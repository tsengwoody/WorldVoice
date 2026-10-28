# Phase 52: shared barrier names and token capability — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** Every wrapper names its segment barriers through three meaning-named constants in `runtime/barriers.py` (engine-specific names only where the evidence differs), and cancellation-token support is declared in `Voice.extraCapabilities` instead of on the core.

**Architecture:** A new constants module in the portable core; four script-driven rename commits (runtime+eSpeak, RHVoice, SAPI5, VE+Cerence), each proven by an order-sensitive token check; an AST guard pins the classification. Part 2 changes one bridge line, two `extraCapabilities` declarations, and the tests that pinned the old "core instance is authoritative" rule.

**Tech Stack:** Python 3.11+, pytest, `ast`/`tokenize` checks, ruff 0.16.3 via prek.

**Spec:** `docs/superpowers/specs/2026-10-28-phase52-shared-barriers-design.md`

## Global Constraints

- No behaviour change: same barrier set per record (up to spelling), same reach points, token passed to exactly the cores that got it before.
- Shared names (spec §3.1): `SYNTHESIZED = "synthesized"`, `ENGINE_DONE = "engine_done"`, `PLAYED_OUT = "played_out"`. Engine-specific (spec §3.2): OneCore `{"callback", "synced"}`, SAPI5 `{"processed"}`, RHVoice `{"message"}`.
- Capability value: `"cancellationToken"`.
- Do not modify inner drivers or `ref/`: `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py addon/synthDrivers/WorldVoice/unicodeScripts/unspaced_common_data.py` and `git ls-files addon/synthDrivers/WorldVoice/driver/Neural` stay empty.
- Drivers independently installable: wrappers import only `runtime/` (and their own inner); no wrapper-to-wrapper import.
- VE and Cerence identical; `tests/test_vocalizer_drift.py` `ALLOWED` unchanged.
- Renames, the new module, the guard and Part 2 in separate commits; each rename commit passes the token check (spec §7.2), recorded in the ledger.
- ruff pinned `0.16.3`; `prek` passes on every commit; commits `<type>: <summary>` + body, no Co-Authored-By, explicit paths, no `--no-verify`, no push/merge, no `git stash`.
- Tests serial with the watchdog: `cd /workspace/WorldVoice-phase52 || exit 1; ( while sleep 5; do m=$(awk '/MemAvailable/{print $2}' /proc/meminfo); [ "$m" -lt 3000000 ] && pkill -f pytest && break; done ) & W=$!; python3 -m pytest -p no:cacheprovider tests; kill $W` (written `FULL` below).
- Mutation on a scratch copy: `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, output to a file, `timeout` per run.
- Baseline at `4ca7e42`: 3468 passed, 0 skipped.

## Review Focus

1. **A barrier key read rather than reached** (RHVoice `record.barriers[...]` `:242-243`, SAPI5 `.get("processed")`/`["ended"]` `:261`, `:515`, VE/Cerence `"spoken" in record.barriers` `:504`): a missed rename there is a `KeyError` or a silently false check, not a missing-barrier error. Task 6's guard walks subscripts, `.get` and `in` on `.barriers`; Tasks 3–5 token checks count each replaced key.
2. **eSpeak's played-out barrier comes from the runtime default**: renaming one side only makes every eSpeak segment raise `KeyError` in the final callback. Task 2 renames both in one commit; Task 6 pins `LeasedPlayer`'s default to `PLAYED_OUT`; existing `tests/test_espeak_segment_drain.py` runs in Task 2.
3. **Ordinary (non-segment) records** carry a different set (SAPI5 `_ORDINARY_BARRIERS`, VE/Cerence empty, OneCore `{"callback"}`): a rename of the strategy set alone leaves ordinary speech failing. Task 6 pins both sets per engine; Task 4 token check covers `:19`.
4. **SAPI5 on NVDA < 2025.3** swaps in NVDA's own `speak(speechSequence)`: a token there raises `TypeError`. Task 8 asserts SAPI5's `Voice` never declares `"cancellationToken"` (old-release bridge test) and the guard forbids the declaration on any Voice that reassigns `synthDriverClass`.
5. **A core that still carries `supportsCancellationToken`** (an old fake or a third-party core) must no longer influence the bridge: Task 7's rewritten `test_token_support_comes_from_the_voice_class` covers "core says True, class does not declare → plain `speak(commands)`".

---

### Task 1: Shared barrier constants

**Files:**
- Create: `addon/synthDrivers/WorldVoice/runtime/barriers.py`
- Create: `tests/test_segment_barriers.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `runtime.barriers.SYNTHESIZED`, `ENGINE_DONE`, `PLAYED_OUT` (str), with the spec §3.1 meanings in the module docstring/comments.

- [ ] **Step 1: Write the failing tests** in `tests/test_segment_barriers.py` (load the module by path with `addon_loader.load_source` or `ast`):
  - `test_shared_barrier_values`: `(SYNTHESIZED, ENGINE_DONE, PLAYED_OUT) == ("synthesized", "engine_done", "played_out")`.
  - `test_shared_barriers_are_the_only_public_names`: the module's public upper-case names are exactly those three.
  - `test_barrier_module_imports_nothing`: its AST has no `Import`/`ImportFrom`.
- [ ] **Step 2: Run** `python3 -m pytest -p no:cacheprovider tests/test_segment_barriers.py -q` — expected: 3 errors/failed (module missing).
- [ ] **Step 3: Create `runtime/barriers.py`** with the three constants, each preceded by a comment stating the spec §3.1 meaning; module docstring: barriers are opaque to `SegmentHost`, these are the shared kinds, engine-specific names live in their wrapper.
- [ ] **Step 4: Run** the same command — expected: 3 passed. `FULL` — expected 3471 passed, 0 skipped.
- [ ] **Step 5: Commit** `feat: name the shared segment barrier kinds` (both files).

### Task 2: Rename group G1 — runtime default, eSpeak, host tests

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/runtime/segmentHost.py:679`
- Modify: `addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py:64,109,182`
- Modify: `tests/test_segment_host.py` (every `"idle"`, and `:150`)
- Create (scratchpad, not committed): `tokcheck.py`, `rename.py`

**Interfaces:**
- Consumes: Task 1 constants.
- Produces: `LeasedPlayer(host, player, *, idle_barrier: str | None = PLAYED_OUT)`.

- [ ] **Step 1: Write the scratchpad tools.** `rename.py FILE OLD=NEW…` replaces exact tokens (via `tokenize`, by position, so only whole tokens) and inserts one import line; `tokcheck.py BASE FILE --map OLD=NEW… --import 'LINE'` compares `git show BASE:FILE` tokens with the working file as spec §7.2 says, printing per-pair counts and `OK`/first mismatch. Sanity-check `tokcheck` on an unchanged file (`OK`, all counts 0) and on a hand-made extra edit (mismatch reported).
- [ ] **Step 2: Apply the lists.** segmentHost: `"idle"=PLAYED_OUT`, import `from .barriers import PLAYED_OUT`. Espeak: `"returned"=SYNTHESIZED`, `"ended"=ENGINE_DONE`, `"idle"=PLAYED_OUT`, import `from ...runtime.barriers import ENGINE_DONE, PLAYED_OUT, SYNTHESIZED`. test_segment_host: `"idle"="played_out"`, `"Fake synthesis retired without its idle barriers"="Fake synthesis retired without its played_out barriers"`, no import. Run `ruff check --fix`/`ruff format` only if prek requires (import placement), then re-run tokcheck.
- [ ] **Step 3: Token check** each file against `HEAD` — expected `OK`; counts: segmentHost `"idle"` 1; Espeak 2/2/1 (returned/ended/idle); test_segment_host `"idle"` 9, message 1. Record commands and output in the ledger.
- [ ] **Step 4: Run** `python3 -m pytest -p no:cacheprovider tests/test_segment_host.py tests/test_espeak_segment_drain.py tests/test_native_strategy_guards.py -q` — expected all pass; `FULL` 3471 passed.
- [ ] **Step 5: Commit** `refactor: name eSpeak and runtime barriers by shared kind` (three files).

### Task 3: Rename group G2 — RHVoice

**Files:** Modify `addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py:146,242-243,250,265,349`

**Interfaces:** Consumes Task 1 constants and Task 2 tools.

- [ ] **Step 1: Apply** `"returned"=SYNTHESIZED`, `"done"=ENGINE_DONE`, `"idle"=PLAYED_OUT`; import `from ...runtime.barriers import ENGINE_DONE, PLAYED_OUT, SYNTHESIZED`. `"message"` kept.
- [ ] **Step 2: Token check** — expected `OK`; counts returned 3 (`:146`, `:243`, `:265`), done 3, idle 2; kept `"message"` 2.
- [ ] **Step 3: Run** `tests/test_rhvoice_segment_drain.py tests/test_native_strategy_guards.py` — pass; `FULL` 3471.
- [ ] **Step 4: Commit** `refactor: name RHVoice barriers by shared kind`.

### Task 4: Rename group G3 — SAPI5

**Files:** Modify `addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py:19,102,165,377,515`

- [ ] **Step 1: Apply** `"ended"=ENGINE_DONE`, `"idle"=PLAYED_OUT`; import `from ...runtime.barriers import ENGINE_DONE, PLAYED_OUT`. `"processed"` kept.
- [ ] **Step 2: Token check** — `OK`; ended 4, idle 2; kept `"processed"` 5.
- [ ] **Step 3: Run** `tests/test_sapi5_segment_drain.py tests/test_sapi5_old_nvda.py tests/test_native_strategy_guards.py` — pass; `FULL` 3471.
- [ ] **Step 4: Commit** `refactor: name SAPI5 barriers by shared kind`.

### Task 5: Rename group G4 — VE and Cerence

**Files:** Modify `addon/synthDrivers/WorldVoice/driver/VE/__init__.py:298,341,504-505`, `addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py:298,343,506-507`

- [ ] **Step 1: Apply to both** `"spoken"=SYNTHESIZED`, `"idle"=PLAYED_OUT`; import `from ...runtime.barriers import PLAYED_OUT, SYNTHESIZED`.
- [ ] **Step 2: Token check both** — `OK`; spoken 3, idle 2 each.
- [ ] **Step 3: Run** `tests/test_vocalizer_segment_drain.py tests/test_vocalizer_drift.py tests/test_worldvoice_cancel_wrappers.py` — pass; `FULL` 3471.
- [ ] **Step 4: Commit** `refactor: name VE and Cerence barriers by shared kind` (both files).

### Task 6: Barrier guard

**Files:** Modify `tests/test_native_strategy_guards.py` (append)

**Interfaces:** Consumes the declarations of Tasks 2–5.

- [ ] **Step 1: Write the guard** (the renames are already in; Step 2 proves it bites). Tests:
  - `SHARED` read by `ast` from `runtime/barriers.py`; `ENGINE_SPECIFIC = {"Espeak": set(), "SAPI5": {"processed"}, "RHVoice": {"message"}, "OneCore": {"callback", "synced"}, "VE": set(), "Cerence": set()}`.
  - `EXPECTED = {"Espeak": ({"SYNTHESIZED","ENGINE_DONE","PLAYED_OUT"}, None), "RHVoice": ({"message","ENGINE_DONE","SYNTHESIZED","PLAYED_OUT"}, None), "SAPI5": ({"ENGINE_DONE","processed","PLAYED_OUT"}, {"ENGINE_DONE","processed"}), "OneCore": ({"callback","synced"}, {"callback"}), "VE": ({"SYNTHESIZED","PLAYED_OUT"}, set()), "Cerence": (same as VE)}` (strategy set, `_ORDINARY_BARRIERS` or `None` when absent), elements as constant names or literals.
  - `test_strategy_barriers_use_shared_or_listed_names[engine]` (6): every barrier expression (spec §7.1 list) is an `ast.Name` in `SHARED` imported from `runtime.barriers` in that file, or an `ast.Constant` str in `ENGINE_SPECIFIC[engine]`; and the declared sets equal `EXPECTED[engine]`.
  - `test_engine_specific_barrier_names_are_used_and_not_shared`: each listed name occurs as a barrier expression in its wrapper; no listed name equals a `SHARED` value.
  - `test_leased_player_reaches_played_out_by_default`: `LeasedPlayer.__init__`'s `idle_barrier` default is `ast.Name("PLAYED_OUT")`.
- [ ] **Step 2: Prove it bites:** in a scratch copy, put `"idle"` back into one strategy set and add `"processed"` to Espeak's list → expected the corresponding tests fail; record in the ledger.
- [ ] **Step 3: Run** `tests/test_native_strategy_guards.py` — pass; `FULL` 3479 passed.
- [ ] **Step 4: Commit** `test: guard the barrier names each wrapper uses`.

### Task 7: Token support from `Voice.extraCapabilities`

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/bridge/engineAdapter.py:117`
- Modify: `addon/synthDrivers/WorldVoice/driver/__init__.py:26` (comment only)
- Modify: `addon/synthDrivers/WorldVoice/driver/VE/__init__.py:345,873`, `driver/Cerence/__init__.py:347,880`
- Modify tests: `tests/test_runtime_legacy_adapter.py:73-88,555-576`, `tests/test_native_strategy_guards.py:306-319`, `tests/test_worldvoice_cancel_wrappers.py:64`, `tests/test_worldvoice_request_builder.py:72-100,215-217`, `tests/runtime_harness.py:261-264,442-466`

**Interfaces:**
- Produces: `EngineCapabilities.supports_cancellation_token == ("cancellationToken" in Voice.extraCapabilities)`.

- [ ] **Step 1: Rewrite the tests.**
  - `test_token_support_comes_from_the_voice_class`, parametrized `(declared, core_claim)` in `[(True, None), (False, True), (False, None)]`: the class's `extraCapabilities` contains `"cancellationToken"` iff `declared`; the core carries `supportsCancellationToken = core_claim` when not `None`. Assert `core.spoken == [(("hello",), {"cancellationToken": token} if declared else {})]` and `capabilities.supports_cancellation_token is declared`; waitfactor/variants still `False`. Docstring states the rule change (spec §4).
  - `test_bridge_passes_the_token_to_the_real_vocalizer_wrapper`: add `assert "cancellationToken" in cls.extraCapabilities` and `assert not hasattr(core, "supportsCancellationToken")`; keep the `_speakPlain` call and `calls == [(["hi"], token)]`.
  - `test_vocalizer_wrapper_has_no_guard_fallback`: replace the class-constant `any(...)` with: no `supportsCancellationToken` assignment in `SynthDriver`, and `Voice.extraCapabilities` literal equals `{"waitfactor", "variant", "cancellationToken"}`.
  - `test_installs_player_stand_in_and_keeps_inner_stop_flag`: `assert "cancellationToken" in engine_harness.module.Voice.extraCapabilities` (the harness loads the real wrapper module) instead of the core attribute.
  - Request builder fake: `voice(key, *, supports_token=None, …)` sets `Voice.extraCapabilities = frozenset({"cancellationToken"})` when `supports_token`; the core keeps no attribute; the assertion at `:215-217` uses the engine (`VE`/`Cerence`) instead of `core.supportsCancellationToken`.
  - `runtime_harness.py`: drop `ContractCore.supportsCancellationToken`; `LegacyVoice.extraCapabilities = frozenset({"cancellationToken"})`.
- [ ] **Step 2: Run** `tests/test_runtime_legacy_adapter.py tests/test_native_strategy_guards.py tests/test_worldvoice_cancel_wrappers.py tests/test_worldvoice_request_builder.py tests/test_runtime_adapter_contract.py -q` — expected red: the `(True, None)` case gets `{}`, the legacy-contract harness raises `TypeError` (missing `cancellationToken`), the VE/Cerence structure test fails.
- [ ] **Step 3: Implement.** Bridge: `supports_cancellation_token="cancellationToken" in extra`. VE/Cerence: delete the class constant, add `"cancellationToken"` to `extraCapabilities`. `driver/__init__.py`: comment above `extraCapabilities` naming the three recognized values and what `"cancellationToken"` promises.
- [ ] **Step 4: Run** the Step 2 command — pass; `FULL` 3479 passed.
- [ ] **Step 5: Commit** `refactor: declare cancellation-token support in Voice.extraCapabilities` (all Task 7 files).

### Task 8: Token-capability guard and SAPI5 old-NVDA path

**Files:** Modify `tests/test_native_strategy_guards.py` (append), `tests/test_sapi5_old_nvda.py:191-216`

- [ ] **Step 1: Write the tests.**
  - `test_a_token_capability_needs_a_fixed_core_that_takes_the_token[engine]` (6): parse the wrapper; if its `Voice.extraCapabilities` contains `"cancellationToken"`, then `SynthDriver.speak` has a parameter `cancellationToken`, and no method of `Voice` assigns `synthDriverClass` (`cls.synthDriverClass, …` targets included); if the Voice reassigns `synthDriverClass` (SAPI5), it must not declare the value. Assert the declaring set is exactly `{"VE", "Cerence"}`.
  - In `test_old_nvda_sapi5_driver_runs_through_the_bridge_as_a_legacy_done_core`: `assert "cancellationToken" not in voice.extraCapabilities` after `ready()`.
- [ ] **Step 2: Prove it bites:** in a scratch copy, add `"cancellationToken"` to SAPI5's Voice → the guard and the old-NVDA test fail (the latter with `TypeError` from NVDA's `speak`); record in the ledger.
- [ ] **Step 3: Run** both files — pass; `FULL` 3485 passed.
- [ ] **Step 4: Commit** `test: guard which cores may receive the cancellation token`.

### Task 9: Verification and mutation

- [ ] **Step 1:** `FULL` — 3485 passed, 0 skipped (record actual); `prek run --all-files` all Passed; `git diff --check master`; protected-path commands empty; `git diff master --stat -- ref` empty.
- [ ] **Step 2:** Re-run every token check against its commit's parent (`tokcheck.py <sha>^ …` with the committed file); record.
- [ ] **Step 3:** Mutants of spec §7.3 on a scratch copy, one run each with `timeout 600`, targeted test files; record killed/survived with reasons in the ledger and the report.
- [ ] **Step 4:** Report back (no commit unless the ledger notes require a doc fix).
