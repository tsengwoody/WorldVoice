# Number group mode

Date: 2026-10-21.
Base: `master` `4c5183e`. Branch: `feat/number-group-mode`. Worktree: `/workspace/WorldVoice-feat-group`.
Flow: normal flow (`DEVELOPMENT_WORKFLOW.md` section 3). Section 13 explains why the complex flow is not needed.
Status: every behaviour rule marked G1–G7 and U1–U3 was decided by the user in the discussion of 2026-10-21 and is not reopened here. Section 11 lists facts found while writing this spec that the user should see before merge. Section 12 lists the new open questions, each adopted with a conservative default.

All `file:line` references are to `4c5183e`. NVDA references are to `ref/nvda` at `7d25bc76e`. Line numbers quoted in the decision list (for example ":288-311") came from an older base; the numbers below are the current ones.

## 1. Problem

- **Pair mode is fixed at two digits.** The "pair" number mode (UI label 兩位一組) cuts every number into pairs from the left (`pipeline/__init__.py:355-373`). The pair size is the literal `2` at `:366`. A user who wants to hear a phone number, an account number or a long code in groups of three or four has no way to do so.
- **Digit mode separates digits with a space.** Digit mode ("number") puts a `" "` between adjacent digits (`:375-381`, the space at `:379`). The digits then reach the synth as one string, `"1 2 3"`.
  - With number wait 0 the whole number is one segment, so the synth may join the digits or read them with sentence prosody.
  - With number wait > 0 the number split of the previous feature breaks the digits apart (`_split_spaced_numbers`, `:206-238`). That only works while the digits are ASCII digits. When the user maps digits to words in `unicode.dic` (`get_translate_table`, `:80-89`), `"12"` becomes `"一 二"`, which the split never touches (finding F5 of `docs/superpowers/specs/2026-10-21-feat-number-and-punctuation-pause-design.md:504`).
- **The number pause is a plain `BreakCommand`** (`:264-268`), so later code and tests cannot tell it apart from an item or Chinese-space pause.

## 2. Goals and non-goals

Goals:

- Replace pair mode by a **group** mode with a user-chosen group size of 1–10, default 3 (G1–G3).
- Show the group size and the group wait in both settings panels, enabled only in group mode (G4).
- Rename pair → group everywhere, with no compatibility layer (G5, G7).
- Digit mode always separates digits with a `NumberBreakCommand` carrying the number wait, also at 0 and also for translated digits (U1).
- The number pause stage inserts `NumberBreakCommand` (U2).
- Unknown stored number modes read as "value" (U3).

Non-goals:

- No change to `compat/commands.py` (earlier decision 1f). A `BreakCommand` with time 0 still becomes `Pause(0)` (`compat/commands.py:15-16`) and still splits the WorldVoice segment (`runtime/requestBuilder.py:44-50`).
- No change to the settings ring's list or order (G4). Only the labels of the renamed entries change (section 4.6).
- No config migration (G5, U3). No release note: `buildVars.py` is not touched by this branch (the main checkout holds an uncommitted edit of it).
- No change to the number split rules of the previous feature (`_split_spaced_numbers`, `_both_numbers`), the punctuation stage or the stage order.
- No change to how decimals, signs or one-group numbers are read in group mode (G3 keeps pair mode's rules).
- No `__repr__` for the new command classes. Like `PunctuationBreakCommand` today, they print as `BreakCommand(time=…)` in the pipeline log (`ref/nvda/source/speech/commands.py:210-211`).
- Earlier specs and plans that mention pair mode are historical records and are not edited.

## 3. Current behaviour (verified)

### 3.1 Number modes (`inject_number_mode`, `pipeline/__init__.py:384-400`)

- `inject_number_mode` reads `settings.number_mode`, the digit table (`get_translate_table(ctx)`, `:80-89`) and `settings.scaled_pair_wait()` (`:390-392`). For each text item it runs `iter_number_speech_segments_mode` (`:403-418`), deduplicates language commands when the synth supports roles (`:398-399`) and joins adjacent strings again (`merge_consecutive_strings`, `:421-432`).
- `_translate_number(raw, mode, table, pair_pause)` (`:350-381`):
  - **value** (`:351-353`): unchanged.
  - **pair** (`:355-373`):
    - a number that contains `"."` is unchanged (`:358-360`);
    - a leading `+`/`-` stays on the first pair (`:361-365`, `:372`);
    - pairs are cut from the left: `digits[i : i + 2]` (`:366`);
    - one `PairNumberBreakCommand(pair_pause)` separates the pairs, even at pause 0 (`:367-371`);
    - a number of up to two digits yields one piece, so it is unchanged.
  - **number** (`:375-381`): a `" "` between two adjacent digits (`:378-379`); every character goes through the digit table (`:380`). Any other mode value falls into this branch too.
- `PairNumberBreakCommand` is a bare `BreakCommand` subclass (`:41-42`). `PunctuationBreakCommand` is the same pattern (`:45-46`).
- `scaled_pair_wait()` = `min(pair_wait_factor * PAIR_WAIT_UNIT_MS, MAX_PUNCTUATION_WAIT_MS)` = `min(factor * 5, 500)` ms (`pipeline/settings.py:21-26`, `:209-213`). It does not depend on the global wait factor.

### 3.2 Number pause (`number_wait_factor`, `:249-268`)

- Wait = `scaled_number_wait()` = `global_wait_factor // 10 * number_wait_factor` (`settings.py:187-192`). Defaults 10 and 10 (`settings.py:85-102`), so 10 ms: the stage is active by default.
- Wait ≤ 0: input unchanged (`:261-263`). Otherwise `_remove_space` (`:176-198`), `_split_numbers` (`:241-246`), then `_insert_between(..., _both_numbers, BreakCommand(wait))` (`:264-268`) with one shared instance.
- `_both_numbers` needs two adjacent `str` items that each fullmatch `_NUMBER_RE` (`:153-159`). A command between them prevents the break.

### 3.3 Settings table and config

- `PipelineSettingSpec` (`settings.py:37-62`) holds key, kind, default, driver id, label, display name, ring flag, `min_step` and `normalize`.
  - `convert` returns `normalize(value)` when set, else `kind(value)` (`:51-54`).
  - `confspec` hard-codes `integer(default=…,min=0,max=100)` for every int (`:56-62`).
- `PIPELINE_SETTINGS` (`:66-163`) lists, in Voice panel order, the driver settings `cni`, `nummod` (`:75-84`), `globalwaitfactor`, `numberwaitfactor`, `pairwaitfactor` (`:103-110`), `itemwaitfactor`, `sayallwaitfactor`, `chinesespacewaitfactor`, `punctuationpauseenabled`, `removepunctuationcharacters`, `punctuationwaitfactor`, then the non-driver keys `scope` and `punctuation_pause_characters` (`:161-162`).
- `number_mode` has no `normalize`, so any stored string is used as is.
- `PipelineSettings.effective` zeroes `pair_wait_factor` (with the other pauses) for a non-WorldVoice synth outside scope "all" (`:215-239`, `:234`). It does not touch `number_mode`.
- The repository reads every spec key through `section.get(key, default)` and `spec.convert` (`_get_value`, `:242-249`; `load`, `:261-265`). The service converts every value on `update` and writes only changed keys (`:286-305`).
- The confspec is registered as `config.conf.spec["WorldVoice"]["pipeline"] = dict(PIPELINE_CONFSPEC)` (`WorldVoice/__init__.py:62-79`).
- **NVDA validates a stored value whenever it is read and whenever it is written.**
  - Read: `AggregatedSection.__getitem__` → `_cacheLeaf` → `validator.check(spec, val)` (`ref/nvda/source/config/__init__.py:1179-1217`, `:1269-1274`). An out-of-range or non-integer stored value raises a configobj validation error. `AggregatedSection.get` catches only `KeyError` (`:1250-1254`), and so does `_get_value`.
  - Write: `__setitem__` runs the same check (`:1350-1352`).
  - Only `BASE_ONLY_SECTIONS` are validated when the profile loads (`:565-574`). The `WorldVoice` section is validated only on access.
- **Unknown keys.** A key with no spec entry is never read by `ConfigPipelineRepository.load`, which reads spec keys only. configobj keeps it in the profile and writes it back on save (`config/__init__.py:714-716`).

### 3.4 Driver settings and the ring

- `_pipeline_driver_setting` makes a `NumericDriverSetting` (0–100, no `minVal`/`maxVal` passed), a `BooleanDriverSetting` or a string `DriverSetting`, all with `useConfig=False` (`WorldVoice/__init__.py:103-112`). Only specs with a `driver_id` become driver settings (`:132-135`); `numlan` is inserted after `cni` (`:136-147`).
- `_get_availableNummods` returns `value`, `number` and `pair` (`:475-480`). The `pair` label `_("pair")` at `:479` has no translator comment.
- `_PipelineSetting` descriptors read and write the pipeline service for every spec with a driver id (`:483-505`).
- The ring lists `supportedSettings` in order, skipping `availableInSettingsRing=False` (`ref/nvda/source/synthSettingsRing.py:197-218`).
  - A string setting's ring value is the index of the current id in `available…s`. It is `None` when the id is unknown (`synthSettingsRing.py:86-90`). `increase` then computes `None + 1` and raises `TypeError` (`:38-41`).
  - A ring change also writes `config.conf["speech"][synth.name][id]` (`:63-65`). For `useConfig=False` settings that key is never read back: NVDA loads only `useConfig` settings (`ref/nvda/source/autoSettingsUtils/autoSettings.py:200-202`).

### 3.5 Panels

- **Speech Pipeline panel** (`addon/globalPlugins/WorldVoice/speechSettingsDialog.py:113-278`). Control order: Effect Scope (`:120-133`), Ignore comma (`:135-140`), Number mode (`:142-158`), global wait (`:160-168`), number wait (`:170-178`), **pair wait** (`:180-188`), item, say all, Chinese space (`:190-218`), the four punctuation controls (`:220-253`).
  - An unknown stored mode selects the first choice (`:155-158`).
  - The punctuation switch enables its three controls through `onPunctuationPauseEnabledChange`, bound to `EVT_CHECKBOX` (`:225-229`) and called once at the end of `makeSettings` (`:254-261`).
  - `onSave` writes all values in one `pipeline_settings.update` (`:263-278`).
  - The UI strings in this panel have no translator comments today (for example `:143-145`, `:181`).
- **NVDA Voice panel with WorldVoice** (`addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py`).
  - `makeSettings` creates every driver control up front (`createDriverSettings`, `:110-151`), runs NVDA's `makeSettings`, adds the punctuation character edit and binds the punctuation switch (`:15-20`).
  - The character edit is moved right after the punctuation wait slider's sizer and in tab order (`:52-82`).
  - The switch state is applied when the panel opens (`:22-32`), on `EVT_CHECKBOX` with `evt.Skip()` so NVDA's handler still writes the setting (`:34-37`), and in `_updateValueForControl` after a voice change (`:159-165`).
  - Disabled controls are disabled, not hidden (`:39-50`).
  - `onSave` writes the character edit through the service before NVDA saves (`:84-89`). `onDiscard` restores every pipeline key from a snapshot (`:94-108`).
- **NVDA internals the Voice panel relies on.**
  - A string driver setting becomes a `wx.Choice` named `<id>List`, with its options in `_<id>s`. Its `EVT_CHOICE` handler `StringDriverSettingChanger` calls `evt.Skip()` and writes the setting at once (`ref/nvda/source/gui/settingsDialogs.py:1333-1356`, `:1462-1515`).
  - Only a **voice** change calls `updateDriverSettings` (`:1341-1350`), which runs `_updateValueForControl` for each supported setting (`:1546-1575`). Nothing refreshes the panel after a ring change.
  - `onDiscard` unbinds `EVT_CHOICE` from every `<id>List` (`:1621-1628`).
  - NVDA's own Voice panel uses `nvdaControls.SelectOnFocusSpinCtrl`, a `wx.SpinCtrl` subclass that selects its value on focus, for "Capital pitch change percentage" (`settingsDialogs.py:1839-1845`; `ref/nvda/source/gui/nvdaControls.py:103-129`).
  - `LabeledControlHelper` enables and disables a control's label together with the control (`ref/nvda/source/gui/guiHelper.py:242-277`).

### 3.6 Strings and documents

- `addon/locale/zh_TW/LC_MESSAGES/nvda.po` has `"pair"` → `兩位一組` (`:174-175`), `"pair wait factor:"` → `兩位一組停頓參數：` (`:190-191`) and `"Pair wait factor"` → `兩位一組停頓參數` (`:611-612`). No other locale has any of these three msgids, nor a `group` msgid.
- `readme.md:44-46` and `addon/doc/zh_TW/readme.md:44-46` describe only value and digit modes. Pair mode was never documented.

## 4. Design

### 4.1 Group mode (G1, G2, G3, G7)

Decided by the user (2026-10-21).

- `PairNumberBreakCommand` becomes `GroupNumberBreakCommand(BreakCommand)`, docstring "Pause between digit groups in group number mode." (G7).
- The mode value `"pair"` becomes `"group"` in `_translate_number`.
- `_translate_number` takes the group size and the group pause as parameters. Suggested signature:

  ```python
  def _translate_number(
      raw: str, mode: str, table: dict[int, str], group_size: int, group_pause: int, number_pause: int,
  ) -> Iterator[SpeechCmd]
  ```

  `iter_number_speech_segments_mode` passes the same three values through. `inject_number_mode` reads them once per call from `settings.group_size`, `settings.scaled_group_wait()` and `settings.scaled_number_wait()`.
- The group branch keeps pair mode's rules exactly; only `2` at `:366` becomes `group_size` (G1, G3):
  - a number that contains `"."` is unchanged (decimals are read as one value);
  - the sign stays on the first group;
  - groups are cut from the **left**: size 3 turns `"12345"` into `"123"`, `"45"`;
  - one `GroupNumberBreakCommand(group_pause)` instance separates the groups, even at pause 0;
  - a number of at most `group_size` digits is unchanged.
- The digit table is not applied in group mode, as in pair mode today.
- `group_size` is always in 1–10 when it comes from the settings service (section 4.3). `_translate_number` does not guard against 0 itself.

### 4.2 Digit mode and the number pause (U1, U2)

Decided by the user (2026-10-21).

- New class `NumberBreakCommand(BreakCommand)` in `pipeline/__init__.py`, docstring "Pause between numbers, and between the digits of a number in digit mode."
- **U2.** `number_wait_factor` inserts `NumberBreakCommand(wait)` instead of `BreakCommand(wait)` (`:267`). It is still one shared instance per call, and still only when the wait is > 0. It sounds the same: `normalize_legacy_commands` turns every `BreakCommand` subclass into `Pause(time / 1000)` (`compat/commands.py:15-16`).
- **U1.** The digit branch of `_translate_number` yields `NumberBreakCommand(number_pause)` between two adjacent digits instead of `" "` (`:378-379`).
  - `number_pause` is `settings.scaled_number_wait()`. The break is inserted for **every** value, including 0. At 0 it becomes `Pause(0)`, so each digit is its own segment (accepted, consistent with decision 1f).
  - One instance per number, like the group separator.
  - The table translation of each character is unchanged (`:380`). Translated digits are therefore separated by breaks too. This fixes F5 of the previous spec.
  - Non-digits are unchanged: a sign or `"."` is never next to a break. So `"-12"` gives `"-1"`, NB, `"2"`, and `"12.5"` gives `"1"`, NB, `"2.5"` after merging.
- `number_mode` runs before `number_wait_factor` (section 6). In digit mode the digits are already separate items with a command between them, so:
  - `_split_spaced_numbers` finds nothing to split inside a number;
  - `_both_numbers` never sees two adjacent digit strings, so it adds no second break.

  A Hypothesis run on a prototype (3,000 examples over text made of digits, spaces, letters, `.`, `,` and `-`, in every mode, with sizes 1–10 and random waits) found no `NumberBreakCommand` or `GroupNumberBreakCommand` next to another `BreakCommand` after the whole chain `number_mode` → `chinesespace_wait_factor` → `item_wait_factor` → `punctuation_wait_factor` → `number_wait_factor`.

### 4.3 Settings, config and normalisation (G5, U3)

Decided by the user (2026-10-21), except where a line says otherwise.

**Spec bounds.**
- `PipelineSettingSpec` gains `min_value: int = 0` and `max_value: int = 100`.
- `confspec` emits `integer(default={default},min={min_value},max={max_value})`. Every existing int keeps its exact confspec string.
- `convert` clamps every int-kind result to `[min_value, max_value]` after `normalize` or `kind(value)`. Decided by orchestrator with the recommended default; user may override before merge (Q3).
  - For the existing int keys this changes nothing a user can see. NVDA rejects an out-of-range write anyway (`config/__init__.py:1350-1352`), and the 0–100 sliders cannot produce one.
  - `_floor_to_ten` (`settings.py:29-30`) still runs first for `global_wait_factor`.
- What "validated on read" means with NVDA's config is section 11, F1.

**Keys.**

| Key | Kind | Default | Bounds | Driver id | Label | Ring |
| --- | --- | --- | --- | --- | --- | --- |
| `number_mode` | str | `"value"` | — | `nummod` (unchanged) | unchanged | yes (unchanged) |
| `group_wait_factor` (was `pair_wait_factor`) | int | 0 | 0–100 | `groupwaitfactor` (was `pairwaitfactor`) | `_("Group wait factor")` (was `"Pair wait factor"`) | yes, same position |
| `group_size` (new) | int | 3 | 1–10 | none | none | no |

- The driver id `groupwaitfactor` and the label are Decided by orchestrator with the recommended default; user may override before merge (Q10).
- `group_wait_factor` keeps the position of `pair_wait_factor` in `PIPELINE_SETTINGS`, so the Voice panel and ring order do not change.
- `group_size` has no driver id: no driver setting, no descriptor, not in the ring (G4). It is appended after `punctuation_pause_characters` with the other non-driver keys. Decided by orchestrator with the recommended default; user may override before merge (Q7).
- `PipelineSettings` renames the field `pair_wait_factor` to `group_wait_factor` and adds `group_size: int`.
- `PAIR_WAIT_UNIT_MS` becomes `GROUP_WAIT_UNIT_MS` (still 5), and `scaled_pair_wait` becomes `scaled_group_wait` (same formula: `min(group_wait_factor * 5, 500)`).
- `effective` zeroes `group_wait_factor` where it zeroed `pair_wait_factor` (`:234`). It leaves `group_size` alone, as it leaves `number_mode` alone.
- New confspec entries: `group_wait_factor = integer(default=0,min=0,max=100)`, `group_size = integer(default=3,min=1,max=10)`. `pair_wait_factor` disappears from the confspec.

**U3: unknown number modes.**
- `number_mode` gets `normalize=_number_mode`. It maps `str(value)` to itself when it is one of `NUMBER_MODES = ("value", "number", "group")`, else to `"value"`.
- `NUMBER_MODES` lives in `pipeline/settings.py`. `_get_availableNummods` and the Speech Pipeline panel keep their own ordered lists. A test checks that both lists equal `NUMBER_MODES`.
- The normalisation runs on read (`load`) and on write (`update`). So:
  - a stored `"pair"` reads as `"value"`;
  - `synth.nummod = "pair"` stores `"value"`;
  - both panels and the ring show "value".

### 4.4 Speech Pipeline panel (G4)

Decided by the user (2026-10-21): the order and the enable rule.

New control order:

1. Effect Scope: (choice)
2. Ignore comma between number (checkbox)
3. Number mode: (choice: value, number, group)
4. **Group size:** (new spin control)
5. **group wait factor:** (slider, moved up from after number wait)
6. global wait factor:
7. number wait factor:
8. item wait factor:, sayall wait factor:, chinese space wait factor:
9. the four punctuation controls, unchanged

Details:

- `self.number_mode_value = ["value", "number", "group"]`, with choice labels `_("value")`, `_("number")`, `_("group")`.
- `self._group_size_spin = settingsSizerHelper.addLabeledControl(_("Group size:"), nvdaControls.SelectOnFocusSpinCtrl, min=…, max=…, initial=settings.group_size)`.
  - min and max come from `PIPELINE_SETTING_BY_KEY["group_size"]`, so the range has one source.
  - `SelectOnFocusSpinCtrl` is a `wx.SpinCtrl` (G3). Choosing it over a plain `wx.SpinCtrl` is Decided by orchestrator with the recommended default; user may override before merge (Q2). Reason: NVDA's Voice panel uses it for its own spin control.
- `self._pair_wait_factor_slider` becomes `self._group_wait_factor_slider`, labelled `_("group wait factor:")`, and is created right after the spin control.
- Enable rule (same pattern as the punctuation switch):
  - `self.Bind(wx.EVT_CHOICE, self.onNumberModeChange, self._number_mode_choice)`.
  - `onNumberModeChange(event)` enables the spin control and the group wait slider exactly when the current selection is `"group"`. A selection outside the list counts as not group.
  - `makeSettings` calls `self.onNumberModeChange(None)` once, after both controls exist, so the panel opens in the right state.
  - Disabled controls keep their values. `onSave` still saves them.
- `onSave` writes `group_wait_factor=self._group_wait_factor_slider.GetValue()` and `group_size=self._group_size_spin.GetValue()` in the same single `update` call.

### 4.5 NVDA Voice panel (G4)

Decided by the user (2026-10-21): a custom spin control made like the punctuation character edit, the enable rule for both group controls, the three update points and the unchanged ring.

**Placement: right after the Number Mode list.** Decided by orchestrator with the recommended default; user may override before merge (Q1). The user asked the spec to choose between "after the number mode choice" and "after the group wait slider". Reasons for "after the number mode choice":

- It keeps the Speech Pipeline panel's order: mode, then size.
- The size is the mode's own parameter. The group wait slider is a driver setting; NVDA lays driver controls out in `supportedSettings` order, and that order is also the ring order (`synthSettingsRing.py:207-218`). Moving the slider next to the size would mean either reordering the ring (excluded by G4) or moving a second NVDA-made control by hand.
- Tab order stays simple. With group mode off, the disabled spin control is skipped, so Tab goes from Number Mode to Global wait factor, as today.

The cost: in the Voice panel, Global wait factor and Number wait factor sit between the size and the group wait slider.

Resulting Voice panel order (WorldVoice): … Ignore comma between number, Number Language, Number Mode, **Group size:**, Global wait factor, Number wait factor, **Group wait factor**, item wait factor, … , Punctuation wait factor, Punctuation pause characters:, then NVDA's own controls.

Details:

- `makeSettings` (`VoiceSettingsDialogs.py:15-20`) becomes, in order:
  1. `createDriverSettings()`
  2. `super().makeSettings(settingsSizer)`
  3. `_addGroupSizeControl(settingsSizer)`
  4. `_addPunctuationPauseCharactersControl(settingsSizer)`
  5. `_bindPunctuationPauseEnabledToggle()`
  6. `_bindNumberModeChoice()`

  Adding the size before the character edit keeps the "number controls before punctuation controls" order when a control falls back to the end (see "Another synthesizer" below).
- `_addGroupSizeControl` follows `_addPunctuationPauseCharactersControl` (`:52-82`):
  - it creates `self.groupSizeSpin` with `addLabeledControl(_("Group size:"), nvdaControls.SelectOnFocusSpinCtrl, min, max, initial=pipeline_settings.get().group_size)`;
  - when `self.sizerDict` has `"nummod"`, it detaches the spin control's sizer and inserts it right after the `nummod` sizer, keeping proportion, flag and border;
  - it calls `self.groupSizeSpin.MoveAfterInTabOrder(self.nummodList)`.
- `_applyGroupControlsState()`:
  - with no `nummodList`, it returns and changes nothing;
  - otherwise the state is "group" when `self._nummods[self.nummodList.GetSelection()].id == "group"`, guarding a selection outside the list;
  - it enables or disables `groupwaitfactorSlider` and `groupSizeSpin`, skipping a control that does not exist yet.

  It reads the **control**, not `driver.nummod`. WorldVoice's `EVT_CHOICE` handler is bound after NVDA's, so it runs first, before `StringDriverSettingChanger` has written the setting (`settingsDialogs.py:1340-1356`; the punctuation handler at `VoiceSettingsDialogs.py:34-37` relies on the same order).
- The state is applied at three points, as for the punctuation switch:
  1. **When the panel opens:** `_bindNumberModeChoice()` binds `wx.EVT_CHOICE` on `nummodList` to `_onNumberModeChoice` and applies the state once. It runs after the spin control exists. The earlier call from `_updateValueForControl` during `super().makeSettings` runs before the spin control exists and only sets the slider's state.
  2. **On `EVT_CHOICE`:** `_onNumberModeChoice(evt)` calls `evt.Skip()` first, so NVDA still writes the setting, then applies the state.
  3. **In `_updateValueForControl`:** in the string branch (`:166-189`), after the selection is set, `if setting.id == "nummod": self._applyGroupControlsState()`. This covers a voice change, including a voice change after a ring change made while the dialog was open. `SetSelection` fires no `EVT_CHOICE`.
- `onSave` writes `punctuation_pause_characters` and `group_size=self.groupSizeSpin.GetValue()` in one `pipeline_settings.update` call, then calls NVDA's `onSave`. `onDiscard` needs no change: `group_size` is in `PIPELINE_CONFIG_KEYS`, so the snapshot restores it.
- Like the character edit, the size is written on Save or Apply. The group wait slider is a driver control and writes at once.
- **Another synthesizer in the same panel** (the user changes synth while the dialog is open; the panel class stays patched until WorldVoice terminates, `WorldVoice/__init__.py:200-204`):
  - there is no `nummodList`, so the spin control stays where the helper put it, after NVDA's own controls and before the character edit;
  - it stays enabled and is saved on Save, as the character edit is (`tests/test_voice_settings_panel.py:254-270`).

  Decided by orchestrator with the recommended default; user may override before merge (Q6).

### 4.6 Settings ring

Unchanged list and order (G4).

- `nummod` still cycles value → number → group; the last value is now shown as "group" (群組).
- `groupwaitfactor` takes the place of `pairwaitfactor`; its ring name is the label "Group wait factor" (群組停頓參數).
- The group size is not in the ring.
- The ring has no disabled state. A group wait change made in another mode is stored and takes effect when group mode is chosen.

### 4.7 Strings and translations (G6)

| Where | msgid | zh_TW | Source |
| --- | --- | --- | --- |
| `speechSettingsDialog.py` choice, `WorldVoice/__init__.py` `availableNummods` | `"group"` (was `"pair"`) | 群組 | Decided by the user (2026-10-21) |
| both panels | `"Group size:"` (new) | 每組位數： | Decided by the user (2026-10-21) |
| `speechSettingsDialog.py` slider | `"group wait factor:"` (was `"pair wait factor:"`) | 群組停頓參數： | Decided by the user (2026-10-21) |
| `pipeline/settings.py` driver label (Voice panel, ring) | `"Group wait factor"` (was `"Pair wait factor"`) | 群組停頓參數 | Decided by orchestrator with the recommended default; user may override before merge (Q5) |

- Every new or changed `_()` call gets a `# Translators:` comment directly above it, or inside the parentheses in NVDA's multi-line form (`tests/test_translator_comments.py:14-27`). Suggested texts:
  - `"group"`: "A number mode: the digits of a number are read in groups of the chosen size, counted from the left."
  - `"Group size:"`: "Label for a spin control that sets how many digits each group has in the group number mode."
  - `"group wait factor:"`: "Label for a slider that sets the pause between digit groups."
  - `"Group wait factor"`: keep the existing "Label for a setting in voice settings dialog."
- `addon/locale/zh_TW/LC_MESSAGES/nvda.po`: replace the three pair entries and add `"Group size:"`; check with `msgfmt --check`; generate the `.pot` with `scons pot` and do not commit it (`DEVELOPMENT_WORKFLOW.md` section 6).
- Other languages: none of them has the pair strings (section 3.6), so nothing is lost. The new strings stay untranslated until translators add them (G6).

## 5. What an NVDA user hears and sees

Terms:

- **NB(x)** is `NumberBreakCommand(x)`, **GB(x)** is `GroupNumberBreakCommand(x)`, **B(x)** is a plain `BreakCommand(x)`.
- Any of them becomes `Pause(x/1000)`: the text before and after it are separate segments, with x ms of silence. At x = 0 only the segment handoff gap remains.
- Text with no command between it is one segment.
- `w` = number wait (`scaled_number_wait`), `g` = group wait (`scaled_group_wait`), `n` = group size.
- "Before" is `master` `4c5183e`; it only differs from "After" where noted.

Every "After" cell below was produced by a scratch prototype of section 4 running the real stage functions in `STAGES` order. Punctuation was off, item and Chinese-space waits were 0, and the context was generic unless noted.

### 5.1 `"12345678"`

| Mode | After | Before |
| --- | --- | --- |
| value | unchanged, any w | same |
| number, w = 0 | `"1"`, NB(0), `"2"`, NB(0), … `"8"` (eight segments) | `"1 2 3 4 5 6 7 8"`, one segment |
| number, w > 0 | `"1"`, NB(w), `"2"`, … `"8"` | `"1"`, B(w), `"2"`, … `"8"` (same sound) |
| group n = 1 | `"1"`, GB(g), `"2"`, … `"8"`, any w | — |
| group n = 2 | `"12"`, GB(g), `"34"`, GB(g), `"56"`, GB(g), `"78"`, any w | identical to pair mode |
| group n = 3 | `"123"`, GB(g), `"456"`, GB(g), `"78"`, any w | — |
| group n = 10 | unchanged (8 digits ≤ 10) | — |

### 5.2 `"-1234567"`

| Mode | After |
| --- | --- |
| value | unchanged |
| number | `"-1"`, NB(w), `"2"`, NB(w), … `"7"` (the sign stays with the first digit; w = 0 included) |
| group n = 1 | `"-1"`, GB(g), `"2"`, … `"7"` |
| group n = 2 | `"-12"`, GB(g), `"34"`, GB(g), `"56"`, GB(g), `"7"` |
| group n = 3 | `"-123"`, GB(g), `"456"`, GB(g), `"7"` |
| group n = 10 | unchanged |

### 5.3 `"12.5"`

| Mode | After | Before |
| --- | --- | --- |
| value | unchanged | same |
| number | `"1"`, NB(w), `"2.5"` for any w | `"1 2.5"` at w = 0; `"1"`, B(w), `"2.5"` at w > 0 |
| group, any n | unchanged (decimals are read as one value) | pair: unchanged |

### 5.4 `"1 2"` (two numbers in plain text)

| Mode | w = 0 | w > 0 |
| --- | --- | --- |
| value | `"1 2"`, one segment | `"1"`, NB(w), `"2"` |
| number | `"1 2"`, one segment (single digits get no digit break) | `"1"`, NB(w), `"2"` |
| group, any n | `"1 2"`, one segment | `"1"`, NB(w), `"2"` |

Before: the same, with B(w) instead of NB(w).

Two longer numbers, `"12345 678"`, group n = 3:
- w = 0: `"123"`, GB(g), `"45 678"`. The last group of the first number and the second number share a segment, as pair mode did.
- w > 0: `"123"`, GB(g), `"45"`, NB(w), `"678"`.

### 5.5 Digits mapped through the number-language symbol table

Context: WorldVoice, language zh, number language zh, `unicode.dic` maps `0`–`9` to `〇一二三四五六七八九`.

| Mode, input | After | Before |
| --- | --- | --- |
| number, `"123"` | `"一"`, NB(w), `"二"`, NB(w), `"三"`, any w | `"一 二 三"`; the Chinese-space stage turned each space into B(Chinese-space wait) when that wait was > 0 (`_CH_SPACE_RE`, `:34`, matches `一`–`九` but not `〇`); at Chinese-space wait 0, one segment |
| number, `"12.5"` | `"一"`, NB(w), `"二.五"` | `"一 二.五"` |
| number, `"共 12 34 個"`, Chinese-space wait 10 | `"共"`, B(10), `"一"`, NB(w), `"二"`, B(10), `"三"`, NB(w), `"四"`, B(10), `"個"` | every space became B(10) |
| group n = 2, `"1234"` | `"12"`, GB(g), `"34"`; the table is not applied, so the digits stay ASCII and the number-language voice reads them | — |

With a number-language voice different from the current one, each number is wrapped in `WVLangChangeCommand`s by `number_language` (`:280-306`). The breaks of digit and group mode then sit inside that wrapper: `"a 1234 b"` in digit mode gives `"a"`, L(zh), `"1"`, NB, `"2"`, NB, `"3"`, NB, `"4"`, L(en), `"b"`.

### 5.6 Group size 1 versus digit mode

Both are kept. Decided by the user (2026-10-21).

| | Group, size 1 | Digit mode ("number") |
| --- | --- | --- |
| Separator | `GroupNumberBreakCommand` | `NumberBreakCommand` |
| Wait used | group wait: 5 ms per step, at most 500 ms, independent of the global factor | number wait: global units × number wait factor |
| Digit table (`unicode.dic`) | not applied | applied to every character |
| Decimals | the whole number is unchanged: `"12.5"` | split before the point: `"1"`, NB, `"2.5"` |
| Sign | on the first digit: `"-1"`, GB, `"2"` | on the first digit: `"-1"`, NB, `"2"` |
| Number pause from the number pause stage | added between two whole numbers that only whitespace separates | the same |

### 5.7 Panels

| Number mode | Group size | Group wait factor |
| --- | --- | --- |
| group | enabled | enabled |
| value or number | disabled, value kept and saved | disabled, value kept and saved |

This applies to the Speech Pipeline panel and to the WorldVoice Voice panel. It is applied when the panel opens, when the mode choice changes, and (Voice panel) after a voice change.

**Focus and what NVDA reads.**

- Speech Pipeline panel:
  - Tab order: Effect Scope, Ignore comma, Number mode, Group size, group wait factor, global wait factor, …
  - With a mode other than group, Tab goes from Number mode straight to global wait factor, because wx does not focus disabled windows.
  - On the spin control NVDA reads its label, "Group size:" (zh_TW "每組位數："), the spin-button role and the value, for example 3.
  - `SelectOnFocusSpinCtrl` selects the value on focus, so typing a digit replaces it.
  - Up and Down Arrow change the value within 1–10.
- Voice panel: Number Mode, Group size, Global wait factor, Number wait factor, Group wait factor, … With a mode other than group, both group controls are skipped by Tab.
- Object navigation still reaches a disabled control, and NVDA reports it as unavailable. Its label is disabled with it (`guiHelper.py:256-258`).
- Changing the mode with the arrow keys in the closed choice fires `EVT_CHOICE` on each change, so the enabled state follows at once.

## 6. Interaction with the stage order (`STAGES`, `pipeline/__init__.py:788-798`)

`apply_speech_dictionaries` → `ignore_comma_between_number` → `number_language` → `number_mode` → `chinesespace_wait_factor` → `item_wait_factor` → `punctuation_wait_factor` → `number_wait_factor` → `speech_viewer`. Unchanged.

- **`ignore_comma_between_number` runs first.**
  - With it on, `"1,234,567"` becomes `"1234567"` before grouping.
  - With it off, each comma-separated part is its own number. In group mode each part is grouped on its own; in digit mode `"1,234"` gives `"1,2"`, NB, `"3"`, NB, `"4"`.
- **`number_language` runs before `number_mode`.** It wraps whole numbers in `WVLangChangeCommand`s (`:280-306`). The digit and group breaks are then inside the wrapper (section 5.5).
  - `inject_number_mode` deduplicates language commands only for its own segments (`:398-399`) and forwards the commands unchanged.
  - `inject_langchange_reorder` in `speak` (`WorldVoice/__init__.py:325`) keeps a non-language command with the text that follows it, so each break stays between its digits.
- **`number_mode` runs before `chinesespace_wait_factor`.**
  - The Chinese-space regex needs whitespace between two CJK ideographs (`:34`). Translated digits are no longer separated by a space, so the Chinese-space stage no longer adds breaks between them.
  - It still adds them between translated numbers and the surrounding CJK text (section 5.5; finding F3).
- **`item_wait_factor`** breaks only between two adjacent `str` items (`:149-150`, `:163-173`). Digit and group breaks sit between the pieces of one item, so no item break is added there.
  - `["12", "34"]` in digit mode gives `"1"`, NB, `"2"`, B(item), `"3"`, NB, `"4"`.
- **`punctuation_wait_factor`.**
  - NB and GB are `BreakCommand`s. A boundary punctuation pause before one of them is suppressed, as before with `PairNumberBreakCommand` (`tests/test_pipeline_passthrough.py:180-188`).
  - `"Total 1234."` + `"Next"` in group mode n = 2, punctuation `"."`, item wait 30: `"Total 12"`, GB, `"34"`, `"."`, B(30), `"Next"`.
- **`number_wait_factor` runs last of the pause stages.**
  - `_remove_space` strips each text item; the digit and group pieces carry no edge whitespace.
  - `_split_spaced_numbers` only splits whitespace gaps that are left inside a text item, such as `"45 678"` (section 5.4).
  - `_both_numbers` needs two adjacent strings, and a command always separates two digits or two groups of one number. So a number pause is never added inside a number, and never next to a digit or group break (section 4.2).

## 7. Engines and layers

- **Shared core:** `pipeline/__init__.py` and `pipeline/settings.py`.
- **Driver package:** `synthDrivers/WorldVoice/__init__.py` (`availableNummods`) and `VoiceSettingsDialogs.py`.
- **Global plugin:** `speechSettingsDialog.py`.
- **Untouched:** no engine wrapper, inner driver, `compat/` or `runtime/` code. Engine drivers stay independently installable.
- **Other synthesizers:** with scope "all" the pipeline also runs for them (`pipeline/scope.py:48-61`). They now get NB and GB instead of the `" "` digit separator; see F2.
- **Config:** `pyproject.toml` (`[tool.mutmut] source_paths`, section 9.3).

## 8. Config, compatibility and errors

No migration and no compatibility code (G5, U3). Decided by the user (2026-10-21).

**Effect on an existing profile.**

| Stored before | After the upgrade |
| --- | --- |
| `number_mode = pair` | Reads as `"value"`. Both panels and the ring show "value". The user hears whole numbers until they choose group mode. Group size 2 reproduces the old pair reading. |
| `pair_wait_factor = N` | Ignored and lost. `group_wait_factor` starts at its default 0. The stale key stays in `nvda.ini`, because configobj writes every key back (`config/__init__.py:714-716`). It is never read: `load` reads spec keys only, and NVDA validates only keys it is asked for (section 3.3). |
| `number_mode = pair` written by the ring into `[speech][WorldVoice]` (`synthSettingsRing.py:63-65`) | Never read. NVDA loads only `useConfig` settings (`autoSettings.py:200-202`). |
| nothing stored | group size 3, group wait 0, mode value (unchanged default) |

- A stored `"pair"` stays in `nvda.ini` until the user picks another mode. Saving the panel with "value" writes nothing, because `update` compares with the normalised current value (`settings.py:294-298`). This is harmless.
- **U3 also removes two latent failures for a stored `"pair"`.** Without it:
  - `_translate_number` would fall into the digit branch and read the number digit by digit (`pipeline/__init__.py:375-381`);
  - the ring's Number Mode entry would raise `TypeError` on the next increase (`synthSettingsRing.py:38-41`, `:86-90`).
- **Errors.**
  - WorldVoice only writes `group_size` through `update`, which clamps first, so its own writes never fail NVDA's 1–10 check.
  - A hand-edited out-of-range or non-integer value fails NVDA's check on read and raises; see F1. Nothing else new can raise.

## 9. Test plan

### 9.1 Unit tests

**Settings** (`tests/test_pipeline_settings_service.py`, `tests/test_config_stub.py`):
- Confspec:
  - `group_size` → `"integer(default=3,min=1,max=10)"`;
  - `group_wait_factor` → `"integer(default=0,min=0,max=100)"`;
  - `global_wait_factor` keeps `"integer(default=10,min=0,max=100)"`;
  - `pair_wait_factor` is absent.
- Driver ids: `groupwaitfactor` replaces `pairwaitfactor` in place; `group_size` has no driver id.
- `convert` clamps:
  - `group_size` 0, -5, 11, 99 and `"7"` give 1, 1, 10, 10 and 7;
  - `number_wait_factor` 150 gives 100;
  - `global_wait_factor` `"57"` still gives 50.
- `number_mode` normalisation:
  - `"pair"`, `"roman"`, `""` and `None` read and update to `"value"`;
  - `"value"`, `"number"` and `"group"` are kept;
  - a stored `"pair"` in a profile reads as `"value"`.
- `scaled_group_wait`: 20 → 100 ms, 200 → 500 ms, independent of the global factor.
- `effective(False)` outside scope "all" zeroes `group_wait_factor` and keeps `group_size`.
- `NUMBER_MODES` equals the keys of `_get_availableNummods` and the Speech Pipeline panel's `number_mode_value`.

**Driver** (`tests/test_worldvoice_pipeline_settings.py`, `tests/test_lint_rewrites.py`):
- `allSupportedSettings` ids, with `groupwaitfactor` where `pairwaitfactor` was.
- `synth.nummod = "group"` stores `"group"`; `synth.nummod = "pair"` stores `"value"`.
- `availableNummods` is `value`, `number`, `group`, in that order.
- No `groupsize` descriptor exists.

**Pipeline** (`tests/test_pipeline_filters.py`, `tests/test_pipeline_stages.py`, `tests/test_pipeline_passthrough.py`):
- Group mode, every row of tables 5.1–5.3 for n = 1, 2, 3 and 10:
  - `"12345"`, n = 3 → `["123", GB, "45"]` (G1);
  - a number of exactly n digits is unchanged;
  - decimals are unchanged;
  - `"+12345"`, n = 3 → `["+123", GB, "45"]`.
- The group separator is one instance per number and has the group wait at pause 0 and 50.
- Digit mode:
  - `"12"` → `["1", NB(w), "2"]` for w = 0 and w = 40;
  - `"12.5"` → `["1", NB, "2.5"]`;
  - `"-1234"` → `["-1", NB, "2", NB, "3", NB, "4"]`;
  - `[marker, "a 12", marker]` → `[marker, "a 1", NB(0), "2", marker]`;
  - with a digit table, `"11"` → `["一", NB, "一"]` (replaces `test_translated_digits_are_not_split`).
- Digit mode, then `number_wait_factor` with w = 40: `"12"` → `["1", NB(40), "2"]`, with no second break.
- Group mode n = 2, then `number_wait_factor` with w = 40: `"1234 5678"` → `["12", GB(0), "34", NB(40), "56", GB(0), "78"]`.
- `number_wait_factor` inserts `NumberBreakCommand` instances. All number-wait breaks of one call are one instance; keep the identity checks.
- A `GroupNumberBreakCommand` suppresses the boundary punctuation pause (renamed `test_a_group_number_break_counts_as_an_existing_pause_for_punctuation`).
- A stored `"pair"` mode, run through the settings service and `inject_number_mode`, gives value-mode output.
- The `ORDER` guard (`tests/pipeline_harness.py:125-135`) is unchanged.

**Speech Pipeline panel** (`tests/test_settings_panels.py`, `tests/test_pipeline_panels.py`):
- The label order in section 4.4.
- The spin control has min 1, max 10 and the stored value.
- Enable state for each stored mode (value, number, group, and an unknown stored `"pair"`):
  - only group enables the two controls;
  - an unknown mode selects value and disables them.
- Firing `EVT_CHOICE` after selecting group enables both; after selecting number, disables both.
- Disabled values are still saved.
- `onSave` writes `group_size` and `group_wait_factor`, and no `pair_wait_factor`.

**Voice panel** (`tests/test_voice_settings_panel.py`, `tests/test_pipeline_panels.py`):
- `SETTINGS` gains `DriverSetting("nummod")` and `NumericDriverSetting("groupwaitfactor")`. The test `Driver` gains `availableNummods` and `nummod`/`groupwaitfactor` values.
- The spin control:
  - sits right after the `nummod` sizer;
  - `tab_after is panel.nummodList`;
  - has the label "Group size:" and holds the stored size.
- The enable state follows the stored mode when the panel opens.
- Firing `EVT_CHOICE` on `nummodList`:
  - updates both controls;
  - still lets NVDA's handler write `driver.nummod` (the harness `Choice` must bind a writer the way NVDA does).
- After `updateDriverSettings(changedSetting="voice")` the state matches `driver.nummod`, including after a simulated ring change.
- A synth without `nummod` gets the spin control at the end, before the character edit, enabled.
- `onSave` writes `group_size`, and a later `onDiscard` keeps it. Discard without Save restores it.

**Harness changes these tests need:**
- `tests/ui_harness.py`:
  - a `SpinCtrl` fake (`min`, `max`, `initial`), registered in `fake_wx` (`:421-465`);
  - a `gui.nvdaControls` stub with `SelectOnFocusSpinCtrl` in `gui_stubs` (`:468-490`);
  - the fake `VoiceSettingsPanel._createNewControl` (`:333-355`) binds `EVT_CHOICE` to write the driver setting, like NVDA.
- `tests/pipeline_harness.py:110-122`: `punctuation_settings` gets `scaled_group_wait` (replacing `scaled_pair_wait`) and `group_size=3`.

### 9.2 Property tests (Hypothesis)

In `tests/test_pipeline_pause_properties.py` (profiles in `tests/conftest.py:17-21`).

- **G1, groups.** Input: an optional sign + 1–30 digits, size n in 1–10 and group pause p in 0–500. In group mode:
  - the output alternates `str` and `GroupNumberBreakCommand(p)`;
  - joining the strings gives back the input;
  - with the sign removed from the first string, every group has exactly n digits except the last, which has 1 to n;
  - the output has `ceil(len(digits) / n) - 1` breaks;
  - when `len(digits) <= n` the output is the input, unchanged.

  This replaces N6 (`test_property_pairs_are_separate_items_at_any_pause`, `:236-252`). A prototype passed G1 on 3,000 examples.
- **G2, decimals.** Any `[+-]?\d+\.\d+` is unchanged in group mode for every n.
- **D1, digits.** Input: an optional sign + 1–30 digits and w in 0–500. In digit mode:
  - the output alternates `str` and `NumberBreakCommand(w)`;
  - it has `len(digits) - 1` breaks;
  - the strings join back to the input.

  With a random digit→word table, each string is the translation of one digit, the first with the sign. This is the F5 fix.
- **X1, no stacked breaks.** Input: lists of text over `0123456789 a.,-`, any mode, size 1–10, number wait, group wait, item wait and punctuation wait in small ranges. After the chain `number_mode` → `chinesespace_wait_factor` → `item_wait_factor` → `punctuation_wait_factor` → `number_wait_factor`, no `NumberBreakCommand` or `GroupNumberBreakCommand` is adjacent to another `BreakCommand`. The prototype passed on 3,000 examples.

  Restrict the property to the new classes. Two *item* breaks around a blank item can already be adjacent on `master` (F7).
- **S1, settings.**
  - For any integer and any int spec, `convert` lies in `[min_value, max_value]` and is idempotent.
  - For any text, the `number_mode` normalisation returns a member of `NUMBER_MODES` and is idempotent.
- Keep N1–N5, N7, N8 and P1–P5, P4b unchanged.

### 9.3 Mutation testing (mutmut)

- Add `addon/synthDrivers/WorldVoice/pipeline/settings.py` to `[tool.mutmut] source_paths` (`pyproject.toml:38-45`). Decided by orchestrator with the recommended default; user may override before merge (Q9). `tests/mutation_support.py` names trampolines by file, so the alias-loaded settings module is matched.
- Run, with at most 3 workers and the memory guard (stop below 3 GB MemAvailable): `_translate_number`, `iter_number_speech_segments_mode`, `inject_number_mode`, `number_wait_factor`, `PipelineSettingSpec.convert`, `PipelineSettingSpec.confspec`, the `number_mode` normaliser and `PipelineSettings.scaled_group_wait`. The plan confirms the exact mutant names with `mutmut results`.
- Record each surviving mutant with its reason. As in phase 29, confirm each one by running the suite with that mutant applied.

### 9.4 Translator comments

`tests/test_translator_comments.py` must pass with the new comments (section 4.7). Add a check that every `_()` call whose msgid is `"group"`, `"Group size:"`, `"group wait factor:"` or `"Group wait factor"` has a `# Translators:` comment. Today the test only checks that existing comments are well placed.

### 9.5 Windows / NVDA manual items

Linux tests reach only the controlled native and audio boundaries. These items need Windows with NVDA and a packaged test build:

1. **Group mode, sizes 1, 2, 3 and 10**, group wait 0 and 50. Read `"12345678"`, `"-1234567"`, `"12.5"` and `"0912345678"`. Each group is read as a number; at wait 0 there is only the handoff gap.
2. **Digit mode**, number wait 0 and 40.
   - `"12345"` has a break between every digit. At 0 listen for the per-digit segment split.
   - With `unicode.dic` mapping digits to Chinese words and number language zh, `"123"` is read digit by digit with breaks.
3. **Upgrade.** A profile with `number_mode = pair` and `pair_wait_factor = 40`:
   - both panels and the ring show "value";
   - numbers are read as values;
   - the ring's Number Mode entry can be changed without an error;
   - `nvda.ini` still holds the stale keys, and nothing is logged.
4. **Speech Pipeline panel.**
   - Tab order as in section 5.7.
   - NVDA reads "Group size: spin button 3" (exact wording to be recorded).
   - Both group controls are skipped by Tab and reported unavailable in object navigation unless the mode is group.
   - Arrowing through the mode choice updates the state at once.
   - Values survive Save and reopen.
5. **Voice panel (WorldVoice).**
   - The spin control sits after Number Mode in both Tab order and layout.
   - NVDA reads its label: the control is moved in tab order, as the punctuation edit is (`VoiceSettingsDialogs.py:79-81`), and the label association has not been checked on Windows.
   - Disabled state on open and on changing the mode.
   - Change the mode with the ring while the dialog is open, then change the voice: the state follows the mode.
   - Save, then Cancel, keeps the size; Cancel without Save restores it.
6. **Scope "all"** with eSpeak NG, OneCore and SAPI5:
   - digit mode at number wait 0: `"12345"` must not be read as one number (F2);
   - group mode at group wait 0: the groups must not merge.

## 10. Existing tests and documents that need new expectations

A scratch prototype of sections 4.1–4.5 (without strings and docs) was run against the full suite (single process, memory guard; baseline 1830 passed, 0 skipped). Exactly 59 test IDs in these 29 test functions failed, and nothing else:

| Test | Why | New expectation |
| --- | --- | --- |
| `test_lint_rewrites.py::test_number_modes_are_a_plain_dict_in_order` (`:41-48`) | `pair` entry | `("group", "group", "group")` |
| `test_pipeline_filters.py::test_number_wait_factor_drops_blanks_then_breaks_between_numbers` (`:78-88`) | break type name | `("NumberBreakCommand", 40)` |
| `test_pipeline_filters.py::test_number_wait_breaks_only_between_whole_numbers` (2 of 5 ids, `:91-104`) | break type name | `("NumberBreakCommand", 40)` |
| `test_pipeline_filters.py::test_number_wait_splits_numbers_separated_only_by_whitespace` (13 of 24 ids; `B40`, `:108`) | break type name | `B40 = ("NumberBreakCommand", 40)` |
| `test_pipeline_filters.py::test_the_shortest_number_wait_still_breaks` (`:145-151`) | break type name | `("NumberBreakCommand", 1)` |
| `test_pipeline_filters.py::test_number_wait_splits_across_items_and_keeps_commands` (`:154-162`) | break type name | `B40` as above; the `BreakCommand(5)` marker stays |
| `test_pipeline_filters.py::test_digit_mode_then_number_wait_pauses_between_digits` (`:165-173`) | break type name | `["1", ("NumberBreakCommand", 40), "2"]` |
| `test_pipeline_filters.py::test_translated_digits_are_not_split` (`:176-187`) | U1 fixes F5 | rename (e.g. `test_translated_digits_are_split_by_the_number_wait`); `["一", NB(40), "一"]` |
| `test_pipeline_filters.py::test_pair_mode_then_number_wait_breaks_between_numbers_only` (`:190-202`) | rename | group mode, `group_size=2`, `GroupNumberBreakCommand` |
| `test_pipeline_filters.py::test_number_mode` (12 ids; `NUMBER_MODES`, `:207-225`) | pair → group; digit separators | `("group", n)` rows; number rows `"12.5"` → `["1", NB(0), "2.5"]`, `"-1234"` → `["-1", NB(0), "2", NB(0), "3", NB(0), "4"]`, `"123"`, `"12"` likewise; parametrise sizes |
| `test_pipeline_panels.py::test_pipeline_panel_saves_once_through_the_service` (`:33-77`) | rename, new control | `number_mode_value` with `"group"`; `_group_wait_factor_slider`, `_group_size_spin`; `group_wait_factor`, `group_size` in the update |
| `test_pipeline_panels.py::test_voice_panel_discard_after_apply_keeps_applied_pipeline_values` (`:115-149`) | `onSave` reads the spin control | set `panel.groupSizeSpin`; add `group_size` to the state |
| `test_pipeline_passthrough.py::test_number_wait_drops_blank_text_but_not_commands` (`:71-76`) | break type name | `("NumberBreakCommand", 40)` |
| `test_pipeline_passthrough.py::test_number_mode_passes_commands_and_merges_text_around_them` (`:138-142`) | U1 | `[marker, "a 1", NB(0), "2", marker]` |
| `test_pipeline_passthrough.py::test_a_pair_number_break_counts_as_an_existing_pause_for_punctuation` (`:180-188`) | rename | `GroupNumberBreakCommand`; rename the test |
| `test_pipeline_pause_properties.py::test_property_pairs_are_separate_items_at_any_pause` (`:236-252`) | rename | replaced by G1 (section 9.2) |
| `test_pipeline_settings_service.py::test_table_drives_fields_defaults_keys_and_confspec` (`:25-50`) | keys, ids | `OLD_DEFAULTS` (`:8-22`) with `group_wait_factor` and `group_size`; `groupwaitfactor` in the id list; confspec asserts for the new keys |
| `test_pipeline_settings_service.py::test_get_reads_defaults_and_current_profile` (`:53-63`) | `OLD_DEFAULTS` | as above |
| `test_pipeline_settings_service.py::test_effective_matches_the_old_synth_scoping` (`:121-179`) | field rename | `group_wait_factor` |
| `test_pipeline_settings_service.py::test_scaled_waits_follow_their_units_and_caps` (9 ids, `:182-201`) | `OLD_DEFAULTS`; helper rename | `scaled_group_wait`, `group_wait_factor` |
| `test_pipeline_stages.py::test_number_mode_reads_symbols_from_context` (`:125-137`) | U1 | `["一", NB(w), "一"]` and `["1", NB(w), "1"]` |
| `test_settings_panels.py::test_pipeline_panel_shows_the_stored_settings` (`:30-77`) | new order, rename | label list of section 4.4; `number_mode="group"`, `group_wait_factor`, `group_size` |
| `test_settings_panels.py::test_pipeline_panel_saves_the_edited_controls_to_config` (`:137-157`) | rename | `_group_wait_factor_slider`, `group_wait_factor`; add `group_size` |
| `test_voice_settings_panel.py::test_punctuation_characters_follow_the_wait_factor_slider` (`:184-195`) | the spin control lands last when `SETTINGS` has no `nummod` | passes again once `SETTINGS` gains `nummod`; assert the spin control's place too |
| `test_voice_settings_panel.py::test_a_synth_without_pause_settings_gets_the_characters_edit_at_the_end` (`:254-270`) | new control at the end | order `[voice, rate, Automatic language switching…, "Group size:", "Punctuation pause characters:"]`; rename |
| `test_worldvoice_pipeline_settings.py::test_settings_lists_keep_their_order_and_store_pipeline_values_outside_speech_config` (`EXPECTED_IDS`, `:20-41`) | driver id | `groupwaitfactor` |
| `test_worldvoice_pipeline_settings.py::test_descriptors_read_and_write_through_the_service` (`:64-79`) | `"pair"` now normalises | use `"group"`; add a `"pair"` → `"value"` case |

Also expected to change once `SETTINGS` gains `nummod` and `groupwaitfactor` (they passed in the prototype only because the test driver had neither): `test_voice_settings_panel.py::test_every_setting_gets_a_control_in_standard_order_and_unsupported_ones_are_hidden` (`:102-125`, the `sizerDict` and shown lists) and the `ALL` set (`:65-74`).

Still pass unchanged and should stay:
- `test_settings_panels.py::test_pipeline_panel_selects_the_first_choice_for_an_unknown_stored_value` (`:79-83`). It now passes through the normaliser instead of the `ValueError` path.
- `test_pipeline_stages.py::test_zero_number_wait_keeps_spaces` and `test_positive_number_wait_breaks_between_numbers` (`:107-122`).
- The number-split properties N1–N8. They test `isinstance(…, BreakCommand)`, which a `NumberBreakCommand` satisfies.

Documents:
- `addon/locale/zh_TW/LC_MESSAGES/nvda.po`: section 4.7.
- `readme.md:44-46` and `addon/doc/zh_TW/readme.md:44-46`: add a group-mode bullet. Decided by orchestrator with the recommended default; user may override before merge (Q8). For example:
  - EN: "Group mode: Reads the digits of a number in groups counted from the left. The group size (1–10, default 3) and the pause between groups are set in the Speech Pipeline panel or the Voice settings panel. For example, with size 3, "12345" is read as "123", "45"."
  - zh_TW: "群組模式：從左邊開始，把數字每幾位分成一組朗讀。每組位數（1～10，預設 3）和群組停頓，可以在語音流程面板或語音設定面板調整。例如每組 3 位時，「12345」會讀成「123」、「45」。"

  Other readmes are left to translators.
- Earlier specs and plans that mention pair mode are not edited (non-goal).

## 11. Findings needing the user

**F1. "Clamped or validated on read": NVDA validates on read, but an invalid stored value raises.** This affects the G5 wording "the stored value is clamped or validated on read".

- With `min=1,max=10` in the confspec, NVDA checks a stored `group_size` every time it is read (`config/__init__.py:1269-1274`). A hand-edited `group_size = 0`, `11` or `abc` raises a configobj validation error out of `section.get`. `_get_value` does not catch it (`settings.py:242-249`).
- The error then surfaces in three places:
  - WorldVoice's start-up `pipeline_settings.get()` (`WorldVoice/__init__.py:248`): the synth fails to load (`:185-190`) and NVDA falls back to another synth;
  - every stage handler (`pipeline/__init__.py:759-762`): NVDA logs the error and skips the stage;
  - the Speech Pipeline panel (`speechSettingsDialog.py:118`): the panel fails to open.
- This already applies to every existing int key, for example a hand-edited `number_wait_factor = 150`. The new key only has a narrower range.
- The clamp in `convert` (section 4.3) protects WorldVoice's own writes and stub configs. It cannot help here, because the raise happens before `convert`.

Options:

- **A. Keep NVDA's validation as the "validated on read" step; clamp in `convert`; no fallback.** No change to today's behaviour for invalid stored values. Recommended for this feature; adopted as Decided by orchestrator with the recommended default; user may override before merge (Q4).
- **B. Fall back per key.**
  - `ConfigPipelineRepository.load` catches `configobj.validate.ValidateError` for each key, logs one warning and uses the spec default.
  - It fixes the failure for all pipeline keys.
  - It needs a `configobj.validate` stub in every test loader of `pipeline/settings.py`. configobj is not installed in the test environment, and NVDA ships it (`config/__init__.py:28`).

**F2. With scope "all", digit mode no longer puts a space between digits.** This affects U1 for synthesizers other than WorldVoice.

- Before: `"12"` became `"1 2"`, which every synth reads as two digits.
- After: `"1"`, `NumberBreakCommand(w)`, `"2"`, where w is the number wait and may be 0. NVDA's eSpeak, SAPI5 and OneCore drivers turn the break into markup (`ref/nvda/source/synthDrivers/espeak.py:204-205`, `sapi5.py:928-929`, `ref/nvda/source/speechXml.py:307-308`). Whether a 0 ms break separates two digits for each engine has not been verified.
- A third-party synth that ignores `BreakCommand` and joins its text items would read `"12"` as twelve. Digit mode exists to avoid exactly that.
- WorldVoice itself is safe, because every break splits the segment.
- This is the previous spec's F2 (`2026-10-21-feat-number-and-punctuation-pause-design.md:492-498`), now applied to digit mode as well as to pairs.
- Recommendation: keep U1 as decided and run manual item 6. If a built-in synth merges the digits, a follow-up could keep a space after each digit break for non-WorldVoice contexts only (`ctx.supports_roles` False). That would change U1's output, so it is the user's call.

**F3 (for information). The pause between translated CJK digits now follows the number wait, not the Chinese-space wait.**

- On `master`, translated digits `"一 二 三"` got Chinese-space breaks, because `_CH_SPACE_RE` matches `一`–`九` (`pipeline/__init__.py:34`; `〇` U+3007 is outside the range).
- After U1 they get `NumberBreakCommand(number wait)`. With the defaults both are 10 ms (`settings.py:95-102`, `:127-134`).
- Users who set the number wait to 0 now get a per-digit segment split in digit mode, translated or not. Default users hear no change for ASCII digits: at 10 ms the number split already broke `"1 2"` apart.

**F4 (for information). U3 also prevents two failures for a stored "pair"** (section 8): digit-mode reading through the fall-through branch, and a `TypeError` in the ring. This supports the decision.

**F5 (for information). No other language loses a translation.** Only zh_TW has the pair strings (section 3.6), so the accepted loss in G6 affects no catalog.

**F6 (for information). A ring change does not refresh an open Voice panel.**
- NVDA only refreshes driver controls after a voice change (`settingsDialogs.py:1341-1350`). The group controls' state therefore follows a ring change only at the next voice change or panel rebuild.
- This matches the punctuation switch (`tests/test_voice_settings_panel.py:241-251`). "After a ring change" in G4 is implemented as "after a voice change that follows a ring change".

**F7 (for information; out of scope).** The property run found an existing `master` behaviour. With item wait and number wait both > 0, `["0", " ", "0"]` gives `"0"`, B(item), B(item), `"0"`: the item stage puts a break on both sides of the blank item, and `_remove_space` then drops it. This feature does not change it.

## 12. Open questions

All are new and adopted with the conservative default. Each is Decided by orchestrator with the recommended default; user may override before merge.

1. **Q1. Voice panel placement:** right after Number Mode (section 4.5), not after the group wait slider.
2. **Q2. Spin control class:** `nvdaControls.SelectOnFocusSpinCtrl`, a `wx.SpinCtrl` subclass, as NVDA's own Voice panel uses.
3. **Q3. Generic clamp:** `convert` clamps every int spec to its bounds; existing keys keep 0–100 and their confspec strings.
4. **Q4. F1:** option A, no fallback for invalid stored values.
5. **Q5. Driver label translation:** "Group wait factor" → 群組停頓參數 (no colon, like the existing 兩位一組停頓參數).
6. **Q6. Another synthesizer in the Voice panel:** the spin control is shown at the end before the character edit, enabled, and saved, as the character edit is.
7. **Q7. Table position:** `group_size` is appended after `punctuation_pause_characters` (non-driver keys last).
8. **Q8. Readme:** add a group-mode bullet to `readme.md` and `addon/doc/zh_TW/readme.md`; no changelog change.
9. **Q9. mutmut:** add `pipeline/settings.py` to `source_paths`.
10. **Q10. Names:** driver id `groupwaitfactor`, constant `GROUP_WAIT_UNIT_MS`, helper `scaled_group_wait`, `NUMBER_MODES`, control attributes `_group_size_spin` (Speech Pipeline panel) and `groupSizeSpin` (Voice panel).
11. **Q11. F2:** keep U1 for every synthesizer; decide on a mitigation only after manual item 6.

## 13. Flow classification and size

The normal flow is enough. None of the complex-flow criteria (`DEVELOPMENT_WORKFLOW.md` section 4.0) apply:

- the plan and the implementation are done by the same agent;
- no file must be byte-exact (no inner driver, packaging or build change);
- the rename touches about 10 source and test files, and each change is behavioural and covered by tests. It is not a mechanical move that needs tree-id proof.

**Estimated plan size: 12 tasks**, so per section 3.2 the implementer works in three batches of 4 (4 / 4 / 4), with an Opus batch review after batches 1 and 2 and the final Fable review after batch 3. Suggested tasks:

1. `PipelineSettingSpec` bounds, clamp and confspec (Q3).
2. `number_mode` normalisation and `NUMBER_MODES` (U3).
3. Rename `pair_wait_factor` → `group_wait_factor`, with driver id, label, unit and helper; add the `group_size` key.
4. Group mode in `_translate_number` and `GroupNumberBreakCommand` (G1–G3, G7).
5. `NumberBreakCommand` in `number_wait_factor` (U2).
6. Digit mode `NumberBreakCommand` (U1).
7. `availableNummods` and the driver tests.
8. Speech Pipeline panel: rename, order, spin control and enable rule; `ui_harness` `SpinCtrl` and `nvdaControls`.
9. Voice panel: spin control placement, enable rule at the three points, and save.
10. Strings: translator comments, zh_TW `nvda.po`, `msgfmt --check`, `scons pot`.
11. Hypothesis properties G1, G2, D1, X1, S1, and the mutmut run.
12. Readme bullets and full verification (section 7 of the workflow).

## 14. Mutation results

Linux, mutmut 3.8.0, on `8642cbf` (after the deferred-minor fixes): `mutmut run --max-children 3` with the globs below, under a scratchpad guard that kills the run if MemAvailable < 3 GB. The guard never fired.

```
addon.synthDrivers.WorldVoice.pipeline.x__translate_number*
addon.synthDrivers.WorldVoice.pipeline.x_iter_number_speech_segments_mode*
addon.synthDrivers.WorldVoice.pipeline.x_inject_number_mode*
addon.synthDrivers.WorldVoice.pipeline.x_number_wait_factor*
addon.synthDrivers.WorldVoice.pipeline.settings.*convert*
addon.synthDrivers.WorldVoice.pipeline.settings.*confspec*
addon.synthDrivers.WorldVoice.pipeline.settings.x__number_mode*
addon.synthDrivers.WorldVoice.pipeline.settings.*scaled_group_wait*
```

**146 mutants: 141 killed, 5 survived.**

| Function | Mutants | Killed | Survived |
| --- | --- | --- | --- |
| `_translate_number` | 46 | 44 | 2 |
| `iter_number_speech_segments_mode` | 37 | 34 | 3 |
| `inject_number_mode` | 27 | 27 | 0 |
| `number_wait_factor` | 12 | 12 | 0 |
| `PipelineSettingSpec.convert` | 15 | 15 | 0 |
| `_number_mode` | 7 | 7 | 0 |
| `PipelineSettings.scaled_group_wait` | 5 | 5 | 0 |
| `PipelineSettingSpec.confspec` | 0 | — | — |

`confspec` is a property; mutmut 3.8.0 does not mutate decorated functions. Its strings are pinned by `test_int_confspec_carries_the_spec_bounds`, `test_group_settings_replace_the_pair_wait_and_add_the_size` and `test_pipeline_defaults_match_the_confspec_the_add_on_registers`.

Each survivor was confirmed by running the whole suite in `mutants/` with `MUTANT_UNDER_TEST=<name>` (hygiene guards excluded, as in `[tool.mutmut]`): 1917 passed every time. The numbers are this run's names only; the Change column identifies each mutant.

| Mutant | Change | Why it survives |
| --- | --- | --- |
| `_translate_number` 15 | `digits[0] in "+-"` → `digits[0] in "XX+-XX"` | Equivalent: `digits[0]` is one character of a `_NUMBER_RE` match, so it is a sign or a digit and never `X`. |
| `_translate_number` 41 | `previous_was_digit = False` → `None` | Equivalent: the value is only used as a truth value, and `None` is false. |
| `iter_number_speech_segments_mode` 1 | `previous_was_number = False` → `None` | Equivalent, as above. |
| `iter_number_speech_segments_mode` 4 | initial `preceding_text = ""` → `"XXXX"` | Equivalent: `preceding_text` is only read through `.endswith(".")`, which is false for both. |
| `iter_number_speech_segments_mode` 37 | `preceding_text = ""` after a number → `"XXXX"` | Equivalent, as above. |

Earlier survivors closed by tests on this branch: the group branch applying the digit table (`test_group_mode_does_not_translate_digits`, batch 1 review M1), the decimal branch applying it (B2-M5), a group wait scaled by the global factor (M2), and a write of an unchanged number mode (M3).
