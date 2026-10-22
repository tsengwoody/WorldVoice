# Phase 32: share the panels' dependency logic, derive the log labels, and narrow `SpeechContext`

Date: 2026-10-22.
Base: `master` `96d6c08` (phase 31 merged). Branch: `phase32-panels-context` (worktree `/workspace/WorldVoice-phase32`).
Flow: normal flow (DEVELOPMENT_WORKFLOW.md §3), one implementer, one final Fable 5.1 review.
Source: round-6 review `storage/refactor6.md` §1.5, §3.2, §3.3, §3.4, §8, §9 (N22–N25) and §11 "階段 32".
Status: the user approved D1–D4 as recommended on 2026-10-22 (section 3). The smaller choices in section 16 are orchestrator defaults.

All line numbers refer to `96d6c08`. Paths without a prefix are under `addon/synthDrivers/WorldVoice/`; the Speech settings dialog is `addon/globalPlugins/WorldVoice/speechSettingsDialog.py` (called "the dialog" below). The review's line numbers are from `41dc50d`. Phase 31 did not touch the two panels, `pipelineControls.py` or `context.py`, so their numbers still match. In `pipeline/__init__.py` they moved (section 15).

## 1. Problem and goal

Four small items are left from round 6. None of them changes what NVDA users hear or see.

1. **N22, DRY.** Both settings panels apply the table's `depends_on` rules with the same code:
   - `_applyDependencies` (dialog `:167-174`, `VoiceSettingsDialogs.py:76-84`);
   - `_readController` (dialog `:158-165`, `VoiceSettingsDialogs.py:59-74`). The Voice panel's version adds one branch for NVDA's driver choice lists.
   `panelLayout.dependent_states` (`pipeline/panelLayout.py:77-92`) already holds the rule. The loop that applies it to controls, and the read of a controller control, are written twice.
2. **N23, DRY.** `_LOG_LABELS` (dialog `:38-57`) hand-copies six labels that the pipeline settings table already holds. Only `apply_speech_dictionaries` and `speech_viewer` have no table entry.
3. **N25, hygiene.** Two panels check `worldvoice_synth()` and then call `getSynth()` again: `SpeechRoleSettingsPanel.makeSettings` (dialog `:196`, `:207`, `:209`) and `UnicodeDetectionSettingsPanel.makeSettings` (`:505`, `:516`). The `getSynth` import (`:13`) exists only for these three calls.
4. **N24, ISP (D4).** `SpeechContext.default_voice: Any` (`pipeline/context.py:15`) passes the whole voice facade to the stages. The stages read only `.name` (`pipeline/__init__.py:628-629`, `:674`) and `.language` (`:673`).

Goals:

1. `pipelineControls.py` gets `read_control` and `apply_dependencies`. Each panel keeps only what is panel-specific: which specs it shows, how it finds a control, NVDA's driver option lists (Voice panel), `evt.Skip()` (Voice panel) and the destroyed-window rule in `_voiceControl` (`VoiceSettingsDialogs.py:91-100`).
2. `_LOG_LABELS` is built from the table in `LOG_SWITCHES` order. Only the two stage-only labels stay as literal `_()` calls. No msgid changes.
3. The dialog no longer imports or calls `getSynth`.
4. `SpeechContext` holds two plain strings, `default_voice_name` and `default_voice_language`, instead of the facade. It no longer holds any runtime object.
5. Guards keep each item in place. mutmut covers the new helpers.

Affected layers: `pipelineControls.py` (the wx layer from the settings-order work), the two panels, `pipeline/context.py`, two speak passes in `pipeline/__init__.py`, `SynthDriver.speech_context` in the main driver `__init__.py`, the tests, and `pyproject.toml` (mutmut). Not affected: engine wrappers, inner drivers (`driver/<Engine>/driver/`), `runtime/`, `compat/`, `pipeline/panelLayout.py` and translations. Neural is not affected (section 7.5).

## 2. Non-goals

- Any change to what NVDA users hear or see. No new or changed strings, settings, config keys, panels, log keys, enable rules, Tab order or event routing.
- Sharing the controller *binding*.
  - The Speech Pipeline panel binds on the panel, with the control as source (dialog `:145-148`).
  - The Voice panel binds on the control itself (`VoiceSettingsDialogs.py:42-48`). It must call `evt.Skip()` (`:50-53`), so that NVDA's own handler on the same control still writes the driver setting. `tests/test_voice_settings_panel.py:263-278` and `:318-333` pin this.
  - The two routes differ on purpose, so the binding stays in each panel.
- Sharing `_onControllerChange`. It is one call (Speech Pipeline panel) or `Skip` plus one call (Voice panel).
- A mixin or base class for the two panels. The panels have different NVDA bases (`SettingsPanel` and `VoiceSettingsPanel`) and live in different packages. Review §10 rules out any UI abstraction beyond the table-driven `SpeechPipelinePanel`.
- Moving `apply_dependencies` or `read_control` into `panelLayout.py`. They call wx control methods, and `panelLayout.py` is the pure layer (its docstring, `:1-6`).
- Merging `BaseSettingsPanel`/`LOG_SWITCHES` into `PipelineSettingSpec` (review §3.4, §10).
- The other `getSynth()` calls: `pipeline/context.py:26` (the locator itself), `pipeline/__init__.py:51` (`with_order_log`), and the main driver `:216` (injected into the runtime).
- Updating line references in older specs, plans or reviews. They are historical records.

## 3. Decisions

| # | Decision | By |
| --- | --- | --- |
| D1 | Share the dependency logic as two functions in `pipelineControls.py`: `apply_dependencies(specs, read, control_of)` and `read_control(spec, control, driver_options=None)` (section 4). | Decided by the user (2026-10-22) |
| D2 | Build `_LOG_LABELS` from `PIPELINE_SETTINGS` in `LOG_SWITCHES` order. The two stage-only labels stay explicit, and no msgid changes (section 5). | Decided by the user (2026-10-22) |
| D3 | Use the synth that `worldvoice_synth()` returned. Remove the three UI `getSynth()` calls and the import (section 6). | Decided by the user (2026-10-22) |
| D4 | Narrow `SpeechContext.default_voice` to plain values (section 7). | Decided by the user (2026-10-22) |

## 4. Item 1: one dependency path for both panels (D1)

### 4.1 Current code

Speech Pipeline panel (the dialog):

```python
# :158-165
def _readController(self, key):
	(spec,) = [spec for spec in self._specs() if spec.key == key]
	control = self._control(spec)
	if control is None:
		return ABSENT
	if spec.control == "choice":
		return selected_value(choice_values(spec), control.GetCurrentSelection())
	return control.GetValue()

# :167-174
def _applyDependencies(self):
	# Disabled controls keep their values, and onSave still stores them.
	specs = self._specs()
	states = dependent_states(specs, self._readController)
	for spec in specs:
		control = self._control(spec)
		if spec.key in states and control is not None:
			control.Enable(states[spec.key])
```

Voice panel (`VoiceSettingsDialogs.py`):

```python
# :59-74
def _readController(self, key):
	"""...docstring: read the control, not the driver..."""
	(spec,) = [spec for spec in self._voiceSpecs() if spec.key == key]
	control = self._voiceControl(spec)
	if control is None:
		return ABSENT
	if spec.control != "choice":
		return control.GetValue()
	if spec.driver_id is not None:
		# No selection (-1) names no option, although the list's last option is at -1.
		options = [option.id for option in getattr(self, f"_{spec.driver_id}s", [])]
		return selected_value(options, control.GetSelection())
	return selected_value(choice_values(spec), control.GetCurrentSelection())

# :76-84
def _applyDependencies(self):
	# Disable rather than hide: NVDA's updateDriverSettings shows every supported
	# control again after a voice change, but never enables or disables one.
	specs = self._voiceSpecs()
	states = dependent_states(specs, self._readController)
	for spec in specs:
		control = self._voiceControl(spec)
		if spec.key in states and control is not None:
			control.Enable(states[spec.key])
```

What differs, and stays in each panel:
- the spec list: `_specs()` (dialog `:151-153`) or `_voiceSpecs()` (`VoiceSettingsDialogs.py:86-89`);
- the control lookup: `_control` (dialog `:155-156`, a plain `getattr`) or `_voiceControl` (`:91-100`, which counts a destroyed wx window as none);
- the source of a driver choice's options: `self._<driver_id>s`, which NVDA's `_updateValueForControl` sets (`VoiceSettingsDialogs.py:245-258`). Only the Voice panel has NVDA-made driver lists. The Speech Pipeline panel builds every control itself from `spec.choices` (`pipelineControls.py:36-42`).

Other callers of `_applyDependencies`, which stay as they are:
- `makeSettings` (dialog `:149`; `VoiceSettingsDialogs.py:40`);
- `_onControllerChange` (dialog `:176-177`; `VoiceSettingsDialogs.py:50-53`);
- `VoiceSettingsDialogs.py:268-270`, after NVDA's `SetValue`/`SetSelection`, which fire no event.

### 4.2 New functions in `pipelineControls.py`

Imports: add `ABSENT` and `dependent_states` to the existing `from .pipeline.panelLayout import (...)` (`pipelineControls.py:13-20`), and `Callable` and `Sequence` from `collections.abc`. Nothing else.

```python
def read_control(spec: Any, control: Any, driver_options: Sequence[str] | None = None) -> Any:
	"""A controller's value as its control shows it, for panelLayout.dependent_states.

	ABSENT without a control (another synth has none). driver_options are the option ids of a
	choice NVDA made for a driver setting, in list order; None for a control WorldVoice made from
	the table, which reads as control_value. No selection reads as None.
	"""
	if control is None:
		return ABSENT
	if driver_options is not None and spec.control == "choice":
		# No selection (-1) names no option, although the list's last option is at -1.
		return selected_value(driver_options, control.GetSelection())
	return control_value(spec, control)


def apply_dependencies(
	specs: Sequence[Any],
	read: Callable[[str], Any],
	control_of: Callable[[Any], Any],
) -> None:
	"""Enable or disable each dependent control of specs from read(controller key).

	control_of(spec) is the panel's control for spec, or None. A dependent with no control, or
	whose controller reads ABSENT, is left alone. Only Enable is called: disabled controls keep
	their values, and onSave still stores them.
	"""
	states = dependent_states(specs, read)
	for spec in specs:
		control = control_of(spec)
		if spec.key in states and control is not None:
			control.Enable(states[spec.key])
```

**Why `read_control` falls back to `control_value` (Q1).**
- Only a checkbox or a choice can be a controller. `check_dependencies` enforces this (`tests/test_settings_table_guard.py:114-121`), and a broken table with a slider controller is in its `BROKEN` cases (`:307-309`). `CHANGE_EVENTS` (`pipelineControls.py:23`) also has events only for those two kinds.
- For those two kinds, `control_value` (`:68-74`) is exactly the body both panels hold today: `selected_value(choice_values(spec), control.GetCurrentSelection())` for a choice, `control.GetValue()` for a checkbox.
- So, for every table that passes the guard, it returns the same value as today's code. The choice branch is then written once.
- `control_value` scales a slider by `from_display`. That branch could only matter for a slider controller, which the guard forbids. It would also be the correct value to compare with `depends_on`, which names a stored value.

**Why the order of the two conditions does not matter.** Today the Voice panel reads `GetSelection()` with options only for `spec.control == "choice" and spec.driver_id is not None`. The new code reads them for `driver_options is not None and spec.control == "choice"`. The Voice panel passes options exactly when `spec.driver_id is not None` (section 4.3). So both conditions select the same specs. A driver checkbox (`punctuation_pause_enabled`) gets `driver_options=[]` and still reads `GetValue()`.

`apply_dependencies` is the loop both panels have today, with the panel's two lookups passed in. It calls `control_of(spec)` once per spec, in table order, as both panels do now.

Module docstring (`pipelineControls.py:1-6`): it changes to say that the module also reads controller controls and applies the table's `depends_on` rules for both panels. It keeps the sentence "No engine driver imports this."

### 4.3 The panels after the change

Speech Pipeline panel (the dialog):

```python
def _readController(self, key):
	(spec,) = [spec for spec in self._specs() if spec.key == key]
	return read_control(spec, self._control(spec))

def _applyDependencies(self):
	apply_dependencies(self._specs(), self._readController, self._control)
```

Voice panel:

```python
def _readController(self, key):
	"""<the current docstring, :60-62, unchanged>"""
	(spec,) = [spec for spec in self._voiceSpecs() if spec.key == key]
	# NVDA's list for a driver setting: the option ids it shows, in order.
	options = None
	if spec.driver_id is not None:
		options = [option.id for option in getattr(self, f"_{spec.driver_id}s", [])]
	return read_control(spec, self._voiceControl(spec), options)

def _applyDependencies(self):
	# Disable rather than hide: NVDA's updateDriverSettings shows every supported
	# control again after a voice change, but never enables or disables one.
	apply_dependencies(self._voiceSpecs(), self._readController, self._voiceControl)
```

- The options list is now built for every driver-setting controller. Before, it was built only for a driver choice, and only after the control was found.
  - `getattr` with a default has no side effect, so this cannot be observed.
  - Today the only driver controllers are `number_mode` (a choice) and `punctuation_pause_enabled` (a checkbox), from `pipeline/settings.py:162-174`, `:227-237` and the `depends_on` entries at `:189`, `:248`, `:258`, `:268`.
- `_onControllerChange`, `_bindControllers`, `_controllerDriverIds` and `_voiceControl` do not change.

Imports that leave:
- the dialog: `ABSENT`, `choice_values`, `dependent_states` and `selected_value` (`:20`, `:22`, `:24`, `:27`). Nothing else in the file uses them. `controller_keys`, `panel_specs`, `pipeline_attribute` and `PIPELINE_PANEL` stay.
- `VoiceSettingsDialogs.py`: `ABSENT`, `choice_values`, `dependent_states` and `selected_value` (`:8`, `:10`, `:13`, `:16`).

Imports added: `apply_dependencies` and `read_control`, to each panel's existing `pipelineControls` import (dialog `:30`; `VoiceSettingsDialogs.py:20`).

## 5. Item 2: `_LOG_LABELS` from the table (D2)

### 5.1 Current code

`_LOG_LABELS` (dialog `:38-57`) has eight literal `_()` calls, each with its own Translators comment, in `LOG_SWITCHES` order. `LOG_SWITCHES` (`pipeline/__init__.py:818-819`) comes from `STAGES` (`:805-815`): `apply_speech_dictionaries`, `number_language`, `number_mode`, `chinesespace_wait_factor`, `item_wait_factor`, `punctuation_wait_factor`, `number_wait_factor`, `speech_viewer`. Its only reader is `LogSettingsPanel.settings` (`:668-670`), as `_LOG_LABELS.get(key, key)`.

Six of the eight msgids are already table strings (`pipeline/settings.py`):

| Log key | Today's msgid (dialog line) | Table string it equals |
| --- | --- | --- |
| `number_language` | "Number language" (`:44`) | `display_name`, `:157` (`label` is "Number &language", `:155`) |
| `number_mode` | "Number mode" (`:46`) | `display_name`, `:170` (`label` is "Number &mode", `:168`) |
| `chinesespace_wait_factor` | "Chinese space wait factor" (`:48`) | `label`, `:224` (no `display_name`) |
| `item_wait_factor` | "Item wait factor" (`:50`) | `label`, `:206` |
| `punctuation_wait_factor` | "Punctuation wait factor" (`:52`) | `label`, `:256` |
| `number_wait_factor` | "Number wait factor" (`:54`) | `label`, `:197` |
| `apply_speech_dictionaries` | "Apply speech dictionaries" (`:42`) | no table entry |
| `speech_viewer` | "Speech viewer" (`:56`) | no table entry |

So the rule is **`spec.display_name or spec.label`**. It gives the exact msgid used today for all six. Nothing needs to be stripped.

`number_language` is an ordering-only entry (`pipeline_config=False`, `:160`). It is therefore missing from `PIPELINE_SETTING_BY_KEY` (`:273-274`). The lookup must use `PIPELINE_SETTINGS`.

### 5.2 New code (the dialog, replacing `:38-57`)

```python
# Labels of the log switches that have no pipeline setting of their own.
_STAGE_LOG_LABELS = {
	# Translators: Label for the pipeline log switch of a speech pipeline stage.
	"apply_speech_dictionaries": _("Apply speech dictionaries"),
	# Translators: Label for the pipeline log switch of a speech pipeline stage.
	"speech_viewer": _("Speech viewer"),
}
# One label per log switch, in LOG_SWITCHES order. A stage named after a pipeline setting uses that
# setting's name: its settings-ring name, else its label (tests keep "&" out of these).
_SETTING_NAMES = {spec.key: spec.display_name or spec.label for spec in PIPELINE_SETTINGS}
_LOG_LABELS = {key: _SETTING_NAMES.get(key) or _STAGE_LOG_LABELS.get(key, key) for key in LOG_SWITCHES}
```

- `LogSettingsPanel.settings` (`:668-670`) changes to `_LOG_LABELS[key]`. The key fallback that `.get(key, key)` gave now lives in the comprehension, so every switch has an entry.
- The dialog already imports `PIPELINE_SETTINGS` (`:29`) and `LOG_SWITCHES` (`:17`). No import is added.
- Precedence: the table first, then the explicit labels, then the key. A test keeps the explicit keys and the table keys disjoint (section 10.4), so the precedence never decides anything.

### 5.3 msgids and translations

- The table strings are translated when `pipeline/settings.py` is imported. It calls `addonHandler.initTranslation()` at `:24`, before the table at `:125`, and uses the same add-on catalog as the dialog (`:36`). Each derived label is therefore `_("<the same msgid>")` with the same catalog, so it gives the same text in every locale.
- No `&` stripping. `display_name` exists precisely for "a name without an accelerator". Stripping `&` at run time would act on the *translated* text: zh_TW translates "Number &language" as "數字語言(&L)" (`addon/locale/zh_TW/LC_MESSAGES/nvda.po:576-577`), and stripping would give "數字語言(L)". A test keeps `&` out of the derived English labels instead (section 10.4). None of the seven catalogs has `&` in its msgstr for the four wait-factor msgids. This was checked with grep over `addon/locale/*/LC_MESSAGES/nvda.po`.
- **The msgid set does not change.** All six msgids keep a `_()` call with a Translators comment in `pipeline/settings.py` (`:156-157`, `:169-170`, `:196-197`, `:205-206`, `:223-224`, `:255-256`). The two stage-only msgids keep theirs in the dialog.
- What changes in the next `scons pot`: those six entries lose the dialog's source reference and the "pipeline log switch" comment. They keep the table's comment.
- No `.po` edit is needed. `msgfmt --check` on the zh_TW catalog is unchanged.
- `tests/test_translator_comments.py` stays green. `CHANGED_LABEL_MSGIDS` (`:44-56`) needs one single-line `_("…")` call with a Translators comment per msgid (`:117-122`). The table provides "Number mode", "Number language" and "Item wait factor", and the dialog still provides "Apply speech dictionaries" and "Speech viewer". `test_zh_tw_catalog_follows_the_labels` (`:146-149`) reads only the catalog.

## 6. Item 3: no `getSynth()` in the UI (D3)

### 6.1 Current code

```python
# SpeechRoleSettingsPanel.makeSettings, dialog :194-221
if worldvoice_synth() is None:
	...  # "not WorldVoice" text, self.disable = True, return
self._manager = getSynth().voice_manager      # :207
synth = getSynth()                            # :209
# set_main_voice (:211-215) and speech_section (:219) use synth.name

# UnicodeDetectionSettingsPanel.makeSettings, dialog :503-516
if worldvoice_synth() is None:
	...
self._manager = getSynth().voice_manager      # :516
```

### 6.2 New code

```python
synth = worldvoice_synth()
if synth is None:
	...  # unchanged
self._manager = synth.voice_manager
```

- Role panel: the `synth = getSynth()` line at `:209` is deleted. The closures keep capturing `synth`, which is now the same object.
- Unicode panel: `synth` is used only for `voice_manager`.
- Delete `from synthDriverHandler import getSynth` (`:13`).

**Why the result is the same object.** `worldvoice_synth()` is `getSynth()` filtered by name (`pipeline/context.py:24-27`). `makeSettings` runs on NVDA's GUI thread, so no synth switch runs between the check and the next statement. Both calls returned the same object, the synth whose `name` is `"WorldVoice"`, so `synth.name` in the closures is unchanged.

`set_main_voice` still asks `worldvoice_synth()` when it runs (`:212`). `onSave` still compares `current.voice_manager is self._manager` (`:476-482`). Neither changes.

## 7. Item 4: `SpeechContext` holds plain values (D4)

### 7.1 Current code

- `pipeline/context.py:3` imports `Any` only for `:15`, `default_voice: Any = None`. `GENERIC_CONTEXT` (`:21`) leaves it `None`.
- `deduplicate_language_command` (`pipeline/__init__.py:627-629`):
  ```python
  # Initial voice / language; a context without a default voice compares None.
  default_voice = ctx.default_voice
  voice_name = default_name = default_voice.name if default_voice is not None else None
  ```
  Note `:630`: `current_language = default_language = ctx.language`. Here the *synth's* language is called `default_language`.
- `lang_cmd_to_voice` (`:673-674`):
  ```python
  lang = cmd.lang or ctx.default_voice.language
  yield SelectVoice(ctx.voice_name_for_language(lang) or ctx.default_voice.name)
  ```
- `SynthDriver.speech_context` (main driver `__init__.py:357-368`) passes `default_voice=manager.defaultVoiceInstance` (`:365`).
- No other reader. `grep -rn "default_voice" addon` finds only these lines.

### 7.2 New shape: two strings (Q4)

`pipeline/context.py`:

```python
@dataclass(frozen=True)
class SpeechContext:
	"""What a pipeline stage may know about the synthesizer that speaks: plain values and lookups."""

	supports_roles: bool
	language: str | None
	number_language: str
	# The name and language of the default voice; None without one.
	default_voice_name: str | None = None
	default_voice_language: str | None = None
	voice_name_for_language: Callable[[str], str | None] = lambda language: None
	# The locale of the voice that speaks a language, as its engine reports it; None without one.
	voice_locale_for_language: Callable[[str], str | None] = lambda language: None
```

- `from typing import Any` (`:3`) is deleted.
- The two new fields take the place of `default_voice`, so the positional order of the fields after them does not change. Every caller passes those by keyword anyway.
- `GENERIC_CONTEXT` (`:21`) is unchanged.

**Why the name is `default_voice_language`, not the review's `default_language`.** `default_language` already names a different thing in `deduplicate_language_command`: the synth's language (`:630`). A field of the same name holding the *voice's* language would invite mixing them up.

**Why two fields, not a frozen `DefaultVoice(name, language)`.**
- Two fields keep `SpeechContext` flat, as its other fields are.
- `GENERIC_CONTEXT` needs no new value.
- No stage reads one field without the context.
- A value object would only bring back "an object that stands for the voice", which is what D4 removes.

### 7.3 Call sites

`deduplicate_language_command` (`:627-629`):
```python
# Initial voice / language; a context without a default voice compares None.
voice_name = default_name = ctx.default_voice_name
```

`lang_cmd_to_voice` (`:673-674`):
```python
lang = cmd.lang or ctx.default_voice_language
yield SelectVoice(ctx.voice_name_for_language(lang) or ctx.default_voice_name)
```

`SynthDriver.speech_context` (main driver `:357-368`):
```python
manager = self._voiceManager
if manager is None:
	return GENERIC_CONTEXT
voice = manager.defaultVoiceInstance
return SpeechContext(
	supports_roles=True,
	language=self.language,
	number_language=self._numlan,
	default_voice_name=voice.name,
	default_voice_language=voice.language,
	voice_name_for_language=manager.getVoiceNameForLanguage,
	voice_locale_for_language=manager.getVoiceLocaleForLanguage,
)
```

### 7.4 Why behaviour is unchanged

- **The same values.** Today the context captures the instance, and the stages read `.name`/`.language` from it later. Those are plain attributes, set once in `VoiceFacade.__init__` from the voice spec (`compat/voiceFacade.py:34-35`). Every engine `Voice` and Neural's `Voice` inherit them through `driver.Voice(VoiceFacade)` (`driver/__init__.py:12`), and none overrides them. `grep` over `driver/*/__init__.py` and `ref/Neural` finds no `name`/`language` property. Reading them when the context is built therefore gives the values the stages read later.
- **When a context is built.** Each stage handler calls `current_context()` once per run (`pipeline/__init__.py:773`), and `speak()` builds one per call (`__init__.py:323`). That is the same number of `speech_context()` calls as today. Each call now adds two attribute reads.
- **Both values come from one instance.** `manager.defaultVoiceName` is `self._defaultVoiceInstance.name` (`voiceManager.py:185-186`). Reading both fields from one `voice` keeps them from the same instance, even if the default voice changes on another thread between two reads.
- **`defaultVoiceInstance` is never `None` here.**
  - The manager sets it to `None` (`voiceManager.py:59`) and then to an instance inside `_initialize` (`:91`), before its constructor returns. Otherwise `__init__` raises (`:68-72`).
  - The setter only assigns an instance (`:193`).
  - The synth assigns `self._voiceManager` only from the finished constructor (`__init__.py:232`), and resets it to `None` only in `terminate` (`:303`).
  - `speech_context()` returns `GENERIC_CONTEXT` for a `None` manager (`:359-360`). So `voice` is never `None` when the attributes are read, and no `None` guard is added (Q5).
- **`GENERIC_CONTEXT`.** `deduplicate_language_command` still compares `None` (`default_voice_name=None`), as before. `lang_cmd_to_voice` used to raise `AttributeError` on `None.language`/`None.name` for a language command; it would now yield `SelectVoice(None)`. That path cannot run:
  - `lang_cmd_to_voice` is called only from `speak()` (`__init__.py:326`);
  - `speak()` returns at once when terminated (`:317-318`);
  - the same `speak()` call reads `self._voiceManager.defaultVoiceName` (`:331`), so a `None` manager fails there first, as today;
  - `pipeline/__init__.py` never calls `lang_cmd_to_voice` (`grep`).

### 7.5 Neural

`ref/Neural` is the external plugin, read-only. Its add-on code is:
- `Neural/__init__.py:1-8`, a `Voice(WorldVoice)` subclass of `synthDrivers.WorldVoice.driver.Voice` that sets `core`, `engine` and `synth_driver_class`;
- `Neural/driver/`, its own SynthDriver and speech API.

`grep -rn "SpeechContext\|default_voice\|speech_context\|current_context\|pipeline" ref/Neural --include=*.py` finds nothing. The plugin never reads the context, so the field change cannot reach it. `tests/test_plugin_voice_contract.py` pins the `driver.Voice` contract, which this phase does not touch.

## 8. Module layers and import direction

```
globalPlugins/WorldVoice/speechSettingsDialog.py ─┐
                                                  ├─► synthDrivers/WorldVoice/pipelineControls.py  (wx layer)
synthDrivers/WorldVoice/VoiceSettingsDialogs.py ──┘            │
          ▲                                                    └─► pipeline/panelLayout.py  (pure layer,
          │                                                                                  no imports)
synthDrivers/WorldVoice/__init__.py (:52 imports the Voice panel)
```

- **No cycle.** The main driver imports the Voice panel (`__init__.py:52`). The Voice panel imports `pipelineControls`, and `pipelineControls` imports `pipeline.panelLayout`, which imports nothing (`panelLayout.py:8-9`). The new code adds only `ABSENT` and `dependent_states` from `panelLayout` to `pipelineControls`. `pipelineControls` must never import the driver package `__init__`, `VoiceSettingsDialogs` or `globalPlugins`. Guard C (section 10.4) enforces this.
- **The dialog reaches the synth package only through modules that do not import the dialog.** These are `pipelineControls`, `pipeline.panelLayout`, `pipeline.settings`, `pipeline.context` and `pipeline` (for `LOG_SWITCHES`), all as today. Item 2 adds no import. Item 3 removes one (`synthDriverHandler`).
- **Phase 31 modules.** `pipeline/numbers.py` and `pipeline/symbols.py` are not touched. Item 4 changes two speak passes in `pipeline/__init__.py` and adds no import there. The phase 31 guards (`tests/test_pipeline_structure.py:40-108`) stay green unchanged.
- **The phase-31-era settings modules.**
  - `panelLayout.py` (pure) keeps `dependent_states` as the one rule and gets no new code.
  - `pipelineControls.py` (wx) gets the two functions that call wx methods, next to `control_value`, which `read_control` reuses.
  - This is the split review §2.4 describes: the rules are testable, and the wx part is as thin as possible.

## 9. Test harness

- **`tests/ui_harness.py` needs no change.** `_pipeline_ui` (`:673-699`) already loads the real `panelLayout.py` and `pipelineControls.py` for both panels and for `load_pipeline_controls` (`:702-707`). The new functions come with the module.
- **`load_settings_dialog` stubs `synthDriverHandler.getSynth` (`:751`).** It must stay, because `pipeline/context.py` imports `getSynth` (`:5`), and `worldvoice_synth()` goes through it.
- **Test namespaces that only exist for the dialog's `getSynth` call are removed:**
  - `tests/test_role_panel.py:130`;
  - `tests/test_unicode_panel.py:59`.
  - These tests use `load_definitions`, which runs the definitions in the namespace the test supplies (`tests/addon_loader.py:53-96`). After the change, a `getSynth` call left in either `makeSettings` would raise `NameError` there. So these two tests then prove that the panels no longer call it.
- **`pipeline_harness.py` constructs no `SpeechContext`** (`grep`). The fake `VoiceManager` in `tests/test_worldvoice_speak.py:75-79` already gives `defaultVoiceInstance` both `name` and `language`, so the real `speech_context()` works with it unchanged.

## 10. Tests

### 10.1 Behaviour that must not change: existing tests, not edited

These tests pin both panels' enable rules end to end. They must pass without edits.

Speech Pipeline panel, `tests/test_settings_panels.py`:
- `:129-136` stored mode (value, number, group, and an unknown mode);
- `:139-150` the mode choice;
- `:153-159` no selection counts as not group;
- `:221-227` only the controllers are bound;
- `:255-…` the disabled group size is saved;
- `:320-325` the pause controls follow the stored switch (4 cases);
- `:328-346` the pause controls follow the switch only;
- `:349-…` the disabled pause controls are saved.

Voice panel, `tests/test_voice_settings_panel.py`:
- `:255-260` pause enabled or disabled;
- `:263-278` toggle, with `Skip` so NVDA still writes the setting;
- `:281-288` a voice switch keeps the controls disabled;
- `:291-305` a settings-ring toggle followed by a voice switch;
- `:307-315` stored mode (4 cases);
- `:318-333` the mode choice, with `Skip`;
- `:336-346` a settings-ring mode change;
- `:349-360` a mode missing from the list (selection -1) counts as not group;
- `:368-377` another synth (ABSENT);
- `:429-475` rebuilds (destroyed windows);
- `:578-601` a non-driver checkbox controller.

Log Record panel: `tests/test_settings_panels.py:475-489`.

Role, Unicode and speak:
- `tests/test_role_panel.py:90-157`;
- `tests/test_role_panel_ui.py`;
- `tests/test_unicode_panel.py`, apart from the namespace keys in section 9;
- `tests/test_worldvoice_speak.py`.

### 10.2 New unit tests for the shared helpers (`tests/test_pipeline_controls.py`)

The real `pipelineControls.py` and the real table come from `load_pipeline_controls`. A small recording fake control records every method call and returns set values. It has separate `GetSelection` and `GetCurrentSelection` results, so a test can tell which one was read; ui_harness's `Control` aliases the two (`ui_harness.py:68-71`).

`read_control`:
1. `test_read_control_without_a_control_is_absent`, parametrized:
   - `punctuation_pause_enabled` without options;
   - `number_mode` without options;
   - `number_mode` with `["none", "value", "number", "group"]`.
   Each returns `ABSENT` (identity with `panelLayout.ABSENT`).
2. `test_read_control_reads_a_checkbox`, `[True, False]`. It returns `GetValue()`.
3. `test_read_control_reads_a_table_choice_by_its_current_selection`. The `scope` spec, with current selection 0 → `"all"`, 1 → `"WorldVoice"`, -1 → `None`. The fake's `GetSelection` returns a different index, and is not called.
4. `test_read_control_reads_a_driver_choice_from_its_options`. Options `["a", "b", "c"]`, with selection 2 → `"c"`, -1 → `None` (not the last option), 3 → `None`. `GetCurrentSelection` is not called.
5. `test_read_control_ignores_driver_options_for_a_checkbox`. `punctuation_pause_enabled` with `driver_options=[]` returns `GetValue()`.

`apply_dependencies`, over the real Voice or Pipeline panel specs:

6. `test_apply_dependencies_enables_dependents_from_their_controller`, parametrized:
   - `number_mode` reads `"group"` → `group_size`'s control gets `Enable(True)`;
   - `number_mode` reads `"value"` → `Enable(False)`.
   The three pause dependents follow `punctuation_pause_enabled` the same way.
7. `test_apply_dependencies_leaves_dependents_of_an_absent_controller_alone`. Every read returns `ABSENT`, and no control records a call.
8. `test_apply_dependencies_counts_no_selection_as_not_expected`. `number_mode` reads `None` → `Enable(False)`.
9. `test_apply_dependencies_skips_a_dependent_without_a_control`. `control_of` returns `None` for `group_size`. There is no error, and the other dependents are still set.
10. `test_apply_dependencies_only_enables_dependents`. Every recorded call is `("Enable", bool)`, made on a dependent. Controllers and non-dependent controls record nothing, and no value setter is called. This covers the review's "a disabled control keeps its value".

### 10.3 Log label tests (`tests/test_pipeline_panels.py`)

11. **`test_log_switch_labels_are_unchanged` (new pin).** `load_settings_dialog(monkeypatch).module._LOG_LABELS` equals this dict, in this order:
    ```python
    {"apply_speech_dictionaries": "Apply speech dictionaries", "number_language": "Number language",
     "number_mode": "Number mode", "chinesespace_wait_factor": "Chinese space wait factor",
     "item_wait_factor": "Item wait factor", "punctuation_wait_factor": "Punctuation wait factor",
     "number_wait_factor": "Number wait factor", "speech_viewer": "Speech viewer"}
    ```
    The test `_` is the identity, so this pins the msgids. Write it first. It is green on `96d6c08` and must stay green.
12. **`test_log_labels_match_stages_and_confspec` (edited, `:26-31`).** It loads `_LOG_LABELS` with `load_definitions(PANELS, {"_LOG_LABELS"}, {"_": …})`. That namespace holds only `_`, so it raises `NameError` once `_LOG_LABELS` reads `PIPELINE_SETTINGS`, `LOG_SWITCHES` and the two helper dicts.
    - Change the label half to read `load_settings_dialog(monkeypatch).module._LOG_LABELS` and keep the key-order assertion.
    - The confspec half (`:29-31`) is unchanged.
    - The real `LOG_SWITCHES` stays pinned to `LOG_SWITCH_ORDER` by `tests/test_pipeline_stages.py:43`.
13. `test_log_labels_follow_the_table_labels` (`:34-45`) is unchanged and stays green.

### 10.4 Structure guards

Each guard must be red before its item is done and green after. The implementer confirms this by running the guard first.

- **Guard A, `tests/test_pipeline_panels.py::test_log_labels_come_from_the_table` (D2).**
  - `set(module._STAGE_LOG_LABELS) == {key for key in LOG_SWITCH_ORDER if key not in table_keys}`, where `table_keys` are the keys of `PIPELINE_SETTINGS`. Explicit labels exist only for stages with no table entry, and cover all of them.
  - For each log key with a table entry: `labels[key] == (spec.display_name or spec.label)` and `"&" not in labels[key]`.
  - AST of the dialog: the msgids of all `_()` calls with a string constant share no element with `{spec.label, spec.display_name}` over the table. On `96d6c08` this intersection is exactly the six labels in section 5.1 (checked for this spec), so a hand copy that comes back fails the guard.
- **Guard B, `tests/test_ui_structure.py::test_panels_apply_dependencies_through_one_path` (D1).**
  - Neither panel module (the dialog, `VoiceSettingsDialogs.py`) refers to `dependent_states`, `ABSENT` or `selected_value`. This covers the `Name` nodes and the import `alias` names (`ast.walk`).
  - Each panel's `_applyDependencies` contains a call to `apply_dependencies` and no `For` node.
  - Each panel's `_readController` contains a call to `read_control`.
  - Use the existing `method()` helper (`test_ui_structure.py:18-21`) for the two classes `SpeechPipelinePanel` and `WorldVoiceVoiceSettingsPanel`.
- **Guard C, `tests/test_ui_structure.py::test_pipeline_controls_imports_only_wx_and_the_layout_rules` (import direction).**
  - Every relative `ImportFrom` in `pipelineControls.py` is `level == 1, module == "pipeline.panelLayout"`.
  - Every absolute import's top package is in `{"wx", "gui", "typing", "collections"}` (`ast.walk`, so a function-level import counts too).
  - It is green before and after; it keeps the direction.
- **Guard D, `tests/test_ui_structure.py::test_settings_ui_asks_for_worldvoice_not_for_the_synth` (D3).**
  - No module in `addon/globalPlugins/WorldVoice/` refers to `getSynth`. This covers `Name`, `Attribute` and import `alias` names, through `ast.walk`.
  - Red on `96d6c08` (`:13`, `:207`, `:209`, `:516`).
- **Guard E, `tests/test_pipeline_structure.py::test_speech_context_holds_only_plain_values` (D4).**
  - The `AnnAssign` field names of `class SpeechContext` in `pipeline/context.py` are exactly `supports_roles`, `language`, `number_language`, `default_voice_name`, `default_voice_language`, `voice_name_for_language` and `voice_locale_for_language`. This is read with the AST, without loading the module.
  - No field annotation mentions `Any`.
  - No `.py` file under `addon/synthDrivers/WorldVoice/` uses `default_voice` as an `Attribute.attr` or as a call keyword. The inner drivers `driver/*/driver/` are excluded.

### 10.5 Test edits for D4

These are the 11 construction sites. Each `default_voice=X` becomes `default_voice_name=X.name, default_voice_language=X.language`, written as literals where `X` is a literal `SimpleNamespace`.

| File | Lines |
| --- | --- |
| `tests/test_pipeline_filters.py` | `:38` (the `ctx` helper, `default`), `:482` (`roles_context`) |
| `tests/test_pipeline_passthrough.py` | `:30` |
| `tests/test_pipeline_voice_lookup.py` | `:19` (the `context` helper), `:58` (`manager.defaultVoiceInstance`, a real manager) |
| `tests/test_pipeline_pause_properties.py` | `:685` |
| `tests/test_pipeline_stages.py` | `:172`, `:189`, `:208`, `:229`, `:254` |

There is also one reader. `tests/test_worldvoice_pipeline_settings.py:205-212` passes `voice = object()` and asserts `context["default_voice"] == voice`. It becomes:
- `voice = SimpleNamespace(name="A:en", language="en")`;
- `assert (context["default_voice_name"], context["default_voice_language"]) == ("A:en", "en")`.

No assertion about stage output changes.

`test_lang_cmd_to_voice_selects_names_and_falls_back` (`test_pipeline_voice_lookup.py:33-44`) keeps pinning both fallbacks:
- `L(None)` → the default voice's language → its role voice;
- `L("xx")` → the default voice's name.

## 11. mutmut

- **`pyproject.toml:38-49`:** add `"addon/synthDrivers/WorldVoice/pipelineControls.py"` to `source_paths`, after `pipeline/panelLayout.py` (Q6).
  - `pipelineControls.py` is loaded from its file by `_pipeline_ui` (`ui_harness.py:693-697`), the same way as `panelLayout.py`, which is already mutated.
  - So `tests/mutation_support.py` names its trampolines by file with no edit (`:24-29`, `:50-59`).
  - The two new functions are undecorated, so mutmut mutates them (phase 31 spec §9).
- **Acceptance for the new helpers:** every mutant of `x_read_control*` and `x_apply_dependencies*` is killed or shown equivalent in the plan's implementation notes.
- **Pre-existing functions** (`make_control`, `control_value`, `control_row`) are mutated for the first time.
  - Record their counts and survivors in the notes as the first `pipelineControls` baseline.
  - Kill a survivor when one assertion in `tests/test_pipeline_controls.py` does it. Otherwise give the reason (for example, a wx style constant the fake ignores).
  - They are not blockers, because their code is not changed in this phase.
- **Speak passes, before and after.** Run `x_deduplicate_language_command*` and `x_lang_cmd_to_voice*` on `96d6c08` (a scratch copy) and on the branch head.
  - The `if … is not None else None` conditional disappears, so the before-count drops by its mutants.
  - Every after-survivor must match a before-survivor of the same kind, or be killed or shown equivalent.
- **No other change.** No other `source_paths` change. `panelLayout.py` is not edited, so it is not re-run.
- **Limits:** at most 3 children, the 3 GB memory guard, and `mutants/` removed afterwards. Confirm the glob names with `mutmut results` first. The prefix is `addon.synthDrivers.WorldVoice.`.

## 12. Test plan and verification

- **Suite.**
  - Baseline, re-run for this spec on `96d6c08` in the worktree: `python3 -m pytest -q -p no:cacheprovider tests`, single process, memory guard at 3 GB MemAvailable. **2346 passed, 0 skipped.**
  - After the phase: **2346 + 24 = 2370 passed, 0 skipped**:
    - section 10.2: 3 + 2 + 3 + 3 + 1 + 2 + 1 + 1 + 1 + 1 = 18;
    - section 10.3: 1 new;
    - guards A–E: 5.
  - The plan fixes the exact number when it writes the tests (for example, if test 6 is also parametrized over the pause switch). No existing test is removed, and none is renamed apart from the edits in sections 10.3 and 10.5.
- **Checks.**
  - `prek run --all-files`: all hooks Passed (ruff `0.16.3`).
  - `git diff --check`: clean.
  - The two protected-path commands of DEVELOPMENT_WORKFLOW.md §7 print nothing.
- **msgids.** Run `xgettext --language=Python --keyword=_ --from-code=UTF-8` over the same file list (`git ls-files 'addon/*.py'`, minus the inner drivers and `script_data.py`) on `96d6c08` and on the branch head.
  - The two msgid sets must be equal.
  - Diff only the `msgid` lines, not the references or comments.
  - `msgfmt --check addon/locale/zh_TW/LC_MESSAGES/nvda.po` passes. The file is unchanged.
- **Behaviour equivalence.** The reviewer checks it with `git diff master...HEAD -- addon/`:
  - Item 1: the two helper bodies are today's panel bodies, with the lookups passed in (section 4). The only semantic step is `read_control` → `control_value`, which is equal for the controller kinds the guard allows.
  - Item 2: the derived dict equals the pinned literal (test 11).
  - Item 3: the same object (section 6.2).
  - Item 4: the same values, read earlier from immutable attributes (section 7.4).

## 13. What users notice, and Windows manual items

Users notice nothing. Nothing they hear or see changes, and there are no new strings, settings, panels or log keys.

No dedicated test build is needed. Linux tests cover each item through the real panel code against the fake wx, and through the real speak passes. The one Windows item is an optional smoke test on the next packaged build. It needs NVDA with WorldVoice, in English and in zh_TW:

1. **Voice panel** (NVDA Settings, Voice, with WorldVoice):
   - Untick "Enable punctuation pause control". The three pause controls are disabled, and the setting is still saved.
   - Set Number mode to group, and Group size is enabled. Set it to value, and Group size is disabled.
   - Switch the voice. The enabled states stay right.
2. **WorldVoice Settings, Speech Pipeline**: the same two rules.
3. **WorldVoice Settings, Log Record**: the eight checkbox labels read exactly as before, in English and in zh_TW (數字語言, 數字模式, 中文空白停頓參數, 項目停頓參數, 標點停頓參數, 數字停頓參數, 套用語音字典, 語音檢視器).
4. **Speech Role and Unicode Detection**: both open with WorldVoice. With another synth, both say "Your current speech synthesizer is not WorldVoice."
5. **Speech** (D4): with automatic language switching on, read a mixed English and Chinese line. It still switches voices and returns to the default voice.

Linux does not verify NVDA's real wx, focus or speech on Windows. The review and the handoff must say so (DEVELOPMENT_WORKFLOW.md §7).

## 14. Risks

| Risk | Mitigation |
| --- | --- |
| `read_control` → `control_value` reads a slider controller in display units differently. | No slider can be a controller (`test_settings_table_guard.py:114-121`, `BROKEN` `:307-309`). Section 4.2 explains why the stored value would be the right one anyway. |
| The Voice panel calls `GetCurrentSelection` instead of `GetSelection` on an NVDA driver list, or the reverse. | Tests 3 and 4 use a fake that returns different indexes for the two. `test_voice_settings_panel.py:349-360` (selection -1) stays. |
| `evt.Skip()` or the destroyed-window rule is lost in the move. | Both stay in the Voice panel (section 4.3). `:263-278` and `:318-333` assert `Skip`, and `:429-475` cover destroyed windows. |
| A derived log label changes text in some locale. | Same msgids, same catalog, no `&` stripping (section 5.3). Pin test 11 covers English, and the xgettext msgid-set check covers the catalog side. |
| `test_log_labels_match_stages_and_confspec` breaks because of its narrow namespace. | Expected. Section 10.3, item 12 says how to edit it. |
| A future log switch is named after a setting whose only label has an accelerator. | Guard A fails on `&`. The fix is a `display_name` on the table entry. |
| `pipelineControls` grows an import that closes a cycle through the main driver. | Guard C. |
| The D4 field rename breaks an external reader of `speech_context()`. | Neural does not read it (section 7.5). The review's §11 risk asks about other user code. There is none in the repo or in `ref/Neural`. If the user has any, it needs the same two-field edit (Q4). |
| D4 reads `name`/`language` when the context is built instead of later. | They are immutable attributes, and both come from one instance (section 7.4). The speak tests (`test_worldvoice_speak.py`) run the real `speech_context()`. |
| The new mutmut file brings many pre-existing survivors. | They are recorded, not blocking (section 11). Only the two new helpers must be clean. |
| A test namespace still provides `getSynth`, which hides a call that came back. | Section 9 removes the two keys. Guard D checks the source. |

## 15. Findings that contradict the review

1. **§3.3 and summary item 4: "`PIPELINE_SETTING_BY_KEY[key].display_name or label`".** `number_language` is an ordering-only entry (`pipeline/settings.py:160`), so it is not in `PIPELINE_SETTING_BY_KEY` (`:273-274`, built from `PIPELINE_STORED_SETTINGS`). The lookup must go through `PIPELINE_SETTINGS`. The review's code sketch does that, but the prose does not.
2. **§3.3 sketch: `spec.label.replace("&", "")`.** It is not needed: every derived label is a `display_name` or an `&`-free `label`. It would also be wrong if it ever took effect, because it runs on the *translated* string: zh_TW "數字語言(&L)" would become "數字語言(L)" (`nvda.po:576-577`). The spec uses `display_name or label`, and Guard A keeps `&` out (section 5.3).
3. **§11 step 2: "`test_pipeline_panels.py:27-28` 不變、應仍綠".** That test loads `_LOG_LABELS` through `load_definitions` with a namespace of only `_` (`:27`). A derived `_LOG_LABELS` raises `NameError` there. The test must change (section 10.3, item 12).
4. **Summary item 5 and §11 step 4: the field name `default_language`.** It collides with the local `default_language = ctx.language` (the synth's language) in `deduplicate_language_command` (`pipeline/__init__.py:630`). The spec uses `default_voice_language`.
5. **§11 step 4: "`speech_context()` 改傳 `manager.defaultVoiceName` 與 `manager.defaultVoiceInstance.language`".** The values are equal in production (`voiceManager.py:185-186`), but the spec reads both from one `manager.defaultVoiceInstance`, so the pair cannot mix two instances (section 7.4). The review's "11 處 `default_voice=`" is correct, but it misses the twelfth test site: the reader at `tests/test_worldvoice_pipeline_settings.py:212`, whose `voice = object()` (`:205`) has neither attribute.
6. **Line numbers after phase 31.** The review cites `pipeline/__init__.py:769-770` and `:814-815` (at `41dc50d`). At `96d6c08` these are `:627-629` and `:673-674`, and `with_order_log`'s `getSynth()` is at `:51`, not `:74`. The panel, context and driver line numbers in the review still match.
7. **§11 step 1, case "停用的控制項保留值" (a disabled control keeps its value).** `apply_dependencies` cannot keep or lose a value itself; wx keeps the value of a disabled control. The testable claim is "only `Enable` is called", and that is test 10. The end-to-end form is already pinned by `test_settings_panels.py:255-…` and `:349-…` (disabled controls are saved).

## 16. Open questions

Each of these is decided by the orchestrator with the recommended default; the user may override it before merge.

- **Q1: `read_control` reuses `control_value`.**
  - The alternative is a verbatim copy of the two branches (choice → `GetCurrentSelection`, else `GetValue()`).
  - Reuse writes the choice read once, and gives the same value for every controller kind the table allows (section 4.2).
- **Q2: the log-label rule is `display_name or label`, with no `&` stripping.** Guard A forbids `&` in derived labels (sections 5.3 and 15.2).
- **Q3: no new `panelLayout` helper for log labels.**
  - The derivation is three module-level lines in the dialog, the only reader.
  - It is pinned by test 11 and Guard A, not mutated, because mutmut does not mutate module-level code.
  - Moving it to `panelLayout.py` would put a Log Record panel rule into the module of the two settings panels' shared rules.
- **Q4: two string fields `default_voice_name` / `default_voice_language`**, not a frozen value, and not the review's `default_language` (section 7.2).
- **Q5: no `None` guard in `speech_context()`.** `defaultVoiceInstance` cannot be `None` there (section 7.4). A guard would be a branch no test could reach in production.
- **Q6: add `pipelineControls.py` to the mutmut `source_paths` permanently.**
  - The new helpers stay under mutation in later maintenance runs.
  - Pre-existing survivors are recorded, not blocking (section 11).
- **Q7: the controller binding and `_onControllerChange` stay in each panel** (section 2).
- **Q8: remove the dead `getSynth` keys from the two `load_definitions` namespaces** (section 9).

## 17. Task estimate

7 tasks, so no batches (fewer than 10). There is one final Fable 5.1 review, as every review in this flow uses Fable 5.1. Each task commits only when the suite is green.

1. **Shared helpers.** Write tests 1–10 (section 10.2); they fail because the names are missing. Add `read_control` and `apply_dependencies` to `pipelineControls.py`, and update its docstring. Green: 2364. Commit.
2. **Panels on the helpers.** Write Guard B (red) and Guard C (green). Switch both panels as in section 4.3, and drop the four imports from each. The section 10.1 tests pass unedited. Green: 2366. Commit.
3. **Log labels.**
   - Write test 11; it is green on the current code.
   - Write Guard A; it is red (the six hand copies).
   - Derive `_LOG_LABELS` (section 5.2), and edit `test_log_labels_match_stages_and_confspec` (section 10.3, item 12).
   - Run the xgettext msgid-set comparison and `msgfmt --check`.
   - Green: 2368. Commit.
4. **`getSynth`.** Write Guard D (red). Edit the two `makeSettings` and the import (section 6.2), and remove the two test namespace keys (section 9). Green: 2369. Commit.
5. **D4.** Write Guard E (red). Edit `context.py`, the two speak passes and `speech_context()` (section 7), the 11 construction sites and the one reader (section 10.5). Green: 2370. Commit.
6. **mutmut.**
   - Run the before-run of the two speak passes on a `96d6c08` scratch copy.
   - Add `pipelineControls.py` to `source_paths`, then run the after-run (section 11).
   - Kill or justify every survivor of the two new helpers and every new survivor in the speak passes, and record the `pipelineControls` baseline.
   - Commit `pyproject.toml` and the plan's implementation notes.
7. **Full verification.** DEVELOPMENT_WORKFLOW.md §7: pytest (the final count from section 12), `prek run --all-files`, `git diff --check` and the protected paths. Then report.

The intermediate counts assume the 18 + 1 + 5 tests of section 12. The plan restates them from its exact parametrization.

Effort: about 3 hours.
- `speechSettingsDialog.py` loses about 25 lines (labels, dependency code, `getSynth`).
- `VoiceSettingsDialogs.py` loses about 12.
- `pipelineControls.py` gains about 35.
- `pipeline/context.py` and `pipeline/__init__.py` stay the same size.
- About 25 test lines change, and about 180 new test lines are added.
