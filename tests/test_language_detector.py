"""Language detection: which language each run of text is spoken in."""

import sys
import time
from itertools import pairwise
from types import SimpleNamespace

import pytest
from detector_harness import (
	BreakCommand,
	ConfigProfileTriggerCommand,
	EndUtteranceCommand,
	LangChangeCommand,
	load_language_detection,
	master_detection,
)
from hypothesis import HealthCheck, example, given, settings, strategies as st


@pytest.fixture
def env(stub_modules, monkeypatch):
	return load_language_detection(stub_modules, monkeypatch)


def make_detector(env, languages=("en_US", "zh_TW", "ja"), number_language=None, *, internal_breaks=True):
	"""The one place the detector is built; its dependencies come from env. Without a number language
	the detector's own default applies (digits follow the text). It reads through the pipeline's
	internal breaks, as the driver wires it (spec fix/leading-punctuation-language D13), unless
	internal_breaks is False."""
	providers = {} if number_language is None else {"number_language": lambda: number_language}
	if internal_breaks:
		providers["is_internal_break"] = env.breaks.is_internal_break
	return env.module.LanguageDetector(
		list(languages),
		settings=env.settings,
		language=lambda: env.state.language,
		**providers,
	)


def shape(env, sequence):
	return [
		("lang", item.lang) if isinstance(item, (env.WV, LangChangeCommand)) else item for item in sequence
	]


def switching(env):
	return env.conf["WorldVoice"]["autoLanguageSwitching"]


L = LangChangeCommand

PREFERENCE_KEYS = {
	"cjk": "cjkCharactersLanguage",
	"latin": "latinCharactersLanguage",
	"arabic": "arabicCharactersLanguage",
	"cyrillic": "cyrillicCharactersLanguage",
	"devanagari": "devanagariCharactersLanguage",
}


def detect(env, sequence, *, languages, base, number_language=None, **preferences):
	"""Detect with the given installed languages, synth language, number language and detection
	preferences."""
	env.state.language = base
	for name, value in preferences.items():
		switching(env)[PREFERENCE_KEYS[name]] = value
	detector = make_detector(env, languages=languages, number_language=number_language)
	return shape(env, detector.add_detected_language_commands(sequence))


# Outputs that phase 33 must not change (its spec §10.1).
@pytest.mark.parametrize(
	"languages,base,preferences,sequence,expected",
	[
		pytest.param(
			("en_US", "zh_TW"),
			"en_US",
			{"cjk": "zh_TW"},
			["hi 你好，世界。"],
			["hi ", ("lang", "zh_TW"), "你好，世界。"],
			id="full-width",
		),
		pytest.param(
			("en_US", "ko_KR", "ja_JP"),
			"ko_KR",
			{},
			["한국 漢字 한국"],
			["한국 漢字 한국"],
			id="hanja",
		),
		pytest.param(
			("en_US", "hi_IN"),
			"en_US",
			{},
			["hi नमस्ते"],
			["hi ", ("lang", "hi"), "नमस्ते"],
			id="hindi",
		),
		pytest.param(
			("en_US", "my_MM"),
			"en_US",
			{},
			["hi မြန်မာ"],
			["hi ", ("lang", "my"), "မြန်မာ"],
			id="myanmar",
		),
		pytest.param(
			("en_US", "ar-WW"),
			"en_US",
			{},
			["hi مرحبا"],
			["hi ", ("lang", "ar"), "مرحبا"],
			id="hyphenated-voice",
		),
		pytest.param(
			("en_US", "uk_UA", "ru_RU"),
			"en_US",
			{},
			["hi привет"],
			["hi ", ("lang", "ru"), "привет"],
			id="ru-before-uk",
		),
		pytest.param(("en_US",), "en_US", {}, ["hi Ελληνικά"], ["hi Ελληνικά"], id="no-greek-voice"),
		# Phase 35: digits follow the text; the number language is the pipeline's (spec §6.3).
		pytest.param(
			("en_US", "zh_TW"),
			"en_US",
			{"cjk": "zh_TW"},
			["中12"],
			[("lang", "zh_TW"), "中12"],
			id="digits-follow",
		),
		pytest.param(
			("zh_TW",),
			"zh_TW",
			{},
			[L("de_DE"), "hallo 你好"],
			[("lang", "de_DE"), "hallo ", ("lang", "zh"), "你好"],
			id="no-latin-voice",
		),
	],
)
def test_detection_characterization(env, languages, base, preferences, sequence, expected):
	assert detect(env, sequence, languages=languages, base=base, **preferences) == expected


# Characters Unicode 17.0 and 18.0 assigned to scripts detection knows (fix/unicode-18). Seal, a
# script of its own since 18.0, has no language.
@pytest.mark.parametrize(
	"languages,base,preferences,sequence,expected",
	[
		pytest.param(
			("en_US", "zh_TW"),
			"en_US",
			{"cjk": "zh_TW"},
			["hi \U000323b0\U000323b1"],
			["hi ", ("lang", "zh_TW"), "\U000323b0\U000323b1"],
			id="cjk-extension-j",
		),
		pytest.param(
			("en_US", "ja_JP"),
			"en_US",
			{},
			["hi \U0001b123\U0001b124"],
			["hi ", ("lang", "ja"), "\U0001b123\U0001b124"],
			id="new-kana",
		),
		pytest.param(
			("en_US", "zh_TW"),
			"en_US",
			{"cjk": "zh_TW"},
			["hi \U0003d000"],
			["hi \U0003d000"],
			id="seal-is-not-han",
		),
	],
)
def test_detection_of_unicode_18_characters(env, languages, base, preferences, sequence, expected):
	assert detect(env, sequence, languages=languages, base=base, **preferences) == expected


# Cyrillic and Devanagari have an assumed-language choice like Latin, Han and Arabic (2026-10-23).
@pytest.mark.parametrize(
	"languages,preferences,sequence,expected",
	[
		pytest.param(
			("en_US", "ru_RU", "uk_UA"),
			{"cyrillic": "uk"},
			["hi привіт"],
			["hi ", ("lang", "uk"), "привіт"],
			id="cyrillic-uk",
		),
		pytest.param(
			("en_US", "ru_RU", "uk_UA"),
			{"cyrillic": "ru_RU"},
			["hi привет"],
			["hi ", ("lang", "ru_RU"), "привет"],
			id="cyrillic-regional",
		),
		pytest.param(
			("en_US", "uk_UA"),
			{"cyrillic": "ru"},
			["hi привіт"],
			["hi ", ("lang", "uk"), "привіт"],
			id="cyrillic-without-a-voice",
		),
		pytest.param(
			("en_US", "hi_IN", "mr_IN"),
			{"devanagari": "mr"},
			["hi नमस्कार"],
			["hi ", ("lang", "mr"), "नमस्कार"],
			id="devanagari-mr",
		),
	],
)
def test_configured_cyrillic_and_devanagari_languages(env, languages, preferences, sequence, expected):
	assert detect(env, sequence, languages=languages, base="en_US", **preferences) == expected


# A language counts only with an installed voice (phase 33 spec §3); availability is by primary subtag.
@pytest.mark.parametrize(
	"languages,base,preferences,sequence,expected",
	[
		pytest.param(
			("en_US", "zh_TW"),
			"en_US",
			{},
			[L("de_DE"), "hallo 你好"],
			[("lang", "de_DE"), ("lang", "en"), "hallo ", ("lang", "zh"), "你好"],
			id="C1",
		),
		pytest.param(
			("en_US", "zh_TW"),
			"en_US",
			{},
			[L("de_DE"), ", hallo"],
			# The leading ", " follows "hallo" (spec fix/leading-punctuation-language D5).
			[("lang", "de_DE"), ("lang", "en"), ", hallo"],
			id="C2",
		),
		pytest.param(
			("fr_FR", "zh_TW", "en_US"),
			"zh_TW",
			{"latin": "fr"},
			[L("de_DE"), "hallo"],
			[("lang", "de_DE"), ("lang", "fr"), "hallo"],
			id="C4",
		),
		pytest.param(
			("en_US", "zh_TW"),
			"en_US",
			{},
			[L("en_GB"), "hello"],
			[("lang", "en_GB"), "hello"],
			id="installed-primary",
		),
	],
)
def test_unavailable_language_does_not_cover_its_script(
	env,
	languages,
	base,
	preferences,
	sequence,
	expected,
):
	assert detect(env, sequence, languages=languages, base=base, **preferences) == expected


# After a run in another script, the base language comes back before the preference (phase 33 spec §2).
@pytest.mark.parametrize(
	"languages,base,preferences,sequence,expected",
	[
		pytest.param(
			("en_US", "zh_TW", "ja_JP"),
			"zh_TW",
			{"cjk": "ja"},
			["你好 hello 世界"],
			["你好 ", ("lang", "en"), "hello ", ("lang", "zh_TW"), "世界"],
			id="R1",
		),
		pytest.param(
			("en_GB", "en_US", "zh_TW"),
			"en_GB",
			{"cjk": "zh_TW"},
			["hi 你好 ok"],
			["hi ", ("lang", "zh_TW"), "你好 ", ("lang", "en_GB"), "ok"],
			id="R2",
		),
		pytest.param(
			("en_US", "zh_TW", "ja_JP"),
			"zh_TW",
			{"cjk": "ja"},
			[L("ja"), "中", L(None), "a中"],
			[("lang", "ja"), "中", ("lang", None), ("lang", "en"), "a", ("lang", "zh_TW"), "中"],
			id="R4",
		),
		pytest.param(
			("en_US", "ar-WW"),
			"ar-WW",
			{},
			["مرحبا hi مرحبا"],
			["مرحبا ", ("lang", "en"), "hi ", ("lang", "ar-WW"), "مرحبا"],
			id="hyphenated-base",
		),
	],
)
def test_base_language_wins_after_another_script(env, languages, base, preferences, sequence, expected):
	assert detect(env, sequence, languages=languages, base=base, **preferences) == expected


# The current language still comes before the base: kana or Hangul switch the run, and the Han
# that follows stays in it although the base covers Han too.
@pytest.mark.parametrize(
	"languages,sequence,expected",
	[
		pytest.param(
			("en_US", "zh_TW", "ja_JP"),
			["ひらがな漢字"],
			[("lang", "ja"), "ひらがな漢字"],
			id="kana",
		),
	],
)
def test_current_language_comes_before_the_base(env, languages, sequence, expected):
	assert detect(env, sequence, languages=languages, base="zh_TW", cjk="ja") == expected


def test_spelling_keeps_the_current_language_before_the_locale(env):
	detector = make_detector(env, ("en_US", "zh_TW", "ja_JP"))
	assert list(detector.process_for_spelling("ひ漢", "zh_TW")) == [("ひ漢", "ja")]


@pytest.mark.parametrize("base,expected", [("zh_TW", "zh_TW"), ("ko_KR", "ja")])
def test_find_language_for_script_prefers_an_available_base(env, base, expected):
	switching(env)["cjkCharactersLanguage"] = "ja"
	assert make_detector(env).find_language_for_script("Han", "en_US", base_language=base) == expected


# Spelling answers like detection, with the spelling locale as the base (phase 33 spec §2.4).
@pytest.mark.parametrize(
	"languages,cjk,text,locale,expected",
	[
		pytest.param(
			("en_US", "zh_TW", "ja_JP"),
			"zh_TW",
			"a漢",
			"ja_JP",
			[("a", "en"), ("漢", "ja_JP")],
			id="base-ja",
		),
		pytest.param(
			("en_US", "zh-TW"),
			"zh",
			"a漢",
			"zh-TW",
			[("a", "en"), ("漢", "zh-TW")],
			id="hyphenated-locale",
		),
	],
)
def test_spelling_prefers_the_spelling_locale(env, languages, cjk, text, locale, expected):
	switching(env)["cjkCharactersLanguage"] = cjk
	assert list(make_detector(env, languages).process_for_spelling(text, locale)) == expected


def test_script_without_an_installed_language_keeps_the_current_language(env):
	# No Greek voice: the Greek stays in the zh run instead of returning to the base.
	assert detect(env, ["中Ελλ"], languages=("en_US", "zh_TW"), base="en_US") == [("lang", "zh"), "中Ελλ"]
	detector = make_detector(env, ("en_US", "zh_TW"))
	assert list(detector.process_for_spelling("中Ελ", "en_US")) == [("中Ελ", "zh")]


def test_spelling_with_an_unavailable_locale(env):
	result = list(make_detector(env, languages=("en_US", "zh_TW")).process_for_spelling("a b", "de_DE"))
	assert result == [("a", "en"), (" ", "de_DE"), ("b", "en")]


# Under "Follow surrounding text language" a decimal digit with a script (Arabic-Indic digits are
# Arabic) follows the letter rule of its script; Common digits stay in the run (spec
# fix/script-digit-language G1, decided by the user 2026-11-07, superseding phase 35 spec §6.3).
@pytest.mark.parametrize(
	("sequence", "expected"),
	[
		(["abc ١٢٣"], ["abc ", ("lang", "ar"), "١٢٣"]),
	],
	ids=["abc-arabic-indic"],
)
def test_decimal_digits_follow_the_letter_rule_of_their_script(env, sequence, expected):
	detector = make_detector(env, ("en_US", "zh_TW", "ar"))
	assert shape(env, detector.add_detected_language_commands(sequence)) == expected


NE = ("en_US", "ne_NP")
# A command detection passes through as itself.
MARKER = object()


# The reported case (spec fix/script-digit-language §3): Devanagari digits with no Devanagari letter
# before them go to Nepali, not to the English main voice.
@pytest.mark.parametrize(
	("sequence", "expected"),
	[
		(["२०८१ साल"], [("lang", "ne"), "२०८१ साल"]),
		(["२०८१"], [("lang", "ne"), "२०८१"]),
		(["link", "२०८१"], ["link", ("lang", "ne"), "२०८१"]),
		(["२०८१ link"], [("lang", "ne"), "२०८१ ", ("lang", "en_US"), "link"]),
		(["नेपालमा ५० जिल्ला"], [("lang", "ne"), "नेपालमा ५० जिल्ला"]),
		(["abc 123"], ["abc 123"]),
		(["abc １２３"], ["abc １２３"]),
		# At an item's start the leading "1" follows "२" (spec fix/leading-punctuation-language U9,
		# superseding G2 of fix/script-digit-language there).
		(["1२3"], [("lang", "ne"), "1२3"]),
		([L("ne_NP"), "२०८१"], [("lang", "ne_NP"), "२०८१"]),
		(["नेपाल", "२०८१"], [("lang", "ne"), "नेपाल", "२०८१"]),
		(["२", MARKER, "०"], [("lang", "ne"), "२", MARKER, "०"]),
	],
	ids=[
		"year-then-word",
		"year-alone",
		"after-english-item",
		"back-to-english",
		"nepali-text",
		"ascii",
		"full-width",
		"mixed",
		"covering-document-language",
		"after-nepali-item",
		"other-command-between",
	],
)
def test_script_digits_go_to_their_scripts_language(env, sequence, expected):
	assert detect(env, sequence, languages=NE, base="en_US") == expected


def test_script_digits_without_a_voice_for_their_script_stay(env):
	assert detect(env, ["२०८१"], languages=("en_US", "zh_TW"), base="en_US") == ["२०८१"]


# "main" and a locale wrap every number before detection (detect_with_number_language): the digits
# stay in the wrapper's language, and the rule reads the number language, not the wrapper.
@pytest.mark.parametrize(
	("number_language", "wrapped"),
	[("main", True), ("main", False)],
	ids=["main-wrapped", "main-unwrapped"],
)
def test_other_number_languages_keep_digits_in_the_current_run(env, number_language, wrapped):
	env.state.language = "en_US"
	sequence = [env.WV("en_US"), "२०८१", env.WV("en_US")] if wrapped else ["२०८१"]
	detector = make_detector(env, NE, number_language)
	result = list(detector.add_detected_language_commands(sequence))
	assert [
		item for item in result if isinstance(item, env.WV) and all(item is not c for c in sequence)
	] == []
	assert "".join(item for item in result if isinstance(item, str)) == "२०८१"


@pytest.mark.parametrize("assumed", ["ne"])
def test_the_devanagari_assumed_language_picks_the_digit_language(env, assumed):
	result = detect(env, ["२०८१"], languages=("en_US", "hi_IN", "ne_NP"), base="en_US", devanagari=assumed)
	assert result == [("lang", assumed), "२०८१"]


def test_a_script_digit_prefers_a_covering_base_language(env):
	result = detect(
		env,
		[L("hi_IN"), "abc २"],
		languages=("en_US", "hi_IN", "ne_NP"),
		base="en_US",
		devanagari="ne",
	)
	assert result == [("lang", "hi_IN"), ("lang", "en"), "abc ", ("lang", "hi_IN"), "२"]


def test_detection_reads_the_number_language_once_per_sequence(env):
	reads = []
	detector = env.module.LanguageDetector(
		list(NE),
		settings=env.settings,
		language=lambda: env.state.language,
		number_language=lambda: reads.append(1) or "default",
	)
	list(detector.add_detected_language_commands(["१ a २", "३", '"', EndUtteranceCommand(), "("]))
	assert reads == [1]


# Leading punctuation follows the text after it (spec fix/leading-punctuation-language U1, U2, D1, D2):
# the Common and Inherited characters before an item's first deciding character take its language.
ZH = ("en_US", "zh_TW")
BREAK = BreakCommand(10)


@pytest.mark.parametrize(
	("sequence", "languages", "base", "expected"),
	[
		(['"नेपाल"'], NE, "en_US", [("lang", "ne"), '"नेपाल"']),
		(["- नेपाल"], NE, "en_US", [("lang", "ne"), "- नेपाल"]),
		(['" २०८१'], NE, "en_US", [("lang", "ne"), '" २०८१']),
		(["link", BREAK, '"नेपाल"'], NE, "en_US", ["link", BREAK, ("lang", "ne"), '"नेपाल"']),
		([L("en"), '"नेपाल"'], NE, "en_US", [("lang", "en"), ("lang", "ne"), '"नेपाल"']),
		(["「中文」"], ZH, "en_US", [("lang", "zh"), "「中文」"]),
		(['"Hello"'], NE, "ne_NP", [("lang", "en"), '"Hello"']),
		(["2024年"], ZH, "en_US", [("lang", "zh"), "2024年"]),
		(["3 apples"], ZH, "zh_TW", [("lang", "en"), "3 apples"]),
	],
	ids=[
		"quote",
		"dash",
		"quote-script-digits",
		"after-an-item",
		"after-a-document-language",
		"corner-bracket",
		"mirror",
		"leading-digits-han",
		"leading-digits-latin",
	],
)
def test_a_leading_run_follows_the_text_after_it(env, sequence, languages, base, expected):
	assert detect(env, sequence, languages=languages, base=base) == expected


@pytest.mark.parametrize(
	("sequence", "languages", "base", "number_language", "expected"),
	[
		(['abc "नेपाल"'], NE, "en_US", None, ['abc "', ("lang", "ne"), 'नेपाल"']),
		(['नेपाल "नेपाल"'], NE, "en_US", None, [("lang", "ne"), 'नेपाल "नेपाल"']),
		(['"'], NE, "en_US", None, ['"']),
		(["link", BREAK, "("], NE, "en_US", None, ["link", BREAK, "("]),
		([L("ne_NP"), '"नेपाल"'], NE, "en_US", None, [("lang", "ne_NP"), '"नेपाल"']),
		(['"नेपाल"'], ZH, "en_US", None, ['"नेपाल"']),
		(['"ᏣᎳᎩ'], NE, "en_US", None, ['"ᏣᎳᎩ']),
		(["「中文」"], ZH, "zh_TW", None, ["「中文」"]),
		(["2024年"], ZH, "en_US", "main", ["2024", ("lang", "zh"), "年"]),
	],
	ids=[
		"mid-line",
		"after-nepali",
		"mark-alone",
		"mark-alone-after-an-item",
		"covering-document-language",
		"no-devanagari-voice",
		"cherokee",
		"corner-bracket-zh",
		"main-unwrapped-digits",
	],
)
def test_detection_keeps_these_as_today(env, sequence, languages, base, number_language, expected):
	assert detect(env, sequence, languages=languages, base=base, number_language=number_language) == expected


INTERNAL_BREAKS = [
	"InternalPunctuationBreakCommand",
	"SegmentBreakCommand",
	"NumberBreakCommand",
	"NumberEdgeBreakCommand",
	"UnspacedSpaceBreakCommand",
]


# Option H (spec U5): a pause a stage puts inside an item does not end it, so ' "' stays mid-line.
@pytest.mark.parametrize("name", INTERNAL_BREAKS)
def test_internal_breaks_continue_the_item(env, name):
	pause = getattr(env.breaks, name)(0)
	result = detect(env, ["abc", ",", pause, ' "नेपाल"'], languages=NE, base="en_US")
	assert result == ["abc", ",", pause, ' "', ("lang", "ne"), 'नेपाल"']


@pytest.mark.parametrize(
	"name",
	["PunctuationBreakCommand", "NumberItemEdgeBreakCommand", "IndexCommand", "plain"],
)
def test_boundaries_end_the_item(env, name):
	if name == "plain":
		boundary = BreakCommand(10)
	elif name == "IndexCommand":
		boundary = env.IndexCommand(1)
	else:
		boundary = getattr(env.breaks, name)(0)
	result = detect(env, ["abc", ",", boundary, ' "नेपाल"'], languages=NE, base="en_US")
	assert result == ["abc", ",", boundary, ("lang", "ne"), ' "नेपाल"']


def test_adjacent_strings_are_one_item(env):
	# With the item pause at 0 the item boundary is invisible: the limitation of spec U5.
	assert detect(env, ["link", '"नेपाल"'], languages=NE, base="en_US") == [
		"link",
		'"',
		("lang", "ne"),
		'नेपाल"',
	]
	pause = env.breaks.NumberBreakCommand(10)
	assert detect(env, ["abc ", "12", pause, "34", " (नेपाल)"], languages=NE, base="en_US") == [
		"abc ",
		"12",
		pause,
		"34",
		" (",
		("lang", "ne"),
		"नेपाल)",
	]


def test_a_wrapped_number_keeps_its_item(env):
	# Spec D3: the wrappers continue the item and the wrapped number stops every search.
	opening, closing = env.WV("en_US"), env.WV("en_US")
	result = detect(
		env,
		["नेपाल (", opening, "2024", closing, ") नेपाल"],
		languages=NE,
		base="en_US",
		number_language="main",
	)
	assert result == [
		("lang", "ne"),
		"नेपाल (",
		("lang", "en_US"),
		"2024",
		("lang", "en_US"),
		") ",
		("lang", "ne"),
		"नेपाल",
	]


def test_without_the_internal_break_check_every_break_ends_an_item(env):
	# Spec D13: the detector's own default reads through no break.
	pause = env.breaks.InternalPunctuationBreakCommand(0)
	detector = make_detector(env, NE, internal_breaks=False)
	result = shape(env, detector.add_detected_language_commands(["abc", ",", pause, ' "नेपाल"']))
	assert result == ["abc", ",", pause, ("lang", "ne"), ' "नेपाल"']


def test_blank_text_joins_the_leading_run(env):
	assert detect(env, ["", '"नेपाल"'], languages=NE, base="en_US") == [("lang", "ne"), '"नेपाल"']
	assert detect(env, [" ", "(नेपाल"], languages=NE, base="en_US") == [("lang", "ne"), " ", "(नेपाल"]


def test_inherited_marks_join_the_leading_run(env):
	assert detect(env, ["\u0301नेपाल"], languages=NE, base="en_US") == [("lang", "ne"), "\u0301नेपाल"]
	assert detect(env, ["\u094dनेपाल"], languages=NE, base="en_US") == [("lang", "ne"), "\u094dनेपाल"]


def test_spelling_keeps_a_leading_mark_in_the_locale(env):
	# Spec D7: spelling is unchanged.
	assert list(make_detector(env, NE).process_for_spelling('"नेपाल', "en_US")) == [
		('"', "en_US"),
		("नेपाल", "ne"),
	]


# Items with nothing that decides: at an utterance's start they look ahead to the first deciding
# character; after one they keep the language before them (spec U7, U8, D9-D11).
END = EndUtteranceCommand()
TRIGGER = ConfigProfileTriggerCommand()


@pytest.mark.parametrize(
	("sequence", "expected"),
	[
		(
			["(", "IPB", "नेपाल)"],
			[("lang", "ne"), "(", "IPB", "नेपाल)"],
		),
		(["-", BREAK, "नेपाल"], [("lang", "ne"), "-", BREAK, "नेपाल"]),
		(["(", BREAK, "1", BREAK, "नेपाल"], [("lang", "ne"), "(", BREAK, "1", BREAK, "नेपाल"]),
		(["Price", BREAK, "100", BREAK, "नेपाल"], ["Price", BREAK, "100", BREAK, ("lang", "ne"), "नेपाल"]),
		(["(", BREAK], ["(", BREAK]),
	],
	ids=["internal-punctuation", "dash-item", "paren-and-digit-items", "price", "mark-alone"],
)
def test_an_utterance_start_looks_ahead(env, sequence, expected):
	pause = env.breaks.InternalPunctuationBreakCommand(0)
	sequence = [pause if item == "IPB" else item for item in sequence]
	expected = [pause if item == "IPB" else item for item in expected]
	assert detect(env, sequence, languages=NE, base="en_US") == expected


def test_a_wrapped_number_stops_the_lookahead(env):
	opening, closing = env.WV("en_US"), env.WV("en_US")
	result = detect(
		env,
		["(", BREAK, opening, "1", closing, BREAK, "नेपाल"],
		languages=NE,
		base="en_US",
		number_language="main",
	)
	assert result == ["(", BREAK, ("lang", "en_US"), "1", ("lang", "en_US"), BREAK, ("lang", "ne"), "नेपाल"]
	result = detect(
		env,
		[opening, "2024", closing, BREAK, "(", BREAK, "नेपाल"],
		languages=NE,
		base="en_US",
		number_language="main",
	)
	assert result == [("lang", "en_US"), "2024", ("lang", "en_US"), BREAK, "(", BREAK, ("lang", "ne"), "नेपाल"]


@pytest.mark.parametrize(
	("sequence", "expected"),
	[
		(
			["नेपाल", END, "(", BREAK, "abc"],
			[("lang", "ne"), "नेपाल", END, ("lang", "en_US"), "(", BREAK, "abc"],
		),
		(
			["नेपाल", TRIGGER, "(", BREAK, "abc"],
			[("lang", "ne"), "नेपाल", TRIGGER, ("lang", "en_US"), "(", BREAK, "abc"],
		),
		(
			["नेपाल", "(", BREAK, "abc"],
			[("lang", "ne"), "नेपाल", "(", BREAK, ("lang", "en_US"), "abc"],
		),
		(["(", END, "नेपाल"], ["(", END, ("lang", "ne"), "नेपाल"]),
		(["नेपाल", END, "100"], [("lang", "ne"), "नेपाल", END, "100"]),
	],
	ids=["utterance-end", "profile-trigger", "no-utterance-end", "no-lookahead-across", "run-carries-over"],
)
def test_utterances_bound_the_lookahead(env, sequence, expected):
	assert detect(env, sequence, languages=NE, base="en_US") == expected


HI_NE = ("en_US", "hi_IN", "ne_NP")


@pytest.mark.parametrize(
	("sequence", "preferences", "expected"),
	[
		(['"', L("hi_IN"), "नेपाल"], {}, [("lang", "hi_IN"), '"', ("lang", "hi_IN"), "नेपाल"]),
		(
			[L("ne_NP"), '"', L("hi_IN"), "नेपाल"],
			{},
			[("lang", "ne_NP"), '"', ("lang", "hi_IN"), "नेपाल"],
		),
		(
			[L("hi_IN"), "abc", BREAK, '"नेपाल"'],
			{"devanagari": "ne"},
			[("lang", "hi_IN"), ("lang", "en"), "abc", BREAK, ("lang", "hi_IN"), '"नेपाल"'],
		),
	],
	ids=["across-a-document-language", "covered", "base-before-the-assumed-language"],
)
def test_the_lookahead_across_a_document_language(env, sequence, preferences, expected):
	assert detect(env, sequence, languages=HI_NE, base="en_US", **preferences) == expected


def test_the_lookahead_keeps_the_language_when_no_voice_reads_the_text(env):
	# Spec §4.4: across a document language with no voice for the script, nothing changes.
	assert detect(env, ['"', L("hi_IN"), "नेपाल"], languages=ZH, base="en_US") == [
		'"',
		("lang", "hi_IN"),
		"नेपाल",
	]


def test_a_run_reads_the_first_character_of_every_string(env):
	# The deciding character may open the string after an internal break (mutation testing).
	pause = env.breaks.InternalPunctuationBreakCommand(0)
	assert detect(env, ["(", pause, "中"], languages=ZH, base="en_US") == [("lang", "zh"), "(", pause, "中"]


def test_each_stretch_of_a_run_takes_its_own_target(env):
	# The first stretch is covered by its document language and keeps it; the one after "en" takes the
	# assumed Devanagari language (spec D10, D2).
	result = detect(env, [L("ne_NP"), '"', L("en"), '"नेपाल'], languages=HI_NE, base="en_US")
	assert result == [("lang", "ne_NP"), '"', ("lang", "en"), ("lang", "hi"), '"नेपाल']


def test_a_run_across_two_document_languages_adds_no_switch(env):
	# Review I2: the middle stretch keeps its covering Nepali, so the stretch before it keeps today's
	# rule instead of taking Hindi, which would go Hindi, Nepali, Hindi (spec D6, D10).
	sequence = [L("de_DE"), '"', L("ne_NP"), "(", L("hi_IN"), "नेपाल"]
	result = detect(env, sequence, languages=("en_US", "zh_TW", "ne_NP", "hi_IN"), base="ne_NP")
	assert result == [("lang", "de_DE"), '"', ("lang", "ne_NP"), "(", ("lang", "hi_IN"), "नेपाल"]


def test_detection_ends_an_utterance_where_the_pipeline_does(env):
	# Review M5: the detector keeps its own copy of pipeline.sequence._ends_utterance (spec D13 keeps
	# the pipeline out of it); the two must agree on every command.
	sequence = sys.modules[env.breaks.__package__ + ".sequence"]
	commands = [EndUtteranceCommand(), ConfigProfileTriggerCommand(), BreakCommand(1), env.IndexCommand(1)]
	commands += [env.WV("en"), L("en"), env.breaks.SegmentBreakCommand(1), object()]
	for command in commands:
		utterances = list(env.module._utterances(["a", command, "b"]))
		assert (utterances == [["a", command], ["b"]]) is sequence._ends_utterance(command), command
		assert utterances in ([["a", command], ["b"]], [["a", command, "b"]]), command


def test_a_generator_input_with_utterance_ends_keeps_every_command(env):
	counting = CountingSettings(env.settings)
	detector = env.module.LanguageDetector(
		list(NE),
		settings=counting,
		language=lambda: env.state.language,
		is_internal_break=env.breaks.is_internal_break,
	)
	commands = [BREAK, END, TRIGGER]
	result = list(detector.add_detected_language_commands(iter(["(", BREAK, END, '"नेपाल"', TRIGGER, "x"])))
	assert [item for item in result if any(item is command for command in commands)] == commands
	assert "".join(item for item in result if isinstance(item, str)) == '("नेपाल"x'
	assert counting.reads == 1


def test_a_long_common_only_utterance_stays_linear(env):
	sequence = [item for _ in range(20000) for item in (".", BreakCommand(1))]
	start = time.perf_counter()
	result = list(make_detector(env, NE).add_detected_language_commands(sequence))
	assert time.perf_counter() - start < 2
	assert result == sequence


# Spelling follows the number language (phase 35 spec §5, decided by the user 2026-10-23).
@pytest.mark.parametrize(
	("number_language", "expected"),
	[
		("default", [("中1", "zh")]),
		("main", [("中", "zh"), ("1", "en_US")]),
		("en", [("中", "zh"), ("1", "en")]),
	],
)
def test_spelling_digits_follow_the_number_language(env, number_language, expected):
	detector = make_detector(env, ("en_US", "zh_TW"), number_language)
	assert list(detector.process_for_spelling("中1", "en_US")) == expected


def test_spelling_keeps_a_superscript_in_its_run(env):
	# "²" is not a decimal digit: it is not spelled in the spelling locale under "main".
	detector = make_detector(env, ("en_US", "zh_TW"), "main")
	assert list(detector.process_for_spelling("中²", "en_US")) == [("中²", "zh")]


def test_spelling_keeps_one_run_for_a_number_language_of_the_same_primary(env):
	# Runs split only when the primary subtag changes.
	detector = make_detector(env, ("en_US", "zh_TW"), "zh_TW")
	assert list(detector.process_for_spelling("中1", "en_US")) == [("中1", "zh")]


def test_spelling_uses_the_locale_for_a_number_language_without_a_voice(env):
	# Decided by the user (2026-10-23, Q10).
	detector = make_detector(env, ("en_US", "zh_TW"), "fr")
	assert list(detector.process_for_spelling("中1", "en_US")) == [("中", "zh"), ("1", "en_US")]


def test_spelling_reads_the_number_language_once_per_call(env):
	reads = []
	detector = env.module.LanguageDetector(
		["en_US", "zh_TW"],
		settings=env.settings,
		language=lambda: env.state.language,
		number_language=lambda: reads.append(1) or "main",
	)
	assert list(detector.process_for_spelling("1a2b3", "en_US")) == [("1a2b3", "en_US")]
	assert reads == [1]


# Spelling reads a digit with a script by its script under "default" (spec fix/script-digit-language
# D3), and in the spelling locale under "main".
@pytest.mark.parametrize(
	("number_language", "expected"),
	[("default", [("abc", "en_US"), ("١٢", "ar")])],
)
def test_spelling_arabic_indic_digits_follow_the_number_language(env, number_language, expected):
	detector = make_detector(env, ("en_US", "ar"), number_language)
	assert list(detector.process_for_spelling("abc١٢", "en_US")) == expected


@pytest.mark.parametrize(
	("number_language", "text", "expected"),
	[
		("default", "२", [("२", "ne")]),
		("main", "२", [("२", "en_US")]),
		# Runs split only when the primary language changes, so "en" keeps the locale's run.
		("en", "२", [("२", "en_US")]),
		("default", "1२", [("1", "en_US"), ("२", "ne")]),
		# A Common digit continues the run of the script digit before it (review M3).
		("default", "२1", [("२1", "ne")]),
		("default", "नेपाल५", [("नेपाल५", "ne")]),
		("default", "२ ३", [("२", "ne"), (" ", "en_US"), ("३", "ne")]),
	],
	ids=["alone", "main", "locale", "mixed", "script-then-common", "nepali-text", "space-between"],
)
def test_spelling_script_digits(env, number_language, text, expected):
	detector = make_detector(env, ("en_US", "ne_NP"), number_language)
	assert list(detector.process_for_spelling(text, "en_US")) == expected


def test_language_commands_reset_the_base_language(env):
	ja, back = LangChangeCommand("ja"), LangChangeCommand(None)
	result = list(make_detector(env).add_detected_language_commands([ja, "中", back, "中"]))
	assert result[0] is ja and result[2] is back
	assert shape(env, result) == [("lang", "ja"), "中", ("lang", None), ("lang", "zh"), "中"]


def test_spelling_without_locale_uses_the_synth_language(env):
	result = list(make_detector(env).process_for_spelling("a中 1"))
	assert result == [("a", "en_US"), ("中", "zh"), (" 1", "en_US")]


def test_spelling_with_locale(env):
	result = list(make_detector(env).process_for_spelling("a中 1", "ja"))
	assert result == [("a", "en"), ("中 1", "ja")]


@pytest.mark.parametrize("configured,expected", [("ja", "ja"), ("ko", "zh")])
def test_configured_script_language_wins_only_when_available(env, configured, expected):
	switching(env)["cjkCharactersLanguage"] = configured
	assert make_detector(env).find_language_for_script("Han", "en_US") == expected


def test_script_without_candidates_keeps_the_current_language(env):
	assert make_detector(env).find_language_for_script("NoSuchScript", "en_US") == "en_US"


def test_language_is_read_per_call(env):
	detector = make_detector(env)
	assert shape(env, detector.add_detected_language_commands(["中"])) == [("lang", "zh"), "中"]
	env.state.language = "zh_TW"
	assert shape(env, detector.add_detected_language_commands(["中"])) == ["中"]


class CountingSettings:
	def __init__(self, settings):
		self._settings, self.reads = settings, 0

	def get(self):
		self.reads += 1
		return self._settings.get()


def test_one_settings_read_per_spelling(env):
	counting = CountingSettings(env.settings)
	detector = env.module.LanguageDetector(
		["en_US", "zh_TW", "ar"],
		settings=counting,
		language=lambda: env.state.language,
	)
	assert list(detector.process_for_spelling("中a中a")) == [
		("中", "zh"),
		("a", "en_US"),
		("中", "zh"),
		("a", "en_US"),
	]
	assert counting.reads == 1


SCRIPT_SAMPLES = st.sampled_from(
	["hello", " ", "中文", "日本語", "عربي", "123", ",", "é", "\U0001f600", "\n"]
	+ ["漢字", "привет", "한국", "かな", "Ελληνικά", "12", "，", "नमस्ते"]
	# Phase 35: decimal digits of other scripts, and characters that only look like digits.
	+ ["١٢", "１２", "²", "①"]
	# Devanagari digits, which go to a Devanagari language (fix/script-digit-language).
	+ ["२०"]
	# Leading marks (fix/leading-punctuation-language).
	+ ['"', "(", "「", "- "],
)
TEXTS = st.lists(st.one_of(SCRIPT_SAMPLES, st.characters()), max_size=12).map("".join)
VOICES = (
	"en_US",
	"en_GB",
	"zh_TW",
	"ja_JP",
	"ko_KR",
	"ar-WW",
	"ru_RU",
	"uk_UA",
	"de_DE",
	"fr_FR",
	"hi_IN",
	"mr_IN",
	"ne_NP",
	"el_GR",
)
# Document languages: none, without a voice, hyphenated, a regional variant, primary only, unknown.
COMMAND_LANGUAGES = (None, "de_DE", "ar-WW", "zh_TW", "en_GB", "ja", "fr", "xx_YY")


class Token:
	"""A command drawn before the test has its env: materialize() makes it."""

	def __init__(self, *spec):
		self.spec = spec

	def __repr__(self):
		return f"Token{self.spec}"


BREAK_NAMES = (
	"InternalPunctuationBreakCommand",
	"PunctuationBreakCommand",
	"SegmentBreakCommand",
	"NumberBreakCommand",
	"NumberEdgeBreakCommand",
	"NumberItemEdgeBreakCommand",
	"UnspacedSpaceBreakCommand",
)
# Breaks of every class, number wrappers, index commands and utterance ends
# (spec fix/leading-punctuation-language §7.3).
COMMAND_TOKENS = st.one_of(
	st.sampled_from([*BREAK_NAMES, "plain", "index", "end", "trigger"]).map(Token),
	st.tuples(st.sampled_from(("en_US", "zh_TW", "ne_NP")), st.sampled_from(("12", "२०", "-3"))).map(
		lambda drawn: Token("wrap", *drawn),
	),
)
ITEMS = st.lists(
	st.one_of(
		TEXTS,
		st.sampled_from(COMMAND_LANGUAGES).map(LangChangeCommand),
		st.builds(object),
		COMMAND_TOKENS,
	),
	max_size=8,
)


def materialize(env, items):
	"""items with each Token made into its command; a wrapper becomes opening, number, closing."""
	made = []
	for item in items:
		if not isinstance(item, Token):
			made.append(item)
			continue
		kind, *rest = item.spec
		if kind == "wrap":
			language, number = rest
			made += [env.WV(language), number, env.WV(language)]
		elif kind == "plain":
			made.append(BreakCommand(10))
		elif kind == "index":
			made.append(env.IndexCommand(1))
		elif kind == "end":
			made.append(EndUtteranceCommand())
		elif kind == "trigger":
			made.append(ConfigProfileTriggerCommand())
		else:
			made.append(getattr(env.breaks, kind)(10))
	return made


@st.composite
def scenarios(draw):
	"""Installed voices, the synth language (always one of them), preferences and a spelling locale."""
	installed = draw(st.lists(st.sampled_from(VOICES), min_size=1, max_size=6, unique=True))
	return SimpleNamespace(
		installed=installed,
		base=draw(st.sampled_from(installed)),
		preferences={
			"cjk": draw(st.sampled_from(["zh", "zh_TW", "ja", "ko"])),
			"latin": draw(st.sampled_from(["en", "fr", "de"])),
			"arabic": draw(st.sampled_from(["ar", "fa"])),
			"cyrillic": draw(st.sampled_from(["ru", "uk", "bg"])),
			"devanagari": draw(st.sampled_from(["hi", "mr", "ne"])),
		},
		locale=draw(st.one_of(st.none(), st.sampled_from(COMMAND_LANGUAGES[1:] + tuple(installed)))),
	)


def scenario_detector(env, scenario):
	env.state.language = scenario.base
	for name, value in scenario.preferences.items():
		switching(env)[PREFERENCE_KEYS[name]] = value
	return make_detector(env, scenario.installed)


def has_script(env, character):
	"""Whether detection reads character by its script under "Follow surrounding text language":
	letters, and decimal digits of a script (fix/script-digit-language G1)."""
	return env.module.get_script(ord(character)) not in (
		None,
		"Common",
		"Inherited",
	)


def covers(env, scenario, language, script):
	"""The phase 33 rule, written out: a language of the script with an installed voice."""
	primary = env.module.primary_language(language)
	installed = {env.module.primary_language(voice) for voice in scenario.installed}
	return primary in env.script_languages.SCRIPT_LANGUAGES.get(script, ()) and primary in installed


def spoken_letters(env, scenario, items, result):
	"""Each letter or script digit of the output: its script, the language in effect, the base, and the language of
	the command detection inserted right before it (None if there is none)."""
	given = [item for item in items if not isinstance(item, str)]
	base = language = scenario.base
	inserted = None
	for item in result:
		if isinstance(item, str):
			for character in item:
				if has_script(env, character):
					yield env.module.get_script(ord(character)), language, base, inserted
				inserted = None
		elif not any(item is command for command in given):
			language = inserted = item.lang
		elif isinstance(item, (LangChangeCommand, env.WV)):
			# A given number wrapper sets the language and the base, as a document language does.
			base = language = item.lang or scenario.base


# The detector is stateless between calls, so one function-scoped env serves every example.
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(scenario=scenarios(), items=ITEMS)
def test_property_detection_only_inserts_language_changes(env, scenario, items):
	items = materialize(env, items)
	result = list(scenario_detector(env, scenario).add_detected_language_commands(items))
	assert all(item != "" for item in result), "an empty text was yielded"
	given = [item for item in items if not isinstance(item, str)]
	added = [item for item in result if not isinstance(item, str) and all(item is not c for c in given)]
	assert all(isinstance(item, env.WV) for item in added)
	# Without what detection added, the sequence is the input: same text, commands in place.
	kept = [item for item in result if isinstance(item, str) or any(item is c for c in given)]
	assert merge_texts(kept) == merge_texts(items)


def plain_scenario(installed, base):
	"""A fixed scenario with the shipped preferences, for the explicit examples."""
	preferences = {"cjk": "ja", "latin": "en", "arabic": "ar", "cyrillic": "ru", "devanagari": "hi"}
	return SimpleNamespace(installed=list(installed), base=base, preferences=preferences, locale=None)


# Random draws find these cases in most runs, not all; the examples make every run check them.
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(scenario=scenarios(), items=ITEMS)
@example(scenario=plain_scenario(("en_US", "zh_TW"), "en_US"), items=[L("de_DE"), "hallo"])
def test_property_letters_go_to_installed_languages(env, scenario, items):
	items = materialize(env, items)
	result = list(scenario_detector(env, scenario).add_detected_language_commands(items))
	installed = {env.module.primary_language(voice) for voice in scenario.installed}
	for script, language, _base, inserted in spoken_letters(env, scenario, items, result):
		if inserted is not None:
			assert env.module.primary_language(inserted) in installed
		if any(candidate in installed for candidate in env.script_languages.SCRIPT_LANGUAGES.get(script, ())):
			# Some installed language covers the script, so the letter is spoken in one of them.
			assert covers(env, scenario, language, script)


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(scenario=scenarios(), items=ITEMS)
@example(scenario=plain_scenario(("en_US", "zh_TW"), "en_US"), items=["中文hello"])
def test_property_inserted_commands_prefer_a_covering_base(env, scenario, items):
	items = materialize(env, items)
	result = list(scenario_detector(env, scenario).add_detected_language_commands(items))
	for script, _language, base, inserted in spoken_letters(env, scenario, items, result):
		if inserted is not None and covers(env, scenario, base, script):
			assert inserted == base


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(scenario=scenarios(), text=TEXTS)
def test_property_spelling_runs_of_the_base_primary_carry_the_base(env, scenario, text):
	runs = list(scenario_detector(env, scenario).process_for_spelling(text, scenario.locale))
	base = scenario.locale if scenario.locale is not None else scenario.base
	assert "".join(part for part, _language in runs) == text
	assert all(part for part, _language in runs)
	primary = env.module.primary_language
	assert all(language == base for _part, language in runs if primary(language) == primary(base))


def merge_texts(sequence):
	"""Join adjacent texts and drop empty ones, keeping commands where they are."""
	merged = []
	for item in sequence:
		if isinstance(item, str) and merged and isinstance(merged[-1], str):
			merged[-1] += item
		else:
			merged.append(item)
	return [item for item in merged if item != ""]


def runs_opened_by_digits(env, items, result):
	"""(inserted language, first character, the first character with a script after it or None) for
	each run detection opens with a decimal digit."""
	given = [item for item in items if not isinstance(item, str)]
	for index, (command, following) in enumerate(pairwise(result)):
		inserted = isinstance(command, env.WV) and all(command is not item for item in given)
		if inserted and isinstance(following, str) and following[0].isdecimal():
			later = "".join(item for item in result[index + 1 :] if isinstance(item, str))
			decider = next((character for character in later if has_script(env, character)), None)
			yield command.lang, following[0], decider


# Under "Follow surrounding text language" a digit with a script opens a run only in a language of
# that script (fix/script-digit-language G1, superseding phase 35 spec §11.4 item 4). A Common digit
# opens one only at the start of a leading run, in the language of the character with a script it
# leads to (spec fix/leading-punctuation-language U2).
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(scenario=scenarios(), items=ITEMS)
@example(scenario=plain_scenario(("en_US", "ne_NP"), "en_US"), items=["link", "२०८१ 12"])
@example(scenario=plain_scenario(("en_US", "zh_TW"), "en_US"), items=["2024年"])
def test_property_only_script_digits_start_a_detected_run(env, scenario, items):
	items = materialize(env, items)
	result = list(scenario_detector(env, scenario).add_detected_language_commands(items))
	for language, digit, decider in runs_opened_by_digits(env, items, result):
		character = digit if has_script(env, digit) else decider
		assert character is not None, (items, result)
		assert covers(env, scenario, language, env.module.get_script(ord(character))), (items, result)


# "main" and a locale keep every digit in the run it is in (phase 35 spec §11.4 item 4).
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(scenario=scenarios(), items=ITEMS, number_language=st.sampled_from(("main", "en", "zh_TW", "fr")))
@example(
	scenario=plain_scenario(("en_US", "ne_NP"), "en_US"),
	items=["link", "२०८१"],
	number_language="main",
)
def test_property_digits_never_start_a_detected_run_under_other_number_languages(
	env,
	scenario,
	items,
	number_language,
):
	items = materialize(env, items)
	detector = scenario_detector(env, scenario)
	detector._number_language = lambda: number_language
	result = list(detector.add_detected_language_commands(items))
	assert list(runs_opened_by_digits(env, items, result)) == [], (items, result)


SPELLING_NUMBER_LANGUAGES = ("default", "main", "en", "zh_TW", "fr")


# Phase 35 spec §11.4 item 6: every digit is spelled in the language spec §5 names.
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(scenario=scenarios(), text=TEXTS, number_language=st.sampled_from(SPELLING_NUMBER_LANGUAGES))
def test_property_spelling_digits_carry_the_number_language(env, scenario, text, number_language):
	detector = scenario_detector(env, scenario)
	detector._number_language = lambda: number_language
	runs = list(detector.process_for_spelling(text, scenario.locale))
	primary = env.module.primary_language
	base = scenario.locale if scenario.locale is not None else scenario.base
	installed = {primary(voice) for voice in scenario.installed}
	for index, (part, language) in enumerate(runs):
		if not any(character.isdecimal() for character in part):
			continue
		if number_language == "default":
			# Only a digit with a script opens a run, in a language of its script
			# (fix/script-digit-language D3); other digits follow the run they are in.
			if index > 0 and part[0].isdecimal():
				assert has_script(env, part[0]), (text, runs)
				assert covers(env, scenario, language, env.module.get_script(ord(part[0]))), (text, runs)
		elif number_language == "main" or primary(number_language) not in installed:
			assert primary(language) == primary(base), (text, runs)
		else:
			assert primary(language) == primary(number_language), (text, runs)


def character_languages(env, scenario, sequence):
	"""(character, language in effect) for every character of the sequence: every language command,
	inserted or given, sets the language."""
	language = scenario.base
	for item in sequence:
		if isinstance(item, str):
			for character in item:
				yield character, language
		elif isinstance(item, (LangChangeCommand, env.WV)):
			language = item.lang or scenario.base


def primary_changes(env, pairs):
	"""How often the primary language changes between two characters that are no whitespace."""
	primaries = [
		env.module.primary_language(language) for character, language in pairs if not character.isspace()
	]
	return sum(1 for before, after in pairwise(primaries) if before != after)


def voice_changes(env, scenario, pairs):
	"""How often the voice changes between two characters, whitespace included (a voice given only a
	space still costs a switch): a language with an installed voice is read by it, any other by the
	main voice (review M2)."""
	primary = env.module.primary_language
	installed = {primary(voice) for voice in scenario.installed}
	voices = [
		primary(language) if primary(language) in installed else primary(scenario.base)
		for _, language in pairs
	]
	return sum(1 for before, after in pairwise(voices) if before != after)


def inserted_languages(items, result):
	given = [item for item in items if not isinstance(item, str)]
	return [item.lang for item in result if not isinstance(item, str) and all(item is not c for c in given)]


# Invariant 1 (spec fix/leading-punctuation-language §4.3, D6): the rule only moves where the language
# changes to the start of a run and never adds a change.
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=300)
@given(scenario=scenarios(), items=ITEMS, number_language=st.sampled_from(("default", "main", "zh_TW")))
@example(scenario=plain_scenario(NE, "en_US"), items=['"नेपाल"'], number_language="default")
# Review I2: across two document languages the middle one keeps its covering language.
@example(
	scenario=plain_scenario(("en_US", "zh_TW", "ne_NP", "hi_IN"), "ne_NP"),
	items=[L("de_DE"), '"', L("ne_NP"), "(", L("hi_IN"), "नेपाल"],
	number_language="default",
)
# A run after a deciding character keeps the run language when the text after it is in that language.
@example(scenario=plain_scenario(ZH, "zh_TW"), items=["abc", "12abc"], number_language="default")
@example(
	scenario=plain_scenario(NE, "en_US"),
	items=["(", Token("end"), '"', "नेपाल"],
	number_language="default",
)
@example(scenario=plain_scenario(HI_NE, "en_US"), items=['"', L("hi_IN"), "नेपाल"], number_language="default")
def test_property_never_more_language_changes_than_today(env, scenario, items, number_language):
	items = materialize(env, items)
	detector = scenario_detector(env, scenario)
	detector._number_language = lambda: number_language
	result = list(detector.add_detected_language_commands(items))
	oracle = list(master_detection(detector, items))
	new, old = (
		list(character_languages(env, scenario, result)),
		list(character_languages(env, scenario, oracle)),
	)
	assert [character for character, _ in new] == [character for character, _ in old], (items, result)
	assert primary_changes(env, new) <= primary_changes(env, old), (items, result, oracle)
	assert voice_changes(env, scenario, new) <= voice_changes(env, scenario, old), (items, result, oracle)
	for (character, language), (_, expected) in zip(new, old):
		if has_script(env, character) or (character.isdecimal() and number_language != "default"):
			# A character that decides keeps today's language; only the runs before them move.
			assert language == expected, (character, items, result, oracle)
	if not any(isinstance(item, LangChangeCommand) for item in items):
		assert inserted_languages(items, result) == inserted_languages(items, oracle), (items, result, oracle)
