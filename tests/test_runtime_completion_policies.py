"""Evidence-gated completion selection and resource-bound adapter configuration."""

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


def policies_of(env):
    return importlib.import_module(env.module.__package__ + ".compat.completionPolicies")


def drain_types(env):
    return importlib.import_module(env.module.__package__ + ".runtime.playbackWork")


def fake_voice(env, *, profile=True, wasapi=False, supported=True, reason="Native lifetime is unproven",
               engine="test-engine"):
    """A Voice/SynthDriver pair whose core answers the drain check as told."""
    work = drain_types(env)
    checked = []

    class SynthDriver:
        def speak_segment(self, commands, token, *, context, on_event):
            pass

        def get_segment_drain_support(self, *, nvda_version, audio_mode):
            checked.append((nvda_version, audio_mode))
            return work.DrainSupport(supported, "test-profile", reason)

    class Voice:
        synth_driver_class = SynthDriver
        drain_profile = work.DrainProfile(wasapi_dependent=wasapi) if profile else None

    Voice.engine = engine
    return SimpleNamespace(voice=Voice, driver=SynthDriver, core=SynthDriver(), checked=checked)


@pytest.mark.parametrize("version", ["unknown", "2026.1", "2026.1.1", "2026.2"])
@pytest.mark.parametrize("audio", ["default", "wasapi", "legacy", "unknown"])
@pytest.mark.parametrize("supported", [False, True])
def test_profiled_voice_uses_drain_only_with_explicit_support(env, version, audio, supported):
    pair = fake_voice(env, supported=supported)
    contract, support = policies_of(env).CompletionPolicy().contract_for(
        pair.voice, pair.core, nvda_version=version, audio_mode=audio)
    assert pair.checked == [(version, audio)]
    assert support.supported is supported
    assert contract.mode is (env.models.CompletionMode.DRAIN if supported
                             else env.models.CompletionMode.LEGACY_DONE)
    assert contract.index_range == (env.models.IndexRange(1, 9999) if supported else None)


@pytest.mark.parametrize("version", ["unknown", "2026.1", "2026.1.1", "2026.2"])
@pytest.mark.parametrize("audio", ["default", "wasapi", "legacy", "unknown"])
@pytest.mark.parametrize("engine", ["external-test-engine", "unknown"])
@pytest.mark.parametrize("supported", [False, True])
def test_voice_without_profile_still_uses_legacy_done(env, engine, version, audio, supported):
    # The core's own answer is never consulted without a declared profile.
    pair = fake_voice(env, profile=False, supported=supported, engine=engine)
    contract, support = policies_of(env).CompletionPolicy().contract_for(
        pair.voice, pair.core, nvda_version=version, audio_mode=audio)
    assert support is None and pair.checked == []
    assert contract.mode is env.models.CompletionMode.LEGACY_DONE
    assert contract.index_range is None


@pytest.mark.parametrize("wasapi", [False, True])
@pytest.mark.parametrize("version,audio", [("2026.1", "default"), ("synthetic", "synthetic")])
def test_profiled_voice_without_support_uses_legacy_done(env, wasapi, version, audio):
    pair = fake_voice(env, wasapi=wasapi, supported=False)
    contract, support = policies_of(env).CompletionPolicy().contract_for(
        pair.voice, pair.core, nvda_version=version, audio_mode=audio)
    assert support.supported is False and support.reason == "Native lifetime is unproven"
    assert contract.mode is env.models.CompletionMode.LEGACY_DONE
    assert contract.index_range is None


@pytest.mark.parametrize("wasapi", [False, True])
def test_supported_profile_uses_drain_range(env, wasapi):
    policies = policies_of(env)
    pair = fake_voice(env, wasapi=wasapi)
    contract, _ = policies.CompletionPolicy().contract_for(
        pair.voice, pair.core, nvda_version="synthetic", audio_mode="synthetic")
    assert contract.mode is env.models.CompletionMode.DRAIN
    assert contract.index_range == env.models.IndexRange(1, 9999)
    assert policies._VERIFIED_CONTRACTS == {}


@pytest.mark.parametrize("failure,reason", [
    ("wrong_core", "The opened core is not the Voice's custom outer SynthDriver"),
    ("missing_entry", "The custom core has no callable speak_segment entry"),
    ("missing_support", "The custom core has no callable get_segment_drain_support check"),
    ("support_error", "Drain support inspection failed: RuntimeError: inspection failed"),
    ("invalid_support", "The wrapper did not return an explicit DrainSupport boolean decision"),
    ("truthy_support", "The wrapper did not return an explicit DrainSupport boolean decision"),
    ("unsupported_without_reason", "The wrapper has no supported adapter/native drain profile"),
])
def test_unconfirmed_profile_falls_back_with_concrete_reason(env, failure, reason):
    work = drain_types(env)
    pair = fake_voice(env, supported=failure != "unsupported_without_reason",
                      reason="" if failure == "unsupported_without_reason" else "unused")
    core = pair.core
    if failure == "wrong_core":
        core = SimpleNamespace(speak_segment=pair.core.speak_segment,
                               get_segment_drain_support=pair.core.get_segment_drain_support)
    elif failure == "missing_entry":
        pair.driver.speak_segment = None
    elif failure == "missing_support":
        pair.driver.get_segment_drain_support = None
    elif failure == "support_error":
        def fail(self, **kwargs):
            raise RuntimeError("inspection failed")
        pair.driver.get_segment_drain_support = fail
    elif failure == "invalid_support":
        pair.driver.get_segment_drain_support = lambda self, **kwargs: SimpleNamespace(supported=True)
    elif failure == "truthy_support":
        pair.driver.get_segment_drain_support = lambda self, **kwargs: work.DrainSupport("yes", "p", "r")
    contract, support = policies_of(env).CompletionPolicy().contract_for(
        pair.voice, core, nvda_version="2026.1", audio_mode="default")
    assert support.supported is False and support.reason == reason
    assert contract.mode is env.models.CompletionMode.LEGACY_DONE


def test_drain_support_refuses_a_voice_without_profile(env):
    pair = fake_voice(env, profile=False)
    support = policies_of(env).CompletionPolicy().drain_support(
        pair.voice, pair.core, nvda_version="2026.1", audio_mode="default")
    assert support.supported is False and support.reason == "The Voice declares no drain profile"
    assert pair.checked == []


def test_disabled_force_switch_reports_the_wrapper_reason(env):
    pair = fake_voice(env, reason="DRAIN explicitly enabled; playback is unverified")
    policy = policies_of(env).CompletionPolicy(force_unverified_drain=False)
    contract, support = policy.contract_for(pair.voice, pair.core, nvda_version="2026.1", audio_mode="default")
    assert support.supported is False and support.profile == "test-profile"
    assert support.reason == ("Unverified DRAIN is disabled by force_unverified_drain: "
                              "DRAIN explicitly enabled; playback is unverified")
    assert contract.mode is env.models.CompletionMode.LEGACY_DONE
    assert policies_of(env).CompletionPolicy().force_unverified_drain is True


@pytest.mark.parametrize("minimum,maximum", [(0, 10), (5, 4), (-10, -1)])
def test_invalid_range_is_rejected(env, minimum, maximum):
    with pytest.raises(ValueError):
        env.models.IndexRange(minimum, maximum)


def make_adapter(env):
    class Voice:
        @classmethod
        def create_core(cls):
            return SimpleNamespace(speak=lambda commands: None)
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


COMMANDS = ("IndexCommand", "CharacterModeCommand", "LangChangeCommand", "BreakCommand",
            "PitchCommand", "RateCommand", "VolumeCommand")


def real_completion_selector(policies, warnings, *, policy=None, version="2026.1"):
    """The driver's selector: CompletionPolicy.select with NVDA's version and logger."""
    if policy is None:
        policy = policies.CompletionPolicy()
    policy.nvda_version = version
    policy._logger = SimpleNamespace(warning=lambda *args: warnings.append(args))
    return policy.select


@pytest.mark.parametrize("profile,use_wasapi,expected", [
    ("wasapi", True, "wasapi"), ("wasapi", False, "legacy"), ("wasapi", None, "unknown"),
    ("wasapi", "true", "unknown"), ("wasapi", 1, "unknown"), ("wasapi", 0, "unknown"),
    ("plain", True, "default"), ("plain", None, "default"),
    ("none", True, "default"),
])
def test_synth_policy_uses_actual_opened_core(env, profile, use_wasapi, expected):
    pair = fake_voice(env, profile=profile != "none", wasapi=profile == "wasapi", supported=False)
    core = pair.core
    if use_wasapi is not None:
        core.useWasapi = use_wasapi
    warnings = []
    select = real_completion_selector(policies_of(env), warnings)
    assert select(pair.voice, core).mode is env.models.CompletionMode.LEGACY_DONE
    if profile == "none":
        assert pair.checked == [] and warnings == []
    else:
        assert pair.checked == [("2026.1", expected)]
        assert len(warnings) == 1 and warnings[0][1:4] == ("test-engine", "2026.1", expected)


@pytest.mark.parametrize("engine,audio_modes", [
    ("SAPI5", (("wasapi", True), ("legacy", False), ("unknown", False))),
    ("Espeak", (("default", True), ("legacy", True), ("unknown", True))),
    ("RHVoice", (("default", True), ("wasapi", True), ("unknown", True))),
])
def test_actual_outer_voice_and_core_select_enabled_drain_profiles(
        monkeypatch, tmp_path, engine, audio_modes):
    if engine == "SAPI5":
        from test_sapi5_segment_drain import load_sapi5
        installed = load_sapi5(monkeypatch)
    elif engine == "Espeak":
        from espeak_drain_harness import load_espeak
        installed = load_espeak(monkeypatch, tmp_path)
    else:
        from rhvoice_drain_harness import load_rhvoice
        installed = load_rhvoice(monkeypatch, tmp_path)
    try:
        policies = fresh_policies(monkeypatch)
        policy = policies.CompletionPolicy()
        assert installed.outer.Voice.synth_driver_class is type(installed.driver)
        for audio_mode, expected in audio_modes:
            contract, support = policy.contract_for(installed.outer.Voice, installed.driver,
                nvda_version="2026.1", audio_mode=audio_mode)
            assert support.supported is expected and support.reason
            expected_mode = (installed.rt.models.CompletionMode.DRAIN if expected
                else installed.rt.models.CompletionMode.LEGACY_DONE)
            assert contract.mode is expected_mode
        warnings = []
        selected = real_completion_selector(policies, warnings)(installed.outer.Voice, installed.driver)
        assert selected.mode is installed.rt.models.CompletionMode.DRAIN
        assert selected.index_range is not None
        if engine == "RHVoice":
            assert warnings == []
    finally:
        if engine == "SAPI5":
            installed.driver.terminate()
        else:
            if engine == "Espeak":
                from espeak_drain_harness import finish
            else:
                from rhvoice_drain_harness import finish
            finish(installed)


def test_sapi5_legacy_first_segment_remains_legacy_done(monkeypatch):
    from test_sapi5_segment_drain import load_sapi5
    installed = load_sapi5(monkeypatch)
    try:
        installed.driver.useWasapi = False
        policies = fresh_policies(monkeypatch)
        support = policies.CompletionPolicy().drain_support(installed.outer.Voice, installed.driver,
            nvda_version="2026.1", audio_mode="legacy")
        assert support.supported is False
        contract = real_completion_selector(policies, [])(installed.outer.Voice, installed.driver)
        assert contract.mode is installed.rt.models.CompletionMode.LEGACY_DONE
        assert contract.index_range is None
        assert installed.native.calls == []
        assert installed.driver._segmentHost.current() is None
    finally:
        installed.driver.terminate()


SIX_ENGINES = ["OneCore", "VE", "Cerence", "SAPI5", "Espeak", "RHVoice"]


def load_installed_engine(monkeypatch, tmp_path, engine):
    """Open the installed outer wrapper for *engine* on its fake native boundary."""
    control = None
    if engine in ("OneCore", "VE", "Cerence"):
        from runtime_drain_integration_harness import assemble
        composition = assemble(monkeypatch, tmp_path)
        control = composition.controls[engine]
        outer = control.env.outer if engine == "OneCore" else control.env.module
        core, close = control.core, composition.close
        mode, rt = ("wasapi" if engine == "OneCore" else "default"), composition.rt
    elif engine == "SAPI5":
        from test_sapi5_segment_drain import load_sapi5
        installed = load_sapi5(monkeypatch)
        outer, core, close, mode = installed.outer, installed.driver, installed.driver.terminate, "wasapi"
        rt = installed.rt
    elif engine == "Espeak":
        from espeak_drain_harness import load_espeak, finish
        installed = load_espeak(monkeypatch, tmp_path)
        outer, core, close, mode = installed.outer, installed.driver, lambda: finish(installed), "default"
        rt = installed.rt
    else:
        from rhvoice_drain_harness import load_rhvoice, finish
        installed = load_rhvoice(monkeypatch, tmp_path)
        outer, core, close, mode = installed.outer, installed.driver, lambda: finish(installed), "default"
        rt = installed.rt
    return SimpleNamespace(outer=outer, core=core, close=close, mode=mode, control=control, rt=rt)


def fresh_policies(monkeypatch):
    monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.compat.completionPolicies", raising=False)
    return importlib.import_module("synthDrivers.WorldVoice.compat.completionPolicies")


@pytest.mark.parametrize("engine", SIX_ENGINES)
def test_six_enabled_profiles_use_shared_lifecycle(monkeypatch, tmp_path, engine):
    """The actual opened outer core must select DRAIN before any segment starts."""
    installed = load_installed_engine(monkeypatch, tmp_path, engine)
    outer, core, control = installed.outer, installed.core, installed.control
    try:
        policies = fresh_policies(monkeypatch)
        assert outer.Voice.synth_driver_class is type(core)
        assert outer.Voice.drain_profile is not None
        # The host owns the lifecycle and implements its hooks.
        host = core._segmentHost
        assert isinstance(host, outer.SegmentHost)
        assert host._lifecycle._hooks is host
        policy = policies.CompletionPolicy()
        contract, support = policy.contract_for(outer.Voice, core,
            nvda_version="2026.1", audio_mode=installed.mode)
        assert support.supported is True
        assert contract.mode is policies.CompletionMode.DRAIN
        assert contract.index_range == policies.IndexRange(1, 9999)
        if control is not None:
            assert control.session.completion.mode is installed.rt.models.CompletionMode.DRAIN
            assert control.calls == []
    finally:
        installed.close()


@pytest.mark.parametrize("engine", SIX_ENGINES)
def test_disabled_force_switch_restores_legacy_done(monkeypatch, tmp_path, engine):
    installed = load_installed_engine(monkeypatch, tmp_path, engine)
    outer, core = installed.outer, installed.core
    try:
        policies = fresh_policies(monkeypatch)
        disabled = policies.CompletionPolicy(force_unverified_drain=False)
        support = disabled.drain_support(outer.Voice, core,
            nvda_version="2026.1", audio_mode=installed.mode)
        assert support.supported is False
        assert "force_unverified_drain" in support.reason and "unverified" in support.reason
        warnings = []
        select = real_completion_selector(policies, warnings, policy=disabled)
        contract = select(outer.Voice, core)
        assert contract.mode is installed.rt.models.CompletionMode.LEGACY_DONE
        assert contract.index_range is None
        assert select(outer.Voice, core) == contract
        assert len(warnings) == 1 and "force_unverified_drain" in warnings[0][-1]
        enabled = real_completion_selector(policies, warnings)
        assert enabled(outer.Voice, core).mode is installed.rt.models.CompletionMode.DRAIN
    finally:
        installed.close()


def test_disabled_force_switch_keeps_structural_fallback_reason(monkeypatch):
    from test_sapi5_segment_drain import load_sapi5
    installed = load_sapi5(monkeypatch)
    try:
        installed.driver.useWasapi = False
        policies = fresh_policies(monkeypatch)
        disabled = policies.CompletionPolicy(force_unverified_drain=False)
        support = disabled.drain_support(installed.outer.Voice, installed.driver,
            nvda_version="2026.1", audio_mode="legacy")
        assert support.supported is False
        assert support.reason == "SAPI5 legacy audio has no owned player idle barrier"
    finally:
        installed.driver.terminate()


@pytest.mark.parametrize("engine,wasapi_dependent", [
    ("OneCore", True), ("SAPI5", True),
    ("VE", False), ("Cerence", False), ("RHVoice", False), ("Espeak", False),
])
def test_each_installed_voice_declares_its_drain_profile(engine, wasapi_dependent):
    # Read the declaration from source: loading each wrapper needs its own fakes.
    import ast
    from test_worldvoice_lifecycle import WORLDVOICE
    tree = ast.parse((WORLDVOICE / "driver" / engine / "__init__.py").read_text(encoding="utf-8"))
    voice = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Voice")
    declared = [ast.unparse(node.value) for node in voice.body
                if isinstance(node, ast.Assign) and [t.id for t in node.targets] == ["drain_profile"]]
    expected = "DrainProfile(wasapi_dependent=True)" if wasapi_dependent else "DrainProfile()"
    assert declared == [expected]


def test_select_warns_once_per_distinct_fallback_profile(env):
    policies = policies_of(env)
    warnings = []
    policy = policies.CompletionPolicy(nvda_version="2026.1",
        logger=SimpleNamespace(warning=lambda *args: warnings.append(args)))
    first = fake_voice(env, supported=False, reason="reason a", engine="Fake")
    second = fake_voice(env, supported=False, reason="reason b", engine="Fake")
    for pair in (first, first, second):
        assert policy.select(pair.voice, pair.core) == env.models.CompletionContract()
    assert [args[1:] for args in warnings] == [
        ("Fake", "2026.1", "default", "test-profile", "reason a"),
        ("Fake", "2026.1", "default", "test-profile", "reason b"),
    ]
    assert warnings[0][0] == "WorldVoice %s uses LEGACY_DONE (NVDA %s, audio %s, profile %s): %s"


def test_fallback_dedupe_belongs_to_one_policy(env):
    policies = policies_of(env)
    warnings = []
    logger = SimpleNamespace(warning=lambda *args: warnings.append(args))
    pair = fake_voice(env, supported=False)
    for _ in range(2):
        policies.CompletionPolicy(nvda_version="2026.1", logger=logger).select(pair.voice, pair.core)
    assert len(warnings) == 2


@pytest.mark.parametrize("profile,supported", [(True, True), (True, False), (False, True)])
def test_select_matches_contract_for(env, profile, supported):
    policies = policies_of(env)
    policy = policies.CompletionPolicy(nvda_version="2026.1",
        logger=SimpleNamespace(warning=lambda *args: None))
    pair = fake_voice(env, profile=profile, supported=supported)
    expected, _ = policy.contract_for(pair.voice, pair.core, nvda_version="2026.1",
        audio_mode=policy.audio_mode(pair.voice, pair.core))
    assert policy.select(pair.voice, pair.core) == expected
