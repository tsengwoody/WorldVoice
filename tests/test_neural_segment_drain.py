from threading import Event, current_thread
import gc
from pathlib import Path
import subprocess
import sys
import weakref

import pytest

from neural_drain_harness import in_thread, load_neural, prove_fake_quiescence


@pytest.fixture
def env(monkeypatch, tmp_path):
    result = load_neural(monkeypatch, tmp_path)
    yield result
    result.native.speak_release.set()
    result.native.stop_release.set()
    result.player.feed_release.set()
    result.player.idle_release.set()
    result.player.stop_release.set()
    if result.driver is not None:
        result.driver.terminate()


def speak(env, *, segment=17, commands=("hello",)):
    token = env.scheduler.CancellationToken()
    context = env.rt.models.PlaybackContext(object(), segment)
    events, done = [], Event()

    def receive(event):
        events.append(event)
        done.set()

    env.driver.speak_segment(commands, token, context=context, on_event=receive)
    return token, context, events, done


def finish(call):
    assert call.done.wait(2)
    assert call.errors == []


def complete(env, done):
    env.native.speak_release.set()
    env.player.idle_release.set()
    assert done.wait(2)


def test_neural_stream_owns_contextual_audio_callback(env):
    for stream in env.native.streams.values():
        callback = env.ffi.from_handle(stream.context)
        assert isinstance(callback, env.outer._ContextualAudioCallback)
        assert callback is env.driver._audioCallback
    assert env.outer.Voice.synth_driver_class is type(env.driver)


@pytest.mark.parametrize("version,mode", [("2026.3", "wasapi"), ("source-9ef645d", "wasapi"), ("2025.3", "legacy")])
def test_all_profiles_are_enabled_with_unverified_evidence(env, version, mode):
    support = env.driver.get_segment_drain_support(nvda_version=version, audio_mode=mode)
    assert support.supported is True
    assert "unverified" in support.reason.lower()
    assert "1.50.0.28" in support.profile


def test_sonic_tail_feed_does_not_complete_before_idle(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    env.driver.rateBoost = True
    _, context, events, done = speak(env)
    env.native.wait_calls(1)
    env.native.audio()
    env.native.speak_release.set()
    assert env.player.idle_entered.wait(2)
    assert env.player.fed == [b"\x03\x04\x05\x06"]
    assert events == []
    env.player.idle_release.set()
    assert done.wait(2)
    assert events[0].kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert events[0].source_id is context.source_id
    assert events[0].segment_id == 17
    assert env.dones == []


def test_langchange_tasks_share_work_snapshot_and_one_drain(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    change = env.commands.LangChangeCommand()
    change.lang = "fr"
    _, _, events, done = speak(env, commands=("hello", change, "bonjour"))
    env.native.wait_calls(1)
    env.driver._voiceSettings["voice2"].rate = 100
    complete(env, done)
    assert len(env.native.calls) == 2
    assert "'voice1', 50," in env.native.calls[0][1]
    assert "'voice2', 50," in env.native.calls[1][1]
    assert len(events) == 1


def test_neural_shared_lifecycle_waits_for_all_langchange_tasks_and_sonic_idle(env, monkeypatch):
    from neural_drain_harness import Sonic
    prove_fake_quiescence(env, monkeypatch)
    change = env.commands.LangChangeCommand()
    change.lang = "fr"
    env.driver.rateBoost = True
    streams = iter((Sonic(), Sonic()))
    monkeypatch.setattr(env.driver._audioCallback, "_createSonicStream", lambda: next(streams))
    _, _, events, done = speak(env, commands=("hello", change, "bonjour"))
    env.native.wait_calls(1)
    env.native.audio()
    env.native.speak_release.set()
    env.native.wait_calls(2)
    assert events == []
    env.native.audio()
    assert env.player.idle_entered.wait(2)
    assert len(env.player.fed) == 2
    assert events == []
    env.player.idle_release.set()
    assert done.wait(2)
    assert [event.kind for event in events] == [env.rt.models.EventKind.SEGMENT_DRAINED]
    assert isinstance(env.driver._segmentLifecycle, env.outer.SegmentLifecycle)


def test_neural_cancelled_callback_cannot_feed_successor(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    speak(env)
    env.native.wait_calls(1)
    env.player.feed_release.clear()
    old_callback = in_thread(lambda: env.native.audio(b"old PCM"))
    assert env.player.feed_entered.wait(1)
    env.native.stop_release.clear()
    env.driver.cancel()
    _, _, events, done = speak(env, segment=18)
    env.native.speak_release.set()
    assert env.native.stop_wait_entered.wait(1)
    assert len(env.native.calls) == 1
    env.native.stop_release.set()
    assert not done.wait(0.05)
    assert len(env.native.calls) == 1
    env.player.feed_release.set()
    finish(old_callback)
    env.native.wait_calls(2)
    env.native.audio(b"new PCM")
    assert done.wait(2)
    assert env.player.fed[-1] == b"new PCM"
    assert [event.kind for event in events] == [env.rt.models.EventKind.SEGMENT_DRAINED]
    assert isinstance(env.driver._segmentLifecycle, env.outer.SegmentLifecycle)


def test_neural_cancel_retires_queued_lifecycle_operation(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    speak(env)
    env.native.wait_calls(1)
    speak(env, segment=18)
    env.driver.cancel()
    env.native.speak_release.set()
    with env.driver._segmentLifecycle._condition:
        assert env.driver._segmentLifecycle._condition.wait_for(
            lambda: not env.driver._segmentLifecycle._resource_busy, 2)
        assert env.driver._segmentLifecycle._operations == set()


def test_neural_cancel_before_delayed_terminal_commit_is_silent(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    entered, release = Event(), Event()
    first_events = []

    def hold_first_delivery(event):
        first_events.append(event)
        entered.set()
        assert release.wait(2)

    env.driver.speak_segment(("first",), env.scheduler.CancellationToken(),
        context=env.rt.models.PlaybackContext(object(), 17), on_event=hold_first_delivery)
    env.native.wait_calls(1)
    env.player.idle_release.set()
    env.native.speak_release.set()
    assert entered.wait(1)
    _, _, second_events, _ = speak(env, segment=18)
    try:
        env.native.wait_calls(2)
        with env.driver._segmentLifecycle._condition:
            assert env.driver._segmentLifecycle._condition.wait_for(
                lambda: any(op.work.context.segment_id == 18
                            for op in env.driver._segmentLifecycle._delivery_queue), 2)
        assert env.player.idle_entered.is_set()
        env.driver.cancel()
    finally:
        release.set()
    with env.driver._segmentLifecycle._condition:
        assert env.driver._segmentLifecycle._condition.wait_for(
            lambda: not env.driver._segmentLifecycle._operations, 2)
    assert len(first_events) == 1
    assert second_events == []


def test_neural_waits_for_stop_and_callback_exit(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    _, _, old_events, _ = speak(env)
    env.native.wait_calls(1)
    old = env.native.calls[0][0]
    env.native.stop_release.clear()
    env.player.feed_release.clear()
    callback = in_thread(env.native.audio)
    assert env.player.feed_entered.wait(1)
    env.driver.cancel()
    _, _, new_events, done = speak(env, segment=18)
    assert env.native.stop_wait_entered.wait(1)
    assert len(env.native.calls) == 1
    assert env.native.operations[0][1] == old
    env.native.speak_release.set()
    env.native.stop_release.set()
    assert not env.player.idle_entered.wait(0.05)
    assert len(env.native.calls) == 1
    env.player.feed_release.set()
    finish(callback)
    assert done.wait(2)
    assert old_events == []
    assert new_events[0].kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert len(env.native.calls) == 2
    assert env.player.stops >= 2
    assert env.native.released == [operation[0] for operation in env.native.operations]


def test_stop_completion_and_zero_callbacks_do_not_prove_native_speak_exit(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    speak(env)
    env.native.wait_calls(1)
    env.driver.cancel()
    _, _, _, done = speak(env, segment=18)
    assert env.native.stop_wait_entered.wait(1)
    assert len(env.native.calls) == 1
    complete(env, done)
    assert len(env.native.calls) == 2


def test_explicit_activation_override_completes_with_unproven_quiescence(env):
    _, _, events, done = speak(env)
    env.native.wait_calls(1)
    complete(env, done)
    assert events[0].kind is env.rt.models.EventKind.SEGMENT_DRAINED
    speak(env, segment=18)
    env.native.wait_calls(2)
    assert len(env.native.calls) == 2
    assert env.native.audio() == 2
    assert env.player.fed == [b"\x01\x02"]


@pytest.mark.parametrize("failure", ["feed", "idle", "write", "flush", "sdk", "task", "stop"])
def test_errors_fail_original_work_once_and_never_done(env, monkeypatch, failure):
    prove_fake_quiescence(env, monkeypatch)
    if failure in ("write", "flush"):
        env.driver.rateBoost = True
        env.sonic.error = failure
    elif failure in ("feed", "idle"):
        env.player.error = failure
    elif failure == "sdk":
        env.native.result = 1
    elif failure == "task":
        env.native.speak_error = RuntimeError("native task raised")
    else:
        env.native.stop_error = RuntimeError("stop failed")
    _, context, events, done = speak(env)
    env.native.wait_calls(1)
    assert env.native.audio() == 2
    complete(env, done)
    assert len(events) == 1
    assert events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert events[0].source_id is context.source_id
    assert env.dones == []


def test_sonic_initialization_falls_back_before_speech(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    def unavailable():
        raise OSError("Sonic unavailable")
    monkeypatch.setattr(env.driver._audioCallback, "_createSonicStream", unavailable)
    env.driver.rateBoost = True
    _, _, events, done = speak(env)
    env.native.wait_calls(1)
    assert "'voice1', 50," in env.native.calls[0][1]
    env.native.audio()
    complete(env, done)
    assert env.player.fed == [b"\x01\x02"]
    assert events[0].kind is env.rt.models.EventKind.SEGMENT_DRAINED


def test_bookmark_handle_survives_stop_then_drops_stale_notification(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    index = env.commands.IndexCommand()
    index.index = 1
    speak(env, commands=(index, "hello"))
    env.native.wait_calls(1)
    saved = env.native.synths[env.native.calls[0][0]].bookmark
    handle = weakref.ref(saved[1])
    env.native.stop_release.clear()
    env.driver.cancel()
    assert handle() is not None
    env.native.bookmark(saved=saved)
    assert env.indexes == []
    _, _, _, done = speak(env, segment=18)
    env.native.speak_release.set()
    env.native.stop_release.set()
    assert done.wait(2)
    env.native.bookmark(saved=saved)
    assert env.indexes == []


def test_cancel_stops_actual_langchange_synth_not_selected_voice(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    change = env.commands.LangChangeCommand()
    change.lang = "fr"
    speak(env, commands=(change, "bonjour"))
    env.native.wait_calls(1)
    assert env.native.calls[0][0] != env.driver._voice._synth._handle
    env.driver.cancel()
    assert env.native.stop_start_entered.wait(1)
    assert env.native.operations[0][1] == env.native.calls[0][0]


@pytest.mark.parametrize("kind", ["empty", "index", "break"])
def test_successful_zero_audio_segments_have_final_idle(env, monkeypatch, kind):
    prove_fake_quiescence(env, monkeypatch)
    commands = ()
    if kind != "empty":
        command = (env.commands.IndexCommand if kind == "index" else env.commands.BreakCommand)()
        command.index = 1
        command.time = 20
        commands = (command,)
    _, _, events, done = speak(env, commands=commands)
    env.native.wait_calls(1)
    env.native.speak_release.set()
    assert env.player.idle_entered.wait(1)
    assert events == []
    env.player.idle_release.set()
    assert done.wait(2)
    assert events[0].kind is env.rt.models.EventKind.SEGMENT_DRAINED


def test_pause_holds_drain_until_resume(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    env.driver.pause(True)
    _, _, events, done = speak(env)
    env.native.wait_calls(1)
    env.native.speak_release.set()
    env.player.idle_release.set()
    assert env.player.idle_entered.wait(1)
    assert not done.wait(0.05)
    env.driver.pause(False)
    assert done.wait(2)
    assert len(events) == 1


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("terminate", [False, True])
def test_late_pause_retires_before_cancel_handoff_or_player_close(env, monkeypatch, legacy, terminate):
    prove_fake_quiescence(env, monkeypatch)
    if legacy:
        env.driver.speak(("old legacy",))
        old_events = []
    else:
        _, _, old_events, _ = speak(env)
    env.native.wait_calls(1)
    original_pause, original_stop = env.player.pause, env.player.stop
    pause_entered, release_pause, stopped = Event(), Event(), Event()

    def blocked_pause(switch):
        if switch:
            pause_entered.set()
            assert release_pause.wait(2), "Test did not release pause"
        original_pause(switch)

    def observed_stop():
        original_stop()
        stopped.set()

    monkeypatch.setattr(env.player, "pause", blocked_pause)
    monkeypatch.setattr(env.player, "stop", observed_stop)
    pausing = in_thread(lambda: env.driver.pause(True))
    assert pause_entered.wait(1)
    closing = in_thread(env.driver.terminate if terminate else env.driver.cancel)
    try:
        assert stopped.wait(1), "Cancel must stop before waiting for an entered pause"
        env.native.speak_release.set()
        assert not closing.done.wait(0.05), "Control call retired before the entered pause"
        if terminate:
            assert not env.player.closed
        else:
            if legacy:
                env.driver.speak(("successor legacy",))
            else:
                _, _, _, successor_done = speak(env, segment=18)
            with env.native.condition:
                assert not env.native.condition.wait_for(lambda: len(env.native.calls) >= 2, 0.05)
    finally:
        release_pause.set()
        finish(pausing)
        finish(closing)
    assert old_events == []
    if terminate:
        assert env.player.closed
    else:
        env.native.wait_calls(2)
        assert not env.player.paused, "The retired pause affected successor playback"
        env.player.idle_release.set()
        assert (env.done_event if legacy else successor_done).wait(2)


@pytest.mark.parametrize("legacy", [False, True])
def test_entered_pause_holds_new_native_admission(env, monkeypatch, legacy):
    prove_fake_quiescence(env, monkeypatch)
    original_pause = env.player.pause
    entered, release = Event(), Event()

    def blocked_pause(switch):
        entered.set()
        assert release.wait(2), "Test did not release pause"
        original_pause(switch)

    monkeypatch.setattr(env.player, "pause", blocked_pause)
    pausing = in_thread(lambda: env.driver.pause(True))
    assert entered.wait(1)
    try:
        if legacy:
            env.driver.speak(("queued legacy",))
        else:
            speak(env)
        with env.native.condition:
            assert not env.native.condition.wait_for(lambda: bool(env.native.calls), 0.05)
    finally:
        release.set()
        finish(pausing)
    env.native.wait_calls(1)


@pytest.mark.parametrize("switch", [False, True])
def test_pause_after_termination_does_not_touch_closed_player(env, switch):
    env.driver.terminate()
    calls = list(env.player.pause_calls)
    env.driver.pause(switch)
    assert env.player.closed
    assert env.player.pause_calls == calls


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("switch", [False, True])
def test_pause_or_resume_error_releases_work_and_blocks_admission(env, monkeypatch, legacy, switch):
    prove_fake_quiescence(env, monkeypatch)
    if legacy:
        env.driver.speak(("legacy",))
        events, done = [], env.done_event
    else:
        _, context, events, done = speak(env)
    env.native.wait_calls(1)
    if not switch:
        env.driver.pause(True)
    env.native.speak_release.set()
    assert env.player.idle_entered.wait(1)
    env.player.error = "pause" if switch else "resume"
    with pytest.raises(OSError, match="audio control failed") as raised:
        env.driver.pause(switch)
    assert done.wait(1), "Failed control left the speaking wait unresolved"
    if legacy:
        assert env.dones == [env.driver]
    else:
        assert len(events) == 1
        assert events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
        assert events[0].error is raised.value
        assert events[0].source_id is context.source_id
        assert events[0].segment_id == context.segment_id
        assert env.dones == []
    _, _, rejected, rejected_done = speak(env, segment=18)
    assert rejected_done.wait(1)
    assert len(rejected) == 1 and rejected[0].error is raised.value
    with pytest.raises(OSError) as rejected_legacy:
        env.driver.speak(("uncertain player",))
    assert rejected_legacy.value is raised.value
    assert len(env.native.calls) == 1


@pytest.mark.parametrize("legacy", [False, True])
def test_cancel_after_control_failure_capture_suppresses_terminal_delivery(env, monkeypatch, legacy):
    prove_fake_quiescence(env, monkeypatch)
    if legacy:
        env.driver.speak(("legacy",))
        events = []
    else:
        _, _, events, _ = speak(env)
    env.native.wait_calls(1)
    entered, release = Event(), Event()
    deliver = env.driver._deliver_control_failure

    def blocked_delivery(failure):
        entered.set()
        assert release.wait(2), "Test did not release control failure delivery"
        deliver(failure)

    monkeypatch.setattr(env.driver, "_deliver_control_failure", blocked_delivery)
    env.player.error = "pause"
    pausing = in_thread(lambda: env.driver.pause(True))
    try:
        assert entered.wait(1)
        # Failure has been captured and the pause lock released, while its
        # terminal event has not yet run. Cancel must still invalidate the work.
        env.driver.cancel()
        assert events == []
        assert env.dones == []
    finally:
        release.set()
        assert pausing.done.wait(2)
        env.native.speak_release.set()
    assert len(pausing.errors) == 1
    assert isinstance(pausing.errors[0], OSError)
    assert str(pausing.errors[0]) == "audio control failed"
    finish(in_thread(env.driver._task_queue.join))
    assert events == [], "Captured contextual failure escaped after cancel returned"
    assert env.dones == [], "Captured legacy failure emitted stale DONE after cancel returned"


@pytest.mark.parametrize("failure", [False, True])
@pytest.mark.parametrize("action", ["cancel", "terminate"])
def test_legacy_terminal_notification_allows_synchronous_control_reentry(env, monkeypatch, failure, action):
    env.driver.speak(("legacy",))
    env.native.wait_calls(1)
    notify, returned = env.outer.synthDoneSpeaking.notify, Event()

    def reentrant_notify(**kwargs):
        notify(**kwargs)
        getattr(env.driver, action)()
        returned.set()

    monkeypatch.setattr(env.outer.synthDoneSpeaking, "notify", reentrant_notify)
    try:
        if failure:
            env.player.error = "pause"
            pausing = in_thread(lambda: env.driver.pause(True))
            assert returned.wait(1), "Failure DONE handler deadlocked on synchronous control reentry"
            assert pausing.done.wait(1)
            assert len(pausing.errors) == 1 and isinstance(pausing.errors[0], OSError)
        else:
            env.native.speak_release.set()
            env.player.idle_release.set()
            assert returned.wait(1), "Drained DONE handler deadlocked on synchronous control reentry"
        assert env.dones == [env.driver]
    finally:
        env.native.speak_release.set()
    if action == "terminate":
        assert env.driver._terminationDone.wait(2)


def test_terminate_cancels_blocked_drain_and_closes_player(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    _, _, events, _ = speak(env)
    env.native.wait_calls(1)
    env.native.speak_release.set()
    assert env.player.idle_entered.wait(1)
    env.driver.terminate()
    assert events == []
    assert env.player.closed


def test_cancelled_token_never_starts_native(env):
    token = env.scheduler.CancellationToken()
    token.cancel()
    env.driver.speak_segment(("old",), token, context=env.rt.models.PlaybackContext(object(), 1), on_event=lambda event: pytest.fail("cancelled event"))
    assert env.native.calls == []


def test_legacy_speak_still_delivers_done(env):
    env.driver.speak(("legacy",))
    env.native.wait_calls(1)
    env.native.audio()
    env.native.speak_release.set()
    env.player.idle_release.set()
    assert env.player.idle_entered.wait(1)
    assert env.done_event.wait(1)
    assert env.dones == [env.driver]


def test_cancel_in_progress_blocks_new_native_submission(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    env.player.stop_release.clear()
    cancelling = in_thread(env.driver.cancel)
    assert env.player.stop_entered.wait(1)
    _, _, _, done = speak(env)
    assert not env.player.feed_entered.wait(0.05)
    assert env.native.calls == []
    env.player.stop_release.set()
    finish(cancelling)
    env.native.wait_calls(1)
    complete(env, done)


def test_terminate_waits_for_entered_callback_even_without_quiescence_proof(env):
    speak(env)
    env.native.wait_calls(1)
    env.player.feed_release.clear()
    callback = in_thread(env.native.audio)
    assert env.player.feed_entered.wait(1)
    env.native.speak_release.set()
    assert env.native.stop_wait_entered.wait(1)
    terminating = in_thread(env.driver.terminate)
    assert not terminating.done.wait(0.05)
    assert not env.player.closed
    env.player.feed_release.set()
    finish(callback)
    finish(terminating)
    assert env.player.closed


def test_cancelled_legacy_synthesis_does_not_emit_indexes_or_done(env):
    index = env.commands.IndexCommand()
    index.index = 1
    env.driver.speak((index, "legacy"))
    env.native.wait_calls(1)
    saved = env.native.synths[env.native.calls[0][0]].bookmark
    env.driver.cancel()
    env.native.bookmark(saved=saved)
    env.native.speak_release.set()
    env.player.idle_release.set()
    env.driver._task_queue.join()
    assert env.indexes == []
    assert env.dones == []


def test_retained_legacy_bookmark_handles_do_not_retain_driver(env):
    env.driver.speak(("legacy",))
    env.native.wait_calls(1)
    saved = env.native.synths[env.native.calls[0][0]].bookmark
    env.native.speak_release.set()
    env.player.idle_release.set()
    assert env.done_event.wait(1)
    env.driver.terminate()
    driver_ref = weakref.ref(env.driver)
    env.dones.clear()
    env.driver = None
    gc.collect()
    assert driver_ref() is None
    env.native.bookmark(saved=saved)


def test_failure_sink_can_terminate_after_audio_callback_fault(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    env.player.error = "feed"
    events = []
    failure_entered = Event()

    def fail_and_terminate(event):
        events.append(event)
        failure_entered.set()
        env.driver.terminate()

    env.driver.speak_segment(("hello",), env.scheduler.CancellationToken(),
        context=env.rt.models.PlaybackContext(object(), 17), on_event=fail_and_terminate)
    env.native.wait_calls(1)
    callback = in_thread(env.native.audio)
    finish(callback)
    assert not failure_entered.wait(0.05)
    env.native.speak_release.set()
    assert failure_entered.wait(1)
    assert len(events) == 1


def test_inner_sdk_sources_and_dlls_match_user_baseline():
    from hashlib import sha256
    from neural_drain_harness import NEURAL
    expected = {
        "driver/__init__.py": "d866d5921434a475d240d97d88e31f81bae82cb6da5b54b06c44f9c705a48ef6",
        "driver/speechapi/__init__.py": "7a86eeadfffd0cea2c00cce49b39d43ce79de0aa3c605ff944a37ca3325b881b",
        "driver/speechapi/speechapi_cffi.py": "618a5d2d64574a4a0129a512b7bb73844d76d511d9b86a04243a1395fbd5d652",
        "driver/speechapi/Microsoft.CognitiveServices.Speech.core.dll": "3e3c8caaf342d99fcc144d16d72cdcccc4f979a1ba309a12b20c5457a9e57656",
        "driver/speechapi/Microsoft.CognitiveServices.Speech.extension.audio.sys.dll": "3d15877e59495ffce1f818b962e7f6d9f90365cc7d328c939dac2de646ee335e",
        "driver/speechapi/Microsoft.CognitiveServices.Speech.extension.codec.dll": "1210e818bbc1c35e739b48b9896ccd9d7c8a1d14c141f64056e94b3d6ed50af4",
        "driver/speechapi/Microsoft.CognitiveServices.Speech.extension.embedded.tts.dll": "89521bda1f32867625cea05887ceaf071c9e7dbe85cac6099cc73606c33bb56f",
        "driver/speechapi/Microsoft.CognitiveServices.Speech.extension.kws.dll": "b69f6934483aa6c3af9d5334d23e1e5f4274465c40e8dc9f819f0885462c1d57",
        "driver/speechapi/Microsoft.CognitiveServices.Speech.extension.kws.ort.dll": "708e9de8dacd105fa40fd6985d7003c273871da7e9a149e59cb4f1597b81334b",
        "driver/speechapi/Microsoft.CognitiveServices.Speech.extension.onnxruntime.dll": "3f1e42f4fe9283267145ebd489f3600e510b9478c2bb0cbddc2e586b57a8a081",
        "driver/speechapi/msvcp140_codecvt_ids.dll": "ae8d922b00cdd93e3ebecc37beb46c800f383ebdeb9f9e5b84e04a72428b6fb3",
    }
    for relative, digest in expected.items():
        assert sha256((NEURAL / relative).read_bytes()).hexdigest() == digest, relative


def test_native_speak_exit_and_zero_callbacks_still_wait_for_stop(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    env.native.stop_release.clear()
    speak(env)
    env.native.wait_calls(1)
    env.driver.cancel()
    _, _, _, done = speak(env, segment=18)
    env.native.speak_release.set()
    assert env.native.stop_wait_entered.wait(1)
    assert len(env.native.calls) == 1
    env.native.stop_release.set()
    assert done.wait(2)
    assert len(env.native.calls) == 2


def test_bookmark_lease_blocks_next_native_call_until_handler_exits(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    entered, release = Event(), Event()

    def index_handler(**kwargs):
        entered.set()
        assert release.wait(2)

    monkeypatch.setattr(env.outer.synthIndexReached, "notify", index_handler)
    index = env.commands.IndexCommand()
    index.index = 1
    speak(env, commands=(index, "hello"))
    env.native.wait_calls(1)
    callback = in_thread(env.native.bookmark)
    assert entered.wait(1)
    env.driver.cancel()
    _, _, _, done = speak(env, segment=18)
    env.native.speak_release.set()
    assert env.native.stop_wait_entered.wait(1)
    assert len(env.native.calls) == 1
    release.set()
    finish(callback)
    assert done.wait(2)
    assert len(env.native.calls) == 2


def test_legacy_queued_work_prevents_switch_to_correlated_mode(env):
    env.driver.speak(("legacy",))
    _, _, events, done = speak(env)
    assert done.wait(1)
    assert events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert "legacy" in str(events[0].error).lower()


def test_cancel_discards_sonic_internal_tail_before_next_work(env, monkeypatch):
    from neural_drain_harness import Sonic
    prove_fake_quiescence(env, monkeypatch)
    old, new = Sonic(), Sonic()
    old.flush_tail = b"OLDTAIL"
    new.tail = b"NEWPCM"
    new.flush_tail = b"NEWTAIL"
    streams = iter((old, new))
    monkeypatch.setattr(env.driver._audioCallback, "_createSonicStream", lambda: next(streams))
    env.driver.rateBoost = True
    speak(env)
    env.native.wait_calls(1)
    env.native.audio()
    env.driver.cancel()
    _, _, _, done = speak(env, segment=18)
    env.native.speak_release.set()
    env.native.wait_calls(2)
    # The second speak can return immediately; its flush must use fresh Sonic.
    assert done.wait(2)
    assert env.player.fed == [b"NEWTAIL"]


def test_legacy_cancel_during_callback_retirement_waits_for_player_and_native_stop(env, monkeypatch):
    retirement_entered = Event()
    real_wait = env.driver._segmentCondition.wait_for

    def observed_wait(predicate, timeout=None):
        if current_thread() is env.driver._task_thread and env.driver._legacyCallbacks:
            retirement_entered.set()
        return real_wait(predicate, timeout)

    monkeypatch.setattr(env.driver._segmentCondition, "wait_for", observed_wait)
    env.driver.speak(("old legacy",))
    env.native.wait_calls(1)
    env.player.feed_release.clear()
    callback = in_thread(env.native.audio)
    assert env.player.feed_entered.wait(1)
    env.native.speak_release.set()
    assert retirement_entered.wait(1)
    env.player.stop_release.clear()
    env.native.stop_release.clear()
    cancelling = in_thread(env.driver.cancel)
    assert env.player.stop_entered.wait(1)
    env.driver.speak(("new legacy",))
    env.player.feed_release.set()
    with env.native.condition:
        assert not env.native.condition.wait_for(lambda: len(env.native.calls) >= 2, 0.05)
    env.player.stop_release.set()
    finish(cancelling)
    finish(callback)
    assert env.native.stop_wait_entered.wait(1)
    with env.native.condition:
        assert not env.native.condition.wait_for(lambda: len(env.native.calls) >= 2, 0.05)
    env.native.stop_release.set()
    env.native.wait_calls(2)
    assert env.native.released == [operation[0] for operation in env.native.operations]


def test_legacy_successor_queued_during_cancel_receives_audio(env):
    env.driver.speak(("old legacy",))
    env.native.wait_calls(1)
    env.player.stop_release.clear()
    env.native.stop_release.clear()
    cancelling = in_thread(env.driver.cancel)
    assert env.player.stop_entered.wait(1)
    try:
        env.driver.speak(("successor legacy",))
        callback = in_thread(lambda: env.native.audio(b"cancelled PCM"))
        assert env.player.fed == []
        env.native.speak_release.set()
    finally:
        env.player.stop_release.set()
        finish(cancelling)
        finish(callback)
    assert env.native.stop_wait_entered.wait(1)
    env.native.speak_release.clear()
    env.native.stop_release.set()
    env.native.wait_calls(2)
    env.native.audio(b"successor PCM")
    assert env.player.fed == [b"successor PCM"]


@pytest.mark.parametrize("failure", ["stop", "close"])
def test_termination_player_errors_finish_cleanup_and_repeated_calls(monkeypatch, tmp_path, failure):
    # Own cleanup here so the pre-fix deadlock can fail without hanging teardown.
    env = load_neural(monkeypatch, tmp_path)
    env.player.error = failure
    env.player.stop_release.clear()
    first = in_thread(env.driver.terminate)
    assert env.player.stop_entered.wait(1)
    repeated = in_thread(env.driver.terminate)
    try:
        assert not repeated.done.wait(0.05)
        env.player.stop_release.set()
        finish(first)
        finish(repeated)
        assert env.driver._terminationDone.is_set()
        assert not env.driver._task_thread.is_alive()
        assert isinstance(env.driver._terminationError, OSError)
        assert str(env.driver._terminationError) == f"audio {failure} failed"
        assert env.driver._task_thread._driver is None
        assert env.driver._synthCache == []
        assert env.driver._audioCallback._driver is None
        assert any("termination" in str(message).lower() for message in env.logs)
        env.driver.terminate()
    finally:
        env.player.error = None
        env.player.stop_release.set()
        if not env.driver._terminationDone.is_set():
            env.driver._task_queue.put(None)
            env.driver._terminationDone.set()
        env.driver._task_thread.join(1)
        first.thread.join(1)
        repeated.thread.join(1)


def test_cancel_stop_registration_error_releases_cancellation_barrier(env, monkeypatch):
    env.driver.speak(("legacy",))
    env.native.wait_calls(1)

    def failed_request(native):
        raise OSError("native stop registration failed")

    real_request = env.driver._request_stop
    monkeypatch.setattr(env.driver, "_request_stop", failed_request)
    try:
        with pytest.raises(OSError, match="native stop registration failed"):
            env.driver.cancel()
        assert env.driver._segmentStops == 0
    finally:
        monkeypatch.setattr(env.driver, "_request_stop", real_request)
        env.native.speak_release.set()
    terminating = in_thread(env.driver.terminate)
    finish(terminating)
    assert not env.driver._task_thread.is_alive()


def test_concurrent_cancel_preserves_termination_queue_shutdown(monkeypatch, tmp_path):
    env = load_neural(monkeypatch, tmp_path)
    env.driver.speak(("legacy",))
    env.native.wait_calls(1)
    sentinel_queued = Event()
    real_put = env.driver._task_queue.put

    def observed_put(task, *args, **kwargs):
        real_put(task, *args, **kwargs)
        if task is None:
            sentinel_queued.set()

    monkeypatch.setattr(env.driver._task_queue, "put", observed_put)
    terminating = in_thread(env.driver.terminate)
    try:
        assert sentinel_queued.wait(1)
        env.driver.cancel()
        env.native.speak_release.set()
        finish(terminating)
        assert env.driver._terminationDone.is_set()
        assert not env.driver._task_thread.is_alive()
    finally:
        env.native.speak_release.set()
        env.native.stop_release.set()
        env.player.idle_release.set()
        if not env.driver._terminationDone.is_set():
            real_put(None)
        terminating.thread.join(1)


def test_failed_stop_thread_start_does_not_leave_native_retirement_pending(env, monkeypatch):
    env.driver.speak(("legacy",))
    env.native.wait_calls(1)
    real_start = env.outer.Thread.start

    def failed_stop_start(thread):
        if thread.name == "WorldVoice Neural stop":
            raise OSError("native stop thread failed")
        real_start(thread)

    monkeypatch.setattr(env.outer.Thread, "start", failed_stop_start)
    try:
        with pytest.raises(OSError, match="native stop thread failed"):
            env.driver.cancel()
        operation = env.driver._legacyNative.stop
        assert operation.done.is_set()
        assert str(operation.error) == "native stop thread failed"
        assert env.driver._segmentStops == 0
        env.native.speak_release.set()
        terminating = in_thread(env.driver.terminate)
        finish(terminating)
        assert not env.driver._task_thread.is_alive()
    finally:
        monkeypatch.setattr(env.outer.Thread, "start", real_start)
        # Rescue the deliberately failed pre-fix operation for fixture cleanup.
        native = env.driver._legacyNative
        if native is not None and native.stop is not None:
            native.stop.done.set()
        env.native.speak_release.set()


def _exercise_legacy_bookmark_terminate_reentrancy(tmp_path, contextual):
    monkeypatch = pytest.MonkeyPatch()
    env = load_neural(monkeypatch, tmp_path)
    callback_entered, events = Event(), []
    context = env.rt.models.PlaybackContext(object(), 19)
    token = env.scheduler.CancellationToken()
    index = env.commands.IndexCommand()
    index.index = 1

    def terminate_from_index(*args, **kwargs):
        events.append(args[0] if args else kwargs)
        callback_entered.set()
        env.driver.terminate()
        env.driver.terminate()

    if contextual:
        env.driver.speak_legacy_segment((index, "legacy"), token,
            context=context, on_event=terminate_from_index)
    else:
        env.outer.synthIndexReached.notify = terminate_from_index
        env.driver.speak((index, "legacy"))
    env.native.wait_calls(1)
    callback = in_thread(env.native.bookmark)
    try:
        assert callback_entered.wait(1), "legacy bookmark did not publish its contextual index"
        assert callback.done.wait(0.5), "terminate from legacy bookmark waited on its own native call"
        if contextual:
            assert events and events[0].kind is env.rt.models.EventKind.INDEX
        else:
            assert events and events[0]["index"] == 1
    finally:
        env.native.speak_release.set()
        env.player.idle_release.set()
        env.player.stop_release.set()
        callback.done.wait(2)
        env.driver.terminate()
        monkeypatch.undo()


@pytest.mark.parametrize("contextual", [False, True])
def test_legacy_bookmark_can_terminate_without_waiting_for_native_speak(tmp_path, contextual):
    script = (
        "from pathlib import Path\n"
        "from test_neural_segment_drain import _exercise_legacy_bookmark_terminate_reentrancy\n"
        f"_exercise_legacy_bookmark_terminate_reentrancy(Path({str(tmp_path)!r}), {contextual!r})\n"
    )
    result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).parent,
                            text=True, capture_output=True, timeout=6)
    assert result.returncode == 0, result.stderr
