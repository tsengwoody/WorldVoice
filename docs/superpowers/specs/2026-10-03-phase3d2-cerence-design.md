# 階段 3d-2：Cerence 遷移到 SegmentHost（內層換回原版非同步結構）

日期：2026-10-03。
基準：`master`（`423ef15`，含 3d-1）。分支：`phase3d2-cerence`。
狀態：範圍與設計已獲使用者確認；使用者指示寫完 spec 後直接撰寫並執行 plan。

本文件是 [`refactor.md`](../../../refactor.md) §9 階段 3 的子階段 3d-2。設計沿用 [2026-10-03-phase3d1-ve-design.md](2026-10-03-phase3d1-ve-design.md)，本文件只寫出 Cerence 的差異與新增項目。

## 需求與範圍

已確認的決定：

1. **依 3d-1 的 VE 設計各自實作一份**：Cerence 與 VE 不共用程式碼，兩者必須能各自獨立安裝。
2. **內層換回原版**：Cerence 內層（`driver/Cerence/driver/__init__.py`）改回 `ref/CerenceTTS(min)` 原版的非同步結構，並保留以下 WorldVoice 調整。這是「內層不修改」規則對 Cerence 的例外，與 VE 相同。
   - Sonic 加速（rate boost）、PCM 緩衝、ENDPROCESS 尾段 flush。
   - rate／pitch 的指數對應。
   - 安裝路徑（`getResourcePaths` 加上 `WorldVoice-workspace/Cerence`；`ttsapi/__init__.py` 的 `module_dir`）。
   - `_veCallbackHandler` 屬性與 `_rateBoost` 初始化。
   - Cerence 原本就沒有舊式 Rate/Pitch/Volume 命令，維持不加。
3. **一併處理 3d-1 留下的兩項 VE 小問題**：`_VEStrategy` 的說明文字改為「內層 BgThread 就是 worker」；刪除多餘的 `_queueLock`（host admission 已讓 `_enqueue` 與 `cancel()` 互斥）。VE 行為不變。
4. **沿用的限制**：不考慮 Neural；所有引擎共用的程式碼只放在 `runtime/`；新增的公開名稱用 snake_case；plan 的變異步驟放在 commit 之後。

成功條件：

1. **C3 修正**：Cerence 的 `speak_segment` 在送出事件前返回；契約 4 移除 Cerence 的 xfail 並通過，所有引擎都不再有 xfail。
2. **Cerence 改用 `SegmentHost`**：外層不再出現 `SegmentLifecycle`／`_segmentLifecycle`／`CallbackGate`；守門測試的 `MIGRATED` 加入 `"Cerence"`。
3. **內層差異受控**：Cerence 內層與 `ref/CerenceTTS(min)` 的差異只有上述保留項，加上 `setDaemon(True)` 改為等效的 `self.daemon = True`。bookmark 迴圈原本多縮排一層（只是空白差異），改回與原版一致。`ttsapi/` 不動。
4. **其他引擎不變**（硬性要求）：OneCore、eSpeak、SAPI5、RHVoice 的 wrapper 與內層，以及 VE 的內層，原始碼完全不改；VE 外層只改上述兩項小問題。
5. **完整測試**：基線 1362 passed、101 skipped、1 xfailed；完成後 1375 passed、89 skipped，xfailed 為 0。
6. **格式與保護路徑**：`ruff format --check addon` 通過；Neural 未被追蹤。

**不在範圍內**：把 `SegmentLifecycle` 收為內部實作（3e）。

## 設計

### 1. Cerence 內層

與 3d-1 的 VE 內層相同，恢復原版：
- `BgThread` 與 `_bgQueue`；`speak()` 把每段 `ProcessText2Speech` 與結尾的 `DoneSpeaking` 放進佇列。
- 設定（volume、rate、pitch、variant、waitfactor）以 `TtsSetParamList` 排進佇列；rate boost 的 Sonic 速度沿用 WorldVoice 現有的立即套用。
- `getParameters` 先看佇列中尚未套用的設定。
- `cancel()`、`terminate()` 依原版。

### 2. Cerence 外層

結構與 3d-1 的 VE 外層相同（請見 3d-1 spec §3）：
- `_CerenceStrategy`、`_CerenceRequest`、`_NativeCall`、`_Begin`／`_NativeTask`／`_Retire`。
- `cancel()` 整理佇列但不 `join`；由關閉者 thread 完成關閉。
- 失敗的一般語音仍發出 DONE；`Voice.applyEngineSettings` 的 variant 寫入排進佇列。

Cerence 特有、照舊保留的部分：
- 模組名 `ttsapi`、profile `cerence-ttsapi-0x0520-unverified`、所有顯示給使用者的字串。
- bookmark 以 `int(szValue)` 解碼。
- callback 准入多一道 `isinstance(instance, ttsapi.veTypes.VE_HSAFE)` 檢查。
- `Voice` 類別沿用 Cerence 原本的寫法（`variants` 的例外處理等）。

**行為變化**（與 3d-1 的 VE 相同）：
1. `speak_segment` 立即返回（C3）。
2. `speak()` 回到原版的非同步；合成錯誤不再拋給呼叫端，但失敗的請求仍發出 DONE；控制錯誤已鎖住時仍直接拋出。
3. 設定依原版排進佇列、依序生效。
4. `cancel()` 丟棄佇列中的語音（含排在 segment 後的一般語音），保留設定與一般語音的 DONE；不 `join` BgThread。
5. legacy 使用在呼叫 `speak()` 的當下標記。

### 3. VE 外層小修正

- `_VEStrategy` 說明文字：`VE's native queue: the inner BgThread, each record's tasks queued around speak().`
- 刪除 `_queueLock`；`_enqueue` 的註解說明 host admission（`enqueue` 與 `cancel` 都持有）讓每筆紀錄的工作連在一起。

## 測試

- **3d-1 為 VE 新增的 6 個測試**改成引擎中性的名稱，VE 與 Cerence 都跑：
  - `test_speak_returns_before_native_synthesis`
  - `test_settings_apply_in_call_order_with_speech`
  - `test_cancel_drops_a_segment_queued_behind_the_worker`
  - `test_failed_ordinary_speech_still_publishes_done`
  - `test_engine_settings_variant_waits_for_running_speech`
  - `test_speak_segment_returns_while_a_previous_sink_runs`
- **另外 4 個原本只跑 VE 的 `test_ve_shared_*` 測試**也改成引擎中性的名稱，讓 Cerence 的關閉與錯誤路徑有同樣的保護：
  - `test_terminal_listener_can_speak_successor`
  - `test_player_failure_rejects_successor_with_context`
  - `test_terminate_waits_for_coordinator_stop`
  - `test_player_hook_can_reenter_terminate`
- **Cerence 專用測試**：`test_cerence_shared_*` 的 `isinstance(..., SegmentLifecycle)` 改為檢查 `SegmentHost`。
- **其餘依 `hosted(env)` 分流的測試**：Cerence 改用 host 後自動走新語意的分支，不需另改。
- **契約**：`tests/test_engine_segment_contract.py` 契約 4 不再有 xfail；刪除不再使用的 `_c3`。
- **守門**：`MIGRATED` 加入 `"Cerence"`。
- **變異證明**：在 commit 之後執行；Cerence 比照 3d-1 的 VE 變異，加上 Cerence 特有的 instance 型別檢查。

## 驗收

- `python3 -m pytest tests -q`：`1375 passed, 89 skipped`；沒有 xfailed。
- `git diff master --stat -- addon/synthDrivers/WorldVoice/driver/{OneCore,Espeak,SAPI5,RHVoice}` 與 `driver/VE/driver`：無輸出。
- `grep -n "_segmentLifecycle\|SegmentLifecycle\|CallbackGate" addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py`：無輸出。
- Cerence 內層與 `ref/CerenceTTS(min)` 的差異只有保留項與 `daemon` 一行；`ttsapi/` 無變動。
- `ruff format --check addon`：通過；Neural 未被追蹤。
