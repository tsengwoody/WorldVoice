"""The pipeline filters' output, pinned before their loops were shared."""

from types import SimpleNamespace

import pytest
from pipeline_harness import load_pipeline_module, punctuation_settings


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
		default_voice=default,
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
	assert shape(result) == ["1", ("BreakCommand", 40), "2", "a", "3", ("BreakCommand", 40), "4"]
	assert result[1] is result[5]


@pytest.mark.parametrize(
	"sequence,expected",
	[
		(["12", "3"], ["12", ("BreakCommand", 40), "3"]),
		(["-3.5", "4"], ["-3.5", ("BreakCommand", 40), "4"]),
		(["12abc", "3"], ["12abc", "3"]),
		(["1.", "2"], ["1.", "2"]),
		(["3", "12abc"], ["3", "12abc"]),
	],
)
def test_number_wait_breaks_only_between_whole_numbers(env, sequence, expected):
	env.settings.scaled_number_wait = lambda: 40
	assert (
		shape(env.module.number_wait_factor(sequence, env.settings, env.module.GENERIC_CONTEXT)) == expected
	)


B40 = ("BreakCommand", 40)
SPLITS = [
	("1 2", ["1", B40, "2"]),
	("共 12 34 個", ["共 ", "12", B40, "34", " 個"]),
	("5 -3", ["5", B40, "-3"]),
	("5 - 3", ["5 - 3"]),
	("1.2.3 4", ["1.2.", "3", B40, "4"]),
	("12 apples", ["12 apples"]),
	("abc1 2def", ["abc", "1", B40, "2", "def"]),
	("2026 10 21", ["2026", B40, "10", B40, "21"]),
	("12\u300034", ["12", B40, "34"]),
	("1\t2", ["1", B40, "2"]),
	("1\n2", ["1", B40, "2"]),
	# A no-break space never joins two numbers: it groups digits, as in "10 000" (decided by the user).
	("1\u00a02", ["1\u00a02"]),
	("10\u00a0000", ["10\u00a0000"]),
	("1\u202f234\u202f567", ["1\u202f234\u202f567"]),
	("1\u20072", ["1\u20072"]),
	("1 \u00a02", ["1 \u00a02"]),
	("10\u00a0000 5", ["10\u00a0", "000", B40, "5"]),
	("2 10\u00a0000", ["2", B40, "10", "\u00a0000"]),
	("1-2", ["1-2"]),
	("12abc 3", ["12abc 3"]),
	# F1 option B: a number glued to another number with no gap is never split out.
	("02 2345-6789", ["02 2345-6789"]),
	("3-1 2", ["3-1 2"]),
	("1 2 3-4", ["1", B40, "2", " 3-4"]),
]


@pytest.mark.parametrize("text,expected", SPLITS)
def test_number_wait_splits_numbers_separated_only_by_whitespace(env, text, expected):
	env.settings.scaled_number_wait = lambda: 40
	assert shape(env.module.number_wait_factor([text], env.settings, env.module.GENERIC_CONTEXT)) == expected


def test_the_shortest_number_wait_still_breaks(env):
	env.settings.scaled_number_wait = lambda: 1
	assert shape(env.module.number_wait_factor(["1 2"], env.settings, env.module.GENERIC_CONTEXT)) == [
		"1",
		("BreakCommand", 1),
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


def test_digit_mode_then_number_wait_pauses_between_digits(env):
	env.settings.number_mode = "number"
	env.settings.scaled_number_wait = lambda: 40
	digits = env.module.inject_number_mode(["12"], env.settings, env.module.GENERIC_CONTEXT)
	assert shape(env.module.number_wait_factor(digits, env.settings, env.module.GENERIC_CONTEXT)) == [
		"1",
		B40,
		"2",
	]


def test_translated_digits_are_not_split(env):
	env.settings.number_mode = "number"
	env.settings.scaled_number_wait = lambda: 40
	symbols = SimpleNamespace(symbols={"1": SimpleNamespace(language="zh", replacement="一")})
	context = env.module.SpeechContext(
		supports_roles=True,
		language="zh",
		number_language="zh",
		speech_symbols=symbols,
	)
	digits = env.module.inject_number_mode(["11"], env.settings, context)
	assert list(env.module.number_wait_factor(digits, env.settings, context)) == ["一 一"]


def test_pair_mode_then_number_wait_breaks_between_numbers_only(env):
	env.settings.number_mode = "pair"
	env.settings.scaled_number_wait = lambda: 40
	pairs = env.module.inject_number_mode(["1234 5678"], env.settings, env.module.GENERIC_CONTEXT)
	assert shape(env.module.number_wait_factor(pairs, env.settings, env.module.GENERIC_CONTEXT)) == [
		"12",
		("PairNumberBreakCommand", 0),
		"34",
		B40,
		"56",
		("PairNumberBreakCommand", 0),
		"78",
	]


TEXTS = ["12.5", "-1234", "123", "12", "v1.2", "a. 3", "3.", ".5", "1.2.3", ""]
SHARED = {"v1.2": ["v1.2"], "a. 3": ["a. 3"], "3.": ["3 ."], ".5": [". 5"], "1.2.3": ["1.2 . 3"], "": []}
NUMBER_MODES = {
	("value", 0): {"12.5": ["12.5"], "-1234": ["-1234"], "123": ["123"], "12": ["12"]},
	("number", 0): {"12.5": ["1 2.5"], "-1234": ["-1 2 3 4"], "123": ["1 2 3"], "12": ["1 2"]},
	# Pairs are separate items even at pause 0; up to two digits and decimals have no separator.
	("pair", 0): {
		"12.5": ["12.5"],
		"-1234": ["-12", ("PairNumberBreakCommand", 0), "34"],
		"123": ["12", ("PairNumberBreakCommand", 0), "3"],
		"12": ["12"],
	},
	("pair", 50): {
		"12.5": ["12.5"],
		"-1234": ["-12", ("PairNumberBreakCommand", 50), "34"],
		"123": ["12", ("PairNumberBreakCommand", 50), "3"],
		"12": ["12"],
	},
}


@pytest.mark.parametrize("mode,pause", sorted(NUMBER_MODES))
@pytest.mark.parametrize("text", TEXTS)
def test_number_mode(env, mode, pause, text):
	env.settings.number_mode = mode
	env.settings.scaled_pair_wait = lambda: pause
	expected = {**SHARED, **NUMBER_MODES[(mode, pause)]}[text]
	assert shape(env.module.inject_number_mode([text], env.settings, env.module.GENERIC_CONTEXT)) == expected


def test_number_language_wraps_each_number(env):
	english = SimpleNamespace(name="A:en", language="en")
	context = ctx(env.module, {"en": "A:en", "de": "A:de"}, english)
	result = env.module.inject_number_language(["a1b2"], env.settings, context)
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
	assert list(env.module.inject_number_language([""], env.settings, context)) == []


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
