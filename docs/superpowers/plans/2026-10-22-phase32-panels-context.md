# Phase 32 Panels and Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** Give both settings panels one dependency path (`pipelineControls.read_control` / `apply_dependencies`), derive the log-switch labels from the pipeline settings table, drop the UI's `getSynth()` calls, and narrow `SpeechContext.default_voice` to two plain strings, with no change to what NVDA users hear or see.

**Architecture:** Two undecorated functions join `pipelineControls.py` (the wx layer) next to `control_value`, which `read_control` reuses; each panel keeps its spec list, control lookup, NVDA driver option lists, `evt.Skip()` and binding. `_LOG_LABELS` becomes three module-level lines in the dialog over `PIPELINE_SETTINGS` in `LOG_SWITCHES` order, so the six table msgids keep their table `_()` calls and the two stage-only labels keep theirs. `SpeechContext` gets `default_voice_name` / `default_voice_language` in place of `default_voice`, filled from one `defaultVoiceInstance` in `SynthDriver.speech_context()`.

**Tech Stack:** Python 3.14, pytest, mutmut 3.8.0, ruff 0.16.3 via prek 0.4.14, GNU gettext (`xgettext`, `msgfmt`).

**Spec:** `docs/superpowers/specs/2026-10-22-phase32-panels-context-design.md` (commit `b2b22b4`). Its orchestrator defaults Q1–Q8 stand. Line numbers below refer to `96d6c08`.

## Global Constraints

- No user-visible change (spec §2): no new or changed strings, settings, config keys, panels, log keys, enable rules, Tab order or event routing. The msgid set from `xgettext` is identical before and after (spec §12). No `.po` edit; never commit a `.pot`.
- The tests listed in spec §10.1 pass **without edits**. The only edits to existing tests are spec §9 (two `getSynth` namespace keys), §10.3 item 12 (`test_log_labels_match_stages_and_confspec`) and §10.5 (11 `default_voice=` sites and one reader).
- `read_control(spec: Any, control: Any, driver_options: Sequence[str] | None = None) -> Any` and `apply_dependencies(specs: Sequence[Any], read: Callable[[str], Any], control_of: Callable[[Any], Any]) -> None` live in `addon/synthDrivers/WorldVoice/pipelineControls.py`, undecorated. `pipelineControls.py` imports only `typing`, `collections.abc`, `wx`, `gui` and `.pipeline.panelLayout` (spec §4.2, §8). Nothing goes into `panelLayout.py`.
- The controller binding, `_onControllerChange`, `_bindControllers`, `_controllerDriverIds` and `_voiceControl` stay in each panel unchanged (Q7). No mixin or base class.
- Log label rule: `spec.display_name or spec.label`, no `&` stripping (Q2); no `panelLayout` helper for it (Q3).
- `SpeechContext` fields are exactly `supports_roles`, `language`, `number_language`, `default_voice_name`, `default_voice_language`, `voice_name_for_language`, `voice_locale_for_language` (Q4). No `None` guard in `speech_context()` (Q5).
- mutmut: `pipelineControls.py` joins `source_paths` permanently, after `pipeline/panelLayout.py` (Q6); no other `[tool.mutmut]` change.
- Never modify `addon/synthDrivers/WorldVoice/driver/<Engine>/driver/`, `driver/sonic/` or `languageDetection/script_data.py`. Engine drivers stay independently installable (no driver imports another driver's package). Never add Neural back.
- ruff is pinned `==0.16.3`. Every commit runs the prek hooks; if a hook modifies files, restage and recommit; never `--no-verify`. Stage new files, then `prek run --files <them>` before committing.
- git: stage explicit paths only; check `git diff --cached --stat` before each commit. Messages in English, `<type>: <summary>`, with a body that says why. No `Co-Authored-By`. Never `git stash`, never push, never touch `/workspace/WorldVoice` (reading is fine). Never stage `ref`. The plan is committed with `git add -f`.
- Full suite: `python3 -m pytest -q -p no:cacheprovider tests`, single process, under the memory guard (kill when MemAvailable < 3 GB). mutmut: `--max-children 3`, memory guard, scratch clones only, `mutants/` removed afterwards.
- Baseline on `96d6c08`: **2346 passed, 0 skipped**. Target: **2370 passed, 0 skipped**.
- Each task ends with the §7 checks: full suite, `prek run --all-files` all Passed, `git diff --check master`, and both protected-path commands print nothing.

## Review Focus

1. **The synth is switched away, or the Voice panel is rebuilt, while a panel is open** (NVDA's `refreshGui` destroys windows; another synth has no WorldVoice controls). Dependents must be left alone, never raise. Task 1: `test_apply_dependencies_leaves_dependents_of_an_absent_controller_alone`, `test_apply_dependencies_skips_a_dependent_without_a_control`, `test_read_control_without_a_control_is_absent`; Task 2 runs `test_voice_settings_panel.py:368-377` and `:429-475` unedited.
2. **An NVDA driver list that lacks the stored option** (selection -1, or an index past the list after a voice switch). It must read as no selection, so Group size is disabled, never as the list's last option. Task 1: `test_read_control_reads_a_driver_choice_from_its_options` (-1 and 3 → `None`), `test_apply_dependencies_counts_no_selection_as_not_expected`; Task 2 keeps `:349-360` green unedited.
3. **A translated UI (zh_TW and the other six catalogs)**: the eight Log Record labels must read as before, with no stray accelerator such as "(&L)". Task 3: `test_log_switch_labels_are_unchanged`, Guard A's `"&" not in label` check, the `xgettext` msgid-set comparison and `msgfmt --check`.
4. **A non-modal settings dialog that outlives WorldVoice** (an audio device change rebuilds the synth, or the user switches synths while the Speech Role panel is open). The main-voice hook must ask for the current synth when it runs, and the panel must not save to a replaced manager. Task 4: `test_panel_opens_its_presenter_for_the_worldvoice_manager` (namespace without `getSynth`, `current[0] = None` path) and `test_role_panel_does_not_save_to_a_voice_manager_the_synth_replaced`, both unedited apart from the key removal.
5. **The default voice changes between utterances** (settings ring, voice switch, automatic language switching reverting with `lang=None`). The next speak must use the new default name and language; the context must not be cached. Task 5: the edited `test_worldvoice_pipeline_settings.py` reader also replaces `manager.defaultVoiceInstance` and asserts the second `speech_context()` carries the new pair; `test_lang_cmd_to_voice_selects_names_and_falls_back` keeps `L(None)` → default voice's language and `L("xx")` → default voice's name.

---

### Task 1: Shared helpers in `pipelineControls.py`

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipelineControls.py:1-20` (docstring, imports), append the two functions after `control_row`
- Test: `tests/test_pipeline_controls.py`

**Interfaces:**
- Consumes: `panelLayout.ABSENT`, `panelLayout.dependent_states(specs, read) -> dict[str, bool]`, `pipelineControls.control_value(spec, control)`.
- Produces: `read_control(spec, control, driver_options=None) -> Any` and `apply_dependencies(specs, read, control_of) -> None` in `pipelineControls`, plus `ABSENT` and `dependent_states` as module names of `pipelineControls` (from its import).

- [ ] **Step 1: Write tests 1–10 of spec §10.2** in `tests/test_pipeline_controls.py`

A `Recorder` fake: records `(name, *args)` for every method call in `self.calls`; `GetValue`, `GetSelection`, `GetCurrentSelection` return separately set results (constructor keywords `value`, `selection`, `current`). `panelLayout` is `sys.modules["synthDrivers.WorldVoice.pipeline.panelLayout"]` after `load_pipeline_controls`; the pipeline panel specs are `panelLayout.panel_specs(env.settings.PIPELINE_SETTINGS, panelLayout.PIPELINE_PANEL)`; a spec by key is `next(s for s in env.settings.PIPELINE_SETTINGS if s.key == key)`.

```python
@pytest.mark.parametrize(("key", "options"), [
	("punctuation_pause_enabled", None), ("number_mode", None),
	("number_mode", ["none", "value", "number", "group"])])
def test_read_control_without_a_control_is_absent(monkeypatch, key, options):
	assert env.controls.read_control(spec(key), None, options) is panelLayout.ABSENT

@pytest.mark.parametrize("checked", [True, False])
def test_read_control_reads_a_checkbox(...):            # == checked; calls == [("GetValue",)]

@pytest.mark.parametrize(("current", "value"), [(0, "all"), (1, "WorldVoice"), (-1, None)])
def test_read_control_reads_a_table_choice_by_its_current_selection(...):
	control = Recorder(current=current, selection=1 - current)   # GetSelection disagrees
	assert read_control(spec("scope"), control) == value
	assert "GetSelection" not in names(control.calls)

@pytest.mark.parametrize(("selection", "value"), [(2, "c"), (-1, None), (3, None)])
def test_read_control_reads_a_driver_choice_from_its_options(...):
	control = Recorder(selection=selection, current=0)
	assert read_control(spec("number_mode"), control, ["a", "b", "c"]) == value
	assert "GetCurrentSelection" not in names(control.calls)

def test_read_control_ignores_driver_options_for_a_checkbox(...):
	# punctuation_pause_enabled, driver_options=[] -> GetValue() (False), calls == [("GetValue",)]

@pytest.mark.parametrize(("mode", "pause", "enabled"), [("group", True, True), ("value", False, False)])
def test_apply_dependencies_enables_dependents_from_their_controller(...):
	# read = {"number_mode": mode, "punctuation_pause_enabled": pause}.__getitem__
	# controls = {spec.key: Recorder() for spec in pipeline specs}
	# group_size, remove_punctuation_characters, punctuation_wait_factor,
	# punctuation_pause_characters each record exactly [("Enable", enabled)]

def test_apply_dependencies_leaves_dependents_of_an_absent_controller_alone(...):
	# read returns ABSENT for every key -> every control's calls == []

def test_apply_dependencies_counts_no_selection_as_not_expected(...):
	# number_mode reads None, pause reads True -> group_size calls == [("Enable", False)]

def test_apply_dependencies_skips_a_dependent_without_a_control(...):
	# control_of returns None for group_size -> no error; the three pause dependents
	# still record [("Enable", True)] with pause True

def test_apply_dependencies_only_enables_dependents(...):
	# number_mode "group", pause True: every recorded call is ("Enable", <bool>) on a key in
	# {group_size, remove_punctuation_characters, punctuation_wait_factor, punctuation_pause_characters};
	# every other control (controllers included) has calls == []
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_controls.py`
Expected: 18 failed with `AttributeError: module 'synthDrivers.WorldVoice.pipelineControls' has no attribute 'read_control'` (or `apply_dependencies`); the 14 existing tests pass.

- [ ] **Step 3: Implement `read_control` and `apply_dependencies`** in `pipelineControls.py` with the signatures, docstrings and bodies of spec §4.2 (the bodies are fixed copy: the driver-choice branch reads `GetSelection()` with the comment "No selection (-1) names no option, although the list's last option is at -1."; everything else falls back to `control_value`). Add `ABSENT` and `dependent_states` to the `.pipeline.panelLayout` import and `from collections.abc import Callable, Sequence`. Rewrite the module docstring so it says the module also reads controller controls and applies the table's `depends_on` rules for both panels, keeping "No engine driver imports this."

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_controls.py`
Expected: 32 passed.

- [ ] **Step 5: §7 checks and commit**

Full suite: **2364 passed, 0 skipped**. `prek run --all-files` all Passed; `git diff --check master` clean; protected paths empty.
Commit `tests/test_pipeline_controls.py addon/synthDrivers/WorldVoice/pipelineControls.py` as `feat: share the controller read and dependency loop in pipelineControls`.

### Task 2: Both panels on the shared helpers

**Files:**
- Modify: `addon/globalPlugins/WorldVoice/speechSettingsDialog.py:19-30` (imports), `:158-174` (`_readController`, `_applyDependencies`)
- Modify: `addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py:7-20` (imports), `:59-84`
- Test: `tests/test_ui_structure.py`

**Interfaces:**
- Consumes: Task 1's `read_control`, `apply_dependencies`.
- Produces: nothing new; `_readController(key)` and `_applyDependencies()` keep their names and behaviour.

- [ ] **Step 1: Write Guard B and Guard C** in `tests/test_ui_structure.py` (spec §10.4)

```python
VOICE_PANEL = WORLDVOICE / "VoiceSettingsDialogs.py"
PANELS = {DIALOG: "SpeechPipelinePanel", VOICE_PANEL: "WorldVoiceVoiceSettingsPanel"}

def test_panels_apply_dependencies_through_one_path():
	for path, cls in PANELS.items():
		tree = ast.parse(path.read_text(encoding="utf-8"))
		referred = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
			a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
		assert referred & {"dependent_states", "ABSENT", "selected_value"} == set(), path.name
		apply = method(path, cls, "_applyDependencies")
		assert "apply_dependencies" in called_names(apply) and not any(isinstance(n, ast.For) for n in ast.walk(apply))
		assert "read_control" in called_names(method(path, cls, "_readController"))

@pytest.mark.skipif(running_under_mutmut(), reason="mutmut's copy imports mutmut")
def test_pipeline_controls_imports_only_wx_and_the_layout_rules():
	# every relative ImportFrom: level == 1 and module == "pipeline.panelLayout";
	# every absolute import's top package in {"wx", "gui", "typing", "collections"} (ast.walk)
```

`called_names(node)` is the set of `Call.func` `Name.id` values under `node`. Guard C needs the `skipif` from the start: mutmut 3.8.0 injects a trampoline import into every mutated module (phase 31 Ruling, `abc92df`), and Task 6 mutates `pipelineControls.py`.

- [ ] **Step 2: Run the guards**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_ui_structure.py`
Expected: Guard B FAILS on the dialog (`{'ABSENT', 'dependent_states', 'selected_value'}`); Guard C passes; 2 existing tests pass.

- [ ] **Step 3: Switch both panels** to the bodies of spec §4.3. The Voice panel keeps its docstring (`:60-62`) and its "Disable rather than hide" comment; it builds `options` only when `spec.driver_id is not None`. Remove `ABSENT`, `choice_values`, `dependent_states`, `selected_value` from both `panelLayout` imports, and add `apply_dependencies`, `read_control` to each `pipelineControls` import.

- [ ] **Step 4: Run the guards and the unedited enable-rule tests**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_ui_structure.py tests/test_settings_panels.py tests/test_voice_settings_panel.py`
Expected: all pass; `git diff --stat master -- tests/test_settings_panels.py tests/test_voice_settings_panel.py` prints nothing.

- [ ] **Step 5: §7 checks and commit**

Full suite: **2366 passed, 0 skipped**. prek all Passed; diff-check clean; protected paths empty.
Commit `tests/test_ui_structure.py addon/globalPlugins/WorldVoice/speechSettingsDialog.py addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py` as `refactor: apply depends_on rules in both panels through pipelineControls`.

### Task 3: Log labels from the table

**Files:**
- Modify: `addon/globalPlugins/WorldVoice/speechSettingsDialog.py:38-57` (`_LOG_LABELS`), `:668-670` (`LogSettingsPanel.settings`)
- Test: `tests/test_pipeline_panels.py` (new pin, Guard A, edit `:26-31`)

**Interfaces:**
- Consumes: `PIPELINE_SETTINGS`, `LOG_SWITCHES` (already imported by the dialog).
- Produces: module names `_STAGE_LOG_LABELS: dict[str, str]`, `_SETTING_NAMES: dict[str, str]`, `_LOG_LABELS: dict[str, str]` (one entry per `LOG_SWITCHES` key, in that order).

- [ ] **Step 1: Write `test_log_switch_labels_are_unchanged`**: `list(load_settings_dialog(monkeypatch).module._LOG_LABELS.items()) == list(EXPECTED.items())` with the eight-entry dict of spec §10.3 item 11.

- [ ] **Step 2: Run it on the current code**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_panels.py -k unchanged`
Expected: 1 passed (the pin is green before the change).

- [ ] **Step 3: Write Guard A, `test_log_labels_come_from_the_table`** (spec §10.4)

```python
	env = load_settings_dialog(monkeypatch)
	table = {spec.key: spec for spec in env.module.PIPELINE_SETTINGS}
	assert set(env.module._STAGE_LOG_LABELS) == {k for k in LOG_SWITCH_ORDER if k not in table}
	for key in LOG_SWITCH_ORDER:
		if key in table:
			label = env.module._LOG_LABELS[key]
			assert label == (table[key].display_name or table[key].label) and "&" not in label, key
	strings = {spec.label for spec in table.values()} | ({spec.display_name for spec in table.values()} - {None})
	assert dialog_msgids() & strings == set()   # constant first arg of every _() Call in PANELS
```

- [ ] **Step 4: Run Guard A**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_panels.py -k come_from_the_table`
Expected: FAIL with `AttributeError: ... no attribute '_STAGE_LOG_LABELS'`. (With that line skipped the msgid check fails on exactly the six labels of spec §5.1.)

- [ ] **Step 5: Derive `_LOG_LABELS`** with the exact block of spec §5.2 (fixed copy, including both Translators comments), and change `LogSettingsPanel.settings` to `_LOG_LABELS[key]`. Edit `test_log_labels_match_stages_and_confspec` to take `monkeypatch` and read `load_settings_dialog(monkeypatch).module._LOG_LABELS` for the key-order assertion; its confspec half stays.

- [ ] **Step 6: Run the panel tests**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_panels.py tests/test_settings_panels.py tests/test_translator_comments.py`
Expected: all pass, including `test_log_labels_follow_the_table_labels` and `test_settings_panels.py:475-489` unedited.

- [ ] **Step 7: Compare msgids and check the catalog**

In a scratch clone at `96d6c08` and in the worktree, run `xgettext --language=Python --keyword=_ --from-code=UTF-8 -o - <files>` over `git ls-files 'addon/*.py'` minus `addon/synthDrivers/WorldVoice/driver/*/driver/*` and `languageDetection/script_data.py`; extract the `msgid` entries (with their continuation lines) and diff them.
Expected: no difference. `msgfmt --check -o /dev/null addon/locale/zh_TW/LC_MESSAGES/nvda.po` exits 0; `git diff --stat master -- addon/locale` prints nothing. No `.pot` is written into the worktree.

- [ ] **Step 8: §7 checks and commit**

Full suite: **2368 passed, 0 skipped**. prek all Passed; diff-check clean; protected paths empty.
Commit `tests/test_pipeline_panels.py addon/globalPlugins/WorldVoice/speechSettingsDialog.py` as `refactor: derive the log switch labels from the pipeline settings table`.

### Task 4: No `getSynth()` in the settings UI

**Files:**
- Modify: `addon/globalPlugins/WorldVoice/speechSettingsDialog.py:13`, `:194-209` (`SpeechRoleSettingsPanel.makeSettings`), `:503-516` (`UnicodeDetectionSettingsPanel.makeSettings`)
- Modify: `tests/test_role_panel.py:130`, `tests/test_unicode_panel.py:59` (remove the `"getSynth"` keys)
- Test: `tests/test_ui_structure.py`

**Interfaces:**
- Consumes: `worldvoice_synth()` (unchanged).
- Produces: nothing new.

- [ ] **Step 1: Write Guard D, `test_settings_ui_asks_for_worldvoice_not_for_the_synth`**: for every `*.py` in `ADDON / "globalPlugins/WorldVoice"`, the set of `Name.id`, `Attribute.attr` and import `alias.name`/`asname` from `ast.walk` does not contain `"getSynth"` (assert message: the file name).

- [ ] **Step 2: Run it**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_ui_structure.py -k worldvoice_not_for_the_synth`
Expected: FAIL on `speechSettingsDialog.py`.

- [ ] **Step 3: Use the synth `worldvoice_synth()` returned** (spec §6.2): `synth = worldvoice_synth()` then `if synth is None:` in both `makeSettings`; `self._manager = synth.voice_manager`; delete the Role panel's `synth = getSynth()` line and the `from synthDriverHandler import getSynth` import. Remove the two `"getSynth"` namespace keys (spec §9).

- [ ] **Step 4: Run Guard D and the panel tests**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_ui_structure.py tests/test_role_panel.py tests/test_role_panel_ui.py tests/test_unicode_panel.py tests/test_settings_panels.py`
Expected: all pass.

- [ ] **Step 5: §7 checks and commit**

Full suite: **2369 passed, 0 skipped**. prek all Passed; diff-check clean; protected paths empty.
Commit the four files as `refactor: use the synth worldvoice_synth returned in the settings panels`.

### Task 5: `SpeechContext` holds plain values

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/context.py:3`, `:8-18`
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py:627-629`, `:673-674`
- Modify: `addon/synthDrivers/WorldVoice/__init__.py:357-368` (`speech_context`)
- Modify: the 11 sites of spec §10.5 (`tests/test_pipeline_filters.py:38,482`, `tests/test_pipeline_passthrough.py:30`, `tests/test_pipeline_voice_lookup.py:19,58`, `tests/test_pipeline_pause_properties.py:685`, `tests/test_pipeline_stages.py:172,189,208,229,254`) and the reader `tests/test_worldvoice_pipeline_settings.py:205-212`
- Test: `tests/test_pipeline_structure.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `SpeechContext(..., default_voice_name: str | None = None, default_voice_language: str | None = None, ...)`; `default_voice` no longer exists.

- [ ] **Step 1: Write Guard E, `test_speech_context_holds_only_plain_values`** (spec §10.4): the `AnnAssign` target names of `class SpeechContext` in `pipeline/context.py` equal the seven names of Global Constraints, in that order; no annotation contains a `Name`/`Attribute` called `Any`; no `*.py` under `WORLDVOICE` outside `driver/*/driver/` has an `Attribute.attr == "default_voice"` or a `keyword.arg == "default_voice"`.

- [ ] **Step 2: Run it**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_structure.py -k plain_values`
Expected: FAIL on the field list (`default_voice` present).

- [ ] **Step 3: Narrow the context**: `context.py` as spec §7.2 (fields, docstring "What a pipeline stage may know about the synthesizer that speaks: plain values and lookups.", the "name and language of the default voice" comment, `typing.Any` import deleted); the two speak passes as spec §7.3; `speech_context()` reads `voice = manager.defaultVoiceInstance` once and passes `default_voice_name=voice.name, default_voice_language=voice.language`.

- [ ] **Step 4: Edit the test sites** (spec §10.5): each `default_voice=X` → `default_voice_name=…, default_voice_language=…` (literals for a literal `SimpleNamespace`, `X.name`/`X.language` otherwise). The reader becomes `voice = SimpleNamespace(name="A:en", language="en")` and asserts `(context["default_voice_name"], context["default_voice_language"]) == ("A:en", "en")`; then (Review Focus 5) it sets `manager.defaultVoiceInstance = SimpleNamespace(name="B:zh", language="zh")` and asserts the next `speech_context()` gives `("B:zh", "zh")`.

- [ ] **Step 5: Run Guard E and the pipeline and speak tests**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_structure.py tests/test_pipeline_filters.py tests/test_pipeline_passthrough.py tests/test_pipeline_voice_lookup.py tests/test_pipeline_pause_properties.py tests/test_pipeline_stages.py tests/test_worldvoice_pipeline_settings.py tests/test_worldvoice_speak.py`
Expected: all pass; `grep -rn "default_voice\b" addon tests` finds no `default_voice=` keyword or `.default_voice` attribute.

- [ ] **Step 6: §7 checks and commit**

Full suite: **2370 passed, 0 skipped**. prek all Passed; diff-check clean; protected paths empty.
Commit the source and test files as `refactor: pass the default voice's name and language to the pipeline as plain values`.

### Task 6: mutmut

**Files:**
- Modify: `pyproject.toml:38-49` (`source_paths`)
- Modify: this plan (append "## Implementation notes: mutmut")
- Test: `tests/test_pipeline_controls.py` only if a survivor of the two new helpers needs one more assertion

**Interfaces:**
- Consumes: Tasks 1 and 5.
- Produces: the first `pipelineControls` mutmut baseline.

- [ ] **Step 1: Before-run** on a scratch clone at `96d6c08` (`ref` symlinked, memory guard, `--max-children 3`): globs `addon.synthDrivers.WorldVoice.pipeline.x_deduplicate_language_command*` and `addon.synthDrivers.WorldVoice.pipeline.x_lang_cmd_to_voice*`. Confirm the names with `mutmut results --all true` first.
Expected: completes; no timeout, no "suspicious". Record per-function totals and survivors in the ledger.

- [ ] **Step 2: Add `"addon/synthDrivers/WorldVoice/pipelineControls.py"`** to `source_paths` after `pipeline/panelLayout.py`; commit it with the notes in Step 5.

- [ ] **Step 3: After-run** on a scratch clone of the branch head with that change (same limits): the two speak-pass globs plus `addon.synthDrivers.WorldVoice.pipelineControls.x_*`.
Expected: every `x_read_control*` and `x_apply_dependencies*` mutant killed or shown equivalent; speak-pass count drops by the mutants of the removed `if … is not None else None`; every after-survivor matches a before-survivor of the same kind; no timeout, no "suspicious".

- [ ] **Step 4: Kill or justify.** A new-helper survivor gets one assertion in `tests/test_pipeline_controls.py` (confirmed by re-running that mutant: killed) or a written equivalence reason. A `make_control`/`control_value`/`control_row` survivor is killed only when one assertion does it; otherwise its reason is recorded.

- [ ] **Step 5: Notes, §7 checks and commit**

Append "## Implementation notes: mutmut" (versions, commits, per-function before/after table, each survivor with its reason). Full suite: **2370 passed, 0 skipped** (more only if Step 4 added a test). prek all Passed. Remove both clones' `mutants/`.
Commit `pyproject.toml docs/superpowers/plans/2026-10-22-phase32-panels-context.md` (and the test file if changed) as `test: mutate pipelineControls and record its first mutmut baseline`.

### Task 7: Full verification and report

**Files:** none.

**Interfaces:**
- Consumes: Tasks 1–6.
- Produces: the report to the orchestrator.

- [ ] **Step 1: DEVELOPMENT_WORKFLOW.md §7 on the branch head**

Run: the full suite under the guard; `prek run --all-files`; `git diff --check master`; both protected-path commands.
Expected: **2370 passed, 0 skipped** (or Task 6's adjusted count); all hooks Passed; no diff-check output; both protected-path commands print nothing. `git diff --stat master -- addon/locale` prints nothing.

- [ ] **Step 2: Report** to the orchestrator: commits, Rulings, counts, prek, protected-path output, msgid comparison, mutmut summary. State that Windows/NVDA was not verified (spec §13). The orchestrator dispatches the final Fable 5.1 review.
