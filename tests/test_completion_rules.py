"""The completion rule table is the one place that interprets a completion contract."""

import ast

import pytest
from addon_loader import load_source
from runtime_harness import RUNTIME


@pytest.fixture
def completion(monkeypatch, rt):
	return load_source(monkeypatch, f"{rt.package.__name__}.completion", RUNTIME / "completion.py")


def _contract(rt, mode):
	models = rt.models
	mode = getattr(models.CompletionMode, mode)
	if mode is models.CompletionMode.LEGACY_DONE:
		return models.CompletionContract()
	return models.CompletionContract(mode, models.IndexRange(1, 10))


# correlated, segment_scoped, end_event, drain_event, fails_on_segment_failed,
# requires_end, requires_drain, entry
TABLE = {
	"LEGACY_DONE": (False, False, "DONE", None, False, True, False, "PLAIN"),
	"END_INDEX": (True, True, "SEGMENT_END", None, True, True, False, "PLAIN"),
	"END_INDEX_AND_DRAIN": (True, True, "SEGMENT_END", "SEGMENT_DRAINED", True, True, True, "SEGMENT"),
	"DRAIN": (True, True, "SEGMENT_END", "SEGMENT_DRAINED", True, False, True, "SEGMENT"),
}


@pytest.mark.parametrize("key", TABLE)
def test_rule_table_rows(completion, rt, key):
	rule = completion.rule_for(_contract(rt, key))
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


def test_every_completion_mode_has_exactly_one_rule(completion, rt):
	modes = {mode.name for mode in rt.models.CompletionMode}
	assert set(TABLE) == modes
	assert len({id(completion.rule_for(_contract(rt, mode))) for mode in modes}) == len(modes)


@pytest.mark.parametrize("key", TABLE)
def test_rule_queries_read_only_the_rule_fields(completion, rt, key):
	rule = completion.rule_for(_contract(rt, key))
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
				(end_seen or not rule.requires_end) and (drain_seen or not rule.requires_drain)
			)
			assert rule.indexes_finished(end_seen, drain_seen) is (
				end_seen if rule.requires_end else drain_seen
			)


ADDON = RUNTIME.parent


def _mode_comparisons(path):
	"""(line, enclosing function) of each comparison against a CompletionMode member."""
	tree = ast.parse(path.read_text(encoding="utf-8"))
	functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]

	def is_member(node):
		if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
			return any(is_member(element) for element in node.elts)
		return (
			isinstance(node, ast.Attribute)
			and isinstance(node.value, ast.Name)
			and node.value.id == "CompletionMode"
		)

	def enclosing(line):
		owners = [f for f in functions if f.lineno <= line <= f.end_lineno]
		return max(owners, key=lambda f: f.lineno).name if owners else None

	return sorted(
		(node.lineno, enclosing(node.lineno))
		for node in ast.walk(tree)
		if isinstance(node, ast.Compare) and any(is_member(o) for o in (node.left, *node.comparators))
	)


# Only code that defines or builds a contract may compare CompletionMode
# members; everything else reads the contract through its completion rule.
ALLOWED = {
	"runtime/completion.py": None,
	"runtime/models.py": {"__post_init__"},
	"bridge/completionPolicies.py": None,
}


def test_completion_mode_is_compared_only_where_contracts_are_built():
	found = []
	for path in sorted(ADDON.rglob("*.py")):
		relative = path.relative_to(ADDON).as_posix()
		allowed = ALLOWED.get(relative, set())
		for line, function in _mode_comparisons(path):
			if allowed is not None and function not in allowed:
				found.append(f"{relative}:{line} in {function}")
	assert found == []
