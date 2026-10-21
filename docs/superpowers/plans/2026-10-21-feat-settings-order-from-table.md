# Settings Order and Controls from the Pipeline Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** Make `PIPELINE_SETTINGS` the single source of the order, control kind, label, choices and enable rule of every pipeline control, so the NVDA Voice panel, the settings ring and the Speech Pipeline panel all follow the Q1 order and both panels build and enable their controls generically.

**Architecture:** The table in `pipeline/settings.py` gains six fields and the Q1 order, with number language as an ordering-only entry (`pipeline_config=False`). A pure module `pipeline/panelLayout.py` holds every layout rule (panel filter, labels, scale, choices, enable states, Voice-panel anchors, attribute names). A wx module `pipelineControls.py` builds, reads and locates one control from a spec. Both panels loop over the table through these two modules; no setting is named in panel code.

**Tech Stack:** Python 3 (NVDA add-on), wx and NVDA GUI (faked in `tests/ui_harness.py`), pytest 9.1.1, Hypothesis 6.168.5, mutmut 3.8.0, ruff 0.16.3 through prek 0.4.14, gettext `msgfmt`.

**Spec:** `docs/superpowers/specs/2026-10-21-feat-settings-order-from-table-design.md` (commit 8170a18). Decisions: Q1–Q5 and the label rule are the user's (2026-10-21); N1 and N5 were changed by the user on 2026-10-21 (N1 in Task 9, N5 in Tasks 6–7); N2–N4 and N6–N8 stay as the orchestrator's defaults.

**Baseline:** `master` 658f8b9 + spec commit 8170a18: **1938 passed, 0 skipped**, `prek run --all-files` 8 hooks Passed, protected paths clean.

**Batches (DEVELOPMENT_WORKFLOW.md §3.2, 10 tasks → 5 / 5):**
- **Batch 1 = Tasks 1–5** (table, driver, pure layout rules, control builder, Speech Pipeline panel). The boundary sits where the shared modules and the first consumer are done and the Voice panel work starts. Stop, report, wait for the Opus batch review.
- **Batch 2 = Tasks 6–10** (Voice panel placement and rules, order tests, strings, mutmut). Covered by the final Fable review.

## Global Constraints

- Canonical order (Q1): scope, global_wait_factor, ignore_comma_between_number, number_language, number_mode, group_size, group_wait_factor, number_wait_factor, item_wait_factor, sayall_wait_factor, chinesespace_wait_factor, punctuation_pause_enabled, remove_punctuation_characters, punctuation_wait_factor, punctuation_pause_characters. Scope is in the Speech Pipeline panel only; number language in the Voice panel and the ring only.
- One label per setting, sentence case (first word capitalised; `Unicode`, `Chinese`, `WorldVoice` keep their case), `&` accelerators kept. Controls WorldVoice makes get `label + ":"` unless they are checkboxes.
- `panel_scale=10` on `global_wait_factor` (Speech Pipeline panel shows `value // 10`, saves `shown * 10`); every other entry `panel_scale=1`.
- Enable rules only through `depends_on`; disabled controls keep their values and are still saved.
- N5 (changed by the user, 2026-10-21): when the Voice panel's driver is not WorldVoice, the panel creates none of the WorldVoice non-driver controls (group size, punctuation characters) and its `onSave` writes no pipeline setting; the Speech Pipeline panel stays the place to change them. NVDA rebuilds the Voice panel on a synth change (`refreshGui`: `settingsSizer.Clear(delete_windows=True)` then `makeSettings`, `ref/nvda/source/gui/settingsDialogs.py:1633-1646`), so "not created" is the rule; the panel also drops references to controls of an earlier build, and `onSave` checks `_isWorldVoice()` at save time because a panel can be saved before it is rebuilt.
- Stored config keys, values and confspec strings unchanged; `PIPELINE_CONFSPEC` holds the same 14 keys. `numlan` stays an NVDA driver setting with `useConfig=True`.
- No change to `createDriverSettings` (pinned by `tests/test_nvda_settings_copy.py`), to NVDA's branches of `_updateValueForControl`, to `onDiscard`, to `buildVars.py`, or to the readmes.
- Every new or changed `_()` call has a `# Translators:` comment directly above it. zh_TW `nvda.po` only; check with `msgfmt --check`; never commit `.pot` or `.mo`. Other catalogs untouched (N6).
- Never modify `addon/synthDrivers/WorldVoice/driver/<Engine>/driver/`, `driver/sonic/` or `languageDetection/script_data.py`. WorldVoice behaviour lives in core or the outer wrapper.
- Each engine driver stays independently installable: no engine driver imports `pipelineControls` or another driver; shared code lives in core only.
- Never add Neural back to the repo.
- ruff is pinned to `==0.16.3` (`pyproject.toml` `required-version`); the prek hooks run on every commit.
- git: stage explicit paths only and check `git diff --cached --stat` before each commit; commit messages in English, `<type>: <summary>` with a body that says why; no `Co-Authored-By`; if a hook modifies files, restage and commit again, never `--no-verify`; never `git stash`; never push; never touch the main checkout `/workspace/WorldVoice` (reading is fine); never stage the `ref` symlink.
- Deletion: only the implementer's own scratchpad files.
- Resources: one pytest process with a memory guard that stops pytest below 3 GB MemAvailable; mutmut at most 3 workers with the same guard.
- Verification before every commit and at each batch end (DEVELOPMENT_WORKFLOW.md §7): `python3 -m pytest -q tests` (guarded), `prek run --all-files` all Passed, `git diff --check master`, and both protected-path commands print nothing:
  - `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py`
  - `git ls-files addon/synthDrivers/WorldVoice/driver/Neural`
- Expected full-suite counts below are exact for the tests this plan names; skipped stays 0 throughout. A different count gets a `Ruling:` in the ledger.
- The spec's list of tests needing new expectations (spec §11) was found by reading. Each task names the existing tests expected to go red; the implementer confirms them with a real run and rules on any difference.

## Review Focus

1. **Stored values off the panel's grid** (hand-edited `nvda.ini`, e.g. `global_wait_factor=57`): the Speech Pipeline slider shows 5 and Save stores 50, never 57 or 570. → Task 5, `test_pipeline_panel_shows_an_off_grid_global_wait_on_the_grid`.
2. **Group size typed past its bounds** (0 or 42; wx does not stop every typed value): Save stores the clamped 1 or 10. → Task 5, `test_pipeline_panel_saves_an_out_of_range_group_size_clamped`.
3. **Panel rebuild after a synth change** (NVDA `refreshGui` calls `makeSettings` again on the same panel, eSpeak NG → WorldVoice): the new build places Group size after Number mode and the characters after Punctuation wait factor, and the controls named on the panel are the new ones, not windows NVDA destroyed. → Task 6, `test_a_rebuild_for_worldvoice_places_the_controls_again`.
4. **Unicode whitespace in the punctuation characters** (U+3000 ideographic space, U+00A0) typed in the Voice panel: Save stores the characters without it. → Task 7, `test_saving_strips_unicode_whitespace_from_the_characters`.
5. **A voice change after the rows were moved** (`updateDriverSettings(changedSetting="voice")` with the full table): every row and the tab order stay where `makeSettings` put them. → Task 8, `test_voice_panel_rows_and_tab_order_survive_a_voice_change`.

---

## File map

| File | Role | Tasks |
| --- | --- | --- |
| `addon/synthDrivers/WorldVoice/pipeline/settings.py` | the table, choices, derived maps | 1, 2 |
| `addon/synthDrivers/WorldVoice/__init__.py` | driver settings, descriptors, `availableNummods` | 2 |
| `addon/synthDrivers/WorldVoice/pipeline/panelLayout.py` (new) | pure layout rules | 3 |
| `addon/synthDrivers/WorldVoice/pipelineControls.py` (new) | wx control builder | 4 |
| `addon/globalPlugins/WorldVoice/speechSettingsDialog.py` | Speech Pipeline panel; log labels | 5, 9 |
| `addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py` | Voice panel | 6, 7 |
| `addon/locale/zh_TW/LC_MESSAGES/nvda.po` | zh_TW catalog | 9 |
| `pyproject.toml` | mutmut `source_paths` | 10 |
| `tests/test_settings_table_guard.py` (new) | table guard checks | 1, 2, 3 |
| `tests/test_panel_layout.py` (new) | layout unit + property tests | 3 |
| `tests/test_pipeline_controls.py` (new) | control builder tests | 4 |
| `tests/test_settings_order.py` (new) | driver, ring and panel order | 2, 8 |
| `tests/nvda_stubs.py`, `tests/pipeline_harness.py`, `tests/ui_harness.py` | harness | 2, 4, 8 |

---

## Batch 1

### Task 1: The table — new fields, Q1 order, final labels, guard checks

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/settings.py:37-184`
- Create: `tests/test_settings_table_guard.py`
- Modify: `tests/test_pipeline_settings_service.py:26-51`, `:85-92`; `tests/test_worldvoice_pipeline_settings.py:20-41`

**Interfaces:**
- Consumes: nothing new.
- Produces (in `pipeline/settings.py`):
  - `SCOPE_CHOICES: tuple[tuple[str, str], ...] = (("all", _("All Synthesizers (Global)")), ("WorldVoice", _("Only WorldVoice Synthesizer")))`
  - `NUMBER_MODE_CHOICES: tuple[tuple[str, str], ...] = (("value", _("value")), ("number", _("number")), ("group", _("group")))`, defined before `_number_mode`
  - `NUMBER_MODES = tuple(value for value, _label in NUMBER_MODE_CHOICES)`
  - `PipelineSettingSpec` new fields, all defaulted, after `max_value`: `control: str | None = None`, `choices: tuple[tuple[str, str], ...] | None = None`, `depends_on: tuple[str, Any] | None = None`, `panels: tuple[str, ...] = ("voice", "pipeline")`, `panel_scale: int = 1`, `pipeline_config: bool = True`
  - `PIPELINE_STORED_SETTINGS = tuple(spec for spec in PIPELINE_SETTINGS if spec.pipeline_config)`; `PIPELINE_SETTING_BY_KEY`, `DEFAULT_PIPELINE_SETTINGS`, `PIPELINE_CONFIG_KEYS`, `PIPELINE_CONFSPEC` and `ConfigPipelineRepository.load` iterate it.
  - Guard helpers in `tests/test_settings_table_guard.py`: each `check_<rule>(specs) -> list[str]` returns one message per problem.

- [ ] **Step 1: Write the failing guard and order tests**

`tests/test_settings_table_guard.py` loads the module with `load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})` and builds synthetic specs with `module.PipelineSettingSpec(...)` and `dataclasses.replace`. Check functions (spec §10.2 rule numbers):

| check | rule | broken cases (each a param of `test_each_check_reports_a_broken_table`) |
| --- | --- | --- |
| `check_unique` | 1 | duplicate key; duplicate driver_id |
| `check_control_known` | 2 | `control=None` |
| `check_control_matches_kind` | 3 (bool↔checkbox, int↔slider/spin, str↔choice/text) | bool entry with `control="slider"` |
| `check_placement` | 4 | driver entry with `control="spin"`; voice entry without driver_id and `pipeline_config=False` |
| `check_labels_and_panels` | 5 | `label=""`; `panels=("other",)`; driver entry with `panels=("pipeline",)` |
| `check_choices` | 6 (pipeline-panel choice) | no `choices`; duplicate choice values; default not among the values |
| `check_dependencies` | 7 | unknown controller; controller with its own `depends_on`; controller after the dependent; controller missing from a panel of the dependent; slider controller; checkbox controller with expected `"yes"`; choice controller with expected `"pair"` |
| `check_scale` | 8 | `panel_scale=0`; `panel_scale=10` on a checkbox; slider `max_value=95` with `panel_scale=10` |
| `check_voice_anchor` | 10 | first voice entry without driver_id |
| `check_sentence_case` | 12 (label and display_name; `&` ignored) | `"Number &Mode"`; `"number mode"` |

```python
@pytest.mark.parametrize("check", CHECKS)  # the ten checks above
def test_the_table_passes_every_check(module, check):
	assert check(module.PIPELINE_SETTINGS) == []

@pytest.mark.parametrize(("check", "make_broken"), BROKEN)  # the 25 cases above
def test_each_check_reports_a_broken_table(module, check, make_broken):
	assert check(make_broken(module)) != []
```

In `tests/test_pipeline_settings_service.py` add:

```python
def test_table_lists_every_setting_in_the_canonical_order(monkeypatch):
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	assert [spec.key for spec in module.PIPELINE_SETTINGS] == [
		"scope", "global_wait_factor", "ignore_comma_between_number", "number_mode", "group_size",
		"group_wait_factor", "number_wait_factor", "item_wait_factor", "sayall_wait_factor",
		"chinesespace_wait_factor", "punctuation_pause_enabled", "remove_punctuation_characters",
		"punctuation_wait_factor", "punctuation_pause_characters",
	]  # Task 2 inserts "number_language" after "ignore_comma_between_number"
	assert module.NUMBER_MODES == ("value", "number", "group")
```

- [ ] **Step 2: Run them to see them fail**

Run: `python3 -m pytest -q tests/test_settings_table_guard.py tests/test_pipeline_settings_service.py`
Expected: FAIL — the guard tests error with `AttributeError: 'PipelineSettingSpec' object has no attribute 'control'` (or `unexpected keyword argument 'control'` in the broken builders), and the order test fails on the master order.

- [ ] **Step 3: Implement the table in `pipeline/settings.py`**

Rewrite `PIPELINE_SETTINGS` in the Q1 order with spec §5.2's columns (without row 4, number language, which Task 2 adds). Labels and ring names are final here:

| key | control | panels | label | display_name | depends_on |
| --- | --- | --- | --- | --- | --- |
| scope | choice, `choices=SCOPE_CHOICES` | `("pipeline",)` | "Effect scope" | — | — |
| global_wait_factor | slider, `panel_scale=10` | both | "Global wait factor" | — | — |
| ignore_comma_between_number | checkbox | both | "Ignore commas between numbers" | — | — |
| number_mode | choice, `choices=NUMBER_MODE_CHOICES` | both | "Number &mode" | "Number mode" | — |
| group_size | spin | both | "Group size" | — | `("number_mode", "group")` |
| group_wait_factor | slider | both | "Group wait factor" | — | `("number_mode", "group")` |
| number_wait_factor … chinesespace_wait_factor | slider | both | "Number wait factor", "Item wait factor", "Say all wait factor", "Chinese space wait factor" | — | — |
| punctuation_pause_enabled | checkbox | both | "Enable punctuation pause control" | "Punctuation pauses" | — |
| remove_punctuation_characters | checkbox | both | "Remove configured punctuation at pause points" | "Remove punctuation at pause points" | `("punctuation_pause_enabled", True)` |
| punctuation_wait_factor | slider | both | "Punctuation wait factor" | — | `("punctuation_pause_enabled", True)` |
| punctuation_pause_characters | text, `normalize=_strip` | both | "Punctuation pause characters" | — | `("punctuation_pause_enabled", True)` |

Every default, kind, bound, `min_step`, normaliser and `ring` value stays as on master (`group_size` keeps `min_value=1, max_value=10`). The comment at `:78` becomes "Every panel and the settings ring show these settings in this order." Every `_()` call gets a `# Translators:` comment: labels "Label for a pipeline setting in the voice settings panel and the Speech Pipeline panel.", ring names "Label for a setting in synth settings ring.", the choices one comment each (keep the existing group-mode comment text for `"group"`). Add `PIPELINE_STORED_SETTINGS` and build the four derived maps and `load` from it.

- [ ] **Step 4: Run the new tests, then the full suite (the red run of spec §11)**

Run: `python3 -m pytest -q tests/test_settings_table_guard.py tests/test_pipeline_settings_service.py::test_table_lists_every_setting_in_the_canonical_order` → PASS (36 passed).
Run the guarded full suite. Expected: exactly these existing tests fail, because the driver ids and the last stored key follow the new order:
- `test_pipeline_settings_service.py::test_table_drives_fields_defaults_keys_and_confspec`
- `test_pipeline_settings_service.py::test_group_settings_replace_the_pair_wait_and_add_the_size`
- `test_worldvoice_pipeline_settings.py::test_settings_lists_keep_their_order_and_store_pipeline_values_outside_speech_config`

- [ ] **Step 5: Give the three tests their new expectations**

- `test_table_drives_…`: `driver_ids == ["globalwaitfactor", "cni", "nummod", "groupwaitfactor", "numberwaitfactor", "itemwaitfactor", "sayallwaitfactor", "chinesespacewaitfactor", "punctuationpauseenabled", "removepunctuationcharacters", "punctuationwaitfactor"]`; the rest unchanged.
- `test_group_settings_…`: `module.PIPELINE_CONFIG_KEYS[-1] == "punctuation_pause_characters"`.
- `EXPECTED_IDS`: `…, "uwv", "globalwaitfactor", "cni", "numlan", "nummod", "groupwaitfactor", "numberwaitfactor", "itemwaitfactor", "sayallwaitfactor", "chinesespacewaitfactor", "punctuationpauseenabled", "removepunctuationcharacters", "punctuationwaitfactor"`. The `useConfig` check (`:55-57`) is unchanged.

Run the guarded full suite. Expected: **1974 passed, 0 skipped** (1938 + 35 guard params + 1 order test).

- [ ] **Step 6: Verify (§7) and commit**

```bash
git add addon/synthDrivers/WorldVoice/pipeline/settings.py tests/test_settings_table_guard.py tests/test_pipeline_settings_service.py tests/test_worldvoice_pipeline_settings.py
git commit -m "feat: give the pipeline table the canonical order and every control field"
```

### Task 2: Number language as an ordering-only table entry

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/settings.py` (row 4), `addon/synthDrivers/WorldVoice/__init__.py:47`, `:103-155`, `:482-488`, `:511-513`
- Modify: `tests/nvda_stubs.py:91-94`, `tests/pipeline_harness.py:216-239`, `tests/test_runtime_composition.py:613-618`, `tests/test_lint_rewrites.py:9-14`, `tests/test_settings_panels.py:94-108`, `tests/test_pipeline_settings_service.py`, `tests/test_settings_table_guard.py`, `tests/test_worldvoice_pipeline_settings.py`
- Create: `tests/test_settings_order.py`

**Interfaces:**
- Consumes: Task 1's fields, `NUMBER_MODE_CHOICES`, `PIPELINE_STORED_SETTINGS`.
- Produces: table row `PipelineSettingSpec("number_language", str, "default", driver_id="numlan", control="choice", panels=("voice",), label=_("Number &language"), display_name=_("Number language"), pipeline_config=False)`; driver imports `NUMBER_MODE_CHOICES`; `_pipeline_driver_setting(spec)` passes `useConfig=not spec.pipeline_config`; the descriptor loop installs `_PipelineSetting` only for entries with a `driver_id` and `pipeline_config`.

- [ ] **Step 1: Write the failing tests**

- `tests/test_pipeline_settings_service.py`: the order test of Task 1 gains `"number_language"` after `"ignore_comma_between_number"`; new

```python
def test_number_language_is_ordering_only(monkeypatch):
	module = load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})
	assert [s.key for s in module.PIPELINE_SETTINGS if not s.pipeline_config] == ["number_language"]
	for keys in (module.PIPELINE_SETTING_BY_KEY, module.PIPELINE_CONFSPEC, module.PIPELINE_CONFIG_KEYS,
	             [f.name for f in fields(module.PipelineSettings)]):
		assert "number_language" not in keys
	with pytest.raises(KeyError, match="Unknown pipeline setting: number_language"):
		module.pipeline_settings.update(number_language="en")
```
- `tests/test_settings_table_guard.py`: `check_ordering_only` (rule 9 table part: has a driver_id, not in the pipeline panel, named by no `depends_on`) joins `CHECKS`; broken cases: no driver_id; `panels=("voice", "pipeline")`; a `depends_on` naming it. New `test_driver_choices_match_the_driver_options`: for every entry with a `driver_id` and `choices`, `[(key, info.id, info.name) for key, info in driver._get_availableNummods().items()] == [(v, v, label) for v, label in spec.choices]` (driver from `load_definitions(..., members=("_get_availableNummods",))` with `NUMBER_MODE_CHOICES` in the namespace).
- `tests/test_worldvoice_pipeline_settings.py`: `test_number_language_is_a_driver_setting_nvda_stores` — the `numlan` setting has kind `"str"`, label `"Number &language"`, `displayName == "Number language"`, `defaultVal == "default"`, `availableInSettingsRing is True` and no `useConfig=False`; `"numlan" not in vars(synth_class)` (no `_PipelineSetting` replaces the driver's own property).
- `tests/test_settings_order.py` (own small `manager()` helper; test modules never import each other), over `load_synth`:
  - `test_driver_settings_follow_the_table`: ids after `uwv` == `[s.driver_id for s in PIPELINE_SETTINGS if s.driver_id and "voice" in s.panels]` == `["globalwaitfactor", "cni", "numlan", "nummod", "groupwaitfactor", "numberwaitfactor", "itemwaitfactor", "sayallwaitfactor", "chinesespacewaitfactor", "punctuationpauseenabled", "removepunctuationcharacters", "punctuationwaitfactor"]`.
  - `test_ring_follows_the_table_after_the_standard_settings`: `[s.id for s in synth.supportedSettings if s.options.get("availableInSettingsRing")]` == `["uwv", "globalwaitfactor", "numlan", "nummod", "groupwaitfactor", "numberwaitfactor", "itemwaitfactor", "sayallwaitfactor", "chinesespacewaitfactor", "punctuationpauseenabled", "removepunctuationcharacters", "punctuationwaitfactor"]`.
  - `test_ring_names_follow_the_label_rule`: the ring name (`displayName`, else the label without `&`) of those table entries is `{"globalwaitfactor": "Global wait factor", "numlan": "Number language", "nummod": "Number mode", "groupwaitfactor": "Group wait factor", "numberwaitfactor": "Number wait factor", "itemwaitfactor": "Item wait factor", "sayallwaitfactor": "Say all wait factor", "chinesespacewaitfactor": "Chinese space wait factor", "punctuationpauseenabled": "Punctuation pauses", "removepunctuationcharacters": "Remove punctuation at pause points", "punctuationwaitfactor": "Punctuation wait factor"}`.

- [ ] **Step 2: Run them to see them fail**

Run: `python3 -m pytest -q tests/test_pipeline_settings_service.py tests/test_settings_table_guard.py tests/test_worldvoice_pipeline_settings.py tests/test_settings_order.py`
Expected: FAIL — the order test and `test_number_language_is_ordering_only` (no `number_language` entry), the rule-9 broken cases that build a `number_language`-free table still report (they pass), `test_number_language_is_a_driver_setting_nvda_stores` (label `"Number &Language"`, ring name `"Number Language"`), and `test_ring_names_follow_the_label_rule` (`numlan`). `test_driver_choices_match_the_driver_options` and the two other order tests already pass on the Task 1 code: they guard that the driver keeps following the table.

- [ ] **Step 3: Implement**

Add the row to the table (with `# Translators:` comments), then in `__init__.py`: import `NUMBER_MODE_CHOICES`; `useConfig=not spec.pipeline_config`; delete the hard-coded `numlan` block (`:143-154`); build `_get_availableNummods` as `{value: StringParameterInfo(value, label) for value, label in NUMBER_MODE_CHOICES}`; skip `pipeline_config=False` entries in the descriptor loop.

- [ ] **Step 4: Run the red run of spec §11 for this task**

Run the guarded full suite. Expected failures, all from harness namespaces that lack the new name or read the whole table:
- `test_config_stub.py::test_pipeline_defaults_match_the_confspec_the_add_on_registers` (stub reader takes `number_language`)
- every `test_runtime_composition.py` test that loads the driver package (stub lacks `NUMBER_MODE_CHOICES`)
- `test_lint_rewrites.py::test_number_modes_are_a_plain_dict_in_order`
- `test_settings_panels.py::test_number_modes_match_the_driver_and_the_panel`
- the Task 1 version of `test_table_drives_fields_defaults_keys_and_confspec` (`keys` from all entries)

- [ ] **Step 5: Update the harnesses and tests**

- `tests/nvda_stubs.py` `_spread_defaults`: skip a table call whose keywords include `pipeline_config=False`.
- `tests/pipeline_harness.py` `load_synth`: environment gains `"NUMBER_MODE_CHOICES": settings_module.NUMBER_MODE_CHOICES`.
- `tests/test_runtime_composition.py:613-618`: the settings stub gains `NUMBER_MODE_CHOICES=()`.
- `tests/test_lint_rewrites.py` `_driver_methods` and `test_settings_panels.py::test_number_modes_match_…`: the namespace gains `NUMBER_MODE_CHOICES` from the settings module (the panel side, `panel.number_mode_value`, stays until Task 5).
- `test_table_drives_…`: `keys` from `PIPELINE_STORED_SETTINGS`; `driver_ids` gains `"numlan"` after `"cni"`; still one `ring=False` driver entry.

Run the guarded full suite. Expected: **1984 passed, 0 skipped** (+1 ordering-only, +1 rule-9 table, +3 rule-9 broken, +1 driver choices, +1 numlan setting, +3 order).

- [ ] **Step 6: Verify (§7) and commit**

```bash
git add addon/synthDrivers/WorldVoice/pipeline/settings.py addon/synthDrivers/WorldVoice/__init__.py tests/nvda_stubs.py tests/pipeline_harness.py tests/test_runtime_composition.py tests/test_lint_rewrites.py tests/test_settings_panels.py tests/test_pipeline_settings_service.py tests/test_settings_table_guard.py tests/test_worldvoice_pipeline_settings.py tests/test_settings_order.py
git commit -m "feat: place number language in the pipeline table as an ordering-only entry"
```

### Task 3: Pure layout rules (`pipeline/panelLayout.py`)

**Files:**
- Create: `addon/synthDrivers/WorldVoice/pipeline/panelLayout.py`, `tests/test_panel_layout.py`
- Modify: `tests/test_settings_table_guard.py` (rule 11)

**Interfaces:**
- Consumes: the table fields of Tasks 1–2 (read as plain attributes; the module imports no add-on, wx or NVDA module).
- Produces:

```python
VOICE_PANEL = "voice"
PIPELINE_PANEL = "pipeline"
ABSENT = object()  # read() result: this panel has no control for the controller

def panel_specs(specs, panel: str) -> tuple
def label_text(spec) -> str                      # label, plus ":" unless control == "checkbox"
def to_display(spec, value: int) -> int          # value // spec.panel_scale
def from_display(spec, shown: int) -> int        # shown * spec.panel_scale
def choice_values(spec) -> tuple[str, ...]       # the values of spec.choices
def choice_index(values: Sequence[str], value) -> int            # index, else 0
def selected_value(values: Sequence[str], selection: int) -> str | None
def controller_keys(specs) -> frozenset[str]
def dependent_states(specs, read: Callable[[str], Any]) -> dict[str, bool]
def voice_placements(specs, has_row: Callable[[str], bool]) -> list[tuple[str, str | None]]
def pipeline_attribute(spec) -> str  # "_<key>_<suffix>", suffix checkbox|choice|slider|spin|edit
def voice_attribute(spec) -> str     # "<camelKey><Suffix>", Suffix Checkbox|List|Slider|Spin|Edit
def driver_attribute(spec) -> str    # NVDA's name: "<driver_id>Checkbox|Slider|List"
```

`voice_placements` receives the Voice panel's entries (`panel_specs(..., VOICE_PANEL)`) and follows spec §5.4: every anchor is `None` when no driver entry has a row, else the nearest preceding entry with a row. `dependent_states` leaves out a dependent whose controller reads `ABSENT`; `None` never equals an expected value.

- [ ] **Step 1: Write the failing tests** (`tests/test_panel_layout.py`; the module is loaded with `load_source(None, "panel_layout_under_test", WORLDVOICE / "pipeline/panelLayout.py", register=False)`; table tests take the real table from `load_settings_module`)

| test | assertion |
| --- | --- |
| `test_panel_specs_follow_the_table_per_panel` | pipeline keys = Q1 without `number_language`; voice keys = Q1 without `scope` |
| `test_label_text` ×5 (one per control) | checkbox → label; `"Number &mode"` choice → `"Number &mode:"`; slider, spin, text → label + ":" |
| `test_to_display` ×2, `test_from_display` ×2 | scale 10: 57 → 5, 5 → 50; scale 1: identity |
| `test_choice_index` ×3 | `"group"` → 2; `"roman"` → 0; `None` → 0 |
| `test_selected_value` ×6 | 0, 1, 2 → the value; -1, 3, 8 → `None` |
| `test_controller_keys_of_the_table` | `frozenset({"number_mode", "punctuation_pause_enabled"})` |
| `test_dependent_states_follow_the_number_mode` ×4 (`"value"`, `"number"`, `"group"`, `None`) | `group_size` and `group_wait_factor` are `mode == "group"`; the three pause dependents follow the switch read as `True` |
| `test_dependent_states_follow_the_switch` ×2 | the three pause dependents equal the switch |
| `test_absent_controllers_leave_every_control_alone` | read → `ABSENT` for both → `{}` |
| `test_voice_placements_with_every_row` | `[("group_size", "number_mode"), ("punctuation_pause_characters", "punctuation_wait_factor")]` |
| `test_voice_placements_with_no_driver_row` | both anchors `None` |
| `test_voice_placements_skip_a_missing_anchor` | `number_mode` has no row → `("group_size", "number_language")` |
| `test_attribute_names` ×5 | scope `_scope_choice`; global wait `_global_wait_factor_slider` / `globalWaitFactorSlider` / `globalwaitfactorSlider`; cni `…_checkbox` / `ignoreCommaBetweenNumberCheckbox` / `cniCheckbox`; group size `_group_size_spin` / `groupSizeSpin`; characters `_punctuation_pause_characters_edit` / `punctuationPauseCharactersEdit` |
| Hypothesis ×4 over synthetic tables of up to 8 `SimpleNamespace` entries (random `driver_id`, `panels`, `depends_on`, presence sets) | every anchor precedes its entry and has a row; no driver row → every anchor `None`; `dependent_states` never names a key whose controller read `ABSENT`; `selected_value` is `None` exactly outside `0..len-1` |

`tests/test_settings_table_guard.py`: `check_attribute_names` (rule 11: no Voice-panel `voice_attribute` of a non-driver entry equals a `driver_attribute` of a driver entry) joins `CHECKS`; broken case: a non-driver slider with key `"x"` next to a driver slider with `driver_id="x"`.

- [ ] **Step 2: Run to see them fail**

Run: `python3 -m pytest -q tests/test_panel_layout.py tests/test_settings_table_guard.py`
Expected: FAIL — `FileNotFoundError` for `pipeline/panelLayout.py` at collection.

- [ ] **Step 3: Implement `pipeline/panelLayout.py`** with the signatures above.

- [ ] **Step 4: Run to see them pass, then the full suite**

Expected: the two files pass; guarded full suite **2025 passed, 0 skipped** (+39 layout, +2 guard). No existing test changes.

- [ ] **Step 5: Verify (§7) and commit**

```bash
git add addon/synthDrivers/WorldVoice/pipeline/panelLayout.py tests/test_panel_layout.py tests/test_settings_table_guard.py
git commit -m "feat: add the pure layout rules both settings panels follow"
```

### Task 4: Shared control builder (`pipelineControls.py`) and harness loaders

**Files:**
- Create: `addon/synthDrivers/WorldVoice/pipelineControls.py`, `tests/test_pipeline_controls.py`
- Modify: `tests/ui_harness.py:567-576`, `:598-700`

**Interfaces:**
- Consumes: Task 3's `label_text`, `to_display`, `from_display`, `choice_values`, `choice_index`, `selected_value`.
- Produces:

```python
CHANGE_EVENTS: dict[str, Any]  # {"checkbox": wx.EVT_CHECKBOX, "choice": wx.EVT_CHOICE}
def make_control(parent, helper, spec, value) -> wx.Window   # spec §5.5 table
def control_value(spec, control) -> Any   # the value to save; None for a choice with no selection
def control_row(control, spec)            # the checkbox itself, else control.GetContainingSizer()
```
- Harness: `ui_harness._pipeline_ui(monkeypatch, stubs, conf)` replaces `_pipeline_settings`: it loads `synthDrivers.WorldVoice.pipeline.settings`, `synthDrivers.WorldVoice.pipeline.panelLayout` and `synthDrivers.WorldVoice.pipelineControls` and returns the settings module; `load_settings_dialog` and `load_voice_settings_dialogs` call it and expose `env.settings` (the settings module) and `env.controls`. New `load_pipeline_controls(monkeypatch, conf=None)` returns the same env for the builder tests.

- [ ] **Step 1: Write the failing tests** (`tests/test_pipeline_controls.py`, specs from `env.settings.PIPELINE_SETTING_BY_KEY`, a `BoxSizerHelper` over a fresh `Sizer` and a `make_panel(SettingsPanel)` parent)

| test | assertion |
| --- | --- |
| `test_a_checkbox_is_added_as_itself_with_its_value` | `type is CheckBox`, label `"Ignore commas between numbers"`, value `True`, the sizer's item is the checkbox window |
| `test_a_choice_lists_its_labels_and_selects_the_value` ×3 (`"all"`→0, `"WorldVoice"`→1, `"nowhere"`→0) | choices `["All Synthesizers (Global)", "Only WorldVoice Synthesizer"]`, label `"Effect scope:"` |
| `test_a_slider_shows_the_scaled_value_and_range` ×2 | global 30 → value 3, `minValue` 0, `maxValue` 10; number wait 40 → 40, 0..100; label + ":" |
| `test_a_spin_uses_nvdas_select_on_focus_control` | `type is SelectOnFocusSpinCtrl`, `(GetValue(), GetMin(), GetMax()) == (4, 1, 10)`, label `"Group size:"` |
| `test_a_text_edit_holds_the_value` | `TextCtrl`, value `"。，"`, label `"Punctuation pause characters:"` |
| `test_control_value_reads_what_is_saved` ×6 | checkbox, text, slider (global shown 4 → 40), spin, choice (1 → `"WorldVoice"`), choice -1 → `None` |
| `test_control_row_is_the_checkbox_or_its_sizer` ×2 | checkbox → itself; slider → its row sizer |
| `test_change_events_cover_the_controller_kinds` | `CHANGE_EVENTS == {"checkbox": "EVT_CHECKBOX", "choice": "EVT_CHOICE"}` |

- [ ] **Step 2: Run to see them fail**

Run: `python3 -m pytest -q tests/test_pipeline_controls.py`
Expected: FAIL — `ImportError` for `load_pipeline_controls` (then `FileNotFoundError` for `pipelineControls.py` once the loader exists).

- [ ] **Step 3: Implement `pipelineControls.py` and the harness loaders.** `pipelineControls.py` imports `wx`, `from gui import nvdaControls` and `from .pipeline.panelLayout import ...`; no engine driver imports it.

- [ ] **Step 4: Run to see them pass, then the full suite**

Expected: **2042 passed, 0 skipped** (+17). Both panel loaders still load the unchanged panels.

- [ ] **Step 5: Verify (§7) and commit**

```bash
git add addon/synthDrivers/WorldVoice/pipelineControls.py tests/test_pipeline_controls.py tests/ui_harness.py
git commit -m "feat: add one builder for every pipeline settings control"
```

### Task 5: Speech Pipeline panel from the table

**Files:**
- Modify: `addon/globalPlugins/WorldVoice/speechSettingsDialog.py:10`, `:19`, `:113-309`
- Modify: `tests/test_settings_panels.py`, `tests/test_pipeline_panels.py:33-79`, `tests/test_translator_comments.py:41`

**Interfaces:**
- Consumes: `PIPELINE_SETTINGS`, `pipeline_settings`; Task 3's `PIPELINE_PANEL`, `ABSENT`, `panel_specs`, `controller_keys`, `dependent_states`, `pipeline_attribute`, `choice_values`, `selected_value`; Task 4's `CHANGE_EVENTS`, `make_control`, `control_value`.
- Produces on `SpeechPipelinePanel`: `makeSettings(sizer)` (spec §5.6 steps 1–4), `_onControllerChange(event)`, `_applyDependencies()`, `_readController(key)`, `onSave()` (one `update` over the shown stored entries, leaving out a `None` choice). Removed: `_scope_value`, `number_mode_value`, `_selected_number_mode`, `onNumberModeChange`, `onPunctuationPauseEnabledChange`. The attributes stay `_<key>_<suffix>`.

- [ ] **Step 1: Write the failing tests**

`tests/test_settings_panels.py`:
- `test_pipeline_panel_shows_the_stored_settings`: labels `["Effect scope:", "Global wait factor:", "Ignore commas between numbers", "Number &mode:", "Group size:", "Group wait factor:", "Number wait factor:", "Item wait factor:", "Say all wait factor:", "Chinese space wait factor:", "Enable punctuation pause control", "Remove configured punctuation at pause points", "Punctuation wait factor:", "Punctuation pause characters:"]`; the other assertions unchanged.
- `test_number_modes_match_the_driver_and_the_panel`: `list(NUMBER_MODES) == list(driver._get_availableNummods()) == list(choice_values(spec))` and `panel._number_mode_choice.choices == [label for _v, label in spec.choices]`.
- New `test_pipeline_panel_keeps_the_stored_scope_when_nothing_is_selected` ×2 (`"all"`, `"WorldVoice"`; N2): `Select(-1)`, Save → stored scope unchanged.
- New `test_pipeline_panel_global_wait_slider_shows_tens_and_saves_units`: stored 30 → `kwargs` `minValue` 0, `maxValue` 10, value 3; number wait slider `maxValue` 100; `SetValue(4)`, Save → stored 40.
- New `test_pipeline_panel_binds_only_the_controllers`: `[source for _e, _h, source in panel.bindings] == [panel._number_mode_choice, panel._punctuation_pause_enabled_checkbox]`.
- New (Review Focus 1) `test_pipeline_panel_shows_an_off_grid_global_wait_on_the_grid`: stored `global_wait_factor=57` → slider 5; Save untouched → `env.pipeline_settings.get().global_wait_factor == 50`.
- New (Review Focus 2) `test_pipeline_panel_saves_an_out_of_range_group_size_clamped` ×2: spin `SetValue(0)` → stored 1; `SetValue(42)` → stored 10.

`tests/test_pipeline_panels.py::test_pipeline_panel_saves_once_through_the_service` takes `monkeypatch`, builds the panel from `load_settings_dialog(monkeypatch).module` with `object.__new__`, sets the same `Widget`s on the generic attribute names (no `_scope_value` / `number_mode_value`), replaces the module's `pipeline_settings` with the recorder; same expected update dict; the not-`hasattr` list gains `_scope_value`, `number_mode_value`, `_selected_number_mode`, `onNumberModeChange`, `onPunctuationPauseEnabledChange`.

- [ ] **Step 2: Run to see them fail**

Run: `python3 -m pytest -q tests/test_settings_panels.py tests/test_pipeline_panels.py`
Expected: FAIL — the label list (old labels and order); `test_number_modes_match_…` (`choice_values` missing from the test's import, then `number_mode_value` gone after Step 3); the converted save test (`AttributeError: … _scope_value`); the scope -1 case for stored `"all"` (master writes `"WorldVoice"`). The slider, bindings, off-grid and clamp tests already pass on master: they pin master's behaviour through the rewrite.

- [ ] **Step 3: Implement the generic panel.** Drop the `nvdaControls` and `PIPELINE_SETTING_BY_KEY` imports when unused. `_onControllerChange` only applies (panel-level binding, as master).

- [ ] **Step 4: Run the full suite (red run of spec §11)**

Expected failure beyond the edited tests: `test_translator_comments.py::test_group_strings_have_translator_comments` (`"group wait factor:"` no longer found). Set `GROUP_MODE_MSGIDS = ("group", "Group size", "Group wait factor")` (the Voice panel's `"Group size:"` goes in Task 6; Task 9 extends the check).

Expected: **2049 passed, 0 skipped** (+2 scope, +1 slider, +1 bindings, +1 off-grid, +2 clamp; the edited tests add nothing).

- [ ] **Step 5: Verify (§7) and commit**

```bash
git add addon/globalPlugins/WorldVoice/speechSettingsDialog.py tests/test_settings_panels.py tests/test_pipeline_panels.py tests/test_translator_comments.py
git commit -m "feat: build the Speech Pipeline panel from the pipeline table"
```

**Batch 1 end:** run the full verification (§7), record it in the ledger, STOP and report (batch, commits, BASE..HEAD, counts, Rulings). Do not start Task 6 until the orchestrator says so.

---

## Batch 2

### Task 6: Voice panel — generic placement, and no WorldVoice controls for another synth (N5)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py:9`, `:24-31`, `:93-156`
- Modify: `tests/ui_harness.py` (fake `refreshGui`, `Sizer.Clear`), `tests/test_voice_settings_panel.py`
- Modify (docs commit): spec §2, §3.4 note, §5.8 "Another synthesizer", §5.9 "Another synthesizer", §5.10, §6.2, §10.3, §10.6 item 6, §13 N5

**Interfaces:**
- Consumes: Task 3's `VOICE_PANEL`, `panel_specs`, `voice_placements`, `voice_attribute`, `driver_attribute`; Task 4's `make_control`, `control_row`; `env.settings` from Task 4's harness.
- Produces on `WorldVoiceVoiceSettingsPanel`: `_voiceSpecs() -> tuple` (`panel_specs(PIPELINE_SETTINGS, VOICE_PANEL)`, read at call time), `_voiceControl(spec)` (driver entry → `driver_attribute`, else `voice_attribute`; `None` when missing), `_addPipelineControls(settingsSizer) -> None` (spec §5.8; for another synth it creates nothing and sets every non-driver attribute to `None`), `_rowIndex(settingsSizer, row) -> int | None` (first child whose `GetSizer()` or `GetWindow()` is `row`). `makeSettings` calls `_addPipelineControls` in place of the two named helpers, which are deleted; the two named enable-rule binders stay until Task 7. `onSave` writes the two values only when `_isWorldVoice()` is true at save time (Task 7 makes the body generic and keeps the check).
- Harness: fake `Sizer.Clear(delete_windows=False)` empties the sizer and marks every contained control `destroyed = True`; fake `VoiceSettingsPanel.refreshGui()` does what NVDA does on a new settings instance: `sizerDict.clear()`, `settingsSizer.Clear(delete_windows=True)`, `makeSettings(settingsSizer)` (NVDA leaves `lastControl` as it was; so does the fake).

- [ ] **Step 1: Write the failing tests** (synthetic tables patch `env.module.PIPELINE_SETTINGS` with `dataclasses.replace` of real entries, so `pipeline_settings.get()` still has every key)
- `test_a_control_after_a_checkbox_row_lands_after_the_checkbox`: table = (`ignore_comma_between_number` driver checkbox, `punctuation_pause_characters` text, no `depends_on`), driver with `BooleanDriverSetting("cni")` → the edit's row directly follows the `cniCheckbox` window; `edit.tab_after is panel.cniCheckbox`.
- `test_adjacent_non_driver_controls_keep_table_order`: table = (`number_mode` driver, `group_size`, `punctuation_pause_characters`, both without `depends_on`) → order `nummod`, `"Group size:"`, `"Punctuation pause characters:"`; `spin.tab_after is panel.nummodList`; `edit.tab_after is spin`.
- (N5) `test_a_synth_without_pipeline_settings_gets_the_group_size_and_characters_at_the_end` becomes `test_another_synth_gets_no_worldvoice_controls`: `order(panel) == ["voice", "rate", "Automatic language switching (when supported)"]`; `panel.groupSizeSpin is None and panel.punctuationPauseCharactersEdit is None`; `pipeline_snapshot(panel) is None`.
- (N5) `test_another_synth_saves_the_characters_and_cancel_leaves_pipeline_settings_alone` becomes `test_another_synth_saves_and_cancels_without_touching_pipeline_settings`: Save, an outside `update(item_wait_factor=90)`, Cancel → stored characters and group size are the stored defaults, `item_wait_factor == 90`, `base_calls == ["makeSettings", "onSave", "onDiscard"]`.
- (N5) `test_a_rebuild_for_another_synth_drops_the_worldvoice_controls`: open with `Driver(ALL)`, set `panel._driver` to the eSpeak NG-like driver, `panel.refreshGui()` → order as above, both attributes `None`, and the old spin and edit are `destroyed`; then `onSave()` → no pipeline setting changes and `base_calls` ends with `"onSave"` (the orchestrator's case: WorldVoice → `refreshGui` with another synth → save; NVDA reaches `refreshGui` through `onPanelActivated`, `settingsDialogs.py:1229-1245`).
- (N5) `test_saving_after_the_synth_changed_writes_no_pipeline_setting`: open with `Driver(ALL)`, `groupSizeSpin.SetValue(7)`, switch `panel._driver` to eSpeak NG without a rebuild, `onSave()` → stored `group_size` unchanged (3), `base_calls` ends with `"onSave"`.
- (Review Focus 3) `test_a_rebuild_for_worldvoice_places_the_controls_again`: open with the eSpeak NG-like driver, set `panel._driver = Driver(ALL)`, `panel.refreshGui()` → `"Group size:"` follows `nummod`, the characters follow `punctuationwaitfactor`, and `panel.groupSizeSpin` is a live control in the new sizer (`destroyed` not set).

- [ ] **Step 2: Run to see them fail**

Run: `python3 -m pytest -q tests/test_voice_settings_panel.py`
Expected: FAIL — the two synthetic tests (master ignores the table); the three another-synth tests (master appends, enables and saves both controls); `refreshGui` missing from the fake until the harness step, then the eSpeak rebuild still shows both controls. The WorldVoice rebuild test fails only on the missing `refreshGui`; record whether it then passes on master.

- [ ] **Step 3: Implement** the harness additions, then spec §5.8 with the N5 rule, and the `_isWorldVoice()` check in `onSave`.

- [ ] **Step 4: Run the file, then the full suite**

Expected: every other Voice panel test passes unchanged (labels stay `"Group size:"` and `"Punctuation pause characters:"` through `label_text`). `tests/test_pipeline_panels.py::test_voice_panel_saves_the_characters_and_group_size_in_one_update` goes red (it saves with an `"espeak"` driver): give its driver the name `"WorldVoice"` and its recorder a `get` returning the saved state (Task 7 converts it to the harness). Guarded full suite **2054 passed, 0 skipped** (+5: two synthetic, two rebuilds, save after a synth change; the two another-synth tests are edited, not added).

- [ ] **Step 5: Spec docs commit (N5)** — §13 N5 becomes "Decided by the user (2026-10-21): another synth gets none of the WorldVoice non-driver controls in the Voice panel and saves none; the Speech Pipeline panel is the place to change them", with the matching lines in §2, §5.8–5.10, §6.2, §10.3 and §10.6 item 6 (the old wording struck through, "Changed by the user 2026-10-21"). Ledger: `Task 6: Ruling: N5 changed by the user — the Voice panel creates no WorldVoice non-driver control for another synth (NVDA's refreshGui destroys and rebuilds, so not creating is enough; references are dropped and onSave re-checks the synth) — cost if wrong: eSpeak users lose two controls they could set there before`.

- [ ] **Step 6: Verify (§7) and commit**

```bash
git add tests/ui_harness.py tests/test_voice_settings_panel.py tests/test_pipeline_panels.py addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py
git commit -m "feat: place the Voice panel's pipeline controls by table order"
git add docs/superpowers/specs/2026-10-21-feat-settings-order-from-table-design.md
git commit -m "docs: record that another synth gets no WorldVoice controls in the Voice panel"
```

### Task 7: Voice panel — generic enable rules and save

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py:24-91`, `:148-156`, `:220-259`
- Modify: `tests/test_voice_settings_panel.py`, `tests/test_pipeline_panels.py:117-179`

**Interfaces:**
- Consumes: Task 3's `ABSENT`, `controller_keys`, `dependent_states`, `selected_value`, `choice_values`; Task 4's `CHANGE_EVENTS`, `control_value`; Task 6's `_voiceSpecs`, `_voiceControl`.
- Produces: `_bindControllers()`, `_onControllerChange(evt)` (`evt.Skip()` first, then apply), `_applyDependencies()`, `_readController(key)` (spec §5.9 table; a non-driver checkbox controller reads `GetValue()`), `_controllerDriverIds() -> set[str]`. `_updateValueForControl` ends with `if setting.id in self._controllerDriverIds(): self._applyDependencies()` instead of the two special cases. `onSave`: when `_isWorldVoice()`, one `update` over the Voice-panel non-driver stored entries whose control exists (leaving out `None`); then NVDA's `onSave`; then the snapshot for WorldVoice. Removed: `_bindNumberModeChoice`, `_onNumberModeChoice`, `_applyGroupControlsState`, `_bindPunctuationPauseEnabledToggle`, `_onPunctuationPauseEnabledToggle`, `_applyPunctuationPauseControlsState`.

- [ ] **Step 1: Write the failing tests**
- `test_a_non_driver_checkbox_controls_its_dependent`: synthetic table = (`ignore_comma_between_number` driver checkbox, `remove_punctuation_characters` with `driver_id=None`, `punctuation_pause_characters` with `depends_on=("remove_punctuation_characters", True)`), stored remove `False` → edit disabled; `SetValue(True)` + `fire(..., "EVT_CHECKBOX")` → enabled; event skipped.
- `test_the_named_rule_and_placement_helpers_are_gone`: none of the six names above nor `_addGroupSizeControl`, `_addPunctuationPauseCharactersControl` is on the class.
- (Review Focus 4) `test_saving_strips_unicode_whitespace_from_the_characters`: edit `"　。 ！　"` → stored `"。 ！"` (stripped at the ends only).
- `tests/test_pipeline_panels.py`: the two Voice-panel save tests (`…discard_after_apply…`, `…saves_the_characters_and_group_size_in_one_update`) take `monkeypatch`, build from `load_voice_settings_dialogs(monkeypatch).module` with `object.__new__`, a WorldVoice `panel._driver`, `panel.base_calls` shared with the recorder; same expected calls (`[{"punctuation_pause_characters": " .,", "group_size": 5}, "onSave"]`) and the same discard result.

- [ ] **Step 2: Run to see them fail**

Expected: FAIL — the synthetic controller has no binding (`LookupError: nothing handles`); the helpers still exist. The whitespace test passes on master (the service strips); it pins the generic save.

- [ ] **Step 3: Implement** as spec §5.9–5.10, keeping Task 6's `_isWorldVoice()` check.

- [ ] **Step 4: Run the full suite**

Expected: every existing enable-rule test passes unchanged (open, toggle, mode choice, voice switch, ring-then-voice, -1). Guarded full suite **2057 passed, 0 skipped** (+3).

- [ ] **Step 5: Verify (§7) and commit**

```bash
git add addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py tests/test_voice_settings_panel.py tests/test_pipeline_panels.py
git commit -m "feat: apply the Voice panel's enable rules and save from the table"
```

### Task 8: Order tests for both panels

**Files:**
- Modify: `tests/ui_harness.py` (tab-order model), `tests/test_settings_order.py`

**Interfaces:**
- Consumes: Tasks 5–7 panels; Task 3's `panel_specs`, `pipeline_attribute`, `voice_attribute`, `driver_attribute`.
- Produces in `ui_harness`: `SettingsPanel.__init__` sets `self.tab_order = []`; `Control.__init__` appends itself to `parent.tab_order` when the parent has one; `MoveAfterInTabOrder(other)` also moves the control right after `other` in that list; the fake `_createNewControl` calls `control.MoveAfterInTabOrder(self.lastControl)` when there is one (NVDA `settingsDialogs.py:1457-1459`, `:1512-1514`, `:1541-1543`).

- [ ] **Step 1: Write the tests** (a local fake driver listing every table driver id with the NVDA setting class for its `control`)
- `test_voice_panel_rows_follow_the_table`: the table rows of the layout, mapped to keys, == `[s.key for s in panel_specs(PIPELINE_SETTINGS, "voice")]` == the Q1 voice keys.
- `test_voice_panel_tab_order_follows_the_table`: the table controls in `panel.tab_order` == the same order.
- (Review Focus 5) `test_voice_panel_rows_and_tab_order_survive_a_voice_change`: after `updateDriverSettings(changedSetting="voice")` both lists are unchanged.
- `test_pipeline_panel_controls_follow_the_table`: `sizer.controls()` and `panel.tab_order`, mapped through `pipeline_attribute`, == the pipeline keys.

- [ ] **Step 2: Run them**

Run: `python3 -m pytest -q tests/test_settings_order.py`
Expected: PASS once the harness models tab order. Prove they bite: in a scratch copy (a temporary worktree, never `git stash`), drop the `MoveAfterInTabOrder` call in `_addPipelineControls` → the tab-order tests FAIL; swap two table rows → the row tests FAIL. Record both in the ledger.

- [ ] **Step 3: Full suite.** Expected: **2061 passed, 0 skipped** (+4); every existing test still passes with the tab-order model.

- [ ] **Step 4: Verify (§7) and commit**

```bash
git add tests/ui_harness.py tests/test_settings_order.py
git commit -m "test: pin the order of both settings panels to the pipeline table"
```

### Task 9: Strings — log switch labels (N1, changed by the user), zh_TW catalog, translator checks

**Files:**
- Modify: `addon/globalPlugins/WorldVoice/speechSettingsDialog.py:27-38`, `addon/locale/zh_TW/LC_MESSAGES/nvda.po`, `tests/test_translator_comments.py`, `tests/test_pipeline_panels.py`
- Modify (docs commit): `docs/superpowers/specs/2026-10-21-feat-settings-order-from-table-design.md` §2, §7, §12 F1, §13 N1

**Interfaces:**
- Consumes: the final table labels (Tasks 1–2).
- Produces: `_LOG_LABELS` in sentence case, reusing the table msgids — `"Apply speech dictionaries"`, `"Ignore commas between numbers"`, `"Number language"`, `"Number mode"`, `"Chinese space wait factor"`, `"Item wait factor"`, `"Punctuation wait factor"`, `"Number wait factor"`, `"Speech viewer"` — each with a `# Translators:` comment.

- [ ] **Step 1: Write the failing tests**
- `tests/test_translator_comments.py`: `test_changed_label_strings_have_translator_comments` over `("Number &mode", "Number mode", "Number &language", "Number language", "Item wait factor", "Ignore commas between numbers", "Effect scope", "Group size", "Punctuation pause characters", "Apply speech dictionaries", "Speech viewer")`, same rule as the group test (every call found and commented). `test_zh_tw_catalog_follows_the_labels`: every msgid of that tuple has a non-empty `msgstr` in zh_TW `nvda.po`; none of the dead msgids is left (`"Effect Scope:"`, `"Number mode:"`, `"Group size:"`, `"group wait factor:"`, `"global wait factor:"`, `"number wait factor:"`, `"item wait factor:"`, `"sayall wait factor:"`, `"chinese space wait factor:"`, `"punctuation wait factor:"`, `"Punctuation pause characters:"`, `"Number &Language"`, `"Number Language"`, `"Number &Mode"`, `"Number Mode"`, `"Ignore comma between number"`, `"item wait factor"`, `"apply_speech_dictionaries"`, `"chinese space wait factor"`, `"punctuation wait factor"`, `"number wait factor"`, `"speech viewer"`).
- `tests/test_pipeline_panels.py`: `test_log_labels_follow_the_table_labels`: each `_LOG_LABELS` value is sentence case, and for a key in the table it equals the entry's `display_name` or its label without `&`.

- [ ] **Step 2: Run to see them fail** — the log labels are the old ones; the catalog lacks the new msgids and keeps the dead ones.

- [ ] **Step 3: Implement**
- `_LOG_LABELS` as above.
- zh_TW `nvda.po`: add `"Number &mode"` 數字模式(&M), `"Number &language"` 數字語言(&L), `"Item wait factor"` 項目停頓參數, `"Ignore commas between numbers"` 忽略在數字間的逗號, `"Effect scope"` 作用範圍, `"Group size"` 每組位數, `"Punctuation pause characters"` 標點停頓字元, `"Apply speech dictionaries"` 套用語音字典, `"Speech viewer"` 語音檢視器; delete every dead entry listed in Step 1. `"Number mode"`, `"Number language"`, `"Chinese space wait factor"`, `"Number wait factor"`, `"Punctuation wait factor"` already exist.
- `msgfmt --check -o /dev/null addon/locale/zh_TW/LC_MESSAGES/nvda.po` → no output, exit 0. `scons pot` in the worktree → the `.pot` lists exactly the new msgids among the changed ones; leave it uncommitted (git-ignored).

- [ ] **Step 4: Full suite.** Expected: **2064 passed, 0 skipped** (+3).

- [ ] **Step 5: Verify (§7) and commit (two commits)**

```bash
git add addon/globalPlugins/WorldVoice/speechSettingsDialog.py addon/locale/zh_TW/LC_MESSAGES/nvda.po tests/test_translator_comments.py tests/test_pipeline_panels.py
git commit -m "feat: give the log switches the shared labels and update zh_TW"
git add docs/superpowers/specs/2026-10-21-feat-settings-order-from-table-design.md
git commit -m "docs: record that the log switch labels follow the label rule"
```

Ledger: `Task 9: Ruling: log switch labels renamed to sentence case (N1 changed by the user 2026-10-21) — the user's decision replaces the spec's N1 default — cost if wrong: one string revert and catalog entries`.

### Task 10: mutmut on `panelLayout.py` and final verification

**Files:**
- Modify: `pyproject.toml:35-45`, the spec §10.5 (survivor table), tests only if a survivor shows a missing assertion.

- [ ] **Step 1:** Add `"addon/synthDrivers/WorldVoice/pipeline/panelLayout.py"` to `[tool.mutmut] source_paths`.
- [ ] **Step 2:** Run mutmut at most 3 workers with the memory guard (`mutmut run --max-children 3`, guard kills it below 3 GB MemAvailable). Expected: every `panelLayout` mutant killed or listed.
- [ ] **Step 3:** For each survivor: either add the assertion that kills it (test first, red with the mutant applied in a scratch copy, then green) or confirm it is equivalent by running the suite with that mutant applied, and write it in a survivor table in spec §10.5 with its reason.
- [ ] **Step 4:** Full verification (§7). Expected: **2064 + k passed, 0 skipped** (k = killing tests added in Step 3).
- [ ] **Step 5: Commit**

```bash
git add pyproject.toml docs/superpowers/specs/2026-10-21-feat-settings-order-from-table-design.md
git commit -m "test: run mutmut on the panel layout rules"
```

Then report to the orchestrator (no own reviewer; DEVELOPMENT_WORKFLOW.md §3.2).

---

## Self-review (7.0 checklist)

1. **Spec coverage:** §5.1–5.3 → Tasks 1–2; §5.4 → 3; §5.5 → 4; §5.6 → 5; §5.7 → 2 (order follows the table) and 8; §5.8 → 6; §5.9 → 5 (pipeline) and 7 (voice); §5.10 → 5 and 7; §6 → 5, 6, 8 (layout), 2 (ring); §7 → 1, 2, 5, 6, 9; §8 → 1–2 (`PIPELINE_CONFSPEC` keys, `numlan` `useConfig`); §9 mutmut config → 10; §10.1 → 3; §10.2 → 1–3; §10.3 → 4–7; §10.4 → 2 and 8; §10.5 → 3 and 10; §11 → red runs in 1, 2, 5, 7; §10.6 manual items are reported, not run (no packaging in this plan).
2. **Step scan:** every test step names its tests and assertions; every code step names the file, signature and the spec values; no TBD.
3. **Type consistency:** `panelLayout` names (`panel_specs`, `voice_placements`, `pipeline_attribute`, `voice_attribute`, `driver_attribute`, `choice_values`, `ABSENT`) and `pipelineControls` names (`CHANGE_EVENTS`, `make_control`, `control_value`, `control_row`) are used with the same signatures in Tasks 4–8.
4. **Review Focus:** five items, each with a named test in Tasks 5, 5, 6, 7, 8. N5 (changed by the user) is covered by the four another-synth tests of Task 6.
5. **Proportion:** no function body is written out; code blocks are signatures and test assertions only.
