"""Load the real SAPI5 outer driver and the pinned NVDA driver with COM and audio boundary fakes."""

import builtins
import ctypes
import ctypes.wintypes
import sys
from dataclasses import dataclass
from threading import Condition, Event, current_thread
from types import SimpleNamespace

from addon_loader import ROOT, load_source
from nvda_stubs import StubModules
from runtime_harness import load_runtime, load_scheduler


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
	stubs = StubModules(monkeypatch)
	module, package = stubs.module, stubs.package

	def load(name, path):
		return load_source(monkeypatch, name, path)

	class Base:
		@staticmethod
		def VoiceSetting():
			return SimpleNamespace(id="voice")

		@staticmethod
		def RateSetting():
			return SimpleNamespace(id="rate")

		@staticmethod
		def RateBoostSetting():
			return SimpleNamespace(id="rateBoost")

		@staticmethod
		def PitchSetting():
			return SimpleNamespace(id="pitch")

		@staticmethod
		def VolumeSetting():
			return SimpleNamespace(id="volume")

		@staticmethod
		def UseWasapiSetting():
			return SimpleNamespace(id="useWasapi")

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
	load(
		"synthDrivers.WorldVoice.runtime._segmentLifecycle",
		ROOT / "addon/synthDrivers/WorldVoice/runtime/_segmentLifecycle.py",
	)
	load(
		"synthDrivers.WorldVoice.runtime.segmentHost",
		ROOT / "addon/synthDrivers/WorldVoice/runtime/segmentHost.py",
	)
	scheduler = scheduler or load_scheduler(monkeypatch, rt)
	package("speech", ROOT)

	@dataclass
	class IndexCommand:
		index: int

	commands = commands or module(
		"speech.commands",
		IndexCommand=IndexCommand,
		**{
			name: type(name, (), {})
			for name in (
				"CharacterModeCommand",
				"LangChangeCommand",
				"BreakCommand",
				"PitchCommand",
				"RateCommand",
				"VolumeCommand",
				"PhonemeCommand",
				"SpeechCommand",
			)
		},
	)
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
		_fields_ = [
			(name, ctypes.c_ulong)
			for name in (
				"wFormatTag",
				"cbSize",
				"nChannels",
				"nSamplesPerSec",
				"wBitsPerSample",
				"nBlockAlign",
				"nAvgBytesPerSec",
			)
		]

	interfaces = {
		name: type(name, (ctypes.Structure,), {"_fields_": []})
		for name in (
			"ISpAudio",
			"ISpEventSource",
			"ISpEventSink",
			"ISpNotifySource",
			"ISpNotifySink",
			"ISpVoice",
			"ISpeechVoice",
			"SPEVENT",
		)
	}
	module(
		"comInterfaces.SpeechLib",
		GUID=lambda text: text,
		SPAUDIOSTATE=int,
		WAVEFORMATEX=WAVEFORMATEX,
		**interfaces,
	)
	comtypes = package(
		"comtypes",
		ROOT,
		COMError=OSError,
		COMObject=object,
		hresult=SimpleNamespace(S_OK=0, E_OUTOFMEMORY=1, E_UNEXPECTED=2, E_NOTIMPL=3),
	)
	comtypes.client = module("comtypes.client", CreateObject=create_native)
	module("winreg")
	module("audioDucking", AudioDucker=object, isAudioDuckingSupported=lambda: False, _isDebug=lambda: False)
	module("config", conf={"audio": {"outputDevice": "default"}})
	module("nvwave", WavePlayer=create_player, WAVE_FORMAT_PCM=1)
	module("NVDAState", _allowDeprecatedAPI=lambda: False)
	module("languageHandler", LCID_NONE=0, localeNameToWindowsLCID=lambda lang: 0x409)
	module("synthDrivers._sonic", SonicStream=Sonic, initialize=lambda: None)
	module(
		"logHandler",
		log=SimpleNamespace(
			**{
				name: lambda *args, **kwargs: logs.append(args)
				for name in ("debug", "debugWarning", "warning", "error", "exception")
			},
		),
	)
	module(
		"synthDriverHandler",
		SynthDriver=Base,
		VoiceInfo=object,
		synthIndexReached=SimpleNamespace(notify=lambda **kw: indexes.append(kw["index"])),
		synthDoneSpeaking=SimpleNamespace(notify=lambda **kw: dones.append(kw["synth"])),
	)

	# Notifications must be hashable in the real driver's supportedNotifications.
	class Notification:
		def __init__(self, callback):
			self.notify = callback

	sys.modules["synthDriverHandler"].synthIndexReached = Notification(
		lambda **kw: indexes.append(kw["index"]),
	)
	sys.modules["synthDriverHandler"].synthDoneSpeaking = Notification(lambda **kw: dones.append(kw["synth"]))
	monkeypatch.setattr(builtins, "_", lambda text: text, raising=False)
	base = load("synthDrivers.sapi5", ROOT / "ref/nvda/source/synthDrivers/sapi5.py")
	outer = load(
		"synthDrivers.WorldVoice.driver.SAPI5",
		ROOT / "addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py",
	)
	driver = outer.SynthDriver()
	return SimpleNamespace(
		driver=driver,
		native=native_instances[-1],
		player=players[-1],
		natives=native_instances,
		players=players,
		outer=outer,
		base=base,
		rt=rt,
		scheduler=scheduler,
		indexes=indexes,
		dones=dones,
		logs=logs,
		commands=commands,
	)
