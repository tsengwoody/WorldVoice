# 階段 3c：OneCore 遷移到 SegmentHost

日期：2026-10-02。
基準：`master`（`499a8a2`，含 3b-2）。分支：`phase3c-onecore`。
狀態：使用者已審閱並核可。2026-10-02 依原型結果修訂，修訂處列於文末「原型修訂」。

本文件是 [`refactor.md`](../../../refactor.md) §9 階段 3 的子階段 3c。前一子階段見 [2026-10-02-phase3b2-rhvoice-design.md](2026-10-02-phase3b2-rhvoice-design.md)。

## 需求與範圍

已確認的決定：

1. **做法 A：沿用現有 host 模型**。每個 segment 各有一條 lifecycle thread，資源空出後才送進 OneCore 的 `_queuedSpeech`；不新增「由引擎 worker 執行」的模式。使用者已了解並接受由此產生的設定順序差異（見「行為變化」）。
2. **3b-1 記下的 OneCore `request_stop` 無條件停止**：改由 host 只對「目前或排空中」的紀錄呼叫 `stop_native` 來解決。
3. **沿用的限制**：
   - 不考慮 Neural 相容性。
   - 不共用 VE/Cerence 程式碼；所有引擎共用的程式碼只放在 `runtime/`。
   - 只改外層 wrapper，不改內層驅動 `driver/OneCore/driver/`。
   - 新增的公開名稱用 snake_case。
4. **plan 流程**：變異步驟一律放在 commit 之後。

成功條件：

1. **OneCore 改用 `SegmentHost`**：不再出現 `SegmentLifecycle`／`_segmentLifecycle`／`CallbackGate`；守門測試的 `MIGRATED` 加入 `"OneCore"`。
2. **OneCore 既有 drain 測試全部通過**：只有讀取已移除內部實作的地方才改為透過 host 讀取，plan 逐一列出。
3. **其他引擎的相容性**（硬性要求）：
   - VE、Cerence、eSpeak、SAPI5、RHVoice 的 wrapper 原始碼完全不改（`git diff master` 無輸出）。
   - 它們的 drain 測試、契約測試照常通過；契約 4 的 VE、Cerence 仍為 xfail。
4. **新擴充的單元測試**：每一項都有測試，並至少以一次變異證明它能失敗。
5. **完整測試**：基線 1343 passed、96 skipped、2 xfailed，加上本階段新增測試；xfailed 仍為 2。
6. **格式與保護路徑**：`ruff format --check addon` 通過；內層驅動與 Neural 不變。

**不在範圍內**：VE/Cerence 與 C3（3d）、把 `SegmentLifecycle` 收為內部實作（3e）、OneCore 的父類別私有存取集中化（refactor.md 的 `_InnerDriverAccess` 建議）。

## 現況

基準 `499a8a2` 的 `driver/OneCore/__init__.py`（686 行）：

- `speak_segment` 在呼叫端 thread 接受 operation、做 SSML 轉換，再把 `_SpeechJob` 放進父類別的 `_queuedSpeech`。
- 外層 worker `_runSegmentQueue` 依呼叫順序處理佇列中的三種項目：設定 tuple、一般語音文字、segment 工作。segment 直接在 worker 上執行 `lifecycle.run`，因此設定變更與語音嚴格依呼叫順序生效。這與 NVDA 內建 OneCore 的語意相同。
- native `ocSpeech_speak` 是非同步的，結果由另一條 thread 上的 `_callback` 一次送回整段 WAV 與 markers。
- 自己的 `CallbackGate`、子 lease、`_segmentAccepted`、`_segmentActiveOperation` 簿記。
- `request_stop` 無條件停止 player（3b-1 記錄的問題）。
- 暫停：pause lock、`_segmentPaused`、`_segmentControlGeneration`，drain 時暫停中要等待恢復。
- 控制錯誤：兩段式 capture（在 pause lock 下）與 deliver（讓已接受與佇列中的工作失敗、停止 player、legacy DONE）。

**為何前三家不需要新模式**：eSpeak、SAPI5 的設定立即生效；RHVoice 在 `submit` 時才把設定抄進語音工作。它們在遷移前，segment 也是 lifecycle 輪到時才送進引擎，遷移沒有改變行為。只有 OneCore 把設定 tuple 和語音放在同一個佇列。

## 設計

### 1. host 與 lifecycle 擴充

| 擴充 | 介面 | OneCore 用途 |
| --- | --- | --- |
| 準備 hook | 選用 `NativeStrategy.prepare(host, commands, operation) -> commands`：`enqueue` 在取得 host admission 之前呼叫，回傳值交給 `submit` | SSML 轉換 |
| 未取得資源者失敗立即發布 | `SegmentLifecycle.fail` 對尚未取得資源的 operation（尚未 `run`，或在 `run` 裡等資源）同步 reject 並送出 FAILED；之後它的 `run()` 直接返回 | 控制錯誤時，排隊中的 segment 立即 FAILED |

細節：

- **`prepare`**：
  - 在 admission 之外執行，`cancel()`／`terminate()` 不會等它。
  - segment 出錯時對該 operation 呼叫 `lifecycle.fail` 後返回，不建立紀錄；一般語音出錯時往外拋給呼叫端。
  - 沒有實作時行為與 3b-2 相同。
  - 理由：`submit` 在 admission 下執行。master 在任何鎖之外做 SSML 轉換，且測試要求轉換進行中 `cancel()` 仍可完成。
- **等待中失敗立即發布**：
  - 理由：master 的排隊 segment 尚未進入 `lifecycle.run`，可以 `reject_pending`。在 host 模型下它已在 `run` 裡等資源，`fail` 只會標記錯誤；若前一段的 sink 先 cancel，這個 FAILED 會被靜默（`test_control_error_fails_queued_contexts_and_allows_reentrant_cancel`）。
  - 影響所有引擎，但只影響「等資源時被 fail」的段落：FAILED 提早送出。這類段落原本就不可能送進 native。
- **沿用既有能力**：`drain` hook、`fail_accepted_on_control_error=True`、`request_stop` 只停止目前或排空中的紀錄。

### 2. OneCore 遷移

| 元件 | 3c 之後 |
| --- | --- |
| `_SpeechJob`／`_NativeJob`、`CallbackGate`、子 lease、`_segmentAccepted`、`_segmentActiveOperation` | 由 `NativeRecord` 與 host consumer 取代；SSML 與「callback 已返回」旗標放進 `record.native`（`_OneCoreNative`）；`_queuedSpeech` 裡的工作為 `_SpeechJob(record)` |
| `speak_segment` | 改為 `host.speak_segment`；轉換移到 `prepare`，排隊移到 `submit` |
| `_OneCoreStrategy` | 見下 |
| `_runSegmentQueue` | 保留，依佇列順序處理設定 tuple、一般語音、segment；每筆紀錄：`host.begin` → `player.open()` → `ocSpeech_speak` → 等 native callback 返回 → `host.retire`（segment 等 handoff，即 drain 完成）；終止時仍未收到 callback 的紀錄 `abandon` |
| `_DetachableCallback` | 保留；callback 返回後先 `_retireSegmentNative`（`close`：此後不再接受這筆紀錄的 native callback），再釋放 worker |
| `_callback`（segment） | 以 `host.consumer(record)` + `bound_callback` 解析 WAV 並 feed；成功 `reach("callback")`；錯誤 `record_error` 並停止 player；index 通知依 `record.work.is_valid()` |
| `_callback`（legacy） | 沿用 master 的 queue-empty sync／idle／DONE；成功 `reach("callback")` |
| 一般語音 | `speak()` → 父類別轉換 → `_queueSpeech(text)` → `host.enqueue(text, barriers={"callback"})`；設定 tuple 由父類別直接放進 `_queuedSpeech`，不變 |
| 控制錯誤 | 兩段式保留：capture 改用 `host.latch_control_error`，清空佇列；deliver 對佇列中的紀錄 `abandon`、停止 player、legacy DONE |
| pause、`_maybeInitPlayer` | 保留 |
| `cancel()` | `host.admission()` 下：`host.cancel()`、遞增 `_segmentStops`、移除佇列中的工作（保留設定 tuple）並逐一 `abandon`；之後沿用 master 的停止與暫停解除 |
| `terminate()` | 設定終止旗標 → detach callback → `cancel()` → `host.terminate()` → 父類別 `terminate()` |

`_OneCoreStrategy`：
- `barriers = {"callback", "synced"}`。
- `admission_error`：wrapper 已終止，或 legacy 合成進行中時拒絕切換到 correlated 播放。
- `prepare`：segment 做 SSML 轉換（API5 以上用 `_OcSsmlConverter`，否則 `_OcPreAPI5SsmlConverter`）；一般語音原樣返回。
- `submit`：建立 `_OneCoreNative(text)`，放進 `_queuedSpeech`，喚醒 worker。
- `stop_native`／`stop_player`：停止 player。
- `drain`：~~`player.sync()`，暫停中等待恢復，然後 `reach("synced")`；~~ 真正 player 的 `idle()`（每段一次），然後 `reach(PLAYED_OUT)`；暫停後的等待由 scheduler 處理（Corrected by `phase54-drain-semantics`）；失敗時 `record_error` 並走控制錯誤流程。

保留的名稱（測試會讀取）：`_segmentNative`、`_callback`、`_retireSegmentNative`、`_failSegmentControl`、`_deliverSegmentControlFailure`、`_segmentWorker`、`_queuedSpeech`、`_segmentCondition`。

`SegmentHost` 以 `fail_accepted_on_control_error=True` 建立。

**行為變化**：
1. **設定順序**（使用者選 A）：segment 已排隊、尚未送出時改 rate／volume，新設定會套用到這個 segment。一般語音 `speak()` 與設定的順序不變。WorldVoice 的 scheduler 一次只處理一段（套用設定 → `speak_segment` → 等 DRAINED／FAILED），正常使用時不會出現這個情境。
2. **SSML 轉換時機**：從 `speak_segment` 的呼叫端 thread 移到 lifecycle thread、送出前一刻。
3. **等資源時被 fail 的段落**，FAILED 提早送出。
4. 其餘可觀察行為與 master 相同。

## 測試

- **host**（`tests/test_segment_host.py`）：
  - `prepare` 在 admission 之外執行：`prepare` 進行中 `host.cancel()` 可以完成。
  - `prepare` 的回傳值就是 `submit` 收到的內容。
  - segment 的 `prepare` 出錯：該段 FAILED，下一段不受影響；一般語音出錯則往外拋。
- **lifecycle**（`tests/test_segment_lifecycle.py`）：
  - 在等資源時被 `fail` 的 operation，在資源釋放前就送出 FAILED，只送一次，且從未呼叫 `submit_native`。
  - 尚未 `run` 就被 `fail` 的 operation 立即送出 FAILED；之後的 `run()` 不送出、不再發布。
- **OneCore**（`tests/test_onecore_segment_drain.py`），把做法 A 寫成測試：
  - segment 排在播放中段落之後時改 rate，設定在排隊 segment 送出前套用；
  - 一般語音 `speak()` 與設定依呼叫順序執行。
  - 排在一般語音後面的 segment：cancel 會釋放它（後續 segment 照常排空），控制錯誤會讓它 FAILED。
- **OneCore 既有測試**，讀取已移除內部實作的地方共 20 處：
  - fixture 一併清除 `segmentHost` 模組快取。
  - `_segmentLifecycle` → `_segmentHost._lifecycle`（15 處，其中 `isinstance(..., SegmentLifecycle)` 改為檢查 `SegmentHost`）。
  - `_segmentAccepted` → `_segmentHost._accepted`（2 處）。
  - `_segmentControlError` → `_segmentHost.control_error`。
  - `_segmentActiveOperation is None` → `_segmentNative is None`。
- **守門**：`MIGRATED = ("Espeak", "SAPI5", "RHVoice", "OneCore")`。
- **變異證明**：在 commit 之後執行，每項新行為至少一次。

## 驗收

- `python3 -m pytest tests -q`：全部通過；skipped 96、xfailed 2。
- `git diff master --stat -- addon/synthDrivers/WorldVoice/driver/{VE,Cerence,Espeak,SAPI5,RHVoice}/__init__.py`：無輸出。
- `grep -n "_segmentLifecycle\|SegmentLifecycle\|CallbackGate" addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py`：無輸出。
- `ruff format --check addon`：通過；內層驅動無變動；Neural 未被追蹤。

## 原型修訂（2026-10-02）

原型與乾淨重播後，對原設計做了以下修訂；plan 依修訂後的內容撰寫：

1. **lifecycle 改為在 `fail()` 同步發布**，而不是讓等資源的 `run()` 醒來後自己發布。原型第一版的做法讓 `test_control_error_fails_queued_contexts_and_allows_reentrant_cancel` 約 1/30 失敗：等待中的 thread 還沒醒來，前一段的 sink 已經 cancel 並把它靜默。同步發布後連跑 100 次通過。範圍也擴大到「尚未 `run`」的 operation（第一版只處理等待中的）。
2. **`_retireSegmentNative` 只做 `close`**：原本的 `wait_consumers` 是多餘的（callback 自己的 consumer 已在它之前離開，`retire` 也會等），變異證明它不影響任何行為。
3. **新增「排在一般語音後面的 segment」測試**：在做法 A 下，這是 segment 紀錄唯一會停在 `_queuedSpeech` 的情況；cancel 與控制錯誤若沒有 abandon 它，它的 lifecycle 會永遠等待。原本沒有測試涵蓋。
4. 原型期間 OneCore 測試檔約 230 次中出現一次無法重現的失敗，未記錄到是哪個測試；plan 的 Review Focus 第 5 項請最終審查特別檢查。
5. 實測數字：Task 1 完成後 1349 passed；Task 2 完成後 1353 passed、96 skipped、2 xfailed（host 新增 4 個、lifecycle 2 個、OneCore 4 個）。
