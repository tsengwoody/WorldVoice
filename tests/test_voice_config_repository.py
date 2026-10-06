import builtins

import pytest
from runtime_harness import load_config_repository, make_spec

DEFAULTS = {
	"rate": 50,
	"pitch": 50,
	"volume": 50,
	"variant": "default",
	"inflection": 50,
	"rateBoost": False,
}


@pytest.fixture
def conf():
	return {
		"WorldVoice": {
			"voices": {},
			"autoLanguageSwitching": {"KeepMainLocaleParameterConsistent": False},
		},
		"speech": {"WorldVoice": {"rate": "83", "variant": "main", "rateBoost": "True"}},
	}


@pytest.fixture
def repository(monkeypatch, rt, conf):
	module = load_config_repository(monkeypatch, rt)
	return module.ConfigVoiceSettingsRepository(conf)


def test_load_converts_existing_values_and_defaults_missing_fields(repository, conf):
	conf["WorldVoice"]["voices"]["Fake:a"] = {
		"rate": "72",
		"pitch": "63",
		"volume": "84",
		"inflection": "35",
		"variant": "bright",
		"rateBoost": "False",
		"waitfactor": 9,
	}
	values = repository.load(make_spec())
	assert values == {
		"rate": 72,
		"pitch": 63,
		"volume": 84,
		"inflection": 35,
		"variant": "bright",
		"rateBoost": False,
	}
	conf["WorldVoice"]["voices"]["Fake:a"] = {"rate": "72", "pitch": None}
	assert repository.load(make_spec()) == dict(DEFAULTS, rate=72)


def test_save_converts_six_values_and_does_not_add_waitfactor(repository, conf):
	repository.save(make_spec(), dict(DEFAULTS, rate="72", variant=42, rateBoost="False", waitfactor=8))
	assert conf["WorldVoice"]["voices"]["Fake:a"] == dict(DEFAULTS, rate=72, variant="42")


def test_save_preserves_unrelated_config_values(repository, conf):
	conf["WorldVoice"]["voices"]["Fake:a"] = {"other": "retain", "waitfactor": 9}
	repository.save(make_spec(), dict(DEFAULTS, rate=72, waitfactor=8))
	assert conf["WorldVoice"]["voices"]["Fake:a"] == dict(DEFAULTS, rate=72, other="retain", waitfactor=9)


def test_repository_load_and_save_need_no_nvda_or_engine_imports(monkeypatch, rt, conf):
	original_import = builtins.__import__

	def guarded_import(name, *args, **kwargs):
		if (
			name in {"config", "synthDriverHandler", "logHandler"}
			or "driver" in name.lower()
			or "session" in name.lower()
		):
			raise AssertionError(f"Unexpected dependency: {name}")
		return original_import(name, *args, **kwargs)

	monkeypatch.setattr(builtins, "__import__", guarded_import)
	repository = load_config_repository(monkeypatch, rt).ConfigVoiceSettingsRepository(conf)
	values = repository.load(make_spec())
	repository.save(make_spec(), values)
	assert conf["WorldVoice"]["voices"]["Fake:a"] == DEFAULTS


def test_missing_voice_persists_and_loads_the_six_defaults(repository, conf):
	assert repository.load(make_spec()) == DEFAULTS
	assert conf["WorldVoice"]["voices"]["Fake:a"] == DEFAULTS


def test_voices_load_their_own_values_whatever_the_main_synth_has(repository, conf):
	# Following the main voice is ParameterConsistency's job, through the settings store.
	conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"] = True
	conf["WorldVoice"]["voices"]["Fake:a"] = {"rate": "72", "variant": "bright"}
	assert repository.load(make_spec()) == dict(DEFAULTS, rate=72, variant="bright")
