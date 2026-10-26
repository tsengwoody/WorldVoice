# Phase 39: naming cleanup (`engineRegistry/`, `bringup.py`, `speechDictionary.py`, `runtime/voiceSettings.py`, `unicodeScripts/`)

Date: 2026-10-26.
Base: `master` `e54d804` (phases 36–38 merged). Branch: `phase39-naming-cleanup`.
Source: round-8 review `storage/refactor8.md` §6 "階段 39" — findings F4 (§2.4), F9 (§2.9), F10 (§2.10), the F11 items about `assembly.py` and `languageDetection/scripts.py` (§2.11), A3 (§4.3), and the two items deferred to this phase (phase 37 review M4, phase 38 review M2). The review predates phases 36–38; paths and line numbers below are those of `master` `e54d804`.
Status: automatic flow (DEVELOPMENT_WORKFLOW.md §3), run as the **complex flow** (§4). Scope chosen by the user (2026-10-26): every optional item of phase 39.

## 0. Why the complex flow

This phase is a wide mechanical rename: one package, four modules and two generated data files change name or package, and about forty test files, harnesses, two generators and three configuration files name them by path or by dotted name. DEVELOPMENT_WORKFLOW.md §4.0 lists "大範圍的機械式修改 … 必須證明沒有夾帶其他修改" as a complex-flow case. The plan carries byte-exact `File:`/`Edit:` blocks and the expected `HEAD:addon`/`HEAD:tests` tree ids after every commit, and is dry-run in a fresh clone before it is applied (§4.2–4.4).

## 1. Problem

All paths below are under `addon/synthDrivers/WorldVoice/` unless stated.

1. **`engine/` and `driver/` read as the same thing** (F4). The wrappers live in `driver/<Engine>/`; `engine/` holds the list of known engines and their enabled flags, labels and defaults (`engine/__init__.py:22-30` `ENGINE_SPECS`, `:33-56`). Its importers: `__init__.py:34`, `globalPlugins/WorldVoice/speechSettingsDialog.py:14`; tests `tests/test_engine_registry.py:50`, `tests/test_engine_discovery.py:20-22`, `tests/test_runtime_composition.py:622`, `tests/ui_harness.py:764-779`. `engine/__init__.py:16` derives the add-on root from `__file__` (two `dirname`s) and `:20` the driver package from `__package__.rsplit('.', 1)[0]`; both depend only on the package being one level below the synth.
2. **`assembly.py` does not say what it holds** (F11). Its docstring is "Bring-up helpers for the driver: fixed-order teardown, step timing, attribute patches" (`assembly.py:1`). Importers: `__init__.py:29`, `engine/discovery.py:12`, `pipeline/speech_dictionary.py:7`; tests `tests/test_assembly.py:11`, `tests/test_worldvoice_lifecycle.py:12`, `tests/test_runtime_composition.py:268`, `tests/ui_harness.py:765`.
3. **`pipeline/speech_dictionary.py` is the one snake_case module name** among WorldVoice's own modules (A3); the others are camelCase, and the only other underscores are the generated `script_data.py`/`unspaced_common_data.py`, NVDA's `driver/sonic/_sonic.py` and the private `runtime/_segmentLifecycle.py`. Importer: `pipeline/registry.py:20`, `:178`, `:188`; tests `tests/pipeline_harness.py:60`, `:120`, `tests/test_pipeline_stages.py:135-136`, `tests/test_speech_dictionary.py:27`.
4. **Three `settings.py` files mean three things** (F9). `runtime/settings.py` holds the per-voice parameter state (`VoiceSettingsStore`, `VoiceState`, `VOICE_PARAMETERS`, `PARAMETER_NAMES`), not settings of the runtime. Importers: `__init__.py:55`, `runtime/session.py:17`, `bridge/voiceFacade.py:7`, `bridge/engineAdapter.py:24` (comment), `voices/manager.py:15`, `voices/mainLocalePolicy.py:7`, `voices/settingsRepository.py:6`, `globalPlugins/WorldVoice/rolePresenter.py:5`. No engine wrapper (`driver/*/__init__.py`) and no WorldVoice-workspace plugin imports it: `git grep` over the wrappers finds only `runtime.{engineControl, models, playbackWork, segmentHost, session}`, and `ref/Neural/Neural/__init__.py:2` imports only `synthDrivers.WorldVoice.driver`.
5. **The Unicode script data is split over two packages** (F10, and the F11 name clash of `scripts.py` with NVDA's input-gesture scripts). `languageDetection/scripts.py` (`get_script`) and `languageDetection/script_data.py` are the Script lookup; `pipeline/unspaced_common_data.py` is derived from the same Unicode release. The pipeline imports `languageDetection` only to look up a script (`pipeline/unspaced.py:10`), which loads the whole detector package (`languageDetection/__init__.py:1` imports NVDA's `speech.commands`). Users: `languageDetection/__init__.py:6`, `pipeline/unspaced.py:10`, `:13`, `:24` (comment); generators `tools/generate_unicode_scripts.py:1`, `:10`, `:14`, `tools/generate_unspaced_common.py:7`, `:22`, `:26`, `:43` (`SCRIPT_DATA`, the default of `--script-data`, `:267`); exclusions `pyproject.toml:24` (coverage omit), `:108` (ruff exclude), `.pre-commit-config.yaml:12`, `tests/test_translator_comments.py:8`; tests `tests/test_generated_unicode_data.py:3`, `:18-19`, `tests/test_generate_unicode_scripts.py:1`, `tests/test_language_scripts.py:18-20`, `:68`, `tests/test_pipeline_unspaced_space.py:18`, `:64`, `:100-101`, `tests/pipeline_harness.py:61`, `:109`, `:126`.
6. **Test helpers still carry the names of files that no longer exist** (phase 37 review M4): `tests/ui_harness.py:815` `load_voice_settings_dialogs` loads `ui/voicePanel.py`, `:704` `load_pipeline_controls` loads `ui/controls.py`; `tests/runtime_harness.py:193` `load_config_repository` loads `voices/settingsRepository.py`; the `speechcommand` names (`tests/pipeline_harness.py:191`, `tests/test_legacy_speech_commands.py:26`, `tests/test_worldvoice_index_command.py:9`) hold `speechCommands`. Two test files are named after old modules: `tests/test_pipeline_controls.py`, `tests/test_voice_config_repository.py`.
7. **The structure guard's list misses `recorder.py`** (phase 38 review M2): `tests/test_pipeline_structure.py:117` `test_pipeline_package_keeps_only_stages_logging_and_registry` is parametrized by `STAGE_MODULES` (`:104-113`), which has no `recorder`, so an `os` or NVDA import added to `pipeline/recorder.py` goes unnoticed.

## 2. Goals

1. `git mv engine engineRegistry` (F4). Importers and tests follow. `engineRegistry/__init__.py` gains a module docstring that says what the registry holds and points to `driver/` for the wrappers; nothing else in the package changes.
2. `git mv assembly.py bringup.py` (F11); `tests/test_assembly.py` → `tests/test_bringup.py`, and the test names that hold the module (`assembly` fixture and locals, `_assembly`) follow.
3. `git mv pipeline/speech_dictionary.py pipeline/speechDictionary.py` (A3).
4. `git mv runtime/settings.py runtime/voiceSettings.py` (F9). The test namespaces that expose runtime modules as attributes (`rt.settings`, `modules.settings` in `tests/test_worldvoice_request_builder.py`) name it `voice_settings`, as they name `playbackWork` `playback_work`.
5. New package `unicodeScripts/` with an empty `__init__.py` (F10):

   | From | To |
   | --- | --- |
   | `languageDetection/scripts.py` | `unicodeScripts/lookup.py` (gains a one-line module docstring) |
   | `languageDetection/script_data.py` | `unicodeScripts/script_data.py` (byte-identical) |
   | `pipeline/unspaced_common_data.py` | `unicodeScripts/unspaced_common_data.py` (byte-identical) |

   The user authorized moving the two generated files for this phase (2026-10-26). Their content does not change: no hand edit, no regeneration; `git diff -M` shows both as 100% renames, and `tests/test_generated_unicode_data.py` (which re-renders each file with its generator's own functions) stays green at the new paths. The generators' docstrings, usage examples and `SCRIPT_DATA` default, the ruff/coverage/pre-commit exclusions and `tests/test_translator_comments.py` follow. `tests/test_language_scripts.py` → `tests/test_unicode_scripts.py`.
6. Test helper names follow the modules they load: `load_voice_panel`, `load_ui_controls`, `load_settings_repository`, `speech_commands`; `tests/test_pipeline_controls.py` → `tests/test_ui_controls.py`, `tests/test_voice_config_repository.py` → `tests/test_voice_settings_repository.py`; in `tests/test_ui_structure.py` the constant `PIPELINE_CONTROLS` → `UI_CONTROLS` and its test `test_pipeline_controls_imports_only_wx_and_the_layout_rules` → `test_ui_controls_imports_only_wx_and_the_layout_rules`.
7. `STAGE_MODULES` gains `"recorder"`.
8. New guard tests, each written red first where a red state exists:
   - `tests/test_runtime_import_guard.py::test_package_init_stays_empty[unicodeScripts]`.
   - `tests/test_pipeline_structure.py::test_the_pipeline_does_not_import_language_detection`: no module of `pipeline/` imports `languageDetection` (any `import`/`from` whose dotted name or imported names contain it). Red before the move (`pipeline/unspaced.py:10`).
   - `tests/test_generate_unspaced_common.py::test_without_script_data_the_tool_reads_the_committed_one`: the generator's `SCRIPT_DATA` is `unicodeScripts/script_data.py` and exists. Red before the move.
   - `test_pipeline_package_keeps_only_stages_logging_and_registry[recorder]` (goal 7); no red state without editing the add-on, so the plan shows it red with an uncommitted `import os` in `recorder.py`.

## 3. Non-goals

- No behavior change. NVDA users hear and see nothing new; no UI string changes (none of the moved modules has a translatable string), so no translation work.
- No class, function, constant or attribute rename in the add-on: `ENGINE_SPECS`, `Teardown`, `install`/`uninstall`, `VoiceSettingsStore`, `get_script`, `UNSPACED_COMMON` and every other name keep their names.
- `pipeline/settings.py`'s setting table stays where it is (the optional `settingsTable.py` split of refactor8 §2.9 is not in the scope the user chose).
- `languageDetection/settings.py` and `pipeline/settings.py` keep their names: each is the settings of its package.
- Test files whose names still describe what they test keep them: `tests/test_speech_dictionary.py` (test files are snake_case), `tests/test_runtime_settings_store.py` (`VoiceSettingsStore`), `tests/test_nvda_event_bridge*.py` (class `NvdaEventBridge`), `tests/test_engine_registry.py`/`tests/test_engine_discovery.py`. The alias package names inside tests (`speech_dictionary_test_worldvoice`, `worldvoice_ui_engines`, …) are test-local labels and stay, except `language_scripts_test_worldvoice`, which becomes `unicode_scripts_test_worldvoice` with its file. `tests/test_runtime_composition.py::_config_repository` installs a `ConfigVoiceSettingsRepository` and keeps its name.
- Historical documents under `docs/` keep the old paths as written. `DEVELOPMENT_WORKFLOW.md` (untracked, main checkout) is updated by the orchestrator after merge.

## 4. Constraints (DEVELOPMENT_WORKFLOW.md §8, refactor8.md §0)

- Public import paths do not change: `synthDrivers.WorldVoice.driver` (`Voice`, `getVoiceKey`), `runtime.{engineControl, models, playbackWork, segmentHost, session}`, `text.arabic`, `text.chunker`, `driver.sonic._sonic`. `tests/test_plugin_voice_contract.py` is not edited and passes. `runtime/settings.py` is not among the public paths (§1 item 4).
- Never modify `driver/<Engine>/driver/` or `driver/sonic/`. The two generated data files move only, byte-identical (§2 goal 5). Engine drivers stay independently installable. No Neural, no `ref` in commits.
- Dependency direction after the phase: `languageDetection → unicodeScripts`, `pipeline → unicodeScripts`; `pipeline/` never imports `languageDetection`; `unicodeScripts/` imports nothing outside itself (`lookup → script_data`).
- ruff pinned `==0.16.3`; files as prek leaves them.

## 5. Design

### 5.1 `engineRegistry/`

`git mv engine engineRegistry`. The package stays at the same depth, so `PACKAGE_ROOT` (`os.path.dirname(os.path.dirname(__file__))`, the synth directory) and `INTERNAL_DRIVER_PACKAGE` (`synthDrivers.WorldVoice.driver`) are unchanged; `tests/test_engine_registry.py::test_import_discovers_the_bundled_drivers_then_the_workspace_engines` pins the second (`spec.module_name == f"{PACKAGE}.driver.{spec.name}"`). The docstring (F4 option B's cross-reference, added on top of option A's rename):

```text
"""The known engines: found at import, with whether each is enabled, its label and its default.

The engine wrappers themselves live in driver/<Engine>/ (bundled) and in the WorldVoice-workspace
(plugins); discovery.py finds and loads them. Not part of driver/: a plugin's import of
synthDrivers.WorldVoice.driver must not scan the disk or initialize translations.
"""
```

### 5.2 `bringup.py`, `speechDictionary.py`

Plain `git mv`; ruff's isort moves `from .bringup import …` after the `.bridge.*` imports in `__init__.py`.

### 5.3 `runtime/voiceSettings.py`

Plain `git mv`; every importer's line changes in place (isort order unchanged).

### 5.4 `unicodeScripts/`

```
unicodeScripts/
├── __init__.py              empty (new)
├── lookup.py                ← languageDetection/scripts.py (+ docstring)
├── script_data.py           ← languageDetection/script_data.py (100% rename)
└── unspaced_common_data.py  ← pipeline/unspaced_common_data.py (100% rename)
```

- `languageDetection/__init__.py`: `from .scripts import get_script` → `from ..unicodeScripts.lookup import get_script`.
- `pipeline/unspaced.py`: `from ..unicodeScripts.lookup import get_script`, `from ..unicodeScripts.unspaced_common_data import UNSPACED_COMMON`; the comment naming the file to regenerate says `unicodeScripts/unspaced_common_data.py`.
- `lookup.py` keeps `from .script_data import …` (same package).
- The generated files' content names no path (`script_data.py:1`, `unspaced_common_data.py:1-5`), and the generators write to the destination given on the command line, so their output is unchanged.
- `tests/pipeline_harness.py` drops `unspaced_common_data` from `PIPELINE_MODULES` (the view reads only `pipeline.*` modules; `UNSPACED_COMMON` is still found through `pipeline.unspaced`), and its list of modules to reload names the new dotted paths one for one (`languageDetection.scripts` → `unicodeScripts.lookup`, `pipeline.unspaced_common_data` → `unicodeScripts.unspaced_common_data`), so each load still imports the lookup fresh (`tests/test_pipeline_unspaced_space.py::test_pipeline_harness_loads_the_script_lookup_fresh`, renamed from `…_loads_language_detection_fresh`).
- `tests/test_unicode_scripts.py` no longer aliases the `languageDetection` package without its `__init__`: `unicodeScripts/__init__.py` is empty, so the real package imports.

### 5.5 Tests

See §2 goals 6–8. Expected counts: baseline 3236 passed, 0 skipped; after the phase 3240 passed, 0 skipped (+4 guards: `unicodeScripts` empty `__init__`, pipeline without `languageDetection`, the generator's `SCRIPT_DATA`, `recorder` in `STAGE_MODULES`).

## 6. Settings, data, compatibility

No config key, confspec, stored value or UI string changes. A WorldVoice-workspace plugin imports only `synthDrivers.WorldVoice.driver`, which is unchanged. An installed add-on is replaced as a whole on update, so no stale `engine/`, `assembly.py`, `runtime/settings.py` or `languageDetection/scripts.py` remains.

Documents outside the repository that name the moved paths (orchestrator, after merge): `DEVELOPMENT_WORKFLOW.md` §7 protected-path command and §8 generated-file rule (`languageDetection/script_data.py`, `pipeline/unspaced_common_data.py` → `unicodeScripts/…`); the auto-memory note on generated Unicode data; `storage/refactor8.md` §6.

## 7. Test plan

- Unit: §2 goal 8, §5.5; `tests/test_plugin_voice_contract.py` unchanged and green; `tests/test_generated_unicode_data.py` green at the new paths.
- Mutation: not needed — no logic changes. `pyproject.toml` `[tool.mutmut] source_paths` names none of the moved files.
- Full verification per DEVELOPMENT_WORKFLOW.md §7 after every commit. The protected-path command of §7 shows the two generated files as removed at their old paths; `git diff -M --stat master` must show them as 100% renames, and `git diff -M100% --name-status master` must list them as `R100`.
- Windows/NVDA manual: none required (no behavior change). Not packaged, not verified on Windows.

## 8. Open questions

None. The scope is the user's choice; the docstrings of `engineRegistry/__init__.py` and `unicodeScripts/lookup.py` are the only text added to add-on modules.
