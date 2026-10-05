import os
import sys
import time
from collections import OrderedDict
from typing import Any

import addonHandler
import config
import extensionPoints
import gui
import languageHandler
import speech
import versionInfo
from autoSettingsUtils.driverSetting import BooleanDriverSetting, DriverSetting, NumericDriverSetting
from autoSettingsUtils.utils import StringParameterInfo
from logHandler import log as nvdaLog
from speech.commands import (
	BreakCommand,
	CharacterModeCommand,
	IndexCommand,
	LangChangeCommand,
	PitchCommand,
	RateCommand,
	VolumeCommand,
)
from speech.extensions import filter_speechSequence
from synthDriverHandler import SynthDriver, getSynth, synthDoneSpeaking, synthIndexReached

from . import languageDetection
from .compat.commands import normalize_legacy_commands
from .compat.completionPolicies import CompletionPolicy
from .configRepository import ConfigVoiceSettingsRepository
from .indexLedger import IndexLedger
from .nvdaEventBridge import NvdaEventBridge
from .pipeline import (
	STAGES,
	deduplicate_language_command,
	inject_langchange_reorder,
	lang_cmd_to_voice,
	listable,
	order_move_to_start_register,
)
from .pipeline.context import GENERIC_CONTEXT, SpeechContext
from .pipeline.scope import pipeline_scope
from .pipeline.settings import PIPELINE_CONFSPEC, PIPELINE_SETTINGS, pipeline_settings
from .runtime.requestBuilder import queue_speech_sequence
from .runtime.scheduler import TaskManager
from .runtime.settings import VoiceSettingsStore
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
	"pipeline": dict(PIPELINE_CONFSPEC),
	"role": {},
	"engine": {
		"__many__": "boolean(default=false)",
	},
	"log": {
		"enable": "boolean(default=false)",
		**{stage.log_key: "boolean(default=false)" for stage in STAGES},
	},
	"voices": {
		"__many__": {
			"variant": "string(default=None)",
			"rate": "integer(default=50,min=0,max=100)",
			"pitch": "integer(default=50,min=0,max=100)",
			"volume": "integer(default=50,min=0,max=100)",
			"waitfactor": "integer(default=0,min=0,max=10)",
		},
	},
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

	@staticmethod
	def _pipeline_driver_setting(spec):
		options = {"availableInSettingsRing": spec.ring, "defaultVal": spec.default, "useConfig": False}
		if spec.display_name is not None:
			options["displayName"] = spec.display_name
		if spec.kind is bool:
			return BooleanDriverSetting(spec.driver_id, spec.label, **options)
		if spec.kind is int:
			return NumericDriverSetting(spec.driver_id, spec.label, minStep=spec.min_step, **options)
		return DriverSetting(spec.driver_id, spec.label, **options)

	def _driver_settings(self, capabilities):
		"""The synth settings; ``capabilities`` None lists every optional voice setting."""
		settings = [SynthDriver.VoiceSetting(), SynthDriver.VariantSetting(), SynthDriver.RateSetting()]
		if capabilities is None or "rateBoost" in capabilities:
			settings.append(SynthDriver.RateBoostSetting())
		settings.append(SynthDriver.PitchSetting())
		if capabilities is None or "inflection" in capabilities:
			settings.append(SynthDriver.InflectionSetting())
		settings.append(SynthDriver.VolumeSetting())
		settings.append(
			BooleanDriverSetting(
				"uwv",
				_("Detect language based on Unicode characters"),
				availableInSettingsRing=True,
				defaultVal=True,
				displayName=_("Detect language based on Unicode characters"),
			),
		)
		for spec in PIPELINE_SETTINGS:
			if spec.driver_id is None:
				continue
			settings.append(self._pipeline_driver_setting(spec))
			if spec.driver_id == "cni":
				settings.append(
					DriverSetting(
						"numlan",
						# Translators: Label for a setting in voice settings dialog.
						_("Number &Language"),
						availableInSettingsRing=True,
						defaultVal="default",
						# Translators: Label for a setting in synth settings ring.
						displayName=_("Number Language"),
					),
				)
		return settings

	@property
	def supportedSettings(self):
		capabilities = self._voiceManager.getVoiceCapabilities(self._voiceManager.defaultVoiceName)
		return self._driver_settings(capabilities.settings)

	@property
	def allSupportedSettings(self):
		return self._driver_settings(None)

	def __init__(self):
		self._terminated = False
		self._startNotified = False
		self._pipelineRegistered = False
		self._pipelineSubscribed = False
		self._voicePanelPatched = False
		self._spellingPatched = False
		self.OriginVoiceSettingsPanel = None
		self._realSpellingFunc = None
		self.taskManager = None
		self._voiceManager = None
		self._eventBridge = None
		self._settingsStore = None
		self._indexLedger = None
		try:
			self._initialize()
		except BaseException:
			# Release acquired resources even on KeyboardInterrupt, then re-raise.
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
		pipeline_scope.worldvoice_started()
		nvdaLog.debug("WorldVoice init timing: pipeline register %.3fs", time.perf_counter() - step_start)

		step_start = time.perf_counter()
		self.OriginVoiceSettingsPanel = gui.settingsDialogs.VoiceSettingsPanel
		self._voicePanelPatched = True
		gui.settingsDialogs.VoiceSettingsPanel = WorldVoiceVoiceSettingsPanel
		nvdaLog.debug(
			"WorldVoice init timing: voice settings panel patch %.3fs",
			time.perf_counter() - step_start,
		)

		step_start = time.perf_counter()
		repository = ConfigVoiceSettingsRepository(config.conf, lambda: getSynth().name)
		self._settingsStore = VoiceSettingsStore(repository)
		# One ledger spans every binding of a live core in this runtime. A core
		# handed to a new runtime must first close, or retain its original ledger.
		self._indexLedger = IndexLedger()
		self._eventBridge = NvdaEventBridge(
			self,
			done_event=synthDoneSpeaking,
			index_event=synthIndexReached,
			get_synth=getSynth,
			index_ledger=self._indexLedger,
		)
		self.taskManager = TaskManager(output=self._eventBridge, logger=nvdaLog)
		self._eventBridge.start(self.taskManager.on_event, batch_handler=self.taskManager.on_events)
		nvdaLog.debug("WorldVoice init timing: TaskManager %.3fs", time.perf_counter() - step_start)

		step_start = time.perf_counter()
		self._completionPolicy = CompletionPolicy()
		self._voiceManager = VoiceManager(
			taskManager=self.taskManager,
			settings=self._settingsStore,
			bridge=self._eventBridge,
			index_ledger=self._indexLedger,
			completion_for=self._completion_for,
		)
		nvdaLog.debug("WorldVoice init timing: VoiceManager %.3fs", time.perf_counter() - step_start)

		self._apply_pipeline_settings(pipeline_settings.get())
		pipeline_settings.subscribe(self._apply_pipeline_settings)
		self._pipelineSubscribed = True

		step_start = time.perf_counter()
		self._realSpellingFunc = speech.speech.speakSpelling
		self._spellingPatched = True
		speech.speech.speakSpelling = self.patchedSpeakSpelling
		nvdaLog.debug("WorldVoice init timing: speakSpelling patch %.3fs", time.perf_counter() - step_start)

		step_start = time.perf_counter()
		self.speechSymbols = SpeechSymbols()
		nvdaLog.debug(
			"WorldVoice init timing: SpeechSymbols construct %.3fs",
			time.perf_counter() - step_start,
		)

		step_start = time.perf_counter()
		self.speechSymbols.load("unicode.dic")
		nvdaLog.debug(
			"WorldVoice init timing: SpeechSymbols.load unicode.dic %.3fs",
			time.perf_counter() - step_start,
		)

		step_start = time.perf_counter()
		self._languageDetector = languageDetection.LanguageDetector(
			list(self._voiceManager.allLanguages),
			self.speechSymbols,
		)
		self.add_detected_language_commands = listable(self._languageDetector.add_detected_language_commands)
		nvdaLog.debug("WorldVoice init timing: LanguageDetector %.3fs", time.perf_counter() - step_start)

		self._voice = None
		nvdaLog.debug("WorldVoice init timing: total %.3fs", time.perf_counter() - init_start)

	def _completion_for(self, voice_class, core):
		policy = self._completionPolicy
		nvda_version = versionInfo.version
		audio_mode = policy.audio_mode(voice_class, core)
		contract, support = policy.contract_for(
			voice_class,
			core,
			nvda_version=nvda_version,
			audio_mode=audio_mode,
		)
		if support is not None and not support.supported:
			self._warn_drain_fallback(voice_class.engine, nvda_version, audio_mode, support)
		return contract

	def _warn_drain_fallback(self, engine, nvda_version, audio_mode, support):
		# Log each distinct fallback profile once per synth instance.
		fallbacks = getattr(self, "_drainFallbacks", None)
		if fallbacks is None:
			self._drainFallbacks = fallbacks = set()
		profile = (engine, nvda_version, audio_mode, support.profile, support.reason)
		if profile not in fallbacks:
			fallbacks.add(profile)
			nvdaLog.warning(
				"WorldVoice %s uses LEGACY_DONE (NVDA %s, audio %s, profile %s): %s",
				*profile,
			)

	def terminate(self, *, commit=True):
		if self._terminated:
			return
		self._terminated = True

		def _run_cleanup(name, cleanup):
			try:
				cleanup()
			except Exception:
				nvdaLog.error("WorldVoice terminate: %s", name, exc_info=True)

		taskManager = self.taskManager
		if taskManager is not None:
			playbacks = self._voiceManager.playback_ports if self._voiceManager is not None else ()
			_run_cleanup("task manager shutdown", lambda: taskManager.shutdown(playbacks))
		self.taskManager = None

		if hasattr(self, "add_detected_language_commands"):
			_run_cleanup(
				"language detection unregister",
				lambda: filter_speechSequence.unregister(self.add_detected_language_commands),
			)
		if self._pipelineRegistered:
			_run_cleanup("pipeline cleanup", pipeline_scope.worldvoice_ended)
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
		bridge = self._eventBridge
		if bridge is not None:
			_run_cleanup("event bridge close", bridge.close)
		self._eventBridge = None

		if self._pipelineSubscribed:
			_run_cleanup(
				"pipeline settings unsubscribe",
				lambda: pipeline_settings.unsubscribe(self._apply_pipeline_settings),
			)
			self._pipelineSubscribed = False

		voiceManager = self._voiceManager
		if voiceManager is not None:
			_run_cleanup("voice manager terminate", lambda: voiceManager.terminate(commit=commit))
		self._voiceManager = None

		ledger = self._indexLedger
		if ledger is not None:
			_run_cleanup("index ledger close", ledger.close)
		self._indexLedger = None

		if self._startNotified:
			_run_cleanup("end notification", WVEnd.notify)
			self._startNotified = False

	def loadSettings(self, *args, **kwargs):
		super().loadSettings(*args, **kwargs)
		# Pipeline settings are not NVDA driver config; re-read them for this profile.
		self._apply_pipeline_settings(pipeline_settings.get())
		self._voiceManager.reload()

	def _apply_pipeline_settings(self, settings):
		manager = self._voiceManager
		if manager is not None:
			manager.waitfactor = min(settings.global_wait_factor // 10, 9)

	def speak(self, speechSequence):
		if self._terminated:
			return
		self.order = 0
		if self.uwv and config.conf["WorldVoice"]["autoLanguageSwitching"]["DetectLanguageTiming"] == "after":
			speechSequence = self.add_detected_language_commands(speechSequence)

		speechSequence = inject_langchange_reorder(speechSequence)
		speechSequence = deduplicate_language_command(speechSequence, self.speech_context())

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
		if self.uwv and config.conf["speech"]["trustVoiceLanguage"]:
			for text, loc in self._languageDetector.process_for_spelling(text, locale):
				self._realSpellingFunc(text, loc, useCharacterDescriptions, priority=priority)
		else:
			self._realSpellingFunc(text, locale, useCharacterDescriptions, priority=priority)

	def cancel(self):
		self._voiceManager.cancel()

	def pause(self, switch):
		self.taskManager.pause_current(switch)

	def speech_context(self) -> SpeechContext:
		manager = self._voiceManager
		if manager is None:
			return GENERIC_CONTEXT
		return SpeechContext(
			supports_roles=True,
			language=self.language,
			number_language=getattr(self, "_numlan", "default"),
			speech_symbols=getattr(self, "speechSymbols", None),
			default_voice=manager.defaultVoiceInstance,
			voice_for_language=manager.getVoiceInstanceForLanguage,
		)

	def _set_voice_parameter(self, name, value):
		instance = self._voiceManager.defaultVoiceInstance
		setattr(instance, name, value)
		instance.commit()
		if self._voiceManager.parameter_consistency.enabled:
			self._voiceManager.onVoiceParameterConsistent(instance)

	def _get_volume(self):
		return self._voiceManager.defaultVoiceInstance.volume

	def _set_volume(self, value):
		self._set_voice_parameter("volume", value)

	def _get_rate(self):
		return self._voiceManager.defaultVoiceInstance.rate

	def _set_rate(self, value):
		self._set_voice_parameter("rate", value)

	def _get_pitch(self):
		return self._voiceManager.defaultVoiceInstance.pitch

	def _set_pitch(self, value):
		self._set_voice_parameter("pitch", value)

	def _get_inflection(self):
		return self._voiceManager.defaultVoiceInstance.inflection

	def _set_inflection(self, value):
		self._set_voice_parameter("inflection", value)

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
		for item in self._voiceManager.getVoiceVariants(self._voiceManager.defaultVoiceName):
			values[item["id"]] = StringParameterInfo(item["id"], item["name"])
		return values

	def _get_variant(self):
		return self._voiceManager.defaultVoiceInstance.variant

	def _set_variant(self, value):
		self._set_voice_parameter("variant", value)

	def _get_rateBoost(self):
		return self._voiceManager.defaultVoiceInstance.rateBoost

	def _set_rateBoost(self, enable):
		self._set_voice_parameter("rateBoost", enable)

	def _get_uwv(self):
		return self._uwv

	def _set_uwv(self, value):
		self._uwv = value
		self.detect_language_timing()

	def detect_language_timing(self):
		if (
			self.uwv
			and config.conf["WorldVoice"]["autoLanguageSwitching"]["DetectLanguageTiming"] == "before"
		):
			filter_speechSequence.register(self.add_detected_language_commands)
			order_move_to_start_register()
		else:
			filter_speechSequence.unregister(self.add_detected_language_commands)

	def _get_availableNumlans(self):
		return dict(
			{
				"default": StringParameterInfo("default", _("default")),
			},
			**{
				locale: StringParameterInfo(locale, name)
				for locale, name in zip(
					self._voiceManager.languages,
					list(map(self._getLocaleReadableName, self._voiceManager.languages)),
				)
			},
		)

	def _get_numlan(self):
		return self._numlan

	def _set_numlan(self, value):
		self._numlan = value

	def _get_availableNummods(self):
		return dict(
			{
				"value": StringParameterInfo("value", _("value")),
				"number": StringParameterInfo("number", _("number")),
				"pair": StringParameterInfo("pair", _("pair")),
			},
		)

	def _getLocaleReadableName(self, locale):
		description = languageHandler.getLanguageDescription(locale)
		return "%s" % (description) if description else locale


class _PipelineSetting:
	"""A synth attribute stored only in the pipeline config, never in NVDA's speech config."""

	def __init__(self, key):
		self._key = key

	def __get__(self, synth, owner=None):
		if synth is None:
			return self
		return getattr(pipeline_settings.get(), self._key)

	def __set__(self, synth, value):
		pipeline_settings.update(**{self._key: value})


for _spec in PIPELINE_SETTINGS:
	if _spec.driver_id is not None:
		setattr(SynthDriver, _spec.driver_id, _PipelineSetting(_spec.key))
