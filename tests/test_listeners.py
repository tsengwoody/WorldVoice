"""The one listener list of the settings services: a failing listener is logged, the rest are told."""

import ast
import sys

import pytest
from addon_loader import WORLDVOICE, load_source
from mutation_support import running_under_mutmut

PATH = WORLDVOICE / "listeners.py"
MESSAGE = "WorldVoice: test listener failed"


class RecordingLogger:
	def __init__(self):
		self.errors = []

	def error(self, *args, **kwargs):
		self.errors.append((args, kwargs))


@pytest.fixture
def logger():
	return RecordingLogger()


@pytest.fixture
def listeners(monkeypatch, logger):
	return load_source(monkeypatch, "listeners_under_test", PATH).Listeners(logger, MESSAGE)


def test_listeners_isolate_a_failing_listener(listeners, logger):
	seen, other = [], []

	def failing(value):
		raise RuntimeError("listener failed")

	listeners.subscribe(seen.append)
	listeners.subscribe(failing)
	listeners.subscribe(other.append)
	listeners.notify("x")
	assert seen == other == ["x"]
	assert logger.errors == [((MESSAGE,), {"exc_info": True})]


def test_listeners_tell_each_listener_once_in_subscription_order(listeners):
	calls = []

	def a(value):
		calls.append(("a", value))

	def b(value):
		calls.append(("b", value))

	listeners.subscribe(a)
	listeners.subscribe(b)
	listeners.subscribe(a)
	listeners.notify(1)
	assert calls == [("a", 1), ("b", 1)]


def test_unsubscribing_an_unknown_listener_is_ignored(listeners):
	seen = []
	listeners.unsubscribe(print)
	listeners.subscribe(seen.append)
	listeners.unsubscribe(seen.append)
	listeners.unsubscribe(seen.append)
	listeners.notify(1)
	assert seen == []


def test_a_bound_method_is_matched_by_equality(listeners):
	# The driver subscribes self._applyPipelineSettings, a new bound method on each access.
	class Holder:
		def __init__(self):
			self.seen = []

		def method(self, value):
			self.seen.append(value)

	holder = Holder()
	listeners.subscribe(holder.method)
	listeners.subscribe(holder.method)
	listeners.notify(1)
	listeners.unsubscribe(holder.method)
	listeners.notify(2)
	assert holder.seen == [1]


def test_a_listener_may_unsubscribe_while_told(listeners):
	calls = []

	def first(value):
		calls.append(("first", value))
		listeners.unsubscribe(second)
		listeners.unsubscribe(first)

	def second(value):
		calls.append(("second", value))

	listeners.subscribe(first)
	listeners.subscribe(second)
	listeners.notify(1)
	listeners.notify(2)
	assert calls == [("first", 1), ("second", 1)]


def test_notify_passes_positional_and_keyword_arguments(listeners):
	calls = []
	listeners.subscribe(lambda *args, **kwargs: calls.append((args, kwargs)))
	listeners.notify(1, changed=frozenset({"x"}))
	assert calls == [((1,), {"changed": frozenset({"x"})})]


def test_a_base_exception_is_not_swallowed(listeners, logger):
	def interrupted(value):
		raise KeyboardInterrupt

	listeners.subscribe(interrupted)
	with pytest.raises(KeyboardInterrupt):
		listeners.notify(1)
	assert logger.errors == []


# mutmut's copy imports mutmut, as tests/test_pipeline_structure.py notes.
@pytest.mark.skipif(running_under_mutmut(), reason="mutmut's copy imports mutmut")
def test_listeners_import_only_the_standard_library():
	# Portable core (refactor9 §6.1): no NVDA module, not even logHandler; the caller passes its logger.
	for node in ast.walk(ast.parse(PATH.read_text(encoding="utf-8"))):
		if isinstance(node, (ast.Import, ast.ImportFrom)):
			where = ast.unparse(node)
			assert isinstance(node, ast.Import) or node.level == 0, where
			modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module]
			assert all(module.split(".")[0] in sys.stdlib_module_names for module in modules), where
