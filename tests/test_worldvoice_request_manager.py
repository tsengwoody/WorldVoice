import importlib.util
import sys
import threading
import types
from concurrent.futures import CancelledError
from pathlib import Path

import pytest


class EventStub:
	def __init__(self, on_notify=None):
		self.handlers = []
		self.on_notify = on_notify

	def register(self, handler):
		self.handlers.append(handler)

	def unregister(self, handler):
		self.handlers.remove(handler)

	def notify(self, **kwargs):
		if self.on_notify:
			self.on_notify(**kwargs)
		for handler in tuple(self.handlers):
			handler(**kwargs)


class Buses:
	def __init__(self):
		self.owner = object()
		self.current = self.owner
		self.outer_done = []
		self.outer_indexes = []
		self.done_seen = threading.Event()
		self.index_seen = threading.Event()
		self.before_get_synth = None
		self.done = EventStub(self._record_done)
		self.index = EventStub(self._record_index)

	def get_synth(self):
		if self.before_get_synth:
			self.before_get_synth()
		return self.current

	def _record_done(self, synth):
		if synth is self.owner:
			self.outer_done.append(synth)
			self.done_seen.set()

	def _record_index(self, synth, index):
		if synth is self.owner:
			self.outer_indexes.append(index)
			self.index_seen.set()

	def wait_for_outer_done(self, timeout):
		assert self.done_seen.wait(timeout)
		return self.outer_done


@pytest.fixture
def buses():
	return Buses()


@pytest.fixture
def task_module(monkeypatch, buses):
	log = types.SimpleNamespace(debug=lambda *a, **k: None, error=lambda *a, **k: None)
	monkeypatch.setitem(sys.modules, "logHandler", types.SimpleNamespace(log=log))
	monkeypatch.setitem(
		sys.modules,
		"synthDriverHandler",
		types.SimpleNamespace(
			getSynth=buses.get_synth,
			synthDoneSpeaking=buses.done,
			synthIndexReached=buses.index,
		),
	)
	path = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice/taskManager.py"
	spec = importlib.util.spec_from_file_location("worldvoice_task_manager_under_test", path)
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, spec.name, module)
	spec.loader.exec_module(module)
	return module


@pytest.fixture
def manager(task_module, buses):
	instance = task_module.TaskManager(owner=buses.owner)
	yield instance
	instance.shutdown()


@pytest.fixture
def voice():
	class Core:
		def __init__(self):
			self.spoken = []
			self.cancel_count = 0

		def speak(self, text):
			self.spoken.append(text)

		def cancel(self):
			self.cancel_count += 1

	class Voice:
		def __init__(self):
			self.core = Core()

		def active(self):
			pass

	return Voice()


@pytest.fixture
def blocking_voice(voice):
	voice.entered = threading.Event()
	voice.stop_entered = threading.Event()
	voice.release_stop = threading.Event()
	voice.new_entered = threading.Event()

	def start_old():
		voice.entered.set()

	def start_new():
		voice.new_entered.set()

	def cancel():
		voice.stop_entered.set()
		assert voice.release_stop.wait(1)

	voice.start_old = start_old
	voice.start_new = start_new
	voice.core.cancel = cancel
	return voice


@pytest.fixture
def two_voices():
	class Voice:
		def __init__(self):
			self.core = types.SimpleNamespace(cancel=lambda: None)
			self.entered = threading.Event()

		def active(self):
			pass

		def speak_and_notify(self, event):
			event.notify(synth=self.core)

		def start_async(self):
			self.entered.set()

		def finish_and_notify_twice(self, event):
			event.notify(synth=self.core)
			event.notify(synth=self.core)

	return Voice(), Voice()


def test_synchronous_done_and_duplicate_notification_complete_once(manager, buses, two_voices):
	first, second = two_voices
	request = manager.new_request()
	manager.append_speech(request, first, lambda: first.speak_and_notify(buses.done))
	manager.append_speech(request, second, second.start_async)
	assert manager.submit_request(request)
	assert second.entered.wait(1)
	assert buses.outer_done == []
	second.finish_and_notify_twice(buses.done)
	assert buses.wait_for_outer_done(1) == [manager.owner]


def test_wrong_core_event_cannot_release_current_segment(manager, buses, two_voices):
	voice, _ = two_voices
	request = manager.new_request()
	manager.append_speech(request, voice, voice.start_async)
	manager.submit_request(request)
	assert voice.entered.wait(1)
	buses.done.notify(synth=object())
	buses.index.notify(synth=object(), index=7)
	assert buses.outer_done == []
	assert buses.outer_indexes == []
	assert not request.tasks[0].future.done()
	buses.done.notify(synth=voice.core)
	assert buses.wait_for_outer_done(1) == [manager.owner]


def test_old_epoch_events_are_discarded(manager, buses, two_voices):
	old_voice, new_voice = two_voices
	old = manager.new_request()
	manager.append_speech(old, old_voice, old_voice.start_async)
	assert manager.submit_request(old)
	assert old_voice.entered.wait(1)
	manager.cancel([old_voice])
	new = manager.new_request()
	manager.append_speech(new, new_voice, new_voice.start_async)
	assert manager.submit_request(new)
	assert new_voice.entered.wait(1)
	buses.done.notify(synth=old_voice.core)
	buses.index.notify(synth=old_voice.core, index=9)
	assert buses.outer_done == []
	assert buses.outer_indexes == []
	assert not new.tasks[0].future.done()
	buses.done.notify(synth=new_voice.core)
	assert buses.wait_for_outer_done(1) == [manager.owner]


def test_valid_index_is_forwarded_once_and_owner_event_is_ignored(manager, buses, two_voices):
	voice, _ = two_voices
	request = manager.new_request()
	manager.append_speech(request, voice, voice.start_async)
	assert manager.submit_request(request)
	assert voice.entered.wait(1)
	buses.index.notify(synth=voice.core, index=7)
	assert buses.index_seen.wait(1)
	assert buses.outer_indexes == [7]
	buses.index.notify(synth=voice.core, index=7)
	buses.done.notify(synth=buses.owner)
	assert buses.outer_indexes == [7]
	assert not request.tasks[0].future.done()
	buses.done.notify(synth=voice.core)
	assert buses.wait_for_outer_done(1) == [manager.owner]


def test_index_after_core_done_is_not_forwarded(manager, buses, two_voices):
	voice, _ = two_voices

	def speak():
		buses.done.notify(synth=voice.core)
		buses.index.notify(synth=voice.core, index=11)

	request = manager.new_request()
	manager.append_speech(request, voice, speak)
	assert manager.submit_request(request)
	assert buses.wait_for_outer_done(1) == [manager.owner]
	assert buses.outer_indexes == []


def test_trailing_break_delays_completion(manager, buses, two_voices):
	voice, _ = two_voices
	request = manager.new_request()
	manager.append_speech(request, voice, lambda: voice.speak_and_notify(buses.done))
	break_entered = threading.Event()
	break_release = threading.Event()
	manager.append_break(request, voice, 60)
	request.token.wait = lambda seconds: (break_entered.set(), break_release.wait(1))
	assert manager.submit_request(request)
	assert break_entered.wait(1)
	assert buses.outer_done == []
	break_release.set()
	assert buses.wait_for_outer_done(1) == [manager.owner]


def test_cancelled_request_does_not_emit_done(manager, buses, two_voices):
	voice, _ = two_voices
	request = manager.new_request()
	manager.append_speech(request, voice, voice.start_async)
	assert manager.submit_request(request)
	assert voice.entered.wait(1)
	manager.cancel([voice])
	buses.done.notify(synth=voice.core)
	assert request.tasks[0].future.cancelled() or request.token.is_cancelled()
	assert buses.outer_done == []


def test_cancel_after_completion_acceptance_suppresses_old_done(manager, buses, two_voices):
	voice, _ = two_voices
	accepted = threading.Event()
	release_delivery = threading.Event()
	request = manager.new_request()
	manager.append_speech(request, voice, voice.start_async)
	assert manager.submit_request(request)
	assert voice.entered.wait(1)

	def block_delivery():
		accepted.set()
		assert release_delivery.wait(2)

	buses.before_get_synth = block_delivery
	try:
		buses.done.notify(synth=voice.core)
		assert accepted.wait(1)
		assert request.done_sent
		old_epoch = request.epoch
		manager.cancel([voice])
		assert manager._epoch == old_epoch + 1
	finally:
		release_delivery.set()
		buses.before_get_synth = None
	manager._q.join()
	assert buses.outer_done == []


def test_cancel_after_index_acceptance_suppresses_old_index(manager, buses, two_voices):
	voice, _ = two_voices
	accepted = threading.Event()
	release_delivery = threading.Event()
	request = manager.new_request()
	manager.append_speech(request, voice, voice.start_async)
	assert manager.submit_request(request)
	assert voice.entered.wait(1)

	def block_delivery():
		accepted.set()
		assert release_delivery.wait(2)

	buses.before_get_synth = block_delivery
	index_thread = threading.Thread(target=buses.index.notify, kwargs={"synth": voice.core, "index": 23})
	index_thread.start()
	try:
		assert accepted.wait(1)
		with manager._state_cond:
			assert 23 in manager._current_indexes
		old_epoch = request.epoch
		manager.cancel([voice])
		assert manager._epoch == old_epoch + 1
	finally:
		release_delivery.set()
		buses.before_get_synth = None
		index_thread.join(1)
	assert not index_thread.is_alive()
	assert buses.outer_indexes == []


@pytest.mark.parametrize("failure_at", ["active", "speak"])
def test_failure_stops_core_and_completes_once(manager, buses, two_voices, failure_at):
	voice, other = two_voices
	stops = []
	voice.core.cancel = lambda: stops.append("stopped")

	def fail():
		raise ValueError(failure_at)

	if failure_at == "active":
		voice.active = fail
		run = voice.start_async
	else:
		run = fail
	request = manager.new_request()
	manager.append_speech(request, voice, run)
	manager.append_speech(request, other, other.start_async)
	assert manager.submit_request(request)
	with pytest.raises(ValueError, match=failure_at):
		request.tasks[0].future.result(timeout=1)
	assert buses.wait_for_outer_done(1) == [manager.owner]
	assert request.failed
	assert stops == ["stopped"]
	with pytest.raises(CancelledError):
		request.tasks[1].future.result(timeout=1)
	assert request.tasks[1].future.cancelled()
	assert not other.entered.is_set()


def test_pause_current_uses_valid_voice_snapshot(manager, buses, two_voices):
	voice, _ = two_voices
	calls = []
	voice.pause = lambda: calls.append("pause")
	voice.resume = lambda: calls.append("resume")
	request = manager.new_request()
	manager.append_speech(request, voice, voice.start_async)
	assert manager.submit_request(request)
	assert voice.entered.wait(1)
	manager.pause_current(True)
	manager.pause_current(False)
	assert calls == ["pause", "resume"]
	manager.cancel([voice])
	manager.pause_current(True)
	assert calls == ["pause", "resume"]


def test_handlers_unregister_on_shutdown(task_module, buses):
	manager = task_module.TaskManager(owner=buses.owner)
	assert len(buses.done.handlers) == 1
	assert len(buses.index.handlers) == 1
	manager.shutdown()
	assert buses.done.handlers == []
	assert buses.index.handlers == []
	buses.done.notify(synth=object())
	buses.index.notify(synth=object(), index=99)
	assert buses.outer_done == []
	assert buses.outer_indexes == []


def test_cancel_during_first_active_rejects_stale_ve_events_before_neural_and_ve(manager, buses):
	active_entered = threading.Event()
	release_active = threading.Event()
	neural_entered = threading.Event()
	ve_entered = threading.Event()
	raw_events = []

	class Core:
		def __init__(self):
			self.spoken = []
			self.spoken_after_cancel = []
			self.cancelled = False

		def speak(self, text):
			(self.spoken_after_cancel if self.cancelled else self.spoken).append(text)

		def cancel(self):
			self.cancelled = True

	stale_ve_core = Core()
	neural_core = Core()
	new_ve_core = Core()
	old_voice = types.SimpleNamespace(
		core=stale_ve_core,
		active=lambda: (active_entered.set(), release_active.wait(1)),
	)
	neural_voice = types.SimpleNamespace(core=neural_core, active=lambda: None)
	new_ve_voice = types.SimpleNamespace(core=new_ve_core, active=lambda: None)
	old_request = manager.new_request()
	manager.append_speech(old_request, old_voice, lambda: stale_ve_core.speak("old VE"))
	assert manager.submit_request(old_request)
	assert active_entered.wait(1)
	manager.cancel([old_voice])
	assert old_request.token.is_cancelled()
	release_active.set()
	new_request = manager.new_request()
	manager.append_speech(new_request, neural_voice, neural_entered.set)
	manager.append_speech(new_request, new_ve_voice, ve_entered.set)
	assert manager.submit_request(new_request)
	assert neural_entered.wait(1)
	with manager._state_cond:
		neural_done_event = manager._current_done_event
	assert neural_done_event is not None
	for kind, value in (("index", 9), ("done", None)):
		raw_events.append((kind, stale_ve_core, value))
		if kind == "index":
			buses.index.notify(synth=stale_ve_core, index=value)
		else:
			buses.done.notify(synth=stale_ve_core)
	# Core notifications dispatch synchronously; a wrongly accepted stale done sets this event.
	assert not neural_done_event.is_set()
	assert not ve_entered.is_set()
	assert not new_request.tasks[0].future.done()
	assert buses.outer_indexes == []
	assert buses.outer_done == []
	buses.index.notify(synth=neural_core, index=12)
	buses.done.notify(synth=neural_core)
	assert ve_entered.wait(1)
	buses.index.notify(synth=new_ve_core, index=13)
	buses.done.notify(synth=new_ve_core)
	assert buses.wait_for_outer_done(1) == [manager.owner]
	assert raw_events == [("index", stale_ve_core, 9), ("done", stale_ve_core, None)]
	assert stale_ve_core.spoken_after_cancel == []
	assert stale_ve_core.spoken == []
	assert buses.outer_indexes == [12, 13]
	assert buses.outer_done.count(manager.owner) == 1


def test_cancel_before_synchronous_core_done_discards_old_completion(manager, buses):
	native_entered = threading.Event()
	release_native = threading.Event()
	old_core = types.SimpleNamespace(cancel=lambda: None)
	old_voice = types.SimpleNamespace(core=old_core, active=lambda: None)
	raw_done = []

	def speak_then_done():
		native_entered.set()
		assert release_native.wait(1)
		raw_done.append(old_core)
		buses.done.notify(synth=old_core)

	old_request = manager.new_request()
	manager.append_speech(old_request, old_voice, speak_then_done)
	assert manager.submit_request(old_request)
	assert native_entered.wait(1)
	manager.cancel([old_voice])
	assert old_request.token.is_cancelled()
	release_native.set()
	with pytest.raises(CancelledError):
		old_request.tasks[0].future.result(timeout=1)
	# The future can settle before cleanup and external event emission finish.
	manager._q.join()
	assert raw_done == [old_core]
	assert buses.outer_done == []
	assert buses.outer_indexes == []


def test_cancelled_request_built_before_submit_is_not_enqueued(manager, voice):
	request = manager.new_request()
	manager.append_speech(request, voice, lambda: voice.core.speak(["old"]))
	manager.cancel([voice])
	assert manager.submit_request(request) is False
	assert voice.core.spoken == []


def test_new_request_waits_for_old_stop(manager, blocking_voice):
	old = manager.new_request()
	manager.append_speech(old, blocking_voice, blocking_voice.start_old)
	assert manager.submit_request(old)
	assert blocking_voice.entered.wait(1)
	stopper = threading.Thread(target=manager.cancel, args=([blocking_voice],))
	stopper.start()
	assert blocking_voice.stop_entered.wait(1)
	new = manager.new_request()
	manager.append_speech(new, blocking_voice, blocking_voice.start_new)
	assert manager.submit_request(new)
	assert not blocking_voice.new_entered.wait(0.05)
	blocking_voice.release_stop.set()
	stopper.join(1)
	assert not stopper.is_alive()
	assert blocking_voice.new_entered.wait(1)


def test_two_concurrent_cancels_must_both_finish_before_new_speech(manager, voice, buses):
	entered = [threading.Event(), threading.Event()]
	release = [threading.Event(), threading.Event()]
	lock = threading.Lock()
	count = 0
	old_entered = threading.Event()
	new_entered = threading.Event()
	old = manager.new_request()
	manager.append_speech(old, voice, old_entered.set)
	assert manager.submit_request(old)
	assert old_entered.wait(1)

	def cancel_core():
		nonlocal count
		with lock:
			index = count
			count += 1
		entered[index].set()
		assert release[index].wait(1)

	voice.core.cancel = cancel_core
	stoppers = [threading.Thread(target=manager.cancel, args=([voice],)) for _ in range(2)]
	for stopper in stoppers:
		stopper.start()
	assert all(event.wait(1) for event in entered)
	assert old.token.is_cancelled()
	request = manager.new_request()
	manager.append_speech(request, voice, new_entered.set)
	assert manager.submit_request(request)
	release[0].set()
	stoppers[0].join(1)
	assert not stoppers[0].is_alive()
	assert not new_entered.wait(0.05)
	release[1].set()
	stoppers[1].join(1)
	assert not stoppers[1].is_alive()
	assert new_entered.wait(1)
	assert buses.outer_done == []
	buses.done.notify(synth=voice.core)
	assert buses.wait_for_outer_done(1) == [manager.owner]


def test_cancel_wakes_break_token_and_allows_new_request(manager, voice):
	old = manager.new_request()
	waiting = threading.Event()
	original_wait = old.token.wait

	def observed_wait(seconds):
		waiting.set()
		return original_wait(seconds)

	old.token.wait = observed_wait
	manager.append_break(old, voice, 60)
	assert manager.submit_request(old)
	assert waiting.wait(1)
	manager.cancel([voice])
	new_entered = threading.Event()
	new = manager.new_request()
	manager.append_speech(new, voice, new_entered.set)
	assert manager.submit_request(new)
	assert new_entered.wait(1)


def test_cancel_stops_shared_core_only_once(manager, voice):
	other_voice = types.SimpleNamespace(core=voice.core, active=lambda: None)
	manager.cancel([voice, other_voice, voice])
	assert voice.core.cancel_count == 1


def test_cancel_stops_current_core_before_other_cores(manager, voice):
	entered = threading.Event()
	stopped = []
	voice.core.cancel = lambda: stopped.append("current")
	other_core = types.SimpleNamespace(cancel=lambda: stopped.append("other"))
	other_voice = types.SimpleNamespace(core=other_core)
	request = manager.new_request()
	manager.append_speech(request, voice, entered.set)
	assert manager.submit_request(request)
	assert entered.wait(1)
	manager.cancel([other_voice, voice])
	assert stopped == ["current", "other"]


def test_cancel_during_active_skips_core_speak(manager, voice):
	active_entered = threading.Event()
	release_active = threading.Event()
	completed = threading.Event()
	voice.active = lambda: (active_entered.set(), release_active.wait(1))
	request = manager.new_request()
	manager.append_speech(request, voice, lambda: voice.core.speak(["late"]))
	request.tasks[0].future.add_done_callback(lambda _: completed.set())
	assert manager.submit_request(request)
	assert active_entered.wait(1)
	manager.cancel([voice])
	release_active.set()
	assert completed.wait(1)
	assert request.tasks[0].future.cancelled()
	assert voice.core.spoken == []


def test_cancel_during_speak_stops_core_again_after_speak_returns(manager, voice):
	entered = threading.Event()
	release_speak = threading.Event()

	def blocking_speak(text):
		entered.set()
		assert release_speak.wait(1)
		voice.core.spoken.append(text)

	voice.core.speak = blocking_speak
	request = manager.new_request()
	manager.append_speech(request, voice, lambda: voice.core.speak(["old"]))
	completed = threading.Event()
	request.tasks[0].future.add_done_callback(lambda _: completed.set())
	assert manager.submit_request(request)
	assert entered.wait(1)
	manager.cancel([voice])
	release_speak.set()
	assert completed.wait(1)
	assert request.tasks[0].future.cancelled()
	assert voice.core.cancel_count == 2


def test_pending_speech_is_cancelled_but_new_request_runs(manager, voice, buses):
	first_entered = threading.Event()
	old_entered = threading.Event()
	new_entered = threading.Event()
	first = manager.new_request()
	manager.append_speech(first, voice, first_entered.set)
	assert manager.submit_request(first)
	assert first_entered.wait(1)
	old = manager.new_request()
	manager.append_speech(old, voice, old_entered.set)
	assert manager.submit_request(old)
	old_future = old.tasks[0].future
	old_done = threading.Event()
	old_future.add_done_callback(lambda _: old_done.set())
	manager.cancel([voice])
	new = manager.new_request()
	manager.append_speech(new, voice, new_entered.set)
	assert manager.submit_request(new)
	new_future = new.tasks[0].future
	assert old_done.wait(1)
	assert old_future.cancelled()
	assert new_entered.wait(1)
	assert not old_entered.is_set()
	assert not new_future.cancelled()
	buses.done.notify(synth=voice.core)
	assert new_future.result(timeout=1) is True


def test_failed_speech_marks_request_failed(manager, voice):
	def fail():
		raise ValueError("core failure")

	request = manager.new_request()
	manager.append_speech(request, voice, fail)
	assert manager.submit_request(request)
	with pytest.raises(ValueError, match="core failure"):
		request.tasks[0].future.result(timeout=1)
	assert request.failed


@pytest.mark.parametrize("engine", ["VE", "Cerence"])
def test_direct_wrapper_stop_mid_speech_lets_next_segment_run(manager, buses, monkeypatch, engine):
	from worldvoice_cancel_wrapper_harness import load_real_driver_with_native_stubs

	harness = load_real_driver_with_native_stubs(monkeypatch, engine)
	monkeypatch.setattr(harness.original_driver, "synthDoneSpeaking", buses.done)
	monkeypatch.setattr(harness.original_driver, "synthIndexReached", buses.index)
	core = harness.new_core()
	core.voiceInstance = "voice"
	core.language = "en"
	core._normalization = "OFF"
	spoken = []
	second_spoken = threading.Event()

	def native(instance, text):
		spoken.append(text)
		if text == "first":
			# Like SynthDriver._set_voice(): stop the core without cancelling the request.
			core.cancel()
		else:
			second_spoken.set()

	monkeypatch.setattr(harness.native, "processText2Speech", native)
	voice = types.SimpleNamespace(core=core, active=lambda: None)
	request = manager.new_request()
	for text in ("first", "second"):
		manager.append_speech(request, voice,
			lambda text=text: core.speak([text], cancellationToken=request.token))
	assert manager.submit_request(request)
	assert second_spoken.wait(1)
	assert buses.wait_for_outer_done(1) == [manager.owner]
	assert spoken == ["first", "second"]
