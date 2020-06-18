# -*- coding: utf-8 -*-
# vocalizer/languageDetection/__init__.py
# Copyright (C) 2012 - Rui Batista <ruiandrebatista@gmail.com>
#
# This code is heavily based on the Python guess_language library.
# Copyright 2012 spirit <hiddenspirit@gmail.com>
# https://bitbucket.org/spirit/guess_language/
#
# Original Python package:
# Copyright (c) 2008, Kent S Johnson
# http://code.google.com/p/guess-language/
#
# Original C++ version for KDE:
# Copyright (c) 2006 Jacob R Rideout <kde@jacobrideout.net>
# http://websvn.kde.org/branches/work/sonnet-refactoring/common/nlp/guesslanguage.cpp?view=markup
#
# Original Language::Guess Perl module:
# Copyright (c) 2004-2006 Maciej Ceglowski
# http://web.archive.org/web/20090228163219/http://languid.cantbedone.org/
#
# Note: Language::Guess is GPL-licensed. KDE developers received permission
# from the author to distribute their port under LGPL:
# http://lists.kde.org/?l=kde-sonnet&m=116910092228811&w=2
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation, either version 3 of the License,
# or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty
# of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#

from collections import defaultdict
from io import StringIO

from .blocks import BLOCKS, BLOCK_RSHIFT

import config
from logHandler import log
import languageHandler
import speech
from .. import _config


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
_configKeys = {}
for charset in ('Basic Latin', 'Extended Latin', 'Latin Extended-B'):
	_configKeys[charset] = 'latinCharactersLanguage'

class LanguageDetector(object):
	""" Provides functionality to add guessed language commands to NVDA speech sequences.
	Unicode ranges and user configuration are used to guess the language."""
	def __init__(self, availableLanguages):
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
		defaultLang = speech.getSynth().language
		curLang = defaultLang
		tmpLang = curLang.split("_")[0]
		for command in speechSequence:
			if isinstance(command, speech.LangChangeCommand):
				if command.lang is None:
					curLang = defaultLang
				else:
					curLang = command.lang
				tmpLang = curLang.split("_")[0]
				yield command
				charset = None # Whatever will come, reset the charset.
			elif isinstance(command, str):
				sb.truncate(0)
				prevInIgnore = False
				for c in command:
					# For non-alphanumeric characters, revert to  the currently set language if in the ASCII range
					block = ord(c) >> BLOCK_RSHIFT
					if c.isspace():
						sb.write(c)
						continue
					if c.isdigit() or (not c.isalpha() and block <= 0x8):
						if _config.vocalizerConfig['autoLanguageSwitching']['ignorePonctuationAndNumbersInLanguageDetection']:
							sb.write(c)
							continue
						if prevInIgnore:
							# Digits and ascii punctuation. We already calculated
							sb.write(c)
							continue
						prevInIgnore = True
						charset = None # Revert to default charset, we don't care here and  have to recheck later
						if tmpLang != curLang.split("_")[0]:
							if sb.getvalue():
								yield sb.getvalue()
								sb.truncate(0)
							yield speech.LangChangeCommand(curLang)
							tmpLang = curLang.split("_")[0]
						sb.write(c)
						continue

						# Process alphanumeric characters.
					newCharset = BLOCKS[block]
					if newCharset == charset:
						sb.write(c)
						continue
					charset = newCharset
					if charset in self.languageBlocks[tmpLang]:
						sb.write(c)
						continue
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
						sb.truncate(0)
					tmpLang = newLangFirst
					if newLang == curLang:
						yield speech.LangChangeCommand(newLang)
					else:
						yield speech.LangChangeCommand(tmpLang)
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
			lang = _config.vocalizerConfig['autoLanguageSwitching'][configKey]
			return lang
		return langs[0]

	def process_for_spelling(self, text, locale=None):
		if locale is None:
			defaultLang = speech.getSynth().language
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
					sb.truncate(0)
					sb.write(c)
				continue
			newCharset = BLOCKS[block]
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
					sb.truncate(0)
				sb.write(c)
				curLang = lang
				if curLang == defaultLang.split("_")[0]:
					curLang = defaultLang
			else: # same charset
				sb.write(c)
		if sb.getvalue():
			yield sb.getvalue(), curLang

