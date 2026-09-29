# Correlated segment drain implementation

**Branch:** `test/force-segment-end-index-all-engines`

**Implementation status:** Runtime, outer wrappers and cross-engine integration are implemented and reviewed.
**Profile status:** The four real target profiles still select `LEGACY_DONE`; DRAIN activation requires native callback-quiescence and loaded SDK/source evidence that is not available here. Windows playback acceptance is outstanding.

The implementation connects a context-bound DRAIN event across the playback work/gate, index ledger, engine adapter, scheduler and NVDA event bridge. OneCore, Neural, VE and Cerence have outer wrappers with owned contextual callbacks, callback leases, cancel/fault handling, native handoff barriers and final player-idle checks. Completion policy selects DRAIN only for the installed custom driver when its explicit profile check returns supported. Current profiles report unsupported, so they use `LEGACY_DONE` from the first segment. SAPI5, Espeak and RHVoice retain experimental `END_INDEX` wire values `1..9999`; unknown/external engines use `LEGACY_DONE`.

The Neural inner driver, speech API, CFFI and SDK DLL bytes were user-provided untracked baseline files, committed by the user as `eb605cd`. They were treated as read-only. The 11 exact Neural baseline paths and SHA-256 values are recorded in the [validation record](finish/2026-09-28-worldvoice-correlated-drain-validation.md#task-6-neural-sdk-boundary-and-implementation-2026-09-28). All 20 protected Neural, VE, Cerence, manifest and native hashes were checked against the built package.

## Verification and delivery

- Cross-engine integration suite: **43 passed**, using the real manager, adapters, sessions, scheduler, ledger, bridge and all four wrappers with controlled native/player boundaries. Premature drain, binding-generation bypass and stale callback migration each made the intended assertion fail under independent process-local mutations.
- Final add-on suite: **1,060 passed** with `python3 -m pytest tests -q -p no:cacheprovider`. Bare repository collection exits 2 with **191 vendored NVDA collection errors** because this Linux environment lacks Windows/NVDA/liblouis dependencies; this is not a passing full-tree run.
- SCons built `WorldVoice-6.2-test-correlated-drain-1-9999.nvda-addon` from detached source commit `8d9aa78`. Size: **10,589,232 bytes**. SHA-256: `9e0cd0024492245d20738413a9c6a8369df0f2cb139322f44f8c76072cfdbbb5`. ZIP CRC, manifest/channel, payload hashes, protected files and absence of bytecode/cache entries were checked. The artifact is ignored and not committed.
- No Windows NVDA instance, audio device or matching external VE/Cerence SDK installation was available. Installation, listening/tail timing and the Windows/SDK matrix remain unchecked in the [validation record](finish/2026-09-28-worldvoice-correlated-drain-validation.md#task-11-test-package-and-validation-handoff). Synthetic callback proofs and fallback runs do not certify DRAIN.
- Tasks 1–10 received independent `gpt-6-astra high` reviews. Findings were returned to implementation subagents, fixed and re-reviewed before proceeding. Task 10 review noted a minor opportunity to clean imported test modules from `sys.modules` after fixture teardown; no order-dependent test failure was reproduced.
- Task 11 implementation subagent hit its usage limit after completing the build and most validation notes. The coordinator verified the artifact and final add-on suite and completed this delivery record. An independent `gpt-6-astra high` review approved the Linux implementation/package handoff with no Critical or Important findings; its two Minor documentation corrections were fixed. The reviewer independently reran all 1,060 add-on tests and verified the artifact and protected-file hashes. Windows validation and real-profile DRAIN activation remain outstanding.

OneCore still lacks verified provenance for the loaded native helper/source profile. Supplied Neural SDK files report version `1.50.0.28`, but no callback-quiescence contract or loaded provenance was established. VE's external SDK build and callback-exclusion contract were not verified. Cerence SDK DLLs were absent; its `0x0520`/`0x0200` constants identify structure versions, not a loaded product build. Therefore the wrappers and controlled DRAIN protocol are implemented, but **none of the four real engine profiles is accepted for DRAIN activation**.

## Commits included before this delivery-document commit

Design and plan records:

- `1d7ab27` — `docs: specify correlated drain for OneCore and Neural`
- `645ac47` — `docs: include VE and Cerence in correlated drain design`
- `45d3e8f` — `docs: plan correlated drain wrappers for four engines`

User-provided Neural baseline (not authored as part of implementation):

- `eb605cd` — `update`

Implementation and integration commits:

- `45ee035` — `feat: define correlated drain completion mode`
- `b46a8c8` — `fix: preserve end-index boundary while waiting for drain`
- `c73ad93` — `feat: correlate ordinary indexes with drain completion`
- `fba80fc` — `feat: guard segment work and native callback lifetimes`
- `9b91445` — `feat: bridge context-bound segment drain events`
- `afea3fa` — `feat: wrap OneCore with correlated playback drain`
- `e1b0750` — `fix: retire legacy OneCore audio and detach callbacks`
- `4878461` — `feat: wrap Neural with context-bound drain tasks`
- `85a25b7` — `fix: retire Neural stops and finish termination on player errors`
- `dbb55ef` — `feat: add correlated drain to VE cancellation wrapper`
- `22df6da` — `fix: preserve VE status and cancellation lifetimes`
- `6726032` — `feat: add correlated drain to Cerence wrapper`
- `75cf9c0` — `fix: synchronize Vocalizer pause and cancellation`
- `a139070` — `fix: latch Vocalizer pause failures before playback`
- `b9d144a` — `fix: retire Vocalizer player operations before shutdown`
- `3138497` — `feat: select supported driver drain contracts before playback`
- `518a6f4` — `fix: pass OneCore audio mode to drain support checks`
- `8d9aa78` — `test: cover cross-engine correlated drain integration`

The delivery-document commit is recorded separately in the final handoff because its SHA does not exist until after this file is committed. Verify the full branch history with `git log --reverse --format='%h %s' 4951d39..HEAD`.
