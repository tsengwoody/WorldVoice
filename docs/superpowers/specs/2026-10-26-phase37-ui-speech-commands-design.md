# Phase 37: `ui/` package and `speechCommands.py`

Date: 2026-10-26.
Base: `master` `1f7fa46` (phase 36 merged). Branch: `phase37-ui-speech-commands`.
Source: round-8 review `storage/refactor8.md` §6 "階段 37" — findings F3 (§2.3), F7 (§2.7), the F11 item about `worldvoice_synth` (§2.11) and A2 (§4.2). The review predates phase 36; paths below are those of the current `master`.
Status: automatic flow (DEVELOPMENT_WORKFLOW.md §3), run as the **complex flow** (§4).

## 0. Why the complex flow

This phase is a wide mechanical move and rename: four add-on modules change name or package, and about twenty test files, harnesses and `pyproject.toml` name them by path or by dotted name. DEVELOPMENT_WORKFLOW.md §4.0 lists "大範圍的機械式修改 … 必須證明沒有夾帶其他修改" as a complex-flow case. The plan therefore carries byte-exact `File:`/`Edit:` blocks and the expected `HEAD:addon`/`HEAD:tests` tree ids after every commit, and is dry-run in a fresh clone before it is applied (§4.2–4.4).

## 1. Problem

All paths below are under `addon/synthDrivers/WorldVoice/` unless stated.

1. **The synth-side settings UI is spread over three places** (F3).
   - `VoiceSettingsDialogs.py` (root) holds the one class `WorldVoiceVoiceSettingsPanel` (`VoiceSettingsDialogs.py:37`): a panel, not dialogs, and the only PascalCase file name in the package.
   - `pipelineControls.py` (root) builds, reads and locates the pipeline-setting controls of both panels (`pipelineControls.py:1-8`); it imports `wx` and `gui` (`:13-14`).
   - `pipeline/panelLayout.py` holds the pure layout rules both panels follow (`pipeline/panelLayout.py:1-6`). Nothing in `pipeline/` imports it; its importers are `pipelineControls.py:16`, `VoiceSettingsDialogs.py:7` and `globalPlugins/WorldVoice/speechSettingsDialog.py:18`.
2. **`_speechcommand.py` reads as private, but four packages import it** (F7): `pipeline/__init__.py:14`, `languageDetection/__init__.py:3`, `bridge/commands.py:7`, `bridge/indexCodec.py:9`. The all-lower-case singular name also breaks the package's camelCase module names.
3. **"Loads without wx or NVDA" holds only in the tests** (A2). `pipeline/panelLayout.py:3-4` says it has "no add-on, wx or NVDA import, so tests and mutmut can load this module on its own". The tests load it by file (`tests/test_panel_layout.py:14`, `tests/test_settings_table_guard.py:16`); the global plugin imports it as `synthDrivers.WorldVoice.pipeline.panelLayout`, which first runs `pipeline/__init__.py` and with it `import config`, `speechDictHandler`, `speech.extensions` (`pipeline/__init__.py:8-12`).
4. **`worldvoice_synth()` looks like pipeline-only code** (F11). It sits in `pipeline/context.py:25-28`; besides `current_context()` (`:33`) the global plugin's settings dialog uses it to reach the voice manager (`globalPlugins/WorldVoice/speechSettingsDialog.py:17`, `:177`, `:192`, `:456`, `:485`, `:556`, `:716`).

## 2. Goals

1. New package `ui/` with an **empty** `__init__.py`:

   | From | To |
   | --- | --- |
   | `pipeline/panelLayout.py` | `ui/panelLayout.py` |
   | `pipelineControls.py` | `ui/controls.py` |
   | `VoiceSettingsDialogs.py` | `ui/voicePanel.py` |

   `ui/__init__.py` must stay empty: `ui/controls.py` imports `wx`, so any re-export there would make `ui.panelLayout` need wx too.
2. Rename `_speechcommand.py` → `speechCommands.py`.
3. A2 guard: a test imports `synthDrivers.WorldVoice.ui.panelLayout` by its package path, with `wx`, `gui` and NVDA's `config`, `speech`, `synthDriverHandler`, `logHandler`, `addonHandler` made unimportable, and checks that only `ui` and `ui.panelLayout` are loaded from the add-on. Written test first.
4. F11 `worldvoice_synth`: see §5.3 (stays in `pipeline/context.py`; its docstring names both users).
5. Every importer, test, harness, guard, comment and docstring in `addon/` and `tests/` follows the new paths; `pyproject.toml` `[tool.mutmut] source_paths` follows them too. (No ruff per-file ignore names these files.)
6. Every move uses `git mv` and keeps the file's content apart from import lines and the edits listed here.

## 3. Non-goals

- No behavior change. NVDA users hear and see nothing new; no new or changed UI string (none of the moved modules has a translatable string), so no translation work.
- No class, function or attribute rename: `WorldVoiceVoiceSettingsPanel`, `WVLangChangeCommand`, `WorldVoiceIndexCommand` and every function of the moved modules keep their names. Test helpers `load_voice_settings_dialogs` and `load_pipeline_controls` (`tests/ui_harness.py`) and the `speechcommand` fixture/local names in tests keep their names too (see §5.5).
- `globalPlugins/WorldVoice/speechSettingsDialog.py` stays where it is: the dialog is opened by the global plugin, the panel is patched in by the synth (refactor8 §2.3).
- No change to phase 38–39 items (F1, F4, F6, F8–F10, A3).
- Historical documents under `docs/` keep the old paths as written.

## 4. Constraints (DEVELOPMENT_WORKFLOW.md §8, refactor8.md §0)

- Public import paths do not change: `synthDrivers.WorldVoice.driver` (`Voice`, `getVoiceKey`), `runtime.{engineControl, models, playbackWork, segmentHost, session}`, `text.arabic`, `text.chunker`, `driver.sonic._sonic`. `tests/test_plugin_voice_contract.py` passes unchanged.
- Never modify `driver/<Engine>/driver/`, `driver/sonic/`, `languageDetection/script_data.py`, `pipeline/unspaced_common_data.py`. Engine drivers stay independently installable. No Neural, no `ref` in commits.
- Dependency direction after the phase: `ui.voicePanel → ui.controls → ui.panelLayout`, `ui.voicePanel → pipeline.settings`; `pipeline`, `languageDetection`, `bridge → speechCommands`. Nothing outside `ui/` and the global plugin imports `ui/`; `pipeline/` never imports `ui/`.
- ruff pinned `==0.16.3`; files as prek leaves them.

## 5. Design

### 5.1 `ui/`

```
ui/
├── __init__.py      empty (new)
├── controls.py      ← pipelineControls.py
├── panelLayout.py   ← pipeline/panelLayout.py (content unchanged)
└── voicePanel.py    ← VoiceSettingsDialogs.py
```

Import changes (ruff's isort orders them; the plan holds the sorted result):

- `ui/controls.py`: `from .pipeline.panelLayout import (` → `from .panelLayout import (`; its docstring's "pipeline/panelLayout.py" → "ui/panelLayout.py".
- `ui/voicePanel.py`: `.pipeline.panelLayout` → `.panelLayout`, `.pipeline.settings` → `..pipeline.settings`, `.pipelineControls` → `.controls`.
- `__init__.py:60`: `from .VoiceSettingsDialogs import WorldVoiceVoiceSettingsPanel` → `from .ui.voicePanel import WorldVoiceVoiceSettingsPanel`. The NVDA patch (`__init__.py:209`, `patch_attribute(gui.settingsDialogs, "VoiceSettingsPanel", WorldVoiceVoiceSettingsPanel)`) takes the class object; the string is NVDA's attribute name (`ref/nvda/source/gui/settingsDialogs.py`), not a module path, so it is unchanged. No other code names the old module by string.
- `globalPlugins/WorldVoice/speechSettingsDialog.py:18-31`: `synthDrivers.WorldVoice.pipeline.panelLayout` → `synthDrivers.WorldVoice.ui.panelLayout`, `synthDrivers.WorldVoice.pipelineControls` → `synthDrivers.WorldVoice.ui.controls`.
- Translation sources: `buildVars.pythonSources` already covers `addon/synthDrivers/*/*/*.py`, so `ui/*.py` stays in the `.pot` scan.

### 5.2 `speechCommands.py`

`git mv _speechcommand.py speechCommands.py`, content unchanged. `pipeline/__init__.py`, `languageDetection/__init__.py`, `bridge/commands.py`, `bridge/indexCodec.py` import `..speechCommands` (isort moves the line after `..runtime.…` / `..numberLanguage`).

### 5.3 `worldvoice_synth` (F11)

Ruling: `worldvoice_synth()` stays in `pipeline/context.py`; only its docstring changes, naming both users and why it is not in `ui/`.

- Moving it to `ui/` would make `pipeline/context.py` (`current_context`, `:33`) import `ui/` — the wrong direction (the settings UI depends on the pipeline settings, not the other way round).
- Moving it to a new root module would add a module and change the import in `pipeline/context.py`, the dialog and the guard `tests/test_pipeline_structure.py::test_only_the_context_asks_nvda_for_the_synth`, which names `context.py` as the one place the pipeline reaches the synth. It would buy no dependency: the dialog already imports `synthDrivers.WorldVoice.pipeline` (`LOG_SWITCHES`, `speechSettingsDialog.py:16`) and `pipeline.settings` (`:24`), and `pipeline/context.py` itself imports only `synthDriverHandler` (`:4`).
- So the smallest change that removes the "pipeline-only" reading is the docstring.

### 5.4 A2 guard

New test in `tests/test_ui_structure.py`:

```text
test_panel_layout_imports_by_its_package_path_without_wx_or_nvda
```

- Removes every cached `synthDrivers*` module (monkeypatch), sets `wx`, `gui`, `config`, `speech`, `synthDriverHandler`, `logHandler`, `addonHandler` to `None` in `sys.modules` (an import of them then fails), aliases `synthDrivers` and `synthDrivers.WorldVoice` (the real `__init__.py` of the synth is not run, as in every harness), then `importlib.import_module("synthDrivers.WorldVoice.ui.panelLayout")`.
- Asserts the module's `__file__` is `ui/panelLayout.py` and the loaded `synthDrivers*` modules are exactly `synthDrivers`, `synthDrivers.WorldVoice`, `synthDrivers.WorldVoice.ui`, `synthDrivers.WorldVoice.ui.panelLayout`.
- Removes the two modules the import registered itself in a `finally`, so no later test sees them.
- Red before the move (`ModuleNotFoundError: No module named 'synthDrivers.WorldVoice.ui'`). After the move it is green, and it turns red when `ui/__init__.py` imports `controls` (`import of wx halted`), imports `..pipeline.settings` (`import of config halted`), or imports any other add-on module (the loaded-modules assertion). The plan runs the first of these as an uncommitted check.

### 5.5 Tests and harnesses

- Path constants and dotted names follow §5.1/§5.2: `tests/test_ui_structure.py` (`VOICE_PANEL`, `PIPELINE_CONTROLS`, the import-source assertion becomes `(1, "panelLayout")`, one comment), `tests/ui_harness.py` (aliases `synthDrivers.WorldVoice.ui`; `load_source` names and paths; two docstrings), `tests/test_panel_layout.py`, `tests/test_settings_table_guard.py`, `tests/test_pipeline_controls.py`, `tests/test_pipeline_panels.py`, `tests/test_voice_settings_panel.py` (docstring), `tests/test_runtime_composition.py` (the stub of the panel module), `tests/test_speech_command_contract.py`, `tests/pipeline_harness.py`, `tests/runtime_harness.py`, `tests/detector_harness.py`, `tests/test_format_outputs.py`, `tests/test_legacy_speech_commands.py`, `tests/test_worldvoice_index_command.py`, `tests/test_worldvoice_speak.py`.
- `tests/runtime_harness.py::forbid_legacy_runtime_imports` needs no new rule: ~~`ui/` imports `wx`/`gui`, already forbidden,~~ `ui/controls.py` imports `gui`, which the guard's forbidden set already holds (`wx` is not in that set; `import wx` fails on Linux anyway), and the runtime never imports `ui/`. Corrected by the phase 37 review fixes (M3).
- Helper and fixture names stay (`load_voice_settings_dialogs`, `load_pipeline_controls`, `speechcommand`): they name roles, are used in about twenty places, and renaming them would add churn without changing what a reader finds.

Expected counts: baseline 3224 passed, 0 skipped; after the phase 3225 passed, 0 skipped (+1 guard).

## 6. Settings, data, compatibility

No config key, confspec, stored value or UI string changes. A WorldVoice-workspace plugin imports only `synthDrivers.WorldVoice.driver`, which is unchanged. An installed add-on is replaced as a whole on update, so no stale `VoiceSettingsDialogs.py` remains next to `ui/`.

## 7. Test plan

- Unit: §5.4, §5.5; `tests/test_plugin_voice_contract.py` unchanged and green.
- Mutation: not needed — no logic changes; `pyproject.toml` `source_paths` follow the moved files so a later mutmut run still covers them.
- Full verification per DEVELOPMENT_WORKFLOW.md §7 after every commit.
- Windows/NVDA manual: none required (no behavior change). Not packaged, not verified on Windows. A later packaged build should still show WorldVoice's controls in NVDA's Voice settings panel and open the WorldVoice settings dialog.

## 8. Open questions

None. The F11 placement (§5.3) is a structural ruling with no user-visible effect.
