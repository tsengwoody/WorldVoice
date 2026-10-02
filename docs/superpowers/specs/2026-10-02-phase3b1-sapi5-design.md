# 階段 3b-1：SegmentHost 共用擴充與 SAPI5 遷移

日期：2026-10-02。
基準：`master`（`7448e9c`，含 3a）。分支：`phase3b1-sapi5`。
狀態：使用者已審閱並核可。2026-10-02 依原型結果修訂，修訂處列於文末「原型修訂」。

本文件是 [`refactor.md`](../../../refactor.md) §9 階段 3 的子階段 3b-1。前一子階段見 [2026-10-01-phase3a-segment-host-design.md](2026-10-01-phase3a-segment-host-design.md)。

## 3b 的拆分（使用者已確認）

| 子階段 | 內容 |
| --- | --- |
| **3b-1**（本文件） | 參考 RHVoice 與 SAPI5 兩份分析，一次設計完整的 host 擴充；實作其中 SAPI5 用得到的部分，並遷移 SAPI5，修正 C2 |
| 3b-2 | RHVoice 專屬擴充（退場 thread 上的 `finish`／`seal`、同步 cancel 等待、選用的「控制錯誤讓所有已接受工作失敗」），並遷移 RHVoice |

拆分理由：
- SAPI5 的形狀最接近已遷移的 eSpeak：每段一條 lifecycle thread，原生工作交給引擎自己的 FIFO worker，不需要新的執行模式。
- 遷移後 C2 會自然消失。
- RHVoice 需要的擴充最新，放在 host 已由 SAPI5 驗證之後。

## 需求與範圍

已確認的決定：

1. **共用擴充一次設計**：介面同時參考兩份分析，避免 3b-2 回頭改介面；3b-1 只實作 SAPI5 用得到的部分。
2. **`reset()` 連 lifecycle 一起重建**：SAPI5 重新載入語音時，清除控制錯誤，並換一個新的 `SegmentLifecycle`。理由是現況的 lifecycle fault 永遠不會清除，一旦發生，之後每一段都被拒絕，連換語音也無法恢復。
3. **沿用 3a 的限制**：
   - 不考慮 Neural 相容性。
   - 不共用 VE/Cerence 程式碼；所有引擎共用的程式碼只放在 `runtime/segmentHost.py`。
   - 新增的公開名稱用 snake_case。
4. **plan 流程**：變異步驟一律放在 commit 之後（3a、階段 2 都曾因變異步驟在 commit 之前，被 `git checkout` 還原未提交的修改）。

成功條件：

1. **C2 修正**：以重現測試證明——hook 在 native 綁定後拋出例外時，一般語音仍會送進 native，且 `terminate()` 在 2 秒內返回。此測試在遷移前失敗、遷移後通過。
2. **SAPI5 改用 `SegmentHost`**：不再出現 `SegmentLifecycle`／`_segmentLifecycle`；守門測試的 `MIGRATED` 加入 `"SAPI5"`。
3. **SAPI5 既有 drain 測試全部通過**：只有讀取已移除內部實作的地方才改為透過 host 讀取，並在 plan 中逐一列出。
4. **未遷移引擎的相容性**（硬性要求）：
   - RHVoice、OneCore、VE、Cerence 的 wrapper 原始碼完全不改（`git diff master` 無輸出）。
   - 它們的 drain 測試、契約測試照常通過；契約 4 的 VE、Cerence 仍為 xfail。
   - eSpeak 的 drain 測試照常通過。
5. **host 擴充的單元測試**：每一項擴充都有單元測試，並至少以一次變異證明它能失敗。
6. **完整測試**：基線 1306 passed、96 skipped、2 xfailed；完成後為 1324 passed、96 skipped、2 xfailed（host 新增 16 個、SAPI5 新增 2 個）。
7. **格式與保護路徑**：`ruff format --check addon` 通過；內層驅動與 Neural 不變。

**不在範圍內**：RHVoice 遷移與其專屬擴充（3b-2）、OneCore（3c）、VE/Cerence 與 C3（3d）、把 `SegmentLifecycle` 收為內部實作（3e）。

## 現況

### C2（已確認存在，屬於潛在問題）

基準 `7448e9c` 的 `driver/SAPI5/__init__.py`：

1. `_speakThread` 綁定 request 後，在 EndStream 時設定 `boundary`、`retired`，然後**無條件**等待 `binding.playback_done.wait()`。
2. 若任一 hook 在綁定之後拋出例外，lifecycle 的 `_run_owned` 會 latch fault。
3. `run()` 的 `finally` 中，`needs_playback` 要求 `self._fault is None`，因此不會呼叫 `wait_playback_drained`。
4. `playback_done` 只在 `wait_playback_drained` 的 `finally`，或 `_invalidateSegments`／`_failSegmentControl` 中 `native is None` 時才會設定；此時兩者都不會觸發。
5. 後果：
   - worker 永久卡住，一般語音再也送不進 native。
   - `terminate()`／`_initTts()` 透過 NVDA 的 `_stopThread` 呼叫 `join()`，沒有逾時，會一直卡住。
   - worker 不是 daemon thread，連 process 結束都會被擋住。
   - lifecycle 的 `_fault` 從不清除，之後每一段都被拒絕。

以目前的 hook 程式碼，觸發條件幾乎走不到，所以屬於潛在問題。但只要 hook 或 `_stop_if_cancelled` 的 thread 啟動失敗，就會發生。

### SAPI5 wrapper 與 host 的對應

| 元件 | 3b-1 之後 |
| --- | --- |
| `_NativeRequest`（work、operation、cancelled、error、feeds…） | 共通欄位由 `NativeRecord` 取代；`request`、`stream`、`index_lock` 等 SAPI5 專屬資料放進 `record.native`（`_SapiRequest`）；音訊關閉改用 `record.admitting` |
| `_OperationBinding`（boundary、retired、playback_done、handoff、player/tts 快照） | `retired`／`handoff` 由 `NativeRecord` 提供；`playback_done` 移除（C2 的來源）；快照放進 `record.native` |
| `_SegmentAudioStream`（COM `RemoteWrite`，Sonic 前處理） | 保留，consumer 進出改用 `host.consumer` 與 `bound_callback` |
| `_SegmentPlayer.feed` | 保留為 SAPI5 專屬，改用 host 的 consumer API。不換成 `LeasedPlayer`，因為沒有目前紀錄時必須直接轉送，且要檢查過期的 player |
| `_SegmentPlayer.idle`（提早 idle 檢查） | 保留 |
| `_SegmentSapiSink`（stream 對應、拒絕過期事件、`EndStream`） | 保留；`EndStream` 改為標記屏障 |
| `speak_segment`、`_runSegmentOperation`、五個 hook | 由 host 取代；`drain` 由 SAPI5 strategy 提供 |
| `_invalidateSegments`、`_failSegmentControl` | 改用 `host.cancel`、`host.latch_control_error` 與 `host.abandon` |
| `_speakThread` | 保留，作為 strategy 的 FIFO worker，改用 `host.begin`／`host.retire` |
| `_initTts`、`_initWasapiAudio` | 保留，改呼叫 `host.reset()` |
| legacy（非 WASAPI）路徑 | 保留：一般語音不經 `host.enqueue`，但仍檢查終止與控制錯誤；segment 照舊以 FAILED 拒絕 |

## 設計

### 1. host 擴充

| 擴充 | 介面 | 3b-1 用途 | 3b-2 用途 |
| --- | --- | --- | --- |
| 引擎資料欄位 | `NativeRecord.native: object \| None = None` | request、stream、快照 | identity |
| 每筆屏障 | `host.new_record(operation=None, *, barriers=None, native=None)`；`enqueue(commands, operation=None, *, barriers=None, native=None)` | 一般語音不需要 `idle` | 一般語音也需要 final idle |
| drain hook | 選用 `NativeStrategy.drain(host, record) -> None` | player idle + `reach("idle")` | 不用（改用 `finish`） |
| 退場後仍可停止 | `request_stop` 對「目前紀錄」或「已 retired、尚未 handoff」的紀錄呼叫 `stop_native` | NVDA cancel（`host.cancel` → `lifecycle.cancel` → `request_stop`）能打斷 drain 中的 idle；只靠 token 的取消在 drain 期間到不了 lifecycle | — |
| 引擎准入檢查 | 選用 `NativeStrategy.admission_error(host) -> Exception \| None`；`speak_segment` 在接受前呼叫，有錯誤就拒絕 | worker 不存在、非 WASAPI 或沒有 player | — |
| lifecycle fault 查詢 | 唯讀 `SegmentLifecycle.fault` | C2 缺口只在 fault 時停止 player | — |
| 兩段式關閉 | `host.close(record)`：不再接受新的 consumer；`host.wait_consumers(record)`：等歸零 | EndStream 時關閉，等 feed 歸零後才 flush Sonic | 音訊階段的關閉 |
| 巢狀 consumer | `host.consumer(record)`：record 已關閉時，若目前 thread 的 `callback_record()` 就是它，仍允許進入 | `RemoteWrite` 內的巢狀 feed | 同左 |
| 放棄紀錄 | `host.abandon(record)` | NVDA cancel 清空佇列後的紀錄 | 同左 |
| 重建 | `host.reset()` | `_initTts`／`_initWasapiAudio` | — |

細節：

- **`drain` 的呼叫時機**：`wait_playback_drained` 在工作仍有效、紀錄沒有錯誤時呼叫，排在屏障檢查之前。
  - strategy 沒有實作 `drain` 時，行為與 3a 相同。
  - `drain` 不應拋出例外；若拋出，host 會 `record_error`、`lifecycle.fail` 並 `stop_player`，不讓它變成永久的 lifecycle fault。
  - `drain` 必須可以重複呼叫，因為 lifecycle 在停止與排空的競態下可能再次呼叫。
- **`abandon(record)`**：
  - 關閉紀錄、等 consumer 歸零、退掉 producer、設定 `retired`、移出待處理清單。
  - 不等 `handoff`，因為呼叫它的 thread（NVDA cancel）不是 FIFO worker。
  - 已退場的紀錄重複呼叫不會出錯。
- **`reset()`**：
  - 必須在 `host.admission()` 下、且舊 worker 已 join 之後呼叫。
  - 做的事：
    1. 在 admission 下取消所有已接受的工作。
    2. 清除控制錯誤與紀錄簿記（目前紀錄、待處理清單、紀錄對應、已接受集合）。
    3. 換上新的 `SegmentLifecycle(self)`，再 `terminate()` 舊 lifecycle。
    4. 離開 admission 後，對舊 lifecycle `join_delivery(1)`。
  - 已終止的 host 呼叫 `reset()` 時不做任何事。
- **C2 缺口**：`_run` 的 `finally` 在設定 `handoff` 之前，若 lifecycle 已 latch fault（`lifecycle.fault is not None`），先呼叫 `strategy.stop_player()`（例外以 log 記錄）。一般的取消不觸發，因為 eSpeak 既有測試禁止在佇列中的取消時停止 player。
- **`enqueue` 的邊界情況**：
  - 工作已失效：不送出，直接 abandon（由 `admit_producer` 拒絕已失效的工作，不需另外檢查）。
  - `admit_producer` 回傳 None：abandon。
  - `strategy.submit` 拋出例外：
    - segment：`record_error` 並 abandon，例外不再往外拋給 lifecycle。
    - 一般語音：`forget` 後照舊往外拋給呼叫端。
- **延後的 Minor 一併處理**：
  - `enqueue` 拿掉多餘的 `work` 參數（一律取自 `operation.work`；一般語音為 None）。
  - `wait_native_boundary` 改用 `.get`，紀錄不存在時直接返回。
  - `LeasedPlayer.feed` 以關鍵字參數傳 `onDone`，並記錄 `onDone` 拋出的錯誤。
- **eSpeak**：只有 `enqueue` 呼叫方式隨簽名調整，行為不變；eSpeak 測試照常通過。

### 2. SAPI5 遷移

- `SynthDriver` 建立 `self._segmentHost = SegmentHost("SAPI5", _Sapi5Strategy(self))`。
- **`_Sapi5Strategy`**：
  - `barriers = frozenset({"ended", "processed", "idle"})`；一般語音紀錄以 `barriers={"ended", "processed"}` 建立。
  - `submit`：把 request 放進 SAPI5 的請求佇列，交給 `_speakThread`。
  - `stop_native`：紀錄是目前紀錄時設定 `_isCancelling` 並喚醒 worker（由 worker purge）；再停止紀錄快照中的 player。停止失敗交給 `_failSegmentControl`（`latch_control_error`、清空佇列並 abandon），不往外拋。
  - `stop_player`：停止 player。
  - `drain`：
    - 正常情況：用 `record.native` 裡的 player 快照呼叫原始的 `idle()`，然後 `reach(record, "idle")`。
    - 出錯時：先停止、再 purge；停止或 purge 失敗時 `latch_control_error`，然後 `record_error`。
    - 沒有 player（legacy）時以錯誤處理，不得回報 drained。
- **`_speakThread`**：
  - 取出 request 後 `host.begin(record)`，送出 SAPI `Speak`。
  - EndStream 時 `host.close(record)`、`host.wait_consumers(record)`、flush Sonic、送出尾段音訊。
  - 然後 `host.retire(record)`；不再等 `playback_done`。
- **`_SegmentSapiSink`**：`EndStream` 時 `host.reach(record, "ended")`；處理完畢後 `host.reach(record, "processed")`。
- **cancel**：
  - 在 `host.admission()` 下：先遞增 `_segmentStops`，再於 `_threadCond` 下呼叫 `host.cancel()` 並清空 SAPI5 請求佇列。
  - 釋放 `_threadCond` 後，對被丟掉的紀錄逐一 `host.abandon(record)`；abandon 要等 consumer，而 `RemoteWrite` 會取用 `_threadCond`。
  - 離開 admission 後呼叫 NVDA 的 `super().cancel()`，結束時遞減 `_segmentStops`。
- **`_initTts`／`_initWasapiAudio`**：
  - WASAPI：`_initWasapiAudio` 在父類別已 join 舊 worker、啟動新 worker 之前呼叫 `host.reset()`。
  - legacy：`_initTts` 在父類別初始化後呼叫 `host.reset()`。
- **legacy 路徑**：
  - 一般語音照舊同步送出，不經過 `host.enqueue`。
  - 仍先檢查 `host.terminated` 與 `host.control_error`；終止後維持現況拋出例外，不是靜默忽略。
- **SAPI5 專屬保留**：COM `RemoteWrite`、Sonic、提早 idle 檢查、stream 對應、bookmark 處理。

## 測試

- **C2 重現**（`tests/test_sapi5_segment_drain.py`）：
  - 不使用 `env` fixture，因為它的收尾 `terminate()` 在修正前會卡住。
  - 讓 `wait_native_retired`（遷移後為 host 的對應 hook）在綁定後拋出 `RuntimeError`。
  - 斷言該段回報 `SEGMENT_FAILED`；接著送出的一般語音在 1 秒內送進 native；`terminate()` 在 daemon thread 上於 2 秒內返回。
  - 遷移前必須失敗，並在測試中提供釋放手段，避免卡住測試程序。
- **host 擴充**（`tests/test_segment_host.py`）：每一項擴充各有測試。
  - drain 的呼叫時機、例外處理與重複呼叫。
  - drain 期間的 `request_stop`。
  - close 之後拒絕新 consumer、允許巢狀 consumer。
  - abandon 不等 handoff。
  - reset 之後可以接受新的 segment。
  - `_run` 在 fault 時停止 player。
  - `enqueue` 的三個邊界情況。
  - `LeasedPlayer` 的 `onDone` 錯誤記錄。
- **SAPI5 既有測試**：讀取已移除內部實作的地方共 6 處：`tests/test_sapi5_segment_drain.py` 的 `_segmentNative`、patch `submit_native`、patch `wait_playback_drained`、`_segmentLifecycle._operations` 與 harness 載入 `segmentHost`，以及 `tests/test_runtime_completion_policies.py` 的 `_segmentNative`。改為透過 host 讀取。
- **一般語音不被截斷**（`test_completed_ordinary_speech_does_not_stop_the_player`）：一般語音完成後 player 不得被停止。若一般紀錄要求 `idle`，host 的缺屏障路徑會在每句話後停止 player。
- **eSpeak**：`tests/test_espeak_segment_drain.py` 的 `queue_then_hold` 隨 `enqueue` 新簽名調整。
- **契約、eSpeak 與其他引擎**：全部照常通過。
- **變異證明**：在 commit 之後執行，每個新的 host 行為至少一次。

## 驗收

- `python3 -m pytest tests -q`：全部通過；skipped 96、xfailed 2。
- `git diff master --stat -- addon/synthDrivers/WorldVoice/driver/{RHVoice,OneCore,VE,Cerence}/__init__.py`：無輸出。
- `grep -n "_segmentLifecycle\|SegmentLifecycle" addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py`：無輸出。
- `grep -n "playback_done" addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py`：無輸出。
- `ruff format --check addon`：通過；內層驅動無變動；Neural 未被追蹤。

## 原型修訂（2026-10-02）

原型與乾淨重播後，對原設計做了以下修訂；plan 依修訂後的內容撰寫：

1. 新增選用 hook `NativeStrategy.admission_error(host)`，讓 SAPI5 在接受前拒絕 legacy／無 worker 的 segment。
2. 新增唯讀 `SegmentLifecycle.fault`；C2 缺口只在 lifecycle fault 時停止 player，一般取消不觸發。
3. drain 中的停止由 NVDA cancel 觸發，而非只靠 token 的取消。
4. `_SegmentPlayer` 保留為 SAPI5 專屬（沒有紀錄時直接轉送、過期 player 檢查），不換成 `LeasedPlayer`。
5. `enqueue` 不另外檢查工作是否有效，由 `admit_producer` 拒絕；一般語音的 submit 錯誤照舊往外拋。
6. `reset()` 的順序調整為：取消、清空、換新 lifecycle、終止舊 lifecycle，`join_delivery(1)` 在 admission 之外。
7. 讀取內部實作的測試共 6 處（多了 `tests/test_runtime_completion_policies.py`）；另新增一般語音不被截斷的守門測試。
8. 實測數字：完成後 1324 passed、96 skipped、2 xfailed。
