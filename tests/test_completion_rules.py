"""The completion rule table is the one place that interprets a completion contract."""

import ast
import importlib.util
import sys

import pytest

from runtime_harness import RUNTIME, rt


@pytest.fixture
def completion(monkeypatch, rt):
	name = f"{rt.package.__name__}.completion"
	spec = importlib.util.spec_from_file_location(name, RUNTIME / "completion.py")
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, name, module)
	spec.loader.exec_module(module)
	return module


def _contract(rt, mode, contextual=False):
	models = rt.models
	mode = getattr(models.CompletionMode, mode)
	if mode is models.CompletionMode.LEGACY_DONE:
		return models.CompletionContract(legacy_contextual=contextual)
	return models.CompletionContract(mode, models.IndexRange(1, 10))


# correlated, segment_scoped, end_event, drain_event, fails_on_segment_failed,
# requires_end, requires_drain, entry
TABLE = {
	("LEGACY_DONE", False): (False, False, "DONE", None, False, True, False, "PLAIN"),
	("LEGACY_DONE", True): (False, True, "DONE", None, True, True, False, "LEGACY_SEGMENT"),
	("END_INDEX", False): (True, True, "SEGMENT_END", None, True, True, False, "PLAIN"),
	("END_INDEX_AND_DRAIN", False): (True, True, "SEGMENT_END", "SEGMENT_DRAINED", True, True, True, "SEGMENT"),
	("DRAIN", False): (True, True, "SEGMENT_END", "SEGMENT_DRAINED", True, False, True, "SEGMENT"),
}


@pytest.mark.parametrize("key", TABLE)
def test_rule_table_rows(completion, rt, key):
	rule = completion.rule_for(_contract(rt, *key))
	kinds = rt.models.EventKind
	correlated, scoped, end, drain, fails, requires_end, requires_drain, entry = TABLE[key]
	assert rule == completion.CompletionRule(
		correlated=correlated,
		segment_scoped=scoped,
		end_event=getattr(kinds, end),
		drain_event=getattr(kinds, drain) if drain else None,
		fails_on_segment_failed=fails,
		requires_end=requires_end,
		requires_drain=requires_drain,
		entry=getattr(completion.SpeakEntry, entry),
	)


def test_every_valid_contract_has_exactly_one_rule(completion, rt):
	modes = rt.models.CompletionMode
	valid = {(mode.name, False) for mode in modes} | {("LEGACY_DONE", True)}
	assert set(TABLE) == valid
	assert len({id(completion.rule_for(_contract(rt, *key))) for key in valid}) == len(valid)


@pytest.mark.parametrize("key", TABLE)
def test_rule_queries_read_only_the_rule_fields(completion, rt, key):
	rule = completion.rule_for(_contract(rt, *key))
	kinds, signal = rt.models.EventKind, completion.Signal
	assert rule.accepts_segment(7, 7) is rule.segment_scoped
	assert rule.accepts_segment(7, None) is not rule.segment_scoped
	assert rule.accepts_segment(7, 8) is False
	assert rule.signal_for(rule.end_event) is signal.END
	if rule.drain_event is not None:
		assert rule.signal_for(rule.drain_event) is signal.DRAIN
	expected_failure = signal.FAIL if rule.fails_on_segment_failed else None
	assert rule.signal_for(kinds.SEGMENT_FAILED) is expected_failure
	assert rule.signal_for(kinds.INDEX) is None
	for end_seen in (False, True):
		for drain_seen in (False, True):
			assert rule.is_complete(end_seen, drain_seen) is (
				(end_seen or not rule.requires_end) and (drain_seen or not rule.requires_drain))
			assert rule.indexes_finished(end_seen, drain_seen) is (
				end_seen if rule.requires_end else drain_seen)


ADDON = RUNTIME.parent


def _mode_comparisons(path):
	"""Lines comparing against a CompletionMode member (is, ==, in, not in ...)."""
	tree = ast.parse(path.read_text(encoding="utf-8"))

	def is_member(node):
		if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
			return any(is_member(element) for element in node.elts)
		return (
			isinstance(node, ast.Attribute)
			and isinstance(node.value, ast.Name)
			and node.value.id == "CompletionMode"
		)

	return sorted(
		node.lineno
		for node in ast.walk(tree)
		if isinstance(node, ast.Compare) and any(is_member(o) for o in (node.left, *node.comparators))
	)


# Components that already read contracts only through their completion rule.
CONVERTED = ("runtime/scheduler.py",)


@pytest.mark.parametrize("path", CONVERTED)
def test_converted_components_never_compare_completion_modes(path):
	assert _mode_comparisons(ADDON / path) == []


def test_scheduler_phases_are_an_enum():
	text = (RUNTIME / "scheduler.py").read_text(encoding="utf-8")
	assert "class TaskPhase(Enum):" in text
	for phase in ("starting", "awaiting_completion", "finishing"):
		assert f'"{phase}"' not in text, phase
