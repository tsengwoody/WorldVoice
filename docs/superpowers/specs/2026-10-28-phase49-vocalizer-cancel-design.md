# Phase 49: VE and Cerence cancellation without the silence gate

Date: 2026-10-28.
Base: `master` `ea0d197`. Branch: `phase49-vocalizer-cancel`.
Source: the user's request (relayed by the orchestrator) to pick the better of the two ways the vendored-driver wrappers silence native callbacks after cancellation, and to unify on it.
Status: normal flow (DEVELOPMENT_WORKFLOW.md §3). No approval gates; open points are *Decided by orchestrator with the recommended default; user may override before merge*.

Paths are under `addon/synthDrivers/WorldVoice/` unless stated. VE line numbers are for `driver/VE/__init__.py` at `ea0d197`; the Cerence wrapper `driver/Cerence/__init__.py` is the same code (its lines are +0 to +7 later, `tests/test_vocalizer_drift.py:7` pins every difference). Inner lines are for `driver/VE/driver/__init__.py`; the Cerence inner is the same at the same lines (`driver/Cerence/driver/__init__.py:104-105`, `:154-197`, `:229-237`, `:289-290`, `:425-443`).

## 1. Problem

Three vendored drivers have the same shape: one worker thread with a task queue, one `threading.Event` stop flag that the native callbacks read, and an inner `cancel()` that empties the queue, sets the flag, queues `flag.clear` and stops the player.

| | VE / Cerence inner | RHVoice inner |
| --- | --- | --- |
| worker | `BgThread` + `_bgQueue` (inner `:79-96`, `:279-280`) | `TTSThread` + `__tts_queue` |
| stop flag | `_isSilence` (inner `:289`), read by `VECallback.__call__` (inner `:154`, `:183`, `:194`, `:196`) | `__cancel_flag`, read by the native callbacks |
| inner cancel | drain queue, `set`, queue `clear`, `stop`, `join` (inner `:441-456`) | same idea |

The wrappers handle that flag in two different ways:

- **RHVoice** (`driver/RHVoice/__init__.py`) leaves the inner flag alone as the inner driver's own business. Its own decisions come from the record: callbacks are wrapped by name (`_NativeCallback` `:94-110`) and admitted per record (`_nativeCallback` `:334-355`, `host.consumer`), its own queue tasks are gated by the stop gate (`_QueuedSpeech` `:211-259`), and it only *uses* the inner flag to stop the native synthesis (`stop_native` `:294-297`, inner `cancel` via `super().cancel()` `:393`) and clears it after a segment (`:256-257`).
- **VE / Cerence** replace the inner Event with `_SilenceGate` (`:96-121`): a token-aware `is_set` that also reports "stop" outside a native call (`_insideNativeCall`), a `clear` that does nothing, and `begin(token)` that really clears it. They replace the inner `_player` on the core *and* on the callback with `_GuardedPlayer` (`:124-147`). But the same wrappers *also* do everything RHVoice does: `_ContextualVECallback` (`:230-330`) replaces the inner callback body with per-native-call admission (`_callbackAdmission` `:665-685`, `host.consumer`, `host.bound_callback`) and a validity check on every step (`_recordValid` `:536-545`, which already checks the record's token); own queue tasks bracket each record (`_Begin`, `_NativeTask`, `_Retire` `:170-201`); and the wrapper overrides `cancel`, `pause`, `terminate`, `_speak`, `_onIndexReached` and `getParameters`.

So VE and Cerence carry two layers that answer the same question ("is this work still valid?"). With the guard installed, the inner code that reads the gate never runs (§3), so the gate is a second, partly stale source of truth: a resettable flag (`set` by cancel, really cleared by the next `begin`), a token copy (`_token`) and a native-call marker (`_insideNativeCall`) beside the record, its token and the call admission that already decide.

## 2. Goals, non-goals, anti-goals

Goals:

1. VE and Cerence move to the RHVoice approach: remove `_SilenceGate`; the inner `_isSilence` Event stays the plain inner Event and the guarded wrapper never reads or writes it; the record (`_recordValid`), the host admission (`host.consumer`) and the native-call admission (`_NativeCall.admitting`) are the single source of truth for "is this work still valid". *Decided by orchestrator with the recommended default; user may override before merge.*
   Why this direction and not the reverse: the wrapper already owns every decision the gate makes (§3), so the gate only adds a duck-typed stand-in for an inner object (fragile to inner updates) and three extra states. Moving RHVoice to a gate would add a stand-in where RHVoice now has none.
2. The player stand-in stays, because VE/Cerence need it for a reason RHVoice does not have: the inner `speak` builds `DoneSpeaking(self._player, …)` (inner `:435`) whose `__call__` runs `self._player.idle()` (inner `:236`), and the wrapper must route that idle to `_idlePlayer` (segments drain on the lifecycle thread instead, `:691-705`). It is simplified to that one duty and renamed `_WavePlayer` — the name RHVoice gives its own stand-in for the inner player (`driver/RHVoice/__init__.py:169`). It does **not** become a `LeasedPlayer`: VE/Cerence indexes come from SDK bookmarks inside the callback (`:295-299`), not from the player's `onDone`, and audio is fed by `_feedCallback` (`:687-689`), not through the stand-in.
3. VE and Cerence change identically; `tests/test_vocalizer_drift.py` `ALLOWED` stays as it is.
4. The fallback path (guard not installed → original inner driver) is unchanged, including *when* it is chosen.

Non-goals:

- No change to RHVoice behaviour or code (no inconsistency needing a Ruling was found; §6).
- No change to the inner drivers (`driver/<Engine>/driver/`), to `runtime/`, or to any other engine.
- No new shared code between engine packages.

Anti-goals (a failure even if tests pass):

- Any audio after cancel, any index or DONE after cancel that was silent before, any change in the index/DONE order of uncancelled speech.
- A Windows-visible change in pause, resume or termination.

## 3. Inventory: every gate duty, and what covers it

"Guard installed" is the normal case: `_installGuard` (`:443-483`) succeeds and sets `_guardInstalled`. "Not installed" is the fallback when a private field is missing or an assignment fails (`:444-456`, `:465-481`).

### 3.1 Reads and writes in the inner driver

| Inner site | Guard installed | Not installed |
| --- | --- | --- |
| `VECallback.__call__` reads `isSet()` (`:154`, `:183`, `:194`, `:196`) | never runs: `_ContextualVECallback.__call__` calls `super().__call__` only when `not driver._guardInstalled` (`:249-250`); otherwise it goes to `_process` (`:262-311`), which never reads `_isSilence` | runs on the plain inner Event, as upstream |
| inner `cancel` `set` / queue `clear` (`:453-454`) | never runs: the wrapper's `cancel` (`:725-761`) does not call `super().cancel()`; the inner `terminate` (`:335-336`) calls `self.cancel()`, which is the wrapper's (returns at once once `_playerClosing` is set, `:733-734`, `:938`) | runs, as upstream |
| `DoneSpeaking` → `self._player.idle()` (`:236`) | the stand-in's `idle` → `_idlePlayer` (`:139-142`) | real player idle |
| inner `pause` → `self._player.pause` (`:459`); inner `terminate` → `self._player.close()` (`:346`) | forwarded by the stand-in's `__getattr__` (`:146-147`) | real player |
| `VECallback.__init__` stores `player`, `isSilence` (`:103-105`) | stored, then the wrapper swaps them (`:461-464`) | stored, used |

So with the guard installed, the gate's `is_set`/`isSet` override, the `_insideNativeCall` "stop outside a native call" answer and the blocked `clear` are dead code: nothing ever calls them.

### 3.2 Reads and writes in the wrapper (guard installed only)

`cancelled()` = flag set by `cancel` since the last real `_beginRecord` **or** the current record's token cancelled. `tokenCancelled()` = the second half only. Facts used below, all from `runtime/segmentHost.py` and the wrapper:

- F1 `host.cancel()` (`segmentHost.py:287-289`, `_invalidate` `:663-669`) marks every pending record `cancelled`, and it runs before `self._isSilence.set()` in the wrapper's `cancel` (`:735-737`).
- F2 The current record is pending for all of its native work: it enters `_pending` in `enqueue` (`segmentHost.py:264`) and leaves it only by `abandon` (then it never becomes current), by `retire` when already invalid (`:501-502`), by `forget` (VE calls it at the end of `_retireRecord`, after the record's last native task, `:574-575`) or by segment delivery (after the drain, `segmentHost.py:649`).
- F3 `_token` and `_currentRecord` have the same lifetime: both set in the non-skipped branch of `_beginRecord` (`:556-559`), both cleared at the end of `_retireRecord` under the same lock (`:577-581`). `_token` is `record.work.token` for a segment (`:558`), and `PlaybackWork.is_valid()` is false once that token is cancelled (`runtime/playbackWork.py:80-82`); for ordinary speech `record.work` is `None` (`segmentHost.py:331-333`) and `_token` is `record.native.token`, which `_recordValid` checks (`:539-544`). So "token cancelled" ⇒ `not _recordValid(_currentRecord)`.
- F4 `_doneOwner` equals `_currentRecord` for a record that really began (`:552-556`), and is the skipped record (with `_currentRecord` `None` and `_token` `None`) for a skipped one.

| Wrapper site | Gate use | Covered by | Result |
| --- | --- | --- | --- |
| `_beginRecord` `self._isSilence.begin(token)` (`:558-559`) | resets the flag, stores `_token` | nothing to reset: validity is per record and monotonic (a record never becomes un-cancelled, a token never un-cancels) | **removed** |
| `_retireRecord` `_insideNativeCall = False`, `_token = None` (`:568`, `:581`) | gate bookkeeping | — | **removed** |
| `_runNative` `… or self._isSilence.cancelled()` (`:621`) | skip a piece after cancel | the same line's `record is not self._currentRecord or not self._recordValid(record)`: by F1+F2 a cancel marks the current record; by F3 a token cancel invalidates it. The re-check under the lock (`:630`) and the call admission (`:663`, `:745`) cover a cancel during the wait | **covered** |
| `_runNative` `_insideNativeCall = True/False` (`:627`, `:640`) | "stop" answer outside a native call | `_nativeCall` + `call.admitting` (`:626`, `:639`, `:669-673`): a callback outside an admitting call gets USERSTOP (`:251-261`) | **covered** |
| `cancel` `self._isSilence.set()` (`:737`) | raise the flag | F1: `host.cancel()` two lines earlier; call admission closed at `:743-745` | **removed** |
| `_onIndexReached(None)` `self._isSilence.tokenCancelled()` (`:815`) | drop DONE of a token-cancelled request | the same line's `token.is_cancelled()` for `_doneOwner`: by F3+F4 `_token` is that token (segments return earlier, `:809-810`), or `None` | **covered** |
| `_onIndexReached(index)` `self._isSilence.cancelled()` (`:817`) | drop an index after cancel | `not self._recordValid(record)` on the same line (F1–F3). An index only reaches here from `_process`, which holds an admitted current record (`:251`, `:295-299`) | **covered**; see D2 for the unreachable `record is None` case |
| `_idlePlayer` `self._isSilence.cancelled()` (`:697`) | skip the inner DONE idle after cancel | record current: `not self._recordValid(record)` on the same line (F1–F3). **Record `None`** (DoneSpeaking of a skipped record, F4, or of a dropped ordinary record that `_dropQueuedSpeech` keeps, `:793-796`): only the flag answers | **replaced** by D1 |
| `_VEStrategy.drain` `not driver._isSilence.cancelled()` (`:380`) | do not reach `idle` after cancel | `driver._recordValid(record)` on the same line: the drained segment is the current record (its worker waits in `host.retire` for the handoff, `segmentHost.py:513`) and pending until delivery (F1, F2, F3) | **covered** |
| `_GuardedPlayer.feed` (`:130-137`) | drop/stop a feed after cancel | dead: nothing feeds the stand-in. The guarded callback feeds the real player through `_feedCallback` (`:687-689`), which checks `_recordValid`, and `_process` stops the real player after an invalidated step (`:317-322`); the inner `feed` calls (inner `:177`, `:181`, `:197`) run only in the fallback | **removed** |
| `_GuardedPlayer.idle` with a dead driver weakref (`:143-144`) | idle unless cancelled | unreachable: the only caller is the inner `DoneSpeaking`, which holds the bound method `self._onIndexReached` (inner `:233`, `:435`), a strong reference to the driver | **replaced** by D1 (no driver → no idle) |

Duties the analysis checked and found not owned by the gate: pause/resume (`pause` `:821-875` uses `_paused`, `_pauseRevision`, `_pauses` and the stop gate), termination (`_terminationRequested`, `_playerClosing`, `_RETAINED_CALLBACKS`, `detach` `:326-330`), late native callbacks (admission + `detach`, `:246-248`), legacy ordinary speech with a token (`_recordValid` reads `record.native.token`), and the race the blocked `clear` prevented in the inner driver (the inner `cancel` queues `clear`, which could reset a later cancel's flag — with the guard installed nothing is queued, and record validity cannot be reset).

**Conclusion:** the gate is not load-bearing. Exactly one gate decision is not already made by record state: whether the inner DONE idle runs when no record is current. D1 replaces it with a stricter rule; nothing needs to be kept.

### 3.3 Not installed (fallback)

Unchanged: `_installGuard` keeps the same availability check (the same five fields, `:444-456`), returns before touching anything, and every overridden method keeps its `if not self._guardInstalled: return super()…` first line. The inner Event stays the plain Event the wrapper creates (`:430`), exactly as now.

## 4. Design

### D0. Install

`_installGuard` keeps its availability check and log line. It then wraps only the core's `_player` in `_WavePlayer(real, self)`, records `self._realPlayer = real` and sets `_guardInstalled`. The callback's `_player` and both `_isSilence` references are left as created: the guarded path never reads them (§3.1, §3.2). If the one assignment raises, the core falls back with nothing changed and logs "installation failed"; there is no restoration step and so no "restoration failed" error any more (a single failed assignment cannot leave a partial install). *Decided by orchestrator with the recommended default; user may override before merge.*

### D1. The inner DONE idle needs a running record

`_idlePlayer` (`:691-705`) becomes: segment record → return (unchanged); **no current record → return**; invalid record → return; else idle as now (with the pause wait). `_WavePlayer.idle` with a dead driver returns `None`.

Old behaviour with no current record: idle the real player unless a cancel happened since the last real begin. New: never. The only case that changes is a skipped ordinary request (its token cancelled before it began, or a latched control error) with no cancel since the last real begin: the old code idled the player, the new code does not. That idle had nothing of its own to wait for — a skipped record fed no audio, and the record before it already idled (ordinary), drained (segment) or was stopped (cancelled; `segmentHost.py:515-523`) on the same FIFO worker — and after a control error the player state is uncertain, so skipping is the safer side. DONE ordering is unchanged (the inner `DoneSpeaking` still calls `_onIndexReached(None)` right after). *Decided by orchestrator with the recommended default; user may override before merge.*

### D2. An index needs a running record

`_onIndexReached(index)` drops an index when no record is current or the current record is invalid. Old: an index with no current record was published unless a cancel had happened since the last real begin. That case is unreachable from the SDK (§3.2) and only direct calls could produce it; dropping it matches D1 and the RHVoice rule that a callback without an admitted record is refused (`driver/RHVoice/__init__.py:340-344`). DONE (`index is None`) keeps its own rule unchanged. *Decided by orchestrator with the recommended default; user may override before merge.*

### D3. Removed state and calls

`_SilenceGate`, the `begin`/`set`/`_insideNativeCall`/`_token` calls of §3.2, `_GuardedPlayer.feed` and the second gate argument. `_VEPort.INNER_PRIVATES` keeps `_isSilence` and `_player` (still read by the availability check and the callback constructor). The two `"_SilenceGate.is_set"` entries in `tests/test_naming_layers.py:95`, `:116` go, since the name no longer exists.

### D4. `_WavePlayer`

```python
class _WavePlayer:
	"""The inner driver's player, as its DoneSpeaking sees it: idle goes to the wrapper."""
	def __init__(self, player, driver): ...
	def idle(self): ...          # driver._idlePlayer(), or None when the driver is gone
	def __getattr__(self, name): ...  # pause, stop, close, ... reach the real player
```

## 5. NVDA user's view, strings, settings

No audible or visible change: no audio after cancel, the same index and DONE notifications in the same order, the same pause/resume/termination. No new or changed translatable strings (log messages only: the "restoration failed" warning disappears). No settings or stored data change.

## 6. RHVoice

Checked for alignment only. RHVoice needs the inner flag (it is how the inner `SpeakText` stops the native message, `stop_native` `:294-297`), so its use is not a leftover and stays. No inconsistency found that needs a Ruling. The only alignment is naming: the VE/Cerence player stand-in takes RHVoice's name `_WavePlayer`.

## 7. Test plan

All tests run against both engines through `tests/worldvoice_cancel_wrapper_harness.py`.

New behaviour (red on `ea0d197`, green after):

- `test_done_of_never_spoken_request_skips_idle` — a token-cancelled-before-begin ordinary request: `real_player.idles == 0`, no DONE. (D1)
- `test_index_without_running_request_is_dropped` — direct `_onIndexReached(5)` with no current record publishes nothing. (D2)
- `test_guarded_speech_never_touches_inner_stop_flag` — a recording Event on core and callback stays untouched through speak, cancel and speak again. (D0, D3)

Kept behaviour (green before and after), as regression guards:

- `test_dropped_request_done_skips_idle_and_reports_done` — an ordinary request queued behind one that calls core `cancel()` is dropped; both DONEs are published and the player is never idled.

Rewritten (they pinned gate internals; each keeps its behaviour and is proved by a mutant, §8):

| Old test (`tests/test_worldvoice_cancel_wrappers.py`) | New form |
| --- | --- |
| `test_installs_gate_on_core_and_existing_callback` | `test_installs_player_stand_in_and_keeps_inner_stop_flag`: core `_player` is a `_WavePlayer` over `real_player`; core and callback share one plain, unset `threading.Event`; callback `_player` is `real_player` |
| `test_missing_private_field_falls_back_without_partial_install` | same parameters; asserts no `_WavePlayer` anywhere and the Event untouched |
| `test_missing_callback_falls_back_without_partial_install` | unchanged |
| `test_assignment_failure_restores_all_four_references` | `test_assignment_failure_falls_back_unchanged`: the core's `_player` assignment of a `_WavePlayer` raises; fallback with the original player |
| `test_restoration_failure_raises_instead_of_returning_partial_core` | deleted: D0 has no restoration step |
| `test_gate_checks_token_only_during_native_call` | deleted: its duties are pinned by `test_callback_rejects_audio_outside_native_call` (outside a call), the token tests below (token), and `test_cancelled_idle_cannot_complete_segment[inner-clear]` (reset) |
| `test_player_stops_after_feed_when_cancelled_mid_feed` | `test_core_cancel_during_real_callback_feed_stops_after_feed` (through the real callback, with core `cancel()`), plus no idle |
| `test_player_skips_feed_when_already_cancelled` | `test_callback_after_core_cancel_feeds_nothing` |
| `test_cancel_between_token_check_and_clear_stays_stopped` | `test_cancel_while_request_begins_stays_stopped`: pause inside `_beginRecord` at `host.begin`, cancel token and core, release; nothing spoken or fed |
| `test_native_call_marker_clears_after_exception` | `test_native_call_admission_closes_after_exception`: `native_call(core) is None` and a later callback gets USERSTOP |
| `test_cancelled_request_drops_index_and_done_notifications` | same name, through real speech: a live request publishes its index and DONE; a token-cancelled one publishes neither |
| `test_vocalizer_segment_drain.py::test_cancelled_idle_cannot_complete_segment[clear]` | `[inner-clear]`: clears the inner Event (`callback_handler(core)._isSilence`) |

The harness drops `silence_gate`, `guarded_real_player` and `inside_native_call` and gains `inner_stop_flag(owner)` and `stand_in_real_player(player)`.

`tests/test_vocalizer_drift.py`, `tests/test_native_strategy_guards.py` (inner-privates lists) and the rest of the suite must pass unchanged. Baseline: 3367 passed, 0 skipped.

No Hypothesis test: the decisions are a handful of boolean guards, covered case by case. No Windows/NVDA manual item beyond the standing one: real SDK callbacks, audio devices and NVDA are not exercised on Linux.

## 8. Mutation testing

The wrappers are not core decision modules (§7 of the workflow names `runtime/`), so mutmut is not required; targeted mutants are run on each changed decision, on a scratch copy, with bytecode off (`PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`), a per-mutant timeout and pytest output to a file:

- `_idlePlayer`: drop the `record is None` return; drop the validity return.
- `_onIndexReached`: drop `record is None`; drop the validity check; drop the DONE token check.
- `_runNative`: drop `not self._recordValid(record)` in the first check; drop the re-check under the lock.
- `_VEStrategy.drain`: drop `driver._recordValid(record)`.
- `_beginRecord`: drop the validity check that skips a record.
- `_WavePlayer.idle`: call the real `idle` instead of the driver's.
- `_installGuard`: also replace the callback's `_player`; skip the swap.
- `cancel`: drop `call.admitting = False`.

Each rewritten test of §7 is also proved by at least one mutant it kills. Survivors are recorded with a reason.

## 9. Open questions

None blocking. Defaults the user may override: D0 (no restoration step), D1 (no idle without a running record), D2 (no index without a running record), and the stand-in name `_WavePlayer`.

## 10. Implementation notes (mutation results)

Targeted mutants (spec §8 plus a few more) on each wrapper, run on a scratch copy against `tests/test_worldvoice_cancel_wrappers.py`, `tests/test_vocalizer_segment_drain.py`, `tests/test_runtime_legacy_adapter.py` and `tests/test_runtime_drain_integration.py`: 24 per wrapper, VE and Cerence alike. Killed: idle no-record and validity returns, index no-record and validity drops, the DONE token check, both `_runNative` checks together, the re-check under the lock alone (after `test_cancel_before_native_call_starts_skips_it` was added for it), the stand-in idle redirect, both install variants, the install failure path, the skipped availability check, admission left open on cancel, callback-admission validity, the final stop in `_process`, `_recordValid`'s token check, a cancel that sets the inner flag, and a native call kept after return.

Survivors, each with its reason:

- `_runNative` without its first validity check: the re-check under the lock decides the same; the first check only saves a wait.
- `_VEStrategy.drain` reaching `idle` for an invalid record: the host never publishes a cancelled segment (`segmentHost.py:570-572`, `:634`), so the reach has no effect. It also survives on `ea0d197` with the gate check removed as well.
- `_beginRecord` without its validity skip, `_feedCallback` without its validity check: later checks (`_runNative`, `_process`) decide the same. Both also survive on `ea0d197`; neither line changed in this phase.
- `_WavePlayer.idle` idling the real player when the driver is gone: unreachable (§3.2).
