# Leading Punctuation Follows the Text After It Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** Common and Inherited characters at the start of a text item (punctuation, symbols, spaces, and Common digits under "Follow surrounding text language") go to the language of the first character after them that decides, so a Nepali line starting with `(` or `"` no longer switches to the main voice first; items with only such characters at an utterance's start look ahead to the first deciding character.

**Architecture:** The rule lives in `languageDetection/detector.py`: `add_detected_language_commands` buffers one utterance at a time, and when it meets a non-deciding character at an item's start it plans the whole run in one forward scan (languages per stretch between document language commands), then runs today's per-character loop with those targets. Which breaks continue an item is a function in `pipeline/breaks.py` (`is_internal_break`) that the driver hands to the detector (D13); the punctuation and unspaced stages change only the class of the breaks they emit (two new subclasses).

**Tech Stack:** Python 3 (NVDA add-on), pytest, Hypothesis, mutmut 3.8.0, ruff 0.16.3 via prek.

**Spec:** `docs/superpowers/specs/2026-11-09-fix-leading-punctuation-language-design.md` (approved at d12f58d)

## Global Constraints

- U1–U9 (`Decided by the user`) are binding; D1–D13 are accepted orchestrator defaults. Deviations are recorded as `Ruling:` lines in the ledger; anything changing user-visible behaviour beyond the spec stops the work.
- Code scope: `languageDetection/detector.py`, `pipeline/breaks.py`, `pipeline/punctuation.py` (break class only), `pipeline/unspaced.py` (break class only), `__init__.py` (wiring). No other stage changes behaviour; break times and positions never change.
- The detector imports no `pipeline/` module (D13); `tests/test_pipeline_structure.py` keeps the pipeline from importing `languageDetection`.
- Settings and the number language are read once per `add_detected_language_commands` call; it stays a generator that reads its inputs on the first `next()`, and yields every input command as itself, in order.
- Spelling (`process_for_spelling`) is unchanged (D7).
- `tmp_lang`/`cur_lang` carry across utterance ends as today (D11); only the came-before check and the lookahead reset at `EndUtteranceCommand` and `ConfigProfileTriggerCommand` (U8).
- Docs: only `addon/doc/zh_TW/readme.md` (spec §5 drafts; changelog under a new `## 下一版更新` above `## WorldVoice 7.1 更新`); NVDA UI names quoted from `ref/nvda/source/locale/zh_TW/LC_MESSAGES/nvda.po` without accelerators. No root `readme.md`, no other language, no `.po` (no new UI strings).
- Never edit `addon/synthDrivers/WorldVoice/driver/*/driver/*`, `driver/sonic/`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py`. Engine drivers stay independently installable. Never add Neural. Never stage `ref`.
- ruff pinned `==0.16.3`; commits run prek hooks; when a hook edits files, re-stage and commit again, never `--no-verify`.
- git: stage explicit paths (the plan needs `git add -f`); check `git diff --cached --stat`; commit `<type>: <summary>` with a body explaining why; no `Co-Authored-By`; no push, no merge, no `git stash`.
- Tests: at most 3 parallel workers, under the memory guard (stop pytest when MemAvailable < 3 GB). Scratch files only in `/tmp/claude-0/-workspace-WorldVoice/9392737d-1c1b-4c13-abe5-1db2498dc4cc/scratchpad/`.
- Baseline (master 6ea5665): 3808 passed, 0 skipped; `prek run --all-files` all Passed.

## Review Focus

1. Blank strings and whitespace inside a leading run (`["", '"नेपाल"']`, `[" ", BreakCommand(10), "नेपाल"]` at utterance start): no empty string yielded, one switch at most, before the run — Task 4 `test_blank_text_joins_the_leading_run`.
2. Inherited marks at an item's start (`"́नेपाल"`, a lone virama before Devanagari): they go with the text after them, like Common characters — Task 4 `test_inherited_marks_join_the_leading_run`.
3. A one-shot iterator input with utterance ends (a generator, not a list): every command comes back as itself, in order, and settings are read once — Task 5 `test_a_generator_input_with_utterance_ends_keeps_every_command`.
4. A long utterance of Common-only items under "Follow surrounding text language" (20000 `"."` items separated by plain breaks, no letter): detection stays linear, well under 2 s — Task 5 `test_a_long_common_only_utterance_stays_linear`.
5. Number wrappers under "main" next to a leading run, detection before NVDA: the wrapper objects reach `detect_with_number_language` unchanged, so numbers still reach NVDA glued into their item — Task 6 `test_numbers_reach_nvda_in_their_item_where_the_voice_stays` (existing, must stay green) and `test_a_main_number_after_leading_punctuation_keeps_its_item`.

---

### Task 1: The new break classes and the internal-break check

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/breaks.py:50-55`
- Test: `tests/test_pipeline_stages.py`

**Interfaces:**
- Consumes: `BreakCommand`, `NumberBreakCommand`, `NumberEdgeBreakCommand`, `NumberItemEdgeBreakCommand`, `PunctuationBreakCommand`, `SegmentBreakCommand`.
- Produces: `class InternalPunctuationBreakCommand(PunctuationBreakCommand)`, `class UnspacedSpaceBreakCommand(BreakCommand)`, `is_internal_break(command: SpeechCmd) -> bool` — all in `pipeline/breaks.py`.

- [ ] **Step 1: Write the failing tests** in `tests/test_pipeline_stages.py` (module from `load_pipeline_module`; `Marker` stands for an `IndexCommand`):

```python
@pytest.mark.parametrize(("name", "expected"), [
	("InternalPunctuationBreakCommand", True), ("SegmentBreakCommand", True),
	("NumberBreakCommand", True), ("NumberEdgeBreakCommand", True),
	("UnspacedSpaceBreakCommand", True), ("NumberItemEdgeBreakCommand", False),
	("PunctuationBreakCommand", False), ("BreakCommand", False),
])
def test_is_internal_break(monkeypatch, name, expected):
	module, _ = load_pipeline_module(monkeypatch, pause_settings("value", 0))
	assert module.is_internal_break(getattr(module, name)(10)) is expected

def test_a_command_that_is_no_break_is_not_internal(monkeypatch): ...  # Marker() -> False

def test_the_new_breaks_keep_their_parents(monkeypatch):
	# isinstance(InternalPunctuationBreakCommand(5), PunctuationBreakCommand) and BreakCommand;
	# isinstance(UnspacedSpaceBreakCommand(5), BreakCommand); _plain_breaks of both gives
	# type(x) is BreakCommand with times 5 and 7 and no edge marker.
```

- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_pipeline_stages.py -k "internal or new_breaks"` — expected red: 10 failed (`AttributeError`/`ImportError` for the new names).
- [ ] **Step 3: Implement** the two classes (one-line docstrings: internal punctuation pause / the end-of-item pause beside an in-item number edge; the space pause between unspaced-script characters) and `is_internal_break` in `pipeline/breaks.py`: true for instances of `InternalPunctuationBreakCommand`, `SegmentBreakCommand`, `NumberBreakCommand`, `UnspacedSpaceBreakCommand`, except `NumberItemEdgeBreakCommand` (spec U5, D8). Docstring: a pause a stage puts inside one NVDA item, which language detection reads through (spec U5).
- [ ] **Step 4: Run** the same selection — 10 passed. Full suite `python3 -m pytest -q tests` — **3818 passed, 0 skipped**.
- [ ] **Step 5: Commit** `feat: add the internal break classes and their check` (body: detection must tell WorldVoice's in-item pauses from item boundaries, spec U5/U6/D12/D13).

### Task 2: The punctuation stage emits the internal class at internal points

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/punctuation.py:135-178,193-196`
- Test: `tests/test_pipeline_punctuation_pause.py`, `tests/test_pipeline_stages.py:359-381`, `tests/test_pipeline_filters.py:637-668`, `tests/test_pipeline_passthrough.py:180-185`, `tests/test_pipeline_pause_properties.py:55-90`

**Interfaces:**
- Consumes: Task 1 `InternalPunctuationBreakCommand`; `_is_edge_break`, `_is_item_edge_break`.
- Produces: nothing new; internal points yield `InternalPunctuationBreakCommand(wait)`, the end-of-item pause yields `PunctuationBreakCommand(wait)` unless a pending break is a non-item number edge break (then the internal class).

- [ ] **Step 1: Change the expectations (spec §7.1, class only — positions and times unchanged)**: every expectation for a pause after a mark that non-blank text follows inside the same string names `InternalPunctuationBreakCommand` (21 tests in `test_pipeline_punctuation_pause.py`, including all cases of `test_an_edge_break_keeps_the_punctuation_pause`; the 4 cases of `test_worldvoice_keeps_the_break_subclasses_from_the_stages` (`EDGES`/`NO_EDGES` sets); 2 cases of `test_an_unnamed_symbol_in_number_mode_is_left_to_the_punctuation_stage`; `test_punctuation_pause_passes_a_leading_command`; and the helper of `test_property_the_wait_changes_only_the_break_time`, which maps both class names). Add:

```python
def test_internal_points_emit_the_internal_class(monkeypatch):
	# ["Hello. World"] -> ["Hello", ".", InternalPunctuationBreakCommand, " World"]; the break is a PunctuationBreakCommand too.

def test_the_end_of_item_pause_keeps_the_punctuation_class(monkeypatch):
	# ["Hello.", "World"] -> ["Hello", ".", ("PunctuationBreakCommand", 250), "World"]  (type(...) is PunctuationBreakCommand)

@pytest.mark.parametrize(("edge", "expected"), [
	("NumberEdgeBreakCommand", "InternalPunctuationBreakCommand"),
	("NumberItemEdgeBreakCommand", "PunctuationBreakCommand"),
])
def test_the_end_of_item_pause_beside_an_in_item_number_edge_is_internal(monkeypatch, edge, expected):
	# ["नेपाल,", <edge>(10), "12"] with "," configured, wait 20: the kept break (merge keeps the 20 ms one) has class `expected` (spec F11, D12).
```

- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_pipeline_punctuation_pause.py tests/test_pipeline_stages.py tests/test_pipeline_filters.py tests/test_pipeline_passthrough.py tests/test_pipeline_pause_properties.py` — expected red: the changed tests and 3 of the new ones fail (≈ 31 failed), the rest pass.
- [ ] **Step 3: Implement** in `_punctuation_pauses`: a second pause object `InternalPunctuationBreakCommand(settings.scaled_punctuation_wait())`; `emit` takes the end-of-item class as a parameter (`boundary_break`), yields the internal one at `eligible_here`, and the caller passes the internal break when `any(_is_edge_break(b) and not _is_item_edge_break(b) for b in pending_breaks)`, else the plain punctuation break. Update the stage docstring's first bullet to name both classes.
- [ ] **Step 4: Run** the same files — all pass. Full suite — **3822 passed, 0 skipped**.
- [ ] **Step 5: Commit** `feat: mark internal punctuation pauses with their own class` (body: spec U5/D12, detection reads through them; NVDA's `BreakCommand.__eq__` compares type, so expectations name the class).

### Task 3: The unspaced space pause emits its own class

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/unspaced.py:8,65`
- Test: `tests/test_pipeline_unspaced_space.py`, `tests/test_pipeline_unspaced_space_properties.py` (only if it names the class), `tests/test_pipeline_stages.py`

**Interfaces:**
- Consumes: Task 1 `UnspacedSpaceBreakCommand`.
- Produces: the stage yields `UnspacedSpaceBreakCommand(wait)`.

- [ ] **Step 1: Change the expectations**: `B`/`B10` in `test_pipeline_unspaced_space.py` become `("UnspacedSpaceBreakCommand", 20/10)`, `test_stages_digit_neighbour_has_no_space_pause` checks that name (28 tests); grep the other pipeline test files for a space pause compared as `"BreakCommand"` and update those too. Add `test_the_space_pause_is_an_unspaced_space_break` (`isinstance` of both classes) and, in `test_pipeline_stages.py`, `test_a_synth_without_roles_gets_a_plain_space_pause` (`["中文 日本"]` through the stage handlers with `GENERIC_CONTEXT` and wait 10: the one break is `type(...) is BreakCommand`, time 10).
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_pipeline_unspaced_space.py tests/test_pipeline_unspaced_space_properties.py tests/test_pipeline_stages.py` — expected red: ≈ 29 failed.
- [ ] **Step 3: Implement**: `pause_cmd = UnspacedSpaceBreakCommand(waitfactor)`; import from `.breaks` (drop the unused `BreakCommand` import).
- [ ] **Step 4: Run** — all pass. Full suite — **3824 passed, 0 skipped**.
- [ ] **Step 5: Commit** `feat: mark the unspaced space pause with its own class` (body: spec U6).

### Task 4: Detection — a leading run takes the language of its item's deciding character

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/languageDetection/detector.py`
- Modify: `tests/detector_harness.py` (stub `BreakCommand(time)`, `EndUtteranceCommand`, `ConfigProfileTriggerCommand` in `speech.commands`; load `PACKAGE + ".pipeline.breaks"` as `env.breaks`)
- Test: `tests/test_language_detector.py`

**Interfaces:**
- Consumes: Task 1 `is_internal_break` (tests and driver only, never imported by the detector).
- Produces: `LanguageDetector.__init__(self, available_languages, *, settings, language, number_language=lambda: FOLLOW, is_internal_break=lambda command: False)`; `add_detected_language_commands(speech_sequence)` keeps its signature. `make_detector` in the tests passes `is_internal_break=env.breaks.is_internal_break` (D13: the driver's check).

- [ ] **Step 1: Change the expectations (spec §7.1)**: `C2` → `[("lang","de_DE"), ("lang","en"), ", hallo"]`; `digits-ignored` → `[("lang","de_DE"), ("lang","en"), "12 hallo"]`; `mixed` → `[("lang","ne"), "1२3"]`; `common-then-script` → `[("lang","ne"), "1२"]` with the comment citing U9. `test_property_only_script_digits_start_a_detected_run`: a run opened by a digit without a script is allowed when the next character with a script after it is covered by the run's language (`covers(env, scenario, language, script)`); with none after it in the output, the property fails.
- [ ] **Step 2: Write the failing unit tests** (`detect(...)` with `languages=NE`, `base="en_US"` unless stated; `B = env.breaks`):

```python
# test_a_leading_run_follows_the_text_after_it  (sequence, languages, base, expected)
['"नेपाल"'] -> [("lang","ne"), '"नेपाल"']; ["(नेपाल)"], ["“नेपाल”"], ["- नेपाल"] likewise
['" २०८१'] -> [("lang","ne"), '" २०८१']
["link", BreakCommand(10), '"नेपाल"'] -> ["link", BREAK, ("lang","ne"), '"नेपाल"']
[L("en"), '"नेपाल"'] -> [("lang","en"), ("lang","ne"), '"नेपाल"']
("en_US","zh_TW") base en_US: ["「中文」"], ["（中文）"], ["(中文)"] -> [("lang","zh"), …]
NE base "ne_NP": ['"Hello"'] -> [("lang","en"), '"Hello"']        # mirror; primary of the result as the code gives it
("en_US","zh_TW") base en_US: ["2024年"] -> [("lang","zh"), "2024年"]; base zh_TW: ["3 apples"] -> [("lang","en"), "3 apples"]

# test_detection_keeps_these_as_today
['abc "नेपाल"'] -> ['abc "', ("lang","ne"), 'नेपाल"']; ['नेपाल "नेपाल"']; ['"'] -> ['"']
["link", BreakCommand(10), "("] -> unchanged; [L("ne_NP"), '"नेपाल"'] -> [("lang","ne_NP"), '"नेपाल"']
['"नेपाल"'] with ("en_US","zh_TW") -> ['"नेपाल"']; ['"ᏣᎳᎩ'] -> ['"ᏣᎳᎩ']
("en_US","zh_TW") base zh_TW: ["「中文」"], ["(中文)"] -> unchanged
number language "main", unwrapped: ["2024年"] -> ["2024", ("lang","zh"), "年"]

# test_internal_breaks_continue_the_item(name): ["abc", ",", B.<name>(0), ' "नेपाल"'] gives ' "' to en_US
#   for InternalPunctuationBreakCommand, SegmentBreakCommand, NumberBreakCommand, NumberEdgeBreakCommand, UnspacedSpaceBreakCommand
# test_boundaries_end_the_item(command): the same with PunctuationBreakCommand(0), NumberItemEdgeBreakCommand(0),
#   IndexCommand(1), BreakCommand(10) gives ' "' to ne
# test_adjacent_strings_are_one_item: ["link", '"नेपाल"'] -> ["link", '"', ("lang","ne"), 'नेपाल"']   (U5 limitation)
#   and ["abc ", "12", NumberBreakCommand(10), "34", " (नेपाल)"] keeps " (" in en_US
# test_a_wrapped_number_keeps_its_item (main): ["नेपाल (", WV("en_US"), "2024", WV("en_US"), ") नेपाल"] keeps "2024) " in en_US
# test_without_the_internal_break_check_every_break_ends_an_item: detector built without is_internal_break,
#   ["abc", ",", InternalPunctuationBreakCommand(0), ' "नेपाल"'] gives ' "' to ne
# test_blank_text_joins_the_leading_run: ["", '"नेपाल"'] -> [("lang","ne"), '"नेपाल"'] (no "" yielded)   (Review Focus 1)
# test_inherited_marks_join_the_leading_run: ["́नेपाल"] -> [("lang","ne"), "́नेपाल"]          (Review Focus 2)
# test_spelling_keeps_a_leading_mark_in_the_locale: process_for_spelling('"नेपाल', "en_US") == [('"', "en_US"), ("नेपाल", "ne")]
```

- [ ] **Step 3: Run** `python3 -m pytest -q tests/test_language_detector.py` — expected red: the changed cases, the new leading-run cases and `test_internal_breaks_continue_the_item` fail (`TypeError` on `is_internal_break` until the parameter exists, then wrong languages); "keeps as today", boundary and spelling cases pass.
- [ ] **Step 4: Implement** the item rule in `detector.py`:
  - `__init__` stores `is_internal_break`.
  - A character *decides* (D1) when it is a decimal digit and the number language is not FOLLOW (a stop: it decides nothing), or `get_script` is not `None`/`"Common"`/`"Inherited"`.
  - Items: strings, internal breaks (`is_internal_break`) and `WVLangChangeCommand`s continue an item; any other command, and an NVDA `LangChangeCommand`, ends it (U5, D3, D5).
  - At a non-deciding character at an item's start, plan the run once: scan forward to the item's first deciding character; a stop (non-FOLLOW digit) or a `WVLangChangeCommand` ends the scan with "keep" (D2, D3, D9). The run's language is the deciding character's `_language_for_character(c, tmp_lang, cur_lang, …)` with the state at the item's start (D2). Every character of the run gets that target in today's loop (switch comparison unchanged, `detector.py:89`); the deciding character and everything after it use today's rule.
  - The loop yields strings whole: one output string per input string, split only by inserted switches.
  - The plan and loop must be structured so Task 5 adds the utterance scope and lookahead to the same scan (one planned run covers every character up to the deciding character, split into stretches at NVDA `LangChangeCommand`s).
- [ ] **Step 5: Run** `python3 -m pytest -q tests/test_language_detector.py` — all pass. Full suite — expected **3824 + N passed, 0 skipped** (N = the new test ids, recorded in the ledger), with exactly `tests/test_worldvoice_speak.py::test_property_each_digit_is_read_by_the_number_language_voice` (2 ids) failing if its examples hit a leading Common digit — then mark it in the ledger as fixed by Task 6 and do not commit a red suite: fold its oracle change (Task 6 Step 1, digit property only) into this commit.
- [ ] **Step 6: Commit** `fix: leading punctuation follows the text after it in its item` (body: reported case, U1/U2/U5/U9, D1–D5, D13).

### Task 5: Detection — utterance scope and the utterance-start lookahead

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/languageDetection/detector.py`
- Test: `tests/test_language_detector.py`

**Interfaces:**
- Consumes: Task 4's planned run.
- Produces: no new public names. The detector imports `EndUtteranceCommand` and `ConfigProfileTriggerCommand` from `speech.commands` for its own utterance check (D13 forbids importing `pipeline.sequence._ends_utterance`; same definition).

- [ ] **Step 1: Write the failing tests** (`E = EndUtteranceCommand()`, `C = ConfigProfileTriggerCommand()`; `B10 = BreakCommand(10)`):

```python
# test_an_utterance_start_looks_ahead (U7)
["(", InternalPunctuationBreakCommand(0), "नेपाल)"], ["-", B10, "नेपाल"], ["(", B10, "1", B10, "नेपाल"]
	-> the leading marks and "1" in ne: [("lang","ne"), "(", …]
["Price", B10, "100", B10, "नेपाल"] -> 100 stays en_US;  ["(", B10] -> ["(", B10]
# test_a_wrapped_number_stops_the_lookahead (main, D9)
["(", B10, WV("en_US"), "1", WV("en_US"), B10, "नेपाल"] keeps "(" and "1" in en_US
[WV("en_US"), "2024", WV("en_US"), B10, "(", B10, "नेपाल"] keeps "(" in en_US   (came before)
# test_utterances_bound_the_lookahead (U8, D11)
["नेपाल", E, "(", B10, "abc"] -> "(" in en (switch before "(");  with C in place of E: the same
["नेपाल", "(", B10, "abc"] -> "(" stays ne;  ["(", E, "नेपाल"] -> "(" in en_US
["नेपाल", E, "100"] -> "100" stays ne (no command before it)
# test_the_lookahead_across_a_document_language (D10), languages ("en_US","hi_IN","ne_NP")
['"', L("hi_IN"), "नेपाल"] -> quote to hi_IN;  [L("ne_NP"), '"', L("hi_IN"), "नेपाल"] -> quote stays ne_NP
devanagari="ne": [L("hi_IN"), "abc", B10, '"नेपाल"'] -> quote to hi_IN
# test_detection_reads_the_number_language_once_per_sequence: extend the input with '"', E, "(" — reads == [1]
# test_a_generator_input_with_utterance_ends_keeps_every_command (Review Focus 3):
#   iter(["(", B10, E, '"नेपाल"', C, "x"]) -> every given command present as itself, in order; one settings read
# test_a_long_common_only_utterance_stays_linear (Review Focus 4): 20000 x [".", BreakCommand(1)] under FOLLOW,
#   no letter: output equals input, time.perf_counter() delta < 2 s
```

- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_language_detector.py` — expected red: the lookahead, utterance (`E`/`C` cases with `(` to en) and D10 cases fail; carry-over, "stays ne", generator and linear tests may already pass.
- [ ] **Step 3: Implement**:
  - Split the input into utterances, each ending after an `EndUtteranceCommand` or `ConfigProfileTriggerCommand` (U8); process each utterance list, yielding as it completes. `tmp_lang`/`cur_lang` carry on (D11).
  - Track *came before*: a deciding character or a `WVLangChangeCommand` seen earlier in the utterance (U7, D9).
  - Extend the run scan: at an item boundary with nothing deciding found yet, keep scanning into the next items only when nothing came before; else "keep". A `WVLangChangeCommand` or a non-FOLLOW digit stops with "keep"; the utterance's end with "keep".
  - Stretch languages (D10): the run splits at NVDA `LangChangeCommand`s. Let `s` = the deciding character's script and `X = _language_for_character(c, tmp, cur, …)` with the state after the last crossed `LangChangeCommand` (or the run start's state). Each stretch whose language in force (`tmp` at its start) covers `s` keeps it; otherwise it takes `X` when `X` covers `s`, else keeps (Ruling candidate: "else keeps" is the §4.4 "no voice, nothing changes" rule applied across document commands; within one item it is identical to D2).
  - The plan is computed once per run and covers every character up to the deciding character, so the loop stays linear.
- [ ] **Step 4: Run** — all pass. Full suite — **previous + N passed, 0 skipped** (N recorded).
- [ ] **Step 5: Commit** `fix: an utterance's leading punctuation looks ahead to its text` (body: U7, U8, D9–D11).

### Task 6: Driver wiring and end-to-end tests

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/__init__.py:287-292` (pass `is_internal_break=is_internal_break`, imported from `.pipeline.breaks`)
- Test: `tests/test_worldvoice_speak.py` (wire `_synth` as the driver: `is_internal_break=load("pipeline.breaks").is_internal_break`; `stage_settings` gains `item_wait=0`, `unspaced_wait=0`, `punctuation_characters=".,"`, `punctuation_wait=0`; `speak_through_stages(main=…)` accepts `"ne"` with main voice `NE`, language `ne_NP`; `nvda_processes_each_item(..., level="some")`; a helper `spoken(result)` that drops `"|"` and blank texts, strips each text and merges neighbours of the same voice)

**Interfaces:**
- Consumes: Task 1 `is_internal_break`; Task 4/5 detector parameter.
- Produces: harness helpers `spoken(result) -> list[tuple[str, str]]` and the extended `stage_settings`, used by Task 7.

- [ ] **Step 1: Write the failing tests** (`patch.setitem(VOICES, "ne", NE)` in each; `ITEM = stage_settings(item_wait=10)`; both timings via `@TIMINGS` unless stated):

```python
# test_leading_punctuation_is_read_by_the_voice_of_the_text (§3 rows, item pause 10):
'(नेपाल)', '- नेपाल', '" २०८१', '(2024) नेपाल' (default)  -> spoken == [(NE, text)]
'「中文」', '（中文）', '(中文)', '2024年' (default)             -> [(ZH, text)]
'2024年' (main) -> [(EN, "2024"), (ZH, "年")]
'abc "नेपाल"' -> [(EN, 'abc "'), (NE, 'नेपाल"')]
main "ne": '"Hello"' -> [(EN, '"Hello"')]
# test_a_quoted_line_through_nvda (heard_through_nvda): '"नेपाल"' before/"some" -> [(NE, 'नेपाल')], after/"some" -> [(NE, 'नेपाल')];
#   before/"most" -> NE reads 'quote नेपाल quote';  '(नेपाल)' after/"some" -> [(NE, '(नेपाल)')];
#   after/"most" -> unchanged from master: [(EN, "left paren("), (NE, "नेपाल "), (EN, "right paren)  ")]
# test_pause_settings_keep_the_voices: 'abc, "नेपाल"' with PUNCTUATION off / on("," wait 0 and 30);
#   'abc 12 34 (नेपाल)' with number pause 0 / 10 -> the same spoken voices in each pair: [(EN, ...'"'/'('), (NE, ...)]
# test_adjacent_items_without_an_item_pause: ["link", '"नेपाल"'] item pause 0 -> [(EN, 'link"'), (NE, 'नेपाल"')]
# test_an_item_pause_ends_the_item: ["link", '"नेपाल"'] item pause 10 -> [(EN, "link"), (NE, '"नेपाल"')]
# test_an_utterance_start_looks_ahead: ["(नेपाल)"] with "(" configured -> [(NE, "("), (NE, "नेपाल)")] merged to [(NE, "(नेपाल)")];
#   ["-", "नेपाल"] -> [(NE, "-नेपाल")]; ["(", "1", "नेपाल"] default -> all NE; main -> [(EN, "(1"), (NE, "नेपाल")]
#   ["Price", "100", "नेपाल"] -> [(EN, "Price100"), (NE, "नेपाल")]
# test_a_main_number_after_leading_punctuation_keeps_its_item (Review Focus 5): 'नेपाल (2024) नेपाल' main ->
#   [(NE, "नेपाल ("), (EN, "2024)"), (NE, "नेपाल")] as on master, both timings
```

  Also update `test_property_each_digit_is_read_by_the_number_language_voice` if Task 4 has not: under `"default"`, a decimal digit before any letter or `२` takes the voice of the first such character after it (`ZH`/`EN` by letter, `NE` for `२`), or the main voice when there is none or it is `٣` (no Arabic voice; D1).
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_worldvoice_speak.py` — expected red: rows whose leading run is cut by a `PunctuationBreakCommand`-free internal break fail until the harness passes the check, and every new test using `main="ne"` fails until the harness accepts it.
- [ ] **Step 3: Implement** the wiring in `__init__.py` and the harness changes above.
- [ ] **Step 4: Run** — all pass. Full suite — **previous + N passed, 0 skipped**.
- [ ] **Step 5: Commit** `fix: hand the internal break check to language detection` (body: D13; end-to-end rows of spec §3/§7.4).

### Task 7: The two invariants as Hypothesis properties

**Files:**
- Modify: `tests/detector_harness.py` (add `master_detection(detector, speech_sequence)`: today's per-character rule, `detector.py:66-99` at 6ea5665, using the detector's own `_language_for_character`, `_settings`, `_number_language`, `_language`)
- Test: `tests/test_language_detector.py`, `tests/test_worldvoice_speak.py`

**Interfaces:**
- Consumes: Task 6 `spoken`, `stage_settings`; Task 1 classes via `env.breaks`.
- Produces: `master_detection` (the oracle).

- [ ] **Step 1: Write the properties**:
  - `SCRIPT_SAMPLES` gains `'"'`, `"("`, `"「"`, `"- "`. `ITEMS` also draws: a wrapper triple `[WV(lang), digits, WV(lang)]` (flattened), each break class of Task 1 plus `PunctuationBreakCommand`, `NumberItemEdgeBreakCommand`, plain `BreakCommand`, `IndexCommand`, `EndUtteranceCommand`, `ConfigProfileTriggerCommand`. Existing properties keep passing.
  - `test_property_never_more_language_changes_than_today` (Invariant 1, both number-language kinds drawn: `"default"`, `"main"`): same joined text; primary-language changes between consecutive non-whitespace characters ≤ the oracle's; every deciding character (D1) has the oracle's language; when the items hold no NVDA `LangChangeCommand`, the inserted commands' languages equal the oracle's, in order.
  - `test_property_pause_settings_do_not_change_voices` (Invariant 2, `@TIMINGS`, `max_examples=50`, `deadline=None`): 1–3 items of pieces `abc, नेपाल, 中文, 12, 34, " ", ",", ".", "(", ")", '"', "「", "-", "२", "ー"`; number language `"default"`/`"main"`; main `en`/`zh`; item pause 10; group size 0 or 3 (same in both runs); off = all four pauses 0 and punctuation disabled; on = punctuation enabled with `,.("` at wait 0/5/30, number pause 0/10, segment length 0/4 (wait 10), unspaced wait 0/10. Assert the `(character, voice)` list of non-whitespace characters is equal.
  - `test_property_never_more_voice_changes_than_today` (`@TIMINGS`): the same draws plus item pause 0/10; the run with the detector's `add_detected_language_commands` replaced by `master_detection` is the oracle; same non-whitespace text; voice changes ≤ the oracle's.
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_language_detector.py tests/test_worldvoice_speak.py -k property` — expected green (the rule is in place); to prove each property bites, temporarily (scratch copy, not committed) make the run language skip the D2 covering check / swap `is_internal_break` for the default, and record the falsifying example in the ledger.
- [ ] **Step 3: Full suite** — **previous + 5 passed, 0 skipped**.
- [ ] **Step 4: Commit** `test: pin the leading punctuation invariants as properties` (body: spec §4.3).

### Task 8: Documentation

**Files:**
- Modify: `addon/doc/zh_TW/readme.md:79-93`
- Modify: `docs/superpowers/specs/2026-11-07-fix-script-digit-language-design.md:54` (`git add -f`)

**Interfaces:** none.

- [ ] **Step 1:** Add the spec §5 bullet after the 「字元集假設的語言」 list in `## Unicode 偵測`, and `## 下一版更新` with the spec §5 entry above `## WorldVoice 7.1 更新`; check every quoted NVDA name against `ref/nvda/source/locale/zh_TW/LC_MESSAGES/nvda.po` (「標點及符號等級」, 「一些」, 「多數」, 「全部」) and every WorldVoice name against `addon/locale/zh_TW/LC_MESSAGES/nvda.po` (「語言偵測時間點」, 「跟隨前後文語言」, 「項目停頓參數」).
- [ ] **Step 2:** In the 7.1 spec G2 bullet, strike through the superseded clause and add: "At the start of a text item the leading `1` now follows `२` (Corrected by `fix/leading-punctuation-language`, U9)."
- [ ] **Step 3:** `prek run --all-files` — all Passed; full suite unchanged.
- [ ] **Step 4: Commit** `docs: describe leading punctuation following the text` (readme) and `docs: note the leading-digit correction in the script-digit spec` (spec), two commits.

### Task 9: Mutation testing and full verification

**Files:**
- Ledger only (`.superpowers/sdd/2026-11-09-fix-leading-punctuation-language/progress.md`); tests added for killable survivors go to the files of Tasks 1–5.

**Interfaces:** none.

- [ ] **Step 1:** In a scratch copy of the worktree (with `ref` symlinked), set `[tool.mutmut] source_paths` to `languageDetection/detector.py`, `pipeline/punctuation.py`, `pipeline/breaks.py`; `mutmut run --max-children 3` under the memory guard.
- [ ] **Step 2:** For each survivor: kill it with a test when it is a real gap (TDD, commit `test: …`), else record it as equivalent with its reason in the ledger.
- [ ] **Step 3:** Full verification (§7): `python3 -m pytest -q tests` (report against 3808/0 and explain the delta), `prek run --all-files`, `git diff --check master`, both protected-path commands print nothing.

---

## Self-Review

- **Spec coverage:** U1/U2/U9/D1–D4 → Task 4; U5/U6/D8/D12 → Tasks 1–3; D3/D9 → Tasks 4–5; U7/U8/D10/D11 → Task 5; D5 → Tasks 4–5; D6 and §4.3 → Task 7; D7 → Task 4 spelling test; D13 → Tasks 1, 4, 6; §3/§7.4 → Task 6 (the two-utterance row at detector level, Task 5 — the speak harness cannot take `EndUtteranceCommand`, F9); §5 → Task 8; §7.5 → Task 9; §7.6 manual items stay for the hand-off.
- **Step scan:** code steps give signatures, files and the spec's values; the run-planning algorithm is described where the tests do not determine it (stretches, came-before, stops).
- **Type consistency:** `is_internal_break(command) -> bool` (Tasks 1, 4, 6); `InternalPunctuationBreakCommand`, `UnspacedSpaceBreakCommand` (Tasks 1–4, 7); `master_detection(detector, speech_sequence)` (Task 7); `spoken(result)` (Tasks 6, 7).
- **Review Focus:** five items, each with its test in Tasks 4, 5 and 6.
- **Proportion:** shorter than the spec; test listings are cases, not bodies.
