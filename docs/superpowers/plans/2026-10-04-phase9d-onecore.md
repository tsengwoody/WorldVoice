# Phase 9d OneCore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- Replace OneCore's stop counter with `StopGate`, adding `enter`/`leave` for its two-phase control-fault path.
- List its parent privates in `_OneCorePort`.
- Declare `Voice` after `SynthDriver`, like the other engines.

**Architecture:** `runtime/engineControl.StopGate` gains `enter`/`leave` (`hold` builds on them). The OneCore wrapper swaps `_segmentStops` for the gate, adds a port class with guard-checked name lists, and reorders its classes.

**Tech Stack:** Python 3.11; pytest; ruff format (tabs).

**Spec:** `docs/superpowers/specs/2026-10-04-phase9d-onecore-design.md`

## Global Constraints

- Never edit `driver/<Engine>/driver/` (here `driver/OneCore/driver/`) or `driver/sonic`.
- No shared code between engine packages.
- `addon/` ruff-format clean; new tests use tabs.
- `git add` explicit paths; never stage the `docs/superpowers/finish_task.md` deletion or `refactor.md`.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Full suite: `python3 -m pytest tests -q` (baseline 1507).

## Review Focus

1. **`pause()` arriving while a control-fault capture holds the gate** (between capture and deliver): `pause` must still return early. `not self._stopGate.clear` keeps that. Existing test `test_cancel_after_control_fault_capture_suppresses_pending_failure` exercises the window; name it in the ledger.
2. **`cancel()` raising from `player.stop()`**: the gate must still be released (`hold()`'s `finally`). Existing cancel-failure tests cover it; name them.
3. **`_maybeInitPlayer` during a stop**: it must not re-pause a new player while a stop is in flight. Unchanged predicate; covered by existing pause tests.
4. **AST consumers that load `Voice` from this file**: update to select by name.

---

### Task 1: `StopGate.enter/leave`

**Files:** `addon/synthDrivers/WorldVoice/runtime/engineControl.py`, `tests/test_engine_control.py`

- [ ] **Step 1: Failing test** (append):

```python
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
	assert not woke.wait(0.05)
	with condition:
		gate.leave()
	assert woke.wait(2)
```

- [ ] **Step 2: Run** → FAIL (no `enter`).
- [ ] **Step 3: Implement** per spec §設計 (`hold` uses `enter`/`leave`).
- [ ] **Step 4: Run** `tests/test_engine_control.py`, the SAPI5 and RHVoice tests → PASS.
- [ ] **Step 5: Commit** `feat(runtime): let a stop gate span a two-phase stop`.

---

### Task 2: OneCore gate, port and class order

**Files:** `addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py`, `tests/test_native_strategy_guards.py`, `tests/test_runtime_composition.py`

- [ ] **Step 1: Failing tests** (append to the guards file):

```python
NVDA_ONECORE = Path(__file__).resolve().parents[1] / "ref/nvda/source/synthDrivers/oneCore.py"
INNER_ONECORE = ROOT / "driver/OneCore/driver/__init__.py"


def _own_names(tree):
	own = set()
	for node in tree.body:
		if isinstance(node, ast.ClassDef):
			for item in node.body:
				if isinstance(item, ast.FunctionDef):
					own.add(item.name)
					if item.name == "__init__":
						own |= {
							n.attr for n in ast.walk(item)
							if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)
							and isinstance(n.value, ast.Name) and n.value.id == "self"
						}
	return own


def test_onecore_parent_privates_are_listed_and_exist():
	tree = ast.parse((ROOT / "driver/OneCore/__init__.py").read_text(encoding="utf-8"))
	privates = _class_constant(tree, "_OneCorePort", "NVDA_PRIVATES")
	overrides = _class_constant(tree, "_OneCorePort", "NVDA_OVERRIDES")
	accessed = {
		n.attr for n in ast.walk(tree)
		if isinstance(n, ast.Attribute) and n.attr.startswith("_") and not n.attr.startswith("__")
		and isinstance(n.value, ast.Name) and n.value.id in {"self", "driver", "oneCore"}
	}
	assert accessed - _own_names(tree) <= privates
	parents = INNER_ONECORE.read_text(encoding="utf-8") + NVDA_ONECORE.read_text(encoding="utf-8")
	assert all(re.search(rf"\b{re.escape(name)}\b", parents) for name in privates)
	synth = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SynthDriver")
	overridden = {
		n.name for n in synth.body
		if isinstance(n, ast.FunctionDef) and n.name.startswith("_") and not n.name.startswith("__")
		and re.search(rf"def {n.name}\(", parents)
	}
	assert overridden == overrides


def test_onecore_uses_the_stop_gate_and_declares_voice_last():
	source = (ROOT / "driver/OneCore/__init__.py").read_text(encoding="utf-8")
	assert "_segmentStops" not in source
	tree = ast.parse(source)
	names = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
	assert names.count("Voice") == 1 and names.index("Voice") > names.index("SynthDriver")
	assert not any(
		isinstance(n, ast.Assign) and any(ast.unparse(t) in {"SynthDriver", "Voice.synth_driver_class"} for t in n.targets)
		for n in tree.body
	)
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**

Imports: `from ...runtime.engineControl import StopGate`.

Delete the `SynthDriver = BaseOneCoreSynthDriver` alias with its comment, the early `class Voice`, and the trailing `Voice.synth_driver_class = SynthDriver`. Move `class Voice` (unchanged body, with `synth_driver_class = SynthDriver` written in the class body) to the end of the file, after `class SynthDriver`.

Add, before `_DetachableCallback`:

```python
class _OneCorePort:
	"""Parent private names (vendored OneCoreSynthDriver and NVDA oneCore) this wrapper uses.

	The worker and native callback re-implement the parent's flow around these,
	so they are used in place; compare these lists with both parents on upgrade.
	"""

	NVDA_PRIVATES = frozenset(
		{
			"_OcPreAPI5SsmlConverter",
			"_OcSsmlConverter",
			"_callbackInst",
			"_dll",
			"_earlyExitCB",
			"_isProcessing",
			"_ocSpeechToken",
			"_pitch",
			"_player",
			"_queuedSpeech",
			"_rate",
			"_volume",
			"_wasCancelled",
		},
	)
	NVDA_OVERRIDES = frozenset({"_queueSpeech", "_processQueue", "_callback", "_maybeInitPlayer"})
```

Gate changes, per spec §設計:
- `__init__`: `self._stopGate = StopGate(self._segmentCondition)` in place of `self._segmentStops = 0`;
- worker predicate: `self._stopGate.clear`;
- `_captureSegmentControlFailure`: `self._stopGate.enter()`;
- `_deliverSegmentControlFailure`'s finally: `self._segmentPaused = False` then `self._stopGate.leave()` (`leave` notifies);
- `_maybeInitPlayer`: `if self._segmentPaused and self._stopGate.clear:`;
- `pause`: `if self._segmentTerminated or not self._stopGate.clear: return`, and the inner `or not self._stopGate.clear`.

`cancel`:

```python
	def cancel(self):
		host = self._segmentHost
		with self._stopGate.hold():
			with host.admission():
				host.cancel()
				with self._segmentCondition:
					self._wasCancelled = True
					self._segmentPaused = False
					self._segmentControlGeneration += 1
					dropped = [item.record for item in self._queuedSpeech if isinstance(item, _SpeechJob)]
					# Settings changes keep their queue position.
					self._queuedSpeech = [item for item in self._queuedSpeech if isinstance(item, tuple)]
					self._segmentCondition.notify_all()
				# Queued records never reach the worker.
				for record in dropped:
					host.abandon(record)
			try:
				try:
					if self._player:
						self._player.stop()
				finally:
					# (keep the existing comment)
					with self._segmentPauseLock:
						if self._player:
							if host.control_error is None:
								self._player.pause(False)
							self._player.stop()
			except Exception as error:
				self._failSegmentControl(error)
				raise
```

`tests/test_runtime_composition.py:181`: `voice_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Voice")`.

- [ ] **Step 4: Run**
- `python3 -m pytest tests/test_onecore_segment_drain.py tests/test_native_strategy_guards.py tests/test_engine_segment_contract.py tests/test_runtime_composition.py tests/test_f4_engine_adapters.py -q` → PASS.
- Loop `tests/test_onecore_segment_drain.py` 20×.
- Full suite → green.
- [ ] **Step 5: Commit** `refactor(onecore): use the shared stop gate, list parent privates and declare Voice last`.

Final verification:

```bash
python3 -m pytest tests -q
ruff check addon --exclude 'addon/synthDrivers/WorldVoice/driver/*/driver' --exclude 'addon/synthDrivers/WorldVoice/driver/sonic' --select F401,F821
ruff format --check addon
git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver' addon/synthDrivers/WorldVoice/driver/sonic
```
