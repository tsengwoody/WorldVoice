# Phase 9c RHVoice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- Route RHVoice's name-mangled inner access through one port.
- Make its player proxy a `LeasedPlayer` subclass.
- Replace its cancel counter with `StopGate`.
- Fix D10: a dead owner inside a ctypes callback.
- Require keyword arguments for drain support.

**Architecture:**
- `LeasedPlayer` gains `_feed_admitted`.
- The RHVoice wrapper gains `_RHVoiceInner`.
- `_WavePlayer(LeasedPlayer)` overrides only record selection, its callback and idle.

**Tech Stack:** Python 3.11; pytest; ruff format (tabs).

**Spec:** `docs/superpowers/specs/2026-10-04-phase9c-rhvoice-design.md`

## Global Constraints

- Never edit `driver/<Engine>/driver/` (here: `driver/RHVoice/driver/`) or `driver/sonic`.
- No shared code between engine packages.
- `addon/` ruff-format clean; new tests use tabs.
- `git add` explicit paths; never stage the `docs/superpowers/finish_task.md` deletion or `refactor.md`.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Full suite: `python3 -m pytest tests -q` (baseline 1502).

## Review Focus

1. **The inner `__init__` assigns its four callbacks** before `super().__init__()` returns. `__setattr__` must work then; it uses only class constants. Covered by every RHVoice test that loads the driver.
2. **An index callback released by the worker's final idle** after `host.close(record)`: it must still be admitted (`audio=True`). Existing RHVoice drain tests cover it; name them in the ledger.
3. **`cancel()` from a bound native callback** (re-entrant cancel): `StopGate.hold()` takes `_segmentCondition`. That condition is RLock-based (`Condition(RLock())`), so re-entry from the same thread is safe. Existing re-entrant tests cover it; name them.
4. **The driver collected while the C library still calls back** (D10): return the refusal value. Test in Task 2.
5. **`terminate()` writes `tts_engine = None`** through the port: the inner attribute is set, and `terminate` stays idempotent. Existing terminate tests cover it.

---

### Task 1: `LeasedPlayer._feed_admitted`

**Files:** `addon/synthDrivers/WorldVoice/runtime/segmentHost.py`, `tests/test_segment_host.py`

- [ ] **Step 1: Failing test** (append):

```python
def test_feed_admitted_serves_subclasses_that_choose_their_record(env):
	class Raw:
		def __init__(self):
			self.fed = []

		def feed(self, data, size=None, onDone=None):
			self.fed.append((data, size))

		def stop(self):
			pass

	class Bound(env.module.LeasedPlayer):
		def feed(self, data, onDone=None):
			record = self._host.current()
			with self._host.consumer(record) as admitted:
				if admitted is None:
					return None
				return self._feed_admitted(admitted, data, None, onDone)

	raw = Raw()
	player = Bound(env.host, raw)
	_, _, events = env.speak()
	record = env.strategy.wait_submitted()
	env.host.begin(record)
	player.feed(b"pcm")
	assert raw.fed == [(b"pcm", None)]
	env.run_native(record)
	events.wait_one()
```

- [ ] **Step 2: Run** `python3 -m pytest tests/test_segment_host.py -q -k feed_admitted` → FAIL (`_feed_admitted` missing).
- [ ] **Step 3: Implement** per spec §`LeasedPlayer._feed_admitted`, moving the existing try/except/finally body unchanged.
- [ ] **Step 4: Run** the `segment_host`, `espeak`, `sapi5` test files, then the full suite → green.
- [ ] **Step 5: Commit** `refactor(runtime): split LeasedPlayer's admitted feed from record selection`.

---

### Task 2: RHVoice port, player, stop gate, D10, signature

**Files:** `addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py`, `tests/test_rhvoice_segment_drain.py`, `tests/test_native_strategy_guards.py`

- [ ] **Step 1: Failing tests**

Append to `tests/test_native_strategy_guards.py`:

```python
INNER_RHVOICE = ROOT / "driver/RHVoice/driver/__init__.py"


def test_rhvoice_reaches_inner_privates_only_through_its_port():
	source = (ROOT / "driver/RHVoice/__init__.py").read_text(encoding="utf-8")
	tree = ast.parse(source)
	port = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "_RHVoiceInner")
	port_source = ast.get_source_segment(source, port)
	assert "_SynthDriver__" not in source.replace(port_source, "")
	inner = INNER_RHVOICE.read_text(encoding="utf-8")
	for name in set(re.findall(r"_SynthDriver__(\w+)", port_source)):
		assert re.search(rf"self\.__{name}\b", inner), name


def test_rhvoice_uses_shared_player_and_stop_gate():
	source = (ROOT / "driver/RHVoice/__init__.py").read_text(encoding="utf-8")
	assert "_segmentCancelling" not in source
	tree = ast.parse(source)
	player = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "_WavePlayer")
	assert [ast.unparse(base) for base in player.bases] == ["LeasedPlayer"]
```

Turn the existing `test_espeak_drain_support_requires_keywords` into a parametrized `test_drain_support_requires_keywords(engine)` over `["Espeak", "RHVoice"]`, and add `import re` to the module imports.

Append to `tests/test_rhvoice_segment_drain.py` (match the file's fixture and loader names):

```python
def test_native_callback_after_owner_collection_refuses(env):
	module = sys.modules[type(env.driver).__module__]

	class Gone:
		pass

	owner = Gone()
	calls = []
	done = module._NativeCallback(owner, lambda *args: calls.append(args), True)
	speech = module._NativeCallback(owner, lambda *args: calls.append(args), False)
	del owner
	gc.collect()
	assert done(1, 2, 7) is None
	assert speech(1, 2, 7) == 0
	assert calls == []
```

Add `import gc` (and `import sys` if missing).

- [ ] **Step 2: Run** the guard and RHVoice tests → FAIL (no `_RHVoiceInner`; `_WavePlayer` base; `AttributeError: 'NoneType' object has no attribute '_native_callback'`).

- [ ] **Step 3: Implement** in `driver/RHVoice/__init__.py`.

Imports:
- `from ...runtime.engineControl import StopGate`;
- `from ...runtime.segmentHost import LeasedPlayer, NativeStrategy, SegmentHost`;
- `from ...runtime.playbackWork import DrainProfile, DrainSupport, runtime_profile, unverified_drain_support`.

Port (place first after `_RHVoiceMessage`):

```python
class _RHVoiceInner:
	"""The vendored RHVoice SynthDriver's name-mangled state this wrapper uses.

	The inner driver stays unmodified; every access to its private names goes
	through here, so an update of the vendored driver is checked in one place.
	"""

	CALLBACK_NAMES = frozenset(
		{
			"_SynthDriver__sample_rate_callback",
			"_SynthDriver__speech_callback",
			"_SynthDriver__mark_callback",
			"_SynthDriver__done_callback",
		},
	)
	DONE_CALLBACK = "_SynthDriver__done_callback"

	def __init__(self, driver):
		self._driver = weakref.ref(driver)

	@property
	def player(self):
		return self._driver()._SynthDriver__player

	@property
	def lib(self):
		return self._driver()._SynthDriver__lib

	@property
	def tts_engine(self):
		return self._driver()._SynthDriver__tts_engine

	@tts_engine.setter
	def tts_engine(self, value):
		self._driver()._SynthDriver__tts_engine = value

	@property
	def tts_queue(self):
		return self._driver()._SynthDriver__tts_queue

	@property
	def tts_thread(self):
		return self._driver()._SynthDriver__tts_thread

	@property
	def cancel_flag(self):
		return self._driver()._SynthDriver__cancel_flag

	@property
	def profile(self):
		return self._driver()._SynthDriver__profile

	@property
	def rate(self):
		return self._driver()._SynthDriver__rate

	@property
	def pitch(self):
		return self._driver()._SynthDriver__pitch

	@property
	def volume(self):
		return self._driver()._SynthDriver__volume

	@property
	def rate_boost(self):
		return self._driver()._SynthDriver__rate_boost
```

`_NativeCallback.__call__`:

```python
	def __call__(self, *args):
		owner = self._owner()
		if owner is None:
			# The C library may call back after the driver was collected.
			return None if self._is_done else 0
		return owner._native_callback(self._callback, self._is_done, *args)
```

`_NativeLibrary(host, native, record)`: replace `self._owner = weakref.ref(owner)` with `self._host = host`. Every `self._owner()._segmentHost` becomes `self._host`. Construct it in `submit` with `_NativeLibrary(host, driver._inner.lib, record)`.

`_WavePlayer`:

```python
class _WavePlayer(LeasedPlayer):
	"""Keep a queued index callback tied to its originating native message."""

	def __init__(self, host, player):
		super().__init__(host, player, idle_barrier=None)

	def feed(self, data, onDone=None):
		host = self._host
		bound = host.callback_record()
		if bound is None:
			return None
		with host.consumer(bound) as record:
			if record is None:
				return None
			return self._feed_admitted(record, data, None, onDone)

	def _callback(self, record, onDone):
		host = self._host

		def index_done():
			# The worker's final idle may release this after the native gate closes.
			with host.consumer(record, audio=True) as admitted:
				if admitted is None:
					return
				with host.bound_callback(record):
					try:
						onDone()
					except Exception as error:
						host.record_error(record, error)

		return index_done

	def idle(self):
		host = self._host
		record = host.callback_record()
		try:
			return self._player.idle()
		except Exception as error:
			host.record_error(record, error)
			raise
```

In `SynthDriver.__init__`, `get_player` wraps with `_WavePlayer(self._segmentHost, real)`.

`_QueuedSpeech`:
- wait predicate `lambda: record.closed or owner._stopGate.clear`;
- `owner._SynthDriver__player.idle()` becomes `owner._inner.player.idle()`;
- `owner._SynthDriver__cancel_flag.clear()` becomes `owner._inner.cancel_flag.clear()`.

Strategy:
- every `driver._SynthDriver__X` becomes `driver._inner.X` (player, lib, tts_engine, cancel_flag, profile, rate, pitch, volume, rate_boost, tts_queue);
- `_NativeLibrary(host, driver._inner.lib, record)`.

`SynthDriver`:

```python
	def __init__(self):
		self._segmentHost = SegmentHost("RHVoice", _RHVoiceStrategy(self))
		self._segmentCondition = Condition(RLock())
		self._stopGate = StopGate(self._segmentCondition)
		self._segmentById = {}
		self._segmentNextId = 1
		self._inner = _RHVoiceInner(self)
		super().__init__()
		player = self._inner.player
		...  # get_player wrapping as before, with _WavePlayer(self._segmentHost, real)

	def __setattr__(self, name, value):
		# Inner init creates C callbacks just after assigning Python callables.
		if name in _RHVoiceInner.CALLBACK_NAMES:
			value = _NativeCallback(self, value, name == _RHVoiceInner.DONE_CALLBACK)
		super().__setattr__(name, value)

	def get_segment_drain_support(self, *, nvda_version: str, audio_mode: str) -> DrainSupport:
		...

	def cancel(self):
		host = self._segmentHost
		with self._stopGate.hold():
			with host.admission():
				host.cancel()
				with self._segmentCondition:
					current = host.current()
					dropped = [record for record in self._segmentById.values() if record is not current]
					for record in dropped:
						self._segmentById.pop(record.native.identity, None)
				# Queued records never reach the worker; the inner cancel clears them.
				for record in dropped:
					host.abandon(record)
				error = None
				try:
					super().cancel()
				except Exception as exc:
					host.latch_control_error(exc)
					error = exc
			host.wait_settled(current)
			try:
				self._inner.player.stop()
			except Exception as exc:
				host.latch_control_error(exc)
				if error is None:
					error = exc
		if error is not None:
			raise error
```

In `terminate`, replace each `self._SynthDriver__X` with `self._inner.X`, including `self._inner.tts_engine = None`.

Ordering check: `self._segmentCondition` and `_stopGate` must exist before `super().__init__()` (the inner init may start the worker), and `_inner` before the first `__setattr__` of a callback name. `__setattr__` uses only class constants, but `_NativeCallback(self, …)` needs nothing else.

- [ ] **Step 4: Run**
- `python3 -m pytest tests/test_rhvoice_segment_drain.py tests/test_native_strategy_guards.py tests/test_engine_segment_contract.py -q` → PASS.
- Loop the RHVoice file 20×.
- Full suite → green.
- [ ] **Step 5: Commit** `refactor(rhvoice): reach the inner driver through a port and share the player lease and stop gate`.

Final verification:

```bash
python3 -m pytest tests -q
ruff check addon --exclude 'addon/synthDrivers/WorldVoice/driver/*/driver' --exclude 'addon/synthDrivers/WorldVoice/driver/sonic' --select F401,F821
ruff format --check addon
git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver' addon/synthDrivers/WorldVoice/driver/sonic
```
