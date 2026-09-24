import importlib.util
import sys
import threading
import types
from pathlib import Path

import pytest


class EventStub:
	def __init__(self):
		self.handlers = []

	def register(self, handler):
		self.handlers.append(handler)

	def unregister(self, handler):
		self.handlers.remove(handler)

	def notify(self, **kwargs):
		for handler in tuple(self.handlers):
			handler(**kwargs)


@pytest.fixture
def task_module(monkeypatch):
	log = types.SimpleNamespace(debug=lambda *a, **k: None, error=lambda *a, **k: None)
	monkeypatch.setitem(sys.modules, "logHandler", types.SimpleNamespace(log=log))
	monkeypatch.setitem(
		sys.modules,
		"synthDriverHandler",
		types.SimpleNamespace(
			getSynth=lambda: None,
			synthDoneSpeaking=EventStub(),
			synthIndexReached=EventStub(),
		),
	)
	path = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice/taskManager.py"
	spec = importlib.util.spec_from_file_location("worldvoice_task_manager_under_test", path)
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, spec.name, module)
	spec.loader.exec_module(module)
	return module


@pytest.fixture
def manager(task_module):
	instance = task_module.TaskManager()
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


def test_two_concurrent_cancels_must_both_finish_before_new_speech(manager, voice):
	entered = [threading.Event(), threading.Event()]
	release = [threading.Event(), threading.Event()]
	lock = threading.Lock()
	count = 0
	new_entered = threading.Event()

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


def test_legacy_pending_speech_is_cancelled_but_new_speech_runs(manager, voice):
	first_entered = threading.Event()
	old_entered = threading.Event()
	new_entered = threading.Event()
	manager.add_speak_task(voice, first_entered.set)
	assert first_entered.wait(1)
	old_future = manager.add_speak_task(voice, old_entered.set)
	old_done = threading.Event()
	old_future.add_done_callback(lambda _: old_done.set())
	manager.cancel([voice])
	new_future = manager.add_speak_task(voice, new_entered.set)
	assert old_done.wait(1)
	assert old_future.cancelled()
	assert new_entered.wait(1)
	assert not old_entered.is_set()
	assert not new_future.cancelled()


def test_failed_speech_marks_request_failed(manager, voice):
	def fail():
		raise ValueError("core failure")

	request = manager.new_request()
	manager.append_speech(request, voice, fail)
	assert manager.submit_request(request)
	with pytest.raises(ValueError, match="core failure"):
		request.tasks[0].future.result(timeout=1)
	assert request.failed
