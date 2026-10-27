# Phase 42: split the settings dialog into `panels/` and `dialog.py`

Date: 2026-10-27.
Base: `master` `a7bd115` (phase 43 merged). Branch: `phase42-settings-panels`.
Source: round-9 review `storage/refactor9.md` §4.1 **F2** (with its 2026-10-27 revision on `_as_bool`), §5.2 target tree, §5.3 first row, §6 row **P42**, §6.1 (layered naming rule, decided by the user 2026-10-27). refactor9 cites `master` `85bcf54` (731 lines); phase 43 changed the Unicode Detection panel since, so every line number below is that of `a7bd115` (737 lines), checked in this worktree.
Status: automatic flow (DEVELOPMENT_WORKFLOW.md §3), run as the **complex flow** (§4). No user-visible behavior change in goals 1–3; goal 4 has one, see §9.

Paths are under `addon/globalPlugins/WorldVoice/` unless stated.

## 0. Why the complex flow

About 700 lines move verbatim out of one module into seven new ones, and eleven test files and harnesses name the dialog by path, by dotted module name or by attribute. DEVELOPMENT_WORKFLOW.md §4.0 lists "大範圍的機械式修改 … 必須證明沒有夾帶其他修改" as a complex-flow case. The plan therefore carries byte-exact `File:`/`Edit:` blocks, a split script embedded in the plan for the verbatim move (the phase 38 precedent), a check that the move adds nothing but module headers, and the expected `HEAD:addon`/`HEAD:tests` tree ids after every commit; it is dry-run in a fresh clone before it is applied (§4.2–4.4). The two deduplications are separate commits after the pure move, so `git diff --color-moved` of the move stays readable.

## 1. Problem

1. **One module is six settings UIs** (F2). `speechSettingsDialog.py` (737 lines) holds `BaseSettingsPanel` (`:64-122`, settings described as a dict of dicts), `SpeechPipelinePanel` (`:125-168`, table driven), `SpeechRoleSettingsPanel` (`:171-477`, the wx side of `rolePresenter.RolePanelPresenter`), `UnicodeDetectionSettingsPanel` (`:480-572`), `SpeechEngineSettingsPanel` (`:575-646`), `LogSettingsPanel` (`:649-713`) and `WorldVoiceSettingsDialog` (`:716-737`), plus the log-switch labels (`:39-49`, used only by the Log Record panel), `got_error_callback` (`:52-55`, used only by the Speech Role panel) and `_as_bool` (`:58-61`, used only by `BaseSettingsPanel`). Its import block (`:1-35`) serves all of them at once, so no reader can tell which panel needs what.
2. **The "not WorldVoice" notice is written twice.** The read-only `wx.TextCtrl` with "Your current speech synthesizer is not WorldVoice." is the same eight lines at `:179-185` (Speech Role) and `:487-493` (Unicode Detection).
3. **The settings error dialog is written twice.** `SpeechRoleSettingsPanel.onSave` (`:467-475`) and `utils.py:28-39` (`guard_errors`) build the same `gui.messageBox` (same message, title and `wx.OK | wx.ICON_ERROR`).
4. **Finding: the two copies of the error dialog are not translated alike.** `utils.py` uses `_` (`:30`, `:36`) but never calls `addonHandler.initTranslation()` (it is the only add-on module with a gettext call and no such call). NVDA's `initTranslation` binds `_` in the calling module only (`ref/nvda/source/addonHandler/__init__.py:975-981`), so `utils.py` reaches the builtin `_` that NVDA installs for its own catalog (`ref/nvda/source/languageHandler.py:353`). NVDA's catalog has neither string (`grep` of `ref/nvda/source` finds neither), so the dialog of a failing role-panel handler is English in every language, while the same dialog from a failed role-panel save (`speechSettingsDialog.py:37`, `initTranslation` called) is translated (`addon/locale/zh_TW/LC_MESSAGES/nvda.po:23-43`, which already lists `utils.py:31`/`:36` as sources). Any single shared helper has one `_`, so sharing it changes the language of one of the two paths (§9).
5. **The translation template would miss the new modules.** `buildVars.py:60-66` `pythonSources` (which `sconstruct:130-137` hands to xgettext for `scons pot`) covers `addon/globalPlugins/*/*.py` but not a subpackage of the plugin, so the panels' strings would drop out of `WorldVoice.pot`.

## 2. Goals

1. **Split** (F2, refactor9 §5.2). Every top-level definition moves verbatim, in its original order, with the comment lines right above it:

   | Module | Holds |
   | --- | --- |
   | `panels/__init__.py` | nothing (0 bytes) |
   | `panels/base.py` | `_as_bool`, `BaseSettingsPanel`; goal 2 adds `notWorldVoiceNotice` |
   | `panels/pipeline.py` | `SpeechPipelinePanel` |
   | `panels/role.py` | `got_error_callback`, `SpeechRoleSettingsPanel` |
   | `panels/detection.py` | `UnicodeDetectionSettingsPanel` |
   | `panels/engine.py` | `SpeechEngineSettingsPanel` |
   | `panels/log.py` | `_STAGE_LOG_LABELS`, `_SETTING_NAMES`, `_LOG_LABELS`, `LogSettingsPanel` |
   | `dialog.py` | `WorldVoiceSettingsDialog` |

   - Each module gets a one-line docstring, the imports it uses (absolute `synthDrivers.WorldVoice.…` imports as before; `..utils`, `..rolePresenter`, `..pipelineLog` and `.base` relative) and its own `addonHandler.initTranslation()` (problem 4: without it a moved panel would show English in NVDA, and the tests' identity `_` could not tell).
   - `speechSettingsDialog.py` is deleted; no compatibility module (it is internal to the global plugin, refactor9 §5.3). `__init__.py:22` imports `WorldVoiceSettingsDialog` from `.dialog`.
   - `dialog.py` imports the five panel classes it lists (`:723-735`); the categories and their order are unchanged.
   - `buildVars.py` `pythonSources` gains `'addon/globalPlugins/*/*/*.py'`. The user's uncommitted `addon_version` change in the main checkout is a different line; see §10.
   - Translator comments and msgids move with their strings: no `.po` change.
2. **One "not WorldVoice" notice.** `panels/base.py` gets `notWorldVoiceNotice(panel, sizer)`, which adds the same `wx.TextCtrl` (same value, style flags, background colour, `proportion=1`, `flag=wx.EXPAND`) to `sizer`. Both panels call it where they built the control; each still sets `self.disable = True` and returns. The helper carries a `# Translators:` comment (the copies had none; the msgid is unchanged).
3. **`_as_bool` stays local** in `panels/base.py`, moved unchanged with its only user. *Decided by orchestrator with the recommended default; user may override before merge.* refactor9 suggested importing `engineRegistry.discovery.coerce_bool` (`synthDrivers/WorldVoice/engineRegistry/discovery.py:31-34`, the same body); its 2026-10-27 revision doubts it: it would make the dialog depend on the discovery module for a four-line helper, and `engineRegistry/` is "待定" in §6.1. The dialog gains no import of `engineRegistry.discovery`.
4. **One settings error dialog** (*Decided by the user (2026-10-27)*: option (a) of §9, no changelog line). `utils.py` gets `reportError(error)`, which shows the existing message (`Details: {err}` filled with `str(error)`), title and style; `guard_errors` and `SpeechRoleSettingsPanel.onSave` call it. The log lines (`Unhandled exception in …`, `Failed to save voice settings`), the callback and the `ValueError` that keeps NVDA's dialog open (`:476-477`) stay where they are. `utils.py` calls `addonHandler.initTranslation()`, the two strings get `# Translators:` comments, and the guard of problem 4 loses its one exemption.
   - **Ruling (placement):** refactor9 §5.2 puts `report_error` in `panels/base.py` and has `utils.py` import it. This phase puts `reportError` in `utils.py` next to `guard_errors`: the decorator module would otherwise depend on the panels package (and on `SettingsPanel`, `config`, `tones` through it), and `tests/ui_harness.py` `load_utils` loads `utils.py` without a package, so a relative import would need harness changes. Cost if wrong: one function moves between two modules of the same package.

## 3. Non-goals

- No change to what an NVDA user sees or hears in goals 1–3: panel list and order for WorldVoice and for another synthesizer, controls, labels, focus, values saved, prompts and restart behavior stay identical. No readme or changelog entry for them.
- No rename of an existing name (refactor9 §6.1: phase 47 does that), no change to the wx bindings, no presenter for the other panels, no change to `BaseSettingsPanel`'s dict description (refactor9 F2 keeps it).
- No change to `ui/` in the synth package, to `rolePresenter.py` or `pipelineLog.py`.
- `tests/` keep their snake_case helper names (the project's test convention; §6.1's camelCase rule is for the add-on's host-layer code).

## 4. Naming (refactor9 §6.1)

`globalPlugins/` is NVDA host layer: the new functions are mixedCase, `notWorldVoiceNotice` and `reportError` (refactor9 sketched `not_worldvoice_notice` and `report_error`). Module file names are single lower-case words (`base`, `pipeline`, `role`, `detection`, `engine`, `log`, `dialog`), as refactor9 §5.2 lists them and as the project already names modules.

## 5. Affected layers and files

| File | Change |
| --- | --- |
| `speechSettingsDialog.py` | deleted (split) |
| `dialog.py`, `panels/{__init__,base,pipeline,role,detection,engine,log}.py` | new (split); goal 2 edits `base`, `role`, `detection`; goal 4 edits `role` |
| `__init__.py` | `:22` import from `.dialog` |
| `utils.py` | goal 4: `reportError`, `initTranslation()` |
| `buildVars.py` | one glob |

Only the global plugin changes. No engine, driver wrapper, `runtime/`, `bridge/`, synth-side `ui/` or `pipeline/` change. Protected paths untouched; engine drivers stay independently installable.

## 6. Dialog, panels, focus, names NVDA reads

Unchanged in goals 1–3. `WorldVoiceSettingsDialog` still lists Speech Pipeline, Speech Role, Speech Engine, Unicode Detection, Log Record when WorldVoice is the synthesizer and Speech Pipeline, Speech Engine, Log Record otherwise (`speechSettingsDialog.py:722-735`); the panel classes are the same objects under new modules, so NVDA's category list, titles and initial focus (`SpeechRoleSettingsPanel.postInit`) do not change. Goal 4 changes only the language of the error dialog of a failing role-panel handler (§9).

## 7. Strings

No new or changed msgid. Three `# Translators:` comments are added (the notice; the error message and title), which `scons pot` picks up; no `.po` edit is needed, translators see the comments at the next merge. The catalogs' `#:` source references (`addon/locale/*/LC_MESSAGES/nvda.po`) keep naming `speechSettingsDialog.py` until that merge rewrites them; they are not edited by hand. Suggested zh_TW: unchanged entries (`nvda.po:23-43` already translate the two error strings; the notice keeps its current translation).

## 8. Tests

Path and loader updates (assertions unchanged unless listed):
- `tests/ui_harness.py:731-809` `load_settings_dialog` loads `utils`, the six panel modules (alias package `<package>.panels`) and `dialog.py`; `env.module` is the dialog module (it imports the five panel classes, so `env.module.<Panel>` keeps working) and `env.panels.<name>` each panel module. `:902` `load_global_plugin` stubs `<package>.dialog`.
- Patches move to the module that looks the name up: `RolePanelPresenter` → `env.panels.role` (`tests/test_role_panel_ui.py:69`), `pipeline_log` → `env.panels.log` (`tests/test_settings_panels.py:626`), `PIPELINE_SETTINGS` → `env.panels.pipeline` (`:194`), `pipeline_settings` → `env.panels.pipeline` (`tests/test_pipeline_panels.py:67-69`); reads of `_LOG_LABELS`, `_STAGE_LOG_LABELS`, `PIPELINE_SETTINGS`, `BaseSettingsPanel`, `panel_specs`, `pipeline_attribute` name their panel module. Each patched test asserts the patched effect, so a patch that misses fails.
- `load_definitions` users name the new file: `tests/test_role_panel.py:8` (`panels/role.py`), `test_unicode_panel.py:11` (`panels/detection.py`), `test_pipeline_log.py:14` (`panels/log.py`), `test_role_guards.py:7` (`panels/role.py`), `test_ui_structure.py:13` (`panels/role.py`, `panels/pipeline.py`), `test_settings_panel_save.py:9` (`panels/base.py` then `panels/engine.py` into one namespace).
- Guards keep or gain strength: the `._voiceManager` and `getSynth` bans already scan the plugin with `rglob` (`tests/test_ui_structure.py:31-35`, `:107-119`); the `.wvd` ban (`test_role_guards.py:11`), the phase-43 "the dialog imports only `languageDetection.settings`/`.scriptLanguages`" guard (`test_unicode_panel.py:181-195`) and the "no dependency logic outside `ui/controls.py`" names check (`test_ui_structure.py:64-82`) widen from the one dialog file to every module of the plugin; the msgid overlap check (`test_pipeline_panels.py:195-224`) reads `dialog.py` and every panel module.

New tests (red first where a red exists):
- `tests/test_translator_comments.py::test_every_translated_module_installs_the_add_on_catalog` — every add-on module (vendored inner drivers excluded, as in the file's other guards) with a `_`/`pgettext`/`ngettext`/`npgettext` call has a top-level `addonHandler.initTranslation()`. Until goal 4 the result must equal `["globalPlugins/WorldVoice/utils.py"]` (problem 4), then `[]`. A throw-away probe (plan Task 1) deletes the call from `panels/role.py` and sees it fail.
- `tests/test_translator_comments.py::test_every_translated_module_is_a_pot_source` — every such module matches a `buildVars.pythonSources` glob (read with `ast`). Red after the split until the glob is added.
- `tests/test_ui_structure.py::test_panels_package_init_stays_empty` — `panels/__init__.py` is 0 bytes, the package-init policy of `tests/test_runtime_import_guard.py:55-64`.
- `tests/test_ui_structure.py::test_panels_share_the_not_worldvoice_notice` (refactor9 `test_panels_share_the_not_worldvoice_notice`) — the notice string is a constant exactly once in the plugin, in `panels/base.py`.
- `tests/test_settings_panels.py::test_panels_for_another_synth_show_the_same_read_only_notice[Speech Role, Unicode Detection]` — characterization, green before and after goal 2: one sizer item, a `TextCtrl` child of the panel with the value, exactly the four style flags, the panel's background colour, `proportion=1`, `flag=wx.EXPAND`.
- Goal 4: `tests/test_ui_structure.py::test_settings_errors_share_one_dialog` (message and title constants once, in `utils.py`); `tests/test_role_panel_ui.py::test_a_failed_save_reports_the_error_and_keeps_the_dialog_open` (real `utils`: the shown message, title and style, the log line, `ValueError`); `tests/test_role_panel.py` supplies `reportError` instead of `gui`/`wx`.

Existing `tests/test_guard_errors.py` (message, title, style, callback, interrupts) stays unchanged and green.

No mutmut run: no decision logic changes. Manual Windows/NVDA items: none required for goals 1–3; optional smoke check: open NVDA menu → WorldVoice → Settings with WorldVoice and with another synthesizer; the same panels appear in the same order. For goal 4 (if approved), in a non-English NVDA a failing role-panel handler now shows the translated error dialog; this cannot be triggered on purpose without a fault.

## 9. Open questions

1. **Goal 4 changes a user-visible detail.** Sharing the error dialog in one translated place makes the dialog of a failing Speech Role handler (`guard_errors`) appear in the user's language instead of always in English (problem 4); the English text, the title and the style stay the same. *Decided by the user (2026-10-27):* option (a) — share `reportError` in `utils.py`, which now calls `initTranslation()` (goal 4); the translations already exist in every catalog. The alternatives were (b) skipping this deduplication and (c) sharing it in a module without `initTranslation()` (the failed-save dialog would have turned English). Plan Task 3 implements (a).
   - *Decided by the user (2026-10-27):* no changelog line in `readme.md` or `addon/doc/{ru,uk,zh_CN,zh_HK,zh_TW}/readme.md` for this error-path translation fix.
2. `_as_bool` placement (goal 3) — decided by orchestrator with the recommended default; user may override before merge.
3. `reportError` in `utils.py` rather than `panels/base.py` (goal 4 Ruling) — reported to the orchestrator.

## 10. Settings, compatibility, errors

- No config key, default or stored value changes; no migration.
- NVDA installs an add-on update into a fresh directory, so the deleted `speechSettingsDialog.py` leaves no stale module behind.
- Merge note: the main checkout has an uncommitted `buildVars.py` change (`addon_version`); this branch also changes `buildVars.py` (the glob), so `git merge --ff-only` there will refuse to overwrite the local change until the user commits or sets it aside. (Resolved 2026-10-27: the main checkout no longer has that change.)
