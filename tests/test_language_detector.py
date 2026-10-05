"""Language detection: which language each run of text is spoken in."""

from types import SimpleNamespace

import pytest

from detector_harness import LangChangeCommand, load_language_detection



@pytest.fixture
def env(stub_modules, monkeypatch):
	return load_language_detection(stub_modules, monkeypatch)


def make_detector(env, languages=("en_US", "zh_TW", "ja"), symbols=None):
	"""The one place the detector is built; its dependencies come from env."""
	return env.module.LanguageDetector(
		list(languages), symbols, settings=env.settings, language=lambda: env.state.language,
	)


def shape(env, sequence):
	return [("lang", item.lang) if isinstance(item, (env.WV, LangChangeCommand)) else item for item in sequence]


def switching(env):
	return env.conf["WorldVoice"]["autoLanguageSwitching"]


def test_mixed_scripts_switch_at_script_boundaries(env):
	result = make_detector(env).add_detected_language_commands(["hello 中文 ok"])
	assert shape(env, result) == ["hello ", ("lang", "zh"), "中文 ", ("lang", "en"), "ok"]


@pytest.mark.parametrize("ignore,expected", [
	(False, [("lang", "zh"), "中", ("lang", "en_US"), "1"]),
	(True, [("lang", "zh"), "中1"]),
])
def test_digits_follow_the_ignore_numbers_setting(env, ignore, expected):
	switching(env)["ignoreNumbersInLanguageDetection"] = ignore
	assert shape(env, make_detector(env).add_detected_language_commands(["中1"])) == expected


def test_mode_one_symbol_speaks_its_replacement_in_its_language(env):
	symbols = SimpleNamespace(symbols={"€": SimpleNamespace(replacement="euro", language="de", mode=1)})
	result = make_detector(env, symbols=symbols).add_detected_language_commands(["€x"])
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
	assert result == [("a", "en"), ("中", "zh"), (" 1", "ja")]


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
		["en_US", "zh_TW", "ar"], None, settings=counting, language=lambda: env.state.language,
	)
	result = detector.add_detected_language_commands(["中1中1 abc عربي 2"])
	assert shape(env, result) == [("lang", "zh"), "中1中1 ", ("lang", "en"), "abc ", ("lang", "ar"), "عربي 2"]
	assert counting.reads == 1


def test_one_settings_read_per_spelling(env):
	counting = CountingSettings(env.settings)
	detector = env.module.LanguageDetector(
		["en_US", "zh_TW", "ar"], None, settings=counting, language=lambda: env.state.language,
	)
	assert list(detector.process_for_spelling("中a中a")) == [("中", "zh"), ("a", "en_US"), ("中", "zh"), ("a", "en_US")]
	assert counting.reads == 1
