# Phase 2: Lifecycle Public API and Event-Driven Cancellation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Engine wrappers stop touching `SegmentOperation`/`SegmentLifecycle` private state, and every 50 ms cancellation poll is replaced by a notification.

**Architecture:**
- `CancellationView` gains `add_callback`; `CancellationToken` implements it.
- `PlaybackWork` gains an `on_cancel` hook, which the lifecycle wires to `wake_waiters`. Direct `work.cancel()` calls in any wrapper, Neural included, therefore wake waiters without wrapper changes.
- The lifecycle exposes read-only operation queries plus `on_delivery_thread`, `join_delivery`, `is_resource_busy`, `wait_idle` and `wake_waiters`.
- Wrappers and the phase 1 contract harness move to that API, and a guard test keeps them there.
- Internal flags and the `run()` state machine stay as they are.

**Tech Stack:** Python 3 threading (`Condition`, `Event`, `Lock`), pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-10-01-phase2-lifecycle-public-api-design.md`

## Global Constraints

- Work on branch `phase2-lifecycle-api`, cut from `master` at `dfe01e6`.
- New public names are snake_case. Do not rename existing names.
- Do not add `__slots__` to `SegmentOperation`; wrapper-attached attributes (`_ve_*`, `_onecore_*`, `_rhvoice_*`, `_espeak_*`, `_neural_*`) stay.
- Do not touch `addon/synthDrivers/WorldVoice/driver/<Engine>/driver/` and never add `driver/Neural/` to a commit.
- Token callbacks only notify (set an Event or `notify_all`); the scheduler cancels while holding its state lock.
- Every changed `addon/` file must pass `ruff format --check`. New test files must pass `ruff check`.
- Run from `/workspace/WorldVoice` (tests need the untracked `ref/`). Stage explicit paths only; the user's unstaged deletion of `docs/superpowers/finish_task.md` must never be staged.
- Baseline before Task 1, without Neural: `python3 -m pytest tests -q` → `1255 passed, 96 skipped, 2 xfailed`.
- Each code step applies a patch saved verbatim from this plan. Save the block to the named file under `$PATCHES`, then `git apply` it. Create the directory once: `PATCHES=$(mktemp -d)`; if the shell is new, set it again and re-save any patch you still need.
- Every commit message ends with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A wrapper cancels a queued segment through `PlaybackWork.cancel()` (not the token) while another segment owns the resource → the queued `run()` must wake and discard promptly, not wait for the owner to finish (Task 2, `test_queued_run_wakes_when_cancelled[work]`, proven by mutation M2a).
2. `cancel()` runs while the scheduler holds its state lock, and the callback takes the lifecycle condition → no deadlock and no lock inversion; callbacks run outside the token lock (Task 1, `test_cancellation_callback_runs_outside_the_token_lock`; Task 2, `on_cancel` outside the work lock, mutation M2c).
3. VE/Cerence ordinary speech is waiting behind a contextual segment when `VE.cancel()` or a token cancel arrives → it must stop waiting without polling (Task 3, `test_ordinary_waiting_behind_contextual_does_not_poll` plus the existing `test_cancel_during_contextual_final_idle_releases_waiting_ordinary`).
4. A delivery sink calls back into the lifecycle (`join_delivery`, `on_delivery_thread`) → no self-join deadlock (Task 2, `test_delivery_thread_identity_and_join`).
5. Neural, restored locally and unmodified, cancels work directly → it still passes all its tests (Task 5, Neural worktree run).

---

### Task 1: `CancellationToken.add_callback` and the `CancellationView` contract

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/runtime/scheduler.py` (`CancellationToken`, new module `log`)
- Modify: `addon/synthDrivers/WorldVoice/runtime/session.py` (`CancellationView`)
- Modify: `tests/test_worldvoice_cancel_wrappers.py` (`Token`), `tests/test_runtime_session.py` (`EventToken`)
- Test: `tests/test_runtime_scheduler.py`

**Interfaces:**
- Produces `CancellationToken.add_callback(callback: Callable[[], None]) -> Callable[[], None]` with these semantics:
  - It returns a remover; calling the remover more than once is harmless.
  - The callback runs immediately if the token is already cancelled.
  - Otherwise it runs once at the first `cancel()`, in registration order, outside the token lock.
  - Exceptions are logged with `log.exception("cancellation callback failed")` and swallowed.
- Produces the `CancellationView.add_callback` protocol member, which Tasks 2–4 rely on.

- [ ] **Step 1: Write the failing tests**

Save as `$PATCHES/t1-tests.patch`, then run `git apply $PATCHES/t1-tests.patch`:

```diff
diff --git a/tests/test_runtime_scheduler.py b/tests/test_runtime_scheduler.py
index 21fc462..665d7ea 100644
--- a/tests/test_runtime_scheduler.py
+++ b/tests/test_runtime_scheduler.py
@@ -726,3 +726,65 @@ def test_then_public_cancel_racing_settlement_has_no_callback_error(
             inner.set_result(42)
     assert following.cancelled()
     assert not caplog.records
+
+
+def test_cancellation_token_callbacks_run_once_in_registration_order(scheduler):
+    token = scheduler.CancellationToken()
+    calls = []
+    token.add_callback(lambda: calls.append("first"))
+    token.add_callback(lambda: calls.append("second"))
+    assert calls == []
+    token.cancel()
+    token.cancel()
+    assert calls == ["first", "second"]
+
+
+def test_cancellation_token_callback_on_cancelled_token_runs_immediately(scheduler):
+    token = scheduler.CancellationToken()
+    token.cancel()
+    calls = []
+    remove = token.add_callback(lambda: calls.append("late"))
+    assert calls == ["late"]
+    remove()
+    remove()
+
+
+def test_removed_cancellation_callback_is_not_called(scheduler):
+    token = scheduler.CancellationToken()
+    calls = []
+    remove = token.add_callback(lambda: calls.append("removed"))
+    token.add_callback(lambda: calls.append("kept"))
+    remove()
+    remove()
+    token.cancel()
+    assert calls == ["kept"]
+
+
+def test_cancellation_callback_error_is_logged_and_others_still_run(scheduler, caplog):
+    token = scheduler.CancellationToken()
+    calls = []
+
+    def broken():
+        raise RuntimeError("callback failed")
+
+    token.add_callback(broken)
+    token.add_callback(lambda: calls.append("after"))
+    token.cancel()
+    assert calls == ["after"]
+    assert token.is_cancelled()
+    assert any("callback failed" in str(record.exc_info[1]) for record in caplog.records if record.exc_info)
+
+
+def test_cancellation_callback_runs_outside_the_token_lock(scheduler):
+    token = scheduler.CancellationToken()
+    seen = []
+
+    def reentrant():
+        seen.append(token.is_cancelled())
+        token.add_callback(lambda: seen.append("nested"))
+
+    token.add_callback(reentrant)
+    finished = Event()
+    Thread(target=lambda: (token.cancel(), finished.set()), daemon=True).start()
+    assert finished.wait(1), "cancel() deadlocked inside a callback"
+    assert seen == [True, "nested"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_runtime_scheduler.py -q -k 'cancellation_token or cancellation_callback or removed_cancellation'`
Expected: `5 failed, 45 deselected`. Each failure is `AttributeError: 'CancellationToken' object has no attribute 'add_callback'`.

- [ ] **Step 3: Implement**

Save as `$PATCHES/t1-impl.patch`, then run `git apply $PATCHES/t1-impl.patch`:

```diff
diff --git a/addon/synthDrivers/WorldVoice/runtime/scheduler.py b/addon/synthDrivers/WorldVoice/runtime/scheduler.py
index 8994abf..eec3563 100644
--- a/addon/synthDrivers/WorldVoice/runtime/scheduler.py
+++ b/addon/synthDrivers/WorldVoice/runtime/scheduler.py
@@ -34,16 +34,57 @@ class NotificationOutput(Protocol):
 	def done_speaking(self) -> None: ...
 
 
+log = logging.getLogger(__name__)
+
+
 class CancellationToken:
+	"""Cancellation flag that notifies waiters instead of being polled.
+
+	Callbacks run once, in registration order, on the thread that first calls
+	cancel(), outside the token lock. They must only notify (set an Event,
+	notify a condition): the scheduler cancels while holding its state lock.
+	"""
+
 	def __init__(self):
 		self._event = threading.Event()
+		self._lock = threading.Lock()
+		self._callbacks: dict[int, Callable[[], None]] = {}
+		self._next_callback = count()
 
 	def cancel(self):
-		self._event.set()
+		with self._lock:
+			if self._event.is_set():
+				return
+			self._event.set()
+			callbacks, self._callbacks = list(self._callbacks.values()), {}
+		for callback in callbacks:
+			self._run_callback(callback)
 
 	def is_cancelled(self):
 		return self._event.is_set()
 
+	def add_callback(self, callback: Callable[[], None]) -> Callable[[], None]:
+		"""Call ``callback`` once on cancellation; return a function that removes it."""
+		with self._lock:
+			if not self._event.is_set():
+				key = next(self._next_callback)
+				self._callbacks[key] = callback
+
+				def remove():
+					with self._lock:
+						self._callbacks.pop(key, None)
+
+				return remove
+		self._run_callback(callback)
+		return lambda: None
+
+	@staticmethod
+	def _run_callback(callback):
+		try:
+			callback()
+		except Exception:
+			log.exception("cancellation callback failed")
+
 	def wait(self, timeout=None):
 		return self._event.wait(timeout)
 
diff --git a/addon/synthDrivers/WorldVoice/runtime/session.py b/addon/synthDrivers/WorldVoice/runtime/session.py
index 88aac75..4a498f0 100644
--- a/addon/synthDrivers/WorldVoice/runtime/session.py
+++ b/addon/synthDrivers/WorldVoice/runtime/session.py
@@ -1,6 +1,6 @@
 """Engine ownership and playback contracts independent of legacy drivers."""
 
-from collections.abc import Mapping
+from collections.abc import Callable, Mapping
 from threading import RLock
 from typing import Protocol
 
@@ -18,8 +18,17 @@ from .settings import VoiceSettingsStore
 
 
 class CancellationView(Protocol):
+	"""Read-only cancellation state with change notification.
+
+	add_callback(callback) calls ``callback`` once when the token is cancelled,
+	immediately if it already is, and returns a function that removes it.
+	Callbacks run outside the token's lock and must only notify.
+	"""
+
 	def is_cancelled(self) -> bool: ...
 
+	def add_callback(self, callback: Callable[[], None]) -> Callable[[], None]: ...
+
 
 class EngineAdapter(Protocol):
 	notification_source: object
diff --git a/tests/test_runtime_session.py b/tests/test_runtime_session.py
index e9e7745..ff96d90 100644
--- a/tests/test_runtime_session.py
+++ b/tests/test_runtime_session.py
@@ -214,6 +214,12 @@ class EventToken:
     def is_cancelled(self):
         return self.cancelled.is_set()
 
+    def add_callback(self, callback):
+        # Tests set ``cancelled`` directly; no waiter in these tests subscribes.
+        if self.cancelled.is_set():
+            callback()
+        return lambda: None
+
 
 @pytest.mark.parametrize("mode", ["LEGACY_DONE", "DRAIN"])
 def test_cached_activation_still_speaks_two_distinct_segments(rt, session, adapter, store, mode):
diff --git a/tests/test_worldvoice_cancel_wrappers.py b/tests/test_worldvoice_cancel_wrappers.py
index 8e104a4..ede4ec8 100644
--- a/tests/test_worldvoice_cancel_wrappers.py
+++ b/tests/test_worldvoice_cancel_wrappers.py
@@ -30,13 +30,26 @@ def ready_core(engine_harness):
 class Token:
 	def __init__(self):
 		self._cancelled = False
+		self._callbacks = []
 
 	def cancel(self):
+		if self._cancelled:
+			return
 		self._cancelled = True
+		callbacks, self._callbacks = self._callbacks, []
+		for callback in callbacks:
+			callback()
 
 	def is_cancelled(self):
 		return self._cancelled
 
+	def add_callback(self, callback):
+		if self._cancelled:
+			callback()
+			return lambda: None
+		self._callbacks.append(callback)
+		return lambda: callback in self._callbacks and self._callbacks.remove(callback)
+
 
 def emit_audio(core, types, payload=b"new", done_result=None):
 	callback = core._veCallbackHandler
```

The two test tokens get the same `add_callback` so that later waits can subscribe to them. `EventToken`'s tests set `cancelled` directly and never wait on it, so a minimal stub suffices.

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/test_runtime_scheduler.py -q -k 'cancellation_token or cancellation_callback or removed_cancellation'`
Expected: `5 passed, 45 deselected`

Run: `python3 -m pytest tests -q 2>&1 | tail -1`
Expected: `1260 passed, 96 skipped, 2 xfailed`

Run: `ruff format --check addon/synthDrivers/WorldVoice/runtime/scheduler.py addon/synthDrivers/WorldVoice/runtime/session.py`
Expected: `2 files already formatted`

- [ ] **Step 5: Commit**

```bash
git add addon/synthDrivers/WorldVoice/runtime/scheduler.py addon/synthDrivers/WorldVoice/runtime/session.py \
	tests/test_runtime_scheduler.py tests/test_worldvoice_cancel_wrappers.py tests/test_runtime_session.py
git commit -m "feat(runtime): notify cancellation callbacks instead of being polled

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Lifecycle public API and event-driven `run()` wait

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/runtime/playbackWork.py` (`PlaybackWork.__init__` keyword `on_cancel`, `cancel()`)
- Modify: `addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py`: module docstring (lock order), `SegmentOperation.sink`/`has_started`/`is_retired`, the `accept`/`reject_new` work construction, the `run()` wait, and the new methods `on_delivery_thread`/`join_delivery`/`is_resource_busy`/`wait_idle`/`wake_waiters`
- Test: `tests/test_segment_lifecycle.py`, `tests/test_playback_work.py`

**Interfaces:**
- Consumes `CancellationView.add_callback` from Task 1.
- Produces, used by Tasks 3–4:
  - `SegmentOperation.sink` (property), `has_started() -> bool`, `is_retired() -> bool`.
  - `SegmentLifecycle.on_delivery_thread() -> bool`, `join_delivery(timeout: float | None = None) -> None`, `is_resource_busy() -> bool`, `wait_idle(*, still_wanted: Callable[[], bool] = lambda: True, token: CancellationView | None = None) -> bool`, `wake_waiters() -> None`.
  - `PlaybackWork(context, token, on_event, *, on_cancel=None)`.

- [ ] **Step 1: Write the failing tests**

Save as `$PATCHES/t2-tests.patch`, then run `git apply $PATCHES/t2-tests.patch`:

```diff
diff --git a/tests/test_playback_work.py b/tests/test_playback_work.py
index 510f99b..77c35a3 100644
--- a/tests/test_playback_work.py
+++ b/tests/test_playback_work.py
@@ -331,3 +331,15 @@ def test_cancelled_admitted_feed_stops_before_new_native_work(work_env):
     assert actions == ["stop old playback", "old real feed", "stop old playback", "new native started"]
     assert work.complete_drained() is False
     assert events == []
+
+
+def test_direct_cancel_notifies_owner_after_releasing_the_work_lock(work_env):
+    rt, token, context, events, _ = work_env
+    seen = []
+    work = rt.playback_work.PlaybackWork(context, token, events.append,
+                                         on_cancel=lambda: seen.append(work.is_valid()))
+    finished = Event()
+    Thread(target=lambda: (work.cancel(), finished.set()), daemon=True).start()
+    assert finished.wait(1), "on_cancel ran while the work lock was held"
+    assert seen == [False]
+    assert events == []
diff --git a/tests/test_segment_lifecycle.py b/tests/test_segment_lifecycle.py
index 021975d..d8f322a 100644
--- a/tests/test_segment_lifecycle.py
+++ b/tests/test_segment_lifecycle.py
@@ -669,3 +669,171 @@ def test_terminate_cancels_previously_accepted_pending_rejection(env):
         assert lifecycle._condition.wait_for(lambda: second not in lifecycle._operations, 1)
     assert rejected == []
     assert hooks.submitted == []
+
+
+
+def _hold_resource(env):
+    lifecycle, hooks, events, accept = env
+    owner, _ = accept(1)
+    call = Call(lambda: lifecycle.run(owner, ("owner",)))
+    assert hooks.boundary_entered.wait(1)
+    return owner, call
+
+
+class CountingToken:
+    """A real CancellationToken that counts how often waiters poll it."""
+
+    def __init__(self, inner):
+        self._inner = inner
+        self.checks = 0
+
+    def is_cancelled(self):
+        self.checks += 1
+        return self._inner.is_cancelled()
+
+    def add_callback(self, callback):
+        return self._inner.add_callback(callback)
+
+    def cancel(self):
+        self._inner.cancel()
+
+
+def _accept_counting(env, owner, segment):
+    lifecycle, hooks, events, accept = env
+    token = CountingToken(type(owner.work.token)())
+    context = type(owner.work.context)(object(), segment)
+    return lifecycle.accept(context, token, events.append), token
+
+
+def _assert_not_polled(read_count, window=0.2):
+    # A 50 ms poll would re-check about four times in this window.
+    before = read_count()
+    Event().wait(window)
+    assert read_count() - before <= 1, "waiter is polling instead of waiting for a notification"
+
+
+def test_queued_run_does_not_poll_its_token(env):
+    lifecycle, hooks, events, accept = env
+    owner, owner_call = _hold_resource(env)
+    queued, token = _accept_counting(env, owner, 2)
+    waiting = Call(lambda: lifecycle.run(queued, ("queued",)))
+    waiting.blocked()
+    _assert_not_polled(lambda: token.checks)
+    token.cancel()
+    waiting.finish()
+    hooks.release_boundary.set()
+    owner_call.finish()
+
+
+@pytest.mark.parametrize("cancel", ["token", "work"])
+def test_queued_run_wakes_when_cancelled(env, cancel):
+    lifecycle, hooks, events, accept = env
+    _, owner_call = _hold_resource(env)
+    queued, _ = accept(2)
+    waiting = Call(lambda: lifecycle.run(queued, ("queued",)))
+    waiting.blocked()
+    if cancel == "token":
+        queued.work.token.cancel()
+    else:
+        queued.work.cancel()
+    assert waiting.done.wait(0.5), "queued run was not woken by cancellation"
+    waiting.finish()
+    assert len(hooks.submitted) == 1
+    hooks.release_boundary.set()
+    owner_call.finish()
+
+
+def test_operation_queries_follow_run_and_retirement(env):
+    lifecycle, hooks, events, accept = env
+    sink = events.append
+    operation, _ = accept(1, sink=sink)
+    assert operation.sink is sink
+    assert not operation.has_started()
+    assert not operation.is_retired()
+    call = Call(lambda: lifecycle.run(operation, ("hello",)))
+    assert hooks.boundary_entered.wait(1)
+    assert operation.has_started()
+    assert not operation.is_retired()
+    hooks.release_boundary.set()
+    call.finish()
+    assert operation.is_retired()
+
+
+def test_rejected_operation_reports_started_and_retired(env):
+    lifecycle, hooks, events, accept = env
+    operation, _ = accept(1)
+    lifecycle.reject_pending(operation, RuntimeError("rejected"))
+    assert operation.has_started()
+    assert operation.is_retired()
+
+
+def test_delivery_thread_identity_and_join(env):
+    lifecycle, hooks, events, accept = env
+    seen, joined = [], Event()
+
+    def sink(event):
+        seen.append(lifecycle.on_delivery_thread())
+        lifecycle.join_delivery(1)  # Must not try to join itself.
+        joined.set()
+
+    operation, _ = accept(1, sink=sink)
+    hooks.release_boundary.set()
+    Call(lambda: lifecycle.run(operation, ("hello",))).finish()
+    assert joined.wait(1)
+    assert seen == [True]
+    assert not lifecycle.on_delivery_thread()
+    lifecycle.terminate()
+    lifecycle.join_delivery(1)
+    assert not lifecycle._delivery_thread.is_alive()
+
+
+def test_wait_idle_returns_true_when_resource_is_released(env):
+    lifecycle, hooks, events, accept = env
+    assert lifecycle.wait_idle() is True
+    _, owner_call = _hold_resource(env)
+    assert lifecycle.is_resource_busy()
+    results = []
+    waiting = Call(lambda: results.append(lifecycle.wait_idle()))
+    waiting.blocked()
+    hooks.release_boundary.set()
+    owner_call.finish()
+    waiting.finish()
+    assert results == [True]
+    assert not lifecycle.is_resource_busy()
+
+
+def test_wait_idle_wakes_on_token_cancel_without_polling(env):
+    lifecycle, hooks, events, accept = env
+    owner, owner_call = _hold_resource(env)
+    token = CountingToken(type(owner.work.token)())
+    results = []
+    waiting = Call(lambda: results.append(lifecycle.wait_idle(token=token, still_wanted=lambda: not token.is_cancelled())))
+    waiting.blocked()
+    _assert_not_polled(lambda: token.checks)
+    token.cancel()
+    assert waiting.done.wait(0.5), "wait_idle was not woken by token cancellation"
+    waiting.finish()
+    assert results == [False]
+    hooks.release_boundary.set()
+    owner_call.finish()
+
+
+def test_wait_idle_rechecks_still_wanted_on_wake_waiters(env):
+    lifecycle, hooks, events, accept = env
+    _, owner_call = _hold_resource(env)
+    wanted, checks, results = [True], [0], []
+
+    def still_wanted():
+        checks[0] += 1
+        return wanted[0]
+
+    waiting = Call(lambda: results.append(lifecycle.wait_idle(still_wanted=still_wanted)))
+    waiting.blocked()
+    _assert_not_polled(lambda: checks[0])
+    wanted[0] = False
+    lifecycle.wake_waiters()
+    assert waiting.done.wait(0.5), "wait_idle was not woken by wake_waiters"
+    waiting.finish()
+    assert results == [False]
+    hooks.release_boundary.set()
+    owner_call.finish()
```

`CountingToken` and `_assert_not_polled` detect polling deterministically. A 50 ms poll re-reads the token about four times in a 200 ms window; a notified wait reads it at most once.

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_segment_lifecycle.py tests/test_playback_work.py -q`
Expected: `8 failed, 43 passed`.
- These 8 fail:
  - `test_queued_run_does_not_poll_its_token`, with `waiter is polling instead of waiting for a notification`.
  - The six query and `wait_idle` tests, with `AttributeError`.
  - `test_direct_cancel_notifies_owner_after_releasing_the_work_lock`, with `TypeError ... on_cancel`.
- The two `test_queued_run_wakes_when_cancelled[...]` cases pass today only because of the poll. Step 6 proves they guard the new mechanism.

- [ ] **Step 3: Implement**

Save as `$PATCHES/t2-impl.patch`, then run `git apply $PATCHES/t2-impl.patch`:

```diff
diff --git a/addon/synthDrivers/WorldVoice/runtime/playbackWork.py b/addon/synthDrivers/WorldVoice/runtime/playbackWork.py
index 43b8483..681465b 100644
--- a/addon/synthDrivers/WorldVoice/runtime/playbackWork.py
+++ b/addon/synthDrivers/WorldVoice/runtime/playbackWork.py
@@ -6,6 +6,7 @@ admit -> feed outside locks -> stop if invalid -> release. The next native call
 cannot take over that player's resources until native finish and every release.
 """
 
+from collections.abc import Callable
 from dataclasses import dataclass
 from threading import Condition, Lock
 
@@ -43,10 +44,13 @@ class PlaybackWork:
 		context: PlaybackContext,
 		token: CancellationView,
 		on_event: SegmentEventSink,
+		*,
+		on_cancel: Callable[[], None] | None = None,
 	):
 		self._context = context
 		self._token = token
 		self._on_event = on_event
+		self._on_cancel = on_cancel
 		self._lock = Lock()
 		self._active = True
 		self._error = None
@@ -69,9 +73,14 @@ class PlaybackWork:
 			return self._active and not self._token.is_cancelled()
 
 	def cancel(self) -> None:
-		"""Invalidate this work without mutating the caller's token or notifying."""
+		"""Invalidate this work without mutating the caller's token or notifying its sink.
+
+		``on_cancel`` (the owner's wake-up) runs after the work lock is released.
+		"""
 		with self._lock:
 			self._active = False
+		if self._on_cancel is not None:
+			self._on_cancel()
 
 	def fail(self, error: Exception) -> bool:
 		return self._terminate(EventKind.SEGMENT_FAILED, error)
diff --git a/addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py b/addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py
index 03fdf3f..1cfb6ac 100644
--- a/addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py
+++ b/addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py
@@ -2,11 +2,25 @@
 
 Engine hooks establish native and playback boundaries. This coordinator never
 infers native quiescence from an empty callback count alone.
+
+Lock order:
+
+1. A wrapper lock may be held while taking the lifecycle condition; wrappers
+   always lock in that order.
+2. A token's cancellation callback may take the lifecycle condition while the
+   scheduler holds its state condition (scheduler -> callback -> lifecycle).
+3. While holding its condition the lifecycle never calls hooks, sinks or token
+   callbacks, and never takes a wrapper or scheduler lock. ``wait_idle`` is the
+   one exception: it calls the caller's ``still_wanted`` predicate, which must
+   only read state under its own leaf lock.
+
+Waits are woken by notifications (resource release, cancel(), token
+callbacks, PlaybackWork.cancel(), wake_waiters()), never by polling.
 """
 
 from collections import deque
 import logging
-from threading import Condition, Event, Thread
+from threading import Condition, Event, Thread, current_thread
 from typing import Callable, Protocol
 
 from .models import PlaybackContext, PlaybackEvent, SegmentEventSink, SpeechCommands
@@ -58,6 +72,21 @@ class SegmentOperation:
 			failed = self._error is not None
 		return not failed and self.work.is_valid()
 
+	@property
+	def sink(self) -> SegmentEventSink:
+		"""The sink this operation was accepted with."""
+		return self._sink
+
+	def has_started(self) -> bool:
+		"""True once run() began or the operation was rejected before running."""
+		with self._lifecycle._condition:
+			return self._run_started
+
+	def is_retired(self) -> bool:
+		"""True once the operation released the native/player resource."""
+		with self._lifecycle._condition:
+			return self._retired
+
 
 class ProducerLease:
 	"""A producer's original operation, retained until its actual work exits."""
@@ -104,7 +133,7 @@ class SegmentLifecycle:
 			# event while the coordinator arbitrates fail/cancel vs success;
 			# the external sink runs later, outside that lock.
 			holder = []
-			work = PlaybackWork(context, token, holder.append)
+			work = PlaybackWork(context, token, holder.append, on_cancel=self.wake_waiters)
 			operation = SegmentOperation(self, work, sink, holder, on_retired)
 			self._operations.add(operation)
 			return operation
@@ -119,7 +148,7 @@ class SegmentLifecycle:
 		"""Deliver a rejected request through the coordinator, even after close."""
 		with self._condition:
 			holder = []
-			work = PlaybackWork(context, token, holder.append)
+			work = PlaybackWork(context, token, holder.append, on_cancel=self.wake_waiters)
 			operation = SegmentOperation(self, work, sink, holder)
 			self._operations.add(operation)
 			operation._pre_admission_rejected = True
@@ -159,6 +188,51 @@ class SegmentLifecycle:
 		else:
 			self._condition.notify_all()
 
+	def on_delivery_thread(self) -> bool:
+		"""True when called from this lifecycle's delivery thread (sinks run there)."""
+		with self._condition:
+			return current_thread() is self._delivery_thread
+
+	def join_delivery(self, timeout: float | None = None) -> None:
+		"""Join the delivery thread; a no-op when called from that thread."""
+		with self._condition:
+			thread = self._delivery_thread
+		if thread is not current_thread():
+			thread.join(timeout)
+
+	def is_resource_busy(self) -> bool:
+		with self._condition:
+			return self._resource_busy
+
+	def wait_idle(
+		self,
+		*,
+		still_wanted: Callable[[], bool] = lambda: True,
+		token: CancellationView | None = None,
+	) -> bool:
+		"""Wait until no operation owns the resource.
+
+		Return True when idle, or False as soon as ``still_wanted()`` is false.
+		Wakes on resource release, ``token`` cancellation and wake_waiters().
+		"""
+		remove_wake = token.add_callback(self.wake_waiters) if token is not None else None
+		try:
+			with self._condition:
+				while True:
+					if not still_wanted():
+						return False
+					if not self._resource_busy:
+						return True
+					self._condition.wait()
+		finally:
+			if remove_wake is not None:
+				remove_wake()
+
+	def wake_waiters(self) -> None:
+		"""Make waiters re-check their conditions after an outside state change."""
+		with self._condition:
+			self._condition.notify_all()
+
 	def _wake_delivery_locked(self) -> None:
 		if not self._delivery_active:
 			self._delivery_active = True
@@ -172,16 +246,24 @@ class SegmentLifecycle:
 
 	def run(self, operation: SegmentOperation, commands: SpeechCommands) -> None:
 		self._require_operation(operation)
+		remove_wake = None
 		with self._condition:
 			if operation._run_started:
 				raise RuntimeError("segment operation was already run")
 			operation._run_started = True
-			while self._resource_busy and not self._terminated and self._fault is None:
-				if not operation.work.is_valid():
-					self._discard_operation_locked(operation)
-					return
-				# An external token can cancel without calling cancel().
-				self._condition.wait(0.05)
+			try:
+				while self._resource_busy and not self._terminated and self._fault is None:
+					if not operation.work.is_valid():
+						self._discard_operation_locked(operation)
+						return
+					if remove_wake is None:
+						# An external token can cancel without calling cancel().
+						remove_wake = operation.work.token.add_callback(self.wake_waiters)
+						continue
+					self._condition.wait()
+			finally:
+				if remove_wake is not None:
+					remove_wake()
 			if self._fault is not None:
 				# This accepted operation never acquired the resource. Retain
 				# its original context for asynchronous correlated failure.
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/test_segment_lifecycle.py tests/test_playback_work.py -q`
Expected: `51 passed`

Run: `python3 -m pytest tests -q 2>&1 | tail -1`
Expected: `1270 passed, 96 skipped, 2 xfailed`

Run: `grep -n "wait(0.05)" addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py; ruff format --check addon/synthDrivers/WorldVoice/runtime`
Expected: no grep output, then `8 files already formatted`.

- [ ] **Step 5: Commit**

```bash
git add addon/synthDrivers/WorldVoice/runtime/playbackWork.py addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py \
	tests/test_segment_lifecycle.py tests/test_playback_work.py
git commit -m "feat(runtime): public lifecycle queries and notification-driven waits

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Prove the wake tests bite (mutations M2a–M2c)**

Run each mutation, check it, then restore with `git checkout`:

```bash
L=addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py
P=addon/synthDrivers/WorldVoice/runtime/playbackWork.py

# M2a: PlaybackWork.cancel() no longer wakes the lifecycle.
sed -i 's/holder.append, on_cancel=self.wake_waiters)/holder.append)/' $L
python3 -m pytest tests/test_segment_lifecycle.py -q -k wakes_when 2>&1 | grep -E "^FAILED|passed|failed" | sed 's/ - .*//'
git checkout -- $L

# M2b: run() stops subscribing to the token.
sed -i 's/remove_wake = operation.work.token.add_callback(self.wake_waiters)/remove_wake = lambda: None/' $L
python3 -m pytest tests/test_segment_lifecycle.py -q -k wakes_when 2>&1 | grep -E "^FAILED|passed|failed" | sed 's/ - .*//'
git checkout -- $L

# M2c: on_cancel runs while the work lock is held.
python3 - <<'PY'
p = "addon/synthDrivers/WorldVoice/runtime/playbackWork.py"
s = open(p).read()
old = """		with self._lock:
			self._active = False
		if self._on_cancel is not None:
			self._on_cancel()
"""
assert s.count(old) == 1
open(p, "w").write(s.replace(old, """		with self._lock:
			self._active = False
			if self._on_cancel is not None:
				self._on_cancel()
"""))
PY
python3 -m pytest tests/test_playback_work.py -q -k notifies_owner 2>&1 | tail -1
git checkout -- $P
git status --short | grep addon
```

Expected:
- M2a: only `test_queued_run_wakes_when_cancelled[work]` FAILED, `1 failed, 1 passed, 29 deselected`.
- M2b: only `test_queued_run_wakes_when_cancelled[token]` FAILED, `1 failed, 1 passed, 29 deselected`.
- M2c: `1 failed, 19 deselected`.
- The final `git status` prints nothing.

---

### Task 3: Wrappers use the public API; guard against private access

**Files:**
- Create: `tests/test_lifecycle_private_access.py`
- Modify: `addon/synthDrivers/WorldVoice/driver/VE/__init__.py` and `addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py`, identical changes in each:
  - `speak_segment` uses `is_retired()`.
  - `_wait_segment_delivery` subscribes `completion.set` to the token.
  - The ordinary-speech wait uses `wait_idle()`/`is_resource_busy()`.
  - `cancel()` calls `wake_waiters()` after its `_speechStateLock` block.
  - The terminate cleanup uses `wait_idle()`.
- Modify: `addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py`: five `has_started()` calls, `join_delivery(1)` in `terminate`, and the now-unused `current_thread` import removed.
- Modify: `addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py` (`_run_segment` uses `operation.sink`)
- Test: `tests/test_vocalizer_segment_drain.py` (append two no-poll tests, each parametrized over VE and Cerence)

**Interfaces:**
- Consumes the Task 2 API.
- Produces the guard `tests/test_lifecycle_private_access.py::_private_accesses(text) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

Save as `$PATCHES/t3-tests.patch`, then run `git apply $PATCHES/t3-tests.patch`:

```diff
diff --git a/tests/test_lifecycle_private_access.py b/tests/test_lifecycle_private_access.py
new file mode 100644
index 0000000..23b5252
--- /dev/null
+++ b/tests/test_lifecycle_private_access.py
@@ -0,0 +1,30 @@
+"""Engine wrappers use the lifecycle's public API, never its private state."""
+
+import re
+from pathlib import Path
+
+DRIVERS = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice/driver"
+PRIVATE_ACCESS = re.compile(r"\b(operation|lifecycle|_segmentLifecycle)\._(\w+)")
+# Per-operation data each wrapper attaches itself; SegmentHost replaces it in phase 3.
+WRAPPER_PREFIXES = ("ve_", "onecore_", "rhvoice_", "espeak_", "neural_")
+
+
+def _private_accesses(text):
+	return [
+		match.group(0)
+		for match in PRIVATE_ACCESS.finditer(text)
+		if not match.group(2).startswith(WRAPPER_PREFIXES)
+	]
+
+
+def test_guard_pattern_separates_lifecycle_state_from_wrapper_data():
+	sample = "operation._run_started; operation._ve_work; self._segmentLifecycle._condition; self._segmentCondition"
+	assert _private_accesses(sample) == ["operation._run_started", "_segmentLifecycle._condition"]
+
+
+def test_wrappers_do_not_touch_lifecycle_private_state():
+	found = []
+	for wrapper in sorted(DRIVERS.glob("*/__init__.py")):
+		for number, line in enumerate(wrapper.read_text(encoding="utf-8").splitlines(), 1):
+			found.extend(f"{wrapper.parent.name}:{number}: {access}" for access in _private_accesses(line))
+	assert found == []
diff --git a/tests/test_vocalizer_segment_drain.py b/tests/test_vocalizer_segment_drain.py
index 983b865..d36cc50 100644
--- a/tests/test_vocalizer_segment_drain.py
+++ b/tests/test_vocalizer_segment_drain.py
@@ -1447,3 +1447,57 @@ def test_reentrant_terminate_from_player_close_does_not_wait_for_itself(env, mon
         if not call[1].is_set():
             env.core._terminationDone.set()
             call[0].join(1)
+
+
+class CountingToken(Token):
+    """The test Token, counting how often waiters poll it."""
+
+    def __init__(self):
+        super().__init__()
+        self.checks = 0
+
+    def is_cancelled(self):
+        self.checks += 1
+        return super().is_cancelled()
+
+
+def assert_not_polled(read_count, window=0.2):
+    # A 50 ms poll would re-check about four times in this window.
+    before = read_count()
+    Event().wait(window)
+    assert read_count() - before <= 1, "waiter is polling instead of waiting for a notification"
+
+
+def test_ordinary_waiting_behind_contextual_does_not_poll(env, monkeypatch):
+    held = hold_contextual_final_idle(env, monkeypatch)
+    token = CountingToken()
+    try:
+        ordinary = start_ordinary_behind(held, env, token)
+        assert_not_polled(lambda: token.checks)
+        token.cancel()
+        finish(ordinary)
+    finally:
+        held.release.set()
+    finish(held.contextual)
+
+
+def test_contextual_delivery_wait_does_not_poll(env, monkeypatch):
+    prove_fake_quiescence(env, monkeypatch)
+    monkeypatch.setattr(env.native, "processText2Speech", lambda instance, text: emit(env, instance))
+    entered, release = Event(), Event()
+
+    def blocking_sink(event):
+        entered.set()
+        assert release.wait(2), "Test did not release the sink"
+
+    token = CountingToken()
+    context = env.rt.models.PlaybackContext(object(), 17)
+    call = run_thread(lambda: env.core.speak_segment(("hello",), token, context=context, on_event=blocking_sink))
+    try:
+        assert entered.wait(1)
+        assert_not_polled(lambda: token.checks)
+        token.cancel()
+        assert call[1].wait(0.5), "speak_segment was not woken by token cancellation"
+    finally:
+        release.set()
+    finish(call)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_lifecycle_private_access.py -q 2>&1 | grep -E "Left contains|passed|failed"`
Expected: `Left contains 27 more items, first extra item: 'Cerence:464: operation._retired'` and `1 failed, 1 passed`. The guard's self-test passes; the scan lists 27 accesses, the spec's 26 locations with one line counted twice.

Run: `python3 -m pytest tests/test_vocalizer_segment_drain.py -q -k does_not_poll 2>&1 | tail -1`
Expected: `4 failed, 155 deselected`, each `waiter is polling instead of waiting for a notification`.

- [ ] **Step 3: Migrate the wrappers**

Save as `$PATCHES/t3-impl.patch`, then run `git apply $PATCHES/t3-impl.patch`:

```diff
diff --git a/addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py b/addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py
index 771b565..7ee005b 100644
--- a/addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py
+++ b/addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py
@@ -461,7 +461,7 @@ class SynthDriver(BaseSynthDriver):
 				self._segmentLifecycle.reject_new(context, token, deliver, error.__cause__ or error)
 				self._wait_segment_delivery(completion, token)
 				return
-			if operation._retired and not work.cancelled and not token.is_cancelled():
+			if operation.is_retired() and not work.cancelled and not token.is_cancelled():
 				self._wait_segment_delivery(completion, token)
 		finally:
 			with self._speechStateLock:
@@ -472,15 +472,14 @@ class SynthDriver(BaseSynthDriver):
 	def _wait_segment_delivery(self, completion, token):
 		# A listener may synchronously ask for another segment. The coordinator
 		# owns a single delivery thread, so it cannot wait for its own callback.
-		if (
-			not token.is_cancelled()
-			and threading.current_thread() is not self._segmentLifecycle._delivery_thread
-		):
-			while not completion.wait(0.05):
-				# External tokens have no notification hook. Poll only while the
-				# caller is waiting; direct cancellation sets completion itself.
-				if token.is_cancelled():
-					return
+		if token.is_cancelled() or self._segmentLifecycle.on_delivery_thread():
+			return
+		# Token cancellation wakes this wait; direct cancellation sets completion itself.
+		remove_wake = token.add_callback(completion.set)
+		try:
+			completion.wait()
+		finally:
+			remove_wake()
 
 	# The inner driver still parses settings and splits text. Its synchronous
 	# native calls and callback gate form the SDK boundary for this operation.
@@ -562,24 +561,17 @@ class SynthDriver(BaseSynthDriver):
 		# owner needs the run lock to submit.
 		lifecycle = self._segmentLifecycle
 		while True:
-			if work.operation is None:
-				while work.is_valid():
-					with lifecycle._condition:
-						if not lifecycle._resource_busy:
-							break
-						# External tokens have no notification hook.
-						lifecycle._condition.wait(0.05)
-				if not work.is_valid():
-					yield False
-					return
+			if work.operation is None and not lifecycle.wait_idle(
+				still_wanted=work.is_valid,
+				token=work.token,
+			):
+				yield False
+				return
 			with self._speechRunLock:
-				if work.operation is None:
-					with lifecycle._condition:
-						busy = lifecycle._resource_busy
-					if busy:
-						# A contextual run acquired the resource before this
-						# request acquired the run lock. Let it submit first.
-						continue
+				if work.operation is None and lifecycle.is_resource_busy():
+					# A contextual run acquired the resource before this
+					# request acquired the run lock. Let it submit first.
+					continue
 				yield True
 				return
 
@@ -778,6 +770,8 @@ class SynthDriver(BaseSynthDriver):
 			self._stops += 1
 			self._playerLocal.depth = getattr(self._playerLocal, "depth", 0) + 1
 			self._speechStateLock.notify_all()
+		# Ordinary speech waiting for the contextual resource re-checks its work.
+		self._segmentLifecycle.wake_waiters()
 		if native is not None and native.call_token is not None:
 			self._segmentGate.close(native.call_token)
 		for operation in operations:
@@ -910,10 +904,7 @@ class SynthDriver(BaseSynthDriver):
 		self._terminationLocal.cleaning = True
 		try:
 			# Keep native/player resources alive until the coordinator retires its stop.
-			with self._segmentLifecycle._condition:
-				self._segmentLifecycle._condition.wait_for(
-					lambda: not self._segmentLifecycle._resource_busy,
-				)
+			self._segmentLifecycle.wait_idle()
 			with self._speechRunLock:
 				with self._speechStateLock:
 					self._speechStateLock.wait_for(lambda: self._stops == 0 and self._pauses == 0)
diff --git a/addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py b/addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py
index 0949e85..ad132ee 100644
--- a/addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py
+++ b/addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py
@@ -1,7 +1,7 @@
 import ctypes
 from dataclasses import dataclass
 import io
-from threading import Condition, Event, Lock, Thread, current_thread
+from threading import Condition, Event, Lock, Thread
 import wave
 import weakref
 
@@ -172,7 +172,7 @@ class SynthDriver(BaseOneCoreSynthDriver):
 			self._segmentAccepted.add(operation)
 		if not operation.is_valid():
 			with self._segmentCondition:
-				if not operation._run_started:
+				if not operation.has_started():
 					self._segmentLifecycle.reject_pending(
 						operation,
 						RuntimeError("OneCore segment was cancelled before submission"),
@@ -196,7 +196,7 @@ class SynthDriver(BaseOneCoreSynthDriver):
 			with self._segmentCondition:
 				self._checkSegmentAdmission()
 				if not operation.is_valid():
-					if not operation._run_started:
+					if not operation.has_started():
 						self._segmentLifecycle.reject_pending(
 							operation,
 							RuntimeError("OneCore segment was cancelled before submission"),
@@ -213,7 +213,7 @@ class SynthDriver(BaseOneCoreSynthDriver):
 			self._processQueue()
 		except Exception as error:
 			with self._segmentCondition:
-				if not operation._run_started:
+				if not operation.has_started():
 					self._segmentLifecycle.reject_pending(operation, error)
 				if not operation.work.is_valid():
 					self._segmentAccepted.discard(operation)
@@ -541,7 +541,7 @@ class SynthDriver(BaseOneCoreSynthDriver):
 				try:
 					if operation in queued:
 						with self._segmentCondition:
-							if not operation._run_started:
+							if not operation.has_started():
 								self._segmentLifecycle.reject_pending(operation, error)
 					else:
 						self._segmentLifecycle.fail(operation, error)
@@ -602,7 +602,7 @@ class SynthDriver(BaseOneCoreSynthDriver):
 						item.work.cancel()
 			for operation in tuple(self._segmentAccepted):
 				self._segmentLifecycle.cancel(operation)
-				if not operation._run_started:
+				if not operation.has_started():
 					self._segmentLifecycle.reject_pending(
 						operation,
 						RuntimeError("OneCore segment was cancelled before submission"),
@@ -679,9 +679,7 @@ class SynthDriver(BaseOneCoreSynthDriver):
 			self.cancel()
 		finally:
 			self._segmentLifecycle.terminate()
-			delivery = self._segmentLifecycle._delivery_thread
-			if delivery is not current_thread():
-				delivery.join(1)
+			self._segmentLifecycle.join_delivery(1)
 			super().terminate()
 
 
diff --git a/addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py b/addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py
index 3a045f4..9cd0a96 100644
--- a/addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py
+++ b/addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py
@@ -502,7 +502,7 @@ class SynthDriver(rhvoice.SynthDriver):
 			self._segmentLifecycle.reject_new(
 				operation.work.context,
 				operation.work.token,
-				lambda event: None if operation._rhvoice_cancelled else operation._sink(event),
+				lambda event: None if operation._rhvoice_cancelled else operation.sink(event),
 				self._segmentControlError or error.__cause__ or error,
 			)
 		finally:
diff --git a/addon/synthDrivers/WorldVoice/driver/VE/__init__.py b/addon/synthDrivers/WorldVoice/driver/VE/__init__.py
index 298c174..5878387 100644
--- a/addon/synthDrivers/WorldVoice/driver/VE/__init__.py
+++ b/addon/synthDrivers/WorldVoice/driver/VE/__init__.py
@@ -461,7 +461,7 @@ class SynthDriver(BaseSynthDriver):
 				self._segmentLifecycle.reject_new(context, token, deliver, error.__cause__ or error)
 				self._wait_segment_delivery(completion, token)
 				return
-			if operation._retired and not work.cancelled and not token.is_cancelled():
+			if operation.is_retired() and not work.cancelled and not token.is_cancelled():
 				self._wait_segment_delivery(completion, token)
 		finally:
 			with self._speechStateLock:
@@ -472,15 +472,14 @@ class SynthDriver(BaseSynthDriver):
 	def _wait_segment_delivery(self, completion, token):
 		# A listener may synchronously ask for another segment. The coordinator
 		# owns a single delivery thread, so it cannot wait for its own callback.
-		if (
-			not token.is_cancelled()
-			and threading.current_thread() is not self._segmentLifecycle._delivery_thread
-		):
-			while not completion.wait(0.05):
-				# External tokens have no notification hook. Poll only while the
-				# caller is waiting; direct cancellation sets completion itself.
-				if token.is_cancelled():
-					return
+		if token.is_cancelled() or self._segmentLifecycle.on_delivery_thread():
+			return
+		# Token cancellation wakes this wait; direct cancellation sets completion itself.
+		remove_wake = token.add_callback(completion.set)
+		try:
+			completion.wait()
+		finally:
+			remove_wake()
 
 	# The inner driver still parses settings and splits text. Its synchronous
 	# native calls and callback gate form the SDK boundary for this operation.
@@ -562,24 +561,17 @@ class SynthDriver(BaseSynthDriver):
 		# owner needs the run lock to submit.
 		lifecycle = self._segmentLifecycle
 		while True:
-			if work.operation is None:
-				while work.is_valid():
-					with lifecycle._condition:
-						if not lifecycle._resource_busy:
-							break
-						# External tokens have no notification hook.
-						lifecycle._condition.wait(0.05)
-				if not work.is_valid():
-					yield False
-					return
+			if work.operation is None and not lifecycle.wait_idle(
+				still_wanted=work.is_valid,
+				token=work.token,
+			):
+				yield False
+				return
 			with self._speechRunLock:
-				if work.operation is None:
-					with lifecycle._condition:
-						busy = lifecycle._resource_busy
-					if busy:
-						# A contextual run acquired the resource before this
-						# request acquired the run lock. Let it submit first.
-						continue
+				if work.operation is None and lifecycle.is_resource_busy():
+					# A contextual run acquired the resource before this
+					# request acquired the run lock. Let it submit first.
+					continue
 				yield True
 				return
 
@@ -770,6 +762,8 @@ class SynthDriver(BaseSynthDriver):
 			self._stops += 1
 			self._playerLocal.depth = getattr(self._playerLocal, "depth", 0) + 1
 			self._speechStateLock.notify_all()
+		# Ordinary speech waiting for the contextual resource re-checks its work.
+		self._segmentLifecycle.wake_waiters()
 		if native is not None and native.call_token is not None:
 			self._segmentGate.close(native.call_token)
 		for operation in operations:
@@ -904,10 +898,7 @@ class SynthDriver(BaseSynthDriver):
 			# A stop may have been scheduled after the synchronous speech lock
 			# was released. Keep native/player resources alive through its
 			# coordinator retirement barrier.
-			with self._segmentLifecycle._condition:
-				self._segmentLifecycle._condition.wait_for(
-					lambda: not self._segmentLifecycle._resource_busy,
-				)
+			self._segmentLifecycle.wait_idle()
 			with self._speechRunLock:
 				with self._speechStateLock:
 					self._speechStateLock.wait_for(lambda: self._stops == 0 and self._pauses == 0)
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/test_lifecycle_private_access.py -q 2>&1 | tail -1`
Expected: `2 passed`

Run: `python3 -m pytest tests/test_vocalizer_segment_drain.py -q -k does_not_poll 2>&1 | tail -1`
Expected: `4 passed, 155 deselected`

Run: `python3 -m pytest tests -q 2>&1 | tail -1`
Expected: `1276 passed, 96 skipped, 2 xfailed`

Run: `grep -n "wait(0.05)" addon/synthDrivers/WorldVoice/driver/VE/__init__.py addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py; ruff format --check addon | tail -1; ruff check --select F401 addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py; ruff check tests/test_lifecycle_private_access.py`
Expected: no grep output, `52 files already formatted`, `All checks passed!`, `All checks passed!`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_lifecycle_private_access.py tests/test_vocalizer_segment_drain.py \
	addon/synthDrivers/WorldVoice/driver/VE/__init__.py addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py \
	addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py
git commit -m "refactor(drivers): use the public lifecycle API and drop cancellation polls

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Contract harness uses `on_delivery_thread()`

**Files:**
- Modify: `tests/engine_contract_harness.py` (`delivery_thread_ident` → `on_delivery_thread`)
- Modify: `tests/test_engine_segment_contract.py` (`Events(adapter)` records `on_delivery_thread()` at delivery; contract 1 asserts `[True]`)

**Interfaces:**
- Consumes `SegmentLifecycle.on_delivery_thread()` from Task 2.
- Produces the adapter method `on_delivery_thread() -> bool`, replacing `delivery_thread_ident()`.

- [ ] **Step 1: Apply the change**

Save as `$PATCHES/t4.patch`, then run `git apply $PATCHES/t4.patch`:

```diff
diff --git a/tests/engine_contract_harness.py b/tests/engine_contract_harness.py
index 6e53c37..6c4c060 100644
--- a/tests/engine_contract_harness.py
+++ b/tests/engine_contract_harness.py
@@ -2,8 +2,8 @@
 
 Each adapter loads one real outer engine wrapper with that engine's existing
 fakes. After ``open`` the fakes hold every segment before its final playback
-barrier; only ``complete`` lets the current segment finish. Private runtime
-access stays here so later phases only need to update the adapters.
+barrier; only ``complete`` lets the current segment finish. Runtime access
+stays here so later phases only need to update the adapters.
 """
 
 import sys
@@ -45,9 +45,8 @@ class _Adapter:
 	def terminate(self):
 		self.core.terminate()
 
-	def delivery_thread_ident(self):
-		thread = self.core._segmentLifecycle._delivery_thread
-		return None if thread is None else thread.ident
+	def on_delivery_thread(self):
+		return self.core._segmentLifecycle.on_delivery_thread()
 
 
 class EspeakAdapter(_Adapter):
diff --git a/tests/test_engine_segment_contract.py b/tests/test_engine_segment_contract.py
index 2cdc521..383f77a 100644
--- a/tests/test_engine_segment_contract.py
+++ b/tests/test_engine_segment_contract.py
@@ -50,15 +50,19 @@ def _c3(engine):
 
 
 class Events(list):
-	def __init__(self):
+	def __init__(self, adapter):
 		super().__init__()
 		self.condition = Condition()
 		self.threads = []
+		self.on_delivery_thread = []
+		self._adapter = adapter
 
 	def append(self, event):
+		on_delivery_thread = self._adapter.on_delivery_thread()
 		with self.condition:
 			super().append(event)
 			self.threads.append(get_ident())
+			self.on_delivery_thread.append(on_delivery_thread)
 			self.condition.notify_all()
 
 	def wait_one(self, timeout=2):
@@ -96,7 +100,7 @@ def _start_speak(adapter, token, context, events):
 @pytest.mark.parametrize("engine", _engines(), indirect=True)
 def test_completed_segment_drains_once_on_the_delivery_thread(engine):
 	context = engine.PlaybackContext(object(), 17)
-	events = Events()
+	events = Events(engine)
 	caller, errors = _start_speak(engine, engine.new_token(), context, events)
 
 	engine.complete()
@@ -107,7 +111,7 @@ def test_completed_segment_drains_once_on_the_delivery_thread(engine):
 	assert event.kind is engine.EventKind.SEGMENT_DRAINED
 	assert event.source_id is context.source_id
 	assert event.segment_id == 17
-	assert events.threads == [engine.delivery_thread_ident()]
+	assert events.on_delivery_thread == [True]
 	assert events.threads[0] != caller.ident
 
 
@@ -115,7 +119,7 @@ def test_completed_segment_drains_once_on_the_delivery_thread(engine):
 def test_segment_after_terminate_fails_once_without_native_call(engine):
 	engine.terminate()
 	context = engine.PlaybackContext(object(), 19)
-	events = Events()
+	events = Events(engine)
 	caller, errors = _start_speak(engine, engine.new_token(), context, events)
 
 	event = events.wait_one()
@@ -132,7 +136,7 @@ def test_segment_after_terminate_fails_once_without_native_call(engine):
 def test_cancelled_token_never_reaches_native_or_sink(engine):
 	token = engine.new_token()
 	token.cancel()
-	events = Events()
+	events = Events(engine)
 	caller, errors = _start_speak(engine, token, engine.PlaybackContext(object(), 21), events)
 
 	caller.join(2)
@@ -147,7 +151,7 @@ def test_cancelled_token_never_reaches_native_or_sink(engine):
 @pytest.mark.parametrize("engine", _engines(VE=_c3("VE"), Cerence=_c3("Cerence")), indirect=True)
 def test_speak_segment_returns_before_delivery(engine):
 	context = engine.PlaybackContext(object(), 23)
-	events = Events()
+	events = Events(engine)
 	caller, errors = _start_speak(engine, engine.new_token(), context, events)
 
 	caller.join(1)
```

- [ ] **Step 2: Run and prove it still bites**

Run: `python3 -m pytest tests/test_engine_segment_contract.py -q 2>&1 | tail -1`
Expected: `22 passed, 4 skipped, 2 xfailed`

```bash
H=tests/engine_contract_harness.py
sed -i 's/^\t\treturn self.core._segmentLifecycle.on_delivery_thread()$/\t\treturn False/' $H
python3 -m pytest tests/test_engine_segment_contract.py -q -k test_completed 2>&1 | tail -1
git checkout -- $H
```

Expected: `6 failed, 1 skipped, 21 deselected`, then the file is restored.

Run: `ruff format --check tests/engine_contract_harness.py tests/test_engine_segment_contract.py && ruff check tests/engine_contract_harness.py tests/test_engine_segment_contract.py`
Expected: `2 files already formatted`, `All checks passed!`

- [ ] **Step 3: Commit**

```bash
git add tests/engine_contract_harness.py tests/test_engine_segment_contract.py
git commit -m "test: contract harness asks the lifecycle for the delivery thread

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Neural verification, stability, final checks

**Files:** none modified.

**Interfaces:**
- Consumes all previous tasks.
- Produces the acceptance evidence.

- [ ] **Step 1: Neural worktree**

```bash
W=/workspace/WorldVoice-neural-check
git worktree add --detach "$W" HEAD
ln -s /workspace/WorldVoice/ref "$W/ref"
python3 -c "import zipfile; zipfile.ZipFile('/workspace/WorldVoice/storage/Neural-snapshot-2026-10-01.zip').extractall('$W')"
(cd "$W" && python3 -m pytest tests -q 2>&1 | tail -1)
(cd "$W" && python3 -m pytest tests/test_lifecycle_private_access.py tests/test_engine_segment_contract.py -q 2>&1 | tail -1)
(cd "$W" && git status --short)
git worktree remove --force "$W"
```

Expected:
- Full suite: `1372 passed, 9 skipped, 2 xfailed`.
  - Known pre-existing flake, also on master `dfe01e6` at about 5 in 100 runs: `test_neural_segment_drain.py::test_explicit_activation_override_completes_with_unproven_quiescence` sometimes fails with `assert [] == [b'\x01\x02']`.
  - If that is the only failure, rerun the suite once. Any other failure is real.
- The guard and contract files together: `28 passed, 2 xfailed`. The guard also scans Neural, which only uses `_neural_*` attributes.
- `git status --short` prints nothing.
- The worktree is removed.

- [ ] **Step 2: No-poll tests are stable**

Run: `for i in $(seq 1 10); do python3 -m pytest tests/test_vocalizer_segment_drain.py tests/test_segment_lifecycle.py -q -k "poll or wakes or wait_idle" 2>&1 | tail -1; done | sed 's/ in .*//' | sort | uniq -c`
Expected: a single line, `10 10 passed, 180 deselected`.

- [ ] **Step 3: Final checks**

Run: `python3 -m pytest tests -q 2>&1 | tail -1`
Expected: `1276 passed, 96 skipped, 2 xfailed`

Run:
```bash
grep -n "wait(0.05)" addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py addon/synthDrivers/WorldVoice/driver/VE/__init__.py addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py
ruff format --check addon | tail -1
git diff master --stat -- 'addon/synthDrivers/WorldVoice/driver/*/driver'
git ls-files addon/synthDrivers/WorldVoice/driver/Neural
git log --oneline master..HEAD
```

Expected:
- No grep output, then `52 files already formatted`, then no output from the two path checks.
- The log lists, oldest at the bottom:
  1. `docs: add phase 2 lifecycle public API design spec`
  2. `docs: add phase 2 implementation plan`
  3. `feat(runtime): notify cancellation callbacks instead of being polled`
  4. `feat(runtime): public lifecycle queries and notification-driven waits`
  5. `refactor(drivers): use the public lifecycle API and drop cancellation polls`
  6. `test: contract harness asks the lifecycle for the delivery thread`
