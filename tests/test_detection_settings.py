"""The language detection settings service: the only reader and writer of its six keys."""

from types import SimpleNamespace

import pytest
from addon_loader import WORLDVOICE, alias_package, load_source
from nvda_stubs import StubModules, _confspec_default, worldvoice_conf

SETTINGS = WORLDVOICE / "languageDetection/settings.py"
SCRIPT_LANGUAGES = WORLDVOICE / "languageDetection/scriptLanguages.py"
PACKAGE = "detection_settings_under_test"
DETECTION = PACKAGE + ".languageDetection"


class RecordingSection(dict):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.writes = []

	def __setitem__(self, key, value):
		self.writes.append(key)
		super().__setitem__(key, value)


def load_settings_module(monkeypatch, conf=None, errors=None, *, table=None):
	"""settings.py in an alias of its package, so it loads alone: not the detector (detector.py),
	nor the package's __init__.py, which stays empty, nor the rest of the synth package.

	table, given the script table module, returns the DETECTION_SCRIPTS the settings derive from.
	"""
	stubs = StubModules(monkeypatch)
	stubs.module("config", conf=conf if conf is not None else {})
	stubs.module(
		"logHandler",
		log=SimpleNamespace(
			error=lambda *args, **kwargs: (errors if errors is not None else []).append(args),
		),
	)
	# The synth package's alias holds the listener list the settings import from it.
	alias_package(monkeypatch, PACKAGE)
	load_source(monkeypatch, PACKAGE + ".listeners", WORLDVOICE / "listeners.py")
	alias_package(monkeypatch, DETECTION, WORLDVOICE / "languageDetection")
	script_languages = load_source(monkeypatch, DETECTION + ".scriptLanguages", SCRIPT_LANGUAGES)
	if table is not None:
		monkeypatch.setattr(script_languages, "DETECTION_SCRIPTS", table(script_languages))
	return load_source(monkeypatch, DETECTION + ".settings", SETTINGS)


@pytest.fixture
def env(monkeypatch):
	section = RecordingSection(
		latinCharactersLanguage="en",
		cjkCharactersLanguage="ja",
		arabicCharactersLanguage="ar",
		cyrillicCharactersLanguage="ru",
		devanagariCharactersLanguage="hi",
		detectLanguageTiming="after",
		keepMainLocaleVoiceConsistent=True,
	)
	conf = {"WorldVoice": {"autoLanguageSwitching": section}}
	errors = []
	module = load_settings_module(monkeypatch, conf, errors)
	service = module.DetectionSettingsService(lambda: conf)
	return SimpleNamespace(module=module, section=section, service=service, errors=errors)


ALL_SCRIPTS = {"Latin": "en", "Han": "ja", "Arabic": "ar", "Cyrillic": "ru", "Devanagari": "hi"}


def test_get_reads_the_six_detection_keys(env):
	settings = env.service.get()
	assert dict(settings.script_language) == ALL_SCRIPTS
	assert settings.timing == "after"


def test_script_languages_are_read_only(env):
	with pytest.raises(TypeError):
		env.service.get().script_language["Han"] = "zh"


def test_get_follows_the_current_config(env):
	env.section["detectLanguageTiming"] = "before"
	assert env.service.get().timing == "before"


def test_update_writes_only_the_given_changed_keys(env):
	settings = env.service.update(script_language={"Han": "zh"})
	assert env.section.writes == ["cjkCharactersLanguage"]
	assert settings.script_language["Han"] == "zh"
	assert (env.section["latinCharactersLanguage"], env.section["arabicCharactersLanguage"]) == ("en", "ar")


def test_update_with_stored_values_writes_and_notifies_nothing(env):
	seen = []
	env.service.subscribe(lambda settings, changed: seen.append(changed))
	settings = env.service.update(
		script_language=ALL_SCRIPTS,
		timing="after",
	)
	assert env.section.writes == [] and seen == []
	assert settings == env.service.get()


def test_unknown_script_is_rejected_before_any_write(env):
	with pytest.raises(KeyError):
		env.service.update(timing="before", script_language={"Klingon": "tlh"})
	assert env.section.writes == []


def test_listeners_learn_which_fields_changed(env):
	seen = []
	env.service.subscribe(lambda settings, changed: seen.append((settings.timing, changed)))
	env.service.update(timing="before")
	env.service.update(script_language={"Latin": "fr"}, timing="before")
	assert seen == [
		("before", frozenset({"timing"})),
		("before", frozenset({"script_language"})),
	]


def test_a_failing_listener_is_logged_and_the_others_still_run(env):
	seen = []

	def failing(settings, changed):
		raise RuntimeError("listener failed")

	def record(settings, changed):
		seen.append(changed)

	env.service.subscribe(failing)
	env.service.subscribe(record)
	env.service.subscribe(record)
	# A failing listener loses no update: the value is stored and returned.
	assert env.service.update(timing="before").timing == "before"
	assert env.section["detectLanguageTiming"] == "before"
	env.service.unsubscribe(record)
	env.service.unsubscribe(record)
	env.service.update(timing="after")
	assert seen == [frozenset({"timing"})]
	assert env.errors == [("WorldVoice: detection settings listener failed",)] * 2


def test_confspec_and_script_keys_keep_the_stored_names_and_defaults(env):
	assert env.module.DETECTION_CONFSPEC == {
		"latinCharactersLanguage": "string(default=en)",
		"cjkCharactersLanguage": "string(default=ja)",
		"arabicCharactersLanguage": "string(default=ar)",
		# The first candidates of their scripts: what the detector took before the choice existed.
		"cyrillicCharactersLanguage": "string(default=ru)",
		"devanagariCharactersLanguage": "string(default=hi)",
		"detectLanguageTiming": "string(default=after)",
	}
	assert env.module.SCRIPT_CONFIG_KEYS == {
		"Latin": "latinCharactersLanguage",
		"Han": "cjkCharactersLanguage",
		"Arabic": "arabicCharactersLanguage",
		"Cyrillic": "cyrillicCharactersLanguage",
		"Devanagari": "devanagariCharactersLanguage",
	}


def test_detection_confspec_and_keys_derive_from_the_table(monkeypatch):
	# A script added to the table gets its config key, default and script key, before the timing.
	def with_hebrew(script_languages):
		hebrew = script_languages.DetectionScript("Hebrew", "hebrewCharactersLanguage", "he")
		return (*script_languages.DETECTION_SCRIPTS, hebrew)

	module = load_settings_module(monkeypatch, table=with_hebrew)
	table = with_hebrew(load_source(monkeypatch, "detection_table_under_test", SCRIPT_LANGUAGES))
	assert list(module.DETECTION_CONFSPEC) == [*(row.config_key for row in table), "detectLanguageTiming"]
	assert module.DETECTION_CONFSPEC["hebrewCharactersLanguage"] == "string(default=he)"
	assert list(module.SCRIPT_CONFIG_KEYS) == [row.script for row in table]
	assert module.SCRIPT_CONFIG_KEYS["Hebrew"] == "hebrewCharactersLanguage"


def test_the_config_stub_reads_the_detection_defaults_from_the_table(monkeypatch):
	# Every test that builds a fresh profile with worldvoice_conf gets exactly the keys and defaults
	# of the real DETECTION_CONFSPEC: no key NVDA lacks, none missing.
	module = load_settings_module(monkeypatch)
	switching = worldvoice_conf()["WorldVoice"]["autoLanguageSwitching"]
	assert {key: switching[key] for key in module.DETECTION_CONFSPEC} == {
		key: _confspec_default(validator) for key, validator in module.DETECTION_CONFSPEC.items()
	}
	assert set(switching) - set(module.DETECTION_CONFSPEC) == {
		"keepMainLocaleVoiceConsistent",
		"keepMainLocaleParameterConsistent",
		"keepMainLocaleEngineConsistent",
	}


def test_the_shared_service_reads_nvda_config(monkeypatch):
	conf = {
		"WorldVoice": {
			"autoLanguageSwitching": {
				"latinCharactersLanguage": "fr",
				"cjkCharactersLanguage": "zh",
				"arabicCharactersLanguage": "fa",
				"cyrillicCharactersLanguage": "bg",
				"devanagariCharactersLanguage": "ne",
				"detectLanguageTiming": "before",
			},
		},
	}
	module = load_settings_module(monkeypatch, conf)
	script_language = module.detection_settings.get().script_language
	assert (script_language["Arabic"], script_language["Cyrillic"], script_language["Devanagari"]) == (
		"fa",
		"bg",
		"ne",
	)
