"""The pipeline filters' output, pinned before their loops were shared."""

import re
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
		(["12abc", "3"], ["12abc", "3"]),
		(["3", "12abc"], ["3", "12abc"]),
		(["5-3", "4"], ["5-3", ("NumberBreakCommand", 40), "4"]),
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
		("-1234", ["-1234"]),
		("5-3", ["5-3"]),
		("5 -3", ["5", "-3"]),
		("2026-10-22 12:30", ["2026-10-22", "12:30"]),
		("abc1 2def", ["1", "2"]),
		# A sign is a + or - right before a digit and not right after one.
		("a-3", ["-3"]),
		("3.+4", ["3.+4"]),
		("+3 a+4", ["+3", "+4"]),
		# A no-break space is whitespace and a soft hyphen a format character: neither joins digits.
		("1\u00a02", ["1", "2"]),
		("1\u00ad2", ["1", "2"]),
		("1\u00d72", ["1\u00d72"]),
		# Digits are Unicode decimal digits (Nd): full-width and Arabic-Indic ones too. Separators stay
		# Latin-1, so a full-width or Arabic decimal separator splits the number; superscripts and
		# circled digits are not digits.
		("１２", ["１２"]),
		("٣٫١٤", ["٣", "١٤"]),
		("１２．５", ["１２", "５"]),
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
	("12 apples", ["12 apples"]),
	("abc1 2def", ["abc", "1", B40, "2", "def"]),
	("2026 10 21", ["2026", B40, "10", B40, "21"]),
	("12\u300034", ["12", B40, "34"]),
	# Decided by the user (2026-10-22): a no-break space is ordinary whitespace for the split, so
	# "10 000" written with one is two numbers with a pause between them.
	("1\u00a02", ["1", B40, "2"]),
	("10\u00a0000", ["10", B40, "000"]),
	("1-2", ["1-2"]),
	("12abc 3", ["12abc 3"]),
	# One number definition: a match never touches another, so every whitespace gap splits.
	("02 2345-6789", ["02", B40, "2345-6789"]),
	("3-1 2", ["3-1", B40, "2"]),
	("2026-10-22 12:30", ["2026-10-22", B40, "12:30"]),
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


def test_number_wait_does_not_break_across_other_commands(env):
	command = env.module.WVLangChangeCommand
	blocker = Marker()
	result = number_wait(env, ["1", command("zh"), blocker, command("en"), "2"])
	assert not any(isinstance(item, env.module.NumberBreakCommand) for item in result)
	assert result[2] is blocker


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


def test_number_wait_splits_across_items_and_keeps_commands(env):
	env.settings.scaled_number_wait = lambda: 40
	marker = env.module.BreakCommand(5)
	result = list(
		env.module.number_wait_factor(["5", "1 2", marker, "3 4"], env.settings, env.module.GENERIC_CONTEXT),
	)
	assert shape(result) == ["5", B40, "1", B40, "2", ("BreakCommand", 5), "3", B40, "4"]
	assert result[1] is result[3] is result[7]
	assert result[5] is marker


def test_digit_mode_then_number_wait_keeps_the_digits_together(env):
	# Decided by the user (2026-11-01): number mode reads the digits of a number without a pause.
	env.settings.number_mode = "number"
	env.settings.scaled_number_wait = lambda: 40
	digits = env.module.inject_numbers(["12"], env.settings, env.module.GENERIC_CONTEXT)
	assert shape(env.module.number_wait_factor(digits, env.settings, env.module.GENERIC_CONTEXT)) == ["1 2"]


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


def named(pieces):
	"""Space-separated pieces, where "<x>" stands for the name of the symbol x."""
	return [N(piece[1:-1]) if piece.startswith("<") else piece for piece in pieces.split()]


def spoken(pieces, pause=0):
	"""The pieces as group mode speaks them: a number break of *pause* between each two."""
	return broken(pause, *named(pieces))


def joined(pieces):
	"""The pieces as number mode speaks them: one item, joined with spaces (decided by the user, 2026-11-01)."""
	return [" ".join(named(pieces))]


@pytest.mark.parametrize("wait", [0, 40])
def test_digit_mode_joins_digits_with_spaces_at_any_number_wait(env, wait):
	# Decided by the user (2026-11-01): no break between the pieces of one number.
	env.settings.number_mode = "number"
	env.settings.scaled_number_wait = lambda: wait
	generic = env.module.GENERIC_CONTEXT
	assert shape(env.module.inject_numbers(["12"], env.settings, generic)) == ["1 2"]
	assert shape(env.module.inject_numbers(["-1234"], env.settings, generic)) == ["-1 2 3 4"]


@pytest.mark.parametrize(
	("text", "expected"),
	[
		("A12B", ["A1 2B"]),
		("1a2", ["1a2"]),
	],
)
def test_digit_mode_at_pause_0_keeps_the_text_around_the_digits(env, text, expected):
	env.settings.number_mode = "number"
	result = env.module.inject_numbers([text], env.settings, env.module.GENERIC_CONTEXT)
	assert shape(result) == expected


def test_value_groups_then_number_wait_break_with_the_number_wait(env):
	# The old group mode is value mode with a group size (decided by the user, 2026-11-01, U1).
	env.settings.number_mode = "value"
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
B50 = ("NumberBreakCommand", 50)
# The dot rule: a "." outside a number is spoken apart from it, in every mode but "off".
SHARED = {"a. 3": ["a. 3"], "3.": ["3 ."], ".5": [". 5"], "": []}
# Keyed by (mode, group size, number pause). The group size is independent of the mode (decided by
# the user, 2026-11-01, U1, U2): 0 keeps a number whole, above 0 cuts it in every mode.
NUMBER_MODES = {
	("value", 0, 0): {
		"12.5": ["12.5"],
		"v1.2": ["v1.2"],
	},
	# Digit mode: every digit and every symbol, joined with spaces in one item (decided by the user,
	# 2026-11-01).
	("number", 0, 0): {
		"12.5": joined("1 2 <.> 5"),
		"-1234": joined("-1 2 3 4"),
		"12": joined("1 2"),
		"v1.2": joined("v1 <.> 2"),
		"1.2.3": joined("1 <.> 2 <.> 3"),
	},
	# Without groups digit mode adds no edge pause (U4); two numbers still get the pause (U5).
	("number", 0, 50): {
		"12.5": joined("1 2 <.> 5"),
		"-1234": joined("-1 2 3 4"),
		"v1.2": joined("v1 <.> 2"),
		"12 34": ["1 2", B50, "3 4"],
		"3.": ["3 ."],
	},
	# A group size of 1 in value mode reads every digit apart, as number mode did before 2026-11-01.
	("value", 1, 0): {
		"12.5": spoken("1 2 <.> 5"),
		"-1234": spoken("-1 2 3 4"),
		"12 34": ["1", NB0, "2 3", NB0, "4"],
	},
	# Groups are cut from the left, the sign joins the first, and a symbol is named apart.
	("value", 2, 0): {
		"12.5": spoken("12 <.> 5"),
		"-1234": spoken("-12 34"),
		"123": spoken("12 3"),
		"12": ["12"],
		"v1.2": spoken("v1 <.> 2"),
		"1.2.3": spoken("1 <.> 2 <.> 3"),
	},
	# A number pause above 0 also sets a number apart from the text of its item (number-edge-pause
	# spec, decided by the user 2026-10-24), with a group size above 0 (2026-11-01, U4).
	("value", 2, 50): {
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
	# Off with a group size cuts too, and leaves the pieces and symbols as they are (U2); no dot rule.
	("none", 2, 0): {
		"12.5": ["12", NB0, ".", NB0, "5"],
		"-1234": ["-12", NB0, "34"],
		"v1.2": ["v1", NB0, ".", NB0, "2"],
		"3.": ["3."],
	},
	# Digit mode with a group size reads each piece digit by digit, with breaks between the pieces.
	("number", 2, 50): {
		"12.5": ["1 2", B50, N("."), B50, "5"],
		"-1234": ["-1 2", B50, "3 4"],
		"v1.2": ["v", E50, "1", B50, N("."), B50, "2"],
		"12 34": ["1 2", B50, "3 4"],
		"3.": ["3", E50, " ."],
	},
}
# Each (mode, size, pause) runs the texts of its own table. The SHARED texts run only in value mode
# and with a number pause: in the other modes they take no branch of their own.
WITH_SHARED = {("value", 0, 0), ("value", 2, 50)}
CASES = [
	(text, *key)
	for key, table in NUMBER_MODES.items()
	for text in ({**SHARED, **table} if key in WITH_SHARED else table)
]


@pytest.mark.parametrize(("text", "mode", "size", "pause"), CASES)
def test_number_mode(env, text, mode, size, pause):
	env.settings.number_mode = mode
	env.settings.group_size = size
	env.settings.scaled_number_wait = lambda: pause
	expected = {**SHARED, **NUMBER_MODES[(mode, size, pause)]}[text]
	assert shape(env.module.inject_numbers([text], env.settings, env.module.GENERIC_CONTEXT)) == expected


# Spec 7.1: (input, number, group 3, group 2), each as space-separated pieces.
SPEC_TABLE = [
	("12,345,678", "1 2 <,> 3 4 5 <,> 6 7 8", "12 <,> 345 <,> 678", "12 <,> 34 5 <,> 67 8"),
	("1,234.56", "1 <,> 2 3 4 <.> 5 6", "1 <,> 234 <.> 56", "1 <,> 23 4 <.> 56"),
	("-1234", "-1 2 3 4", "-123 4", "-12 34"),
	("5-3", "5 <-> 3", "5 <-> 3", "5 <-> 3"),
	("2026-10-22", "2 0 2 6 <-> 1 0 <-> 2 2", "202 6 <-> 10 <-> 22", "20 26 <-> 10 <-> 22"),
	("2×3", "2 <×> 3", "2 <×> 3", "2 <×> 3"),
	("45°30", "4 5 <°> 3 0", "45 <°> 30", "45 <°> 30"),
]


# ASCII ids without backslashes: pytest escapes a non-ASCII id in place, so a second collection in
# one process (mutmut's clean run) escapes it again and can no longer select it.
SPEC_IDS = ["".join(c if c.isascii() else f"U+{ord(c):04X}" for c in row[0]) for row in SPEC_TABLE]


def digit_by_digit(piece):
	"""A digit piece as number mode reads it: every digit apart, the sign on the first."""
	sign = piece[0] if piece[0] in "+-" else ""
	return sign + " ".join(piece[len(sign) :])


def pieces_in(mode, pieces):
	"""The space-separated *pieces* of a group column as *mode* speaks them, with breaks between."""
	symbol = lambda piece: piece.startswith("<")
	if mode == "none":
		return broken(0, *(piece[1:-1] if symbol(piece) else piece for piece in pieces.split()))
	if mode == "number":
		return broken(
			0,
			*(N(piece[1:-1]) if symbol(piece) else digit_by_digit(piece) for piece in pieces.split()),
		)
	return spoken(pieces)


@pytest.mark.parametrize(
	("mode", "size", "column"),
	[
		("number", 0, 1),
		("value", 1, 1),
		("value", 3, 2),
		("value", 2, 3),
		("none", 3, 2),
		("none", 2, 3),
		("number", 3, 2),
		("number", 2, 3),
	],
)
@pytest.mark.parametrize("row", SPEC_TABLE, ids=SPEC_IDS)
def test_number_modes_and_group_sizes_name_each_symbol(env, mode, size, column, row):
	# Without groups number mode joins the pieces with spaces; with a group size every mode breaks
	# between them, value and number name the symbols, off leaves them (decided by the user, 2026-11-01).
	env.settings.number_mode = mode
	env.settings.group_size = size
	result = env.module.inject_numbers([row[0]], env.settings, env.module.GENERIC_CONTEXT)
	assert shape(result) == (joined(row[column]) if size == 0 else pieces_in(mode, row[column]))


def test_adjacent_symbols_get_a_name_each(env):
	env.settings.number_mode = "number"
	result = env.module.inject_numbers(["1--2"], env.settings, env.module.GENERIC_CONTEXT)
	assert shape(result) == joined("1 <-> <-> 2")


def roles_context(module, language, number_language):
	return module.SpeechContext(
		supports_roles=True,
		language=language,
		number_language=number_language,
		default_voice_name="Z",
		default_voice_language=language,
		voice_name_for_language={"zh_TW": "Z", "en": "E", "de": "D"}.get,
	)


# A name of "×" from the harness: "multiplication sign", then the words of its locale.
MULTIPLICATION_NAME_RE = re.compile(r"multiplication sign(?: [a-z]+)+?(?= \d|$)")


def names_in(result):
	"""The names of "×" in *result*: number mode speaks them inside its items, between digits."""
	return [name for item in result if isinstance(item, str) for name in MULTIPLICATION_NAME_RE.findall(item)]


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
	env.settings.number_mode = "value"
	env.settings.group_size = 3
	assert shape(env.module.inject_numbers(["123.456"], env.settings, generic)) == spoken("123 . 456")
	# Number mode without groups joins it with the other pieces, with spaces (decided by the user,
	# 2026-11-01).
	env.settings.number_mode = "number"
	env.settings.group_size = 0
	assert shape(env.module.inject_numbers(["12.5"], env.settings, generic)) == joined("1 2 . 5")
	assert shape(env.module.inject_numbers(["1-.2"], env.settings, generic)) == joined("1 <-> . 2")


def test_an_unnamed_symbol_and_a_named_one_are_two_items(env, monkeypatch):
	# The batch 2 review I1 input: no name ever takes the next digits.
	counting_lookup(env, monkeypatch, unnamed=".")
	env.settings.number_mode = "value"
	env.settings.group_size = 1
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
@pytest.mark.parametrize("mode", ["value", "none"])
def test_an_unnamed_symbol_is_left_to_the_punctuation_stage(env, monkeypatch, mode, roles, remove, expected):
	# Accepted by the user (2026-10-22): an unnamed symbol is an item of its own, so the punctuation
	# stage may pause at it and remove it; the digits around it still reach the synth apart. Off with
	# a group size sends every symbol as itself, the same way (2026-11-01, U2; spec risk 5).
	counting_lookup(env, monkeypatch, unnamed=".")
	env.settings.number_mode = mode
	env.settings.group_size = 3
	env.settings.scaled_number_wait = lambda: 10
	env.settings.punctuation_pause_enabled = True
	env.settings.punctuation_pause_characters = "."
	env.settings.remove_punctuation_characters = remove
	context = roles_context(env.module, "zh_TW", "default") if roles else env.module.GENERIC_CONTEXT
	monkeypatch.setattr(env.module.registry, "current_context", lambda: context)
	sequence = ["12.5"]
	for stage in env.module.STAGES:
		sequence = stage.handler(sequence)
	assert shape(sequence) == expected


@pytest.mark.parametrize(
	("remove", "expected"),
	[
		(False, ["1 2", ".", ("InternalPunctuationBreakCommand", 50), "5"]),
		(True, ["1 2", ("InternalPunctuationBreakCommand", 50), "5"]),
	],
	ids=["pause", "remove"],
)
def test_an_unnamed_symbol_in_number_mode_is_left_to_the_punctuation_stage(
	env,
	monkeypatch,
	remove,
	expected,
):
	# Number mode joins its pieces with spaces (decided by the user, 2026-11-01), an unnamed symbol
	# included; the punctuation stage still pauses at it, and removes it, as at any other mark.
	counting_lookup(env, monkeypatch, unnamed=".")
	env.settings.number_mode = "number"
	env.settings.scaled_number_wait = lambda: 10
	env.settings.scaled_punctuation_wait = lambda: 50
	env.settings.punctuation_pause_characters = "."
	env.settings.remove_punctuation_characters = remove
	context = roles_context(env.module, "zh_TW", "default")
	monkeypatch.setattr(env.module.registry, "current_context", lambda: context)
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
	assert result == [" ".join(["1", N(".")] * 3000 + ["1"])]


@pytest.mark.parametrize(
	("size", "text", "expected"),
	[
		(3, "0912345678", spoken("091 234 567 8")),
		(2, "007", spoken("00 7")),
		(3, "+0012", spoken("+001 2")),
	],
)
@pytest.mark.parametrize("mode", ["value", "none"])
def test_groups_keep_leading_zeros_and_every_digit(env, mode, size, text, expected):
	env.settings.number_mode = mode
	env.settings.group_size = size
	assert shape(env.module.inject_numbers([text], env.settings, env.module.GENERIC_CONTEXT)) == expected


@pytest.mark.parametrize("mode", ["value", "none"])
@pytest.mark.parametrize("pause", [0, 50])
def test_group_separator_is_one_instance_per_number(env, mode, pause):
	env.settings.number_mode = mode
	env.settings.group_size = 2
	env.settings.scaled_number_wait = lambda: pause
	result = list(env.module.inject_numbers(["123456"], env.settings, env.module.GENERIC_CONTEXT))
	assert result[0::2] == ["12", "34", "56"]
	first, second = result[1::2]
	assert first is second
	assert first.time == pause


@pytest.mark.parametrize("mode", ["pair", "group"])
@pytest.mark.parametrize(
	("size", "expected"),
	[({}, ["1234"]), ({"groupSize": 2}, ["12", ("NumberBreakCommand", 10), "34"])],
	ids=["no-size", "size-2"],
)
def test_a_stored_pair_mode_reads_numbers_as_values(env, monkeypatch, mode, size, expected):
	# An unknown stored mode, the old group mode included, reads as value; a stored group size groups
	# in value mode, with no migration (decided by the user, 2026-11-01, U7).
	conf = {"WorldVoice": {"pipeline": {"numberMode": mode, **size}}}
	stored = load_settings_module(monkeypatch, conf).pipeline_settings.get()
	assert shape(env.module.inject_numbers(["1234"], stored, env.module.GENERIC_CONTEXT)) == expected


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
	[
		("value", 3, "１２３４５", ["１２３", NB0, "４５"]),
		("value", 1, "٣٤", ["٣", NB0, "٤"]),
		("number", 0, "٣٤", ["٣ ٤"]),
		("number", 3, "１２３４５", ["１ ２ ３", NB0, "４ ５"]),
		("none", 1, "٣٤", ["٣", NB0, "٤"]),
	],
)
def test_every_mode_keeps_the_original_digits(env, mode, size, text, expected):
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
		("number", "E", [("lang", "en"), "1 2", ("lang", "zh_TW"), ". Next"]),
		("value", "Z", ["12 . Next"]),
		("number", "Z", ["1 2 . Next"]),
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
	conf["WorldVoice"]["log"] = {"enable": enable, "numberMode": label_on}
	written = []
	monkeypatch.setattr(
		env.module.registry,
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
	monkeypatch.setattr(env.module.registry, "read_stored", settings_module.read_stored)
	error = sys.modules["configobj.validate"].VdtTypeError("maybe")
	# The settings loader registered a config of its own; the pipeline keeps the one it imported.
	conf = env.module.config.conf
	conf["general"]["loggingLevel"] = "DEBUG"
	conf["WorldVoice"]["log"] = RefusingSection({}, {"enable": error, "numberMode": error})
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
