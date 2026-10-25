"""The space pause of scripts written without spaces (unspaced-script-space-pause spec).

A whitespace run becomes the pause when the character before it and the character after it are both
of an unspaced script: Han, kana, Bopomofo, Thai, Lao, Khmer or Myanmar (decided by the user,
2026-10-25). An Inherited mark takes the script of the character it attaches to (O1).
"""

import re
import sys
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest
from pipeline_harness import load_pipeline_module, punctuation_settings

LANGUAGE_DETECTION_SCRIPTS = "synthDrivers.WorldVoice.languageDetection.scripts"


@pytest.fixture
def env(monkeypatch):
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	return module


# Classifying a character (spec §4.2)


def test_unspaced_scripts_are_the_users_list(env):
	assert env.UNSPACED_SCRIPTS == frozenset(
		{"Han", "Hiragana", "Katakana", "Bopomofo", "Thai", "Lao", "Khmer", "Myanmar"},
	)


@pytest.mark.parametrize(
	"character",
	[
		"一",
		"㐀",
		"鿿",
		"豈",
		"\U00020000",
		"々",
		"〇",
		"あ",
		"ア",
		"ｱ",
		"ㄅ",
		"ㆠ",
		"ก",
		"ກ",
		"ក",
		"က",
		"\U0001b001",
	],
)
def test_is_unspaced(env, character):
	assert env._is_unspaced(character) is True


def _generated_categories():
	"""The General Category of each UNSPACED_COMMON character, as unspaced_common_data.py records it."""
	data = sys.modules["synthDrivers.WorldVoice.pipeline.unspaced_common_data"]
	source = Path(data.__file__).read_text(encoding="utf-8")
	ranges = re.findall(r"^\t\(0x([0-9A-F]+), 0x([0-9A-F]+)\),  # \S+ (\w\w)$", source, re.MULTILINE)
	assert [(int(start, 16), int(end, 16)) for start, end, _category in ranges] == list(
		data.UNSPACED_COMMON_RANGES,
	)
	return [category for start, end, category in ranges for _code in range(int(start, 16), int(end, 16) + 1)]


def test_unspaced_common_follows_the_rule(env):
	# D1, corrected by fix/unspaced-common-rule: generated from Unicode 18.0.0 ScriptExtensions.txt,
	# every Common letter, number or symbol with an unspaced script in its Script_Extensions.
	assert len(env.UNSPACED_COMMON) == 286
	assert {env.get_script(ord(character)) for character in env.UNSPACED_COMMON} == {"Common"}
	# The General Categories are the ones the generator read from the same UnicodeData.txt and wrote
	# beside each range, not Python's unicodedata, which may be of another Unicode version.
	assert Counter(_generated_categories()) == {
		"So": 216,
		"No": 42,
		"Lm": 14,
		"Sk": 12,
		"Lo": 2,
	}


def test_unspaced_common_keeps_the_hand_listed_characters(env):
	# The 13 letters of the first version and the five Bopomofo tone marks need no special case.
	listed = {
		chr(code)
		for code in (0x3006, *range(0x3031, 0x3036), 0x303C, 0x309B, 0x309C, 0x30FC, 0xFF70, 0xFF9E, 0xFF9F)
	}
	tone_marks = {chr(code) for code in (0x02C7, 0x02C9, 0x02CA, 0x02CB, 0x02D9)}
	assert listed | tone_marks <= env.UNSPACED_COMMON


def test_unspaced_common_data_matches_the_script_data(env):
	data = sys.modules["synthDrivers.WorldVoice.pipeline.unspaced_common_data"]
	scripts = sys.modules["synthDrivers.WorldVoice.languageDetection.script_data"]
	assert data.UNICODE_VERSION == scripts.UNICODE_VERSION == "18.0.0"
	assert data.UNSPACED_COMMON is env.UNSPACED_COMMON


def test_every_unspaced_common_character_is_unspaced(env):
	assert all(env._is_unspaced(character) for character in env.UNSPACED_COMMON)


@pytest.mark.parametrize(
	"character",
	["ー", "ｰ", "〆", "゛", "ˇ", "ˉ", "ˊ", "ˋ", "˙", "꜀", "㈱", "㊀", "㍻", "⿰", "〓", "𝍠", "🉐"],
)
def test_common_characters_of_unspaced_scripts_are_unspaced(env, character):
	assert env._is_unspaced(character) is True


@pytest.mark.parametrize("character", ["。", "、", "〽", "゠", "「", "」", "・", "〃", "-", "a", "0"])
def test_common_punctuation_and_ascii_are_not_unspaced(env, character):
	assert env._is_unspaced(character) is False


@pytest.mark.parametrize(
	"character",
	[
		"a",
		"A",
		"Я",
		"한",
		"ㄱ",
		"1",
		"１",
		"。",
		"「",
		"・",
		"゠",
		"　",
		"゙",
		"",
		"\ud800",
		"͸",
		"ˈ",
		"ˌ",
	],
)
def test_is_not_unspaced(env, character):
	assert env._is_unspaced(character) is False


def test_pipeline_harness_loads_language_detection_fresh(monkeypatch):
	# D5: each load imports the script lookup again, never one cached against an earlier test's stubs.
	load_pipeline_module(monkeypatch, punctuation_settings(0))
	first = sys.modules[LANGUAGE_DETECTION_SCRIPTS]
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	second = sys.modules[LANGUAGE_DETECTION_SCRIPTS]
	assert second is not first
	assert module.get_script is second.get_script


# Deciding one whitespace run (spec §4.3, O1)


@pytest.mark.parametrize(
	("text", "expected"),
	[
		("中 文", [True]),
		# Row 19, with が decomposed: the combining voiced mark is Inherited and looked past.
		("か\u3099 か", [True]),
		# Row 20: an ideographic variation selector is Inherited.
		("葛\U000e0100 中", [True]),
		("中\ufe00 文", [True]),
		("中\u200d 文", [True]),
		("中\u200c 文", [True]),
		("か\u3099\u0301 か", [True]),
		# Row 21: a mark right after the run attaches to the whitespace.
		("中 \u3099か", [False]),
		("\u3099 か", [False]),
		# The look-back stops at whitespace: the mark between the runs has no unspaced base.
		("中 \u0301 文", [False, False]),
		(" 中 ", [False, False]),
		("   ", [False]),
		("ｺｰ ｸ", [True]),
		("ーー か", [True]),
		("カﾞ ア", [True]),
		("\U00020000 か", [True]),
		("\ud800 中", [False]),
		("中 \ud800", [False]),
		("中 a", [False]),
		("a 中", [False]),
		("中\n\t 文", [True]),
	],
)
def test_pauses_between(env, text, expected):
	assert [
		env._pauses_between(text, match.start(), match.end()) for match in re.finditer(r"\s+", text)
	] == expected


# The stage (spec §5)


class Marker:
	"""A speech command no stage knows, such as NVDA's IndexCommand."""


def make_settings(*, space=20, mode="value", wait=0, chars="", remove=False, pwait=250):
	"""The settings the stages read; the punctuation stage is on when *chars* names characters."""
	return SimpleNamespace(
		number_mode=mode,
		scope="WorldVoice",
		punctuation_pause_characters=chars,
		punctuation_pause_enabled=bool(chars),
		remove_punctuation_characters=remove,
		scaled_item_wait=lambda: 0,
		scaled_number_wait=lambda: wait,
		scaled_unspaced_script_space_wait=lambda: space,
		scaled_punctuation_wait=lambda: pwait,
		group_size=3,
	)


def context(module):
	return module.SpeechContext(
		supports_roles=True,
		language="zh",
		number_language="default",
		default_voice_name="Z",
		default_voice_language="zh",
		voice_name_for_language={"zh": "Z", "en": "E"}.get,
	)


def shape(module, sequence):
	"""Text as itself; a break as (class name, time); a language change as ("L", language)."""
	result = []
	for item in sequence:
		if isinstance(item, str):
			result.append(item)
		elif hasattr(item, "lang"):
			result.append(("L", item.lang))
		elif hasattr(item, "time"):
			result.append((type(item).__name__, item.time))
		else:
			result.append(item)
	return result


def space_stage(module, sequence, **options):
	return list(
		module.inject_unspaced_script_space_pause(sequence, make_settings(**options), module.GENERIC_CONTEXT),
	)


def every_stage(module, sequence, **options):
	settings, ctx = make_settings(**options), context(module)
	for stage in module.STAGES:
		sequence = list(stage.fn(sequence, settings, ctx))
	return shape(module, sequence)


B = ("BreakCommand", 20)
B10 = ("BreakCommand", 10)


@pytest.mark.parametrize(
	("text", "expected"),
	[
		("中 文 abc 中 文", ["中", B, "文 abc 中", B, "文"]),
		("hello world", "same"),
		("かな カナ", ["かな", B, "カナ"]),
		("ภาษา ไทย", ["ภาษา", B, "ไทย"]),
		("漢字 かな", ["漢字", B, "かな"]),
		("中文 ภาษาไทย", ["中文", B, "ภาษาไทย"]),
		("中 abc", "same"),
		("中 한국", "same"),
		("한국 어", "same"),
		("コーヒー ください", ["コーヒー", B, "ください"]),
		("ｺｰﾋｰ ｸﾀﾞｻｲ", ["ｺｰﾋｰ", B, "ｸﾀﾞｻｲ"]),
		("\u3400 \u3401", ["\u3400", B, "\u3401"]),
		("\U00020000 \U00020001", ["\U00020000", B, "\U00020001"]),
		("中\u3000文", ["中", B, "文"]),
		("中\n\t 文", ["中", B, "文"]),
		("中\u00a0文", ["中", B, "文"]),
		("中\u200b文", "same"),
		(" 中 ", "same"),
		("   ", "same"),
		("か\u3099 か", ["か\u3099", B, "か"]),
		("葛\U000e0100 中", ["葛\U000e0100", B, "中"]),
		("中 \u3099か", "same"),
		("中。 文", "same"),
		("ㄧㄣ ㄓㄨ", ["ㄧㄣ", B, "ㄓㄨ"]),
		("ㄓㄨˋ ㄧㄣ", ["ㄓㄨˋ", B, "ㄧㄣ"]),
		("ㄋㄧˇ ㄏㄠˇ", ["ㄋㄧˇ", B, "ㄏㄠˇ"]),
		("㈱ 公司", ["㈱", B, "公司"]),
		("第 ㊀ 項", ["第", B, "㊀", B, "項"]),
		("ㄓㄨˋ ˙ㄉㄜ", ["ㄓㄨˋ", B, "˙ㄉㄜ"]),
		("a ˇ", "same"),
		("ˇ a", "same"),
		("中 ˇa", ["中", B, "ˇa"]),
		("๑ ๒", ["๑", B, "๒"]),
		("1 2", "same"),
		("", []),
	],
)
def test_worked_examples(env, text, expected):
	assert shape(env, space_stage(env, [text])) == ([text] if expected == "same" else expected)


def test_wait_zero_yields_the_same_objects(env):
	sequence = [Marker(), "中 文", "かな カナ"]
	result = space_stage(env, sequence, space=0)
	assert len(result) == len(sequence) and all(out is item for out, item in zip(result, sequence))


def test_several_runs_reuse_one_break(env):
	result = space_stage(env, ["中 文 か ภา"])
	assert shape(env, result) == ["中", B, "文", B, "か", B, "ภา"]
	assert result[1] is result[3] is result[5]


# Through every stage (spec §4.4, §8.2)


def test_stages_pause_between_han_and_kana(env):
	assert every_stage(env, ["漢字 かな"], space=10) == ["漢字", B10, "かな"]


def test_stages_digit_neighbour_has_no_space_pause(env):
	# A digit is Common, so the space after "第3" never pauses, as today.
	result = every_stage(env, ["第3 章"], space=10, mode="number")
	assert all(not isinstance(item, tuple) or item[0] != "BreakCommand" for item in result), result


@pytest.mark.parametrize("remove", [False, True])
def test_stages_space_among_punctuation_characters(env, remove):
	# F3, Q3 = A: the space stage runs first, so a space between unspaced characters gets the space
	# pause, and only the Latin spaces reach the punctuation stage.
	result = every_stage(env, ["ภาษา ไทย hello world"], space=10, chars=" ", remove=remove)
	PB = ("PunctuationBreakCommand", 250)
	space = [] if remove else [" "]
	assert result == ["ภาษา", B10, "ไทย", *space, PB, "hello", *space, PB, "world"]


@pytest.mark.parametrize(("mode", "wait"), [(m, w) for m in ("value", "number", "group") for w in (0, 10)])
def test_stages_script_digits(env, mode, wait):
	# F6: Thai digits are Thai. Only the number and group modes with a number pause replace the space
	# between two numbers with their own break first (number edge pause spec O3).
	result = every_stage(env, ["๑ ๒"], space=10, mode=mode, wait=wait)
	expected = ("NumberBreakCommand", 10) if mode != "value" and wait > 0 else B10
	assert result == ["๑", expected, "๒"]


# Characters Unicode 17.0 and 18.0 assigned (fix/unicode-18)


@pytest.mark.parametrize(
	("text", "expected"),
	[
		# CJK Extension J (17.0) and Han added to earlier blocks: U+16FF2 in 17.0, U+2B81E in 18.0.
		("\U000323b0 \U000323b1", ["\U000323b0", B, "\U000323b1"]),
		("中 \U00033479", ["中", B, "\U00033479"]),
		("\U00016ff2 \U0002b81e", ["\U00016ff2", B, "\U0002b81e"]),
		# Kana new in 18.0: a Hiragana and a Katakana digraph, and a Katakana letter.
		("\U0001b123 \U0001b124", ["\U0001b123", B, "\U0001b124"]),
		("か \U0001b168", ["か", B, "\U0001b168"]),
		# Small seal script (18.0) is its own script, not Han, so it never pauses.
		("\U0003d000 \U0003d001", "same"),
		("中 \U0003d000", "same"),
		("\U0003d000 中", "same"),
	],
)
def test_unicode_18_characters(env, text, expected):
	assert shape(env, space_stage(env, [text])) == ([text] if expected == "same" else expected)


def test_stages_pause_between_extension_j_ideographs(env):
	assert every_stage(env, ["\U000323b0 \U000323b1"], space=10) == ["\U000323b0", B10, "\U000323b1"]


def test_long_text_stays_fast(env):
	for text, pieces in (("hello world " * 15000, 1), ("ภาษา ไทย " * 15000, 30000)):
		start = time.perf_counter()
		result = space_stage(env, [text])
		assert time.perf_counter() - start < 2
		assert sum(isinstance(item, str) for item in result) == pieces
