# Phase 43: detection script table (`languageDetection/scriptLanguages.py`)

Date: 2026-10-27.
Base: `master` `85bcf54`. Branch: `phase43-detection-script-table`.
Source: round-9 review `storage/refactor9.md` §4.2 **F7**, §4.1 "其他 SRP 觀察" (third bullet), §6 row **P43**, §6.1 (layered naming rule, 2026-10-27). Line numbers below are those of `master` `85bcf54`, checked in this worktree.
Status: automatic normal flow (DEVELOPMENT_WORKFLOW.md §3). No user-visible behavior change.

All paths are under `addon/synthDrivers/WorldVoice/` unless stated.

## 1. Problem

1. **Adding a detection script means editing four places** (F7):
   - `languageDetection/settings.py:15-23` `DETECTION_CONFSPEC` (config key and default);
   - `languageDetection/settings.py:25-31` `SCRIPT_CONFIG_KEYS` (script → key);
   - `languageDetection/__init__.py:66-95` `SCRIPT_LANGUAGES` (candidate languages; Cyrillic and Devanagari were already there);
   - `addon/globalPlugins/WorldVoice/speechSettingsDialog.py:526-538` `_script_labels` (the panel label, which also decides which scripts get a control and in what order, `:505-508`).

   Commit `cfe250a` (the code half of the Cyrillic/Devanagari addition; `6a20565` is its docs half) shows it: `speechSettingsDialog.py` +7, `languageDetection/settings.py` +5, plus five test files. The five scripts appear in the same order in all three dictionaries, but nothing ties them together: a script with a label but no key raises `KeyError` only when the panel opens (`speechSettingsDialog.py:546` reads `self._detection.script_language[script]`), and a key with no label is silently never offered.
2. **The data tables live in the detector module** (§4.1). `languageDetection/__init__.py:8-95` holds 88 lines of language tuples (`BASIC_LATIN` … `SCRIPT_LANGUAGES`); `LanguageDetector` starts at `:98`, and the module imports NVDA's `speech.commands` (`:1`). The dialog imports the whole package (`speechSettingsDialog.py:13`) only to read `SCRIPT_LANGUAGES` (`:542`).

## 2. Goals

1. **One table.** New module `languageDetection/scriptLanguages.py`, standard library only, holds:
   - the language tuples `BASIC_LATIN`, `EXTENDED_LATIN`, `ALL_LATIN`, `CYRILLIC`, `ARABIC`, `DEVANAGARI`, `CJK` and `SCRIPT_LANGUAGES`, moved unchanged (same names, values and order) from `languageDetection/__init__.py:8-95`;
   - `@dataclass(frozen=True) class DetectionScript` with fields `script: str` (the Unicode script name, a key of `SCRIPT_LANGUAGES`), `config_key: str` (the key in `config["WorldVoice"]["autoLanguageSwitching"]`), `default_language: str`;
   - `DETECTION_SCRIPTS: tuple[DetectionScript, ...]`, in the panel's order:

     | script | config_key | default_language |
     | --- | --- | --- |
     | `Latin` | `latinCharactersLanguage` | `en` |
     | `Han` | `CJKCharactersLanguage` | `ja` |
     | `Arabic` | `arabicCharactersLanguage` | `ar` |
     | `Cyrillic` | `cyrillicCharactersLanguage` | `ru` |
     | `Devanagari` | `devanagariCharactersLanguage` | `hi` |

     The comment at `settings.py:19` ("The first candidates of their scripts, which detection took before these choices existed.") moves with the Cyrillic and Devanagari rows.
   - **No translated label in the table.** *Decided by orchestrator with the recommended default; user may override before merge.* refactor9 F7 sketched a `label: str  # _("…")` field and `addonHandler.initTranslation()` in the settings module. This phase deviates: the project may later grow into a standalone language-switching library (refactor9 §6.1, §6.2), so the core table must not depend on NVDA's translation machinery. Labels stay in the NVDA host layer (goal 3).
2. **Everything else derives from the table.**
   - `languageDetection/settings.py`: `DETECTION_CONFSPEC` = one `f"string(default={default_language})"` entry per row, in table order, followed by the existing `"DetectLanguageTiming": "string(default=after)"`; `SCRIPT_CONFIG_KEYS` = `{row.script: row.config_key}` in table order. Both keep their names and exact current values (dict equality and key order). The configobj validator text is config knowledge, so it is built in `settings.py`, not in the core table. `_TIMING_KEY` stays.
   - After this phase the string `…CharactersLanguage` appears in exactly one add-on Python file, `scriptLanguages.py` (guard, §6).
3. **Labels stay host-side.** `UnicodeDetectionSettingsPanel` keeps `_script_labels()` (name unchanged) returning a mapping keyed by script name, with the five `# Translators:` comments and msgids unchanged. `makeSettings` iterates `DETECTION_SCRIPTS` in table order and looks each label up by `row.script`; `_add_script_choice` reads `SCRIPT_LANGUAGES` from `scriptLanguages`. A guard test asserts the label mapping's keys equal the table's scripts.
4. **The dialog no longer loads the detector.** The dialog imports `DETECTION_SCRIPTS` and `SCRIPT_LANGUAGES` from `synthDrivers.WorldVoice.languageDetection.scriptLanguages`; `from synthDrivers.WorldVoice import languageDetection` (`speechSettingsDialog.py:13`) goes away.
   - **Finding (contradicts the brief's literal wording, not its goal).** Importing `synthDrivers.WorldVoice.languageDetection.scriptLanguages` runs `languageDetection/__init__.py` first. While the detector lives there, that import still loads `speech.commands`, and the dialog already runs it today through `languageDetection.settings` (`speechSettingsDialog.py:15`). refactor9 §5.2 keeps `LanguageDetector` in `__init__.py` ("只剩 LanguageDetector") and the orchestrator's brief says `__init__.py` "imports what it needs from `scriptLanguages.py`"; with either, goal 4 and the requested package-path guard ("follow the existing pattern for `pipeline.numbers` / `ui.panelLayout`", which relies on an empty package `__init__.py`, `tests/test_runtime_import_guard.py:55-60`) cannot hold.
   - **Decision.** *Decided by the spec author with the recommended default (no user-visible change); orchestrator/user may override before merge.* `LanguageDetector` moves unchanged (same class body, same imports) to the new module `languageDetection/detector.py`; `languageDetection/__init__.py` becomes empty (0 bytes) and joins `test_package_init_stays_empty`. The move is its own task and commit (plan Task 4), so the fallback — keep the detector in `__init__.py`, which imports from `scriptLanguages`, and guard `scriptLanguages.py` by file path only — is a revert of one commit. Cost of the decision: the synth package's import (`__init__.py:28`, `:267`) and six test helpers change path; `languageDetection` is not a public or plugin-facing path (`ref/Neural` does not import it; refactor9 §5.3 lists no public impact).
   - In NVDA the synth package `synthDrivers/WorldVoice/__init__.py` imports the detector anyway (`:28`), so the gain is the dependency direction, not fewer modules at runtime: the dialog's own imports no longer reach the detector, and `scriptLanguages` is importable without NVDA.

## 3. Non-goals

- No behavior change; nothing an NVDA user hears or sees changes. Panel control order (Latin, CJK, Arabic, Cyrillic, Devanagari, then timing), labels, focus, config keys, defaults and stored values stay identical; `addon/locale/*/nvda.po` need no change; no readme or changelog entry.
- No rename of an existing name (refactor9 §6.1; that is phase 47): `SCRIPT_LANGUAGES`, `SCRIPT_CONFIG_KEYS`, `DETECTION_CONFSPEC`, `LanguageDetector`, `availableLanguages`, `_script_labels`, `_add_script_choice`, `_scriptChoices` keep their names.
- No compatibility re-exports: `languageDetection` is not a public path, so importers (the synth package, the dialog, tests) move to the new modules.
- The detection timing setting stays outside the table (it is not a script).
- No dialog split (P42 moves the panel later and takes the new version).

## 4. Naming (refactor9 §6.1)

- `languageDetection/` is portable core: new names are PEP 8 — `DetectionScript`, `DETECTION_SCRIPTS`, fields `script`, `config_key`, `default_language`; module names follow the existing camelCase file convention (`scriptLanguages.py`, `detector.py`).
- The dialog is NVDA host layer: any new local name there is mixedCase (e.g. `labels`, `detectionScript`).

## 5. Affected layers and files

| File | Change |
| --- | --- |
| `languageDetection/scriptLanguages.py` | new: tuples, `SCRIPT_LANGUAGES`, `DetectionScript`, `DETECTION_SCRIPTS` |
| `languageDetection/settings.py` | derive `DETECTION_CONFSPEC` and `SCRIPT_CONFIG_KEYS` from the table (relative import `from .scriptLanguages import DETECTION_SCRIPTS`) |
| `languageDetection/detector.py` | new: `LanguageDetector`, moved unchanged; imports `SCRIPT_LANGUAGES` from `.scriptLanguages` |
| `languageDetection/__init__.py` | empty |
| `__init__.py` (synth) | `from .languageDetection.detector import LanguageDetector`; `:267` calls `LanguageDetector(` |
| `addon/globalPlugins/WorldVoice/speechSettingsDialog.py` | import from `scriptLanguages`; iterate the table |
| `pyproject.toml:64` | mutmut path `languageDetection/__init__.py` → `languageDetection/detector.py` |

No engine, no driver wrapper, no `runtime/`/`bridge/` change. Protected paths untouched.

## 6. Tests

Existing tests that pin the current values stay and must pass unchanged in their assertions: `tests/test_detection_settings.py::test_confspec_and_script_keys_keep_the_stored_names_and_defaults` (`:143-159`), `tests/test_unicode_panel.py::test_controls_choices_and_selections` (`:87-103`), `tests/test_translator_comments.py` (msgids and zh_TW entries), `tests/test_language_detector.py`.

Harness and path updates:
- `tests/test_detection_settings.py:23-32` loads `settings.py` by file path; it now loads it inside an alias package of `languageDetection/` so the relative import resolves without running `__init__.py`.
- `tests/nvda_stubs.py:86-90` reads `DETECTION_CONFSPEC` with `ast.literal_eval`; it now reads the table rows from `scriptLanguages.py` plus the literal entries of `DETECTION_CONFSPEC` (the `LOG_SWITCHES` / `PIPELINE_SETTINGS` precedent at `:91-120`).
- `tests/detector_harness.py:40-41` exposes the detector module (`languageDetection.detector` after Task 4) and the new `script_languages` module; `tests/test_language_detector.py:667`, `:718` read `SCRIPT_LANGUAGES` from it.
- `tests/test_unicode_panel.py:61` supplies `DETECTION_SCRIPTS` and `SCRIPT_LANGUAGES` instead of `languageDetection`; `tests/ui_harness.py:756` registers the real `scriptLanguages.py`.
- Task 4: `tests/test_worldvoice_lifecycle.py:180`, `tests/test_worldvoice_speak.py:154`, `tests/test_runtime_composition.py:596-597`, `tests/test_pipeline_structure.py:32-36` (path), `tests/test_runtime_import_guard.py:55` (add `languageDetection`).

New guards (each red first):
- `tests/test_script_languages.py` (new):
  - `test_script_languages_import_only_the_standard_library` (AST, like `tests/test_pipeline_structure.py:57-70`);
  - `test_detection_scripts_keep_the_stored_names_and_defaults` (the five rows above, in order);
  - `test_every_detection_script_has_candidates_and_a_candidate_default` (each `script` is a key of `SCRIPT_LANGUAGES`; `default_language` is in its tuple; scripts and keys are unique);
  - `test_script_config_keys_are_written_only_in_the_table` (no string constant ending in `CharactersLanguage` in any `addon/**/*.py` except `scriptLanguages.py`);
  - `test_script_languages_import_by_their_package_path_without_nvda` (Task 4; the `tests/test_ui_structure.py:122-160` pattern: NVDA modules set to `None`, import `synthDrivers.WorldVoice.languageDetection.scriptLanguages`, only the package chain and the module itself load).
- `tests/test_detection_settings.py::test_detection_confspec_and_keys_derive_from_the_table` (a substitute `scriptLanguages` with a sixth row yields a sixth confspec key and script key, timing last) and `test_the_config_stub_reads_the_detection_defaults_from_the_table`.
- `tests/test_unicode_panel.py::test_detection_panel_lists_every_table_script` (labels' keys equal the table's scripts; with the table reversed the controls follow the table order).
- `tests/test_unicode_panel.py::test_the_dialog_reads_the_tables_without_the_detector` (AST: the dialog imports from `languageDetection` only `settings` and `scriptLanguages`).

No mutmut run: no decision logic changes (data move and derivation; the mutmut target path follows the detector).

Manual Windows/NVDA items: none required (no user-visible change). Optional smoke check: open WorldVoice settings → Unicode Detection; the five assumed-language choices and the timing choice appear in the same order with the same values.

## 7. Strings

None new or changed.

## 8. Settings, compatibility, errors

- Same keys, defaults and validators: existing `nvda.ini` profiles read and write exactly as before. No migration.
- `DetectionSettingsService.update` still raises `KeyError` for a script outside the table (`settings.py:78-80`).

## 9. Open questions

1. Detector move to `detector.py` (goal 4) — decided by the spec author, reported to the orchestrator; fallback described in goal 4.
2. Table without labels (goal 1) — decided by orchestrator with the recommended default; user may override before merge.
