# Hide speech engines that cannot load from the Speech Engine panel

- Branch: `feat/hide-unavailable-engines` (normal flow, DEVELOPMENT_WORKFLOW.md §3), from `master` `d352a06`.
- Request (Decided by the user, 2026-11-07): in the WorldVoice "Speech Engine" panel an engine that cannot load is not shown at all — hidden, not grayed out. Motivating case: Vocalizer Expressive (VE), and likewise Cerence, whose DLLs are missing still shows a checkbox.
- D1–D8 (§2.2) are orchestrator defaults: `Decided by orchestrator with the recommended default; user may override before merge`.

## 0. Findings

### F1. The panel lists every discovered engine

`SpeechEngineSettingsPanel.makeSettings` builds one checkbox per `ENGINE_SPECS` entry (`addon/globalPlugins/WorldVoice/panels/engine.py:38-40`) and computes `previousActiveEngine` from the same list (`engine.py:44-48`). `discover_engine_specs` only needs a package `__init__.py` and a `manifest.json` (`addon/synthDrivers/WorldVoice/engineRegistry/discovery.py:52-72`, `:132-150`); nothing about whether the engine can run.

### F2. VE and Cerence are always "ready"

Neither wrapper overrides `ready()` (`driver/VE/__init__.py:894-965`, `driver/Cerence/__init__.py:903-977`), so the base `Voice.ready()` returns True (`driver/__init__.py:85-87`). The DLLs are loaded only when the core is created: `_initializeNative` (`driver/VE/__init__.py:398-404`) calls the inner `ve2.initialize`.

### F3. What the inner `initialize` loads (VE and Cerence differ)

- VE (`driver/VE/driver/ve2/__init__.py:86-97`): `module_dir` is nine `dirname`s above `ve2/__init__.py` plus `WorldVoice-workspace/VE` (`:90`); the architecture folder is `os.environ["PROCESSOR_ARCHITECTURE"]` (`:93`, a `KeyError` when unset); it loads `msvcr110.dll`, `ve.dll`, `vplatform.dll` from `lib/<arch>` (`:95-97`).
- Cerence (`driver/Cerence/driver/ttsapi/__init__.py:82-91`): same `module_dir` shape with `WorldVoice-workspace/Cerence` (`:85`), but the architecture folder is `"x64" if sys.maxsize > 2**32 else "x32"` (`:88`) and it loads only `ve.dll` and `vplatform.dll` (`:90-91`). The orchestrator's "same shape" assumption holds for the folder, not for the architecture name or the DLL list.
- Both put `module_dir/common` first in the resource list unconditionally (VE `:91`, Cerence `:86`), without checking it exists.

### F4. The inner path is derived from the inner file, not from `workspace_path()`

`workspace_path()` is `globalVars.appArgs.configPath/WorldVoice-workspace` (`addon/synthDrivers/WorldVoice/workspace.py:10-12`). The inner drivers derive the folder from their own `__file__` (F3). The two agree when the add-on runs from `<configPath>/addons/WorldVoice`, which is where NVDA runs add-ons, but only the inner derivation decides which file `LoadLibrary` opens.

### F5. Today a missing DLL costs an error with a traceback at every synth load

VE and Cerence are on by default (`driver/VE/manifest.json`, `driver/Cerence/manifest.json`: `"defaultEnabled": true`). `load_enabled_engine_classes` passes them (F2), `createCore` raises in `LoadLibrary`, and `VoiceManager._open_engine` logs `engine VE on error` with `exc_info` and skips the engine (`addon/synthDrivers/WorldVoice/voices/manager.py:94-99`). Every user without VE or Cerence files gets two such tracebacks per synth load.

### F6. The resource list is not a substitute check

Since `ea0d197`, `getResourcePaths` offers the workspace folder only when it exists (`driver/VE/driver/__init__.py:40-58`), but it also offers running voice add-ons and Freedom Scientific data under `PROGRAMDATA` (`:41`, `:48-57`), so it can be non-empty without any DLL. Voice data presence (`availableVoices`, `driver/VE/__init__.py:430-432`) needs the DLLs loaded.

### F7. The per-engine readiness check already exists, for enabled engines only

`load_enabled_engine_classes` (`discovery.py:160-223`) skips disabled specs (`:168`), imports the module (`:173`), requires a `Voice` export (`:175-178`) whose `engine` matches (`:179-186`), handles pre-rename contract names (`:187-215`, including the `synth_driver_class` mapping, a `setattr` on the plugin class with one warning, `:194-206`), calls `voice.ready()` (`:216-219`), and logs any exception and skips the engine (`:221-222`). It wraps each step in `timed` debug lines (`addon/synthDrivers/WorldVoice/bringup.py:39-46`).

### F8. Other `ready()` side effects

SAPI5's `ready()` re-assigns `synthDriverClass`/`drainProfile` on its class (same values each time) and, on NVDA before 2025.3, logs one info line (`driver/SAPI5/__init__.py:706-730`). eSpeak and OneCore check NVDA names (`driver/Espeak/__init__.py:229-240`, `driver/OneCore/__init__.py:684-695`). All are cheap and repeatable (`tests/test_nvda_ready.py:172` pins that a later check decides again).

### F9. Saving writes only the panel's own keys

`BaseSettingsPanel._writeSettings` writes only keys of `self.settings` (`addon/globalPlugins/WorldVoice/panels/base.py:62-81`); a checkbox reads its stored value or the spec default (`base.py:48-56`). NVDA keeps the dialog open when a panel's `isValid()` returns False (`ref/nvda/source/gui/settingsDialogs.py:759-764`, `:780`).

### F10. The zh_TW readme mentions the panel

`addon/doc/zh_TW/readme.md:89` ("若您想停用特定的語音引擎，請在 WorldVoice 語音引擎面板中取消勾選相應的核取方塊。"); the changelog has a `## 下一版更新` section (`readme.md:94-97`).

## 1. Problem

An engine whose files are missing still gets a checkbox, possibly checked (VE and Cerence default to on, F5), although WorldVoice can never load it; at every synth load it logs an error with a traceback.

## 2. Goals and non-goals

### 2.1 Goals (Decided by the user, 2026-11-07)

- G1. The Speech Engine panel shows only engines whose readiness check passes; others have no control at all.
- G2. VE and Cerence report not ready, without loading any DLL, when a DLL their inner `initialize` loads is missing.

### 2.2 Orchestrator defaults (Decided by orchestrator with the recommended default; user may override before merge)

- D1. **What VE/Cerence check:** exactly the DLLs the inner `initialize` loads (F3): VE `msvcr110.dll`, `ve.dll`, `vplatform.dll` in `lib/<PROCESSOR_ARCHITECTURE>`; Cerence `ve.dll`, `vplatform.dll` in `lib/x64` or `lib/x32`. Not the `common` folder (the inner adds it without checking, F3, and whether the engine starts without it is unknown — a false "unavailable" would hide a working engine, worse than today's visible checkbox) and not voice data (needs the DLLs loaded, F6). File existence only (`os.path.isfile`); a DLL that exists but fails to load still fails at `createCore` as today (F5).
- D2. **Which path:** derived as the inner does (nine folders above the inner module's file, F3/F4), not `workspace_path()`, so the check and `LoadLibrary` cannot disagree. A guard test runs the real inner `initialize` with `LoadLibrary` recorded and asserts it loads exactly the files `ready()` checks.
- D3. **Missing `PROCESSOR_ARCHITECTURE` (VE):** `ready()` reads it as `initialize` does, so it raises `KeyError`; the shared readiness check logs any exception as an error and treats the engine as unavailable (F7). Windows always sets it, so this is an anomaly worth an error line. Cerence has no such input.
- D4. **Log:** `ready()` returning False logs one info line, `WorldVoice VE engine is unavailable: missing <paths>` (full paths, all missing ones). It is logged on every check — once per synth load and once per panel open per unavailable engine — with no "already logged" state. Info is NVDA's default log level, so a user whose engine vanished from the panel can find out why. This replaces F5's error with traceback at synth load.
- D5. **No cache:** `available_engine_specs()` asks every engine again on each call (each panel open). Checks are cheap (F8, D1), modules import once per process, and restoring an engine's files makes it reappear at the next panel open without restarting NVDA. Cost: the info lines of D4, SAPI5's info line on NVDA < 2025.3 (F8), the `synth_driver_class` mapping warning of an old plugin (once per process: the mapping is idempotent, `discovery.py:197`), any import error of a broken plugin, and the `WorldVoice init timing: ready check …` debug lines (debug level only) repeat at each panel open.
- D6. **Disabled engines are checked too:** the panel imports and asks every discovered engine, enabled or not, since "cannot load" is independent of the flag. A disabled engine is therefore imported at the first panel open of the session (today only at enabling plus restart).
- D7. **No engine available:** the panel shows the info text and an empty group, and saves without any message (nothing to save, no restart prompt), so the settings dialog is never trapped by "no speech engine is enabled". In practice SAPI5's `ready()` is always True (F8).
- D8. **Strings and docs:** no new UI string (the panel just has fewer checkboxes). zh_TW readme: one sentence in `## 注意` and one entry in `## 下一版更新` (§6).

### 2.3 Non-goals

- RHVoice (its DLL is bundled, `driver/RHVoice/driver/__init__.py:152`; voices in the workspace) and external plugins get no new `ready()`; a plugin's own `ready()` already decides.
- No grayed-out or "(unavailable)" entries, no message about hidden engines.
- No change to the stored `engine` config, its spec, or `load_enabled_engine_classes` behaviour.
- No change to inner drivers (`driver/<Engine>/driver/`).

## 3. What an NVDA user hears and sees

- Without VE files: the Speech Engine panel no longer has a "VE" checkbox (likewise Cerence); Tab moves between the remaining checkboxes. Nothing else in the panel changes: same info text, same group label "Select Speech Engines to Enable".
- Pressing OK without changes never asks to restart because of a hidden engine, even if it is still enabled in the stored config.
- After copying the VE files into `WorldVoice-workspace/VE/lib/<arch>`, reopening the panel shows "VE" again with its previous checked state.
- The NVDA log at synth load shows `WorldVoice VE engine is unavailable: missing …` (info) instead of `engine VE on error` with a traceback.

## 4. Design

### 4.1 engineRegistry (NVDA-free `discovery.py`, snake_case)

- New `load_engine_class(spec: EngineSpec, logger: Any = None) -> type | None` in `discovery.py`: the body of the per-spec loop of `load_enabled_engine_classes` (`discovery.py:170-222`) moved verbatim (same `timed` labels, warnings, errors and mapping); returns the `Voice` class when every step passes and `ready()` is truthy, else None. Never raises: any exception is logged as `Failed to load ready state for <name>: <error>` and gives None.
- `load_enabled_engine_classes` keeps its signature and output: for each enabled spec, `load_engine_class(spec, logger=logger)`, keeping non-None results in spec order.
- New `available_engine_specs() -> tuple[EngineSpec, ...]` in `engineRegistry/__init__.py`: the specs of `ENGINE_SPECS`, in order, whose `load_engine_class(spec, logger=log)` is not None, regardless of the enabled flag (D5, D6).

### 4.2 VE and Cerence wrappers (NVDA layer, camelCase)

Each wrapper gets its own copy (drivers are independently installable; no driver imports another):

- `_engineWorkspace()` (identical in both after the drift test's `Cerence→VE`, `ttsapi→ve2` rewrite, `tests/test_vocalizer_drift.py:34-35`): nine `os.path.dirname`s above `ve2.__file__` (`ttsapi.__file__`), joined with `WorldVoice-workspace/VE` (`…/Cerence`), as F3.
- `_nativeFiles()` (engine-specific, added to the drift test's `ALLOWED`): VE `[<ws>/lib/<os.environ["PROCESSOR_ARCHITECTURE"]>/{msvcr110,ve,vplatform}.dll]`; Cerence `[<ws>/lib/<"x64" if sys.maxsize > 2**32 else "x32">/{ve,vplatform}.dll]`, in the inner's load order. Cerence gains `import sys`; the drift test allows that one import on the Cerence side only.
- `Voice.ready()` classmethod (identical in both): the missing files are those of `_nativeFiles()` that are not `os.path.isfile`; when any is missing, log D4's info line and return False; else True. Never loads a library.

### 4.3 Panel (`panels/engine.py`, NVDA layer)

- `makeSettings`: `available = available_engine_specs()` once; `self.settings` from `available` only; `self.previousActiveEngine` from `available` only (a hidden-but-enabled engine must not make `activeEngine != previousActiveEngine` and prompt for a restart at every OK).
- `isValid`: unchanged, except the "no speech engine is enabled" message is shown only when the panel has at least one checkbox (D7).
- `onSave`: unchanged. Hidden engines are not in `self.settings`, so their stored flags are never written (F9): restoring the files brings back the old state.

## 5. Panels, strings and documentation

- No new or changed UI strings; no `nvda.po` change.
- Focus and names: unchanged controls keep their labels; a hidden engine simply has no control.
- zh_TW readme (`addon/doc/zh_TW/readme.md`), after `readme.md:89`:
  `* 無法載入的語音引擎不會出現在 WorldVoice 語音引擎面板中，例如 WorldVoice-workspace 中缺少 Vocalizer Expressive 或 Cerence 的程式庫檔案（DLL）時。補上檔案後重新開啟面板，該引擎會再次出現，並保留原本的勾選狀態。`
  and in `## 下一版更新`:
  `* **隱藏無法載入的語音引擎：** WorldVoice 語音引擎面板不再顯示無法載入的語音引擎，例如缺少程式庫檔案的 Vocalizer Expressive 或 Cerence。這些引擎原本的啟用設定會保留，補上檔案後重新開啟面板即可再次看到。NVDA 記錄檔也只會以一行說明缺少哪些檔案，不再記錄錯誤。`
- Other languages and the root readme are synced later by the user's rule.

## 6. Settings, compatibility and errors

- Config: unchanged spec and keys; hidden engines keep their stored values (F9).
- Synth load: for VE/Cerence without files, `ready()` now returns False before `createCore`, so `ready_engine_classes` omits them (no traceback, F5). With files present nothing changes. If no enabled engine is ready, `VoiceManager` raises as before (`voices/manager.py:90-91`).
- Errors: any exception in a readiness check (import error, missing `PROCESSOR_ARCHITECTURE`, a plugin's `ready()` raising) hides that engine and logs one error line (D3, F7).
- Threads: the panel runs the checks on the GUI thread; VE/Cerence checks touch only the file system; SAPI5 re-assigns identical class values (F8).

## 7. Affected layers

| Layer | File | Change |
| --- | --- | --- |
| core, NVDA-free | `engineRegistry/discovery.py` | `load_engine_class` factored out |
| core | `engineRegistry/__init__.py` | `available_engine_specs()` |
| wrapper | `driver/VE/__init__.py`, `driver/Cerence/__init__.py` | `_engineWorkspace`, `_nativeFiles`, `Voice.ready` |
| GUI | `globalPlugins/WorldVoice/panels/engine.py` | available specs only |
| tests | `test_engine_discovery.py`, `test_engine_registry.py`, new `test_vocalizer_ready.py`, `test_vocalizer_drift.py`, `test_settings_panels.py`, `ui_harness.py` | |
| docs | `addon/doc/zh_TW/readme.md` | §5 |

## 8. Test plan

- Unit (`test_engine_discovery.py`): `load_engine_class` returns the ready class regardless of the enabled flag; returns None with the same warning/error lines for a missing `Voice`, an engine-name mismatch, unready, stale contract names and a raising import/`ready()`; existing `load_enabled_engine_classes` tests unchanged.
- Unit (`test_engine_registry.py`): `available_engine_specs()` keeps discovery order, includes a disabled-by-default ready engine, drops an unready and a raising one, and logs the error.
- Unit (new `test_vocalizer_ready.py`, VE and Cerence via `worldvoice_cancel_wrapper_harness.load_real_driver_with_native_stubs`): all files present → True, no log; each single file missing and none present → False with one info line naming exactly the missing paths; VE without `PROCESSOR_ARCHITECTURE` raises `KeyError`; `ready()` never calls `LoadLibrary`; guard: the real inner `initialize` with a recording `cdll` loads exactly `_nativeFiles()` (VE with `PROCESSOR_ARCHITECTURE` set; Cerence for both `sys.maxsize` cases).
- Guard (`test_vocalizer_drift.py`): `Voice.ready` and `_engineWorkspace` identical; `_nativeFiles` and Cerence's `import sys` allowed.
- Panel (`test_settings_panels.py` via `ui_harness.load_settings_dialog`, which gains `available_engine_specs` and `env.unavailable_engines`): a hidden engine has no checkbox and is not in `previousActiveEngine` even when stored on; OK without changes saves nothing and asks nothing; a change saves visible flags and leaves the hidden one's stored value; unchecking every visible engine still refuses; no available engine → no checkbox, no message, nothing written.
- Property/mutation tests: none; the logic is a filter with exhaustive unit cases (no core decision module changes, §7 of the workflow).
- Windows / NVDA manual: (M1) without `WorldVoice-workspace/VE` the panel has no VE checkbox and the log has the info line, no traceback; (M2) with VE files present VE appears and speaks as before; (M3) remove one DLL (e.g. `msvcr110.dll`) → VE hidden; restore → reappears with its old state after reopening the panel; (M4) Cerence the same on 64-bit NVDA (`lib/x64`); (M5) with a hidden but stored-enabled VE, OK without changes does not prompt to restart.

## 9. Risks

- A DLL present but unloadable (wrong architecture, corrupt) still shows the engine; it fails at synth load as today (D1).
- Importing a disabled plugin at panel open runs its import-time code on the GUI thread (D6).
- If NVDA ever ran the add-on outside `<configPath>/addons`, D2 follows the inner driver, which is what decides loading.

## 10. Questions and the defaults applied

### 10.1 Orchestrator defaults (Decided by orchestrator with the recommended default; user may override before merge)

D1–D8 of §2.2.

### 10.2 Decided by the user (2026-11-07)

G1, G2: hide, not gray out, any engine that cannot load; VE/Cerence with missing DLLs is the motivating case.
