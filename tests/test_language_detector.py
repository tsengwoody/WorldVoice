"""Language detection: which language each run of text is spoken in."""

from types import SimpleNamespace

import pytest
from detector_harness import LangChangeCommand, load_language_detection
from hypothesis import HealthCheck, given, settings, strategies as st


@pytest.fixture
def env(stub_modules, monkeypatch):
	return load_language_detection(stub_modules, monkeypatch)


def make_detector(env, languages=("en_US", "zh_TW", "ja"), symbols=None):
	"""The one place the detector is built; its dependencies come from env."""
	return env.module.LanguageDetector(
		list(languages),
		symbols,
		settings=env.settings,
		language=lambda: env.state.language,
	)


def shape(env, sequence):
	return [
		("lang", item.lang) if isinstance(item, (env.WV, LangChangeCommand)) else item for item in sequence
	]


def switching(env):
	return env.conf["WorldVoice"]["autoLanguageSwitching"]


L = LangChangeCommand

PREFERENCE_KEYS = {
	"cjk": "CJKCharactersLanguage",
	"latin": "latinCharactersLanguage",
	"ignore_numbers": "ignoreNumbersInLanguageDetection",
}


def detect(env, sequence, *, languages, base, **preferences):
	"""Detect with the given installed languages, synth language and detection preferences."""
	env.state.language = base
	for name, value in preferences.items():
		switching(env)[PREFERENCE_KEYS[name]] = value
	return shape(env, make_detector(env, languages=languages).add_detected_language_commands(sequence))


# Outputs that phase 33 must not change (spec §10.1).
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
		pytest.param(
			("en_US", "zh_TW"),
			"en_US",
			{"cjk": "zh_TW"},
			["中12"],
			[("lang", "zh_TW"), "中", ("lang", "en_US"), "12"],
			id="digits-to-base",
		),
		pytest.param(
			("en_US", "zh_TW"),
			"en_US",
			{"cjk": "zh_TW", "ignore_numbers": True},
			["中12"],
			[("lang", "zh_TW"), "中12"],
			id="digits-ignored",
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


# A language counts only with an installed voice (spec §3); availability is by primary subtag.
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
			[("lang", "de_DE"), ", ", ("lang", "en"), "hallo"],
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
			{"ignore_numbers": True},
			[L("de_DE"), "12 hallo"],
			[("lang", "de_DE"), "12 ", ("lang", "en"), "hallo"],
			id="digits-ignored",
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


# After a run in another script, the base language comes back before the preference (spec §2).
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
			("en_US", "ja_JP", "zh_TW"),
			"ja_JP",
			{"cjk": "zh_TW"},
			["漢字 hello 漢字"],
			["漢字 ", ("lang", "en"), "hello ", ("lang", "ja_JP"), "漢字"],
			id="R3",
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
		pytest.param(("en_US", "zh_TW", "ko_KR"), ["한국漢字"], [("lang", "ko"), "한국漢字"], id="hangul"),
	],
)
def test_current_language_comes_before_the_base(env, languages, sequence, expected):
	assert detect(env, sequence, languages=languages, base="zh_TW", cjk="ja") == expected


def test_spelling_keeps_the_current_language_before_the_locale(env):
	detector = make_detector(env, ("en_US", "zh_TW", "ja_JP"))
	assert list(detector.process_for_spelling("ひ漢", "zh_TW")) == [("ひ漢", "ja")]


@pytest.mark.parametrize("base,expected", [("zh_TW", "zh_TW"), ("ko_KR", "ja")])
def test_find_language_for_script_prefers_an_available_base(env, base, expected):
	switching(env)["CJKCharactersLanguage"] = "ja"
	assert make_detector(env).find_language_for_script("Han", "en_US", base_language=base) == expected


# Spelling answers like detection, with the spelling locale as the base (spec §2.4).
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
			("en_US", "zh_TW", "ja_JP"),
			"ja",
			"a中",
			"zh_TW",
			[("a", "en"), ("中", "zh_TW")],
			id="base-zh",
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
	switching(env)["CJKCharactersLanguage"] = cjk
	assert list(make_detector(env, languages).process_for_spelling(text, locale)) == expected


def test_spelling_with_an_unavailable_locale(env):
	result = list(make_detector(env, languages=("en_US", "zh_TW")).process_for_spelling("a b", "de_DE"))
	assert result == [("a", "en"), (" ", "de_DE"), ("b", "en")]


def test_mixed_scripts_switch_at_script_boundaries(env):
	result = make_detector(env).add_detected_language_commands(["hello 中文 ok"])
	assert shape(env, result) == ["hello ", ("lang", "zh"), "中文 ", ("lang", "en_US"), "ok"]


@pytest.mark.parametrize(
	"ignore,expected",
	[
		(False, [("lang", "zh"), "中", ("lang", "en_US"), "1"]),
		(True, [("lang", "zh"), "中1"]),
	],
)
def test_digits_follow_the_ignore_numbers_setting(env, ignore, expected):
	switching(env)["ignoreNumbersInLanguageDetection"] = ignore
	assert shape(env, make_detector(env).add_detected_language_commands(["中1"])) == expected


def test_mode_one_symbol_speaks_its_replacement_in_its_language(env):
	symbols = SimpleNamespace(symbols={"€": SimpleNamespace(replacement="euro", language="de", mode=1)})
	languages = ("en_US", "zh_TW", "ja", "de_DE")
	result = make_detector(env, languages, symbols=symbols).add_detected_language_commands(["€x"])
	assert shape(env, result) == [("lang", "de"), "eurox"]


def test_language_commands_reset_the_base_language(env):
	ja, back = LangChangeCommand("ja"), LangChangeCommand(None)
	result = list(make_detector(env).add_detected_language_commands([ja, "中", back, "中"]))
	assert result[0] is ja and result[2] is back
	assert shape(env, result) == [("lang", "ja"), "中", ("lang", None), ("lang", "zh"), "中"]


def test_other_commands_pass_through_as_themselves(env):
	marker = object()
	assert list(make_detector(env).add_detected_language_commands([marker])) == [marker]


def test_spelling_without_locale_uses_the_synth_language(env):
	result = list(make_detector(env).process_for_spelling("a中 1"))
	assert result == [("a", "en_US"), ("中", "zh"), (" 1", "en_US")]


def test_spelling_with_locale(env):
	result = list(make_detector(env).process_for_spelling("a中 1", "ja"))
	assert result == [("a", "en"), ("中 1", "ja")]


@pytest.mark.parametrize("configured,expected", [("zh", "zh"), ("ja", "ja"), ("ko", "zh")])
def test_configured_script_language_wins_only_when_available(env, configured, expected):
	switching(env)["CJKCharactersLanguage"] = configured
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


def test_one_settings_read_per_sequence(env):
	switching(env)["ignoreNumbersInLanguageDetection"] = True
	counting = CountingSettings(env.settings)
	detector = env.module.LanguageDetector(
		["en_US", "zh_TW", "ar"],
		None,
		settings=counting,
		language=lambda: env.state.language,
	)
	result = detector.add_detected_language_commands(["中1中1 abc عربي 2"])
	assert shape(env, result) == [
		("lang", "zh"),
		"中1中1 ",
		("lang", "en_US"),
		"abc ",
		("lang", "ar"),
		"عربي 2",
	]
	assert counting.reads == 1


def test_one_settings_read_per_spelling(env):
	counting = CountingSettings(env.settings)
	detector = env.module.LanguageDetector(
		["en_US", "zh_TW", "ar"],
		None,
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
	["hello", " ", "中文", "日本語", "عربي", "123", ",", "é", "\U0001f600", "\n"],
)


# The detector is stateless between calls, so one function-scoped env serves every example.
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
	items=st.lists(
		st.one_of(
			st.lists(st.one_of(SCRIPT_SAMPLES, st.characters()), max_size=12).map("".join),
			st.sampled_from(["zh_TW", "ar", None, "fr"]).map(LangChangeCommand),
			st.builds(object),
		),
		max_size=8,
	),
	ignore_numbers=st.booleans(),
)
def test_property_detection_only_inserts_language_changes(env, items, ignore_numbers):
	switching(env)["ignoreNumbersInLanguageDetection"] = ignore_numbers
	result = list(
		make_detector(env, languages=("en_US", "zh_TW", "ja", "ar")).add_detected_language_commands(items),
	)
	assert all(item != "" for item in result), "an empty text was yielded"
	given = [item for item in items if not isinstance(item, str)]
	added = [item for item in result if not isinstance(item, str) and all(item is not c for c in given)]
	assert all(isinstance(item, env.WV) for item in added)
	# Without what detection added, the sequence is the input: same text, commands in place.
	kept = [item for item in result if isinstance(item, str) or any(item is c for c in given)]
	assert merge_texts(kept) == merge_texts(items)


def merge_texts(sequence):
	"""Join adjacent texts and drop empty ones, keeping commands where they are."""
	merged = []
	for item in sequence:
		if isinstance(item, str) and merged and isinstance(merged[-1], str):
			merged[-1] += item
		else:
			merged.append(item)
	return [item for item in merged if item != ""]
