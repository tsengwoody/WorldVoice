import codecs
import collections
import os

import addonHandler
import globalVars
import languageHandler
from logHandler import log

addonHandler.initTranslation()

base_path = globalVars.appArgs.configPath

SPEECH_SYMBOL_LANGUAGE_LABELS = dict(languageHandler.getAvailableLanguages())

SYMMOD_CONTEXT = 0
SYMMOD_FORCE = 1

SPEECH_SYMBOL_MODE_LABELS = {
		SYMMOD_CONTEXT: _("context"),
		SYMMOD_FORCE: _("force"),
}


class SpeechSymbol(object):
	__slots__ = ("identifier", "replacement", "language", "mode", "displayName")

	def __init__(self, identifier, replacement=None, language=None, mode=None, displayName=None):
		self.identifier = identifier
		self.replacement = replacement
		self.language = language
		self.mode = mode
		self.displayName = displayName

	def __repr__(self):
		attrs = []
		for attr in self.__slots__:
			attrs.append("{name}={val!r}".format(
				name=attr, val=getattr(self, attr)))
		return "SpeechSymbol(%s)" % ", ".join(attrs)


class SpeechSymbols(object):
	"""
	Contains raw information about the pronunciation of symbols.
	It does not handle inheritance of data from other sources, processing of text, etc.
	This is all handled by L{SpeechSymbolProcessor}.
	"""

	def __init__(self):
		"""Constructor.
		"""
		self.symbols = collections.OrderedDict()
		self.fileName = None
		self.localesToNames = dict(languageHandler.getAvailableLanguages())

	def load(self, fileName):
		"""Load symbol information from a file.
		@param fileName: The name of the file from which to load symbol information.
		@type fileName: str
		@raise IOError: If the file cannot be read.
		"""
		self.fileName = os.path.join(base_path, fileName)
		if not os.path.exists(self.fileName):
			with codecs.open(self.fileName, 'w', encoding='utf-8') as f:
				f.write("")
		with codecs.open(self.fileName, "r", "utf_8_sig", errors="replace") as f:
			handler = self._loadSymbol
			for line in f:
				if line.isspace() or line.startswith("#"):
					# Whitespace or comment.
					continue
				line = line.rstrip("\r\n")
				try:
					handler(line)
				except ValueError:
					log.warning(u"Invalid line in file {file}: {line}".format(
						file=fileName, line=line))

	def _loadSymbolField(self, input, inputMap=None):
		if input == "-":
			# Default.
			return None
		if not inputMap:
			return input
		try:
			return inputMap[input]
		except KeyError:
			raise ValueError

	IDENTIFIER_ESCAPES_INPUT = {
		"0": "\0",
		"t": "\t",
		"n": "\n",
		"r": "\r",
		"f": "\f",
		"v": "\v",
		"#": "#",
		"\\": "\\",
	}
	IDENTIFIER_ESCAPES_OUTPUT = {v: k for k, v in IDENTIFIER_ESCAPES_INPUT.items()}
	MODE_INPUT = {
		"context": SYMMOD_CONTEXT,
		"force": SYMMOD_FORCE,
	}
	MODE_OUTPUT = {v: k for k, v in MODE_INPUT.items()}

	def _loadSymbol(self, line):
		line = line.split("\t")
		identifier = replacement = language = mode = displayName = None
		if line[-1].startswith("#"):
			# Regardless of how many fields there are,
			# if the last field is a comment, it is the display name.
			displayName = line[-1][1:].lstrip()
			del line[-1]
		line = iter(line)
		try:
			identifier = next(line)
			if not identifier:
				# Empty identifier is not allowed.
				raise ValueError
			replacement = self._loadSymbolField(next(line))
		except StopIteration:
			# These fields are mandatory.
			raise ValueError
		try:
			language = self._loadSymbolField(next(line))
			mode = self._loadSymbolField(next(line), self.MODE_INPUT)
		except StopIteration:
			# These fields are optional. Defaults will be used for unspecified fields.
			pass
		if not displayName:
			displayName = identifier
		self.symbols[identifier] = SpeechSymbol(identifier, replacement, language, mode, displayName)

	def save(self, fileName=None):
		"""Save symbol information to a file.
		@param fileName: The name of the file to which to save symbol information,
			C{None} to use the file name last passed to L{load} or L{save}.
		@type fileName: str
		@raise IOError: If the file cannot be written.
		@raise ValueError: If C{fileName} is C{None}
			and L{load} or L{save} has not been called.
		"""
		if fileName:
			self.fileName = fileName
		elif self.fileName:
			fileName = self.fileName
		else:
			raise ValueError("No file name")

		with codecs.open(fileName, "w", "utf_8_sig", errors="replace") as f:
			if self.symbols:
				for symbol in self.symbols.values():
					f.write(u"%s\r\n" % self._saveSymbol(symbol))

	def _saveSymbolField(self, output, outputMap=None):
		if output is None:
			return "-"
		if not outputMap:
			return output
		try:
			return outputMap[output]
		except KeyError:
			raise ValueError

	def _saveSymbol(self, symbol):
		identifier = symbol.identifier
		try:
			identifier = u"\\%s%s" % (
				self.IDENTIFIER_ESCAPES_OUTPUT[identifier[0]], identifier[1:])
		except KeyError:
			pass
		fields = [identifier,
			self._saveSymbolField(symbol.replacement),
			self._saveSymbolField(symbol.language),
			self._saveSymbolField(symbol.mode, self.MODE_OUTPUT)
		]
		# Strip optional fields with default values.
		for field in reversed(fields[2:]):
			if field == "-":
				del fields[-1]
			else:
				# This field specifies a value, so no more fields can be stripped.
				break
		if symbol.displayName:
			fields.append("# %s" % symbol.displayName)
		return u"\t".join(fields)

	def updateSymbol(self, symbol):
		self.symbols[symbol.identifier] = symbol

	def deleteSymbol(self, symbol):
		del self.symbols[symbol.identifier]
