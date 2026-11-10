# Phase 59: test-clean3 removals and merges

Date: 2026-11-10.
Base: `master` `f1bbec0`. Branch: `phase59-test-clean3`. Normal flow (DEVELOPMENT_WORKFLOW.md §3).
Source: the test audit `storage/test-clean3.md` (2026-11-10, base `f1bbec0`, 3998 tests; git-ignored), its id lists `storage/test-clean3-final-remove.txt` (294), `storage/test-clean3-merge.txt` (132) and `storage/test-clean3-decide.txt` (52), and the audit's coverage data in its scratchpad (`cov-before.db` with per-test contexts, `report-before.txt`, `cov-remove-decide.db`).

User decision (2026-11-10, audit §1.4): **follow the leaning of every decide item.** 44 of the 52 decide items are removed (two of them only after generic translator checks replace them, §8), 8 are kept. All 50 audited merge suggestions (49 numbered rows, §6) are in scope. The coverage gaps of the audit come in a later phase (§12).

Appendix files, committed next to this spec:

| File | Content |
|---|---|
| `2026-11-10-phase59-test-clean3-remove.txt` | The **final** removal list: 294 collected node ids that disappear (250 audit removals + 44 decide items that lean remove). Sorted, ids exactly as `pytest --collect-only -q` prints them at `f1bbec0`. |
| `2026-11-10-phase59-test-clean3-merge.txt` | The 132 ids the merges replace, one per line as `<row>\t<id>` (`G1-M1` … `G8-M5`, §6), ids exactly as collected at `f1bbec0`. |
| `2026-11-10-phase59-test-clean3-decide.txt` | The 52 decide ids as `<remove\|keep>\t<id>` (§3). |
| `2026-11-10-phase59-test-clean3-coverage-before.txt` | The audit's `coverage report` at `f1bbec0` (per module; TOTAL 8625 stmts / 69 miss, 2472 branches / 91 partial, 98.56%), the reference for the per-module report check (§9.4). |

All four lists were checked by script against `python3 -m pytest tests --collect-only -q -p no:cacheprovider` at `f1bbec0` (3998 ids): every id is collected, none repeats, the removal and merge lists are disjoint, the removal list is the 250 audit removals plus exactly the decide ids tagged `remove`.

| | Count |
|---|---|
| Collected at `f1bbec0` | 3998 (audit §1: 3998 passed, 0 skipped) |
| Removed: audit list | 250 |
| Removed: decide items that lean remove | 44 |
| **Removed in total** | **294** |
| Kept decide items | 8 (unchanged) |
| Ids replaced by merges | 132 |
| Ids the merges produce | 72 (net **−60**, §6.9) |
| New translator tests | 2 (§8) |
| **Collected and passed after** | **3646** (= 3998 − 294 − 60 + 2), 0 skipped |
| Test files deleted | 2: `test_f4_engine_session.py` (emptied by removals), `test_global_plugin_lifecycle.py` (moved into `test_global_plugin_menu.py` by G8-M4) |
| Changes under `addon/` | none |

Line references are `tests/<file>:<line>` at `f1bbec0` unless they name another path.

## 1. Problem and goal

The suite has grown from 3332 (after phase 58) to 3998 collected tests. The audit found 250 tests that are duplicates, subsumed by a test asserting a superset on the same path (often a Hypothesis property added later), parametrize cases that take no branch of their own, or one existence pin (audit §1, §2.3). It left 52 ids to the user and proposed 50 merges that fold near-identical tests into a parametrize or into an existing test without losing a path or an assertion. Deselecting the 302 removal and decide ids lost no arc of branch coverage (audit §1, A.1).

Goal: delete the 294 ids from the source, do every merge with every path and assertion of the tests it replaces, replace the two hand-kept translator lists with two generic catalog checks, and drop what the deletions and merges leave unused. Nothing under `addon/` changes; NVDA users see and hear nothing different.

## 2. What disappears

- `2026-11-10-phase59-test-clean3-remove.txt` (294 ids) is the only source of truth for removals; §9.1 proves the collection matches it.
- Per kind (computed from the collection at `f1bbec0`):

| Kind | Functions | Ids |
|---|---|---|
| Whole test function deleted (every case removed) | 61 | 110 |
| Some cases of a parametrize removed | 50 | 184 |

- Per audit group (the deletion commits of §10 follow this split):

| Group | Audit removals | Decide removals | Total |
|---|---|---|---|
| G1 engine drains, contract | 5 | 6 (D1) | 11 |
| G2 segment host, scheduler | 0 | 0 | 0 |
| G3 runtime, adapters | 14 | 2 (D2) | 16 |
| G4 pipeline numbers, pauses | 152 | 12 (D3) | 164 |
| G5 stages, settings, speak | 23 | 14 (D4–D8) | 37 |
| G6 driver, panels | 26 | 2 (D9) | 28 |
| G7 guards, generators | 4 | 3 (D10, D11) | 7 (2 of them in the translator commit, §8) |
| G8 detection, registry, plugin | 26 | 5 (D14–D16) | 31 |
| Total | 250 | 44 | 294 |

The reasons for each removal are in the audit's per-group 移除清單 tables; the spec does not repeat them. Notes on cross-references between groups are in §4.

## 3. The decide items (52 ids)

Every row: **Decided by the user (2026-11-10): follow the audit's leaning.**

| # | Test (ids) | Leaning | Action in this phase |
|---|---|---|---|
| D1 | `test_vocalizer_init_cleanup.py::test_a_built_core_keeps_its_resources[VE\|Cerence]` (`:147-156`); `test_wrapper_init_cleanup.py::test_rhvoice_a_built_core_keeps_its_resources` (`:161-170`), `::test_espeak_a_built_core_keeps_its_resources` (`:260-269`), `::test_onecore_a_built_core_keeps_its_host` (`:407-414`), `::test_sapi5_a_built_core_keeps_its_resources` (`:536-546`) (6) | remove | Delete. |
| D2 | `test_f4_engine_session.py::test_reopen_reapplies_same_snapshot` (`:93-104`), `::test_partial_failure_invalidates_stamp` (`:107-115`) (2) | remove | Delete; with the three audit removals (`:57-67`, `:70-80`, `:83-90`) the file is empty and is deleted with its `FakeCore` and `engine` fixture. `conftest.py`'s `session_module` stays (the `snap` fixture uses it, audit G3 連帶可刪). |
| D3 | `test_pipeline_number_groups.py::test_edges_appear_iff_a_group_and_a_pause[*]` (12, `:245-253`) | remove | Delete the function. |
| D4 | `test_pipeline_settings_service.py::test_a_stored_group_mode_reads_as_value_and_keeps_the_stored_size` (`:472-477`) | remove | Delete. |
| D5 | `test_pipeline_nvda_ssml.py::test_nvda_ssml_keeps_every_word_and_pause_of_the_scope_all_output[number-pauses1]` (`:46-68`) | remove | Delete the `number` row; `[value-pauses0]` stays (index 0, id unchanged). |
| D6 | `test_worldvoice_speak.py::test_pause_settings_keep_the_voices[number-pause-after\|number-pause-before]` (2) | remove | Delete the `number-pause` `pytest.param` (`:1201`); the function (`:1191-1218`) and the two `punctuation-*` rows stay. |
| D7 | `test_worldvoice_speak.py::test_a_hyphen_after_a_word_stays_with_it[en-x-*\|en-han2-*\|zh-han2-*]` (6) | remove | Delete the `HYPHEN_ROWS` rows `id="en-x"` (`:940`), `id="en-han2"` (`:942`), `id="zh-han2"` (`:951`). |
| D8 | `test_worldvoice_speak.py::test_leading_punctuation_is_read_by_the_voice_of_the_text[full-width-paren-*\|paren-han-*]` (4) | remove | Delete the rows `id="full-width-paren"` (`:1133`) and `id="paren-han"` (`:1134`). |
| D9 | `test_settings_table_guard.py::test_group_size_is_an_independent_panel_only_spin` (`:425-431`), `::test_segment_length_is_an_independent_panel_only_spin` (`:434-444`) (2) | remove | Delete. |
| D10 | `test_translator_comments.py::test_changed_label_strings_have_translator_comments` (`:123-128`), `::test_zh_tw_catalog_follows_the_labels` (`:148-151`) (2) | remove after the generic checks | Replaced by X1 and X2 (§8) in the same phase; deleted only in the commit after the one that adds X1 and X2. |
| D11 | `test_plugin_voice_contract.py::test_pre_rename_names_map_onto_the_base_voice` (`:129-137`) | remove | Delete, with `pre_rename_names` (`:122-126`) and what only it uses (K-G7, §5.4). |
| D12 | `test_native_strategy_guards.py::test_every_strategy_feeds_and_plays_out_its_audio[*]` (6, `:569-575`) | keep | Keep unchanged. |
| D13 | `test_native_strategy_guards.py::test_a_local_neural_is_guarded_when_it_defines_a_strategy[strategy\|snapshot]` (2, `:52-67`) | keep | Keep unchanged (removal waits for the user to confirm `driver/Neural` is never put back, together with the UNTRACKED exceptions; audit G7). |
| D14 | `test_language_detector.py::test_a_leading_run_follows_the_text_after_it[paren\|curly-quote]` (2, `:547-581`) | remove | Delete the two rows. |
| D15 | `test_language_detector.py::test_a_leading_run_follows_the_text_after_it[full-width-paren\|paren-han]` (2) | remove | Delete the two rows. |
| D16 | `test_language_detector.py::test_detection_keeps_these_as_today[paren-zh]` (`:584-612`) | remove | Delete the row. |

Totals: removed 44 (D1 6, D2 2, D3 12, D4 1, D5 1, D6 2, D7 6, D8 4, D9 2, D10 2, D11 1, D14 2, D15 2, D16 1); kept 8 (D12 6, D13 2).

## 4. Notes on the audit

**N1: cross-group citations.** Some removal reasons cite a test that another group removes or merges. Each was re-checked; the chain still ends in a kept test:

| Removed | Cites | Status of the cited test | Still covered by |
|---|---|---|---|
| G5 `test_worldvoice_speak.py::test_by_default_a_long_sentence_is_one_segment` (`:470-471`) | `test_pipeline_segment_pause.py::test_nothing_changes_without_a_pause[0-7]` | removed (G4; the whole function `:103-108`) | `test_pipeline_segment_pause.py::test_property_no_pause_leaves_the_sequence_alone` (the G4 reason for that removal) and `::test_nothing_changes_for_real_settings[9]` (kept) |
| G5 `test_pipeline_stages.py::test_the_new_breaks_keep_their_parents` (`:411-420`) | `test_pipeline_unspaced_space.py::test_the_space_pause_is_an_unspaced_space_break` | removed (G4, `:344-347`) | `test_pipeline_stages.py::test_a_synth_without_roles_gets_a_plain_space_pause`, `::test_other_synths_get_only_plain_breaks_from_the_stages[*]`, `::test_plain_breaks_mark_only_edge_breaks` (all kept) |
| G6 `test_settings_panels.py::test_pipeline_panel_saves_an_out_of_range_group_size_as_the_default[1-1\|11-11]` and `::…shows…[1-1\|12-12]` | `test_pipeline_settings_service.py::test_group_size_outside_its_range_reads_as_the_default` "0、1、11、上限、"7"、-1、2^31、10^20" | its `[1-1]`, `[11-11]`, `[100000000000000000000-0]` rows are removed (G5) | its kept rows `0`, `7`, `2147483647`, `-1`, `2147483648` and `test_pipeline_pause_properties.py::test_property_group_size_convert_keeps_or_resets` (merged by G4-M2, kept as `[group_size]`) |
| G1 `test_espeak_segment_drain.py::test_real_profile_is_enabled_with_unverified_evidence` (`:442-444`); G3 `test_runtime_completion_policies.py::test_select_matches_contract_for[True-True]` | `test_runtime_completion_policies.py::test_actual_outer_voice_and_core_select_enabled_drain_profiles[*]` | merged into `test_six_enabled_profiles_use_shared_lifecycle` (G3-M2) | the merged test keeps every audio-mode assertion and the `select` assertion for each engine |
| G3 `test_runtime_legacy_adapter.py::test_a_new_core_gets_the_voice_set` (`:272-282`); D2 | `::test_reopening_sets_the_voice_even_on_the_same_core_object`, `::test_after_a_failed_apply_the_same_voice_is_set_again[hook]` | become `@example`s of the property (G3-M1) | the property with those examples, which G3-M1 also gives the source tests' remaining assertions (N4) |
| G1 `test_sapi5_segment_drain.py` (merge 7 reason) | `::test_end_stream_waits_for_actual_idle_and_preserves_tail_indexes` | parametrized by G1-M13 (`[speech]`) | the `[speech]` case, same body |
| G6 `test_ui_controls.py::test_apply_dependencies_counts_no_value_as_not_expected` (`:224-228`) | `::test_apply_dependencies_enables_dependents_from_their_controller[value-False-False]` | renamed by T8 (§7) | the same test without its single-row parametrize |

**N2: 49 numbered merge rows, not 50.** The audit counts "50 組" (audit §1, §1.1), but its group sections number 13 + 8 + 5 + 3 + 5 + 6 + 4 + 5 = 49 rows (G2's M8 has three parts a–c, so the merge file uses 51 tags). The id and net counts are exact and do add up: 35 + 19 + 17 + 18 + 10 + 13 + 12 + 8 = 132 ids, −15 −5 −17 −5 −1 −11 +0 −6 = **−60** (§6.9). The spec uses the audit's numbering (`G<n>-M<k>`).

**N3: the arcs only removed or merged tests reach.** Over `cov-before.db`, the arcs executed by no test outside the 294 + 132 ids are exactly 18:

| Module | Arcs | Only test(s) | Kept by |
|---|---|---|---|
| `addon/globalPlugins/WorldVoice/panels/role.py` | `153->154`, `154->-152`, `294->295`, `295->-292` | `test_role_panel_ui.py::test_panel_for_another_synth_only_says_so` | G6-M1 (`postInit`, `onDiscard`, `onSave` move into the merged test) |
| `addon/globalPlugins/WorldVoice/panels/detection.py` | `92->93`, `93->-91` | `test_settings_panels.py::test_unicode_panel_for_another_synth_only_says_so` | G6-M1 (`onSave`) |
| `addon/synthDrivers/WorldVoice/driver/VE/__init__.py` `544->-537`; `driver/Cerence/__init__.py` `549->-542` | | `test_vocalizer_segment_drain.py::test_empty_wrapper_text_makes_no_native_call[VE\|Cerence]` | G1-M9 (`emptied` row) |
| `addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py` | `491->492`, `492->-461` | `test_onecore_segment_drain.py::test_cancelled_segment_feed_is_stopped_by_the_lease_before_successor` | G1-M12 (`segment` case) |
| `addon/globalPlugins/WorldVoice/__init__.py` | `45->46`, `46->48`, `48->50`, `75->-71` | `test_global_plugin_lifecycle.py::test_dead_menu_runtime_error_does_not_stop_cleanup` | G8-M4 (the rewritten dead-menu test; `terminate` `:43-51`, `removeMenu` `:71-79` of the real module) |
| same | `72->-71` | `test_global_plugin_lifecycle.py::test_secure_mode_terminate_runs_every_cleanup_step` | G8-M4 (terminate in secure mode) |
| same | `-1->28` | both `test_global_plugin_lifecycle.py` tests | **lost by design** (below) |
| same | `-1->81`, `81->-1` | `test_core_install.py::test_menu_import_reports_a_corrupt_archive` | **lost by design** (below) |

The last three are entry and exit arcs of a fragment that `load_definitions` compiles on its own (`tests/test_global_plugin_lifecycle.py:10-11`, `tests/test_core_install.py:223`): `-1` is the fragment's module entry, which the real module never has. Lines 28 and 81 stay covered through the real module (`(25,28)`, `(28,29)`, `(71,81)`, `(81,120)` are executed by the `ui_harness` tests of `test_global_plugin_menu.py`). These are the same kind of arcs phase 57 accepted (phase 57 spec D20, N3). The coverage gate (§9.3) lists exactly these three as allowed losses. *Decided by orchestrator with the recommended default; user may override before merge* (the alternative, keeping a `load_definitions` fragment test only for these arcs, keeps nothing a user can hear or see).

**N4: G3-M1 needs two assertions the property lacks.** `test_runtime_legacy_adapter.py::test_property_the_voice_is_set_unless_the_same_healthy_core_already_took_it` (`:324-357`) asserts the voice write, the failure and the complete write set per step, but not (a) `adapter.core is core` after a reopen (`test_reopening_sets_the_voice_even_on_the_same_core_object`, `:266`) nor (b) the stored voice after a failed apply (`test_after_a_failed_apply_the_same_voice_is_set_again`, `core.voice == "a"`, `:243`). G3-M1 adds both to the property (§6.3), so the examples keep every assertion of the tests they replace.

**N5: renumbered ids caused by row deletions.** Two kept ids change only because an earlier or duplicate row goes (pytest's automatic ids); §9.1 pairs them by function and parameters:
- `test_voice_settings_repository.py::test_load_uses_the_default_for_a_stored_value_int_refuses[stored4]` → `[stored3]` (`"1e2"` at index 3 goes, `:80`).
- `test_voice_settings_repository.py::test_load_keeps_the_bounds_of_the_int_parameters_without_a_log[100_0]` → `[100]` (the int `100` goes, `:131`; the string `"100"` is no longer a duplicate id).
Every other partial removal keeps the kept ids: explicit ids, ids built from parameter values, or removed rows at the end of an index-numbered list (`test_pipeline_filters.py::test_every_mode_keeps_the_original_digits` removes `expected3`/`expected4`, `test_pipeline_number_edges.py::test_number_wait_factor_splits_spaced_numbers_except_in_number_mode` removes `expected2`, `test_pipeline_nvda_ssml.py` D5 removes `pauses1`).

**N6: the translator facts (§8).** At `f1bbec0` the add-on has 12 modules with a gettext call (`_translated_modules()`, `tests/test_translator_comments.py:157-168`), every call is `_("<literal>")` (no `pgettext`, `ngettext`, `npgettext`, no non-literal argument), giving 90 distinct msgids; `buildVars.py` adds three `_()` calls (`:21` summary, `:24` description, `:29` changelog; "WorldVoice" is also a source msgid). The zh_TW catalog has 92 entries, no `msgctxt`, no `msgid_plural`, no obsolete `#~` entry; every one of the 92 is used and translated. So X1 and X2 pass today.

**N7: the changelog string.** The user's wording names buildVars' summary and description. The changelog `_()` (`buildVars.py:29`) is extracted by `scons pot` too (`buildVars.py:70` `i18nSources = pythonSources + ["buildVars.py"]`; `sconstruct:130-137`) and is in the zh_TW catalog, so X2 would report it as unused unless it counts as a source string. X1 and X2 therefore read every `_()` call of `buildVars.py`. Consequence: a version's new changelog needs its zh_TW msgstr in the same commit, as every other new string does (DEVELOPMENT_WORKFLOW.md §6). *Decided by orchestrator with the recommended default; user may override before merge.*

**N8: what the translator replacement no longer checks.** `test_changed_label_strings_have_translator_comments` also asserted that 18 listed labels have a `# Translators:` comment and are still used, and that 26 old msgids are no longer used. After this phase nothing checks that a gettext call has a `# Translators:` comment (44 legacy strings lack one; out of scope by the user's decision, audit §1.4 G7); `test_translator_comments_precede_gettext_calls` (`:31-39`) still checks that every such comment sits on a gettext call. The "old msgid is gone from the catalog" half is covered by X2.

## 5. How the removals are made

### 5.1 Whole functions

Delete the function with its decorators and the comment block directly above it that only describes it. 61 functions, 110 ids (the two D10 functions in the translator commit, §8).

### 5.2 Rows and values

When the removed cases are whole rows of a parametrize list, or whole values of one of several stacked parametrizes, delete those rows or values. Explicit ids stay. A parametrize left with one row stays a one-row parametrize (its id does not change), unless §5.3 or §7 says otherwise. Notable cases:

- `test_pipeline_number_groups.py::test_numbers_that_only_whitespace_separates_get_one_break` (`:256-266`): delete `"  "`/`"two"` and `"　"`/`"ideographic"` from the `space` values and ids (`:256`).
- `test_pipeline_filters.py::test_groups_keep_leading_zeros_and_every_digit` (`:741-753`): delete `"none"` from the mode values; keep `["value"]` as a one-value parametrize so the three kept ids do not change (audit G4 allows either). *Decided by orchestrator with the recommended default; user may override before merge.*
- `test_pipeline_filters.py::test_number_modes_and_group_sizes_name_each_symbol` (`:519-539`): delete the rows `("value", 1, 1)`, `("none", 3, 2)`, `("none", 2, 3)`, `("number", 3, 2)`, `("number", 2, 3)` of the `mode, size, column` list (`:520-531`); the three spec 7.1 columns stay (21 ids). The helper edit this needs is R3.
- `test_pipeline_filters.py::test_number_mode` (`:474-480`, `CASES` built from tables just above): delete `12` and `1.2.3` from the `("number", 0, 0)` table and `12.5` and `-1234` from the `("number", 0, 50)` table.
- `test_pipeline_number_edges.py`: delete the `ROWS` rows `i14` (`:418`), `i19` (`:436`), `i20` (`:438`), `i27` (`:451`), `i28` (`:452`) (each removes one id from `test_number_stage_worked_examples` and one from `test_worked_examples_through_every_stage`), the `ITEM_ROWS` row `value-size3` (`:170-176`) and 19 `SPACED_ROWS` rows (`:774-834`; `:775-784`, `:789`, `:797`, `:804`, `:806-809`, `:814`, `:820` per the ids in the remove list). The three `*-item0` ids are R2.
- `test_runtime_completion_policies.py::test_disabled_force_switch_restores_legacy_done` (`:519-544`): parametrize over `["OneCore"]` instead of `SIX_ENGINES` (`:519`); the id stays `[OneCore]`.
- `test_panel_layout.py::test_the_number_mode_controls_no_other_setting` (`:94-97`): keep only `"none"`.
- `test_settings_panels.py::test_pipeline_panel_group_size_is_enabled_for_every_stored_mode` (`:138-143`): keep `none`, `group`.
- Language detector rows (`test_language_detector.py`, functions at `:184-225`, `:229-292`, `:296-342`, `:347-360`, `:375-406`, `:429-440`, `:450-487`, `:496-509`, `:512-515`, `:547-581`, `:584-612`, `:926-932`, `:977-980`): delete the listed rows; `test_decimal_digits_follow_the_letter_rule_of_their_script` is left with one row (T7, §7).

### 5.3 Restructured parametrizations (kept ids unchanged)

| # | Test | Restructure |
|---|---|---|
| R1 | `test_generate_unspaced_common.py::test_network_errors_name_the_url_and_suggest_a_local_file` (`:436-457`, `error` × `name, option`) | One `@pytest.mark.parametrize(("name", "option", "error"), [("ScriptExtensions.txt", "--source", urllib.error.URLError("no route")), ("UnicodeData.txt", "--unicode-data", TimeoutError("timed out"))])`. pytest joins stacked ids starting from the decorator nearest the function, so the single list yields the same strings: `[ScriptExtensions.txt---source-error0]`, `[UnicodeData.txt---unicode-data-error1]` (audit G7). |
| R2 | `test_pipeline_number_edges.py` `ITEM_ROWS` comprehension (`:177-192`, ids `{name}-{mode}-item0`) | Replace it by the three rows that stay, listed out: `end-value-item0`, `end-none-item0`, `whole-numbers-value-item0` (same sequences, options and expected values). Removes `alone-value-item0`, `alone-none-item0`, `whole-numbers-none-item0` (audit G4 連帶可刪). |
| R3 | `test_pipeline_filters.py:539` | After §5.2 only `("value", 3, 2)` and `("value", 2, 3)` take the `size != 0` branch, so `pieces_in(mode, row[column])` is `spoken(row[column])` (`pieces_in`'s last line, `:516`). Use `spoken(row[column])` and delete `pieces_in` (`:506-516`) and `digit_by_digit` (`:500-503`) (audit G4 連帶可刪; `broken`, `N`, `named`, `spoken`, `joined` keep other users). |

### 5.4 Knock-on deletions (audit 連帶可刪, re-checked by grep on the worktree)

| Id | File | Delete | Why (grep at `f1bbec0`) | Commit |
|---|---|---|---|---|
| K-G1a | `test_engine_segment_contract.py` | `class C3Blocking` (`:32-33`), the `xfails` parameter and branch of `_engines` (`:36-46`, keep the plain `pytest.param(name, id=name)` loop), the C3 check at the end of `test_speak_segment_returns_before_delivery` (`:163-165`, which G1-M1 replaces by a plain assertion), docstring `:3-5` ("Known gaps are strict xfails …") | no caller passes `xfails` (`:98`, `:116`, `:133`, `:146`, `:168`, `:175`, `:197`, `:211`, `:231` all call `_engines()`); `C3Blocking` only at `:165` | G1-M1 |
| K-G1b | `test_espeak_segment_drain.py` | `get_ident` (`:4`), `delivery_thread` (`:10`), `segment_lifecycle` (`:12`), `quiet_period` (`:15`) | used only by `test_speak_after_terminate_fails_through_lifecycle_delivery` (`:477`, `:485`, `:496`, `:502`); `segment_host` stays (`:191`, `:529`) | G1-M2 |
| K-G2a | `test_playback_work.py` | `new_work` (`:53-59`) | no user today (`grep -rn new_work tests/`: only the definition and an unrelated test name) | G2 deletion |
| K-G2b | `test_segment_host.py` | the three identical `broken(operation)` closures (`:638`, `:665`, `:708`) | replaced by one helper `break_boundary_hook(env, monkeypatch)` that patches `env.host.wait_native_boundary` with the same closure through the given `monkeypatch` (so `monkeypatch.undo()` in `test_reset_recovers_from_a_lifecycle_fault`, `:648`, still restores it) | G2-M4 |
| K-G3 | `test_f4_engine_session.py` | the whole file | D2 | G3 deletion |
| K-G4a | `test_pipeline_number_groups.py` | `class Marker` (`:157-158`), `MARKER` (`:292`), `NB0` from `:217` | `Marker` used at `:222` (removed `test_off_without_groups_or_wrapper_is_the_identity`) and `:292`; `MARKER` only in the removed `command` row (`:299`); `NB0` has no user today | G4 deletion |
| K-G4b | `test_pipeline_segment_pause.py` | `class CallbackCommand` (`:25-26`), `marked_plain_break` (`:137-138`) | used only by the removed `[callback]` (`:164`) and `[marked-plain]` (`:146`) rows | G4 deletion |
| K-G4c | `test_pipeline_filters.py` | `pieces_in`, `digit_by_digit` | R3 | G4 restructure |
| K-G6a | `test_settings_panels.py:12` | `WORLDVOICE`, `load_definitions` from the `addon_loader` import (`load_source` stays) | used only by `test_number_modes_match_the_driver_and_the_panel` (`:113-114`) | G6-M2 |
| K-G6b | `test_role_panel_ui.py:10` | `TextCtrl` from the `ui_harness` import | used only at `:112` | G6-M1 |
| K-G7a | `test_plugin_voice_contract.py` | `pre_rename_names` (`:122-126`), `import importlib` (`:4`), `ROOT` (`:12`), `from pathlib import Path` (`:6`) | only D11 and `pre_rename_names` use them; `inspect` stays (`:81`); re-check `ast` and the `composition`/`stub_modules` fixtures by grep | G7 deletion |
| K-G7b | `test_translator_comments.py` | `CHANGED_LABEL_MSGIDS` with its comment (`:42-65`), `DEAD_MSGIDS` with its comment (`:66-94`), `_gettext_calls` (`:98-120`) | only D10 uses them (`:124`, `:127`, `:150-151`); `ZH_TW_CATALOG` (`:95`) and `_catalog` (`:131-145`) are reused by X1/X2; `re` stays (`:9-12`) | translator delete commit |
| K-G8a | `test_engine_discovery.py` | `test_load_engine_class_gives_none_for_each_failure` entirely (`:378-403`: two rows removed, two merged by G8-M1) and `_divide_by_zero` (`:374-375`) | `_divide_by_zero` used only by that function | G8-M1 |
| K-G8b | `test_core_install.py` | `import types` (`:10`), `load_definitions` from `:15` (`ADDON` stays: `:19`), `PLUGIN` (`:20`); docstring `:5-6` "The last two tests load the real files instead" → "The last test loads the real files instead" | used only by `test_menu_import_reports_a_corrupt_archive` (`:184-225`, `:223`) | G8-M3 |
| K-G8c | `test_global_plugin_lifecycle.py` | the whole file (`load_plugin_class` `:10-11`, `plugin_environment` `:14-42`) | G8-M4 | G8-M4 |

Not done, against the audit's 連帶可刪 G4 line "`shape()` 的 `else: result.append(item)` 分支隨之用不到" (`test_pipeline_number_groups.py:206-207`): without that branch `shape()` would drop an unexpected item silently, so a later test could pass with a stray command in the output. *Decided by orchestrator with the recommended default; user may override before merge.*

After the deletions, the implementer re-runs an orphan scan (module-level names of each touched test file that had a user at `f1bbec0` and have none now; repeat until nothing new) and `ruff` (F401); anything found beyond this table is deleted in the commit that orphaned it and recorded in the progress ledger.

## 6. Merges

Rules for every row:
- Every path and every assertion of the replaced tests is kept; where the audit's shape would weaken one (noted in the row), the row says how it is kept.
- Kept ids that a row edits do not change, unless the row says so; the new ids are those of the named function and parametrize. The implementer records each row's `- old` and `+ new` ids in the progress ledger (§9.1).
- **Run before committing** (the audit did not run these shapes): G1-M6 (the `[index-only]` case), G2-M6, G2-M7, G4-M3, and the two assertions G3-M1 adds (N4). For every other row the merged test is run green before the source tests are deleted too.
- Comments that record a user decision, a review finding or a bug reference move with their assertion.

### 6.1 G1 (35 ids → 20, net −15)

| Row | Replaces | Into | Target shape | New ids |
|---|---|---|---|---|
| G1-M1 | `test_engine_segment_contract.py::test_completed_segment_drains_once_on_the_delivery_thread[*]` (6, `:98-113`) | `::test_speak_segment_returns_before_delivery[*]` (`:146-165`) | Append `assert event.source_id is context.source_id`, `assert events.on_delivery_thread == [True]`, `assert events.threads[0] != caller.ident`; replace the `C3Blocking` raise (`:163-165`) by `assert returned_early`, placed last as now (K-G1a). | 0 (target ids unchanged) |
| G1-M2 | `test_espeak_segment_drain.py::test_speak_after_terminate_fails_through_lifecycle_delivery` (`:474-504`); `test_onecore_segment_drain.py::test_onecore_rejected_segment_uses_async_lifecycle_delivery[True]` (`:687-722`) | `test_engine_segment_contract.py::test_segment_after_terminate_fails_once_without_native_call[*]` (`:116-130`) | Add `assert events.on_delivery_thread == [True]`, `assert events.threads[0] != caller.ident`, and the exact error text per engine: `str(event.error) == f"{name} driver has terminated"` with `name` the engine's display name (`"eSpeak"` for Espeak, as `test_espeak_segment_drain.py:501` asserts; the others as `addon/synthDrivers/WorldVoice/runtime/segmentHost.py:234` and the wrappers raise, e.g. `driver/VE/__init__.py:455`). `Events.wait_one` (`:65-73`) already fails on a duplicate event (the source's `quiet_period()` + `len(events) == 1`). The repeated terminate of the eSpeak test (`:476`) is the contract fixture's `adapter.close()` after `engine.terminate()` (`tests/engine_contract_harness.py`, `close` methods); confirm by reading each adapter's `close`, else add `engine.terminate()` twice at the start of the contract test. The OneCore `[False]` case stays: drop the parametrize, inline `terminated=False` (`:689-701` keep only the else branch; `:722` becomes `== 1`). | 0; rename `…lifecycle_delivery[False]` → `…lifecycle_delivery` |
| G1-M3 | `test_espeak_segment_drain.py::test_failed_native_synthesis_does_not_reach_audio_fed[native\|native_result]` (`:83-107`) | `::test_observable_callback_or_native_failure_fails_exact_context_after_return[*]` (`:52-80`) | Record `host.reach` as `:88-94` does; for `failure in ("native", "native_result")` assert `env.outer.AUDIO_FED not in reached`; for `native_result` also `str(event.error) == "eSpeak synthesis failed with code -1"`, for `native` `isinstance(event.error, OSError)` (`:104-107`). Move the AUDIO_FED comment (`:85-86`). | 0 |
| G1-M4 | `test_vocalizer_segment_drain.py::test_foreign_instance_endprocess_does_not_touch_current_buffer[VE\|Cerence]` (`:1075-1093`) | `::test_refused_endprocess_does_not_reach_engine_done[*]` (`:2088-2104`) | Take `buffered_audio(callback_handler(env.core))` and `real_player(env.core).fed` before and after the foreign ENDPROCESS inside `native`; assert both unchanged, plus every other assertion of the source. | 0 |
| G1-M5 | `test_onecore_segment_drain.py::test_onecore_successor_player_open_waits_for_old_feed_and_stop` (`:213-249`) | `::test_onecore_shared_handoff_waits_for_callback_feed_and_stop` (`:115-150`) | Record `env.player.open` calls; before the stop is released assert `opened == []` and `stays_false(…, lambda: bool(opened))`; after, `opened == [True]` (the source's exact checks). | 0 |
| G1-M6 | `test_onecore_segment_drain.py::test_segment_drain_idles_the_real_player` (`:606-615`) | `::test_empty_index_and_break_segments_drain_at_known_end[break-only]` (`:881-903`) | Append `assert env.player.idles == 1` with the C4 comment (phase 54, `3a982bc`). **Run** `[index-only]` with it: if it holds, assert it for both rows; if not, only for `break-only`. | 0 |
| G1-M7 | `test_sapi5_segment_drain.py::test_sapi5_wasapi_shared_lifecycle_waits_for_endstream_pcm_and_idle` (`:58-79`) | `::test_admitted_pcm_feed_retires_before_final_tail_and_idle[False]` (`:668-713`) | For `feed_fails is False` add `event.segment_id == 17` and `env.player.fed == [6, 0]`, and every other assertion of the source not already in the target. | 0 |
| G1-M8 | `test_vocalizer_segment_drain.py::test_segment_whose_every_call_ends_reaches_engine_done`, `::test_last_call_without_endprocess_fails_the_segment`, `::test_only_the_last_call_needs_endprocess` (`[VE\|Cerence]` each, `:2068-2085`) | new `test_engine_done_needs_the_last_native_call_to_end` | `@pytest.mark.parametrize(("pieces", "ends", "drained"), [(["a", "b", "c"], [True, True, True], True), (["a", "b"], [True, False], False), (["a", "b", "c"], [True, False, True], True)], ids=["every-call-ends", "last-call-unended", "middle-call-unended"])` over `speak_pieces` (`:2051-2065`); assert `calls == pieces`, the event kind, and for `drained is False` `"engine_done" in str(env.events[0].error)`. Keep the middle-call comment (`:2082`). | 6 (`[VE\|Cerence-every-call-ends\|…]`) |
| G1-M9 | `test_vocalizer_segment_drain.py::test_a_long_segment_is_one_native_call`, `::test_break_repeated_runs_still_runs`, `::test_empty_wrapper_text_makes_no_native_call` (`[VE\|Cerence]` each, `:2133-2160`) | new `test_a_segment_is_at_most_one_native_call` | `@pytest.mark.parametrize(("text", "transform", "expected"), [(LONG, None, [LONG]), ("hello", str.upper, ["HELLO"]), ("hello", lambda text: "", [])], ids=["long", "transformed", "emptied"])` with `LONG = " ".join(["word"] * 60)` and `assert len(LONG) == 299` kept (`:2135`); patch `env.module.break_repeated_runs` when `transform` is set; assert `calls == expected` and the single `SEGMENT_DRAINED` (new for `transformed`, it holds: the segment completes). Keep the U5 comment (`:2118-2119`). The `emptied` case keeps the VE `544->-537` / Cerence `549->-542` arcs (N3). | 6 |
| G1-M10 | `test_vocalizer_segment_drain.py::test_segment_without_native_call_reaches_engine_done[VE\|Cerence]` (`:2107-2115`) | `::test_zero_audio_segments_still_wait_for_real_idle` (`:1249-1267`, `kind` in `["empty", "index"]`) | Add `"blank"` (sequence `("   ",)`) to `kind`; for `empty` and `blank` record native calls and assert `calls == []`; move the veinner comment (`:2108`). | 2 (`[VE-blank]`, `[Cerence-blank]`) |
| G1-M11 | `test_onecore_segment_drain.py::test_sync_failure_fails_only_its_segment` (`:581-603`), `::test_idle_failure_fails_only_its_segment` (`:618-638`) | new `test_a_player_failure_fails_only_its_segment` | `@pytest.mark.parametrize("fault", ["sync", "idle"])`; `env.player.error = fault`; the `respond()` markers per fault as in the sources; `f"{fault} failed"`. | 2 |
| G1-M12 | `test_onecore_segment_drain.py::test_cancelled_legacy_feed_retires_only_after_its_final_stop` (`:1217-1254`), `::test_cancelled_segment_feed_is_stopped_by_the_lease_before_successor` (`:1658-1689`) | new `test_a_cancelled_late_feed_is_stopped_before_its_successor` | `@pytest.mark.parametrize("mode", ["segment", "legacy_after_segment"])` with `start_controlled_playback(env, mode)` (`:1057-1074`), `base = 2 if legacy else 1` native calls, `env.dones == []` for legacy, `call.thread in stop_threads` for both. The `segment` case keeps `OneCore 491->492->-461` (N3). | 2 |
| G1-M13 | `test_sapi5_segment_drain.py::test_end_stream_waits_for_actual_idle_and_preserves_tail_indexes` (`:109-123`), `::test_empty_audio_still_requires_idle` (`:158-166`) | new `test_end_stream_waits_for_actual_idle` | `@pytest.mark.parametrize(("commands", "tail", "indexes", "fed"), [(None, None, [7], [6]), (("",), [], [], [])], ids=["speech", "empty"])`, both bodies' assertions per case. Line `:123` goes (T10). | 2 |

### 6.2 G2 (19 ids → 14, net −5)

| Row | Replaces | Into | Target shape | New ids |
|---|---|---|---|---|
| G2-M1 | `test_rhvoice_segment_drain.py::test_terminal_sink_can_terminate_outside_native_and_worker_stacks` (`:106-120`), `::test_rhvoice_shared_sink_reenters_terminate` (`:538-555`) | new `test_terminal_sink_can_terminate_from_the_delivery_thread` at `:106` | One scenario (`{"auto_return": True}`, `speak(env, sink=sink)`, wait for delivery); the sink records `current_thread()` and calls `env.driver.terminate()` in `try/except` recording errors; assert `threads[0] is not call.thread`, `threads[0] is not tts_thread(env.driver)`, `call.returned.is_set()`, `errors == []`, `env.native.engine_deleted`. Audit ran it green. | 1 |
| G2-M2 | `test_worldvoice_cancel_wrappers.py::test_speech_and_cancel_remain_usable[VE\|Cerence]` (`:280-293`) | `::test_guarded_speech_never_touches_inner_stop_flag[*]` (`:582-607`) | After its `real_player(core).fed == [b"first", b"second"]` add `stops == 1` and `idles == 2`. Audit ran it green. | 0 |
| G2-M3 | `test_runtime_drain_integration.py::test_switch_waits_for_original_correlated_drain[VE-Cerence]` (`:124-156`) | `::test_next_engine_starts_only_after_segment_drain[engines0]` (`:60-93`) | After the first `barrier = first.tail()`: `context = first.contexts[0]`, `c.output.drains == []`, `not request.tasks[0].future.done()`; after `second.wait_call()`: one drain with that `source_id`/`segment_id`/`SEGMENT_DRAINED`, and `second.contexts[0]`'s source and segment differ from the first. The `[engines0]` parametrize stays (the audit's optional constant would rename the id; not done). Audit ran it green. | 0 |
| G2-M4 | `test_segment_host.py::test_faulted_reports_a_control_error_or_lifecycle_fault_until_reset` (`:656-678`) | `::test_reset_recovers_from_a_control_error` (`:609-618`), `::test_reset_recovers_from_a_lifecycle_fault` (`:635-653`) | Control-error test: `faulted is False` at the start, `True` after the latch, `False` after reset. Lifecycle test: after the failed segment `control_error is None and faulted is True`; after reset `faulted is False`. Extract `break_boundary_hook` (K-G2b). Audit ran it green. | 0 |
| G2-M5 | `test_segment_host.py::test_control_error_fails_an_unpublished_drain` (`:963-978`), `::test_control_error_relabels_a_drain_the_lifecycle_already_committed` (`:981-1001`) | `test_control_error_fails_an_unpublished_drain` | `@pytest.mark.parametrize("lifecycle_fail", ["lands", "lost"])`; `"lost"` patches `env.host._lifecycle.fail` to a no-op (`:984`, with its comment `:982-983`); both assert `SEGMENT_FAILED` and `str(event.error) == "stop failed"` (new for `lands`; the audit ran it). | 2 |
| G2-M6 | `test_segment_host.py::test_ordinary_speech_raises_after_a_control_error` (`:415-420`), `::test_terminated_host_rejects_new_ordinary_speech` (`:1140-1144`), `::test_ordinary_submit_error_is_raised` (`:751-754`) | new `test_ordinary_enqueue_raises_without_submitting` | `@pytest.mark.parametrize(("cause", "error", "match"), [("control_error", OSError, "stop failed"), ("terminated", RuntimeError, "Fake driver has terminated"), ("submit_error", RuntimeError, "queue rejected")])`; one set-up line per cause; `pytest.raises(error, match=match)` around `env.host.enqueue(…)`; `env.strategy.submitted == []` (new for `submit_error`). **Run.** | 3 |
| G2-M7 | `test_playback_work.py::test_direct_cancel_notifies_owner_after_releasing_the_work_lock` (`:166-179`), `::test_terminal_event_notifies_owner_after_releasing_the_work_lock[fail\|complete_drained]` (`:182-197`) | new `test_owner_is_notified_after_releasing_the_work_lock` | `@pytest.mark.parametrize(("finish", "published"), [("cancel", 0), ("fail", 1), ("complete_drained", 1)])`; `action` per `finish`; `len(events) == published` (the source's `events == []` for cancel). **Run.** | 3 |
| G2-M8a | `test_runtime_segment_completion.py::test_end_waits_for_speak_return` (`:112-130`), `::test_drain_waits_for_speak_return_and_rejects_late_index` (`:179-200`) | new `test_completion_waits_for_speak_return_and_rejects_late_index` | `MODES = [("END_INDEX", "SEGMENT_END"), ("DRAIN", "SEGMENT_DRAINED")]`; `@pytest.mark.parametrize(("mode", "kind"), MODES)`; the DRAIN body. Audit ran both modes. | 2 |
| G2-M8b | `::test_duplicate_end_cannot_advance_next_task` (`:81-91`), `::test_duplicate_drain_cannot_advance_next_segment` (`:157-176`) | new `test_duplicate_completion_cannot_advance_next_segment` | Same table; the DRAIN body (`INDEX, old, old, INDEX`; `output.indexes == [123]`). Audit ran both modes. | 2 |
| G2-M8c | `::test_end_then_speak_error_is_failure` (`:94-109`) | `::test_drain_does_not_override_failure_or_cancellation` (`:203-230`) | Parametrize over `("mode", "outcome")` with `pytest.param("DRAIN", "speak_error", id="speak_error")`, `…"segment_failure"…`, `…"cancel"…` (kept ids unchanged) and `pytest.param("END_INDEX", "speak_error", id="END_INDEX-speak_error")`; `marker(rt, mode)` instead of the literal `"DRAIN"` (`:205`). The minimal form of the audit; the full 2 × 3 is not done. | 1 |

### 6.3 G3 (17 ids → 0, net −17)

| Row | Replaces | Into | Target shape |
|---|---|---|---|
| G3-M1 | `test_runtime_legacy_adapter.py::test_another_voice_is_set` (`:217-222`), `::test_after_a_failed_apply_the_same_voice_is_set_again[voice\|rate\|hook]` (`:236-246`), `::test_a_core_not_reporting_the_voice_gets_it_set[raise\|lie]` (`:249-257`), `::test_reopening_sets_the_voice_even_on_the_same_core_object` (`:260-269`), `::test_a_core_that_needs_a_voice_reload_gets_the_voice_set[True-True\|raise-True\|False-False]` (`:303-312`) (10) | `::test_property_the_voice_is_set_unless_the_same_healthy_core_already_took_it` (`:324-357`) | Ten `@example(actions=[…])`, one per replaced id, each the replaced test's action sequence in the property's tuple form (`APPLY`, `:315-321`): another voice `[("apply","a",None,"true",None), ("apply","b",…), ("apply","a",…)]`; failed apply `[("apply","a",step,"true",None), ("apply","a",None,"true",None)]` for each step; getter `[("apply","a",None,"true",None), ("apply","a",None,getter,None)]`; reopen `[("apply","a",None,"true",None), ("reopen",), ("apply","a",None,"true",None)]`; reload `[("apply","a",None,"true",None), ("apply","a",None,"true",reload)]` for `True`, `"raise"`, `False`. Add to the property (N4): in the `reopen` branch `assert adapter.core is core`; after each apply `assert core.__dict__["voice"] == voice` (the stored value: the getter may raise or lie). **Run** the property with the examples; if the second assertion fails in a case none of the replaced tests covers, restrict it to failed applies that wrote the voice (`failed and expect_voice`) and record a `Ruling:`. Not merged (audit G3): `test_reapplying_the_same_voice_skips_only_the_voice_setter`, `test_another_voice_is_set_even_when_the_core_already_reports_it`, `test_a_failed_close_still_forgets_the_voice`. |
| G3-M2 | `test_runtime_completion_policies.py::test_actual_outer_voice_and_core_select_enabled_drain_profiles[SAPI5-audio_modes0\|Espeak-audio_modes1\|RHVoice-audio_modes2]` (`:348-404`) | `::test_six_enabled_profiles_use_shared_lifecycle[*]` (`:466-493`) | Keep `@pytest.mark.parametrize("engine", SIX_ENGINES)` (ids unchanged) and add a module table `AUDIO_MODES = {"OneCore": (("wasapi", True),), "VE": (("default", True),), "Cerence": (("default", True),), "SAPI5": (("wasapi", True), ("legacy", False), ("unknown", False)), "Espeak": (("default", True), ("legacy", True), ("unknown", True)), "RHVoice": (("default", True), ("wasapi", True), ("unknown", True))}` (the source's rows `:351-353` verbatim; the other three are the mode `load_installed_engine` opens, `:441`). After the existing assertions, per audio mode: `support.supported is expected and support.reason`, `contract.mode` DRAIN or LEGACY_DONE; then `real_completion_selector(policies, warnings)(outer.Voice, core)` selects DRAIN with an `index_range`, and `warnings == []` for RHVoice. Both tests open the engine through the same loaders (`load_installed_engine`, `:431-460`; the source `:362-371`). |
| G3-M3 | `::test_disabled_force_switch_keeps_structural_fallback_reason` (`:547-562`) | `::test_sapi5_legacy_first_segment_remains_legacy_done` (`:407-425`) | `for force in (True, False)`: `CompletionPolicy(forceUnverifiedDrain=force).drainSupport(…, audioMode="legacy")` gives `supported is False` and the exact reason `"SAPI5 legacy audio has no owned player idle barrier"`; the rest unchanged. |
| G3-M4 | `test_f4_engine_adapters.py::test_voice_metadata_names_the_declaring_engine[VE\|Cerence]` (`:121-134`) | `::test_voice_metadata_keeps_vocalizer_quirks[*]` (`:137-149`) | `monkeypatch.setattr(voice_class, "engine", "Renamed")` at the start; assert `metadata["engine"] == "Renamed"`, `metadata["name"] == "Renamed:x"`, `metadata["description"] == "x - English [Renamed]"`, plus any other assertion of the source. |
| G3-M5 | `test_runtime_session.py::test_drain_session_passes_original_context_commands_and_token` (`:287-298`) | `::test_cached_activation_still_speaks_two_distinct_segments` (`:221-229`) | Keep the first commands and context in variables; assert `adapter.contexts[0] is first_context`, `adapter.spoken[0][0] is commands`, `adapter.spoken[0][1] is token`. |

### 6.4 G4 (18 ids → 13, net −5)

| Row | Replaces | Into | Target shape | New ids |
|---|---|---|---|---|
| G4-M1 | the six `split_once` properties of `test_pipeline_pause_properties.py` (`:572-641`) | new `test_property_the_number_split` | One `@SHARED_ENV @given(text=NUMBER_TEXT)` test calling `split_once(env, text)` once and making all six groups of assertions, each under a one-line comment naming its property; the user-decision comment (`:582`) and the leftover-text comment (`:633-634`) move along. The leftover-text group's early `return` (`:636-637`) becomes an `if` around that group, last, so it cannot skip the others. | 1 |
| G4-M2 | `::test_property_group_size_convert_keeps_or_resets` (`:685-693`), `::test_property_segment_length_convert_keeps_or_resets` (`:696-703`) | new `test_property_a_size_convert_keeps_or_resets` | `@pytest.mark.parametrize("key", ["group_size", "segment_length"])` + `@SHARED_ENV @given(value=st.integers())`; same body; the two decision comments (`:688-689`, `:699`) as one block. | 2 (`[group_size]`, `[segment_length]`) |
| G4-M3 | `test_pipeline_filters.py::test_an_unnamed_symbol_is_left_to_the_punctuation_stage[*]` (8, `:659-689`), `::test_an_unnamed_symbol_in_number_mode_is_left_to_the_punctuation_stage[pause\|remove]` (`:692-719`) | `test_an_unnamed_symbol_is_left_to_the_punctuation_stage` | One table `("mode", "size", "roles", "remove", "expected")`: the eight value/none rows (size 3) and the two number rows (size 0); settings for every row: `punctuation_pause_enabled`, `scaled_number_wait = 10`, `scaled_punctuation_wait = 50`, `punctuation_pause_characters = "."`. **Run**: the eight rows' expectations hold with the punctuation wait at 50 (audit G4: they contain no punctuation pause); if one does not, keep that row's own waits as a column. Keep both comments (`:674-676`, `:706-707`). | 10 |

### 6.5 G5 (10 ids → 9, net −1)

| Row | Replaces | Into | Target shape | New ids |
|---|---|---|---|---|
| G5-M1 | `test_pipeline_stages.py::test_number_mode_switch_logs_both_number_mode_stages` (`:46-59`), `::test_the_number_language_switch_logs_the_number_stage[language-only]` (`:99-118`; `[both]` is removed) | new `test_a_number_switch_logs_its_number_stages` | `@pytest.mark.parametrize(("on", "pairs"), [(("numberMode",), 2), (("numberLanguage",), 1)], ids=["mode", "language"])`; the body of `:104-118`. | 2 |
| G5-M2 | `::test_number_language_and_number_wait_pause_between_numbers` (`:225-244`), `::test_number_language_pauses_at_a_no_break_space[\xa0]` (`:264-286`) | `test_number_language_and_number_wait_pause_between_numbers` | `@pytest.mark.parametrize(("text", "numbers"), [("1 2", ("1", "2")), ("10\xa0000", ("10", "000"))], ids=["space", "no-break-space"])`; expected `["en", a, "zh", ("NB", 10), "en", b, "zh"]`; keep the 2026-10-22 decision comment. | 2 |
| G5-M3 | `test_pipeline_settings_service.py::test_group_size_confspec_is_its_range` (`:105-117`), `::test_segment_length_confspec_is_its_range` (`:120-127`) | new `test_a_size_confspec_is_its_range` | `@pytest.mark.parametrize(("key", "stored"), [("group_size", "groupSize"), ("segment_length", "segmentLength")], ids=["group_size", "segment_length"])`; `(min, max, default, reset_out_of_range) == (0, 2**31 - 1, 0, True)` and the confspec string per key; the key list of `reset_out_of_range` and the `segmentWaitFactor` confspec asserted once (in the `group_size` case or a plain line outside the per-key part, as the sources have them). Drop `not hasattr(spec, "stored_min_value")` (existence line, part of the audit's shape). | 2 |
| G5-M4 | `test_worldvoice_pipeline_settings.py::test_an_unknown_number_mode_is_stored_and_read_as_value` (`:127-133`), `::test_synth_nummod_group_stores_value` (`:136-144`) | new `test_an_old_or_unknown_number_mode_is_stored_and_read_as_value` | `@pytest.mark.parametrize("written", ["pair", "group"])`; conf starts at `numberMode: "group"`; read before writing is `value`, write, stored `value`, read `value`; keep the U7 comment. | 2 |
| G5-M5 | `test_pipeline_panels.py::test_dialog_msgids_come_from_the_dialog_and_every_panel` (`:193-204`) | `::test_log_labels_come_from_the_table` (`:207-221`) | Before its `dialog_msgids() & strings == set()` add `assert titles <= dialog_msgids()` with the seven titles of the source, so the disjointness check cannot pass on an empty set. | 1 (the target's own id) |

### 6.6 G6 (13 ids → 2, net −11)

| Row | Replaces | Into | Target shape | New ids |
|---|---|---|---|---|
| G6-M1 | `test_role_panel_ui.py::test_panel_for_another_synth_only_says_so` (`:101-115`), `test_settings_panels.py::test_unicode_panel_for_another_synth_only_says_so` (`:775-782`) | `test_settings_panels.py::test_panels_for_another_synth_show_the_same_read_only_notice[SpeechRoleSettingsPanel\|UnicodeDetectionSettingsPanel]` (`:785-796`) | Keep `@pytest.mark.parametrize("name", …)` (ids unchanged) and add `AFTER = {"SpeechRoleSettingsPanel": ("postInit", "onDiscard", "onSave"), "UnicodeDetectionSettingsPanel": ("onSave",)}`; after `build(env, name)` call each method of `AFTER[name]` in order; add `panel.disable is True` and `env.shown == []`. Keep the "saving must not reach it" comment (`:782`). Keeps the role.py and detection.py arcs (N3). | 0 |
| G6-M2 | `test_settings_panels.py::test_number_modes_match_the_driver_and_the_panel` (`:109-131`) | `test_settings_table_guard.py::test_driver_choices_match_the_driver_options` (`:460-478`) | Add `list(module.NUMBER_MODES) == [value for value, _ in spec.choices] == ["none", "value", "number"]` (U1: the ring does not list `group`). The panel labels are asserted by `test_pipeline_panel_group_size_stays_enabled_after_every_mode_choice` (`choice.choices == ["off", "value", "number"]`); if the source asserts anything that test does not, move it too. | 0 |
| G6-M3 | `test_settings_panels.py::test_log_panel_shows_an_invalid_switch_unticked` (`:558-567`) | `::test_log_panel_save_fixes_an_invalid_switch` (`:570-581`) | Before `panel.onSave()` add the source's two checkbox assertions (numberMode unticked, speechViewer ticked). | 0 |
| G6-M4 | `::test_pipeline_panel_keeps_the_stored_mode_when_nothing_is_selected[none\|number]` (`:159-171`), `::test_pipeline_panel_keeps_the_stored_scope_when_nothing_is_selected[all\|WorldVoice]` (`:174-185`) | new `test_pipeline_panel_keeps_the_stored_choice_when_nothing_is_selected` | `@pytest.mark.parametrize(("attribute", "stored_key", "stored"), [("_number_mode_choice", "numberMode", "number"), ("_scope_choice", "scope", "WorldVoice")], ids=["mode", "scope"])`: one non-default stored value per control (audit G6: the second value takes no other branch). | 2 |
| G6-M5 | `test_settings_order.py::test_voice_panel_rows_are_spaced_like_nvdas_driver_rows[*]` (4, `:270-280`) | `::test_voice_panel_orders_follow_the_table[*]` (`:254-267`) | Add `spacing == dict.fromkeys(VOICE_KEYS, (10, env.wx.BOTTOM))` with its comment (NVDA's 10 px bottom border, `tests/test_settings_order.py:275`); same `build_then` (`:236-251`) and scenarios. | 0 |
| G6-M6 | `test_settings_panel_save.py::test_failed_save_changes_no_settings_and_logs` (`:106-123`) | `::test_engine_change_does_not_restart_after_failed_flag_write` (`:93-103`) | Add `args == ("WorldVoice: failed to save %s settings", "engine")` and `kwargs == {"exc_info": True}` for the log record, and any other assertion of the source the target lacks. | 0 |

### 6.7 G7 (12 ids → 12, net 0)

| Row | Replaces | Into | Target shape | New ids |
|---|---|---|---|---|
| G7-M1 | `test_generate_unspaced_common.py::test_downloaded_source_must_match_its_checksum` (`:372-376`), `::test_downloaded_unicode_data_must_match_its_checksum` (`:379-383`) | new `test_a_downloaded_file_must_match_its_checksum` | `@pytest.mark.parametrize(("keyword", "name", "digest"), [("sha256", "ScriptExtensions.txt", SOURCE_SHA256), ("unicode_data_sha256", "UnicodeData.txt", UNICODE_DATA_SHA256)], ids=["ScriptExtensions.txt", "UnicodeData.txt"])`; `_run(…, **{keyword: "0" * 64})`; message `f"{name} checksum mismatch: actual {digest}"`; `not destination.exists()`. | 2 |
| G7-M2 | `test_nvda_ready.py::test_ready_skips_with_one_warning_when_a_module_name_is_missing[Espeak\|OneCore]` (`:102-112`), `::test_ready_skips_when_a_class_name_is_missing[Espeak\|OneCore]` (`:115-123`) | new `test_ready_skips_with_one_warning_when_a_name_is_missing` | `@pytest.mark.parametrize("kind", ["module", "class"])` on the `skipped_engine` fixture (`:78-82`); per kind the deleted attribute (`engine.module`/`engine.module_name` or `engine.host_class`/`engine.class_name`), the version (`"2025.1.0"` or `"2026.3.0"`, kept per kind) and the owner prefix; assert `result is False` and the full `records == [("warning", message)]` (the class case had only `endswith`). A helper shared with G7-M3 may remove the name and return its full dotted name. | 4 |
| G7-M3 | `::test_sapi5_uses_nvdas_driver_with_one_info_line_when_a_module_name_is_missing` (`:150-158`), `::test_sapi5_uses_nvdas_driver_when_a_class_name_is_missing` (`:161-168`) | new `test_sapi5_uses_nvdas_driver_with_one_info_line_when_a_name_is_missing` | Same `kind` table with the sources' versions (`"2025.1.0"`, `"2025.2.0"`) and missing names; `result is True`, `assert_sapi5_uses_nvdas_driver(sapi5)`, the exact info record. | 2 |
| G7-M4 | `test_generated_unicode_data.py::test_script_data_is_the_generators_output` (`:76-77`), `::test_unspaced_common_data_is_the_generators_output` (`:80-83`), `::test_other_line_endings_in_script_data_are_caught` (`:129-132`), `::test_other_line_endings_in_unspaced_common_data_are_caught` (`:135-138`) | `test_generated_file_is_the_generators_output`, `test_other_line_endings_in_a_generated_file_are_caught` | `GENERATED = [("scripts_tool", _rerender_script_data, SCRIPT_DATA), ("unspaced_tool", _rerender_unspaced_common_data, UNSPACED_COMMON_DATA)]` with `ids=["script_data", "unspaced_common_data"]`; the tool fixture through `request.getfixturevalue`. The byte-exact guard of the protected Unicode data files must keep its strength (DEVELOPMENT_WORKFLOW.md §7). | 4 |

### 6.8 G8 (8 ids → 2, net −6)

| Row | Replaces | Into | Target shape | New ids |
|---|---|---|---|---|
| G8-M1 | `test_engine_discovery.py::test_load_engine_class_gives_none_for_each_failure[no-voice\|raises]` (`:378-403`) | `::test_failures_are_logged_and_timed` (`:69-90`) | Replace the two `in log.lines` checks (`:86-87`) by `[entry for entry in log.lines if entry[0] != "debug"] == [("warning", "Skipping Missing engine candidate: Voice export missing"), ("error", "Failed to load ready state for Broken: boom")]`; plus any assertion of the source rows not implied (each row asserts `load_engine_class` returns `None`; the target's spec list proves that through `load_enabled_engine_classes`, check it asserts the result excludes both). K-G8a. | 0 |
| G8-M2 | `test_voice_settings_repository.py::test_load_leaves_an_invalid_stored_value_in_the_config` (`:94-97`) | `::test_load_uses_the_default_for_a_stored_value_int_refuses[*]` (`:80-91`) | Append `assert conf["WorldVoice"]["voices"]["Fake:a"] == {"rate": stored, "pitch": "61", "variant": "bright"}`: the whole stored entry unchanged, as the source asserts the whole entry. | 0 |
| G8-M3 | `test_core_install.py::test_menu_import_reports_a_corrupt_archive` (`:184-225`) | `test_global_plugin_menu.py::test_failed_extraction_reports_and_logs_the_archive_name` (`:187-199`) | `fail()` raises `zipfile.BadZipFile("bad archive")` instead of `OSError` (`:192-193`): the plugin's `except Exception` takes both; the real archive raising `BadZipFile` on `b"not a zip"` is `test_core_install.py::test_install_always_removes_the_archive[True]` (`:167-181`). K-G8b; loses the fragment arcs `-1->81`, `81->-1` (N3). | 0 |
| G8-M4 | `test_global_plugin_lifecycle.py::test_secure_mode_terminate_runs_every_cleanup_step` (`:45-53`), `::test_dead_menu_runtime_error_does_not_stop_cleanup` (`:56-69`) | `test_global_plugin_menu.py` | (a) At the end of `test_secure_mode_adds_no_menu` (`:45-49`): `env.calls.clear(); env.plugin.terminate(); assert env.calls == [("unpatch",), ("detach",)]` (keeps `72->-71`). (b) New `test_a_dead_menu_runtime_error_does_not_stop_cleanup` after `test_a_menu_nvda_already_dismantled_is_still_destroyed` (`:63-71`): the `ui_harness` plugin with a menu; `env.tray.menu.Remove` raises `RuntimeError("wrapped C/C++ object deleted")`; after `terminate()` assert `env.calls[-2:] == [("unpatch",), ("detach",)]` and `item.destroyed is False` (the RuntimeError leaves `removeMenu` before `Destroy`, `addon/globalPlugins/WorldVoice/__init__.py:71-79`, and `terminate` swallows it, `:43-48`); keeps `45->46->48->50` and `75->-71`. A separate test, not a parametrize with the AttributeError test, so no kept id changes (the audit's parametrize is optional). K-G8c. | 1 |
| G8-M5 | `test_voice_catalog.py::test_empty_catalog_has_no_voices` (`:92-99`), `::test_empty_catalog_has_no_engines` (`:102-105`) | new `test_empty_catalog_is_empty` | Both bodies' assertions (six fields) in one test. | 1 |

### 6.9 Merge arithmetic

| Group | Ids replaced | New ids | Net |
|---|---|---|---|
| G1 | 35 | 20 | −15 |
| G2 | 19 | 14 | −5 |
| G3 | 17 | 0 | −17 |
| G4 | 18 | 13 | −5 |
| G5 | 10 | 9 | −1 |
| G6 | 13 | 2 | −11 |
| G7 | 12 | 12 | 0 |
| G8 | 8 | 2 | −6 |
| Total | 132 | 72 | **−60** |

Each row's own net is in its "New ids" column against its tag count in `-merge.txt`; the audit's per-group nets (audit §1.1) match. Renames that come with a merge but are not counted in it: G1-M2 (`[False]` → plain). Ids an M-row edits but does not list in `-merge.txt` keep their ids (`test_speak_segment_returns_before_delivery[*]`, `test_segment_after_terminate_fails_once_without_native_call[*]`, `test_six_enabled_profiles_use_shared_lifecycle[*]`, …).

## 7. Tidy edits from the audit's 連帶可刪 lists

The audit lists these under 連帶可刪 although no deletion of this phase causes them; they remove a dead single-row parametrize, an alias or an existence line. Kept-id renames are listed; counts do not change.

| # | Where | Edit | Id change |
|---|---|---|---|
| T1 | `test_generate_unicode_scripts.py::test_an_unreadable_source_names_the_path_and_option` (`:166-183`) | Drop the `make` parametrize (only `missing` is left since phase 57); inline it. | `[missing]` → plain |
| T2 | `test_generate_unspaced_common.py::test_an_unreadable_local_file_names_the_path_and_option` (`:469-489`) | Same. | `[--source-ScriptExtensions.txt-missing]`, `[--unicode-data-UnicodeData.txt-missing]` → without the `-missing` part (exact strings recorded) |
| T3 | `test_generate_unspaced_common.py::test_select_drops_characters_without_an_unspaced_script` (`:127-129`) | Drop the one-value `extension` parametrize. | `[extension0]` → plain |
| T4 | `test_hygiene_guards.py:70` | Delete `assert "omits the lint hook" not in config` (a "the old comment is gone" check, `42e7277`). | none |
| T5 | `test_engine_discovery.py::test_plugin_with_old_contract_names_is_reported` (`:224-250`) | Drop the one-row parametrize; write the values. | `[extra_capabilities-extraCapabilities-member0]` → plain |
| T6 | `test_engine_filter.py::test_a_role_voice_outside_the_engine_is_ignored` (`:63-65`) | Same (`role = "B:en"`). | `[B:en]` → plain |
| T7 | `test_language_detector.py::test_decimal_digits_follow_the_letter_rule_of_their_script` (`:429-440`) | After §5.2 one row is left; drop the parametrize. | `[abc-arabic-indic]` → plain |
| T8 | `test_ui_controls.py` | Delete the alias `DEPENDENTS = PAUSE_DEPENDENTS` (`:156`; users `:214`, `:250` use `PAUSE_DEPENDENTS`); drop the one-row parametrizes of `test_read_control_without_a_control_is_absent` (`:159-167`), `test_read_control_reads_a_checkbox` (`:170-175`), `test_apply_dependencies_enables_dependents_from_their_controller` (`:210-215`), inlining each value where it is used (no statement is dropped, including the `mode` that no longer changes the result). | `[number_mode-options0]`, `[True]`, `[value-False-False]` → plain |
| T9 | `test_panel_layout.py::test_to_display` (`:70-72`), `::test_from_display` (`:75-77`) | Same. | `[10-57-5]`, `[10-5-50]` → plain |
| T10 | `test_vocalizer_segment_drain.py:614`, `test_onecore_segment_drain.py:283`, `test_sapi5_segment_drain.py:123`, `test_espeak_segment_drain.py:49` | Delete the `synthDriverClass is …` existence line from each test; `test_runtime_completion_policies.py::test_six_enabled_profiles_use_shared_lifecycle[*]` asserts it for all six engines (`:473`). | none |

Not done (they are in the audit's 保留但值得一提, not 連帶可刪): the G3 and G5 one-line existence assertions in kept tests, the G2 one-row parametrizes `[2]` and `[engines0]`, the G8 table consolidation of four detector functions. *Decided by orchestrator with the recommended default; user may override before merge.*

## 8. The translator replacement (D10)

In `tests/test_translator_comments.py`:

- **Helper** `_source_msgids()` → `({msgid: [locations]}, [unsupported locations])`. Sources: the modules of `_translated_modules()` (`:157-168`, the add-on modules with a gettext call, `EXCLUDED` `:9` applied) and `buildVars.py` at the repository root (read as `test_every_translated_module_is_a_pot_source` reads it, `:186-187`). These are the files `scons pot` hands to xgettext (`buildVars.py:60-70`, `sconstruct:130-137`), minus modules without a gettext call; `test_every_translated_module_is_a_pot_source` (`:183-194`) keeps the two sets aligned. For each `ast.Call` whose `func` is an `ast.Name` in `GETTEXT_NAMES` (`:154`): when it is `_` with exactly one positional argument that is a `str` constant (implicit concatenation is already one constant), record that string with `relative:lineno`; any other form (`pgettext`, `ngettext`, `npgettext`, a non-literal or extra argument) is recorded as unsupported, because `_catalog` (`:131-145`) reads neither `msgctxt` nor plurals. None exists at `f1bbec0` (N6).
- **X1** `test_every_source_msgid_has_a_zh_tw_translation`: `unsupported == []`, and `{msgid: locations for msgid, locations in source.items() if not catalog.get(msgid)} == {}` with `catalog = _catalog(ZH_TW_CATALOG)` (`:95`).
- **X2** `test_the_zh_tw_catalog_has_no_unused_entry`: `sorted(set(catalog) - set(source)) == []`. `_catalog` leaves out the header and obsolete `#~` entries (`:132`), so those are allowed. X2 also guards X1 against an empty extraction (the catalog has 92 entries).
- Module docstring (`:1`): add that the zh_TW catalog must translate exactly the source strings.
- Then delete D10 and K-G7b.

Both new tests pass at `f1bbec0` (prototype run against the worktree: 90 + 2 source msgids, 92 catalog entries, nothing missing, nothing unused, no unsupported call). Commit order: X1 + X2 first (3646 + 2), D10 + K-G7b in the next commit (back to 3646). The red check for each: in a scratch copy only, blank one zh_TW `msgstr` (X1 must fail naming its msgid and location) and add an unused entry (X2 must fail naming it); record the result in the ledger.

## 9. Verification

Run everything in the worktree. At most 3 pytest processes at a time (no xdist is installed; separate processes, e.g. the per-file runs), each under a memory watchdog that kills only its own pytest when MemAvailable drops below 3 GB (start pytest in the background, keep its PID, poll `/proc/meminfo`, `kill <PID>`; never `pkill -f pytest`, other sessions run pytest here). Never `ulimit -v`.

### 9.1 Collection proof

Reuse phase 57's `collect_params.py` plugin and its JSONL format (`docs/superpowers/specs/2026-10-31-phase57-test-clean2-design.md:254-275`). Baseline: collect at the spec commit (its `tests/` equals `f1bbec0`'s); 3998 lines.

The proof script takes `BASE.jsonl HEAD.jsonl REMOVED.txt MERGES.txt RENAMES.txt` and exits 0 only if:

1. Every id of `REMOVED` and every `- old` of `MERGES` is a base id; the two sets are disjoint; head ids are unique.
2. Every `+ new` of `MERGES` is a head id and not a base id outside the row's own `- old` ids (a merged test may keep one of its old ids, e.g. G5-M5, G4-M3 when the function name and id coincide).
3. **Multiset of (function, parameters)** for the rest: base minus `REMOVED` minus the merges' `- old`, with each `RENAMES` id mapped to its new function (and to empty parameters when the new id has no `[...]`), equals head minus the merges' `+ new`.
4. **Ids:** every head id outside the merges' `+ new` and outside `{RENAMES.get(id, id)}` pairs one-to-one with an expected id missing from the head with the same function and parameters (an index renumbering, N5); the script prints each pair. Any unpaired id fails.
5. Per M-row: `len(+ new) − len(- old)` equals the row's net in §6.

`MERGES.txt` is the progress ledger's list of `- old`/`+ new` lines tagged by row (its `- old` lines are exactly `2026-11-10-phase59-test-clean3-merge.txt`). `RENAMES.txt` holds the two N5 renumberings only if the script's pairing is not used for them, plus G1-M2's rename and T1–T9's renames (`old -> new`).

Per commit: run the proof with `BASE` = the previous commit's collection and that commit's subset of the lists. At the end of the branch: `BASE` = the baseline and the full lists; the renumbering pairs must be exactly the two of N5.

### 9.2 Test count

`python3 -m pytest -q tests`: **3646 passed, 0 skipped**. Expected after each stage of §10:

| After | Collected |
|---|---|
| G1 … G8 deletion commits (292 ids; D10 is later) | 3987, 3987, 3971, 3807, 3770, 3742, 3737, **3706** |
| G1 … G8 merge commits (−15, −5, −17, −5, −1, −11, 0, −6) | 3691, 3686, 3669, 3664, 3663, 3652, 3652, **3646** |
| Tidy commits T1–T10 | 3646 |
| X1 + X2 | 3648 |
| D10 + K-G7b | **3646** |

Also run each test file this phase touches on its own (`python3 -m pytest -q tests/<file>`, at most 3 at a time), so a kept test that only passed because a deleted test ran before it shows up. Repeat the concurrency files 5 times each after the last commit: `tests/test_segment_host.py`, `tests/test_rhvoice_segment_drain.py`, `tests/test_onecore_segment_drain.py`, `tests/test_sapi5_segment_drain.py`, `tests/test_vocalizer_segment_drain.py`, `tests/test_espeak_segment_drain.py`, `tests/test_engine_segment_contract.py`, `tests/test_runtime_segment_completion.py`, `tests/test_runtime_drain_integration.py`, `tests/test_worldvoice_cancel_wrappers.py`, `tests/test_playback_work.py`; all pass every time.

### 9.3 Coverage gate: no arc lost

Full run with branch coverage (the `pyproject.toml` `[tool.coverage.*]` settings, `:13-27`: ctrace, `source = ["addon"]`, vendored code omitted):

```bash
COVERAGE_FILE=$SP/p59-after.db python3 -m pytest tests -q -p no:cacheprovider --cov=addon --cov-branch --cov-report=term > $SP/p59-coverage.txt
python3 $SP/arc_gate.py <audit scratchpad>/cov-before.db $SP/p59-after.db
```

`cov-before.db` is the audit's per-test-context run at `f1bbec0` (`/tmp/claude-0/-workspace-WorldVoice/9e65e0e5-7706-45c2-8166-5a831b64aee2/scratchpad/cov-before.db`); if it is gone, rebuild it at the spec commit with the same command and `--cov-context=test`.

```python
"""arc_gate.py BEFORE.db AFTER.db: exact per-module arc-set comparison of two coverage.py data files."""
import sqlite3
import sys

# Fragment entry/exit arcs of load_definitions compiles (spec N3); lost by design.
ALLOWED_LOST = {
	("globalPlugins/WorldVoice/__init__.py", -1, 28),
	("globalPlugins/WorldVoice/__init__.py", -1, 81),
	("globalPlugins/WorldVoice/__init__.py", 81, -1),
}
# Timing-dependent arcs (audit §1, phase 58): they may appear or vanish run to run.
TIMING = {
	("synthDrivers/WorldVoice/runtime/_segmentLifecycle.py", 165, 166),
	("synthDrivers/WorldVoice/runtime/_segmentLifecycle.py", 166, -164),
	("synthDrivers/WorldVoice/runtime/scheduler.py", 392, 393),
	("synthDrivers/WorldVoice/runtime/scheduler.py", 393, -391),
}


def arcs(path):
	con = sqlite3.connect(path)
	assert dict(con.execute("select key, value from meta")).get("has_arcs") == "1", path
	files = dict(con.execute("select id, path from file"))
	return {
		(files[fid].split("/addon/", 1)[1], a, b)
		for fid, a, b in con.execute("select distinct file_id, fromno, tono from arc")
	}


before, after = arcs(sys.argv[1]), arcs(sys.argv[2])
lost = sorted(before - after - TIMING)
gained = sorted(after - before - TIMING)
for module in sorted({arc[0] for arc in lost + gained}):
	print(module, "lost", [a[1:] for a in lost if a[0] == module], "gained", [a[1:] for a in gained if a[0] == module])
unexpected = [arc for arc in lost if arc not in ALLOWED_LOST]
missing_allowed = sorted(ALLOWED_LOST - set(lost))
print("unexpected lost:", unexpected)
print("allowed lost not lost (fine, report it):", missing_allowed)
sys.exit(1 if unexpected else 0)
```

Gate: exit 0, i.e. every arc of `cov-before.db` outside `TIMING` is in the new run except the three `ALLOWED_LOST` arcs. Gained arcs are reported, never a failure. Record the printout in the ledger. If a timing arc in `TIMING` is the only difference, nothing more is needed; any other lost arc is a merge that dropped a path: fix the merge, do not extend the allow-list.

### 9.4 Per-module report

Against `2026-11-10-phase59-test-clean3-coverage-before.txt`: for every module Stmts and Branch equal (no `addon/` change; TOTAL 8625 / 2472), Miss and BrPart not higher, except `runtime/scheduler.py` and `runtime/_segmentLifecycle.py` by at most the `TIMING` arcs. A script compares the two tables and lists every module that differs in either direction.

### 9.5 Other checks (DEVELOPMENT_WORKFLOW.md §7)

- `git diff --stat master -- addon` is empty: **no change under `addon/` at all** in this phase.
- `prek run --all-files`: every hook Passed (ruff pinned `0.16.3`, `pyproject.toml:81-82`).
- `git diff --check`.
- Protected paths: the two commands of DEVELOPMENT_WORKFLOW.md §7 print nothing.
- Linux only; no Windows or NVDA manual item (nothing user-visible changes).

## 10. Commit structure

The spec and its four lists are committed first (this commit), then the plan. Implementation commits are small and separated by kind, in this order:

1. **Deletion commits**, one per audit group (G1 … G8; G2's only deletes K-G2a): whole functions, rows and values of §5.2, `test_f4_engine_session.py`, and the §5.4 knock-ons marked "deletion". D10 is not here. A deletion commit adds nothing: every added line in each hunk is an ordered subsequence of the hunk's removed tokens (Python `tokenize`; allows a shortened import line or a list row cut out of a one-line list). The R1–R3 restructures go in a separate G4/G7 restructure commit right after that group's deletions.
2. **Merge commits**, one per M-row or per test file (a pure parametrize/fold; the knock-ons a merge causes go with it). Each commit records its `- old`/`+ new` ids in the ledger and passes §9.1.
3. **Tidy commits** T1–T10, one per file.
4. **Translator commits**: X1 + X2, then D10 + K-G7b.

Each commit: full suite count as §9.2, §9.1 proof, prek. The coverage gate (§9.3, §9.4) runs after the last deletion commit, after the last merge commit and at the end of the branch.

## 11. Risks and Review Focus candidates

1. **A merge that silently drops an assertion.** The rows in §6 name every assertion that moves; the reviewer compares each replaced test with its target line by line (the arc gate sees paths, not assertions).
2. **Kept ids that change by accident.** G3-M2, G6-M1 and G2-M8c restructure kept parametrizes; their shapes keep the ids (`engine` table lookup, `name` table lookup, explicit `pytest.param` ids). §9.1 step 3 fails on any unplanned change.
3. **Hypothesis merges change sampling.** G4-M1 runs six properties on one sample stream instead of six; G3-M1 adds ten examples that always run. The properties' strategies are unchanged; the examples pin what the replaced tests pinned.
4. **Timing-sensitive merges.** G1-M2, G1-M5, G1-M12, G2-M1, G2-M3 and G2-M4 merge concurrency tests; the 5× repeats of §9.2 are the check.
5. **The fragment arcs** of N3: the gate allows exactly three; a fourth lost arc means a path was dropped.
6. **The translator checks read only `_("literal")`.** A future `pgettext`/`ngettext` call fails X1 by design (unsupported form) until the helper and `_catalog` learn it.
7. **Renumbered ids** (N5): nothing in `pyproject.toml`, `tools/` or `tests/` selects tests by id (check by grep before committing).

## 12. Non-goals

- **The coverage gaps** of the audit (§4 item 3 and each group's 覆蓋缺口), for a later phase; listed for traceability: RHVoice wrapper `driver/RHVoice/__init__.py:148-150`, `:218-219`, `:251`, `:319-322`, `:100-101`; VE/Cerence segment inner `speak()` raising (`driver/VE/__init__.py:475->482`, Cerence `:480->487`), pause failure with a native call in flight (VE `:800`, Cerence `:810`), the no-errcheck failure result (`:219`); SAPI5 `driver/SAPI5/__init__.py:536->534`, `:146-147`, `:332`, `:342`, `:571`; OneCore `:431-432`, `:566-567` and eSpeak `:208-209` (listener raising in `synthDoneSpeaking`); `runtime/scheduler.py:455`, `:487`; `runtime/_segmentLifecycle.py:323`; `runtime/segmentHost.py:528->530`; `bridge/nvdaEvents.py:233->exit`; `globalPlugins/WorldVoice/rolePresenter.py:45->44`; `panels/role.py:164`; `ui/voicePanel.py:204->202`; `tools/generate_unspaced_common.py` `load_script_of` returning `None`; and the product-code candidates `text/chunker.py:98`, `panels/base.py` `settingsSizerHelper` (`30->32`), `bridge/engineAdapter.py:53` (`addon/` changes).
- No change under `addon/`.
- No new tests except X1 and X2 and the tests the merges produce (§6.9).
- The `# Translators:` presence check with a shrinking list of the 44 legacy strings (N8).
- The audit's 保留但值得一提 items (§7, last paragraph) and D13's later removal with the UNTRACKED exceptions.
- No translation, readme or packaging work (no string changes).

## 13. Constraints (DEVELOPMENT_WORKFLOW.md §8)

- Work only in `/workspace/WorldVoice-phase59`; `ref` there is a git-ignored symlink, never staged. The main checkout is not touched.
- Stage explicit paths only and check `git diff --cached --stat` before each commit; English `<type>: <summary>` messages with a body that says why; no `Co-Authored-By`; prek hooks run, re-stage after a hook fix, never `--no-verify`; no push; never `git stash`.
- Do not touch the inner drivers (`driver/<Engine>/driver/`) or the generated Unicode data; engines stay independently installable; Neural is not added.
- At most 3 pytest processes at a time, each with the MemAvailable < 3 GB watchdog that kills only its own process; never `ulimit -v`.

## 14. Defaults taken and open questions

None blocks the work. Defaults taken (*Decided by orchestrator with the recommended default; user may override before merge*):

1. N3: the three `load_definitions` fragment arcs of the global plugin are allowed to go.
2. N7: X1/X2 count buildVars' changelog as a source string.
3. §5.2: `test_groups_keep_leading_zeros_and_every_digit` keeps a one-value `["value"]` parametrize (ids unchanged).
4. §5.4: `shape()`'s `else` branch in `test_pipeline_number_groups.py` stays.
5. §6: optional extras of the audit's merge shapes are not done where they would rename a kept id (G2-M3 constant, G2-M8c full 2 × 3, G8-M4 parametrize with the AttributeError test).
6. §7: the 連帶可刪 tidy edits T1–T10 are done; the 保留但值得一提 items are not.
