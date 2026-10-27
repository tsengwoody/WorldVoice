# Phase 43: detection script table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).
> 5 tasks: no batch reviews (§3.2).

**Goal:** Make `languageDetection/scriptLanguages.py` (standard library only) the single source of the detection scripts, their config keys and defaults, derive `DETECTION_CONFSPEC`, `SCRIPT_CONFIG_KEYS` and the Unicode Detection panel's controls from it, and move the detector out of the package `__init__.py` — with no user-visible change.

**Architecture:** `scriptLanguages.py` holds the language tuples, `SCRIPT_LANGUAGES` and `DETECTION_SCRIPTS: tuple[DetectionScript, ...]`. `settings.py` (NVDA config layer) builds the configobj validators from the rows; the dialog (NVDA host layer) keeps its translated labels keyed by script name and iterates the table. `LanguageDetector` moves unchanged to `languageDetection/detector.py`; `languageDetection/__init__.py` becomes empty, so `scriptLanguages` imports by package path without NVDA.

**Tech Stack:** Python 3 (NVDA add-on), pytest, Hypothesis (existing detector properties), ruff `==0.16.3` and add-trailing-comma through prek.

**Spec:** `docs/superpowers/specs/2026-10-27-phase43-detection-script-table-design.md`

**Base:** `master` `85bcf54`; `python3 -m pytest -q tests` → 3247 passed, 0 skipped; `prek run --all-files` all Passed. `docs/` is git-ignored but tracked: stage spec/plan with `git add -f`.

## Global Constraints

- No user-visible change: panel order Latin, CJK, Arabic, Cyrillic, Devanagari, timing; labels/msgids, config keys, defaults, validators and stored values identical; no `.po`, readme or changelog change.
- `DETECTION_SCRIPTS` rows, in order: `("Latin", "latinCharactersLanguage", "en")`, `("Han", "CJKCharactersLanguage", "ja")`, `("Arabic", "arabicCharactersLanguage", "ar")`, `("Cyrillic", "cyrillicCharactersLanguage", "ru")`, `("Devanagari", "devanagariCharactersLanguage", "hi")`. No translated label in the table.
- `scriptLanguages.py` imports only the standard library; `languageDetection/__init__.py` ends empty (0 bytes).
- Naming (refactor9 §6.1): new core names PEP 8 (`DetectionScript`, `DETECTION_SCRIPTS`, `script`, `config_key`, `default_language`); new dialog locals mixedCase. No existing name is renamed.
- No compatibility re-exports; importers move to the new modules.
- Never modify `driver/<Engine>/driver/**`, `driver/sonic/**`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py`. Engine drivers stay independently installable. Never stage Neural or `ref`.
- Formatting follows ref/nvda: tabs, line length 110, ruff pinned `0.16.3`.
- Git: explicit paths only, check `git diff --cached --stat` before each commit; English `<type>: <summary>` with a body saying why; no `Co-Authored-By`; if a hook changes files, stage and commit again, never `--no-verify`; never `git stash`; no push; never touch the main checkout.
- Tests: one pytest process, with the memory guard `$SCRATCH/runtests.sh <worktree> <args>` (kills pytest when MemAvailable < 3 GB).
- Deviations go to `.superpowers/sdd/2026-10-27-phase43-detection-script-table/progress.md` as `Ruling: <decision> — <reason> — <cost if wrong>`.

## Review Focus

1. **A profile with non-default choices** (e.g. Cyrillic `uk`, Devanagari `mr`) must still read and write the same keys after the derivation. Task 2: existing `test_update_writes_the_cyrillic_and_devanagari_keys`, `test_the_shared_service_reads_nvda_config`, plus `test_detection_confspec_and_keys_derive_from_the_table`.
2. **A fresh profile** must get the same defaults — in NVDA's confspec and in the test config stub every other test builds on. Task 2: `test_confspec_and_script_keys_keep_the_stored_names_and_defaults` (unchanged literal pin) and `test_the_config_stub_reads_the_detection_defaults_from_the_table`.
3. **The panel with no voice for a script** (choice disabled, not saved) and the control order users navigate by Tab. Task 3: existing `test_script_without_candidates_is_disabled_and_not_saved`, `test_controls_choices_and_selections`, plus `test_detection_panel_lists_every_table_script`.
4. **Letters of scripts outside the table** (Hebrew, Thai, kana …) must detect as before: the data move must not drop or reorder a candidate. Task 1 Step 5: the moved block compared with the base blob; the full `tests/test_language_detector.py` suite.
5. **Synth start and stop** construct and tear down the detector from its new module. Task 4: `tests/test_worldvoice_lifecycle.py`, `tests/test_runtime_composition.py` (the real `__init__.py`), `tests/test_worldvoice_speak.py`.

---

### Task 1: `scriptLanguages.py` — the language data and the detection script table

**Files:**
- Create: `addon/synthDrivers/WorldVoice/languageDetection/scriptLanguages.py`
- Modify: `addon/synthDrivers/WorldVoice/languageDetection/__init__.py:8-95` (data removed; import added)
- Create: `tests/test_script_languages.py`
- Modify: `tests/detector_harness.py`, `tests/test_language_detector.py:667,718`

**Interfaces:**
- Consumes: base tree.
- Produces: module `languageDetection.scriptLanguages` with `BASIC_LATIN`, `EXTENDED_LATIN`, `ALL_LATIN`, `CYRILLIC`, `ARABIC`, `DEVANAGARI`, `CJK`, `SCRIPT_LANGUAGES: dict[str, tuple[str, ...]]`, `@dataclass(frozen=True) class DetectionScript(script: str, config_key: str, default_language: str)`, `DETECTION_SCRIPTS: tuple[DetectionScript, ...]`. `load_language_detection(...)` result gains `script_languages` (the module).

- [ ] **Step 1: Write the failing tests** in `tests/test_script_languages.py` (load the module with `load_source(monkeypatch, "script_languages_under_test", WORLDVOICE / "languageDetection/scriptLanguages.py")`):
  - `test_script_languages_import_only_the_standard_library` — skip under mutmut like `tests/test_pipeline_structure.py:57`; every `Import`/`ImportFrom` node has level 0 and a top-level module in `sys.stdlib_module_names`.
  - `test_detection_scripts_keep_the_stored_names_and_defaults` — `[(s.script, s.config_key, s.default_language) for s in module.DETECTION_SCRIPTS] ==` the five rows of Global Constraints, in order; `dataclasses.fields` names `["script", "config_key", "default_language"]`.
  - `test_every_detection_script_has_candidates_and_a_candidate_default` — for each row, `row.script in module.SCRIPT_LANGUAGES` and `row.default_language in module.SCRIPT_LANGUAGES[row.script]`; scripts unique; config keys unique.
- [ ] **Step 2: Run** `$SCRATCH/runtests.sh . tests/test_script_languages.py` → red: 3 failed (`FileNotFoundError` for `scriptLanguages.py`).
- [ ] **Step 3: Create `scriptLanguages.py`**: module docstring saying it is the detection's language data and the table of scripts whose assumed language the user chooses, standard library only so it loads without NVDA; move `languageDetection/__init__.py:8-95` there unchanged; add `DetectionScript` (comment per field) and `DETECTION_SCRIPTS` (comment: the Unicode Detection panel's order; the Cyrillic/Devanagari rows keep the comment of `settings.py:19`). In `__init__.py` delete `:8-95` and add `from .scriptLanguages import SCRIPT_LANGUAGES`.
- [ ] **Step 4: Point the detector tests at the module**: `detector_harness.load_language_detection` returns `script_languages=importlib.import_module(PACKAGE + ".languageDetection.scriptLanguages")`; `tests/test_language_detector.py:667,718` read `env.script_languages.SCRIPT_LANGUAGES`.
- [ ] **Step 5: Verify the data moved byte for byte**: `git show 85bcf54:addon/synthDrivers/WorldVoice/languageDetection/__init__.py | sed -n 8,95p > $SCRATCH/base-data.txt`; the same 88 lines must appear contiguously in `scriptLanguages.py` (`python3 -c` check that the file text contains the base text) → prints `True`.
- [ ] **Step 6: Run** `$SCRATCH/runtests.sh . tests` → green: 3250 passed, 0 skipped.
- [ ] **Step 7: Commit** `refactor: move the detection language data into scriptLanguages` (stage the two add-on files and three test files).

### Task 2: settings derive the confspec and script keys from the table

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/languageDetection/settings.py:15-31`
- Modify: `tests/test_detection_settings.py:10,23-32`, `tests/nvda_stubs.py:86-90`
- Modify: `tests/test_script_languages.py`

**Interfaces:**
- Consumes: `DETECTION_SCRIPTS`, `DetectionScript` (Task 1).
- Produces: `settings.DETECTION_CONFSPEC: dict[str, str]` and `settings.SCRIPT_CONFIG_KEYS: dict[str, str]`, same values and order as today; `settings.py` imports `from .scriptLanguages import DETECTION_SCRIPTS`.

- [ ] **Step 1: Write the failing tests**
  - `tests/test_script_languages.py::test_script_config_keys_are_written_only_in_the_table` — walk `ADDON.rglob("*.py")` (skip `driver/*/driver/` and the generated data like `tests/test_translator_comments.py:8`); collect `ast.Constant` strings ending in `"CharactersLanguage"`; assert the set of files holding any is `{WORLDVOICE / "languageDetection/scriptLanguages.py"}`.
  - `tests/test_detection_settings.py::test_detection_confspec_and_keys_derive_from_the_table` — register a substitute module `<alias>.scriptLanguages` whose `DETECTION_SCRIPTS` is the real table plus `DetectionScript("Hebrew", "hebrewCharactersLanguage", "he")`, load `settings.py` in that alias package; assert `list(module.DETECTION_CONFSPEC)[-2:] == ["hebrewCharactersLanguage", "DetectLanguageTiming"]`, `module.DETECTION_CONFSPEC["hebrewCharactersLanguage"] == "string(default=he)"`, `module.SCRIPT_CONFIG_KEYS["Hebrew"] == "hebrewCharactersLanguage"`, and `list(module.SCRIPT_CONFIG_KEYS) == [row.script for row in table]`.
  - `tests/test_detection_settings.py::test_the_config_stub_reads_the_detection_defaults_from_the_table` — `worldvoice_conf()["WorldVoice"]["autoLanguageSwitching"]` contains `{row.config_key: row.default_language for row in DETECTION_SCRIPTS}` and `DetectLanguageTiming == "after"`.
  - Change `load_settings_module` to load through `alias_package(monkeypatch, "detection_settings_under_test", WORLDVOICE / "languageDetection")` and `importlib.import_module("detection_settings_under_test.settings")` (optionally with a substitute `scriptLanguages`), so the relative import resolves without `__init__.py`.
- [ ] **Step 2: Run** `$SCRATCH/runtests.sh . tests/test_detection_settings.py tests/test_script_languages.py` → red: `test_script_config_keys_are_written_only_in_the_table` (settings.py holds the keys) and `test_detection_confspec_and_keys_derive_from_the_table` (no Hebrew key) fail; the stub test passes (it pins today's behavior).
- [ ] **Step 3: Derive in `settings.py`**: `DETECTION_CONFSPEC = {**{row.config_key: f"string(default={row.default_language})" for row in DETECTION_SCRIPTS}, "DetectLanguageTiming": "string(default=after)"}`; `SCRIPT_CONFIG_KEYS = {row.script: row.config_key for row in DETECTION_SCRIPTS}`; keep the comments' meaning.
- [ ] **Step 4: Teach `tests/nvda_stubs.py` the table**: for `DETECTION_CONFSPEC`, walk the dict node of `settings.py`; a constant key takes `_confspec_default(literal value)`; a `**{…}` entry must be a `DictComp` iterating `DETECTION_SCRIPTS` — read the rows from `scriptLanguages.py` (`DetectionScript(...)` calls; fields from the dataclass's annotated names, positional or keyword, `ast.literal_eval` each), evaluate the comprehension's key and value expressions for each row with the loop variable bound to a namespace of the row, and pass the value through `_confspec_default`. Anything else raises `ValueError` as today.
- [ ] **Step 5: Run** `$SCRATCH/runtests.sh . tests` → green: 3253 passed, 0 skipped.
- [ ] **Step 6: Commit** `refactor: derive the detection confspec and script keys from the table`.

### Task 3: the Unicode Detection panel iterates the table

**Files:**
- Modify: `addon/globalPlugins/WorldVoice/speechSettingsDialog.py:13,505-508,540-542`
- Modify: `tests/test_unicode_panel.py:55-64`, `tests/ui_harness.py:756`

**Interfaces:**
- Consumes: `DETECTION_SCRIPTS`, `SCRIPT_LANGUAGES` (Task 1).
- Produces: the dialog imports `from synthDrivers.WorldVoice.languageDetection.scriptLanguages import DETECTION_SCRIPTS, SCRIPT_LANGUAGES`; `_script_labels()` unchanged; `from synthDrivers.WorldVoice import languageDetection` removed.

- [ ] **Step 1: Write the failing tests** in `tests/test_unicode_panel.py` (`build` gains `table=None`; environment supplies `"DETECTION_SCRIPTS": table or env.script_languages.DETECTION_SCRIPTS` and `"SCRIPT_LANGUAGES": env.script_languages.SCRIPT_LANGUAGES` instead of `"languageDetection"`):
  - `test_detection_panel_lists_every_table_script` — `set(built.panel._script_labels()) == {row.script for row in DETECTION_SCRIPTS}` and the label count equals the table length; with `table=tuple(reversed(DETECTION_SCRIPTS))` the first five control labels are the default order reversed and saving still writes each row's key.
  - `test_the_dialog_reads_the_tables_without_the_detector` — AST of `speechSettingsDialog.py`: every import naming `languageDetection` is `from synthDrivers.WorldVoice.languageDetection.settings import …` or `….scriptLanguages import …`.
- [ ] **Step 2: Run** `$SCRATCH/runtests.sh . tests/test_unicode_panel.py` → red: every `build`-based test fails with `NameError: name 'languageDetection' is not defined` (the environment no longer supplies it), and the import test fails on `from synthDrivers.WorldVoice import languageDetection`.
- [ ] **Step 3: Change the dialog**: `makeSettings` builds `labels = self._script_labels()` and `self._scriptChoices = {detectionScript.script: self._add_script_choice(settingsSizerHelper, detectionScript.script, labels[detectionScript.script]) for detectionScript in DETECTION_SCRIPTS}`; `_add_script_choice` uses `SCRIPT_LANGUAGES[script]`; replace the import line. Translator comments untouched.
- [ ] **Step 4: Update `tests/ui_harness.py:756`**: drop the `languageDetection` package stub's `SCRIPT_LANGUAGES`; register the real `scriptLanguages.py` with `load_source(monkeypatch, "synthDrivers.WorldVoice.languageDetection.scriptLanguages", WORLDVOICE / "languageDetection/scriptLanguages.py")`.
- [ ] **Step 5: Run** `$SCRATCH/runtests.sh . tests` → green: 3255 passed, 0 skipped.
- [ ] **Step 6: Commit** `refactor: build the Unicode Detection choices from the script table`.

### Task 4: move the detector out of the package `__init__.py`

**Files:**
- Create: `addon/synthDrivers/WorldVoice/languageDetection/detector.py` (content of `__init__.py`, unchanged)
- Modify: `addon/synthDrivers/WorldVoice/languageDetection/__init__.py` (empty), `addon/synthDrivers/WorldVoice/__init__.py:28,267`, `pyproject.toml:64`
- Modify: `tests/detector_harness.py`, `tests/test_worldvoice_lifecycle.py:180`, `tests/test_worldvoice_speak.py:154`, `tests/test_runtime_composition.py:596-597`, `tests/test_pipeline_structure.py:32-36`, `tests/test_runtime_import_guard.py:55`, `tests/test_script_languages.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: `languageDetection.detector.LanguageDetector` (same signature); synth `__init__.py` imports `from .languageDetection.detector import LanguageDetector`.

- [ ] **Step 1: Write the failing tests**
  - `tests/test_script_languages.py::test_script_languages_import_by_their_package_path_without_nvda` — the `tests/test_ui_structure.py:122-160` pattern: drop `synthDrivers*` from `sys.modules`, set `wx` and the NVDA modules (including `speech`) to `None`, alias `synthDrivers` and `synthDrivers.WorldVoice`, import `synthDrivers.WorldVoice.languageDetection.scriptLanguages`; assert the loaded `synthDrivers*` names are exactly the package chain plus the module, and pop the two self-registered names in `finally`.
  - `tests/test_runtime_import_guard.py::test_package_init_stays_empty` parametrized with `"languageDetection"` too.
- [ ] **Step 2: Run** `$SCRATCH/runtests.sh . tests/test_script_languages.py tests/test_runtime_import_guard.py` → red: 2 failed (`ImportError` on `speech.commands`; `__init__.py` not empty).
- [ ] **Step 3: Move**: `git mv languageDetection/__init__.py languageDetection/detector.py`, then create an empty `languageDetection/__init__.py`; synth `__init__.py:28` → `from .languageDetection.detector import LanguageDetector`, `:267` → `LanguageDetector(`; `pyproject.toml:64` → `languageDetection/detector.py`. Confirm `git diff -M --stat` shows `detector.py` as a 100% rename.
- [ ] **Step 4: Follow in tests**: `detector_harness` imports `.languageDetection.detector` as `module`; `test_worldvoice_lifecycle` supplies `"LanguageDetector": LanguageDetector`; `test_worldvoice_speak` loads `"languageDetection.detector"`; `test_runtime_composition` stubs `package + ".languageDetection.detector"` with a `LanguageDetector`; `test_pipeline_structure.py:33` reads `languageDetection/detector.py`.
- [ ] **Step 5: Run** `$SCRATCH/runtests.sh . tests` → green: 3257 passed, 0 skipped (3256 + the new parametrization).
- [ ] **Step 6: Commit** `refactor: move the language detector out of the package init`.

### Task 5: full verification

- [ ] **Step 1:** `$SCRATCH/runtests.sh . tests` → 3257 passed, 0 skipped (baseline 3247 + 10 new).
- [ ] **Step 2:** `prek run --all-files` → all Passed; `git diff --check master` → no output.
- [ ] **Step 3:** protected paths: `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py addon/synthDrivers/WorldVoice/unicodeScripts/unspaced_common_data.py` and `git ls-files addon/synthDrivers/WorldVoice/driver/Neural` → both empty.
- [ ] **Step 4:** `grep -rn "CharactersLanguage" addon --include=*.py` → only `scriptLanguages.py`; `git diff master -- addon/locale` → empty.
