# 階段 28：測試的執行速度與資源

日期：2026-10-06。
基準：`master`（`10c5e1b`，階段 26 合併完成）。分支：`phase28-test-speed`。
狀態：使用者要求依序完成階段 23～28，自動流程執行；審查使用 Opus 5.5。

對應 repo 根目錄 `refactor-test.md`（不入版控）的階段 28。使用者已決定不加入 `pytest-xdist`（2026-10-06），所以平行化不在範圍。

## 現況（實測）

- 全套 1691 個測試約 45 秒；`--durations` 加總：setup 21.6 秒、call 17.5 秒、teardown ≈ 0。
- **setup**：每個測試 10～35 ms，花在重新載入 add-on 模組（每個測試拿到全新的模組物件，見階段 24 的隔離設計）。bytecode 快取有在用（`__pycache__` 存在、`sys.dont_write_bytecode` 為 False），時間主要是執行模組本體（建立類別、dataclass）。
- **最慢的 call**：`test_segment_host.py::test_terminate_does_not_hang_on_a_blocked_sink` 與 `test_espeak_segment_drain.py::test_cancel_or_terminate_before_deferred_delivery_keeps_event_silent[True]` 各 1.00 秒，等的是產品程式寫死的 `join_delivery(1)`（`runtime/segmentHost.py:279、289`）。其次是兩個 `test_hygiene_guards.py` 守門各 0.41 秒（各自把 tests 全部 parse 一次）。
- **記憶體**：一個開 `--cov=addon --cov-branch` 的全套行程峰值 **1898 MB**；不開 coverage 時 **299 MB**。比較 coverage 7.16.2 的三種核心：

  | 核心 | 峰值 | 時間 |
  | --- | --- | --- |
  | sysmon（Python 3.14 預設） | 1898 MB | 56 秒 |
  | ctrace | 334 MB | 55 秒 |
  | pytrace | 416 MB | 69 秒 |

  兩種核心量出的覆蓋率相同（差 1 行，屬執行緒時序浮動）。sysmon 在「每個測試重新載入模組」的寫法下大量累積記憶體；這正是先前 8 個平行 coverage 行程讓 container 記憶體耗盡、重啟的根本原因。
- 覆蓋率設定只存在 scratchpad 的 coveragerc；repo 沒有 `[tool.coverage]`，直接 `pytest --cov=addon` 會把 vendored driver 算進去、也不量分支。

## 設計

1. **`pyproject.toml` 加入 `[tool.coverage.run]`／`[tool.coverage.report]`**：`core = "ctrace"`（註明理由與量測數字）、`branch = true`、`source = ["addon"]`、`omit` 內層 driver、sonic、`script_data.py`（與 ruff 的排除一致）。之後 `python3 -m pytest tests --cov` 即得到專案的標準數字，記憶體約 330 MB。
2. **可注入的 delivery join 上限**：`runtime/segmentHost.py` 的兩處 `join_delivery(1)` 改為模組常數 `DELIVERY_JOIN_TIMEOUT = 1.0`（產品預設不變）；兩個測試以 monkeypatch 縮短（例如 0.05 秒），仍斷言 terminate 不會卡在被阻塞的 sink。
3. **守門測試共用 parse 結果**：`test_hygiene_guards.py` 兩個掃描 tests 的守門共用一份以 `functools.cache` 快取的 AST。
4. **不做**：
   - setup 改成 module／session 範圍共用模組：會破壞階段 24 刻意保留的「每個測試全新模組物件」隔離，收益（最多約 20 秒）不值得風險。
   - `pytest-xdist`：使用者決定不加。

## 驗證

- 全套與逐檔通過、收集清單不變、`ruff check/format addon tests` 乾淨。
- 前後量測：全套時間、`--durations` 前 10、`--cov` 峰值記憶體。
- 壓力測試（最多 3 個 worker、有記憶體看門狗）0 失敗。
