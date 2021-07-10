import re

import languageHandler

try:
	from speech import LangChangeCommand, BreakCommand
except:
	from speech.commands import LangChangeCommand, BreakCommand

from synthDrivers.WorldVoiceXVED2 import _config
from synthDrivers.WorldVoiceXVED2.speechcommand import WVLangChangeCommand

number_pattern = re.compile(r"[0-9]+[0-9.:]*[0-9]+|[0-9]")
comma_number_pattern = re.compile(r"(?<=[0-9]),(?=[0-9])")
chinese_space_pattern = re.compile(r"(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])")

class WorldVoiceBaseSynthDriver:
	def patchedNumSpeechSequence(self, speechSequence):
		return self.coercionNumberLangChange(speechSequence, self._nummod, self._numlan, self.speechSymbols)

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
				dot_count = dot_count +1
				number_str = ' '.join(number).replace(" . ", ".")

			if dot_count > 2:
				nodot_str = number_str.split(".")
				temp = ""
				for n, d in zip(nodot_str, ["."]*(len(nodot_str) -1)):
					if len(n) == 1 or "number":
						n = n.translate(translate_dict)
					temp = temp +n +d
				n = nodot_str[-1]
				if len(n) == 1 or "number":
					n = n.translate(translate_dict)
				temp = temp +n
				number_str = temp

				number_str = number_str.replace(".", _config.vocalizerConfig["autoLanguageSwitching"]["numberDotReplacement"])

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
					command.lang = numberLanguage
				elif command.lang == 'EndNumber':
					command.lang = currentLang
				else:
					currentLang = command.lang
		return result

	def _getLocaleReadableName(self, locale):
		description = languageHandler.getLanguageDescription(locale)
		return "%s" % (description) if description else locale
