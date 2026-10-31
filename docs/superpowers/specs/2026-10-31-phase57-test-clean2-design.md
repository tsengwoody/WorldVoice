# Phase 57: test-clean2 removals

Date: 2026-10-31.
Base: `master` `3c178f4`. Branch: `phase57-test-clean2`. Normal flow (DEVELOPMENT_WORKFLOW.md §3).
Source: the test audit `storage/test-clean2.md` (2026-10-31, base `3c178f4`; git-ignored), its id lists `storage/test-clean2-remove.txt` (455 node ids) and `storage/test-clean2-decide.txt` (121 node ids), and the audit's per-test coverage data (`unique.json`, `report-before.txt`, `cov-before.db` in the audit's scratchpad).

User instruction (2026-10-31): delete the tests in `test-clean2-remove.txt` as recommended, and handle the user-decision items according to their leaning; the coverage gaps come afterwards (phase 58, not this phase).

Appendix files, committed next to this spec:

| File | Content |
|---|---|
| `2026-10-31-phase57-test-clean2-remove.txt` | The **final** removal list: 486 collected node ids that disappear (455 + 31 decide items that lean remove). Sorted, ids exactly as `pytest --collect-only -q` prints them at `3c178f4`. |
| `2026-10-31-phase57-test-clean2-renames.txt` | Every explicit id change of a kept test (7 `old -> new`) and the one new id (`+ new`). |
| `2026-10-31-phase57-test-clean2-edited.txt` | The kept tests whose code changes (161 ids, tagged by kind of change). |
| `2026-10-31-phase57-test-clean2-coverage-before.txt` | The audit's baseline `coverage report` at `3c178f4` (per module; TOTAL 8368 stmts / 180 miss, 2374 branches / 157 partial, 96.75%), the reference for the per-module gate (§6.3). |

| | Count |
|---|---|
| Collected at `3c178f4` | 3727 (3727 passed, 0 skipped) |
| Removed: audit list | 455 |
| Removed: decide items that lean remove | 31 |
| **Removed in total** | **486** |
| Kept decide items | 90 (76 unchanged, 14 edited) |
| New ids | 1 (an assertion moved out of a parametrize, §5.4 E2) |
| Renamed or moved ids | 7 (§5.5, `-renames.txt`) |
| **Collected and passed after** | **3242** (= 3727 − 486 + 1), 0 skipped |
| Test files deleted | 4: `test_role_guards.py`, `test_workspace.py`, `test_worldvoice_index_command.py` (emptied by removals); `test_core_archive.py` (its 3 kept tests move to `test_core_install.py`) |
| Changes under `addon/` | none |

Line references are `tests/<file>:<line>` at `3c178f4` unless they name another path.

## 1. Problem and goal

The suite has grown to 3727 collected tests. The audit found 455 that are pure existence pins left by one-off refactors, duplicates, tests whose assertions another test asserts as a superset, and parametrize cases that take no branch of their own (audit §1, §2.3). It also left 121 ids to the user, each with a leaning. Removing the 455 with `--deselect` kept the branch coverage at 96.77% with no module losing a line or branch (audit §1, A.1).

Goal: delete those tests from the source, resolve every decide item as the user asked (follow the leaning), do the merges a deletion needs so that no assertion is lost, and drop the helpers, fixtures and imports the deletions leave unused. No test changes behaviour except where this spec says so; nothing under `addon/` changes; NVDA users see and hear nothing different.

## 2. What disappears

- **The 455 audit ids**, all of them (the audit's coordinator already moved `tests/test_core_archive.py::test_install_always_removes_the_archive[False]` out of the list and keeps it: audit §1 and §3 G7; it is not in the 455).
- **31 decide ids** that lean remove (§3).
- Together: `2026-10-31-phase57-test-clean2-remove.txt` (486 ids). It is the only source of truth for what disappears; §6.1 proves the collection matches it exactly.

Per kind of edit (computed from the collection at `3c178f4` against the final list):

| Kind | Functions | Ids |
|---|---|---|
| Whole test function deleted (every case removed) | 124 | 165 |
| Some cases of a parametrize removed | 101 | 321 |

The partially removed parametrizations are handled by §5.2 and §5.3.

## 3. The decide items (121 ids)

Every row: **Decided by the user (2026-10-31): follow the audit's leaning**, except the two rows marked *Correction* (§4 C1) and the two marked *Deferred* (their leaning is conditional on a replacement this phase defers, §5.6), which are **Decided by orchestrator with the recommended default; user may override before merge**.

| # | Test (ids) | Leaning | Action in this phase |
|---|---|---|---|
| D1 | `test_engine_segment_contract.py::test_every_core_speaks_segments_through_the_shared_mixin[VE\|Cerence\|OneCore\|RHVoice\|SAPI5\|Espeak]` (6), `:170` | keep | Keep unchanged. It is the loaded-class check that also makes D30 redundant. |
| D2 | `test_set_voice_in_flight.py::test_choosing_another_voice_mid_segment_lets_the_request_finish[…-False]` (5), `:40` | keep | Keep unchanged. |
| D3 | `test_sapi5_segment_drain.py::test_pcm_arriving_after_completion_cannot_feed_retired_audio`, `:783` | remove | Delete. |
| D4 | `test_onecore_segment_drain.py::test_native_and_parse_errors_fail_original_work_without_drain[response4]` (markers `"1:-1"`, `:565`) | remove | Delete that row. `[response5]` renumbers to `[response4]` (§6.1 pairs it by its parameters). |
| D5 | `test_runtime_segment_completion.py::test_marker_pause_cancel_current_and_future_callback`, `:413` | remove | Delete. |
| D6 | `test_worldvoice_cancel_wrappers.py::test_installs_player_stand_in_and_keeps_inner_stop_flag[VE\|Cerence]` (2), `:68` | keep, drop the token lines | Keep; delete `:70-72` (the token comment and the two token assertions). The token rule stays guarded by D34 (§4 C1). |
| D7 | `test_segment_host.py::test_boundary_hook_ignores_an_operation_without_a_record`, `:679` | keep | Keep unchanged. |
| D8 | `test_completion_rules.py::test_completion_mode_is_compared_only_where_contracts_are_built`, `:116` | keep | Keep unchanged. |
| D9 | `test_completion_rules.py::test_every_completion_mode_has_exactly_one_rule`, `:50` | remove | Delete. |
| D10 | `test_f4_engine_adapters.py::test_onecore_language_is_applied_only_on_activation`, `:84-98` | remove | Delete (and its orphans, §5.7). |
| D11 | `test_runtime_completion_policies.py::test_six_loaded_voices_pass_the_pre_rename_check[*]` (6), `:429-439` | keep (and consider deleting the AST twin) | Keep unchanged; the AST twin is D27. |
| D12 | `test_pipeline_filters.py::test_an_old_snake_case_log_switch_does_not_log`, `:899` | remove | Delete. |
| D13 | `test_pipeline_settings_service.py::test_old_snake_case_keys_read_as_defaults`, `:628` | keep | Keep unchanged. |
| D14 | `test_pipeline_panels.py::test_table_labels_tell_translators_they_name_log_switches`, `:245` | keep | Keep unchanged. |
| D15 | `test_pipeline_structure.py::test_pipeline_package_keeps_only_stages_logging_and_registry[*]` (9), `:133-155` | keep; drop (1) the MOVED check, move (3) out of the parametrize | Edit E2 (§5.4). |
| D16 | `test_pipeline_structure.py::test_speech_context_holds_only_plain_values`, `:200-225` | keep; drop the `default_voice` grep | Edit E3: delete `:219-225`. The field list and the `Any` check stay. |
| D17 | `test_pipeline_nvda_ssml.py::test_nvda_ssml_keeps_every_word_and_pause_of_the_scope_all_output[group-pauses2]` | remove | Delete the `("group", [10, 20])` row at `:48`. |
| D18 | `test_pipeline_unspaced_space.py::test_is_unspaced[㐀\|鿿\|豈\|〇\|ㆠ]` (5), rows `:40`, `:41`, `:42`, `:45`, `:50` | remove ("if the generators have tests of their own") | Delete the 5 rows. The condition holds: `test_generate_unicode_scripts.py`, the code-point samples in `test_unicode_scripts.py` and the byte-exact guard `test_generated_unicode_data.py::test_script_data_is_the_generators_output` cover the data. |
| D19 | `test_pipeline_unspaced_space.py::test_pipeline_harness_loads_the_script_lookup_fresh`, `:150-157` | remove ("keep if a false green ever happened") | Delete. No false green is recorded: it came with the harness change of `a68dc53` as a preventive check (spec `2026-10-25-feat-unspaced-script-space-pause-design.md` D5). |
| D20 | `test_role_guards.py::test_error_callback_finds_its_dialog_without_a_class_registry` | remove | Delete; the file is then empty and is deleted. Its 2 unique arcs are `addon/globalPlugins/WorldVoice/panels/role.py` `(-1,20)` and `(20,-1)`, the entry and exit of the `gotErrorCallback` fragment that `load_definitions` compiles on its own; lines `role.py:20-23` stay covered by `test_role_panel_ui.py::test_a_failing_handler_reports_the_error_and_reopens_the_dialog` (`:268-289`, which asserts `dialog.cancelled == [None]` and the `popupSettingsDialog` call with the dialog type). |
| D21 | `test_role_panel.py::test_panel_opens_its_presenter_for_the_worldvoice_manager`, `:89-164` | remove, after moving its `_onDestroy` binding assertion | Merge M2 (§5.5), then delete. |
| D22 | `test_worldvoice_index_command.py::test_marker_is_an_index_command` | remove | Delete; with `test_marker_rejects_non_integer` (audit list) the file is empty and is deleted. |
| D23 | `test_ui_structure.py::test_panels_apply_dependencies_through_one_path`, `:83` | keep | Keep unchanged. |
| D24 | `test_settings_table_guard.py::test_each_check_reports_a_broken_table[*]` (44), `:411` | keep | Keep unchanged. |
| D25 | `test_config_stub.py::test_the_stub_refuses_a_key_its_section_lacks`, `:15` | keep | Keep unchanged. |
| D26 | `test_plugin_voice_contract.py::test_plugin_attributes_exist_on_the_base_voice`, `:77` | keep | Keep unchanged. |
| D27 | `test_plugin_voice_contract.py::test_no_bundled_voice_defines_a_pre_rename_name`, `:143-161` | remove | Delete. Verified superset: D11 runs `discovery._pre_rename_contract_names` (`addon/synthDrivers/WorldVoice/engineRegistry/discovery.py:157-159`, `hasattr` over `PRE_RENAME_CONTRACT_NAMES` `:36-43`) on each of the same six loaded `Voice` classes (`SIX_ENGINES`, `test_runtime_completion_policies.py:351`; `BUNDLED_ENGINES`, `test_plugin_voice_contract.py:122`); `hasattr` sees every name a class body defines, and inherited ones too. |
| D28 | `test_native_strategy_guards.py::test_sapi5_uses_the_shared_engine_controls`, `:215-218` | remove | Delete. Same assertion as `test_engine_players_are_leased[SAPI5]` (`:740-744`, `LEASED_PLAYERS["SAPI5"] == "_SegmentPlayer"`, `:705-711`). |
| D29 | `test_native_strategy_guards.py::test_rhvoice_uses_shared_player_and_stop_gate`, `:266-270` | remove | Delete. Same as `test_engine_players_are_leased[RHVoice]` (`_WavePlayer`). |
| D30 | `test_native_strategy_guards.py::test_every_bundled_wrapper_uses_the_segment_host_speaker`, `:413-419` | remove | Delete. D1 (kept) asserts `speak_segment is SegmentHostSpeaker.speak_segment` on every loaded wrapper, and `test_every_wrapper_core_declares_the_segment_drain_entries` (`:398-410`) pins the base set. |
| D31 | `test_native_strategy_guards.py::test_vocalizer_wrapper_has_no_guard_fallback[VE\|Cerence]` (2), `:386-395` | keep, drop the `_guardInstalled` line | Edit E4 (§5.4), with the rename the audit suggests. |
| D32 | `test_native_strategy_guards.py::test_drain_support_requires_keywords[Espeak\|RHVoice]` (2), `:116-126` | remove | Delete the whole function. |
| D33 | `test_native_strategy_guards.py::test_onecore_uses_the_stop_gate_and_declares_voice_last`, `:325-334` | remove | Delete. |
| D34 | `test_native_strategy_guards.py::test_no_add_on_code_names_the_request_token`, `:686-697` | remove | ***Correction*: keep** (§4 C1). Edit E5: its comment `:687-690` names `test_plain_speak_never_passes_the_request_token`, which the audit list removes; reword it. |
| D35 | `test_native_strategy_guards.py::test_token_name_detection`, `:673-683` | remove with D34 | ***Correction*: keep** with D34. |
| D36 | `test_generated_unicode_data.py::test_a_hand_edit_of_script_data_is_caught[upper-case hex \| added comment \| docstring]` (3) | remove | Delete the rows `:99-103` (with their comments). The split-range row and the `SCRIPT_RANGE_STARTS` row stay. |
| D37 | `test_generated_unicode_data.py::test_a_hand_edit_of_unspaced_common_data_is_caught[lower-case hex \| one space before the comment]` (2) | remove | Delete the rows `:121-123` (with the comment `:121`). |
| D38 | `test_translator_comments.py::test_changed_label_strings_have_translator_comments`, `:131` | remove *after* replacing it with the generic guards | ***Deferred*: keep.** The replacement (audit G6 merge suggestion) is not done in this phase (§5.6), so the leaning's precondition does not hold. |
| D39 | `test_translator_comments.py::test_zh_tw_catalog_follows_the_labels`, `:156` | same as D38 | ***Deferred*: keep.** |
| D40 | `test_detection_settings.py::test_old_pascal_case_keys_are_ignored`, `:269` | remove | Delete. |
| D41 | `test_main_locale_policy.py::test_old_pascal_case_flags_are_ignored`, `:125` | remove | Delete. |
| D42 | `test_detection_settings.py::test_the_config_stub_reads_the_detection_defaults_from_the_table`, `:194` | keep | Keep unchanged. |
| D43 | `test_detection_settings.py::test_script_languages_are_read_only`, `:78` | keep | Keep unchanged. |
| D44 | `test_voice_catalog.py::test_catalog_is_immutable`, `:62` | keep | Keep unchanged. |
| D45 | `test_locales.py::test_primary_language_matches_both_former_helpers`, `:36` | keep (consider a rename) | Keep unchanged; the rename is deferred (§5.6). |
| D46 | `test_workspace.py::test_install_without_core_files_does_not_load_the_workspace` | remove | Delete; with the two audit-list tests the file is empty and is deleted. `addon/synthDrivers/WorldVoice/workspace.py` and `addon/installTasks.py` lose no covered line or branch (static union check, §4 N5). |

Totals: removed 31 ids (D3, D4, D5, D9, D10, D12, D17 ×1, D18 ×5, D19, D20, D21, D22, D27, D28, D29, D30, D32 ×2, D33, D36 ×3, D37 ×2, D40, D41, D46); kept unchanged 76 ids (D1 6, D2 5, D7, D8, D11 6, D13, D14, D23, D24 44, D25, D26, D34, D35, D38, D39, D42–D45); kept with edits 14 ids (D6 2, D15 9, D16 1, D31 2).

## 4. Corrections and notes on the audit

**C1 (correction): the request-token guard stays (D34, D35).** The audit's own summary names `_TOKEN_NAMES` in `test_native_strategy_guards.py` as the one guard that keeps the removed token keyword and trait from coming back (audit §1.3 item 2), and two removals rest on it: the 3 `test_runtime_legacy_adapter.py::test_plain_speak_never_passes_the_request_token[*]` and the 2 `::test_bridge_speaks_the_real_vocalizer_wrapper_without_a_token[*]` (audit G3: "token 名稱全域禁用另由使用者保留的 test_native_strategy_guards.py `_TOKEN_NAMES` 守住"), and D6's dropped lines (audit G2: "token 關鍵字已由 test_native_strategy_guards.py 的 AST 守門（86399d4）負責"). D34's own leaning cites the other way round: "behaviour covered by `test_plain_speak_never_passes_the_request_token` and `test_worldvoice_cancel_wrappers.py:71`", both of which go. Following every leaning would leave no check at all on a rule the audit meant to keep in one place. D34 also scans the vendored inner drivers (`:691-696`), so it is the only check that would notice an upstream VE/Cerence inner update reintroducing the keyword. Kept: 2 ids. *Decided by orchestrator with the recommended default; user may override before merge* (removing both is consistent with the user's "existence pin" rule if the user prefers no guard).

**N1 (note, list followed): two more circular cross-references.** `test_hygiene_guards.py::test_the_speech_symbols_feature_is_gone` (audit list) says the behaviour is covered by `test_language_detector.py::test_symbols_argument_is_rejected[keyword]`, and `::test_the_ignore_numbers_option_is_gone` cites `test_detection_settings.py:254` (`test_get_reads_a_section_that_still_holds_the_old_key`) and `test_language_detector.py:426` (`test_digits_follow_the_current_language_whatever_is_stored`); all of these are in the audit list too. Unlike C1, the audit summary names no retained guard for them: each is a pin that a removed option (phase 33 speech symbols, phase 35 ignore-numbers) stays removed, the category the user asked to delete. They are deleted as listed; after this phase nothing checks that those options stay gone. Reported to the user.

**N2 (note): spot checks of the "被涵蓋" (subsumed) claims.** Both tests were read for each:

| Removed | Subsuming test(s) | Result |
|---|---|---|
| `test_pipeline_filters.py::test_number_wait_keeps_held_language_commands_at_the_end` `:259` | `::test_number_wait_breaks_between_numbers_across_language_commands` `:225-237` (sequence ends with a held language command) | holds |
| `::test_number_wait_inserts_number_break_commands` `:283-288` | `shape()` rows with `B40 = ("NumberBreakCommand", 40)` (`:20-29`, `:174`); `test_pipeline_passthrough.py::test_a_number_break_counts_as_an_existing_pause_for_punctuation` `:203-211` (subclass of BreakCommand) | holds |
| `::test_punctuation_segments` `:831-841` | `test_pipeline_punctuation_pause.py::test_zero_wait_keeps_the_pause_point_rules` Rule 1 (`12,500.`) and Rule 2 rows (`:227-234`) | holds |
| `test_pipeline_punctuation_pause.py::test_positive_punctuation_wait_factor_inserts_a_punctuation_break` `:24-33` | `::test_the_punctuation_pause_follows_the_global_factor[10-30-30]` `:36-61` (same input, same four-item shape, real settings) | holds |
| `::test_a_disabled_switch_changes_nothing[*]` (12) `:135-145` | `test_pipeline_pause_properties.py::test_property_a_disabled_switch_changes_nothing` `:62-75` (`is` identity; characters `""`, `" "`, marks; remove; wait 0–1000) | holds |
| `::test_removal_applies_to_pause_between_text_items` `:122-132` | `::test_zero_wait_pauses_at_every_point_whether_or_not_marks_are_removed[True]` `:170-179` | holds |
| `test_pipeline_settings_service.py::test_stored_key_is_nvda_camel_case_of_the_field[*]` `:69-81` | `::test_every_entry_reads_its_stored_key_from_the_derivation` `:84-100` (all 12 stored keys, `sayAllWaitFactor` included) | holds |
| `::test_scaled_waits_…[changes1…changes8]` `:413-439` | `test_pipeline_pause_properties.py::test_property_every_pause_is_the_global_units_times_its_factor` `:634-649` (oracle `global // 10 * factor`, all five keys, 0–100) | holds |
| `test_pipeline_stages.py::test_handler_logs_before_and_after_when_enabled` `:172-180` | `::test_a_stage_logs_under_each_of_its_switches[own-only]` `:63-84` | **holds only together with** `test_pipeline_filters.py::test_run_logged_records_only_when_switched_on[INFO-True-True]` `:844-874`: `[own-only]` uses an identity stage, so only the latter asserts that the logged path returns the stage's *transformed* output; `Stage.handler` returns `_run_logged`'s result as is (`addon/synthDrivers/WorldVoice/pipeline/registry.py:112-117`). Both stay. |
| `::test_positive_number_wait_breaks_between_numbers` `:224-229` | `test_pipeline_filters.py::test_number_wait_factor_drops_blanks_then_breaks_between_numbers` `:95-105`; `test_pipeline_passthrough.py::test_number_wait_drops_blank_text_but_not_commands` `:110-115` (strips `" 3 "`) | holds |
| `::test_another_synth_keeps_the_punctuation_pause_next_to_an_edge[*]` `:615-635` | `test_pipeline_number_edges.py::test_other_synths_keep_the_punctuation_pause_through_the_handlers[*]` `:584-599` (end to end through every handler) | holds |
| `test_pipeline_unspaced_space.py::test_wait_zero_yields_the_same_objects` `:309-312` | `test_pipeline_unspaced_space_properties.py::test_property_off_is_identity` `:101-105` | holds |
| `test_pipeline_number_edges.py::test_number_stage_worked_examples[*-item10…]` | the number stage never reads the item wait: `scaled_item_wait` is read only at `addon/synthDrivers/WorldVoice/pipeline/items.py:29` | holds |
| `test_settings_order.py::test_voice_panel_rows_follow_the_table`, `::…tab_order_follows_the_table`, `::…survive_a_voice_change` `:206-222` | `::test_voice_panel_orders_follow_the_table[first build\|voice switch]` `:277-290` (same panel construction in `build_then` `:259-274`) | holds |
| `test_role_repository.py::test_save_rewrites_sections_and_keeps_scalars` `:64-67` | `::test_save_drops_role_sections_under_full_locale_keys` `:76-82` | holds |
| `::test_assign_adds_or_replaces_one_locale` `:70-73` | `::test_assign_drops_a_stored_full_locale_role_so_the_primary_role_speaks` `:85-92` | holds |
| `test_settings_panel_save.py::test_unchanged_engines_write_nothing` `:93-100` | `test_settings_panels.py::test_engine_panel_unchanged_engines_save_without_asking` `:447-454` | holds |
| `test_unicode_panel.py::test_saving_unchanged_choices_notifies_nobody` `:154-157` | `::test_saving_reports_a_timing_change_to_subscribers_not_to_the_synth[after-False]` `:143-151` | holds |
| `test_role_panel.py::test_failed_apply_shows_error_and_raises_value_error` `:19-57`; D20; D21 | `test_role_panel_ui.py` (`:268-289`; the fake `Presenter` requires both `speechSection` and `setMainVoice` keywords, `:18-21`) | holds; D21's binding assertion is the one gap, moved by M2 |

**N3 (note):** the audit's one removal with unique coverage, `test_pipeline_settings_service.py::test_the_refused_key_bookkeeping_is_gone`, owns only the entry and exit arcs of `read_stored` (`addon/synthDrivers/WorldVoice/pipeline/settings.py`, `(-361,361)`, `(361,-361)`), like D20's two arcs: no line, no branch. The audit's `--deselect` run showed `settings.py` unchanged.

**N4 (note): the kept `[False]` case.** `test_core_archive.py::test_install_always_removes_the_archive[False]` is the only covered path through `addon/generics/coreArchive.py:31→34` once the two other `test_core_archive.py` tests go, because the `install` fixture of `test_core_install.py` runs *copies* of `coreArchive.py` and `workspace.py` in a temporary add-on folder (`test_core_install.py:1-6`, `:72-97`) and coverage does not see copies. Merge M3 (§5.5) therefore moves the test with its loader unchanged (`core_archive_harness.load` on the real `INSTALL` path, `test_core_archive.py:48-62`); it must **not** be switched to the `install` fixture, despite the audit's "([True] 可以改用那邊的 `install` fixture)". The `[False]` and `[True]` cases move together.

**N5 (note): static check of the final list.** Over the audit's per-test coverage database, the arcs and lines executed *only* by tests in the final 486-id list are exactly the four entry/exit arcs of N3 and D20; no line, no branch arc. This does not see the effect of the fixture and helper edits of §5.4–§5.7, which the real coverage run (§6.3) checks.

## 5. How the removals are made

### 5.1 Whole functions

Delete the function (with its decorators and the comment block directly above it that only describes it). 124 functions, 165 ids.

### 5.2 Parametrize rows

- When the removed cases are whole rows of one parametrize list (or whole values of one of several stacked parametrizes), delete those rows or values. Rows with explicit ids (`pytest.param(..., id=...)` or `ids=[...]`) keep their ids.
- Rows with pytest's automatic index ids (`sequence2-expected2`, `response5`, `config4`, `error2`, `changes9`, `extension1`, duplicates disambiguated as `0-False0`/`0-False1`, …) renumber when an earlier row goes. That is accepted: no explicit ids are added only to keep an index id stable. §6.1 pairs every renumbered id with its base id by function and parameter values; the plan's ledger records the pairs. Affected functions (from the collection at `3c178f4`): `test_engine_discovery.py::test_a_configured_engine_flag_overrides_the_manifest_default`, `::test_plugin_with_old_contract_names_is_reported`, `test_engine_registry.py::test_engine_enabled_reads_the_config_then_the_manifest`, `test_generate_unicode_scripts.py::test_network_errors_name_the_url_and_suggest_a_local_file`, `test_generate_unspaced_common.py::test_network_errors_…`, `::test_select_drops_characters_without_an_unspaced_script`, `test_onecore_segment_drain.py::test_native_and_parse_errors_…` (D4), `test_pipeline_filters.py::test_number_wait_breaks_only_between_whole_numbers`, `::test_number_re_finds_whole_numbers`, `::test_number_wait_splits_numbers_separated_only_by_whitespace`, `test_pipeline_settings_service.py::test_scaled_waits_are_the_global_units_times_the_factor`, `test_pipeline_stages.py::test_other_synths_get_only_plain_breaks_from_the_stages`, `::test_worldvoice_keeps_the_break_subclasses_from_the_stages`, `test_pipeline_unspaced_space.py::test_pauses_between`, `::test_worked_examples`, `test_ui_controls.py::test_read_control_without_a_control_is_absent`.
- **A parametrize left with one row stays a one-row parametrize** (its id does not change), e.g. `test_runtime_scheduler.py::test_all_concurrent_stops_finish_before_new_speech` keeps `@pytest.mark.parametrize("stop_count", [2])` (`:301`) and its loops over `stop_count`. Exception, because the parameter's machinery becomes dead code (audit G2 連帶可刪): the two cases below drop the parametrize and are listed in `-renames.txt`:
  - `test_segment_host.py::test_retire_waits_for_admitted_consumers[0]` → `::test_retire_waits_for_admitted_consumers`: delete `:269` and the `start_delay` parameter and the `Event().wait(start_delay)` line `:276` (with its comment).
  - `test_segment_lifecycle.py::test_queued_run_does_not_poll_its_token[0]` → `::test_queued_run_does_not_poll_its_token`: delete `:831`, the `start_delay` argument at `:835`, the `start_delay` parameters of `CountingToken.__init__` (`:759`, `:762-763`) and `_accept_counting` (`:778`, `:780`), and the `if self.checks == 0: Event().wait(...)` lines `:766-767`. `CountingToken`'s other user, `test_wait_idle_wakes_on_token_cancel_without_polling`, passes no `start_delay` (audit G2; re-check by grep).
  If `Event` then has no other use in a file, its import goes too.
- Fixture parametrization: `test_nvda_ready.py::test_ready_on_ref_nvda_is_true_and_silent[SAPI5]` goes by switching the test from the `engine` fixture (`:73-76`, params `sorted(CASES)`) to the existing `skipped_engine` fixture (`:79-82`, params Espeak, OneCore): `def test_ready_on_ref_nvda_is_true_and_silent(skipped_engine, monkeypatch)` (`:98-99`). The remaining ids `[Espeak]` and `[OneCore]` are unchanged; `engine` stays for `test_live_and_static_views_agree_on_ref_nvda` (`:181`). The SAPI5 case is covered by `test_sapi5_on_ref_nvda_uses_the_wrapper` (`:145-147`).

### 5.3 Cross products and shared tables (restructured parametrizations, kept ids unchanged)

Where the removed cases are not whole rows, the parametrization is rewritten so that it produces exactly the kept ids, with the same id strings (pytest joins stacked parametrize ids starting from the decorator nearest the function; a single parametrize over the same argnames in that order produces the same strings).

| # | Test | Removed / total | Restructure |
|---|---|---|---|
| R1 | `test_pipeline_filters.py::test_number_mode` `:442-449` (stacked `mode,size,pause` × `text`, tables `TEXTS`/`SHARED`/`NUMBER_MODES` `:379-439`) | 33 / 60 | Drop the `("group", 3, 0)` and `("group", 10, 0)` tables (20 ids). Apply `SHARED` (`a. 3`, `3.`, `.5`, `""`) only to `("value", 3, 0)` and `("group", 2, 50)` (8 ids). Drop `-1234`, `123`, `12`, `1.2.3` from `("value", 3, 0)` and `123` from `("number", 3, 0)` (5 ids). Replace the two stacked decorators by one `@pytest.mark.parametrize(("text", "mode", "size", "pause"), CASES)` built from the tables, so each `(mode, size, pause)` runs exactly the texts its table (with `SHARED` where it applies) lists. Kept: the 27 ids in `-edited.txt` tagged `[R]`, e.g. `[12.5-value-3-0]`, `[-group-2-50]`. |
| R2 | `test_pipeline_filters.py::test_number_and_group_modes_name_each_symbol` `:480-485` (`SPEC_TABLE` `:453-473`) | 15 / 36 | Delete the `123.456`, `12.5`, `192.168.0.1`, `3,14`, `6÷2` rows of `SPEC_TABLE` (only this test and `SPEC_IDS` use it). Pure row deletion; 7 rows × 3 columns stay. |
| R3 | `test_pipeline_number_edges.py` `ROWS` `:192-317`, `ITEM_ROWS` `:110-188`, `STAGE_ROWS` `:318`; tests `test_number_stage_worked_examples` `:329-332` and `test_worked_examples_through_every_stage` `:468-473` | 18 / 73 and 3 / 101 | (a) Delete the `id="1g"` row (`:194`; removed from both tests). (b) In the `item_rows` calls for `"inside"` (`:126`) and `"numbers"` (`:127-132`) drop the item-wait-0 entry (`inside-item0` duplicates row `1`, `numbers-item0` duplicates `m1-items`; removed from both tests). (c) `STAGE_ROWS` leaves out every row that `item_rows()` (`:100-105`) made at an item wait other than 0, because the number stage never reads the item wait (N2). Rows not made by `item_rows` (`wrapper-item10`, `total-items-item10`, …) are not affected by (c). How (c) is expressed (a marker set, a flag on `item_rows`, a set of ids) is the implementer's choice; the result must be exactly the kept ids. |
| R4 | `test_runtime_composition.py::test_unconfirmed_wrapper_uses_legacy_and_logs_concrete_fallback_once` `:910-927` (`engine` × `failure`) | 11 / 14 | One parametrize `("failure", "engine")` over `wrong_core-OneCore`, `unsupported-Espeak`, `support_error-OneCore`. |
| R5 | `test_pipeline_settings_service.py::test_load_reads_the_default_for_each_invalid_key` `:464-473` and `::test_a_panel_save_writes_the_default_over_a_refused_value` `:495-515` (both over `list(OLD_DEFAULTS)`) | 7 / 12 each | Both parametrize over a new key list `scope`, `number_mode`, `global_wait_factor`, `punctuation_pause_enabled`, `group_size` (audit G4). `OLD_DEFAULTS` itself is not touched: five other tests and `STORED_DEFAULTS` use it (`:11-40`, `:241`, `:373`, `:404`, `:441`). |
| R6 | `test_worldvoice_pipeline_settings.py::test_voice_parameters_commit_and_follow_the_consistency_policy` `:178-180` (`name` × `consistent`) | 5 / 12 | One parametrize `("consistent", "name")`: the six `False-*` and `True-volume`. |
| R7 | `test_settings_panels.py::test_pipeline_panel_enables_pause_controls_from_the_stored_switch` `:320-322` (`remove` × `pause`) | 2 / 4 | One parametrize `("pause", "remove")`: `(False, True)`, `(True, False)`. |

Every other partial removal is a row or value deletion (§5.2), including the stacked ones that are whole slices: `test_f4_engine_adapters.py::test_bytes_repr_loses_only_its_wrapper` (drop the `b'Arabic'` row), `test_generate_unspaced_common.py::test_network_errors_…` (drop `error1`, `error3`), `::test_an_unreadable_local_file_names_the_path_and_option` (drop the `directory` maker; `ids=["missing"]`), `test_generate_unicode_scripts.py::test_an_unreadable_source_names_the_path_and_option` (same), `test_pipeline_number_edges.py::test_no_edge_break_without_a_number_pause` (drop the `group` mode), and the VE/Cerence pairs in `test_vocalizer_segment_drain.py` (drop the value from the inner list; both engines lose it).

### 5.4 Line-level edits of kept tests

| # | Where (at `3c178f4`) | Edit | Ids |
|---|---|---|---|
| E1 (D6) | `test_worldvoice_cancel_wrappers.py:70-72` | Delete the token comment and the two token assertions. | `test_installs_player_stand_in_and_keeps_inner_stop_flag[VE\|Cerence]` |
| E2 (D15) | `test_pipeline_structure.py:86-103` (`MOVED` and its comment), `:106-115` (`top_level_names`, used only by `:136`), `:136`, `:152-155` | Delete the `MOVED` assertion `:136`, `MOVED` and `top_level_names` (after a grep confirms no other user). Move the `symbols.py` relative-import assertion `:152-155` out of the parametrize, unchanged, into a new test `test_symbols_module_has_no_relative_imports` placed after the parametrized one. The comment `:137-139` stays with the import assertion it explains. | the 9 `[module]` ids; new `test_symbols_module_has_no_relative_imports` |
| E3 (D16) | `test_pipeline_structure.py:219-225` | Delete the `default_voice` scan over every module. | `test_speech_context_holds_only_plain_values` |
| E4 (D31) | `test_native_strategy_guards.py:386-395` | Delete `assert "_guardInstalled" not in source` (`:392`); rename the test to `test_vocalizer_voice_declares_waitfactor_and_variant`; reword the comment `:388-390` to what is left (the Voice declares exactly `waitfactor` and `variant`; the core takes no request token, fix/ve-drop-cancellation-token). | `[VE\|Cerence]`, renamed (`-renames.txt`) |
| E5 (C1) | `test_native_strategy_guards.py:687-690` | Comment only: drop the reference to the removed `test_plain_speak_never_passes_the_request_token`; say this guard is the one check on the token keyword and trait. | `test_no_add_on_code_names_the_request_token` |

Not done (deferred, §5.6): the one-line existence assertions the audit lists under 保留但值得一提 in kept G3/G4 tests (`test_runtime_composition.py:77`, `test_runtime_voice_facade.py:113` second half, `test_runtime_completion_policies.py:205` and `:220`, `test_worldvoice_pipeline_settings.py:63` and `:221`, and two in `test_pipeline_panels.py` / `test_pipeline_settings_service.py`). They are not on the remove list nor decide items.

### 5.5 Merges done in this phase

Only merges that keep an assertion a deletion would otherwise lose, and the file consolidation the audit recommends. *Decided by orchestrator with the recommended default; user may override before merge.*

| # | Merge | Detail |
|---|---|---|
| M1 | `test_worldvoice_cancel_wrappers.py::test_core_cancel_reports_neither_index_nor_done[VE\|Cerence]` (`:231-245`, audit list) into `::test_cancelled_request_drops_index_and_done_notifications` (`:210-227`) | Move the LEGACY_DONE comment (`:232-233`) and the idle assertion: the live request may end in an idle, so record `real_player(core).idles` after the live request and assert it is unchanged after the cancelled one (the removed test's `idles == 0` started from no request). Run the merged test; then delete the source test. |
| M2 | `test_role_panel.py::test_panel_opens_its_presenter_for_the_worldvoice_manager` (D21) into `test_role_panel_ui.py::test_opened_panel_shows_locales_and_consistency_flags_with_no_voice_yet` (`:132-145`) | Add `assert ("EVT_WINDOW_DESTROY", panel._onDestroy, None) in panel.bindings` (the harness records `(event, handler, source)`, `tests/ui_harness.py:413-414`; `EVT_WINDOW_DESTROY` is the string, `:564-570`; the panel binds at `addon/globalPlugins/WorldVoice/panels/role.py:52`) and `assert panel.disable is False` (the source's `:154`, `:156`). Check, in a scratch copy only, that the new binding assertion fails with `role.py:52` removed. Then delete D21. |
| M3 | `test_core_archive.py` into `test_core_install.py` | Move `test_install_always_removes_the_archive` (both cases) and `test_menu_import_reports_a_corrupt_archive` (`test_core_archive.py:48-106`) verbatim to the end of `test_core_install.py`, with what they need: `import types`, `load_definitions` from `addon_loader`, `PLUGIN = ADDON / "globalPlugins/WorldVoice/__init__.py"`. They use `test_core_install.py`'s `make_zip` (`:20-24`; same members, `ZIP_STORED`, return value unused). Keep the real-file loader (N4). Add one sentence to the module docstring (`:1-6`): these two tests load the real files, so coverage sees `coreArchive.py`. Delete `test_core_archive.py`. Prove the move with the order-checking move comparison of DEVELOPMENT_WORKFLOW.md §3.2 (moved blocks byte-identical and in order; only imports, the constant and the docstring sentence added). Ids in `-renames.txt`. |
| M4 | The `symbols.py` check out of D15's parametrize | Part of E2. |

### 5.6 Merges and suggestions deferred

*Decided by orchestrator with the recommended default (defer; none is needed to keep an assertion); user may override before merge.* Listed for a later phase:

- G1: fold the per-engine terminate tests (`test_espeak_segment_drain.py::test_speak_after_terminate_fails_through_lifecycle_delivery`, `test_onecore_segment_drain.py::test_onecore_rejected_segment_uses_async_lifecycle_delivery[True]`) into the contract test.
- G2: merge the two RHVoice sink-terminate tests; fold `test_speech_and_cancel_remain_usable` into `test_guarded_speech_never_touches_inner_stop_flag`.
- G3: turn the `test_runtime_legacy_adapter.py` example tests into Hypothesis `@example`s; fold `test_voice_metadata_names_the_declaring_engine` into `…_keeps_vocalizer_quirks`; merge `test_six_enabled_profiles_use_shared_lifecycle` with `test_actual_outer_voice_and_core_select_enabled_drain_profiles`; move `test_f4_engine_session.py` into `test_runtime_legacy_adapter.py`.
- G4: fold `test_dialog_msgids_come_from_the_dialog_and_every_panel` into `test_log_labels_come_from_the_table`; merge the six `split_once` properties; merge the two worked-example tests of `test_pipeline_number_edges.py`; merge the two no-break-space stage tests.
- G5: merge `test_number_modes_match_the_driver_and_the_panel` with `test_driver_choices_match_the_driver_options`; merge the two failed-save tests of `test_settings_panel_save.py`; `test_worldvoice_request_manager.py`'s own `EventStub`.
- G6: replace `CHANGED_LABEL_MSGIDS`/`DEAD_MSGIDS` by the two generic translator guards; only then D38 and D39 go.
- G7: move `test_global_plugin_lifecycle.py` onto the `ui_harness`; merge the two empty-catalog tests of `test_voice_catalog.py`; rename D45.
- The one-line existence assertions in kept tests (§5.4, last paragraph).

### 5.7 Helpers, fixtures and imports the deletions leave unused

Found by an AST scan of `tests/` (names that have users at `3c178f4` and none after the final list, repeated until nothing new appears) plus the audit's 連帶可刪 lists. The implementer re-checks each by `grep -rnw <name> tests/` before deleting; `ruff` (F401) catches the imports.

| File | Unused after | Delete |
|---|---|---|
| `worldvoice_cancel_wrapper_harness.py:328` | `leased_player()` | the function (its only user, `test_vocalizer_segment_drain.py:2409-2410`, goes) |
| `test_vocalizer_segment_drain.py:18` | `leased_player` import | the name |
| `test_segment_barriers.py:5` | `load_source` | the name (`WORLDVOICE` stays) |
| `test_segment_host.py`, `test_segment_lifecycle.py` | `start_delay` machinery | §5.2 |
| `test_f4_engine_session.py:10`, `:20-21` | `FakeCore.fail_on` | the attribute and the raise (only `test_setter_failure_invalidates_stamp` set it, `:123`, `:127`) |
| `test_f4_engine_adapters.py:5`, `:8` | `load_definitions`, `DRIVERS`, then `WORLDVOICE` | the import line and `DRIVERS` (D10 was their only user) |
| `test_legacy_speech_commands.py` fixture `legacy` `:12-32` | `driver` import `:24`, `Voice=driver.Voice` `:28`, `"driver"` in the loop `:22` | those; then the three stubs `:18-20` (`config`, `languageHandler`, `synthDriverHandler`) only if the three remaining tests pass without them, alone and in the full suite (audit G4: "刪除前請跑一次確認") |
| `test_lint_rewrites.py:12-13` | `StringParameterInfo`, `NUMBER_MODE_CHOICES` in `_driver_methods`' namespace | both entries: only `_get_availableNummods` used them, and `load_definitions(..., members=names)` keeps only the named methods (`tests/addon_loader.py:53-85`) |
| `test_pipeline_panels.py:14` | `CONFSPEC` | the constant |
| `test_pipeline_settings_service.py:3` | `inspect` | the import |
| `test_pipeline_stages.py:8`, `:611-612` | `worldvoice_conf` import, `plain_shape` | both |
| `test_pipeline_unspaced_space.py:18`, `:202` | `SCRIPT_LOOKUP`, `class Marker` (local; used only by `test_wait_zero_yields_the_same_objects`) | both |
| `test_pipeline_structure.py:86-115` | `MOVED`, `top_level_names` | E2 |
| `test_plugin_voice_contract.py:122` | `BUNDLED_ENGINES` | the constant (`ast`, `ROOT`, `pre_rename_names` stay) |
| `test_role_panel.py:5`, `:15-16`, `:81-86` | `pytest`, `checkbox()`, `class Control` | all three |
| `test_settings_order.py:146-151` | `voice_panel()` | the function (`voice_rows`, `voice_controls`, `tab_keys` stay) |
| `test_ui_harness.py:9` | `BoxSizerHelper`, `Label` | the names |
| `test_ui_structure.py:17-23`, `:126-133` | `NOT_WORLDVOICE`, `ERROR_MESSAGE`, `ERROR_TITLE`, `string_constants()` | all four |
| `test_hygiene_guards.py:95-108` | `_imported_modules`, `_is_speech_symbols` | both (`test_lifecycle_private_access.py` has its own `_imported_modules`) |
| `test_script_languages.py:6`, `:11`, `:16` | `re`, `ADDON`, `EXCLUDED` | all three |
| `test_translator_comments.py:42` | `GROUP_MODE_MSGIDS` | the constant (`CHANGED_LABEL_MSGIDS`, `DEAD_MSGIDS`, `ZH_TW_CATALOG`, `_gettext_calls`, `_catalog` stay with D38/D39) |
| `test_nvda_ready.py:216-230` | `_label_definitions()` | the function (`load_source` stays: `test_sapi5_imports_and_uses_nvdas_driver_without_audio_stream_class`) |
| `test_detection_settings.py:3`, `:4`, `:9` | `ast`, `dataclasses`, `_detection_confspec` import | all three (`nvda_stubs._detection_confspec` itself stays; `worldvoice_conf` uses it) |
| `test_core_archive.py` | whole file | M3 |

### 5.8 Stale references

At `3c178f4` the only reference to a deleted test function from code that stays is the comment of E5. References in old specs and plans under `docs/` are history and stay.

## 6. Verification

Run everything in the worktree, one pytest process at a time, under a memory watchdog that kills only its own pytest when MemAvailable drops below 3 GB (for example: start pytest in the background, keep its PID, poll `/proc/meminfo`, `kill <PID>`; never `pkill -f pytest`; other sessions run pytest on this machine).

### 6.1 Collection proof (the core proof of this phase)

A tiny pytest plugin, kept in the scratchpad (not committed), writes one JSON line per collected item:

```python
# collect_params.py: with COLLECT_PARAMS_OUT=<file>, write {"id", "fn", "params"} per collected item.
import json, os, re

_ADDRESS = re.compile(r" at 0x[0-9a-fA-F]+")

def pytest_collection_finish(session):
	out = os.environ.get("COLLECT_PARAMS_OUT")
	if not out:
		return
	with open(out, "w", encoding="utf-8") as handle:
		for item in session.items:
			spec = getattr(item, "callspec", None)
			params = {k: _ADDRESS.sub(" at 0x?", repr(v)) for k, v in sorted(spec.params.items())} if spec else {}
			handle.write(json.dumps({"id": item.nodeid, "fn": item.nodeid.split("[", 1)[0], "params": params}, ensure_ascii=False) + "\n")
```

```bash
COLLECT_PARAMS_OUT=$SP/<name>.jsonl PYTHONPATH=$SP python3 -m pytest --collect-only -q -p no:cacheprovider -p collect_params tests
```

Baseline: collect at the spec commit (its `tests/` equals `3c178f4`'s: `git diff --stat 3c178f4 -- tests` is empty); 3727 lines.

The proof script takes `BASE.jsonl HEAD.jsonl REMOVED.txt RENAMES.txt` and must pass with exit 0 and print its pairing list:

1. Every id of `REMOVED` is a base id; every `old` of `RENAMES` is a base id not in `REMOVED`; head ids are unique.
2. **Multiset of (function, parameters):** base minus `REMOVED`, with each renamed id mapped to its new function (and to empty parameters when the new id has no `[...]`), equals head minus the `+ new` ids. Nothing else may appear or disappear.
3. **Ids:** let `expected = {RENAMES.get(id, id) for base ids not in REMOVED}`. Every head id outside `expected` and outside the `+ new` ids must pair one-to-one with an id of `expected` missing from the head that has the same function and parameters (an index renumbering, §5.2); the script prints each pair. Any unpaired id on either side fails.
4. Each `+ new` id is in the head.

At the end of the branch: `BASE` = the baseline, `REMOVED` = `2026-10-31-phase57-test-clean2-remove.txt`, `RENAMES` = `2026-10-31-phase57-test-clean2-renames.txt`. The renumbering pairs must all be in the functions listed in §5.2 (and D4); the reviewer reads the list.

### 6.2 Test count

`python3 -m pytest -q tests`: **3242 passed, 0 skipped** (3727 − 486 + 1). Also run each test file this phase touches on its own (`python3 -m pytest -q tests/<file>`), so that a kept test that only passed because a deleted test ran before it in the same module shows up.

### 6.3 Coverage gate

Full run with branch coverage (the `pyproject.toml` `[tool.coverage.*]` settings: C tracer, `source = ["addon"]`, vendored code omitted):

```bash
COVERAGE_FILE=$SP/p57.coverage python3 -m pytest tests -q -p no:cacheprovider --cov=addon --cov-branch --cov-report=term > $SP/p57-coverage.txt
```

- TOTAL: Miss ≤ 180 and BrPart ≤ 157, Stmts 8368 and Branch 2374 unchanged (no `addon/` change).
- **Per module** against `2026-10-31-phase57-test-clean2-coverage-before.txt`: for every module, Stmts and Branch equal, Miss and BrPart not higher. A script compares the two tables and lists every module that differs in either direction.
- The only accepted increase is timing jitter in the concurrency modules `addon/synthDrivers/WorldVoice/runtime/scheduler.py`, `runtime/segmentHost.py` and `runtime/_segmentLifecycle.py` (the audit's own `--deselect` run moved `scheduler.py` by one line and one branch, the other way). Such an increase is accepted only after one more full coverage run in which that module is back at or below the baseline; record both runs.
- `addon/generics/coreArchive.py` must stay at 100% (N4).

### 6.4 Commit structure

The spec is committed first (this commit), then the plan. Implementation commits are small and separated by kind; the plan fixes the exact split:

1. **Deletion commits**, grouped per audit group (G1…G7) or per file: whole functions, row and value deletions of §5.2, whole files emptied by removals, and the §5.7 helpers and imports they orphan (ruff's F401 fails a commit that leaves an unused import, so an orphaned import goes in the same commit). A deletion commit adds nothing: every added line in each diff hunk is an ordered subsequence of the hunk's removed tokens (Python `tokenize`; this allows a shortened import line or a list row cut out of a one-line list, e.g. D17). A script checks this per commit.
2. **Restructure commits** for R1–R7 and the fixture switch of §5.2 (`test_nvda_ready.py`), one per test file.
3. **Rename commits** for the two single-row parametrizes of §5.2 (segment host, lifecycle).
4. **Edit commits** for E1–E5.
5. **Merge commits** for M1, M2 (each: the assertion moves into the kept test, then the source test goes, in that commit or the next) and M3 (the verbatim move and the file deletion, proven by the move comparison).

Each implementation commit carries its own id list (a subset of the final list; the lists partition it) and rename subset. **Per-commit proof:** collect after each commit and run §6.1 with `BASE` = the previous commit's collection, `REMOVED` = that commit's list, `RENAMES` = that commit's renames. For deletion commits the parameters of every surviving test are unchanged by construction; for restructure commits the proof shows the same. Record each result in the progress ledger.

### 6.5 Other checks (DEVELOPMENT_WORKFLOW.md §7)

- `git diff --stat master -- addon` is empty: no change under `addon/` at all in this phase.
- `prek run --all-files`: every hook Passed (ruff pinned `0.16.3`).
- `git diff --check`.
- Protected paths: the two commands of §7 print nothing.
- Repeat the concurrency files 5 times each after the last commit (`tests/test_segment_host.py`, `tests/test_segment_lifecycle.py`, `tests/test_runtime_scheduler.py`, `tests/test_worldvoice_cancel_wrappers.py`, `tests/test_vocalizer_segment_drain.py`): all pass every time.
- Linux only; no Windows or NVDA manual item (nothing user-visible changes).

## 7. Risks and Review Focus candidates

1. **Coverage blind spots of copied files.** Tests that run a copied file (the `install` fixture) look covered but are invisible to coverage (N4). M3 must keep the real-file loader; the per-module gate on `coreArchive.py` and `installTasks.py` checks it. The same reason makes the static union check of N5 a guide only.
2. **Fixture and helper edits change what other tests execute.** The `legacy` fixture stops importing `driver` (§5.7), `test_nvda_ready` switches fixtures, `_driver_methods` loses two names, `CountingToken` loses its delay. A module that was covered only through such a fixture would show up in the per-module gate; the touched files run alone (§6.2).
3. **Order dependence and module-level state.** Deleting the first test of a module can change which test first imports or caches a module (`sys.modules` entries the harnesses pop and reload, e.g. `tests/pipeline_harness.py`, `SCRIPT_LOOKUP`). The full run plus the per-file runs cover both orders that matter.
4. **Hypothesis properties now carry examples that were pinned.** Several deleted examples are subsumed only by properties (disabled switch, empty list, scaled waits, group-size reset, zero waits). The properties are unchanged, run with the existing profiles, and sample those regions (N2); no `@example` is added in this phase (deferred, §5.6). A reviewer may check that each property's strategy reaches the deleted example's region.
5. **Timing-variant cases removed.** `test_retire_waits_for_admitted_consumers[0.1]`, `test_queued_run_does_not_poll_its_token[0.06]` and `test_all_concurrent_stops_finish_before_new_speech[1]` go. The `[0.06]` case pinned the *measurement* race fixed by `7ad23a4` (measure only after the waiter blocks): if `_wait_until_waiting` were ever weakened, the remaining case would turn flaky instead of failing deterministically. The 5× repeat runs (§6.5) are the check now.
6. **Renumbered ids.** `[response5]` becomes `[response4]`, `[changes9-…]` becomes `[changes1-…]`, `[0-False1]`'s sibling becomes `[0-False]`, …; nothing in `pyproject.toml`, `tools/` or `tests/` selects tests by id (checked by grep), but a reader of old notes may be misled. §6.1 prints every pair.
7. **Restructured parametrizations (R1–R7) and `STAGE_ROWS`.** An off-by-one in a rebuilt case list silently drops or duplicates a kept case; §6.1's multiset check catches both.
8. **C1 and N1 are judgement calls** about existence guards (keep the token guard, drop the speech-symbols and ignore-numbers ones); the user may want both handled alike.

## 8. Non-goals

- **Phase 58, the coverage gaps** (audit §4.3 and the groups' 覆蓋缺口), listed for traceability only: `runtime/segmentHost.py:546-547`, `:562-564` (`stop_player` raising when an ordinary record retires or fails), `:637-638` (`lifecycle.run` raising falls back to `reject_new`); `runtime/_segmentLifecycle.py:451-452` (`on_retired` raising), `:514`; RHVoice `RHVoice_new_message` raising (`driver/RHVoice/__init__.py:148-150`) and the submit-failure cleanup (`:319-322`); VE/Cerence output-buffer overflow guard (`driver/VE/__init__.py:271`, `driver/Cerence/__init__.py:271`), the Sonic early feed (`:279-280`), `:288`, queued `getParameter` (VE `:550-557`), `_terminationError` (VE `:883-886`, Cerence `:892-895`); SAPI5 legacy audio Bookmark/index (`driver/SAPI5/__init__.py:328-330`, `:338-340`) and `:153-156`; OneCore `:356-357`; `runtime/requestBuilder.py:39`, `:46`; `bridge/engineAdapter.py` legacy-mode cancel and raise paths (`192->194`, `203->205`, `208->210`); `rolePresenter.setVariant` (`globalPlugins/WorldVoice/rolePresenter.py:85`) and `:145-146`; `panels/detection.py:59-60`; `voices/manager.py:212-213`; `pipeline/context.py:39-40`; and the dead line `engineRegistry/discovery.py:78` (an `addon/` change).
- No change under `addon/`.
- No new tests, except the one assertion moved out of a parametrize (E2) and the assertions moved by M1 and M2.
- The deferred merges and suggestions of §5.6.
- No translation, readme or packaging work (no strings change).

## 9. Constraints (DEVELOPMENT_WORKFLOW.md §8)

- Work only in `/workspace/WorldVoice-phase57`; `ref` there is a git-ignored symlink, never staged. The main checkout is not touched.
- Stage explicit paths only and check `git diff --cached --stat` before each commit; English `<type>: <summary>` messages with a body that says why; no `Co-Authored-By`; prek hooks run, re-stage after a hook fix, never `--no-verify`; no push; never `git stash`.
- Do not touch the inner drivers (`driver/<Engine>/driver/`) or the generated Unicode data; engines stay independently installable; Neural is not added.
- At most one pytest process at a time, with the MemAvailable < 3 GB watchdog that kills only its own process.

## 10. Open questions for the user

None blocks the work. To tell the user, with the defaults taken:

1. C1: the request-token guard (D34, D35) is kept against its leaning, because the audit's other removals rely on it. Override: delete both.
2. N1: the speech-symbols and ignore-numbers "option is gone" checks are deleted as listed; nothing guards those options afterwards.
3. D38, D39: kept until the generic translator guards exist (deferred).
4. §5.6: all merges that are not needed to keep an assertion are deferred, including the one-line existence assertions in kept tests.
