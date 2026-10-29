"""Load the real outer/inner OneCore classes and pinned NVDA Python driver.

Only Windows dependencies, SSML conversion and the audio/native boundaries are
substituted. The native fake retains the constructor-installed fixed callback.
"""

import builtins
import ctypes
import io
import sys
import wave
from threading import Condition, Event, Thread
from types import SimpleNamespace

from addon_loader import REF, ROOT, load_source
from nvda_stubs import StubModules
from runtime_harness import load_runtime, load_scheduler
from waiting import HOLD_TIMEOUT, WAIT_TIMEOUT

NVDA = REF / "nvda"
VERSION = "source-DETACHED-9ef645d"


class NativeFunction:
	def __init__(self, function=lambda *args: None):
		self.function = function

	def __call__(self, *args):
		return self.function(*args)


class Native:
	def __init__(self):
		self._name = str(NVDA / "lib/x64/nvdaHelperLocalWin10.dll")
		self.callback = None
		self.calls = []
		self.settings = []
		self.condition = Condition()
		self.terminated = False
		self.submit_error = None
		self.ocSpeech_initialize = NativeFunction(self.initialize)
		self.ocSpeech_speak = NativeFunction(self.speak)
		self.ocSpeech_terminate = NativeFunction(self.terminate)
		for name in ("Pitch", "Rate", "Volume"):
			setattr(self, "ocSpeech_get" + name, NativeFunction(lambda *args: 1.0))
			setattr(
				self,
				"ocSpeech_set" + name,
				NativeFunction(
					lambda token, value, name=name: self.settings.append((name, value.value)),
				),
			)
		self.ocSpeech_supportsProsodyOptions = NativeFunction(lambda: True)
		self.ocSpeech_supportsPunctuationSilence = NativeFunction(lambda: False)
		self.ocSpeech_getCurrentVoiceLanguage = NativeFunction(lambda token: "en-US")
		self.ocSpeech_getCurrentVoiceId = NativeFunction(lambda token: "voice")
		self.ocSpeech_setVoice = NativeFunction()
		self.ocSpeech_getVoices = NativeFunction(lambda token: "voice:en-US:Test")

	def initialize(self, callback):
		self.callback = callback
		return 123

	def speak(self, token, text):
		if self.submit_error:
			raise self.submit_error
		with self.condition:
			self.calls.append(text)
			self.condition.notify_all()

	def wait_calls(self, count):
		with self.condition:
			assert self.condition.wait_for(lambda: len(self.calls) >= count, WAIT_TIMEOUT)

	def terminate(self, token):
		self.terminated = True

	def respond(self, *, frames=8, markers="1:20000", failure=False, malformed=False):
		stream = io.BytesIO()
		with wave.open(stream, "wb") as wav:
			wav.setnchannels(1)
			wav.setsampwidth(2)
			wav.setframerate(1000)
			wav.writeframes(b"\x01\x02" * frames)
		# OneCore's fixed header includes the two-byte WAVEFORMATEX extension.
		raw = bytearray(stream.getvalue())
		raw[16:20] = (18).to_bytes(4, "little")
		raw[36:36] = b"\x00\x00"
		raw[4:8] = (len(raw) - 8).to_bytes(4, "little")
		buffer = ctypes.create_string_buffer(b"bad" if malformed else bytes(raw))
		self.callback(ctypes.addressof(buffer), 0 if failure else len(buffer) - 1, markers)


class Player:
	def __init__(self, **kwargs):
		self.__dict__.update(kwargs)
		self.fed = []
		self.sync_entered = Event()
		self.sync_release = Event()
		self.feed_entered = Event()
		self.feed_release = Event()
		self.feed_release.set()
		self.stops = 0
		self.idles = 0
		self.error = None
		self.pause_switch = False

	def open(self):
		pass

	def feed(self, data, size=None, onDone=None):
		self.feed_entered.set()
		assert self.feed_release.wait(HOLD_TIMEOUT), "Test did not release feed"
		if self.error == "feed":
			raise OSError("feed failed")
		self.fed.append(ctypes.string_at(data, size))
		if onDone:
			onDone()

	def sync(self):
		self.sync_entered.set()
		assert self.sync_release.wait(HOLD_TIMEOUT), "Test did not release sync"
		if self.error == "sync":
			raise OSError("sync failed")

	def idle(self):
		# Counts only the real player's idle; a lease that skips it leaves this unchanged.
		self.sync()
		self.idles += 1
		if self.error == "idle":
			raise OSError("idle failed")

	def stop(self):
		self.stops += 1
		self.sync_release.set()

	def pause(self, switch):
		self.pause_switch = switch


def in_thread(function):
	done = Event()
	errors = []

	def run():
		try:
			function()
		except BaseException as error:  # noqa: BLE001 - collected for the calling test to assert
			errors.append(error)
		finally:
			done.set()

	thread = Thread(target=run, daemon=True)
	thread.start()
	return SimpleNamespace(thread=thread, done=done, errors=errors)


def load_onecore(monkeypatch, *, rt=None, scheduler=None, voice_base=object, commands=None):
	stubs = StubModules(monkeypatch)
	module, package = stubs.module, stubs.package

	def load(name, path):
		return load_source(monkeypatch, name, path)

	class Base:
		def __init__(self):
			self.availableVoices = {
				"voice": SimpleNamespace(id="voice", displayName="Test", language="en_US", onecoreIndex=0),
			}
			self.availableLanguages = {"en_US"}

		def __getattr__(self, name):
			getter = getattr(type(self), "_get_" + name, None)
			if getter:
				return getter(self)
			raise AttributeError(name)

		def __setattr__(self, name, value):
			setter = getattr(type(self), "_set_" + name, None) if not name.startswith("_") else None
			if setter:
				setter(self, value)
			else:
				object.__setattr__(self, name, value)

		def terminate(self):
			pass

	class Converter:
		def __init__(self, *args):
			pass

		def convertToXml(self, commands):
			return repr(tuple(commands))

	class Notification:
		def __init__(self, notify):
			self.notify = notify

	native = Native()
	player = Player(samplesPerSec=1000)
	indexes, dones, logs = [], [], []
	package("synthDrivers", ROOT / "addon/synthDrivers")
	package("synthDrivers.WorldVoice", ROOT / "addon/synthDrivers/WorldVoice")
	package("synthDrivers.WorldVoice.driver", ROOT / "addon/synthDrivers/WorldVoice/driver", Voice=voice_base)
	rt = rt or load_runtime(monkeypatch, "synthDrivers.WorldVoice.runtime")
	scheduler = scheduler or load_scheduler(monkeypatch, rt)
	package("speech", ROOT)
	commands = commands or module(
		"speech.commands",
		**{
			name: type(name, (), {})
			for name in (
				"IndexCommand",
				"CharacterModeCommand",
				"LangChangeCommand",
				"BreakCommand",
				"PitchCommand",
				"RateCommand",
				"VolumeCommand",
				"PhonemeCommand",
			)
		},
	)
	monkeypatch.setitem(sys.modules, "speech.commands", commands)
	module("speech.types", SpeechSequence=list, SequenceItemT=object)
	module(
		"speechXml",
		SsmlConverter=Converter,
		SetAttrCommand=object,
		XmlBalancerCommand=object,
		toNvdaLang=lambda text: text.replace("-", "_"),
	)
	module("comtypes", BSTR=str)
	module("winreg")
	module("config", conf={"audio": {"outputDevice": "default"}})
	module("languageHandler", getWindowsLanguage=lambda: "en_US", getLanguage=lambda: "en")
	module("NVDAHelper", getHelperLocalWin10Dll=lambda: native)
	module("nvwave", WavePlayer=lambda **kwargs: player, __file__=str(NVDA / "source/nvwave.py"))
	module("buildVersion", version=VERSION)
	module("queueHandler", eventQueue=object(), queueFunction=lambda *args: None)
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
		isDebugForSynthDriver=lambda: False,
		findAndSetNextSynth=lambda *args: None,
		synthIndexReached=Notification(lambda **kw: indexes.append(kw["index"])),
		synthDoneSpeaking=Notification(lambda **kw: dones.append(kw["synth"])),
	)
	monkeypatch.setattr(builtins, "_", lambda value: value, raising=False)
	base = load("synthDrivers.oneCore", NVDA / "source/synthDrivers/oneCore.py")
	monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.driver.OneCore.driver", raising=False)
	outer = load(
		"synthDrivers.WorldVoice.driver.OneCore",
		ROOT / "addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py",
	)
	driver = outer.SynthDriver()
	driver.language = "en_US"
	# Seed the player so the first callback does not replace it; constructor and
	# callback remain real, and the fake matches NVDA's player boundary.
	driver._player = player
	driver._bytesPerSec = 2000
	return SimpleNamespace(
		driver=driver,
		outer=outer,
		base=base,
		native=native,
		player=player,
		rt=rt,
		scheduler=scheduler,
		indexes=indexes,
		dones=dones,
		logs=logs,
		commands=commands,
	)


# Named views of wrapper internals that tests check but no public API exposes; each private
# name is read here only. They read without a lock, as the tests did, except where they
# replaced a wait under the wrapper's condition.


def native_call(driver):
	"""The native call record the wrapper's worker has in flight, or None."""
	return driver._segmentNative


def segment_terminated(driver):
	"""Whether terminate() has set the wrapper's terminated flag."""
	with driver._segmentCondition:
		return driver._segmentTerminated


def segment_paused(driver):
	"""Whether the wrapper holds segment playback paused."""
	return driver._segmentPaused


def stop_gate_clear(driver):
	"""Whether no cancel or stop holds the wrapper's stop gate."""
	with driver._segmentCondition:
		return driver._stopGate.clear


def has_player(driver):
	"""Whether the inner driver has opened its WavePlayer."""
	return driver._player is not None


def queued_speech(driver):
	"""The inner driver's speech queue: ordinary speech and queued segment jobs."""
	return tuple(driver._queuedSpeech)


def queued_segment_jobs(driver):
	"""The segment jobs waiting in the inner driver's speech queue."""
	job = sys.modules[type(driver).__module__]._SpeechJob
	return [item for item in queued_speech(driver) if isinstance(item, job)]


def segment_worker(driver):
	"""The wrapper's worker thread that feeds the native queue, or None before it started."""
	return driver._segmentWorker
