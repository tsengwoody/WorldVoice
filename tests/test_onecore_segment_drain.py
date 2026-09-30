import gc
from threading import Event
import weakref

import pytest

from onecore_drain_harness import VERSION, in_thread, load_onecore


@pytest.fixture
def env(monkeypatch):
    result = load_onecore(monkeypatch)
    yield result
    result.player.feed_release.set()
    result.player.sync_release.set()
    if result.driver is not None:
        result.driver.terminate()


def speak(env, segment=17, commands=("hello",), events=None):
    events = [] if events is None else events
    token = env.scheduler.CancellationToken()
    context = env.rt.models.PlaybackContext(object(), segment)
    env.driver.speak_segment(commands, token, context=context, on_event=events.append)
    return token, context, events


def finish(call):
    assert call.done.wait(2), "Callback did not exit"
    call.thread.join(1)
    assert call.errors == []


def test_onecore_waits_for_tail_sync_before_drain(env):
    token, context, events = speak(env)
    env.native.wait_calls(1)
    call = in_thread(env.native.respond)
    assert env.player.sync_entered.wait(1)
    assert env.indexes == [1]
    assert sum(map(len, env.player.fed)) == 16
    assert events == []
    env.player.sync_release.set()
    finish(call)
    assert len(events) == 1
    assert events[0].kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert events[0].source_id is context.source_id
    assert events[0].segment_id == 17
    assert env.outer.Voice.synth_driver_class is type(env.driver)


def test_settings_tuples_do_not_take_native_job_identity(env):
    env.driver._set_rate(60)
    _, first, events_a = speak(env)
    _, second, events_b = speak(env, segment=18)
    env.native.wait_calls(1)
    assert env.native.settings == [("Rate", 1.1)]
    assert len(env.native.calls) == 1
    env.player.sync_release.set()
    env.native.respond()
    env.native.wait_calls(2)
    env.native.respond()
    assert events_a[0].source_id is first.source_id
    assert events_b[0].source_id is second.source_id
    assert events_b[0].segment_id == 18


def test_cancel_removes_queued_text_but_keeps_settings_identity(env):
    speak(env)
    env.native.wait_calls(1)
    _, _, discarded = speak(env, segment=18)
    env.driver._set_volume(75)
    env.driver.cancel()
    _, expected, events = speak(env, segment=19)
    env.native.respond()
    env.native.wait_calls(2)
    env.native.respond()
    assert discarded == []
    assert env.native.settings == [("Volume", 0.75)]
    assert events[0].source_id is expected.source_id
    assert events[0].segment_id == 19


def test_cancelled_input_token_never_submits_native_work(env):
    token = env.scheduler.CancellationToken()
    token.cancel()
    events = []
    env.driver.speak_segment(("old",), token,
        context=env.rt.models.PlaybackContext(object(), 17), on_event=events.append)
    assert env.native.calls == [] and events == []


@pytest.mark.parametrize("failure", [False, True])
def test_late_cancelled_callback_is_consumed_before_next_submission(env, failure):
    _, _, old_events = speak(env)
    env.native.wait_calls(1)
    env.driver.cancel()
    _, new, new_events = speak(env, segment=18)
    assert len(env.native.calls) == 1
    env.native.respond(failure=failure)
    env.native.wait_calls(2)
    assert old_events == [] and new_events == []
    env.native.respond()
    assert len(new_events) == 1
    assert new_events[0].source_id is new.source_id
    assert new_events[0].segment_id == 18


@pytest.mark.parametrize("response", [
    {"failure": True}, {"malformed": True}, {"markers": "bad"},
    {"markers": "1:999999999"}, {"markers": "1:-1"},
    {"markers": "2:40000|1:20000"},
])
def test_native_and_parse_errors_fail_original_work_without_drain(env, response):
    _, context, events = speak(env)
    env.native.wait_calls(1)
    env.player.sync_release.set()
    env.native.respond(**response)
    assert len(events) == 1
    assert events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert events[0].source_id is context.source_id
    assert isinstance(events[0].error, Exception)
    assert env.dones == []


@pytest.mark.parametrize("error", ["feed", "sync"])
def test_observable_player_errors_fail_without_drain(env, error):
    _, _, events = speak(env)
    env.native.wait_calls(1)
    env.player.error = error
    env.player.sync_release.set()
    env.native.respond()
    assert [event.kind for event in events] == [env.rt.models.EventKind.SEGMENT_FAILED]


@pytest.mark.parametrize("commands,frames,markers", [
    ((), 0, ""), (("index-only",), 0, "1:0"), (("break-only",), 8, ""),
])
def test_empty_index_and_break_segments_drain_at_known_end(env, commands, frames, markers):
    if commands == ("index-only",):
        index = env.commands.IndexCommand()
        index.index = 1
        commands = (index,)
    elif commands == ("break-only",):
        pause = env.commands.BreakCommand()
        pause.time = 8
        commands = (pause,)
    _, _, events = speak(env, commands=commands)
    env.native.wait_calls(1)
    env.player.sync_release.set()
    env.native.respond(frames=frames, markers=markers)
    assert [event.kind for event in events] == [env.rt.models.EventKind.SEGMENT_DRAINED]


@pytest.mark.parametrize("frames", [0, 8])
def test_pause_holds_completion_until_resume(env, frames):
    _, _, events = speak(env)
    env.native.wait_calls(1)
    env.driver.pause(True)
    env.player.sync_release.set()
    call = in_thread(lambda: env.native.respond(frames=frames, markers=""))
    assert env.player.sync_entered.wait(1)
    assert events == []
    assert not call.done.wait(0.05)
    env.driver.pause(False)
    finish(call)
    assert [event.kind for event in events] == [env.rt.models.EventKind.SEGMENT_DRAINED]


def test_pause_before_first_wav_also_pauses_new_player(env):
    env.driver._player = None
    speak(env)
    env.native.wait_calls(1)
    env.driver.pause(True)
    call = in_thread(lambda: env.native.respond(markers=""))
    assert env.player.sync_entered.wait(1)
    paused = env.player.pause_switch
    env.driver.pause(False)
    env.player.sync_release.set()
    finish(call)
    assert paused, "A player initialized after pause played without being paused"


def test_cancel_stop_returning_from_sync_never_reports_drain(env):
    _, _, events = speak(env)
    env.native.wait_calls(1)
    call = in_thread(env.native.respond)
    assert env.player.sync_entered.wait(1)
    env.driver.cancel()
    finish(call)
    assert events == []
    assert env.player.stops >= 1


def test_feed_admission_cancel_finishes_old_feed_before_new_native_call(env):
    _, _, old_events = speak(env)
    env.native.wait_calls(1)
    env.player.feed_release.clear()
    call = in_thread(env.native.respond)
    assert env.player.feed_entered.wait(1)
    env.driver.cancel()
    speak(env, segment=18)
    assert len(env.native.calls) == 1
    env.player.feed_release.set()
    finish(call)
    env.native.wait_calls(2)
    assert env.player.stops >= 2
    assert old_events == []


def test_cancel_stop_must_exit_before_a_retired_callback_allows_new_work(env):
    speak(env)
    env.native.wait_calls(1)
    stopped = Event()
    release_stop = Event()
    original_stop = env.player.stop

    def blocked_stop():
        stopped.set()
        assert release_stop.wait(1)
        original_stop()

    env.player.stop = blocked_stop
    cancel = in_thread(env.driver.cancel)
    assert stopped.wait(1)
    speak(env, segment=18)
    env.native.respond(failure=True)
    with env.native.condition:
        advanced = env.native.condition.wait_for(lambda: len(env.native.calls) >= 2, 0.05)
    release_stop.set()
    finish(cancel)
    assert not advanced, "New native work started before the old cancel stop exited"
    env.native.wait_calls(2)


def test_terminate_unblocks_sync_and_retains_late_callback(env):
    _, _, events = speak(env)
    env.native.wait_calls(1)
    callback = env.native.callback
    call = in_thread(env.native.respond)
    assert env.player.sync_entered.wait(1)
    env.driver.terminate()
    finish(call)
    # A timeout in the actual helper's terminate may leave the pointer callable.
    callback(None, 0, None)
    assert events == []
    assert env.native.terminated


def test_native_submission_exception_fails_and_allows_following_work(env):
    env.native.submit_error = OSError("submit failed")
    failed = Event()
    events = []
    token = env.scheduler.CancellationToken()
    context = env.rt.models.PlaybackContext(object(), 17)
    env.driver.speak_segment(("hello",), token, context=context,
        on_event=lambda event: (events.append(event), failed.set()))
    assert failed.wait(1)
    assert [event.kind for event in events] == [env.rt.models.EventKind.SEGMENT_FAILED]
    env.native.submit_error = None
    speak(env, segment=18)
    env.native.wait_calls(1)


def test_capability_allows_live_profile_without_provenance_certification(env, monkeypatch):
    support = env.driver.get_segment_drain_support(nvda_version=VERSION, audio_mode="wasapi")
    assert support.supported
    assert "unverified" in support.reason.lower()
    for version, audio in (("2026.3", "wasapi"), (VERSION, "waveout"), ("2024.1", "wasapi")):
        support = env.driver.get_segment_drain_support(nvda_version=version, audio_mode=audio)
        assert support.supported and support.reason
    monkeypatch.setattr(env.base, "__file__", "/unverified/oneCore.py")
    support = env.driver.get_segment_drain_support(nvda_version=VERSION, audio_mode="wasapi")
    assert support.supported and "unverified" in support.reason.lower()


def test_capability_rejects_uninitialized_native_and_foreign_helper(env):
    env.native._name = "/unverified/nvdaHelperLocalWin10.dll"
    support = env.driver.get_segment_drain_support(nvda_version=VERSION, audio_mode="wasapi")
    assert support.supported and "unverified" in support.reason.lower()


@pytest.mark.parametrize("missing", ["token", "callback", "native speak"])
def test_capability_rejects_partial_initialization(env, missing):
    if missing == "token":
        env.driver._ocSpeechToken.value = None
    elif missing == "callback":
        env.driver._callbackInst = None
    else:
        env.native.ocSpeech_speak = None
    support = env.driver.get_segment_drain_support(nvda_version=VERSION, audio_mode="wasapi")
    assert not support.supported and support.reason


def test_pause_resume_reaches_real_player_before_success_event(env):
    _, _, events = speak(env)
    env.native.wait_calls(1)
    env.driver.pause(True)
    env.player.sync_release.set()
    call = in_thread(lambda: env.native.respond(frames=0, markers=""))
    assert env.player.sync_entered.wait(1)
    resumed = Event()
    release = Event()
    original_pause = env.player.pause

    def blocking_resume(switch):
        if not switch:
            resumed.set()
            assert release.wait(1)
        original_pause(switch)

    env.player.pause = blocking_resume
    resume = in_thread(lambda: env.driver.pause(False))
    assert resumed.wait(1)
    assert not call.done.wait(0.05)
    assert events == []
    release.set()
    finish(resume)
    finish(call)
    assert [event.kind for event in events] == [env.rt.models.EventKind.SEGMENT_DRAINED]


def start_controlled_playback(env, mode):
    if mode == "legacy_after_segment":
        speak(env)
        env.native.wait_calls(1)
        env.player.sync_release.set()
        env.native.respond(markers="")
        env.player.sync_release.clear()
        env.player.sync_entered.clear()
    if mode == "segment":
        _, context, events = speak(env)
    else:
        context, events = None, []
        env.driver.speak(("legacy",))
    env.native.wait_calls(2 if mode == "legacy_after_segment" else 1)
    return context, events


@pytest.mark.parametrize("mode", ["segment", "legacy", "legacy_after_segment"])
@pytest.mark.parametrize("terminate", [False, True])
def test_late_pause_retires_before_cancel_handoff_or_native_close(env, mode, terminate):
    _, old_events = start_controlled_playback(env, mode)
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

    env.player.pause, env.player.stop = blocked_pause, observed_stop
    pause = in_thread(lambda: env.driver.pause(True))
    assert pause_entered.wait(1)
    closing = in_thread(env.driver.terminate if terminate else env.driver.cancel)
    try:
        assert stopped.wait(1), "Cancel must stop playback before waiting for pause"
        assert not closing.done.wait(0.05), "Close/cancel retired while pause could still affect the player"
        if terminate:
            assert not env.native.terminated
        else:
            _, _, successor_events = speak(env, segment=18)
            if mode != "legacy":
                env.native.respond(failure=True)
            assert len(env.native.calls) == (2 if mode == "legacy_after_segment" else 1)
    finally:
        release_pause.set()
        finish(pause)
        finish(closing)
    assert old_events == []
    if not terminate:
        if mode == "legacy":
            env.native.respond(failure=True)
        env.native.wait_calls(3 if mode == "legacy_after_segment" else 2)
        assert not env.player.pause_switch, "A retired pause affected successor playback"
        env.native.respond(markers="")
        assert [event.kind for event in successor_events] == [env.rt.models.EventKind.SEGMENT_DRAINED]
    else:
        assert env.native.terminated


@pytest.mark.parametrize("mode", ["segment", "legacy", "legacy_after_segment"])
@pytest.mark.parametrize("switch", [False, True])
def test_pause_or_resume_error_resolves_work_and_blocks_new_admission(env, mode, switch):
    context, events = start_controlled_playback(env, mode)
    if not switch:
        env.driver.pause(True)
    call = in_thread(lambda: env.native.respond(markers=""))
    assert env.player.sync_entered.wait(1)
    error = OSError("player control failed")

    def failed_control(switch):
        raise error

    env.player.pause = failed_control
    with pytest.raises(OSError) as raised:
        env.driver.pause(switch)
    assert raised.value is error
    env.player.sync_release.set()
    finish(call)
    if mode == "segment":
        assert len(events) == 1
        assert events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
        assert events[0].error is error
        assert events[0].source_id is context.source_id
        assert events[0].segment_id == context.segment_id
    else:
        assert env.dones == [env.driver], "Legacy failure did not release its wait exactly once"
    calls = len(env.native.calls)
    _, _, rejected = speak(env, segment=18)
    assert len(rejected) == 1
    assert rejected[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert rejected[0].error is error
    with pytest.raises(OSError) as rejected_legacy:
        env.driver.speak(("uncertain player",))
    assert rejected_legacy.value is error
    assert len(env.native.calls) == calls


def test_pause_error_on_new_player_latches_before_following_segment(env):
    env.driver._player = None
    _, _, events = speak(env)
    env.native.wait_calls(1)
    env.driver.pause(True)
    error = OSError("new player pause failed")

    def failed_pause(switch):
        raise error

    env.player.pause = failed_pause
    env.native.respond(markers="")
    assert len(events) == 1 and events[0].error is error
    _, _, rejected = speak(env, segment=18)
    assert len(rejected) == 1 and rejected[0].error is error
    assert len(env.native.calls) == 1


def test_control_error_fails_queued_contexts_and_allows_reentrant_cancel(env):
    events, failed = [], Event()
    token = env.scheduler.CancellationToken()
    context = env.rt.models.PlaybackContext(object(), 17)

    def failure_sink(event):
        events.append(event)
        env.driver.cancel()
        failed.set()

    env.driver.speak_segment(("active",), token, context=context, on_event=failure_sink)
    env.native.wait_calls(1)
    _, queued_context, queued_events = speak(env, segment=18)
    error = OSError("pause failed with queued work")

    def failed_pause(switch):
        raise error

    env.player.pause = failed_pause
    pause = in_thread(lambda: env.driver.pause(True))
    assert pause.done.wait(1), "Failure sink deadlocked while cancelling"
    pause.thread.join(1)
    assert pause.errors == [error]
    assert failed.is_set()
    assert len(events) == 1 and events[0].error is error
    assert len(queued_events) == 1 and queued_events[0].error is error
    assert queued_events[0].source_id is queued_context.source_id
    env.native.respond(failure=True)
    assert len(env.native.calls) == 1


def test_legacy_native_submission_error_releases_speaking_wait(env):
    error = OSError("legacy submission failed")
    done = Event()
    original_done = env.outer.synthDoneSpeaking.notify

    def completed(**kwargs):
        original_done(**kwargs)
        done.set()

    env.outer.synthDoneSpeaking.notify = completed
    env.native.submit_error = error
    env.driver.speak(("legacy",))
    assert done.wait(1), "Legacy submission failed without releasing its speaking wait"
    assert env.dones == [env.driver]


def test_legacy_speak_after_correlated_work_preserves_done_notification(env):
    speak(env)
    env.native.wait_calls(1)
    env.player.sync_release.set()
    env.native.respond()
    env.driver.speak(("legacy",))
    env.native.wait_calls(2)
    env.native.respond()
    assert env.dones == [env.driver]


def test_cancelled_legacy_feed_retires_only_after_its_final_stop(env):
    speak(env)
    env.native.wait_calls(1)
    env.player.sync_release.set()
    env.native.respond()
    env.driver.speak(("legacy",))
    env.native.wait_calls(2)
    env.player.feed_entered.clear()
    env.player.feed_release.clear()
    call = in_thread(lambda: env.native.respond(markers=""))
    assert env.player.feed_entered.wait(1)
    env.driver.cancel()
    speak(env, segment=18)
    assert len(env.native.calls) == 2
    final_stop = Event()
    release_stop = Event()
    original_stop = env.player.stop

    def blocked_final_stop():
        final_stop.set()
        assert release_stop.wait(1)
        original_stop()

    env.player.stop = blocked_final_stop
    env.player.feed_release.set()
    stopped = final_stop.wait(0.5)
    with env.native.condition:
        advanced = env.native.condition.wait_for(lambda: len(env.native.calls) >= 3, 0.05)
    release_stop.set()
    finish(call)
    assert stopped, "The legacy feed queued audio after cancel without a final stop"
    assert not advanced, "New native work started before the cancelled legacy feed's final stop"
    env.native.wait_calls(3)
    assert env.dones == []


def test_cancelled_legacy_sync_does_not_emit_done(env):
    speak(env)
    env.native.wait_calls(1)
    env.player.sync_release.set()
    env.native.respond()
    env.driver.speak(("legacy",))
    env.native.wait_calls(2)
    env.player.sync_entered.clear()
    env.player.sync_release.clear()
    call = in_thread(lambda: env.native.respond(markers=""))
    assert env.player.sync_entered.wait(1)
    env.driver.cancel()
    finish(call)
    assert env.dones == []


@pytest.mark.parametrize("correlated", [False, True])
def test_terminated_driver_is_collected_while_late_native_callback_stays_callable(env, correlated):
    if correlated:
        speak(env)
        env.native.wait_calls(1)
        env.player.sync_release.set()
        env.native.respond()
    callback = env.native.callback
    driver_ref = weakref.ref(env.driver)
    touched = []
    env.driver._callback = lambda *args: touched.append("late driver access")
    env.driver.terminate()
    worker = env.driver._segmentWorker
    if worker is not None:
        worker.join(1)
        assert not worker.is_alive()
    callback(None, 0, None)
    assert touched == []
    env.dones.clear()
    env.driver = None
    gc.collect()
    assert driver_ref() is None, "Retained native callback kept the terminated driver graph alive"
    callback(None, 0, None)
    assert touched == []


def test_legacy_speak_still_uses_parent_interface(env):
    env.driver.speak(("legacy",))
    env.native.wait_calls(1)
    env.player.sync_release.set()
    env.native.respond()
    assert env.indexes == [1]
    assert env.dones == [env.driver]
