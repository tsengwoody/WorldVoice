# Phase 3a: SegmentHost Core and eSpeak Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `runtime/segmentHost.py` (NativeRecord, NativeStrategy, SegmentHost, LeasedPlayer) and move the eSpeak wrapper onto it, without changing any other engine.

**Architecture:**
- **Cross-engine runtime fixes first:**
  - `PlaybackWork` terminal events wake waiters.
  - `EngineSession` rejects tokens that cannot notify.
  - Token removal is exact.
  - The guard regex is broader.
  - The lock-order docs are completed.
- **The host:**
  - `SegmentHost` owns a `SegmentLifecycle` and implements its five hooks.
  - It runs the shared flow: accept or reject, a thread per segment, records, consumers, the control-error latch, FIFO retirement, cancel/terminate with a bounded delivery join.
  - Engines supply a `NativeStrategy` and mark their own barriers.
- **eSpeak migration:**
  - eSpeak keeps only its native specifics: the FIFO markers, `_SegmentNative`, index binding and the ordinary-speech done notification.
  - Its tests read host state instead of removed internals.

**Tech Stack:** Python 3 threading, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-10-01-phase3a-segment-host-design.md`

## Global Constraints

- Work on branch `phase3a-segment-host`, cut from `master` at `024835c`; the spec commit `36a5a3f` is on it.
- **Do not change** `addon/synthDrivers/WorldVoice/driver/{RHVoice,SAPI5,OneCore,VE,Cerence}/__init__.py`. Their tests must pass unchanged, and VE/Cerence contract 4 stays xfail.
- `SegmentLifecycle`'s public API stays as in phase 2.
- Never modify `driver/<Engine>/driver/` and never commit `driver/Neural/`. Neural compatibility is not required.
- No shared VE/Cerence code. Code shared by all engines lives only in `runtime/segmentHost.py`.
- New public names are snake_case.
- Every changed `addon/` file passes `ruff format --check`; new test files pass `ruff check`.
- Run from `/workspace/WorldVoice` (tests need the untracked `ref/`). Stage explicit paths only; never stage the user's unstaged deletion of `docs/superpowers/finish_task.md`.
- Baseline before Task 1: `python3 -m pytest tests -q` → `1277 passed, 96 skipped, 2 xfailed`.
- Each code step applies a patch saved verbatim from this plan. Set `PATCHES=$(mktemp -d)` once, save the block to the named file, then run `git apply`.
- Every commit message ends with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. eSpeak is cancelled while ordinary speech plays and a contextual segment is queued → the ordinary audio keeps playing, and the cancelled segment stays silent. Covered by the existing `test_cancelling_queued_contextual_speech_preserves_active_ordinary_audio`, which Task 3 points at `host.enqueue`.
2. A delivery sink blocks or calls `terminate()` → `terminate()` neither self-joins nor hangs; the join is bounded to 1 s. Task 2, `test_sink_can_terminate_without_self_join` and `test_terminate_does_not_hang_on_a_blocked_sink` (mutation M2e).
3. A player stop fails mid-segment → only the first control error is kept, pending work fails with it, and later segments are rejected. Task 2, `test_first_control_error_fails_pending_work_and_rejects_new_segments` (mutation M2d).
4. The other five engines run unmodified on the changed runtime → their wrappers are byte-identical, and their drain and contract tests pass. Task 4, Step 2.
5. A native path skips one completion barrier (e.g. eSpeak never marks `returned`) → the segment fails instead of draining. Task 2, `test_missing_barrier_fails_and_discards_audio` (M2a); Task 3, Step 4 mutation M3.

---

### Task 1: Cross-engine runtime requirements

These changes reach every engine. Spec §6 items 1–6.

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/runtime/playbackWork.py` (`_terminate` calls `on_cancel` after delivering)
- Modify: `addon/synthDrivers/WorldVoice/runtime/session.py` (`EngineSession.speak` rejects tokens without `add_callback`)
- Modify: `addon/synthDrivers/WorldVoice/runtime/scheduler.py` (`CancellationToken.cancel` re-checks each callback under the lock)
- Modify: `addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py` (lock-order docstring: leaf-lock edges)
- Modify: `tests/test_lifecycle_private_access.py` (regex covers `_lifecycle` and `getattr`)
- Modify: `tests/test_runtime_composition.py` (fake tokens get `add_callback` through `_idle_token()`)
- Modify: `tests/test_runtime_session.py` (`EventToken` implements the full contract)
- Test: `tests/test_playback_work.py`, `tests/test_segment_lifecycle.py`, `tests/test_runtime_scheduler.py`, `tests/test_runtime_session.py`, `tests/test_lifecycle_private_access.py`

**Interfaces:**
- Produces:
  - `EngineSession.speak` raises `TypeError("speech tokens must implement CancellationView.add_callback")`.
  - `PlaybackWork.fail()`/`complete_drained()` call `on_cancel` after the sink.
  - `CancellationToken`: a callback removed before its turn never runs.

- [ ] **Step 1: Write the failing tests**

Save as `$PATCHES/t1-tests.patch`, then run `git apply $PATCHES/t1-tests.patch`:

```diff
diff --git a/tests/test_lifecycle_private_access.py b/tests/test_lifecycle_private_access.py
index 23b5252..d21b222 100644
--- a/tests/test_lifecycle_private_access.py
+++ b/tests/test_lifecycle_private_access.py
@@ -22,6 +22,16 @@ def test_guard_pattern_separates_lifecycle_state_from_wrapper_data():
 	assert _private_accesses(sample) == ["operation._run_started", "_segmentLifecycle._condition"]
 
 
+def test_guard_pattern_catches_lifecycle_aliases_and_getattr():
+	assert _private_accesses("self._lifecycle._condition") == ["_lifecycle._condition"]
+	assert _private_accesses('getattr(operation, "_run_started", False)') == ['getattr(operation, "_run_started"']
+	assert _private_accesses("getattr(self._segmentLifecycle, '_delivery_thread')") == [
+		"getattr(self._segmentLifecycle, '_delivery_thread'",
+	]
+	assert _private_accesses('getattr(self, "_veCallbackHandler", None)') == []
+	assert _private_accesses('getattr(operation, "_espeak_native", None)') == []
+
+
 def test_wrappers_do_not_touch_lifecycle_private_state():
 	found = []
 	for wrapper in sorted(DRIVERS.glob("*/__init__.py")):
diff --git a/tests/test_playback_work.py b/tests/test_playback_work.py
index 77c35a3..2a65e6a 100644
--- a/tests/test_playback_work.py
+++ b/tests/test_playback_work.py
@@ -343,3 +343,17 @@ def test_direct_cancel_notifies_owner_after_releasing_the_work_lock(work_env):
     assert finished.wait(1), "on_cancel ran while the work lock was held"
     assert seen == [False]
     assert events == []
+
+
+@pytest.mark.parametrize("finish", ["fail", "complete_drained"])
+def test_terminal_event_notifies_owner_after_releasing_the_work_lock(work_env, finish):
+    rt, token, context, events, _ = work_env
+    seen = []
+    work = rt.playback_work.PlaybackWork(context, token, events.append,
+                                         on_cancel=lambda: seen.append(work.is_valid()))
+    finished = Event()
+    action = (lambda: work.fail(RuntimeError("failed"))) if finish == "fail" else work.complete_drained
+    Thread(target=lambda: (action(), finished.set()), daemon=True).start()
+    assert finished.wait(1), "on_cancel ran while the work lock was held"
+    assert seen == [False]
+    assert len(events) == 1
diff --git a/tests/test_runtime_scheduler.py b/tests/test_runtime_scheduler.py
index 665d7ea..d9b1e8e 100644
--- a/tests/test_runtime_scheduler.py
+++ b/tests/test_runtime_scheduler.py
@@ -788,3 +788,18 @@ def test_cancellation_callback_runs_outside_the_token_lock(scheduler):
     Thread(target=lambda: (token.cancel(), finished.set()), daemon=True).start()
     assert finished.wait(1), "cancel() deadlocked inside a callback"
     assert seen == [True, "nested"]
+
+
+def test_callback_removed_during_dispatch_is_not_called(scheduler):
+    token = scheduler.CancellationToken()
+    calls = []
+    removers = {}
+
+    def first():
+        calls.append("first")
+        removers["second"]()
+
+    token.add_callback(first)
+    removers["second"] = token.add_callback(lambda: calls.append("second"))
+    token.cancel()
+    assert calls == ["first"]
diff --git a/tests/test_runtime_session.py b/tests/test_runtime_session.py
index ff96d90..8ff1c83 100644
--- a/tests/test_runtime_session.py
+++ b/tests/test_runtime_session.py
@@ -1,5 +1,6 @@
 from concurrent.futures import ThreadPoolExecutor
 from threading import Event
+from types import SimpleNamespace
 
 import pytest
 
@@ -208,17 +209,29 @@ def test_capability_and_metadata_queries_do_not_activate(session, adapter, store
 
 
 class EventToken:
+    """Minimal CancellationView: callbacks run once on cancel() and can be removed."""
+
     def __init__(self):
         self.cancelled = Event()
+        self._callbacks = []
+
+    def cancel(self):
+        if self.cancelled.is_set():
+            return
+        self.cancelled.set()
+        callbacks, self._callbacks = self._callbacks, []
+        for callback in callbacks:
+            callback()
 
     def is_cancelled(self):
         return self.cancelled.is_set()
 
     def add_callback(self, callback):
-        # Tests set ``cancelled`` directly; no waiter in these tests subscribes.
         if self.cancelled.is_set():
             callback()
-        return lambda: None
+            return lambda: None
+        self._callbacks.append(callback)
+        return lambda: callback in self._callbacks and self._callbacks.remove(callback)
 
 
 @pytest.mark.parametrize("mode", ["LEGACY_DONE", "DRAIN"])
@@ -310,3 +323,10 @@ def test_session_rejects_finishing_foreign_context(rt, session, adapter):
     with pytest.raises(ValueError, match="source"):
         session.finish_segment(rt.models.PlaybackContext(object(), 1))
     assert adapter.finished == []
+
+
+def test_speak_rejects_a_token_without_cancellation_callbacks(session, adapter):
+    token = SimpleNamespace(is_cancelled=lambda: False)
+    with pytest.raises(TypeError, match="add_callback"):
+        session.speak(("hello",), token)
+    assert adapter.spoken == []
diff --git a/tests/test_segment_lifecycle.py b/tests/test_segment_lifecycle.py
index da4a6d1..5c9bda1 100644
--- a/tests/test_segment_lifecycle.py
+++ b/tests/test_segment_lifecycle.py
@@ -772,7 +772,7 @@ def test_queued_run_does_not_poll_its_token(env, start_delay):
     owner_call.finish()
 
 
-@pytest.mark.parametrize("cancel", ["token", "work"])
+@pytest.mark.parametrize("cancel", ["token", "work", "fail"])
 def test_queued_run_wakes_when_cancelled(env, cancel):
     lifecycle, hooks, events, accept = env
     _, owner_call = _hold_resource(env)
@@ -781,8 +781,10 @@ def test_queued_run_wakes_when_cancelled(env, cancel):
     waiting.blocked()
     if cancel == "token":
         queued.work.token.cancel()
-    else:
+    elif cancel == "work":
         queued.work.cancel()
+    else:
+        queued.work.fail(RuntimeError("failed while queued"))
     assert waiting.done.wait(0.5), "queued run was not woken by cancellation"
     waiting.finish()
     assert len(hooks.submitted) == 1
```

This patch also gives `EventToken` the full `add_callback` contract. It is test-only and keeps the existing session tests green.

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests -q 2>&1 | grep -E "^FAILED|passed|failed" | sed 's/ - .*//'`
Expected: `6 failed, 1277 passed, 96 skipped, 2 xfailed`, with exactly these failures:
- `test_lifecycle_private_access.py::test_guard_pattern_catches_lifecycle_aliases_and_getattr`
- `test_playback_work.py::test_terminal_event_notifies_owner_after_releasing_the_work_lock[fail]` and `[complete_drained]`
- `test_runtime_scheduler.py::test_callback_removed_during_dispatch_is_not_called`
- `test_runtime_session.py::test_speak_rejects_a_token_without_cancellation_callbacks`
- `test_segment_lifecycle.py::test_queued_run_wakes_when_cancelled[fail]`

- [ ] **Step 3: Implement**

Save as `$PATCHES/t1-impl.patch`, then run `git apply $PATCHES/t1-impl.patch`:

```diff
diff --git a/addon/synthDrivers/WorldVoice/runtime/playbackWork.py b/addon/synthDrivers/WorldVoice/runtime/playbackWork.py
index 681465b..a161f46 100644
--- a/addon/synthDrivers/WorldVoice/runtime/playbackWork.py
+++ b/addon/synthDrivers/WorldVoice/runtime/playbackWork.py
@@ -103,6 +103,9 @@ class PlaybackWork:
 			)
 		# The sink may cancel/unbind, reenter this work, or block.
 		self._on_event(event)
+		# A finished work is invalid too; wake its owner's waiters.
+		if self._on_cancel is not None:
+			self._on_cancel()
 		return True
 
 
diff --git a/addon/synthDrivers/WorldVoice/runtime/scheduler.py b/addon/synthDrivers/WorldVoice/runtime/scheduler.py
index eec3563..862fae0 100644
--- a/addon/synthDrivers/WorldVoice/runtime/scheduler.py
+++ b/addon/synthDrivers/WorldVoice/runtime/scheduler.py
@@ -56,9 +56,13 @@ class CancellationToken:
 			if self._event.is_set():
 				return
 			self._event.set()
-			callbacks, self._callbacks = list(self._callbacks.values()), {}
-		for callback in callbacks:
-			self._run_callback(callback)
+			keys = list(self._callbacks)
+		for key in keys:
+			# Re-check under the lock: a callback removed meanwhile never runs.
+			with self._lock:
+				callback = self._callbacks.pop(key, None)
+			if callback is not None:
+				self._run_callback(callback)
 
 	def is_cancelled(self):
 		return self._event.is_set()
diff --git a/addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py b/addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py
index 1cfb6ac..2d804c6 100644
--- a/addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py
+++ b/addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py
@@ -9,10 +9,13 @@ Lock order:
    always lock in that order.
 2. A token's cancellation callback may take the lifecycle condition while the
    scheduler holds its state condition (scheduler -> callback -> lifecycle).
-3. While holding its condition the lifecycle never calls hooks, sinks or token
-   callbacks, and never takes a wrapper or scheduler lock. ``wait_idle`` is the
-   one exception: it calls the caller's ``still_wanted`` predicate, which must
-   only read state under its own leaf lock.
+3. While holding its condition the lifecycle never calls hooks or sinks, and
+   never takes a wrapper or scheduler lock. It may take leaf locks: a token's
+   own lock (add_callback and its remover) and a PlaybackWork lock (is_valid).
+   Subscribing to an already-cancelled token runs wake_waiters() at once,
+   which re-enters the (reentrant) condition. ``wait_idle`` also calls the
+   caller's ``still_wanted`` predicate, which must only read state under its
+   own leaf lock.
 
 Waits are woken by notifications (resource release, cancel(), token
 callbacks, PlaybackWork.cancel(), wake_waiters()), never by polling.
diff --git a/addon/synthDrivers/WorldVoice/runtime/session.py b/addon/synthDrivers/WorldVoice/runtime/session.py
index 4a498f0..ad0bfbb 100644
--- a/addon/synthDrivers/WorldVoice/runtime/session.py
+++ b/addon/synthDrivers/WorldVoice/runtime/session.py
@@ -171,6 +171,10 @@ class EngineSession:
 		*,
 		context: PlaybackContext | None = None,
 	) -> None:
+		if not callable(getattr(token, "add_callback", None)):
+			# Waiters subscribe instead of polling, so a token that cannot
+			# notify would leave them blocked.
+			raise TypeError("speech tokens must implement CancellationView.add_callback")
 		if context is None:
 			if self.completion.mode is not CompletionMode.LEGACY_DONE:
 				raise ValueError("Correlated completion requires a playback context")
diff --git a/tests/test_lifecycle_private_access.py b/tests/test_lifecycle_private_access.py
index d21b222..97efce3 100644
--- a/tests/test_lifecycle_private_access.py
+++ b/tests/test_lifecycle_private_access.py
@@ -4,7 +4,11 @@ import re
 from pathlib import Path
 
 DRIVERS = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice/driver"
-PRIVATE_ACCESS = re.compile(r"\b(operation|lifecycle|_segmentLifecycle)\._(\w+)")
+LIFECYCLE_OBJECTS = r"(?:operation|lifecycle|_lifecycle|_segmentLifecycle)"
+PRIVATE_ACCESS = re.compile(rf"(?<![A-Za-z0-9]){LIFECYCLE_OBJECTS}\._(\w+)")
+PRIVATE_GETATTR = re.compile(
+	rf"getattr\(\s*(?:self\.)?{LIFECYCLE_OBJECTS}\s*,\s*[\"']_(\w+)[\"']",
+)
 # Per-operation data each wrapper attaches itself; SegmentHost replaces it in phase 3.
 WRAPPER_PREFIXES = ("ve_", "onecore_", "rhvoice_", "espeak_", "neural_")
 
@@ -12,8 +16,9 @@ WRAPPER_PREFIXES = ("ve_", "onecore_", "rhvoice_", "espeak_", "neural_")
 def _private_accesses(text):
 	return [
 		match.group(0)
-		for match in PRIVATE_ACCESS.finditer(text)
-		if not match.group(2).startswith(WRAPPER_PREFIXES)
+		for pattern in (PRIVATE_ACCESS, PRIVATE_GETATTR)
+		for match in pattern.finditer(text)
+		if not match.group(1).startswith(WRAPPER_PREFIXES)
 	]
 
 
diff --git a/tests/test_runtime_composition.py b/tests/test_runtime_composition.py
index e493cff..9a95155 100644
--- a/tests/test_runtime_composition.py
+++ b/tests/test_runtime_composition.py
@@ -15,6 +15,12 @@ from test_worldvoice_request_builder import EventStub
 from test_worldvoice_index_command import nvda_commands
 
 
+def _idle_token():
+    """A never-cancelled token that honours the CancellationView contract."""
+    return SimpleNamespace(is_cancelled=lambda: False, add_callback=lambda callback: (lambda: None))
+
+
+
 @pytest.fixture
 def composition(monkeypatch):
     manager_module = _load_voice_manager(monkeypatch, {})
@@ -143,7 +149,7 @@ def test_failed_alias_open_preserves_existing_owner_and_closes_once(composition)
         spoken.append(commands)
     shared.speak = speak
     assert session.activate("first:a")
-    session.speak(("owner remains usable",), SimpleNamespace(is_cancelled=lambda: False))
+    session.speak(("owner remains usable",), _idle_token())
     assert spoken == [("owner remains usable",)]
     manager.terminate(commit=False)
     assert shared.closes == 1
@@ -487,7 +493,7 @@ def test_alias_uses_one_allocator_and_one_close(composition, nvda_commands):
     shared.speak = lambda commands: spoken.append(commands[-1].index)
     for segment, key in enumerate(("first:a", "alias:a"), 1):
         port = manager.resolve_playback(key)
-        port.speak(("hello",), SimpleNamespace(is_cancelled=lambda: False),
+        port.speak(("hello",), _idle_token(),
                    context=c.models.PlaybackContext(port.source_id, segment))
     assert spoken == [501, 502]
     manager.terminate(commit=False)
@@ -569,7 +575,7 @@ def test_live_core_rebind_preserves_allocator_high_water(composition, nvda_comma
     port = manager.resolve_playback("marker:a")
     spoken = []
     cls.core.speak = lambda commands: spoken.append(commands[-1].index)
-    token = SimpleNamespace(is_cancelled=lambda: False)
+    token = _idle_token()
     port.speak(("first",), token, context=c.models.PlaybackContext(port.source_id, 1))
     c.bridge.unbind(port.source_id)
     c.bridge.bind(cls.core, port.source_id, completion=port.completion)
@@ -870,7 +876,7 @@ def test_drain_factory_configured_after_bind_before_publication(composition, mon
     manager = c.create(lambda cls, core: drain_contract(c))
     port = manager.resolve_playback("drain:a")
     context = c.models.PlaybackContext(port.source_id, 1)
-    port.speak(("hello",), SimpleNamespace(is_cancelled=lambda: False), context=context)
+    port.speak(("hello",), _idle_token(), context=context)
     assert len(setup) == 1
     assert calls[0]["context"] is context and callable(calls[0]["on_event"])
 
```

`tests/test_runtime_composition.py` passes `SimpleNamespace(is_cancelled=...)` tokens through `EngineSession`. The new check rejects those, so this patch replaces them with `_idle_token()`, which also has `add_callback`.

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests -q 2>&1 | tail -1`
Expected: `1283 passed, 96 skipped, 2 xfailed`

Run: `ruff format --check addon | tail -1`
Expected: `52 files already formatted`

- [ ] **Step 5: Commit**

```bash
git add addon/synthDrivers/WorldVoice/runtime/playbackWork.py addon/synthDrivers/WorldVoice/runtime/session.py \
	addon/synthDrivers/WorldVoice/runtime/scheduler.py addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py \
	tests/test_playback_work.py tests/test_segment_lifecycle.py tests/test_runtime_scheduler.py \
	tests/test_runtime_session.py tests/test_runtime_composition.py tests/test_lifecycle_private_access.py
git commit -m "fix(runtime): wake on terminal events, require notifying tokens, exact callback removal

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `runtime/segmentHost.py`

**Files:**
- Create: `addon/synthDrivers/WorldVoice/runtime/segmentHost.py`
- Create: `tests/test_segment_host.py`

**Interfaces:**
- Consumes `SegmentLifecycle`, `SegmentOperation`, `ProducerLease` (unchanged) and Task 1's `PlaybackWork`.
- Produces, for Task 3:
  - `NativeRecord(work, barriers, operation, producer, retired, handoff, cancelled, closed, error, consumers)` with `barriers_met()`, `missing_barriers()` and `is_valid()`.
  - `OrdinaryOutcome(cancelled: bool, error: Exception | None)`.
  - The `NativeStrategy` protocol: `barriers`, `submit(host, record, commands)`, `stop_native(host, record)`, `stop_player(host)`.
  - `SegmentHost(engine, strategy)`:
    - Entry points: `admission()`, `terminated`, `control_error`, `on_delivery_thread()`, `speak_segment(...)`, `enqueue(commands, work=None, operation=None)`, `cancel()`, `terminate() -> bool`.
    - Records and consumers: `new_record`, `begin`, `current`, `callback_record`, `bound_callback`, `consumer(record=None)`, `reach(record, barrier)`, `record_error`, `latch_control_error`, `forget`, `retire(record) -> OrdinaryOutcome | None`.
    - The five lifecycle hooks.
  - `LeasedPlayer(host, player, *, idle_barrier="idle")` with `feed`, `idle` and `stop`.
- Behavior details:
  - A missing barrier fails with `RuntimeError("<engine> synthesis retired without its <names> barriers")`.
  - A terminated host rejects with `RuntimeError("<engine> driver has terminated")`.

- [ ] **Step 1: Write the failing tests**

Save as `$PATCHES/t2-tests.patch`, then run `git apply $PATCHES/t2-tests.patch`:

```diff
diff --git a/tests/test_segment_host.py b/tests/test_segment_host.py
new file mode 100644
index 0000000..57a7ed5
--- /dev/null
+++ b/tests/test_segment_host.py
@@ -0,0 +1,361 @@
+"""SegmentHost and LeasedPlayer against a fake engine strategy."""
+
+import importlib.util
+import sys
+from threading import Condition, Event, Thread, get_ident
+from types import SimpleNamespace
+
+import pytest
+from runtime_harness import RUNTIME, load_runtime, load_scheduler
+
+
+class FakeStrategy:
+	"""Records submitted native work; tests step it through begin/reach/retire."""
+
+	barriers = frozenset({"returned", "idle"})
+
+	def __init__(self):
+		self.condition = Condition()
+		self.submitted = []
+		self.native_stops = []
+		self.player_stops = 0
+		self.submit_error = None
+
+	def submit(self, host, record, commands):
+		if self.submit_error is not None:
+			raise self.submit_error
+		with self.condition:
+			self.submitted.append((record, commands))
+			self.condition.notify_all()
+
+	def stop_native(self, host, record):
+		with self.condition:
+			self.native_stops.append(record)
+			self.condition.notify_all()
+
+	def stop_player(self, host):
+		self.player_stops += 1
+
+	def wait_submitted(self, count=1):
+		with self.condition:
+			assert self.condition.wait_for(lambda: len(self.submitted) >= count, 2), (
+				"native work was not submitted"
+			)
+			return self.submitted[count - 1][0]
+
+
+class Events(list):
+	def __init__(self):
+		super().__init__()
+		self.condition = Condition()
+		self.threads = []
+
+	def append(self, event):
+		with self.condition:
+			super().append(event)
+			self.threads.append(get_ident())
+			self.condition.notify_all()
+
+	def wait_one(self):
+		with self.condition:
+			assert self.condition.wait_for(lambda: bool(self), 2), "no terminal event delivered"
+			self.condition.wait_for(lambda: len(self) > 1, 0.1)
+			assert len(self) == 1, list(self)
+			return self[0]
+
+
+def _load(monkeypatch, rt, name):
+	full = f"{rt.package.__name__}.{name}"
+	spec = importlib.util.spec_from_file_location(full, RUNTIME / f"{name}.py")
+	module = importlib.util.module_from_spec(spec)
+	monkeypatch.setitem(sys.modules, full, module)
+	spec.loader.exec_module(module)
+	return module
+
+
+@pytest.fixture
+def env(monkeypatch):
+	rt = load_runtime(monkeypatch)
+	scheduler = load_scheduler(monkeypatch, rt)
+	_load(monkeypatch, rt, "segmentLifecycle")
+	module = _load(monkeypatch, rt, "segmentHost")
+	strategy = FakeStrategy()
+	host = module.SegmentHost("Fake", strategy)
+	threads = []
+
+	def speak(segment=17, sink=None, token=None):
+		events = Events()
+		token = token or scheduler.CancellationToken()
+		context = rt.models.PlaybackContext(object(), segment)
+		host.speak_segment(("hello",), token, context=context, on_event=sink or events.append)
+		return token, context, events
+
+	def run_native(record, reach=("returned", "idle")):
+		# The engine's FIFO worker: begin, mark barriers, retire (blocks until handoff).
+		def work():
+			host.begin(record)
+			for barrier in reach:
+				host.reach(record, barrier)
+			result.append(host.retire(record))
+
+		result = []
+		thread = Thread(target=work, daemon=True)
+		thread.start()
+		threads.append(thread)
+		return thread, result
+
+	yield SimpleNamespace(
+		rt=rt,
+		scheduler=scheduler,
+		module=module,
+		host=host,
+		strategy=strategy,
+		speak=speak,
+		run_native=run_native,
+	)
+	host.terminate()
+	for thread in threads:
+		thread.join(2)
+
+
+def test_completed_segment_drains_once_after_every_barrier(env):
+	_, context, events = env.speak()
+	record = env.strategy.wait_submitted()
+	assert record.operation is not None
+	native, _ = env.run_native(record)
+	event = events.wait_one()
+	native.join(2)
+	assert event.kind is env.rt.models.EventKind.SEGMENT_DRAINED
+	assert (event.source_id, event.segment_id) == (context.source_id, 17)
+	assert env.strategy.player_stops == 0
+
+
+def test_missing_barrier_fails_and_discards_audio(env):
+	_, _, events = env.speak()
+	record = env.strategy.wait_submitted()
+	env.run_native(record, reach=("returned",))
+	event = events.wait_one()
+	assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
+	assert str(event.error) == "Fake synthesis retired without its idle barriers"
+	# The lifecycle's own stop/drain pass after fail() may stop the player again.
+	assert env.strategy.player_stops >= 1
+
+
+def test_native_error_fails_the_original_segment(env):
+	_, context, events = env.speak()
+	record = env.strategy.wait_submitted()
+	env.host.record_error(record, OSError("native failed"))
+	env.run_native(record)
+	event = events.wait_one()
+	assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
+	assert isinstance(event.error, OSError)
+	assert event.segment_id == context.segment_id
+
+
+def test_submit_error_fails_the_segment(env):
+	env.strategy.submit_error = RuntimeError("queue rejected")
+	_, _, events = env.speak()
+	event = events.wait_one()
+	assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
+	assert env.strategy.submitted == []
+
+
+def test_terminated_host_rejects_without_submitting(env):
+	assert env.host.terminate() is True
+	assert env.host.terminate() is False
+	_, _, events = env.speak(segment=19)
+	event = events.wait_one()
+	assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
+	assert str(event.error) == "Fake driver has terminated"
+	assert env.strategy.submitted == []
+	assert events.threads[0] != get_ident()
+
+
+def test_first_control_error_fails_pending_work_and_rejects_new_segments(env):
+	_, _, events = env.speak()
+	record = env.strategy.wait_submitted()
+	first, second = OSError("stop failed"), OSError("second stop failed")
+	env.host.latch_control_error(first)
+	env.host.latch_control_error(second)
+	assert env.host.control_error is first
+	env.run_native(record)
+	assert events.wait_one().error is first
+	_, _, rejected = env.speak(segment=18)
+	assert rejected.wait_one().error is first
+	assert len(env.strategy.submitted) == 1
+
+
+def test_cancel_keeps_accepted_segment_silent_and_stops_active_native(env):
+	_, _, events = env.speak()
+	record = env.strategy.wait_submitted()
+	env.host.begin(record)
+	env.host.cancel()
+	# The lifecycle asks for the stop on its own thread.
+	with env.strategy.condition:
+		assert env.strategy.condition.wait_for(lambda: env.strategy.native_stops == [record], 1)
+	native, _ = env.run_native(record)
+	native.join(2)
+	with events.condition:
+		events.condition.wait_for(lambda: bool(events), 0.2)
+	assert list(events) == []
+
+
+def test_sink_can_terminate_without_self_join(env):
+	terminated = Event()
+
+	def sink(event):
+		env.host.terminate()
+		terminated.set()
+
+	env.speak(sink=sink)
+	env.run_native(env.strategy.wait_submitted())
+	assert terminated.wait(2), "terminate() from the delivery thread deadlocked"
+
+
+def test_terminate_does_not_hang_on_a_blocked_sink(env):
+	entered, release = Event(), Event()
+
+	def sink(event):
+		entered.set()
+		release.wait(5)
+
+	env.speak(sink=sink)
+	env.run_native(env.strategy.wait_submitted())
+	assert entered.wait(2)
+	finished = Event()
+	Thread(target=lambda: (env.host.terminate(), finished.set()), daemon=True).start()
+	try:
+		# The delivery join is bounded to one second.
+		assert finished.wait(2), "terminate() waited on a blocked sink"
+	finally:
+		release.set()
+
+
+def test_retire_waits_for_admitted_consumers(env):
+	record = env.host.new_record(None)
+	env.host.begin(record)
+	release, retired = Event(), Event()
+
+	def consume():
+		with env.host.consumer() as admitted:
+			assert admitted is record
+			release.wait(2)
+
+	consumer = Thread(target=consume, daemon=True)
+	consumer.start()
+	Event().wait(0.05)
+	Thread(target=lambda: (env.host.retire(record), retired.set()), daemon=True).start()
+	assert not retired.wait(0.1), "retire() did not wait for the admitted consumer"
+	release.set()
+	assert retired.wait(1)
+	with env.host.consumer(record) as late:
+		assert late is None
+
+
+@pytest.mark.parametrize("case", ["complete", "missing", "error", "cancelled"])
+def test_ordinary_record_outcomes(env, case):
+	env.host.enqueue(("ordinary",))
+	record = env.strategy.wait_submitted()
+	assert record.operation is None and record.work is None
+	env.host.begin(record)
+	if case != "missing":
+		env.host.reach(record, "returned")
+		env.host.reach(record, "idle")
+	if case == "error":
+		env.host.record_error(record, OSError("feed failed"))
+	if case == "cancelled":
+		env.host.cancel()
+	outcome = env.host.retire(record)
+	assert outcome.cancelled is (case == "cancelled")
+	if case == "complete":
+		assert outcome.error is None
+		assert env.strategy.player_stops == 0
+	elif case == "missing":
+		assert "returned, idle" in str(outcome.error) or "idle, returned" in str(outcome.error)
+		assert env.strategy.player_stops == 1
+	elif case == "error":
+		assert isinstance(outcome.error, OSError)
+		assert env.strategy.player_stops == 1
+	else:
+		assert outcome.error is None
+		assert env.strategy.player_stops == 1
+
+
+def test_ordinary_speech_raises_after_a_control_error(env):
+	error = OSError("stop failed")
+	env.host.latch_control_error(error)
+	with pytest.raises(OSError, match="stop failed"):
+		env.host.enqueue(("ordinary",))
+	assert env.strategy.submitted == []
+
+
+def test_unknown_barrier_is_rejected(env):
+	record = env.host.new_record(None)
+	with pytest.raises(KeyError):
+		env.host.reach(record, "ended")
+
+
+class FakePlayer:
+	def __init__(self):
+		self.fed, self.callbacks, self.stops, self.idles = [], [], 0, 0
+		self.stop_error = None
+
+	def feed(self, data, size=None, onDone=None):
+		self.fed.append(data)
+		if onDone is not None:
+			self.callbacks.append(onDone)
+
+	def idle(self):
+		self.idles += 1
+
+	def stop(self):
+		self.stops += 1
+		if self.stop_error is not None:
+			raise self.stop_error
+
+
+def test_leased_player_ignores_feed_without_a_current_record(env):
+	real = FakePlayer()
+	player = env.module.LeasedPlayer(env.host, real)
+	assert player.feed(b"pcm") is None
+	assert real.fed == []
+
+
+def test_leased_player_binds_on_done_to_its_record_and_reaches_idle(env):
+	real = FakePlayer()
+	player = env.module.LeasedPlayer(env.host, real)
+	record = env.host.new_record(None)
+	env.host.begin(record)
+	seen = []
+	player.feed(b"pcm", 3, lambda: seen.append(env.host.callback_record()))
+	real.callbacks[0]()
+	assert seen == [record]
+	assert env.host.callback_record() is None
+	player.idle()
+	assert record.barriers["idle"] is True
+
+
+def test_leased_player_stops_again_after_an_invalidated_feed(env):
+	real = FakePlayer()
+	player = env.module.LeasedPlayer(env.host, real)
+	env.host.enqueue(("ordinary",))
+	record = env.strategy.wait_submitted()
+	env.host.begin(record)
+	original_feed = real.feed
+
+	def feed_then_cancel(*args):
+		original_feed(*args)
+		env.host.cancel()
+
+	real.feed = feed_then_cancel
+	player.feed(b"pcm")
+	assert real.stops == 1
+
+
+def test_leased_player_stop_failure_latches_a_control_error(env):
+	real = FakePlayer()
+	real.stop_error = OSError("stop failed")
+	player = env.module.LeasedPlayer(env.host, real)
+	with pytest.raises(OSError):
+		player.stop()
+	assert env.host.control_error is real.stop_error
```

`FakeStrategy` records submitted work. Each test steps its own FIFO worker through `begin` → `reach` → `retire`, using the fixture's `run_native`.

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_segment_host.py -q 2>&1 | tail -1`
Expected: `20 errors`, each a `FileNotFoundError` for `runtime/segmentHost.py`.

- [ ] **Step 3: Implement**

Save as `$PATCHES/t2-impl.patch`, then run `git apply $PATCHES/t2-impl.patch`:

```diff
diff --git a/addon/synthDrivers/WorldVoice/runtime/segmentHost.py b/addon/synthDrivers/WorldVoice/runtime/segmentHost.py
new file mode 100644
index 0000000..3fbbb21
--- /dev/null
+++ b/addon/synthDrivers/WorldVoice/runtime/segmentHost.py
@@ -0,0 +1,452 @@
+"""Shared segment flow for engine wrappers; engines supply only native specifics.
+
+A SegmentHost owns one SegmentLifecycle and implements its hooks. It accepts
+contextual segments, rejects them after termination or a control fault, runs
+each one on its own thread, records native work for both contextual and
+ordinary speech, admits callback/player consumers, latches control errors and
+retires work in the engine's FIFO order. An engine provides a NativeStrategy
+(how to queue, stop and drain its native work) and marks its own completion
+barriers on each record.
+
+Lock order: host admission -> host condition -> lifecycle condition. The host
+never calls the strategy, a sink or a player while holding its own condition.
+"""
+
+from collections.abc import Callable, Iterator
+from contextlib import contextmanager
+from dataclasses import dataclass, field
+import logging
+from threading import Condition, Event, RLock, Thread, local
+from typing import Protocol
+
+from .models import PlaybackContext, PlaybackEvent, SegmentEventSink, SpeechCommands
+from .playbackWork import PlaybackWork
+from .segmentLifecycle import ProducerLease, SegmentLifecycle, SegmentOperation
+from .session import CancellationView
+
+
+log = logging.getLogger(__name__)
+
+
+@dataclass(eq=False)
+class NativeRecord:
+	"""One unit of native work, for a contextual segment or ordinary speech."""
+
+	work: PlaybackWork | None
+	barriers: dict[str, bool] = field(default_factory=dict)
+	operation: SegmentOperation | None = None
+	producer: ProducerLease | None = None
+	retired: Event | None = None
+	handoff: Event | None = None
+	cancelled: bool = False
+	closed: bool = False
+	error: Exception | None = None
+	consumers: int = 0
+
+	def barriers_met(self) -> bool:
+		return all(self.barriers.values())
+
+	def missing_barriers(self) -> tuple[str, ...]:
+		return tuple(name for name, reached in self.barriers.items() if not reached)
+
+	def is_valid(self) -> bool:
+		return not self.cancelled and not self.closed and (self.work is None or self.work.is_valid())
+
+
+@dataclass(frozen=True)
+class OrdinaryOutcome:
+	"""How an ordinary (non-contextual) record retired."""
+
+	cancelled: bool
+	error: Exception | None
+
+
+class NativeStrategy(Protocol):
+	"""What an engine supplies; everything else is the host's."""
+
+	barriers: frozenset[str]
+
+	def submit(self, host: "SegmentHost", record: NativeRecord, commands: SpeechCommands) -> None:
+		"""Queue native work for ``record``; arrange for ``host.retire(record)`` when it ends."""
+
+	def stop_native(self, host: "SegmentHost", record: NativeRecord) -> None:
+		"""Stop the native work that is currently running ``record``."""
+
+	def stop_player(self, host: "SegmentHost") -> None:
+		"""Discard queued audio; used after cancellation or failure."""
+
+
+class SegmentHost:
+	def __init__(self, engine: str, strategy: NativeStrategy):
+		self.engine = engine
+		self._strategy = strategy
+		self._admission = RLock()
+		self._condition = Condition(RLock())
+		self._callback_local = local()
+		self._terminated = False
+		self._control_error: Exception | None = None
+		self._current: NativeRecord | None = None
+		self._pending: list[NativeRecord] = []
+		self._records: dict[SegmentOperation, NativeRecord] = {}
+		# Accepted operations -> whether the host cancelled them (keeps them silent).
+		self._accepted: dict[SegmentOperation, bool] = {}
+		self._lifecycle = SegmentLifecycle(self)
+
+	# Entry points ---------------------------------------------------------
+
+	@contextmanager
+	def admission(self) -> Iterator[None]:
+		"""Hold admission so no segment is accepted until the block ends."""
+		with self._admission:
+			yield
+
+	@property
+	def terminated(self) -> bool:
+		return self._terminated
+
+	@property
+	def control_error(self) -> Exception | None:
+		with self._condition:
+			return self._control_error
+
+	def on_delivery_thread(self) -> bool:
+		return self._lifecycle.on_delivery_thread()
+
+	def speak_segment(
+		self,
+		commands: SpeechCommands,
+		token: CancellationView,
+		*,
+		context: PlaybackContext,
+		on_event: SegmentEventSink,
+	) -> None:
+		with self._admission:
+			if self._terminated:
+				self._lifecycle.reject_new(
+					context,
+					token,
+					on_event,
+					RuntimeError(f"{self.engine} driver has terminated"),
+				)
+				return
+			control_error = self.control_error
+			if control_error is not None:
+				self._lifecycle.reject_new(context, token, on_event, control_error)
+				return
+
+			def deliver(event):
+				self._deliver(operation, on_event, event)
+
+			operation = self._lifecycle.accept(context, token, deliver)
+			with self._condition:
+				self._accepted[operation] = False
+		Thread(
+			target=self._run,
+			args=(operation, tuple(commands), deliver),
+			name=f"WorldVoice {self.engine} lifecycle",
+			daemon=True,
+		).start()
+
+	def enqueue(self, commands: SpeechCommands, work: PlaybackWork | None = None, operation=None) -> None:
+		"""Queue native work; ordinary speech passes neither work nor operation."""
+		record = self.new_record(work, operation)
+		with self._admission:
+			if self._terminated:
+				if work is not None:
+					work.cancel()
+				return
+			with self._condition:
+				control_error = self._control_error
+				if control_error is not None and operation is None:
+					raise control_error
+				self._pending.append(record)
+				if operation is not None:
+					self._records[operation] = record
+			if control_error is not None:
+				self._lifecycle.fail(operation, control_error)
+				record.retired.set()
+				return
+			if operation is not None:
+				record.producer = self._lifecycle.admit_producer(operation)
+			self._strategy.submit(self, record, commands)
+
+	def cancel(self) -> None:
+		with self._admission:
+			self._invalidate()
+
+	def terminate(self) -> bool:
+		"""Stop all work; return False when already terminated."""
+		with self._admission:
+			if self._terminated:
+				return False
+			self._terminated = True
+			self._invalidate()
+			self._lifecycle.terminate()
+		self._lifecycle.join_delivery(1)
+		return True
+
+	# Records and consumers ------------------------------------------------
+
+	def new_record(
+		self,
+		work: PlaybackWork | None,
+		operation: SegmentOperation | None = None,
+	) -> NativeRecord:
+		segment = operation is not None
+		return NativeRecord(
+			work,
+			barriers=dict.fromkeys(self._strategy.barriers, False),
+			operation=operation,
+			retired=Event() if segment else None,
+			handoff=Event() if segment else None,
+		)
+
+	def begin(self, record: NativeRecord) -> None:
+		with self._condition:
+			self._current = record
+
+	def current(self) -> NativeRecord | None:
+		with self._condition:
+			return self._current
+
+	def callback_record(self) -> NativeRecord | None:
+		return getattr(self._callback_local, "record", None)
+
+	@contextmanager
+	def bound_callback(self, record: NativeRecord) -> Iterator[None]:
+		"""Bind ``record`` for a delayed player callback on this thread."""
+		previous = self.callback_record()
+		self._callback_local.record = record
+		try:
+			yield
+		finally:
+			self._callback_local.record = previous
+
+	@contextmanager
+	def consumer(self, record: NativeRecord | None = None) -> Iterator[NativeRecord | None]:
+		"""Admit a callback or player call for the current record (None if not admitted)."""
+		with self._condition:
+			record = record or self._current
+			if record is None or record is not self._current or not record.is_valid():
+				admitted = None
+			else:
+				record.consumers += 1
+				admitted = record
+		try:
+			yield admitted
+		finally:
+			if admitted is not None:
+				with self._condition:
+					admitted.consumers -= 1
+					self._condition.notify_all()
+
+	def reach(self, record: NativeRecord, barrier: str) -> None:
+		with self._condition:
+			if barrier not in record.barriers:
+				raise KeyError(barrier)
+			record.barriers[barrier] = True
+
+	def record_error(self, record: NativeRecord | None, error: Exception) -> None:
+		with self._condition:
+			if record is not None and record.error is None:
+				record.error = error
+
+	def latch_control_error(self, error: Exception) -> None:
+		# A stop failure does not prove queued callbacks were discarded. Keep the
+		# first control error until the driver reloads, and fail pending work.
+		with self._condition:
+			if self._control_error is None:
+				self._control_error = error
+			for record in self._pending:
+				if record.error is None:
+					record.error = self._control_error
+
+	def forget(self, record: NativeRecord) -> None:
+		with self._condition:
+			if record in self._pending:
+				self._pending.remove(record)
+
+	def retire(self, record: NativeRecord) -> OrdinaryOutcome | None:
+		"""Retire ``record`` in FIFO order; return the outcome for ordinary speech."""
+		with self._condition:
+			valid = record.is_valid()
+			record.closed = True
+			self._condition.wait_for(lambda: record.consumers == 0)
+			valid = valid and not record.cancelled and (record.work is None or record.work.is_valid())
+			if not valid and record in self._pending:
+				self._pending.remove(record)
+			if self._current is record:
+				self._current = None
+		if record.operation is not None:
+			if record.producer is not None:
+				self._lifecycle.retire_producer(record.producer)
+			record.retired.set()
+			# The FIFO worker keeps player ownership until the coordinator has
+			# finished the final stop or drain check for this operation.
+			record.handoff.wait()
+			return None
+		if not valid:
+			# Token-only cancellation can skip the terminal idle; discard queued audio.
+			try:
+				self._strategy.stop_player(self)
+			except Exception:
+				log.error("Error stopping cancelled %s playback", self.engine, exc_info=True)
+			return OrdinaryOutcome(cancelled=True, error=None)
+		error = record.error
+		if error is None and not record.barriers_met():
+			error = self._missing_barriers_error(record)
+		if error is not None and self.control_error is None:
+			try:
+				self._strategy.stop_player(self)
+			except Exception as stop_error:
+				log.error("Error stopping failed %s playback", self.engine, exc_info=True)
+				self.record_error(record, stop_error)
+		return OrdinaryOutcome(cancelled=False, error=error)
+
+	# SegmentEngineHooks ---------------------------------------------------
+
+	def submit_native(self, operation: SegmentOperation, commands: SpeechCommands) -> None:
+		self.enqueue(commands, operation.work, operation)
+
+	def request_stop(self, operation: SegmentOperation) -> None:
+		with self._condition:
+			record = self._records.get(operation)
+			if record is not None:
+				record.cancelled = True
+				active = record is self._current
+			else:
+				active = False
+		if active:
+			self._strategy.stop_native(self, record)
+
+	def wait_native_boundary(self, operation: SegmentOperation) -> None:
+		with self._condition:
+			record = self._records[operation]
+		record.retired.wait()
+		if record.error is not None:
+			self._lifecycle.fail(operation, record.error)
+
+	def wait_native_retired(self, operation: SegmentOperation) -> None:
+		# retire() already waited for every admitted consumer.
+		return
+
+	def wait_playback_drained(self, operation: SegmentOperation) -> None:
+		with self._condition:
+			record = self._records.get(operation)
+		if record is None:
+			return
+		if not operation.work.is_valid() or record.error is not None:
+			self._strategy.stop_player(self)
+			return
+		if not record.barriers_met():
+			self._lifecycle.fail(operation, self._missing_barriers_error(record))
+			self._strategy.stop_player(self)
+
+	# Internals ------------------------------------------------------------
+
+	def _missing_barriers_error(self, record: NativeRecord) -> RuntimeError:
+		return RuntimeError(
+			f"{self.engine} synthesis retired without its {', '.join(record.missing_barriers())} barriers",
+		)
+
+	def _run(self, operation: SegmentOperation, commands: SpeechCommands, deliver: Callable) -> None:
+		try:
+			self._lifecycle.run(operation, commands)
+		except Exception as error:
+			self._lifecycle.reject_new(
+				operation.work.context,
+				operation.work.token,
+				deliver,
+				self.control_error or error.__cause__ or error,
+			)
+		finally:
+			with self._condition:
+				record = self._records.pop(operation, None)
+				if self._accepted.get(operation) or operation.work.token.is_cancelled():
+					self._accepted.pop(operation, None)
+			if record is not None:
+				record.handoff.set()
+
+	def _deliver(self, operation: SegmentOperation, sink: SegmentEventSink, event: PlaybackEvent) -> None:
+		try:
+			with self._condition:
+				silenced = self._accepted.get(operation, False)
+			if not operation.work.token.is_cancelled() and not silenced and not self._terminated:
+				sink(event)
+		finally:
+			# Work stays cancellable until publication starts on the delivery thread.
+			with self._condition:
+				self._accepted.pop(operation, None)
+				for record in self._pending:
+					if record.operation is operation:
+						self._pending.remove(record)
+						break
+
+	def _invalidate(self) -> None:
+		with self._condition:
+			for operation in tuple(self._accepted):
+				self._accepted[operation] = True
+				self._lifecycle.cancel(operation)
+			for record in self._pending:
+				record.cancelled = True
+				if record.work is not None and record.operation is None:
+					record.work.cancel()
+
+
+class LeasedPlayer:
+	"""Admit every feed/idle as a consumer of the current record."""
+
+	def __init__(self, host: SegmentHost, player, *, idle_barrier: str | None = "idle"):
+		self._host = host
+		self._player = player
+		self._idle_barrier = idle_barrier
+
+	def __getattr__(self, name):
+		return getattr(self._player, name)
+
+	def feed(self, data, size=None, onDone=None):
+		host = self._host
+		with host.consumer() as record:
+			if record is None:
+				return None
+			callback = None
+			if onDone is not None:
+
+				def callback():
+					with host.consumer(record) as admitted:
+						if admitted is None:
+							return
+						with host.bound_callback(record):
+							onDone()
+
+			try:
+				return self._player.feed(data, size, callback)
+			except Exception as error:
+				host.record_error(record, error)
+				raise
+			finally:
+				# A feed that was already admitted may queue audio after cancel's
+				# stop. Stop it again before the FIFO barrier permits a successor.
+				if not record.is_valid():
+					self.stop()
+
+	def idle(self):
+		host = self._host
+		with host.consumer() as record:
+			if record is None:
+				return None
+			try:
+				result = self._player.idle()
+			except Exception as error:
+				host.record_error(record, error)
+				raise
+			if self._idle_barrier is not None:
+				host.reach(record, self._idle_barrier)
+			return result
+
+	def stop(self):
+		try:
+			return self._player.stop()
+		except Exception as error:
+			self._host.latch_control_error(error)
+			raise
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/test_segment_host.py -q 2>&1 | tail -1`
Expected: `20 passed`

Run: `python3 -m pytest tests -q 2>&1 | tail -1`
Expected: `1303 passed, 96 skipped, 2 xfailed`

Run: `ruff format --check addon | tail -1; ruff check tests/test_segment_host.py`
Expected: `53 files already formatted`, `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add addon/synthDrivers/WorldVoice/runtime/segmentHost.py tests/test_segment_host.py
git commit -m "feat(runtime): SegmentHost, NativeRecord, NativeStrategy and LeasedPlayer

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Prove the host tests bite (mutations M2a–M2e)**

```bash
H=addon/synthDrivers/WorldVoice/runtime/segmentHost.py
mutate() { python3 - "$1" "$2" <<'PY'
import sys
p = "addon/synthDrivers/WorldVoice/runtime/segmentHost.py"
s = open(p).read()
assert s.count(sys.argv[1]) == 1, sys.argv[1]
open(p, "w").write(s.replace(sys.argv[1], sys.argv[2]))
PY
}
check() { python3 -m pytest tests/test_segment_host.py -q 2>&1 | grep -E '^FAILED|passed|failed' | sed 's/ - .*//'; git checkout -- $H; }

mutate "		if not record.barriers_met():
			self._lifecycle.fail(operation, self._missing_barriers_error(record))" "		if False:
			self._lifecycle.fail(operation, self._missing_barriers_error(record))"; check   # M2a
mutate "			self._condition.wait_for(lambda: record.consumers == 0)" "			pass"; check   # M2b
mutate "				if not record.is_valid():
					self.stop()" "				if False:
					self.stop()"; check   # M2c
mutate "			if self._control_error is None:
				self._control_error = error" "			if True:
				self._control_error = error"; check   # M2d
mutate "		self._lifecycle.join_delivery(1)" "		self._lifecycle.join_delivery()"; check   # M2e
git status --short | grep addon
```

Expected: each mutation fails exactly one test, with `1 failed, 19 passed`:
- M2a: `test_missing_barrier_fails_and_discards_audio`
- M2b: `test_retire_waits_for_admitted_consumers`
- M2c: `test_leased_player_stops_again_after_an_invalidated_feed`
- M2d: `test_first_control_error_fails_pending_work_and_rejects_new_segments`
- M2e: `test_terminate_does_not_hang_on_a_blocked_sink`

The final `git status` prints nothing.

---

### Task 3: Move eSpeak onto SegmentHost

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py` (full rewrite: `_EspeakStrategy`, `_SegmentNative` on host, `LeasedPlayer`, host-delegating `speak_segment`/`speak`/`cancel`/`terminate`, index binding, ordinary done notification)
- Modify: `tests/test_espeak_segment_drain.py`:
  - The fixture also drops the cached `runtime.segmentHost`.
  - Six assertions read host state instead of removed internals: `_segmentNative` → `_segmentHost.current()`, `_segmentAccepted` → `_segmentHost._accepted`, `_queueSpeech` → `_segmentHost.enqueue`, `_deliverSpeech` → `_segmentHost._deliver`, `_segmentLifecycle` → `_segmentHost._lifecycle`.
- Modify: `tests/engine_contract_harness.py` (drops cached `segmentHost`; `on_delivery_thread` prefers `_segmentHost`)
- Modify: `tests/test_runtime_completion_policies.py` (a migrated core's host owns the lifecycle and implements its hooks)
- Modify: `tests/test_lifecycle_private_access.py` (adds `MIGRATED = ("Espeak",)`: these use `SegmentHost` and never mention `SegmentLifecycle`)

**Interfaces:**
- Consumes the Task 2 API.
- Produces `SynthDriver._segmentHost`. Later sub-phases follow the same pattern for each engine.

- [ ] **Step 1: Point the tests at the host**

Save as `$PATCHES/t3-tests.patch`, then run `git apply $PATCHES/t3-tests.patch`:

```diff
diff --git a/tests/engine_contract_harness.py b/tests/engine_contract_harness.py
index 6c4c060..9e67df9 100644
--- a/tests/engine_contract_harness.py
+++ b/tests/engine_contract_harness.py
@@ -25,6 +25,7 @@ def _fresh_lifecycle_module(monkeypatch):
 	# Each loader reloads runtime models; reload the coordinator too so its
 	# event enum belongs to that same runtime copy.
 	monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentLifecycle", raising=False)
+	monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentHost", raising=False)
 
 
 class _Adapter:
@@ -46,7 +47,9 @@ class _Adapter:
 		self.core.terminate()
 
 	def on_delivery_thread(self):
-		return self.core._segmentLifecycle.on_delivery_thread()
+		host = getattr(self.core, "_segmentHost", None)
+		lifecycle = host if host is not None else self.core._segmentLifecycle
+		return lifecycle.on_delivery_thread()
 
 
 class EspeakAdapter(_Adapter):
diff --git a/tests/test_espeak_segment_drain.py b/tests/test_espeak_segment_drain.py
index edeeb7d..01842ce 100644
--- a/tests/test_espeak_segment_drain.py
+++ b/tests/test_espeak_segment_drain.py
@@ -12,6 +12,7 @@ from espeak_drain_harness import finish, load_espeak, speak, wait_event
 @pytest.fixture
 def env(monkeypatch, tmp_path):
     monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentLifecycle", raising=False)
+    monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentHost", raising=False)
     result = load_espeak(monkeypatch, tmp_path)
     yield result
     finish(result)
@@ -86,7 +87,7 @@ def test_espeak_shared_lifecycle_waits_for_fifo_and_empty_audio_idle(env):
     env.native.next_scripts.append({"empty": True})
     _, context, events = speak(env, commands=("",))
     call = env.native.wait_calls(1)
-    assert isinstance(env.driver._segmentNative.operation, lifecycle.SegmentOperation)
+    assert isinstance(env.driver._segmentHost.current().operation, lifecycle.SegmentOperation)
     assert env.player.idle_entered.wait(1)
     old_index = call.index_callback
     old_index(42)
@@ -110,7 +111,7 @@ def test_espeak_token_cancel_after_feed_discards_pcm_before_successor(env):
     first = env.native.wait_calls(1)
     assert first.before_terminal.wait(1)
     assert env.player.queued_bytes == 8
-    assert isinstance(env.driver._segmentNative.operation, lifecycle.SegmentOperation)
+    assert isinstance(env.driver._segmentHost.current().operation, lifecycle.SegmentOperation)
     token.cancel()
     _, successor_context, successor_events = speak(env, segment=18)
     assert len(env.native.calls) == 1
@@ -171,19 +172,19 @@ def test_cancelling_queued_contextual_speech_preserves_active_ordinary_audio(env
     assert ordinary.before_terminal.wait(1)
     assert env.player.queued_bytes == 8
     queued, release_queue = Event(), Event()
-    original_queue = env.driver._queueSpeech
+    original_queue = env.driver._segmentHost.enqueue
     def queue_then_hold(commands, work, operation=None):
         result = original_queue(commands, work, operation)
         if operation is not None:
             queued.set()
             assert release_queue.wait(2), "Test did not release contextual submission"
         return result
-    monkeypatch.setattr(env.driver, "_queueSpeech", queue_then_hold)
+    monkeypatch.setattr(env.driver._segmentHost, "enqueue", queue_then_hold)
     token, _, cancelled_events = speak(env, segment=18)
     assert queued.wait(1)
     token.cancel()
     release_queue.set()
-    operation = next(iter(env.driver._segmentAccepted))
+    operation = next(iter(env.driver._segmentHost._accepted))
     with operation._lifecycle._condition:
         assert operation._lifecycle._condition.wait_for(lambda: operation._stop_done is not None, 1)
         stop_done = operation._stop_done
@@ -271,13 +272,13 @@ def test_terminal_sink_can_terminate_after_native_retirement(env):
 @pytest.mark.parametrize("terminate", [False, True])
 def test_cancel_or_terminate_before_deferred_delivery_keeps_event_silent(env, monkeypatch, terminate):
     entered, release, delivered = Event(), Event(), Event()
-    original = env.driver._deliverSpeech
-    def delayed(native, error):
+    original = env.driver._segmentHost._deliver
+    def delayed(*args):
         entered.set()
         assert release.wait(2)
-        original(native, error)
+        original(*args)
         delivered.set()
-    monkeypatch.setattr(env.driver, "_deliverSpeech", delayed)
+    monkeypatch.setattr(env.driver._segmentHost, "_deliver", delayed)
     _, _, events = speak(env)
     call = env.native.wait_calls(1)
     env.player.idle_release.set()
@@ -467,6 +468,6 @@ def test_speak_after_terminate_fails_through_lifecycle_delivery(env):
     assert events[0].source_id is context.source_id
     assert events[0].segment_id == 19
     assert str(events[0].error) == "eSpeak driver has terminated"
-    assert threads == [env.driver._segmentLifecycle._delivery_thread.ident]
+    assert threads == [env.driver._segmentHost._lifecycle._delivery_thread.ident]
     assert threads[0] != caller
     assert env.native.calls == []
diff --git a/tests/test_lifecycle_private_access.py b/tests/test_lifecycle_private_access.py
index 97efce3..564f9b5 100644
--- a/tests/test_lifecycle_private_access.py
+++ b/tests/test_lifecycle_private_access.py
@@ -43,3 +43,14 @@ def test_wrappers_do_not_touch_lifecycle_private_state():
 		for number, line in enumerate(wrapper.read_text(encoding="utf-8").splitlines(), 1):
 			found.extend(f"{wrapper.parent.name}:{number}: {access}" for access in _private_accesses(line))
 	assert found == []
+
+
+# Wrappers moved onto SegmentHost; the host owns their lifecycle entirely.
+MIGRATED = ("Espeak",)
+
+
+def test_migrated_wrappers_only_use_the_segment_host():
+	for name in MIGRATED:
+		text = (DRIVERS / name / "__init__.py").read_text(encoding="utf-8")
+		assert "SegmentHost" in text, name
+		assert "_segmentLifecycle" not in text and "SegmentLifecycle" not in text, name
diff --git a/tests/test_runtime_completion_policies.py b/tests/test_runtime_completion_policies.py
index 3a5b4db..910f7b3 100644
--- a/tests/test_runtime_completion_policies.py
+++ b/tests/test_runtime_completion_policies.py
@@ -295,8 +295,14 @@ def test_seven_enabled_profiles_use_shared_lifecycle(monkeypatch, tmp_path, engi
         assert policies.FORCE_UNVERIFIED_DRAIN is True
         assert sys.modules["synthDrivers.WorldVoice.driver." + engine] is outer
         assert outer.Voice.synth_driver_class is type(core)
-        assert isinstance(core._segmentLifecycle, outer.SegmentLifecycle)
-        assert core._segmentLifecycle._hooks is core
+        host = getattr(core, "_segmentHost", None)
+        if host is not None:
+            # Migrated wrappers: the host owns the lifecycle and implements its hooks.
+            assert isinstance(host, outer.SegmentHost)
+            assert host._lifecycle._hooks is host
+        else:
+            assert isinstance(core._segmentLifecycle, outer.SegmentLifecycle)
+            assert core._segmentLifecycle._hooks is core
         support = policies.get_segment_drain_support(outer.Voice, core,
             nvda_version="2026.1", audio_mode=installed.mode)
         assert support.supported is True
```

The harness and fixture also drop the cached `runtime.segmentHost` module. Each loader reloads the runtime models, and a stale host module would compare events against an older `EventKind`.

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests -q 2>&1 | grep -E "^FAILED|passed|failed" | sed 's/ - .*//'`
Expected: `7 failed, 1297 passed, 96 skipped, 2 xfailed`.
- The failures are six `test_espeak_segment_drain.py` tests, each an `AttributeError` for `_segmentHost`:
  - `test_espeak_shared_lifecycle_waits_for_fifo_and_empty_audio_idle`
  - `test_espeak_token_cancel_after_feed_discards_pcm_before_successor`
  - `test_cancelling_queued_contextual_speech_preserves_active_ordinary_audio`
  - `test_cancel_or_terminate_before_deferred_delivery_keeps_event_silent[False]` and `[True]`
  - `test_speak_after_terminate_fails_through_lifecycle_delivery`
- The seventh is `test_lifecycle_private_access.py::test_migrated_wrappers_only_use_the_segment_host`.

- [ ] **Step 3: Rewrite the eSpeak wrapper**

Save as `$PATCHES/t3-impl.patch`, then run `git apply $PATCHES/t3-impl.patch`:

```diff
diff --git a/addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py b/addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py
index d29b3c7..ccbb52d 100644
--- a/addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py
+++ b/addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py
@@ -1,5 +1,4 @@
-from dataclasses import dataclass
-from threading import Condition, Event, RLock, Thread, local
+from threading import Thread
 import weakref
 
 from synthDrivers import _espeak
@@ -7,103 +6,10 @@ from synthDrivers.espeak import SynthDriver as BaseSynthDriver
 from synthDriverHandler import synthDoneSpeaking
 from logHandler import log
 from synthDrivers.WorldVoice.driver import Voice
-from ...runtime.models import PlaybackContext, PlaybackEvent, SegmentEventSink, SpeechCommands
-from ...runtime.playbackWork import PlaybackWork, runtime_profile, unverified_drain_support
+from ...runtime.models import PlaybackContext, SegmentEventSink, SpeechCommands
+from ...runtime.playbackWork import runtime_profile, unverified_drain_support
+from ...runtime.segmentHost import LeasedPlayer, NativeRecord, SegmentHost
 from ...runtime.session import CancellationView
-from ...runtime.segmentLifecycle import SegmentLifecycle
-
-
-@dataclass(eq=False)
-class _NativeSpeech:
-	work: PlaybackWork | None
-	operation: object | None = None
-	retired: Event | None = None
-	handoff: Event | None = None
-	producer: object | None = None
-	cancelled: bool = False
-	closed: bool = False
-	ended: bool = False
-	idle_completed: bool = False
-	returned: bool = False
-	error: Exception | None = None
-	consumers: int = 0
-
-	def is_valid(self):
-		return not self.cancelled and not self.closed and (self.work is None or self.work.is_valid())
-
-
-class _SegmentPlayer:
-	"""Retain the original native job around PCM and delayed index callbacks."""
-
-	def __init__(self, driver, player):
-		self._driver = weakref.ref(driver)
-		self._player = player
-
-	def __getattr__(self, name):
-		return getattr(self._player, name)
-
-	def feed(self, data, size=None, onDone=None):
-		driver = self._driver()
-		if driver is None:
-			return
-		native = driver._admitConsumer()
-		if native is None:
-			return
-		callback = None
-		if onDone is not None:
-
-			def callback():
-				owner = self._driver()
-				if owner is None or not owner._admitConsumer(native):
-					return
-				previous = getattr(owner._segmentCallbackLocal, "native", None)
-				owner._segmentCallbackLocal.native = native
-				try:
-					onDone()
-				finally:
-					owner._segmentCallbackLocal.native = previous
-					owner._releaseConsumer(native)
-
-		try:
-			return self._player.feed(data, size, callback)
-		except Exception as error:
-			driver._recordError(native, error)
-			raise
-		finally:
-			try:
-				# A feed that was already admitted may queue audio after cancel's
-				# stop. Stop it again before the FIFO barrier permits a successor.
-				if not native.is_valid():
-					self.stop()
-			finally:
-				driver._releaseConsumer(native)
-
-	def idle(self):
-		driver = self._driver()
-		if driver is None:
-			return
-		native = driver._admitConsumer()
-		if native is None:
-			return
-		try:
-			result = self._player.idle()
-			with driver._segmentCondition:
-				native.idle_completed = True
-			return result
-		except Exception as error:
-			driver._recordError(native, error)
-			raise
-		finally:
-			driver._releaseConsumer(native)
-
-	def stop(self):
-		try:
-			return self._player.stop()
-		except Exception as error:
-			driver = self._driver()
-			if driver is not None:
-				driver._recordControlError(error)
-			raise
 
 
 class _SegmentNative:
@@ -118,24 +24,23 @@ class _SegmentNative:
 
 	def espeak_ng_Cancel(self, *args):
 		driver = self._driver()
-		if driver is not None and driver._segmentControlError is not None:
+		if driver is not None and driver._segmentHost.control_error is not None:
 			return _espeak.EE_OK
 		try:
 			return self._native.espeak_ng_Cancel(*args)
 		except Exception as error:
 			driver = self._driver()
 			if driver is not None:
-				driver._recordError(driver._segmentNative, error)
+				driver._segmentHost.record_error(driver._segmentHost.current(), error)
 			raise
 
 	def espeak_Synth(self, *args):
 		driver = self._driver()
 		if driver is None:
 			return _espeak.EE_OK
-		with driver._segmentCondition:
-			native = driver._segmentNative
-			control_error = driver._segmentControlError
-		if native is None or control_error is not None or not native.is_valid():
+		host = driver._segmentHost
+		record = host.current()
+		if record is None or host.control_error is not None or not record.is_valid():
 			return _espeak.EE_OK
 		try:
 			result = self._native.espeak_Synth(*args)
@@ -143,29 +48,47 @@ class _SegmentNative:
 				raise RuntimeError("eSpeak synthesis failed with code %s" % result)
 			return result
 		except Exception as error:
-			driver._recordError(native, error)
+			host.record_error(record, error)
 			raise
 		finally:
-			with driver._segmentCondition:
-				native.returned = True
+			host.reach(record, "returned")
+
+
+class _EspeakStrategy:
+	"""eSpeak's native queue: NVDA's FIFO with begin and retire markers."""
+
+	barriers = frozenset({"returned", "ended", "idle"})
+
+	def __init__(self, driver):
+		self._driver = weakref.ref(driver)
+
+	def submit(self, host, record, commands):
+		driver = self._driver()
+		# Begin and retirement remain separate queue entries: NVDA stop()
+		# removes queued _speak calls but preserves both identity barriers.
+		_espeak._execWhenDone(driver._beginSpeech, record, mustBeAsync=True)
+		try:
+			BaseSynthDriver.speak(driver, commands)
+		except Exception as error:
+			host.record_error(record, error)
+		finally:
+			_espeak._execWhenDone(driver._retireSpeech, record, mustBeAsync=True)
+
+	def stop_native(self, host, record):
+		self.stop_player(host)
+
+	def stop_player(self, host):
+		_espeak.isSpeaking = False
+		_espeak.player.stop()
 
 
 class SynthDriver(BaseSynthDriver):
 	"""Add correlated completion without changing NVDA's synthesis queue."""
 
 	def __init__(self):
-		self._segmentCondition = Condition(RLock())
-		self._segmentAdmission = RLock()
-		self._segmentCallbackLocal = local()
-		self._segmentNative = None
-		self._segmentPending = []
-		self._segmentTerminated = False
-		self._segmentControlError = None
-		self._segmentLifecycle = SegmentLifecycle(self)
-		self._segmentOperations = {}
-		self._segmentAccepted = set()
+		self._segmentHost = SegmentHost("eSpeak", _EspeakStrategy(self))
 		super().__init__()
-		_espeak.player = _SegmentPlayer(self, _espeak.player)
+		_espeak.player = LeasedPlayer(self._segmentHost, _espeak.player)
 		_espeak.espeakDLL = _SegmentNative(self, _espeak.espeakDLL)
 
 	def get_segment_drain_support(self, *, nvda_version=None, audio_mode=None):
@@ -182,313 +105,74 @@ class SynthDriver(BaseSynthDriver):
 		context: PlaybackContext,
 		on_event: SegmentEventSink,
 	):
-		with self._segmentAdmission:
-			if self._segmentTerminated:
-				self._segmentLifecycle.reject_new(
-					context,
-					token,
-					on_event,
-					RuntimeError("eSpeak driver has terminated"),
-				)
-				return
-			if self._segmentControlError is not None:
-				self._segmentLifecycle.reject_new(context, token, on_event, self._segmentControlError)
-				return
-
-			def deliver(event):
-				self._deliverSpeech(operation, event)
-
-			operation = self._segmentLifecycle.accept(context, token, deliver)
-			operation._espeak_sink = on_event
-			operation._espeak_cancelled = False
-			with self._segmentCondition:
-				self._segmentAccepted.add(operation)
-		Thread(
-			target=self._runSegment,
-			args=(operation, tuple(commands), deliver),
-			name="WorldVoice eSpeak lifecycle",
-			daemon=True,
-		).start()
-
-	def _runSegment(self, operation, commands, deliver):
-		try:
-			self._segmentLifecycle.run(operation, commands)
-		except Exception as error:
-			self._segmentLifecycle.reject_new(
-				operation.work.context,
-				operation.work.token,
-				deliver,
-				self._segmentControlError or error.__cause__ or error,
-			)
-		finally:
-			with self._segmentCondition:
-				native = self._segmentOperations.pop(operation, None)
-				if operation._espeak_cancelled or operation.work.token.is_cancelled():
-					self._segmentAccepted.discard(operation)
-			if native is not None:
-				native.handoff.set()
-
-	def submit_native(self, operation, commands):
-		self._queueSpeech(commands, operation.work, operation)
-
-	def request_stop(self, operation):
-		with self._segmentCondition:
-			native = self._segmentOperations.get(operation)
-			if native is not None:
-				native.cancelled = True
-				active = native is self._segmentNative
-			else:
-				active = False
-		if active:
-			_espeak.isSpeaking = False
-			_espeak.player.stop()
-
-	def wait_native_boundary(self, operation):
-		with self._segmentCondition:
-			native = self._segmentOperations[operation]
-		native.retired.wait()
-		if native.error is not None:
-			self._segmentLifecycle.fail(operation, native.error)
-
-	def wait_native_retired(self, operation):
-		return
-
-	def wait_playback_drained(self, operation):
-		with self._segmentCondition:
-			native = self._segmentOperations.get(operation)
-		if native is None:
-			return
-		if not operation.work.is_valid() or native.error is not None:
-			_espeak.isSpeaking = False
-			_espeak.player.stop()
-			return
-		if not (native.returned and native.ended and native.idle_completed):
-			self._segmentLifecycle.fail(
-				operation,
-				RuntimeError(
-					"eSpeak synthesis retired without its native return, end and player idle barriers",
-				),
-			)
-			_espeak.isSpeaking = False
-			_espeak.player.stop()
+		self._segmentHost.speak_segment(commands, token, context=context, on_event=on_event)
 
 	def speak(self, speechSequence):
-		self._queueSpeech(speechSequence, None)
+		self._segmentHost.enqueue(speechSequence)
 
-	def _queueSpeech(self, commands, work, operation=None):
-		native = _NativeSpeech(
-			work,
-			operation=operation,
-			retired=Event() if operation is not None else None,
-			handoff=Event() if operation is not None else None,
-		)
-		with self._segmentAdmission:
-			if self._segmentTerminated:
-				if work is not None:
-					work.cancel()
-				return
-			with self._segmentCondition:
-				control_error = self._segmentControlError
-				if control_error is not None and work is None:
-					raise control_error
-				self._segmentPending.append(native)
-				if operation is not None:
-					self._segmentOperations[operation] = native
-					operation._espeak_native = native
-			if control_error is not None:
-				if operation is not None:
-					self._segmentLifecycle.fail(operation, control_error)
-					native.retired.set()
-				else:
-					native.closed = True
-					self._dispatchSpeech(native, control_error)
-				return
-			if operation is not None:
-				native.producer = self._segmentLifecycle.admit_producer(operation)
-			# Begin and retirement remain separate queue entries: NVDA stop()
-			# removes queued _speak calls but preserves both identity barriers.
-			_espeak._execWhenDone(self._beginSpeech, native, mustBeAsync=True)
-			try:
-				super().speak(commands)
-			except Exception as error:
-				self._recordError(native, error)
-			finally:
-				_espeak._execWhenDone(self._retireSpeech, native, mustBeAsync=True)
-
-	def _beginSpeech(self, native):
-		with self._segmentCondition:
-			self._segmentNative = native
+	def _beginSpeech(self, record):
+		self._segmentHost.begin(record)
 		owner_ref = weakref.ref(self)
 
 		def index_callback(index):
 			owner = owner_ref()
 			if owner is not None:
-				owner._indexFor(native, index)
+				owner._indexFor(record, index)
 
 		_espeak.onIndexReached = index_callback
 
-	def _admitConsumer(self, native=None):
-		with self._segmentCondition:
-			native = native or self._segmentNative
-			if native is None or native is not self._segmentNative or not native.is_valid():
-				return None
-			native.consumers += 1
-			return native
-
-	def _releaseConsumer(self, native):
-		with self._segmentCondition:
-			native.consumers -= 1
-			self._segmentCondition.notify_all()
-
-	def _recordError(self, native, error):
-		with self._segmentCondition:
-			if native is not None and native.error is None:
-				native.error = error
-
-	def _recordControlError(self, error):
-		# A stop failure does not prove that queued PCM/index callbacks were
-		# discarded. Retain the first control error until the driver reloads.
-		with self._segmentCondition:
-			if self._segmentControlError is None:
-				self._segmentControlError = error
-			for native in self._segmentPending:
-				if native.error is None:
-					native.error = self._segmentControlError
-
-	def _indexFor(self, native, index):
+	def _indexFor(self, record, index):
 		# NVDA's onDone lambdas resolve its mutable onIndexReached global.
 		# The player lease takes precedence so an old index cannot bind to a
 		# successor even if that global was replaced in the meantime.
-		native = getattr(self._segmentCallbackLocal, "native", None) or native
-		if not self._admitConsumer(native):
-			return
-		try:
+		host = self._segmentHost
+		record = host.callback_record() or record
+		with host.consumer(record) as admitted:
+			if admitted is None:
+				return
 			if index is None:
-				with self._segmentCondition:
-					native.ended = True
+				host.reach(admitted, "ended")
 			else:
 				super()._onIndexReached(index)
-		finally:
-			self._releaseConsumer(native)
 
 	def _onIndexReached(self, index):
-		with self._segmentCondition:
-			native = self._segmentNative
-		if native is not None:
-			self._indexFor(native, index)
+		record = self._segmentHost.current()
+		if record is not None:
+			self._indexFor(record, index)
 
-	def _retireSpeech(self, native):
+	def _retireSpeech(self, record: NativeRecord):
 		# FIFO is the proof that NVDA's _speak and the synchronous native
 		# callback have returned. Never publish while either is on the stack.
-		with self._segmentCondition:
-			valid = native.is_valid()
-			native.closed = True
-			self._segmentCondition.wait_for(lambda: native.consumers == 0)
-			valid = valid and not native.cancelled and (native.work is None or native.work.is_valid())
-			if not valid and native in self._segmentPending:
-				self._segmentPending.remove(native)
-			if self._segmentNative is native:
-				self._segmentNative = None
-		if native.operation is not None:
-			if native.producer is not None:
-				self._segmentLifecycle.retire_producer(native.producer)
-			native.retired.set()
-			# The FIFO worker must retain player ownership until the coordinator
-			# has finished the final stop or drain check for this operation.
-			native.handoff.wait()
+		outcome = self._segmentHost.retire(record)
+		if outcome is None or outcome.cancelled:
 			return
-		if not valid:
+		if outcome.error is not None:
 			_espeak.isSpeaking = False
-			# Token-only cancellation can occur after the last feed and skip
-			# terminal idle admission. Discard that PCM before FIFO handoff.
-			try:
-				_espeak.player.stop()
-			except Exception:
-				# The player proxy latched the error. The cancelled segment stays
-				# silent, and queued work cannot enter native synthesis afterward.
-				log.error("Error stopping cancelled eSpeak playback", exc_info=True)
-			return
-		error = native.error
-		if error is None and not (native.returned and native.ended and native.idle_completed):
-			error = RuntimeError(
-				"eSpeak synthesis retired without its native return, end and player idle barriers",
-			)
-		if error is not None:
-			_espeak.isSpeaking = False
-			if self._segmentControlError is None:
-				try:
-					_espeak.player.stop()
-				except Exception as stop_error:
-					log.error("Error stopping failed eSpeak playback", exc_info=True)
-					self._recordError(native, stop_error)
-		self._dispatchSpeech(native, error)
-
-	def _dispatchSpeech(self, native, error):
 		Thread(
-			target=self._deliverSpeech,
-			args=(native, error),
+			target=self._notifyDone,
+			args=(record,),
 			name="WorldVoice eSpeak completion",
 			daemon=True,
 		).start()
 
-	def _deliverSpeech(self, native, error):
-		event_delivery = isinstance(error, PlaybackEvent)
+	def _notifyDone(self, record):
 		try:
-			if event_delivery:
-				if (
-					not native.work.token.is_cancelled()
-					and not native._espeak_cancelled
-					and not self._segmentTerminated
-				):
-					native._espeak_sink(error)
-				return
-			with self._segmentCondition:
-				error = error or native.error or self._segmentControlError
-			if native.work is not None:
-				if error is not None:
-					native.work.fail(error)
-				else:
-					native.work.complete_drained()
-			elif not native.cancelled and not self._segmentTerminated:
+			if not record.cancelled and not self._segmentHost.terminated:
 				synthDoneSpeaking.notify(synth=self)
 		except Exception:
 			log.error("Error delivering eSpeak completion", exc_info=True)
 		finally:
-			# Keep work cancellable until publication starts on the delivery
-			# thread, including the gap after native FIFO retirement.
-			with self._segmentCondition:
-				if event_delivery:
-					self._segmentAccepted.discard(native)
-					bound = getattr(native, "_espeak_native", None)
-					if bound in self._segmentPending:
-						self._segmentPending.remove(bound)
-				elif native in self._segmentPending:
-					self._segmentPending.remove(native)
-
-	def _invalidateSpeech(self):
-		with self._segmentCondition:
-			for operation in tuple(self._segmentAccepted):
-				operation._espeak_cancelled = True
-				self._segmentLifecycle.cancel(operation)
-			for native in self._segmentPending:
-				native.cancelled = True
-				if native.work is not None and native.operation is None:
-					native.work.cancel()
+			self._segmentHost.forget(record)
 
 	def cancel(self):
-		with self._segmentAdmission:
-			self._invalidateSpeech()
-			if not self._segmentTerminated:
+		with self._segmentHost.admission():
+			self._segmentHost.cancel()
+			if not self._segmentHost.terminated:
 				return super().cancel()
 
 	def terminate(self):
-		with self._segmentAdmission:
-			if self._segmentTerminated:
-				return
-			self._segmentTerminated = True
-			self._invalidateSpeech()
-			self._segmentLifecycle.terminate()
-		return super().terminate()
+		if self._segmentHost.terminate():
+			return super().terminate()
 
 
 class Voice(Voice):
```

Behavior that moved into the host is unchanged: admission, rejection, delivery gating, consumer admission, the control-error latch and FIFO retirement. Two eSpeak specifics stay here:
- `_espeak.isSpeaking = False` when an ordinary record fails.
- The `synthDoneSpeaking` notification on a separate thread.

- [ ] **Step 4: Run the tests and prove the barrier still bites**

Run: `python3 -m pytest tests -q 2>&1 | tail -1`
Expected: `1304 passed, 96 skipped, 2 xfailed`

Run: `for i in 1 2 3; do python3 -m pytest tests/test_espeak_segment_drain.py -q 2>&1 | tail -1; done`
Expected: `27 passed` three times.

Mutation M3 makes eSpeak stop marking the `returned` barrier:
```bash
E=addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py
sed -i 's/^\t\t\thost.reach(record, "returned")$/\t\t\tpass/' $E
python3 -m pytest tests/test_espeak_segment_drain.py -q 2>&1 | tail -1
git checkout -- $E
```
Expected: `13 failed, 14 passed`, then the file is restored.

Run: `ruff format --check addon | tail -1; grep -n "_segmentLifecycle\|SegmentLifecycle" $E`
Expected: `53 files already formatted`; no grep output.

- [ ] **Step 5: Commit**

```bash
git add addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py tests/test_espeak_segment_drain.py \
	tests/engine_contract_harness.py tests/test_runtime_completion_policies.py tests/test_lifecycle_private_access.py
git commit -m "refactor(espeak): run segments through SegmentHost

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Final verification

**Files:** none modified.

- [ ] **Step 1: Stability**

Run: `for i in 1 2 3 4 5; do python3 -m pytest tests/test_espeak_segment_drain.py tests/test_segment_host.py tests/test_engine_segment_contract.py -q 2>&1 | tail -1; done | sed 's/ in .*//' | sort | uniq -c`
Expected: one line, `5 69 passed, 4 skipped, 2 xfailed`.

- [ ] **Step 2: The other five engines are untouched and green**

Run: `git diff master --stat -- addon/synthDrivers/WorldVoice/driver/RHVoice addon/synthDrivers/WorldVoice/driver/SAPI5 addon/synthDrivers/WorldVoice/driver/OneCore addon/synthDrivers/WorldVoice/driver/VE addon/synthDrivers/WorldVoice/driver/Cerence`
Expected: no output.

Run: `python3 -m pytest tests/test_rhvoice_segment_drain.py tests/test_sapi5_segment_drain.py tests/test_onecore_segment_drain.py tests/test_vocalizer_segment_drain.py -q 2>&1 | tail -1`
Expected: `308 passed, 9 skipped`.

Run: `python3 -m pytest tests/test_engine_segment_contract.py -q -rx 2>&1 | grep -E "XFAIL|passed"`
Expected: `XFAIL` lines for `[VE]` and `[Cerence]` only, then `22 passed, 4 skipped, 2 xfailed`.

- [ ] **Step 3: Full suite and protected paths**

Run: `python3 -m pytest tests -q 2>&1 | tail -1`
Expected: `1304 passed, 96 skipped, 2 xfailed`

Run:
```bash
ruff format --check addon | tail -1
git diff master --stat -- 'addon/synthDrivers/WorldVoice/driver/*/driver'
git ls-files addon/synthDrivers/WorldVoice/driver/Neural
git log --oneline master..HEAD
```
Expected:
- `53 files already formatted`, then no output from the two path checks.
- The log lists, oldest at the bottom:
  1. `docs: add phase 3a SegmentHost core and eSpeak migration design spec`
  2. `docs: add phase 3a implementation plan`
  3. `fix(runtime): wake on terminal events, require notifying tokens, exact callback removal`
  4. `feat(runtime): SegmentHost, NativeRecord, NativeStrategy and LeasedPlayer`
  5. `refactor(espeak): run segments through SegmentHost`
