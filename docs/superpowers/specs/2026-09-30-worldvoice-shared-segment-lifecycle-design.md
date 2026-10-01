# WorldVoice 七引擎共用 segment 生命週期設計

日期：2026-09-30。
基準：`5803b4e`，分支 `test/force-segment-end-index-all-engines`。
狀態：對話中的範圍與架構已獲使用者確認；本文件待使用者審閱。

本文件補充 [既有 correlated DRAIN 設計](2026-09-28-worldvoice-correlated-drain-design.md)。既有文件記錄最初四個引擎的設計當時狀態；目前程式已有 OneCore、Neural、VE、Cerence、SAPI5、eSpeak、RHVoice 七個外層 wrapper。七者的 DRAIN 運作路徑已啟用，其中 SAPI5 僅涵蓋 WASAPI。

## 需求與範圍

使用者要讓七個 wrapper 共用同一個 segment 生命週期流程：接受帶有 `PlaybackContext` 的工作；取消時關閉該工作的新 callback／音訊 admission；等待舊 native 工作與已進入的 callback、feed 退場；確認該段最後音訊的播放屏障；最後只回報一次帶原 `source_id`、`segment_id` 的成功或失敗事件。各引擎繼續提供自己的 native 提交與停止方式、callback 退場依據，以及播放屏障。

本次將 **SAPI5 現有 WASAPI DRAIN 路徑** 納入共用流程。SAPI5 `useWasapi=False` 的 legacy 音訊仍依目前政策使用 `LEGACY_DONE`；為它建立可證明播放排空的屏障與啟用 DRAIN，屬下一個 change。本次不把 `EndStream` 或匿名 `synthDoneSpeaking` 重新命名為 legacy DRAIN。

成功條件：

1. 七個已啟用 DRAIN 的外層 wrapper 都使用同一個生命週期 coordinator 與 hook 介面，不能僅增加同名方法而仍由七份互不相關的程式自行決定完成順序。
2. 取消或失敗優先於成功；舊 callback、feed、index、drain 及 native 工作不得完成或餵音訊給後繼 segment。新 segment 可以排隊，但不得在舊工作資源退場前開始使用同一 native/player 資源。
3. `SEGMENT_DRAINED` 只在該段 native/producer 退場及該引擎既有的最後播放屏障完成後發布。`SEGMENT_FAILED` 對應原工作，事件至多一次；取消不產生成功事件。
4. 一般 `speak`、NVDA 語音設定、原始 index 的轉送、既有 completion policy 和 unknown/external engine fallback 不因抽取介面而改變。
5. 本設計重構不建立新的 SDK callback 靜默或 Windows 實機播放認證；既有明確啟用 DRAIN 的證據界線維持記錄。

## 現況與方案

`runtime/playbackWork.py` 已有 `PlaybackWork`，負責保存 context、取消身分及一次性 terminal 事件；`CallbackGate` 負責 native call 和已進入 callback 的 lease。OneCore、Neural、VE、Cerence 使用 `CallbackGate`；SAPI5、eSpeak、RHVoice 則有各自的請求、音訊或 worker 退場紀錄。各 wrapper 現在各自串接取消、等待和事件交付，流程順序及重入保護分散於七處。

選定方案是 **共用 coordinator 加 engine-specific hooks**。僅定義一份 `Protocol` 而讓七個 wrapper 繼續各自判斷完成順序，無法保證共用流程；把 native callback、COM、CFFI 和 player 細節塞進單一泛用 driver，則會混淆各引擎不同的歸屬及排空訊號。coordinator 只管理可跨引擎共用的狀態與順序，hooks 提供可由各引擎證明的邊界。

## 元件與責任

在 `runtime/segmentLifecycle.py` 建立每個 core 一個 `SegmentLifecycle`，以及每段一個 `SegmentOperation`；定義 `SegmentEngineHooks` 供七個 wrapper 實作。沿用現有 `PlaybackWork` 作為事件及取消身分的唯一來源。coordinator 擁有以下狀態：工作已接受、native 已提交、取消／失敗已鎖存、舊 producer 是否退場、播放屏障是否完成、terminal 是否已排程及交付。狀態轉移以每段原始 context 為鍵，不能從目前正在播放的段落反查舊 callback 的身分。

coordinator 對 wrapper 提供以下語義介面；確切 Python 方法簽名由後續 plan 固定：

- `accept(context, token, sink)`：建立並登記工作；取消或終止中的舊工作停止接收新 producer。後繼工作可以排隊等待安全交接。
- `admit_producer(operation)`／`retire_producer(lease)`：讓 native callback、nested feed、播放器 feed 與外部 delivery 保留原工作身分。正常 native 結束後，已接受 callback／feed 所啟動的巢狀 feed 或播放器 onDone 仍須綁定原 operation 並完成其退場；新的、無此因果關係的 native callback 不得接管舊工作。取消後這些舊 consumer 只可清理退場，不得再餵音訊或轉送 index。lease 必須涵蓋巢狀操作的實際存活期。
- `close_admission(operation)` 與 `cancel(operation)`：先使舊工作失效並停止接收新 producer，再安排 engine hook 執行 native stop／播放器 stop。取消不能直接把 callback 計數歸零。
- `complete(operation)`：由安全的 worker 執行共用順序：等待 hook 到達該引擎不再建立新 producer 的 native 結束邊界，才關閉正常路徑的 admission；等待已進入 producer 退場；等待 hook 的該段播放屏障；重查取消／錯誤狀態，再排程 `SEGMENT_DRAINED`。仍有效的工作在任何階段出錯則走 `SEGMENT_FAILED`。
- `fail(operation, error)`／`terminate()`：鎖存失敗、阻止成功、清理工作與交付所有權。無法證實舊資源已退場時，阻擋後繼 native 提交，不能把未知狀態當成成功退場。

各 wrapper 提供 `SegmentEngineHooks` 介面，至少包含 `submit_native(operation, commands)`、`request_stop(operation)`、`wait_native_retired(operation)`、`wait_playback_drained(operation)`。hook 可使用現有 callback gate、COM stream ID、工作佇列或播放器 API。`wait_native_retired` 必須涵蓋已提交的 native call、可繼續產生 callback 的 producer，以及已進入 callback/feed 的 lease；hook 必須告知 coordinator 何時可以關閉正常路徑的新 producer admission。觀察到「目前計數為零」本身不等於未來不會有新 callback。`wait_playback_drained` 必須使用該引擎當前 DRAIN 路徑的實際尾音屏障，不可只看 native 合成函式返回或尾端 index。

coordinator 的狀態鎖只保護狀態，不包住 native 呼叫、播放器操作、等待或事件 sink。coordinator 管理 terminal delivery queue，從不在 native、COM 或 driver worker callback stack 直接呼叫外部 sink；sink 重入 cancel／terminate 時也不能等待自己的 delivery 執行緒。`PlaybackWork` 繼續提供最終的一次性檢查；coordinator 在排程交付及真正交付前保留 operation 所有權，避免取消或 terminate 後的晚到成功。

一般 NVDA `speak` 路徑保留現有外部相容行為。若 legacy 工作與 contextual segment 共用 native/player，對應 hook 必須沿用現有的交接保護，直到舊資源退場。現有 `speak_segment(commands, token, *, context, on_event)`、`get_segment_drain_support`、adapter、bridge、ledger 及 scheduler 的外部契約保持不變。

## 七個 adapter 的邊界

| Engine | native／producer 退場 hook | 播放屏障 hook |
| --- | --- | --- |
| OneCore | `ocSpeech_speak` 工作、固定 callback 指標及 callback lease 退場 | 已餵入最後 PCM 後的現有 `sync`／播放器屏障 |
| Neural | task queue、SDK `speak_ssml`／stop、audio/bookmark callback 與 Sonic 尾端 feed 退場 | 目前 contextual task 使用的 player `idle` |
| VE | `ProcessText2Speech` 切塊、owned callback 與 guarded feed 退場 | cancellation guard 保護的真實 player `idle` |
| Cerence | Cerence 型別的 `ProcessText2Speech`、owned callback 與 guarded feed 退場 | cancellation guard 保護的真實 player `idle` |
| SAPI5 | WASAPI request／stream ID、`EndStream`、完整 PCM callback 及 feed 退場 | 該 request 最後的 WavePlayer `idle`；legacy 路徑不在本次啟用 |
| eSpeak | native `_speak` 返回、FIFO callback 與 player feed 退場 | 現有 final player idle／callback completion 屏障 |
| RHVoice | 內層 worker、native return、已接受及巢狀 callback/feed 退場 | producer 退場後的最後 player idle |

這張表記錄各 hook 的責任，不把它們宣稱為已獲 SDK 或實機證實的 callback 靜默契約。VE／Cerence 的 cancellation guard 安裝檢查、OneCore 的基本 native 初始化檢查，以及 SAPI5 WASAPI 的 player 檢查仍保留於 profile capability 決策。

## 順序、錯誤與交接

正常路徑是 `accept → submit_native → 確認不再有新 native producer → close admission → 等已進入 producer 退場 → wait_playback_drained → deliver DRAINED`。多個 native 子工作屬同一 segment 時只建立一個 operation，直到所有子工作與最後尾音完成才走 terminal 事件。沒有語音 PCM 的合法 segment 仍須完成其 engine 對應的空工作屏障，不能靠缺少 callback 推論完成。

取消路徑先使 operation 失效，再通知 hook 停止 native 與音訊；已進入的 callback/feed 繼續保有原 operation 身分直至退出。後繼 operation 的 Python 物件可建立或排隊；同一 native/player 的實際提交必須等舊 stop、native return、已接受 producer 和播放器清理退場。取消、終止、失敗與成功競爭時，失效或失敗的 operation 不得發布成功，sink 重入取消時也不得死鎖。

播放器 idle、native stop、callback 解碼、hook 交接或事件排程失敗時，仍有效的原 operation 收到一次 `SEGMENT_FAILED`。已取消的 operation 不再送 terminal 成功或失敗，但 stop／退場錯誤仍鎖存為 core control error。若錯誤使 native/player 是否可重用無法確認，coordinator 將該 core 標為不可安全交接並拒絕後續 native 提交；不能以 timeout 或匿名 NVDA DONE 代替排空證據。恢復方式限於經 hook 證實安全的重新初始化或 driver 重建。

## 驗收與驗證

1. 共用 coordinator 測試刻意阻擋 native return、已進入 callback、巢狀 feed 和 player idle，逐一確認尚未發布 DRAIN、尚未提交後繼 native 工作；釋放後事件只有一個，攜帶原 context。
2. 取消、native stop 失敗、idle 失敗、重複 callback、晚到 index、舊 sink、事件接收端重入 cancel／terminate，以及兩段同 core 交錯都要驗證失敗優先、無舊音訊遷移、無死鎖。
3. 七個 wrapper 各自以實際外層類別搭配可控 native/player 假件驗證其 hooks。語音選擇、LangChange、index、Sonic、pause/resume、取消及舊 `speak` 相容測試繼續通過；SAPI5 WASAPI 的 EndStream、PCM feed 及 idle 順序保留。
4. policy／composition 測試證實七個已啟用 DRAIN 路徑選用新 coordinator；SAPI5 legacy 從首段維持 `LEGACY_DONE`。整合測試證實跨引擎切換仍等前段完成才啟動下一段。
5. 執行全部 add-on 測試、適當的封裝與來源一致性檢查，將結果寫入交付紀錄。Linux fake 邊界測試與 Windows 真實 NVDA、SDK、音效裝置驗證分別記錄；沒有實機結果時不宣稱尾音或 callback 時序已通過認證。

## 後續 handoff

使用者確認本文件後，才依 superpowers writing-plans 建立任務順序及實作驗收 plan。先建立共用 coordinator 的可驗證契約，再逐步遷移七個 wrapper；SAPI5 legacy DRAIN 的可行性與實作另開 change，其完成標準仍需獨立確認真實播放排空訊號。
