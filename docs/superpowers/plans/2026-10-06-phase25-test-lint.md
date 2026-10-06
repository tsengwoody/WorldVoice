# 階段 25 實作計畫：測試程式的 lint 與格式

Spec：`docs/superpowers/specs/2026-10-06-phase25-test-lint-design.md`。分支 `phase25-test-lint`，基準 `f7bb32b`。

每個 commit 前：全套通過、收集清單（node id）與開工前完全相同。

1. 共用 fixture 移入 `tests/conftest.py`（`rt`、`compat`、`nvda_commands`、`module`→`session_module`、`snap`），刪除各檔的 fixture import。
2. 一次性格式化：`add-trailing-comma` 與 `ruff format` 交替到穩定；逐檔比對 AST 確認只有格式改變。
3. 清除 ruff 項目：I001、RUF059、F401、SIM117、PIE807、PLR0402 自動修；BLE001 加 noqa 並寫錯誤去處；S102 以 per-file-ignores；其餘逐一修。每類修完跑全套，並逐檔單獨執行測試檔確認 import 排序沒有副作用。
4. `.pre-commit-config.yaml` 五個 hook 的範圍改為 `^(addon|tests)/`；`test_ruff_reports_nothing` 檢查 `addon` 與 `tests`。
5. Fable 審查，fast-forward 合併。
