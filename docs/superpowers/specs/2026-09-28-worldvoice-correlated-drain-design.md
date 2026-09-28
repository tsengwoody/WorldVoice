# WorldVoice OneCore／Neural 帶 segment 身分的 DRAIN 設計

日期：2026-09-28。

狀態：設計草案，待使用者審閱；尚未實作。書面 spec 確認後撰寫實作 plan。

設計審閱：`gpt-6-astra high` 首輪提出兩項 Neural callback／native 交接問題；修正後第二輪無遺留 findings。SDK 契約依據與 Windows 音訊驗證仍屬後續實作驗收工作。

程式基準：`4951d39`，分支 `test/force-segment-end-index-all-engines`，以及目前工作目錄中使用者新增、尚未追蹤的 `addon/synthDrivers/WorldVoice/driver/Neural/`。本次文件不把 Neural 的 Python、DLL 或其他使用者檔案加入 commit。

## 1. 需求與成功條件

使用者要求先以 OneCore、Neural 實作可關聯到單次 segment 的播放排空通知：driver 確認該段音訊已播完，回報建立工作時取得的 `source_id`、`segment_id`。兩個客製 `SynthDriver` 類別分別定義在外層 `driver/OneCore/__init__.py`、`driver/Neural/__init__.py`，透過繼承現有 driver，並由同檔案的 `Voice.synth_driver_class = SynthDriver` 選用。

採用獨立的 `DRAIN` 完成模式。成功時，scheduler 收到本段有效的 `SEGMENT_DRAINED` 就能完成該段，不需要附加或等待 `WorldVoiceIndexCommand`。原本 NVDA 的一般 index 仍正確轉送；取消後的舊工作不得完成新工作、轉送舊 index，或在新工作開始後重新送入舊音訊。

本案延續現有 segment 基礎建設，不回退至 `cbf7dde`。重用 `PlaybackContext`、來源生命週期、取消 token、事件批次交付、request 完成流程與 IndexLedger 的一般 index 關聯。

使用者已在強制 END_INDEX 的測試版重現 VE → SAPI5 → VE 尾音未完即切段。本案只新增 OneCore／Neural 的排空實作；不能據此宣稱 VE／SAPI5 或其他引擎的切換問題已修復。

## 2. 參考實作與限制

| 位置 | 已確認行為 | 本次需要補上的部分 |
| --- | --- | --- |
| `driver/OneCore/__init__.py` | 目前直接把 `.driver.OneCoreSynthDriver` 匯入為 `SynthDriver` | 在外層建立客製子類別 |
| `driver/OneCore/driver/__init__.py` | 繼承 NVDA OneCore，增加 language property | 保留為客製子類別的基底 |
| `ref/nvda/source/synthDrivers/oneCore.py` | `_callback` 接收 WAV 與 markers、送出 marker 前及後續音訊；`_processQueue` 在佇列空時 `sync()`／`idle()` 後發出整體 done | 讓 native 工作與 context 綁定，在本段最後音訊的播放屏障完成後產生帶身分事件 |
| `ref/nvda/nvdaHelper/localWin10/oneCoreSpeech.cpp` | native callback 接收整次合成結果；初始化時註冊固定 callback，沒有 Python segment ID 參數 | 維持明確的單一 in-flight native 工作歸屬，不能在 callback 到達時猜目前 segment |
| `driver/Neural/driver/__init__.py` | 一次 `speak` 可因 LangChange 產生多個 `SpeakTask`，最後加入 `DoneSpeakingTask`；SpeakTask 在 finally 中 flush Sonic，DoneSpeakingTask 呼叫 `player.idle()` 後發出 done | 同段所有子工作共享 context，最後的完成工作捕捉此 context；將合成錯誤與取消排除於成功 drain |
| `driver/Neural/driver/speechapi/__init__.py` | 同步 `speak_ssml` 送音訊至共用 audio callback；bookmark callback 可替換；`stop_async` 非同步停止 SDK | 保存 native 工作及取消身分，控制 callback 與資源的存活期 |
| `compat/engineAdapter.py` | 已收到 context，但目前只傳 commands／既有 cancellationToken 給 core | 增加明確的 segment 播放入口 |
| `runtime/scheduler.py` | 已檢查非 legacy 事件的 source／segment，已有 drain_seen | 增加 DRAIN-only 完成判斷與完成後 index 邊界 |

`WavePlayer.feed()` 返回不代表音訊播完；`sync()`／`idle()` 或最後音訊區塊的播放完成 callback 才是可使用的播放屏障。屏障因 `stop()` 返回時，必須再次檢查取消身分，不能報成功。

這裡的「排空」以受支援播放器的播放完成契約為準；原始碼檢查和 fake 測試不能取代 Windows／NVDA 音效裝置的實機驗證。NVDA 原始碼版本與播放器 API 的相容性需被記錄，不以方法名稱存在推論所有 NVDA 版本都相容。

## 3. 方案比較

| 方案 | 取捨 | 決策 |
| --- | --- | --- |
| DRAIN：排空完成直接攜帶 context | 不消耗段尾 marker；需要每個 driver 提供可信的工作歸屬與排空屏障 | 本案採用，OneCore／Neural 先行 |
| END_INDEX_AND_DRAIN | 沿用段尾 marker，再等待同段排空；即使排空已知仍可能因 marker 未送達而等待 | 保留既有模式與回歸測試，不作為這兩個 wrapper 的新預設 |
| 收到匿名 done 時補上目前 segment ID | 修改少，但取消、晚到回呼或同 core 重用時無法證明 done 的來源段落 | 不採用 |

## 4. 完成契約與 index 責任

完成模式總共有四種，保留 legacy 相容路徑：

| 模式 | 成功完成條件 | 是否追加段尾 marker |
| --- | --- | --- |
| LEGACY_DONE | 現有來源符合的匿名 DONE | 否 |
| END_INDEX | 本段 SEGMENT_END | 是 |
| END_INDEX_AND_DRAIN | 本段 SEGMENT_END 與 SEGMENT_DRAINED 都到齊，順序不限 | 是 |
| DRAIN | 本段 SEGMENT_DRAINED | 否 |

錯誤、取消與關閉繼續優先於成功；DRAIN 不接受匿名 DONE 或單獨 SEGMENT_END 作為成功替代。

本案 DRAIN 仍使用 `IndexLedger` 重編及還原原始 `IndexCommand`，因此其 `CompletionContract` 仍宣告正整數 `IndexRange`。先沿用使用者指定的測試 wire 範圍 **1..9999，含兩端**。這個範圍限制 wire bookmark，與 source／segment ID 無關，也不代表已驗證所有引擎的 native 整數範圍。

`IndexAllocation.end_index` 對 DRAIN 可以為 None：僅配置原有 index 所需的數量，不保留未送出的尾端值。沒有原始 index 的 DRAIN segment 不消耗任何 wire index，仍必須登記 segment 以驗證完成通知。wire 值在同一 live source 中不重用；有一般 index 的長時間使用仍可能耗盡範圍，耗盡時在送入引擎前使整段失敗。

`WorldVoiceIndexCommand` 保留供兩種 marker 模式使用。外來語音序列仍不能自行注入這個內部 command。不能因為 OneCore／Neural 改成 DRAIN，就移除其他模式需要的 codec／ledger。

## 5. 身分、介面與事件流

沿用不可變的 `PlaybackContext(source_id, segment_id)`：source 是 session 開啟資源的身分，segment 是單次播放工作身分。取消 generation／token 用來作廢工作，不取代這兩個識別值。`activate()` 繼續用 `(source_id, voice_key, revision)`，不因段落切換而失去快取。

新增 wrapper 專用入口，設計介面如下；一般 legacy `speak` 仍走既有介面：

```python
speak_segment(commands, token, *, context: PlaybackContext, on_event) -> None
```

`on_event` 是 adapter／bridge 為這次綁定建立的內部事件接收端；接受 `SEGMENT_DRAINED`／`SEGMENT_FAILED` 及其原始 context。它捕捉實際 core 與 binding generation，不在回呼當下從 scheduler 的 current task 取得 ID。core 的 segment 入口、能力宣告與事件接收端都必須在資源對外可用前準備完成。

事件流程：

```text
scheduler 建立 PlaybackContext
  → session／adapter 傳入 commands、token、context、綁定事件接收端
  → 外層 SynthDriver 建立保留 context 的播放工作
  → 合成所有子工作並送完尾端音訊
  → 播放屏障完成，重新檢查工作尚有效且合成成功
  → SEGMENT_DRAINED(source_id, segment_id)
  → bridge 驗證 core／binding／context，ledger 整理一般 index
  → scheduler 依 DRAIN 完成本段
  → 全部段落與 pause 完成後，WorldVoice 對 NVDA 發出一次 request done
```

一般 index 仍經 NVDA `synthIndexReached` 和 wire ledger 解碼。drain／failure 經 WorldVoice 的專用入口傳遞，不修改 NVDA 公開通知的參數。native done 可以繼續存在，但在 DRAIN 模式不推進 scheduler。

成功 drain 交付時，ledger 先依原始命令順序補交尚未交付的原始 index，再於同一批次交付 SEGMENT_DRAINED。這延續既有 terminal index 補交前置 index 的語義，處理播放已結束但 Python index 回呼晚到的情況。失敗、取消不能補交。原始值去重規則保持不變。

批次供應者在 scheduler 的既有交付序列內進行 ledger 解碼與 binding generation 驗證。若 index 的外部 handler 重入取消或 unbind，後續 drain 不得完成失效工作。不能在 bridge／ledger 的內部狀態鎖下呼叫外部事件 handler。

DRAIN 模式成功 drain 後，晚到 index／重複 drain 均丟棄。END_INDEX_AND_DRAIN 若 drain 先到，必須保留 terminal marker 的映射直到真實 END_INDEX 到達；若 END_INDEX 先到，仍要保留足夠的 segment 資料接受稍後的 drain。不得為了共用清理程式而破壞任何一種順序。

## 6. OneCore 外層子類別

在 `driver/OneCore/__init__.py` 匯入 `.driver.OneCoreSynthDriver` 為基底別名，再定義客製 `class SynthDriver(BaseSynthDriver)`，指定至 `Voice.synth_driver_class`。保留基底的 language 支援與 NVDA 的語音／SSML 設定行為。

子類別覆寫必要的佇列／callback 接點，使每個實際提交至 `ocSpeech_speak` 的文字工作綁定 context、token 與原始事件接收端。參數設定 tuple 不當成語音工作；清除已排隊的文字不能使工作與 context 錯位。

同一 native core 一次只有一個 in-flight 合成工作。callback 歸屬來自提交時留下的工作記錄；cancel 後仍保留此 native 工作的已取消記錄，直到其 callback 被消耗或 native 資源確實終止。新工作不能提前覆寫它。callback 一進入就取得自己的工作記錄，其後的等待與通知使用該記錄。

該段所有音訊（包含最後 marker 後面的尾端資料）送入播放器後，在 OneCore 的背景處理流程建立播放屏障。建議先採最後音訊送入後的 `sync()`；也允許等價、經測試的最後區塊 onDone。實作不在 NVDA 主執行緒阻塞等待，不把父類別 `_processQueue()` 整體返回當成逐段排空的證據。

失敗回呼 `len == 0`、WAV／marker 處理例外、可觀察到的播放器錯誤都產生本段 SEGMENT_FAILED。保留既有錯誤紀錄與必要的資源清理；失敗處理繼續處理佇列時不可把失敗工作轉成 drain。父類別內部自動處理下一項前，需先完成舊工作的歸屬與終止處理。

## 7. Neural 外層子類別

在 `driver/Neural/__init__.py` 匯入 `.driver.SynthDriver` 為基底別名，定義客製 `SynthDriver`，並由 `Voice.synth_driver_class` 選用。客製 task／callback helper 可以放在外層模組或 WorldVoice 自有 helper 模組。保留 `driver/Neural/driver/` 原始碼及 DLL；不使用修改基底 module 全域 class 的 monkey patch。

外層子類別使用自己的初始化接點，建立 WorldVoice 自有的 AudioCallback，並在建立各個 SpeechSynthesizer／StreamAudioConfig 時就把它交給 native stream。由於基底初始化直接建立 callback，允許在外層覆寫必要的初始化流程，重用基底的模型發現、語音與設定類別。不得先讓基底 stream 綁住原 callback，再只替換 Python 屬性。

每次 `speak_segment` 建立一個 segment 工作。LangChange 造成多個 SpeakTask 時，每個子工作都捕捉同一份 context／取消身分，最後只安排一次該 segment 的完成工作。保存參數 snapshot，避免稍後的 rate／voice 設定污染已排程的子工作。

完成順序必須是：所有子工作合成成功 → 每次合成的 AudioCallback.finish() 已完成 Sonic flush 且尾端資料已送入 → 最後完成工作等待 player.idle()／等價屏障 → 檢查尚有效 → 報告一次 drain。

SDK 結果不是 `ResultReason_SynthesizingAudioComplete`、子工作丟出例外或可觀察到的 audio／Sonic 失敗時，segment 失敗，不能讓最後 DoneSpeakingTask 再把它算成成功。不能只依賴基底 TaskThread 記錄例外，否則 scheduler 可能永遠等不到 failure。

自有 AudioCallback 在處理／flush 例外時，把第一次錯誤鎖存在進入 callback 時捕捉的工作記錄上，關閉該工作的後續音訊 admission，並安全地返回 CFFI 邊界；完成工作必須檢查此失敗狀態。不得只呼叫會吞掉例外的基底 AudioCallback 方法，再以「沒有 exception」判斷成功。尚未開始合成前，Sonic 初始化不可用可以沿用 native SSML rate 的既有 fallback；已開始音訊處理後的 Sonic 處理／flush 失敗不能如此隱藏。

取消需作用於該段實際正在使用的 native synth；LangChange 的 active synth 不一定等於 `self._voice._synth`。取消尚未執行的子工作與完成工作，正在執行的工作保存舊 context，之後即使 idle 因 stop 返回也不送成功事件。

Neural 的 SDK audio callback 是共用資源，沒有 utterance ID。本案採用每個 native stream／synth 的 admission gate，加上序列化的 SDK 工作生命週期：native 工作開始前綁定不可變工作記錄，callback 進入 gate 時取得該記錄及 in-flight 計數，退出時釋放計數。已取得記錄的 callback 後續不得重讀其他工作的 context。

正常完成的交接屏障必須同時滿足：同步 `speak_ssml` 已返回、受支援 SDK 的契約保證此工作不會再啟動新的 audio／bookmark callback，以及已進入的 callback／feed 全部退出。只有之後才可清理該工作的 callback 身分、完成其 Sonic flush 並交接下一 native 工作。同一 segment 的語言子工作可以繼續送音訊，整段排空在最後完成工作等待；不同 segment 則要等本段 drain 才啟動。不能僅以 callback 計數暫時為零，或 Python task 已返回，推論 native 回呼已全部停止。

取消時先關閉舊 gate、標記取消並 stop 播放器以解除 feed／drain 等待，再對保存的 active native synth 發出 native stop。外層 helper 必須保留 stop operation handle，於背景流程等待停止完成（使用所支援 SDK 的 stop wait API；不能直接使用現有丟棄 handle 的 `stop_async()` 當成停止屏障），並等舊的同步合成呼叫及已進入的 callback／feed 全部退出。此等待期間新工作可以排隊，但不能重新開啟舊音訊通路。native stop 的完成本身不产生成功 drain。

bookmark 的 CFFI handle 及 audio callback 物件由工作／stream 資源持有到上述屏障完成，避免替換回呼時提前釋放舊 handle。取消、等待與 callback 退出不持有彼此需要的鎖。各語音 native synth 共用的播放器／Sonic 也遵守同一個序列化交接點。

上述「native 工作結束後不再產生新 callback」是 SDK profile 啟用 DRAIN 的前置契約，必須在實作驗證中記錄支援版本及其契約依據；本機 CFFI 宣告包含 stop wait API，僅能證明可呼叫該 API，不能證明回呼生命週期。若無法建立此契約，該 profile 在播放前選 LEGACY_DONE，不能先重新開啟 gate，再把晚到舊音訊貼成新段。相關能力驗證列為 Neural 任務的前置步驟，不以測試結果猜測任意 SDK 版本都符合。

## 8. 取消、失敗與執行緒契約

每段的有效狀態可視為 admitted → synthesizing → draining → completed，另有 cancelled／failed。成功與失敗最多通知一次；取消後不發成功，舊事件可以到達邊界但必須被丟棄。來源 unbind／close 時一併關閉該 binding 的事件入口。

播放屏障前後都檢查工作狀態。stop／cancel 必須能喚醒或解除背景播放等待；不要持有 cancel 所需的狀態鎖跨越阻塞 feed、sync、idle、native stop／terminate 或對外通知。

取消與 feed admission 之間需要有可證明的順序：cancel 返回後，舊工作不可再次向已被新工作接管的播放器送音訊。僅在 feed 前讀取一次旗標並不足以處理檢查後被取消的競態。具體實作要以測試建立取消、in-flight feed 退出和下一段 admission 的屏障，且避免 stop 與 feed 互鎖。

這些保護可以抽成 WorldVoice 的小型共用 helper，但 helper 僅負責工作生命週期／回呼歸屬，OneCore 和 Neural 仍各自管理 native 佇列及播放器完成方式。不可假定 VE 的 `_SilenceGate`／`_GuardedPlayer` 能不經檢查就套用兩個不同的 callback 流程。

空序列、只有 index、只有 break 等情況都必須有明確結果：成功且沒有音訊可等待時，可以在該工作的已知結束點完成；native 合成失敗則回報 failure。不可為了空段另外附加假的 END_INDEX。

## 9. Policy、相容性與範圍

OneCore／Neural 只有在實際載入客製 subclass，且 segment 入口、事件連接及底層相容性檢查完成後，才能選 DRAIN。不能只因 engine 字串相同就宣告具備 drain 能力。完成契約在資源開始播放前固定。

本測試分支中，成功啟用的 OneCore DRAIN 必須優先於 `_TEST_ONLY_FORCE_END_INDEX_ENGINES`；Neural 也明確選用 DRAIN。SAPI5／Espeak／VE／Cerence／RHVoice 仍保留本分支既有的實驗 END_INDEX 設定，文件需清楚標示其限制，避免把混用測試誤認為所有引擎均已等尾音。

兩個目標 wrapper 不支援所需 NVDA／SDK 流程時，於啟動選擇明確的 LEGACY_DONE 相容路徑並記錄原因；不得落入本分支的強制 END_INDEX 規則而掩蓋 DRAIN 未啟用，也不得在單段等待期間改用匿名 DONE 解套。相容路徑本身不提供逐段排空保證。

能力檢查需配合明確測試過的 adapter API／版本範圍與回歸測試；僅 hasattr 檢查不是播放完成證據。新方案的測試啟用與 Windows 實機驗證記錄分開，不把 wrapper 的 capability 或模擬測試當成 `_VERIFIED_CONTRACTS` 的硬體驗證資料。

不修改 NVDA source 或 native DLL、不更改 source_id 的 activation 用途、不為每個 segment 重建合成器、不新增 UI 開關或固定延遲猜測機制。

## 10. 驗收與測試矩陣

1. **模式**：DRAIN 只靠相符的 SEGMENT_DRAINED 完成；END_INDEX／匿名 DONE 不完成它。AND 模式保留兩種事件順序；legacy 與原 END_INDEX 回歸通過。
2. **編碼**：DRAIN 不附加 WorldVoiceIndexCommand；一般 index 仍重編、依序還原、去重；沒有 index 不消耗 wire ID；範圍兩端及耗盡行為符合契約。
3. **歸屬**：錯誤 source／segment、重複 drain、cancel 後舊 callback、unbind/rebind 後舊事件都無法推進新段。context 必須是建立 native 工作時的原值。
4. **交付順序**：未交付一般 index 與 drain 同批次且 index 在前；index handler 重入取消時不交付成功；完成後晚到 index 丟棄。既有 event batch 重入修正持續有效。
5. **OneCore**：marker 已到但尾端音訊尚未完成時不切段；sync 完成才 drain；len=0 為 failure；參數 tuple 與多次 speak 不造成 context 錯位；cancel 舊 native callback 後的新工作使用新 context。
6. **Neural**：同段多語言子工作只有一次最終 drain；Sonic 尾端包含在屏障前；SDK 非成功結果／task 例外不被 DoneSpeakingTask 改算成功；取消對準實際 active native synth。測試 native stream 實際持有自有 callback，並注入處理／flush 例外驗證失敗鎖存，另驗證初始化 fallback 不被誤判為播放失敗。
7. **取消競態**：在送入音訊前、feed 阻塞中、drain 阻塞中及 drain 交付前取消；stop 能解除等待，新工作開始後不再收到舊音訊。pause/resume 與 terminate 沒有互鎖。
8. **整合**：OneCore／Neural 的 Voice 使用外層客製 subclass；DRAIN capability 及 binding 在資源發布前完成；不相容時明確回退 legacy；其他引擎政策符合本節範圍。
9. **設定快取**：同 source／voice／revision 的兩段只 apply 一次但有兩個 context；voice／revision 改變按原邏輯套用，segment ID 不加入 activation key。
10. **Windows 實機**：記錄 NVDA 版本、音訊模式、輸出装置與 Neural SDK／語音資料版本。測試兩引擎各自短長語音、OneCore → Neural → OneCore、反向切換、rateBoost、快速 cancel→speak、pause/resume、只有 index／break 的序列。用時間戳記錄 context、合成結束、播放屏障完成、drain 交付及下一段開始，並聽測尾音重疊／截斷。
11. **Native 交接**：fake 保留 audio／bookmark callback 跨越取消；native stop 尚未完成、同步合成尚未退出或 callback 仍在執行時，新工作都不能開啟音訊 gate。舊 bookmark handle 在退出前保持有效，舊 callback 保存舊 context。沒有已確認的 SDK 回呼結束契約時，profile 不能選 DRAIN。

單元測試使用可控制合成回呼與播放器屏障的 fake，測試實際 wrapper 的 Python 方法，不以替換整個 wrapper 的假實作作為驗收。Linux 可驗證協定／競態及包裝內容；實際音訊時序的結論保留給 Windows 驗證。

## 11. 預期變更位置與交付方式

- `runtime/models.py`、`runtime/scheduler.py`、`runtime/session.py`：DRAIN 模式、能力介面、完成條件與狀態檢查。
- `compat/engineAdapter.py`、`voiceManager.py`、`nvdaEventBridge.py`：context／事件接收端連接、bind/unbind 所有權與排空事件輸入。
- `compat/indexCodec.py`、`indexLedger.py`：不追加尾標記的編碼、一般 index 的段落映射、成功 drain 的原子事件批次。
- `compat/completionPolicies.py` 與組裝處：兩個已連接 wrapper 的 DRAIN 政策及不相容時的明確 fallback。
- `driver/OneCore/__init__.py`、`driver/Neural/__init__.py` 及必要的 WorldVoice helper：使用者指定的外層 subclass 與具 context 的工作／排空處理。
- 對應 runtime、bridge、ledger、adapter、wrapper 測試；測試版說明及實機驗證紀錄。

後續 plan 依序拆分契約與 ledger、bridge／adapter、OneCore、Neural、policy／整合與驗證。實作沿用使用者要求的 Subagent-Driven：實作者 `gpt-6-sol high`，每項任務獨立 reviewer `gpt-6-astra high`；main agent 審核結果，問題交回修正並重新 review。

最終更新 `docs/superpowers/finish_task.md`，包含本案新增 commit list、測試與封裝結果、實機已驗證及尚未驗證項目。完成範圍不得涵蓋尚未新增 drain 的引擎。
