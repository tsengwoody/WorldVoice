# Phase 50: VE and Cerence without the guard fallback — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** Remove the VE/Cerence "guard not installed → original inner driver" path so both wrappers install unconditionally, like OneCore, SAPI5, RHVoice and eSpeak.

**Architecture:** `_installGuard` becomes two plain assignments with no check and no `except`, so a failure propagates out of `SynthDriver.__init__` (`createCore` raises, the voice manager logs and skips the engine). `_guardInstalled` and the fifteen sites that read or write it go; `supportsCancellationToken` becomes the class constant `True`; drain support always returns the unverified-enabled answer.

**Tech Stack:** Python 3.11+, pytest, AST checks, ctypes stubs in `tests/worldvoice_cancel_wrapper_harness.py`.

**Spec:** `docs/superpowers/specs/2026-10-28-phase50-vocalizer-no-fallback-design.md`

## Global Constraints

- No behaviour change on the guarded path; existing guarded-path tests pass unchanged.
- Do not modify inner drivers: `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*'` (and the other §7 protected paths) stays empty.
- VE and Cerence change identically; `tests/test_vocalizer_drift.py` `ALLOWED` stays `{"_PROFILE", "_ContextualVECallback._process", "SynthDriver._callbackAdmission", "Voice.variants"}`.
- Drivers stay independently installable: no import between `driver/<Engine>/` packages; `runtime/` and `bridge/` unchanged.
- ruff pinned `0.16.3`; `prek run --all-files` passes; commits `<type>: <summary>` + body, no Co-Authored-By, explicit paths, no `--no-verify`, no push/merge, no `git stash`.
- Tests serial with the MemAvailable < 3 GB watchdog; mutation runs on a scratch copy with `PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider`, `__pycache__` cleared, output to a file, per-run timeout.
- Baseline at `0c3aaa7`: 3379 passed, 0 skipped.

## Review Focus

1. Ordinary speech with a token through the PLAIN entry: the bridge must still pass `cancellationToken` to VE/Cerence once the property becomes a class attribute (`getattr` on the instance). Task 2: `test_installs_player_stand_in_and_keeps_inner_stop_flag` (`core.supportsCancellationToken is True`) and existing `tests/test_runtime_legacy_adapter.py`/request-builder tests; Task 2 adds the class-constant assertion to the structural test.
2. Install failure after `_initializeNative`: must raise from the constructor, not leave a half-installed core (old: warning + original driver). Task 1 `test_install_failure_raises_from_the_constructor`.
3. Drain support with WASAPI and legacy audio: always `supported` with "unverified" in the reason. Existing `test_guarded_native_profiles_are_enabled_with_unverified_evidence`, re-run in Task 2.
4. Callback for an instance outside any native call (late or foreign native callback): still `USERSTOP`, nothing fed, now without the inner-callback branch. Existing `test_callback_rejects_audio_outside_native_call`, re-run in Task 2.
5. Terminate and pause through the stand-in after the branches go: the inner `pause`/`terminate` still reach the real player. Existing pause/terminate tests in `tests/test_vocalizer_segment_drain.py` and `tests/test_worldvoice_cancel_wrappers.py`, re-run in Task 2.

---

### Task 1: The install has no check and raises on failure (D1)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/VE/__init__.py:407-430` (`_installGuard`)
- Modify: `addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py:409-432` (same)
- Modify: `tests/test_worldvoice_cancel_wrappers.py:76-145`
- Modify: `tests/worldvoice_cancel_wrapper_harness.py:235-262` (`new_core`)

**Interfaces:**
- Consumes: nothing.
- Produces: `SynthDriver._installGuard(self) -> None` with no check/except (still sets `_guardInstalled = True` until Task 2); harness `new_core() -> SynthDriver` with no parameters.

- [ ] **Step 1: Rewrite the assignment-failure test and delete the fallback tests**

Replace `test_assignment_failure_falls_back_unchanged` with:

```python
def test_install_failure_raises_from_the_constructor(engine_harness, monkeypatch):
	# Same injected failure on `_player = _IdleRoutingPlayer(...)` as before.
	...
	with pytest.raises(RuntimeError, match="injected install failure"):
		engine_harness.new_core()
```

Delete `test_missing_private_field_falls_back_without_partial_install` (and its parametrize), `test_missing_callback_falls_back_without_partial_install`, `test_fallback_delegates_each_original_method` (and its parametrize).

- [ ] **Step 2: Run to verify red**

Run: `python3 -m pytest -p no:cacheprovider tests/test_worldvoice_cancel_wrappers.py -k install_failure -q`
Expected: 2 failed (`DID NOT RAISE`), VE and Cerence.

- [ ] **Step 3: Simplify `_installGuard` in both wrappers**

Body per spec D1 (`self._realPlayer = self._player`; `self._player = _IdleRoutingPlayer(self._realPlayer, self)`), keep the existing two-line comment, then `self._guardInstalled = True` (removed in Task 2). Drop `new_core`'s `missing`/`callback_proxy` parameters and the custom-init branch: `new_core()` returns `wrapped.SynthDriver()`.

- [ ] **Step 4: Run to verify green**

Run: `python3 -m pytest -p no:cacheprovider tests/test_worldvoice_cancel_wrappers.py tests/test_vocalizer_drift.py tests/test_native_strategy_guards.py -q`
Expected: all pass. Full suite (watchdog command): 3359 passed, 0 skipped (3379 − 20 deleted fallback items).

- [ ] **Step 5: Commit**

```bash
git add addon/synthDrivers/WorldVoice/driver/VE/__init__.py addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py tests/test_worldvoice_cancel_wrappers.py tests/worldvoice_cancel_wrapper_harness.py
git commit -m "refactor: install the VE/Cerence guard without a check"
```

### Task 2: Remove the fallback flag and every branch (D2, D3, D4)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/VE/__init__.py` (spec §3 rows 1, 4-15)
- Modify: `addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py` (same rows, Cerence lines in spec §3)
- Test: `tests/test_native_strategy_guards.py`

**Interfaces:**
- Consumes: Task 1's `_installGuard`.
- Produces: `SynthDriver.supportsCancellationToken = True` (class attribute); `get_segment_drain_support(...) -> DrainSupport` always `unverified_drain_support(_PROFILE, "SDK callback quiescence and physical playback are")`.

- [ ] **Step 1: Write the structural test**

```python
@pytest.mark.parametrize("engine", ["VE", "Cerence"])
def test_vocalizer_wrapper_has_no_guard_fallback(engine):
	source = (ROOT / "driver" / engine / "__init__.py").read_text(encoding="utf-8")
	tree = ast.parse(source)
	assert "_guardInstalled" not in {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
	synth = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SynthDriver")
	assert any(
		isinstance(item, ast.Assign)
		and [ast.unparse(t) for t in item.targets] == ["supportsCancellationToken"]
		and isinstance(item.value, ast.Constant) and item.value.value is True
		for item in synth.body
	)
```

- [ ] **Step 2: Run to verify red**

Run: `python3 -m pytest -p no:cacheprovider tests/test_native_strategy_guards.py -k no_guard_fallback -q`
Expected: 2 failed (`_guardInstalled` found).

- [ ] **Step 3: Remove the flag and branches in both wrappers**

Delete `self._guardInstalled = False` and `= True`, the `if not …_guardInstalled:` lines with their `return` in `_ContextualVECallback.__call__`, `_VEStrategy.admission_error` (`_CerenceStrategy` in Cerence), `speak`, `_speak`, `getParameters`, `cancel`, `_onIndexReached`, `pause`, `terminate`, and the unavailable branch of `get_segment_drain_support`. Replace the `supportsCancellationToken` property with the class attribute (place it at the top of the `SynthDriver` body). Keep VE and Cerence identical.

- [ ] **Step 4: Run to verify green**

Run: `python3 -m pytest -p no:cacheprovider tests/test_native_strategy_guards.py tests/test_vocalizer_drift.py tests/test_worldvoice_cancel_wrappers.py tests/test_vocalizer_segment_drain.py tests/test_runtime_legacy_adapter.py tests/test_runtime_drain_integration.py -q`
Expected: all pass. `grep -n _guardInstalled addon/ tests/ -r` → no output. Full suite (watchdog command): 3361 passed, 0 skipped.

- [ ] **Step 5: Commit**

```bash
git add addon/synthDrivers/WorldVoice/driver/VE/__init__.py addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py tests/test_native_strategy_guards.py
git commit -m "refactor: drop the VE/Cerence guard-not-installed fallback"
```

### Task 3: Verify, mutate, record

**Files:**
- Modify: `docs/superpowers/specs/2026-10-28-phase50-vocalizer-no-fallback-design.md` (append "## 8. Implementation notes")

**Interfaces:**
- Consumes: Tasks 1-2.
- Produces: verification and mutation record.

- [ ] **Step 1: Full verification (§7)**

Full suite with the watchdog: 3361 passed, 0 skipped. `prek run --all-files`: all Passed. `git diff --check master`: no output. Protected paths (`git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py addon/synthDrivers/WorldVoice/unicodeScripts/unspaced_common_data.py`; `git ls-files addon/synthDrivers/WorldVoice/driver/Neural`): no output. `git diff --stat master` line delta per wrapper.

- [ ] **Step 2: Mutation runs (spec §6, 4 mutants × 2 wrappers)**

On a scratch copy (`cp -a` of the worktree without `.git`, `ref` symlink kept), each mutant applied by a script, `PYTHONDONTWRITEBYTECODE=1 timeout 600 python3 -m pytest -p no:cacheprovider -x -q <the four spec §6 test files>`, output to a file. Expected: all 8 killed.

- [ ] **Step 3: Record and commit**

Append mutation results, line delta and test count to the spec; `git add -f` the spec; commit `docs: record the phase 50 implementation notes`.
