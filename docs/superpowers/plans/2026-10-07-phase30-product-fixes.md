# 階段 30 實作計畫：產品問題修正

Spec：`docs/superpowers/specs/2026-10-07-phase30-product-fixes-design.md`。分支 `phase30-product-fixes`，基準 `100e3a6`。

每項：先寫會在舊程式失敗的測試，再修，跑相關測試與全套，commit。

1. `disable_log_record` 的提示移出 `if`（`test_global_plugin_menu.py`）。
2. chunker 以純文字長度計算、硬切與空白切都不拆開字母與組合符號、尾端 escape 併入最後一段（`test_text_preprocessing.py`；另以 Hypothesis 臨時 fuzz 一萬例驗證不變式，不加進 repo）。
3. `_run_logged` 的記錄寫入改走 `_LogWriter`，攔下 `OSError`、一次停機只記錄一次（`test_pipeline_stages.py`）。
4. 刪除 `SpeechRoleSettingsPanel.voiceInstance`。
6. `deduplicate_language_command(start_language=)`，數字語言 stage 傳入當下語言（`test_pipeline_passthrough.py`）。
7. 驗證：全套、逐檔、ruff、`pytest --cov`、壓力測試（3 個 worker）；Opus 5.5 審查；fast-forward 合併。
