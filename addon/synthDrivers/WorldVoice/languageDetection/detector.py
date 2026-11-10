from speech.commands import ConfigProfileTriggerCommand, EndUtteranceCommand, LangChangeCommand

from ..locales import primary_language
from ..numberLanguage import FOLLOW, MAIN
from ..speechCommands import WVLangChangeCommand
from ..unicodeScripts.lookup import get_script
from .scriptLanguages import SCRIPT_LANGUAGES

# get_script for a character with no script of its own.
_NO_SCRIPT = (None, "Common", "Inherited")


class LanguageDetector:
	"""Provides functionality to add guessed language commands to NVDA speech sequences.
	Unicode ranges and user configuration are used to guess the language."""

	def __init__(
		self,
		available_languages,
		*,
		settings,
		language,
		number_language=lambda: FOLLOW,
		is_internal_break=lambda command: False,
	):
		"""settings.get() returns the detection settings; language returns the synth's current language;
		number_language returns the number language speech uses (the driver's spoken choice), which
		decides how digits are detected and spelled; is_internal_break tells a pause a stage put inside
		one item, which does not end the item (the driver passes pipeline.breaks.is_internal_break; the
		detector imports no pipeline module)."""
		self._settings = settings
		self._language = language
		self._number_language = number_language
		self._is_internal_break = is_internal_break
		self.available_languages = frozenset(primary_language(lang) for lang in available_languages)

	def _covers(self, language, script):
		"""Whether language is a language of script that has an installed voice."""
		primary = primary_language(language)
		return primary in SCRIPT_LANGUAGES.get(script, ()) and primary in self.available_languages

	def find_language_for_script(self, script, current_language, settings=None, base_language=None):
		"""The language for a letter of script: the current language, the base language, the
		configured language, then the first installed one; the current language if none has a voice."""
		candidates = SCRIPT_LANGUAGES.get(script, ())
		if not candidates or self._covers(current_language, script):
			return current_language
		if base_language is not None and self._covers(base_language, script):
			return base_language
		if settings is None:
			settings = self._settings.get()
		configured = settings.script_language.get(script)
		if configured is not None:
			configured_primary = primary_language(configured)
			if configured_primary in candidates and configured_primary in self.available_languages:
				return configured
		for candidate in candidates:
			if candidate in self.available_languages:
				return candidate
		return current_language

	def _script_language(self, character, current_language, base_language, settings):
		"""The language for character by its script; the current language for a character of no
		script of its own (Common, Inherited or unknown)."""
		script = get_script(ord(character))
		if script in _NO_SCRIPT:
			return current_language
		return self.find_language_for_script(script, current_language, settings, base_language=base_language)

	def _language_for_character(self, character, current_language, base_language, settings, digits_by_script):
		# "main" and a locale wrap every number in its number language before detection
		# (pipeline.numberStages.detect_with_number_language), so a decimal digit of any script stays
		# in the run. Under "Follow surrounding text language" (digits_by_script) a digit with a
		# script, such as a Devanagari one, follows the letter rule of its script, as a voice of
		# another script may not read it (spec fix/script-digit-language G1).
		if character.isdecimal() and not digits_by_script:
			return current_language
		return self._script_language(character, current_language, base_language, settings)

	def add_detected_language_commands(self, speech_sequence):
		# Read the settings and the number language once, so the whole sequence is detected with the
		# same values.
		detection = _SequenceDetection(
			self,
			self._settings.get(),
			self._number_language() == FOLLOW,
			self._language(),
		)
		for utterance in _utterances(speech_sequence):
			yield from detection.detect(utterance)

	def _spelling_language_for_digit(self, number_language, default_language):
		"""The language a decimal digit is spelled in under "main" or a locale: the spelling locale for
		"main", or the number language when it has a voice."""
		if number_language != MAIN and primary_language(number_language) in self.available_languages:
			return number_language
		return default_language

	def process_for_spelling(self, text, locale=None):
		settings = self._settings.get()
		number_language = self._number_language()
		default_language = locale if locale is not None else self._language()
		current_language = default_language
		buffer = []
		for character in text:
			if character.isspace():
				target_language = default_language
			elif character.isdecimal() and number_language != FOLLOW:
				target_language = self._spelling_language_for_digit(number_language, default_language)
			else:
				# Under "Follow surrounding text language" a digit is spelled as detection reads it.
				target_language = self._script_language(
					character,
					current_language,
					default_language,
					settings,
				)

			if primary_language(target_language) != primary_language(current_language):
				if buffer:
					yield "".join(buffer), current_language
					buffer = []
				current_language = target_language
			buffer.append(character)
		if buffer:
			yield "".join(buffer), current_language


class _SequenceDetection:
	"""One add_detected_language_commands call: the values read once for it, and the language state.

	cur_lang is the language of the last language command (the base), tmp_lang the language of the run
	in progress; both carry from one utterance to the next (spec fix/leading-punctuation-language D11).
	Leading punctuation follows the text after it: the characters at an item's start that decide
	nothing take the language of the first character that decides.
	"""

	def __init__(self, detector, settings, digits_by_script, default_lang):
		self.detector = detector
		self.settings = settings
		self.digits_by_script = digits_by_script
		self.default_lang = default_lang
		self.cur_lang = default_lang
		self.tmp_lang = default_lang

	def decides(self, character):
		"""Whether character decides the language of the characters before it (spec D1): a character
		with a script of its own, or a decimal digit under "main" or a locale (a stop)."""
		return self.is_stop(character) or get_script(ord(character)) not in _NO_SCRIPT

	def is_stop(self, character):
		"""A decimal digit under "main" or a locale: it keeps the run before it in the current language
		(spec D2, D9); such numbers are wrapped before detection."""
		return character.isdecimal() and not self.digits_by_script

	def ends_item(self, command):
		"""Whether command, which is no text and no number wrapper, ends an item (spec U5, D5)."""
		return isinstance(command, LangChangeCommand) or not self.detector._is_internal_break(command)

	def plan(self, commands, index, offset, came_before):
		"""The run of characters that decide nothing, from commands[index][offset] at an item's start.

		The run ends at the item's first deciding character. When nothing decided earlier in the
		utterance (came_before is False), an item with no deciding character looks ahead across items
		and commands to the first one in the utterance (spec U7). A number wrapper or a stop ends the
		run without deciding (D2, D3, D9), and so does the utterance's end.

		Returns where the run ends, as (index, offset) of the first position after it, and the target
		of each stretch of the run between NVDA language commands (None: today's rule).
		"""
		# The language in force at the start of each stretch, and the state the deciding character meets.
		stretch_languages = [self.tmp_lang]
		tmp_lang, cur_lang = self.tmp_lang, self.cur_lang
		for i in range(index, len(commands)):
			command = commands[i]
			if isinstance(command, str):
				for k in range(offset if i == index else 0, len(command)):
					character = command[k]
					if self.decides(character):
						return (i, k), self.stretch_targets(character, stretch_languages, tmp_lang, cur_lang)
			elif isinstance(command, WVLangChangeCommand) or (came_before and self.ends_item(command)):
				return (i, 0), [None] * len(stretch_languages)
			elif isinstance(command, LangChangeCommand):
				tmp_lang = cur_lang = command.lang or self.default_lang
				stretch_languages.append(tmp_lang)
		return (len(commands), 0), [None] * len(stretch_languages)

	def stretch_targets(self, character, stretch_languages, tmp_lang, cur_lang):
		"""The target of each stretch of a run that the deciding character ends (spec D2, D10).

		target is what the character gets with the state it meets. Every stretch keeps its language when
		target does not cover the script (no installed voice reads it: nothing changes, spec §4.4).
		Otherwise the stretches are decided from the last one back: a stretch whose language in force
		covers the script keeps it, and once one keeps a language of another primary than target, every
		stretch before it keeps today's rule too, so the run never goes target, that language, target
		(spec D6, review I2). Within one item, where a run has one stretch, this is D2.
		"""
		if self.is_stop(character):
			return [None] * len(stretch_languages)
		script = get_script(ord(character))
		target = self.detector._language_for_character(
			character,
			tmp_lang,
			cur_lang,
			self.settings,
			self.digits_by_script,
		)
		covers = self.detector._covers
		targets = [None] * len(stretch_languages)
		if not covers(target, script):
			return targets
		for index in range(len(stretch_languages) - 1, -1, -1):
			language = stretch_languages[index]
			if not covers(language, script):
				targets[index] = target
			elif primary_language(language) != primary_language(target):
				break
		return targets

	def detect(self, commands):
		"""Detect one utterance."""
		at_item_start = True
		# Whether a deciding character or a number wrapper came earlier in the utterance (spec U7, D9).
		came_before = False
		# The planned run: where it ends and the targets of its stretches still to come.
		run_end, run_targets = (0, 0), [None]
		for index, command in enumerate(commands):
			if isinstance(command, (LangChangeCommand, WVLangChangeCommand)):
				self.cur_lang = command.lang or self.default_lang
				self.tmp_lang = self.cur_lang
				if isinstance(command, WVLangChangeCommand):
					# A number wrapper continues the item; what follows it is no longer at its start (D3).
					at_item_start = False
					came_before = True
				else:
					at_item_start = True
					if (index, 0) < run_end:
						run_targets.pop(0)
				yield command
			elif isinstance(command, str):
				buffer = []
				for offset, character in enumerate(command):
					if (index, offset) < run_end:
						target = run_targets[0]
					elif at_item_start and not self.decides(character):
						run_end, run_targets = self.plan(commands, index, offset, came_before)
						target = run_targets[0]
					else:
						if self.decides(character):
							at_item_start = False
							came_before = True
						target = None
					if target is None:
						target = self.detector._language_for_character(
							character,
							self.tmp_lang,
							self.cur_lang,
							self.settings,
							self.digits_by_script,
						)
					if primary_language(target) != primary_language(self.tmp_lang):
						if buffer:
							yield "".join(buffer)
							buffer = []
						yield WVLangChangeCommand(target)
						self.tmp_lang = target
					buffer.append(character)
				if buffer:
					yield "".join(buffer)
			else:
				if self.ends_item(command):
					at_item_start = True
				yield command


def _utterances(speech_sequence):
	"""The sequence cut into utterances, each with the command that ends it (spec U8): NVDA's speech
	manager ends one at an EndUtteranceCommand and before a ConfigProfileTriggerCommand, as
	pipeline.sequence._ends_utterance reads them (this package imports no pipeline module)."""
	utterance = []
	for command in speech_sequence:
		utterance.append(command)
		if isinstance(command, (EndUtteranceCommand, ConfigProfileTriggerCommand)):
			yield utterance
			utterance = []
	if utterance:
		yield utterance
