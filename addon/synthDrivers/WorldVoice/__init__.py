from collections import OrderedDict
import importlib
import os
import sys
import time
from typing import Any

import addonHandler
from autoSettingsUtils.driverSetting import BooleanDriverSetting, DriverSetting, NumericDriverSetting
from autoSettingsUtils.utils import StringParameterInfo
import config
import extensionPoints
import gui
import languageHandler
from logHandler import log as nvdaLog
import speech
from speech.commands import IndexCommand, CharacterModeCommand, LangChangeCommand, PitchCommand, RateCommand, VolumeCommand, SpeechCommand, BreakCommand
from speech.extensions import filter_speechSequence
from synthDriverHandler import SynthDriver, synthIndexReached, synthDoneSpeaking, getSynth

from . import languageDetection
from .pipeline import (
	ignore_comma_between_number,
	item_wait_factor,
	inject_langchange_reorder,
	deduplicate_language_command,
	lang_cmd_to_voice,
	order_move_to_start_register,
	listable,
)
from .pipeline.settings import (
	apply_worldvoice_pipeline,
	clear_pipeline,
	get_effective_pipeline_settings,
	save_pipeline_settings,
)
from .configRepository import ConfigVoiceSettingsRepository
from .runtime.settings import VoiceSettingsStore
from .nvdaEventBridge import NvdaEventBridge
from .compat.commands import normalize_legacy_commands
from .taskManager import TaskManager
from .requestBuilder import queue_speech_sequence
from .voiceManager import VoiceManager
from .VoiceSettingsDialogs import WorldVoiceVoiceSettingsPanel


_: Any

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, base_dir)
from generics.speechSymbols.models import SpeechSymbols

addonHandler.initTranslation()

config.conf.spec["WorldVoice"] = {
	"autoLanguageSwitching": {
		"ignoreNumbersInLanguageDetection": "boolean(default=false)",
		"latinCharactersLanguage": "string(default=en)",
		"CJKCharactersLanguage": "string(default=ja)",
		"arabicCharactersLanguage": "string(default=ar)",
		"DetectLanguageTiming": "string(default=after)",
		"KeepMainLocaleVoiceConsistent": "boolean(default=true)",
		"KeepMainLocaleParameterConsistent": "boolean(default=false)",
		"KeepMainLocaleEngineConsistent": "boolean(default=true)",
	},
	"pipeline": {
		"scope": "string(default=WorldVoice)",
		"ignore_comma_between_number": "boolean(default=false)",
		"number_mode": "string(default=value)",
		"global_wait_factor": "integer(default=10,min=0,max=100)",
		"number_wait_factor": "integer(default=10,min=0,max=100)",
		"pair_wait_factor": "integer(default=0,min=0,max=100)",
		"item_wait_factor": "integer(default=10,min=0,max=100)",
		"sayall_wait_factor": "integer(default=10,min=0,max=100)",
		"chinesespace_wait_factor": "integer(default=10,min=0,max=100)",
		"punctuation_wait_factor": "integer(default=0,min=0,max=100)",
		"punctuation_pause_enabled": "boolean(default=true)",
		"remove_punctuation_characters": "boolean(default=false)",
		"punctuation_pause_characters": "string(default=\"،؛,.;:!؟?…\")",
	},
	"role": {},
	"engine": {
		"__many__": "boolean(default=false)"
	},
	"log": {
		"enable": "boolean(default=false)",
		"ignore_comma_between_number": "boolean(default=false)",
		"number_mode": "boolean(default=false)",
		"number_language": "boolean(default=false)",
		"number_wait_factor": "boolean(default=false)",
		"item_wait_factor": "boolean(default=false)",
		"chinesespace_wait_factor": "boolean(default=false)",
		"punctuation_wait_factor": "boolean(default=false)",
		"speech_viewer": "boolean(default=false)",
		"apply_speech_dictionaries": "boolean(default=false)",
	},
	"voices": {
		"__many__": {
			"variant": "string(default=None)",
			"rate": "integer(default=50,min=0,max=100)",
			"pitch": "integer(default=50,min=0,max=100)",
			"volume": "integer(default=50,min=0,max=100)",
			"waitfactor": "integer(default=0,min=0,max=10)",
		}
	}
}

WVStart = extensionPoints.Action()
WVEnd = extensionPoints.Action()


class SynthDriver(SynthDriver):
	name = "WorldVoice"
	description = "WorldVoice"
	supportedCommands = {
		IndexCommand,
		CharacterModeCommand,
		LangChangeCommand,
		BreakCommand,
		PitchCommand,
		RateCommand,
		VolumeCommand,
	}
	supportedNotifications = {synthIndexReached, synthDoneSpeaking}

	@classmethod
	def check(cls):
		return True

	@property
	def supportedSettings(self):
		settings = [
			SynthDriver.VoiceSetting(),
		]
		settings.append(SynthDriver.VariantSetting())
		settings.append(SynthDriver.RateSetting())
		if "rateBoost" in self._voiceManager.defaultVoiceInstance.__class__.supportedSettings():
			settings.append(SynthDriver.RateBoostSetting())
		settings.extend([
			SynthDriver.PitchSetting(),
		])
		if 'inflection' in self._voiceManager.defaultVoiceInstance.__class__.supportedSettings():
			settings.append(SynthDriver.InflectionSetting())
		settings.extend([
			SynthDriver.VolumeSetting(),
			BooleanDriverSetting(
				"uwv",
				_("Detect language based on Unicode characters"),
				availableInSettingsRing=True,
				defaultVal=True,
				displayName=_("Detect language based on Unicode characters"),
			),
			BooleanDriverSetting(
				"cni",
				_("Ignore comma between number"),
				defaultVal=False,
			),
			DriverSetting(
				"numlan",
				# Translators: Label for a setting in voice settings dialog.
				_("Number &Language"),
				availableInSettingsRing=True,
				defaultVal="default",
				# Translators: Label for a setting in synth settings ring.
				displayName=_("Number Language"),
			),
			DriverSetting(
				"nummod",
				# Translators: Label for a setting in voice settings dialog.
				_("Number &Mode"),
				availableInSettingsRing=True,
				defaultVal="value",
				# Translators: Label for a setting in synth settings ring.
				displayName=_("Number Mode"),
			),
			NumericDriverSetting(
				"globalwaitfactor",
				# Translators: Label for a setting in voice settings dialog.
				_("Global wait factor"),
				availableInSettingsRing=True,
				defaultVal=50,
				minStep=10,
			),
			NumericDriverSetting(
				"numberwaitfactor",
				# Translators: Label for a setting in voice settings dialog.
				_("Number wait factor"),
				availableInSettingsRing=True,
				defaultVal=0,
				minStep=1,
			),
			NumericDriverSetting(
				"pairwaitfactor",
				# Translators: Label for a setting in voice settings dialog.
				_("Pair wait factor"),
				availableInSettingsRing=True,
				defaultVal=0,
				minStep=1,
			),
			NumericDriverSetting(
				"itemwaitfactor",
				# Translators: Label for a setting in voice settings dialog.
				_("item wait factor"),
				availableInSettingsRing=True,
				defaultVal=0,
				minStep=1,
			),
			NumericDriverSetting(
				"sayallwaitfactor",
				# Translators: Label for a setting in voice settings dialog.
				_("Say all wait factor"),
				availableInSettingsRing=True,
				defaultVal=0,
				minStep=1,
			),
			NumericDriverSetting(
				"chinesespacewaitfactor",
				# Translators: Label for a setting in voice settings dialog.
				_("Chinese space wait factor"),
				availableInSettingsRing=True,
				defaultVal=0,
				minStep=1,
			),
			BooleanDriverSetting(
				"punctuationpauseenabled",
				# Translators: Label for a setting in voice settings dialog.
				_("Enable punctuation pause control"),
				availableInSettingsRing=True,
				defaultVal=True,
				# Translators: Label for a setting in synth settings ring.
				displayName=_("Punctuation pauses"),
			),
			BooleanDriverSetting(
				"removepunctuationcharacters",
				_("Remove configured punctuation at pause points"),
				availableInSettingsRing=True,
				defaultVal=False,
				displayName=_("Remove punctuation at pause points"),
			),
			NumericDriverSetting(
				"punctuationwaitfactor",
				# Translators: Label for a setting in voice settings dialog.
				_("Punctuation wait factor"),
				availableInSettingsRing=True,
				defaultVal=0,
				minStep=1,
			),
		])
		return settings

	@property
	def allSupportedSettings(self):
		settings = [
			SynthDriver.VoiceSetting(),
			SynthDriver.VariantSetting(),
			SynthDriver.RateSetting(),
			SynthDriver.RateBoostSetting(),
			SynthDriver.PitchSetting(),
			SynthDriver.InflectionSetting(),
			SynthDriver.VolumeSetting(),
			BooleanDriverSetting(
				"uwv",
				_("Detect language based on Unicode characters"),
				availableInSettingsRing=True,
				defaultVal=True,
				displayName=_("Detect language based on Unicode characters"),
			),
			BooleanDriverSetting(
				"cni",
				_("Ignore comma between number"),
				defaultVal=False,
			),
			DriverSetting(
				"numlan",
				# Translators: Label for a setting in voice settings dialog.
				_("Number &Language"),
				availableInSettingsRing=True,
				defaultVal="default",
				# Translators: Label for a setting in synth settings ring.
				displayName=_("Number Language"),
			),
			DriverSetting(
				"nummod",
				# Translators: Label for a setting in voice settings dialog.
				_("Number &Mode"),
				availableInSettingsRing=True,
				defaultVal="value",
				# Translators: Label for a setting in synth settings ring.
				displayName=_("Number Mode"),
			),
			NumericDriverSetting(
				"globalwaitfactor",
				# Translators: Label for a setting in voice settings dialog.
				_("Global wait factor"),
				availableInSettingsRing=True,
				defaultVal=50,
				minStep=10,
			),
			NumericDriverSetting(
				"numberwaitfactor",
				# Translators: Label for a setting in voice settings dialog.
				_("Number wait factor"),
				availableInSettingsRing=True,
				defaultVal=0,
				minStep=1,
			),
			NumericDriverSetting(
				"pairwaitfactor",
				# Translators: Label for a setting in voice settings dialog.
				_("Pair wait factor"),
				availableInSettingsRing=True,
				defaultVal=0,
				minStep=1,
			),
			NumericDriverSetting(
				"itemwaitfactor",
				# Translators: Label for a setting in voice settings dialog.
				_("item wait factor"),
				availableInSettingsRing=True,
				defaultVal=0,
				minStep=1,
			),
			NumericDriverSetting(
				"sayallwaitfactor",
				# Translators: Label for a setting in voice settings dialog.
				_("Say all wait factor"),
				availableInSettingsRing=True,
				defaultVal=0,
				minStep=1,
			),
			NumericDriverSetting(
				"chinesespacewaitfactor",
				# Translators: Label for a setting in voice settings dialog.
				_("Chinese space wait factor"),
				availableInSettingsRing=True,
				defaultVal=0,
				minStep=1,
			),
			BooleanDriverSetting(
				"punctuationpauseenabled",
				# Translators: Label for a setting in voice settings dialog.
				_("Enable punctuation pause control"),
				availableInSettingsRing=True,
				defaultVal=True,
				# Translators: Label for a setting in synth settings ring.
				displayName=_("Punctuation pauses"),
			),
			BooleanDriverSetting(
				"removepunctuationcharacters",
				_("Remove configured punctuation at pause points"),
				availableInSettingsRing=True,
				defaultVal=False,
				displayName=_("Remove punctuation at pause points"),
			),
			NumericDriverSetting(
				"punctuationwaitfactor",
				# Translators: Label for a setting in voice settings dialog.
				_("Punctuation wait factor"),
				availableInSettingsRing=True,
				defaultVal=0,
				minStep=1,
			),
		]
		return settings

	def __init__(self):
		self._terminated = False
		self._startNotified = False
		self._pipelineRegistered = False
		self._voicePanelPatched = False
		self._spellingPatched = False
		self.OriginVoiceSettingsPanel = None
		self._realSpellingFunc = None
		self.taskManager = None
		self._voiceManager = None
		self._eventBridge = None
		self._settingsStore = None
		try:
			self._initialize()
		except BaseException:
			self.terminate(commit=False)
			raise

	def _initialize(self):
		init_start = time.perf_counter()
		step_start = init_start
		self._startNotified = True
		WVStart.notify()
		nvdaLog.debug("WorldVoice init timing: WVStart.notify %.3fs", time.perf_counter() - step_start)

		self.order = 0

		step_start = time.perf_counter()
		self._pipelineRegistered = True
		apply_worldvoice_pipeline()
		nvdaLog.debug("WorldVoice init timing: pipeline register %.3fs", time.perf_counter() - step_start)

		step_start = time.perf_counter()
		self.OriginVoiceSettingsPanel = gui.settingsDialogs.VoiceSettingsPanel
		self._voicePanelPatched = True
		gui.settingsDialogs.VoiceSettingsPanel = WorldVoiceVoiceSettingsPanel
		nvdaLog.debug("WorldVoice init timing: voice settings panel patch %.3fs", time.perf_counter() - step_start)

		step_start = time.perf_counter()
		repository = ConfigVoiceSettingsRepository(config.conf, lambda: getSynth().name)
		self._settingsStore = VoiceSettingsStore(repository)
		self._eventBridge = NvdaEventBridge(self, done_event=synthDoneSpeaking,
			index_event=synthIndexReached, get_synth=getSynth)
		self.taskManager = TaskManager(output=self._eventBridge, logger=nvdaLog)
		self._eventBridge.start(self.taskManager.on_event)
		nvdaLog.debug("WorldVoice init timing: TaskManager %.3fs", time.perf_counter() - step_start)

		step_start = time.perf_counter()
		self._voiceManager = VoiceManager(taskManager=self.taskManager,
			settings=self._settingsStore, bridge=self._eventBridge)
		nvdaLog.debug("WorldVoice init timing: VoiceManager %.3fs", time.perf_counter() - step_start)

		step_start = time.perf_counter()
		self._realSpellingFunc = speech.speech.speakSpelling
		self._spellingPatched = True
		speech.speech.speakSpelling = self.patchedSpeakSpelling
		nvdaLog.debug("WorldVoice init timing: speakSpelling patch %.3fs", time.perf_counter() - step_start)

		step_start = time.perf_counter()
		self.speechSymbols = SpeechSymbols()
		nvdaLog.debug("WorldVoice init timing: SpeechSymbols construct %.3fs", time.perf_counter() - step_start)

		step_start = time.perf_counter()
		self.speechSymbols.load('unicode.dic')
		nvdaLog.debug("WorldVoice init timing: SpeechSymbols.load unicode.dic %.3fs", time.perf_counter() - step_start)

		step_start = time.perf_counter()
		self._languageDetector = languageDetection.LanguageDetector(list(self._voiceManager.allLanguages), self.speechSymbols)
		self.add_detected_language_commands = listable(self._languageDetector.add_detected_language_commands)
		nvdaLog.debug("WorldVoice init timing: LanguageDetector %.3fs", time.perf_counter() - step_start)

		self._voice = None
		nvdaLog.debug("WorldVoice init timing: total %.3fs", time.perf_counter() - init_start)

	def terminate(self, *, commit=True):
		if self._terminated:
			return
		self._terminated = True

		def _run_cleanup(name, cleanup):
			try:
				cleanup()
			except BaseException:
				nvdaLog.error("WorldVoice terminate: %s", name, exc_info=True)

		if hasattr(self, "add_detected_language_commands"):
			_run_cleanup(
				"language detection unregister",
				lambda: filter_speechSequence.unregister(self.add_detected_language_commands),
			)
		if self._pipelineRegistered:
			_run_cleanup("pipeline cleanup", clear_pipeline)
			self._pipelineRegistered = False
		if self._voicePanelPatched:
			_run_cleanup(
				"voice settings panel restore",
				lambda: setattr(gui.settingsDialogs, "VoiceSettingsPanel", self.OriginVoiceSettingsPanel),
			)
			self._voicePanelPatched = False
		if self._spellingPatched:
			_run_cleanup(
				"spelling function restore",
				lambda: setattr(speech.speech, "speakSpelling", self._realSpellingFunc),
			)
			self._spellingPatched = False
		if self._voiceManager is not None:
			_run_cleanup("cancel", self.cancel)

		taskManager = self.taskManager
		if taskManager is not None:
			_run_cleanup("task manager shutdown", taskManager.shutdown)
		self.taskManager = None

		bridge = self._eventBridge
		if bridge is not None:
			_run_cleanup("event bridge close", bridge.close)
		self._eventBridge = None

		voiceManager = self._voiceManager
		if voiceManager is not None:
			_run_cleanup("voice manager terminate", lambda: voiceManager.terminate(commit=commit))
		self._voiceManager = None

		if self._startNotified:
			_run_cleanup("end notification", WVEnd.notify)
			self._startNotified = False

	def loadSettings(self, *args, **kwargs):
		super().loadSettings(*args, **kwargs)
		self._voiceManager.reload()
		save_pipeline_settings(get_effective_pipeline_settings(synth=self))

	def saveSettings(self, *args, **kwargs):
		super().saveSettings(*args, **kwargs)
		save_pipeline_settings(get_effective_pipeline_settings(synth=self))

	def speak(self, speechSequence):
		self.order = 0
		if self.uwv and config.conf["WorldVoice"]['autoLanguageSwitching']['DetectLanguageTiming'] == 'after':
			speechSequence = self.add_detected_language_commands(speechSequence)

		speechSequence = inject_langchange_reorder(speechSequence)
		speechSequence = deduplicate_language_command(speechSequence)

		speechSequence = lang_cmd_to_voice(
			speechSequence=speechSequence,
			voice_manager=self._voiceManager,
			default_instance=self._voiceManager.defaultVoiceInstance,
		)

		queue_speech_sequence(
			self.taskManager,
			normalize_legacy_commands(speechSequence),
			self._voiceManager.defaultVoiceName,
			self._voiceManager.resolve_playback,
		)

	def patchedSpeakSpelling(self, text, locale=None, useCharacterDescriptions=False, priority=None):
		if self.uwv \
		and config.conf["speech"]["trustVoiceLanguage"]:
			for text, loc in self._languageDetector.process_for_spelling(text, locale):
				self._realSpellingFunc(text, loc, useCharacterDescriptions, priority=priority)
		else:
			self._realSpellingFunc(text, locale, useCharacterDescriptions, priority=priority)

	def cancel(self):
		self._voiceManager.cancel()

	def pause(self, switch):
		self.taskManager.pause_current(switch)

	def _get_volume(self):
		return self._voiceManager.defaultVoiceInstance.volume

	def _set_volume(self, value):
		self._voiceManager.defaultVoiceInstance.volume = value
		self._voiceManager.defaultVoiceInstance.commit()
		if config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"]:
			self._voiceManager.onVoiceParameterConsistent(self._voiceManager.defaultVoiceInstance)

	def _get_rate(self):
		return self._voiceManager.defaultVoiceInstance.rate

	def _set_rate(self, value):
		self._voiceManager.defaultVoiceInstance.rate = value
		self._voiceManager.defaultVoiceInstance.commit()
		if config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"]:
			self._voiceManager.onVoiceParameterConsistent(self._voiceManager.defaultVoiceInstance)

	def _get_pitch(self):
		return self._voiceManager.defaultVoiceInstance.pitch

	def _set_pitch(self, value):
		self._voiceManager.defaultVoiceInstance.pitch = value
		self._voiceManager.defaultVoiceInstance.commit()
		if config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"]:
			self._voiceManager.onVoiceParameterConsistent(self._voiceManager.defaultVoiceInstance)

	def _get_inflection(self):
		return self._voiceManager.defaultVoiceInstance.inflection

	def _set_inflection(self, value):
		self._voiceManager.defaultVoiceInstance.inflection = value
		self._voiceManager.defaultVoiceInstance.commit()
		if config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"]:
			self._voiceManager.onVoiceParameterConsistent(self._voiceManager.defaultVoiceInstance)

	def _getAvailableVoices(self):
		return self._voiceManager.voiceInfos

	def _get_voice(self):
		if self._voice is None:
			voice = self._voiceManager.getVoiceNameForLanguage(languageHandler.getLanguage())
			if voice is None:
				voice = list(self.availableVoices.keys())[0]
			return voice
		return self._voiceManager.defaultVoiceName

	def _set_voice(self, voiceName):
		self._voice = voiceName
		if voiceName == self._voiceManager.defaultVoiceName:
			return
		# Stop speech before setting a new voice to avoid voice instances
		# continuing speaking when changing voices for, e.g., say-all
		# See NVDA ticket #3540
		self._voiceManager.defaultVoiceInstance.stop()
		self._voiceManager.defaultVoiceName = voiceName

	def _get_availableVariants(self):
		values = OrderedDict([("default", StringParameterInfo("default", _("default")))])
		for item in self._voiceManager.defaultVoiceInstance.variants:
			values[item["id"]] = StringParameterInfo(item["id"], item["name"])
		return values

	def _get_variant(self):
		return self._voiceManager.defaultVoiceInstance.variant

	def _set_variant(self, value):
		self._voiceManager.defaultVoiceInstance.variant = value
		self._voiceManager.defaultVoiceInstance.commit()
		if config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"]:
			self._voiceManager.onVoiceParameterConsistent(self._voiceManager.defaultVoiceInstance)

	def _get_rateBoost(self):
		return self._voiceManager.defaultVoiceInstance.rateBoost

	def _set_rateBoost(self, enable):
		self._voiceManager.defaultVoiceInstance.rateBoost = enable
		self._voiceManager.defaultVoiceInstance.commit()
		if config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"]:
			self._voiceManager.onVoiceParameterConsistent(self._voiceManager.defaultVoiceInstance)

	def _get_uwv(self):
		return self._uwv

	def _set_uwv(self, value):
		self._uwv = value
		self.detect_language_timing()

	def detect_language_timing(self):
		if self.uwv and config.conf["WorldVoice"]['autoLanguageSwitching']['DetectLanguageTiming'] == 'before':
			filter_speechSequence.register(self.add_detected_language_commands)
			order_move_to_start_register()
		else:
			filter_speechSequence.unregister(self.add_detected_language_commands)

	def _get_cni(self):
		return self._cni

	def _set_cni(self, value):
		self._cni = value
		if value:
			filter_speechSequence.register(ignore_comma_between_number)
			order_move_to_start_register()
		else:
			filter_speechSequence.unregister(ignore_comma_between_number)
		config.conf["WorldVoice"]["pipeline"]["ignore_comma_between_number"] = self.cni

	def _get_availableNumlans(self):
		return dict(
			{
				"default": StringParameterInfo("default", _("default")),
			},
			**{
				locale: StringParameterInfo(locale, name) for locale, name in zip(self._voiceManager.languages, list(map(self._getLocaleReadableName, self._voiceManager.languages)))
			}
		)

	def _get_numlan(self):
		return self._numlan

	def _set_numlan(self, value):
		self._numlan = value

	def _get_availableNummods(self):
		return dict({
			"value": StringParameterInfo("value", _("value")),
			"number": StringParameterInfo("number", _("number")),
			"pair": StringParameterInfo("pair", _("pair")),
		})

	def _get_nummod(self):
		return self._nummod

	def _set_nummod(self, value):
		self._nummod = value
		config.conf["WorldVoice"]["pipeline"]["number_mode"] = self.nummod

	def _get_globalwaitfactor(self):
		return self._globalwaitfactor * 10

	def _set_globalwaitfactor(self, value):
		self._globalwaitfactor = value // 10
		self._voiceManager.waitfactor = min(value // 10, 9)
		config.conf["WorldVoice"]["pipeline"]["global_wait_factor"] = self.globalwaitfactor

	def _get_numberwaitfactor(self):
		return self._numberwaitfactor

	def _set_numberwaitfactor(self, value):
		self._numberwaitfactor = value
		config.conf["WorldVoice"]["pipeline"]["number_wait_factor"] = self.numberwaitfactor

	def _get_pairwaitfactor(self):
		# Defensive: the attribute may not exist yet when the driver was
		# upgraded from a version without this setting.
		return getattr(self, "_pairwaitfactor", 0)

	def _set_pairwaitfactor(self, value):
		self._pairwaitfactor = value
		config.conf["WorldVoice"]["pipeline"]["pair_wait_factor"] = self.pairwaitfactor

	def _get_itemwaitfactor(self):
		return self._itemwaitfactor

	def _set_itemwaitfactor(self, value):
		self._itemwaitfactor = value
		if value > 0:
			filter_speechSequence.register(item_wait_factor)
			order_move_to_start_register()
		else:
			filter_speechSequence.unregister(item_wait_factor)
		config.conf["WorldVoice"]["pipeline"]["item_wait_factor"] = self.itemwaitfactor

	def _get_sayallwaitfactor(self):
		return self._sayallwaitfactor

	def _set_sayallwaitfactor(self, value):
		self._sayallwaitfactor = value
		config.conf["WorldVoice"]["pipeline"]["sayall_wait_factor"] = self.sayallwaitfactor

	def _get_chinesespacewaitfactor(self):
		return self._chinesespacewaitfactor

	def _set_chinesespacewaitfactor(self, value):
		self._chinesespacewaitfactor = value
		config.conf["WorldVoice"]["pipeline"]["chinesespace_wait_factor"] = self.chinesespacewaitfactor

	def _get_punctuationpauseenabled(self):
		# Defensive: the attribute may not exist yet when the driver was
		# upgraded from a version without this setting.
		return getattr(self, "_punctuationpauseenabled", True)

	def _set_punctuationpauseenabled(self, value):
		self._punctuationpauseenabled = value
		config.conf["WorldVoice"]["pipeline"]["punctuation_pause_enabled"] = self.punctuationpauseenabled

	def _get_removepunctuationcharacters(self):
		return getattr(self, "_removepunctuationcharacters", False)

	def _set_removepunctuationcharacters(self, value):
		self._removepunctuationcharacters = value
		config.conf["WorldVoice"]["pipeline"]["remove_punctuation_characters"] = self.removepunctuationcharacters

	def _get_punctuationwaitfactor(self):
		# Defensive: the attribute may not exist yet when the driver was
		# upgraded from a version without this setting.
		return getattr(self, "_punctuationwaitfactor", 0)

	def _set_punctuationwaitfactor(self, value):
		self._punctuationwaitfactor = value
		config.conf["WorldVoice"]["pipeline"]["punctuation_wait_factor"] = self.punctuationwaitfactor

	def _getLocaleReadableName(self, locale):
		description = languageHandler.getLanguageDescription(locale)
		return "%s" % (description) if description else locale
