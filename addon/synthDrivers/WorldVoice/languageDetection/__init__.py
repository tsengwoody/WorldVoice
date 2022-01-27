# -*- coding: utf-8 -*-

from collections import defaultdict
from io import StringIO

from .blocks import BLOCKS, BLOCK_RSHIFT

import config
from logHandler import log
import languageHandler

try:
	from synthDriverHandler import getSynth
except:
	from speech import getSynth

from .._speechcommand import WVLangChangeCommand

BASIC_LATIN = [
    u"en", u"ha", u"so", u"id", u"la", u"sw", u"eu",
    u"nr", u"zu", u"xh", u"ss", u"st", u"tn", u"ts"
]
EXTENDED_LATIN = [
    u"cs", u"af", u"pl", u"hr", u"ro", u"sk", u"sl", u"tr", u"hu", u"az",
    u"et", u"sq", u"ca", u"es", u"gl", u"fr", u"de", u"nl", u"it", u"da", u"is", u"nb", u"sv",
    u"fi", u"lv", u"pt", u"ve", u"lt", u"tl", u"cy", u"vi", "no"
]
ALL_LATIN = BASIC_LATIN + EXTENDED_LATIN

CYRILLIC = [u"ru", u"uk", u"kk", u"uz", u"mn", u"sr", u"mk", u"bg", u"ky"]
ARABIC = [u"ar", u"fa", u"ps", u"ur"]
CJK = [u"zh", u"ja", u"ko"]

SINGLETONS = {
    u"Armenian" : u"hy",
    u"Hebrew" : u"he",
    u"Bengali" : u"bn",
    u"Gurmukhi": u"pa",
    u"Greek" : u"el",
    u"Gujarati" : u"gu",
    u"Oriya" : u"or",
    u"Tamil" : u"ta",
    u"Telugu" : u"te",
    u"Kannada" : u"kn",
    u"Malayalam" : u"ml",
    u"Sinhala" : u"si",
    u"Thai" : u"th",
    u"Lao" : u"lo",
    u"Tibetan" : u"bo",
    u"Burmese" : u"my",
    u"Georgian" : u"ka",
    u"Mongolian" : u"mn-Mong",
    u"Khmer" : u"km",
}

# Config keys to get languages to revert to, when in dobt
_configKeys = {'CJK Unified Ideographs': 'CJKCharactersLanguage'}
for charset in ('Basic Latin', 'Extended Latin', 'Latin Extended-B'):
	_configKeys[charset] = 'latinCharactersLanguage'

class LanguageDetector(object):
	""" Provides functionality to add guessed language commands to NVDA speech sequences.
	Unicode ranges and user configuration are used to guess the language."""
	def __init__(self, availableLanguages, speechSymbols=None):
		self.speechSymbols = speechSymbols
		# We only work with language codes yet, no dialects.
		availableLanguages = frozenset(l.split("_")[0] for l in availableLanguages)
		# Cache what are the unicode blocks supported by each language.
		# Only cache for languages we have available
		languageBlocks = defaultdict(lambda : [])
		# Basic latin and extended latin are considered the same.
		for l in (set(ALL_LATIN) & availableLanguages):
			languageBlocks[l].extend([u"Basic Latin", u"Extended Latin"])
		# Syrilic and arabic languages.
		for l in (set(CYRILLIC) & availableLanguages):
			languageBlocks[l].append(u"Cyrillic")
		# For arabic.
		for l in (set(ARABIC) & availableLanguages):
			languageBlocks[l].extend([u"Arabic", u"Arabic Presentation Forms-A", u"Arabic Presentation Forms-B"])
		# If we have korian, store its blocks.
		if u"ko" in availableLanguages:
			for block in [u"Hangul Syllables", u"Hangul Jamo", u"Hangul Compatibility Jamo", u"Hangul"]:
				languageBlocks[u"ko"].append(block)
			# Same for greek.
		if u"el" in availableLanguages:
			languageBlocks[u"el"].append(u"Greek and Coptic")
		# And japonese.
		if u"ja" in availableLanguages:
			languageBlocks[u"ja"].extend([u"Kana", u"CJK Unified Ideographs"])
		# Chinese (I have some dobts here).
		if u"zh" in availableLanguages:
			languageBlocks[u"zh"].extend([u"CJK Unified Ideographs", u"Bopomofo", u"Bopomofo Extended", u"KangXi Radicals"])
		# Ad singletone languages (te only language for the range)
		for k, v in SINGLETONS.items():
			if v in availableLanguages:
				languageBlocks[v].append(k)
		self.languageBlocks = languageBlocks

		# cache a reversed version of the hash table too.
		blockLanguages = defaultdict(lambda : [])
		for k, v in languageBlocks.items():
			for i in v:
				blockLanguages[i].append(k)
		self.blockLanguages = blockLanguages


	def add_detected_language_commands(self, speechSequence):
		sb = StringIO()
		charset = None
		defaultLang = getSynth().language
		curLang = defaultLang
		tmpLang = curLang.split("_")[0]
		for command in speechSequence:
			if isinstance(command, WVLangChangeCommand):
				if command.lang is None:
					curLang = defaultLang
				else:
					curLang = command.lang
				tmpLang = curLang.split("_")[0]
				yield command
				charset = None # Whatever will come, reset the charset.
			elif isinstance(command, str):
				sb = StringIO()
				command = str(command)
				prevInIgnore = False
				rule = False
				for c in command:
					if self.speechSymbols and c in self.speechSymbols.symbols:
						rule = True
						block = ord(c) >> BLOCK_RSHIFT
						try:
							newCharset = BLOCKS[block]
						except IndexError:
							newCharset = None
						charset = newCharset
						symbol = self.speechSymbols.symbols[c]
						c = symbol.replacement if symbol.replacement and not c in [str(i) for i in range(10)] else c
						if symbol.mode == 1:
							newLang = symbol.language
						else:
							newLang = tmpLang
						newLangFirst = newLang.split("_")[0]
						if newLangFirst == tmpLang:
							# Same old...
							sb.write(c)
							continue
						# Change language
						# First yield the string we already have.
						if sb.getvalue():
							yield sb.getvalue()
							sb = StringIO()
						tmpLang = newLangFirst
						charset = None
						yield WVLangChangeCommand(newLang)
						yield c
						continue

					# For non-alphanumeric characters, revert to  the currently set language if in the ASCII range
					block = ord(c) >> BLOCK_RSHIFT
					if c.isspace():
						sb.write(c)
						continue
					if c.isdigit() or (not c.isalpha() and block <= 0x8):
						if config.conf["WorldVoice"]['autoLanguageSwitching']['ignoreNumbersInLanguageDetection'] and c.isdigit():
							sb.write(c)
							continue
						if config.conf["WorldVoice"]['autoLanguageSwitching']['ignorePunctuationInLanguageDetection'] and not c.isdigit():
							sb.write(c)
							continue
						if prevInIgnore and not rule:
							# Digits and ascii punctuation. We already calculated
							sb.write(c)
							continue
						prevInIgnore = True
						charset = None # Revert to default charset, we don't care here and  have to recheck later
						if tmpLang != curLang.split("_")[0]:
							if sb.getvalue():
								yield sb.getvalue()
								sb = StringIO()
							yield WVLangChangeCommand(curLang)
							tmpLang = curLang.split("_")[0]
						sb.write(c)
						continue

						# Process alphanumeric characters.
					prevInIgnore = False
					try:
						newCharset = BLOCKS[block]
					except IndexError:
						newCharset = None
					if not rule:
						if newCharset == charset:
							sb.write(c)
							continue
						charset = newCharset
						if charset in self.languageBlocks[tmpLang]:
							sb.write(c)
							continue
					else:
						charset = newCharset
					rule = False
					# Find the new language to use
					newLang = self.find_language_for_charset(charset, curLang)
					newLangFirst = newLang.split("_")[0]
					if newLangFirst == tmpLang:
						# Same old...
						sb.write(c)
						continue
					# Change language
					# First yield the string we already have.
					if sb.getvalue():
						yield sb.getvalue()
						sb = StringIO()
					tmpLang = newLangFirst
					if newLang == curLang:
						yield WVLangChangeCommand(newLang)
					else:
						yield WVLangChangeCommand(tmpLang)
					sb.write(c)
				# Send the string, if we have one:
				if sb.getvalue():
					yield sb.getvalue()
			else:
				yield command

	def find_language_for_charset(self, charset, curLang):
		langs = self.blockLanguages[charset]
		if not langs or curLang.split("_")[0] in langs:
			return curLang
		# See if we have any configured language for this charset.
		if charset in _configKeys:
			configKey = _configKeys[charset]
			lang = config.conf["WorldVoice"]['autoLanguageSwitching'][configKey]
			return lang
		return langs[0]

	def process_for_spelling(self, text, locale=None):
		if locale is None:
			defaultLang = getSynth().language
		else:
			defaultLang = locale
		curLang = defaultLang
		charset = None
		sb = StringIO()
		for c in text:
			block = ord(c) >> BLOCK_RSHIFT
			if c.isspace() or c.isdigit() or (not c.isalpha() and block <= 0x8):
				charset = None
				if curLang == defaultLang:
					sb.write(c)
				else:
					if sb.getvalue():
						yield sb.getvalue(), curLang
					curLang = defaultLang
					sb = StringIO()
					sb.write(c)
				continue
			try:
				newCharset = BLOCKS[block]
			except IndexError:
				newCharset = None
			if charset is None or charset != newCharset:
				tmpLang = curLang.split("_")[0]
				if newCharset in self.languageBlocks[tmpLang]:
					sb.write(c)
					continue
				lang = self.find_language_for_charset(newCharset, tmpLang)
				charset = newCharset
				if lang == tmpLang:
					sb.write(c)
					continue
				if sb.getvalue():
					yield sb.getvalue(), curLang
					sb = StringIO()
				sb.write(c)
				curLang = lang
				if curLang == defaultLang.split("_")[0]:
					curLang = defaultLang
			else: # same charset
				sb.write(c)
		if sb.getvalue():
			yield sb.getvalue(), curLang

