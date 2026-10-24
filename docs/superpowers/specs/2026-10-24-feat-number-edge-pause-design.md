# Number edge pause: a pause before and after every number in digit and group modes

Date: 2026-10-24.
Baseline: `master` `8612c3d`. Branch: `feat/number-edge-pause`, worktree `/workspace/WorldVoice-number-edge-pause` (`ref` symlinked to `/workspace/WorldVoice/ref`).
Baseline numbers: `python3 -m pytest -q tests` → 2610 passed, 0 skipped; `prek run --all-files` all Passed.
Flow: normal flow (`DEVELOPMENT_WORKFLOW.md` §3.1).

Status:

- U1–U5 were decided by the user (2026-10-24).
- U1 was narrowed by the user the same day, in answer to Q1: edge pauses only in the number (digit) and group modes.
- O1–O6 were shown to the user by the orchestrator.
- D1–D10 are defaults added while writing this spec (§11).
- No question is open.

References used throughout:

- Pipeline stages: `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (below: `pipeline:<line>`).
- Number definitions: `addon/synthDrivers/WorldVoice/pipeline/numbers.py` (below: `numbers:<line>`).
- Pipeline settings table: `addon/synthDrivers/WorldVoice/pipeline/settings.py` (below: `psettings:<line>`).
- Synth: `addon/synthDrivers/WorldVoice/__init__.py` (below: `synth:<line>`).
- Detector: `addon/synthDrivers/WorldVoice/languageDetection/__init__.py` (below: `detection:<line>`).
- Speech settings dialogs: `addon/globalPlugins/WorldVoice/speechSettingsDialog.py` (below: `dialog:<line>`).
- NVDA: `ref/nvda/source/...`.

The design (§4) was prototyped in a scratch copy of the worktree, which was not committed. After the U1 narrowing, the prototype was rebuilt and run again:

- The existing suite failed on behaviour in exactly the 11 expectations listed in §8.1.
- The prototype produced every sequence in §5, both the stage output and the full `STAGES` output.
- It ran the speak harness of `tests/test_worldvoice_speak.py` for §4.8.
- A Hypothesis check, 4000 examples, passed: an edge break never meets another break after all stages, and the number stage adds no edge break in value or "none" mode. The examples covered:
  - roles on and off;
  - number language default, main and en;
  - punctuation on and off;
  - random item, Chinese-space and number waits.
- A second check ran on the first prototype, the one with edge pauses in every mode: 3000 examples, comparing at pause 0 after stripping each text item and dropping blank ones. With a pause of 0 the new stage equaled today's two stages. The narrowing does not change output at pause 0, so that result still holds. It extends to value mode at any pause, because the value-mode output of the new stage does not depend on the pause (§4.2 step 4).

## 0. Findings and the resolved question

### F1 / Q1 (resolved). Which numbers get the edge pause

- **What F1 raised.**
  - The pause would be on by default. `scaled_number_wait()` is `global_wait_factor // 10 * number_wait_factor` (`psettings:309-313`). Both factors default to 10 (`psettings:143-154`, `psettings:200-209`). The default number mode is value (`psettings:170-183`).
  - Every edge break splits the text into separate engine pieces. WorldVoice turns a break into `Pause` (`compat/commands.py:15-16`). The request builder flushes the text before it and appends a separate break task (`runtime/requestBuilder.py:44-50`, `runtime/scheduler.py:231-236`). NVDA processes symbols item by item after the filters (`ref/nvda/source/speech/speech.py:1137`, `:1216-1231`).
  - With U3 the split also cuts words that hold digits (`1st`, `MP3`, `10am`, `$5`), and it moves the punctuation that ends a sentence into a piece of its own (`Is it 5?`).
- **Decided by the user (2026-10-24):** option A. U3 stays as decided, with the edge pause next to any neighbour, letters included. But U1 is narrowed: edge pauses are added only in the number (digit) and group modes. Value mode and "none" get no edge pause (§2.1).
- **Consequences of the narrowing:**
  - **Default settings are unaffected.** Value mode is the default, so a user who never chose digit or group mode hears no change. The phase 35 rows that keep a number in its whole item for NVDA's context rules run in value mode (`tests/test_worldvoice_speak.py:540-571`). They hold at any pause.
  - **F1's examples now apply only in the number and group modes.** There, digits are already split into separate pieces today (`pipeline:393-408`). What is new:
    - a number of one piece is also set apart from the text: `the 1st item` and `MP3` stay whole today in number mode;
    - the first and last pieces no longer stick to the letters next to them.

    §8.6 item M6 records what the engines say. Examples:

| Text, number mode, number wait 10 | Today | After |
|---|---|---|
| `the 1st item` | `the 1st item` | `the` \| `1` \| `st item` |
| `MP3` | `MP3` | `MP` \| `3` |
| `10am` | `1` \| `0am` | `1` \| `0` \| `am` |
| `Is it 5?` | `Is it 5?` | `Is it` \| `5` \| `?` |

### F2 (for information). O4 changes nothing by itself

- Today, in number language "Follow"/"main" or for a synth without roles, the mode stage cuts `"COVID-19"` as the match `-19` (`pipeline:449-471`, `numbers:22`). The pieces are then merged back with the text: `"COVID-1"`, NB, `"9"` in number mode; `"COVID-19"` in value mode.
- NVDA's negative-number rule needs the `-` not to follow a word character (`ref/nvda/source/locale/en/symbols.dic:19`, `ref/nvda/source/locale/zh_TW/symbols.dic:21`). So today the `-` is never read as a minus sign there.
- With edge breaks, a `NUMBER_RE` span would make `"-1"` or `"-19"` an item of its own, and NVDA would read "minus". Using the hyphen-rule spans (O4) keeps today's reading.
- Without edge breaks the hyphen-rule spans give exactly today's strings, because `merge_consecutive_strings` joins `"COVID-"` and `"1"` again. This covers value and "none" mode at any pause, and every mode at pause 0 (prototype oracle above).
- The only audible change is the edge pause between `COVID-` and the first digit, in the number and group modes (§3).

### F3 (orchestrator default, user may override). A plain edge `NumberBreakCommand` would shorten every punctuation pause next to a number

- The punctuation stage lets any break waiting between two items suppress the boundary pause of the item before it (`pipeline:574-577`, `:658`). If the edge pause were a plain `NumberBreakCommand`, `"Total. 12"` in number mode with `.` configured would get the 10 ms number pause where it gets the punctuation pause today, for example 250 ms.
- Removal would also leave a number break and a punctuation break side by side: `"3，下"` would become `"3"`, NB, PB, `"下"`.
- O5's "reuse the existing dedupe" is not enough. The existing rule (review M2, `pipeline:581-585`, `:660-667`) only covers two number breaks around an item that removal empties.
- This spec therefore:
  - gives the edge pause its own class, `NumberEdgeBreakCommand(NumberBreakCommand)`;
  - adds two rules that apply to that class only (§4.6.3).

  Every existing rule, test and earlier decision about `NumberBreakCommand` stays as it is.

## 1. Problem

- In number and group modes, the pieces of a number are pauses apart, but the first and last pieces stay glued to the text around them: `"第123章"` is read as `第1` | `2` | `3章`.
- When the number language equals the language of the surrounding text, nothing else separates a number from its neighbours. Examples: "Follow current text language" (the default), or a locale whose voice is the voice in force. A language switch around the number is the only thing that sets it apart today, and it exists only when the number language's voice differs (`pipeline:304-319`, `:681-730`).
- The existing number pause (`number_wait_factor`, `pipeline:198-241`) separates numbers only from each other: `"1 2"`, and adjacent number items.

## 2. Goals and non-goals

### 2.1 Goals (decided by the user, 2026-10-24)

- **U1 (amended by the user, 2026-10-24, in answer to Q1).** Every number gets a pause before and after it, but only when the number mode is "number" (digit by digit) or "group". In value mode and "none" there is no edge pause. In those two modes, number-language handling, the dot rule (value) and the thousands step (value) run as today.
- **U2.** The pause time is the existing number pause, `settings.scaled_number_wait()` (`psettings:312-313`). There is no new setting.
- **U3.** The pause is added whatever the neighbour is: text, whitespace or punctuation, letters included (confirmed by the Q1 answer). `"共 3 章"` and `"第3。"` both get it on both sides.
- **U4.** A pause time of 0 means no edge break at all.
  - Unchanged: the between-numbers pause (`number_wait_factor`, `pipeline:209-212`) still adds nothing at 0.
  - Unchanged: the number- and group-mode piece separators in `_translate_number` still insert `NumberBreakCommand` even at 0 (`pipeline:393-408`). They make each piece an item of its own.
  - Reason, agreed with the user:
    - a `BreakCommand(0)` still becomes `Pause(0)` (`compat/commands.py:15-16`), and the request builder flushes a separate task around it (`runtime/requestBuilder.py:44-50`);
    - 0 also means "pauses off": `PipelineSettings.effective` zeroes the number wait for other synths outside scope "all" (`psettings:330-349`), and a global factor below 10 makes `global_factor_units` 0 (`psettings:309-310`).
- **U5.** Numbers are found once, with the number-language rule: `_split_numbers_for_language` (`pipeline:117-136`), that is, `NUMBER_RE` (`numbers:22`) plus the hyphen rule. For each number, three things happen in order:
  1. edge pauses;
  2. number language;
  3. number mode.

  This merges today's `inject_number_language` and `inject_number_mode` stages (`STAGES`, `pipeline:875-885`) into one number stage.

### 2.2 Orchestrator calls shown to the user (Decided by orchestrator; user may override before merge)

- **O1.** The edge break sits outside the language wrapper: `第`, Break, Lang(num), pieces…, Lang(cur), Break, `章`.
- **O2.** An edge break is added only on a side where the same text item has content next to the number. Whitespace counts as content (U3), refined by D1. A number at the very start or end of an item gets no break on that side; item boundaries are `item_wait_factor`'s job.
- **O3.** Two numbers separated only by whitespace (`"1 2"`) get exactly one `NumberBreakCommand` between them, never two or three.
  - In the number and group modes, the number stage does this (§4.3).
  - In value and "none" modes, `number_wait_factor` does it, as today.
  - The output is today's in every mode (§4.6.4).
- **O4.** The number and group modes now use the hyphen-rule spans. See F2 and §3 for the effect.
- **O5.** The punctuation pause keeps working, and a number break never stacks on it (§4.6.3; extended by F3/D2).
- **O6.** Language detection runs after `STAGES` and passes breaks through (§4.8). No code changes there, only tests.

### 2.3 Non-goals

- `NUMBER_RE`, `SYMBOLS`, the sign and hyphen rules, the digit set (`numbers:11-28`), `number_pieces` (`numbers:63-90`), and symbol naming (`pipeline/symbols.py`).
- The code of `number_wait_factor`, `split_spaced_numbers`, `_insert_number_breaks` and `_remove_space` stays unchanged (`pipeline:165-241`, `numbers:36-60`).
- The thousands step `remove_thousands_separators` stays unchanged and stays the stage before the number stage (`pipeline:58-71`, `:877`). It acts in value mode only, where there are no edge breaks, so the two never interact.
- Language detection, `wrap_numbers_for_detection` and `detect_with_number_language` (`pipeline:322-390`) stay unchanged.
- The pre-existing loss of a punctuation pause in front of a number wrapped for another voice stays as it is (`"Total. 12"` with a locale, phase 35 F2, `tests/test_worldvoice_speak.py:443-449`).
- Any engine wrapper, the upstream drivers under `driver/<Engine>/driver/`, and Neural.

## 3. User-visible changes

What NVDA users hear with number wait 10 ms and "Follow current text language", unless the row says otherwise. "|" is a pause.

| Text, settings | Today | After |
|---|---|---|
| anything in value mode (the default) or "none" | — | unchanged |
| `第3章`, number or group mode | `第3章` | `第` \| `3` \| `章` |
| `第3章`, number mode, number language en (another voice) | `第` (zh) `3` (en) `章` (zh) | `第` \| `3` (en) \| `章` |
| `第123章`, number mode | `第1` \| `2` \| `3章` | `第` \| `1` \| `2` \| `3` \| `章` |
| `第123章`, group mode, size 2 | `第12` \| `3章` | `第` \| `12` \| `3` \| `章` |
| `第3章`, number mode, number wait 0 (or global wait factor below 10) | `第3章` | unchanged |
| `共 3 章`, number mode | `共 3 章` | `共` \| `3` \| `章` |
| `12 34`, number mode | `1` \| `2` \| `3` \| `4` | unchanged (one pause each) |
| `COVID-19`, number mode | `COVID-1` \| `9` | `COVID-` \| `1` \| `9` |
| `the 1st item`, `MP3`, `10am`, `Is it 5?`, number mode | see F1 | see F1 |
| `Total. 12`, number mode, `.` a punctuation pause character (50 ms) | `Total.` \| `1` \| `2` (50 ms first) | unchanged (the 10 ms edge pause merges into the 50 ms one) |
| `第3。下一章`, number mode, `。` configured, remove on | `第3` \| `下一章` | `第` \| `3` \| `下一章` (the last pause is the longer of the two) |
| `1，2`, number mode, `，` configured, remove on | `1，2` (the mark before a digit is not a pause point, `pipeline:520-526`) | `1` \| `2`: the mark is now an item of its own, so it is removed (D2) |
| Another synth, scope "all", number or group mode | as WorldVoice today | edge pauses as plain `BreakCommand`s, same rules |
| Log Record panel | "Number language", "Number mode" switches | the same two switches, each of which logs the merged stage (§4.7) |

- No panel, dialog, control or label changes.
- No new or changed translatable strings.
- The readmes change (§6).

## 4. Design

### 4.1 Terms

- **Item**: one `str` in the speech sequence.
- **Span**: one ("number", text) part of `_split_numbers_for_language(item)` (`pipeline:117-136`). The parts alternate between text and number: the hyphen rule only moves a sign into the text, and `NUMBER_RE` matches never touch (`numbers:42-43`).
- **Content on a side**: the item has a non-whitespace character between the span and that end of the item (D1). The checks are `item[:start].strip()` for the left side and `item[end:].strip()` for the right side.
- **Whitespace gap**: a text part between two spans that is all whitespace (`str.isspace()`). A no-break space counts, as in `split_spaced_numbers` (`numbers:44-46`, decided by the user 2026-10-22).
- **Edge break**: `NumberEdgeBreakCommand(scaled_number_wait())`, a new subclass of `NumberBreakCommand` (`pipeline:35-36`).

  ```python
  class NumberEdgeBreakCommand(NumberBreakCommand):
      """Pause between a number and the text next to it in its item (number and group modes)."""
  ```

  Because it is a `NumberBreakCommand`, every existing `isinstance(…, NumberBreakCommand)` check treats it as a number break. That includes the M2 rule (`pipeline:660-667`) and the tests that collect number breaks.

### 4.2 The number stage: `inject_numbers`

`STAGES` (`pipeline:875-885`) becomes:

```python
STAGES = (
	Stage("apply_speech_dictionaries", apply_speech_dictionaries),
	Stage("number_mode", remove_thousands_separators, log_switch=False),
	Stage("number_mode", inject_numbers, also_logged_by=("number_language",)),
	Stage("chinesespace_wait_factor", inject_chinese_space_pause),
	Stage("item_wait_factor", item_wait_factor),
	Stage("punctuation_wait_factor", inject_punctuation_pause),
	Stage("number_wait_factor", number_wait_factor),
	Stage("speech_viewer", speech_viewer),
)
```

`inject_numbers(speechSequence, settings, ctx)`:

1. `wraps = ctx.supports_roles and ctx.number_language not in (FOLLOW, MAIN)`.
2. **Synth without roles.** Drop every `WVLangChangeCommand` with `remove_language_command` (`pipeline:244-250`), as `inject_number_language` does today (`pipeline:319`). This happens in mode "none" too.
3. **Nothing to do.** If `mode == "none"` and not `wraps`, yield the rest unchanged, the same objects. This keeps today's two pass-throughs:
   - "none" leaves numbers alone, without even the dot rule (`pipeline:417-420`);
   - "Follow"/"main" add no wrapper at this stage (`pipeline:310-316`).
4. **Breaks.**
   - `pause = settings.scaled_number_wait()`.
   - The edge break is `NumberEdgeBreakCommand(pause)` when `mode in ("number", "group")` and `pause > 0`; otherwise there is none (U1, U4).
   - The gap break is one `NumberBreakCommand(pause)` per stage run, under the same condition.
   - In value mode nothing in the stage reads `pause`, so value-mode output is the same at every pause.
5. **Namer.** `namer = symbol_namer(ctx.voice_locale_for_language)`, as today (`pipeline:423-429`). Symbols are named for the number language when `wraps`, else for the language in force.
6. **Walk.** Track the language in force: `language = item.lang or ctx.language` at each `LangChangeCommand`/`WVLangChangeCommand`, as today (`pipeline:268-271`, `:432-434`). Every non-`str` item passes through.
7. **Per item.** Each `str` item goes through `_number_item_segments(item, …)` (§4.3–§4.5). With `wraps`, the result then goes through `deduplicate_language_command(…, ctx, start_language=language)` (`pipeline:274-278`; phase 30 item 6). Finally it goes through `merge_consecutive_strings` (`pipeline:474-485`).

`_number_item_segments(item, *, mode, group_size, pause, name_of, number_language, language, edge, gap_break)` is a generator. It handles each part of `_split_numbers_for_language(item)` in order:

- **A text part.**
  - If it is a whitespace gap and there is an edge break, yield `gap_break` in its place (§4.3).
  - Otherwise yield the text, with the dot rule (§4.5).
- **A number span.** Yield, in this order:
  1. the left edge break (§4.3);
  2. `WVLangChangeCommand(number_language)` when wrapping;
  3. the span as is in mode "none", otherwise `_translate_number(span, mode, group_size, pause, name_of)` (`pipeline:393-408`, unchanged; in value mode it yields the span unchanged);
  4. `WVLangChangeCommand(language)` when wrapping;
  5. the right edge break.

### 4.3 The edge rule (U1, U3, U4, O1, O2, O3, D1, D6)

- **Where.** In the number and group modes, with a pause above 0, an edge break goes on each side of a span where the item has content on that side (§4.1). There is no edge break:
  - in value mode or "none";
  - when `pause <= 0`;
  - at the start or end of an item;
  - where only whitespace lies between the span and the item's end (D1).
- **Position (O1).** The edge break goes outside the wrapper: left edge, opening wrapper, pieces, closing wrapper, right edge. The closing wrapper names the language in force, as today (`pipeline:301`).
- **Whitespace gaps (O3, D6).** When there are edge breaks, two spans separated only by whitespace get one `NumberBreakCommand`, the gap break, in place of the gap. The right edge of the first span and the left edge of the second are not added.
  - This is the result `number_wait_factor` gives for such text today (`pipeline:198-241`, `numbers:36-60`): one number break replaces the whitespace.
  - The gap break is a plain `NumberBreakCommand`, not an edge break, because it is a pause between two numbers.
  - Without edge breaks (value mode, "none", or pause 0), the gap stays text and `number_wait_factor` handles it as today.
- **Other gaps.** A gap that holds anything besides whitespace is ordinary text, and it gets an edge break on each side (U3). Examples: `"1，2"`, `"1, 2"`.
  - If the mark is silent at the user's symbol level, the listener hears two number pauses in a row. That is accepted under U3.
  - With the punctuation pause on and the mark configured, §4.6.3 merges the two into one.
- **One edge-break instance per stage run.** It is shared like `number_wait_factor`'s break (`pipeline:213-216`). The synth only reads its time, and no code compares breaks by identity.

### 4.4 Number language inside the stage

- The wrapper is exactly today's (`pipeline:296-301`). It applies only for a locale number language (`wraps`): opening `WVLangChangeCommand(ctx.number_language)`, closing `WVLangChangeCommand(language in force)`. It is deduplicated per item, with `start_language` set to the language in force.
- "Follow" and "main" add no wrapper here, as today (`pipeline:310-316`). "main" numbers are still wrapped where detection runs (`detect_with_number_language`, `pipeline:358-390`; phase 35 §4.4).
- A synth without roles gets no wrapper, and incoming `WVLangChangeCommand`s are dropped (§4.2 step 2).

### 4.5 Number mode inside the stage

- **Pieces and separators.** `_translate_number` is unchanged (`pipeline:393-408`): one separator instance per number, present even at pause 0 (U4).
- **Spans.** The hyphen-rule spans are used (U5, O4). A span's sign after a word character is in the text part, so in the number and group modes it is no longer part of the first piece. Without edge breaks, the merged strings are identical to today's (F2).
- **Symbol names.** They use the locale of the number language when wrapping, else that of the language in force, as today (`pipeline:424-429`, `:442`).
- **Dot rule (D5).** Today's rule (`pipeline:457-470`) applies to the item's text parts in every mode but "none":
  - a text part right after a number that starts with `"."` gets a leading `" "`;
  - a text part right before a number that ends with `"."` gets a trailing `" "`.

  The rule now depends only on the item's text, not on whether a wrapper is kept. Today, with a locale wrapper whose voice differs, the mode stage saw `"12"` and `"."` as separate strings and added no space (phase 35 F2). Now:
  - `"12. Next"` in value mode with number language en gives `L(en) "12" L(zh) " . Next"` instead of `L(en) "12" L(zh) ". Next"` (§5 row 23).
  - Nothing is audible. NVDA strips every text item in `processText` (`ref/nvda/source/speech/speech.py:214`) before any synth sees it (`:1225-1231`). With an edge break, `number_wait_factor`'s `_remove_space` also strips the item later (`pipeline:165-187`).
  - The P8 docstring note about this difference becomes obsolete (`tests/test_pipeline_pause_properties.py:742-750`, final review M5).

### 4.6 The later stages

#### 4.6.1 Chinese space (`pipeline:488-511`)

The Chinese-space pattern needs a CJK character on both sides of the space inside one item (`pipeline:32`). Edge breaks only cut an item at a number, so they never separate a CJK character from the space next to it. In `"中 文3"`, the part `"中 文"` still gets its Chinese-space pause.

#### 4.6.2 Item wait (`pipeline:152-162`)

- The item wait breaks only between two adjacent `str` items. An edge break always has non-blank text of its own item between it and the item's end (D1), so an item break is never placed next to an edge break.
- Items that are separated only by formatting or an index command get no edge break (O2): `"第"`, IndexCommand, `"3"`, IndexCommand, `"章"` in browse mode (§5 row 28).

#### 4.6.3 Punctuation pause (O5, F3, D2, D3)

`inject_punctuation_pause` (`pipeline:549-678`) changes in two places, and both act on edge breaks only. `_is_edge_break(command)` is true for a `NumberEdgeBreakCommand`, and for a plain `BreakCommand` that carries the edge marker of D3.

- **E1. An edge break does not suppress a boundary pause.**
  - Today `emit(previous, text_follows and not pending_breaks, text_follows)` (`pipeline:658`) suppresses the boundary pause whenever any break waits.
  - Now it is suppressed only when a waiting break is not an edge break: `text_follows and all(_is_edge_break(b) for b in pending_breaks)`.
  - Breaks that are not edges keep today's rule: an existing break, a separator `NumberBreakCommand`, or a plain break of another synth's number pieces (P4b, `tests/test_pipeline_pause_properties.py:165-180`).
- **E2. Breaks that meet around an edge break collapse into one.**
  - **Run.** A run is everything between two non-blank text items in the stage's output, or before the first or after the last one: breaks, blank text, and other commands such as language and index commands.
  - **Rule.** When a run holds two or more `BreakCommand`s and at least one of them is an edge break, only one break of the run is kept:
    - the longest;
    - on a tie, the first that is not an edge break;
    - if all are edge breaks, the first.

    The run's other items keep their order.
  - **Runs without an edge break are untouched.** The following keep their current behaviour and tests (`tests/test_pipeline_punctuation_pause.py:227-266`, `tests/test_pipeline_passthrough.py:203-212`):
    - the M2 rule (`pipeline:660-667`);
    - "removal changes only marks around any other break" (`test_property_removal_changes_only_the_marks`);
    - "a number break counts as an existing pause".
  - **Coverage.** E2 runs over the whole output of the active stage, the last item included. Today's final `emit` (`pipeline:677-678`) bypasses the M2 check; E2 must not. Implementation: `inject_punctuation_pause` yields from `_merge_edge_breaks(<today's loop>)` after its early returns (`pipeline:587-596`).
  - **When the stage is off,** E2 does not run. Property P-E5 (§8.3) shows that edge breaks cannot meet another break without this stage:
    - an edge break always has non-blank text of its own item on its outer side;
    - every other break the stages make sits between spoken text.
- **Why "longest" and not "the earlier one" (M2).**
  - Where a punctuation pause and an edge pause fall on one spot, the punctuation pause is the one the user tuned for that mark, and it is usually the longer one. Keeping the earlier break would make `"Total. 12"` lose its 50–500 ms pause to the 10 ms edge.
  - Keeping the longer one also keeps the number separated when the punctuation pause is 0 ms (§5 rows 35, 44).
  - Number breaks in one run all have the same time (`scaled_number_wait()`), so M2's "earlier" choice is unaffected.
- **Results** (prototype, number mode, punctuation wait 50 ms, number wait 10 ms):

| Input | Removal off | Removal on |
|---|---|---|
| `"第3。"`, `"3，"` (nothing follows) | `"第"`, E10, `"3"`, E10, `"。"` | the same |
| `"第3。下一章"` | `"第"`, E10, `"3"`, E10, `"。"`, PB50, `"下一章"` | `"第"`, E10, `"3"`, PB50, `"下一章"` |
| `"3，下"` | `"3"`, E10, `"，"`, PB50, `"下"` | `"3"`, PB50, `"下"` |
| `"Total. 12"` | `"Total"`, `"."`, PB50, `"1"`, NB10, `"2"` | `"Total"`, PB50, `"1"`, NB10, `"2"` |

  - With nothing following, there is no punctuation pause, as today: the mark at the end of the sequence is never a pause point (`pipeline:569-570`).
  - The `"Total. 12"` results match today: the same pause before the number.
- **D3: synths without roles.**
  - For another synth, `_stage_handler` turns every break subclass into a plain `BreakCommand` after each stage (`pipeline:832-847`), because NVDA's `speechXml` picks a converter by class name (`ref/nvda/source/speechXml.py:256-258`). The punctuation stage could then not tell an edge break from any other break.
  - So `_plain_breaks` sets the attribute `worldvoice_number_edge = True` on the plain `BreakCommand` it makes from an edge break. The class stays NVDA's `BreakCommand`:
    - it has no `__slots__`;
    - its `__eq__` compares only type and time (`ref/nvda/source/speech/commands.py:200-218`);
    - OneCore, SAPI5 and eSpeak read only `.time`, so the attribute is invisible to them.
  - Existing number and punctuation breaks get no marker. The documented limit for other synths (`tests/test_pipeline_filters.py:598-626`, number-unify spec 6.4.1) stays as it is.

#### 4.6.4 Number wait (`pipeline:198-241`)

The code is unchanged.

- **Value mode and "none":** it splits `"1 2"` and breaks between whole-number items, as today.
- **Number and group modes:**
  - The number stage has already replaced every whitespace gap with one number break (§4.3). `split_spaced_numbers` finds nothing more to split, and `_insert_number_breaks` sees a break instead of two adjacent numbers, so it adds nothing.
  - O3 holds: `"12 34"` gives `"1"`, NB, `"2"`, NB, `"3"`, NB, `"4"`. With a locale, `"1 2"` gives `L(en) "1" L(zh)`, NB, `L(en) "2" L(zh)`. Both are today's output.
  - Whole-number items still get its break, as in `["1", "2"]`. A number alone in its item has no edge break (O2), so the two never meet.
  - `_remove_space` strips every text item whenever the number wait is above 0 (`pipeline:165-187`, `:209-216`), and edge breaks exist only then. So `"共 "`, E, `"3"`, E, `" 章"` reaches the synth as `"共"`, E, `"3"`, E, `"章"`.

#### 4.6.5 In `speak` (`synth:314-330`)

- `inject_langchange_reorder` moves each language command in front of the commands buffered before it (`pipeline:749-782`). So the left edge break reaches the request builder after the voice switch: `"第"`, SelectVoice(en), Pause, `"3"`, SelectVoice(zh), Pause, `"章"`.
- A break task has no voice (`runtime/scheduler.py:231-236`), so nothing audible changes. Today's `"1 2"` with a locale already has this shape.

### 4.7 Logging (D4)

- **How logging works today.**
  - `_run_logged` turns a stage's log on by the switch named by its log key (`pipeline:811-829`).
  - `LOG_SWITCHES` derives one switch per log key from `STAGES` (`pipeline:888-889`).
  - The Log Record panel lists one checkbox per switch (`dialog:39-49`, `:643-649`), and the confspec has one boolean per switch (`synth:83-86`).
  - A plain merge under log key `"number_mode"` would drop the "Number language" switch from the panel, from the confspec and from users' stored profiles.
- **Conservative default.**
  - `Stage` gains `also_logged_by: tuple[str, ...] = ()`: the switches that also turn this stage's log on.
  - `LOG_SWITCHES` lists, for each stage with `log_switch=True`, its `also_logged_by` keys and then its `log_key`, each key once, in order. The result is today's tuple: `("apply_speech_dictionaries", "number_language", "number_mode", "chinesespace_wait_factor", "item_wait_factor", "punctuation_wait_factor", "number_wait_factor", "speech_viewer")`.
  - `_stage_handler(log_key, fn, switches)` passes `(*also_logged_by, log_key)` to `_run_logged`. The stage logs when the debug level or the record switch is on (unchanged) and any of those switches is on.
  - Rows are labelled with the log key, `"number_mode"`.
- **What users see.**
  - The Log Record panel shows the same two checkboxes with the same labels ("Number language" and "Number mode", from `display_name` at `psettings:165`, `:179`).
  - Stored `[WorldVoice][log]` keys keep working.
  - "Number language" alone logs the number stage once. "Number mode" logs the thousands step and the number stage, as today (`tests/test_pipeline_stages.py:46-59`).
- The translator comments at `psettings:163-165` and `:177-178` stay true.
- `tests/nvda_stubs.py:103-118` derives the log confspec from the AST of `STAGES`. It must also read the `also_logged_by` keyword.

### 4.8 Language detection (O6)

- Detection timed "before" is an NVDA filter, and `order_move_to_start_register` moves all of `STAGES` in front of it (`synth:460-469`, `pipeline:892-895`). Detection timed "after" runs in `speak` (`synth:317-318`). Both see the number stage's output.
- The detector passes any non-language command through without touching `tmpLang` (`detection:149-174`, the `else` at `:173-174`). It keeps a decimal digit in the current run (`detection:138-143`).
- `wrap_numbers_for_detection` wraps a number that is now alone in its item. Its `joins` are false on both sides, so dropping a redundant wrapper glues nothing (`pipeline:343-355`, `:379-390`).
- No code changes.

Prototype run through the speak harness. Timings "after" and "before" gave identical results. In value mode at number wait 10, every row equals today's. The number-mode column at wait 0 is today's output. At wait 10 the voices stay the same and only breaks are added; leading and trailing spaces are stripped by `_remove_space`.

| Text | Number language | Main voice | Number mode, wait 0 (today) | Number mode, wait 10 |
|---|---|---|---|---|
| `第3章` | default / main | zh | `[(ZH, "第3章")]` | `[(ZH, "第"), "\|", (ZH, "3"), "\|", (ZH, "章")]` |
| `第3章` | en | zh | `[(ZH, "第"), (EN, "3"), (ZH, "章")]` | `[(ZH, "第"), "\|", (EN, "3"), "\|", (ZH, "章")]` |
| `中12` | main | en | `[(ZH, "中"), (EN, "1"), "\|", (EN, "2")]` | `[(ZH, "中"), "\|", (EN, "1"), "\|", (EN, "2")]` |
| `中12` | default | en | `[(ZH, "中1"), "\|", (ZH, "2")]` | `[(ZH, "中"), "\|", (ZH, "1"), "\|", (ZH, "2")]` |
| `abc3中` | default | en | `[(EN, "abc3"), (ZH, "中")]` | `[(EN, "abc"), "\|", (EN, "3"), "\|", (ZH, "中")]` |
| `中 COVID-19 中` | main | zh | `[(ZH, "中 "), (EN, "COVID-"), (ZH, "1"), "\|", (ZH, "9 中")]` | `[(ZH, "中 "), (EN, "COVID-"), "\|", (ZH, "1"), "\|", (ZH, "9"), "\|", (ZH, "中")]` |
| `中 -12 34` | main | en | `[(ZH, "中 "), (EN, "-1"), "\|", (EN, "2 3"), "\|", (EN, "4")]` | `[(ZH, "中"), "\|", (EN, "-1"), "\|", (EN, "2"), "\|", (EN, "3"), "\|", (EN, "4")]` |
| `abc 123 def` | zh_TW | zh | `[(EN, "abc "), (ZH, "1"), "\|", (ZH, "2"), "\|", (ZH, "3 "), (EN, "def")]` | `[(EN, "abc"), "\|", (ZH, "1"), "\|", (ZH, "2"), "\|", (ZH, "3"), "\|", (EN, "def")]` |

### 4.9 Code removed, kept and added

- **Removed from `pipeline/__init__.py`:**
  - `_insert_WVLangChangeCommand_between_number` (`:253-279`);
  - `iter_number_speech_segments_language` (`:282-301`);
  - `inject_number_language` (`:304-319`);
  - `inject_number_mode` (`:411-446`);
  - `iter_number_speech_segments_mode` (`:449-471`).

  Nothing outside the pipeline and the tests uses them (grep of `addon/` and `tests/`).
- **Kept:** `remove_language_command`, `_translate_number`, `merge_consecutive_strings`, `deduplicate_language_command` and `_split_numbers_for_language`. `_split_by` also stays; the Chinese-space and punctuation stages still use it.
- **Added:** `NumberEdgeBreakCommand`, `inject_numbers`, `_number_item_segments`, `_is_edge_break`, `_merge_edge_breaks` and `Stage.also_logged_by`.
- **Docstrings:**
  - `NumberBreakCommand` (`:36`) adds "and between two numbers that only whitespace separates, in number and group modes".
  - `inject_punctuation_pause` (`:554-586`) gains E1 and E2.
- `pipeline/numbers.py` and `pipeline/symbols.py` are untouched. So `test_number_lexing_imports_only_the_standard_library` and the `MOVED` guard (`tests/test_pipeline_structure.py:41-123`) still hold.
- **Simplification from the narrowing.** Value mode never has edge breaks, so:
  - there is no interaction with the thousands step;
  - the value path of the stage is today's composition, with the wrapper and the dot rule, and it does not read the pause;
  - the punctuation rules E1 and E2 and the D3 marker only ever see edge breaks from the number and group modes.

  No part of the design existed only for value mode, so nothing could be removed. The number and group modes still need every part: the gap break, E1, E2 and D3.

## 5. Worked examples

These are prototype outputs: the stage output of `inject_numbers` and the output after every stage of `STAGES`.

- Context: a WorldVoice context, language zh, voices `{"zh": Z, "en": E}`.
- Default settings: **number mode**, number wait 10, punctuation wait 50, item and Chinese-space waits 0, group size 3. A row only names what differs.
- Notation:
  - `E10` is an edge break;
  - `NB10` is a `NumberBreakCommand` (separator or gap break);
  - `PB50` is a punctuation break;
  - `L(x)` is `WVLangChangeCommand(x)`;
  - `B10*` is a plain `BreakCommand` with the edge marker.
- "same" means the full output equals the stage output.

| # | Input, settings | `inject_numbers` output | After all `STAGES` |
|---|---|---|---|
| 1 | `第3章`, number or group | `第` E10 `3` E10 `章` | same |
| 1v | `第3章`, value | `第3章` | same (today's) |
| 2 | `第3章`, en | `第` E10 L(en) `3` L(zh) E10 `章` | same |
| 2v | `第3章`, value, en | `第` L(en) `3` L(zh) `章` | same (today's) |
| 3 | `第123章` | `第` E10 `1` NB10 `2` NB10 `3` E10 `章` | same |
| 4 | `第123章`, group 2 | `第` E10 `12` NB10 `3` E10 `章` | same |
| 5 | `第123章`, en | `第` E10 L(en) `1` NB10 `2` NB10 `3` L(zh) E10 `章` | same |
| 6 | `第3章`, none | `第3章` (the same object) | same |
| 7 | `第3章`, none, en | `第` L(en) `3` L(zh) `章` (today's) | same |
| 8 | `共 3 章` | `共 ` E10 `3` E10 ` 章` | `共` E10 `3` E10 `章` |
| 8v | `共 3 章`, value | `共 3 章` | same (today's) |
| 9 | `1 2` | `1` NB10 `2` | same (today's) |
| 9v | `1 2`, value or none | `1 2` | `1` NB10 `2` (by `number_wait_factor`, as today) |
| 10 | `1 2`, en | L(en) `1` L(zh) NB10 L(en) `2` L(zh) | same (today's) |
| 11 | `12 34` | `1` NB10 `2` NB10 `3` NB10 `4` | same (today's) |
| 13 | `COVID-19` | `COVID-` E10 `1` NB10 `9` | same |
| 13g | `COVID-19`, group | `COVID-` E10 `19` | same |
| 13v | `COVID-19`, value | `COVID-19` | same (today's) |
| 15 | `-5` | `-5` | same |
| 16 | `a -5` | `a ` E10 `-5` | `a` E10 `-5` (NVDA reads `-5` alone as "minus 5", as it reads `a -5` today) |
| 17 | `x-5` | `x-` E10 `5` | same |
| 18 | `35.` | `3` NB10 `5` E10 ` .` | `3` NB10 `5` E10 `.` |
| 19 | `1.` | `1` E10 ` .` | `1` E10 `.` |
| 20 | `a.5` | `a. ` E10 `5` | `a.` E10 `5` |
| 21 | `There are 5. Next` | `There are ` E10 `5` E10 ` . Next` | `There are` E10 `5` E10 `. Next` |
| 22 | the same, `.` configured | as row 21 | `There are` E10 `5` E10 `.` PB50 `Next` |
| 23 | `12. Next`, value, en, wait 0 | L(en) `12` L(zh) ` . Next` (today: `. Next`, D5) | same |
| 24 | `3` | `3` | same |
| 25 | `第3章`, wait 0 | `第3章` | same (today's) |
| 26 | `the 1st item` | `the ` E10 `1` E10 `st item` | `the` E10 `1` E10 `st item` (F1) |
| 26a | `MP3` | `MP` E10 `3` | same (F1) |
| 26b | `10am` | `1` NB10 `0` E10 `am` | same (F1) |
| 26v | `the 1st item`, value | `the 1st item` | same (today's) |
| 27 | `Is it 5?` | `Is it ` E10 `5` E10 `?` | `Is it` E10 `5` E10 `?` (F1) |
| 28 | `第`, Index, `3`, Index, `章` | unchanged | unchanged (O2) |
| 29 | `第3章`, no roles (scope "all") | `第` B10* `3` B10* `章` | same |
| 30 | `WV("en")`, `第3章`, no roles, number language en | `第` B10* `3` B10* `章` (WV command dropped, no wrapper) | same |
| 31 | `第3。`, `。` configured, remove off or on | `第` E10 `3` E10 `。` | same |
| 32 | `3，`, `，` configured, remove off or on | `3` E10 `，` | same |
| 33 | `第3。下一章`, `。` configured | `第` E10 `3` E10 `。下一章` | `第` E10 `3` E10 `。` PB50 `下一章` |
| 34 | the same, remove on | as row 33 | `第` E10 `3` PB50 `下一章` |
| 35 | the same, remove on, punctuation wait 0 | as row 33 | `第` E10 `3` E10 `下一章` |
| 36 | `3，下`, `，` configured | `3` E10 `，下` | `3` E10 `，` PB50 `下` |
| 37 | the same, remove on | as row 36 | `3` PB50 `下` |
| 38 | `Total. 12`, `.` configured | `Total. ` E10 `1` NB10 `2` | `Total` `.` PB50 `1` NB10 `2` (today's pause before the number) |
| 38v | the same, value | `Total. 12` | `Total` `.` PB50 `12` (today's) |
| 39 | `Total. 12`, `.` configured, remove on | as row 38 | `Total` PB50 `1` NB10 `2` |
| 40 | `1，2` (no punctuation pause) | `1` E10 `，` E10 `2` | same (two pauses; today `1，2`) |
| 41 | `1，2`, `，` configured | as row 40 | `1` E10 `，` PB50 `2` |
| 42 | the same, remove on | as row 40 | `1` PB50 `2` |
| 42v | the same, value | `1，2` | same (today's) |
| 43 | `1 ` (trailing space) | `1 ` | `1` (no edge break, D1) |
| 44 | `Total. 12`, `.` configured, punctuation wait 0 | as row 38 | `Total` `.` E10 `1` NB10 `2` |
| 45 | `["3，", "下"]`, `，` configured, remove on, item wait 30 | `3` E10 `，`, `下` | `3` B30 `下` (the item break is the longest) |
| 46 | `12,345元`, value | `12345元` (thousands step first) | same (today's) |

Rows 31–45 were not run for another synth in scope "all". From row 29 and §4.6.3, they give the same sequences with every break plain.

## 6. Panels, strings and documentation

- **Panels and dialogs:** no changes.
  - No control is added, removed or renamed.
  - The focus order and the names NVDA reads stay the same.
  - The Log Record panel keeps its two number switches (§4.7).
- **Translatable strings:** none added or changed. "Number wait factor" / 數字停頓參數 (`addon/locale/zh_TW/LC_MESSAGES/nvda.po:410-411`) now also sets the edge pause in the digit and group modes. Keeping the label is the conservative default (D8).
- **Readmes (D8):** change `readme.md` and `addon/doc/zh_TW/readme.md` only. The ru, uk, zh_CN and zh_HK readmes stay untouched, as in phase 35 Q9.
  - Add to the "Speech pause adjustment" bullet (`readme.md:53`, `addon/doc/zh_TW/readme.md:53`):
    - EN: "In digit mode and group mode, the number pause is also placed before and after every number that touches other text in the same item, as in "第3章", even when the number is read in the same language as the text. Numeric mode and Off add no such pause, and a number pause of 0 adds none."
    - zh_TW: 「在數字模式與群組模式中，數字停頓也會加在每個數字的前後（數字與同一段文字的其他內容相鄰時），例如「第3章」，即使數字與文字以相同的語言朗讀。數值模式與不處理不加這個停頓；數字停頓為 0 時也不加。」
  - Add to the changelog, under "Next update" (`readme.md:73`, `addon/doc/zh_TW/readme.md:73`):
    - EN: "**Pause around numbers in digit and group modes:** In digit mode and group mode, the number pause now also separates every number from the text next to it, as in "第3章", even when the number is read in the same language as the text. Digits next to letters, as in "1st" or "MP3", are set apart too. Numeric mode, the default, is unchanged. Set the number wait factor to 0 to turn the pause off. Where a punctuation pause falls next to a number, only the longer of the two pauses is heard."
    - zh_TW: 「**數字模式與群組模式的數字前後停頓：** 在數字模式與群組模式中，數字停頓現在也會把每個數字與前後的文字分開，例如「第3章」，即使數字與文字以相同的語言朗讀。與字母相鄰的數字（例如「1st」、「MP3」）也會被分開。預設的數值模式不變。將數字停頓參數設為 0 即可關閉這個停頓。標點停頓與數字停頓落在同一處時，只會聽到較長的那一個。」
- `buildVars.py` stays untouched.

## 7. Settings, data, compatibility and errors

- **Settings and stored data:** no new setting, no confspec change, no migration.
  - The pipeline section keeps its keys (`psettings:285-290`).
  - The log section keeps the same switch keys (§4.7).
  - The number language stays a driver setting (`psettings:155-169`).
- **Default users:** users in value mode, the default, hear no change at any pause.
- **Other synths:**
  - In scope "WorldVoice" they get a number wait of 0 (`psettings:338-348`), so no edge break (U4).
  - In scope "all" they get edge pauses as plain breaks with the D3 marker, in the digit and group modes. NVDA's `speechXml` keeps every word and pause (`tests/test_pipeline_nvda_ssml.py` still passes in the prototype).
- **Upstream drivers, engine wrappers and Neural:** untouched. The change is core pipeline code only.
- **Errors:** no new error path.
  - The stage reads only values it already reads today.
  - A failure inside a stage still goes through NVDA's filter handling, as today.
  - The pipeline log write guard (`pipeline:785-808`) is unchanged.
- **Performance:** each edge break adds a speech task boundary. In the digit and group modes, a text full of short numbers gets up to two more pauses per number, on top of the separators these modes already send. Manual item M9 checks responsiveness.

## 8. Test plan

### 8.1 Existing expectations that change

The prototype ran with temporary aliases (`inject_number_mode = inject_number_language = inject_numbers`). Exactly these 11 expectations failed on behaviour; everything else passed.

- `tests/test_pipeline_filters.py`:
  - `test_number_mode[v1.2-group-2-50]`, `[a. 3-group-2-50]`, `[3.-group-2-50]` and `[.5-group-2-50]`: the `NUMBER_MODES` group-2 rows at pause 50 gain the edge breaks.
  - `test_main_number_language_passes_through_the_early_stage`: value mode merges strings, so the identity check becomes an equality check. The test still checks that "main" adds no language command at this stage.
  - `test_number_segments_with_main_wrap_in_the_current_language`: deleted with its helper. "main" never wrapped at this stage.
  - `test_number_language_leaves_a_sign_after_a_word_with_it`: rewritten through `inject_numbers` with number language de. The segments are the same, merged.
- `tests/test_pipeline_stages.py`:
  - `test_stages_order_and_log_keys`: `ORDER` (`tests/pipeline_harness.py:161-172`) loses `"number_language"`. `LOG_SWITCH_ORDER` (`:173-183`) is unchanged.
  - `test_worldvoice_keeps_the_break_subclasses_from_the_stages[number]` and `[group]`: the sets gain `("NumberEdgeBreakCommand", 10)`. The `[value]` case is unchanged.
- `tests/test_worldvoice_speak.py`:
  - `test_numbers_without_detection[locale-next]`: `(EN, ".")` becomes `(EN, " .")` (D5, value mode).

The value-mode rows of `test_main_moves_a_sign_with_its_number[wait-*]` (number wait 50) no longer change after the narrowing.

Mechanical renames, with identical output:

- In `tests/test_pipeline_filters.py`, `tests/test_pipeline_passthrough.py`, `tests/test_pipeline_pause_properties.py` and `tests/test_pipeline_stages.py:185-188`, every call of `inject_number_mode` or `inject_number_language` becomes a call of `inject_numbers`. In `test_pipeline_pause_properties.py` that covers `run_group_mode`, the digit-mode property, `run_number_mode`, the off-mode identity and the P10 chain.
- The off-mode identity property keeps `GENERIC_CONTEXT`, which still yields the same objects (§4.2 step 3). It is renamed to "…identity for the thousands and number stages".

Helpers and stubs:

- `tests/nvda_stubs.py:103-118` must read `also_logged_by` (§4.7).
- Drop the M5 note at `tests/test_pipeline_pause_properties.py:742-750` (D5).

These guards must keep passing unchanged:

- `tests/test_hygiene_guards.py` (ruff 0.16.3, blind-except reasons);
- `tests/test_pipeline_structure.py` (number lexing imports, `MOVED`, context fields, `getSynth`);
- `tests/test_pipeline_panels.py:30` (the confspec comprehension over `LOG_SWITCHES`);
- `tests/test_settings_table_guard.py`.

### 8.2 New unit tests (red first)

- **Worked examples:** the §5 rows as parametrized cases, both the stage output and the full `STAGES` output. Cover every mode, number language default, main and en, and roles on and off.
- **U1 / U4:**
  - In value mode and "none", there is no `NumberEdgeBreakCommand` at any pause, and the output equals today's (rows 1v, 2v, 8v, 9v, 13v, 26v, 38v, 42v, 46).
  - Mode "none" yields the same objects for default and main, and today's wrappers for a locale.
  - With `scaled_number_wait()` ≤ 0, the number and group modes add no edge break, while their separators are still `NumberBreakCommand(0)`.
  - A global factor below 10, through the real `PipelineSettings` (`psettings:309-313`).
- **O2 / D1:** a number alone in its item; at the item's start or end; followed only by whitespace (ASCII space, no-break space, U+3000).
- **O3:** in number and group modes, `"1 2"`, `"1 2"`, `"12 34"`, and `"1 2"` with an en wrapper each get exactly one `NumberBreakCommand` between the numbers, and `number_wait_factor` adds none afterwards. Value-mode `"1 2"` is still split by `number_wait_factor`.
- **O1:** the order is break, wrapper, pieces, wrapper, break. Dedupe uses `start_language` inside another language's stretch, as in `tests/test_pipeline_passthrough.py:118-153`.
- **O4:** `"COVID-19"`, `"中+2"`, `"a -5"` and `"5-3"` in number and group modes, plus unchanged value-mode output.
- **D5:** the dot rule with and without a wrapper, in value mode and in number mode at pause 0 and 10.
- **E1 / E2:**
  - §5 rows 31–45, through `inject_punctuation_pause` alone and through `STAGES`.
  - A run with an edge break and a language command or index command between it and a punctuation break.
  - A tie between an edge break and a punctuation break: the punctuation break stays.
  - A run of only two edge breaks: the first stays.
  - The last item of the sequence (the final `emit`).
  - Every case of `tests/test_pipeline_punctuation_pause.py:227-266` and `tests/test_pipeline_passthrough.py:203-212`, unchanged.
- **D3:**
  - `_plain_breaks` marks only edge breaks.
  - In number mode, another synth's `"Total. 12"` keeps the 50 ms punctuation pause.
  - `"3，下"` with removal gives one pause.
  - `speechXml` keeps every word of `"第3章"` in number mode, with the breaks.
  - A guard reads `ref/nvda/source/speech/commands.py` with `ast` and checks that `BreakCommand` and its bases define no `__slots__`.
- **D4:**
  - `LOG_SWITCHES` is unchanged.
  - "Number language" alone logs the number stage once, labelled `"number_mode"`.
  - "Number mode" alone logs two before/after pairs (the existing test).
  - Both switches on still log the number stage once.
  - The confspec and the Log Record panel list both switches with their labels.
- **O6:** the §4.8 table as rows of `tests/test_worldvoice_speak.py`, in number mode at number wait 0 and 10, timings "after" and "before". Add one value-mode row at wait 10 showing today's output.

### 8.3 Property tests (Hypothesis)

- **P-E1, text kept.** In the number and group modes, the `str` items of `inject_numbers` are joined, with each symbol name mapped back to its symbol, as in the existing P5 (`test_property_number_modes_keep_the_text`). The result equals the input with two changes: each whitespace gap between two numbers is removed when the pause is above 0, and the dot-rule spaces are added. Any number language, roles on.
- **P-E2, no edge break outside number and group modes.** For any sequence and context, `inject_numbers` adds no `NumberEdgeBreakCommand` in value mode or "none", nor at pause ≤ 0. In value mode, the stage output is the same for every pause.
- **P-E3, one break between numbers.** In the stage output, no two breaks are adjacent. Two numbers that only whitespace separates have exactly one `NumberBreakCommand` between them and no edge break.
- **P-E4, edges sit at number boundaries.** Each edge break has a number piece on one side, or a wrapper and then a number piece. On the other side it has non-blank text of the same input item.
- **P-E5, edges never meet another break.** Run all of `STAGES` through `stage.fn`, so break classes are kept, and treat language commands as transparent. No edge break may sit next to any other break. Inputs:
  - random text over digits, letters, marks, CJK and U+3000, with existing breaks and language commands;
  - random number, item and Chinese-space waits;
  - any mode, group size and number language; roles on and off;
  - punctuation pause on or off, with or without removal, with or without a space among the characters.

  The prototype passed this property, including P-E2's first check, in 4000 examples. The existing P10 (`tests/test_pipeline_pause_properties.py:663-701`) keeps running with `inject_numbers` in its chain and must still pass.
- **P-E6, E2 keeps the longest.** In a run with an edge break, the kept break's time is the run's maximum, and the run's other items keep their order. Runs without an edge break are untouched (identity).
- **P8** (`tests/test_pipeline_pause_properties.py:739-761`) keeps comparing number language en with default, with random number waits, now including edge breaks. It must still pass.
- **Equivalence with today, during development only (D9).** Copy today's `inject_number_language` and `inject_number_mode` into a scratch oracle, and compare after stripping text items and dropping blank ones:
  - in value mode and "none", `inject_numbers` must equal the oracle composition at any pause;
  - in the number and group modes, at pause 0.

  Record the result in the plan. The prototype passed the pause-0 check in 3000 examples, and value-mode output does not depend on the pause. The oracle is not committed; the renamed existing tests keep the characterization.

### 8.4 Mutation testing

`pipeline/__init__.py` is already in `[tool.mutmut] source_paths` (`pyproject.toml:45-55`). Run mutmut on Linux over `_number_item_segments`, `inject_numbers`, `_merge_edge_breaks`, `_is_edge_break` and `_plain_breaks`. Record each surviving mutant and its reason in the plan or the review (`DEVELOPMENT_WORKFLOW.md` §7).

### 8.5 Verification (`DEVELOPMENT_WORKFLOW.md` §7)

- `python3 -m pytest -q tests`: compare passed and skipped with 2610 and 0. The passed count rises with the new tests; skipped stays at 0.
- `prek run --all-files`: all Passed.
- `git diff --check`.
- Protected paths: both commands must print nothing.

  ```bash
  git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py
  git ls-files addon/synthDrivers/WorldVoice/driver/Neural
  ```

- Not verifiable on Linux: NVDA on Windows, real audio, engine SDKs. The report must say so.

### 8.6 Windows / NVDA manual items

- **M1.** A Chinese voice, default settings (value mode): `第3章` and `共 3 章` sound exactly as before. In number mode and in group mode, `第3章`, `共 3 章` and `第123章` get a short pause before and after the number. In "Off", there is no pause.
- **M2.** Number mode, number language English, an English voice installed: `第3章` reads `3` in English, with the pauses.
- **M3.** Number mode with number wait factor 0, then with global wait factor 0: everything sounds as before.
- **M4.** Number mode: `12 34` and `10 000` (with a no-break space) give one pause between the numbers, not longer than before.
- **M5.** Number mode, punctuation pause on, `。` and `.` configured, punctuation wait 100:
  - `第3。下一章` and `Total. 12`: the punctuation pause is as long as before, and not doubled;
  - with "remove" on: one pause only.
- **M6.** Number mode, English text: `the 1st item`, `COVID-19 cases`, `$5`, `MP3`, `Is it 5?` and `10am`. Run on Vocalizer/Cerence, eSpeak, OneCore and SAPI5, and record what each engine says (F1).
- **M7.** Scope "all", number mode, with NVDA's own OneCore, eSpeak and SAPI5:
  - `第3章` gets the pauses, and nothing after a number is dropped;
  - `Total. 12` with `.` configured keeps its punctuation pause (D3).
- **M8.** Number mode, Unicode detection on, timings "before" and "after": `abc3中`, and `中12` with "Follow document main language". The voices are the same as before, with pauses added.
- **M9.** Group mode: say all and arrow navigation through a page or spreadsheet with many numbers. No noticeable lag.
- **M10.** Log Record panel: "Number language" and "Number mode" are both listed, and each one alone records the number stage.

## 9. Affected layers

| File | Change |
|---|---|
| `addon/synthDrivers/WorldVoice/pipeline/__init__.py` | the number stage (§4.2–§4.5); E1/E2 (§4.6.3); the `_plain_breaks` marker (D3); `Stage.also_logged_by`, `_stage_handler`, `_run_logged` and `LOG_SWITCHES` (§4.7); docstrings |
| `readme.md`, `addon/doc/zh_TW/readme.md` | §6 |
| `tests/…` | §8 |

Untouched: `pipeline/numbers.py`, `pipeline/symbols.py`, `pipeline/settings.py`, `pipeline/context.py`, `languageDetection/`, the synth's `__init__.py`, `speechSettingsDialog.py`, the locale `.po` files, the engine wrappers and the upstream drivers.

## 10. Risks

- **Engines read split words differently in the digit and group modes** (F1, resolved as A). Default value-mode users are not affected. M6 records the effect.
- **More speech tasks per utterance** in the digit and group modes (§7, M9).
- **E2 drops a break class in favour of a longer break.** Downstream, only `number_wait_factor` looks at break classes, and only to block a number break (`pipeline:219-241`). Nothing depends on which class survives.
- **D3's attribute on NVDA's `BreakCommand`.** If NVDA ever adds `__slots__` to `BreakCommand`, setting the attribute raises. The AST guard of §8.2 shows this in the guard run after an NVDA upgrade.

## 11. Questions and the defaults applied

**Q1 (resolved).** Decided by the user (2026-10-24): option A. The edge pause is added whatever the neighbour, letters included (U3 unchanged), but only in the number and group modes (U1 amended). Options B (no pause next to letters of space-separated scripts) and C (B, plus no pause before item-final punctuation) were not chosen.

Decided by orchestrator with the recommended default; user may override before merge:

- **D1. A whitespace-only remainder counts as no content.** A number followed or preceded only by whitespace up to the item's end gets no edge break on that side (§4.3).
  - Why: NVDA strips every item (`speech.py:214`), and `_remove_space` strips items when the number wait is above 0, so that whitespace is never heard.
  - A break there would separate the number from nothing in its item. It would also put a number break next to the following item break, as in `["1 ", "2"]` with an item wait.
  - Alternative: the literal O2, where whitespace always counts. That needs E2 for item breaks too, and leaves a pause at the end of an utterance.
- **D2. Edge breaks are their own class, with two rules (E1, E2; F3).**
  - Alternative: "longest wins" for every number break. That changes M2, P4b and `test_a_number_break_counts_as_an_existing_pause_for_punctuation`, and reverses earlier decisions.
  - Accepted consequence, in the number and group modes only: a full-width mark between two numbers (`"1，2"`) is now an item of its own, so removal drops it. Today the mark before a digit is not a pause point (`pipeline:520-526`).
- **D3. A marker attribute on other synths' plain breaks,** so that E1 and E2 also work in scope "all" (§4.6.3).
  - Alternative: accept another known limit for scope "all". `"Total. 12"` in number mode would then lose its punctuation pause to the 10 ms edge.
- **D4. Logging (§4.7).** The merged stage keeps log key `"number_mode"`, and the `"number_language"` switch also logs it, through `Stage.also_logged_by`. Rows are labelled `"number_mode"`. Neither the panel nor the confspec changes.
  - Alternative: one new switch. That needs a new label and translation, and orphans the stored keys.
- **D5. The dot rule follows only the item's text,** with or without a kept wrapper (§4.5). The change shows in the sequence only, in value mode with a locale, and is not audible.
- **D6. Inside the number stage, a whitespace gap between two numbers becomes one plain `NumberBreakCommand`.** This happens in the number and group modes, with a pause above 0. `number_wait_factor` is unchanged (§4.3, §4.6.4).
- **D7. Names.** `inject_numbers`, `_number_item_segments`, `NumberEdgeBreakCommand`, `_is_edge_break` and `_merge_edge_breaks`. The old functions are removed and their tests renamed (§4.9, §8.1).
- **D8. Strings and docs.** "Number wait factor" keeps its label. Only the English and zh_TW readmes change: one bullet and one changelog entry (§6).
- **D9. The equivalence oracle runs during development only and is not committed** (§8.3). It checks value and "none" modes at any pause, and the number and group modes at pause 0.
- **D10. One edge-break instance and one gap-break instance per stage run** (§4.3).
