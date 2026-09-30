"""Correlated RHVoice completion at the real installed outer wrapper."""

import gc
import ctypes
import sys
from threading import Event, Thread, current_thread
import time
import weakref

import pytest

from rhvoice_drain_harness import finish, load_rhvoice, speak


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentLifecycle", raising=False)
    result = load_rhvoice(monkeypatch, tmp_path)
    yield result
    finish(result)


def assert_no_successor_native_call(env, timeout=0.1):
    with env.native.condition:
        assert not env.native.condition.wait_for(lambda: len(env.native.calls) > 1, timeout)


def test_done_before_native_return_waits_for_final_idle_and_retirement(env):
    env.native.scripts.append({})
    token, context, events = speak(env)
    call = env.native.wait_call()
    assert call.done.wait(3)
    assert events == []
    player = env.players[0]
    player.block_idle_number = 2
    player.idle_release.clear()
    call.return_release.set()
    assert call.returned.wait(3)
    assert player.second_idle_entered.wait(3)
    assert player.idle_count == 2
    assert events == []
    player.idle_release.set()
    event = events.wait_one()
    assert event.kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert (event.source_id, event.segment_id) == (context.source_id, context.segment_id)
    assert env.native.deleted == [1]
    assert env.indexes == [7]
    assert env.driver.lastIndex is None  # The inner callback's existing state.
    assert len(events) == 1


def test_missing_done_does_not_drain_after_native_return(env):
    env.native.scripts.append({"missing_done": True, "auto_return": True})
    _, _, events = speak(env)
    call = env.native.wait_call()
    assert call.returned.wait(3)
    assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_FAILED


def test_message_delete_failure_fails_closed_for_contextual_and_legacy_successors(env):
    def fail_delete(message):
        raise OSError("delete failed")
    env.native.RHVoice_delete_message.function = fail_delete
    env.native.scripts.append({"auto_return": True})
    _, _, old_events = speak(env, text="old")
    old_call = env.native.wait_call()
    assert old_call.returned.wait(3)
    event = old_events.wait_one()
    assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert isinstance(event.error, OSError)
    assert str(event.error) == "delete failed"
    assert len(old_events) == 1
    env.native.scripts.append({"auto_return": True})
    _, _, next_events = speak(env, segment=2, text="next")
    assert next_events.wait_one().kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert_no_successor_native_call(env)
    with pytest.raises(OSError, match="delete failed"):
        env.driver.speak(("legacy", env.commands.IndexCommand(7)))
    assert_no_successor_native_call(env)
    assert len(env.native.calls) == 1


def test_terminal_sink_can_terminate_outside_native_and_worker_stacks(env):
    delivered = Event()
    threads = []
    def sink(event):
        threads.append(current_thread())
        env.driver.terminate()
        delivered.set()
    env.native.scripts.append({"auto_return": True})
    speak(env, sink=sink)
    call = env.native.wait_call()
    assert delivered.wait(3)
    assert threads[0] is not call.thread
    assert threads[0] is not env.driver._SynthDriver__tts_thread


@pytest.mark.parametrize("fault", ["native", "result", "feed", "idle"])
def test_swallowed_native_and_audio_failures_never_publish_success(env, fault):
    script = {"auto_return": True}
    if fault == "native": script["raise_native"] = True
    if fault == "result": script["result"] = 0
    if fault in ("feed", "idle"):
        original = env.inner.nvwave.WavePlayer
        def player(**kwargs):
            result = original(**kwargs)
            result.error = fault
            return result
        env.inner.nvwave.WavePlayer = player
    env.native.scripts.append(script)
    _, _, events = speak(env)
    assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert env.native.deleted == [1]


def test_cancelled_old_callbacks_do_not_complete_or_index_successor(env):
    _, old_context, old_events = speak(env, segment=1, text="old")
    old_call = env.native.wait_call()
    assert old_call.done.wait(3)
    cancel_thread = Thread(target=env.driver.cancel)
    cancel_thread.start()
    old_call.return_release.set()
    cancel_thread.join(3)
    assert not cancel_thread.is_alive()
    env.native.scripts.append({"auto_return": True})
    _, new_context, new_events = speak(env, segment=2, text="new")
    new_call = env.native.wait_call(2)
    env.native.callbacks.process_mark(b"99", old_call.user_data)
    env.native.callbacks.done(old_call.user_data)
    event = new_events.wait_one()
    assert event.segment_id == new_context.segment_id
    assert event.kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert old_events == []
    assert env.indexes == [7, 7]


def test_stop_failure_fails_closed_for_later_work(env):
    _, _, old_events = speak(env, text="old")
    call = env.native.wait_call()
    assert call.done.wait(3)
    env.players[0].stop_error = OSError("stop failed")
    with pytest.raises(OSError, match="stop failed"):
        env.driver.cancel()
    call.return_release.set()
    env.native.scripts.append({"auto_return": True})
    _, _, next_events = speak(env, text="new")
    assert next_events.wait_one().kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert old_events == []


def test_cancel_sees_operation_accepted_before_wrapper_registration(env, monkeypatch):
    accepted, release_accept = Event(), Event()
    lifecycle = env.driver._segmentLifecycle
    real_accept = lifecycle.accept

    def held_accept(*args):
        operation = real_accept(*args)
        accepted.set()
        assert release_accept.wait(3)
        return operation

    monkeypatch.setattr(lifecycle, "accept", held_accept)
    token = env.scheduler.CancellationToken()
    context = env.rt.models.PlaybackContext(object(), 17)
    events = []
    speaking = Thread(target=lambda: env.driver.speak_segment(("hello",), token,
        context=context, on_event=events.append), daemon=True)
    speaking.start()
    try:
        assert accepted.wait(1)
        cancelled = Event()
        cancelling = Thread(target=lambda: (env.driver.cancel(), cancelled.set()), daemon=True)
        cancelling.start()
        # The accepted operation must be registered before cancel can finish.
        assert not cancelled.wait(0.1)
        release_accept.set()
        speaking.join(3)
        cancelling.join(3)
        assert not speaking.is_alive() and not cancelling.is_alive()
        assert env.native.calls == []
        assert events == []
    finally:
        release_accept.set()


def test_cancel_releases_queued_work_without_running_its_native_message(env):
    speak(env, text="active")
    call = env.native.wait_call()
    events = speak(env, text="queued")[2]
    reference = weakref.ref(events)
    stopper = Thread(target=env.driver.cancel)
    stopper.start()
    call.return_release.set()
    stopper.join(3)
    assert not stopper.is_alive()
    del events
    deadline = time.monotonic() + 3
    while reference() is not None and time.monotonic() < deadline:
        gc.collect()
        time.sleep(0.01)
    assert reference() is None
    assert len(env.native.calls) == 1


def test_delayed_old_index_callback_cannot_index_successor(env):
    speak(env, text="old")
    call = env.native.wait_call()
    assert call.done.wait(3)
    old_index = env.players[0].retained_callbacks[0] if env.players[0].retained_callbacks else None
    # The real WavePlayer may retain an onDone closure even after stop.
    assert old_index is not None
    stopper = Thread(target=env.driver.cancel)
    stopper.start()
    call.return_release.set()
    stopper.join(3)
    env.native.scripts.append({"auto_return": True})
    _, _, events = speak(env, text="new")
    env.native.wait_call(2)
    old_index()
    assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert env.indexes == [7, 7]


def test_support_is_enabled_for_every_reported_profile_with_evidence_caveat(env):
    for version, audio in (("2025.1", "waveOut"), ("2026.3", "wasapi"), (None, None)):
        support = env.driver.get_segment_drain_support(nvda_version=version, audio_mode=audio)
        assert support.supported is True
        assert "unverified" in support.reason.lower()
        assert "RHVoice" in support.profile


def test_legacy_done_callback_can_cancel_without_deadlocking_worker(env):
    cancelled = Event()
    def cancel_from_done(**kwargs):
        env.driver.cancel()
        cancelled.set()
    env.inner.synthDoneSpeaking.notify = cancel_from_done
    env.native.scripts.append({"auto_return": True})
    _, _, events = speak(env)
    call = env.native.wait_call()
    assert cancelled.wait(1)
    assert call.returned.wait(1)
    assert events == []


def test_cancel_waits_for_admitted_feed_and_stops_late_audio_before_successor(env):
    created = Event()
    original = env.inner.nvwave.WavePlayer
    def blocked_player(**kwargs):
        player = original(**kwargs)
        player.feed_release.clear()
        created.set()
        return player
    env.inner.nvwave.WavePlayer = blocked_player
    _, _, old_events = speak(env, text="old")
    old_call = env.native.wait_call()
    assert created.wait(3)
    player = env.players[0]
    assert player.feed_entered.wait(3)
    stopper = Thread(target=env.driver.cancel)
    stopper.start()
    assert player.stop_entered.wait(3)
    assert stopper.is_alive()
    player.feed_release.set()
    old_call.return_release.set()
    stopper.join(3)
    assert not stopper.is_alive()
    assert player.stops >= 2
    env.native.scripts.append({"auto_return": True})
    _, _, next_events = speak(env, text="new")
    assert next_events.wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert old_events == []


def test_terminate_releases_engine_after_stop_failure(env):
    env.native.scripts.append({"auto_return": True})
    _, _, events = speak(env)
    assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED
    env.players[0].stop_error = OSError("stop failed")
    with pytest.raises(OSError, match="stop failed"):
        env.driver.terminate()
    assert env.native.engine_deleted
    assert env.players[0].closed


def test_message_cleanup_waits_for_admitted_native_callback(env):
    callback_entered, release_callback = Event(), Event()
    real_set_sample_rate = env.driver._SynthDriver__player.set_sample_rate
    calls = 0
    def held_set_sample_rate(rate):
        nonlocal calls
        calls += 1
        if calls == 2:
            callback_entered.set()
            assert release_callback.wait(3)
        return real_set_sample_rate(rate)
    env.driver._SynthDriver__player.set_sample_rate = held_set_sample_rate
    def async_callback(callbacks, user_data):
        Thread(target=lambda: callbacks.set_sample_rate(22050, user_data), daemon=True).start()
        assert callback_entered.wait(3)
    env.native.scripts.append({"auto_return": True, "async_callback": async_callback})
    _, _, events = speak(env)
    call = env.native.wait_call()
    assert call.returned.wait(3)
    assert env.native.deleted == []
    assert events == []
    release_callback.set()
    assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert env.native.deleted == [1]


def test_legacy_speak_keeps_inner_settings_snapshot_and_queue(env):
    env.driver.rate = 70
    env.driver.pitch = 30
    env.driver.volume = 80
    env.driver.rateBoost = True
    env.native.scripts.append({"auto_return": True})
    env.driver.speak(("legacy", env.commands.IndexCommand(7)))
    call = env.native.wait_call()
    assert call.returned.wait(3)
    assert call.text == b"<speak>legacy</speak>"
    assert call.options.voice_profile == b"Alice"
    assert (call.options.rate, call.options.pitch, call.options.volume) == pytest.approx((0.4, -0.4, 0.6))
    assert call.options.boost == 2.5
    assert call.options.flags == env.inner.RHVoice_synth_flag.dont_clip_rate
    assert env.dones == [env.driver]


def test_rhvoice_shared_lifecycle_waits_for_nested_feed_and_final_idle(env):
    assert env.driver._segmentLifecycle is not None
    callback_entered, release_callback = Event(), Event()
    original_rate = env.driver._SynthDriver__player.set_sample_rate
    calls = 0
    def delayed_rate(rate):
        nonlocal calls
        calls += 1
        if calls == 2:
            callback_entered.set()
            assert release_callback.wait(3)
            env.driver._SynthDriver__player.do_play(b"nested")
        return original_rate(rate)
    env.driver._SynthDriver__player.set_sample_rate = delayed_rate
    def callback(callbacks, user_data):
        Thread(target=lambda: callbacks.set_sample_rate(22050, user_data), daemon=True).start()
        assert callback_entered.wait(3)
        env.players[0].block_idle_number = 3
        env.players[0].idle_release.clear()
    env.native.scripts.append({"auto_return": True, "async_callback": callback})
    _, _, old_events = speak(env, text="old")
    old_call = env.native.wait_call()
    assert old_call.returned.wait(3)
    player = env.players[0]
    env.native.scripts.append({"auto_return": True})
    _, _, new_events = speak(env, segment=2, text="new")
    assert_no_successor_native_call(env)
    assert old_events == []
    release_callback.set()
    assert player.third_idle_entered.wait(3)
    assert_no_successor_native_call(env)
    assert old_events == []
    player.idle_release.set()
    assert old_events.wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED
    env.native.wait_call(2)
    assert new_events.wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED


def test_rhvoice_shared_cancel_keeps_old_identity_until_retirement(env):
    assert env.driver._segmentLifecycle is not None
    created = Event()
    original = env.inner.nvwave.WavePlayer
    def blocked_player(**kwargs):
        player = original(**kwargs)
        player.feed_release.clear()
        created.set()
        return player
    env.inner.nvwave.WavePlayer = blocked_player
    _, _, old_events = speak(env, text="old")
    old_call = env.native.wait_call()
    assert created.wait(3)
    player = env.players[0]
    assert player.feed_entered.wait(3)
    original_id = old_call.user_data
    stopper = Thread(target=env.driver.cancel)
    stopper.start()
    assert player.stop_entered.wait(3)
    env.native.scripts.append({"auto_return": True})
    _, _, new_events = speak(env, segment=2, text="new")
    assert_no_successor_native_call(env)
    assert original_id in env.driver._segmentById
    player.feed_release.set()
    old_call.return_release.set()
    stopper.join(3)
    assert not stopper.is_alive()
    env.native.wait_call(2)
    assert new_events.wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert old_events == []
    assert original_id not in env.driver._segmentById


def test_rhvoice_shared_token_cancel_clears_native_flag_before_successor(env):
    token, _, old_events = speak(env, text="old")
    old_call = env.native.wait_call()
    assert old_call.done.wait(3)
    token.cancel()
    old_call.return_release.set()
    assert old_call.returned.wait(3)
    env.native.scripts.append({"auto_return": True})
    _, _, next_events = speak(env, segment=2, text="new")
    env.native.wait_call(2)
    assert next_events.wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert old_events == []


def test_rhvoice_shared_sink_reenters_terminate(env):
    assert env.driver._segmentLifecycle is not None
    delivered = Event()
    errors = []
    def sink(event):
        try:
            env.driver.terminate()
        except Exception as error:
            errors.append(error)
        delivered.set()
    env.native.scripts.append({"auto_return": True})
    speak(env, sink=sink)
    call = env.native.wait_call()
    assert delivered.wait(3)
    assert call.returned.is_set()
    assert errors == []
    assert env.native.engine_deleted


def test_reentrant_successor_during_concurrent_cancel_does_not_deadlock(env):
    done_entered, successor_queued = Event(), Event()
    successor_events = []
    def enqueue_from_done(**kwargs):
        if done_entered.is_set():
            return
        done_entered.set()
        assert env.players[0].stop_entered.wait(3)
        successor_events.append(speak(env, segment=2, text="successor")[2])
        successor_queued.set()
    env.inner.synthDoneSpeaking.notify = enqueue_from_done
    env.native.scripts.extend(({"auto_return": True}, {"auto_return": True}))
    speak(env, segment=1, text="old")
    old_call = env.native.wait_call()
    assert done_entered.wait(3)
    stopper = Thread(target=env.driver.cancel)
    stopper.start()
    assert successor_queued.wait(1)
    stopper.join(3)
    assert not stopper.is_alive()
    env.native.wait_call(2)
    assert successor_events[0].wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED


def test_cancel_invalidates_completion_waiting_for_async_delivery(env, monkeypatch):
    delivery_waiting, release_delivery = Event(), Event()
    lifecycle = env.driver._segmentLifecycle
    queue_delivery = lifecycle._queue_delivery_locked
    def delayed_delivery(operation):
        delivery_waiting.set()
        assert release_delivery.wait(3)
        queue_delivery(operation)
    monkeypatch.setattr(lifecycle, "_queue_delivery_locked", delayed_delivery)
    env.native.scripts.append({"auto_return": True})
    _, _, events = speak(env)
    assert delivery_waiting.wait(3)
    stopper = Thread(target=env.driver.cancel)
    stopper.start()
    try:
        deadline = time.monotonic() + 3
        while not any(operation._rhvoice_cancelled for operation in env.driver._segmentAccepted) and time.monotonic() < deadline:
            time.sleep(0.001)
        assert any(operation._rhvoice_cancelled for operation in env.driver._segmentAccepted)
    finally:
        release_delivery.set()
    stopper.join(3)
    assert not stopper.is_alive()
    assert events == []


def test_audio_index_listener_can_cancel_from_its_own_callback_thread(env):
    created = Event()
    real_player = env.inner.nvwave.WavePlayer
    def threaded_player(**kwargs):
        player = real_player(**kwargs)
        player.threaded_callbacks = True
        created.set()
        return player
    env.inner.nvwave.WavePlayer = threaded_player
    index_thread, cancelled = [], Event()
    def cancel_from_index(**kwargs):
        index_thread.append(current_thread())
        env.driver.cancel()
        cancelled.set()
    env.inner.synthIndexReached.notify = cancel_from_index
    env.native.scripts.append({"auto_return": True})
    _, _, events = speak(env)
    call = env.native.wait_call()
    assert created.wait(3)
    assert cancelled.wait(3)
    assert call.returned.wait(3)
    assert index_thread[0] is not call.thread
    assert events == []


def test_stop_fault_before_deferred_terminal_delivery_fails_closed(env, monkeypatch):
    delivery_waiting, release_delivery = Event(), Event()
    lifecycle = env.driver._segmentLifecycle
    queue_delivery = lifecycle._queue_delivery_locked
    def delayed_delivery(operation):
        delivery_waiting.set()
        assert release_delivery.wait(3)
        queue_delivery(operation)
    monkeypatch.setattr(lifecycle, "_queue_delivery_locked", delayed_delivery)
    env.native.scripts.append({"auto_return": True})
    _, _, events = speak(env)
    assert delivery_waiting.wait(3)
    env.players[0].stop_error = OSError("stop failed")
    stop_errors = []
    def stop_player():
        try:
            env.driver._SynthDriver__player.stop()
        except OSError as error:
            stop_errors.append(error)
    stopper = Thread(target=stop_player)
    stopper.start()
    try:
        deadline = time.monotonic() + 3
        while env.driver._segmentControlError is None and time.monotonic() < deadline:
            time.sleep(0.001)
        assert env.driver._segmentControlError is not None
    finally:
        release_delivery.set()
    stopper.join(3)
    assert len(stop_errors) == 1
    assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_FAILED


def test_callback_cancel_does_not_wait_for_delivery_cancel_awaiting_that_callback(env):
    delivery_started, index_entered, delivery_stopped = Event(), Event(), Event()
    delivery_cancelled, index_cancelled = Event(), Event()
    delivery_thread = []
    original_stop = env.driver._SynthDriver__player.stop
    def observed_stop():
        if delivery_thread and current_thread() is delivery_thread[0]:
            delivery_stopped.set()
        return original_stop()
    env.driver._SynthDriver__player.stop = observed_stop
    def on_index(**kwargs):
        if not delivery_started.is_set():
            return
        index_entered.set()
        assert delivery_stopped.wait(3)
        env.driver.cancel()
        index_cancelled.set()
    env.inner.synthIndexReached.notify = on_index
    def on_first_event(event):
        delivery_thread.append(current_thread())
        env.players[0].threaded_callbacks = True
        delivery_started.set()
        assert index_entered.wait(3)
        env.driver.cancel()
        delivery_cancelled.set()
    env.native.scripts.extend((
        {"auto_return": True},
        {"auto_return": True, "before_callbacks": lambda: delivery_started.wait(3)},
    ))
    speak(env, segment=1, text="first", sink=on_first_event)
    speak(env, segment=2, text="second")
    assert env.native.wait_call(2)
    assert index_entered.wait(3)
    assert delivery_cancelled.wait(2)
    assert index_cancelled.wait(2)


def test_admitted_late_feed_gets_final_idle_and_index_before_drain(env):
    late_callbacks = []
    def late_pcm_and_mark(callbacks, user_data):
        player = env.players[0]
        player.feed_release.clear()
        def emit_late():
            samples = (ctypes.c_short * 2)(3, 4)
            callbacks.play_speech(samples, 2, user_data)
            callbacks.process_mark(b"99", user_data)
        thread = Thread(target=emit_late, daemon=True)
        late_callbacks.append(thread)
        thread.start()
        assert player.second_feed_entered.wait(3)
    env.native.scripts.append({"auto_return": True, "async_callback": late_pcm_and_mark})
    _, _, events = speak(env)
    call = env.native.wait_call()
    speech = env.driver._segmentById[call.user_data]
    assert call.done.wait(3)
    player = env.players[0]
    assert call.returned.wait(3)
    assert player.second_idle_completed.wait(3)
    deadline = time.monotonic() + 3
    while not speech.closed and time.monotonic() < deadline:
        time.sleep(0.001)
    assert speech.closed
    assert events == []
    assert player.fed == [b"\x01\x00\x02\x00"]
    player.block_idle_number = 3
    player.idle_release.clear()
    player.feed_release.set()
    late_callbacks[0].join(3)
    assert not late_callbacks[0].is_alive()
    try:
        assert player.third_idle_entered.wait(3)
        assert events == []
    finally:
        player.idle_release.set()
    assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert player.fed == [b"\x01\x00\x02\x00", b"\x03\x00\x04\x00"]
    assert env.indexes == [7, 99]
    assert player.stops == 0
    assert player.idle_count >= 3


def test_admitted_native_mark_can_enter_nested_feed_after_callback_gate_closes(env):
    mark_entered, release_mark = Event(), Event()
    mark_threads = []
    audio = env.driver._SynthDriver__player
    real_get_player = audio.get_player
    def held_get_player():
        player = real_get_player()
        if mark_threads and current_thread() is mark_threads[0]:
            mark_entered.set()
            assert release_mark.wait(3)
        return player
    audio.get_player = held_get_player
    def late_mark(callbacks, user_data):
        def emit():
            samples = (ctypes.c_short * 2)(3, 4)
            callbacks.play_speech(samples, 2, user_data)
            callbacks.process_mark(b"99", user_data)
        thread = Thread(target=emit, daemon=True)
        mark_threads.append(thread)
        thread.start()
        assert mark_entered.wait(3)
    env.native.scripts.append({"auto_return": True, "async_callback": late_mark})
    _, _, events = speak(env)
    call = env.native.wait_call()
    speech = env.driver._segmentById[call.user_data]
    assert call.done.wait(3)
    assert call.returned.wait(3)
    player = env.players[0]
    assert player.second_idle_completed.wait(3)
    deadline = time.monotonic() + 3
    while not speech.closed and time.monotonic() < deadline:
        time.sleep(0.001)
    assert speech.closed
    assert speech.consumers == 1  # The admitted mark still owns its native lease.
    assert env.native.callbacks.process_mark(b"100", call.user_data) == 0
    assert player.fed == [b"\x01\x00\x02\x00"]
    assert env.indexes == [7]
    assert events == []
    player.block_idle_number = 3
    player.idle_release.clear()
    try:
        release_mark.set()
        mark_threads[0].join(3)
        assert not mark_threads[0].is_alive()
        assert player.third_idle_entered.wait(3)
        assert events == []
    finally:
        player.idle_release.set()
    assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert player.fed == [b"\x01\x00\x02\x00", b"\x03\x00\x04\x00"]
    assert env.indexes == [7, 99]
    assert player.stops == 0
