# Phase 45′: wrapper boilerplate convergence — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** The six engine wrappers share one `speak_segment`, one constructor-failure cleanup loop and one NVDA label, and lose a duplicate flag, two unreachable mode locks, a no-op quiescence check and stale comments — with no behaviour change on any production path.

**Architecture:** `SegmentHostSpeaker(SegmentDrainCore)` in `runtime/segmentHost.py` supplies `speak_segment` from `self._segmentHost`; each wrapper names it as its last base. `release_newest_first` in `runtime/engineControl.py` is the cleanup loop. `bridge/nvdaVersion.nvdaLabel` is the NVDA-layer label. The rest is deletion inside the OneCore, VE and Cerence wrappers.

**Tech Stack:** Python 3.11+, pytest, `ast`/`tokenize` guards and proof scripts, ruff 0.16.3 via prek.

**Spec:** `docs/superpowers/specs/2026-10-29-phase45b-boilerplate-design.md`

## Global Constraints

- No behaviour change on any production path (spec §2). The only direct-call change is spec §3.5 (VE/Cerence segment after ordinary speech). Anything else that turns out to change behaviour is dropped and recorded as a `Ruling:`.
- Moves and renames (Tasks 2, 3, 4, 5) carry the spec §6.2 proofs: order-sensitive token checks (`p45b/tokcheck.py`) and move checks (`p45b/movecheck.py`) in the scratchpad `/tmp/claude-0/-workspace-WorldVoice/1edac6d9-7900-4c53-bcf9-ab498b97141f/scratchpad/`; commands and results in the ledger. A move or rename commit contains nothing else; one group per commit (VE and Cerence are one group: the drift guard needs them identical).
- VE and Cerence change identically; `tests/test_vocalizer_drift.py` `ALLOWED` unchanged.
- Never modify `driver/*/driver/*`, `driver/sonic/`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py`; no Neural; each engine driver stays independently installable: shared code only in `runtime/` (NVDA-free, snake_case) or `bridge/` (NVDA layer, camelCase); no driver imports another.
- ruff pinned `0.16.3`; `prek` passes on every commit (restage and recommit if a hook rewrites; never `--no-verify`).
- git: explicit paths, `git diff --cached --stat` before each commit, `<type>: <summary>` + why-body, no `Co-Authored-By`, no push, no `git stash`, never touch `/workspace/WorldVoice`.
- Tests serial (no xdist) with the watchdog: `<scratch>/p45b/runtests.sh <out> [tests...]` (kills pytest under 3 GB MemAvailable); written `FULL` below.
- Baseline at `8ef4e12`: 3597 passed, 0 skipped.
- Progress ledger: `.superpowers/sdd/2026-10-29-phase45b-boilerplate/progress.md`; deviations as `Ruling: <decision> — <reason> — <cost if wrong>`.

## Review Focus

1. **A base that defines `speak_segment` before the mixin** (a future NVDA or vendored driver release): it would silently replace the host's segment entry. Task 1 guard (last base, no own override) and Task 2 `test_every_core_speaks_segments_through_the_shared_mixin` (identity on every loaded wrapper).
2. **A constructor that fails and whose cleanup step also fails** (e.g. RHVoice engine delete, VE native terminate): the other releases still run newest first, one error line each with the unchanged text, and the original error is raised. Task 3 (helper unit test; init-cleanup files with message pins).
3. **Shutdown racing speech** (terminate while a VE/Cerence `enqueue` holds host admission, then `speak`, `speak_segment` or `pause`): the VE flag must still answer before the host does. Task 5 (`test_pause_after_terminate_keeps_each_engine_behaviour`, `test_ordinary_speak_after_terminate_raises`, `test_segment_after_terminate_fails_once_without_native_call`).
4. **OneCore rate/pitch change before the first speech of a core** (settings applied at open): the tuple must reach the native helper before the first `ocSpeech_speak`, now always through the wrapper worker. Task 6 (`test_settings_tuples_do_not_take_native_job_identity`, `test_ordinary_speech_and_settings_keep_call_order`).
5. **VE/Cerence native call that returns while its callbacks are admitted, then the next call** (multi-chunk say all): `_nativeCall` must still be cleared after every call so the next call's callbacks are admitted. Task 8 (`tests/test_vocalizer_segment_drain.py` whole file, `tests/test_vocalizer_cancel*` via FULL).

---

### Task 1: `SegmentHostSpeaker` mixin

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/runtime/segmentHost.py` (after `SegmentDrainCore`, `:125-148`)
- Modify: `tests/test_native_strategy_guards.py:373-381`
- Test: `tests/test_segment_host.py`

**Interfaces:**
- Consumes: `SegmentDrainCore`, `SegmentHost.speak_segment(commands, token, *, context, on_event)`.
- Produces: `class SegmentHostSpeaker(SegmentDrainCore)` with `speak_segment(self, commands: SpeechCommands, token: CancellationView, *, context: PlaybackContext, on_event: SegmentEventSink) -> None`; requires the core to set `self._segmentHost`.

- [ ] **Step 1: Write the failing tests** in `tests/test_segment_host.py`:
  - `test_segment_host_speaker_forwards_to_the_core_host`: a `Core(SegmentHostSpeaker)` with `get_segment_drain_support` defined and `_segmentHost` a recorder; `core.speak_segment(cmds, token, context=ctx, on_event=sink)` → recorder got `((cmds, token), {"context": ctx, "on_event": sink})`, returns None.
  - `test_segment_host_speaker_leaves_drain_support_abstract`: `issubclass(SegmentHostSpeaker, SegmentDrainCore)`; `class Bare(SegmentHostSpeaker): pass`; `pytest.raises(TypeError)` on `Bare()`.
- [ ] **Step 2: Run** `python3 -m pytest -q -p no:cacheprovider tests/test_segment_host.py -k segment_host_speaker` — expected: 2 errors/failed (`AttributeError: ... SegmentHostSpeaker`).
- [ ] **Step 3: Implement** the mixin (spec §3.1; docstring says: last base, sets `self._segmentHost`, `get_segment_drain_support` stays the wrapper's). Change the guard to accept either last base: `SegmentDrainCore` with `{"speak_segment", "get_segment_drain_support"} <= own`, or `SegmentHostSpeaker` with `"get_segment_drain_support" in own and "speak_segment" not in own`.
- [ ] **Step 4: Run** the two files — expected all pass. `FULL` — expected 3599 passed, 0 skipped.
- [ ] **Step 5: Commit** `feat: add a SegmentHostSpeaker mixin for the wrappers' segment entry`.

### Task 2: Wrappers adopt the mixin (B1 move)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/{Espeak,RHVoice,SAPI5,OneCore,VE,Cerence}/__init__.py` (imports; `class SynthDriver(...)` bases; delete `speak_segment`)
- Test: `tests/test_native_strategy_guards.py`, `tests/test_engine_segment_contract.py`

**Interfaces:**
- Consumes: `SegmentHostSpeaker` (Task 1).
- Produces: each `SynthDriver(<parent>, SegmentHostSpeaker)` without its own `speak_segment`.

- [ ] **Step 1: Write the failing tests:**
  - `tests/test_native_strategy_guards.py::test_every_bundled_wrapper_uses_the_segment_host_speaker`: for the six bundled engines the last base unparses to `SegmentHostSpeaker`.
  - `tests/test_engine_segment_contract.py::test_every_core_speaks_segments_through_the_shared_mixin` (all engines): `module = sys.modules[type(engine.core).__module__]`; `type(engine.core).speak_segment is module.SegmentHostSpeaker.speak_segment`.
- [ ] **Step 2: Run** both — expected: 1 + 6 failed (`SegmentDrainCore` last / `AttributeError: SegmentHostSpeaker`).
- [ ] **Step 3: Write the proof scripts** `p45b/tokcheck.py` (old/new token streams: drop listed old/new line ranges and top-level import statements, apply `old=new` NAME substitutions, compare `(type, string, column-if-first-on-line)` in order, print imported-name diff) and `p45b/movecheck.py` (a function's tokens in old file A vs a function's tokens in new file B, in order, optional ignore of a `-> None` return annotation).
- [ ] **Step 4: Move, one commit per group** in this order: eSpeak, RHVoice, SAPI5, OneCore, VE+Cerence. For each: delete `speak_segment`, replace `SegmentDrainCore` by `SegmentHostSpeaker` in the base list and the `segmentHost` import, delete the `runtime.models` and `runtime.session` imports (used only by `speak_segment`). Run `movecheck` (old method ≡ mixin method) and `tokcheck --drop-old <method lines> --sub SegmentDrainCore=SegmentHostSpeaker` (expected: identical; import diff exactly `-PlaybackContext -SegmentEventSink -SpeechCommands -CancellationView -SegmentDrainCore +SegmentHostSpeaker`); run the engine's drain test file and `tests/test_engine_segment_contract.py -k <Engine>` — expected green. Commit `refactor: speak <Engine> segments through SegmentHostSpeaker` (wrapper files only).
- [ ] **Step 5: Run** the two Step 1 tests — expected: pass. `FULL` — expected 3606 passed, 0 skipped. Commit the tests: `test: pin the shared speak_segment on every bundled wrapper`.

### Task 3: One constructor-failure cleanup loop (B2)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/runtime/engineControl.py` (new function, docstring line)
- Modify: `Espeak:147-155`, `RHVoice:338-346`, `SAPI5:400-414`, `OneCore:257-265`, `VE:403-411` (Cerence same)
- Test: `tests/test_engine_control.py`, `tests/test_wrapper_init_cleanup.py:58-60`, `tests/test_vocalizer_init_cleanup.py:139-140`

**Interfaces:**
- Produces: `release_newest_first(releases: Sequence[Callable[[], object]], *, logger, message: str) -> None`.

- [ ] **Step 1: Characterization** — `_assert_one_cleanup_error_logged(record, engine)` also asserts `args == (f"WorldVoice {engine} initialization cleanup failed",)` (eSpeak's name is `eSpeak`); the vocalizer test asserts `args == (f"WorldVoice {harness.engine} initialization cleanup failed",)` (or the fixture's engine name). Run both files — expected: pass (green on today's code). Commit `test: pin the constructor cleanup log text`.
- [ ] **Step 2: Write the failing test** `test_release_newest_first_runs_every_release_in_reverse_and_logs_failures` in `tests/test_engine_control.py`: releases `a`, `b` (raises `OSError`), `c`; calls `["c", "b", "a"]`; logger got one `("error", ("msg",), {"exc_info": True})`; `release_newest_first([], logger=..., message="msg")` logs nothing. Run — expected: 1 failed (`ImportError`).
- [ ] **Step 3: Implement** the helper (spec §3.2). Run the file — expected: pass. Commit `feat: add release_newest_first for constructor cleanup`.
- [ ] **Step 4: Converge** the five wrappers (spec §3.2): each `except BaseException:` keeps its comments and `releases`, calls `release_newest_first(releases, logger=log, message="WorldVoice <engine> initialization cleanup failed")`, then `raise`. Proof: `tokcheck` per wrapper with the removed loop range listed; `movecheck`-style comparison of each removed loop to the helper body with `log=logger` and the string → `message`. Run both init-cleanup files and `tests/test_vocalizer_drift.py` — expected pass. `FULL` — expected 3607 passed, 0 skipped. Commit `refactor: share the wrappers' constructor cleanup loop`.

### Task 4: One NVDA label (B3)

**Files:**
- Create: `addon/synthDrivers/WorldVoice/bridge/nvdaVersion.py`
- Modify: `Espeak:18-22,255`, `SAPI5:41-45,733`, `OneCore:32-36,699` (+ one import each)
- Test: `tests/test_nvda_ready.py`

**Interfaces:**
- Produces: `bridge.nvdaVersion.nvdaLabel() -> str` (`"NVDA <versionInfo.version>"`, `versionInfo` imported inside the call).

- [ ] **Step 1: Write the failing test** `test_one_nvda_label_names_the_running_nvda`: AST scan of `driver/*/__init__.py` and `bridge/*.py` finds exactly one function named `nvdaLabel`/`_nvdaLabel` (in `bridge/nvdaVersion.py`) and no other `import versionInfo`; loading `bridge/nvdaVersion.py` by path with `sys.modules["versionInfo"] = SimpleNamespace(version="2026.1.0")` gives `nvdaLabel() == "NVDA 2026.1.0"`. Run — expected: 1 failed (three definitions / missing file).
- [ ] **Step 2: Move:** create the module; delete the three copies; replace `_nvdaLabel` with `nvdaLabel`; add `from ...bridge.nvdaVersion import nvdaLabel`. Proof: `movecheck` (each old body ≡ new body, comment line excepted — its wording is generalised, spec §3.3) and `tokcheck --drop-old <def lines> --sub _nvdaLabel=nvdaLabel` (import diff exactly `+nvdaLabel`).
- [ ] **Step 3: Run** `tests/test_nvda_ready.py tests/test_sapi5_old_nvda.py` — expected pass. `FULL` — expected 3608 passed, 0 skipped. Commit `refactor: share one NVDA label for the wrappers' ready() logs` (module, three wrappers, test).

### Task 5: One VE/Cerence termination flag (B6)

**Files:**
- Modify: `VE:333,390,482,813,824,884` (Cerence same)
- Test: `tests/test_engine_segment_contract.py`

- [ ] **Step 1: Characterization** `test_pause_after_terminate_keeps_each_engine_behaviour` (all engines, table `POST_TERMINATE_PAUSE = {"VE": RuntimeError, "Cerence": RuntimeError, "Espeak": AttributeError, "OneCore": None, "RHVoice": None, "SAPI5": None}`; for an error type assert `pytest.raises` and, for VE/Cerence, `match="driver has terminated"`; else `core.pause(True) is None`). Comment: cons.md B15 kept as is (spec §4). Run — expected: 6 passed. `FULL` — 3614. Commit `test: pin pause() after terminate on every engine`.
- [ ] **Step 2: Rename** `_terminated` → `_terminationRequested` (reads) and delete the two assignments of `_terminated` (VE and Cerence together). Proof: `tokcheck --sub _terminated=_terminationRequested --drop-old 390 --drop-old 884` per file: identical; `grep -c _terminationRequested` 3 → 7.
- [ ] **Step 3: Run** `tests/test_vocalizer_segment_drain.py tests/test_engine_segment_contract.py tests/test_vocalizer_drift.py` — expected pass. `FULL` — 3614 passed, 0 skipped. Commit `refactor: keep one VE and Cerence termination flag`.

### Task 6: Remove OneCore `_segmentMode` (B7)

**Files:**
- Modify: `OneCore:160-161,188,234,327-328,448-449`; `runtime/barriers.py:34-35`

- [ ] **Step 1: Delete** the flag and its three False branches (spec §3.6); fix the `barriers.py` sentence (spec §3.8). Proof: `tokcheck --drop-old 160-161 --drop-old 188 --drop-old 234 --drop-old 327-328 --drop-old 448-449` on the wrapper: identical.
- [ ] **Step 2: Run** `tests/test_onecore_segment_drain.py tests/test_engine_segment_contract.py tests/test_nvda_ready.py tests/test_native_strategy_guards.py` — expected pass (Review Focus 4 tests included). `FULL` — 3614 passed, 0 skipped. Commit `refactor: drop OneCore's unreachable pre-speech mode`.

### Task 7: Remove VE/Cerence `_legacyUsed` (B7)

**Files:**
- Modify: `VE:335-336,383,484-486` (Cerence `:335-338,385,486-488`)
- Test: `tests/test_engine_segment_contract.py:196-229`

- [ ] **Step 1: Change the test:** `test_segment_after_ordinary_speech_drains` (all engines): ordinary speech, then a segment reaches native synthesis and drains with segment id 27; comment cites spec §3.5 (production never mixes the entries on one core). Run — expected: VE and Cerence fail (`SEGMENT_FAILED`), 4 pass.
- [ ] **Step 2: Delete** `_legacyUsed`, its `admission_error` branch, and its `speak` comment + assignment (VE and Cerence). Proof: `tokcheck` with the deleted ranges: identical.
- [ ] **Step 3: Run** the contract file and `tests/test_vocalizer_segment_drain.py tests/test_vocalizer_drift.py` — expected pass. `FULL` — 3614 passed, 0 skipped. Commit `refactor: drop the VE and Cerence ordinary-speech mode lock` (wrappers + test).

### Task 8: Remove `_confirmNativeQuiescence` (B16)

**Files:**
- Modify: `VE:466-469,614,622-627,630-636` (Cerence same offsets +2)
- Modify: `tests/test_vocalizer_segment_drain.py:56-59` and its 39 calls; `tests/runtime_drain_integration_harness.py:1-5,287-288`; `tests/test_hygiene_guards.py:148,151`

- [ ] **Step 1: Delete** the method and the dead branch (spec §3.7): `finally` keeps `_closeAdmission`, `wait_consumers`, the `if invoked:` evidence and the lock block with an unconditional `self._nativeCall = None`. Delete the test replacements (scripted: exactly 39 lines `\tprove_fake_quiescence(env, monkeypatch)` plus the helper; the harness lines and docstring sentence) and the `_REASONS` entry with `_LATCHED`. Proof: `tokcheck` on each wrapper with the deleted ranges and the one dedent of `self._nativeCall = None` (compare with indentation ignored on that line only).
- [ ] **Step 2: Run** `tests/test_vocalizer_segment_drain.py tests/test_hygiene_guards.py tests/test_vocalizer_drift.py tests/test_runtime_drain_integration.py` (or the files using the harness) — expected pass. `FULL` — 3614 passed, 0 skipped. Commit `refactor: drop the VE and Cerence no-op quiescence check`.

### Task 9: Stale comments and verification (B16)

**Files:**
- Modify: `OneCore:371`, `SAPI5:662-664`, `VE:689-692` (Cerence same), spec §9 notes

- [ ] **Step 1: Rewrite** the three comments (spec §3.8 table). Proof: `tokcheck` differs only in COMMENT tokens on those lines. Run `tests/test_vocalizer_drift.py tests/test_hygiene_guards.py` — pass. Commit `docs: correct stale wrapper comments`.
- [ ] **Step 2: Verify (§7):** `FULL` — expected 3614 passed, 0 skipped; `prek run --all-files` all Passed; `git diff --check master`; the two protected-path commands empty; `grep -rn "_segmentMode\|_legacyUsed\|_confirmNativeQuiescence\|_nvdaLabel" addon tests` empty.
- [ ] **Step 3: Record** in the spec a "## 8. Implementation notes" section (rulings, proof results, counts). Commit `docs: record the phase 45' implementation notes`.

## Self-Review

- Spec coverage: §3.1 → T1/T2; §3.2 → T3; §3.3 → T4; §3.4 → T5; §3.5 → T7; §3.6 → T6; §3.7 → T8; §3.8 → T6 (barriers), T7 (VE speak, contract comment), T9 (rest); §4 → T5 Step 1 (B15 pin); §6.2 → T2–T9 proofs.
- Each Review Focus item names a task and tests.
- Types: `SegmentHostSpeaker`, `release_newest_first`, `nvdaLabel` names are used identically across tasks.
- 9 tasks: one run, no batch reviews (DEVELOPMENT_WORKFLOW §3.2).
