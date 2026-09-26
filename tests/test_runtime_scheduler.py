"""Scheduler contracts, including deterministic cancellation interleavings."""

import builtins
from concurrent.futures import CancelledError
from threading import Event, Lock, Thread

import pytest

from runtime_harness import FakePlayback, RecordingOutput, load_scheduler, rt


@pytest.fixture
def scheduler(monkeypatch, rt):
    original = builtins.__import__

    def pure_import(name, *args, **kwargs):
        assert name not in {"synthDriverHandler", "config", "logHandler"}
        assert "synthDrivers" not in name and ".compat" not in name
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", pure_import)
    return load_scheduler(monkeypatch, rt)


@pytest.fixture
def output():
    return RecordingOutput()


@pytest.fixture
def manager(scheduler, output):
    manager = scheduler.TaskManager(output)
    yield manager
    manager.shutdown()


@pytest.fixture
def port():
    return FakePlayback()


def event(manager, rt, port, kind="DONE", index=None):
    manager.on_event(rt.models.PlaybackEvent(getattr(rt.models.EventKind, kind), port.source_id, index))


def speech(manager, port):
    request = manager.new_request()
    future = manager.append_speech(request, port, "Fake:a", ("hello",))
    assert manager.submit_request(request)
    assert port.entered.wait(1)
    return request, future


def test_synchronous_done_finishes_once(manager, port, output, rt, scheduler):
    port.on_speak = lambda: (event(manager, rt, port), event(manager, rt, port))
    request, future = speech(manager, port)
    assert future.result(1) is True
    assert output.wait_done() == 1
    assert request.state is scheduler.RequestState.COMPLETED
    assert request.remaining == 0
    assert manager.submit_request(request) is False
    assert port.activated == ["Fake:a"]
    assert port.spoken == [(("hello",), request.token)]


def test_synchronous_done_advances_only_after_speak_returns(manager, port, output, rt):
    second = FakePlayback()
    release = Event()
    accepted = Event()
    def speak_done():
        event(manager, rt, port)
        accepted.set()
        assert release.wait(2)
    port.on_speak = speak_done
    request = manager.new_request()
    first = manager.append_speech(request, port, "Fake:a", ("one",))
    manager.append_speech(request, second, "Fake:b", ("two",))
    try:
        assert manager.submit_request(request)
        assert accepted.wait(1)
        assert not first.done()
        assert not second.entered.is_set()
    finally:
        release.set()
    assert second.entered.wait(1)
    assert output.done_count == 0
    event(manager, rt, second)
    event(manager, rt, second)
    assert output.wait_done() == 1


def test_wrong_source_event_cannot_release_current_segment(manager, port, output, rt):
    request, future = speech(manager, port)
    wrong = FakePlayback()
    event(manager, rt, wrong)
    event(manager, rt, wrong, "INDEX", 7)
    assert not future.done()
    assert output.indexes == []
    event(manager, rt, port)
    assert output.wait_done() == 1


def test_valid_index_is_forwarded_once(manager, port, output, rt):
    speech(manager, port)
    event(manager, rt, port, "INDEX", 7)
    event(manager, rt, port, "INDEX", 7)
    assert output.indexes == [7]
    assert output.done_count == 0


def test_index_after_done_is_not_forwarded(manager, port, output, rt):
    port.on_speak = lambda: (event(manager, rt, port), event(manager, rt, port, "INDEX", 11))
    speech(manager, port)
    assert output.wait_done() == 1
    assert output.indexes == []


def test_trailing_break_delays_completion(manager, port, output, rt):
    entered, release = Event(), Event()
    port.on_speak = lambda: event(manager, rt, port)
    request = manager.new_request()
    manager.append_speech(request, port, "Fake:a", ("hello",))
    future = manager.append_break(request, 60)
    def wait(seconds):
        assert seconds == 60
        entered.set()
        assert release.wait(2)
        return False
    request.token.wait = wait
    try:
        assert manager.submit_request(request)
        assert entered.wait(1)
        assert output.done_count == 0
    finally:
        release.set()
    assert future.result(1) is None
    assert output.wait_done() == 1


@pytest.mark.parametrize("kind", ["empty", "break"])
def test_non_speech_request_completes_without_output(manager, output, scheduler, kind):
    request = manager.new_request()
    if kind == "break":
        manager.append_break(request, 0)
    assert manager.submit_request(request)
    manager._q.join()
    assert request.state is scheduler.RequestState.COMPLETED
    assert request.request_id not in manager._requests
    assert output.done_count == 0


@pytest.mark.parametrize("failure_at", ["activate", "speak"])
def test_failure_stops_playback_and_completes_once(manager, port, output, scheduler, failure_at):
    other = FakePlayback()
    def fail():
        raise ValueError(failure_at)
    setattr(port, "on_" + failure_at, fail)
    request = manager.new_request()
    first = manager.append_speech(request, port, "Fake:a", ("one",))
    second = manager.append_speech(request, other, "Fake:b", ("two",))
    assert manager.submit_request(request)
    with pytest.raises(ValueError, match=failure_at):
        first.result(1)
    assert output.wait_done() == 1
    with pytest.raises(CancelledError):
        second.result(1)
    manager._q.join()
    assert request.state is scheduler.RequestState.FAILED
    assert request.token.is_cancelled()
    assert request.remaining == 0
    assert port.cancel_count == 1
    assert not other.entered.is_set()


def test_cancelled_request_built_before_submit_is_not_enqueued(manager, port, scheduler, output):
    request = manager.new_request()
    future = manager.append_speech(request, port, "Fake:a", ("old",))
    manager.cancel([port])
    assert request.state is scheduler.RequestState.CANCELLED
    assert future.cancelled()
    assert manager.submit_request(request) is False
    assert port.spoken == []
    assert output.done_count == 0


def test_append_after_submit_is_rejected(manager, port, scheduler):
    request, _ = speech(manager, port)
    with pytest.raises(scheduler.InvalidRequestState):
        manager.append_speech(request, port, "Fake:a", ())
    with pytest.raises(scheduler.InvalidRequestState):
        manager.append_break(request, 0)
    assert manager.submit_request(request) is False
    with pytest.raises(scheduler.InvalidRequestState):
        manager.abort_request(request, ValueError())


def test_abort_building_releases_tracking_and_futures(manager, port, scheduler, output):
    request = manager.new_request()
    futures = [manager.append_speech(request, port, "Fake:a", ()), manager.append_break(request, 0)]
    error = ValueError("build failed")
    manager.abort_request(request, error)
    assert request.state is scheduler.RequestState.FAILED
    assert request.request_id not in manager._requests
    assert request.token.is_cancelled()
    assert all(future.exception(1) is error for future in futures)
    manager.abort_request(request, RuntimeError())
    manager.cancel()
    assert request.state is scheduler.RequestState.FAILED
    assert output.done_count == 0


@pytest.mark.parametrize("kind", ["INDEX", "DONE"])
def test_cancel_between_acceptance_and_output_suppresses_index_and_done(manager, port, output, rt, kind):
    request, _ = speech(manager, port)
    accepted, release = Event(), Event()
    original = manager._deliver_index if kind == "INDEX" else manager._deliver_done
    def blocked(*args):
        accepted.set()
        assert release.wait(2)
        original(*args)
    setattr(manager, "_deliver_index" if kind == "INDEX" else "_deliver_done", blocked)
    thread = Thread(target=event, args=(manager, rt, port, kind, 23))
    try:
        thread.start()
        assert accepted.wait(1)
        manager.cancel([port])
    finally:
        release.set()
        thread.join(1)
    manager._q.join()
    assert not thread.is_alive()
    assert output.indexes == []
    assert output.done_count == 0


def test_future_callback_can_cancel_and_submit(manager, port, rt, output):
    callback_done = Event()
    other = FakePlayback()
    other.on_speak = lambda: event(manager, rt, other)
    request = manager.new_request()
    future = manager.append_speech(request, port, "Fake:a", ())
    def callback(_):
        # A second thread must acquire state: an RLock alone cannot hide violations.
        thread = Thread(target=manager.cancel)
        thread.start()
        thread.join(1)
        assert not thread.is_alive()
        new = manager.new_request()
        manager.append_speech(new, other, "Fake:b", ("new",))
        assert manager.submit_request(new)
        callback_done.set()
    chained = future.then(callback)
    assert manager.submit_request(request)
    assert port.entered.wait(1)
    event(manager, rt, port)
    assert callback_done.wait(1)
    assert chained.result(1) is None
    assert output.wait_done() == 1


def test_shutdown_rejects_new_request(manager, scheduler, port):
    request = manager.new_request()
    future = manager.append_speech(request, port, "Fake:a", ())
    manager.shutdown()
    assert future.cancelled()
    with pytest.raises(scheduler.InvalidRequestState):
        manager.new_request()
    assert manager.submit_request(request) is False


def test_old_epoch_events_are_discarded(manager, port, output, rt):
    old, old_future = speech(manager, port)
    manager.cancel([port])
    other = FakePlayback()
    new, new_future = speech(manager, other)
    event(manager, rt, port)
    event(manager, rt, port, "INDEX", 9)
    assert not new_future.done()
    assert output.indexes == []
    assert output.done_count == 0
    event(manager, rt, other)
    assert output.wait_done() == 1
    assert old_future.cancelled()


@pytest.mark.parametrize("stop_count", [1, 2])
def test_all_concurrent_stops_finish_before_new_speech(manager, port, rt, output, stop_count):
    speech(manager, port)
    entered = [Event() for _ in range(stop_count)]
    release = [Event() for _ in range(stop_count)]
    exited = [Event() for _ in range(stop_count)]
    counter, lock = [], Lock()
    def stop():
        with lock:
            index = len(counter)
            counter.append(index)
        entered[index].set()
        assert release[index].wait(2)
        exited[index].set()
    port.on_cancel = stop
    threads = [Thread(target=manager.cancel, args=([port],)) for _ in entered]
    other = FakePlayback()
    try:
        for thread in threads:
            thread.start()
        assert all(e.wait(1) for e in entered)
        new = manager.new_request()
        manager.append_speech(new, other, "Fake:b", ())
        assert manager.submit_request(new)
        for index in range(stop_count):
            assert not other.entered.wait(0.03)
            release[index].set()
            assert exited[index].wait(1)
        assert other.entered.wait(1)
        event(manager, rt, other)
        assert output.wait_done() == 1
    finally:
        for e in release:
            e.set()
        for thread in threads:
            thread.join(1)
        port.on_cancel = None


def test_cancel_wakes_break_token_and_allows_new_request(manager, port):
    request = manager.new_request()
    entered = Event()
    original = request.token.wait
    def wait(seconds):
        entered.set()
        return original(seconds)
    request.token.wait = wait
    future = manager.append_break(request, 60)
    assert manager.submit_request(request)
    assert entered.wait(1)
    manager.pause_current(True)
    manager.cancel()
    speech(manager, port)
    assert future.cancelled()
    assert port.paused == []


def test_cancel_stops_shared_source_once_and_current_first(manager, port):
    speech(manager, port)
    alias, other = FakePlayback(), FakePlayback()
    alias.source_id = port.source_id
    stopped = []
    port.on_cancel = lambda: stopped.append("current")
    other.on_cancel = lambda: stopped.append("other")
    alias.on_cancel = lambda: stopped.append("alias")
    manager.cancel([other, alias, port])
    assert stopped == ["current", "other"]


def test_cancel_during_activate_skips_speak_and_stale_events(manager, port, rt, output):
    entered, release = Event(), Event()
    def activate():
        entered.set()
        assert release.wait(2)
    port.on_activate = activate
    request = manager.new_request()
    future = manager.append_speech(request, port, "Fake:a", ("old",))
    try:
        assert manager.submit_request(request)
        assert entered.wait(1)
        manager.cancel([port])
    finally:
        release.set()
    with pytest.raises(CancelledError):
        future.result(1)
    assert port.spoken == []
    first, second = FakePlayback(), FakePlayback()
    new = manager.new_request()
    manager.append_speech(new, first, "Fake:b", ())
    manager.append_speech(new, second, "Fake:c", ())
    assert manager.submit_request(new)
    assert first.entered.wait(1)
    event(manager, rt, port)
    event(manager, rt, port, "INDEX", 9)
    assert not second.entered.is_set()
    assert not new.tasks[0].future.done()
    event(manager, rt, first, "INDEX", 12)
    event(manager, rt, first)
    assert second.entered.wait(1)
    event(manager, rt, second, "INDEX", 13)
    event(manager, rt, second)
    assert output.wait_done() == 1
    assert output.indexes == [12, 13]


def test_cancel_during_speak_stops_again_and_discards_synchronous_done(manager, port, rt, output):
    entered, release = Event(), Event()
    def speak_done():
        entered.set()
        assert release.wait(2)
        event(manager, rt, port)
    port.on_speak = speak_done
    try:
        request, future = speech(manager, port)
        assert entered.wait(1)
        manager.cancel([port])
    finally:
        release.set()
    with pytest.raises(CancelledError):
        future.result(1)
    manager._q.join()
    assert port.cancel_count == 2
    assert output.done_count == 0


def test_pending_speech_is_cancelled_but_new_request_runs(manager, port, rt):
    speech(manager, port)
    queued = FakePlayback()
    old = manager.new_request()
    old_future = manager.append_speech(old, queued, "Fake:b", ())
    assert manager.submit_request(old)
    manager.cancel([port])
    new_port = FakePlayback()
    _, new_future = speech(manager, new_port)
    assert old_future.cancelled()
    assert not queued.entered.is_set()
    event(manager, rt, new_port)
    assert new_future.result(1) is True


def test_cancel_current_preserves_queued_request_and_gates_stop(manager, port, rt, output):
    request, future = speech(manager, port)
    entered, release = Event(), Event()
    other = FakePlayback()
    new = manager.new_request()
    manager.append_speech(new, other, "Fake:b", ())
    assert manager.submit_request(new)
    def stop():
        entered.set()
        assert release.wait(2)
    port.on_cancel = stop
    thread = Thread(target=manager.cancel_current)
    try:
        thread.start()
        assert entered.wait(1)
        assert not other.entered.wait(0.03)
    finally:
        release.set()
        thread.join(1)
        port.on_cancel = None
    assert other.entered.wait(1)
    assert future.cancelled()
    event(manager, rt, other)
    assert output.wait_done() == 1


def test_pause_current_uses_valid_playback(manager, port):
    manager.pause_current(True)
    speech(manager, port)
    manager.pause_current(True)
    manager.pause_current(False)
    manager.cancel([port])
    manager.pause_current(True)
    assert port.paused == [True, False]


def test_direct_playback_stop_does_not_cancel_request(manager, port, rt, output):
    def speak_done():
        port.cancel()
        event(manager, rt, port)
    port.on_speak = speak_done
    request = manager.new_request()
    futures = [manager.append_speech(request, port, "Fake:a", (text,)) for text in ("first", "second")]
    assert manager.submit_request(request)
    assert output.wait_done() == 1
    assert [commands for commands, _ in port.spoken] == [("first",), ("second",)]
    assert all(future.result(1) is True for future in futures)
    assert not request.token.is_cancelled()


def test_then_flattens_results_errors_and_cancellation(scheduler):
    future = scheduler.SpeechFuture()
    chained = future.then(lambda f: f.result() + 1)
    future.set_result(3)
    assert chained.result(1) == 4
    cancelled = scheduler.SpeechFuture()
    next_future = cancelled.then(lambda _: 1)
    cancelled.cancel()
    assert next_future.cancelled()
    inner = scheduler.SpeechFuture()
    flattened = future.then(lambda _: inner)
    inner.set_result(8)
    assert flattened.result(1) == 8
    failed = scheduler.SpeechFuture()
    propagated = failed.then(lambda f: f.result())
    failed.set_exception(ValueError("failed"))
    with pytest.raises(ValueError, match="failed"):
        propagated.result(1)


def test_token_cancellation_inside_speak_suppresses_done(manager, port, output, scheduler):
    request = manager.new_request()
    future = manager.append_speech(request, port, "Fake:a", ())
    port.on_speak = request.token.cancel
    assert manager.submit_request(request)
    with pytest.raises(CancelledError):
        future.result(1)
    manager._q.join()
    assert request.state is scheduler.RequestState.CANCELLED
    assert output.done_count == 0


def test_engine_calls_and_output_run_outside_state_lock(manager, port, rt, output):
    acquired = []
    def probe():
        done = Event()
        def enter():
            with manager._state_cond:
                done.set()
        thread = Thread(target=enter)
        thread.start()
        try:
            assert done.wait(1)
            acquired.append(True)
        finally:
            thread.join(1)
    port.on_activate = probe
    port.on_speak = lambda: (probe(), event(manager, rt, port, "INDEX", 3), event(manager, rt, port))
    original_index, original_done = output.index_reached, output.done_speaking
    output.index_reached = lambda index: (probe(), original_index(index))
    output.done_speaking = lambda: (probe(), original_done())
    speech(manager, port)
    assert output.wait_done() == 1
    assert acquired == [True, True, True, True]


def test_abort_and_cancel_building_callbacks_run_outside_state_lock(manager, port):
    for operation in (lambda r: manager.abort_request(r, ValueError()), lambda r: manager.cancel()):
        request = manager.new_request()
        future = manager.append_speech(request, port, "Fake:a", ())
        completed = Event()
        def callback(_):
            thread = Thread(target=lambda: (manager.new_request(), completed.set()))
            thread.start()
            thread.join(1)
        future.add_done_callback(callback)
        operation(request)
        assert completed.is_set()


def test_stop_failure_does_not_block_other_ports_or_new_request(manager, port, rt, output):
    speech(manager, port)
    other = FakePlayback()
    def fail_stop():
        raise ValueError("stop failed")
    port.on_cancel = fail_stop
    manager.cancel([port, other])
    assert other.cancel_count == 1
    other.on_speak = lambda: event(manager, rt, other)
    speech(manager, other)
    assert output.wait_done() == 1


@pytest.mark.parametrize("with_tasks", [False, True])
def test_submit_token_cancelled_building_request_releases_tracking_and_futures(
        manager, port, scheduler, output, with_tasks):
    request = manager.new_request()
    futures = []
    callback_completed = Event()
    callback_unlocked = []
    if with_tasks:
        futures = [manager.append_speech(request, port, "Fake:a", ("old",)),
                   manager.append_break(request, 0)]
        def callback(_):
            def acquire_state():
                with manager._state_cond:
                    callback_completed.set()
            thread = Thread(target=acquire_state)
            thread.start()
            callback_unlocked.append(callback_completed.wait(1))
            thread.join(1)
        futures[0].add_done_callback(callback)
    request.token.cancel()
    assert manager.submit_request(request) is False
    assert request.state is scheduler.RequestState.CANCELLED
    assert request.request_id not in manager._requests
    assert request.remaining == 0
    assert all(future.cancelled() for future in futures)
    if with_tasks:
        assert callback_unlocked == [True]
    assert not port.entered.is_set()
    assert output.done_count == 0
    assert manager.submit_request(request) is False


@pytest.mark.parametrize("cancel_at", ["speak", "awaiting_done"])
def test_cancelled_speech_future_does_not_stall_following_tasks(manager, port, rt, output, cancel_at):
    request = manager.new_request()
    first = manager.append_speech(request, port, "Fake:a", ("first",))
    next_port = FakePlayback()
    second = manager.append_speech(request, next_port, "Fake:b", ("second",))
    next_port.on_speak = lambda: event(manager, rt, next_port)
    waiting = Event()
    def speak_hook():
        if cancel_at == "speak":
            assert first.cancel()
            event(manager, rt, port)
        else:
            done = manager._current_done_event
            original_wait = done.wait
            def observed_wait():
                waiting.set()
                return original_wait()
            done.wait = observed_wait
    port.on_speak = speak_hook
    try:
        assert manager.submit_request(request)
        if cancel_at == "awaiting_done":
            assert waiting.wait(1)
            assert first.cancel()
            event(manager, rt, port)
        assert next_port.entered.wait(1)
        assert second.result(1) is True
        assert output.wait_done() == 1
        assert first.cancelled()
        assert request.remaining == 0
    finally:
        # A regression must fail promptly instead of hanging fixture shutdown.
        manager.cancel()
