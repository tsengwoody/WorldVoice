"""Symbol names inside numbers come from NVDA's own single-symbol lookup, in the number's language.

The last tests load NVDA's real characterProcessing from ref/nvda, so they still hold when NVDA
changes its symbol tables or its locale fallback.
"""

import builtins
import unicodedata
from types import SimpleNamespace

import pytest
from addon_loader import REF, load_source
from nvda_stubs import StubModules
from pipeline_harness import load_pipeline_module, punctuation_settings

CHARACTER_PROCESSING = REF / "nvda/source/characterProcessing.py"
# NVDA's symbol loader still calls codecs.open, which Python 3.14 deprecates.
NVDA_WARNINGS = pytest.mark.filterwarnings("ignore:codecs.open:DeprecationWarning")
NUMBER_SYMBOLS = "".join(c for c in map(chr, range(0x100)) if unicodedata.category(c)[0] in "PS")


@pytest.fixture
def module(monkeypatch):
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	return module


def test_symbol_name_is_the_lookups_name(module):
	assert module._symbol_name("en", "×") == "multiplication sign en"


def _raise_lookup_error(locale, symbol):
	raise LookupError(locale)


@pytest.mark.parametrize(
	"lookup",
	[
		_raise_lookup_error,
		lambda locale, symbol: None,
		lambda locale, symbol: "",
		lambda locale, symbol: symbol,
	],
	ids=["raises", "none", "empty", "itself"],
)
def test_symbol_name_is_none_without_a_name(module, monkeypatch, lookup):
	monkeypatch.setattr(module.characterProcessing, "processSpeechSymbol", lookup)
	assert module._symbol_name("en", ".") is None


@pytest.mark.parametrize(
	("current", "language", "expected"),
	[
		# Another synth's context has no language: NVDA's own processText starts from this one.
		("en_GB", None, "en_GB"),
		# NVDA's locale fallback only drops a country after "_".
		("zh_TW", "zh-TW", "zh_TW"),
		# WorldVoice's number languages are bare primary subtags, and NVDA has no "zh" table.
		("zh_TW", "zh", "zh_TW"),
		("zh_TW", "en", "en"),
		("zh_TW", "de_CH", "de_CH"),
	],
)
def test_symbol_locale(module, monkeypatch, current, language, expected):
	monkeypatch.setattr(module.speech, "getCurrentLanguage", lambda: current)
	assert module._symbol_locale(language) == expected


def load_nvda_character_processing(monkeypatch, tmp_path):
	"""NVDA's real characterProcessing over ref/nvda's symbol tables, with its built-in dictionaries."""
	if not CHARACTER_PROCESSING.is_file():
		pytest.skip("ref/nvda is not checked out")
	stubs = StubModules(monkeypatch)
	stubs.translation()
	monkeypatch.setattr(builtins, "pgettext", lambda context, text: text, raising=False)
	stubs.module(
		"NVDAState",
		shouldWriteToDisk=lambda: False,
		WritePaths=SimpleNamespace(
			getSymbolsConfigFile=lambda locale: str(tmp_path / f"symbols-{locale}.dic"),
		),
	)
	ignore = lambda *args, **kwargs: None
	stubs.module(
		"logHandler",
		log=SimpleNamespace(debug=ignore, debugWarning=ignore, error=ignore, exception=ignore),
	)
	stubs.module("globalVars", appDir=str(REF / "nvda/source"))
	stubs.module("config", conf={"speech": {"symbolDictionaries": ["cldr"]}})
	stubs.module("addonHandler", getRunningAddons=list)
	character_processing = load_source(monkeypatch, "characterProcessing", CHARACTER_PROCESSING)
	character_processing._addSymbolDefinitions()
	return character_processing


@pytest.mark.parametrize(
	("locale", "symbol", "name"),
	[
		("en", "×", "times"),
		("zh_TW", "×", "乘以"),
		("zh_TW", "°", "度"),
		# No de_CH entry: the base language's table.
		("de_CH", "×", "Mal"),
		# No table at all: English.
		("xx", "×", "times"),
		("en", ".", "dot"),
	],
)
@NVDA_WARNINGS
def test_nvda_names_symbols_in_the_requested_language(monkeypatch, tmp_path, locale, symbol, name):
	character_processing = load_nvda_character_processing(monkeypatch, tmp_path)
	assert character_processing.processSpeechSymbol(locale, symbol) == name


@pytest.mark.parametrize("locale", ["en", "zh_TW"])
@NVDA_WARNINGS
def test_every_number_symbol_has_a_name(monkeypatch, tmp_path, locale):
	character_processing = load_nvda_character_processing(monkeypatch, tmp_path)
	unnamed = [
		symbol
		for symbol in NUMBER_SYMBOLS
		if character_processing.processSpeechSymbol(locale, symbol) in ("", None, symbol)
	]
	assert unnamed == []


@NVDA_WARNINGS
def test_pipeline_names_symbols_with_nvdas_real_lookup(module, monkeypatch, tmp_path):
	monkeypatch.setattr(module, "characterProcessing", load_nvda_character_processing(monkeypatch, tmp_path))
	monkeypatch.setattr(module.speech, "getCurrentLanguage", lambda: "zh_TW")
	assert module._symbol_name(module._symbol_locale("zh"), "×") == "乘以"
