# 階段 23：並發測試的穩定性

日期：2026-10-06。
基準：`master`（`c9952c1`）。分支：`phase23-test-stability`。
狀態：使用者要求依序完成階段 23～28（2026-10-06），自動流程執行。

對應 repo 根目錄 `refactor-test.md`（不入版控）的階段 23。

## 現況

`tests/` 有 49 處固定時間等待（`Event().wait(0.x)`、`.wait(0.x)`、`time.sleep`），分成四類：

| 類別 | 例子 | 會不會造成偶發失敗 |
| --- | --- | --- |
| A. 手寫輪詢迴圈：「等某狀態成立」 | `for _ in range(200): if ...: break; Event().wait(0.005)`；`deadline = time.monotonic() + 3; while ...: time.sleep(0.001)` | 不會（有逾時上限），但約 20 處各寫一次，逾時從 0.2 秒到 3 秒不一 |
| B. 負向檢查：「某事在一段時間內沒發生」 | `assert not done.wait(0.05)`；`Event().wait(0.1)` 後計數 | 不會誤判失敗，最多漏判 |
| C. 正向等待的逾時過短 | `waiting.done.wait(0.5)`、`final_stop.wait(0.5)` | 會；機器忙（coverage、平行執行）時可能逾時 |
| D. 斷言另一執行緒改的狀態卻沒有等待 | `test_cancel_during_contextual_final_idle_releases_waiting_ordinary[Cerence]` 的 `_pending == []` | 會；已知偶發 |

等待 helper 已有好幾份各自的版本：`test_segment_host.py::wait_until`、`test_vocalizer_segment_drain.py::wait_for`、`test_onecore_segment_drain.py::wait_events`、`espeak_drain_harness.wait_event`、`test_sapi5_segment_drain.py::wait_event`、`test_segment_lifecycle.py::wait_until_waiting`。

## 設計

新增 `tests/waiting.py`，集中兩個工具與兩個常數：

```python
WAIT_TIMEOUT = 3.0    # 正向等待的上限；條件成立就立即返回，所以寬鬆不拖慢測試
QUIET_PERIOD = 0.05   # 負向檢查觀察的時間

def eventually(predicate, timeout=WAIT_TIMEOUT, message=None):
	"""輪詢直到 predicate() 為真；逾時則 AssertionError，訊息帶上最後一次的值。回傳該值。"""

def stays_unset(event, period=QUIET_PERIOD, message=None):
	"""負向檢查：event 在 period 內沒有被設定。只能漏判、不會誤判失敗。"""
```

改寫規則：

- A 類 → `eventually(...)`。各檔自寫的 helper 改為呼叫 `eventually`，或直接以 `eventually` 取代呼叫點。
- B 類 → 改用 `stays_unset`，並統一觀察時間；「等重複事件到達再計數」的 `Event().wait(0.1)` 保留語意，改用具名常數並註明這是負向檢查。
- C 類 → 正向等待的逾時改為 `WAIT_TIMEOUT`。
- D 類 → 斷言前先 `eventually` 等狀態收斂。由壓力測試找出（見「驗證」）。
- 參數化的「慢執行緒」模擬（例如 `Event().wait(start_delay)`）是測試情境本身，保留。
- `gc.collect()` 加輪詢的弱引用檢查改用 `eventually`（每次 predicate 內先 `gc.collect()`）。

## 驗證

- 全套通過；收集清單不變（1491）。
- 壓力測試：開 coverage，4 個 worker 平行，各跑 8 輪全套。修改前先跑一次作為基準，記錄所有偶發失敗；修改後再跑一次，0 失敗。
- `tests/` 內的固定等待只剩：`waiting.py` 本身、參數化的慢執行緒模擬、各自註明理由的少數例外。
