# Phase 49: VE and Cerence cancellation without the silence gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** Remove `_SilenceGate` from the VE and Cerence wrappers so that record validity, host admission and native-call admission alone decide whether work is still valid, as in the RHVoice wrapper.

**Architecture:** The inner `_isSilence` Event is left as the plain inner Event and never read or written on the guarded path. The core's `_player` becomes `_WavePlayer`, whose only duty is to send the inner `DoneSpeaking` idle to `_idlePlayer`. The single gate decision record state did not already make (idle with no running record) becomes "no running record → no idle"; an index with no running record is dropped.

**Tech Stack:** Python 3.11+, pytest, ctypes stubs in `tests/worldvoice_cancel_wrapper_harness.py`.

**Spec:** `docs/superpowers/specs/2026-10-28-phase49-vocalizer-cancel-design.md`

## Global Constraints

- Do not modify inner drivers: `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*'` stays empty (plus the other §7 protected paths).
- VE (`driver/VE/__init__.py`) and Cerence (`driver/Cerence/__init__.py`) change identically; `tests/test_vocalizer_drift.py` `ALLOWED` stays `{"_PROFILE", "_ContextualVECallback._process", "SynthDriver._callbackAdmission", "Voice.variants"}`.
- No shared code between `driver/<Engine>/` packages; nothing in `runtime/` changes. RHVoice unchanged.
- Fallback (guard not installed) unchanged, chosen under the same five-field availability check.
- No user-visible change: no audio after cancel, same index/DONE order.
- ruff pinned `0.16.3`; `prek run --all-files` passes; commits `<type>: <summary>` + body, no Co-Authored-By, explicit paths, no `--no-verify`, no push/merge, no `git stash`.
- Tests serial (no xdist installed) with the MemAvailable < 3 GB watchdog; `PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider` for mutation runs, output to a file, per-mutant timeout.
- Baseline at `ea0d197`: 3367 passed, 0 skipped.

## Review Focus

1. A cancel (token and core) arriving while the worker is inside `_beginRecord`, after the validity check — the request must stay silent. Task 2 `test_cancel_while_request_begins_stays_stopped`.
2. Ordinary speech queued behind a request that cancels — its kept `DoneSpeaking` must publish DONE and must not idle the stopped player. Task 2 `test_dropped_request_done_skips_idle_and_reports_done`.
3. A late `ENDPROCESS` with a Sonic tail after core `cancel()` — acknowledged, nothing fed. Task 2 `test_endprocess_after_core_cancel_feeds_nothing`.
4. A request whose token was cancelled before its turn (skipped) — no idle, no DONE. Task 1 `test_done_of_never_spoken_request_skips_idle`.
5. Pause/terminate through the stand-in (inner `pause` and `terminate` reach the real player via `__getattr__`). Existing `test_guard_keeps_original_pause_and_terminate` and the pause/terminate tests in `tests/test_vocalizer_segment_drain.py:1058-1660`, re-run in Task 3.

---

### Task 1: An idle and an index need a running record (D1, D2)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/VE/__init__.py` (`_idlePlayer` `:691-705`, `_onIndexReached` `:803-819`, `_GuardedPlayer.idle` `:139-144`)
- Modify: `addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py` (same methods)
- Test: `tests/test_worldvoice_cancel_wrappers.py`

**Interfaces:**
- Consumes: harness `Token`, `real_player`, `speak_now`, `ready_core`.
- Produces: `_idlePlayer()` returns without idling when `self._currentRecord is None`; `_onIndexReached(index)` drops an index when `self._currentRecord is None`.

- [ ] **Step 1: Write the failing tests**

```python
def test_done_of_never_spoken_request_skips_idle(engine_harness, monkeypatch):
	# token cancelled before speak -> record skipped at _Begin, no core cancel
	...speak_now(core, ["old"], cancellationToken=token)  # token.cancel() first
	assert real_player(core).idles == 0
	assert dones == []

def test_index_without_running_request_is_dropped(engine_harness, monkeypatch):
	core = ready_core(engine_harness)
	core._onIndexReached(5)
	assert indexes == []
```

- [ ] **Step 2: Run, expect FAIL** — `python3 -m pytest -q tests/test_worldvoice_cancel_wrappers.py -k "never_spoken or without_running"`: 4 failed (`idles == 1`; `indexes == [{... 5}]`).
- [ ] **Step 3: Implement** in both wrappers: `_idlePlayer` returns when `record is None` (after the segment check, before the validity check); `_onIndexReached` index branch returns when `record is None or not self._recordValid(record)` (keep the gate check until Task 3); `_GuardedPlayer.idle` returns `None` when the driver is gone.
- [ ] **Step 4: Run, expect PASS** — same command: 4 passed; whole file passes; full suite 3371 passed, 0 skipped.
- [ ] **Step 5: Commit** — `fix: idle and index only for a running VE/Cerence request` (both wrappers + test file).

### Task 2: Pin the cancellation behaviour through real speech (green before and after)

**Files:**
- Test: `tests/test_worldvoice_cancel_wrappers.py`

**Interfaces:**
- Consumes: harness `emit_audio`, `native_call`, `callback_handler`, `native_message`, `Token`.
- Produces: the record-based replacements named in spec §7 that Task 3 relies on when it deletes the gate-pinning tests.

- [ ] **Step 1: Add tests** (each must pass on the current code):
  - `test_core_cancel_during_real_callback_feed_stops_after_feed` — slow real feed; `core.cancel()` from another thread while it blocks; after release `fed == [b"sound"]`, `stops` grew after release (stop after the feed), `idles == 0`.
  - `test_callback_after_core_cancel_feeds_nothing` — native calls `core.cancel()` then sends `OUTBUFREQ`; result `NUAN_E_TTS_USERSTOP`, `fed == []`.
  - `test_cancel_while_request_begins_stays_stopped` — wrap `core._segmentHost.begin` to block (it runs under the wrapper lock after the validity check); `token.cancel()`, `core.cancel()` in a thread, release; `called == []`, `fed == []`.
  - `test_native_call_admission_closes_after_exception` — native raises; afterwards `native_call(core) is None` and an `OUTBUFREQ` callback returns USERSTOP.
  - `test_cancelled_request_drops_index_and_done_notifications` — rewritten in place: request A (live token) emits index 6 → `indexes == [6]`, one DONE; request B: native cancels its token then calls `core._onIndexReached(7)` → still `indexes == [6]`, one DONE.
  - `test_dropped_request_done_skips_idle_and_reports_done` — request 1's native waits; request 2 is queued; release; native calls `core.cancel()`; `dones` has two entries, `idles == 0`, request 2 never reaches native.
  - `test_endprocess_after_core_cancel_feeds_nothing` — Sonic stub with a tail; native emits audio, calls `core.cancel()`, then sends `ENDPROCESS`; returns `NUAN_OK` (legacy acknowledgement), `fed` holds only the pre-cancel audio.
- [ ] **Step 2: Run** — `python3 -m pytest -q tests/test_worldvoice_cancel_wrappers.py`: all pass (new 6 tests × 2 engines). Full suite 3383 passed, 0 skipped.
- [ ] **Step 3: Commit** — `test: pin VE/Cerence cancellation through real speech`.

### Task 3: Remove the silence gate (D0, D3, D4)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/VE/__init__.py`, `addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py`
- Modify: `tests/worldvoice_cancel_wrapper_harness.py` (drop `silence_gate`, `guarded_real_player`, `inside_native_call`; add `inner_stop_flag(owner)`, `stand_in_real_player(player)`)
- Modify: `tests/test_worldvoice_cancel_wrappers.py`, `tests/test_vocalizer_segment_drain.py` (`[clear]` → `[inner-clear]`), `tests/test_naming_layers.py:95`, `:116`

**Interfaces:**
- Consumes: Task 1 record-None rules; Task 2 replacement tests.
- Produces: `class _WavePlayer: __init__(self, player, driver); idle(self); __getattr__(self, name)`; `SynthDriver._realPlayer` unchanged.

- [ ] **Step 1: Write the failing tests**
  - `test_installs_player_stand_in_and_keeps_inner_stop_flag` — `isinstance(player_of(core), module._WavePlayer)`, `stand_in_real_player(player_of(core)) is real_player(core)`, `player_of(callback_handler(core)) is real_player(core)`, `inner_stop_flag(core) is inner_stop_flag(handler)`, `type(...) is threading.Event`, `not ....is_set()`.
  - `test_guarded_speech_never_touches_inner_stop_flag` — install a recording `threading.Event` subclass on core and handler after construction; speak, `core.cancel()`, speak; no `set`/`clear`/`is_set` calls recorded; audio of both requests fed.
  - `test_assignment_failure_falls_back_unchanged` — patch `module.SynthDriver.__setattr__` to raise for a `_WavePlayer` value; `supportsCancellationToken is False`, `player_of(core) is` the original player.
  - `test_missing_private_field_falls_back_without_partial_install` — same parameters, asserts no `_WavePlayer` on core or callback.
  - Delete `test_restoration_failure_raises_instead_of_returning_partial_core`, `test_gate_checks_token_only_during_native_call`, `test_player_stops_after_feed_when_cancelled_mid_feed`, `test_player_skips_feed_when_already_cancelled`, `test_cancel_between_token_check_and_clear_stays_stopped`, `test_native_call_marker_clears_after_exception` (replaced in Task 2, spec §7).
  - `tests/test_vocalizer_segment_drain.py::test_cancelled_idle_cannot_complete_segment`: `"clear"` → `"inner-clear"`, clearing `inner_stop_flag(callback_handler(env.core))`.
- [ ] **Step 2: Run, expect FAIL** — `python3 -m pytest -q tests/test_worldvoice_cancel_wrappers.py -k "stand_in or never_touches or falls_back"`: failures (`module` has no `_WavePlayer`; the gate replaces the Event).
- [ ] **Step 3: Implement** in both wrappers: delete `_SilenceGate`; replace `_GuardedPlayer` by `_WavePlayer` (spec D4, no `feed`); `_installGuard` keeps the availability check and swaps only `self._player` (spec D0, no restoration); drop every gate call listed in spec §3.2 (`_beginRecord` begin/token, `_retireRecord` marker/token, `_runNative` `cancelled()` and marker, `cancel` `set()`, `_onIndexReached` `tokenCancelled()`/`cancelled()`, `_idlePlayer` `cancelled()`, drain `cancelled()`). Remove the `_SilenceGate.is_set` entries from `tests/test_naming_layers.py`. Drop now-unused imports.
- [ ] **Step 4: Run, expect PASS** — the cancel-wrapper, segment-drain, drift, naming, native-strategy-guard files pass; full suite: 3383 − 12 (6 deleted × 2) + 4 (2 new install tests × 2) = 3375 passed, 0 skipped (record the real count in the ledger). `prek run --all-files` Passed; protected-path check empty; `git diff --check` clean.
- [ ] **Step 5: Commit** — `refactor: drop the VE/Cerence silence gate for record validity`.

### Task 4: Mutation proof and final verification

**Files:**
- Scratch only: `<scratchpad>/p49/mutants.py`, results in `.superpowers/sdd/2026-10-28-phase49-vocalizer-cancel/progress.md`.

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: the mutant table for the report.

- [ ] **Step 1:** Script: copy the worktree to scratch (`cp -a`, keep the `ref` symlink), apply one textual mutant at a time to `driver/VE/__init__.py` (spec §8 list), run `tests/test_worldvoice_cancel_wrappers.py tests/test_vocalizer_segment_drain.py tests/test_runtime_legacy_adapter.py -x` with `timeout 300`, output to a file, record killed/survived and the killing test. Then the same for the Cerence wrapper for the mutants that touch Cerence-only text (none expected; one spot-check mutant).
- [ ] **Step 2:** Prove each rewritten/new test of Task 2/3 kills at least one mutant; for a test none kills, add a dedicated mutant or record why.
- [ ] **Step 3:** Full verification (workflow §7): full suite count vs 3367, `prek run --all-files`, `git diff --check`, protected paths, `git ls-files .../driver/Neural` empty. Record line deltas (`git diff --stat master -- driver/VE/__init__.py driver/Cerence/__init__.py`).
- [ ] **Step 4:** If a survivor reveals a missing test, add it (TDD) and commit `test: …`.
