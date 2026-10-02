"""Resource ownership and producer retirement for the shared lifecycle."""

import importlib.util
import logging
import sys
from threading import Condition, Event, Thread, current_thread

import pytest

from runtime_harness import RUNTIME, load_runtime, load_scheduler


class Call:
    def __init__(self, function):
        self.done = Event()
        self.error = None

        def invoke():
            try:
                function()
            except BaseException as error:
                self.error = error
            finally:
                self.done.set()

        self.thread = Thread(target=invoke, daemon=True)
        self.thread.start()

    def blocked(self):
        assert not self.done.wait(0.05), self.error

    def finish(self):
        assert self.done.wait(1), "lifecycle call did not finish"
        self.thread.join(1)
        if self.error:
            raise self.error


class RecordedEvents(list):
    def __init__(self):
        super().__init__()
        self._condition = Condition()

    def append(self, event):
        with self._condition:
            super().append(event)
            self._condition.notify_all()

    def wait_for_count(self, count):
        with self._condition:
            assert self._condition.wait_for(lambda: len(self) >= count, timeout=1), self


class Hooks:
    def __init__(self):
        self.submitted = []
        self.submitted_after_stops = []
        self.submit_entered = Event()
        self.release_submit = Event()
        self.release_submit.set()
        self.first_submitted = Event()
        self.second_submitted = Event()
        self.boundary_entered = Event()
        self.release_boundary = Event()
        self.release_second_boundary = Event()
        self.retirement_entered = Event()
        self.stop_entered = Event()
        self.stop_exited = Event()
        self.release_stop = Event()
        self.stop_error = None
        self.stop_calls = 0
        self.stop_completions = 0
        self.retired_error = None
        self.playback_entered = Event()
        self.playback_calls = 0
        self.release_playback = Event()
        self.release_playback.set()

    def submit_native(self, operation, commands):
        self.submit_entered.set()
        assert self.release_submit.wait(1)
        self.submitted.append((operation, commands))
        self.submitted_after_stops.append(self.stop_completions)
        self.first_submitted.set()
        if len(self.submitted) == 2:
            self.second_submitted.set()

    def request_stop(self, operation):
        assert not operation.is_valid()
        self.stop_calls += 1
        self.stop_entered.set()
        assert self.release_stop.wait(1)
        self.stop_completions += 1
        self.stop_exited.set()
        if self.stop_error:
            raise self.stop_error

    def wait_native_boundary(self, operation):
        if self.submitted[0][0] is operation:
            self.boundary_entered.set()
            assert self.release_boundary.wait(1)
        else:
            assert self.release_second_boundary.wait(1)

    def wait_native_retired(self, operation):
        self.retirement_entered.set()
        if self.retired_error:
            raise self.retired_error

    def wait_playback_drained(self, operation):
        self.playback_calls += 1
        self.playback_entered.set()
        assert self.release_playback.wait(1)


@pytest.fixture
def env(monkeypatch):
    rt = load_runtime(monkeypatch)
    scheduler = load_scheduler(monkeypatch, rt)
    name = f"{rt.package.__name__}.segmentLifecycle"
    spec = importlib.util.spec_from_file_location(name, RUNTIME / "segmentLifecycle.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    hooks = Hooks()
    lifecycle = module.SegmentLifecycle(hooks)
    events = RecordedEvents()

    def accept(segment, sink=None, on_retired=None):
        context = rt.models.PlaybackContext(object(), segment)
        operation = lifecycle.accept(context, scheduler.CancellationToken(),
                                     events.append if sink is None else sink,
                                     on_retired=on_retired)
        return operation, context

    yield lifecycle, hooks, events, accept
    hooks.release_boundary.set()
    hooks.release_second_boundary.set()
    hooks.release_stop.set()
    hooks.release_submit.set()
    hooks.release_playback.set()
    lifecycle.terminate()


def test_native_boundary_precedes_admission_close(env):
    lifecycle, hooks, events, accept = env
    old, context = accept(1)
    new, _ = accept(2)
    first = Call(lambda: lifecycle.run(old, ("old",)))
    assert hooks.boundary_entered.wait(1)
    lease = lifecycle.admit_producer(old)
    assert lease is not None
    second = Call(lambda: lifecycle.run(new, ("new",)))
    second.blocked()
    assert events == []
    assert len(hooks.submitted) == 1

    hooks.release_boundary.set()
    # The admitted producer still owns the old resource after native return.
    first.blocked()
    assert lifecycle.admit_producer(old) is None
    assert events == []
    assert len(hooks.submitted) == 1
    lifecycle.retire_producer(lease)
    first.finish()
    events.wait_for_count(1)
    assert len(events) == 1
    assert events[0].source_id is context.source_id
    assert events[0].segment_id == context.segment_id
    assert len(hooks.submitted) <= 2
    hooks.release_second_boundary.set()
    second.finish()


def test_nested_lease_retires_before_successor(env):
    lifecycle, hooks, events, accept = env
    old, context = accept(1)
    new, _ = accept(2)
    first = Call(lambda: lifecycle.run(old, ("old",)))
    assert hooks.boundary_entered.wait(1)
    parent = lifecycle.admit_producer(old)
    assert parent is not None
    hooks.release_boundary.set()
    assert hooks.retirement_entered.wait(1)
    assert lifecycle.admit_producer(old) is None
    child = lifecycle.admit_producer(old, parent=parent)
    assert child is not None
    second = Call(lambda: lifecycle.run(new, ("new",)))
    lifecycle.retire_producer(parent)
    lifecycle.retire_producer(parent)
    assert lifecycle.admit_producer(old, parent=parent) is None
    first.blocked()
    assert events == []
    assert len(hooks.submitted) == 1
    lifecycle.retire_producer(child)
    first.finish()
    events.wait_for_count(1)
    assert len(events) == 1
    assert events[0].source_id is context.source_id
    assert events[0].segment_id == context.segment_id
    hooks.release_second_boundary.set()
    second.finish()


def test_cancelled_queued_operation_never_submits(env):
    lifecycle, hooks, events, accept = env
    old, context = accept(1)
    queued, _ = accept(2)
    first = Call(lambda: lifecycle.run(old, ("old",)))
    assert hooks.boundary_entered.wait(1)
    second = Call(lambda: lifecycle.run(queued, ("queued",)))
    lifecycle.cancel(queued)
    second.finish()
    assert len(hooks.submitted) == 1
    assert events == []
    hooks.release_boundary.set()
    first.finish()
    events.wait_for_count(1)
    assert len(hooks.submitted) == 1
    assert len(events) == 1
    assert events[0].source_id is context.source_id


def test_stop_failure_blocks_successor(env):
    lifecycle, hooks, events, accept = env
    old, _ = accept(1)
    new, _ = accept(2)
    hooks.stop_error = RuntimeError("native stop failed")
    first = Call(lambda: lifecycle.run(old, ("old",)))
    assert hooks.boundary_entered.wait(1)
    second = Call(lambda: lifecycle.run(new, ("new",)))
    lifecycle.cancel(old)
    assert hooks.stop_entered.wait(1)
    hooks.release_boundary.set()
    first.blocked()
    second.blocked()
    assert events == []
    assert len(hooks.submitted) == 1
    hooks.release_stop.set()
    first.finish()
    assert second.done.wait(1)
    assert second.error is None
    assert len(hooks.submitted) == 1
    events.wait_for_count(1)
    assert [(event.segment_id, event.kind.value, event.error) for event in events] == [
        (2, "segment_failed", hooks.stop_error)]
    assert new not in lifecycle._operations


def test_retirement_failure_latches_core_fault(env):
    lifecycle, hooks, events, accept = env
    old, context = accept(1)
    new, _ = accept(2)
    hooks.retired_error = RuntimeError("retirement unproven")
    hooks.release_boundary.set()
    lifecycle.run(old, ("old",))
    events.wait_for_count(1)
    assert len(events) == 1
    assert events[0].kind.value == "segment_failed"
    assert events[0].source_id is context.source_id
    lifecycle.run(new, ("new",))
    events.wait_for_count(2)
    assert events[1].kind.value == "segment_failed"
    assert events[1].segment_id == 2
    assert events[1].error is hooks.retired_error
    assert len(hooks.submitted) == 1


def test_operation_cannot_submit_twice(env):
    lifecycle, hooks, events, accept = env
    old, _ = accept(1)
    hooks.release_boundary.set()
    lifecycle.run(old, ("old",))
    events.wait_for_count(1)
    with pytest.raises(RuntimeError, match="already run"):
        lifecycle.run(old, ("again",))
    assert len(hooks.submitted) == 1
    assert len(events) == 1


def test_failed_queued_operation_never_submits(env):
    lifecycle, hooks, events, accept = env
    old, _ = accept(1)
    queued, context = accept(2)
    first = Call(lambda: lifecycle.run(old, ("old",)))
    assert hooks.boundary_entered.wait(1)
    second = Call(lambda: lifecycle.run(queued, ("queued",)))
    lifecycle.fail(queued, RuntimeError("before native call"))
    hooks.release_boundary.set()
    first.finish()
    second.finish()
    events.wait_for_count(2)
    assert len(hooks.submitted) == 1
    assert len(events) == 2
    failed = [event for event in events if event.source_id is context.source_id]
    assert len(failed) == 1
    assert failed[0].kind.value == "segment_failed"


def test_late_cancel_cannot_stop_successor_resource(env):
    lifecycle, hooks, events, accept = env
    old, _ = accept(1)
    new, _ = accept(2)
    hooks.release_boundary.set()
    lifecycle.run(old, ("old",))
    events.wait_for_count(1)
    second = Call(lambda: lifecycle.run(new, ("new",)))
    assert hooks.second_submitted.wait(1)
    lifecycle.cancel(old)
    assert not hooks.stop_entered.wait(0.05)
    hooks.release_second_boundary.set()
    second.finish()
    events.wait_for_count(2)
    assert len(events) == 2


def test_token_cancel_during_playback_stops_before_handoff(env):
    lifecycle, hooks, events, accept = env
    old, _ = accept(1)
    new, _ = accept(2)
    hooks.release_boundary.set()
    hooks.release_playback.clear()
    first = Call(lambda: lifecycle.run(old, ("old",)))
    assert hooks.playback_entered.wait(1)
    second = Call(lambda: lifecycle.run(new, ("new",)))
    old.work.token.cancel()
    hooks.release_playback.set()
    assert hooks.stop_entered.wait(1)
    first.blocked()
    second.blocked()
    assert events == []
    assert len(hooks.submitted) == 1
    hooks.release_stop.set()
    first.finish()
    assert hooks.playback_calls == 2
    hooks.release_second_boundary.set()
    second.finish()
    events.wait_for_count(1)
    assert len(events) == 1


@pytest.mark.parametrize("invalidate", ["cancel", "fail"])
def test_invalidated_operation_waits_for_player_cleanup(env, invalidate):
    lifecycle, hooks, events, accept = env
    old, context = accept(1)
    new, _ = accept(2)
    first = Call(lambda: lifecycle.run(old, ("old",)))
    assert hooks.boundary_entered.wait(1)
    second = Call(lambda: lifecycle.run(new, ("new",)))
    hooks.release_stop.set()
    hooks.release_playback.clear()
    if invalidate == "cancel":
        lifecycle.cancel(old)
    else:
        lifecycle.fail(old, RuntimeError("old segment failed"))
    hooks.release_boundary.set()
    assert hooks.playback_entered.wait(1)
    first.blocked()
    second.blocked()
    assert events == []
    assert len(hooks.submitted) == 1
    hooks.release_playback.set()
    first.finish()
    if invalidate == "fail":
        events.wait_for_count(1)
    assert len(events) == (0 if invalidate == "cancel" else 1)
    if events:
        assert events[0].source_id is context.source_id
        assert events[0].kind.value == "segment_failed"
    hooks.release_second_boundary.set()
    second.finish()


def test_stop_before_native_submission_requires_post_submit_stop(env):
    lifecycle, hooks, events, accept = env
    old, _ = accept(1)
    new, _ = accept(2)
    hooks.release_submit.clear()
    hooks.release_stop.set()
    hooks.release_boundary.set()
    first = Call(lambda: lifecycle.run(old, ("old",)))
    assert hooks.submit_entered.wait(1)
    second = Call(lambda: lifecycle.run(new, ("new",)))
    lifecycle.cancel(old)
    assert hooks.stop_exited.wait(1)
    # The first stop completed while the native submit hook had not submitted.
    assert hooks.stop_calls == 1
    assert hooks.submitted == []
    hooks.release_submit.set()
    first.finish()
    assert hooks.stop_calls == 2
    assert hooks.submitted[0][0] is old
    assert hooks.submitted_after_stops[0] == 1
    hooks.release_second_boundary.set()
    second.finish()
    assert hooks.submitted_after_stops == [1, 2]
    events.wait_for_count(1)
    assert len(events) == 1


def test_cancel_before_deferred_delivery_is_silent(env):
    lifecycle, hooks, events, accept = env
    hooks.release_boundary.set()
    hooks.release_second_boundary.set()
    first_entered = Event()
    release_first = Event()
    last_delivered = Event()

    def first_sink(event):
        first_entered.set()
        assert release_first.wait(1)
        events.append(event)

    first, first_context = accept(1, first_sink)
    cancelled, _ = accept(2)
    last, last_context = accept(3, lambda event: (events.append(event), last_delivered.set()))
    try:
        Call(lambda: lifecycle.run(first, ("first",))).finish()
        assert first_entered.wait(1)
        Call(lambda: lifecycle.run(cancelled, ("cancelled",))).finish()
        lifecycle.cancel(cancelled)
        Call(lambda: lifecycle.run(last, ("last",))).finish()
    finally:
        release_first.set()
    assert last_delivered.wait(1)
    assert [(event.source_id, event.segment_id) for event in events] == [
        (first_context.source_id, 1), (last_context.source_id, 3)]


def test_failure_wins_over_queued_success(env):
    lifecycle, hooks, events, accept = env
    hooks.release_boundary.set()
    hooks.release_second_boundary.set()
    first_entered = Event()
    release_first = Event()
    failed_delivered = Event()

    def first_sink(event):
        first_entered.set()
        assert release_first.wait(1)
        events.append(event)

    first, _ = accept(1, first_sink)
    failed, failed_context = accept(2, lambda event: (events.append(event), failed_delivered.set()))
    first_error = RuntimeError("first failure")
    try:
        Call(lambda: lifecycle.run(first, ("first",))).finish()
        assert first_entered.wait(1)
        Call(lambda: lifecycle.run(failed, ("failed",))).finish()
        lifecycle.fail(failed, first_error)
        lifecycle.fail(failed, RuntimeError("second failure"))
    finally:
        release_first.set()
    assert failed_delivered.wait(1)
    assert len(events) == 2
    assert events[1].kind.value == "segment_failed"
    assert events[1].source_id is failed_context.source_id
    assert events[1].segment_id == 2
    assert events[1].error is first_error


def test_sink_can_cancel_and_terminate_without_self_join(env):
    lifecycle, hooks, events, accept = env
    hooks.release_boundary.set()
    sink_done = Event()
    run_thread = []
    sink_thread = []
    operation = None

    def sink(event):
        sink_thread.append(current_thread())
        events.append(event)
        lifecycle.cancel(operation)
        lifecycle.terminate()
        sink_done.set()

    operation, context = accept(1, sink)

    def run():
        run_thread.append(current_thread())
        lifecycle.run(operation, ("first",))

    Call(run).finish()
    assert sink_done.wait(1)
    assert sink_thread[0] is not run_thread[0]
    assert [(event.kind.value, event.source_id, event.segment_id) for event in events] == [
        ("segment_drained", context.source_id, 1)]


def test_raising_sink_does_not_relabel_successor(env, caplog):
    lifecycle, hooks, events, accept = env
    hooks.release_boundary.set()
    hooks.release_second_boundary.set()
    first_entered = Event()
    second_delivered = Event()
    run_threads = []
    sink_threads = []

    def raising_sink(event):
        sink_threads.append(current_thread())
        events.append(event)
        first_entered.set()
        raise RuntimeError("sink failure")

    def second_sink(event):
        sink_threads.append(current_thread())
        events.append(event)
        second_delivered.set()

    first, first_context = accept(1, raising_sink)
    second, second_context = accept(2, second_sink)

    def run(operation, commands):
        run_threads.append(current_thread())
        lifecycle.run(operation, commands)

    with caplog.at_level(logging.ERROR):
        Call(lambda: run(first, ("first",))).finish()
        assert first_entered.wait(1)
        Call(lambda: run(second, ("second",))).finish()
        assert second_delivered.wait(1)
    assert all(thread not in run_threads for thread in sink_threads)
    assert sink_threads[0] is sink_threads[1]
    assert [(event.kind.value, event.source_id, event.segment_id) for event in events] == [
        ("segment_drained", first_context.source_id, 1),
        ("segment_drained", second_context.source_id, 2)]
    failures = [record for record in caplog.records
                if "segment event sink failed" in record.getMessage().lower()]
    assert len(failures) == 1
    assert failures[0].exc_info[0] is RuntimeError


def test_terminate_invalidates_queued_and_active_before_worker_shutdown(env, monkeypatch):
    lifecycle, hooks, events, accept = env
    hooks.release_boundary.set()
    hooks.release_second_boundary.set()
    hooks.release_stop.set()
    first_entered = Event()
    release_first = Event()
    active_at_boundary = Event()
    release_active = Event()
    cancel_entered = Event()
    allow_cancel = Event()

    def first_sink(event):
        first_entered.set()
        assert release_first.wait(3)
        events.append(event)

    first, first_context = accept(1, first_sink)
    queued, _ = accept(2)
    active, _ = accept(3)
    original_boundary = hooks.wait_native_boundary

    def boundary(operation):
        if operation is active:
            active_at_boundary.set()
            assert release_active.wait(3)
        else:
            original_boundary(operation)

    monkeypatch.setattr(hooks, "wait_native_boundary", boundary)
    original_cancel = lifecycle.cancel

    def paused_cancel(operation):
        cancel_entered.set()
        assert allow_cancel.wait(3)
        original_cancel(operation)

    # Pause the old terminate() between publishing shutdown and cancel().
    # The corrected implementation invalidates under the condition first.
    monkeypatch.setattr(lifecycle, "cancel", paused_cancel)
    termination = None
    active_call = None
    try:
        Call(lambda: lifecycle.run(first, ("first",))).finish()
        assert first_entered.wait(1)
        Call(lambda: lifecycle.run(queued, ("queued",))).finish()
        active_call = Call(lambda: lifecycle.run(active, ("active",)))
        assert active_at_boundary.wait(1)
        termination = Call(lifecycle.terminate)
        with lifecycle._condition:
            assert lifecycle._condition.wait_for(lambda: lifecycle._terminated, timeout=1)
        old_gap = queued.work.is_valid()
        if old_gap:
            assert cancel_entered.wait(1)
        else:
            allow_cancel.set()
            assert termination.done.wait(1)
        release_first.set()
        lifecycle._delivery_thread.join(1)
        assert not lifecycle._delivery_thread.is_alive()
        release_active.set()
        active_call.finish()
        allow_cancel.set()
        termination.finish()
        assert [(event.source_id, event.segment_id) for event in events] == [
            (first_context.source_id, 1)]
        assert not lifecycle._delivery_queue
        assert not lifecycle._operations
    finally:
        release_first.set()
        release_active.set()
        allow_cancel.set()
        if active_call is not None:
            active_call.done.wait(1)
        if termination is not None:
            termination.done.wait(1)


def test_terminate_blocks_new_acceptance(env):
    lifecycle, _, events, accept = env
    lifecycle.terminate()
    with pytest.raises(RuntimeError, match="terminated"):
        accept(1)


def test_pending_operation_rejection_delivers_after_latched_fault(env):
    lifecycle, hooks, events, accept = env
    pending, context = accept(18)
    error = OSError("native resources unsafe")
    lifecycle._latch_fault(pending, error)
    lifecycle.reject_pending(pending, error)
    events.wait_for_count(1)
    assert [(event.source_id, event.segment_id, event.error) for event in events] == [
        (context.source_id, 18, error)]
    assert hooks.submitted == []


def test_retirement_callback_runs_when_cancel_suppresses_delivery(env):
    lifecycle, hooks, events, accept = env
    retired = Event()
    operation, _ = accept(18, on_retired=lambda owner: retired.set())
    operation.work.token.cancel()
    lifecycle.reject_pending(operation, RuntimeError("never submitted"))
    assert retired.wait(1)
    assert operation not in lifecycle._operations
    assert events == []
    assert hooks.submitted == []


def test_reject_new_delivers_after_lifecycle_termination(env):
    lifecycle, hooks, events, _ = env
    lifecycle.terminate()
    context = sys.modules[f"{lifecycle.__class__.__module__.rsplit('.', 1)[0]}.models"].PlaybackContext(
        object(), 19)
    token = sys.modules[f"{lifecycle.__class__.__module__.rsplit('.', 1)[0]}.scheduler"].CancellationToken()
    error = RuntimeError("driver terminated")
    operation = lifecycle.reject_new(context, token, events.append, error)
    events.wait_for_count(1)
    assert operation.work.context is context
    assert [(event.source_id, event.segment_id, event.error) for event in events] == [
        (context.source_id, 19, error)]
    assert hooks.submitted == []


def test_terminate_cancels_previously_accepted_pending_rejection(env):
    lifecycle, hooks, _, accept = env
    entered, release, rejected = Event(), Event(), RecordedEvents()
    first, _ = accept(20, lambda event: (entered.set(), release.wait(2)))
    lifecycle.reject_pending(first, RuntimeError("first rejection"))
    assert entered.wait(1)
    second, _ = accept(21, rejected.append)
    error = OSError("second rejection")
    lifecycle.reject_pending(second, error)
    lifecycle.terminate()
    release.set()
    with lifecycle._condition:
        assert lifecycle._condition.wait_for(lambda: second not in lifecycle._operations, 1)
    assert rejected == []
    assert hooks.submitted == []



def _hold_resource(env):
    lifecycle, hooks, events, accept = env
    owner, _ = accept(1)
    call = Call(lambda: lifecycle.run(owner, ("owner",)))
    assert hooks.boundary_entered.wait(1)
    return owner, call


class CountingToken:
    """A real CancellationToken that counts how often waiters poll it."""

    def __init__(self, inner, start_delay=0):
        self._inner = inner
        self.checks = 0
        # Holds the waiter's first read, as a thread that starts late would.
        self._start_delay = start_delay

    def is_cancelled(self):
        if self.checks == 0:
            Event().wait(self._start_delay)
        self.checks += 1
        return self._inner.is_cancelled()

    def add_callback(self, callback):
        return self._inner.add_callback(callback)

    def cancel(self):
        self._inner.cancel()


def _accept_counting(env, owner, segment, start_delay=0):
    lifecycle, hooks, events, accept = env
    token = CountingToken(type(owner.work.token)(), start_delay)
    context = type(owner.work.context)(object(), segment)
    return lifecycle.accept(context, token, events.append), token


class WaitObserver:
    """Proxy for the lifecycle condition that tracks which threads are inside wait()."""

    def __init__(self, condition):
        self._condition = condition
        self.waiting = set()

    def __enter__(self):
        return self._condition.__enter__()

    def __exit__(self, *exc):
        return self._condition.__exit__(*exc)

    def __getattr__(self, name):
        return getattr(self._condition, name)

    def wait(self, timeout=None):
        self.waiting.add(current_thread())
        try:
            return self._condition.wait(timeout)
        finally:
            self.waiting.discard(current_thread())


def _observe_waits(lifecycle):
    observer = WaitObserver(lifecycle._condition)
    lifecycle._condition = observer
    return observer


def _wait_until_waiting(observer, call):
    # Measure only once the waiter has actually blocked; its reads before
    # blocking are legitimate and must not count as polling.
    deadline = Event()
    for _ in range(200):
        if call.thread in observer.waiting:
            return
        deadline.wait(0.005)
    raise AssertionError("waiter never blocked on the lifecycle condition")


def _assert_not_polled(read_count, window=0.2):
    # A 50 ms poll would re-check about four times in this window.
    before = read_count()
    Event().wait(window)
    assert read_count() - before <= 1, "waiter is polling instead of waiting for a notification"


@pytest.mark.parametrize("start_delay", [0, 0.06])
def test_queued_run_does_not_poll_its_token(env, start_delay):
    lifecycle, hooks, events, accept = env
    owner, owner_call = _hold_resource(env)
    queued, token = _accept_counting(env, owner, 2, start_delay)
    observer = _observe_waits(lifecycle)
    waiting = Call(lambda: lifecycle.run(queued, ("queued",)))
    _wait_until_waiting(observer, waiting)
    _assert_not_polled(lambda: token.checks)
    token.cancel()
    waiting.finish()
    hooks.release_boundary.set()
    owner_call.finish()


@pytest.mark.parametrize("cancel", ["token", "work", "fail"])
def test_queued_run_wakes_when_cancelled(env, cancel):
    lifecycle, hooks, events, accept = env
    _, owner_call = _hold_resource(env)
    queued, _ = accept(2)
    waiting = Call(lambda: lifecycle.run(queued, ("queued",)))
    waiting.blocked()
    if cancel == "token":
        queued.work.token.cancel()
    elif cancel == "work":
        queued.work.cancel()
    else:
        queued.work.fail(RuntimeError("failed while queued"))
    assert waiting.done.wait(0.5), "queued run was not woken by cancellation"
    waiting.finish()
    assert len(hooks.submitted) == 1
    hooks.release_boundary.set()
    owner_call.finish()


def test_operation_queries_follow_run_and_retirement(env):
    lifecycle, hooks, events, accept = env
    sink = events.append
    operation, _ = accept(1, sink=sink)
    assert operation.sink is sink
    assert not operation.has_started()
    assert not operation.is_retired()
    call = Call(lambda: lifecycle.run(operation, ("hello",)))
    assert hooks.boundary_entered.wait(1)
    assert operation.has_started()
    assert not operation.is_retired()
    hooks.release_boundary.set()
    call.finish()
    assert operation.is_retired()


def test_rejected_operation_reports_started_and_retired(env):
    lifecycle, hooks, events, accept = env
    operation, _ = accept(1)
    lifecycle.reject_pending(operation, RuntimeError("rejected"))
    assert operation.has_started()
    assert operation.is_retired()


def test_delivery_thread_identity_and_join(env):
    lifecycle, hooks, events, accept = env
    seen, joined = [], Event()

    def sink(event):
        seen.append(lifecycle.on_delivery_thread())
        lifecycle.join_delivery(1)  # Must not try to join itself.
        joined.set()

    operation, _ = accept(1, sink=sink)
    hooks.release_boundary.set()
    Call(lambda: lifecycle.run(operation, ("hello",))).finish()
    assert joined.wait(1)
    assert seen == [True]
    assert not lifecycle.on_delivery_thread()
    lifecycle.terminate()
    lifecycle.join_delivery(1)
    assert not lifecycle._delivery_thread.is_alive()


def test_wait_idle_returns_true_when_resource_is_released(env):
    lifecycle, hooks, events, accept = env
    assert lifecycle.wait_idle() is True
    _, owner_call = _hold_resource(env)
    assert lifecycle.is_resource_busy()
    results = []
    waiting = Call(lambda: results.append(lifecycle.wait_idle()))
    waiting.blocked()
    hooks.release_boundary.set()
    owner_call.finish()
    waiting.finish()
    assert results == [True]
    assert not lifecycle.is_resource_busy()


def test_wait_idle_wakes_on_token_cancel_without_polling(env):
    lifecycle, hooks, events, accept = env
    owner, owner_call = _hold_resource(env)
    token = CountingToken(type(owner.work.token)())
    results = []
    observer = _observe_waits(lifecycle)
    waiting = Call(lambda: results.append(lifecycle.wait_idle(token=token, still_wanted=lambda: not token.is_cancelled())))
    _wait_until_waiting(observer, waiting)
    _assert_not_polled(lambda: token.checks)
    token.cancel()
    assert waiting.done.wait(0.5), "wait_idle was not woken by token cancellation"
    waiting.finish()
    assert results == [False]
    hooks.release_boundary.set()
    owner_call.finish()


def test_wait_idle_rechecks_still_wanted_on_wake_waiters(env):
    lifecycle, hooks, events, accept = env
    _, owner_call = _hold_resource(env)
    wanted, checks, results = [True], [0], []

    def still_wanted():
        checks[0] += 1
        return wanted[0]

    observer = _observe_waits(lifecycle)
    waiting = Call(lambda: results.append(lifecycle.wait_idle(still_wanted=still_wanted)))
    _wait_until_waiting(observer, waiting)
    _assert_not_polled(lambda: checks[0])
    wanted[0] = False
    lifecycle.wake_waiters()
    assert waiting.done.wait(0.5), "wait_idle was not woken by wake_waiters"
    waiting.finish()
    assert results == [False]
    hooks.release_boundary.set()
    owner_call.finish()
