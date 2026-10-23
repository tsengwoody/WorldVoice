"""Language detection: which language each run of text is spoken in."""

from itertools import pairwise
from types import SimpleNamespace

import pytest
from detector_harness import LangChangeCommand, load_language_detection
from hypothesis import HealthCheck, example, given, settings, strategies as st


@pytest.fixture
def env(stub_modules, monkeypatch):
	return load_language_detection(stub_modules, monkeypatch)


def make_detector(env, languages=("en_US", "zh_TW", "ja"), number_language=None):
	"""The one place the detector is built; its dependencies come from env. Without a number language
	the detector's own default applies (digits follow the text)."""
	providers = {} if number_language is None else {"number_language": lambda: number_language}
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
	"cjk": "CJKCharactersLanguage",
	"latin": "latinCharactersLanguage",
	"arabic": "arabicCharactersLanguage",
}


def detect(env, sequence, *, languages, base, **preferences):
	"""Detect with the given installed languages, synth language and detection preferences."""
	env.state.language = base
	for name, value in preferences.items():
		switching(env)[PREFERENCE_KEYS[name]] = value
	return shape(env, make_detector(env, languages=languages).add_detected_language_commands(sequence))


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
			{},
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
		pytest.param(
			("en_US", "zh_TW"),
			"en_US",
			{},
			[L("de_DE"), "hallo 12"],
			[("lang", "de_DE"), ("lang", "en"), "hallo 12"],
			id="digits-stay-in-the-run",
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


def test_script_without_an_installed_language_keeps_the_current_language(env):
	# No Greek voice: the Greek stays in the zh run instead of returning to the base.
	assert detect(env, ["中Ελλ"], languages=("en_US", "zh_TW"), base="en_US") == [("lang", "zh"), "中Ελλ"]
	detector = make_detector(env, ("en_US", "zh_TW"))
	assert list(detector.process_for_spelling("中Ελ", "en_US")) == [("中Ελ", "zh")]


def test_spelling_with_an_unavailable_locale(env):
	result = list(make_detector(env, languages=("en_US", "zh_TW")).process_for_spelling("a b", "de_DE"))
	assert result == [("a", "en"), (" ", "de_DE"), ("b", "en")]


@pytest.mark.parametrize(
	"locale,primary",
	[
		("en_US", "en"),
		("ar-WW", "ar"),
		("ZH-tw", "zh"),
		("ja", "ja"),
		("sr-Latn-RS", "sr"),
		("zh_Hant_TW", "zh"),
	],
)
def test_primary_language_is_the_first_subtag(env, locale, primary):
	assert env.module.get_primary_language(locale) == primary


def test_mixed_scripts_switch_at_script_boundaries(env):
	result = make_detector(env).add_detected_language_commands(["hello 中文 ok"])
	assert shape(env, result) == ["hello ", ("lang", "zh"), "中文 ", ("lang", "en_US"), "ok"]


@pytest.mark.parametrize("stored", [False, True], ids=["stored-off", "stored-on"])
def test_digits_follow_the_current_language_whatever_is_stored(env, stored):
	# The old "ignore numbers" key is never read again (phase 35 goal 2).
	switching(env)["ignoreNumbersInLanguageDetection"] = stored
	assert shape(env, make_detector(env).add_detected_language_commands(["中1"])) == [("lang", "zh"), "中1"]


# Decimal digits of any script are not letters: many are not Common script (Arabic-Indic digits are
# Arabic), so without their own rule they would switch the voice (phase 35 spec §6.3, F4).
@pytest.mark.parametrize(
	("sequence", "expected"),
	[
		(["abc ١٢٣"], ["abc ١٢٣"]),
		(["مرحبا ١٢٣"], [("lang", "ar"), "مرحبا ١٢٣"]),
		(["中１２３"], [("lang", "zh"), "中１２３"]),
	],
	ids=["abc-arabic-indic", "arabic-arabic-indic", "han-full-width"],
)
def test_decimal_digits_never_switch_the_language(env, sequence, expected):
	detector = make_detector(env, ("en_US", "zh_TW", "ar"))
	assert shape(env, detector.add_detected_language_commands(sequence)) == expected


def test_superscripts_are_not_digits(env):
	# "²" is not a decimal digit (spec §6.1): it is Common script and stays in the run.
	assert shape(env, make_detector(env).add_detected_language_commands(["中²"])) == [("lang", "zh"), "中²"]


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


@pytest.mark.parametrize("number_language", ["default", "main"])
def test_spelling_keeps_arabic_indic_digits_in_a_latin_run(env, number_language):
	detector = make_detector(env, ("en_US", "ar"), number_language)
	assert list(detector.process_for_spelling("abc١٢", "en_US")) == [("abc١٢", "en_US")]


# The speech symbols are gone (phase 33 spec §1.2): an old caller fails at construction, not later.
@pytest.mark.parametrize(
	"args,kwargs",
	[pytest.param((None,), {}, id="positional"), pytest.param((), {"speechSymbols": None}, id="keyword")],
)
def test_symbols_argument_is_rejected(env, args, kwargs):
	with pytest.raises(TypeError):
		env.module.LanguageDetector(
			["en_US"],
			*args,
			settings=env.settings,
			language=lambda: env.state.language,
			**kwargs,
		)


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
	counting = CountingSettings(env.settings)
	detector = env.module.LanguageDetector(
		["en_US", "zh_TW", "ar"],
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
	+ ["漢字", "привет", "한국", "かな", "Ελληνικά", "12", "，"]
	# Phase 35: decimal digits of other scripts, and characters that only look like digits.
	+ ["١٢", "１２", "²", "①"],
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
	"el_GR",
)
# Document languages: none, without a voice, hyphenated, a regional variant, primary only, unknown.
COMMAND_LANGUAGES = (None, "de_DE", "ar-WW", "zh_TW", "en_GB", "ja", "fr", "xx_YY")
ITEMS = st.lists(
	st.one_of(TEXTS, st.sampled_from(COMMAND_LANGUAGES).map(LangChangeCommand), st.builds(object)),
	max_size=8,
)


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
		},
		locale=draw(st.one_of(st.none(), st.sampled_from(COMMAND_LANGUAGES[1:] + tuple(installed)))),
	)


def scenario_detector(env, scenario):
	env.state.language = scenario.base
	for name, value in scenario.preferences.items():
		switching(env)[PREFERENCE_KEYS[name]] = value
	return make_detector(env, scenario.installed)


def is_letter(env, character):
	return not character.isdecimal() and env.module.get_script(ord(character)) not in (
		None,
		"Common",
		"Inherited",
	)


def covers(env, scenario, language, script):
	"""The phase 33 rule, written out: a language of the script with an installed voice."""
	primary = env.module.get_primary_language(language)
	installed = {env.module.get_primary_language(voice) for voice in scenario.installed}
	return primary in env.module.SCRIPT_LANGUAGES.get(script, ()) and primary in installed


def spoken_letters(env, scenario, items, result):
	"""Each letter of the output: its script, the language in effect, the base, and the language of
	the command detection inserted right before it (None if there is none)."""
	given = [item for item in items if not isinstance(item, str)]
	base = language = scenario.base
	inserted = None
	for item in result:
		if isinstance(item, str):
			for character in item:
				if is_letter(env, character):
					yield env.module.get_script(ord(character)), language, base, inserted
				inserted = None
		elif not any(item is command for command in given):
			language = inserted = item.lang
		elif isinstance(item, LangChangeCommand):
			base = language = item.lang or scenario.base


# The detector is stateless between calls, so one function-scoped env serves every example.
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(scenario=scenarios(), items=ITEMS)
def test_property_detection_only_inserts_language_changes(env, scenario, items):
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
	preferences = {"cjk": "ja", "latin": "en", "arabic": "ar"}
	return SimpleNamespace(installed=list(installed), base=base, preferences=preferences, locale=None)


# Random draws find these cases in most runs, not all; the examples make every run check them.
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(scenario=scenarios(), items=ITEMS)
@example(scenario=plain_scenario(("en_US", "zh_TW"), "en_US"), items=[L("de_DE"), "hallo"])
def test_property_letters_go_to_installed_languages(env, scenario, items):
	result = list(scenario_detector(env, scenario).add_detected_language_commands(items))
	installed = {env.module.get_primary_language(voice) for voice in scenario.installed}
	for script, language, _base, inserted in spoken_letters(env, scenario, items, result):
		if inserted is not None:
			assert env.module.get_primary_language(inserted) in installed
		if any(candidate in installed for candidate in env.module.SCRIPT_LANGUAGES.get(script, ())):
			# Some installed language covers the script, so the letter is spoken in one of them.
			assert covers(env, scenario, language, script)


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(scenario=scenarios(), items=ITEMS)
@example(scenario=plain_scenario(("en_US", "zh_TW"), "en_US"), items=["中文hello"])
def test_property_inserted_commands_prefer_a_covering_base(env, scenario, items):
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
	primary = env.module.get_primary_language
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


# Phase 35 spec §11.4 item 4: digits never start a run that detection opens.
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(scenario=scenarios(), items=ITEMS)
def test_property_digits_never_start_a_detected_run(env, scenario, items):
	result = list(scenario_detector(env, scenario).add_detected_language_commands(items))
	given = [item for item in items if not isinstance(item, str)]
	for command, following in pairwise(result):
		inserted = isinstance(command, env.WV) and all(command is not item for item in given)
		if inserted and isinstance(following, str):
			assert not following[0].isdecimal(), (items, result)


SPELLING_NUMBER_LANGUAGES = ("default", "main", "en", "zh_TW", "fr")


# Phase 35 spec §11.4 item 6: every digit is spelled in the language spec §5 names.
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(scenario=scenarios(), text=TEXTS, number_language=st.sampled_from(SPELLING_NUMBER_LANGUAGES))
def test_property_spelling_digits_carry_the_number_language(env, scenario, text, number_language):
	detector = scenario_detector(env, scenario)
	detector._number_language = lambda: number_language
	runs = list(detector.process_for_spelling(text, scenario.locale))
	primary = env.module.get_primary_language
	base = scenario.locale if scenario.locale is not None else scenario.base
	installed = {primary(voice) for voice in scenario.installed}
	for index, (part, language) in enumerate(runs):
		if not any(character.isdecimal() for character in part):
			continue
		if number_language == "default":
			# A digit follows the run it is in, so it never opens one.
			assert index == 0 or not part[0].isdecimal(), (text, runs)
		elif number_language == "main" or primary(number_language) not in installed:
			assert primary(language) == primary(base), (text, runs)
		else:
			assert primary(language) == primary(number_language), (text, runs)
