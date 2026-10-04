# Phase 9a Host Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- Turn `NativeStrategy` into an ABC with default hooks.
- Give `SegmentHost` one terminated behavior and one control-error behavior.
- Gather eSpeak's NVDA-private access into one port.
- Add two cross-engine contract scenarios.

**Architecture:**
- `runtime/segmentHost.py` gains the ABC and drops the `fail_accepted_on_control_error` switch.
- Every engine strategy subclasses the ABC; the other five engines change only their declarations.
- eSpeak gets `_EspeakPort`.
- The contract harness learns `speak_ordinary` and `fail_next_stop`.

**Tech Stack:** Python 3.11; pytest; ruff format (tabs).

**Spec:** `docs/superpowers/specs/2026-10-04-phase9a-host-design.md`

## Global Constraints

- Never edit `driver/<Engine>/driver/` or `driver/sonic`.
- VE and Cerence stay separate copies; no shared code between engine packages.
- `addon/` stays ruff-format clean; tests use tabs in new files.
- `git add` explicit paths; never stage the `docs/superpowers/finish_task.md` deletion or `refactor.md`.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Full suite: `python3 -m pytest tests -q` (baseline 1475).

## Review Focus

1. **A strategy that overrides none of the optional hooks** (eSpeak, RHVoice): its segments still finish, and the barrier check still fails a segment whose barriers were not reached. Test in Task 1.
2. **Ordinary speech already queued when terminate happens**: only a new `enqueue` raises. Records already pending are cancelled, as before. Test in Task 1.
3. **Control error raised while a segment is mid-delivery on eSpeak/SAPI5**: exactly one terminal event, and it is FAILED. Covered by the existing host race test (now unconditional) in Task 1.
4. **eSpeak after terminate**: NVDA's `_espeak.terminate()` nulls the module globals. Any later `cancel()` on the wrapper must not touch `_espeak.player` (it does not today: `cancel` skips `super().cancel()` when terminated). Pin it in Task 2.
5. **Contract stop-failure scenario on an engine that needs a segment in flight** for `cancel()` to stop the player. Mark such an engine xfail with a reason; never weaken the assertion. Task 3.

---

### Task 1: `NativeStrategy` ABC and the host's single behaviors

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/runtime/segmentHost.py`
- Modify: the `class _XStrategy` declarations and `SegmentHost(...)` calls in `driver/{Espeak,SAPI5,RHVoice,OneCore,VE,Cerence}/__init__.py`
- Test: `tests/test_segment_host.py`, `tests/test_native_strategy_guards.py` (create)

**Interfaces:**
- Produces: `NativeStrategy(ABC)`, with abstract `submit/stop_native/stop_player` and default `prepare/admission_error/drain`.
- `SegmentHost(engine, strategy)` (no `fail_accepted_on_control_error`).

- [ ] **Step 1: Write the failing tests**

In `tests/test_segment_host.py`:
- Delete the default (`{}`) parameter rows of `test_control_error_and_an_unpublished_drain` and `test_control_error_and_the_active_segment`.
- Change the remaining parameter to `{}` (the switch no longer exists). Do the same for the `[{"fail_accepted_on_control_error": True}]` indirect parameter at about line 835.
- Read the `env` fixture to see how it passes these kwargs to `SegmentHost`. After this change the fixture passes none.

Then append:

```python
def test_default_hooks_finish_a_segment(env):
	# env's strategy may define hooks; a bare subclass must still work.
	host_module = sys.modules[type(env.host).__module__]

	class Bare(host_module.NativeStrategy):
		barriers = frozenset({"done"})

		def submit(self, host, record, commands):
			host.begin(record)
			host.reach(record, "done")
			Thread(target=host.retire, args=(record,), daemon=True).start()

		def stop_native(self, host, record):
			pass

		def stop_player(self, host):
			pass

	strategy = Bare()
	assert strategy.prepare(None, ("x",), None) == ("x",)
	assert strategy.admission_error(None) is None
	assert strategy.drain(None, None) is None


def test_terminated_host_rejects_new_ordinary_speech(env):
	env.host.terminate()
	with pytest.raises(RuntimeError, match="terminated"):
		env.host.enqueue(("late",))
```

Before writing them, adapt the names (`env`, `sys`, `Thread`, the event helpers) to what `tests/test_segment_host.py` already imports and builds. Read its fixture first. If the fixture builds the host with a strategy object, add a third test that runs one segment end-to-end through a `SegmentHost` constructed with `Bare()`, using the file's existing speak/wait helpers, and asserts one `SEGMENT_DRAINED`.

`tests/test_native_strategy_guards.py`:

```python
"""Every engine strategy is a NativeStrategy, and the host never probes for hooks."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice"
ENGINES = ("Espeak", "SAPI5", "RHVoice", "OneCore", "VE", "Cerence")


def test_every_strategy_subclasses_native_strategy():
	for engine in ENGINES:
		tree = ast.parse((ROOT / "driver" / engine / "__init__.py").read_text(encoding="utf-8"))
		strategies = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name.endswith("Strategy")]
		assert strategies, engine
		for node in strategies:
			assert [ast.unparse(base) for base in node.bases] == ["NativeStrategy"], (engine, node.name)


def test_host_has_no_optional_hook_probing_or_failure_switch():
	host = (ROOT / "runtime/segmentHost.py").read_text(encoding="utf-8")
	assert "getattr(self._strategy" not in host
	for path in ROOT.rglob("*.py"):
		assert "fail_accepted_on_control_error" not in path.read_text(encoding="utf-8"), path
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_segment_host.py tests/test_native_strategy_guards.py -q`
Expected: failures for the guard tests (strategies have no base; the switch exists), the new ABC test (`NativeStrategy` is a `Protocol`, so `prepare` is missing on a subclass), the terminated test (no raise), and the reparameterised drain tests (DRAINED instead of FAILED).

- [ ] **Step 3: Implement**

`segmentHost.py`:
- Replace `from typing import Protocol` with `from abc import ABC, abstractmethod`.
- Replace the `NativeStrategy` class with the spec §1 ABC, keeping the existing docstrings of the three abstract methods, and turning the optional-hook comments into the default methods' docstrings.
- `__init__(self, engine: str, strategy: NativeStrategy)`; delete `self._fail_accepted` and its comment.
- `speak_segment`: `engine_error = self._strategy.admission_error(self)`.
- `enqueue`:

```python
		work = operation.work if operation is not None else None
		# Engine preparation (e.g. SSML conversion) runs outside admission so
		# cancel() and terminate() never wait for it.
		try:
			commands = self._strategy.prepare(self, commands, operation)
		except Exception as error:
			if operation is None:
				raise
			self._lifecycle_of(operation).fail(operation, error)
			return
		record = self.new_record(operation, barriers=barriers, native=native)
		with self._admission:
			if self._terminated:
				if work is None:
					raise RuntimeError(f"{self.engine} driver has terminated")
				work.cancel()
				return
```

  (the rest unchanged).
- `latch_control_error`: `accepted = tuple(self._accepted)`, and the comment says every accepted operation fails ("a stop failure must not be reported as success").
- `_deliver`: drop `self._fail_accepted and` from the condition.
- `wait_playback_drained`:

```python
		try:
			self._strategy.drain(self, record)
		except Exception as error:
			# A raising drain fails this segment, never the whole lifecycle.
			self.record_error(record, error)
			lifecycle.fail(operation, record.error)
			self._strategy.stop_player(self)
			return
		if record.error is not None:
			# The strategy already stopped or purged what it needed to.
			lifecycle.fail(operation, record.error)
			return
```

  followed by the existing barrier check.
- Update the module docstring sentence "An engine provides a NativeStrategy (how to queue, stop and drain its native work)…" only if it mentions optional hooks.

Engines:
- Each `class _XStrategy:` becomes `class _XStrategy(NativeStrategy):`; add `NativeStrategy` to each file's `from ...runtime.segmentHost import ...` line.
- Remove `, fail_accepted_on_control_error=True` from VE, Cerence, OneCore and RHVoice. Collapse multi-line calls if ruff format does so.

- [ ] **Step 4: Run to verify**

Run: `python3 -m pytest tests/test_segment_host.py tests/test_native_strategy_guards.py -q` → PASS.
Then run `python3 -m pytest tests -q` → all pass. Fix any eSpeak/SAPI5 test that asserted DRAINED after a control error, or silent ordinary speech after terminate: change it to the new behavior and ledger each one. The probe run before planning showed none outside `test_segment_host.py`.

- [ ] **Step 5: Commit**

```bash
ruff format addon/synthDrivers/WorldVoice
git add addon/synthDrivers/WorldVoice/runtime/segmentHost.py addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py addon/synthDrivers/WorldVoice/driver/VE/__init__.py addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py tests/test_segment_host.py tests/test_native_strategy_guards.py
git commit -m "refactor(runtime): make NativeStrategy an ABC and give the host one failure behavior

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: eSpeak port and drain-support signature

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py`
- Test: `tests/test_native_strategy_guards.py` (append), `tests/test_espeak_segment_drain.py` (append)

**Interfaces:**
- Produces: `_EspeakPort` with `install(host, driver)`, `run_when_done(function, record)`, `set_index_callback(callback)`, `stop_player()`, `mark_not_speaking()` and `ok`.
- `SynthDriver._port`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_native_strategy_guards.py`:

```python
def test_espeak_touches_nvda_privates_only_through_its_port():
	tree = ast.parse((ROOT / "driver/Espeak/__init__.py").read_text(encoding="utf-8"))
	port = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "_EspeakPort")
	inside = {id(node) for node in ast.walk(port)}
	outside = [
		node.lineno for node in ast.walk(tree)
		if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
		and node.value.id == "_espeak" and id(node) not in inside
	]
	assert outside == []


def test_espeak_drain_support_requires_keywords():
	tree = ast.parse((ROOT / "driver/Espeak/__init__.py").read_text(encoding="utf-8"))
	method = next(
		n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "get_segment_drain_support"
	)
	assert [a.arg for a in method.args.kwonlyargs] == ["nvda_version", "audio_mode"]
	assert method.args.kw_defaults == [None, None]
```

Append to `tests/test_espeak_segment_drain.py` (match the file's fixture name `env` and helpers):

```python
def test_cancel_after_terminate_leaves_nvda_espeak_alone(env):
	env.driver.terminate()
	env.driver.cancel()  # must not reach NVDA's terminated _espeak module
```

Before writing it, check what `finish(env)`/fixture teardown does after a terminate, and whether `env.driver.terminate()` is already exercised. If `finish` terminates again, that is fine: terminate is idempotent.

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_native_strategy_guards.py -q -k espeak` → FAIL (no `_EspeakPort`; the signature has defaults). The cancel-after-terminate test likely already passes: it pins existing behavior (Review Focus 4). Note that in the ledger.

- [ ] **Step 3: Implement**

In `driver/Espeak/__init__.py`, keep `_SegmentNative` but make it take `ok`:

```python
class _SegmentNative:
	"""Observe errors swallowed by NVDA's native callback/queue boundaries."""

	def __init__(self, driver, native, ok):
		self._driver = weakref.ref(driver)
		self._native = native
		self._ok = ok
```

Replace every `_espeak.EE_OK` inside it with `self._ok`.

Add:

```python
class _EspeakPort:
	"""Every NVDA private the wrapper touches in synthDrivers._espeak.

	NVDA's _espeak.terminate() resets player, espeakDLL and onIndexReached to
	None, so nothing here needs restoring.
	"""

	@property
	def ok(self):
		return _espeak.EE_OK

	def install(self, host, driver):
		_espeak.player = LeasedPlayer(host, _espeak.player)
		_espeak.espeakDLL = _SegmentNative(driver, _espeak.espeakDLL, _espeak.EE_OK)

	def run_when_done(self, function, record):
		_espeak._execWhenDone(function, record, mustBeAsync=True)

	def set_index_callback(self, callback):
		_espeak.onIndexReached = callback

	def mark_not_speaking(self):
		_espeak.isSpeaking = False

	def stop_player(self):
		_espeak.isSpeaking = False
		_espeak.player.stop()
```

Strategy (now `_EspeakStrategy(NativeStrategy)`):

```python
	def submit(self, host, record, commands):
		driver = self._driver()
		# Begin and retirement remain separate queue entries: NVDA stop()
		# removes queued _speak calls but preserves both identity barriers.
		driver._port.run_when_done(driver._beginSpeech, record)
		try:
			BaseSynthDriver.speak(driver, commands)
		except Exception as error:
			host.record_error(record, error)
		finally:
			driver._port.run_when_done(driver._retireSpeech, record)

	def stop_native(self, host, record):
		self.stop_player(host)

	def stop_player(self, host):
		self._driver()._port.stop_player()
```

Driver:
- `__init__`: `self._port = _EspeakPort()` before creating the host. After `super().__init__()`, call `self._port.install(self._segmentHost, self)`, replacing the two `_espeak.` assignments.
- `_beginSpeech`: `self._port.set_index_callback(index_callback)`.
- `_retireSpeech`: `self._port.mark_not_speaking()`.
- `def get_segment_drain_support(self, *, nvda_version: str, audio_mode: str) -> DrainSupport:`; import `DrainSupport` from `...runtime.playbackWork`.

`_espeak.EE_OK` in `_SegmentNative` was the only other access; it is now `self._ok`. Confirm with the guard.

- [ ] **Step 4: Run to verify**

Run: `python3 -m pytest tests/test_native_strategy_guards.py tests/test_espeak_segment_drain.py -q` → PASS.
Then run `python3 -m pytest tests -q` → all pass. If a test calls `get_segment_drain_support()` on eSpeak without keywords, give it the keywords (`grep -rn "get_segment_drain_support(" tests`).

- [ ] **Step 5: Commit**

```bash
ruff format addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py
git add addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py tests/test_native_strategy_guards.py tests/test_espeak_segment_drain.py
git commit -m "refactor(espeak): route NVDA _espeak access through one port

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Two cross-engine contract scenarios

**Files:**
- Modify: `tests/engine_contract_harness.py`, `tests/test_engine_segment_contract.py`

**Interfaces:**
- Produces: adapter methods `speak_ordinary(commands)` and `fail_next_stop()`.

- [ ] **Step 1: Write the tests**

`tests/engine_contract_harness.py`: add to `_Adapter`:

```python
	def speak_ordinary(self, commands):
		self.core.speak(commands)

	def _player(self):
		return self.env.player

	def fail_next_stop(self):
		"""Make the engine's real player fail its next stop() once."""
		player = self._player()
		original = player.stop
		failures = [OSError("player stop failed")]

		def stop(*args, **kwargs):
			if failures:
				raise failures.pop()
			return original(*args, **kwargs)

		player.stop = stop
```

Overrides:
- `RHVoiceAdapter._player` returns `self.core._SynthDriver__player`;
- `_NuanceAdapter._player` returns `self.core._real_player`;
- eSpeak, SAPI5 and OneCore use `env.player`.

Check each harness: eSpeak's `env.player` is the fake behind `LeasedPlayer`; SAPI5's `env.player` must be the one the driver currently uses (the SAPI5 env has a `players` list; if `env.player` is not the latest, use `self.env.players[-1]`).

`tests/test_engine_segment_contract.py`: append:

```python
@pytest.mark.parametrize("engine", _engines(), indirect=True)
def test_ordinary_speak_after_terminate_raises(engine):
	engine.terminate()
	with pytest.raises(RuntimeError):
		engine.speak_ordinary(("hello",))


@pytest.mark.parametrize("engine", _engines(), indirect=True)
def test_segment_after_player_stop_failure_fails(engine):
	engine.fail_next_stop()
	with suppress(Exception):
		engine.core.cancel()
	context = engine.PlaybackContext(object(), 25)
	events = Events(engine)
	caller, errors = _start_speak(engine, engine.new_token(), context, events)

	event = events.wait_one()
	caller.join(2)

	assert not caller.is_alive() and errors == []
	assert event.kind is engine.EventKind.SEGMENT_FAILED
	assert event.segment_id == 25
```

Add `from contextlib import suppress` to the imports.

- [ ] **Step 2: Run**

Run: `python3 -m pytest tests/test_engine_segment_contract.py -q -k "after_terminate_raises or stop_failure_fails"`
Expected: `after_terminate_raises` passes for all six after Task 1. For `stop_failure_fails`, record which engines fail and why: read the failure, then check whether that engine's `cancel()` calls the player's `stop()` while idle and whether a failure there latches. If an engine does not latch on that path, or does not stop an idle player, give it a strict xfail.

- `_engines` currently supports only C3-style xfails. Extend it to `_engines(**xfails)` where each value is a `(reason, raises)` pair:

```python
def _engines(**xfails):
	params = []
	for name in ADAPTERS:
		marks = []
		if name in xfails:
			reason, raises = xfails[name]
			# Only the known gap may xfail; any other failure still fails the run.
			marks.append(pytest.mark.xfail(strict=True, raises=raises, reason=reason))
		params.append(pytest.param(name, marks=marks, id=name))
	return params
```

  No existing call passes xfails today (`grep -n "_engines(" tests/test_engine_segment_contract.py`). If one does, convert it.
- If the failure is "no terminal event delivered" because the segment drained instead, the raised type is `AssertionError`. Use `raises=AssertionError` and a reason naming the path (e.g. `"SAPI5 cancel() does not latch a player stop failure (9b)"`).
- An engine that fails because the fake idles forever should not get an xfail. Fix the adapter so `complete()` is not needed: the scenario expects FAILED without completing.

- [ ] **Step 3: Verify**

Run: `python3 -m pytest tests/test_engine_segment_contract.py -q` → all pass or xfail (no XPASS).
Then run `python3 -m pytest tests -q` → green.

- [ ] **Step 4: Commit**

```bash
git add tests/engine_contract_harness.py tests/test_engine_segment_contract.py
git commit -m "test(contract): pin ordinary speech after terminate and segments after a stop failure

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Final verification (after Task 3):

```bash
python3 -m pytest tests -q
ruff check addon --exclude 'addon/synthDrivers/WorldVoice/driver/*/driver' --exclude 'addon/synthDrivers/WorldVoice/driver/sonic' --select F401,F821
ruff format --check addon
git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver' addon/synthDrivers/WorldVoice/driver/sonic
```
