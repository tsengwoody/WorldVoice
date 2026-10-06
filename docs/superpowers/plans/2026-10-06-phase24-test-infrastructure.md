# 階段 24 實作計畫：測試基礎設施——統一模組載入

Spec：`docs/superpowers/specs/2026-10-06-phase24-test-infrastructure-design.md`。分支 `phase24-test-infrastructure`，基準 `e153aec`。

每個 commit：收集清單不變（守門測試新增者除外）、全套通過、逐檔單獨執行通過、ruff 乾淨。

1. `tests/addon_loader.py`；依群組改寫：runtime harness → drain harness → pipeline／settings／plugin → UI 與引擎定義（`load_definitions`）→ 主驅動；S102 縮小；守門 `spec_from_file_location` 只在 loader。
2. 共用 helper 移到 harness 模組（`pipeline_harness`、`worldvoice_harness`、`sapi5_drain_harness`、`legacy_adapter_harness`、`core_archive_harness`、`worldvoice_cancel_wrapper_harness`）；`composition` 移入 conftest；守門：沒有測試模組互相 import。
3. `nvda_stubs.worldvoice_conf()`：以 ast 讀 add-on confspec 來源產生預設值；在手寫且缺鍵處採用。
4. Fable 審查，fast-forward 合併。
