# 階段 12：組裝根與 patch 堆疊

日期：2026-10-05。
基準：`master`（`714a3cf`，階段 10a 完成）。分支：`phase12-assembly`。
狀態：依使用者要求自動執行（spec → plan → 實作 → Fable review）。§6.3 的 monkey-patch 已複核為有效，保留並同步，不需使用者決定（`refactor.md` §6.3 更正）。

本文件是 [`refactor.md`](../../../refactor.md) §11 的階段 12，對應 §1.1、§3.3（discovery 計時）、§5.3（log 分層）、§6.3，以及 §9 的 C1、C2、C10。

## 需求與範圍

### 1. 主驅動的清理改為一張固定順序的清理表

- 現況（`synthDrivers/WorldVoice/__init__.py`）：
  - 5 個旗標：`_startNotified`、`_pipelineRegistered`、`_pipelineSubscribed`、`_voicePanelPatched`、`_spellingPatched`；
  - `hasattr(self, "add_detected_language_commands")`；
  - `terminate` 內 10 段 `_run_cleanup`。
  - 每新增一個步驟要改 `__init__`、`_initialize`、`terminate` 三處。
- **不用 `ExitStack`**。現行的清理順序不是初始化的反序，而且測試固定了這個順序：
  - 工作執行緒要先停；
  - bridge 要在引擎關閉前關閉，晚到的 index 才不會送進正在關閉的引擎；
  - ledger 最後才關；
  - 見 `test_failed_synth_construction_releases_acquired_resources`、`test_worker_stops_before_bridge_and_sessions_close`、`test_shutdown_disables_late_index_before_engine_close`。
  - 改成後進先出，會讓 VoiceManager 在 bridge 之前關閉，違反這些不變式。
- 新模組 `synthDrivers/WorldVoice/assembly.py`（純 Python，不 import NVDA）提供 `Teardown`：

```python
class Teardown:
	"""Cleanups registered as resources come up, run once in one fixed order."""

	def __init__(self, order: Sequence[str], logger): ...
	def add(self, name: str, cleanup: Callable[[], object]) -> None: ...  # 不在 order 內或重複登記 → ValueError
	def run(self) -> None: ...  # 依 order 執行已登記者；Exception 記 "WorldVoice terminate: %s" 後繼續；BaseException 照常往外拋
```

- `run` 只執行一次。第二次呼叫時沒有任何已登記項目，所以什麼都不做。
- 例外處理與現行 `_run_cleanup` 相同：`except Exception` 記 log，`KeyboardInterrupt` 中斷其餘清理並往外拋（階段 0 已知的延後 minor，行為不變）。
- 主驅動類別屬性 `_TEARDOWN_ORDER` 依現行 `terminate` 的順序列出 10 個名稱，字串與現行 log 相同：

```python
_TEARDOWN_ORDER = (
	"task manager shutdown",
	"language detection unregister",
	"pipeline cleanup",
	"voice settings panel restore",
	"spelling function restore",
	"event bridge close",
	"pipeline settings unsubscribe",
	"voice manager terminate",
	"index ledger close",
	"end notification",
)
```

- **兩類登記**：
  - **Runtime 物件**（task manager、bridge、VoiceManager、ledger）：`_new_teardown()` 一次登記四個 closure，執行時讀當下的 `self.taskManager`／`self._eventBridge`／`self._voiceManager`／`self._indexLedger`，為 `None` 就跳過。這與現行 `terminate` 的 `is not None` 檢查等價。
    - `task manager shutdown` 的 playbacks 在執行時才從 `self._voiceManager.playback_ports` 取得，同現行。
    - `voice manager terminate` 用 `terminate(commit=self._terminateCommit)`。`terminate(commit=...)` 在 `run()` 前設定 `self._terminateCommit`。
  - **副作用**（開始通知、pipeline 登記與訂閱、panel 與 spelling patch、語言偵測 filter）：取得副作用的那一步才 `add`。不需要旗標。
- `terminate` 變成：

```python
def terminate(self, *, commit=True):
	if self._terminated:
		return
	self._terminated = True
	self._terminateCommit = commit
	try:
		self._teardown.run()
	finally:
		self.taskManager = self._eventBridge = self._voiceManager = self._indexLedger = None
```

  - 現行在各段清理後把屬性設回 `None`（失敗也一樣）。改為 run 結束後統一設定；`speak` 等入口先檢查 `_terminated`，所以中間狀態不可見。
- 新增步驟只需兩處：
  - 在 `_initialize` 取得副作用後 `add`；
  - 在 `_TEARDOWN_ORDER` 放進名稱。
  - `add` 對未列名稱拋 `ValueError`，所以不會忘記第二處。

### 2. 計時改用 `timed`

- `assembly.timed(logger, label)` context manager：
  - 結束時 `logger.debug("WorldVoice init timing: %s %.3fs", label, elapsed)`；
  - 例外時也記錄（`finally`），並原樣往外拋；
  - `logger` 為 `None` 時不記錄。
- 主驅動 `_initialize` 的 9 段 `step_start = time.perf_counter(); …; nvdaLog.debug(...)` 改為 `with timed(nvdaLog, "<label>"):`。
  - label 與現行字串相同：`WVStart.notify`、`pipeline register`、`voice settings panel patch`、`TaskManager`、`VoiceManager`、`speakSpelling patch`、`SpeechSymbols construct`、`SpeechSymbols.load unicode.dic`、`LanguageDetector`、`total`（整個 `_initialize`）。
  - 差異：失敗的步驟現在也會記一行計時，以往不記。只影響 DEBUG log。
- `engine/discovery.load_enabled_engine_classes` 的 4 段計時（`ready check <engine> module import`、`Voice lookup`、`voice.ready`、`total`）改為 `timed(logger, f"ready check {spec.name} module import")` 等。
  - discovery 原本就在 `finally` 記錄，文字不變。
  - `_log` helper 保留給非計時訊息。

### 3. `patch_attribute`

- `assembly.patch_attribute(owner, name, value) -> Callable[[], None]`：
  - 讀出原值、設定新值，回傳把原值寫回的函式；
  - 回傳的函式只寫回一次，第二次呼叫不做事，避免清理重入時把較新的 patch 蓋掉。
- 使用處：
  - 主驅動 `gui.settingsDialogs.VoiceSettingsPanel`：`OriginVoiceSettingsPanel` 屬性刪除，它只用於還原；
  - 主驅動 `speech.speech.speakSpelling`：`self._realSpellingFunc` 保留，`patchedSpeakSpelling` 要呼叫原函式；
  - `pipeline/speech_dictionary.py` 的 `speech.speech.processText`：模組只保留一個 `_restore` 全域取代兩個全域，`install`／`uninstall` 介面與冪等性不變。
- **`sayAll` 不改**。`sayAll.patch`／`unpatch` 呼叫的是 NVDA 的 `sayAll.initialize(...)` API，不是屬性替換，`patch_attribute` 不適用。
- **GlobalPlugin 不改**。它只有三個步驟（`patch`、`attach_global`、選單），沒有旗標或順序問題，加清理表沒有讀者受益。

### 4. stage 註冊移到最後（C2）

- 現況：`pipeline_scope.worldvoice_started()` 是 `_initialize` 的第二步，早於 `speechSymbols` 與語言偵測建立。期間若有 `filter_speechSequence` 呼叫，`speech_context()` 以 `getattr(self, "speechSymbols", None)`、`getattr(self, "_numlan", "default")` 回應。
- 改為 `_initialize` 的最後一步（`LanguageDetector` 與 `self._voice = None` 之後）才 `worldvoice_started()`，並登記 `pipeline cleanup`。
- `__init__` 先設 `self._numlan = "default"`。`_numlan` 由 NVDA 在建構後的 `loadSettings` 經 `numlan` setter 設定，建構期間沒有其他來源。
- `speech_context()` 刪除兩個 `getattr`，改讀 `self._numlan`、`self.speechSymbols`。`manager is None` 時回傳 `GENERIC_CONTEXT` 的守衛保留：terminate 之後，scope 為 "all" 的全域 pipeline 仍可能呼叫它。
- 清理順序不受影響：`pipeline cleanup` 在 `_TEARDOWN_ORDER` 的位置不變。

### 5. `WorldVoiceVoiceSettingsPanel` 與 NVDA 同步（§6.3、C1）

- `VoiceSettingsDialogs.py`：
  - `createDriverSettings` 的註解改為：「Copied from NVDA's AutoSettingsMixin.updateDriverSettings, listing allSupportedSettings so every control exists in its standard order; compare with NVDA's version on every NVDA upgrade.」
  - docstring 補一句用途：預先建立控制項，切換語音時 RateBoost／Inflection 才會留在原位。
  - 補上 NVDA 現版的 `elif setting.id.startswith("_"): continue`（跳過私有設定）。目前 WorldVoice 沒有 `_` 開頭的設定，行為不變。
- 守門測試 `tests/test_nvda_settings_copy.py`。`ref/nvda` 不存在時 skip。
  - **結構相同**：
    - 取 NVDA `AutoSettingsMixin.updateDriverSettings` 與 WorldVoice `createDriverSettings` 的 AST，刪除兩者的 docstring；
    - WorldVoice 的版本再刪除唯一一個 `supportedSettings = (...)` 指派，NVDA 版本的 `for setting in settingsInst.supportedSettings` 改為 `for setting in supportedSettings`；
    - 函式名稱正規化後比對 `ast.dump`，必須相同。
    - NVDA 改動這個方法時，測試會失敗並提示同步。
  - **指紋**：WorldVoice 的 `_updateValueForControl` 刻意與 NVDA 不同（重新載入字串選項，切換語音後清單才正確），不能結構比對。所以固定 NVDA `AutoSettingsMixin._updateValueForControl` 的 `ast.dump` SHA-256。NVDA 改動時測試失敗，提示人工複核 WorldVoice 的版本。
  - 兩個指紋都記錄目前 `ref/nvda` 的 commit（`1406f9f8a`）作為註解。

### 6. log 分層（C10）

- `synthDrivers/WorldVoice/log.py`：
  - 不再 import `gui`、`wx`、`addonHandler`；
  - 刪除 import 時的 `log_dir.mkdir`；
  - `PipelineLog.__init__` 不碰磁碟。`_ensure_log_file` 在第一次 `write`／`move_to` 時建立目錄與檔頭。
- `PipelineLog.export()` 拆成兩半：
  - synth 層保留 `move_to(dst: Path) -> None`：建立目的地目錄、移動檔案、重建空檔頭。失敗時往外拋。
  - UI 層：`globalPlugins/WorldVoice/pipelineLog.py` 新增 `export_with_dialog(log=pl)`，內容是原 `export` 的 `wx.FileDialog`、成功的 `wx.MessageBox`、失敗的 `wx.LogError`。訊息字串與 noqa 理由不變。
  - `PipelineLogService` 的預設 exporter 改為 `export_with_dialog`。
- `pipeline/__init__.py` 的 `pl = PipelineLog("pipeline.csv")` 保留在 import 時建立。建構已不碰磁碟，所以沒有 import 時的副作用。

### 決定

- 不用 `ExitStack`／後進先出：理由見第 1 節。
- 不改 `sayAll` 與 GlobalPlugin：理由見第 3 節。
- `pipeline_settings`／`pipeline_scope` 模組單例不改為注入（§5.3 列為可選，收益有限）。

### 成功條件

1. 完整測試全部通過；`ruff format --check addon` 通過；`ruff check addon <附錄範圍> --select F401,F821,BLE001,I001` 為 0；hygiene 守門測試通過。
2. 守門測試（`tests/test_assembly_structure.py`）：
   - 主驅動不出現 `_startNotified`、`_pipelineRegistered`、`_pipelineSubscribed`、`_voicePanelPatched`、`_spellingPatched`、`_run_cleanup`、`OriginVoiceSettingsPanel`、`hasattr(self, "add_detected_language_commands")`、`getattr(self, "_numlan"`、`getattr(self, "speechSymbols"`、`step_start`；
   - `log.py` 不 import `wx`、`gui`；
   - `speech_dictionary.py` 只有一個模組層可變全域 `_restore`。
3. `Teardown`、`timed`、`patch_attribute` 的單元測試通過。
4. 初始化與終止的既有順序測試全部通過，不放寬任何斷言。另新增：stage 註冊發生在 `SpeechSymbols.load` 與 `LanguageDetector` 之後。
5. NVDA 設定複本守門測試通過（第 5 節）。
6. `driver/<Engine>/driver/`、`driver/sonic` 無變動。
7. 使用者可見行為不變：
   - 語音設定面板的控制項與順序；
   - log 匯出對話框與訊息；
   - 清理順序；
   - 數字語言與符號在 pipeline 中的行為。

### 不在範圍內

- GlobalPlugin 的清理、`sayAll`（第 3 節）。
- `_run_logged` 每次讀 config（§5.3 的 `LogPolicy`，階段 13）。
- `WVW_PATH` 等路徑推導（C12，階段 16）。
- 以 `exec` 抽出類別本體的測試改為一般 import（階段 16 視本階段結果）。

## 測試

1. `tests/test_assembly.py`（新）：
   - `Teardown`：
     - 依 order 執行而非登記順序；
     - 未登記的名稱跳過；
     - 未列名稱 `ValueError`；
     - 重複登記 `ValueError`；
     - 一項拋 `Exception` 時記 log 並繼續；
     - `KeyboardInterrupt` 往外拋、其後項目不執行；
     - 第二次 `run` 不做事。
   - `timed`：
     - 成功時記一行 label 與秒數；
     - 例外時也記錄且例外原樣拋出；
     - `logger=None` 不記錄。
   - `patch_attribute`：
     - 設定新值；
     - 還原舊值；
     - 第二次呼叫還原函式不做事。
2. `tests/test_worldvoice_lifecycle.py`、`tests/test_runtime_composition.py`：
   - exec 環境補上 `Teardown`、`timed`、`patch_attribute`（取自真實 `assembly` 模組）；
   - 以 `object.__new__` 建 synth 的 helper 改用 `synth._teardown = synth._new_teardown()`，取代逐一設旗標；
   - 新增 C2 順序斷言（成功條件 4）。
3. `tests/test_pipeline_log.py`：
   - `move_to` 移動檔案並重建檔頭；
   - 建構 `PipelineLog` 不建立目錄；
   - `export_with_dialog` 在取消、成功、失敗三種情況下的對話框呼叫（wx stub）。
4. `tests/test_speech_dictionary*.py`（既有測試）：`install`／`uninstall` 冪等與還原行為通過；若無既有測試則新增。
5. `tests/test_nvda_settings_copy.py`、`tests/test_assembly_structure.py`：成功條件 2、5。
