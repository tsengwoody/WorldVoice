import os
import re
import sys
base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
addon_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
synth_drivers_path = os.path.join(addon_path, 'synthDrivers', 'WorldVoiceXVED2')
sys.path.insert(0, base_dir)

from collections import OrderedDict

import addonHandler
from autoSettingsUtils.driverSetting import BooleanDriverSetting, DriverSetting, NumericDriverSetting
from autoSettingsUtils.utils import StringParameterInfo
import config
from synthDriverHandler import SynthDriver, VoiceInfo, synthIndexReached, synthDoneSpeaking
import languageHandler
from logHandler import log
import speech

from ._voiceManager import VoiceManager
from . import languageDetection
from . import _config
from generics.speechSymbols.models import SpeechSymbols
from generics.synthDrivers import WorldVoiceBaseSynthDriver
from . import speechcommand

try:
	from speech import IndexCommand, CharacterModeCommand, LangChangeCommand, BreakCommand, PitchCommand, RateCommand, VolumeCommand
except:
	from speech.commands import IndexCommand, CharacterModeCommand, LangChangeCommand, BreakCommand, PitchCommand, RateCommand, VolumeCommand

number_pattern = re.compile(r"[0-9]+[0-9.:]*[0-9]+|[0-9]")
comma_number_pattern = re.compile(r"(?<=[0-9]),(?=[0-9])")
chinese_space_pattern = re.compile(r"(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])")

addonHandler.initTranslation()

class SynthDriver(WorldVoiceBaseSynthDriver, SynthDriver):
	name = "WorldVoiceXVED2"
	description = "WorldVoice(VE)"
	supportedSettings = [
		SynthDriver.VoiceSetting(),
		# SynthDriver.VariantSetting(),
		SynthDriver.RateSetting(),
		SynthDriver.PitchSetting(),
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
			"chinesespace",
			# Translators: Label for a setting in voice settings dialog.
			_("Pause time when encountering spaces between Chinese"),
			defaultVal=0,
			minStep=1,
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
		with VoiceManager.preOpen() as check:
			return check

	def __init__(self):
		# Initialize the driver
		self._voiceManager = VoiceManager(self._onIndexReached)
		log.debug("Vocalizer info: %s" % self._info())
		if config.conf["WorldVoice"]['autoLanguageSwitching']['DetectLanguageTiming'] == 'before':
			try:
				self._realSpeakFunc = speech.speech.speak
				speech.speech.speak = self.patchedSpeak
			except:
				self._realSpeakFunc = speech.speak
				speech.speak = self.patchedSpeak
		else:
			try:
				self._realSpeakFunc = speech.speech.speak
			except:
				self._realSpeakFunc = speech.speak

		try:
			self._realSpellingFunc = speech.speech.speakSpelling
			speech.speech.speakSpelling = self.patchedSpeakSpelling
			from speech.sayAll import initialize as sayAllInitialize
			sayAllInitialize(
				speech.speech.speak,
				speech.speech.speakObject,
				speech.speech.getTextInfoSpeech,
				speech.speech.SpeakTextInfoState,
			)
		except:
			self._realSpellingFunc = speech.speakSpelling
			speech.speakSpelling = self.patchedSpeakSpelling
			speech._speakWithoutPauses = speech.SpeechWithoutPauses(speakFunc=self.patchedSpeak)
			speech.speakWithoutPauses = speech._speakWithoutPauses.speakWithoutPauses

		self.speechSymbols = SpeechSymbols()
		self.speechSymbols.load('unicode.dic')
		self._languageDetector = languageDetection.LanguageDetector(list(self._voiceManager.languages), self.speechSymbols)

		self._localeToVoices = self._voiceManager.localeToVoicesMap
		self._locales = sorted([l for l in self._localeToVoices if len(self._localeToVoices[l]) > 0])
		self._localeNames = list(map(self._getLocaleReadableName, self._locales))

		self._voice = None

	def loadSettings(self, onlyChanged=False):
		super().loadSettings(onlyChanged)
		self._voiceManager.reload()

	def _onIndexReached(self, index):
		if index is not None:
			synthIndexReached.notify(synth=self, index=index)
		else:
			synthDoneSpeaking.notify(synth=self)

	def terminate(self):
		if config.conf["WorldVoice"]['autoLanguageSwitching']['DetectLanguageTiming'] == 'before':
			try:
				speech.speech.speak = self._realSpeakFunc
				speech.speech.speakSpelling = self._realSpellingFunc
			except:
				speech.speak = self._realSpeakFunc
				speech.speakSpelling = self._realSpellingFunc
				speech._speakWithoutPauses = speech.SpeechWithoutPauses(speakFunc=speech.speak)
				speech.speakWithoutPauses = speech._speakWithoutPauses.speakWithoutPauses

		try:
			self.cancel()
			self._voiceManager.close()
		except RuntimeError:
			log.error("Vocalizer terminate", exc_info=True)

	def speak(self, speechSequence):
		if config.conf["WorldVoice"]['autoLanguageSwitching']['DetectLanguageTiming'] == 'after':
			if self._cni:
				speechSequence = [comma_number_pattern.sub(lambda m:'', command) if isinstance(command, str) else command for command in speechSequence]
			speechSequence = self.patchedNumSpeechSequence(speechSequence)
			if self.uwv \
				and config.conf["WorldVoice"]['autoLanguageSwitching']['useUnicodeLanguageDetection']:
				speechSequence = self._languageDetector.add_detected_language_commands(speechSequence)
				speechSequence = list(speechSequence)

		speechSequence = self.patchedSpaceSpeechSequence(speechSequence)

		voiceInstance = defaultInstance = self._voiceManager.defaultVoiceInstance
		currentLanguage = defaultLanguage = self.language
		chunks = []
		charMode = False
		hasText = False

		for command in speechSequence:
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
			# elif isinstance(command, PitchCommand):
				# pitch = voiceInstance._pitch
				# pitchOffset = self._percentToParam(command.offset, _vocalizer.PITCH_MIN, _vocalizer.PITCH_MAX) - _vocalizer.PITCH_MIN
				# chunks.append("\x1b\\pitch=%d\\" % (pitch+pitchOffset))
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
			elif isinstance(command, LangChangeCommand) or isinstance(command, speechcommand.WVLangChangeCommand):
				if command.lang == currentLanguage:
					# Keep on the same voice.
					continue
				if command.lang is None:
					# No language, use default.
					voiceInstance = defaultInstance
					currentLanguage = defaultLanguage
					continue
				# Changed language, lets see what we have.
				newInstance = self._voiceManager.getVoiceInstanceForLanguage(command.lang)
				currentLanguage = command.lang
				if newInstance is None:
					# No voice for this language, use default.
					newInstance = defaultInstance
				if newInstance == voiceInstance:
					# Same voice, next command.
					continue
				if hasText: # We changed voice, send what we already have to vocalizer.
					voiceInstance.speak(speech.CHUNK_SEPARATOR.join(chunks).replace("  \x1b", "\x1b"))
					chunks = []
					hasText = False
				voiceInstance = newInstance
			elif isinstance(command, speechcommand.SplitCommand):
				self._speak(voiceInstance.token, chunks)
				chunks = []
				hasText = False

		if chunks:
			voiceInstance.speak(speech.CHUNK_SEPARATOR.join(chunks).replace("  \x1b", "\x1b"))

	def patchedSpeak(self, speechSequence, symbolLevel=None, priority=None):
		if config.conf["WorldVoice"]['autoLanguageSwitching']['DetectLanguageTiming'] == 'before':
			if self._cni:
				speechSequence = [comma_number_pattern.sub(lambda m:'', command) if isinstance(command, str) else command for command in speechSequence]
			speechSequence = self.patchedNumSpeechSequence(speechSequence)
			if self.uwv \
				and config.conf["WorldVoice"]['autoLanguageSwitching']['useUnicodeLanguageDetection']:
				speechSequence = self._languageDetector.add_detected_language_commands(speechSequence)
				speechSequence = list(speechSequence)
		self._realSpeakFunc(speechSequence, symbolLevel, priority=priority)

	def patchedSpeakSpelling(self, text, locale=None, useCharacterDescriptions=False, priority=None):
		if self.uwv \
			and config.conf["WorldVoice"]['autoLanguageSwitching']['useUnicodeLanguageDetection'] \
			and config.conf["speech"]["trustVoiceLanguage"]:
				for text, loc in self._languageDetector.process_for_spelling(text, locale):
					self._realSpellingFunc(text, loc, useCharacterDescriptions, priority=priority)
		else:
			self._realSpellingFunc(text, locale, useCharacterDescriptions, priority=priority)

	def cancel(self):
		self._voiceManager.defaultVoiceInstance.stop()

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
		self._voiceManager.setDefaultVoice(voiceName)
		if config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleVoiceConsistent"]:
			locale = self._voiceManager.defaultVoiceInstance.language if self._voiceManager.defaultVoiceInstance.language else languageHandler.getLanguage()
			if not locale in config.conf["WorldVoice"]["autoLanguageSwitching"]:
				config.conf["WorldVoice"]["autoLanguageSwitching"][locale] = {}
			config.conf["WorldVoice"]["autoLanguageSwitching"][locale]['voice'] = self._voiceManager.defaultVoiceInstance.name
			locale = locale.split("_")[0]
			if not locale in config.conf["WorldVoice"]["autoLanguageSwitching"]:
				config.conf["WorldVoice"]["autoLanguageSwitching"][locale] = {}
			config.conf["WorldVoice"]["autoLanguageSwitching"][locale]['voice'] = self._voiceManager.defaultVoiceInstance.name

		# Available variants are cached by default. As variants maybe different for each voice remove the cached value
		# if hasattr(self, '_availableVariants'):
			# del self._availableVariants
		# Synchronize with the synth so the parameters
		# we report are not from the previous voice.
		# _vocalizer.sync()

	def _get_variant(self):
		return self._voiceManager.defaultVoiceInstance.variant

	def _set_variant(self, name):
		self.cancel()
		self._voiceManager.defaultVoiceInstance.variant = name

	def _getAvailableVariants(self):
		dbs = self._voiceManager.defaultVoiceInstance.variants
		return OrderedDict([(d, VoiceInfo(d, d)) for d in dbs])

	def _get_availableLanguages(self):
		return self._voiceManager.languages

	def _get_language(self):
		return self._voiceManager.getVoiceLanguage()

	def _info(self):
		s = [self.description]
		return ", ".join(s)

	def _get_availableNumlans(self):
		return dict({
			"default": StringParameterInfo("default", _("default")),
		}, **{
			locale: StringParameterInfo(locale, name) for locale, name in zip(self._locales, self._localeNames)
		})

	def _get_numlan(self):
		return self._numlan

	def _set_numlan(self,value):
		self._numlan = value

	def _get_availableNummods(self):
		return dict({
			"value": StringParameterInfo("value", _("value")),
			"number": StringParameterInfo("number", _("number")),
		})

	def _get_nummod(self):
		return self._nummod

	def _set_nummod(self,value):
		self._nummod = value

	def _get_chinesespace(self):
		return self._chinesespace

	def _set_chinesespace(self,value):
		self._chinesespace = value

	def _get_cni(self):
		return self._cni

	def _set_cni(self,value):
		self._cni = value

	def _getLocaleReadableName(self, locale):
		description = languageHandler.getLanguageDescription(locale)
		return "%s" % (description) if description else locale
