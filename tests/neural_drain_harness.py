"""Real Neural outer/inner/speechapi code over a controlled CFFI/SDK boundary.

The fake SDK's explicit stop-quiescence promise is test evidence only. Real
SDK profiles stay unsupported; no version/provenance check is bypassed.
"""

import builtins
import importlib.util
from pathlib import Path
import sys
from threading import Condition, Event, Thread
from types import ModuleType, SimpleNamespace

from runtime_harness import load_runtime, load_scheduler

ROOT = Path(__file__).resolve().parents[1]
NEURAL = ROOT / "addon/synthDrivers/WorldVoice/driver/Neural"


class Handle:
    def __init__(self, value):
        self.value = value


class Ffi:
    NULL = None

    def new(self, kind, value=None):
        return value.encode() if isinstance(value, str) else value if kind == "char[]" else [0]

    def gc(self, handle, destructor):
        return handle

    def new_handle(self, value):
        return Handle(value)

    def from_handle(self, handle):
        return handle.value

    def callback(self, kind):
        return lambda function: function

    def string(self, value):
        return value.encode() if isinstance(value, str) else value

    def buffer(self, value, size):
        return value[:size]

    def dlopen(self, path):
        return self.lib


class Native:
    ResultReason_SynthesizingAudioComplete = 9
    SpeechServiceConnection_SynthModelKey = 1
    SpeechSynthesisOutputFormat_Raw24Khz16BitMonoPcm = 2

    def __init__(self):
        self.streams = {}
        self.synths = {}
        self.operations = []
        self.calls = []
        self.condition = Condition()
        self.next_handle = 10
        self.speak_release = Event()
        self.stop_release = Event()
        self.stop_release.set()
        self.stop_wait_entered = Event()
        self.stop_start_entered = Event()
        self.result = 9
        self.speak_error = None
        self.stop_error = None
        self.released = []

    def allocate(self, pointer):
        self.next_handle += 1
        pointer[0] = self.next_handle
        return 0

    embedded_speech_config_create = allocate
    speech_config_get_property_bag = lambda self, handle, pointer: self.allocate(pointer)
    audio_stream_create_push_audio_output_stream = allocate

    def audio_config_create_audio_output_from_stream(self, pointer, stream):
        pointer[0] = stream
        return 0

    def push_audio_output_stream_set_callbacks(self, stream, context, write, close):
        self.streams[stream] = SimpleNamespace(context=context, write=write)
        return 0

    def synthesizer_create_speech_synthesizer_from_config(self, pointer, config, stream):
        self.allocate(pointer)
        number = len(self.synths) + 1
        self.synths[pointer[0]] = SimpleNamespace(stream=stream, bookmark=None,
            name=f"voice{number}", locale="en-US" if number == 1 else "fr-FR")
        return 0

    def synthesizer_get_voices_list(self, handle, text, pointer):
        pointer[0] = handle
        return 0

    def synthesis_voices_result_get_voice_num(self, handle, pointer):
        pointer[0] = 1
        return 0

    def synthesis_voices_result_get_voice_info(self, handle, index, pointer):
        pointer[0] = handle
        return 0

    def voice_info_get_name(self, handle):
        return self.synths[handle].name.encode()

    def voice_info_get_locale(self, handle):
        return self.synths[handle].locale.encode()

    def synthesizer_bookmark_reached_set_callback(self, handle, callback, context):
        self.synths[handle].bookmark = (callback, context)
        return 0

    def synthesizer_speak_ssml(self, handle, text, size, pointer):
        with self.condition:
            self.calls.append((handle, text.decode()))
            self.condition.notify_all()
        assert self.speak_release.wait(4), "Test did not release native speak"
        if self.speak_error:
            raise self.speak_error
        pointer[0] = self.result
        return 0

    def synth_result_get_reason(self, result, pointer):
        pointer[0] = result
        return 0

    def synthesizer_stop_speaking_async(self, synth, pointer):
        self.allocate(pointer)
        self.operations.append((pointer[0], synth))
        self.stop_start_entered.set()
        return 0

    def synthesizer_stop_speaking_async_wait_for(self, handle, timeout):
        self.stop_wait_entered.set()
        assert handle in [operation[0] for operation in self.operations]
        assert self.stop_release.wait(4), "Test did not release native stop"
        if self.stop_error:
            raise self.stop_error
        return 0

    def synthesizer_async_handle_release(self, handle):
        self.released.append(handle)
        return 0

    def wait_calls(self, count):
        with self.condition:
            assert self.condition.wait_for(lambda: len(self.calls) >= count, 2)

    def audio(self, data=b"\x01\x02", synth=None):
        synth = self.calls[-1][0] if synth is None else synth
        stream = self.streams[self.synths[synth].stream]
        return stream.write(stream.context, data, len(data))

    def bookmark(self, text="1", saved=None):
        callback, context = saved or self.synths[self.calls[-1][0]].bookmark
        callback(0, text, context)

    synthesizer_event_get_text = lambda self, event: event.encode()

    def __getattr__(self, name):
        if name.endswith("_release") or name in (
            "property_bag_set_string", "embedded_speech_config_add_path", "speech_config_set_audio_output_format"):
            return lambda *args: 0
        raise AttributeError(name)


class Player:
    def __init__(self):
        self.fed = []
        self.feed_entered = Event()
        self.feed_release = Event()
        self.feed_release.set()
        self.idle_entered = Event()
        self.idle_release = Event()
        self.stops = 0
        self.stop_entered = Event()
        self.stop_release = Event()
        self.stop_release.set()
        self.paused = False
        self.closed = False
        self.error = None

    def feed(self, data):
        self.feed_entered.set()
        assert self.feed_release.wait(4)
        if self.error == "feed":
            raise OSError("audio feed failed")
        self.fed.append(data)

    def idle(self):
        self.idle_entered.set()
        assert self.idle_release.wait(4)
        if self.error == "idle":
            raise OSError("audio idle failed")

    def stop(self):
        self.stops += 1
        self.stop_entered.set()
        assert self.stop_release.wait(4)
        if self.error == "stop":
            raise OSError("audio stop failed")
        self.idle_release.set()

    def pause(self, switch):
        self.paused = switch

    def close(self):
        if self.error == "close":
            raise OSError("audio close failed")
        self.closed = True


class Sonic:
    def __init__(self):
        self.error = None
        self.tail = b"\x03\x04"
        self.flush_tail = b"\x05\x06"

    def writeShort(self, samples, count):
        if self.error == "write":
            raise OSError("Sonic write failed")

    def readShort(self):
        tail, self.tail = self.tail, b""
        return tail

    def flush(self):
        if self.error == "flush":
            raise OSError("Sonic flush failed")
        self.tail = self.flush_tail


def in_thread(function):
    done, errors = Event(), []

    def run():
        try:
            function()
        except BaseException as error:
            errors.append(error)
        finally:
            done.set()

    thread = Thread(target=run, daemon=True)
    thread.start()
    return SimpleNamespace(thread=thread, done=done, errors=errors)


def load_neural(monkeypatch, tmp_path, *, rt=None, scheduler=None, voice_base=object, commands=None):
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
        def __getattr__(self, name):
            getter = getattr(type(self), "_get_" + name, None)
            if name == "availableVoices":
                return self._getAvailableVoices()
            if getter:
                return getter(self)
            raise AttributeError(name)

        def __setattr__(self, name, value):
            setter = getattr(type(self), "_set_" + name, None) if not name.startswith("_") else None
            if setter:
                setter(self, value)
            else:
                object.__setattr__(self, name, value)

        VoiceSetting = RateSetting = RateBoostSetting = PitchSetting = VolumeSetting = staticmethod(lambda: object())

    class Converter:
        def __init__(self, language):
            pass

        def convertToXml(self, commands):
            return repr((self.voice, self.rate, self.pitch, self.volume, tuple(commands)))

    class VoiceInfo:
        def __init__(self, id, name, language):
            self.id, self.name, self.language = id, name, language
            self.displayName = name

    class Notification:
        def __init__(self, notify):
            self.notify = notify

    native, player, sonic = Native(), Player(), Sonic()
    ffi = Ffi()
    ffi.lib = native
    indexes, dones, logs = [], [], []
    done_event = Event()

    def legacy_done(**kwargs):
        dones.append(kwargs["synth"])
        done_event.set()
    package("synthDrivers", ROOT / "addon/synthDrivers")
    package("synthDrivers.WorldVoice", ROOT / "addon/synthDrivers/WorldVoice")
    package("synthDrivers.WorldVoice.driver", NEURAL.parent, Voice=voice_base)
    rt = rt or load_runtime(monkeypatch, "synthDrivers.WorldVoice.runtime")
    scheduler = scheduler or load_scheduler(monkeypatch, rt)
    package("speech", ROOT)
    commands = commands or module("speech.commands", **{name: type(name, (), {}) for name in (
        "BreakCommand", "IndexCommand", "CharacterModeCommand", "LangChangeCommand", "RateCommand", "PitchCommand", "VolumeCommand")})
    monkeypatch.setitem(sys.modules, "speech.commands", commands)
    module("speechXml", SsmlConverter=Converter)
    module("configobj", ConfigObj=object)
    module("addonHandler", getRunningAddons=lambda: ())
    module("config", conf={"audio": {"outputDevice": "default"}, "speech": {"NeuralVoices": {"languages": {}}}})
    module("nvwave", WavePlayer=lambda **kwargs: player)
    module("languageHandler", getLanguage=lambda: "en_US", getLanguageDescription=lambda lang: lang)
    module("synthDriverHandler", SynthDriver=Base, VoiceInfo=VoiceInfo,
        synthIndexReached=Notification(lambda **kw: indexes.append(kw["index"])),
        synthDoneSpeaking=Notification(legacy_done))
    package("autoSettingsUtils", ROOT)
    module("autoSettingsUtils.driverSetting", BooleanDriverSetting=object, DriverSetting=object)
    module("autoSettingsUtils.utils", percentToParam=lambda percent, low, high: int(low + percent / 100 * (high - low)), StringParameterInfo=object)
    module("logHandler", log=SimpleNamespace(**{name: lambda *args, **kwargs: logs.append(args)
        for name in ("warning", "error", "exception")}))
    module("synthDrivers._sonic", initialize=lambda: None, SonicStream=lambda *args: sonic)
    monkeypatch.setattr(builtins, "_", lambda value: value, raising=False)
    package("synthDrivers.WorldVoice.driver.Neural", NEURAL)
    package("synthDrivers.WorldVoice.driver.Neural.driver", NEURAL / "driver")
    module("synthDrivers.WorldVoice.driver.Neural.driver.speechapi.speechapi_cffi", ffi=ffi)
    for name in ("synthDrivers.WorldVoice.driver.Neural.driver.speechapi",):
        monkeypatch.delitem(sys.modules, name, raising=False)
    inner = load("synthDrivers.WorldVoice.driver.Neural.driver", NEURAL / "driver/__init__.py")
    inner.__path__ = [str(NEURAL / "driver")]
    keys = []
    for number in (1, 2):
        key = tmp_path / f"voice{number}.key"
        key.write_text("fake test credential")
        keys.append((key, tmp_path))
    monkeypatch.setattr(inner.SynthDriver, "getVoiceAddons", classmethod(lambda cls: iter(keys)))
    outer = load("synthDrivers.WorldVoice.driver.Neural", NEURAL / "__init__.py")
    outer.__path__ = [str(NEURAL)]
    driver = outer.SynthDriver()
    return SimpleNamespace(driver=driver, outer=outer, inner=inner, native=native,
        ffi=ffi, player=player, sonic=sonic, rt=rt, scheduler=scheduler,
        commands=commands, indexes=indexes, dones=dones, done_event=done_event, logs=logs)


def prove_fake_quiescence(env, monkeypatch):
    """Test seam after the real stop handle path; never changes capability."""
    monkeypatch.setattr(env.driver, "_confirm_native_quiescence", lambda native: None)
