# Phase 38: split `pipeline/__init__.py`, move the recorder and Say All into `pipeline/`

Date: 2026-10-26.
Base: `master` `9f77382` (phases 36 and 37 merged). Branch: `phase38-pipeline-split`.
Source: round-8 review `storage/refactor8.md` §6 "階段 38" — findings F1 (§2.1), F6 (§2.6), F8 (§2.8) and A2 (§4.2) for `pipeline/numbers.py`. The review predates phases 36–37 (`compat/` is now `bridge/`, `_speechcommand.py` is `speechCommands.py`, the settings UI is in `ui/`); paths and line numbers below are those of the current `master`.
Status: automatic flow (DEVELOPMENT_WORKFLOW.md §3), run as the **complex flow** (§4).

## 0. Why the complex flow

About 1100 lines move verbatim out of `pipeline/__init__.py` into eight new modules, two modules move with `git mv`, and some twenty test files and harnesses name the pipeline by path, by dotted module name or by attribute. DEVELOPMENT_WORKFLOW.md §4.0 lists "大範圍的機械式修改 … 必須證明沒有夾帶其他修改" as a complex-flow case. The plan therefore carries byte-exact `File:`/`Edit:` blocks, a committed-in-the-plan extraction script for the verbatim move, and the expected `HEAD:addon`/`HEAD:tests` tree ids after every commit, and is dry-run in a fresh clone before it is applied (§4.2–4.4).

## 1. Problem

All paths below are under `addon/synthDrivers/WorldVoice/` unless stated.

1. **Every pipeline function lives in the package entry point** (F1). `pipeline/__init__.py` (1125 lines) holds the break commands (`:37-75`), the number stages (`inject_numbers` `:386`, `number_wait_factor` `:242`, `remove_thousands_separators` `:93`), the item pause (`item_wait_factor` `:171`), the unspaced-script pause (`:601-656`), the punctuation pause (`:659-843`), the edge-break merge (`:846-871`), the language-command helpers that `SynthDriver.speak` calls directly (`deduplicate_language_command` `:874`, `lang_cmd_to_voice` `:926`, `inject_langchange_reorder` `:942`; called at `__init__.py:321-323`), the CSV log writer (`_LogWriter` `:978`, `_run_logged` `:1004`) and the stage table with its registration (`Stage` `:1064`, `STAGES` `:1085`, `register_stages` `:1113`). A reader cannot tell from a file name where a stage is, nor which functions are NVDA filters and which are the synth's last step before the engines.
2. **"Loads without NVDA" holds only in the tests** (A2). `pipeline/numbers.py:3` says "This module imports only the standard library, so it needs no NVDA module or stub to load." The tests load it by file; an import by its package path `synthDrivers.WorldVoice.pipeline.numbers` first runs `pipeline/__init__.py`, which imports `config`, `speechDictHandler`, `logHandler`, `speech.commands`, `speech.extensions` (`pipeline/__init__.py:8-12`).
3. **`log.py` is named like a logger and placed outside its only user** (F6). It holds only `PipelineLog` (`log.py:13`); its one importer is `pipeline/__init__.py:15`, and the global plugin reaches it through `pipeline.pl` (`globalPlugins/WorldVoice/pipelineLog.py:10`). It finds the log folder from its own depth: `Path(__file__).resolve().parent.parent / "log"` (`log.py:6-9`), so moving it a folder deeper would move the log to `addon/synthDrivers/log`.
4. **`sayAll.py` sits at the root with NVDA's copyright header** (F8). `sayAll.py:1-3` is NVDA's header, but the module is WorldVoice's own patch: it applies the pipeline setting `sayall_wait_factor` (`sayAll.py:25`) through `pipeline_settings` and `current_context` (`:13-14`). Its only user is the global plugin (`globalPlugins/WorldVoice/__init__.py:15`).

## 2. Goals

1. **Split `pipeline/__init__.py` into focused modules** (F1); every definition moves verbatim, in its original order, with the comment lines right above it:

   | Module | Holds |
   | --- | --- |
   | `pipeline/sequence.py` | `SpeechCmd` and the two checks two stages share: `_MISSING`, `_both_text` |
   | `pipeline/breaks.py` | `NumberBreakCommand`, `NumberEdgeBreakCommand`, `NumberItemEdgeBreakCommand`, `PunctuationBreakCommand`, the edge marker (`_EDGE_MARKER`, `_ITEM_EDGE`, `_edge_kind`, `_is_edge_break`, `_is_item_edge_break`), `_merge_edge_breaks`, `_merged_run`, `_plain_breaks`, `_plain_break` |
   | `pipeline/items.py` | `item_wait_factor`, `_insert_item_breaks` |
   | `pipeline/numberStages.py` | `remove_thousands_separators`, `inject_numbers` and its helpers, `number_wait_factor` and its helpers, `_split_numbers_for_language`, `wrap_numbers_for_detection`, `detect_with_number_language`, `merge_consecutive_strings` |
   | `pipeline/punctuation.py` | `inject_punctuation_pause`, `_punctuation_pauses`, `_split_by`, `_get_punctuation_regex`, `_split_punctuation_segments` |
   | `pipeline/unspaced.py` | `UNSPACED_SCRIPTS`, `_WHITESPACE_RE`, `_is_unspaced`, `_pauses_between`, `inject_unspaced_script_space_pause` |
   | `pipeline/languageCommands.py` | `remove_language_command`, `deduplicate_language_command`, `lang_cmd_to_voice`, `inject_langchange_reorder` |
   | `pipeline/registry.py` | `pl`, `listable`, `speech_viewer`, `apply_speech_dictionaries`, `_LogWriter`, `_log_writer`, `_run_logged`, `_stage_handler`, `Stage`, `STAGES`, `_log_switches`, `LOG_SWITCHES`, `order_move_to_start_register`, `register_stages`, `unregister_stages` |

   Each new module gets a one-paragraph docstring and the imports it uses. `pipeline/__init__.py` becomes **empty** (§5.1).
2. **Importers use the owning module**: `__init__.py` (synth) imports from `pipeline.languageCommands`, `pipeline.numberStages` and `pipeline.registry`; `pipeline/scope.py` from `.registry`; `globalPlugins/WorldVoice/pipelineLog.py` (`pl`) and `globalPlugins/WorldVoice/speechSettingsDialog.py` (`LOG_SWITCHES`) from `synthDrivers.WorldVoice.pipeline.registry`.
3. **A2 guard**: a test imports `synthDrivers.WorldVoice.pipeline.numbers` by its package path with NVDA's modules unimportable and checks that only `pipeline` and `pipeline.numbers` load from the add-on; `pipeline` joins the empty-`__init__.py` guard of `bridge`, `voices`, `ui`. Written test first.
4. **`log.py` → `pipeline/recorder.py`** (F6), `git mv`, class name `PipelineLog` kept. The recorder takes the log file as a constructor argument and computes no path at import; the module that owns `pl` passes `addon/log/pipeline.csv`. A new test pins that path. Written test first.
5. **`sayAll.py` → `pipeline/sayAll.py`** (F8), `git mv`; NVDA's copyright header becomes a WorldVoice module docstring that says what the module does and that it makes the same `speech.sayAll.initialize` call NVDA makes when speech starts (`ref/nvda/source/speech/__init__.py:166-171`). It is not re-exported anywhere (it imports `speech`).
6. Every test, harness, guard and path constant follows the new modules; `pyproject.toml` `[tool.mutmut] source_paths` lists the new modules instead of `pipeline/__init__.py`. No ruff per-file ignore names the moved files.

## 3. Non-goals

- No behavior change. NVDA users hear and see nothing new; the pipeline log is still written to `addon/log/pipeline.csv` and exported from the same object; no new or changed UI string, so no translation work.
- No rename of any class, function, constant or attribute that moves; `PipelineLog`, `pl`, `STAGES`, `LOG_SWITCHES` keep their names.
- `pipeline/numbers.py`, `symbols.py`, `settings.py`, `context.py`, `speech_dictionary.py` are not edited. `pipeline/unspaced_common_data.py` (generated, protected) and `languageDetection/script_data.py` are not touched.
- Phase 39 items (F4, F9, F10, A3, the rest of F11) are out of scope. Historical documents under `docs/` keep the old paths as written.

## 4. Constraints (DEVELOPMENT_WORKFLOW.md §8, refactor8.md §0)

- Public import paths do not change: `synthDrivers.WorldVoice.driver` (`Voice`, `getVoiceKey`), `runtime.{engineControl, models, playbackWork, segmentHost, session}`, `text.arabic`, `text.chunker`, `driver.sonic._sonic`. `tests/test_plugin_voice_contract.py` passes unchanged. No wrapper or external plugin imports `pipeline`, `log` or `sayAll` (`git grep` of `addon/` and `ref/`).
- Never modify `driver/<Engine>/driver/`, `driver/sonic/`, `languageDetection/script_data.py`, `pipeline/unspaced_common_data.py`. Engine drivers stay independently installable. No Neural, no `ref` in commits.
- Module-level state stays single: one `pl`, one `_log_writer`, one `STAGES` tuple whose `Stage.handler`s are bound once (`pipeline/__init__.py:1079-1081`), one `speech_dictionary._restore`; `register_stages`/`unregister_stages` keep registering and removing exactly those handlers.
- Test assertions do not change. Only patch targets and harness wiring change, and the test count grows only by the new guard and path tests.
- ruff pinned `==0.16.3`; files as prek leaves them.

## 5. Design

### 5.1 `pipeline/__init__.py` is empty

refactor8 §2.1 proposed an `__init__.py` that re-exports what external code uses. A re-export of `pl`, `LOG_SWITCHES` or the stage functions has to import `registry`, and with it `config`, `speechDictHandler` and `speech.extensions`, so `import synthDrivers.WorldVoice.pipeline.numbers` would still need NVDA and A2 would stay open. Every importer is in this repository (§4), so they import from the owning module instead and `__init__.py` stays empty, as `bridge/`, `voices/` and `ui/` already are (`tests/test_runtime_import_guard.py:55-59`).

Ruling: `pipeline/__init__.py` is empty and importers name the owning submodule, not a re-export package — a re-export package would keep A2 open, and an empty package matches `bridge/`, `voices/`, `ui/` — cost if wrong: code outside this repository that imported `synthDrivers.WorldVoice.pipeline.<name>` breaks; refactor8 §2.1 and a scan of `ref/` found none.

### 5.2 Module boundaries

The table in §2.1 follows refactor8 §2.1 with these differences, each forced or argued by the code:

- **`wrap_numbers_for_detection`, `detect_with_number_language` and `_split_numbers_for_language` go to `numberStages.py`, not `languageCommands.py`.** `inject_numbers` needs `remove_language_command` (`pipeline/__init__.py:415`) and `deduplicate_language_command` (`:497`, `:519`), and `wrap_numbers_for_detection` needs `_split_numbers_for_language` (`:319`), which `_number_item_segments` uses too (`:552`). With the two detection functions in `languageCommands.py` the two modules would import each other. In `numberStages.py` the direction is one way (`numberStages → languageCommands`); `detect_with_number_language` is the number language applied to detection, and its docstring says so.
- **`item_wait_factor` gets its own `items.py`**, not `numberStages.py`: it is the item pause (setting `item_wait_factor`); it only meets numbers through the edge breaks of `breaks.py`.
- **`sequence.py` holds `SpeechCmd`, `_MISSING` and `_both_text`**: every stage module annotates with `SpeechCmd`, and `_MISSING`/`_both_text` are used by both the item stage (`:194`, `:200`) and the number pause (`:165`, `:270`). Without this module either `numberStages` would import `items` for two helpers, or `languageCommands` would import `breaks` for a type alias.
- **`_plain_breaks`/`_plain_break` go to `breaks.py`**, not `registry.py`: they read and set `_EDGE_MARKER` (`:1040-1045`), which stays private to `breaks.py`'s marker helpers.
- **`listable`, `speech_viewer` and `apply_speech_dictionaries` go to `registry.py`**: the two stages are a few lines each; `listable` makes a sequence function an NVDA filter, which the synth uses for language detection (`__init__.py:275`).

Ruling: eight modules instead of refactor8's six (`sequence.py` and `items.py` added; detection wrapping in `numberStages.py`; plain breaks in `breaks.py`) — the six-module split has an import cycle and puts the item pause under numbers — cost if wrong: one more file to open per stage family; nothing outside `pipeline/` names these modules except the synth, the global plugin and the tests.

Dependency direction after the split (no cycle): `registry → {items, numberStages, punctuation, unspaced, breaks, sequence, recorder, context, settings, speech_dictionary}`; `numberStages → {languageCommands, breaks, sequence, numbers, symbols, context}`; `items, punctuation → {breaks, sequence, context}`; `unspaced → {sequence, context, unspaced_common_data, languageDetection.scripts}`; `languageCommands → {sequence, context, runtime.models, speechCommands}`; `breaks → sequence`; `scope → registry`. Nothing in `pipeline/` imports `registry` except `scope.py`.

### 5.3 The recorder (F6)

`pipeline/recorder.py` (moved from `log.py`) drops the import-time path computation (`log.py:6-9`); `PipelineLog(log_file)` takes the file. The owner of `pl` passes it:

```python
# The pipeline log is addon/log/pipeline.csv; parents[3] of a module in pipeline/ is addon/.
pl = PipelineLog(Path(__file__).resolve().parents[3] / "log" / "pipeline.csv")
```

The line is written in `pipeline/__init__.py` by the F6 commit and moves to `registry.py` with the split. refactor8 §2.6 suggested injecting the path from the synth or the global plugin. `pl` is created when the pipeline is imported and used by the global plugin's export even when WorldVoice is not the synth (`globalPlugins/WorldVoice/pipelineLog.py:43`); injecting later would leave a window with no file, and `synthDrivers/WorldVoice/__init__.py` computes its add-on root (`__init__.py:66`) only after importing the pipeline (`:37`). A test pins the result: the real `PipelineLog` built from the arguments `pl` was given writes `ADDON / "log" / "pipeline.csv"`.

Ruling: the recorder takes its file; `pl`'s owner computes `addon/log/pipeline.csv` from its own `__file__` once, with the depth stated next to it and pinned by a test — injection from the synth or the global plugin would add a window without a file — cost if wrong: moving `registry.py` again needs that index changed, and the pin test fails until it is.

### 5.4 Say All (F8)

`pipeline/sayAll.py` (moved from `sayAll.py`) imports `.context` and `.settings` instead of `.pipeline.context` and `.pipeline.settings`; NVDA's three-line copyright header becomes a module docstring. The global plugin imports `synthDrivers.WorldVoice.pipeline.sayAll`. Nothing re-exports it.

### 5.5 Tests

- `tests/pipeline_harness.py` loads the empty package and imports `pipeline.registry` (which imports every stage module), and returns a `PipelineModules` view: a read of a name comes from the first of the pipeline modules that defines or imports it, so the ~440 reads of `module.<name>` in the stage tests stay as they are; **setting an attribute on the view raises**, so a patch that still names the package instead of the module that looks the name up fails loudly instead of silently patching nothing. The stub `synthDrivers.WorldVoice.log` becomes `synthDrivers.WorldVoice.pipeline.recorder`; its `PipelineLog` keeps the arguments it was given and still has no `write`, so a test that logs must replace `pl`.
- **Retargeted patches.** Every patch the stage handler reads goes to `module.registry` (where `_stage_handler`, `_run_logged`, `_LogWriter.write` and `register_stages` look the names up): `current_context`, `pl`, `log`, `pipeline_settings`, `filter_speechSequence`, `read_stored` in `tests/test_pipeline_stages.py`, `test_pipeline_filters.py`, `test_pipeline_nvda_ssml.py`, `test_pipeline_number_edges.py`; `pl` on the registry stub in `tests/test_settings_panels.py:620`. The dry run checks with a throw-away pytest plugin that each patched value is read by the code under test.
- Wiring by dotted name or path: `tests/nvda_stubs.py:110` (`STAGES` read from `pipeline/registry.py`), `tests/test_pipeline_number_edges.py:65` (`pipeline.breaks`), `tests/ui_harness.py:781` (`LOG_SWITCHES` stub on `pipeline.registry`) and `:874` (`pipeline.sayAll`), `tests/test_pipeline_log.py:34` (`pl` stub on `pipeline.registry`), `tests/test_runtime_composition.py:598-611` (stubs per module), `tests/test_pipeline_scope.py:10-12` (stub `registry` module), `tests/test_worldvoice_speak.py:148`, `:181-184`, `tests/test_say_all.py:53`, `tests/test_pipeline_log.py:12`, `:110-114` and `tests/test_pipeline_log_rotation.py:9-11` (the recorder by its new path; the fixtures pass the file instead of patching `log_dir`).
- `tests/test_pipeline_structure.py::test_pipeline_package_keeps_only_stages_logging_and_registry` checks each of the eight new modules instead of the package file (parametrized: +7 tests).
- New tests: `test_the_pipeline_log_is_written_to_the_add_on_log_folder` (F6), `test_number_lexing_imports_by_its_package_path_without_nvda` (A2), `test_package_init_stays_empty[pipeline]`.

Expected counts: base 3226 passed, 0 skipped; after F6 3227; after F8 3227; after F1 3236 (+7 parametrized, +1 A2 guard, +1 empty `__init__.py`).

## 6. Test plan

- Unit: the whole suite, unchanged assertions, at every commit; the three new tests and the parametrized structure test written red first.
- Patch observation (dry run, not committed): every value patched onto `pipeline.registry` is wrapped to record a call or attribute read; each patch must be read in at least one parametrization of its test, and the ones never read must be exactly those whose test asserts that nothing was written.
- Pure move: the split is done by the plan's script, which takes each top-level chunk of the old `__init__.py` verbatim; `git diff --color-moved` of the split commit shows only moved lines apart from the new module headers, the emptied `__init__.py` and the listed import lines.
- mutmut: not run; no decision logic changes (§7 asks for it only when core decision modules change behavior).
- Windows/NVDA manual: none required by the spec; the import order at NVDA start is covered by `tests/test_runtime_composition.py` and `tests/test_worldvoice_speak.py` (real imports of the new modules). Not packaged, not verified on Windows.

## 7. Open questions

None. The three Rulings above keep user-visible behavior unchanged; Decided by orchestrator with the recommended default; user may override before merge.
