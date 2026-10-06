"""Exercise the real SAPI5 outer and pinned NVDA driver at COM/audio boundaries."""

import builtins
import ctypes
import ctypes.wintypes
import importlib
import sys
from dataclasses import dataclass
from threading import Condition, Event, Thread, current_thread
from types import SimpleNamespace

import pytest
from addon_loader import ROOT, load_source
from nvda_stubs import StubModules
from runtime_harness import load_runtime, load_scheduler
from waiting import eventually, stays_false, stays_unset


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
	env.driver.speak_segment(
		commands or ("hello", env.commands.IndexCommand(7)),
		token,
		context=context,
		on_event=sink or events.append,
	)
	return token, context, events


def wait_event(events):
	with events.condition:
		assert events.condition.wait_for(lambda: bool(events), 2), "No terminal event delivered"
		assert len(events) == 1
		return events[0]


def test_sapi5_wasapi_shared_lifecycle_waits_for_endstream_pcm_and_idle(env):
	_, context, events = speak(env)
	env.native.wait_calls(1)
	native = env.driver._segmentHost.current()
	lifecycle = importlib.import_module(env.rt.package.__name__ + "._segmentLifecycle")
	assert isinstance(native.operation, lifecycle.SegmentOperation)
	env.player.feed_release.clear()
	pcm = Thread(
		target=lambda: env.native.audio.ISequentialStream_RemoteWrite(None, None, 8, None),
		daemon=True,
	)
	pcm.start()
	assert env.player.feed_entered.wait(1)
	env.native.end()
	assert events == [] and not env.player.idle_entered.is_set()
	env.player.feed_release.set()
	pcm.join(2)
	assert not pcm.is_alive()
	assert env.player.idle_entered.wait(1)
	assert events == []
	env.player.idle_release.set()
	event = wait_event(events)
	assert event.source_id is context.source_id and event.segment_id == 17
	assert event.kind is env.rt.models.EventKind.SEGMENT_DRAINED
	assert env.player.fed == [6, 0]


def test_sapi5_shared_cancel_blocks_request_handoff(env):
	_, _, old_events = speak(env)
	env.native.wait_calls(1)
	env.player.feed_release.clear()
	pcm = Thread(
		target=lambda: env.native.audio.ISequentialStream_RemoteWrite(None, None, 8, None),
		daemon=True,
	)
	pcm.start()
	assert env.player.feed_entered.wait(1)
	env.driver.cancel()
	_, context, next_events = speak(env, segment=18, commands=("next", env.commands.IndexCommand(9)))
	env.native.end(1)
	assert len(env.native.calls) == 1 and next_events == []
	env.player.feed_release.set()
	pcm.join(2)
	assert not pcm.is_alive()
	env.native.wait_calls(2)
	env.native.end(1)
	assert next_events == [] and env.indexes == []
	env.player.idle_release.set()
	env.native.end(2)
	event = wait_event(next_events)
	assert event.source_id is context.source_id and event.segment_id == 18
	assert env.indexes == [9] and old_events == []


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
		except Exception as error:  # noqa: BLE001 - collected and asserted in the test thread
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


@pytest.mark.parametrize("audio_mode,expected", [("wasapi", True), ("winmm", False), ("legacy", False)])
def test_wasapi_profile_enabled_legacy_profiles_unsupported(env, audio_mode, expected):
	result = env.driver.get_segment_drain_support(
		nvda_version="source-DETACHED-9ef645d",
		audio_mode=audio_mode,
	)
	assert result.supported is expected
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


def test_cancel_context_queued_behind_ordinary_speech_retires(env):
	env.driver.speak(("ordinary",))
	env.native.wait_calls(1)
	_, _, old_events = speak(env)
	env.driver.cancel()
	env.native.wait_purge()
	_, _, successor = speak(env, segment=19)
	env.native.wait_calls(2)
	env.native.end(2)
	assert wait_event(successor).segment_id == 19
	assert old_events == []


def test_token_cancel_context_queued_behind_ordinary_speech_retires(env, monkeypatch):
	env.driver.speak(("ordinary",))
	env.native.wait_calls(1)
	admitted = Event()
	submit = env.driver._segmentHost.submit_native

	def observed_submit(operation, commands):
		submit(operation, commands)
		admitted.set()

	monkeypatch.setattr(env.driver._segmentHost, "submit_native", observed_submit)
	token, _, old_events = speak(env)
	assert admitted.wait(1)
	token.cancel()
	env.player.idle_release.set()
	env.native.end(1)
	_, _, successor = speak(env, segment=19)
	env.native.wait_calls(2)
	env.native.end(2)
	assert wait_event(successor).segment_id == 19
	assert old_events == []


def test_cancel_stops_player_while_final_idle_is_blocked(env, monkeypatch):
	entered, stop_called = Event(), Event()
	idle = env.player.idle
	stop = env.player.stop

	def blocked_idle():
		entered.set()
		env.player.idle_release.wait()
		return idle()

	def observed_stop():
		stop_called.set()
		return stop()

	monkeypatch.setattr(env.player, "idle", blocked_idle)
	monkeypatch.setattr(env.player, "stop", observed_stop)
	_, _, events = speak(env)
	env.native.wait_calls(1)
	env.native.end()
	assert entered.wait(1)
	finished = Event()
	cancellation = Thread(target=lambda: (env.driver.cancel(), finished.set()), daemon=True)
	cancellation.start()
	try:
		assert stop_called.wait(1), "Cancel could not stop the player during idle"
	finally:
		env.player.idle_release.set()
		cancellation.join(2)
	assert finished.is_set() and events == []


def test_old_endstream_before_new_speak_returns_cannot_bind_successor(env, monkeypatch):
	_, _, first_events = speak(env)
	env.native.wait_calls(1)
	env.player.idle_release.set()
	env.native.end(1)
	assert wait_event(first_events).segment_id == 17
	speak_native = env.native.Speak
	injected, release = Event(), Event()

	def delayed_speak(text, flags):
		stream = speak_native(text, flags)
		if text is not None and stream == 2:
			env.native.end(1)
			injected.set()
			assert release.wait(2)
		return stream

	monkeypatch.setattr(env.native, "Speak", delayed_speak)
	_, context, successor = speak(env, segment=18)
	assert injected.wait(1)
	try:
		assert successor == []
	finally:
		release.set()
	env.native.end(2)
	event = wait_event(successor)
	assert event.source_id is context.source_id and event.segment_id == 18
	assert event.kind is env.rt.models.EventKind.SEGMENT_DRAINED


def test_cancel_during_terminal_commit_allows_successor_after_commit(env, monkeypatch):
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
	cancelled = Event()
	cancel_thread = Thread(target=lambda: (env.driver.cancel(), cancelled.set()), daemon=True)
	cancel_thread.start()
	stays_unset(cancelled)
	release.set()
	cancel_thread.join(2)
	assert cancelled.is_set()
	env.native.wait_purge()
	_, _, successor = speak(env, segment=18)
	env.native.wait_calls(2)
	env.native.end(2)
	assert wait_event(successor).segment_id == 18
	assert len(events) <= 1


def test_cancel_waits_for_admitted_feed_final_stop_before_successor(env):
	_, _, old_events = speak(env)
	env.native.wait_calls(1)
	env.player.feed_release.clear()
	failures = []

	def write():
		try:
			env.native.audio.ISequentialStream_RemoteWrite(None, None, 8, None)
		except Exception as error:  # noqa: BLE001 - collected and asserted in the test thread
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


def test_accepted_successor_receives_failure_after_playback_fault(env, monkeypatch):
	real_barrier = env.driver._segmentHost.wait_playback_drained

	def failed_barrier(operation):
		real_barrier(operation)
		raise RuntimeError("SAPI5 playback barrier failed")

	monkeypatch.setattr(env.driver._segmentHost, "wait_playback_drained", failed_barrier)
	_, _first, old_events = speak(env)
	env.native.wait_calls(1)
	_, successor, next_events = speak(env, segment=18)
	env.player.idle_release.set()
	env.native.end(1)
	assert wait_event(old_events).kind is env.rt.models.EventKind.SEGMENT_FAILED
	rejected = wait_event(next_events)
	assert (rejected.kind, rejected.source_id, rejected.segment_id) == (
		env.rt.models.EventKind.SEGMENT_FAILED,
		successor.source_id,
		18,
	)
	assert len(env.native.calls) == 1
	assert all(
		operation.work.context is not successor
		for operation in env.driver._segmentHost._lifecycle._operations
	)


def test_idle_failure_purges_before_queued_successor(env):
	_, _, failed = speak(env)
	_, _, successor = speak(env, segment=18)
	env.native.wait_calls(1)
	env.player.error = "idle"
	env.player.idle_release.set()
	env.native.end()
	assert wait_event(failed).kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert env.native.purges == 1
	env.player.error = None
	env.native.wait_calls(2)
	env.native.end(2)
	assert wait_event(successor).kind is env.rt.models.EventKind.SEGMENT_DRAINED


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
	callback = Thread(
		target=lambda: env.native.audio.ISequentialStream_RemoteWrite(None, None, 8, None),
		daemon=True,
	)
	callback.start()
	assert env.player.feed_entered.wait(1)
	stopped = Event()
	termination = Thread(target=lambda: (env.driver.terminate(), stopped.set()), daemon=True)
	termination.start()
	stays_unset(stopped)
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
	stays_unset(env.player.idle_entered)
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
		except Exception as error:  # noqa: BLE001 - collected and asserted in the test thread
			failures.append(error)

	callback_thread = Thread(target=write, daemon=True)
	callback_thread.start()
	assert admitted.wait(1)
	env.player.idle_release.set()
	env.native.end()
	try:
		stays_unset(env.player.idle_entered, message="Idle overtook an admitted PCM feed")
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
		except Exception as error:  # noqa: BLE001 - collected and asserted in the test thread
			failures.append(error)

	callback = Thread(target=write_pcm, daemon=True)
	callback.start()
	assert entered.wait(1)
	env.native.end()
	env.player.idle_release.set()
	try:
		stays_unset(env.player.idle_entered, message="Idle overtook Sonic processing")
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
	event = SimpleNamespace(
		eEventId=env.base._SPEventEnum.END_INPUT_STREAM,
		ulStreamNum=1,
		ullAudioStreamOffset=0,
	)
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


def test_admitted_old_end_callback_cannot_complete_reloaded_successor(env, monkeypatch):
	_, _, old_events = speak(env)
	env.native.wait_calls(1)
	old_sink = env.native.sink
	admitted, release = Event(), Event()
	lookup = old_sink._native

	def blocked_lookup(stream):
		result = lookup(stream)
		admitted.set()
		assert release.wait(2)
		return result

	monkeypatch.setattr(old_sink, "_native", blocked_lookup)
	errors = []

	def old_end():
		try:
			old_sink.EndStream(1, 0)
		except Exception as error:  # noqa: BLE001 - collected and asserted in the test thread
			errors.append(error)

	callback = Thread(target=old_end, daemon=True)
	callback.start()
	assert admitted.wait(1)
	env.driver.voice = "voice"
	native, player = env.natives[-1], env.players[-1]
	_, _, events = speak(env, segment=18)
	native.wait_calls(1)
	release.set()
	callback.join(2)
	assert not callback.is_alive() and errors == []
	stays_false(events.condition, lambda: bool(events), message="Old end completed replacement work")
	assert old_events == []
	player.idle_release.set()
	native.end()
	assert wait_event(events).kind is env.rt.models.EventKind.SEGMENT_DRAINED


def test_voice_reload_retires_ordinary_pcm_callback_before_replacing_audio(env, monkeypatch):
	env.driver.speak(("ordinary", env.commands.IndexCommand(11)))
	env.native.wait_calls(1)
	old_audio, old_sonic = env.native.audio, env.driver.sonicStream
	admitted, release = Event(), Event()
	original_write = env.base.SynthDriverAudioStream.ISequentialStream_RemoteWrite

	def blocked_write(audio, *args):
		if audio is old_audio:
			admitted.set()
			assert release.wait(2)
		return original_write(audio, *args)

	monkeypatch.setattr(env.base.SynthDriverAudioStream, "ISequentialStream_RemoteWrite", blocked_write)
	errors = []

	def write_pcm():
		try:
			old_audio.ISequentialStream_RemoteWrite(None, None, 8, None)
		except Exception as error:  # noqa: BLE001 - collected and asserted in the test thread
			errors.append(error)

	callback = Thread(target=write_pcm, daemon=True)
	callback.start()
	assert admitted.wait(1)
	reloaded = Event()

	def reload():
		try:
			env.driver.voice = "voice"
		except Exception as error:  # noqa: BLE001 - collected and asserted in the test thread
			errors.append(error)
		finally:
			reloaded.set()

	reload_thread = Thread(target=reload, daemon=True)
	reload_thread.start()
	try:
		stays_unset(reloaded, message="Reload replaced audio before ordinary PCM callback retired")
		assert env.driver.sonicStream is old_sonic
	finally:
		release.set()
		callback.join(2)
		reload_thread.join(2)
	assert not callback.is_alive() and not reload_thread.is_alive() and errors == []
	native, player = env.natives[-1], env.players[-1]
	_, _, events = speak(env, segment=18)
	native.wait_calls(1)
	assert player.fed == []
	player.idle_release.set()
	native.end()
	assert wait_event(events).kind is env.rt.models.EventKind.SEGMENT_DRAINED
	assert player.fed == [6]


def test_cancelled_ordinary_pcm_feed_stops_again_before_successor_admission(env, monkeypatch):
	env.driver.speak(("ordinary", env.commands.IndexCommand(11)))
	env.native.wait_calls(1)
	admitted, release = Event(), Event()
	feed = env.player.feed
	callback = None
	failures = []

	def blocked_feed(data, size=None, onDone=None):
		if current_thread() is callback:
			admitted.set()
			assert release.wait(2)
		return feed(data, size, onDone)

	monkeypatch.setattr(env.player, "feed", blocked_feed)

	def write_pcm():
		try:
			env.native.audio.ISequentialStream_RemoteWrite(None, None, 8, None)
		except Exception as error:  # noqa: BLE001 - collected and asserted in the test thread
			failures.append(error)

	callback = Thread(target=write_pcm, daemon=True)
	callback.start()
	assert admitted.wait(1)
	env.driver.cancel()
	stops_after_cancel = env.player.stops
	_, _, events = speak(env, segment=18, commands=("next", env.commands.IndexCommand(9)))
	try:
		assert len(env.native.calls) == 1
	finally:
		release.set()
		callback.join(2)
	assert not callback.is_alive() and failures == []
	env.native.wait_calls(2)
	assert env.player.stops > stops_after_cancel, (
		"Cancelled ordinary feed restarted audio after the final stop"
	)
	assert [tuple(bookmarks) for bookmarks in env.driver._bookmarkLists] == [(9,)]
	assert env.driver.sonicStream.tail == []
	env.driver.sonicStream.tail = [4]
	env.native.end(2)
	assert wait_event(events).kind is env.rt.models.EventKind.SEGMENT_DRAINED
	assert env.indexes == [9]
	assert env.dones == []


def test_ordinary_com_failure_purges_and_rejects_queued_successor_before_stale_pcm(env):
	env.driver.speak(("ordinary", env.commands.IndexCommand(11)))
	env.native.wait_calls(1)
	_, context, events = speak(env, segment=18, commands=("successor", env.commands.IndexCommand(9)))
	old_audio = env.native.audio
	env.player.error = "feed"
	with pytest.raises(OSError, match="feed failed"):
		old_audio.ISequentialStream_RemoteWrite(None, None, 8, None)
	event = wait_event(events)
	assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert event.source_id is context.source_id and event.segment_id == 18
	assert env.native.purges == 1
	assert len(env.native.calls) == 1, "Successor entered the shared audio stream after ordinary failure"
	env.player.error = None
	env.driver.sonicStream.tail = [1, 2, 3]
	before = tuple(env.player.fed)
	old_audio.ISequentialStream_RemoteWrite(None, None, 8, None)
	assert tuple(env.player.fed) == before, "Old-stream PCM reached the successor player"
	assert env.dones == []


def test_ordinary_speak_fails_fast_after_cancel_purge_fault_even_if_purge_recovers(env):
	env.driver.speak(("ordinary",))
	env.native.wait_calls(1)
	env.native.purge_error = True
	env.driver.cancel()
	env.driver._thread.join(2)
	assert not env.driver._thread.is_alive()
	env.native.purge_error = None
	with pytest.raises(OSError, match="purge failed"):
		env.driver.speak(("new ordinary",))
	assert len(env.native.calls) == 1
	assert len(env.driver._speakRequests) == 0
	assert env.dones == []


def test_ordinary_speech_waits_for_contextual_final_idle(env, monkeypatch):
	# Parity probe for the VE/Cerence ordinary-speech ownership finding: the
	# WASAPI worker keeps the shared player through the contextual final idle.
	entries = []
	original_speak = env.native.Speak

	def recording_speak(text, flags):
		if text is not None:
			entries.append(env.player.idle_release.is_set())
		return original_speak(text, flags)

	monkeypatch.setattr(env.native, "Speak", recording_speak)
	_, context, events = speak(env)
	env.native.wait_calls(1)
	env.native.end()
	assert env.player.idle_entered.wait(1)
	env.driver.speak(("ordinary", env.commands.IndexCommand(11)))
	assert len(env.native.calls) == 1, "Ordinary speech entered native during the final idle"
	assert len(env.driver._speakRequests) == 1
	assert events == []
	env.player.idle_release.set()
	event = wait_event(events)
	env.native.wait_calls(2)
	assert entries == [False, True]
	env.native.end(2)
	eventually(lambda: env.dones)
	assert env.dones == [env.driver]
	assert event.kind is env.rt.models.EventKind.SEGMENT_DRAINED
	assert (event.source_id, event.segment_id) == (context.source_id, context.segment_id)
	assert env.indexes == [7, 11]


def test_completed_ordinary_speech_does_not_stop_the_player(env):
	# Ordinary requests prove only their end marker and processing; the parent
	# owns their queue-empty idle. Requiring more would stop every utterance.
	env.player.idle_release.set()
	env.driver.speak(("first", env.commands.IndexCommand(7)))
	env.native.wait_calls(1)
	env.native.end()
	assert env.player.idle_entered.wait(1)
	env.driver.speak(("second", env.commands.IndexCommand(9)))
	env.native.wait_calls(2)
	env.native.end(2)
	eventually(lambda: len(env.dones) == 2)
	assert env.dones == [env.driver, env.driver]
	assert env.indexes == [7, 9]
	assert env.player.stops == 0


def test_submit_failure_before_binding_leaves_the_lifecycle_usable(env, monkeypatch):
	# The record is abandoned before submit binds its SAPI5 data; the
	# lifecycle's stop must not turn that into a permanent fault.
	real_speak = env.outer.BaseSynthDriver.speak
	calls = []

	def failing_speak(driver, commands):
		calls.append(commands)
		if len(calls) == 1:
			raise OSError("xml conversion failed")
		return real_speak(driver, commands)

	monkeypatch.setattr(env.outer.BaseSynthDriver, "speak", failing_speak)
	_, _, failed = speak(env)
	assert wait_event(failed).kind is env.rt.models.EventKind.SEGMENT_FAILED
	host = env.driver._segmentHost
	assert host._lifecycle.wait_idle()
	assert host._lifecycle.fault is None
	_, _, successor = speak(env, segment=18)
	env.player.idle_release.set()
	env.native.wait_calls(1)
	env.native.end(1)
	assert wait_event(successor).kind is env.rt.models.EventKind.SEGMENT_DRAINED


def test_hook_fault_after_binding_does_not_strand_the_worker(monkeypatch):
	"""C2: a lifecycle hook that fails after the native request is bound."""
	env = load_sapi5(monkeypatch)
	hooks = env.driver._segmentHost
	real_boundary = hooks.wait_native_boundary

	def failing_boundary(operation):
		real_boundary(operation)
		raise RuntimeError("hook failed after binding")

	monkeypatch.setattr(hooks, "wait_native_boundary", failing_boundary)
	try:
		_, _, events = speak(env)
		env.native.wait_calls(1)
		env.player.idle_release.set()
		env.native.end()
		assert wait_event(events).kind is env.rt.models.EventKind.SEGMENT_FAILED
		ordinary = Thread(target=lambda: env.driver.speak(("ordinary",)), daemon=True)
		ordinary.start()
		with env.native.condition:
			reached = env.native.condition.wait_for(lambda: len(env.native.calls) >= 2, 1)
		assert reached, "ordinary speech never reached native after the hook fault"
		env.native.end(2)
		terminated = Thread(target=env.driver.terminate, daemon=True)
		terminated.start()
		terminated.join(2)
		assert not terminated.is_alive(), "terminate() hung on the stranded worker"
	finally:
		for player in env.players:
			player.feed_release.set()
			player.idle_release.set()
		env.driver.terminate()


def test_cancel_player_stop_failure_latches_and_rejects_speech(env):
	env.player.stop_error = True
	with pytest.raises(OSError):
		env.driver.cancel()
	env.player.stop_error = None
	assert str(env.driver._segmentHost.control_error) == "stop failed"
	with pytest.raises(OSError, match="stop failed"):
		env.driver.speak(["after"])


def test_worker_stop_failure_latches_until_a_voice_reload(env):
	env.player.stop_error = True
	with pytest.raises(OSError):
		env.driver._stopThread()
	env.player.stop_error = None
	assert str(env.driver._segmentHost.control_error) == "stop failed"
	env.driver.voice = "voice"
	assert env.driver._segmentHost.control_error is None
	native, player = env.natives[-1], env.players[-1]
	player.idle_release.set()
	_, _, events = speak(env, segment=18)
	native.wait_calls(1)
	native.end()
	assert wait_event(events).segment_id == 18


def test_stop_failure_after_an_invalidated_feed_latches(env):
	_, _, _first = speak(env)
	env.native.wait_calls(1)
	env.player.feed_release.clear()
	failures = []

	def write_pcm():
		try:
			env.native.audio.ISequentialStream_RemoteWrite(None, None, 8, None)
		except Exception as error:  # noqa: BLE001 - collected and asserted in the test thread
			failures.append(error)

	callback = Thread(target=write_pcm, daemon=True)
	env.player.feed_entered.clear()
	callback.start()
	assert env.player.feed_entered.wait(2)
	env.driver.cancel()
	# The admitted feed now returns into an invalid record; its final stop fails.
	env.player.stop_error = True
	env.player.feed_release.set()
	callback.join(2)
	env.player.stop_error = None
	assert not callback.is_alive()
	assert [str(error) for error in failures] == ["stop failed"]
	assert str(env.driver._segmentHost.control_error) == "stop failed"
	_, _, successor = speak(env, segment=18)
	assert wait_event(successor).kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert len(env.native.calls) == 1


def test_strategy_stop_player_without_a_wasapi_player_does_nothing(env):
	strategy, host, player = env.driver._segmentHost._strategy, env.driver._segmentHost, env.driver.player
	stopped = []
	try:
		env.driver.player = None
		strategy.stop_player(host)
		env.driver.player = SimpleNamespace(stop=lambda: stopped.append(True))
		strategy.stop_player(host)
	finally:
		env.driver.player = player
	assert stopped == [True]


def test_segment_feed_admits_the_record_it_read(env, monkeypatch):
	from contextlib import contextmanager

	host = env.driver._segmentHost
	stale = object()
	asked = []

	@contextmanager
	def consumer(record=None, **options):
		asked.append(record)
		yield None

	monkeypatch.setattr(host, "current", lambda: stale)
	monkeypatch.setattr(host, "consumer", consumer)
	assert env.driver.player.feed(b"pcm", 3) is None
	assert asked == [stale]
