# Segment-index completion validation — evidence pending

Recorded 2026-09-27 on a Linux host (`uname -s` returned `Linux`). **Task 8 is incomplete pending Windows/NVDA/device access.** No real engine/profile has been validated or migrated. The production `_VERIFIED_CONTRACTS` table remains empty; every profile selects `LEGACY_DONE` with no index range. No marker policy rows or drain/failure hooks were added.

## Evidence boundaries

- **Source observations:** the repository contains the wrappers and event paths listed below. These establish inspection targets only. They do not prove that an installed driver accepts an `IndexCommand` subclass, preserves indexes, accepts a particular integer range, or finishes physical audio at any callback.
- **Fake tests:** Linux tests use NVDA stubs, fake engines and fake audio. Their results cover policy fallback and software contracts only. They are not hardware evidence and cannot authorize a production opt-in.
- **Hardware evidence:** none collected. There is no Windows NVDA runtime, installed engine/version inventory, device measurement, listening result or real event trace from this run. Driver availability on a future Windows host is unverified, including external drivers.

## Per-profile evidence matrix

`U` means **unverified / not run on Windows hardware** in every hardware cell below. `default`, `wasapi` and `legacy` are intended policy-key labels, not observations of an opened audio device. The version column requires the exact NVDA version; the engine column also requires the actual driver/DLL version when a run becomes possible. Add separate rows for every tested version/audio-mode combination; do not extrapolate to neighboring versions.

| Engine / driver version | NVDA version | Audio mode | Subclass acceptance | Verified index range | Order & adjacent skip | Empty text | Marker vs speak-return | Audio-tail timing | Cancel | Failure signal | Selected mode | Source location | Hardware date / result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OneCore / U | U | `default` (actual U) | U | U; none approved | U | U | U | U | U | U | `LEGACY_DONE` | S1 | No hardware date; U |
| SAPI5 / U | U | `wasapi` (actual U) | U | U; none approved | U | U | U | U | U | U | `LEGACY_DONE` | S2 | No hardware date; U |
| SAPI5 / U | U | `legacy` (actual U) | U | U; none approved | U | U | U | U | U | U | `LEGACY_DONE` | S2 | No hardware date; U |
| VE / U | U | `default` (actual U) | U | U; none approved | U | U | U | U | U | U | `LEGACY_DONE` | S3 | No hardware date; U |
| Cerence / U | U | `default` (actual U) | U | U; none approved | U | U | U | U | U | U | `LEGACY_DONE` | S4 | No hardware date; U |
| RHVoice / U | U | `default` (actual U) | U | U; none approved | U | U | U | U | U | U | `LEGACY_DONE` | S5 | No hardware date; U |
| Espeak / U | U | `default` (actual U) | U | U; none approved | U | U | U | U | U | U | `LEGACY_DONE` | S6 | No hardware date; U |
| Available external: inventory/name/version U | U | U | U | U; none approved | U | U | U | U | U | U | `LEGACY_DONE` | S7; installed driver path U | No hardware date; U |

## Source observations and locations

Paths are relative to the repository root. These were read without modifying NVDA, `ref/`, or embedded lower-level drivers.

- **S1:** `addon/synthDrivers/WorldVoice/driver/OneCore/driver/__init__.py`, `OneCoreSynthDriver`: imports `synthDrivers.oneCore.SynthDriver` and adds language accessors. Inspect the exact installed NVDA `synthDrivers/oneCore.py` and its native bridge before proposing a range or timing contract. Those installed sources and runtime behavior were not verified here.
- **S2:** `addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py`, `Voice`: uses NVDA `synthDrivers.sapi5.SynthDriver`. `addon/synthDrivers/WorldVoice/__init__.py`, `_completion_for`: selects SAPI5 `wasapi`, `legacy`, or `unknown` from the opened core. Inspect the exact installed `synthDrivers/sapi5.py` and engine implementation independently for each audio mode; neither mode has hardware evidence here.
- **S3:** `addon/synthDrivers/WorldVoice/driver/VE/__init__.py`, `CancellableSynthDriver.speak`, `cancel`, `_onIndexReached`: contains cancellation guards. `addon/synthDrivers/WorldVoice/driver/VE/driver/__init__.py`, `SynthDriver.speak` and `_onIndexReached`: contains index handling and notifications. `driver/ve2/veTypes.py` defines native mark fields. None of these establishes accepted DLL bounds or physical drain timing.
- **S4:** `addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py`, `CancellableSynthDriver.speak`, `cancel`, `_onIndexReached`: contains cancellation guards. `addon/synthDrivers/WorldVoice/driver/Cerence/driver/__init__.py`, `SynthDriver.speak` and `_onIndexReached`: contains index handling and notifications. `driver/ttsapi/veTypes.py` defines native mark fields. These require independent installed-version verification, even where source resembles VE.
- **S5:** `addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py`, `Voice`: selects the bundled driver. `addon/synthDrivers/WorldVoice/driver/RHVoice/driver/__init__.py`, `RHVoice_callback_types.process_mark`, `SynthDriver.speak` and `cancel`: provides native callback and submission inspection targets. A declared C callback type alone does not verify mark parsing, ordering or playback completion.
- **S6:** `addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py`, `Voice`: imports NVDA `synthDrivers.espeak.SynthDriver`. The exact installed NVDA driver, native library, player and version remain to be inspected on Windows.
- **S7:** `addon/synthDrivers/WorldVoice/engine/__init__.py` supplies `WorldVoice-workspace` as the external root; `addon/synthDrivers/WorldVoice/engine/discovery.py`, `_iter_external_candidates` and `discover_engine_specs`, locates external manifests. Inventory the actual Windows workspace and add one row per available external engine/profile. The fake `external-test-engine` policy key is not an installed external engine.

The shared policy is `addon/synthDrivers/WorldVoice/compat/completionPolicies.py`, `get_completion_contract`. `addon/synthDrivers/WorldVoice/runtime/models.py`, `CompletionContract`, defaults to `LEGACY_DONE` and no range. The empty exact-key table is source evidence for conservative selection, not a claim about hardware capability.

## Windows probe plan — all not run

Keep each item unchecked until its associated real evidence is retained. Run every applicable scenario for every matrix row, separately for SAPI5 WASAPI and legacy. Missing engines remain unverified.

- [ ] Record Windows build, exact NVDA build/version, WorldVoice commit, engine/DLL version, voice, language, rate settings, output device/backend and actual opened audio mode. Inventory external drivers and capture their installed source/manifest paths. Associate each artifact with the exact `(engine, nvda_version, audio_mode)` key and run date.
- [ ] Inspect the exact installed driver/native boundary and documented parser/storage limits before selecting test integers. Then test a safe low positive value, a safely supported value beyond NVDA's usual index range, and the candidate upper bound. Record the actual numbers, round-trip callback values and supporting source locations. No Python `int` assumption, guessed DLL bound, unreviewed oversized integer or approved range exists in this report.
- [ ] Submit both ordinary `IndexCommand` and the WorldVoice internal subclass, including adjacent indexes around short text, long text and the end marker. Trace whether each is accepted, skipped, reordered, duplicated, truncated or transformed. Test text with no caller indexes as well. Require ordered observations and usable terminal-marker behavior for the claimed contract.
- [ ] Exercise empty text, an empty sequence, whitespace-only text, and command-only sequences (including adjacent indexes, setting changes and breaks). Record return, marker, done and audio events, including absent callbacks; do not treat a timeout as completion.
- [ ] For short and long speech, record submission start, `speak` return, every index callback, done/drain callback, actual audio tail and next-segment audio start on a common monotonic timeline. Test synchronous and asynchronous delivery. Listen and retain an audio capture with an alignment method so premature switching and overlap can be assessed independently of callback timestamps.
- [ ] Cancel repeatedly during synthesis, queued audio and the final tail, then replay immediately. Exercise A→B→A and stale callbacks from cancelled work. Record cancel request/return and late notifications, verify cancelled audio stops, and verify a stale event cannot finish or advance new speech.
- [ ] Exercise same-engine and cross-engine switching, pauses/breaks, say-all, configuration/voice changes and pause/resume (including near the terminal marker). Verify actual playback has no premature switch, overlap, skipped segment or hang; retain the event trace and listening/capture result for each scenario.
- [ ] With a controlled recoverable failure, record submission exceptions and any asynchronous engine failure notification, its source identity, and whether queued work can recover. Missing or unidentifiable failure signals stay explicitly unverified; never re-label an anonymous done event as a drain/failure signal.

For each trace retain run/scenario IDs, exact profile, source ID, generation, segment ID, command kind/index, timestamp, thread, event type, cancellation state, exception/failure details and audio artifact references where observable. Record how events are correlated to submitted work. An unavailable field or signal must be recorded as unavailable rather than invented. Capture external instrumentation without changing NVDA, `ref/`, or embedded lower-level drivers.

## Opt-in gate and unfinished migration

`END_INDEX` requires real evidence that terminal-marker completion satisfies the audio-tail contract for the exact profile. If the marker arrives before the tail, `END_INDEX_AND_DRAIN` additionally needs a reliable, source-bound drain signal; without it retain `LEGACY_DONE`. If a future WorldVoice-only hook is required, capture the original `PlaybackContext` when work is submitted and emit `PlaybackEvent(SEGMENT_DRAINED, context.source_id, segment_id=context.segment_id)` through the adapter's keyword-only `event_sink` supplied by `voiceManager`. A global current context or unlabelled done notification is insufficient. No such hook was introduced in this run.

- [ ] Execute the Windows matrix and attach dated real event/audio evidence.
- [ ] For each proven exact key, add `test_verified_profile_selects_recorded_contract` asserting the report's exact mode and range, while neighboring unknown versions stay legacy. Add synchronous, delayed, duplicate and post-cancel stale hook fixtures if a hook is needed.
- [ ] Re-run affected policy/adapter/wrapper tests and the same Windows scenarios after implementation. Mark a row migrated only after fake contracts pass **and** real hardware satisfies the selected mode.
- [ ] Commit each verified profile separately. Complete Task 8 only after all built-in engine requirements pass; record unavailable external profiles separately.

## Linux fake-test results

Executed 2026-09-27:

```text
python3 -m pytest tests/test_runtime_completion_policies.py tests/test_runtime_adapter_contract.py tests/test_runtime_legacy_adapter.py tests/test_worldvoice_cancel_wrappers.py tests/test_f4_engine_adapters.py -q -p no:cacheprovider
209 passed in 2.73s
```

The fallback test now covers all matrix engine categories, both SAPI5 modes, unknown audio modes, unknown engine names and the illustrative version strings `unknown`, `2026.1`, `2026.1.1`, `2026.2`. These version strings are test inputs, not an installed-version inventory. Every tested profile explicitly asserts `LEGACY_DONE` and no index range. The other tests exercise existing adapter and wrapper software contracts using fakes. **No result in this section fills a hardware matrix cell or completes Task 8.**

## Task 9 final software validation — 2026-09-27

**Tasks 1–7 and 9 are complete. Task 8 remains incomplete pending Windows/NVDA/device evidence. F7 is not resolved in production.** The final tested code/test revision is `568c9026b52766119a7edf5ab52ffa8c10cd2c13`; Task 9 changes documentation only. All eight matrix rows above remain unverified and all production profiles remain `LEGACY_DONE`. No production marker completion contract, approved integer range, or physical drain/failure hook is enabled.

Final execution in `/tmp/worldvoice-segment-index` on Linux, after Task 8's policy-test changes:

```text
python3 -m pytest tests -q -p no:cacheprovider
569 passed in 7.78s
exit code: 0

git diff --check
(no output)
exit code: 0
```

Only `tests` was collected; `ref/nvda` was not collected. The 569 results are software/fake/stub evidence, including conservative profile fallback cases added in Task 8. They supersede the 507-test Task 7 count for this final revision. Documentation-only edits do not change that tested revision's executable behavior. Staged whitespace and document consistency checks are recorded in the Task 9 execution report.

### Focused changed-code audit

Paths below use `WV = addon/synthDrivers/WorldVoice`. Inspection covered the changed runtime, codec, ledger, adapter, bridge and composition paths, against spec §§4–9. No additional defect requiring a code change was found in this focused audit. This statement does not certify any real driver's marker or audio semantics.

| Requirement | Inspected implementation and concrete regression evidence | Result |
| --- | --- | --- |
| Runtime dependency boundary | AST-walked every import in `WV/runtime/*.py`, including nested imports: 26 import statements, all standard library or runtime-local; `rg` also supplied the textual import inventory. `tests/runtime_harness.py::forbid_legacy_runtime_imports` wraps native contract execution through teardown. | No NVDA/speech/compat/driver dependency in runtime. |
| Builder and normalizer do not inject markers | `WV/runtime/requestBuilder.py::queue_speech_sequence` flushes nonempty speech on selection, pause and end; `WV/compat/commands.py::normalize_legacy_commands` rejects incoming internal markers and converts Voice/Break only. `test_select_pause_and_end_flush_only_nonempty_segments`, `test_full_sequence_normalizes_without_inserting_internal_markers`. | Segmentation stays in builder; no allocation or marker append there. |
| Sole marker construction path | AST searched every call in `WV/**/*.py`: the only `WorldVoiceIndexCommand(...)` construction is `WV/compat/indexCodec.py:27`. `encode_segment` snapshots/validates first, prepares the full allocation, copies caller indexes and appends once. `LegacyEngineAdapter.speak` calls it only for marker contracts. `test_complete_select_pause_sequence_has_exactly_three_markers`, `test_original_indexes_round_trip_without_internal_marker_leak`. | Exactly one boundary construction path; legacy profiles append no marker. |
| No wire reuse or alias allocator collision | `WV/indexLedger.py::bind/prepare/unbind/retire_source` retain strong source identity and a monotonic high water; exhaustion rejects a complete allocation before send. `WV/voiceManager.py` reuses the owner's session and rejects conflicting alias contracts. `test_same_source_rebind_preserves_high_water`, `test_exhaustion_is_atomic`, `test_alias_uses_one_allocator_and_one_close`, `test_live_core_rebind_preserves_allocator_high_water`. | Retire/unbind do not reset a live source; a new ledger must not be attached to an unclosed old core. |
| Binding generation and ordered decode/delivery | `WV/nvdaEventBridge.py::_receive` passes a deferred supplier with its captured `ledger_token`; `WV/indexLedger.py::receive_index` checks that token under its lock. `WV/runtime/scheduler.py::on_events` invokes decode and delivers the complete batch under delivery lock, outside state lock for output. `test_supplier_cannot_decode_replacement_binding_after_validation`, `test_decode_binding_token_cannot_consume_replacement_segment`, `test_index_delivery_precedes_terminal_batch`, `test_index_callback_cancels_remaining_batch`. | Task 4 race fix is retained; old binding cannot consume replacement mapping and cancellation stops the remaining batch. |
| Activation independent of segment | `WV/runtime/session.py::activate` stores exactly `(self.source_id, key, snapshot.revision)`. `speak` accepts each distinct `PlaybackContext` even when activation returns False. `test_same_voice_two_segments_preserve_activation_cache`, `test_cached_activation_still_speaks_two_distinct_segments`, `test_marker_a_b_a_restores_voice_and_settings`, `test_marker_pending_apply_pending_discard`. | Segment/epoch/wire index do not enter activation cache. |
| Single request completion and public done owner | Searches for `set_result`, `set_exception`, `RequestState.COMPLETED`, `done_sent` and `done_speaking(` in the relevant boundary/runtime paths locate state/Future settlement in `WV/runtime/scheduler.py`; `_worker/_run_one/_finish_task_locked` own submitted-task completion. `on_events` only stores signals/errors and wakes; it never starts the next task or settles its Future. `_deliver_done` makes the sole runtime output call; `NvdaEventBridge.done_speaking` is the owner-filtered NVDA notification adapter. Empty request completion remains the scheduler's existing submit path. `test_trailing_pause_and_non_speech_done_policy`, `test_missing_marker_failure_releases_request_once`, `test_marker_pause_cancel_current_and_future_callback`. | Successful done waits for the entire request; FAILED may release upper-layer wait once without claiming success; cancellation suppresses done. |
| Failure and tail barrier | `_run_one` waits for `speak` return, then delivery completion, validity, error and required END/DRAIN flags. `test_end_waits_for_speak_return`, `test_end_then_speak_error_is_failure`, `test_end_and_drain_require_same_segment`, `test_done_without_end_is_not_success`, `test_boundary_errors_do_not_leave_waits_or_kill_worker`. | Fake events establish software ordering only; real tail timing remains Task 8. No arbitrary done or timer fabricates drain. |
| Ledger close and shutdown | `WV/indexLedger.py::close` marks closed and clears bindings/sources under lock, then releases references outside it; `receive_index` returns empty and bind/prepare reject work after close. `WV/__init__.py::terminate` stops worker, closes bridge, closes manager/resources, then closes ledger. `test_close_releases_source_retained_through_unbind_and_rejects_work`, `test_close_releases_sources_after_unlocking`, `test_shutdown_disables_late_index_before_engine_close`. | Late callbacks cannot revive closed ledger state. A forever-blocking synchronous native call remains an existing shutdown limitation. |

Additional scope command: `git diff --name-only 23b176d..568c902 -- addon/synthDrivers/WorldVoice/driver ref` returned no paths (exit 0). No embedded lower-level driver, `ref/` or NVDA source was modified. AST audit returned `PASS: 26 runtime import statements contain no forbidden dependency; one production marker constructor: [('addon/synthDrivers/WorldVoice/compat/indexCodec.py', 27)]` (exit 0).

### Spec and task coverage

Test names above and below refer to actual collected tests, not proposed scenarios. Every software row passed in the final 569-test run; production applicability still depends on the empty opt-in table and Task 8.

| Spec acceptance | Tasks | Delivered evidence | Status |
| --- | --- | --- | --- |
| §§1–3 names, scope, per-adapter migration | 1, 6, 8, 9 | `_speechcommand.py`, `runtime/models.py`, exact-key `completionPolicies.py`, per-profile matrix | Core complete; real adapter migration pending. |
| §4; C13–15 activation/source/segment separation | 1, 3, 5, 7 | Session/adapter context tests; same-voice, A→B→A, rollback, failed apply and adapter replacement in `test_runtime_session.py` / `test_runtime_adapter_contract.py` | Software complete. |
| §5; D17 runtime boundaries/context/events | 1, 3, 4, 5, 6, 7 | Shared native/legacy contracts, import guard through teardown, `test_entry_point_imports_real_ledger_and_completion_policy` | Software complete. |
| §6; A1–6 command/index isolation/lifecycle | 1, 2, 3, 4, 6, 7 | `test_worldvoice_index_command.py`, `test_index_codec.py`, `test_index_ledger.py`, alias/rebind composition tests | Software complete; subclass acceptance and integer ranges on installed drivers unverified. |
| §7 marker/drain/legacy and audio handoff | 3, 5, 6, 8 | Synchronous return/error and END+DRAIN tests; conservative exact-key policy | Software complete; real audio handoff pending. |
| §8; B7–12 cancellation/failure/ordering | 2, 3, 4, 5, 6, 7 | `test_same_source_late_events_do_not_finish_next_segment`, `test_cancel_a_b_a_rejects_same_source_late_callbacks`, generation-token race and delivery-order tests; existing stop/cancel/shutdown regressions | Marker software contracts complete; legacy production has no F7 guarantee. |
| §9; C16 request done/failure policy | 5, 7 | Trailing pause/no-speech tests, failed request once-only release, callback cancellation and complete sequence tests | Software complete. |
| D18–19 installed engines and playback scenarios | 8, 9 | Eight unverified matrix rows and unchecked Windows probe plan above | Incomplete; no Windows/NVDA/device evidence. |
| D20 evidence layers | 8, 9 | Source observations, fake results and absent hardware results explicitly separated | Reporting complete; does not fill D18–19. |
| User clarification: SelectVoice/Pause/end segmentation; adapter-only marker | 1, 3, 7 | Builder/normalizer characterization and shared full-sequence contract, three speech segments/three markers/one pause/one done | Software complete. |

### Independent review record and remaining work

The task-by-task independent Astra reviews are recorded in `.superpowers/sdd/2026-09-27-worldvoice-segment-index/progress.md` and the corresponding task reports/diff artifacts. Tasks 1–7 were approved after their applicable fix loops. Task 1's fixture compatibility findings were fixed in `6f10eee`; Task 4's stale supplier/rebinding race was fixed in `885f575`, with deterministic tests named above and a scoped re-review. Task 8's evidence-status increment was approved; this approval did not certify any hardware profile. Task 9 performed the focused audit above and arranges its own document/evidence review through the parent execution workflow; no new independent whole-branch review is claimed here.

The only remaining implementation-plan task is the hardware-dependent part of Task 8: exact installed driver/version inventory, safe native index bounds, subclass/index/empty-command behavior, real audio tail and switching/cancel/failure traces, evidence-backed opt-ins and any required source-bound hooks, then repeat software and hardware validation per profile. Until those results exist, **do not claim F7 fixed in production**. No available software test can substitute for this evidence.
