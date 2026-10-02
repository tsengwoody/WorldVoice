# Phase 3c: OneCore Migration to SegmentHost Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the runtime the two mechanisms OneCore needs, then move the OneCore wrapper onto `SegmentHost` (approach A: a segment enters OneCore's queue only when its predecessor drains).

**Architecture:**
- **Task 1 (shared runtime):**
  - New optional `NativeStrategy.prepare(host, commands, operation)` hook. `enqueue` calls it before taking host admission, so SSML conversion never blocks `cancel()`/`terminate()`.
  - `SegmentLifecycle.fail()` publishes FAILED synchronously for an operation that has not acquired the resource: one not yet run, or one waiting in `run()`. Its `run()` then returns without doing anything. This keeps master OneCore's "a control error fails queued segments at once" ordering.
- **Task 2 (OneCore):**
  - `_OneCoreStrategy` provides `admission_error`, `prepare`, `submit`, `stop_native`, `stop_player` and `drain` (sync plus pause wait).
  - The outer worker keeps OneCore's ordered `_queuedSpeech` of setting tuples, ordinary text and segment records.
  - `_DetachableCallback` keeps the fixed native pointer.
  - Pause handling and two-phase control-failure capture/deliver stay. The wrapper goes from 686 to 601 lines.
- VE, Cerence, eSpeak, SAPI5 and RHVoice wrappers are untouched.

**Tech Stack:** Python 3 threading, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-10-02-phase3c-onecore-design.md`

## Global Constraints

- Work on branch `phase3c-onecore`, cut from `master` at `499a8a2`. The spec commit `dde45e6` and the plan commit are on it.
- **Do not change** `addon/synthDrivers/WorldVoice/driver/{VE,Cerence,Espeak,SAPI5,RHVoice}/__init__.py`. Their tests must pass, and VE/Cerence contract 4 stays xfail.
- Never modify `driver/<Engine>/driver/` and never commit `driver/Neural/`. Neural compatibility is not required.
- No shared VE/Cerence code. Code shared by all engines lives only in `runtime/`.
- New public names are snake_case.
- Every changed `addon/` file passes `ruff format --check`; `tests/test_segment_host.py` passes `ruff check`.
- Run from `/workspace/WorldVoice`, since tests need the untracked `ref/`. Stage explicit paths only; never stage the user's unstaged deletion of `docs/superpowers/finish_task.md`.
- Baseline before Task 1: `python3 -m pytest tests -q` → `1343 passed, 96 skipped, 2 xfailed`.
- Each code step applies a patch saved verbatim from this plan: set `PATCHES=$(mktemp -d)` once, save the block to the named file, then run `git apply`.
- **Mutation steps come after the commit step.** They end with `git checkout -- <file>`, which would otherwise discard uncommitted work; this happened in phases 2 and 3a.
- Every commit message ends with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **The approved settings-order change (approach A).** A rate/volume change made while a segment waits for its predecessor applies to that segment. Ordinary `speak()` text and settings keep call order.
   - Pinned by `test_setting_changed_while_a_segment_waits_applies_before_it` (M2a) and `test_ordinary_speech_and_settings_keep_call_order`.
   - Check that no other ordering changes slipped in, for example settings dropped by `cancel()` (they must keep their queue position) or by a control error (master clears them).
2. **Synchronous `fail()` publication for every engine.** A failed operation that has not acquired the resource is now published at once.
   - Check that no engine relied on a failed waiting operation reaching `submit_native` or `wait_playback_drained`.
   - Check that the operation's thread in `SegmentHost._run` handles `run()` returning early, so no second FAILED comes from `reject_new`.
   - Covered by `test_failed_waiting_operation_is_published_before_the_resource_frees` (M1d) and `test_failed_operation_that_never_ran_is_published_and_its_run_is_a_no_op` (M1e, M1g).
   - The waiting-loop `_retired` check is defensive: mutant M1f is equivalent, because `_run_owned` returns on the error and the event holder is already empty.
3. **A segment queued behind ordinary speech.** Under approach A, this is the only state in which a segment record waits in `_queuedSpeech`. Cancel and a control error must abandon it, or its lifecycle waits forever and every later segment is stuck.
   - Covered by `test_cancel_releases_a_segment_queued_behind_ordinary_speech` (M2c) and `test_control_error_fails_a_segment_queued_behind_ordinary_speech` (M2b).
4. **Lock order.** The worker holds `_segmentCondition` while calling `host.begin`/`host.abandon` (engine → host). Control-failure capture calls `host.latch_control_error` under `_segmentCondition`; that call reaches `lifecycle.fail` (engine → lifecycle).
   - `prepare` runs with no lock held.
   - The reviewer checks by reading that no path takes `_segmentCondition` while holding the host or lifecycle condition. That includes `drain`, which waits on `_segmentCondition` from the lifecycle thread.
5. **Rare test flake to look for.** During prototyping, the OneCore file failed once in about 230 runs, and the failing test was not captured.
   - The earlier, reproducible flake in `test_control_error_fails_queued_contexts_and_allows_reentrant_cancel` (2/60) was the race fixed by synchronous `fail()` publication; it then passed 100/100.
   - The reviewer should look for remaining wake-order races between the worker, the native callback thread, lifecycle threads and the delivery thread.

---

### Task 1: Prepare hook and synchronous failure publication

Spec §1. No engine wrapper changes; every engine's tests must pass.

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/runtime/segmentHost.py` (`enqueue` calls the optional `prepare` before admission; protocol comment)
- Modify: `addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py` (`SegmentOperation._waiting`, `run()`, `fail()`)
- Modify: `tests/test_segment_host.py` (`PreparingStrategy`, `prepare_env` fixture, 4 tests)
- Modify: `tests/test_segment_lifecycle.py` (2 tests)

**Interfaces:**
- Consumes: the 3b-2 host and lifecycle at `499a8a2`.
- Produces (Task 2 relies on these exact names):
  - Optional `NativeStrategy.prepare(host, commands, operation) -> commands`:
    - `host.enqueue` calls it outside host admission, before the record exists, and passes the result to `submit`.
    - If it raises for a segment, the host calls `lifecycle.fail(operation, error)` and returns. For ordinary speech, the error is re-raised.
  - `SegmentLifecycle.fail(operation, error)`:
    - If the operation has not run, or is waiting in `run()` for the resource, it publishes FAILED immediately (reject plus delivery) and returns. It does not start a stop.
    - `run()` of such an operation returns without submitting.

- [ ] **Step 1: Write the failing tests**

Save as `$PATCHES/t1-tests.patch`, then run `git apply $PATCHES/t1-tests.patch`:

```diff
diff --git a/tests/test_segment_host.py b/tests/test_segment_host.py
index 4f869d3..6bcc7eb 100644
--- a/tests/test_segment_host.py
+++ b/tests/test_segment_host.py
@@ -874,3 +874,77 @@ def test_control_error_and_the_active_segment(env, stopped):
 		assert not wait_until(lambda: bool(env.strategy.native_stops), 0.2)
 	env.run_native(record)
 	assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_FAILED
+
+
+class PreparingStrategy(FakeStrategy):
+	"""A strategy that converts commands in prepare() before submission."""
+
+	def __init__(self):
+		super().__init__()
+		self.prepare_entered = Event()
+		self.prepare_release = Event()
+		self.prepare_release.set()
+		self.prepare_error = None
+
+	def prepare(self, host, commands, operation):
+		self.prepare_entered.set()
+		assert self.prepare_release.wait(2), "Test did not release prepare"
+		if self.prepare_error is not None:
+			raise self.prepare_error
+		return ("prepared", *commands)
+
+
+@pytest.fixture
+def prepare_env(env):
+	strategy = PreparingStrategy()
+	env.host._strategy = strategy
+	env.strategy = strategy
+	return env
+
+
+def test_prepare_result_is_what_submit_receives(prepare_env):
+	env = prepare_env
+	env.speak()
+	record = env.strategy.wait_submitted()
+	assert env.strategy.submitted[0][1] == ("prepared", "hello")
+	env.host.enqueue(("ordinary",))
+	env.strategy.wait_submitted(2)
+	assert env.strategy.submitted[1][1] == ("prepared", "ordinary")
+	env.run_native(record)
+
+
+def test_cancel_does_not_wait_for_prepare(prepare_env):
+	env = prepare_env
+	env.strategy.prepare_release.clear()
+	_, _, events = env.speak()
+	assert env.strategy.prepare_entered.wait(1)
+	cancelled = Event()
+	Thread(target=lambda: (env.host.cancel(), cancelled.set()), daemon=True).start()
+	try:
+		assert cancelled.wait(1), "cancel() waited for prepare()"
+	finally:
+		env.strategy.prepare_release.set()
+	with events.condition:
+		assert not events.condition.wait_for(lambda: bool(events), 0.2)
+	assert env.strategy.submitted == []
+
+
+def test_segment_prepare_error_fails_only_that_segment(prepare_env):
+	env = prepare_env
+	env.strategy.prepare_error = ValueError("conversion failed")
+	_, _, failed = env.speak()
+	event = failed.wait_one()
+	assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
+	assert isinstance(event.error, ValueError)
+	env.strategy.prepare_error = None
+	_, _, events = env.speak(segment=18)
+	env.run_native(env.strategy.wait_submitted())
+	assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED
+
+
+def test_ordinary_prepare_error_is_raised(prepare_env):
+	env = prepare_env
+	env.strategy.prepare_error = ValueError("conversion failed")
+	with pytest.raises(ValueError, match="conversion failed"):
+		env.host.enqueue(("ordinary",))
+	assert env.strategy.submitted == []
diff --git a/tests/test_segment_lifecycle.py b/tests/test_segment_lifecycle.py
index f7440ef..1556b2f 100644
--- a/tests/test_segment_lifecycle.py
+++ b/tests/test_segment_lifecycle.py
@@ -299,6 +299,40 @@ def test_failed_queued_operation_never_submits(env):
     assert failed[0].kind.value == "segment_failed"
 
 
+def test_failed_waiting_operation_is_published_before_the_resource_frees(env):
+    lifecycle, hooks, events, accept = env
+    old, _ = accept(1)
+    queued, context = accept(2)
+    first = Call(lambda: lifecycle.run(old, ("old",)))
+    assert hooks.boundary_entered.wait(1)
+    second = Call(lambda: lifecycle.run(queued, ("queued",)))
+    second.blocked()
+    lifecycle.fail(queued, RuntimeError("control error"))
+    second.finish()
+    events.wait_for_count(1)
+    assert [(event.source_id, event.kind.value) for event in events] == [
+        (context.source_id, "segment_failed")]
+    assert len(hooks.submitted) == 1
+    hooks.release_boundary.set()
+    first.finish()
+    events.wait_for_count(2)
+    with events._condition:
+        assert not events._condition.wait_for(lambda: len(events) > 2, 0.1), events
+
+
+def test_failed_operation_that_never_ran_is_published_and_its_run_is_a_no_op(env):
+    lifecycle, hooks, events, accept = env
+    operation, context = accept(5)
+    lifecycle.fail(operation, RuntimeError("control error"))
+    events.wait_for_count(1)
+    assert [(event.source_id, event.kind.value) for event in events] == [
+        (context.source_id, "segment_failed")]
+    Call(lambda: lifecycle.run(operation, ("never",))).finish()
+    assert hooks.submitted == []
+    with events._condition:
+        assert not events._condition.wait_for(lambda: len(events) > 1, 0.1), events
+
+
 def test_late_cancel_cannot_stop_successor_resource(env):
     lifecycle, hooks, events, accept = env
     old, _ = accept(1)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests -q 2>&1 | grep -E "^FAILED|passed|failed" | sed 's/ - .*//'`
Expected: `6 failed, 1343 passed, 96 skipped, 2 xfailed`:
- `tests/test_segment_host.py::test_prepare_result_is_what_submit_receives`
- `tests/test_segment_host.py::test_cancel_does_not_wait_for_prepare`
- `tests/test_segment_host.py::test_segment_prepare_error_fails_only_that_segment`
- `tests/test_segment_host.py::test_ordinary_prepare_error_is_raised`
- `tests/test_segment_lifecycle.py::test_failed_waiting_operation_is_published_before_the_resource_frees`
- `tests/test_segment_lifecycle.py::test_failed_operation_that_never_ran_is_published_and_its_run_is_a_no_op`

- [ ] **Step 3: Implement**

Save as `$PATCHES/t1-impl.patch`, then run `git apply $PATCHES/t1-impl.patch`:

```diff
diff --git a/addon/synthDrivers/WorldVoice/runtime/segmentHost.py b/addon/synthDrivers/WorldVoice/runtime/segmentHost.py
index 3b481c4..c5b3495 100644
--- a/addon/synthDrivers/WorldVoice/runtime/segmentHost.py
+++ b/addon/synthDrivers/WorldVoice/runtime/segmentHost.py
@@ -83,6 +83,11 @@ class NativeStrategy(Protocol):
 	def stop_player(self, host: "SegmentHost") -> None:
 		"""Discard queued audio; used after cancellation or failure."""
 
+	# Optional: def prepare(self, host, commands, operation) -> SpeechCommands
+	# Called by enqueue() outside host admission before the record exists; it
+	# returns what submit() receives. A raised error fails the segment (or is
+	# raised to an ordinary caller).
+	#
 	# Optional: def admission_error(self, host) -> Exception | None
 	# Called under host admission before a segment is accepted; a returned error
 	# rejects the segment (e.g. an audio route that cannot drain).
@@ -186,6 +191,17 @@ class SegmentHost:
 	) -> None:
 		"""Queue native work; ordinary speech passes no operation."""
 		work = operation.work if operation is not None else None
+		prepare = getattr(self._strategy, "prepare", None)
+		if prepare is not None:
+			# Engine preparation (e.g. SSML conversion) runs outside admission so
+			# cancel() and terminate() never wait for it.
+			try:
+				commands = prepare(self, commands, operation)
+			except Exception as error:
+				if operation is None:
+					raise
+				self._lifecycle_of(operation).fail(operation, error)
+				return
 		record = self.new_record(operation, barriers=barriers, native=native)
 		with self._admission:
 			if self._terminated:
diff --git a/addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py b/addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py
index f75eed9..b27bbe6 100644
--- a/addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py
+++ b/addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py
@@ -65,6 +65,8 @@ class SegmentOperation:
 		self._playback_verified = False
 		self._playback_stop_done: Event | None = None
 		self._run_started = False
+		# True while run() waits for the resource; fail() may then publish it.
+		self._waiting = False
 		self._retired = False
 		self._pre_admission_rejected = False
 		self._error: Exception | None = None
@@ -258,10 +260,17 @@ class SegmentLifecycle:
 		remove_wake = None
 		with self._condition:
 			if operation._run_started:
+				if operation._retired and operation._error is not None:
+					# fail() already published this operation before it ran.
+					return
 				raise RuntimeError("segment operation was already run")
 			operation._run_started = True
+			operation._waiting = True
 			try:
 				while self._resource_busy and not self._terminated and self._fault is None:
+					if operation._retired:
+						# fail() published it while it waited for the resource.
+						return
 					if not operation.work.is_valid():
 						self._discard_operation_locked(operation)
 						return
@@ -271,6 +280,7 @@ class SegmentLifecycle:
 						continue
 					self._condition.wait()
 			finally:
+				operation._waiting = False
 				if remove_wake is not None:
 					remove_wake()
 			if self._fault is not None:
@@ -410,6 +420,12 @@ class SegmentLifecycle:
 			if operation._error is None:
 				operation._error = error
 			operation._admitting = False
+			if (not operation._run_started or operation._waiting) and operation in self._operations:
+				# It has not acquired the resource and can never submit: publish
+				# the failure now, in fail()'s order, instead of after a wake-up.
+				self._reject_pending_locked(operation, operation._error)
+				self._condition.notify_all()
+				return
 			self._condition.notify_all()
 		self._start_stop(operation)
 
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/test_segment_host.py tests/test_segment_lifecycle.py -q 2>&1 | tail -1`
Expected: `93 passed`

Run: `python3 -m pytest tests -q 2>&1 | tail -1`
Expected: `1349 passed, 96 skipped, 2 xfailed`

Run: `ruff format --check addon | tail -1; ruff check tests/test_segment_host.py`
Expected: `53 files already formatted`, `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add addon/synthDrivers/WorldVoice/runtime/segmentHost.py addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py \
	tests/test_segment_host.py tests/test_segment_lifecycle.py
git commit -m "feat(runtime): prepare hook outside admission and synchronous failure of unacquired segments

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Prove the tests bite (mutations M1a–M1g, after the commit)**

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

mutate $H '		prepare = getattr(self._strategy, "prepare", None)' '		prepare = None'; check tests/test_segment_host.py   # M1a
mutate $H '				commands = prepare(self, commands, operation)' '				with self._admission:
					commands = prepare(self, commands, operation)'; check tests/test_segment_host.py   # M1b
mutate $H '			except Exception as error:
				if operation is None:
					raise
				self._lifecycle_of(operation).fail(operation, error)
				return' '			except Exception:
				raise'; check tests/test_segment_host.py   # M1c
mutate $L '			if (not operation._run_started or operation._waiting) and operation in self._operations:' '			if not operation._run_started and operation in self._operations:'; check tests/test_segment_lifecycle.py   # M1d
mutate $L '			if (not operation._run_started or operation._waiting) and operation in self._operations:' '			if operation._waiting and operation in self._operations:'; check tests/test_segment_lifecycle.py   # M1e
mutate $L '					if operation._retired:
						# fail() published it while it waited for the resource.' '					if False:
						# fail() published it while it waited for the resource.'; check tests/test_segment_lifecycle.py   # M1f
mutate $L '				if operation._retired and operation._error is not None:' '				if False:'; check tests/test_segment_lifecycle.py   # M1g
git status --short | grep addon
```

Expected:
- M1a: `prepare` ignored. `4 failed, 53 passed`, the four prepare tests:
  - `test_prepare_result_is_what_submit_receives`
  - `test_cancel_does_not_wait_for_prepare`
  - `test_segment_prepare_error_fails_only_that_segment`
  - `test_ordinary_prepare_error_is_raised`
- M1b: `prepare` runs under admission. `1 failed, 56 passed`: `test_cancel_does_not_wait_for_prepare`
- M1c: a segment `prepare` error is raised. `1 failed, 56 passed`: `test_segment_prepare_error_fails_only_that_segment`
- M1d: a waiting operation is not published by `fail()`. `1 failed, 35 passed`: `test_failed_waiting_operation_is_published_before_the_resource_frees`
- M1e: an unrun operation is not published by `fail()`. `1 failed, 35 passed`: `test_failed_operation_that_never_ran_is_published_and_its_run_is_a_no_op`
- M1f: the waiting loop ignores an already published operation. `36 passed`. This is an equivalent mutant; see Review Focus 2.
- M1g: `run()` of an already published operation raises. `1 failed, 35 passed`: `test_failed_operation_that_never_ran_is_published_and_its_run_is_a_no_op`

The final `git status` prints nothing.

---

### Task 2: Move OneCore onto SegmentHost

Spec §2.

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py` (rewrite of the segment path)
- Modify: `tests/test_onecore_segment_drain.py`:
  - 20 coupled reads now go through the host.
  - 4 new tests.
- Modify: `tests/test_lifecycle_private_access.py` (`MIGRATED = ("Espeak", "SAPI5", "RHVoice", "OneCore")`)

**Interfaces:**
- Consumes: Task 1's `prepare` hook and `fail()` semantics; the existing host API (`speak_segment`, `enqueue(barriers=)`, `begin`, `consumer`, `bound_callback`, `close`, `reach`, `record_error`, `retire`, `abandon`, `forget`, `cancel`, `terminate`, `latch_control_error`, `fail_accepted_on_control_error`, `drain`, `admission_error`).
- Produces:
  - `SynthDriver._segmentHost`, a `SegmentHost("OneCore", _OneCoreStrategy(self), fail_accepted_on_control_error=True)`.
  - `_OneCoreStrategy.barriers = {"callback", "synced"}`; ordinary text uses `{"callback"}`.
  - `_OneCoreNative(text, called)` in `record.native`; `_SpeechJob(record)` in `_queuedSpeech`.
  - Kept names that tests read: `_segmentNative` (the record being processed), `_callback`, `_retireSegmentNative`, `_failSegmentControl`, `_deliverSegmentControlFailure`, `_segmentWorker`, `_queuedSpeech`, `_segmentCondition`.
- The coupled test reads, which change only how they read state:
  1. The fixture also evicts `synthDrivers.WorldVoice.runtime.segmentHost`.
  2. `env.driver._segmentLifecycle` → `env.driver._segmentHost._lifecycle`, in 15 places. The first test's `isinstance(lifecycle, env.outer.SegmentLifecycle)` becomes `isinstance(env.driver._segmentHost, env.outer.SegmentHost)`.
  3. `env.driver._segmentAccepted` → `env.driver._segmentHost._accepted`, in 2 places.
  4. `env.driver._segmentControlError` → `env.driver._segmentHost.control_error`.
  5. `env.driver._segmentActiveOperation is None` → `env.driver._segmentNative is None`.
- New tests:
  - `test_setting_changed_while_a_segment_waits_applies_before_it`
  - `test_ordinary_speech_and_settings_keep_call_order`
  - `test_cancel_releases_a_segment_queued_behind_ordinary_speech`
  - `test_control_error_fails_a_segment_queued_behind_ordinary_speech`
  - They share the helper `queue_segment_behind_ordinary_speech`.

- [ ] **Step 1: Point the tests at the host and add the new tests**

Save as `$PATCHES/t2-tests.patch`, then run `git apply $PATCHES/t2-tests.patch`:

```diff
diff --git a/tests/test_lifecycle_private_access.py b/tests/test_lifecycle_private_access.py
index 9d2357a..222a98f 100644
--- a/tests/test_lifecycle_private_access.py
+++ b/tests/test_lifecycle_private_access.py
@@ -46,7 +46,7 @@ def test_wrappers_do_not_touch_lifecycle_private_state():
 
 
 # Wrappers moved onto SegmentHost; the host owns their lifecycle entirely.
-MIGRATED = ("Espeak", "SAPI5", "RHVoice")
+MIGRATED = ("Espeak", "SAPI5", "RHVoice", "OneCore")
 
 
 def test_migrated_wrappers_only_use_the_segment_host():
diff --git a/tests/test_onecore_segment_drain.py b/tests/test_onecore_segment_drain.py
index 1e47fb7..83b6be6 100644
--- a/tests/test_onecore_segment_drain.py
+++ b/tests/test_onecore_segment_drain.py
@@ -11,6 +11,7 @@ from onecore_drain_harness import VERSION, in_thread, load_onecore
 @pytest.fixture
 def env(monkeypatch):
     monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentLifecycle", raising=False)
+    monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentHost", raising=False)
     result = load_onecore(monkeypatch)
     yield result
     result.player.feed_release.set()
@@ -47,8 +48,8 @@ def test_onecore_uses_shared_lifecycle_for_empty_and_pcm_segments(env, frames, c
     events = []
     _, context, _ = speak(env, commands=commands, events=events)
     # The actual wrapper must own the same operation that the coordinator runs.
-    lifecycle = env.driver._segmentLifecycle
-    assert isinstance(lifecycle, env.outer.SegmentLifecycle)
+    lifecycle = env.driver._segmentHost._lifecycle
+    assert isinstance(env.driver._segmentHost, env.outer.SegmentHost)
     env.native.wait_calls(1)
     native = env.driver._segmentNative
     assert native.operation in lifecycle._operations
@@ -242,6 +243,42 @@ def test_settings_tuples_do_not_take_native_job_identity(env):
     assert events_b[0].segment_id == 18
 
 
+def test_setting_changed_while_a_segment_waits_applies_before_it(env):
+    # A queued segment enters OneCore's queue only once its predecessor drains,
+    # so a setting changed meanwhile is applied before that segment is spoken.
+    speak(env)
+    env.native.wait_calls(1)
+    _, _, events = speak(env, segment=18)
+    env.driver._set_rate(60)
+    env.player.sync_release.set()
+    env.native.respond(markers="")
+    env.native.wait_calls(2)
+    assert env.native.settings == [("Rate", 1.1)]
+    env.native.respond(markers="")
+    wait_events(events)
+    assert [event.kind for event in events] == [env.rt.models.EventKind.SEGMENT_DRAINED]
+
+
+def test_ordinary_speech_and_settings_keep_call_order(env):
+    entries = []
+    original_speak = env.native.speak
+
+    def recording_speak(token, text):
+        entries.append(list(env.native.settings))
+        original_speak(token, text)
+
+    env.native.ocSpeech_speak = env.native.ocSpeech_speak.__class__(recording_speak)
+    env.driver.speak(("first",))
+    env.driver._set_rate(60)
+    env.driver.speak(("second",))
+    env.native.wait_calls(1)
+    env.player.sync_release.set()
+    env.native.respond(markers="")
+    env.native.wait_calls(2)
+    env.native.respond(markers="")
+    assert entries == [[], [("Rate", 1.1)]]
+
+
 def test_cancel_removes_queued_text_but_keeps_settings_identity(env):
     speak(env)
     env.native.wait_calls(1)
@@ -322,7 +359,7 @@ def test_cancel_after_control_fault_capture_suppresses_pending_failure(env, monk
         context=context, on_event=events.append))
     try:
         assert converting.wait(1)
-        operation = next(iter(env.driver._segmentLifecycle._operations))
+        operation = next(iter(env.driver._segmentHost._lifecycle._operations))
         faulting = in_thread(lambda: env.driver._failSegmentControl(OSError("player failed")))
         assert captured.wait(1)
         cancelling = in_thread(env.driver.cancel)
@@ -331,9 +368,9 @@ def test_cancel_after_control_fault_capture_suppresses_pending_failure(env, monk
         finish(faulting)
         release_conversion.set()
         finish(speaking)
-        with env.driver._segmentLifecycle._condition:
-            assert env.driver._segmentLifecycle._condition.wait_for(
-                lambda: operation not in env.driver._segmentLifecycle._operations, 1)
+        with env.driver._segmentHost._lifecycle._condition:
+            assert env.driver._segmentHost._lifecycle._condition.wait_for(
+                lambda: operation not in env.driver._segmentHost._lifecycle._operations, 1)
         assert events == []
         assert env.native.calls == []
     finally:
@@ -359,7 +396,7 @@ def test_suppressed_conversion_failure_retires_accepted_membership(env, monkeypa
         context=context, on_event=events.append))
     try:
         assert converting.wait(1)
-        operation = next(iter(env.driver._segmentLifecycle._operations))
+        operation = next(iter(env.driver._segmentHost._lifecycle._operations))
         real_fail = operation.work.fail
 
         def held_fail(error):
@@ -372,15 +409,15 @@ def test_suppressed_conversion_failure_retires_accepted_membership(env, monkeypa
         finish(speaking)
         assert failing.wait(1)
         with env.driver._segmentCondition:
-            assert operation in env.driver._segmentAccepted
+            assert operation in env.driver._segmentHost._accepted
         token.cancel()
         release_failure.set()
-        with env.driver._segmentLifecycle._condition:
-            assert env.driver._segmentLifecycle._condition.wait_for(
-                lambda: operation not in env.driver._segmentLifecycle._operations, 1)
+        with env.driver._segmentHost._lifecycle._condition:
+            assert env.driver._segmentHost._lifecycle._condition.wait_for(
+                lambda: operation not in env.driver._segmentHost._lifecycle._operations, 1)
         with env.driver._segmentCondition:
             assert env.driver._segmentCondition.wait_for(
-                lambda: operation not in env.driver._segmentAccepted, 1)
+                lambda: operation not in env.driver._segmentHost._accepted, 1)
         assert events == []
         assert env.native.calls == []
     finally:
@@ -390,7 +427,7 @@ def test_suppressed_conversion_failure_retires_accepted_membership(env, monkeypa
 
 def test_cancel_sees_work_between_queue_pop_and_lifecycle_run(env, monkeypatch):
     entered, release, finished = Event(), Event(), Event()
-    lifecycle = env.driver._segmentLifecycle
+    lifecycle = env.driver._segmentHost._lifecycle
     real_run = lifecycle.run
 
     def held_run(operation, commands):
@@ -504,7 +541,7 @@ def test_onecore_rejected_segment_uses_async_lifecycle_delivery(env, terminated)
         env.native.respond(markers="")
         with env.driver._segmentCondition:
             assert env.driver._segmentCondition.wait_for(
-                lambda: env.driver._segmentControlError is not None, 1)
+                lambda: env.driver._segmentHost.control_error is not None, 1)
     caller = get_ident()
     received, events, threads = Event(), [], []
     token = env.scheduler.CancellationToken()
@@ -521,21 +558,21 @@ def test_onecore_rejected_segment_uses_async_lifecycle_delivery(env, terminated)
     assert events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
     assert events[0].source_id is context.source_id
     assert events[0].segment_id == 19
-    assert threads == [env.driver._segmentLifecycle._delivery_thread.ident]
+    assert threads == [env.driver._segmentHost._lifecycle._delivery_thread.ident]
     assert threads[0] != caller
     assert len(env.native.calls) == (0 if terminated else 1)
 
 
 def test_onecore_acceptance_is_atomic_with_terminate(env):
     entered, release_accept = Event(), Event()
-    original_accept = env.driver._segmentLifecycle.accept
+    original_accept = env.driver._segmentHost._lifecycle.accept
 
     def blocked_accept(*args, **kwargs):
         entered.set()
         assert release_accept.wait(2)
         return original_accept(*args, **kwargs)
 
-    env.driver._segmentLifecycle.accept = blocked_accept
+    env.driver._segmentHost._lifecycle.accept = blocked_accept
     events = []
     speaking = in_thread(lambda: speak(env, events=events))
     assert entered.wait(1)
@@ -548,7 +585,7 @@ def test_onecore_acceptance_is_atomic_with_terminate(env):
 
 
 def test_onecore_terminate_overlap_preserves_rejected_failure_event(env):
-    lifecycle = env.driver._segmentLifecycle
+    lifecycle = env.driver._segmentHost._lifecycle
     delivery_entered, release_delivery = Event(), Event()
     blocker_context = env.rt.models.PlaybackContext(object(), 20)
     lifecycle.reject_new(blocker_context, env.scheduler.CancellationToken(),
@@ -586,7 +623,7 @@ def test_onecore_terminate_overlap_preserves_rejected_failure_event(env):
 
 
 def test_onecore_accepted_then_terminated_suppresses_pending_failure(env, monkeypatch):
-    lifecycle = env.driver._segmentLifecycle
+    lifecycle = env.driver._segmentHost._lifecycle
     delivery_entered, release_delivery = Event(), Event()
     blocker_context = env.rt.models.PlaybackContext(object(), 20)
     lifecycle.reject_new(blocker_context, env.scheduler.CancellationToken(),
@@ -839,7 +876,7 @@ def start_controlled_playback(env, mode):
         # native callback returns. Wait for that handoff before resetting sync.
         with env.driver._segmentCondition:
             assert env.driver._segmentCondition.wait_for(
-                lambda: env.driver._segmentActiveOperation is None, 1)
+                lambda: env.driver._segmentNative is None, 1)
         env.player.sync_release.clear()
         env.player.sync_entered.clear()
     if mode == "segment":
@@ -1096,6 +1133,45 @@ def test_terminated_driver_is_collected_while_late_native_callback_stays_callabl
     assert touched == []
 
 
+def queue_segment_behind_ordinary_speech(env):
+    env.driver.speak(("legacy",))
+    env.native.wait_calls(1)
+    _, _, queued = speak(env, segment=18)
+    with env.driver._segmentCondition:
+        assert env.driver._segmentCondition.wait_for(lambda: any(
+            isinstance(item, env.outer._SpeechJob) for item in env.driver._queuedSpeech), 1)
+    return queued
+
+
+def test_cancel_releases_a_segment_queued_behind_ordinary_speech(env):
+    queued = queue_segment_behind_ordinary_speech(env)
+    env.driver.cancel()
+    env.native.respond(markers="")
+    _, _, events = speak(env, segment=19)
+    env.native.wait_calls(2)
+    env.player.sync_release.set()
+    env.native.respond(markers="")
+    wait_events(events)
+    assert queued == []
+    assert [event.kind for event in events] == [env.rt.models.EventKind.SEGMENT_DRAINED]
+
+
+def test_control_error_fails_a_segment_queued_behind_ordinary_speech(env):
+    queued = queue_segment_behind_ordinary_speech(env)
+    error = OSError("pause failed behind ordinary speech")
+
+    def failed_pause(switch):
+        raise error
+
+    env.player.pause = failed_pause
+    with pytest.raises(OSError):
+        env.driver.pause(True)
+    wait_events(queued)
+    assert len(queued) == 1
+    assert queued[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
+    assert queued[0].error is error
+
+
 def test_legacy_speak_still_uses_parent_interface(env):
     env.driver.speak(("legacy",))
     env.native.wait_calls(1)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests -q 2>&1 | grep -E "^FAILED|passed|failed" | sed 's/ - .*//'`
Expected: `16 failed, 1337 passed, 96 skipped, 2 xfailed`. The failures:
- `tests/test_lifecycle_private_access.py::test_migrated_wrappers_only_use_the_segment_host`
- `test_setting_changed_while_a_segment_waits_applies_before_it`: master applies the setting after the queued segment. This is the approved change.
- Fourteen coupled reads in `tests/test_onecore_segment_drain.py`, each an `AttributeError` for `_segmentHost` or `SegmentHost`:
  - `test_onecore_uses_shared_lifecycle_for_empty_and_pcm_segments[0-commands0]` and `[8-commands1]`
  - `test_cancel_after_control_fault_capture_suppresses_pending_failure`
  - `test_suppressed_conversion_failure_retires_accepted_membership`
  - `test_cancel_sees_work_between_queue_pop_and_lifecycle_run`
  - `test_onecore_rejected_segment_uses_async_lifecycle_delivery[False]` and `[True]`
  - `test_onecore_acceptance_is_atomic_with_terminate`
  - `test_onecore_terminate_overlap_preserves_rejected_failure_event`
  - `test_onecore_accepted_then_terminated_suppresses_pending_failure`
  - `test_late_pause_retires_before_cancel_handoff_or_native_close[False-legacy_after_segment]` and `[True-legacy_after_segment]`
  - `test_pause_or_resume_error_resolves_work_and_blocks_new_admission[False-legacy_after_segment]` and `[True-legacy_after_segment]`

`test_ordinary_speech_and_settings_keep_call_order` and both queued-behind-ordinary tests already pass on master; mutations M2b and M2c prove the latter two bite.

- [ ] **Step 3: Rewrite the OneCore wrapper**

Save as `$PATCHES/t2-impl.patch`, then run `git apply $PATCHES/t2-impl.patch`:

```diff
diff --git a/addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py b/addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py
index ad132ee..653d7df 100644
--- a/addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py
+++ b/addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py
@@ -1,7 +1,7 @@
 import ctypes
 from dataclasses import dataclass
 import io
-from threading import Condition, Event, Lock, Thread
+from threading import Condition, Lock, Thread
 import wave
 import weakref
 
@@ -12,14 +12,8 @@ from synthDriverHandler import synthDoneSpeaking, synthIndexReached
 from .driver import OneCoreSynthDriver as BaseOneCoreSynthDriver
 from synthDrivers.WorldVoice.driver import Voice
 from ...runtime.models import PlaybackContext, SegmentEventSink, SpeechCommands
-from ...runtime.playbackWork import (
-	CallbackGate,
-	DrainSupport,
-	PlaybackWork,
-	runtime_profile,
-	unverified_drain_support,
-)
-from ...runtime.segmentLifecycle import SegmentLifecycle, SegmentOperation
+from ...runtime.playbackWork import DrainSupport, runtime_profile, unverified_drain_support
+from ...runtime.segmentHost import SegmentHost
 from ...runtime.session import CancellationView
 
 
@@ -46,6 +40,10 @@ class Voice(Voice):
 # lifetime; it must not retain the driver, player or captured work graph.
 _TERMINATED_CALLBACKS = []
 
+# Ordinary (legacy) text proves only that its callback returned; the parent
+# owns its queue-empty sync, idle and DONE.
+_ORDINARY_BARRIERS = frozenset({"callback"})
+
 
 class _DetachableCallback:
 	"""Fixed native callback pointer with revocable, weak driver ownership."""
@@ -62,57 +60,125 @@ class _DetachableCallback:
 		# detach/terminate never waits for its feed/sync under this lock.
 		if driver is not None:
 			with driver._segmentCondition:
-				native = driver._segmentNative
+				record = driver._segmentNative
 			try:
 				driver._callback(audio, length, markers)
 			finally:
-				# Retire contextual native ownership only after the callback body
-				# has returned, including any admitted feed and final stop.
-				if native is not None and native.operation is not None:
-					driver._retireSegmentNative(native)
-					native.boundary.set()
+				# Retire callback ownership only after the callback body has
+				# returned, including any admitted feed and final stop, then
+				# release the worker.
+				if record is not None:
+					try:
+						driver._retireSegmentNative(record)
+					finally:
+						driver._releaseSegmentWorker(record)
 
 	def detach(self):
 		with self._lock:
 			self._driver = None
 
 
-@dataclass(frozen=True)
-class _SpeechJob:
+@dataclass(eq=False)
+class _OneCoreNative:
+	"""OneCore data carried on a NativeRecord: its SSML and callback return."""
+
 	text: str
-	work: PlaybackWork | None
-	operation: SegmentOperation | None = None
+	called: bool = False
 
 
 @dataclass(frozen=True)
-class _NativeJob:
-	job: _SpeechJob
-	call_token: object | None
-	boundary: Event | None = None
+class _SpeechJob:
+	record: object
+
+
+class _OneCoreStrategy:
+	"""OneCore's native queue: the parent's _queuedSpeech and the outer worker."""
 
-	@property
-	def operation(self):
-		return self.job.operation
+	barriers = frozenset({"callback", "synced"})
+
+	def __init__(self, driver):
+		self._driver = weakref.ref(driver)
+
+	def admission_error(self, host):
+		driver = self._driver()
+		with driver._segmentCondition:
+			if driver._segmentTerminated:
+				return RuntimeError("OneCore driver has terminated")
+			if not driver._segmentMode and driver._isProcessing:
+				return RuntimeError("Cannot switch to correlated playback while legacy synthesis is active")
+		return None
+
+	def prepare(self, host, commands, operation):
+		if operation is None:
+			# Ordinary text arrives already converted by the parent's speak().
+			return commands
+		driver = self._driver()
+		with driver._segmentCondition:
+			driver._checkSegmentAdmission()
+		if driver.supportsProsodyOptions:
+			conv = oneCore._OcSsmlConverter(driver.language, driver.availableLanguages)
+		else:
+			conv = oneCore._OcPreAPI5SsmlConverter(
+				driver.language,
+				driver.availableLanguages,
+				driver._rate,
+				driver._pitch,
+				driver._volume,
+			)
+		return conv.convertToXml(tuple(commands))
+
+	def submit(self, host, record, text):
+		driver = self._driver()
+		with driver._segmentCondition:
+			driver._checkSegmentAdmission()
+			record.native = _OneCoreNative(text)
+			driver._segmentMode = True
+			driver._queuedSpeech.append(_SpeechJob(record))
+		driver._processQueue()
+
+	def stop_native(self, host, record):
+		player = self._driver()._player
+		if player:
+			player.stop()
+
+	def stop_player(self, host):
+		player = self._driver()._player
+		if player:
+			player.stop()
+
+	def drain(self, host, record):
+		driver = self._driver()
+		player = driver._player
+		if player:
+			try:
+				player.sync()
+				with driver._segmentCondition:
+					driver._segmentCondition.wait_for(
+						lambda: not driver._segmentPaused or not record.work.is_valid(),
+					)
+			except Exception as error:
+				host.record_error(record, error)
+				driver._failSegmentControl(error)
+				return
+		host.reach(record, "synced")
 
 
 class SynthDriver(BaseOneCoreSynthDriver):
 	"""Retain terminal callback ownership and drain each correlated utterance."""
 
 	def __init__(self):
+		self._segmentHost = SegmentHost(
+			"OneCore", _OneCoreStrategy(self), fail_accepted_on_control_error=True
+		)
 		self._segmentCondition = Condition()
 		self._segmentPauseLock = Lock()
-		self._segmentGate = CallbackGate()
-		self._segmentLifecycle = SegmentLifecycle(self)
 		self._segmentMode = False
 		self._segmentTerminated = False
 		self._segmentPaused = False
 		self._segmentControlGeneration = 0
-		self._segmentControlError = None
 		self._segmentStops = 0
 		self._segmentWorker = None
 		self._segmentNative = None
-		self._segmentActiveOperation = None
-		self._segmentAccepted = set()
 		self._segmentCallback = _DetachableCallback(self)
 		# The parent installs CFUNCTYPE(self._callback) once. Intercept only
 		# that instance lookup; its native pointer owns the trampoline rather
@@ -148,82 +214,15 @@ class SynthDriver(BaseOneCoreSynthDriver):
 		context: PlaybackContext,
 		on_event: SegmentEventSink,
 	) -> None:
-		with self._segmentCondition:
-			admission_error = (
-				RuntimeError("OneCore driver has terminated")
-				if self._segmentTerminated
-				else self._segmentControlError
-			)
-			if admission_error is not None:
-				self._segmentLifecycle.reject_new(context, token, on_event, admission_error)
-				return
-
-			def retired(operation):
-				with self._segmentCondition:
-					self._segmentAccepted.discard(operation)
-					self._segmentCondition.notify_all()
-
-			operation = self._segmentLifecycle.accept(
-				context,
-				token,
-				on_event,
-				on_retired=retired,
-			)
-			self._segmentAccepted.add(operation)
-		if not operation.is_valid():
-			with self._segmentCondition:
-				if not operation.has_started():
-					self._segmentLifecycle.reject_pending(
-						operation,
-						RuntimeError("OneCore segment was cancelled before submission"),
-					)
-				self._segmentAccepted.discard(operation)
-			return
-		try:
-			with self._segmentCondition:
-				self._checkSegmentAdmission()
-			if self.supportsProsodyOptions:
-				conv = oneCore._OcSsmlConverter(self.language, self.availableLanguages)
-			else:
-				conv = oneCore._OcPreAPI5SsmlConverter(
-					self.language,
-					self.availableLanguages,
-					self._rate,
-					self._pitch,
-					self._volume,
-				)
-			job = _SpeechJob(conv.convertToXml(tuple(commands)), operation.work, operation)
-			with self._segmentCondition:
-				self._checkSegmentAdmission()
-				if not operation.is_valid():
-					if not operation.has_started():
-						self._segmentLifecycle.reject_pending(
-							operation,
-							RuntimeError("OneCore segment was cancelled before submission"),
-						)
-					self._segmentAccepted.discard(operation)
-					return
-				if not self._segmentMode and self._isProcessing:
-					raise RuntimeError(
-						"Cannot switch to correlated playback while legacy synthesis is active",
-					)
-				self._segmentMode = True
-				self._queuedSpeech.append(job)
-				self._segmentAccepted.discard(operation)
-			self._processQueue()
-		except Exception as error:
-			with self._segmentCondition:
-				if not operation.has_started():
-					self._segmentLifecycle.reject_pending(operation, error)
-				if not operation.work.is_valid():
-					self._segmentAccepted.discard(operation)
+		self._segmentHost.speak_segment(commands, token, context=context, on_event=on_event)
 
 	def _checkSegmentAdmission(self):
 		# Called under the condition; a control fault requires resource replacement.
 		if self._segmentTerminated:
 			raise RuntimeError("OneCore driver has terminated")
-		if self._segmentControlError is not None:
-			raise self._segmentControlError
+		control_error = self._segmentHost.control_error
+		if control_error is not None:
+			raise control_error
 
 	def speak(self, speechSequence):
 		with self._segmentCondition:
@@ -233,18 +232,16 @@ class SynthDriver(BaseOneCoreSynthDriver):
 	def _queueSpeech(self, item):
 		with self._segmentCondition:
 			self._checkSegmentAdmission()
-			# Legacy text uses the same native ownership and control retirement
-			# as legacy text queued after a correlated segment. Keep its original
-			# speak conversion and anonymous DONE completion interface.
-			self._segmentMode = True
-			self._queuedSpeech.append(item)
-		self._processQueue()
+		# Legacy text uses the same native ownership and control retirement as
+		# a correlated segment, keeping its original conversion and anonymous
+		# DONE completion interface.
+		self._segmentHost.enqueue(item, barriers=_ORDINARY_BARRIERS)
 
 	def _processQueue(self):
 		if not self._segmentMode:
 			return super()._processQueue()
 		with self._segmentCondition:
-			if self._segmentTerminated or self._segmentControlError is not None:
+			if self._segmentTerminated or self._segmentHost.control_error is not None:
 				return
 			if self._segmentWorker is None:
 				self._segmentWorker = Thread(
@@ -256,12 +253,13 @@ class SynthDriver(BaseOneCoreSynthDriver):
 			self._segmentCondition.notify_all()
 
 	def _runSegmentQueue(self):
+		host = self._segmentHost
 		while True:
 			with self._segmentCondition:
 				self._segmentCondition.wait_for(
 					lambda: (
 						self._segmentTerminated
-						or self._segmentControlError is not None
+						or host.control_error is not None
 						or (
 							self._segmentNative is None
 							and self._segmentStops == 0
@@ -269,172 +267,101 @@ class SynthDriver(BaseOneCoreSynthDriver):
 						)
 					),
 				)
-				if self._segmentTerminated or self._segmentControlError is not None:
+				if self._segmentTerminated or host.control_error is not None:
 					return
 				item = self._queuedSpeech.pop(0)
-				if not isinstance(item, tuple):
-					job = item if isinstance(item, _SpeechJob) else _SpeechJob(item, None)
-					if job.work is not None and not job.work.is_valid():
-						if job.operation is not None:
-							self._segmentLifecycle.reject_pending(
-								job.operation,
-								RuntimeError("OneCore segment was cancelled before submission"),
-							)
-						continue
-					if job.operation is None:
-						# Legacy text retains the existing native queue contract.
-						native = _NativeJob(job, None)
-						self._segmentNative = native
-						self._wasCancelled = False
-						self._isProcessing = True
-					else:
-						# The queue-to-worker transition is visible to cancel().
-						self._segmentActiveOperation = job.operation
-			try:
 				if isinstance(item, tuple):
-					func, value = item
-					func(self._ocSpeechToken, ctypes.c_double(value))
-				elif job.operation is not None:
-					try:
-						self._segmentLifecycle.run(job.operation, job.text)
-					finally:
-						with self._segmentCondition:
-							if self._segmentActiveOperation is job.operation:
-								self._segmentActiveOperation = None
+					record = None
 				else:
-					self._dll.ocSpeech_speak(self._ocSpeechToken, native.job.text)
-			except Exception as error:
-				log.exception("OneCore queued operation failed")
-				if not isinstance(item, tuple):
-					try:
-						if job.operation is not None:
-							self._segmentLifecycle.fail(job.operation, error)
-						elif native.job.work is not None:
-							native.job.work.fail(error)
-						else:
-							self._failSegmentControl(error)
-					finally:
-						if job.operation is None:
-							self._retireSegmentNative(native)
+					record = item.record
+					if not record.is_valid():
+						host.abandon(record)
+						continue
+					self._segmentNative = record
+					host.begin(record)
+					self._wasCancelled = False
+					self._isProcessing = True
+			if record is None:
+				func, value = item
+				try:
+					func(self._ocSpeechToken, ctypes.c_double(value))
+				except Exception as error:
+					log.exception("OneCore setting change failed")
+					self._failSegmentControl(error)
+				continue
+			self._speakRecord(record)
 
-	# SegmentLifecycle hooks. The existing queue still serializes settings and
-	# legacy jobs; the coordinator owns contextual retirement and delivery.
-	def submit_native(self, operation, text):
-		with self._segmentCondition:
-			call = self._segmentGate.begin_native(operation.work)
-			native = _NativeJob(_SpeechJob(text, operation.work, operation), call, Event())
-			operation._onecore_native = native
-			self._segmentNative = native
-			self._segmentActiveOperation = operation
-			self._wasCancelled = False
-			self._isProcessing = True
+	def _speakRecord(self, record):
+		host = self._segmentHost
 		try:
-			if self._player:
-				self._player.open()
-			if not operation.is_valid():
-				self._retireSegmentNative(native)
-				native.boundary.set()
-				return
-		except Exception as error:
-			self._failSegmentControl(error)
-			self._retireSegmentNative(native)
-			native.boundary.set()
-			return
-		try:
-			self._dll.ocSpeech_speak(self._ocSpeechToken, text)
-		except Exception as error:
-			self._segmentLifecycle.fail(operation, error)
-			self._retireSegmentNative(native)
-			native.boundary.set()
-
-	def request_stop(self, operation):
-		if self._player:
-			self._player.stop()
-
-	def wait_native_boundary(self, operation):
-		operation._onecore_native.boundary.wait()
-
-	def wait_native_retired(self, operation):
-		self._segmentGate.wait_retired(operation._onecore_native.call_token)
-
-	def wait_playback_drained(self, operation):
-		if operation.is_valid() and self._player:
 			try:
-				self._player.sync()
-				with self._segmentCondition:
-					self._segmentCondition.wait_for(
-						lambda: not self._segmentPaused or not operation.is_valid(),
-					)
+				if self._player:
+					self._player.open()
 			except Exception as error:
+				host.record_error(record, error)
 				self._failSegmentControl(error)
-				raise
+				self._releaseSegmentWorker(record)
+			else:
+				if not record.is_valid():
+					self._releaseSegmentWorker(record)
+				else:
+					try:
+						self._dll.ocSpeech_speak(self._ocSpeechToken, record.native.text)
+					except Exception as error:
+						log.exception("OneCore queued operation failed")
+						host.record_error(record, error)
+						if record.operation is None:
+							self._failSegmentControl(error)
+						self._releaseSegmentWorker(record)
+			with self._segmentCondition:
+				# The native callback returns once per call, even when cancelled.
+				self._segmentCondition.wait_for(lambda: record.native.called or self._segmentTerminated)
+				called = record.native.called
+			if not called:
+				host.abandon(record)
+				return
+			host.retire(record)
+			if record.operation is None:
+				host.forget(record)
+		finally:
+			with self._segmentCondition:
+				if self._segmentNative is record:
+					self._segmentNative = None
+					self._isProcessing = False
+				self._segmentCondition.notify_all()
 
-	def _retireSegmentNative(self, native):
-		if native.call_token is not None:
-			self._segmentGate.finish_native(native.call_token)
-			self._segmentGate.wait_retired(native.call_token)
+	def _retireSegmentNative(self, record):
+		# The callback has returned: no further native callback enters this record.
+		self._segmentHost.close(record)
+
+	def _releaseSegmentWorker(self, record):
 		with self._segmentCondition:
-			if self._segmentNative is native:
-				self._segmentNative = None
-				self._isProcessing = False
+			record.native.called = True
 			self._segmentCondition.notify_all()
 
 	def _callback(self, audio, length, markers):
 		if not self._segmentMode:
 			return super()._callback(audio, length, markers)
+		host = self._segmentHost
 		with self._segmentCondition:
-			native = self._segmentNative
-			control_failed = self._segmentControlError is not None
-		if native is None or self._earlyExitCB:
+			record = self._segmentNative
+		control_failed = host.control_error is not None
+		if record is None or self._earlyExitCB:
 			return
 		if control_failed:
 			return
-		work = native.job.work
-		if work is None:
-			try:
-				super()._callback(audio, length, markers)
-				# The parent's callback schedules our worker instead of recursively
-				# running its queue. Preserve the parent's legacy queue-empty DONE.
-				with self._segmentCondition:
-					empty = not self._queuedSpeech and not self._wasCancelled and not self._segmentTerminated
-				if empty and self._player:
-					self._player.sync()
-					with self._segmentCondition:
-						self._segmentCondition.wait_for(
-							lambda: not self._segmentPaused or self._wasCancelled or self._segmentTerminated,
-						)
-						empty = (
-							not self._queuedSpeech and not self._wasCancelled and not self._segmentTerminated
-						)
-					if empty:
-						self._player.idle()
-						with self._segmentCondition:
-							self._segmentCondition.wait_for(
-								lambda: (
-									not self._segmentPaused or self._wasCancelled or self._segmentTerminated
-								),
-							)
-						if not self._wasCancelled and not self._segmentTerminated:
-							synthDoneSpeaking.notify(synth=self)
-			except Exception as error:
-				log.exception("OneCore legacy playback failed")
-				self._failSegmentControl(error)
-			finally:
-				try:
-					# The parent can return from an admitted feed after cancel's
-					# stop has run. Keep this native record as legacy admission
-					# until a final stop removes anything that feed queued.
-					if (self._wasCancelled or self._segmentTerminated) and self._player:
-						self._player.stop()
-				finally:
-					self._retireSegmentNative(native)
+		if record.operation is None:
+			self._legacyCallback(record, audio, length, markers)
 			return
-		operation = native.operation
-		lease = self._segmentGate.enter_callback()
-		producer = self._segmentLifecycle.admit_producer(operation) if lease is not None else None
-		try:
-			if lease is None or producer is None:
+		with host.consumer(record) as admitted:
+			if admitted is None:
 				return  # Consume a cancelled terminal callback without feeding.
+			with host.bound_callback(record):
+				self._segmentPlayback(record, audio, length, markers)
+
+	def _segmentPlayback(self, record, audio, length, markers):
+		host = self._segmentHost
+		try:
 			if length == 0:
 				raise RuntimeError("OneCore native synthesis returned no WAV (length=0)")
 			if length < oneCore.WAVE_HEADER_LENGTH:
@@ -454,99 +381,100 @@ class SynthDriver(BaseOneCoreSynthDriver):
 				if not previous <= position <= data_len:
 					raise ValueError("OneCore marker offset is outside ordered WAV audio")
 				if not self._feedSegment(
-					operation,
-					producer,
+					record,
 					player,
 					data + previous,
 					position - previous,
-					lambda index=index: self._segmentIndex(operation, index),
+					lambda index=index: self._segmentIndex(record, index),
 				):
 					return
 				previous = position
-			if not self._feedSegment(operation, producer, player, data + previous, data_len - previous):
+			if not self._feedSegment(record, player, data + previous, data_len - previous):
 				return
+			host.reach(record, "callback")
 		except Exception as error:
 			log.exception("OneCore segment playback failed")
-			try:
-				self._segmentLifecycle.fail(operation, error)
-			finally:
-				if self._player:
-					self._player.stop()
+			host.record_error(record, error)
+			if self._player:
+				self._player.stop()
 		finally:
-			try:
-				if lease is not None:
-					if not operation.is_valid() and self._player:
-						self._player.stop()
-			finally:
-				if producer is not None:
-					self._segmentLifecycle.retire_producer(producer)
-				if lease is not None:
-					lease.close()
+			if not record.is_valid() and self._player:
+				self._player.stop()
 
-	def _segmentIndex(self, operation, index):
-		if operation.is_valid():
+	def _legacyCallback(self, record, audio, length, markers):
+		try:
+			super()._callback(audio, length, markers)
+			self._segmentHost.reach(record, "callback")
+			# The parent's callback schedules our worker instead of recursively
+			# running its queue. Preserve the parent's legacy queue-empty DONE.
+			with self._segmentCondition:
+				empty = not self._queuedSpeech and not self._wasCancelled and not self._segmentTerminated
+			if empty and self._player:
+				self._player.sync()
+				with self._segmentCondition:
+					self._segmentCondition.wait_for(
+						lambda: not self._segmentPaused or self._wasCancelled or self._segmentTerminated,
+					)
+					empty = not self._queuedSpeech and not self._wasCancelled and not self._segmentTerminated
+				if empty:
+					self._player.idle()
+					with self._segmentCondition:
+						self._segmentCondition.wait_for(
+							lambda: not self._segmentPaused or self._wasCancelled or self._segmentTerminated,
+						)
+					if not self._wasCancelled and not self._segmentTerminated:
+						synthDoneSpeaking.notify(synth=self)
+		except Exception as error:
+			log.exception("OneCore legacy playback failed")
+			self._failSegmentControl(error)
+		finally:
+			# The parent can return from an admitted feed after cancel's stop has
+			# run. Keep this record current until a final stop removes anything
+			# that feed queued.
+			if (self._wasCancelled or self._segmentTerminated) and self._player:
+				self._player.stop()
+
+	def _segmentIndex(self, record, index):
+		if record.work.is_valid():
 			synthIndexReached.notify(synth=self, index=index)
 
-	def _feedSegment(self, operation, parent, player, address, size, on_done=None):
-		if not operation.is_valid():
-			return False
-		feed = self._segmentLifecycle.admit_producer(operation, parent=parent)
-		if feed is None:
+	def _feedSegment(self, record, player, address, size, on_done=None):
+		if not record.is_valid():
 			return False
 		try:
 			player.feed(ctypes.c_void_p(address), size=size, onDone=on_done)
 		finally:
-			try:
-				if not operation.is_valid():
-					player.stop()
-			finally:
-				self._segmentLifecycle.retire_producer(feed)
-		return operation.is_valid()
+			if not record.is_valid():
+				player.stop()
+		return record.is_valid()
 
 	def _captureSegmentControlFailure(self, error):
 		# Capture while the pause lock is still owned, before cancellation can
 		# retire that operation and admit a successor. Delivery happens later.
+		host = self._segmentHost
 		with self._segmentCondition:
-			if self._segmentControlError is not None:
+			if host.control_error is not None:
 				return None
-			self._segmentControlError = error
+			host.latch_control_error(error)
 			self._segmentControlGeneration += 1
 			self._wasCancelled = True
 			self._segmentStops += 1
-			queued = list(self._segmentAccepted) + [
-				item.operation
-				for item in self._queuedSpeech
-				if isinstance(item, _SpeechJob) and item.operation is not None
-			]
-			# Keep work removed from the queue visible to cancel until its
-			# asynchronous lifecycle failure is committed for delivery.
-			self._segmentAccepted.update(queued)
-			operations = list(queued)
-			legacy = any(isinstance(item, str) for item in self._queuedSpeech)
-			if self._segmentActiveOperation is not None:
-				operations.append(self._segmentActiveOperation)
-			elif self._segmentNative is not None:
-				legacy = True
+			dropped = [item.record for item in self._queuedSpeech if isinstance(item, _SpeechJob)]
+			legacy = any(record.operation is None for record in dropped) or (
+				self._segmentNative is not None and self._segmentNative.operation is None
+			)
 			self._queuedSpeech.clear()
-			return error, operations, queued, legacy
+			self._segmentCondition.notify_all()
+			return error, dropped, legacy
 
 	def _deliverSegmentControlFailure(self, failure):
 		if failure is None:
 			return
-		error, operations, queued, legacy = failure
+		error, dropped, legacy = failure
 		try:
-			# Invalidate contextual work before stop releases its drain wait.
-			# Sinks can reenter cancel/terminate, so no driver lock is held.
-			for operation in operations:
-				try:
-					if operation in queued:
-						with self._segmentCondition:
-							if not operation.has_started():
-								self._segmentLifecycle.reject_pending(operation, error)
-					else:
-						self._segmentLifecycle.fail(operation, error)
-				except Exception:
-					log.exception("OneCore control failure delivery failed")
+			# Queued records never reach the worker; they fail with the latched error.
+			for record in dropped:
+				self._segmentHost.abandon(record)
 			if self._player:
 				try:
 					self._player.stop()
@@ -580,38 +508,26 @@ class SynthDriver(BaseOneCoreSynthDriver):
 				except Exception as error:
 					failure = self._captureSegmentControlFailure(error)
 					raise
-		except Exception as error:
+		except Exception:
 			self._deliverSegmentControlFailure(failure)
 			raise
 
 	def cancel(self):
-		with self._segmentCondition:
-			self._wasCancelled = True
-			self._segmentPaused = False
-			self._segmentControlGeneration += 1
-			self._segmentStops += 1
-			for item in self._queuedSpeech:
-				if isinstance(item, _SpeechJob) and item.work is not None:
-					if item.operation is not None:
-						self._segmentLifecycle.cancel(item.operation)
-						self._segmentLifecycle.reject_pending(
-							item.operation,
-							RuntimeError("OneCore segment was cancelled before submission"),
-						)
-					else:
-						item.work.cancel()
-			for operation in tuple(self._segmentAccepted):
-				self._segmentLifecycle.cancel(operation)
-				if not operation.has_started():
-					self._segmentLifecycle.reject_pending(
-						operation,
-						RuntimeError("OneCore segment was cancelled before submission"),
-					)
-			self._segmentAccepted.clear()
-			self._queuedSpeech = [item for item in self._queuedSpeech if isinstance(item, tuple)]
-			if self._segmentActiveOperation is not None:
-				self._segmentLifecycle.cancel(self._segmentActiveOperation)
-			self._segmentCondition.notify_all()
+		host = self._segmentHost
+		with host.admission():
+			host.cancel()
+			with self._segmentCondition:
+				self._wasCancelled = True
+				self._segmentPaused = False
+				self._segmentControlGeneration += 1
+				self._segmentStops += 1
+				dropped = [item.record for item in self._queuedSpeech if isinstance(item, _SpeechJob)]
+				# Settings changes keep their queue position.
+				self._queuedSpeech = [item for item in self._queuedSpeech if isinstance(item, tuple)]
+				self._segmentCondition.notify_all()
+			# Queued records never reach the worker.
+			for record in dropped:
+				host.abandon(record)
 		try:
 			try:
 				if self._player:
@@ -622,7 +538,7 @@ class SynthDriver(BaseOneCoreSynthDriver):
 				# then undo a late pause before letting a successor use the player.
 				with self._segmentPauseLock:
 					if self._player:
-						if self._segmentControlError is None:
+						if host.control_error is None:
 							self._player.pause(False)
 						self._player.stop()
 		except Exception as error:
@@ -678,8 +594,7 @@ class SynthDriver(BaseOneCoreSynthDriver):
 		try:
 			self.cancel()
 		finally:
-			self._segmentLifecycle.terminate()
-			self._segmentLifecycle.join_delivery(1)
+			self._segmentHost.terminate()
 			super().terminate()
 
 
```

- [ ] **Step 4: Run the tests and the acceptance checks**

Run: `python3 -m pytest tests -q 2>&1 | tail -1`
Expected: `1353 passed, 96 skipped, 2 xfailed`

Run: `for i in 1 2 3; do python3 -m pytest tests/test_onecore_segment_drain.py -q 2>&1 | tail -1; done | sed 's/ in .*//'`
Expected: `74 passed` three times.

Run:
```bash
O=addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py
ruff format --check addon | tail -1
grep -n "_segmentLifecycle\|SegmentLifecycle\|CallbackGate" $O
```
Expected: `53 files already formatted`, then no grep output.

- [ ] **Step 5: Commit**

```bash
git add addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py tests/test_onecore_segment_drain.py \
	tests/test_lifecycle_private_access.py
git commit -m "refactor(onecore): run segments through SegmentHost

A segment now enters OneCore's queue when its predecessor drains, so a
setting changed while it waits applies to it, as on the other host engines.
The host stops only the current or draining record (no unconditional stop).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Prove the OneCore wrapper bites (mutations M2a–M2e, after the commit)**

```bash
O=addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py
mutate() { python3 - "$1" "$2" <<'PY'
import sys
p = "addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py"
old, new = sys.argv[1:]
s = open(p).read()
assert s.count(old) == 1, old
open(p, "w").write(s.replace(old, new))
PY
}
check() { timeout 300 python3 -m pytest tests/test_onecore_segment_drain.py -q -p no:cacheprovider 2>&1 | grep -E '^FAILED|passed|failed' | sed 's/ - .*//'; git checkout -- $O; }

mutate '		host.reach(record, "synced")' '		pass'; check   # M2a
mutate '			for record in dropped:
				self._segmentHost.abandon(record)' '			pass'; check   # M2b
mutate '			for record in dropped:
				host.abandon(record)
		try:' '		try:'; check   # M2c
mutate 'fail_accepted_on_control_error=True' 'fail_accepted_on_control_error=False'; check   # M2d
mutate '			if driver._segmentTerminated:
				return RuntimeError("OneCore driver has terminated")' '			if False:
				return RuntimeError("OneCore driver has terminated")'; check   # M2e
git status --short | grep addon
```

Expected:
- M2a: drain never reaches `synced`. `15 failed, 59 passed`:
  - `test_onecore_uses_shared_lifecycle_for_empty_and_pcm_segments[0-commands0]` and `[8-commands1]`
  - `test_onecore_waits_for_tail_sync_before_drain`
  - `test_setting_changed_while_a_segment_waits_applies_before_it`
  - `test_empty_index_and_break_segments_drain_at_known_end[commands0-0-]`, `[commands1-0-1:0]` and `[commands2-8-]`
  - `test_pause_holds_completion_until_resume[0]` and `[8]`
  - `test_pause_resume_reaches_real_player_before_success_event`
  - `test_late_pause_retires_before_cancel_handoff_or_native_close[False-segment]`, `[False-legacy]` and `[False-legacy_after_segment]`
  - `test_cancel_releases_a_segment_queued_behind_ordinary_speech`
  - `test_ordinary_speech_waits_for_contextual_final_sync`
- M2b: control-failure delivery keeps queued records. `1 failed, 73 passed`: `test_control_error_fails_a_segment_queued_behind_ordinary_speech`
- M2c: cancel keeps queued records. `1 failed, 73 passed`: `test_cancel_releases_a_segment_queued_behind_ordinary_speech`
- M2d: OneCore does not opt in to failing accepted work. `1 failed, 73 passed`: `test_control_error_fails_queued_contexts_and_allows_reentrant_cancel`
- M2e: `admission_error` ignores the wrapper's terminate. `1 failed, 73 passed`: `test_onecore_terminate_overlap_preserves_rejected_failure_event`

The final `git status` prints nothing.

---

### Task 3: Final verification

**Files:** none modified.

- [ ] **Step 1: Stability**

Run: `for i in 1 2 3 4 5; do python3 -m pytest tests/test_onecore_segment_drain.py tests/test_segment_host.py tests/test_segment_lifecycle.py tests/test_engine_segment_contract.py tests/test_rhvoice_segment_drain.py tests/test_espeak_segment_drain.py tests/test_sapi5_segment_drain.py -q 2>&1 | tail -1; done | sed 's/ in .*//' | sort | uniq -c`
Expected: one line, `5 309 passed, 4 skipped, 2 xfailed`.

Run: `for i in $(seq 1 20); do python3 -m pytest tests/test_onecore_segment_drain.py -q 2>&1 | tail -1; done | sed 's/ in .*//' | sort | uniq -c`
Expected: one line, `20 74 passed`. If a run fails, record the failing test in the ledger for the final reviewer; see Review Focus 5.

- [ ] **Step 2: The other engines are untouched and green**

Run: `git diff master --stat -- addon/synthDrivers/WorldVoice/driver/VE addon/synthDrivers/WorldVoice/driver/Cerence addon/synthDrivers/WorldVoice/driver/Espeak addon/synthDrivers/WorldVoice/driver/SAPI5 addon/synthDrivers/WorldVoice/driver/RHVoice`
Expected: no output.

Run: `python3 -m pytest tests/test_vocalizer_segment_drain.py -q 2>&1 | tail -1`
Expected: `150 passed, 9 skipped`.

Run: `python3 -m pytest tests/test_engine_segment_contract.py -q -rx 2>&1 | grep -E "XFAIL|passed"`
Expected: `XFAIL` lines for `[VE]` and `[Cerence]` only, then `22 passed, 4 skipped, 2 xfailed`.

- [ ] **Step 3: Full suite and protected paths**

Run: `python3 -m pytest tests -q 2>&1 | tail -1`
Expected: `1353 passed, 96 skipped, 2 xfailed`

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
  1. `docs: add phase 3c OneCore migration design spec`
  2. `docs: add phase 3c implementation plan and amend its spec`
  3. `feat(runtime): prepare hook outside admission and synchronous failure of unacquired segments`
  4. `refactor(onecore): run segments through SegmentHost`
