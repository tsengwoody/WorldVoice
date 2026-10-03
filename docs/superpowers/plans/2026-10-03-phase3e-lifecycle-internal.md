# Phase 3e: SegmentLifecycle Internal to SegmentHost Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- Make `SegmentLifecycle` a private module that only `SegmentHost` imports.
- Delete the wrapper-era lifecycle API and `CallbackGate`.
- Remove the Neural tests, and leave the suite with no skipped tests.

**Architecture:**
- **Task 1** removes every Neural test dependency:
  - It deletes `test_neural_segment_drain.py` and `neural_drain_harness.py`, plus the Neural parameters, adapter and harness branches in other files.
  - It also deletes 6 Neural-only scheduler integration tests. One is covered by an existing scheduler test; five need the contextual legacy mode that only Neural implemented, a gap the spec records.
  - It ports the voice-switch test to VE, using a second harness VE voice.
- **Task 2** is a test-only cleanup now that every engine runs on `SegmentHost`:
  - drops the "no host, read `_segmentLifecycle`" fallbacks;
  - merges the two VE/Cerence twin tests;
  - drops the SAPI5 `stranded` scaffolding.
- **Task 3** does the internalization:
  - adds guard tests first;
  - `git mv runtime/segmentLifecycle.py runtime/_segmentLifecycle.py`;
  - deletes `is_resource_busy`, `reject_pending`, `SegmentOperation.sink/has_started/is_retired`, and `CallbackGate`/`CallbackLease`/`_NativeCall`;
  - points tests at the new module.

**Tech Stack:** Python 3 threading, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-10-03-phase3e-lifecycle-internal-design.md`

## Global Constraints

- Work on branch `phase3e-lifecycle-internal`, cut from `master` at `f2a4309`. The spec commit `4aa979f` and the plan commit are on it.
- **Do not change** anything under `addon/synthDrivers/WorldVoice/driver/`: wrappers and inner drivers stay byte-identical.
- In `runtime/`, change only:
  - `segmentHost.py`: the one import line;
  - `_segmentLifecycle.py`: renamed, with deletions and a docstring line only;
  - `playbackWork.py`: deletions and its docstring only.
- Do not change `compat/completionPolicies.DRAIN_ENGINES`. Leave tests that only use "Neural" as an engine name.
- Never commit `driver/Neural/`. Neural compatibility is not required. `storage/Neural-snapshot-2026-10-01.zip` stays.
- New public names are snake_case.
- Every changed `addon/` file passes `ruff format --check`.
- Run from the repo root, since tests need the untracked `ref/`. Stage explicit paths only, and never stage the user's unstaged deletion of `docs/superpowers/finish_task.md`. Never touch `git stash`.
- Baseline before Task 1: `python3 -m pytest tests -q` → `1377 passed, 89 skipped`.
- Each code step applies a patch saved verbatim from this plan. Set `PATCHES=$(mktemp -d)` once, save the block to the named file, then run `git apply`.
- **Mutation steps come after the commit step.** They end with `git checkout -- addon`, which would otherwise discard uncommitted work.
- Every commit message ends with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **The contextual legacy coverage gap.**
   - Five deleted integration tests drove `speak_legacy_segment` through a real engine. Only Neural ever implemented it.
   - Check that no in-repo engine defines `speak_legacy_segment`, so `VoiceManager._resource_completion` never sets `legacy_contextual` for them.
   - Check that the remaining unit tests cover the scheduler, bridge and adapter contracts those tests relied on:
     - `test_runtime_legacy_adapter.py`: 4 contextual tests;
     - `test_nvda_event_bridge.py`: 2;
     - `test_runtime_scheduler.py::test_contextual_legacy_completion_requires_exact_segment_identity`.
2. **`reject_pending` → `fail` in `test_segment_lifecycle.py`.**
   - Five tests used `reject_pending` to reject an accepted, unstarted operation. They now call `fail()`.
   - For an unstarted operation, `fail()` sets the error and calls `_reject_pending_locked` under the condition, which is the path the host uses.
   - Check that no test lost the "pending" precondition, for example by now failing an operation that already runs.
3. **The second harness VE voice.**
   - `runtime_drain_integration_harness.assemble` now makes VE list `fake` and `fake2`.
   - Check that no integration or completion-policy test silently depends on VE having one voice. `c.key("VE")` returns the first spec, `VE:fake`.
4. **Deleted lifecycle API.**
   - `is_resource_busy`, the public `reject_pending`, and `SegmentOperation.sink/has_started/is_retired` had no addon callers.
   - Check `segmentHost.py`, `scheduler.py`, `compat/` and `nvdaEventBridge.py` for indirect use (`getattr`, duck typing).
   - Check that `_reject_pending_locked`, `wake_waiters` and `close_admission` remain, because the lifecycle itself uses them.
5. **Merged twin tests.**
   - VE now also runs Cerence's extra assertion that callback admission stays closed after the successor retires, in `test_shared_cancel_retires_guarded_feed_before_successor`.
   - Check that this assertion is meaningful for VE and not passing vacuously. `env.opened[0][1]` is the first opened instance.

---

### Task 1: Remove the Neural tests and port the voice-switch test to VE

Spec §2.1 and §2.2.

**Files:**
- Delete: `tests/test_neural_segment_drain.py`, `tests/neural_drain_harness.py`
- Modify: `tests/runtime_drain_integration_harness.py`:
  - drop the Neural imports, `ENGINES` entry and branches;
  - give VE a second voice.
- Modify: `tests/test_runtime_drain_integration.py`:
  - drop the Neural parameters and branches;
  - delete 6 Neural-only tests;
  - port `test_voice_switch_reapplies_native_settings_and_keeps_distinct_drains` to VE.
- Modify: `tests/test_runtime_completion_policies.py` (`SEVEN_ENGINES` → `SIX_ENGINES`)
- Modify: `tests/test_engine_segment_contract.py` and `tests/engine_contract_harness.py` (drop `NeuralAdapter`)
- Modify: `tests/test_lifecycle_private_access.py` (drop the `neural_` prefix)

**Interfaces:**
- Consumes: nothing new. `onecore_drain_harness.in_thread` already exists and is what the integration harness uses.
- Produces:
  - `runtime_drain_integration_harness.ENGINES == ("OneCore", "VE", "Cerence")`.
  - VE specs `VE:fake` and `VE:fake2` in the integration composition.
  - `SIX_ENGINES` in `test_runtime_completion_policies.py`.

- [ ] **Step 1: Delete the Neural test files**

Run: `git rm -q tests/test_neural_segment_drain.py tests/neural_drain_harness.py`

- [ ] **Step 2: Remove Neural from the other tests and port the voice-switch test**

Save as `$PATCHES/t1.patch`, then run `git apply $PATCHES/t1.patch`:

```diff
diff --git a/tests/engine_contract_harness.py b/tests/engine_contract_harness.py
index 9e67df9..87e89a7 100644
--- a/tests/engine_contract_harness.py
+++ b/tests/engine_contract_harness.py
@@ -11,7 +11,6 @@ from threading import Event
 
 from espeak_drain_harness import finish as finish_espeak
 from espeak_drain_harness import load_espeak
-from neural_drain_harness import load_neural
 from onecore_drain_harness import in_thread, load_onecore
 from rhvoice_drain_harness import finish as finish_rhvoice
 from rhvoice_drain_harness import load_rhvoice
@@ -141,31 +140,6 @@ class OneCoreAdapter(_Adapter):
 		self.core.terminate()
 
 
-class NeuralAdapter(_Adapter):
-	engine = "Neural"
-
-	def open(self, monkeypatch, tmp_path):
-		_fresh_lifecycle_module(monkeypatch)
-		env = load_neural(monkeypatch, tmp_path)
-		self.bind(env, env.driver)
-
-	def complete(self):
-		self.env.native.wait_calls(1)
-		self.env.native.speak_release.set()
-		self.env.player.idle_release.set()
-
-	def native_call_count(self):
-		return len(self.env.native.calls)
-
-	def close(self):
-		self.env.native.speak_release.set()
-		self.env.native.stop_release.set()
-		self.env.player.feed_release.set()
-		self.env.player.idle_release.set()
-		self.env.player.stop_release.set()
-		self.core.terminate()
-
-
 class _NuanceAdapter(_Adapter):
 	def open(self, monkeypatch, tmp_path):
 		_fresh_lifecycle_module(monkeypatch)
diff --git a/tests/runtime_drain_integration_harness.py b/tests/runtime_drain_integration_harness.py
index fef8997..3114313 100644
--- a/tests/runtime_drain_integration_harness.py
+++ b/tests/runtime_drain_integration_harness.py
@@ -9,7 +9,6 @@ import sys
 from threading import Condition, Event
 from types import ModuleType, SimpleNamespace
 
-from neural_drain_harness import NEURAL_AVAILABLE, load_neural
 from onecore_drain_harness import ROOT, in_thread, load_onecore
 from runtime_harness import MemoryRepository, load_runtime, load_scheduler
 from test_vocalizer_segment_drain import emit
@@ -18,8 +17,7 @@ from worldvoice_cancel_wrapper_harness import load_real_driver_with_native_stubs
 
 
 PACKAGE = "synthDrivers.WorldVoice"
-# Neural joins the composition only when its untracked driver is present.
-ENGINES = ("OneCore", "Neural", "VE", "Cerence") if NEURAL_AVAILABLE else ("OneCore", "VE", "Cerence")
+ENGINES = ("OneCore", "VE", "Cerence")
 
 
 class NativeCall:
@@ -41,8 +39,8 @@ class AudioBarrier:
 class EngineControl:
     def __init__(self, env, engine, monkeypatch):
         self.env, self.engine = env, engine
-        self.core = env.driver if engine in ("OneCore", "Neural") else env.core
-        self.player = env.player if engine in ("OneCore", "Neural") else self.core._real_player
+        self.core = env.driver if engine == "OneCore" else env.core
+        self.player = env.player if engine == "OneCore" else self.core._real_player
         self.condition = Condition()
         self.started = Event()
         self.calls, self.contexts, self.commands, self.sinks, self.applied = [], [], [], [], []
@@ -98,17 +96,6 @@ class EngineControl:
                 self._start(token, text)
 
             monkeypatch.setattr(env.native.ocSpeech_speak, "function", speak)
-        elif engine == "Neural":
-            def speak(handle, text, size, pointer):
-                with env.native.condition:
-                    env.native.calls.append((handle, text.decode()))
-                    env.native.condition.notify_all()
-                call = self._start(handle, text.decode())
-                assert call.release.wait(4), "Neural native result was never released"
-                pointer[0] = env.native.result
-                return 0
-
-            monkeypatch.setattr(env.native, "synthesizer_speak_ssml", speak)
         else:
             def speak(instance, text):
                 call = self._start(instance, text)
@@ -153,16 +140,6 @@ class EngineControl:
             callback = in_thread(lambda: self.env.native.respond(frames=frames, markers=markers))
             call.callback = callback
             self.callbacks.append(callback)
-        elif self.engine == "Neural":
-            def respond():
-                self.env.native.audio(b"pcm-tail", synth=call.instance)
-                for command in call.commands:
-                    if isinstance(command, self.env.commands.IndexCommand):
-                        self.env.native.bookmark(str(command.index))
-                call.release.set()
-            callback = in_thread(respond)
-            call.callback = callback
-            self.callbacks.append(callback)
         else:
             call.release.set()
         return call
@@ -185,9 +162,6 @@ class EngineControl:
             barrier.release.set()
         if self.engine == "OneCore":
             self.env.player.sync_release.set()
-        if self.engine == "Neural":
-            self.env.native.speak_release.set()
-            self.env.native.stop_release.set()
 
 
 def assemble(monkeypatch, tmp_path, *, supported=True):
@@ -236,9 +210,6 @@ def assemble(monkeypatch, tmp_path, *, supported=True):
     controls = {}
     controls["OneCore"] = EngineControl(load_onecore(
         monkeypatch, rt=rt, scheduler=scheduler, voice_base=voice_base, commands=commands), "OneCore", monkeypatch)
-    if NEURAL_AVAILABLE:
-        controls["Neural"] = EngineControl(load_neural(monkeypatch, tmp_path, rt=rt, scheduler=scheduler,
-            voice_base=voice_base, commands=commands), "Neural", monkeypatch)
     for engine in ("VE", "Cerence"):
         env = load_real_driver_with_native_stubs(monkeypatch, engine, rt=rt,
             voice_base=voice_base, commands=commands, property_setters=True)
@@ -257,6 +228,10 @@ def assemble(monkeypatch, tmp_path, *, supported=True):
         monkeypatch.setattr(env.native, "getParamList", get_params)
         monkeypatch.setattr(env.native, "setParamList", set_params)
         monkeypatch.setattr(env.native, "getSpeechDBList", lambda *args: ["default"])
+        if engine == "VE":
+            # A second VE voice lets a request switch voices within one engine.
+            monkeypatch.setattr(env.native, "getVoiceList", lambda language: [
+                SimpleNamespace(szVoiceName=b"fake"), SimpleNamespace(szVoiceName=b"fake2")])
         monkeypatch.setattr(env.native, "close", lambda *args: None)
         monkeypatch.setattr(env.native, "terminate", lambda: None)
         env.core = env.new_core()
@@ -264,7 +239,7 @@ def assemble(monkeypatch, tmp_path, *, supported=True):
         controls[engine] = EngineControl(env, engine, monkeypatch)
     # Mocked NVDA setting descriptors and VoiceInfo supply realistic metadata.
     for engine, control in controls.items():
-        outer = control.env.outer if engine in ("OneCore", "Neural") else control.env.module
+        outer = control.env.outer if engine == "OneCore" else control.env.module
         monkeypatch.setattr(outer.SynthDriver, "supportedSettings", [SimpleNamespace(id=name)
             for name in ("voice", "rate", "rateBoost", "pitch", "volume")], raising=False)
         outer.Voice.core = control.core
@@ -281,7 +256,7 @@ def assemble(monkeypatch, tmp_path, *, supported=True):
     engine_module = ModuleType(PACKAGE + ".engine")
     engine_module.EngineType = [SimpleNamespace(name=name) for name in ENGINES]
     engine_module.READY_ENGINE_CLASS = {
-        name: (control.env.outer if name in ("OneCore", "Neural") else control.env.module).Voice
+        name: (control.env.outer if name == "OneCore" else control.env.module).Voice
         for name, control in controls.items()}
     engine_module.get_engine_enabled = lambda *args: True
     engine_module.refresh_ready_engine_classes = lambda *args: None
@@ -311,7 +286,7 @@ def assemble(monkeypatch, tmp_path, *, supported=True):
     # The loaded wrappers retain different NVDA Notification objects; reconnect
     # each hardware notification to the same production event bridge.
     for control in controls.values():
-        wrapper = control.env.outer if control.engine in ("OneCore", "Neural") else control.env.original_driver
+        wrapper = control.env.outer if control.engine == "OneCore" else control.env.original_driver
         monkeypatch.setattr(wrapper.synthIndexReached, "notify", index.notify)
         monkeypatch.setattr(wrapper.synthDoneSpeaking, "notify", done.notify)
     bridge = bridge_type(owner, done_event=done, index_event=index,
diff --git a/tests/test_engine_segment_contract.py b/tests/test_engine_segment_contract.py
index cb10d83..2300b45 100644
--- a/tests/test_engine_segment_contract.py
+++ b/tests/test_engine_segment_contract.py
@@ -11,13 +11,11 @@ import pytest
 from engine_contract_harness import (
 	CerenceAdapter,
 	EspeakAdapter,
-	NeuralAdapter,
 	OneCoreAdapter,
 	RHVoiceAdapter,
 	SAPI5Adapter,
 	VEAdapter,
 )
-from neural_drain_harness import requires_neural
 
 ADAPTERS = {
 	"VE": VEAdapter,
@@ -26,7 +24,6 @@ ADAPTERS = {
 	"RHVoice": RHVoiceAdapter,
 	"SAPI5": SAPI5Adapter,
 	"Espeak": EspeakAdapter,
-	"Neural": NeuralAdapter,
 }
 
 
@@ -37,7 +34,7 @@ class C3Blocking(AssertionError):
 def _engines(**xfails):
 	params = []
 	for name in ADAPTERS:
-		marks = [requires_neural] if name == "Neural" else []
+		marks = []
 		if name in xfails:
 			# Only the known gap may xfail; any other failure still fails the run.
 			marks.append(pytest.mark.xfail(strict=True, raises=C3Blocking, reason=xfails[name]))
diff --git a/tests/test_lifecycle_private_access.py b/tests/test_lifecycle_private_access.py
index 78c4a4d..4cfcd29 100644
--- a/tests/test_lifecycle_private_access.py
+++ b/tests/test_lifecycle_private_access.py
@@ -10,7 +10,7 @@ PRIVATE_GETATTR = re.compile(
 	rf"getattr\(\s*(?:self\.)?{LIFECYCLE_OBJECTS}\s*,\s*[\"']_(\w+)[\"']",
 )
 # Per-operation data each wrapper attaches itself; SegmentHost replaces it in phase 3.
-WRAPPER_PREFIXES = ("ve_", "onecore_", "rhvoice_", "espeak_", "neural_")
+WRAPPER_PREFIXES = ("ve_", "onecore_", "rhvoice_", "espeak_")
 
 
 def _private_accesses(text):
diff --git a/tests/test_runtime_completion_policies.py b/tests/test_runtime_completion_policies.py
index 0fce499..a0b337d 100644
--- a/tests/test_runtime_completion_policies.py
+++ b/tests/test_runtime_completion_policies.py
@@ -6,7 +6,6 @@ from types import SimpleNamespace
 
 import pytest
 
-from neural_drain_harness import requires_neural
 from test_worldvoice_lifecycle import _load_voice_manager, _load_synth_class
 
 
@@ -235,18 +234,17 @@ def test_sapi5_legacy_first_segment_remains_legacy_done(monkeypatch):
         installed.driver.terminate()
 
 
-SEVEN_ENGINES = ["OneCore", pytest.param("Neural", marks=requires_neural),
-    "VE", "Cerence", "SAPI5", "Espeak", "RHVoice"]
+SIX_ENGINES = ["OneCore", "VE", "Cerence", "SAPI5", "Espeak", "RHVoice"]
 
 
 def load_installed_engine(monkeypatch, tmp_path, engine):
     """Open the installed outer wrapper for *engine* on its fake native boundary."""
     control = None
-    if engine in ("OneCore", "Neural", "VE", "Cerence"):
+    if engine in ("OneCore", "VE", "Cerence"):
         from runtime_drain_integration_harness import assemble
         composition = assemble(monkeypatch, tmp_path)
         control = composition.controls[engine]
-        outer = control.env.outer if engine in ("OneCore", "Neural") else control.env.module
+        outer = control.env.outer if engine == "OneCore" else control.env.module
         core, close = control.core, composition.close
         mode, rt = ("wasapi" if engine == "OneCore" else "default"), composition.rt
     elif engine == "SAPI5":
@@ -285,8 +283,8 @@ def real_completion_selector(policies, warnings):
     return object.__new__(root)._completion_for
 
 
-@pytest.mark.parametrize("engine", SEVEN_ENGINES)
-def test_seven_enabled_profiles_use_shared_lifecycle(monkeypatch, tmp_path, engine):
+@pytest.mark.parametrize("engine", SIX_ENGINES)
+def test_six_enabled_profiles_use_shared_lifecycle(monkeypatch, tmp_path, engine):
     """The actual opened outer core must select DRAIN before any segment starts."""
     installed = load_installed_engine(monkeypatch, tmp_path, engine)
     outer, core, control = installed.outer, installed.core, installed.control
@@ -317,7 +315,7 @@ def test_seven_enabled_profiles_use_shared_lifecycle(monkeypatch, tmp_path, engi
         installed.close()
 
 
-@pytest.mark.parametrize("engine", SEVEN_ENGINES)
+@pytest.mark.parametrize("engine", SIX_ENGINES)
 def test_disabled_force_switch_restores_legacy_done(monkeypatch, tmp_path, engine):
     installed = load_installed_engine(monkeypatch, tmp_path, engine)
     outer, core = installed.outer, installed.core
diff --git a/tests/test_runtime_drain_integration.py b/tests/test_runtime_drain_integration.py
index f3749b1..4026d9a 100644
--- a/tests/test_runtime_drain_integration.py
+++ b/tests/test_runtime_drain_integration.py
@@ -1,15 +1,10 @@
 """Correlated drains across the real manager, adapters, bridge and wrappers."""
 
 from concurrent.futures import TimeoutError
-from pathlib import Path
-import subprocess
-import sys
-from threading import Event
 
 import pytest
 
 from runtime_drain_integration_harness import ENGINES, assemble
-from neural_drain_harness import in_thread, requires_neural
 
 
 @pytest.fixture
@@ -36,8 +31,7 @@ def test_wrapper_index_precedes_audio_drain_and_request_done(composition, engine
     assert [kind for kind, _ in c.output.timeline] == ["index", "drain", "done"]
 
 
-@pytest.mark.parametrize("engines", [
-    pytest.param(("OneCore", "Neural", "OneCore"), marks=requires_neural), ("VE", "Cerence", "VE")])
+@pytest.mark.parametrize("engines", [("VE", "Cerence", "VE")])
 def test_next_engine_starts_only_after_segment_drain(composition, engines):
     c = composition
     a, b, _ = engines
@@ -65,8 +59,7 @@ def test_next_engine_starts_only_after_segment_drain(composition, engines):
     assert len(c.output.drains) == 3
 
 
-@pytest.mark.parametrize("first,successor", [
-    pytest.param("OneCore", "Neural", marks=requires_neural), ("VE", "Cerence")])
+@pytest.mark.parametrize("first,successor", [("VE", "Cerence")])
 def test_switch_waits_for_original_correlated_drain(composition, first, successor):
     c = composition
     request = c.submit(("original", c.rt.models.SelectVoice(c.key(successor)),
@@ -238,64 +231,53 @@ def test_setting_revision_reapplies_without_reusing_segment_context(composition,
     assert len(c.output.dones) == 1
 
 
-@requires_neural
 def test_voice_switch_reapplies_native_settings_and_keeps_distinct_drains(composition):
     c = composition
-    a, b = "Neural:voice1", "Neural:voice2"
+    a, b = "VE:fake", "VE:fake2"
     c.manager.resolve_playback(b)
     c.store.state(b).update(rate=31)
     request = c.submit(("english", c.rt.models.SelectVoice(b), "french",
-        c.rt.models.SelectVoice(a), "english again"), "Neural")
-    control = c.controls["Neural"]
+        c.rt.models.SelectVoice(a), "english again"), "VE")
+    control = c.controls["VE"]
     for number in (1, 2, 3):
         barrier = control.tail(number)
         assert len(control.calls) == number
         barrier.release.set()
     c.wait_done()
-    assert [snapshot.voice_id for snapshot in control.applied] == ["voice1", "voice2", "voice1"]
+    assert [snapshot.voice_id for snapshot in control.applied] == ["fake", "fake2", "fake"]
     assert [snapshot.rate for snapshot in control.applied] == [50, 31, 50]
-    assert control.calls[0].instance != control.calls[1].instance
-    assert control.calls[0].instance == control.calls[2].instance
+    instances = [call.instance.pHandleData for call in control.calls]
+    assert instances[0] != instances[1]
+    assert instances[0] == instances[2]
     assert len({context.segment_id for context in control.contexts}) == 3
     assert len(c.output.drains) == 3
     assert request.state is c.scheduler.RequestState.COMPLETED
 
 
-@pytest.mark.parametrize("engine", [pytest.param("Neural", marks=requires_neural), "VE", "Cerence"])
+@pytest.mark.parametrize("engine", ["VE", "Cerence"])
 def test_language_change_active_native_call_cannot_escape_cancel(composition, monkeypatch, engine):
     c = composition
     control = c.controls[engine]
-    if engine in ("VE", "Cerence"):
-        monkeypatch.setattr(control.core, "getVoiceNameForLanguage", lambda language: "fr", raising=False)
+    monkeypatch.setattr(control.core, "getVoiceNameForLanguage", lambda language: "fr", raising=False)
     old = c.submit(("hello", c.commands.LangChangeCommand("fr"), "bonjour"), engine)
     first = control.wait_call()
     control.complete_native()
     second = control.wait_call(2)
-    first_id = first.instance if engine == "Neural" else first.instance.pHandleData
-    second_id = second.instance if engine == "Neural" else second.instance.pHandleData
-    saved_bookmark = control.env.native.synths[second_id].bookmark if engine == "Neural" else None
+    first_id = first.instance.pHandleData
+    second_id = second.instance.pHandleData
     assert first_id != second_id
     assert len(control.contexts) == 1
     assert c.output.drains == []
-    if engine == "Neural":
-        control.env.native.stop_start_entered.clear()
     c.tasks.cancel(c.manager.playback_ports)
-    if engine == "Neural":
-        assert control.env.native.stop_start_entered.wait(1)
-        with control.env.native.condition:
-            assert any(synth == second_id for _, synth in control.env.native.operations)
     second.release.set()
     fresh = c.submit(("new default voice",), engine)
     control.wait_call(3)
     assert len(control.calls) == 3
-    assert (control.calls[2].instance if engine == "Neural" else control.calls[2].instance.pHandleData) == first_id
+    assert control.calls[2].instance.pHandleData == first_id
     fed_before = list(control.player.fed)
-    if engine == "Neural":
-        control.env.native.bookmark("9999", saved=saved_bookmark)
-    else:
-        from test_vocalizer_segment_drain import emit
-        assert emit(control.env, second.instance, payload=b"stale", index=9999) == [
-            control.env.types.NUAN_E_TTS_USERSTOP]
+    from test_vocalizer_segment_drain import emit
+    assert emit(control.env, second.instance, payload=b"stale", index=9999) == [
+        control.env.types.NUAN_E_TTS_USERSTOP]
     assert control.player.fed == fed_before
     assert c.output.indexes == []
     assert not fresh.tasks[0].future.done()
@@ -361,234 +343,3 @@ def test_unsupported_profile_uses_legacy_from_first_segment(monkeypatch, tmp_pat
         assert len(c.output.dones) == 1
     finally:
         c.close()
-
-
-@requires_neural
-def test_unsupported_neural_sdk_failure_releases_legacy_request(monkeypatch, tmp_path):
-    c = assemble(monkeypatch, tmp_path, supported=False)
-    try:
-        control = c.controls["Neural"]
-        assert control.session.completion.mode is c.rt.models.CompletionMode.LEGACY_DONE
-        control.env.native.result = 1
-        request = c.submit(("SDK failure",), "Neural")
-        call = control.wait_call()
-        assert call.context is None
-        call.release.set()
-        with pytest.raises(RuntimeError, match="Neural SDK synthesis failed"):
-            request.tasks[0].future.result(timeout=1)
-        c.wait_done()
-        assert request.state is c.scheduler.RequestState.FAILED
-        assert c.output.drains == []
-        assert len(c.output.dones) == 1
-        assert control.env.logs
-    finally:
-        c.close()
-
-
-@requires_neural
-def test_contextual_legacy_control_failure_fails_request(monkeypatch, tmp_path):
-    c = assemble(monkeypatch, tmp_path, supported=False)
-    try:
-        control = c.controls["Neural"]
-        control.player.error = "pause"
-        request = c.submit(("pause failure",), "Neural")
-        control.wait_call()
-        barrier = control.tail()
-        pausing = in_thread(lambda: c.tasks.pause_current(True))
-        pausing.done.wait(1)
-        barrier.release.set()
-        with pytest.raises(OSError, match="audio control failed"):
-            request.tasks[0].future.result(timeout=2)
-        assert pausing.errors and isinstance(pausing.errors[0], OSError)
-        c.wait_done()
-        assert request.state is c.scheduler.RequestState.FAILED
-        assert c.output.drains == []
-        assert len(c.output.dones) == 1
-    finally:
-        c.close()
-
-
-@requires_neural
-def test_neural_legacy_done_acceptance_cannot_release_successor_after_cancel(monkeypatch, tmp_path):
-    c = assemble(monkeypatch, tmp_path, supported=False)
-    release = Event()
-    try:
-        control = c.controls["Neural"]
-        old = c.submit(("old legacy",), "Neural")
-        control.wait_call()
-        work = next(iter(control.core._segmentWorks))
-        accepted = Event()
-        complete = work.complete
-
-        def blocked_complete():
-            result = complete()
-            if result:
-                accepted.set()
-                assert release.wait(2), "Test did not release accepted legacy DONE"
-            return result
-
-        monkeypatch.setattr(work, "complete", blocked_complete)
-        control.tail().release.set()
-        assert accepted.wait(1)
-        cancelling = in_thread(lambda: c.tasks.cancel(c.manager.playback_ports))
-        fresh = None
-        try:
-            # If cancellation can return across the accepted notification, admit
-            # a real successor while the old notification is still suspended.
-            if cancelling.done.wait(0.05):
-                assert cancelling.errors == []
-                fresh = c.submit(("successor legacy",), "Neural")
-                with c.tasks._state_cond:
-                    assert c.tasks._state_cond.wait_for(lambda:
-                        c.tasks._current_task is fresh.tasks[0]
-                        and c.tasks._current_phase == "awaiting_completion", 1)
-        finally:
-            release.set()
-            assert cancelling.done.wait(2)
-            assert cancelling.errors == []
-        if fresh is None:
-            fresh = c.submit(("successor legacy",), "Neural")
-        successor = control.wait_call(2)
-        assert not successor.release.is_set(), "Successor synthesis must still be blocked"
-        with pytest.raises(TimeoutError):
-            fresh.tasks[0].future.result(timeout=0.05)
-        assert c.output.dones == []
-        control.tail(2, idle_number=2).release.set()
-        c.wait_done()
-        assert old.state is c.scheduler.RequestState.CANCELLED
-        assert fresh.tasks[0].future.result(timeout=1) is True
-        assert fresh.state is c.scheduler.RequestState.COMPLETED
-    finally:
-        release.set()
-        c.close()
-
-
-@requires_neural
-def test_neural_legacy_control_failure_delivery_cannot_complete_cancelled_request(monkeypatch, tmp_path):
-    c = assemble(monkeypatch, tmp_path, supported=False)
-    release = Event()
-    try:
-        control = c.controls["Neural"]
-        request = c.submit(("legacy control failure",), "Neural")
-        control.wait_call()
-        work = next(iter(control.core._segmentWorks))
-        complete, accepted = work.complete, Event()
-
-        def blocked_complete():
-            result = complete()
-            if result:
-                accepted.set()
-                assert release.wait(2), "Test did not release accepted failure DONE"
-            return result
-
-        monkeypatch.setattr(work, "complete", blocked_complete)
-        control.player.error = "pause"
-        pausing = in_thread(lambda: c.tasks.pause_current(True))
-        assert accepted.wait(1)
-        cancelling = in_thread(lambda: c.tasks.cancel(c.manager.playback_ports))
-        try:
-            assert cancelling.done.wait(1), "Cancel blocked behind external legacy event delivery"
-        finally:
-            release.set()
-            assert pausing.done.wait(2)
-            assert cancelling.done.wait(2)
-        assert len(pausing.errors) == 1 and isinstance(pausing.errors[0], OSError)
-        assert cancelling.errors == []
-        assert request.state is c.scheduler.RequestState.CANCELLED
-        assert c.output.dones == []
-    finally:
-        release.set()
-        c.close()
-
-
-@requires_neural
-def test_contextual_neural_legacy_ignores_anonymous_and_revoked_completion(monkeypatch, tmp_path):
-    c = assemble(monkeypatch, tmp_path, supported=False)
-    try:
-        control = c.controls["Neural"]
-        request = c.submit(("legacy identity",), "Neural")
-        control.wait_call()
-        work = next(iter(control.core._segmentWorks))
-        context = work.context
-        old_sink = work.on_event
-        done = c.rt.models.PlaybackEvent(c.rt.models.EventKind.DONE,
-            context.source_id, segment_id=context.segment_id)
-        c.bridge._done_event.notify(synth=control.core)
-        with pytest.raises(TimeoutError):
-            request.tasks[0].future.result(timeout=0.03)
-        c.bridge.unbind(control.session.source_id)
-        c.bridge.bind(control.core, control.session.source_id, completion=control.session.completion)
-        old_sink(done)
-        with pytest.raises(TimeoutError):
-            request.tasks[0].future.result(timeout=0.03)
-        assert c.output.dones == []
-        monkeypatch.setattr(work, "on_event", c.bridge.legacy_segment_sink(control.core, context))
-        control.tail().release.set()
-        c.wait_done()
-        assert request.tasks[0].future.result(timeout=1) is True
-    finally:
-        c.close()
-
-
-def _exercise_neural_legacy_terminal_index_cancel(failure, tmp_path):
-    # A broken lock order leaves daemon engine/scheduler threads deadlocked.
-    # Run this case in its own interpreter so failed evidence cannot hang cleanup.
-    monkeypatch = pytest.MonkeyPatch()
-    c = assemble(monkeypatch, tmp_path, supported=False)
-    control = c.controls["Neural"]
-    c.submit(("legacy", c.commands.IndexCommand(818)), "Neural")
-    control.wait_call()
-    work = next(iter(control.core._segmentWorks))
-    complete = work.complete
-    accepted, release_done = Event(), Event()
-    index_entered, cancel_index, cancelled = Event(), Event(), Event()
-
-    def held_complete():
-        result = complete()
-        if result:
-            accepted.set()
-            assert release_done.wait(2), "Test did not release terminal acceptance"
-        return result
-
-    def index_handler(index):
-        assert index == 818
-        index_entered.set()
-        assert cancel_index.wait(2), "Test did not release index cancellation"
-        c.tasks.cancel(c.manager.playback_ports)
-        cancelled.set()
-
-    monkeypatch.setattr(work, "complete", held_complete)
-    monkeypatch.setattr(c.bridge, "index_reached", index_handler)
-    bookmark = in_thread(lambda: control.env.native.bookmark("818"))
-    assert index_entered.wait(1)
-    if failure:
-        control.player.error = "pause"
-        terminal = in_thread(lambda: c.tasks.pause_current(True))
-    else:
-        control.wait_call().release.set()
-        control.wait_idle().release.set()
-        terminal = None
-    assert accepted.wait(1)
-    cancel_index.set()
-    release_done.set()
-    assert cancelled.wait(1), "Index cancellation and legacy terminal delivery deadlocked"
-    assert bookmark.done.wait(1) and bookmark.errors == []
-    if terminal is not None:
-        assert terminal.done.wait(1)
-        assert len(terminal.errors) == 1 and isinstance(terminal.errors[0], OSError)
-    assert c.output.dones == []
-    c.close()
-    monkeypatch.undo()
-
-
-@requires_neural
-@pytest.mark.parametrize("failure", [False, True])
-def test_neural_legacy_terminal_and_index_cancel_have_no_lock_inversion(tmp_path, failure):
-    script = (
-        "from pathlib import Path\n"
-        "from test_runtime_drain_integration import _exercise_neural_legacy_terminal_index_cancel\n"
-        f"_exercise_neural_legacy_terminal_index_cancel({failure!r}, Path({str(tmp_path)!r}))\n"
-    )
-    result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).parent,
-                            text=True, capture_output=True, timeout=6)
-    assert result.returncode == 0, result.stderr
```

- [ ] **Step 3: Run the tests**

Run: `python3 -m pytest tests -q 2>&1 | tail -1`
Expected: `1378 passed, 2 skipped`. The two skips are the VE twin tests, which Task 2 merges.

Run: `python3 -m pytest tests/test_runtime_drain_integration.py -q 2>&1 | tail -1; grep -rln "neural_drain_harness\|requires_neural\|NEURAL_AVAILABLE\|load_neural\|NeuralAdapter" tests`
Expected: `33 passed`, then no grep output.

The ported test passes at once because the behavior already exists. Step 5's mutations prove that it bites.

- [ ] **Step 4: Commit**

```bash
git add tests/runtime_drain_integration_harness.py tests/test_runtime_drain_integration.py \
	tests/test_runtime_completion_policies.py tests/test_engine_segment_contract.py \
	tests/engine_contract_harness.py tests/test_lifecycle_private_access.py
git commit -m "test: drop the Neural tests and port the voice-switch drain test to VE

Neural is not in the repository and no longer has to stay compatible. The
contextual legacy integration tests only Neural could run are removed; the
gap is recorded in the phase 3e spec. A second harness VE voice keeps the
same-engine voice-switch coverage.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

`git rm` in Step 1 already staged the two deletions.

- [ ] **Step 5: Prove the ported test bites (mutations MV1–MV2, after the commit)**

```bash
mutate() { python3 - "$1" "$2" "$3" <<'PY'
import sys
p, old, new = sys.argv[1:]
s = open(p).read()
assert s.count(old) == 1, old
open(p, "w").write(s.replace(old, new))
PY
}
check() { timeout 300 python3 -m pytest tests/test_runtime_drain_integration.py -q -p no:cacheprovider 2>&1 | grep -E '^FAILED|^[0-9]+ (passed|failed)' | sed 's/ - .*//'; git checkout -- addon; }

echo MV1; mutate addon/synthDrivers/WorldVoice/driver/VE/driver/__init__.py '		self._instanceCache[name] = instance
		return instance' '		return instance'; check
echo MV2; mutate addon/synthDrivers/WorldVoice/runtime/session.py '			self._adapter.apply(state.spec, snapshot)
			self._applied' '			if applied is None:
				self._adapter.apply(state.spec, snapshot)
			self._applied'; check
git status --short | grep addon
```

Expected:
- MV1: VE never caches a voice's instance. `2 failed, 31 passed`:
  - `test_voice_switch_reapplies_native_settings_and_keeps_distinct_drains`
  - `test_language_change_active_native_call_cannot_escape_cancel[VE]`
- MV2: the session skips `apply` after the first activation. `4 failed, 29 passed`:
  - `test_setting_revision_reapplies_without_reusing_segment_context[OneCore]`, `[VE]` and `[Cerence]`
  - `test_voice_switch_reapplies_native_settings_and_keeps_distinct_drains`

The final `git status` prints nothing.

---

### Task 2: Tests use only the host; merge the VE/Cerence twins

Spec §2.3 and §2.4. This is a test-only refactor, so the whole suite stays green and loses its last 2 skips.

**Files:**
- Modify: `tests/test_vocalizer_segment_drain.py`:
  - `hosted()` is removed;
  - `lifecycle_of()`, `settle_segment()` and `settle_worker()` read only the host;
  - 11 `hosted(env)` branches keep only their host side;
  - `test_ve_shared_*` and `test_cerence_shared_*` merge into `test_shared_lifecycle_waits_for_chunk_callback_and_idle` and `test_shared_cancel_retires_guarded_feed_before_successor`.
- Modify: `tests/test_worldvoice_cancel_wrappers.py` (`emit_audio` reads `_nativeCall` only)
- Modify: `tests/engine_contract_harness.py` (`on_delivery_thread` via the host)
- Modify: `tests/test_runtime_completion_policies.py`, `tests/test_runtime_drain_integration.py` (host branch only)
- Modify: `tests/test_sapi5_segment_drain.py` (`hooks = env.driver._segmentHost`; `stranded` scaffolding removed)

**Interfaces:**
- Consumes: Task 1's test files.
- Produces: `lifecycle_of(env)` returns `env.core._segmentHost._lifecycle`. Task 3 does not change this helper.

- [ ] **Step 1: Apply the cleanup**

Save as `$PATCHES/t2.patch`, then run `git apply $PATCHES/t2.patch`:

```diff
diff --git a/tests/engine_contract_harness.py b/tests/engine_contract_harness.py
index 87e89a7..a825522 100644
--- a/tests/engine_contract_harness.py
+++ b/tests/engine_contract_harness.py
@@ -46,9 +46,7 @@ class _Adapter:
 		self.core.terminate()
 
 	def on_delivery_thread(self):
-		host = getattr(self.core, "_segmentHost", None)
-		lifecycle = host if host is not None else self.core._segmentLifecycle
-		return lifecycle.on_delivery_thread()
+		return self.core._segmentHost.on_delivery_thread()
 
 
 class EspeakAdapter(_Adapter):
diff --git a/tests/test_runtime_completion_policies.py b/tests/test_runtime_completion_policies.py
index a0b337d..c076d96 100644
--- a/tests/test_runtime_completion_policies.py
+++ b/tests/test_runtime_completion_policies.py
@@ -293,14 +293,10 @@ def test_six_enabled_profiles_use_shared_lifecycle(monkeypatch, tmp_path, engine
         assert policies.FORCE_UNVERIFIED_DRAIN is True
         assert sys.modules["synthDrivers.WorldVoice.driver." + engine] is outer
         assert outer.Voice.synth_driver_class is type(core)
-        host = getattr(core, "_segmentHost", None)
-        if host is not None:
-            # Migrated wrappers: the host owns the lifecycle and implements its hooks.
-            assert isinstance(host, outer.SegmentHost)
-            assert host._lifecycle._hooks is host
-        else:
-            assert isinstance(core._segmentLifecycle, outer.SegmentLifecycle)
-            assert core._segmentLifecycle._hooks is core
+        # The host owns the lifecycle and implements its hooks.
+        host = core._segmentHost
+        assert isinstance(host, outer.SegmentHost)
+        assert host._lifecycle._hooks is host
         support = policies.get_segment_drain_support(outer.Voice, core,
             nvda_version="2026.1", audio_mode=installed.mode)
         assert support.supported is True
diff --git a/tests/test_runtime_drain_integration.py b/tests/test_runtime_drain_integration.py
index 4026d9a..24a5953 100644
--- a/tests/test_runtime_drain_integration.py
+++ b/tests/test_runtime_drain_integration.py
@@ -68,11 +68,8 @@ def test_switch_waits_for_original_correlated_drain(composition, first, successo
     following = c.controls[successor]
     barrier = original.tail()
     context = original.contexts[0]
-    host = getattr(original.core, "_segmentHost", None)
-    if host is not None:
-        assert host._lifecycle._hooks is host
-    else:
-        assert original.core._segmentLifecycle._hooks is original.core
+    host = original.core._segmentHost
+    assert host._lifecycle._hooks is host
     assert c.output.drains == []
     assert following.started.wait(0.03) is False
     assert following.calls == []
diff --git a/tests/test_sapi5_segment_drain.py b/tests/test_sapi5_segment_drain.py
index 9480b87..d583140 100644
--- a/tests/test_sapi5_segment_drain.py
+++ b/tests/test_sapi5_segment_drain.py
@@ -1302,15 +1302,11 @@ def test_submit_failure_before_binding_leaves_the_lifecycle_usable(env, monkeypa
 def test_hook_fault_after_binding_does_not_strand_the_worker(monkeypatch):
     """C2: a lifecycle hook that fails after the native request is bound."""
     env = load_sapi5(monkeypatch)
-    hooks = getattr(env.driver, "_segmentHost", env.driver)
+    hooks = env.driver._segmentHost
     real_retired = hooks.wait_native_retired
-    stranded = []
 
     def failing_retired(operation):
         real_retired(operation)
-        binding = getattr(env.driver, "_segmentBindings", {}).get(operation)
-        if binding is not None:
-            stranded.append(binding)
         raise RuntimeError("hook failed after binding")
 
     monkeypatch.setattr(hooks, "wait_native_retired", failing_retired)
@@ -1331,8 +1327,6 @@ def test_hook_fault_after_binding_does_not_strand_the_worker(monkeypatch):
         terminated.join(2)
         assert not terminated.is_alive(), "terminate() hung on the stranded worker"
     finally:
-        for binding in stranded:
-            binding.playback_done.set()
         for player in env.players:
             player.feed_release.set()
             player.idle_release.set()
diff --git a/tests/test_vocalizer_segment_drain.py b/tests/test_vocalizer_segment_drain.py
index 4e64686..6ac72df 100644
--- a/tests/test_vocalizer_segment_drain.py
+++ b/tests/test_vocalizer_segment_drain.py
@@ -60,29 +60,19 @@ def wait_for(predicate):
     assert predicate()
 
 
-def hosted(env):
-    # VE runs on SegmentHost (phase 3d-1); Cerence keeps its synchronous wrapper.
-    return getattr(env.core, "_segmentHost", None)
-
-
 def lifecycle_of(env):
-    host = hosted(env)
-    return host._lifecycle if host is not None else env.core._segmentLifecycle
+    return env.core._segmentHost._lifecycle
 
 
 def settle_segment(env, context):
-    # speak_segment returns before delivery on the host; wait for this
-    # segment's operation to be published or discarded.
-    if hosted(env) is None:
-        return
+    # speak_segment returns before delivery; wait for this segment's
+    # operation to be published or discarded.
     lifecycle = lifecycle_of(env)
     wait_for(lambda: all(operation.work.context is not context for operation in list(lifecycle._operations)))
 
 
 def settle_worker(env):
-    # VE queues ordinary speech to the inner BgThread; wait until it ran.
-    if hosted(env) is None:
-        return
+    # Ordinary speech is queued to the inner BgThread; wait until it ran.
     queue, thread = env.core._bgQueue, env.core._bgThread
     wait_for(lambda: queue.unfinished_tasks == 0 or not thread.is_alive())
 
@@ -133,9 +123,7 @@ def emit(env, instance, *, payload=b"pcm", index=_NO_BOOKMARK, end=True):
     return results
 
 
-def test_ve_shared_lifecycle_waits_for_chunk_callback_and_idle(env, monkeypatch):
-    if env.engine != "VE":
-        pytest.skip("VE lifecycle adapter")
+def test_shared_lifecycle_waits_for_chunk_callback_and_idle(env, monkeypatch):
     prove_fake_quiescence(env, monkeypatch)
     assert isinstance(env.core._segmentHost, env.module.SegmentHost)
     feed_entered, feed_release, idle_entered, idle_release = Event(), Event(), Event(), Event()
@@ -165,80 +153,7 @@ def test_ve_shared_lifecycle_waits_for_chunk_callback_and_idle(env, monkeypatch)
     assert env.indexes == [31]
 
 
-def test_ve_shared_cancel_retires_guarded_feed_before_successor(env, monkeypatch):
-    if env.engine != "VE":
-        pytest.skip("VE lifecycle adapter")
-    prove_fake_quiescence(env, monkeypatch)
-    assert isinstance(env.core._segmentHost, env.module.SegmentHost)
-    feed_entered, feed_release, stop_entered, stop_release = Event(), Event(), Event(), Event()
-    calls, callbacks = [], []
-    env.core._real_player.feed = lambda data: (feed_entered.set(), feed_release.wait(2))
-    def stop():
-        stop_entered.set()
-        assert stop_release.wait(2)
-    env.core._real_player.stop = stop
-    def native(instance, text):
-        calls.append(text)
-        if len(calls) == 1:
-            callbacks.append(run_thread(lambda: emit(env, instance, index=41)))
-            assert feed_entered.wait(1)
-        else:
-            emit(env, instance, index=42)
-    monkeypatch.setattr(env.native, "processText2Speech", native)
-    token, _, first = speak(env)
-    assert feed_entered.wait(1)
-    token.cancel()
-    _, context, second = speak(env, segment=18)
-    feed_release.set()
-    assert stop_entered.wait(1)
-    assert calls == ["hello"]
-    stop_release.set()
-    # The callback thread can feed before native() records its handle.
-    wait_for(lambda: bool(callbacks))
-    finish(callbacks[0])
-    finish(first)
-    finish(second)
-    wait_for(lambda: len(env.events) == 1)
-    assert calls == ["hello", "hello"]
-    assert env.indexes == [42]
-    assert len(env.events) == 1
-    assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_DRAINED
-    assert env.events[0].source_id is context.source_id
-    assert env.events[0].segment_id == 18
-
-
-@pytest.mark.parametrize("env", ["Cerence"], indirect=True)
-def test_cerence_shared_lifecycle_waits_for_chunk_callback_and_idle(env, monkeypatch):
-    prove_fake_quiescence(env, monkeypatch)
-    assert isinstance(env.core._segmentHost, env.module.SegmentHost)
-    feed_entered, feed_release, idle_entered, idle_release = Event(), Event(), Event(), Event()
-    callbacks = []
-    env.core._real_player.feed = lambda data: (feed_entered.set(), feed_release.wait(2))
-    env.core._real_player.idle = lambda: (idle_entered.set(), idle_release.wait(2))
-    def native(instance, text):
-        callbacks.append(run_thread(lambda: emit(env, instance, index=31)))
-        assert feed_entered.wait(1)
-    monkeypatch.setattr(env.native, "processText2Speech", native)
-    _, context, call = speak(env)
-    assert feed_entered.wait(1)
-    assert env.events == []
-    assert not idle_entered.is_set()
-    feed_release.set()
-    wait_for(lambda: bool(callbacks))
-    finish(callbacks[0])
-    assert idle_entered.wait(1)
-    assert env.events == []
-    idle_release.set()
-    finish(call)
-    wait_for(lambda: len(env.events) == 1)
-    assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_DRAINED
-    assert env.events[0].source_id is context.source_id
-    assert env.events[0].segment_id == context.segment_id
-    assert env.indexes == [31]
-
-
-@pytest.mark.parametrize("env", ["Cerence"], indirect=True)
-def test_cerence_shared_cancel_retires_guarded_feed_before_successor(env, monkeypatch):
+def test_shared_cancel_retires_guarded_feed_before_successor(env, monkeypatch):
     prove_fake_quiescence(env, monkeypatch)
     assert isinstance(env.core._segmentHost, env.module.SegmentHost)
     feed_entered, feed_release, stop_entered, stop_release = Event(), Event(), Event(), Event()
@@ -645,16 +560,10 @@ def hold_contextual_final_idle(env, monkeypatch):
 
 
 def start_ordinary_behind(held, env, token=None):
-    if hosted(env):
-        # speak() returns once queued; the worker holds it behind the segment.
-        ordinary = run_thread(lambda: env.core.speak(("ordinary",), token))
-        finish(ordinary)
-        wait_for(lambda: queued_ordinary(env) == 1)
-        return ordinary
+    # speak() returns once queued; the worker holds it behind the segment.
     ordinary = run_thread(lambda: env.core.speak(("ordinary",), token))
-    # Either the ordinary request reaches native, or it waits for the
-    # coordinator resource. Only the latter keeps the shared player exclusive.
-    wait_for(lambda: ordinary[0] in held.condition.waiters or len(held.native_calls) > 1)
+    finish(ordinary)
+    wait_for(lambda: queued_ordinary(env) == 1)
     return ordinary
 
 
@@ -664,10 +573,7 @@ def test_contextual_final_idle_keeps_ordinary_speech_out_of_native(env, monkeypa
         ordinary = start_ordinary_behind(held, env)
         assert held.native_calls == [("hello", False)], (
             "Ordinary speech entered native during the contextual final idle")
-        if hosted(env):
-            assert queued_ordinary(env) == 1
-        else:
-            assert not ordinary[1].is_set()
+        assert queued_ordinary(env) == 1
     finally:
         held.release.set()
     finish(held.contextual)
@@ -692,13 +598,10 @@ def test_cancel_during_contextual_final_idle_releases_waiting_ordinary(env, monk
     finish(held.contextual)
     finish(ordinary)
     settle_worker(env)
-    if hosted(env):
-        # Like the original add-on: cancel drops queued speech, keeps its DONE.
-        assert held.native_calls == [("hello", False)]
-        assert len(env.dones) == 1
-        assert hosted(env)._pending == []
-    else:
-        assert held.native_calls == [("hello", False), ("ordinary", True)]
+    # Like the original add-on: cancel drops queued speech, keeps its DONE.
+    assert held.native_calls == [("hello", False)]
+    assert len(env.dones) == 1
+    assert env.core._segmentHost._pending == []
     with held.condition:
         assert held.condition.wait_for(
             lambda: not lifecycle_of(env)._operations, 1)
@@ -755,11 +658,8 @@ def test_terminate_during_contextual_final_idle_with_waiting_ordinary(
         held.release.set()
     finish(held.contextual)
     assert ordinary[1].wait(2)
-    if hosted(env):
-        # The queued request returned at once; terminate's cancel dropped it.
-        assert ordinary[2] == []
-    else:
-        assert [str(error) for error in ordinary[2]] == [f"{env.engine} driver has terminated"]
+    # The queued request returned at once; terminate's cancel dropped it.
+    assert ordinary[2] == []
     assert held.native_calls == [("hello", False)]
     assert closed.is_set()
     assert env.events == []
@@ -774,8 +674,7 @@ def test_multichunk_langchange_has_one_work_and_final_drain(env, monkeypatch):
     calls, works = [], []
     def native(instance, text):
         calls.append((instance.pHandleData, text))
-        native = env.core._nativeCall if hosted(env) else env.core._nativeWork
-        works.append(native.record if hosted(env) else native.work)
+        works.append(env.core._nativeCall.record)
         emit(env, instance, index=len(calls))
     monkeypatch.setattr(env.native, "processText2Speech", native)
     _, _, call = speak(env, ("hello", change, "bonjour"))
@@ -965,21 +864,12 @@ def test_direct_cancel_after_idle_return_still_invalidates_original_work(env, mo
     prove_fake_quiescence(env, monkeypatch)
     monkeypatch.setattr(env.native, "processText2Speech", lambda *args: None)
     returned, release = Event(), Event()
-    if hosted(env):
-        retire = env.core._segmentHost.retire
-        def after_native(record, **kwargs):
-            returned.set()
-            assert release.wait(2)
-            return retire(record, **kwargs)
-        monkeypatch.setattr(env.core._segmentHost, "retire", after_native)
-    else:
-        run_speech = env.core._run_speech
-        def after_idle(commands, work):
-            result = run_speech(commands, work)
-            returned.set()
-            assert release.wait(2)
-            return result
-        monkeypatch.setattr(env.core, "_run_speech", after_idle)
+    retire = env.core._segmentHost.retire
+    def after_native(record, **kwargs):
+        returned.set()
+        assert release.wait(2)
+        return retire(record, **kwargs)
+    monkeypatch.setattr(env.core._segmentHost, "retire", after_native)
     _, _, call = speak(env)
     assert returned.wait(1)
     env.core.cancel()
@@ -1458,7 +1348,7 @@ def test_failed_cancelled_pause_reconciliation_blocks_fresh_speech(env, monkeypa
         if fresh is None:
             fresh = fresh_speech()
         if speech_path == "legacy":
-            if hosted(env) and fresh_during_pause:
+            if fresh_during_pause:
                 # Queued before the fault: the worker drops it, nothing is raised.
                 finish(fresh)
             else:
@@ -1470,8 +1360,8 @@ def test_failed_cancelled_pause_reconciliation_blocks_fresh_speech(env, monkeypa
             assert env.events[0].segment_id == 18
             assert env.events[0].error is error
         assert native_calls == []
-        # VE (async): speech queued before the fault still releases its DONE.
-        assert len(env.dones) == (1 if hosted(env) and speech_path == "legacy" and fresh_during_pause else 0)
+        # Async speak(): speech queued before the fault still releases its DONE.
+        assert len(env.dones) == (1 if speech_path == "legacy" and fresh_during_pause else 0)
         assert player.idles == 0
         # Clearing cancellation cannot clear an unknown player state fault.
         env.core.cancel()
@@ -1521,11 +1411,8 @@ def test_resume_failure_faults_active_work_and_suppresses_drain(env, monkeypatch
             env.core.pause(False)
         assert failed_resume_states == [True]
         if speech_path == "legacy":
-            if hosted(env):
-                # speak() returned once queued; the fault suppresses its DONE.
-                finish(speech)
-            else:
-                assert_operation_failed(speech, error)
+            # speak() returned once queued; the fault suppresses its DONE.
+            finish(speech)
         else:
             finish(speech)
             assert len(env.events) == 1
@@ -1533,8 +1420,8 @@ def test_resume_failure_faults_active_work_and_suppresses_drain(env, monkeypatch
             assert env.events[0].source_id is context.source_id
             assert env.events[0].segment_id == 17
             assert env.events[0].error is error
-        # VE (async): the failed ordinary request still releases its DONE.
-        assert len(env.dones) == (1 if hosted(env) and speech_path == "legacy" else 0)
+        # Async speak(): the failed ordinary request still releases its DONE.
+        assert len(env.dones) == (1 if speech_path == "legacy" else 0)
     finally:
         # Release the pre-fix paused work so RED does not leak a thread.
         env.core.cancel()
diff --git a/tests/test_worldvoice_cancel_wrappers.py b/tests/test_worldvoice_cancel_wrappers.py
index 51d75fc..e6049bf 100644
--- a/tests/test_worldvoice_cancel_wrappers.py
+++ b/tests/test_worldvoice_cancel_wrappers.py
@@ -67,7 +67,7 @@ def emit_audio(core, types, payload=b"new", done_result=None):
 	callback = core._veCallbackHandler
 	if done_result is None:
 		done_result = types.NUAN_OK
-	native = getattr(core, "_nativeCall", None) or getattr(core, "_nativeWork", None)
+	native = getattr(core, "_nativeCall", None)
 	instance = native.instance if native is not None else None
 	out_data = types.VE_OUTDATA()
 	assert callback(instance, None, native_message(types, types.VE_MSG_OUTBUFREQ, out_data)) == types.NUAN_OK
```

- [ ] **Step 2: Run the tests**

Run: `python3 -m pytest tests -q 2>&1 | tail -1`
Expected: `1378 passed`, with no skipped.

Run: `python3 -m pytest tests/test_vocalizer_segment_drain.py tests/test_worldvoice_cancel_wrappers.py -q 2>&1 | tail -1; grep -n "hosted(\|_segmentLifecycle\b\|_nativeWork\|_run_speech\|_segmentBindings\|VE lifecycle adapter" tests/*.py`
Expected: `233 passed`, then no grep output.

- [ ] **Step 3: Commit**

```bash
git add tests/test_vocalizer_segment_drain.py tests/test_worldvoice_cancel_wrappers.py tests/engine_contract_harness.py \
	tests/test_runtime_completion_policies.py tests/test_runtime_drain_integration.py tests/test_sapi5_segment_drain.py
git commit -m "test: read segment state only through SegmentHost and merge the VE/Cerence twins

Every engine runs on SegmentHost, so the fallbacks to a wrapper-owned
SegmentLifecycle were dead. The VE and Cerence copies of two shared-lifecycle
tests become one engine-neutral test each; the suite has no skips left.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: SegmentLifecycle becomes a private module of SegmentHost

Spec §1, §2.5 to §2.8.

**Files:**
- Rename: `addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py` → `addon/synthDrivers/WorldVoice/runtime/_segmentLifecycle.py`. Delete `SegmentOperation.sink`/`has_started`/`is_retired`, `SegmentLifecycle.reject_pending`/`is_resource_busy`, and add the docstring line.
- Modify: `addon/synthDrivers/WorldVoice/runtime/segmentHost.py:25` (import)
- Modify: `addon/synthDrivers/WorldVoice/runtime/playbackWork.py`: delete `_NativeCall`, `CallbackLease` and `CallbackGate` and the unused `Condition` import, and update the docstring.
- Test: `tests/test_lifecycle_private_access.py` (4 new guard tests)
- Modify: tests that load the module by name:
  - `engine_contract_harness.py`
  - `test_espeak_segment_drain.py`, `test_onecore_segment_drain.py`, `test_rhvoice_segment_drain.py`, `test_sapi5_segment_drain.py`, `test_vocalizer_segment_drain.py`
  - `test_segment_host.py`, `test_segment_lifecycle.py`
- Modify: `tests/test_segment_lifecycle.py`:
  - `reject_pending` → `fail`;
  - two query tests read the private state;
  - `is_resource_busy()` → `_resource_busy`.
- Modify: `tests/test_playback_work.py` (delete the 6 `CallbackGate` tests)

**Interfaces:**
- Consumes: Task 2's `lifecycle_of(env)`.
- Produces: module `synthDrivers.WorldVoice.runtime._segmentLifecycle` with `SegmentLifecycle`, `SegmentOperation`, `ProducerLease` and `SegmentEngineHooks`. `SegmentHost` is unchanged.

- [ ] **Step 1: Write the guard tests**

Save as `$PATCHES/t3-tests.patch`, then run `git apply $PATCHES/t3-tests.patch`:

```diff
diff --git a/tests/test_lifecycle_private_access.py b/tests/test_lifecycle_private_access.py
index 4cfcd29..ae7c703 100644
--- a/tests/test_lifecycle_private_access.py
+++ b/tests/test_lifecycle_private_access.py
@@ -1,9 +1,12 @@
-"""Engine wrappers use the lifecycle's public API, never its private state."""
+"""SegmentLifecycle is internal to SegmentHost; engine wrappers use only the host."""
 
+import ast
 import re
 from pathlib import Path
 
-DRIVERS = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice/driver"
+ADDON = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice"
+RUNTIME = ADDON / "runtime"
+DRIVERS = ADDON / "driver"
 LIFECYCLE_OBJECTS = r"(?:operation|lifecycle|_lifecycle|_segmentLifecycle)"
 PRIVATE_ACCESS = re.compile(rf"(?<![A-Za-z0-9]){LIFECYCLE_OBJECTS}\._(\w+)")
 PRIVATE_GETATTR = re.compile(
@@ -45,12 +48,53 @@ def test_wrappers_do_not_touch_lifecycle_private_state():
 	assert found == []
 
 
-# Wrappers moved onto SegmentHost; the host owns their lifecycle entirely.
-MIGRATED = ("Espeak", "SAPI5", "RHVoice", "OneCore", "VE", "Cerence")
+WRAPPERS = ("Espeak", "SAPI5", "RHVoice", "OneCore", "VE", "Cerence")
+LIFECYCLE_MODULES = ("_segmentLifecycle", "segmentLifecycle")
 
 
-def test_migrated_wrappers_only_use_the_segment_host():
-	for name in MIGRATED:
+def _imported_modules(path):
+	tree = ast.parse(path.read_text(encoding="utf-8"))
+	for node in ast.walk(tree):
+		if isinstance(node, ast.ImportFrom):
+			if node.module:
+				yield node.module
+			yield from (alias.name for alias in node.names)
+		elif isinstance(node, ast.Import):
+			yield from (alias.name for alias in node.names)
+
+
+def _methods(path, class_name):
+	tree = ast.parse(path.read_text(encoding="utf-8"))
+	cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
+	return {node.name for node in cls.body if isinstance(node, ast.FunctionDef)}
+
+
+def test_only_the_segment_host_imports_the_lifecycle():
+	importers = sorted(
+		path.relative_to(ADDON).as_posix()
+		for path in ADDON.rglob("*.py")
+		if any(name.split(".")[-1] in LIFECYCLE_MODULES for name in _imported_modules(path))
+	)
+	assert importers == ["runtime/segmentHost.py"]
+
+
+def test_the_lifecycle_module_is_private():
+	assert not (RUNTIME / "segmentLifecycle.py").exists()
+	assert (RUNTIME / "_segmentLifecycle.py").is_file()
+
+
+def test_wrappers_only_use_the_segment_host():
+	for name in WRAPPERS:
 		text = (DRIVERS / name / "__init__.py").read_text(encoding="utf-8")
 		assert "SegmentHost" in text, name
-		assert "_segmentLifecycle" not in text and "SegmentLifecycle" not in text, name
+		for banned in ("_lifecycle", "SegmentLifecycle", "segmentLifecycle", "CallbackGate"):
+			assert banned not in text, (name, banned)
+
+
+def test_wrapper_era_lifecycle_api_is_gone():
+	lifecycle = RUNTIME / "_segmentLifecycle.py"
+	assert not {"is_resource_busy", "reject_pending"} & _methods(lifecycle, "SegmentLifecycle")
+	assert not {"sink", "has_started", "is_retired"} & _methods(lifecycle, "SegmentOperation")
+	playback = (RUNTIME / "playbackWork.py").read_text(encoding="utf-8")
+	for name in ("CallbackGate", "CallbackLease", "_NativeCall"):
+		assert f"class {name}" not in playback, name
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests -q 2>&1 | grep -E "^FAILED|^[0-9]+ (passed|failed)" | sed 's/ - .*//'`
Expected: `2 failed, 1379 passed`. The failures:
- `tests/test_lifecycle_private_access.py::test_the_lifecycle_module_is_private`: `segmentLifecycle.py` still exists.
- `tests/test_lifecycle_private_access.py::test_wrapper_era_lifecycle_api_is_gone`: `_segmentLifecycle.py` does not exist yet.

`test_only_the_segment_host_imports_the_lifecycle` and `test_wrappers_only_use_the_segment_host` already pass, because today only `segmentHost.py` imports the lifecycle. Mutations M3a–M3b prove they bite.

- [ ] **Step 3: Rename the module, delete the dead API and adapt the tests**

Save as `$PATCHES/t3-impl.patch`, then run `git apply $PATCHES/t3-impl.patch`. The patch includes the rename, which `git apply` performs:

```diff
diff --git a/addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py b/addon/synthDrivers/WorldVoice/runtime/_segmentLifecycle.py
similarity index 94%
rename from addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py
rename to addon/synthDrivers/WorldVoice/runtime/_segmentLifecycle.py
index b27bbe6..49d2523 100644
--- a/addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py
+++ b/addon/synthDrivers/WorldVoice/runtime/_segmentLifecycle.py
@@ -1,5 +1,7 @@
 """Shared ownership and retirement of one contextual speech segment at a time.
 
+Internal to SegmentHost; nothing else imports this module.
+
 Engine hooks establish native and playback boundaries. This coordinator never
 infers native quiescence from an empty callback count alone.
 
@@ -77,21 +79,6 @@ class SegmentOperation:
 			failed = self._error is not None
 		return not failed and self.work.is_valid()
 
-	@property
-	def sink(self) -> SegmentEventSink:
-		"""The sink this operation was accepted with."""
-		return self._sink
-
-	def has_started(self) -> bool:
-		"""True once run() began or the operation was rejected before running."""
-		with self._lifecycle._condition:
-			return self._run_started
-
-	def is_retired(self) -> bool:
-		"""True once the operation released the native/player resource."""
-		with self._lifecycle._condition:
-			return self._retired
-
 
 class ProducerLease:
 	"""A producer's original operation, retained until its actual work exits."""
@@ -160,14 +147,6 @@ class SegmentLifecycle:
 			self._reject_pending_locked(operation, error)
 			return operation
 
-	def reject_pending(self, operation: SegmentOperation, error: Exception) -> None:
-		"""Fail accepted work that never acquired native/player resources."""
-		self._require_operation(operation)
-		with self._condition:
-			if operation not in self._operations or operation._run_started:
-				raise RuntimeError("segment operation is not pending")
-			self._reject_pending_locked(operation, error)
-
 	def _reject_pending_locked(self, operation: SegmentOperation, error: Exception) -> None:
 		operation._run_started = True
 		operation._admitting = False
@@ -211,10 +190,6 @@ class SegmentLifecycle:
 		if thread is not current_thread():
 			thread.join(timeout)
 
-	def is_resource_busy(self) -> bool:
-		with self._condition:
-			return self._resource_busy
-
 	def wait_idle(
 		self,
 		*,
diff --git a/addon/synthDrivers/WorldVoice/runtime/playbackWork.py b/addon/synthDrivers/WorldVoice/runtime/playbackWork.py
index a161f46..54b5e9a 100644
--- a/addon/synthDrivers/WorldVoice/runtime/playbackWork.py
+++ b/addon/synthDrivers/WorldVoice/runtime/playbackWork.py
@@ -1,14 +1,12 @@
-"""Segment lifetime and callback ownership, independent of native SDKs.
+"""Segment playback work and drain-support evidence, independent of native SDKs.
 
-Drivers own playback barriers and proof of native quiescence. They must retain
-a callback lease through real feed and any final stop of invalidated playback:
-admit -> feed outside locks -> stop if invalid -> release. The next native call
-cannot take over that player's resources until native finish and every release.
+Drivers own playback barriers and proof of native quiescence; SegmentHost holds
+callback consumers through real feed and any final stop of invalidated playback.
 """
 
 from collections.abc import Callable
 from dataclasses import dataclass
-from threading import Condition, Lock
+from threading import Lock
 
 from .models import EventKind, PlaybackContext, PlaybackEvent, SegmentEventSink
 from .session import CancellationView
@@ -107,99 +105,3 @@ class PlaybackWork:
 		if self._on_cancel is not None:
 			self._on_cancel()
 		return True
-
-
-class _NativeCall:
-	"""Opaque token retaining a call's identity until its consumers retire."""
-
-	def __init__(self, gate, work):
-		self._gate = gate
-		self._work = work
-		self._admitting = True
-		self._finished = False
-		self._callbacks = 0
-
-
-class CallbackLease:
-	"""One admitted callback; release only after all its external work exits."""
-
-	def __init__(self, gate, call):
-		self._gate = gate
-		self._call = call
-		self._closed = False
-
-	@property
-	def work(self) -> PlaybackWork:
-		return self._call._work
-
-	@property
-	def call_token(self) -> object:
-		return self._call
-
-	def close(self) -> None:
-		with self._gate._condition:
-			if self._closed:
-				return
-			self._closed = True
-			self._call._callbacks -= 1
-			self._gate._condition.notify_all()
-
-
-class CallbackGate:
-	"""Serialize native calls without guessing when the SDK stops callbacks.
-
-	State/counters are protected by the condition; its waits release the lock.
-	No native calls, player operations or event delivery run under this lock.
-	Gate admission may read work validity; PlaybackWork never acquires the gate.
-	"""
-
-	def __init__(self):
-		self._condition = Condition()
-		self._current = None
-
-	def begin_native(self, work: PlaybackWork) -> object:
-		"""Wait for the previous native finish and all its callbacks to exit."""
-		with self._condition:
-			self._condition.wait_for(
-				lambda: self._current is None or (self._current._finished and self._current._callbacks == 0),
-			)
-			call = _NativeCall(self, work)
-			self._current = call
-			return call
-
-	def enter_callback(self) -> CallbackLease | None:
-		with self._condition:
-			call = self._current
-			if call is None or not call._admitting or not call._work.is_valid():
-				return None
-			call._callbacks += 1
-			return CallbackLease(self, call)
-
-	def close(self, call_token: object) -> None:
-		"""Stop new admission; this does not declare native quiescence."""
-		call = self._call(call_token)
-		with self._condition:
-			call._admitting = False
-
-	def finish_native(self, call_token: object) -> None:
-		"""Driver declaration: this call can no longer initiate callbacks."""
-		call = self._call(call_token)
-		with self._condition:
-			call._admitting = False
-			call._finished = True
-			self._condition.notify_all()
-
-	def wait_retired(self, call_token: object) -> None:
-		"""Wait for admitted leases, independently of the native finish.
-
-		Close admission first when a stable zero-callback barrier is needed.
-		A return here alone never permits a new native call.
-		"""
-		call = self._call(call_token)
-		with self._condition:
-			self._condition.wait_for(lambda: call._callbacks == 0)
-
-	def _call(self, token: object) -> _NativeCall:
-		if not isinstance(token, _NativeCall) or token._gate is not self:
-			raise ValueError("Native call token does not belong to this gate")
-		return token
diff --git a/addon/synthDrivers/WorldVoice/runtime/segmentHost.py b/addon/synthDrivers/WorldVoice/runtime/segmentHost.py
index d636b44..da674a6 100644
--- a/addon/synthDrivers/WorldVoice/runtime/segmentHost.py
+++ b/addon/synthDrivers/WorldVoice/runtime/segmentHost.py
@@ -22,7 +22,7 @@ from typing import Protocol
 
 from .models import EventKind, PlaybackContext, PlaybackEvent, SegmentEventSink, SpeechCommands
 from .playbackWork import PlaybackWork
-from .segmentLifecycle import ProducerLease, SegmentLifecycle, SegmentOperation
+from ._segmentLifecycle import ProducerLease, SegmentLifecycle, SegmentOperation
 from .session import CancellationView
 
 
diff --git a/tests/engine_contract_harness.py b/tests/engine_contract_harness.py
index a825522..e7ca6f2 100644
--- a/tests/engine_contract_harness.py
+++ b/tests/engine_contract_harness.py
@@ -23,7 +23,7 @@ from worldvoice_cancel_wrapper_harness import load_real_driver_with_native_stubs
 def _fresh_lifecycle_module(monkeypatch):
 	# Each loader reloads runtime models; reload the coordinator too so its
 	# event enum belongs to that same runtime copy.
-	monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentLifecycle", raising=False)
+	monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime._segmentLifecycle", raising=False)
 	monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentHost", raising=False)
 
 
diff --git a/tests/test_espeak_segment_drain.py b/tests/test_espeak_segment_drain.py
index 3c2cee1..b53aa71 100644
--- a/tests/test_espeak_segment_drain.py
+++ b/tests/test_espeak_segment_drain.py
@@ -11,7 +11,7 @@ from espeak_drain_harness import finish, load_espeak, speak, wait_event
 
 @pytest.fixture
 def env(monkeypatch, tmp_path):
-    monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentLifecycle", raising=False)
+    monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime._segmentLifecycle", raising=False)
     monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentHost", raising=False)
     result = load_espeak(monkeypatch, tmp_path)
     yield result
@@ -83,7 +83,7 @@ def test_empty_audio_still_waits_for_idle_and_native_retirement(env):
 
 
 def test_espeak_shared_lifecycle_waits_for_fifo_and_empty_audio_idle(env):
-    lifecycle = importlib.import_module(env.rt.package.__name__ + ".segmentLifecycle")
+    lifecycle = importlib.import_module(env.rt.package.__name__ + "._segmentLifecycle")
     env.native.next_scripts.append({"empty": True})
     _, context, events = speak(env, commands=("",))
     call = env.native.wait_calls(1)
@@ -105,7 +105,7 @@ def test_espeak_shared_lifecycle_waits_for_fifo_and_empty_audio_idle(env):
 
 
 def test_espeak_token_cancel_after_feed_discards_pcm_before_successor(env):
-    lifecycle = importlib.import_module(env.rt.package.__name__ + ".segmentLifecycle")
+    lifecycle = importlib.import_module(env.rt.package.__name__ + "._segmentLifecycle")
     env.native.next_scripts.append({"hold_terminal": True})
     token, _, cancelled_events = speak(env)
     first = env.native.wait_calls(1)
diff --git a/tests/test_onecore_segment_drain.py b/tests/test_onecore_segment_drain.py
index caefa7a..a103b5a 100644
--- a/tests/test_onecore_segment_drain.py
+++ b/tests/test_onecore_segment_drain.py
@@ -10,7 +10,7 @@ from onecore_drain_harness import VERSION, in_thread, load_onecore
 
 @pytest.fixture
 def env(monkeypatch):
-    monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentLifecycle", raising=False)
+    monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime._segmentLifecycle", raising=False)
     monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentHost", raising=False)
     result = load_onecore(monkeypatch)
     yield result
diff --git a/tests/test_playback_work.py b/tests/test_playback_work.py
index 2a65e6a..c8cbc52 100644
--- a/tests/test_playback_work.py
+++ b/tests/test_playback_work.py
@@ -170,169 +170,6 @@ def test_concurrent_terminal_calls_notify_only_once(work_env):
     assert len(events) == 1
 
 
-def test_callbacks_require_open_valid_native_work(work_env):
-    rt, _, _, _, work = work_env
-    gate = rt.playback_work.CallbackGate()
-    assert gate.enter_callback() is None
-    call_token = gate.begin_native(work)
-    lease = gate.enter_callback()
-    assert lease.work is work
-    assert lease.call_token is call_token
-    with pytest.raises(AttributeError):
-        lease.work = new_work(rt, work)
-    with pytest.raises(AttributeError):
-        lease.call_token = object()
-    gate.close(call_token)
-    gate.close(call_token)
-    assert gate.enter_callback() is None
-    lease.close()
-    lease.close()
-    gate.wait_retired(call_token)
-    gate.finish_native(call_token)
-
-
-@pytest.mark.parametrize("invalidate", ["cancel", "token", "fail", "drain"])
-def test_invalid_work_refuses_callback_admission(work_env, invalidate):
-    rt, token, _, _, work = work_env
-    gate = rt.playback_work.CallbackGate()
-    call_token = gate.begin_native(work)
-    if invalidate == "token":
-        token.cancel()
-    elif invalidate == "fail":
-        work.fail(RuntimeError("native failed"))
-    elif invalidate == "drain":
-        work.complete_drained()
-    else:
-        work.cancel()
-    assert gate.enter_callback() is None
-    gate.finish_native(call_token)
-
-
-def test_zero_callbacks_does_not_declare_native_quiescence(work_env):
-    rt, _, _, _, work = work_env
-    gate = rt.playback_work.CallbackGate()
-    previous = gate.begin_native(work)
-    gate.close(previous)
-    # Retirement only observes admitted leases, not the SDK contract.
-    assert ThreadCall(lambda: gate.wait_retired(previous)).finish() is None
-    next_call = ThreadCall(lambda: gate.begin_native(new_work(rt, work)))
-    try:
-        next_call.assert_blocked()
-    finally:
-        gate.finish_native(previous)
-    following = next_call.finish()
-    assert following is not previous
-    gate.finish_native(following)
-
-
-def test_native_finish_does_not_release_an_entered_callback(work_env):
-    rt, _, context, _, work = work_env
-    gate = rt.playback_work.CallbackGate()
-    previous = gate.begin_native(work)
-    lease = gate.enter_callback()
-    gate.finish_native(previous)
-    assert gate.enter_callback() is None
-    next_work = new_work(rt, work)
-    next_call = ThreadCall(lambda: gate.begin_native(next_work))
-    retired = ThreadCall(lambda: gate.wait_retired(previous))
-    try:
-        next_call.assert_blocked()
-        retired.assert_blocked()
-        assert lease.work is work
-        assert lease.work.context is context
-    finally:
-        lease.close()
-    assert retired.finish() is None
-    following = next_call.finish()
-    # Old identity/duplicate release cannot alter the new call's admission.
-    gate.close(previous)
-    gate.finish_native(previous)
-    lease.close()
-    new_lease = gate.enter_callback()
-    assert new_lease.work is next_work
-    assert new_lease.call_token is following
-    assert lease.work.context is context
-    new_lease.close()
-    gate.finish_native(following)
-
-
-def test_retirement_waits_for_every_lease(work_env):
-    rt, _, _, _, work = work_env
-    gate = rt.playback_work.CallbackGate()
-    call_token = gate.begin_native(work)
-    first, second = gate.enter_callback(), gate.enter_callback()
-    gate.close(call_token)
-    retired = ThreadCall(lambda: gate.wait_retired(call_token))
-    try:
-        retired.assert_blocked()
-        first.close()
-        first.close()
-        retired.assert_blocked()
-    finally:
-        second.close()
-    assert retired.finish() is None
-    gate.finish_native(call_token)
-
-
-def test_cancelled_admitted_feed_stops_before_new_native_work(work_env):
-    rt, _, _, events, work = work_env
-    gate = rt.playback_work.CallbackGate()
-    previous = gate.begin_native(work)
-    admitted, start_feed, feed_started, finish_feed = (Event() for _ in range(4))
-    actions = []
-    playing = Event()
-
-    def stop():
-        actions.append("stop old playback")
-        playing.clear()
-
-    def callback_feed():
-        lease = gate.enter_callback()
-        assert lease is not None
-        try:
-            admitted.set()
-            assert start_feed.wait(1)
-            # Real feed runs outside the gate: it can start after cancel's stop.
-            actions.append("old real feed")
-            playing.set()
-            feed_started.set()
-            assert finish_feed.wait(1)
-        finally:
-            if not lease.work.is_valid():
-                stop()
-            lease.close()
-
-    old_feed = ThreadCall(callback_feed)
-    assert admitted.wait(1)
-    gate.close(previous)
-    work.cancel()
-    stop()
-    gate.finish_native(previous)
-    next_work = new_work(rt, work)
-
-    def next_native():
-        call_token = gate.begin_native(next_work)
-        assert not playing.is_set()
-        actions.append("new native started")
-        return call_token
-
-    following = ThreadCall(next_native)
-    try:
-        following.assert_blocked()
-        start_feed.set()
-        assert feed_started.wait(1)
-        assert playing.is_set()
-        following.assert_blocked()
-    finally:
-        start_feed.set()
-        finish_feed.set()
-    old_feed.finish()
-    gate.finish_native(following.finish())
-    assert actions == ["stop old playback", "old real feed", "stop old playback", "new native started"]
-    assert work.complete_drained() is False
-    assert events == []
-
-
 def test_direct_cancel_notifies_owner_after_releasing_the_work_lock(work_env):
     rt, token, context, events, _ = work_env
     seen = []
diff --git a/tests/test_rhvoice_segment_drain.py b/tests/test_rhvoice_segment_drain.py
index b511ded..aa7b50c 100644
--- a/tests/test_rhvoice_segment_drain.py
+++ b/tests/test_rhvoice_segment_drain.py
@@ -14,7 +14,7 @@ from rhvoice_drain_harness import finish, load_rhvoice, speak
 
 @pytest.fixture
 def env(monkeypatch, tmp_path):
-    monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentLifecycle", raising=False)
+    monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime._segmentLifecycle", raising=False)
     monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentHost", raising=False)
     result = load_rhvoice(monkeypatch, tmp_path)
     yield result
diff --git a/tests/test_sapi5_segment_drain.py b/tests/test_sapi5_segment_drain.py
index d583140..95b1847 100644
--- a/tests/test_sapi5_segment_drain.py
+++ b/tests/test_sapi5_segment_drain.py
@@ -204,8 +204,8 @@ def load_sapi5(monkeypatch, *, rt=None, scheduler=None, voice_base=object, comma
     package("synthDrivers.WorldVoice", ROOT / "addon/synthDrivers/WorldVoice")
     package("synthDrivers.WorldVoice.driver", ROOT / "addon/synthDrivers/WorldVoice/driver", Voice=voice_base)
     rt = rt or load_runtime(monkeypatch, "synthDrivers.WorldVoice.runtime")
-    load("synthDrivers.WorldVoice.runtime.segmentLifecycle",
-        ROOT / "addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py")
+    load("synthDrivers.WorldVoice.runtime._segmentLifecycle",
+        ROOT / "addon/synthDrivers/WorldVoice/runtime/_segmentLifecycle.py")
     load("synthDrivers.WorldVoice.runtime.segmentHost",
         ROOT / "addon/synthDrivers/WorldVoice/runtime/segmentHost.py")
     scheduler = scheduler or load_scheduler(monkeypatch, rt)
@@ -303,7 +303,7 @@ def test_sapi5_wasapi_shared_lifecycle_waits_for_endstream_pcm_and_idle(env):
     _, context, events = speak(env)
     env.native.wait_calls(1)
     native = env.driver._segmentHost.current()
-    lifecycle = importlib.import_module(env.rt.package.__name__ + ".segmentLifecycle")
+    lifecycle = importlib.import_module(env.rt.package.__name__ + "._segmentLifecycle")
     assert isinstance(native.operation, lifecycle.SegmentOperation)
     env.player.feed_release.clear()
     pcm = Thread(target=lambda: env.native.audio.ISequentialStream_RemoteWrite(None, None, 8, None), daemon=True)
diff --git a/tests/test_segment_host.py b/tests/test_segment_host.py
index eac00ee..b8a1eec 100644
--- a/tests/test_segment_host.py
+++ b/tests/test_segment_host.py
@@ -78,7 +78,7 @@ def env(monkeypatch, request):
 	options = getattr(request, "param", {})
 	rt = load_runtime(monkeypatch)
 	scheduler = load_scheduler(monkeypatch, rt)
-	_load(monkeypatch, rt, "segmentLifecycle")
+	_load(monkeypatch, rt, "_segmentLifecycle")
 	module = _load(monkeypatch, rt, "segmentHost")
 	strategy = FakeStrategy()
 	host = module.SegmentHost("Fake", strategy, **options)
diff --git a/tests/test_segment_lifecycle.py b/tests/test_segment_lifecycle.py
index 1556b2f..be39194 100644
--- a/tests/test_segment_lifecycle.py
+++ b/tests/test_segment_lifecycle.py
@@ -119,8 +119,8 @@ class Hooks:
 def env(monkeypatch):
     rt = load_runtime(monkeypatch)
     scheduler = load_scheduler(monkeypatch, rt)
-    name = f"{rt.package.__name__}.segmentLifecycle"
-    spec = importlib.util.spec_from_file_location(name, RUNTIME / "segmentLifecycle.py")
+    name = f"{rt.package.__name__}._segmentLifecycle"
+    spec = importlib.util.spec_from_file_location(name, RUNTIME / "_segmentLifecycle.py")
     module = importlib.util.module_from_spec(spec)
     monkeypatch.setitem(sys.modules, name, module)
     spec.loader.exec_module(module)
@@ -656,7 +656,7 @@ def test_pending_operation_rejection_delivers_after_latched_fault(env):
     pending, context = accept(18)
     error = OSError("native resources unsafe")
     lifecycle._latch_fault(pending, error)
-    lifecycle.reject_pending(pending, error)
+    lifecycle.fail(pending, error)
     events.wait_for_count(1)
     assert [(event.source_id, event.segment_id, event.error) for event in events] == [
         (context.source_id, 18, error)]
@@ -668,7 +668,7 @@ def test_retirement_callback_runs_when_cancel_suppresses_delivery(env):
     retired = Event()
     operation, _ = accept(18, on_retired=lambda owner: retired.set())
     operation.work.token.cancel()
-    lifecycle.reject_pending(operation, RuntimeError("never submitted"))
+    lifecycle.fail(operation, RuntimeError("never submitted"))
     assert retired.wait(1)
     assert operation not in lifecycle._operations
     assert events == []
@@ -687,7 +687,7 @@ def test_idle_delivery_thread_releases_a_retired_operation(env):
     reference = weakref.ref(sink)
     operation, _ = accept(18, sink, on_retired=lambda owner: retired.set())
     operation.work.token.cancel()
-    lifecycle.reject_pending(operation, RuntimeError("never submitted"))
+    lifecycle.fail(operation, RuntimeError("never submitted"))
     assert retired.wait(1)
     del operation, sink
     for _ in range(100):
@@ -717,11 +717,11 @@ def test_terminate_cancels_previously_accepted_pending_rejection(env):
     lifecycle, hooks, _, accept = env
     entered, release, rejected = Event(), Event(), RecordedEvents()
     first, _ = accept(20, lambda event: (entered.set(), release.wait(2)))
-    lifecycle.reject_pending(first, RuntimeError("first rejection"))
+    lifecycle.fail(first, RuntimeError("first rejection"))
     assert entered.wait(1)
     second, _ = accept(21, rejected.append)
     error = OSError("second rejection")
-    lifecycle.reject_pending(second, error)
+    lifecycle.fail(second, error)
     lifecycle.terminate()
     release.set()
     with lifecycle._condition:
@@ -851,28 +851,26 @@ def test_queued_run_wakes_when_cancelled(env, cancel):
     owner_call.finish()
 
 
-def test_operation_queries_follow_run_and_retirement(env):
+def test_operation_state_follows_run_and_retirement(env):
     lifecycle, hooks, events, accept = env
-    sink = events.append
-    operation, _ = accept(1, sink=sink)
-    assert operation.sink is sink
-    assert not operation.has_started()
-    assert not operation.is_retired()
+    operation, _ = accept(1)
+    assert not operation._run_started
+    assert not operation._retired
     call = Call(lambda: lifecycle.run(operation, ("hello",)))
     assert hooks.boundary_entered.wait(1)
-    assert operation.has_started()
-    assert not operation.is_retired()
+    assert operation._run_started
+    assert not operation._retired
     hooks.release_boundary.set()
     call.finish()
-    assert operation.is_retired()
+    assert operation._retired
 
 
-def test_rejected_operation_reports_started_and_retired(env):
+def test_failed_pending_operation_is_started_and_retired(env):
     lifecycle, hooks, events, accept = env
     operation, _ = accept(1)
-    lifecycle.reject_pending(operation, RuntimeError("rejected"))
-    assert operation.has_started()
-    assert operation.is_retired()
+    lifecycle.fail(operation, RuntimeError("rejected"))
+    assert operation._run_started
+    assert operation._retired
 
 
 def test_delivery_thread_identity_and_join(env):
@@ -899,7 +897,7 @@ def test_wait_idle_returns_true_when_resource_is_released(env):
     lifecycle, hooks, events, accept = env
     assert lifecycle.wait_idle() is True
     _, owner_call = _hold_resource(env)
-    assert lifecycle.is_resource_busy()
+    assert lifecycle._resource_busy
     results = []
     waiting = Call(lambda: results.append(lifecycle.wait_idle()))
     waiting.blocked()
@@ -907,7 +905,7 @@ def test_wait_idle_returns_true_when_resource_is_released(env):
     owner_call.finish()
     waiting.finish()
     assert results == [True]
-    assert not lifecycle.is_resource_busy()
+    assert not lifecycle._resource_busy
 
 
 def test_wait_idle_wakes_on_token_cancel_without_polling(env):
diff --git a/tests/test_vocalizer_segment_drain.py b/tests/test_vocalizer_segment_drain.py
index 6ac72df..10677b2 100644
--- a/tests/test_vocalizer_segment_drain.py
+++ b/tests/test_vocalizer_segment_drain.py
@@ -15,7 +15,7 @@ from test_worldvoice_cancel_wrappers import Token, native_message
 def env(request, monkeypatch):
     # The harness reloads runtime models for every engine case. Reload the
     # coordinator too so its event enum belongs to that same runtime copy.
-    monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentLifecycle", raising=False)
+    monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime._segmentLifecycle", raising=False)
     monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentHost", raising=False)
     result = load_real_driver_with_native_stubs(monkeypatch, request.param)
     result.core = result.new_core()
```

- [ ] **Step 4: Run the tests and the acceptance checks**

Run: `python3 -m pytest tests -q 2>&1 | tail -1`
Expected: `1372 passed`

Run:
```bash
R=addon/synthDrivers/WorldVoice/runtime
ruff format --check addon | tail -1
test ! -e $R/segmentLifecycle.py && echo gone
grep -rn "_segmentLifecycle\|segmentLifecycle" addon --include=*.py | grep -v "^$R/_segmentLifecycle.py"
grep -rn "CallbackGate\|CallbackLease" addon --include=*.py
git diff -M master --stat -- addon | cat
```
Expected:
- `53 files already formatted`;
- `gone`;
- one grep line: `addon/synthDrivers/WorldVoice/runtime/segmentHost.py:25:from ._segmentLifecycle import ProducerLease, SegmentLifecycle, SegmentOperation`;
- no `CallbackGate` output;
- the stat lists only `.../{segmentLifecycle.py => _segmentLifecycle.py}`, `.../runtime/playbackWork.py` and `.../runtime/segmentHost.py`: `3 files changed, 7 insertions(+), 130 deletions(-)`.

- [ ] **Step 5: Commit**

```bash
git add addon/synthDrivers/WorldVoice/runtime/_segmentLifecycle.py addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py \
	addon/synthDrivers/WorldVoice/runtime/segmentHost.py addon/synthDrivers/WorldVoice/runtime/playbackWork.py \
	tests/test_lifecycle_private_access.py tests/engine_contract_harness.py tests/test_espeak_segment_drain.py \
	tests/test_onecore_segment_drain.py tests/test_rhvoice_segment_drain.py tests/test_sapi5_segment_drain.py \
	tests/test_segment_host.py tests/test_segment_lifecycle.py tests/test_vocalizer_segment_drain.py tests/test_playback_work.py
git commit -m "refactor(runtime): make SegmentLifecycle a private module of SegmentHost

segmentLifecycle.py becomes _segmentLifecycle.py and only segmentHost.py
imports it. The query API added for wrappers in phase 2 and the unused
CallbackGate are removed; guard tests keep wrappers and the rest of the
add-on on SegmentHost.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Prove the guards bite (mutations M3a–M3d, after the commit)**

```bash
mutate() { python3 - "$1" "$2" "$3" <<'PY'
import sys
p, old, new = sys.argv[1:]
s = open(p).read()
assert s.count(old) == 1, old
open(p, "w").write(s.replace(old, new))
PY
}
check() { timeout 300 python3 -m pytest tests/test_lifecycle_private_access.py -q -p no:cacheprovider 2>&1 | grep -E '^FAILED|^[0-9]+ (passed|failed)' | sed 's/ - .*//'; git checkout -- addon; }
R=addon/synthDrivers/WorldVoice/runtime

echo M3a; mutate addon/synthDrivers/WorldVoice/driver/VE/__init__.py 'from ...runtime.segmentHost import SegmentHost
' 'from ...runtime.segmentHost import SegmentHost
from ...runtime._segmentLifecycle import SegmentLifecycle
'; check
echo M3b; mutate $R/scheduler.py 'from .models import' 'from ._segmentLifecycle import SegmentOperation
from .models import'; check
echo M3c; printf '\n\nclass CallbackGate:\n\tpass\n' >> $R/playbackWork.py; check
echo M3d; mutate $R/_segmentLifecycle.py '	def wait_idle(
' '	def is_resource_busy(self) -> bool:
		return self._resource_busy

	def wait_idle(
'; check
git status --short | grep addon
```

Expected:
- M3a: a wrapper imports the lifecycle. `2 failed, 5 passed`:
  - `test_only_the_segment_host_imports_the_lifecycle`
  - `test_wrappers_only_use_the_segment_host`
- M3b: another runtime module imports it. `1 failed, 6 passed`: `test_only_the_segment_host_imports_the_lifecycle`
- M3c: `CallbackGate` returns. `1 failed, 6 passed`: `test_wrapper_era_lifecycle_api_is_gone`
- M3d: `is_resource_busy` returns. `1 failed, 6 passed`: `test_wrapper_era_lifecycle_api_is_gone`

The final `git status` prints nothing.

---

### Task 4: Final verification

**Files:** none modified.

- [ ] **Step 1: Stability**

Run: `for i in 1 2 3 4 5; do python3 -m pytest tests/test_vocalizer_segment_drain.py tests/test_worldvoice_cancel_wrappers.py tests/test_engine_segment_contract.py tests/test_runtime_drain_integration.py tests/test_f4_engine_adapters.py tests/test_segment_host.py tests/test_segment_lifecycle.py tests/test_playback_work.py -q 2>&1 | tail -1; done | sed 's/ in .*//' | sort | uniq -c`
Expected: one line, `5 404 passed`.

Run: `for i in $(seq 1 20); do python3 -m pytest tests/test_vocalizer_segment_drain.py tests/test_worldvoice_cancel_wrappers.py -q 2>&1 | tail -1; done | sed 's/ in .*//' | sort | uniq -c`
Expected: one line, `20 233 passed`.

- [ ] **Step 2: The engines are untouched and green**

Run: `git diff master --stat -- addon/synthDrivers/WorldVoice/driver`
Expected: no output.

Run: `python3 -m pytest tests/test_onecore_segment_drain.py tests/test_rhvoice_segment_drain.py tests/test_sapi5_segment_drain.py tests/test_espeak_segment_drain.py -q 2>&1 | tail -1`
Expected: `196 passed`.

Run: `python3 -m pytest tests/test_engine_segment_contract.py -q 2>&1 | tail -1`
Expected: `24 passed`, with no skipped.

- [ ] **Step 3: Full suite and protected paths**

Run: `python3 -m pytest tests -q 2>&1 | tail -1`
Expected: `1372 passed`

Run:
```bash
ruff format --check addon | tail -1
ls tests | grep -i neural
git ls-files addon/synthDrivers/WorldVoice/driver/Neural
git log --oneline master..HEAD
```
Expected:
- `53 files already formatted`, then no output from `ls` or `ls-files`.
- The log lists, oldest at the bottom:
  1. `docs: add phase 3e lifecycle internalization design spec`
  2. `docs: add phase 3e implementation plan and amend its spec`
  3. `test: drop the Neural tests and port the voice-switch drain test to VE`
  4. `test: read segment state only through SegmentHost and merge the VE/Cerence twins`
  5. `refactor(runtime): make SegmentLifecycle a private module of SegmentHost`
