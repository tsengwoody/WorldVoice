# Phase 5: Voice Binding, EngineResource and DrainProfile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- Engine `Voice` classes stop being global state:
  - they create and destroy cores for the adapter that owns them;
  - instances receive their binding through the constructor;
  - they declare drain capability with a `DrainProfile` instead of being proven by reflection.
- `VoiceManager` tracks each opened engine as an `EngineResource`.

**Architecture:**
- **Task 1** replaces the reflection in `compat/completionPolicies.py` with:
  - a `CompletionPolicy` class (`audio_mode`, `drain_support`, `contract_for`, `force_unverified_drain` as a constructor argument);
  - per-engine `drain_profile` declarations on each `Voice`.

  The main driver's `_completion_for` delegates to it.
- **Task 2** replaces `engineOn`/`engineOff`/`cls.core`/`cls.session`/`_runtime_binding` with:
  - `create_core()`/`destroy_core(core)`/`voices(core)`;
  - `LegacyVoiceBinding(settings, session, core)` passed to `VoiceFacade(spec, binding, taskManager)`.

  The adapter owns its core, and the alias machinery is deleted.
- **Task 3** turns `VoiceManager._resources` tuples into `EngineResource` and splits `_initialize` into `_open_engine`/`_bind`/`_publish`. It also deletes the write-only `installEngine`.
- **Task 4** is the final verification.

**Tech Stack:** Python 3, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-10-04-phase5-voice-binding-design.md`

## Global Constraints

- Work on branch `phase5-voice-binding`, cut from `master` at `f4fc958`. The spec commit `f78de59` and the plan commit are on it.
- **Behavior for users is unchanged:** the same engines open with the same completion contracts, voices, settings, cancel and close behavior.
- Old plugin interfaces are **not** kept: `engineOn`, `engineOff`, `cls.core`, `cls.session`, `_runtime_binding`, `is_source_owned`, `detach_alias`.
- **Never modify inner drivers** (`addon/synthDrivers/WorldVoice/driver/*/driver/`).
- In outer wrappers (`driver/<Engine>/__init__.py`), change only `class Voice` plus the one `from ...runtime.playbackWork import` line that adds `DrainProfile`.
- `runtime/` must not import `compat/`. New names are snake_case.
- Every changed `addon/` file passes `ruff format --check`. Never commit `driver/Neural/`.
- Run from the repo root. Stage explicit paths only, never the user's unstaged deletion of `docs/superpowers/finish_task.md`. Never touch `git stash`.
- Baseline before Task 1: `python3 -m pytest tests -q` → `1446 passed`.
- Each code step applies a patch saved verbatim from this plan. Set `PATCHES=$(mktemp -d)` once, save the block to the named file, then run `git apply`.
- **Mutation steps come after the commit step.** They end with `git checkout -- addon`.
- Every commit message ends with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Same contract for every in-repo engine.**
   - The deleted reflection (module ownership, `driver.__module__`, `signature().bind()`) must have passed for all six engines.
   - Check each wrapper's `Voice.synth_driver_class` against the core its `create_core` returns, and that every declared `DrainProfile` matches the old `DRAIN_ENGINES`/`_WASAPI_MODE_ENGINES` membership:
     - OneCore and SAPI5 are WASAPI-dependent;
     - VE, Cerence, RHVoice and Espeak are not.
2. **Close and failure paths without class state.**
   - `LegacyEngineAdapter.close()` clears its own fields, then calls `destroy_core`. A `destroy_core` failure must still leave the adapter closed and propagate to `EngineSession.close`/`VoiceManager.terminate`, which log and continue.
   - `create_core` failing must leave nothing behind.
   - Check `VoiceManager._initialize` failure rollback: `terminate(commit=False)` must close every resource appended so far.
3. **Two engines can no longer share a core.**
   - Before, two engines whose `Voice` classes resolved to the same `core` (for example a plugin subclassing another engine's `Voice`) shared one session.
   - Now each adapter creates its own core. Confirm no in-repo engine relied on sharing, and that the bridge and index ledger see distinct sources.
4. **Voice instances read `core` through the binding.**
   - VE's and Cerence's `variants` read `self.core`; the facade property returns `binding.core`.
   - Check every instance-side `self.core` read in the add-on, and that `_createVoiceInstance` always passes the resource's binding (never `None` core).
5. **`_completion_for` without `__init__`.**
   - Tests build the driver with `object.__new__` and set `_completionPolicy`; production sets it in `__init__` before `VoiceManager` runs.
   - Check that no other path calls `_completion_for` before `_completionPolicy` exists. `VoiceManager` calls it during its own construction.

---

### Task 1: CompletionPolicy and DrainProfile declarations

Spec §3.

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/runtime/playbackWork.py` (add `DrainProfile`)
- Modify: `addon/synthDrivers/WorldVoice/compat/completionPolicies.py`: rewrite as `CompletionPolicy`, keeping `_VERIFIED_CONTRACTS` and `_DRAIN_CONTRACT`.
- Modify: `addon/synthDrivers/WorldVoice/__init__.py`:
  - import `CompletionPolicy`;
  - set `self._completionPolicy` before `VoiceManager`;
  - rewrite `_completion_for`.
- Modify: `addon/synthDrivers/WorldVoice/driver/__init__.py` (`drain_profile = None`)
- Modify: the six `driver/<Engine>/__init__.py` files: the `DrainProfile` import and the `drain_profile` declaration in `class Voice`.
- Test: `tests/test_engine_interface_guards.py` (new; policy guards)
- Test (rewritten for the new API): `tests/test_runtime_completion_policies.py`, `tests/test_runtime_composition.py`, `tests/runtime_drain_integration_harness.py`, `tests/test_worldvoice_lifecycle.py`, `tests/test_f4_engine_adapters.py`, `tests/test_runtime_legacy_adapter.py`

**Interfaces:**
- Produces:
  - `runtime.playbackWork.DrainProfile(wasapi_dependent: bool = False)`
  - `compat.completionPolicies.CompletionPolicy(*, force_unverified_drain=True)` with:
    - `audio_mode(voice_class, core) -> str`
    - `drain_support(voice_class, core, *, nvda_version, audio_mode) -> DrainSupport`
    - `contract_for(voice_class, core, *, nvda_version, audio_mode) -> (CompletionContract, DrainSupport | None)`
  - `SynthDriver._completionPolicy`.
- Removes: `DRAIN_ENGINES`, `_WASAPI_MODE_ENGINES`, `FORCE_UNVERIFIED_DRAIN`, `resolve_audio_mode`, `get_completion_contract`, `get_segment_drain_support`.

**Test mapping (old → new):**

| Old test | Now |
|---|---|
| `test_rhvoice_uses_drain_only_with_explicit_support` | `test_profiled_voice_uses_drain_only_with_explicit_support` (same 32 cases) |
| `test_unknown_and_external_profiles_still_use_legacy_done`, `test_unknown_engine_fallback_unchanged` | `test_voice_without_profile_still_uses_legacy_done` |
| `test_target_without_drain_support_uses_legacy_done`, `test_unsupported_wrapper_profile_falls_back_before_speech` | `test_profiled_voice_without_support_uses_legacy_done` |
| `test_supported_target_uses_drain_range` | `test_supported_profile_uses_drain_range` |
| `test_synth_policy_uses_actual_opened_core`, `test_resolve_audio_mode_only_reads_wasapi_sensitive_engines` | `test_synth_policy_uses_actual_opened_core` (profile × `useWasapi` matrix, including no profile) |
| (new) | `test_unconfirmed_profile_falls_back_with_concrete_reason`, `test_disabled_force_switch_reports_the_wrapper_reason`, `test_each_installed_voice_declares_its_drain_profile` |
| composition `foreign_voice`, `foreign_driver`, `wrong_signature` cases | deleted: the reflection they exercised no longer exists |

The installed-engine tests, the force-switch tests, the SAPI5 legacy test and the composition selector keep their assertions and switch to `CompletionPolicy`. The reason text `FORCE_UNVERIFIED_DRAIN` becomes `force_unverified_drain`.

- [ ] **Step 1: Rewrite the tests for CompletionPolicy and add the guards**

Save as `$PATCHES/t1-tests.patch`, then run `git apply $PATCHES/t1-tests.patch`:

```diff
diff --git a/tests/runtime_drain_integration_harness.py b/tests/runtime_drain_integration_harness.py
index 3114313..d4a043b 100644
--- a/tests/runtime_drain_integration_harness.py
+++ b/tests/runtime_drain_integration_harness.py
@@ -262,7 +262,6 @@ def assemble(monkeypatch, tmp_path, *, supported=True):
     engine_module.refresh_ready_engine_classes = lambda *args: None
     monkeypatch.setitem(sys.modules, engine_module.__name__, engine_module)
     manager_module = importlib.import_module(PACKAGE + ".voiceManager")
-    policy = importlib.import_module(PACKAGE + ".compat.completionPolicies")
     ledger = importlib.import_module(PACKAGE + ".indexLedger").IndexLedger()
     bridge_type = importlib.import_module(PACKAGE + ".nvdaEventBridge").NvdaEventBridge
     output = SimpleNamespace(indexes=[], dones=[], drains=[], timeline=[], condition=Condition())
@@ -308,16 +307,13 @@ def assemble(monkeypatch, tmp_path, *, supported=True):
     store = rt.settings.VoiceSettingsStore(repo)
 
     def completion_for(cls, core):
-        if supported:
+        if supported and cls.drain_profile is not None:
             # Explicit fake-native callback exclusion evidence, not certification
             # of any installed SDK or physical Windows playback profile.
-            enabled = True
-        else:
-            # Exercise the supported generic fallback branch independently of
-            # the wrappers' newly enabled real-profile capability declarations.
-            enabled = False
-        return policy.get_completion_contract(cls.engine, nvda_version="unverified",
-            audio_mode="unverified", segment_drain_supported=enabled)
+            return rt.models.CompletionContract(rt.models.CompletionMode.DRAIN, rt.models.IndexRange(1, 9999))
+        # Exercise the generic fallback independently of the wrappers' own
+        # drain support checks.
+        return rt.models.CompletionContract()
 
     manager = manager_module.VoiceManager(tasks, store, bridge,
         index_ledger=ledger, completion_for=completion_for)
diff --git a/tests/test_engine_interface_guards.py b/tests/test_engine_interface_guards.py
new file mode 100644
index 0000000..6bd1418
--- /dev/null
+++ b/tests/test_engine_interface_guards.py
@@ -0,0 +1,21 @@
+"""Engines declare what they can do; nothing proves it by reflection or shares state on classes."""
+
+from pathlib import Path
+
+ADDON = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice"
+
+
+def test_completion_policy_reads_declarations_instead_of_reflection():
+	text = (ADDON / "compat/completionPolicies.py").read_text(encoding="utf-8")
+	for removed in ("import sys", "signature", "sys.modules", "__module__", "FORCE_UNVERIFIED_DRAIN",
+					"DRAIN_ENGINES", "_WASAPI_MODE_ENGINES", "def get_segment_drain_support",
+					"def get_completion_contract", "def resolve_audio_mode"):
+		assert removed not in text, removed
+	assert "class CompletionPolicy" in text
+
+
+def test_driver_selects_completion_through_its_policy():
+	text = (ADDON / "__init__.py").read_text(encoding="utf-8")
+	assert "from .compat.completionPolicies import CompletionPolicy\n" in text
+	for removed in ("DRAIN_ENGINES", "get_completion_contract", "get_segment_drain_support", "resolve_audio_mode"):
+		assert removed not in text, removed
diff --git a/tests/test_f4_engine_adapters.py b/tests/test_f4_engine_adapters.py
index 6b0b39e..24d7561 100644
--- a/tests/test_f4_engine_adapters.py
+++ b/tests/test_f4_engine_adapters.py
@@ -79,7 +79,7 @@ def test_onecore_language_is_applied_only_on_activation():
 		def __init__(self, id, name, taskManager, language=None):
 			self.language = language
 	core = types.SimpleNamespace(language="original")
-	environment = {"Voice": BaseVoice, "SynthDriver": object}
+	environment = {"Voice": BaseVoice, "SynthDriver": object, "DrainProfile": lambda **kwargs: None}
 	exec(compile(ast.Module(body=[voice_class], type_ignores=[]), str(path), "exec"), environment)
 	environment["Voice"].core = core
 	adapter = environment["Voice"]("a", "OneCore:a", None, language="en")
diff --git a/tests/test_runtime_completion_policies.py b/tests/test_runtime_completion_policies.py
index c076d96..c5ffb69 100644
--- a/tests/test_runtime_completion_policies.py
+++ b/tests/test_runtime_completion_policies.py
@@ -17,13 +17,45 @@ def env(monkeypatch):
     return SimpleNamespace(module=module, models=models, adapter=adapter)
 
 
+def policies_of(env):
+    return importlib.import_module(env.module.__package__ + ".compat.completionPolicies")
+
+
+def drain_types(env):
+    return importlib.import_module(env.module.__package__ + ".runtime.playbackWork")
+
+
+def fake_voice(env, *, profile=True, wasapi=False, supported=True, reason="Native lifetime is unproven",
+               engine="test-engine"):
+    """A Voice/SynthDriver pair whose core answers the drain check as told."""
+    work = drain_types(env)
+    checked = []
+
+    class SynthDriver:
+        def speak_segment(self, commands, token, *, context, on_event):
+            pass
+
+        def get_segment_drain_support(self, *, nvda_version, audio_mode):
+            checked.append((nvda_version, audio_mode))
+            return work.DrainSupport(supported, "test-profile", reason)
+
+    class Voice:
+        synth_driver_class = SynthDriver
+        drain_profile = work.DrainProfile(wasapi_dependent=wasapi) if profile else None
+
+    Voice.engine = engine
+    return SimpleNamespace(voice=Voice, driver=SynthDriver, core=SynthDriver(), checked=checked)
+
+
 @pytest.mark.parametrize("version", ["unknown", "2026.1", "2026.1.1", "2026.2"])
 @pytest.mark.parametrize("audio", ["default", "wasapi", "legacy", "unknown"])
 @pytest.mark.parametrize("supported", [False, True])
-def test_rhvoice_uses_drain_only_with_explicit_support(env, version, audio, supported):
-    policies = importlib.import_module(env.module.__package__ + ".compat.completionPolicies")
-    contract = policies.get_completion_contract("RHVoice", nvda_version=version, audio_mode=audio,
-                                                segment_drain_supported=supported)
+def test_profiled_voice_uses_drain_only_with_explicit_support(env, version, audio, supported):
+    pair = fake_voice(env, supported=supported)
+    contract, support = policies_of(env).CompletionPolicy().contract_for(
+        pair.voice, pair.core, nvda_version=version, audio_mode=audio)
+    assert pair.checked == [(version, audio)]
+    assert support.supported is supported
     assert contract.mode is (env.models.CompletionMode.DRAIN if supported
                              else env.models.CompletionMode.LEGACY_DONE)
     assert contract.index_range == (env.models.IndexRange(1, 9999) if supported else None)
@@ -33,45 +65,82 @@ def test_rhvoice_uses_drain_only_with_explicit_support(env, version, audio, supp
 @pytest.mark.parametrize("audio", ["default", "wasapi", "legacy", "unknown"])
 @pytest.mark.parametrize("engine", ["external-test-engine", "unknown"])
 @pytest.mark.parametrize("supported", [False, True])
-def test_unknown_and_external_profiles_still_use_legacy_done(env, engine, version, audio, supported):
-    path = env.module.__package__ + ".compat.completionPolicies"
-    assert importlib.util.find_spec(path) is not None, "Completion policies have not been implemented"
-    policies = importlib.import_module(path)
-    contract = policies.get_completion_contract(engine, nvda_version=version, audio_mode=audio,
-                                                segment_drain_supported=supported)
+def test_voice_without_profile_still_uses_legacy_done(env, engine, version, audio, supported):
+    # The core's own answer is never consulted without a declared profile.
+    pair = fake_voice(env, profile=False, supported=supported, engine=engine)
+    contract, support = policies_of(env).CompletionPolicy().contract_for(
+        pair.voice, pair.core, nvda_version=version, audio_mode=audio)
+    assert support is None and pair.checked == []
     assert contract.mode is env.models.CompletionMode.LEGACY_DONE
     assert contract.index_range is None
 
 
-@pytest.mark.parametrize("engine", ["OneCore", "Neural", "VE", "Cerence", "SAPI5", "Espeak", "RHVoice"])
+@pytest.mark.parametrize("wasapi", [False, True])
 @pytest.mark.parametrize("version,audio", [("2026.1", "default"), ("synthetic", "synthetic")])
-def test_target_without_drain_support_uses_legacy_done(env, engine, version, audio):
-    policies = importlib.import_module(env.module.__package__ + ".compat.completionPolicies")
-    contract = policies.get_completion_contract(engine, nvda_version=version, audio_mode=audio)
+def test_profiled_voice_without_support_uses_legacy_done(env, wasapi, version, audio):
+    pair = fake_voice(env, wasapi=wasapi, supported=False)
+    contract, support = policies_of(env).CompletionPolicy().contract_for(
+        pair.voice, pair.core, nvda_version=version, audio_mode=audio)
+    assert support.supported is False and support.reason == "Native lifetime is unproven"
     assert contract.mode is env.models.CompletionMode.LEGACY_DONE
     assert contract.index_range is None
 
 
-@pytest.mark.parametrize("engine", ["OneCore", "Neural", "VE", "Cerence", "SAPI5", "Espeak", "RHVoice"])
-def test_supported_target_uses_drain_range(env, engine):
-    policies = importlib.import_module(env.module.__package__ + ".compat.completionPolicies")
-    contract = policies.get_completion_contract(engine, nvda_version="synthetic", audio_mode="synthetic",
-                                                segment_drain_supported=True)
+@pytest.mark.parametrize("wasapi", [False, True])
+def test_supported_profile_uses_drain_range(env, wasapi):
+    policies = policies_of(env)
+    pair = fake_voice(env, wasapi=wasapi)
+    contract, _ = policies.CompletionPolicy().contract_for(
+        pair.voice, pair.core, nvda_version="synthetic", audio_mode="synthetic")
     assert contract.mode is env.models.CompletionMode.DRAIN
     assert contract.index_range == env.models.IndexRange(1, 9999)
     assert policies._VERIFIED_CONTRACTS == {}
 
 
-@pytest.mark.parametrize("engine,audio_mode", [
-    ("SAPI5", "wasapi"), ("SAPI5", "legacy"), ("SAPI5", "unknown"),
-    ("Espeak", "default"), ("Espeak", "legacy"), ("Espeak", "unknown"),
+@pytest.mark.parametrize("failure,reason", [
+    ("wrong_core", "The opened core is not the Voice's custom outer SynthDriver"),
+    ("missing_entry", "The custom core has no callable speak_segment entry"),
+    ("missing_support", "The custom core has no callable get_segment_drain_support check"),
+    ("support_error", "Drain support inspection failed: RuntimeError: inspection failed"),
+    ("invalid_support", "The wrapper did not return an explicit DrainSupport boolean decision"),
+    ("truthy_support", "The wrapper did not return an explicit DrainSupport boolean decision"),
+    ("unsupported_without_reason", "The wrapper has no supported adapter/native drain profile"),
 ])
-def test_unsupported_wrapper_profile_falls_back_before_speech(env, engine, audio_mode):
-    policies = importlib.import_module(env.module.__package__ + ".compat.completionPolicies")
-    contract = policies.get_completion_contract(engine, nvda_version="2026.1", audio_mode=audio_mode,
-                                                segment_drain_supported=False)
+def test_unconfirmed_profile_falls_back_with_concrete_reason(env, failure, reason):
+    work = drain_types(env)
+    pair = fake_voice(env, supported=failure != "unsupported_without_reason",
+                      reason="" if failure == "unsupported_without_reason" else "unused")
+    core = pair.core
+    if failure == "wrong_core":
+        core = SimpleNamespace(speak_segment=pair.core.speak_segment,
+                               get_segment_drain_support=pair.core.get_segment_drain_support)
+    elif failure == "missing_entry":
+        pair.driver.speak_segment = None
+    elif failure == "missing_support":
+        pair.driver.get_segment_drain_support = None
+    elif failure == "support_error":
+        def fail(self, **kwargs):
+            raise RuntimeError("inspection failed")
+        pair.driver.get_segment_drain_support = fail
+    elif failure == "invalid_support":
+        pair.driver.get_segment_drain_support = lambda self, **kwargs: SimpleNamespace(supported=True)
+    elif failure == "truthy_support":
+        pair.driver.get_segment_drain_support = lambda self, **kwargs: work.DrainSupport("yes", "p", "r")
+    contract, support = policies_of(env).CompletionPolicy().contract_for(
+        pair.voice, core, nvda_version="2026.1", audio_mode="default")
+    assert support.supported is False and support.reason == reason
     assert contract.mode is env.models.CompletionMode.LEGACY_DONE
-    assert contract.index_range is None
+
+
+def test_disabled_force_switch_reports_the_wrapper_reason(env):
+    pair = fake_voice(env, reason="DRAIN explicitly enabled; playback is unverified")
+    policy = policies_of(env).CompletionPolicy(force_unverified_drain=False)
+    contract, support = policy.contract_for(pair.voice, pair.core, nvda_version="2026.1", audio_mode="default")
+    assert support.supported is False and support.profile == "test-profile"
+    assert support.reason == ("Unverified DRAIN is disabled by force_unverified_drain: "
+                              "DRAIN explicitly enabled; playback is unverified")
+    assert contract.mode is env.models.CompletionMode.LEGACY_DONE
+    assert policies_of(env).CompletionPolicy().force_unverified_drain is True
 
 
 @pytest.mark.parametrize("minimum,maximum", [(0, 10), (5, 4), (-10, -1)])
@@ -122,32 +191,41 @@ def test_configure_after_speech_is_rejected(env):
         adapter.configure_completion(env.models.CompletionContract())
 
 
-@pytest.mark.parametrize("engine,use_wasapi,expected", [
-    ("SAPI5", True, "wasapi"), ("SAPI5", False, "legacy"), ("SAPI5", None, "unknown"),
-    ("OneCore", True, "wasapi"), ("OneCore", False, "legacy"), ("OneCore", None, "unknown"),
-    ("Espeak", None, "default"),
-    ("OneCore", "true", "unknown"), ("OneCore", 1, "unknown"), ("OneCore", 0, "unknown"),
-])
-def test_synth_policy_uses_actual_opened_core(env, engine, use_wasapi, expected):
-    selected = []
-    commands = {name: type(name, (), {}) for name in (
-        "IndexCommand", "CharacterModeCommand", "LangChangeCommand", "BreakCommand",
-        "PitchCommand", "RateCommand", "VolumeCommand")}
-    def policy(engine, **kwargs):
-        selected.append((engine, kwargs))
-        return env.models.CompletionContract()
-    real = importlib.import_module(env.module.__package__ + ".compat.completionPolicies")
+COMMANDS = ("IndexCommand", "CharacterModeCommand", "LangChangeCommand", "BreakCommand",
+            "PitchCommand", "RateCommand", "VolumeCommand")
+
+
+def real_completion_selector(policies, warnings, *, policy=None, version="2026.1"):
+    """The real driver's _completion_for, without running its NVDA constructor."""
     root = _load_synth_class({"SynthDriver": object, "synthIndexReached": object(),
-        "synthDoneSpeaking": object(), "versionInfo": SimpleNamespace(version="2026.1"),
-        "get_completion_contract": policy,
-        "get_segment_drain_support": real.get_segment_drain_support,
-        "resolve_audio_mode": real.resolve_audio_mode, "DRAIN_ENGINES": real.DRAIN_ENGINES,
-        "nvdaLog": SimpleNamespace(warning=lambda *args: None), **commands})
+        "synthDoneSpeaking": object(), "versionInfo": SimpleNamespace(version=version),
+        "CompletionPolicy": policies.CompletionPolicy,
+        "nvdaLog": SimpleNamespace(warning=lambda *args: warnings.append(args)),
+        **{name: type(name, (), {}) for name in COMMANDS}})
     synth = object.__new__(root)
-    assert hasattr(synth, "_completion_for"), "Runtime completion policy selection is missing"
-    core = SimpleNamespace() if use_wasapi is None else SimpleNamespace(useWasapi=use_wasapi)
-    synth._completion_for(SimpleNamespace(engine=engine), core)
-    assert selected == [(engine, {"nvda_version": "2026.1", "audio_mode": expected, "segment_drain_supported": False})]
+    synth._completionPolicy = policy or policies.CompletionPolicy()
+    return synth._completion_for
+
+
+@pytest.mark.parametrize("profile,use_wasapi,expected", [
+    ("wasapi", True, "wasapi"), ("wasapi", False, "legacy"), ("wasapi", None, "unknown"),
+    ("wasapi", "true", "unknown"), ("wasapi", 1, "unknown"), ("wasapi", 0, "unknown"),
+    ("plain", True, "default"), ("plain", None, "default"),
+    ("none", True, "default"),
+])
+def test_synth_policy_uses_actual_opened_core(env, profile, use_wasapi, expected):
+    pair = fake_voice(env, profile=profile != "none", wasapi=profile == "wasapi", supported=False)
+    core = pair.core
+    if use_wasapi is not None:
+        core.useWasapi = use_wasapi
+    warnings = []
+    select = real_completion_selector(policies_of(env), warnings)
+    assert select(pair.voice, core).mode is env.models.CompletionMode.LEGACY_DONE
+    if profile == "none":
+        assert pair.checked == [] and warnings == []
+    else:
+        assert pair.checked == [("2026.1", expected)]
+        assert len(warnings) == 1 and warnings[0][1:4] == ("test-engine", "2026.1", expected)
 
 
 @pytest.mark.parametrize("engine,audio_modes", [
@@ -167,30 +245,18 @@ def test_actual_outer_voice_and_core_select_enabled_drain_profiles(
         from rhvoice_drain_harness import load_rhvoice
         installed = load_rhvoice(monkeypatch, tmp_path)
     try:
-        monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.compat.completionPolicies", raising=False)
-        policies = importlib.import_module("synthDrivers.WorldVoice.compat.completionPolicies")
-        assert sys.modules["synthDrivers.WorldVoice.driver." + engine] is installed.outer
+        policies = fresh_policies(monkeypatch)
+        policy = policies.CompletionPolicy()
         assert installed.outer.Voice.synth_driver_class is type(installed.driver)
         for audio_mode, expected in audio_modes:
-            support = policies.get_segment_drain_support(installed.outer.Voice, installed.driver,
+            contract, support = policy.contract_for(installed.outer.Voice, installed.driver,
                 nvda_version="2026.1", audio_mode=audio_mode)
             assert support.supported is expected and support.reason
-            contract = policies.get_completion_contract(engine, nvda_version="2026.1",
-                audio_mode=audio_mode, segment_drain_supported=support.supported)
             expected_mode = (installed.rt.models.CompletionMode.DRAIN if expected
                 else installed.rt.models.CompletionMode.LEGACY_DONE)
             assert contract.mode is expected_mode
-        commands = {name: type(name, (), {}) for name in (
-            "IndexCommand", "CharacterModeCommand", "LangChangeCommand", "BreakCommand",
-            "PitchCommand", "RateCommand", "VolumeCommand")}
         warnings = []
-        root = _load_synth_class({"SynthDriver": object, "synthIndexReached": object(),
-            "synthDoneSpeaking": object(), "versionInfo": SimpleNamespace(version="2026.1"),
-            "get_completion_contract": policies.get_completion_contract,
-            "get_segment_drain_support": policies.get_segment_drain_support,
-            "resolve_audio_mode": policies.resolve_audio_mode, "DRAIN_ENGINES": policies.DRAIN_ENGINES,
-            "nvdaLog": SimpleNamespace(warning=lambda *args: warnings.append(args)), **commands})
-        selected = object.__new__(root)._completion_for(installed.outer.Voice, installed.driver)
+        selected = real_completion_selector(policies, warnings)(installed.outer.Voice, installed.driver)
         assert selected.mode is installed.rt.models.CompletionMode.DRAIN
         assert selected.index_range is not None
         if engine == "RHVoice":
@@ -211,21 +277,11 @@ def test_sapi5_legacy_first_segment_remains_legacy_done(monkeypatch):
     installed = load_sapi5(monkeypatch)
     try:
         installed.driver.useWasapi = False
-        monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.compat.completionPolicies", raising=False)
-        policies = importlib.import_module("synthDrivers.WorldVoice.compat.completionPolicies")
-        support = policies.get_segment_drain_support(installed.outer.Voice, installed.driver,
+        policies = fresh_policies(monkeypatch)
+        support = policies.CompletionPolicy().drain_support(installed.outer.Voice, installed.driver,
             nvda_version="2026.1", audio_mode="legacy")
         assert support.supported is False
-        commands = {name: type(name, (), {}) for name in (
-            "IndexCommand", "CharacterModeCommand", "LangChangeCommand", "BreakCommand",
-            "PitchCommand", "RateCommand", "VolumeCommand")}
-        root = _load_synth_class({"SynthDriver": object, "synthIndexReached": object(),
-            "synthDoneSpeaking": object(), "versionInfo": SimpleNamespace(version="2026.1"),
-            "get_completion_contract": policies.get_completion_contract,
-            "get_segment_drain_support": policies.get_segment_drain_support,
-            "resolve_audio_mode": policies.resolve_audio_mode, "DRAIN_ENGINES": policies.DRAIN_ENGINES,
-            "nvdaLog": SimpleNamespace(warning=lambda *args: None), **commands})
-        contract = object.__new__(root)._completion_for(installed.outer.Voice, installed.driver)
+        contract = real_completion_selector(policies, [])(installed.outer.Voice, installed.driver)
         assert contract.mode is installed.rt.models.CompletionMode.LEGACY_DONE
         assert contract.index_range is None
         assert installed.native.calls == []
@@ -270,19 +326,6 @@ def fresh_policies(monkeypatch):
     return importlib.import_module("synthDrivers.WorldVoice.compat.completionPolicies")
 
 
-def real_completion_selector(policies, warnings):
-    commands = {name: type(name, (), {}) for name in (
-        "IndexCommand", "CharacterModeCommand", "LangChangeCommand", "BreakCommand",
-        "PitchCommand", "RateCommand", "VolumeCommand")}
-    root = _load_synth_class({"SynthDriver": object, "synthIndexReached": object(),
-        "synthDoneSpeaking": object(), "versionInfo": SimpleNamespace(version="2026.1"),
-        "get_completion_contract": policies.get_completion_contract,
-        "get_segment_drain_support": policies.get_segment_drain_support,
-        "resolve_audio_mode": policies.resolve_audio_mode, "DRAIN_ENGINES": policies.DRAIN_ENGINES,
-        "nvdaLog": SimpleNamespace(warning=lambda *args: warnings.append(args)), **commands})
-    return object.__new__(root)._completion_for
-
-
 @pytest.mark.parametrize("engine", SIX_ENGINES)
 def test_six_enabled_profiles_use_shared_lifecycle(monkeypatch, tmp_path, engine):
     """The actual opened outer core must select DRAIN before any segment starts."""
@@ -290,18 +333,16 @@ def test_six_enabled_profiles_use_shared_lifecycle(monkeypatch, tmp_path, engine
     outer, core, control = installed.outer, installed.core, installed.control
     try:
         policies = fresh_policies(monkeypatch)
-        assert policies.FORCE_UNVERIFIED_DRAIN is True
-        assert sys.modules["synthDrivers.WorldVoice.driver." + engine] is outer
         assert outer.Voice.synth_driver_class is type(core)
+        assert outer.Voice.drain_profile is not None
         # The host owns the lifecycle and implements its hooks.
         host = core._segmentHost
         assert isinstance(host, outer.SegmentHost)
         assert host._lifecycle._hooks is host
-        support = policies.get_segment_drain_support(outer.Voice, core,
+        policy = policies.CompletionPolicy()
+        contract, support = policy.contract_for(outer.Voice, core,
             nvda_version="2026.1", audio_mode=installed.mode)
         assert support.supported is True
-        contract = policies.get_completion_contract(engine, nvda_version="2026.1",
-            audio_mode=installed.mode, segment_drain_supported=support.supported)
         assert contract.mode is policies.CompletionMode.DRAIN
         assert contract.index_range == policies.IndexRange(1, 9999)
         if control is not None:
@@ -317,20 +358,20 @@ def test_disabled_force_switch_restores_legacy_done(monkeypatch, tmp_path, engin
     outer, core = installed.outer, installed.core
     try:
         policies = fresh_policies(monkeypatch)
-        monkeypatch.setattr(policies, "FORCE_UNVERIFIED_DRAIN", False)
-        support = policies.get_segment_drain_support(outer.Voice, core,
+        disabled = policies.CompletionPolicy(force_unverified_drain=False)
+        support = disabled.drain_support(outer.Voice, core,
             nvda_version="2026.1", audio_mode=installed.mode)
         assert support.supported is False
-        assert "FORCE_UNVERIFIED_DRAIN" in support.reason and "unverified" in support.reason
+        assert "force_unverified_drain" in support.reason and "unverified" in support.reason
         warnings = []
-        select = real_completion_selector(policies, warnings)
+        select = real_completion_selector(policies, warnings, policy=disabled)
         contract = select(outer.Voice, core)
         assert contract.mode is installed.rt.models.CompletionMode.LEGACY_DONE
         assert contract.index_range is None
         assert select(outer.Voice, core) == contract
-        assert len(warnings) == 1 and "FORCE_UNVERIFIED_DRAIN" in warnings[0][-1]
-        monkeypatch.setattr(policies, "FORCE_UNVERIFIED_DRAIN", True)
-        assert select(outer.Voice, core).mode is installed.rt.models.CompletionMode.DRAIN
+        assert len(warnings) == 1 and "force_unverified_drain" in warnings[0][-1]
+        enabled = real_completion_selector(policies, warnings)
+        assert enabled(outer.Voice, core).mode is installed.rt.models.CompletionMode.DRAIN
     finally:
         installed.close()
 
@@ -341,8 +382,8 @@ def test_disabled_force_switch_keeps_structural_fallback_reason(monkeypatch):
     try:
         installed.driver.useWasapi = False
         policies = fresh_policies(monkeypatch)
-        monkeypatch.setattr(policies, "FORCE_UNVERIFIED_DRAIN", False)
-        support = policies.get_segment_drain_support(installed.outer.Voice, installed.driver,
+        disabled = policies.CompletionPolicy(force_unverified_drain=False)
+        support = disabled.drain_support(installed.outer.Voice, installed.driver,
             nvda_version="2026.1", audio_mode="legacy")
         assert support.supported is False
         assert support.reason == "SAPI5 legacy audio has no owned player idle barrier"
@@ -350,22 +391,17 @@ def test_disabled_force_switch_keeps_structural_fallback_reason(monkeypatch):
         installed.driver.terminate()
 
 
-@pytest.mark.parametrize("engine,core,expected", [
-    ("SAPI5", SimpleNamespace(useWasapi=True), "wasapi"),
-    ("OneCore", SimpleNamespace(useWasapi=False), "legacy"),
-    ("OneCore", SimpleNamespace(), "unknown"),
-    ("Neural", SimpleNamespace(useWasapi=True), "default"),
-    ("external-test-engine", SimpleNamespace(useWasapi=True), "default"),
+@pytest.mark.parametrize("engine,wasapi_dependent", [
+    ("OneCore", True), ("SAPI5", True),
+    ("VE", False), ("Cerence", False), ("RHVoice", False), ("Espeak", False),
 ])
-def test_resolve_audio_mode_only_reads_wasapi_sensitive_engines(env, engine, core, expected):
-    policies = importlib.import_module(env.module.__package__ + ".compat.completionPolicies")
-    assert policies.resolve_audio_mode(engine, core) == expected
-
-
-@pytest.mark.parametrize("engine", ["unknown", "external-test-engine"])
-def test_unknown_engine_fallback_unchanged(env, engine):
-    policies = importlib.import_module(env.module.__package__ + ".compat.completionPolicies")
-    contract = policies.get_completion_contract(engine, nvda_version="2026.1",
-        audio_mode="default", segment_drain_supported=True)
-    assert contract.mode is env.models.CompletionMode.LEGACY_DONE
-    assert contract.index_range is None
+def test_each_installed_voice_declares_its_drain_profile(engine, wasapi_dependent):
+    # Read the declaration from source: loading each wrapper needs its own fakes.
+    import ast
+    from test_worldvoice_lifecycle import WORLDVOICE
+    tree = ast.parse((WORLDVOICE / "driver" / engine / "__init__.py").read_text(encoding="utf-8"))
+    voice = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Voice")
+    declared = [ast.unparse(node.value) for node in voice.body
+                if isinstance(node, ast.Assign) and [t.id for t in node.targets] == ["drain_profile"]]
+    expected = "DrainProfile(wasapi_dependent=True)" if wasapi_dependent else "DrainProfile()"
+    assert declared == [expected]
diff --git a/tests/test_runtime_composition.py b/tests/test_runtime_composition.py
index 9a95155..8c7b556 100644
--- a/tests/test_runtime_composition.py
+++ b/tests/test_runtime_composition.py
@@ -197,7 +197,8 @@ def test_cached_onecore_voice_round_trip_through_manager(composition):
     path = WORLDVOICE / "driver/OneCore/__init__.py"
     tree = ast.parse(path.read_text(encoding="utf-8"))
     voice_class = next(node for node in tree.body if isinstance(node, ast.ClassDef))
-    environment = {"Voice": c.driver.Voice, "SynthDriver": c.Core}
+    environment = {"Voice": c.driver.Voice, "SynthDriver": c.Core,
+                   "DrainProfile": importlib.import_module(c.module.__package__ + ".runtime.playbackWork").DrainProfile}
     exec(compile(ast.Module(body=[voice_class], type_ignores=[]), str(path), "exec"), environment)
     c.module.READY_ENGINE_CLASS["OneCore"] = environment["Voice"]
     manager = c.create()
@@ -638,8 +639,11 @@ def test_entry_point_imports_real_ledger_and_completion_policy(monkeypatch, nvda
         policies = importlib.import_module(package + ".compat.completionPolicies")
         models = importlib.import_module(package + ".runtime.models")
         assert module.IndexLedger is ledger.IndexLedger
-        assert module.get_completion_contract is policies.get_completion_contract
-        assert module.get_completion_contract("unverified", nvda_version="test", audio_mode="test").mode is models.CompletionMode.LEGACY_DONE
+        assert module.CompletionPolicy is policies.CompletionPolicy
+        voice = SimpleNamespace(engine="unverified", drain_profile=None)
+        contract, support = module.CompletionPolicy().contract_for(
+            voice, object(), nvda_version="test", audio_mode="test")
+        assert contract.mode is models.CompletionMode.LEGACY_DONE and support is None
         assert module.SynthDriver.__module__ == package
         assert ledger.__file__ == str(WORLDVOICE / "indexLedger.py")
         assert policies.__file__ == str(WORLDVOICE / "compat/completionPolicies.py")
@@ -662,19 +666,20 @@ def runtime_completion_selector(c, version="synthetic"):
     root = _load_synth_class({
         "SynthDriver": object, "synthIndexReached": object(), "synthDoneSpeaking": object(),
         "versionInfo": SimpleNamespace(version=version),
-        "get_completion_contract": policies.get_completion_contract,
-        "get_segment_drain_support": policies.get_segment_drain_support,
-        "resolve_audio_mode": policies.resolve_audio_mode, "DRAIN_ENGINES": policies.DRAIN_ENGINES,
+        "CompletionPolicy": policies.CompletionPolicy,
         "nvdaLog": SimpleNamespace(warning=lambda *args: logs.append(args)), **commands,
     })
-    return object.__new__(root)._completion_for, logs
+    synth = object.__new__(root)
+    synth._completionPolicy = policies.CompletionPolicy()
+    return synth._completion_for, logs
 
 
 def installed_drain_voice(c, monkeypatch, name="OneCore", *, supported=True):
     """Replace unavailable native resources at the installed-driver boundary."""
-    support_type = importlib.import_module(c.module.__package__ + ".runtime.playbackWork").DrainSupport
+    work = importlib.import_module(c.module.__package__ + ".runtime.playbackWork")
+    support_type = work.DrainSupport
     cls = c.engine(name)
-    module_name = c.module.__package__ + ".driver." + name
+    cls.drain_profile = work.DrainProfile(wasapi_dependent=name in ("OneCore", "SAPI5"))
     checked, spoken = [], []
 
     class SynthDriver(c.Core):
@@ -687,13 +692,9 @@ def installed_drain_voice(c, monkeypatch, name="OneCore", *, supported=True):
             on_event(c.models.PlaybackEvent(c.models.EventKind.SEGMENT_DRAINED,
                                            context.source_id, segment_id=context.segment_id))
 
-    SynthDriver.__module__ = cls.__module__ = module_name
     cls.synth_driver_class = SynthDriver
     cls.engineOn = classmethod(lambda voice: setattr(voice, "core", SynthDriver()))
-    module = ModuleType(module_name)
-    module.Voice, module.SynthDriver = cls, SynthDriver
-    monkeypatch.setitem(sys.modules, module_name, module)
-    return SimpleNamespace(voice=cls, driver=SynthDriver, module=module,
+    return SimpleNamespace(voice=cls, driver=SynthDriver,
                            checked=checked, spoken=spoken, support_type=support_type)
 
 
@@ -803,23 +804,16 @@ def test_wasapi_mode_sensitive_support_uses_actual_opened_core(
 
 
 @pytest.mark.parametrize("engine", ["OneCore", "SAPI5", "Espeak"])
-@pytest.mark.parametrize("failure", ["foreign_voice", "foreign_driver", "wrong_core", "missing_entry",
-                                    "wrong_signature", "missing_support", "invalid_support",
+@pytest.mark.parametrize("failure", ["wrong_core", "missing_entry", "missing_support", "invalid_support",
                                     "truthy_support", "unsupported", "support_error"])
 def test_unconfirmed_wrapper_uses_legacy_and_logs_concrete_fallback_once(composition, monkeypatch, engine, failure):
     c = composition
     installed = installed_drain_voice(c, monkeypatch, engine)
     cls = installed.voice
-    if failure == "foreign_voice":
-        installed.module.Voice = type("ForeignVoice", (), {})
-    elif failure == "foreign_driver":
-        installed.driver.__module__ = "foreign_driver"
-    elif failure == "wrong_core":
+    if failure == "wrong_core":
         cls.engineOn = classmethod(lambda voice: setattr(voice, "core", c.Core()))
     elif failure == "missing_entry":
         installed.driver.speak_segment = None
-    elif failure == "wrong_signature":
-        installed.driver.speak_segment = lambda self, commands: None
     elif failure == "missing_support":
         installed.driver.get_segment_drain_support = None
     elif failure == "invalid_support":
diff --git a/tests/test_runtime_legacy_adapter.py b/tests/test_runtime_legacy_adapter.py
index a3c1522..08b9157 100644
--- a/tests/test_runtime_legacy_adapter.py
+++ b/tests/test_runtime_legacy_adapter.py
@@ -245,7 +245,7 @@ def test_onecore_cached_a_b_a_restores_language(compat, rt):
     tree = ast.parse(path.read_text(encoding="utf-8"))
     node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Voice")
     core = Core()
-    env = {"Voice": legacy_class(core), "SynthDriver": object}
+    env = {"Voice": legacy_class(core), "SynthDriver": object, "DrainProfile": rt.playback_work.DrainProfile}
     exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), env)
     cls = env["Voice"]
     store = rt.settings.VoiceSettingsStore(MemoryRepository())
diff --git a/tests/test_worldvoice_lifecycle.py b/tests/test_worldvoice_lifecycle.py
index 54c51e2..9cdb0cf 100644
--- a/tests/test_worldvoice_lifecycle.py
+++ b/tests/test_worldvoice_lifecycle.py
@@ -108,6 +108,7 @@ def test_failed_synth_construction_releases_acquired_resources(failure):
 		"WorldVoiceVoiceSettingsPanel": object(),
 		"TaskManager": TaskManager,
 		"VoiceManager": VoiceManager,
+		"CompletionPolicy": lambda: object(),
 		"IndexLedger": Ledger,
 		"NvdaEventBridge": Bridge,
 		"ConfigVoiceSettingsRepository": lambda *args: object(),
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests -q 2>&1 | grep -E "^FAILED|^ERROR tests|^[0-9]+ (passed|failed)" | sed 's/ - .*//' | cut -d: -f1 | sort | uniq -c | sort -rn`
Expected: the last line is `193 failed, 1201 passed, 30 errors`. The failures by file:
- `142 FAILED tests/test_runtime_completion_policies.py`
- `48 FAILED tests/test_runtime_composition.py`
- `30 ERROR tests/test_runtime_drain_integration.py`
- `2 FAILED tests/test_engine_interface_guards.py`
- `1 FAILED tests/test_runtime_legacy_adapter.py`

Every one of them reaches `CompletionPolicy`, `DrainProfile` or `drain_profile`, which do not exist yet.

- [ ] **Step 3: Add DrainProfile, CompletionPolicy and the declarations**

Save as `$PATCHES/t1-impl.patch`, then run `git apply $PATCHES/t1-impl.patch`:

```diff
diff --git a/addon/synthDrivers/WorldVoice/__init__.py b/addon/synthDrivers/WorldVoice/__init__.py
index 66ddffd..2ce34f5 100644
--- a/addon/synthDrivers/WorldVoice/__init__.py
+++ b/addon/synthDrivers/WorldVoice/__init__.py
@@ -48,12 +48,7 @@ from .configRepository import ConfigVoiceSettingsRepository
 from .runtime.settings import VoiceSettingsStore
 from .nvdaEventBridge import NvdaEventBridge
 from .indexLedger import IndexLedger
-from .compat.completionPolicies import (
-	DRAIN_ENGINES,
-	get_completion_contract,
-	get_segment_drain_support,
-	resolve_audio_mode,
-)
+from .compat.completionPolicies import CompletionPolicy
 from .compat.commands import normalize_legacy_commands
 from .taskManager import TaskManager
 from .requestBuilder import queue_speech_sequence
@@ -446,6 +441,7 @@ class SynthDriver(SynthDriver):
 		nvdaLog.debug("WorldVoice init timing: TaskManager %.3fs", time.perf_counter() - step_start)
 
 		step_start = time.perf_counter()
+		self._completionPolicy = CompletionPolicy()
 		self._voiceManager = VoiceManager(
 			taskManager=self.taskManager,
 			settings=self._settingsStore,
@@ -487,26 +483,18 @@ class SynthDriver(SynthDriver):
 		nvdaLog.debug("WorldVoice init timing: total %.3fs", time.perf_counter() - init_start)
 
 	def _completion_for(self, voice_class, core):
-		engine = voice_class.engine
+		policy = self._completionPolicy
 		nvda_version = versionInfo.version
-		audio_mode = resolve_audio_mode(engine, core)
-		drain_supported = False
-		if engine in DRAIN_ENGINES:
-			support = get_segment_drain_support(
-				voice_class,
-				core,
-				nvda_version=nvda_version,
-				audio_mode=audio_mode,
-			)
-			drain_supported = support.supported
-			if not drain_supported:
-				self._warn_drain_fallback(engine, nvda_version, audio_mode, support)
-		return get_completion_contract(
-			engine,
+		audio_mode = policy.audio_mode(voice_class, core)
+		contract, support = policy.contract_for(
+			voice_class,
+			core,
 			nvda_version=nvda_version,
 			audio_mode=audio_mode,
-			segment_drain_supported=drain_supported,
 		)
+		if support is not None and not support.supported:
+			self._warn_drain_fallback(voice_class.engine, nvda_version, audio_mode, support)
+		return contract
 
 	def _warn_drain_fallback(self, engine, nvda_version, audio_mode, support):
 		# Log each distinct fallback profile once per synth instance.
diff --git a/addon/synthDrivers/WorldVoice/compat/completionPolicies.py b/addon/synthDrivers/WorldVoice/compat/completionPolicies.py
index f7de107..512cc77 100644
--- a/addon/synthDrivers/WorldVoice/compat/completionPolicies.py
+++ b/addon/synthDrivers/WorldVoice/compat/completionPolicies.py
@@ -1,109 +1,95 @@
-"""Verified completion opt-ins require evidence for the exact runtime profile.
+"""Completion contracts chosen from each wrapper's declared drain profile.
 
-Keep this table empty until the engine/version/audio mode has documented
+Verified opt-ins require evidence for the exact runtime profile. Keep the
+verified table empty until the engine/version/audio mode has documented
 physical playback and ordered-index evidence. IndexCommand support alone
 never establishes completion semantics or a safe integer range.
 
-Supported custom wrappers use their explicit adapter/native drain contract.
-This is separate from physical playback certification. No installed wrapper
-profile is verified yet, so DRAIN for them is a forced activation controlled by
-FORCE_UNVERIFIED_DRAIN; turning it off restores LEGACY_DONE for every one.
+A wrapper opts into DRAIN by declaring ``Voice.drain_profile``; its opened core
+then decides through ``get_segment_drain_support``. This is separate from
+physical playback certification. No installed wrapper profile is verified yet,
+so DRAIN for them is a forced activation controlled by ``force_unverified_drain``;
+turning it off restores LEGACY_DONE for every one.
 """
 
-from inspect import signature
-import sys
-
 from ..runtime.models import CompletionContract, CompletionMode, IndexRange
 from ..runtime.playbackWork import DrainSupport
 
 
 _VERIFIED_CONTRACTS: dict[tuple[str, str, str], CompletionContract] = {}
 
-# Forced activation of DRAIN on wrapper profiles without playback evidence.
-# Read on every completion selection, so it applies to engines opened later.
-FORCE_UNVERIFIED_DRAIN = True
-
-# Single source for engines whose custom wrapper may report drain support.
-DRAIN_ENGINES = frozenset({"OneCore", "Neural", "VE", "Cerence", "SAPI5", "Espeak", "RHVoice"})
-# Engines whose drain support depends on the opened core's WASAPI setting.
-_WASAPI_MODE_ENGINES = frozenset({"OneCore", "SAPI5"})
 _DRAIN_CONTRACT = CompletionContract(CompletionMode.DRAIN, IndexRange(1, 9999))
 
 
-def resolve_audio_mode(engine: str, core: object) -> str:
-	"""Report the opened core's audio path; only explicit booleans are trusted."""
-	if engine not in _WASAPI_MODE_ENGINES:
-		return "default"
-	use_wasapi = getattr(core, "useWasapi", None)
-	return "wasapi" if use_wasapi is True else "legacy" if use_wasapi is False else "unknown"
-
-
-def get_completion_contract(
-	engine: str,
-	*,
-	nvda_version: str,
-	audio_mode: str,
-	segment_drain_supported: bool = False,
-) -> CompletionContract:
-	# Unsupported target profiles must not select a different contract while a
-	# segment is waiting for completion.
-	if engine in DRAIN_ENGINES:
-		return _DRAIN_CONTRACT if segment_drain_supported is True else CompletionContract()
-	return _VERIFIED_CONTRACTS.get((engine, nvda_version, audio_mode), CompletionContract())
-
-
-def get_segment_drain_support(
-	voice_class: type,
-	core: object,
-	*,
-	nvda_version: str,
-	audio_mode: str,
-) -> DrainSupport:
-	"""Check the opened installed wrapper before composing its event binding.
-
-	Method presence and engine names do not establish native compatibility.
-	The loaded outer module must own both the actual Voice and its driver;
-	only that driver's explicit DrainSupport decision can enable DRAIN.
-	"""
-	module_name = __package__.rsplit(".", 1)[0] + ".driver." + voice_class.engine
-
-	def unsupported(reason):
-		return DrainSupport(False, module_name, reason)
-
-	module = sys.modules.get(module_name)
-	if module is None or getattr(module, "Voice", None) is not voice_class:
-		return unsupported("The actual Voice is not the installed custom outer wrapper")
-	driver = getattr(module, "SynthDriver", None)
-	if (
-		not isinstance(driver, type)
-		or driver.__module__ != module_name
-		or getattr(voice_class, "synth_driver_class", None) is not driver
-	):
-		return unsupported("Voice does not select the installed custom outer SynthDriver")
-	if not isinstance(core, driver):
-		return unsupported("The opened core is not the Voice's custom outer SynthDriver")
-	entry = getattr(core, "speak_segment", None)
-	if not callable(entry):
-		return unsupported("The custom core has no callable speak_segment entry")
-	try:
-		signature(entry).bind((), object(), context=object(), on_event=object())
-	except (TypeError, ValueError):
-		return unsupported("speak_segment does not accept commands, token, context and on_event")
-	check = getattr(core, "get_segment_drain_support", None)
-	if not callable(check):
-		return unsupported("The custom core has no callable get_segment_drain_support check")
-	try:
-		support = check(nvda_version=nvda_version, audio_mode=audio_mode)
-	except Exception as error:
-		return unsupported(f"Drain support inspection failed: {type(error).__name__}: {error}")
-	if not isinstance(support, DrainSupport) or not isinstance(support.supported, bool):
-		return unsupported("The wrapper did not return an explicit DrainSupport boolean decision")
-	if not support.supported and not support.reason:
-		return unsupported("The wrapper has no supported adapter/native drain profile")
-	if support.supported and not FORCE_UNVERIFIED_DRAIN:
-		return DrainSupport(
-			False,
-			support.profile,
-			f"Unverified DRAIN is disabled by FORCE_UNVERIFIED_DRAIN: {support.reason}",
-		)
-	return support
+class CompletionPolicy:
+	def __init__(self, *, force_unverified_drain: bool = True):
+		# Forced activation of DRAIN on wrapper profiles without playback evidence.
+		self.force_unverified_drain = force_unverified_drain
+
+	def audio_mode(self, voice_class: type, core: object) -> str:
+		"""Report the opened core's audio path; only explicit booleans are trusted."""
+		profile = getattr(voice_class, "drain_profile", None)
+		if profile is None or not profile.wasapi_dependent:
+			return "default"
+		use_wasapi = getattr(core, "useWasapi", None)
+		return "wasapi" if use_wasapi is True else "legacy" if use_wasapi is False else "unknown"
+
+	def drain_support(
+		self,
+		voice_class: type,
+		core: object,
+		*,
+		nvda_version: str,
+		audio_mode: str,
+	) -> DrainSupport:
+		"""Ask the opened core of a Voice that declares a drain profile."""
+		module_name = __package__.rsplit(".", 1)[0] + ".driver." + voice_class.engine
+
+		def unsupported(reason):
+			return DrainSupport(False, module_name, reason)
+
+		if getattr(voice_class, "drain_profile", None) is None:
+			return unsupported("The Voice declares no drain profile")
+		driver = getattr(voice_class, "synth_driver_class", None)
+		if not isinstance(driver, type) or not isinstance(core, driver):
+			return unsupported("The opened core is not the Voice's custom outer SynthDriver")
+		if not callable(getattr(core, "speak_segment", None)):
+			return unsupported("The custom core has no callable speak_segment entry")
+		check = getattr(core, "get_segment_drain_support", None)
+		if not callable(check):
+			return unsupported("The custom core has no callable get_segment_drain_support check")
+		try:
+			support = check(nvda_version=nvda_version, audio_mode=audio_mode)
+		except Exception as error:
+			return unsupported(f"Drain support inspection failed: {type(error).__name__}: {error}")
+		if not isinstance(support, DrainSupport) or not isinstance(support.supported, bool):
+			return unsupported("The wrapper did not return an explicit DrainSupport boolean decision")
+		if not support.supported and not support.reason:
+			return unsupported("The wrapper has no supported adapter/native drain profile")
+		if support.supported and not self.force_unverified_drain:
+			return DrainSupport(
+				False,
+				support.profile,
+				f"Unverified DRAIN is disabled by force_unverified_drain: {support.reason}",
+			)
+		return support
+
+	def contract_for(
+		self,
+		voice_class: type,
+		core: object,
+		*,
+		nvda_version: str,
+		audio_mode: str,
+	) -> tuple[CompletionContract, DrainSupport | None]:
+		"""Select the contract before any segment starts.
+
+		Returns the wrapper's drain support decision too, or None when the Voice
+		declares no drain profile. Unsupported profiles must not select a
+		different contract while a segment is waiting for completion.
+		"""
+		if getattr(voice_class, "drain_profile", None) is None:
+			key = (voice_class.engine, nvda_version, audio_mode)
+			return _VERIFIED_CONTRACTS.get(key, CompletionContract()), None
+		support = self.drain_support(voice_class, core, nvda_version=nvda_version, audio_mode=audio_mode)
+		return (_DRAIN_CONTRACT if support.supported else CompletionContract()), support
diff --git a/addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py b/addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py
index e1982e8..50aab08 100644
--- a/addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py
+++ b/addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py
@@ -36,7 +36,7 @@ from synthDrivers.WorldVoice.driver import Voice, getVoiceKey
 from synthDrivers.WorldVoice.text.arabic import break_repeated_runs
 from synthDrivers.WorldVoice.text.chunker import split_speech_text_pieces
 from ...runtime.models import PlaybackContext, SegmentEventSink, SpeechCommands
-from ...runtime.playbackWork import DrainSupport, unverified_drain_support
+from ...runtime.playbackWork import DrainProfile, DrainSupport, unverified_drain_support
 from ...runtime.segmentHost import SegmentHost
 from ...runtime.session import CancellationView
 
@@ -920,6 +920,7 @@ class Voice(Voice):
 	extra_capabilities = frozenset({"waitfactor", "variant"})
 	core = None
 	engine = "Cerence"
+	drain_profile = DrainProfile()
 	synth_driver_class = SynthDriver
 
 	def applyEngineSettings(self, core, snapshot):
diff --git a/addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py b/addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py
index ccbb52d..ffac4ab 100644
--- a/addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py
+++ b/addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py
@@ -7,7 +7,7 @@ from synthDriverHandler import synthDoneSpeaking
 from logHandler import log
 from synthDrivers.WorldVoice.driver import Voice
 from ...runtime.models import PlaybackContext, SegmentEventSink, SpeechCommands
-from ...runtime.playbackWork import runtime_profile, unverified_drain_support
+from ...runtime.playbackWork import DrainProfile, runtime_profile, unverified_drain_support
 from ...runtime.segmentHost import LeasedPlayer, NativeRecord, SegmentHost
 from ...runtime.session import CancellationView
 
@@ -178,4 +178,5 @@ class SynthDriver(BaseSynthDriver):
 class Voice(Voice):
 	core = None
 	engine = "Espeak"
+	drain_profile = DrainProfile()
 	synth_driver_class = SynthDriver
diff --git a/addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py b/addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py
index ea9ca42..d6a1a50 100644
--- a/addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py
+++ b/addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py
@@ -12,7 +12,7 @@ from synthDriverHandler import synthDoneSpeaking, synthIndexReached
 from .driver import OneCoreSynthDriver as BaseOneCoreSynthDriver
 from synthDrivers.WorldVoice.driver import Voice
 from ...runtime.models import PlaybackContext, SegmentEventSink, SpeechCommands
-from ...runtime.playbackWork import DrainSupport, runtime_profile, unverified_drain_support
+from ...runtime.playbackWork import DrainProfile, DrainSupport, runtime_profile, unverified_drain_support
 from ...runtime.segmentHost import SegmentHost
 from ...runtime.session import CancellationView
 
@@ -25,6 +25,7 @@ SynthDriver = BaseOneCoreSynthDriver
 class Voice(Voice):
 	core = None
 	engine = "OneCore"
+	drain_profile = DrainProfile(wasapi_dependent=True)
 	synth_driver_class = SynthDriver
 
 	def applyEngineSettings(self, core, snapshot):
diff --git a/addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py b/addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py
index 4a704dc..09ea149 100644
--- a/addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py
+++ b/addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py
@@ -7,7 +7,7 @@ import weakref
 from . import driver as rhvoice
 from synthDrivers.WorldVoice.driver import Voice
 from ...runtime.models import PlaybackContext, SegmentEventSink, SpeechCommands
-from ...runtime.playbackWork import runtime_profile, unverified_drain_support
+from ...runtime.playbackWork import DrainProfile, runtime_profile, unverified_drain_support
 from ...runtime.segmentHost import SegmentHost
 from ...runtime.session import CancellationView
 
@@ -381,4 +381,5 @@ class SynthDriver(rhvoice.SynthDriver):
 class Voice(Voice):
 	core = None
 	engine = "RHVoice"
+	drain_profile = DrainProfile()
 	synth_driver_class = SynthDriver
diff --git a/addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py b/addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py
index 0a67ba8..f4ec28f 100644
--- a/addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py
+++ b/addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py
@@ -8,7 +8,7 @@ from synthDriverHandler import synthIndexReached
 from logHandler import log
 from synthDrivers.WorldVoice.driver import Voice
 from ...runtime.models import PlaybackContext, SegmentEventSink, SpeechCommands
-from ...runtime.playbackWork import DrainSupport, unverified_drain_support
+from ...runtime.playbackWork import DrainProfile, DrainSupport, unverified_drain_support
 from ...runtime.segmentHost import SegmentHost
 from ...runtime.session import CancellationView
 
@@ -628,5 +628,6 @@ class SynthDriver(BaseSynthDriver):
 class Voice(Voice):
 	core = None
 	engine = "SAPI5"
+	drain_profile = DrainProfile(wasapi_dependent=True)
 
 	synth_driver_class = SynthDriver
diff --git a/addon/synthDrivers/WorldVoice/driver/VE/__init__.py b/addon/synthDrivers/WorldVoice/driver/VE/__init__.py
index e3b5c8f..b272aaa 100644
--- a/addon/synthDrivers/WorldVoice/driver/VE/__init__.py
+++ b/addon/synthDrivers/WorldVoice/driver/VE/__init__.py
@@ -36,7 +36,7 @@ from synthDrivers.WorldVoice.driver import Voice, getVoiceKey
 from synthDrivers.WorldVoice.text.arabic import break_repeated_runs
 from synthDrivers.WorldVoice.text.chunker import split_speech_text_pieces
 from ...runtime.models import PlaybackContext, SegmentEventSink, SpeechCommands
-from ...runtime.playbackWork import DrainSupport, unverified_drain_support
+from ...runtime.playbackWork import DrainProfile, DrainSupport, unverified_drain_support
 from ...runtime.segmentHost import SegmentHost
 from ...runtime.session import CancellationView
 
@@ -911,6 +911,7 @@ class Voice(Voice):
 	extra_capabilities = frozenset({"waitfactor", "variant"})
 	core = None
 	engine = "VE"
+	drain_profile = DrainProfile()
 	synth_driver_class = SynthDriver
 
 	def applyEngineSettings(self, core, snapshot):
diff --git a/addon/synthDrivers/WorldVoice/driver/__init__.py b/addon/synthDrivers/WorldVoice/driver/__init__.py
index 4b2b22a..2a76e85 100644
--- a/addon/synthDrivers/WorldVoice/driver/__init__.py
+++ b/addon/synthDrivers/WorldVoice/driver/__init__.py
@@ -16,6 +16,7 @@ class Voice(VoiceFacade):
 	engine = ""
 	synth_driver_class = None
 	extra_capabilities = frozenset()
+	drain_profile = None
 
 	def applyEngineSettings(self, core, snapshot):
 		return None
diff --git a/addon/synthDrivers/WorldVoice/runtime/playbackWork.py b/addon/synthDrivers/WorldVoice/runtime/playbackWork.py
index 54b5e9a..4bd18b3 100644
--- a/addon/synthDrivers/WorldVoice/runtime/playbackWork.py
+++ b/addon/synthDrivers/WorldVoice/runtime/playbackWork.py
@@ -21,6 +21,17 @@ class DrainSupport:
 	reason: str
 
 
+@dataclass(frozen=True)
+class DrainProfile:
+	"""A Voice's declaration that its core reports segment drain.
+
+	The core still decides at runtime through ``get_segment_drain_support``.
+	"""
+
+	# The audio mode follows the opened core's useWasapi setting.
+	wasapi_dependent: bool = False
+
+
 def runtime_profile(engine: str, nvda_version, audio_mode) -> str:
 	"""Name a wrapper profile by engine and the runtime it was opened under."""
 	return f"{engine}/{nvda_version or 'unknown'}/{audio_mode or 'unknown'}"
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests -q 2>&1 | tail -1; ruff format --check addon | tail -1`
Expected: `1424 passed`, then `54 files already formatted`.

- [ ] **Step 5: Commit**

```bash
git add addon/synthDrivers/WorldVoice/runtime/playbackWork.py addon/synthDrivers/WorldVoice/compat/completionPolicies.py \
	addon/synthDrivers/WorldVoice/__init__.py addon/synthDrivers/WorldVoice/driver/__init__.py \
	addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py \
	addon/synthDrivers/WorldVoice/driver/VE/__init__.py addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py \
	addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py \
	tests/test_engine_interface_guards.py tests/test_runtime_completion_policies.py tests/test_runtime_composition.py \
	tests/runtime_drain_integration_harness.py tests/test_worldvoice_lifecycle.py tests/test_f4_engine_adapters.py \
	tests/test_runtime_legacy_adapter.py
git commit -m "refactor(compat): select completion from declared drain profiles

Each Voice declares a DrainProfile; a CompletionPolicy object asks the
opened core of a profiled Voice for its drain support. The reflection
that proved a core was an installed wrapper, the hard-coded engine sets
and the mutable FORCE_UNVERIFIED_DRAIN flag are gone; the flag is now a
policy constructor argument.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Prove the policy is pinned (mutations M1a–M1e, after the commit)**

```bash
mutate() { python3 - "$1" "$2" "$3" <<'PY'
import sys
p, old, new = sys.argv[1:]
s = open(p).read()
assert s.count(old) == 1, old
open(p, "w").write(s.replace(old, new))
PY
}
A=addon/synthDrivers/WorldVoice
check() { timeout 600 python3 -m pytest tests -q -p no:cacheprovider 2>&1 | grep -E '^[0-9]+ (passed|failed)' | sed 's/ in .*//'; git checkout -- addon; }

echo M1a; mutate $A/compat/completionPolicies.py '		if getattr(voice_class, "drain_profile", None) is None:
			key = ' '		if False:
			key = '; check
echo M1b; mutate $A/compat/completionPolicies.py '		if profile is None or not profile.wasapi_dependent:' '		if profile is None:'; check
echo M1c; mutate $A/compat/completionPolicies.py '		if support.supported and not self.force_unverified_drain:' '		if False:'; check
echo M1d; mutate $A/driver/OneCore/__init__.py '	drain_profile = DrainProfile(wasapi_dependent=True)' '	drain_profile = DrainProfile()'; check
echo M1e; mutate $A/compat/completionPolicies.py '"""Completion contracts chosen' 'import sys

"""Completion contracts chosen'; check
git status --short | grep addon
```

Expected (full-suite counts):
- M1a: profile-less voices take the drain path. `66 failed, 1358 passed`.
- M1b: `audio_mode` ignores `wasapi_dependent`. `6 failed, 1418 passed`.
- M1c: `force_unverified_drain` is ignored. `7 failed, 1417 passed`.
- M1d: OneCore stops being WASAPI-dependent. `1 failed, 1423 passed`.
- M1e: `import sys` returns to the policy. `1 failed, 1423 passed` (the guard).

The final `git status` prints nothing.

---

### Task 2: Engines create cores for adapters; voices receive their binding

Spec §1 and §2.

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/__init__.py`:
  - class docstring;
  - remove `core`/`session`/`engineOn`/`engineOff`;
  - add `create_core`/`destroy_core`;
  - `voices(cls, core)`.
- Modify: the six `driver/<Engine>/__init__.py` files: remove `core = None` from `class Voice`, and for VE and Cerence change to `voices(cls, core)`.
- Modify: `addon/synthDrivers/WorldVoice/compat/voiceFacade.py`:
  - `LegacyVoiceBinding(settings, session, core)`;
  - `VoiceFacade(spec, binding, taskManager)` and the `core` property;
  - drop the `Callable` import.
- Modify: `addon/synthDrivers/WorldVoice/compat/engineAdapter.py`:
  - no `is_source_owned`;
  - `open` via `create_core`, the `core` property, `close` via `destroy_core`, `voices(core)`;
  - delete `detach_alias`.
- Modify: `addon/synthDrivers/WorldVoice/voiceManager.py`:
  - `_bindings`;
  - no alias branch;
  - binding per engine;
  - `_createVoiceInstance(spec, binding, taskManager)`;
  - terminate without class writes.
- Test: `tests/test_engine_interface_guards.py` (class-state guard)
- Test (rewritten for the new interface):
  - harnesses: `tests/voice_binding_harness.py`, `tests/runtime_harness.py`, `tests/runtime_drain_integration_harness.py`;
  - tests: `tests/test_runtime_legacy_adapter.py`, `tests/test_runtime_composition.py`, `tests/test_runtime_completion_policies.py`, `tests/test_f4_voice_state.py`, `tests/test_voice_settings_transaction.py`, `tests/test_f4_engine_session.py`, `tests/test_runtime_voice_facade.py`, `tests/test_worldvoice_request_builder.py`, `tests/test_worldvoice_lifecycle.py`, `tests/test_f4_engine_adapters.py`.

**Interfaces:**
- Consumes: Task 1's `CompletionPolicy` (unchanged here).
- Produces:
  - `Voice.create_core() -> core` and `Voice.destroy_core(core)`. `create_core` either returns a core or raises without leaving one.
  - `Voice.voices(core)`.
  - `LegacyVoiceBinding(settings, session, core)`.
  - `VoiceFacade(spec, binding, taskManager)` with `.core`.
  - `LegacyEngineAdapter.core`.
  - `VoiceManager._bindings: dict[str, LegacyVoiceBinding]`.

**Test mapping:**
- **Deleted:** 7 alias tests. Each needs two engines that share one core, which can no longer happen:
  - `test_runtime_composition.py`:
    - `test_shared_source_alias_uses_one_session_and_close`
    - `test_failed_alias_open_preserves_existing_owner_and_closes_once`
    - `test_alias_uses_one_allocator_and_one_close`
    - `test_alias_conflicting_completion_contract_is_rejected`
    - `test_unsupported_targets_sharing_core_keep_one_legacy_owner`
    - `test_drain_alias_uses_only_owner_event_factory`
  - `test_runtime_legacy_adapter.py`: `test_alias_detach_preserves_shared_resource_owner`.
- **Rewritten:**
  - `test_partial_engine_open_is_cleaned_once` → `test_failed_core_creation_leaves_nothing_to_clean` + `test_close_releases_adapter_state_even_when_destroy_core_fails`;
  - `test_raw_engine_lifecycle_does_not_create_an_extra_session` → `test_engine_core_factory_keeps_no_class_state`;
  - `test_engine_session_is_cleared_after_terminate_failure` → `test_destroy_core_failure_propagates`;
  - `test_manager_assigns_engine_session_to_new_voice` → `test_manager_binds_new_voice_to_its_engine`;
  - `test_unbound_facade_refuses_construction` → `test_facade_reads_its_engine_core_from_the_binding`.
- **New:** `test_each_adapter_owns_its_own_core`, and the class-state guard.
- **Other changes:**
  - Composition's fake engine records its open core in a test-only `opened` attribute instead of `cls.core`.
  - Assertions that class state was "not yet published" (`cls.session is None`, `cls._runtime_binding is None`) are removed with the class state.
  - `test_only_started_sessions_are_resolvable` now asserts that the failed engine created no core.

- [ ] **Step 1: Rewrite the tests for the binding interface and add the guard**

Save as `$PATCHES/t2-tests.patch`, then run `git apply $PATCHES/t2-tests.patch`:

```diff
diff --git a/tests/runtime_drain_integration_harness.py b/tests/runtime_drain_integration_harness.py
index d4a043b..b3b61c6 100644
--- a/tests/runtime_drain_integration_harness.py
+++ b/tests/runtime_drain_integration_harness.py
@@ -242,7 +242,7 @@ def assemble(monkeypatch, tmp_path, *, supported=True):
         outer = control.env.outer if engine == "OneCore" else control.env.module
         monkeypatch.setattr(outer.SynthDriver, "supportedSettings", [SimpleNamespace(id=name)
             for name in ("voice", "rate", "rateBoost", "pitch", "volume")], raising=False)
-        outer.Voice.core = control.core
+        monkeypatch.setattr(outer.Voice, "create_core", classmethod(lambda cls, core=control.core: core))
         if engine != "OneCore":
             monkeypatch.setattr(control.core, "_confirm_native_quiescence", lambda native: None)
 
diff --git a/tests/runtime_harness.py b/tests/runtime_harness.py
index a94a609..5a8f689 100644
--- a/tests/runtime_harness.py
+++ b/tests/runtime_harness.py
@@ -385,21 +385,20 @@ def assemble_adapter_contract(monkeypatch, adapter_kind, *, completion_mode="LEG
 
         class LegacyVoice:
             @classmethod
-            def engineOn(cls):
-                cls.core = core
+            def create_core(cls):
                 core.open_count += 1
+                return core
 
             @classmethod
-            def engineOff(cls):
+            def destroy_core(cls, target):
                 core.close_count += 1
-                cls.core = None
 
             @classmethod
             def supportedSettings(cls):
                 return supported
 
             @classmethod
-            def voices(cls):
+            def voices(cls, target):
                 return [vars(spec) for spec in voices]
 
             def applyEngineSettings(self, target, snapshot):
diff --git a/tests/test_engine_interface_guards.py b/tests/test_engine_interface_guards.py
index 6bd1418..7a231e4 100644
--- a/tests/test_engine_interface_guards.py
+++ b/tests/test_engine_interface_guards.py
@@ -19,3 +19,23 @@ def test_driver_selects_completion_through_its_policy():
 	assert "from .compat.completionPolicies import CompletionPolicy\n" in text
 	for removed in ("DRAIN_ENGINES", "get_completion_contract", "get_segment_drain_support", "resolve_audio_mode"):
 		assert removed not in text, removed
+
+
+def _addon_sources():
+	for path in sorted(ADDON.rglob("*.py")):
+		yield path.relative_to(ADDON).as_posix(), path.read_text(encoding="utf-8")
+
+
+def test_engine_classes_hold_no_shared_core_or_session():
+	import re
+
+	found = []
+	class_state = re.compile(r"\b(cls|Voice|voice_class|_voice_class|voiceInstance)\.(core|session|_runtime_binding)\s*=[^=]")
+	for name, text in _addon_sources():
+		for removed in ("engineOn", "engineOff", "_runtime_binding", "detach_alias", "is_source_owned"):
+			if removed in text:
+				found.append(f"{name}: {removed}")
+		for number, line in enumerate(text.splitlines(), 1):
+			if class_state.search(line):
+				found.append(f"{name}:{number}: {line.strip()}")
+	assert found == []
diff --git a/tests/test_f4_engine_adapters.py b/tests/test_f4_engine_adapters.py
index 24d7561..5f81cc9 100644
--- a/tests/test_f4_engine_adapters.py
+++ b/tests/test_f4_engine_adapters.py
@@ -18,7 +18,7 @@ def test_wrapper_settings_are_pending_until_activation(monkeypatch, engine, snap
 	core.getVoiceInstance = lambda voice_id: f"native:{voice_id}"
 	core.getParameter = lambda instance, parameter, type_: "plain"
 	core.availableVariants = {"plain": object(), "bright": object()}
-	monkeypatch.setattr(harness.module.Voice, "core", core)
+	adapter.core = core  # the harness Voice base is a plain object
 	monkeypatch.setattr(harness.module, "TtsSetParamList",
 		lambda instance, pair: lambda: writes.append((instance, pair[1])))
 	adapter.id = "a"
@@ -63,7 +63,7 @@ def test_variant_metadata_read_preserves_playback_state(monkeypatch, engine):
 	core = types.SimpleNamespace(voice="a", rate=71, pitch=63, waitfactor=2)
 	core.getVoiceInstance = lambda voice_id: f"native:{voice_id}"
 	core.getParameter = lambda instance, parameter, type_: "en"
-	monkeypatch.setattr(harness.module.Voice, "core", core)
+	adapter.core = core  # the harness Voice base is a plain object
 	monkeypatch.setattr(harness.module.ve2 if engine == "VE" else harness.module.ttsapi,
 		"getSpeechDBList", lambda language, voice_id: ["plain", "bright"])
 	adapter.id = "b"
diff --git a/tests/test_f4_engine_session.py b/tests/test_f4_engine_session.py
index a622a28..3672de0 100644
--- a/tests/test_f4_engine_session.py
+++ b/tests/test_f4_engine_session.py
@@ -63,12 +63,12 @@ def engine(module, compat, rt):
     def adapter(core):
         class Legacy:
             @classmethod
-            def engineOn(cls):
-                cls.core = core
+            def create_core(cls):
+                return core
 
             @classmethod
-            def engineOff(cls):
-                cls.core = None
+            def destroy_core(cls, target):
+                pass
 
             @classmethod
             def supportedSettings(cls):
diff --git a/tests/test_f4_voice_state.py b/tests/test_f4_voice_state.py
index 2660b56..5328eea 100644
--- a/tests/test_f4_voice_state.py
+++ b/tests/test_f4_voice_state.py
@@ -1,4 +1,6 @@
 import ast
+import dataclasses
+import inspect
 from collections import defaultdict
 import importlib.util
 import sys
@@ -63,11 +65,8 @@ def _create_voices(monkeypatch, config):
 	module = importlib.util.module_from_spec(spec)
 	monkeypatch.setitem(sys.modules, name, module)
 	spec.loader.exec_module(module)
-	install_binding(module, config)
-	return (
-		module.Voice("a", "A:a", None, "en"),
-		module.Voice("b", "B:b", None, "fr"),
-	)
+	voice = install_binding(module, config)
+	return voice("a", "A:a", "en"), voice("b", "B:b", "fr")
 
 
 def _load_panel_class(config):
@@ -116,8 +115,8 @@ class RecordingCore:
 def test_voice_settings_are_pending_and_revision_tracks_real_changes(monkeypatch):
 	(a, b), config = _voices(monkeypatch)
 	core = RecordingCore()
-	a.__class__.core = core
-	c = a.__class__("c", "C:c", None, "en")
+	spec = type(a._state.spec)("c", "C:c", "C:c", "en", "C", "en")
+	c = a.__class__(spec, dataclasses.replace(a._binding, core=core), None)
 	assert (a.revision, b.revision, c.revision) == (0, 0, 0)
 	assert core.writes == []
 	a.rate = 72
@@ -145,7 +144,6 @@ def test_voice_settings_are_pending_and_revision_tracks_real_changes(monkeypatch
 def test_worker_activation_uses_one_snapshot_per_segment(monkeypatch):
 	(a, _), _ = _voices(monkeypatch)
 	core = RecordingCore()
-	a.__class__.core = core
 	bind_core(core, a)
 	a.active()
 	first_count = len(core.writes)
@@ -175,31 +173,30 @@ def test_speech_queue_does_not_activate_voice(monkeypatch):
 	a.active = lambda: (_ for _ in ()).throw(AssertionError("queue activated voice"))
 	request = object()
 	a.speak(["hello"], request)
-	assert queued == [(request, a.session, a.name, ("hello",))]
+	assert queued == [(request, a._binding.session, a.name, ("hello",))]
 	assert core.spoken == []
 	assert core.writes == []
 
 
-def test_manager_assigns_engine_session_to_new_voice(monkeypatch):
+def test_manager_binds_new_voice_to_its_engine(monkeypatch):
 	(a, _), _ = _voices(monkeypatch)
 	module = sys.modules["f4_test_worldvoice.voiceManager"]
-	engine = a.__class__
-	engine.session = a._binding.session
-	module.READY_ENGINE_CLASS["A"] = engine
-	voice_meta = a._binding.spec_for("A:new")
+	module.READY_ENGINE_CLASS["A"] = a.__class__
+	voice_meta = type(a._state.spec)("new", "A:new", "A:new", "en", "A", "en")
 	manager_instance = object.__new__(module.VoiceManager)
 	manager_instance._specs = {voice_meta.name: voice_meta}
-	manager_instance._sessions = {"A": engine.session}
+	manager_instance._bindings = {"A": a._binding}
 	manager_instance.settings = a._binding.settings
 	manager_instance.taskManager = None
 	manager_instance._instanceCache = {}
 	manager_instance._waitfactor = 0
 	created = manager_instance._createVoiceInstance("A:new")
-	assert "session" in created.__dict__
-	assert created.session is engine.session
+	assert created._binding is a._binding
+	assert created.core is a._binding.core
+	assert "session" not in vars(created)
 
 
-def test_raw_engine_lifecycle_does_not_create_an_extra_session(monkeypatch):
+def test_engine_core_factory_keeps_no_class_state(monkeypatch):
 	(a, _), _ = _voices(monkeypatch)
 	terminated = []
 
@@ -208,20 +205,19 @@ def test_raw_engine_lifecycle_does_not_create_an_extra_session(monkeypatch):
 			terminated.append(self)
 
 	class Voice(a.__class__):
-		core = None
-		session = None
 		synth_driver_class = Core
 
-	Voice.engineOn()
-	assert Voice.session is None
-	core = Voice.core
-	Voice.engineOff()
-	assert terminated == [core]
-	assert Voice.core is None
-	assert Voice.session is None
+	Voice.engine = "A"
+	first, second = Voice.create_core(), Voice.create_core()
+	assert isinstance(first, Core) and first is not second
+	assert first.wv == "A"
+	Voice.destroy_core(first)
+	assert terminated == [first]
+	assert {"core", "session", "_runtime_binding"}.isdisjoint(vars(Voice))
+	assert isinstance(inspect.getattr_static(Voice, "core"), property)
 
 
-def test_engine_session_is_cleared_after_terminate_failure(monkeypatch):
+def test_destroy_core_failure_propagates(monkeypatch):
 	(a, _), _ = _voices(monkeypatch)
 
 	class Core(RecordingCore):
@@ -229,14 +225,11 @@ def test_engine_session_is_cleared_after_terminate_failure(monkeypatch):
 			raise RuntimeError("terminate failed")
 
 	class Voice(a.__class__):
-		core = None
 		synth_driver_class = Core
 
-	Voice.engineOn()
+	core = Voice.create_core()
 	with pytest.raises(RuntimeError, match="terminate failed"):
-		Voice.engineOff()
-	assert Voice.core is None
-	assert Voice.session is None
+		Voice.destroy_core(core)
 
 
 def test_cancel_during_activation_skips_speech(manager, buses):
@@ -304,7 +297,6 @@ def test_preview_b_while_a_is_playing_then_cancel_restores_next_segment(monkeypa
 			self.release.wait(2)
 
 	core = BlockingCore()
-	a.__class__.core = core
 	session = bind_core(core, a, b)
 	a.active()
 	playback = threading.Thread(target=core.speak, args=("A is speaking",))
@@ -369,7 +361,6 @@ def test_ui_consistency_copy_is_atomic_for_worker_activation(monkeypatch, action
 	(a, b), config = _voices(monkeypatch)
 	a.update_settings(rate=72, pitch=61, volume=73, inflection=44, rateBoost=True)
 	core = RecordingCore()
-	a.__class__.core = core
 	bind_core(core, a, b)
 	manager_module = sys.modules["f4_test_worldvoice.voiceManager"]
 	manager_instance = object.__new__(manager_module.VoiceManager)
diff --git a/tests/test_runtime_completion_policies.py b/tests/test_runtime_completion_policies.py
index c5ffb69..109468d 100644
--- a/tests/test_runtime_completion_policies.py
+++ b/tests/test_runtime_completion_policies.py
@@ -158,10 +158,9 @@ def test_contextual_legacy_option_cannot_change_marker_completion(env, mode):
 
 def make_adapter(env):
     class Voice:
-        core = None
         @classmethod
-        def engineOn(cls):
-            cls.core = SimpleNamespace(speak=lambda commands: None)
+        def create_core(cls):
+            return SimpleNamespace(speak=lambda commands: None)
         @classmethod
         def supportedSettings(cls):
             return ()
diff --git a/tests/test_runtime_composition.py b/tests/test_runtime_composition.py
index 8c7b556..089f53d 100644
--- a/tests/test_runtime_composition.py
+++ b/tests/test_runtime_composition.py
@@ -58,25 +58,31 @@ def composition(monkeypatch):
         def cancel(self):
             self.cancels += 1
 
-    def engine(name, *, shared=None, fail=False, empty=False):
+    def engine(name, *, fail=False, empty=False):
         class Voice(driver.Voice):
-            core = None
-            session = None
             synth_driver_class = Core
+            opened = None  # Test bookkeeping: the core this engine has open.
 
             @classmethod
-            def engineOn(cls):
-                cls.core = shared or Core()
+            def create_core(cls):
                 if fail:
                     raise RuntimeError("partial open")
+                cls.opened = cls.synth_driver_class()
+                return cls.opened
+
+            @classmethod
+            def destroy_core(cls, core):
+                if cls.opened is core:
+                    cls.opened = None
+                super().destroy_core(core)
 
             @classmethod
             def supportedSettings(cls):
                 return ["rate", "pitch", "volume"]
 
             @classmethod
-            def voices(cls):
-                return [] if empty else super().voices()
+            def voices(cls, core):
+                return [] if empty else super().voices(core)
 
             def applyEngineSettings(self, core, snapshot):
                 core.language = snapshot.language
@@ -112,47 +118,8 @@ def test_only_started_sessions_are_resolvable(composition):
     manager = c.create()
     assert manager.resolve_playback("failed:a") is None
     assert manager.resolve_playback("ok:a") is not None
-    assert c.cores[0].closes == 1
-    assert c.repo.saves == []
-
-
-def test_shared_source_alias_uses_one_session_and_close(composition):
-    c = composition
-    shared = c.Core()
-    first, alias = c.engine("first", shared=shared), c.engine("alias", shared=shared)
-    manager = c.create()
-    assert manager.resolve_playback("first:a") is manager.resolve_playback("alias:a")
-    assert first.session is alias.session
-    manager.getVoiceInstance("alias:a").active()
-    manager.terminate(commit=False)
-    manager.terminate(commit=False)
-    assert shared.closes == 1
-    assert first.core is alias.core is None
-    assert first._runtime_binding is alias._runtime_binding is None
-    assert manager.resolve_playback("first:a") is None
-
-
-def test_failed_alias_open_preserves_existing_owner_and_closes_once(composition):
-    c = composition
-    shared = c.Core()
-    first = c.engine("first", shared=shared)
-    failed = c.engine("failed", shared=shared, fail=True)
-    manager = c.create()
-    session = manager.resolve_playback("first:a")
-    assert session is first.session
-    assert manager.resolve_playback("failed:a") is None
-    assert shared.closes == 0
-    assert failed.core is failed._runtime_binding is None
-    spoken = []
-    def speak(commands):
-        assert shared.closes == 0
-        spoken.append(commands)
-    shared.speak = speak
-    assert session.activate("first:a")
-    session.speak(("owner remains usable",), _idle_token())
-    assert spoken == [("owner remains usable",)]
-    manager.terminate(commit=False)
-    assert shared.closes == 1
+    # A failed create_core leaves no core behind; only the started engine opened one.
+    assert [core.closes for core in c.cores] == [0]
     assert c.repo.saves == []
 
 
@@ -171,7 +138,6 @@ def test_initialization_failure_closes_without_commit(composition, failure):
     assert c.cores[0].closes == 1
     assert c.bridge._sources == {}
     assert c.repo.saves == []
-    assert cls._runtime_binding is None
 
 
 def test_source_is_bound_before_engine_is_published(composition):
@@ -184,9 +150,9 @@ def test_source_is_bound_before_engine_is_published(composition):
         original(source, source_id, **kwargs)
     c.bridge.bind = bind
     original_voices = c.module.READY_ENGINE_CLASS["ok"].voices
-    def voices(cls):
-        assert id(cls.core) in c.bridge._sources
-        return original_voices()
+    def voices(cls, core):
+        assert id(core) in c.bridge._sources
+        return original_voices(core)
     c.module.READY_ENGINE_CLASS["ok"].voices = classmethod(voices)
     assert c.create().resolve_playback("ok:a") is not None
 
@@ -460,8 +426,7 @@ def test_resource_bound_before_first_encoded_speech(composition, nvda_commands):
     selected = []
     contract = marker_contract(c)
     def completion_for(voice_class, core):
-        assert voice_class is cls and core is cls.core
-        assert cls.session is None
+        assert voice_class is cls and core is cls.opened
         selected.append(core)
         return contract
     manager = c.create(completion_for)
@@ -470,8 +435,8 @@ def test_resource_bound_before_first_encoded_speech(composition, nvda_commands):
     finished = threading.Event()
     def speak(commands):
         spoken.extend(commands)
-        c.index.notify(synth=cls.core, index=commands[-1].index)
-    cls.core.speak = speak
+        c.index.notify(synth=cls.opened, index=commands[-1].index)
+    cls.opened.speak = speak
     c.done.register(lambda synth: finished.set() if synth is c.owner else None)
     request = c.tasks.new_request()
     original = nvda_commands.IndexCommand(42)
@@ -480,41 +445,10 @@ def test_resource_bound_before_first_encoded_speech(composition, nvda_commands):
     assert finished.wait(1)
     assert [item.index for item in spoken if isinstance(item, nvda_commands.IndexCommand)] == [501, 502]
     assert original.index == 42
-    assert selected == [cls.core]
+    assert selected == [cls.opened]
     assert port.completion == contract
 
 
-def test_alias_uses_one_allocator_and_one_close(composition, nvda_commands):
-    c = composition
-    shared = c.Core()
-    c.engine("first", shared=shared)
-    c.engine("alias", shared=shared)
-    manager = c.create(lambda cls, core: marker_contract(c))
-    spoken = []
-    shared.speak = lambda commands: spoken.append(commands[-1].index)
-    for segment, key in enumerate(("first:a", "alias:a"), 1):
-        port = manager.resolve_playback(key)
-        port.speak(("hello",), _idle_token(),
-                   context=c.models.PlaybackContext(port.source_id, segment))
-    assert spoken == [501, 502]
-    manager.terminate(commit=False)
-    assert shared.closes == 1
-
-
-def test_alias_conflicting_completion_contract_is_rejected(composition):
-    c = composition
-    shared = c.Core()
-    first = c.engine("first", shared=shared)
-    alias = c.engine("alias", shared=shared)
-    with pytest.raises(ValueError, match="completion contract"):
-        c.create(lambda cls, core: marker_contract(c) if cls is first else c.models.CompletionContract())
-    assert first.session is alias.session is None
-    assert first.core is alias.core is None
-    assert shared.closes == 1
-    assert c.bridge._sources == {}
-    assert c.repo.saves == []
-
-
 def test_partial_bind_failure_releases_resources_without_commit(composition):
     c = composition
     cls = c.engine("marker")
@@ -523,7 +457,6 @@ def test_partial_bind_failure_releases_resources_without_commit(composition):
     def bind(source, source_id, **kwargs):
         original(source, source_id, **kwargs)
         source_ids.append(source_id)
-        assert cls.session is None
         raise RuntimeError("partial marker bind")
     c.bridge.bind = bind
     with pytest.raises(RuntimeError, match="partial marker bind"):
@@ -543,13 +476,13 @@ def test_shutdown_disables_late_index_before_engine_close(composition):
     marker = c.ledger.prepare(c.models.PlaybackContext(port.source_id, 1), (42,)).end_index
     received = []
     c.index.register(lambda synth, index: received.append(index) if synth is c.owner else None)
-    original_close = cls.core.terminate
+    original_close = cls.opened.terminate
     def close():
         assert c.bridge._closed
         assert not c.ledger._closed
-        c.index.notify(synth=cls.core, index=marker)
+        c.index.notify(synth=cls.opened, index=marker)
         original_close()
-    cls.core.terminate = close
+    cls.opened.terminate = close
     synth, errors = make_synth(c, manager)
     synth.terminate()
     assert received == []
@@ -565,7 +498,6 @@ def test_completion_selection_failure_closes_opened_core(composition):
     with pytest.raises(RuntimeError, match="policy failure"):
         c.create(fail)
     assert c.cores[0].closes == 1
-    assert cls.session is None
     assert c.repo.saves == []
 
 
@@ -575,14 +507,14 @@ def test_live_core_rebind_preserves_allocator_high_water(composition, nvda_comma
     manager = c.create(lambda cls, core: marker_contract(c))
     port = manager.resolve_playback("marker:a")
     spoken = []
-    cls.core.speak = lambda commands: spoken.append(commands[-1].index)
+    cls.opened.speak = lambda commands: spoken.append(commands[-1].index)
     token = _idle_token()
     port.speak(("first",), token, context=c.models.PlaybackContext(port.source_id, 1))
     c.bridge.unbind(port.source_id)
-    c.bridge.bind(cls.core, port.source_id, completion=port.completion)
+    c.bridge.bind(cls.opened, port.source_id, completion=port.completion)
     port.speak(("second",), token, context=c.models.PlaybackContext(port.source_id, 2))
     assert spoken == [501, 502]
-    assert cls.core.closes == 0
+    assert cls.opened.closes == 0
     assert c.ledger.receive_index(port.source_id, 501) == ()
 
 
@@ -693,7 +625,6 @@ def installed_drain_voice(c, monkeypatch, name="OneCore", *, supported=True):
                                            context.source_id, segment_id=context.segment_id))
 
     cls.synth_driver_class = SynthDriver
-    cls.engineOn = classmethod(lambda voice: setattr(voice, "core", SynthDriver()))
     return SimpleNamespace(voice=cls, driver=SynthDriver,
                            checked=checked, spoken=spoken, support_type=support_type)
 
@@ -707,8 +638,7 @@ def test_supported_installed_wrapper_is_bound_before_first_drain_speech(composit
     configured = []
     configure = c.module.LegacyEngineAdapter.configure_segment_events
     def configure_after_bind(adapter, factory):
-        assert installed.voice.session is None
-        assert c.bridge._sources[id(installed.voice.core)].source is installed.voice.core
+        assert c.bridge._sources[id(installed.voice.opened)].source is installed.voice.opened
         configure(adapter, factory)
         configured.append(adapter)
     monkeypatch.setattr(c.module.LegacyEngineAdapter, "configure_segment_events", configure_after_bind)
@@ -811,7 +741,10 @@ def test_unconfirmed_wrapper_uses_legacy_and_logs_concrete_fallback_once(composi
     installed = installed_drain_voice(c, monkeypatch, engine)
     cls = installed.voice
     if failure == "wrong_core":
-        cls.engineOn = classmethod(lambda voice: setattr(voice, "core", c.Core()))
+        def foreign_core(voice):
+            voice.opened = c.Core()
+            return voice.opened
+        cls.create_core = classmethod(foreign_core)
     elif failure == "missing_entry":
         installed.driver.speak_segment = None
     elif failure == "missing_support":
@@ -833,7 +766,7 @@ def test_unconfirmed_wrapper_uses_legacy_and_logs_concrete_fallback_once(composi
     port = manager.resolve_playback(engine + ":a")
     assert port.completion.mode is c.models.CompletionMode.LEGACY_DONE
     assert port.completion.index_range is None
-    assert select(cls, cls.core) == port.completion
+    assert select(cls, cls.opened) == port.completion
     assert len(logs) == 1
     assert "LEGACY_DONE" in logs[0][0] and logs[0][-1]
     if failure == "unsupported":
@@ -842,19 +775,6 @@ def test_unconfirmed_wrapper_uses_legacy_and_logs_concrete_fallback_once(composi
         assert "Native profile inspection failed" in logs[0][-1]
 
 
-def test_unsupported_targets_sharing_core_keep_one_legacy_owner(composition):
-    c = composition
-    shared = c.Core()
-    first, alias = c.engine("OneCore", shared=shared), c.engine("Neural", shared=shared)
-    select, logs = runtime_completion_selector(c)
-    manager = c.create(select)
-    port = manager.resolve_playback("OneCore:a")
-    assert manager.resolve_playback("Neural:a") is port
-    assert port.completion.mode is c.models.CompletionMode.LEGACY_DONE
-    manager.terminate(commit=False)
-    assert shared.closes == 1 and first.core is alias.core is None
-
-
 def test_drain_factory_configured_after_bind_before_publication(composition, monkeypatch, nvda_commands):
     c = composition
     cls = c.engine("drain")
@@ -862,8 +782,7 @@ def test_drain_factory_configured_after_bind_before_publication(composition, mon
     cls.synth_driver_class.speak_segment = lambda core, commands, token, **kwargs: calls.append(kwargs)
     configure = c.module.LegacyEngineAdapter.configure_segment_events
     def configure_after_bind(adapter, factory):
-        assert cls.session is None
-        assert c.bridge._sources[id(cls.core)].source is cls.core
+        assert c.bridge._sources[id(cls.opened)].source is cls.opened
         configure(adapter, factory)
         setup.append(adapter)
     monkeypatch.setattr(c.module.LegacyEngineAdapter, "configure_segment_events", configure_after_bind)
@@ -891,11 +810,11 @@ def test_drain_request_integrates_encoded_indexes_and_native_events(composition,
         drain = c.models.PlaybackEvent(c.models.EventKind.SEGMENT_DRAINED,
                                       context.source_id, segment_id=context.segment_id)
         if mode == "END_INDEX_AND_DRAIN" and order == "end_first":
-            c.index.notify(synth=cls.core, index=commands[-1].index)
+            c.index.notify(synth=cls.opened, index=commands[-1].index)
         on_event(drain)
         if mode == "END_INDEX_AND_DRAIN" and order == "drain_first":
-            c.index.notify(synth=cls.core, index=commands[-1].index)
-    cls.core.speak_segment = speak
+            c.index.notify(synth=cls.opened, index=commands[-1].index)
+    cls.opened.speak_segment = speak
     request = c.tasks.new_request()
     c.tasks.append_speech(request, port, "drain:a", ("hello", nvda_commands.IndexCommand(42),
                                                    nvda_commands.IndexCommand(7)))
@@ -927,7 +846,7 @@ def test_index_handler_revokes_remainder_of_drain_batch(composition, nvda_comman
         on_event(c.models.PlaybackEvent(c.models.EventKind.SEGMENT_DRAINED,
                                       context.source_id, segment_id=context.segment_id))
         returned.set()
-    cls.core.speak_segment = speak
+    cls.opened.speak_segment = speak
     request = c.tasks.new_request()
     future = c.tasks.append_speech(request, port, "drain:a",
                                  (nvda_commands.IndexCommand(42), nvda_commands.IndexCommand(7)))
@@ -940,25 +859,6 @@ def test_index_handler_revokes_remainder_of_drain_batch(composition, nvda_comman
         assert not future.done()
 
 
-def test_drain_alias_uses_only_owner_event_factory(composition, monkeypatch, nvda_commands):
-    c = composition
-    shared = c.Core()
-    shared.speak_segment = lambda *args, **kwargs: None
-    first, alias = c.engine("first", shared=shared), c.engine("alias", shared=shared)
-    configured = []
-    configure = c.module.LegacyEngineAdapter.configure_segment_events
-    def record(adapter, factory):
-        configured.append(adapter)
-        configure(adapter, factory)
-    monkeypatch.setattr(c.module.LegacyEngineAdapter, "configure_segment_events", record)
-    manager = c.create(lambda cls, core: drain_contract(c))
-    owner = manager.resolve_playback("first:a")
-    assert manager.resolve_playback("alias:a") is owner
-    assert configured == [owner._adapter] and len(c.bridge._sources) == 1
-    manager.terminate(commit=False)
-    assert first.session is alias.session is None and shared.closes == 1
-
-
 def test_partial_event_configuration_rolls_back_binding_and_owner(composition, monkeypatch):
     c = composition
     cls = c.engine("drain")
@@ -966,13 +866,12 @@ def test_partial_event_configuration_rolls_back_binding_and_owner(composition, m
     configure = c.module.LegacyEngineAdapter.configure_segment_events
     def fail_after_configure(adapter, factory):
         configure(adapter, factory)
-        assert cls.session is None
         raise RuntimeError("partial event setup")
     monkeypatch.setattr(c.module.LegacyEngineAdapter, "configure_segment_events", fail_after_configure)
     with pytest.raises(RuntimeError, match="partial event setup"):
         c.create(lambda cls, core: drain_contract(c))
     assert c.bridge._sources == {}
-    assert cls.core is cls.session is None and c.cores[0].closes == 1
+    assert cls.opened is None and c.cores[0].closes == 1
     assert c.repo.saves == []
 
 
@@ -983,18 +882,18 @@ def test_each_drain_factory_captures_its_own_resource(composition, nvda_commands
     manager = c.create(lambda cls, core: drain_contract(c))
     calls, completed = [], threading.Event()
     for cls in (first, second):
-        def speak(commands, token, *, context, on_event, source=cls.core):
+        def speak(commands, token, *, context, on_event, source=cls.opened):
             assert c.bridge._sources[id(source)].source_id is context.source_id
             calls.append(source)
             on_event(c.models.PlaybackEvent(c.models.EventKind.SEGMENT_DRAINED,
                                           context.source_id, segment_id=context.segment_id))
-        cls.core.speak_segment = speak
+        cls.opened.speak_segment = speak
     c.done.register(lambda synth: completed.set() if synth is c.owner else None)
     request = c.tasks.new_request()
     for key in ("first:a", "second:a"):
         c.tasks.append_speech(request, manager.resolve_playback(key), key, ("hello",))
     assert c.tasks.submit_request(request) and completed.wait(1)
-    assert calls == [first.core, second.core]
+    assert calls == [first.opened, second.opened]
 
 
 def test_reentrant_drain_supplier_waits_until_current_index_batch_finishes(composition, nvda_commands):
@@ -1022,7 +921,7 @@ def test_reentrant_drain_supplier_waits_until_current_index_batch_finishes(compo
         current["event"] = c.models.PlaybackEvent(c.models.EventKind.SEGMENT_DRAINED,
                                                context.source_id, segment_id=context.segment_id)
         on_event(current["event"])
-    cls.core.speak_segment = speak
+    cls.opened.speak_segment = speak
     request = c.tasks.new_request()
     c.tasks.append_speech(request, port, "drain:a", (nvda_commands.IndexCommand(42),
                                                   nvda_commands.IndexCommand(7)))
@@ -1042,13 +941,13 @@ def test_old_drain_sink_cannot_complete_request_after_core_rebind(composition, n
     def speak(commands, token, *, context, on_event):
         calls.append((context, on_event))
         entered.set()
-    cls.core.speak_segment = speak
+    cls.opened.speak_segment = speak
     first = c.tasks.new_request()
     c.tasks.append_speech(first, port, "drain:a", ("old",))
     assert c.tasks.submit_request(first) and entered.wait(1)
     c.tasks.cancel((port,))
     c.bridge.unbind(port.source_id)
-    c.bridge.bind(cls.core, port.source_id, completion=port.completion)
+    c.bridge.bind(cls.opened, port.source_id, completion=port.completion)
     entered.clear()
     second = c.tasks.new_request()
     future = c.tasks.append_speech(second, port, "drain:a", ("new", nvda_commands.IndexCommand(42)))
diff --git a/tests/test_runtime_legacy_adapter.py b/tests/test_runtime_legacy_adapter.py
index 08b9157..a18e030 100644
--- a/tests/test_runtime_legacy_adapter.py
+++ b/tests/test_runtime_legacy_adapter.py
@@ -53,24 +53,24 @@ class Core:
 def legacy_class(core):
     class Legacy:
         opens = closes = 0
-        session = None
 
         @classmethod
-        def engineOn(cls):
+        def create_core(cls):
             cls.opens += 1
-            cls.core = core
+            return core
 
         @classmethod
-        def engineOff(cls):
+        def destroy_core(cls, target):
+            assert target is core
             cls.closes += 1
-            cls.core = cls.session = None
 
         @classmethod
         def supportedSettings(cls):
             return ["voice", "rateBoost", "rate", "pitch", "volume", "inflection"]
 
         @classmethod
-        def voices(cls):
+        def voices(cls, target):
+            assert target is core
             return [dict(id="a", name="Fake:a", description="A", language="en",
                          engine="Fake", locale="en", langDescription="English")]
 
@@ -87,7 +87,6 @@ def legacy_class(core):
         def variants(self):
             return [{"id": "bright", "name": "Bright"}]
 
-    Legacy.core = None
     return Legacy
 
 
@@ -116,8 +115,9 @@ def test_lifecycle_metadata_and_apply_order(compat, rt):
     adapter.close()
     adapter.close()
     assert cls.closes == 1
-    assert cls.core is None
+    assert adapter.core is None and adapter.notification_source is None
     adapter.open()
+    assert adapter.core is core
     adapter.close()
     assert (cls.opens, cls.closes) == (2, 2)
 
@@ -149,7 +149,7 @@ def test_contextual_legacy_reopen_reconfigures_segment_events(compat, rt):
 @pytest.mark.parametrize("extra", [{}, {"name": "noncanonical", "description": "", "locale": "en_US"}])
 def test_voice_metadata_defaults_and_canonical_key(compat, rt, extra):
     cls = legacy_class(Core())
-    cls.voices = classmethod(lambda cls: [dict(engine="Fake", id="a", language="en_US", **extra)])
+    cls.voices = classmethod(lambda cls, core: [dict(engine="Fake", id="a", language="en_US", **extra)])
     adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: cls())
     assert adapter.list_voices() == (rt.models.VoiceSpec("a", "Fake:a", "", "en_US", "Fake", "en_US"),)
 
@@ -159,7 +159,7 @@ def test_malformed_voice_metadata_does_not_hide_valid_voices(compat, rt):
     valid = dict(engine="Fake", id="a", language="en", name="Fake:a", description="A", locale="en")
     malformed = dict(valid, id="broken")
     del malformed["language"]
-    cls.voices = classmethod(lambda cls: [malformed, valid])
+    cls.voices = classmethod(lambda cls, core: [malformed, valid])
     adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: cls())
     assert adapter.list_voices() == (rt.models.VoiceSpec("a", "Fake:a", "A", "en", "Fake", "en"),)
 
@@ -193,51 +193,56 @@ def test_unsupported_generic_settings_are_not_written(compat, rt):
     assert adapter.capabilities.settings == frozenset({"rate"})
 
 
-@pytest.mark.parametrize("cleanup_fails", [False, True])
-def test_partial_engine_open_is_cleaned_once(compat, rt, cleanup_fails):
+def test_failed_core_creation_leaves_nothing_to_clean(compat, rt):
     core = Core()
     cls = legacy_class(core)
 
     def fail_open(cls):
-        cls.core = core
+        cls.opens += 1
         raise ValueError("open failed")
 
-    def cleanup(cls):
-        cls.closes += 1
-        cls.core = None
-        if cleanup_fails:
-            raise OSError("cleanup failed")
-
-    cls.engineOn = classmethod(fail_open)
-    cls.engineOff = classmethod(cleanup)
+    cls.create_core = classmethod(fail_open)
     adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: cls())
     session = rt.session.EngineSession(adapter, rt.settings.VoiceSettingsStore(MemoryRepository()))
-    with pytest.raises(ValueError, match="open failed") as caught:
+    with pytest.raises(ValueError, match="open failed"):
         session.open()
+    assert adapter.core is None and adapter.notification_source is None
     session.close()
     adapter.close()
-    assert cls.closes == 1
-    assert cls.core is None
-    if cleanup_fails:
-        assert isinstance(caught.value.__cause__, OSError)
+    assert (cls.opens, cls.closes) == (1, 0)
 
 
-def test_alias_detach_preserves_shared_resource_owner(compat):
+def test_close_releases_adapter_state_even_when_destroy_core_fails(compat):
     core = Core()
-    owner_cls, alias_cls = legacy_class(core), legacy_class(core)
-    owner = compat.adapter.LegacyEngineAdapter(owner_cls, lambda key: owner_cls())
-    alias = compat.adapter.LegacyEngineAdapter(alias_cls, lambda key: alias_cls())
-    owner.open()
-    alias.open()
-    alias_cls.session = object()
-    alias_cls._runtime_binding = object()
-    alias.detach_alias()
-    alias.close()
-    assert (alias_cls.core, alias_cls.session, alias_cls._runtime_binding) == (None, None, None)
-    assert owner_cls.core is core
-    assert (owner_cls.closes, alias_cls.closes) == (0, 0)
-    owner.close()
-    assert (owner_cls.closes, alias_cls.closes) == (1, 0)
+    cls = legacy_class(core)
+
+    def fail_destroy(cls, target):
+        cls.closes += 1
+        raise OSError("cleanup failed")
+
+    cls.destroy_core = classmethod(fail_destroy)
+    adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: cls())
+    adapter.open()
+    with pytest.raises(OSError, match="cleanup failed"):
+        adapter.close()
+    assert adapter.core is None and adapter.notification_source is None
+    adapter.close()
+    assert cls.closes == 1
+
+
+def test_each_adapter_owns_its_own_core(compat):
+    first_core, second_core = Core(), Core()
+    first_cls, second_cls = legacy_class(first_core), legacy_class(second_core)
+    first = compat.adapter.LegacyEngineAdapter(first_cls, lambda key: first_cls())
+    second = compat.adapter.LegacyEngineAdapter(second_cls, lambda key: second_cls())
+    first.open()
+    second.open()
+    assert (first.core, second.core) == (first_core, second_core)
+    second.close()
+    assert first.core is first_core
+    assert (first_cls.closes, second_cls.closes) == (0, 1)
+    first.close()
+    assert (first_cls.closes, second_cls.closes) == (1, 1)
 
 
 def test_onecore_cached_a_b_a_restores_language(compat, rt):
@@ -278,10 +283,12 @@ def test_real_variant_and_waitfactor_hooks(compat, rt, monkeypatch, engine):
                         lambda instance, pair: lambda: writes.append((instance, pair[1])))
     monkeypatch.setattr(harness.module.ve2 if engine == "VE" else harness.module.ttsapi,
                         "getSpeechDBList", lambda language, key: ["plain", "bright"])
-    monkeypatch.setattr(cls, "engineOn", classmethod(lambda cls: setattr(cls, "core", core)), raising=False)
+    monkeypatch.setattr(cls, "create_core", classmethod(lambda cls: core), raising=False)
     monkeypatch.setattr(cls, "supportedSettings", classmethod(lambda cls: ["rate"]), raising=False)
     voice = object.__new__(cls)
     voice.id = "a"
+    # The harness's Voice base is a plain object; a bound facade exposes core.
+    voice.core = core
     adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: voice)
     adapter.open()
     core.writes.clear()
diff --git a/tests/test_runtime_voice_facade.py b/tests/test_runtime_voice_facade.py
index 88f8107..f0d2407 100644
--- a/tests/test_runtime_voice_facade.py
+++ b/tests/test_runtime_voice_facade.py
@@ -24,13 +24,13 @@ def setup(compat, rt):
     store = rt.settings.VoiceSettingsStore(repo)
     adapter = FakeAdapter()
     session = rt.session.EngineSession(adapter, store)
-    binding = compat.facade.LegacyVoiceBinding(store, session, make_spec)
+    binding = compat.facade.LegacyVoiceBinding(store, session, None)
 
     class Voice(compat.facade.VoiceFacade):
-        _runtime_binding = binding
+        pass
 
     tasks = RecordingTasks()
-    voice = Voice("a", "Fake:a", tasks, "en")
+    voice = Voice(make_spec("Fake:a"), binding, tasks)
     return SimpleNamespace(repo=repo, store=store, adapter=adapter, session=session,
                            binding=binding, cls=Voice, tasks=tasks, voice=voice)
 
@@ -45,7 +45,7 @@ def test_facade_and_new_api_share_one_state(setup):
     assert facade.rate == 50
     assert facade.pitch == 50
     assert setup.repo.saves == []
-    other = setup.cls("a", "Fake:a", setup.tasks)
+    other = setup.cls(make_spec("Fake:a"), setup.binding, setup.tasks)
     other.volume = 23
     assert facade.volume == 23
     assert setup.repo.loads == ["Fake:a"]
@@ -119,6 +119,10 @@ def test_playback_queues_key_and_commands_without_capturing_facade(setup):
     assert setup.repo.saves == []
 
 
-def test_unbound_facade_refuses_construction(compat):
-    with pytest.raises(RuntimeError, match="binding"):
-        compat.facade.VoiceFacade("a", "Fake:a", RecordingTasks())
+def test_facade_reads_its_engine_core_from_the_binding(setup, compat):
+    core = object()
+    binding = compat.facade.LegacyVoiceBinding(setup.store, setup.session, core)
+    voice = setup.cls(make_spec("Fake:b", "fr"), binding, setup.tasks)
+    assert voice.core is core and setup.voice.core is None
+    assert (voice.id, voice.name, voice.language) == ("b", "Fake:b", "fr")
+    assert "core" not in vars(voice) and not hasattr(setup.cls, "_runtime_binding")
diff --git a/tests/test_voice_settings_transaction.py b/tests/test_voice_settings_transaction.py
index 31d5e58..10b26c5 100644
--- a/tests/test_voice_settings_transaction.py
+++ b/tests/test_voice_settings_transaction.py
@@ -45,11 +45,8 @@ def _create_voices(monkeypatch, config):
 	config.conf["WorldVoice"]["voices"] = {}
 	config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"] = False
 	from voice_binding_harness import install_binding
-	install_binding(module, config)
-	return (
-		module.Voice("a", "A:a", None, "en"),
-		module.Voice("b", "B:b", None, "fr"),
-	)
+	voice = install_binding(module, config)
+	return voice("a", "A:a", "en"), voice("b", "B:b", "fr")
 
 
 def test_parameter_preview_is_undone_by_cancel(monkeypatch):
@@ -167,7 +164,7 @@ def _editing_panel(monkeypatch):
 
 def test_dialog_late_voice_is_restored_on_discard(monkeypatch):
 	panel, manager, a, b, config, _ = _editing_panel(monkeypatch)
-	late = manager.settings.ensure(a._binding.spec_for("Fake:late"))
+	late = manager.settings.ensure(type(a._state.spec)("late", "Fake:late", "Fake:late", "en", "Fake", "en"))
 	late.update(rate=81)
 	b.rate = 72  # A known state without a cached facade is in the same edit.
 	panel.onDiscard()
@@ -195,7 +192,7 @@ def test_apply_rebases_voice_and_role_edit_state(monkeypatch):
 
 def test_main_locale_voice_consistency_repeated_apply_then_discard(monkeypatch):
 	panel, manager, a, b, config, errors = _editing_panel(monkeypatch)
-	c = type(a)("c", "A:c", None, "en")
+	c = type(a)(type(a._state.spec)("c", "A:c", "A:c", "en", "A", "en"), a._binding, None)
 	voices = {voice.name: voice for voice in (a, b, c)}
 	manager.getVoiceInstance = voices.__getitem__
 	manager._voiceInfos = dict.fromkeys(voices)
diff --git a/tests/test_worldvoice_lifecycle.py b/tests/test_worldvoice_lifecycle.py
index 9cdb0cf..dce39e6 100644
--- a/tests/test_worldvoice_lifecycle.py
+++ b/tests/test_worldvoice_lifecycle.py
@@ -176,18 +176,17 @@ def test_voice_manager_closes_engine_when_no_voices(monkeypatch):
 
 	class Engine:
 		engine = "A"
-		core = None
 
 		@classmethod
-		def engineOn(cls):
-			cls.core = object()
+		def create_core(cls):
+			return object()
 
 		@classmethod
-		def voices(cls):
+		def voices(cls, core):
 			return []
 
 		@classmethod
-		def engineOff(cls):
+		def destroy_core(cls, core):
 			closed.append(cls.engine)
 
 	module = _load_voice_manager(monkeypatch, {"A": Engine})
@@ -208,7 +207,7 @@ def test_voice_manager_continues_cleanup_after_one_engine_fails(monkeypatch):
 		engine = "broken"
 
 		@classmethod
-		def engineOff(cls):
+		def close(cls):
 			closed.append("broken")
 			raise RuntimeError("failure while closing")
 
@@ -216,7 +215,7 @@ def test_voice_manager_continues_cleanup_after_one_engine_fails(monkeypatch):
 		engine = "other"
 
 		@classmethod
-		def engineOff(cls):
+		def close(cls):
 			closed.append("other")
 
 	module = _load_voice_manager(monkeypatch, {"broken": BrokenEngine, "other": OtherEngine})
@@ -226,10 +225,11 @@ def test_voice_manager_continues_cleanup_after_one_engine_fails(monkeypatch):
 	manager._instanceCache = {}
 	manager.installEngine = [BrokenEngine, OtherEngine]
 	manager._sessions = {}
+	manager._bindings = {}
 	manager.settings = types.SimpleNamespace(keys=lambda: ())
 	manager._bridge = types.SimpleNamespace(unbind=lambda source: None)
 	manager._resources = [
-		(object(), types.SimpleNamespace(close=cls.engineOff, source_id=object()), None, cls, True)
+		(object(), types.SimpleNamespace(close=cls.close, source_id=object()), None, cls, True)
 		for cls in (BrokenEngine, OtherEngine)
 	]
 	manager.terminate()
@@ -271,21 +271,20 @@ def test_bridge_unregisters_events_if_registration_fails(monkeypatch, failure):
 def test_drain_configuration_failure_rolls_back_previously_opened_engines(monkeypatch):
 	closed, bound = [], {}
 	class Engine:
-		core = session = None
 		@classmethod
-		def engineOn(cls):
-			cls.core = types.SimpleNamespace()
+		def create_core(cls):
+			core = types.SimpleNamespace()
 			if cls.engine == "first":
-				cls.core.speak_segment = lambda *args, **kwargs: None
+				core.speak_segment = lambda *args, **kwargs: None
+			return core
 		@classmethod
-		def engineOff(cls):
+		def destroy_core(cls, core):
 			closed.append(cls.engine)
-			cls.core = None
 		@classmethod
 		def supportedSettings(cls):
 			return []
 		@classmethod
-		def voices(cls):
+		def voices(cls, core):
 			return []
 	class First(Engine):
 		engine = "first"
@@ -305,7 +304,6 @@ def test_drain_configuration_failure_rolls_back_previously_opened_engines(monkey
 			completion_for=lambda cls, core: models.CompletionContract(
 				models.CompletionMode.DRAIN, models.IndexRange(1, 9999)))
 	assert closed == ["broken", "first"] and bound == {}
-	assert First.core is Broken.core is First.session is Broken.session is None
 
 
 @pytest.mark.parametrize("error", [RuntimeError("bridge failure"), KeyboardInterrupt()])
diff --git a/tests/test_worldvoice_request_builder.py b/tests/test_worldvoice_request_builder.py
index 3d562da..f3be0f5 100644
--- a/tests/test_worldvoice_request_builder.py
+++ b/tests/test_worldvoice_request_builder.py
@@ -98,17 +98,15 @@ def assembly(modules):
                 pass
 
         class Voice(modules.driver.Voice):
-            core = None
             synth_driver_class = Core
 
         Voice.engine = engine
         spec = modules.models.VoiceSpec(voice_id, key, key, "en", engine, "en")
         adapter = modules.adapter.LegacyEngineAdapter(Voice, voices.__getitem__)
         session = modules.session.EngineSession(adapter, store)
-        Voice._runtime_binding = modules.facade.LegacyVoiceBinding(store, session, lambda key: spec)
-        instance = Voice(voice_id, key, manager)
-        voices[key] = instance
         session.open()
+        instance = Voice(spec, modules.facade.LegacyVoiceBinding(store, session, adapter.core), manager)
+        voices[key] = instance
         ports[key] = session
         bridge.bind(adapter.notification_source, session.source_id)
         return instance
diff --git a/tests/voice_binding_harness.py b/tests/voice_binding_harness.py
index 4f6e6d2..f962439 100644
--- a/tests/voice_binding_harness.py
+++ b/tests/voice_binding_harness.py
@@ -6,6 +6,7 @@ from runtime_harness import FakeAdapter
 
 
 def install_binding(driver, config):
+    """Bind voices of *driver* to one settings store; returns a voice factory."""
     package = driver.__name__.rsplit(".", 1)[0]
     models = importlib.import_module(package + ".runtime.models")
     settings = importlib.import_module(package + ".runtime.settings")
@@ -13,18 +14,18 @@ def install_binding(driver, config):
     facade = importlib.import_module(package + ".compat.voiceFacade")
     repository = importlib.import_module(package + ".configRepository")
     store = settings.VoiceSettingsStore(repository.ConfigVoiceSettingsRepository(config.conf, lambda: "WorldVoice"))
+    session = sessions.EngineSession(FakeAdapter(), store)
+    binding = facade.LegacyVoiceBinding(store, session, None)
 
-    def spec_for(key):
-        engine, voice_id = key.split(":", 1)
-        language = "fr" if voice_id == "b" else "en"
-        return models.VoiceSpec(voice_id, key, key, language, engine, language)
+    def voice(voice_id, key, language):
+        engine = key.split(":", 1)[0]
+        return driver.Voice(models.VoiceSpec(voice_id, key, key, language, engine, language), binding, None)
 
-    session = sessions.EngineSession(FakeAdapter(), store)
-    driver.Voice._runtime_binding = facade.LegacyVoiceBinding(store, session, spec_for)
-    return store
+    return voice
 
 
 def bind_core(core, *voices):
+    """Rebind *voices* to a real adapter and session that own *core*."""
     voice_class = type(voices[0])
     package = voice_class.__module__.split(".driver")[0]
     adapters = importlib.import_module(package + ".compat.engineAdapter")
@@ -32,14 +33,12 @@ def bind_core(core, *voices):
     facade = importlib.import_module(package + ".compat.voiceFacade")
     old = voices[0]._binding
     by_name = {voice.name: voice for voice in voices}
-    voice_class.core = core
     voice_class.supportedSettings = classmethod(lambda cls: [setting.id for setting in core.supportedSettings])
+    voice_class.create_core = classmethod(lambda cls: core)
     adapter = adapters.LegacyEngineAdapter(voice_class, by_name.__getitem__)
     session = sessions.EngineSession(adapter, old.settings)
     session.open()
-    binding = facade.LegacyVoiceBinding(old.settings, session, old.spec_for)
-    voice_class._runtime_binding = binding
+    binding = facade.LegacyVoiceBinding(old.settings, session, core)
     for voice in voices:
         voice._binding = binding
-        voice.session = session
     return session
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests -q 2>&1 | grep -E "^FAILED|^ERROR tests|^[0-9]+ (passed|failed)" | sed 's/ - .*//' | cut -d: -f1 | sort | uniq -c | sort -rn`
Expected: the last line is `153 failed, 1183 passed, 83 errors`. Every failing file builds voices or adapters through `create_core`, `voices(core)`, `LegacyVoiceBinding(..., core)` or `VoiceFacade(spec, binding, taskManager)`, which do not exist yet:
- `test_runtime_composition.py` (74);
- `test_runtime_drain_integration.py` (30 errors, 3 failures);
- `test_runtime_legacy_adapter.py` (21 failures, 19 errors);
- `test_runtime_adapter_contract.py` (21 errors);
- `test_voice_settings_transaction.py` (13);
- `test_completion_characterization.py` (12);
- `test_f4_voice_state.py` (10);
- `test_worldvoice_request_builder.py` (9);
- `test_runtime_completion_policies.py` (8);
- `test_f4_engine_session.py` (7 errors);
- `test_runtime_voice_facade.py` (6 errors);
- `test_worldvoice_lifecycle.py` (2);
- `test_engine_interface_guards.py` (1).

- [ ] **Step 3: Move cores into adapters and bindings into constructors**

Save as `$PATCHES/t2-impl.patch`, then run `git apply $PATCHES/t2-impl.patch`:

```diff
diff --git a/addon/synthDrivers/WorldVoice/compat/engineAdapter.py b/addon/synthDrivers/WorldVoice/compat/engineAdapter.py
index 4c92510..de0806d 100644
--- a/addon/synthDrivers/WorldVoice/compat/engineAdapter.py
+++ b/addon/synthDrivers/WorldVoice/compat/engineAdapter.py
@@ -51,13 +51,11 @@ class LegacyEngineAdapter:
 		voice_class: type,
 		resolve_voice: Callable[[str], object],
 		*,
-		is_source_owned: Callable[[object], bool] | None = None,
 		index_ledger: IndexLedger | None = None,
 		completion: CompletionContract | None = None,
 	):
 		self._voice_class = voice_class
 		self._resolve_voice = resolve_voice
-		self._is_source_owned = is_source_owned
 		self._index_ledger = index_ledger
 		self._completion = completion or CompletionContract()
 		self._completion_configured = completion is not None
@@ -72,24 +70,14 @@ class LegacyEngineAdapter:
 	def open(self) -> None:
 		if self._opened:
 			return
-		# Claim cleanup before engineOn: it may acquire a core then raise.
+		# create_core either returns a core this adapter owns or raises without one.
+		self._core = self._voice_class.create_core()
+		self.notification_source = self._core
 		self._opened = True
-		try:
-			self._voice_class.engineOn()
-			self._core = self._voice_class.core
-			self.notification_source = self._core
-		except Exception as error:
-			try:
-				source = getattr(self._voice_class, "core", None)
-				if self._is_source_owned is not None and self._is_source_owned(source):
-					# engineOn may expose an existing owner's resource before
-					# failing. This alias must not release that owner's core.
-					self.detach_alias()
-				else:
-					self.close()
-			except Exception as cleanup_error:
-				raise error from cleanup_error
-			raise
+
+	@property
+	def core(self):
+		return self._core
 
 	def configure_completion(self, contract: CompletionContract) -> None:
 		"""Fix completion semantics for this opened resource before playback."""
@@ -125,27 +113,14 @@ class LegacyEngineAdapter:
 	def close(self) -> None:
 		if not self._opened:
 			return
-		self._opened = False
-		try:
-			self._voice_class.engineOff()
-		finally:
-			self._core = None
-			self.notification_source = None
-			self._segment_events = None
-			self._legacy_events = None
-			self._spoken = False
-
-	def detach_alias(self) -> None:
-		"""Relinquish a duplicate adapter without releasing the owner's core."""
+		core = self._core
 		self._opened = False
 		self._core = None
 		self.notification_source = None
 		self._segment_events = None
 		self._legacy_events = None
 		self._spoken = False
-		self._voice_class.core = None
-		self._voice_class.session = None
-		self._voice_class._runtime_binding = None
+		self._voice_class.destroy_core(core)
 
 	@property
 	def capabilities(self) -> EngineCapabilities:
@@ -160,7 +135,7 @@ class LegacyEngineAdapter:
 
 	def list_voices(self) -> tuple[VoiceSpec, ...]:
 		specs = []
-		for voice in self._voice_class.voices():
+		for voice in self._voice_class.voices(self._core):
 			try:
 				engine, voice_id, language = voice["engine"], voice["id"], voice["language"]
 				specs.append(
diff --git a/addon/synthDrivers/WorldVoice/compat/voiceFacade.py b/addon/synthDrivers/WorldVoice/compat/voiceFacade.py
index 7fddd48..b700eba 100644
--- a/addon/synthDrivers/WorldVoice/compat/voiceFacade.py
+++ b/addon/synthDrivers/WorldVoice/compat/voiceFacade.py
@@ -1,6 +1,5 @@
 """Legacy caller API backed by one runtime settings store and session."""
 
-from collections.abc import Callable
 from dataclasses import dataclass
 
 from ..runtime.models import VoiceSpec
@@ -10,9 +9,11 @@ from ..runtime.settings import VoiceSettingsStore
 
 @dataclass(frozen=True)
 class LegacyVoiceBinding:
+	"""One opened engine's settings, playback session and core."""
+
 	settings: VoiceSettingsStore
 	session: EngineSession
-	spec_for: Callable[[str], VoiceSpec]
+	core: object
 
 
 def _setting(name):
@@ -36,19 +37,18 @@ def _baseline(name):
 
 
 class VoiceFacade:
-	_runtime_binding: LegacyVoiceBinding | None = None
-
-	def __init__(self, id, name, taskManager, language=None):
-		binding = type(self)._runtime_binding
-		if binding is None:
-			raise RuntimeError("Voice requires a runtime binding")
+	def __init__(self, spec: VoiceSpec, binding: LegacyVoiceBinding, taskManager):
 		self._binding = binding
-		self._state = binding.settings.ensure(binding.spec_for(name))
+		self._state = binding.settings.ensure(spec)
 		self.id = self._state.spec.id
 		self.name = self._state.spec.name
 		self.language = self._state.spec.language
 		self.taskManager = taskManager
 
+	@property
+	def core(self):
+		return self._binding.core
+
 	rate = _setting("rate")
 	pitch = _setting("pitch")
 	volume = _setting("volume")
diff --git a/addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py b/addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py
index 50aab08..fc64e2f 100644
--- a/addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py
+++ b/addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py
@@ -918,7 +918,6 @@ CancellableSynthDriver = SynthDriver
 
 class Voice(Voice):
 	extra_capabilities = frozenset({"waitfactor", "variant"})
-	core = None
 	engine = "Cerence"
 	drain_profile = DrainProfile()
 	synth_driver_class = SynthDriver
@@ -960,13 +959,13 @@ class Voice(Voice):
 			return []
 
 	@classmethod
-	def voices(cls):
+	def voices(cls, core):
 		result = []
-		if not cls.ready() or not cls.core:
+		if not cls.ready() or not core:
 			return result
 
 		try:
-			voices = cls.core.availableVoices.values()
+			voices = core.availableVoices.values()
 		except Exception:
 			return result
 
diff --git a/addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py b/addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py
index ffac4ab..4fc686d 100644
--- a/addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py
+++ b/addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py
@@ -176,7 +176,6 @@ class SynthDriver(BaseSynthDriver):
 
 
 class Voice(Voice):
-	core = None
 	engine = "Espeak"
 	drain_profile = DrainProfile()
 	synth_driver_class = SynthDriver
diff --git a/addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py b/addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py
index d6a1a50..54f9ca1 100644
--- a/addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py
+++ b/addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py
@@ -23,7 +23,6 @@ SynthDriver = BaseOneCoreSynthDriver
 
 
 class Voice(Voice):
-	core = None
 	engine = "OneCore"
 	drain_profile = DrainProfile(wasapi_dependent=True)
 	synth_driver_class = SynthDriver
diff --git a/addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py b/addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py
index 09ea149..3c9bd3d 100644
--- a/addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py
+++ b/addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py
@@ -379,7 +379,6 @@ class SynthDriver(rhvoice.SynthDriver):
 
 
 class Voice(Voice):
-	core = None
 	engine = "RHVoice"
 	drain_profile = DrainProfile()
 	synth_driver_class = SynthDriver
diff --git a/addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py b/addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py
index f4ec28f..c7b289e 100644
--- a/addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py
+++ b/addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py
@@ -626,7 +626,6 @@ class SynthDriver(BaseSynthDriver):
 
 
 class Voice(Voice):
-	core = None
 	engine = "SAPI5"
 	drain_profile = DrainProfile(wasapi_dependent=True)
 
diff --git a/addon/synthDrivers/WorldVoice/driver/VE/__init__.py b/addon/synthDrivers/WorldVoice/driver/VE/__init__.py
index b272aaa..56efd21 100644
--- a/addon/synthDrivers/WorldVoice/driver/VE/__init__.py
+++ b/addon/synthDrivers/WorldVoice/driver/VE/__init__.py
@@ -909,7 +909,6 @@ CancellableSynthDriver = SynthDriver
 
 class Voice(Voice):
 	extra_capabilities = frozenset({"waitfactor", "variant"})
-	core = None
 	engine = "VE"
 	drain_profile = DrainProfile()
 	synth_driver_class = SynthDriver
@@ -948,13 +947,13 @@ class Voice(Voice):
 		]
 
 	@classmethod
-	def voices(cls):
+	def voices(cls, core):
 		result = []
-		if not cls.ready() or not cls.core:
+		if not cls.ready() or not core:
 			return result
 
 		try:
-			voices = cls.core.availableVoices.values()
+			voices = core.availableVoices.values()
 		except Exception:
 			return result
 
diff --git a/addon/synthDrivers/WorldVoice/driver/__init__.py b/addon/synthDrivers/WorldVoice/driver/__init__.py
index 2a76e85..b922eb2 100644
--- a/addon/synthDrivers/WorldVoice/driver/__init__.py
+++ b/addon/synthDrivers/WorldVoice/driver/__init__.py
@@ -11,8 +11,12 @@ def getVoiceKey(engine, voiceId):
 
 
 class Voice(VoiceFacade):
-	core = None
-	session = None
+	"""One engine's metadata and core factory; instances are bound voices.
+
+	The engine adapter owns the core: create_core either returns a working core
+	or raises without leaving one behind, and destroy_core releases it.
+	"""
+
 	engine = ""
 	synth_driver_class = None
 	extra_capabilities = frozenset()
@@ -45,13 +49,13 @@ class Voice(VoiceFacade):
 		}
 
 	@classmethod
-	def voices(cls):
+	def voices(cls, core):
 		result = []
-		if not cls.ready() or not cls.core:
+		if not cls.ready() or not core:
 			return result
 
 		try:
-			voices = cls.core.availableVoices.values()
+			voices = core.availableVoices.values()
 		except Exception:
 			return result
 
@@ -75,17 +79,11 @@ class Voice(VoiceFacade):
 		return True
 
 	@classmethod
-	def engineOn(cls):
-		if not cls.core:
-			cls.core = cls.synth_driver_class()
-			cls.core.wv = cls.engine
+	def create_core(cls):
+		core = cls.synth_driver_class()
+		core.wv = cls.engine
+		return core
 
 	@classmethod
-	def engineOff(cls):
-		try:
-			if cls.core:
-				cls.core.terminate()
-		finally:
-			cls.session = None
-			cls.core = None
-			cls._runtime_binding = None
+	def destroy_core(cls, core):
+		core.terminate()
diff --git a/addon/synthDrivers/WorldVoice/voiceManager.py b/addon/synthDrivers/WorldVoice/voiceManager.py
index e3f9acb..a4cd3ec 100644
--- a/addon/synthDrivers/WorldVoice/voiceManager.py
+++ b/addon/synthDrivers/WorldVoice/voiceManager.py
@@ -81,6 +81,7 @@ class VoiceManager(object):
 		self.installEngine = []
 		self._resources = []
 		self._sessions = {}
+		self._bindings = {}
 		self._specs = {}
 		self._instanceCache = {}
 		self._waitfactor = 0
@@ -107,51 +108,37 @@ class VoiceManager(object):
 				cls,
 				self.getVoiceInstance,
 				index_ledger=self._index_ledger,
-				is_source_owned=lambda source: any(resource[0] is source for resource in self._resources),
 			)
 			try:
 				adapter.open()
 			except Exception:
 				log.error("engine %s on error", eng.name, exc_info=True)
 				continue
+			session = EngineSession(adapter, self.settings)
 			# Retain identities (not equality) for the entire resource lifetime.
-			owner = next(
-				(resource for resource in self._resources if resource[0] is adapter.notification_source),
-				None,
-			)
-			if owner is not None:
-				session = owner[1]
-				self._resources.append((adapter.notification_source, session, adapter, cls, False))
-				completion = self._resource_completion(cls, adapter.notification_source)
-				if completion != session.completion:
-					raise ValueError("Aliases of one resource must share a completion contract")
-				adapter.configure_completion(session.completion)
-			else:
-				session = EngineSession(adapter, self.settings)
-				self._resources.append((adapter.notification_source, session, adapter, cls, True))
-				session.open()
-				completion = self._resource_completion(cls, adapter.notification_source)
-				adapter.configure_completion(completion)
-				# Claim ownership before binding, since bind may register then raise.
-				self._bridge.bind(adapter.notification_source, session.source_id, completion=completion)
-				if rule_for(completion).drain_event is not None:
-					adapter.configure_segment_events(
-						lambda context, source=adapter.notification_source: self._bridge.segment_sink(
-							source,
-							context,
-						),
-					)
-				elif completion.legacy_contextual:
-					adapter.configure_legacy_segment_events(
-						lambda context, source=adapter.notification_source: self._bridge.legacy_segment_sink(
-							source,
-							context,
-						),
-					)
-			cls.session = session
-			cls._runtime_binding = LegacyVoiceBinding(self.settings, session, self.getVoiceSpec)
+			self._resources.append((adapter.notification_source, session, adapter, cls, True))
+			session.open()
+			completion = self._resource_completion(cls, adapter.notification_source)
+			adapter.configure_completion(completion)
+			# Claim ownership before binding, since bind may register then raise.
+			self._bridge.bind(adapter.notification_source, session.source_id, completion=completion)
+			if rule_for(completion).drain_event is not None:
+				adapter.configure_segment_events(
+					lambda context, source=adapter.notification_source: self._bridge.segment_sink(
+						source,
+						context,
+					),
+				)
+			elif completion.legacy_contextual:
+				adapter.configure_legacy_segment_events(
+					lambda context, source=adapter.notification_source: self._bridge.legacy_segment_sink(
+						source,
+						context,
+					),
+				)
 			# Only bound, operational resources become visible to resolvers.
 			self._sessions[eng.name] = session
+			self._bindings[eng.name] = LegacyVoiceBinding(self.settings, session, adapter.core)
 			self.installEngine.append(cls)
 			for spec in adapter.list_voices():
 				self._specs[spec.name] = spec
@@ -174,6 +161,7 @@ class VoiceManager(object):
 		self._terminated = True
 		# Stop publication before releasing any resources.
 		self._sessions.clear()
+		self._bindings.clear()
 		if commit:
 			for key in self.settings.keys():
 				try:
@@ -182,23 +170,14 @@ class VoiceManager(object):
 					log.error("Failed to save voice %s", key, exc_info=True)
 		self._instanceCache.clear()
 		for source, session, adapter, cls, owns in reversed(self._resources):
-			if owns:
-				try:
-					self._bridge.unbind(session.source_id)
-				except Exception:
-					log.error("Failed to unbind engine %s", cls.engine, exc_info=True)
-				try:
-					session.close()
-				except Exception:
-					log.error("Failed to close engine %s", cls.engine, exc_info=True)
-				finally:
-					cls.session = None
-					cls._runtime_binding = None
-			else:
-				try:
-					adapter.detach_alias()
-				except Exception:
-					log.error("Failed to detach engine alias %s", cls.engine, exc_info=True)
+			try:
+				self._bridge.unbind(session.source_id)
+			except Exception:
+				log.error("Failed to unbind engine %s", cls.engine, exc_info=True)
+			try:
+				session.close()
+			except Exception:
+				log.error("Failed to close engine %s", cls.engine, exc_info=True)
 		self._resources.clear()
 		self.installEngine.clear()
 		self.taskManager = None
@@ -270,13 +249,7 @@ class VoiceManager(object):
 		spec = self.getVoiceSpec(voiceName)
 		cls = READY_ENGINE_CLASS[spec.engine]
 		self.settings.ensure(spec)
-		voiceInstance = cls(
-			id=spec.id,
-			name=spec.name,
-			language=spec.language,
-			taskManager=self.taskManager,
-		)
-		voiceInstance.session = self._sessions[spec.engine]
+		voiceInstance = cls(spec, self._bindings[spec.engine], self.taskManager)
 		self._instanceCache[voiceName] = voiceInstance
 		return voiceInstance
 
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests -q 2>&1 | tail -1; ruff format --check addon | tail -1`
Expected: `1419 passed`, then `54 files already formatted`.

- [ ] **Step 5: Commit**

```bash
git add addon/synthDrivers/WorldVoice/driver/__init__.py \
	addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py \
	addon/synthDrivers/WorldVoice/driver/VE/__init__.py addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py \
	addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py \
	addon/synthDrivers/WorldVoice/compat/voiceFacade.py addon/synthDrivers/WorldVoice/compat/engineAdapter.py \
	addon/synthDrivers/WorldVoice/voiceManager.py \
	tests/test_engine_interface_guards.py tests/voice_binding_harness.py tests/runtime_harness.py \
	tests/runtime_drain_integration_harness.py tests/test_runtime_legacy_adapter.py tests/test_runtime_composition.py \
	tests/test_runtime_completion_policies.py tests/test_f4_voice_state.py tests/test_voice_settings_transaction.py \
	tests/test_f4_engine_session.py tests/test_runtime_voice_facade.py tests/test_worldvoice_request_builder.py \
	tests/test_worldvoice_lifecycle.py tests/test_f4_engine_adapters.py
git commit -m "refactor(compat): engines create cores for their adapter and voices get their binding

Voice classes no longer hold core, session or runtime binding as class
attributes: create_core/destroy_core replace engineOn/engineOff, the
adapter owns the core, and VoiceFacade receives (spec, binding,
taskManager). Two engines can no longer share one core, so the alias
machinery is removed.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Prove the binding is pinned (mutations M2a–M2d, after the commit)**

```bash
mutate() { python3 - "$1" "$2" "$3" <<'PY'
import sys
p, old, new = sys.argv[1:]
s = open(p).read()
assert s.count(old) == 1, old
open(p, "w").write(s.replace(old, new))
PY
}
A=addon/synthDrivers/WorldVoice
check() { timeout 600 python3 -m pytest tests -q -p no:cacheprovider 2>&1 | grep -E '^[0-9]+ (passed|failed)' | sed 's/ in .*//'; git checkout -- addon; }

echo M2a; mutate $A/compat/engineAdapter.py '		self._voice_class.destroy_core(core)' '		pass'; check
echo M2b; mutate $A/compat/voiceFacade.py '		return self._binding.core' '		return None'; check
echo M2c; mutate $A/compat/engineAdapter.py '		for voice in self._voice_class.voices(self._core):' '		for voice in self._voice_class.voices(None):'; check
echo M2d; mutate $A/driver/__init__.py '		core.wv = cls.engine
		return core' '		core.wv = cls.engine
		cls.core = core
		return core'; check
git status --short | grep addon
```

Expected (full-suite counts):
- M2a: `close()` never destroys the core. `17 failed, 1402 passed`.
- M2b: the facade's `core` returns None. `7 failed, 1412 passed`.
- M2c: `list_voices` passes no core. `84 failed, 1305 passed, 30 errors`.
- M2d: `create_core` writes `cls.core` again. `2 failed, 1417 passed` (the guard plus `test_engine_core_factory_keeps_no_class_state`).

The final `git status` prints nothing.

---

### Task 3: EngineResource and the split VoiceManager initialization

Spec §4.

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/voiceManager.py`:
  - `EngineResource`;
  - `_open_engine`/`_bind`/`_publish`;
  - `terminate` over resources;
  - delete `installEngine`.
- Test: `tests/test_runtime_composition.py` (`test_each_opened_engine_is_one_engine_resource`)
- Test: `tests/test_worldvoice_lifecycle.py` (`test_voice_manager_continues_cleanup_after_one_engine_fails` builds `EngineResource` values)

**Interfaces:**
- Consumes: Task 2's `LegacyVoiceBinding`, `LegacyEngineAdapter.core`, `_bindings`.
- Produces: `voiceManager.EngineResource(engine, voice_class, adapter, session, binding)` and `VoiceManager._resources: list[EngineResource]`.

- [ ] **Step 1: Write the resource tests**

Save as `$PATCHES/t3-tests.patch`, then run `git apply $PATCHES/t3-tests.patch`:

```diff
diff --git a/tests/test_runtime_composition.py b/tests/test_runtime_composition.py
index 089f53d..b86e269 100644
--- a/tests/test_runtime_composition.py
+++ b/tests/test_runtime_composition.py
@@ -123,6 +123,22 @@ def test_only_started_sessions_are_resolvable(composition):
     assert c.repo.saves == []
 
 
+def test_each_opened_engine_is_one_engine_resource(composition):
+    c = composition
+    classes = c.engine("first"), c.engine("second")
+    c.engine("failed", fail=True)
+    manager = c.create()
+    assert [resource.engine for resource in manager._resources] == ["first", "second"]
+    for resource, cls in zip(manager._resources, classes):
+        assert resource.voice_class is cls
+        assert resource.adapter.core is cls.opened is resource.binding.core
+        assert resource.session is resource.binding.session is manager.resolve_playback(cls.engine + ":a")
+        assert manager.getVoiceInstance(cls.engine + ":a")._binding is resource.binding
+    assert not hasattr(manager, "installEngine")
+    manager.terminate(commit=False)
+    assert manager._resources == [] and [cls.opened for cls in classes] == [None, None]
+
+
 @pytest.mark.parametrize("failure", ["empty", "bind"])
 def test_initialization_failure_closes_without_commit(composition, failure):
     c = composition
diff --git a/tests/test_worldvoice_lifecycle.py b/tests/test_worldvoice_lifecycle.py
index dce39e6..667d7b7 100644
--- a/tests/test_worldvoice_lifecycle.py
+++ b/tests/test_worldvoice_lifecycle.py
@@ -223,13 +223,12 @@ def test_voice_manager_continues_cleanup_after_one_engine_fails(monkeypatch):
 	manager.taskManager = object()
 	manager._terminated = False
 	manager._instanceCache = {}
-	manager.installEngine = [BrokenEngine, OtherEngine]
 	manager._sessions = {}
 	manager._bindings = {}
 	manager.settings = types.SimpleNamespace(keys=lambda: ())
 	manager._bridge = types.SimpleNamespace(unbind=lambda source: None)
 	manager._resources = [
-		(object(), types.SimpleNamespace(close=cls.close, source_id=object()), None, cls, True)
+		module.EngineResource(cls.engine, cls, None, types.SimpleNamespace(close=cls.close, source_id=object()), None)
 		for cls in (BrokenEngine, OtherEngine)
 	]
 	manager.terminate()
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests -q 2>&1 | grep -E "^FAILED|^[0-9]+ (passed|failed)" | sed 's/ - .*//'`
Expected: `2 failed, 1418 passed`:
- `tests/test_worldvoice_lifecycle.py::test_voice_manager_continues_cleanup_after_one_engine_fails`: there is no `EngineResource` yet.
- `tests/test_runtime_composition.py::test_each_opened_engine_is_one_engine_resource`: the resources are still tuples.

- [ ] **Step 3: Introduce EngineResource and split `_initialize`**

Save as `$PATCHES/t3-impl.patch`, then run `git apply $PATCHES/t3-impl.patch`:

```diff
diff --git a/addon/synthDrivers/WorldVoice/voiceManager.py b/addon/synthDrivers/WorldVoice/voiceManager.py
index a4cd3ec..1fd374e 100644
--- a/addon/synthDrivers/WorldVoice/voiceManager.py
+++ b/addon/synthDrivers/WorldVoice/voiceManager.py
@@ -1,6 +1,6 @@
 from collections import OrderedDict, defaultdict
 from collections.abc import Mapping
-from dataclasses import replace
+from dataclasses import dataclass, replace
 from operator import attrgetter
 from typing import Callable, TypeVar, Dict, List
 import re
@@ -22,6 +22,18 @@ from .nvdaEventBridge import NvdaEventBridge
 
 from .engine import EngineType, READY_ENGINE_CLASS, get_engine_enabled, refresh_ready_engine_classes
 
+
+@dataclass
+class EngineResource:
+	"""One opened engine: its adapter, playback session and voice binding."""
+
+	engine: str
+	voice_class: type
+	adapter: LegacyEngineAdapter
+	session: EngineSession
+	binding: LegacyVoiceBinding
+
+
 T = TypeVar("T")
 K = TypeVar("K")
 V = TypeVar("V")
@@ -78,8 +90,7 @@ class VoiceManager(object):
 		self._bridge = bridge
 		self._index_ledger = index_ledger
 		self._completion_for = completion_for
-		self.installEngine = []
-		self._resources = []
+		self._resources: list[EngineResource] = []
 		self._sessions = {}
 		self._bindings = {}
 		self._specs = {}
@@ -104,49 +115,54 @@ class VoiceManager(object):
 			cls = READY_ENGINE_CLASS.get(eng.name)
 			if cls is None:
 				continue
-			adapter = LegacyEngineAdapter(
-				cls,
-				self.getVoiceInstance,
-				index_ledger=self._index_ledger,
-			)
-			try:
-				adapter.open()
-			except Exception:
-				log.error("engine %s on error", eng.name, exc_info=True)
+			resource = self._open_engine(eng.name, cls)
+			if resource is None:
 				continue
-			session = EngineSession(adapter, self.settings)
-			# Retain identities (not equality) for the entire resource lifetime.
-			self._resources.append((adapter.notification_source, session, adapter, cls, True))
-			session.open()
-			completion = self._resource_completion(cls, adapter.notification_source)
-			adapter.configure_completion(completion)
-			# Claim ownership before binding, since bind may register then raise.
-			self._bridge.bind(adapter.notification_source, session.source_id, completion=completion)
-			if rule_for(completion).drain_event is not None:
-				adapter.configure_segment_events(
-					lambda context, source=adapter.notification_source: self._bridge.segment_sink(
-						source,
-						context,
-					),
-				)
-			elif completion.legacy_contextual:
-				adapter.configure_legacy_segment_events(
-					lambda context, source=adapter.notification_source: self._bridge.legacy_segment_sink(
-						source,
-						context,
-					),
-				)
-			# Only bound, operational resources become visible to resolvers.
-			self._sessions[eng.name] = session
-			self._bindings[eng.name] = LegacyVoiceBinding(self.settings, session, adapter.core)
-			self.installEngine.append(cls)
-			for spec in adapter.list_voices():
-				self._specs[spec.name] = spec
+			self._bind(resource)
+			self._publish(resource)
 		self._setVoiceDatas()
 		if not self.table:
 			raise RuntimeError("No WorldVoice voices are available from enabled speech engines.")
 		self._defaultVoiceInstance = self.getVoiceInstance(self._getDefaultVoiceMeta().name)
 
+	def _open_engine(self, name: str, cls: type) -> EngineResource | None:
+		adapter = LegacyEngineAdapter(cls, self.getVoiceInstance, index_ledger=self._index_ledger)
+		try:
+			adapter.open()
+		except Exception:
+			log.error("engine %s on error", name, exc_info=True)
+			return None
+		session = EngineSession(adapter, self.settings)
+		binding = LegacyVoiceBinding(self.settings, session, adapter.core)
+		resource = EngineResource(name, cls, adapter, session, binding)
+		# Claim cleanup before opening: every later step may fail.
+		self._resources.append(resource)
+		session.open()
+		return resource
+
+	def _bind(self, resource: EngineResource) -> None:
+		adapter, session = resource.adapter, resource.session
+		source = adapter.notification_source
+		completion = self._resource_completion(resource.voice_class, source)
+		adapter.configure_completion(completion)
+		# Claim ownership before binding, since bind may register then raise.
+		self._bridge.bind(source, session.source_id, completion=completion)
+		if rule_for(completion).drain_event is not None:
+			adapter.configure_segment_events(
+				lambda context: self._bridge.segment_sink(source, context),
+			)
+		elif completion.legacy_contextual:
+			adapter.configure_legacy_segment_events(
+				lambda context: self._bridge.legacy_segment_sink(source, context),
+			)
+
+	def _publish(self, resource: EngineResource) -> None:
+		# Only bound, operational resources become visible to resolvers.
+		self._sessions[resource.engine] = resource.session
+		self._bindings[resource.engine] = resource.binding
+		for spec in resource.adapter.list_voices():
+			self._specs[spec.name] = spec
+
 	def _resource_completion(self, cls, source):
 		completion = self._completion_for(cls, source)
 		if completion.mode is CompletionMode.LEGACY_DONE and callable(
@@ -169,17 +185,17 @@ class VoiceManager(object):
 				except Exception:
 					log.error("Failed to save voice %s", key, exc_info=True)
 		self._instanceCache.clear()
-		for source, session, adapter, cls, owns in reversed(self._resources):
+		for resource in reversed(self._resources):
+			engine = resource.voice_class.engine
 			try:
-				self._bridge.unbind(session.source_id)
+				self._bridge.unbind(resource.session.source_id)
 			except Exception:
-				log.error("Failed to unbind engine %s", cls.engine, exc_info=True)
+				log.error("Failed to unbind engine %s", engine, exc_info=True)
 			try:
-				session.close()
+				resource.session.close()
 			except Exception:
-				log.error("Failed to close engine %s", cls.engine, exc_info=True)
+				log.error("Failed to close engine %s", engine, exc_info=True)
 		self._resources.clear()
-		self.installEngine.clear()
 		self.taskManager = None
 
 	def resolve_playback(self, key: str) -> PlaybackPort | None:
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests -q 2>&1 | tail -1; ruff format --check addon/synthDrivers/WorldVoice/voiceManager.py; grep -n "installEngine" addon/synthDrivers/WorldVoice/voiceManager.py`
Expected: `1420 passed`, then `1 file already formatted`, then no grep output.

- [ ] **Step 5: Commit**

```bash
git add addon/synthDrivers/WorldVoice/voiceManager.py tests/test_runtime_composition.py tests/test_worldvoice_lifecycle.py
git commit -m "refactor(voiceManager): track each opened engine as an EngineResource

The five-field resource tuple becomes a dataclass, and _initialize opens,
binds and publishes each engine through _open_engine, _bind and _publish.
The write-only installEngine list is removed.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Prove the resources are pinned (mutations M3a–M3b, after the commit)**

```bash
mutate() { python3 - "$1" "$2" "$3" <<'PY'
import sys
p, old, new = sys.argv[1:]
s = open(p).read()
assert s.count(old) == 1, old
open(p, "w").write(s.replace(old, new))
PY
}
A=addon/synthDrivers/WorldVoice
check() { timeout 600 python3 -m pytest tests -q -p no:cacheprovider 2>&1 | grep -E '^[0-9]+ (passed|failed)' | sed 's/ in .*//'; git checkout -- addon; }

echo M3a; mutate $A/voiceManager.py '		self._bindings[resource.engine] = resource.binding' '		pass'; check
echo M3b; mutate $A/voiceManager.py '		binding = LegacyVoiceBinding(self.settings, session, adapter.core)' '		binding = LegacyVoiceBinding(self.settings, session, None)'; check
git status --short | grep addon
```

Expected (full-suite counts):
- M3a: `_publish` forgets the binding. `84 failed, 1306 passed, 30 errors`.
- M3b: the resource's binding carries no core. `1 failed, 1419 passed` (`test_each_opened_engine_is_one_engine_resource`).

The final `git status` prints nothing.

Moving `self._resources.append(resource)` after `session.open()` is an equivalent mutant. `adapter.open()` already ran, so `session.open()` cannot fail there, and the master code had the same order. No test can tell the two apart, so it is not listed.

---

### Task 4: Final verification

**Files:** none modified.

- [ ] **Step 1: Stability**

Run: `for i in 1 2 3 4 5; do python3 -m pytest tests/test_runtime_composition.py tests/test_runtime_completion_policies.py tests/test_runtime_legacy_adapter.py tests/test_runtime_voice_facade.py tests/test_f4_voice_state.py tests/test_f4_engine_session.py tests/test_worldvoice_lifecycle.py tests/test_worldvoice_request_builder.py tests/test_runtime_drain_integration.py tests/test_engine_interface_guards.py tests/test_voice_settings_transaction.py -q 2>&1 | tail -1; done | sed 's/ in .*//' | sort | uniq -c`
Expected: one line, `5 366 passed`.

Run: `for i in $(seq 1 20); do python3 -m pytest tests/test_vocalizer_segment_drain.py tests/test_worldvoice_cancel_wrappers.py -q 2>&1 | tail -1; done | sed 's/ in .*//' | sort | uniq -c`
Expected: one line, `20 233 passed`.

- [ ] **Step 2: Scope**

Run:
```bash
git diff master --stat -- 'addon/synthDrivers/WorldVoice/driver/*/driver'
git diff master -U0 -- 'addon/synthDrivers/WorldVoice/driver/*/__init__.py' | grep '^[-+]' | grep -v '^+++\|^---' | sort | uniq -c
git ls-files addon/synthDrivers/WorldVoice/driver/Neural
ruff format --check addon | tail -1
```
Expected:
- No output from the first command.
- The second lists only these line pairs (counts in front):
  - the six `from ...runtime.playbackWork import` lines gaining `DrainProfile`;
  - six `-	core = None`;
  - four `+	drain_profile = DrainProfile()` and two `+	drain_profile = DrainProfile(wasapi_dependent=True)`;
  - for VE and Cerence, `def voices(cls)` → `def voices(cls, core)` and the two `cls.core` → `core` reads.
- No output from `ls-files`, then `54 files already formatted`.

- [ ] **Step 3: Full suite and history**

Run: `python3 -m pytest tests -q 2>&1 | tail -1; git log --oneline master..HEAD`
Expected: `1420 passed`. The log lists, oldest at the bottom:
1. `docs: add phase 5 voice binding design spec`
2. `docs: add phase 5 implementation plan and amend its spec`
3. `refactor(compat): select completion from declared drain profiles`
4. `refactor(compat): engines create cores for their adapter and voices get their binding`
5. `refactor(voiceManager): track each opened engine as an EngineResource`
