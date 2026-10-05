from speech.commands import LangChangeCommand

from .._speechcommand import WVLangChangeCommand
from .scripts import get_script

BASIC_LATIN = (
	"en",
	"ha",
	"so",
	"id",
	"la",
	"sw",
	"eu",
	"nr",
	"zu",
	"xh",
	"ss",
	"st",
	"tn",
	"ts",
)
EXTENDED_LATIN = (
	"cs",
	"af",
	"pl",
	"hr",
	"ro",
	"sk",
	"sl",
	"tr",
	"hu",
	"az",
	"et",
	"sq",
	"ca",
	"es",
	"gl",
	"fr",
	"de",
	"nl",
	"it",
	"da",
	"is",
	"nb",
	"sv",
	"fi",
	"lv",
	"pt",
	"ve",
	"lt",
	"tl",
	"cy",
	"vi",
	"no",
	"uz",
)
ALL_LATIN = BASIC_LATIN + EXTENDED_LATIN

CYRILLIC = ("ru", "uk", "be", "kk", "tt", "uz", "mn", "sr", "mk", "bg", "ky")
ARABIC = ("ar", "fa", "ps", "ur")
DEVANAGARI = ("hi", "sa", "mr", "ne")
CJK = ("zh", "ja", "ko")

SCRIPT_LANGUAGES = {
	"Latin": ALL_LATIN,
	"Cyrillic": CYRILLIC,
	"Arabic": ARABIC,
	"Devanagari": DEVANAGARI,
	"Han": CJK,
	"Hiragana": ("ja",),
	"Katakana": ("ja",),
	"Hangul": ("ko",),
	"Bopomofo": ("zh",),
	"Armenian": ("hy",),
	"Hebrew": ("he",),
	"Bengali": ("bn",),
	"Gurmukhi": ("pa",),
	"Greek": ("el",),
	"Gujarati": ("gu",),
	"Oriya": ("or",),
	"Tamil": ("ta",),
	"Telugu": ("te",),
	"Kannada": ("kn",),
	"Malayalam": ("ml",),
	"Sinhala": ("si",),
	"Thai": ("th",),
	"Lao": ("lo",),
	"Tibetan": ("bo",),
	"Myanmar": ("my",),
	"Georgian": ("ka",),
	"Mongolian": ("mn",),
	"Khmer": ("km",),
}


def get_primary_language(locale: str) -> str:
	return locale.replace("-", "_").split("_", maxsplit=1)[0].lower()


class LanguageDetector:
	"""Provides functionality to add guessed language commands to NVDA speech sequences.
	Unicode ranges and user configuration are used to guess the language."""

	def __init__(self, availableLanguages, speechSymbols=None, *, settings, language):
		"""settings.get() returns the detection settings; language returns the synth's current language."""
		self.speechSymbols = speechSymbols
		self._settings = settings
		self._language = language
		self.availableLanguages = frozenset(get_primary_language(lang) for lang in availableLanguages)

	def find_language_for_script(self, script, current_language, settings=None):
		candidates = SCRIPT_LANGUAGES.get(script, ())
		current_primary = get_primary_language(current_language)
		if not candidates or current_primary in candidates:
			return current_language
		if settings is None:
			settings = self._settings.get()
		configured = settings.script_language.get(script)
		if configured is not None:
			configured_primary = get_primary_language(configured)
			if configured_primary in candidates and configured_primary in self.availableLanguages:
				return configured
		for candidate in candidates:
			if candidate in self.availableLanguages:
				return candidate
		return current_language

	def _language_for_character(self, character, current_language, base_language, settings):
		if character.isdigit():
			if settings.ignore_numbers:
				return current_language
			return base_language
		script = get_script(ord(character))
		if script in (None, "Common", "Inherited"):
			return current_language
		return self.find_language_for_script(script, current_language, settings)

	def add_detected_language_commands(self, speechSequence):
		# Read the settings once, so the whole sequence is detected with the same values.
		settings = self._settings.get()
		defaultLang = self._language()
		curLang = defaultLang
		tmpLang = curLang
		for command in speechSequence:
			if isinstance(command, (LangChangeCommand, WVLangChangeCommand)):
				curLang = command.lang or defaultLang
				tmpLang = curLang
				yield command
			elif isinstance(command, str):
				buffer = []
				for c in command:
					if self.speechSymbols and c in self.speechSymbols.symbols:
						symbol = self.speechSymbols.symbols[c]
						text = symbol.replacement if symbol.replacement and c not in "0123456789" else c
						targetLang = symbol.language if symbol.mode == 1 else tmpLang
					else:
						text = c
						targetLang = self._language_for_character(c, tmpLang, curLang, settings)

					if get_primary_language(targetLang) != get_primary_language(tmpLang):
						if buffer:
							yield "".join(buffer)
							buffer = []
						yield WVLangChangeCommand(targetLang)
						tmpLang = targetLang
					buffer.append(text)
				if buffer:
					yield "".join(buffer)
			else:
				yield command

	def process_for_spelling(self, text, locale=None):
		settings = self._settings.get()
		default_language = locale if locale is not None else self._language()
		current_language = default_language
		buffer = []
		for character in text:
			if character.isspace() or character.isdigit():
				target_language = default_language
			else:
				script = get_script(ord(character))
				if script in (None, "Common", "Inherited"):
					target_language = current_language
				else:
					target_language = self.find_language_for_script(script, current_language, settings)

			if get_primary_language(target_language) == get_primary_language(default_language):
				target_language = default_language
			if get_primary_language(target_language) != get_primary_language(current_language):
				if buffer:
					yield "".join(buffer), current_language
					buffer = []
				current_language = target_language
			buffer.append(character)
		if buffer:
			yield "".join(buffer), current_language
