from speech.commands import LangChangeCommand

from ..locales import primary_language
from ..numberLanguage import FOLLOW, MAIN
from ..speechCommands import WVLangChangeCommand
from ..unicodeScripts.lookup import get_script
from .scriptLanguages import SCRIPT_LANGUAGES


class LanguageDetector:
	"""Provides functionality to add guessed language commands to NVDA speech sequences.
	Unicode ranges and user configuration are used to guess the language."""

	def __init__(self, available_languages, *, settings, language, number_language=lambda: FOLLOW):
		"""settings.get() returns the detection settings; language returns the synth's current language;
		number_language returns the stored number language, which spelling follows."""
		self._settings = settings
		self._language = language
		self._number_language = number_language
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

	def _language_for_character(self, character, current_language, base_language, settings):
		# A decimal digit of any script stays in the current run: the pipeline wraps a number for
		# its number language. Many decimal digits are not Common script (Arabic-Indic ones are
		# Arabic), so they need this rule.
		if character.isdecimal():
			return current_language
		script = get_script(ord(character))
		if script in (None, "Common", "Inherited"):
			return current_language
		return self.find_language_for_script(script, current_language, settings, base_language=base_language)

	def add_detected_language_commands(self, speech_sequence):
		# Read the settings once, so the whole sequence is detected with the same values.
		settings = self._settings.get()
		default_lang = self._language()
		cur_lang = default_lang
		tmp_lang = cur_lang
		for command in speech_sequence:
			if isinstance(command, (LangChangeCommand, WVLangChangeCommand)):
				cur_lang = command.lang or default_lang
				tmp_lang = cur_lang
				yield command
			elif isinstance(command, str):
				buffer = []
				for c in command:
					target_lang = self._language_for_character(c, tmp_lang, cur_lang, settings)
					if primary_language(target_lang) != primary_language(tmp_lang):
						if buffer:
							yield "".join(buffer)
							buffer = []
						yield WVLangChangeCommand(target_lang)
						tmp_lang = target_lang
					buffer.append(c)
				if buffer:
					yield "".join(buffer)
			else:
				yield command

	def _spelling_language_for_digit(self, number_language, current_language, default_language):
		"""The language a decimal digit is spelled in: the current one when it follows the text, the
		spelling locale for "main", or the number language when it has a voice."""
		if number_language == FOLLOW:
			return current_language
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
			elif character.isdecimal():
				target_language = self._spelling_language_for_digit(
					number_language,
					current_language,
					default_language,
				)
			else:
				script = get_script(ord(character))
				if script in (None, "Common", "Inherited"):
					target_language = current_language
				else:
					target_language = self.find_language_for_script(
						script,
						current_language,
						settings,
						base_language=default_language,
					)

			if primary_language(target_language) != primary_language(current_language):
				if buffer:
					yield "".join(buffer), current_language
					buffer = []
				current_language = target_language
			buffer.append(character)
		if buffer:
			yield "".join(buffer), current_language
