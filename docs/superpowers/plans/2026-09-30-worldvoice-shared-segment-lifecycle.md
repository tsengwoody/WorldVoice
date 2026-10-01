# WorldVoice Shared Segment Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route the seven enabled DRAIN wrappers through one coordinator for admission, cancellation, producer retirement, playback drain, and once-only correlated terminal delivery.

**Architecture:** Add one `SegmentLifecycle` per outer synth core and one `SegmentOperation` per contextual segment. The coordinator owns ordering, leases, failure state, resource handoff and terminal delivery; engine hooks retain native submit/stop, native producer boundary and final player barrier. Keep ordinary NVDA `speak` behavior and SAPI5 legacy audio policy unchanged.

**Tech Stack:** Python 3, NVDA synth drivers, pytest with existing fake-native/audio harnesses, SCons add-on packaging.

**Spec:** `docs/superpowers/specs/2026-09-30-worldvoice-shared-segment-lifecycle-design.md`

## Global Constraints

- Work on `test/force-segment-end-index-all-engines`; do not edit NVDA upstream sources, bundled native SDKs or inner driver implementations.
- Cover OneCore, Neural, VE, Cerence, SAPI5 WASAPI, eSpeak and RHVoice outer wrappers. SAPI5 `useWasapi=False` remains `LEGACY_DONE` from the first segment; its DRAIN barrier is a later change.
- Preserve `speak_segment(commands, token, *, context, on_event)`, `get_segment_drain_support`, settings, ordinary `speak`, original index delivery, adapter/bridge/ledger/scheduler contracts and unknown-engine fallback.
- Only the original operation may own a callback, feed, index or terminal event. A successor may queue, but cannot submit to a shared native/player resource until its predecessor's stop, producer leases and player cleanup retire.
- A live operation gets at most one `SEGMENT_DRAINED` after native and playback barriers, or one `SEGMENT_FAILED` on observable failure. A cancelled operation gets neither. Failed uncertain cleanup blocks later native admission until hook-proven reinitialization or driver replacement.
- Never hold coordinator locks across native calls, audio operations, waits or event sinks. No terminal sink runs on native/COM/driver callback or worker stacks; reentrant cancel/terminate must not self-join.
- Retain the current profile evidence caveat: Linux fake tests do not establish Windows/SDK callback silence or physical tail acceptance.

## File Map

- Create `addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py`: the common operation, lease, hook protocol, resource gate, cancellation/fault state, and terminal delivery queue.
- Keep `runtime/playbackWork.py` as the `PlaybackWork` event/context validity primitive; change it only if a test proves a missing atomicity primitive.
- Modify the seven `addon/synthDrivers/WorldVoice/driver/<Engine>/__init__.py` outer wrappers only; keep each engine's native/player specifics there. VE and Cerence have distinct modules and tests even though their patterns resemble each other.
- Create `tests/test_segment_lifecycle.py`; extend `tests/test_{onecore,neural,vocalizer,sapi5,espeak,rhvoice}_segment_drain.py` and `tests/test_runtime_drain_integration.py`. `test_vocalizer_segment_drain.py` parametrizes VE and Cerence.
- Update `docs/superpowers/finish_task.md` only after implementation verification; include the new commit list and real-versus-fake validation limits.

## Coordinator Interface for All Tasks

Implement these public names in `runtime/segmentLifecycle.py`. `SegmentEngineHooks` is a `Protocol` with `submit_native(operation: SegmentOperation, commands: SpeechCommands) -> None`, `request_stop(operation: SegmentOperation) -> None`, `wait_native_boundary(operation: SegmentOperation) -> None`, `wait_native_retired(operation: SegmentOperation) -> None`, and `wait_playback_drained(operation: SegmentOperation) -> None`. A boundary means the hook's **existing** criterion for no further native producer; it does not create a new SDK guarantee. `wait_native_retired` waits all already admitted callback/feed leases. A hook may delegate to the wrapper's existing methods and state rather than duplicate native logic.

`SegmentLifecycle(hooks: SegmentEngineHooks)` exposes `accept(context: PlaybackContext, token: CancellationView, sink: SegmentEventSink) -> SegmentOperation`, `run(operation: SegmentOperation, commands: SpeechCommands) -> None`, `admit_producer(operation: SegmentOperation, parent: ProducerLease | None = None) -> ProducerLease | None`, `retire_producer(lease: ProducerLease) -> None`, `close_admission(operation: SegmentOperation) -> None`, `cancel(operation: SegmentOperation) -> None`, `fail(operation: SegmentOperation, error: Exception) -> None`, and `terminate() -> None`. `SegmentOperation.work: PlaybackWork` and `SegmentOperation.is_valid() -> bool` provide the captured context and cancellation check. `ProducerLease.operation: SegmentOperation` is immutable; retirement is idempotent. A child lease may only be created from a live parent lease of the same operation, including after normal native admission closes; after cancellation it cannot feed/index and is retained solely for cleanup.

`run` serializes native/player resource ownership, calls hook submit then native boundary, closes normal admission, waits admitted producers, waits playback drain, and queues one terminal event. On cancellation it requests stop and waits safe retirement before releasing the resource; queued cancelled work never submits. `request_stop` must not wait on the calling callback/feed stack; if native stop blocks, arrange it on a safe thread and let the retirement hook wait for its result. `fail` queues failure for a still-live operation and prevents success; a stop or uncertain retirement fault also latches a core control error. Delivery rechecks `PlaybackWork` immediately before committing the event; cancellation before that point suppresses delivery. Once `PlaybackWork` commits an event, later cancellation cannot retract it. Do not substitute an anonymous NVDA DONE or a timeout for either barrier.

## Review Focus

- Native return before a late callback/feed: Task 1 and each wrapper task must keep the predecessor's identity and block successor submission until admitted work retires.
- Token cancellation between final feed and terminal dispatch: Tasks 1, 2 and 8 must suppress success and discard old PCM before successor handoff.
- SAPI5 `EndStream` before PCM feed or player idle: Task 7 must keep the WASAPI operation open; legacy audio remains `LEGACY_DONE`.
- Empty audio or index-only segment: Tasks 3, 7 and 8 must still observe the engine's final barrier before DRAIN.
- Sink reenters cancel/terminate or raises: Task 2 and each wrapper regression must avoid deadlock, duplication and successor misattribution.

---

### Task 1: Common operation, resource gate and producer leases

**Files:** Create `runtime/segmentLifecycle.py`, `tests/test_segment_lifecycle.py`.

**Interfaces:** Produce the names and signatures under “Coordinator Interface”. Task 2 supplies terminal queue behavior; use a local recording sink until then. Consume `PlaybackWork`, `PlaybackContext`, `CancellationView`, `SegmentEventSink`, `SpeechCommands`.

- [ ] **Write failing tests:** `test_native_boundary_precedes_admission_close`, `test_nested_lease_retires_before_successor`, `test_cancelled_queued_operation_never_submits`, `test_stop_failure_blocks_successor`. Use controllable hook `Event`s; assert `events == []` and `len(hooks.submitted) == 1` while each old boundary/lease/stop is held, then exactly one event with the old context after release.
- [ ] **Verify RED:** `python3 -m pytest -q tests/test_segment_lifecycle.py` fails for the absent coordinator.
- [ ] **Implement:** Operation identity, same-core serialized `run`, normal and parent-derived producer admission, idempotent retirement, cancellation before stop, stop/retirement fault latching, and hook calls outside locks. Keep legacy-sharing protection in engine hooks.
- [ ] **Verify GREEN:** `python3 -m pytest -q tests/test_segment_lifecycle.py`; run `git diff --check`.
- [ ] **Commit:** `feat: add shared segment lifecycle coordinator`.

### Task 2: Once-only delivery and reentrant teardown

**Files:** Modify `runtime/segmentLifecycle.py`, `tests/test_segment_lifecycle.py`.

**Interfaces:** Preserve Task 1 API; terminal delivery uses `SegmentOperation.work` and `PlaybackWork.complete_drained()` / `.fail(error)` on a coordinator-owned queue, never from hook/callback stacks.

- [ ] **Write failing tests:** `test_cancel_before_deferred_delivery_is_silent`, `test_failure_wins_over_queued_success`, `test_sink_can_cancel_and_terminate_without_self_join`, `test_raising_sink_does_not_relabel_successor`, `test_terminate_blocks_new_acceptance`. Assert at most one original-context terminal event and no callback/worker-thread sink call.
- [ ] **Verify RED:** `python3 -m pytest -q tests/test_segment_lifecycle.py -k 'delivery or failure or sink or terminate'` fails at the new assertions.
- [ ] **Implement:** One delivery worker/queue per lifecycle, operation ownership until delivery commit, queued event invalidation, lock-free sink call, and shutdown behavior safe from its own worker. Preserve the first failure and suppress terminal delivery for cancelled operations.
- [ ] **Verify GREEN:** `python3 -m pytest -q tests/test_segment_lifecycle.py`; `git diff --check`.
- [ ] **Commit:** `feat: serialize correlated segment delivery`.

### Task 3: OneCore adapter

**Files:** Modify `driver/OneCore/__init__.py`, `tests/test_onecore_segment_drain.py`.

**Interfaces:** Consume `SegmentLifecycle` and hooks from Tasks 1–2. OneCore hook keeps `ocSpeech_speak`, fixed callback ownership, `CallbackGate`, final feed and `sync`; settings tuples and legacy `speak` remain on the existing queue.

- [ ] **Write failing actual-wrapper tests:** `test_onecore_uses_shared_lifecycle_for_empty_and_pcm_segments` and `test_onecore_shared_handoff_waits_for_callback_feed_and_stop`. Assert operation/coordinator ownership, no event before native callback return or `sync`, no successor native call during held old feed/stop, and original `source_id`/`segment_id` after release.
- [ ] **Verify RED:** `python3 -m pytest -q tests/test_onecore_segment_drain.py -k 'shared_lifecycle or shared_handoff'` fails.
- [ ] **Implement:** Adapt `speak_segment`, `_runSegmentQueue`, `_callback`, `_retireSegmentNative`, `_feedSegment`, `cancel`, `terminate` to the common coordinator and OneCore hooks; remove contextual-only duplicate terminal/order state when replaced. Preserve settings identity, pause/resume and legacy DONE.
- [ ] **Verify GREEN:** `python3 -m pytest -q tests/test_onecore_segment_drain.py tests/test_segment_lifecycle.py`.
- [ ] **Commit:** `refactor: route OneCore segments through lifecycle`.

### Task 4: Neural adapter

**Files:** Modify `driver/Neural/__init__.py`, `tests/test_neural_segment_drain.py`.

**Interfaces:** Consume the coordinator; Neural hooks retain `_SegmentSpeakTask` / `_SegmentDrainTask`, SDK stop, `CallbackGate`, bookmark/audio ownership, Sonic tail feed and player `idle`.

- [ ] **Write failing actual-wrapper tests:** `test_neural_shared_lifecycle_waits_for_all_langchange_tasks_and_sonic_idle` and `test_neural_cancelled_callback_cannot_feed_successor`. Assert one terminal event per multi-task segment, no event before last Sonic feed/idle, and no second native submission while old callback/stop is held.
- [ ] **Verify RED:** `python3 -m pytest -q tests/test_neural_segment_drain.py -k 'shared_lifecycle or cancelled_callback_cannot_feed_successor'` fails.
- [ ] **Implement:** Bind all segment tasks to one `SegmentOperation`; pass leases through audio/bookmark and nested feed paths; delegate native boundary, stop, retirement and final idle through hooks. Keep `_confirm_native_quiescence`'s explicit unverified activation status and the separate contextual legacy path.
- [ ] **Verify GREEN:** `python3 -m pytest -q tests/test_neural_segment_drain.py tests/test_segment_lifecycle.py`.
- [ ] **Commit:** `refactor: route Neural segments through lifecycle`.

### Task 5: VE adapter

**Files:** Modify `driver/VE/__init__.py`, `tests/test_vocalizer_segment_drain.py` (VE parametrization).

**Interfaces:** Consume the coordinator; VE hook owns `ProcessText2Speech`, `_ContextualVECallback`, `CallbackGate`, `_GuardedPlayer`, native stop and actual player idle. Keep VE-specific type decoding.

- [ ] **Write failing VE actual-wrapper tests:** `test_ve_shared_lifecycle_waits_for_chunk_callback_and_idle` and `test_ve_shared_cancel_retires_guarded_feed_before_successor`. Restrict these tests to VE within the existing two-engine fixture. Assert no early DRAIN/native handoff, old index isolation, and exactly one original-context event after barrier release.
- [ ] **Verify RED:** `python3 -m pytest -q tests/test_vocalizer_segment_drain.py -k 've_shared'` fails.
- [ ] **Implement:** Route contextual `speak_segment`, chunk producer leases, guarded feed, cancellation and terminal delivery through VE hooks/coordinator; preserve VE callback parsing, settings, and guard-based capability check.
- [ ] **Verify GREEN:** `python3 -m pytest -q tests/test_vocalizer_segment_drain.py tests/test_worldvoice_cancel_wrappers.py`.
- [ ] **Commit:** `refactor: route VE segments through lifecycle`.

### Task 6: Cerence adapter

**Files:** Modify `driver/Cerence/__init__.py`, `tests/test_vocalizer_segment_drain.py` (Cerence parametrization).

**Interfaces:** Same coordinator API as Task 5, with Cerence's own `ProcessText2Speech`, `_ContextualCerenceCallback`, type decoding, `_GuardedPlayer` and native stop.

- [ ] **Write failing Cerence actual-wrapper tests:** `test_cerence_shared_lifecycle_waits_for_chunk_callback_and_idle` and `test_cerence_shared_cancel_retires_guarded_feed_before_successor`. Restrict these tests to Cerence within the existing two-engine fixture. Assert the same ordering and original identity using Cerence marker/data shapes, including late callback rejection.
- [ ] **Verify RED:** `python3 -m pytest -q tests/test_vocalizer_segment_drain.py -k 'cerence_shared'` fails.
- [ ] **Implement:** Migrate contextual operation and guarded callback/feed to Cerence hooks; retain its distinct native types, stop path and capability checks. Remove only duplicated lifecycle logic.
- [ ] **Verify GREEN:** `python3 -m pytest -q tests/test_vocalizer_segment_drain.py tests/test_worldvoice_cancel_wrappers.py`.
- [ ] **Commit:** `refactor: route Cerence segments through lifecycle`.

### Task 7: SAPI5 WASAPI adapter

**Files:** Modify `driver/SAPI5/__init__.py`, `tests/test_sapi5_segment_drain.py`, `tests/test_runtime_completion_policies.py`.

**Interfaces:** Consume the coordinator only when `useWasapi` and the owned player are available. Hook retains request/stream ID, `EndStream`, complete PCM feed, final WavePlayer `idle`, COM stop and player cleanup. Legacy audio continues `LEGACY_DONE`.

- [ ] **Write failing actual-wrapper tests:** `test_sapi5_wasapi_shared_lifecycle_waits_for_endstream_pcm_and_idle`, `test_sapi5_shared_cancel_blocks_request_handoff`, and `test_sapi5_legacy_stays_legacy_done`. Assert `EndStream` alone does not drain, stale stream/index never completes the next request, and policy chooses legacy before its first segment.
- [ ] **Verify RED:** `python3 -m pytest -q tests/test_sapi5_segment_drain.py tests/test_runtime_completion_policies.py -k 'sapi5_wasapi_shared or sapi5_shared_cancel or sapi5_legacy_stays'` fails.
- [ ] **Implement:** Attach a `SegmentOperation` to the existing request binding; bridge COM/PCM/EndStream consumers to leases and expose SAPI5 stop, native boundary and final WASAPI idle as hooks. Keep `_initTts` / `_initWasapiAudio` replacement behavior and legacy `speak` path.
- [ ] **Verify GREEN:** `python3 -m pytest -q tests/test_sapi5_segment_drain.py tests/test_runtime_completion_policies.py`.
- [ ] **Commit:** `refactor: route SAPI5 WASAPI segments through lifecycle`.

### Task 8: eSpeak adapter

**Files:** Modify `driver/Espeak/__init__.py`, `tests/test_espeak_segment_drain.py`.

**Interfaces:** Consume the coordinator; hook retains `_execWhenDone` FIFO ownership, `_speak` native return, index/end callback, `_SegmentPlayer` feed/onDone and final player idle/stop.

- [ ] **Write failing actual-wrapper tests:** `test_espeak_shared_lifecycle_waits_for_fifo_and_empty_audio_idle` and `test_espeak_token_cancel_after_feed_discards_pcm_before_successor`. Assert no event before both FIFO return and player idle, old callback/index identity, no early successor native call, and cancelled work emits nothing.
- [ ] **Verify RED:** `python3 -m pytest -q tests/test_espeak_segment_drain.py -k 'espeak_shared_lifecycle or espeak_token_cancel_after_feed'` fails.
- [ ] **Implement:** Bind `_NativeSpeech` and nested player consumers to the operation; move contextual retirement, stop and terminal ordering to hooks/coordinator while retaining native FIFO and ordinary `speak` behavior.
- [ ] **Verify GREEN:** `python3 -m pytest -q tests/test_espeak_segment_drain.py tests/test_segment_lifecycle.py`.
- [ ] **Commit:** `refactor: route eSpeak segments through lifecycle`.

### Task 9: RHVoice adapter

**Files:** Modify `driver/RHVoice/__init__.py`, `tests/test_rhvoice_segment_drain.py`.

**Interfaces:** Consume the coordinator; hook retains inner worker/native return, native done, admitted and nested callback/feed, final player idle, stop and player cleanup. Do not edit `driver/RHVoice/driver/`.

- [ ] **Write failing actual-wrapper tests:** `test_rhvoice_shared_lifecycle_waits_for_nested_feed_and_final_idle`, `test_rhvoice_shared_cancel_keeps_old_identity_until_retirement`, and `test_rhvoice_shared_sink_reenters_terminate`. Assert no early DRAIN, no successor submission while old nested feed/stop runs, original identity, and no sink self-join.
- [ ] **Verify RED:** `python3 -m pytest -q tests/test_rhvoice_segment_drain.py -k 'rhvoice_shared'` fails.
- [ ] **Implement:** Connect `_QueuedSpeech`, `_NativeCallback`, `_WavePlayer`, queue, `cancel` and `terminate` to RHVoice hooks/operation leases. Preserve inner XML/settings and the already enabled profile policy.
- [ ] **Verify GREEN:** `python3 -m pytest -q tests/test_rhvoice_segment_drain.py tests/test_segment_lifecycle.py`.
- [ ] **Commit:** `refactor: route RHVoice segments through lifecycle`.

### Task 10: Cross-engine integration and delivery record

**Files:** Modify `tests/test_runtime_drain_integration.py`, `tests/test_runtime_completion_policies.py`, `docs/superpowers/finish_task.md`; modify `readme.md` only if its test-package statement changes. No production changes unless a test exposes a defect, which returns to the owning task.

**Interfaces:** Consume all seven migrated wrappers and unchanged policy/adapter/bridge/scheduler APIs. Produce a complete validation and commit record.

- [ ] **Add integration assertions:** `test_seven_enabled_profiles_use_shared_lifecycle`, `test_switch_waits_for_original_correlated_drain`, `test_sapi5_legacy_first_segment_remains_legacy_done`, and `test_unknown_engine_fallback_unchanged`. Check actual outer cores, event identity, no successor start before old drain, and policy mode before playback.
- [ ] **Verify integration:** `python3 -m pytest -q tests/test_runtime_drain_integration.py tests/test_runtime_completion_policies.py` passes. Fix only integration glue here; send any hook or coordinator defect back to its owning task and repeat its focused suite/review.
- [ ] **Verify delivery:** `python3 -m pytest -q tests`; `git diff --check`; build with `scons version=6.2-test-correlated-drain-1-9999 channel=dev` in clean isolated source, then check ZIP integrity, tracked source-to-package bytes and protected native hashes. Record exact counts/results and Windows validation limits.
- [ ] **Document and commit:** Update `docs/superpowers/finish_task.md` with all new implementation/review/validation commits and any package hash; commit integration tests and delivery record.

## Review and Execution Handoff

Use the user's previously requested subagent-driven method: one `gpt-6-sol high` implementation agent per task, a separate `gpt-6-astra high` reviewer agent for that task, and main-agent review before accepting it. Return Critical/Important spec or bug findings to the implementation agent and repeat review after correction. After Task 10, main agent and a fresh `gpt-6-astra high` agent review the integrated seven-engine change. Treat the previous review waiver as applying only to the completed DRAIN activation, not this refactor.

The execution gate remains separate from this document: review this plan before starting product code. The later SAPI5 legacy audio DRAIN change needs its own playback-barrier design and plan.
