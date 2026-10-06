"""Routing and all-or-nothing request construction contracts."""

import builtins
import importlib
import sys
from threading import Event
from types import SimpleNamespace

import pytest
from runtime_harness import (
	FakePlayback,
	RecordingOutput,
	load_scheduler,
	tracked_requests,
	worker_queue_empty,
)
from waiting import HOLD_TIMEOUT, WAIT_TIMEOUT


@pytest.fixture
def builder(monkeypatch, rt):
	original = builtins.__import__

	def pure_import(name, *args, **kwargs):
		assert name not in {
			"driver",
			"speech",
			"speech.commands",
			"config",
			"synthDriverHandler",
			"logHandler",
		}
		assert ".driver" not in name and ".compat" not in name
		return original(name, *args, **kwargs)

	monkeypatch.setattr(builtins, "__import__", pure_import)
	load_scheduler(monkeypatch, rt)
	name = rt.package.__name__ + ".requestBuilder"
	monkeypatch.delitem(sys.modules, name, raising=False)
	return importlib.import_module(name)


@pytest.fixture
def recording_builder(builder):
	class RecordingManager:
		def __init__(self):
			self.speech = []
			self.breaks = []
			self.tasks = []
			self.submit_count = 0
			self.ports = {key: FakePlayback() for key in ("Fake:a", "Fake:b")}

		def new_request(self):
			self.request = object()
			return self.request

		def append_speech(self, request, playback, key, commands):
			assert request is self.request
			assert playback is self.ports[key]
			assert isinstance(commands, tuple)
			self.speech.append((key, commands))
			self.tasks.append(("speech", key, commands))

		def append_break(self, request, seconds):
			assert request is self.request
			self.breaks.append(seconds)
			self.tasks.append(("break", seconds))

		def submit_request(self, request):
			assert request is self.request
			self.submit_count += 1
			return True

		def run(self, sequence, default="Fake:a"):
			return builder.queue_speech_sequence(self, sequence, default, self.ports.get)

	return RecordingManager()


def test_unavailable_segment_does_not_block_next_voice(recording_builder, rt):
	select, pause = rt.models.SelectVoice, rt.models.Pause
	assert recording_builder.run(
		[
			"A",
			select("missing:x"),
			"skip",
			999,
			pause(1),
			select("Fake:b"),
			"B",
			pause(0.2),
		],
	)
	assert recording_builder.speech == [("Fake:a", ("A",)), ("Fake:b", ("B",))]
	assert recording_builder.breaks == [0.2]
	assert recording_builder.submit_count == 1


def test_unavailable_default_and_repeated_missing_voices_recover(recording_builder, rt):
	select, pause = rt.models.SelectVoice, rt.models.Pause
	assert recording_builder.run(
		[
			"skip",
			999,
			pause(1),
			select("missing:y"),
			"skip again",
			select("missing:z"),
			pause(2),
			select("Fake:b"),
			"B",
		],
		default="missing:x",
	)
	assert recording_builder.tasks == [("speech", "Fake:b", ("B",))]
	assert recording_builder.submit_count == 1


def test_valid_indexes_and_breaks_keep_input_order(recording_builder, rt):
	select, pause = rt.models.SelectVoice, rt.models.Pause
	index = object()
	sequence = [index, "A", 11, pause(0.1), "after", select("Fake:b"), 22, "B", pause(0.2)]
	assert recording_builder.run(sequence)
	sequence.clear()
	assert recording_builder.tasks == [
		("speech", "Fake:a", (index, "A", 11)),
		("break", 0.1),
		("speech", "Fake:a", ("after",)),
		("speech", "Fake:b", (22, "B")),
		("break", 0.2),
	]
	assert recording_builder.speech[0][1][0] is index
	assert recording_builder.submit_count == 1


@pytest.fixture
def runtime(monkeypatch, rt, builder):
	scheduler = sys.modules[rt.package.__name__ + ".scheduler"]
	output = RecordingOutput()
	manager = scheduler.TaskManager(output)
	requests = []
	original = manager.new_request

	def new_request():
		request = original()
		requests.append(request)
		return request

	monkeypatch.setattr(manager, "new_request", new_request)
	value = SimpleNamespace(
		manager=manager,
		output=output,
		requests=requests,
		scheduler=scheduler,
		port=FakePlayback(),
	)
	yield value
	manager.shutdown()


@pytest.mark.parametrize("kind", ["empty", "unavailable", "break_only"])
def test_requests_without_speech_do_not_notify_done(builder, runtime, rt, kind):
	sequences = {
		"empty": [],
		"unavailable": ["skip", 999, rt.models.Pause(1)],
		"break_only": [rt.models.Pause(0)],
	}
	resolve = lambda key: None if kind == "unavailable" else runtime.port
	assert builder.queue_speech_sequence(runtime.manager, sequences[kind], "Fake:a", resolve)
	runtime.manager._q.join()
	request = runtime.requests[0]
	assert request.state is runtime.scheduler.RequestState.COMPLETED
	assert tracked_requests(runtime.manager) == {}
	assert runtime.output.done_count == 0
	assert runtime.port.spoken == []


def test_whole_request_waits_for_generator_and_trailing_break(builder, runtime, rt, monkeypatch):
	break_entered, release_break = Event(), Event()
	manager, port = runtime.manager, runtime.port

	def on_speak():
		for command in port.spoken[-1][0]:
			if isinstance(command, int):
				manager.on_event(rt.models.PlaybackEvent(rt.models.EventKind.INDEX, port.source_id, command))
		manager.on_event(rt.models.PlaybackEvent(rt.models.EventKind.DONE, port.source_id))

	port.on_speak = on_speak
	submissions = []
	original_submit = manager.submit_request

	def submit(request):
		submissions.append(request)

		def wait(seconds):
			assert seconds == 0.2
			break_entered.set()
			assert release_break.wait(HOLD_TIMEOUT)

		monkeypatch.setattr(request.token, "wait", wait)
		return original_submit(request)

	monkeypatch.setattr(manager, "submit_request", submit)

	def sequence():
		yield "A"
		yield 11
		yield rt.models.SelectVoice("missing:x")
		assert worker_queue_empty(manager)
		assert port.spoken == []
		yield 999
		yield rt.models.Pause(1)
		yield rt.models.SelectVoice("Fake:b")
		yield 22
		yield "B"
		yield rt.models.Pause(0.2)
		assert submissions == []

	try:
		assert builder.queue_speech_sequence(
			manager,
			sequence(),
			"Fake:a",
			lambda key: None if key == "missing:x" else port,
		)
		assert break_entered.wait(WAIT_TIMEOUT)
		assert runtime.output.indexes == [11, 22]
		assert runtime.output.done_count == 0
		assert port.activated == ["Fake:a", "Fake:b"]
		assert [commands for commands, token in port.spoken] == [("A", 11), (22, "B")]
		assert len(submissions) == 1
		assert not runtime.requests[0].tasks[-1].future.done()
	finally:
		release_break.set()
	assert runtime.output.wait_done() == 1


@pytest.mark.parametrize("flush_first", [False, True])
def test_generator_failure_aborts_unsubmitted_request(builder, runtime, rt, flush_first):
	error = RuntimeError("generator failed")

	def sequence():
		yield "A"
		if flush_first:
			yield rt.models.Pause(0.1)
		raise error

	with pytest.raises(RuntimeError) as caught:
		builder.queue_speech_sequence(runtime.manager, sequence(), "Fake:a", lambda key: runtime.port)
	assert caught.value is error
	request = runtime.requests[0]
	assert request.state is runtime.scheduler.RequestState.FAILED
	assert tracked_requests(runtime.manager) == {}
	assert all(task.future.exception() is error for task in request.tasks)
	assert bool(request.tasks) is flush_first
	assert runtime.port.spoken == []
	assert worker_queue_empty(runtime.manager)
	assert runtime.output.done_count == 0


@pytest.mark.parametrize("initial", [False, True])
def test_resolver_failure_aborts_request(builder, runtime, rt, initial):
	error = RuntimeError("resolver failed")

	def resolve(key):
		if initial or key == "broken:x":
			raise error
		return runtime.port

	with pytest.raises(RuntimeError) as caught:
		builder.queue_speech_sequence(
			runtime.manager,
			["A", rt.models.SelectVoice("broken:x"), "B"],
			"Fake:a",
			resolve,
		)
	assert caught.value is error
	request = runtime.requests[0]
	assert request.state is runtime.scheduler.RequestState.FAILED
	assert tracked_requests(runtime.manager) == {}
	assert all(task.future.exception() is error for task in request.tasks)
	assert bool(request.tasks) is not initial
	assert runtime.port.spoken == []
	assert runtime.output.done_count == 0


@pytest.mark.parametrize("stop", ["cancel", "shutdown"])
@pytest.mark.parametrize("next_command", ["speech", "break", "end", "error"])
def test_cancel_during_build_returns_false(builder, runtime, rt, stop, next_command):
	def sequence():
		yield "A"
		yield rt.models.Pause(0)
		getattr(runtime.manager, stop)()
		if next_command == "speech":
			yield "B"
		elif next_command == "break":
			yield rt.models.Pause(1)
		elif next_command == "error":
			raise RuntimeError("late generator failure")

	assert (
		builder.queue_speech_sequence(
			runtime.manager,
			sequence(),
			"Fake:a",
			lambda key: runtime.port,
		)
		is False
	)
	request = runtime.requests[0]
	assert request.state is runtime.scheduler.RequestState.CANCELLED
	assert tracked_requests(runtime.manager) == {}
	assert all(task.future.cancelled() for task in request.tasks)
	assert runtime.port.spoken == []
	assert runtime.output.done_count == 0


def test_shutdown_before_build_returns_false(builder, runtime):
	runtime.manager.shutdown()
	assert (
		builder.queue_speech_sequence(
			runtime.manager,
			["A"],
			"Fake:a",
			lambda key: runtime.port,
		)
		is False
	)
	assert runtime.requests == []


@pytest.mark.parametrize("stop", ["cancel", "shutdown"])
@pytest.mark.parametrize("failure", ["generator", "resolver"])
def test_cancellation_between_error_check_and_abort_returns_false(
	builder,
	runtime,
	rt,
	monkeypatch,
	stop,
	failure,
):
	original_abort = runtime.manager.abort_request
	error = RuntimeError(f"{failure} failed")

	def abort_after_stop(request, caught):
		assert request.state is runtime.scheduler.RequestState.BUILDING
		assert caught is error
		getattr(runtime.manager, stop)()
		original_abort(request, caught)

	monkeypatch.setattr(runtime.manager, "abort_request", abort_after_stop)

	def resolve(key):
		if key == "broken:x":
			raise error
		return runtime.port

	def sequence():
		yield "A"
		yield rt.models.Pause(0)
		if failure == "generator":
			raise error
		yield rt.models.SelectVoice("broken:x")

	assert builder.queue_speech_sequence(runtime.manager, sequence(), "Fake:a", resolve) is False
	request = runtime.requests[0]
	assert request.state is runtime.scheduler.RequestState.CANCELLED
	assert tracked_requests(runtime.manager) == {}
	assert len(request.tasks) == 2
	assert all(task.future.cancelled() for task in request.tasks)
	assert runtime.port.spoken == []
	assert runtime.output.done_count == 0


@pytest.mark.parametrize("repeat_selection", [False, True])
def test_select_pause_and_end_flush_only_nonempty_segments(recording_builder, rt, repeat_selection):
	select, pause = rt.models.SelectVoice, rt.models.Pause
	selections = [select("Fake:b")] * (2 if repeat_selection else 1)
	assert recording_builder.run(["A", *selections, "B", pause(0.2), "C"])
	assert recording_builder.tasks == [
		("speech", "Fake:a", ("A",)),
		("speech", "Fake:b", ("B",)),
		("break", 0.2),
		("speech", "Fake:b", ("C",)),
	]
	assert recording_builder.submit_count == 1


def test_command_and_index_only_segments_are_preserved(recording_builder, rt):
	command, index = object(), object()
	assert recording_builder.run([command, rt.models.SelectVoice("Fake:b"), index])
	assert recording_builder.tasks == [
		("speech", "Fake:a", (command,)),
		("speech", "Fake:b", (index,)),
	]
	assert recording_builder.submit_count == 1
