from collections import OrderedDict
import importlib
import os
import re
import sys
from typing import Any

import addonHandler
from autoSettingsUtils.driverSetting import BooleanDriverSetting, DriverSetting, NumericDriverSetting
from autoSettingsUtils.utils import StringParameterInfo
import buildVersion
import config
import extensionPoints
import gui
import languageHandler
from logHandler import log
import speech
from speech.commands import IndexCommand, CharacterModeCommand, LangChangeCommand, BreakCommand, PitchCommand, RateCommand, VolumeCommand, SpeechCommand
from speech.extensions import filter_speechSequence
from synthDriverHandler import SynthDriver, synthIndexReached, synthDoneSpeaking

from . import languageDetection

from .pipeline import (
	ignore_comma_between_number,
	item_wait_factor,
	inject_langchange_reorder,
	deduplicate_language_command,
	lang_cmd_to_voice,
	order_move_to_start_register,
	static_register,
	unregister,
)
from ._speechcommand import SplitCommand
from .engine import EngineType
from .voiceManager import VoiceManager
from .VoiceSettingsDialogs import WorldVoiceVoiceSettingsPanel

version = "2024" if buildVersion.formatBuildVersionString().split(".")[0] == "2024" else "2025"
module = importlib.import_module(f"synthDrivers.WorldVoice.driver.{version}")
Voice = getattr(module, "Voice")


_: Any

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, base_dir)
from generics.speechSymbols.models import SpeechSymbols

addonHandler.initTranslation()

config.conf.spec["WorldVoice"] = {
	"autoLanguageSwitching": {
		"ignoreNumbersInLanguageDetection": "boolean(default=false)",
		"ignorePunctuationInLanguageDetection": "boolean(default=false)",
		"latinCharactersLanguage": "string(default=en)",
		"CJKCharactersLanguage": "string(default=ja)",
		"arabicCharactersLanguage": "string(default=ar)",
		"DetectLanguageTiming": "string(default=after)",
		"KeepMainLocaleVoiceConsistent": "boolean(default=true)",
		"KeepMainLocaleParameterConsistent": "boolean(default=false)",
		"KeepMainLocaleEngineConsistent": "boolean(default=true)",
	},
	"pipeline": {
		"enable": "boolean(default=true)",
		"scope": "string(default=WorldVoice)",
		"ignore_comma_between_number": "boolean(default=false)",
		"number_mode": "string(default=value)",
		"global_wait_factor": "integer(default=50,min=0,max=100)",
		"number_wait_factor": "integer(default=50,min=0,max=100)",
		"item_wait_factor": "integer(default=50,min=0,max=100)",
		"sayall_wait_factor": "integer(default=50,min=0,max=100)",
		"chinesespace_wait_factor": "integer(default=50,min=0,max=100)",
	},
	"role": {},
	"engine": {
		eng.name: f"boolean(default={str(eng.default_enabled)})"
		for eng in EngineType
	},
	"log": {
		"enable": "boolean(default=false)",
		"ignore_comma_between_number": "boolean(default=false)",
		"number_mode": "boolean(default=false)",
		"number_language": "boolean(default=false)",
		"number_wait_factor": "boolean(default=false)",
		"item_wait_factor": "boolean(default=false)",
		"chinesespace_wait_factor": "boolean(default=false)",
		"speech_viewer": "boolean(default=false)",
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
		if self._voiceManager.defaultVoiceInstance.engine in ["OneCore", "SAPI5", "RH", "espeak", "VE"]:
			settings.append(SynthDriver.RateBoostSetting())
		settings.extend([
			SynthDriver.PitchSetting(),
		])
		if self._voiceManager.defaultVoiceInstance.engine in ["aisound"]:
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
		]
		return settings

	def __init__(self):
		WVStart.notify()

		self.order = 0

		static_register()
		order_move_to_start_register()

		self.OriginVoiceSettingsPanel = gui.settingsDialogs.VoiceSettingsPanel
		gui.settingsDialogs.VoiceSettingsPanel = WorldVoiceVoiceSettingsPanel

		self._voiceManager = VoiceManager()

		self._realSpellingFunc = speech.speech.speakSpelling
		speech.speech.speakSpelling = self.patchedSpeakSpelling

		self.speechSymbols = SpeechSymbols()
		self.speechSymbols.load('unicode.dic')

		self._languageDetector = languageDetection.LanguageDetector(list(self._voiceManager.allLanguages), self.speechSymbols)

		self._voice = None

	def terminate(self):
		unregister()

		gui.settingsDialogs.VoiceSettingsPanel = self.OriginVoiceSettingsPanel

		speech.speech.speakSpelling = self._realSpellingFunc

		try:
			self.cancel()
			self._voiceManager.terminate()
		except BaseException:
			log.error("WorldVoice terminate", exc_info=True)

		WVEnd.notify()

	def loadSettings(self, *args, **kwargs):
		super().loadSettings(*args, **kwargs)
		self._voiceManager.reload()
		config.conf["WorldVoice"]["pipeline"]["ignore_comma_between_number"] = self.cni
		config.conf["WorldVoice"]["pipeline"]["number_mode"] = self.nummod
		config.conf["WorldVoice"]["pipeline"]["global_wait_factor"] = self.globalwaitfactor
		config.conf["WorldVoice"]["pipeline"]["number_wait_factor"] = self.numberwaitfactor
		config.conf["WorldVoice"]["pipeline"]["item_wait_factor"] = self.itemwaitfactor
		config.conf["WorldVoice"]["pipeline"]["sayall_wait_factor"] = self.sayallwaitfactor
		config.conf["WorldVoice"]["pipeline"]["chinesespace_wait_factor"] = self.chinesespacewaitfactor

	def saveSettings(self, *args, **kwargs):
		super().saveSettings(*args, **kwargs)
		config.conf["WorldVoice"]["pipeline"]["ignore_comma_between_number"] = self.cni
		config.conf["WorldVoice"]["pipeline"]["number_mode"] = self.nummod
		config.conf["WorldVoice"]["pipeline"]["global_wait_factor"] = self.globalwaitfactor
		config.conf["WorldVoice"]["pipeline"]["number_wait_factor"] = self.numberwaitfactor
		config.conf["WorldVoice"]["pipeline"]["item_wait_factor"] = self.itemwaitfactor
		config.conf["WorldVoice"]["pipeline"]["sayall_wait_factor"] = self.sayallwaitfactor
		config.conf["WorldVoice"]["pipeline"]["chinesespace_wait_factor"] = self.chinesespacewaitfactor

	def speak(self, speechSequence):
		self.order = 0
		if self.uwv and config.conf["WorldVoice"]['autoLanguageSwitching']['DetectLanguageTiming'] == 'after':
			speechSequence = self._languageDetector.add_detected_language_commands(speechSequence)

		speechSequence = inject_langchange_reorder(speechSequence)

		speechSequence = deduplicate_language_command(speechSequence)
		speechSequence = lang_cmd_to_voice(
			speechSequence=speechSequence,
			voice_manager=self._voiceManager,
			default_instance=self._voiceManager.defaultVoiceInstance,
		)

		chunks = []
		hasText = False
		charMode = False

		voiceInstance = self._voiceManager.defaultVoiceInstance
		for command in speechSequence:
			if voiceInstance.engine == "VE":
				if isinstance(command, str):
					command = command.strip()
					if not command:
						continue
					# If character mode is on use lower case characters
					# Because the synth does not allow to turn off the caps reporting
					if charMode or len(command) == 1:
						command = command.lower()
					# replace the escape character since it is used for parameter changing
					chunks.append(command.replace('\x1b', ''))
					hasText = True
				elif isinstance(command, IndexCommand):
					# start and end The spaces here seem to be important
					chunks.append(f"\x1b\\mrk={command.index}\\")
				elif isinstance(command, BreakCommand):
					voiceInstance.speak(speech.CHUNK_SEPARATOR.join(chunks).replace("  \x1b", "\x1b"))
					chunks = []
					hasText = False
					voiceInstance.breaks(command.time)
					# chunks.append(f"\x1b\\pause={breakTime}\\")
				elif isinstance(command, RateCommand):
					boundedValue = max(0, min(command.newValue, 100))
					factor = 25.0 if boundedValue >= 50 else 50.0
					norm = 2.0 ** ((boundedValue - 50.0) / factor)
					value = int(round(norm * 100))
					chunks.append(f"\x1b\\rate={value}\\")
				elif isinstance(command, PitchCommand):
					boundedValue = max(0, min(command.newValue, 100))
					factor = 50.0
					norm = 2.0 ** ((boundedValue - 50.0) / factor)
					value = int(round(norm * 100))
					chunks.append(f"\x1b\\pitch={value}\\")
				elif isinstance(command, VolumeCommand):
					value = max(0, min(command.newValue, 100))
					chunks.append(f"\x1b\\vol={value}\\")
				elif isinstance(command, CharacterModeCommand):
					charMode = command.state
					s = "\x1b\\tn=spell\\" if command.state else "\x1b\\tn=normal\\"
					# s = " \x1b\\tn=spell\\ " if command.state else " \x1b\\tn=normal\\ "
					chunks.append(s)
				elif isinstance(command, SplitCommand):
					voiceInstance.speak(speech.CHUNK_SEPARATOR.join(chunks).replace("  \x1b", "\x1b"))
					chunks = []
					hasText = False
				elif isinstance(command, Voice):
					newInstance = command
					if hasText:  # We changed voice, send what we already have to vocalizer.
						voiceInstance.speak(speech.CHUNK_SEPARATOR.join(chunks).replace("  \x1b", "\x1b"))
					chunks = []
					hasText = False
					voiceInstance = newInstance
				elif isinstance(command, SpeechCommand):
					log.debugWarning("Unsupported speech command: %s" % command)
				else:
					log.error("Unknown speech: %s" % command)
			elif voiceInstance.engine == "Aisound":
				item = command
				if isinstance(item, str):
					if charMode:
						text = ' '.join([x for x in item])
					else:
						text = item
					voiceInstance.speak(text)
				elif isinstance(item, IndexCommand):
					voiceInstance.index(item.index)
				elif isinstance(item, CharacterModeCommand):
					charMode = item.state
				elif isinstance(command, Voice):
					newInstance = command
					charMode = False
					voiceInstance = newInstance
				elif isinstance(item, SpeechCommand):
					log.debugWarning("Unsupported speech command: %s" % item)
				else:
					log.error("Unknown speech: %s" % item)
			elif voiceInstance.engine in ["OneCore", "RH", "Espeak", "piper", "IBM", "SAPI5"]:
				if isinstance(command, Voice):
					newInstance = command
					voiceInstance.speak(chunks)
					chunks = []
					voiceInstance = newInstance
				else:
					chunks.append(command)

		if voiceInstance.engine in ["VE", "Aisound"]:
			if chunks:
				voiceInstance.speak(speech.CHUNK_SEPARATOR.join(chunks).replace("  \x1b", "\x1b"))
		elif voiceInstance.engine in ["OneCore", "RH", "Espeak", "piper", "IBM", "SAPI5"]:
			voiceInstance.speak(chunks)

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
		if switch:
			self._voiceManager.defaultVoiceInstance.pause()
		else:
			self._voiceManager.defaultVoiceInstance.resume()

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

	def _get_rateBoost(self):
		return self._voiceManager.defaultVoiceInstance.rateBoost

	def _set_rateBoost(self, enable):
		self._voiceManager.defaultVoiceInstance.rateBoost = enable

	def _get_uwv(self):
		return self._uwv

	def _set_uwv(self, value):
		self._uwv = value
		self.detect_language_timing()

	def detect_language_timing(self):
		if self.uwv and config.conf["WorldVoice"]['autoLanguageSwitching']['DetectLanguageTiming'] == 'before':
			filter_speechSequence.register(self._languageDetector.add_detected_language_commands)
			order_move_to_start_register()
		else:
			filter_speechSequence.unregister(self._languageDetector.add_detected_language_commands)

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
		self._voiceManager.waitfactor = value
		config.conf["WorldVoice"]["pipeline"]["global_wait_factor"] = self.globalwaitfactor

	def _get_numberwaitfactor(self):
		return self._numberwaitfactor

	def _set_numberwaitfactor(self, value):
		self._numberwaitfactor = value
		config.conf["WorldVoice"]["pipeline"]["number_wait_factor"] = self.numberwaitfactor

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

	def patchedLengthSpeechSequence(self, speechSequence):
		result = []
		for command in speechSequence:
			if isinstance(command, str):
				result.extend(self.lengthsplit(command, 100))
			else:
				result.append(command)
		return result

	def lengthsplit(self, string, length):
		result = []
		pattern = re.compile(r"[\s]")
		spaces = pattern.findall(string)
		others = pattern.split(string)
		fragment = ""
		for other, space in zip(others, spaces):
			fragment += other + space
			if len(fragment) > length:
				result.append(fragment)
				result.append(SplitCommand())
				fragment = ""
		fragment += others[-1]
		result.append(fragment)
		return result

	def _getLocaleReadableName(self, locale):
		description = languageHandler.getLanguageDescription(locale)
		return "%s" % (description) if description else locale
