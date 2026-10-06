"""Pure work identity and explicit native/callback handoff barriers."""

from threading import Barrier, Event, Thread

import pytest

from runtime_harness import load_scheduler, rt
from waiting import stays_unset


@pytest.fixture
def work_env(monkeypatch, rt):
    scheduler = load_scheduler(monkeypatch, rt)
    token = scheduler.CancellationToken()
    context = rt.models.PlaybackContext(object(), 17)
    events = []
    work = rt.playback_work.PlaybackWork(context, token, events.append)
    return rt, token, context, events, work


class ThreadCall:
    """Bounded waits surface deadlocks without leaving non-daemon workers."""

    def __init__(self, function):
        self.started = Event()
        self.done = Event()
        self.result = None
        self.error = None

        def run():
            self.started.set()
            try:
                self.result = function()
            except BaseException as error:
                self.error = error
            finally:
                self.done.set()

        self.thread = Thread(target=run, daemon=True)
        self.thread.start()
        assert self.started.wait(1)

    def assert_blocked(self):
        stays_unset(self.done, message=self.error)

    def finish(self):
        assert self.done.wait(1), "Lifecycle operation did not retire"
        self.thread.join(1)
        if self.error is not None:
            raise self.error
        return self.result


def new_work(rt, previous, segment_id=18):
    token = type(previous.token)()
    return rt.playback_work.PlaybackWork(
        rt.models.PlaybackContext(object(), segment_id), token, lambda event: None)


def test_unverified_drain_support_helpers(work_env):
    rt, *_ = work_env
    assert rt.playback_work.runtime_profile("RHVoice", None, "wasapi") == "RHVoice/unknown/wasapi"
    support = rt.playback_work.unverified_drain_support("p", "physical playback is")
    assert support == rt.playback_work.DrainSupport(
        True, "p", "DRAIN explicitly enabled; physical playback is unverified")


def test_drain_uses_original_context_once(work_env):
    rt, token, context, events, work = work_env
    assert work.context is context
    assert work.token is token
    assert work.is_valid() is True
    assert work.complete_drained() is True
    assert work.complete_drained() is False
    assert work.fail(RuntimeError("late error")) is False
    assert work.is_valid() is False
    assert work.error is None
    assert len(events) == 1
    event = events[0]
    assert event.kind is rt.models.EventKind.SEGMENT_DRAINED
    assert event.source_id is context.source_id
    assert event.segment_id == 17
    assert event.error is None
    with pytest.raises(AttributeError):
        work.context = rt.models.PlaybackContext(object(), 18)
    with pytest.raises(AttributeError):
        work.token = token


def test_first_fault_wins(work_env):
    rt, _, context, events, work = work_env
    first, second = RuntimeError("first"), RuntimeError("second")
    assert work.fail(first) is True
    assert work.fail(second) is False
    assert work.error is first
    assert work.complete_drained() is False
    assert work.is_valid() is False
    assert len(events) == 1
    event = events[0]
    assert event.kind is rt.models.EventKind.SEGMENT_FAILED
    assert event.source_id is context.source_id
    assert event.segment_id == 17
    assert event.error is first
    with pytest.raises(AttributeError):
        work.error = second


def test_cancelled_work_never_reports_drain(work_env):
    _, token, _, events, work = work_env
    token.cancel()
    assert work.is_valid() is False
    assert work.complete_drained() is False
    assert events == []


def test_direct_cancel_is_terminal_and_silent(work_env):
    _, token, _, events, work = work_env
    assert work.cancel() is None
    work.cancel()
    assert token.is_cancelled() is False
    assert work.is_valid() is False
    assert work.complete_drained() is False
    assert work.fail(RuntimeError("after cancellation")) is False
    assert events == []


@pytest.mark.parametrize("terminal", ["complete_drained", "fail"])
def test_event_sink_can_reenter_cancel_without_deadlock(work_env, terminal):
    rt, token, context, _, _ = work_env
    events = []

    def sink(event):
        events.append(event)
        work.cancel()

    work = rt.playback_work.PlaybackWork(context, token, sink)
    operation = work.complete_drained if terminal == "complete_drained" else (
        lambda: work.fail(RuntimeError("callback processing")))
    assert ThreadCall(operation).finish() is True
    assert len(events) == 1


def test_concurrent_terminal_calls_notify_only_once(work_env):
    _, _, _, events, work = work_env
    start = Barrier(3)

    def terminate(operation):
        start.wait(1)
        return operation()

    first = ThreadCall(lambda: terminate(work.complete_drained))
    second = ThreadCall(lambda: terminate(lambda: work.fail(RuntimeError("fault"))))
    start.wait(1)
    assert sorted((first.finish(), second.finish())) == [False, True]
    assert len(events) == 1


def test_direct_cancel_notifies_owner_after_releasing_the_work_lock(work_env):
    rt, token, context, events, _ = work_env
    seen = []
    work = rt.playback_work.PlaybackWork(context, token, events.append,
                                         on_cancel=lambda: seen.append(work.is_valid()))
    finished = Event()
    Thread(target=lambda: (work.cancel(), finished.set()), daemon=True).start()
    assert finished.wait(1), "on_cancel ran while the work lock was held"
    assert seen == [False]
    assert events == []


@pytest.mark.parametrize("finish", ["fail", "complete_drained"])
def test_terminal_event_notifies_owner_after_releasing_the_work_lock(work_env, finish):
    rt, token, context, events, _ = work_env
    seen = []
    work = rt.playback_work.PlaybackWork(context, token, events.append,
                                         on_cancel=lambda: seen.append(work.is_valid()))
    finished = Event()
    action = (lambda: work.fail(RuntimeError("failed"))) if finish == "fail" else work.complete_drained
    Thread(target=lambda: (action(), finished.set()), daemon=True).start()
    assert finished.wait(1), "on_cancel ran while the work lock was held"
    assert seen == [False]
    assert len(events) == 1
