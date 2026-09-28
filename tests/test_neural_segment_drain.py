from threading import Event
import gc
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
def test_all_unproven_sdk_profiles_are_unsupported(env, version, mode):
    support = env.driver.get_segment_drain_support(nvda_version=version, audio_mode=mode)
    assert support.supported is False
    assert "callback" in support.reason.lower()
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


def test_unproven_quiescence_never_reopens_gate(env):
    _, _, events, done = speak(env)
    env.native.wait_calls(1)
    complete(env, done)
    assert events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert "callback" in str(events[0].error).lower()
    speak(env, segment=18)
    assert len(env.native.calls) == 1
    assert env.native.audio() == 2
    assert env.player.fed == []


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


def test_failure_sink_can_terminate_inside_audio_callback(env, monkeypatch):
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
    assert failure_entered.wait(1)
    env.native.speak_release.set()
    finish(callback)
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
