from collections import OrderedDict
import os
import re
import sys
import unicodedata

import addonHandler
from autoSettingsUtils.driverSetting import BooleanDriverSetting, DriverSetting, NumericDriverSetting
from autoSettingsUtils.utils import StringParameterInfo
import config
import extensionPoints
import languageHandler
from logHandler import log
import speech
from speech.commands import IndexCommand, CharacterModeCommand, LangChangeCommand, BreakCommand, PitchCommand, RateCommand, VolumeCommand, PhonemeCommand, SpeechCommand
from speech.sayAll import initialize as sayAllInitialize
from synthDriverHandler import SynthDriver, synthIndexReached, synthDoneSpeaking

from . import languageDetection
from ._speechcommand import SplitCommand, WVLangChangeCommand
from .voice import Voice
from .voiceManager import VoiceManager

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, base_dir)
from generics.speechSymbols.models import SpeechSymbols

number_pattern = re.compile(r"[0-9\-\+]+[0-9.:]*[0-9]+|[0-9]")
comma_number_pattern = re.compile(r"(?<=[0-9]),(?=[0-9])")
chinese_space_pattern = re.compile(r"(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])")

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
WVConfigure = extensionPoints.Action()


class SynthDriver(SynthDriver):
	name = "WorldVoice"
	description = "WorldVoice"
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
			"chinesespacewaitfactor",
			# Translators: Label for a setting in voice settings dialog.
			_("Chinese space wait factor"),
			availableInSettingsRing=True,
			defaultVal=0,
			minStep=1,
		),
		# '''DriverSetting(
		#	"speechcommandsgenerate",
		#	_("SpeechCommands generate timing"),
		#	defaultVal="BNP",
		#),
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
		return VoiceManager.ready()

	def __init__(self):
		self._voiceManager = VoiceManager()
		self._voiceManager.waitfactor = config.conf["WorldVoice"]["other"]["WaitFactor"]
		if self._voiceManager.voice_class["OneCore"].core:
			self._voiceManager.voice_class["OneCore"].core.rateBoost = config.conf["WorldVoice"]["other"]["RateBoost"]

		if config.conf["WorldVoice"]["autoLanguageSwitching"]["DetectLanguageTiming"] == 'before':
			self._realSpeakFunc = speech.speech.speak
			speech.speech.speak = self.patchedSpeak
		else:
			self._realSpeakFunc = speech.speech.speak

		self._realSpellingFunc = speech.speech.speakSpelling
		speech.speech.speakSpelling = self.patchedSpeakSpelling

		sayAllInitialize(
			speech.speech.speak,
			speech.speech.speakObject,
			speech.speech.getTextInfoSpeech,
			speech.speech.SpeakTextInfoState,
		)

		self.speechSymbols = SpeechSymbols()
		self.speechSymbols.load('unicode.dic')
		self._languageDetector = languageDetection.LanguageDetector(list(self._voiceManager.languages), self.speechSymbols)

		self._locales = self._voiceManager.languages
		self._localeNames = list(map(self._getLocaleReadableName, self._locales))

		self._voice = None

		WVStart.notify()

	def loadSettings(self, onlyChanged=False):
		super().loadSettings(onlyChanged)
		self._voiceManager.reload()

	def terminate(self):
		if config.conf["WorldVoice"]["autoLanguageSwitching"]["DetectLanguageTiming"] == 'before':
			speech.speech.speak = self._realSpeakFunc

		speech.speech.speakSpelling = self._realSpellingFunc

		sayAllInitialize(
			speech.speech.speak,
			speech.speech.speakObject,
			speech.speech.getTextInfoSpeech,
			speech.speech.SpeakTextInfoState,
		)

		try:
			self.cancel()
			self._voiceManager.terminate()
		except RuntimeError:
			log.error("Vocalizer terminate", exc_info=True)

		WVEnd.notify()

	def speak(self, speechSequence):
		if config.conf["WorldVoice"]['autoLanguageSwitching']['DetectLanguageTiming'] == 'after':
			if self._cni:
				speechSequence = [comma_number_pattern.sub(lambda m:'', command) if isinstance(command, str) else command for command in speechSequence]
			if self._itemwaitfactor > 0:
				speechSequence = self.patchedStrItemSpeechSequence(speechSequence)
			if self._chinesespacewaitfactor > 0:
				speechSequence = self.patchedChineseSpaceWaitFactorSpeechSequence(speechSequence)
			speechSequence = self.patchedNumLangSpeechSequence(speechSequence)
			if self.uwv \
			and config.conf["WorldVoice"]['autoLanguageSwitching']['useUnicodeLanguageDetection']:
				speechSequence = self._languageDetector.add_detected_language_commands(speechSequence)
				speechSequence = list(speechSequence)

		if self._normalization != "OFF":
			self.patchedNormalizationSpeechSequence(speechSequence)

		speechSequence = self.patchedOrderLangChangeCommandSpeechSequence(speechSequence)
		voiceInstance = defaultInstance = self._voiceManager.defaultVoiceInstance
		currentLanguage = defaultLanguage = self.language
		temp = []
		for command in speechSequence:
			if isinstance(command, LangChangeCommand) or isinstance(command, WVLangChangeCommand):
				if command.lang == currentLanguage:
					# Keep on the same voice.
					continue
				# Changed language, lets see what we have.
				if command.lang is None:
					# No language, use default.
					newInstance = defaultInstance
					currentLanguage = defaultLanguage
				else:
					newInstance = self._voiceManager.getVoiceInstanceForLanguage(command.lang)
					currentLanguage = command.lang
					if newInstance is None:
						# No voice for this language, use default.
						newInstance = defaultInstance
				if newInstance == voiceInstance:
					# Same voice, next command.
					continue
				temp.append(newInstance)
				voiceInstance = newInstance
			else:
				temp.append(command)
		speechSequence = temp

		speechSequence = self.patchedSpaceFilterSpaceSpeechSequence(speechSequence)
		speechSequence = self.patchedNumSpaceSpeechSequence(speechSequence)

		chunks = []
		hasText = False
		charMode = False

		textList = []

		# NVDA SpeechCommands are linear, but XML is hierarchical.
		# Therefore, we track values for non-empty tags.
		# When a tag changes, we close all previously opened tags and open new ones.
		tags = {}
		# We have to use something mutable here because it needs to be changed by the inner function.
		tagsChanged = [True]
		openedTags = []

		def outputTags():
			if not tagsChanged[0]:
				return
			for tag in reversed(openedTags):
				textList.append("</%s>" % tag)
			del openedTags[:]
			for tag, attrs in tags.items():
				textList.append("<%s" % tag)
				for attr, val in attrs.items():
					textList.append(' %s="%s"' % (attr, val))
				textList.append(">")
				openedTags.append(tag)
			tagsChanged[0] = False

			if voiceInstance.engine == "SAPI5":
				# Pitch must always be specified in the markup.
				tags["pitch"] = {"absmiddle": voiceInstance._pitch}

		voiceInstance = defaultInstance = self._voiceManager.defaultVoiceInstance
		for command in speechSequence:
			if voiceInstance.engine == "VE":
				if isinstance(command, str):
					# command = command.strip()
					# if not command:
						# continue
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
				elif isinstance(command, voice.Voice):
					newInstance = command
					if hasText:  # We changed voice, send what we already have to vocalizer.
						voiceInstance.speak(speech.CHUNK_SEPARATOR.join(chunks).replace("  \x1b", "\x1b"))
					chunks = []
					hasText = False
					voiceInstance = newInstance
					if voiceInstance.engine == "SAPI5":
						# Pitch must always be specified in the markup.
						tags["pitch"] = {"absmiddle": voiceInstance._pitch}
				elif isinstance(command, SpeechCommand):
					log.debugWarning("Unsupported speech command: %s" % command)
				else:
					log.error("Unknown speech: %s" % command)
			elif voiceInstance.engine == "SAPI5":
				item = command
				if isinstance(item, str):
					outputTags()
					textList.append(item.replace("<", "&lt;"))
				elif isinstance(item, IndexCommand):
					textList.append('<Bookmark Mark="%d" />' % item.index)
				elif isinstance(item, CharacterModeCommand):
					if item.state:
						tags["spell"] = {}
					else:
						try:
							del tags["spell"]
						except KeyError:
							pass
					tagsChanged[0] = True
				elif isinstance(item, BreakCommand):
					textList.append('<silence msec="%d" />' % item.time)
				elif isinstance(item, PitchCommand):
					tags["pitch"] = {"absmiddle": int((voiceInstance.pitch * item.multiplier) // 2 - 25)}
					tagsChanged[0] = True
				elif isinstance(item, VolumeCommand):
					if item.multiplier == 1:
						try:
							del tags["volume"]
						except KeyError:
							pass
					else:
						tags["volume"] = {"level": int(voiceInstance._volume * item.multiplier)}
					tagsChanged[0] = True
				elif isinstance(item, RateCommand):
					if item.multiplier == 1:
						try:
							del tags["rate"]
						except KeyError:
							pass
					else:
						tags["rate"] = {"absspeed": int(voiceInstance._rate * item.multiplier)}
					tagsChanged[0] = True
				elif isinstance(item, PhonemeCommand):
					try:
						textList.append(
							'<pron sym="%s">%s</pron>'
							% (self._convertPhoneme(item.ipa), item.text or "")
						)
					except LookupError:
						log.debugWarning("Couldn't convert character in IPA string: %s" % item.ipa)
						if item.text:
							textList.append(item.text)
				elif isinstance(command, voice.Voice):
					newInstance = command
					tags.clear()
					tagsChanged[0] = True
					outputTags()
					text = "".join(textList)
					voiceInstance.speak(text)
					textList.clear()

					voiceInstance = newInstance
					if voiceInstance.engine == "SAPI5":
						# Pitch must always be specified in the markup.
						tags["pitch"] = {"absmiddle": voiceInstance._pitch}
				elif isinstance(item, SpeechCommand):
					log.debugWarning("Unsupported speech command: %s" % item)
				else:
					log.error("Unknown speech: %s" % item)
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
				elif isinstance(command, voice.Voice):
					newInstance = command
					charMode = False
					voiceInstance = newInstance
					if voiceInstance.engine == "SAPI5":
						# Pitch must always be specified in the markup.
						tags["pitch"] = {"absmiddle": voiceInstance._pitch}
				elif isinstance(item, SpeechCommand):
					log.debugWarning("Unsupported speech command: %s" % item)
				else:
					log.error("Unknown speech: %s" % item)
			elif voiceInstance.engine == "OneCore" or voiceInstance.engine == "RH":
				if isinstance(command, voice.Voice):
					newInstance = command
					voiceInstance.speak(chunks)
					chunks = []
					voiceInstance = newInstance
					if voiceInstance.engine == "SAPI5":
						# Pitch must always be specified in the markup.
						tags["pitch"] = {"absmiddle": voiceInstance._pitch}
				else:
					chunks.append(command)

		if voiceInstance.engine == "VE":
			if chunks:
				voiceInstance.speak(speech.CHUNK_SEPARATOR.join(chunks).replace("  \x1b", "\x1b"))
		elif voiceInstance.engine == "SAPI5":
			tags.clear()
			tagsChanged[0] = True
			outputTags()
			text = "".join(textList)
			voiceInstance.speak(text)
			textList.clear()
		elif voiceInstance.engine == "aisound":
			if chunks:
				voiceInstance.speak(chunks)
		elif voiceInstance.engine == "OneCore" or voiceInstance.engine == "RH":
			voiceInstance.speak(chunks)

	def patchedSpeak(self, speechSequence, symbolLevel=None, priority=None):
		if config.conf["WorldVoice"]['autoLanguageSwitching']['DetectLanguageTiming'] == 'before':
			if self._cni:
				speechSequence = [comma_number_pattern.sub(lambda m:'', command) if isinstance(command, str) else command for command in speechSequence]
			if self._itemwaitfactor > 0:
				speechSequence = self.patchedStrItemSpeechSequence(speechSequence)
			if self._chinesespacewaitfactor > 0:
				speechSequence = self.patchedChineseSpaceWaitFactorSpeechSequence(speechSequence)
			speechSequence = self.patchedNumLangSpeechSequence(speechSequence)
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
		if config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleVoiceConsistent"]:
			locale = self._voiceManager.defaultVoiceInstance.language if self._voiceManager.defaultVoiceInstance.language else languageHandler.getLanguage()
			if locale not in config.conf["WorldVoice"]["speechRole"]:
				config.conf["WorldVoice"]["speechRole"][locale] = {}
			config.conf["WorldVoice"]["speechRole"][locale]['voice'] = self._voiceManager.defaultVoiceInstance.name
			locale = locale.split("_")[0]
			if locale not in config.conf["WorldVoice"]["speechRole"]:
				config.conf["WorldVoice"]["speechRole"][locale] = {}
			config.conf["WorldVoice"]["speechRole"][locale]['voice'] = self._voiceManager.defaultVoiceInstance.name

		if config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleEngineConsistent"]:
			self._voiceManager.engine = self._voiceManager._defaultVoiceInstance.engine
		else:
			self._voiceManager.engine = 'ALL'
		self._voiceManager.onKeepEngineConsistent()

	def _info(self):
		s = [self.description]
		return ", ".join(s)

	def _get_availableNormalizations(self):
		values = OrderedDict([("OFF", StringParameterInfo("OFF", _("OFF")))])
		for form in ("NFC", "NFKC", "NFD", "NFKD"):
			values[form] = StringParameterInfo(form, form)
		return values

	def _get_normalization(self):
		return self._normalization

	def _set_normalization(self, value):
		if value in self.availableNormalizations:
			self._normalization = value

	def _get_availableSpeechcommandsgenerates(self):
		values = OrderedDict([
			("BNP", StringParameterInfo("BNP", _("before NVDA processing"))),
			("ANP", StringParameterInfo("ANP", _("after NVDA processing"))),
		])
		return values

	def _get_speechcommandsgenerate(self):
		return self._speechcommandsgenerate

	def _set_speechcommandsgenerate(self, value):
		if value in self.availableSpeechcommandsgenerates:
			self._speechcommandsgenerate = value

	def _get_availableNumlans(self):
		return dict(
			{
				"default": StringParameterInfo("default", _("default")),
			},
			**{
				locale: StringParameterInfo(locale, name) for locale, name in zip(self._locales, self._localeNames)
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

	def _get_itemwaitfactor(self):
		return self._itemwaitfactor

	def _set_itemwaitfactor(self, value):
		self._itemwaitfactor = value

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

	def patchedNormalizationSpeechSequence(self, speechSequence):
		temp = []
		for command in speechSequence:
			if isinstance(command, str):
				command = unicodedata.normalize(self._normalization, command)
			temp.append(command)
		return temp

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

	def patchedSpaceFilterSpaceSpeechSequence(self, speechSequence):
		# filter blank string
		result = []
		for command in speechSequence:
			if isinstance(command, str):
				if command.strip():
					result.append(command.strip())
			else:
				result.append(command)

		return result

	def patchedNumSpaceSpeechSequence(self, speechSequence):
		numberwaitfactor = self._numberwaitfactor * 5 if self._numberwaitfactor > 0 else 1

		# state0: normal stage
		# state1: encounter number str once
		# state2: encounter blank str
		# state3: encounter number str twice in a row
		'''result = []
		state = 0
		for command in speechSequence:
			if isinstance(command, str):
				if not command.strip():
					if state == 1:
						state = 2
					else:
						state = 0
				else:
					if number_pattern.match(command):
						if state == 2:
							state = 3
						else:
							state = 1
					else:
						state = 0
			else:
				state = 0
			if state == 3:
				state = 1
				result.append(BreakCommand(numberwaitfactor))
				result.append(command)
			else:
				result.append(command)
		speechSequence = result'''

		# state0: normal stage
		# state1: encounter number str once
		# state2: encounter number str twice in a row
		result = []
		state = 0
		for command in speechSequence:
			if isinstance(command, str):
				if number_pattern.match(command):
					if state == 1:
						state = 2
					else:
						state = 1
				else:
					state = 0
			else:
				state = 0
			if state == 2:
				state = 1
				result.append(BreakCommand(numberwaitfactor))
				result.append(command)
			else:
				result.append(command)
		speechSequence = result

		return speechSequence

	def patchedStrItemSpeechSequence(self, speechSequence):
		result = []
		state = 0
		for command in speechSequence:
			if isinstance(command, str):
				if state == 1:
					state = 2
				else:
					state = 1
			else:
				state = 0
			if state == 2:
				state = 1
				result.append(BreakCommand(self._itemwaitfactor * 5))
				result.append(command)
			else:
				result.append(command)

		return result

	def patchedNumLangSpeechSequence(self, speechSequence):
		return self.coercionNumberLangChange(speechSequence, self._nummod, self._numlan, self.speechSymbols)

	def patchedChineseSpaceWaitFactorSpeechSequence(self, speechSequence):
		'''joinString = ""
		tempSpeechSequence = []
		for command in speechSequence:
			if not isinstance(command, str):
				tempSpeechSequence.append(joinString)
				tempSpeechSequence.append(command)
				joinString = ""
			else:
				joinString += command
		tempSpeechSequence.append(joinString)
		speechSequence = tempSpeechSequence'''

		tempSpeechSequence = []
		for command in speechSequence:
			if isinstance(command, str):
				result = re.split(chinese_space_pattern, command)
				if len(result) == 1:
					tempSpeechSequence.append(command)
				else:
					temp = []
					for i in result:
						temp.append(i)
						temp.append(BreakCommand(self._chinesespacewaitfactor * 5))
					temp = temp[:-1]
					tempSpeechSequence += temp
			else:
				tempSpeechSequence.append(command)
		speechSequence = tempSpeechSequence
		return speechSequence

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

	def resplit(self, pattern, string, mode, numberLanguage, speechSymbols):
		translate_dict = {}
		for c in "1234567890":
			if speechSymbols and c in speechSymbols.symbols:
				symbol = speechSymbols.symbols[c]
				if symbol.language == numberLanguage or symbol.language == "Windows":
					translate_dict[ord(c)] = symbol.replacement if symbol.replacement else c

		result = []
		numbers = pattern.findall(string)
		others = pattern.split(string)
		for other, number in zip(others, numbers):
			dot_count = len(number.split("."))
			if mode == 'value':
				number_str = number
			elif mode == 'number':
				number_str = ' '.join(number).replace(" . ", ".")

			if dot_count > 2 or mode == 'number':
				nodot_str = number_str.split(".")
				temp = ""
				for n, d in zip(nodot_str, ["."] * (len(nodot_str) - 1)):
					if len(n) == 1 or "number":
						n = n.translate(translate_dict)
					temp = temp + n + d
				n = nodot_str[-1]
				if len(n) == 1 or "number":
					n = n.translate(translate_dict)
				temp = temp + n
				number_str = temp

				number_str = number_str.replace(".", config.conf["WorldVoice"]["other"]["numberDotReplacement"])

			result.extend([other, WVLangChangeCommand('StartNumber'), number_str, WVLangChangeCommand('EndNumber')])
		result.append(others[-1])
		return result

	def coercionNumberLangChange(self, speechSequence, mode, numberLanguage, speechSymbols):
		result = []
		for command in speechSequence:
			if isinstance(command, str):
				result.extend(self.resplit(number_pattern, command, mode, numberLanguage, speechSymbols))
			else:
				result.append(command)

		currentLang = self.language
		for command in result:
			if isinstance(command, WVLangChangeCommand):
				if command.lang == 'StartNumber':
					command.lang = numberLanguage if numberLanguage != 'default' else self.language
				elif command.lang == 'EndNumber':
					command.lang = currentLang
				else:
					currentLang = command.lang
		return result

	def _getLocaleReadableName(self, locale):
		description = languageHandler.getLanguageDescription(locale)
		return "%s" % (description) if description else locale
