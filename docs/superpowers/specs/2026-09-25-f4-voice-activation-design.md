# F4：語音設定於下一段開始時生效

## 目的與已確認的行為

WorldVoice 目前在建立 `Voice`、載入設定或操作設定介面時，可能直接改寫引擎共用的 `core`。這些動作可與另一段語音的播放重疊，造成播放狀態在 TaskManager 排程之外改變。

使用者已確認：語速、音調、音量、變體、waitfactor 等設定若在播放期間變更，**新值於下一段語音開始時生效**。同一 Voice 連續播放兩段時亦同。取消設定編輯後，下一段應使用還原後的值。取消目前語音與暫停／恢復仍須即時處理。

## 選擇的架構

保留每個引擎一個完整 `core`，由該引擎的 `EngineSession` 管理其目前套用的 Voice 與設定版本。每個 `Voice` 保有自己的待生效設定及執行期間的版本號。`Voice` 建構、設定載入與 UI 編輯只改變待生效設定；TaskManager 的語音工作執行緒在每段開始時，透過 Session 套用設定並呼叫 `core.speak()`。

不為每個 Voice 建立完整 `core`。VE／Cerence 的 `core` 已在內部按 Voice 快取原生實例，並持有播放器與回呼；原生函式庫初始化狀態也是模組全域。若為每個 Voice 複製完整 `core`，須額外解決初始化、終止及資源所有權，且仍不能阻止 UI 直接修改正在播放 Voice 的 `core`。

Session 是單一引擎 `core` 的設定與播放協調者。實作可沿用現有 `Voice.core` 作為唯讀相容入口；設定寫入須集中到 Session 在 worker 內執行。`VoiceManager` 負責建立及關閉每引擎的 Session，並將對應 Session 交給 Voice。TaskManager 繼續序列執行語音工作，並保留目前以 `core` 身分比對完成事件及執行取消的行為。

## 設定版本與快照

每個 Voice 實例在完成初始設定載入後，以 `revision = 0` 作為基準。設定檔不保存此版本。Voice 的設定寫入入口只在值實際變更時遞增版本；設定介面的預覽、NVDA 設定 setter、重新載入設定及取消編輯所造成的值變動皆遵守此規則。取消時版本只會增加，不會倒退。多個欄位在同一次編輯中各自增加版本是允許的，因為 Session 只需辨識最後的快照。

Voice 以同一把鎖保護待生效設定與版本。worker 在每段語音開始時，以一次加鎖讀取不可變的設定快照，包含 Voice ID、引擎專用參數、language 與 revision。快照讀取後才發生的編輯屬於下一段；編輯不直接寫入 `core`。

Session 記錄上次**成功套用**的 `(core 身分／世代, Voice ID, revision)`：

1. 同一 `core`、同一 Voice、同一版本：不呼叫設定 setter，直接播放。
2. 同一 Voice、版本不同：套用新快照後播放。
3. Voice 不同，或 `core` 重建：完整套用該 Voice 的快照後播放，即使該 Voice 的版本未變。

每段固定成本為取得一次快照與比較記錄值；不重新讀設定檔，也不逐項比對 `core` 的參數。若 Session 在套用設定期間發生錯誤，清除已套用記錄，因為 `core` 可能已部分改變。

## 語音工作流程與引擎差異

TaskManager 的 speech task 是「下一段開始」的邊界。worker 取快照、檢查 Session 記錄、必要時套用參數、再呼叫 `core.speak()`。目前 `TaskManager._run_one()` 與 `Voice.speak()` 閉包都會呼叫 `active()`；改造後只保留 worker 的一次啟用流程。break task 不觸發設定套用。

通用參數依引擎宣告的 supported settings 套用。VE／Cerence 的 `variant` 與 `waitfactor` 必須從目前會直接寫原生實例的 Voice setter 移到 Session 的引擎專用套用步驟；UI 選擇變體只更新待生效值。OneCore 的 `language` 也在每次需要啟用該 Voice 時套用，避免切回已快取 Voice 時沿用上一個 Voice 的語言。引擎專用參數的套用順序應先選 Voice，再設定其參數；原生實例屬於該 Voice 的參數應作用於正確的實例。

語音清單與變體清單屬於中繼資料讀取，可以維持現有 UI 功能；此讀取路徑不得設定目前播放 Voice 的參數。若讀取會建立原生語音實例，該實例不得改變目前啟用的 Voice 或其播放參數。

## 取消、失敗及生命週期

TaskManager 繼續直接取消目前的 `core`，並直接對目前語音執行暫停／恢復；這些控制操作不等待下一段。已取消的 task 在套用設定前或呼叫 `speak()` 前，沿用既有 token 檢查。取消後已成功套用的 Session 記錄可保留；下段仍會按 Voice ID 與版本重新判斷。

若設定套用失敗，該段不得用舊的 `core` 狀態繼續播放；讓目前 speech task 走既有錯誤／完成流程，記錄錯誤，並清除已套用記錄，讓後續段落完整重試。引擎關閉或重新建立時，Session 也清除已套用記錄。Session 的關閉順序沿用 VoiceManager 與 TaskManager 現有生命週期，確保不在 worker 使用 `core` 時終止它。

## 驗收情境

- A 正在播放時建立或預覽 B，不改變 A 的 Voice ID、參數或原生播放狀態；B 開始時才套用 B 的設定。
- 同一 Voice 的兩段之間修改設定，第一段維持開始時的快照，第二段使用新值。
- 同一 Voice 連續播放且設定未變時，不重複呼叫引擎設定 setter。
- A → B → A 時，即使 A 的版本未變，切回 A 仍重新套用 A 的設定。
- 編輯後按取消，下一段使用還原值；設定版本不倒退。
- `core` 重建後，下一段即使 Voice 與版本看似相同，也完整套用設定。
- VE／Cerence 的變體與 waitfactor、OneCore 的 language 遵守相同生效邊界；取消及暫停／恢復保持即時。
- 套用參數失敗時，不以舊設定播放該段，後續段落可重試。
