# Voice panel: create WorldVoice's controls in table order

Date: 2026-10-22.
Base: `master` `c6a71e4`. Branch: `feat/voice-panel-creation-order`. Flow: normal, lightweight (short spec, plan under 10 tasks, one final Fable review).
NVDA reference: `ref/nvda` `7d25bc76e`. Line numbers below are for `master` `c6a71e4`, and for NVDA at that commit.

## 1. Problem and goal

In NVDA's Voice panel, WorldVoice adds two controls that are not driver settings: "Group size" (spin) and "Punctuation pause characters" (edit). `makeSettings` creates them last, after NVDA's own controls (`addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py:36-42`, `_addPipelineControls` `:104-148`). It then moves them in two ways:

- in the layout, with `_moveSizer` (Detach/Insert, `:26-32`, `:145-147`);
- in the Tab order, with `control.MoveAfterInTabOrder(anchor)` (`:148`). This moves only the control. Its label `StaticText` stays where it was created.

NVDA's object navigation (NVDA+numpad 4/6) follows the window creation order, which is the HWND sibling order. `MoveAfterInTabOrder` does not change that order (the user observes both controls at the end of the panel). So a user who navigates by object hears both controls after NVDA's own controls, and hears each label far from its control.

Goal: each WorldVoice non-driver control is created at its table position. Creation order then equals layout, Tab and object-navigation order, and each label sits directly before its control. Nothing else the user sees or hears changes.

Non-goals: the Speech Pipeline panel; the table; strings; the settings ring; save, discard and the enable rules.

## 2. Decisions

| # | Decision | Status |
| --- | --- | --- |
| D1 | Create each non-driver control at its table position: right after the row of the nearest earlier Voice-panel entry that has a row, including chains of non-driver controls. Remove `MoveAfterInTabOrder` for these controls. | Decided by the user (2026-10-22) |
| D2 | Replace the copied `createDriverSettings` (`VoiceSettingsDialogs.py:196-237`, a copy of NVDA's `AutoSettingsMixin.updateDriverSettings`, `ref/nvda/source/gui/settingsDialogs.py:1546-1575`) with an `updateDriverSettings` override. The override runs a creation pre-pass, then `super().updateDriverSettings(changedSetting)`. | Decided by the user (2026-10-22) |
| D3 | Keep N5 (another synth gets no non-driver control and saves none), the I1 rule (a destroyed control counts as absent after `refreshGui`), the `depends_on` enable rules, and `onSave`/`onDiscard`. | Decided by the user (2026-10-22) |
| D4 | Guards: remove the AST-equality guard for the copy. Add sha256 fingerprints for the NVDA internals the new code relies on, and keep the `_updateValueForControl` fingerprint. | Decided by the user (2026-10-22) |
| D5 | The layout keeps one layout-only move (section 4.3). | Decided by the implementer, as the user allowed |

## 3. NVDA internals relied on

- **`SettingsPanel._buildGui`** (`settingsDialogs.py:403-406`) calls `makeSettings(self.settingsSizer)` once the panel is constructed.
- **`VoiceSettingsPanel.makeSettings`** (`:1686-1688`) first calls `self.updateDriverSettings()`, then adds NVDA's own controls with a `BoxSizerHelper` (`:1690` onwards). An override of `updateDriverSettings` therefore runs before NVDA's own controls exist.
- **`AutoSettingsMixin.updateDriverSettings`** (`:1546-1575`) does three things:
  - hides every `sizerDict` row whose setting is unsupported, except `changedSetting` (`:1553-1558`);
  - for each setting in `supportedSettings`, except `changedSetting`, calls `_updateValueForControl` if the row exists, or `_createNewControl` if the row is missing and the setting is not private (`:1564-1573`);
  - lays out the sizer (`:1575`).
- **`_createNewControl`** (`:1577-1591`) makes the control with the maker for the setting's kind. It stores the row in `sizerDict[setting.id]` and inserts it at `len(self.sizerDict) - 1`. That index counts only driver rows. An `UnsupportedConfigParameterError` is logged and leaves no row.
- **`lastControl`** (`:1382`). Each maker does `if self.lastControl: <control>.MoveAfterInTabOrder(self.lastControl)` and then `self.lastControl = <control>` (`:1457-1459`, `:1512-1514`, `:1541-1543`). A slider or a choice is made by `LabeledControlHelper`, which creates the `StaticText` label, then the control, and puts both in one row sizer (`ref/nvda/source/gui/guiHelper.py:288-291`). A checkbox is a single window.
- **A voice change.** `StringDriverSettingChanger` calls `container.updateDriverSettings(changedSetting="voice")` (`settingsDialogs.py:1343-1350`). On the patched panel, `container` is WorldVoice's panel, so the override runs.
- **`refreshGui`** (`:1633-1646`) runs when the settings instance changed (a synth change). It clears `sizerDict`, runs `settingsSizer.Clear(delete_windows=True)`, and then `makeSettings` again on the same panel. `lastControl` is left naming a destroyed window. A destroyed wx window is falsy, so the makers' `if self.lastControl:` skips it.
- **`_updateValueForControl`** (`:1601-1619`). WorldVoice overrides it to reload the string options (`VoiceSettingsDialogs.py:239-275`). That override is unchanged.

## 4. Design

All changes are in `addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py`, plus one pure helper in `addon/synthDrivers/WorldVoice/pipeline/panelLayout.py`.

### 4.1 `makeSettings`

`makeSettings` sets `_pipelineSnapshot` as today. It then calls `super().makeSettings(settingsSizer)`, followed by `_bindControllers()` and `_applyDependencies()`. It no longer calls `createDriverSettings` or `_addPipelineControls`: NVDA's `makeSettings` calls the override first (section 3).

### 4.2 `updateDriverSettings(changedSetting=None)` override

1. **Pre-pass.** The settings are `allSupportedSettings` when the instance has it, otherwise `supportedSettings`.
   - First, every non-driver attribute whose control is absent (`_voiceControl` is `None`) is set to `None`. This keeps I1: a destroyed control is never named. A live control is kept.
   - The non-driver controls to make are those that are absent, and only when `_isWorldVoice()` is true (N5).
   - For each setting, in order:
     - unless it is `changedSetting`, already in `sizerDict`, or private, call `self._createNewControl(setting, settingsStorage)`;
     - then make the non-driver controls that `creation_followers` lists after this setting's id.
   - After the loop, make those listed under `None`.
   - Each non-driver control is made with its own `BoxSizerHelper` (no spacer, as today) and sets `self.lastControl` to itself. The next driver control's `MoveAfterInTabOrder(self.lastControl)` then keeps the Tab order equal to the creation order. No `MoveAfterInTabOrder` is called on WorldVoice's controls.
2. **Layout pass** (section 4.3), for the non-driver controls made in this call only.
3. `super().updateDriverSettings(changedSetting)` hides the unsupported rows and updates the values. NVDA creates nothing more here, because the pre-pass already listed every supported setting.

On a voice switch, every row exists already. The pre-pass then makes nothing, and NVDA shows RateBoost/Inflection in place, as the copy did.

**New pure helper.** `creation_followers(specs, listed) -> dict[str | None, tuple[str, ...]]` in `panelLayout.py`:

- `specs` are the Voice-panel entries in table order.
- `listed(driver_id)` says whether the panel makes a row for that driver setting: the id is in the settings list and is not private.
- The result maps a driver id to the keys of the non-driver entries made right after it, in table order. Key `None` holds the entries with no listed driver entry before them.
- A run of non-driver entries follows the listed driver entry before the run, so chains keep table order.

### 4.3 Layout placement: a layout-only move stays

NVDA inserts each driver row at `len(self.sizerDict) - 1` (`settingsDialogs.py:1585-1590`), an index that counts driver rows only. If a non-driver row were inserted at its table position, every later driver row would land one slot too early.

Computing a "right" index for our row cannot prevent this. Only overriding `_createNewControl` could, and that would mean copying NVDA code again, which D2 removes. So the non-driver row is appended where `BoxSizerHelper` puts it: at the end of the sizer, after the driver rows made so far, because NVDA's own controls do not exist yet (section 3). Each later driver row is then inserted before it.

After the pre-pass, each row made in this call is moved after its anchor row with the existing `_moveSizer`/`_rowIndex`/`voice_placements` code. This move is layout-only. It changes no window order and no Tab order.

### 4.4 Removed

- `createDriverSettings`.
- `_addPipelineControls`. Its parts become `_makePipelineControl` and `_placePipelineRows`.
- The `MoveAfterInTabOrder` call.

## 5. Guards (`tests/test_nvda_settings_copy.py`)

- Remove `test_create_driver_settings_is_nvdas_update_driver_settings_over_all_settings` and its AST helpers.
- Fingerprints (sha256 of `ast.unparse` of the method, as for `_updateValueForControl`), each with a comment saying what to review when it fails:
  - `AutoSettingsMixin._createNewControl`: the insertion index the layout pass corrects, and that a failed maker leaves no row;
  - `AutoSettingsMixin.updateDriverSettings`: that it still creates nothing the pre-pass listed, hides unsupported rows and updates values;
  - `AutoSettingsMixin.refreshGui`: that it still destroys every window, keeps `lastControl` and calls `makeSettings` (I1);
  - `AutoSettingsMixin._updateValueForControl`: kept.
- Structural checks:
  - each of `_makeSliderSettingControl`, `_makeStringSettingControl` and `_makeBooleanSettingControl` contains `if self.lastControl: <c>.MoveAfterInTabOrder(self.lastControl)` followed by `self.lastControl = <c>`;
  - the first statement of `VoiceSettingsPanel.makeSettings` is `self.updateDriverSettings()`;
  - `StringDriverSettingChanger.__call__` calls `self.container.updateDriverSettings(changedSetting=self.setting.id)`.

## 6. Test fakes (`tests/ui_harness.py`)

- **Window order.** `SettingsPanel` keeps `children`: the windows in creation order, standing in for the HWND sibling order. Every `Control` made with that parent appends itself. `Sizer.Clear(delete_windows=True)` destroys the windows and removes them from `children`.
- **Tab order.** `tab_order` stays a separate list. `MoveAfterInTabOrder` changes only `tab_order`, never `children`.
- **Labels.** `BoxSizerHelper.addLabeledControl` creates a `Label` (a `StaticText`) before the control and puts both in the row sizer, as `LabeledControlHelper` does. The fake `_createNewControl` does the same for sliders and choices. `Sizer.controls()` and `contents()` leave labels out, so existing tests that count a row's controls are unchanged. Clearing still destroys the labels.
- **`lastControl`.** The fake makers already chain `lastControl` as NVDA does. They keep doing so.
- **Kept strict:** a destroyed control raises on any wx call and is falsy; a `SizerItem` dies on `Detach`.

New tests in `tests/test_settings_order.py` cover the real table with WorldVoice. They assert that the children order, the Tab order and the layout order of the Voice-panel entries all equal the table order, and that each label is the window directly before its control. They are run:

- on the first build;
- after a voice switch;
- after a WorldVoice → WorldVoice rebuild;
- after an other synth → WorldVoice rebuild.

The children-order test fails on `master`, where both controls come last.

## 7. Windows manual items (not verifiable on Linux)

1. With WorldVoice, open the Voice panel. Navigate by object (NVDA+numpad 4/6) through the WorldVoice rows. Expected: "Group size" comes right after "Number mode" and before "Group wait factor", and "Punctuation pause characters" comes right after "Punctuation wait factor". Each control is read with its own label, and the label object sits directly before it.
2. Tab and Shift+Tab through the same rows. Expected: the same order as item 1.
3. Pick a voice that supports RateBoost/Inflection after one that does not. Expected: the controls appear in place, after Rate and Pitch, and the order of items 1 and 2 still holds.
4. Switch synth from the Voice panel's "Change..." button: WorldVoice → eSpeak → WorldVoice, and WorldVoice → WorldVoice (OK with WorldVoice kept). Expected: items 1 and 2 hold after each rebuild into WorldVoice, and no error is logged.
5. With another synth, open the Voice panel. Expected: no Group size and no Punctuation pause characters control, and saving writes no pipeline setting.

## 8. Strings, config, engines

- No translation changes are expected: no `_()` string is added or changed.
- No config, confspec or migration change.
- No engine driver changes. `driver/<Engine>/driver/` is untouched, and drivers stay independently installable.
