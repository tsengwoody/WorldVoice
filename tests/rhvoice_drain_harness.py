"""Load the installed RHVoice wrapper with real inner code and fake external edges."""

import ctypes
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import Condition, Event, Thread, current_thread
from types import SimpleNamespace

from nvda_stubs import StubModules
from runtime_harness import load_runtime, load_scheduler

ROOT = Path(__file__).resolve().parents[1]


class Player:
	def __init__(self, **kwargs):
		self.fed = []
		self.callbacks = []
		self.retained_callbacks = []
		self.feed_entered = Event()
		self.second_feed_entered = Event()
		self.feed_release = Event()
		self.feed_release.set()
		self.feed_calls = 0
		self.idle_entered = Event()
		self.second_idle_entered = Event()
		self.third_idle_entered = Event()
		self.second_idle_completed = Event()
		self.idle_release = Event()
		self.idle_release.set()
		self.idle_count = 0
		self.block_idle_number = None
		self.threaded_callbacks = False
		self.error = None
		self.stop_error = None
		self.stops = 0
		self.stop_entered = Event()
		self.closed = False

	def feed(self, data, onDone=None):
		self.feed_calls += 1
		self.feed_entered.set()
		if self.feed_calls == 2:
			self.second_feed_entered.set()
		assert self.feed_release.wait(3), "test did not release feed"
		if self.error == "feed":
			raise OSError("feed failed")
		self.fed.append(data)
		if onDone:
			self.callbacks.append(onDone)
			self.retained_callbacks.append(onDone)

	def idle(self):
		self.idle_count += 1
		self.idle_entered.set()
		if self.idle_count == 2:
			self.second_idle_entered.set()
		if self.idle_count == 3:
			self.third_idle_entered.set()
		if self.idle_count == self.block_idle_number:
			assert self.idle_release.wait(3), "test did not release idle"
		if self.error == "idle":
			raise OSError("idle failed")
		callbacks, self.callbacks = self.callbacks, []
		for callback in callbacks:
			if self.threaded_callbacks:
				callback_thread = Thread(target=callback, daemon=True)
				callback_thread.start()
				callback_thread.join()
			else:
				callback()
		if self.idle_count == 2:
			self.second_idle_completed.set()

	def stop(self):
		self.stops += 1
		self.stop_entered.set()
		if self.stop_error:
			raise self.stop_error
		self.callbacks.clear()

	def close(self):
		self.closed = True

	def pause(self, switch):
		pass


class NativeFunction:
	def __init__(self, function):
		self.function = function

	def __call__(self, *args):
		return self.function(*args)


class Native:
	def __init__(self):
		self.condition = Condition()
		self.calls = []
		self.scripts = []
		self.callbacks = None
		self.messages = {}
		self.next_message = 1
		self.deleted = []
		self.engine_deleted = False
		self.RHVoice_get_version = NativeFunction(lambda: b"fake")
		self.RHVoice_new_tts_engine = NativeFunction(self._new_engine)
		self.RHVoice_delete_tts_engine = NativeFunction(self._delete_engine)
		self.RHVoice_get_number_of_voices = NativeFunction(lambda engine: 1)
		self.RHVoice_get_voices = NativeFunction(
			lambda engine: [
				SimpleNamespace(
					language=b"en",
					name=b"Alice",
					country=b"US",
				),
			],
		)
		self.RHVoice_get_number_of_voice_profiles = NativeFunction(lambda engine: 1)
		self.RHVoice_get_voice_profiles = NativeFunction(lambda engine: [b"Alice"])
		self.RHVoice_are_languages_compatible = NativeFunction(lambda *args: 1)
		self.RHVoice_new_message = NativeFunction(self._new_message)
		self.RHVoice_delete_message = NativeFunction(self.deleted.append)
		self.RHVoice_speak = NativeFunction(self._speak)

	def _new_engine(self, params):
		self.callbacks = params._obj.callbacks
		return 1

	def _delete_engine(self, engine):
		self.engine_deleted = True

	def _new_message(self, engine, text, length, kind, params, user_data):
		message = self.next_message
		self.next_message += 1
		options = params._obj
		self.messages[message] = (
			text,
			user_data,
			SimpleNamespace(
				voice_profile=options.voice_profile,
				rate=options.absolute_rate,
				pitch=options.absolute_pitch,
				volume=options.absolute_volume,
				boost=options.relative_rate,
				flags=options.flags,
			),
		)
		return message

	def _speak(self, message):
		text, user_data, options = self.messages[message]
		script = self.scripts.pop(0) if self.scripts else {}
		call = SimpleNamespace(
			text=text,
			user_data=user_data,
			options=options,
			thread=current_thread(),
			done=Event(),
			return_release=Event(),
			returned=Event(),
		)
		with self.condition:
			self.calls.append(call)
			self.condition.notify_all()
		try:
			if script.get("raise_native"):
				raise OSError("native failed")
			if script.get("before_callbacks"):
				script["before_callbacks"]()
			self.callbacks.set_sample_rate(22050, user_data)
			samples = (ctypes.c_short * 2)(1, 2)
			self.callbacks.play_speech(samples, 2, user_data)
			self.callbacks.process_mark(b"7", user_data)
			if script.get("async_callback"):
				script["async_callback"](self.callbacks, user_data)
			if not script.get("missing_done"):
				self.callbacks.done(user_data)
				call.done.set()
			if script.get("auto_return"):
				call.return_release.set()
			assert call.return_release.wait(3), "test did not release native return"
			return script.get("result", 1)
		finally:
			call.returned.set()

	def wait_call(self, number=1):
		with self.condition:
			assert self.condition.wait_for(lambda: len(self.calls) >= number, 3), "no native call"
			return self.calls[number - 1]

	def release(self):
		for call in self.calls:
			call.return_release.set()


class Events(list):
	def __init__(self):
		super().__init__()
		self.condition = Condition()

	def append(self, event):
		with self.condition:
			super().append(event)
			self.condition.notify_all()

	def wait_one(self):
		with self.condition:
			assert self.condition.wait_for(lambda: bool(self), 3), "no segment event"
			assert len(self) == 1
			return self[0]


def load_rhvoice(monkeypatch, tmp_path):
	stubs = StubModules(monkeypatch)
	module, package = stubs.module, stubs.package

	def load(name, path):
		spec = importlib.util.spec_from_file_location(name, path)
		item = importlib.util.module_from_spec(spec)
		monkeypatch.setitem(sys.modules, name, item)
		spec.loader.exec_module(item)
		return item

	class BaseMeta(type):
		def __new__(meta, name, bases, attrs):
			result = super().__new__(meta, name, bases, attrs)
			for key, getter in attrs.items():
				if key.startswith("_get_"):
					setattr(result, key[5:], property(getter, attrs.get("_set_" + key[5:])))
			return result

	class Base(metaclass=BaseMeta):
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

	package("synthDrivers", ROOT / "addon/synthDrivers")
	package("synthDrivers.WorldVoice", ROOT / "addon/synthDrivers/WorldVoice")
	package("synthDrivers.WorldVoice.driver", ROOT / "addon/synthDrivers/WorldVoice/driver", Voice=object)
	rt = load_runtime(monkeypatch, "synthDrivers.WorldVoice.runtime")
	scheduler = load_scheduler(monkeypatch, rt)
	package("speech", ROOT)

	@dataclass
	class IndexCommand:
		index: int

	commands = module(
		"speech.commands",
		IndexCommand=IndexCommand,
		**{
			name: type(name, (), {})
			for name in (
				"CharacterModeCommand",
				"LangChangeCommand",
				"PitchCommand",
				"RateCommand",
				"VolumeCommand",
			)
		},
	)

	class SsmlConverter:
		def __init__(self, defaultLanguage):
			pass

		def convertToXml(self, sequence):
			return f"<speak>{sequence[0]}</speak>"

	module("speechXml", SsmlConverter=SsmlConverter)
	module("config", conf={"audio": {"outputDevice": "default"}})
	module("globalVars", appArgs=SimpleNamespace(configPath=str(tmp_path)))
	module("buildVersion", version_year=2026)
	module("addonAPIVersion", CURRENT=1)
	module("addonHandler", getRunningAddons=list)
	module("languageHandler", getLanguage=lambda: "en_US")
	logs, indexes, dones, players = [], [], [], []
	module(
		"logHandler",
		log=SimpleNamespace(
			**{name: lambda *args, **kwargs: logs.append(args) for name in ("info", "error", "debugWarning")},
		),
	)

	class Notification:
		def __init__(self, callback):
			self.notify = callback

	module(
		"synthDriverHandler",
		SynthDriver=Base,
		VoiceInfo=object,
		synthIndexReached=Notification(lambda **kw: indexes.append(kw["index"])),
		synthDoneSpeaking=Notification(lambda **kw: dones.append(kw["synth"])),
	)
	module("nvwave", WavePlayer=lambda **kw: players.append(Player(**kw)) or players[-1])
	native = Native()
	monkeypatch.setattr(ctypes, "CDLL", lambda path: native)
	inner = load(
		"synthDrivers.WorldVoice.driver.RHVoice.driver",
		ROOT / "addon/synthDrivers/WorldVoice/driver/RHVoice/driver/__init__.py",
	)
	outer = load(
		"synthDrivers.WorldVoice.driver.RHVoice",
		ROOT / "addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py",
	)
	driver = outer.SynthDriver()
	return SimpleNamespace(
		driver=driver,
		outer=outer,
		inner=inner,
		rt=rt,
		scheduler=scheduler,
		commands=commands,
		native=native,
		players=players,
		indexes=indexes,
		dones=dones,
		logs=logs,
	)


def speak(env, segment=1, text="hello", sink=None):
	events = Events()
	token = env.scheduler.CancellationToken()
	context = env.rt.models.PlaybackContext(object(), segment)
	env.driver.speak_segment(
		(text, env.commands.IndexCommand(7)),
		token,
		context=context,
		on_event=sink or events.append,
	)
	return token, context, events


def finish(env):
	env.native.release()
	for player in env.players:
		player.feed_release.set()
		player.idle_release.set()
		player.stop_error = None
	env.driver.terminate()
