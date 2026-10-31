"""SegmentHost and LeasedPlayer against a fake engine strategy."""

import logging
from threading import Condition, Event, Thread, get_ident
from types import SimpleNamespace

import pytest
from addon_loader import REF, load_source
from runtime_harness import (
	RUNTIME,
	accepted_operations,
	load_runtime,
	load_scheduler,
	native_record,
	pending_records,
)
from waiting import HOLD_TIMEOUT, WAIT_TIMEOUT, eventually, stays_false, stays_unset

# The runtime's own value: LeasedPlayer reaches it by default, so the fakes must declare it.
PLAYED_OUT = load_source(None, "segment_host_barriers", RUNTIME / "barriers.py", register=False).PLAYED_OUT


class FakeStrategy:
	"""Records submitted native work; tests step it through begin/reach/retire."""

	barriers = frozenset({"returned", PLAYED_OUT})

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
			assert self.condition.wait_for(lambda: len(self.submitted) >= count, WAIT_TIMEOUT), (
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
		eventually(lambda: bool(self), message="no terminal event delivered")
		# A duplicate delivered shortly after the first event must still be caught.
		stays_false(
			self.condition,
			lambda: len(self) > 1,
			message=lambda: f"expected one terminal event, got {list(self)}",
		)
		return self[0]


def native(module, strategy_type):
	"""An engine-style strategy: the fake's behavior on the real NativeStrategy base."""
	return type(strategy_type.__name__, (strategy_type, module.NativeStrategy), {})()


def _load(monkeypatch, rt, name):
	return load_source(monkeypatch, f"{rt.package.__name__}.{name}", RUNTIME / f"{name}.py")


@pytest.fixture
def env(monkeypatch, request):
	options = getattr(request, "param", {})
	rt = load_runtime(monkeypatch)
	scheduler = load_scheduler(monkeypatch, rt)
	_load(monkeypatch, rt, "_segmentLifecycle")
	module = _load(monkeypatch, rt, "segmentHost")
	strategy = native(module, FakeStrategy)
	host = module.SegmentHost("Fake", strategy, **options)
	threads = []

	def speak(segment=17, sink=None, token=None):
		events = Events()
		token = token or scheduler.CancellationToken()
		context = rt.models.PlaybackContext(object(), segment)
		host.speak_segment(("hello",), token, context=context, on_event=sink or events.append)
		return token, context, events

	def run_native(record, reach=("returned", PLAYED_OUT)):
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
	native.join(WAIT_TIMEOUT)
	assert event.kind is env.rt.models.EventKind.SEGMENT_DRAINED
	assert (event.source_id, event.segment_id) == (context.source_id, 17)
	assert env.strategy.player_stops == 0


def test_missing_barrier_fails_and_discards_audio(env):
	_, _, events = env.speak()
	record = env.strategy.wait_submitted()
	env.run_native(record, reach=("returned",))
	event = events.wait_one()
	assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert str(event.error) == f"Fake synthesis retired without its {PLAYED_OUT} barriers"
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
		assert env.strategy.condition.wait_for(lambda: env.strategy.native_stops == [record], WAIT_TIMEOUT)
	native, _ = env.run_native(record)
	native.join(WAIT_TIMEOUT)
	stays_false(events.condition, lambda: bool(events), message=lambda: f"unexpected events {list(events)}")
	# The discarded operation's bookkeeping is released (on the delivery thread).
	eventually(lambda: not accepted_operations(env.host))
	assert accepted_operations(env.host) == {}


def test_cancel_after_commit_keeps_the_event_silent(env, monkeypatch):
	# Order: the event is committed, NVDA cancels, the run thread finishes its
	# bookkeeping, and only then does the delivery thread call the sink.
	cancelled = Event()
	real_run = env.host._lifecycle.run

	def run_until_cancelled(operation, commands):
		real_run(operation, commands)
		assert cancelled.wait(WAIT_TIMEOUT)

	monkeypatch.setattr(env.host._lifecycle, "run", run_until_cancelled)
	_, _, events = env.speak()
	record = env.strategy.wait_submitted()
	original = env.host._deliver

	def cancel_before_publication(operation, sink, event):
		env.host.cancel()
		cancelled.set()
		assert record.handoff.wait(WAIT_TIMEOUT), "run thread did not finish"
		original(operation, sink, event)

	monkeypatch.setattr(env.host, "_deliver", cancel_before_publication)
	env.run_native(record)
	stays_false(events.condition, lambda: bool(events), message=lambda: f"unexpected events {list(events)}")


def test_sink_can_terminate_without_self_join(env):
	terminated = Event()

	def sink(event):
		env.host.terminate()
		terminated.set()

	env.speak(sink=sink)
	env.run_native(env.strategy.wait_submitted())
	assert terminated.wait(WAIT_TIMEOUT), "terminate() from the delivery thread deadlocked"


def test_terminate_does_not_hang_on_a_blocked_sink(env, monkeypatch):
	monkeypatch.setattr(env.module, "DELIVERY_JOIN_TIMEOUT", 0.05)
	entered, release = Event(), Event()

	def sink(event):
		entered.set()
		release.wait(HOLD_TIMEOUT)

	env.speak(sink=sink)
	env.run_native(env.strategy.wait_submitted())
	assert entered.wait(WAIT_TIMEOUT)
	finished = Event()
	Thread(target=lambda: (env.host.terminate(), finished.set()), daemon=True).start()
	try:
		# The delivery join is bounded (DELIVERY_JOIN_TIMEOUT).
		assert finished.wait(WAIT_TIMEOUT), "terminate() waited on a blocked sink"
	finally:
		release.set()


@pytest.mark.parametrize("start_delay", [0, 0.1])
def test_retire_waits_for_admitted_consumers(env, start_delay):
	record = env.host.new_record()
	env.host.begin(record)
	release, retired, entered = Event(), Event(), Event()

	def consume():
		Event().wait(start_delay)  # a consumer thread that is slow to start
		with env.host.consumer() as admitted:
			assert admitted is record
			entered.set()
			release.wait(HOLD_TIMEOUT)

	consumer = Thread(target=consume, daemon=True)
	consumer.start()
	assert entered.wait(WAIT_TIMEOUT), "consumer was never admitted"
	Thread(target=lambda: (env.host.retire(record), retired.set()), daemon=True).start()
	stays_unset(retired, message="retire() did not wait for the admitted consumer")
	release.set()
	assert retired.wait(WAIT_TIMEOUT)
	with env.host.consumer(record) as late:
		assert late is None


def test_a_retired_ordinary_record_stays_cancellable_until_forgotten(env):
	# The engine reports DONE after retire(); a cancel in between must still mark the record.
	env.host.enqueue(("ordinary",))
	record = env.strategy.wait_submitted()
	env.host.begin(record)
	env.host.reach(record, "returned")
	env.host.reach(record, PLAYED_OUT)
	assert env.host.retire(record).cancelled is False
	assert record in pending_records(env.host)
	env.host.cancel()
	assert record.cancelled
	env.host.forget(record)
	assert record not in pending_records(env.host)


def host_errors(env, caplog):
	return [
		record
		for record in caplog.records
		if record.name == env.module.log.name and record.levelno >= logging.ERROR
	]


@pytest.mark.parametrize("case", ["complete", "missing", "error", "cancelled"])
def test_ordinary_record_outcomes(env, caplog, case):
	caplog.set_level(logging.ERROR, logger=env.module.log.name)
	env.host.enqueue(("ordinary",))
	record = env.strategy.wait_submitted()
	assert record.operation is None and record.work is None
	env.host.begin(record)
	if case != "missing":
		env.host.reach(record, "returned")
		env.host.reach(record, PLAYED_OUT)
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
		missing = str(outcome.error)
		assert f"returned, {PLAYED_OUT}" in missing or f"{PLAYED_OUT}, returned" in missing
		assert env.strategy.player_stops == 1
		# The engines do not read the outcome, so the host's log is the only trace of it.
		[logged] = host_errors(env, caplog)
		message = logged.getMessage()
		assert "Fake" in message and "returned" in message and PLAYED_OUT in message
	elif case == "error":
		assert isinstance(outcome.error, OSError)
		assert env.strategy.player_stops == 1
	else:
		assert outcome.error is None
		assert env.strategy.player_stops == 1
	if case != "missing":
		assert host_errors(env, caplog) == []


@pytest.mark.parametrize("case", ["missing", "complete", "error"])
def test_a_host_cancelled_ordinary_record_retires_cancelled(env, caplog, case):
	# Every engine cancels ordinary speech through the host: whatever barriers the record
	# reached, and even after a recorded error, retire reports it cancelled, logs nothing for
	# its unreached barriers and discards queued audio.
	caplog.set_level(logging.ERROR, logger=env.module.log.name)
	env.host.enqueue(("ordinary",))
	record = env.strategy.wait_submitted()
	env.host.begin(record)
	if case == "complete":
		env.host.reach(record, "returned")
		env.host.reach(record, PLAYED_OUT)
	if case == "error":
		env.host.record_error(record, OSError("feed failed"))
	env.host.cancel()
	outcome = env.host.retire(record)
	assert outcome == env.module.OrdinaryOutcome(cancelled=True, error=None)
	assert host_errors(env, caplog) == []
	assert env.strategy.player_stops == 1
	assert record not in pending_records(env.host)


def test_ordinary_speech_raises_after_a_control_error(env):
	error = OSError("stop failed")
	env.host.latch_control_error(error)
	with pytest.raises(OSError, match="stop failed"):
		env.host.enqueue(("ordinary",))
	assert env.strategy.submitted == []


def test_unknown_barrier_is_rejected(env):
	record = env.host.new_record()
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
	record = env.host.new_record()
	env.host.begin(record)
	seen = []
	player.feed(b"pcm", 3, lambda: seen.append(env.host.callback_record()))
	real.callbacks[0]()
	assert seen == [record]
	assert env.host.callback_record() is None
	player.idle()
	assert record.barriers[PLAYED_OUT] is True


def test_leased_player_stops_again_after_an_invalidated_feed(env):
	real = FakePlayer()
	player = env.module.LeasedPlayer(env.host, real)
	env.host.enqueue(("ordinary",))
	record = env.strategy.wait_submitted()
	env.host.begin(record)
	original_feed = real.feed

	def feed_then_cancel(*args, **kwargs):
		original_feed(*args, **kwargs)
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


class DrainingStrategy(FakeStrategy):
	"""A strategy whose playback barrier is reached by drain() on the lifecycle thread."""

	def __init__(self):
		super().__init__()
		self.drains = []
		self.drain_error = None
		self.drain_raises = None
		self.drain_release = Event()
		self.drain_release.set()
		self.drain_entered = Event()

	def drain(self, host, record):
		self.drains.append(record)
		self.drain_entered.set()
		assert self.drain_release.wait(HOLD_TIMEOUT), "test did not release drain"
		if self.drain_raises is not None:
			raise self.drain_raises
		if self.drain_error is not None:
			host.record_error(record, self.drain_error)
			return
		host.reach(record, PLAYED_OUT)


@pytest.fixture
def drain_env(env):
	strategy = native(env.module, DrainingStrategy)
	env.host._strategy = strategy
	env.strategy = strategy
	return env


def test_record_carries_engine_data_and_its_own_barriers(env):
	data = object()
	env.host.enqueue(("ordinary",), barriers={"returned"}, native=data)
	record = env.strategy.wait_submitted()
	assert record.native is data
	assert record.barriers == {"returned": False}
	assert record.operation is None and record.work is None


def test_drain_runs_before_the_barrier_check(drain_env):
	env = drain_env
	_, _, events = env.speak()
	record = env.strategy.wait_submitted()
	env.run_native(record, reach=("returned",))
	event = events.wait_one()
	assert event.kind is env.rt.models.EventKind.SEGMENT_DRAINED
	assert env.strategy.drains == [record]


@pytest.mark.parametrize("failure", ["recorded", "raised"])
def test_drain_failure_fails_only_that_segment(drain_env, failure):
	env = drain_env
	if failure == "recorded":
		env.strategy.drain_error = OSError("idle failed")
	else:
		env.strategy.drain_raises = OSError("idle failed")
	_, _, events = env.speak()
	env.run_native(env.strategy.wait_submitted(), reach=("returned",))
	event = events.wait_one()
	assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert isinstance(event.error, OSError)
	# No permanent lifecycle fault: the next segment still drains.
	env.strategy.drain_error = env.strategy.drain_raises = None
	_, _, successor = env.speak(segment=18)
	env.run_native(env.strategy.wait_submitted(2), reach=("returned",))
	assert successor.wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED


def test_stop_reaches_a_record_that_is_still_draining(drain_env):
	env = drain_env
	env.strategy.drain_release.clear()
	env.speak()
	record = env.strategy.wait_submitted()
	env.run_native(record, reach=("returned",))
	assert env.strategy.drain_entered.wait(WAIT_TIMEOUT)
	# NVDA's cancel reaches the lifecycle, which asks the host to stop the record.
	env.host.cancel()
	with env.strategy.condition:
		stopped = env.strategy.condition.wait_for(lambda: record in env.strategy.native_stops, WAIT_TIMEOUT)
	env.strategy.drain_release.set()
	assert stopped, "cancel could not stop the record during drain"


def test_closed_record_admits_only_its_own_nested_consumers(env):
	record = env.host.new_record()
	env.host.begin(record)
	env.host.close(record)
	assert record.is_valid(), "closing admission does not invalidate the work"
	with env.host.consumer(record) as outsider:
		assert outsider is None
	with env.host.bound_callback(record), env.host.consumer(record) as nested:
		assert nested is record
	env.host.wait_consumers(record)
	assert record.consumers == 0


def test_abandon_retires_a_dropped_record_without_handoff(env):
	# No lifecycle thread runs this operation, so no handoff ever comes.
	events = Events()
	token = env.scheduler.CancellationToken()
	context = env.rt.models.PlaybackContext(object(), 32)
	operation = env.host._lifecycle.accept(context, token, events.append)
	env.host.enqueue(("dropped",), operation)
	record = env.strategy.wait_submitted()
	finished = Event()
	Thread(target=lambda: (env.host.abandon(record), finished.set()), daemon=True).start()
	assert finished.wait(WAIT_TIMEOUT), "abandon() waited for a handoff that never comes"
	assert record.retired.is_set()
	env.host.abandon(record)  # idempotent
	stays_false(events.condition, lambda: bool(events), message=lambda: f"unexpected events {list(events)}")


def test_reset_recovers_from_a_control_error(env):
	env.host.latch_control_error(OSError("stop failed"))
	_, _, rejected = env.speak()
	assert rejected.wait_one().kind is env.rt.models.EventKind.SEGMENT_FAILED
	with env.host.admission():
		env.host.reset()
	assert env.host.control_error is None
	_, _, events = env.speak(segment=18)
	env.run_native(env.strategy.wait_submitted())
	assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED


def test_reset_recovers_from_a_lifecycle_fault(env, monkeypatch):
	boundary = env.host.wait_native_boundary

	def broken(operation):
		boundary(operation)
		raise RuntimeError("hook failed")

	monkeypatch.setattr(env.host, "wait_native_boundary", broken)
	_, _, failed = env.speak()
	env.run_native(env.strategy.wait_submitted())
	assert failed.wait_one().kind is env.rt.models.EventKind.SEGMENT_FAILED
	_, _, rejected = env.speak(segment=18)
	assert rejected.wait_one().kind is env.rt.models.EventKind.SEGMENT_FAILED
	monkeypatch.undo()
	with env.host.admission():
		env.host.reset()
	_, _, events = env.speak(segment=19)
	env.run_native(env.strategy.wait_submitted(2))
	assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED


def test_faulted_reports_a_control_error_or_lifecycle_fault_until_reset(env, monkeypatch):
	assert env.host.faulted is False
	env.host.latch_control_error(OSError("stop failed"))
	assert env.host.faulted is True
	with env.host.admission():
		env.host.reset()
	assert env.host.faulted is False
	boundary = env.host.wait_native_boundary

	def broken(operation):
		boundary(operation)
		raise RuntimeError("hook failed")

	monkeypatch.setattr(env.host, "wait_native_boundary", broken)
	_, _, failed = env.speak()
	env.run_native(env.strategy.wait_submitted())
	assert failed.wait_one().kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert env.host.control_error is None
	assert env.host.faulted is True
	monkeypatch.undo()
	with env.host.admission():
		env.host.reset()
	assert env.host.faulted is False


def test_hook_fault_stops_the_player_and_releases_the_worker(env, monkeypatch):
	boundary = env.host.wait_native_boundary

	def broken(operation):
		boundary(operation)
		raise RuntimeError("hook failed")

	monkeypatch.setattr(env.host, "wait_native_boundary", broken)
	_, _, events = env.speak()
	native, _ = env.run_native(env.strategy.wait_submitted())
	assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_FAILED
	native.join(WAIT_TIMEOUT)
	assert not native.is_alive(), "the FIFO worker stayed parked after a hook fault"
	assert env.strategy.player_stops >= 1


def test_stop_skips_a_record_abandoned_before_native_work(env):
	# The record retired without native work; stopping it would reach engine
	# data that was never bound.
	env.strategy.submit_error = RuntimeError("queue rejected")
	_, _, events = env.speak()
	assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_FAILED
	env.host.wait_idle()
	assert env.strategy.native_stops == []


def test_enqueue_skips_submission_for_invalid_work(env):
	token = env.scheduler.CancellationToken()
	context = env.rt.models.PlaybackContext(object(), 30)
	operation = env.host._lifecycle.accept(context, token, lambda event: None)
	token.cancel()
	env.host.enqueue(("late",), operation)
	assert env.strategy.submitted == []


def test_segment_submit_error_is_recorded_not_raised(env):
	token = env.scheduler.CancellationToken()
	context = env.rt.models.PlaybackContext(object(), 31)
	operation = env.host._lifecycle.accept(context, token, lambda event: None)
	env.strategy.submit_error = RuntimeError("queue rejected")
	env.host.enqueue(("segment",), operation)
	record = native_record(env.host, operation)
	assert isinstance(record.error, RuntimeError)
	assert record.retired.is_set()


def test_ordinary_submit_error_is_raised(env):
	env.strategy.submit_error = RuntimeError("queue rejected")
	with pytest.raises(RuntimeError, match="queue rejected"):
		env.host.enqueue(("ordinary",))


def test_boundary_hook_ignores_an_operation_without_a_record(env):
	token = env.scheduler.CancellationToken()
	context = env.rt.models.PlaybackContext(object(), 32)
	operation = env.host._lifecycle.accept(context, token, lambda event: None)
	env.host.wait_native_boundary(operation)


def test_leased_player_passes_on_done_by_keyword_and_records_its_error(env):
	class KeywordPlayer:
		def __init__(self):
			self.callbacks = []

		def feed(self, data, onDone=None):
			self.callbacks.append(onDone)

	real = KeywordPlayer()
	player = env.module.LeasedPlayer(env.host, real)
	record = env.host.new_record()
	env.host.begin(record)
	failure = OSError("index failed")

	def on_done():
		raise failure

	player.feed(b"pcm", onDone=on_done)
	with pytest.raises(OSError):
		real.callbacks[0]()
	assert record.error is failure


def test_engine_admission_error_rejects_before_acceptance(env):
	env.strategy.admission_error = lambda host: RuntimeError("route cannot drain")
	_, _, events = env.speak(segment=33)
	event = events.wait_one()
	assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert str(event.error) == "route cannot drain"
	assert event.segment_id == 33
	assert env.strategy.submitted == []
	assert accepted_operations(env.host) == {}


def test_audio_consumer_is_admitted_after_close(env):
	env.speak()
	record = env.strategy.wait_submitted()
	env.host.begin(record)
	env.host.close(record)
	with env.host.consumer(record) as plain:
		assert plain is None
	with env.host.consumer(record, audio=True) as audio:
		assert audio is record
	env.run_native(record)


def test_retire_seals_the_record_against_audio_consumers(env):
	_, _, events = env.speak()
	record = env.strategy.wait_submitted()
	env.host.begin(record)
	env.host.close(record)
	held, release = Event(), Event()

	def hold():
		with env.host.consumer(record, audio=True) as admitted:
			assert admitted is record
			held.set()
			assert release.wait(HOLD_TIMEOUT)

	Thread(target=hold, daemon=True).start()
	assert held.wait(WAIT_TIMEOUT)
	for barrier in ("returned", PLAYED_OUT):
		env.host.reach(record, barrier)
	Thread(target=env.host.retire, args=(record,), daemon=True).start()
	eventually(lambda: record.closed)
	with env.host.consumer(record, audio=True) as late:
		assert late is None
	assert env.host.current() is record
	release.set()
	assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED


def test_retire_runs_finish_after_consumers_and_before_retirement(env):
	_, _, events = env.speak()
	record = env.strategy.wait_submitted()
	env.host.begin(record)
	order = []
	held, release = Event(), Event()

	def hold():
		with env.host.consumer(record) as admitted:
			assert admitted is record
			held.set()
			assert release.wait(HOLD_TIMEOUT)
			order.append("consumer")

	def finish():
		order.append(("finish", record.consumers, record.retired.is_set(), env.host.current() is record))

	Thread(target=hold, daemon=True).start()
	assert held.wait(WAIT_TIMEOUT)
	for barrier in ("returned", PLAYED_OUT):
		env.host.reach(record, barrier)
	Thread(target=lambda: env.host.retire(record, finish=finish), daemon=True).start()
	release.set()
	assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED
	assert order == ["consumer", ("finish", 0, False, True)]


def test_finish_error_fails_only_that_segment(env):
	_, _, failed = env.speak()
	record = env.strategy.wait_submitted()
	env.host.begin(record)
	for barrier in ("returned", PLAYED_OUT):
		env.host.reach(record, barrier)

	def finish():
		raise OSError("delete failed")

	Thread(target=lambda: env.host.retire(record, finish=finish), daemon=True).start()
	event = failed.wait_one()
	assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert isinstance(event.error, OSError)
	_, _, events = env.speak(segment=18)
	env.run_native(env.strategy.wait_submitted(2))
	assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED


def test_wait_settled_waits_for_the_record_to_leave_the_worker(env):
	env.speak()
	record = env.strategy.wait_submitted()
	env.host.begin(record)
	settled = Event()
	Thread(target=lambda: (env.host.wait_settled(record), settled.set()), daemon=True).start()
	stays_unset(settled)
	env.run_native(record)
	assert settled.wait(WAIT_TIMEOUT)


def test_wait_settled_from_the_records_own_callback_does_not_wait(env):
	env.speak()
	record = env.strategy.wait_submitted()
	env.host.begin(record)
	settled = Event()

	def settle():
		with env.host.bound_callback(record):
			env.host.wait_settled(record)
		settled.set()

	Thread(target=settle, daemon=True).start()
	assert settled.wait(WAIT_TIMEOUT)
	env.run_native(record)


def test_wait_settled_waits_for_a_running_sink(env):
	entered, release = Event(), Event()

	def sink(event):
		entered.set()
		assert release.wait(HOLD_TIMEOUT)

	env.speak(sink=sink)
	env.run_native(env.strategy.wait_submitted())
	assert entered.wait(WAIT_TIMEOUT)
	settled = Event()
	Thread(target=lambda: (env.host.wait_settled(None), settled.set()), daemon=True).start()
	stays_unset(settled)
	release.set()
	assert settled.wait(WAIT_TIMEOUT)


def test_wait_settled_from_a_sink_does_not_wait_for_sinks(env):
	settled = Event()

	def sink(event):
		env.host.wait_settled(None)
		settled.set()

	env.speak(sink=sink)
	env.run_native(env.strategy.wait_submitted())
	assert settled.wait(WAIT_TIMEOUT)


def test_wait_settled_from_a_callback_does_not_wait_for_sinks(env):
	entered, release = Event(), Event()

	def sink(event):
		entered.set()
		assert release.wait(HOLD_TIMEOUT)

	env.speak(sink=sink)
	first = env.strategy.wait_submitted()
	env.run_native(first)
	assert entered.wait(WAIT_TIMEOUT)
	settled = Event()

	def settle():
		with env.host.bound_callback(first):
			env.host.wait_settled(None)
		settled.set()

	Thread(target=settle, daemon=True).start()
	try:
		assert settled.wait(WAIT_TIMEOUT)
	finally:
		release.set()


def test_control_error_fails_an_unpublished_drain(env):
	entered, release = Event(), Event()

	def blocking(event):
		entered.set()
		assert release.wait(HOLD_TIMEOUT)

	env.speak(segment=17, sink=blocking)
	env.run_native(env.strategy.wait_submitted())
	assert entered.wait(WAIT_TIMEOUT)
	_, _, events = env.speak(segment=18)
	env.run_native(env.strategy.wait_submitted(2))
	env.host.wait_idle()
	env.host.latch_control_error(OSError("stop failed"))
	release.set()
	assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_FAILED


def test_control_error_relabels_a_drain_the_lifecycle_already_committed(env, monkeypatch):
	# lifecycle.fail() can land after the delivery thread read the result; the
	# host itself must not publish success once the control error is latched.
	monkeypatch.setattr(env.host._lifecycle, "fail", lambda operation, error: None)
	entered, release = Event(), Event()

	def blocking(event):
		entered.set()
		assert release.wait(HOLD_TIMEOUT)

	env.speak(segment=17, sink=blocking)
	env.run_native(env.strategy.wait_submitted())
	assert entered.wait(WAIT_TIMEOUT)
	_, _, events = env.speak(segment=18)
	env.run_native(env.strategy.wait_submitted(2))
	env.host.wait_idle()
	env.host.latch_control_error(OSError("stop failed"))
	release.set()
	event = events.wait_one()
	assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert str(event.error) == "stop failed"


def test_control_error_stops_the_active_segment(env):
	# A control error stops the active segment at once; it never reports success.
	_, _, events = env.speak()
	record = env.strategy.wait_submitted()
	env.host.begin(record)
	env.host.latch_control_error(OSError("stop failed"))
	eventually(lambda: record in env.strategy.native_stops)
	env.run_native(record)
	assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_FAILED


class PreparingStrategy(FakeStrategy):
	"""A strategy that converts commands in prepare() before submission."""

	def __init__(self):
		super().__init__()
		self.prepare_entered = Event()
		self.prepare_release = Event()
		self.prepare_release.set()
		self.prepare_error = None

	def prepare(self, host, commands, operation):
		self.prepare_entered.set()
		assert self.prepare_release.wait(HOLD_TIMEOUT), "Test did not release prepare"
		if self.prepare_error is not None:
			raise self.prepare_error
		return ("prepared", *commands)


@pytest.fixture
def prepare_env(env):
	strategy = native(env.module, PreparingStrategy)
	env.host._strategy = strategy
	env.strategy = strategy
	return env


def test_prepare_result_is_what_submit_receives(prepare_env):
	env = prepare_env
	env.speak()
	record = env.strategy.wait_submitted()
	assert env.strategy.submitted[0][1] == ("prepared", "hello")
	env.host.enqueue(("ordinary",))
	env.strategy.wait_submitted(2)
	assert env.strategy.submitted[1][1] == ("prepared", "ordinary")
	env.run_native(record)


def test_cancel_does_not_wait_for_prepare(prepare_env):
	env = prepare_env
	env.strategy.prepare_release.clear()
	_, _, events = env.speak()
	assert env.strategy.prepare_entered.wait(WAIT_TIMEOUT)
	cancelled = Event()
	Thread(target=lambda: (env.host.cancel(), cancelled.set()), daemon=True).start()
	try:
		assert cancelled.wait(WAIT_TIMEOUT), "cancel() waited for prepare()"
	finally:
		env.strategy.prepare_release.set()
	stays_false(events.condition, lambda: bool(events), message=lambda: f"unexpected events {list(events)}")
	assert env.strategy.submitted == []


def test_segment_prepare_error_fails_only_that_segment(prepare_env):
	env = prepare_env
	env.strategy.prepare_error = ValueError("conversion failed")
	_, _, failed = env.speak()
	event = failed.wait_one()
	assert event.kind is env.rt.models.EventKind.SEGMENT_FAILED
	assert isinstance(event.error, ValueError)
	env.strategy.prepare_error = None
	_, _, events = env.speak(segment=18)
	env.run_native(env.strategy.wait_submitted())
	assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED


def test_ordinary_prepare_error_is_raised(prepare_env):
	env = prepare_env
	env.strategy.prepare_error = ValueError("conversion failed")
	with pytest.raises(ValueError, match="conversion failed"):
		env.host.enqueue(("ordinary",))
	assert env.strategy.submitted == []


def test_wait_idle_returns_once_the_last_segment_retires(env):
	env.speak()
	record = env.strategy.wait_submitted()
	waited = Event()
	Thread(target=lambda: (env.host.wait_idle(), waited.set()), daemon=True).start()
	stays_unset(waited)
	env.run_native(record)
	assert waited.wait(WAIT_TIMEOUT)


def test_default_hooks_finish_a_segment(env):
	class Bare(env.module.NativeStrategy):
		barriers = frozenset({PLAYED_OUT})

		def __init__(self):
			self.submitted = Event()
			self.record = None

		def submit(self, host, record, commands):
			self.record = record
			self.submitted.set()

		def stop_native(self, host, record):
			pass

		def stop_player(self, host):
			pass

	strategy = Bare()
	assert strategy.prepare(None, ("x",), None) == ("x",)
	assert strategy.admission_error(None) is None
	assert strategy.drain(None, None) is None
	host = env.module.SegmentHost("Bare", strategy)
	events = Events()
	context = env.rt.models.PlaybackContext(object(), 31)
	host.speak_segment(("hello",), env.scheduler.CancellationToken(), context=context, on_event=events.append)
	assert strategy.submitted.wait(WAIT_TIMEOUT)

	def work():
		host.begin(strategy.record)
		host.reach(strategy.record, PLAYED_OUT)
		host.retire(strategy.record)

	worker = Thread(target=work, daemon=True)
	worker.start()
	try:
		assert events.wait_one().kind is env.rt.models.EventKind.SEGMENT_DRAINED
	finally:
		worker.join(2)
		host.terminate()


def test_terminated_host_rejects_new_ordinary_speech(env):
	env.host.terminate()
	with pytest.raises(RuntimeError, match="Fake driver has terminated"):
		env.host.enqueue(("late",))
	assert env.strategy.submitted == []


def test_leased_player_hooks_can_be_overridden(env):
	calls = []

	class Raw:
		def feed(self, data, size=None, onDone=None):
			calls.append(("feed", data, onDone is not None))
			raise OSError("feed failed")

		def stop(self):
			raise OSError("stop failed")

	class Custom(env.module.LeasedPlayer):
		def _callback(self, record, onDone):
			calls.append("callback")
			return onDone

		def _record_error(self, record, error):
			calls.append(("record_error", str(error)))

		def _stop_failed(self, error):
			calls.append(("stop_failed", str(error)))

	player = Custom(env.host, Raw())
	_, _, events = env.speak()
	record = env.strategy.wait_submitted()
	env.host.begin(record)
	with pytest.raises(OSError, match="feed failed"):
		player.feed(b"pcm", onDone=lambda: None)
	with pytest.raises(OSError, match="stop failed"):
		player.stop()
	assert calls == [
		"callback",
		("feed", b"pcm", True),
		("record_error", "feed failed"),
		("stop_failed", "stop failed"),
	]
	assert env.host.control_error is None
	env.run_native(record)
	events.wait_one()


def test_feed_admitted_serves_subclasses_that_choose_their_record(env):
	class Raw:
		def __init__(self):
			self.fed = []

		def feed(self, data, size=None, onDone=None):
			self.fed.append((data, size))

		def stop(self):
			pass

	class Bound(env.module.LeasedPlayer):
		def feed(self, data, onDone=None):
			record = self._host.current()
			with self._host.consumer(record) as admitted:
				if admitted is None:
					return None
				return self._feed_admitted(admitted, data, None, onDone)

	raw = Raw()
	player = Bound(env.host, raw)
	_, _, events = env.speak()
	record = env.strategy.wait_submitted()
	env.host.begin(record)
	player.feed(b"pcm")
	assert raw.fed == [(b"pcm", None)]
	env.run_native(record)
	events.wait_one()


def test_abandoning_the_current_record_wakes_settle_waiters(env):
	env.host.enqueue(("ordinary",))
	record = env.strategy.wait_submitted()
	env.host.begin(record)
	settled = Event()
	waiter = Thread(target=lambda: (env.host.wait_settled(record), settled.set()), daemon=True)
	waiter.start()
	stays_unset(settled)
	env.host.abandon(record)
	assert settled.wait(WAIT_TIMEOUT), "wait_settled missed the abandon"


def test_a_strategy_without_barriers_is_rejected(env):
	class Barrierless(FakeStrategy):
		barriers = frozenset()

	with pytest.raises(ValueError, match="^Fake strategy declares no played-out barrier$"):
		env.module.SegmentHost("Fake", native(env.module, Barrierless))


def test_a_strategy_without_played_out_is_rejected(env):
	# Without PLAYED_OUT a segment would drain before its audio has played.
	class NotPlayedOut(FakeStrategy):
		barriers = frozenset({"returned"})

	with pytest.raises(ValueError, match="^Fake strategy declares no played-out barrier$"):
		env.module.SegmentHost("Fake", native(env.module, NotPlayedOut))


def test_ordinary_barrier_sets_need_no_played_out(env):
	# Ordinary speech keeps the parent's own playback end (VE's set is empty).
	env.host.enqueue(("ordinary",), barriers=frozenset())
	record = env.strategy.wait_submitted()
	assert record.barriers == {}


def test_segment_drain_core_combines_with_an_abcmeta_driver_metaclass(env):
	# NVDA's SynthDriver has the metaclass baseObject.AutoPropertyType(ABCMeta); a Protocol's
	# _ProtocolMeta would conflict with it, an ABC does not. The suite's stub drivers are plain classes.
	from abc import ABCMeta

	core = env.module.SegmentDrainCore
	assert type(core) is ABCMeta

	class DriverMeta(ABCMeta):
		pass

	class Driver(metaclass=DriverMeta):
		pass

	class Wrapper(Driver, core):
		def get_segment_drain_support(self, *, nvda_version, audio_mode):
			return None

		def speak_segment(self, commands, token, *, context, on_event):
			return None

	assert type(Wrapper) is DriverMeta
	Wrapper()

	class Incomplete(Driver, core):
		def speak_segment(self, commands, token, *, context, on_event):
			return None

	with pytest.raises(TypeError):
		Incomplete()


def test_nvda_driver_metaclass_is_an_abcmeta():
	# The stand-in metaclass above, and the drain harnesses', model this: NVDA's AutoPropertyType.
	import ast

	tree = ast.parse((REF / "nvda/source/baseObject.py").read_text(encoding="utf-8"))
	meta = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "AutoPropertyType")
	assert [ast.unparse(base) for base in meta.bases] == ["ABCMeta"]


def test_segment_host_speaker_forwards_to_the_core_host(env):
	# Every bundled wrapper takes speak_segment from this mixin: the call reaches its own host unchanged.
	calls = []

	class Host:
		def speak_segment(self, *args, **kwargs):
			calls.append((args, kwargs))

	class Core(env.module.SegmentHostSpeaker):
		def __init__(self):
			self._segmentHost = Host()

		def get_segment_drain_support(self, *, nvda_version, audio_mode):
			return None

	commands, token, context, sink = ("text",), object(), object(), object()
	assert Core().speak_segment(commands, token, context=context, on_event=sink) is None
	assert calls == [((commands, token), {"context": context, "on_event": sink})]


def test_segment_host_speaker_leaves_drain_support_abstract(env):
	# The mixin is the bridge's SegmentDrainCore; each wrapper still decides drain support itself.
	speaker = env.module.SegmentHostSpeaker
	assert issubclass(speaker, env.module.SegmentDrainCore)

	class Bare(speaker):
		pass

	with pytest.raises(TypeError):
		Bare()
