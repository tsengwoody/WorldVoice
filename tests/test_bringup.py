"""Teardown, step timing and attribute patches used to assemble the driver."""

from types import SimpleNamespace

import pytest
from addon_loader import WORLDVOICE, load_source


@pytest.fixture
def bringup():
	return load_source(None, "bringup_under_test", WORLDVOICE / "bringup.py", register=False)


class Log:
	def __init__(self):
		self.debugs, self.errors = [], []

	def debug(self, *args):
		self.debugs.append(args)

	def error(self, *args, **kwargs):
		self.errors.append((args, kwargs))


def test_teardown_runs_in_declared_order_not_registration_order(bringup):
	ran = []
	teardown = bringup.Teardown(("a", "b", "c"), Log())
	teardown.add("c", lambda: ran.append("c"))
	teardown.add("a", lambda: ran.append("a"))
	teardown.run()
	assert ran == ["a", "c"]


def test_teardown_rejects_unknown_and_duplicate_names(bringup):
	teardown = bringup.Teardown(("a",), Log())
	with pytest.raises(ValueError):
		teardown.add("z", lambda: None)
	teardown.add("a", lambda: None)
	with pytest.raises(ValueError):
		teardown.add("a", lambda: None)


def test_teardown_logs_a_failure_and_continues(bringup):
	ran, log = [], Log()
	teardown = bringup.Teardown(("a", "b"), log)
	teardown.add("a", lambda: 1 / 0)
	teardown.add("b", lambda: ran.append("b"))
	teardown.run()
	assert ran == ["b"]
	assert log.errors == [(("WorldVoice terminate: %s", "a"), {"exc_info": True})]


def test_teardown_lets_interrupts_through(bringup):
	ran = []

	def interrupt():
		raise KeyboardInterrupt

	teardown = bringup.Teardown(("a", "b"), Log())
	teardown.add("a", interrupt)
	teardown.add("b", lambda: ran.append("b"))
	with pytest.raises(KeyboardInterrupt):
		teardown.run()
	assert ran == []


def test_teardown_runs_once(bringup):
	ran = []
	teardown = bringup.Teardown(("a",), Log())
	teardown.add("a", lambda: ran.append("a"))
	teardown.run()
	teardown.run()
	assert ran == ["a"]


def test_timed_logs_label_and_seconds(bringup, monkeypatch):
	clock = iter([1.0, 1.25])
	monkeypatch.setattr(bringup.time, "perf_counter", lambda: next(clock))
	log = Log()
	with bringup.timed(log, "TaskManager"):
		pass
	assert log.debugs == [("WorldVoice init timing: %s %.3fs", "TaskManager", 0.25)]


def test_timed_logs_and_reraises_on_failure(bringup):
	log = Log()
	with pytest.raises(ZeroDivisionError), bringup.timed(log, "step"):
		raise ZeroDivisionError
	assert [entry[1] for entry in log.debugs] == ["step"]


def test_timed_without_logger(bringup):
	with bringup.timed(None, "step"):
		pass


def test_patch_attribute_restores_once(bringup):
	owner = SimpleNamespace(value="original")
	restore = bringup.patch_attribute(owner, "value", "patched")
	assert owner.value == "patched"
	restore()
	assert owner.value == "original"
	owner.value = "newer"
	restore()
	assert owner.value == "newer"


def test_teardown_refuses_registration_after_it_ran(bringup):
	teardown = bringup.Teardown(("a",), Log())
	teardown.run()
	with pytest.raises(RuntimeError):
		teardown.add("a", lambda: None)
