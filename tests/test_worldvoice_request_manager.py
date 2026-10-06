import importlib
import importlib.util
import sys
import threading
import types
from concurrent.futures import CancelledError
from pathlib import Path

import pytest
from addon_loader import alias_package
from runtime_harness import accepted_indexes
from waiting import HOLD_TIMEOUT, WAIT_TIMEOUT, stays_unset


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

	def wait_for_outer_done(self):
		assert self.done_seen.wait(WAIT_TIMEOUT)
		return self.outer_done


@pytest.fixture
def buses():
	return Buses()


@pytest.fixture
def task_module(monkeypatch, buses):
	package_name = "worldvoice_task_manager_under_test"
	root = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice"
	for name in tuple(sys.modules):
		if name.startswith(package_name + "."):
			monkeypatch.delitem(sys.modules, name)
	alias_package(monkeypatch, package_name, root)
	module = importlib.import_module(package_name + ".runtime.scheduler")
	bridge_module = importlib.import_module(package_name + ".nvdaEventBridge")
	module.test_bridge_class = bridge_module.NvdaEventBridge
	return module


def make_manager(task_module, buses):
	bridge = task_module.test_bridge_class(
		buses.owner,
		done_event=buses.done,
		index_event=buses.index,
		get_synth=buses.get_synth,
	)
	instance = task_module.TaskManager(output=bridge)
	bridge.start(instance.on_event, batch_handler=instance.on_events)
	# Test composition owns the event subscriptions and test port registry.
	instance.test_bridge = bridge
	instance.test_ports = {}
	instance.owner = buses.owner
	return instance


@pytest.fixture
def manager(task_module, buses):
	instance = make_manager(task_module, buses)
	yield instance
	instance.shutdown()
	instance.test_bridge.close()


def port_for(manager, voice):
	"""Bind a test playback boundary; production scheduler never sees Voice/core."""
	identity = id(voice.core)
	entry = manager.test_ports.get(identity)
	if entry is None:
		source_id = object()
		manager.test_bridge.bind(voice.core, source_id)
		manager.test_ports[identity] = source_id
	else:
		source_id = entry

	class Port:
		def activate(self, key):
			return voice.active()

		def speak(self, commands, token, *, context=None):
			commands[0]()

		def finish_segment(self, context):
			pass

		def cancel(self):
			voice.core.cancel()

		def pause(self, switch):
			(voice.pause if switch else voice.resume)()

	port = Port()
	port.source_id = source_id
	models = importlib.import_module(manager.__class__.__module__.rsplit(".", 1)[0] + ".models")
	port.completion = models.CompletionContract()
	return port


def append_speech(manager, request, voice, run):
	return manager.append_speech(request, port_for(manager, voice), "Fake:a", (run,))


def append_break(manager, request, voice, seconds):
	return manager.append_break(request, seconds)


def cancel(manager, voices=()):
	return manager.cancel([port_for(manager, voice) for voice in voices])


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
	append_speech(manager, request, first, lambda: first.speak_and_notify(buses.done))
	append_speech(manager, request, second, second.start_async)
	assert manager.submit_request(request)
	assert second.entered.wait(WAIT_TIMEOUT)
	assert buses.outer_done == []
	second.finish_and_notify_twice(buses.done)
	assert buses.wait_for_outer_done() == [manager.owner]


def test_wrong_core_event_cannot_release_current_segment(manager, buses, two_voices):
	voice, _ = two_voices
	request = manager.new_request()
	append_speech(manager, request, voice, voice.start_async)
	manager.submit_request(request)
	assert voice.entered.wait(WAIT_TIMEOUT)
	buses.done.notify(synth=object())
	buses.index.notify(synth=object(), index=7)
	assert buses.outer_done == []
	assert buses.outer_indexes == []
	assert not request.tasks[0].future.done()
	buses.done.notify(synth=voice.core)
	assert buses.wait_for_outer_done() == [manager.owner]


def test_old_epoch_events_are_discarded(manager, buses, two_voices):
	old_voice, new_voice = two_voices
	old = manager.new_request()
	append_speech(manager, old, old_voice, old_voice.start_async)
	assert manager.submit_request(old)
	assert old_voice.entered.wait(WAIT_TIMEOUT)
	cancel(manager, [old_voice])
	new = manager.new_request()
	append_speech(manager, new, new_voice, new_voice.start_async)
	assert manager.submit_request(new)
	assert new_voice.entered.wait(WAIT_TIMEOUT)
	buses.done.notify(synth=old_voice.core)
	buses.index.notify(synth=old_voice.core, index=9)
	assert buses.outer_done == []
	assert buses.outer_indexes == []
	assert not new.tasks[0].future.done()
	buses.done.notify(synth=new_voice.core)
	assert buses.wait_for_outer_done() == [manager.owner]


def test_valid_index_is_forwarded_once_and_owner_event_is_ignored(manager, buses, two_voices):
	voice, _ = two_voices
	request = manager.new_request()
	append_speech(manager, request, voice, voice.start_async)
	assert manager.submit_request(request)
	assert voice.entered.wait(WAIT_TIMEOUT)
	buses.index.notify(synth=voice.core, index=7)
	assert buses.index_seen.wait(WAIT_TIMEOUT)
	assert buses.outer_indexes == [7]
	buses.index.notify(synth=voice.core, index=7)
	buses.done.notify(synth=buses.owner)
	assert buses.outer_indexes == [7]
	assert not request.tasks[0].future.done()
	buses.done.notify(synth=voice.core)
	assert buses.wait_for_outer_done() == [manager.owner]


def test_index_after_core_done_is_not_forwarded(manager, buses, two_voices):
	voice, _ = two_voices

	def speak():
		buses.done.notify(synth=voice.core)
		buses.index.notify(synth=voice.core, index=11)

	request = manager.new_request()
	append_speech(manager, request, voice, speak)
	assert manager.submit_request(request)
	assert buses.wait_for_outer_done() == [manager.owner]
	assert buses.outer_indexes == []


def test_trailing_break_delays_completion(manager, buses, two_voices):
	voice, _ = two_voices
	request = manager.new_request()
	append_speech(manager, request, voice, lambda: voice.speak_and_notify(buses.done))
	break_entered = threading.Event()
	break_release = threading.Event()
	append_break(manager, request, voice, 60)
	request.token.wait = lambda seconds: (break_entered.set(), break_release.wait(HOLD_TIMEOUT))
	assert manager.submit_request(request)
	assert break_entered.wait(WAIT_TIMEOUT)
	assert buses.outer_done == []
	break_release.set()
	assert buses.wait_for_outer_done() == [manager.owner]


def test_cancelled_request_does_not_emit_done(manager, buses, two_voices):
	voice, _ = two_voices
	request = manager.new_request()
	append_speech(manager, request, voice, voice.start_async)
	assert manager.submit_request(request)
	assert voice.entered.wait(WAIT_TIMEOUT)
	cancel(manager, [voice])
	buses.done.notify(synth=voice.core)
	assert request.tasks[0].future.cancelled() or request.token.is_cancelled()
	assert buses.outer_done == []


def test_cancel_after_completion_acceptance_suppresses_old_done(manager, buses, two_voices):
	voice, _ = two_voices
	accepted = threading.Event()
	release_delivery = threading.Event()
	request = manager.new_request()
	append_speech(manager, request, voice, voice.start_async)
	assert manager.submit_request(request)
	assert voice.entered.wait(WAIT_TIMEOUT)

	def block_delivery():
		accepted.set()
		assert release_delivery.wait(HOLD_TIMEOUT)

	original_delivery = manager._deliver_done
	manager._deliver_done = lambda request: (block_delivery(), original_delivery(request))
	try:
		buses.done.notify(synth=voice.core)
		assert accepted.wait(WAIT_TIMEOUT)
		assert request.done_sent
		old_epoch = request.epoch
		cancel(manager, [voice])
		# Cancel starts a new epoch: requests made after it belong to that epoch.
		assert manager.new_request().epoch == old_epoch + 1
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
	append_speech(manager, request, voice, voice.start_async)
	assert manager.submit_request(request)
	assert voice.entered.wait(WAIT_TIMEOUT)

	def block_delivery():
		accepted.set()
		assert release_delivery.wait(HOLD_TIMEOUT)

	original_delivery = manager._deliver_index
	manager._deliver_index = lambda *args: (block_delivery(), original_delivery(*args))
	index_thread = threading.Thread(target=buses.index.notify, kwargs={"synth": voice.core, "index": 23})
	index_thread.start()
	try:
		assert accepted.wait(WAIT_TIMEOUT)
		assert 23 in accepted_indexes(manager)
		old_epoch = request.epoch
		# Event batches serialize cancellation; direct token cancellation
		# still exercises the output validity check before delivery.
		request.token.cancel()
	finally:
		release_delivery.set()
		buses.before_get_synth = None
		index_thread.join(1)
	cancel(manager, [voice])
	assert manager.new_request().epoch == old_epoch + 1
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
	append_speech(manager, request, voice, run)
	append_speech(manager, request, other, other.start_async)
	assert manager.submit_request(request)
	with pytest.raises(ValueError, match=failure_at):
		request.tasks[0].future.result(timeout=WAIT_TIMEOUT)
	assert buses.wait_for_outer_done() == [manager.owner]
	assert request.state.value == "failed"
	assert stops == ["stopped"]
	with pytest.raises(CancelledError):
		request.tasks[1].future.result(timeout=WAIT_TIMEOUT)
	assert request.tasks[1].future.cancelled()
	assert not other.entered.is_set()


def test_pause_current_uses_valid_voice_snapshot(manager, buses, two_voices):
	voice, _ = two_voices
	calls = []
	voice.pause = lambda: calls.append("pause")
	voice.resume = lambda: calls.append("resume")
	request = manager.new_request()
	append_speech(manager, request, voice, voice.start_async)
	assert manager.submit_request(request)
	assert voice.entered.wait(WAIT_TIMEOUT)
	manager.pause_current(True)
	manager.pause_current(False)
	assert calls == ["pause", "resume"]
	cancel(manager, [voice])
	manager.pause_current(True)
	assert calls == ["pause", "resume"]


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
		active=lambda: (active_entered.set(), release_active.wait(HOLD_TIMEOUT)),
	)
	neural_voice = types.SimpleNamespace(core=neural_core, active=lambda: None)
	new_ve_voice = types.SimpleNamespace(core=new_ve_core, active=lambda: None)
	old_request = manager.new_request()
	append_speech(manager, old_request, old_voice, lambda: stale_ve_core.speak("old VE"))
	assert manager.submit_request(old_request)
	assert active_entered.wait(WAIT_TIMEOUT)
	cancel(manager, [old_voice])
	assert old_request.token.is_cancelled()
	release_active.set()
	new_request = manager.new_request()
	append_speech(manager, new_request, neural_voice, neural_entered.set)
	append_speech(manager, new_request, new_ve_voice, ve_entered.set)
	assert manager.submit_request(new_request)
	assert neural_entered.wait(WAIT_TIMEOUT)
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
	assert ve_entered.wait(WAIT_TIMEOUT)
	buses.index.notify(synth=new_ve_core, index=13)
	buses.done.notify(synth=new_ve_core)
	assert buses.wait_for_outer_done() == [manager.owner]
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
		assert release_native.wait(HOLD_TIMEOUT)
		raw_done.append(old_core)
		buses.done.notify(synth=old_core)

	old_request = manager.new_request()
	append_speech(manager, old_request, old_voice, speak_then_done)
	assert manager.submit_request(old_request)
	assert native_entered.wait(WAIT_TIMEOUT)
	cancel(manager, [old_voice])
	assert old_request.token.is_cancelled()
	release_native.set()
	with pytest.raises(CancelledError):
		old_request.tasks[0].future.result(timeout=WAIT_TIMEOUT)
	# The future can settle before cleanup and external event emission finish.
	manager._q.join()
	assert raw_done == [old_core]
	assert buses.outer_done == []
	assert buses.outer_indexes == []


def test_cancelled_request_built_before_submit_is_not_enqueued(manager, voice):
	request = manager.new_request()
	append_speech(manager, request, voice, lambda: voice.core.speak(["old"]))
	cancel(manager, [voice])
	assert manager.submit_request(request) is False
	assert voice.core.spoken == []


def test_two_concurrent_cancels_must_both_finish_before_new_speech(manager, voice, buses):
	entered = [threading.Event(), threading.Event()]
	release = [threading.Event(), threading.Event()]
	lock = threading.Lock()
	count = 0
	old_entered = threading.Event()
	new_entered = threading.Event()
	old = manager.new_request()
	append_speech(manager, old, voice, old_entered.set)
	assert manager.submit_request(old)
	assert old_entered.wait(WAIT_TIMEOUT)

	def cancel_core():
		nonlocal count
		with lock:
			index = count
			count += 1
		entered[index].set()
		assert release[index].wait(HOLD_TIMEOUT)

	voice.core.cancel = cancel_core
	stoppers = [threading.Thread(target=cancel, args=(manager, [voice])) for _ in range(2)]
	for stopper in stoppers:
		stopper.start()
	assert all(event.wait(WAIT_TIMEOUT) for event in entered)
	assert old.token.is_cancelled()
	request = manager.new_request()
	append_speech(manager, request, voice, new_entered.set)
	assert manager.submit_request(request)
	release[0].set()
	stoppers[0].join(WAIT_TIMEOUT)
	assert not stoppers[0].is_alive()
	stays_unset(new_entered)
	release[1].set()
	stoppers[1].join(WAIT_TIMEOUT)
	assert not stoppers[1].is_alive()
	assert new_entered.wait(WAIT_TIMEOUT)
	assert buses.outer_done == []
	buses.done.notify(synth=voice.core)
	assert buses.wait_for_outer_done() == [manager.owner]


def test_cancel_wakes_break_token_and_allows_new_request(manager, voice):
	old = manager.new_request()
	waiting = threading.Event()
	original_wait = old.token.wait

	def observed_wait(seconds):
		waiting.set()
		return original_wait(seconds)

	old.token.wait = observed_wait
	append_break(manager, old, voice, 60)
	assert manager.submit_request(old)
	assert waiting.wait(WAIT_TIMEOUT)
	cancel(manager, [voice])
	new_entered = threading.Event()
	new = manager.new_request()
	append_speech(manager, new, voice, new_entered.set)
	assert manager.submit_request(new)
	assert new_entered.wait(WAIT_TIMEOUT)


def test_cancel_stops_shared_core_only_once(manager, voice):
	other_voice = types.SimpleNamespace(core=voice.core, active=lambda: None)
	cancel(manager, [voice, other_voice, voice])
	assert voice.core.cancel_count == 1


def test_cancel_stops_current_core_before_other_cores(manager, voice):
	entered = threading.Event()
	stopped = []
	voice.core.cancel = lambda: stopped.append("current")
	other_core = types.SimpleNamespace(cancel=lambda: stopped.append("other"))
	other_voice = types.SimpleNamespace(core=other_core)
	request = manager.new_request()
	append_speech(manager, request, voice, entered.set)
	assert manager.submit_request(request)
	assert entered.wait(WAIT_TIMEOUT)
	cancel(manager, [other_voice, voice])
	assert stopped == ["current", "other"]


def test_cancel_during_active_skips_core_speak(manager, voice):
	active_entered = threading.Event()
	release_active = threading.Event()
	completed = threading.Event()
	voice.active = lambda: (active_entered.set(), release_active.wait(HOLD_TIMEOUT))
	request = manager.new_request()
	append_speech(manager, request, voice, lambda: voice.core.speak(["late"]))
	request.tasks[0].future.add_done_callback(lambda _: completed.set())
	assert manager.submit_request(request)
	assert active_entered.wait(WAIT_TIMEOUT)
	cancel(manager, [voice])
	release_active.set()
	assert completed.wait(WAIT_TIMEOUT)
	assert request.tasks[0].future.cancelled()
	assert voice.core.spoken == []


def test_cancel_during_speak_stops_core_again_after_speak_returns(manager, voice):
	entered = threading.Event()
	release_speak = threading.Event()

	def blocking_speak(text):
		entered.set()
		assert release_speak.wait(HOLD_TIMEOUT)
		voice.core.spoken.append(text)

	voice.core.speak = blocking_speak
	request = manager.new_request()
	append_speech(manager, request, voice, lambda: voice.core.speak(["old"]))
	completed = threading.Event()
	request.tasks[0].future.add_done_callback(lambda _: completed.set())
	assert manager.submit_request(request)
	assert entered.wait(WAIT_TIMEOUT)
	cancel(manager, [voice])
	release_speak.set()
	assert completed.wait(WAIT_TIMEOUT)
	assert request.tasks[0].future.cancelled()
	assert voice.core.cancel_count == 2


def test_pending_speech_is_cancelled_but_new_request_runs(manager, voice, buses):
	first_entered = threading.Event()
	old_entered = threading.Event()
	new_entered = threading.Event()
	first = manager.new_request()
	append_speech(manager, first, voice, first_entered.set)
	assert manager.submit_request(first)
	assert first_entered.wait(WAIT_TIMEOUT)
	old = manager.new_request()
	append_speech(manager, old, voice, old_entered.set)
	assert manager.submit_request(old)
	old_future = old.tasks[0].future
	old_done = threading.Event()
	old_future.add_done_callback(lambda _: old_done.set())
	cancel(manager, [voice])
	new = manager.new_request()
	append_speech(manager, new, voice, new_entered.set)
	assert manager.submit_request(new)
	new_future = new.tasks[0].future
	assert old_done.wait(WAIT_TIMEOUT)
	assert old_future.cancelled()
	assert new_entered.wait(WAIT_TIMEOUT)
	assert not old_entered.is_set()
	assert not new_future.cancelled()
	buses.done.notify(synth=voice.core)
	assert new_future.result(timeout=WAIT_TIMEOUT) is True


@pytest.mark.parametrize("engine", ["VE", "Cerence"])
def test_direct_wrapper_stop_mid_speech_lets_next_segment_run(manager, buses, monkeypatch, engine):
	from worldvoice_cancel_wrapper_harness import load_real_driver_with_native_stubs

	harness = load_real_driver_with_native_stubs(monkeypatch, engine)
	monkeypatch.setattr(harness.original_driver, "synthDoneSpeaking", buses.done)
	monkeypatch.setattr(harness.original_driver, "synthIndexReached", buses.index)
	core = harness.new_core()
	core.voiceInstance = core.getVoiceInstance("fake")
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
		append_speech(
			manager,
			request,
			voice,
			lambda text=text: core.speak([text], cancellationToken=request.token),
		)
	assert manager.submit_request(request)
	assert second_spoken.wait(WAIT_TIMEOUT)
	assert buses.wait_for_outer_done() == [manager.owner]
	assert spoken == ["first", "second"]
