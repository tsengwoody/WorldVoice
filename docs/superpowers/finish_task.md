# Shared segment lifecycle delivery record

**Branch:** `test/force-segment-end-index-all-engines`

**Date:** 2026-09-30; final review fixes and rebuild 2026-10-01

**Build source:** detached commit `b36b707`, the final commit that touches `addon/`. The earlier `ee6d0b8` build is superseded.

One common `SegmentLifecycle` now owns contextual operation admission, producer leases, failure and cancellation state, resource handoff, and terminal event delivery. The outer OneCore, Neural, VE, Cerence, SAPI5 WASAPI, eSpeak, and RHVoice wrappers use it while retaining their native submission, callback, stop, and player barriers. SAPI5 legacy audio continues to choose `LEGACY_DONE` before its first segment. Unknown and external engines retain the same fallback. The enabled profile selection is an explicit prior user request; it does not establish physical playback or SDK callback exclusion on Windows.

The later Neural correction `6caceb5` closes a cancellation race: `speak_segment` had accepted a lifecycle operation before registering its driver work, so `cancel()` could snapshot `_segmentWorks` in between and miss that operation. Acceptance and registration now share `_segmentCondition`; native calls, task construction, and event delivery remain outside that condition. A held-boundary regression covers the gap.

## Final review fix waves

A whole-branch review after `6caceb5` produced two fix waves. Each change stays in the outer wrappers or the shared coordinator; native submission, callback, stop and player barriers are unchanged.

- **OneCore and RHVoice admission-cancel atomicity** (`816fe6a`). OneCore registers each accepted operation under `_segmentCondition` before XML conversion and keeps it cancellation-visible until queue insertion and the queue-to-run handoff. RHVoice holds `_segmentAdmission` across lifecycle acceptance and `_segmentAccepted` registration, and cancellation takes the same lock before its snapshot.
- **Coordinator latched-fault delivery for queued Neural/SAPI5 operations** (`816fe6a`). `SegmentLifecycle.run()` converts a latched fault met by an accepted, unsubmitted operation into one coordinator-owned asynchronous `SEGMENT_FAILED` with the original context and first error, without native submission.
- **OneCore faulted-acceptance cancellation and retirement** (`65a8961`, `25f9fda`). Captured pre-run and queued operations stay visible to `cancel()` until lifecycle delivery or cancellation, so a cancelled pending failure is suppressed. `SegmentLifecycle.accept()` takes an optional `on_retired` callback, run on the dispatcher outside coordinator locks, which OneCore uses to clear accepted membership even when delivery was suppressed.
- **Ordinary-speech ownership behind contextual playback** (`b36b707`). VE and Cerence ordinary `speak()` held only `_speechRunLock`, which a contextual operation releases after native submission, so ordinary text could reach native and feed the shared player during the contextual final idle. Ordinary requests now wait for the coordinator resource (`_resource_busy`) to retire outside the run lock, as `_finish_termination` already does, and recheck it after acquiring the lock. A cancel that finds termination already sealed still releases pending contextual delivery waits. Actual-wrapper regressions cover ordinary speech behind the final idle, driver cancel and ordinary token cancel while waiting, and terminate while waiting, including an ordinary request that seals termination first. Parity probes on OneCore, Neural, SAPI5 WASAPI and RHVoice passed on the pre-fix source and remain as regressions: OneCore, SAPI5 WASAPI and RHVoice keep ordinary text queued behind the contextual final barrier on their single worker, and Neural refuses ordinary speech after correlated playback. eSpeak was fixed earlier in `fe25096`.

## Verification

- `python3 -m pytest -q tests/test_runtime_drain_integration.py tests/test_runtime_completion_policies.py`: **205 passed** in 7.06s at `e1ebe34`.
- Final focused command after `b36b707`: `python3 -m pytest -q tests/test_vocalizer_segment_drain.py tests/test_onecore_segment_drain.py tests/test_neural_segment_drain.py tests/test_sapi5_segment_drain.py tests/test_rhvoice_segment_drain.py tests/test_segment_lifecycle.py`: **395 passed, 9 skipped**.
- Final full command: `python3 -m pytest -q tests`: **1,298 passed, 9 skipped** (34.69s before the code commit; 33.65s before this record).
- `git diff --check`: exit 0 before the final code commit and before this record.
- The integration harness uses the real manager, sessions, adapters, index ledger, scheduler, event bridge, and four opened outer wrappers over controlled native and player boundaries. Separate actual-wrapper fixtures cover SAPI5, eSpeak, and RHVoice. The seven-profile assertion checks installed outer core identity, shared coordinator ownership, and policy choice before speech. The switch assertion holds the original player's drain, checks that the successor has not submitted, and checks the original `source_id` and `segment_id` on the released DRAIN event.

The build used SCons 4.11.1 and Markdown 3.11 installed in `/tmp/worldvoice-task10-venv`, with system gettext. Command: `scons version=6.2-test-correlated-drain-1-9999 channel=dev` from the clean detached worktree `/tmp/worldvoice-final-build-b36b707` (no tracked changes). It exited 0. The artifact remains in that isolated build directory; the ignored root artifact and its README annotation remain the earlier activation package.

| Build audit | Result |
| --- | --- |
| Artifact | `WorldVoice-6.2-test-correlated-drain-1-9999.nvda-addon` |
| Source | `b36b707` |
| Size | 10,614,751 bytes |
| SHA-256 | `10bbe05b7a78f46d9730c1f5fccc593928da44b3c473b42db35b772b1bcebf9f` |
| ZIP | 122 unique entries; every CRC passed; paths safe; no bytecode or cache entries |
| Source consistency | All 99 tracked add-on files match the detached source bytes in the package; the other 23 entries are generated manifests, translations and documentation |
| Protected baseline | All 22 Neural, VE, and Cerence inner/native/manifest files (everything under those engine directories except the outer `__init__.py`) match the earlier activation package byte for byte, and also match the superseded `ee6d0b8` build |
| Manifest | Version `6.2-test-correlated-drain-1-9999`, update channel `dev` |

No Windows NVDA instance, physical audio device, loaded VE/Cerence/Neural SDK, or measured callback quiescence was used. The Linux tests prove behavior against controlled native and audio boundaries; installation, listening and tail timing, loaded SDK provenance, and real Windows profile acceptance remain open. SAPI5 legacy audio was intentionally left on `LEGACY_DONE`.

## New commits in this change

The following exact short SHA and subject pairs, from `git log --reverse --format='%h %s' 3603004^..HEAD`, include design, plan, implementation, corrections, validation, and both final review fix waves.

- `3603004` docs: design shared segment lifecycle for seven engines
- `b7abba9` docs: plan shared segment lifecycle migration
- `c4bc29b` feat: add shared segment lifecycle coordinator
- `3aaef1c` fix: keep segment handoff behind player and submit barriers
- `50516f2` feat: serialize correlated segment delivery
- `9658150` fix: invalidate segment delivery atomically on teardown
- `083b0b3` refactor: route OneCore segments through lifecycle
- `9b04693` fix: preserve OneCore callback and rejection boundaries
- `13b97eb` fix: signal OneCore boundary after retirement returns
- `136cbae` fix: preserve rejected segment delivery through teardown
- `ae4c267` fix: cancel accepted OneCore rejection on termination
- `42b26cc` refactor: route Neural segments through lifecycle
- `14502c4` fix: keep Neural terminal delivery cancellable
- `c9e97e6` refactor: route VE segments through lifecycle
- `36727ff` fix: retire VE cancellation and player hooks safely
- `71e6c73` refactor: route Cerence segments through lifecycle
- `12df672` refactor: route SAPI5 WASAPI segments through lifecycle
- `13ae6cb` fix: retire queued SAPI5 work and reject stale streams
- `63c815d` refactor: route eSpeak segments through lifecycle
- `fe25096` fix: keep eSpeak player ownership through mixed speech cleanup
- `5a66990` refactor: route RHVoice segments through lifecycle
- `1dd9e2b` fix: fail closed after RHVoice message cleanup fault
- `ee6d0b8` test: hold RHVoice final idle before successor handoff
- `e1ebe34` test: verify seven shared lifecycle profiles and cross-engine handoff
- `d69b823` docs: record shared segment lifecycle delivery
- `6caceb5` fix: close Neural segment admission cancellation gap
- `0d60071` docs: record Neural admission race follow-up
- `fe371e6` docs: record post-delivery Neural admission fix
- `816fe6a` fix: preserve accepted segment cancellation and fault delivery
- `65a8961` fix: keep OneCore faulted acceptance cancellable
- `25f9fda` fix: retire OneCore acceptance after suppressed delivery
- `b36b707` fix: keep VE and Cerence ordinary speech behind contextual playback
- this record: docs: record final review fixes and rebuilt package
