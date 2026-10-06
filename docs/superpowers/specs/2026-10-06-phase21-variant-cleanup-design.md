# 階段 21：variant 外漏修正與第五輪收尾

日期：2026-10-06。
基準：`master`（`2df3fe3`）。分支：`phase21-variant-cleanup`。
狀態：使用者已決定範圍（2026-10-06），依自動流程執行（spec → plan → 實作 → Fable 審查）。

本文件對應 `storage/refactor5.md`（第五輪審查，不入版控）§11 階段 21。細節在 §3.1（N13）、§9 的 N 表（N14–N19）、§2.1、§4、§6、§8。以下行號都以 `2df3fe3` 為準，每一項都已在原始碼上逐行複核。

## 使用者決定

- N14 併入本階段：`defaultVoiceName` setter 對不可用名稱拋 `LookupError`。
- N15：刪除 `wait_native_retired`（不保留為擴充點）。
- 衛生可選項：做 scheduler logger 與 VE/Cerence `threading.local` 子類；`speechSymbols` 不做。
- N19：加上 presenter 持舊 manager 的檢查。
- 21(a) 先修 `load`，階段 22 再把繼承政策移出 repository。

## 現況與需求

### (a) N13：`load` 從主 synth 的 speech 區段讀 variant

`configRepository.py:47-58` 在參數一致開啟且閘門打開時，對 `VOICE_PARAMETERS` 每一個名稱讀 `config.conf["speech"]["WorldVoice"]`，包括 `variant`。專案對「可複製參數」的定義是 `PARAMETER_NAMES`（`runtime/settings.py:26-27`，variant 除外），`ParameterConsistency.copy_from`（`mainLocalePolicy.py:84-89`）遵守它，`load` 沒有。

NVDA 的 profile 切換（`ref/nvda/source/synthDriverHandler.py:600`）與語音設定面板「取消」（`gui/settingsDialogs.py:1621-1629`）都呼叫 `loadSettings` → WorldVoice 覆寫（`__init__.py:323-327`）→ `VoiceManager.reload()` → 每個已建立的語音 `repository.load`。主語音的 operating point 因此蓋到所有 VE/Cerence 語音；不在對方清單時 `applyEngineSettings` 拋 `ValueError("Unavailable variant")`（`driver/VE/__init__.py:964-965`、`driver/Cerence/__init__.py:971-972`），該語音每句都在 activate 失敗。

需求：

- `load` 只對 `PARAMETER_NAMES` 讀共用區段；`variant` 永遠是語音自己存的值（或預設）。
- 參數一致關閉時行為不變。
- `tests/test_voice_config_repository.py` 的三個期望（`variant="main"`）改為語音自己的值；新增「共用 variant 不覆蓋語音自己的 variant」測試；守門：`load` 的共用讀取迭代 `PARAMETER_NAMES`。

### (b) N14：不可用的主語音名稱拋 `LookupError`

`VoiceManager.defaultVoiceName` setter（`voiceManager.py:186-193`）對不在 catalog 的名稱 `debugWarning` 後返回；`SynthDriver._set_voice`（`__init__.py:427-435`）在驗證前寫 `self._voice`。NVDA 的 `loadSettings`（`synthDriverHandler.py:392-397`）只在 `changeVoice` 拋例外時把 config 的 `voice` 修回 `self.voice`；NVDA 的 OneCore（`oneCore.py:605`）與 SAPI5 都拋。

需求：

- setter 對不可用名稱 `raise LookupError(name)`，不改任何狀態。
- `_set_voice` 在 setter 成功後才寫 `self._voice`。名稱等於目前主語音時仍直接記下並返回。
- 測試：setter 拋例外且主語音不變；`_set_voice` 失敗時 `_voice` 不變；成功時記下。

### (c) N18：`VoiceSettingsDialogs.py:37` 重複寫入

NVDA 的 `_makeBooleanSettingControl` 已綁 `_onCheckChanged` 寫同一個 descriptor（`gui/settingsDialogs.py:1529-1533`），descriptor 只在值改變時寫入與通知（`pipeline/settings.py:294-298`）。刪掉第 37 行，保留 `evt.Skip()` 與可見性更新。

### (d) N15：刪除 `wait_native_retired`

Protocol（`runtime/_segmentLifecycle.py:43`）、呼叫點（`:335`）、唯一實作（`runtime/segmentHost.py:530-532`，只有 `return`）三處都刪。

測試目前把它當成故障注入點：

- `tests/test_segment_lifecycle.py`：`Hooks.wait_native_retired`、`retirement_entered`、`retired_error`；`test_nested_lease_retires_before_successor` 以 `retirement_entered` 等待「admission 已關閉」；`test_retirement_failure_latches_core_fault` 以 `retired_error` 注入。
- `tests/test_segment_host.py:539、557` 以 monkeypatch 讓 host 的 `wait_native_retired` 拋例外。

改法：

- 「admission 已關閉」改以 lifecycle 條件變數等待 `operation._admitting` 為假（該檔已讀 `operation._waiting` 等私有狀態）。
- 故障注入改到 `wait_native_boundary`：它與被刪的 hook 在 `_run_owned` 的同一個 `try`，例外同樣走 `_latch_fault`。lifecycle 測試讓 `Hooks.wait_native_boundary` 在放行後拋 `boundary_error`；host 測試的 `broken` 先呼叫原本的 `wait_native_boundary` 再拋例外，保留原本「native 已退休後才故障」的時序。

### (e) N16：`retire()` → `forget()` 的契約

`SegmentHost.retire`（`segmentHost.py:449-470`）把仍有效的一般語音記錄留在 `_pending`，讓之後的 cancel 能標記 `cancelled`；呼叫端送完通知後必須 `forget`。六家都做（Espeak `:195`、RHVoice `:259`、SAPI5 `:626`、OneCore `:340`、VE `:568`、Cerence `:570`），docstring 沒寫。

需求：docstring 補上這一步；host 測試固定「retire 之後、forget 之前 cancel 會標記 cancelled；forget 之後 `_pending` 不含該記錄」。

### (f) N17：三處同形程式碼

1. `SegmentHost._deliver`（`:619-622`）與 `_forget_operation`（`:628-631`）的四行迴圈 → `_drop_pending_locked(operation)`。
2. `RolePanelPresenter.apply`（`rolePresenter.py:136-142`）自寫 `prune_assignments` 的條件 → 呼叫 `roles.prune_assignments`。
3. `installTasks._load_core_archive` 與 `_workspace_path`（`:9-24`）→ 共用 `_load_by_path(relpath, name)`；兩個函式名稱保留（`tests/test_workspace.py` monkeypatch `_workspace_path`）。

### (g) 衛生

1. OneCore 的 7 處 `log.exception`（`driver/OneCore/__init__.py:293、325、358、423、455、509、515`）改為 `log.error(..., exc_info=True)`，與其他五家及 pyproject `G201` 的理由一致（NVDA 的 `log.exception` 會把預期的 COM 錯誤降為 debugWarning）。這是唯一的可見差異：這些預期中的 COM 錯誤會以 ERROR 記錄，與其他五家相同。
2. `BaseSettingsPanel.makeSettings`（`speechSettingsDialog.py:76`）讀到無效值時的 `tones.beep` 改為記 log（讀取路徑不發聲）。`_write_settings` 的 beep（`:108`）是存檔錯誤回饋，保留。
3. `_get_availableNumlans`（`__init__.py:481-493`）改為一般的 dict 建構。
4. `CancellationToken` 接受 `logger`（預設模組 logger）；`TaskManager.new_request` 傳入 `self._logger`。
5. VE/Cerence：模組層 `_ThreadState(threading.local)`，類別屬性 `depth = 0`、`cleaning = False`；三個 `threading.local()` 改用它；6 處 `getattr(local, "depth"/"cleaning", …)` 改為直接讀屬性。兩檔同步，漂移允許清單不變。

### (h) N19：角色面板持舊 manager

`SpeechRoleSettingsPanel.makeSettings` 記下 `self._manager`（`speechSettingsDialog.py:309`）；對話框開著時若 NVDA 重建 WorldVoice（例如音訊裝置變更，`synthDriverHandler.py:592-596`），`onSave`（`:577-580`）只確認「目前是 WorldVoice」，會對已 terminate 的舊 manager 執行 `apply()`。

需求：`onSave` 在目前 synth 的 `voice_manager` 不是 `self._manager` 時記 warning 並返回，不套用。

## 不在範圍內

- 繼承政策移出 repository（階段 22）。
- `speechSymbols` 的 import 時求值與 `list(keys())`（使用者決定不做）。
- 第五輪 §10 的全部項目。

## 驗證

- `python3 -m pytest tests -q` 全數通過。
- `ruff check addon`、`ruff format --check addon` 0 項。
- `tests/test_vocalizer_drift.py` 允許清單不變。
- prek hook 在每次 commit 通過。

## 實作備註（與上文的差異）

- (a) 另有 `tests/test_runtime_composition.py::test_voices_loaded_while_the_driver_starts_keep_their_own_values` 以 `variant="max"` 固定外漏，期望改為語音自己的 `own-b`。「共用讀取只迭代 `PARAMETER_NAMES`」以行為測試 `test_shared_variant_never_overrides_the_voice_variant` 固定，不另加字串守門。
- (d) `tests/test_sapi5_segment_drain.py::test_hook_fault_after_binding_does_not_strand_the_worker` 也以 `wait_native_retired` 注入故障，同樣改包 `wait_native_boundary`。
- (f) presenter 改用 `prune_assignments` 後，`tests/test_role_presenter.py` 的 `load_presenter` 需把 manager 所用的 `roles` 模組放進 `synthDrivers.WorldVoice.roles`。
- (h) `tests/test_role_panel.py` 的 synth stub 補上 `voice_manager`，panel 補上 `_manager`；新行為測試在 `tests/test_ui_structure.py`。
- (g) 讀取路徑的無效值以 `log.debugWarning(..., exc_info=True)` 記錄。
