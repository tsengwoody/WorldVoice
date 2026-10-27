# Phase 47c Plugin Contract Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).
> 9 tasks, run in one go (fewer than 10, §3.2). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the `driver.Voice` plugin contract (`synth_driver_class`, `extra_capabilities`, `drain_profile`, `create_core`, `destroy_core`) and `VoiceFacade.update_settings` to mixedCase with no alias, make engine discovery skip and report a plugin that still uses an old name, and delete `TRANSITIONAL_47C`.

**Architecture:** Each contract name is one rename group applied by `p47c/ren.py` from an explicit rule list (`p47c/groups/<task>.py`) across its definition, every caller and the tests, and proven by `p47c/check.py` (order-sensitive token check, AST and ordered-comments check, empty `KEPT`). Discovery gains a `PRE_RENAME_CONTRACT_NAMES` table and a skip-with-error step before `ready()`. Neural is verified through a local `ref` overlay in the worktree.

**Tech Stack:** Python 3.11 semantics (NVDA 2024.1 floor), pytest, ruff 0.16.3 via prek, AST/tokenize scripts.

**Spec:** `docs/superpowers/specs/2026-10-27-phase47c-plugin-contract-design.md`

## Global Constraints

- No alias and no compatibility layer for any old name (spec §2). Already-mixedCase contract names (`applyEngineSettings`, `voiceInfoToMetadata`, `supportedSettings`, `getVoiceKey`, `loadParameter`, `variants`, `voices`, `ready`, `core`) are not touched.
- `engineRegistry/` gets only the old-name check; none of its own names is renamed (spec §3).
- No translatable string, setting, setting id, config key or gesture changes; the only new text is the discovery error line of spec §5. No readme or changelog edit (spec §8).
- `ref/` is never modified in the main checkout and never staged; the worktree's `ref` overlay is local and git-ignored (spec §7).
- Never edit `driver/<Engine>/driver/`, `driver/sonic/`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py`; never add Neural to the repo.
- Engine drivers stay independently installable: a wrapper imports only core modules and `driver`, never another wrapper.
- Renames only by `ren.py` from explicit lists, one group per commit, each passing `check.py`; renames and other edits never share a commit (the guard's entry deletions ride with their rename; `check.py` allows only deletions there).
- Before each rename, `prescan.py` lists string tables, `getattr`/`hasattr`/`setattr` strings, monkeypatch targets and guard name lists naming the OLD names; each hit is in the group or explained in the ledger.
- Formatting follows ref/nvda: tabs, line length 110, ruff pinned `0.16.3`.
- git: stage explicit paths, `git diff --cached --stat` before each commit; English `<type>: <summary>` with a body; no `Co-Authored-By`; re-stage after a hook change, never `--no-verify`; no push; never `git stash`; new files under `docs/` need `git add -f`.
- Tests serially, or at most 3 workers with a watchdog killing pytest below 3 GB MemAvailable (`p47c/suite.sh` runs serially with the watchdog).

## Review Focus

1. A contract name reached by a string with a default (`getattr(voiceClass, "drain_profile", None)`, `getattr(self._voiceClass, "extra_capabilities", frozenset())`) left unrenamed fails silently: DRAIN falls back to LEGACY_DONE and VE/Cerence lose waitfactor/variant. Tasks 3 and 4 rename those strings in the same group; `check.py` with an empty `KEPT` proves no OLD is left in the group's files; `tests/test_runtime_completion_policies.py::test_six_enabled_profiles_use_shared_lifecycle` and `tests/test_runtime_composition.py::test_waitfactor_updates_declared_capability_without_activating` run in Tasks 3–4; Task 9's word grep proves none is left anywhere.
2. A false positive in the old-name check skips every engine (the base `Voice` is in every MRO), and the synth fails with "No WorldVoice voices are available": Task 8's `test_pre_rename_names_map_onto_the_base_voice` and `test_no_bundled_voice_defines_a_pre_rename_name`.
3. A plugin that inherits an old name from its own helper base, or defines several, must still be reported, once, before `ready()` runs: Task 8's `test_old_contract_names_are_listed_together_and_inherited_ones_count` and the parametrized `test_plugin_with_old_contract_names_is_reported` (asserts `ready()` is not called).
4. Neural's class attribute `core = None` shadows the facade's `core` property; after the rename the Neural-style plugin must still open, take settings through `updateSettings` and terminate: Tasks 2 and 6 keep `tests/test_plugin_voice_contract.py::test_neural_style_plugin_runs_through_the_manager` green.
5. The real Neural file with only the one-line change must satisfy the contract test, and the unchanged one must not: Task 1 confirms red with the overlay, Task 2 turns it green; Task 9 runs the full suite with the overlay in place.

---

## The rename procedure (Tasks 2–6)

Scratch tools (session scratchpad `p47c/`, copied from `p47b/`): `ren.py <repo> <group> [--dry]`, `check.py REV <group> [--verbose]`, `prescan.py <repo> <group>`, `scan.py <repo> NAME[,NAME] [path…]`. A group file defines `RENAMES = {path: [rule…]}` and `KEPT = {}`.

For each group:

- [ ] Delete the group's entries from `TRANSITIONAL_47C` (and only those; remove a module key when its set empties).
- [ ] Run `python3 -m pytest -q tests/test_naming_layers.py`. Expected red: `test_naming_follows_layer` fails listing exactly the deleted entries.
- [ ] Write the group file from `scan.py` output: the definition, every attribute, keyword and string occurrence that names the contract member; nothing else.
- [ ] Run `prescan.py`; every hit must be covered by the group. Record the result in the ledger.
- [ ] Run `ren.py --dry`, then `ren.py`.
- [ ] Run `python3 -m pytest -q tests/test_naming_layers.py` → all passed; then `p47c/suite.sh` → 3303 passed, 0 skipped (with the overlay from Task 1).
- [ ] `git add` the group's paths and the guard; `git diff --cached --stat`; commit; run `python3 check.py HEAD~1 <group> --verbose` → `pure rename: OK (…)`. Record the line in the ledger. If it fails, fix the group, `git reset --soft HEAD~1`, re-run.

---

### Task 1: Neural overlay in the worktree

**Files:**
- Create (git-ignored, never staged): `/workspace/WorldVoice-phase47c/ref/` (directory replacing the symlink)

**Interfaces:**
- Consumes: `/workspace/WorldVoice/ref/*` (read only)
- Produces: worktree `ref/Neural/Neural/__init__.py` with line 8 `	synthDriverClass = SynthDriver`; every other entry a symlink to the main checkout's

- [ ] Replace the symlink:

  ```bash
  cd /workspace/WorldVoice-phase47c
  rm ref                                   # removes the symlink only
  mkdir ref
  for entry in /workspace/WorldVoice/ref/*; do
  	name=$(basename "$entry")
  	[ "$name" = Neural ] || ln -s "$entry" "ref/$name"
  done
  cp -a /workspace/WorldVoice/ref/Neural ref/Neural
  rm -rf ref/Neural/Neural/__pycache__
  sed -i '8s/^\tsynth_driver_class = SynthDriver$/\tsynthDriverClass = SynthDriver/' ref/Neural/Neural/__init__.py
  diff -r /workspace/WorldVoice/ref/Neural ref/Neural -x __pycache__   # exactly line 8
  git status --short ref                   # empty: ref is ignored
  ```

- [ ] Run `python3 -m pytest -q tests/test_plugin_voice_contract.py`. Expected red: `test_reference_neural_plugin_uses_only_plugin_attributes` fails (`assert {'core', 'engine', 'synthDriverClass'} <= {…'synth_driver_class'…}`); 4 passed, 1 failed.
- [ ] Record the commands and the diff in the ledger. No commit.

### Task 2: rename `synth_driver_class` → `synthDriverClass`

**Files:**
- Modify: `driver/__init__.py`, the six `driver/<Engine>/__init__.py`, `bridge/completionPolicies.py` (getattr string)
- Test: `tests/{conftest,test_driver_voice_base,test_espeak_segment_drain,test_native_strategy_guards,test_onecore_segment_drain,test_plugin_voice_contract,test_runtime_completion_policies,test_runtime_composition,test_sapi5_segment_drain,test_vocalizer_segment_drain,test_worldvoice_cancel_wrappers,test_worldvoice_request_builder}.py`, `tests/test_naming_layers.py` (deletion)

**Interfaces:**
- Produces: `Voice.synthDriverClass` (class attribute, default `None`); `PLUGIN_VOICE_ATTRIBUTES` contains `synthDriverClass`.

- [ ] Rename procedure. Rules: `member Voice` in `driver/__init__.py` and each wrapper; `text` on the getattr line of `completionPolicies.py`, the `PLUGIN_VOICE_ATTRIBUTES` line and the `"Voice.synth_driver_class"` guard string in `test_native_strategy_guards.py`; `member` for test-local Voice classes; `attr` for `env.outer.Voice`, `cls`, `driver`, `first`, … receivers. Expected: `test_reference_neural_plugin_uses_only_plugin_attributes` green; suite 3303 passed, 0 skipped.

### Task 3: rename `extra_capabilities` → `extraCapabilities`

**Files:**
- Modify: `driver/__init__.py`, `driver/{VE,Cerence}/__init__.py` (identical change, `tests/test_vocalizer_drift.py`), `bridge/engineAdapter.py` (getattr string)
- Test: `tests/{test_plugin_voice_contract,test_runtime_composition,test_runtime_legacy_adapter}.py`, guard deletion

**Interfaces:**
- Produces: `Voice.extraCapabilities` (default `frozenset()`), read by `VoiceClassAdapter.capabilities`.

- [ ] Rename procedure. Expected: suite 3303 passed, 0 skipped; `test_real_variant_and_waitfactor_hooks` and `test_waitfactor_updates_declared_capability_without_activating` among them.

### Task 4: rename `drain_profile` → `drainProfile`

**Files:**
- Modify: `driver/__init__.py`, the six wrappers, `bridge/completionPolicies.py` (docstring and three getattr strings)
- Test: `tests/{runtime_drain_integration_harness,test_plugin_voice_contract,test_runtime_completion_policies,test_runtime_composition}.py` (including the `SimpleNamespace(drain_profile=None)` keyword), guard deletion

**Interfaces:**
- Produces: `Voice.drainProfile` (default `None`), read by `CompletionPolicy.audioMode`, `drainSupport`, `contractFor`.

- [ ] Rename procedure. Expected: suite 3303 passed, 0 skipped; the `test_*_segment_drain.py` files and `test_six_enabled_profiles_use_shared_lifecycle` among them.

### Task 5: rename `create_core` → `createCore`, `destroy_core` → `destroyCore`

**Files:**
- Modify: `driver/__init__.py` (definitions and the class docstring), `bridge/engineAdapter.py` (calls and comment)
- Test: `tests/{conftest,legacy_adapter_harness,runtime_drain_integration_harness,runtime_harness,test_f4_engine_session,test_runtime_completion_policies,test_runtime_composition,test_runtime_legacy_adapter,test_worldvoice_lifecycle,voice_binding_harness}.py` (definitions, `super().destroy_core`, `monkeypatch.setattr(..., "create_core", ...)` strings, comments), guard deletion

**Interfaces:**
- Produces: `Voice.createCore()` and `Voice.destroyCore(core)` classmethods, called by `VoiceClassAdapter.open`/`close`.

- [ ] Rename procedure (one group with both pairs: they are one lifecycle and share their files). Expected: suite 3303 passed, 0 skipped.

### Task 6: rename `VoiceFacade.update_settings` → `updateSettings`

**Files:**
- Modify: `bridge/voiceFacade.py`, `globalPlugins/WorldVoice/rolePresenter.py`
- Test: `tests/{test_f4_voice_state,test_plugin_voice_contract,test_role_presenter,test_runtime_voice_facade}.py`, guard deletion (the last entry: ruff collapses the emptied dict to `= {}`, which `check.py` allows)

**Interfaces:**
- Produces: `VoiceFacade.updateSettings(**values)`.

- [ ] Rename procedure. Expected: suite 3303 passed, 0 skipped.

### Task 7: delete `TRANSITIONAL_47C` from the guard

**Files:**
- Modify: `tests/test_naming_layers.py`

**Interfaces:**
- Consumes: the empty `TRANSITIONAL_47C` left by Task 6
- Produces: guard with `INTERFACE_NAMES` and `TRANSITIONAL_47D` only; self-test `test_only_stored_identifiers_wait`

- [ ] Delete `TRANSITIONAL_47C` and its comment; drop it from the `_listed(...)` calls of `test_naming_follows_layer` and `test_lists_hold_only_names_that_break_the_rule`; rename `test_only_stored_identifiers_and_the_plugin_contract_wait` → `test_only_stored_identifiers_wait`, keep its `TRANSITIONAL_47D` subset assertion and drop the `TRANSITIONAL_47C` one; rewrite the docstring's closing paragraph: "One list waits for a later phase and may only shrink: TRANSITIONAL_47D, the stored identifiers above, until phase 47d."
- [ ] Run `python3 -m pytest -q tests/test_naming_layers.py` → all passed (same count as before: one self-test renamed, none added); `git grep -n TRANSITIONAL_47C -- addon tests` → empty.
- [ ] Suite 3303 passed, 0 skipped. Commit `test: delete the plugin contract's transitional naming list`.

### Task 8: discovery reports a pre-rename plugin

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/engineRegistry/discovery.py`
- Test: `tests/test_engine_discovery.py`, `tests/test_plugin_voice_contract.py`

**Interfaces:**
- Produces: `discovery.PRE_RENAME_CONTRACT_NAMES: dict[str, str]` (six pairs, spec §2 order: `synth_driver_class`, `extra_capabilities`, `drain_profile`, `create_core`, `destroy_core`, `update_settings`); `load_enabled_engine_classes` skips such a plugin with one `logger.error` line.

- [ ] Write `test_plugin_with_old_contract_names_is_reported` in `tests/test_engine_discovery.py`, parametrized over the six old names with a `kind` of attribute or classmethod per name (`synth_driver_class`, `extra_capabilities`, `drain_profile` as class attributes; `create_core`, `destroy_core` as classmethods; `update_settings` as a method). A `Voice` with `engine="Stale"`, `ready` recording calls, and the old name. Assert `load_enabled_engine_classes([spec], {}, logger=log) == {}`, `ready` was not called, and `("error", f"Skipping Stale engine candidate: plugin uses the pre-rename contract name(s) {old} (now {new}); update the plugin") in log.lines`.
- [ ] Write `test_old_contract_names_are_listed_together_and_inherited_ones_count`: `Helper` defines classmethod `create_core`; `Voice(Helper)` sets `engine="Stale"`, `drain_profile=None`; a second module's `Voice` has `engine="Fresh"`, `synthDriverClass`, `createCore`. Assert only `Fresh` loads and the error list is exactly `["Skipping Stale engine candidate: plugin uses the pre-rename contract name(s) drain_profile (now drainProfile), create_core (now createCore); update the plugin"]`.
- [ ] Write in `tests/test_plugin_voice_contract.py` a fixture-free helper that imports the discovery module of the `composition` package (`importlib.import_module(composition.driver.__name__.rsplit(".", 1)[0] + ".engineRegistry.discovery")`), then `test_pre_rename_names_map_onto_the_base_voice` (for each `old, new`: `not hasattr(base, old)` and `hasattr(base, new)`) and `test_no_bundled_voice_defines_a_pre_rename_name` (for each of `Cerence, Espeak, OneCore, RHVoice, SAPI5, VE`, the names assigned or defined in the body of `class Voice` in `addon/synthDrivers/WorldVoice/driver/<Engine>/__init__.py`, read by AST, are disjoint from the table's keys; the set of classes found is all six).
- [ ] Run `python3 -m pytest -q tests/test_engine_discovery.py tests/test_plugin_voice_contract.py`. Expected red: the discovery tests fail (`{}` expected, the stale `Voice` loads; no error line) and the contract tests error on the missing `PRE_RENAME_CONTRACT_NAMES` (AttributeError).
- [ ] Implement in `discovery.py`: the table with a comment (why: plugins built for the contract before phase 47c, refactor9 §6.1), a helper `_pre_rename_contract_names(voice) -> list[str]` (table order, `hasattr`), and the skip after the `Voice.engine` check, before the `voice.ready` timing block, logging `"Skipping %s engine candidate: plugin uses the pre-rename contract name(s) %s; update the plugin"` with `", ".join(f"{old} (now {new})" …)`.
- [ ] Run the two files → green (9 new cases). Suite 3312 passed, 0 skipped. `prek run --all-files` → all Passed. Commit `feat: report engine plugins that still use the pre-rename contract`.

### Task 9: docs check and final verification

**Files:**
- Read: `readme.md`, `addon/doc/{ru,uk,zh_CN,zh_HK,zh_TW}/readme.md`

**Interfaces:**
- Consumes: the branch after Task 8

- [ ] `grep -niE "synth_driver|extra_capab|drain_profile|create_core|destroy_core|update_settings|plugin|workspace" readme.md addon/doc/*/readme.md` → no contract or plugin-writing text (spec §8); record in the ledger.
- [ ] §7 verification with the overlay: `p47c/suite.sh` → 3312 passed, 0 skipped; `prek run --all-files` → all Passed; `git diff --check master` → empty; both protected-path commands empty.
- [ ] `git grep -nwE "synth_driver_class|extra_capabilities|drain_profile|create_core|destroy_core|update_settings" -- addon tests` → only `engineRegistry/discovery.py` (the table and its comment) and the discovery tests in `tests/test_engine_discovery.py`.
- [ ] Re-run every group's `check.py` against its own commit (`check.py <sha>~1 <group> --head <sha>`) and record all six results in the ledger. No commit.

---

## Self-Review

- Spec coverage: §2 goals 1–2 → Tasks 2–6; goal 3 → Task 8; goal 4 → Tasks 2–7; goal 5 → Tasks 1–2; §8 → Task 9; §9 new tests → Task 8; §10 → the rename procedure.
- Type consistency: `PRE_RENAME_CONTRACT_NAMES` is `dict[str, str]` in Task 8 and the spec; log text identical in spec §5 and Task 8.
- Review Focus: each item names its task and test.
- Proportion: 5 mechanical rename tasks share one procedure; the one behavior change (Task 8) carries the TDD steps.
