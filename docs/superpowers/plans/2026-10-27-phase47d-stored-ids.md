# Phase 47d Stored Identifiers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).
> 9 tasks, run in one go (fewer than 10, §3.2). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename every identifier WorldVoice stores in an NVDA file (nvda.ini `[WorldVoice]` keys, WorldVoice driver setting ids, gestures.ini script names) to NVDA camelCase without a migration, keep core fields snake_case behind one `stored_key_for` derivation, and end the naming guard with no `TRANSITIONAL_47D` and a check of the stored identifiers.

**Architecture:** Literal identifiers (detection keys, main-locale flags, driver ids, script names) are renamed by `p47d/ren.py` from explicit rule lists, one group per commit, each proven by `p47d/check.py`. The pipeline and log sections, whose stored key today *is* a core field or log key, get a core derivation `stored_key_for` (`pipeline/settings.py`) and a `PipelineSettingSpec.stored_key` property; the repository, `PIPELINE_CONFSPEC`, the stage switches and `LOG_SWITCHES` switch to it in commits whose code change is listed as explicit `EDITS` and whose fixture changes are listed `OLD=NEW` pairs, all proven by `check.py`. Guards then pin the stored identifiers.

**Tech Stack:** Python 3.11 semantics (NVDA 2024.1 floor), pytest, ruff 0.16.3 via prek, AST/tokenize scripts.

**Spec:** `docs/superpowers/specs/2026-10-27-phase47d-stored-ids-design.md`

## Global Constraints

- No migration, no compatibility read of an old key, no changelog line, no readme edit (spec §4, §7).
- Core fields and APIs keep field keys (`PipelineSettings.*`, `update(**changes)`, `depends_on`, `PIPELINE_SETTING_BY_KEY`, `DEFAULT_PIPELINE_SETTINGS`, `PIPELINE_CONFIG_KEYS`, `Stage.log_key`, CSV rows); only nvda.ini keys, driver ids and script names change (spec §3, §5).
- Exceptions stay: `WorldVoice` (section, synth `name`), data keys (voices, engines, role locales), NVDA-defined ids and keys, `uwv`/`numlan`/`nummod`, stored values (spec §3).
- No msgid or `# Translators:` change (spec §7).
- Renames only by `ren.py` from explicit lists, one group per commit, each passing `check.py`; a non-rename change shares a commit with renames only as a listed `EDITS` entry that `check.py` applies (Tasks 5–6); guard entry deletions ride with their rename (deletion only).
- Before each rename, `prescan.py` lists every OLD occurrence repository-wide (addon minus vendored/sonic, tests, readmes, `.po`, `buildVars.py`); each hit is in the group or explained in the ledger.
- Never edit `driver/<Engine>/driver/`, `driver/sonic/`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py`; never add Neural. Engine drivers stay independently installable.
- Formatting per ref/nvda: tabs, line length 110, ruff pinned `0.16.3`.
- git: stage explicit paths, `git diff --cached --stat` before each commit; English `<type>: <summary>` with a body; no `Co-Authored-By`; re-stage after a hook change, never `--no-verify`; no push; never `git stash`; never stage `ref`; new files under `docs/` need `git add -f`.
- Tests serially, or at most 3 workers with a watchdog killing pytest below 3 GB MemAvailable (`p47d/suite.sh` runs serially with the watchdog).

## Review Focus

1. **A pipeline value written under one key and read under another.** `save` maps field → stored key and `load` stored → field; a slip (e.g. `PIPELINE_CONFSPEC` still by field key) makes every save land in an orphan and every read return the default, per profile. Task 5 runs the whole pipeline suite on camelCase fixtures (`tests/test_pipeline_settings_service.py` incl. the per-profile test, `tests/test_config_stub.py`); Task 7 adds `test_repository_reads_and_writes_stored_keys`.
2. **An upgraded profile with the old keys still present.** An old key must neither be read nor block anything: Task 7's `test_old_snake_case_keys_read_as_defaults`, `test_an_old_snake_case_log_switch_does_not_log`, `test_old_pascal_case_keys_are_ignored` (detection), `test_old_pascal_case_flags_are_ignored` (main-locale); configobj tolerance is evidenced in the spec §4 and the ledger.
3. **Voice panel controls named after a driver id.** NVDA names its controls `<id>Slider`/`<id>Checkbox` and the punctuation checkbox enables two dependents found by `driverAttribute`; the `_PipelineSetting` descriptor is installed under the id. Task 2 keeps `tests/test_voice_settings_panel.py` (dependencies, creation order), `tests/test_panel_layout.py`, `tests/test_settings_order.py` and `tests/test_worldvoice_pipeline_settings.py` green on the new ids.
4. **Choice driver settings and NVDA's `available{id.capitalize()}s`.** `numlan`/`nummod` stay lowercase; a future camelCase choice id would silently lose its list. Task 8's `check_stored_names` and its broken case `camel-case choice driver id`; `test_driver_choices_match_the_driver_options` stays green.
5. **The Log Record panel's labels and switches.** A switch named after a setting must still show that setting's name, and the number stage must stay switchable by `numberLanguage`: Task 6 keeps `tests/test_pipeline_panels.py` (log labels), `tests/test_pipeline_filters.py` (switch reads, `also_logged_by`) and `tests/pipeline_harness.py:LOG_SWITCHES` green on the stored switches; the script rename keeps gesture lookup by name green in `tests/test_global_plugin_menu.py` (Task 3).

---

## The rename procedure (Tasks 1–3, 5–6)

Scratch tools (session scratchpad `p47d/`, copied from `p47c/` and extended): `ren.py <repo> <group> [--dry]`, `check.py REV <group> [--verbose]`, `prescan.py <repo> <group>`, `scan.py <repo> NAME[,NAME] [path…]`, `suite.sh`. A group file defines `RENAMES = {path: [rule…]}`, `KEPT = {path: {OLD: count}}` (with a comment giving the reason for each kept occurrence) and, for Tasks 5–6, `EDITS = {path: [(before, after), …]}`.

Extensions over `p47c` (done before Task 1, recorded in the ledger):
- `ren.py` rule `("strings", OLD[, NEW])`: every word occurrence of OLD in the file's string tokens; `EDITS` applied (each `before` exactly once) before the rules.
- `check.py`: applies `EDITS` to REV before comparing; a file may be listed with only `EDITS`.
- `prescan.py`: also greps `readme.md`, `addon/doc/*/readme.md`, `addon/locale/*/LC_MESSAGES/nvda.po`, `buildVars.py`.

For each group:

- [ ] Write the group file from `scan.py` output.
- [ ] Run `prescan.py`; every hit is covered or explained in the ledger.
- [ ] Red: run `ren.py` on the group's test files only (a `--only tests/` filter), then the affected test files → the renamed assertions fail (expected: failures naming the new key/id). Then run `ren.py` on the rest.
- [ ] Green: affected test files pass; `p47d/suite.sh` → the task's expected count, 0 skipped.
- [ ] `git add` the group's paths; `git diff --cached --stat`; commit; `python3 check.py HEAD~1 <group> --verbose` → `pure rename: OK (…)`. Record the line in the ledger. On failure: fix the group, `git reset --soft HEAD~1`, redo.

---

### Task 1: autoLanguageSwitching keys

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/languageDetection/scriptLanguages.py`, `languageDetection/settings.py`, `__init__.py`, `voices/mainLocalePolicy.py`
- Modify (tests): `tests/test_detection_settings.py`, `tests/test_driver_ui_hooks.py`, `tests/test_unicode_panel.py`, `tests/test_worldvoice_speak.py`, `tests/detector_harness.py`, `tests/test_language_detector.py`, `tests/test_script_languages.py`, `tests/test_main_locale_policy.py`, `tests/test_role_presenter.py`, `tests/test_voice_manager_roles.py`, `tests/test_voice_settings_transaction.py`, `tests/runtime_drain_integration_harness.py`, `tests/test_runtime_composition.py`, `tests/test_voice_settings_repository.py`, `tests/test_worldvoice_pipeline_settings.py`, `tests/worldvoice_harness.py` (as the prescan finds)

**Interfaces:**
- Consumes: —
- Produces: stored keys `cjkCharactersLanguage`, `detectLanguageTiming` (group `t1a`); `keepMainLocaleVoiceConsistent`, `keepMainLocaleParameterConsistent`, `keepMainLocaleEngineConsistent` (group `t1b`; the docstring word `KeepMainLocale*` → `keepMainLocale*`)

- [ ] Group `t1a`: `DetectLanguageTiming=detectLanguageTiming`, `CJKCharactersLanguage=cjkCharactersLanguage`, `strings` rules in every file (the spellings occur only as stored keys; `_DetectLanguageTiming*` attributes in `panels/detection.py` are other tokens and stay, `KEPT` empty).
- [ ] Red/green per the procedure; suite → **3318 passed, 0 skipped**; commit `refactor: store the detection keys in camelCase`; `check.py` OK.
- [ ] Group `t1b`: the three flags and `KeepMainLocale=keepMainLocale`, `strings` rules plus comment `text` rules where a docstring/comment names a flag.
- [ ] Red/green; suite → **3318 passed, 0 skipped**; commit `refactor: store the main-locale flags in camelCase`; `check.py` OK.

### Task 2: driver setting ids

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/settings.py`
- Modify (tests): `tests/test_panel_layout.py`, `tests/test_pipeline_panels.py`, `tests/test_pipeline_settings_service.py`, `tests/test_settings_order.py`, `tests/test_worldvoice_pipeline_settings.py`, `tests/test_voice_settings_panel.py`, `tests/test_settings_table_guard.py` (as the prescan finds)

**Interfaces:**
- Consumes: —
- Produces: driver ids `globalWaitFactor`, `numberWaitFactor`, `itemWaitFactor`, `sayAllWaitFactor`, `unspacedScriptSpaceWaitFactor`, `punctuationPauseEnabled`, `removePunctuationCharacters`, `punctuationWaitFactor`; NVDA control names `<id>Slider`/`<id>Checkbox` follow

- [ ] Group `t2`: the eight pairs; plus composite pairs the prescan finds (`globalwaitfactorSlider=globalWaitFactorSlider`, `punctuationpauseenabledCheckbox=punctuationPauseEnabledCheckbox`, `punctuationwaitfactorSlider=punctuationWaitFactorSlider`, `removepunctuationcharactersCheckbox=removePunctuationCharactersCheckbox`) as `strings` and `attr` rules.
- [ ] Red/green; suite → **3318 passed, 0 skipped**; commit `refactor: name the pipeline driver settings in camelCase`; `check.py` OK.

### Task 3: gesture script names

**Files:**
- Modify: `addon/globalPlugins/WorldVoice/__init__.py`, `tests/test_global_plugin_menu.py`, `tests/test_naming_layers.py` (deletion of the two `TRANSITIONAL_47D` entries)

**Interfaces:**
- Consumes: —
- Produces: `GlobalPlugin.script_popupSpeechSettingsDialog`, `GlobalPlugin.script_switchLogRecord`; `TRANSITIONAL_47D` empty

- [ ] Delete both entries from `TRANSITIONAL_47D`; `python3 -m pytest -q tests/test_naming_layers.py` → red: `test_naming_follows_layer` lists exactly the two script names.
- [ ] Group `t3`: `("member", "GlobalPlugin", OLD, NEW)` for both, and the test file's attribute/string occurrences.
- [ ] Green: `tests/test_naming_layers.py tests/test_global_plugin_menu.py` pass; suite → **3318 passed, 0 skipped**; commit `refactor: name the gesture scripts in camelCase`; `check.py` OK (guard deletion only).

### Task 4: the stored-key derivation

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/settings.py`, `tests/test_pipeline_settings_service.py`

**Interfaces:**
- Consumes: —
- Produces: `STORED_WORDS: dict[str, str] = {"sayall": "sayAll"}`; `stored_key_for(name: str) -> str`; `PipelineSettingSpec.stored_key` (property, `stored_key_for(self.key)`)

- [ ] Tests:
  - `test_stored_key_is_nvda_camel_case_of_the_field`, parametrized `("scope", "scope")`, `("number_mode", "numberMode")`, `("sayall_wait_factor", "sayAllWaitFactor")`, `("unspaced_script_space_wait_factor", "unspacedScriptSpaceWaitFactor")`: `module.stored_key_for(field) == stored`.
  - `test_every_entry_reads_its_stored_key_from_the_derivation`: for every spec in `PIPELINE_SETTINGS`, `spec.stored_key == module.stored_key_for(spec.key)`, and `[spec.stored_key for spec in PIPELINE_STORED_SETTINGS]` equals spec §2.1's pipeline column in table order.
- [ ] Red: `python3 -m pytest -q tests/test_pipeline_settings_service.py -k "stored_key or derivation"` → 5 failed (`AttributeError: … stored_key_for`).
- [ ] Implement in `pipeline/settings.py` (spec §5).
- [ ] Green: 5 passed; suite → **3323 passed, 0 skipped**; commit `feat: derive the nvda.ini key of a pipeline setting`.

### Task 5: the pipeline section reads and writes stored keys

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/settings.py` (EDITS), `tests/nvda_stubs.py` (EDITS), and every test fixture naming a pipeline config key (prescan: `tests/test_pipeline_settings_service.py`, `tests/test_pipeline_filters.py`, `tests/test_pipeline_number_edges.py`, `tests/test_pipeline_panels.py`, `tests/test_settings_panels.py`, `tests/test_worldvoice_pipeline_settings.py`, `tests/test_driver_ui_hooks.py`, …)

**Interfaces:**
- Consumes: `PipelineSettingSpec.stored_key`, `stored_key_for` (Task 4)
- Produces: `PIPELINE_CONFSPEC` keyed by stored key; `ConfigPipelineRepository.load()`/`save(values)` mapping field ↔ stored key; `nvda_stubs.worldvoice_conf()` pipeline section keyed by stored key

- [ ] Group `t5`, `EDITS`:
  - `pipeline/settings.py`: `PIPELINE_CONFSPEC = {spec.stored_key: …}`; `load` reads `read_stored(section, spec.stored_key, spec.default)` (`_get_value` goes); `save` writes `section[PIPELINE_SETTING_BY_KEY[key].stored_key] = value`.
  - `tests/nvda_stubs.py`: a helper that executes `STORED_WORDS` and `stored_key_for` from the settings source; the `PIPELINE_CONFSPEC` branch keys by `stored_key_for(<table key>)`.
- [ ] Rules: line-scoped `text` rules (and `kw` rules for `Section(number_mode=…)`) for every fixture string that is a pipeline config key, from the prescan; field-key strings (`getattr(settings, "number_mode")`, `depends_on`, `update(...)` keywords, `PIPELINE_SETTING_BY_KEY[...]`) stay and are counted in `KEPT` with reasons.
- [ ] Red: apply only the test-file rules → the fixture-driven tests fail (stored values not read). Then apply the EDITS.
- [ ] Green: `tests/test_pipeline_settings_service.py tests/test_config_stub.py tests/test_pipeline_filters.py tests/test_pipeline_panels.py tests/test_settings_panels.py tests/test_worldvoice_pipeline_settings.py` pass; suite → **3323 passed, 0 skipped**; commit `refactor: store the pipeline settings under camelCase keys`; `check.py` OK (EDITS + pairs).

### Task 6: the log switches are stored keys

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/registry.py` (EDITS), `addon/globalPlugins/WorldVoice/panels/log.py` (EDITS + strings), `tests/nvda_stubs.py` (EDITS), `tests/pipeline_harness.py` (`LOG_SWITCHES` list), `tests/test_pipeline_filters.py`, `tests/test_pipeline_panels.py`, `tests/test_settings_panels.py`, `tests/test_translator_comments.py` (as the prescan finds)

**Interfaces:**
- Consumes: `stored_key_for` (Task 4)
- Produces: `Stage` handlers reading stored switches; `_run_logged(..., switches=None)` falls back to `(stored_key_for(label),)`; `LOG_SWITCHES` = stored switches in stage order; `_STAGE_LOG_LABELS` keyed `applySpeechDictionaries`/`speechViewer`; `_SETTING_NAMES` keyed by `spec.stored_key`

- [ ] Group `t6`: EDITS for the registry lines and the nvda_stubs log branch; `attr` rule `spec.key → spec.stored_key` on `panels/log.py`'s `_SETTING_NAMES` line, `text` rules for the two label keys; fixture rules for switch keys only (log keys in `STAGE_LOG_KEYS` and CSV assertions stay, `KEPT` with reasons).
- [ ] Red: test rules only → `tests/test_pipeline_panels.py tests/test_pipeline_filters.py` fail on switch names. Then EDITS.
- [ ] Green: those files pass; suite → **3323 passed, 0 skipped**; commit `refactor: store the pipeline log switches under camelCase keys`; `check.py` OK.

### Task 7: old keys are ignored

**Files:**
- Modify (tests only): `tests/test_pipeline_settings_service.py`, `tests/test_pipeline_filters.py`, `tests/test_detection_settings.py`, `tests/test_main_locale_policy.py`

**Interfaces:**
- Consumes: Tasks 1, 5, 6
- Produces: —

- [ ] Tests:
  - `test_repository_reads_and_writes_stored_keys`: conf `{"WorldVoice": {"pipeline": {"numberMode": "group", "sayAllWaitFactor": 30}}}` → `get().number_mode == "group"`, `.sayall_wait_factor == 30`; `update(number_mode="number")` → section `["numberMode"] == "number"` and `"number_mode" not in section`.
  - `test_old_snake_case_keys_read_as_defaults`: conf pipeline `{"number_mode": "group", "global_wait_factor": 50}` → `number_mode == "value"`, `global_wait_factor == 10`; after `update(group_size=4)` the old keys are unchanged and `section["groupSize"] == 4`.
  - `test_an_old_snake_case_log_switch_does_not_log`: log `{"enable": True, "number_mode": True}` at DEBUG → the number stage writes no log row.
  - `test_old_pascal_case_keys_are_ignored` (detection): section with `DetectLanguageTiming="before"`, `CJKCharactersLanguage="zh"` plus the new keys at defaults → `timing == "after"`, `script_language["Han"] == "ja"`.
  - `test_old_pascal_case_flags_are_ignored` (main-locale): flags section with the three old keys set opposite to the new ones → each `enabled` follows the new key.
- [ ] Each passes on first run (characterization). Confirm each catches its bug: in a scratch copy, point the reader back at the old key (e.g. `_TIMING_KEY = "DetectLanguageTiming"`) → the test fails; record in the ledger.
- [ ] Suite → **3328 passed, 0 skipped**; commit `test: pin that the pre-rename keys are ignored`.

### Task 8: guards for the stored identifiers

**Files:**
- Modify: `tests/test_naming_layers.py`, `tests/test_settings_table_guard.py`

**Interfaces:**
- Consumes: Tasks 1–6; `nvda_stubs.worldvoice_conf`, `pipeline_harness.load_synth`, `load_settings_module`
- Produces: `PROPER_NOUN_SECTIONS`, `DATA_SECTIONS`, `NVDA_SETTING_IDS`, `stored_identifier_violations(names)`; `check_stored_names`, `CODED_DRIVER_IDS = {"numlan", "nummod"}`; no `TRANSITIONAL_47D`

- [ ] `tests/test_settings_table_guard.py`: `check_stored_names(specs)` (spec §6) added to `CHECKS`; `BROKEN` gains `"stored key not camel case"` (`_with(m, "group_size", key="Group_size")`), `"driver id other than the stored key"` (`_with(m, "number_wait_factor", driver_id="numberwaitfactor")`), `"camel-case choice driver id"` (`_with(m, "number_mode", driver_id="numberMode")`).
- [ ] Red: before adding to `CHECKS`, run the three `BROKEN` cases with a stub `check_stored_names` returning `[]` → 3 failed; then implement → pass.
- [ ] `tests/test_naming_layers.py`: delete `TRANSITIONAL_47D` and `test_only_stored_identifiers_wait`; `_listed(INTERFACE_NAMES)`; rewrite rule 3 and the closing paragraph of the docstring; rule 2 drops "a stored setting id". Add:
  - `test_stored_identifiers_use_nvda_camel_case(monkeypatch)`: collector of spec §6 → `stored_identifier_violations(...) == []`.
  - `test_the_stored_identifier_check_reports_other_spellings`: `stored_identifier_violations([("x", "DetectLanguageTiming"), ("x", "number_mode"), ("x", "numberMode")])` reports exactly the first two.
  - `test_data_sections_hold_no_defined_keys`: for each `DATA_SECTIONS` name, `worldvoice_conf()["WorldVoice"][name] == {}`.
  - `test_nvda_setting_ids_are_nvdas`: each `NVDA_SETTING_IDS` id occurs as a string literal in `ref/nvda/source/synthDriverHandler.py`, and the synth's standard settings are exactly these ids.
- [ ] Red for the collector: temporarily add `("x", "DetectLanguageTiming")` to its input in a scratch run → reported; record in the ledger.
- [ ] Suite → **3335 passed, 0 skipped** (+4 table guard, +4 naming tests, −1 removed); commit `test: guard the stored identifiers' camelCase`.

### Task 9: verification

**Files:** — (ledger only)

**Interfaces:**
- Consumes: everything
- Produces: the ledger's final section

- [ ] `p47d/suite.sh` → **3335 passed, 0 skipped**.
- [ ] `prek run --all-files` → all Passed; `git diff --check master` → empty.
- [ ] Protected paths: `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py addon/synthDrivers/WorldVoice/unicodeScripts/unspaced_common_data.py` and `git ls-files addon/synthDrivers/WorldVoice/driver/Neural` → both empty.
- [ ] Repository-wide `git grep -n -w` of every OLD string of spec §2.1 (and the composite control names) outside `docs/`; each remaining hit justified in the ledger (field keys, log keys, values, history).
- [ ] Re-run every group's `check.py` against its commit; record the lines.
