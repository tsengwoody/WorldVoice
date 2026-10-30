# Phase 55: the remaining audit C items (C1, C6, C7)

Date: 2026-10-29.
Base: `master` `b768c57` (P54 merged). Branch: `phase55-c-items`. Normal flow (DEVELOPMENT_WORKFLOW.md §3).
Source: the consistency audit `cons.md` (§8 C1, §1 C6, §5 C7, the summary table and its recommendations). Its line numbers are for `9d96ace`; every line below was re-located on `b768c57`.

| Item | Decision | This phase |
|---|---|---|
| C1: RHVoice emits an anonymous `synthDoneSpeaking` per segment | Fix: segment records no longer notify DONE; ordinary speech unchanged | Implemented (§1) |
| C6: a failing OneCore constructor leaks the native token | Fix: release the token NVDA's constructor created, newest first | Implemented (§2) |
| C7: RHVoice `cancel()` waits for its worker | **Keep the wait** and the post-settle stop; document what each protects (§3.4). Decided by orchestrator with the recommended default; user may override before merge | Comments + pinning tests (§3) |

Line conventions: `RHVoice:383` is `addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py` line 383 (likewise `OneCore:`, `SAPI5:`); `inner-RHVoice:` is `driver/RHVoice/driver/__init__.py`; `host:` is `runtime/segmentHost.py`; `lifecycle:` is `runtime/_segmentLifecycle.py`; `scheduler:` is `runtime/scheduler.py`; NVDA paths are under `ref/nvda/`.

## 1. C1: RHVoice segments notify `synthDoneSpeaking`

### Problem

`_nativeCallback` passes RHVoice's done callback straight to the inner `DoneCallback` (`RHVoice:370-392`, call at `:383`), which runs `player.on_done()`, `player.idle()` and then `synthDoneSpeaking.notify(synth=<wrapper>)` (`inner-RHVoice:343-353`). Nothing distinguishes a segment record from ordinary speech, so every segment notifies an anonymous DONE. The other five engines suppress DONE for segments (cons.md §8 table; e.g. eSpeak only notifies for ordinary records, `Espeak:207`; OneCore at `OneCore:410`, `:503`, `:545` only on ordinary paths).

Today nobody consumes it: segments are spoken only through `SpeakEntry.SEGMENT` rules, all correlated (`runtime/completion.py:86-106`); the bridge drops DONE for correlated bindings (`bridge/nvdaEvents.py:232-235`); NVDA's speech manager ignores DONE from anything but `getSynth()` (`ref/nvda/source/speech/manager.py:717-720`), and the RHVoice core is not NVDA's synth. So it is harmless, but it is the only exception to "segments emit no DONE", costs one notify per segment on the RHVoice worker, and would mislead a future plain fallback or external listener.

### Design (`driver/RHVoice/__init__.py`)

- In `_nativeCallback`, when `isDone` and `record.operation is not None` (a segment record; ordinary records have no operation, `host:344-359`), do not call the inner `DoneCallback`. Run its player steps instead, through the port: a new `_RHVoiceInner.segmentDone()` that mirrors `DoneCallback.__call__` minus the notify:
  - if `cancelFlag` is set, return (the inner's first check, `inner-RHVoice:345-346`);
  - `player.on_done()` then `player.idle()` (`inner-RHVoice:347-348`); `on_done`/`idle` are public methods of the inner `AudioPlayer` (`inner-RHVoice:253-266`), reached through the existing `_RHVoiceInner.player` property (`RHVoice:45-47`). The inner's second cancel check (`:349-350`) only gates the notify and goes with it.
- `host.reach(record, ENGINE_DONE)` stays exactly where it is (after the call returns, `RHVoice:384-385`).
- Errors: the inner `DoneCallback` swallows and logs any exception (`inner-RHVoice:352-353`), after which the wrapper reaches `ENGINE_DONE`. On the segment path an exception from `on_done()`/`idle()` now reaches `_nativeCallback`'s existing handler, which records it on the record and returns the refused value (`RHVoice:389-391`), so `ENGINE_DONE` is not reached. For failures in `_WavePlayer.feed`/`idle` the segment outcome is unchanged: they are already recorded on the record before they propagate (`host:724-730` via `_WavePlayer.feed`, `RHVoice:210-216` for idle), so the segment failed before too, with the same first error. The one exception is player creation: `on_done()`/`idle()` reach `AudioPlayer.get_player()` → `do_get_player()`, which builds the `nvwave.WavePlayer` and reads `outputDeviceSection` (`inner-RHVoice:189-198`) before any `_WavePlayer` exists, so its error was never recorded on the record. Before, the inner swallowed it, the wrapper reached `ENGINE_DONE`, and if the final idle in `_QueuedSpeech` then created the player successfully the segment reported `SEGMENT_DRAINED` although its held-back last chunk was never played. Now that error is recorded and the segment reports `SEGMENT_FAILED` (review M2). This is the more correct outcome, not a regression, and needs no code change. Apart from that, only the inner's `log.error("RHVoice done callback")` line is gone for segments.
- Ordinary speech (`operation is None`) still calls the inner callback, so its DONE, `on_done()` and `idle()` are exactly as today.
- The inner driver is not modified.

### What NVDA users hear or see

Nothing. Audio, indexes and `SEGMENT_DRAINED` timing are unchanged (`on_done()` still feeds the held-back last chunk before `idle()`, `barriers.py:17-19`). NVDA never saw the extra DONE.

### Tests (`tests/test_rhvoice_segment_drain.py`)

- New `test_a_segment_and_an_ordinary_utterance_notify_exactly_one_done` (mirror of `tests/test_espeak_segment_drain.py:445-471`): a segment drains with `env.dones == []`, then one ordinary utterance → `env.dones == [env.driver]`.
- `test_ordinary_speech_waits_for_contextual_final_idle` (`:768-800`): drop the `dones_before` tolerance; assert `env.dones == []` while the segment drains and `env.dones == [env.driver]` after the ordinary utterance.
- `test_legacy_done_callback_can_cancel_without_deadlocking_worker` (`:294-307`) spoke a **segment** and only worked because segments notified DONE; it becomes ordinary (legacy) speech, which is what its name and purpose describe.
- `test_legacy_speak_keeps_inner_settings_snapshot_and_queue` (`:382-396`) keeps asserting the ordinary DONE.

## 2. C6: OneCore constructor failure leaks the native token

### Problem

`SynthDriver.__init__`'s failure branch releases only the segment host; its comment says "a native token NVDA's constructor left cannot be" released (`OneCore:244-252`). But NVDA's constructor creates the callback trampoline and the token early (`ref/nvda/source/synthDrivers/oneCore.py:268-270`) and can still raise afterwards, e.g. at `self.voice = self._getDefaultVoice()` (`oneCore.py:280`, which calls `ocSpeech_setVoice`, `oneCore.py:620-627`). NVDA's own `terminate` releases exactly these: it sets `_earlyExitCB`, calls `self._dll.ocSpeech_terminate(self._ocSpeechToken)` and drops the token and trampoline (`oneCore.py:303-312`). `VoiceClassAdapter.open` gets no core to terminate when the constructor raises (comment at `OneCore:245-247`), so the token leaks once per failed start.

SAPI5 already releases what its parent built, conditionally: "once `_initWasapiAudio` built a player, NVDA's terminate ..." (`SAPI5:392-406`).

### Design (`driver/OneCore/__init__.py`)

- In the `except BaseException` branch, build the release list like SAPI5: `[self._segmentHost.terminate]`, plus a new `self._releaseParentNative` when NVDA's constructor got as far as its callback trampoline (`getattr(self, "_callbackInst", None) is not None`). `release_newest_first` (`runtime/engineControl.py:176-186`) runs it first, logs a raising release with "WorldVoice OneCore initialization cleanup failed" and still releases the host; the original error is re-raised.
- `_releaseParentNative()` (mirrors NVDA's `terminate`, `oneCore.py:303-312`, and the wrapper's own `terminate`, `OneCore:633-653`):
  1. Block callbacks first: `self._earlyExitCB = True` (checked by `_callback`, `OneCore:428`) and `self._segmentCallback.detach()` (`OneCore:96-98`), so a callback the helper may still deliver reaches no driver.
  2. Keep the trampoline alive for the process: `_TERMINATED_CALLBACKS.append(self._callbackInst)` — the reviewed helper can time out of terminate without invalidating the callback (`OneCore:21-24`, as `terminate` does at `:647-648`). The trampoline wraps only the `_DetachableCallback` (the parent sees `self._callback` intercepted, `OneCore:236-243`), so this retains no driver.
  3. Only for a live token (`token is not None and token.value`): `self._dll.ocSpeech_terminate(token)`. A token that was never created (`_ocSpeechToken` missing), or created with a null value (`ocSpeech_initialize` raised, so `.value` was never assigned, or returned null), is not terminated.
  4. Finally (also when terminate raises) drop `self._ocSpeechToken` and `self._callbackInst`, as NVDA does.
- Fix the comment: the wrapper releases the host and, once NVDA's constructor created them, its native callback and token.
- `tests/test_wrapper_init_cleanup.py`'s module docstring says what a parent left half-built "stays out of reach"; amend it for OneCore.

No new parent private names: `_callbackInst`, `_dll`, `_earlyExitCB`, `_ocSpeechToken` are already in `_OneCorePort.NVDA_PRIVATES` (`OneCore:50-64`), checked by `tests/test_native_strategy_guards.py:270-284`.

### What NVDA users hear or see

Nothing unless OneCore fails to start; then the native token is released instead of leaking for the rest of the NVDA session.

### Tests (`tests/test_wrapper_init_cleanup.py`, OneCore section; fakes on Linux, `tests/onecore_drain_harness.py` loads NVDA's real `oneCore.py`)

- `test_onecore_a_failing_step_after_the_token_terminates_it_and_releases_the_host`: `ocSpeech_setVoice` raises → the original error propagates; `ocSpeech_terminate` was called once with the token value from `ocSpeech_initialize`; release order `["token", "host"]`; at terminate time the driver's callback was already detached and `_earlyExitCB` set; the trampoline is in `_TERMINATED_CALLBACKS`; the driver dropped `_ocSpeechToken` and `_callbackInst`.
- `test_onecore_a_null_token_is_not_terminated`: `ocSpeech_initialize` returns `0`, then `ocSpeech_setVoice` raises → no `ocSpeech_terminate`; release order `["host"]`.
- `test_onecore_a_failing_token_release_is_logged_and_the_original_error_raised`: `ocSpeech_setVoice` raises and `ocSpeech_terminate` raises → one "initialization cleanup failed" log, original error raised, host released.
- Existing `test_onecore_a_failing_nvda_constructor_releases_the_host` (initialize raises → null token): additionally assert `ocSpeech_terminate` was not called.

Windows manual item: none practical (forcing a OneCore start failure needs a broken helper or voice set); unverified on Windows.

## 3. C7: RHVoice `cancel()` waits for its worker

### 3.1 What the code does

`cancel()` (`RHVoice:402-431`): under the stop gate and host admission it cancels the host, abandons every record but the current one and calls the inner `cancel()` (which empties the tts queue, sets the cancel flag and stops the player, `inner-RHVoice:605-612`). Then, outside admission, `host.wait_settled(current)` (`:423`) and a second `self._inner.player.stop()` (`:424-428`). `wait_settled` waits until `current` is no longer the host's current record and until sinks running at call time return; from a callback bound to that record it does not wait for the record, and from any bound callback or the delivery thread it does not wait for sinks (`host:472-486`).

### 3.2 Why it was introduced

- The pre-host RHVoice design (`docs/superpowers/specs/2026-09-30-worldvoice-rhvoice-drain-design.md:25`): cancellation "stops playback, waits for the current callable/callback/feed activity to retire before admitting a successor, then stops again if an already-admitted feed could have queued old audio".
- Phase 3b-2 kept that synchronous cancel when RHVoice moved onto `SegmentHost` (`docs/superpowers/specs/2026-10-02-phase3b2-rhvoice-design.md:60` "`cancel()` returns with the old segment stopped", `:105` steps; commits `644cc74` added `wait_settled`, `fbbc850` used it). `d911e38` only added the `notify_all` in `abandon` that wakes it (`host:438-439`).
- The late-feed re-stop is **not** newer than the wait: RHVoice's `_WavePlayer.feed` already stopped again after an admitted feed of an invalid record in `fbbc850` (its `finally: if not record.is_valid(): self.stop()`); P53 only moved that into the shared `LeasedPlayer._feed_admitted` (`host:720-734`). So the wait was never merely a backup of that re-stop.

### 3.3 Which guarantees are held elsewhere

**(a) Late audio overlapping a successor.**

- *Successor on RHVoice:* held without the wait. One inner tts worker runs every record in order (`inner-RHVoice:413-428`); a record's `_QueuedSpeech` leaves only after `close` + `wait_consumers` + `retire`, and `retire` waits for every consumer (`RHVoice:248-262`, `host:511-513`). Every feed is a consumer (`RHVoice:184-192`) whose `finally` stops the player again when the record is invalid (`host:731-734`), and `host.cancel()` invalidates the current record before the inner cancel's stop (`host:307-309`, `:690-697`; the current record is still pending until retire). The next record also waits for the stop gate (`RHVoice:235`) and the lifecycle resource (`lifecycle:244`).
- *Successor on another engine:* **not held without the wait.** The scheduler starts any next task once no stop is in flight (`scheduler:561`); `_stops_in_flight` drops when every `core.cancel()` returned (`scheduler:424-431`, `:446-447`). The lifecycle resource gate is per engine (each `SegmentHost` owns its `SegmentLifecycle`, `host:189`), and `finish_segment` only retires index-ledger state (`bridge/engineAdapter.py:187-189`). Without the wait, a feed admitted before the cancel can still be inside `WavePlayer.feed` when `cancel()` returns. If it enters `wasPlay_feed` after cancel's stop, WASAPI completes the pending stop and plays the chunk (`ref/nvda/nvdaHelper/local/wasapi.cpp:320-323`; NVDA's `feed` itself, `ref/nvda/source/nvwave.py:313-366`), until the feed's own re-stop. With the wait, that re-stop has happened before `cancel()` returns, so before any successor can start. This is the guarantee the wait gives and nothing else does.
- The other four engines do not wait (cons.md §5 table: `Espeak:213`, `SAPI5:674`, `OneCore:573`, `VE:675`); for them the same cross-engine window exists today. That is an inconsistency in the other direction, not evidence that RHVoice's wait is redundant.

**(b) Does anything rely on `cancel()` returning only after sinks/retire?**

- Scheduler: relies on "returned ⇒ old audio stopped" only through `_stops_in_flight` (above). It does not rely on running sinks having returned: `cancel()` bumps the epoch and cancels every request token under the delivery lock (`scheduler:433-449`), and `_accepts_events_locked` drops events for invalid tasks (`scheduler:287-295`). The sink half of `wait_settled` is therefore covered elsewhere; it stays because it is the same host call and is harmless (it never runs on a bound callback or the delivery thread).
- Bridge: `VoiceClassAdapter.cancel` retires the index source then calls `core.cancel()`; nothing follows (`bridge/engineAdapter.py:191-194`).

**(c) `terminate()`.** It calls `cancel()`, then `ttsQueue.put(None)` and `ttsThread.join()` (`RHVoice:433-449`). Joining the worker already implies the current record left, so terminate does not need the wait.

**(d) Main-thread blocking.** `cancel()` runs on NVDA's main thread (`SynthDriver.cancel` → `VoiceManager.cancel` → `TaskManager.cancel` → `_stop_all` → `EngineSession.cancel` → `VoiceClassAdapter.cancel` → `core.cancel`: `addon/synthDrivers/WorldVoice/__init__.py:332-335`, `voices/manager.py:255-257`, `scheduler:418-431`, `runtime/session.py:188-189`, `bridge/engineAdapter.py:191-194`). The wait is bounded: after cancel every callback is refused (`host:383-413`; the inner speech callback also returns 0 on the cancel flag, `inner-RHVoice:295-299`), a feed blocked on buffer space is woken by the stop (`wasapi.cpp:582-603`), `idle()` on a stopped player returns (`wasapi.cpp:620-626`), the cancelled record skips the final idle (`RHVoice:250-261`), and retire runs only the message delete. What remains is how long `RHVoice_speak` takes to return after a refused callback — unmeasured on Windows.

### 3.4 Decision

Decided by orchestrator with the recommended default; user may override before merge: **keep** `host.wait_settled(current)` and the post-settle stop, and replace the missing rationale with accurate comments at the call site:

- The wait: a successor on RHVoice is already ordered by the single worker; the wait is what orders the worker's late-feed re-stop before `cancel()` returns, and the scheduler starts a successor on **any** engine as soon as every cancel returned. It is bounded because every callback is refused after the cancel. A callback bound to the record does not wait for it (deadlock), as `wait_settled` documents.
- The post-settle stop: the only stop guaranteed to run on the cancelling thread after the worker settled. If the inner cancel raised before or in its own stop (the error is latched, `RHVoice:418-421`), audio already queued keeps playing unless something stops it; the feed re-stop runs only for a feed in flight, the lifecycle's `request_stop` runs on its own thread for segments only (`lifecycle:471-495`), and retire's stop for a cancelled ordinary record runs after `current` changed (`host:519-543`), racing `cancel()`'s return.

No behaviour changes, so no `SegmentHost.wait_settled` change: RHVoice stays its only production caller.

### 3.5 Tests (`tests/test_rhvoice_segment_drain.py`)

- `test_cancel_waits_for_admitted_feed_and_stops_late_audio_before_successor` (`:310-338`) stays and is tightened: it records the order of the player's feed returns and stops, and asserts that when `cancel()` returned, the blocked feed had returned **and** a stop followed it (today it only checks `stops >= 2` after the join).
- New `test_cancel_stops_again_after_settling_when_its_first_stop_failed`: the player's first stop raises once; `cancel()` raises that error, and a stop ran on the cancelling thread after the native call returned (deterministic: the fake native call is released only after the first stop was entered).

### 3.6 What NVDA users hear or see

Nothing changes. Open question (§6): removing the wait would make RHVoice's cancel return without waiting for `RHVoice_speak`, at the price of the cross-engine window in §3.3(a).

## 4. Readme

No behaviour an NVDA user can notice changes (C6 only when OneCore fails to start), so no changelog entry; the readmes (root `readme.md`, `addon/doc/{ru,uk,zh_CN,zh_HK,zh_TW}`) are not touched.

## 5. Constraints

- Never modify `driver/*/driver/*` (RHVoice's inner `DoneCallback`/`AudioPlayer` stay as vendored), `driver/sonic/`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py`; no Neural.
- Engine drivers stay independently installable; no cross-driver imports; shared code only in `runtime/`/`bridge/` (nothing new is shared in this phase).
- RHVoice inner private names only through `_RHVoiceInner` (`tests/test_native_strategy_guards.py:224`); OneCore parent privates only from `_OneCorePort.NVDA_PRIVATES`.
- ruff pinned `0.16.3`; tabs; match the surrounding comment density.

## 6. Open questions

1. **C7 removal (user-audible trade-off, not decided here).** Removing the wait (and the post-settle stop) would let NVDA's main thread return from cancel without waiting for `RHVoice_speak`, matching the other four engines, at the price of a window in which a late RHVoice chunk can overlap the first audio of a successor on another engine. Neither side is measured on Windows. Kept as is until the user chooses.
2. **The other engines' cross-engine window (§3.3(a)).** eSpeak, SAPI5, OneCore and VE/Cerence return from cancel while an admitted feed may still be in flight. Making them wait would change their cancel latency; not in scope.

## 7. Verification

- Linux: full `python3 -m pytest -q tests` (baseline 3632 passed, 0 skipped), `prek run --all-files`, `git diff --check`, protected paths unchanged, no tracked Neural files.
- Windows / NVDA: unverified. C1 is not audible; C6 requires a forced OneCore start failure; C7 changes no behaviour. Worth a listen when convenient: with RHVoice and another engine in one sentence, interrupt speech repeatedly (quick navigation) and listen for RHVoice tails over the next engine (should be none, as before).
