# Phase 55 Audit C Items (C1, C6, C7) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** RHVoice segments stop notifying an anonymous `synthDoneSpeaking`; a failing OneCore constructor releases the native token NVDA's constructor created; RHVoice's synchronous cancel wait and post-settle stop are kept and documented with tests that pin what they protect.

**Architecture:** All changes are in the engine wrappers (`driver/RHVoice/__init__.py`, `driver/OneCore/__init__.py`); no runtime/bridge code changes. C1 routes a segment record's done callback to a new `_RHVoiceInner.segmentDone()` (the inner `DoneCallback` minus its notify). C6 adds `SynthDriver._releaseParentNative()` to OneCore's constructor failure list, released newest first by `release_newest_first`. C7 is comments plus tests.

**Tech Stack:** Python 3 (NVDA add-on), pytest, threading, ctypes fakes; ruff 0.16.3 via prek.

**Spec:** `docs/superpowers/specs/2026-10-29-phase55-c-items-design.md`

## Global Constraints

- Never modify `driver/*/driver/*` (RHVoice's inner `DoneCallback`/`AudioPlayer`, the vendored OneCore driver), `driver/sonic/`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py`; never add Neural.
- Engine drivers stay independently installable: no cross-driver imports; shared code only in `runtime/`/`bridge/` (none added here).
- RHVoice reaches inner private names only through `_RHVoiceInner` (`tests/test_native_strategy_guards.py::test_rhvoice_reaches_inner_privates_only_through_its_port`); OneCore uses only parent privates listed in `_OneCorePort.NVDA_PRIVATES` (`test_onecore_parent_privates_are_listed_and_exist`).
- Ordinary RHVoice speech (`record.operation is None`) keeps calling the inner done callback unchanged.
- OneCore: `ocSpeech_terminate` only for a live token (`token is not None and token.value`); callbacks blocked (`_earlyExitCB`, `_segmentCallback.detach()`) and the trampoline kept in `_TERMINATED_CALLBACKS` before it.
- C7: no behaviour change; `SegmentHost.wait_settled` untouched.
- Tests that read wrapper privates go through named views in the harness modules where one exists; new ones follow that pattern.
- ruff pinned `0.16.3`; prek hooks run on commit (re-stage and re-commit if a hook rewrites files; never `--no-verify`); commits: explicit paths, `git diff --cached --stat` first, English `<type>: <summary>` + why-body, no `Co-Authored-By`; no push; no `git stash`; at most 3 pytest workers.
- No readme/changelog change (no user-noticeable behaviour change).

## Review Focus

1. A segment cancelled while its done callback runs: the cancel-flag check must still skip `on_done()`/`idle()`, and the record still reaches `ENGINE_DONE` only when the steps did not raise (Task 1 `test_a_segment_and_an_ordinary_utterance_notify_exactly_one_done` covers the normal path; the existing `test_cancelled_old_callbacks_do_not_complete_or_index_successor` and `test_swallowed_native_and_audio_failures_never_publish_success[idle]` must stay green).
2. Ordinary (legacy) speech behind a segment on the single worker still gets exactly one DONE, after the segment's final idle (Task 1 rewritten `test_ordinary_speech_waits_for_contextual_final_idle`).
3. A DONE listener that cancels from the worker's done callback must not deadlock now that the DONE comes only from ordinary speech (Task 1 rewritten `test_legacy_done_callback_can_cancel_without_deadlocking_worker`).
4. OneCore start failure with a null token, or with `ocSpeech_terminate` itself raising: no terminate on a null token, one cleanup log, the original error propagates, the host is still released (Task 2 `test_onecore_a_null_token_is_not_terminated`, `test_onecore_a_failing_token_release_is_logged_and_the_original_error_raised`).
5. Cancel racing an admitted RHVoice feed: `cancel()` must not return before that feed returned and was stopped again, and must stop once more after settling when its first stop failed (Task 3 tightened `test_cancel_waits_for_admitted_feed_and_stops_late_audio_before_successor`, new `test_cancel_stops_again_after_settling_when_its_first_stop_failed`).

Baseline (worktree at `b768c57` + spec commit): **3632 passed, 0 skipped**; prek all Passed; protected paths clean.

---

### Task 1: C1 — RHVoice segment records do not notify DONE

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py` (`_RHVoiceInner`, `:25-89`; `SynthDriver._nativeCallback`, `:370-391`)
- Test: `tests/test_rhvoice_segment_drain.py` (`:294-307`, `:768-800`, new test)

**Interfaces:**
- Consumes: `_RHVoiceInner.player` (inner `AudioPlayer`: public `on_done()`, `idle()`), `_RHVoiceInner.cancelFlag`; `NativeRecord.operation`.
- Produces: `_RHVoiceInner.segmentDone(self) -> None` — the inner `DoneCallback.__call__` steps without `synthDoneSpeaking.notify`: return if `cancelFlag.is_set()`, else `player.on_done()` then `player.idle()`; exceptions propagate.

- [ ] **Step 1: Write the failing test and update the two DONE-dependent tests**
  - New `test_a_segment_and_an_ordinary_utterance_notify_exactly_one_done`: `env.native.scripts.append({"auto_return": True})`; `speak(env)` → `events.wait_one().kind is SEGMENT_DRAINED`; `env.dones == []`; then `env.native.scripts.append({"auto_return": True})`, `env.driver.speak(("legacy", env.commands.IndexCommand(8)))`, `env.native.wait_call(2).returned.wait(...)`, `eventually(lambda: env.dones)`; `env.dones == [env.driver]`.
  - `test_ordinary_speech_waits_for_contextual_final_idle`: replace `dones_before` with `assert env.dones == []` before the ordinary `speak`, and end with `eventually(lambda: env.dones)` + `assert env.dones == [env.driver]`.
  - `test_legacy_done_callback_can_cancel_without_deadlocking_worker`: speak ordinary text (`env.driver.speak(("legacy", env.commands.IndexCommand(7)))`) instead of a segment; keep `cancelled.wait` and `call.returned.wait`; drop the segment `events` assertion.
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_rhvoice_segment_drain.py` — Expected: FAIL in the new test (`env.dones == [<driver>]` after the segment) and in `test_ordinary_speech_waits_for_contextual_final_idle` (`env.dones` not empty before the ordinary speak); the legacy-cancel test passes either way.
- [ ] **Step 3: Implement** `_RHVoiceInner.segmentDone()`; in `_nativeCallback`, inside the bound-callback `try`, call `self._inner.segmentDone()` (result `None`) instead of `callback(*args)` when `isDone and record.operation is not None`; `host.reach(record, ENGINE_DONE)` and the error handler stay as they are. One comment: a segment's end is reported by the runtime, so the anonymous DONE goes; the player steps stay.
- [ ] **Step 4: Run** the file → PASS; full suite `python3 -m pytest -q tests` → **3633 passed, 0 skipped**.
- [ ] **Step 5: Commit** `driver/RHVoice/__init__.py`, `tests/test_rhvoice_segment_drain.py`: `fix: stop RHVoice segments notifying an anonymous synthDoneSpeaking`.

### Task 2: C6 — OneCore constructor failure releases the native token

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py` (`SynthDriver.__init__` except branch `:244-253`; new method after `__init__`)
- Test: `tests/test_wrapper_init_cleanup.py` (module docstring `:1-8`; OneCore section `:271-338`)

**Interfaces:**
- Consumes: NVDA parent state `_callbackInst`, `_ocSpeechToken` (`HANDLE`), `_dll.ocSpeech_terminate`, `_earlyExitCB`; wrapper `_segmentCallback.detach()`, module `_TERMINATED_CALLBACKS`; `release_newest_first(releases, logger=log, message=...)`.
- Produces: `SynthDriver._releaseParentNative(self) -> None` (spec §2 steps 1–4); except branch: `releases = [self._segmentHost.terminate]` + `self._releaseParentNative` when `getattr(self, "_callbackInst", None) is not None`.

- [ ] **Step 1: Write the failing tests** (OneCore section; capture the half-built driver with a subclass `class Probe(env.outer.SynthDriver)` whose `__init__` appends `self` then calls `super().__init__()`; record `"token"` in `record.calls` from a replacement `env.native.ocSpeech_terminate`; `_fail_onecore_set_voice(env)` makes `env.native.ocSpeech_setVoice` raise `Boom("ocSpeech_setVoice failed")`)
  - `test_onecore_a_failing_step_after_the_token_terminates_it_and_releases_the_host`: `Probe()` raises `Boom`; terminate called once with token value `123` (`env.native.initialize` returns 123); `record.calls == ["token", "host"]`; at terminate time `driver._earlyExitCB is True` and the callback was detached (named view `segment_callback_detached(driver)` in `tests/onecore_drain_harness.py`); `env.outer._TERMINATED_CALLBACKS[-1] is env.native.callback`; `driver._ocSpeechToken is None and driver._callbackInst is None` (named views); host released.
  - `test_onecore_a_null_token_is_not_terminated`: `initialize` returns `0`; setVoice raises → `Boom`; `record.calls == ["host"]` (no `"token"`).
  - `test_onecore_a_failing_token_release_is_logged_and_the_original_error_raised`: setVoice raises and terminate raises `RuntimeError` → `Boom` raised; `_assert_one_cleanup_error_logged(record, "OneCore")`; host released.
  - `test_onecore_a_failing_nvda_constructor_releases_the_host` (initialize raises): add `assert "token" not in record.calls` via the recording terminate.
  - Docstring: OneCore's native callback and token are released once NVDA's constructor created them.
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_wrapper_init_cleanup.py -k onecore` — Expected: FAIL in the first and third new tests (no terminate, `record.calls == ["host"]`; no log); the null-token test and the updated initialize test pass already (nothing releases the token today).
- [ ] **Step 3: Implement** `_releaseParentNative` and the conditional release list; rewrite the except-branch comment (spec §2).
- [ ] **Step 4: Run** → PASS; full suite → **3636 passed, 0 skipped**.
- [ ] **Step 5: Commit** `driver/OneCore/__init__.py`, `tests/test_wrapper_init_cleanup.py`, `tests/onecore_drain_harness.py`: `fix: release OneCore's native token when its constructor fails`.

### Task 3: C7 — document and pin RHVoice's cancel wait and post-settle stop

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py` (`SynthDriver.cancel`, `:402-431`) — comments only
- Test: `tests/test_rhvoice_segment_drain.py` (`:310-338`, new test)

**Interfaces:**
- Consumes: harness `Player` (`feed_release`, `feed_entered`, `stop_entered`, `stops`, `stop_error`), `Native` call (`return_release`, `returned`, `done`).
- Produces: no code interface.

- [ ] **Step 1: Write the tests**
  - Tighten `test_cancel_waits_for_admitted_feed_and_stops_late_audio_before_successor`: in `blocked_player`, wrap the new player's `feed` and `stop` to append `"fed"` (after the original feed returns) and `"stop"` to a shared `order` list; the stopper thread runs `env.driver.cancel()` then `returned.extend(order)`; after the join assert `"fed" in returned` and `"stop" in returned[returned.index("fed") + 1:]`.
  - New `test_cancel_stops_again_after_settling_when_its_first_stop_failed`: speak a segment, `call.done.wait`; replace `player.stop` with a wrapper that records `(current_thread(), call.returned.is_set())` and raises `OSError("stop failed")` on its first call only; a helper thread releases `call.return_release` after `player.stop_entered`; `pytest.raises(OSError)` around `env.driver.cancel()`; assert some recorded stop has `(main thread, True)`.
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_rhvoice_segment_drain.py -k "cancel_waits_for_admitted or stops_again_after_settling"` — Expected: PASS (the behaviour exists). Mutation check (scratch copy, not committed): delete `host.wait_settled(current)` → the tightened test FAILs (`stopper.is_alive()` or the order assertion); delete the post-settle stop → the new test FAILs (no `(main, True)` stop). Record both in the ledger.
- [ ] **Step 3: Implement** the comments at the call site (spec §3.4): the wait orders the late-feed re-stop before `cancel()` returns because the scheduler starts a successor on any engine once every cancel returned; same-engine successors are ordered by the single worker; bounded because callbacks are refused; a bound callback does not wait. The post-settle stop: the only stop on this thread after the worker settled, which matters when the inner cancel raised before or in its own stop.
- [ ] **Step 4: Run** → PASS; full suite → **3637 passed, 0 skipped**.
- [ ] **Step 5: Commit** `driver/RHVoice/__init__.py`, `tests/test_rhvoice_segment_drain.py`: `docs: explain what RHVoice's synchronous cancel protects`.

### Task 4: Full verification

- [ ] `python3 -m pytest -q tests` → **3637 passed, 0 skipped** (baseline 3632 + 5).
- [ ] `prek run --all-files` → all Passed; `git diff --check master` → no output.
- [ ] Protected paths: `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py addon/synthDrivers/WorldVoice/unicodeScripts/unspaced_common_data.py` and `git ls-files addon/synthDrivers/WorldVoice/driver/Neural` → no output.
- [ ] Ledger: final counts, every `Ruling:`; report to the orchestrator (no packaging, Windows unverified).

## Self-Review

- Spec coverage: §1 → Task 1; §2 → Task 2; §3.4/§3.5 → Task 3; §4 (no readme) → Global Constraints; §7 → Task 4.
- Types: `segmentDone() -> None`, `_releaseParentNative() -> None`; `record.operation` is `SegmentOperation | None`.
- Review Focus items 1–5 each name a task test.
- Proportion: three small wrapper changes, five new tests, three rewritten/tightened.
