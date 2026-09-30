# Correlated segment drain implementation

**Branch:** `test/force-segment-end-index-all-engines`

**Implementation status:** Runtime, seven outer wrappers, evidence-gated policy selection and cross-engine integration are implemented. RHVoice Task 2 policy review and the full RHVoice whole-change review are approved.
**Profile status:** All seven real target profiles select `LEGACY_DONE`; DRAIN activation requires engine-specific native/audio evidence that is not available here. Windows playback acceptance is outstanding.

The implementation connects a context-bound DRAIN event across playback work, the index ledger, engine adapter, scheduler and NVDA event bridge. OneCore, Neural, VE, Cerence, SAPI5, eSpeak and RHVoice have outer wrappers with owned contextual callbacks, callback retirement, cancel/fault handling and engine-specific playback barriers. SAPI5 correlates WASAPI requests through `EndStream`, full PCM callback retirement and final player idle; its legacy audio route remains unsupported. eSpeak correlates callback completion with FIFO retirement after `_speak` returns and delivers terminal events outside native/background worker stacks. RHVoice retains its inner native worker while the outer wrapper waits for native done, successful native return, admitted callback/feed retirement, and a final player idle after those consumers retire before publishing a correlated drain outside callback/worker stacks. Completion policy selects DRAIN only for the installed custom driver when its explicit profile check returns supported. Every real profile, including RHVoice, explicitly reports unsupported, so it uses `LEGACY_DONE` from the first segment. RHVoice has left the test-only forced `END_INDEX` branch; unknown/external engines remain `LEGACY_DONE`.

The Neural inner driver, speech API, CFFI and SDK DLL bytes were user-provided untracked baseline files, committed by the user as `eb605cd`. They were treated as read-only. The 11 exact Neural baseline paths and SHA-256 values are recorded in the [validation record](finish/2026-09-28-worldvoice-correlated-drain-validation.md#task-6-neural-sdk-boundary-and-implementation-2026-09-28). All 20 protected Neural, VE, Cerence, manifest and native hashes were checked against the previous delivery package; this build audit compares every tracked add-on file against its source bytes.

## Verification and delivery

- Cross-engine integration suite: **43 passed**, using the real manager, adapters, sessions, scheduler, ledger, bridge and all four wrappers with controlled native/player boundaries. Premature drain, binding-generation bypass and stale callback migration each made the intended assertion fail under independent process-local mutations.
- RHVoice policy and actual Voice/core selection plus the RHVoice wrapper suite: **167 passed** with `pytest -q tests/test_runtime_completion_policies.py tests/test_rhvoice_segment_drain.py`. The focused RHVoice suite passed **24 tests**. The full add-on suite passed **1,197 tests** with `pytest -q tests` (29.40s). Existing bare repository collection is outside this add-on run because the Linux environment lacks Windows/NVDA/liblouis dependencies.
- SCons rebuilt `WorldVoice-6.2-test-correlated-drain-1-9999.nvda-addon` in a clean detached build worktree from correction commit `3e69e8f`. Size: **10,604,105 bytes**. SHA-256: `7c49fc96160f6ca49399f8848d99d538d08afa17ce4a1842123afe5e6f30c353`. The ZIP has **121 unique entries**, all CRCs pass, paths are safe, and it contains no bytecode/cache files. All **98 tracked add-on files** match build source bytes, including RHVoice wrapper and completion policy; all **4 RHVoice inner entries** match the previous package; the packaged English README matches the build input. The manifest uses version `6.2-test-correlated-drain-1-9999` and update channel `dev`. The root README gained the artifact hash after packaging, so the packaged README intentionally predates that self-referential annotation. The artifact is ignored and not committed.
- No Windows NVDA instance, audio device or matching external VE/Cerence SDK installation was available. Installation, listening/tail timing and the Windows/SDK matrix remain unchecked in the [validation record](finish/2026-09-28-worldvoice-correlated-drain-validation.md#task-11-test-package-and-validation-handoff-2026-09-28). Synthetic callback proofs and fallback runs do not certify DRAIN.
- Tasks 1–10 received independent `gpt-6-astra high` reviews. Findings were returned to implementation subagents, fixed and re-reviewed before proceeding. Task 10 review noted a minor opportunity to clean imported test modules from `sys.modules` after fixture teardown; no order-dependent test failure was reproduced.
- Task 11 implementation subagent hit its usage limit after completing the build and most validation notes. The coordinator verified the artifact and final add-on suite and completed this delivery record. An independent `gpt-6-astra high` review approved the Linux implementation/package handoff with no Critical or Important findings; its two Minor documentation corrections were fixed. The reviewer independently reran all 1,060 add-on tests and verified the artifact and protected-file hashes. Windows validation and real-profile DRAIN activation remain outstanding.
- A separate holistic `gpt-6-astra high` review of tasks 1–11 found lifetime and failure-propagation defects across OneCore and Neural, plus a documentation anchor issue. The OneCore and Neural findings were fixed in `cf33129` and `f3415a8`; the documentation link was corrected here. Targeted RED/GREEN regressions, a full 1,117-test run, and artifact rebuild followed. The reviewer repeated the full review after the final callback reentrancy fix and approved with no remaining actionable findings. This approval covers Linux code and package consistency; it does not certify Windows playback, SDK callback quiescence, or DRAIN activation for any real profile.
- The 2026-09-29 SAPI5/eSpeak extension received per-task `gpt-6-astra high` reviews. SAPI5 findings were returned through three corrective rounds, then approved at `3f8d8a7`; eSpeak cancellation and failed-stop findings were corrected in `231fdb9` and approved. Policy/composition integration was approved at `9e737df` with 300 focused tests. A separate whole-extension review found two SAPI5 fallback issues: ordinary synthesis failure could hand native callbacks to a successor, and a failed purge left later ordinary requests queued on a dead worker. Both received RED/GREEN regressions and were fixed in `d7a8a8a`; the same reviewer approved the complete extension with no remaining Critical, Important or Moderate findings. The final add-on suite passed 1,169 tests. These reviews establish Linux implementation and fallback correctness, not Windows playback acceptance.
- The full RHVoice whole-change `gpt-6-astra high` scoped re-review approved the admitted-producer and delivery-status corrections with no new breakage. The delayed nested-feed/index defect was fixed in `3e69e8f`, covered by a failing-then-passing actual-wrapper regression, and verified with 167 focused and 1,197 full add-on tests. The final package audit and hash were recorded in `d81b0c7`. This review does not establish Windows playback acceptance or real-profile DRAIN support.

OneCore still lacks verified provenance for the loaded native helper/source profile. Supplied Neural SDK files report version `1.50.0.28`, but no callback-quiescence contract or loaded provenance was established. VE's external SDK build and callback-exclusion contract were not verified. Cerence SDK DLLs were absent; its `0x0520`/`0x0200` constants identify structure versions, not a loaded product build. SAPI5 callback retirement and physical playback were not verified on Windows, and eSpeak callback retirement and physical playback likewise remain unverified. RHVoice's native callback/return ordering, final player idle and physical playback have only fake-boundary tests, not named-profile Windows evidence. Therefore the wrappers and controlled DRAIN protocol are implemented, but **none of the seven real engine profiles is accepted for DRAIN activation**.

## Commits included in this delivery

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
- `dd50918` — `docs: record holistic correlated drain review`

2026-09-29 SAPI5/eSpeak extension:

- `d23d11f` — `docs: extend correlated drain scope to SAPI5 and eSpeak`
- `e82a146` — `Add correlated SAPI5 WASAPI segment drain wrapper`
- `f2a4192` — `Retire SAPI5 PCM callbacks before correlated drain`
- `753e3c4` — `Preserve SAPI5 callback lifetimes across voice reload`
- `b0b017e` — `Add FIFO-retired correlated drain wrapper for eSpeak`
- `3f8d8a7` — `Stop cancelled ordinary SAPI5 PCM before successor playback`
- `231fdb9` — `Fail closed on eSpeak cancellation and cleanup stop failures`
- `9e737df` — `Route SAPI5 and eSpeak through evidence-gated drain policy`
- `d7a8a8a` — `Fail closed after ordinary SAPI5 synthesis errors`
- `5a37dd1` — `docs: update SAPI5 and eSpeak completion guidance`
- `2e27c2c` — `docs: record SAPI5 and eSpeak drain delivery`

2026-09-30 RHVoice extension:

- `e37322b` — `docs: plan RHVoice correlated drain wrapper`
- `e7220ab` — `Add context-aware RHVoice segment drain wrapper`
- `3a376bb` — `docs: correct RHVoice delivery file path`
- `19d39cb` — `Retain RHVoice delivery ownership through cancellation`
- `c2a45d9` — `Avoid RHVoice callback and delivery cancellation cycle`
- `a80b324` — `Route RHVoice through evidence-gated drain policy`
- `b890562` — `docs: record RHVoice fallback and package audit`
- `eafe955` — `Drain RHVoice audio admitted before retirement`
- `71ca851` — `Record corrected RHVoice package audit`
- `3e69e8f` — `Allow admitted RHVoice native callbacks to finish nested feeds`
- `d81b0c7` — `Record RHVoice admitted-producer fix and package audit`
- `76cda09` — `Record approved RHVoice whole-change review`
- `7c17396` — `docs: complete RHVoice commit list`
- `6066f28` — `docs: include final RHVoice review commit`

This record is updated in its own documentation commit, so its current commit hash is not listed inside itself. Verify the complete branch commit list, including that commit, with `git log --reverse --format='%h %s' 4951d39..HEAD`.
