"""eSpeak drain requires callback idle and FIFO native retirement."""

from threading import Event, current_thread
import importlib
import sys

import pytest

from espeak_drain_harness import finish, load_espeak, speak, wait_event


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentLifecycle", raising=False)
    result = load_espeak(monkeypatch, tmp_path)
    yield result
    finish(result)


def test_callback_idle_end_precedes_native_return_and_drain_waits_for_fifo_barrier(env):
    delivery_threads = []
    _, context, events = speak(env, sink=lambda event: (delivery_threads.append(current_thread()), events.append(event)))
    call = env.native.wait_calls(1)
    assert env.player.idle_entered.wait(1)
    assert events == []
    env.player.idle_release.set()
    assert call.after_callback.wait(1)
    assert not call.returned.is_set()
    assert env.indexes == [7]
    assert events == []
    call.return_release.set()
    event = wait_event(events)
    assert event.kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert event.source_id is context.source_id
    assert event.segment_id == 17
    assert call.returned.is_set()
    assert delivery_threads[0] is not call.thread
    assert env.dones == []
    assert env.outer.Voice.synth_driver_class is type(env.driver)


@pytest.mark.parametrize("failure", ["feed", "idle", "native", "missing_end", "native_result"])
# The pinned NVDA callback catches player failures and returns None to ctypes.
# Its resulting conversion warning is upstream; the wrapper must still fail.
@pytest.mark.filterwarnings("ignore:Exception ignored while converting result of ctypes callback function:pytest.PytestUnraisableExceptionWarning")
def test_observable_callback_or_native_failure_fails_exact_context_after_return(env, failure):
    if failure in ("feed", "idle"):
        env.player.error = failure
    elif failure == "native":
        env.native.next_scripts.append({"error": True})
    elif failure == "native_result":
        env.native.next_scripts.append({"result": -1})
    else:
        env.native.next_scripts.append({"missing_end": True})
    _, context, events = speak(env)
    call = env.native.wait_calls(1)
    env.player.idle_release.set()
    if failure != "native":
        assert call.after_callback.wait(1)
        assert events == []
        call.return_release.set()
    event = wait_event(events)
    assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert event.source_id is context.source_id
    assert event.segment_id == 17
    assert isinstance(event.error, RuntimeError if failure in ("missing_end", "native_result") else OSError)
    assert call.returned.is_set()
    assert env.dones == []


def test_empty_audio_still_waits_for_idle_and_native_retirement(env):
    env.native.next_scripts.append({"empty": True})
    _, _, events = speak(env, commands=("",))
    call = env.native.wait_calls(1)
    assert env.player.idle_entered.wait(1)
    assert events == []
    env.player.idle_release.set()
    assert call.after_callback.wait(1)
    assert events == []
    call.return_release.set()
    assert wait_event(events).kind is env.rt.models.EventKind.SEGMENT_DRAINED


def test_espeak_shared_lifecycle_waits_for_fifo_and_empty_audio_idle(env):
    lifecycle = importlib.import_module(env.rt.package.__name__ + ".segmentLifecycle")
    env.native.next_scripts.append({"empty": True})
    _, context, events = speak(env, commands=("",))
    call = env.native.wait_calls(1)
    assert isinstance(env.driver._segmentNative.operation, lifecycle.SegmentOperation)
    assert env.player.idle_entered.wait(1)
    old_index = call.index_callback
    old_index(42)
    assert env.indexes == [42]
    assert events == []
    env.player.idle_release.set()
    assert call.after_callback.wait(1)
    assert events == []
    call.return_release.set()
    event = wait_event(events)
    assert event.kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert event.source_id is context.source_id
    old_index(99)
    assert env.indexes == [42]


def test_espeak_token_cancel_after_feed_discards_pcm_before_successor(env):
    lifecycle = importlib.import_module(env.rt.package.__name__ + ".segmentLifecycle")
    env.native.next_scripts.append({"hold_terminal": True})
    token, _, cancelled_events = speak(env)
    first = env.native.wait_calls(1)
    assert first.before_terminal.wait(1)
    assert env.player.queued_bytes == 8
    assert isinstance(env.driver._segmentNative.operation, lifecycle.SegmentOperation)
    token.cancel()
    _, successor_context, successor_events = speak(env, segment=18)
    assert len(env.native.calls) == 1
    first.terminal_release.set()
    first.return_release.set()
    second = env.native.wait_calls(2)
    assert second.queued_bytes_at_entry == 0
    env.player.idle_release.set()
    second.return_release.set()
    event = wait_event(successor_events)
    assert event.kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert event.source_id is successor_context.source_id
    assert cancelled_events == []


@pytest.mark.parametrize("cancelled", [False, True])
def test_ordinary_speech_waits_for_contextual_final_stop_before_using_player(env, cancelled):
    env.native.next_scripts.append({"hold_terminal": True} if cancelled else {"missing_end": True})
    token, _, segment_events = speak(env)
    first = env.native.wait_calls(1)
    assert first.before_terminal.wait(1)
    assert env.player.queued_bytes == 8
    if cancelled:
        token.cancel()
    env.driver.speak(("ordinary after segment",))
    stopped, release_stop = Event(), Event()
    original_stop = env.player.stop
    def held_stop():
        stopped.set()
        assert release_stop.wait(2), "Test did not release contextual cleanup"
        original_stop()
    env.player.stop = held_stop
    first.terminal_release.set()
    if not cancelled:
        env.player.idle_release.set()
    first.return_release.set()
    try:
        assert stopped.wait(1)
        assert len(env.native.calls) == 1, "Ordinary native work entered before old PCM cleanup"
    finally:
        release_stop.set()
        env.player.idle_release.set()
    ordinary = env.native.wait_calls(2)
    assert ordinary.queued_bytes_at_entry == 0
    ordinary.return_release.set()
    env.inner.bgQueue.join()
    assert env.dones == [env.driver]
    if cancelled:
        assert segment_events == []
    else:
        assert wait_event(segment_events).kind is env.rt.models.EventKind.SEGMENT_FAILED


def test_cancelling_queued_contextual_speech_preserves_active_ordinary_audio(env, monkeypatch):
    env.native.next_scripts.append({"hold_terminal": True})
    env.driver.speak(("ordinary remains active",))
    ordinary = env.native.wait_calls(1)
    assert ordinary.before_terminal.wait(1)
    assert env.player.queued_bytes == 8
    queued, release_queue = Event(), Event()
    original_queue = env.driver._queueSpeech
    def queue_then_hold(commands, work, operation=None):
        result = original_queue(commands, work, operation)
        if operation is not None:
            queued.set()
            assert release_queue.wait(2), "Test did not release contextual submission"
        return result
    monkeypatch.setattr(env.driver, "_queueSpeech", queue_then_hold)
    token, _, cancelled_events = speak(env, segment=18)
    assert queued.wait(1)
    token.cancel()
    release_queue.set()
    operation = next(iter(env.driver._segmentAccepted))
    with operation._lifecycle._condition:
        assert operation._lifecycle._condition.wait_for(lambda: operation._stop_done is not None, 1)
        stop_done = operation._stop_done
    assert stop_done.wait(1)
    assert env.player.stops == 0, "Queued cancellation stopped the ordinary player"
    assert env.player.queued_bytes == 8
    assert env.inner.isSpeaking
    assert len(env.native.calls) == 1
    env.player.idle_release.set()
    ordinary.terminal_release.set()
    ordinary.return_release.set()
    env.inner.bgQueue.join()
    assert env.dones == [env.driver]
    _, _, successor_events = speak(env, segment=19)
    successor = env.native.wait_calls(2)
    successor.return_release.set()
    assert wait_event(successor_events).kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert cancelled_events == []


@pytest.mark.parametrize("token_only", [False, True])
def test_cancelled_active_call_and_queued_call_retire_before_successor(env, token_only):
    token, _, events = speak(env)
    first = env.native.wait_calls(1)
    assert env.player.idle_entered.wait(1)
    queued_token, _, queued_events = speak(env, segment=18)
    if token_only:
        token.cancel()
        queued_token.cancel()
        env.player.idle_release.set()
    else:
        env.driver.cancel()
    _, successor_context, successor = speak(env, segment=19)
    assert len(env.native.calls) == 1
    first.return_release.set()
    second = env.native.wait_calls(2)
    assert first.returned.is_set()
    assert second.after_callback.wait(1)
    second.return_release.set()
    event = wait_event(successor)
    assert event.kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert event.source_id is successor_context.source_id
    assert event.segment_id == 19
    assert events == queued_events == []


def test_retained_old_indexes_and_end_callback_cannot_complete_successor(env):
    _, _, events = speak(env)
    first = env.native.wait_calls(1)
    assert env.player.idle_entered.wait(1)
    retained = env.player.callbacks[0]
    env.driver.cancel()
    _, _, successor = speak(env, segment=18)
    first.return_release.set()
    second = env.native.wait_calls(2)
    assert second.after_callback.wait(1)
    indexes = list(env.indexes)
    retained()
    first.index_callback(99)
    first.index_callback(None)
    assert env.indexes == indexes
    assert successor == []
    second.return_release.set()
    assert wait_event(successor).kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert events == []


def test_terminal_sink_can_terminate_after_native_retirement(env):
    terminated, deliveries = Event(), []
    def sink(event):
        deliveries.append(event)
        env.driver.terminate()
        terminated.set()
    speak(env, sink=sink)
    call = env.native.wait_calls(1)
    env.player.idle_release.set()
    assert call.after_callback.wait(1)
    call.return_release.set()
    assert terminated.wait(1), "Completion sink deadlocked in native/bgThread termination"
    assert len(deliveries) == 1
    assert deliveries[0].kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert env.native.terminated


@pytest.mark.parametrize("terminate", [False, True])
def test_cancel_or_terminate_before_deferred_delivery_keeps_event_silent(env, monkeypatch, terminate):
    entered, release, delivered = Event(), Event(), Event()
    original = env.driver._deliverSpeech
    def delayed(native, error):
        entered.set()
        assert release.wait(2)
        original(native, error)
        delivered.set()
    monkeypatch.setattr(env.driver, "_deliverSpeech", delayed)
    _, _, events = speak(env)
    call = env.native.wait_calls(1)
    env.player.idle_release.set()
    call.return_release.set()
    assert entered.wait(1)
    try:
        env.driver.terminate() if terminate else env.driver.cancel()
    finally:
        release.set()
    assert delivered.wait(1)
    assert events == []


def test_cancelled_feed_final_stop_finishes_before_successor_native_call(env):
    env.player.feed_release.clear()
    _, _, events = speak(env)
    first = env.native.wait_calls(1)
    assert env.player.feed_entered.wait(1)
    env.driver.cancel()
    _, _, successor = speak(env, segment=18)
    stopped, release_stop = Event(), Event()
    original_stop = env.player.stop
    def final_stop():
        stopped.set()
        assert release_stop.wait(2)
        original_stop()
    env.player.stop = final_stop
    env.player.feed_release.set()
    try:
        assert stopped.wait(1)
        first.return_release.set()
        assert len(env.native.calls) == 1
        assert successor == []
    finally:
        release_stop.set()
    second = env.native.wait_calls(2)
    second.return_release.set()
    assert wait_event(successor).kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert events == []


def test_token_cancel_between_last_feed_and_terminal_discards_pcm_before_successor(env):
    env.native.next_scripts.append({"hold_terminal": True})
    token, _, events = speak(env)
    first = env.native.wait_calls(1)
    assert first.before_terminal.wait(1)
    assert env.player.queued_bytes == 8
    token.cancel()
    _, _, successor = speak(env, segment=18)
    stopped, release_stop = Event(), Event()
    original_stop = env.player.stop
    def final_stop():
        stopped.set()
        assert release_stop.wait(2), "Test did not release final stop"
        original_stop()
    env.player.stop = final_stop
    first.terminal_release.set()
    first.return_release.set()
    try:
        assert stopped.wait(1), "Token cancellation left old PCM queued without a final stop"
        assert len(env.native.calls) == 1
        assert events == successor == []
    finally:
        release_stop.set()
        env.player.idle_release.set()
    second = env.native.wait_calls(2)
    assert second.queued_bytes_at_entry == 0
    second.return_release.set()
    assert wait_event(successor).kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert events == []


@pytest.mark.parametrize("cancelled", [False, True])
def test_failed_cleanup_stop_blocks_queued_and_later_native_admission(env, cancelled):
    stop_error = OSError("failed cleanup stop")
    env.player.stop_error = stop_error
    env.player.idle_release.set()
    env.native.next_scripts.extend(({"hold_terminal": True} if cancelled else {"missing_end": True},
                                   {"auto_return": True}))
    token, _, failed = speak(env)
    first = env.native.wait_calls(1)
    if cancelled:
        assert first.before_terminal.wait(1)
        token.cancel()
        first.terminal_release.set()
    assert first.after_callback.wait(1)
    _, successor_context, successor = speak(env, segment=18)
    first.return_release.set()
    if not cancelled:
        assert wait_event(failed).kind is env.rt.models.EventKind.SEGMENT_FAILED
    event = wait_event(successor)
    assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert event.error is stop_error
    assert event.source_id is successor_context.source_id
    assert len(env.native.calls) == 1
    assert not env.inner.isSpeaking, "Rejected native work left synthesis marked active"
    if cancelled:
        assert failed == []
    # A recovered stop alone does not prove a safe reset/reload. The latch
    # must still reject later correlated and legacy requests on this driver.
    env.player.stop_error = None
    _, _, later = speak(env, segment=19)
    assert wait_event(later).error is stop_error
    with pytest.raises(OSError) as rejected:
        env.driver.speak(("legacy after unsafe cleanup",))
    assert rejected.value is stop_error
    assert len(env.native.calls) == 1


def test_native_reset_exception_is_preserved_before_synth_entry(env):
    error = OSError("native reset failed")
    def failed_reset(*args):
        raise error
    env.native.espeak_ng_Cancel.callback = failed_reset
    _, context, events = speak(env)
    event = wait_event(events)
    assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert event.source_id is context.source_id
    assert event.error is error
    assert env.native.calls == []


def test_failure_sink_can_cancel_and_admit_successor(env):
    env.native.next_scripts.append({"error": True})
    successor_events, admitted = [], Event()
    def sink(event):
        assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
        env.driver.cancel()
        _, _, events = speak(env, segment=18)
        successor_events.append(events)
        admitted.set()
    speak(env, sink=sink)
    env.native.wait_calls(1)
    assert admitted.wait(1)
    next_call = env.native.wait_calls(2)
    env.player.idle_release.set()
    next_call.return_release.set()
    assert wait_event(successor_events[0]).kind is env.rt.models.EventKind.SEGMENT_DRAINED


def test_real_profile_is_enabled_with_unverified_evidence(env):
    support = env.driver.get_segment_drain_support(nvda_version="2026.3", audio_mode="wasapi")
    assert support.supported and "unverified" in support.reason.lower()


def test_correlated_path_preserves_base_language_variant_prosody_and_legacy_done(env):
    env.driver.variant = "max"
    commands = ("<&>", env.commands.LangChangeCommand("fr"), env.commands.PitchCommand(1.2),
                "bonjour", env.commands.IndexCommand(7))
    _, _, events = speak(env, commands=commands)
    call = env.native.wait_calls(1)
    assert call.text.startswith('&lt;&&gt;')
    assert '<voice xml:lang="fr-fr">' in call.text
    assert '<prosody pitch="120%">' in call.text
    assert '<mark name="7" />' in call.text
    env.player.idle_release.set()
    call.return_release.set()
    assert wait_event(events).kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert env.driver.variant == "max"
    env.driver.speak(("legacy",))
    legacy = env.native.wait_calls(2)
    assert legacy.after_callback.wait(1)
    legacy.return_release.set()
    env.inner.bgQueue.join()
    assert env.dones == [env.driver]
