# Shared segment lifecycle delivery record

**Branch:** `test/force-segment-end-index-all-engines`

**Date:** 2026-09-30

**Build source:** detached commit `ee6d0b8`; integration assertions committed separately as `e1ebe34`.

One common `SegmentLifecycle` now owns contextual operation admission, producer leases, failure and cancellation state, resource handoff, and terminal event delivery. The outer OneCore, Neural, VE, Cerence, SAPI5 WASAPI, eSpeak, and RHVoice wrappers use it while retaining their native submission, callback, stop, and player barriers. SAPI5 legacy audio continues to choose `LEGACY_DONE` before its first segment. Unknown and external engines retain the same fallback. The enabled profile selection is an explicit prior user request; it does not establish physical playback or SDK callback exclusion on Windows.

## Verification

- `python3 -m pytest -q tests/test_runtime_drain_integration.py tests/test_runtime_completion_policies.py`: **205 passed** in 7.06s.
- `python3 -m pytest -q tests`: **1,275 passed, 9 skipped** in 37.82s.
- `git diff --check`: exit 0 before the integration commit; repeated for this record.
- The integration harness uses the real manager, sessions, adapters, index ledger, scheduler, event bridge, and four opened outer wrappers over controlled native and player boundaries. Separate actual-wrapper fixtures cover SAPI5, eSpeak, and RHVoice. The seven-profile assertion checks installed outer core identity, shared coordinator ownership, and policy choice before speech. The switch assertion holds the original player's drain, checks that the successor has not submitted, and checks the original `source_id` and `segment_id` on the released DRAIN event.

The build used SCons 4.11.1 and Markdown 3.11 installed in `/tmp/worldvoice-task10-venv`, with system gettext. Command: `scons version=6.2-test-correlated-drain-1-9999 channel=dev` from the clean detached source `/tmp/worldvoice-task10-build-ee6d0b8`. It exited 0. The artifact remains in that isolated build checkout; the ignored root artifact and its README annotation remain the earlier activation package.

| Build audit | Result |
| --- | --- |
| Artifact | `WorldVoice-6.2-test-correlated-drain-1-9999.nvda-addon` |
| Size | 10,613,480 bytes |
| SHA-256 | `bfec2cbdebc7653443ff3885166e58f97df63cf03f3f2b331d1f5aeeaa1fe2ab` |
| ZIP | 122 unique entries; every CRC passed; paths safe; no bytecode or cache entries |
| Source consistency | All 99 tracked add-on files match the detached source bytes in the package |
| Protected baseline | All 20 Neural, VE, and Cerence inner/native/manifest files match the earlier activation package byte for byte |
| Manifest | Version `6.2-test-correlated-drain-1-9999`, update channel `dev` |

No Windows NVDA instance, physical audio device, loaded VE/Cerence SDK, or measured callback quiescence was used. The Linux tests prove behavior against controlled native and audio boundaries; installation, listening and tail timing, loaded SDK provenance, and real Windows profile acceptance remain open. SAPI5 legacy audio was intentionally left on `LEGACY_DONE`.

## New commits in this change

The following exact short SHA and subject pairs include design, plan, implementation, corrections, and the cross-engine validation commit. The documentation commit containing this record is identified in the Task 10 handoff because a commit cannot contain its own SHA. The complete history can be checked with `git log --reverse --format='%h %s' 3603004^..HEAD`.

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
