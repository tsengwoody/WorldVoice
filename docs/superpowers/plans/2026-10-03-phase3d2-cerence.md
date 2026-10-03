# Phase 3d-2: Cerence Migration to SegmentHost Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- Restore Cerence's inner driver to the original asynchronous `ref/CerenceTTS(min)` structure, keeping the WorldVoice additions the spec lists.
- Move the outer Cerence wrapper onto `SegmentHost`, as a separate copy of the 3d-1 VE design.
- Fix C3 for Cerence and remove the last xfail in the suite.
- Clean up the two small VE leftovers from 3d-1.

**Architecture:**
- **Task 1** is a VE-only refactor:
  - the `_VEStrategy` docstring now names the inner `BgThread` as the worker;
  - `_queueLock` is removed, since host admission already serializes `_enqueue` against `cancel()`.
- **Task 2** has two parts:
  - The inner `driver/Cerence/driver/__init__.py` returns to the original `BgThread` queue:
    - queued `ProcessText2Speech`/`DoneSpeaking`/`TtsSetParamList`;
    - the queue-scanning `getParameters`;
    - the original `cancel`/`terminate`.
    It keeps Sonic, the exponential rate/pitch mapping, the install paths and `_veCallbackHandler`/`_rateBoost`. `setDaemon(True)` becomes `self.daemon = True`.
  - The outer `driver/Cerence/__init__.py` mirrors the VE wrapper:
    - It defines `_CerenceStrategy`, `_CerenceRequest`, `_NativeCall` and `_Begin`/`_NativeTask`/`_Retire`.
    - `cancel()` never joins the BgThread; a closer thread finishes termination.
    - Cerence keeps its own strings, `int(szValue)` bookmarks, the `VE_HSAFE` admission check and its `Voice` class. The variant write is queued.
- Nothing is shared between VE and Cerence. Shared code stays in `runtime/`, which this plan does not change.

**Tech Stack:** Python 3 threading, ctypes, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-10-03-phase3d2-cerence-design.md` (design details: `docs/superpowers/specs/2026-10-03-phase3d1-ve-design.md` §3)

## Global Constraints

- Work on branch `phase3d2-cerence`, cut from `master` at `423ef15`. The spec commit `0c6127a` and the plan commit are on it.
- **Do not change** `addon/synthDrivers/WorldVoice/runtime/` or `addon/synthDrivers/WorldVoice/driver/{OneCore,Espeak,SAPI5,RHVoice}/` (wrappers and inner drivers), or `driver/VE/driver/`. Their tests must pass unchanged.
- The VE outer wrapper changes only by the docstring and the `_queueLock` removal (spec §3).
- The Cerence inner driver is an approved exception to "inner drivers are unmodified" (user, 2026-10-03). It may differ from `ref/CerenceTTS(min)/synthDrivers/CerenceTTS/__init__.py` only by:
  - the kept WorldVoice items;
  - `self.daemon = True`.
  `driver/Cerence/driver/ttsapi/` is not modified.
- Never commit `driver/Neural/`. Neural compatibility is not required.
- No shared VE/Cerence code. New public names are snake_case.
- Every changed `addon/` file passes `ruff format --check`.
- Run from the repo root, since tests need the untracked `ref/`. Stage explicit paths only, and never stage the user's unstaged deletion of `docs/superpowers/finish_task.md`. Never touch `git stash`.
- Baseline before Task 1: `python3 -m pytest tests -q` → `1362 passed, 101 skipped, 1 xfailed`.
- Each code step applies a patch saved verbatim from this plan. Set `PATCHES=$(mktemp -d)` once, save the block to the named file, then run `git apply`.
- **Mutation steps come after the commit step.** They end with `git checkout -- <file>`, which would otherwise discard uncommitted work.
- Every commit message ends with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Deadlock-freedom of Cerence `cancel()`/`terminate()` re-entry.** Cerence now has the same five actors as VE: the scheduler, the inner `BgThread`, native callbacks, lifecycle threads and the delivery thread.
   - `terminate()` re-entered from any of them starts the "WorldVoice Cerence close" thread instead of waiting.
   - Pinned by the following tests, all engine-neutral from Task 2, plus mutation M2h:
     - `test_player_hook_can_reenter_terminate`
     - `test_terminate_waits_for_coordinator_stop`
     - `test_done_listener_can_terminate_without_deadlocking_speech`
     - `test_index_listener_can_terminate_and_retire_native_before_close`
   - The reviewer looks for a closer path that joins a `BgThread` which waits on the closer's own thread.
2. **Queue surgery in Cerence `cancel()`.** `_drop_queued_speech` must:
   - keep `TtsSetParamList` entries, the `Retire` of a begun record, and the ordinary `DoneSpeaking`;
   - drop queued `Begin`s (abandoning their records) and segment `DoneSpeaking` entries.
   - Pinned by `test_cancel_drops_a_segment_queued_behind_the_worker[Cerence]` and `test_cancel_during_contextual_final_idle_releases_waiting_ordinary[Cerence]` (M2b, M2c).
   - The reviewer checks the race where the `BgThread` has popped a `Begin` that has not run yet.
3. **Cerence-only callback paths.**
   - Callback admission rejects a non-`VE_HSAFE` instance (pinned by `test_token_cancellation_rejects_real_callback_before_core_cancel[Cerence]`, M2i).
   - Bookmarks decode with `int(szValue)` (pinned by `test_cerence_bookmark_decodes_szvalue`).
   - The reviewer checks what a malformed `szValue` does on the `BgThread`: it must not wedge the queue or leave a record unretired.
4. **Removing VE's `_queueLock`.**
   - `SegmentHost.enqueue` calls `strategy.submit` → `_enqueue` inside `host._admission`.
   - `cancel()` holds `host.admission()` around `_drop_queued_speech`.
   - The reviewer checks that no other path splits a `Begin`…`Retire` bracket. Inner setters put `TtsSetParamList` without admission; that is harmless because cancel keeps settings, and `_queueLock` never covered them either.
5. **Inner fidelity and rate boost.**
   - Diff the Cerence inner driver against `ref/CerenceTTS(min)`. Every difference must be a kept item or `self.daemon = True`.
   - Rate boost keeps WorldVoice's immediate Sonic speed change, while the native `VE_PARAM_SPEECHRATE` reset is queued. The reviewer checks that toggling rate boost while speech is queued cannot leave the wrong native rate once the queue drains.

---

### Task 1: VE leftovers from 3d-1

Spec §3. This is a refactor with no behavior change, so the existing VE tests are its gate.

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/VE/__init__.py:292-293` (docstring), `:348-349` (`_queueLock`), `:485-495` (`_enqueue`), `:679` (`cancel`)

**Interfaces:**
- Consumes: `SegmentHost.enqueue` holding `_admission` around `strategy.submit`, and `SegmentHost.admission()`. Both are unchanged.
- Produces: nothing new. Task 2's Cerence wrapper is written without `_queueLock` from the start.

- [ ] **Step 1: Confirm the VE tests are green before the refactor**

Run: `python3 -m pytest tests/test_vocalizer_segment_drain.py tests/test_worldvoice_cancel_wrappers.py -q -k VE 2>&1 | tail -1`
Expected: `142 passed, 14 skipped, 77 deselected`.

- [ ] **Step 2: Apply the refactor**

Save as `$PATCHES/t1-impl.patch`, then run `git apply $PATCHES/t1-impl.patch`:

```diff
diff --git a/addon/synthDrivers/WorldVoice/driver/VE/__init__.py b/addon/synthDrivers/WorldVoice/driver/VE/__init__.py
index 88487b0..715173d 100644
--- a/addon/synthDrivers/WorldVoice/driver/VE/__init__.py
+++ b/addon/synthDrivers/WorldVoice/driver/VE/__init__.py
@@ -290,7 +290,7 @@ class _ContextualVECallback(base.VECallback):
 
 
 class _VEStrategy:
-	"""VE's native queue: the outer FIFO worker in place of the add-on's BgThread."""
+	"""VE's native queue: the inner BgThread, each record's tasks queued around speak()."""
 
 	barriers = frozenset({"spoken", "idle"})
 
@@ -345,8 +345,6 @@ class SynthDriver(BaseSynthDriver):
 		self._guard_installed = False
 		self._speechStateLock = threading.Condition()
 		self._segmentHost = SegmentHost("VE", _VEStrategy(self), fail_accepted_on_control_error=True)
-		# Serializes a record's Begin/NativeTask/Retire tasks against cancel().
-		self._queueLock = threading.RLock()
 		self._submitting = None
 		self._currentRecord = None
 		self._doneOwner = None
@@ -485,14 +483,14 @@ class SynthDriver(BaseSynthDriver):
 	def _enqueue(self, record, commands):
 		# The inner speak() converts on this thread and queues its native
 		# chunks and DoneSpeaking; bracket them with this record's tasks.
-		with self._queueLock:
-			self._bgQueue.put(_Begin(self, record))
-			self._submitting = record
-			try:
-				BaseSynthDriver.speak(self, commands)
-			finally:
-				self._submitting = None
-				self._bgQueue.put(_Retire(self, record))
+		# Host admission (held by enqueue and by cancel) keeps the bracket whole.
+		self._bgQueue.put(_Begin(self, record))
+		self._submitting = record
+		try:
+			BaseSynthDriver.speak(self, commands)
+		finally:
+			self._submitting = None
+			self._bgQueue.put(_Retire(self, record))
 
 	def _record_valid(self, record):
 		# Sealing (retire) does not invalidate the work; callback admission
@@ -676,7 +674,7 @@ class SynthDriver(BaseSynthDriver):
 				if self._playerClosing:
 					return
 			host.cancel()
-			with self._queueLock, self._speechStateLock:
+			with self._speechStateLock:
 				self._isSilence.set()
 				# WavePlayer.stop clears its own pause state. Keep the final idle
 				# predicate in sync so fresh speech does not await a stale pause.
```

- [ ] **Step 3: Run the tests**

Run: `python3 -m pytest tests -q 2>&1 | tail -1`
Expected: `1362 passed, 101 skipped, 1 xfailed`

Run: `grep -n "_queueLock\|outer FIFO" addon/synthDrivers/WorldVoice/driver/VE/__init__.py; ruff format --check addon/synthDrivers/WorldVoice/driver/VE/__init__.py`
Expected: no grep output, then `1 file already formatted`.

- [ ] **Step 4: Commit**

```bash
git add addon/synthDrivers/WorldVoice/driver/VE/__init__.py
git commit -m "refactor(ve): drop the redundant queue lock and name the inner BgThread as the worker

Host admission already serializes _enqueue against cancel(), so the
separate _queueLock added nothing.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Cerence on the original asynchronous inner driver and SegmentHost

Spec §1, §2 and the test section.

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/Cerence/driver/__init__.py` (inner driver, restored to the original async structure plus the kept items)
- Modify: `addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py` (outer wrapper, a separate copy of the VE design adapted to Cerence)
- Modify: `tests/test_vocalizer_segment_drain.py`:
  - 10 VE-only tests lose their skip and become engine-neutral;
  - 2 Cerence tests check for `SegmentHost`.
- Modify: `tests/test_engine_segment_contract.py` (contract 4 with no xfail; `_c3` removed)
- Modify: `tests/test_lifecycle_private_access.py` (`MIGRATED` gains `"Cerence"`)

**Interfaces:**
- Consumes:
  - the `SegmentHost` API used by VE in 3d-1, unchanged: `speak_segment`, `enqueue(barriers=, native=)`, `begin`, `consumer`, `bound_callback`, `wait_consumers`, `reach`, `record_error`, `latch_control_error`, `retire`, `abandon`, `forget`, `cancel`, `terminate`, `admission`, `wait_idle`, `fail_accepted_on_control_error`;
  - the `drain`/`admission_error` hooks;
  - Task 1's admission-only bracket (no `_queueLock`).
- Produces (names the tests read):
  - Inner `BgThread` and `self._bgQueue`/`self._bgThread`.
  - `SynthDriver._segmentHost`, a `SegmentHost("Cerence", _CerenceStrategy(self), fail_accepted_on_control_error=True)`.
  - `_CerenceStrategy.barriers = {"spoken", "idle"}`. Ordinary records use `_ORDINARY_BARRIERS = frozenset()`.
  - Queue tasks `_Begin`, `_NativeTask` and `_Retire`, each carrying `.record`.
  - `_CerenceRequest(commands, token, began, skipped)` in `record.native`.
  - `_NativeCall(record, instance, admitting)`, current as `_nativeCall`.
  - Kept names: `_veCallbackHandler` (a `_ContextualCerenceCallback`), `_real_player`, `_isSilence`, `_onIndexReached`, `_veCallback`, `_terminationDone`, `_currentRecord`.

- [ ] **Step 1: Make the tests engine-neutral and expect the host**

Save as `$PATCHES/t2-tests.patch`, then run `git apply $PATCHES/t2-tests.patch`:

```diff
diff --git a/tests/test_engine_segment_contract.py b/tests/test_engine_segment_contract.py
index 91efeb2..cb10d83 100644
--- a/tests/test_engine_segment_contract.py
+++ b/tests/test_engine_segment_contract.py
@@ -45,10 +45,6 @@ def _engines(**xfails):
 	return params
 
 
-def _c3(engine):
-	return f"C3: {engine} speak_segment blocks until delivery; fixed by SegmentHost in phase 3"
-
-
 class Events(list):
 	def __init__(self, adapter):
 		super().__init__()
@@ -148,7 +144,7 @@ def test_cancelled_token_never_reaches_native_or_sink(engine):
 	assert list(events) == []
 
 
-@pytest.mark.parametrize("engine", _engines(Cerence=_c3("Cerence")), indirect=True)
+@pytest.mark.parametrize("engine", _engines(), indirect=True)
 def test_speak_segment_returns_before_delivery(engine):
 	context = engine.PlaybackContext(object(), 23)
 	events = Events(engine)
diff --git a/tests/test_lifecycle_private_access.py b/tests/test_lifecycle_private_access.py
index 6922f4b..78c4a4d 100644
--- a/tests/test_lifecycle_private_access.py
+++ b/tests/test_lifecycle_private_access.py
@@ -46,7 +46,7 @@ def test_wrappers_do_not_touch_lifecycle_private_state():
 
 
 # Wrappers moved onto SegmentHost; the host owns their lifecycle entirely.
-MIGRATED = ("Espeak", "SAPI5", "RHVoice", "OneCore", "VE")
+MIGRATED = ("Espeak", "SAPI5", "RHVoice", "OneCore", "VE", "Cerence")
 
 
 def test_migrated_wrappers_only_use_the_segment_host():
diff --git a/tests/test_vocalizer_segment_drain.py b/tests/test_vocalizer_segment_drain.py
index 49713f8..c40176a 100644
--- a/tests/test_vocalizer_segment_drain.py
+++ b/tests/test_vocalizer_segment_drain.py
@@ -210,7 +210,7 @@ def test_ve_shared_cancel_retires_guarded_feed_before_successor(env, monkeypatch
 @pytest.mark.parametrize("env", ["Cerence"], indirect=True)
 def test_cerence_shared_lifecycle_waits_for_chunk_callback_and_idle(env, monkeypatch):
     prove_fake_quiescence(env, monkeypatch)
-    assert isinstance(env.core._segmentLifecycle, env.module.SegmentLifecycle)
+    assert isinstance(env.core._segmentHost, env.module.SegmentHost)
     feed_entered, feed_release, idle_entered, idle_release = Event(), Event(), Event(), Event()
     callbacks = []
     env.core._real_player.feed = lambda data: (feed_entered.set(), feed_release.wait(2))
@@ -240,7 +240,7 @@ def test_cerence_shared_lifecycle_waits_for_chunk_callback_and_idle(env, monkeyp
 @pytest.mark.parametrize("env", ["Cerence"], indirect=True)
 def test_cerence_shared_cancel_retires_guarded_feed_before_successor(env, monkeypatch):
     prove_fake_quiescence(env, monkeypatch)
-    assert isinstance(env.core._segmentLifecycle, env.module.SegmentLifecycle)
+    assert isinstance(env.core._segmentHost, env.module.SegmentHost)
     feed_entered, feed_release, stop_entered, stop_release = Event(), Event(), Event(), Event()
     calls, callbacks = [], []
     env.core._real_player.feed = lambda data: (feed_entered.set(), feed_release.wait(2))
@@ -281,9 +281,7 @@ def test_cerence_shared_cancel_retires_guarded_feed_before_successor(env, monkey
     assert env.indexes == [42]
 
 
-def test_ve_shared_terminal_listener_can_speak_successor(env, monkeypatch):
-    if env.engine != "VE":
-        pytest.skip("VE lifecycle adapter")
+def test_terminal_listener_can_speak_successor(env, monkeypatch):
     monkeypatch.setattr(env.native, "processText2Speech", lambda *args: None)
     token = Token()
     source = object()
@@ -301,10 +299,8 @@ def test_ve_shared_terminal_listener_can_speak_successor(env, monkeypatch):
     assert [event.segment_id for event in events] == [17, 18]
 
 
-def test_ve_speak_returns_before_native_synthesis(env, monkeypatch):
+def test_speak_returns_before_native_synthesis(env, monkeypatch):
     # Like the original add-on: speak() queues to the BgThread and returns.
-    if env.engine != "VE":
-        pytest.skip("VE lifecycle adapter")
     entered, release = Event(), Event()
     def native(instance, text):
         entered.set()
@@ -322,10 +318,8 @@ def test_ve_speak_returns_before_native_synthesis(env, monkeypatch):
     assert len(env.dones) == 1
 
 
-def test_ve_settings_apply_in_call_order_with_speech(env, monkeypatch):
+def test_settings_apply_in_call_order_with_speech(env, monkeypatch):
     # Like the original add-on: settings queue behind speech already requested.
-    if env.engine != "VE":
-        pytest.skip("VE lifecycle adapter")
     order = []
     entered, release = Event(), Event()
     def native(instance, text):
@@ -345,11 +339,9 @@ def test_ve_settings_apply_in_call_order_with_speech(env, monkeypatch):
     assert order == [("spoken", "first"), ("set", ((env.types.VE_PARAM_VOLUME, 40),)), ("spoken", "second")]
 
 
-def test_ve_cancel_drops_a_segment_queued_behind_the_worker(env, monkeypatch):
+def test_cancel_drops_a_segment_queued_behind_the_worker(env, monkeypatch):
     # After a handoff the next segment can queue while the BgThread finishes
     # the previous retirement; cancel must retire it without a DONE.
-    if env.engine != "VE":
-        pytest.skip("VE lifecycle adapter")
     prove_fake_quiescence(env, monkeypatch)
     monkeypatch.setattr(env.native, "processText2Speech", lambda *args: None)
     host = env.core._segmentHost
@@ -378,11 +370,9 @@ def test_ve_cancel_drops_a_segment_queued_behind_the_worker(env, monkeypatch):
     assert env.dones == []
 
 
-def test_ve_failed_ordinary_speech_still_publishes_done(env, monkeypatch):
+def test_failed_ordinary_speech_still_publishes_done(env, monkeypatch):
     # speak() no longer raises, so a failed request must still release a
     # LEGACY_DONE waiter, as the original add-on's DoneSpeaking does.
-    if env.engine != "VE":
-        pytest.skip("VE lifecycle adapter")
     def fail(instance, text):
         raise OSError("native failed")
     monkeypatch.setattr(env.native, "processText2Speech", fail)
@@ -391,11 +381,9 @@ def test_ve_failed_ordinary_speech_still_publishes_done(env, monkeypatch):
     assert env.core._real_player.idles == 0
 
 
-def test_ve_engine_settings_variant_waits_for_running_speech(env, monkeypatch):
+def test_engine_settings_variant_waits_for_running_speech(env, monkeypatch):
     # The variant write joins the BgThread queue like every inner setting, so
     # it never runs on the same native instance as an in-flight synthesis.
-    if env.engine != "VE":
-        pytest.skip("VE lifecycle adapter")
     order = []
     entered, release = Event(), Event()
     def native(instance, text):
@@ -418,9 +406,7 @@ def test_ve_engine_settings_variant_waits_for_running_speech(env, monkeypatch):
     assert order == [("spoken", "first"), ("set", ((env.types.VE_PARAM_VOICE_OPERATING_POINT, "plain"),))]
 
 
-def test_ve_shared_player_failure_rejects_successor_with_context(env, monkeypatch):
-    if env.engine != "VE":
-        pytest.skip("VE lifecycle adapter")
+def test_player_failure_rejects_successor_with_context(env, monkeypatch):
     prove_fake_quiescence(env, monkeypatch)
     monkeypatch.setattr(env.native, "processText2Speech", lambda *args: None)
     error = OSError("idle failed")
@@ -438,9 +424,7 @@ def test_ve_shared_player_failure_rejects_successor_with_context(env, monkeypatc
     assert env.events[1].segment_id == 18
 
 
-def test_ve_shared_terminate_waits_for_coordinator_stop(env, monkeypatch):
-    if env.engine != "VE":
-        pytest.skip("VE lifecycle adapter")
+def test_terminate_waits_for_coordinator_stop(env, monkeypatch):
     idle_entered, idle_release, hook_entered, hook_release = Event(), Event(), Event(), Event()
     closed = Event()
     monkeypatch.setattr(env.native, "processText2Speech", lambda *args: None)
@@ -467,11 +451,9 @@ def test_ve_shared_terminate_waits_for_coordinator_stop(env, monkeypatch):
 
 
 @pytest.mark.parametrize("cancel_kind", ["token", "direct"])
-def test_ve_shared_speak_segment_returns_while_a_previous_sink_runs(env, monkeypatch, cancel_kind):
+def test_speak_segment_returns_while_a_previous_sink_runs(env, monkeypatch, cancel_kind):
     # C3: speak_segment no longer waits for delivery, so a blocked sink of the
     # previous segment cannot hold the caller; cancellation keeps it silent.
-    if env.engine != "VE":
-        pytest.skip("VE lifecycle adapter")
     monkeypatch.setattr(env.native, "processText2Speech", lambda *args: None)
     sink_entered, sink_release = Event(), Event()
     first_context = env.rt.models.PlaybackContext(object(), 17)
@@ -498,9 +480,7 @@ def test_ve_shared_speak_segment_returns_while_a_previous_sink_runs(env, monkeyp
 
 
 @pytest.mark.parametrize("hook", ["stop", "idle"])
-def test_ve_shared_player_hook_can_reenter_terminate(env, monkeypatch, hook):
-    if env.engine != "VE":
-        pytest.skip("VE lifecycle adapter")
+def test_player_hook_can_reenter_terminate(env, monkeypatch, hook):
     monkeypatch.setattr(env.native, "close", lambda instance: None)
     monkeypatch.setattr(env.native, "terminate", lambda: None)
     token = Token()
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests -q 2>&1 | grep -E "^FAILED|^[0-9]+ (passed|failed)" | sed 's/ - .*//'`
Expected: `12 failed, 1363 passed, 89 skipped`. The failures:
- `tests/test_engine_segment_contract.py::test_speak_segment_returns_before_delivery[Cerence]`: C3, now that its xfail is gone.
- `tests/test_lifecycle_private_access.py::test_migrated_wrappers_only_use_the_segment_host`
- In `tests/test_vocalizer_segment_drain.py`:
  - `test_cerence_shared_lifecycle_waits_for_chunk_callback_and_idle[Cerence]`
  - `test_cerence_shared_cancel_retires_guarded_feed_before_successor[Cerence]`
  - `test_speak_returns_before_native_synthesis[Cerence]`
  - `test_settings_apply_in_call_order_with_speech[Cerence]`
  - `test_cancel_drops_a_segment_queued_behind_the_worker[Cerence]`
  - `test_failed_ordinary_speech_still_publishes_done[Cerence]`
  - `test_engine_settings_variant_waits_for_running_speech[Cerence]`
  - `test_terminate_waits_for_coordinator_stop[Cerence]`
  - `test_speak_segment_returns_while_a_previous_sink_runs[Cerence-token]` and `[Cerence-direct]`

The other three newly neutral tests pass for Cerence already: `test_terminal_listener_can_speak_successor`, `test_player_failure_rejects_successor_with_context` and `test_player_hook_can_reenter_terminate`. They guard the migration against regressing those paths; M2h proves `test_player_hook_can_reenter_terminate` bites once the wrapper uses the closer.

- [ ] **Step 3: Restore the inner driver and rewrite the wrapper**

Save as `$PATCHES/t2-impl.patch`, then run `git apply $PATCHES/t2-impl.patch`:

```diff
diff --git a/addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py b/addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py
index 7ee005b..b5f43b3 100644
--- a/addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py
+++ b/addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py
@@ -1,5 +1,6 @@
 import languageHandler
 import locale
+import queue
 import threading
 import weakref
 from contextlib import contextmanager
@@ -35,18 +36,20 @@ from synthDrivers.WorldVoice.driver import Voice, getVoiceKey
 from synthDrivers.WorldVoice.text.arabic import break_repeated_runs
 from synthDrivers.WorldVoice.text.chunker import split_speech_text_pieces
 from ...runtime.models import PlaybackContext, SegmentEventSink, SpeechCommands
-from ...runtime.playbackWork import CallbackGate, DrainSupport, unverified_drain_support
-from ...runtime.segmentLifecycle import SegmentLifecycle
+from ...runtime.playbackWork import DrainSupport, unverified_drain_support
+from ...runtime.segmentHost import SegmentHost
 from ...runtime.session import CancellationView
 
 
 _PROFILE = "cerence-ttsapi-0x0520-unverified"
-_QUIESCENCE_REASON = (
-	"The loaded Cerence ttsapi SDK has no verified callback-exclusion contract after "
-	"ve_ttsProcessText2Speech returns; SDK version/build provenance and the "
-	"NVDA playback profile are unverified"
-)
 _RETAINED_CALLBACKS = []
+# Ordinary speech proves no barrier: its idle and DONE stay with the inner
+# driver's DoneSpeaking, its failures are recorded errors, and its token is
+# the worker's to honour (a token-cancelled request is not a failure).
+_ORDINARY_BARRIERS = frozenset()
+# Queued in place of ordinary speech that cancel() drops: like the original
+# add-on, cancel discards queued speech but keeps its DONE notification.
+_DONE = object()
 
 
 class _SilenceGate(threading.Event):
@@ -103,61 +106,58 @@ class _GuardedPlayer:
 		return getattr(self._real, name)
 
 
-class _SpeechWork:
-	"""One synchronous batch; errors are delivered after callback retirement."""
+@dataclass(eq=False)
+class _CerenceRequest:
+	"""Cerence data carried on a NativeRecord: its speech sequence and ordinary token."""
 
-	def __init__(self, token, playback=None, completion=None):
-		self.token = token
-		self.playback = playback
-		self.completion = completion
-		self._lock = threading.Lock()
-		self._active = True
-		self.error = None
-		self.drained = False
-		self.operation = None
-		self.cancelled = False
+	commands: object
+	token: object = None
+	# Set on the inner BgThread when its Begin task ran (skipped: never spoken).
+	began: bool = False
+	skipped: bool = False
 
-	def is_valid(self):
-		with self._lock:
-			return self._active and self.error is None and not (self.token and self.token.is_cancelled())
 
-	def cancel(self):
-		with self._lock:
-			self._active = False
-			self.cancelled = True
-		if self.playback is not None:
-			self.playback.cancel()
-		if self.completion is not None:
-			self.completion.set()
-
-	def fault(self, error):
-		with self._lock:
-			if self.error is None:
-				self.error = error
-
-
-@dataclass
-class _NativeWork:
-	work: _SpeechWork
+@dataclass(eq=False)
+class _NativeCall:
+	"""One synchronous ve_ttsProcessText2Speech call and its callback admission."""
+
+	record: object
 	instance: object
-	call_token: object = None
 	admitting: bool = True
-	callbacks: int = 0
-	producer: object = None
 
 
-class _SegmentCallbackLease:
-	def __init__(self, gate_lease, producer, lifecycle, work):
-		self._gate_lease = gate_lease
-		self.producer = producer
-		self._lifecycle = lifecycle
-		self.work = work
+class _RecordTask:
+	"""A task for the inner BgThread queue, bound to one NativeRecord."""
 
-	def close(self):
-		try:
-			self._gate_lease.close()
-		finally:
-			self._lifecycle.retire_producer(self.producer)
+	def __init__(self, driver, record):
+		self._driver = weakref.ref(driver)
+		self.record = record
+
+
+class _Begin(_RecordTask):
+	def __call__(self):
+		driver = self._driver()
+		if driver is not None:
+			driver._begin_record(self.record)
+
+
+class _NativeTask(_RecordTask):
+	def __init__(self, driver, record, instance, text):
+		super().__init__(driver, record)
+		self._instance = instance
+		self._text = text
+
+	def __call__(self):
+		driver = self._driver()
+		if driver is not None:
+			driver._run_native(self.record, self._instance, self._text)
+
+
+class _Retire(_RecordTask):
+	def __call__(self):
+		driver = self._driver()
+		if driver is not None:
+			driver._retire_record(self.record)
 
 
 class ProcessText2Speech(BaseProcessText2Speech):
@@ -186,20 +186,6 @@ class ProcessText2Speech(BaseProcessText2Speech):
 		return result
 
 
-class _LegacyLease:
-	"""Preserve legacy compatibility without asserting SDK quiescence."""
-
-	def __init__(self, driver, native):
-		self._driver = driver
-		self.native = native
-		self.work = native.work
-
-	def close(self):
-		with self._driver._speechStateLock:
-			self.native.callbacks -= 1
-			self._driver._speechStateLock.notify_all()
-
-
 class _ContextualCerenceCallback(base.VECallback):
 	"""Constructor-installed native callback; never borrows a later call's work."""
 
@@ -221,22 +207,24 @@ class _ContextualCerenceCallback(base.VECallback):
 			return NUAN_E_TTS_USERSTOP
 		if not driver._guard_installed:
 			return super().__call__(instance, userData, message)
-		lease, native = driver._admit_callback(instance)
-		if lease is None:
-			# Legacy ENDPROCESS historically acknowledges cancellation. It
-			# cannot flush or clear anything without an admitted call lease.
-			if (
-				native is not None
-				and native.work.playback is None
-				and (message.contents.eMessage == VE_MSG_ENDPROCESS)
-			):
-				return NUAN_OK
-			return NUAN_E_TTS_USERSTOP
-		work = lease.work
-		driver._callbackLocal.depth = getattr(driver._callbackLocal, "depth", 0) + 1
+		with driver._callback_admission(instance) as (record, call):
+			if record is None:
+				# Legacy ENDPROCESS historically acknowledges cancellation. It
+				# cannot flush or clear anything without an admitted call.
+				if (
+					call is not None
+					and call.record.operation is None
+					and message.contents.eMessage == VE_MSG_ENDPROCESS
+				):
+					return NUAN_OK
+				return NUAN_E_TTS_USERSTOP
+			return self._process(driver, record, call, message)
+
+	def _process(self, driver, record, call, message):
+		host = driver._segmentHost
 		try:
 			with self._processingLock:
-				if not work.is_valid():
+				if not driver._record_valid(record):
 					return NUAN_E_TTS_USERSTOP
 				message_type = message.contents.eMessage
 				if message_type == VE_MSG_OUTBUFREQ:
@@ -256,15 +244,15 @@ class _ContextualCerenceCallback(base.VECallback):
 							if output:
 								self._feedBuf.write(bytes(output))
 							if self._feedBuf.tell() >= base.pcmBufLen:
-								driver._feed_callback(work, self._feedBuf.getvalue(), lease)
+								driver._feed_callback(record, self._feedBuf.getvalue())
 								self._feedBuf = BytesIO()
 						else:
-							driver._feed_callback(work, string_at(data.pOutPcmBuf, data.cntPcmBufLen), lease)
-					if not work.is_valid():
+							driver._feed_callback(record, string_at(data.pOutPcmBuf, data.cntPcmBufLen))
+					if not driver._record_valid(record):
 						self._feedBuf = BytesIO()
 						return NUAN_E_TTS_USERSTOP
 					for i in range(int(data.cntMrkListLen)):
-						if not work.is_valid():
+						if not driver._record_valid(record):
 							return NUAN_E_TTS_USERSTOP
 						if data.pMrkList[i].eMrkType == VE_MRK_BOOKMARK:
 							self._onIndexReached(int(data.pMrkList[i].szValue))
@@ -274,28 +262,25 @@ class _ContextualCerenceCallback(base.VECallback):
 					if self._sonicEnabled and self.sonicStream is not None:
 						self.sonicStream.flush()
 						output = self.sonicStream.readShort()
-						if output and work.is_valid():
+						if output and driver._record_valid(record):
 							self._feedBuf.write(bytes(output))
-					if self._feedBuf.tell() and work.is_valid():
-						driver._feed_callback(work, self._feedBuf.getvalue(), lease)
+					if self._feedBuf.tell() and driver._record_valid(record):
+						driver._feed_callback(record, self._feedBuf.getvalue())
 					self._feedBuf = BytesIO()
-				return NUAN_OK if work.is_valid() else NUAN_E_TTS_USERSTOP
+				return NUAN_OK if driver._record_valid(record) else NUAN_E_TTS_USERSTOP
 		except Exception as error:
-			work.fault(error)
-			driver._close_admission(native)
+			host.record_error(record, error)
+			driver._close_admission(call)
 			log.error("WorldVoice Cerence callback failed", exc_info=True)
 			return NUAN_E_TTS_USERSTOP
 		finally:
-			# Retain ownership through the final stop; new work cannot reset
-			# the gate or use the player until this lease has exited.
+			# The callback keeps its admission through the final stop; the
+			# worker cannot start another call until this consumer leaves.
 			try:
-				if not work.is_valid():
+				if not driver._record_valid(record):
 					driver._real_player.stop()
 			except Exception as error:
-				work.fault(error)
-			finally:
-				lease.close()
-				driver._callbackLocal.depth -= 1
+				host.record_error(record, error)
 
 	def detach(self):
 		self._driver = None
@@ -304,17 +289,70 @@ class _ContextualCerenceCallback(base.VECallback):
 		self._feedBuf = BytesIO()
 
 
+class _CerenceStrategy:
+	"""Cerence's native queue: the inner BgThread, each record's tasks queued around speak()."""
+
+	barriers = frozenset({"spoken", "idle"})
+
+	def __init__(self, driver):
+		self._driver = weakref.ref(driver)
+
+	def admission_error(self, host):
+		driver = self._driver()
+		if not driver._guard_installed:
+			return RuntimeError("Cerence cancellation guard installation is unavailable")
+		with driver._speechStateLock:
+			if driver._terminated:
+				return RuntimeError("Cerence driver has terminated")
+			if driver._legacyUsed:
+				return RuntimeError(
+					"Legacy Cerence callback lifetimes are unproven; cannot enter correlated mode"
+				)
+		return None
+
+	def submit(self, host, record, commands):
+		driver = self._driver()
+		if record.native is None:
+			record.native = _CerenceRequest(commands)
+		driver._enqueue(record, record.native.commands)
+
+	def stop_native(self, host, record):
+		self._driver()._stop_player()
+
+	def stop_player(self, host):
+		self._driver()._stop_player()
+
+	def drain(self, host, record):
+		driver = self._driver()
+		with driver._player_operation():
+			try:
+				driver._real_player.idle()
+				with driver._speechStateLock:
+					driver._speechStateLock.wait_for(
+						lambda: (
+							(driver._pauses == 0 and not driver._paused) or not driver._record_valid(record)
+						),
+					)
+			except Exception as error:
+				# The player state is uncertain after a failed idle: reject successors.
+				host.record_error(record, error)
+				host.latch_control_error(error)
+				return
+			if driver._record_valid(record) and not driver._isSilence.cancelled():
+				host.reach(record, "idle")
+
+
 class SynthDriver(BaseSynthDriver):
 	def __init__(self):
 		self._guard_installed = False
 		self._speechStateLock = threading.Condition()
-		self._speechRunLock = threading.Lock()
-		self._segmentGate = CallbackGate()
-		self._segmentLifecycle = SegmentLifecycle(self)
-		self._currentWork = None
-		self._segmentWorks = set()
-		self._nativeWork = None
-		self._segmentBlockedError = None
+		self._segmentHost = SegmentHost(
+			"Cerence", _CerenceStrategy(self), fail_accepted_on_control_error=True
+		)
+		self._submitting = None
+		self._currentRecord = None
+		self._doneOwner = None
+		self._nativeCall = None
 		self._legacyUsed = False
 		self._stops = 0
 		self._paused = False
@@ -322,7 +360,6 @@ class SynthDriver(BaseSynthDriver):
 		self._pauses = 0
 		self._terminated = False
 		self._callbackLocal = threading.local()
-		self._speechLocal = threading.local()
 		self._playerLocal = threading.local()
 		self._terminationLocal = threading.local()
 		self._playerClosing = False
@@ -341,6 +378,8 @@ class SynthDriver(BaseSynthDriver):
 			raise RuntimeError("no resources available")
 		ttsapi.initialize(resources)
 		self._instanceCache = {}
+		self._bgQueue = queue.Queue()
+		self._bgThread = base.BgThread(self._bgQueue)
 		try:
 			device = base.config.conf["audio"]["outputDevice"]
 		except KeyError:
@@ -415,7 +454,7 @@ class SynthDriver(BaseSynthDriver):
 			return DrainSupport(False, _PROFILE, "Cerence cancellation guard installation is unavailable")
 		return unverified_drain_support(_PROFILE, "SDK callback quiescence and physical playback are")
 
-	def _confirm_native_quiescence(self, native):
+	def _confirm_native_quiescence(self, call):
 		# Explicit activation override; retain the callback guard and idle barrier.
 		return None
 
@@ -427,191 +466,83 @@ class SynthDriver(BaseSynthDriver):
 		context: PlaybackContext,
 		on_event: SegmentEventSink,
 	) -> None:
-		completion = threading.Event()
-
-		def deliver(event):
-			try:
-				on_event(event)
-			finally:
-				completion.set()
-
-		with self._speechStateLock:
-			admission_error = self._segmentBlockedError
-			if admission_error is None:
-				try:
-					operation = self._segmentLifecycle.accept(context, token, deliver)
-				except RuntimeError as error:
-					admission_error = error
-				else:
-					work = _SpeechWork(token, operation.work, completion)
-					work.operation = operation
-					operation._ve_work = work
-					operation._ve_natives = []
-					self._segmentWorks.add(work)
-		if admission_error is not None:
-			self._segmentLifecycle.reject_new(context, token, deliver, admission_error)
-			self._wait_segment_delivery(completion, token)
-			return
-		try:
-			try:
-				self._segmentLifecycle.run(operation, tuple(commands))
-			except RuntimeError as error:
-				# A prior fatal resource fault rejects before this operation owns
-				# native/player state. Preserve this request's original context.
-				self._segmentLifecycle.reject_new(context, token, deliver, error.__cause__ or error)
-				self._wait_segment_delivery(completion, token)
-				return
-			if operation.is_retired() and not work.cancelled and not token.is_cancelled():
-				self._wait_segment_delivery(completion, token)
-		finally:
-			with self._speechStateLock:
-				self._segmentWorks.discard(work)
-			if self._terminationRequested:
-				self._finish_termination()
-
-	def _wait_segment_delivery(self, completion, token):
-		# A listener may synchronously ask for another segment. The coordinator
-		# owns a single delivery thread, so it cannot wait for its own callback.
-		if token.is_cancelled() or self._segmentLifecycle.on_delivery_thread():
-			return
-		# Token cancellation wakes this wait; direct cancellation sets completion itself.
-		remove_wake = token.add_callback(completion.set)
-		try:
-			completion.wait()
-		finally:
-			remove_wake()
-
-	# The inner driver still parses settings and splits text. Its synchronous
-	# native calls and callback gate form the SDK boundary for this operation.
-	def submit_native(self, operation, commands):
-		self._run_speech(commands, operation._ve_work)
-		if operation._ve_work.error is not None:
-			raise operation._ve_work.error
-
-	def request_stop(self, operation):
-		with self._speechStateLock:
-			self._stops += 1
-			self._playerLocal.depth = getattr(self._playerLocal, "depth", 0) + 1
-			self._speechStateLock.notify_all()
-		try:
-			self._real_player.stop()
-		finally:
-			with self._speechStateLock:
-				self._stops -= 1
-				self._speechStateLock.notify_all()
-			# Contextual teardown belongs to speak_segment after the coordinator
-			# retires this operation. Finishing here would wait on our own stop.
-			self._playerLocal.depth -= 1
-
-	def wait_native_boundary(self, operation):
-		if operation._ve_work.error is not None:
-			raise operation._ve_work.error
-
-	def wait_native_retired(self, operation):
-		for native in operation._ve_natives:
-			if native.call_token is not None:
-				self._segmentGate.wait_retired(native.call_token)
-
-	def wait_playback_drained(self, operation):
-		work = operation._ve_work
-		if work.error is not None:
-			raise work.error
-		if not work.is_valid():
-			return
-		self._playerLocal.depth = getattr(self._playerLocal, "depth", 0) + 1
-		try:
-			self._real_player.idle()
-			with self._speechStateLock:
-				self._speechStateLock.wait_for(
-					lambda: (self._pauses == 0 and not self._paused) or not work.is_valid(),
-				)
-			if work.error is not None:
-				raise work.error
-			work.drained = work.is_valid() and not self._isSilence.cancelled()
-		finally:
-			# The owning run clears the resource-busy flag before teardown.
-			self._playerLocal.depth -= 1
+		self._segmentHost.speak_segment(commands, token, context=context, on_event=on_event)
 
 	def speak(self, speechSequence, cancellationToken=None):
 		if not self._guard_installed:
 			return super().speak(speechSequence)
-		work = _SpeechWork(cancellationToken)
-		result = self._run_speech(speechSequence, work)
-		if work.error is not None:
-			raise work.error
-		return result
+		with self._speechStateLock:
+			if self._terminated:
+				raise RuntimeError("Cerence driver has terminated")
+			# Legacy callback lifetimes are unproven: correlated mode stays off
+			# from the moment ordinary speech is requested.
+			self._legacyUsed = True
+		# Like the original add-on's BgThread queue: return once queued.
+		self._segmentHost.enqueue(
+			speechSequence,
+			barriers=_ORDINARY_BARRIERS,
+			native=_CerenceRequest(speechSequence, cancellationToken),
+		)
 
-	def _run_speech(self, commands, work):
-		self._speechLocal.depth = getattr(self._speechLocal, "depth", 0) + 1
+	def _enqueue(self, record, commands):
+		# The inner speak() converts on this thread and queues its native
+		# chunks and DoneSpeaking; bracket them with this record's tasks.
+		# Host admission (held by enqueue and by cancel) keeps the bracket whole.
+		self._bgQueue.put(_Begin(self, record))
+		self._submitting = record
 		try:
-			return self._run_speech_locked(commands, work)
+			BaseSynthDriver.speak(self, commands)
 		finally:
-			self._speechLocal.depth -= 1
-			# A notification may request termination while this thread owns
-			# the native batch/lease. Close resources only after releasing it.
-			if self._terminationRequested and work.operation is None:
-				self._finish_termination()
-
-	@contextmanager
-	def _speech_run_ownership(self, work):
-		# A contextual operation releases the run lock after native submission
-		# but still owns the shared native/player resource through its final
-		# playback barrier and stop retirement. Ordinary speech waits for that
-		# coordinator retirement outside the run lock, because the contextual
-		# owner needs the run lock to submit.
-		lifecycle = self._segmentLifecycle
-		while True:
-			if work.operation is None and not lifecycle.wait_idle(
-				still_wanted=work.is_valid,
-				token=work.token,
-			):
-				yield False
-				return
-			with self._speechRunLock:
-				if work.operation is None and lifecycle.is_resource_busy():
-					# A contextual run acquired the resource before this
-					# request acquired the run lock. Let it submit first.
-					continue
-				yield True
-				return
+			self._submitting = None
+			self._bgQueue.put(_Retire(self, record))
+
+	def _record_valid(self, record):
+		# Sealing (retire) does not invalidate the work; callback admission
+		# already refuses sealed records.
+		token = record.native.token if record.native is not None else None
+		return (
+			not record.cancelled
+			and record.error is None
+			and (record.work is None or record.work.is_valid())
+			and not (token and token.is_cancelled())
+		)
 
-	def _run_speech_locked(self, commands, work):
-		with self._speech_run_ownership(work) as owned:
-			if not owned:
-				return
+	def _begin_record(self, record):
+		host = self._segmentHost
+		with self._speechStateLock:
+			self._speechStateLock.wait_for(lambda: self._stops == 0 and self._pauses == 0)
+			record.native.began = True
+			self._doneOwner = record
+			if not self._record_valid(record) or record.abandoned or host.control_error is not None:
+				record.native.skipped = True
+			else:
+				self._currentRecord = record
+				host.begin(record)
+				token = record.work.token if record.work is not None else record.native.token
+				self._isSilence.begin(token)
+		if record.native.skipped:
+			host.abandon(record)
+			return
+		self._reset_callback_audio()
+
+	def _retire_record(self, record):
+		host = self._segmentHost
+		if not record.native.skipped:
+			self._isSilence._inside_native_call = False
+			if "spoken" in record.barriers and self._record_valid(record):
+				host.reach(record, "spoken")
 			with self._speechStateLock:
 				self._speechStateLock.wait_for(lambda: self._stops == 0 and self._pauses == 0)
-				if not work.is_valid():
-					return
-				if not self._guard_installed:
-					work.fault(RuntimeError("Cerence cancellation guard installation is unavailable"))
-					return
-				if self._terminated:
-					work.fault(RuntimeError("Cerence driver has terminated"))
-					return
-				if self._segmentBlockedError is not None:
-					work.fault(self._segmentBlockedError)
-					return
-				if work.playback is not None and self._legacyUsed:
-					work.fault(
-						RuntimeError(
-							"Legacy Cerence callback lifetimes are unproven; cannot enter correlated mode",
-						),
-					)
-					return
-				self._currentWork = work
-				self._legacyUsed |= work.playback is None
-				self._isSilence.begin(work.token)
-			try:
-				self._reset_callback_audio()
-				return super().speak(commands)
-			except Exception as error:
-				work.fault(error)
-			finally:
-				self._isSilence._inside_native_call = False
-				with self._speechStateLock:
-					self._speechStateLock.wait_for(lambda: self._stops == 0 and self._pauses == 0)
-					self._currentWork = None
+			host.retire(record)
+			if record.operation is None:
+				host.forget(record)
+		with self._speechStateLock:
+			if self._currentRecord is record:
+				self._currentRecord = None
+			if self._doneOwner is record:
+				self._doneOwner = None
+			self._isSilence._token = None
+			self._speechStateLock.notify_all()
 
 	def _reset_callback_audio(self):
 		callback = self._veCallbackHandler
@@ -624,158 +555,149 @@ class SynthDriver(BaseSynthDriver):
 	def _speak(self, voiceInstance, chunks):
 		if not self._guard_installed:
 			return super()._speak(voiceInstance, chunks)
-		work = self._currentWork
-		if work is None:
+		record = self._submitting
+		if record is None:
 			return
 		for piece in split_speech_text_pieces(break_repeated_runs("".join(chunks))):
-			if not work.is_valid() or self._isSilence.cancelled():
-				break
-			producer = (
-				self._segmentLifecycle.admit_producer(work.operation) if work.operation is not None else None
-			)
-			call = self._segmentGate.begin_native(work) if work.playback is not None else None
-			native = _NativeWork(work, voiceInstance, call, producer=producer)
-			if work.operation is not None:
-				work.operation._ve_natives.append(native)
+			self._bgQueue.put(_NativeTask(self, record, voiceInstance, piece))
+
+	def _run_native(self, record, voiceInstance, piece):
+		host = self._segmentHost
+		if record is not self._currentRecord or not self._record_valid(record) or self._isSilence.cancelled():
+			return
+		call = _NativeCall(record, voiceInstance)
+		with self._speechStateLock:
+			self._speechStateLock.wait_for(lambda: self._stops == 0 and self._pauses == 0)
+			self._nativeCall = call
+			self._isSilence._inside_native_call = True
+		invoked = False
+		try:
+			if self._record_valid(record):
+				invoked = True
+				result = ProcessText2Speech(voiceInstance, piece)()
+				if result == NUAN_E_TTS_USERSTOP and self._record_valid(record):
+					raise RuntimeError("Cerence native synthesis returned USERSTOP")
+		except Exception as error:
+			log.error("WorldVoice Cerence native synthesis failed", exc_info=True)
+			host.record_error(record, error)
+		finally:
+			self._close_admission(call)
+			self._isSilence._inside_native_call = False
+			# Every callback admitted to this call returns before the next one.
+			host.wait_consumers(record)
+			blocked = None
+			if invoked:
+				try:
+					self._confirm_native_quiescence(call)
+				except Exception as error:
+					host.record_error(record, error)
+					host.latch_control_error(error)
+					blocked = error
 			with self._speechStateLock:
 				self._speechStateLock.wait_for(lambda: self._stops == 0 and self._pauses == 0)
-				self._nativeWork = native
-				self._isSilence._inside_native_call = True
-			invoked = False
-			try:
-				if work.is_valid():
-					invoked = True
-					result = ProcessText2Speech(voiceInstance, piece)()
-					if result == NUAN_E_TTS_USERSTOP and work.is_valid():
-						raise RuntimeError("Cerence native synthesis returned USERSTOP")
-			except Exception as error:
-				work.fault(error)
-			finally:
-				self._close_admission(native)
-				self._isSilence._inside_native_call = False
-				if call is not None:
-					try:
-						if invoked:
-							self._confirm_native_quiescence(native)
-						self._segmentGate.finish_native(call)
-					except Exception as error:
-						work.fault(error)
-						self._segmentBlockedError = error
-					finally:
-						self._segmentGate.wait_retired(call)
-				else:
-					with self._speechStateLock:
-						self._speechStateLock.wait_for(lambda: native.callbacks == 0)
-				with self._speechStateLock:
-					self._speechStateLock.wait_for(lambda: self._stops == 0 and self._pauses == 0)
-					if self._segmentBlockedError is None:
-						self._nativeWork = None
-				if self._segmentBlockedError is not None:
-					try:
-						self._real_player.stop()
-					except Exception as error:
-						work.fault(error)
-				if producer is not None:
-					self._segmentLifecycle.retire_producer(producer)
-
-	def _close_admission(self, native):
+				if blocked is None:
+					self._nativeCall = None
+			if blocked is not None:
+				try:
+					self._real_player.stop()
+				except Exception as error:
+					host.record_error(record, error)
+
+	def _close_admission(self, call):
 		with self._speechStateLock:
-			native.admitting = False
-		if native.call_token is not None:
-			self._segmentGate.close(native.call_token)
+			call.admitting = False
 
-	def _admit_callback(self, instance):
+	@contextmanager
+	def _callback_admission(self, instance):
+		host = self._segmentHost
 		with self._speechStateLock:
-			native = self._nativeWork
+			call = self._nativeCall
 			if (
-				native is None
-				or not native.admitting
-				or not isinstance(
-					instance,
-					ttsapi.veTypes.VE_HSAFE,
-				)
-				or instance != native.instance
+				call is None
+				or not call.admitting
+				or not isinstance(instance, ttsapi.veTypes.VE_HSAFE)
+				or instance != call.instance
 			):
-				return None, None
-			if not native.work.is_valid():
-				return None, native
-			if native.call_token is None:
-				native.callbacks += 1
-				return _LegacyLease(self, native), native
-			lease = self._segmentGate.enter_callback()
-			if lease is not None and lease.call_token is not native.call_token:
-				lease.close()
-				return None, None
-			if lease is not None:
-				producer = self._segmentLifecycle.admit_producer(native.work.operation, native.producer)
-				if producer is None:
-					lease.close()
-					return None, native
-				lease = _SegmentCallbackLease(lease, producer, self._segmentLifecycle, native.work)
-			return lease, native
-
-	def _feed_callback(self, work, data, callback_lease=None):
-		# The callback lease owns the final stop, including feed failures.
-		producer = None
-		if work.operation is not None and callback_lease is not None:
-			producer = self._segmentLifecycle.admit_producer(work.operation, callback_lease.producer)
-		try:
-			if work.is_valid():
-				self._real_player.feed(data)
-		finally:
-			if producer is not None:
-				self._segmentLifecycle.retire_producer(producer)
+				call = None
+		if call is None:
+			yield None, None
+			return
+		record = call.record
+		with host.consumer(record) as admitted:
+			if admitted is None or not self._record_valid(record):
+				yield None, call
+				return
+			self._callbackLocal.depth = getattr(self._callbackLocal, "depth", 0) + 1
+			try:
+				with host.bound_callback(record):
+					yield record, call
+			finally:
+				self._callbackLocal.depth -= 1
+
+	def _feed_callback(self, record, data):
+		if self._record_valid(record):
+			self._real_player.feed(data)
 
 	def _idle_player(self):
-		work = self._currentWork
-		if work is not None and work.operation is not None:
+		# Called by the inner DoneSpeaking on the worker. Segments drain on the
+		# lifecycle thread; ordinary speech keeps the add-on's final idle.
+		record = self._currentRecord
+		if record is not None and record.operation is not None:
 			return
-		if self._isSilence.cancelled() or (work is not None and not work.is_valid()):
+		if self._isSilence.cancelled() or (record is not None and not self._record_valid(record)):
 			return
-		self._real_player.idle()
-		if work is not None:
+		with self._player_operation():
+			self._real_player.idle()
+			if record is not None:
+				with self._speechStateLock:
+					self._speechStateLock.wait_for(
+						lambda: (self._pauses == 0 and not self._paused) or not self._record_valid(record),
+					)
+
+	@contextmanager
+	def _player_operation(self):
+		self._playerLocal.depth = getattr(self._playerLocal, "depth", 0) + 1
+		try:
+			yield
+		finally:
+			self._playerLocal.depth -= 1
+
+	def _stop_player(self):
+		with self._speechStateLock:
+			self._stops += 1
+			self._speechStateLock.notify_all()
+		try:
+			with self._player_operation():
+				self._real_player.stop()
+		finally:
 			with self._speechStateLock:
-				self._speechStateLock.wait_for(
-					lambda: (self._pauses == 0 and not self._paused) or not work.is_valid(),
-				)
-				work.drained = work.is_valid() and not self._isSilence.cancelled()
+				self._stops -= 1
+				self._speechStateLock.notify_all()
 
 	def cancel(self):
 		if not self._guard_installed:
 			return super().cancel()
-		with self._speechStateLock:
-			if self._playerClosing:
-				# Another thread sealed termination first, possibly an ordinary
-				# request released by the coordinator's terminate. The player is
-				# closing, but a contextual caller may still await delivery.
-				for pending in self._segmentWorks:
-					pending.cancel()
-				return
-			self._isSilence.set()
-			# WavePlayer.stop clears its own pause state. Keep the final idle
-			# predicate in sync so fresh speech does not await a stale pause.
-			self._paused = False
-			self._pauseRevision += 1
-			work = self._currentWork
-			if work is not None:
-				work.cancel()
-			for pending in self._segmentWorks:
-				pending.cancel()
-			operations = tuple(
-				pending.operation for pending in self._segmentWorks if pending.operation is not None
-			)
-			native = self._nativeWork
-			if native is not None:
-				native.admitting = False
-			self._stops += 1
-			self._playerLocal.depth = getattr(self._playerLocal, "depth", 0) + 1
-			self._speechStateLock.notify_all()
-		# Ordinary speech waiting for the contextual resource re-checks its work.
-		self._segmentLifecycle.wake_waiters()
-		if native is not None and native.call_token is not None:
-			self._segmentGate.close(native.call_token)
-		for operation in operations:
-			self._segmentLifecycle.cancel(operation)
+		host = self._segmentHost
+		with host.admission():
+			with self._speechStateLock:
+				if self._playerClosing:
+					return
+			host.cancel()
+			with self._speechStateLock:
+				self._isSilence.set()
+				# WavePlayer.stop clears its own pause state. Keep the final idle
+				# predicate in sync so fresh speech does not await a stale pause.
+				self._paused = False
+				self._pauseRevision += 1
+				dropped = self._drop_queued_speech()
+				call = self._nativeCall
+				if call is not None:
+					call.admitting = False
+				self._stops += 1
+				self._playerLocal.depth = getattr(self._playerLocal, "depth", 0) + 1
+				self._speechStateLock.notify_all()
+			for record in dropped:
+				host.abandon(record)
 		try:
 			self._real_player.stop()
 		finally:
@@ -784,22 +706,68 @@ class SynthDriver(BaseSynthDriver):
 				self._speechStateLock.notify_all()
 			self._retire_player_operation()
 
+	def _drop_queued_speech(self):
+		"""Like the add-on's cancel: drop queued speech, keep settings and DONE.
+
+		A kept NativeTask of a dropped or cancelled record is a no-op.
+
+		Unlike it, never join the BgThread: cancel may run on it, on a callback,
+		a listener or a lifecycle thread. Returns records that will never begin.
+		"""
+		tasks = []
+		try:
+			while True:
+				tasks.append(self._bgQueue.get_nowait())
+				self._bgQueue.task_done()
+		except queue.Empty:
+			pass
+		queued = {task.record for task in tasks if isinstance(task, _Begin)}
+		# Leading tasks belong to the record whose Begin already ran.
+		owner = next(
+			(task.record for task in tasks if isinstance(task, _Retire) and task.record not in queued),
+			None,
+		)
+		kept, dropped = [], []
+		for task in tasks:
+			if isinstance(task, _Begin):
+				owner = task.record
+				dropped.append(task.record)
+			elif isinstance(task, _Retire):
+				if task.record not in queued:
+					kept.append(task)
+				owner = None
+			elif isinstance(task, base.DoneSpeaking):
+				# Segments never publish an anonymous DONE.
+				if owner is None or owner.operation is None:
+					kept.append(task)
+			else:
+				kept.append(task)
+		for task in kept:
+			self._bgQueue.put(task)
+		return dropped
+
 	def _onIndexReached(self, index):
 		if not self._guard_installed:
 			return super()._onIndexReached(index)
-		work = self._currentWork
+		record = self._currentRecord
 		if index is None:
-			if work is not None and work.playback is not None:
+			record = self._doneOwner
+			if record is not None and record.operation is not None:
 				return
-			if self._isSilence.token_cancelled() or (work is not None and work.error is not None):
+			token = record.native.token if record is not None else None
+			# speak() no longer raises, so a failed request still releases its
+			# DONE waiter, as the add-on's DoneSpeaking does; only a cancelled
+			# token silences it.
+			if self._isSilence.token_cancelled() or (token is not None and token.is_cancelled()):
 				return
-		elif self._isSilence.cancelled() or (work is not None and not work.is_valid()):
+		elif self._isSilence.cancelled() or (record is not None and not self._record_valid(record)):
 			return
 		return super()._onIndexReached(index)
 
 	def pause(self, switch):
 		if not self._guard_installed:
 			return super().pause(switch)
+		host = self._segmentHost
 		with self._speechStateLock:
 			if self._terminated:
 				raise RuntimeError("Cerence driver has terminated")
@@ -822,23 +790,19 @@ class SynthDriver(BaseSynthDriver):
 					if revision == self._pauseRevision:
 						break
 		except Exception as error:
+			# A raised pause/resume may have partially changed the player.
+			# Block this core permanently instead of guessing its state.
+			host.latch_control_error(error)
 			with self._speechStateLock:
-				# A raised pause/resume may have partially changed the player.
-				# Block this core permanently instead of guessing its state.
-				if self._segmentBlockedError is None:
-					self._segmentBlockedError = error
-				if self._currentWork is not None:
-					self._currentWork.fault(error)
-				for pending in self._segmentWorks:
-					pending.fault(error)
-				native = self._nativeWork
-				if native is not None:
-					native.admitting = False
+				record = self._currentRecord
+				call = self._nativeCall
+				if call is not None:
+					call.admitting = False
 				self._pauseRevision += 1
 				self._stops += 1
 				self._speechStateLock.notify_all()
-			if native is not None and native.call_token is not None:
-				self._segmentGate.close(native.call_token)
+			if record is not None:
+				host.record_error(record, error)
 			try:
 				# Release a real idle/feed blocked by the uncertain pause state.
 				self._real_player.stop()
@@ -860,12 +824,14 @@ class SynthDriver(BaseSynthDriver):
 	def _is_reentrant_termination(self):
 		return bool(
 			getattr(self._callbackLocal, "depth", 0)
-			or getattr(self._speechLocal, "depth", 0)
 			or getattr(self._playerLocal, "depth", 0)
-			or getattr(self._terminationLocal, "cleaning", False),
+			or getattr(self._terminationLocal, "cleaning", False)
+			or threading.current_thread() is self._bgThread,
 		)
 
 	def _retire_player_operation(self):
+		# A terminate() requested inside this cancel/pause finishes when the
+		# operation that owned the player returns, as before the async inner.
 		self._playerLocal.depth -= 1
 		if self._terminationRequested and not self._is_reentrant_termination():
 			self._finish_termination()
@@ -879,22 +845,24 @@ class SynthDriver(BaseSynthDriver):
 			self._terminationRequested = True
 			self._terminated = True
 		if first:
-			self._segmentLifecycle.terminate()
+			self._segmentHost.terminate()
 			try:
 				self.cancel()
 			except Exception as error:
 				self._terminationError = error
 		if reentrant:
-			# The caller may own speech, a callback, a player operation or
-			# cleanup itself. Its outer owner finishes after retirement.
+			# The caller owns a callback, a player operation or the BgThread
+			# itself; a closer thread finishes once they all retire.
+			if first:
+				threading.Thread(
+					target=self._finish_termination, name="WorldVoice Cerence close", daemon=True
+				).start()
 			return
 		self._finish_termination()
 		if self._terminationError is not None:
 			raise self._terminationError
 
 	def _finish_termination(self):
-		if self._is_reentrant_termination():
-			return
 		with self._speechStateLock:
 			first = not self._terminationCleaning
 			self._terminationCleaning = True
@@ -903,19 +871,21 @@ class SynthDriver(BaseSynthDriver):
 			return
 		self._terminationLocal.cleaning = True
 		try:
-			# Keep native/player resources alive until the coordinator retires its stop.
-			self._segmentLifecycle.wait_idle()
-			with self._speechRunLock:
-				with self._speechStateLock:
-					self._speechStateLock.wait_for(lambda: self._stops == 0 and self._pauses == 0)
-					# Seal atomically with the zero-operation barrier so a late
-					# cancel cannot start another stop against closing resources.
-					self._playerClosing = True
-				callback = self._veCallback
-				self._veCallbackHandler.detach()
-				# The native destruction API also lacks pointer-lifetime proof.
-				_RETAINED_CALLBACKS.append(callback)
-				super().terminate()
+			# Let the BgThread finish its current record, then keep native and
+			# player resources alive through any stop or pause still running.
+			self._bgQueue.put(None)
+			self._bgThread.join()
+			self._segmentHost.wait_idle()
+			with self._speechStateLock:
+				self._speechStateLock.wait_for(lambda: self._stops == 0 and self._pauses == 0)
+				# Seal atomically with the zero-operation barrier so a late
+				# cancel cannot start another stop against closing resources.
+				self._playerClosing = True
+			callback = self._veCallback
+			self._veCallbackHandler.detach()
+			# The native destruction API also lacks pointer-lifetime proof.
+			_RETAINED_CALLBACKS.append(callback)
+			super().terminate()
 		except Exception as error:
 			if self._terminationError is None:
 				self._terminationError = error
@@ -946,7 +916,9 @@ class Voice(Voice):
 		if snapshot.variant != "default" and snapshot.variant not in core.availableVariants:
 			raise ValueError(f"Unavailable variant: {snapshot.variant}")
 		selected = self._defaultVariant if snapshot.variant == "default" else snapshot.variant
-		TtsSetParamList(instance, (VE_PARAM_VOICE_OPERATING_POINT, selected))()
+		# Like every inner setting: applied in order on the BgThread, never
+		# beside an in-flight synthesis on the same instance.
+		core._bgQueue.put(TtsSetParamList(instance, (VE_PARAM_VOICE_OPERATING_POINT, selected)))
 		core.waitfactor = snapshot.waitfactor
 
 	@property
diff --git a/addon/synthDrivers/WorldVoice/driver/Cerence/driver/__init__.py b/addon/synthDrivers/WorldVoice/driver/Cerence/driver/__init__.py
index 84793dc..ab1dbb8 100644
--- a/addon/synthDrivers/WorldVoice/driver/Cerence/driver/__init__.py
+++ b/addon/synthDrivers/WorldVoice/driver/Cerence/driver/__init__.py
@@ -1,4 +1,5 @@
 import math
+import queue
 import threading
 import unicodedata
 import os
@@ -74,6 +75,25 @@ def getAvailableResources():
 
 	return resources
 
+class BgThread(threading.Thread):
+
+	def __init__(self, bgQueue):
+		super().__init__()
+		self._bgQueue = bgQueue
+		self.daemon = True
+		self.start()
+
+	def run(self):
+		while True:
+			task = self._bgQueue.get()
+			if task is None:
+				break
+			try:
+				task()
+			except Exception:
+				log.error("Error running task from queue", exc_info=True)
+			self._bgQueue.task_done()
+
 pcmBufLen = 8192 # 8 Kb
 markBufSize = 100
 
@@ -164,8 +184,8 @@ class VECallback(object):
 					return NUAN_E_TTS_USERSTOP
 				# And check for bookmarks
 				for i in range(int(outData.contents.cntMrkListLen)):
-						if outData.contents.pMrkList[i].eMrkType == VE_MRK_BOOKMARK:
-							self._onIndexReached(int(outData.contents.pMrkList[i].szValue))
+					if outData.contents.pMrkList[i].eMrkType == VE_MRK_BOOKMARK:
+						self._onIndexReached(int(outData.contents.pMrkList[i].szValue))
 			elif messageType == VE_MSG_ENDPROCESS:
 				if self._sonicEnabled and self.sonicStream is not None:
 					self.sonicStream.flush()
@@ -255,6 +275,8 @@ class SynthDriver(SynthDriver):
 		ttsapi.initialize(resources)
 
 		self._instanceCache = {}
+		self._bgQueue = queue.Queue()
+		self._bgThread = BgThread(self._bgQueue)
 
 		try:
 			# Audio device used since NVDA 2025.1
@@ -318,6 +340,8 @@ class SynthDriver(SynthDriver):
 			ttsapi.terminate()
 		except RuntimeError:
 			log.error("CerenceTTS terminate", exc_info=True)
+		self._bgQueue.put(None)
+		self._bgThread.join()
 		self._player.close()
 		self._veCallback = None
 
@@ -391,16 +415,28 @@ class SynthDriver(SynthDriver):
 				log.error(f"Unknown speech: {command}")
 		if chunks:
 			self._speak(currentInstance, chunks)
-		DoneSpeaking(self._player, self._onIndexReached)()
+		self._bgQueue.put(DoneSpeaking(self._player, self._onIndexReached))
 
 	def _speak(self, voiceInstance, chunks):
 		text = "".join(chunks)
-		self._isSilence.clear()
-		ProcessText2Speech(voiceInstance, text)()
+		self._bgQueue.put(ProcessText2Speech(voiceInstance, text))
 
 	def cancel(self):
+		taskList = []
+		try:
+			while True:
+				task = self._bgQueue.get_nowait()
+				self._bgQueue.task_done()
+				if isinstance(task, (TtsSetParamList, DoneSpeaking)):
+					taskList.append(task)
+		except queue.Empty:
+			pass
+		for task in taskList:
+			self._bgQueue.put(task)
 		self._isSilence.set()
+		self._bgQueue.put(self._isSilence.clear)
 		self._player.stop()
+		self._bgQueue.join()
 
 	def pause(self, switch):
 		self._player.pause(switch)
@@ -415,6 +451,28 @@ class SynthDriver(SynthDriver):
 		return self.getParameters(instance, (paramId, type_))[0]
 
 	def getParameters(self, instance, *idAndTypes):
+		taskList = []
+		values = [None] * len(idAndTypes)
+
+		try:
+			while True:
+				task = self._bgQueue.get_nowait()
+				self._bgQueue.task_done()
+				taskList.append(task)
+		except queue.Empty:
+			pass
+
+		for task in filter(lambda t: isinstance(t, TtsSetParamList) and t.instance == instance, taskList):
+			for id, value in task.idAndValues:
+				for i, p in enumerate(idAndTypes):
+					if id == p[0]:
+						values[i] = value
+
+		for task in taskList:
+			self._bgQueue.put(task)
+
+		if None not in values:
+			return values
 		return ttsapi.getParamList(instance, *idAndTypes)
 
 	def _get_voiceInstance(self):
@@ -424,7 +482,7 @@ class SynthDriver(SynthDriver):
 		return self.getParameter(self.voiceInstance, VE_PARAM_VOLUME)
 
 	def _set_volume(self, value):
-		TtsSetParamList(self.voiceInstance, (VE_PARAM_VOLUME, int(value)))()
+		self._bgQueue.put(TtsSetParamList(self.voiceInstance, (VE_PARAM_VOLUME, int(value))))
 
 	def _get_rate(self):
 		if self._rateBoost:
@@ -438,13 +496,13 @@ class SynthDriver(SynthDriver):
 	def _set_rate(self, value):
 		if self._rateBoost:
 			self._rate = self._percentToParamFloat(value, 0.5, 6.0)
-			TtsSetParamList(self.voiceInstance, (VE_PARAM_SPEECHRATE, 100))()
+			self._bgQueue.put(TtsSetParamList(self.voiceInstance, (VE_PARAM_SPEECHRATE, 100)))
 			self._veCallbackHandler.setSpeed(self._rate)
 			return
 		factor = 25.0 if value >= 50 else 50.0
 		norm = 2.0 ** ((value - 50.0) / factor)
 		self._rate = rate = int(round(norm * 100))
-		TtsSetParamList(self.voiceInstance, (VE_PARAM_SPEECHRATE, rate))()
+		self._bgQueue.put(TtsSetParamList(self.voiceInstance, (VE_PARAM_SPEECHRATE, rate)))
 		self._veCallbackHandler.setSpeed(1.0)
 
 	def _get_rateBoost(self):
@@ -466,7 +524,7 @@ class SynthDriver(SynthDriver):
 		norm = 2.0 ** ((value - 50.0) / factor)
 		pitch = int(round(norm * 100))
 
-		TtsSetParamList(self.voiceInstance, (VE_PARAM_PITCH, pitch))()
+		self._bgQueue.put(TtsSetParamList(self.voiceInstance, (VE_PARAM_PITCH, pitch)))
 
 	def _getAvailableVoices(self):
 		voices = []
@@ -489,7 +547,7 @@ class SynthDriver(SynthDriver):
 
 	def _set_variant(self, variant):
 		if variant in self.availableVariants and variant != self.variant:
-			TtsSetParamList(self.voiceInstance, (VE_PARAM_VOICE_OPERATING_POINT, variant))()
+			self._bgQueue.put(TtsSetParamList(self.voiceInstance, (VE_PARAM_VOICE_OPERATING_POINT, variant)))
 
 	def _getAvailableVariants(self):
 		language = self.getParameter(self.voiceInstance, VE_PARAM_LANGUAGE, type_=str) # FIXME: store language...
@@ -500,7 +558,7 @@ class SynthDriver(SynthDriver):
 		return str(self.getParameter(self.voiceInstance, VE_PARAM_WAITFACTOR))
 
 	def _set_waitfactor(self, value):
-		TtsSetParamList(self.voiceInstance, (VE_PARAM_WAITFACTOR, int(value)))()
+		self._bgQueue.put(TtsSetParamList(self.voiceInstance, (VE_PARAM_WAITFACTOR, int(value))))
 
 	def _get_availableWaitfactors(self):
 		return OrderedDict([(v, VoiceInfo(v, v)) for v in [str(v) for v in range(WAITFACTOR_MIN, WAITFACTOR_MAX+1)]])
```

- [ ] **Step 4: Run the tests and the acceptance checks**

Run: `python3 -m pytest tests -q 2>&1 | tail -1`
Expected: `1375 passed, 89 skipped`

Run: `for i in 1 2 3; do python3 -m pytest tests/test_vocalizer_segment_drain.py tests/test_worldvoice_cancel_wrappers.py -q 2>&1 | tail -1; done | sed 's/ in .*//'`
Expected: `231 passed, 2 skipped` three times.

Run:
```bash
O=addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py
I=addon/synthDrivers/WorldVoice/driver/Cerence/driver/__init__.py
R="ref/CerenceTTS(min)/synthDrivers/CerenceTTS/__init__.py"
ruff format --check addon | tail -1
grep -n "_segmentLifecycle\|SegmentLifecycle\|CallbackGate" $O
diff <(sed 's/[[:space:]]*$//' "$R") <(sed 's/[[:space:]]*$//' $I) | grep -c "^[<>]"
git diff --stat -- addon/synthDrivers/WorldVoice/driver/Cerence/driver/ttsapi
```
Expected:
- `53 files already formatted`;
- no grep output;
- `128` differing lines, all of them kept items plus `self.daemon = True`:
  - Sonic and PCM buffering;
  - the ENDPROCESS flush;
  - the rate/pitch mapping and rate boost;
  - the install path;
  - `_veCallbackHandler`/`_rateBoost`;
- no `ttsapi` diff.

- [ ] **Step 5: Commit**

```bash
git add addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py addon/synthDrivers/WorldVoice/driver/Cerence/driver/__init__.py \
	tests/test_vocalizer_segment_drain.py tests/test_engine_segment_contract.py tests/test_lifecycle_private_access.py
git commit -m "refactor(cerence): restore the original async inner driver and run segments through SegmentHost

The inner Cerence driver returns to the original CerenceTTS BgThread queue
(keeping Sonic, the exponential rate/pitch mapping and the WorldVoice
install path). The wrapper, a separate copy of the VE design, queues each
record on that BgThread, so speak() and speak_segment() return once queued
(C3), settings apply in call order, and cancel drops queued speech. The
last contract xfail is gone.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Prove the wrapper bites (mutations M2a–M2i, after the commit)**

```bash
O=addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py
I=addon/synthDrivers/WorldVoice/driver/Cerence/driver/__init__.py
mutate() { python3 - "$1" "$2" "$3" <<'PY'
import sys
p, old, new = sys.argv[1:]
s = open(p).read()
assert s.count(old) == 1, old
open(p, "w").write(s.replace(old, new))
PY
}
check() { timeout 300 python3 -m pytest tests/test_vocalizer_segment_drain.py tests/test_worldvoice_cancel_wrappers.py -q -p no:cacheprovider 2>&1 | grep -E '^FAILED|^[0-9]+ (passed|failed)' | sed 's/ - .*//'; git checkout -- $O $I; }

echo M2a; mutate $O '				host.reach(record, "idle")' '				pass'; check
echo M2b; mutate $O '			for record in dropped:
				host.abandon(record)
		try:' '		try:'; check
echo M2c; mutate $O '				if owner is None or owner.operation is None:
					kept.append(task)' '				kept.append(task)'; check
echo M2d; mutate $I '		self._bgQueue.put(TtsSetParamList(self.voiceInstance, (VE_PARAM_VOLUME, int(value))))' '		TtsSetParamList(self.voiceInstance, (VE_PARAM_VOLUME, int(value)))()'; check
echo M2e; mutate $O '			native=_CerenceRequest(speechSequence, cancellationToken),
		)' '			native=_CerenceRequest(speechSequence, cancellationToken),
		)
		self._bgQueue.join()'; check
echo M2f; mutate $O '			self._legacyUsed = True
		# Like' '			pass
		# Like'; check
echo M2g; mutate $O '_ORDINARY_BARRIERS = frozenset()' '_ORDINARY_BARRIERS = frozenset({"spoken"})'; check
echo M2h; mutate $O '				threading.Thread(
					target=self._finish_termination, name="WorldVoice Cerence close", daemon=True
				).start()' '				pass'; check
echo M2i; mutate $O '				or not isinstance(instance, ttsapi.veTypes.VE_HSAFE)
' ''; check
git status --short | grep addon
```

Expected (each `check` prints its failures, then the count line):
- M2a: drain never reaches `idle`. `15 failed, 216 passed, 2 skipped`:
  - `test_cerence_shared_lifecycle_waits_for_chunk_callback_and_idle[Cerence]`
  - `test_cerence_shared_cancel_retires_guarded_feed_before_successor[Cerence]`
  - `test_vocalizer_endprocess_is_not_segment_drain[Cerence]`
  - `test_contextual_final_idle_keeps_ordinary_speech_out_of_native[Cerence]`
  - `test_token_cancelled_ordinary_leaves_contextual_final_idle_untouched[Cerence]`
  - `test_multichunk_langchange_has_one_work_and_final_drain[Cerence]`
  - `test_explicit_activation_override_allows_successor_after_idle[Cerence]`
  - `test_real_sonic_initialization_failure_uses_native_pcm_fallback[Cerence]`
  - `test_zero_audio_segments_still_wait_for_real_idle[Cerence-empty]`, `[Cerence-index]` and `[Cerence-break]`
  - `test_cerence_bookmark_decodes_szvalue[23-Cerence]`, `[-17-Cerence]` and `[0-Cerence]`
  - `test_segment_drain_waits_for_real_resume_return[Cerence]`
- M2b: cancel does not abandon dropped records. `2 failed, 229 passed, 2 skipped`:
  - `test_cancel_drops_a_segment_queued_behind_the_worker[Cerence]`
  - `test_cancel_during_contextual_final_idle_releases_waiting_ordinary[Cerence]`
- M2c: cancel keeps a dropped segment's `DoneSpeaking`. `1 failed, 230 passed, 2 skipped`: `test_cancel_drops_a_segment_queued_behind_the_worker[Cerence]`
- M2d: the inner volume setter applies immediately. `1 failed, 230 passed, 2 skipped`: `test_settings_apply_in_call_order_with_speech[Cerence]`
- M2e: `speak()` waits for the queue. `8 failed, 223 passed, 2 skipped`:
  - `test_speak_returns_before_native_synthesis[Cerence]`
  - `test_contextual_final_idle_keeps_ordinary_speech_out_of_native[Cerence]`
  - `test_cancel_during_contextual_final_idle_releases_waiting_ordinary[Cerence]`
  - `test_token_cancelled_ordinary_leaves_contextual_final_idle_untouched[Cerence]`
  - `test_terminate_during_contextual_final_idle_with_waiting_ordinary[Cerence-False]` and `[Cerence-True]`
  - `test_done_listener_can_terminate_without_deadlocking_speech[Cerence]`
  - `test_ordinary_waiting_behind_contextual_does_not_poll[Cerence]`
- M2f: legacy use is not marked at `speak()`. `1 failed, 230 passed, 2 skipped`: `test_legacy_use_prevents_entering_unproven_correlated_mode[Cerence]`
- M2g: ordinary records require `spoken`. `1 failed, 230 passed, 2 skipped`: `test_cancel_during_real_callback_feed_stops_after_feed[Cerence]`
- M2h: no closer thread for a re-entrant terminate. `4 failed, 227 passed, 2 skipped`:
  - `test_player_hook_can_reenter_terminate[Cerence-stop]` and `[Cerence-idle]`
  - `test_done_listener_can_terminate_without_deadlocking_speech[Cerence]`
  - `test_index_listener_can_terminate_and_retire_native_before_close[Cerence]`
- M2i: callback admission drops the `VE_HSAFE` check. `2 failed, 229 passed, 2 skipped`:
  - `test_token_cancellation_rejects_real_callback_before_core_cancel[Cerence]`
  - `test_cancelled_native_piece_rejects_callback_and_never_starts_next_piece[Cerence]`

The final `git status` prints nothing.

---

### Task 3: Final verification

**Files:** none modified.

- [ ] **Step 1: Stability**

Run: `for i in 1 2 3 4 5; do python3 -m pytest tests/test_vocalizer_segment_drain.py tests/test_worldvoice_cancel_wrappers.py tests/test_engine_segment_contract.py tests/test_runtime_drain_integration.py tests/test_f4_engine_adapters.py tests/test_segment_host.py -q 2>&1 | tail -1; done | sed 's/ in .*//' | sort | uniq -c`
Expected: one line, `5 352 passed, 17 skipped`.

Run: `for i in $(seq 1 20); do python3 -m pytest tests/test_vocalizer_segment_drain.py tests/test_worldvoice_cancel_wrappers.py -q 2>&1 | tail -1; done | sed 's/ in .*//' | sort | uniq -c`
Expected: one line, `20 231 passed, 2 skipped`.

- [ ] **Step 2: The other engines are untouched and green**

Run: `git diff master --stat -- addon/synthDrivers/WorldVoice/runtime addon/synthDrivers/WorldVoice/driver/OneCore addon/synthDrivers/WorldVoice/driver/Espeak addon/synthDrivers/WorldVoice/driver/SAPI5 addon/synthDrivers/WorldVoice/driver/RHVoice addon/synthDrivers/WorldVoice/driver/VE/driver`
Expected: no output.

Run: `python3 -m pytest tests/test_onecore_segment_drain.py tests/test_rhvoice_segment_drain.py tests/test_sapi5_segment_drain.py tests/test_espeak_segment_drain.py -q 2>&1 | tail -1`
Expected: `196 passed`.

Run: `python3 -m pytest tests/test_engine_segment_contract.py -q -rx 2>&1 | tail -1`
Expected: `24 passed, 4 skipped`, with no `xfailed`.

- [ ] **Step 3: Full suite and protected paths**

Run: `python3 -m pytest tests -q 2>&1 | tail -1`
Expected: `1375 passed, 89 skipped`

Run:
```bash
ruff format --check addon | tail -1
git ls-files addon/synthDrivers/WorldVoice/driver/Neural
git log --oneline master..HEAD
```
Expected:
- `53 files already formatted`, then no output from `ls-files`.
- The log lists, oldest at the bottom:
  1. `docs: add phase 3d-2 Cerence migration design spec`
  2. `docs: add phase 3d-2 implementation plan and amend its spec`
  3. `refactor(ve): drop the redundant queue lock and name the inner BgThread as the worker`
  4. `refactor(cerence): restore the original async inner driver and run segments through SegmentHost`
