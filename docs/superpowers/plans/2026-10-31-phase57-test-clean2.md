# Phase 57 test-clean2 removals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** Delete the 486 test ids in the spec's removal list, do the restructures, renames, edits and merges the spec fixes (§5.2–§5.7), and end at 3243 passed, 0 skipped, with no `addon/` change and no coverage loss per module.

**Architecture:** Test-only phase. Every commit is one kind (pure deletion, restructure, rename, edit, merge) and carries its own id list, a slice of the final list. After every commit a scripted collection proof compares the collection with the previous commit's: exactly that commit's ids are gone, every renumbered index id pairs with a kept id of the same function and parameters, and nothing else changes. Deletion commits must also pass a token check that proves they only remove tokens.

**Tech Stack:** pytest (+ pytest-cov, Hypothesis), Python `tokenize`, git, prek (ruff `==0.16.3`).

**Spec:** `docs/superpowers/specs/2026-10-31-phase57-test-clean2-design.md` with its appendix files `…-remove.txt` (486 ids), `…-renames.txt`, `…-edited.txt`, `…-coverage-before.txt` in the same folder.

## Global Constraints

- Worktree `/workspace/WorldVoice-phase57`, branch `phase57-test-clean2`; `ref` is a git-ignored symlink, never staged. The main checkout is not touched.
- No change under `addon/` (`git diff --stat master -- addon` empty). Never touch inner drivers (`driver/<Engine>/driver/`), `driver/sonic/`, or the generated `unicodeScripts/script_data.py` / `unspaced_common_data.py`; never add Neural. Engine drivers stay independently installable.
- ruff pinned `==0.16.3` (prek hooks run on commit; re-stage and re-commit if a hook modifies a file; never `--no-verify`).
- git: stage explicit paths only; check `git diff --cached --stat` before each commit; English `<type>: <summary>` with a why body (`test:` for these commits); no `Co-Authored-By`; no push; never `git stash`. Scratch worktrees only under the scratchpad, removed only if created here.
- Resources: one pytest process at a time, always under `impl/runpy.sh` (MemAvailable < 3 GB → `kill -TERM` of its own PID only).
- The removal list is the only source of truth for what disappears. No test changes behaviour except as the spec says. No new tests except E2's `test_symbols_module_has_no_relative_imports` and the assertions moved by M1/M2.
- Index ids renumber when an earlier row goes (spec §5.2); no explicit ids are added to keep them stable. Renumbered pairs may only occur in the functions listed in spec §5.2.
- A parametrize left with one row stays a one-row parametrize, except the two in Task 12.

## Review Focus

1. **Copied-file coverage blind spot (M3).** `test_core_install.py`'s `install` fixture runs *copies* of `coreArchive.py`; if the moved `test_install_always_removes_the_archive` were switched to it, `coreArchive.py:31→34` would silently lose coverage. → Task 14 (move check: the moved blocks are byte-identical, loader unchanged) and Task 15 (`addon/generics/coreArchive.py` 100%).
2. **Fixture and helper edits change what other tests run.** The `legacy` fixture losing `driver` and maybe three stubs, `_driver_methods` losing two names, the `test_nvda_ready` fixture switch, `CountingToken` losing its delay. → Tasks 6, 11, 12: each touched file runs alone and in the full suite; Task 15's per-module coverage gate.
3. **Order dependence and module state.** Deleting the first tests of a module changes which test first imports a reloaded module (`tests/pipeline_harness.py`, `SCRIPT_LOOKUP`). → every task runs each touched file on its own plus the full suite.
4. **Off-by-one in rebuilt parametrizations** (R1's `CASES`, R3's `STAGE_ROWS`, R4–R7): a kept case silently dropped or duplicated. → Tasks 10 and 11: the collection proof's multiset check on (function, parameters).
5. **Timing-variant cases gone** (`[0.1]`, `[0.06]`, `[1]` of the concurrency tests): a weakened wait helper would now turn flaky instead of failing. → Task 12 runs the two edited files 5×; Task 15 runs the five concurrency files 5× each.

---

## Proof tooling (scratchpad, not committed)

`SP=/tmp/claude-0/-workspace-WorldVoice/a68674de-080e-47c7-b392-44942b53ef24/scratchpad/p57`, scripts in `$SP/impl/`:

| Script | Use | Pass output |
|---|---|---|
| `collect.sh <out.jsonl>` | `PYTHONHASHSEED=0` collection with `$SP/collect_params.py` (spec §6.1; the fixed seed makes set reprs in params stable) | `<N> tests collected`, `<N>` lines |
| `proof.py BASE HEAD REMOVED RENAMES` | spec §6.1 steps 1–4; prints every renumbered pair | `PROOF OK` |
| `tokcheck.py <rev> <rev\|WT> [paths]` | per hunk: added tokens are an ordered subsequence of removed tokens; per file: new Python tokens a subsequence of old; new files fail | `TOKCHECK OK` |
| `partition.py lists` | splits `…-remove.txt` into the per-commit lists below; asserts they partition all 486 ids | `total 486` |
| `runpy.sh <log> <pytest args>` | one pytest under the memory watchdog | `rc=0 killed=0` |
| `movecheck.py` (Task 14) | order-checking move comparison for M3 | `MOVE OK` |
| `covcmp.py` (Task 15) | per-module coverage table comparison | lists every differing module |

**Per-commit list rule** (`partition.py`): an id goes to the special commit of its function if listed in the table, otherwise to its file's audit group.

| List | Functions / files |
|---|---|
| `R12-filters` (48) | `test_pipeline_filters.py::test_number_mode`, `::test_number_and_group_modes_name_each_symbol` |
| `R3-edges` (21) | `test_pipeline_number_edges.py::test_number_stage_worked_examples`, `::test_worked_examples_through_every_stage` |
| `R4-composition` (11) | `test_runtime_composition.py::test_unconfirmed_wrapper_uses_legacy_and_logs_concrete_fallback_once` |
| `R5-settings-service` (14) | `test_pipeline_settings_service.py::test_load_reads_the_default_for_each_invalid_key`, `::test_a_panel_save_writes_the_default_over_a_refused_value` |
| `R6-wv-pipeline-settings` (5) | `test_worldvoice_pipeline_settings.py::test_voice_parameters_commit_and_follow_the_consistency_policy` |
| `R7-settings-panels` (2) | `test_settings_panels.py::test_pipeline_panel_enables_pause_controls_from_the_stored_switch` |
| `F-nvda-ready` (1) | `test_nvda_ready.py::test_ready_on_ref_nvda_is_true_and_silent` |
| `M1` (2), `M2` (1) | `test_worldvoice_cancel_wrappers.py::test_core_cancel_reports_neither_index_nor_done`; `test_role_panel.py::test_panel_opens_its_presenter_for_the_worldvoice_manager` |
| `G1` (17), `G2` (10), `G3` (38), `G5` (56), `G6` (43), `G7` (39) | the audit group's file list (`storage/test-clean2.md` §3 摘要) |
| `G4a` (69) | `test_pipeline_{filters,number_edges,nvda_symbols,nvda_ssml,log,passthrough,panels,structure,voice_lookup}.py` |
| `G4b` (109) | `test_pipeline_{punctuation_pause,settings_service,stages,unspaced_space}.py`, `test_worldvoice_pipeline_settings.py`, `test_legacy_speech_commands.py`, `test_lint_rewrites.py` |

**Proof block** (every committing task runs it before `git commit`, on the working tree; `cPREV` is the previous commit's collection):

1. `impl/collect.sh $SP/impl/cNN-<name>.jsonl` → the task's expected count.
2. `python3 impl/proof.py impl/cPREV.jsonl impl/cNN-<name>.jsonl impl/lists/<list>.txt <renames-or-/dev/null>` → `PROOF OK`; every printed pair is in a spec §5.2 function.
3. Deletion tasks only: `python3 impl/tokcheck.py HEAD WT tests` → `TOKCHECK OK`.
4. Each touched test file alone: `python3 -m pytest -q -p no:cacheprovider tests/<file>` → all pass.
5. `prek run --files <touched files>` → Passed (ruff F401 catches orphaned imports).
6. `impl/runpy.sh impl/cNN-full.log -q -p no:cacheprovider tests` → `<N> passed`, no skipped, `rc=0 killed=0`.
7. Commit; record commands, counts and pairs in the ledger `.superpowers/sdd/2026-10-31-phase57-test-clean2/progress.md`.

**Running counts** (collected = passed, 0 skipped):

| After | Count | | After | Count |
|---|---|---|---|---|
| base (spec commit) | 3727 | | T10 R12 / R3 | 3299 / 3278 |
| T2 G1 | 3710 | | T11 R4 / R5 / R6 / R7 / F | 3267 / 3253 / 3248 / 3246 / 3245 |
| T3 G2 | 3700 | | T12 renames | 3245 |
| T4 G3 | 3662 | | T13 E1 / E2+E3 / E4+E5 | 3245 / 3246 / 3246 |
| T5 G4a | 3593 | | T14 M1 / M2 / M3 | 3244 / 3243 / 3243 |
| T6 G4b | 3485 | | | |
| T7 G5 | 3429 | | | |
| T8 G6 | 3386 | | | |
| T9 G7 | 3347 | | | |

From Task 6 on, every count includes the frozen-values guard the batch 1 review added after Task 5 (`test_runtime_playback_context.py::test_runtime_value_classes_are_frozen`, 3594 after it), so the final count is 3243.

Batches (DEVELOPMENT_WORKFLOW.md §3.2, 15 tasks): **1–5**, **6–10**, **11–15**; stop and report after Tasks 5 and 10.

---

### Task 1: Proof tooling and baseline

**Files:** scratchpad only (`$SP/impl/`); ledger `.superpowers/sdd/2026-10-31-phase57-test-clean2/progress.md`.

**Interfaces:**
- Consumes: spec appendix files; `$SP/collect_params.py`.
- Produces: `collect.sh`, `proof.py`, `tokcheck.py`, `partition.py`, `runpy.sh`, `impl/lists/*.txt`, `impl/c00-spec.jsonl`.

- [ ] **Step 1:** Write the five scripts (table above). `python3 impl/partition.py impl/lists` → 17 lists, `total 486`.
- [ ] **Step 2:** `impl/collect.sh impl/c00-spec.jsonl` twice; the two files are byte-identical (determinism) and have 3727 lines.
- [ ] **Step 3: Red check of the tools.** `proof.py c00 c00 /dev/null /dev/null` → `PROOF OK`; `proof.py c00 c00 impl/lists/G1.txt /dev/null` → `FAIL` (17 missing removals reported as unpaired/multiset errors). `tokcheck.py <c>~1 <c>` on a recent commit that added test code (e.g. `git log -1 --format=%h -- tests`) → `TOKCHECK FAIL`; reversed → `TOKCHECK OK`.
- [ ] **Step 4:** Baseline full run `impl/runpy.sh impl/base-full.log -q -p no:cacheprovider tests` → `3727 passed`. Record in the ledger.
- [ ] **Step 5:** Commit this plan: `git add -f docs/superpowers/plans/2026-10-31-phase57-test-clean2.md`, `docs: plan phase 57 (test-clean2 removals)`.

### Task 2: G1 deletions (engine drain files)

**Files:** Modify `tests/test_onecore_segment_drain.py`, `tests/test_sapi5_segment_drain.py`, `tests/test_vocalizer_segment_drain.py`, `tests/worldvoice_cancel_wrapper_harness.py` (`leased_player()` `:328`).

**Interfaces:** Consumes `impl/lists/G1.txt`, `impl/c00-spec.jsonl`. Produces `impl/c02-g1.jsonl`.

- [ ] **Step 1:** Delete every id of `G1.txt`: whole functions (spec §5.1), rows (§5.2; D4 = the `"1:-1"` row of `test_native_and_parse_errors_fail_original_work_without_drain`), and for the VE/Cerence stacked pairs the value from the inner list (§5.3 last paragraph). Delete `leased_player` from the harness and its import in `test_vocalizer_segment_drain.py:18` (§5.7) after `grep -rnw leased_player tests/` shows no other user.
- [ ] **Step 2:** Proof block. Expected: 3710; pairs only `test_native_and_parse_errors_…[response5] → [response4]`; `TOKCHECK OK`.
- [ ] **Step 3:** Commit `test: remove the G1 engine-drain duplicates and pins`.

### Task 3: G2 deletions (segment host, lifecycle, scheduler)

**Files:** Modify `tests/test_rhvoice_segment_drain.py`, `tests/test_runtime_scheduler.py`, `tests/test_runtime_segment_completion.py`, `tests/test_segment_barriers.py` (`load_source` import `:5`), `tests/test_segment_host.py`, `tests/test_segment_lifecycle.py`.

**Interfaces:** Consumes `G2.txt`, `c02`. Produces `c03-g2.jsonl`.

- [ ] **Step 1:** Delete the `G2.txt` ids. The parametrize rows `[0.1]`, `[0.06]`, `[1]` go; `[0]`, `[0]`, `[2]` stay one-row parametrizes here (Task 12 drops the first two). `test_segment_barriers.py`: drop `load_source` from the import, keep `WORLDVOICE`.
- [ ] **Step 2:** Proof block. Expected: 3700; no pairs; `TOKCHECK OK`.
- [ ] **Step 3:** Commit `test: remove the G2 segment-host and scheduler duplicates`.

### Task 4: G3 deletions (runtime assembly and bridge)

**Files:** Modify `tests/test_completion_characterization.py`, `tests/test_completion_rules.py` (D9), `tests/test_f4_engine_adapters.py` (D10; drop `load_definitions` import line and `DRIVERS`, then `WORLDVOICE` if unused), `tests/test_f4_engine_session.py` (`FakeCore.fail_on` `:10`, `:20-21`), `tests/test_index_codec.py`, `tests/test_nvda_event_bridge.py`, `tests/test_nvda_event_bridge_contracts.py`, `tests/test_runtime_composition.py` (not R4's function), `tests/test_runtime_legacy_adapter.py`, `tests/test_runtime_playback_context.py`, `tests/test_runtime_session.py`, `tests/test_runtime_voice_state.py`.

**Interfaces:** Consumes `G3.txt`, `c03`. Produces `c04-g3.jsonl`.

- [ ] **Step 1:** Delete the `G3.txt` ids (`test_bytes_repr_loses_only_its_wrapper`: the `b'Arabic'` row) and the §5.7 orphans of these files, each re-checked by `grep -rnw`.
- [ ] **Step 2:** Proof block. Expected: 3662; no pairs; `TOKCHECK OK`.
- [ ] **Step 3:** Commit `test: remove the G3 runtime and bridge existence pins`.

### Task 5: G4a deletions (pipeline filters, edges, symbols, panels)

**Files:** Modify `tests/test_pipeline_filters.py` (not R1/R2's functions), `tests/test_pipeline_number_edges.py` (not R3's), `tests/test_pipeline_nvda_symbols.py`, `tests/test_pipeline_nvda_ssml.py` (D17 row `:48`), `tests/test_pipeline_log.py`, `tests/test_pipeline_passthrough.py`, `tests/test_pipeline_panels.py` (`CONFSPEC` `:14`), `tests/test_pipeline_voice_lookup.py`.

**Interfaces:** Consumes `G4a.txt`, `c04`. Produces `c05-g4a.jsonl`.

- [ ] **Step 1:** Delete the `G4a.txt` ids (D12 included; `test_no_edge_break_without_a_number_pause`: drop the `group` mode) and the orphans.
- [ ] **Step 2:** Proof block. Expected: 3593; pairs only in `test_number_wait_breaks_only_between_whole_numbers`, `test_number_re_finds_whole_numbers`, `test_number_wait_splits_numbers_separated_only_by_whitespace`; `TOKCHECK OK`.
- [ ] **Step 3:** Commit `test: remove the G4 pipeline filter and symbol duplicates`.
- [ ] **Step 4: Batch 1 boundary.** Report commits, proof results and counts to the orchestrator; wait for the batch review.

### Task 6: G4b deletions (pause, settings service, stages, unspaced)

**Files:** Modify `tests/test_pipeline_punctuation_pause.py`, `tests/test_pipeline_settings_service.py` (not R5's; `inspect` `:3`), `tests/test_pipeline_stages.py` (`worldvoice_conf` import `:8`, `plain_shape` `:611-612`), `tests/test_pipeline_unspaced_space.py` (D18 rows, D19; `SCRIPT_LOOKUP` `:18`, `class Marker` `:202`), `tests/test_legacy_speech_commands.py` (fixture `legacy` `:12-32`), `tests/test_lint_rewrites.py` (`:12-13`).

**Interfaces:** Consumes `G4b.txt`, `c05`. Produces `c06-g4b.jsonl`.

- [ ] **Step 1:** Delete the `G4b.txt` ids and the §5.7 orphans. `legacy` fixture: drop the `driver` import `:24`, `Voice=driver.Voice` `:28`, `"driver"` in the loop `:22`.
- [ ] **Step 2: Fixture probe (Review Focus 2).** Delete the three stubs `:18-20` (`config`, `languageHandler`, `synthDriverHandler`); run `tests/test_legacy_speech_commands.py` alone and in the full suite. Keep the deletion only if both pass; otherwise restore them and log `Ruling:`.
- [ ] **Step 3:** `_driver_methods` in `test_lint_rewrites.py`: drop `StringParameterInfo`, `NUMBER_MODE_CHOICES`; the file alone passes.
- [ ] **Step 4:** Proof block. Expected: 3485; pairs only in `test_scaled_waits_are_the_global_units_times_the_factor`, `test_other_synths_get_only_plain_breaks_from_the_stages`, `test_worldvoice_keeps_the_break_subclasses_from_the_stages`, `test_pauses_between`, `test_worked_examples`; `TOKCHECK OK`.
- [ ] **Step 5:** Commit `test: remove the G4 pause, settings and stage duplicates`.

### Task 7: G5 deletions (driver, panels, UI)

**Files:** Modify `tests/test_panel_layout.py`, `tests/test_role_panel.py` (only D-list id `test_failed_apply_…`; `pytest`, `checkbox()`, `class Control` only if unused after — M2's source still uses what it uses), `tests/test_role_panel_ui.py`, `tests/test_role_repository.py`, `tests/test_settings_order.py` (`voice_panel()` `:146-151`), `tests/test_settings_panel_save.py`, `tests/test_settings_panels.py` (not R7's), `tests/test_ui_controls.py`, `tests/test_ui_harness.py` (`BoxSizerHelper`, `Label` `:9`), `tests/test_ui_structure.py` (`:17-23`, `:126-133`), `tests/test_unicode_panel.py`, `tests/test_voice_settings_panel.py`, `tests/test_worldvoice_speak.py`. Delete `tests/test_role_guards.py`, `tests/test_worldvoice_index_command.py`.

**Interfaces:** Consumes `G5.txt`, `c06`. Produces `c07-g5.jsonl`.

- [ ] **Step 1:** Delete the `G5.txt` ids, the two emptied files, and the orphans; orphans of `test_role_panel.py` that M2's source test still uses wait for Task 14.
- [ ] **Step 2:** Proof block. Expected: 3429; pairs only in `test_read_control_without_a_control_is_absent`; `TOKCHECK OK` (deleted files allowed).
- [ ] **Step 3:** Commit `test: remove the G5 panel and UI duplicates`.

### Task 8: G6 deletions (guards, generators)

**Files:** Modify `tests/test_generate_unicode_scripts.py`, `tests/test_generate_unspaced_common.py`, `tests/test_generated_unicode_data.py` (D36 rows `:99-103`, D37 rows `:121-123`), `tests/test_hygiene_guards.py` (`:95-108`), `tests/test_native_strategy_guards.py` (D28–D30, D32, D33; D34/D35 stay), `tests/test_nvda_ready.py` (not `F`'s id; `_label_definitions()` `:216-230`), `tests/test_plugin_voice_contract.py` (D27; `BUNDLED_ENGINES` `:122`), `tests/test_script_languages.py` (`re`, `ADDON`, `EXCLUDED`), `tests/test_translator_comments.py` (`GROUP_MODE_MSGIDS` `:42`).

**Interfaces:** Consumes `G6.txt`, `c07`. Produces `c08-g6.jsonl`.

- [ ] **Step 1:** Delete the `G6.txt` ids and orphans (`test_an_unreadable_…`: drop the `directory` maker, keep `ids=["missing"]`).
- [ ] **Step 2:** Proof block. Expected: 3386; pairs only in `test_network_errors_name_the_url_and_suggest_a_local_file` (both generator files), `test_select_drops_characters_without_an_unspaced_script`; `TOKCHECK OK`.
- [ ] **Step 3:** Commit `test: remove the G6 guard and generator duplicates`.

### Task 9: G7 deletions (detection, install, registry)

**Files:** Modify `tests/test_core_archive.py` (2 ids only), `tests/test_detection_settings.py` (`ast`, `dataclasses`, `_detection_confspec` import), `tests/test_driver_ui_hooks.py`, `tests/test_driver_voice_base.py`, `tests/test_engine_discovery.py`, `tests/test_engine_filter.py`, `tests/test_engine_registry.py`, `tests/test_global_plugin_menu.py`, `tests/test_language_detector.py`, `tests/test_locales.py`, `tests/test_main_locale_policy.py`, `tests/test_number_language_choice.py`. Delete `tests/test_workspace.py`.

**Interfaces:** Consumes `G7.txt`, `c08`. Produces `c09-g7.jsonl`.

- [ ] **Step 1:** Delete the `G7.txt` ids, `test_workspace.py`, and the orphans. `test_core_archive.py` keeps `test_install_always_removes_the_archive` and `test_menu_import_reports_a_corrupt_archive` with their loader (N4).
- [ ] **Step 2:** Proof block. Expected: 3347; pairs only in `test_a_configured_engine_flag_overrides_the_manifest_default`, `test_plugin_with_old_contract_names_is_reported`, `test_engine_enabled_reads_the_config_then_the_manifest`; `TOKCHECK OK`.
- [ ] **Step 3:** Commit `test: remove the G7 detection, install and registry pins`.

### Task 10: Restructures R1–R3 (pipeline number tables)

**Files:** Modify `tests/test_pipeline_filters.py` (`TEXTS`/`SHARED`/`NUMBER_MODES` `:379-449`, `SPEC_TABLE` `:453-485`), `tests/test_pipeline_number_edges.py` (`item_rows` `:100-132`, `ROWS` `:192-317`, `STAGE_ROWS` `:318`).

**Interfaces:** Consumes `R12-filters.txt`, `R3-edges.txt`, `c09`. Produces `c10a-r12.jsonl`, `c10b-r3.jsonl`.

- [ ] **Step 1 (R1, R2):** Replace `test_number_mode`'s two stacked decorators by `@pytest.mark.parametrize(("text", "mode", "size", "pause"), CASES)`; `CASES` built from the tables so each `(mode, size, pause)` runs exactly its texts (spec §5.3 R1: no `("group",3,0)`/`("group",10,0)`; `SHARED` only for `("value",3,0)` and `("group",2,50)`; `-1234`, `123`, `12`, `1.2.3` out of `("value",3,0)`; `123` out of `("number",3,0)`). Delete the five `SPEC_TABLE` rows (R2).
- [ ] **Step 2:** Proof block without step 3 (restructure). Expected: 3299; the 27 `[R]` ids of `test_number_mode` in `-edited.txt` kept with the same strings; no pairs.
- [ ] **Step 3:** Commit `test: trim the number-mode tables to the cases with their own branch`.
- [ ] **Step 4 (R3):** Delete the `id="1g"` row; drop the item-wait-0 entry from the `"inside"` and `"numbers"` `item_rows` calls; make `STAGE_ROWS` leave out every `item_rows` row made at an item wait other than 0 (expression is free; non-`item_rows` rows unaffected).
- [ ] **Step 5:** Proof block without step 3. Expected: 3278; no pairs (all `ROWS` ids are explicit).
- [ ] **Step 6:** Commit `test: run each number-edge worked example once per distinct input`.
- [ ] **Step 7: Batch 2 boundary.** Report and wait.

### Task 11: Restructures R4–R7 and the `test_nvda_ready` fixture switch

**Files:** Modify `tests/test_runtime_composition.py:910-927`, `tests/test_pipeline_settings_service.py:464-515`, `tests/test_worldvoice_pipeline_settings.py:178-180`, `tests/test_settings_panels.py:320-322`, `tests/test_nvda_ready.py:98-99`.

**Interfaces:** Consumes `R4…R7`, `F-nvda-ready` lists, `c10b`. Produces `c11a`…`c11e` collections.

- [ ] **Step 1 (R4):** one `@pytest.mark.parametrize(("failure", "engine"), [("wrong_core", "OneCore"), ("unsupported", "Espeak"), ("support_error", "OneCore")])`. Proof → 3267. Commit `test: keep the three legacy-fallback cases that differ`.
- [ ] **Step 2 (R5):** both tests parametrize over a new list `scope`, `number_mode`, `global_wait_factor`, `punctuation_pause_enabled`, `group_size`; `OLD_DEFAULTS` untouched. Proof → 3253. Commit `test: check the invalid-key default once per kind of field`.
- [ ] **Step 3 (R6):** one `("consistent", "name")` parametrize: the six `False-*` and `True-volume`. Proof → 3248. Commit.
- [ ] **Step 4 (R7):** one `("pause", "remove")` parametrize: `(False, True)`, `(True, False)`. Proof → 3246. Commit.
- [ ] **Step 5 (F):** `def test_ready_on_ref_nvda_is_true_and_silent(skipped_engine, monkeypatch)`; `engine` fixture stays (used by `test_live_and_static_views_agree_on_ref_nvda`). Proof → 3245, ids `[Espeak]`, `[OneCore]` unchanged. Commit `test: check NVDA readiness only for the engines it skips`.
- [ ] Each step: the file alone passes (Review Focus 2); proof block without step 3; ids equal to the kept ids, no pairs.

### Task 12: Renames of the two single-row timing parametrizes

**Files:** Modify `tests/test_segment_host.py:269-276`, `tests/test_segment_lifecycle.py:759-835`.

**Interfaces:** Consumes `c11e`; renames `impl/renames-t12.txt` (the two `[0] -> no-param` lines of `-renames.txt`). Produces `c12a`, `c12b`.

- [ ] **Step 1:** `test_retire_waits_for_admitted_consumers`: delete the parametrize, the `start_delay` parameter and `Event().wait(start_delay)` with its comment; drop `Event` import if unused. Proof (REMOVED `/dev/null`, RENAMES one line) → 3245. Run the file 5× → all pass. Commit `test: drop the delay parameter left with one value`.
- [ ] **Step 2:** `test_queued_run_does_not_poll_its_token`: delete the parametrize and `start_delay` argument; `CountingToken.__init__` and `_accept_counting` lose `start_delay`; delete the `if self.checks == 0: Event().wait(...)` lines (grep: `test_wait_idle_wakes_on_token_cancel_without_polling` passes no delay). Proof → 3245. File 5× → pass. Commit.

### Task 13: Edits E1–E5

**Files:** Modify `tests/test_worldvoice_cancel_wrappers.py:70-72`, `tests/test_pipeline_structure.py:86-155`, `:219-225`, `tests/test_native_strategy_guards.py:386-395`, `:687-690`.

**Interfaces:** Consumes `c12b`. Produces `c13a`…`c13c`.

- [ ] **Step 1 (E1):** delete the token comment and two token assertions. Proof (empty lists) → 3245; `TOKCHECK OK`. Commit `test: leave the request-token rule to the one AST guard`.
- [ ] **Step 2 (E2, E3):** delete `MOVED` (+comment), `top_level_names` and the `:136` assertion after `grep -rnw` shows no other user; move the `symbols.py` relative-import assertion (with the comment `:137-139`) unchanged into `def test_symbols_module_has_no_relative_imports():` right after the parametrized test; delete the `default_voice` scan `:219-225`. Red/green: the new test fails if `addon/.../pipeline/symbols.py` gains `from . import x` (check in a scratch copy only), passes as is. Proof (RENAMES `+ tests/test_pipeline_structure.py::test_symbols_module_has_no_relative_imports`) → 3246. Commit `test: check the symbols module's imports once, not per pipeline module`.
- [ ] **Step 3 (E4, E5):** delete `assert "_guardInstalled" not in source`; rename to `test_vocalizer_voice_declares_waitfactor_and_variant`; reword `:388-390` to what is left; reword `:687-690` so it names this guard as the one check on the token keyword and trait (no reference to the removed test). Proof (RENAMES the two `[VE|Cerence]` lines) → 3246. Commit `test: name the vocalizer guard after what it still checks`.

- [ ] **Step 4 (review cleanup, batch 1 m1/m3, batch 2 m3):** one `test:` commit that drops the branches and entries the removed rows left unreached (ledger list) and rewords the comment at `test_pipeline_nvda_symbols.py` (`# Never a path …`) and the stale module docstrings of `test_role_panel.py` and `test_legacy_speech_commands.py`. Proof (empty lists) → collection unchanged; full suite passes.

### Task 14: Merges M1, M2, M3

**Files:** Modify `tests/test_worldvoice_cancel_wrappers.py:210-245`, `tests/test_role_panel_ui.py:132-145`, `tests/test_role_panel.py` (two kept tests remain), `tests/test_core_install.py`; delete `tests/test_core_archive.py`.

**Interfaces:** Consumes `M1.txt`, `M2.txt`, `c13c`. Produces `c14a`…`c14c`; `impl/movecheck.py`.

- [ ] **Step 1 (M1):** in `test_cancelled_request_drops_index_and_done_notifications` add the LEGACY_DONE comment and `idles_before = real_player(core).idles` after the live request, `assert real_player(core).idles == idles_before` after the cancelled one; red check in a scratch copy: the merged assertion fails if the cancelled request records an idle (e.g. force `idles += 1` in the harness player). Delete the source test. Proof → 3244. Concurrency file 5× → pass. Commit `test: fold the core-cancel idle check into the cancelled-request test`.
- [ ] **Step 2 (M2):** add `assert ("EVT_WINDOW_DESTROY", panel._onDestroy, None) in panel.bindings` and `assert panel.disable is False`; red check in a scratch copy with `role.py:52` removed → fails. Delete D21 and the `test_role_panel.py` orphans (`pytest`, `checkbox()`, `class Control`). Proof → 3243. Commit `test: check the role panel's destroy binding in the UI test`.
- [ ] **Step 3 (M3):** move `test_core_archive.py:48-106` verbatim to the end of `test_core_install.py`, add `import types`, `load_definitions` from `addon_loader`, `PLUGIN = ADDON / "globalPlugins/WorldVoice/__init__.py"`, one docstring sentence (these two tests load the real files so coverage sees `coreArchive.py`); delete `test_core_archive.py`. `movecheck.py`: the moved blocks appear byte-identical and in order in the new file; `new − old` is exactly moved blocks + the listed additions → `MOVE OK`. Proof (RENAMES the three `test_core_archive` lines) → 3243. `python3 -m pytest -q --cov=addon/generics --cov-branch tests/test_core_install.py` → `coreArchive.py` 100%. Commit `test: move the archive tests next to the install tests`.

### Task 15: Final verification

**Files:** none (ledger only).

**Interfaces:** Consumes everything above; `impl/covcmp.py`.

- [ ] **Step 1:** End-to-end proof: `proof.py $SP/base-params.jsonl impl/c14c.jsonl <…-remove.txt> <…-renames.txt>` → `PROOF OK`; every pair is in a spec §5.2 function (or D4). Also the base check from `c00-spec.jsonl`.
- [ ] **Step 2:** Full suite → `3243 passed`, 0 skipped. Every touched test file run alone → pass.
- [ ] **Step 3:** `COVERAGE_FILE=$SP/impl/p57.coverage impl/runpy.sh $SP/impl/p57-coverage.txt tests -q -p no:cacheprovider --cov=addon --cov-branch --cov-report=term`; `covcmp.py` against `…-coverage-before.txt`: Stmts/Branch equal per module, Miss/BrPart not higher (TOTAL Miss ≤ 180, BrPart ≤ 157); an increase only in `runtime/scheduler.py`, `runtime/segmentHost.py`, `runtime/_segmentLifecycle.py` is accepted after a second full run puts it back at or below baseline; `addon/generics/coreArchive.py` 100%.
- [ ] **Step 4:** 5× each: `tests/test_segment_host.py`, `tests/test_segment_lifecycle.py`, `tests/test_runtime_scheduler.py`, `tests/test_worldvoice_cancel_wrappers.py`, `tests/test_vocalizer_segment_drain.py` → all pass.
- [ ] **Step 5:** `prek run --all-files` all Passed; `git diff --check master`; `git diff --stat master -- addon` empty; the two protected-path commands of DEVELOPMENT_WORKFLOW.md §7 print nothing.
- [ ] **Step 6:** Report: commits, proofs, counts, coverage comparison, every `Ruling:`.
