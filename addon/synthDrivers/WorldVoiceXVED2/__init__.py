from collections import OrderedDict
import config
from synthDriverHandler import SynthDriver, VoiceInfo, synthIndexReached, synthDoneSpeaking
import languageHandler
from logHandler import log
import speech

from . import _vocalizer
from . import languageDetection
from . import _config

import addonHandler
addonHandler.initTranslation()

import re
import driverHandler

VOICE_PARAMETERS = [
	(_vocalizer.VE_PARAM_VOICE_OPERATING_POINT, "variant", str),
	(_vocalizer.VE_PARAM_SPEECHRATE, "rate", int),
	(_vocalizer.VE_PARAM_PITCH, "pitch", int),
	(_vocalizer.VE_PARAM_VOLUME, "volume", int),
]

number_pattern = re.compile(r"[0-9]+[0-9.:]*[0-9]+|[0-9]")
chinese_space_pattern = re.compile(r"(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])")

english_number = {
	ord("0"): "zero",
	ord("1"): "one",
	ord("2"): "two",
	ord("3"): "three",
	ord("4"): "four",
	ord("5"): "five",
	ord("6"): "six",
	ord("7"): "seven",
	ord("8"): "eight",
	ord("9"): "nine",
	# ord("."): "dot",
}
english_number = {key: " {} ".format(value) for key, value in english_number.items()}
chinese_number = {
	ord("0"): u"\u96f6",
	ord("1"): u"\u4e00",
	ord("2"): u"\u4e8c",
	ord("3"): u"\u4e09",
	ord("4"): u"\u56db",
	ord("5"): u"\u4e94",
	ord("6"): u"\u516d",
	ord("7"): u"\u4e03",
	ord("8"): u"\u516b",
	ord("9"): u"\u4e5d",
	ord("."): u"\u9ede",
}

class SynthDriver(SynthDriver):
	name = "WorldVoiceXVED2"
	description = "WorldVoiceXVE(driver 2)"

	supportedSettings = [
		SynthDriver.VoiceSetting(),
		# SynthDriver.VariantSetting(),
		SynthDriver.RateSetting(),
		SynthDriver.PitchSetting(),
		SynthDriver.VolumeSetting(),
		driverHandler.DriverSetting(
			"num",
			# Translators: Label for a setting in voice settings dialog.
			_("&Number Mode"),
			availableInSettingsRing=True,
			# Translators: Label for a setting in synth settings ring.
			displayName=_("Number Mode"),
		),
		driverHandler.NumericDriverSetting(
			"chinesespace",
			# Translators: Label for a setting in voice settings dialog.
			_("&Chinese Space Break"),
			minStep=1,
			availableInSettingsRing=True,
			# Translators: Label for a setting in synth settings ring.
			displayName=_("Chinese Space Break"),
		),
		driverHandler.BooleanDriverSetting(
			"dli",
			_("Ignore language information of document"),
		),
	]
	supportedCommands = {
		speech.IndexCommand,
		speech.CharacterModeCommand,
		speech.LangChangeCommand,
	}
	supportedNotifications = {synthIndexReached, synthDoneSpeaking}

	@classmethod
	def check(cls):
		with _vocalizer.preOpenVocalizer() as check:
			return check

	def __init__(self):
		_config.load()
		self._instanceCache = {}
		self._voice = None

		_vocalizer.initialize(self._onIndexReached)
		self._resources = _vocalizer.getAvailableResources()

		self._realSpeakFunc = speech.speak
		self._realSpellingFunc = speech.speakSpelling
		speech.speak = self.patchedSpeak
		speech.speakSpelling = self.patchedSpeakSpelling
		self._languageDetector = languageDetection.LanguageDetector([l.id for l in self._resources])
		speech._speakWithoutPauses = speech.SpeechWithoutPauses(speakFunc=self.patchedSpeak)
		speech.speakWithoutPauses = speech._speakWithoutPauses.speakWithoutPauses

		self._localeToVoices = {}
		with _vocalizer.preOpenVocalizer() as check:
			if check:
				for l, v in _vocalizer.getAvailableResources().items():
					self._localeToVoices[l.id] = v
					if "_" in l.id:
						lang = l.id.split("_")[0]
						if lang not in self._localeToVoices:
							self._localeToVoices[lang] = []
						self._localeToVoices[lang].extend(v)
		self._locales = sorted([l for l in self._localeToVoices if len(self._localeToVoices[l]) > 0])
		self._localeNames = list(map(self._getLocaleReadableName, self._locales))

		self._nummod = "default"
		self._chinesespace = "0"
		self._dli = True

	def getVoiceInstance(self, voiceName):
		try:
			return self._instanceCache[voiceName]
		except KeyError:
			instance, name = _vocalizer.open(voiceName)
			self.onVoiceLoad(voiceName, instance)
			self._instanceCache[name] = instance
			return instance

	def getVoiceNameForLanguage(self, language):
		lang = _config.vocalizerConfig["autoLanguageSwitching"].get(language, None)
		if lang is not None:
			if lang["voice"] in self.availableVoices:
				return lang["voice"]

		for l, voices in self._resources.items():
			if l.id.startswith(language):
				return voices[0].id

	def onVoiceLoad(self, voiceName, instance):
		""" Restores variant and other settings if available, when a voice is loaded."""

		if voiceName in _config.vocalizerConfig['voices']:
			for p, name, t in VOICE_PARAMETERS:
				value = _config.vocalizerConfig['voices'][voiceName].get(name, None)
				if value is None:
					continue
				_vocalizer.setParameter(instance, p, t(value))

	def onVoiceUnload(self, voiceName, instance):
		""" Saves variant to be restored for each voice."""

		if voiceName not in _config.vocalizerConfig['voices']:
			_config.vocalizerConfig['voices'][voiceName] = {}

		for p, name, t in VOICE_PARAMETERS:
			value = _vocalizer.getParameter(instance, p, type_=t)
			_config.vocalizerConfig['voices'][voiceName][name] = value

	def saveSettings(self):
		for voiceName, instance in self._instanceCache.items():
			self.onVoiceUnload(voiceName, instance)
		super().saveSettings()

	def loadSettings(self, onlyChanged=False):
		self.cancel()
		for voiceName, instance in self._instanceCache.items():
			self.onVoiceLoad(voiceName, instance)
		super().loadSettings(onlyChanged)

	def terminate(self):
		speech.speak = self._realSpeakFunc
		speech.speakSpelling = self._realSpellingFunc

		speech._speakWithoutPauses = speech.SpeechWithoutPauses(speakFunc=speech.speak)
		speech.speakWithoutPauses = speech._speakWithoutPauses.speakWithoutPauses

		try:
			self.cancel()
			for voiceName, instance in self._instanceCache.items():
				_vocalizer.close(instance)
			_vocalizer.terminate()
			_config.save() # Flush the configuration file
		except RuntimeError:
			log.error("Vocalizer terminate", exc_info=True)

	def speak(self, speechSequence):
		speechSequence = self.patchedNumSpeechSequence(speechSequence)
		speechSequence = self.patchedSpaceSpeechSequence(speechSequence)

		currentInstance = defaultInstance = self.voiceInstance
		currentLanguage = defaultLanguage = self.language
		chunks = []
		hasText = False
		charMode = False
		for command in speechSequence:
			if isinstance(command, str):
				command = command.strip()
				if not command:
					continue
				# If character mode is on use lower case characters
				# Because the synth does not allow to turn off the caps reporting
				if charMode or len(command) == 1:
					command = command.lower()
				# replace the excape character since it is used for parameter changing
				chunks.append(command.replace("\x1b", ""))
				hasText = True
			elif isinstance(command, speech.IndexCommand):
				chunks.append("\x1b\\mrk=%d\\" % command.index)
			elif isinstance(command, speech.BreakCommand):
				maxTime = 6553 if self.variant == "bet2" else 65535
				breakTime = max(1, min(command.time, maxTime))
				self._speak(currentInstance, chunks)
				chunks = []
				hasText = False
				_vocalizer.processBreak(currentInstance, breakTime)
			elif isinstance(command, speech.CharacterModeCommand):
				charMode = command.state
				s = "\x1b\\tn=spell\\" if command.state else "\x1b\\tn=normal\\"
				chunks.append(s)
			elif isinstance(command, speech.LangChangeCommand):
				if command.lang == currentLanguage:
					# Keep on the same voice.
					continue
				if command.lang is None:
					# No language, use default.
					currentInstance = defaultInstance
					currentLanguage = defaultLanguage
					continue
				# Changed language, lets see what we have.
				currentLanguage = command.lang
				newVoiceName = self.getVoiceNameForLanguage(currentLanguage)
				if newVoiceName is None:
					# No voice for this language, use default.
					newInstance = defaultInstance
				else:
					newInstance = self.getVoiceInstance(newVoiceName)
				if newInstance == currentInstance:
					# Same voice, next command.
					continue
				if hasText: # We changed voice, send text we already have to vocalizer.
					self._speak(currentInstance, chunks)
					chunks = []
					hasText = False
				currentInstance = newInstance
			elif isinstance(command, speech.PitchCommand):
				pitch = _vocalizer.getParameter(currentInstance, _vocalizer.VE_PARAM_PITCH, type_=int)
				pitchOffset = self._percentToParam(command.offset, _vocalizer.PITCH_MIN, _vocalizer.PITCH_MAX) - _vocalizer.PITCH_MIN
				chunks.append("\x1b\\pitch=%d\\" % (pitch+pitchOffset))
		if chunks:
			self._speak(currentInstance, chunks)

	def _speak(self, voiceInstance, chunks):
		text = speech.CHUNK_SEPARATOR.join(chunks).replace("  \x1b", "\x1b")
		_vocalizer.processText2Speech(voiceInstance, text)

	def patchedSpeak(self, speechSequence, symbolLevel=None, priority=None):
		if self._dli:
			speechSequence = self.removeLangChangeCommand(speechSequence)
		if config.conf["speech"]["autoLanguageSwitching"] \
			and _config.vocalizerConfig['autoLanguageSwitching']['useUnicodeLanguageDetection']:
			speechSequence = self._languageDetector.add_detected_language_commands(speechSequence)
		self._realSpeakFunc(speechSequence, symbolLevel, priority=priority)

	def patchedSpeakSpelling(self, text, locale=None, useCharacterDescriptions=False, priority=None):
		if config.conf["speech"]["autoLanguageSwitching"] \
			and _config.vocalizerConfig['autoLanguageSwitching']['useUnicodeLanguageDetection']:
				for text, loc in self._languageDetector.process_for_spelling(text, locale):
					self._realSpellingFunc(text, loc, useCharacterDescriptions, priority=priority)
		else:
			self._realSpellingFunc(text, locale, useCharacterDescriptions, priority=priority)

	def cancel(self):
		_vocalizer.stop()

	def pause(self, switch):
		if switch:
			_vocalizer.pause()
		else:
			_vocalizer.resume()

	def _onIndexReached(self, index):
		if index is not None:
			synthIndexReached.notify(synth=self, index=index)
		else:
			synthDoneSpeaking.notify(synth=self)

	def _get_voiceInstance(self):
		return self.getVoiceInstance(self.voice)

	def _get_volume(self):
		return _vocalizer.getParameter(self.voiceInstance, _vocalizer.VE_PARAM_VOLUME)

	def _set_volume(self, value):
		_vocalizer.setParameter(self.voiceInstance, _vocalizer.VE_PARAM_VOLUME, int(value))

	def _get_rate(self):
		rate = _vocalizer.getParameter(self.voiceInstance, _vocalizer.VE_PARAM_SPEECHRATE)
		return self._paramToPercent(rate, _vocalizer.RATE_MIN, _vocalizer.RATE_MAX)

	def _set_rate(self, value):
		rate = self._percentToParam(value, _vocalizer.RATE_MIN, _vocalizer.RATE_MAX)
		_vocalizer.setParameter(self.voiceInstance, _vocalizer.VE_PARAM_SPEECHRATE, rate)

	def _get_pitch(self):
		pitch = _vocalizer.getParameter(self.voiceInstance, _vocalizer.VE_PARAM_PITCH)
		return self._paramToPercent(pitch, _vocalizer.PITCH_MIN, _vocalizer.PITCH_MAX)

	def _set_pitch(self, value):
		pitch = self._percentToParam(value, _vocalizer.PITCH_MIN, _vocalizer.PITCH_MAX)
		_vocalizer.setParameter(self.voiceInstance, _vocalizer.VE_PARAM_PITCH, pitch)

	def _getAvailableVoices(self):
		voices = []
		for items in self._resources.values():
			voices.extend(items)
		return OrderedDict([(v.id, v) for v in voices])

	def _get_voice(self):
		if self._voice is None:
			self._voice = self.getVoiceNameForLanguage(languageHandler.getLanguage())
			if self._voice is None:
				self._voice = list(self.availableVoices.keys())[0]
		return self._voice

	def _set_voice(self, voiceName):
		if voiceName == self.voice: return
		if voiceName not in self.availableVoices:
			raise RuntimeError()
		self.cancel()
		self._voice = voiceName
		# Available variants are cached by default. As variants maybe different for each voice remove the cached value
		if hasattr(self, "_availableVariants"):
			del self._availableVariants

	def _get_variant(self):
		return _vocalizer.getParameter(self.voiceInstance, _vocalizer.VE_PARAM_VOICE_OPERATING_POINT, type_=str)

	def _set_variant(self, name):
		self.cancel()
		_vocalizer.setParameter(self.voiceInstance, _vocalizer.VE_PARAM_VOICE_OPERATING_POINT, name)

	def _getAvailableVariants(self):
		language = _vocalizer.getParameter(self.voiceInstance, _vocalizer.VE_PARAM_LANGUAGE, type_=str) # FIXME: store language...
		dbs = _vocalizer.getSpeechDBList(language, self.voice)
		return OrderedDict([(d, VoiceInfo(d, d)) for d in dbs])

	def _get_language(self):
		return self.availableVoices[self.voice].language

	def _get_availableNums(self):
		return dict({
			"default": driverHandler.StringParameterInfo("default", _("default")),
			"automatic_number": driverHandler.StringParameterInfo("automatic_number", _("automatic number")),
			"chinese_number": driverHandler.StringParameterInfo("chinese_number", _("chinese number")),
			"english_number": driverHandler.StringParameterInfo("english_number", _("english number")),
		}, **{
			locale + "_number": driverHandler.StringParameterInfo(locale + "_number", _("number ") + name) for locale, name in zip(self._locales, self._localeNames)
		}, **{
			locale + "_value": driverHandler.StringParameterInfo(locale + "_value", _("value ") + name) for locale, name in zip(self._locales, self._localeNames)
		})

	def _get_num(self):
		return self._nummod

	def _set_num(self,value):
		self._nummod = value

	def _get_chinesespace(self):
		return self._chinesespace

	def _set_chinesespace(self,value):
		self._chinesespace = value

	def _get_dli(self):
		return self._dli

	def _set_dli(self,value):
		self._dli = value

	def patchedNumSpeechSequence(self, speechSequence):
		if self._nummod == "automatic_number":
			speechSequence = [number_pattern.sub(lambda m: ' '.join(m.group(0)), command) if isinstance(command, str) else command for command in speechSequence]
		elif self._nummod == "chinese_number":
			speechSequence = [command.translate(chinese_number) if isinstance(command, str) else command for command in speechSequence]
		elif self._nummod == "english_number":
			speechSequence = [command.translate(english_number) if isinstance(command, str) else command for command in speechSequence]
		elif self._nummod.endswith("_number"):
			speechSequence = self.coercionNumberLangChange(speechSequence, self._nummod[:-7], 'number')
		elif self._nummod.endswith("_value"):
			speechSequence = self.coercionNumberLangChange(speechSequence, self._nummod[:-6], 'value')
		return speechSequence

	def patchedSpaceSpeechSequence(self, speechSequence):
		if not int(self._chinesespace) == 0:
			joinString = ""
			tempSpeechSequence = []
			for command in speechSequence:
				if not isinstance(command, str):
					tempSpeechSequence.append(joinString)
					tempSpeechSequence.append(command)
					joinString = ""
				else:
					joinString += command
			tempSpeechSequence.append(joinString)
			speechSequence = tempSpeechSequence

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
							temp.append(speech.BreakCommand(int(self._chinesespace) * 5))
						temp = temp[:-1]
						tempSpeechSequence += temp
				else:
					tempSpeechSequence.append(command)
			speechSequence = tempSpeechSequence
		return speechSequence

	def removeLangChangeCommand(self, speechSequence):
		result = []
		for command in speechSequence:
			if not isinstance(command, speech.LangChangeCommand):
				result.append(command)
		return result


	def resplit(self, pattern, string, mode):
		result = []
		numbers = pattern.findall(string)
		others = pattern.split(string)
		for other, number in zip(others, numbers):
			if mode == 'value':
				result.extend([other, speech.LangChangeCommand('StartNumber'), number, speech.LangChangeCommand('EndNumber')])
			elif mode == 'number':
				result.extend([other, speech.LangChangeCommand('StartNumber'), ' '.join(number), speech.LangChangeCommand('EndNumber')])
		result.append(others[-1])
		return result

	def coercionNumberLangChange(self, speechSequence, numberLanguage, mode):
		result = []
		for command in speechSequence:
			if isinstance(command, str):
				result.extend(self.resplit(number_pattern, command, mode))
			else:
				result.append(command)

		currentLang = self.language
		for command in result:
			if isinstance(command, speech.LangChangeCommand):
				if command.lang == 'StartNumber':
					command.lang = numberLanguage
				elif command.lang == 'EndNumber':
					command.lang = currentLang
				else:
					currentLang = command.lang
		return result

	def _getLocaleReadableName(self, locale):
		description = languageHandler.getLanguageDescription(locale)
		return "%s" % (description) if description else locale
