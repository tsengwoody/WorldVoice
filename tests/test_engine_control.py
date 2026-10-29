"""Shared engine control parts: stop gate, queued records, control-fault policy."""

from threading import Condition, Event, Lock, Thread

import pytest
from addon_loader import load_source
from runtime_harness import RUNTIME, load_runtime
from waiting import HOLD_TIMEOUT, WAIT_TIMEOUT, stays_unset


@pytest.fixture
def control(monkeypatch):
	rt = load_runtime(monkeypatch)
	return load_source(monkeypatch, f"{rt.package.__name__}.engineControl", RUNTIME / "engineControl.py")


def test_stop_gate_blocks_until_every_stop_returns(control):
	condition = Condition()
	gate = control.StopGate(condition)
	assert gate.clear
	entered, release, woke = Event(), Event(), Event()

	def stopper():
		with gate.hold(), gate.hold():
			entered.set()
			release.wait(HOLD_TIMEOUT)

	def worker():
		with condition:
			condition.wait_for(lambda: gate.clear, HOLD_TIMEOUT)
		woke.set()

	Thread(target=stopper, daemon=True).start()
	assert entered.wait(WAIT_TIMEOUT)
	with condition:
		assert not gate.clear
	Thread(target=worker, daemon=True).start()
	stays_unset(woke)
	release.set()
	assert woke.wait(WAIT_TIMEOUT)


def test_stop_gate_releases_after_an_error(control):
	gate = control.StopGate(Condition())
	with pytest.raises(OSError), gate.hold():
		raise OSError("stop failed")
	assert gate.clear


def test_queued_records(control):
	queued = control.QueuedRecords()
	a, b = object(), object()
	queued.add(1, a)
	queued.add(2, b)
	assert len(queued) == 2
	assert queued.pop(1) is a
	assert queued.pop(1) is None
	assert queued.take_all() == [b]
	assert len(queued) == 0


def test_control_fault_latches_once_and_abandons_outside_the_lock(control):
	condition = Condition()
	latched, abandoned = [], []

	class Host:
		control_error = None

		def latch_control_error(self, error):
			latched.append(error)
			self.control_error = error

		def abandon(self, record):
			# abandon waits for consumers that may need the engine lock.
			acquired = condition.acquire(timeout=WAIT_TIMEOUT)
			assert acquired, "abandon ran while the engine lock was held by another thread"
			condition.release()
			abandoned.append(record)

	records = [object(), object()]
	drops = []

	def drop():
		drops.append(True)
		return list(records)

	policy = control.ControlFaultPolicy(Host(), condition, drop)
	error = OSError("stop failed")
	result = []
	thread = Thread(target=lambda: result.append(policy.fail(error)))
	thread.start()
	thread.join(WAIT_TIMEOUT)
	assert result == [True]
	assert latched == [error] and abandoned == records and drops == [True]
	assert policy.fail(OSError("again")) is False
	assert latched == [error] and drops == [True]


def test_stop_gate_two_phase_enter_and_leave(control):
	condition = Condition()
	gate = control.StopGate(condition)
	woke = Event()
	with condition:
		gate.enter()
		assert not gate.clear

	def worker():
		with condition:
			condition.wait_for(lambda: gate.clear, HOLD_TIMEOUT)
		woke.set()

	Thread(target=worker, daemon=True).start()
	stays_unset(woke)
	with condition:
		gate.leave()
	assert woke.wait(WAIT_TIMEOUT)


class _FaultHost:
	"""A host that records latches and abandons."""

	def __init__(self, abandon=None):
		self.control_error = None
		self.latched, self.abandoned = [], []
		self._abandon = abandon

	def latch_control_error(self, error):
		self.latched.append(error)
		self.control_error = error

	def abandon(self, record):
		if self._abandon is not None:
			self._abandon(record)
		self.abandoned.append(record)


def test_capture_drops_under_the_lock_and_returns_none_once_latched(control):
	condition = Condition()
	host = _FaultHost()
	records = [object(), object()]
	owned = []

	def drop():
		owned.append(condition._is_owned())
		return list(records)

	policy = control.ControlFaultPolicy(host, condition, drop)
	error = OSError("stop failed")
	fault = policy.capture(error)
	assert fault.error is error and fault.dropped == tuple(records)
	assert owned == [True] and host.latched == [error] and host.abandoned == []
	assert policy.capture(OSError("again")) is None
	assert owned == [True]


def test_deliver_runs_after_even_when_an_abandon_raises(control):
	def abandon(record):
		raise OSError("abandon failed")

	host = _FaultHost(abandon)
	afters = []
	policy = control.ControlFaultPolicy(host, Condition(), lambda: [object()], after=afters.append)
	fault = policy.capture(OSError("stop failed"))
	with pytest.raises(OSError, match="abandon failed"):
		policy.deliver(fault)
	assert afters == [fault]
	policy.deliver(None)
	assert afters == [fault]


def test_deferred_delivers_after_the_outermost_block_outside_a_lock(control):
	lock = Lock()
	host = _FaultHost()
	records = [object()]
	free = []

	def after(fault):
		acquired = lock.acquire(blocking=False)
		free.append(acquired)
		if acquired:
			lock.release()

	policy = control.ControlFaultPolicy(host, Condition(), lambda: list(records), after=after)
	error = OSError("stop failed")
	with policy.deferred(), lock:
		with policy.deferred():
			assert policy.fail(error) is True
		assert host.abandoned == [] and free == []
		assert policy.fail(OSError("again")) is False
	assert host.abandoned == records and free == [True]
	assert host.latched == [error]


def test_fail_without_drop_only_latches(control):
	host = _FaultHost()
	policy = control.ControlFaultPolicy(host, Condition())
	error = OSError("stop failed")
	assert policy.fail(error) is True
	assert host.latched == [error] and host.abandoned == []
	assert policy.fail(OSError("again")) is False


def test_deferred_block_without_a_fault_delivers_nothing(control, monkeypatch):
	policy = control.ControlFaultPolicy(_FaultHost(), Condition())
	delivered = []
	monkeypatch.setattr(policy, "deliver", delivered.append)
	with policy.deferred():
		pass
	assert delivered == []


def test_release_newest_first_runs_every_release_in_reverse_and_logs_failures(control):
	# A constructor that raises releases what it built, newest first; a failed step is logged with
	# the wrapper's message and the older ones still run.
	calls, logged = [], []

	class Logger:
		def error(self, *args, **kwargs):
			logged.append((args, kwargs))

	def failing():
		calls.append("b")
		raise OSError("release failed")

	releases = [lambda: calls.append("a"), failing, lambda: calls.append("c")]
	assert control.release_newest_first(releases, logger=Logger(), message="cleanup failed") is None
	assert calls == ["c", "b", "a"]
	assert logged == [(("cleanup failed",), {"exc_info": True})]
	control.release_newest_first([], logger=Logger(), message="cleanup failed")
	assert len(logged) == 1


def test_release_newest_first_lets_a_base_exception_escape(control):
	# Only Exception is caught: a KeyboardInterrupt in a release escapes at once, the older
	# releases do not run and nothing is logged, as with the wrappers' own loops before.
	calls, logged = [], []

	class Logger:
		def error(self, *args, **kwargs):
			logged.append((args, kwargs))

	def interrupted():
		calls.append("b")
		raise KeyboardInterrupt

	releases = [lambda: calls.append("a"), interrupted, lambda: calls.append("c")]
	with pytest.raises(KeyboardInterrupt):
		control.release_newest_first(releases, logger=Logger(), message="cleanup failed")
	assert calls == ["c", "b"]
	assert logged == []
