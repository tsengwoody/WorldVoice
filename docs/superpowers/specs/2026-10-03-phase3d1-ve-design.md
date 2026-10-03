# 階段 3d-1：VE 遷移到 SegmentHost（內層換回原版非同步結構）

日期：2026-10-03。
基準：`master`（`82a793e`，含 3c）。分支：`phase3d1-ve`。
狀態：對話中的範圍與設計已獲使用者確認；本文件待使用者審閱。

本文件是 [`refactor.md`](../../../refactor.md) §9 階段 3 的子階段 3d-1。前一子階段見 [2026-10-02-phase3c-onecore-design.md](2026-10-02-phase3c-onecore-design.md)。

## 3d 的拆分（使用者已確認）

| 子階段 | 內容 |
| --- | --- |
| **3d-1**（本文件） | VE：內層換回原版非同步結構、外層改用 SegmentHost、修 C3、移除契約 4 的 VE xfail、處理 phase 2 留下的 VE 項目 |
| 3d-2 | Cerence：依 3d-1 的設計各自實作一份（不共用程式碼），移除契約 4 的 Cerence xfail |

拆分理由：先在 VE 上驗證 worker 模型、非同步 `speak()` 與終止重入的設計，Cerence 在此期間維持現狀當對照。

## 需求與範圍

已確認的決定：

1. **執行模型：依原版 VE2 的非同步結構**。`ref/VE2-min`（原版 Vocalizer Expressive 2 add-on）以 `BgThread` 佇列處理語音、設定與 DONE。WorldVoice 早期（自有 TaskManager 時期）把內層改成同步；現在由 scheduler 與 SegmentHost 負責排程，恢復原版結構。
2. **內層 driver 例外**：使用者要求 VE 內層（`driver/VE/driver/__init__.py`）換回原版實作，並保留以下 WorldVoice 調整。這是「內層不修改」規則對 VE 的例外；Cerence 於 3d-2 再議。
   - Sonic 加速（rate boost）、PCM 緩衝、ENDPROCESS 尾段 flush。
   - rate／pitch 的指數對應。
   - 舊式 `RateCommand`／`PitchCommand(newValue)`／`VolumeCommand` 支援。
   - 安裝路徑調整（`user_folder` 層數；`ve2/__init__.py` 的 `module_dir`）。
   - `_veCallbackHandler` 屬性與 `_voice` 預設值後備。
3. **NVDA `cancel()` 丟棄佇列中的語音**（phase 2 留下的待決項目 (1)）：包括排在 segment 後面、沒有 token 的一般語音；依原版保留設定與一般語音的 DONE。
4. **沿用的限制**：
   - 不考慮 Neural 相容性。
   - 不共用 VE/Cerence 程式碼；所有引擎共用的程式碼只放在 `runtime/`。
   - 新增的公開名稱用 snake_case。
   - plan 的變異步驟放在 commit 之後。

成功條件：

1. **C3 修正**：VE 的 `speak_segment` 在送出事件前返回；契約 4 移除 VE 的 xfail 並通過。
2. **VE 改用 `SegmentHost`**：外層不再出現 `SegmentLifecycle`／`_segmentLifecycle`／`CallbackGate`；守門測試的 `MIGRATED` 加入 `"VE"`。
3. **內層差異受控**：VE 內層與 `ref/VE2-min` 的差異只有上述保留項，加上 `BgThread` 的 `setDaemon(True)` 改為等效的 `self.daemon = True`（前者已過時，會產生警告）。
4. **其他引擎與 Cerence 不變**（硬性要求）：
   - OneCore、eSpeak、SAPI5、RHVoice、Cerence 的 wrapper，以及 Cerence 的內層，原始碼完全不改。
   - 它們的測試照常通過；契約 4 的 Cerence 仍為 xfail。
5. **既有 VE 測試**：讀取已移除內部實作或依賴同步語意的地方改寫，plan 逐一列出。
6. **完整測試**：基線 1355 passed、96 skipped、2 xfailed；完成後 xfailed 為 1（只剩 Cerence）。
7. **格式與保護路徑**：`ruff format --check addon` 通過；其他引擎的內層不變；Neural 未被追蹤。

**不在範圍內**：Cerence（3d-2）、把 `SegmentLifecycle` 收為內部實作（3e）。

## 現況

基準 `82a793e`：

- 內層 VE：`speak()` 在呼叫端 thread 同步轉換並合成（`ve_ttsProcessText2Speech` 與其 callback 都在同一條 thread），最後同步發出 DONE；設定立即套用。
- 外層 VE（998 行）：`speak_segment` 在 scheduler thread 上執行 `lifecycle.run`，等事件送出才返回（C3）；一般語音在呼叫端等 segment 用完資源後同步合成；自有 `_SpeechWork`、`_NativeWork`、`CallbackGate`、子 lease、終止重入簿記。

## 設計

### 1. 內層 VE（`driver/VE/driver/__init__.py`）

恢復原版：
- `BgThread` 與 `_bgQueue`；`speak()` 把每段 `ProcessText2Speech` 與結尾的 `DoneSpeaking` 放進佇列。
- 設定（volume、rate、pitch、variant、waitfactor）以 `TtsSetParamList` 排進佇列；rate boost 的 Sonic 速度沿用 WorldVoice 現有的立即套用。
- `getParameters` 先看佇列中尚未套用的設定。
- `cancel()`：清空佇列，只保留 `TtsSetParamList` 與 `DoneSpeaking`；設定 silence、停止 player、`join` 佇列。
- `terminate()`：關閉 instance、`ve2.terminate()`、結束並 join `BgThread`、關閉 player。

保留項見「需求與範圍」第 2 點；`ve2/` 不動。

### 2. host 擴充（`runtime/segmentHost.py`）

- `SegmentHost.wait_idle()`：轉呼叫 lifecycle 的 `wait_idle()`，讓 VE 關閉 native 前能等最後一段退場。

### 3. 外層 VE（`driver/VE/__init__.py`）

**執行結構**：外層不自己開 worker，內層的 `BgThread` 就是 worker；外層把綁定紀錄的工作插進它的佇列。

```
submit（segment 與一般語音共用，在 host admission 下；只轉換與排隊，不合成）：
    _bgQueue ← Begin(record)
    內層 speak(commands) → 外層 _speak 覆寫：每個 piece 放入 NativeTask(record, instance, piece)
                         → 內層自行放入 DoneSpeaking
    _bgQueue ← Retire(record)
    （在外層佇列鎖內完成，兩筆紀錄的工作不會交錯）
BgThread：
    Begin      → 等停止／暫停歸零；紀錄無效或已有控制錯誤時略過並 abandon；
                 否則 host.begin、silence gate 換成這筆的 token、重置 callback 緩衝
    NativeTask → 開放 callback 准入 → ve_ttsProcessText2Speech（保留原始 status）
                 → 關閉准入、等 consumer 歸零、啟用覆寫檢查
    DoneSpeaking（內層）→ 一般語音：idle（含暫停等待）＋ DONE；segment：略過
    Retire     → reach("spoken")、等停止／暫停歸零、host.retire（segment 等 drain 完成）、一般語音 forget
```

- **`_VEStrategy`**：
  - `barriers = {"spoken", "idle"}`；一般語音不設 barrier。真正的錯誤記錄在紀錄上，依 host 規則停止 player；被 token 取消不算失敗。
  - `admission_error`：guard 未安裝、已終止、曾使用 legacy 語音時拒絕 segment（沿用現有規則）。
  - `submit`：如上排隊。
  - `stop_native`／`stop_player`：停止 player，期間以 `_stops` 擋住下一次 native 呼叫。
  - `drain`：`player.idle()` 加暫停等待後 `reach("idle")`；idle 失敗時 `record_error` 並 `latch_control_error`（沿用現行「後續拒絕」）。
- **callback 准入**：每次 native 呼叫建立 `_NativeCall(record, instance)`；callback 必須符合 instance 且仍在准入中，才以 `host.consumer` 與 `bound_callback` 進入。取代 `CallbackGate` 與子 lease。
- **保留**：`_SilenceGate`、`_GuardedPlayer`、`ProcessText2Speech`（保留原始 status）、`_ContextualVECallback` 的 Sonic 處理、`_confirm_native_quiescence` 啟用覆寫、暫停版本號與 `_stops`／`_pauses`、`Voice` 類別。
- **`speak()`**：已終止時拋出例外；呼叫當下標記 legacy 使用；以 `host.enqueue(speech, barriers=frozenset(), native=_VERequest(speech, token))` 排隊後返回。
- **`cancel()`**（外層覆寫，不呼叫原版會 `join` 的 cancel）：
  - 在 host admission 下：`host.cancel()`；在佇列鎖與狀態鎖下設定 silence、清除暫停狀態、整理佇列。
  - 整理佇列的規則：丟掉 `Begin`、`NativeTask`；保留設定、已開始那筆的 `Retire`、一般語音的 `DoneSpeaking`；丟掉 segment 的 `DoneSpeaking`。
  - 尚未開始的紀錄逐一 `abandon`；停止 player。
  - 不等 BgThread 做完：cancel 可能在 BgThread、callback、listener 或 lifecycle thread 上被呼叫，原版的 `join` 在這些情況會死結。
- **`terminate()`**：
  - 首次呼叫：`host.terminate()` 與 `cancel()`。
  - 在 BgThread、callback、player 操作（cancel／pause／stop／idle／drain）或關閉流程中重入時，開一條關閉者 thread 後返回。
  - 其他呼叫端直接執行關閉並等待完成。
  - cancel／pause 結束時若已要求終止，同步完成關閉，維持現行行為。
  - 關閉流程：讓 BgThread 結束並 join → `host.wait_idle()` → 等停止與暫停歸零 → 封閉 player → detach callback → 內層 `terminate()`。
- **`Voice.applyEngineSettings`**：variant 維持立即套用。scheduler 只在前一段排空後才套用，不會與合成同時進行。

**行為變化**：
1. `speak_segment` 立即返回（C3）。
2. `speak()` 回到原版的非同步：放進佇列即返回；index／DONE 在 BgThread 上發出；合成錯誤不再拋給呼叫端（控制錯誤已鎖住時仍直接拋出）。
3. 設定依原版排進佇列、依序生效。
4. `cancel()` 丟棄佇列中的語音（含排在 segment 後的一般語音），保留設定與一般語音的 DONE；不 `join` BgThread。
5. legacy 使用在呼叫 `speak()` 的當下標記。

## 測試

- **共用輔助**：
  - `tests/test_vocalizer_segment_drain.py`：`hosted`、`lifecycle_of`、`settle_segment`（等該段送出或捨棄）、`settle_worker`（等 BgThread 佇列清空）、`speak_ordinary`、`queued_ordinary`；`speak()` 輔助在 `speak_segment` 返回後等 `settle_segment`。
  - `tests/test_worldvoice_cancel_wrappers.py`：`speak_now`。
  - 輔助依 core 是否已用 host 分流，Cerence 照舊。
- **改讀內部實作**：`_segmentLifecycle` → host（`isinstance` 改檢查 `SegmentHost`）；`request_stop` 改 patch 在 host 上；`_nativeWork` → `_nativeCall`；`_run_speech` → patch host 的 `retire`；`tests/test_runtime_drain_integration.py` 的 hooks 檢查；fixture 一併清除 `segmentHost` 模組快取。
- **語意改變而改寫**（VE 分支，Cerence 保留原預期）：
  - `test_ve_shared_silent_cancel_releases_delivery_wait` → `test_ve_shared_speak_segment_returns_while_a_previous_sink_runs`。
  - 排在 segment 後的一般語音：在佇列中等待；cancel 時丟棄並保留 DONE；terminate 時呼叫端不再收到例外。
  - 一般語音的錯誤不拋給呼叫端（原生錯誤、暫停故障前已排隊者）。
  - 設定測試等佇列處理完再檢查。
- **契約**：`tests/test_engine_segment_contract.py` 契約 4 只保留 Cerence 的 xfail。
- **守門**：`MIGRATED` 加入 `"VE"`。
- **新增**：
  - VE `speak()` 在合成完成前返回。
  - 設定與語音依呼叫順序生效。
  - `SegmentHost.wait_idle()` 的 host 單元測試。
- **變異證明**：在 commit 之後執行，每項新行為至少一次。

## 驗收

- `python3 -m pytest tests -q`：全部通過；skipped 96、xfailed 1。
- `git diff master --stat -- addon/synthDrivers/WorldVoice/driver/{OneCore,Espeak,SAPI5,RHVoice,Cerence}`：無輸出。
- `grep -n "_segmentLifecycle\|SegmentLifecycle\|CallbackGate" addon/synthDrivers/WorldVoice/driver/VE/__init__.py`：無輸出。
- VE 內層與 `ref/VE2-min` 的差異只有保留項與 `daemon` 一行；`ve2/` 無變動。
- `ruff format --check addon`：通過；其他引擎的內層不變；Neural 未被追蹤。
