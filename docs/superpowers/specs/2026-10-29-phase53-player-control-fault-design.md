# Phase 53: player and control-fault unification

Date: 2026-10-29.
Base: `master` `9d96ace` (baseline 3566 passed, 0 skipped; `prek` all Passed; protected paths clean).
Branch: `phase53-player-control-fault`, worktree `/workspace/WorldVoice-phase53`. Normal flow (DEVELOPMENT_WORKFLOW §3).
Sources: the consistency audit `cons.md` items **B4, B5, C2, C5** (§5 cancel, §6 control errors, §9 player, "建議"), and `storage/refactor9.md` row P53.

Line references: `host:` = `addon/synthDrivers/WorldVoice/runtime/segmentHost.py`, `control:` = `runtime/engineControl.py`, `lifecycle:` = `runtime/_segmentLifecycle.py`, `OneCore:` / `VE:` / `RHVoice:` / `SAPI5:` / `Espeak:` = `driver/<Engine>/__init__.py`, `oneCore.py:` / `nvwave.py:` / `speech.py:` = `ref/nvda/source/...`. Cerence line numbers equal VE's below 325, VE+2 for 326–628 and VE+7 from 630 (cons.md header); only VE lines are given.

## 1. Problem

### 1.1 Three copies of "lease the player" (B5)

Every engine must (a) admit each feed as a consumer of the record it belongs to, (b) record a feed error on that record, (c) stop the player again when a feed that was admitted before a cancel returns after the cancel's stop, and (d) treat a failed stop as a control error. `LeasedPlayer` (`host:681-759`) does all four: feed admission `host:696-700`, error recording `host:709-711`, the late-feed stop `host:712-716`, stop failure `host:737-738`, `host:754-759`. eSpeak (`Espeak:86`), RHVoice (`_WavePlayer`, `RHVoice:171-210`) and SAPI5 (`_SegmentPlayer`, `SAPI5:198-272`) use it.

Two engines repeat it by hand:

- **OneCore** never imports `LeasedPlayer` (`OneCore:13-19`). Its segment callback stops after every feed whose record became invalid (`_feedSegment`, `OneCore:499-507`), again when the callback ends (`_segmentPlayback` finally, `OneCore:458-460`), and the ordinary (legacy) callback once more (`_legacyCallback` finally, `OneCore:488-493`). NVDA's own `_callback` feeds the raw `self._player` (`oneCore.py:518-528`).
- **VE/Cerence** keep the real player in `_realPlayer` behind `_IdleRoutingPlayer` (`VE:98-119`, `VE:439-443`), which only routes the inner `DoneSpeaking` idle. Feeds go to the raw player after a validity check (`_feedCallback`, `VE:646-648`), and the native callback stops the raw player whenever its record is invalid when it returns (`VE:295-302`); that stop's failure is only recorded on the record (`VE:301-302`).

### 1.2 Three ways to latch a control error (B4)

- `ControlFaultPolicy` (`control:70-96`): latch the first error, drop the engine's queued records under the engine lock, abandon them outside it. Only SAPI5 uses it (`SAPI5:416-420`, `SAPI5:551-552`).
- OneCore's own two-phase copy, `_captureSegmentControlFailure` / `_deliverSegmentControlFailure` (`OneCore:509-553`): the same latch and drop, plus engine state (control generation, `_wasCancelled`, a stop-gate hold, a legacy `DONE`, pause reset). Capture runs while the pause lock is held; delivery after it is released (`OneCore:555-570`, `OneCore:605-635`).
- Direct `host.latch_control_error(...)`: VE drain (`VE:354`), `_runNative` (`VE:608`), `_stopPlayer` (`VE:700`), `cancel` (`VE:730`), `pause` (`VE:823`); RHVoice message cleanup (`RHVoice:167`) and `cancel` (`RHVoice:414`, `RHVoice:420`); `LeasedPlayer._stop_failed`'s default (`host:737-738`), which eSpeak and RHVoice's `_WavePlayer` inherit.

### 1.3 OneCore stop failures never latch (C2)

OneCore's `stop_native` and `stop_player` call the raw player (`OneCore:167-175`). A failure there propagates into the lifecycle's stop thread or `wait_playback_drained` and becomes a lifecycle fault (`lifecycle:486-489`, `lifecycle:311-314`): later segments are rejected (`lifecycle:264-267`), but `host.control_error` stays None, so ordinary speech is still admitted (`OneCore:256-262`) and the worker keeps feeding a player whose stop failed. The same wrapper's `cancel` does latch a stop failure (`OneCore:601-603`). The late-feed stops (`OneCore:457`, `OneCore:460`, `OneCore:493`, `OneCore:506`) never latch either.

### 1.4 The same failure has different consequences (C5)

| Event | eSpeak | RHVoice | SAPI5 | OneCore | VE/Cerence |
|---|---|---|---|---|---|
| Failed stop | latch (`host:737-738`) | latch (`RHVoice:414`, `:420`; `_WavePlayer` inherits `host:737-738`) | latch (`SAPI5:142-143`, `:239-243`, `:673-674`) | **not latched** (C2), except in `cancel` (`OneCore:601-603`) | latch (`VE:698-701`, `:729-731`); the callback's own stop only records (`VE:301-302`) |
| Failed segment drain wait (`idle`/`sync`) | n/a (idle in NVDA's callback; `LeasedPlayer.idle` records, `host:745-749`) | records (`RHVoice:250-254`) | records, then stop + purge; a failed stop/purge latches (`SAPI5:156-165`) | **latches** (`OneCore:181-190`) | **latches**, "player state is uncertain" (`VE:351-355`) |
| Failed ordinary final idle | — | records | parent's (`SAPI5:624-625` inside the request's failure path) | **latches** (`_legacyCallback`, `OneCore:485-487`) | records; "retire's stop resets the player, and a failed stop latches" (`VE:670-676`) |
| Failed player `open` | — | — | — | segment **latches**, ordinary skips the sentence (`OneCore:331-347`) | — |
| Failed player replacement (`_maybeInitPlayer`) | — | — | — | **latches** (`OneCore:565-567`) | — |
| Failed native synthesis | records (`Espeak:56-61`) | records (`RHVoice:139-152`) | segment: records, stop + purge; ordinary: **latches** (COM, `SAPI5:646-650`) | segment records; ordinary skips the sentence (`OneCore:352-360`) | records (`VE:589-591`) |

One kind of event means "this segment fails, the next one plays" in one engine and "the engine is dead until it is reloaded" in another, and VE uses both rules for the same `idle()` failure on its two paths (`VE:351-355` vs `VE:670-676`).

## 2. Goals and non-goals

Goals:

1. **One lease.** Every engine's player feeds and stops go through a `LeasedPlayer` (or subclass). The late-feed stop, feed-error recording and stop-failure handling exist only in `LeasedPlayer` (B5).
2. **One way to latch.** Every wrapper with its own native queue (RHVoice, SAPI5, OneCore, VE, Cerence) latches only through its `ControlFaultPolicy`; no wrapper calls `host.latch_control_error` (B4). eSpeak, whose queue is NVDA's, keeps `LeasedPlayer`'s default stop-failure hook (`host.latch_control_error`) — the documented host API for an engine with no queue of its own.
3. **OneCore latches a failed stop** (C2), by goal 1.
4. **One latch rule** (§3.1), written in `runtime/engineControl.py` and applied to every engine (C5).

Non-goals (other phases): correct-run behaviour; barrier sets and reach points; drain semantics — `idle()` vs `sync()`, the drain's pause waits, ducking (P54: C3, C4, B10); boilerplate and mixins (P45′: B1–B3, B6, B7, B11, B15, B16, including the dead `_confirmNativeQuiescence`); RHVoice's synchronous wait in `cancel` (C7); OneCore's constructor token leak (C6); readme and translations.

## 3. Design

### 3.1 The latch rule

Decided by orchestrator with the recommended default; user may override before merge. (It is cons.md's recommendation, which is already VE's ordinary path (`VE:670-676`) and SAPI5's drain (`SAPI5:156-165`).)

> **Control failures latch.** A failure of an operation whose job is to put the player or engine back into a known state — stop, purge, pause/resume, the inner engine's cancel, releasing a native resource, or a native call whose callbacks cannot be proven finished — latches the engine's control error: nothing else can reset that state, so no later speech may run on it. The engine stays unusable until its core is reloaded.
>
> **Progress failures fail only their record.** A failure while a record makes or plays its audio — opening or replacing the player, feeding, `idle()`/`sync()`, native synthesis, callback processing — is recorded on that record (`host.record_error`), which fails that segment (or ordinary sentence). The stop on that record's failure path then resets the player before any successor uses it: the drain's own stop for a failed drain wait, `wait_playback_drained`'s `stop_player` for other segment failures (`host:579-581`), `retire`'s stop for ordinary speech (`host:536-541`). Only if that stop fails is the engine latched, by the first rule.
>
> **Exception.** SAPI5 latches a failed *ordinary* request: its single COM stream cannot attribute a callback after the purge to the next request (`SAPI5:646-650`, cons.md A12).

Why this is safe for the successor: the latch protected successors from a player in an unknown state, but every progress failure is followed by a stop before the successor's first feed (FIFO retirement: `host:513-516`, `lifecycle:311-314`), and a stop that fails still latches. The rule changes only failure paths.

Known consequence (no change in this phase): a stop clears the player's pause (`nvwave.py:385-392`). If a drain wait fails while the user holds speech paused, the stop unpauses the player. The engines differ after that:

- **VE/Cerence:** a successor segment of the same utterance plays although NVDA still shows speech paused; the wrapper's pause flag (`_paused`) stays set, so that successor's drain waits for a resume. SAPI5's drain and VE's ordinary idle already behave this way today.
- **OneCore:** not affected. Each callback's `_maybeInitPlayer` pauses the player again while `_segmentPaused` is set and no stop is in flight (`OneCore:592-597`), before the successor's first feed, and that successor's drain waits for a resume; nothing is heard.

NVDA cancels a pause before any new utterance (`speech.py:1159-1160`). Pause semantics belong to P54.

Classification of every latching or recording site after this phase (before → after):

| Site | Before | After |
|---|---|---|
| eSpeak player stop (`LeasedPlayer`) | latch | latch (unchanged) |
| eSpeak native synthesis, idle | record | record (unchanged) |
| RHVoice `_WavePlayer` stop, inner `cancel`, player stop in `cancel` | latch (host API) | latch (policy) |
| RHVoice native message delete (`RHVoice:159-168`) | latch (host API) | latch (policy): native release |
| RHVoice native/callback/final idle | record | record (unchanged) |
| SAPI5 every site | as §1.4 | unchanged |
| OneCore `stop_native`, `stop_player`, playback and late-feed stops | lifecycle fault only / not latched | latch (policy, via `LeasedPlayer`) |
| OneCore `cancel` stops, `pause`, new player's pause | latch (own copy) | latch (policy) |
| OneCore segment drain `sync()` | latch | record, then stop; a failed stop latches |
| OneCore player `open()` for a segment | latch | record |
| OneCore player replacement (`_maybeInitPlayer`) | latch | record (the record's failure path stops) |
| OneCore ordinary callback (feed, `sync`, `idle`) | latch + one `DONE` | record; the sentence completes like a skipped one (`DONE` when it is the last) |
| OneCore ordinary `open()`, `ocSpeech_speak` | skip sentence | unchanged |
| VE/Cerence segment drain `idle()` | latch | record, then stop; a failed stop latches |
| VE/Cerence ordinary final idle | record | unchanged |
| VE/Cerence `_stopPlayer`, `cancel` stop | latch (host API) | latch (policy, via `LeasedPlayer`) |
| VE/Cerence callback's final stop (`VE:295-302`) | record only | removed; the late-feed stop is `LeasedPlayer`'s and latches |
| VE/Cerence `pause` | latch (host API) | latch (policy) |
| VE/Cerence `_confirmNativeQuiescence` (`VE:604-609`, a no-op today) | latch (host API) | latch (policy): unproven callback quiescence |

### 3.2 `ControlFaultPolicy` grows two phases (core, `runtime/engineControl.py`)

The policy stays NVDA-free and engine-agnostic. New API:

- `ControlFault` (frozen dataclass): `error: Exception`, `dropped: tuple[NativeRecord, ...]`.
- `ControlFaultPolicy(host, condition, drop=None, *, after=None)`. `drop` (default: drop nothing) runs under `condition` right after the latch and returns the queued records to abandon; `after(fault)` runs outside every lock once the dropped records are abandoned (in a `finally`, so it runs even if an abandon raises).
- `capture(error) -> ControlFault | None`: under `condition`, return None when a control error is already latched; otherwise `host.latch_control_error(error)`, call `drop`, `condition.notify_all()`, return the fault.
- `deliver(fault)`: no-op for None; abandon each dropped record, then `after(fault)`.
- `fail(error) -> bool`: `capture`, then `deliver` — unless the calling thread is inside `deferred()`, in which case delivery waits for the end of that block. Returns whether this call latched (as today, `control:83-96`).
- `deferred()` (context manager, re-entrant per thread): holds delivery of a fault captured on this thread until the outermost block ends. A wrapper wraps a lock it must not deliver under — OneCore's pause lock — inside this block, so the fault is captured while the lock is still held and delivered after it is released. This is OneCore's capture/deliver split (`OneCore:509-553`) made reusable.

The module docstring states the latch rule (§3.1). Lock order is unchanged: engine lock (the policy's `condition`) → host condition; `deliver` and `after` run with neither held.

### 3.3 OneCore

- **Player lease.** New `_OneCorePlayer(LeasedPlayer)` with `idle_barrier=None`. It overrides two hooks:
  - `_callback(record, on_done)` returns `on_done` unchanged: OneCore index callbacks fire while the audio plays, after the callback has closed and the worker has retired the record (`OneCore:390-392`, `host:492-495`), so a consumer-admitted wrapper would drop them. A segment's own index callback checks its work (`_segmentIndex`, `OneCore:495-497`); an ordinary one is NVDA's (`oneCore.py:521`), unchanged from today.
  - `_stop_failed(error)` → the driver's `_failSegmentControl(error)` (weak reference to the driver, as `SAPI5:201-203`).
- **Every player OneCore holds is leased.** The wrapper defines `_player` as a property over `_leasedPlayer`; its setter wraps any player that is not already a `LeasedPlayer`. NVDA writes `self._player` in its constructor and in `_maybeInitPlayer` (`oneCore.py:273`, `oneCore.py:296-301`), and every reader — NVDA's `_callback` feeds (`oneCore.py:518-528`), `_maybeInitPlayer`'s `idle()` on the old player (`oneCore.py:291-293`), the wrapper's stops, `sync()`, `open()`, `pause()` — then gets the lease; non-lease methods pass through `LeasedPlayer.__getattr__` (`host:693-694`). `_player` stays in `_OneCorePort.NVDA_PRIVATES` (still NVDA's attribute, read and written in place). A setter rather than a `_maybeInitPlayer`-only wrap also covers the constructor's `None` and a player installed directly (the test harness seeds one, `tests/onecore_drain_harness.py:265`).
- **Late-feed stops** (`OneCore:457-460`, `:488-493`, `:505-506`) are deleted; `_feedSegment` keeps only its validity checks. Feeds are admitted for the current record (`host:364-396`); inside the segment callback that is a nested admission of the record the callback already holds (`OneCore:413-417`), which `host.consumer` allows while the record still admits (`host:376-383`). The stop in `_segmentPlayback`'s `except` (discard a failed record's audio) stays and goes through the lease.
- **Control faults** use `self._controlFault = ControlFaultPolicy(host, self._segmentCondition, self._dropForControlFault, after=self._afterControlFault)`. `_dropForControlFault` (under the condition) does what capture did after the latch (`OneCore:517-525`: generation, `_wasCancelled`, stop-gate enter, legacy detection, queue clear) and returns the dropped records; `_afterControlFault` does what delivery did after the abandons (`OneCore:536-550`: stop with a log, one legacy `DONE`, then pause reset and stop-gate leave in a `finally`). `_failSegmentControl(error)` = `self._controlFault.fail(error)`. `_captureSegmentControlFailure` and `_deliverSegmentControlFailure` are removed. `_maybeInitPlayer`, `pause` and the pause-lock part of `cancel` run `with self._controlFault.deferred(), self._segmentPauseLock:`, so faults captured under the pause lock — including a lease stop failure inside `cancel`'s pause-lock block, which today escapes the block before it is latched (`OneCore:596-603`) — are delivered after the lock is released.
- **Latch rule.** Drain: a failed `sync()` (or pause wait) is recorded, then the drain stops the player; a failed stop is passed to `_failSegmentControl` (already latched by the lease; mirrors `SAPI5:160-164`). Segment `open()` failure: recorded only. `_maybeInitPlayer`: a failed admission check or player replacement is raised to the callback, whose `except` records it and stops (`OneCore:453-457`); only a failed `pause(True)` of the new player calls `_failSegmentControl`. Ordinary callback (`_legacyCallback`): a failure is recorded on its record and logged; the worker then completes that sentence like a skipped one (`_completeSkippedSentence`, `OneCore:380-388`: one `DONE` when nothing is queued and it was not cancelled), and `retire`'s stop resets the player (`host:536-541`).

### 3.4 VE and Cerence (identical changes)

- New `_CallbackPlayer(LeasedPlayer)` around `_realPlayer`, `idle_barrier=None`, built in `_installGuard` as `self._leasedPlayer`. `feed` is `LeasedPlayer`'s own: it admits the current record, which is the record the callback already holds — `_callbackAdmission` enters `host.consumer(record)`, which admits only the current record (`host:376-383`) — so the feed's admission nests inside the callback's own (`VE:635-642`). (An override admitting `host.callback_record()`, as RHVoice does, would admit the same record and call `LeasedPlayer`'s private `_feed_admitted`; see §9.) `_stop_failed` → the driver's `_failSegmentControl`.
- `_feedCallback` feeds through the lease. The callback's final stop (`VE:295-302`) is removed: a feed admitted before a cancel is stopped again by the lease (`host:712-716`); a cancel stops by itself (`VE:727-731`); a record that failed is stopped on its failure path (§3.1) before the successor's first call (the `_Retire` task precedes the next `_Begin` on the BgThread, `VE:480`, `VE:499`). `_IdleRoutingPlayer` keeps routing the ordinary final idle to `_idlePlayer` and passes every other read to the real player.
- `_stopPlayer` and `cancel` stop through the lease (its stop failure latches); their explicit `latch_control_error` calls go. `pause`'s and `_runNative`'s latches call `_failSegmentControl`. `self._controlFault = ControlFaultPolicy(self._segmentHost, self._speechStateLock)` with no drop: queued records are already abandoned by `_beginRecord` once a control error is latched (`VE:513-519`), as today.
- Drain (`VE:340-357`): a failed `idle()` (or pause wait) is recorded, then `_stopPlayer()`; its failure is passed to `_failSegmentControl` (already latched). `_idlePlayer` is unchanged.
- `tests/test_vocalizer_drift.py` `ALLOWED` stays unchanged; `_VEPort`/`_CerencePort` lists change only if a newly read inner private requires it (none is expected: `_leasedPlayer` and `_controlFault` are the wrapper's own, set in `_installGuard`/`__init__`).

### 3.5 RHVoice

`self._controlFault = ControlFaultPolicy(self._segmentHost, self._segmentCondition)` with no drop (a queued record skips its task once a control error is latched, `RHVoice:234`); `_failSegmentControl(error)`. `_WavePlayer` takes the driver (weak reference) and overrides `_stop_failed` → `_failSegmentControl`; `_NativeLibrary.cleanup` and `cancel` call `_failSegmentControl` instead of `host.latch_control_error`. A queued record's drop stays "one step late" (cons.md B4): dropping it from `ControlFaultPolicy` would race the worker's own `begin` (it waits only for `record.closed or stopGate.clear`, `RHVoice:228`), which `cancel` avoids by holding the stop gate.

### 3.6 SAPI5 and eSpeak

No code change. SAPI5 already follows the rule and uses the policy; eSpeak latches through `LeasedPlayer`'s default hook (goal 2).

## 4. NVDA user-visible changes

None on a correct run: no setting, dialog, string, barrier or event changes, and a run without failures takes the same path (the lease admits the same record the callback already holds; index callbacks are passed through unchanged).

Failure paths (only after a player or engine error, which `WasapiPlayer` rarely raises, cons.md C2):

- OneCore: a failed player stop now rejects later speech (ordinary included) until the voice is reloaded (C2). A failed drain `sync()`, segment player `open()` or player replacement now fails only that segment; the next segment plays. A failure in an ordinary sentence's callback fails only that sentence; later queued sentences still speak.
- VE/Cerence: a failed segment drain `idle()` fails only that segment; the next one plays. A failed stop of the late-feed check now latches instead of only failing the record. A failed record's audio is stopped on its failure path, a few milliseconds later than the callback's own stop did.
- RHVoice: none (the same latches, through the policy).

## 5. Settings, strings, migration

None. No new strings, so no translations.

## 6. Error handling and locks

- `LeasedPlayer.stop` latches before it re-raises (`host:754-759`); callers that also report the failure (`cancel`'s `except`, drains) call `_failSegmentControl` again, which returns False.
- OneCore lock order stays pause lock → `_segmentCondition` → host condition; `deliver`/`after` (abandons, `DONE`, player stop) never run under the pause lock. A failure sink or `DONE` listener that calls `cancel()` re-entrantly therefore cannot deadlock on the non-reentrant pause lock (pinned today by `tests/test_onecore_segment_drain.py:1123-1152`).
- VE: `ControlFaultPolicy.fail` takes `_speechStateLock` then the host condition; every caller holds neither (`pause`'s `except`, `_stopPlayer`'s stop-gate hold releases the lock before the stop, the callback thread holds only `_processingLock`).

## 7. Tests

Each behaviour change gets a test that fails on `master` first (red), then passes.

### 7.1 New and changed tests

- `tests/test_engine_control.py`: `capture` returns None once latched and calls `drop` under the condition; `deliver` abandons outside the lock then calls `after`, also after an abandon raises; `deferred` holds delivery until the outermost block ends and delivers outside a lock taken inside it; `fail` keeps its return value.
- `tests/test_onecore_segment_drain.py`:
  - C2: a failing `stop_player` latches `control_error`; ordinary speech is then rejected.
  - Lease: the player is a `LeasedPlayer` after construction, after a seed and after a sample-rate replacement; index callbacks fire after the record retired (drain still waiting); a feed admitted before `cancel` is stopped once more by the lease before the successor's native call (existing `test_cancelled_legacy_feed_retires_only_after_its_final_stop`, plus a segment variant).
  - Rule: drain `sync()` failure fails only that segment, stops the player, the successor drains (replaces `test_onecore_shared_sync_fault_rejects_successor_without_native_call`, `test_onecore_sync_fault_fails_accepted_queued_segment`); a drain stop failure after a `sync()` failure latches; segment `open()` failure fails only its segment (replaces `test_segment_player_open_failure_still_latches`); player-replacement failure fails only its segment; ordinary callback failure fails only its sentence and still completes; `test_onecore_rejected_segment_uses_async_lifecycle_delivery` latches by a stop failure instead of a sync failure.
  - Pause lock: a lease stop failure inside `cancel`'s pause-lock block is delivered after the lock is released (the `after` hook can take the pause lock).
  - The held-delivery tests (`:418-465`, `:1326-1351`) hold `_controlFault.deliver` instead of the removed method.
- `tests/test_vocalizer_segment_drain.py` (VE and Cerence): drain `idle()` failure fails only that segment, stops the player, the successor drains (replaces `test_player_failure_rejects_successor_with_context`); a drain stop failure after it latches; a late feed after `cancel` is stopped by the lease and a failure of that stop latches; feeds go through a `LeasedPlayer`.
- `tests/test_rhvoice_segment_drain.py`: the existing latch tests keep passing through the policy; one test pins that `_WavePlayer`'s stop failure goes through `_failSegmentControl`.
- Guards (`tests/test_native_strategy_guards.py`): no wrapper calls `latch_control_error`; RHVoice, SAPI5, OneCore, VE and Cerence each build exactly one `ControlFaultPolicy`; OneCore's and VE/Cerence's player classes subclass `LeasedPlayer`; OneCore and VE/Cerence call no raw `feed`/`stop` on a player outside `LeasedPlayer`.
- `tests/test_hygiene_guards.py` `_REASONS`: the `latch_control_error` keys become `_failSegmentControl` keys (no wrapper handler names the host API any more).

### 7.2 Mutants (scratch copies; result recorded in the progress ledger)

1. OneCore drain still calls `_failSegmentControl` on a `sync()` failure → the successor test fails.
2. OneCore/VE drain records but does not stop → the "stopped before the successor" assertion fails.
3. `LeasedPlayer._feed_admitted` without its late stop → the OneCore and VE late-feed tests fail.
4. `_OneCorePlayer._stop_failed` → `pass` → the C2 test fails.
5. `ControlFaultPolicy.fail` ignores `deferred()` → the pause-lock delivery test fails (or deadlocks within its timeout).
6. `_OneCorePlayer._callback` wraps `on_done` in `host.consumer(record)` → the index-after-retire test fails.
7. `_player` setter does not wrap → the lease-identity tests fail.

`runtime/engineControl.py` is core: run `mutmut` on it (adding it to `source_paths` only in the scratch copy) and record surviving mutants with reasons.

### 7.3 Windows / NVDA (not verified on Linux)

Failure paths need a real device fault and are not practical to provoke by hand; correct-run smoke only: OneCore, VE, Cerence and RHVoice multi-language reading with indexes (say all), cancel mid-sentence, pause/resume. Linux tests exercise only the controlled native and audio boundaries.

## 8. Open questions

- The latch rule (§3.1): Decided by orchestrator with the recommended default; user may override before merge.
- Pause/resume failures stay control failures (latch), unchanged from today; native resource release (RHVoice message delete) and unproven callback quiescence (VE) likewise. Decided by orchestrator with the recommended default; user may override before merge.
- OneCore ordinary callback failure now completes its sentence instead of latching (follows from the rule; the ordinary path is unreachable in production, cons.md §4). Decided by orchestrator with the recommended default; user may override before merge.

## 9. Implementation notes

Plan: `docs/superpowers/plans/2026-10-29-phase53-player-control-fault.md` (8 tasks, one run). Ledger rulings (`.superpowers/sdd/2026-10-29-phase53-player-control-fault/progress.md`) in short:

- `ControlFaultPolicy.deferred()` delivers only a captured fault at the end of the block; delivering `None` there ran a patched `deliver` on every fault-free cancel (Task 3; one more unit test).
- `LeasedPlayer._feed_admitted` passes `size` and `onDone` only when its caller did (`host:702-716`). The inner VE callback feeds bare data (`player.feed(data)`), and the lease used to add `onDone=None`; real `nvwave.WavePlayer.feed` accepts both forms (Task 5).
- VE/Cerence `_CallbackPlayer` keeps `LeasedPlayer`'s default feed admission (the current record) instead of admitting `host.callback_record()` as §3.4 says: the callback's record is the current one (`_callbackAdmission` enters `host.consumer(record)`, which requires it to be current), and an override would call `LeasedPlayer`'s private `_feed_admitted`, which the VE inner-privates guard counts (Task 5).
- After a failed drain wait the lifecycle stops the player as well (`request_stop` → `stop_native`, then a second `wait_playback_drained` → `stop_player`), so the drain's own stop is the earliest of several; it is kept to match SAPI5 and §3.1 (Task 6; mutant M2a below).
- When the drain's stop also fails, the failed segment's event carries the stop error: `latch_control_error` fails accepted operations first (`host:451-452`) (Task 6).
- `tests/test_hygiene_guards.py` `_REASONS`: the `latch_control_error` keys became `_failSegmentControl` keys as the handlers moved (Tasks 4, 6, 7).

Mutants (§7.2, swapped into the worktree file and restored): M1, M4, M5, M6, M7 (OneCore), M2b and M8 (VE) killed by the named tests. M2a (OneCore drain without its own stop) survives: the lifecycle's own stops cover it. M3 (`LeasedPlayer` without the late-feed stop) is killed by `tests/test_espeak_segment_drain.py::test_cancelled_feed_final_stop_finishes_before_successor_native_call` and, since the review fixes, by the OneCore and VE/Cerence late-feed tests, which now require a stop on the callback thread that fed. For OneCore and VE/Cerence the host and lifecycle also stop a cancelled record before its successor (`stop_native`, `retire` for ordinary speech, `wait_playback_drained` for segments), so the lease's late stop is the earliest one there, not the only one.

`mutmut` 3.8.0 on `runtime/engineControl.py` (scratch clone, `source_paths` narrowed to that file, tests narrowed to `test_engine_control.py` and the five engine drain files, 2 children, memory watchdog): 53 mutants, 52 killed, 1 survived — `ControlFaultPolicy.fail` with `getattr(local, "depth", None)` instead of `0`, an equivalent mutant (both defaults are falsy). With the whole suite selected, mutmut's stats run fails on an unrelated test (`test_config_stub.py::test_pipeline_defaults_match_the_confspec_the_add_on_registers`, `NameError: _mutmut_mutated`), and a `ref` symlink in the clone stalls mutant generation; the narrowed run links `ref` only after generation.

Verification at the last commit: 3596 passed, 0 skipped (baseline 3566 + 30 new tests); `prek run --all-files` all Passed; `git diff --check` clean; protected-path commands empty. Linux tests exercise only the controlled native and audio boundaries; Windows/NVDA not verified.
