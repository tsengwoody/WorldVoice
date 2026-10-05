# 階段 17：收尾

日期：2026-10-05。
基準：`master`（`47700b4`）。分支：`phase17-cleanup`。
狀態：使用者核准開始，並決定 #26 的政策：一般語音開不了音訊裝置時只讓這一句失敗，不鎖住整個 OneCore 引擎。依自動流程執行（spec → plan → 實作 → Fable review）。

本 spec 的範圍與逐項理由見 repo 根目錄的 [`refactor-cleanup.md`](../../../refactor-cleanup.md) §3。以下只記錄每個 task 的需求與成功條件。項目編號與該文件相同。

## 需求

### Task A：使用者可感知

- **#26**：OneCore `_speakRecord` 的 `player.open()` 失敗時：
  - 一般語音（`record.operation is None`）只對這一句記錄錯誤並釋放 worker，**不呼叫 `_failSegmentControl`**，下一句照常送出。這比照 NVDA 原生 OneCore（下一句重試）。
  - segment 的 open 失敗維持現行的鎖定。
  - 一般語音 `ocSpeech_speak` 失敗時的現行鎖定不在本項範圍內，不改。
- **#49**：VE／Cerence `_strip_bytes_repr` 只去掉開頭的 `b'` 與結尾的 `'`（`text[2:-1]`），不再用 `.strip` 剝掉字元集合。兩檔相同。

### Task B：runtime 潛在問題

- **#20**：`_segmentLifecycle._deliver` 每輪迴圈也重設 `error`。
- **#22**：`SegmentHost.abandon` 改變 `_current` 後 `notify_all()`。
- **#28**：`SegmentLifecycle.run` 在等待資源的迴圈結束後，再檢查一次 `_retired`。
- **#39**：`SegmentHost.__init__` 拒絕 `barriers` 為空的 strategy（`ValueError`）。
- **#44**：SAPI5 segment feed 只讀一次 `host.current()`，以同一筆記錄取得 consumer 與 feed。
- **#18**：刪除 `SegmentHost._invalidate` 的死分支。
- **#65**：`RolePanelPresenter.close()` 清除 `engine_consistency.preview`。
- **#57**：`Teardown.add` 在 `run()` 之後呼叫時拋 `RuntimeError`。

### Task C：測試缺口

依 `refactor-cleanup.md` §3 Task C，共 14 項：#2、#8、#32、#34、#36、#40、#42、#46、#53、#54、#58、#67、#68、#71。

### Task D：註解與文字

依 §3 Task D，共 7 項：#23、#14、#50、#6、#56、#63、#16。#50 同時擴充 hygiene 守門的理由表，加入組合條目。

### Task E：小型整理

依 §3 Task E，共 6 項：#45、#55、#59、#62、#64、#70。

## 成功條件

1. 完整測試全部通過；lint gate 與 `ruff format --check addon` 通過。
2. Task A、B 每項都有先失敗、後通過的測試。#18 是死碼刪除，以既有測試保證行為不變。
3. VE／Cerence 漂移測試的允許清單不變。
4. `driver/<Engine>/driver/`、`driver/sonic` 無變動。
5. 除 #26 外，使用者可見行為不變。

## 不在範圍內

`refactor-cleanup.md` §4 的 20 項。
