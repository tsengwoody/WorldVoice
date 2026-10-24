# Number edge pause: a pause before and after every number

Date: 2026-10-24.
Baseline: `master` `8612c3d`. Branch: `feat/number-edge-pause`, worktree `/workspace/WorldVoice-number-edge-pause` (`ref` symlinked to `/workspace/WorldVoice/ref`).
Baseline numbers: `python3 -m pytest -q tests` → 2610 passed, 0 skipped; `prek run --all-files` all Passed.
Flow: normal flow (`DEVELOPMENT_WORKFLOW.md` §3.1).
Status: U1–U5 were decided by the user (2026-10-24). O1–O6 were shown to the user by the orchestrator. D1–D10 are defaults added while writing this spec (§11). One question needs the user before merge (§0, Q1).

References used throughout:

- Pipeline stages: `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (below: `pipeline:<line>`).
- Number definitions: `addon/synthDrivers/WorldVoice/pipeline/numbers.py` (below: `numbers:<line>`).
- Pipeline settings table: `addon/synthDrivers/WorldVoice/pipeline/settings.py` (below: `psettings:<line>`).
- Synth: `addon/synthDrivers/WorldVoice/__init__.py` (below: `synth:<line>`).
- Detector: `addon/synthDrivers/WorldVoice/languageDetection/__init__.py` (below: `detection:<line>`).
- Speech settings dialogs: `addon/globalPlugins/WorldVoice/speechSettingsDialog.py` (below: `dialog:<line>`).
- NVDA: `ref/nvda/source/...`.

A prototype of this design (§4) was run in a scratch copy of the worktree. It was not committed. The prototype:

- passed the existing suite except the 14 expectations listed in §8.1;
- produced every sequence in §5 (stage output and full `STAGES` output);
- ran the speak harness of `tests/test_worldvoice_speak.py` for §4.8;
- passed these Hypothesis checks:
  - an edge break never meets another break after all stages: 4000 examples, roles on and off, number language default/main/en, punctuation on and off, item, Chinese-space and number waits;
  - with a pause of 0, the new stage equals today's two stages: 3000 examples, compared after stripping each text item and dropping blank items.

## 0. Findings that need the user

### F1 (Q1, needs an answer before merge). The edge pause is on by default, and it also splits words that contain digits

- **On by default.** `scaled_number_wait()` is `global_wait_factor // 10 * number_wait_factor` (`psettings:309-313`). Both defaults are 10 (`psettings:143-154`, `psettings:200-209`). So with default settings every number gets a 10 ms edge pause in value mode, the default number mode (`psettings:170-183`). Every user who never touched the number wait gets the change.
- **Every edge break splits the item.** WorldVoice turns each break into `Pause` (`compat/commands.py:15-16`). The request builder flushes the text before a `Pause` and appends a separate break task (`runtime/requestBuilder.py:44-50`, `runtime/scheduler.py:231-236`). So the engine gets the text before the number, the number and the text after it as three separate pieces. NVDA's own synths behave the same way, because NVDA processes symbols item by item after the filters (`ref/nvda/source/speech/speech.py:1137` filters, `:1216-1231` `processText` per item).
- **What this changes besides the pause.** U3 adds the edge pause next to any neighbour: text, whitespace or punctuation. So:
  - Ordinals and units written next to digits are cut: `"the 1st item"` becomes `"the"`, pause, `"1"`, pause, `"st item"` (§5 row 26). An engine that reads `1st` as "first" will instead read "one", then `st` on its own. Many engines read a lone `st` as "street" or "saint". The same happens to `2nd`, `3rd`, `10am`, `5kg`, `MP3`, `H2O`, `3D`, `4K` and `$5`. For `$5`, an engine that says "five dollars" will say "dollar", "five" instead.
  - Sentence punctuation after a number becomes an item of its own: `"Is it 5?"` becomes `"Is it"`, pause, `"5"`, pause, `"?"`. Engines lose the question or exclamation intonation on the number.
  - Phase 35 kept a number in its item where the voice does not change, so that NVDA's context rules read the whole item (`tests/test_worldvoice_speak.py:540-571`, batch 1 review C1). That still holds only at a number pause of 0. The existing rows run at 0 and keep passing.
- **Options:**
  - **A. Keep U3 as decided.** Every neighbour, as specified in this document.
  - **B. No edge pause next to a letter of a script that puts spaces between words** (Latin, Greek, Cyrillic and similar). `1st`, `MP3`, `H2O` and `10am` stay whole. Han, kana, hangul, Thai and other scripts without spaces, as well as whitespace, punctuation and symbols, still get the pause, so `第3章`, `共 3 章`, `第3。` and `COVID-` + `19` behave as in A.
  - **C. B, and also no pause before item-final punctuation.** `"Is it 5?"` and `"第3。"` keep their intonation. This partly reverses U3 for `第3。`.
- **Recommendation: B.** It keeps the goal (`第3章`) and the CJK cases that U3 lists, and it does not change English words.
- **Default applied:** this spec implements **A**, as the user decided. B and C need only one more condition, on the character next to the number, in the edge rule of §4.3. Under B, the only §5 row that changes is row 26 (no edge break between `1` and `st`). Under C, rows 18, 19, 27, 31 and 32 also lose their right edge break.

### F2 (for information). O4 changes nothing by itself

- Today, in number language "Follow"/"main" or for a synth without roles, the mode stage cuts `"COVID-19"` as the match `-19` (`pipeline:449-471`, `numbers:22`), but the pieces are merged back with the text: `"COVID-1"`, NB, `"9"` in number mode, and `"COVID-19"` in value mode.
- NVDA's negative-number rule needs the `-` not to follow a word character (`ref/nvda/source/locale/en/symbols.dic:19`, `ref/nvda/source/locale/zh_TW/symbols.dic:21`). So today the `-` is never read as a minus sign there.
- With edge breaks, a NUMBER_RE span would make `"-19"` an item of its own and NVDA would read "minus 19". Using the hyphen-rule spans (O4) is what keeps today's reading.
- At a pause of 0 the hyphen-rule spans give exactly today's strings, because `merge_consecutive_strings` joins `"COVID-"` and `"1"` again (prototype oracle above). The audible change is only the edge pause between `COVID-` and `19` (§3).

### F3 (orchestrator default, user may override). A plain edge `NumberBreakCommand` would shorten every punctuation pause next to a number

- The punctuation stage lets any break waiting between two items suppress the boundary pause of the item before it (`pipeline:574-577`, `:658`). If the edge pause were a plain `NumberBreakCommand`, `"Total. 12"` with `.` configured would get the 10 ms number pause where it gets the punctuation pause today (for example 250 ms).
- Removal would also leave a number break and a punctuation break side by side: `"3，下"` would become `"3"`, NB, PB, `"下"`.
- O5's "reuse the existing dedupe" is not enough. The existing rule (review M2, `pipeline:581-585`, `:660-667`) only covers two number breaks around an item that removal empties.
- This spec therefore:
  - gives the edge pause its own class, `NumberEdgeBreakCommand(NumberBreakCommand)`;
  - adds two rules that apply to that class only (§4.6.3).

  Every existing rule, test and earlier decision about `NumberBreakCommand` stays as it is.

## 1. Problem

- When the number language equals the language of the surrounding text, nothing separates a number from its neighbours. Examples: "Follow current text language" (the default), or a locale whose voice is the voice in force.
- In `"第3章"` the voice reads `第3章` as one run. The listener cannot tell where the number starts.
- A language switch around the number is the only thing that sets it apart today, and it exists only when the number language's voice differs (`pipeline:304-319`, `:681-730`).
- The existing number pause (`number_wait_factor`, `pipeline:198-241`) only separates two numbers from each other: `"1 2"` and adjacent number items.

## 2. Goals and non-goals

### 2.1 Goals (decided by the user, 2026-10-24)

- **U1.** Every number gets a pause before and after it, but only when the number mode is not "none". This applies to value, number and group modes. In mode "none" there is no edge pause, and number-language handling still runs as today.
- **U2.** The pause time is the existing number pause, `settings.scaled_number_wait()` (`psettings:312-313`). There is no new setting.
- **U3.** The pause is added whatever the neighbour is: text, whitespace or punctuation. `"共 3 章"` and `"第3。"` both get it on both sides.
- **U4.** A pause time of 0 means no edge break at all. Unchanged:
  - the between-numbers pause (`number_wait_factor`, `pipeline:209-212`) still adds nothing at 0;
  - the number- and group-mode piece separators in `_translate_number` still insert `NumberBreakCommand` even at 0 (`pipeline:393-408`), because they make each piece an item of its own.

  Reason (agreed with the user):
  - a `BreakCommand(0)` still becomes `Pause(0)` (`compat/commands.py:15-16`), and the request builder flushes a separate task around it (`runtime/requestBuilder.py:44-50`), so a 0 ms break is still audible as a cut;
  - 0 also means "pauses off": `PipelineSettings.effective` zeroes the number wait for other synths outside scope "all" (`psettings:330-349`), and a global factor below 10 makes `global_factor_units` 0 (`psettings:309-310`).
- **U5.** Numbers are found once, with the number-language rule: `_split_numbers_for_language` (`pipeline:117-136`), that is, `NUMBER_RE` (`numbers:22`) plus the hyphen rule. For each number, three things happen in order:
  1. edge pauses;
  2. number language;
  3. number mode.

  This merges today's `inject_number_language` and `inject_number_mode` stages (`STAGES`, `pipeline:875-885`) into one number stage.

### 2.2 Orchestrator calls shown to the user (Decided by orchestrator; user may override before merge)

- **O1.** The edge break sits outside the language wrapper: `第`, Break, Lang(num), pieces…, Lang(cur), Break, `章`.
- **O2.** An edge break is added only on a side where the same text item has content next to the number. Whitespace counts as content (U3), refined by D1. A number at the very start or end of an item gets no break on that side, because item boundaries are `item_wait_factor`'s job.
- **O3.** Two numbers separated only by whitespace (`"1 2"`) get exactly one `NumberBreakCommand` between them, never two or three. For the cases `number_wait_factor` already covers, its output is unchanged (§4.3, §4.6.4).
- **O4.** Number mode now uses the hyphen-rule spans. Its effect is described in F2 and §3.
- **O5.** The punctuation pause keeps working, and a number break never stacks on it (§4.6.3; extended by F3/D2).
- **O6.** Language detection runs after `STAGES` and passes breaks through (§4.8). There is no code change there, only tests.

### 2.3 Non-goals

- `NUMBER_RE`, `SYMBOLS`, the sign and hyphen rules, the digit set (`numbers:11-28`), `number_pieces` (`numbers:63-90`), symbol naming (`pipeline/symbols.py`).
- `number_wait_factor`, `split_spaced_numbers`, `_insert_number_breaks`, `_remove_space`: unchanged code (`pipeline:165-241`, `numbers:36-60`).
- The thousands step `remove_thousands_separators`: unchanged, and it stays the stage before the number stage (`pipeline:58-71`, `:877`).
- Language detection, `wrap_numbers_for_detection`, `detect_with_number_language` (`pipeline:322-390`): unchanged.
- The pre-existing loss of a punctuation pause in front of a number wrapped for another voice (`"Total. 12"` with a locale, phase 35 F2, `tests/test_worldvoice_speak.py:443-449`): unchanged.
- Any engine wrapper, the upstream drivers under `driver/<Engine>/driver/`, and Neural.

## 3. User-visible changes

What NVDA users hear, with default settings (number wait 10 ms, value mode, "Follow current text language"), unless the row says otherwise. "|" is a pause.

| Text, settings | Today | After |
|---|---|---|
| `第3章` | `第3章` | `第` \| `3` \| `章` |
| `第3章`, number language en (another voice) | `第` (zh) `3` (en) `章` (zh) | `第` \| `3` (en) \| `章` |
| `第123章`, number mode | `第1` \| `2` \| `3章` | `第` \| `1` \| `2` \| `3` \| `章` |
| `第3章`, mode "none" | `第3章` | unchanged |
| `第3章`, number wait 0 (or global wait factor below 10) | `第3章` | unchanged |
| `共 3 章` | `共 3 章` | `共` \| `3` \| `章` |
| `1 2` | `1` \| `2` | unchanged (one pause) |
| `COVID-19` | `COVID-19` | `COVID-` \| `19` |
| `the 1st item` (F1) | `the 1st item` | `the` \| `1` \| `st item` |
| `Total. 12`, `.` a punctuation pause character (50 ms) | `Total.` \| `12` (50 ms) | unchanged (50 ms; the 10 ms edge pause merges into it) |
| `第3。下一章`, `。` configured, remove on | `第3` \| `下一章` | `第` \| `3` \| `下一章` (the last pause is the longer of the two) |
| `1，2`, `，` configured, remove on | `1，2` (the mark before a digit is not a pause point, `pipeline:520-526`) | `1` \| `2`: the mark is now an item of its own, so it is removed (D2) |
| Another synth, scope "all" | as WorldVoice today | edge pauses as plain `BreakCommand`s, same rules |
| Log Record panel | "Number language", "Number mode" switches | the same two switches, each of which logs the merged stage (§4.7) |

- No panel, dialog, control or label changes.
- No new or changed translatable strings.
- The readmes change (§6).

## 4. Design

### 4.1 Terms

- **Item**: one `str` in the speech sequence.
- **Span**: one ("number", text) part of `_split_numbers_for_language(item)` (`pipeline:117-136`). The parts alternate text/number, because the hyphen rule only moves a sign into the text and `NUMBER_RE` matches never touch (`numbers:42-43`).
- **Content on a side**: the item has a non-whitespace character between the span and that end of the item (D1). The test is `item[:start].strip()` for the left side and `item[end:].strip()` for the right side.
- **Whitespace gap**: a text part between two spans that is all whitespace (`str.isspace()`). A no-break space counts, as in `split_spaced_numbers` (`numbers:44-46`, decided by the user 2026-10-22).
- **Edge break**: `NumberEdgeBreakCommand(scaled_number_wait())`, a new subclass of `NumberBreakCommand` (`pipeline:35-36`):

  ```python
  class NumberEdgeBreakCommand(NumberBreakCommand):
  	"""Pause between a number and the text next to it in its item."""
  ```

  It is a `NumberBreakCommand`, so every existing `isinstance(…, NumberBreakCommand)` check treats it as a number break: the M2 rule (`pipeline:660-667`) and the tests that collect number breaks.

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
2. **Synth without roles.** Drop every `WVLangChangeCommand` with `remove_language_command` (`pipeline:244-250`), as `inject_number_language` does today (`pipeline:319`). This also happens in mode "none".
3. **Nothing to do.** If `mode == "none"` and not `wraps`, yield the rest unchanged, with the same objects. This keeps today's two pass-throughs:
   - "none" leaves numbers alone, without even the dot rule (`pipeline:417-420`);
   - "Follow"/"main" add no wrapper at this stage (`pipeline:310-316`).
4. `pause = settings.scaled_number_wait()`. The edge break is `NumberEdgeBreakCommand(pause)` when `mode != "none"` and `pause > 0`, otherwise `None` (U1, U4). The gap break is one `NumberBreakCommand(pause)` per stage run.
5. The namer is built as today (`pipeline:423-429`): `namer = symbol_namer(ctx.voice_locale_for_language)`. Symbols are named for the number language when `wraps`, else for the language in force.
6. Walk the sequence and track the language in force: `language = item.lang or ctx.language` at each `LangChangeCommand`/`WVLangChangeCommand` (as `pipeline:268-271` and `:432-434` do today). Every non-`str` item passes through.
7. For each `str` item, run `_number_item_segments(item, …)` (§4.3–§4.5).
   - With `wraps`, pass the result through `deduplicate_language_command(…, ctx, start_language=language)` (`pipeline:274-278`; phase 30 item 6).
   - Then pass it through `merge_consecutive_strings` (`pipeline:474-485`).

`_number_item_segments(item, *, mode, group_size, pause, name_of, number_language, language, edge, gap_break)` is a generator. For each part of `_split_numbers_for_language(item)`, in order:

- **Text part.**
  - If it is a whitespace gap and `edge` is not `None`, yield `gap_break` in its place (§4.3).
  - Otherwise yield it, with the dot rule (§4.5).
- **Number span.** Yield, in this order:
  1. the left edge break (§4.3);
  2. `WVLangChangeCommand(number_language)` when wrapping;
  3. the span as is in mode "none", else `_translate_number(span, mode, group_size, pause, name_of)` (`pipeline:393-408`, unchanged);
  4. `WVLangChangeCommand(language)` when wrapping;
  5. the right edge break.

### 4.3 The edge rule (U1, U3, U4, O1, O2, O3, D1, D6)

- **Where.** An edge break goes on each side of a span where the item has content on that side (§4.1). There is no edge break:
  - in mode "none";
  - when `pause <= 0`;
  - at the start or end of an item;
  - where only whitespace lies between the span and the item's end (D1).
- **Position (O1).** The edge break goes outside the wrapper: left edge, opening wrapper, pieces, closing wrapper, right edge. The closing wrapper names the language in force, as today (`pipeline:301`).
- **Whitespace gaps (O3, D6).**
  - Two spans separated only by whitespace, with `edge` not `None`: the gap is replaced by one `NumberBreakCommand`, the gap break. The right edge of the first span and the left edge of the second span are not added.
  - This is the same result `number_wait_factor` produces today for such text (`pipeline:198-241`, `numbers:36-60`): whitespace replaced by one number break.
  - It is a plain `NumberBreakCommand`, not an edge break, because it is a pause between two numbers.
  - With `edge` `None` (pause 0, or mode "none"), the gap stays text, and `number_wait_factor` handles it as today.
- **Other gaps.** A gap that holds anything besides whitespace (`"1，2"`, `"1, 2"`) is ordinary text: an edge break on each side of it (U3). If the mark in it is silent at the user's symbol level, the listener hears two number pauses in a row. That is accepted under U3. With the punctuation pause on and the mark configured, §4.6.3 merges them.
- **One edge instance per stage run.** It is shared like `number_wait_factor`'s break (`pipeline:213-216`). The synth only reads its time, and no code compares breaks by identity.

### 4.4 Number language inside the stage

- The wrapper is exactly today's (`pipeline:296-301`):
  - only for a locale number language (`wraps`);
  - opening `WVLangChangeCommand(ctx.number_language)`, closing `WVLangChangeCommand(language in force)`;
  - deduplicated per item with `start_language` the language in force.
- "Follow" and "main" add no wrapper here, as today (`pipeline:310-316`). "main" numbers are still wrapped where detection runs (`detect_with_number_language`, `pipeline:358-390`; phase 35 §4.4).
- A synth without roles gets no wrapper, and incoming `WVLangChangeCommand`s are dropped (§4.2 step 2).

### 4.5 Number mode inside the stage

- **Pieces and separators:** `_translate_number` unchanged (`pipeline:393-408`). There is one separator instance per number, and it is present even at pause 0 (U4).
- **Spans:** the hyphen-rule spans (U5, O4). The sign of a span after a word character is in the text part, so in number and group modes it is no longer part of the first piece. At pause 0 the merged strings are identical to today (F2).
- **Symbol names:** the locale is that of the number language when wrapping, else that of the language in force, as today (`pipeline:424-429`, `:442`).
- **Dot rule (D5).** The rule is today's (`pipeline:457-470`), applied to the item's text parts, in every mode but "none":
  - a text part right after a number that starts with `"."` gets a leading `" "`;
  - a text part right before a number that ends with `"."` gets a trailing `" "`.

  The rule now depends only on the item's text, not on whether a wrapper is kept.
  - Today, with a locale wrapper whose voice differs, the mode stage saw `"12"` and `"."` as separate strings and added no space (phase 35 F2).
  - Now `"12. Next"` with number language en gives `L(en) "12" L(zh) " . Next"` instead of `L(en) "12" L(zh) ". Next"` (§5 row 23).
  - Nothing changes audibly: NVDA strips every text item in `processText` (`ref/nvda/source/speech/speech.py:214`) before any synth sees it (`:1225-1231`). With an edge break, `number_wait_factor`'s `_remove_space` also strips it later (`pipeline:165-187`).
  - The P8 docstring note on this difference (`tests/test_pipeline_pause_properties.py:742-750`, final review M5) becomes obsolete.

### 4.6 The later stages

#### 4.6.1 Chinese space (`pipeline:488-511`)

- Its pattern needs a CJK character on both sides of the space inside one item (`pipeline:32`).
- Edge breaks only cut an item at a number, so they never separate a CJK character from the space next to it. `"中 文3"` still gets its Chinese-space pause in `"中 文"`.

#### 4.6.2 Item wait (`pipeline:152-162`)

- It breaks only between two adjacent `str` items. An edge break always has non-blank text of its own item between it and the item's end (D1), so an item break is never placed next to an edge break.
- Items that only formatting or an index command separates (`"第"`, IndexCommand, `"3"`, IndexCommand, `"章"` in browse mode) get no edge break (O2). §5 row 28.

#### 4.6.3 Punctuation pause (O5, F3, D2, D3)

`inject_punctuation_pause` (`pipeline:549-678`) changes in two places. Both act only on edge breaks. `_is_edge_break(command)` is true for a `NumberEdgeBreakCommand`, and for a plain `BreakCommand` that carries the edge marker of D3.

- **E1. An edge break does not suppress a boundary pause.**
  - Today `emit(previous, text_follows and not pending_breaks, text_follows)` (`pipeline:658`) suppresses the boundary pause whenever any break waits.
  - Now it is suppressed only when a waiting break is not an edge break: `text_follows and all(_is_edge_break(b) for b in pending_breaks)`.
  - Breaks that are not edges keep today's rule: an existing break, a separator `NumberBreakCommand`, or a plain break of another synth's number pieces (P4b, `tests/test_pipeline_pause_properties.py:165-180`).
- **E2. Breaks that meet around an edge break collapse into one.**
  - A *run* is everything between two non-blank text items in the stage's output, or before the first or after the last one. It can hold breaks, blank text and other commands, such as language and index commands.
  - When a run holds two or more `BreakCommand`s and at least one is an edge break, only one break of the run is kept:
    - the longest;
    - on a tie, the first that is not an edge break;
    - if all are edge breaks, the first.

    The run's other items keep their order.
  - Runs without an edge break are untouched. So these keep their current behaviour and tests (`tests/test_pipeline_punctuation_pause.py:227-266`, `tests/test_pipeline_passthrough.py:203-212`):
    - the M2 rule (`pipeline:660-667`);
    - "removal changes only marks around any other break" (`test_property_removal_changes_only_the_marks`);
    - "a number break counts as an existing pause".
  - E2 runs over the whole output of the active stage, the last item included. Today's final `emit` (`pipeline:677-678`) bypasses the M2 check. E2 must not.

    Implementation: `inject_punctuation_pause` yields from `_merge_edge_breaks(<today's loop>)` after its early returns (`pipeline:587-596`).
  - It does not run when the stage is off. The property in §8.3 (P-E5) shows that edge breaks cannot meet another break without this stage: an edge break always has non-blank text of its own item on its outer side, and every other break the stages make sits between spoken text.
- **Why "longest" and not "the earlier one" (M2).**
  - Where a punctuation pause and an edge pause fall on one spot, the punctuation pause is what the user tuned for that mark, and it is usually the longer one. Keeping the earlier break would make `"Total. 12"` lose its 50–500 ms pause to the 10 ms edge.
  - Keeping the longer one also keeps the number separated when the punctuation pause is 0 ms (§5 rows 41, 44).
  - Number breaks in one run all have the same time (`scaled_number_wait()`), so M2's "earlier" choice is unaffected.
- **Results** (prototype; punctuation wait 50 ms, number wait 10 ms):
  - `"第3。"`, `"3，"` (nothing follows): no punctuation pause, as today. The output is `"第"`, E10, `"3"`, E10, `"。"` with removal on or off. The mark at the end of the sequence is never a pause point (`pipeline:569-570`).
  - `"第3。下一章"`: removal off gives `"第"`, E10, `"3"`, E10, `"。"`, PB50, `"下一章"`. Removal on gives `"第"`, E10, `"3"`, PB50, `"下一章"`.
  - `"3，下"`: removal off gives `"3"`, E10, `"，"`, PB50, `"下"`. Removal on gives `"3"`, PB50, `"下"`.
  - `"Total. 12"`: removal off gives `"Total"`, `"."`, PB50, `"12"`. Removal on gives `"Total"`, PB50, `"12"`. These are today's results.
- **D3: synths without roles.**
  - `_stage_handler` turns every break subclass into a plain `BreakCommand` after each stage for another synth (`pipeline:832-847`), because NVDA's `speechXml` picks a converter by class name (`ref/nvda/source/speechXml.py:256-258`). The punctuation stage then could not tell an edge break from any other break.
  - So `_plain_breaks` sets the attribute `worldvoice_number_edge = True` on the plain `BreakCommand` it makes from an edge break.
  - The class stays NVDA's `BreakCommand`. NVDA's `BreakCommand` has no `__slots__`, and its `__eq__` compares only type and time (`ref/nvda/source/speech/commands.py:200-218`). OneCore, SAPI5 and eSpeak read only `.time`, so the attribute is invisible to them.
  - Existing number and punctuation breaks get no marker, so the documented limit for other synths (`tests/test_pipeline_filters.py:598-626`, number-unify spec 6.4.1) stays as it is.

#### 4.6.4 Number wait (`pipeline:198-241`)

The code is unchanged.

- **Mode "none":** nothing changes. It splits `"1 2"` and breaks between whole-number items, as today.
- **Other modes:** the number stage has already replaced every whitespace gap with one number break (§4.3). `split_spaced_numbers` finds nothing more to split, and `_insert_number_breaks` sees a break, not two adjacent numbers, so it adds nothing.
  - O3 holds: `"1 2"` gives exactly `"1"`, NB, `"2"`. With a locale it gives `L(en) "1" L(zh)`, NB, `L(en) "2" L(zh)`, which is today's output (`tests/test_pipeline_stages.py:191-210`).
- **Across items:** whole-number items still get its break (`["1", "2"]`). A number alone in its item has no edge break (O2), so the two breaks never meet.
- **Whitespace next to an edge:** `_remove_space` strips every text item whenever the number wait is above 0 (`pipeline:165-187`, `:209-216`), and edge breaks exist only then. So `"共 "`, E, `"3"`, E, `" 章"` reaches the synth as `"共"`, E, `"3"`, E, `"章"`.

#### 4.6.5 In `speak` (`synth:314-330`)

- `inject_langchange_reorder` moves each language command in front of the commands buffered before it (`pipeline:749-782`). The left edge break therefore reaches the request builder after the voice switch: `"第"`, SelectVoice(en), Pause, `"3"`, SelectVoice(zh), Pause, `"章"`.
- A break task has no voice (`runtime/scheduler.py:231-236`), so nothing audible changes.
- Today's `"1 2"` with a locale already has this shape.

### 4.7 Logging (D4)

- `_run_logged` turns a stage's log on by the switch named by its log key (`pipeline:811-829`). `LOG_SWITCHES` derives one switch per log key from `STAGES` (`pipeline:888-889`). The Log Record panel lists one checkbox per switch (`dialog:39-49`, `:643-649`), and the confspec has one boolean per switch (`synth:83-86`).
- A plain merge with log key `"number_mode"` would drop the "Number language" switch: from the panel, from the confspec and from users' stored profiles.
- Conservative default:
  - `Stage` gains `also_logged_by: tuple[str, ...] = ()`, the switches that also turn this stage's log on.
  - `LOG_SWITCHES` lists, for each stage with `log_switch=True`, its `also_logged_by` keys and then its `log_key`, each key once, in order. The result is today's tuple:

    ```
    ("apply_speech_dictionaries", "number_language", "number_mode", "chinesespace_wait_factor",
     "item_wait_factor", "punctuation_wait_factor", "number_wait_factor", "speech_viewer")
    ```

  - `_stage_handler(log_key, fn, switches)` passes `(*also_logged_by, log_key)` to `_run_logged`. `_run_logged` logs when the debug level or the record switch is on (unchanged), and any of those switches is on.
  - Rows are labelled with the log key, `"number_mode"`.
- What users see:
  - The Log Record panel shows the same two checkboxes with the same labels ("Number language", "Number mode", taken from `display_name` at `psettings:165`, `:179`).
  - Stored `[WorldVoice][log]` keys keep working.
  - "Number language" alone logs the number stage once. "Number mode" logs the thousands step and the number stage, as today (`tests/test_pipeline_stages.py:46-59`).
- The translator comments at `psettings:163-165` and `:177-178` stay true.
- `tests/nvda_stubs.py:103-118` derives the log confspec from the AST of `STAGES`. It must also read the `also_logged_by` keyword, or the stub silently loses `number_language`.

### 4.8 Language detection (O6)

- Detection timed "before" is an NVDA filter, and `order_move_to_start_register` moves all of `STAGES` in front of it (`synth:460-469`, `pipeline:892-895`). Detection timed "after" runs in `speak` (`synth:317-318`). Both see the number stage's output.
- The detector passes any non-language command through without touching `tmpLang` (`detection:149-174`, the `else` at `:173-174`), and keeps a decimal digit in the current run (`detection:138-143`).
- `wrap_numbers_for_detection` wraps a number that is now alone in its item. Both sides of its `joins` are false, so dropping a redundant wrapper glues nothing (`pipeline:343-355`, `:379-390`).
- No code change. Prototype through the speak harness, with every voice the same as at number wait 0 and only breaks added:

| Text | Number language | Main voice | Number wait 0 | Number wait 10 (timings "after" and "before" alike) |
|---|---|---|---|---|
| `第3章` | default / main | zh | `[(ZH, "第3章")]` | `[(ZH, "第"), "\|", (ZH, "3"), "\|", (ZH, "章")]` |
| `第3章` | en | zh | `[(ZH, "第"), (EN, "3"), (ZH, "章")]` | `[(ZH, "第"), "\|", (EN, "3"), "\|", (ZH, "章")]` |
| `中12` | main | en | `[(ZH, "中"), (EN, "12")]` | `[(ZH, "中"), "\|", (EN, "12")]` |
| `中12` | default | en | `[(ZH, "中12")]` | `[(ZH, "中"), "\|", (ZH, "12")]` |
| `abc3中` | default | en | `[(EN, "abc3"), (ZH, "中")]` | `[(EN, "abc"), "\|", (EN, "3"), "\|", (ZH, "中")]` |
| `中 COVID-19 中` | main | zh | `[(ZH, "中 "), (EN, "COVID-"), (ZH, "19 中")]` | `[(ZH, "中 "), (EN, "COVID-"), "\|", (ZH, "19"), "\|", (ZH, "中")]` |
| `中 -12 34` | main | en | `[(ZH, "中 "), (EN, "-12 34")]` | `[(ZH, "中"), "\|", (EN, "-12"), "\|", (EN, "34")]` |
| `abc 123 def` | zh_TW | zh | `[(EN, "abc "), (ZH, "123 "), (EN, "def")]` | `[(EN, "abc"), "\|", (ZH, "123"), "\|", (EN, "def")]` |

### 4.9 Code removed, kept and added

- **Removed from `pipeline/__init__.py`:**
  - `_insert_WVLangChangeCommand_between_number` (`:253-279`);
  - `iter_number_speech_segments_language` (`:282-301`);
  - `inject_number_language` (`:304-319`);
  - `inject_number_mode` (`:411-446`);
  - `iter_number_speech_segments_mode` (`:449-471`).

  Only the pipeline and the tests use them (grep of `addon/` and `tests/`).
- **Kept:** `remove_language_command`, `_translate_number`, `merge_consecutive_strings`, `deduplicate_language_command`, `_split_numbers_for_language`, and `_split_by` (still used by the Chinese-space and punctuation stages).
- **Added:**
  - `NumberEdgeBreakCommand`;
  - `inject_numbers`;
  - `_number_item_segments`;
  - `_is_edge_break`;
  - `_merge_edge_breaks`;
  - `Stage.also_logged_by`.
- **Docstrings:**
  - `NumberBreakCommand`'s docstring (`:36`) adds "and between two numbers that only whitespace separates";
  - `inject_punctuation_pause`'s docstring (`:554-586`) gains E1 and E2.
- `pipeline/numbers.py` and `pipeline/symbols.py` are untouched, so `test_number_lexing_imports_only_the_standard_library` and the `MOVED` guard (`tests/test_pipeline_structure.py:41-123`) still hold.

## 5. Worked examples

These are prototype outputs, both the stage output of `inject_numbers` and the output after every stage of `STAGES`.

- Context: WorldVoice context, language zh, voices `{"zh": Z, "en": E}`.
- Settings: number wait 10, punctuation wait 50, item and Chinese-space waits 0, group size 3, unless a row says otherwise.
- Notation:
  - `E10` is an edge break, `NB10` a `NumberBreakCommand` (separator or gap break), `PB50` a punctuation break;
  - `L(x)` is `WVLangChangeCommand(x)`;
  - `B10*` is a plain `BreakCommand` with the edge marker.
- Where the full output equals the stage output, the column says "same".

| # | Input, settings | `inject_numbers` output | After all `STAGES` |
|---|---|---|---|
| 1 | `第3章`, value / number / group, default | `第` E10 `3` E10 `章` | same |
| 2 | `第3章`, value, en | `第` E10 L(en) `3` L(zh) E10 `章` | same |
| 3 | `第123章`, number, default | `第` E10 `1` NB10 `2` NB10 `3` E10 `章` | same |
| 4 | `第123章`, group 2, default | `第` E10 `12` NB10 `3` E10 `章` | same |
| 5 | `第123章`, number, en | `第` E10 L(en) `1` NB10 `2` NB10 `3` L(zh) E10 `章` | same |
| 6 | `第3章`, none, default | `第3章` (the same object) | same |
| 7 | `第3章`, none, en | `第` L(en) `3` L(zh) `章` (today's) | same |
| 8 | `共 3 章` | `共 ` E10 `3` E10 ` 章` | `共` E10 `3` E10 `章` |
| 9 | `1 2` | `1` NB10 `2` | same (today: `1` NB10 `2`) |
| 10 | `1 2`, en | L(en) `1` L(zh) NB10 L(en) `2` L(zh) | same (today's) |
| 11 | `12 34`, number | `1` NB10 `2` NB10 `3` NB10 `4` | same (today's) |
| 12 | `1 2`, none | `1 2` | `1` NB10 `2` (by `number_wait_factor`, as today) |
| 13 | `COVID-19` | `COVID-` E10 `19` | same |
| 14 | `COVID-19`, number | `COVID-` E10 `1` NB10 `9` | same |
| 15 | `-5` | `-5` | same |
| 16 | `a -5` | `a ` E10 `-5` | `a` E10 `-5` (NVDA reads `-5` alone as "minus 5", as it reads `a -5` today) |
| 17 | `x-5` | `x-` E10 `5` | same |
| 18 | `3.5.` | `3.5` E10 ` .` | `3.5` E10 `.` |
| 19 | `1.` | `1` E10 ` .` | `1` E10 `.` |
| 20 | `a.5` | `a. ` E10 `5` | `a.` E10 `5` |
| 21 | `There are 5. Next` | `There are ` E10 `5` E10 ` . Next` | `There are` E10 `5` E10 `. Next` |
| 22 | `There are 5. Next`, `.` configured | as row 21 | `There are` E10 `5` E10 `.` PB50 `Next` |
| 23 | `12. Next`, en, number wait 0 | L(en) `12` L(zh) ` . Next` (today: `. Next`, D5) | same |
| 24 | `3` | `3` | same |
| 25 | `第3章`, number wait 0 (any mode but "none") | `第3章` | same (today's) |
| 26 | `the 1st item` | `the ` E10 `1` E10 `st item` | `the` E10 `1` E10 `st item` (F1) |
| 27 | `Is it 5?` | `Is it ` E10 `5` E10 `?` | `Is it` E10 `5` E10 `?` (F1) |
| 28 | `第`, Index, `3`, Index, `章` | unchanged | unchanged (O2) |
| 29 | `第3章`, no roles (scope "all") | `第` B10* `3` B10* `章` | same |
| 30 | `WV("en")`, `第3章`, no roles, number language en | `第` B10* `3` B10* `章` (the WV command is dropped, no wrapper) | same |
| 31 | `第3。`, `。` configured, remove off or on | `第` E10 `3` E10 `。` | same |
| 32 | `3，`, `，` configured, remove off or on | `3` E10 `，` | same |
| 33 | `第3。下一章`, `。` configured | `第` E10 `3` E10 `。下一章` | `第` E10 `3` E10 `。` PB50 `下一章` |
| 34 | the same, remove on | as row 33 | `第` E10 `3` PB50 `下一章` |
| 35 | the same, remove on, punctuation wait 0 | as row 33 | `第` E10 `3` E10 `下一章` |
| 36 | `3，下`, `，` configured | `3` E10 `，下` | `3` E10 `，` PB50 `下` |
| 37 | the same, remove on | as row 36 | `3` PB50 `下` |
| 38 | `Total. 12`, `.` configured | `Total. ` E10 `12` | `Total` `.` PB50 `12` (today's) |
| 39 | the same, remove on | as row 38 | `Total` PB50 `12` (today's) |
| 40 | `1，2` (no punctuation pause) | `1` E10 `，` E10 `2` | same (two pauses; today `1，2`) |
| 41 | `1，2`, `，` configured | as row 40 | `1` E10 `，` PB50 `2` |
| 42 | the same, remove on | as row 40 | `1` PB50 `2` |
| 43 | `1 ` (trailing space) | `1 ` | `1` (no edge break, D1) |
| 44 | `Total. 12`, `.` configured, punctuation wait 0 | as row 38 | `Total` `.` E10 `12` |
| 45 | `["3，", "下"]`, `，` configured, remove on, item wait 30 | `3` E10 `，`, `下` | `3` B30 `下` (the item break is the longest) |
| 46 | `12,345元`, value | `12345` E10 `元` (thousands step first) | same |

Not run, but they follow from row 29 and §4.6.3: rows 31–45 for another synth in scope "all" give the same sequences with every break plain.

## 6. Panels, strings and documentation

- **Panels and dialogs:** no change. No control is added, removed or renamed. Focus order and the names NVDA reads stay the same. The Log Record panel keeps its two number switches (§4.7).
- **Translatable strings:** none added or changed. "Number wait factor" / 數字停頓參數 (`addon/locale/zh_TW/LC_MESSAGES/nvda.po:410-411`) now also sets the edge pause. Keeping the label is the conservative default (D8).
- **Readmes (D8).** Update `readme.md` and `addon/doc/zh_TW/readme.md` only. The ru, uk, zh_CN and zh_HK readmes stay untouched, as in phase 35 Q9.
  - Speech pause adjustment bullet (`readme.md:53`, `addon/doc/zh_TW/readme.md:53`). Add:
    - EN: "When the number mode is not Off, the number pause is also placed before and after every number that touches other text in the same item, as in "第3章", even when the number is read in the same language as the text. With a number pause of 0 there is none."
    - zh_TW: 「數字模式不是「不處理」時，數字停頓也會加在每個數字的前後（數字與同一段文字的其他內容相鄰時），例如「第3章」，即使數字與文字以相同的語言朗讀。數字停頓為 0 時不加。」
  - Changelog, "Next update" (`readme.md:73`, `addon/doc/zh_TW/readme.md:73`). Add:
    - EN: "**Pause around numbers:** With a number mode other than Off, the number pause now also separates every number from the text next to it, as in "第3章", even when the number is read in the same language as the text. Set the number wait factor to 0 to turn it off. Words written with digits, such as "1st" or "MP3", are split by the pause as well; where a punctuation pause falls next to a number, only the longer of the two pauses is heard."
    - zh_TW: 「**數字前後停頓：** 數字模式不是「不處理」時，數字停頓現在也會把每個數字與前後的文字分開，例如「第3章」，即使數字與文字以相同的語言朗讀。將數字停頓參數設為 0 即可關閉。含數字的字詞（例如「1st」、「MP3」）也會被停頓分開；標點停頓與數字停頓落在同一處時，只會聽到較長的那一個。」

    If the user picks option B or C of Q1, the sentence about "1st"/"MP3" changes accordingly.
- `buildVars.py` stays untouched.

## 7. Settings, data, compatibility and errors

- **Settings and config:** no new setting, no confspec change, no migration.
  - The pipeline section keeps its keys (`psettings:285-290`).
  - The log section keeps the same switch keys (§4.7).
  - The number language stays a driver setting (`psettings:155-169`).
- **Other synths:**
  - Scope "WorldVoice": the number wait is 0 for another synth (`psettings:338-348`), so it gets no edge break, as U4 intends.
  - Scope "all": it gets edge pauses as plain breaks with the D3 marker. NVDA's `speechXml` keeps every word and pause (`tests/test_pipeline_nvda_ssml.py`, still passing in the prototype).
- **Upstream drivers, engine wrappers, Neural:** untouched. The change is core pipeline code only.
- **Errors:** no new error path.
  - The stage reads only values it already reads today.
  - A failure inside a stage still goes through NVDA's filter handling as today.
  - The pipeline log write guard (`pipeline:785-808`) is unchanged.
- **Performance:** each edge break adds a speech task boundary. A table of many short numbers in text sends up to two more pauses per number. Number mode already does this between digits. Manual item M9 checks responsiveness.

## 8. Test plan

### 8.1 Existing expectations that change

Run with the prototype and temporary aliases `inject_number_mode = inject_number_language = inject_numbers`. Exactly these 14 failed on behaviour; everything else passed:

- `tests/test_pipeline_filters.py::test_number_mode[v1.2-group-2-50]`, `[a. 3-group-2-50]`, `[3.-group-2-50]`, `[.5-group-2-50]` (the `NUMBER_MODES` group-2 rows at pause 50): the edge breaks are added.
- `tests/test_pipeline_filters.py`:
  - `test_main_number_language_passes_through_the_early_stage`: value mode merges strings, so identity becomes equality, and the test still checks that "main" adds no language command at this stage;
  - `test_number_segments_with_main_wrap_in_the_current_language`: deleted with its helper. "main" never wrapped at this stage;
  - `test_number_language_leaves_a_sign_after_a_word_with_it`: rewritten through `inject_numbers` with number language de. Same segments, merged.
- `tests/test_pipeline_stages.py`:
  - `test_stages_order_and_log_keys`: `ORDER` in `tests/pipeline_harness.py:161-172` loses `"number_language"`. `LOG_SWITCH_ORDER` (`:173-183`) is unchanged;
  - `test_worldvoice_keeps_the_break_subclasses_from_the_stages[value|number|group]`: the sets gain `("NumberEdgeBreakCommand", 10)`.
- `tests/test_worldvoice_speak.py`:
  - `test_numbers_without_detection[locale-next]`: `(EN, ".")` becomes `(EN, " .")` (D5);
  - `test_main_moves_a_sign_with_its_number[wait-after|wait-before]`: `[(ZH, "中 "), (EN, "-12"), "|", (EN, "34")]` becomes `[(ZH, "中"), "|", (EN, "-12"), "|", (EN, "34")]`.

Mechanical renames, where the output is identical:

- every call of `inject_number_mode` / `inject_number_language` in `tests/test_pipeline_filters.py`, `tests/test_pipeline_passthrough.py`, `tests/test_pipeline_pause_properties.py` (`run_group_mode`, digit mode, `run_number_mode`, the off-mode identity, the P10 chain) and `tests/test_pipeline_stages.py:185-188` becomes `inject_numbers`.
  - The off-mode identity property keeps `GENERIC_CONTEXT`, which still yields the same objects (§4.2 step 3).
  - Its name becomes "…identity for the thousands and number stages".

Helpers and stubs:

- `tests/nvda_stubs.py:103-118`: read `also_logged_by` (§4.7).
- `tests/test_pipeline_pause_properties.py:742-750`: drop the M5 note (D5).

Guards that must keep passing unchanged: `tests/test_hygiene_guards.py` (ruff 0.16.3, blind-except reasons), `tests/test_pipeline_structure.py` (number lexing imports, `MOVED`, context fields, `getSynth`), `tests/test_pipeline_panels.py:30` (the confspec comprehension over `LOG_SWITCHES`), `tests/test_settings_table_guard.py`.

### 8.2 New unit tests (red first)

- **Edge rule:** the §5 rows as parametrized cases, both the stage output and the full `STAGES` output:
  - every mode;
  - number language default, main and en;
  - roles on and off.
- **U1 / U4:**
  - mode "none" yields the same objects for default/main, and today's wrappers for a locale;
  - `scaled_number_wait()` ≤ 0 adds no `NumberEdgeBreakCommand` in any mode, while the number-mode separators are still `NumberBreakCommand(0)`;
  - global factor below 10 through the real `PipelineSettings` (`psettings:309-313`).
- **O2 / D1:**
  - a number alone in its item;
  - at the item start or end;
  - followed only by whitespace (ASCII space, no-break space, U+3000).
- **O3:** `"1 2"`, `"1 2"`, `"12 34"` in number mode, and `"1 2"` with an en wrapper: exactly one `NumberBreakCommand` between the numbers, and `number_wait_factor` adds none afterwards.
- **O1:** break, wrapper, pieces, wrapper, break order, and dedupe with `start_language` inside another language's stretch, as in `tests/test_pipeline_passthrough.py:118-153`.
- **O4:** `"COVID-19"`, `"中+2"`, `"a -5"`, `"5-3"` in every mode.
- **D5:** the dot rule with and without a wrapper, at pause 0 and 10.
- **E1 / E2:** §5 rows 31–45 through `inject_punctuation_pause` alone and through `STAGES`. Plus:
  - a run with an edge break and a language command or an index command between it and a punctuation break;
  - a tie between an edge break and a punctuation break (the punctuation break stays);
  - a run of two edge breaks only (the first stays);
  - the last item of the sequence (the final `emit`);
  - every case of `tests/test_pipeline_punctuation_pause.py:227-266` and `tests/test_pipeline_passthrough.py:203-212`, unchanged.
- **D3:**
  - `_plain_breaks` marks only edge breaks;
  - another synth's `"Total. 12"` keeps the 50 ms punctuation pause;
  - `"3，下"` with removal gives one pause;
  - `speechXml` keeps every word of `"第3章"` with the breaks.
- **D4:**
  - `LOG_SWITCHES` is unchanged;
  - "Number language" alone logs the number stage once, labelled `"number_mode"`;
  - "Number mode" alone logs two before/after pairs (the existing test);
  - both switches together still log the number stage once;
  - the confspec and the Log Record panel list both switches with their labels.
- **O6:** the §4.8 table as rows of `tests/test_worldvoice_speak.py` at number wait 10, timings "after" and "before".

### 8.3 Property tests (Hypothesis)

- **P-E1, text kept.** In value mode, the `str` items of `inject_numbers` joined equal the input with:
  - each whitespace gap between two numbers removed when the pause is above 0;
  - the dot-rule spaces added.

  Any number language, roles on.
- **P-E2, no edge break in mode "none" or at pause ≤ 0,** for any sequence and context.
- **P-E3, one break between numbers.** In the stage output no two breaks are adjacent. Two numbers that only whitespace separates have exactly one `NumberBreakCommand` between them and no edge break.
- **P-E4, edges sit at number boundaries.**
  - Each edge break has a number piece (or a wrapper and then a number piece) on one side.
  - It has non-blank text of the same input item on the other side.
- **P-E5, edges never meet another break.** After all `STAGES` (`stage.fn`, so classes are kept), with language commands treated as transparent, no edge break is next to any other break.
  - Inputs: random text over digits, letters, marks, CJK, U+3000; existing breaks and language commands.
  - Random number, item and Chinese-space waits; any mode, group size and number language; roles on and off.
  - Punctuation pause on or off, with or without removal, with or without a space among the characters.

  This is the property the prototype ran 4000 times. The existing P10 (`tests/test_pipeline_pause_properties.py:663-701`) keeps running with `inject_numbers` in its chain, and must still pass.
- **P-E6, E2 keeps the longest.** For a run with an edge break, the kept break's time is the run's maximum and the run's other items keep their order. Runs without an edge break are untouched (identity).
- **P8** (`tests/test_pipeline_pause_properties.py:739-761`) keeps comparing number language en and default with random number waits, now including edge breaks. It must still pass.
- **Pause-0 equivalence, during development only (D9).**
  - Copy today's `inject_number_language` and `inject_number_mode` into a scratch oracle.
  - Check that, with pause 0, `inject_numbers` equals the oracle composition after stripping text items and dropping blank ones.
  - Record the result in the plan. The prototype passed 3000 examples.
  - The oracle is not committed. The renamed existing tests keep the characterization.

### 8.4 Mutation testing

- `pipeline/__init__.py` is already in `[tool.mutmut] source_paths` (`pyproject.toml:45-55`).
- On Linux, run mutmut on `_number_item_segments`, `inject_numbers`, `_merge_edge_breaks`, `_is_edge_break` and `_plain_breaks`.
- Record every surviving mutant and its reason in the plan or the review (`DEVELOPMENT_WORKFLOW.md` §7).

### 8.5 Verification (`DEVELOPMENT_WORKFLOW.md` §7)

- `python3 -m pytest -q tests`: compare passed/skipped with 2610/0. The count rises with the new tests, and 0 skipped stays.
- `prek run --all-files`: all Passed.
- `git diff --check`.
- Protected paths: both commands empty.

  ```bash
  git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py
  git ls-files addon/synthDrivers/WorldVoice/driver/Neural
  ```

- Not verifiable on Linux: Windows NVDA, real audio, engine SDKs. The report must say so.

### 8.6 Windows / NVDA manual items

- **M1.** A Chinese voice, default settings. `第3章`, `共 3 章`, `第123章` in value, number and group modes: a short pause before and after the number. Mode "Off": no pause.
- **M2.** Number language English with an English voice installed: `第3章` reads `3` in English, with the pauses.
- **M3.** Number wait factor 0, then global wait factor 0: everything sounds as before this change.
- **M4.** `1 2 3`, `10 000` with a no-break space: one pause between numbers, not longer than before.
- **M5.** Punctuation pause on, `。` and `.` configured, punctuation wait 100:
  - `第3。下一章` and `Total. 12`: the punctuation pause is as long as before and is not doubled;
  - with "remove" on, one pause only.
- **M6.** English text: `the 1st item`, `COVID-19 cases`, `$5`, `MP3`, `Is it 5?`, `10am` on Vocalizer/Cerence, eSpeak, OneCore and SAPI5. Record what each engine says, for Q1.
- **M7.** Scope "all" with NVDA's own OneCore, eSpeak and SAPI5:
  - `第3章` gets the pauses, and nothing after a number is dropped;
  - `Total. 12` with `.` configured keeps its punctuation pause (D3).
- **M8.** Unicode detection on, timings "before" and "after": `abc3中`, `中12` with "Follow document main language". Same voices as before, with pauses.
- **M9.** Say all and arrow navigation through a page or spreadsheet with many numbers: no noticeable lag.
- **M10.** Log Record panel: both "Number language" and "Number mode" are listed. Each one alone records the number stage.

## 9. Affected layers

| File | Change |
|---|---|
| `addon/synthDrivers/WorldVoice/pipeline/__init__.py` | the number stage (§4.2–§4.5), E1/E2 (§4.6.3), the `_plain_breaks` marker (D3), `Stage.also_logged_by`, `_stage_handler`, `_run_logged`, `LOG_SWITCHES` (§4.7), docstrings |
| `readme.md`, `addon/doc/zh_TW/readme.md` | §6 |
| `tests/…` | §8 |

Untouched: `pipeline/numbers.py`, `pipeline/symbols.py`, `pipeline/settings.py`, `pipeline/context.py`, `languageDetection/`, `synth __init__.py`, `speechSettingsDialog.py`, the locale `.po` files, engine wrappers, upstream drivers.

## 10. Risks

- **Engines read split words differently** (F1, Q1). This is the main user-visible risk. It is on by default.
- **More speech tasks per utterance** (§7, M9).
- **E2 drops a break class in favour of a longer one.** Downstream only `number_wait_factor` inspects break classes, and only to block a number break (`pipeline:219-241`), so nothing depends on which class survives.
- **D3's attribute on NVDA's `BreakCommand`.** If NVDA ever adds `__slots__` to `BreakCommand`, setting the attribute raises. A guard test reads `ref/nvda/source/speech/commands.py` with `ast` and checks that `BreakCommand` and its bases define no `__slots__`, so an NVDA upgrade shows the problem in the guard run.

## 11. Open questions and the defaults applied

- **Q1 (needs the user).** Which neighbours get the edge pause: A (every neighbour, as decided), B (not next to letters of space-separated scripts, recommended) or C (B, plus none before item-final punctuation). See F1. Default applied: A.

Decided by orchestrator with the recommended default; user may override before merge:

- **D1. Whitespace-only remainder.** A number followed (or preceded) only by whitespace up to the item's end counts as at the end, so it gets no edge break on that side (§4.3).
  - Why: NVDA strips every item (`speech.py:214`) and `_remove_space` strips them when the number wait is above 0, so that whitespace is never heard.
  - A break there would separate the number from nothing in its item. It would also put a number break next to the following item break (`["1 ", "2"]` with an item wait).
  - Alternative: the literal O2, where whitespace always counts. That needs E2 for item breaks as well, and leaves a trailing pause at the end of an utterance.
- **D2. Edge breaks are their own class with two rules (E1, E2; F3).**
  - Alternative: apply "longest wins" to every number break. That changes M2, P4b and `test_a_number_break_counts_as_an_existing_pause_for_punctuation`, and reverses earlier decisions.
  - Accepted consequence: a full-width mark between two numbers (`"1，2"`) is now an item of its own, so removal drops it. Today the mark before a digit is not a pause point (`pipeline:520-526`).
- **D3. A marker attribute on the plain breaks of other synths**, so that E1/E2 also work in scope "all" (§4.6.3).
  - Alternative: accept another known limit for scope "all". `"Total. 12"` would lose its punctuation pause to the 10 ms edge.
- **D4. Logging.** The merged stage keeps log key `"number_mode"` and is also logged by the `"number_language"` switch, through `Stage.also_logged_by`. Rows are labelled `"number_mode"`. There is no panel or confspec change (§4.7).
  - Alternative: one new switch for the number stage. That needs a new label and translation, and orphans stored keys.
- **D5. The dot rule follows the item's text only,** with or without a kept wrapper (§4.5). The change is sequence-level only, with no audible effect.
- **D6. The whitespace gap between two numbers becomes one plain `NumberBreakCommand` inside the number stage.** `number_wait_factor` is unchanged (§4.3, §4.6.4).
- **D7. Names.**
  - `inject_numbers` and `_number_item_segments`.
  - `NumberEdgeBreakCommand`, `_is_edge_break` and `_merge_edge_breaks`.
  - The old functions are removed and their tests renamed (§4.9, §8.1).
- **D8. Strings and docs.** "Number wait factor" keeps its label. Only the English and zh_TW readmes change: one bullet and one changelog entry (§6).
- **D9. The pause-0 oracle runs during development and is not committed** (§8.3).
- **D10. One edge break instance and one gap break instance per stage run** (§4.3).
