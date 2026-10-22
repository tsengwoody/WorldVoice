"""NVDA's name for a symbol in the locale of the voice that speaks it, and whether NVDA has a symbols
table for a locale.

Whether a locale has a table is cached for the rest of the NVDA run, keyed by the locale: the table
lives in NVDA's own program directory (globalVars.appDir, set once at startup), and a new built-in
table arrives only with an NVDA update, which restarts NVDA. NVDA assumes the same when it globs
these files once per run (SymbolDictionaryDefinition.availableLocales, a cached_property). NVDA's
current language is not cached: it follows the voice, the synth and the configuration profile.
"""

import os
from collections.abc import Callable
from functools import lru_cache

import characterProcessing
import globalVars
import languageHandler
import speech


def _symbol_table_on_disk(locale: str) -> bool:
	"""Whether NVDA has its own symbols table for *locale*, with no fallback to another locale.

	NVDA's mandatory built-in dictionary is locale/<locale>/symbols.dic in its program directory
	(characterProcessing.py:893-901). processSpeechSymbol falls back to the base language and then
	to English without saying so, so only the file tells whether the locale has names of its own.
	A locale that is not a plain name (empty, or with a path in it) has none. Call it through
	has_symbol_table, which asks once per locale.
	"""
	if not locale.replace("_", "").isalnum():
		return False
	return os.path.isfile(os.path.join(globalVars.appDir, "locale", locale, "symbols.dic"))


# A call, not a decorator: mutmut 3.8.0 does not mutate decorated functions.
has_symbol_table = lru_cache(maxsize=None)(_symbol_table_on_disk)


def symbol_locale(language: str | None, voice_locale: str | None = None) -> str:
	"""The locale to look a symbol name up in, for text spoken in *language* by a voice of *voice_locale*.

	The voice's own locale comes first, in NVDA's form ("zh-TW" -> "zh_TW"), when NVDA has a
	symbols table for it (decided by the user, 2026-10-22). Otherwise: no language (another synth's
	context) is NVDA's current language, where NVDA's own symbol processing starts. NVDA only drops
	a country after "_", so a "-" becomes "_"; and a bare language, as WorldVoice stores number
	languages, takes the country of NVDA's current language when the two agree ("zh" -> "zh_TW"), as
	NVDA's spelling does.
	"""
	if voice_locale:
		locale = languageHandler.normalizeLanguage(voice_locale)
		if locale and has_symbol_table(locale):
			return locale
	current = speech.getCurrentLanguage()
	if not language:
		return current
	locale = language.replace("-", "_")
	if "_" not in locale and locale.lower() == current.split("_")[0].lower():
		return current
	return locale


def symbol_name(locale: str, symbol: str) -> str | None:
	"""NVDA's name of *symbol* in *locale*, as when NVDA reads that one character; None without one."""
	try:
		name = characterProcessing.processSpeechSymbol(locale, symbol)
	except LookupError:
		return None
	return name if name and name != symbol else None


def symbol_namer(
	voice_locale_for_language: Callable[[str], str | None],
) -> Callable[[str | None], Callable[[str], str | None]]:
	"""Name lookups for one stage run: one locale per language and one NVDA lookup per symbol.

	*voice_locale_for_language* gives the locale of the voice that speaks a language; it is asked
	once per language per run, and never for no language.
	"""
	locales: dict[str | None, str] = {}
	names: dict[tuple[str | None, str], str | None] = {}

	def for_language(language: str | None) -> Callable[[str], str | None]:
		def name_of(symbol: str) -> str | None:
			key = (language, symbol)
			if key not in names:
				if language not in locales:
					voice_locale = voice_locale_for_language(language) if language else None
					locales[language] = symbol_locale(language, voice_locale)
				names[key] = symbol_name(locales[language], symbol)
			return names[key]

		return name_of

	return for_language
