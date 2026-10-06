"""Teardown, step timing and attribute patches used to assemble the driver."""

from types import SimpleNamespace

import pytest
from addon_loader import WORLDVOICE, load_source


@pytest.fixture
def assembly():
	return load_source(None, "assembly_under_test", WORLDVOICE / "assembly.py", register=False)


class Log:
	def __init__(self):
		self.debugs, self.errors = [], []

	def debug(self, *args):
		self.debugs.append(args)

	def error(self, *args, **kwargs):
		self.errors.append((args, kwargs))


def test_teardown_runs_in_declared_order_not_registration_order(assembly):
	ran = []
	teardown = assembly.Teardown(("a", "b", "c"), Log())
	teardown.add("c", lambda: ran.append("c"))
	teardown.add("a", lambda: ran.append("a"))
	teardown.run()
	assert ran == ["a", "c"]


def test_teardown_rejects_unknown_and_duplicate_names(assembly):
	teardown = assembly.Teardown(("a",), Log())
	with pytest.raises(ValueError):
		teardown.add("z", lambda: None)
	teardown.add("a", lambda: None)
	with pytest.raises(ValueError):
		teardown.add("a", lambda: None)


def test_teardown_logs_a_failure_and_continues(assembly):
	ran, log = [], Log()
	teardown = assembly.Teardown(("a", "b"), log)
	teardown.add("a", lambda: 1 / 0)
	teardown.add("b", lambda: ran.append("b"))
	teardown.run()
	assert ran == ["b"]
	assert log.errors == [(("WorldVoice terminate: %s", "a"), {"exc_info": True})]


def test_teardown_lets_interrupts_through(assembly):
	ran = []

	def interrupt():
		raise KeyboardInterrupt

	teardown = assembly.Teardown(("a", "b"), Log())
	teardown.add("a", interrupt)
	teardown.add("b", lambda: ran.append("b"))
	with pytest.raises(KeyboardInterrupt):
		teardown.run()
	assert ran == []


def test_teardown_runs_once(assembly):
	ran = []
	teardown = assembly.Teardown(("a",), Log())
	teardown.add("a", lambda: ran.append("a"))
	teardown.run()
	teardown.run()
	assert ran == ["a"]


def test_timed_logs_label_and_seconds(assembly, monkeypatch):
	clock = iter([1.0, 1.25])
	monkeypatch.setattr(assembly.time, "perf_counter", lambda: next(clock))
	log = Log()
	with assembly.timed(log, "TaskManager"):
		pass
	assert log.debugs == [("WorldVoice init timing: %s %.3fs", "TaskManager", 0.25)]


def test_timed_logs_and_reraises_on_failure(assembly):
	log = Log()
	with pytest.raises(ZeroDivisionError), assembly.timed(log, "step"):
		raise ZeroDivisionError
	assert [entry[1] for entry in log.debugs] == ["step"]


def test_timed_without_logger(assembly):
	with assembly.timed(None, "step"):
		pass


def test_patch_attribute_restores_once(assembly):
	owner = SimpleNamespace(value="original")
	restore = assembly.patch_attribute(owner, "value", "patched")
	assert owner.value == "patched"
	restore()
	assert owner.value == "original"
	owner.value = "newer"
	restore()
	assert owner.value == "newer"


def test_teardown_refuses_registration_after_it_ran(assembly):
	teardown = assembly.Teardown(("a",), Log())
	teardown.run()
	with pytest.raises(RuntimeError):
		teardown.add("a", lambda: None)
