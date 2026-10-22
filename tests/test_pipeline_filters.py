"""The pipeline filters' output, pinned before their loops were shared."""

import sys
import time
from types import SimpleNamespace

import pytest
from pipeline_harness import load_pipeline_module, load_settings_module, punctuation_settings


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
		# Digits are ASCII only.
		("\uff11\uff12", []),
		("12.", ["12"]),
	],
)
def test_number_re_finds_whole_numbers(env, text, matches):
	assert [match.group() for match in env.module._NUMBER_RE.finditer(text)] == matches


@pytest.mark.parametrize("text", ["1" * 5000 + "a", "1." * 3000 + "a"])
def test_number_re_fullmatch_fails_fast(env, text):
	start = time.perf_counter()
	assert env.module._NUMBER_RE.fullmatch(text) is None
	assert time.perf_counter() - start < 0.5


B40 = ("NumberBreakCommand", 40)
NB0 = ("NumberBreakCommand", 0)
GB0 = ("GroupNumberBreakCommand", 0)
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
	# One number definition: a match never touches another, so every whitespace gap splits.
	("02 2345-6789", ["02", B40, "2345-6789"]),
	("3-1 2", ["3-1", B40, "2"]),
	("1 2 3-4", ["1", B40, "2", B40, "3-4"]),
	("1-2 3 4", ["1-2", B40, "3", B40, "4"]),
	("2026-10-22 12:30", ["2026-10-22", B40, "12:30"]),
	("12,345 6", ["12,345", B40, "6"]),
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
	digits = env.module.inject_number_mode(["12"], env.settings, env.module.GENERIC_CONTEXT)
	assert shape(env.module.number_wait_factor(digits, env.settings, env.module.GENERIC_CONTEXT)) == [
		"1",
		B40,
		"2",
	]


def zh_context(module, replacements):
	"""A WorldVoice zh context whose symbol table maps digits to the given words."""
	symbols = SimpleNamespace(
		symbols={
			digit: SimpleNamespace(language="zh", replacement=word) for digit, word in replacements.items()
		},
	)
	return module.SpeechContext(
		supports_roles=True,
		language="zh",
		number_language="zh",
		speech_symbols=symbols,
	)


def test_translated_digits_are_split_by_the_number_wait(env):
	env.settings.number_mode = "number"
	env.settings.scaled_number_wait = lambda: 40
	context = zh_context(env.module, {"1": "一"})
	digits = env.module.inject_number_mode(["11"], env.settings, context)
	assert shape(env.module.number_wait_factor(digits, env.settings, context)) == ["一", B40, "一"]


def test_group_mode_does_not_translate_digits(env):
	env.settings.number_mode = "group"
	env.settings.group_size = 2
	context = zh_context(env.module, {"1": "一"})
	assert shape(env.module.inject_number_mode(["1234"], env.settings, context)) == ["12", GB0, "34"]
	# A decimal is read whole, untranslated too.
	assert shape(env.module.inject_number_mode(["12.5"], env.settings, context)) == ["12.5"]


@pytest.mark.parametrize("wait", [0, 40])
def test_digit_mode_separates_digits_with_the_number_wait(env, wait):
	env.settings.number_mode = "number"
	env.settings.scaled_number_wait = lambda: wait
	generic = env.module.GENERIC_CONTEXT
	assert shape(env.module.inject_number_mode(["12"], env.settings, generic)) == [
		"1",
		("NumberBreakCommand", wait),
		"2",
	]
	result = list(env.module.inject_number_mode(["-1234"], env.settings, generic))
	assert result[0::2] == ["-1", "2", "3", "4"]
	first, *others = result[1::2]
	assert all(other is first for other in others)


@pytest.mark.parametrize(
	("text", "expected"),
	[
		("A12B", ["A1", NB0, "2B"]),
		("3.14", ["3.1", NB0, "4"]),
		("1a2", ["1a2"]),
		("v1.2", ["v1.2"]),
	],
)
def test_digit_mode_breaks_only_between_adjacent_digits(env, text, expected):
	env.settings.number_mode = "number"
	assert shape(env.module.inject_number_mode([text], env.settings, env.module.GENERIC_CONTEXT)) == expected


def test_digit_words_are_kept_verbatim_one_per_item(env):
	env.settings.number_mode = "number"
	context = zh_context(env.module, {"1": "one ", "2": "two"})
	assert shape(env.module.inject_number_mode(["12"], env.settings, context)) == ["one ", NB0, "two"]


def test_group_mode_then_number_wait_breaks_between_numbers_only(env):
	env.settings.number_mode = "group"
	env.settings.group_size = 2
	env.settings.scaled_number_wait = lambda: 40
	groups = env.module.inject_number_mode(["1234 5678"], env.settings, env.module.GENERIC_CONTEXT)
	assert shape(env.module.number_wait_factor(groups, env.settings, env.module.GENERIC_CONTEXT)) == [
		"12",
		("GroupNumberBreakCommand", 0),
		"34",
		B40,
		"56",
		("GroupNumberBreakCommand", 0),
		"78",
	]


TEXTS = ["12.5", "-1234", "123", "12", "v1.2", "a. 3", "3.", ".5", "1.2.3", ""]
SHARED = {"v1.2": ["v1.2"], "a. 3": ["a. 3"], "3.": ["3 ."], ".5": [". 5"], "1.2.3": ["1.2.3"], "": []}
GB50 = ("GroupNumberBreakCommand", 50)
# Keyed by (mode, group size, group pause).
NUMBER_MODES = {
	("value", 3, 0): {"12.5": ["12.5"], "-1234": ["-1234"], "123": ["123"], "12": ["12"]},
	# Digit mode separates two adjacent digits with the number wait, even at 0.
	("number", 3, 0): {
		"12.5": ["1", NB0, "2.5"],
		"-1234": ["-1", NB0, "2", NB0, "3", NB0, "4"],
		"123": ["1", NB0, "2", NB0, "3"],
		"12": ["1", NB0, "2"],
	},
	# Groups are cut from the left and are separate items even at pause 0; a number of at most
	# the group size and a decimal have no separator.
	("group", 1, 0): {
		"12.5": ["12.5"],
		"-1234": ["-1", GB0, "2", GB0, "3", GB0, "4"],
		"123": ["1", GB0, "2", GB0, "3"],
		"12": ["1", GB0, "2"],
	},
	("group", 2, 0): {"12.5": ["12.5"], "-1234": ["-12", GB0, "34"], "123": ["12", GB0, "3"], "12": ["12"]},
	("group", 2, 50): {
		"12.5": ["12.5"],
		"-1234": ["-12", GB50, "34"],
		"123": ["12", GB50, "3"],
		"12": ["12"],
	},
	("group", 3, 0): {"12.5": ["12.5"], "-1234": ["-123", GB0, "4"], "123": ["123"], "12": ["12"]},
	("group", 10, 0): {"12.5": ["12.5"], "-1234": ["-1234"], "123": ["123"], "12": ["12"]},
}


@pytest.mark.parametrize("mode,size,pause", sorted(NUMBER_MODES))
@pytest.mark.parametrize("text", TEXTS)
def test_number_mode(env, mode, size, pause, text):
	env.settings.number_mode = mode
	env.settings.group_size = size
	env.settings.scaled_group_wait = lambda: pause
	expected = {**SHARED, **NUMBER_MODES[(mode, size, pause)]}[text]
	assert shape(env.module.inject_number_mode([text], env.settings, env.module.GENERIC_CONTEXT)) == expected


@pytest.mark.parametrize(
	("size", "text", "expected"),
	[
		(3, "0912345678", ["091", GB0, "234", GB0, "567", GB0, "8"]),
		(2, "007", ["00", GB0, "7"]),
		(3, "+0012", ["+001", GB0, "2"]),
	],
)
def test_group_mode_keeps_leading_zeros_and_every_digit(env, size, text, expected):
	env.settings.number_mode = "group"
	env.settings.group_size = size
	assert shape(env.module.inject_number_mode([text], env.settings, env.module.GENERIC_CONTEXT)) == expected


@pytest.mark.parametrize("pause", [0, 50])
def test_group_separator_is_one_instance_per_number(env, pause):
	env.settings.number_mode = "group"
	env.settings.group_size = 2
	env.settings.scaled_group_wait = lambda: pause
	result = list(env.module.inject_number_mode(["123456"], env.settings, env.module.GENERIC_CONTEXT))
	assert result[0::2] == ["12", "34", "56"]
	first, second = result[1::2]
	assert first is second
	assert first.time == pause


def test_a_stored_pair_mode_reads_numbers_as_values(env, monkeypatch):
	conf = {"WorldVoice": {"pipeline": {"number_mode": "pair", "group_size": 2}}}
	stored = load_settings_module(monkeypatch, conf).pipeline_settings.get()
	assert list(env.module.inject_number_mode(["1234"], stored, env.module.GENERIC_CONTEXT)) == ["1234"]


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
