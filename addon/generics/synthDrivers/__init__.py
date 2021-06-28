import re

import driverHandler
import languageHandler
import speech

try:
	from speech import IndexCommand, CharacterModeCommand, LangChangeCommand, BreakCommand, PitchCommand, RateCommand, VolumeCommand
except:
	from speech.commands import IndexCommand, CharacterModeCommand, LangChangeCommand, BreakCommand, PitchCommand, RateCommand, VolumeCommand

number_pattern = re.compile(r"[0-9]+[0-9.:]*[0-9]+|[0-9]")
comma_number_pattern = re.compile(r"(?<=[0-9]),(?=[0-9])")
chinese_space_pattern = re.compile(r"(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])")

class WorldVoiceBaseSynthDriver:

	def patchedSpeak(self, speechSequence, symbolLevel=None, priority=None):
		if self._cni:
			temp = []
			for command in speechSequence:
				if isinstance(command, str):
					temp.append(comma_number_pattern.sub(lambda m:'', command))
				else:
					temp.append(command)
			speechSequence = temp
		if self.uwv \
			and _config.vocalizerConfig['autoLanguageSwitching']['useUnicodeLanguageDetection'] \
			and not _config.vocalizerConfig['autoLanguageSwitching']['afterSymbolDetection']:
			speechSequence = self._languageDetector.add_detected_language_commands(speechSequence)
			speechSequence = list(speechSequence)
		self._realSpeakFunc(speechSequence, symbolLevel, priority=priority)

	def patchedSpeakSpelling(self, text, locale=None, useCharacterDescriptions=False, priority=None):
		if config.conf["speech"]["autoLanguageSwitching"] \
			and _config.vocalizerConfig['autoLanguageSwitching']['useUnicodeLanguageDetection'] \
			and config.conf["speech"]["trustVoiceLanguage"]:
				for text, loc in self._languageDetector.process_for_spelling(text, locale):
					self._realSpellingFunc(text, loc, useCharacterDescriptions, priority=priority)
		else:
			self._realSpellingFunc(text, locale, useCharacterDescriptions, priority=priority)

	def patchedNumSpeechSequence(self, speechSequence):
		return self.coercionNumberLangChange(speechSequence, self._numlan, self._nummod)

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
							temp.append(BreakCommand(int(self._chinesespace) * 5))
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
				result.append(speechcommand.SplitCommand())
				fragment = ""
		fragment += others[-1]
		result.append(fragment)
		return result

	def resplit(self, pattern, string, mode):
		result = []
		numbers = pattern.findall(string)
		others = pattern.split(string)
		for other, number in zip(others, numbers):
			if mode == 'value':
				result.extend([other, LangChangeCommand('StartNumber'), number, LangChangeCommand('EndNumber')])
			elif mode == 'number':
				result.extend([other, LangChangeCommand('StartNumber'), ' '.join(number).replace(" . ", " ."), LangChangeCommand('EndNumber')])
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
			if isinstance(command, LangChangeCommand):
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
