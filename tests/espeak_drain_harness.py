"""Load the actual pinned NVDA eSpeak drivers with DLL/audio boundary fakes."""

import builtins
import ctypes
from dataclasses import dataclass
import importlib.util
from pathlib import Path
import sys
from threading import Condition, Event, current_thread
from types import ModuleType, SimpleNamespace

from runtime_harness import load_runtime, load_scheduler

ROOT = Path(__file__).resolve().parents[1]


class Player:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.fed = []
        self.callbacks = []
        self.idle_entered, self.idle_release = Event(), Event()
        self.feed_entered, self.feed_release = Event(), Event()
        self.feed_release.set()
        self.error = None
        self.stop_error = None
        self.stops = 0
        self.queued_bytes = 0
        self.closed = False
        self.paused = False

    def feed(self, data, size=None, onDone=None):
        self.feed_entered.set()
        assert self.feed_release.wait(3), "Test did not release feed"
        if self.error == "feed":
            raise OSError("feed failed")
        self.fed.append(size)
        self.queued_bytes += size or 0
        if onDone:
            self.callbacks.append(onDone)

    def idle(self):
        self.idle_entered.set()
        assert self.idle_release.wait(3), "Test did not release idle"
        if self.error == "idle":
            raise OSError("idle failed")
        callbacks, self.callbacks = self.callbacks, []
        for callback in callbacks:
            callback()
        self.queued_bytes = 0

    def stop(self):
        self.stops += 1
        if self.stop_error is not None:
            raise self.stop_error
        self.queued_bytes = 0
        self.callbacks.clear()
        self.idle_release.set()

    def pause(self, switch):
        self.paused = switch

    def close(self):
        self.closed = True


class NativeFunction:
    """ctypes functions allow initialization to assign signatures and errcheck."""
    def __init__(self, callback):
        self.callback = callback

    def __call__(self, *args):
        return self.callback(*args)


class Native:
    def __init__(self):
        self.condition = Condition()
        self.calls = []
        self.next_scripts = []
        self.callback = None
        self.inner = None
        self.terminated = False
        self.params = {1: 190, 2: 100, 3: 40, 4: 75}
        self.voice = None
        self.espeak_Initialize = NativeFunction(lambda *args: 22050)
        self.espeak_Info = NativeFunction(lambda *args: b"fake native boundary")
        self.espeak_SetSynthCallback = NativeFunction(self._set_callback)
        self.espeak_ng_Cancel = NativeFunction(lambda *args: 0)
        self.espeak_Synth = NativeFunction(self._synth)
        self.espeak_SetParameter = NativeFunction(self._set_parameter)
        self.espeak_GetParameter = NativeFunction(lambda param, current: self.params[param])
        self.espeak_GetCurrentVoice = NativeFunction(lambda: ctypes.pointer(self.voice))
        self.espeak_SetVoiceByName = NativeFunction(self._set_voice_name)
        self.espeak_SetVoiceByProperties = NativeFunction(lambda *args: 0)
        self.espeak_ListVoices = NativeFunction(lambda *args: ())
        self.espeak_Terminate = NativeFunction(self._terminate)

    def _set_callback(self, callback):
        self.callback = callback

    def _set_parameter(self, param, value, relative):
        self.params[param] = value
        return 0

    def _set_voice_name(self, name):
        self.voice.identifier = name
        return 0

    def _terminate(self):
        self.terminated = True
        return 0

    def _synth(self, text, *args):
        with self.condition:
            call = SimpleNamespace(text=text.decode(), thread=current_thread(),
                after_callback=Event(), return_release=Event(), returned=Event(),
                before_terminal=Event(), terminal_release=Event(),
                queued_bytes_at_entry=self.inner.player.queued_bytes,
                index_callback=self.inner.onIndexReached)
            script = self.next_scripts.pop(0) if self.next_scripts else {}
            self.calls.append(call)
            self.condition.notify_all()
        try:
            if script.get("error"):
                raise OSError("native failed")
            events = (self.inner.espeak_EVENT * 2)()
            events[0].type = self.inner.espeakEVENT_MARK
            events[0].id.name = b"7"
            events[1].type = self.inner.espeakEVENT_LIST_TERMINATED
            if not script.get("empty"):
                wav = (ctypes.c_short * 4)(1, 2, 3, 4)
                self.callback(ctypes.addressof(wav), 4, events)
            call.before_terminal.set()
            if script.get("hold_terminal"):
                assert call.terminal_release.wait(3), "Test did not release terminal callback"
            if not script.get("missing_end"):
                terminal = (self.inner.espeak_EVENT * 1)()
                self.callback(None, 0, terminal)
            call.after_callback.set()
            if script.get("auto_return"):
                call.return_release.set()
            assert call.return_release.wait(3), "Test did not release native return"
            return script.get("result", 0)
        finally:
            call.returned.set()

    def wait_calls(self, count):
        with self.condition:
            assert self.condition.wait_for(lambda: len(self.calls) >= count, 3), "No native call"
            return self.calls[count - 1]

    def release(self):
        for call in self.calls:
            call.terminal_release.set()
            call.return_release.set()


def load_espeak(monkeypatch, tmp_path, *, rt=None, scheduler=None, voice_base=object, commands=None):
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

    class BaseMeta(type):
        def __new__(meta, name, bases, attrs):
            result = super().__new__(meta, name, bases, attrs)
            for key, getter in attrs.items():
                if key.startswith("_get_"):
                    setattr(result, key[5:], property(getter, attrs.get("_set_" + key[5:])))
            return result

    class Base(metaclass=BaseMeta):
        availableLanguages = {"en-gb", "fr-fr"}
        @staticmethod
        def _paramToPercent(value, low, high): return round((value - low) * 100 / (high - low))
        @staticmethod
        def _percentToParam(value, low, high): return round(value * (high - low) / 100 + low)
        @staticmethod
        def VoiceSetting(): return SimpleNamespace(id="voice")
        @staticmethod
        def VariantSetting(): return SimpleNamespace(id="variant")
        @staticmethod
        def RateSetting(): return SimpleNamespace(id="rate")
        @staticmethod
        def RateBoostSetting(): return SimpleNamespace(id="rateBoost")
        @staticmethod
        def PitchSetting(): return SimpleNamespace(id="pitch")
        @staticmethod
        def InflectionSetting(): return SimpleNamespace(id="inflection")
        @staticmethod
        def VolumeSetting(): return SimpleNamespace(id="volume")

    package("synthDrivers", ROOT / "addon/synthDrivers")
    package("synthDrivers.WorldVoice", ROOT / "addon/synthDrivers/WorldVoice")
    package("synthDrivers.WorldVoice.driver", ROOT / "addon/synthDrivers/WorldVoice/driver", Voice=voice_base)
    rt = rt or load_runtime(monkeypatch, "synthDrivers.WorldVoice.runtime")
    scheduler = scheduler or load_scheduler(monkeypatch, rt)
    package("speech", ROOT)
    @dataclass
    class IndexCommand:
        index: int
    @dataclass
    class LangChangeCommand:
        lang: str | None
    @dataclass
    class PitchCommand:
        multiplier: float
    commands = commands or module("speech.commands", IndexCommand=IndexCommand,
        LangChangeCommand=LangChangeCommand, PitchCommand=PitchCommand,
        **{name: type(name, (), {}) for name in ("CharacterModeCommand", "BreakCommand", "RateCommand",
        "VolumeCommand", "PhonemeCommand", "SpeechCommand")})
    monkeypatch.setitem(sys.modules, "speech.commands", commands)
    module("speech.types", SpeechSequence=list)
    module("speechXml", toXmlLang=lambda lang: lang.replace("_", "-"))
    module("languageHandler", getLanguage=lambda: "en-gb", stripLocaleFromLangCode=lambda lang: lang.split("-")[0])
    logs, indexes, dones, players = [], [], [], []
    module("logHandler", log=SimpleNamespace(**{name: lambda *args, **kwargs: logs.append(args)
        for name in ("info", "debug", "debugWarning", "warning", "error", "exception")}))
    class Notification:
        def __init__(self, callback): self.notify = callback
    module("synthDriverHandler", SynthDriver=Base, VoiceInfo=object,
        synthIndexReached=Notification(lambda **kw: indexes.append(kw["index"])),
        synthDoneSpeaking=Notification(lambda **kw: dones.append(kw["synth"])))
    module("config", conf={"audio": {"outputDevice": "default"}})
    variants = tmp_path / "synthDrivers/espeak-ng-data/voices/!v"
    variants.mkdir(parents=True)
    (variants / "max").write_text("name Max\n")
    module("globalVars", appDir=str(tmp_path))
    def create_player(**kwargs):
        player = Player(**kwargs)
        players.append(player)
        return player
    module("nvwave", WavePlayer=create_player)
    monkeypatch.setattr(builtins, "_", lambda text: text, raising=False)
    monkeypatch.setattr(builtins, "pgettext", lambda context, text: text, raising=False)
    native = Native()
    monkeypatch.setattr(ctypes.cdll, "LoadLibrary", lambda path: native)
    inner = load("synthDrivers._espeak", ROOT / "ref/nvda/source/synthDrivers/_espeak.py")
    native.inner = inner
    native.voice = inner.espeak_VOICE(name=b"English", languages=b"\x02en-gb", identifier=b"en-gb")
    base = load("synthDrivers.espeak", ROOT / "ref/nvda/source/synthDrivers/espeak.py")
    outer = load("synthDrivers.WorldVoice.driver.Espeak", ROOT / "addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py")
    driver = outer.SynthDriver()
    return SimpleNamespace(driver=driver, player=players[-1], native=native, inner=inner,
        outer=outer, base=base, rt=rt, scheduler=scheduler, indexes=indexes, dones=dones, logs=logs,
        commands=commands)


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
        assert events.condition.wait_for(lambda: bool(events), 3), "No terminal event delivered"
        assert len(events) == 1
        return events[0]


def finish(env):
    env.player.stop_error = None
    env.player.feed_release.set()
    env.player.idle_release.set()
    env.native.release()
    env.driver.terminate()
