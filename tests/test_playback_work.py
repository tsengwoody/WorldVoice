"""Pure work identity and explicit native/callback handoff barriers."""

from dataclasses import FrozenInstanceError
from threading import Barrier, Event, Thread

import pytest

from runtime_harness import forbid_legacy_runtime_imports, load_runtime, load_scheduler, rt


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
        assert not self.done.wait(0.05), self.error

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


def test_playback_helper_loads_without_nvda_or_native_driver(monkeypatch):
    with forbid_legacy_runtime_imports(monkeypatch):
        loaded = load_runtime(monkeypatch, "worldvoice_playback_work_pure_test")
    assert loaded.playback_work.PlaybackWork is not None


def test_drain_support_is_immutable(work_env):
    rt, *_ = work_env
    support = rt.playback_work.DrainSupport(True, "native-profile", "confirmed callback contract")
    assert (support.supported, support.profile, support.reason) == (
        True, "native-profile", "confirmed callback contract")
    with pytest.raises(FrozenInstanceError):
        support.supported = False


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


def test_callbacks_require_open_valid_native_work(work_env):
    rt, _, _, _, work = work_env
    gate = rt.playback_work.CallbackGate()
    assert gate.enter_callback() is None
    call_token = gate.begin_native(work)
    lease = gate.enter_callback()
    assert lease.work is work
    assert lease.call_token is call_token
    with pytest.raises(AttributeError):
        lease.work = new_work(rt, work)
    with pytest.raises(AttributeError):
        lease.call_token = object()
    gate.close(call_token)
    gate.close(call_token)
    assert gate.enter_callback() is None
    lease.close()
    lease.close()
    gate.wait_retired(call_token)
    gate.finish_native(call_token)


@pytest.mark.parametrize("invalidate", ["cancel", "token", "fail", "drain"])
def test_invalid_work_refuses_callback_admission(work_env, invalidate):
    rt, token, _, _, work = work_env
    gate = rt.playback_work.CallbackGate()
    call_token = gate.begin_native(work)
    if invalidate == "token":
        token.cancel()
    elif invalidate == "fail":
        work.fail(RuntimeError("native failed"))
    elif invalidate == "drain":
        work.complete_drained()
    else:
        work.cancel()
    assert gate.enter_callback() is None
    gate.finish_native(call_token)


def test_zero_callbacks_does_not_declare_native_quiescence(work_env):
    rt, _, _, _, work = work_env
    gate = rt.playback_work.CallbackGate()
    previous = gate.begin_native(work)
    gate.close(previous)
    # Retirement only observes admitted leases, not the SDK contract.
    assert ThreadCall(lambda: gate.wait_retired(previous)).finish() is None
    next_call = ThreadCall(lambda: gate.begin_native(new_work(rt, work)))
    try:
        next_call.assert_blocked()
    finally:
        gate.finish_native(previous)
    following = next_call.finish()
    assert following is not previous
    gate.finish_native(following)


def test_native_finish_does_not_release_an_entered_callback(work_env):
    rt, _, context, _, work = work_env
    gate = rt.playback_work.CallbackGate()
    previous = gate.begin_native(work)
    lease = gate.enter_callback()
    gate.finish_native(previous)
    assert gate.enter_callback() is None
    next_work = new_work(rt, work)
    next_call = ThreadCall(lambda: gate.begin_native(next_work))
    retired = ThreadCall(lambda: gate.wait_retired(previous))
    try:
        next_call.assert_blocked()
        retired.assert_blocked()
        assert lease.work is work
        assert lease.work.context is context
    finally:
        lease.close()
    assert retired.finish() is None
    following = next_call.finish()
    # Old identity/duplicate release cannot alter the new call's admission.
    gate.close(previous)
    gate.finish_native(previous)
    lease.close()
    new_lease = gate.enter_callback()
    assert new_lease.work is next_work
    assert new_lease.call_token is following
    assert lease.work.context is context
    new_lease.close()
    gate.finish_native(following)


def test_retirement_waits_for_every_lease(work_env):
    rt, _, _, _, work = work_env
    gate = rt.playback_work.CallbackGate()
    call_token = gate.begin_native(work)
    first, second = gate.enter_callback(), gate.enter_callback()
    gate.close(call_token)
    retired = ThreadCall(lambda: gate.wait_retired(call_token))
    try:
        retired.assert_blocked()
        first.close()
        first.close()
        retired.assert_blocked()
    finally:
        second.close()
    assert retired.finish() is None
    gate.finish_native(call_token)


def test_cancelled_admitted_feed_stops_before_new_native_work(work_env):
    rt, _, _, events, work = work_env
    gate = rt.playback_work.CallbackGate()
    previous = gate.begin_native(work)
    admitted, start_feed, feed_started, finish_feed = (Event() for _ in range(4))
    actions = []
    playing = Event()

    def stop():
        actions.append("stop old playback")
        playing.clear()

    def callback_feed():
        lease = gate.enter_callback()
        assert lease is not None
        try:
            admitted.set()
            assert start_feed.wait(1)
            # Real feed runs outside the gate: it can start after cancel's stop.
            actions.append("old real feed")
            playing.set()
            feed_started.set()
            assert finish_feed.wait(1)
        finally:
            if not lease.work.is_valid():
                stop()
            lease.close()

    old_feed = ThreadCall(callback_feed)
    assert admitted.wait(1)
    gate.close(previous)
    work.cancel()
    stop()
    gate.finish_native(previous)
    next_work = new_work(rt, work)

    def next_native():
        call_token = gate.begin_native(next_work)
        assert not playing.is_set()
        actions.append("new native started")
        return call_token

    following = ThreadCall(next_native)
    try:
        following.assert_blocked()
        start_feed.set()
        assert feed_started.wait(1)
        assert playing.is_set()
        following.assert_blocked()
    finally:
        start_feed.set()
        finish_feed.set()
    old_feed.finish()
    gate.finish_native(following.finish())
    assert actions == ["stop old playback", "old real feed", "stop old playback", "new native started"]
    assert work.complete_drained() is False
    assert events == []
