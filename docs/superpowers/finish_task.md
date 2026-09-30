# Correlated segment drain implementation

**Branch:** `test/force-segment-end-index-all-engines`

**Implementation status:** Runtime, six outer wrappers, evidence-gated policy selection and cross-engine integration are implemented and reviewed.
**Profile status:** All six real target profiles select `LEGACY_DONE`; DRAIN activation requires native callback-quiescence and loaded SDK/source evidence that is not available here. Windows playback acceptance is outstanding.

The implementation connects a context-bound DRAIN event across playback work, the index ledger, engine adapter, scheduler and NVDA event bridge. OneCore, Neural, VE, Cerence, SAPI5 and eSpeak have outer wrappers with owned contextual callbacks, callback retirement, cancel/fault handling and engine-specific playback barriers. SAPI5 correlates WASAPI requests through `EndStream`, full PCM callback retirement and final player idle; its legacy audio route remains unsupported. eSpeak correlates callback completion with FIFO retirement after `_speak` returns and delivers terminal events outside native/background worker stacks. Completion policy selects DRAIN only for the installed custom driver when its explicit profile check returns supported. Current real profiles report unsupported, so they use `LEGACY_DONE` from the first segment. RHVoice alone retains the test-branch experimental `END_INDEX` wire values `1..9999`; unknown/external engines use `LEGACY_DONE`.

The Neural inner driver, speech API, CFFI and SDK DLL bytes were user-provided untracked baseline files, committed by the user as `eb605cd`. They were treated as read-only. The 11 exact Neural baseline paths and SHA-256 values are recorded in the [validation record](finish/2026-09-28-worldvoice-correlated-drain-validation.md#task-6-neural-sdk-boundary-and-implementation-2026-09-28). All 20 protected Neural, VE, Cerence, manifest and native hashes were checked against the built package.

## Verification and delivery

- Cross-engine integration suite: **43 passed**, using the real manager, adapters, sessions, scheduler, ledger, bridge and all four wrappers with controlled native/player boundaries. Premature drain, binding-generation bypass and stale callback migration each made the intended assertion fail under independent process-local mutations.
- Final add-on suite for the expanded SAPI5/eSpeak implementation: **1,169 passed** with `pytest -q tests` (25.80s). Focused suites passed: SAPI5 **47**, eSpeak **21**, and policy/composition plus both wrapper suites **300**. Bare repository collection exits 2 with **191 vendored NVDA collection errors** because this Linux environment lacks Windows/NVDA/liblouis dependencies; the add-on suite is the passing repository-targeted run.
- SCons rebuilt `WorldVoice-6.2-test-correlated-drain-1-9999.nvda-addon` from the reviewed implementation and updated test-branch help. Size: **10,600,899 bytes**. SHA-256: `8a19f7e1facea936ef72b42a9e9947b9266d8484a97416eaec2bc565f56d9c2d`. The ZIP has 121 unique entries, all CRCs pass, paths are safe, and it contains no bytecode/cache files. All **98 tracked add-on files** match source bytes; the manifest uses version `6.2-test-correlated-drain-1-9999` and update channel `dev`. The artifact is ignored and not committed.
- No Windows NVDA instance, audio device or matching external VE/Cerence SDK installation was available. Installation, listening/tail timing and the Windows/SDK matrix remain unchecked in the [validation record](finish/2026-09-28-worldvoice-correlated-drain-validation.md#task-11-test-package-and-validation-handoff-2026-09-28). Synthetic callback proofs and fallback runs do not certify DRAIN.
- Tasks 1–10 received independent `gpt-6-astra high` reviews. Findings were returned to implementation subagents, fixed and re-reviewed before proceeding. Task 10 review noted a minor opportunity to clean imported test modules from `sys.modules` after fixture teardown; no order-dependent test failure was reproduced.
- Task 11 implementation subagent hit its usage limit after completing the build and most validation notes. The coordinator verified the artifact and final add-on suite and completed this delivery record. An independent `gpt-6-astra high` review approved the Linux implementation/package handoff with no Critical or Important findings; its two Minor documentation corrections were fixed. The reviewer independently reran all 1,060 add-on tests and verified the artifact and protected-file hashes. Windows validation and real-profile DRAIN activation remain outstanding.
- A separate holistic `gpt-6-astra high` review of tasks 1–11 found lifetime and failure-propagation defects across OneCore and Neural, plus a documentation anchor issue. The OneCore and Neural findings were fixed in `cf33129` and `f3415a8`; the documentation link was corrected here. Targeted RED/GREEN regressions, a full 1,117-test run, and artifact rebuild followed. The reviewer repeated the full review after the final callback reentrancy fix and approved with no remaining actionable findings. This approval covers Linux code and package consistency; it does not certify Windows playback, SDK callback quiescence, or DRAIN activation for any real profile.
- The 2026-09-29 SAPI5/eSpeak extension received per-task `gpt-6-astra high` reviews. SAPI5 findings were returned through three corrective rounds, then approved at `3f8d8a7`; eSpeak cancellation and failed-stop findings were corrected in `231fdb9` and approved. Policy/composition integration was approved at `9e737df` with 300 focused tests. A separate whole-extension review found two SAPI5 fallback issues: ordinary synthesis failure could hand native callbacks to a successor, and a failed purge left later ordinary requests queued on a dead worker. Both received RED/GREEN regressions and were fixed in `d7a8a8a`; the same reviewer approved the complete extension with no remaining Critical, Important or Moderate findings. The final add-on suite passed 1,169 tests. These reviews establish Linux implementation and fallback correctness, not Windows playback acceptance.

OneCore still lacks verified provenance for the loaded native helper/source profile. Supplied Neural SDK files report version `1.50.0.28`, but no callback-quiescence contract or loaded provenance was established. VE's external SDK build and callback-exclusion contract were not verified. Cerence SDK DLLs were absent; its `0x0520`/`0x0200` constants identify structure versions, not a loaded product build. SAPI5 callback retirement and physical playback were not verified on Windows, and eSpeak callback retirement and physical playback likewise remain unverified. Therefore the wrappers and controlled DRAIN protocol are implemented, but **none of the six real engine profiles is accepted for DRAIN activation**.

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
- `3439c8e` — `docs: record correlated drain implementation and validation`
- `cf33129` — `fix: retire OneCore pause operations before handoff`
- `f3415a8` — `fix: preserve contextual Neural legacy completion`

2026-09-29 SAPI5/eSpeak extension:

- `d23d11f` — `docs: extend correlated drain scope to SAPI5 and eSpeak`
- `e82a146` — `Add correlated SAPI5 WASAPI segment drain wrapper`
- `f2a4192` — `Retire SAPI5 PCM callbacks before correlated drain`
- `753e3c4` — `Preserve SAPI5 callback lifetimes across voice reload`
- `3f8d8a7` — `Stop cancelled ordinary SAPI5 PCM before successor playback`
- `b0b017e` — `Add FIFO-retired correlated drain wrapper for eSpeak`
- `231fdb9` — `Fail closed on eSpeak cancellation and cleanup stop failures`
- `9e737df` — `Route SAPI5 and eSpeak through evidence-gated drain policy`
- `d7a8a8a` — `Fail closed after ordinary SAPI5 synthesis errors`
- `5a37dd1` — `docs: update SAPI5 and eSpeak completion guidance`

This delivery record is included in its own documentation commit. Verify the complete branch commit list, including that commit, with `git log --reverse --format='%h %s' 4951d39..HEAD`.
