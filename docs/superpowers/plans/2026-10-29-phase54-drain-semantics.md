# Phase 54 Drain Semantics (C3/B10) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** The scheduler keeps the session's pause state and holds segment boundaries while paused, replacing OneCore's and VE/Cerence's own drain unpause waits.

**Architecture:** `TaskManager` (runtime, NVDA-free) records `_paused` and the playback that accepted the last forwarded pause; a completed task does not finish and no task starts while paused; resume is forwarded to the paused engine before the state clears. The two engine drains stop waiting for unpause. C4 option A (decided by the user 2026-10-29, after Tasks 1–5): OneCore's segment drain idles the real player (Tasks 6–7); B9 is dropped.

**Tech Stack:** Python 3 (NVDA add-on), pytest, threading; ruff 0.16.3 via prek.

**Spec:** `docs/superpowers/specs/2026-10-29-phase54-drain-semantics-design.md`

## Global Constraints

- `runtime/` stays NVDA-free (`tests/test_runtime_scheduler.py` `scheduler` fixture forbids NVDA imports).
- Never modify `driver/*/driver/*`, `driver/sonic/`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py`; no Neural.
- Each engine driver stays independently installable; shared code only in `runtime/` / `bridge/`.
- VE and Cerence change identically; `tests/test_vocalizer_drift.py` `ALLOWED` stays `{"_PROFILE", "_ContextualVECallback._process", "SynthDriver._callbackAdmission", "Voice.variants"}`.
- Scheduler lock order stays delivery lock → state condition; no wait while holding `_delivery_lock`.
- A raised forwarded `pause(True)` restores the previous pause state; a raised `pause(False)` keeps the scheduler paused (NVDA's `isPaused` behaves the same, `speech.py:236-240`).
- ruff pinned `0.16.3`; prek hooks run on commit; commits: explicit paths, English `<type>: <summary>` + why-body, no `Co-Authored-By`.
- C4 (Tasks 6–7 only): the drain calls the real player's `idle()` (`player._player.idle()`), never the lease's; the ordinary `_legacyCallback` path is unchanged.
- Readme: one changelog entry in the six readmes; zh_TW 「修正在語言段落交界時暫停，下一段語音仍會繼續播放的問題。」; English "Fixed speech continuing with the next language segment when paused right at a segment boundary."; never edit `addon/doc/en/` or `.html`.

## Review Focus

1. Pause lands after `SEGMENT_DRAINED` was processed but before the next task starts, with the next task on a different engine → next task must not start until resume (Task 1 `test_pause_after_drain_holds_next_engine_until_resume`).
2. Resume must reach the paused engine before a successor on the same engine starts → forwarded `pause(False)` precedes the successor's `speak` (Task 2 `test_resume_reaches_paused_engine_before_successor_starts`).
3. A failing `pause(True)` must not leave speech held forever while NVDA believes it is not paused (Task 1 `test_failed_pause_restores_unpaused_state`).
4. Cancel while a task is held (completion hold or start hold) must release it and clear the pause, so fresh speech plays (Task 1 `test_cancel_releases_completion_hold_and_clears_pause`, Task 2 `test_cancel_releases_start_hold`).
5. The P53 case: the paused task fails, the next request is held, resume clears the failed engine's pause flag (Task 2 `test_failed_paused_task_holds_next_request_and_resume_reaches_failed_engine`).

---

### Task 1: Scheduler pause state and completion hold

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/runtime/scheduler.py:169-188` (state), `:428-441` (`cancel`), `:454-465` (`pause_current`), `:522-565` (`_execute`)
- Test: `tests/test_runtime_scheduler.py`

**Interfaces:**
- Consumes: existing `TaskManager`, `FakePlayback(completion=...)` (`tests/runtime_harness.py:162`).
- Produces: `TaskManager._paused: bool`, `TaskManager._pause_target: PlaybackPort | None`; `pause_current(switch: bool) -> None` (new semantics, spec §2); helper `_pausable_playback_locked() -> PlaybackPort | None` (today's forwarding rule plus "completion not ready").

- [ ] **Step 1: Write the failing tests** (DRAIN-contract helper: `FakePlayback(completion=CompletionContract(CompletionMode.DRAIN, IndexRange(...)))`; drain via `manager.on_event(PlaybackEvent(SEGMENT_DRAINED, port.source_id, segment_id=port.contexts[-1].segment_id))`)
  - `test_pause_after_drain_holds_next_engine_until_resume`: request with segment on `first` then on `second`; drain `first`, then `pause_current(True)`: the first task's future stays undone and `second.entered` stays unset (`stays_unset`); `first.paused == []` (a completed task is not forwarded); `pause_current(False)` → `second.entered` set, then drain `second` → `output.wait_done() == 1`.
  - `test_pause_during_segment_is_forwarded_and_resume_returns_to_it`: pause while `port` is AWAITING → `port.paused == [True]`; drain; future not done; resume → `port.paused == [True, False]`, future result `True`.
  - `test_failed_pause_restores_unpaused_state`: `port.pause` raises on `True` → `pause_current(True)` raises; then drain → future completes (not held).
  - `test_failed_resume_keeps_the_pause`: pause forwarded, then `port.pause` raises on `False` → `pause_current(False)` raises; drain → future stays undone (`stays_unset` on a done Event); `manager.cancel()` → future cancelled.
  - `test_cancel_releases_completion_hold_and_clears_pause`: pause, drain (held), `manager.cancel([port])` → future cancelled; a new speech request on `port` starts (`entered`) and completes.
  - `test_cancelled_future_releases_completion_hold`: pause, drain (held), `future.cancel()` → worker moves on (next task's port `entered`).
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_runtime_scheduler.py -k "pause or hold"` — Expected: the new tests FAIL (held tests: next task starts; failure tests: no restore).
- [ ] **Step 3: Implement** in `scheduler.py`: init `_paused = False`, `_pause_target = None`; `cancel()` clears both under the state lock; `pause_current` per spec §2 (pause: set state, forward via `_pausable_playback_locked()`, restore previous `(paused, target)` on exception; resume: forward to `_pause_target` or `_pausable_playback_locked()`, then clear and `notify_all`; closed → no-op); `_execute`: after `done.wait()`, `with self._state_cond: while self._paused and self._valid_locked(task): self._state_cond.wait()`; the Future done-callback also notifies `_state_cond` when cancelled.
- [ ] **Step 4: Run** the same command → PASS; full suite `python3 -m pytest -q tests` → 3617 + 6 = 3623 passed, 0 skipped (adjust `test_pause_current_uses_valid_playback` only if it fails here; it is rewritten in Task 2).
- [ ] **Step 5: Commit** `scheduler.py`, `tests/test_runtime_scheduler.py`: `fix: hold a drained segment while speech is paused`.

### Task 2: Start hold and resume forwarding to the paused engine

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/runtime/scheduler.py:505-520` (`_acquire`)
- Test: `tests/test_runtime_scheduler.py` (rewrite `test_pause_current_uses_valid_playback`, `:477-484`)

**Interfaces:**
- Consumes: Task 1 `_paused`, `_pause_target`, `pause_current`.
- Produces: `_acquire` waits while `self._stops_in_flight or (self._paused and self._valid_locked(task))`.

- [ ] **Step 1: Write the failing tests**
  - `test_pause_without_current_task_holds_next_task`: `pause_current(True)` with no task → submitting speech does not enter `port` (`stays_unset(port.entered)`); `port.paused == []`; resume → `port.entered` set.
  - `test_pause_during_break_holds_following_speech`: request = break(60, controlled `token.wait`) + speech; pause during the break; release the break → speech not entered; resume → entered.
  - `test_resume_reaches_paused_engine_before_successor_starts`: segment on `port` then on `port`; pause forwarded while first AWAITING; drain first; resume; the recorded order of `port.paused[-1] is False` precedes the second `speak` (record a shared call log in `port.pause`/`on_speak`).
  - `test_cancel_releases_start_hold`: pause with no task; submit speech (held); `manager.cancel()` → held request's future cancelled; new request speaks.
  - `test_failed_paused_task_holds_next_request_and_resume_reaches_failed_engine`: pause forwarded to `port` (AWAITING); emit `SEGMENT_FAILED` for its segment and submit a second request on `other`: while paused the second is not entered (the failure is reported only after resume); resume → `port.paused == [True, False]`, first future raises, `other.entered` set.
  - Rewrite `test_pause_current_uses_valid_playback` → `test_pause_forwarding_follows_the_current_segment`: pause with no task → no forward; resume; speech; pause/resume forwarded `[True, False]`; after `cancel([port])`, pause → not forwarded and `manager.pause_current(False)` restores.
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_runtime_scheduler.py` → the new start-hold tests FAIL (task starts while paused).
- [ ] **Step 3: Implement** the `_acquire` wait condition.
- [ ] **Step 4: Run** → PASS; full suite → 3623 + 5 = 3628 passed, 0 skipped (the rewrite replaces one test).
- [ ] **Step 5: Commit**: `fix: start no speech task while the session is paused`.

### Task 3: OneCore segment drain stops waiting for unpause

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py:191-211`
- Test: `tests/test_onecore_segment_drain.py:882-894`, `:1008-1036`

**Interfaces:**
- Consumes: Task 1/2 (the scheduler now owns the hold).
- Produces: `_OneCoreStrategy.drain` = `sync()` then `PLAYED_OUT`; failure path unchanged.

- [ ] **Step 1: Rewrite the tests**: `test_pause_holds_completion_until_resume` → `test_segment_drain_does_not_wait_for_resume` (pause, release sync, respond → `SEGMENT_DRAINED` arrives while still paused; then `pause(False)`); `test_pause_resume_reaches_real_player_before_success_event` → `test_drain_reports_while_a_resume_is_in_flight` (blocking resume does not hold the event).
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_onecore_segment_drain.py` → the two rewritten tests FAIL.
- [ ] **Step 3: Implement**: remove the `_segmentPaused` wait (`OneCore:197-200`); keep the `sync()` comment.
- [ ] **Step 4: Run** → PASS; full suite → 3628 passed, 0 skipped.
- [ ] **Step 5: Commit**: `refactor: leave OneCore's pause at segment ends to the scheduler`.

### Task 4: VE/Cerence segment drain stops waiting for unpause

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/VE/__init__.py:347-368`, `addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py:347-368` (identical edit)
- Test: `tests/test_vocalizer_segment_drain.py:1106-1116`, `:1390-1424` (and any test that pins the drain wait)

**Interfaces:**
- Consumes: Tasks 1/2.
- Produces: `_VEStrategy.drain` = `_realPlayer.idle()` then `PLAYED_OUT` while the record is valid; failure path unchanged.

- [ ] **Step 1: Rewrite the tests**: `test_pause_holds_completion_after_real_idle` → `test_segment_drain_does_not_wait_for_resume` (the speech call finishes while paused, one event); `test_segment_drain_waits_for_real_resume_return` → `test_segment_drain_does_not_wait_for_an_inflight_resume`. Both run for VE and Cerence through the existing `env` parametrization.
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_vocalizer_segment_drain.py` → rewritten tests FAIL.
- [ ] **Step 3: Implement**: remove the wait block (`VE:352-357`, `Cerence:352-357`).
- [ ] **Step 4: Run** → PASS; `python3 -m pytest -q tests/test_vocalizer_drift.py` PASS; full suite → 3628 passed, 0 skipped.
- [ ] **Step 5: Commit**: `refactor: leave VE and Cerence pause at segment ends to the scheduler`.

### Task 5: Barrier documentation and changelog

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/runtime/barriers.py:30-37`; `readme.md`; `addon/doc/{ru,uk,zh_CN,zh_HK,zh_TW}/readme.md` (next-version changelog)

- [ ] **Step 1:** `PLAYED_OUT` comment: proven by `idle()` returning, or OneCore's `sync()` returning; a pause after that is held by the scheduler, not the engine; keep the existing OneCore continuous-segment sentence.
- [ ] **Step 2:** Add the Global Constraints changelog entry to each readme's next-version section (ru/uk/zh_CN/zh_HK in their language, matching the neighbouring entries).
- [ ] **Step 3: Run** full suite → 3628 passed, 0 skipped; `prek run --all-files` all Passed; `git diff --check` clean; protected-path commands print nothing.
- [ ] **Step 4: Commit**: `docs: record the scheduler pause hold at segment ends`.

### Task 6: OneCore segment drain idles the real player (C4 option A)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py` (`_OneCoreStrategy.drain`)
- Modify: `tests/onecore_drain_harness.py` (`Player`: `idles` counter; error mode `"idle"` raises `OSError("idle failed")` after the sync wait)
- Test: `tests/test_onecore_segment_drain.py`

**Interfaces:**
- Consumes: `_OneCorePlayer` (`LeasedPlayer`, real player in `._player`).
- Produces: `_OneCoreStrategy.drain(host, record)` calls `player._player.idle()`; failure path as before.

- [ ] **Step 1: Write the failing tests**
  - `test_segment_drain_idles_the_real_player`: speak, release sync, respond → `[SEGMENT_DRAINED]` and `env.player.idles == 1`.
  - `test_idle_failure_fails_only_its_segment`: `env.player.error = "idle"` → `[SEGMENT_FAILED]` with `str(error) == "idle failed"`, `env.player.stops >= 1`, `control_error is None`; a successor drains.
  - Extend `test_legacy_speak_still_uses_parent_interface`: `env.player.idles == 1` (ordinary queue-empty idle unchanged).
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_onecore_segment_drain.py` → the two new tests FAIL (`idles == 0`; no idle error). Red proofs in scratch: the same tests also fail with the drain calling the lease's `player.idle()`.
- [ ] **Step 3: Implement**: replace `player.sync()` by `player._player.idle()` with a comment why the lease is bypassed.
- [ ] **Step 4: Run** → PASS; full suite → 3630 passed, 0 skipped.
- [ ] **Step 5: Commit**: `fix: idle OneCore's real player at the end of each segment`.

### Task 7: C4 documentation and changelog

**Files:** `addon/synthDrivers/WorldVoice/runtime/barriers.py`; spec corrections (strikethrough + "Corrected by `phase54-drain-semantics`") in `docs/superpowers/specs/2026-10-02-phase3c-onecore-design.md:93`, `docs/superpowers/specs/2026-10-28-phase52-shared-barriers-design.md:85`, `:129`, `:140`; the six readmes.

- [ ] **Step 1:** `PLAYED_OUT` comment: every segment drain ends with `idle()`, which also closes the continuous segment; OneCore's ordinary speech idles once its queue empties.
- [ ] **Step 2:** Spec corrections (keep old text struck through).
- [ ] **Step 3:** Readme entry per spec §3.6 in all six readmes.
- [ ] **Step 4:** Full §7 verification: 3630 passed / 0 skipped, prek Passed, `git diff --check` clean, protected paths empty.
- [ ] **Step 5: Commit**: `docs: record OneCore's per-segment idle`.
