# Phase 1: Engine Segment Contract Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One parametrized test file that pins four `speak_segment` contract items across all seven outer engine wrappers, with the known C3 gap (VE, Cerence) visible as strict xfails.

**Architecture:** `tests/engine_contract_harness.py` holds one small adapter per engine. Each adapter reuses that engine's existing loader and fakes. After `open()` the fakes hold every segment before completion, and `complete()` releases it. `tests/test_engine_segment_contract.py` parametrizes four tests over the adapters. These tests pin behavior that already exists, so each one is proven able to fail with a temporary production mutation that is reverted with `git checkout` before commit.

**Tech Stack:** Python 3, pytest (indirect parametrization, strict xfail), the existing per-engine fake harnesses under `tests/`.

**Spec:** `docs/superpowers/specs/2026-10-01-phase1-engine-segment-contract-design.md`

## Global Constraints

- Work on branch `phase1-engine-contract`, cut from `master` at `0fa002b`. It already holds the spec commit and the amended spec.
- Do not change any file under `addon/`. Mutation steps edit production files only temporarily; each one ends with `git checkout -- <file>`, and `git status --short` must show no `addon/` change before any commit.
- Never add `addon/synthDrivers/WorldVoice/driver/Neural/` to a commit. Neural is only extracted inside the temporary worktree of Task 5.
- New test files use tab indentation. They must pass `ruff format --check` and `ruff check`; ruff's own import order is used as-is.
- Keep every existing test file unchanged.
- Run from `/workspace/WorldVoice` (tests need the untracked `ref/` there).
- Baseline before Task 1, without Neural: `python3 -m pytest tests -q` → `1233 passed, 92 skipped`.
- Every commit message ends with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A segment produces a second terminal event shortly after the first → the contract must catch it, not pass on the first event (Task 1, `Events.wait_one` waits 0.1 s for a duplicate; proven by mutation M1).
2. An adapter leaves a fake held when a test fails midway → the run must not hang; `close()` releases every hold before `terminate()` (Task 4, Step 3 runs the xfail cases, whose callers stay blocked until `close()`).
3. VE or Cerence stops blocking in a later phase → the strict xfail must turn into a failure so the mark gets removed (Task 4, Step 4 `--runxfail` shows the exact failing assertion that must flip).
4. A loader's runtime copy differs from the one the test compares against → enum identity checks would fail spuriously; adapters take `EventKind` from their own `env.rt` (Task 1, every assertion uses `engine.EventKind`).
5. Neural is restored locally → its four cases must run and pass, not stay skipped (Task 5, temporary worktree with the snapshot).

---

### Task 1: Adapter harness and contract 1 (completed segment drains once)

**Files:**
- Create: `tests/engine_contract_harness.py`
- Create: `tests/test_engine_segment_contract.py`

**Interfaces:**
- Consumes the existing loaders: `espeak_drain_harness.load_espeak(monkeypatch, tmp_path)` and `finish`, `rhvoice_drain_harness.load_rhvoice(monkeypatch, tmp_path)` and `finish`, `onecore_drain_harness.load_onecore(monkeypatch)` and `in_thread`, `neural_drain_harness.load_neural(monkeypatch, tmp_path)` and `requires_neural`, `test_sapi5_segment_drain.load_sapi5(monkeypatch)`, `worldvoice_cancel_wrapper_harness.load_real_driver_with_native_stubs(monkeypatch, engine)`, `test_vocalizer_segment_drain.emit(env, instance)`, `test_worldvoice_cancel_wrappers.Token`.
- Produces, for Tasks 2–4:
  - Adapter attributes `engine: str`, `EventKind`, `PlaybackContext`.
  - Adapter methods `open(monkeypatch, tmp_path)`, `close()`, `new_token()`, `speak(commands, token, context, sink)`, `complete()`, `terminate()`, `native_call_count() -> int`, `delivery_thread_ident() -> int | None`.
  - In the test file: `ADAPTERS`, `_engines(**xfails) -> list[pytest.param]`, `_c3(engine) -> str`, `Events` (with `.condition`, `.threads`, `.wait_one(timeout=2)`), the indirect fixture `engine`, and `_start_speak(adapter, token, context, events) -> (Thread, list)`.

- [ ] **Step 1: Create the harness**

Create `tests/engine_contract_harness.py`:

```python
"""Engine adapters for the shared segment contract tests.

Each adapter loads one real outer engine wrapper with that engine's existing
fakes. After ``open`` the fakes hold every segment before its final playback
barrier; only ``complete`` lets the current segment finish. Private runtime
access stays here so later phases only need to update the adapters.
"""

import sys
from threading import Event

from espeak_drain_harness import finish as finish_espeak
from espeak_drain_harness import load_espeak
from neural_drain_harness import load_neural
from onecore_drain_harness import in_thread, load_onecore
from rhvoice_drain_harness import finish as finish_rhvoice
from rhvoice_drain_harness import load_rhvoice
from test_sapi5_segment_drain import load_sapi5
from test_vocalizer_segment_drain import emit
from test_worldvoice_cancel_wrappers import Token
from worldvoice_cancel_wrapper_harness import load_real_driver_with_native_stubs


def _fresh_lifecycle_module(monkeypatch):
	# Each loader reloads runtime models; reload the coordinator too so its
	# event enum belongs to that same runtime copy.
	monkeypatch.delitem(sys.modules, "synthDrivers.WorldVoice.runtime.segmentLifecycle", raising=False)


class _Adapter:
	engine = ""

	def bind(self, env, core):
		self.env = env
		self.core = core
		self.EventKind = env.rt.models.EventKind
		self.PlaybackContext = env.rt.models.PlaybackContext

	def new_token(self):
		return self.env.scheduler.CancellationToken()

	def speak(self, commands, token, context, sink):
		self.core.speak_segment(commands, token, context=context, on_event=sink)

	def terminate(self):
		self.core.terminate()

	def delivery_thread_ident(self):
		thread = self.core._segmentLifecycle._delivery_thread
		return None if thread is None else thread.ident


class EspeakAdapter(_Adapter):
	engine = "Espeak"

	def open(self, monkeypatch, tmp_path):
		_fresh_lifecycle_module(monkeypatch)
		env = load_espeak(monkeypatch, tmp_path)
		self.bind(env, env.driver)

	def complete(self):
		self.env.native.wait_calls(1)
		self.env.player.idle_release.set()
		self.env.native.release()

	def native_call_count(self):
		return len(self.env.native.calls)

	def close(self):
		finish_espeak(self.env)


class RHVoiceAdapter(_Adapter):
	engine = "RHVoice"

	def open(self, monkeypatch, tmp_path):
		_fresh_lifecycle_module(monkeypatch)
		env = load_rhvoice(monkeypatch, tmp_path)
		self.bind(env, env.driver)

	def complete(self):
		self.env.native.wait_call()
		self.env.native.release()

	def native_call_count(self):
		return len(self.env.native.calls)

	def close(self):
		finish_rhvoice(self.env)


class SAPI5Adapter(_Adapter):
	engine = "SAPI5"

	def open(self, monkeypatch, tmp_path):
		_fresh_lifecycle_module(monkeypatch)
		env = load_sapi5(monkeypatch)
		self.bind(env, env.driver)

	def complete(self):
		self.env.native.wait_calls(1)
		self.env.native.end(self.env.native.calls[-1][0])
		self.env.player.idle_release.set()

	def native_call_count(self):
		return len(self.env.native.calls)

	def close(self):
		for player in self.env.players:
			player.feed_release.set()
			player.idle_release.set()
			player.stop_error = None
		for native in self.env.natives:
			native.purge_error = None
		self.core.terminate()


class OneCoreAdapter(_Adapter):
	engine = "OneCore"

	def open(self, monkeypatch, tmp_path):
		_fresh_lifecycle_module(monkeypatch)
		env = load_onecore(monkeypatch)
		self.bind(env, env.driver)

	def complete(self):
		self.env.native.wait_calls(1)
		response = in_thread(lambda: self.env.native.respond(frames=8, markers=""))
		assert response.done.wait(2), "OneCore callback did not return"
		assert response.errors == []
		self.env.player.sync_release.set()

	def native_call_count(self):
		return len(self.env.native.calls)

	def close(self):
		self.env.player.feed_release.set()
		self.env.player.sync_release.set()
		self.core.terminate()


class NeuralAdapter(_Adapter):
	engine = "Neural"

	def open(self, monkeypatch, tmp_path):
		_fresh_lifecycle_module(monkeypatch)
		env = load_neural(monkeypatch, tmp_path)
		self.bind(env, env.driver)

	def complete(self):
		self.env.native.wait_calls(1)
		self.env.native.speak_release.set()
		self.env.player.idle_release.set()

	def native_call_count(self):
		return len(self.env.native.calls)

	def close(self):
		self.env.native.speak_release.set()
		self.env.native.stop_release.set()
		self.env.player.feed_release.set()
		self.env.player.idle_release.set()
		self.env.player.stop_release.set()
		self.core.terminate()


class _NuanceAdapter(_Adapter):
	def open(self, monkeypatch, tmp_path):
		_fresh_lifecycle_module(monkeypatch)
		env = load_real_driver_with_native_stubs(monkeypatch, self.engine)
		core = env.new_core()
		env.core = core
		core._veCallbackHandler._ensureSonicStream = lambda: False
		monkeypatch.setattr(env.original_driver.synthIndexReached, "notify", lambda **kwargs: None)
		monkeypatch.setattr(env.original_driver.synthDoneSpeaking, "notify", lambda **kwargs: None)
		# The fake SDK has no native resources to release on terminate.
		monkeypatch.setattr(env.native, "close", lambda instance: None)
		monkeypatch.setattr(env.native, "terminate", lambda: None)
		self.idle_release = Event()
		core._real_player.idle = lambda: self.idle_release.wait(3)
		core._real_player.stop = self.idle_release.set
		self.calls = []

		def native(instance, text):
			self.calls.append(text)
			emit(env, instance)

		monkeypatch.setattr(env.native, "processText2Speech", native)
		self.bind(env, core)

	def new_token(self):
		return Token()

	def complete(self):
		self.idle_release.set()

	def native_call_count(self):
		return len(self.calls)

	def close(self):
		self.idle_release.set()
		self.core.terminate()


class VEAdapter(_NuanceAdapter):
	engine = "VE"


class CerenceAdapter(_NuanceAdapter):
	engine = "Cerence"
```

- [ ] **Step 2: Create the test file with contract 1**

Create `tests/test_engine_segment_contract.py`:

```python
"""Segment contract every outer engine wrapper must keep for the scheduler.

The adapters in engine_contract_harness drive each engine's own fakes. Known
gaps are strict xfails: fixing one turns it into XPASS, which fails the run
until the mark is removed.
"""

from threading import Condition, Thread, get_ident

import pytest
from engine_contract_harness import (
	CerenceAdapter,
	EspeakAdapter,
	NeuralAdapter,
	OneCoreAdapter,
	RHVoiceAdapter,
	SAPI5Adapter,
	VEAdapter,
)
from neural_drain_harness import requires_neural

ADAPTERS = {
	"VE": VEAdapter,
	"Cerence": CerenceAdapter,
	"OneCore": OneCoreAdapter,
	"RHVoice": RHVoiceAdapter,
	"SAPI5": SAPI5Adapter,
	"Espeak": EspeakAdapter,
	"Neural": NeuralAdapter,
}


def _engines(**xfails):
	params = []
	for name in ADAPTERS:
		marks = [requires_neural] if name == "Neural" else []
		if name in xfails:
			marks.append(pytest.mark.xfail(strict=True, reason=xfails[name]))
		params.append(pytest.param(name, marks=marks, id=name))
	return params


def _c3(engine):
	return f"C3: {engine} speak_segment blocks until delivery; fixed by SegmentHost in phase 3"


class Events(list):
	def __init__(self):
		super().__init__()
		self.condition = Condition()
		self.threads = []

	def append(self, event):
		with self.condition:
			super().append(event)
			self.threads.append(get_ident())
			self.condition.notify_all()

	def wait_one(self, timeout=2):
		with self.condition:
			assert self.condition.wait_for(lambda: bool(self), timeout), "no terminal event delivered"
		# A duplicate delivered shortly after the first event must still be caught.
		with self.condition:
			self.condition.wait_for(lambda: len(self) > 1, 0.1)
			assert len(self) == 1, f"expected one terminal event, got {list(self)}"
			return self[0]


@pytest.fixture
def engine(request, monkeypatch, tmp_path):
	adapter = ADAPTERS[request.param]()
	adapter.open(monkeypatch, tmp_path)
	yield adapter
	adapter.close()


def _start_speak(adapter, token, context, events):
	errors = []

	def run():
		try:
			adapter.speak(("hello",), token, context, events.append)
		except Exception as error:  # noqa: BLE001 - the test reports any caller-thread failure
			errors.append(error)

	thread = Thread(target=run, name="contract caller", daemon=True)
	thread.start()
	return thread, errors


@pytest.mark.parametrize("engine", _engines(), indirect=True)
def test_completed_segment_drains_once_on_the_delivery_thread(engine):
	context = engine.PlaybackContext(object(), 17)
	events = Events()
	caller, errors = _start_speak(engine, engine.new_token(), context, events)

	engine.complete()
	event = events.wait_one()
	caller.join(2)

	assert not caller.is_alive() and errors == []
	assert event.kind is engine.EventKind.SEGMENT_DRAINED
	assert event.source_id is context.source_id
	assert event.segment_id == 17
	assert events.threads == [engine.delivery_thread_ident()]
	assert events.threads[0] != caller.ident
```

- [ ] **Step 3: Run contract 1**

Run: `python3 -m pytest tests/test_engine_segment_contract.py -q`
Expected: `6 passed, 1 skipped` (Neural is skipped because it is not installed).

- [ ] **Step 4: Prove contract 1 can fail (mutation M1)**

Make the coordinator deliver every terminal event twice, run, then restore:

```bash
L=addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py
sed -i 's/^\t\t\t\t\toperation._sink(event)$/\t\t\t\t\toperation._sink(event)\n\t\t\t\t\toperation._sink(event)/' $L
git diff --stat -- $L
python3 -m pytest tests/test_engine_segment_contract.py -q 2>&1 | tail -1
git checkout -- $L
git status --short
```

Expected:
- `git diff --stat` shows `1 file changed, 1 insertion(+)`.
- The test run ends with `6 failed, 1 skipped`, and each failure says `expected one terminal event`.
- After `git checkout`, `git status --short` lists only the two new test files.

- [ ] **Step 5: Style checks**

Run: `ruff format --check tests/engine_contract_harness.py tests/test_engine_segment_contract.py && ruff check tests/engine_contract_harness.py tests/test_engine_segment_contract.py`
Expected: `2 files already formatted`, then `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add tests/engine_contract_harness.py tests/test_engine_segment_contract.py
git commit -m "test: add engine segment contract harness and completed-segment contract

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Contract 2 (segment after terminate fails once)

**Files:**
- Modify: `tests/test_engine_segment_contract.py` (append)

**Interfaces:**
- Consumes the Task 1 adapter API, plus `_engines`, `Events` and `_start_speak`.
- Produces nothing new.

- [ ] **Step 1: Append contract 2**

Append to `tests/test_engine_segment_contract.py`:

```python


@pytest.mark.parametrize("engine", _engines(), indirect=True)
def test_segment_after_terminate_fails_once_without_native_call(engine):
	engine.terminate()
	context = engine.PlaybackContext(object(), 19)
	events = Events()
	caller, errors = _start_speak(engine, engine.new_token(), context, events)

	event = events.wait_one()
	caller.join(2)

	assert not caller.is_alive() and errors == []
	assert event.kind is engine.EventKind.SEGMENT_FAILED
	assert event.source_id is context.source_id
	assert event.segment_id == 19
	assert engine.native_call_count() == 0
```

- [ ] **Step 2: Run it**

Run: `python3 -m pytest tests/test_engine_segment_contract.py -q -k test_segment_after_terminate`
Expected: `6 passed, 1 skipped, 7 deselected`

- [ ] **Step 3: Prove it can fail (mutation M2: undo phase 0's eSpeak C1 fix)**

```bash
E=addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py
python3 - <<'PY'
p = "addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py"
s = open(p).read()
old = """			if self._segmentTerminated:
				self._segmentLifecycle.reject_new(
					context,
					token,
					on_event,
					RuntimeError("eSpeak driver has terminated"),
				)
				return"""
assert s.count(old) == 1
open(p, "w").write(s.replace(old, """			if self._segmentTerminated:
				return"""))
PY
python3 -m pytest tests/test_engine_segment_contract.py -q -k test_segment_after_terminate 2>&1 | grep -E "^FAILED|passed|failed" | sed 's/ - .*//'
git checkout -- $E
git status --short
```

Expected: only `test_segment_after_terminate_fails_once_without_native_call[Espeak]` FAILED, with the summary `1 failed, 5 passed, 1 skipped, 7 deselected`. After `git checkout`, no `addon/` change is listed.

- [ ] **Step 4: Style checks and commit**

Run: `ruff format --check tests/test_engine_segment_contract.py && ruff check tests/test_engine_segment_contract.py`
Expected: `1 file already formatted`, `All checks passed!`

```bash
git add tests/test_engine_segment_contract.py
git commit -m "test: pin the post-terminate failure contract for every engine

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Contract 3 (cancelled token never reaches native or sink)

**Files:**
- Modify: `tests/test_engine_segment_contract.py` (append)

**Interfaces:**
- Consumes the Task 1 adapter API, plus `_engines`, `Events` and `_start_speak`.
- Produces nothing new.

- [ ] **Step 1: Append contract 3**

Append to `tests/test_engine_segment_contract.py`:

```python


@pytest.mark.parametrize("engine", _engines(), indirect=True)
def test_cancelled_token_never_reaches_native_or_sink(engine):
	token = engine.new_token()
	token.cancel()
	events = Events()
	caller, errors = _start_speak(engine, token, engine.PlaybackContext(object(), 21), events)

	caller.join(2)
	with events.condition:
		events.condition.wait_for(lambda: bool(events), 0.2)

	assert not caller.is_alive() and errors == []
	assert engine.native_call_count() == 0
	assert list(events) == []
```

- [ ] **Step 2: Run it**

Run: `python3 -m pytest tests/test_engine_segment_contract.py -q -k test_cancelled_token`
Expected: `6 passed, 1 skipped, 14 deselected`

- [ ] **Step 3: Prove it can fail (mutation M3: `PlaybackWork.is_valid` ignores the token)**

```bash
P=addon/synthDrivers/WorldVoice/runtime/playbackWork.py
sed -i 's/^\t\t\treturn self._active and not self._token.is_cancelled()$/\t\t\treturn self._active/' $P
git diff --stat -- $P
python3 -m pytest tests/test_engine_segment_contract.py -q -k test_cancelled_token 2>&1 | grep -E "^FAILED|passed|failed" | sed 's/ - .*//'
git checkout -- $P
git status --short
```

Expected:
- `git diff --stat` shows `1 file changed, 1 insertion(+), 1 deletion(-)`.
- These four fail: `[OneCore]`, `[RHVoice]`, `[SAPI5]`, `[Espeak]`. The summary reads `4 failed, 2 passed, 1 skipped, 14 deselected`.
- VE and Cerence still pass because their wrappers check the token themselves, outside `PlaybackWork`.
- After `git checkout`, no `addon/` change is listed.

- [ ] **Step 4: Style checks and commit**

Run: `ruff format --check tests/test_engine_segment_contract.py && ruff check tests/test_engine_segment_contract.py`
Expected: `1 file already formatted`, `All checks passed!`

```bash
git add tests/test_engine_segment_contract.py
git commit -m "test: pin the cancelled-token contract for every engine

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Contract 4 (speak_segment returns before delivery) with the C3 strict xfails

**Files:**
- Modify: `tests/test_engine_segment_contract.py` (append)

**Interfaces:**
- Consumes the Task 1 adapter API, plus `_engines`, `_c3`, `Events` and `_start_speak`.
- Produces nothing new.

- [ ] **Step 1: Append contract 4**

Append to `tests/test_engine_segment_contract.py`:

```python


@pytest.mark.parametrize("engine", _engines(VE=_c3("VE"), Cerence=_c3("Cerence")), indirect=True)
def test_speak_segment_returns_before_delivery(engine):
	context = engine.PlaybackContext(object(), 23)
	events = Events()
	caller, errors = _start_speak(engine, engine.new_token(), context, events)

	caller.join(1)
	returned_early = not caller.is_alive()
	delivered_early = list(events)
	engine.complete()
	event = events.wait_one()
	caller.join(2)

	assert returned_early, "speak_segment did not return before the segment completed"
	assert delivered_early == []
	assert errors == []
	assert event.kind is engine.EventKind.SEGMENT_DRAINED
	assert event.segment_id == 23
```

- [ ] **Step 2: Run it**

Run: `python3 -m pytest tests/test_engine_segment_contract.py -q -k test_speak_segment_returns -rx`
Expected: `4 passed, 1 skipped, 21 deselected, 2 xfailed`. The `-rx` summary lists `[VE]` and `[Cerence]` with reasons starting `C3: VE speak_segment blocks until delivery` and `C3: Cerence speak_segment blocks until delivery`.

- [ ] **Step 3: The xfail cases do not hang**

Run: `timeout 60 python3 -m pytest tests/test_engine_segment_contract.py -q`
Expected: `22 passed, 4 skipped, 2 xfailed` well inside 60 s (about 6 s). The VE and Cerence callers stay blocked until `close()` releases the idle hold; the run finishing proves that release works.

- [ ] **Step 4: Show the red behind the xfail**

Run: `python3 -m pytest tests/test_engine_segment_contract.py -q -k test_speak_segment_returns --runxfail 2>&1 | grep -E "^E +AssertionError|passed|failed"`
Expected: two lines `E   AssertionError: speak_segment did not return before the segment completed`, and the summary `2 failed, 4 passed, 1 skipped, 21 deselected`.

- [ ] **Step 5: Style checks and commit**

Run: `ruff format --check tests/test_engine_segment_contract.py && ruff check tests/test_engine_segment_contract.py`
Expected: `1 file already formatted`, `All checks passed!`

```bash
git add tests/test_engine_segment_contract.py
git commit -m "test: pin non-blocking speak_segment; mark VE and Cerence C3 as strict xfail

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Verify with Neural, record the findings, final checks

**Files:**
- Modify: `docs/superpowers/specs/2026-10-01-phase1-engine-segment-contract-design.md` ("實作發現" section, only if this run differs from the prototype)

**Interfaces:**
- Consumes all previous tasks.
- Produces the acceptance evidence.

- [ ] **Step 1: Run the contract with Neural in a temporary worktree**

```bash
W=/workspace/WorldVoice-neural-check
git worktree add --detach "$W" HEAD
ln -s /workspace/WorldVoice/ref "$W/ref"
python3 -c "import zipfile; zipfile.ZipFile('/workspace/WorldVoice/storage/Neural-snapshot-2026-10-01.zip').extractall('$W')"
(cd "$W" && python3 -m pytest tests/test_engine_segment_contract.py -q 2>&1 | tail -1)
(cd "$W" && python3 -m pytest tests -q 2>&1 | tail -1)
(cd "$W" && git status --short)
git worktree remove --force "$W"
```

Expected:
- Contract file: `26 passed, 2 xfailed`, with no skips.
- Full suite: `1351 passed, 9 skipped, 2 xfailed`.
- `git status --short` in the worktree prints nothing, because `driver/Neural/` is gitignored.
- The worktree is removed afterwards.

- [ ] **Step 2: Repeat the contract file five times**

Run: `for i in 1 2 3 4 5; do python3 -m pytest tests/test_engine_segment_contract.py -q 2>&1 | tail -1; done`
Expected: five identical lines, `22 passed, 4 skipped, 2 xfailed`.

- [ ] **Step 3: Full suite and protected paths**

Run: `python3 -m pytest tests -q 2>&1 | tail -1`
Expected: `1255 passed, 96 skipped, 2 xfailed`

Run: `git diff master --stat -- addon/; git ls-files addon/synthDrivers/WorldVoice/driver/Neural`
Expected: no output.

- [ ] **Step 4: Record findings only if they differ**

If Steps 1–3 matched every Expected line, the spec's "實作發現" section is already accurate; change nothing. Otherwise append, in that section, one line per difference giving the engine, the contract item, what happened, and the xfail reason, then commit:

```bash
git add -f docs/superpowers/specs/2026-10-01-phase1-engine-segment-contract-design.md
git commit -m "docs: record phase 1 contract findings

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5: Commit list**

Run: `git log --oneline master..HEAD`
Expected, oldest at the bottom:
1. `docs: add phase 1 engine segment contract design spec`
2. `docs: add phase 1 implementation plan`
3. `test: add engine segment contract harness and completed-segment contract`
4. `test: pin the post-terminate failure contract for every engine`
5. `test: pin the cancelled-token contract for every engine`
6. `test: pin non-blocking speak_segment; mark VE and Cerence C3 as strict xfail`

A seventh `docs: record phase 1 contract findings` commit appears only if Step 4 found a difference.
