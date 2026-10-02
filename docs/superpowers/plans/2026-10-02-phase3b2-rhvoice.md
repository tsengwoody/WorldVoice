# Phase 3b-2: RHVoice Migration to SegmentHost Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `runtime/segmentHost.py` the four mechanisms RHVoice needs, then move the RHVoice wrapper onto the host, keeping its observable behavior except one approved change: a failed ordinary utterance now stops the player.

**Architecture:**
- **Task 1 (shared runtime):**
  - `retire(record, finish=...)` runs worker-side cleanup after the record is sealed.
  - `consumer(record, audio=True)` admits player index callbacks after `close()`.
  - `wait_settled(record)` gives NVDA cancel its synchronous wait, with exemptions that avoid deadlock.
  - `SegmentHost(..., fail_accepted_on_control_error=True)` fails every accepted operation on a control error and relabels an unpublished DRAINED.
  - The lifecycle delivery loop stops pinning the last retired operation.
- **Task 2 (RHVoice):**
  - `_RHVoiceStrategy` plus the remaining native-specific pieces sit on the host: callback identity, `_NativeLibrary`, `_WavePlayer`, `_QueuedSpeech` and the cancel gate.
  - The wrapper shrinks from 719 to 384 lines.
- eSpeak and SAPI5 do not opt in, and their wrappers are untouched.

**Tech Stack:** Python 3 threading, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-10-02-phase3b2-rhvoice-design.md`

## Global Constraints

- Work on branch `phase3b2-rhvoice`, cut from `master` at `5e74ab5`; the spec commit `c925d0a` and the plan commit are on it.
- **Do not change** `addon/synthDrivers/WorldVoice/driver/{OneCore,VE,Cerence,Espeak,SAPI5}/__init__.py`. Their tests must pass, and VE/Cerence contract 4 stays xfail.
- Never modify `driver/<Engine>/driver/` and never commit `driver/Neural/`. Neural compatibility is not required.
- No shared VE/Cerence code. Code shared by all engines lives only in `runtime/`.
- New public names are snake_case.
- Every changed `addon/` file passes `ruff format --check`; `tests/test_segment_host.py` passes `ruff check`.
- Run from `/workspace/WorldVoice`, since tests need the untracked `ref/`. Stage explicit paths only; never stage the user's unstaged deletion of `docs/superpowers/finish_task.md`.
- Baseline before Task 1: `python3 -m pytest tests -q` → `1326 passed, 96 skipped, 2 xfailed`.
- Each code step applies a patch saved verbatim from this plan: set `PATCHES=$(mktemp -d)` once, save the block to the named file, then run `git apply`.
- **Mutation steps come after the commit step.** They end with `git checkout -- <file>`, which would otherwise discard uncommitted work; this happened in phases 2 and 3a.
- Every commit message ends with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **NVDA cancel re-entered from a sink, an index listener or the done listener.**
   - `wait_settled` must never wait for the caller's own record, nor for a sink that may be waiting for the caller.
   - Covered by the existing RHVoice tests:
     - `test_legacy_done_callback_can_cancel_without_deadlocking_worker`
     - `test_audio_index_listener_can_cancel_from_its_own_callback_thread`
     - `test_callback_cancel_does_not_wait_for_delivery_cancel_awaiting_that_callback`
     - `test_reentrant_successor_during_concurrent_cancel_does_not_deadlock`
   - Also covered by Task 1's `wait_settled` tests (M1d–M1h).
   - The reviewer should still look for an unexempted path, for example the worker thread outside its `bound_callback` block.
2. **Lock order under cancel.**
   - `cancel()` holds host admission across `host.abandon` (which waits for consumers) and the inner `cancel()` (which drains the tts queue and stops the player).
   - The worker gate takes `_segmentCondition` and then the host condition. `_native_callback` releases `_segmentCondition` before `host.consumer`.
   - The reviewer checks by reading that no path takes `_segmentCondition` while holding the host condition, and that no consumer waits for host admission.
3. **Tail indexes during the final idle.** Index callbacks released by the worker's final idle must still index; any that arrive after `retire()` seals the record must be dropped.
   - Covered by `test_admitted_late_feed_gets_final_idle_and_index_before_drain` and `test_admitted_native_mark_can_enter_nested_feed_after_callback_gate_closes` (M2a).
   - Also covered by `test_retire_seals_the_record_against_audio_consumers` (M1a).
4. **Ordinary speech after the approved change.** A completed ordinary utterance must never stop the player; a failed one must.
   - Covered by `test_completed_ordinary_speech_does_not_stop_the_player` and `test_failed_ordinary_speech_stops_the_player` (M2e).
5. **A control error racing a terminal delivery.**
   - `lifecycle.fail()` can land after the delivery thread has read the operation's result. The host's DRAINED→FAILED relabel in `_deliver` covers that window.
   - Without it, `test_stop_fault_before_deferred_terminal_delivery_fails_closed` failed 11 of 15 runs during prototyping.
   - Covered by `test_opted_in_control_error_relabels_a_drain_the_lifecycle_already_committed` (M1i) and M2d.

---

### Task 1: Host and lifecycle extensions

Spec §1 and §2. eSpeak and SAPI5 do not opt in; their tests must pass unchanged.

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/runtime/segmentHost.py`
- Modify: `addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py` (`_deliver` clears its loop locals)
- Modify: `tests/test_segment_host.py`:
  - The `env` fixture takes optional host keyword arguments through `indirect` parametrization.
  - 15 new tests.
- Modify: `tests/test_segment_lifecycle.py` (one new test)

**Interfaces:**
- Consumes: the 3b-1 host (`SegmentHost`, `NativeRecord`, `NativeStrategy`, `LeasedPlayer`) at `5e74ab5`.
- Produces (Task 2 relies on these exact names):
  - `SegmentHost(engine, strategy, *, fail_accepted_on_control_error: bool = False)`
  - `host.consumer(record=None, *, audio: bool = False)`:
    - `audio=True` admits a consumer after `close()`, until `retire()` seals the record.
    - It still refuses invalid, sealed or non-current records.
  - `host.retire(record, *, finish: Callable[[], None] | None = None) -> OrdinaryOutcome | None`, in this order:
    1. Seals the record (`closed = True`).
    2. Waits for consumers to reach zero.
    3. Calls `finish()` outside the host condition; an exception it raises is recorded with `record_error`.
    4. Clears the current record and calls `notify_all`, then retires as in 3b-1.
  - `host.wait_settled(record: NativeRecord | None) -> None`:
    - Waits until `record` is no longer current, unless `callback_record() is record`.
    - Waits until the sinks running at call time have returned, unless the caller is a bound callback or the delivery thread.
  - `latch_control_error(error)`, when opted in, calls `lifecycle.fail(operation, error)` for every accepted operation, outside the host condition.
  - `_deliver`, when opted in and a control error is latched, publishes a DRAINED event as FAILED with that error.
  - The host tracks running sinks in `_delivering`.

- [ ] **Step 1: Write the failing tests**

Save as `$PATCHES/t1-tests.patch`, then run `git apply $PATCHES/t1-tests.patch`:

```diff
diff --git a/tests/test_segment_host.py b/tests/test_segment_host.py
index 24f5ded..4f869d3 100644
--- a/tests/test_segment_host.py
+++ b/tests/test_segment_host.py
@@ -74,13 +74,14 @@ def _load(monkeypatch, rt, name):
 
 
 @pytest.fixture
-def env(monkeypatch):
+def env(monkeypatch, request):
+	options = getattr(request, "param", {})
 	rt = load_runtime(monkeypatch)
 	scheduler = load_scheduler(monkeypatch, rt)
 	_load(monkeypatch, rt, "segmentLifecycle")
 	module = _load(monkeypatch, rt, "segmentHost")
 	strategy = FakeStrategy()
-	host = module.SegmentHost("Fake", strategy)
+	host = module.SegmentHost("Fake", strategy, **options)
 	threads = []
 
 	def speak(segment=17, sink=None, token=None):
@@ -632,3 +633,244 @@ def test_engine_admission_error_rejects_before_acceptance(env):
 	assert event.segment_id == 33
 	assert env.strategy.submitted == []
 	assert env.host._accepted == {}
+
+
+def wait_until(predicate, timeout=1):
+	deadline = Event()
+	for _ in range(int(timeout / 0.005)):
+		if predicate():
+			return True
+		deadline.wait(0.005)
+	return predicate()
+
+
+def test_audio_consumer_is_admitted_after_close(env):
+	env.speak()
+	record = env.strategy.wait_submitted()
+	env.host.begin(record)
+	env.host.close(record)
+	with env.host.consumer(record) as plain:
+		assert plain is None
+	with env.host.consumer(record, audio=True) as audio:
+		assert audio is record
+	env.run_native(record)
+
+
+def test_retire_seals_the_record_against_audio_consumers(env):
+	_, _, events = env.speak()
+	record = env.strategy.wait_submitted()
+	env.host.begin(record)
+	env.host.close(record)
+	held, release = Event(), Event()
+
+	def hold():
+		with env.host.consumer(record, audio=True) as admitted:
+			assert admitted is record
+			held.set()
+			assert release.wait(2)
+
+	Thread(target=hold, daemon=True).start()
+	assert held.wait(1)
+	for barrier in ("returned", "idle"):
+		env.host.reach(record, barrier)
+	Thread(target=env.host.retire, args=(record,), daemon=True).start()
+	assert wait_until(lambda: record.closed)
+	with env.host.consumer(record, audio=True) as late:
+		assert late is None
+	assert env.host.current() is record
+	release.set()
+	assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED
+
+
+def test_retire_runs_finish_after_consumers_and_before_retirement(env):
+	_, _, events = env.speak()
+	record = env.strategy.wait_submitted()
+	env.host.begin(record)
+	order = []
+	held, release = Event(), Event()
+
+	def hold():
+		with env.host.consumer(record) as admitted:
+			assert admitted is record
+			held.set()
+			assert release.wait(2)
+			order.append("consumer")
+
+	def finish():
+		order.append(("finish", record.consumers, record.retired.is_set(), env.host.current() is record))
+
+	Thread(target=hold, daemon=True).start()
+	assert held.wait(1)
+	for barrier in ("returned", "idle"):
+		env.host.reach(record, barrier)
+	Thread(target=lambda: env.host.retire(record, finish=finish), daemon=True).start()
+	release.set()
+	assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED
+	assert order == ["consumer", ("finish", 0, False, True)]
+
+
+def test_finish_error_fails_only_that_segment(env):
+	_, _, failed = env.speak()
+	record = env.strategy.wait_submitted()
+	env.host.begin(record)
+	for barrier in ("returned", "idle"):
+		env.host.reach(record, barrier)
+
+	def finish():
+		raise OSError("delete failed")
+
+	Thread(target=lambda: env.host.retire(record, finish=finish), daemon=True).start()
+	event = failed.wait_one()
+	assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
+	assert isinstance(event.error, OSError)
+	_, _, events = env.speak(segment=18)
+	env.run_native(env.strategy.wait_submitted(2))
+	assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED
+
+
+def test_wait_settled_waits_for_the_record_to_leave_the_worker(env):
+	env.speak()
+	record = env.strategy.wait_submitted()
+	env.host.begin(record)
+	settled = Event()
+	Thread(target=lambda: (env.host.wait_settled(record), settled.set()), daemon=True).start()
+	assert not settled.wait(0.1)
+	env.run_native(record)
+	assert settled.wait(1)
+
+
+def test_wait_settled_from_the_records_own_callback_does_not_wait(env):
+	env.speak()
+	record = env.strategy.wait_submitted()
+	env.host.begin(record)
+	settled = Event()
+
+	def settle():
+		with env.host.bound_callback(record):
+			env.host.wait_settled(record)
+		settled.set()
+
+	Thread(target=settle, daemon=True).start()
+	assert settled.wait(1)
+	env.run_native(record)
+
+
+def test_wait_settled_waits_for_a_running_sink(env):
+	entered, release = Event(), Event()
+
+	def sink(event):
+		entered.set()
+		assert release.wait(2)
+
+	env.speak(sink=sink)
+	env.run_native(env.strategy.wait_submitted())
+	assert entered.wait(2)
+	settled = Event()
+	Thread(target=lambda: (env.host.wait_settled(None), settled.set()), daemon=True).start()
+	assert not settled.wait(0.1)
+	release.set()
+	assert settled.wait(1)
+
+
+def test_wait_settled_from_a_sink_does_not_wait_for_sinks(env):
+	settled = Event()
+
+	def sink(event):
+		env.host.wait_settled(None)
+		settled.set()
+
+	env.speak(sink=sink)
+	env.run_native(env.strategy.wait_submitted())
+	assert settled.wait(1)
+
+
+def test_wait_settled_from_a_callback_does_not_wait_for_sinks(env):
+	entered, release = Event(), Event()
+
+	def sink(event):
+		entered.set()
+		assert release.wait(2)
+
+	env.speak(sink=sink)
+	first = env.strategy.wait_submitted()
+	env.run_native(first)
+	assert entered.wait(2)
+	settled = Event()
+
+	def settle():
+		with env.host.bound_callback(first):
+			env.host.wait_settled(None)
+		settled.set()
+
+	Thread(target=settle, daemon=True).start()
+	try:
+		assert settled.wait(1)
+	finally:
+		release.set()
+
+
+@pytest.mark.parametrize(
+	("env", "kind"),
+	[({}, "SEGMENT_DRAINED"), ({"fail_accepted_on_control_error": True}, "SEGMENT_FAILED")],
+	indirect=["env"],
+)
+def test_control_error_and_an_unpublished_drain(env, kind):
+	entered, release = Event(), Event()
+
+	def blocking(event):
+		entered.set()
+		assert release.wait(2)
+
+	env.speak(segment=17, sink=blocking)
+	env.run_native(env.strategy.wait_submitted())
+	assert entered.wait(2)
+	_, _, events = env.speak(segment=18)
+	env.run_native(env.strategy.wait_submitted(2))
+	assert env.host._lifecycle.wait_idle()
+	env.host.latch_control_error(OSError("stop failed"))
+	release.set()
+	assert events.wait_one().kind is getattr(env.rt.models.EventKind, kind)
+
+
+@pytest.mark.parametrize("env", [{"fail_accepted_on_control_error": True}], indirect=True)
+def test_opted_in_control_error_relabels_a_drain_the_lifecycle_already_committed(env, monkeypatch):
+	# lifecycle.fail() can land after the delivery thread read the result; the
+	# host itself must not publish success once the control error is latched.
+	monkeypatch.setattr(env.host._lifecycle, "fail", lambda operation, error: None)
+	entered, release = Event(), Event()
+
+	def blocking(event):
+		entered.set()
+		assert release.wait(2)
+
+	env.speak(segment=17, sink=blocking)
+	env.run_native(env.strategy.wait_submitted())
+	assert entered.wait(2)
+	_, _, events = env.speak(segment=18)
+	env.run_native(env.strategy.wait_submitted(2))
+	assert env.host._lifecycle.wait_idle()
+	env.host.latch_control_error(OSError("stop failed"))
+	release.set()
+	event = events.wait_one()
+	assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
+	assert str(event.error) == "stop failed"
+
+
+@pytest.mark.parametrize(
+	("env", "stopped"),
+	[({}, False), ({"fail_accepted_on_control_error": True}, True)],
+	indirect=["env"],
+)
+def test_control_error_and_the_active_segment(env, stopped):
+	# Opted in, a control error stops the active segment at once; by default it
+	# finishes and then fails through its record.
+	_, _, events = env.speak()
+	record = env.strategy.wait_submitted()
+	env.host.begin(record)
+	env.host.latch_control_error(OSError("stop failed"))
+	if stopped:
+		assert wait_until(lambda: record in env.strategy.native_stops)
+	else:
+		assert not wait_until(lambda: bool(env.strategy.native_stops), 0.2)
+	env.run_native(record)
+	assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_FAILED
diff --git a/tests/test_segment_lifecycle.py b/tests/test_segment_lifecycle.py
index 5c9bda1..f7440ef 100644
--- a/tests/test_segment_lifecycle.py
+++ b/tests/test_segment_lifecycle.py
@@ -1,9 +1,11 @@
 """Resource ownership and producer retirement for the shared lifecycle."""
 
+import gc
 import importlib.util
 import logging
 import sys
 from threading import Condition, Event, Thread, current_thread
+import weakref
 
 import pytest
 
@@ -639,6 +641,29 @@ def test_retirement_callback_runs_when_cancel_suppresses_delivery(env):
     assert hooks.submitted == []
 
 
+def test_idle_delivery_thread_releases_a_retired_operation(env):
+    lifecycle, hooks, events, accept = env
+    retired = Event()
+
+    class Sink:
+        def __call__(self, event):
+            events.append(event)
+
+    sink = Sink()
+    reference = weakref.ref(sink)
+    operation, _ = accept(18, sink, on_retired=lambda owner: retired.set())
+    operation.work.token.cancel()
+    lifecycle.reject_pending(operation, RuntimeError("never submitted"))
+    assert retired.wait(1)
+    del operation, sink
+    for _ in range(100):
+        gc.collect()
+        if reference() is None:
+            break
+        Event().wait(0.01)
+    assert reference() is None, "the idle delivery thread still holds the retired operation"
+
+
 def test_reject_new_delivers_after_lifecycle_termination(env):
     lifecycle, hooks, events, _ = env
     lifecycle.terminate()
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests -q 2>&1 | grep -E "^FAILED|^ERROR tests|passed|failed" | sed 's/ - .*//'`
Expected: `10 failed, 1328 passed, 96 skipped, 2 xfailed, 7 warnings, 3 errors`:
- Nine failures are in `tests/test_segment_host.py`, from the missing `audio`/`finish` keywords or the missing `wait_settled` method:
  - `test_audio_consumer_is_admitted_after_close`
  - `test_retire_seals_the_record_against_audio_consumers`
  - `test_retire_runs_finish_after_consumers_and_before_retirement`
  - `test_finish_error_fails_only_that_segment`
  - `test_wait_settled_waits_for_the_record_to_leave_the_worker`
  - `test_wait_settled_from_the_records_own_callback_does_not_wait`
  - `test_wait_settled_waits_for_a_running_sink`
  - `test_wait_settled_from_a_sink_does_not_wait_for_sinks`
  - `test_wait_settled_from_a_callback_does_not_wait_for_sinks`
- The tenth is `tests/test_segment_lifecycle.py::test_idle_delivery_thread_releases_a_retired_operation`.
- The 3 errors are fixture `TypeError`s for the unknown keyword `fail_accepted_on_control_error`:
  - `test_control_error_and_an_unpublished_drain[env1-SEGMENT_FAILED]`
  - `test_opted_in_control_error_relabels_a_drain_the_lifecycle_already_committed[env0]`
  - `test_control_error_and_the_active_segment[env1-True]`
- The default-behavior halves (`[env0-SEGMENT_DRAINED]`, `[env0-False]`) already pass. They pin the behavior that must not change.

- [ ] **Step 3: Implement the extensions**

Save as `$PATCHES/t1-impl.patch`, then run `git apply $PATCHES/t1-impl.patch`:

```diff
diff --git a/addon/synthDrivers/WorldVoice/runtime/segmentHost.py b/addon/synthDrivers/WorldVoice/runtime/segmentHost.py
index c126bcc..3b481c4 100644
--- a/addon/synthDrivers/WorldVoice/runtime/segmentHost.py
+++ b/addon/synthDrivers/WorldVoice/runtime/segmentHost.py
@@ -8,8 +8,9 @@ retires work in the engine's FIFO order. An engine provides a NativeStrategy
 (how to queue, stop and drain its native work) and marks its own completion
 barriers on each record.
 
-Lock order: host admission -> host condition -> lifecycle condition. The host
-never calls the strategy, a sink or a player while holding its own condition.
+Lock order: host admission -> engine lock -> host condition -> lifecycle
+condition. The host never calls the strategy, a sink or a player while holding
+its own condition.
 """
 
 from collections.abc import Callable, Iterator
@@ -19,7 +20,7 @@ import logging
 from threading import Condition, Event, RLock, Thread, local
 from typing import Protocol
 
-from .models import PlaybackContext, PlaybackEvent, SegmentEventSink, SpeechCommands
+from .models import EventKind, PlaybackContext, PlaybackEvent, SegmentEventSink, SpeechCommands
 from .playbackWork import PlaybackWork
 from .segmentLifecycle import ProducerLease, SegmentLifecycle, SegmentOperation
 from .session import CancellationView
@@ -93,9 +94,14 @@ class NativeStrategy(Protocol):
 
 
 class SegmentHost:
-	def __init__(self, engine: str, strategy: NativeStrategy):
+	def __init__(
+		self, engine: str, strategy: NativeStrategy, *, fail_accepted_on_control_error: bool = False
+	):
 		self.engine = engine
 		self._strategy = strategy
+		# Opt-in: a control error also fails every accepted operation, including
+		# ones that already drained but are not yet published.
+		self._fail_accepted = fail_accepted_on_control_error
 		self._admission = RLock()
 		self._condition = Condition(RLock())
 		self._callback_local = local()
@@ -106,6 +112,8 @@ class SegmentHost:
 		self._records: dict[SegmentOperation, NativeRecord] = {}
 		# Accepted operations -> whether the host cancelled them (keeps them silent).
 		self._accepted: dict[SegmentOperation, bool] = {}
+		# Operations whose sink is running on the delivery thread.
+		self._delivering: set[SegmentOperation] = set()
 		self._lifecycle = SegmentLifecycle(self)
 
 	# Entry points ---------------------------------------------------------
@@ -287,8 +295,17 @@ class SegmentHost:
 			self._callback_local.record = previous
 
 	@contextmanager
-	def consumer(self, record: NativeRecord | None = None) -> Iterator[NativeRecord | None]:
-		"""Admit a callback or player call for the current record (None if not admitted)."""
+	def consumer(
+		self,
+		record: NativeRecord | None = None,
+		*,
+		audio: bool = False,
+	) -> Iterator[NativeRecord | None]:
+		"""Admit a callback or player call for the current record (None if not admitted).
+
+		``audio=True`` admits a delayed player callback (e.g. an index onDone)
+		after close() until retire() seals the record.
+		"""
 		with self._condition:
 			record = record or self._current
 			if (
@@ -296,7 +313,7 @@ class SegmentHost:
 				or record is not self._current
 				or not record.is_valid()
 				# After close(), only a callback already bound to this record may nest.
-				or (not record.admitting and self.callback_record() is not record)
+				or (not record.admitting and not audio and self.callback_record() is not record)
 			):
 				admitted = None
 			else:
@@ -359,23 +376,61 @@ class SegmentHost:
 			for record in self._pending:
 				if record.error is None:
 					record.error = self._control_error
+			latched = self._control_error
+			accepted = tuple(self._accepted) if self._fail_accepted else ()
+		for operation in accepted:
+			self._lifecycle_of(operation).fail(operation, latched)
+
+	def wait_settled(self, record: NativeRecord | None) -> None:
+		"""After cancel: wait until ``record`` leaves the worker and running sinks return.
+
+		A callback bound to ``record`` does not wait for that record; a bound
+		callback or the delivery thread does not wait for sinks, which may in
+		turn be waiting for it.
+		"""
+		bound = self.callback_record()
+		in_delivery = self.on_delivery_thread()
+		with self._condition:
+			if record is not None and bound is not record:
+				self._condition.wait_for(lambda: self._current is not record)
+			if bound is None and not in_delivery:
+				running = set(self._delivering)
+				self._condition.wait_for(lambda: not (running & self._delivering))
 
 	def forget(self, record: NativeRecord) -> None:
 		with self._condition:
 			if record in self._pending:
 				self._pending.remove(record)
 
-	def retire(self, record: NativeRecord) -> OrdinaryOutcome | None:
-		"""Retire ``record`` in FIFO order; return the outcome for ordinary speech."""
+	def retire(
+		self,
+		record: NativeRecord,
+		*,
+		finish: Callable[[], None] | None = None,
+	) -> OrdinaryOutcome | None:
+		"""Retire ``record`` in FIFO order; return the outcome for ordinary speech.
+
+		Retirement seals the record: no consumer is admitted afterwards. ``finish``
+		runs on the calling (worker) thread once every consumer has left, before
+		the record stops being current; an exception it raises is recorded on
+		the record.
+		"""
 		with self._condition:
 			valid = record.is_valid()
 			record.closed = True
 			self._condition.wait_for(lambda: record.consumers == 0)
+		if finish is not None:
+			try:
+				finish()
+			except Exception as error:
+				self.record_error(record, error)
+		with self._condition:
 			valid = valid and not record.cancelled and (record.work is None or record.work.is_valid())
 			if not valid and record in self._pending:
 				self._pending.remove(record)
 			if self._current is record:
 				self._current = None
+			self._condition.notify_all()
 		if record.operation is not None:
 			producer, record.producer = record.producer, None
 			if producer is not None:
@@ -506,11 +561,26 @@ class SegmentHost:
 		try:
 			with self._condition:
 				silenced = self._accepted.get(operation, False)
+				control_error = self._control_error
+				self._delivering.add(operation)
 			if not operation.work.token.is_cancelled() and not silenced and not self._terminated:
+				if (
+					self._fail_accepted
+					and control_error is not None
+					and event.kind is EventKind.SEGMENT_DRAINED
+				):
+					event = PlaybackEvent(
+						EventKind.SEGMENT_FAILED,
+						event.source_id,
+						segment_id=event.segment_id,
+						error=control_error,
+					)
 				sink(event)
 		finally:
 			# Work stays cancellable until publication starts on the delivery thread.
 			with self._condition:
+				self._delivering.discard(operation)
+				self._condition.notify_all()
 				self._accepted.pop(operation, None)
 				for record in self._pending:
 					if record.operation is operation:
diff --git a/addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py b/addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py
index be8e541..f75eed9 100644
--- a/addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py
+++ b/addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py
@@ -430,6 +430,9 @@ class SegmentLifecycle:
 
 	def _deliver(self) -> None:
 		while True:
+			# Drop the previous iteration's operation before waiting, so an idle
+			# delivery thread never keeps a retired operation's sink alive.
+			retired = operation = event = None
 			with self._condition:
 				self._condition.wait_for(
 					lambda: self._delivery_queue or self._retirement_queue or self._terminated,
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/test_segment_host.py tests/test_segment_lifecycle.py -q 2>&1 | tail -1`
Expected: `87 passed`

Run: `python3 -m pytest tests -q 2>&1 | tail -1`
Expected: `1341 passed, 96 skipped, 2 xfailed`

Run: `ruff format --check addon | tail -1; ruff check tests/test_segment_host.py`
Expected: `53 files already formatted`, `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add addon/synthDrivers/WorldVoice/runtime/segmentHost.py addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py \
	tests/test_segment_host.py tests/test_segment_lifecycle.py
git commit -m "feat(runtime): retire finish, audio consumers, settled cancel and opt-in accepted failure

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Prove the tests bite (mutations M1a–M1k, after the commit)**

```bash
H=addon/synthDrivers/WorldVoice/runtime/segmentHost.py
L=addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py
mutate() { python3 - "$1" "$2" "$3" <<'PY'
import sys
p, old, new = sys.argv[1:]
s = open(p).read()
assert s.count(old) == 1, old
open(p, "w").write(s.replace(old, new))
PY
}
check() { timeout 300 python3 -m pytest $1 -q -p no:cacheprovider 2>&1 | grep -E '^FAILED|passed|failed' | sed 's/ - .*//'; git checkout -- $H $L; }

mutate $H '				or (not record.admitting and not audio and self.callback_record() is not record)' '				or (not record.admitting and self.callback_record() is not record)'; check tests/test_segment_host.py   # M1a
mutate $H '		if finish is not None:
			try:' '		if False:
			try:'; check tests/test_segment_host.py   # M1b
mutate $H '				finish()
			except Exception as error:
				self.record_error(record, error)' '				finish()
			except Exception:
				pass'; check tests/test_segment_host.py   # M1c
mutate $H '			if record is not None and bound is not record:' '			if False:'; check tests/test_segment_host.py   # M1d
mutate $H '			if record is not None and bound is not record:' '			if record is not None:'; check tests/test_segment_host.py   # M1e
mutate $H '			if bound is None and not in_delivery:' '			if False:'; check tests/test_segment_host.py   # M1f
mutate $H '			if bound is None and not in_delivery:' '			if bound is None:'; check tests/test_segment_host.py   # M1g
mutate $H '			if bound is None and not in_delivery:' '			if not in_delivery:'; check tests/test_segment_host.py   # M1h
mutate $H '				if (
					self._fail_accepted
					and control_error is not None' '				if (
					False
					and control_error is not None'; check tests/test_segment_host.py   # M1i
mutate $H '			accepted = tuple(self._accepted) if self._fail_accepted else ()' '			accepted = ()'; check tests/test_segment_host.py   # M1j
mutate $L '			retired = operation = event = None
' ''; check tests/test_segment_lifecycle.py   # M1k
git status --short | grep addon
```

Expected:
- M1a: `audio` ignored. `2 failed, 51 passed`:
  - `test_audio_consumer_is_admitted_after_close`
  - `test_retire_seals_the_record_against_audio_consumers`
- M1b: `finish` never runs. `2 failed, 51 passed`:
  - `test_retire_runs_finish_after_consumers_and_before_retirement`
  - `test_finish_error_fails_only_that_segment`
- M1c: a `finish` error is swallowed. `1 failed, 52 passed`: `test_finish_error_fails_only_that_segment`
- M1d: does not wait for the record. `1 failed, 52 passed`: `test_wait_settled_waits_for_the_record_to_leave_the_worker`
- M1e: the record's own callback waits. `1 failed, 52 passed`: `test_wait_settled_from_the_records_own_callback_does_not_wait`
- M1f: does not wait for sinks. `1 failed, 52 passed`: `test_wait_settled_waits_for_a_running_sink`
- M1g: the delivery thread waits for sinks. `1 failed, 52 passed`: `test_wait_settled_from_a_sink_does_not_wait_for_sinks`
- M1h: a bound callback waits for sinks. `1 failed, 52 passed`: `test_wait_settled_from_a_callback_does_not_wait_for_sinks`
- M1i: no relabel. `1 failed, 52 passed`: `test_opted_in_control_error_relabels_a_drain_the_lifecycle_already_committed[env0]`
- M1j: accepted operations are not failed. `1 failed, 52 passed`: `test_control_error_and_the_active_segment[env1-True]`
- M1k: delivery locals kept. `1 failed, 33 passed`: `test_idle_delivery_thread_releases_a_retired_operation`

The final `git status` prints nothing.

---

### Task 2: Move RHVoice onto SegmentHost

Spec §3.

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py` (rewrite of the segment path)
- Modify: `tests/test_rhvoice_segment_drain.py`:
  - 12 coupled reads now go through the host.
  - Two new ordinary-speech tests.
- Modify: `tests/test_lifecycle_private_access.py` (`MIGRATED = ("Espeak", "SAPI5", "RHVoice")`)

**Interfaces:**
- Consumes: everything Task 1 produces, by the exact names in its Interfaces block.
- Produces:
  - `SynthDriver._segmentHost`, a `SegmentHost("RHVoice", _RHVoiceStrategy(self), fail_accepted_on_control_error=True)`.
  - `SynthDriver._segmentById`, mapping callback identity to `NativeRecord` (kept under the old name; tests read it).
  - `_RHVoiceStrategy`:
    - `barriers = {"message", "done", "returned", "idle"}`.
    - `submit`: assigns the identity, builds `SpeakText` and queues `_QueuedSpeech`.
    - `stop_native`: sets the cancel flag and stops the player.
    - `stop_player`.
  - `_RHVoiceMessage(identity, library)` in `record.native`.
- The coupled test reads, which change only how they read state:
  1. The fixture also evicts `synthDrivers.WorldVoice.runtime.segmentHost`.
  2. `env.driver._segmentLifecycle` → `env.driver._segmentHost._lifecycle`, in 7 places.
  3. The patched `accept` double takes `*args, **kwargs`.
  4. `env.driver._run_segment` → `env.driver._segmentHost._run`, both the read and the `monkeypatch.setattr`.
  5. `env.driver._segmentAdmission` → `env.driver._segmentHost._admission`.
  6. `operation._rhvoice_cancelled for operation in env.driver._segmentAccepted` → `env.driver._segmentHost._accepted.values()`, in 2 places.
  7. `env.driver._segmentControlError` → `env.driver._segmentHost.control_error`, in 2 places.
  8. `speech.closed` → `not speech.admitting`, in 2 tests.

- [ ] **Step 1: Point the tests at the host and add the ordinary-speech tests**

Save as `$PATCHES/t2-tests.patch`, then run `git apply $PATCHES/t2-tests.patch`:

```diff
diff --git a/tests/test_lifecycle_private_access.py b/tests/test_lifecycle_private_access.py
index 08d61be..9d2357a 100644
--- a/tests/test_lifecycle_private_access.py
+++ b/tests/test_lifecycle_private_access.py
@@ -46,7 +46,7 @@ def test_wrappers_do_not_touch_lifecycle_private_state():
 
 
 # Wrappers moved onto SegmentHost; the host owns their lifecycle entirely.
-MIGRATED = ("Espeak", "SAPI5")
+MIGRATED = ("Espeak", "SAPI5", "RHVoice")
 
 
 def test_migrated_wrappers_only_use_the_segment_host():
diff --git a/tests/test_rhvoice_segment_drain.py b/tests/test_rhvoice_segment_drain.py
index 2972000..b511ded 100644
--- a/tests/test_rhvoice_segment_drain.py
+++ b/tests/test_rhvoice_segment_drain.py
@@ -15,6 +15,7 @@ from rhvoice_drain_harness import finish, load_rhvoice, speak
 @pytest.fixture
 def env(monkeypatch, tmp_path):
     monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentLifecycle", raising=False)
+    monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentHost", raising=False)
     result = load_rhvoice(monkeypatch, tmp_path)
     yield result
     finish(result)
@@ -151,12 +152,12 @@ def test_stop_failure_fails_closed_for_later_work(env):
 def test_cancel_sees_operation_accepted_before_wrapper_registration(env, monkeypatch):
     accepted, release_accept = Event(), Event()
     run_entered, release_run, run_finished = Event(), Event(), Event()
-    lifecycle = env.driver._segmentLifecycle
+    lifecycle = env.driver._segmentHost._lifecycle
     real_accept = lifecycle.accept
-    real_run = env.driver._run_segment
+    real_run = env.driver._segmentHost._run
 
-    def held_accept(*args):
-        operation = real_accept(*args)
+    def held_accept(*args, **kwargs):
+        operation = real_accept(*args, **kwargs)
         accepted.set()
         assert release_accept.wait(3)
         return operation
@@ -170,7 +171,7 @@ def test_cancel_sees_operation_accepted_before_wrapper_registration(env, monkeyp
             run_finished.set()
 
     monkeypatch.setattr(lifecycle, "accept", held_accept)
-    monkeypatch.setattr(env.driver, "_run_segment", held_run)
+    monkeypatch.setattr(env.driver._segmentHost, "_run", held_run)
     token = env.scheduler.CancellationToken()
     context = env.rt.models.PlaybackContext(object(), 17)
     events = []
@@ -181,7 +182,7 @@ def test_cancel_sees_operation_accepted_before_wrapper_registration(env, monkeyp
         assert accepted.wait(1)
         # The speaking thread must hold the admission lock through wrapper
         # registration. A nonblocking probe from this thread detects the gap.
-        admission = env.driver._segmentAdmission
+        admission = env.driver._segmentHost._admission
         acquired = admission.acquire(blocking=False)
         if acquired:
             admission.release()
@@ -346,7 +347,7 @@ def test_legacy_speak_keeps_inner_settings_snapshot_and_queue(env):
 
 
 def test_rhvoice_shared_lifecycle_waits_for_nested_feed_and_final_idle(env):
-    assert env.driver._segmentLifecycle is not None
+    assert env.driver._segmentHost._lifecycle is not None
     callback_entered, release_callback = Event(), Event()
     original_rate = env.driver._SynthDriver__player.set_sample_rate
     calls = 0
@@ -384,7 +385,7 @@ def test_rhvoice_shared_lifecycle_waits_for_nested_feed_and_final_idle(env):
 
 
 def test_rhvoice_shared_cancel_keeps_old_identity_until_retirement(env):
-    assert env.driver._segmentLifecycle is not None
+    assert env.driver._segmentHost._lifecycle is not None
     created = Event()
     original = env.inner.nvwave.WavePlayer
     def blocked_player(**kwargs):
@@ -431,7 +432,7 @@ def test_rhvoice_shared_token_cancel_clears_native_flag_before_successor(env):
 
 
 def test_rhvoice_shared_sink_reenters_terminate(env):
-    assert env.driver._segmentLifecycle is not None
+    assert env.driver._segmentHost._lifecycle is not None
     delivered = Event()
     errors = []
     def sink(event):
@@ -475,7 +476,7 @@ def test_reentrant_successor_during_concurrent_cancel_does_not_deadlock(env):
 
 def test_cancel_invalidates_completion_waiting_for_async_delivery(env, monkeypatch):
     delivery_waiting, release_delivery = Event(), Event()
-    lifecycle = env.driver._segmentLifecycle
+    lifecycle = env.driver._segmentHost._lifecycle
     queue_delivery = lifecycle._queue_delivery_locked
     def delayed_delivery(operation):
         delivery_waiting.set()
@@ -489,9 +490,9 @@ def test_cancel_invalidates_completion_waiting_for_async_delivery(env, monkeypat
     stopper.start()
     try:
         deadline = time.monotonic() + 3
-        while not any(operation._rhvoice_cancelled for operation in env.driver._segmentAccepted) and time.monotonic() < deadline:
+        while not any(env.driver._segmentHost._accepted.values()) and time.monotonic() < deadline:
             time.sleep(0.001)
-        assert any(operation._rhvoice_cancelled for operation in env.driver._segmentAccepted)
+        assert any(env.driver._segmentHost._accepted.values())
     finally:
         release_delivery.set()
     stopper.join(3)
@@ -526,7 +527,7 @@ def test_audio_index_listener_can_cancel_from_its_own_callback_thread(env):
 
 def test_stop_fault_before_deferred_terminal_delivery_fails_closed(env, monkeypatch):
     delivery_waiting, release_delivery = Event(), Event()
-    lifecycle = env.driver._segmentLifecycle
+    lifecycle = env.driver._segmentHost._lifecycle
     queue_delivery = lifecycle._queue_delivery_locked
     def delayed_delivery(operation):
         delivery_waiting.set()
@@ -547,9 +548,9 @@ def test_stop_fault_before_deferred_terminal_delivery_fails_closed(env, monkeypa
     stopper.start()
     try:
         deadline = time.monotonic() + 3
-        while env.driver._segmentControlError is None and time.monotonic() < deadline:
+        while env.driver._segmentHost.control_error is None and time.monotonic() < deadline:
             time.sleep(0.001)
-        assert env.driver._segmentControlError is not None
+        assert env.driver._segmentHost.control_error is not None
     finally:
         release_delivery.set()
     stopper.join(3)
@@ -616,9 +617,9 @@ def test_admitted_late_feed_gets_final_idle_and_index_before_drain(env):
     assert call.returned.wait(3)
     assert player.second_idle_completed.wait(3)
     deadline = time.monotonic() + 3
-    while not speech.closed and time.monotonic() < deadline:
+    while speech.admitting and time.monotonic() < deadline:
         time.sleep(0.001)
-    assert speech.closed
+    assert not speech.admitting
     assert events == []
     assert player.fed == [b"\x01\x00\x02\x00"]
     player.block_idle_number = 3
@@ -668,9 +669,9 @@ def test_admitted_native_mark_can_enter_nested_feed_after_callback_gate_closes(e
     player = env.players[0]
     assert player.second_idle_completed.wait(3)
     deadline = time.monotonic() + 3
-    while not speech.closed and time.monotonic() < deadline:
+    while speech.admitting and time.monotonic() < deadline:
         time.sleep(0.001)
-    assert speech.closed
+    assert not speech.admitting
     assert speech.consumers == 1  # The admitted mark still owns its native lease.
     assert env.native.callbacks.process_mark(b"100", call.user_data) == 0
     assert player.fed == [b"\x01\x00\x02\x00"]
@@ -724,6 +725,25 @@ def test_ordinary_speech_waits_for_contextual_final_idle(env):
     assert len(events) == 1
 
 
+def test_completed_ordinary_speech_does_not_stop_the_player(env):
+    # Ordinary speech reaches every barrier; the host must not stop it.
+    env.native.scripts.extend(({"auto_return": True},) * 3)
+    env.driver.speak(("first",))
+    env.driver.speak(("second",))
+    _, _, events = speak(env, text="segment")
+    assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED
+    assert env.players[0].stops == 0
+
+
+def test_failed_ordinary_speech_stops_the_player(env):
+    # Like the other host engines, a failed ordinary message discards its audio.
+    env.native.scripts.extend(({"auto_return": True, "result": 0}, {"auto_return": True}))
+    env.driver.speak(("failed",))
+    _, _, events = speak(env, text="segment")
+    assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED
+    assert env.players[0].stops == 1
+
+
 def test_speak_after_terminate_fails_through_lifecycle_delivery(env):
     env.driver.terminate()
     env.driver.terminate()  # Repeated terminate must stay idempotent.
@@ -746,6 +766,6 @@ def test_speak_after_terminate_fails_through_lifecycle_delivery(env):
     assert events[0].source_id is context.source_id
     assert events[0].segment_id == 19
     assert str(events[0].error) == "RHVoice driver has terminated"
-    assert threads == [env.driver._segmentLifecycle._delivery_thread.ident]
+    assert threads == [env.driver._segmentHost._lifecycle._delivery_thread.ident]
     assert threads[0] != caller
     assert env.native.calls == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests -q 2>&1 | grep -E "^FAILED|passed|failed" | sed 's/ - .*//'`
Expected: `11 failed, 1332 passed, 96 skipped, 2 xfailed`. The failures:
- `tests/test_lifecycle_private_access.py::test_migrated_wrappers_only_use_the_segment_host`
- `tests/test_rhvoice_segment_drain.py::test_failed_ordinary_speech_stops_the_player`: the approved behavior change.
- Nine coupled reads, each an `AttributeError` for `_segmentHost`:
  - `test_cancel_sees_operation_accepted_before_wrapper_registration`
  - `test_rhvoice_shared_lifecycle_waits_for_nested_feed_and_final_idle`
  - `test_rhvoice_shared_cancel_keeps_old_identity_until_retirement`
  - `test_rhvoice_shared_sink_reenters_terminate`
  - `test_cancel_invalidates_completion_waiting_for_async_delivery`
  - `test_stop_fault_before_deferred_terminal_delivery_fails_closed`
  - `test_admitted_late_feed_gets_final_idle_and_index_before_drain`
  - `test_admitted_native_mark_can_enter_nested_feed_after_callback_gate_closes`
  - `test_speak_after_terminate_fails_through_lifecycle_delivery`

`test_completed_ordinary_speech_does_not_stop_the_player` already passes; mutation M2e proves it bites.

- [ ] **Step 3: Rewrite the RHVoice wrapper**

Save as `$PATCHES/t2-impl.patch`, then run `git apply $PATCHES/t2-impl.patch`:

```diff
diff --git a/addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py b/addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py
index 9cd0a96..4a704dc 100644
--- a/addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py
+++ b/addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py
@@ -1,41 +1,23 @@
 """WorldVoice's context-aware boundary around the vendored RHVoice worker."""
 
-from threading import Condition, Event, RLock, Thread, current_thread, local
+from dataclasses import dataclass
+from threading import Condition, RLock
 import weakref
 
-from logHandler import log
-
 from . import driver as rhvoice
 from synthDrivers.WorldVoice.driver import Voice
-from ...runtime.models import EventKind, PlaybackContext, PlaybackEvent, SegmentEventSink, SpeechCommands
-from ...runtime.playbackWork import PlaybackWork, runtime_profile, unverified_drain_support
+from ...runtime.models import PlaybackContext, SegmentEventSink, SpeechCommands
+from ...runtime.playbackWork import runtime_profile, unverified_drain_support
+from ...runtime.segmentHost import SegmentHost
 from ...runtime.session import CancellationView
-from ...runtime.segmentLifecycle import SegmentLifecycle
-
-
-class _Speech:
-	def __init__(self, work, operation=None):
-		self.work = work
-		self.operation = operation
-		self.boundary = Event() if operation is not None else None
-		self.retired = Event() if operation is not None else None
-		self.handoff = Event() if operation is not None else None
-		self.producer = None
-		self.identity = None
-		self.cancelled = False
-		self.closed = False
-		self.audio_closed = False
-		self.done = False
-		self.returned = False
-		self.final_idle = False
-		self.message_created = False
-		self.error = None
-		self.consumers = 0
-		self.delivering = False
-		self.delivery_thread = None
-
-	def valid(self):
-		return not self.cancelled and (self.work is None or self.work.is_valid())
+
+
+@dataclass(eq=False)
+class _RHVoiceMessage:
+	"""RHVoice data carried on a NativeRecord: its callback identity and library."""
+
+	identity: int
+	library: "_NativeLibrary | None" = None
 
 
 class _NativeCallback:
@@ -56,40 +38,40 @@ class _NativeCallback:
 class _NativeLibrary:
 	"""Observe synchronous native outcomes that SpeakText does not inspect."""
 
-	def __init__(self, owner, native, speech):
+	def __init__(self, owner, native, record):
 		self._owner = weakref.ref(owner)
 		self._native = native
-		self._speech = speech
+		self._record = record
 		self._message = None
 
 	def __getattr__(self, name):
 		return getattr(self._native, name)
 
 	def RHVoice_new_message(self, *args):
-		owner = self._owner()
+		host = self._owner()._segmentHost
 		try:
-			message = self._native.RHVoice_new_message(*args[:-1], self._speech.identity)
+			message = self._native.RHVoice_new_message(*args[:-1], self._record.native.identity)
 			self._message = message
-			self._speech.message_created = bool(message)
-			if not message:
-				owner._record_error(self._speech, RuntimeError("RHVoice did not create a message"))
+			if message:
+				host.reach(self._record, "message")
+			else:
+				host.record_error(self._record, RuntimeError("RHVoice did not create a message"))
 			return message
 		except Exception as error:
-			owner._record_error(self._speech, error)
+			host.record_error(self._record, error)
 			raise
 
 	def RHVoice_speak(self, message):
-		owner = self._owner()
+		host = self._owner()._segmentHost
 		try:
 			result = self._native.RHVoice_speak(message)
 			if not result:
-				owner._record_error(self._speech, RuntimeError("RHVoice synthesis failed"))
+				host.record_error(self._record, RuntimeError("RHVoice synthesis failed"))
 			else:
-				with owner._segmentCondition:
-					self._speech.returned = True
+				host.reach(self._record, "returned")
 			return result
 		except Exception as error:
-			owner._record_error(self._speech, error)
+			host.record_error(self._record, error)
 			raise
 
 	def RHVoice_delete_message(self, message):
@@ -103,11 +85,9 @@ class _NativeLibrary:
 				self._native.RHVoice_delete_message(self._message)
 				self._message = None
 			except Exception as error:
-				owner = self._owner()
-				owner._record_error(self._speech, error)
 				# The native message may still own resources after a failed delete.
 				# Stop reusing this engine and player, even if stop succeeds.
-				owner._record_control_error(error)
+				self._owner()._segmentHost.latch_control_error(error)
 				raise
 
 
@@ -122,151 +102,162 @@ class _WavePlayer:
 		return getattr(self._player, name)
 
 	def feed(self, data, onDone=None):
-		owner = self._owner()
-		admitted = owner._admit_consumer()
-		if admitted is None:
-			return
-		speech, feed_lease = admitted
+		host = self._owner()._segmentHost
+		bound = host.callback_record()
+		if bound is None:
+			return None
+		with host.consumer(bound) as record:
+			if record is None:
+				return None
+
+			def index_done():
+				# The worker's final idle may release this after the native gate closes.
+				with host.consumer(record, audio=True) as admitted:
+					if admitted is None:
+						return
+					with host.bound_callback(record):
+						try:
+							onDone()
+						except Exception as error:
+							host.record_error(record, error)
 
-		def index_done():
-			child = owner._admit_consumer(speech, admitted_audio=True, parent=speech.producer)
-			if child is None:
-				return
-			previous = getattr(owner._segmentLocal, "speech", None)
-			previous_lease = getattr(owner._segmentLocal, "lease", None)
-			owner._segmentLocal.speech = speech
-			owner._segmentLocal.lease = child[1]
 			try:
-				if speech.valid():
-					onDone()
+				return self._player.feed(data, onDone=index_done if onDone else None)
 			except Exception as error:
-				owner._record_error(speech, error)
+				host.record_error(record, error)
+				raise
 			finally:
-				owner._segmentLocal.speech = previous
-				owner._segmentLocal.lease = previous_lease
-				owner._release_consumer(speech, child[1])
-
-		try:
-			return self._player.feed(data, onDone=index_done if onDone else None)
-		except Exception as error:
-			owner._record_error(speech, error)
-			raise
-		finally:
-			try:
-				if not speech.valid():
+				if not record.is_valid():
 					self.stop()
-			finally:
-				owner._release_consumer(speech, feed_lease)
 
 	def idle(self):
-		owner = self._owner()
-		speech = owner._associated_speech()
+		host = self._owner()._segmentHost
+		record = host.callback_record()
 		try:
 			return self._player.idle()
 		except Exception as error:
-			owner._record_error(speech, error)
+			host.record_error(record, error)
 			raise
 
 	def stop(self):
 		try:
 			return self._player.stop()
 		except Exception as error:
-			self._owner()._record_control_error(error)
+			self._owner()._segmentHost.latch_control_error(error)
 			raise
 
 
 class _QueuedSpeech:
-	def __init__(self, owner, speech, task, library):
+	"""One record's turn on the RHVoice worker: native task, final idle, cleanup."""
+
+	def __init__(self, owner, record, task):
 		self._owner = weakref.ref(owner)
-		self._speech = speech
+		self._record = record
 		self._task = task
-		self._library = library
 
 	def __call__(self):
 		owner = self._owner()
 		if owner is None:
 			return
+		host = owner._segmentHost
+		record = self._record
 		with owner._segmentCondition:
-			owner._segmentCondition.wait_for(lambda: self._speech.closed or owner._segmentCancelling == 0)
-			if self._speech.closed:
-				if self._speech.operation is not None:
-					self._speech.boundary.set()
-					if self._speech.producer is not None:
-						owner._segmentLifecycle.retire_producer(self._speech.producer)
-					self._speech.retired.set()
+			owner._segmentCondition.wait_for(lambda: record.closed or owner._segmentCancelling == 0)
+			if record.closed:
+				# NVDA cancel already abandoned this queued record.
 				return
-			owner._segmentCurrent = self._speech
-		owner._segmentLocal.speech = self._speech
-		owner._segmentLocal.lease = self._speech.producer
+			host.begin(record)
 		try:
-			if self._speech.valid() and owner._segmentControlError is None:
-				self._task()
+			if record.is_valid() and host.control_error is None:
+				with host.bound_callback(record):
+					self._task()
 		except Exception as error:
-			owner._record_error(self._speech, error)
-		finally:
-			if self._speech.boundary is not None:
-				self._speech.boundary.set()
-			with owner._segmentCondition:
-				# Stop new native/feed admission, but let callbacks that already
-				# hold a lease finish their player work before the last idle.
-				self._speech.closed = True
-				owner._segmentCondition.wait_for(lambda: self._speech.consumers == 0)
-				self._speech.final_idle = False
-				should_idle = (
-					self._speech.done
-					and self._speech.returned
-					and self._speech.valid()
-					and self._speech.error is None
-					and owner._segmentControlError is None
-				)
-			if should_idle and self._speech.valid():
-				try:
-					owner._SynthDriver__player.idle()
-				except Exception as error:
-					owner._record_error(self._speech, error)
-			with owner._segmentCondition:
-				self._speech.audio_closed = True
-				owner._segmentCondition.wait_for(lambda: self._speech.consumers == 0)
+			host.record_error(record, error)
+		# Stop new native callbacks, but let admitted ones finish their player
+		# work before the final idle.
+		host.close(record)
+		host.wait_consumers(record)
+		if (
+			record.barriers["done"]
+			and record.barriers["returned"]
+			and record.is_valid()
+			and record.error is None
+			and host.control_error is None
+		):
 			try:
-				self._library.cleanup()
+				owner._SynthDriver__player.idle()
+				host.reach(record, "idle")
 			except Exception as error:
-				owner._record_error(self._speech, error)
-			owner._segmentLocal.speech = None
-			owner._segmentLocal.lease = None
-			with owner._segmentCondition:
-				owner._segmentCurrent = None
-				owner._segmentById.pop(self._speech.identity, None)
-				owner._segmentCondition.notify_all()
-			if self._speech.producer is not None:
-				owner._segmentLifecycle.retire_producer(self._speech.producer)
-				self._speech.retired.set()
-				self._speech.handoff.wait()
-				owner._SynthDriver__cancel_flag.clear()
-			else:
-				owner._dispatch(self._speech)
+				host.record_error(record, error)
+		host.retire(record, finish=record.native.library.cleanup)
+		with owner._segmentCondition:
+			owner._segmentById.pop(record.native.identity, None)
+		if record.operation is not None:
+			owner._SynthDriver__cancel_flag.clear()
+		else:
+			host.forget(record)
+
+
+class _RHVoiceStrategy:
+	"""RHVoice's native queue: the inner tts queue and its single worker."""
+
+	barriers = frozenset({"message", "done", "returned", "idle"})
+
+	def __init__(self, driver):
+		self._driver = weakref.ref(driver)
+
+	def submit(self, host, record, commands):
+		driver = self._driver()
+		with driver._segmentCondition:
+			identity = driver._segmentNextId
+			driver._segmentNextId += 1
+			record.native = _RHVoiceMessage(identity)
+			driver._segmentById[identity] = record
+		try:
+			converter = rhvoice.SsmlConverter(driver, driver.language)
+			text = converter.convertToXml(commands)
+			library = record.native.library = _NativeLibrary(driver, driver._SynthDriver__lib, record)
+			task = rhvoice.SpeakText(
+				library,
+				driver._SynthDriver__tts_engine,
+				text,
+				driver._SynthDriver__cancel_flag,
+				driver._SynthDriver__player,
+			)
+			task.set_voice_profile(driver._SynthDriver__profile)
+			task.set_rate(driver._SynthDriver__rate)
+			task.set_pitch(driver._SynthDriver__pitch)
+			task.set_volume(driver._SynthDriver__volume)
+			task.configure_rate_boost(driver._SynthDriver__rate_boost)
+			driver._SynthDriver__tts_queue.put(_QueuedSpeech(driver, record, task))
+		except Exception:
+			with driver._segmentCondition:
+				driver._segmentById.pop(identity, None)
+			raise
+
+	def stop_native(self, host, record):
+		driver = self._driver()
+		driver._SynthDriver__cancel_flag.set()
+		driver._SynthDriver__player.stop()
+
+	def stop_player(self, host):
+		self._driver()._SynthDriver__player.stop()
 
 
 class SynthDriver(rhvoice.SynthDriver):
 	"""Retain RHVoice's single worker and observe its actual completion barriers."""
 
 	def __init__(self):
+		self._segmentHost = SegmentHost(
+			"RHVoice", _RHVoiceStrategy(self), fail_accepted_on_control_error=True
+		)
 		self._segmentCondition = Condition(RLock())
-		self._segmentAdmission = RLock()
-		self._segmentLocal = local()
-		self._segmentCurrent = None
-		self._segmentPending = []
 		self._segmentById = {}
 		self._segmentNextId = 1
-		self._segmentControlError = None
 		self._segmentCancelling = 0
-		self._segmentTerminated = False
-		self._segmentLifecycle = SegmentLifecycle(self)
-		self._segmentOperations = {}
-		self._segmentAccepted = set()
 		super().__init__()
 		player = self._SynthDriver__player
 		original_get_player = player.get_player
-		original_idle = player.idle
 		wrapped = {}
 
 		def get_player():
@@ -277,21 +268,7 @@ class SynthDriver(rhvoice.SynthDriver):
 				wrapped[real] = _WavePlayer(self, real)
 			return wrapped[real]
 
-		def idle():
-			speech = self._associated_speech()
-			try:
-				result = original_idle()
-				if speech is not None:
-					with self._segmentCondition:
-						if speech.returned:
-							speech.final_idle = True
-				return result
-			except Exception as error:
-				self._record_error(speech, error)
-				raise
-
 		player.get_player = get_player
-		player.idle = idle
 
 	def __setattr__(self, name, value):
 		# Inner init creates C callbacks just after assigning Python callables.
@@ -305,131 +282,27 @@ class SynthDriver(rhvoice.SynthDriver):
 		super().__setattr__(name, value)
 
 	def _native_callback(self, callback, is_done, *args):
+		host = self._segmentHost
 		identity = args[-1]
 		with self._segmentCondition:
-			speech = self._segmentById.get(identity)
-			if speech is None or speech is not self._segmentCurrent or speech.closed or not speech.valid():
-				return None if is_done else 0
-			speech.consumers += 1
-			lease = (
-				self._segmentLifecycle.admit_producer(speech.operation, speech.producer)
-				if speech.operation is not None
-				else None
-			)
-		previous = getattr(self._segmentLocal, "speech", None)
-		previous_native = getattr(self._segmentLocal, "native_speech", None)
-		previous_lease = getattr(self._segmentLocal, "lease", None)
-		self._segmentLocal.speech = speech
-		self._segmentLocal.native_speech = speech
-		self._segmentLocal.lease = lease
-		try:
-			result = callback(*args)
-			if is_done:
-				with self._segmentCondition:
-					speech.done = True
-			elif not result:
-				self._record_error(speech, RuntimeError("RHVoice callback failed"))
-			return result
-		except Exception as error:
-			self._record_error(speech, error)
-			return None if is_done else 0
-		finally:
-			self._segmentLocal.speech = previous
-			self._segmentLocal.native_speech = previous_native
-			self._segmentLocal.lease = previous_lease
-			self._release_consumer(speech, lease)
-
-	def _associated_speech(self):
-		return getattr(self._segmentLocal, "speech", None)
-
-	def _admit_consumer(self, speech=None, *, admitted_audio=False, parent=None):
-		with self._segmentCondition:
-			speech = speech or self._associated_speech()
-			# A native callback already holding a lease may start its nested feed
-			# after retirement closes admission to new native callbacks.
-			if (
-				speech is None
-				or speech is not self._segmentCurrent
-				or not speech.valid()
-				or speech.audio_closed
-				or (
-					speech.closed
-					and not admitted_audio
-					and getattr(self._segmentLocal, "native_speech", None) is not speech
-				)
-			):
-				return None
-			speech.consumers += 1
-			lease = None
-			if speech.operation is not None:
-				parent = parent or getattr(self._segmentLocal, "lease", None)
-				lease = self._segmentLifecycle.admit_producer(speech.operation, parent)
-				if lease is None:
-					speech.consumers -= 1
-					return None
-			return speech, lease
-
-	def _release_consumer(self, speech, lease=None):
-		if lease is not None:
-			self._segmentLifecycle.retire_producer(lease)
-		with self._segmentCondition:
-			speech.consumers -= 1
-			self._segmentCondition.notify_all()
-
-	def _record_error(self, speech, error):
-		with self._segmentCondition:
-			if speech is not None and speech.error is None:
-				speech.error = error
-
-	def _record_control_error(self, error):
-		with self._segmentCondition:
-			if self._segmentControlError is None:
-				self._segmentControlError = error
-			for speech in self._segmentPending:
-				if speech.error is None:
-					speech.error = self._segmentControlError
-			for operation in tuple(self._segmentAccepted):
-				self._segmentLifecycle.fail(operation, self._segmentControlError)
-
-	def _dispatch(self, speech):
-		work = speech.work
-		if work is None or not work.is_valid():
-			with self._segmentCondition:
-				if speech in self._segmentPending:
-					self._segmentPending.remove(speech)
-				self._segmentCondition.notify_all()
-			return
-
-		def deliver():
-			with self._segmentCondition:
-				if speech not in self._segmentPending or not work.is_valid():
-					if speech in self._segmentPending:
-						self._segmentPending.remove(speech)
-					self._segmentCondition.notify_all()
-					return
-				speech.delivering = True
-				speech.delivery_thread = current_thread()
-				error = speech.error or self._segmentControlError
-				if error is None and not (
-					speech.done and speech.returned and speech.final_idle and speech.message_created
-				):
-					error = RuntimeError("RHVoice segment ended without all completion barriers")
-			try:
-				if error is None:
-					work.complete_drained()
-				else:
-					work.fail(error)
-			except Exception:
-				log.error("RHVoice segment event sink", exc_info=True)
-			finally:
-				with self._segmentCondition:
-					speech.delivering = False
-					speech.delivery_thread = None
-					if speech in self._segmentPending:
-						self._segmentPending.remove(speech)
-					self._segmentCondition.notify_all()
-
-		Thread(target=deliver, daemon=True, name="RHVoice segment event").start()
+			record = self._segmentById.get(identity)
+		refused = None if is_done else 0
+		if record is None:
+			return refused
+		with host.consumer(record) as admitted:
+			if admitted is None:
+				return refused
+			with host.bound_callback(record):
+				try:
+					result = callback(*args)
+					if is_done:
+						host.reach(record, "done")
+					elif not result:
+						host.record_error(record, RuntimeError("RHVoice callback failed"))
+					return result
+				except Exception as error:
+					host.record_error(record, error)
+					return refused
 
 	def get_segment_drain_support(self, *, nvda_version=None, audio_mode=None):
 		return unverified_drain_support(
@@ -445,243 +318,36 @@ class SynthDriver(rhvoice.SynthDriver):
 		context: PlaybackContext,
 		on_event: SegmentEventSink,
 	):
-		def deliver(event):
-			try:
-				if (
-					not operation._rhvoice_cancelled
-					and not token.is_cancelled()
-					and not self._segmentTerminated
-				):
-					with self._segmentCondition:
-						control_error = self._segmentControlError
-					if control_error is not None and event.kind is EventKind.SEGMENT_DRAINED:
-						event = PlaybackEvent(
-							EventKind.SEGMENT_FAILED,
-							event.source_id,
-							segment_id=event.segment_id,
-							error=control_error,
-						)
-					on_event(event)
-			finally:
-				with self._segmentCondition:
-					self._segmentAccepted.discard(operation)
-
-		with self._segmentAdmission:
-			with self._segmentCondition:
-				terminated = self._segmentTerminated
-				control_error = self._segmentControlError
-			if terminated:
-				self._segmentLifecycle.reject_new(
-					context,
-					token,
-					on_event,
-					RuntimeError("RHVoice driver has terminated"),
-				)
-				return
-			if control_error is not None:
-				self._segmentLifecycle.reject_new(context, token, on_event, control_error)
-				return
-			operation = self._segmentLifecycle.accept(context, token, deliver)
-			operation._rhvoice_cancelled = False
-			with self._segmentCondition:
-				self._segmentAccepted.add(operation)
-
-		def run():
-			self._run_segment(operation, tuple(commands))
-
-		Thread(
-			target=run,
-			name="WorldVoice RHVoice lifecycle",
-			daemon=True,
-		).start()
-
-	def _run_segment(self, operation, commands):
-		try:
-			self._segmentLifecycle.run(operation, commands)
-		except Exception as error:
-			self._segmentLifecycle.reject_new(
-				operation.work.context,
-				operation.work.token,
-				lambda event: None if operation._rhvoice_cancelled else operation.sink(event),
-				self._segmentControlError or error.__cause__ or error,
-			)
-		finally:
-			with self._segmentCondition:
-				speech = self._segmentOperations.pop(operation, None)
-				if speech in self._segmentPending:
-					self._segmentPending.remove(speech)
-				if operation._rhvoice_cancelled or operation.work.token.is_cancelled():
-					self._segmentAccepted.discard(operation)
-			if speech is not None:
-				speech.handoff.set()
-
-	def submit_native(self, operation, commands):
-		self._queue_speech(commands, operation.work, operation)
-
-	def request_stop(self, operation):
-		with self._segmentCondition:
-			speech = self._segmentOperations.get(operation)
-			if speech is None:
-				return
-			speech.cancelled = True
-			active = speech is self._segmentCurrent
-		if active:
-			self._SynthDriver__cancel_flag.set()
-			self._SynthDriver__player.stop()
-
-	def wait_native_boundary(self, operation):
-		with self._segmentCondition:
-			speech = self._segmentOperations.get(operation)
-		if speech is not None:
-			speech.boundary.wait()
-
-	def wait_native_retired(self, operation):
-		with self._segmentCondition:
-			speech = self._segmentOperations.get(operation)
-		if speech is None:
-			return
-		speech.retired.wait()
-		if speech.error is not None:
-			self._segmentLifecycle.fail(operation, speech.error)
-
-	def wait_playback_drained(self, operation):
-		with self._segmentCondition:
-			speech = self._segmentOperations.get(operation)
-		if speech is None:
-			return
-		if not operation.work.is_valid() or speech.error is not None:
-			self._SynthDriver__player.stop()
-			return
-		if not (speech.message_created and speech.done and speech.returned and speech.final_idle):
-			self._segmentLifecycle.fail(
-				operation,
-				RuntimeError(
-					"RHVoice segment ended without all completion barriers",
-				),
-			)
-			self._SynthDriver__player.stop()
+		self._segmentHost.speak_segment(commands, token, context=context, on_event=on_event)
 
 	def speak(self, speechSequence):
-		self._queue_speech(speechSequence, None)
-
-	def _queue_speech(self, commands, work, operation=None):
-		with self._segmentAdmission:
-			if self._segmentTerminated or (work is not None and not work.is_valid()):
-				if work is not None:
-					work.cancel()
-				return
-			speech = _Speech(work, operation)
-			with self._segmentCondition:
-				control_error = self._segmentControlError
-				self._segmentPending.append(speech)
-				if operation is not None:
-					self._segmentOperations[operation] = speech
-				if control_error is not None:
-					speech.error = control_error
-				else:
-					speech.identity = self._segmentNextId
-					self._segmentNextId += 1
-					self._segmentById[speech.identity] = speech
-			if control_error is not None:
-				if operation is not None:
-					self._segmentLifecycle.fail(operation, control_error)
-					speech.boundary.set()
-					speech.retired.set()
-					with self._segmentCondition:
-						self._segmentPending.remove(speech)
-				else:
-					with self._segmentCondition:
-						self._segmentPending.remove(speech)
-					raise control_error
-				return
-			if operation is not None:
-				speech.producer = self._segmentLifecycle.admit_producer(operation)
-				if speech.producer is None:
-					with self._segmentCondition:
-						self._segmentById.pop(speech.identity, None)
-						self._segmentPending.remove(speech)
-						self._segmentOperations.pop(operation, None)
-					return
-			try:
-				converter = rhvoice.SsmlConverter(self, self.language)
-				text = converter.convertToXml(commands)
-				lib = _NativeLibrary(self, self._SynthDriver__lib, speech)
-				task = rhvoice.SpeakText(
-					lib,
-					self._SynthDriver__tts_engine,
-					text,
-					self._SynthDriver__cancel_flag,
-					self._SynthDriver__player,
-				)
-				task.set_voice_profile(self._SynthDriver__profile)
-				task.set_rate(self._SynthDriver__rate)
-				task.set_pitch(self._SynthDriver__pitch)
-				task.set_volume(self._SynthDriver__volume)
-				task.configure_rate_boost(self._SynthDriver__rate_boost)
-				self._SynthDriver__tts_queue.put(_QueuedSpeech(self, speech, task, lib))
-			except Exception:
-				with self._segmentCondition:
-					self._segmentById.pop(speech.identity, None)
-					self._segmentPending.remove(speech)
-					self._segmentOperations.pop(operation, None)
-				if speech.producer is not None:
-					self._segmentLifecycle.retire_producer(speech.producer)
-				raise
+		self._segmentHost.enqueue(speechSequence)
 
 	def cancel(self):
-		with self._segmentAdmission:
-			with self._segmentCondition:
-				operations = tuple(self._segmentAccepted)
-			for operation in operations:
-				operation._rhvoice_cancelled = True
-				self._segmentLifecycle.cancel(operation)
+		host = self._segmentHost
+		with host.admission():
+			host.cancel()
 			with self._segmentCondition:
 				self._segmentCancelling += 1
-				current = self._segmentCurrent
-				callback_origin = self._associated_speech() is not None
-				in_delivery = any(
-					speech.delivery_thread is current_thread() for speech in self._segmentPending
-				)
-				deliveries = tuple(
-					speech
-					for speech in self._segmentPending
-					if speech.delivering and speech.delivery_thread is not current_thread()
-				)
-				for speech in tuple(self._segmentPending):
-					speech.cancelled = True
-					if speech.work is not None:
-						speech.work.cancel()
-					if speech is not current and not speech.delivering:
-						speech.closed = True
-						if speech.operation is not None:
-							speech.boundary.set()
-							if speech.producer is not None:
-								self._segmentLifecycle.retire_producer(speech.producer)
-							speech.retired.set()
-						self._segmentById.pop(speech.identity, None)
-						self._segmentPending.remove(speech)
+				current = host.current()
+				dropped = [record for record in self._segmentById.values() if record is not current]
+				for record in dropped:
+					self._segmentById.pop(record.native.identity, None)
+			# Queued records never reach the worker; the inner cancel clears them.
+			for record in dropped:
+				host.abandon(record)
 			error = None
 			try:
 				super().cancel()
 			except Exception as exc:
-				self._record_control_error(exc)
+				host.latch_control_error(exc)
 				error = exc
 		try:
-			with self._segmentCondition:
-				# Legacy done listeners can call cancel from inside the native
-				# callback. That callback itself holds the retirement lease.
-				if current is not None and self._associated_speech() is not current:
-					self._segmentCondition.wait_for(lambda: self._segmentCurrent is not current)
-				# A delivery sink may be waiting for this native/audio callback
-				# to retire. The callback must not wait for that delivery in turn.
-				if not in_delivery and not callback_origin:
-					self._segmentCondition.wait_for(
-						lambda: all(not speech.delivering for speech in deliveries),
-					)
+			host.wait_settled(current)
 			try:
 				self._SynthDriver__player.stop()
 			except Exception as exc:
-				self._record_control_error(exc)
+				host.latch_control_error(exc)
 				if error is None:
 					error = exc
 		finally:
@@ -692,11 +358,10 @@ class SynthDriver(rhvoice.SynthDriver):
 			raise error
 
 	def terminate(self):
-		with self._segmentAdmission:
+		with self._segmentHost.admission():
 			if self._SynthDriver__tts_engine is None:
 				return
-			self._segmentTerminated = True
-			self._segmentLifecycle.terminate()
+			self._segmentHost.terminate()
 		error = None
 		try:
 			self.cancel()
```

- [ ] **Step 4: Run the tests and the acceptance checks**

Run: `python3 -m pytest tests -q 2>&1 | tail -1`
Expected: `1343 passed, 96 skipped, 2 xfailed`

Run: `for i in 1 2 3; do python3 -m pytest tests/test_rhvoice_segment_drain.py -q 2>&1 | tail -1; done | sed 's/ in .*//'`
Expected: `34 passed` three times.

Run:
```bash
R=addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py
ruff format --check addon | tail -1
grep -n "_segmentLifecycle\|SegmentLifecycle" $R
```
Expected: `53 files already formatted`, then no grep output.

- [ ] **Step 5: Commit**

```bash
git add addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py tests/test_rhvoice_segment_drain.py \
	tests/test_lifecycle_private_access.py
git commit -m "refactor(rhvoice): run segments through SegmentHost

A failed ordinary utterance now stops the player, as on the other host
engines.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Prove the RHVoice wrapper bites (mutations M2a–M2e, after the commit)**

```bash
R=addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py
mutate() { python3 - "$1" "$2" <<'PY'
import sys
p = "addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py"
old, new = sys.argv[1:]
s = open(p).read()
assert s.count(old) == 1, old
open(p, "w").write(s.replace(old, new))
PY
}
check() { timeout 300 python3 -m pytest tests/test_rhvoice_segment_drain.py -q -p no:cacheprovider 2>&1 | grep -E '^FAILED|passed|failed' | sed 's/ - .*//'; git checkout -- $R; }

mutate '				with host.consumer(record, audio=True) as admitted:' '				with host.consumer(record) as admitted:'; check   # M2a
mutate '		host.retire(record, finish=record.native.library.cleanup)' '		host.retire(record)'; check   # M2b
mutate '			host.wait_settled(current)' '			pass'; check   # M2c
mutate 'fail_accepted_on_control_error=True' 'fail_accepted_on_control_error=False'; check   # M2d
mutate '				host.reach(record, "idle")' '				pass'; check   # M2e
git status --short | grep addon
```

Expected:
- M2a: index callbacks lose their after-close admission. `2 failed, 32 passed`:
  - `test_admitted_late_feed_gets_final_idle_and_index_before_drain`
  - `test_admitted_native_mark_can_enter_nested_feed_after_callback_gate_closes`
- M2b: the message is never deleted. `7 failed, 27 passed`:
  - `test_done_before_native_return_waits_for_final_idle_and_retirement`
  - `test_message_delete_failure_fails_closed_for_contextual_and_legacy_successors`
  - `test_swallowed_native_and_audio_failures_never_publish_success[native]`, `[result]`, `[feed]` and `[idle]`
  - `test_message_cleanup_waits_for_admitted_native_callback`
- M2c: cancel does not settle. `1 failed, 33 passed`: `test_cancel_waits_for_admitted_feed_and_stops_late_audio_before_successor`
- M2d: RHVoice does not opt in. `1 failed, 33 passed`: `test_stop_fault_before_deferred_terminal_delivery_fails_closed`
- M2e: the worker never reaches `idle`. `15 failed, 19 passed`. Every drain fails with `RHVoice synthesis retired without its idle barriers`. The failures include:
  - `test_completed_ordinary_speech_does_not_stop_the_player`
  - `test_failed_ordinary_speech_stops_the_player`
  - `test_ordinary_speech_waits_for_contextual_final_idle`

The final `git status` prints nothing.

---

### Task 3: Final verification

**Files:** none modified.

- [ ] **Step 1: Stability**

Run: `for i in 1 2 3 4 5; do python3 -m pytest tests/test_rhvoice_segment_drain.py tests/test_segment_host.py tests/test_segment_lifecycle.py tests/test_engine_segment_contract.py tests/test_espeak_segment_drain.py tests/test_sapi5_segment_drain.py -q 2>&1 | tail -1; done | sed 's/ in .*//' | sort | uniq -c`
Expected: one line, `5 229 passed, 4 skipped, 2 xfailed`.

- [ ] **Step 2: The other engines are untouched and green**

Run: `git diff master --stat -- addon/synthDrivers/WorldVoice/driver/OneCore addon/synthDrivers/WorldVoice/driver/VE addon/synthDrivers/WorldVoice/driver/Cerence addon/synthDrivers/WorldVoice/driver/Espeak addon/synthDrivers/WorldVoice/driver/SAPI5`
Expected: no output.

Run: `python3 -m pytest tests/test_onecore_segment_drain.py tests/test_vocalizer_segment_drain.py -q 2>&1 | tail -1`
Expected: `220 passed, 9 skipped`.

Run: `python3 -m pytest tests/test_engine_segment_contract.py -q -rx 2>&1 | grep -E "XFAIL|passed"`
Expected: `XFAIL` lines for `[VE]` and `[Cerence]` only, then `22 passed, 4 skipped, 2 xfailed`.

- [ ] **Step 3: Full suite and protected paths**

Run: `python3 -m pytest tests -q 2>&1 | tail -1`
Expected: `1343 passed, 96 skipped, 2 xfailed`

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
  1. `docs: add phase 3b-2 RHVoice migration design spec`
  2. `docs: add phase 3b-2 implementation plan and amend its spec`
  3. `feat(runtime): retire finish, audio consumers, settled cancel and opt-in accepted failure`
  4. `refactor(rhvoice): run segments through SegmentHost`
