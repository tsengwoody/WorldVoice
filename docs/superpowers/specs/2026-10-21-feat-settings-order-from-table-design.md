# Settings order and controls from the pipeline settings table

Date: 2026-10-21.
Base: `master` `658f8b9`. Branch: `feat/settings-order-from-table`. Worktree: `/workspace/WorldVoice-feat-order`.
Flow: normal flow (`DEVELOPMENT_WORKFLOW.md` section 3). Section 14 explains why the complex flow is not needed.
Status: the canonical order (Q1), the shared labels and their wording (Q2), `panel_scale` (Q3), `depends_on` (Q4) and the flow (Q5) were decided by the user on 2026-10-21 and are not reopened here. Section 12 lists facts found while writing this spec that the user should see before merge. Section 13 lists the new open questions, each adopted with a conservative default.

All `file:line` references are to `658f8b9`. NVDA references are to `ref/nvda` at `7d25bc76e`.

## 1. Problem

The order and the construction of the pipeline controls live in four places, and they disagree.

- **The table only orders the driver settings.** `PIPELINE_SETTINGS` (`addon/synthDrivers/WorldVoice/pipeline/settings.py:79-179`) says "Synth settings appear in the voice settings dialog in this order" (`:78`). The driver turns every entry with a `driver_id` into an NVDA driver setting in that order (`synthDrivers/WorldVoice/__init__.py:139-142`). The non-driver keys `scope`, `punctuation_pause_characters` and `group_size` are appended at the end (`settings.py:175-178`) and have no place in that order.
- **Number language is hard-coded.** `numlan` is appended right after `cni` inside the loop (`__init__.py:143-154`). Its label and ring name live there, not in the table.
- **Two Voice panel controls are placed by hand.**
  - The group size spin control is moved after the `nummod` row (`VoiceSettingsDialogs.py:93-122`).
  - The punctuation characters edit is moved after the `punctuationwaitfactor` row (`:124-146`).
  - Both use `_moveSizer` (`:14-20`) with a named anchor.
- **The Speech Pipeline panel builds every control by hand** (`globalPlugins/WorldVoice/speechSettingsDialog.py:116-268`), in its own order and with its own labels. Its order differs from the Voice panel's: global wait sits after group wait (`:172-191`).
- **The enable rules are written twice.**
  - Voice panel: `_bindNumberModeChoice`, `_applyGroupControlsState`, `_bindPunctuationPauseEnabledToggle`, `_applyPunctuationPauseControlsState` and the two special cases in `_updateValueForControl` (`VoiceSettingsDialogs.py:33-91`, `:230-232`, `:257-259`).
  - Speech Pipeline panel: `onNumberModeChange` and `onPunctuationPauseEnabledChange` (`speechSettingsDialog.py:160`, `:238-242`, `:267-288`).
- **The labels are written twice.** The Speech Pipeline panel has its own msgids ("global wait factor:", "sayall wait factor:", …), which differ in case and wording from the driver labels ("Global wait factor", "Say all wait factor", …) (section 3.6).

Adding one setting today means editing the table, the driver, both panels, both enable rules and both label sets, and keeping three orders in step by hand.

## 2. Goals and non-goals

Goals:

- One table, `PIPELINE_SETTINGS`, gives the order, the control kind, the label, the choices and the enable rule of every pipeline control (Q1, Q4).
- The NVDA Voice panel, the settings ring and the Speech Pipeline panel all follow the table order (Q1).
- Number language becomes an ordering-only table entry. Its value stays an NVDA driver setting stored by NVDA (section 5.3).
- The Voice panel places every non-driver control after the row of the previous table entry, with no named anchor (section 5.8).
- Both panels apply the enable rules generically from `depends_on` (Q4, section 5.9).
- One label per setting, shared by both panels, in sentence case (Q2, section 7).
- A guard test fails when a table entry lacks a field a panel needs (section 10.2).

Non-goals:

- No change to stored config keys or values, nor to the confspec strings (section 8).
- No change to `onSave` or discard/snapshot behaviour, except that a choice with no selection keeps its stored value in every case (section 5.10, N2), and that the Voice panel saves no pipeline setting for another synth (Changed by the user (2026-10-21, N5); section 5.10).
- No change to NVDA's own copy in `createDriverSettings` (`VoiceSettingsDialogs.py:177-218`), which `tests/test_nvda_settings_copy.py:60-81` pins to NVDA's `updateDriverSettings`.
- No refresh of an open Voice panel after a ring change. NVDA refreshes only after a voice change (`ref/nvda/source/gui/settingsDialogs.py:1343-1350`). This is unchanged from master (section 12, F6).
- No change to the pipeline log switch labels (`speechSettingsDialog.py:28-38`). See N1.
- No change to the Speech Pipeline panel's slider class (`wx.Slider`), to the uwv setting (`__init__.py:130-138`) or to NVDA's own Voice panel controls.
- No readme change. The readmes describe what each setting does, not where it sits (`readme.md:39-52`, `addon/doc/zh_TW/readme.md:35-51`). `buildVars.py` is not touched (the main checkout holds an uncommitted edit of it).
- No other-language catalog edits (`DEVELOPMENT_WORKFLOW.md` section 6). See N6.

## 3. Current behaviour (verified)

### 3.1 The table

- `PipelineSettingSpec` (`settings.py:46-75`) has `key`, `kind`, `default`, `driver_id`, `label`, `display_name`, `ring`, `min_step`, `normalize`, `min_value` and `max_value`.
- `PIPELINE_SETTINGS` order (`:79-179`): `ignore_comma_between_number`, `number_mode`, `global_wait_factor`, `number_wait_factor`, `group_wait_factor`, `item_wait_factor`, `sayall_wait_factor`, `chinesespace_wait_factor`, `punctuation_pause_enabled`, `remove_punctuation_characters`, `punctuation_wait_factor`, `scope`, `punctuation_pause_characters`, `group_size`.
- `PIPELINE_SETTING_BY_KEY`, `DEFAULT_PIPELINE_SETTINGS`, `PIPELINE_CONFIG_KEYS` and `PIPELINE_CONFSPEC` are built from every entry (`:181-184`).
- `ConfigPipelineRepository.load` builds `PipelineSettings` from every entry (`:278-282`). `PipelineSettingsService.update` rejects a key with no entry (`:303-310`).
- `NUMBER_MODES` is a separate tuple (`:38`), used by the `number_mode` normaliser (`:41-43`).
- Labels without a translator comment: `cni` (`:85`) and `remove_punctuation_characters` (`:164-165`).

### 3.2 Driver settings and the ring

- `_pipeline_driver_setting` (`__init__.py:103-119`) makes a `BooleanDriverSetting`, a `NumericDriverSetting` (with `minVal`, `maxVal`, `minStep`) or a string `DriverSetting`, always with `useConfig=False`.
- `_driver_settings` (`:121-155`) lists voice, variant, rate, rate boost, pitch, inflection, volume, uwv, then the table's driver entries. `numlan` follows `cni` (`:143-154`) and has `useConfig` left at its default `True` (`ref/nvda/source/autoSettingsUtils/driverSetting.py:47`). NVDA therefore stores it in `[speech][WorldVoice]` (`ref/nvda/source/autoSettingsUtils/autoSettings.py:156-163`, `:196-203`).
- `numlan`'s value is the driver's own `_numlan` (`__init__.py:183`, `:476-480`). Its options come from `_get_availableNumlans` (`:470-474`). The pipeline context receives it as `number_language` (`:371`).
- `_get_availableNummods` (`:482-488`) repeats the three modes and their labels, apart from `NUMBER_MODES`.
- `_PipelineSetting` descriptors are installed on the class for every entry with a `driver_id` (`:496-513`).
- When a setting has no `displayName`, NVDA strips `&` from the label (`driverSetting.py:62-64`).
- The ring lists `supportedSettings` in order, skipping `availableInSettingsRing=False` (`ref/nvda/source/synthSettingsRing.py:207-219`). It restores the current entry by id (`:201-212`, `:225-232`). The initial entry is `rate` (`ref/nvda/source/synthDriverHandler.py:417-428`).
- Master ring order: voice, variant, rate, rate boost (when supported), pitch, inflection (when supported), volume, uwv, numlan, nummod, globalwaitfactor, numberwaitfactor, groupwaitfactor, itemwaitfactor, sayallwaitfactor, chinesespacewaitfactor, punctuationpauseenabled, removepunctuationcharacters, punctuationwaitfactor. `cni` is not in the ring (`settings.py:86`).

### 3.3 NVDA's Voice panel machinery

- `makeSettings` runs `updateDriverSettings()` first, then adds NVDA's own controls (`settingsDialogs.py:1686-1718`).
- `updateDriverSettings` hides unsupported rows, then updates or creates each supported setting (`:1546-1575`). It never moves a row.
- `_createNewControl` inserts a new row at `len(self.sizerDict) - 1` (`:1577-1590`). The index counts driver rows only.
- Row and attribute shapes:
  - slider: `nvdaControls.EnhancedInputSlider` named `<id>Slider`, label `"<label>:"`, in its own sizer (`:1423-1460`);
  - choice: `wx.Choice` named `<id>List`, options in `_<id>s`, label `"<label>:"`, in its own sizer (`:1462-1515`);
  - checkbox: `wx.CheckBox` named `<id>Checkbox`, label without colon. The row in `sizerDict` is the checkbox window itself, not a sizer (`:1517-1544`).
- Each new driver control is moved after the previous one in tab order (`:1457-1459`, `:1512-1514`, `:1541-1543`).
- The choice writer `StringDriverSettingChanger` and the checkbox writer both call `evt.Skip()` first. Only a voice change calls `updateDriverSettings` (`:1333-1356`, `:1530-1534`).
- `onDiscard` unbinds `EVT_CHOICE` from every `<id>List`, then reloads the driver settings (`:1621-1628`).
- `refreshGui` clears every row and runs `makeSettings` again when the settings instance changes, for example after a synth change (`:1633-1646`).
- `BoxSizerHelper.addItem` adds a spacer before every item except the helper's first (`ref/nvda/source/gui/guiHelper.py:384`, `:412-415`).
- `LabeledControlHelper` enables, disables, shows and hides the label with its control (`guiHelper.py:227-233`).

### 3.4 WorldVoice's Voice panel (`VoiceSettingsDialogs.py`)

- `makeSettings` (`:24-31`) takes a pipeline snapshot for WorldVoice, creates every driver control up front (`createDriverSettings`, `:177-218`, over `allSupportedSettings`, `:201-205`), runs NVDA's `makeSettings`, adds the group size and the characters edit, then binds the two switches.
- Because every control exists up front, a later voice change only updates and shows rows. `_createNewControl` is never reached again for WorldVoice, so the moved rows never upset its index.
- With another synth (the patched class stays while WorldVoice is loaded, `__init__.py:207-211`), there is no `nummod` or `punctuationwaitfactor` row. Both added controls stay at the end, after NVDA's own controls, enabled, and are saved on Save (`tests/test_voice_settings_panel.py:336-355`, `:390-403`).
- Each added control uses a fresh `BoxSizerHelper` (`:98`, `:125`), so no spacer is left behind when its row moves.
- `_updateValueForControl` (`:220-259`) is WorldVoice's override. It reloads string options (`SetItems`, `:234-250`), so a value missing from the new list leaves no selection (-1). It applies the punctuation rule after the `punctuationpauseenabled` checkbox (`:230-232`) and the group rule after the `nummod` list (`:257-259`).
- Enable rules read the control, not the driver. WorldVoice's handler is bound after NVDA's writer, so it runs first and must `Skip()` (`:44-47`, `:75-78`). A selection outside the list (-1) is "not group" (`:54-57`).
- `onSave` writes the characters and the group size in one `update`, then runs NVDA's `onSave`, then retakes the snapshot (`:148-156`). `onDiscard` restores every stored key from the snapshot (`:161-175`).

### 3.5 The Speech Pipeline panel (`speechSettingsDialog.py:113-309`)

- One `BoxSizerHelper` for the whole panel (`:117`), so wx spacers separate the rows.
- Control order and attributes:

  | # | Label (msgid) | Control | Attribute |
  | --- | --- | --- | --- |
  | 1 | "Effect Scope:" | `wx.Choice` | `_scope_choice` (`:120-133`) |
  | 2 | "Ignore comma between number" | `wx.CheckBox` | `_ignore_comma_between_number_checkbox` (`:135-140`) |
  | 3 | "Number mode:" | `wx.Choice` | `_number_mode_choice` (`:142-160`) |
  | 4 | "Group size:" | `SelectOnFocusSpinCtrl` | `_group_size_spin` (`:162-170`) |
  | 5 | "group wait factor:" | `wx.Slider` 0..100 | `_group_wait_factor_slider` (`:172-181`) |
  | 6 | "global wait factor:" | `wx.Slider` 0..10, shown `// 10` | `_global_wait_factor_slider` (`:183-191`) |
  | 7–10 | "number wait factor:", "item wait factor:", "sayall wait factor:", "chinese space wait factor:" | `wx.Slider` 0..100 | `_<key>_slider` (`:193-231`) |
  | 11 | "Enable punctuation pause control" | `wx.CheckBox` | `_punctuation_pause_enabled_checkbox` (`:233-243`) |
  | 12 | "Remove configured punctuation at pause points" | `wx.CheckBox` | `_remove_punctuation_characters_checkbox` (`:245-250`) |
  | 13 | "punctuation wait factor:" | `wx.Slider` 0..100 | `_punctuation_wait_factor_slider` (`:252-260`) |
  | 14 | "Punctuation pause characters:" | `wx.TextCtrl` | `_punctuation_pause_characters_edit` (`:262-266`) |

- Every attribute is `_<key>_<suffix>`, with suffix `choice`, `checkbox`, `slider`, `spin` or `edit`.
- An unknown stored scope or mode selects the first choice (`:130-133`, `:156-159`).
- Enable rules: `self.Bind` on the panel for the mode choice (`:160`) and the switch (`:238-242`); both applied once at the end (`:267-268`); no selection counts as not group (`:270-281`).
- `onSave` writes every value in one `update` (`:290-309`). The global slider is saved `* 10` (`:298`). A mode choice with no selection keeps the stored mode (`:291-293`). A scope choice with no selection writes `_scope_value[-1]`, that is `"WorldVoice"` (`:295`).
- The scope and mode choice labels are local lists (`:120-124`, `:142-148`).

### 3.6 Labels today

| Setting | Driver label (Voice panel) | Ring name | Speech Pipeline panel |
| --- | --- | --- | --- |
| scope | — | — | "Effect Scope:" |
| cni | "Ignore comma between number" | — | "Ignore comma between number" |
| numlan | "Number &Language" (`__init__.py:148`) | "Number Language" (`:152`) | — |
| nummod | "Number &Mode" (`settings.py:94`) | "Number Mode" (`:96`) | "Number mode:" |
| group_size | — ("Group size:", `VoiceSettingsDialogs.py:102`) | — | "Group size:" |
| groupwaitfactor | "Group wait factor" | label | "group wait factor:" |
| globalwaitfactor | "Global wait factor" | label | "global wait factor:" |
| numberwaitfactor | "Number wait factor" | label | "number wait factor:" |
| itemwaitfactor | "item wait factor" (`settings.py:131`) | label | "item wait factor:" |
| sayallwaitfactor | "Say all wait factor" | label | "sayall wait factor:" |
| chinesespacewaitfactor | "Chinese space wait factor" | label | "chinese space wait factor:" |
| punctuationpauseenabled | "Enable punctuation pause control" | "Punctuation pauses" | same as driver |
| removepunctuationcharacters | "Remove configured punctuation at pause points" | "Remove punctuation at pause points" | same as driver |
| punctuationwaitfactor | "Punctuation wait factor" | label | "punctuation wait factor:" |
| punctuation_pause_characters | — ("Punctuation pause characters:", `VoiceSettingsDialogs.py:127`) | — | "Punctuation pause characters:" |

The pipeline log switches have their own labels (`speechSettingsDialog.py:28-38`). Four of their msgids are also label msgids: "Ignore comma between number" (`:30`), "Number language" (`:31`), "Number mode" (`:32`) and "item wait factor" (`:34`).

## 4. Decisions

| Id | Decision | Status |
| --- | --- | --- |
| Q1 | Canonical order: scope, global wait, ignore comma, number language, number mode, group size, group wait, number wait, item wait, say all wait, Chinese space wait, punctuation pause switch, remove punctuation, punctuation wait, punctuation characters. Scope appears only in the Speech Pipeline panel; number language only in the Voice panel and the ring. | Decided by the user (2026-10-21) |
| Q2 | One label per setting, shared by both panels; no separate `panel_label`. Sentence case: only the first letter of the first word is capitalised; proper nouns (Unicode, Chinese) keep their case; `&` accelerators stay where they are. The Speech Pipeline panel appends ":" to every non-checkbox label, as NVDA does (`settingsDialogs.py:1437`, `:1474`, `:1525`). The changed wordings are listed in section 7. | Decided by the user (2026-10-21) |
| Q3 | `panel_scale=10` on `global_wait_factor`: the Speech Pipeline panel shows 0..10 and saves `* 10`. The Voice panel is unchanged. | Decided by the user (2026-10-21) |
| Q4 | Enable rules are declared with `depends_on` and applied generically by both panels. No hard-coded rule remains. | Decided by the user (2026-10-21) |
| Q5 | Normal flow. | Decided by the user (2026-10-21) |

The spec keeps the parts these decisions touch in one place each, so a later change stays local:

- labels: the `label` and `display_name` fields, plus `panelLayout.label_text` (section 5.4);
- scale: the `panel_scale` field and `panelLayout.to_display` / `from_display`;
- enable rules: the `depends_on` field and `panelLayout.dependent_states`.

## 5. Design

### 5.1 New and changed table fields

`PipelineSettingSpec` (`settings.py:46-75`) gains these fields. Every new field has a default, so the positional `key, kind, default` form stays.

| Field | Type, default | Meaning |
| --- | --- | --- |
| `control` | `str \| None = None` | `"checkbox"`, `"slider"`, `"choice"`, `"spin"` or `"text"`. `None` is only a placeholder that the guard test rejects (section 10.2). |
| `choices` | `tuple[tuple[str, str], ...] \| None = None` | `(value, label)` pairs, in display order, for a choice. `None` for a choice whose options the driver supplies (number language). |
| `depends_on` | `tuple[str, Any] \| None = None` | `(controller_key, value)`. The control is enabled exactly when the controller's current panel value equals `value`. |
| `panels` | `tuple[str, ...] = ("voice", "pipeline")` | Where the setting is shown. `"voice"` is the NVDA Voice panel (and the ring for driver settings); `"pipeline"` is the Speech Pipeline panel. |
| `panel_scale` | `int = 1` | Speech Pipeline panel slider only: it shows `value // panel_scale` and saves `shown * panel_scale` (Q3). |
| `pipeline_config` | `bool = True` | `False` marks an ordering-only entry whose value NVDA stores as a driver setting (section 5.3). |

Refinements over the proposal, with reasons:

- **No `panel_label`** (Q2). The single `label` is the msgid for both panels.
- **`pipeline_config` instead of a separate list.** Number language must sit between `cni` and `nummod` (Q1). A second ordered list would bring back the problem this feature removes: two orders to keep in step. One flag on one table, plus a derived tuple of stored entries (section 5.3), keeps a single order.
- **`choices` carries labels as msgids evaluated at import**, like `label` already is (`settings.py:9`, `:85-173`). `NUMBER_MODES` becomes `tuple(value for value, _label in NUMBER_MODE_CHOICES)`, and `_get_availableNummods` builds from `NUMBER_MODE_CHOICES`. This removes the third copy of the modes (`__init__.py:482-488`, `speechSettingsDialog.py:142-148`).
- **`control` is explicit, even where `kind` implies it.** Driver controls are made by NVDA from the driver setting class (`settingsDialogs.py:1592-1599`). The guard test checks that `control` matches that class (bool → checkbox, int → slider, str → choice), so the Voice panel's attribute suffix rule (section 5.8) stays right.
- **Controllers are limited to checkbox and choice.** Those are the only kinds whose change event both panels already handle, and both are discrete, so `==` is well defined.

### 5.2 The table in its new order

`PIPELINE_SETTINGS` lists every entry in the Q1 order. "both" means `("voice", "pipeline")`.

| # | key | kind, default | driver_id | control | panels | label | display_name | ring | extra |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `scope` | str, `"WorldVoice"` | — | choice | pipeline | "Effect scope" | — | — | `choices=SCOPE_CHOICES` |
| 2 | `global_wait_factor` | int, 10 | `globalwaitfactor` | slider | both | "Global wait factor" | — | yes | `min_step=10`, `normalize=_floor_to_ten`, `panel_scale=10` |
| 3 | `ignore_comma_between_number` | bool, False | `cni` | checkbox | both | "Ignore commas between numbers" | — | no | |
| 4 | `number_language` | str, `"default"` | `numlan` | choice | voice | "Number &language" | "Number language" | yes | `pipeline_config=False`; options from `availableNumlans` |
| 5 | `number_mode` | str, `"value"` | `nummod` | choice | both | "Number &mode" | "Number mode" | yes | `choices=NUMBER_MODE_CHOICES`, `normalize=_number_mode` |
| 6 | `group_size` | int, 3 (1–10) | — | spin | both | "Group size" | — | — | `depends_on=("number_mode", "group")` |
| 7 | `group_wait_factor` | int, 0 | `groupwaitfactor` | slider | both | "Group wait factor" | — | yes | `depends_on=("number_mode", "group")` |
| 8 | `number_wait_factor` | int, 10 | `numberwaitfactor` | slider | both | "Number wait factor" | — | yes | |
| 9 | `item_wait_factor` | int, 10 | `itemwaitfactor` | slider | both | "Item wait factor" | — | yes | |
| 10 | `sayall_wait_factor` | int, 10 | `sayallwaitfactor` | slider | both | "Say all wait factor" | — | yes | |
| 11 | `chinesespace_wait_factor` | int, 10 | `chinesespacewaitfactor` | slider | both | "Chinese space wait factor" | — | yes | |
| 12 | `punctuation_pause_enabled` | bool, True | `punctuationpauseenabled` | checkbox | both | "Enable punctuation pause control" | "Punctuation pauses" | yes | |
| 13 | `remove_punctuation_characters` | bool, False | `removepunctuationcharacters` | checkbox | both | "Remove configured punctuation at pause points" | "Remove punctuation at pause points" | yes | `depends_on=("punctuation_pause_enabled", True)` |
| 14 | `punctuation_wait_factor` | int, 0 | `punctuationwaitfactor` | slider | both | "Punctuation wait factor" | — | yes | `depends_on=("punctuation_pause_enabled", True)` |
| 15 | `punctuation_pause_characters` | str, `""` | — | text | both | "Punctuation pause characters" | — | — | `normalize=_strip`, `depends_on=("punctuation_pause_enabled", True)` |

- `SCOPE_CHOICES = (("all", _("All Synthesizers (Global)")), ("WorldVoice", _("Only WorldVoice Synthesizer")))` and `NUMBER_MODE_CHOICES = (("value", _("value")), ("number", _("number")), ("group", _("group")))` are module constants in `settings.py`, defined before `_number_mode`. The choice msgids are unchanged.
- The comment at `:78` becomes "Every panel and the settings ring show these settings in this order."
- `ring` keeps its current value for every driver entry. Non-driver entries keep the default `True`, which nothing reads.
- Every default, kind, bound, normaliser and confspec string is unchanged. `group_size` keeps `min_value=1, max_value=10` (`:178`).

### 5.3 Stored entries and the ordering-only entry

New derived tuple in `settings.py`:

```python
PIPELINE_STORED_SETTINGS = tuple(spec for spec in PIPELINE_SETTINGS if spec.pipeline_config)
```

- `PIPELINE_SETTING_BY_KEY`, `DEFAULT_PIPELINE_SETTINGS`, `PIPELINE_CONFIG_KEYS` and `PIPELINE_CONFSPEC` (`:181-184`) are built from `PIPELINE_STORED_SETTINGS`.
- `ConfigPipelineRepository.load` (`:278-282`) iterates `PIPELINE_STORED_SETTINGS`.
- As a result, `number_language`:
  - is not in `PIPELINE_CONFSPEC`, so `config.conf.spec["WorldVoice"]["pipeline"]` (`__init__.py:69`) has no such key;
  - is not a `PipelineSettings` field and is never read from or written to the pipeline section;
  - is rejected by `pipeline_settings.update(number_language=…)` with the existing `KeyError` (`settings.py:306-309`);
  - is not in the Voice panel's discard snapshot keys (`VoiceSettingsDialogs.py:169-173`). NVDA's `loadSettings` restores it on discard, as today (`settingsDialogs.py:1628`).
- The driver:
  - `_pipeline_driver_setting` passes `useConfig=not spec.pipeline_config`. Every stored entry keeps `useConfig=False`; `numlan` gets `useConfig=True`, as today.
  - `_driver_settings` (`__init__.py:139-142`) iterates `PIPELINE_SETTINGS` (all entries, for order) and keeps entries with a `driver_id`. The hard-coded `numlan` block (`:143-154`) is deleted. Its label, ring name, `defaultVal="default"` and ring flag now come from the table entry.
  - The descriptor loop (`:511-513`) skips entries with `pipeline_config=False`. Without this, `setattr(SynthDriver, "numlan", _PipelineSetting("number_language"))` would replace the driver's own `numlan` property (`:476-480`), and every read would raise `AttributeError` on `PipelineSettings`. The guard test checks that `numlan` is still the driver's own property.
  - The options still come from `_get_availableNumlans` (`:470-474`), which NVDA calls as `availableNumlans` (`settingsDialogs.py:1481-1486`; `synthSettingsRing.py:75-77`).
- The driver keeps importing only `PIPELINE_CONFSPEC`, `PIPELINE_SETTINGS` and `pipeline_settings`, plus the new `NUMBER_MODE_CHOICES` (`__init__.py:47`).

### 5.4 Pure layout rules (`addon/synthDrivers/WorldVoice/pipeline/panelLayout.py`, new)

A module with no add-on, wx or NVDA imports. Every function takes the specs it works on, so tests and mutmut can load it on its own. Suggested signatures:

```python
VOICE_PANEL = "voice"
PIPELINE_PANEL = "pipeline"
ABSENT = object()  # read() result: this panel has no control for the controller

def panel_specs(specs, panel) -> tuple[PipelineSettingSpec, ...]
def label_text(spec) -> str
def to_display(spec, value: int) -> int
def from_display(spec, shown: int) -> int
def choice_index(values: Sequence[str], value) -> int
def selected_value(values: Sequence[str], selection: int) -> str | None
def controller_keys(specs) -> frozenset[str]
def dependent_states(specs, read: Callable[[str], Any]) -> dict[str, bool]
def voice_placements(specs, has_row: Callable[[str], bool]) -> list[tuple[str, str | None]]
```

Rules:

- `panel_specs`: the entries whose `panels` contain `panel`, in table order.
- `label_text`: `spec.label` for a checkbox, `f"{spec.label}:"` otherwise (Q2; NVDA's rule at `settingsDialogs.py:1437`, `:1474`, `:1525`). It is used for every control WorldVoice makes itself, in both panels. NVDA makes the driver controls' labels itself.
- `to_display(spec, value)` = `value // spec.panel_scale`; `from_display(spec, shown)` = `shown * spec.panel_scale` (Q3).
- `choice_index(values, value)`: the index of `value`, or 0 when it is missing. This keeps "an unknown stored value selects the first choice" (`speechSettingsDialog.py:130-133`, `:156-159`).
- `selected_value(values, selection)`: `values[selection]` when `0 <= selection < len(values)`, else `None`. A `-1` selection never maps to the last value.
- `controller_keys`: the keys named in any `depends_on`.
- `dependent_states(specs, read)`:
  - for every spec with `depends_on = (controller, expected)`, call `read(controller)`;
  - `ABSENT`: the spec is left out of the result, so its control is not touched (another synth in the Voice panel; section 5.9);
  - anything else: the result maps `spec.key` to `value == expected`, where `None` (no selection) never equals an expected value.
- `voice_placements(specs, has_row)`: for each Voice-panel entry without a `driver_id`, in table order, its anchor key or `None`:
  - ~~when no Voice-panel driver entry has a row (another synth), every anchor is `None`;~~ Removed after the batch 1 review (B1-M9): with N5 the Voice panel calls this for WorldVoice only, so the rule has no use;
  - ~~otherwise~~ the anchor is the nearest preceding Voice-panel entry for which `has_row(key)` is true, or `None` when no earlier entry has a row.

### 5.5 Shared control builder (`addon/synthDrivers/WorldVoice/pipelineControls.py`, new)

The wx side, used by both panels. It sits in the core driver package next to `VoiceSettingsDialogs.py`. The global plugin already imports from `synthDrivers.WorldVoice` (`speechSettingsDialog.py:14-19`). No engine driver imports it, so drivers stay independently installable.

```python
CHANGE_EVENTS: dict[str, wx.PyEventBinder]  # "checkbox": wx.EVT_CHECKBOX, "choice": wx.EVT_CHOICE

def make_control(parent, helper: guiHelper.BoxSizerHelper, spec, value) -> wx.Window
def control_value(spec, control) -> Any  # the value to save; None for a choice with no selection
def control_row(control, spec)            # the settings-sizer item: the checkbox itself, else its containing sizer
```

`make_control`, by `spec.control`:

| control | made with | initial value |
| --- | --- | --- |
| checkbox | `helper.addItem(wx.CheckBox(parent, label=label_text(spec)))` | `SetValue(value)` |
| choice | `helper.addLabeledControl(label_text(spec), wx.Choice, choices=[label for _v, label in spec.choices])` | `Select(choice_index(values, value))` |
| slider | `helper.addLabeledControl(label_text(spec), wx.Slider, value=to_display(spec, value), minValue=to_display(spec, spec.min_value), maxValue=to_display(spec, spec.max_value), style=wx.SL_HORIZONTAL)` | in the constructor |
| spin | `helper.addLabeledControl(label_text(spec), nvdaControls.SelectOnFocusSpinCtrl, min=spec.min_value, max=spec.max_value, initial=value)` | in the constructor |
| text | `helper.addLabeledControl(label_text(spec), wx.TextCtrl)` | `SetValue(value)` |

- The slider's construction value replaces master's placeholder (`value=50` or `5`) followed by `SetValue` (`speechSettingsDialog.py:176-181`, `:186-191`). The result is the same.
- `control_value`: checkbox and text `GetValue()`, slider `from_display(spec, GetValue())`, spin `GetValue()`, choice `selected_value(values, GetCurrentSelection())`.
- The caller passes the helper. The Speech Pipeline panel passes its one helper, so its spacers stay (`guiHelper.py:384`, `:412-415`). The Voice panel passes a fresh helper per control, so no spacer is left behind when the row moves (as at `VoiceSettingsDialogs.py:98`, `:125`).

### 5.6 Speech Pipeline panel

`SpeechPipelinePanel.makeSettings` becomes a loop over `panel_specs(PIPELINE_SETTINGS, PIPELINE_PANEL)`:

1. `settings = pipeline_settings.get()` once (as at `:118`).
2. For each spec: `control = make_control(self, settingsSizerHelper, spec, getattr(settings, spec.key))`, stored as `self._<key>_<suffix>` with suffix `checkbox`, `choice`, `slider`, `spin`, or `edit` for text. These are exactly today's attribute names (section 3.5), so tests and readers keep them.
3. For each spec in `controller_keys`: `self.Bind(CHANGE_EVENTS[spec.control], self._onControllerChange, control)`. This is the same panel-level binding as today (`:160`, `:238-242`). Only controllers are bound: "Remove configured punctuation…" stays unbound (`tests/test_settings_panels.py:208-212`).
4. `self._applyDependencies()` once, after every control exists (as at `:267-268`).

Removed: `_scope_value`, `number_mode_value`, `_selected_number_mode`, `onNumberModeChange`, `onPunctuationPauseEnabledChange` (`:120-124`, `:142-148`, `:270-288`).

`onSave` makes one `pipeline_settings.update(**values)` call, where `values` maps each shown spec with `pipeline_config` to `control_value(spec, control)`. A choice whose value is `None` is left out, so its stored value is kept (section 5.10).

New control order, Tab order and labels: section 6.1.

### 5.7 Voice panel driver controls and the ring

- Nothing in the Voice panel code orders driver controls. They follow `supportedSettings`/`allSupportedSettings` (section 5.3), which now follow the table.
- The ring follows `supportedSettings` (`synthSettingsRing.py:207-219`). New ring order: section 6.3.

### 5.8 Voice panel non-driver controls

`WorldVoiceVoiceSettingsPanel.makeSettings` becomes:

1. Snapshot as today (`VoiceSettingsDialogs.py:25`).
2. `self.createDriverSettings()` (unchanged; NVDA copy).
3. `super().makeSettings(settingsSizer)`.
4. `self._addPipelineControls(settingsSizer)`.
5. `self._bindControllers()`.
6. `self._applyDependencies()`.

`_addPipelineControls(settingsSizer)`:

- `entries = panel_specs(PIPELINE_SETTINGS, VOICE_PANEL)`. `PIPELINE_SETTINGS` is read from the module global at call time, so a test can patch it with a synthetic table.
- For each entry without a `driver_id`, in table order:
  - make the control with a fresh `guiHelper.BoxSizerHelper(self, sizer=settingsSizer)`, valued from one `pipeline_settings.get()`;
  - store it as `self.<camelKey><Suffix>`, where `camelKey` is the key in lower camel case and `Suffix` is `Checkbox`, `List`, `Slider`, `Spin` or `Edit`. This gives today's `groupSizeSpin` and `punctuationPauseCharactersEdit` (`:100`, `:126`).
- Then, for each `(key, anchor)` in `voice_placements(entries, has_row)`, with `anchor` not `None`:
  - the anchor row is `self.sizerDict[anchor.driver_id]` for a driver anchor, or `control_row(...)` of the anchor's own control;
  - the anchor's index is the first child of `settingsSizer` whose `GetSizer()` or `GetWindow()` is that row. Matching the window is new: a checkbox driver row is a window (`settingsDialogs.py:1544`, `:1584`). Master only matched sizers (`VoiceSettingsDialogs.py:112-119`, `:133-140`), which was enough because no added control followed a checkbox;
  - the control's row is moved there with `_moveSizer(settingsSizer, row, index + 1)` (unchanged helper, `:14-20`);
  - `control.MoveAfterInTabOrder(anchorControl)`, where a driver anchor's control is `<driver_id>Slider`, `<driver_id>Checkbox` or `<driver_id>List` (`settingsDialogs.py:1443`, `:1496`, `:1526`).
- `has_row(key)` is true for a driver entry whose `driver_id` is in `sizerDict`, and for a non-driver entry whose control exists. Rows are added in table order, so an anchor that is itself an added control was placed first.

Removed: `_addGroupSizeControl`, `_addPunctuationPauseCharactersControl`, every name of a specific setting in the panel code.

With the Q1 table the anchors are `number_mode` for the group size and `punctuation_wait_factor` for the characters. These are the positions of master (section 6.2).

**After `updateDriverSettings`.** A voice change runs NVDA's `updateDriverSettings(changedSetting="voice")` (`settingsDialogs.py:1343-1350`). It hides, shows and updates rows (`:1553-1568`) and never moves one. For WorldVoice it never creates one either (section 3.4). So the placement made in `makeSettings` stays right, and nothing needs to run again. The non-driver rows are not in `sizerDict`, so they are never hidden.

**Another synthesizer.** ~~No table driver entry has a row, so every anchor is `None`. The added controls stay where the helper put them: after NVDA's own controls, in table order (group size, then characters), with no tab move. This is exactly master's layout (`tests/test_voice_settings_panel.py:336-355`).~~ Changed by the user (2026-10-21, N5): `_addPipelineControls` creates none of the non-driver controls when `_isWorldVoice()` is false, and sets their attributes to `None`, so nothing refers to windows of an earlier build. When the synthesizer changes while the dialog is open, NVDA calls the Voice panel's `onPanelActivated` (`settingsDialogs.py:1229-1245`), whose `refreshGui` runs `settingsSizer.Clear(delete_windows=True)` and then `makeSettings` again on the same panel (`:1633-1646`). The old windows are therefore destroyed by NVDA and the rule runs again for the new synth: neither hiding nor destroying is needed. The Speech Pipeline panel stays the place to change these settings for another synth.

**`_createNewControl` index.** The moved rows shift the `len(sizerDict) - 1` index that `_createNewControl` uses (`settingsDialogs.py:1585-1590`). This is safe for the same reasons as on master: WorldVoice creates every row up front, and another synth has no ~~moved rows~~ added rows (N5).

### 5.9 Enable rules (both panels)

`_applyDependencies()` calls `dependent_states(specs, self._readController)` for the panel's specs. For each key in the result, it calls `Enable(state)` on that key's control, skipping a control that does not exist yet. Disabled controls are disabled, not hidden, and keep their values. `LabeledControlHelper` disables the label too (`guiHelper.py:227-229`).

**Which value is read.** Always the controller's control in this panel, never the driver or the service, whether the controller is a choice or a checkbox.

- In the Voice panel, WorldVoice's handler runs before NVDA's writer (section 3.4), so the driver still holds the old value when the handler runs.
- After `SetValue`/`SetSelection` in `_updateValueForControl`, the control already holds the driver's value, so reading the control gives the same answer.

`_readController(key)`:

| Panel | Controller | Value |
| --- | --- | --- |
| Voice | driver checkbox | `getattr(self, f"{driver_id}Checkbox").GetValue()` |
| Voice | driver choice | `selected_value([o.id for o in getattr(self, f"_{driver_id}s", [])], list.GetSelection())` |
| Voice | any, control missing | `ABSENT` |
| Speech Pipeline | checkbox | `GetValue()` |
| Speech Pipeline | choice | `selected_value(values, GetCurrentSelection())` |

**The -1 selection.** A choice with no selection reads as `None`, so every dependent is disabled. This covers:

- a stored mode missing from a reloaded list (`VoiceSettingsDialogs.py:249-256`, `tests/test_voice_settings_panel.py:324-333`);
- a Speech Pipeline choice set to -1 (`tests/test_settings_panels.py:139-145`).

**When the rules run.**

| Point | Voice panel | Speech Pipeline panel |
| --- | --- | --- |
| Panel opens | `_applyDependencies()` at the end of `makeSettings`. The calls made during `super().makeSettings` skip the non-driver dependents, which do not exist yet. | at the end of `makeSettings` |
| Controller change | `_bindControllers()` binds `CHANGE_EVENTS[...]` on each controller control that exists (`nummodList`, `punctuationpauseenabledCheckbox`) to `_onControllerChange`, which calls `evt.Skip()` first (so NVDA's writer still runs), then applies | `self.Bind(..., control)` on the panel; the handler applies |
| Voice change | `_updateValueForControl`: after the value is set, `if setting.id in self._controllerDriverIds(): self._applyDependencies()`. This replaces the two special cases (`:230-232`, `:257-259`). `SetValue`/`SetSelection` fire no event. | — (no voice change in this panel) |
| Ring change while open | no refresh until the next voice change or rebuild (F6) | — (the panel reads the service when it is built) |

`_controllerDriverIds()` is the set of `driver_id`s of `controller_keys`. Only the end of `_updateValueForControl` changes; NVDA's own branches stay as they are.

**Another synthesizer.** Neither controller control exists, so `read` returns `ABSENT`. ~~and the two added controls stay enabled, as on master (`tests/test_voice_settings_panel.py:351-354`).~~ With N5 (Changed by the user (2026-10-21, N5)) there are no added controls to enable.

### 5.10 Save, discard and snapshot

- **Voice panel `onSave`:** ~~one~~ when `_isWorldVoice()` is true at save time, one `pipeline_settings.update(**values)` over the Voice-panel non-driver entries with `pipeline_config` whose control exists, then NVDA's `onSave`, then the snapshot for WorldVoice. For another synth it writes no pipeline setting (Changed by the user (2026-10-21, N5)). The check runs at save time because a panel built for WorldVoice can be saved before NVDA rebuilds it for a new synth. With the Q1 table these are `group_size` and `punctuation_pause_characters`, in one call, as today (`VoiceSettingsDialogs.py:148-156`). A choice reading `None` would be left out; there is none today.
- **Voice panel `onDiscard`:** unchanged (`:161-175`). It uses `PIPELINE_CONFIG_KEYS`, which now holds stored keys only. The key set is unchanged (section 8).
- **Speech Pipeline panel `onSave`:** one `update` over every shown stored entry (section 5.6).
  - The global wait is saved `* 10` through `from_display`.
  - A choice with no selection keeps its stored value. This was already the rule for the mode (`speechSettingsDialog.py:291-293`). For the scope it replaces writing `"WorldVoice"` (`:295`). A `wx.Choice` the panel has selected cannot return to -1 through the UI, so no user sees this (N2).
- Disabled controls are still saved in both panels, as today.

## 6. What the user sees and hears

### 6.1 Speech Pipeline panel (Tab order = layout order)

| # | Master | New |
| --- | --- | --- |
| 1 | Effect Scope: | Effect scope: |
| 2 | Ignore comma between number | **Global wait factor:** (moved up; 0..10) |
| 3 | Number mode: | Ignore commas between numbers |
| 4 | Group size: | Number mode: (accelerator Alt+M) |
| 5 | group wait factor: | Group size: |
| 6 | global wait factor: | Group wait factor: |
| 7 | number wait factor: | Number wait factor: |
| 8 | item wait factor: | Item wait factor: |
| 9 | sayall wait factor: | Say all wait factor: |
| 10 | chinese space wait factor: | Chinese space wait factor: |
| 11 | Enable punctuation pause control | Enable punctuation pause control |
| 12 | Remove configured punctuation at pause points | Remove configured punctuation at pause points |
| 13 | punctuation wait factor: | Punctuation wait factor: |
| 14 | Punctuation pause characters: | Punctuation pause characters: |

- The only order change is the global wait factor, which moves from 6 to 2 (Q1).
- The labels change to the shared driver labels with ":" (Q2, section 7).
- The number mode label is now "Number &mode:", so the panel gains the accelerator Alt+M. Nothing else in the panel uses M; the dialog's own "&Categories:" is Alt+C (`settingsDialogs.py:576`).
- Tab skips disabled controls. With a mode other than group, Tab goes from Number mode straight to Number wait factor. With the switch off, Tab goes from the switch straight to the end of the panel.

### 6.2 NVDA Voice panel with WorldVoice (Tab order = layout order)

The rows before the table (Voice … Volume, Detect language based on Unicode characters) and NVDA's own rows after it are unchanged.

| # | Master | New |
| --- | --- | --- |
| 1 | Ignore comma between number | **Global wait factor:** |
| 2 | Number Language: | Ignore commas between numbers |
| 3 | Number Mode: | Number language: |
| 4 | Group size: | Number mode: |
| 5 | Global wait factor: | Group size: |
| 6 | Number wait factor: | **Group wait factor:** |
| 7 | Group wait factor: | Number wait factor: |
| 8 | item wait factor: | Item wait factor: |
| 9 | Say all wait factor: | Say all wait factor: |
| 10 | Chinese space wait factor: | Chinese space wait factor: |
| 11 | Enable punctuation pause control | Enable punctuation pause control |
| 12 | Remove configured punctuation at pause points | Remove configured punctuation at pause points |
| 13 | Punctuation wait factor: | Punctuation wait factor: |
| 14 | Punctuation pause characters: | Punctuation pause characters: |

- Global wait moves before Ignore commas; Group wait moves up, right after Group size (Q1).
- Group size and the characters edit keep their master positions: after Number mode and after Punctuation wait factor.
- The accelerators stay: Alt+L for Number language, Alt+M for Number mode.
- **Another synthesizer:** ~~unchanged from master. Group size and Punctuation pause characters sit after NVDA's own controls, enabled, and are saved on Save.~~ Changed by the user (2026-10-21, N5): the Voice panel shows neither Group size nor Punctuation pause characters, and Save writes no pipeline setting. They are changed in the Speech Pipeline panel.

### 6.3 Settings ring

The entries before the table (voice … volume, uwv) are unchanged, and the ring still starts at rate.

| # | Master | New |
| --- | --- | --- |
| 1 | Number Language | **Global wait factor** |
| 2 | Number Mode | Number language |
| 3 | Global wait factor | Number mode |
| 4 | Number wait factor | **Group wait factor** |
| 5 | Group wait factor | Number wait factor |
| 6 | item wait factor | Item wait factor |
| 7 | Say all wait factor | Say all wait factor |
| 8 | Chinese space wait factor | Chinese space wait factor |
| 9 | Punctuation pauses | Punctuation pauses |
| 10 | Remove punctuation at pause points | Remove punctuation at pause points |
| 11 | Punctuation wait factor | Punctuation wait factor |

Exactly two entries move:

- Global wait factor moves from after Number mode to right after uwv ("Detect language based on Unicode characters");
- Group wait factor moves from after Number wait factor to right after Number mode.

Ignore commas is still not in the ring. The ring keeps its position by setting id across a voice change (`synthSettingsRing.py:201-212`), so moving entries does not lose the current one. The ring names follow the label rule: "Number language", "Number mode", "Item wait factor".

### 6.4 What NVDA reads

The roles and values are NVDA's standard reports; record the exact wording on Windows (section 10.6).

| Control | Voice panel | Speech Pipeline panel |
| --- | --- | --- |
| Global wait factor | "Global wait factor: slider 10" (0..100, step 10) | "Global wait factor: slider 1" (0..10; saved × 10) |
| Ignore commas between numbers | "Ignore commas between numbers check box not checked" | same |
| Number language | "Number language: combo box default Alt+L" | — |
| Number mode | "Number mode: combo box value Alt+M" | same, now with Alt+M |
| Group size | "Group size: spin button 3"; "unavailable" outside group mode | same |
| Group wait factor | "Group wait factor: slider 0"; "unavailable" outside group mode | same |
| Other wait factors | "<label>: slider <value>" | same |
| Enable punctuation pause control | check box | same |
| Remove configured punctuation…, Punctuation wait factor, Punctuation pause characters | "unavailable" while the switch is off | same |

- A disabled control is skipped by Tab. Object navigation still reaches it, and NVDA reports it as unavailable; its label is disabled with it (`guiHelper.py:227-229`).
- In zh_TW the labels are the translations in section 7. NVDA appends an ASCII ":" in the Voice panel, and the Speech Pipeline panel now does the same (F5).

## 7. Strings and translations

Decided by the user (2026-10-21): one label per setting, in sentence case, with the colon rule of Q2. Every new or changed `_()` call gets a `# Translators:` comment directly above it (`tests/test_translator_comments.py:14-27`).

The existing driver-label comment "Label for a setting in voice settings dialog." becomes "Label for a pipeline setting in the voice settings panel and the Speech Pipeline panel." Changing a comment does not change a msgid. The two labels without a comment (`settings.py:85`, `:164`) and the choice labels moved into `settings.py` get one too.

### 7.1 Every msgid

**Changed** (old msgid → new msgid; zh_TW reuses the existing wording):

| Old | New | zh_TW | Used by |
| --- | --- | --- | --- |
| "Number &Mode" | "Number &mode" | 數字模式(&M) | label, both panels |
| "Number Mode" | "Number mode" (an existing msgid, `speechSettingsDialog.py:32`; zh_TW 數字模式, `nvda.po:374-375`) | — | ring name |
| "Number &Language" | "Number &language" | 數字語言(&L) | label, Voice panel |
| "Number Language" | "Number language" (an existing msgid, `speechSettingsDialog.py:31`; zh_TW 數字語言, `nvda.po:378-379`) | — | ring name |
| "item wait factor" (label) | "Item wait factor" | 項目停頓參數 | label, both panels, ring |
| "Ignore comma between number" (label) | "Ignore commas between numbers" | 忽略在數字間的逗號 | label, both panels |
| "Effect Scope:" | "Effect scope" | 作用範圍 | label, Speech Pipeline panel |
| "Group size:" | "Group size" | 每組位數 | label, both panels |
| "Punctuation pause characters:" | "Punctuation pause characters" | 標點停頓字元 | label, both panels |

**Removed** (no longer used anywhere in the add-on):

- Speech Pipeline panel: "Number mode:", "global wait factor:", "number wait factor:", "group wait factor:", "item wait factor:", "sayall wait factor:", "chinese space wait factor:", "punctuation wait factor:".
- Through the changes above: "Effect Scope:", "Group size:", "Punctuation pause characters:", "Number &Mode", "Number Mode", "Number &Language", "Number Language".

**Kept and still used:**

- Shared labels (already sentence case): "Global wait factor", "Number wait factor", "Group wait factor", "Say all wait factor", "Chinese space wait factor", "Punctuation wait factor", "Enable punctuation pause control", "Remove configured punctuation at pause points".
- Ring names: "Punctuation pauses", "Remove punctuation at pause points".
- Choices: "value", "number", "group", "default", "All Synthesizers (Global)", "Only WorldVoice Synthesizer". The case rule covers labels only, so the scope choices keep their capitals.
- Not in the table, untouched: "Detect language based on Unicode characters".
- Still used by the pipeline log switches only (N1): "Ignore comma between number" (`speechSettingsDialog.py:30`) and "item wait factor" (`:34`). "Number mode" and "Number language" are used by both the log switches and the ring.

**Added:** none apart from the new msgids in the "Changed" table.

### 7.2 `addon/locale/zh_TW/LC_MESSAGES/nvda.po`

- Add the seven new msgids of the "Changed" table with the zh_TW wording shown.
- Delete the entries of the 15 removed msgids, so the catalog holds no dead entries (N7):
  - "Effect Scope:" (`:152-153`), "Number mode:" (`:179-180`), "Group size:" (`:185-186`), "group wait factor:" (`:190-191`), "global wait factor:" (`:194-195`), "number wait factor:" (`:198-199`), "item wait factor:" (`:202-203`), "sayall wait factor:" (`:206-207`), "chinese space wait factor:" (`:210-211`), "punctuation wait factor:" (`:227-228`), "Punctuation pause characters:" (`:232-233`);
  - "Number &Language" (`:583-584`), "Number Language" (`:589-590`), "Number &Mode" (`:595-596`), "Number Mode" (`:601-602`).
- Keep "Ignore comma between number" (`:159-160`) and "item wait factor" (`:389-390`): the log switches use them.
- Check with `msgfmt --check`. Generate the `.pot` with `scons pot` and do not commit it (`DEVELOPMENT_WORKFLOW.md` section 6).

### 7.3 Other languages

Other languages lose only the changed or removed msgids. They see English for these until translators add them (N6):

| Locale | Untranslated after this change |
| --- | --- |
| ar | Number &mode, Number &language, Ignore commas between numbers; ring names Number mode and Number language (ar has only the old capitalised msgids) |
| ru, uk, tr, zh_CN, zh_HK | Effect scope, Number &mode, Number &language, Item wait factor, Ignore commas between numbers |
| all | Group size, Punctuation pause characters (only zh_TW had them) |

The removed Speech Pipeline panel msgids lose nothing else. The shared label of each one is already translated in the same locales: compare the locale lists for "global wait factor:" and "Global wait factor", and likewise for number, say all and Chinese space.

## 8. Config, compatibility and errors

- **Stored keys and values: unchanged.**
  - `PIPELINE_CONFSPEC` holds the same 14 keys with the same strings. Only its dict order follows the new table, which configobj does not use to read or write values.
  - `numlan` stays in `[speech][WorldVoice]`, written and read by NVDA (`autoSettings.py:156-163`, `:196-203`).
- **No migration.** Profiles and stored values read exactly as before.
- **Errors.** The table is static. A malformed entry is caught by the guard test (section 10.2) and never raises at runtime. The panels skip a control that does not exist, as today (`VoiceSettingsDialogs.py:58-61`, `:89-91`).

## 9. Engines and layers

- **Core table:** `pipeline/settings.py`.
- **New core modules:** `pipeline/panelLayout.py` (pure) and `pipelineControls.py` (wx).
- **Driver package:** `synthDrivers/WorldVoice/__init__.py` (driver settings, descriptors, `availableNummods`) and `VoiceSettingsDialogs.py`.
- **Global plugin:** `speechSettingsDialog.py`.
- **Untouched:** every engine wrapper and inner driver, `compat/`, `runtime/`, `createDriverSettings`. Engine drivers stay independently installable.
- **Config:** `pyproject.toml` `[tool.mutmut] source_paths` gains `pipeline/panelLayout.py` (`pyproject.toml:35-45`).

## 10. Test plan

### 10.1 Unit tests for `panelLayout` (new `tests/test_panel_layout.py`)

- `panel_specs`: the real table gives the Q1 order without number language for `"pipeline"`, and without scope for `"voice"`.
- `label_text`: checkbox → label; slider, choice, spin, text → label + ":"; a label with `&` keeps it.
- `to_display` / `from_display`: scale 10: 57 → 5 and 5 → 50; scale 1 is the identity.
- `choice_index`: known value → its index; unknown or `None` → 0.
- `selected_value`: 0..n-1 → the value; -1, n, n+5 → `None`.
- `dependent_states` on the real table:
  - mode `"group"` → `group_size` and `group_wait_factor` true, the others untouched by the mode rule;
  - `"value"`, `"number"`, `None` → false;
  - switch `True`/`False` → the three punctuation dependents follow;
  - `ABSENT` for both controllers → empty result.
- `voice_placements` on the real table:
  - every row present → `[("group_size", "number_mode"), ("punctuation_pause_characters", "punctuation_wait_factor")]`;
  - ~~no driver row → both `None`;~~ only the added controls have rows → the group size has no earlier row (`None`) and the characters follow the group size (B1-M9);
  - `number_mode` missing but `number_language` present → the group size anchors on `number_language`.

### 10.2 Guard tests for the table (new `tests/test_settings_table_guard.py`)

Each rule is one test over the real table. Each rule also gets a negative case: a synthetic table that breaks it must be reported by the same check function, so the guard is itself tested.

1. Keys are unique; driver ids are unique.
2. `control` is one of the five kinds (catches a new entry without `control`).
3. `control` matches `kind`: checkbox ↔ bool, slider ↔ int, spin ↔ int, choice ↔ str, text ↔ str.
4. A driver entry has checkbox, slider or choice. A Voice-panel entry without a `driver_id` has spin, text, checkbox, slider or choice and a `pipeline_config` of `True`.
5. `label` is a non-empty string; `panels` is a non-empty subset of `{"voice", "pipeline"}`; an entry with a `driver_id` has `"voice"`.
6. A choice shown in the Speech Pipeline panel has `choices`, with unique values that contain the default. A driver choice with `choices` matches the driver's `available<Id>s` (number mode).
7. `depends_on`:
   - the controller exists, has no `depends_on` itself, comes earlier in the table, and appears in every panel where the dependent appears;
   - its control is checkbox (expected value a `bool`) or choice (expected value one of its `choices`).
8. `panel_scale` ≥ 1; a value other than 1 only on a slider whose `min_value`, `max_value` and default are multiples of it.
9. `pipeline_config=False`:
   - the entry has a `driver_id`, is not in the Speech Pipeline panel and is not named by any `depends_on`;
   - its key is in none of `PIPELINE_SETTING_BY_KEY`, `PIPELINE_CONFSPEC`, `PIPELINE_CONFIG_KEYS` and the `PipelineSettings` fields;
   - its driver setting has `useConfig=True`, and the driver attribute is not a `_PipelineSetting`.
10. The first Voice-panel entry has a `driver_id`, so every non-driver Voice entry has an anchor.
11. No Voice-panel attribute name `<camelKey><Suffix>` equals an NVDA driver-control name `<driver_id>Slider|Checkbox|List`.
12. Labels are in sentence case: the first character is upper case (ignoring `&`). No later word starts with a capital, except words in an allow-list (`Unicode`, `Chinese`, `WorldVoice`).

### 10.3 Panel tests (UI harness)

**Harness changes** (`tests/ui_harness.py`):

- `load_settings_dialog` and `load_voice_settings_dialogs` also load `pipeline/panelLayout.py` and `pipelineControls.py` under the alias packages they already use (`:567-576`, `:683-700`).
- `fake_wx` gains nothing: `CheckBox`, `Choice`, `Slider`, `TextCtrl`, `SelectOnFocusSpinCtrl`, `SizerItem.GetWindow` and the `fire` order exist (`:102-138`, `:164-165`, `:277-295`).

**Speech Pipeline panel** (`tests/test_settings_panels.py`):

- The label list of section 6.1, and `sizer.controls()` keys in table order.
- Choices come from the table (`SCOPE_CHOICES`, `NUMBER_MODE_CHOICES` labels). An unknown stored scope or mode selects 0.
- The global slider shows `stored // 10`, has range 0..10 and saves `* 10`; another slider has 0..100.
- Enable states from stored values, after `fire`, and with -1: as today, now through the generic rule.
- `onSave` makes one `update`. A choice with -1 keeps the stored value, for the mode and for the scope (N2).

**Voice panel** (`tests/test_voice_settings_panel.py`):

- The existing tests keep their expectations (section 11).
- The same tests with the full Q1 driver setting list (`SETTINGS` extended to every table driver id): `order(panel)` matches section 6.2.
- **Synthetic tables** (patch `env.module.PIPELINE_SETTINGS`):
  - a non-driver control after a **checkbox** driver row lands right after the checkbox window, with `tab_after` that checkbox;
  - two adjacent non-driver entries keep table order, and the second has `tab_after` the first;
  - a non-driver controller (checkbox) enables a dependent through the generic rule.
- The enable rules at all three points, for both controllers, including the ring-then-voice case and the -1 case (existing tests, kept).
- Another synth: ~~layout, tab and enabled state as on master (existing tests).~~ no WorldVoice control, built directly and after `refreshGui`; Save writes no pipeline setting, also when the synth changed without a rebuild; discard leaves pipeline settings alone (Changed by the user (2026-10-21, N5)).

### 10.4 Order tests (new, `tests/test_settings_order.py`)

- **Driver:** `[s.id for s in synth.allSupportedSettings]` after `uwv` equals the `driver_id`s of `panel_specs(PIPELINE_SETTINGS, "voice")` with a `driver_id`, in order.
- **Ring:** the ring list the way `updateSupportedSettings` builds it (`availableInSettingsRing` filter over `supportedSettings`) equals the driver entries of the table with `ring=True`, in order, after the standard settings.
- **Voice panel:** the panel's table rows (driver ids mapped back to keys, non-driver controls by attribute) equal the keys of `panel_specs(…, "voice")`, and each control's `tab_after` chain follows the same order.
- **Speech Pipeline panel:** the controls' keys, in sizer order, equal the keys of `panel_specs(…, "pipeline")`.

### 10.5 Property tests and mutmut

- Hypothesis (`tests/test_panel_layout.py`), over synthetic tables of up to 8 entries with random `driver_id`, `panels` and presence sets:
  - every anchor precedes its entry and has a row;
  - ~~with no driver row, every anchor is `None`;~~ the anchor is the nearest earlier row, and `None` exactly when no earlier entry has a row (B1-M9);
  - `dependent_states` never names a key whose controller read `ABSENT`;
  - `selected_value` is `None` exactly outside `0..len-1`.
- **mutmut:** add `pipeline/panelLayout.py` to `source_paths`. Run with at most 3 workers and the memory guard (stop below 3 GB MemAvailable). Record each surviving mutant with its reason, and confirm each one by running the suite with that mutant applied, as in phase 29.

### 10.6 Windows / NVDA manual items

Linux tests reach only the fakes. These items need Windows with NVDA and a packaged test build:

1. **Voice panel, WorldVoice:** the layout and Tab order of section 6.2 from Voice to the end, including Group size after Number mode and the characters edit after Punctuation wait factor. Record what NVDA reads for each control (section 6.4).
2. **Speech Pipeline panel:** the layout and Tab order of section 6.1. The global wait factor reads 0..10 and keeps its value after Save and reopen. Alt+M moves to Number mode.
3. **Enable states**, in both panels:
   - on open, for each mode and switch value;
   - on changing the mode with the arrow keys and on toggling the switch;
   - Tab skips disabled controls, and object navigation reports them unavailable.
4. **Voice change** in the Voice panel: every row keeps its place, and the enable states follow the voice's values. Then a ring change of the mode or the switch while the dialog is open, followed by a voice change: the states follow.
5. **Settings ring:** the order of section 6.3, starting at rate. Global wait factor follows "Detect language…"; Group wait factor follows Number mode. A ring change persists, and numlan still persists across an NVDA restart.
6. **Another synth** (eSpeak NG) with WorldVoice installed: in the Voice panel, ~~Group size and Punctuation pause characters sit after NVDA's own controls, enabled, and Save stores them~~ neither Group size nor Punctuation pause characters is shown, and Save changes no pipeline setting (check in the Speech Pipeline panel). Also switch from WorldVoice to eSpeak NG while the settings dialog is open, then from eSpeak NG back to WorldVoice: each time the Voice panel shows the right controls. No error in the log.
7. **zh_TW:** every label of section 7 is translated; record how the colon shows.

## 11. Existing tests that need new expectations

Found by reading every test that loads the touched modules; the plan confirms the list with a red run.

| Test | Why | New expectation |
| --- | --- | --- |
| `test_pipeline_settings_service.py::test_table_drives_fields_defaults_keys_and_confspec` (`:26-51`) | `keys` from all entries now includes `number_language`; the driver id order changes | keys from `PIPELINE_STORED_SETTINGS`; driver ids in Q1 order with `numlan`; one `ring=False` still |
| `test_pipeline_settings_service.py::test_group_settings_replace_the_pair_wait_and_add_the_size` (`:85-92`) | `PIPELINE_CONFIG_KEYS[-1]` | `"punctuation_pause_characters"` |
| `test_worldvoice_pipeline_settings.py::EXPECTED_IDS` (`:20-41`), used by `test_settings_lists_keep_their_order_and_store_pipeline_values_outside_speech_config` (`:44-63`) | new order | `uwv`, `globalwaitfactor`, `cni`, `numlan`, `nummod`, `groupwaitfactor`, `numberwaitfactor`, …; the `useConfig` check (`:55-57`) still holds |
| `test_lint_rewrites.py::test_number_modes_are_a_plain_dict_in_order` (`:41-48`) | `_get_availableNummods` reads `NUMBER_MODE_CHOICES` | env gains `NUMBER_MODE_CHOICES`; same three entries |
| `test_settings_panels.py::test_pipeline_panel_shows_the_stored_settings` (`:32-84`) | order and labels | section 6.1 labels |
| `test_settings_panels.py::test_number_modes_match_the_driver_and_the_panel` (`:94-108`) | `number_mode_value` removed; driver env | compare `NUMBER_MODES`, the driver's keys and the panel choice's values from the spec |
| `test_pipeline_panels.py::test_pipeline_panel_saves_once_through_the_service` (`:33-79`) | `onSave` is generic | env gains the table and the helpers; same update dict; the removed names join the `not hasattr` list |
| `test_pipeline_panels.py::test_voice_panel_discard_after_apply_keeps_applied_pipeline_values` (`:117-153`) and `::test_voice_panel_saves_the_characters_and_group_size_in_one_update` (`:156-179`) | the Voice panel `onSave` is generic | env gains the table and the helpers; same calls |
| `test_translator_comments.py::test_group_strings_have_translator_comments` (`:41-67`) | "Group size:" and "group wait factor:" are gone | `("group", "Group size", "Group wait factor")`; extend the check to every changed msgid of section 7.1 |
| `test_runtime_composition.py` stub (`:613-618`) | the driver imports `NUMBER_MODE_CHOICES` | stub gains `NUMBER_MODE_CHOICES=()` |
| `tests/nvda_stubs.py:91-94` (harness; used by `test_config_stub.py` and every `worldvoice_conf` user) | the AST reader takes every table entry | skip entries with the keyword `pipeline_config=False` |
| `tests/pipeline_harness.py:204-219` `load_synth` | `_get_availableNummods` needs `NUMBER_MODE_CHOICES` when called | environment gains it |

These still pass unchanged:

- `test_voice_settings_panel.py`: the Voice panel labels stay "Group size:" and "Punctuation pause characters:" (label + ":"), and the anchors are the same.
- `test_nvda_settings_copy.py`: `createDriverSettings` and NVDA's `_updateValueForControl` are unchanged.
- `test_worldvoice_speak.py:232-240` (numlan options and property).
- `test_pipeline_pause_properties.py:423`, `:440`.
- `test_pipeline_panels.py::test_log_labels_match_stages_and_confspec`.
- `test_voice_settings_transaction.py:56`.

## 12. Findings needing the user

None of these endangers a decision. Each is informational or comes with a default in section 13.

- **F1. The pipeline log switches share four label msgids.**
  - "Ignore comma between number" and "item wait factor" stay in use by the log switches (`speechSettingsDialog.py:30`, `:34`), while the settings now say "Ignore commas between numbers" and "Item wait factor".
  - The log panel therefore keeps the old wording; see N1.
  - The ring names "Number mode" and "Number language" reuse the log switches' existing msgids, so they keep every existing translation except ar.
- **F2. The Speech Pipeline panel gains an accelerator.** "Number &mode:" gives Alt+M in that panel. NVDA reports it when the choice gets focus. This follows from Q2. There is no conflict in the panel (section 6.1).
- **F3. Translations lost in other languages** (section 7.3). The biggest loss is ar, ru, uk, tr, zh_CN and zh_HK for "Number &mode", "Number &language" and "Ignore commas between numbers", which they translate today in both the Voice panel and the Speech Pipeline panel.
- **F4 (existing, out of scope). An unknown stored scope shows the wrong choice.**
  - The panel selects the first choice, "All Synthesizers (Global)" (`speechSettingsDialog.py:130-133`).
  - The pipeline treats any scope other than `"all"` as WorldVoice-only (`settings.py:240`).
  - Saving the panel then stores `"all"`.
  - This feature keeps the behaviour (`tests/test_settings_panels.py:87-91`).
- **F5. The colon in zh_TW Speech Pipeline labels changes from full-width "：" to ASCII ":".** This follows from the Q2 colon rule, and the Voice panel already shows it that way (`settingsDialogs.py:1437`, `:1474`).
- **F6 (existing).** A ring change does not refresh an open Voice panel. The enable states follow it at the next voice change or rebuild (`settingsDialogs.py:1343-1350`), as on master.

## 13. Open questions

All are new and adopted with the conservative default. Each is Decided by orchestrator with the recommended default; user may override before merge.

1. **N1. Pipeline log switch labels:** unchanged. Aligning them with the new labels (for example "Ignore commas between numbers", sentence case) is a separate change.
2. **N2. Scope choice with no selection:** `onSave` keeps the stored scope, as it already does for the mode, instead of writing `"WorldVoice"`. The UI cannot reach this state.
3. **N3. Modelling number language:** one `pipeline_config` flag on the single table, plus the derived `PIPELINE_STORED_SETTINGS`, rather than a second ordered list.
4. **N4. Module placement and names:** pure rules in `pipeline/panelLayout.py` (added to mutmut), wx builders in `pipelineControls.py`. Attribute names `_<key>_<suffix>` (Speech Pipeline panel) and `<camelKey><Suffix>` (Voice panel), which reproduce today's names.
5. **N5. Another synthesizer:** ~~the Voice panel keeps master's layout. The non-driver controls stay at the end, enabled, and are saved.~~ Decided by the user (2026-10-21): when the Voice panel's driver is not WorldVoice, the panel shows none of the WorldVoice non-driver controls (group size, punctuation characters) and its Save writes no pipeline setting; the Speech Pipeline panel is the place to change them (section 5.8, 5.10).
6. **N6. Other-language catalogs:** not edited (`DEVELOPMENT_WORKFLOW.md` section 6). Copying the old translations onto the new msgids would edit catalogs that belong to translators.
7. **N7. zh_TW catalog:** the 15 entries of removed msgids are deleted, not left obsolete.
8. **N8. Controllers:** only checkbox and choice may control others, and a controller may not depend on another setting. Both rules are enforced by the guard test.

## 14. Flow classification and size

The normal flow is enough. None of the complex-flow criteria (`DEVELOPMENT_WORKFLOW.md` section 4.0) apply:

- the same agent writes the plan and implements it;
- no file must be byte-exact (no inner driver, packaging or build change);
- the change is behavioural and covered by tests, not a mechanical move across many files.

**Estimated plan size: 10 tasks**, so per section 3.2 the implementer works in two batches of 5 (5 / 5): an Opus batch review after batch 1, and the final Fable review after batch 2. Suggested tasks:

1. Table fields, the Q1 order and the guard tests (section 10.2); `PIPELINE_STORED_SETTINGS` and the derived maps; `tests/nvda_stubs.py` reader.
2. Number language entry: `_driver_settings`, `useConfig`, descriptor filter, `NUMBER_MODE_CHOICES` and `_get_availableNummods`; driver and ring order tests.
3. `pipeline/panelLayout.py` with unit and property tests.
4. `pipelineControls.py`, and the harness loaders.
5. Speech Pipeline panel: generic `makeSettings`, enable rules and `onSave`; panel and order tests.
6. Voice panel: generic non-driver placement, including the synthetic-table tests.
7. Voice panel: generic enable rules at the three points and the generic `onSave`; remove the named helpers.
8. Order tests for both panels and the ring (section 10.4).
9. Strings: sentence-case labels, translator comments, zh_TW `nvda.po`, `msgfmt --check`, `scons pot`, `test_translator_comments.py`.
10. mutmut on `panelLayout.py`, the survivor table in this spec, and full verification (`DEVELOPMENT_WORKFLOW.md` section 7).
