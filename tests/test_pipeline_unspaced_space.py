"""The space pause of scripts written without spaces (unspaced-script-space-pause spec).

A whitespace run becomes the pause when the character before it and the character after it are both
of an unspaced script: Han, kana, Bopomofo, Thai, Lao, Khmer or Myanmar (decided by the user,
2026-10-25). An Inherited mark takes the script of the character it attaches to (O1).
"""

import re
import sys

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


def test_unspaced_common_is_pinned(env):
	# D1: the Common letters whose Script_Extensions are only unspaced scripts (Unicode 16.0.0).
	assert env._UNSPACED_COMMON == {
		chr(code)
		for code in (0x3006, *range(0x3031, 0x3036), 0x303C, 0x309B, 0x309C, 0x30FC, 0xFF70, 0xFF9E, 0xFF9F)
	}
	assert {env.get_script(ord(character)) for character in env._UNSPACED_COMMON} == {"Common"}


def test_bopomofo_tone_marks_are_pinned(env):
	# Q1: Common, with Latin in their Script_Extensions, counted as Bopomofo.
	assert env._UNSPACED_BOPOMOFO_MARKS == {chr(code) for code in (0x02C7, 0x02C9, 0x02CA, 0x02CB, 0x02D9)}
	assert {env.get_script(ord(character)) for character in env._UNSPACED_BOPOMOFO_MARKS} == {"Common"}


def test_every_listed_character_is_unspaced(env):
	assert all(
		env._is_unspaced(character) for character in env._UNSPACED_COMMON | env._UNSPACED_BOPOMOFO_MARKS
	)


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
