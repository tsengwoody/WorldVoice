"""The language detection settings service: the only reader and writer of its six keys."""

import dataclasses
from types import SimpleNamespace

import pytest
from addon_loader import WORLDVOICE, load_source
from nvda_stubs import StubModules

SETTINGS = WORLDVOICE / "languageDetection/settings.py"


class RecordingSection(dict):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.writes = []

	def __setitem__(self, key, value):
		self.writes.append(key)
		super().__setitem__(key, value)


def load_settings_module(monkeypatch, conf=None, errors=None):
	stubs = StubModules(monkeypatch)
	stubs.module("config", conf=conf if conf is not None else {})
	stubs.module(
		"logHandler",
		log=SimpleNamespace(
			error=lambda *args, **kwargs: (errors if errors is not None else []).append(args),
		),
	)
	return load_source(monkeypatch, "detection_settings_under_test", SETTINGS)


@pytest.fixture
def env(monkeypatch):
	section = RecordingSection(
		latinCharactersLanguage="en",
		CJKCharactersLanguage="ja",
		arabicCharactersLanguage="ar",
		cyrillicCharactersLanguage="ru",
		devanagariCharactersLanguage="hi",
		DetectLanguageTiming="after",
		KeepMainLocaleVoiceConsistent=True,
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
	env.section["DetectLanguageTiming"] = "before"
	assert env.service.get().timing == "before"


def test_update_writes_only_the_given_changed_keys(env):
	settings = env.service.update(script_language={"Han": "zh"})
	assert env.section.writes == ["CJKCharactersLanguage"]
	assert settings.script_language["Han"] == "zh"
	assert (env.section["latinCharactersLanguage"], env.section["arabicCharactersLanguage"]) == ("en", "ar")


@pytest.mark.parametrize(
	"script,language,key",
	[
		("Cyrillic", "uk", "cyrillicCharactersLanguage"),
		("Devanagari", "mr", "devanagariCharactersLanguage"),
	],
)
def test_update_writes_the_cyrillic_and_devanagari_keys(env, script, language, key):
	seen = []
	env.service.subscribe(lambda settings, changed: seen.append(changed))
	settings = env.service.update(script_language={script: language})
	assert env.section.writes == [key]
	assert env.section[key] == language and settings.script_language[script] == language
	assert seen == [frozenset({"script_language"})]


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
	env.service.update(timing="before")
	env.service.unsubscribe(record)
	env.service.unsubscribe(record)
	env.service.update(timing="after")
	assert seen == [frozenset({"timing"})]
	assert len(env.errors) == 2


def test_confspec_and_script_keys_keep_the_stored_names_and_defaults(env):
	assert env.module.DETECTION_CONFSPEC == {
		"latinCharactersLanguage": "string(default=en)",
		"CJKCharactersLanguage": "string(default=ja)",
		"arabicCharactersLanguage": "string(default=ar)",
		# The first candidates of their scripts: what the detector took before the choice existed.
		"cyrillicCharactersLanguage": "string(default=ru)",
		"devanagariCharactersLanguage": "string(default=hi)",
		"DetectLanguageTiming": "string(default=after)",
	}
	assert env.module.SCRIPT_CONFIG_KEYS == {
		"Latin": "latinCharactersLanguage",
		"Han": "CJKCharactersLanguage",
		"Arabic": "arabicCharactersLanguage",
		"Cyrillic": "cyrillicCharactersLanguage",
		"Devanagari": "devanagariCharactersLanguage",
	}


def test_the_shared_service_reads_nvda_config(monkeypatch):
	conf = {
		"WorldVoice": {
			"autoLanguageSwitching": {
				"latinCharactersLanguage": "fr",
				"CJKCharactersLanguage": "zh",
				"arabicCharactersLanguage": "fa",
				"cyrillicCharactersLanguage": "bg",
				"devanagariCharactersLanguage": "ne",
				"DetectLanguageTiming": "before",
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


# Phase 35 removed the "ignore numbers" option: the number language decides every digit.
def test_update_rejects_ignore_numbers(env):
	with pytest.raises(TypeError):
		env.service.update(ignore_numbers=True)
	assert env.section.writes == []


def test_get_reads_a_section_that_still_holds_the_old_key(env):
	# A profile keeps the old key until NVDA drops it; nothing reads it.
	env.section["ignoreNumbersInLanguageDetection"] = True
	settings = env.service.get()
	assert (dict(settings.script_language), settings.timing) == (
		ALL_SCRIPTS,
		"after",
	)


def test_settings_have_no_ignore_numbers_field(env):
	assert [field.name for field in dataclasses.fields(env.module.DetectionSettings)] == [
		"script_language",
		"timing",
	]
