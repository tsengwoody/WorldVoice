# Number Edge Pause Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** In the number (digit) and group modes, with a number pause above 0, put the number pause before and after every number that has other text of its own item next to it, by merging the number-language and number-mode stages into one number stage, and keep the punctuation pause and every existing pause rule intact.

**Architecture:** One new stage `inject_numbers` replaces `inject_number_language` and `inject_number_mode` in `STAGES`; per item, `_number_item_segments` walks `_split_numbers_for_language` and yields, per number, left edge, opening wrapper, pieces, closing wrapper, right edge, with a whitespace gap between two numbers replaced by one gap `NumberBreakCommand`. Edge breaks are `NumberEdgeBreakCommand(NumberBreakCommand)`; the punctuation stage gains two edge-only rules (E1: an edge does not suppress a boundary pause; E2: `_merge_edge_breaks` keeps the longest break of a run that holds an edge), and other synths' plain breaks carry the attribute `worldvoice_number_edge` so E1/E2 work in scope "all". Logging keeps both switches through `Stage.also_logged_by`.

**Tech Stack:** Python 3.14.4, pytest 9.1.1, Hypothesis 6.168.5, mutmut 3.8.0, ruff 0.16.3 via prek 0.4.14.

**Spec:** `docs/superpowers/specs/2026-10-24-feat-number-edge-pause-design.md` (commit `bce7eb9`). U1–U5 are the user's decisions; O1–O6 and D1–D10 apply as written. `pipeline:<n>` = `addon/synthDrivers/WorldVoice/pipeline/__init__.py:<n>` on `8612c3d`. "§5 row N" means the row of the spec's worked-examples table.

## Global Constraints

- Edge pauses only when `settings.number_mode in ("number", "group")` and `settings.scaled_number_wait() > 0` (U1, U4). Value mode and "none" never get one, at any pause; their output is today's except D5's spacing.
- Pause time = `settings.scaled_number_wait()`; no new setting, no confspec change, no translatable string change (U2, §6, §7).
- Spans come from `_split_numbers_for_language` (`NUMBER_RE` + hyphen rule) in every mode (U5, O4). `pipeline/numbers.py`, `pipeline/symbols.py`, `number_wait_factor`, `split_spaced_numbers`, `_insert_number_breaks`, `_remove_space`, `remove_thousands_separators`, `wrap_numbers_for_detection`, `detect_with_number_language` and `languageDetection/` are untouched (§2.3).
- Edge-break position: outside the wrapper (O1); none at an item's start or end or before only whitespace up to it (O2, D1); a whitespace gap (`str.isspace()`, no-break space included) between two numbers becomes one plain `NumberBreakCommand` gap break and no edges (O3, D6). One edge instance and one gap instance per stage run (D10).
- Punctuation stage: E1 and E2 exactly as spec §4.6.3, keep rule "longest; tie → first non-edge; all edges → first". Runs with no edge break are untouched; every existing punctuation test passes unchanged.
- D3 marker attribute name: `worldvoice_number_edge`, value `True`, set only on plain breaks made from edge breaks (or from already-marked plain breaks).
- D4: `STAGES` number stage is `Stage("number_mode", inject_numbers, also_logged_by=("number_language",))`; `LOG_SWITCHES` stays `("apply_speech_dictionaries", "number_language", "number_mode", "chinesespace_wait_factor", "item_wait_factor", "punctuation_wait_factor", "number_wait_factor", "speech_viewer")`; log rows are labelled `"number_mode"`.
- Readmes: only `readme.md` and `addon/doc/zh_TW/readme.md`, with the exact texts of spec §6. `buildVars.py` is never touched (the user has an uncommitted edit in the main checkout).
- Never modify `addon/synthDrivers/WorldVoice/driver/<Engine>/driver/`, `driver/sonic/` or `languageDetection/script_data.py`. Engine drivers stay independently installable (no driver imports another driver's package; shared code only in core). Never add Neural back. ruff pinned `==0.16.3`.
- Style: tabs, the surrounding comment density and docstring tone; record decisions as "decided by the user (2026-10-24)" where the code records one.
- git: stage explicit paths only; `git diff --cached --stat` before each commit; English `<type>: <summary>` messages with a body that says why; no `Co-Authored-By`; commits run prek; if a hook rewrites files, restage and recommit; never `--no-verify`, `git stash` or push; never touch `/workspace/WorldVoice`; never stage `ref`. `docs/` is git-ignored: stage the plan with `git add -f`.
- Full suite: `<scratch>/guard.sh python3 -m pytest -q -p no:cacheprovider tests`, one process; the guard kills the run when MemAvailable < 3 GB. mutmut: `--max-children 3` under the same guard. `<scratch>` = `/tmp/claude-0/-workspace-WorldVoice/552d4b5b-ba04-48a7-a26d-68b1a2360464/scratchpad`.
- Baseline on `8612c3d`: **2610 passed, 0 skipped**. Every count below is "passed, 0 skipped". Each task ends with: full suite, `prek run --all-files` all Passed, `git diff --check master`, and both protected-path commands of `DEVELOPMENT_WORKFLOW.md` §7 printing nothing.

## Review Focus

1. **One break instance shared across runs.** The stage shares one edge instance and one punctuation-break instance across the whole sequence, so E2 must decide by position, never by identity: `["a", E10, PB50, "b", E10, "c"]` with the same `E10` object twice must keep `PB50` in the first run and `E10` in the second. Task 2, `test_merge_edge_breaks[shared-instance]`.
2. **The edge marker across several stage handlers (scope "all").** `_plain_breaks` runs after every stage, so a marked plain break would lose its marker after the first stage that re-plains it, and the punctuation stage would see an unmarked break. Re-plaining must keep the marker. Task 3, `test_plain_breaks_mark_only_edge_breaks` (second assertion).
3. **A long item full of short numbers at pause > 0** (a spreadsheet row, `"a1 " * 5000`, number mode). The content check per side must not rescan the item per number (the spec's `item[:start].strip()` is quadratic as written); the whole of `STAGES` must finish in under 2 s. Task 5, `test_a_long_item_of_numbers_stays_linear`.
4. **Blank items and items that are only a number with whitespace** (`""`, `" "`, `"　"`, `" 3 "`) in number mode at pause 10. No edge break, no gap break, today's output (an empty item disappears). Task 5, `test_no_edge_break_at_an_item_end_or_before_only_whitespace[blank-*]`.
5. **A space listed as a punctuation pause character** next to an edge (`"共 3 章"`, characters `" "`, removal off and on). The space becomes a pause point right where the edge break is; the listener must hear one pause there, the longer one, never two. Task 6, `test_a_space_pause_character_meets_an_edge_break[remove-off|remove-on]`.

---

### Task 1: A stage can log under several switches

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (`_run_logged` pipeline:811-829, `_stage_handler` :841-853, `Stage` :856-871, `LOG_SWITCHES` :888-889)
- Test: `tests/test_pipeline_stages.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Stage(log_key, fn, log_switch=True, also_logged_by: tuple[str, ...] = ())`; `_run_logged(label, fn, speechSequence, settings, ctx, switches: tuple[str, ...] | None = None)` (switches default `(label,)`; logs when debug or recording, and any switch on; rows labelled *label*); `_stage_handler(log_key, fn, switches: tuple[str, ...])`; `_log_switches(stages: Iterable[Stage]) -> tuple[str, ...]`; `LOG_SWITCHES = _log_switches(STAGES)`.

- [ ] **Step 1: Write the failing tests** in `tests/test_pipeline_stages.py`:
  - `test_a_stage_logs_under_each_of_its_switches`, parametrized `on` over `[(), ("number_language",), ("number_mode",), ("number_language", "number_mode")]`, ids `none, other-only, own-only, both`: log conf `{"enable": True, **dict.fromkeys(LOG_SWITCH_ORDER, False), **dict.fromkeys(on, True)}`; `stage = module.Stage("number_mode", lambda sequence, s, ctx: list(sequence), also_logged_by=("number_language",))`; `stage.handler(["a"])`; `assert writes == ([] if not on else [("number_mode", "before"), ("number_mode", "after")])`.
  - `test_log_switches_list_each_key_once_in_stage_order`: with `f = lambda sequence, s, ctx: sequence`, `assert module._log_switches((Stage("a", f), Stage("b", f, log_switch=False, also_logged_by=("x",)), Stage("c", f, also_logged_by=("a", "d")), Stage("c", f))) == ("a", "d", "c")`.
  - `test_the_log_confspec_has_every_log_switch`: `from nvda_stubs import worldvoice_conf`; `assert set(module.LOG_SWITCHES) <= set(worldvoice_conf()["WorldVoice"]["log"])` (a guard for Task 4's stub change).
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_pipeline_stages.py`. Expected red: the four `test_a_stage_logs_under_each_of_its_switches` cases fail with `TypeError: ... unexpected keyword argument 'also_logged_by'`, `test_log_switches_list_each_key_once_in_stage_order` with `AttributeError: ... '_log_switches'`; the confspec guard passes.
- [ ] **Step 3: Implement** the Produces signatures. `Stage.__post_init__` passes `(*self.also_logged_by, self.log_key)` to `_stage_handler`; `_log_switches` keeps, for each stage with `log_switch`, its `also_logged_by` keys then its `log_key`, each key once in first-seen order. Comment on `also_logged_by`: the switches that also turn this stage's log on.
- [ ] **Step 4: Run** the file again: all green. Full suite: **2616 passed, 0 skipped** (2610 + 6).
- [ ] **Step 5: Commit** `tests/test_pipeline_stages.py addon/synthDrivers/WorldVoice/pipeline/__init__.py` — `feat: let a pipeline stage log under more than one switch`.

### Task 2: Edge breaks and the punctuation rules E1 and E2

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (new class after pipeline:35-36; `inject_punctuation_pause` :549-678 and its docstring)
- Test: `tests/test_pipeline_punctuation_pause.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `class NumberEdgeBreakCommand(NumberBreakCommand)` with docstring "Pause between a number and the text next to it in its item (number and group modes)."; `_EDGE_MARKER = "worldvoice_number_edge"`; `_is_edge_break(command: SpeechCmd) -> bool` (a `NumberEdgeBreakCommand`, or any `BreakCommand` whose `_EDGE_MARKER` attribute is true); `_merge_edge_breaks(speechSequence: Iterable[SpeechCmd]) -> Iterator[SpeechCmd]`.

Notation in this task's tests: `E10 = module.NumberEdgeBreakCommand(10)`, `NB10 = module.NumberBreakCommand(10)`, `PB50 = module.PunctuationBreakCommand(50)`; expected shapes use `shape()` of the test file (`(type name, time)`). Settings: `punctuation_settings(wait, remove_characters=remove)` with `punctuation_pause_characters = "。，."`.

- [ ] **Step 1: Write the failing tests.**
  - `test_an_edge_break_keeps_the_punctuation_pause` parametrized `(sequence, remove, wait, expected)`, ids in brackets; `E` = `("NumberEdgeBreakCommand", 10)`, `NB` = `("NumberBreakCommand", 10)`, `P(t)` = `("PunctuationBreakCommand", t)`:
    - `[第3。-off]` `["第", E10, "3", E10, "。"]`, off, 50 → `["第", E, "3", E, "。"]`; `[第3。-on]` the same with removal → the same.
    - `[第3。下一章-off]` `["第", E10, "3", E10, "。下一章"]`, off, 50 → `["第", E, "3", E, "。", P(50), "下一章"]`; `[-on]` → `["第", E, "3", P(50), "下一章"]` (this is the final `emit`, spec E2 coverage).
    - `[3，下-off]` `["3", E10, "，下"]` → `["3", E, "，", P(50), "下"]`; `[-on]` → `["3", P(50), "下"]`.
    - `[Total-off]` `["Total. ", E10, "1", NB10, "2"]` → `["Total", ".", " ", P(50), "1", NB, "2"]`; `[-on]` → `["Total", " ", P(50), "1", NB, "2"]`.
    - `[1，2-off]` `["1", E10, "，", E10, "2"]` → `["1", E, "，", P(50), "2"]`; `[-on]` → `["1", P(50), "2"]`.
    - `[第3。下一章-on-wait0]` wait 0, removal → `["第", E, "3", E, "下一章"]`; `[Total-off-wait0]` → `["Total", ".", " ", E, "1", NB, "2"]`.
    - `[tie]` `["a.", module.NumberEdgeBreakCommand(50), "b"]`, off, 50 → `["a", ".", P(50), "b"]`.
  - `test_merge_edge_breaks` parametrized over `module._merge_edge_breaks(sequence)` with `lang = module.WVLangChangeCommand("en")`, `marker` a plain object, comparing by identity (`result == [...]` of the same objects):
    - `[transparent]` `["a", E10, lang, marker, PB50, "b"]` → `["a", lang, marker, PB50, "b"]`;
    - `[no-edge]` `["a", NB10, PB50, "b"]` → unchanged;
    - `[blank-text]` `["a", E10, " ", PB0, "b"]` → `["a", E10, " ", "b"]`;
    - `[end]` `["a", E10, E20]` → `["a", E20]`;
    - `[start-tie]` `[E10, PB10, "a"]` → `[PB10, "a"]`;
    - `[edges-tie]` `["a", E10, E10b, "b"]` (two instances) → `["a", E10, "b"]`, `result[1] is E10`;
    - `[shared-instance]` (Review Focus 1) `["a", E10, PB50, "b", E10, "c"]` with one `E10` object → `["a", PB50, "b", E10, "c"]`.
  - `test_is_edge_break`: true for `NumberEdgeBreakCommand(10)`; false for `NumberBreakCommand(10)`, `PunctuationBreakCommand(10)` and a plain `BreakCommand(10)`; true for a plain `BreakCommand(10)` after `setattr(b, "worldvoice_number_edge", True)`.
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_pipeline_punctuation_pause.py`. Expected red: every new case errors with `AttributeError: ... 'NumberEdgeBreakCommand'` (or `'_merge_edge_breaks'`, `'_is_edge_break'`); the existing cases pass.
- [ ] **Step 3: Implement.** E1: the boundary-pause argument of the loop's `emit` becomes `text_follows and all(_is_edge_break(b) for b in pending_breaks)`. E2: move today's loop (from `it = iter(...)` to the final `yield from pending_breaks`) into an inner generator and `yield from _merge_edge_breaks(<inner>())` after the early returns. `_merge_edge_breaks` buffers a run (everything that is not non-blank text) and, when the run holds two or more `BreakCommand`s and at least one edge break, keeps only the break at index `max(break_indices, key=lambda i: (run[i].time, not _is_edge_break(run[i])))` (`max` keeps the first of equal keys). Docstrings: `inject_punctuation_pause` gains two bullets for E1 and E2; `NumberBreakCommand` gains "and between two numbers that only whitespace separates, in number and group modes".
- [ ] **Step 4: Run** the file: green. Full suite: **2637 passed, 0 skipped** (2616 + 13 + 7 + 1).
- [ ] **Step 5: Commit** `tests/test_pipeline_punctuation_pause.py addon/synthDrivers/WorldVoice/pipeline/__init__.py` — `feat: keep the punctuation pause next to a number edge break`.

### Task 3: Other synths' plain breaks remember an edge (D3)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (`_plain_breaks` pipeline:832-838)
- Test: `tests/test_pipeline_stages.py`, `tests/test_pipeline_nvda_ssml.py`

**Interfaces:**
- Consumes: `NumberEdgeBreakCommand`, `_EDGE_MARKER`, `_is_edge_break` (Task 2).
- Produces: `_plain_breaks(speechSequence) -> list[SpeechCmd]`, each `BreakCommand` subclass a plain `BreakCommand(item.time)`, with `worldvoice_number_edge = True` set when `_is_edge_break(item)`.

- [ ] **Step 1: Write the failing tests.**
  - `test_plain_breaks_mark_only_edge_breaks` (test_pipeline_stages.py): `result = module._plain_breaks([E10, NB10, PB20, BreakCommand(5), "x"])`; every break has `type(item) is BreakCommand`; `[getattr(b, "worldvoice_number_edge", False) for b in result[:4]] == [True, False, False, False]`; Review Focus 2: `module._plain_breaks(result)` gives the same marker list.
  - `test_another_synth_keeps_the_punctuation_pause_next_to_an_edge` (test_pipeline_stages.py), parametrized `[total]`: `["Total. ", E10, "1", NB10, "2"]`, removal off → shape `["Total", ".", " ", ("BreakCommand", 50), "1", ("BreakCommand", 10), "2"]`; `[3，下-remove]`: `["3", E10, "，下"]`, removal on → `["3", ("BreakCommand", 50), "下"]`. Run as another synth: `current_context` → `GENERIC_CONTEXT`, settings `punctuation_settings(50, remove)` with characters `"。，."`; `sequence = module._plain_breaks(sequence)`, then the handler of the `punctuation_wait_factor` stage of `STAGES`.
  - `test_nvda_break_command_has_no_slots` (test_pipeline_nvda_ssml.py): skip without `ref/nvda/source/speech/commands.py`; parse it with `ast`; starting at class `BreakCommand`, follow each base that is a class defined in that file; assert none of them assigns `__slots__` in its body.
- [ ] **Step 2: Run** both files. Expected red: `test_plain_breaks_mark_only_edge_breaks` (`[False, False, False, False]`) and both `test_another_synth_...` cases (the unmarked plain break suppresses the pause: `("BreakCommand", 10)` where 50 is expected); the AST guard passes.
- [ ] **Step 3: Implement** `_plain_breaks` per Produces; its docstring says why the marker exists (the punctuation stage tells edges apart by it; NVDA's `BreakCommand` has no `__slots__` and its `__eq__` reads only type and time, so engines never see it).
- [ ] **Step 4: Run** both files: green. Full suite: **2641 passed, 0 skipped** (2637 + 4).
- [ ] **Step 5: Commit** `tests/test_pipeline_stages.py tests/test_pipeline_nvda_ssml.py addon/synthDrivers/WorldVoice/pipeline/__init__.py` — `feat: mark the plain breaks other synths get for number edges`.

### Task 4: One number stage, `inject_numbers` (no edge breaks yet)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (remove pipeline:253-319 and :411-471; add `inject_numbers`, `_number_item_segments`; `STAGES` :875-885)
- Modify: `tests/nvda_stubs.py:103-118`, `tests/pipeline_harness.py:161-172` (`ORDER`)
- Modify (rename calls, update expectations): `tests/test_pipeline_filters.py`, `tests/test_pipeline_passthrough.py`, `tests/test_pipeline_pause_properties.py`, `tests/test_pipeline_stages.py`, `tests/test_worldvoice_speak.py`

**Interfaces:**
- Consumes: `Stage(..., also_logged_by=...)` (Task 1).
- Produces: `inject_numbers(speechSequence, settings, ctx) -> Iterator[SpeechCmd]` (spec §4.2 steps 1–7); `_number_item_segments(item: str, *, mode: str, group_size: int, pause: int, name_of: Callable[[str], str | None], number_language: str | None, language: str | None, edge: SpeechCmd | None, gap_break: SpeechCmd | None) -> Iterator[SpeechCmd]` (spec §4.2; `number_language` is the wrapper language or `None` when not wrapping). In this task `inject_numbers` passes `edge=None, gap_break=None`.

- [ ] **Step 1: Rename and update tests.** Every call of `inject_number_mode` / `inject_number_language` in the five test files becomes `inject_numbers` (spec §8.1). Then:
  - `test_main_number_language_passes_through_the_early_stage`: `assert result == ["a1b2", items[1], "3"]` and `result[1] is items[1]` (equality, spec §8.1).
  - delete `test_number_segments_with_main_wrap_in_the_current_language`.
  - `test_number_language_leaves_a_sign_after_a_word_with_it`: `inject_numbers(["a-1 中+2 -3"], env.settings, ctx(env.module, {"en": "A:en", "de": "A:de"}, english))` (value mode, number language de) gives the same shape list as today.
  - `tests/pipeline_harness.py` `ORDER`: drop `"number_language"`.
  - `test_numbers_without_detection[locale-next]`: `(EN, ".")` → `(EN, " .")` (D5).
  - rename `test_property_off_mode_is_the_identity_for_both_number_stages` → `..._for_the_thousands_and_number_stages`; drop the M5 sentences from P8's docstring (`test_pipeline_pause_properties.py:744-747`), keeping "It ignores whitespace and runs with the punctuation pause off."
  - New, `test_pipeline_stages.py`: `test_the_number_language_switch_logs_the_number_stage`, parametrized `[language-only]` (switches `number_language` on) → `writes == [("number_mode", "before"), ("number_mode", "after")]`, `[both]` (`number_language` and `number_mode` on) → the pair twice; run `["12,345"]` through every handler as `test_number_mode_switch_logs_both_number_mode_stages` does.
  - New, `test_pipeline_filters.py`: `test_the_dot_rule_reads_the_item_text_with_a_wrapper`, `roles_context(env.module, "zh_TW", "en")`, `["12. Next"]`: `[value]` → `[("lang", "en"), "12", ("lang", "zh_TW"), " . Next"]`; `[number-pause-0]` (number mode, wait 0) → `[("lang", "en"), "1", ("NumberBreakCommand", 0), "2", ("lang", "zh_TW"), " . Next"]`.
  - New, `test_pipeline_filters.py`: `test_off_mode_wraps_only_for_a_locale`, mode `"none"`, `roles_context(env.module, "zh_TW", numlan)`, `["第3章"]`: `[default]` and `[main]` → the result is the input list's own objects (`len == 1 and result[0] is sequence[0]`); `[en]` → `["第", ("lang", "en"), "3", ("lang", "zh_TW"), "章"]`.
- [ ] **Step 2: Run** `python3 -m pytest -q tests`. Expected red: every renamed call fails with `AttributeError: ... 'inject_numbers'`, plus `test_stages_order_and_log_keys`, the D5 speak row and the new tests.
- [ ] **Step 3: Implement** `inject_numbers` and `_number_item_segments` (spec §4.2–§4.5) and remove the five old functions (§4.9). `STAGES` gets `Stage("number_mode", inject_numbers, also_logged_by=("number_language",))` in place of the two stages. Left/right content is decided from the neighbouring text part (`parts[i - 1][1].strip()` / `parts[i + 1][1].strip()`), never by slicing the item (Review Focus 3). The dot rule runs in every mode but "none", on the text parts. `tests/nvda_stubs.py`: the `LOG_SWITCHES` branch adds, per stage without `log_switch=False`, the literal keys of its `also_logged_by` keyword, then `args[0]`. Docstring of `inject_numbers`: the spec §4.2 order (edges, number language, number mode), and the two pass-throughs of step 3.
- [ ] **Step 4: Run** the full suite: **2647 passed, 0 skipped** (2641 − 1 deleted + 2 + 2 + 3). `test_the_log_confspec_has_every_log_switch` must pass (it fails if the stub misses `also_logged_by`).
- [ ] **Step 5: Equivalence oracle (D9, not committed).** In `<scratch>/oracle/`, a pytest module that loads the pipeline with `load_pipeline_module`, copies master's `inject_number_language`, `inject_number_mode` and their helpers (`git show master:addon/synthDrivers/WorldVoice/pipeline/__init__.py`), and checks with Hypothesis (3000 examples): text lists over `NUMBER_TEXT`'s alphabet plus `"a-"`, language commands; contexts generic and roles with number language default, main, en; modes value/none at any pause in 0..60, number/group at pause 0; after stripping text items and dropping blank ones, `inject_numbers` equals the old composition. Run it from the worktree root with `--rootdir` pointing at the worktree. Expected: pass. Record the result under "Execution record" at the end of this plan.
- [ ] **Step 6: Commit** `addon/synthDrivers/WorldVoice/pipeline/__init__.py tests/nvda_stubs.py tests/pipeline_harness.py tests/test_pipeline_filters.py tests/test_pipeline_passthrough.py tests/test_pipeline_pause_properties.py tests/test_pipeline_stages.py tests/test_worldvoice_speak.py` and `git add -f` the plan — `refactor: merge the number language and number mode stages`.

### Task 5: Edge and gap breaks in the number stage

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (`inject_numbers`, `_number_item_segments`)
- Create: `tests/test_pipeline_number_edges.py`
- Modify: `tests/test_pipeline_filters.py` (`NUMBER_MODES` `("group", 2, 50)`), `tests/test_pipeline_stages.py` (`test_worldvoice_keeps_the_break_subclasses_from_the_stages`)

**Interfaces:**
- Consumes: `NumberEdgeBreakCommand` (Task 2); `inject_numbers`, `_number_item_segments` (Task 4).
- Produces: `inject_numbers` with `edge = NumberEdgeBreakCommand(pause)` and `gap_break = NumberBreakCommand(pause)` when `mode in ("number", "group") and pause > 0`, else `None`; `tests/test_pipeline_number_edges.py` with `ROWS` (Task 6 adds the full-`STAGES` test over it), `shape()` and `context()` helpers.

`tests/test_pipeline_number_edges.py` conventions: `load_pipeline_module` with fresh settings per test: `number_mode="number"`, `scaled_number_wait=lambda: 10`, `group_size=3`, `scaled_punctuation_wait=lambda: 50`, punctuation disabled, item and Chinese-space waits 0. `context(module, numlan, roles=True)`: language `"zh"`, default voice `"Z"`/`"zh"`, `voice_name_for_language={"zh": "Z", "en": "E"}.get`. `shape()`: text as is; `NumberEdgeBreakCommand` → `("E", t)`; other `NumberBreakCommand` → `("NB", t)`; `PunctuationBreakCommand` → `("PB", t)`; plain `BreakCommand` → `("B*", t)` when marked, else `("B", t)`; language commands → `("L", lang)`; anything else as is. Names: `N(symbol)` = `symbol_name("zh", symbol)` (the harness's name in language zh). `ROWS` holds `pytest.param(sequence, options, stage, full, id=...)`, where `options` sets `mode`, `group_size`, `numlan`, `wait`, punctuation characters/removal/wait, item wait, `roles`, and `stage` is `None` for rows tested only through `STAGES`.

- [ ] **Step 1: Write the failing tests.**
  - `ROWS` stage column, one param per §5 row with the spec's `inject_numbers` output: `1`, `1g` (row 1, group), `1v`, `2`, `2v`, `3`, `4`, `5`, `6`, `7`, `8`, `8v`, `9`, `9v`, `10`, `11`, `13`, `13g`, `13v`, `15`, `16`, `17`, `18`, `19`, `20`, `21`, `23`, `24`, `25`, `26`, `26a`, `26b`, `26v`, `27`, `28` (`IndexCommand` = a `Marker` object), `40`, `42v`, `43`, plus O4 rows `o4-plus` (`"中+2"` → `["中+", ("E", 10), "2"]`), `o4-plus-value` (`["中+2"]`) and `o4-range` (`"5-3"` → `["5", ("NB", 10), N("-"), ("NB", 10), "3"]`); 41 params. Rows 22, 29–39, 41, 42, 44–46 carry `stage=None` (Task 6). `test_number_stage_worked_examples(sequence, options, stage, full)` runs over the rows with a stage only (`STAGE_ROWS = [r for r in ROWS if r.values[2] is not None]`): `assert shape(module.inject_numbers(sequence, settings, ctx)) == stage`.
  - `test_off_mode_yields_the_same_objects` (row 6): mode "none", default numlan, `result[0] is sequence[0]`.
  - `test_no_edge_break_without_a_number_pause`, parametrized mode `number`/`group` × wait `0`/`-5`: `["第123章"]` gives no `NumberEdgeBreakCommand`, and every break is a `NumberBreakCommand` with time = the wait (4 cases).
  - `test_a_global_factor_below_ten_adds_no_edge_break`: real settings `load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {"number_mode": "number", "global_wait_factor": 9, "number_wait_factor": 10}}}).pipeline_settings.get()`; `scaled_number_wait() == 0`; `inject_numbers(["第3章"], settings, GENERIC_CONTEXT) == ["第3章"]`.
  - `test_no_edge_break_at_an_item_end_or_before_only_whitespace` (O2, D1, Review Focus 4), number mode, wait 10: `"3"` → `["3"]`; `"3章"` → `["3", E, "章"]`; `"第3"` → `["第", E, "3"]`; `"3 "`, `"3 "`, `"3　"`, `" 3"`, `" 3 "` → unchanged; `"　第3　"` → `["　第", E, "3　"]`; ids `blank-empty` `""` → `[]`, `blank-space` `" "` → `[" "]`, `blank-ideographic` `"　"` → `["　"]` (12 cases).
  - `test_one_break_between_numbers_that_only_whitespace_separates` (O3): run `inject_numbers` then `number_wait_factor`; `[space]` `"1 2"` → `["1", ("NB", 10), "2"]`; `[no-break]` `"1 2"` → same; `[digits]` `"12 34"` → `["1", NB, "2", NB, "3", NB, "4"]`; `[wrapper]` numlan en `"1 2"` → `[("L", "en"), "1", ("L", "zh"), ("NB", 10), ("L", "en"), "2", ("L", "zh")]`; `[value]` value mode: stage `["1 2"]`, after `number_wait_factor` `["1", ("NB", 10), "2"]`. Each: no `("E", 10)` in either output.
  - `test_edge_breaks_sit_outside_the_wrapper` (O1, start_language): number language en, voices `{"zh": "Z", "en": "E", "fr": "F"}`, `[LangChangeCommand("fr"), "y 2x"]` → `[("L", "fr"), "y ", ("E", 10), ("L", "en"), "2", ("L", "fr"), ("E", 10), "x"]`.
  - `test_the_dot_rule_with_a_wrapper_and_edges` (D5 at pause 10): numlan en, `["12. Next"]` → `[("L", "en"), "1", ("NB", 10), "2", ("L", "zh"), ("E", 10), " . Next"]`.
  - `test_one_edge_and_one_gap_instance_per_run` (D10): `["第1章 2 3", "第4章"]`: every `NumberEdgeBreakCommand` in the result is one object, every gap `NumberBreakCommand` between `"2"` and `"3"` one object.
  - `test_a_long_item_of_numbers_stays_linear` (Review Focus 3): `["a1 " * 5000]`, number mode, wait 10, punctuation enabled with characters `"., "`, through every `stage.fn` of `STAGES`, in under 2 s (`time.perf_counter`), and the result holds 10 000 − 1 edge breaks.
  - Update `NUMBER_MODES[("group", 2, 50)]` (spec §8.1): `"v1.2"` → `["v", E50, "1", NB50, N_en("."), NB50, "2"]` where `E50 = ("NumberEdgeBreakCommand", 50)` in that file's `shape()`; and override `SHARED` there: `"a. 3"` → `["a. ", E50, "3"]`, `"3."` → `["3", E50, " ."]`, `".5"` → `[". ", E50, "5"]`.
  - Update `test_worldvoice_keeps_the_break_subclasses_from_the_stages[number]` and `[group]`: the sets gain `("NumberEdgeBreakCommand", 10)`.
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_pipeline_number_edges.py tests/test_pipeline_filters.py tests/test_pipeline_stages.py`. Expected red: every case that expects an `("E", 10)`/`E50` and the two subclass sets; the value, "none", pause-0 and blank cases already pass.
- [ ] **Step 3: Implement** the Produces line in `inject_numbers` and the edge/gap rules of spec §4.3 in `_number_item_segments`: a text part that is whitespace and has a number on both sides yields `gap_break` when `edge` is set; a number span yields `edge` on a side whose neighbouring text part has non-whitespace content.
- [ ] **Step 4: Run** the three files: green. Full suite: **2715 passed, 0 skipped** (2647 + 41 + 1 + 4 + 1 + 12 + 5 + 1 + 1 + 1 + 1).
- [ ] **Step 5: Commit** `addon/synthDrivers/WorldVoice/pipeline/__init__.py tests/test_pipeline_number_edges.py tests/test_pipeline_filters.py tests/test_pipeline_stages.py` — `feat: pause before and after numbers in digit and group modes`.

### Task 6: Edge pauses through all stages, other synths and the readmes

**Files:**
- Modify: `tests/test_pipeline_number_edges.py`, `tests/test_pipeline_nvda_ssml.py`
- Modify: `readme.md` (bullet at :53, changelog under "## Next update"), `addon/doc/zh_TW/readme.md` (same places)

**Interfaces:**
- Consumes: `ROWS`, `shape()`, `context()` (Task 5); `_plain_breaks` marker (Task 3); E1/E2 (Task 2).
- Produces: nothing new in code.

- [ ] **Step 1: Write the failing or new tests.**
  - Add to `ROWS` the §5 rows without a stage column (`stage=None`), with the spec's "After all `STAGES`" output: `22`, `31`, `31r` (row 31, removal on), `32`, `32r`, `33`, `34`, `35`, `36`, `37`, `38`, `38v`, `39`, `41`, `42`, `44`, `45`, `46`. Punctuation rows enable the stage with the character the row names (`"。"`, `"，"` or `"."`) and wait 50 unless the row says 0; row 45 sets item wait 30 and its input is two items.
  - `test_worked_examples_through_every_stage(sequence, options, stage, full)` over all of `ROWS` (59 params): run each `stage.fn` of `STAGES`; `assert shape(result) == (stage if full == "same" else full)`.
  - `test_other_synths_get_marked_edge_breaks`: rows 29 (`["第3章"]`, `GENERIC`-like context without roles, number language default) and 30 (`[WV("en"), "第3章"]`, no roles, number language en), through every `stage.handler` with `current_context` patched → `["第", ("B*", 10), "3", ("B*", 10), "章"]` (2 cases).
  - `test_other_synths_keep_the_punctuation_pause_through_the_handlers`: no roles, number mode, through every `stage.handler`: `[total]` `["Total. 12"]`, `"."` configured → `["Total", ".", ("B", 50), "1", ("B", 10), "2"]`; `[3，下-remove]` `["3，下"]`, `"，"` configured, removal → `["3", ("B", 50), "下"]` (2 cases).
  - `test_a_space_pause_character_meets_an_edge_break` (Review Focus 5): `["共 3 章"]`, characters `" "`, wait 50, `[remove-off]` and `[remove-on]` → `["共", ("E", 10), "3", ("PB", 50), "章"]` both, through every `stage.fn`.
  - `test_nvda_ssml_keeps_every_word_of_a_number_between_edges` (test_pipeline_nvda_ssml.py): number mode, generic context, `["第3章"]` through every handler; `re.sub(r"<[^>]*>|\s", "", xml) == "第3章"`; `xml.count('<break time="10ms"/>') == 2`; `warnings == []`.
- [ ] **Step 2: Run** the two files. Expected: green on the code of Task 5 (this task tests the composition of Tasks 2–5; any red is a bug in those tasks and is fixed there with a `Ruling:` in the ledger).
- [ ] **Step 3: Readmes.** Append the spec §6 sentence to the "Speech pause adjustment" bullet of both readmes, and add the spec §6 changelog entry as the first bullet under "Next update" in both, texts verbatim.
- [ ] **Step 4: Run** the full suite: **2781 passed, 0 skipped** (2715 + 59 + 2 + 2 + 2 + 1).
- [ ] **Step 5: Commit** `tests/test_pipeline_number_edges.py tests/test_pipeline_nvda_ssml.py readme.md addon/doc/zh_TW/readme.md` — `test: pin the number edge pause through every stage and document it`.

### Task 7: Edge-pause properties

**Files:**
- Create: `tests/test_pipeline_number_edge_properties.py`

**Interfaces:**
- Consumes: `inject_numbers`, `NumberEdgeBreakCommand`, `_merge_edge_breaks`, `STAGES`.
- Produces: nothing.

Strategies: `TEXT = st.text(alphabet="0123456789+-.,:aZ共第章。，，  　", max_size=16)`; `MODES = st.sampled_from(["none", "value", "number", "group"])`; numlan from `["default", "main", "en"]`; roles on/off; waits `st.integers(-5, 60)`; settings fresh per example as in `test_pipeline_pause_properties.py`. Symbol names are read back with a map over the harness names in `"en"` and `"zh"`.

- [ ] **Step 1: Write the properties** (`@SHARED_ENV @given(...)`, the health-check setting of `test_pipeline_pause_properties.py`):
  - `test_property_edges_keep_the_text` (P-E1): number/group, roles on, any numlan; joined `str` items with names read back equal the input with each whitespace gap between two numbers removed when wait > 0, after removing all spaces from both (the dot rule adds spaces).
  - `test_property_no_edge_outside_digit_and_group_modes` (P-E2): any mode/numlan/roles; no `NumberEdgeBreakCommand` when mode is value or none or wait ≤ 0; in value mode `shape` of the stage output is equal for the drawn wait and for 0.
  - `test_property_one_break_between_numbers` (P-E3): single-item input; no two `BreakCommand`s adjacent in the stage output, language commands transparent; for two `NUMBER_RE` matches with an all-whitespace gap, mode number/group, wait > 0: exactly one `NumberBreakCommand` and no edge break between their pieces.
  - `test_property_edges_sit_at_number_boundaries` (P-E4): each edge break has, on one side (skipping language commands), a piece whose edge character is a digit or a sign-led digit or a symbol name, and on the other side non-blank text.
  - `test_property_edges_never_meet_another_break` (P-E5): lists of up to 4 items from `TEXT`, existing `BreakCommand(30)` and `WVLangChangeCommand("en")`; random number, item and Chinese-space waits; any mode, group size 2–10, numlan, roles; punctuation on/off, removal on/off, characters from `[".,", "。，", ". ,"]`; through every `stage.fn` of `STAGES`; skipping language commands, no edge break is next to another `BreakCommand`. `max_examples=400`.
  - `test_property_merge_keeps_the_longest` (P-E6): lists of text (`"a"`, `" "`, `""`), edge/number/punctuation/plain breaks with times 0–60, and markers; per run (split at non-blank text), when it holds an edge and ≥ 2 breaks, the kept break's time is the run's maximum and the non-break items keep their order; otherwise the run is unchanged (identity).
- [ ] **Step 2: Run** the file. Expected: green (the code is done; a failing example is a bug, fixed in the owning task's code with a regression case added there and a `Ruling:` in the ledger).
- [ ] **Step 3: Run** the full suite: **2787 passed, 0 skipped** (2781 + 6).
- [ ] **Step 4: Commit** `tests/test_pipeline_number_edge_properties.py` — `test: check number edge pause properties with Hypothesis`.

### Task 8: Detection passes the edge breaks through (O6)

**Files:**
- Modify: `tests/test_worldvoice_speak.py`

**Interfaces:**
- Consumes: `speak_through_stages`, `stage_settings`, `TIMINGS` of that file.
- Produces: nothing.

- [ ] **Step 1: Write the tests.** `EDGE_ROWS`: one `pytest.param(sequence, numlan, main, wait0, wait10, id=...)` per row of spec §4.8's table, its first row ("default / main") split in two, so 9 params with ids `rank-follow`, `rank-main`, `rank-en`, `zh12-main`, `zh12-follow`, `abc3-follow`, `covid-main`, `sign-main`, `zh-locale`, and the table's two expected columns. `test_number_mode_edges_with_detection`, `@TIMINGS` × `EDGE_ROWS` × `wait` in `[0, 10]`: `speak_through_stages(monkeypatch, sequence, numlan=numlan, main=main, timing=timing, settings=stage_settings(number_mode="number", number_wait=wait)) == (wait0 if wait == 0 else wait10)` (36 cases). `test_value_mode_has_no_edges_with_detection`, `@TIMINGS`: `["第3章"]`, numlan default, main zh, value mode, wait 10 → `[(ZH, "第3章")]` (2 cases).
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_worldvoice_speak.py`. Expected: green (O6 needs no code; a red row is recorded as a `Ruling:` and stops the task for the orchestrator).
- [ ] **Step 3: Run** the full suite: **2825 passed, 0 skipped** (2787 + 38).
- [ ] **Step 4: Commit** `tests/test_worldvoice_speak.py` — `test: pin what each voice reads around number edge pauses`.

### Task 9: Mutation testing and final verification

**Files:**
- Modify only if a survivor is a real gap: the test file that owns the function.

**Interfaces:**
- Consumes: everything above.
- Produces: the execution record below.

- [ ] **Step 1: mutmut.** From the worktree root (`mutants/` is git-ignored): `<scratch>/guard.sh mutmut run --max-children 3 "*_number_item_segments*" "*inject_numbers*" "*_merge_edge_breaks*" "*_is_edge_break*" "*_plain_breaks*"`, after confirming the names with `mutmut results`. Each survivor: `mutmut show <name>`, then confirm with the suite in `mutants/` under `MUTANT_UNDER_TEST=<name>`. A real gap gets a killing test in the owning test file (full suite count rises by that many); an equivalent mutant is listed with its reason in the execution record. Remove `mutants/` afterwards (own scratch output).
- [ ] **Step 2: Verify** (`DEVELOPMENT_WORKFLOW.md` §7): full suite **≥ 2825 passed, 0 skipped**; `prek run --all-files` all Passed; `git diff --check master` prints nothing; `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py` and `git ls-files addon/synthDrivers/WorldVoice/driver/Neural` print nothing; `git diff --stat master -- buildVars.py addon/locale` prints nothing.
- [ ] **Step 3: Commit** any killing tests (`test: kill surviving mutants of the number edge stage`) and this plan's execution record (`git add -f` the plan; `docs: record the number edge pause execution`).

## Execution record

(Filled in during execution: oracle result of Task 4 step 5, mutmut results of Task 9.)
