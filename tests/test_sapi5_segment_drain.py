"""Exercise the real SAPI5 outer and pinned NVDA driver at COM/audio boundaries."""

import builtins
import ctypes
import ctypes.wintypes
from dataclasses import dataclass
import importlib.util
from pathlib import Path
import sys
from threading import Condition, Event, Thread, current_thread
from types import ModuleType, SimpleNamespace

import pytest

from runtime_harness import load_runtime, load_scheduler

ROOT = Path(__file__).resolve().parents[1]


class Player:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.fed = []
        self.callbacks = []
        self.idle_entered = Event()
        self.idle_release = Event()
        self.feed_entered = Event()
        self.feed_release = Event()
        self.feed_release.set()
        self.error = None
        self.stops = 0
        self.stop_error = None
        self.closed = False
        self.paused = False

    def feed(self, data, size=None, onDone=None):
        self.feed_entered.set()
        assert self.feed_release.wait(2), "Test did not release feed"
        if self.error == "feed":
            raise OSError("feed failed")
        self.fed.append(size)
        if onDone:
            self.callbacks.append(onDone)

    def idle(self):
        self.idle_entered.set()
        assert self.idle_release.wait(2), "Test did not release idle"
        if self.error == "idle":
            raise OSError("idle failed")
        callbacks, self.callbacks = self.callbacks, []
        for callback in callbacks:
            callback()

    def stop(self):
        self.stops += 1
        self.idle_release.set()
        if self.stop_error:
            raise OSError("stop failed")

    def close(self):
        self.closed = True

    def pause(self, switch):
        self.paused = switch


class Sonic:
    def __init__(self, sampleRate, channels):
        self.sampleRate, self.channels = sampleRate, channels
        self.samplesAvailable = 10000
        self.tail = [1, 2, 3]
        self.error = None
        self.speed = 1

    def writeShort(self, *args):
        pass

    def flush(self):
        if self.error:
            raise OSError("sonic flush failed")

    def readShort(self):
        tail, self.tail = self.tail, []
        return tail


class Native:
    def __init__(self):
        self.condition = Condition()
        self.calls = []
        self.purges = 0
        self.purge_error = None
        self.sink = None
        self.error = None
        self.Voice = SimpleNamespace(Id="voice", GetAttribute=lambda name: "409")
        self.Status = SimpleNamespace(LastBookmark="")
        self.AudioOutputStream = self
        self.Rate = 0
        self.Volume = 100

    def QueryInterface(self, interface):
        return self

    def SetOutput(self, audio, default):
        self.audio = audio

    def SetNotifySink(self, sink):
        self.sink = sink

    def Speak(self, text, flags):
        if text is None:
            if self.purge_error:
                raise OSError("purge failed")
            with self.condition:
                self.purges += 1
                self.condition.notify_all()
            return 0
        if self.error:
            raise OSError("native speak failed")
        with self.condition:
            stream = len(self.calls) + 1
            self.calls.append((stream, text, current_thread()))
            self.condition.notify_all()
            return stream

    def GetVoices(self):
        return [self.Voice]

    def wait_calls(self, count):
        with self.condition:
            assert self.condition.wait_for(lambda: len(self.calls) >= count, 2)

    def wait_purge(self):
        with self.condition:
            assert self.condition.wait_for(lambda: self.purges > 0, 2)

    def end(self, stream=1):
        self.sink.EndStream(stream, 0)


def load_sapi5(monkeypatch, *, rt=None, scheduler=None, voice_base=object, commands=None):
    def module(name, **attrs):
        result = ModuleType(name)
        result.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, result)
        return result

    def package(name, path, **attrs):
        result = module(name, **attrs)
        result.__path__ = [str(path)]
        return result

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        result = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, result)
        spec.loader.exec_module(result)
        return result

    class Base:
        @staticmethod
        def VoiceSetting(): return SimpleNamespace(id="voice")
        @staticmethod
        def RateSetting(): return SimpleNamespace(id="rate")
        @staticmethod
        def RateBoostSetting(): return SimpleNamespace(id="rateBoost")
        @staticmethod
        def PitchSetting(): return SimpleNamespace(id="pitch")
        @staticmethod
        def VolumeSetting(): return SimpleNamespace(id="volume")
        @staticmethod
        def UseWasapiSetting(): return SimpleNamespace(id="useWasapi")

        def __setattr__(self, name, value):
            setter = getattr(type(self), "_set_" + name, None) if not name.startswith("_") else None
            if setter:
                setter(self, value)
            else:
                object.__setattr__(self, name, value)

    # NVDA's AutoPropertyObject normally installs these properties via its metaclass.
    class BaseMeta(type):
        def __new__(meta, name, bases, attrs):
            result = super().__new__(meta, name, bases, attrs)
            for key, getter in attrs.items():
                if key.startswith("_get_"):
                    setattr(result, key[5:], property(getter, attrs.get("_set_" + key[5:])))
            return result

    Base = BaseMeta("Base", (Base,), {})
    native_instances, players, indexes, dones, logs = [], [], [], [], []

    def create_native(*args):
        native = Native()
        native_instances.append(native)
        return native

    def create_player(**kwargs):
        player = Player(**kwargs)
        players.append(player)
        return player

    package("synthDrivers", ROOT / "addon/synthDrivers")
    package("synthDrivers.WorldVoice", ROOT / "addon/synthDrivers/WorldVoice")
    package("synthDrivers.WorldVoice.driver", ROOT / "addon/synthDrivers/WorldVoice/driver", Voice=voice_base)
    rt = rt or load_runtime(monkeypatch, "synthDrivers.WorldVoice.runtime")
    scheduler = scheduler or load_scheduler(monkeypatch, rt)
    package("speech", ROOT)
    @dataclass
    class IndexCommand:
        index: int
    commands = commands or module("speech.commands", IndexCommand=IndexCommand,
        **{name: type(name, (), {}) for name in ("CharacterModeCommand", "LangChangeCommand", "BreakCommand",
        "PitchCommand", "RateCommand", "VolumeCommand", "PhonemeCommand", "SpeechCommand")})
    monkeypatch.setitem(sys.modules, "speech.commands", commands)
    monkeypatch.setattr(ctypes, "HRESULT", ctypes.c_long, raising=False)
    monkeypatch.setattr(ctypes, "WINFUNCTYPE", lambda *args: lambda *args: lambda *args: 0, raising=False)
    monkeypatch.setattr(ctypes.wintypes, "_LARGE_INTEGER", ctypes.c_longlong, raising=False)
    monkeypatch.setattr(ctypes.wintypes, "_ULARGE_INTEGER", ctypes.c_ulonglong, raising=False)
    package("winBindings", ROOT)
    ole32 = module("winBindings.ole32")
    sys.modules["winBindings"].ole32 = ole32
    package("comInterfaces", ROOT)
    class WAVEFORMATEX(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulong) for name in ("wFormatTag", "cbSize", "nChannels", "nSamplesPerSec", "wBitsPerSample", "nBlockAlign", "nAvgBytesPerSec")]
    interfaces = {name: type(name, (ctypes.Structure,), {"_fields_": []}) for name in
        ("ISpAudio", "ISpEventSource", "ISpEventSink", "ISpNotifySource", "ISpNotifySink", "ISpVoice", "ISpeechVoice", "SPEVENT")}
    module("comInterfaces.SpeechLib", GUID=lambda text: text, SPAUDIOSTATE=int, WAVEFORMATEX=WAVEFORMATEX, **interfaces)
    comtypes = package("comtypes", ROOT, COMError=OSError, COMObject=object,
        hresult=SimpleNamespace(S_OK=0, E_OUTOFMEMORY=1, E_UNEXPECTED=2, E_NOTIMPL=3))
    comtypes.client = module("comtypes.client", CreateObject=create_native)
    module("winreg")
    module("audioDucking", AudioDucker=object, isAudioDuckingSupported=lambda: False, _isDebug=lambda: False)
    module("config", conf={"audio": {"outputDevice": "default"}})
    module("nvwave", WavePlayer=create_player, WAVE_FORMAT_PCM=1)
    module("NVDAState", _allowDeprecatedAPI=lambda: False)
    module("languageHandler", LCID_NONE=0, localeNameToWindowsLCID=lambda lang: 0x409)
    module("synthDrivers._sonic", SonicStream=Sonic, initialize=lambda: None)
    module("logHandler", log=SimpleNamespace(**{name: lambda *args, **kwargs: logs.append(args)
        for name in ("debug", "debugWarning", "warning", "error", "exception")}))
    module("synthDriverHandler", SynthDriver=Base, VoiceInfo=object,
        synthIndexReached=SimpleNamespace(notify=lambda **kw: indexes.append(kw["index"])),
        synthDoneSpeaking=SimpleNamespace(notify=lambda **kw: dones.append(kw["synth"])))
    # Notifications must be hashable in the real driver's supportedNotifications.
    class Notification:
        def __init__(self, callback): self.notify = callback
    sys.modules["synthDriverHandler"].synthIndexReached = Notification(lambda **kw: indexes.append(kw["index"]))
    sys.modules["synthDriverHandler"].synthDoneSpeaking = Notification(lambda **kw: dones.append(kw["synth"]))
    monkeypatch.setattr(builtins, "_", lambda text: text, raising=False)
    base = load("synthDrivers.sapi5", ROOT / "ref/nvda/source/synthDrivers/sapi5.py")
    outer = load("synthDrivers.WorldVoice.driver.SAPI5", ROOT / "addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py")
    driver = outer.SynthDriver()
    return SimpleNamespace(driver=driver, native=native_instances[-1], player=players[-1],
        natives=native_instances, players=players, outer=outer, base=base, rt=rt, scheduler=scheduler,
        indexes=indexes, dones=dones, logs=logs, commands=commands)


@pytest.fixture
def env(monkeypatch):
    result = load_sapi5(monkeypatch)
    yield result
    for player in result.players:
        player.feed_release.set()
        player.idle_release.set()
        player.stop_error = None
    for native in result.natives:
        native.purge_error = None
    result.driver.terminate()


class TerminalEvents(list):
    def __init__(self):
        super().__init__()
        self.condition = Condition()

    def append(self, event):
        with self.condition:
            super().append(event)
            self.condition.notify_all()


def speak(env, segment=17, commands=None, sink=None):
    events = TerminalEvents()
    token = env.scheduler.CancellationToken()
    context = env.rt.models.PlaybackContext(object(), segment)
    env.driver.speak_segment(commands or ("hello", env.commands.IndexCommand(7)), token,
        context=context, on_event=sink or events.append)
    return token, context, events


def wait_event(events):
    with events.condition:
        assert events.condition.wait_for(lambda: bool(events), 2), "No terminal event delivered"
        assert len(events) == 1
        return events[0]


def test_end_stream_waits_for_actual_idle_and_preserves_tail_indexes(env):
    _, context, events = speak(env)
    env.native.wait_calls(1)
    env.native.end()
    assert env.player.idle_entered.wait(1)
    assert events == []
    assert env.indexes == [7]
    assert env.player.fed == [6]
    env.player.idle_release.set()
    event = wait_event(events)
    assert event.kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert event.source_id is context.source_id
    assert event.segment_id == 17
    assert env.dones == []
    assert env.outer.Voice.synth_driver_class is type(env.driver)


@pytest.mark.parametrize("failure", ["feed", "idle", "sonic", "native"])
def test_observable_worker_or_player_failure_fails_exact_context(env, failure):
    if failure == "native":
        env.native.error = True
    _, context, events = speak(env)
    if failure != "native":
        env.native.wait_calls(1)
        if failure == "sonic":
            env.driver.sonicStream.error = True
        else:
            env.player.error = failure
        env.player.idle_release.set()
        env.native.end()
    event = wait_event(events)
    assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert event.source_id is context.source_id
    assert event.segment_id == 17
    assert isinstance(event.error, OSError)
    assert env.dones == []


def test_idle_without_end_marker_fails_instead_of_draining(env):
    _, context, events = speak(env)
    env.native.wait_calls(1)
    env.player.idle_release.set()
    env.driver.player.idle()
    event = wait_event(events)
    assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert event.source_id is context.source_id
    assert isinstance(event.error, RuntimeError)


def test_empty_audio_still_requires_idle(env):
    env.driver.sonicStream.tail = []
    _, _, events = speak(env, commands=("",))
    env.native.wait_calls(1)
    env.native.end()
    assert env.player.idle_entered.wait(1)
    assert events == []
    env.player.idle_release.set()
    assert wait_event(events).kind is env.rt.models.EventKind.SEGMENT_DRAINED


@pytest.mark.parametrize("token_only", [False, True])
def test_cancel_during_idle_cannot_publish_success(env, token_only):
    token, _, events = speak(env)
    env.native.wait_calls(1)
    env.native.end()
    assert env.player.idle_entered.wait(1)
    if token_only:
        token.cancel()
        env.player.idle_release.set()
    else:
        env.driver.cancel()
        env.native.wait_purge()
    # A following request is a FIFO witness that the first worker job retired.
    _, _, successor = speak(env, segment=18)
    env.native.wait_calls(2)
    env.native.end(2)
    assert wait_event(successor).kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert events == []


def test_old_stream_and_delayed_bookmark_cannot_satisfy_successor(env):
    _, _, old_events = speak(env)
    env.native.wait_calls(1)
    env.native.sink.Bookmark(1, 0, "7", 7)
    delayed = env.player.callbacks[0]
    env.driver.cancel()
    env.native.wait_purge()
    _, context, events = speak(env, segment=18)
    env.native.wait_calls(2)
    delayed()
    env.native.end(1)
    assert env.indexes == []
    assert events == [] and old_events == []
    env.native.end(2)
    event = wait_event(events)
    assert event.source_id is context.source_id
    assert event.segment_id == 18
    assert env.indexes == [7]


def test_queued_segments_each_idle_before_exact_completion(env):
    _, first, first_events = speak(env)
    _, second, second_events = speak(env, segment=18)
    env.native.wait_calls(1)
    env.native.end()
    assert env.player.idle_entered.wait(1)
    assert len(env.native.calls) == 1 and first_events == []
    env.player.idle_release.set()
    first_event = wait_event(first_events)
    env.native.wait_calls(2)
    env.native.end(2)
    second_event = wait_event(second_events)
    assert first_event.source_id is first.source_id
    assert second_event.source_id is second.source_id
    assert second_event.segment_id == 18


def test_completion_sink_can_terminate_without_joining_worker_itself(env):
    done, delivery_threads, events, errors = Event(), [], [], []
    def sink(event):
        try:
            delivery_threads.append(current_thread())
            env.driver.terminate()
            events.append(event)
        except Exception as error:
            errors.append(error)
        finally:
            done.set()
    speak(env, sink=sink)
    env.native.wait_calls(1)
    worker = env.native.calls[0][2]
    env.player.idle_release.set()
    env.native.end()
    assert done.wait(2), "Termination deadlocked completion delivery"
    assert errors == []
    assert events[0].kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert delivery_threads[0] is not worker
    assert not worker.is_alive()


def test_cancelled_token_never_submits_native_work(env):
    token = env.scheduler.CancellationToken()
    token.cancel()
    events = []
    env.driver.speak_segment(("cancelled",), token,
        context=env.rt.models.PlaybackContext(object(), 17), on_event=events.append)
    assert env.native.calls == [] and events == []


@pytest.mark.parametrize("audio_mode", ["wasapi", "winmm", "legacy"])
def test_real_profiles_remain_unsupported(env, audio_mode):
    result = env.driver.get_segment_drain_support(nvda_version="source-DETACHED-9ef645d", audio_mode=audio_mode)
    assert result.supported is False
    assert result.profile and result.reason


def test_legacy_route_rejects_correlated_admission_before_speech(env):
    env.driver.useWasapi = False
    _, _, events = speak(env)
    assert wait_event(events).kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert env.natives[-1].calls == []


def test_voice_reload_preserves_settings_and_invalidates_prior_context(env):
    env.driver.rate = 65
    env.driver.pitch = 35
    env.driver.volume = 75
    env.driver.rateBoost = True
    _, _, old_events = speak(env)
    env.native.wait_calls(1)
    env.driver.voice = "voice"
    assert env.player.closed
    assert env.driver.rate == 65 and env.driver.pitch == 35 and env.driver.volume == 75
    assert env.natives[-1].Volume == 75
    assert env.natives[-1].Rate == 0
    assert env.driver.sonicStream.speed == 4.075
    env.native.end()
    assert old_events == []


def test_ordinary_speech_keeps_legacy_notifications_and_indexes(env):
    env.driver.speak(("legacy", env.commands.IndexCommand(7), env.commands.IndexCommand(9)))
    env.native.wait_calls(1)
    env.player.idle_release.set()
    env.native.end()
    assert env.player.idle_entered.wait(1)
    assert env.indexes == [7, 9]
    assert env.dones == [env.driver]


def test_legacy_audio_start_notification_keeps_original_state(env):
    env.driver.useWasapi = False
    native = env.natives[-1]
    native.sink.StartStream(1, 0)
    assert env.driver._isSpeaking is True
    native.end()
    assert env.driver._isSpeaking is False
    assert env.dones == [env.driver]


def test_com_feed_failure_wakes_worker_without_end_notification(env):
    _, context, events = speak(env)
    env.native.wait_calls(1)
    env.player.error = "feed"
    with pytest.raises(OSError, match="feed failed"):
        env.native.audio.ISequentialStream_RemoteWrite(None, None, 8, None)
    event = wait_event(events)
    assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert event.source_id is context.source_id
    assert env.dones == []


def test_cancelled_queued_work_is_not_submitted(env):
    _, _, first_events = speak(env)
    env.native.wait_calls(1)
    _, _, queued_events = speak(env, segment=18)
    env.driver.cancel()
    env.native.wait_purge()
    _, _, successor_events = speak(env, segment=19)
    env.native.wait_calls(2)
    env.native.end(2)
    assert wait_event(successor_events).segment_id == 19
    assert first_events == [] and queued_events == []


def test_cancel_invalidates_terminal_delivery_waiting_off_worker(env, monkeypatch):
    entered, release = Event(), Event()
    complete = env.rt.playback_work.PlaybackWork.complete_drained
    def blocked_complete(work):
        entered.set()
        assert release.wait(2)
        return complete(work)
    monkeypatch.setattr(env.rt.playback_work.PlaybackWork, "complete_drained", blocked_complete)
    _, _, events = speak(env)
    env.native.wait_calls(1)
    env.player.idle_release.set()
    env.native.end()
    assert entered.wait(1)
    env.driver.cancel()
    release.set()
    env.native.wait_purge()
    _, _, successor = speak(env, segment=18)
    env.native.wait_calls(2)
    env.native.end(2)
    assert wait_event(successor).segment_id == 18
    assert events == []


def test_cancel_waits_for_admitted_feed_final_stop_before_successor(env):
    _, _, old_events = speak(env)
    env.native.wait_calls(1)
    env.player.feed_release.clear()
    failures = []
    def write():
        try:
            env.native.audio.ISequentialStream_RemoteWrite(None, None, 8, None)
        except Exception as error:
            failures.append(error)
    callback = Thread(target=write, daemon=True)
    callback.start()
    assert env.player.feed_entered.wait(1)
    env.driver.cancel()
    _, _, events = speak(env, segment=18)
    assert len(env.native.calls) == 1
    stops = env.player.stops
    env.player.feed_release.set()
    callback.join(2)
    assert not callback.is_alive() and failures == []
    env.native.wait_calls(2)
    assert env.player.stops > stops
    env.native.end(2)
    assert wait_event(events).segment_id == 18
    assert old_events == []


def test_failed_segment_purges_native_before_successor_admission(env):
    _, _, failed = speak(env)
    env.native.wait_calls(1)
    env.player.error = "feed"
    env.native.end()
    assert wait_event(failed).kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert env.native.purges == 1
    env.player.error = None
    env.player.idle_release.set()
    _, _, next_events = speak(env, segment=18)
    env.native.wait_calls(2)
    env.native.end(2)
    assert wait_event(next_events).segment_id == 18


@pytest.mark.parametrize("control", ["stop", "purge"])
def test_failed_retirement_fails_queued_and_future_work_without_admitting_audio(env, control):
    _, _, failed = speak(env)
    env.native.wait_calls(1)
    _, _, queued = speak(env, segment=18)
    env.player.error = "feed"
    if control == "stop":
        env.player.stop_error = True
    else:
        env.native.purge_error = True
    env.native.end()
    assert wait_event(failed).kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert wait_event(queued).kind is env.rt.models.EventKind.SEGMENT_FAILED
    env.player.error = None
    _, _, successor = speak(env, segment=19)
    assert wait_event(successor).kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert len(env.native.calls) == 1
    env.player.stop_error = None
    env.native.purge_error = None


def test_tail_bookmarks_keep_order_when_player_callbacks_are_delayed(env):
    _, _, events = speak(env, commands=("hello", env.commands.IndexCommand(7), env.commands.IndexCommand(9)))
    env.native.wait_calls(1)
    env.native.sink.Bookmark(1, 0, "7", 7)
    env.native.end()
    assert env.player.idle_entered.wait(1)
    assert env.indexes == [7, 9]
    env.player.idle_release.set()
    assert wait_event(events).kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert env.indexes == [7, 9]


def test_worker_completion_without_end_marker_fails_exact_work(env):
    _, context, events = speak(env)
    env.native.wait_calls(1)
    with env.driver._threadCond:
        env.driver._isCompleted = True
        env.driver._threadCond.notify_all()
    event = wait_event(events)
    assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert event.source_id is context.source_id
    assert isinstance(event.error, RuntimeError)


def test_termination_waits_for_admitted_feed_final_stop(env):
    _, _, events = speak(env)
    env.native.wait_calls(1)
    env.player.feed_release.clear()
    callback = Thread(target=lambda: env.native.audio.ISequentialStream_RemoteWrite(None, None, 8, None), daemon=True)
    callback.start()
    assert env.player.feed_entered.wait(1)
    stopped = Event()
    termination = Thread(target=lambda: (env.driver.terminate(), stopped.set()), daemon=True)
    termination.start()
    assert not stopped.wait(.02)
    env.player.feed_release.set()
    callback.join(2)
    termination.join(2)
    assert not callback.is_alive() and not termination.is_alive()
    assert stopped.is_set() and env.player.closed
    assert events == []


def test_tail_indexes_do_not_overtake_an_admitted_bookmark_notification(env, monkeypatch):
    _, _, events = speak(env, commands=("hello", env.commands.IndexCommand(7), env.commands.IndexCommand(9)))
    env.native.wait_calls(1)
    env.native.sink.Bookmark(1, 0, "7", 7)
    entered, release = Event(), Event()
    notification = sys.modules["synthDriverHandler"].synthIndexReached
    notify = notification.notify
    def blocked_notify(**kwargs):
        if kwargs["index"] == 7:
            entered.set()
            assert release.wait(2)
        notify(**kwargs)
    monkeypatch.setattr(notification, "notify", blocked_notify)
    callback = Thread(target=env.player.callbacks[0], daemon=True)
    callback.start()
    assert entered.wait(1)
    env.player.idle_release.set()
    env.native.end()
    # Tail notification must await the already admitted ordinary bookmark.
    assert not env.player.idle_entered.wait(.02)
    release.set()
    callback.join(2)
    assert not callback.is_alive()
    assert wait_event(events).kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert env.indexes == [7, 9]


def test_voice_reload_replaces_faulted_playback_and_can_speak_again(env):
    _, _, failed = speak(env)
    env.native.wait_calls(1)
    env.player.error = "feed"
    env.native.purge_error = True
    env.native.end()
    assert wait_event(failed).kind is env.rt.models.EventKind.SEGMENT_FAILED
    env.native.purge_error = None
    env.driver.voice = "voice"
    native, player = env.natives[-1], env.players[-1]
    player.idle_release.set()
    _, _, events = speak(env, segment=18)
    native.wait_calls(1)
    native.end()
    assert wait_event(events).segment_id == 18


def test_token_cancelled_native_end_retires_silently_before_successor(env):
    token, _, old_events = speak(env)
    env.native.wait_calls(1)
    token.cancel()
    _, _, successor = speak(env, segment=18)
    env.native.end()
    env.native.wait_calls(2)
    env.native.end(2)
    assert wait_event(successor).segment_id == 18
    assert old_events == []


@pytest.mark.parametrize("feed_fails", [False, True])
def test_admitted_pcm_feed_retires_before_final_tail_and_idle(env, monkeypatch, feed_fails):
    _, context, events = speak(env)
    env.native.wait_calls(1)
    admitted, release = Event(), Event()
    feed = env.player.feed
    failures = []
    callback_thread = None
    def held_pcm_feed(data, size=None, onDone=None):
        if current_thread() is callback_thread:
            admitted.set()
            assert release.wait(2)
            if feed_fails:
                raise OSError("admitted PCM feed failed")
        return feed(data, size, onDone)
    monkeypatch.setattr(env.player, "feed", held_pcm_feed)
    def write():
        try:
            env.native.audio.ISequentialStream_RemoteWrite(None, None, 8, None)
        except Exception as error:
            failures.append(error)
    callback_thread = Thread(target=write, daemon=True)
    callback_thread.start()
    assert admitted.wait(1)
    env.player.idle_release.set()
    env.native.end()
    try:
        assert not env.player.idle_entered.wait(.02), "Idle overtook an admitted PCM feed"
        assert events == []
    finally:
        release.set()
        callback_thread.join(2)
    assert not callback_thread.is_alive()
    event = wait_event(events)
    assert event.source_id is context.source_id
    if feed_fails:
        assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
        assert len(failures) == 1
        assert not env.player.idle_entered.is_set()
    else:
        assert event.kind is env.rt.models.EventKind.SEGMENT_DRAINED
        assert failures == []


def test_pcm_arriving_after_final_idle_cannot_feed_the_completed_segment(env):
    _, _, events = speak(env)
    env.native.wait_calls(1)
    env.native.end()
    assert env.player.idle_entered.wait(1)
    before = tuple(env.player.fed)
    env.native.audio.ISequentialStream_RemoteWrite(None, None, 8, None)
    assert tuple(env.player.fed) == before
    env.player.idle_release.set()
    assert wait_event(events).kind is env.rt.models.EventKind.SEGMENT_DRAINED


@pytest.mark.parametrize("operation", ["writeShort", "readShort"])
def test_com_sonic_failure_before_feed_fails_and_wakes_exact_work(env, monkeypatch, operation):
    _, context, events = speak(env)
    env.native.wait_calls(1)
    def fail(*args):
        raise OSError("COM Sonic operation failed")
    monkeypatch.setattr(env.driver.sonicStream, operation, fail)
    with pytest.raises(OSError, match="COM Sonic operation failed"):
        env.native.audio.ISequentialStream_RemoteWrite(None, None, 8, None)
    event = wait_event(events)
    assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
    assert event.source_id is context.source_id
    assert event.segment_id == 17
    assert str(event.error) == "COM Sonic operation failed"
    assert not env.player.idle_entered.is_set()
    assert env.dones == []


def test_admitted_com_sonic_operation_retires_before_final_tail_and_idle(env, monkeypatch):
    _, _, events = speak(env)
    env.native.wait_calls(1)
    entered, release = Event(), Event()
    write = env.driver.sonicStream.writeShort
    def blocked_write(*args):
        entered.set()
        assert release.wait(2)
        return write(*args)
    monkeypatch.setattr(env.driver.sonicStream, "writeShort", blocked_write)
    failures = []
    def write_pcm():
        try:
            env.native.audio.ISequentialStream_RemoteWrite(None, None, 8, None)
        except Exception as error:
            failures.append(error)
    callback = Thread(target=write_pcm, daemon=True)
    callback.start()
    assert entered.wait(1)
    env.native.end()
    env.player.idle_release.set()
    try:
        assert not env.player.idle_entered.wait(.02), "Idle overtook Sonic processing"
    finally:
        release.set()
        callback.join(2)
    assert failures == [] and not callback.is_alive()
    assert wait_event(events).kind is env.rt.models.EventKind.SEGMENT_DRAINED
    assert env.player.fed == [6, 0]


def test_pcm_arriving_after_completion_cannot_feed_retired_audio(env):
    _, _, events = speak(env)
    env.native.wait_calls(1)
    env.player.idle_release.set()
    env.native.end()
    assert wait_event(events).kind is env.rt.models.EventKind.SEGMENT_DRAINED
    before = tuple(env.player.fed)
    env.native.audio.ISequentialStream_RemoteWrite(None, None, 8, None)
    assert tuple(env.player.fed) == before


def test_token_cancel_retires_sonic_tail_and_bookmarks_before_successors(env):
    token, _, old_events = speak(env)
    env.native.wait_calls(1)
    token.cancel()
    _, _, next_events = speak(env, segment=18, commands=("next", env.commands.IndexCommand(9)))
    env.native.end()
    env.native.wait_calls(2)
    # The cancelled request's unconsumed Sonic tail cannot become successor audio.
    assert env.driver.sonicStream.tail == []
    assert [tuple(bookmarks) for bookmarks in env.driver._bookmarkLists] == [(9,)]
    env.driver.sonicStream.tail = [4]
    env.player.idle_release.set()
    env.native.end(2)
    assert wait_event(next_events).segment_id == 18
    env.driver.speak(("ordinary", env.commands.IndexCommand(11)))
    env.native.wait_calls(3)
    done = Event()
    notification = sys.modules["synthDriverHandler"].synthDoneSpeaking
    notify = notification.notify
    def observed_done(**kwargs):
        notify(**kwargs)
        done.set()
    notification.notify = observed_done
    env.native.end(3)
    assert done.wait(1)
    assert env.indexes == [9, 11]
    assert env.player.fed == [2, 0]
    assert old_events == []


def test_retained_old_notify_sink_cannot_consume_replacement_end_event(env, monkeypatch):
    old_sink = env.native.sink
    env.driver.voice = "voice"
    native, player = env.natives[-1], env.players[-1]
    _, _, events = speak(env, segment=18)
    native.wait_calls(1)
    event = SimpleNamespace(eEventId=env.base._SPEventEnum.END_INPUT_STREAM, ulStreamNum=1,
        ullAudioStreamOffset=0)
    queued = {source: [] for source in env.natives}
    queued[native].append(event)
    def enumerate_events(source):
        while queued[source]:
            yield queued[source].pop(0)
    monkeypatch.setattr(env.base._SapiEvent, "enumerateFrom", staticmethod(enumerate_events))
    old_sink.ISpNotifySink_Notify()
    assert queued[native] == [event], "An old sink consumed replacement voice events"
    player.idle_release.set()
    native.sink.ISpNotifySink_Notify()
    assert wait_event(events).segment_id == 18
    assert queued[native] == []
