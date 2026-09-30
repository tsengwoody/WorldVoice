"""Test-branch completion override and resource-bound adapter configuration."""

import importlib
import sys
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
@pytest.mark.parametrize("audio", ["default", "wasapi", "legacy", "unknown"])
@pytest.mark.parametrize("engine", ["RHVoice"])
@pytest.mark.parametrize("supported", [False, True])
def test_test_branch_forces_end_index_for_remaining_engines(env, engine, version, audio, supported):
    policies = importlib.import_module(env.module.__package__ + ".compat.completionPolicies")
    contract = policies.get_completion_contract(engine, nvda_version=version, audio_mode=audio,
                                                segment_drain_supported=supported)
    assert contract.mode is env.models.CompletionMode.END_INDEX
    assert contract.index_range == env.models.IndexRange(1, 9999)


@pytest.mark.parametrize("version", ["unknown", "2026.1", "2026.1.1", "2026.2"])
@pytest.mark.parametrize("audio", ["default", "wasapi", "legacy", "unknown"])
@pytest.mark.parametrize("engine", ["external-test-engine", "unknown"])
@pytest.mark.parametrize("supported", [False, True])
def test_unknown_and_external_profiles_still_use_legacy_done(env, engine, version, audio, supported):
    path = env.module.__package__ + ".compat.completionPolicies"
    assert importlib.util.find_spec(path) is not None, "Completion policies have not been implemented"
    policies = importlib.import_module(path)
    contract = policies.get_completion_contract(engine, nvda_version=version, audio_mode=audio,
                                                segment_drain_supported=supported)
    assert contract.mode is env.models.CompletionMode.LEGACY_DONE
    assert contract.index_range is None


@pytest.mark.parametrize("engine", ["OneCore", "Neural", "VE", "Cerence", "SAPI5", "Espeak"])
@pytest.mark.parametrize("version,audio", [("2026.1", "default"), ("synthetic", "synthetic")])
def test_target_without_drain_support_never_uses_test_index_override(env, engine, version, audio):
    policies = importlib.import_module(env.module.__package__ + ".compat.completionPolicies")
    contract = policies.get_completion_contract(engine, nvda_version=version, audio_mode=audio)
    assert contract.mode is env.models.CompletionMode.LEGACY_DONE
    assert contract.index_range is None


@pytest.mark.parametrize("engine", ["OneCore", "Neural", "VE", "Cerence", "SAPI5", "Espeak"])
def test_supported_target_uses_drain_range(env, engine):
    policies = importlib.import_module(env.module.__package__ + ".compat.completionPolicies")
    contract = policies.get_completion_contract(engine, nvda_version="synthetic", audio_mode="synthetic",
                                                segment_drain_supported=True)
    assert contract.mode is env.models.CompletionMode.DRAIN
    assert contract.index_range == env.models.IndexRange(1, 9999)
    assert policies._VERIFIED_CONTRACTS == {}


@pytest.mark.parametrize("engine,audio_mode", [
    ("SAPI5", "wasapi"), ("SAPI5", "legacy"), ("SAPI5", "unknown"),
    ("Espeak", "default"), ("Espeak", "legacy"), ("Espeak", "unknown"),
])
def test_unsupported_new_wrapper_profile_falls_back_before_speech(env, engine, audio_mode):
    policies = importlib.import_module(env.module.__package__ + ".compat.completionPolicies")
    contract = policies.get_completion_contract(engine, nvda_version="2026.1", audio_mode=audio_mode,
                                                segment_drain_supported=False)
    assert contract.mode is env.models.CompletionMode.LEGACY_DONE
    assert contract.index_range is None


@pytest.mark.parametrize("minimum,maximum", [(0, 10), (5, 4), (-10, -1)])
def test_invalid_range_is_rejected(env, minimum, maximum):
    with pytest.raises(ValueError):
        env.models.IndexRange(minimum, maximum)


@pytest.mark.parametrize("mode", ["END_INDEX", "DRAIN"])
def test_contextual_legacy_option_cannot_change_marker_completion(env, mode):
    with pytest.raises(ValueError):
        env.models.CompletionContract(getattr(env.models.CompletionMode, mode),
            env.models.IndexRange(1, 9999), legacy_contextual=True)


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
    ("SAPI5", True, "wasapi"), ("SAPI5", False, "legacy"), ("SAPI5", None, "unknown"),
    ("OneCore", True, "wasapi"), ("OneCore", False, "legacy"), ("OneCore", None, "unknown"),
    ("Espeak", None, "default"),
    ("OneCore", "true", "unknown"), ("OneCore", 1, "unknown"), ("OneCore", 0, "unknown"),
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
        "get_completion_contract": policy,
        "get_segment_drain_support": getattr(importlib.import_module(
            env.module.__package__ + ".compat.completionPolicies"), "get_segment_drain_support", None),
        "nvdaLog": SimpleNamespace(warning=lambda *args: None), **commands})
    synth = object.__new__(root)
    assert hasattr(synth, "_completion_for"), "Runtime completion policy selection is missing"
    core = SimpleNamespace() if use_wasapi is None else SimpleNamespace(useWasapi=use_wasapi)
    synth._completion_for(SimpleNamespace(engine=engine), core)
    assert selected == [(engine, {"nvda_version": "2026.1", "audio_mode": expected, "segment_drain_supported": False})]


@pytest.mark.parametrize("engine,audio_modes", [
    ("SAPI5", ("wasapi", "legacy", "unknown")),
    ("Espeak", ("default", "legacy", "unknown")),
])
def test_actual_outer_voice_and_core_keep_unverified_profiles_legacy(
        monkeypatch, tmp_path, engine, audio_modes):
    if engine == "SAPI5":
        from test_sapi5_segment_drain import load_sapi5
        installed = load_sapi5(monkeypatch)
    else:
        from espeak_drain_harness import load_espeak
        installed = load_espeak(monkeypatch, tmp_path)
    try:
        monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.compat.completionPolicies", raising=False)
        policies = importlib.import_module("synthDrivers.WorldVoice.compat.completionPolicies")
        assert sys.modules["synthDrivers.WorldVoice.driver." + engine] is installed.outer
        assert installed.outer.Voice.synth_driver_class is type(installed.driver)
        for audio_mode in audio_modes:
            support = policies.get_segment_drain_support(installed.outer.Voice, installed.driver,
                nvda_version="2026.1", audio_mode=audio_mode)
            assert support.supported is False and support.reason
            contract = policies.get_completion_contract(engine, nvda_version="2026.1",
                audio_mode=audio_mode, segment_drain_supported=support.supported)
            assert contract.mode is installed.rt.models.CompletionMode.LEGACY_DONE
        commands = {name: type(name, (), {}) for name in (
            "IndexCommand", "CharacterModeCommand", "LangChangeCommand", "BreakCommand",
            "PitchCommand", "RateCommand", "VolumeCommand")}
        root = _load_synth_class({"SynthDriver": object, "synthIndexReached": object(),
            "synthDoneSpeaking": object(), "versionInfo": SimpleNamespace(version="2026.1"),
            "get_completion_contract": policies.get_completion_contract,
            "get_segment_drain_support": policies.get_segment_drain_support,
            "nvdaLog": SimpleNamespace(warning=lambda *args: None), **commands})
        selected = object.__new__(root)._completion_for(installed.outer.Voice, installed.driver)
        assert selected.mode is installed.rt.models.CompletionMode.LEGACY_DONE
        assert selected.index_range is None
    finally:
        if engine == "SAPI5":
            installed.driver.terminate()
        else:
            from espeak_drain_harness import finish
            finish(installed)
