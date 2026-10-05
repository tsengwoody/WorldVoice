# Phase 9e VE/Cerence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- Give VE and Cerence the shared `StopGate`, with an exception-safe `cancel`.
- Add InnerPort lists, a `voiceInfoToMetadata` hook in place of `voices()`, and drop the dead `_DONE`.
- Add a VE↔Cerence drift test and the third cross-engine contract scenario.

**Architecture:** Identical edits in the two separate wrapper files (no shared code). Guards and drift tests live under `tests/`.

**Tech Stack:** Python 3.11; pytest; ruff format (tabs).

**Spec:** `docs/superpowers/specs/2026-10-05-phase9e-vocalizer-design.md`

## Global Constraints

- Never edit `driver/VE/driver/`, `driver/Cerence/driver/` or `driver/sonic`.
- VE and Cerence stay separate files with no shared code; every wrapper edit is applied to both.
- `addon/` ruff-format clean; new tests use tabs.
- `git add` explicit paths; never stage the `docs/superpowers/finish_task.md` deletion or `refactor.md`.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Full suite: `python3 -m pytest tests -q` (baseline 1513).

## Review Focus

1. **`cancel()` returning early because `_playerClosing` is set**: no `leave()` and no `_retire_player_operation()` may run (nothing was entered). The `entered` flag handles it; covered by the existing terminate-during-cancel tests.
2. **`terminate()` requested inside a cancel**: `_retire_player_operation` must still run after `leave()`, so `_finish_termination`'s `wait_for(gate clear and pauses == 0)` can proceed. Existing re-entrant terminate tests cover it; name them.
3. **`pause()` failure path**: `enter`/`leave` replace the old ±1; the player stop failure inside it is logged, not raised. Covered by existing pause-failure tests.
4. **`voices()` output must be identical** (clean of `b'…'`, description by id). Test in Task 2.
5. **Drift allow-list**: it must not hide a real new divergence; the test asserts set equality, not a subset.

---

### Task 1: StopGate and exception-safe cancel (both engines)

**Files:** `driver/VE/__init__.py`, `driver/Cerence/__init__.py`, `tests/test_vocalizer_segment_drain.py`

- [ ] **Step 1: Failing test** (append; the file's `env` fixture is parametrized over VE/Cerence):

```python
def test_cancel_releases_the_stop_gate_when_abandon_fails(env, monkeypatch):
    def failing_abandon(record):
        raise RuntimeError("abandon failed")

    monkeypatch.setattr(env.core._segmentHost, "abandon", failing_abandon)
    _, _, call = speak(env)  # queue one record behind nothing; cancel will drop or stop it
    with pytest.raises(RuntimeError, match="abandon failed"):
        # Force a dropped record: queue a second segment so cancel abandons it.
        speak(env, segment=18)
        env.core.cancel()
    monkeypatch.undo()
    with env.core._speechStateLock:
        assert env.core._stopGate.clear
```

If cancel drops no record in this harness (so abandon is never reached), queue the second record through `env.core.speak(("x",))` (ordinary), which `_drop_queued_speech` drops while the first is held. Read `test_cancel_drops_a_segment_queued_behind_the_worker` for how this file holds the worker. Ledger the variant used.

- [ ] **Step 2: Run** → FAIL (`AttributeError: _stopGate`).

- [ ] **Step 3: Implement**, identically in both files:
- import `from ...runtime.engineControl import StopGate`;
- `__init__`: `self._stopGate = StopGate(self._speechStateLock)` in place of `self._stops = 0`. Check where `_speechStateLock` is created: the gate must be constructed after it;
- `_stop_player`:

```python
	def _stop_player(self):
		with self._stopGate.hold():
			try:
				with self._player_operation():
					self._real_player.stop()
			except Exception as error:
				# A failed stop leaves the player state unknown: reject successors.
				self._segmentHost.latch_control_error(error)
				raise
```

- `cancel`: as in spec §設計;
- `pause` failure path: `self._stops += 1` becomes `self._stopGate.enter()`; in its `finally`, `self._stops -= 1` followed by `notify_all()` becomes `self._stopGate.leave()`;
- the 6 readers: `self._stops == 0` becomes `self._stopGate.clear`.

- [ ] **Step 4: Run** `tests/test_vocalizer_segment_drain.py` and the contract tests → PASS; loop the vocalizer file 20×; full suite.
- [ ] **Step 5: Commit** `refactor(VE, Cerence): use the shared stop gate and release it on every cancel path`.

---

### Task 2: Ports, metadata hook, dead sentinel (both engines)

**Files:** both wrappers; `tests/test_native_strategy_guards.py`, `tests/test_f4_engine_adapters.py`

- [ ] **Step 1: Failing tests**

`tests/test_f4_engine_adapters.py`:

```python
@pytest.mark.parametrize("engine", ["VE", "Cerence"])
def test_voice_metadata_keeps_vocalizer_quirks(monkeypatch, engine):
	harness = load_real_driver_with_native_stubs(monkeypatch, engine)
	voice_class = harness.module.Voice
	monkeypatch.setattr(voice_class, "ready", classmethod(lambda cls: True), raising=False)
	monkeypatch.setattr(harness.module, "languageHandler",
		types.SimpleNamespace(getLanguageDescription=lambda locale: ""), raising=False)
	core = types.SimpleNamespace(availableVoices={
		"x": types.SimpleNamespace(id="x", language="en", displayName="Display - b'English'"),
	})
	[metadata] = voice_class.voices(core)
	assert metadata["langDescription"] == "English"
	assert metadata["description"] == f"x - English [{voice_class.engine}]"
	assert metadata["name"] == f"{voice_class.engine}:x"
```

`voices` may resolve `languageHandler` through the base module (`synthDrivers.WorldVoice.driver`) once the hook moves. Patch the name in the wrapper module **and** the base driver module the harness loaded. Find it via `sys.modules[voice_class.__mro__[1].__module__]` and patch with `raising=False`.

`tests/test_native_strategy_guards.py`:

```python
def _vocalizer_own_names(tree):
	own = _own_names(tree)
	for node in tree.body:
		if isinstance(node, ast.ClassDef):
			for item in node.body:
				if isinstance(item, ast.Assign):
					own |= {t.id for t in item.targets if isinstance(t, ast.Name)}
				if isinstance(item, ast.FunctionDef) and item.name == "_install_guard":
					own |= {
						n.attr for n in ast.walk(item)
						if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)
						and isinstance(n.value, ast.Name) and n.value.id == "self"
					}
	return own


@pytest.mark.parametrize("engine", ["VE", "Cerence"])
def test_vocalizer_inner_privates_are_listed_and_exist(engine):
	tree = ast.parse((ROOT / "driver" / engine / "__init__.py").read_text(encoding="utf-8"))
	port = f"_{engine}Port"
	privates = _class_constant(tree, port, "INNER_PRIVATES")
	overrides = _class_constant(tree, port, "INNER_OVERRIDES")
	accessed = {
		n.attr for n in ast.walk(tree)
		if isinstance(n, ast.Attribute) and n.attr.startswith("_") and not n.attr.startswith("__")
		and isinstance(n.value, ast.Name)
	}
	assert accessed - _vocalizer_own_names(tree) <= privates
	inner = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "driver" / engine / "driver").rglob("*.py"))
	assert all(re.search(rf"\b{re.escape(name)}\b", inner) for name in privates)
	synth = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SynthDriver")
	overridden = {
		n.name for n in synth.body
		if isinstance(n, ast.FunctionDef) and n.name.startswith("_") and not n.name.startswith("__")
		and re.search(rf"def {n.name}\(", inner)
	}
	assert overridden == overrides


@pytest.mark.parametrize("engine", ["VE", "Cerence"])
def test_vocalizer_retired_names_are_gone(engine):
	source = (ROOT / "driver" / engine / "__init__.py").read_text(encoding="utf-8")
	assert "_stops" not in source
	assert "_DONE" not in source
	assert "def voices(" not in source
```

Note: `accessed` takes any `Name.attr`. Attributes of other objects that are not inner privates (e.g. `record._x`) would show up. If the first run lists names such as host or runtime privates, that means the wrapper touches runtime internals. `tests/test_lifecycle_private_access.py` already forbids those, so none should appear. If some do appear and they are local helper attributes (`call.admitting` is public), add the helper class's own stores to `_vocalizer_own_names` and ledger it.

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement** in both files:
- delete `_DONE` and its two-line comment;
- add `_strip_bytes_repr(text)` at module level:

```python
def _strip_bytes_repr(text):
	return text.strip("b'").strip("'") if (text.startswith("b'") and text.endswith("'")) else text
```

- replace `voices()` with the `voiceInfoToMetadata` classmethod from the spec;
- add, after the module constants:

```python
class _VEPort:  # _CerencePort in the Cerence file
	"""Private names of the vendored inner VE driver this wrapper reads, writes or overrides.

	Not used at runtime; tests/test_native_strategy_guards.py pins these lists
	against the inner package, so an update of the vendored driver is checked here.
	"""

	INNER_PRIVATES = frozenset(
		{
			"_bgQueue", "_bgThread", "_ensureSonicStream", "_feedBuf", "_instanceCache", "_isSilence",
			"_markBuf", "_normalization", "_pcmBuf", "_player", "_rateBoost", "_resources",
			"_sonicEnabled", "_sonicInitTried", "_veCallback", "_veCallbackHandler", "_voice",
		},
	)
	INNER_OVERRIDES = frozenset({"_speak", "_onIndexReached"})
```

- In `Voice`, add the class attributes `_defaultVariant = None` and `_defaultVariantCore = None`. This makes `getattr(self, "_defaultVariantCore", None)` a plain attribute read, and the guard sees them as own names. Keep the `getattr` call if a test sets them on instances.

- [ ] **Step 4: Run** the f4 adapter tests, the guards and the vocalizer tests; then the full suite.
- [ ] **Step 5: Commit** `refactor(VE, Cerence): list inner privates, use the metadata hook and drop a dead sentinel`.

---

### Task 3: Drift test and the third contract scenario

**Files:** `tests/test_vocalizer_drift.py` (create), `tests/test_engine_segment_contract.py`

- [ ] **Step 1: Write the tests**

```python
"""VE and Cerence are hand-kept copies; any new divergence must be deliberate."""

import ast
from pathlib import Path

DRIVERS = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice/driver"
ALLOWED = {"_PROFILE", "_ContextualVECallback._process", "SynthDriver._callback_admission", "Voice.variants"}


def _definitions(source):
	tree = ast.parse(source)
	result = {}
	for node in tree.body:
		if isinstance(node, ast.ClassDef):
			for item in node.body:
				if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
					result[f"{node.name}.{item.name}"] = ast.dump(item)
				elif isinstance(item, (ast.Assign, ast.AnnAssign)):
					result[f"{node.name}.{ast.unparse(item.targets[0] if isinstance(item, ast.Assign) else item.target)}"] = ast.dump(item)
			result[node.name + ".<bases>"] = ast.dump(ast.Tuple(elts=node.bases, ctx=ast.Load()))
		elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
			result[node.name] = ast.dump(node)
		elif isinstance(node, ast.Assign):
			result[ast.unparse(node.targets[0])] = ast.dump(node)
		elif isinstance(node, (ast.Import, ast.ImportFrom)):
			result["import:" + ast.unparse(node)] = ""
	return result


def test_cerence_differs_from_ve_only_where_allowed():
	ve = (DRIVERS / "VE/__init__.py").read_text(encoding="utf-8")
	cerence = (DRIVERS / "Cerence/__init__.py").read_text(encoding="utf-8")
	cerence = cerence.replace("Cerence", "VE").replace("ttsapi", "ve2")
	left, right = _definitions(ve), _definitions(cerence)
	assert left.keys() == right.keys()
	differing = {name for name in left if left[name] != right[name]}
	assert differing == ALLOWED
```

If the normalization leaves other textual differences that are not real divergences (for example a string literal `"ve-ttsapi-..."` inside `_PROFILE`, which is allowed), keep them in `ALLOWED` only if they are the documented four. Anything else found on the first run is real drift: align the two files rather than widening the list, unless the difference is an engine API difference. Ledger each case.

Contract scenario (append to `tests/test_engine_segment_contract.py`):

```python
ORDINARY_THEN_SEGMENT = {
	"VE": "SEGMENT_FAILED",
	"Cerence": "SEGMENT_FAILED",
	"OneCore": "SEGMENT_DRAINED",
	"RHVoice": "SEGMENT_DRAINED",
	"SAPI5": "SEGMENT_DRAINED",
	"Espeak": "SEGMENT_DRAINED",
}


@pytest.mark.parametrize("engine", _engines(), indirect=True)
def test_segment_after_ordinary_speech_follows_the_engine_mode_rule(engine):
	# VE/Cerence refuse correlated mode once legacy speech ran: its callback
	# lifetimes are unproven. Every other engine runs the segment after it.
	engine.speak_ordinary(("first",))
	context = engine.PlaybackContext(object(), 27)
	events = Events(engine)
	caller, errors = _start_speak(engine, engine.new_token(), context, events)
	for _ in range(3):
		engine.complete()
		with events.condition:
			if events.condition.wait_for(lambda: bool(events), 0.5):
				break
	event = events.wait_one()
	caller.join(2)
	assert not caller.is_alive() and errors == []
	assert event.kind is getattr(engine.EventKind, ORDINARY_THEN_SEGMENT[engine.engine])
	assert event.segment_id == 27
	if event.kind is engine.EventKind.SEGMENT_FAILED:
		assert "Legacy" in str(event.error)
```

- [ ] **Step 2: Run** both files; fix real drift if any (see note), then the full suite.
- [ ] **Step 3: Commit** `test: pin VE/Cerence drift and the ordinary-then-segment contract`.

Final verification:

```bash
python3 -m pytest tests -q
ruff check addon --exclude 'addon/synthDrivers/WorldVoice/driver/*/driver' --exclude 'addon/synthDrivers/WorldVoice/driver/sonic' --select F401,F821
ruff format --check addon
git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver' addon/synthDrivers/WorldVoice/driver/sonic
```
