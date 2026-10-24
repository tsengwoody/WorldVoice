"""The pipeline filters' output, pinned before their loops were shared."""

import sys
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest
from nvda_stubs import RefusingSection
from pipeline_harness import load_pipeline_module, load_settings_module, punctuation_settings, symbol_name


@pytest.fixture
def env(monkeypatch):
	settings = punctuation_settings(0)
	module, _ = load_pipeline_module(monkeypatch, settings)
	return SimpleNamespace(module=module, settings=settings)


def shape(sequence):
	result = []
	for item in sequence:
		if isinstance(item, str):
			result.append(item)
		elif hasattr(item, "lang"):
			result.append(("lang", item.lang))
		else:
			result.append((type(item).__name__, item.time))
	return result


def ctx(module, names, default):
	"""A WorldVoice context whose languages resolve to the given voice names."""
	return module.SpeechContext(
		supports_roles=True,
		language=default.language,
		number_language="de",
		default_voice_name=default.name,
		default_voice_language=default.language,
		voice_name_for_language=names.get,
	)


@pytest.mark.parametrize(
	"sequence,expected",
	[
		([], []),
		(["a"], ["a"]),
		(["", "b"], ["", ("BreakCommand", 30), "b"]),
	],
)
def test_item_wait_factor_edges(env, sequence, expected):
	env.settings.scaled_item_wait = lambda: 30
	assert shape(env.module.item_wait_factor(sequence, env.settings, env.module.GENERIC_CONTEXT)) == expected


@pytest.mark.parametrize(
	("wait", "expected"),
	[(1, ["a", ("BreakCommand", 1), "b"]), (0, ["a", "b"])],
	ids=["1-ms", "0-ms"],
)
def test_the_shortest_item_wait_breaks(env, wait, expected):
	# An item wait of 1 ms is a pause; 0 is none (review M4, mutmut).
	sequence = ["a", "b"]
	env.settings.scaled_item_wait = lambda: wait
	assert shape(env.module.item_wait_factor(sequence, env.settings, env.module.GENERIC_CONTEXT)) == expected


def test_item_wait_factor_breaks_only_between_adjacent_text(env):
	env.settings.scaled_item_wait = lambda: 30
	marker = env.module.BreakCommand(5)
	result = list(
		env.module.item_wait_factor(["a", "b", marker, "c", "d"], env.settings, env.module.GENERIC_CONTEXT),
	)
	assert shape(result) == [
		"a",
		("BreakCommand", 30),
		"b",
		("BreakCommand", 5),
		"c",
		("BreakCommand", 30),
		"d",
	]
	assert result[1] is result[5]
	assert result[3] is marker


def test_item_wait_factor_off_passes_through(env):
	assert list(env.module.item_wait_factor(["a", "b"], env.settings, env.module.GENERIC_CONTEXT)) == [
		"a",
		"b",
	]


def test_number_wait_factor_drops_blanks_then_breaks_between_numbers(env):
	env.settings.scaled_number_wait = lambda: 40
	result = list(
		env.module.number_wait_factor(
			["1", " ", "2", "a", "3", "4"],
			env.settings,
			env.module.GENERIC_CONTEXT,
		),
	)
	assert shape(result) == ["1", ("NumberBreakCommand", 40), "2", "a", "3", ("NumberBreakCommand", 40), "4"]
	assert result[1] is result[5]


@pytest.mark.parametrize(
	"sequence,expected",
	[
		(["12", "3"], ["12", ("NumberBreakCommand", 40), "3"]),
		(["-3.5", "4"], ["-3.5", ("NumberBreakCommand", 40), "4"]),
		(["12abc", "3"], ["12abc", "3"]),
		(["1.", "2"], ["1.", "2"]),
		(["3", "12abc"], ["3", "12abc"]),
		(["5-3", "4"], ["5-3", ("NumberBreakCommand", 40), "4"]),
		(["12:30", "1"], ["12:30", ("NumberBreakCommand", 40), "1"]),
	],
)
def test_number_wait_breaks_only_between_whole_numbers(env, sequence, expected):
	env.settings.scaled_number_wait = lambda: 40
	assert (
		shape(env.module.number_wait_factor(sequence, env.settings, env.module.GENERIC_CONTEXT)) == expected
	)


@pytest.mark.parametrize(
	("text", "matches"),
	[
		("12,345,678", ["12,345,678"]),
		("1,234.56", ["1,234.56"]),
		("-1234", ["-1234"]),
		("5-3", ["5-3"]),
		("5 -3", ["5", "-3"]),
		("2026-10-22 12:30", ["2026-10-22", "12:30"]),
		("192.168.0.1", ["192.168.0.1"]),
		# Full-width punctuation is not a number symbol.
		("12\uff0c34", ["12", "34"]),
		("abc1 2def", ["1", "2"]),
		# A sign is a + or - right before a digit and not right after one.
		("a-3", ["-3"]),
		("--3", ["-3"]),
		("3.+4", ["3.+4"]),
		("+3 a+4", ["+3", "+4"]),
		# A no-break space is whitespace and a soft hyphen a format character: neither joins digits.
		("1\u00a02", ["1", "2"]),
		("1\u00ad2", ["1", "2"]),
		("1'000", ["1'000"]),
		("1_000", ["1_000"]),
		("1\u00d72", ["1\u00d72"]),
		# Digits are Unicode decimal digits (Nd): full-width and Arabic-Indic ones too. Separators stay
		# Latin-1, so a full-width or Arabic decimal separator splits the number; superscripts and
		# circled digits are not digits.
		("１２", ["１２"]),
		("٣٫١٤", ["٣", "١٤"]),
		("１２．５", ["１２", "５"]),
		("x²", []),
		("10²", ["10"]),
		("①", []),
		("12.", ["12"]),
	],
)
def test_number_re_finds_whole_numbers(env, text, matches):
	assert [match.group() for match in env.module.numbers.NUMBER_RE.finditer(text)] == matches


@pytest.mark.parametrize("text", ["1" * 5000 + "a", "1." * 3000 + "a"])
def test_number_re_fullmatch_fails_fast(env, text):
	start = time.perf_counter()
	assert env.module.numbers.NUMBER_RE.fullmatch(text) is None
	assert time.perf_counter() - start < 0.5


B40 = ("NumberBreakCommand", 40)
NB0 = ("NumberBreakCommand", 0)
SPLITS = [
	("1 2", ["1", B40, "2"]),
	("共 12 34 個", ["共 ", "12", B40, "34", " 個"]),
	("5 -3", ["5", B40, "-3"]),
	("5 - 3", ["5 - 3"]),
	("1.2.3 4", ["1.2.3", B40, "4"]),
	("12 apples", ["12 apples"]),
	("abc1 2def", ["abc", "1", B40, "2", "def"]),
	("2026 10 21", ["2026", B40, "10", B40, "21"]),
	("12\u300034", ["12", B40, "34"]),
	("1\t2", ["1", B40, "2"]),
	("1\n2", ["1", B40, "2"]),
	# Decided by the user (2026-10-22): a no-break space is ordinary whitespace for the split, so
	# "10 000" written with one is two numbers with a pause between them.
	("1\u00a02", ["1", B40, "2"]),
	("10\u00a0000", ["10", B40, "000"]),
	("1\u202f234\u202f567", ["1", B40, "234", B40, "567"]),
	("1\u20072", ["1", B40, "2"]),
	("1 \u00a02", ["1", B40, "2"]),
	("10\u00a0000 5", ["10", B40, "000", B40, "5"]),
	("2 10\u00a0000", ["2", B40, "10", B40, "000"]),
	("1-2", ["1-2"]),
	("12abc 3", ["12abc 3"]),
	# One number definition: a match never touches another, so every whitespace gap splits.
	("02 2345-6789", ["02", B40, "2345-6789"]),
	("3-1 2", ["3-1", B40, "2"]),
	("1 2 3-4", ["1", B40, "2", B40, "3-4"]),
	("1-2 3 4", ["1-2", B40, "3", B40, "4"]),
	("2026-10-22 12:30", ["2026-10-22", B40, "12:30"]),
	("12,345 6", ["12,345", B40, "6"]),
	("１ ２", ["１", B40, "２"]),
	("١ ٢", ["١", B40, "٢"]),
]


class Marker:
	"""A speech command no stage knows, such as NVDA's IndexCommand."""


def language_commands(module):
	"""WorldVoice's WVLangChangeCommand and NVDA's LangChangeCommand: both are transparent."""
	return [module.WVLangChangeCommand, sys.modules["speech.commands"].LangChangeCommand]


def number_wait(env, sequence):
	env.settings.scaled_number_wait = lambda: 40
	return list(env.module.number_wait_factor(sequence, env.settings, env.module.GENERIC_CONTEXT))


@pytest.mark.parametrize("kind", [0, 1], ids=["WVLangChangeCommand", "LangChangeCommand"])
def test_number_wait_breaks_between_numbers_across_language_commands(env, kind):
	command = language_commands(env.module)[kind]
	sequence = [command("en"), "1", command("zh"), " ", command("en"), "2", command("zh")]
	assert shape(number_wait(env, sequence)) == [
		("lang", "en"),
		"1",
		("lang", "zh"),
		B40,
		("lang", "en"),
		"2",
		("lang", "zh"),
	]


@pytest.mark.parametrize(
	"kind,lang",
	[(0, "zh"), (1, None)],
	ids=["WVLangChangeCommand", "LangChangeCommand"],
)
def test_number_wait_breaks_after_a_single_language_command(env, kind, lang):
	command = language_commands(env.module)[kind](lang)
	assert shape(number_wait(env, ["1", command, "2"])) == ["1", ("lang", lang), B40, "2"]


@pytest.mark.parametrize("blocker", ["index", "break"])
def test_number_wait_does_not_break_across_other_commands(env, blocker):
	command = env.module.WVLangChangeCommand
	blocker = Marker() if blocker == "index" else env.module.BreakCommand(5)
	result = number_wait(env, ["1", command("zh"), blocker, command("en"), "2"])
	assert not any(isinstance(item, env.module.NumberBreakCommand) for item in result)
	assert result[2] is blocker


def test_number_wait_keeps_held_language_commands_at_the_end(env):
	assert shape(number_wait(env, ["1", env.module.WVLangChangeCommand("zh")])) == ["1", ("lang", "zh")]


def test_number_wait_does_not_break_between_a_number_and_text_across_language_commands(env):
	sequence = ["1", env.module.WVLangChangeCommand("zh"), "abc"]
	assert shape(number_wait(env, sequence)) == ["1", ("lang", "zh"), "abc"]


@pytest.mark.parametrize("text,expected", SPLITS)
def test_number_wait_splits_numbers_separated_only_by_whitespace(env, text, expected):
	env.settings.scaled_number_wait = lambda: 40
	assert shape(env.module.number_wait_factor([text], env.settings, env.module.GENERIC_CONTEXT)) == expected


def test_the_shortest_number_wait_still_breaks(env):
	env.settings.scaled_number_wait = lambda: 1
	assert shape(env.module.number_wait_factor(["1 2"], env.settings, env.module.GENERIC_CONTEXT)) == [
		"1",
		("NumberBreakCommand", 1),
		"2",
	]


def test_number_wait_inserts_number_break_commands(env):
	env.settings.scaled_number_wait = lambda: 40
	result = list(env.module.number_wait_factor(["1 2"], env.settings, env.module.GENERIC_CONTEXT))
	assert isinstance(result[1], env.module.NumberBreakCommand)
	assert isinstance(result[1], env.module.BreakCommand)
	assert result[1].time == 40


def test_number_wait_splits_across_items_and_keeps_commands(env):
	env.settings.scaled_number_wait = lambda: 40
	marker = env.module.BreakCommand(5)
	result = list(
		env.module.number_wait_factor(["5", "1 2", marker, "3 4"], env.settings, env.module.GENERIC_CONTEXT),
	)
	assert shape(result) == ["5", B40, "1", B40, "2", ("BreakCommand", 5), "3", B40, "4"]
	assert result[1] is result[3] is result[7]
	assert result[5] is marker


def test_digit_mode_then_number_wait_pauses_between_digits(env):
	env.settings.number_mode = "number"
	env.settings.scaled_number_wait = lambda: 40
	digits = env.module.inject_numbers(["12"], env.settings, env.module.GENERIC_CONTEXT)
	assert shape(env.module.number_wait_factor(digits, env.settings, env.module.GENERIC_CONTEXT)) == [
		"1",
		B40,
		"2",
	]


def N(symbol, locale="en"):
	"""The harness's name of a symbol: GENERIC_CONTEXT looks names up in NVDA's current language, "en"."""
	return symbol_name(locale, symbol)


def broken(pause, *items):
	"""*items* with a number break of *pause* between each two."""
	result = []
	for item in items:
		if result:
			result.append(("NumberBreakCommand", pause))
		result.append(item)
	return result


def spoken(pieces, pause=0):
	"""Space-separated pieces, where "<x>" stands for the name of the symbol x."""
	return broken(pause, *(N(piece[1:-1]) if piece.startswith("<") else piece for piece in pieces.split()))


@pytest.mark.parametrize("wait", [0, 40])
def test_digit_mode_separates_digits_with_the_number_wait(env, wait):
	env.settings.number_mode = "number"
	env.settings.scaled_number_wait = lambda: wait
	generic = env.module.GENERIC_CONTEXT
	assert shape(env.module.inject_numbers(["12"], env.settings, generic)) == [
		"1",
		("NumberBreakCommand", wait),
		"2",
	]
	result = list(env.module.inject_numbers(["-1234"], env.settings, generic))
	assert result[0::2] == ["-1", "2", "3", "4"]
	first, *others = result[1::2]
	assert all(other is first for other in others)


@pytest.mark.parametrize(
	("text", "pieces"),
	[
		("A12B", "A1 2B"),
		("3.14", "3 <.> 1 4"),
		("1a2", "1a2"),
		("v1.2", "v1 <.> 2"),
	],
)
def test_digit_mode_breaks_between_digits_and_around_symbols(env, text, pieces):
	env.settings.number_mode = "number"
	result = env.module.inject_numbers([text], env.settings, env.module.GENERIC_CONTEXT)
	assert shape(result) == spoken(pieces)


def test_group_mode_then_number_wait_breaks_with_the_number_wait(env):
	env.settings.number_mode = "group"
	env.settings.group_size = 2
	env.settings.scaled_number_wait = lambda: 40
	groups = env.module.inject_numbers(["1234 5678"], env.settings, env.module.GENERIC_CONTEXT)
	assert shape(env.module.number_wait_factor(groups, env.settings, env.module.GENERIC_CONTEXT)) == broken(
		40,
		"12",
		"34",
		"56",
		"78",
	)


E50 = ("NumberEdgeBreakCommand", 50)
TEXTS = ["12.5", "-1234", "123", "12", "v1.2", "a. 3", "3.", ".5", "1.2.3", ""]
# The dot rule: a "." outside a number is spoken apart from it, in every mode but "off".
SHARED = {"a. 3": ["a. 3"], "3.": ["3 ."], ".5": [". 5"], "": []}
# Keyed by (mode, group size, number pause).
NUMBER_MODES = {
	("value", 3, 0): {
		"12.5": ["12.5"],
		"-1234": ["-1234"],
		"123": ["123"],
		"12": ["12"],
		"v1.2": ["v1.2"],
		"1.2.3": ["1.2.3"],
	},
	# Digit mode: every digit and every symbol is an item of its own, even at pause 0.
	("number", 3, 0): {
		"12.5": spoken("1 2 <.> 5"),
		"-1234": spoken("-1 2 3 4"),
		"123": spoken("1 2 3"),
		"12": spoken("1 2"),
		"v1.2": spoken("v1 <.> 2"),
		"1.2.3": spoken("1 <.> 2 <.> 3"),
	},
	# Groups are cut from the left, the sign joins the first, and a symbol is named apart.
	("group", 2, 0): {
		"12.5": spoken("12 <.> 5"),
		"-1234": spoken("-12 34"),
		"123": spoken("12 3"),
		"12": ["12"],
		"v1.2": spoken("v1 <.> 2"),
		"1.2.3": spoken("1 <.> 2 <.> 3"),
	},
	# A number pause above 0 also sets a number apart from the text of its item (number-edge-pause
	# spec, decided by the user 2026-10-24).
	("group", 2, 50): {
		"12.5": spoken("12 <.> 5", 50),
		"-1234": spoken("-12 34", 50),
		"123": spoken("12 3", 50),
		"12": ["12"],
		"v1.2": ["v", E50, *spoken("1 <.> 2", 50)],
		"1.2.3": spoken("1 <.> 2 <.> 3", 50),
		"a. 3": ["a. ", E50, "3"],
		"3.": ["3", E50, " ."],
		".5": [". ", E50, "5"],
	},
	("group", 3, 0): {
		"12.5": spoken("12 <.> 5"),
		"-1234": spoken("-123 4"),
		"123": ["123"],
		"12": ["12"],
		"v1.2": spoken("v1 <.> 2"),
		"1.2.3": spoken("1 <.> 2 <.> 3"),
	},
	("group", 10, 0): {
		"12.5": spoken("12 <.> 5"),
		"-1234": ["-1234"],
		"123": ["123"],
		"12": ["12"],
		"v1.2": spoken("v1 <.> 2"),
		"1.2.3": spoken("1 <.> 2 <.> 3"),
	},
}


@pytest.mark.parametrize("mode,size,pause", sorted(NUMBER_MODES))
@pytest.mark.parametrize("text", TEXTS)
def test_number_mode(env, mode, size, pause, text):
	env.settings.number_mode = mode
	env.settings.group_size = size
	env.settings.scaled_number_wait = lambda: pause
	expected = {**SHARED, **NUMBER_MODES[(mode, size, pause)]}[text]
	assert shape(env.module.inject_numbers([text], env.settings, env.module.GENERIC_CONTEXT)) == expected


# Spec 7.1: (input, number, group 3, group 2), each as space-separated pieces.
SPEC_TABLE = [
	("12,345,678", "1 2 <,> 3 4 5 <,> 6 7 8", "12 <,> 345 <,> 678", "12 <,> 34 5 <,> 67 8"),
	("1,234.56", "1 <,> 2 3 4 <.> 5 6", "1 <,> 234 <.> 56", "1 <,> 23 4 <.> 56"),
	("123.456", "1 2 3 <.> 4 5 6", "123 <.> 456", "12 3 <.> 45 6"),
	("12.5", "1 2 <.> 5", "12 <.> 5", "12 <.> 5"),
	("-1234", "-1 2 3 4", "-123 4", "-12 34"),
	("5-3", "5 <-> 3", "5 <-> 3", "5 <-> 3"),
	("2026-10-22", "2 0 2 6 <-> 1 0 <-> 2 2", "202 6 <-> 10 <-> 22", "20 26 <-> 10 <-> 22"),
	(
		"192.168.0.1",
		"1 9 2 <.> 1 6 8 <.> 0 <.> 1",
		"192 <.> 168 <.> 0 <.> 1",
		"19 2 <.> 16 8 <.> 0 <.> 1",
	),
	("3,14", "3 <,> 1 4", "3 <,> 14", "3 <,> 14"),
	("2×3", "2 <×> 3", "2 <×> 3", "2 <×> 3"),
	("6÷2", "6 <÷> 2", "6 <÷> 2", "6 <÷> 2"),
	("45°30", "4 5 <°> 3 0", "45 <°> 30", "45 <°> 30"),
]


# ASCII ids without backslashes: pytest escapes a non-ASCII id in place, so a second collection in
# one process (mutmut's clean run) escapes it again and can no longer select it.
SPEC_IDS = ["".join(c if c.isascii() else f"U+{ord(c):04X}" for c in row[0]) for row in SPEC_TABLE]


@pytest.mark.parametrize(("mode", "size", "column"), [("number", 1, 1), ("group", 3, 2), ("group", 2, 3)])
@pytest.mark.parametrize("row", SPEC_TABLE, ids=SPEC_IDS)
def test_number_and_group_modes_name_each_symbol(env, mode, size, column, row):
	env.settings.number_mode = mode
	env.settings.group_size = size
	result = env.module.inject_numbers([row[0]], env.settings, env.module.GENERIC_CONTEXT)
	assert shape(result) == spoken(row[column])


@pytest.mark.parametrize("pause", [0, 25])
def test_number_breaks_use_the_number_pause(env, pause):
	env.settings.number_mode = "group"
	env.settings.scaled_number_wait = lambda: pause
	result = list(env.module.inject_numbers(["1,234.5"], env.settings, env.module.GENERIC_CONTEXT))
	breaks = [item for item in result if not isinstance(item, str)]
	assert breaks
	assert all(type(item) is env.module.NumberBreakCommand and item.time == pause for item in breaks)
	assert not hasattr(env.module, "GroupNumberBreakCommand")


def test_adjacent_symbols_get_a_name_each(env):
	env.settings.number_mode = "number"
	result = env.module.inject_numbers(["1--2"], env.settings, env.module.GENERIC_CONTEXT)
	assert shape(result) == spoken("1 <-> <-> 2")


def roles_context(module, language, number_language):
	return module.SpeechContext(
		supports_roles=True,
		language=language,
		number_language=number_language,
		default_voice_name="Z",
		default_voice_language=language,
		voice_name_for_language={"zh_TW": "Z", "en": "E", "de": "D"}.get,
	)


def names_in(result):
	return [item for item in result if isinstance(item, str) and item.startswith("multiplication sign")]


def test_symbol_names_follow_the_number_language(env):
	env.settings.number_mode = "number"
	command = env.module.WVLangChangeCommand
	ctx = roles_context(env.module, "zh_TW", "en")
	result = list(env.module.inject_numbers([command("en"), "2×3", command("zh_TW")], env.settings, ctx))
	assert names_in(result) == [N("×", "en")]


def test_symbol_names_follow_language_commands_with_default_number_language(env):
	env.settings.number_mode = "number"
	wv, nvda = env.module.WVLangChangeCommand, sys.modules["speech.commands"].LangChangeCommand
	ctx = roles_context(env.module, "zh_TW", "default")
	sequence = ["2×3", wv("de"), "2×3", nvda(None), "2×3"]
	result = list(env.module.inject_numbers(sequence, env.settings, ctx))
	assert names_in(result) == [N("×", "zh_TW"), N("×", "de"), N("×", "zh_TW")]


def test_symbol_names_follow_language_commands_with_main_number_language(env):
	# "main" is not a locale: symbols are named in the language in force, as for "default".
	env.settings.number_mode = "number"
	wv, nvda = env.module.WVLangChangeCommand, sys.modules["speech.commands"].LangChangeCommand
	ctx = roles_context(env.module, "zh_TW", "main")
	sequence = ["2×3", wv("de"), "2×3", nvda(None), "2×3"]
	result = list(env.module.inject_numbers(sequence, env.settings, ctx))
	assert names_in(result) == [N("×", "zh_TW"), N("×", "de"), N("×", "zh_TW")]


def test_symbol_names_follow_the_voice_locale(env, monkeypatch):
	# Decided by the user (2026-10-22): the locale of the voice for the number language, or for
	# the language in force, wins over NVDA's interface language.
	env.settings.number_mode = "number"
	monkeypatch.setattr(env.module.symbols.speech, "getCurrentLanguage", lambda: "en")
	ctx = replace(roles_context(env.module, "zh", "en"), voice_locale_for_language={"en": "zh-TW"}.get)
	assert names_in(env.module.inject_numbers(["2×3"], env.settings, ctx)) == [N("×", "zh_TW")]
	ctx = replace(roles_context(env.module, "zh", "default"), voice_locale_for_language={"zh": "zh_CN"}.get)
	assert names_in(env.module.inject_numbers(["2×3"], env.settings, ctx)) == [N("×", "zh_CN")]


def test_symbol_names_without_roles_ignore_the_number_language(env):
	env.settings.number_mode = "number"
	ctx = env.module.SpeechContext(supports_roles=False, language="fr", number_language="en")
	assert names_in(env.module.inject_numbers(["2×3"], env.settings, ctx)) == [N("×", "fr")]


def test_symbol_names_without_a_language_use_nvdas_current_language(env, monkeypatch):
	env.settings.number_mode = "number"
	monkeypatch.setattr(env.module.symbols.speech, "getCurrentLanguage", lambda: "de")
	result = env.module.inject_numbers(["2×3"], env.settings, env.module.GENERIC_CONTEXT)
	assert names_in(result) == [N("×", "de")]


def counting_lookup(env, monkeypatch, unnamed=""):
	"""Record each symbol looked up; the symbols in *unnamed* have no name."""
	calls = []

	def lookup(locale, symbol):
		calls.append(symbol)
		return symbol if symbol in unnamed else symbol_name(locale, symbol)

	monkeypatch.setattr(env.module.symbols.characterProcessing, "processSpeechSymbol", lookup)
	return calls


@pytest.mark.parametrize("mode", ["value", "none"])
def test_value_and_off_leave_symbols_alone(env, monkeypatch, mode):
	calls = counting_lookup(env, monkeypatch)
	env.settings.number_mode = mode
	assert list(env.module.inject_numbers(["2×3"], env.settings, env.module.GENERIC_CONTEXT)) == [
		"2×3",
	]
	assert calls == []


def test_a_symbol_without_a_name_is_its_own_item(env, monkeypatch):
	# Decided by the user (2026-10-22): a symbol NVDA has no name for (a user can clear its
	# replacement) is sent as itself, between number breaks like a name; NVDA then decides its sound.
	counting_lookup(env, monkeypatch, unnamed=".")
	generic = env.module.GENERIC_CONTEXT
	env.settings.number_mode = "group"
	assert shape(env.module.inject_numbers(["123.456"], env.settings, generic)) == spoken("123 . 456")
	env.settings.number_mode = "number"
	assert shape(env.module.inject_numbers(["12.5"], env.settings, generic)) == spoken("1 2 . 5")
	assert shape(env.module.inject_numbers(["1-.2"], env.settings, generic)) == spoken("1 <-> . 2")


def test_an_unnamed_symbol_and_a_named_one_are_two_items(env, monkeypatch):
	# The batch 2 review I1 input: no name ever takes the next digits.
	counting_lookup(env, monkeypatch, unnamed=".")
	env.settings.number_mode = "number"
	result = env.module.inject_numbers(["1.-2"], env.settings, env.module.GENERIC_CONTEXT)
	assert shape(result) == spoken("1 . <-> 2")


NB10, B10 = ("NumberBreakCommand", 10), ("BreakCommand", 10)


@pytest.mark.parametrize(
	("roles", "remove", "expected"),
	[
		# Pause only: the mark stays; the number breaks around it already pause, so no punctuation pause.
		(True, False, ["12", NB10, ".", NB10, "5"]),
		# Removal drops the mark and the number break after it (final review M2): one pause, not two.
		(True, True, ["12", NB10, "5"]),
		# Another synthesizer (scope "all") gets plain breaks from every stage, so the punctuation
		# stage cannot tell the number breaks from any other break: a known limit (spec 6.4.1).
		(False, False, ["12", B10, ".", B10, "5"]),
		(False, True, ["12", B10, B10, "5"]),
	],
)
def test_an_unnamed_symbol_is_left_to_the_punctuation_stage(env, monkeypatch, roles, remove, expected):
	# Accepted by the user (2026-10-22): an unnamed symbol is an item of its own, so the punctuation
	# stage may pause at it and remove it; the digits around it still reach the synth apart.
	counting_lookup(env, monkeypatch, unnamed=".")
	env.settings.number_mode = "group"
	env.settings.scaled_number_wait = lambda: 10
	env.settings.punctuation_pause_enabled = True
	env.settings.punctuation_pause_characters = "."
	env.settings.remove_punctuation_characters = remove
	context = roles_context(env.module, "zh_TW", "default") if roles else env.module.GENERIC_CONTEXT
	monkeypatch.setattr(env.module, "current_context", lambda: context)
	sequence = ["12.5"]
	for stage in env.module.STAGES:
		sequence = stage.handler(sequence)
	assert shape(sequence) == expected


def test_long_symbol_runs_look_each_symbol_up_once_per_item(env, monkeypatch):
	# Review Focus 3: an IP list or a version string must not cost one NVDA lookup per symbol.
	calls = counting_lookup(env, monkeypatch)
	languages = []
	monkeypatch.setattr(
		env.module.symbols.speech,
		"getCurrentLanguage",
		lambda: languages.append("en") or "en",
	)
	env.settings.number_mode = "number"
	start = time.perf_counter()
	result = list(
		env.module.inject_numbers(["1." * 3000 + "1"], env.settings, env.module.GENERIC_CONTEXT),
	)
	assert time.perf_counter() - start < 2
	assert (calls, len(languages)) == (["."], 1)
	assert result.count(N(".")) == 3000


@pytest.mark.parametrize(
	("size", "text", "expected"),
	[
		(3, "0912345678", spoken("091 234 567 8")),
		(2, "007", spoken("00 7")),
		(3, "+0012", spoken("+001 2")),
	],
)
def test_group_mode_keeps_leading_zeros_and_every_digit(env, size, text, expected):
	env.settings.number_mode = "group"
	env.settings.group_size = size
	assert shape(env.module.inject_numbers([text], env.settings, env.module.GENERIC_CONTEXT)) == expected


@pytest.mark.parametrize("pause", [0, 50])
def test_group_separator_is_one_instance_per_number(env, pause):
	env.settings.number_mode = "group"
	env.settings.group_size = 2
	env.settings.scaled_number_wait = lambda: pause
	result = list(env.module.inject_numbers(["123456"], env.settings, env.module.GENERIC_CONTEXT))
	assert result[0::2] == ["12", "34", "56"]
	first, second = result[1::2]
	assert first is second
	assert first.time == pause


def test_a_stored_pair_mode_reads_numbers_as_values(env, monkeypatch):
	conf = {"WorldVoice": {"pipeline": {"number_mode": "pair", "group_size": 2}}}
	stored = load_settings_module(monkeypatch, conf).pipeline_settings.get()
	assert list(env.module.inject_numbers(["1234"], stored, env.module.GENERIC_CONTEXT)) == ["1234"]


@pytest.mark.parametrize(
	("text", "expected"),
	[
		("１２,３４５", "１２３４５"),
		("١٢,٣٤٥", "١٢٣٤٥"),
		# Not thousands runs: the lookarounds count every decimal digit.
		("１２,３４５６", "１２,３４５６"),
		("１２３４,５６７", "１２３４,５６７"),
	],
)
def test_thousands_separators_of_other_digits(env, text, expected):
	result = env.module.remove_thousands_separators([text], env.settings, env.module.GENERIC_CONTEXT)
	assert list(result) == [expected]


@pytest.mark.parametrize(
	("mode", "size", "text", "expected"),
	[("group", 3, "１２３４５", ["１２３", NB0, "４５"]), ("number", 1, "٣٤", ["٣", NB0, "٤"])],
)
def test_group_and_number_modes_keep_the_original_digits(env, mode, size, text, expected):
	# Decided by the user (2026-10-23): pieces keep the characters they were written with.
	env.settings.number_mode = mode
	env.settings.group_size = size
	assert shape(env.module.inject_numbers([text], env.settings, env.module.GENERIC_CONTEXT)) == expected


def test_number_language_wraps_each_number(env):
	english = SimpleNamespace(name="A:en", language="en")
	context = ctx(env.module, {"en": "A:en", "de": "A:de"}, english)
	result = env.module.inject_numbers(["a1b2"], env.settings, context)
	assert shape(result) == [
		"a",
		("lang", "de"),
		"1",
		("lang", "en"),
		"b",
		("lang", "de"),
		"2",
		("lang", "en"),
	]
	assert list(env.module.inject_numbers([""], env.settings, context)) == []


def test_main_number_language_passes_through_the_early_stage(env):
	# A "main" wrapper would name the language in force, which the stage's dedupe drops (spec §4.4).
	english = SimpleNamespace(name="A:en", language="en")
	context = replace(ctx(env.module, {"en": "A:en", "zh": "B:zh"}, english), number_language="main")
	items = ["a1b2", env.module.WVLangChangeCommand("zh"), "3"]
	result = list(env.module.inject_numbers(items, env.settings, context))
	# Value mode merges the text it reads, so the strings are equal, not the same objects.
	assert result == ["a1b2", items[1], "3"]
	assert result[1] is items[1]


def test_number_language_leaves_a_sign_after_a_word_with_it(env):
	# Decided by the user (2026-10-23, U2): "a-1" and "中+2" keep their sign; " -3" moves it.
	english = SimpleNamespace(name="A:en", language="en")
	context = ctx(env.module, {"en": "A:en", "de": "A:de"}, english)
	result = env.module.inject_numbers(["a-1 中+2 -3"], env.settings, context)
	assert shape(result) == [
		"a-",
		("lang", "de"),
		"1",
		("lang", "en"),
		" 中+",
		("lang", "de"),
		"2",
		("lang", "en"),
		" ",
		("lang", "de"),
		"-3",
		("lang", "en"),
	]


@pytest.mark.parametrize(
	("mode", "voice", "expected"),
	[
		("value", "E", [("lang", "en"), "12", ("lang", "zh_TW"), ". Next"]),
		("number", "E", [("lang", "en"), "1", ("NumberBreakCommand", 0), "2", ("lang", "zh_TW"), ". Next"]),
		("value", "Z", ["12 . Next"]),
		("number", "Z", ["1", ("NumberBreakCommand", 0), "2 . Next"]),
	],
	ids=["value-kept", "number-pause-0-kept", "value-dropped", "number-pause-0-dropped"],
)
def test_the_dot_rule_spaces_only_numbers_whose_wrapper_goes(env, mode, voice, expected):
	# Number-edge-pause spec D5 (review I1): as before the stages were merged, the dot rule spaces
	# a period only where the number stays in the text's voice; next to a number read by another
	# voice the space could be a new punctuation pause point.
	env.settings.number_mode = mode
	context = replace(
		roles_context(env.module, "zh_TW", "en"),
		voice_name_for_language={"zh_TW": "Z", "en": voice}.get,
	)
	assert shape(env.module.inject_numbers(["12. Next"], env.settings, context)) == expected


def test_the_dot_rule_reads_the_language_in_force(env):
	# The wrapper of an en number goes inside NVDA's en stretch, though the context's language is
	# zh_TW, so the period is spaced (review M4, mutmut: the start language of the check).
	env.settings.number_mode = "value"
	LangChangeCommand = sys.modules["speech.commands"].LangChangeCommand
	sequence = [LangChangeCommand("en"), "12. Next"]
	result = env.module.inject_numbers(sequence, env.settings, roles_context(env.module, "zh_TW", "en"))
	assert shape(result) == [("lang", "en"), "12 . Next"]


@pytest.mark.parametrize("numlan", ["default", "main", "en"])
def test_off_mode_wraps_only_for_a_locale(env, numlan):
	env.settings.number_mode = "none"
	sequence = ["第3章"]
	result = list(
		env.module.inject_numbers(sequence, env.settings, roles_context(env.module, "zh_TW", numlan)),
	)
	if numlan == "en":
		assert shape(result) == ["第", ("lang", "en"), "3", ("lang", "zh_TW"), "章"]
	else:
		assert len(result) == 1 and result[0] is sequence[0]


def test_chinese_space_pause(env):
	env.settings.scaled_chinesespace_wait = lambda: 20
	result = env.module.inject_chinese_space_pause(
		["中 文 abc 中 文"],
		env.settings,
		env.module.GENERIC_CONTEXT,
	)
	assert shape(result) == ["中", ("BreakCommand", 20), "文 abc 中", ("BreakCommand", 20), "文"]
	env.settings.scaled_chinesespace_wait = lambda: 0
	assert list(
		env.module.inject_chinese_space_pause(["中 文"], env.settings, env.module.GENERIC_CONTEXT),
	) == ["中 文"]


def test_punctuation_segments(env):
	regex = env.module._get_punctuation_regex(".,")
	assert list(env.module._split_punctuation_segments("a, b,, 12,500. c", regex)) == [
		("text", "a"),
		("punct", ","),
		("text", " b"),
		("punct", ",,"),
		("text", " 12,500"),
		("punct", "."),
		("text", " c"),
	]


@pytest.mark.parametrize(
	"level,enable,label_on,writes",
	[
		("INFO", False, True, []),
		("INFO", True, False, []),
		("INFO", True, True, ["before", "after"]),
		("DEBUG", False, True, []),
	],
)
def test_run_logged_records_only_when_switched_on(env, monkeypatch, level, enable, label_on, writes):
	import sys

	conf = sys.modules["config"].conf
	conf["general"]["loggingLevel"] = level
	conf["WorldVoice"]["log"] = {"enable": enable, "number_mode": label_on}
	written = []
	monkeypatch.setattr(
		env.module,
		"pl",
		SimpleNamespace(write=lambda _id, label, timing, seq: written.append(timing)),
	)
	calls = []

	def stage(sequence, settings, ctx):
		calls.append(list(sequence))
		return iter(["out"])

	result = env.module._run_logged("number_mode", stage, ["in"], env.settings, env.module.GENERIC_CONTEXT)
	assert list(result) == ["out"]
	assert calls == [["in"]]
	assert written == writes


def test_an_invalid_log_switch_reads_off(env, monkeypatch):
	# NVDA refuses a stored "maybe" for a boolean on every read; the stage still runs, unlogged.
	settings_module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	monkeypatch.setattr(env.module, "read_stored", settings_module.read_stored)
	error = sys.modules["configobj.validate"].VdtTypeError("maybe")
	# The settings loader registered a config of its own; the pipeline keeps the one it imported.
	conf = env.module.config.conf
	conf["general"]["loggingLevel"] = "DEBUG"
	conf["WorldVoice"]["log"] = RefusingSection({}, {"enable": error, "number_mode": error})
	debugged = []
	monkeypatch.setattr(env.module.log, "debug", lambda *args, **kwargs: debugged.append(args))
	result = env.module._run_logged(
		"number_mode",
		lambda sequence, settings, ctx: iter(["out"]),
		["in"],
		None,
		None,
	)
	assert list(result) == ["out"]
	assert debugged == []
