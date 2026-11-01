# Number mode and grouping as independent settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** Make the number mode (off, value, number) and the group size (0 = no grouping, 1..2147483647) two independent settings: the group size cuts every number into pieces in every mode, the mode renders each piece, edge pauses follow the group size, and two numbers never run together.

**Architecture:** Core pipeline only. `pipeline/numbers.py` gets two pure steps (cut, render) behind the unchanged `number_pieces` signature; `pipeline/numberStages.py` drops its per-mode branches (pass-through, edges and the gap break now read the group size) and adds the number + group 0 break between numbers in two items (spec §4.3 G2, O2); `pipeline/settings.py` drops the "group" choice and gives `group_size` the range 0..2**31-1, default 0, no dependency. Panels, synth and engine wrappers read the table and change no code. Docs: the number paragraphs of the six readmes.

**Tech Stack:** Python 3.14 venv on Windows, pytest, Hypothesis, prek (ruff `==0.16.3`), NVDA stubs of `tests/` (`pipeline_harness.py`, `nvda_stubs.py`).

**Spec:** `docs/superpowers/specs/2026-11-01-feat-number-group-independent-design.md` (commit `274b8eb6`). The worked examples (§3.2, §5 i1–i30), the pieces table (§9.2), the properties (§9.3) and the doc wording (§6.4) are in the spec; this plan names the tests, the files, the order and the checks, and does not repeat the tables.

## Global Constraints

- Worktree `D:/NVDA/NVDA_development/WorldVoice-number-group`, branch `feat/number-group-independent`. The main checkout `D:/NVDA/NVDA_development/WorldVoice` is never touched. `ref/` is a git-ignored folder of junctions: never staged, never modified.
- Python `D:/NVDA/NVDA_development/.venv-worldvoice/Scripts/python.exe`; full run `<python> -m pytest -q -p no:cacheprovider tests`, one process, no parallel workers.
- Baseline (master `65856d26` + spec `274b8eb6`): **3375 passed, 9 failed, 1 skipped**. The 9 failures are all in `tests/test_generated_unicode_data.py` (Windows line endings) and stay exactly those 9 after every task; the 1 skip stays.
- Spec decisions U1–U10 (user) and O1–O8 (orchestrator defaults) are implemented as written; the spec is not edited. A deviation is a ledger line `Ruling: <decision> — <reason> — <cost if wrong>`. A user-visible question the spec does not answer stops the work and is reported.
- Never edit `driver/<Engine>/driver/`, `driver/sonic/`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py`; never add Neural. Engine drivers stay independently installable (no driver imports another; shared code only in core). No engine wrapper changes on this branch.
- `pipeline/numbers.py` stays standard-library only.
- No `_()` string is added or changed (O5); the "group" msgid stays in every `.po` (O6). The 7.0 changelog sections of all readmes are not touched (U9); no new changelog section (O7).
- Tabs; ruff pinned `==0.16.3`. prek only as `prek.exe run --files <files>` (never `--all-files`); a hook that rewrites a file → re-stage, re-commit, never `--no-verify`. If the hook says `prek: not found`, put `/d/NVDA/NVDA_development/.venv-worldvoice/Scripts` first on PATH.
- git: stage explicit paths; `git diff --cached --stat` before each commit; English `<type>: <summary>` with a why body; no `Co-Authored-By`; no push, no merge; never `git stash`. Line-ending-only "M" entries with an empty `git diff` are noise and never staged. `docs/` files are added with `git add -f`.
- Ledger: `.superpowers/sdd/2026-11-01-feat-number-group-independent/progress.md` (ignored): task, commit, red evidence, green evidence, full-suite counts, Rulings.
- mutmut is Linux-only and is not run here (O8); the report says so.

## Review Focus

Inputs the spec does not single out that are most likely to hurt an NVDA user:

1. **A table read cell by cell in number mode with group 0** (`["10", "20"]`, `["10", M, "20"]`, an `IndexCommand` or a language command between two number cells, an `EndUtteranceCommand` between them). The user expects two cells never to sound like one number, and no pause across an utterance end. → Task 4 `test_number_mode_without_groups_keeps_numbers_in_two_items_apart` (rows i16–i18, i29, i30 and the G2 list of spec §9.2) and Task 5 `test_property_two_numbers_never_share_a_run` (P-U5).
2. **Whitespace other than a plain space between two numbers** (no-break space, ideographic space, two spaces) in every mode with group 0 and 3. The user expects one pause, and number mode's own joining spaces never split. → Task 3 `test_numbers_that_only_whitespace_separates_get_one_break` and Task 5 P-U5.
3. **A huge or invalid stored group size** (`3000000000`, `-1`, `abc`, `3.5`, 2147483647 itself) in nvda.ini or typed in the spin. The user expects WorldVoice to load, read 0 for invalid values, and a number to stay whole with size 2147483647. → Task 2 `test_group_size_outside_its_range_reads_as_the_default`, `test_a_refused_stored_group_size_reads_as_zero`, `test_every_spin_fits_a_wx_spin_control`, and Task 1 pieces row `123` / 2147483647.
4. **An old profile with `numberMode = group`** (with and without `groupSize`). The user expects the panels to open on "value" and the ring never to meet an unknown mode. → Task 2 `test_a_stored_group_mode_reads_as_value`, `test_synth_nummod_group_stores_value`, `test_available_nummods_match_number_modes`.
5. **Off mode with a group size above 0, and symbols without an NVDA name** (`"5×3"`, `"1.,2"`, a lone `"."` piece reaching the punctuation stage). The user expects nothing lost or doubled. → Task 1 pieces rows `1.,2`, `5×3`; Task 3 row i3/i7 and `test_an_unnamed_symbol_is_left_to_the_punctuation_stage` with none + size; Task 5 P-none.

---

## Running counts

Counts are passed / failed / skipped of the full run; the failed 9 and skipped 1 never change. Passed counts are planned from the tests each task adds or removes; a different count caused only by a parametrization choice is recorded in the ledger (not a Ruling), any other difference is investigated.

| After | Passed (planned) |
|---|---|
| baseline | 3375 |
| Task 1 | 3375 + n1 (new tests of `test_pipeline_number_groups.py`) |
| Task 2 | previous + n2 (settings, guard, panel rows added − rows of the removed "group" cases) |
| Task 3 | previous + n3 |
| Task 4 | previous + n4 |
| Task 5 | previous + n5 |
| Task 6 | unchanged (docs only) |

The ledger records the exact n of each task when its tests are written (before the run), and the run must match it.

---

### Task 1: Cut and render helpers (`numbers.py`)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/numbers.py`
- Create: `tests/test_pipeline_number_groups.py`

**Interfaces:**
- Consumes: `NUMBER_TOKEN_RE`, `NUMBER_RE`, `SYMBOLS` (`numbers.py:11-24`); `symbol_name` from `tests/pipeline_harness.py`.
- Produces: `group_pieces(raw: str, group_size: int) -> list[str]` and `render_piece(piece: str, mode: str, name_of: Callable[[str], str | None]) -> str` in `numbers.py`. `number_pieces` is unchanged in this task (Task 3 rewires it).

- [ ] **Step 1: Tests (red).** In `tests/test_pipeline_number_groups.py`, loading `numbers.py` through the pipeline harness:
  - `test_group_pieces_cuts_digit_runs_and_symbols` — parametrized over the raw/size pairs of spec §9.2 "Pieces": assert `group_pieces(raw, size)` equals the "none" column (the cut).
  - `test_group_pieces_of_size_zero_is_the_whole_match` — `group_pieces("1,234.5", 0) == ["1,234.5"]`, `group_pieces("-12", -1) == ["-12"]`.
  - `test_render_piece_by_mode` — rows: (`"123"`, none → `"123"`), (`"."`, none → `"."`), (`"."`, value → `N(".")`), (`"×"`, value → `"×"` with a namer returning None), (`"-123"`, number → `"-1 2 3"`), (`"12.5"`, number → `f"1 2 {N('.')} 5"`), (`"12.5"`, value → `"12.5"`), (`"１２３"`, number → `"１ ２ ３"`).
  - `test_property_cut_pieces_join_back_and_hold_at_most_n_digits` (P-G1, spec §9.3) over `st.from_regex(NUMBER_RE, fullmatch=True)` and `st.integers(1, 12)`; size 0 gives `[raw]`.
  - `test_property_render_keeps_the_digits_and_names_the_symbols` (P-G2) over the same strategy and the three modes, with `read_back_names`.
  - Expected red: `AttributeError: module ... has no attribute 'group_pieces'` (and `render_piece`) for every test.
- [ ] **Step 2: Code (green).** Add `group_pieces` and `render_piece` in `numbers.py` as spec §4.1 steps 1 and 2 describe (docstrings cite U1/U2, decided by the user, 2026-11-01). A symbol piece is a piece with no decimal digit. Number rendering: the tokens of the piece (`NUMBER_TOKEN_RE`), each digit apart with the sign on the first digit (O3), each symbol by `name_of(s) or s`, joined with single spaces.
- [ ] **Step 3: Verify.** `pytest -q tests/test_pipeline_number_groups.py` → all pass. Full run → **3375 + n1 passed, 9 failed, 1 skipped**. `prek.exe run --files` on the two files → Passed.
- [ ] **Step 4: Commit** `feat: add the cut and render steps of a number's pieces` (body: the two pure steps the independent group size needs; `number_pieces` keeps its meaning until the stage is rewired).

### Task 2: Settings: no "group" mode, group size 0..2**31-1, always enabled

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/settings.py` (`NUMBER_MODE_CHOICES`, `group_size` entry, a `SPIN_MAX` constant)
- Test (update + add): `tests/test_pipeline_settings_service.py`, `tests/test_settings_table_guard.py`, `tests/test_worldvoice_pipeline_settings.py`, `tests/test_settings_panels.py`, `tests/test_voice_settings_panel.py`, `tests/test_ui_controls.py`, `tests/test_panel_layout.py`, `tests/test_pipeline_panels.py`, and any other test that pins the old table (found by the red run).

**Interfaces:**
- Consumes: `PipelineSettingSpec`, `read_stored`, `convert` (`settings.py:85-136`, `:362-382`).
- Produces: `NUMBER_MODES == ("none", "value", "number")`; `PIPELINE_SETTING_BY_KEY["group_size"]` with `default=0, min_value=0, max_value=SPIN_MAX (2**31 - 1), reset_out_of_range=True, control="spin", depends_on=None, driver_id=None`; confspec `integer(default=0,min=0,max=2147483647)`. Consumed by Task 3 (the stage reads `settings.group_size`, which can now be 0).

- [ ] **Step 1: Tests (red).** Update or add:
  - `test_number_mode_choices_put_off_first`: choices are off, value, number. `test_table_lists_every_setting_in_the_canonical_order`: `NUMBER_MODES == ("none", "value", "number")`.
  - `test_group_size_confspec_is_its_range`: `(min, max, default, reset) == (0, 2147483647, 0, True)`, confspec `integer(default=0,min=0,max=2147483647)`.
  - `test_group_size_outside_its_range_reads_as_the_default`: 0, 1, 2147483647, `"7"` keep; -1, 2147483648 → 0.
  - `test_a_refused_stored_group_size_reads_as_zero`: stored `-1` (too small), `abc`, `3.5` (type error), `2147483648` (too big) refused by the stub section → `read_stored` gives 0, one warning each.
  - `test_a_stored_group_mode_reads_as_value` (service) and the existing number-mode read/write rows: "group" → "value".
  - `test_synth_nummod_group_stores_value` and `test_available_nummods_match_number_modes` (`tests/test_worldvoice_pipeline_settings.py`).
  - Guards (`tests/test_settings_table_guard.py`): `test_group_size_is_an_independent_panel_only_spin` (no `depends_on`, no `driver_id`, min 0, max `2**31 - 1`, default 0), `test_no_entry_depends_on_the_number_mode`, `test_every_spin_fits_a_wx_spin_control` (every `control="spin"` entry has `max_value <= 2**31 - 1`; a table copy with `max_value=2**31` fails the check); the mutation rows "default below the bounds" use `default=-1` and "default above the bounds" `default=2**31`; rows that used `("number_mode", "group")` as a dependency use another valid dependency.
  - Panels: `test_pipeline_panel_group_size_is_enabled_for_every_stored_mode` and `test_pipeline_panel_group_size_stays_enabled_after_every_mode_choice` (replace the enable/disable tests, `tests/test_settings_panels.py:125-170`), the same pair in `tests/test_voice_settings_panel.py:294-350`; spin range `(0, 2147483647)`; out-of-range typed sizes -1 and 2147483648 save 0; stored `-1` shows 0 and a save writes 0; `test_pipeline_panel_binds_only_the_controllers` binds only the punctuation switch; `tests/test_panel_layout.py` controller keys only `punctuation_pause_enabled`; `tests/test_ui_controls.py` dependency tests use the punctuation dependents.
  - Stored fixtures with `numberMode="group"` become `"value"` (or keep "group" where the test is about reading it as value); fixtures relying on the old default 3 use 0.
  - Expected red: the updated assertions fail on the old table (4 choices, default 3, range 1..10, spin disabled outside "group").
- [ ] **Step 2: Code (green).** In `settings.py`: drop `("group", _("group"))` and its translator comment; add `SPIN_MAX = 2**31 - 1` with a comment citing spec F4 (largest value a wx `SpinCtrl` holds); `group_size` entry `0`, `min_value=0`, `max_value=SPIN_MAX`, no `depends_on`; rewrite the two comments as spec §4.4 says. No other module changes (panels and synth read the table).
- [ ] **Step 3: Verify.** The touched test files alone → pass. Full run → **previous + n2 passed, 9 failed, 1 skipped**. Pipeline tests are unaffected (their stand-in settings carry their own `group_size`; mode "group" is still understood by the stage until Task 3). prek on touched files → Passed.
- [ ] **Step 4: Commit** `feat: make the group size an independent 0..2**31-1 setting` (body: U1, U6, U7, O4; why the max is the wx spin limit; "group" reads as value).

### Task 3: The number stage groups in every mode; edges follow the group size

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/numbers.py` (`number_pieces`), `addon/synthDrivers/WorldVoice/pipeline/numberStages.py` (`_translate_number`, `inject_numbers`, `_inject_item_numbers`, `_number_item_segments`, `number_wait_factor` docstring), `addon/synthDrivers/WorldVoice/pipeline/breaks.py` (docstrings, spec §4.6)
- Test (update + add): `tests/test_pipeline_number_edges.py`, `tests/test_pipeline_number_edge_properties.py`, `tests/test_pipeline_filters.py`, `tests/test_pipeline_pause_properties.py`, `tests/pipeline_harness.py:244`, `tests/test_worldvoice_speak.py:346`, `tests/test_pipeline_unspaced_space.py:184`, `tests/test_pipeline_stages.py`, `tests/test_pipeline_nvda_ssml.py`, `tests/test_pipeline_passthrough.py`, `tests/test_pipeline_number_groups.py`.

**Interfaces:**
- Consumes: `group_pieces`, `render_piece` (Task 1); `settings.group_size` (Task 2, may be 0).
- Produces: `number_pieces(raw, mode, group_size, name_of)` = `[render_piece(p, mode, name_of) for p in group_pieces(raw, group_size)]`; `_translate_number` yields the pieces with one `NumberBreakCommand(number_pause)` instance between each two at any pause (O1); `inject_numbers` passes through only for none + group 0 + no wrapper, adds edges only for `group_size > 0 and pause > 0`, and for number + group 0 + pause > 0 runs the list path with `edges = (None, NumberBreakCommand(pause), None)` (Task 4 fills the third); `_number_item_segments` puts `gap_break` where `gap_break is not None` and renders every number through `_translate_number`.

- [ ] **Step 1: Tests (red).**
  - `tests/test_pipeline_number_edges.py`: add rows i1–i15, i19–i28 of spec §5 to `ROWS` (stage and full run; i16–i18, i29, i30 wait for Task 4); move the existing rows per spec §9.1 (value/none rows get `"size": 0`, "group" rows become value + size, `o4-range` becomes number+3 `"5"`, NB, N("-"), NB, `"3"` and a new `o4-range-0` keeps `f"5 {N('-')} 3"`); `SPACED_ROWS` and `test_no_break_at_all_in_number_mode_without_a_number_pause` run at number+0 with the expectations of spec §3.2 (no edges); `test_off_mode_with_a_locale_keeps_the_dots_as_they_are` passes size 0; `test_no_edge_break_without_a_number_pause` uses value + size 2.
  - `tests/test_pipeline_number_groups.py`: `test_number_pieces_by_mode_and_size` (the full table of spec §9.2 "Pieces", all three columns); `test_off_without_groups_or_wrapper_is_the_identity` (same objects returned, `is`); `test_off_with_a_group_size_runs_the_stage` (`"1234"` none+3 → `"123"`, NB, `"4"`); `test_value_without_groups_does_not_depend_on_the_pause` (pause 0 vs 10, same shape); `test_edges_appear_iff_a_group_and_a_pause` (each mode × size {0, 3} × pause {0, 10} on `"第123章"`); `test_numbers_that_only_whitespace_separates_get_one_break` (`"10 20"`, `"10\u00a020"`, `"10\u300020"` × three modes × size {0, 3}, after every stage exactly one break between the two numbers); `test_thousands_then_groups` (`"1,234,567"` → `"123"`, NB, `"456"`, NB, `"7"`; `"12,345.678"` value+3 → `"123"`, NB, `"45"`, NB, N("."), NB, `"678"`; `"1,23"` value+3 → `"1"`, NB, N(","), NB, `"23"`).
  - `tests/test_pipeline_filters.py`: the number-mode tables of spec §9.1 replace mode "group" by value + size and pass size 0 where no grouping is meant; add none + size and number + size cases to `test_number_mode` and to `test_an_unnamed_symbol_is_left_to_the_punctuation_stage`.
  - Properties (`tests/test_pipeline_number_edge_properties.py`, `tests/test_pipeline_pause_properties.py`): `MODES` = the three modes; properties that drew `SPACED_MODES` draw all three modes with sizes 1–10; `test_property_no_edge_outside_digit_and_group_modes` becomes `test_property_no_edge_without_a_group_or_a_pause` (P-U4 first half); `test_property_one_break_between_numbers` counts pieces − 1 for every number when size > 0, in every mode; `run_group_mode`/`MODE_SIZES`/`GROUP_SIZES` run value + size; `test_property_off_mode_is_the_identity_for_the_thousands_and_number_stages` uses `group_size=0`; `test_property_every_symbol_is_its_own_item_when_some_have_no_name` runs every mode with size ≥ 1.
  - Stand-in defaults (`pipeline_harness.py:244`, `test_worldvoice_speak.py:346`, `test_pipeline_unspaced_space.py:184`) become `group_size=0`; `test_number_mode_edges_with_detection` runs with group 3 and gains group-0 rows; `test_value_mode_has_no_edges_with_detection` pins value + group 0.
  - Expected red: the new rows fail (value/none + 3 not cut, no edges for value + 3, number + 0 still has edges, `number_pieces` table columns differ), the stand-in default change breaks nothing by itself in value mode.
- [ ] **Step 2: Code (green).** `number_pieces` per spec §4.1 (docstring rewritten, §11 list); `_translate_number` per §4.2 (join branch removed); `inject_numbers` per §4.3 "Pass-through" and "Edges", plus the number + group 0 list path with `(None, NumberBreakCommand(pause), None)`; `_number_item_segments`: gap condition `gap_break is not None`, "none" branch removed; every comment and docstring of spec §11's last bullet rewritten (`stages:118-120`, `:235-240`, `:263-265`, `:288-290`); `breaks.py` docstrings per §4.6 (the item-edge sentence of §4.6 is added in Task 4).
- [ ] **Step 3: Verify.** `pytest -q tests/test_pipeline_number_edges.py tests/test_pipeline_number_groups.py tests/test_pipeline_filters.py tests/test_pipeline_number_edge_properties.py tests/test_pipeline_pause_properties.py` → pass. Full run → **previous + n3 passed, 9 failed, 1 skipped**. prek on touched files → Passed.
- [ ] **Step 4: Commit** `feat: group numbers in every number mode and tie edge pauses to the group size` (body: U2, U3, U4, U5 G1, O1, O3; number + group 0 has no edges).

### Task 4: Number + group 0 keeps a break between numbers in two items (G2, O2)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/numberStages.py` (`inject_numbers`, `_inject_item_numbers`), `addon/synthDrivers/WorldVoice/pipeline/breaks.py` (`NumberItemEdgeBreakCommand` docstring)
- Test: `tests/test_pipeline_number_edges.py`, `tests/test_pipeline_number_groups.py`

**Interfaces:**
- Consumes: Task 3's number + group 0 list path; `_split_numbers_for_language`, `_is_spoken`, `_ends_utterance`.
- Produces: for number + group 0 + pause > 0, `edges = (None, NumberBreakCommand(pause), NumberItemEdgeBreakCommand(pause))`; `_inject_item_numbers` passes `edge_after` only when the next spoken item of the utterance starts with a number, and `edge_before` only when the previous spoken item of the utterance ended with one. A helper `_next_spoken_starts_with_number(speech_sequence: list) -> list[bool]` (reverse pass, reset at an utterance end) and a forward flag `previous_ends_with_number`.

- [ ] **Step 1: Tests (red).**
  - `tests/test_pipeline_number_edges.py`: rows i16, i17, i18, i29, i30 of spec §5 in `ROWS` (stage and full run).
  - `tests/test_pipeline_number_groups.py`: `test_number_mode_without_groups_keeps_numbers_in_two_items_apart` (spec §9.2 G2 list: `["10", "20"]`, `["10", M, "20"]`, `["10", " ", "20"]`, `["10", L(en), "20"]` → exactly one break between the two numbers after every stage; `["10", EU, "20"]` → none; `["第1", "2章"]` → one break between 1 and 2, none next to 第 or 章; `["第1", "章"]` → none) and `test_number_mode_without_groups_takes_the_longer_item_pause` (i17: item 30 → `"1 0"`, B30, `"2 0"`).
  - Expected red: `["10", "20"]` number+0 gives `"1 0"`, `"2 0"` with no break (Task 3 state, the spec F1 gap).
- [ ] **Step 2: Code (green).** As spec §4.3 "Implementation of the group-0 number row". The existing `spoken_kinds[:1] == ["number"]` / `[-1:]` checks in `_number_item_segments` still decide the item's own side.
- [ ] **Step 3: Verify.** The two files → pass; the edge-property file → pass. Full run → **previous + n4 passed, 9 failed, 1 skipped**. prek → Passed.
- [ ] **Step 4: Commit** `feat: keep a pause between numbers of two items in digit mode without groups` (body: O2, F1, why the item-edge class keeps the longer item pause).

### Task 5: Properties of the independent group size (spec §9.3)

**Files:**
- Test: `tests/test_pipeline_number_groups.py` (new properties), `tests/test_pipeline_number_edge_properties.py`, `tests/test_pipeline_pause_properties.py` (replaced properties)

**Interfaces:**
- Consumes: Tasks 1–4. Produces: nothing for later tasks.

- [ ] **Step 1: Tests.** `test_property_lone_number_is_its_pieces_with_one_break_between_each_two` (P-G3, replaces `test_property_groups_are_separate_items_of_the_chosen_size` and `test_property_breaks_and_names_stay_inside_numbers`); `test_property_no_edge_next_to_text_without_a_group` (P-U4 second half: number + group 0 edge-class breaks have a number on both sides); `test_property_two_numbers_never_share_a_run` (P-U5, the prototype's check: numbers of 1–7 digits joined by a space, two spaces, a no-break space, an ideographic space or an item boundary; every mode, group 0–10, item wait {0, 10, 30}, number language default/main/en, wait 1–60; after every stage no break-free run holds two source numbers, and with group 0 every run is one whole source number); `test_property_value_groups_after_the_thousands_step` (P-U3); `test_property_off_with_groups_keeps_every_character` (P-none second half); `test_property_group_size_convert_keeps_or_resets` rewritten as P-S (`st.integers()`; and `read_stored` of `str(v)` for v < 0 gives 0).
  - Expected: green at once (the code is in place); red is proven per property by a scratch mutation in a temporary worktree under the scratchpad (P-U5: Task 4's G2 code removed → fails on `["10", "20"]`; P-G3: one `NumberBreakCommand` per piece pair replaced by none at pause 0 → fails; P-U3: `remove_thousands_separators` disabled → fails), recorded in the ledger. No `git stash`.
- [ ] **Step 2: Verify.** The three files → pass (default profile). Full run → **previous + n5 passed, 9 failed, 1 skipped**. prek → Passed.
- [ ] **Step 3: Commit** `test: pin the independent group size with Hypothesis properties`.

### Task 6: User guide (U9)

**Files:**
- Modify: `readme.md`, `addon/doc/ru/readme.md`, `addon/doc/uk/readme.md`, `addon/doc/zh_CN/readme.md`, `addon/doc/zh_HK/readme.md`, `addon/doc/zh_TW/readme.md`

**Interfaces:** none.

- [ ] **Step 1:** Replace the "Number mode" bullet with its sub-bullets and the "Number wait factor" bullet with the spec §6.4 text (en, zh_TW verbatim); ru, uk, zh_CN, zh_HK translated to match, keeping each file's existing terms (mode names, panel names, the wait factor's name) and indentation. The 7.0 changelog sections are not touched.
- [ ] **Step 2: Verify.** `git diff master -- readme.md addon/doc` touches only those two bullets per file; full run → Task 5 count unchanged (doc tests, if any, pass); prek on the six files → Passed.
- [ ] **Step 3: Commit** `docs: describe the group size as independent of the number mode`.

### Task 7: Final verification (no code)

- [ ] Full run → the Task 6 count passed, the same 9 failed, 1 skipped; any difference from 3375 explained by the tests added and removed.
- [ ] `prek.exe run --files $(git diff --name-only master...HEAD)` → all Passed.
- [ ] `git diff --check master...HEAD` → no output.
- [ ] Protected paths (workflow §7): `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py addon/synthDrivers/WorldVoice/unicodeScripts/unspaced_common_data.py` and `git ls-files addon/synthDrivers/WorldVoice/driver/Neural` → both empty.
- [ ] `git diff master...HEAD -- addon/locale` → empty (O6); `grep -rn '"group"' addon/synthDrivers/WorldVoice/pipeline` → only the "group" read-as-value comment, if any.
- [ ] Report: tasks, commits, red/green per task, counts, prek, diff --check, protected paths, Rulings, unverified items (Windows NVDA M1–M7, real synths, wx 4.3.2 spin limits, mutmut not run).

---

## Self-Review

- **Spec coverage:** U1 (Tasks 2, 3), U2 (Tasks 1, 3), U3 (Task 3 `test_thousands_then_groups`, Task 5 P-U3), U4 (Task 3 edges, Task 5 P-U4), U5 (Task 3 G1, Task 4 G2, Task 5 P-U5), U6 (Task 2), U7 (Task 2, no migration code), U8 (Task 3 value/none + 0 rows unchanged, dot rule untouched), U9 (Task 6), U10 (coordinator, not this plan). O1 (Task 3 pause-0 rows i24, i25), O2 (Task 4), O3 (Task 1 render, Task 3 i8), O4 (Task 2), O5/O6 (no `.po` edit, Task 7 check), O7 (no changelog), O8 (report). §9.1 updates (Tasks 2, 3), §9.2 (Tasks 1–4), §9.3 (Tasks 1, 3, 5), §9.5 manual items listed as unverified.
- **Steps explicit:** every task names its files, tests, expected red and the full-run counts; code steps give signatures and spec sections, not bodies.
- **Types consistent:** `group_pieces(str, int) -> list[str]`, `render_piece(str, str, Callable) -> str`, `number_pieces` signature unchanged; `edges` stays a 3-tuple with `None` allowed in the first and third slot.
- **Review Focus:** 5 items, each mapped to named tests of Tasks 1–5.
- **Proportion:** the two behavioural tasks (3, 4) carry most of the test work; settings and docs are mechanical.
