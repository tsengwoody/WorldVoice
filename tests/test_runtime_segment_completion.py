"""Correlated completion, delivery ordering and segment lifetime contracts."""
from concurrent.futures import CancelledError
from threading import Event, Thread

import pytest

from runtime_harness import FakePlayback, RecordingOutput, load_scheduler, rt


@pytest.fixture
def scheduler(monkeypatch, rt):
    return load_scheduler(monkeypatch, rt)


@pytest.fixture
def output():
    return RecordingOutput()


@pytest.fixture
def manager(scheduler, output):
    manager = scheduler.TaskManager(output)
    yield manager
    manager.shutdown()


def marker(rt, mode="END_INDEX"):
    return FakePlayback(rt.models.CompletionContract(
        getattr(rt.models.CompletionMode, mode), rt.models.IndexRange(1, 1000)))


def start(manager, port, next_port=None):
    request = manager.new_request()
    future = manager.append_speech(request, port, "Fake:a", ("hello",))
    if next_port is not None:
        manager.append_speech(request, next_port, "Fake:b", ("next",))
    assert manager.submit_request(request)
    assert port.entered.wait(1)
    assert port.contexts[-1] is not None
    return request, future


def make_event(rt, port, kind="SEGMENT_END", *, context=None, index=None, error=None):
    context = context or port.contexts[-1]
    return rt.models.PlaybackEvent(getattr(rt.models.EventKind, kind), port.source_id,
                                   index, context.segment_id, error)


def emit(manager, rt, port, kind="SEGMENT_END", **kwargs):
    manager.on_event(make_event(rt, port, kind, **kwargs))


def test_same_source_late_events_do_not_finish_next_segment(manager, rt, output):
    port = marker(rt)
    _, old = start(manager, port)
    context = port.contexts[-1]
    manager.cancel()
    port.entered.clear()
    _, future_b = start(manager, port)
    assert old.cancelled()
    assert port.contexts[-1].segment_id != context.segment_id
    for kind in ("INDEX", "SEGMENT_END", "SEGMENT_DRAINED", "SEGMENT_FAILED"):
        emit(manager, rt, port, kind, context=context, index=123, error=ValueError("old"))
    manager.on_event(rt.models.PlaybackEvent(rt.models.EventKind.DONE, port.source_id))
    assert not future_b.done()
    assert output.indexes == []
    emit(manager, rt, port)
    assert future_b.result(1) is True


def test_duplicate_end_cannot_advance_next_task(manager, rt):
    port, second = marker(rt), marker(rt)
    second.source_id = port.source_id
    request, _ = start(manager, port, second)
    old = make_event(rt, port)
    manager.on_event(old)
    assert second.entered.wait(1)
    manager.on_event(old)
    assert not request.tasks[1].future.done()
    emit(manager, rt, second)
    assert request.tasks[1].future.result(1) is True


def test_end_then_speak_error_is_failure(manager, rt, scheduler, output):
    port, second = marker(rt), marker(rt)
    error = ValueError("after END")
    def speak():
        emit(manager, rt, port)
        raise error
    port.on_speak = speak
    request, first = start(manager, port, second)
    assert first.exception(1) is error
    with pytest.raises(CancelledError):
        request.tasks[1].future.result(1)
    assert request.state is scheduler.RequestState.FAILED
    assert not second.entered.is_set()
    assert output.wait_done() == 1


def test_end_waits_for_speak_return(manager, rt):
    port, next_port = marker(rt), marker(rt)
    ended, release = Event(), Event()
    def speak():
        emit(manager, rt, port)
        ended.set()
        assert release.wait(2)
    port.on_speak = speak
    try:
        _, first = start(manager, port, next_port)
        assert ended.wait(1)
        assert not first.done()
        assert not next_port.entered.is_set()
    finally:
        release.set()
    assert next_port.entered.wait(1)
    emit(manager, rt, next_port)


def test_done_without_end_is_not_success(manager, rt):
    port = marker(rt)
    _, future = start(manager, port)
    manager.on_event(rt.models.PlaybackEvent(rt.models.EventKind.DONE, port.source_id))
    assert not future.done()
    manager.cancel()
    with pytest.raises(CancelledError):
        future.result(1)


def test_drain_needs_matching_drain_not_end_or_done(manager, rt, output):
    port = marker(rt, "DRAIN")
    _, future = start(manager, port)
    emit(manager, rt, port, "SEGMENT_END")
    manager.on_event(rt.models.PlaybackEvent(rt.models.EventKind.DONE, port.source_id))
    assert not future.done()
    emit(manager, rt, port, "INDEX", index=123)
    assert output.indexes == [123]
    emit(manager, rt, port, "SEGMENT_DRAINED")
    assert future.result(1) is True


def test_drain_rejects_wrong_source_and_segment(manager, rt):
    class EqualSource:
        def __eq__(self, other):
            return True

    port = marker(rt, "DRAIN")
    port.source_id = EqualSource()
    _, future = start(manager, port)
    context = port.contexts[-1]
    manager.on_event(rt.models.PlaybackEvent(
        rt.models.EventKind.SEGMENT_DRAINED, EqualSource(), segment_id=context.segment_id))
    wrong = rt.models.PlaybackContext(port.source_id, context.segment_id + 100)
    emit(manager, rt, port, "SEGMENT_DRAINED", context=wrong)
    manager.on_event(rt.models.PlaybackEvent(rt.models.EventKind.SEGMENT_DRAINED, port.source_id))
    assert not future.done()
    emit(manager, rt, port, "SEGMENT_DRAINED")
    assert future.result(1) is True


def test_duplicate_drain_cannot_advance_next_segment(manager, rt, output):
    port, second = marker(rt, "DRAIN"), marker(rt, "DRAIN")
    second.source_id = port.source_id
    request, first = start(manager, port, second)
    old = make_event(rt, port, "SEGMENT_DRAINED")
    manager.on_events(lambda: (make_event(rt, port, "INDEX", index=123), old, old,
                              make_event(rt, port, "INDEX", index=456)))
    assert first.result(1) is True
    assert second.entered.wait(1)
    manager.on_events(lambda: (old, make_event(rt, port, "INDEX", index=789)))
    assert not request.tasks[1].future.done()
    assert output.indexes == [123]
    emit(manager, rt, second, "SEGMENT_DRAINED")
    assert request.tasks[1].future.result(1) is True


def test_drain_waits_for_speak_return_and_rejects_late_index(manager, rt, output):
    port, second = marker(rt, "DRAIN"), marker(rt, "DRAIN")
    drained, release = Event(), Event()

    def speak():
        emit(manager, rt, port, "SEGMENT_DRAINED")
        drained.set()
        assert release.wait(2)

    port.on_speak = speak
    try:
        _, future = start(manager, port, second)
        assert drained.wait(1)
        emit(manager, rt, port, "INDEX", index=123)
        assert output.indexes == []
        assert not future.done()
        assert not second.entered.is_set()
    finally:
        release.set()
    assert future.result(1) is True
    assert second.entered.wait(1)
    emit(manager, rt, second, "SEGMENT_DRAINED")


@pytest.mark.parametrize("outcome", ["speak_error", "segment_failure", "cancel"])
def test_drain_does_not_override_failure_or_cancellation(manager, rt, scheduler, output, outcome):
    port, second = marker(rt, "DRAIN"), marker(rt, "DRAIN")
    error = ValueError("after drain")

    def speak():
        emit(manager, rt, port, "SEGMENT_DRAINED")
        if outcome == "speak_error":
            raise error
        if outcome == "segment_failure":
            emit(manager, rt, port, "SEGMENT_FAILED", error=error)
        else:
            manager.cancel()

    port.on_speak = speak
    request, future = start(manager, port, second)
    if outcome == "cancel":
        with pytest.raises(CancelledError):
            future.result(1)
        assert request.state is scheduler.RequestState.CANCELLED
        assert output.done_count == 0
    else:
        assert future.exception(1) is error
        assert request.state is scheduler.RequestState.FAILED
        assert output.wait_done() == 1
    with pytest.raises(CancelledError):
        request.tasks[1].future.result(1)
    assert not second.entered.is_set()


@pytest.mark.parametrize("first,second", [("SEGMENT_END", "SEGMENT_DRAINED"),
                                           ("SEGMENT_DRAINED", "SEGMENT_END")])
def test_end_and_drain_require_same_segment(manager, rt, first, second):
    port = marker(rt, "END_INDEX_AND_DRAIN")
    _, future = start(manager, port)
    context = port.contexts[-1]
    emit(manager, rt, port, first)
    assert not future.done()
    wrong = rt.models.PlaybackContext(port.source_id, context.segment_id + 100)
    emit(manager, rt, port, second, context=wrong)
    assert not future.done()
    emit(manager, rt, port, second)
    assert future.result(1) is True


def test_end_and_drain_rejects_index_after_end_while_waiting_for_drain(manager, rt, output):
    port = marker(rt, "END_INDEX_AND_DRAIN")
    _, future = start(manager, port)
    emit(manager, rt, port, "INDEX", index=123)
    emit(manager, rt, port, "SEGMENT_END")
    emit(manager, rt, port, "INDEX", index=456)
    assert output.indexes == [123]
    assert not future.done()
    emit(manager, rt, port, "SEGMENT_DRAINED")
    assert future.result(1) is True
    assert output.indexes == [123]


def test_index_delivery_precedes_terminal_batch(manager, rt, output):
    port, next_port = marker(rt), marker(rt)
    start(manager, port, next_port)
    entered, release, attempted, loaded = Event(), Event(), Event(), Event()
    original = output.index_reached
    def output_index(index):
        entered.set()
        assert release.wait(2)
        original(index)
    output.index_reached = output_index
    def terminal():
        attempted.set()
        manager.on_events(lambda: (loaded.set(), (make_event(rt, port),))[1])
    index_thread = Thread(target=emit, args=(manager, rt, port, "INDEX"), kwargs={"index": 123})
    end_thread = Thread(target=terminal)
    try:
        index_thread.start()
        assert entered.wait(1)
        end_thread.start()
        assert attempted.wait(1)
        assert not loaded.is_set()
        assert not next_port.entered.is_set()
    finally:
        release.set()
        index_thread.join(1)
        end_thread.join(1)
    assert next_port.entered.wait(1)
    assert loaded.is_set()
    assert output.indexes == [123]
    emit(manager, rt, next_port)


def test_index_callback_cancels_remaining_batch(manager, rt, output):
    port = marker(rt)
    _, future = start(manager, port)
    original = output.index_reached
    output.index_reached = lambda index: (original(index), manager.cancel())
    manager.on_events(lambda: (make_event(rt, port, "INDEX", index=123),
                              make_event(rt, port, "INDEX", index=456), make_event(rt, port)))
    with pytest.raises(CancelledError):
        future.result(1)
    assert output.indexes == [123]
    assert output.done_count == 0


def test_missing_marker_failure_releases_request_once(manager, rt, scheduler, output):
    port, second = marker(rt), marker(rt)
    request, future = start(manager, port, second)
    error = ValueError("missing marker")
    failure = make_event(rt, port, "SEGMENT_FAILED", error=error)
    manager.on_events(lambda: (failure, failure))
    assert future.exception(1) is error
    with pytest.raises(CancelledError):
        request.tasks[1].future.result(1)
    assert request.state is scheduler.RequestState.FAILED
    assert request.remaining == 0
    assert not second.entered.is_set()
    assert output.wait_done() == 1


def test_trailing_pause_and_non_speech_done_policy(manager, rt, output):
    port = marker(rt)
    entered, release = Event(), Event()
    request = manager.new_request()
    manager.append_speech(request, port, "Fake:a", ())
    tail = manager.append_break(request, 60)
    request.token.wait = lambda seconds: (entered.set(), release.wait(2))[1]
    port.on_speak = lambda: emit(manager, rt, port)
    try:
        manager.submit_request(request)
        assert entered.wait(1)
        assert output.done_count == 0
    finally:
        release.set()
    assert tail.result(1) is None
    assert output.wait_done() == 1
    for pause in (False, True):
        request = manager.new_request()
        if pause:
            manager.append_break(request, 0)
        manager.submit_request(request)
    manager._q.join()
    assert output.done_count == 1


@pytest.mark.parametrize("outcome", ["success", "cancel", "error", "future_cancel", "activate_error"])
def test_finish_segment_runs_on_all_terminal_paths(manager, rt, outcome):
    port = marker(rt)
    error = ValueError("activate")
    if outcome == "activate_error":
        def fail():
            raise error
        port.on_activate = fail
        request = manager.new_request()
        future = manager.append_speech(request, port, "Fake:a", ())
        manager.submit_request(request)
        assert future.exception(1) is error
    else:
        _, future = start(manager, port)
        if outcome == "success":
            emit(manager, rt, port)
            assert future.result(1) is True
        elif outcome == "cancel":
            manager.cancel()
        elif outcome == "future_cancel":
            assert future.cancel()
        else:
            emit(manager, rt, port, "SEGMENT_FAILED", error=error)
            assert future.exception(1) is error
    manager._q.join()
    assert len(port.finished) == 1
    assert port.finished[0].source_id is port.source_id
    if port.contexts:
        assert port.finished == port.contexts


def test_supplier_output_and_cleanup_are_outside_state_lock(manager, rt, output):
    port = marker(rt)
    _, future = start(manager, port)
    def probe():
        acquired = Event()
        def enter():
            with manager._state_cond:
                acquired.set()
        thread = Thread(target=enter)
        thread.start()
        assert acquired.wait(1)
        thread.join(1)
    original_finish = port.finish_segment
    port.finish_segment = lambda context: (probe(), original_finish(context))
    original_output = output.index_reached
    output.index_reached = lambda index: (probe(), original_output(index))
    def supplier():
        probe()
        return (make_event(rt, port, "INDEX", index=123), make_event(rt, port))
    manager.on_events(supplier)
    assert future.result(1) is True
    assert output.indexes == [123]


@pytest.mark.parametrize("failure_at", ["output", "supplier", "cleanup"])
def test_boundary_errors_do_not_leave_waits_or_kill_worker(manager, rt, output, failure_at):
    port = marker(rt)
    _, future = start(manager, port)
    error = ValueError(failure_at)
    def fail(*args):
        raise error
    if failure_at == "output":
        output.index_reached = fail
        emit(manager, rt, port, "INDEX", index=123)
    elif failure_at == "supplier":
        manager.on_events(fail)
    else:
        port.finish_segment = fail
        emit(manager, rt, port)
    if failure_at == "cleanup":
        assert future.result(1) is True
    else:
        assert future.exception(1) is error
    other = marker(rt)
    _, following = start(manager, other)
    emit(manager, rt, other)
    assert following.result(1) is True
    assert manager._thread.is_alive()


def test_marker_pause_cancel_current_and_future_callback(manager, rt, output):
    port, other = marker(rt), marker(rt)
    request, first = start(manager, port)
    next_request = manager.new_request()
    next_future = manager.append_speech(next_request, other, "Fake:b", ())
    manager.submit_request(next_request)
    manager.pause_current(True)
    manager.pause_current(False)
    callback = Event()
    def completed(_):
        thread = Thread(target=lambda: (manager.new_request(), callback.set()))
        thread.start()
        thread.join(1)
    first.add_done_callback(completed)
    manager.cancel_current()
    assert other.entered.wait(1)
    assert first.cancelled()
    assert callback.wait(1)
    assert port.paused == [True, False]
    emit(manager, rt, other)
    assert next_future.result(1) is True
    assert output.wait_done() == 1


def test_done_output_error_does_not_kill_worker(manager, rt, output):
    port = marker(rt)
    _, first = start(manager, port)
    called = Event()
    def fail():
        called.set()
        raise ValueError("done output")
    output.done_speaking = fail
    emit(manager, rt, port)
    assert first.result(1) is True
    assert called.wait(1)
    other = marker(rt)
    request = manager.new_request()
    future = manager.append_speech(request, other, "Fake:b", ())
    manager.submit_request(request)
    assert other.entered.wait(1)
    emit(manager, rt, other)
    assert future.result(1) is True


def test_completion_contract_is_read_once_per_segment(manager, rt):
    port = marker(rt, "END_INDEX_AND_DRAIN")
    _, future = start(manager, port)
    port.completion = rt.models.CompletionContract()
    emit(manager, rt, port)
    assert not future.done()
    emit(manager, rt, port, "SEGMENT_DRAINED")
    assert future.result(1) is True


def test_wrong_source_and_starting_phase_reject_segment_events(manager, rt, output):
    port = marker(rt)
    active, release = Event(), Event()
    port.on_activate = lambda: (active.set(), release.wait(2))
    request = manager.new_request()
    future = manager.append_speech(request, port, "Fake:a", ())
    try:
        manager.submit_request(request)
        assert active.wait(1)
        context = request.tasks[0].context
        emit(manager, rt, port, context=context)
        emit(manager, rt, port, "INDEX", context=context, index=1)
        assert not future.done()
    finally:
        release.set()
    assert port.entered.wait(1)
    wrong_source = rt.models.PlaybackEvent(rt.models.EventKind.SEGMENT_END, object(),
                                          segment_id=context.segment_id)
    manager.on_event(wrong_source)
    assert not future.done()
    assert output.indexes == []
    emit(manager, rt, port)
    assert future.result(1) is True


def test_reentrant_supplier_is_deferred_until_current_batch_finishes(manager, rt, output):
    port = marker(rt)
    _, future = start(manager, port)
    sequence = []
    original = output.index_reached
    def supplier():
        sequence.append("decode END")
        return (make_event(rt, port),)
    def on_index(index):
        original(index)
        sequence.append(index)
        if index == 123:
            manager.on_events(supplier)
            sequence.append("nested call returned")
        assert not future.done()
        assert output.done_count == 0
    output.index_reached = on_index
    manager.on_events(lambda: (make_event(rt, port, "INDEX", index=123),
                              make_event(rt, port, "INDEX", index=124)))
    assert future.result(1) is True
    assert output.indexes == [123, 124]
    assert sequence == [123, "nested call returned", 124, "decode END"]


@pytest.mark.parametrize("outcome", ["cancel", "failure"])
def test_reentrant_terminal_supplier_preserves_cancel_and_failure(manager, rt, output, outcome):
    port = marker(rt)
    request, future = start(manager, port)
    error = ValueError("queued failure")
    original = output.index_reached
    def on_index(index):
        original(index)
        if index == 123:
            if outcome == "cancel":
                manager.on_events(lambda: (make_event(rt, port),))
                manager.cancel()
            else:
                manager.on_events(lambda: (make_event(rt, port, "SEGMENT_FAILED", error=error),))
    output.index_reached = on_index
    manager.on_events(lambda: (make_event(rt, port, "INDEX", index=123),
                              make_event(rt, port, "INDEX", index=124)))
    if outcome == "cancel":
        with pytest.raises(CancelledError):
            future.result(1)
        assert output.indexes == [123]
        assert output.done_count == 0
    else:
        assert future.exception(1) is error
        assert output.indexes == [123, 124]
        assert output.wait_done() == 1
    manager._q.join()
    assert request.remaining == 0
    assert port.finished == port.contexts
