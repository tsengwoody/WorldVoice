# 階段 28 實作計畫：測試的執行速度與資源

Spec：`docs/superpowers/specs/2026-10-06-phase28-test-speed-design.md`。分支 `phase28-test-speed`，基準 `10c5e1b`。

1. `pyproject.toml` 加 `[tool.coverage]`（`core = "ctrace"`、branch、source、omit vendored）；量測 `pytest --cov` 的峰值記憶體與 TOTAL。
2. `runtime/segmentHost.py` 的 delivery join 上限改為模組常數 `DELIVERY_JOIN_TIMEOUT = 1.0`；兩個刻意卡住 sink 的測試 monkeypatch 為 0.05 秒。
3. `test_hygiene_guards.py` 兩個掃描 tests 的守門共用 `functools.cache` 的 parse 結果。
4. 驗證：全套、ruff、壓力測試（3 個 worker × 3 輪，記錄最低可用記憶體）；Opus 5.5 審查；fast-forward 合併。
