import builtins

import pytest

from runtime_harness import load_config_repository, make_spec, rt


DEFAULTS = {
    "rate": 50, "pitch": 50, "volume": 50, "variant": "default",
    "inflection": 50, "rateBoost": False,
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
    return module.ConfigVoiceSettingsRepository(conf, "WorldVoice")


def test_load_converts_existing_values_and_defaults_missing_fields(repository, conf):
    conf["WorldVoice"]["voices"]["Fake:a"] = {
        "rate": "72", "pitch": "63", "volume": "84", "inflection": "35",
        "variant": "bright", "rateBoost": "False", "waitfactor": 9,
    }
    values = repository.load(make_spec())
    assert values == {"rate": 72, "pitch": 63, "volume": 84, "inflection": 35,
                      "variant": "bright", "rateBoost": False}
    conf["WorldVoice"]["voices"]["Fake:a"] = {"rate": "72", "pitch": None}
    assert repository.load(make_spec()) == dict(DEFAULTS, rate=72)


def test_missing_voice_persists_six_defaults_but_loads_effective_main_values(repository, conf):
    conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"] = True
    assert repository.load(make_spec()) == dict(DEFAULTS, rate=83, variant="main", rateBoost=True)
    assert conf["WorldVoice"]["voices"]["Fake:a"] == DEFAULTS


def test_consistency_uses_main_synth_and_does_not_fallback_for_missing_main_fields(repository, conf):
    conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"] = True
    conf["WorldVoice"]["voices"]["Fake:a"] = {"rate": "72", "pitch": "91"}
    assert repository.load(make_spec()) == dict(DEFAULTS, rate=83, variant="main", rateBoost=True)


def test_voices_keep_their_own_values_until_the_main_settings_are_ready(monkeypatch, rt, conf):
    conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"] = True
    conf["WorldVoice"]["voices"]["Fake:a"] = {
        "rate": "72", "variant": "own", "inflection": "35", "rateBoost": "False",
    }
    ready = [False]
    repository = load_config_repository(monkeypatch, rt).ConfigVoiceSettingsRepository(
        conf, "WorldVoice", main_settings_ready=lambda: ready[0])
    assert repository.load(make_spec()) == dict(DEFAULTS, rate=72, variant="own", inflection=35)
    ready[0] = True
    assert repository.load(make_spec()) == dict(DEFAULTS, rate=83, variant="main", rateBoost=True)


def test_missing_speech_node_falls_back_to_voice(repository, conf):
    conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"] = True
    conf["WorldVoice"]["voices"]["Fake:a"] = {"rate": "72"}
    conf["speech"].clear()
    assert repository.load(make_spec())["rate"] == 72


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
        if name in {"config", "synthDriverHandler", "logHandler"} or "driver" in name.lower() or "session" in name.lower():
            raise AssertionError(f"Unexpected dependency: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    repository = load_config_repository(monkeypatch, rt).ConfigVoiceSettingsRepository(conf, "WorldVoice")
    values = repository.load(make_spec())
    repository.save(make_spec(), values)
    assert conf["WorldVoice"]["voices"]["Fake:a"] == DEFAULTS


def test_invalid_main_value_falls_back_to_the_voice_for_that_key_only(repository, conf):
    class Section(dict):
        def get(self, key, default=None):
            if key == "rate":
                raise ValueError("invalid rate in nvda.ini")
            return super().get(key, default)

    conf["speech"]["WorldVoice"] = Section(pitch="61")
    conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"] = True
    conf["WorldVoice"]["voices"]["Fake:a"] = {"rate": "72", "pitch": "30"}
    assert repository.load(make_spec()) == dict(DEFAULTS, rate=72, pitch=61)
