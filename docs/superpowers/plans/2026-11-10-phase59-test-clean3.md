# Phase 59 Test-Clean3 Removals and Merges Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.2 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** Delete the spec's 294 test ids, make the 49 merge rows without losing a path or an assertion, apply the tidy edits T1–T10, and replace the two hand-kept translator lists by two generic catalog checks, ending at 3646 passed, 0 skipped, with no change under `addon/`.

**Architecture:** Test-only work in `tests/`, in the spec's commit order (§10): one deletion commit per audit group (plus the G4 and G7 restructure commits), merge commits per target file, tidy commits per file, then the two translator commits. Every commit is proven by a collection diff (`prove.py`, spec §9.1) against the previous commit's collection; deletion commits also pass a token check that they add nothing. Branch coverage is compared arc by arc against the audit's `cov-before.db` after the deletions, after the merges and at the end.

**Tech Stack:** Python 3, pytest, Hypothesis, coverage.py (ctrace, `--cov-branch`), ruff 0.16.3 via prek.

**Spec:** `docs/superpowers/specs/2026-11-10-phase59-test-clean3-design.md` (spec commit `b48af06`) with its appendix lists `…-remove.txt` (294), `…-merge.txt` (132), `…-decide.txt` (52), `…-coverage-before.txt`. The spec is the authority for every id, row shape and value; this plan says only in which task, commit and order each is done and how it is checked.

## Global Constraints

- No file under `addon/` changes: `git diff --stat master -- addon` stays empty after every commit.
- Removals are exactly `…-remove.txt`; merges replace exactly `…-merge.txt`'s ids; every merged test keeps every path and assertion of the tests it replaces (spec §6 rules); kept ids change only where the spec lists a rename (N5, G1-M2, T1–T9).
- Expected counts (spec §9.2): deletions 3987, 3987, 3971, 3807, 3770, 3742, 3737, **3706**; merges 3691, 3686, 3669, 3664, 3663, 3652, 3652, **3646**; tidy 3646; X1+X2 3648; D10 **3646**; 0 skipped throughout.
- Never edit `addon/synthDrivers/WorldVoice/driver/*/driver/*`, `driver/sonic/`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py` (here: nothing under `addon/` at all). Engine drivers stay independently installable. Never add Neural. Never stage `ref` (a git-ignored symlink).
- ruff pinned `==0.16.3`; commits run prek hooks; when a hook edits files, re-stage and commit again, never `--no-verify`.
- git: work only in `/workspace/WorldVoice-phase59`; stage explicit paths (`git add -f` for new files under `docs/`); check `git diff --cached --stat` before each commit; English `<type>: <summary>` with a body that says why; no `Co-Authored-By`; no push, no merge; never `git stash`; never touch `/workspace/WorldVoice`.
- Tests: at most 3 pytest processes at a time, each through `$SP/run_wd.sh` (watchdog kills only its own pytest and children when MemAvailable < 3 GB; the loop ends with pytest); pytest invoked as `python3 -m pytest tests -q …` (`tests` before `-q`); never `ulimit -v`; never `pkill -f` a pytest pattern.
- Red checks for merges and X1/X2 run on a scratch copy (`rsync -a --exclude=.git` of the worktree into `$SP/redcopy`) or by temporarily breaking an expected value in the worktree that is reverted before staging; never by editing `addon/` in the worktree.
- Deviations: `Ruling: <decision> — <reason> — <cost if wrong>` in the ledger, listed in each report.
- `$SP` = `/tmp/claude-0/-workspace-WorldVoice/9e65e0e5-7706-45c2-8166-5a831b64aee2/scratchpad/p59`; ledger `L` = `.superpowers/sdd/2026-11-10-phase59-test-clean3/` (git-ignored).
- Baseline (`f1bbec0`, spec commit `b48af06`): 3998 passed, 0 skipped; prek all Passed.

## Commit procedure (every commit of Tasks 1–11)

1. `$SP/collect.sh c<NN>` → prints the collected count (must equal the task's expected count).
2. `python3 $SP/prove.py $SP/<previous>.jsonl $SP/c<NN>.jsonl <removed subset> <merges subset> <renames subset>` → last line `PROOF OK`; any `renumbered:` line must be one of spec N5's two pairs.
3. Deletion commits only: `python3 $SP/del_check.py HEAD` → `violations 0`.
4. Run each touched test file on its own (`$SP/run_wd.sh $SP/f-<name>.txt tests/<file> -q -p no:cacheprovider`, ≤3 at a time) → all pass; then the full suite `$SP/run_wd.sh $SP/full-c<NN>.txt tests -q -p no:cacheprovider` → `<count> passed`, no skip.
5. `ruff check tests` clean; `git add <explicit paths>`; `git diff --cached --stat`; commit (prek runs); record sha, count and proof line in `L/progress.md`.

## Review Focus

1. **A merge that keeps the path but drops an assertion** (the arc gate cannot see it): every merge row of Tasks 5–9 that adds assertions gets a red check: temporarily break one added expected value per case (or mutate the code under test in `$SP/redcopy`) and see the merged test fail on that line, then restore — Tasks 5–9, step "Red check".
2. **A kept test that passed only because a deleted or merged test ran before it** (shared module state, fixture order): every touched file runs on its own after each commit — Commit procedure step 4; all touched files again in Task 12.
3. **A concurrency merge that is flaky** (G1-M2, G1-M5, G1-M12, G2-M1, G2-M3, G2-M4): the eleven concurrency files run 5 times each — Task 12 Step 3.
4. **A zh_TW entry that NVDA shows in English** — a blank `msgstr` or a `#, fuzzy` entry (msgfmt drops fuzzy translations): X1 must fail on both — Task 11 `test_every_source_msgid_has_a_zh_tw_translation` red checks.
5. **A translatable string outside the add-on modules or in an unsupported form** — the buildVars changelog `_()` and a `pgettext` call: X1 must name the buildVars location when its msgstr is blank and report the unsupported call — Task 11 red checks.

---

### Task 1: Tooling, ledger, G1 and G2 deletions

**Files:**
- Create (scratch, not committed): `$SP/run_wd.sh`, `$SP/collect_params.py`, `$SP/collect.sh`, `$SP/prove.py`, `$SP/del_check.py`, `$SP/orphans.py`, `$SP/arc_gate.py` (spec §9.3 verbatim), `$SP/report_cmp.py` (spec §9.4)
- Create (ignored): `L/progress.md`, `L/removed-G<n>.txt`, `L/merges.txt`, `L/renames.txt`
- Modify: `tests/test_vocalizer_segment_drain.py`, `tests/test_sapi5_segment_drain.py`, `tests/test_espeak_segment_drain.py`, `tests/test_vocalizer_init_cleanup.py`, `tests/test_wrapper_init_cleanup.py`, `tests/test_playback_work.py`

**Interfaces:**
- Produces: `prove.py BASE.jsonl HEAD.jsonl REMOVED MERGES RENAMES` (spec §9.1 steps 1–5; `MERGES` lines `<row>\t- <id>` / `<row>\t+ <id>` / `<row>\t= <id>`, the last for a kept id whose parameters a merge reshapes, compared by id; `RENAMES` lines `old -> new`; `-` for an empty list); `del_check.py REV [REV2|WT]`; `orphans.py BASE_REV`; `collect.sh NAME` → `$SP/NAME.jsonl`; `L/removed-G<n>.txt` = the remove-list ids of group n (group by file, spec §2 table / audit `groups.txt`).

- [ ] **Step 1: Tooling.** Write the scripts above; `$SP/collect.sh base` at `b48af06` → `3998`; `python3 $SP/prove.py $SP/base.jsonl $SP/base.jsonl - - -` → `PROOF OK`. Split `…-remove.txt` by group into `L/removed-G1.txt` … `G8.txt` (11, 0, 16, 164, 37, 28, 7, 31; G7 includes the two D10 ids, which go to `L/removed-D10.txt` instead: G7 file 5). Start `L/progress.md` with the task list, batch split and the tool commands.
- [ ] **Step 2: G1 deletion** — the 11 ids of `L/removed-G1.txt` (spec §5.1/§5.2; D1's six `*_a_built_core_keeps_*` functions). No knock-on (K-G1a/K-G1b come with G1-M1/G1-M2).
- [ ] **Step 3: Verify and commit** per the commit procedure: count **3987**, proof OK (removed = G1), `del_check` 0 violations; commit `test: delete the duplicate G1 engine drain tests`.
- [ ] **Step 4: G2 deletion** — K-G2a only (`new_work`, `tests/test_playback_work.py:53-59`). Count **3987**, proof OK with empty lists, `del_check` 0; commit `test: delete the unused new_work helper`.

### Task 2: G3 and G4 deletions, G4 restructure

**Files:**
- Delete: `tests/test_f4_engine_session.py`
- Modify: `tests/test_runtime_completion_policies.py`, `tests/test_runtime_composition.py`, `tests/test_runtime_legacy_adapter.py`, `tests/test_pipeline_filters.py`, `tests/test_pipeline_number_edges.py`, `tests/test_pipeline_number_groups.py`, `tests/test_pipeline_punctuation_pause.py`, `tests/test_pipeline_segment_pause.py`, `tests/test_pipeline_unspaced_space.py`

**Interfaces:**
- Consumes: Task 1 tools and lists.

- [ ] **Step 1: G3 deletion** — `L/removed-G3.txt` minus the five `test_disabled_force_switch_restores_legacy_done` ids (11): delete `test_f4_engine_session.py` (D2 + three audit ids, K-G3; `conftest.py`'s `session_module` stays) and the other G3 ids. Count **3976**, proof OK, `del_check` 0; commit `test: delete the duplicate G3 runtime tests`.
- [ ] **Step 2: G3 restructure** — `test_disabled_force_switch_restores_legacy_done` parametrizes over `["OneCore"]` instead of `SIX_ENGINES` (§5.2; id `[OneCore]` kept). `["OneCore"]` is not a token subsequence of `SIX_ENGINES`, so this is its own commit (Ruling: like R1–R3, §10.1). Count **3971**, proof OK (removed = the five other engines' ids); commit `test: run the disabled force switch case for OneCore only`.
- [ ] **Step 3: G4 deletion** — `L/removed-G4.txt` minus the three `*-item0` ids of R2 (161 ids): §5.2 rows and values (number groups `space` values, `["value"]` kept as one-value parametrize, the five `mode, size, column` rows, `test_number_mode` tables, `ROWS`/`SPACED_ROWS` rows, `value-size3`), D3 function, K-G4a (`Marker`, `MARKER`, `NB0`), K-G4b (`CallbackCommand`, `marked_plain_break`). `shape()`'s `else` branch stays (§5.4). `python3 $SP/orphans.py HEAD` → nothing beyond K-G4a/b.
- [ ] **Step 4: Verify and commit** — count **3810**, proof OK (removed = the 161), `del_check` 0; commit `test: delete the redundant G4 number and pause cases`.
- [ ] **Step 5: G4 restructure** — R2 (three explicit `ITEM_ROWS`-derived rows `end-value-item0`, `end-none-item0`, `whole-numbers-value-item0`, same sequences/options/expected) and R3 (`spoken(row[column])`; delete `pieces_in`, `digit_by_digit`, K-G4c). Run `tests/test_pipeline_filters.py` and `tests/test_pipeline_number_edges.py` before the change and record the kept ids' params from `c<NN>.jsonl`; after: same ids, same params.
- [ ] **Step 6: Verify and commit** — count **3807**, proof OK (removed = the three `*-item0` ids); commit `test: write out the kept number edge rows and drop pieces_in`.

### Task 3: G5 and G6 deletions

**Files:**
- Modify: `tests/test_pipeline_nvda_ssml.py`, `tests/test_pipeline_settings_service.py`, `tests/test_pipeline_stages.py`, `tests/test_text_preprocessing.py`, `tests/test_worldvoice_speak.py`, `tests/test_panel_layout.py`, `tests/test_settings_panels.py`, `tests/test_settings_table_guard.py`, `tests/test_ui_controls.py`, `tests/test_voice_settings_panel.py`

**Interfaces:**
- Consumes: Task 1 tools and lists.

- [ ] **Step 1: G5 deletion** — `L/removed-G5.txt` (37), including D4–D8 (§3: delete the D5 `number` row, D6 `number-pause` `pytest.param`, D7 rows `en-x`/`en-han2`/`zh-han2`, D8 rows `full-width-paren`/`paren-han`). Orphan scan clean.
- [ ] **Step 2: Verify and commit** — count **3770**, proof OK, `del_check` 0; commit `test: delete the redundant G5 stage, settings and speak cases`.
- [ ] **Step 3: G6 deletion** — `L/removed-G6.txt` (28), including D9; §5.2 `test_the_number_mode_controls_no_other_setting` keeps only `"none"`, `test_pipeline_panel_group_size_is_enabled_for_every_stored_mode` keeps `none`, `group`. K-G6a/K-G6b come with G6-M2/G6-M1. Orphan scan clean.
- [ ] **Step 4: Verify and commit** — count **3742**, proof OK, `del_check` 0; commit `test: delete the redundant G6 panel cases`.

### Task 4: G7 and G8 deletions, R1, deletion-stage coverage gate

**Files:**
- Modify: `tests/test_generate_unspaced_common.py`, `tests/test_native_strategy_guards.py`, `tests/test_plugin_voice_contract.py`, `tests/test_engine_discovery.py`, `tests/test_engine_filter.py`, `tests/test_language_detector.py`, `tests/test_voice_settings_repository.py`

**Interfaces:**
- Consumes: Task 1 tools; `$SP/../cov-before.db`.
- Produces: `$SP/p59-deleted.db` and the deletion-stage gate result in the ledger.

- [ ] **Step 1: G7 deletion** — `test_check_versions_needs_one_unicode_version`, `test_leased_player_reaches_played_out_by_default`, D11 with K-G7a (`pre_rename_names`, `importlib`, `ROOT`, `Path`; re-check `ast`, `composition`, `stub_modules` by grep). Count **3739**, proof OK (3 ids), `del_check` 0; commit `test: delete the redundant G7 guard tests`.
- [ ] **Step 2: R1** — one `@pytest.mark.parametrize(("name", "option", "error"), […])` with the spec's two rows; ids `[ScriptExtensions.txt---source-error0]`, `[UnicodeData.txt---unicode-data-error1]` unchanged. Count **3737**, proof OK (removed = `…-error1` of ScriptExtensions and `…-error0` of UnicodeData); commit `test: pair each network error with one download`.
- [ ] **Step 3: G8 deletion** — `L/removed-G8.txt` (31): language detector rows (§5.2 list incl. D14–D16; `test_decimal_digits_follow_the_letter_rule_of_their_script` left with one row — T7 inlines it later), `test_engine_discovery.py` two rows (K-G8a waits for G8-M1), `test_engine_filter.py`, `test_voice_settings_repository.py` (N5). Orphan scan clean.
- [ ] **Step 4: Verify and commit** — count **3706**, proof OK, `renumbered:` exactly the two N5 pairs, `del_check` 0; commit `test: delete the redundant G8 detection and registry cases`.
- [ ] **Step 5: Deletion-stage proof and coverage gate.** `prove.py $SP/base.jsonl $SP/c<last>.jsonl L/removed-all-but-D10.txt - -` → OK, 292 removed, two N5 pairs. Full run `COVERAGE_FILE=$SP/p59-deleted.db $SP/run_wd.sh $SP/p59-deleted-cov.txt tests -q -p no:cacheprovider --cov=addon --cov-branch --cov-report=term`; `python3 $SP/arc_gate.py $SP/../cov-before.db $SP/p59-deleted.db` → exit 0, `unexpected lost: []`, and all three `ALLOWED_LOST` arcs listed under "allowed lost not lost" (their merge sources still exist). `report_cmp.py` against `…-coverage-before.txt` → failures 0. Record in ledger. **End of batch 1 (Tasks 1–4): stop and report.**

### Task 5: G1 merges

**Files:**
- Modify: `tests/test_engine_segment_contract.py` (G1-M1, G1-M2, K-G1a), `tests/test_espeak_segment_drain.py` (G1-M2 source, G1-M3, K-G1b), `tests/test_onecore_segment_drain.py` (G1-M2 `[False]` inline, M5, M6, M11, M12), `tests/test_vocalizer_segment_drain.py` (M4, M8, M9, M10), `tests/test_sapi5_segment_drain.py` (M7, M13)

**Interfaces:**
- Consumes: `tests/engine_contract_harness.py` (`Events.wait_one`, adapters' `close`).
- Produces: new tests `test_engine_done_needs_the_last_native_call_to_end[<engine>-every-call-ends|last-call-unended|middle-call-unended]`, `test_a_segment_is_at_most_one_native_call[<engine>-long|transformed|emptied]`, `test_zero_audio_segments_still_wait_for_real_idle[<engine>-blank]`, `test_a_player_failure_fails_only_its_segment[sync|idle]`, `test_a_cancelled_late_feed_is_stopped_before_its_successor[segment|legacy_after_segment]`, `test_end_stream_waits_for_actual_idle[speech|empty]`; rename `test_onecore_rejected_segment_uses_async_lifecycle_delivery[False]` → plain (in `L/renames.txt`).

- [ ] **Step 1: Merge commits, one per target file**, in the order contract (M1, M2 + K-G1a/K-G1b + OneCore `[False]` inline), eSpeak (M3), OneCore (M5, M6, M11, M12), Vocalizer (M4, M8, M9, M10), SAPI5 (M7, M13), each with the spec §6.1 row's exact shape and values. Before deleting each source, run the merged test green with the source still present. G1-M2: read every adapter's `close` in `tests/engine_contract_harness.py`; if any does not call `terminate` again, add `engine.terminate()` twice in the contract test (Ruling). G1-M6: **run** `[index-only]` with `env.player.idles == 1`; assert for both rows only if it holds (record the outcome).
- [ ] **Step 2: Red check per row** (Review Focus 1): break one added expected value per case — M1 `events.on_delivery_thread == [False]`; M2 the error text (`"x driver has terminated"`) for each engine; M3 `"code -2"`; M4 a changed `fed`; M5 `opened == [False]`; M6 `idles == 2`; M7 `segment_id == 18`; M8 `drained` flipped per case; M9 `expected` of `emptied` → `[""]`; M10 `calls == [""]` for `blank`; M11 `"x failed"`; M12 `base` off by one; M13 `indexes` of `speech` → `[8]` — see the failure, restore, re-run green. Record per row in the ledger.
- [ ] **Step 3: Verify each commit** — ledger lines `G1-M<k>\t- …`/`+ …` (the `- ` lines equal `…-merge.txt`'s G1 rows); proof per commit; counts: contract **3698** (M1 −6, M2 −2), eSpeak **3696** (M3), OneCore **3694** (M5, M6, M11, M12), Vocalizer **3692** (M4, M8, M9, M10), SAPI5 **3691** (M7, M13).
- [ ] **Step 4: Commit messages** `test: fold the <file> drain duplicates into <target>` with a body naming the rows and the kept assertions.

### Task 6: G2 merges

**Files:**
- Modify: `tests/test_rhvoice_segment_drain.py` (M1), `tests/test_worldvoice_cancel_wrappers.py` (M2), `tests/test_runtime_drain_integration.py` (M3), `tests/test_segment_host.py` (M4 + K-G2b, M5, M6), `tests/test_playback_work.py` (M7), `tests/test_runtime_segment_completion.py` (M8a–c)

**Interfaces:**
- Produces: `break_boundary_hook(env, monkeypatch) -> None` in `tests/test_segment_host.py` (patches `env.host.wait_native_boundary` with the former `broken(operation)` closure through the given `monkeypatch`); new tests `test_terminal_sink_can_terminate_from_the_delivery_thread`, `test_control_error_fails_an_unpublished_drain[lands|lost]`, `test_ordinary_enqueue_raises_without_submitting[control_error|terminated|submit_error]` (explicit ids), `test_owner_is_notified_after_releasing_the_work_lock[cancel|fail|complete_drained]`, `test_completion_waits_for_speak_return_and_rejects_late_index[END_INDEX-SEGMENT_END|DRAIN-SEGMENT_DRAINED]`, `test_duplicate_completion_cannot_advance_next_segment[…]`, `test_drain_does_not_override_failure_or_cancellation[END_INDEX-speak_error]`; the three kept ids of `test_drain_does_not_override_failure_or_cancellation` go as `G2-M8c\t= <id>` lines (their params gain `mode`).

- [ ] **Step 1: Merge commits, one per file**, spec §6.2 shapes. **Run before committing:** G2-M6 (all three causes, incl. `env.strategy.submitted == []` for `submit_error`) and G2-M7 (all three finishes) — if an assertion does not hold, stop and record (it would be a product finding, not a test edit).
- [ ] **Step 2: Red checks** — M1 `errors == ["x"]`; M2 `stops == 2`; M3 drain `segment_id` +1; M4 `faulted is True` after reset; M5 `"stop failedx"` for both cases; M6 `match` per cause; M7 `published` +1 per case; M8a/b/c the kind per mode. Record.
- [ ] **Step 3: Verify** — proof per commit; counts: RHVoice **3690**, cancel wrappers **3688**, drain integration **3687**, segment host **3686**, playback work **3686**, segment completion **3686**.

### Task 7: G3 and G4 merges

**Files:**
- Modify: `tests/test_runtime_legacy_adapter.py` (M1), `tests/test_runtime_completion_policies.py` (M2, M3), `tests/test_f4_engine_adapters.py` (M4), `tests/test_runtime_session.py` (M5), `tests/test_pipeline_pause_properties.py` (G4-M1, G4-M2), `tests/test_pipeline_filters.py` (G4-M3)

**Interfaces:**
- Produces: `AUDIO_MODES: dict[str, tuple[tuple[str, bool], ...]]` in `tests/test_runtime_completion_policies.py` (spec G3-M2 values verbatim); `test_property_the_number_split`; `test_property_a_size_convert_keeps_or_resets[group_size|segment_length]`; the 10-row `test_an_unnamed_symbol_is_left_to_the_punctuation_stage` table.

- [ ] **Step 1: G3-M1 first, TDD-style:** add the ten `@example`s and the two N4 assertions (`adapter.core is core` in `reopen`; `core.__dict__["voice"] == voice` after each apply); **run** the property (Hypothesis default + the examples). If the stored-voice assertion fails on a case none of the replaced tests covers, restrict it to `failed and expect_voice` and record a Ruling. Red check: change one example's expected voice write → the property fails on that example. Then delete the ten source ids; commit.
- [ ] **Step 2: G3-M2..M5** per spec §6.3, one commit per file (completion policies M2+M3, adapters M4, session M5); red checks: M2 one `AUDIO_MODES` flag flipped; M3 reason text; M4 `"Renamed:y"`; M5 `is not first_context`.
- [ ] **Step 3: Verify** — counts: legacy adapter **3676**, completion policies **3672**, adapters **3670**, session **3669**.
- [ ] **Step 4: G4-M1, G4-M2** (one commit, pause properties): the six groups under one `@given`, the leftover-text group last inside an `if`; red check: break one assertion in the first and one in the last group (e.g. negate a comparison) → Hypothesis fails. G4-M2 parametrize; red check: wrong default for `segment_length`.
- [ ] **Step 5: G4-M3** — **run** the eight value/none rows with `scaled_punctuation_wait = 50` first; if a row's expectation changes, keep that row's own waits as a column (Ruling). Red check: one `expected` per mode altered.
- [ ] **Step 6: Verify** — counts: pause properties **3664**, filters **3664**.

### Task 8: G5 and G6 merges

**Files:**
- Modify: `tests/test_pipeline_stages.py` (G5-M1, M2), `tests/test_pipeline_settings_service.py` (M3), `tests/test_worldvoice_pipeline_settings.py` (M4), `tests/test_pipeline_panels.py` (M5), `tests/test_settings_panels.py` (G6-M1 target, M2 source + K-G6a, M3, M4), `tests/test_role_panel_ui.py` (G6-M1 source, K-G6b), `tests/test_settings_table_guard.py` (M2 target), `tests/test_settings_order.py` (M5), `tests/test_settings_panel_save.py` (M6)

**Interfaces:**
- Produces: `test_a_number_switch_logs_its_number_stages[mode|language]`, `test_number_language_and_number_wait_pause_between_numbers[space|no-break-space]`, `test_a_size_confspec_is_its_range[group_size|segment_length]`, `test_an_old_or_unknown_number_mode_is_stored_and_read_as_value[pair|group]`, `test_pipeline_panel_keeps_the_stored_choice_when_nothing_is_selected[mode|scope]`; `AFTER` table in `tests/test_settings_panels.py`.

- [ ] **Step 1: G5 merge commits, one per file**, spec §6.5. Red checks: M1 `pairs` +1; M2 the `NB` wait; M3 the confspec string per key; M4 stored value `"group"`; M5 one title misspelt in `titles` (the `<=` must fail). Counts: stages, settings service, pipeline settings **3664**; panels **3663**.
- [ ] **Step 2: G6 merge commits, one per target file**, spec §6.6. G6-M1 keeps the role.py and detection.py arcs (N3: `postInit`, `onDiscard`, `onSave`); G6-M2 also moves any source assertion not in `test_pipeline_panel_group_size_stays_enabled_after_every_mode_choice`. Red checks: M1 `env.shown == ["x"]`; M2 an extra `"group"` in the expected list; M3 the ticked state flipped; M4 the stored value; M5 `(5, env.wx.BOTTOM)`; M6 `"settings"` for `"engine"`. Counts: settings panels (M1, M3, M4) **3658**, table guard (M2) **3657**, settings order (M5) **3653**, panel save (M6) **3652**. **End of batch 2 (Tasks 5–8): stop and report.**

### Task 9: G7 and G8 merges, merge-stage coverage gate

**Files:**
- Modify: `tests/test_generate_unspaced_common.py` (G7-M1), `tests/test_nvda_ready.py` (M2, M3), `tests/test_generated_unicode_data.py` (M4), `tests/test_engine_discovery.py` (G8-M1 + K-G8a), `tests/test_voice_settings_repository.py` (M2), `tests/test_global_plugin_menu.py` (M3 target, M4), `tests/test_core_install.py` (M3 source + K-G8b), `tests/test_voice_catalog.py` (M5)
- Delete: `tests/test_global_plugin_lifecycle.py` (K-G8c)

**Interfaces:**
- Produces: `GENERATED` table and `test_generated_file_is_the_generators_output[script_data|unspaced_common_data]`, `test_other_line_endings_in_a_generated_file_are_caught[…]`; `test_a_downloaded_file_must_match_its_checksum[ScriptExtensions.txt|UnicodeData.txt]`; `test_ready_skips_with_one_warning_when_a_name_is_missing[<engine>-module|class]`; `test_sapi5_uses_nvdas_driver_with_one_info_line_when_a_name_is_missing[module|class]`; `test_a_dead_menu_runtime_error_does_not_stop_cleanup`; `test_empty_catalog_is_empty`.

- [ ] **Step 1: G7 merge commits**, spec §6.7. G7-M4 red check is mandatory (protected-data guard strength): in `$SP/redcopy`, change one byte of `unicodeScripts/script_data.py` and of `unspaced_common_data.py` → the matching case fails; and a CRLF line ending in each → the line-ending case fails. Other red checks: M1 digest per case; M2/M3 the message per kind. Count **3652**.
- [ ] **Step 2: G8 merge commits**, spec §6.8 (G8-M3 `BadZipFile("bad archive")`; G8-M4 (a) and (b) in `tests/test_global_plugin_menu.py`, then delete `tests/test_global_plugin_lifecycle.py`). Red checks: M1 one message text; M2 `"pitch": "60"`; M4(a) order of `("unpatch",), ("detach",)` swapped; M4(b) `item.destroyed is True`; M5 one field. Counts: discovery **3650**, repository **3649**, core install → menu (M3) **3648**, menu (M4) **3647**, catalog **3646**.
- [ ] **Step 3: Merge-stage proof and gate.** `prove.py $SP/c<last-deletion>.jsonl $SP/c<last>.jsonl - L/merges.txt L/renames.txt` → OK (132 olds, 72 news, nets per row). Coverage run `COVERAGE_FILE=$SP/p59-merged.db …`; `arc_gate.py cov-before.db p59-merged.db` → exit 0, lost exactly the three `ALLOWED_LOST` arcs (plus `TIMING` noise only); `report_cmp.py` failures 0. Orphan scan over `HEAD` vs Task 4's last commit: nothing new.

### Task 10: Tidy edits T1–T10

**Files:**
- Modify: `tests/test_generate_unicode_scripts.py` (T1), `tests/test_generate_unspaced_common.py` (T2, T3), `tests/test_hygiene_guards.py` (T4), `tests/test_engine_discovery.py` (T5), `tests/test_engine_filter.py` (T6), `tests/test_language_detector.py` (T7), `tests/test_ui_controls.py` (T8), `tests/test_panel_layout.py` (T9), `tests/test_vocalizer_segment_drain.py`, `tests/test_onecore_segment_drain.py`, `tests/test_sapi5_segment_drain.py`, `tests/test_espeak_segment_drain.py` (T10)

**Interfaces:**
- Produces: the renames of spec §7 in `L/renames.txt` (T1, T2 exact strings, T3, T5–T9).

- [ ] **Step 1: One commit per file**, spec §7 (T10 the four `synthDriverClass is …` lines, one commit; T8 inlines every value, drops no statement). For each one-row parametrize dropped, record `old -> new` in `L/renames.txt`; `prove.py` accepts the rename only if the new params are a sub-dict of the old.
- [ ] **Step 2: Verify** — every commit count **3646**, proof OK; grep that no file in `pyproject.toml`, `tools/`, `tests/` selects a renamed id (spec §11 item 7).

### Task 11: Translator checks X1, X2, then D10

**Files:**
- Modify: `tests/test_translator_comments.py`

**Interfaces:**
- Produces: `_source_msgids() -> tuple[dict[str, list[str]], list[str]]` (msgid → `relative:lineno` locations; unsupported call locations), sources = `_translated_modules()` + root `buildVars.py`; `test_every_source_msgid_has_a_zh_tw_translation`; `test_the_zh_tw_catalog_has_no_unused_entry`.

- [ ] **Step 1: Write X1 and X2** (spec §8):

```python
def test_every_source_msgid_has_a_zh_tw_translation():
	source, unsupported = _source_msgids()
	catalog = _catalog(ZH_TW_CATALOG)
	assert unsupported == []
	assert {msgid: locations for msgid, locations in source.items() if not catalog.get(msgid)} == {}


def test_the_zh_tw_catalog_has_no_unused_entry():
	source, _unsupported = _source_msgids()
	assert sorted(set(_catalog(ZH_TW_CATALOG)) - set(source)) == []
```

Review Focus 4: `_catalog` maps a `#, fuzzy` entry's msgstr to `""` (msgfmt drops fuzzy translations, so NVDA would show English) — Ruling (spec §8 says nothing about fuzzy; X2 still sees the msgid). Update the module docstring (spec §8).
- [ ] **Step 2: Red checks in `$SP/redcopy`** (spec §8 + Review Focus 4–5), each run as `python3 -m pytest tests/test_translator_comments.py -q` in the copy: (a) blank the msgstr of an add-on string → X1 fails naming it and its `module:line`; (b) blank the buildVars changelog msgstr → X1 fails naming `buildVars.py:29`; (c) mark one entry `#, fuzzy` → X1 fails naming it; (d) add an unused entry → X2 fails naming it; (e) add `pgettext("ctx", "x")` to a translated module → X1 fails with that location in `unsupported`. Green in the worktree: 90 + source msgids from buildVars, 92 catalog entries.
- [ ] **Step 3: Commit X1+X2** — count **3648**, proof OK with `L/merges.txt` lines `X\t+ <id>` for the two new ids (`prove.py` `NETS["X"] = 2`); commit `test: check the zh_TW catalog against every source string`.
- [ ] **Step 4: D10 + K-G7b** — delete `test_changed_label_strings_have_translator_comments`, `test_zh_tw_catalog_follows_the_labels`, `CHANGED_LABEL_MSGIDS`, `DEAD_MSGIDS`, `_gettext_calls` (with their comments); `ZH_TW_CATALOG`, `_catalog`, `re` stay. Count **3646**, proof OK (removed = `L/removed-D10.txt`), `del_check` 0; commit `test: drop the hand-kept translator label lists`.

### Task 12: Final gates

**Files:** none changed (ledger only).

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Whole-branch proof.** `prove.py $SP/base.jsonl $SP/final.jsonl <full remove list> L/merges.txt L/renames.txt` (`L/merges.txt` includes the two `X` additions) → `PROOF OK`, `renumbered:` exactly spec N5's two pairs; `del_check` per deletion commit re-run from `git log`.
- [ ] **Step 2: Coverage gate** (spec §9.3/§9.4): `COVERAGE_FILE=$SP/p59-after.db $SP/run_wd.sh $SP/p59-coverage.txt tests -q -p no:cacheprovider --cov=addon --cov-branch --cov-report=term`; `arc_gate.py cov-before.db p59-after.db` → exit 0, lost exactly the three `ALLOWED_LOST` arcs; `report_cmp.py` → 0 failures (TOTAL 8625 stmts / 2472 branches). Any other lost arc: fix the merge, never extend the allow-list.
- [ ] **Step 3: Isolation and repeats.** Every file touched on the branch run on its own (≤3 at a time) → all pass; the eleven concurrency files of spec §9.2 × 5 each → all pass every time.
- [ ] **Step 4: DEVELOPMENT_WORKFLOW §7.** `python3 -m pytest tests -q` → **3646 passed**, 0 skipped; `prek run --all-files` → all Passed; `git diff --check master` clean; the two protected-path commands print nothing; `git diff --stat master -- addon/` empty.
- [ ] **Step 5: Report** — commit range, counts, prek, protected paths, arc-gate printout, every `Ruling:`, anything unverified (Linux only; no Windows/NVDA item).

## Batches

12 tasks → 4/4/4: batch 1 Tasks 1–4 (deletions), batch 2 Tasks 5–8 (G1–G6 merges), batch 3 Tasks 9–12 (G7–G8 merges, tidy, translator, final gates). Stop and report after batches 1 and 2.
