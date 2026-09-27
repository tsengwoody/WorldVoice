"""Conservative opt-in policy and resource-bound adapter configuration."""

import importlib
from types import SimpleNamespace

import pytest

from test_worldvoice_lifecycle import _load_voice_manager, _load_synth_class


@pytest.fixture
def env(monkeypatch):
    module = _load_voice_manager(monkeypatch, {})
    models = importlib.import_module(module.__package__ + ".runtime.models")
    adapter = importlib.import_module(module.__package__ + ".compat.engineAdapter")
    return SimpleNamespace(module=module, models=models, adapter=adapter)


@pytest.mark.parametrize("version", ["unknown", "2026.1", "2026.1.1", "2026.2"])
@pytest.mark.parametrize("engine,audio", [
    ("OneCore", "default"), ("SAPI5", "wasapi"), ("SAPI5", "legacy"),
    ("VE", "default"), ("Cerence", "default"), ("RHVoice", "default"),
    ("Espeak", "default"), ("external-test-engine", "default"),
    ("unknown", "default"),
    *[(engine, "unknown") for engine in (
        "OneCore", "SAPI5", "VE", "Cerence", "RHVoice", "Espeak",
        "external-test-engine", "unknown")],
])
def test_unverified_profiles_always_use_legacy_done(env, engine, version, audio):
    path = env.module.__package__ + ".compat.completionPolicies"
    assert importlib.util.find_spec(path) is not None, "Completion policies have not been implemented"
    policies = importlib.import_module(path)
    contract = policies.get_completion_contract(engine, nvda_version=version, audio_mode=audio)
    assert contract.mode is env.models.CompletionMode.LEGACY_DONE
    assert contract.index_range is None


@pytest.mark.parametrize("minimum,maximum", [(0, 10), (5, 4), (-10, -1)])
def test_invalid_range_is_rejected(env, minimum, maximum):
    with pytest.raises(ValueError):
        env.models.IndexRange(minimum, maximum)


def make_adapter(env):
    class Voice:
        core = None
        @classmethod
        def engineOn(cls):
            cls.core = SimpleNamespace(speak=lambda commands: None)
        @classmethod
        def supportedSettings(cls):
            return ()
    return env.adapter.LegacyEngineAdapter(Voice, lambda key: None)


def test_configure_requires_open_and_cannot_downgrade(env):
    adapter = make_adapter(env)
    contract = env.models.CompletionContract(env.models.CompletionMode.END_INDEX, env.models.IndexRange(1, 10))
    assert hasattr(adapter, "configure_completion"), "Resource-bound completion configuration is missing"
    with pytest.raises(RuntimeError):
        adapter.configure_completion(contract)
    adapter.open()
    adapter.configure_completion(contract)
    adapter.configure_completion(contract)
    with pytest.raises(RuntimeError):
        adapter.configure_completion(env.models.CompletionContract())
    assert adapter.capabilities.completion == contract


def test_configure_after_speech_is_rejected(env):
    adapter = make_adapter(env)
    adapter.open()
    adapter.speak(("hello",), SimpleNamespace(is_cancelled=lambda: False))
    assert hasattr(adapter, "configure_completion"), "Resource-bound completion configuration is missing"
    with pytest.raises(RuntimeError):
        adapter.configure_completion(env.models.CompletionContract())


@pytest.mark.parametrize("engine,use_wasapi,expected", [
    ("SAPI5", True, "wasapi"), ("SAPI5", False, "legacy"), ("OneCore", True, "default"),
    ("SAPI5", None, "unknown"),
])
def test_synth_policy_uses_actual_opened_core(env, engine, use_wasapi, expected):
    selected = []
    commands = {name: type(name, (), {}) for name in (
        "IndexCommand", "CharacterModeCommand", "LangChangeCommand", "BreakCommand",
        "PitchCommand", "RateCommand", "VolumeCommand")}
    def policy(engine, **kwargs):
        selected.append((engine, kwargs))
        return env.models.CompletionContract()
    root = _load_synth_class({"SynthDriver": object, "synthIndexReached": object(),
        "synthDoneSpeaking": object(), "versionInfo": SimpleNamespace(version="2026.1"),
        "get_completion_contract": policy, **commands})
    synth = object.__new__(root)
    assert hasattr(synth, "_completion_for"), "Runtime completion policy selection is missing"
    core = SimpleNamespace() if use_wasapi is None else SimpleNamespace(useWasapi=use_wasapi)
    synth._completion_for(SimpleNamespace(engine=engine), core)
    assert selected == [(engine, {"nvda_version": "2026.1", "audio_mode": expected})]
