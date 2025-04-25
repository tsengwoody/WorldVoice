from collections import OrderedDict
import os
import re
import sys
from typing import Any

import addonHandler
from autoSettingsUtils.driverSetting import BooleanDriverSetting, DriverSetting, NumericDriverSetting
from autoSettingsUtils.utils import StringParameterInfo
import config
import extensionPoints
import gui
import languageHandler
from logHandler import log
import speech
from speech.commands import IndexCommand, CharacterModeCommand, LangChangeCommand, BreakCommand, PitchCommand, RateCommand, VolumeCommand, SpeechCommand
from speech.extensions import filter_speechSequence
from synthDriverHandler import SynthDriver, synthIndexReached, synthDoneSpeaking
import tones

from . import languageDetection

from .pipeline import (
	ignore_comma_between_number,
	normalization,
	item_wait_factor,
	number_wait_factor,
	remove_space,
	inject_number_langchange,
	inject_chinese_space_pause,
	deduplicate_language_command,
	lang_cmd_to_voice,
)
from ._speechcommand import SplitCommand, WVLangChangeCommand
from .voice import Voice
from .voiceEngine import EngineType
from .voiceManager import VoiceManager
from .VoiceSettingsDialogs import WorldVoiceVoiceSettingsPanel

_: Any

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, base_dir)
from generics.speechSymbols.models import SpeechSymbols

addonHandler.initTranslation()

config.conf.spec["WorldVoice"] = {
	"autoLanguageSwitching": {
		"useUnicodeLanguageDetection": "boolean(default=true)",
		"ignoreNumbersInLanguageDetection": "boolean(default=false)",
		"ignorePunctuationInLanguageDetection": "boolean(default=false)",
		"latinCharactersLanguage": "string(default=en)",
		"CJKCharactersLanguage": "string(default=ja)",
		"DetectLanguageTiming": "string(default=after)",
		"KeepMainLocaleVoiceConsistent": "boolean(default=true)",
		"KeepMainLocaleParameterConsistent": "boolean(default=false)",
		"KeepMainLocaleEngineConsistent": "boolean(default=true)",
	},
	"speechRole": {},
	"engine": {
		eng.name: f"boolean(default={str(eng.default_enabled)})"
		for eng in EngineType
	},
	"other": {
		"WaitFactor": "integer(default=1,min=0,max=9)",
		"RateBoost": "boolean(default=true)",
		"numberDotReplacement": "string(default='.')",
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


def inject_langchange_reorder(speechSequence):
	"""
	Re-order language-change commands so that any LangChangeCommand /
	WVLangChangeCommand is emitted *before* the group of commands and
	text it belongs to.
	* LangChangeCmd ─→ prepend to current buffer, then flush buffer.
	* plain string   ─→ append to buffer, then flush buffer.
	* other commands ─→ just accumulate.
	"""
	buffer: List[SpeechCmd] = []

	for cmd in speechSequence:
		if isinstance(cmd, (LangChangeCommand, WVLangChangeCommand)):
			# 1. put language switch at the *front* of this mini-chunk
			buffer.insert(0, cmd)
			# 2. flush the whole chunk in order
			yield from buffer
			buffer.clear()

		elif isinstance(cmd, str):
			# accumulate text, then flush together with prior controls
			buffer.append(cmd)
			yield from buffer
			buffer.clear()

		else:
			# other control commands: keep buffering
			buffer.append(cmd)

	# flush any trailing commands at end of sequence
	if buffer:
		yield from buffer


def order_move_to_start_register():
	# stack: first in last out
	filter_speechSequence.moveToEnd(number_wait_factor, False)
	filter_speechSequence.moveToEnd(remove_space, False)
	filter_speechSequence.moveToEnd(item_wait_factor, False)

	filter_speechSequence.moveToEnd(inject_chinese_space_pause, False)
	filter_speechSequence.moveToEnd(inject_number_langchange, False)

	filter_speechSequence.moveToEnd(normalization, False)
	filter_speechSequence.moveToEnd(ignore_comma_between_number, False)


def order_move_to_end_register():
	# queue: first in first out
	filter_speechSequence.moveToEnd(ignore_comma_between_number, True)
	filter_speechSequence.moveToEnd(normalization, True)

	filter_speechSequence.moveToEnd(inject_number_langchange, True)
	filter_speechSequence.moveToEnd(inject_chinese_space_pause, True)

	filter_speechSequence.moveToEnd(item_wait_factor, True)
	filter_speechSequence.moveToEnd(remove_space, True)
	filter_speechSequence.moveToEnd(number_wait_factor, True)


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
		if self._voiceManager.defaultVoiceInstance.engine in ["OneCore", "RH", "espeak", "piper"]:
			settings.append(SynthDriver.RateBoostSetting())
		settings.extend([
			SynthDriver.PitchSetting(),
		])
		if self._voiceManager.defaultVoiceInstance.engine in ["aisound"]:
			settings.append(SynthDriver.InflectionSetting())
		settings.extend([
			SynthDriver.VolumeSetting(),
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
			DriverSetting(
				"normalization",
				_("Normalization"),
				defaultVal="OFF",
			),
			BooleanDriverSetting(
				"cni",
				_("Ignore comma between number"),
				defaultVal=False,
			),
			BooleanDriverSetting(
				"uwv",
				_("Enable WorldVoice setting rules to detect text language"),
				availableInSettingsRing=True,
				defaultVal=True,
				displayName=_("Enable WorldVoice rules"),
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
			DriverSetting(
				"normalization",
				_("Normalization"),
				defaultVal="OFF",
			),
			BooleanDriverSetting(
				"cni",
				_("Ignore comma between number"),
				defaultVal=False,
			),
			BooleanDriverSetting(
				"uwv",
				_("Enable WorldVoice setting rules to detect text language"),
				availableInSettingsRing=True,
				defaultVal=True,
				displayName=_("Enable WorldVoice rules"),
			),
		]
		return settings

	def __init__(self):
		self.order = 0
		filter_speechSequence.register(inject_chinese_space_pause)
		filter_speechSequence.register(inject_number_langchange)
		filter_speechSequence.register(remove_space)
		filter_speechSequence.register(number_wait_factor)
		order_move_to_start_register()

		self.OriginVoiceSettingsPanel = gui.settingsDialogs.VoiceSettingsPanel
		gui.settingsDialogs.VoiceSettingsPanel = WorldVoiceVoiceSettingsPanel
		self._voiceManager = VoiceManager()
		self._voiceManager.waitfactor = config.conf["WorldVoice"]["other"]["WaitFactor"]

		self._realSpellingFunc = speech.speech.speakSpelling
		speech.speech.speakSpelling = self.patchedSpeakSpelling

		self.speechSymbols = SpeechSymbols()
		self.speechSymbols.load('unicode.dic')
		self._languageDetector = languageDetection.LanguageDetector(list(self._voiceManager.allLanguages), self.speechSymbols)

		self._voice = None

		WVStart.notify()

	def terminate(self):
		filter_speechSequence.unregister(item_wait_factor)
		filter_speechSequence.unregister(normalization)
		filter_speechSequence.unregister(ignore_comma_between_number)

		filter_speechSequence.unregister(inject_chinese_space_pause)
		filter_speechSequence.unregister(inject_number_langchange)
		filter_speechSequence.unregister(remove_space)
		filter_speechSequence.unregister(number_wait_factor)

		gui.settingsDialogs.VoiceSettingsPanel = self.OriginVoiceSettingsPanel

		speech.speech.speakSpelling = self._realSpellingFunc

		try:
			self.cancel()
			self._voiceManager.terminate()
		except BaseException:
			log.error("WorldVoice terminate", exc_info=True)

		WVEnd.notify()

	def loadSettings(self, onlyChanged=False):
		super().loadSettings(onlyChanged)
		self._voiceManager.reload()

	def speak(self, speechSequence):
		self.order = 0
		if self.uwv and config.conf["WorldVoice"]['autoLanguageSwitching']['DetectLanguageTiming'] == 'after':
			speechSequence = self._languageDetector.add_detected_language_commands(speechSequence)

		# speechSequence = self.patchedOrderLangChangeCommandSpeechSequence(speechSequence)
		inject_langchange_reorder(speechSequence)

		speechSequence = deduplicate_language_command(speechSequence)
		speechSequence = lang_cmd_to_voice(
			speechSequence=speechSequence,
			voice_manager=self._voiceManager,
			default_instance=self._voiceManager.defaultVoiceInstance,
		)

		chunks = []
		hasText = False
		charMode = False

		voiceInstance = defaultInstance = self._voiceManager.defaultVoiceInstance
		for command in speechSequence:
			if voiceInstance.engine == "VE":
				if isinstance(command, str):
					# command = command.strip()
					# if not command:
					# 	continue
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
			elif voiceInstance.engine == "aisound":
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
			elif voiceInstance.engine in ["OneCore", "RH", "espeak", "piper", "IBM", "SAPI5"]:
				if isinstance(command, Voice):
					newInstance = command
					voiceInstance.speak(chunks)
					chunks = []
					voiceInstance = newInstance
				else:
					chunks.append(command)

		if voiceInstance.engine == "VE":
			if chunks:
				voiceInstance.speak(speech.CHUNK_SEPARATOR.join(chunks).replace("  \x1b", "\x1b"))
		elif voiceInstance.engine == "aisound":
			if chunks:
				voiceInstance.speak(chunks)
		elif voiceInstance.engine in ["OneCore", "RH", "espeak", "piper", "IBM", "SAPI5"]:
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

	def _get_availableNormalizations(self):
		values = OrderedDict([("OFF", StringParameterInfo("OFF", _("OFF")))])
		for form in ("NFC", "NFKC", "NFD", "NFKD"):
			values[form] = StringParameterInfo(form, form)
		return values

	def _get_normalization(self):
		return self._normalization

	def _set_normalization(self, value):
		self._normalization = value
		if value != "OFF":
			filter_speechSequence.register(normalization)
			order_move_to_start_register()
		else:
			filter_speechSequence.unregister(normalization)

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

	def _get_uwv(self):
		return self._uwv

	def _set_uwv(self, value):
		self._uwv = value
		if value and config.conf["WorldVoice"]['autoLanguageSwitching']['DetectLanguageTiming'] == 'before':
			filter_speechSequence.register(self._languageDetector.add_detected_language_commands)
			order_move_to_start_register()
		else:
			filter_speechSequence.unregister(self._languageDetector.add_detected_language_commands)

	def _get_itemwaitfactor(self):
		return self._itemwaitfactor

	def _set_itemwaitfactor(self, value):
		self._itemwaitfactor = value
		if value > 0:
			filter_speechSequence.register(item_wait_factor)
			order_move_to_start_register()
		else:
			filter_speechSequence.unregister(item_wait_factor)

	def _get_numberwaitfactor(self):
		return self._numberwaitfactor

	def _set_numberwaitfactor(self, value):
		self._numberwaitfactor = value

	def _get_chinesespacewaitfactor(self):
		return self._chinesespacewaitfactor

	def _set_chinesespacewaitfactor(self, value):
		self._chinesespacewaitfactor = value

	def _get_cni(self):
		return self._cni

	def _set_cni(self, value):
		self._cni = value
		if value:
			filter_speechSequence.register(ignore_comma_between_number)
			order_move_to_start_register()
		else:
			filter_speechSequence.unregister(ignore_comma_between_number)

	def patchedOrderLangChangeCommandSpeechSequence(self, speechSequence):
		stables = []
		unstables = []
		for command in speechSequence:
			if isinstance(command, LangChangeCommand) or isinstance(command, WVLangChangeCommand):
				unstables.insert(0, command)
				stables.extend(unstables)
				unstables.clear()
			elif isinstance(command, str):
				unstables.append(command)
				stables.extend(unstables)
				unstables.clear()
			else:
				unstables.append(command)
		stables.extend(unstables)
		return stables

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
