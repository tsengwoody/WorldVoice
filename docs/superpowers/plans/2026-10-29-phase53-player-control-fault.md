# Phase 53: player and control-fault unification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** Every engine feeds and stops its player through a `LeasedPlayer`, every queue-owning wrapper latches only through its `ControlFaultPolicy`, and one written latch rule decides which failures latch.

**Architecture:** `ControlFaultPolicy` (core, `runtime/engineControl.py`) gains a two-phase `capture`/`deliver`, an `after` hook and a per-thread `deferred()` block, so OneCore's private capture/deliver copy becomes policy configuration. OneCore wraps every player it holds (a `_player` property) in `_OneCorePlayer(LeasedPlayer)`; VE/Cerence feed and stop through `_CallbackPlayer(LeasedPlayer)`; RHVoice's `_WavePlayer` reports stop failures to its policy. Drain, open and replacement failures become record-only failures followed by a stop.

**Tech Stack:** Python 3.11+, pytest, `ast` guards, ruff 0.16.3 via prek, mutmut 3.8.0 on a scratch copy.

**Spec:** `docs/superpowers/specs/2026-10-29-phase53-player-control-fault-design.md`

## Global Constraints

- Latch rule (spec §3.1), verbatim intent: control failures (stop, purge, pause/resume, inner cancel, native release, unproven callback quiescence) latch; progress failures (open/replace player, feed, `idle()`/`sync()`, native synthesis, callback processing) are recorded on their record and followed by a stop that resets the player; a failed stop latches. Exception: SAPI5 ordinary request failure latches (`SAPI5:646-650`).
- No change to correct-run behaviour, barrier sets, reach points, drain semantics (`idle` vs `sync`, pause waits), boilerplate (P45′), readme.
- SAPI5 and eSpeak code unchanged.
- No wrapper calls `host.latch_control_error`; eSpeak latches only through `LeasedPlayer`'s default `_stop_failed`.
- OneCore lock order pause lock → `_segmentCondition` → host condition; nothing is delivered (abandon, `DONE`, after-hook) under the pause lock.
- VE and Cerence changed identically; `tests/test_vocalizer_drift.py` `ALLOWED` unchanged; `_VEPort`/`_CerencePort` lists unchanged unless the guard demands it (record a `Ruling:`).
- Never modify `driver/*/driver/*`, `driver/sonic/`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py`; no Neural; no wrapper imports another driver package; shared code only in `runtime/`/`bridge/`.
- ruff pinned `0.16.3`; `prek` passes on every commit (restage and recommit if a hook rewrites; never `--no-verify`).
- git: explicit paths, `git diff --cached --stat` before each commit, `<type>: <summary>` + why-body, no `Co-Authored-By`, no push, no `git stash`, never touch `/workspace/WorldVoice`.
- Tests serial (no xdist) with the watchdog: `/tmp/claude-0/-workspace-WorldVoice/1edac6d9-7900-4c53-bcf9-ab498b97141f/scratchpad/p53/runtests.sh /workspace/WorldVoice-phase53 <out> tests` (kills pytest under 3 GB MemAvailable); written `FULL` below.
- Baseline at `9d96ace`: 3566 passed, 0 skipped.
- Progress ledger: `.superpowers/sdd/2026-10-29-phase53-player-control-fault/progress.md`; deviations as `Ruling: <decision> — <reason> — <cost if wrong>`.

## Review Focus

1. **Cancel while a feed is in flight** (OneCore segment and ordinary callback, VE/Cerence native callback): the feed's audio must be stopped again before the successor's first native call, now by the lease only. Task 2 (`test_cancelled_segment_feed_is_stopped_by_the_lease_before_successor`, existing `test_cancelled_legacy_feed_retires_only_after_its_final_stop`) and Task 5 (`test_late_feed_after_cancel_is_stopped_and_stop_failure_latches`).
2. **Index callbacks during playback after retirement** (OneCore): a lease that admitted `onDone` through `host.consumer` would silently drop every index after the callback returns, so say-all would lose its caret. Task 2 `test_index_fires_after_the_record_retired`.
3. **A stop failure under OneCore's pause lock with a re-entrant cancel from the failure sink or a `DONE` listener**: delivery must wait until the non-reentrant pause lock is released. Task 3 `test_cancel_pause_lock_stop_failure_delivers_after_lock_release`; existing `test_control_error_fails_queued_contexts_and_allows_reentrant_cancel`.
4. **OneCore sample-rate change mid-utterance** (voice with another rate): the replacement player must be leased, honour a held pause, and a failed replacement must fail only that segment. Task 2 `test_player_is_leased_after_seed_construction_and_replacement`; Task 4 `test_player_replacement_failure_fails_only_its_segment`; existing `test_pause_before_first_wav_also_pauses_new_player`.
5. **A drain failure followed at once by the successor segment** (multi-language sentence): the successor may start only after the failed record's stop; if that stop fails, it is rejected. Task 4 (`test_sync_failure_fails_only_its_segment`, `test_drain_stop_failure_after_sync_failure_latches`) and Task 6 (`test_drain_idle_failure_fails_only_its_segment`, `test_drain_stop_failure_after_idle_failure_latches`).

---

### Task 1: Two-phase `ControlFaultPolicy` and the written rule

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/runtime/engineControl.py:1-96`
- Test: `tests/test_engine_control.py`

**Interfaces:**
- Consumes: `SegmentHost.latch_control_error`, `SegmentHost.abandon`, `SegmentHost.control_error`.
- Produces: `ControlFault(error: Exception, dropped: tuple[NativeRecord, ...])` (frozen dataclass); `ControlFaultPolicy(host, condition, drop: Callable[[], Iterable[NativeRecord]] | None = None, *, after: Callable[[ControlFault], None] | None = None)` with `capture(error) -> ControlFault | None`, `deliver(fault: ControlFault | None) -> None`, `fail(error) -> bool`, `deferred() -> ContextManager[None]`.

- [ ] **Step 1: Write the failing tests** in `tests/test_engine_control.py` (fake `Host` as in `test_control_fault_latches_once_and_abandons_outside_the_lock`):
  - `test_capture_drops_under_the_lock_and_returns_none_once_latched`: in `drop`, `condition._is_owned()` is True; `capture(e)` returns a fault with `fault.error is e` and `fault.dropped == tuple(records)`; nothing abandoned yet; a second `capture` returns `None` and `drop` ran once.
  - `test_deliver_runs_after_even_when_an_abandon_raises`: `abandon` raises on the first record; `pytest.raises(OSError)` around `deliver(fault)`; `after` got `[fault]`; `policy.deliver(None)` is a no-op.
  - `test_deferred_delivers_after_the_outermost_block_outside_a_lock`: `lock = Lock()`; `with policy.deferred(), lock: with policy.deferred(): assert policy.fail(e) is True; assert abandoned == []`; after the blocks `abandoned == records` and inside `after` `lock.acquire(blocking=False)` was True.
  - `test_fail_without_drop_only_latches`: `ControlFaultPolicy(Host(), Condition())` → `fail(e) is True`, `latched == [e]`, `fail(OSError()) is False`.
- [ ] **Step 2: Run** `python3 -m pytest -q -p no:cacheprovider tests/test_engine_control.py` — expected: 4 failed (`AttributeError`/`TypeError`), 5 passed.
- [ ] **Step 3: Implement** in `engineControl.py`: `ControlFault`, the new `ControlFaultPolicy` signature and the four methods (spec §3.2). `fail` = `capture`, then deliver now or, inside `deferred()` on this thread, keep the fault (at most one) for the outermost block's exit; per-thread state in a `threading.local`. Rewrite the module docstring to state the latch rule (spec §3.1) and "wrappers with their own queue latch only through this policy; eSpeak uses `LeasedPlayer`'s default hook".
- [ ] **Step 4: Run** the same file — expected: 9 passed. `FULL` — expected 3570 passed, 0 skipped.
- [ ] **Step 5: Commit** `feat: give the control-fault policy capture, deliver and deferred delivery` (both files).

### Task 2: OneCore leases every player (B5, C2)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py` (imports `:13-19`, new class before `_OneCoreStrategy`, `SynthDriver.__init__` `:198-218`, `_segmentPlayback` `:419-460`, `_legacyCallback` finally `:488-493`, `_feedSegment` `:499-507`)
- Test: `tests/test_onecore_segment_drain.py`

**Interfaces:**
- Consumes: `LeasedPlayer` (`host:681-759`); existing `SynthDriver._failSegmentControl(error)`.
- Produces: `_OneCorePlayer(driver, player)` (`LeasedPlayer`, `idle_barrier=None`; `_callback(record, on_done)` returns `on_done`; `_stop_failed` → `driver._failSegmentControl`); `SynthDriver._player` property/setter over `self._leasedPlayer` (setter wraps any non-`LeasedPlayer`, keeps `None`).

- [ ] **Step 1: Write the failing tests:**
  - `test_stop_player_failure_latches_and_rejects_ordinary_speech`: speak a segment, wait native call, `env.player.stop` raises `OSError("stop failed")`; `with pytest.raises(OSError): host._strategy.stop_player(host)` via `segment_host(env.driver)`; `segment_host(env.driver).control_error` is that error; `pytest.raises(OSError)` on `env.driver.speak(("next",))`.
  - `test_player_is_leased_after_seed_construction_and_replacement`: `isinstance(env.driver._player, env.rt.segmentHost.LeasedPlayer)` (load the class from `sys.modules[type(env.driver).__module__].LeasedPlayer`) and `env.driver._player._player is env.player`; set `env.driver._player = None` → `None`; respond with a WAV at another rate (`env.player.samplesPerSec = 2000` before respond so NVDA replaces it) → still a lease wrapping `env.player`.
  - `test_index_fires_after_the_record_retired`: speak a segment, respond with `markers="1:20000"` while `env.player` defers `onDone` (patch `feed` to stash it); after the callback returned and the worker retired (`eventually(lambda: native_call(env.driver) is None)`), call the stashed `onDone` → `env.indexes == [1]`; then `sync_release.set()` and the segment drains.
  - `test_cancelled_segment_feed_is_stopped_by_the_lease_before_successor`: as `test_cancelled_legacy_feed_retires_only_after_its_final_stop` but with a segment: hold `feed`, `cancel()`, queue segment 18, block the post-feed `stop`; assert the blocked stop is reached and no second native call starts before it is released.
- [ ] **Step 2: Run** `python3 -m pytest -q -p no:cacheprovider tests/test_onecore_segment_drain.py -k "latches_and_rejects or is_leased or after_the_record_retired or stopped_by_the_lease"` — expected: the first three fail (no latch / raw player / — index may pass); record exact red set in the ledger. (The fourth may pass today via `_feedSegment`; it pins the lease after the hand-written stops are deleted.)
- [ ] **Step 3: Implement** `_OneCorePlayer`; add `self._leasedPlayer = None` in `__init__` before `super().__init__()`; the `_player` property and setter; delete the stops at `:458-460` (finally), `:488-493` (finally) and `:505-506`; `_feedSegment` becomes check-valid / feed / return `record.is_valid()`. Keep the `except` stop at `:456-457`.
- [ ] **Step 4: Run** the whole `tests/test_onecore_segment_drain.py` and `tests/test_engine_segment_contract.py` — expected: all pass. `FULL` — expected 3574 passed, 0 skipped.
- [ ] **Step 5: Commit** `refactor: lease every OneCore player through LeasedPlayer` (body: B5 one late-feed stop, C2 stop failures latch).

### Task 3: OneCore control faults through the policy (B4)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py` (`:509-635`, `__init__`)
- Test: `tests/test_onecore_segment_drain.py` (`:418-465`, `:1326-1351`, new test)

**Interfaces:**
- Consumes: Task 1 `ControlFaultPolicy`, `ControlFault`.
- Produces: `SynthDriver._controlFault` (policy with `drop=self._dropForControlFault`, `after=self._afterControlFault`); `_dropForControlFault() -> list[NativeRecord]` (under `_segmentCondition`); `_afterControlFault(fault: ControlFault) -> None`; `_failSegmentControl(error) -> bool`. Removed: `_captureSegmentControlFailure`, `_deliverSegmentControlFailure`.

- [ ] **Step 1: Change the held-delivery tests** to patch `env.driver._controlFault.deliver` (instance attribute) instead of `_deliverSegmentControlFailure`, and write `test_cancel_pause_lock_stop_failure_delivers_after_lock_release`: speak a segment; make `env.player.stop` succeed once then raise; wrap `env.driver._controlFault.deliver` (`monkeypatch.setattr` on the policy instance) with a recorder of `env.driver._segmentPauseLock.acquire(blocking=False)` (released again) before calling the original; `pytest.raises(OSError)` on `cancel()`; assert the recorded acquire was True, `control_error` is the stop error and `stop_gate_clear(env.driver)`.
- [ ] **Step 2: Run** `python3 -m pytest -q -p no:cacheprovider tests/test_onecore_segment_drain.py -k "control_fault or fault_capture or pause_lock_stop"` — expected: 3 failed (`AttributeError: _controlFault`).
- [ ] **Step 3: Implement** spec §3.3 "Control faults": build the policy in `__init__` after `_stopGate`; move capture's post-latch body into `_dropForControlFault` (store the legacy flag on `self._controlFaultLegacy`) and delivery's post-abandon body into `_afterControlFault`; `_maybeInitPlayer`, `pause` and `cancel`'s pause-lock block use `with self._controlFault.deferred(), self._segmentPauseLock:` and call `_failSegmentControl` where they captured. Keep `_maybeInitPlayer`'s current catch-all for now (Task 4 narrows it).
- [ ] **Step 4: Run** `tests/test_onecore_segment_drain.py`, `tests/test_engine_segment_contract.py` — all pass. `FULL` — expected 3575 passed, 0 skipped.
- [ ] **Step 5: Commit** `refactor: route OneCore control faults through ControlFaultPolicy`.

### Task 4: OneCore follows the latch rule (C5)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py` (`drain` `:177-192`, `_speakRecord` `:327-378`, `_legacyCallback` `:462-487`, `_maybeInitPlayer`)
- Modify: `tests/test_hygiene_guards.py` only if a new `noqa: BLE001` reason needs an entry (it should not: reasons below exist)
- Test: `tests/test_onecore_segment_drain.py` (`:592-657`, `:1429-1439`, new tests)

**Interfaces:**
- Consumes: Task 2 lease (`player.stop()` latches on failure), Task 3 `_failSegmentControl`.
- Produces: nothing new.

- [ ] **Step 1: Rewrite/write the tests:**
  - `test_sync_failure_fails_only_its_segment` (replaces `test_onecore_shared_sync_fault_rejects_successor_without_native_call`): first segment's `sync` raises → its event `SEGMENT_FAILED` with `error` the `OSError("sync failed")`; `env.player.stops` grew by ≥1 before the successor's native call; `control_error is None`; reset `env.player.error = None`, successor `SEGMENT_DRAINED`, `len(env.native.calls) == 2`.
  - `test_sync_failure_lets_a_queued_segment_drain` (replaces `test_onecore_sync_fault_fails_accepted_queued_segment`): queued 18 drains after 17 failed.
  - `test_drain_stop_failure_after_sync_failure_latches`: `sync` and the next `stop` raise → `control_error` is the stop error; successor rejected, no new native call.
  - `test_onecore_rejected_segment_uses_async_lifecycle_delivery[False]`: latch by `cancel()` with a failing stop instead of a sync error.
  - `test_segment_player_open_failure_fails_only_its_segment` (replaces `..._still_latches`): event error is the open error; `control_error is None`; with `open` restored the next segment drains.
  - `test_player_replacement_failure_fails_only_its_segment`: `env.player.samplesPerSec = 2000`, `nvwave.WavePlayer` (patch `env.base.nvwave.WavePlayer`) raises → segment fails with it, `control_error is None`.
  - `test_ordinary_callback_failure_fails_only_its_sentence`: after one completed segment (so legacy goes through the worker), `env.driver.speak(("a",))`, `env.player.error = "feed"` for its callback → `env.dones == [env.driver]` once, `control_error is None`, `env.player.stops` ≥ 1; `env.driver.speak(("b",))` reaches native.
- [ ] **Step 2: Run** `python3 -m pytest -q -p no:cacheprovider tests/test_onecore_segment_drain.py -k "fails_only or lets_a_queued or stop_failure_after_sync or async_lifecycle"` — expected: the five behaviour tests fail (latched today); the stop-failure and async-delivery tests pass.
- [ ] **Step 3: Implement** spec §3.3 "Latch rule": drain `except` (`noqa: BLE001 - recorded on the record; the segment fails`) records then `player.stop()` inside a nested `try` whose handler (`noqa: BLE001 - latched: the player or engine state is unknown`) calls `driver._failSegmentControl`; segment `open()` failure records only; `_maybeInitPlayer` calls `_failSegmentControl` only for the new player's `pause(True)` failure; `_legacyCallback` `except` records on its record and logs; `_speakRecord` completes an ordinary record whose `error` is set like a skipped one.
- [ ] **Step 4: Run** `tests/test_onecore_segment_drain.py`, `tests/test_engine_segment_contract.py`, `tests/test_hygiene_guards.py` — all pass. `FULL` — expected 3578 passed, 0 skipped.
- [ ] **Step 5: Commit** `fix: fail only the record on OneCore drain, open and replacement errors`.

### Task 5: VE/Cerence feed and stop through a lease (B5)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/VE/__init__.py` and `driver/Cerence/__init__.py` identically (imports, new class after `_IdleRoutingPlayer`, `_process` finally `:295-302`, `_installGuard` `:439-443`, `_feedCallback` `:646-648`, `_stopPlayer` `:693-701`, `cancel` stop `:727-731`, `pause` cleanup stop `:836`, `_runNative` blocked stop `:616`)
- Test: `tests/test_vocalizer_segment_drain.py`

**Interfaces:**
- Consumes: `LeasedPlayer`. `_CallbackPlayer._stop_failed` keeps the inherited default (host latch) in this task; Task 6 points it at the policy.
- Produces: `_CallbackPlayer(driver, player)` (`LeasedPlayer`, `idle_barrier=None`, `feed` admits `host.callback_record()`); `SynthDriver._leasedPlayer`.

- [ ] **Step 1: Write the failing tests** (both engines via the `env` fixture):
  - `test_feeds_go_through_the_lease`: `isinstance(env.core._leasedPlayer, LeasedPlayer)` and `env.core._leasedPlayer._player is real_player(env.core)`; a segment's PCM reaches `real_player(env.core).fed`.
  - `test_late_feed_after_cancel_is_stopped_and_stop_failure_latches`: hold the real player's `feed` inside a callback, `cancel()` from another thread, make the next `stop` raise, release the feed → `segment_host(env.core).control_error` is that stop error and the successor segment fails.
- [ ] **Step 2: Run** `python3 -m pytest -q -p no:cacheprovider tests/test_vocalizer_segment_drain.py -k "through_the_lease or late_feed_after_cancel"` — expected: 4 failed.
- [ ] **Step 3: Implement** spec §3.4 first two bullets plus "`_stopPlayer` and `cancel` stop through the lease"; the `pause` cleanup and `_runNative` blocked stops also use `self._leasedPlayer.stop()` (handlers unchanged). Remove the callback's final stop. Same edit in Cerence.
- [ ] **Step 4: Run** `tests/test_vocalizer_segment_drain.py`, `tests/test_vocalizer_drift.py`, `tests/test_native_strategy_guards.py`, `tests/test_engine_segment_contract.py` — all pass. `FULL` — expected 3582 passed, 0 skipped.
- [ ] **Step 5: Commit** `refactor: feed and stop the VE and Cerence players through a lease`.

### Task 6: VE/Cerence latch through the policy and follow the rule (B4, C5)

**Files:**
- Modify: VE and Cerence `__init__.py` identically (imports, `__init__`, `_CallbackPlayer._stop_failed`, drain `:340-357`, `_runNative` `:604-609`, `_stopPlayer`, `cancel`, `pause` `:820-823`)
- Modify: `tests/test_hygiene_guards.py` `_REASONS` (`:145-160`)
- Test: `tests/test_vocalizer_segment_drain.py` (`:406-421`, new test)

**Interfaces:**
- Consumes: Task 1 policy; Task 5 `_CallbackPlayer`.
- Produces: `SynthDriver._controlFault = ControlFaultPolicy(self._segmentHost, self._speechStateLock)`; `SynthDriver._failSegmentControl(error) -> bool`.

- [ ] **Step 1: Write the tests:**
  - `test_drain_idle_failure_fails_only_its_segment` (replaces `test_player_failure_rejects_successor_with_context`): first idle raises → first event `SEGMENT_FAILED` with that error and its `source_id`; a stop ran; `control_error is None`; idle restored, successor `SEGMENT_DRAINED` and reached native.
  - `test_drain_stop_failure_after_idle_failure_latches`: idle and the following stop raise → `control_error` is the stop error, successor `SEGMENT_FAILED` without a native call.
- [ ] **Step 2: Run** `-k "idle_failure_fails_only or stop_failure_after_idle"` — expected: the first fails (latched today, ×2), the second passes or fails by latch identity; record it.
- [ ] **Step 3: Implement** spec §3.4 bullets 3–4: build the policy in `__init__` after `_segmentHost`; `_failSegmentControl`; `_CallbackPlayer._stop_failed` → driver's `_failSegmentControl`; drain `except` (`noqa: BLE001 - recorded on the record; the segment fails`) records then `_stopPlayer()` in a nested `try` (`noqa: BLE001 - latched: the player or engine state is unknown` → `_failSegmentControl`); `pause` and `_runNative` call `_failSegmentControl`; `cancel` and `_stopPlayer` lose their explicit latch. In `_REASONS`, replace `("record_error", "latch_control_error")` by nothing (keep `("record_error", "_failSegmentControl")`) and `("latch_control_error", "error = exc")` by `("_failSegmentControl", "error = exc")` (RHVoice uses it in Task 7; the entry is harmless before).
- [ ] **Step 4: Run** the vocalizer, drift, hygiene, guard and contract tests — all pass. `FULL` — expected 3584 passed, 0 skipped.
- [ ] **Step 5: Commit** `fix: fail only the record on a VE and Cerence drain idle error`.

### Task 7: RHVoice latches through the policy (B4)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py` (`_NativeLibrary` `:115-168`, `_WavePlayer` `:171-185`, `submit` `:283`, `__init__` `:308-321`, `_wrapPlayer` `:342`, `cancel` `:410-422`)
- Test: `tests/test_rhvoice_segment_drain.py`

**Interfaces:**
- Consumes: Task 1 policy.
- Produces: `SynthDriver._controlFault = ControlFaultPolicy(self._segmentHost, self._segmentCondition)`; `_failSegmentControl(error) -> bool`; `_WavePlayer(driver, player)`; `_NativeLibrary(host, native, record, fail)` where `fail` is `Callable[[Exception], object]`.

- [ ] **Step 1: Write the failing test** `test_player_stop_failure_goes_through_the_control_fault_policy`: patch `env.driver._controlFault.fail` with a recorder that calls the original; `env.players[0].stop_error = OSError("stop failed")` after one segment created the player; `pytest.raises(OSError)` on `env.driver.cancel()`; recorder saw that error first; `control_error` is it.
- [ ] **Step 2: Run** `python3 -m pytest -q -p no:cacheprovider tests/test_rhvoice_segment_drain.py -k control_fault_policy` — expected: 1 failed (`AttributeError: _controlFault`).
- [ ] **Step 3: Implement** spec §3.5; the `cancel` handlers keep `noqa: BLE001 - latched, and kept to raise after the remaining cleanup`.
- [ ] **Step 4: Run** `tests/test_rhvoice_segment_drain.py`, hygiene, guards, contract — all pass. `FULL` — expected 3585 passed, 0 skipped.
- [ ] **Step 5: Commit** `refactor: route RHVoice control errors through ControlFaultPolicy`.

### Task 8: Guards, mutants and spec notes

**Files:**
- Modify: `tests/test_native_strategy_guards.py`
- Modify: `docs/superpowers/specs/2026-10-29-phase53-player-control-fault-design.md` §9
- Ledger only: mutant results

**Interfaces:**
- Consumes: everything above.
- Produces: guards.

- [ ] **Step 1: Write the guards:**
  - `test_no_wrapper_calls_latch_control_error`: no `ast.Attribute` with `attr == "latch_control_error"` in any `driver/<Engine>/__init__.py`.
  - `test_queue_owning_wrappers_build_one_control_fault_policy`: RHVoice, SAPI5, OneCore, VE, Cerence each contain exactly one `ControlFaultPolicy(` call; eSpeak none.
  - `test_onecore_and_vocalizer_players_are_leased`: `_OneCorePlayer` and `_CallbackPlayer` have `LeasedPlayer` as their only base.
  - `test_onecore_and_vocalizer_feed_and_stop_only_through_the_lease`: in OneCore no `.feed(`/`.stop(` on an expression ending in `_player._player`/`._player` raw access outside `_OneCorePlayer`; in VE/Cerence no `_realPlayer.feed(` or `_realPlayer.stop(`.
- [ ] **Step 2: Run** them — expected: 4 passed (red check: on a scratch copy of `master` the first and last fail; record in the ledger).
- [ ] **Step 3: Mutants** (spec §7.2) on scratch copies under the scratchpad, one at a time, each with the owning test file: expected each killed; then `mutmut run` on a scratch clone with `source_paths` set to `runtime/engineControl.py` only; record survivors with reasons.
- [ ] **Step 4: Full verification** (§7): `FULL` — expected 3589 passed, 0 skipped; `prek run --all-files` all Passed; `git diff --check` empty; both protected-path commands empty. Fill spec §9 (Rulings, counts, mutant results).
- [ ] **Step 5: Commit** `test: guard the single player lease and control-fault path` (guards) and `docs: record phase 53 implementation notes` (spec, `git add -f`).
