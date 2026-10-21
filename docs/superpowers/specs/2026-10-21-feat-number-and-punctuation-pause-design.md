# Number and punctuation pauses

Date: 2026-10-21.
Base: `master` `133cb1e`. Branch: `feat/number-and-punctuation-pause`. Worktree: `/workspace/WorldVoice-feat-pauses`.
Flow: normal flow (`DEVELOPMENT_WORKFLOW.md` section 3). Section 13 explains why the complex flow is not needed.
Status: every behaviour rule in sections 4.1–4.4 was decided by the user in the discussion of 2026-10-21. Section 11 lists facts found while writing this spec that the user should see before merge. Section 12 lists the questions that remain open.

All `file:line` references are to `133cb1e`. NVDA references are to `ref/nvda` at `7d25bc76e`.

## 1. Problem

Two pause features in the speech pipeline (`addon/synthDrivers/WorldVoice/pipeline/__init__.py`) do not do what users expect.

**Number pause.** `number_wait_factor` (`pipeline/__init__.py:197-206`) inserts a `BreakCommand` only between two *separate* text items that both start with a number (`_both_numbers`, `:150-154`). A screen reader usually sends a whole line as one string, so `"1 2"` or `"共 12 34 個"` never pauses. The check is also a prefix match (`_NUMBER_RE.match`, `:153`; the comment at `:151` says this is deliberate), so an item such as `"12abc"` counts as a number.

**Pair mode.** In pair mode (`_translate_number`, `:293-311`) a pair pause of 0 joins the pairs with a space (`:306`), so the pairs go to the synth as one string, `"12 34"`. That has two effects. The synth may read the pairs as one number or with sentence prosody. And once the number pause splits numbers inside a string (item 1b), `"12 34"` would get a *number* pause between the pairs of one number.

**Punctuation pause.** `inject_punctuation_pause` (`:436-536`) mixes two switches. With the switch off (`punctuation_pause_enabled` False), mark removal still runs (`:460-464`). With the switch on and a wait of 0, no pause point is marked at all (`pause_cmd` is None, `:471`). The settings panel enables the character list when the switch *or* removal is on (`speechSettingsDialog.py:261-272`). The default character list `"،؛,.;:!؟?…"` (`pipeline/settings.py:162`) applies pauses and removal to marks the user never chose.

## 2. Goals and non-goals

Goals:

- Numbers that are separated only by whitespace inside one string are spoken as separate items, with the number pause between them (items 1a–1d).
- In pair mode, pairs are always separate items with a `PairNumberBreakCommand` between them, even at a pause of 0 (item 1e).
- The punctuation switch controls the whole punctuation stage. With the switch on, every pause point gets a `PunctuationBreakCommand`, even at 0 ms. Removal only decides whether the mark itself is kept (items 2-1 to 2-4).
- In the settings panel, the switch enables or disables the controls that depend on it (item 2-5).
- The default character list is empty (item 2-6).

Non-goals:

- No change to `compat/commands.py` (item 1f). A `BreakCommand` with time ≤ 0 still becomes `Pause(0)` and still splits the WorldVoice segment.
- No change to the early returns of other stages: Chinese space (`:379-382`) and item wait (`:164-167`) still pass the input through when their wait is ≤ 0.
- No change to the pause-point rules of the punctuation stage (item 2-7).
- No config migration and no release note for the default change (item 2-6, option C).
- No new settings and no new UI strings.
- The number-language voice switch is out of scope (section 11, F4).

## 3. Current behaviour (verified)

### 3.1 Number pause

- `_NUMBER_RE = r"[+-]?[0-9]+(?:\.[0-9]+)?"` (`:32`). ASCII digits only. It has no word boundary, so it also matches the `1` in `"abc1"`.
- `number_wait_factor` (`:197-206`):
  - Its wait is `scaled_number_wait()` = `global_wait_factor // 10 * number_wait_factor` (`settings.py:187-192`). With the defaults (global 10, number 10; `settings.py:85-102`) it is 10 ms, so the stage is **active by default**.
  - When the wait is ≤ 0, the input passes through unchanged (`:203-205`).
  - Otherwise the stage runs `_remove_space` (`:171-193`), which strips each text item and drops blank ones. It then runs `_insert_between(..., _both_numbers, BreakCommand(wait))` (`:206`), which reuses one `BreakCommand` instance (`:117-131`).
- `_both_numbers` (`:150-154`) requires two adjacent `str` items that both *start with* a number.

### 3.2 Number modes (`inject_number_mode`, `:323-338`; `_translate_number`, `:288-319`)

- value (`:289-291`): the number is unchanged.
- pair (`:293-311`):
  - A decimal number (one that contains `"."`) is unchanged (`:296-298`).
  - A leading sign stays with the first pair (`:299-303`, `:310`).
  - Pairs are read from the left (`:304`).
  - The separator is `PairNumberBreakCommand(pause)` when pause > 0, otherwise `" "` (`:305-306`).
  - `pause` is `scaled_pair_wait()` = `min(pair_wait_factor * 5, 500)` (`settings.py:209-213`). The default `pair_wait_factor` is 0 (`settings.py:103-110`).
- number (digit mode, `:313-319`):
  - Adjacent digits get a `" "` between them (`:316-317`).
  - Each character goes through the digit translation table (`:318`). The table is built from user-defined symbols in NVDA's config `unicode.dic` (`get_translate_table`, `:77-86`; loaded at `addon/synthDrivers/WorldVoice/__init__.py:263-266`).
  - The table is empty unless the user defined replacements for digits. Without the WorldVoice synth it is always empty, because `GENERIC_CONTEXT` has no symbols (`pipeline/context.py:20`).
- `merge_consecutive_strings` (`:359-370`) joins the pieces of each item again. Digit mode therefore turns `"12"` into the single string `"1 2"`.

### 3.3 Punctuation pause (`inject_punctuation_pause`, `:436-536`)

- `wait_factor` is 0 when the switch is off (`:460`). The stage passes through only when the wait is ≤ 0 **and** removal is off (`:462-464`). So removal works with the switch off.
- An empty or blank character list passes through (`:466-469`). This early return is required: `_get_punctuation_regex("")` would compile `[]+(?![\d])` (`:411-412`), which raises `re.PatternError`.
- `pause_cmd` is None when the wait is ≤ 0 (`:471`). Then no break is inserted (`:484-486`, `:511-512`, `:515-516`), but removal still uses the pause points (`:483`, `:506-510`).
- The pause-point rules are kept by this design:
  1. **Not before a digit.** The regex does not match a mark run that is followed by a digit or another configured mark (`:412`).
  2. **One point per run.** Consecutive marks are one segment (`:417-432`).
  3. **Internal point.** A mark inside an item is a pause point only when non-blank text follows later in the same item (`:491-498`).
  4. **Boundary point.**
     - A mark at the end of an item is a pause point only when the next non-Break item is non-blank text, with no `BreakCommand` in between (`:484-486`, `:524-533`).
     - For removal, a `BreakCommand` in between does not matter (`:483`, `:530`).
  5. **Never at the end.** The last item never gets a pause (`:535`).

### 3.4 Pipeline stage order (`STAGES`, `:719-729`)

`apply_speech_dictionaries` → `ignore_comma_between_number` → `number_language` → `number_mode` → `chinesespace_wait_factor` → `item_wait_factor` → `punctuation_wait_factor` → `number_wait_factor` → `speech_viewer`.

### 3.5 From pipeline to audio

- In the WorldVoice synth, `normalize_legacy_commands` (`compat/commands.py:15-16`; called at `WorldVoice/__init__.py:330`) turns every `BreakCommand` into `Pause(time / 1000)`.
- `queue_speech_sequence` sends each `Pause` through `flush()` and then `append_break` (`runtime/requestBuilder.py:44-50`). The text before the pause and the text after it therefore become **separate segments**. A 0 s break task is still queued (`runtime/scheduler.py:231-236`).
- Adjacent `str` items with no command between them are chunks of **one** segment (`requestBuilder.py:51-52`).
- With scope "all", other synthesizers also run the pipeline (`pipeline/scope.py:48-61`; `settings.py:215-239` keeps the stored values for them). NVDA's own drivers turn a `BreakCommand` into markup:
  - eSpeak: `<break time="Nms" />` (`ref/nvda/source/synthDrivers/espeak.py:204-205`);
  - SAPI5: `<silence msec="N" />` (`sapi5.py:928-929`);
  - OneCore: an SSML `break` (`ref/nvda/source/speechXml.py:307-308`).

### 3.6 UI that exposes these settings

- **Speech Pipeline panel** (`addon/globalPlugins/WorldVoice/speechSettingsDialog.py:113-289`). The controls appear in this order: switch checkbox (`:220-230`), remove checkbox (`:232-242`), punctuation wait slider (`:244-252`), character edit (`:254-259`). They are the last controls of the panel. The current enable rules (`:261-272`):
  - the slider is enabled when the switch is on;
  - the edit is enabled when the switch is on **or** removal is on;
  - the remove checkbox is always enabled.
- **NVDA Voice panel with WorldVoice** (`addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py`).
  - The switch, the remove checkbox and the slider are NVDA driver-setting controls (`WorldVoice/__init__.py:104-112`, `:132-135`). The character edit is added after the slider (`VoiceSettingsDialogs.py:51-81`).
  - When the switch is off, the slider's sizer is **hidden** (`:22-49`). The remove checkbox and the edit stay visible and enabled.
  - Pre-existing defect: when the voice changes, NVDA calls `updateDriverSettings` (`ref/nvda/source/gui/settingsDialogs.py:1339-1350`). It runs `_updateValueForControl`, which calls `settingsSizer.Show(...)` for every supported setting (`:1563-1567`, `:1601-1602`). That shows the hidden slider again while the switch is still off. See section 11, F3.
- **Synth settings ring.** NVDA lists every supported setting with `availableInSettingsRing` (`ref/nvda/source/synthSettingsRing.py:208-209`). That includes `punctuationpauseenabled`, `removepunctuationcharacters` and `punctuationwaitfactor`, because `ring` defaults to True (`settings.py:47`, `:135-160`). The ring has no disabled state.

## 4. Design

### 4.1 Number pause (items 1a–1f)

**1a. `_both_numbers` uses `fullmatch`.** Decided by the user (2026-10-21).
`_NUMBER_RE.fullmatch(previous)` and `_NUMBER_RE.fullmatch(current)` replace `.match`. Replace the comment at `:151` with one that states the new rule. For example: `# Whole items only: "12" and "-3.5" are numbers, "12abc" and "1." are not.`
Consequences: `["12abc", "3"]` and `["1.", "2"]` no longer get a number pause. `["1", "2"]` still does.

**1b. Split whitespace-separated numbers inside a string.** Decided by the user (2026-10-21).
`number_wait_factor` becomes:

1. If `scaled_number_wait() <= 0`, yield the input unchanged, as today (`:203-205`).
2. Run `_remove_space` (unchanged).
3. Run a new number-split step on every `str` item. Non-`str` items pass through.
4. Run `_insert_between(..., _both_numbers, BreakCommand(wait))` with one shared `BreakCommand` instance, as today.

The number-split rule for one string `t`, where `m1 … mk` are the `_NUMBER_RE.finditer(t)` matches:

- A match is **glued** to a neighbour when the gap `t[mi.end():mi+1.start()]` between them is the empty string. This only happens when the second match starts with `+` or `-` right after the first, as in `"2345-6789"` or `"3+4"`. A match glued to either neighbour is **unsplittable**. Decided by the user (2026-10-21): F1 option B.
- Two consecutive matches are **joined** when the gap is non-empty and all whitespace (`str.isspace`) and both matches are splittable. This is the meaning of "separated only by whitespace". An empty gap, as in `"1-2"`, does not join.
- A match is **standalone** when it is joined to at least one neighbour.
- If no match is standalone, yield `t` unchanged.
- Otherwise:
  - Yield each standalone match as its own item.
  - Drop the gap between two joined standalone matches.
  - Yield every other piece of `t` verbatim, including its spaces and unsplittable numbers. Never yield an empty piece.
- The step is a generator, like the other stages.

Only regex matches become standalone items, and the two items of every dropped gap fullmatch `_NUMBER_RE`. So every dropped gap gets a break, and digits are never joined together. Because glued matches are never split out, a break appears only where whitespace was removed, and leftover text never fullmatches a number unless it was a separate item in the input. The examples come from the decision and were checked against a scratch prototype (wait 40):

| Input | Output |
| --- | --- |
| `"1 2"` | `"1"`, Break, `"2"` |
| `"共 12 34 個"` | `"共 "`, `"12"`, Break, `"34"`, `" 個"` |
| `"5 -3"` | `"5"`, Break, `"-3"` |
| `"5 - 3"` | unchanged |
| `"1.2.3 4"` | `"1.2."`, `"3"`, Break, `"4"` |
| `"12 apples"` | unchanged |
| `"abc1 2def"` (1d) | `"abc"`, `"1"`, Break, `"2"`, `"def"` |
| `"2026 10 21"` | `"2026"`, Break, `"10"`, Break, `"21"` |
| `"12　34"` (ideographic space) | `"12"`, Break, `"34"` |
| `"02 2345-6789"` | unchanged (F1, option B) |
| `"3-1 2"` | unchanged (F1, option B) |
| `"1 2 3-4"` | `"1"`, Break, `"2"`, `" 3-4"` (F1, option B) |

"Whitespace" means Unicode whitespace (`str.isspace`). It includes the ideographic space U+3000 and the no-break space, and it matches what `_remove_space` strips with `str.strip()` (`:188`). Decided by orchestrator with the recommended default; user may override before merge.

**1c. Digit mode pauses between digits.** Decided by the user (2026-10-21).
No code change is needed: `"12"` becomes `"1 2"` in `number_mode`, and the split in 1b then puts a break between the digits. This applies only while digits are not translated. If the user defined replacements for digits in `unicode.dic`, the digits become words (for example `"一 二"`) and are not split (section 3.2; section 11, F5).

**1d. Numbers attached to text are split too.** Decided by the user (2026-10-21). This follows from 1b, because `_NUMBER_RE` has no word boundary.

**1e. Pair mode always yields `PairNumberBreakCommand(pause)`.** Decided by the user (2026-10-21).
In `_translate_number`, replace `PairNumberBreakCommand(pause) if pause > 0 else " "` (`:306`) with `PairNumberBreakCommand(pause)`. Decimal numbers and numbers with up to two digits are unchanged, so they have no separator.

**1f. `compat/commands.py` is unchanged.** Decided by the user (2026-10-21).
`PairNumberBreakCommand(0)` becomes `Pause(0)`, so `"12"` and `"34"` are spoken as separate segments with only the segment handoff gap between them. The user accepts that gap.

### 4.2 Punctuation pause (items 2-1 to 2-4, 2-7)

New start of `inject_punctuation_pause`:

```python
if not settings.punctuation_pause_enabled:
	yield from speechSequence
	return
chars = settings.punctuation_pause_characters.strip()
if not chars:
	yield from speechSequence
	return
pause_cmd = PunctuationBreakCommand(settings.scaled_punctuation_wait())
```

- **2-1.** Switch off: the input passes through unchanged, whatever the removal setting is. Decided by the user (2026-10-21).
- **2-2.** Switch on: every pause point gets `pause_cmd`, even when its time is 0, and whether or not removal is on. Removal only decides whether the mark is kept. The `pause_cmd is None` branch (`:471`) and the `pause_cmd is not None` tests (`:485`, `:511`, `:515`) are removed. Decided by the user (2026-10-21).
- **2-3.** A value of 0 gives `Pause(0)`, which splits the segment at each pause point. Decided by the user (2026-10-21).
- **2-4.** An empty or blank character list passes the input through unchanged. Keep this early return (`:466-469`); without it the regex raises `re.PatternError`. Decided by the user (2026-10-21).
- **2-7.** All pause-point rules in section 3.3 stay unchanged, including the difference between a boundary *pause* (a `BreakCommand` in between suppresses it) and boundary *removal* (it does not). Decided by the user (2026-10-21).
- With the switch on, an item that contains a configured mark is always split into text and mark pieces (`:502-510`), even when the mark is not a pause point. `"Hi."` at the end becomes `"Hi"`, `"."`. This already happens today when the wait is > 0. Adjacent strings stay chunks of one segment (`requestBuilder.py:51-52`), so it is inaudible.
- Rewrite the docstring (`:441-459`) to describe the new rules. The bullet at `:457-458` ("eligible punctuation is omitted even when the pause duration is zero…") becomes:
  - the switch turns the whole stage on or off;
  - with the switch on, every pause point gets a `PunctuationBreakCommand`, even at 0 ms;
  - removal only drops the mark.

### 4.3 Settings UI (item 2-5)

**Speech Pipeline panel.** Decided by the user (2026-10-21).

- `onPunctuationPauseEnabledChange` (`speechSettingsDialog.py:261-266`) sets the enabled state of the remove checkbox, the punctuation wait slider and the character edit to the state of the switch.
- `onRemovePunctuationCharactersChange` and its `Bind` (`:237-241`, `:268-272`) are no longer needed and are removed.
- The initial call at `:259` stays, so the panel opens in the right state.
- Disabled controls keep their values. `onSave` (`:274-289`) still saves them, so turning the switch on again restores the previous choices.

**NVDA Voice panel (WorldVoice).** The user asked for consistency (2026-10-21). The rule in this section is Decided by orchestrator with the recommended default; user may override before merge.

- Apply the same rule: when the switch is off, disable `removepunctuationcharactersCheckbox`, `punctuationwaitfactorSlider` and `punctuationPauseCharactersEdit`.
- Disabling *replaces* the current hiding of the slider (`VoiceSettingsDialogs.py:40-49`). NVDA's `updateDriverSettings` calls `Show` but never `Enable` (`settingsDialogs.py:1601-1602`), so the state survives a voice change. This also fixes the defect in section 3.6.
- Apply the state when the panel opens, after the character edit exists (`VoiceSettingsDialogs.py:19-20`, already in that order), and on every toggle. The toggle handler keeps `evt.Skip()`, so NVDA still writes the setting (`:35-38`).
- When the synth is not WorldVoice, the panel has no switch checkbox and the character edit stays enabled, as today (`:28-31`).

**Synth settings ring.** No change. Decided by orchestrator with the recommended default; user may override before merge.
The ring has no disabled state. Hiding entries would require a `supportedSettings` list that depends on the switch, and that would also hide the controls in the Voice panel through `isSupported`. With the switch off, a change to "remove" or "punctuation wait factor" in the ring is stored but has no effect until the switch is turned on.

**Focus and what NVDA reads.**

- Pressing Space on "Enable punctuation pause control" toggles it; NVDA says "not checked" or "checked". Focus stays on the checkbox, which is always enabled.
- With the switch off, Tab skips the three disabled controls (wx does not give focus to disabled windows).
  - Speech Pipeline panel: they are the last controls, so Tab moves on to the dialog buttons.
  - Voice panel: Tab moves to NVDA's next control, "Automatic language switching (when supported)".
- Object navigation still reaches the disabled controls, and NVDA reads them as unavailable, for example "Remove configured punctuation at pause points check box unavailable not checked".
- With the switch on, all controls behave as today.

### 4.4 Default character list (item 2-6)

`PipelineSettingSpec("punctuation_pause_characters", str, "", normalize=_strip)` (`settings.py:162`). The confspec becomes `string(default="")` (`settings.py:56-62`). Decided by the user (2026-10-21): option C, no migration and no release note.

## 5. What an NVDA user hears and sees

Terms used in the tables:

- **B(w)** is a `BreakCommand(w)` with w > 0: the text before and after it are separate segments with w ms of silence between them.
- **B(0)**, **PB(0)** and **PuB(0)** become `Pause(0)`: separate segments, with no added silence beyond the segment handoff.
- Text without a command between it is one segment.
- `w` is the number wait and `p` is the pair pause.

### 5.1 Numbers, input `"1234 5678"`, one string

| Mode | Number wait | Pair pause | Before | After |
| --- | --- | --- | --- | --- |
| value | 0 | any | `"1234 5678"` | unchanged |
| value | w > 0 | any | `"1234 5678"` (no pause) | `"1234"`, B(w), `"5678"` |
| number | 0 | any | `"1 2 3 4 5 6 7 8"` | unchanged |
| number | w > 0 | any | `"1 2 3 4 5 6 7 8"` (no pause) | `"1"`, B(w), `"2"`, B(w), … `"8"` (a pause between every digit) |
| pair | 0 | 0 | `"12 34 56 78"` (one segment) | `"12"`, PB(0), `"34 56"`, PB(0), `"78"` |
| pair | 0 | p > 0 | `"12"`, PB(p), `"34 56"`, PB(p), `"78"` | unchanged |
| pair | w > 0 | 0 | `"12 34 56 78"` (one segment) | `"12"`, PB(0), `"34"`, B(w), `"56"`, PB(0), `"78"` |
| pair | w > 0 | p > 0 | `"12"`, PB(p), `"34 56"`, PB(p), `"78"` | `"12"`, PB(p), `"34"`, B(w), `"56"`, PB(p), `"78"` |

Other inputs, all modes:

- `"12.5"`:
  - Pair mode: unchanged.
  - Digit mode: `"1 2.5"`, which becomes `"1"`, B(w), `"2.5"` when w > 0.
- `"-1234"`:
  - Pair mode: `"-12"`, PB(p), `"34"` for every p, including 0.
  - Digit mode with w > 0: `"-1"`, B(w), `"2"`, B(w), `"3"`, B(w), `"4"`.
- `"12"`: pair mode leaves it unchanged, because a number of up to two digits has no separator.
- A pair pause is never followed by a number pause. `_both_numbers` only looks at two adjacent `str` items, and a `PairNumberBreakCommand` sits between the pairs.

### 5.2 Punctuation, input `"Hello, world. Bye."` and `["Hi.", "there"]`

| Switch | Wait | Remove | List | Before | After |
| --- | --- | --- | --- | --- | --- |
| off | any | off | any | unchanged | unchanged |
| off | any | on | `",."` | marks at pause points removed: `"Hello world Bye."` | **unchanged** |
| on | 0 | off | `",."` | unchanged | `"Hello"`, `","`, PuB(0), `" world"`, `"."`, PuB(0), `" Bye"`, `"."`; `"Hi"`, `"."`, PuB(0), `"there"` |
| on | 0 | on | `",."` | `"Hello world Bye."` (no break) | `"Hello"`, PuB(0), `" world"`, PuB(0), `" Bye"`, `"."`; `"Hi"`, PuB(0), `"there"` |
| on | v > 0 | off | `",."` | marks kept, PuB(v) at each point | unchanged |
| on | v > 0 | on | `",."` | marks removed, PuB(v) at each point | unchanged |
| any | any | any | `""` or blank | removal or pauses with the list as typed | unchanged |

- The final `"."` is never a pause point (rule 5), so it is kept even when removal is on.
- `"12,500 and 3.5. Next"` keeps the `,` in `12,500` and the `.` in `3.5` (rule 1). Only the `.` before `" Next"` is a pause point.

### 5.3 Panels

| Switch | Remove checkbox | Wait slider | Character edit |
| --- | --- | --- | --- |
| on | enabled | enabled | enabled |
| off | disabled (value kept) | disabled (value kept) | disabled (value kept) |

The table applies to the Speech Pipeline panel and the WorldVoice Voice panel. Before this change:

- the Speech Pipeline panel always enabled the remove checkbox and enabled the edit when the switch or removal was on;
- the Voice panel hid the slider and left the other two controls enabled.

## 6. Interaction with the stage order (`STAGES`, `:719-729`)

- **`number_mode` runs before `number_wait_factor`.**
  - Digit mode produces `"1 2"`, which the split then breaks apart (1c).
  - Pair mode produces `PairNumberBreakCommand`s, which `_both_numbers` never treats as numbers. So pairs of one number never get a number pause, and two numbers in pair mode still get one (table 5.1).
  - Pair mode no longer produces `"12 34"` strings, which the split would otherwise break apart. Without 1e, the number pause would land between the pairs of one number at pair pause 0.
- **`chinesespace_wait_factor` runs before `number_wait_factor`.** `_CH_SPACE_RE` (`:33`) only matches whitespace between two CJK ideographs, so the space in `"共 12"` is left alone. The number split keeps it verbatim (`"共 "`).
- **`item_wait_factor` runs before `punctuation_wait_factor`.** The item break between two text items is a `BreakCommand`, so it suppresses the boundary punctuation pause (rule 4). This is unchanged and applies at wait 0 too: `["Hello.", B, "World"]` gives `"Hello"`, `"."`, B, `"World"` with no `PunctuationBreakCommand`.
  - `item_wait_factor` runs after `number_mode`. It therefore never sees two adjacent pair strings, because a `PairNumberBreakCommand` is between them.
- **`punctuation_wait_factor` runs before `number_wait_factor`.** A punctuation break between `"1,"` and `" 2"` is a command between the two strings, so no number pause is added on top. The number split runs on the text pieces left after punctuation splitting. Example: `"1 2."` with list `"."` gives `"1 2"`, `"."`, and then `"1"`, B(w), `"2"`, `"."`.
- **`number_language` runs before everything above.** With a number language whose voice differs from the current one, each number is wrapped in `WVLangChangeCommand`s (`:218-266`). Numbers are then never adjacent `str` items, and no number pause is inserted. This is unchanged; see F4.

## 7. Engines and layers

- Shared core only: `pipeline/__init__.py` and `pipeline/settings.py`. No engine wrapper, inner driver, `compat/` or `runtime/` code changes. Engine drivers stay independently installable.
- UI: `addon/globalPlugins/WorldVoice/speechSettingsDialog.py` and `addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py`.
- Config: `pyproject.toml` (`[tool.mutmut] source_paths`, section 9.3).
- The pipeline also runs for other synthesizers when the scope is "all" (section 3.5), so these changes reach them too. See F2.

## 8. Strings, settings and compatibility

**Strings.** No string is added or changed. Removing `onRemovePunctuationCharactersChange` removes no string. `addon/locale/zh_TW/LC_MESSAGES/nvda.po` is unchanged.

**Default change and existing users.**

- NVDA writes a config value only when it differs from the value already in force (`ref/nvda/source/config/__init__.py:1363-1368`). `PipelineSettingsService.update` writes only changed keys (`settings.py:295-298`).
  - A profile in which the user never edited the list has no stored `punctuation_pause_characters`. After the upgrade it reads `""`.
  - A profile with a stored list keeps it. That includes a list stored by an older WorldVoice version, which this spec cannot detect.
- Effects for a profile without a stored list:
  - All defaults (switch on, wait 0, remove off): before, the stage passed through (`:462-464`); after, the empty list passes through. **No change.**
  - Wait > 0 or removal on: before, pauses or removal at `،؛,.;:!؟?…`; after, nothing until the user types characters. This is silent, as accepted under option C.
  - Switch off and removal on: before, removal worked; after, nothing (2-1 and 2-6).
- Effect for a profile with a stored list, switch on (the default) and wait 0: before, the stage passed through when removal was off; after, every pause point splits the segment (`Pause(0)`, 2-3). This was accepted by the user.
- **Number pause:**
  - It is active with the default settings (10 ms, section 3.1). Every user on defaults now hears a short break between whitespace-separated numbers in one string.
  - Pair-mode users at the default pair pause 0 now get one segment per pair.
- **Errors.** Nothing new can raise. The empty-list guard is kept (2-4), and `_NUMBER_RE` and the split use no user input in a pattern.

## 9. Test plan

### 9.1 Unit tests

Number (`tests/test_pipeline_filters.py`, `tests/test_pipeline_stages.py`, `tests/test_pipeline_passthrough.py`):

- `_both_numbers`, through `number_wait_factor`:
  - `["12abc", "3"]` and `["1.", "2"]` get no break;
  - `["12", "3"]` and `["-3.5", "4"]` get one;
  - a non-`str` neighbour gets none.
- Every example in the table in section 4.1, plus `"1-2"`, `"12abc 3"`, a tab gap and a U+3000 gap.
- Across items: `["5", "1 2"]` gives `"5"`, B, `"1"`, B, `"2"`. Commands between items are kept and block the break, as today.
- Wait ≤ 0 returns the input unchanged, including blank items. Keep `test_zero_number_wait_keeps_spaces`.
- All inserted breaks are one instance. Keep the identity check at `tests/test_pipeline_filters.py:87`.
- Digit mode end to end (`inject_number_mode`, then `number_wait_factor`): `"12"` gives `"1"`, B, `"2"`. A digit table that maps `"1"` to a word gives no split (F5).
- Pair mode:
  - `"-1234"` at pause 0 gives `["-12", PairNumberBreakCommand(0), "34"]`;
  - `"123"` gives `"12"`, PB, `"3"`;
  - `"12"` and `"12.5"` are unchanged;
  - with pause 0 and number wait > 0, run through `number_mode` and then `number_wait_factor`: no number break between the pairs of one number.
- The stage order guard (`ORDER`, `tests/pipeline_harness.py:125-135`) is unchanged.

Punctuation (`tests/test_pipeline_punctuation_pause.py`, `tests/test_pipeline_passthrough.py`):

- Switch off returns the input unchanged for every combination of remove, wait and list (parametrized).
- Switch on, wait 0:
  - remove off gives `PunctuationBreakCommand(0)` at internal and boundary points, with the marks kept;
  - remove on gives the same breaks, with the marks removed.
- An empty list and a blank list (`"  "`) return the input unchanged and raise nothing.
- Rules 1–5 at wait 0: `"12,500"` and `"3.5"` get no point, `"Hi.,  there"` gets one point for the `.,` run, the last item gets none, and an existing `BreakCommand` suppresses the boundary pause but not boundary removal.

Settings and panels:

- `tests/test_pipeline_settings_service.py`: the default is `""` and the confspec is `'string(default="")'`.
- `tests/test_settings_panels.py`:
  - For every switch × remove combination, the remove checkbox, the slider and the edit are enabled exactly when the switch is on.
  - Toggling the switch updates all three controls.
  - Toggling removal changes no enabled state.
  - Disabled values are still saved.
- `tests/test_voice_settings_panel.py`:
  - Add `BooleanDriverSetting("removepunctuationcharacters")` to `SETTINGS` (`:20-30`).
  - The three controls are disabled when the switch is off and enabled when it is on, both on open and after a toggle.
  - The slider stays shown.
  - After `updateDriverSettings(changedSetting="voice")` the three controls are still disabled.
  - NVDA's handler still writes the switch value.

### 9.2 Property tests (Hypothesis)

Existing profiles: `tests/conftest.py:18-26` (`default` 200 examples, `deep` 20000, `mutmut` derandomized). Suggested file: `tests/test_pipeline_pause_properties.py`.

Number split. Input: text over digits, `+-.`, ASCII letters, a CJK ideograph, space, tab and U+3000, run through `number_wait_factor` with a wait > 0.

- **N1, walk.** Walk the output against `input.strip()`:
  - each `str` item must be the next verbatim slice;
  - each `BreakCommand` must consume a whitespace run;
  - the walk must end exactly at the end.

  This proves three things: text is kept verbatim, every dropped gap has a break, and nothing else is dropped. Under F1 option B (decided by the user, 2026-10-21) every run a break consumes is non-empty.
- **N7, leftover text.** When the split changed a string, an output text item that fullmatches `_NUMBER_RE` is always next to a break: leftover text never fullmatches a number. Added with the F1 decision (2026-10-21).
- **N2, no gap left.** No output text item contains two `_NUMBER_RE` matches separated only by non-empty whitespace.
- **N3, no gluing.** No two consecutive `str` items have a digit at the end of the first and at the start of the second.
- **N4, placement.** A `BreakCommand` is exactly between consecutive items that both fullmatch `_NUMBER_RE`, and all breaks are one instance.
- **N5, zero wait.** Wait ≤ 0 returns a list equal to the input, item for item, for any mix of strings and commands.
- **N6, pair.** For an optional sign plus n ≥ 3 digits and any pause p ≥ 0, including 0:
  - the output alternates `str` and `PairNumberBreakCommand(p)`;
  - it has `ceil(n / 2) - 1` breaks;
  - the strings join back to the input.

Punctuation. Input: lists of text over letters, digits, spaces and the configured marks, interleaved with existing `BreakCommand`s.

- **P1.** Switch off gives the input unchanged for any list, removal and wait.
- **P2.** Switch on with a non-empty list: the output for wait 0 and for a random wait v differ only in the `time` of the `PunctuationBreakCommand`s.
- **P3.** Removal on and off produce the same number of `PunctuationBreakCommand`s, between the same text. With removal off, the joined text equals the joined input text.
- **P4.** The output never ends with a `PunctuationBreakCommand`. With removal off, a `PunctuationBreakCommand` is never directly next to an existing `BreakCommand`; text that is only marks can still sit between them (`["a", existing, ". b"]`, `[".", ".", existing, "1"]`), because a mark that opens an item is an internal pause point (2-7).
- **P4b.** An existing `BreakCommand` suppresses only the boundary pause before it: taking the existing breaks out of the input gives the same output with each run of them replaced by one `PunctuationBreakCommand` when the item before ends with a mark and non-blank text follows, else by nothing. Added in the review fixes (Minor 2).
- **P5.** An empty or blank list gives the input unchanged.

A scratch prototype of 1b passed N1 (in its user-rule form), N2 and N3 on 20,000 examples. Every empty-gap break it found was an F1 case (for example `"9-3　8"` and `"6+6\t0"`).

### 9.3 Mutation testing (mutmut)

- Add `addon/synthDrivers/WorldVoice/pipeline/__init__.py` to `[tool.mutmut] source_paths` (`pyproject.toml:38-44`). Decided by orchestrator with the recommended default; user may override before merge.
- Run only the changed decision functions, by name glob, with at most 3 workers and the memory guard (stop when MemAvailable < 3 GB). For example: `mutmut run --max-children 3 "addon.synthDrivers.WorldVoice.pipeline.x__both_numbers*"`. Run the same command for `number_wait_factor`, the new split helper(s), `_translate_number` and `inject_punctuation_pause`. The plan confirms the exact names with `mutmut results`.
- `tests/mutation_support.py` already maps the alias-loaded pipeline module to its file.
- Record each surviving mutant, with the reason, in the implementation notes. As in phase 29, confirm each one by running the suite with that mutant applied.

### 9.4 Windows / NVDA manual items

Linux tests reach only the controlled native and audio boundaries. These items need Windows with NVDA:

1. **Value mode, default number wait.** Read `"1 2"`, `"共 12 34 個"`, `"5 -3"`, `"abc1 2def"`, `"12 apples"` and `"02 2345-6789"` (F1). Raise the number wait to make the breaks clearly audible.
2. **Digit mode.** `"12345"` has a break between every digit.
3. **Pair mode, pause 0 versus 50.** `"12345678"` is spoken as pairs. At pause 0 there is only the handoff gap. Each pair is read as a two-digit number.
4. **Punctuation.** List `",."`, `"Hello, world. Bye."`:
   - Switch on, wait 0 versus 50, removal off and on: listen for the segment split at wait 0.
   - Switch off: no change.
5. **Speech Pipeline panel.**
   - Toggle the switch with Space.
   - Tab skips the three controls when the switch is off.
   - Object navigation reads them as unavailable.
   - Values survive Save and reopen.
6. **Voice panel (WorldVoice).**
   - The same checks as item 5.
   - Change the voice while the switch is off: the controls stay disabled and the slider stays where it is (F3).
   - The settings ring (NVDA+Ctrl+arrows) still lists the three settings.
7. **Scope "all"** with eSpeak NG, OneCore and SAPI5: pair mode at pause 0 and `"1 2"` with a number wait. The pairs and digits must not merge (F2).
8. **Upgrade.**
   - A profile without a stored list shows an empty list and has no punctuation pauses.
   - A profile with a stored list keeps it.

## 10. Existing tests and documents that need new expectations

A scratch prototype of sections 4.1, 4.2, 4.3 (Speech Pipeline panel only) and 4.4 was run against the full suite (single process, memory guard). Exactly these 7 tests failed:

| Test | Old expectation | New expectation |
| --- | --- | --- |
| `tests/test_pipeline_filters.py::test_number_mode[-1234-pair-0]` (`NUMBER_MODES`, `:96`) | `["-12 34"]` | `["-12", ("PairNumberBreakCommand", 0), "34"]` |
| `tests/test_pipeline_punctuation_pause.py::test_zero_punctuation_wait_factor_preserves_existing_text_and_breaks` (`:10-16`) | unchanged sequence | `["Hello", ".", existing_break, "World"]`, with no new break because the existing one suppresses it. Rename to match. |
| `tests/test_pipeline_punctuation_pause.py::test_removal_uses_pause_points_even_with_zero_wait_or_disabled_pause_control` (`:43-50`) | removal works at wait 0 without a break, and with the switch off | wait 0 with removal: `"Hello"`, `PunctuationBreakCommand(0)`, `" world"`, `"."`; switch off: unchanged. Rename. |
| `tests/test_pipeline_settings_service.py::test_table_drives_fields_defaults_keys_and_confspec` (`OLD_DEFAULTS`, `:20`; `:34`) | `"،؛,.;:!؟?…"` | `""` and `'string(default="")'` |
| `tests/test_pipeline_settings_service.py::test_get_reads_defaults_and_current_profile` (uses `OLD_DEFAULTS`) | as above | as above |
| `tests/test_settings_panels.py::test_pipeline_panel_enables_pause_controls_from_the_stored_switches[False-True-False-True]` (`:86-106`) | the edit is enabled when only removal is on | the edit is disabled; add the remove checkbox state to every case |
| `tests/test_settings_panels.py::test_pipeline_panel_switches_follow_the_checkboxes` (`:108-130`) | the edit follows switch or removal | all three follow the switch only |

The NVDA Voice panel part of section 4.3 was not in the prototype. It will also change:

- `tests/test_voice_settings_panel.py::test_wait_factor_slider_shows_only_while_pauses_are_enabled` (`:193-196`);
- `tests/test_voice_settings_panel.py::test_toggling_pauses_shows_or_hides_the_slider_and_still_saves_the_setting` (`:199-216`).

Both assert hiding, which becomes disabling.

These existing tests still pass unchanged and should stay as they are:

- `tests/test_pipeline_filters.py::test_number_wait_factor_drops_blanks_then_breaks_between_numbers` (`:78-88`);
- `tests/test_pipeline_stages.py::test_zero_number_wait_keeps_spaces` and `test_positive_number_wait_breaks_between_numbers` (`:107-122`);
- `tests/test_pipeline_passthrough.py::test_number_wait_drops_blank_text_but_not_commands` (`:71-76`) and `test_a_pair_number_break_counts_as_an_existing_pause_for_punctuation` (`:180-188`).

Documents:

- No user document states the old default or the changed rules. `readme.md:47` and `addon/doc/zh_TW/readme.md:47` describe the number, item, Chinese and say-all pauses ("0 means no pause"), which stay true. They do not describe pair mode or punctuation pauses.
- Under option C no release note is added.
- Earlier specs: `docs/superpowers/specs/2026-10-05-phase13-pipeline-design.md:44` says `number_wait_factor` uses "both are number strings". That matches the new `fullmatch` rule and needs no correction.

## 11. Findings needing the user

**F1. A sign-attached number next to a split run gets a break where the input had no whitespace.** This affects decision 1b. **Decided by the user (2026-10-21): option B.** The text below is kept as the record of the question.

- Example: `"02 2345-6789"` (a common Taiwanese phone format).
  - `"02"` and `"2345"` are joined, so both become standalone.
  - `"-6789"` is attached to `"2345"` with an empty gap, so it is left as verbatim text.
  - That text is exactly a number, so `_both_numbers` puts a break before it: `"02"`, B, `"2345"`, B, `"-6789"`.
  - The synth then reads `"-6789"` on its own, probably as "minus 6789".
- Similar cases:
  - `"3-1 2"` gives `"3"`, B, `"-1"`, B, `"2"`;
  - `"1 2-3 4"` gives `"1"`, B, `"2"`, B, `"-3"`, B, `"4"`.
- On its own, `"2345-6789"` is unchanged.
- The user's guarantees still hold: every split pair fullmatches and gets a break, and digits are never joined. But "every break is at a removed whitespace gap" does not hold.

Options:

- **A. Keep the rule as decided.** Accept a break at a sign that is attached to a split number.
- **B. A number attached to another number by an empty gap is never standalone (recommended).**
  - Only whitespace gaps between "free" numbers are split. `"02 2345-6789"` and `"3-1 2"` stay unchanged, and `"1 2 3-4"` gives `"1"`, B, `"2"`, `" 3-4"`.
  - Breaks then appear only at removed whitespace, and digits are still never joined.
  - The change is one extra condition in the "joined" rule, plus the non-empty form of property N1.

This spec describes A, because that is the decision. The implementer must not start the number split until the user answers.

**F2. With scope "all", pair pause 0 and the number split depend on how other synthesizers handle a break.**

- Today pair pause 0 sends `"12 34"`, which separates the pairs for every synth. After 1e it sends `"12"`, `BreakCommand(0)`, `"34"`.
- NVDA's eSpeak, SAPI5 and OneCore drivers emit a 0 ms break tag (section 3.5). Whether each engine treats that tag as a word boundary has not been verified.
- A third-party synth that ignores `BreakCommand` would join the text and read `"1234"`. The same applies to `"1 2"` after the split, which would be read as `"12"`.
- WorldVoice itself is safe, because every break splits the segment.
- Recommendation: keep the decision and run manual item 7. Design a mitigation only if a built-in synth merges the pairs.

**F3. The Voice panel already loses the hidden slider state on a voice change** (section 3.6, `ref/nvda/source/gui/settingsDialogs.py:1601-1602`). The recommended Voice panel rule in section 4.3 (disable instead of hide) fixes it. The slider then stays visible but disabled when the switch is off, where today it is hidden. Tab behaviour is the same.

**F4 (for information; no change proposed).** When the number language selects a voice other than the current one, `number_language` wraps every number in `WVLangChangeCommand`s (`:218-266`). `"1 2"` then reaches `number_wait_factor` as `"1"`, command, command, `"2"`, and gets no number pause, as it does today. The voice switch already separates the segments. Out of scope.

**F5 (for information).** Digit mode pauses between digits only when the digits are not translated. User-defined digit replacements in `unicode.dic` (`:77-86`) turn the digits into words, which the number split does not touch.

## 12. Open questions

1. **F1 rule.** Decided by the user (2026-10-21): option B. A number glued to another number with no gap is never split out (section 4.1).
2. **Voice panel: disable instead of hide** (section 4.3). Decided by orchestrator with the recommended default; user may override before merge.
3. **Settings ring unchanged** (section 4.3). Decided by orchestrator with the recommended default; user may override before merge.
4. **Whitespace means `str.isspace`**, and an empty gap never joins two numbers (section 4.1). Decided by orchestrator with the recommended default; user may override before merge.
5. **Add `pipeline/__init__.py` to mutmut `source_paths`** (section 9.3). Decided by orchestrator with the recommended default; user may override before merge.

## 13. Flow classification

The normal flow is enough. None of the complex-flow criteria (`DEVELOPMENT_WORKFLOW.md` section 4.0) apply:

- the plan and the implementation are done by the same agent;
- no file must be byte-exact (no inner driver, packaging or build change);
- the change is local to one pipeline module, its settings table, two panels and their tests, with no mechanical change across many files.
