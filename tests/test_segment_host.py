"""SegmentHost and LeasedPlayer against a fake engine strategy."""

import importlib.util
import sys
from threading import Condition, Event, Thread, get_ident
from types import SimpleNamespace

import pytest
from runtime_harness import RUNTIME, load_runtime, load_scheduler


class FakeStrategy:
	"""Records submitted native work; tests step it through begin/reach/retire."""

	barriers = frozenset({"returned", "idle"})

	def __init__(self):
		self.condition = Condition()
		self.submitted = []
		self.native_stops = []
		self.player_stops = 0
		self.submit_error = None

	def submit(self, host, record, commands):
		if self.submit_error is not None:
			raise self.submit_error
		with self.condition:
			self.submitted.append((record, commands))
			self.condition.notify_all()

	def stop_native(self, host, record):
		with self.condition:
			self.native_stops.append(record)
			self.condition.notify_all()

	def stop_player(self, host):
		self.player_stops += 1

	def wait_submitted(self, count=1):
		with self.condition:
			assert self.condition.wait_for(lambda: len(self.submitted) >= count, 2), (
				"native work was not submitted"
			)
			return self.submitted[count - 1][0]


class Events(list):
	def __init__(self):
		super().__init__()
		self.condition = Condition()
		self.threads = []

	def append(self, event):
		with self.condition:
			super().append(event)
			self.threads.append(get_ident())
			self.condition.notify_all()

	def wait_one(self):
		with self.condition:
			assert self.condition.wait_for(lambda: bool(self), 2), "no terminal event delivered"
			self.condition.wait_for(lambda: len(self) > 1, 0.1)
			assert len(self) == 1, list(self)
			return self[0]


def _load(monkeypatch, rt, name):
	full = f"{rt.package.__name__}.{name}"
	spec = importlib.util.spec_from_file_location(full, RUNTIME / f"{name}.py")
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, full, module)
	spec.loader.exec_module(module)
	return module


@pytest.fixture
def env(monkeypatch):
	rt = load_runtime(monkeypatch)
	scheduler = load_scheduler(monkeypatch, rt)
	_load(monkeypatch, rt, "segmentLifecycle")
	module = _load(monkeypatch, rt, "segmentHost")
	strategy = FakeStrategy()
	host = module.SegmentHost("Fake", strategy)
	threads = []

	def speak(segment=17, sink=None, token=None):
		events = Events()
		token = token or scheduler.CancellationToken()
		context = rt.models.PlaybackContext(object(), segment)
		host.speak_segment(("hello",), token, context=context, on_event=sink or events.append)
		return token, context, events

	def run_native(record, reach=("returned", "idle")):
		# The engine's FIFO worker: begin, mark barriers, retire (blocks until handoff).
		def work():
			host.begin(record)
			for barrier in reach:
				host.reach(record, barrier)
			result.append(host.retire(record))

		result = []
		thread = Thread(target=work, daemon=True)
		thread.start()
		threads.append(thread)
		return thread, result

	yield SimpleNamespace(
		rt=rt,
		scheduler=scheduler,
		module=module,
		host=host,
		strategy=strategy,
		speak=speak,
		run_native=run_native,
	)
	host.terminate()
	for thread in threads:
		thread.join(2)


def test_completed_segment_drains_once_after_every_barrier(env):
	_, context, events = env.speak()
	record = env.strategy.wait_submitted()
	assert record.operation is not None
	native, _ = env.run_native(record)
	event = events.wait_one()
	native.join(2)
	assert event.kind is env.rt.models.EventKind.SEGMENT_DRAINED
	assert (event.source_id, event.segment_id) == (context.source_id, 17)
	assert env.strategy.player_stops == 0


def test_missing_barrier_fails_and_discards_audio(env):
	_, _, events = env.speak()
	record = env.strategy.wait_submitted()
	env.run_native(record, reach=("returned",))
	event = events.wait_one()
	assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert str(event.error) == "Fake synthesis retired without its idle barriers"
	# The lifecycle's own stop/drain pass after fail() may stop the player again.
	assert env.strategy.player_stops >= 1


def test_native_error_fails_the_original_segment(env):
	_, context, events = env.speak()
	record = env.strategy.wait_submitted()
	env.host.record_error(record, OSError("native failed"))
	env.run_native(record)
	event = events.wait_one()
	assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert isinstance(event.error, OSError)
	assert event.segment_id == context.segment_id


def test_submit_error_fails_the_segment(env):
	env.strategy.submit_error = RuntimeError("queue rejected")
	_, _, events = env.speak()
	event = events.wait_one()
	assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert env.strategy.submitted == []


def test_terminated_host_rejects_without_submitting(env):
	assert env.host.terminate() is True
	assert env.host.terminate() is False
	_, _, events = env.speak(segment=19)
	event = events.wait_one()
	assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert str(event.error) == "Fake driver has terminated"
	assert env.strategy.submitted == []
	assert events.threads[0] != get_ident()


def test_first_control_error_fails_pending_work_and_rejects_new_segments(env):
	_, _, events = env.speak()
	record = env.strategy.wait_submitted()
	first, second = OSError("stop failed"), OSError("second stop failed")
	env.host.latch_control_error(first)
	env.host.latch_control_error(second)
	assert env.host.control_error is first
	env.run_native(record)
	assert events.wait_one().error is first
	_, _, rejected = env.speak(segment=18)
	assert rejected.wait_one().error is first
	assert len(env.strategy.submitted) == 1


def test_cancel_keeps_accepted_segment_silent_and_stops_active_native(env):
	_, _, events = env.speak()
	record = env.strategy.wait_submitted()
	env.host.begin(record)
	env.host.cancel()
	# The lifecycle asks for the stop on its own thread.
	with env.strategy.condition:
		assert env.strategy.condition.wait_for(lambda: env.strategy.native_stops == [record], 1)
	native, _ = env.run_native(record)
	native.join(2)
	with events.condition:
		events.condition.wait_for(lambda: bool(events), 0.2)
	assert list(events) == []


def test_sink_can_terminate_without_self_join(env):
	terminated = Event()

	def sink(event):
		env.host.terminate()
		terminated.set()

	env.speak(sink=sink)
	env.run_native(env.strategy.wait_submitted())
	assert terminated.wait(2), "terminate() from the delivery thread deadlocked"


def test_terminate_does_not_hang_on_a_blocked_sink(env):
	entered, release = Event(), Event()

	def sink(event):
		entered.set()
		release.wait(5)

	env.speak(sink=sink)
	env.run_native(env.strategy.wait_submitted())
	assert entered.wait(2)
	finished = Event()
	Thread(target=lambda: (env.host.terminate(), finished.set()), daemon=True).start()
	try:
		# The delivery join is bounded to one second.
		assert finished.wait(2), "terminate() waited on a blocked sink"
	finally:
		release.set()


def test_retire_waits_for_admitted_consumers(env):
	record = env.host.new_record(None)
	env.host.begin(record)
	release, retired = Event(), Event()

	def consume():
		with env.host.consumer() as admitted:
			assert admitted is record
			release.wait(2)

	consumer = Thread(target=consume, daemon=True)
	consumer.start()
	Event().wait(0.05)
	Thread(target=lambda: (env.host.retire(record), retired.set()), daemon=True).start()
	assert not retired.wait(0.1), "retire() did not wait for the admitted consumer"
	release.set()
	assert retired.wait(1)
	with env.host.consumer(record) as late:
		assert late is None


@pytest.mark.parametrize("case", ["complete", "missing", "error", "cancelled"])
def test_ordinary_record_outcomes(env, case):
	env.host.enqueue(("ordinary",))
	record = env.strategy.wait_submitted()
	assert record.operation is None and record.work is None
	env.host.begin(record)
	if case != "missing":
		env.host.reach(record, "returned")
		env.host.reach(record, "idle")
	if case == "error":
		env.host.record_error(record, OSError("feed failed"))
	if case == "cancelled":
		env.host.cancel()
	outcome = env.host.retire(record)
	assert outcome.cancelled is (case == "cancelled")
	if case == "complete":
		assert outcome.error is None
		assert env.strategy.player_stops == 0
	elif case == "missing":
		assert "returned, idle" in str(outcome.error) or "idle, returned" in str(outcome.error)
		assert env.strategy.player_stops == 1
	elif case == "error":
		assert isinstance(outcome.error, OSError)
		assert env.strategy.player_stops == 1
	else:
		assert outcome.error is None
		assert env.strategy.player_stops == 1


def test_ordinary_speech_raises_after_a_control_error(env):
	error = OSError("stop failed")
	env.host.latch_control_error(error)
	with pytest.raises(OSError, match="stop failed"):
		env.host.enqueue(("ordinary",))
	assert env.strategy.submitted == []


def test_unknown_barrier_is_rejected(env):
	record = env.host.new_record(None)
	with pytest.raises(KeyError):
		env.host.reach(record, "ended")


class FakePlayer:
	def __init__(self):
		self.fed, self.callbacks, self.stops, self.idles = [], [], 0, 0
		self.stop_error = None

	def feed(self, data, size=None, onDone=None):
		self.fed.append(data)
		if onDone is not None:
			self.callbacks.append(onDone)

	def idle(self):
		self.idles += 1

	def stop(self):
		self.stops += 1
		if self.stop_error is not None:
			raise self.stop_error


def test_leased_player_ignores_feed_without_a_current_record(env):
	real = FakePlayer()
	player = env.module.LeasedPlayer(env.host, real)
	assert player.feed(b"pcm") is None
	assert real.fed == []


def test_leased_player_binds_on_done_to_its_record_and_reaches_idle(env):
	real = FakePlayer()
	player = env.module.LeasedPlayer(env.host, real)
	record = env.host.new_record(None)
	env.host.begin(record)
	seen = []
	player.feed(b"pcm", 3, lambda: seen.append(env.host.callback_record()))
	real.callbacks[0]()
	assert seen == [record]
	assert env.host.callback_record() is None
	player.idle()
	assert record.barriers["idle"] is True


def test_leased_player_stops_again_after_an_invalidated_feed(env):
	real = FakePlayer()
	player = env.module.LeasedPlayer(env.host, real)
	env.host.enqueue(("ordinary",))
	record = env.strategy.wait_submitted()
	env.host.begin(record)
	original_feed = real.feed

	def feed_then_cancel(*args):
		original_feed(*args)
		env.host.cancel()

	real.feed = feed_then_cancel
	player.feed(b"pcm")
	assert real.stops == 1


def test_leased_player_stop_failure_latches_a_control_error(env):
	real = FakePlayer()
	real.stop_error = OSError("stop failed")
	player = env.module.LeasedPlayer(env.host, real)
	with pytest.raises(OSError):
		player.stop()
	assert env.host.control_error is real.stop_error
