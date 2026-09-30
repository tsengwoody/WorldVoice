"""Correlated RHVoice completion at the real installed outer wrapper."""

import gc
from threading import Event, Thread, current_thread
import weakref

import pytest

from rhvoice_drain_harness import finish, load_rhvoice, speak


@pytest.fixture
def env(monkeypatch, tmp_path):
    result = load_rhvoice(monkeypatch, tmp_path)
    yield result
    finish(result)


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
    gc.collect()
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


def test_support_is_explicitly_false_for_every_reported_profile(env):
    for version, audio in (("2025.1", "waveOut"), ("2026.3", "wasapi"), (None, None)):
        support = env.driver.get_segment_drain_support(nvda_version=version, audio_mode=audio)
        assert support.supported is False
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
