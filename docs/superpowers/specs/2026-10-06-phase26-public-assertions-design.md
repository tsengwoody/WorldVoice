# 階段 26：斷言改以公開行為為準，等待統一

日期：2026-10-06。
基準：`master`（`ffdbbb5`，階段 27 合併完成）。分支：`phase26-public-assertions`。
狀態：使用者要求依序完成階段 23～28，自動流程執行；審查使用 Opus 5.5。

對應 repo 根目錄 `refactor-test.md`（不入版控）的階段 26，含階段 27 審查補充的等待統一。

## 現況

### 寫死的正向等待

階段 23 只處理了「短逾時」與手寫輪詢；舊的執行緒測試仍寫死約 630 處正向等待：`.wait(1)` 324、`.wait(2)` 139、`.wait(3)` 68、`.join(1)` 48、`.join(2)` 31、`.join(3)` 12，以及 `Condition.wait_for(pred, n)`。集中在 vocalizer drain 89、rhvoice drain 76、onecore drain 73、sapi5 drain 53、segment lifecycle 49、request manager 42、segment host 40、scheduler 38。階段 27 審查在 8 個行程、記憶體吃緊的負載下，重現到這些 1～2 秒的等待逾時。

### 讀私有狀態的斷言

約 230 處直接讀 add-on 物件的私有屬性（`_pending`、`_operations`、`_lifecycle`、`_segmentHost`、`_bgQueue`、`_real_player`、`_terminationDone`、`_stopGate`、`_instanceCache`…）：vocalizer drain 68、cancel wrappers 41、onecore drain 35、segment host 16、sapi5 drain 16、rhvoice drain 12、pipeline settings 9、espeak drain 9 等。內部改名或重構時，這些測試即使行為沒變也會壞（階段 21、22 已實際發生）。

## 設計

### 1. 等待統一（先做，機械性）

- 正向等待（回傳值被 `assert`，或之後立即斷言對方已完成；`join` 後斷言 `not is_alive()`）的寫死秒數改為 `waiting.WAIT_TIMEOUT`。`Condition.wait_for(pred, n)` 的正向用法同樣改。
- 不改：負向檢查（`assert not ....wait(...)`、`is False`）、`finally` 中只為清理的 `join`／`wait`（改了無害但沒必要；若與正向等待混在同一行則一起改）、刻意測逾時的情境（例如被測程式自己的逾時參數）。
- 逐檔改寫，一組檔案一個 commit；每個 commit 全套通過。

### 2. 私有狀態斷言

逐一分類：

1. **可由公開行為觀察**：事件序列、DONE／index 通知、下一段語音能否開始、`wait_idle()`／`wait_settled()` 的回傳、公開 property。→ 改寫成公開行為的斷言。
2. **確實需要看內部**：資源洩漏類（例如「`_pending` 不累積」「operation 被移出」「player 被關閉」），沒有公開觀察點。→ 集中成 harness 的具名查詢函式（例如 `pending_records(host)`、`player_closes(core)`、`lifecycle_operations(host)`），放在對應 harness；內部改名時只改一處。
3. **只是附帶的存在性或型別檢查**（例如 `isinstance(core._segmentHost, SegmentHost)`、`operation in lifecycle._operations` 這類與測試意圖無關的檢查）→ 刪除。
4. **測試設置需要碰內部**（monkeypatch 私有方法製造故障、注入假 player）不是斷言，不在本階段範圍。

原則：不改變每個測試的情境與意圖；改寫後該測試仍會在原本要抓的錯誤上失敗。不確定時歸入第 2 類。

## 驗證

- 每個 commit：全套通過、收集清單不變、`ruff check/format` 乾淨。
- 完成後：逐檔單獨執行；壓力測試（開 coverage，4 個 worker × 6 輪全套）0 失敗；另以 8 個行程的極端負載跑 2 輪全套，記錄結果。
- 統計：寫死正向等待與私有狀態斷言的前後數量；第 2 類保留清單。
