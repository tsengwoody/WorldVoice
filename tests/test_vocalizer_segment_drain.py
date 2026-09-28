import ctypes
from io import BytesIO
from threading import Event, Thread

import pytest

from worldvoice_cancel_wrapper_harness import load_real_driver_with_native_stubs
from test_worldvoice_cancel_wrappers import Token, native_message


@pytest.fixture(params=["VE", "Cerence"])
def env(request, monkeypatch):
    result = load_real_driver_with_native_stubs(monkeypatch, request.param)
    result.core = result.new_core()
    result.core._veCallbackHandler._ensureSonicStream = lambda: False
    result.events, result.indexes, result.dones = [], [], []
    monkeypatch.setattr(result.original_driver.synthIndexReached, "notify",
        lambda **kwargs: result.indexes.append(kwargs["index"]))
    monkeypatch.setattr(result.original_driver.synthDoneSpeaking, "notify",
        lambda **kwargs: result.dones.append(kwargs))
    return result


def prove_fake_quiescence(env, monkeypatch):
    # A test-only contract promises this native call will not start callbacks
    # after return. It never changes the production capability result.
    monkeypatch.setattr(env.core, "_confirm_native_quiescence", lambda native: None)


def run_thread(action):
    errors, done = [], Event()
    def run():
        try:
            action()
        except Exception as error:
            errors.append(error)
        finally:
            done.set()
    thread = Thread(target=run, daemon=True)
    thread.start()
    return thread, done, errors


def finish(call):
    assert call[1].wait(2)
    assert call[2] == []


def speak(env, commands=("hello",), *, token=None, segment=17):
    token = token or Token()
    context = env.rt.models.PlaybackContext(object(), segment)
    return token, context, run_thread(lambda: env.core.speak_segment(commands, token,
        context=context, on_event=env.events.append))


_NO_BOOKMARK = object()


def emit(env, instance, *, payload=b"pcm", index=_NO_BOOKMARK, end=True):
    callback, types = env.core._veCallbackHandler, env.types
    data = types.VE_OUTDATA()
    results = [callback(instance, None, native_message(types, types.VE_MSG_OUTBUFREQ, data))]
    if results[0] != types.NUAN_OK:
        return results
    ctypes.memmove(data.pOutPcmBuf, payload, len(payload))
    data.cntPcmBufLen = len(payload)
    data.cntMrkListLen = 0 if index is _NO_BOOKMARK else 1
    if index is not _NO_BOOKMARK:
        data.pMrkList[0].eMrkType = types.VE_MRK_BOOKMARK
        if env.engine == "VE":
            data.pMrkList[0].ulMrkId = index
        else:
            data.pMrkList[0].szValue = str(index).encode("ascii") if isinstance(index, int) else index
    results.append(callback(instance, None, native_message(types, types.VE_MSG_OUTBUFDONE, data)))
    if end:
        results.append(callback(instance, None, native_message(types, types.VE_MSG_ENDPROCESS, data)))
    return results


def test_native_constructor_owns_contextual_callback_before_first_open(env):
    instance = env.core.voiceInstance
    assert isinstance(env.core._veCallbackHandler, getattr(env.module, "_Contextual" + env.engine + "Callback"))
    assert env.opened[0][1] == instance
    assert env.opened[0][2] is env.core._veCallback
    env.core._veCallbackHandler._feedBuf = BytesIO(b"keep")
    message = native_message(env.types, env.types.VE_MSG_ENDPROCESS, env.types.VE_OUTDATA())
    assert env.opened[0][2](instance, None, message) == env.types.NUAN_E_TTS_USERSTOP
    assert env.core._veCallbackHandler._feedBuf.getvalue() == b"keep"
    assert env.module.CancellableSynthDriver is env.module.SynthDriver
    assert env.module.Voice.synth_driver_class is env.module.SynthDriver


@pytest.mark.parametrize("version,mode", [("2026.3", "wasapi"), ("2025.3", "legacy")])
def test_unproven_native_profiles_are_unsupported(env, version, mode):
    support = env.core.get_segment_drain_support(nvda_version=version, audio_mode=mode)
    assert not support.supported
    assert "ProcessText2Speech" in support.reason
    assert "callback" in support.reason.lower()


def test_vocalizer_endprocess_is_not_segment_drain(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    entered, release = Event(), Event()
    def idle():
        entered.set()
        assert release.wait(2)
    env.core._real_player.idle = idle
    monkeypatch.setattr(env.native, "processText2Speech", lambda instance, text: emit(env, instance, index=23))
    _, context, call = speak(env)
    assert entered.wait(1)
    assert env.events == []
    assert env.core._real_player.fed == [b"pcm"]
    assert env.indexes == [23]
    release.set()
    finish(call)
    assert len(env.events) == 1
    assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert env.events[0].source_id is context.source_id
    assert env.events[0].segment_id == 17
    assert env.dones == []


def test_multichunk_langchange_has_one_work_and_final_drain(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    change = __import__("speech.commands", fromlist=["LangChangeCommand"]).LangChangeCommand()
    change.lang = "fr"
    monkeypatch.setattr(env.core, "getVoiceNameForLanguage", lambda language: "fr", raising=False)
    monkeypatch.setattr(env.module, "split_speech_text_pieces", lambda text: [text + "1", text + "2"])
    calls, works = [], []
    def native(instance, text):
        calls.append((instance.pHandleData, text))
        works.append(env.core._nativeWork.work)
        emit(env, instance, index=len(calls))
    monkeypatch.setattr(env.native, "processText2Speech", native)
    _, _, call = speak(env, ("hello", change, "bonjour"))
    finish(call)
    assert len(calls) == 4
    assert [item[0] for item in calls] == [1, 1, 2, 2]
    assert all(work is works[0] for work in works)
    assert env.indexes == [1, 2, 3, 4]
    assert len(env.opened) == 2
    assert all(opened[2] is env.core._veCallback for opened in env.opened)
    assert len(env.events) == 1
    assert env.core._real_player.idles == 1


@pytest.mark.parametrize("cancel_kind", ["token", "direct", "clear"])
def test_cancelled_idle_cannot_complete_segment(env, monkeypatch, cancel_kind):
    prove_fake_quiescence(env, monkeypatch)
    entered, release = Event(), Event()
    env.core._real_player.idle = lambda: (entered.set(), release.wait(2))
    env.core._real_player.stop = release.set
    monkeypatch.setattr(env.native, "processText2Speech", lambda instance, text: emit(env, instance))
    token, _, call = speak(env)
    assert entered.wait(1)
    if cancel_kind == "token":
        token.cancel()
    else:
        env.core.cancel()
        if cancel_kind == "clear":
            env.core._isSilence.clear()
    release.set()
    finish(call)
    assert env.events == []


@pytest.mark.parametrize("fault", ["feed", "idle", "write", "read", "flush", "marker", "native"])
def test_processing_errors_latch_failure_on_original_context(env, monkeypatch, fault):
    prove_fake_quiescence(env, monkeypatch)
    def fail(*args, **kwargs):
        raise OSError(f"{fault} failed")
    if fault in ("feed", "idle"):
        setattr(env.core._real_player, fault, fail)
    elif fault == "marker":
        monkeypatch.setattr(env.original_driver.synthIndexReached, "notify", fail)
    elif fault in ("write", "read", "flush"):
        class Sonic:
            def writeShort(self, *args):
                if fault == "write": fail()
            def readShort(self):
                if fault == "read": fail()
                return b"tail"
            def flush(self):
                if fault == "flush": fail()
        callback = env.core._veCallbackHandler
        def sonic():
            callback.sonicStream = Sonic()
            callback._sonicEnabled = True
            return True
        callback._ensureSonicStream = sonic
    results = []
    def native(instance, text):
        if fault == "native": fail()
        results.extend(emit(env, instance, index=9))
    monkeypatch.setattr(env.native, "processText2Speech", native)
    _, context, call = speak(env)
    finish(call)
    assert len(env.events) == 1
    assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert env.events[0].source_id is context.source_id
    assert str(env.events[0].error) == f"{fault} failed"
    assert env.dones == []
    if fault not in ("idle", "native"):
        assert env.types.NUAN_E_TTS_USERSTOP in results


def test_missing_contract_closes_old_call_and_never_reopens_for_successor(env, monkeypatch):
    calls = []
    monkeypatch.setattr(env.native, "processText2Speech", lambda instance, text: calls.append(text))
    _, _, first = speak(env)
    finish(first)
    assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
    _, _, second = speak(env, segment=18)
    finish(second)
    assert calls == ["hello"]
    env.core._veCallbackHandler._feedBuf = BytesIO(b"new")
    assert emit(env, env.core.voiceInstance) == [env.types.NUAN_E_TTS_USERSTOP]
    assert env.core._veCallbackHandler._feedBuf.getvalue() == b"new"


def test_cancelled_token_does_not_submit_native_or_notify(env, monkeypatch):
    token = Token()
    token.cancel()
    monkeypatch.setattr(env.native, "processText2Speech", lambda *args: pytest.fail("native entered"))
    _, _, call = speak(env, token=token)
    finish(call)
    assert env.events == []


def test_old_feed_final_stop_retires_before_next_native_call(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    feed_entered, feed_release, stop_entered, stop_release = Event(), Event(), Event(), Event()
    calls = []
    env.core._real_player.feed = lambda data: (feed_entered.set(), feed_release.wait(2))
    def stop():
        stop_entered.set()
        assert stop_release.wait(2)
    env.core._real_player.stop = stop
    callback_calls = []
    def native(instance, text):
        calls.append(text)
        if len(calls) == 1:
            callback_calls.append(run_thread(lambda: emit(env, instance)))
            assert feed_entered.wait(1)
    monkeypatch.setattr(env.native, "processText2Speech", native)
    token, _, first = speak(env)
    assert feed_entered.wait(1)
    token.cancel()
    _, _, second = speak(env, segment=18)
    feed_release.set()
    assert stop_entered.wait(1)
    assert calls == ["hello"]
    stop_release.set()
    finish(callback_calls[0])
    finish(first)
    finish(second)
    assert calls == ["hello", "hello"]
    assert [event.segment_id for event in env.events] == [18]


def test_cancel_stop_in_progress_blocks_next_native_call(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    entered, release = Event(), Event()
    env.core._real_player.stop = lambda: (entered.set(), release.wait(2))
    cancelling = run_thread(env.core.cancel)
    assert entered.wait(1)
    native_entered = Event()
    monkeypatch.setattr(env.native, "processText2Speech", lambda *args: native_entered.set())
    _, _, call = speak(env)
    assert not native_entered.wait(.05)
    release.set()
    finish(cancelling)
    finish(call)
    assert len(env.events) == 1


def test_foreign_instance_endprocess_does_not_touch_current_buffer(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    callback = env.core._veCallbackHandler
    def native(instance, text):
        callback._feedBuf = BytesIO(b"current")
        foreign = env.types.VE_HSAFE()
        foreign.pHandleData = 123
        result = callback(foreign, None, native_message(env.types, env.types.VE_MSG_ENDPROCESS, env.types.VE_OUTDATA()))
        assert result == env.types.NUAN_E_TTS_USERSTOP
        assert callback._feedBuf.getvalue() == b"current"
    monkeypatch.setattr(env.native, "processText2Speech", native)
    _, _, call = speak(env)
    finish(call)
    assert env.core._real_player.fed == []


def test_anonymous_done_never_completes_context(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    def native(instance, text):
        env.core._onIndexReached(None)
        assert env.events == []
    monkeypatch.setattr(env.native, "processText2Speech", native)
    _, _, call = speak(env)
    finish(call)
    assert len(env.events) == 1
    assert env.dones == []


def test_native_userstop_without_cancel_is_failure(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    monkeypatch.setattr(env.native, "processText2Speech", lambda *args: env.types.NUAN_E_TTS_USERSTOP)
    _, _, call = speak(env)
    finish(call)
    assert len(env.events) == 1
    assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert "USERSTOP" in str(env.events[0].error)


def test_direct_cancel_after_idle_return_still_invalidates_original_work(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    monkeypatch.setattr(env.native, "processText2Speech", lambda *args: None)
    returned, release = Event(), Event()
    run_speech = env.core._run_speech
    def after_idle(commands, work):
        result = run_speech(commands, work)
        returned.set()
        assert release.wait(2)
        return result
    monkeypatch.setattr(env.core, "_run_speech", after_idle)
    _, _, call = speak(env)
    assert returned.wait(1)
    env.core.cancel()
    release.set()
    finish(call)
    assert env.events == []


def test_cancel_discards_sonic_internal_tail_before_next_segment(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    class Sonic:
        def __init__(self, tail):
            self.tail = tail
            self.flushed = False
        def writeShort(self, *args): pass
        def readShort(self): return self.tail if self.flushed else b""
        def flush(self): self.flushed = True
    streams = [Sonic(b"OLDTAIL"), Sonic(b"NEWTAIL")]
    callback = env.core._veCallbackHandler
    def sonic():
        if callback.sonicStream is None:
            callback.sonicStream = streams.pop(0)
            callback._sonicEnabled = True
        return True
    callback._ensureSonicStream = sonic
    calls = []
    def native(instance, text):
        calls.append(text)
        emit(env, instance, end=len(calls) > 1)
        if len(calls) == 1:
            env.core.cancel()
    monkeypatch.setattr(env.native, "processText2Speech", native)
    _, _, old = speak(env)
    finish(old)
    _, _, new = speak(env, segment=18)
    finish(new)
    assert env.core._real_player.fed == [b"NEWTAIL"]
    assert [event.segment_id for event in env.events] == [18]


def test_real_sonic_initialization_failure_uses_native_pcm_fallback(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    callback = env.core._veCallbackHandler
    callback._ensureSonicStream = env.original_driver.VECallback._ensureSonicStream.__get__(callback)
    monkeypatch.setattr(env.native, "processText2Speech", lambda instance, text: emit(env, instance))
    _, _, call = speak(env)
    finish(call)
    assert callback._sonicInitTried
    assert not callback._sonicEnabled
    assert env.core._real_player.fed == [b"pcm"]
    assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_DRAINED


def test_late_endprocess_outside_call_preserves_next_buffer(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    monkeypatch.setattr(env.native, "processText2Speech", lambda instance, text: emit(env, instance))
    _, _, call = speak(env)
    finish(call)
    callback = env.core._veCallbackHandler
    callback._feedBuf = BytesIO(b"next buffer")
    result = callback(env.core.voiceInstance, None,
        native_message(env.types, env.types.VE_MSG_ENDPROCESS, env.types.VE_OUTDATA()))
    assert result == env.types.NUAN_E_TTS_USERSTOP
    assert callback._feedBuf.getvalue() == b"next buffer"


def test_legacy_use_prevents_entering_unproven_correlated_mode(env, monkeypatch):
    monkeypatch.setattr(env.native, "processText2Speech", lambda *args: None)
    env.core.speak(("legacy",))
    _, _, call = speak(env)
    finish(call)
    assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert "Legacy" in str(env.events[0].error)


def test_cancelled_native_userstop_is_silent_and_keeps_legacy_done(env, monkeypatch):
    def native(instance, text):
        env.core.cancel()
        return env.types.NUAN_E_TTS_USERSTOP
    monkeypatch.setattr(env.native, "processText2Speech", native)
    env.core.speak(("legacy",))
    assert len(env.dones) == 1
    assert env.events == []


def test_callback_lease_holds_bookmark_handler_before_next_call(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    entered, release, callback_ready = Event(), Event(), Event()
    def index(**kwargs):
        entered.set()
        assert release.wait(2)
    monkeypatch.setattr(env.original_driver.synthIndexReached, "notify", index)
    calls, callbacks = [], []
    def native(instance, text):
        calls.append(text)
        if len(calls) == 1:
            callbacks.append(run_thread(lambda: emit(env, instance, index=7)))
            callback_ready.set()
            assert entered.wait(1)
    monkeypatch.setattr(env.native, "processText2Speech", native)
    _, _, first = speak(env)
    assert entered.wait(1)
    assert callback_ready.wait(1)
    env.core.cancel()
    _, _, second = speak(env, segment=18)
    assert calls == ["hello"]
    release.set()
    finish(callbacks[0])
    finish(first)
    finish(second)
    assert [event.segment_id for event in env.events] == [18]


@pytest.mark.parametrize("kind", ["empty", "index", "break"])
def test_zero_audio_segments_still_wait_for_real_idle(env, monkeypatch, kind):
    prove_fake_quiescence(env, monkeypatch)
    import speech.commands as commands
    sequence = ()
    if kind == "index":
        index = commands.IndexCommand()
        index.index = 23
        sequence = (index,)
    elif kind == "break":
        pause = commands.BreakCommand()
        pause.time = 20
        sequence = (pause,)
    entered, release = Event(), Event()
    env.core._real_player.idle = lambda: (entered.set(), release.wait(2))
    monkeypatch.setattr(env.native, "processText2Speech", lambda *args: None)
    _, _, call = speak(env, sequence)
    assert entered.wait(1)
    assert env.events == []
    release.set()
    finish(call)
    assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_DRAINED


def test_pause_holds_completion_after_real_idle(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    env.core.pause(True)
    entered = Event()
    env.core._real_player.idle = entered.set
    monkeypatch.setattr(env.native, "processText2Speech", lambda *args: None)
    _, _, call = speak(env)
    assert entered.wait(1)
    assert not call[1].wait(.05)
    env.core.pause(False)
    finish(call)
    assert len(env.events) == 1


@pytest.mark.parametrize("status", [0, 0x80000807, 0xffffffff])
def test_raw_status_survives_installed_ctypes_errcheck(env, monkeypatch, status):
    native_function = env.native.veDll.ve_ttsProcessText2Speech
    # The real installed checker returns None for OK and USERSTOP.
    native_function.errcheck = env.native.veCheckForError
    monkeypatch.setattr(env.native, "processText2Speech", lambda *args: status)
    if status == 0xffffffff:
        with pytest.raises(env.types.VeError):
            env.module.ProcessText2Speech(env.core.voiceInstance, "hello")()
    else:
        assert env.module.ProcessText2Speech(env.core.voiceInstance, "hello")() == status
    assert native_function.errcheck is env.native.veCheckForError


def test_raw_status_call_does_not_mutate_shared_errcheck_concurrently(env, monkeypatch):
    native_function = env.native.veDll.ve_ttsProcessText2Speech
    native_function.errcheck = env.native.veCheckForError
    entered, release = Event(), Event()
    def process(instance, text):
        if text == "outer":
            entered.set()
            assert release.wait(2)
        return env.types.NUAN_OK
    monkeypatch.setattr(env.native, "processText2Speech", process)
    results = []
    outer = run_thread(lambda: results.append(env.module.ProcessText2Speech(env.core.voiceInstance, "outer")()))
    try:
        assert entered.wait(1)
        data = env.types.VE_INTEXT()
        text = b"original"
        data.eTextFormat = env.types.VE_NORM_TEXT
        data.cntTextLength = len(text)
        data.szInText = ctypes.cast(ctypes.c_char_p(text), ctypes.c_void_p)
        assert native_function(env.core.voiceInstance, ctypes.byref(data)) is None
        assert native_function.errcheck is env.native.veCheckForError
    finally:
        release.set()
    finish(outer)
    assert results == [0]


def test_cancel_resets_pause_before_next_legacy_speech(env, monkeypatch):
    # Empty speech reaches idle without the native ABI, isolating pause state.
    env.core.pause(True)
    env.core.cancel()
    call = run_thread(lambda: env.core.speak(()))
    try:
        finish(call)
        assert len(env.dones) == 1
    finally:
        env.core.pause(False)
        call[0].join(1)


def test_done_listener_can_terminate_without_deadlocking_speech(env, monkeypatch):
    monkeypatch.setattr(env.native, "close", lambda instance: None)
    monkeypatch.setattr(env.native, "terminate", lambda: None)
    monkeypatch.setattr(env.original_driver.synthDoneSpeaking, "notify", lambda **kwargs: env.core.terminate())
    call = run_thread(lambda: env.core.speak(()))
    try:
        finish(call)
        assert env.core._real_player.closes == 1
    finally:
        if not call[1].is_set():
            # Rescue the pre-fix non-reentrant lock so this RED cannot leave
            # a permanently blocked thread in the test process.
            env.core._speechRunLock.release()
            call[0].join(1)


def test_index_listener_can_terminate_and_retire_native_before_close(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    monkeypatch.setattr(env.native, "close", lambda instance: None)
    monkeypatch.setattr(env.native, "terminate", lambda: None)
    listener_returned, native_returned, closed = Event(), Event(), Event()
    close_player = env.core._real_player.close
    def close():
        assert native_returned.is_set()
        close_player()
        closed.set()
    env.core._real_player.close = close
    def index(**kwargs):
        env.core.terminate()
        assert not closed.is_set()
        listener_returned.set()
    monkeypatch.setattr(env.original_driver.synthIndexReached, "notify", index)
    def process(instance, text):
        emit(env, instance, index=7)
        native_returned.set()
    monkeypatch.setattr(env.native, "processText2Speech", process)
    _, _, call = speak(env)
    try:
        assert listener_returned.wait(1)
        finish(call)
        assert closed.wait(1)
        assert env.events == []
    finally:
        if not call[1].is_set():
            env.core._speechRunLock.release()
            call[0].join(1)


def test_native_error_status_fails_context_through_installed_errcheck(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    # Exercise the real ve2 checker, not a Python exception from the stub.
    env.native.veDll.ve_ttsProcessText2Speech.errcheck = env.native.veCheckForError
    monkeypatch.setattr(env.native, "processText2Speech", lambda *args: 0xffffffff)
    _, context, call = speak(env)
    finish(call)
    assert len(env.events) == 1
    assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert env.events[0].source_id is context.source_id
    assert isinstance(env.events[0].error, env.types.VeError)
    assert env.dones == []


@pytest.mark.parametrize("env", ["Cerence"], indirect=True)
@pytest.mark.parametrize("bookmark", [b"23", b"-17", b"0"])
def test_cerence_bookmark_decodes_szvalue(env, monkeypatch, bookmark):
    prove_fake_quiescence(env, monkeypatch)
    results = []
    def native(instance, text):
        results.extend(emit(env, instance, index=bookmark))
    monkeypatch.setattr(env.native, "processText2Speech", native)
    _, _, call = speak(env)
    finish(call)
    assert results == [env.types.NUAN_OK] * 3
    assert env.indexes == [{b"23": 23, b"-17": -17, b"0": 0}[bookmark]]
    assert [event.kind for event in env.events] == [env.rt.models.EventKind.SEGMENT_DRAINED]


@pytest.mark.parametrize("env", ["Cerence"], indirect=True)
@pytest.mark.parametrize("bookmark", [b"bad", b"", None])
def test_cerence_bookmark_decode_fault_fails_work(env, monkeypatch, bookmark):
    prove_fake_quiescence(env, monkeypatch)
    results, idle_calls = [], []
    env.core._real_player.idle = lambda: idle_calls.append(True)
    def native(instance, text):
        results.extend(emit(env, instance, index=bookmark))
        # Even a later idle return cannot rehabilitate the failed work.
        env.core._real_player.idle()
    monkeypatch.setattr(env.native, "processText2Speech", native)
    _, context, call = speak(env)
    finish(call)
    assert env.types.NUAN_E_TTS_USERSTOP in results
    assert idle_calls == [True]
    assert env.indexes == []
    assert len(env.events) == 1
    assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert env.events[0].source_id is context.source_id
    assert env.events[0].segment_id == 17
    assert isinstance(env.events[0].error, (TypeError, ValueError))
    assert env.dones == []


@pytest.mark.parametrize("env", ["Cerence"], indirect=True)
def test_callback_rejects_missing_instance_without_touching_current_buffer(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    callback = env.core._veCallbackHandler
    def native(instance, text):
        callback._feedBuf = BytesIO(b"current")
        message = native_message(env.types, env.types.VE_MSG_ENDPROCESS, env.types.VE_OUTDATA())
        assert callback(None, None, message) == env.types.NUAN_E_TTS_USERSTOP
        assert callback._feedBuf.getvalue() == b"current"
    monkeypatch.setattr(env.native, "processText2Speech", native)
    _, _, call = speak(env)
    finish(call)
    assert env.core._real_player.fed == []


@pytest.mark.parametrize("apply_before_barrier", [True, False])
@pytest.mark.parametrize("fresh_during_pause", [True, False])
def test_cancel_retires_inflight_pause_before_fresh_speech(env, apply_before_barrier, fresh_during_pause):
    entered, release, idle_entered = Event(), Event(), Event()
    player = env.core._real_player
    pause_player = player.pause
    def pause(switch):
        if switch and not apply_before_barrier:
            entered.set()
            assert release.wait(2)
        pause_player(switch)
        if switch and apply_before_barrier:
            entered.set()
            assert release.wait(2)
    player.pause = pause
    player.idle = idle_entered.set
    pausing, fresh = run_thread(lambda: env.core.pause(True)), None
    try:
        assert entered.wait(1)
        # Cancellation must still stop the player while pause is in flight.
        cancelling = run_thread(env.core.cancel)
        finish(cancelling)
        assert not player.isPaused
        if fresh_during_pause:
            fresh = run_thread(lambda: env.core.speak(()))
            assert not idle_entered.wait(.05)
        release.set()
        finish(pausing)
        if fresh is None:
            fresh = run_thread(lambda: env.core.speak(()))
        finish(fresh)
        assert idle_entered.is_set()
        assert not player.isPaused
        assert len(env.dones) == 1
    finally:
        release.set()
        pausing[0].join(1)
        env.core.pause(False)
        if fresh is not None:
            fresh[0].join(1)



def test_pause_requested_during_cancel_waits_for_player_stop(env):
    stop_entered, stop_release, pause_entered = Event(), Event(), Event()
    player = env.core._real_player
    stop_player, pause_player = player.stop, player.pause
    def stop():
        stop_entered.set()
        assert stop_release.wait(2)
        stop_player()
    def pause(switch):
        pause_entered.set()
        pause_player(switch)
    player.stop, player.pause = stop, pause
    cancelling, pausing = run_thread(env.core.cancel), None
    try:
        assert stop_entered.wait(1)
        pausing = run_thread(lambda: env.core.pause(True))
        assert not pause_entered.wait(.05)
        stop_release.set()
        finish(cancelling)
        finish(pausing)
        assert player.isPaused
        env.core.pause(False)
        fresh = run_thread(lambda: env.core.speak(()))
        finish(fresh)
        assert len(env.dones) == 1
    finally:
        stop_release.set()
        cancelling[0].join(1)
        if pausing is not None:
            pausing[0].join(1)
        env.core.pause(False)



def test_segment_drain_waits_for_real_resume_return(env, monkeypatch):
    prove_fake_quiescence(env, monkeypatch)
    idle_entered, resume_entered, resume_release = Event(), Event(), Event()
    player = env.core._real_player
    pause_player = player.pause
    env.core.pause(True)
    def pause(switch):
        if not switch:
            resume_entered.set()
            assert resume_release.wait(2)
        pause_player(switch)
    player.pause = pause
    player.idle = idle_entered.set
    monkeypatch.setattr(env.native, "processText2Speech", lambda *args: None)
    _, _, speech = speak(env)
    resuming = None
    try:
        assert idle_entered.wait(1)
        resuming = run_thread(lambda: env.core.pause(False))
        assert resume_entered.wait(1)
        assert not speech[1].wait(.05)
        assert env.events == []
        resume_release.set()
        finish(resuming)
        finish(speech)
        assert not player.isPaused
        assert [event.kind for event in env.events] == [env.rt.models.EventKind.SEGMENT_DRAINED]
    finally:
        resume_release.set()
        if resuming is not None:
            resuming[0].join(1)
        env.core.pause(False)
        speech[0].join(1)



def assert_operation_failed(call, error):
    assert call[1].wait(2)
    assert call[2] == [error]


@pytest.mark.parametrize("speech_path", ["legacy", "segment"])
@pytest.mark.parametrize("fresh_during_pause", [True, False])
def test_failed_cancelled_pause_reconciliation_blocks_fresh_speech(env, monkeypatch, speech_path, fresh_during_pause):
    prove_fake_quiescence(env, monkeypatch)
    entered, release = Event(), Event()
    player = env.core._real_player
    pause_player = player.pause
    error = OSError("resume failed")
    failed_resume_states = []
    def pause(switch):
        if switch:
            entered.set()
            assert release.wait(2)
            pause_player(True)
        else:
            failed_resume_states.append(player.isPaused)
            raise error
    player.pause = pause
    native_calls = []
    monkeypatch.setattr(env.native, "processText2Speech", lambda instance, text: native_calls.append(text))
    def fresh_speech():
        if speech_path == "legacy":
            return run_thread(lambda: env.core.speak(("fresh",)))
        return speak(env, ("fresh",), segment=18)[2]
    pausing, fresh = run_thread(lambda: env.core.pause(True)), None
    try:
        assert entered.wait(1)
        finish(run_thread(env.core.cancel))
        assert not player.isPaused
        if fresh_during_pause:
            fresh = fresh_speech()
            assert not fresh[1].wait(.05)
        release.set()
        assert_operation_failed(pausing, error)
        # Corrective resume failed before changing the paused player.
        assert failed_resume_states == [True]
        if fresh is None:
            fresh = fresh_speech()
        if speech_path == "legacy":
            assert_operation_failed(fresh, error)
        else:
            finish(fresh)
            assert len(env.events) == 1
            assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
            assert env.events[0].segment_id == 18
            assert env.events[0].error is error
        assert native_calls == []
        assert env.dones == []
        assert player.idles == 0
        # Clearing cancellation cannot clear an unknown player state fault.
        env.core.cancel()
        again = fresh_speech()
        if speech_path == "legacy":
            assert_operation_failed(again, error)
        else:
            finish(again)
            assert len(env.events) == 2
            assert all(event.kind is env.rt.models.EventKind.SEGMENT_FAILED for event in env.events)
        assert native_calls == []
    finally:
        release.set()
        pausing[0].join(1)
        if fresh is not None:
            fresh[0].join(1)


@pytest.mark.parametrize("speech_path", ["legacy", "segment"])
def test_resume_failure_faults_active_work_and_suppresses_drain(env, monkeypatch, speech_path):
    prove_fake_quiescence(env, monkeypatch)
    idle_entered, idle_release = Event(), Event()
    player = env.core._real_player
    env.core.pause(True)
    stop_player = player.stop
    def idle():
        idle_entered.set()
        assert idle_release.wait(5)
    def stop():
        stop_player()
        idle_release.set()
    player.idle, player.stop = idle, stop
    error = OSError("active resume failed")
    failed_resume_states = []
    def pause(switch):
        failed_resume_states.append(player.isPaused)
        raise error
    player.pause = pause
    if speech_path == "legacy":
        speech = run_thread(lambda: env.core.speak(()))
        context = None
    else:
        _, context, speech = speak(env, ())
    try:
        assert idle_entered.wait(1)
        with pytest.raises(OSError, match="active resume failed"):
            env.core.pause(False)
        assert failed_resume_states == [True]
        if speech_path == "legacy":
            assert_operation_failed(speech, error)
        else:
            finish(speech)
            assert len(env.events) == 1
            assert env.events[0].kind is env.rt.models.EventKind.SEGMENT_FAILED
            assert env.events[0].source_id is context.source_id
            assert env.events[0].segment_id == 17
            assert env.events[0].error is error
        assert env.dones == []
    finally:
        # Release the pre-fix paused work so RED does not leak a thread.
        env.core.cancel()
        speech[0].join(1)
