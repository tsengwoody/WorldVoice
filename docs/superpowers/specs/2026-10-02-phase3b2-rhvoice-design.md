# 階段 3b-2：RHVoice 遷移到 SegmentHost

日期：2026-10-02。
基準：`master`（`5e74ab5`，含 3b-1）。分支：`phase3b2-rhvoice`。
狀態：使用者已審閱並核可。2026-10-02 依原型結果修訂，修訂處列於文末「原型修訂」。

本文件是 [`refactor.md`](../../../refactor.md) §9 階段 3 的子階段 3b-2。前一子階段見 [2026-10-02-phase3b1-sapi5-design.md](2026-10-02-phase3b1-sapi5-design.md)。

## 需求與範圍

已確認的決定：

1. **做法 A**：RHVoice 需要的共用機制寫進 `runtime/segmentHost.py`，以選用或參數化的方式提供；eSpeak／SAPI5 行為不變。
2. **一般語音比照 host 規則**：RHVoice 一般語音失敗或缺屏障時停止 player（現況不檢查）。成功時不得停止。
3. **abandoned 紀錄**：維持 3b-1 的規則，永遠不算「排空中」，`request_stop` 不呼叫 `stop_native`。
4. **沿用的限制**：
   - 不考慮 Neural 相容性。
   - 不共用 VE/Cerence 程式碼；所有引擎共用的程式碼只放在 `runtime/`。
   - 只改外層 wrapper，不改內層驅動 `driver/RHVoice/driver/`。
   - 新增的公開名稱用 snake_case。
5. **plan 流程**：變異步驟一律放在 commit 之後。

成功條件：

1. **RHVoice 改用 `SegmentHost`**：不再出現 `SegmentLifecycle`／`_segmentLifecycle`；守門測試的 `MIGRATED` 加入 `"RHVoice"`。
2. **RHVoice 既有 drain 測試全部通過**：只有讀取已移除內部實作的地方才改為透過 host 讀取，plan 逐一列出。
3. **未遷移與已遷移引擎的相容性**（硬性要求）：
   - OneCore、VE、Cerence、eSpeak、SAPI5 的 wrapper 原始碼完全不改（`git diff master` 無輸出）。
   - 它們的 drain 測試、契約測試照常通過；契約 4 的 VE、Cerence 仍為 xfail。
4. **新擴充的單元測試**：每一項都有測試，並至少以一次變異證明它能失敗。
5. **完整測試**：基線 1326 passed、96 skipped、2 xfailed，加上本階段新增測試；xfailed 仍為 2。
6. **格式與保護路徑**：`ruff format --check addon` 通過；內層驅動與 Neural 不變。

**不在範圍內**：OneCore（3c）、VE/Cerence 與 C3（3d）、把 `SegmentLifecycle` 收為內部實作（3e）、RHVoice 的 name-mangled 存取集中化（refactor.md 的 `_InnerDriverAccess` 建議）。

## 現況

基準 `5e74ab5` 的 `driver/RHVoice/__init__.py`（719 行）自己實作整套生命週期簿記：

- `_Speech`：7 個布林、boundary／retired／handoff、consumer 計數、delivery thread。
- 每個 native callback 與 feed 都申請 lifecycle 子 lease。
- 自己的 `_dispatch` delivery thread、`_segmentAccepted` 與 `_rhvoice_cancelled` 靜默旗標。
- 控制錯誤時讓所有已接受的 operation 失敗；送出時 DRAINED 改報 FAILED。
- worker 上的退場順序：
  1. 關閉 native callback 入口，等 consumer 歸零；
  2. final idle，期間仍允許 index callback；
  3. 完全封閉，等 consumer 歸零；
  4. 刪除 message；
  5. retired，等 handoff，清除 cancel flag。
- `cancel()` 是同步的：返回前等目前段落退場、等正在執行的 sink 結束。從 callback 或 delivery thread 呼叫時略過，以免死結。

## 設計

### 1. host 擴充（`runtime/segmentHost.py`）

| 擴充 | 介面 | RHVoice 用途 |
| --- | --- | --- |
| 退場收尾 | `retire(record, *, finish=None)`：封閉紀錄、consumer 歸零後，在呼叫端（worker）thread 執行 `finish`，例外以 `record_error` 記錄，然後才解除目前紀錄並設定 `retired` | 刪除 native message |
| 關閉後的音訊 callback | `consumer(record=None, *, audio=False)`：`audio=True` 時在 `close()` 之後、`retire()` 封閉之前仍允許進入 | final idle 期間的尾段 index |
| 同步 cancel 等待 | `wait_settled(record)`：等 `record` 不再是目前紀錄，並等呼叫當下正在執行的 sink 結束 | `cancel()` 返回前舊段落已停 |
| 控制錯誤讓已接受工作失敗 | `SegmentHost(engine, strategy, *, fail_accepted_on_control_error=False)`：開啟時 `latch_control_error` 對所有已接受的 operation 呼叫 `lifecycle.fail`；送出時 DRAINED 改報 FAILED | 停止失敗後不得回報成功 |
| abandoned 紀錄 | 維持 3b-1：不算排空中 | 佇列中被取消的段落 |

細節：

- **`retire(finish=...)`**：
  - `finish` 在 host condition 之外呼叫，不違反「持有 condition 時不呼叫外部程式碼」。
  - `retire` 在解除目前紀錄時 `notify_all`，`wait_settled` 靠它喚醒。
  - 不傳 `finish` 時行為與 3b-1 相同。
- **`consumer(audio=True)`**：只放寬「已關閉」一項；紀錄已失效、已封閉或已不是目前紀錄時照樣拒絕。
- **`wait_settled(record)`**：
  - 從綁定 `record` 的 callback（`callback_record() is record`）呼叫時，不等該紀錄退場。
  - 從任何綁定的 callback 或 delivery thread 呼叫時，不等 sink。
  - 等待的 sink 是呼叫當下正在執行的那些（快照），不等之後才開始的。
  - host 在 `_deliver` 呼叫 sink 前後登記與移除，並 `notify_all`。
- **`fail_accepted_on_control_error`**：
  - `lifecycle.fail` 在 host condition 之外呼叫；它讓進行中的段落立即停止，並讓已排空未送出的段落在送出時改為失敗。
  - `_deliver` 的 DRAINED → FAILED 改報不可省略：`lifecycle.fail` 可能晚於 delivery thread 讀取結果。
  - 預設 False；eSpeak、SAPI5 不開啟，行為不變。
- **鎖順序**：host admission → 引擎鎖 → host condition → lifecycle condition。host 模組說明補上引擎鎖。

### 2. 共用 runtime 修正（`runtime/segmentLifecycle.py`）

lifecycle 的 `_deliver` 迴圈在每輪等待前清掉上一輪的區域變數（`retired`、`operation`、`event`）。

理由：原型發現閒置的 delivery thread 仍抓著上一個已退場 operation，連帶保留它的 sink。RHVoice 的 gc 測試 `test_cancel_releases_queued_work_without_running_its_native_message` 因此約 1/8 失敗（master 40/40 通過）；修正後 60/60 通過。RHVoice 改用 host 後才經過 `on_retired` 這條路，所以 master 不會觸發。

### 3. RHVoice 遷移

| 元件 | 3b-2 之後 |
| --- | --- |
| `_Speech` | 由 `NativeRecord` 取代；barrier 為 `{"message", "done", "returned", "idle"}`，segment 與一般語音相同；callback identity 與 `_NativeLibrary` 放進 `record.native`（`_RHVoiceMessage`） |
| `_NativeLibrary` | 保留；`message`、`returned` 改為標記屏障；錯誤用 `host.record_error`；刪除 message 失敗時 `latch_control_error` |
| `_NativeCallback`、`_native_callback` | 保留；以 identity 找紀錄，改用 `host.consumer(record)` 與 `bound_callback`；done callback 標記 `done`；不再申請 lifecycle 子 lease（consumer 計數加 retire 等待已保證退場順序） |
| `_WavePlayer.feed` | 保留；沒有綁定紀錄時丟棄（同現況）；巢狀 feed 走 host 巢狀規則；index callback 用 `consumer(record, audio=True)` |
| 包裝 `AudioPlayer.idle` | 移除；worker 自己的 final idle 成功後才 `reach("idle")` |
| `_QueuedSpeech` | 保留，順序不變：取消閘門 → `host.begin` → 綁定紀錄執行 native task → `close` + `wait_consumers` → 條件成立時 final idle → `retire(record, finish=刪除 message)` → segment 清除 cancel flag；一般語音 `forget` |
| `speak_segment`、`_run_segment`、`_dispatch`、五個 hook、`_segmentAccepted`、`_rhvoice_cancelled` | 由 host 取代；送出改走 lifecycle 的 delivery thread |
| `_RHVoiceStrategy` | `submit`：指定 identity、建立 `SpeakText`、放進內層佇列；`stop_native`：設定 cancel flag、停止 player；`stop_player`：停止 player；不實作 `drain` |
| `cancel()` | 見下 |
| `terminate()` | `host.terminate()` → `cancel()` → 結束 worker → 關閉 player → 刪除 engine |

`cancel()`：
1. 在 `host.admission()` 下：`host.cancel()`；遞增 `_segmentCancelling`；對佇列中（非目前）的紀錄逐一 `host.abandon`；呼叫內層 `cancel()`，失敗時 `latch_control_error`。
2. 離開 admission 後：`host.wait_settled(current)`；停止 player，失敗時 `latch_control_error`。
3. 最後遞減 `_segmentCancelling` 並喚醒 worker。

`SegmentHost` 以 `fail_accepted_on_control_error=True` 建立。

**行為變化**：
1. 一般語音失敗或缺屏障時停止 player（使用者已選）。
2. 「排空中」的紀錄（已 retired、尚未 handoff）也會收到 NVDA cancel 的停止，與 SAPI5 一致：設定 cancel flag 並停止 player，worker 在 handoff 後清除 cancel flag。
3. 其餘可觀察行為與 master 相同。

## 測試

- **host**（`tests/test_segment_host.py`）：
  - `consumer(audio=True)`：`close()` 後允許、`retire()` 封閉後拒絕、不帶 `audio` 時照舊拒絕。
  - `retire(finish=...)`：在 consumer 歸零之後、`retired` 之前執行；`finish` 的例外讓該段 FAILED，下一段不受影響。
  - `wait_settled`：等目前紀錄退場；綁定該紀錄的 callback 不等；等正在執行的 sink；delivery thread 或綁定的 callback 不等 sink。
  - `fail_accepted_on_control_error`：
    - 已排空、尚未送出的段落：開啟時 FAILED，預設 DRAINED。
    - 進行中的段落：開啟時立即 `stop_native`；預設不停止，播完後才因紀錄錯誤而 FAILED。
    - `lifecycle.fail` 晚於 delivery thread 讀取結果時（以替身讓 `fail` 不生效模擬），開啟後 host 仍改報 FAILED。
- **lifecycle**（`tests/test_segment_lifecycle.py`）：閒置的 delivery thread 不保留已退場 operation 的 sink（weakref + gc）。
- **RHVoice**（`tests/test_rhvoice_segment_drain.py`）：一般語音成功時不停止 player；合成失敗時停止 player。
- **RHVoice 既有測試**，讀取已移除內部實作的地方共 12 處：
  - fixture 一併清除 `segmentHost` 模組快取。
  - `_segmentLifecycle` → `_segmentHost._lifecycle`（7 處）。
  - patch `accept` 的替身改接 `**kwargs`。
  - `_run_segment` → `_segmentHost._run`。
  - `_segmentAdmission` → `_segmentHost._admission`。
  - `_segmentAccepted` + `_rhvoice_cancelled` → `_segmentHost._accepted.values()`。
  - `_segmentControlError` → `_segmentHost.control_error`。
  - `speech.closed` → `not speech.admitting`（2 個測試）。
- **守門**：`tests/test_lifecycle_private_access.py` 的 `MIGRATED = ("Espeak", "SAPI5", "RHVoice")`。
- **變異證明**：在 commit 之後執行，每項新行為至少一次。

## 驗收

- `python3 -m pytest tests -q`：全部通過；skipped 96、xfailed 2。
- `git diff master --stat -- addon/synthDrivers/WorldVoice/driver/{OneCore,VE,Cerence,Espeak,SAPI5}/__init__.py`：無輸出。
- `grep -n "_segmentLifecycle\|SegmentLifecycle" addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py`：無輸出。
- `ruff format --check addon`：通過；內層驅動無變動；Neural 未被追蹤。

## 原型修訂（2026-10-02）

原型與乾淨重播後，對原設計做了以下修訂；plan 依修訂後的內容撰寫：

1. **DRAINED → FAILED 改報必須保留**。原型曾以為 `lifecycle.fail` 已涵蓋而移除它，結果 `test_stop_fault_before_deferred_terminal_delivery_fails_closed` 15 次中失敗 11 次：測試讓 `fail` 卡在 lifecycle 鎖上，晚於 delivery thread 讀取結果。已恢復，並新增 host 測試鎖定這個時間窗。
2. **「控制錯誤讓等待中的段落立即失敗」不是可觀察行為**。`lifecycle.fail` 不會讓還在等資源的段落插隊；master 的 RHVoice 也一樣。改以「進行中的段落立即被停止」驗證開啟後的差異。
3. 實測數字：Task 1 完成後 1341 passed；Task 2 完成後 1343 passed、96 skipped、2 xfailed（host 新增 15 個、lifecycle 1 個、RHVoice 2 個）。
