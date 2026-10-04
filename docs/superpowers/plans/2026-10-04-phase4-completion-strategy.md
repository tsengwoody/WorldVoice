# Phase 4: Completion Rule Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every component reads a completion contract through one rule table instead of comparing `CompletionMode`. The scheduler gets a `TaskPhase` Enum and a `_run_one` split into three stages. Behavior stays the same.

**Architecture:**
- **Task 1** pins today's behavior with characterization tests:
  - a scheduler outcome matrix (5 contracts × 9 event scenarios);
  - an adapter entry matrix;
  - the adapter's 7 precondition messages.
- **Task 2** adds `runtime/completion.py`: `SpeakEntry`, `Signal`, `CompletionRule` with its queries, and the 5-row `_RULES` table behind `rule_for(contract)`.
- **Tasks 3–5** move the consumers onto `rule_for`, each with a guard test that fails first:
  - Task 3: the scheduler, plus `TaskPhase` and `_acquire`/`_execute`/`_settle`;
  - Task 4: `LegacyEngineAdapter.speak`, with an entry table;
  - Task 5: the index ledger, event bridge, session and `voiceManager.py:136`. The guard then becomes add-on-wide.
- **Task 6** is the final verification.

**Tech Stack:** Python 3 threading, pytest, ruff, `ast` for the guards.

**Spec:** `docs/superpowers/specs/2026-10-04-phase4-completion-strategy-design.md`

## Global Constraints

- Work on branch `phase4-completion-strategy`, cut from `master` at `3c9df71`. The spec commit `4b1bff2` and the plan commit are on it.
- **Pure refactor.** All 1373 baseline tests must pass **unchanged**; only new test files and `tests/conftest.py` are added.
- **Do not change** anything under `addon/synthDrivers/WorldVoice/driver/`. `runtime/` must not import `compat/`.
- Lock order (delivery lock → state condition) and "engine calls, output and Future settlement run outside the state condition" stay exactly as they are.
- `SpeechFuture.then`, the compatibility shims and the contextual legacy feature stay; they are phase 8 work.
- Only these places may compare `CompletionMode` members:
  - `runtime/completion.py`;
  - `runtime/models.py` `__post_init__`;
  - `compat/completionPolicies.py`;
  - `voiceManager.py` `_resource_completion`.
- New names are snake_case. Every changed `addon/` file passes `ruff format --check`. Never commit `driver/Neural/`.
- Run from the repo root. Stage explicit paths only, never the user's unstaged deletion of `docs/superpowers/finish_task.md`. Never touch `git stash`.
- Baseline before Task 1: `python3 -m pytest tests -q` → `1373 passed`.
- Each code step applies a patch saved verbatim from this plan. Set `PATCHES=$(mktemp -d)` once, save the block to the named file, then run `git apply`.
- **Mutation steps come after the commit step.** They end with `git checkout -- addon`.
- Every commit message ends with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **`_run_one` split ordering.**
   - `_acquire`/`_execute`/`_settle` must keep every original step in order, including:
     - the stop wait;
     - validity checks after `activate` and after `speak`;
     - the future-cancel wake registration before `speak`;
     - stopping a non-token-aware playback when the token was cancelled during `speak`;
     - the final decision under delivery lock → state condition;
     - `_settle` running on every exit path: early returns, exceptions, and the pause-only task.
   - Compare against `git show master:addon/synthDrivers/WorldVoice/runtime/scheduler.py` line by line.
2. **END_INDEX `drain_event = None`.**
   - Before, a SEGMENT_DRAINED for an END_INDEX task set `drain_seen`; now it is ignored.
   - The spec claims nothing reads `drain_seen` for END_INDEX. Verify `is_complete`/`indexes_finished` for that row, the ledger's drain path, and the bridge's `segment_sink`.
3. **The conftest fixture.**
   - `tests/conftest.py` deletes every `runtime/completion.py` module before each test.
   - Check that it cannot hide a real identity bug. In production `runtime.completion` and `runtime.models` are each imported once under `synthDrivers.WorldVoice.runtime`.
4. **Adapter equivalence.**
   - `contextual` now comes from `rule.entry is LEGACY_SEGMENT`, not `contract.legacy_contextual`. The drain-factory check uses `rule.drain_event is not None`, while the event sink and the core call use `rule.entry`.
   - Check that the 7 error messages, their order, `finish_segment` on cancellation or exception, and the "no NVDA imports on the plain path" property are unchanged.
5. **Bridge and ledger rewrites.**
   - `_receive` keeps its contextual-legacy early return inside `not rule.correlated`.
   - The ledger's `finished` uses `is_complete(True, drain_seen)` on the terminal marker and `is_complete(end_seen, True)` on drain.
   - The ledger's bind check is now `not rule.correlated or index_range is None`.

---

### Task 1: Characterization tests for every completion contract

Spec "測試" item 1. The tests pin today's behavior, so they pass at once. Step 4's mutations of today's code prove they bite.

**Files:**
- Create: `tests/test_completion_characterization.py`

**Interfaces:**
- Consumes:
  - `runtime_harness`: `FakePlayback`, `RecordingOutput`, `load_index_support`, `load_scheduler`, `rt`;
  - `test_runtime_legacy_adapter`: `Core`, `compat`, `legacy_class`;
  - `test_worldvoice_index_command`: `nvda_commands`.
- Produces: `CONTRACTS`, `contract(rt, name)`, `SCENARIOS`, `OUTCOMES`, `ENTRIES`. Later tasks do not import them.

- [ ] **Step 1: Write the characterization tests**

Save as `$PATCHES/t1.patch`, then run `git apply $PATCHES/t1.patch`:

```diff
diff --git a/tests/test_completion_characterization.py b/tests/test_completion_characterization.py
new file mode 100644
index 0000000..c3c8e4a
--- /dev/null
+++ b/tests/test_completion_characterization.py
@@ -0,0 +1,259 @@
+"""Pin how each completion contract is interpreted by the scheduler and the adapter.
+
+Written before the completion rule table replaced per-mode branches; every
+row here records the behavior that refactor had to keep.
+"""
+
+from types import SimpleNamespace
+
+import pytest
+
+from runtime_harness import FakePlayback, RecordingOutput, load_index_support, load_scheduler, rt
+from test_runtime_legacy_adapter import Core, compat, legacy_class
+from test_worldvoice_index_command import nvda_commands
+
+CONTRACTS = ("plain", "contextual", "END_INDEX", "END_INDEX_AND_DRAIN", "DRAIN")
+
+
+def contract(rt, name):
+	models = rt.models
+	if name == "plain":
+		return models.CompletionContract()
+	if name == "contextual":
+		return models.CompletionContract(legacy_contextual=True)
+	return models.CompletionContract(getattr(models.CompletionMode, name), models.IndexRange(1, 1000))
+
+
+@pytest.fixture
+def scheduler(monkeypatch, rt):
+	return load_scheduler(monkeypatch, rt)
+
+
+@pytest.fixture
+def manager(scheduler):
+	manager = scheduler.TaskManager(RecordingOutput())
+	yield manager
+	manager.shutdown()
+
+
+# Event steps: (kind, segment) where segment is "own", "none" or "other".
+SCENARIOS = {
+	"done_anonymous": [("DONE", "none")],
+	"done_own": [("DONE", "own")],
+	"end_own": [("SEGMENT_END", "own")],
+	"drained_own": [("SEGMENT_DRAINED", "own")],
+	"failed_own": [("SEGMENT_FAILED", "own")],
+	"failed_anonymous": [("SEGMENT_FAILED", "none")],
+	"end_then_drained": [("SEGMENT_END", "own"), ("SEGMENT_DRAINED", "own")],
+	"drained_then_end": [("SEGMENT_DRAINED", "own"), ("SEGMENT_END", "own")],
+	"other_segment": [("DONE", "other"), ("SEGMENT_END", "other"), ("SEGMENT_DRAINED", "other")],
+}
+
+# What the scheduler did with each scenario before the rule table existed.
+OUTCOMES = {
+	"plain": {
+		"done_anonymous": "complete",
+		"done_own": "pending",
+		"end_own": "pending",
+		"drained_own": "pending",
+		"failed_own": "pending",
+		"failed_anonymous": "pending",
+		"end_then_drained": "pending",
+		"drained_then_end": "pending",
+		"other_segment": "pending",
+	},
+	"contextual": {
+		"done_anonymous": "pending",
+		"done_own": "complete",
+		"end_own": "pending",
+		"drained_own": "pending",
+		"failed_own": "failed",
+		"failed_anonymous": "pending",
+		"end_then_drained": "pending",
+		"drained_then_end": "pending",
+		"other_segment": "pending",
+	},
+	"END_INDEX": {
+		"done_anonymous": "pending",
+		"done_own": "pending",
+		"end_own": "complete",
+		"drained_own": "pending",
+		"failed_own": "failed",
+		"failed_anonymous": "pending",
+		"end_then_drained": "complete",
+		"drained_then_end": "complete",
+		"other_segment": "pending",
+	},
+	"END_INDEX_AND_DRAIN": {
+		"done_anonymous": "pending",
+		"done_own": "pending",
+		"end_own": "pending",
+		"drained_own": "pending",
+		"failed_own": "failed",
+		"failed_anonymous": "pending",
+		"end_then_drained": "complete",
+		"drained_then_end": "complete",
+		"other_segment": "pending",
+	},
+	"DRAIN": {
+		"done_anonymous": "pending",
+		"done_own": "pending",
+		"end_own": "pending",
+		"drained_own": "complete",
+		"failed_own": "failed",
+		"failed_anonymous": "pending",
+		"end_then_drained": "complete",
+		"drained_then_end": "complete",
+		"other_segment": "pending",
+	},
+}
+
+
+def _segment_id(task, where):
+	return {"own": task.segment_id, "none": None, "other": task.segment_id + 1}[where]
+
+
+@pytest.mark.parametrize("scenario", SCENARIOS)
+@pytest.mark.parametrize("name", CONTRACTS)
+def test_scheduler_outcome_per_contract(manager, rt, name, scenario):
+	port = FakePlayback(contract(rt, name))
+	request = manager.new_request()
+	future = manager.append_speech(request, port, "Fake:a", ("hello",))
+	assert manager.submit_request(request)
+	assert port.entered.wait(1)
+	task = request.tasks[0]
+	error = OSError("segment failed")
+	for kind, where in SCENARIOS[scenario]:
+		manager.on_event(rt.models.PlaybackEvent(
+			getattr(rt.models.EventKind, kind), port.source_id,
+			segment_id=_segment_id(task, where), error=error))
+	expected = OUTCOMES[name][scenario]
+	if expected == "complete":
+		assert future.result(1) is True
+	elif expected == "failed":
+		assert future.exception(1) is error
+	else:
+		# on_event signals the worker synchronously when the task is ready.
+		assert not manager._current_done_event.is_set()
+		assert not future.done()
+		manager.cancel()
+
+
+@pytest.mark.parametrize("name", ("END_INDEX_AND_DRAIN", "DRAIN"))
+def test_scheduler_index_after_end_per_contract(manager, rt, name):
+	# AND stops index delivery at END; DRAIN keeps delivering until drained.
+	output = manager._output
+	port = FakePlayback(contract(rt, name))
+	request = manager.new_request()
+	future = manager.append_speech(request, port, "Fake:a", ("hello",))
+	assert manager.submit_request(request)
+	assert port.entered.wait(1)
+	segment = request.tasks[0].segment_id
+	events = rt.models.EventKind
+	manager.on_event(rt.models.PlaybackEvent(events.SEGMENT_END, port.source_id, segment_id=segment))
+	manager.on_event(rt.models.PlaybackEvent(events.INDEX, port.source_id, 7, segment))
+	assert output.indexes == ([] if name == "END_INDEX_AND_DRAIN" else [7])
+	manager.on_event(rt.models.PlaybackEvent(events.SEGMENT_DRAINED, port.source_id, segment_id=segment))
+	assert future.result(1) is True
+
+
+class EntryCore(Core):
+	"""Records which native entry the adapter chose."""
+
+	def __init__(self):
+		super().__init__()
+		self.entries = []
+
+	def speak(self, commands, **kwargs):
+		self.entries.append(("speak", commands, tuple(sorted(kwargs))))
+
+	def speak_segment(self, commands, token, *, context, on_event):
+		self.entries.append(("speak_segment", commands, on_event))
+
+	def speak_legacy_segment(self, commands, token, *, context, on_event):
+		self.entries.append(("speak_legacy_segment", commands, on_event))
+
+
+@pytest.fixture
+def adapter_env(monkeypatch, compat, rt, nvda_commands):
+	support = load_index_support(monkeypatch, rt, "worldvoice_compat_test")
+	ledgers = []
+
+	def make(name, *, ledger=True, segment_events=True, legacy_events=True):
+		core = EntryCore()
+		cls = legacy_class(core)
+		index_ledger = support.ledger.IndexLedger() if ledger else None
+		adapter = compat.adapter.LegacyEngineAdapter(cls, lambda key: cls(), index_ledger=index_ledger)
+		adapter.open()
+		chosen = contract(rt, name)
+		adapter.configure_completion(chosen)
+		source_id = object()
+		if index_ledger is not None:
+			ledgers.append((adapter, index_ledger))
+			if chosen.mode is not rt.models.CompletionMode.LEGACY_DONE:
+				index_ledger.bind(core, source_id, chosen)
+		else:
+			ledgers.append((adapter, None))
+		sinks = SimpleNamespace(segment=lambda event: None, legacy=lambda event: None)
+		if segment_events and chosen.mode in (rt.models.CompletionMode.DRAIN,
+				rt.models.CompletionMode.END_INDEX_AND_DRAIN):
+			adapter.configure_segment_events(lambda context: sinks.segment)
+		if legacy_events and chosen.legacy_contextual:
+			adapter.configure_legacy_segment_events(lambda context: sinks.legacy)
+		return SimpleNamespace(adapter=adapter, core=core, sinks=sinks,
+			context=rt.models.PlaybackContext(source_id, 1))
+
+	yield SimpleNamespace(make=make, commands=nvda_commands,
+		token=SimpleNamespace(is_cancelled=lambda: False))
+	for adapter, ledger in ledgers:
+		adapter.close()
+		if ledger is not None:
+			ledger.close()
+
+
+# (native entry, markers encoded, event sink) per contract.
+ENTRIES = {
+	"plain": ("speak", False, None),
+	"contextual": ("speak_legacy_segment", False, "legacy"),
+	"END_INDEX": ("speak", True, None),
+	"END_INDEX_AND_DRAIN": ("speak_segment", True, "segment"),
+	"DRAIN": ("speak_segment", True, "segment"),
+}
+
+
+@pytest.mark.parametrize("name", CONTRACTS)
+def test_adapter_entry_per_contract(adapter_env, name):
+	env = adapter_env.make(name)
+	original = adapter_env.commands.IndexCommand(123)
+	context = None if name == "plain" else env.context
+	env.adapter.speak(("hello", original), adapter_env.token, context=context)
+	entry, encoded, sink = ENTRIES[name]
+	assert len(env.core.entries) == 1
+	called, commands, extra = env.core.entries[0]
+	assert called == entry
+	indexes = [c.index for c in commands if isinstance(c, adapter_env.commands.IndexCommand)]
+	assert (indexes != [123]) is encoded
+	if sink is not None:
+		assert extra is getattr(env.sinks, sink)
+	else:
+		assert extra == ()
+
+
+@pytest.mark.parametrize("name,missing,error,message", [
+	("contextual", "context", ValueError, "Contextual legacy completion requires a playback context"),
+	("END_INDEX", "context", ValueError, "Correlated completion requires a playback context"),
+	("DRAIN", "context", ValueError, "Correlated completion requires a playback context"),
+	("END_INDEX", "ledger", ValueError, "Marker completion requires an index ledger"),
+	("DRAIN", "segment_events", RuntimeError, "Drain completion requires a segment event factory"),
+	("END_INDEX_AND_DRAIN", "segment_events", RuntimeError, "Drain completion requires a segment event factory"),
+	("contextual", "legacy_events", RuntimeError,
+		"Contextual legacy completion requires a segment event factory"),
+])
+def test_adapter_precondition_errors_per_contract(adapter_env, name, missing, error, message):
+	env = adapter_env.make(name, ledger=missing != "ledger", segment_events=missing != "segment_events",
+		legacy_events=missing != "legacy_events")
+	context = None if missing == "context" else env.context
+	with pytest.raises(error) as caught:
+		env.adapter.speak(("hello",), adapter_env.token, context=context)
+	assert str(caught.value) == message
+	assert env.core.entries == []
```

- [ ] **Step 2: Run them against today's code**

Run: `python3 -m pytest tests/test_completion_characterization.py -q 2>&1 | tail -1; python3 -m pytest tests -q 2>&1 | tail -1`
Expected: `59 passed`, then `1432 passed`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_completion_characterization.py
git commit -m "test: pin how the scheduler and adapter interpret each completion contract

Characterization tests for the five contracts, written before the completion
rule table replaces the per-mode branches.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Prove they bite (mutations M1a–M1d of today's code, after the commit)**

```bash
mutate() { python3 - "$1" "$2" "$3" <<'PY'
import sys
p, old, new = sys.argv[1:]
s = open(p).read()
assert s.count(old) == 1, old
open(p, "w").write(s.replace(old, new))
PY
}
A=addon/synthDrivers/WorldVoice
check() { timeout 300 python3 -m pytest tests/test_completion_characterization.py -q -p no:cacheprovider 2>&1 | grep -E '^FAILED|^[0-9]+ (passed|failed)' | sed 's/ - .*//'; git checkout -- addon; }

echo M1a; mutate $A/runtime/scheduler.py '		if task.completion.mode is CompletionMode.DRAIN:
			return task.drain_seen
		return task.end_seen and (' '		if task.completion.mode is CompletionMode.DRAIN:
			return task.end_seen
		return task.end_seen and ('; check
echo M1b; mutate $A/runtime/scheduler.py '					elif not legacy and event.kind is EventKind.SEGMENT_FAILED:' '					elif False:'; check
echo M1c; mutate $A/compat/engineAdapter.py 'drain_mode = self._completion.mode in (CompletionMode.DRAIN, CompletionMode.END_INDEX_AND_DRAIN)' 'drain_mode = self._completion.mode is CompletionMode.DRAIN'; check
echo M1d; mutate $A/compat/engineAdapter.py '"Marker completion requires an index ledger"' '"Marker completion needs an index ledger"'; check
git status --short | grep addon
```

Expected:
- M1a: DRAIN readiness reads `end_seen`. `2 failed, 57 passed`:
  - `test_scheduler_outcome_per_contract[DRAIN-end_own]`
  - `test_scheduler_outcome_per_contract[DRAIN-drained_own]`
- M1b: correlated SEGMENT_FAILED is ignored. `3 failed, 56 passed`: `[END_INDEX-failed_own]`, `[END_INDEX_AND_DRAIN-failed_own]` and `[DRAIN-failed_own]`.
- M1c: the adapter treats AND as non-drain. `2 failed, 57 passed`: `test_adapter_entry_per_contract[END_INDEX_AND_DRAIN]` and the AND `segment_events` precondition.
- M1d: one precondition message changes. `1 failed, 58 passed`: the END_INDEX `ledger` precondition.

The final `git status` prints nothing.

---

### Task 2: The completion rule table

Spec §1.

**Files:**
- Create: `addon/synthDrivers/WorldVoice/runtime/completion.py`
- Test: `tests/test_completion_rules.py`

**Interfaces:**
- Consumes: `runtime.models.CompletionContract`, `CompletionMode`, `EventKind`.
- Produces (used by Tasks 3–5):
  - `SpeakEntry` (`SEGMENT`, `LEGACY_SEGMENT`, `PLAIN`);
  - `Signal` (`END`, `DRAIN`, `FAIL`);
  - frozen `CompletionRule(correlated, segment_scoped, end_event, drain_event, fails_on_segment_failed, requires_end, requires_drain, entry)` with:
    - `accepts_segment(segment_id, event_segment_id) -> bool`
    - `signal_for(kind) -> Signal | None`
    - `is_complete(end_seen, drain_seen) -> bool`
    - `indexes_finished(end_seen, drain_seen) -> bool`
  - `rule_for(contract) -> CompletionRule`.

- [ ] **Step 1: Write the table tests**

Save as `$PATCHES/t2-tests.patch`, then run `git apply $PATCHES/t2-tests.patch`:

```diff
diff --git a/tests/test_completion_rules.py b/tests/test_completion_rules.py
new file mode 100644
index 0000000..40b6f8a
--- /dev/null
+++ b/tests/test_completion_rules.py
@@ -0,0 +1,82 @@
+"""The completion rule table is the one place that interprets a completion contract."""
+
+import importlib.util
+import sys
+
+import pytest
+
+from runtime_harness import RUNTIME, rt
+
+
+@pytest.fixture
+def completion(monkeypatch, rt):
+	name = f"{rt.package.__name__}.completion"
+	spec = importlib.util.spec_from_file_location(name, RUNTIME / "completion.py")
+	module = importlib.util.module_from_spec(spec)
+	monkeypatch.setitem(sys.modules, name, module)
+	spec.loader.exec_module(module)
+	return module
+
+
+def _contract(rt, mode, contextual=False):
+	models = rt.models
+	mode = getattr(models.CompletionMode, mode)
+	if mode is models.CompletionMode.LEGACY_DONE:
+		return models.CompletionContract(legacy_contextual=contextual)
+	return models.CompletionContract(mode, models.IndexRange(1, 10))
+
+
+# correlated, segment_scoped, end_event, drain_event, fails_on_segment_failed,
+# requires_end, requires_drain, entry
+TABLE = {
+	("LEGACY_DONE", False): (False, False, "DONE", None, False, True, False, "PLAIN"),
+	("LEGACY_DONE", True): (False, True, "DONE", None, True, True, False, "LEGACY_SEGMENT"),
+	("END_INDEX", False): (True, True, "SEGMENT_END", None, True, True, False, "PLAIN"),
+	("END_INDEX_AND_DRAIN", False): (True, True, "SEGMENT_END", "SEGMENT_DRAINED", True, True, True, "SEGMENT"),
+	("DRAIN", False): (True, True, "SEGMENT_END", "SEGMENT_DRAINED", True, False, True, "SEGMENT"),
+}
+
+
+@pytest.mark.parametrize("key", TABLE)
+def test_rule_table_rows(completion, rt, key):
+	rule = completion.rule_for(_contract(rt, *key))
+	kinds = rt.models.EventKind
+	correlated, scoped, end, drain, fails, requires_end, requires_drain, entry = TABLE[key]
+	assert rule == completion.CompletionRule(
+		correlated=correlated,
+		segment_scoped=scoped,
+		end_event=getattr(kinds, end),
+		drain_event=getattr(kinds, drain) if drain else None,
+		fails_on_segment_failed=fails,
+		requires_end=requires_end,
+		requires_drain=requires_drain,
+		entry=getattr(completion.SpeakEntry, entry),
+	)
+
+
+def test_every_valid_contract_has_exactly_one_rule(completion, rt):
+	modes = rt.models.CompletionMode
+	valid = {(mode.name, False) for mode in modes} | {("LEGACY_DONE", True)}
+	assert set(TABLE) == valid
+	assert len({id(completion.rule_for(_contract(rt, *key))) for key in valid}) == len(valid)
+
+
+@pytest.mark.parametrize("key", TABLE)
+def test_rule_queries_read_only_the_rule_fields(completion, rt, key):
+	rule = completion.rule_for(_contract(rt, *key))
+	kinds, signal = rt.models.EventKind, completion.Signal
+	assert rule.accepts_segment(7, 7) is rule.segment_scoped
+	assert rule.accepts_segment(7, None) is not rule.segment_scoped
+	assert rule.accepts_segment(7, 8) is False
+	assert rule.signal_for(rule.end_event) is signal.END
+	if rule.drain_event is not None:
+		assert rule.signal_for(rule.drain_event) is signal.DRAIN
+	expected_failure = signal.FAIL if rule.fails_on_segment_failed else None
+	assert rule.signal_for(kinds.SEGMENT_FAILED) is expected_failure
+	assert rule.signal_for(kinds.INDEX) is None
+	for end_seen in (False, True):
+		for drain_seen in (False, True):
+			assert rule.is_complete(end_seen, drain_seen) is (
+				(end_seen or not rule.requires_end) and (drain_seen or not rule.requires_drain))
+			assert rule.indexes_finished(end_seen, drain_seen) is (
+				end_seen if rule.requires_end else drain_seen)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests -q 2>&1 | tail -1`
Expected: `1432 passed, 11 errors`. All 11 errors are in `tests/test_completion_rules.py`: `FileNotFoundError`, because `runtime/completion.py` does not exist yet.

- [ ] **Step 3: Add the module**

Save as `$PATCHES/t2-impl.patch`, then run `git apply $PATCHES/t2-impl.patch`:

```diff
diff --git a/addon/synthDrivers/WorldVoice/runtime/completion.py b/addon/synthDrivers/WorldVoice/runtime/completion.py
new file mode 100644
index 0000000..9f5cc4e
--- /dev/null
+++ b/addon/synthDrivers/WorldVoice/runtime/completion.py
@@ -0,0 +1,123 @@
+"""What each completion contract means, in one table.
+
+The scheduler, the engine adapter, the index ledger, the event bridge and the
+session read a contract only through its rule. Adding or removing a completion
+mode changes one row here instead of every component's branches.
+"""
+
+from dataclasses import dataclass
+from enum import Enum
+
+from .models import CompletionContract, CompletionMode, EventKind
+
+
+class SpeakEntry(Enum):
+	"""Which core entry the adapter calls; runtime never calls a core itself."""
+
+	SEGMENT = "segment"  # speak_segment(commands, token, context=, on_event=)
+	LEGACY_SEGMENT = "legacy_segment"  # speak_legacy_segment(commands, token, context=, on_event=)
+	PLAIN = "plain"  # speak(commands[, cancellationToken=])
+
+
+class Signal(Enum):
+	"""What an accepted event means for its segment."""
+
+	END = "end"
+	DRAIN = "drain"
+	FAIL = "fail"
+
+
+@dataclass(frozen=True)
+class CompletionRule:
+	# Uses the index ledger: markers are encoded and a playback context is required.
+	correlated: bool
+	# Events must carry the segment's ID; otherwise they must carry none.
+	segment_scoped: bool
+	end_event: EventKind
+	# Not None exactly when the core reports segment events (drain/failure).
+	drain_event: EventKind | None
+	fails_on_segment_failed: bool
+	requires_end: bool
+	requires_drain: bool
+	entry: SpeakEntry
+
+	def accepts_segment(self, segment_id: int | None, event_segment_id: int | None) -> bool:
+		if self.segment_scoped:
+			return event_segment_id == segment_id
+		return event_segment_id is None
+
+	def signal_for(self, kind: EventKind) -> Signal | None:
+		if kind is self.end_event:
+			return Signal.END
+		if kind is self.drain_event:
+			return Signal.DRAIN
+		if kind is EventKind.SEGMENT_FAILED and self.fails_on_segment_failed:
+			return Signal.FAIL
+		return None
+
+	def is_complete(self, end_seen: bool, drain_seen: bool) -> bool:
+		return (end_seen or not self.requires_end) and (drain_seen or not self.requires_drain)
+
+	def indexes_finished(self, end_seen: bool, drain_seen: bool) -> bool:
+		"""Whether later INDEX events for the segment are stale."""
+		return end_seen if self.requires_end else drain_seen
+
+
+_RULES = {
+	(CompletionMode.LEGACY_DONE, False): CompletionRule(
+		correlated=False,
+		segment_scoped=False,
+		end_event=EventKind.DONE,
+		drain_event=None,
+		fails_on_segment_failed=False,
+		requires_end=True,
+		requires_drain=False,
+		entry=SpeakEntry.PLAIN,
+	),
+	# Contextual legacy: software-correlated DONE without a native drain barrier.
+	(CompletionMode.LEGACY_DONE, True): CompletionRule(
+		correlated=False,
+		segment_scoped=True,
+		end_event=EventKind.DONE,
+		drain_event=None,
+		fails_on_segment_failed=True,
+		requires_end=True,
+		requires_drain=False,
+		entry=SpeakEntry.LEGACY_SEGMENT,
+	),
+	(CompletionMode.END_INDEX, False): CompletionRule(
+		correlated=True,
+		segment_scoped=True,
+		end_event=EventKind.SEGMENT_END,
+		drain_event=None,
+		fails_on_segment_failed=True,
+		requires_end=True,
+		requires_drain=False,
+		entry=SpeakEntry.PLAIN,
+	),
+	(CompletionMode.END_INDEX_AND_DRAIN, False): CompletionRule(
+		correlated=True,
+		segment_scoped=True,
+		end_event=EventKind.SEGMENT_END,
+		drain_event=EventKind.SEGMENT_DRAINED,
+		fails_on_segment_failed=True,
+		requires_end=True,
+		requires_drain=True,
+		entry=SpeakEntry.SEGMENT,
+	),
+	# A drain segment has no terminal marker; SEGMENT_END is recorded but never required.
+	(CompletionMode.DRAIN, False): CompletionRule(
+		correlated=True,
+		segment_scoped=True,
+		end_event=EventKind.SEGMENT_END,
+		drain_event=EventKind.SEGMENT_DRAINED,
+		fails_on_segment_failed=True,
+		requires_end=False,
+		requires_drain=True,
+		entry=SpeakEntry.SEGMENT,
+	),
+}
+
+
+def rule_for(contract: CompletionContract) -> CompletionRule:
+	return _RULES[(contract.mode, contract.legacy_contextual)]
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests -q 2>&1 | tail -1; ruff format --check addon/synthDrivers/WorldVoice/runtime/completion.py`
Expected: `1443 passed`, then `1 file already formatted`.

- [ ] **Step 5: Commit**

```bash
git add addon/synthDrivers/WorldVoice/runtime/completion.py tests/test_completion_rules.py
git commit -m "feat(runtime): add the completion rule table

One frozen CompletionRule per valid completion contract records what the
contract means: event correlation, which events end, drain or fail a
segment, what completion requires and which core entry speaks it.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Prove the table tests bite (mutations M2a–M2b, after the commit)**

```bash
mutate() { python3 - "$1" "$2" "$3" <<'PY'
import sys
p, old, new = sys.argv[1:]
s = open(p).read()
assert s.count(old) == 1, old
open(p, "w").write(s.replace(old, new))
PY
}
A=addon/synthDrivers/WorldVoice
check() { timeout 300 python3 -m pytest tests/test_completion_rules.py -q -p no:cacheprovider 2>&1 | grep -E '^FAILED|^[0-9]+ (passed|failed)' | sed 's/ - .*//'; git checkout -- addon; }

echo M2a; mutate $A/runtime/completion.py '		requires_end=False,
		requires_drain=True,
		entry=SpeakEntry.SEGMENT,' '		requires_end=True,
		requires_drain=True,
		entry=SpeakEntry.SEGMENT,'; check
echo M2b; mutate $A/runtime/completion.py '		return end_seen if self.requires_end else drain_seen' '		return end_seen'; check
git status --short | grep addon
```

Expected:
- M2a: DRAIN requires END. `1 failed, 10 passed`: `test_rule_table_rows[key4]`.
- M2b: `indexes_finished` always reads `end_seen`. `1 failed, 10 passed`: `test_rule_queries_read_only_the_rule_fields[key4]`.

The final `git status` prints nothing.

---

### Task 3: The scheduler reads the rule table; TaskPhase; `_run_one` in three stages

Spec §2 and §4.

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/runtime/scheduler.py`:
  - imports;
  - `TaskPhase`;
  - `_Task.rule`;
  - `_accepts_events_locked`, `_completion_ready_locked`, `_indexes_finished_locked`;
  - `_process_event_batch`;
  - `pause_current`;
  - `_run_one` → `_run_one` + `_acquire` + `_execute` + `_settle`.
- Create: `tests/conftest.py` (rebinds `runtime.completion` to each test's models)
- Test: `tests/test_completion_rules.py` (guard for the scheduler, and the phase Enum)

**Interfaces:**
- Consumes: Task 2's `rule_for`, `CompletionRule`, `Signal`.
- Produces:
  - `scheduler.TaskPhase` (`STARTING`, `AWAITING_COMPLETION`, `FINISHING`, values `auto()`);
  - `_Task.rule`;
  - in `tests/test_completion_rules.py`, `_mode_comparisons(path)` and `CONVERTED`. Task 4 extends `CONVERTED`; Task 5 replaces both with the add-on-wide guard.

- [ ] **Step 1: Write the scheduler guards**

Save as `$PATCHES/t3-tests.patch`, then run `git apply $PATCHES/t3-tests.patch`:

```diff
diff --git a/tests/test_completion_rules.py b/tests/test_completion_rules.py
index 40b6f8a..36ddd77 100644
--- a/tests/test_completion_rules.py
+++ b/tests/test_completion_rules.py
@@ -1,5 +1,6 @@
 """The completion rule table is the one place that interprets a completion contract."""
 
+import ast
 import importlib.util
 import sys
 
@@ -80,3 +81,42 @@ def test_rule_queries_read_only_the_rule_fields(completion, rt, key):
 				(end_seen or not rule.requires_end) and (drain_seen or not rule.requires_drain))
 			assert rule.indexes_finished(end_seen, drain_seen) is (
 				end_seen if rule.requires_end else drain_seen)
+
+
+ADDON = RUNTIME.parent
+
+
+def _mode_comparisons(path):
+	"""Lines comparing against a CompletionMode member (is, ==, in, not in ...)."""
+	tree = ast.parse(path.read_text(encoding="utf-8"))
+
+	def is_member(node):
+		if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
+			return any(is_member(element) for element in node.elts)
+		return (
+			isinstance(node, ast.Attribute)
+			and isinstance(node.value, ast.Name)
+			and node.value.id == "CompletionMode"
+		)
+
+	return sorted(
+		node.lineno
+		for node in ast.walk(tree)
+		if isinstance(node, ast.Compare) and any(is_member(o) for o in (node.left, *node.comparators))
+	)
+
+
+# Components that already read contracts only through their completion rule.
+CONVERTED = ("runtime/scheduler.py",)
+
+
+@pytest.mark.parametrize("path", CONVERTED)
+def test_converted_components_never_compare_completion_modes(path):
+	assert _mode_comparisons(ADDON / path) == []
+
+
+def test_scheduler_phases_are_an_enum():
+	text = (RUNTIME / "scheduler.py").read_text(encoding="utf-8")
+	assert "class TaskPhase(Enum):" in text
+	for phase in ("starting", "awaiting_completion", "finishing"):
+		assert f'"{phase}"' not in text, phase
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests -q 2>&1 | grep -E "^FAILED|^[0-9]+ (passed|failed)" | sed 's/ - .*//'`
Expected: `2 failed, 1443 passed`:
- `tests/test_completion_rules.py::test_converted_components_never_compare_completion_modes[runtime/scheduler.py]`
- `tests/test_completion_rules.py::test_scheduler_phases_are_an_enum`

- [ ] **Step 3: Move the scheduler onto the rule table**

Save as `$PATCHES/t3-impl.patch`, then run `git apply $PATCHES/t3-impl.patch`:

```diff
diff --git a/addon/synthDrivers/WorldVoice/runtime/scheduler.py b/addon/synthDrivers/WorldVoice/runtime/scheduler.py
index 862fae0..373e2e9 100644
--- a/addon/synthDrivers/WorldVoice/runtime/scheduler.py
+++ b/addon/synthDrivers/WorldVoice/runtime/scheduler.py
@@ -10,16 +10,16 @@ from collections import deque
 from collections.abc import Callable, Iterable
 from concurrent.futures import Future, InvalidStateError
 from dataclasses import dataclass, field
-from enum import Enum
+from enum import Enum, auto
 from itertools import count
 import logging
 import queue
 import threading
 from typing import Protocol
 
+from .completion import CompletionRule, Signal, rule_for
 from .models import (
 	CompletionContract,
-	CompletionMode,
 	EventKind,
 	PlaybackContext,
 	PlaybackEvent,
@@ -154,6 +154,12 @@ class RequestState(Enum):
 	FAILED = "failed"
 
 
+class TaskPhase(Enum):
+	STARTING = auto()
+	AWAITING_COMPLETION = auto()
+	FINISHING = auto()
+
+
 class InvalidRequestState(RuntimeError):
 	pass
 
@@ -185,6 +191,7 @@ class _Task:
 	segment_id: int | None = None
 	context: PlaybackContext | None = None
 	completion: CompletionContract | None = None
+	rule: CompletionRule | None = None
 	end_seen: bool = False
 	drain_seen: bool = False
 	error: Exception | None = None
@@ -308,22 +315,16 @@ class TaskManager:
 			task is not None
 			and task.playback is not None
 			and self._current_task is task
-			and self._current_phase == "awaiting_completion"
+			and self._current_phase is TaskPhase.AWAITING_COMPLETION
 			and self._valid_locked(task)
 			and task.error is None
 		)
 
 	def _completion_ready_locked(self, task):
-		if task.completion.mode is CompletionMode.DRAIN:
-			return task.drain_seen
-		return task.end_seen and (
-			task.completion.mode is not CompletionMode.END_INDEX_AND_DRAIN or task.drain_seen
-		)
+		return task.rule.is_complete(task.end_seen, task.drain_seen)
 
 	def _indexes_finished_locked(self, task):
-		if task.completion.mode is CompletionMode.DRAIN:
-			return task.drain_seen
-		return task.end_seen
+		return task.rule.indexes_finished(task.end_seen, task.drain_seen)
 
 	def on_event(self, event: PlaybackEvent) -> None:
 		self.on_events(lambda: (event,))
@@ -356,11 +357,8 @@ class TaskManager:
 				with self._state_cond:
 					if not self._accepts_events_locked(task) or event.source_id is not task.source_id:
 						continue
-					legacy = task.completion.mode is CompletionMode.LEGACY_DONE
-					if legacy and not task.completion.legacy_contextual:
-						if event.segment_id is not None:
-							continue
-					elif event.segment_id != task.segment_id:
+					rule = task.rule
+					if not rule.accepts_segment(task.segment_id, event.segment_id):
 						continue
 					if event.kind is EventKind.INDEX:
 						if (
@@ -371,20 +369,14 @@ class TaskManager:
 							continue
 						self._current_indexes.add(event.index)
 						index = event.index
-					elif legacy and event.kind is EventKind.DONE:
-						task.end_seen = True
-					elif (
-						legacy
-						and task.completion.legacy_contextual
-						and event.kind is EventKind.SEGMENT_FAILED
-					):
-						task.error = event.error or RuntimeError("Speech segment failed")
-					elif not legacy and event.kind is EventKind.SEGMENT_END:
-						task.end_seen = True
-					elif not legacy and event.kind is EventKind.SEGMENT_DRAINED:
-						task.drain_seen = True
-					elif not legacy and event.kind is EventKind.SEGMENT_FAILED:
-						task.error = event.error or RuntimeError("Speech segment failed")
+					else:
+						signal = rule.signal_for(event.kind)
+						if signal is Signal.END:
+							task.end_seen = True
+						elif signal is Signal.DRAIN:
+							task.drain_seen = True
+						elif signal is Signal.FAIL:
+							task.error = event.error or RuntimeError("Speech segment failed")
 				if index is not None:
 					self._deliver_index(task, index)
 		except Exception as error:
@@ -397,7 +389,7 @@ class TaskManager:
 				if (
 					task is not None
 					and self._current_task is task
-					and self._current_phase == "awaiting_completion"
+					and self._current_phase is TaskPhase.AWAITING_COMPLETION
 					and (task.error is not None or self._completion_ready_locked(task))
 				):
 					self._current_done_event.set()
@@ -499,7 +491,7 @@ class TaskManager:
 				current.playback
 				if current
 				and self._valid_locked(current)
-				and self._current_phase in ("starting", "awaiting_completion")
+				and self._current_phase in (TaskPhase.STARTING, TaskPhase.AWAITING_COMPLETION)
 				else None
 			)
 		if playback is not None:
@@ -530,58 +522,8 @@ class TaskManager:
 	def _run_one(self, task):
 		result, error, failed = None, None, False
 		try:
-			source = task.playback.source_id if task.playback is not None else None
-			with self._state_cond:
-				while self._stops_in_flight:
-					self._state_cond.wait()
-				valid = self._valid_locked(task)
-				if valid:
-					task.source_id = source
-					if task.playback is not None:
-						task.context = PlaybackContext(source, task.segment_id)
-					self._current_task = task
-					self._current_phase = "starting"
-					self._current_indexes = set()
-					self._current_done_event = threading.Event()
-			if not valid:
-				return
-			if task.playback is None:
-				task.request.token.wait(task.seconds)
-				return
-			task.completion = task.playback.completion
-			task.playback.activate(task.voice_key)
-			with self._state_cond:
-				if not self._valid_locked(task):
-					return
-				# Register before entry because speak can synchronously report completion.
-				self._current_phase = "awaiting_completion"
-				done = self._current_done_event
-			# Future.cancel is public too. Wake this task's event even when
-			# cancellation races the validity check or an active done wait.
-			# Registration is outside state: an already-settled Future invokes
-			# its callback immediately. The callback never finishes the task.
-			task.future.add_done_callback(lambda future: done.set() if future.cancelled() else None)
-			task.playback.speak(task.commands, task.request.token, context=task.context)
-			if task.request.token.is_cancelled():
-				# A non-token-aware synchronous speak may outlive the first stop.
-				self._stop_playback(task.playback)
-				return
-			with self._state_cond:
-				if not self._valid_locked(task):
-					return
-			done.wait()
-			# A wake is only a signal. Wait for the complete delivery batch and
-			# then validate after speak returned; errors/cancellation beat completion.
-			with self._delivery_lock:
-				with self._state_cond:
-					if not self._valid_locked(task):
-						return
-					if task.error is not None:
-						raise task.error
-					if not self._completion_ready_locked(task):
-						return
-					self._current_phase = "finishing"
-					result = True
+			if self._acquire(task):
+				result = self._execute(task)
 		except Exception as caught:
 			error = caught
 			with self._state_cond:
@@ -591,33 +533,100 @@ class TaskManager:
 					failed = True
 			self._logger.error("Speech scheduler task error", exc_info=True)
 		finally:
-			if failed and task.playback is not None:
-				self._stop_playback(task.playback)
-			if task.context is not None:
-				try:
-					task.playback.finish_segment(task.context)
-				except Exception:
-					self._logger.error("Failed to finish speech segment", exc_info=True)
+			self._settle(task, result, error, failed)
+
+	def _acquire(self, task):
+		"""Wait out in-flight stops, then make a still-valid task current."""
+		source = task.playback.source_id if task.playback is not None else None
+		with self._state_cond:
+			while self._stops_in_flight:
+				self._state_cond.wait()
+			if not self._valid_locked(task):
+				return False
+			task.source_id = source
+			if task.playback is not None:
+				task.context = PlaybackContext(source, task.segment_id)
+			self._current_task = task
+			self._current_phase = TaskPhase.STARTING
+			self._current_indexes = set()
+			self._current_done_event = threading.Event()
+		return True
+
+	def _execute(self, task):
+		"""Run the current task; True on completion, None when it stopped early.
+
+		Validity is checked again after each engine call, because activate and
+		speak run outside the state condition and cancellation can win at any
+		point. The final decision waits for the whole event batch to finish.
+		"""
+		if task.playback is None:
+			task.request.token.wait(task.seconds)
+			return None
+		task.completion = task.playback.completion
+		task.rule = rule_for(task.completion)
+		task.playback.activate(task.voice_key)
+		with self._state_cond:
+			if not self._valid_locked(task):
+				return None
+			# Register before entry because speak can synchronously report completion.
+			self._current_phase = TaskPhase.AWAITING_COMPLETION
+			done = self._current_done_event
+		# Future.cancel is public too. Wake this task's event even when
+		# cancellation races the validity check or an active done wait.
+		# Registration is outside state: an already-settled Future invokes
+		# its callback immediately. The callback never finishes the task.
+		task.future.add_done_callback(lambda future: done.set() if future.cancelled() else None)
+		task.playback.speak(task.commands, task.request.token, context=task.context)
+		if task.request.token.is_cancelled():
+			# A non-token-aware synchronous speak may outlive the first stop.
+			self._stop_playback(task.playback)
+			return None
+		with self._state_cond:
+			if not self._valid_locked(task):
+				return None
+		done.wait()
+		# A wake is only a signal. Wait for the complete delivery batch and
+		# then validate after speak returned; errors/cancellation beat completion.
+		with self._delivery_lock:
 			with self._state_cond:
-				valid = self._valid_locked(task)
-				if self._current_task is task:
-					self._current_task = None
-					self._current_phase = None
-					self._current_done_event = None
-					self._current_indexes = set()
-				notify_done = self._finish_task_locked(task)
-			# The state transition happens before user callbacks can re-enter.
-			if error is not None:
-				_settle_future(task.future, error=error)
-			elif valid:
-				_settle_future(task.future, result=result)
-			else:
-				task.future.cancel()
-			if notify_done:
-				try:
-					self._deliver_done(task.request)
-				except Exception:
-					self._logger.error("Speech done notification error", exc_info=True)
+				if not self._valid_locked(task):
+					return None
+				if task.error is not None:
+					raise task.error
+				if not self._completion_ready_locked(task):
+					return None
+				self._current_phase = TaskPhase.FINISHING
+				return True
+
+	def _settle(self, task, result, error, failed):
+		"""Release the task's resources, then settle its Future and the request."""
+		if failed and task.playback is not None:
+			self._stop_playback(task.playback)
+		if task.context is not None:
+			try:
+				task.playback.finish_segment(task.context)
+			except Exception:
+				self._logger.error("Failed to finish speech segment", exc_info=True)
+		with self._state_cond:
+			valid = self._valid_locked(task)
+			if self._current_task is task:
+				self._current_task = None
+				self._current_phase = None
+				self._current_done_event = None
+				self._current_indexes = set()
+			notify_done = self._finish_task_locked(task)
+		# The state transition happens before user callbacks can re-enter.
+		if error is not None:
+			_settle_future(task.future, error=error)
+		elif valid:
+			_settle_future(task.future, result=result)
+		else:
+			task.future.cancel()
+		if notify_done:
+			try:
+				self._deliver_done(task.request)
+			except Exception:
+				self._logger.error("Speech done notification error", exc_info=True)
 
 	def _finish_task_locked(self, task):
 		request = task.request
diff --git a/tests/conftest.py b/tests/conftest.py
new file mode 100644
index 0000000..1000800
--- /dev/null
+++ b/tests/conftest.py
@@ -0,0 +1,17 @@
+"""Shared fixtures for every test module."""
+
+import sys
+
+import pytest
+
+
+@pytest.fixture(autouse=True)
+def fresh_completion_rules(monkeypatch):
+	"""Bind runtime.completion to the models each test loads.
+
+	Harnesses reload runtime.models per test, often under an alias package. A
+	completion module imported by an earlier test would keep that test's enums.
+	"""
+	for name, module in tuple(sys.modules.items()):
+		if (getattr(module, "__file__", None) or "").replace("\\", "/").endswith("runtime/completion.py"):
+			monkeypatch.delitem(sys.modules, name)
```

`tests/conftest.py` is required, not optional. Without it, a `runtime.completion` module imported by an earlier test keeps that test's `CompletionMode`, and `rule_for` raises `KeyError` in about 150 tests.

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests -q 2>&1 | tail -1; ruff format --check addon/synthDrivers/WorldVoice/runtime/scheduler.py; grep -n '"starting"\|"awaiting_completion"\|"finishing"' addon/synthDrivers/WorldVoice/runtime/scheduler.py`
Expected: `1445 passed`, then `1 file already formatted`, then no grep output.

- [ ] **Step 5: Commit**

```bash
git add addon/synthDrivers/WorldVoice/runtime/scheduler.py tests/conftest.py tests/test_completion_rules.py
git commit -m "refactor(scheduler): read completion through its rule and split the task run

Event filtering, recording and readiness come from the completion rule
instead of CompletionMode branches. The phase is a TaskPhase Enum, and
_run_one delegates to _acquire, _execute and _settle with the same steps,
lock order and outside-the-lock calls as before.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Prove the scheduler uses the rules (mutations M3a–M3c, after the commit)**

```bash
mutate() { python3 - "$1" "$2" "$3" <<'PY'
import sys
p, old, new = sys.argv[1:]
s = open(p).read()
assert s.count(old) == 1, old
open(p, "w").write(s.replace(old, new))
PY
}
A=addon/synthDrivers/WorldVoice
check() { timeout 300 python3 -m pytest tests/test_completion_characterization.py tests/test_completion_rules.py tests/test_runtime_scheduler.py tests/test_runtime_segment_completion.py -q -p no:cacheprovider 2>&1 | grep -E '^[0-9]+ (passed|failed)' | sed 's/ - .*//'; git checkout -- addon; }

echo M3a; mutate $A/runtime/scheduler.py '						elif signal is Signal.DRAIN:' '						elif False:'; check
echo M3b; mutate $A/runtime/scheduler.py '		return task.rule.indexes_finished(task.end_seen, task.drain_seen)' '		return False'; check
echo M3c; printf '\n\ndef _legacy_ready(task):\n\treturn task.completion.mode is CompletionMode.DRAIN\n' >> $A/runtime/scheduler.py; check
git status --short | grep addon
```

Expected (count lines only):
- M3a: drain signals are ignored. `15 failed, 144 passed`.
- M3b: indexes never finish. `5 failed, 154 passed`.
- M3c: a `CompletionMode` comparison returns to the scheduler. `1 failed, 158 passed` (the scheduler guard).

The final `git status` prints nothing.

---

### Task 4: The adapter reads the rule table

Spec §3.

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/compat/engineAdapter.py`:
  - imports;
  - module-level `_speak_segment`, `_speak_legacy_segment`, `_speak_plain` and `_ENTRIES`;
  - `LegacyEngineAdapter.speak`.
- Test: `tests/test_completion_rules.py` (`CONVERTED` gains the adapter)

**Interfaces:**
- Consumes: Task 2's `rule_for`, `SpeakEntry`.
- Produces: nothing new for later tasks.

- [ ] **Step 1: Extend the guard to the adapter**

Save as `$PATCHES/t4-tests.patch`, then run `git apply $PATCHES/t4-tests.patch`:

```diff
diff --git a/tests/test_completion_rules.py b/tests/test_completion_rules.py
index 36ddd77..ac12da3 100644
--- a/tests/test_completion_rules.py
+++ b/tests/test_completion_rules.py
@@ -107,7 +107,7 @@ def _mode_comparisons(path):
 
 
 # Components that already read contracts only through their completion rule.
-CONVERTED = ("runtime/scheduler.py",)
+CONVERTED = ("runtime/scheduler.py", "compat/engineAdapter.py")
 
 
 @pytest.mark.parametrize("path", CONVERTED)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests -q 2>&1 | grep -E "^FAILED|^[0-9]+ (passed|failed)" | sed 's/ - .*//'`
Expected: `1 failed, 1445 passed`: `tests/test_completion_rules.py::test_converted_components_never_compare_completion_modes[compat/engineAdapter.py]`.

- [ ] **Step 3: Move the adapter onto the rule table**

Save as `$PATCHES/t4-impl.patch`, then run `git apply $PATCHES/t4-impl.patch`:

```diff
diff --git a/addon/synthDrivers/WorldVoice/compat/engineAdapter.py b/addon/synthDrivers/WorldVoice/compat/engineAdapter.py
index cf61d52..4c92510 100644
--- a/addon/synthDrivers/WorldVoice/compat/engineAdapter.py
+++ b/addon/synthDrivers/WorldVoice/compat/engineAdapter.py
@@ -6,9 +6,9 @@ from collections.abc import Callable, Mapping
 from typing import TYPE_CHECKING
 import logging
 
+from ..runtime.completion import SpeakEntry, rule_for
 from ..runtime.models import (
 	CompletionContract,
-	CompletionMode,
 	EngineCapabilities,
 	PlaybackContext,
 	SegmentEventSink,
@@ -22,6 +22,29 @@ if TYPE_CHECKING:
 	from ..indexLedger import IndexLedger
 
 
+def _speak_segment(adapter, commands, token, context, on_event):
+	adapter._core.speak_segment(commands, token, context=context, on_event=on_event)
+
+
+def _speak_legacy_segment(adapter, commands, token, context, on_event):
+	adapter._core.speak_legacy_segment(commands, token, context=context, on_event=on_event)
+
+
+def _speak_plain(adapter, commands, token, context, on_event):
+	if adapter.capabilities.supports_cancellation_token:
+		adapter._core.speak(commands, cancellationToken=token)
+	else:
+		adapter._core.speak(commands)
+
+
+# The completion rule names the core entry; each entry has its own signature.
+_ENTRIES = {
+	SpeakEntry.SEGMENT: _speak_segment,
+	SpeakEntry.LEGACY_SEGMENT: _speak_legacy_segment,
+	SpeakEntry.PLAIN: _speak_plain,
+}
+
+
 class LegacyEngineAdapter:
 	def __init__(
 		self,
@@ -174,48 +197,42 @@ class LegacyEngineAdapter:
 		context: PlaybackContext | None = None,
 	) -> None:
 		self._spoken = True
-		marker_mode = self._completion.mode is not CompletionMode.LEGACY_DONE
-		drain_mode = self._completion.mode in (CompletionMode.DRAIN, CompletionMode.END_INDEX_AND_DRAIN)
-		legacy_contextual = self._completion.legacy_contextual and context is not None
-		if self._completion.legacy_contextual and context is None:
+		rule = rule_for(self._completion)
+		contextual = rule.entry is SpeakEntry.LEGACY_SEGMENT
+		if contextual and context is None:
 			raise ValueError("Contextual legacy completion requires a playback context")
-		if marker_mode:
+		if rule.correlated:
 			if context is None:
 				raise ValueError("Correlated completion requires a playback context")
 			if self._index_ledger is None:
 				raise ValueError("Marker completion requires an index ledger")
 			self._source_id = context.source_id
-		if drain_mode and self._segment_events is None:
+		if rule.drain_event is not None and self._segment_events is None:
 			raise RuntimeError("Drain completion requires a segment event factory")
-		if legacy_contextual and self._legacy_events is None:
+		if contextual and self._legacy_events is None:
 			raise RuntimeError("Contextual legacy completion requires a segment event factory")
 		if token.is_cancelled():
-			if marker_mode:
+			if rule.correlated:
 				self.finish_segment(context)
 			return
 		try:
-			if marker_mode:
+			if rule.correlated:
 				# Legacy direct calls must not load NVDA command dependencies.
 				from .indexCodec import encode_segment
 
 				commands = encode_segment(commands, context, self._index_ledger)
-			on_event = self._segment_events(context) if drain_mode else None
-			if legacy_contextual:
+			on_event = None
+			if rule.entry is SpeakEntry.SEGMENT:
+				on_event = self._segment_events(context)
+			elif contextual:
 				on_event = self._legacy_events(context)
 			if token.is_cancelled():
-				if marker_mode:
+				if rule.correlated:
 					self.finish_segment(context)
 				return
-			if drain_mode:
-				self._core.speak_segment(commands, token, context=context, on_event=on_event)
-			elif legacy_contextual:
-				self._core.speak_legacy_segment(commands, token, context=context, on_event=on_event)
-			elif self.capabilities.supports_cancellation_token:
-				self._core.speak(commands, cancellationToken=token)
-			else:
-				self._core.speak(commands)
+			_ENTRIES[rule.entry](self, commands, token, context, on_event)
 		except Exception:
-			if marker_mode:
+			if rule.correlated:
 				self.finish_segment(context)
 			raise
 
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests -q 2>&1 | tail -1; ruff format --check addon/synthDrivers/WorldVoice/compat/engineAdapter.py`
Expected: `1446 passed`, then `1 file already formatted`.

- [ ] **Step 5: Commit**

```bash
git add addon/synthDrivers/WorldVoice/compat/engineAdapter.py tests/test_completion_rules.py
git commit -m "refactor(compat): choose the adapter's checks and core entry from the completion rule

The four completion booleans in LegacyEngineAdapter.speak become rule
fields, and the core call is looked up by the rule's SpeakEntry. The
checks, their order and their messages are unchanged.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Prove the adapter uses the rules (mutations M4a–M4c, after the commit)**

```bash
mutate() { python3 - "$1" "$2" "$3" <<'PY'
import sys
p, old, new = sys.argv[1:]
s = open(p).read()
assert s.count(old) == 1, old
open(p, "w").write(s.replace(old, new))
PY
}
A=addon/synthDrivers/WorldVoice
check() { timeout 300 python3 -m pytest tests/test_completion_characterization.py tests/test_completion_rules.py tests/test_runtime_legacy_adapter.py -q -p no:cacheprovider 2>&1 | grep -E '^[0-9]+ (passed|failed)' | sed 's/ - .*//'; git checkout -- addon; }

echo M4a; mutate $A/compat/engineAdapter.py '	SpeakEntry.SEGMENT: _speak_segment,' '	SpeakEntry.SEGMENT: _speak_plain,'; check
echo M4b; mutate $A/compat/engineAdapter.py '		if rule.drain_event is not None and self._segment_events is None:' '		if False:'; check
echo M4c; printf '\n\ndef _legacy_marker(contract):\n\treturn contract.mode is not CompletionMode.LEGACY_DONE\n' >> $A/compat/engineAdapter.py; check
git status --short | grep addon
```

Expected (count lines only):
- M4a: SEGMENT dispatches to the plain entry. `8 failed, 106 passed`.
- M4b: the drain-factory check is dropped. `3 failed, 111 passed`.
- M4c: a `CompletionMode` comparison returns to the adapter. `1 failed, 113 passed` (the adapter guard).

The final `git status` prints nothing.

---

### Task 5: Ledger, bridge, session and voice manager read the rule table

Spec §1's behavior mapping and §5.

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/indexLedger.py`:
  - `_Source.rule`;
  - `bind` (correlated check);
  - `prepare` (`marker = rule.requires_end`);
  - `receive_index` and `receive_segment_event` (`is_complete`, `requires_drain`).
- Modify: `addon/synthDrivers/WorldVoice/nvdaEventBridge.py`:
  - `bind`, `unbind`, `close` and `_receive` use `correlated`;
  - `segment_sink` uses `drain_event`.
- Modify: `addon/synthDrivers/WorldVoice/runtime/session.py` (`speak` uses `correlated`)
- Modify: `addon/synthDrivers/WorldVoice/voiceManager.py:136` (`drain_event`)
- Test: `tests/test_completion_rules.py` (the add-on-wide guard replaces `CONVERTED`)

**Interfaces:**
- Consumes: Task 2's `rule_for`, `CompletionRule`.
- Produces: `_mode_comparisons(path) -> list[(line, enclosing function)]` and `ALLOWED`.

- [ ] **Step 1: Make the guard add-on-wide**

Save as `$PATCHES/t5-tests.patch`, then run `git apply $PATCHES/t5-tests.patch`:

```diff
diff --git a/tests/test_completion_rules.py b/tests/test_completion_rules.py
index ac12da3..e8d3cef 100644
--- a/tests/test_completion_rules.py
+++ b/tests/test_completion_rules.py
@@ -87,8 +87,9 @@ ADDON = RUNTIME.parent
 
 
 def _mode_comparisons(path):
-	"""Lines comparing against a CompletionMode member (is, ==, in, not in ...)."""
+	"""(line, enclosing function) of each comparison against a CompletionMode member."""
 	tree = ast.parse(path.read_text(encoding="utf-8"))
+	functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
 
 	def is_member(node):
 		if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
@@ -99,20 +100,47 @@ def _mode_comparisons(path):
 			and node.value.id == "CompletionMode"
 		)
 
+	def enclosing(line):
+		owners = [f for f in functions if f.lineno <= line <= f.end_lineno]
+		return max(owners, key=lambda f: f.lineno).name if owners else None
+
 	return sorted(
-		node.lineno
+		(node.lineno, enclosing(node.lineno))
 		for node in ast.walk(tree)
 		if isinstance(node, ast.Compare) and any(is_member(o) for o in (node.left, *node.comparators))
 	)
 
 
-# Components that already read contracts only through their completion rule.
-CONVERTED = ("runtime/scheduler.py", "compat/engineAdapter.py")
+# Only code that defines or builds a contract may compare CompletionMode
+# members; everything else reads the contract through its completion rule.
+ALLOWED = {
+	"runtime/completion.py": None,
+	"runtime/models.py": {"__post_init__"},
+	"compat/completionPolicies.py": None,
+	"voiceManager.py": {"_resource_completion"},
+}
 
 
-@pytest.mark.parametrize("path", CONVERTED)
-def test_converted_components_never_compare_completion_modes(path):
-	assert _mode_comparisons(ADDON / path) == []
+def test_completion_mode_is_compared_only_where_contracts_are_built():
+	found = []
+	for path in sorted(ADDON.rglob("*.py")):
+		relative = path.relative_to(ADDON).as_posix()
+		allowed = ALLOWED.get(relative, set())
+		for line, function in _mode_comparisons(path):
+			if allowed is not None and function not in allowed:
+				found.append(f"{relative}:{line} in {function}")
+	assert found == []
+
+
+def test_mode_comparison_scan_sees_members_and_tuples(tmp_path):
+	sample = tmp_path / "sample.py"
+	sample.write_text(
+		"def a(c):\n\treturn c.mode is CompletionMode.DRAIN\n"
+		"def b(c):\n\treturn c.mode in (CompletionMode.DRAIN, CompletionMode.END_INDEX)\n"
+		"def c(c):\n\treturn c.mode != other.mode\n",
+		encoding="utf-8",
+	)
+	assert _mode_comparisons(sample) == [(2, "a"), (4, "b")]
 
 
 def test_scheduler_phases_are_an_enum():
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests -q 2>&1 | grep -E "^FAILED|^[0-9]+ (passed|failed)" | sed 's/ - .*//'`
Expected: `1 failed, 1445 passed`: `tests/test_completion_rules.py::test_completion_mode_is_compared_only_where_contracts_are_built`.

The assertion lists these 12 comparisons:
- `indexLedger.py`: `bind`, `prepare`, `receive_index`, and `receive_segment_event` twice;
- `nvdaEventBridge.py`: `bind`, `unbind`, `segment_sink`, `close`, `_receive`;
- `runtime/session.py`: `speak`;
- `voiceManager.py`: `_initialize`.

`voiceManager.py:_resource_completion` is not listed, because it is allowed.

- [ ] **Step 3: Move the remaining components onto the rule table**

Save as `$PATCHES/t5-impl.patch`, then run `git apply $PATCHES/t5-impl.patch`:

```diff
diff --git a/addon/synthDrivers/WorldVoice/indexLedger.py b/addon/synthDrivers/WorldVoice/indexLedger.py
index 77c1db1..db9680f 100644
--- a/addon/synthDrivers/WorldVoice/indexLedger.py
+++ b/addon/synthDrivers/WorldVoice/indexLedger.py
@@ -8,6 +8,7 @@ publishing it through a fresh ledger.
 from dataclasses import dataclass, field
 from threading import Lock
 
+from .runtime.completion import CompletionRule, rule_for
 from .runtime.models import (
 	CompletionContract,
 	CompletionMode,
@@ -48,6 +49,7 @@ class _Source:
 	# Strong reference prevents id reuse even while this source is unbound.
 	source: object
 	mode: CompletionMode
+	rule: CompletionRule
 	minimum: int
 	maximum: int
 	next_index: int
@@ -73,15 +75,8 @@ class IndexLedger:
 	def bind(self, source: object, source_id: object, contract: CompletionContract) -> object:
 		"""Return an opaque token identifying this exact binding generation."""
 		mode, index_range = contract.mode, contract.index_range
-		if (
-			mode
-			not in (
-				CompletionMode.END_INDEX,
-				CompletionMode.END_INDEX_AND_DRAIN,
-				CompletionMode.DRAIN,
-			)
-			or index_range is None
-		):
+		rule = rule_for(contract)
+		if not rule.correlated or index_range is None:
 			raise InvalidIndexContext("Index allocation requires a correlated completion contract")
 		minimum, maximum = index_range.minimum, index_range.maximum
 		with self._lock:
@@ -99,7 +94,7 @@ class IndexLedger:
 						raise InvalidIndexContext("Source is already bound to another source ID")
 					return existing.token
 			else:
-				state = _Source(source, mode, minimum, maximum, minimum)
+				state = _Source(source, mode, rule, minimum, maximum, minimum)
 				self._sources[id(source)] = state
 			binding = _Binding(source_id, state)
 			state.binding = binding
@@ -118,7 +113,7 @@ class IndexLedger:
 			state = binding.state
 			if segment_id in state.segments:
 				raise InvalidIndexContext("Segment is already prepared and has not been retired")
-			marker = state.mode is not CompletionMode.DRAIN
+			marker = state.rule.requires_end
 			count = len(originals) + int(marker)
 			if state.next_index + count - 1 > state.maximum:
 				raise IndexSpaceExhausted("Source wire index range is exhausted")
@@ -162,7 +157,7 @@ class IndexLedger:
 			events = self._pending_indexes(source_id, segment, stop)
 			if terminal:
 				segment.end_seen = True
-				segment.finished = state.mode is CompletionMode.END_INDEX or segment.drain_seen
+				segment.finished = state.rule.is_complete(True, segment.drain_seen)
 				events.append(PlaybackEvent(EventKind.SEGMENT_END, source_id, segment_id=segment.segment_id))
 				self._remove_indexes(state, segment)
 			return tuple(events)
@@ -190,11 +185,11 @@ class IndexLedger:
 				segment.finished = True
 				self._remove_indexes(state, segment)
 				return (event,)
-			if state.mode is CompletionMode.END_INDEX or segment.drain_seen:
+			if not state.rule.requires_drain or segment.drain_seen:
 				return ()
 			events = self._pending_indexes(event.source_id, segment, len(segment.originals))
 			segment.drain_seen = True
-			segment.finished = state.mode is CompletionMode.DRAIN or segment.end_seen
+			segment.finished = state.rule.is_complete(segment.end_seen, True)
 			# AND still needs the real terminal callback when drain arrives first.
 			self._remove_indexes(state, segment, keep_terminal=not segment.finished)
 			return (*events, event)
diff --git a/addon/synthDrivers/WorldVoice/nvdaEventBridge.py b/addon/synthDrivers/WorldVoice/nvdaEventBridge.py
index 2ad237a..c374610 100644
--- a/addon/synthDrivers/WorldVoice/nvdaEventBridge.py
+++ b/addon/synthDrivers/WorldVoice/nvdaEventBridge.py
@@ -5,9 +5,9 @@ from dataclasses import dataclass
 from threading import RLock
 
 from .indexLedger import IndexLedger
+from .runtime.completion import rule_for
 from .runtime.models import (
 	CompletionContract,
-	CompletionMode,
 	EventKind,
 	PlaybackContext,
 	PlaybackEvent,
@@ -108,7 +108,7 @@ class NvdaEventBridge:
 			if completion.legacy_contextual and self._batch_handler is None:
 				raise ValueError("Contextual legacy completion requires a batch handler")
 			ledger_token = None
-			if completion.mode is not CompletionMode.LEGACY_DONE:
+			if rule_for(completion).correlated:
 				if self._index_ledger is None or self._batch_handler is None:
 					raise ValueError("Marker completion requires an index ledger and batch handler")
 				if any(binding.source_id is source_id for binding in self._sources.values()):
@@ -130,7 +130,7 @@ class NvdaEventBridge:
 			bindings = [binding for binding in self._sources.values() if binding.source_id is source_id]
 			for binding in bindings:
 				del self._sources[id(binding.source)]
-			if any(binding.completion.mode is not CompletionMode.LEGACY_DONE for binding in bindings):
+			if any(rule_for(binding.completion).correlated for binding in bindings):
 				self._index_ledger.unbind(source_id)
 		# Release source references after unlocking.
 
@@ -148,11 +148,7 @@ class NvdaEventBridge:
 				or binding is None
 				or binding.source is not source
 				or binding.source_id is not context.source_id
-				or binding.completion.mode
-				not in (
-					CompletionMode.DRAIN,
-					CompletionMode.END_INDEX_AND_DRAIN,
-				)
+				or rule_for(binding.completion).drain_event is None
 			):
 				raise ValueError("Segment events require a matching drain-capable source binding")
 			batch_handler = self._batch_handler
@@ -231,7 +227,7 @@ class NvdaEventBridge:
 				if first_error is None:
 					first_error = error
 		for binding in sources.values():
-			if binding.completion.mode is CompletionMode.LEGACY_DONE:
+			if not rule_for(binding.completion).correlated:
 				continue
 			try:
 				self._index_ledger.unbind(binding.source_id)
@@ -257,7 +253,7 @@ class NvdaEventBridge:
 				return
 			handler = self._handler
 			batch_handler = self._batch_handler
-		if binding.completion.mode is CompletionMode.LEGACY_DONE:
+		if not rule_for(binding.completion).correlated:
 			if binding.completion.legacy_contextual:
 				return  # Only the context-bound sink may complete this source.
 			if handler is not None:
diff --git a/addon/synthDrivers/WorldVoice/runtime/session.py b/addon/synthDrivers/WorldVoice/runtime/session.py
index ad0bfbb..59e3bac 100644
--- a/addon/synthDrivers/WorldVoice/runtime/session.py
+++ b/addon/synthDrivers/WorldVoice/runtime/session.py
@@ -4,9 +4,9 @@ from collections.abc import Callable, Mapping
 from threading import RLock
 from typing import Protocol
 
+from .completion import rule_for
 from .models import (
 	CompletionContract,
-	CompletionMode,
 	EngineCapabilities,
 	PlaybackContext,
 	SourceId,
@@ -176,7 +176,7 @@ class EngineSession:
 			# notify would leave them blocked.
 			raise TypeError("speech tokens must implement CancellationView.add_callback")
 		if context is None:
-			if self.completion.mode is not CompletionMode.LEGACY_DONE:
+			if rule_for(self.completion).correlated:
 				raise ValueError("Correlated completion requires a playback context")
 			self._adapter.speak(commands, token)
 		else:
diff --git a/addon/synthDrivers/WorldVoice/voiceManager.py b/addon/synthDrivers/WorldVoice/voiceManager.py
index 57e7015..e3f9acb 100644
--- a/addon/synthDrivers/WorldVoice/voiceManager.py
+++ b/addon/synthDrivers/WorldVoice/voiceManager.py
@@ -12,6 +12,7 @@ from synthDriverHandler import VoiceInfo
 
 from .compat.engineAdapter import LegacyEngineAdapter
 from .compat.voiceFacade import LegacyVoiceBinding
+from .runtime.completion import rule_for
 from .runtime.models import VoiceSpec, EngineCapabilities, CompletionContract, CompletionMode
 from .indexLedger import IndexLedger
 from .runtime.session import EngineSession, PlaybackPort
@@ -133,7 +134,7 @@ class VoiceManager(object):
 				adapter.configure_completion(completion)
 				# Claim ownership before binding, since bind may register then raise.
 				self._bridge.bind(adapter.notification_source, session.source_id, completion=completion)
-				if completion.mode in (CompletionMode.DRAIN, CompletionMode.END_INDEX_AND_DRAIN):
+				if rule_for(completion).drain_event is not None:
 					adapter.configure_segment_events(
 						lambda context, source=adapter.notification_source: self._bridge.segment_sink(
 							source,
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests -q 2>&1 | tail -1; ruff format --check addon | tail -1`
Expected: `1446 passed`, then `54 files already formatted`.

- [ ] **Step 5: Commit**

```bash
git add addon/synthDrivers/WorldVoice/indexLedger.py addon/synthDrivers/WorldVoice/nvdaEventBridge.py \
	addon/synthDrivers/WorldVoice/runtime/session.py addon/synthDrivers/WorldVoice/voiceManager.py tests/test_completion_rules.py
git commit -m "refactor: read completion rules in the ledger, bridge, session and voice manager

The ledger's segment completion now shares the scheduler's is_complete
instead of a second copy, and the remaining CompletionMode branches become
rule queries. A guard keeps CompletionMode comparisons to the places that
define or build contracts.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Prove the components use the rules (mutations M5a–M5e, after the commit)**

```bash
mutate() { python3 - "$1" "$2" "$3" <<'PY'
import sys
p, old, new = sys.argv[1:]
s = open(p).read()
assert s.count(old) == 1, old
open(p, "w").write(s.replace(old, new))
PY
}
A=addon/synthDrivers/WorldVoice
check() { timeout 300 python3 -m pytest tests/test_index_ledger.py tests/test_nvda_event_bridge.py tests/test_runtime_session.py tests/test_completion_rules.py tests/test_runtime_legacy_adapter.py -q -p no:cacheprovider 2>&1 | grep -E '^[0-9]+ (passed|failed)' | sed 's/ - .*//'; git checkout -- addon; }

echo M5a; mutate $A/indexLedger.py '			marker = state.rule.requires_end' '			marker = True'; check
echo M5b; mutate $A/indexLedger.py '			if not state.rule.requires_drain or segment.drain_seen:' '			if segment.drain_seen:'; check
echo M5c; mutate $A/nvdaEventBridge.py '				or rule_for(binding.completion).drain_event is None' '				or False'; check
echo M5d; mutate $A/runtime/session.py '			if rule_for(self.completion).correlated:' '			if False:'; check
echo M5e; printf '\n\ndef _legacy_marker(contract):\n\treturn contract.mode is not CompletionMode.LEGACY_DONE\n' >> $A/nvdaEventBridge.py; check
git status --short | grep addon
```

Expected (count lines only):
- M5a: every correlated segment gets a terminal marker. `8 failed, 177 passed`.
- M5b: END_INDEX no longer ignores drain. `1 failed, 184 passed`.
- M5c: `segment_sink` accepts any correlated binding. `1 failed, 184 passed`.
- M5d: the session no longer requires a context for correlated completion. `3 failed, 182 passed`.
- M5e: a `CompletionMode` comparison returns to the bridge. `1 failed, 184 passed` (the add-on-wide guard).

The final `git status` prints nothing.

---

### Task 6: Final verification

**Files:** none modified.

- [ ] **Step 1: Stability**

Run: `for i in 1 2 3 4 5; do python3 -m pytest tests/test_completion_characterization.py tests/test_completion_rules.py tests/test_runtime_scheduler.py tests/test_runtime_segment_completion.py tests/test_runtime_legacy_adapter.py tests/test_index_ledger.py tests/test_nvda_event_bridge.py tests/test_runtime_drain_integration.py tests/test_runtime_adapter_contract.py tests/test_runtime_session.py -q 2>&1 | tail -1; done | sed 's/ in .*//' | sort | uniq -c`
Expected: one line, `5 406 passed`.

Run: `for i in $(seq 1 20); do python3 -m pytest tests/test_vocalizer_segment_drain.py tests/test_worldvoice_cancel_wrappers.py -q 2>&1 | tail -1; done | sed 's/ in .*//' | sort | uniq -c`
Expected: one line, `20 233 passed`.

- [ ] **Step 2: Scope and protected paths**

Run:
```bash
git diff master --stat -- addon/synthDrivers/WorldVoice/driver
git diff master --stat -- tests | grep -v "test_completion_characterization\|test_completion_rules\|conftest\|files changed"
git ls-files addon/synthDrivers/WorldVoice/driver/Neural
ruff format --check addon | tail -1
```
Expected: no output from the first three commands, then `54 files already formatted`. The baseline tests are unchanged.

- [ ] **Step 3: Full suite and history**

Run: `python3 -m pytest tests -q 2>&1 | tail -1; git log --oneline master..HEAD`
Expected: `1446 passed`. The log lists, oldest at the bottom:
1. `docs: add phase 4 completion strategy design spec`
2. `docs: add phase 4 implementation plan and amend its spec`
3. `test: pin how the scheduler and adapter interpret each completion contract`
4. `feat(runtime): add the completion rule table`
5. `refactor(scheduler): read completion through its rule and split the task run`
6. `refactor(compat): choose the adapter's checks and core entry from the completion rule`
7. `refactor: read completion rules in the ledger, bridge, session and voice manager`
