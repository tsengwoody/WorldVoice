# 階段 23 實作計畫：並發測試的穩定性

Spec：`docs/superpowers/specs/2026-10-06-phase23-test-stability-design.md`。分支 `phase23-test-stability`，基準 `c9952c1`。

## 任務 1：基準壓力測試

開 coverage、4 個 worker 平行、各跑 8 輪全套（共 32 輪）。結果：31 輪通過、1 輪失敗。之後針對可疑測試在負載下各重複 160 次，確認兩個偶發，都是 D 類（另一執行緒完成前就斷言）：

- `test_vocalizer_segment_drain.py::test_done_listener_can_terminate_without_deadlocking_speech[Cerence]`：`closes == 0`。重入的 terminate 交給 "WorldVoice VE close" 執行緒關 player，`settle_worker` 不等它。
- `test_vocalizer_segment_drain.py::test_cancel_during_contextual_final_idle_releases_waiting_ordinary[VE]`（Cerence 已知）：`_pending` 由 delivery 執行緒的 `_forget_operation` 清，晚於 operation 移出 `_operations`。

## 任務 2：`tests/waiting.py`

`eventually`、`stays_unset`、`quiet_period`、`WAIT_TIMEOUT = 3.0`、`QUIET_PERIOD = 0.05`。

## 任務 3：改寫固定等待

依 spec 的 A／B／C／D 規則逐檔改寫；各檔自寫的等待 helper 委派給 `eventually` 或刪除；不改縮排。

## 任務 4：驗證

全套通過、收集數 1491；壓力測試（同任務 1 設定）0 失敗；Fable 審查；fast-forward 合併。
