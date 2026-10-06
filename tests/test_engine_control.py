"""Shared engine control parts: stop gate, queued records, control-fault policy."""

import importlib.util
import sys
from threading import Condition, Event, Thread
from types import SimpleNamespace

import pytest

from runtime_harness import RUNTIME, load_runtime
from waiting import stays_unset


@pytest.fixture
def control(monkeypatch):
	rt = load_runtime(monkeypatch)
	name = f"{rt.package.__name__}.engineControl"
	spec = importlib.util.spec_from_file_location(name, RUNTIME / "engineControl.py")
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, name, module)
	spec.loader.exec_module(module)
	return module


def test_stop_gate_blocks_until_every_stop_returns(control):
	condition = Condition()
	gate = control.StopGate(condition)
	assert gate.clear
	entered, release, woke = Event(), Event(), Event()

	def stopper():
		with gate.hold():
			with gate.hold():
				entered.set()
				release.wait(2)

	def worker():
		with condition:
			condition.wait_for(lambda: gate.clear, 2)
		woke.set()

	Thread(target=stopper, daemon=True).start()
	assert entered.wait(2)
	with condition:
		assert not gate.clear
	Thread(target=worker, daemon=True).start()
	stays_unset(woke)
	release.set()
	assert woke.wait(2)


def test_stop_gate_releases_after_an_error(control):
	gate = control.StopGate(Condition())
	with pytest.raises(OSError):
		with gate.hold():
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
			acquired = condition.acquire(timeout=1)
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
	thread.join(2)
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
			condition.wait_for(lambda: gate.clear, 2)
		woke.set()

	Thread(target=worker, daemon=True).start()
	stays_unset(woke)
	with condition:
		gate.leave()
	assert woke.wait(2)
