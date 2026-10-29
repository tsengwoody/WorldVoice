# Phase 54: drain semantics (pause at segment boundaries; OneCore ducking open question)

Date: 2026-10-29.
Base: `master` `5d836bd` (P45′ merged). Branch: `phase54-drain-semantics`. Normal flow (DEVELOPMENT_WORKFLOW.md §3).
Source: the consistency audit `cons.md` (C3, C4, B9, B10) and `storage/refactor9.md` row P54.

Status of the three items:

| Item | Decision | This phase |
|---|---|---|
| C3 + B10: the unpause wait at segment boundaries | Decided by the user (2026-10-29): move the wait into the runtime, remove OneCore's and VE/Cerence's own waits | Implemented (§2) |
| C4: OneCore segment drain never `idle()`s, so ducking is not released | Decided by the user (2026-10-29), first round: OneCore drain calls `idle()` per segment. **Withdrawn by the user (2026-10-29), second round:** do not release ducking between segments; investigate releasing it only when speech ends | Open question, not implemented (§3) |
| B9: drain-support profile naming | Unify only if a pure rename | Dropped: not a rename (§4) |

Line conventions: `OneCore:191` is `addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py` line 191 (likewise `VE:`, `Cerence:`, `SAPI5:`, `Espeak:`, `RHVoice:`); `scheduler:` is `runtime/scheduler.py`; `host:` is `runtime/segmentHost.py`; `lifecycle:` is `runtime/_segmentLifecycle.py`; `inner-RHVoice:` / `inner-VE:` are `driver/<Engine>/driver/__init__.py`; NVDA paths are under `ref/nvda/`.

## 1. Background: where pause flows today

- NVDA: `speech.pauseSpeech(switch)` calls `getSynth().pause(switch)` and only then sets `_speechState.isPaused = switch` (`ref/nvda/source/speech/speech.py:236-240`); if the synth raises, NVDA's paused state is unchanged. `cancelSpeech()` calls `_manager.cancel()` → `getSynth().cancel()` and clears `isPaused` (`speech.py:217-233`, `ref/nvda/source/speech/manager.py:768-770`). Any new `speak()` while paused cancels first (`speech.py:1159-1160`). `pauseSpeech` resets `beenCanceled` (`speech.py:240`), so the first `cancelSpeech` after a pause always reaches the synth.
- WorldVoice: `SynthDriver.pause` → `TaskManager.pause_current(switch)` (`addon/synthDrivers/WorldVoice/__init__.py:337-340`); `SynthDriver.cancel` → `VoiceManager.cancel` → `TaskManager.cancel(playback_ports)` (`__init__.py:332-335`, `voices/manager.py:255-257`).
- `pause_current` keeps **no state**: it forwards `switch` to the current task's playback only when that task is valid and in `STARTING` or `AWAITING_COMPLETION` (`scheduler:454-465`), then `EngineSession.pause` → `VoiceClassAdapter.pause` → `core.pause` (`runtime/session.py:191-192`, `bridge/engineAdapter.py:196-197`). A pause with no current task, during a break task (`playback is None`) or in `FINISHING` is dropped.
- Engines: `WasapiPlayer::pause` only stops the client; `playState` stays `playing`, so `sync()` keeps waiting while paused (`ref/nvda/nvdaHelper/local/wasapi.cpp:620-634`, `:650-659`); `WavePlayer.idle()` is `sync()` plus side effects (`ref/nvda/source/nvwave.py:376-382`). So a pause that lands **before** the segment's audio has played out holds every engine's drain naturally.
- Engine-level unpause waits exist only in two drains: OneCore waits on `_segmentPaused` after `sync()` (`OneCore:197-200`); VE/Cerence wait on `_pauses == 0 and not _paused` after `idle()` (`VE:352-357`, `Cerence:352-357`). SAPI5's drain (`SAPI5:142-158`), eSpeak's NVDA-callback idle (`ref/nvda/source/synthDrivers/_espeak.py:172-176`) and RHVoice's worker idle (`RHVoice:258`) do not wait.

## 2. C3 + B10: the runtime holds segment boundaries while paused

C3 is independent of the C4 outcome (§3): it neither changes which player call proves `PLAYED_OUT` (`idle()` or `sync()`) nor adds an end-of-speech call; every C4 option keeps the scheduler holds below.

### Problem

A pause that lands after the engine's `sync()`/`idle()` returned and before the scheduler starts the next task is lost for SAPI5, eSpeak and RHVoice: `PLAYED_OUT` is reached, `SEGMENT_DRAINED` completes the task, and the scheduler starts the next segment — possibly on another engine whose player was never paused — so speech continues after the user pressed pause (cons.md C3). OneCore and VE/Cerence hold the boundary, each with its own pause state. A pause with no current task (between tasks, or during a break task) is dropped for every engine.

The P53 consequence deferred here (`docs/superpowers/specs/2026-10-29-phase53-player-control-fault-design.md:69-74`): if a drain wait fails while the user holds speech paused, the failure-path stop unpauses the player (`nvwave.py:384-392`). The failed segment fails its request (`runtime/completion.py:53-54`, `scheduler:494-500`), the scheduler reports DONE for the failed request (`scheduler:373-384`), and NVDA's speech manager may then push queued speech (`manager.py:717-730`) without a cancel; on VE/Cerence that speech plays although NVDA shows speech paused (P53 spec: "a successor segment ... plays").

### Is the runtime's pause state reliable?

Yes, once the scheduler keeps one. Verified:

- Every NVDA pause/resume reaches `pause_current` (`__init__.py:337-340`); after `terminate` the driver ignores it.
- Every NVDA path that clears `isPaused` cancels the synth first (`speech.py:217-233`, `:1159-1160`), which reaches `TaskManager.cancel` (`voices/manager.py:255-257`). A synth switch terminates the driver, which shuts the scheduler down (`scheduler:467-477`).
- When `synth.pause` raises, NVDA keeps its old paused state (`speech.py:237-239`). The scheduler must do the same: restore its previous state before re-raising, or a failed `pause(True)` would hold speech forever while NVDA believes it is not paused.

### Where the wait goes

Decided by the user (2026-10-29): the wait moves into the runtime and keys on the runtime's own pause state; OneCore's and VE/Cerence's own drain waits are removed.

The user's wording placed it "after the strategy's drain returns and before `SEGMENT_DRAINED` is published". The per-engine `SegmentHost` that publishes the event has no access to the session's pause state: wiring one in would need a new argument on `SegmentDrainCore.speak_segment` (`host:139-148`), the interface the external Neural plugin implements. The scheduler is the only runtime component that sees every pause and every segment. So the wait sits where `SEGMENT_DRAINED` takes effect: the scheduler does not finish a completed task, and does not start a task, while paused. For the next segment this is the same as delaying the event (the scheduler runs one task at a time, `scheduler:479-487`); the engine's lifecycle resource is released while the scheduler waits, which no one else can use. Decided by orchestrator with the recommended default; user may override before merge.

### Design (`runtime/scheduler.py`, `TaskManager`)

State, under `_state_cond`: `_paused: bool` (the session's pause state) and `_pause_target: PlaybackPort | None` (the playback that last accepted a forwarded `pause(True)`).

`pause_current(switch)`:

- Closed scheduler: no-op.
- `switch=True`: remember the previous `(_paused, _pause_target)`; set `_paused = True`. Forward to the current task's playback only when today's rule holds (`scheduler:456-463`) **and** the task's completion is not yet ready (`_completion_ready_locked`); a completed task's engine is idle, and pausing an idle WASAPI player and later resuming it would re-enable that player's ducker with nothing playing (`nvwave.py:396-404`). When forwarded, `_pause_target` = that playback. Forwarding runs outside the state lock (as today). If it raises, restore the previous state, then re-raise.
- `switch=False`: forward to `_pause_target` if set, else by today's rule (a resume NVDA sends without a prior pause keeps today's behaviour). The forward runs **before** the state clears, so a successor on the same engine never starts before that engine resumed. If it raises, the scheduler stays paused (NVDA's `isPaused` also stays `True`); otherwise clear `_paused` and `_pause_target` and `notify_all`.

`cancel()` clears `_paused` and `_pause_target` in its locked block (`scheduler:432-438`); the engines' own cancel resets their pause state (`OneCore:579-582`, `VE:688-692`, `WavePlayer.stop` clears `_isPaused`, `nvwave.py:392`). `cancel_current()` does not clear the pause: NVDA never calls it, and the pause remains NVDA's. `shutdown()` cancels.

Holds:

1. **Completion hold** (`_execute`, after `done.wait()`, `scheduler:554`): under `_state_cond` only, wait while `_paused and _valid_locked(task)`; then the existing final check under delivery lock + state (`scheduler:557-565`). The wait must not hold `_delivery_lock`: `cancel()` takes it first (`scheduler:432`). It applies to every completion contract; a failed task (`task.error`) skips the hold through the final check only after resume — acceptable: a failure while paused is reported when the user resumes or cancels.
2. **Start hold** (`_acquire`, `scheduler:505-520`): wait while `_stops_in_flight or (_paused and _valid_locked(task))`. Covers a pause between tasks, during a break task, and the P53 consequence (the next utterance waits until resume or cancel).

Wake-ups: resume (`notify_all`), `cancel()`/`cancel_current()` (`_wake_current_locked`, `scheduler:397-400`), `shutdown()` via cancel. A public `Future.cancel()` of the waiting task must also wake the completion hold: its done-callback (`scheduler:545`) additionally notifies `_state_cond` (the condition's lock is an `RLock`, so a callback on a thread that already holds it cannot deadlock).

Engine changes:

- OneCore drain: drop the `_segmentPaused` wait (`OneCore:197-200`). `_segmentPaused` stays for re-pausing a new player (`OneCore:567-572`) and the ordinary path (`OneCore:490-502`).
- VE and Cerence drain: drop the `_pauses`/`_paused` wait (`VE:352-357`, `Cerence:352-357`), identically in both files, so `tests/test_vocalizer_drift.py` `ALLOWED` is unchanged. `_paused`/`_pauses` stay for the ordinary `_idlePlayer` (`VE:653-658`) and the record waits (`VE:502`, `:524`, `:570`, `:595`).
- `runtime/barriers.py`: `PLAYED_OUT` is proven by `idle()` (or OneCore's `sync()`) returning; a pause after that is the scheduler's.

Non-goals: the ordinary-speech unpause waits (OneCore `_legacyCallback`, VE/Cerence `_idlePlayer`) are not drains and stay (the ordinary path is unreachable in production, cons.md §4; the scheduler's hold also covers `LEGACY_DONE` tasks). Pausing a break task's timer (a break keeps counting during a pause; the next task then waits).

### Does this cover the P53-deferred consequence?

Yes for the case described. The failed VE segment's request fails; NVDA pushes the next utterance; its first task waits in `_acquire` while `_paused`; resume forwards `pause(False)` to `_pause_target` (VE, clearing `_paused`) and then releases it. On OneCore the same happens; `_segmentPaused` is cleared by that forwarded resume before the successor's first `_maybeInitPlayer`, so the successor's player is no longer re-paused.

### Interaction with P53 failure paths and cancellation

- Drain failure during a pause: unchanged in the engine (record error, stop, latch only on a failed stop). The task fails without the completion hold blocking the failure from being recorded; its request fails after resume or cancel; the next task waits.
- Cancel/terminate/reset: `cancel()` clears the pause and wakes both holds (tasks become invalid by epoch). Engine `reset()` (SAPI5 reload) happens under the session, not the scheduler; the pause stays NVDA's.

### What NVDA users hear or see

- Pausing exactly as one language segment ends no longer lets the next segment (possibly in another voice or engine) play; speech resumes with that segment on resume. Previously SAPI5, eSpeak and RHVoice segments, and every segment after a break or between segments, could continue.
- Unchanged: pause/resume in the middle of a segment, cancel while paused, new speech while paused (NVDA cancels first).

### Error handling

A raised engine pause/resume keeps P53's rule (control failures latch, `runtime/engineControl.py`), re-raises to NVDA, and leaves the scheduler's pause state as NVDA's.

### Tests

Unit (`tests/test_runtime_scheduler.py`, DRAIN-contract `FakePlayback`): pause after the drain event holds completion and the next task until resume; resume forwards to the paused engine before the next task starts; pause with no current task / during a break holds the next task; cancel releases both holds and clears the state; a cancelled Future releases the completion hold; a raising `pause(True)` restores the state; a raising `pause(False)` keeps it; a completed task is not forwarded a pause; the existing `test_pause_current_uses_valid_playback` is rewritten (its first pause with no task now holds). Engine (`tests/test_onecore_segment_drain.py`, `tests/test_vocalizer_segment_drain.py`): the drain reports `SEGMENT_DRAINED` while the engine is paused (the old "drain waits for resume" tests are replaced). No mutmut (the scheduler change is a small state machine covered by direct tests).

Windows manual checks (not verifiable on Linux):

1. Multi-language say-all mixing SAPI5 + OneCore and eSpeak + VE; press pause (Shift) right as a segment ends, repeatedly; speech must stop and resume at the next segment.
2. Pause during a long punctuation/number break, then resume.
3. Pause, wait, then a new key echo (NVDA cancels): no stale segment plays.
4. Pause during a failing drain (needs a device fault; best effort): after the failure, nothing plays until resume.

### Readme

User-visible: one entry in the next-version changelog of all six readmes (root `readme.md`, `addon/doc/{ru,uk,zh_CN,zh_HK,zh_TW}/readme.md`). zh_TW: 「修正在語言段落交界時暫停，下一段語音仍會繼續播放的問題。」 English: "Fixed speech continuing with the next language segment when paused right at a segment boundary."

## 3. C4: OneCore ducking — open question (not implemented)

The user's second-round decision (2026-10-29): do not release ducking between segments; release it only when speech actually ends. This section is the investigation the user asked for. Nothing in §3 is implemented in this phase.

### 3.1 What `idle()` and `sync()` do in NVDA

- `WavePlayer.sync()` waits for fed audio to play (`nvwave.py:370-374` → `wasapi.cpp:620-634`).
- `WavePlayer.idle()` = `sync()` + re-arm leading-silence trimming (`startTrimmingLeadingSilence()`, when enabled for speech) + `self._audioDucker.disable()` (`nvwave.py:376-382`). In this NVDA it does **not** call the C++ `wasPlay_idle` (which also stops the stream, `wasapi.cpp:637-648`); only the idle timer does (`nvwave.py:484-523`), and that timer never touches the ducker. NVDA's #10721 comment about `idle()` closing the device (`ref/nvda/source/synthDrivers/oneCore.py:434-439`) describes the old WinMM player.
- `feed()` enables the ducker (`nvwave.py:331-332`); `stop()` and `pause(True)` disable it, `pause(False)` enables it (`nvwave.py:384-404`).
- Trimming: while armed, the next fed chunk's leading silence is skipped and one silent frame inserted, then trimming stops until re-armed (`wasapi.cpp:344-361`); a `BreakCommand` at the start of the NVDA utterance turns it off for that utterance (`nvwave.py:338-339`, `:527-534`). WorldVoice's own pauses are scheduler break tasks, not audio (`bridge/commands.py:15-16`, `runtime/requestBuilder.py:48`), so trimming never removes them.
- **Ducking release is delayed by one second.** Each player owns an `AudioDucker` (`nvwave.py:234-239`). `disable()` does not unduck: it schedules the global ref-count decrement 1000 ms later (`ref/nvda/source/audioDucking.py:252-266` → `_unensureDucked`, `:123-146`); `enable()` increments at once (`:208-222` → `_ensureDucked`, `:109-121`). Ducking is a global ref count (`audioDucking.py:64`, `:141-142`), so other audio is unducked only when every player has been disabled for a full second.

Consequence: **an `idle()` at a segment boundary does not release ducking between segments** when the next segment starts feeding within one second; other audio stays lowered across the boundary and is restored one second after the last segment's idle. The other five engines idle at every segment boundary today, and other audio is not audibly restored between their segments for this reason. What `idle()` per segment changes audibly is trimming: each segment's leading silence is trimmed.

### 3.2 What "between segments" means across engines

Each engine has its own player(s) and its own `AudioDucker`: eSpeak's module player (`Espeak:79`), RHVoice's per-sample-rate inner players (`inner-RHVoice:189-198`, wrapped at `RHVoice:348-359`), SAPI5's `self.player` (`SAPI5:473-474`, `:490`), OneCore's `_player` (rebuilt on sample-rate change, `oneCore.py:283-301`), VE/Cerence's `_realPlayer` (`VE:448-451`). An engine switch therefore always changes players. With the global ref count, ducking stays on across a switch as long as either player is enabled or within the one-second grace.

### 3.3 Where each engine idles today, and whether it could sync between segments instead

| Engine | Idle site at a segment boundary | Who owns the call | Could become sync-between / idle-at-end? |
|---|---|---|---|
| eSpeak | NVDA's `_espeak.callback` calls `player.idle()` when synthesis of each `speak` ends (`_espeak.py:172-176`) | NVDA module, but `_espeak.player` is the wrapper's `LeasedPlayer` (`Espeak:79`) | Yes, in the lease: its `idle()` (`host:758-770`) could call the real `sync()` and still reach `PLAYED_OUT`; the real `idle()` would come from an end-of-speech hook |
| RHVoice | Inner idles per message (`inner-RHVoice:409`) and in its done callback (`inner-RHVoice:348`); the wrapper idles once more after the record (`RHVoice:258`) | Inner driver (protected), but every inner player is the wrapper's `_WavePlayer` (`RHVoice:171-218`, installed via `get_player`, `RHVoice:348-359`) | Yes, in `_WavePlayer.idle` (`RHVoice:210-216`), without touching the inner driver |
| SAPI5 | Segment drain `player.idle()` (`SAPI5:149`); NVDA's own worker idles only when its queue is empty (`ref/nvda/source/synthDrivers/sapi5.py:869-871`) | Wrapper | Yes (drain) |
| OneCore | Segment drain `sync()` only (`OneCore:196`); NVDA's own `_processQueue` idles only when its queue is empty (`oneCore.py:430-448`) | Wrapper | Already sync-between; needs only the idle-at-end |
| VE/Cerence | Segment drain `_realPlayer.idle()` (`VE:351`); inner `DoneSpeaking` idles per ordinary sentence (`inner-VE:228-237`, routed through `_IdleRoutingPlayer`, `VE:96-117`) | Wrapper | Yes (drain) |

So no engine is blocked by a protected inner driver: all idle calls reach a wrapper-owned player object.

### 3.4 How the end of speech could be known

- A drain cannot know whether its segment is the last: the next task may be on another engine, a break, or the next NVDA utterance.
- The scheduler knows: a request's remaining tasks (`scheduler:597-614`) and whether its queue is empty. NVDA's own OneCore/SAPI5 idle when their queues empty (`oneCore.py:430-448`, `sapi5.py:869-871`); NVDA's speech manager pushes the next utterance at the end-of-utterance index (`manager.py:700-715`), so during say-all their queue rarely empties between lines.
- A runtime end-of-speech hook would need a new optional core entry (e.g. `finish_speech()`), called by the scheduler on each engine the request used, on its worker, after the last task settles (or when its queue is empty), and skipped for a core that lacks it (the Neural plugin).

### 3.5 Options

| Option | What changes | User-visible effect | Size / risk |
|---|---|---|---|
| A. OneCore drain `idle()` per segment (the first-round decision) | One call in `OneCore` drain | Other audio is restored about one second after OneCore stops speaking, never between segments that follow within a second (§3.1); each OneCore segment's leading silence is trimmed like the other five engines (slightly tighter OneCore-to-OneCore transitions) | S; Windows listening check for clipped starts |
| B. OneCore: sync between segments, idle at end of speech | Runtime end-of-speech hook (§3.4) + OneCore entry | Ducking restored ~1 s after speech ends; OneCore segments keep today's untrimmed starts | M; new optional core interface |
| C. All six: sync between segments, idle at end | Option B for all engines (eSpeak lease, RHVoice `_WavePlayer`, SAPI5/VE drains) | Same ducking result as A/B; leading silence no longer trimmed at segment starts for the five engines that trim today (audible: longer gaps between segments) | M–L; changes all engines' segment transitions |
| D. Leave as is, document | `barriers.py` / `syn.md` note | Other audio stays lowered after OneCore speech until the next cancel or pause | none |

Implementation note for any option that idles from a drain or an end-of-speech hook: OneCore's `_player` is a `LeasedPlayer` with `idle_barrier=None` (`OneCore:101-110`), and `LeasedPlayer.idle()` first enters `host.consumer()` and returns `None` without calling the real `idle()` when no record is admitted (`host:758-762`). The drain runs on the lifecycle thread after the record retired (`host:510-533`, `host:591-601`), so `self._player.idle()` there would silently do nothing while the drain still reaches `PLAYED_OUT` (`OneCore:211`). The call must go to the underlying player (`player._player.idle()`, as SAPI5's final feed does at `SAPI5:602`, or VE's `driver._realPlayer.idle()` at `VE:351`), and its test must prove the real `idle()` ran (e.g. the fake player records the call).

**Recommendation: A.** The concern behind the second-round decision — ducking released between segments — does not happen with `idle()` because NVDA delays unducking by one second (`audioDucking.py:123-146`); A gives exactly "release only when speech actually ends" (plus one second) with a one-line change, and matches the other five engines and NVDA's per-utterance eSpeak. B gives the same ducking result with a new interface; C changes every engine's transitions. Stop-and-ask: the user decides between A–D before any C4 change.

## 4. B9: drain-support profile naming — dropped

`cons.md` §4 proposes `runtime_profile(Voice.engine, nvda_version, audio_mode)` for all six. That is not a pure rename (DEVELOPMENT_WORKFLOW §3.2 rename proof): it changes string values, not identifiers. eSpeak would change from `"espeak/…"` to `"Espeak/…"` (`Espeak:152`); SAPI5's static `"sapi5-wasapi"` / `"sapi5-legacy-audio"` (`SAPI5:418`, `:422`) and VE/Cerence's `_PROFILE` (`VE:42`, `Cerence:42`, carrying the SDK API `ttsapi-0x0520` / `ve2` marker) would lose information. The profile only appears in the `LEGACY_DONE` fallback warning, which already logs engine, NVDA version and audio mode (`bridge/completionPolicies.py:48-55`). Not done; reported to the user.

## 5. Constraints

- `runtime/` stays NVDA-free; no change to `driver/*/driver/*`, `driver/sonic/`, generated Unicode data; no Neural; each driver independently installable; VE and Cerence identical (drift `ALLOWED` unchanged).
- ruff `0.16.3`; prek hooks.

## 6. Open questions

1. C4: option A, B, C or D (§3.5). Stop-and-ask; recommended A.
2. The completion hold also delays a failure report until resume or cancel (§2). Decided by orchestrator with the recommended default; user may override before merge.
