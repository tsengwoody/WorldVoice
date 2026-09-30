"""Resource ownership and producer retirement for the shared lifecycle."""

import importlib.util
import sys
from threading import Event, Thread

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


class Hooks:
    def __init__(self):
        self.submitted = []
        self.first_submitted = Event()
        self.second_submitted = Event()
        self.boundary_entered = Event()
        self.release_boundary = Event()
        self.release_second_boundary = Event()
        self.retirement_entered = Event()
        self.stop_entered = Event()
        self.release_stop = Event()
        self.stop_error = None
        self.retired_error = None
        self.playback_entered = Event()
        self.release_playback = Event()
        self.release_playback.set()

    def submit_native(self, operation, commands):
        self.submitted.append((operation, commands))
        self.first_submitted.set()
        if len(self.submitted) == 2:
            self.second_submitted.set()

    def request_stop(self, operation):
        assert not operation.is_valid()
        self.stop_entered.set()
        assert self.release_stop.wait(1)
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
    events = []

    def accept(segment):
        context = rt.models.PlaybackContext(object(), segment)
        operation = lifecycle.accept(context, scheduler.CancellationToken(), events.append)
        return operation, context

    yield lifecycle, hooks, events, accept
    hooks.release_boundary.set()
    hooks.release_second_boundary.set()
    hooks.release_stop.set()
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
    assert isinstance(second.error, RuntimeError)
    assert len(hooks.submitted) == 1
    assert events == []


def test_retirement_failure_latches_core_fault(env):
    lifecycle, hooks, events, accept = env
    old, context = accept(1)
    new, _ = accept(2)
    hooks.retired_error = RuntimeError("retirement unproven")
    hooks.release_boundary.set()
    lifecycle.run(old, ("old",))
    assert len(events) == 1
    assert events[0].kind.value == "segment_failed"
    assert events[0].source_id is context.source_id
    with pytest.raises(RuntimeError, match="safely reused"):
        lifecycle.run(new, ("new",))
    assert len(hooks.submitted) == 1


def test_operation_cannot_submit_twice(env):
    lifecycle, hooks, events, accept = env
    old, _ = accept(1)
    hooks.release_boundary.set()
    lifecycle.run(old, ("old",))
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
    second = Call(lambda: lifecycle.run(new, ("new",)))
    assert hooks.second_submitted.wait(1)
    lifecycle.cancel(old)
    assert not hooks.stop_entered.wait(0.05)
    hooks.release_second_boundary.set()
    second.finish()
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
    hooks.release_second_boundary.set()
    second.finish()
    assert len(events) == 1
