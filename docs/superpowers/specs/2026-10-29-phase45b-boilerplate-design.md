# Phase 45′: wrapper boilerplate convergence

Date: 2026-10-29.
Base: `master` `8ef4e12` (baseline 3597 passed, 0 skipped; `prek` all Passed; protected paths clean).
Branch: `phase45b-boilerplate`, worktree `/workspace/WorldVoice-phase45b`. Normal flow (DEVELOPMENT_WORKFLOW §3); the code moves carry the §3.2 automated proofs.
Sources: the consistency audit `cons.md` items **B1, B2, B3, B6, B7, B11, B15, B16** (§1, §2, §11, §12, 建議 "P45′ 樣板收斂"); `storage/refactor9.md` rows "P45′" and "P45 wrapper 樣板 mixin" (F4, `SegmentHostSpeaker`). It builds on phase 53 (`docs/superpowers/specs/2026-10-29-phase53-player-control-fault-design.md`, merged `8ef4e12`): every line number below is of `8ef4e12`, not of the audit's base `9d96ace`.

Line references: `host:` = `addon/synthDrivers/WorldVoice/runtime/segmentHost.py`, `control:` = `runtime/engineControl.py`, `barriers:` = `runtime/barriers.py`, `adapter:` = `bridge/engineAdapter.py`, `Espeak:` / `RHVoice:` / `SAPI5:` / `OneCore:` / `VE:` = `driver/<Engine>/__init__.py`, `oneCore.py:` / `sapi5.py:` / `espeak.py:` / `_espeak.py:` = `ref/nvda/source/synthDrivers/...`. Cerence line numbers equal VE's up to 335, VE+2 for 336–647 and VE+7 from 648 (`diff VE/__init__.py Cerence/__init__.py`); only VE lines are given.

## 1. Problem

The six wrappers stand on one skeleton (`SegmentHost` + `NativeStrategy` + shared barriers and, since phase 53, one lease and one latch path), but each still carries copies of the same small pieces and a few flags and branches no reachable path needs:

- **B1** `speak_segment` is the same nine lines in all six (`Espeak:163-171`, `RHVoice:401-409`, `SAPI5:434-442`, `OneCore:295-303`, `VE:470-478`): it forwards to `self._segmentHost.speak_segment` (`host:197-234`). `storage/refactor9.md` F4 proposes a `SegmentHostSpeaker` mixin in `runtime/segmentHost.py`.
- **B2** Four constructors repeat one "release what was built, newest first, log each failure, re-raise" loop (`Espeak:147-155`, `RHVoice:338-346`, `VE:403-411`, `SAPI5:400-414`), and OneCore a one-step copy (`OneCore:257-265`). They came from `4ca7e42` (VE/Cerence) and `484738a` (the other four).
- **B3** `_nvdaLabel` is defined three times (`Espeak:18-22`, `SAPI5:41-45`, `OneCore:32-36`), only to name NVDA in a `ready()` log line (`Espeak:255`, `SAPI5:733`, `OneCore:699`).
- **B6** VE keeps two flags that are always equal: `_terminated` and `_terminationRequested` are both initialised False (`VE:390`, `VE:395`), both set True in the same locked block of `terminate` (`VE:882-884`) and never reset.
- **B7** Two mode locks that no production path reaches (proofs in §3.5, §3.6):
  - VE/Cerence `_legacyUsed` (`VE:383`, set by `speak` `VE:484-486`): once a core spoke ordinary speech, `admission_error` rejects every segment (`VE:335-336`).
  - OneCore `_segmentMode` (`OneCore:234`, set by `submit` `OneCore:188`): three branches run only while it is False (`OneCore:160-161`, `OneCore:327-328`, `OneCore:448-449`).
- **B16** Dead code and stale comments:
  - VE/Cerence `_confirmNativeQuiescence` (`VE:466-468`) returns None; `_runNative` still wraps it in a try/except that would record, latch and stop (`VE:614-636`), a branch that cannot run.
  - `OneCore:371` "As on master: a failed setting is logged" names a branch, not a behaviour.
  - `SAPI5:662-664` "Token-only cancellation" reads as if cores still received the request token (removed in `9d96ace`, `driver/__init__.py:26-28`).
  - `VE:689-692` contrasts the ordinary final idle with "the segment drain, which latches"; since phase 53 the drain records and stops instead (`VE:362-370`).
  - `barriers:34-35` "ordinary speech in segment mode" names `_segmentMode`, which this phase removes.
- **B11** (terminate idempotence) and **B15** (`pause()` after terminate) differ per engine; §4 explains why neither is unified here.

## 2. Goals and non-goals

Goals — pure deletion, move and convergence:

1. One `speak_segment`: a runtime mixin `SegmentHostSpeaker` that all six wrappers use (B1).
2. One constructor-failure cleanup helper in `runtime/` (B2).
3. One NVDA label function (B3).
4. VE/Cerence keep one termination flag (B6).
5. Remove VE/Cerence `_legacyUsed` and OneCore `_segmentMode` with their branches (B7).
6. Remove `_confirmNativeQuiescence` and its unreachable branch; fix the stale comments (B16).

**No behaviour change on any production path**, correct runs and failure paths alike. The only observable difference is on a call sequence production never makes (§3.5): a VE/Cerence core that is called directly with ordinary speech and then a segment now speaks the segment instead of rejecting it.

Non-goals: drain semantics (idle vs sync, pause waits — P54); the runtime file split (P48); OneCore's constructor token leak (C6); RHVoice's wait in `cancel` (C7); readme and translations; anything that changes behaviour (§4 lists the audit items dropped for that reason).

## 3. Design

### 3.1 `SegmentHostSpeaker` (B1, core)

`runtime/segmentHost.py`, after `SegmentDrainCore` (`host:125-148`):

```python
class SegmentHostSpeaker(SegmentDrainCore):
	"""A SegmentDrainCore whose segments go to the SegmentHost the core keeps in self._segmentHost. ..."""

	def speak_segment(self, commands, token, *, context, on_event) -> None:
		self._segmentHost.speak_segment(commands, token, context=context, on_event=on_event)
```

- It is a `SegmentDrainCore`, so the bridge's lookups by name (`adapter:30`, `adapter:91`) and the naming guard's base resolution (`tests/test_naming_layers.py:17-20`, which follows bases transitively) see the same interface. `get_segment_drain_support` stays abstract: each wrapper still decides it.
- Each wrapper names it as its **last** base, replacing `SegmentDrainCore` (`Espeak:134`, `RHVoice:319`, `SAPI5:386`, `OneCore:225`, `VE:375`), and deletes its own `speak_segment`. No other base defines `speak_segment` (NVDA's `SynthDriver` classes and the vendored inner drivers do not), so the MRO resolves it to the mixin; the guard (§6) pins both facts.
- The mixin reads `self._segmentHost`, the attribute every wrapper already sets first in its constructor (`Espeak:139`, `RHVoice:323`, `SAPI5:390`, `OneCore:229`, `VE:378`). It declares no annotation for it: a class-level `_segmentHost` would be a camelCase binding in the core (`tests/test_naming_layers.py:52-66`).
- The now-unused imports (`PlaybackContext`, `SegmentEventSink`, `SpeechCommands`, `CancellationView`) leave each wrapper; each was used only by `speak_segment`.
- **Not moved: `speak()`.** A mixin `speak` placed last is shadowed by the parent's `speak` (NVDA `espeak.py`, `sapi5.py`, `oneCore.py:328`, the vendored RHVoice and VE drivers all define one), and placing the mixin first would let it shadow NVDA methods, which the guard forbids (`tests/test_native_strategy_guards.py:373-381`). Only eSpeak and RHVoice have the plain one-line body (`Espeak:173-174`, `RHVoice:411-412`); the other three carry engine checks (`SAPI5:456-462`, `OneCore:313-316`, `VE:480-492`). The audit marked this half optional (cons.md §11).

No behaviour change: the method body is the same call with the same arguments; `SegmentHost.speak_segment` is unchanged. Proof: the order-sensitive move check (§6.2).

### 3.2 `release_newest_first` (B2, core)

`runtime/engineControl.py`:

```python
def release_newest_first(releases: Sequence[Callable[[], object]], *, logger, message: str) -> None:
	"""Call every release, newest first; log a failed one with message and go on."""
```

The body is the loop every wrapper has today: `for release in reversed(releases): try: release() except Exception: logger.error(message, exc_info=True)`. Each wrapper's `except BaseException:` block keeps its comment, builds `releases` as today, calls the helper with `log` and its unchanged message (`"WorldVoice <engine> initialization cleanup failed"`), then `raise`. OneCore passes `[self._segmentHost.terminate]` and keeps its comment.

No behaviour change: same calls, same order, same catch (`Exception`, so `KeyboardInterrupt` in a release still escapes), the same log call with the same text and `exc_info=True` captured inside the helper's own `except`, and the original exception re-raised by the wrapper's bare `raise`. The wrapper passes its module global `log` at failure time, so the tests that replace it (`tests/test_wrapper_init_cleanup.py:46`, `tests/test_vocalizer_init_cleanup.py:53-57`) still capture the line.

### 3.3 `nvdaLabel` (B3, NVDA layer)

`runtime/` must stay NVDA-free, so the one copy goes to a new NVDA-layer module `bridge/nvdaVersion.py`: `def nvdaLabel() -> str` with the body of today's three copies (lazy `import versionInfo`, `f"NVDA {versionInfo.version}"`). Espeak and OneCore pass `host_label=nvdaLabel`; SAPI5 calls `nvdaLabel()`. Engine drivers stay independently installable: `bridge/` is core, and no driver imports another (DEVELOPMENT_WORKFLOW §8). The import stays lazy, so `versionInfo` is read only when a log line is written, and the tests that put a fake `versionInfo` into `sys.modules` before `ready()` (`tests/test_nvda_ready.py:93`, `tests/test_sapi5_old_nvda.py:148`) keep working.

### 3.4 One VE/Cerence termination flag (B6)

`_terminated` is deleted; its four reads (`VE:333`, `VE:482`, `VE:813`, `VE:824`) read `_terminationRequested`. Proof: both are False from the constructor (`VE:390`, `VE:395`), both become True in the one locked block (`VE:882-884`), and nothing else writes either, so every read sees the same value.

Kept on purpose:

- **VE's own checks are not replaced by `host.terminated`.** `terminate` sets the flag before `self._segmentHost.terminate()` (`VE:884-886`), and `host.terminate` waits for host admission (`host:315`), which a running `enqueue` holds while the inner `speak()` converts text (`host:256-287`, `VE:504`). In that window the VE check rejects a segment (`VE:333-334`) or ordinary speech (`VE:482-483`) and makes `pause()` raise (`VE:813-814`), where the host would still accept. Switching would change those races.
- **OneCore `_segmentTerminated`** (audit B6) is not a duplicate of `host.terminated`: it is set under host admission before `cancel()` (`OneCore:661-671`), while `host.terminate()` runs last (`OneCore:678`), and it is also the wake-up predicate of OneCore's own worker and waits (`OneCore:347`, `OneCore:410`), which `host.terminate` does not notify.
- **OneCore `_checkSegmentAdmission`** and **SAPI5 `_checkSpeechAdmission`** (audit §11 "可納入 B6") check engine state the host does not have: OneCore's earlier flag (above), and SAPI5's worker and the legacy-audio path that bypasses the host (`SAPI5:448-462`).

### 3.5 Remove VE/Cerence `_legacyUsed` (B7)

Delete `_legacyUsed` (`VE:383`), its branch in `admission_error` (`VE:335-336`) and its assignment with comment in `speak` (`VE:484-486`). `admission_error` keeps the termination check.

Reachability proof (production): the engine adapter is the only caller of a core's `speak` or `speak_segment` (`adapter:29-35`; `grep` of the add-on finds no other caller). Which one it calls is the completion contract's entry (`adapter:157`, `adapter:181`; `runtime/completion.py:66-105`), and that contract is fixed once an opened adapter has spoken: `configureCompletion` refuses after speech or a different contract (`adapter:78-85`). Each `open` creates a new core and `close` destroys it (`adapter:66-72`, `adapter:97-106`). So one VE/Cerence core receives only ordinary speech or only segments; the lock never fires. VE/Cerence declare `DrainProfile()` with no condition (`VE:940`), so in production they receive segments only.

Direct-call change (tests, not production): `tests/test_engine_segment_contract.py:196-229` (`ORDINARY_THEN_SEGMENT`) expects VE/Cerence to reject a segment after ordinary speech; now it drains, as on the four other engines. The lock's reason ("Legacy VE callback lifetimes are unproven") no longer holds since ordinary speech runs through the host with all three barriers (`VE:46-50`, `717c302`, `bff05d4`).

### 3.6 Remove OneCore `_segmentMode` (B7)

Delete `_segmentMode` (`OneCore:234`, `OneCore:188`) and the three branches that run only while it is False: the `admission_error` rejection (`OneCore:160-161`), `_processQueue`'s call of NVDA's queue (`OneCore:327-328`) and `_callback`'s call of NVDA's callback (`OneCore:448-449`).

Reachability proof (every path, tests included): `_segmentMode` is False only before the first `submit`, and nothing resets it.

- `_processQueue` is called by the wrapper's `submit` after it set the flag (`OneCore:188-190`), by NVDA's `_queueSpeech` (`oneCore.py:351-352`, overridden by `OneCore:318-324`, which never calls it), by NVDA's `_callback` (`oneCore.py:531`) and by NVDA's `_handleSpeechFailure` (`oneCore.py:475`, called only from NVDA's `_callback`, `oneCore.py:488-490`). Setting changes only append to `_queuedSpeech` (`oneCore.py:365-398`).
- `_callback` is called by the native helper for an `ocSpeech_speak` call (`oneCore.py:462-466`, through `_DetachableCallback`, `OneCore:83-102`). `ocSpeech_speak` is called only by the wrapper worker for a record (`OneCore:400`, after a `submit`) and by NVDA's `_processQueue` (`oneCore.py:466`).
- So before the first `submit` no `ocSpeech_speak` has run, no callback can arrive, and no one calls `_processQueue`: neither False branch can run. `_isProcessing` is set True only by the wrapper worker (`OneCore:365`, after a `submit`) and by NVDA's `_processQueue` (`oneCore.py:461`, unreachable as shown), so `not _segmentMode and _isProcessing` (`OneCore:160`) is never true.

`_processQueue`, `_callback` and `_isProcessing` stay in `_OneCorePort` (`OneCore:58-73`): still overridden or read.

### 3.7 Remove `_confirmNativeQuiescence` (B16)

Delete the method (`VE:466-468`) and, in `_runNative`'s `finally` (`VE:610-636`), the `blocked` variable, the try/except around the call, the `if blocked is None:` guard (its body `self._nativeCall = None` stays, unconditional) and the `if blocked is not None:` stop. Proof: the method's body is `return None`, so the `try` never raises, `blocked` is always None, the guard is always true and the stop never runs. `tests/test_hygiene_guards.py` `_REASONS` loses the `("record_error", "_failSegmentControl")` entry, whose only handlers were these two (`VE:624`, Cerence `:626`). The tests' no-op replacements of the method go (`tests/test_vocalizer_segment_drain.py:56-59` and its 39 calls; `tests/runtime_drain_integration_harness.py:3-4`, `:287-288`).

The latch rule in `control:6-20` keeps "a native call whose callbacks cannot be proven finished" as a class of control failure: it states the rule for any engine, not a current call site.

### 3.8 Stale comments (B16)

| Where | Now | After |
|---|---|---|
| `OneCore:371` | "As on master: a failed setting is logged; speech continues." | "A failed setting is logged; speech continues." |
| `SAPI5:662-664` | "Token-only cancellation does not enter the parent's purge path. …" | "A request whose work was cancelled before cancel() reached this driver does not enter the parent's purge path. …" (the scheduler cancels the request token first, then calls `core.cancel()`, `runtime/scheduler.py:386-395`, `:419-441`; the worker sees the invalid record without `_isCancelling`, `SAPI5:615`, `:628`) |
| `VE:689-692` | "Unlike the segment drain, which latches so no successor starts on an uncertain player, no control error is latched: …" | "As in the segment drain (engineControl's latch rule), no control error is latched: …" (`VE:362-370`) |
| `barriers:34-35` | "ordinary speech in segment mode still calls idle() once the queue empties (its _legacyCallback)" | "OneCore's ordinary speech still calls idle() once its queue empties (_legacyCallback)" |
| `VE:484-485` | "Legacy callback lifetimes are unproven: correlated mode stays off …" | removed with `_legacyUsed` (§3.5) |
| `tests/test_engine_segment_contract.py:208-209` | "VE/Cerence refuse correlated mode once legacy speech ran" | every engine drains a segment after ordinary speech |

Checked and still correct (no change): `VE:46-50`, `VE:792-808` (DONE ownership, cancel through the host, `9d96ace`); `RHVoice:424-428` (abandon queued, `0d222e4`); `driver/__init__.py:26-28`; `SAPI5:708`; `Espeak:69-75`; `barriers:31-36` already says `idle()` releases ducking and the OneCore drain's `sync()` does not (cons.md B16 asked for it; P54 changes that drain). `grep` for `withdraw`, `_set_voice` and `master` finds no other stale wording in `driver/*/__init__.py`, `runtime/` or `bridge/`.

## 4. Audit items not done (each needs a behaviour change)

- **B11 terminate idempotence.** Swapping each guard for `host.terminate()`'s return value changes a failure path:
  - RHVoice guards on `ttsEngine is None` (`RHVoice:447`), which becomes None only after the engine was deleted (`RHVoice:458-462`). If `RHVoice_delete_tts_engine` raises, a second `terminate` retries the cleanup today; with the host's flag it would return at once.
  - SAPI5 has no guard (`SAPI5:696-700`); a second call re-runs NVDA's `terminate` (`sapi5.py:597-615`), which retries a player close that failed the first time. A guard removes that retry, and using `host.terminate()`'s return value would also move the host's termination before `_invalidateSegments`.
  - OneCore's `_segmentTerminated` and VE's `_terminationRequested` are needed for their own reasons (§3.4).
  - eSpeak already uses the host's return value (`Espeak:236-238`).
- **B15 `pause()` after terminate.** Measured on the Linux fakes (scratch probe through `tests/engine_contract_harness.py`): VE and Cerence raise `RuntimeError("<engine> driver has terminated")` (`VE:813-814`); eSpeak raises `AttributeError` (NVDA's `_espeak.pause` on the `None` player, `_espeak.py:269-271`, `espeak.py:254-255`); OneCore, RHVoice and SAPI5 return None. A common rule changes at least one engine on a reachable (shutdown race) path. This phase pins today's behaviour per engine (§6.1) so a later change is deliberate.
- **B1's `speak()` half**: §3.1.
- **B6 for OneCore and SAPI5**: §3.4.

## 5. NVDA user-visible changes

None. No setting, dialog, string, log text, barrier, event or thread changes. The constructor-failure log lines keep their text; the `ready()` log lines keep their text.

## 6. Tests

### 6.1 New and changed tests

- `tests/test_segment_host.py`: `test_segment_host_speaker_forwards_to_the_core_host` (a stub core with `_segmentHost` recording the call receives exactly `commands, token, context=, on_event=`); `test_segment_host_speaker_leaves_drain_support_abstract` (a subclass without `get_segment_drain_support` cannot be instantiated; it is a `SegmentDrainCore`).
- `tests/test_engine_control.py`: `test_release_newest_first_runs_every_release_in_reverse_and_logs_failures` (order newest first; a failing release logs `(message,)` with `exc_info=True` and the rest still run; nothing raised; an empty list does nothing).
- `tests/test_wrapper_init_cleanup.py`, `tests/test_vocalizer_init_cleanup.py`: the cleanup-log assertions also pin the message text `"WorldVoice <engine> initialization cleanup failed"` (characterization, green before and after).
- `tests/test_native_strategy_guards.py`:
  - `test_every_wrapper_core_declares_the_segment_drain_entries` accepts either form: last base `SegmentDrainCore` with both entries its own, or last base `SegmentHostSpeaker` with its own `get_segment_drain_support` and no own `speak_segment` (a local engine package may still use the plain base).
  - new `test_every_bundled_wrapper_uses_the_segment_host_speaker`: the six bundled wrappers use the mixin.
- `tests/test_engine_segment_contract.py`:
  - new `test_every_core_speaks_segments_through_the_shared_mixin`: `type(core).speak_segment is SegmentHostSpeaker.speak_segment` on each loaded wrapper (nothing in the MRO shadows it).
  - new `test_pause_after_terminate_keeps_each_engine_behaviour`: the B15 table of §4 (characterization).
  - `test_segment_after_ordinary_speech_follows_the_engine_mode_rule` becomes `test_segment_after_ordinary_speech_drains`: every engine drains (red on VE/Cerence before §3.5).
- `tests/test_nvda_ready.py`: `test_one_nvda_label_names_the_running_nvda` (only `bridge/nvdaVersion.py` defines it or imports `versionInfo` among the wrappers and bridge; it returns `"NVDA <version>"` with a fake `versionInfo`). The existing `ready()` tests pin the log lines.
- `tests/test_hygiene_guards.py`: `_REASONS` loses the entry of §3.7.
- `tests/test_vocalizer_segment_drain.py`, `tests/runtime_drain_integration_harness.py`: the `_confirmNativeQuiescence` replacements go (§3.7).
- Existing tests that pin the reachable paths of §3.4–§3.7 unchanged: `test_settings_tuples_do_not_take_native_job_identity` (a setting queued before OneCore's first speech is applied before it, `tests/test_onecore_segment_drain.py:283`), `test_ordinary_speak_after_terminate_raises`, `test_segment_after_terminate_fails_once_without_native_call`, the init-cleanup files, `test_vocalizer_segment_drain.py` (native call admission and retirement).

### 6.2 Move and rename proofs (DEVELOPMENT_WORKFLOW §3.2)

Scripts in the scratchpad (`p45b/tokcheck.py`, `p45b/movecheck.py`); commands and results in the progress ledger. Moves and renames are committed separately from other changes, one group per commit:

- **B1 move**, one commit per group (eSpeak, RHVoice, SAPI5, OneCore, VE+Cerence — VE and Cerence move together or the drift guard fails): every removed `speak_segment` is token-identical, in order, to `SegmentHostSpeaker.speak_segment` (modulo the `-> None` annotation two copies lack); the rest of each wrapper is token-identical in order to its old text except the listed import changes (`SegmentDrainCore` → `SegmentHostSpeaker`; `PlaybackContext`, `SegmentEventSink`, `SpeechCommands`, `CancellationView` removed) and the base-class token `SegmentDrainCore` → `SegmentHostSpeaker`.
- **B2 convergence**: each removed loop is token-identical to the helper body with `log` → `logger` and its string → `message`; the rest of each wrapper is unchanged but for the call and the import.
- **B3 move**: each removed `_nvdaLabel` body is token-identical to `nvdaLabel`'s; elsewhere only `_nvdaLabel` → `nvdaLabel` and one import line change.
- **B6 rename** (VE+Cerence): with `_terminated` → `_terminationRequested` applied to the old text and its two now-duplicate assignments dropped, old and new token streams are identical in order; `_terminationRequested` occurrences: 4 before, 8 after per file.
- **B7/B16 deletions**: each commit's token diff contains only the deleted ranges listed in its plan task (plus the comment replacements of §3.8 in their own commit).

### 6.3 Windows / NVDA

Not needed for correctness (no behaviour change); a smoke run of each engine (say all, cancel, pause/resume) on the next test build is enough. Linux tests exercise only the controlled native and audio boundaries.

## 7. Open questions

- §3.5 changes a direct-call behaviour that production never reaches (VE/Cerence accept a segment after ordinary speech). Decided by orchestrator with the recommended default (the coordinator's brief lists `_legacyUsed` for removal when unreachable); user may override before merge.
- B11 and B15 are left as they are (§4); unifying them needs a user decision on the post-terminate behaviour.
- `nvdaLabel` lives in `bridge/` (§3.3) rather than `driver/__init__.py`, the public plugin module the audit also suggested, so the plugin API does not grow. Decided by orchestrator with the recommended default; user may override before merge.

## 8. Implementation notes

Plan: `docs/superpowers/plans/2026-10-29-phase45b-boilerplate.md` (9 tasks, one run). Ledger: `.superpowers/sdd/2026-10-29-phase45b-boilerplate/progress.md`.

- Commits: mixin `df98a6e`; B1 moves `ab9d6b5` (eSpeak), `08d43b4` (RHVoice), `cac6170` (SAPI5), `ebd4d84` (OneCore), `d216228` (VE+Cerence), guard tests `5e55531`; B2 log-text pin `0ebfbcf`, helper `55d4d6c`, convergence `ee45d09`; B3 move `d8844b9`, guard test `8fb207a`; B15 pin `4a348fa`; B6 `295fd88`; B7 OneCore `efec925`, VE/Cerence `d6ea62f`; B16 quiescence `a3f7f80`, comments `9448ccc`.
- Proofs (scratch `p45b/tokcheck.py`, `p45b/movecheck.py`, `p45b/nocomment.py`, all run against `HEAD:<path>` before each commit): every B1, B2, B3, B6, B7 and B16 commit passed its order-sensitive token check with exactly the listed drops, substitutions and import changes; every moved block (six `speak_segment`, five cleanup loops, three `_nvdaLabel`) matched its new home token for token (`-> None`, `log`→`logger`, the message literal→`message`, and the `_nvdaLabel` comment wording excepted, as listed). A negative control (the eSpeak check without the dropped range) fails at the method.
- OneCore `_segmentMode` (§3.6), extra evidence: with the old wrapper restored temporarily, the full suite under coverage never executed the three False-branch bodies (old lines 153, 311, 432).
- Ruling: the B3 move and its guard test are separate commits — keeps the move commit free of other changes.
- Ruling: the comment "As on master" also appeared in `tests/test_onecore_segment_drain.py:338`; fixed with the wrapper comments (`9448ccc`).
- Ruling: `tests/test_hygiene_guards.py`'s table comment named the removed combined entry ("records and latches"); it now names the remaining one.
- Review Focus 5 mutant: replacing the now-unconditional `self._nativeCall = None` in `_runNative` with `pass` survives the VE and contract tests — `_closeAdmission` already closed that call, so a stale `_nativeCall` refuses callbacks as None does. The clear is defensive; equivalent mutant.
- `tests/test_vocalizer_segment_drain.py` tests that took `monkeypatch` only for the removed helper keep the unused fixture parameter (no lint rule flags it; changing 39 signatures would only add churn).

Verification at the last commit: 3614 passed, 0 skipped (baseline 3597 + 17 new tests: 2 mixin, 1 + 6 shared-entry guards, 1 cleanup helper, 1 NVDA label, 6 post-terminate pause); `prek run --all-files` all Passed; `git diff --check master` clean; protected-path commands empty. Linux tests exercise only the controlled native and audio boundaries; Windows/NVDA not verified.
