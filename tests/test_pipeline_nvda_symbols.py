"""Symbol names inside numbers come from NVDA's own single-symbol lookup, in the number's language.

The last tests load NVDA's real characterProcessing from ref/nvda, so they still hold when NVDA
changes its symbol tables or its locale fallback.
"""

import ast
import builtins
import unicodedata
from pathlib import Path
from types import SimpleNamespace

import pytest
from addon_loader import REF, load_source
from nvda_stubs import StubModules
from pipeline_harness import load_pipeline_module, nvda_normalize_language, punctuation_settings

CHARACTER_PROCESSING = REF / "nvda/source/characterProcessing.py"
# NVDA's symbol loader still calls codecs.open, which Python 3.14 deprecates.
NVDA_WARNINGS = pytest.mark.filterwarnings("ignore:codecs.open:DeprecationWarning")
NUMBER_SYMBOLS = "".join(c for c in map(chr, range(0x100)) if unicodedata.category(c)[0] in "PS")


@pytest.fixture
def module(monkeypatch):
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	return module.symbols


def test_symbol_name_is_the_lookups_name(module):
	assert module.symbol_name("en", "×") == "multiplication sign en"


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
	assert module.symbol_name("en", ".") is None


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
	assert module.symbol_locale(language) == expected


@pytest.mark.parametrize(
	("locale", "expected"),
	[
		("zh_TW", True),
		("en", True),
		("de_CH", True),
		# NVDA has tables only with a country for these, and none for a country it does not list.
		("zh", False),
		("en_US", False),
		# Never a path outside NVDA's locale directory.
		("", False),
		("..", False),
		("../en", False),
		# This one resolves to locale/en/symbols.dic, which exists: only the guard refuses it.
		("../locale/en", False),
	],
)
def test_has_symbol_table_matches_nvdas_locale_dir(module, locale, expected):
	assert module.has_symbol_table(locale) is expected


@pytest.mark.parametrize(
	("current", "language", "voice", "expected"),
	[
		# Decided by the user (2026-10-22): the voice's locale wins over NVDA's interface country.
		("en", "zh", "zh-TW", "zh_TW"),
		("en", "zh", "zh_tw", "zh_TW"),
		("zh_TW", "zh", "zh_CN", "zh_CN"),
		("en", "de", "de-CH", "de_CH"),
		# D1/D2: a voice locale without an NVDA table keeps the rule without a voice.
		("zh_TW", "zh", "zh_SG", "zh_TW"),
		("en", "zh", "zh_SG", "zh"),
		("en", "zh", "zh", "zh"),
		("zh_TW", "zh", "zh", "zh_TW"),
		("en", "zh", "x-western", "zh"),
		("en", "zh", "zh-Hant-TW", "zh"),
		("zh_TW", "en", "en_US", "en"),
		("en", "en", "", "en"),
	],
)
def test_symbol_locale_prefers_the_voice_locale_with_a_table(
	module,
	monkeypatch,
	current,
	language,
	voice,
	expected,
):
	monkeypatch.setattr(module.speech, "getCurrentLanguage", lambda: current)
	assert module.symbol_locale(language, voice) == expected


def test_namer_asks_each_language_once_per_run(module):
	# One locale per language per stage run; the next run asks again, so a voice change counts.
	asked = []

	def voice_locale(language):
		asked.append(language)
		return "zh_TW"

	namer = module.symbol_namer(voice_locale)
	for language, symbol in [("zh", "×"), ("zh", "."), ("en", "×"), ("zh", "×")]:
		namer(language)(symbol)
	assert asked == ["zh", "en"]
	namer(None)("×")
	assert asked == ["zh", "en"]
	module.symbol_namer(voice_locale)("zh")("×")
	assert asked == ["zh", "en", "zh"]


def test_symbol_tables_are_probed_once_per_locale(module, monkeypatch):
	# D2: NVDA's locale directory does not change while NVDA runs, so each locale's table is probed
	# once; the current language can change with the voice, so it is still asked every run.
	probes, current = [], []
	isfile = module.os.path.isfile
	monkeypatch.setattr(module.os.path, "isfile", lambda path: probes.append(path) or isfile(path))
	monkeypatch.setattr(module.speech, "getCurrentLanguage", lambda: current.append(1) or "en")
	for _ in range(3):
		namer = module.symbol_namer({"zh": "zh-TW", "en": "en-US"}.get)
		assert (namer("zh")("×"), namer("en")("×")) == ("multiplication sign zh tw", "multiplication sign en")
	# isfile is os's own, so it is patched for everyone; only the probes of NVDA's locale directory
	# count.
	app_dir = Path(module.globalVars.appDir)
	tables = [Path(path) for path in probes if Path(path).is_relative_to(app_dir)]
	assert sorted(path.relative_to(app_dir).as_posix() for path in tables) == [
		"locale/en_US/symbols.dic",
		"locale/zh_TW/symbols.dic",
	]
	assert len(current) == 3


def test_nvda_builtin_symbols_live_in_appdir_locale():
	# has_symbol_table looks where NVDA's mandatory built-in dictionary is.
	if not CHARACTER_PROCESSING.is_file():
		pytest.skip("ref/nvda is not checked out")
	tree = ast.parse(CHARACTER_PROCESSING.read_text(encoding="utf-8"))
	definitions = [
		{keyword.arg: ast.unparse(keyword.value) for keyword in node.keywords}
		for node in ast.walk(tree)
		if isinstance(node, ast.Call) and ast.unparse(node.func) == "SymbolDictionaryDefinition"
	]
	builtin = [definition for definition in definitions if definition.get("name") == "'builtin'"]
	assert builtin == [
		{
			"name": "'builtin'",
			"path": "os.path.join(globalVars.appDir, 'locale', '{locale}', 'symbols.dic')",
			"source": "_SymbolDefinitionSource.BUILTIN",
			"allowComplexSymbols": "True",
			"mandatory": "True",
		},
	]


def test_normalize_language_is_nvdas():
	normalize = nvda_normalize_language()
	assert normalize("zh-tw") == "zh_TW"
	assert normalize("ZH") == "zh"
	assert normalize("x-western") is None


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
	names = {symbol: character_processing.processSpeechSymbol(locale, symbol) for symbol in NUMBER_SYMBOLS}
	assert [symbol for symbol, name in names.items() if name in ("", None, symbol)] == []
	# Spec 8: the punctuation stage never splits a name, because no en or zh_TW name holds a
	# number symbol. fr's "point d'exclamation" does (final review M1), a known limit.
	assert {symbol: name for symbol, name in names.items() if set(name) & set(NUMBER_SYMBOLS)} == {}


@NVDA_WARNINGS
def test_pipeline_names_symbols_with_nvdas_real_lookup(module, monkeypatch, tmp_path):
	monkeypatch.setattr(module, "characterProcessing", load_nvda_character_processing(monkeypatch, tmp_path))
	monkeypatch.setattr(module.speech, "getCurrentLanguage", lambda: "zh_TW")
	assert module.symbol_name(module.symbol_locale("zh"), "×") == "乘以"


# ASCII ids: an id pytest escaped from "乘以" could not be selected on the command line, which mutmut does.
@pytest.mark.parametrize(("voice", "name"), [("zh-TW", "乘以"), ("zh_SG", "times")], ids=["zh-TW", "zh_SG"])
@NVDA_WARNINGS
def test_pipeline_names_symbols_from_the_voice_locale_with_nvdas_real_lookup(
	module,
	monkeypatch,
	tmp_path,
	voice,
	name,
):
	# NVDA's interface in English: a zh-TW voice gets its own table; zh_SG has none, so NVDA's
	# fallback from "zh" ends in English.
	monkeypatch.setattr(module, "characterProcessing", load_nvda_character_processing(monkeypatch, tmp_path))
	monkeypatch.setattr(module.speech, "getCurrentLanguage", lambda: "en")
	assert module.symbol_name(module.symbol_locale("zh", voice), "×") == name
