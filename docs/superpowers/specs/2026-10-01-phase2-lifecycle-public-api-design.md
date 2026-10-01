# 階段 2：lifecycle 公開查詢 API 與事件驅動取消

日期：2026-10-01。
基準：`master`（`dfe01e6`，含階段 0、1）。分支：`phase2-lifecycle-api`。
狀態：對話中的範圍與設計已獲使用者確認；本文件待使用者審閱。

本文件是 [`refactor.md`](../../../refactor.md) §9 的階段 2，對應 §2.2 建議 2、3 與 §4.3 第一點。前一階段見 [2026-10-01-phase1-engine-segment-contract-design.md](2026-10-01-phase1-engine-segment-contract-design.md)。

## 需求與範圍

使用者要讓 engine wrapper 不再直接讀寫 `SegmentOperation`／`SegmentLifecycle` 的私有成員，並移除 50 ms 輪詢，讓階段 3 的 `SegmentHost` 能建立在乾淨的介面上。

已確認的決定：

1. **公開查詢，內部旗標不動**：新增唯讀查詢與 lifecycle 方法，wrapper 全部改用；`SegmentOperation` 的內部旗標（`_admitting`、`_submitted`、`_run_started`、`_retired`、`_pre_admission_rejected` 等）與 `run()` 的狀態機維持原樣。單一狀態 Enum 留給階段 3 重寫 `run()` 時處理。
2. **不做 `attach()`**：wrapper 掛在 operation 上的自訂屬性（`_ve_work`、`_ve_natives`、`_onecore_native`、`_rhvoice_cancelled`、`_espeak_cancelled`、`_espeak_sink`、`_espeak_native`，以及 Neural 的 `_neural_natives`）會在階段 3 被 `NativeRecord` 取代，本階段不動。
3. **命名沿用 `runtime/` 的 snake_case**。
4. **取消通知納入 `CancellationView` 契約**（方案 B）：不保留輪詢的 fallback 路徑。

成功條件：

1. `addon/` 內（扣除內層驅動）沒有任何 wrapper 讀寫 `SegmentOperation` 或 `SegmentLifecycle` 的私有成員。檢查方式見「驗收」。wrapper 自訂屬性（決定 2）不在此限。
2. `runtime/segmentLifecycle.py`、`driver/VE/__init__.py`、`driver/Cerence/__init__.py` 不再有 `wait(0.05)` 或其他固定間隔輪詢。
3. 取消一個 token 後，正在等待它的 lifecycle／wrapper 在 20 ms 內醒來（原本最長 50 ms）。
4. 全部既有測試與階段 1 契約測試維持通過：基線 1255 passed、96 skipped、2 xfailed，加上本階段新增測試。
5. 本地還原 Neural 後，Neural 的測試與契約案例仍通過（Neural 程式碼不修改、不提交）。

**不在範圍內**：

- C3（VE/Cerence `speak_segment` 阻塞到 delivery）本身的修正：屬於階段 3。本階段只把它的輪詢改成事件驅動，阻塞行為不變，契約 4 的 xfail 保留。
- `ProducerLease` 與 `CallbackLease` 合併（§2.2 建議 4）：屬於階段 3。
- delivery thread 懶重啟（§2.2 第五點）：不改。
- 內層驅動 `driver/<Engine>/driver/` 與 Neural 程式碼。

## 現況

wrapper 讀取 lifecycle 內部狀態的位置（基準 `dfe01e6`）：

| 私有成員 | 使用者 | 用途 |
| --- | --- | --- |
| `operation._run_started` | OneCore ×5 | 判斷 operation 是否已進入 `run()`，決定能否 `reject_pending` |
| `operation._retired` | VE、Cerence | 判斷是否要等 delivery |
| `operation._sink` | RHVoice | `run()` 失敗時以原 sink 重新 `reject_new` |
| `lifecycle._delivery_thread` | VE、Cerence（避免自我等待）、OneCore（terminate 時 join） | delivery thread 身分 |
| `lifecycle._resource_busy` | VE、Cerence ×3 | 一般語音等待 contextual 工作釋放資源 |
| `lifecycle._condition` | VE、Cerence ×5 | 搭配上一列等待 |

輪詢位置：

- `runtime/segmentLifecycle.py` 的 `run()`：等待資源釋放時 `self._condition.wait(0.05)`，因為外部 token 被取消時沒有任何通知。
- `driver/VE/__init__.py`、`driver/Cerence/__init__.py` 的 `_wait_segment_delivery`：`completion.wait(0.05)` 迴圈檢查 token。
- 同兩檔的一般語音路徑：`lifecycle._condition.wait(0.05)` 等待 `_resource_busy` 解除，或該工作失效（token 取消或 VE 直接 `cancel()`）。

取消來源：

- production 中實作 `CancellationView` 的只有 `runtime/scheduler.py` 的 `CancellationToken`（內部是 `threading.Event`）。外掛引擎從 scheduler 收到 token，不自行建立。
- 測試另有兩個自訂 token：`tests/test_worldvoice_cancel_wrappers.py::Token` 與 `tests/test_runtime_session.py::EventToken`。
- scheduler 在持有自己的 `_state_cond` 時呼叫 `token.cancel()`。

## 設計

### 1. `CancellationView` 取消通知

`runtime/session.py`：

```python
class CancellationView(Protocol):
	def is_cancelled(self) -> bool: ...
	def add_callback(self, callback: Callable[[], None]) -> Callable[[], None]: ...
```

`add_callback` 的語意（所有實作都必須遵守）：

- 回傳一個「移除」函式；呼叫它之後該回呼不會再被呼叫。重複移除不出錯。
- token 已取消時，在呼叫 `add_callback` 的 thread 上立即呼叫回呼一次。
- 否則在第一次 `cancel()` 時，於呼叫 `cancel()` 的 thread、token 自身的鎖之外，依註冊順序各呼叫一次。之後再 `cancel()` 不重複呼叫。
- 回呼拋出的例外記錄 log 後忽略，不影響其他回呼與 `cancel()` 的呼叫端。

`runtime/scheduler.py` 的 `CancellationToken` 實作上述語意。兩個測試 token 補上相同語意的最小實作。

**回呼規則**：回呼只能做「通知」（`Event.set()`、在 condition 上 `notify_all()`），不得阻塞、不得呼叫 hook、sink 或 scheduler。理由：scheduler 會在持有 `_state_cond` 時呼叫 `cancel()`。

### 2. `SegmentOperation` 公開查詢

在 `runtime/segmentLifecycle.py`：

```python
class SegmentOperation:
	@property
	def sink(self) -> SegmentEventSink: ...   # accept() 收到的原 sink，唯讀
	def has_started(self) -> bool: ...        # 已進入 run() 或已被 reject（_run_started）
	def is_retired(self) -> bool: ...         # 已退場（_retired）
```

查詢在 lifecycle 的 `_condition` 下讀取旗標，回傳當下快照。呼叫端若需要「讀取後依結果動作」的原子性，必須自行持有它原本就持有的 wrapper 鎖（例如 OneCore 的 `_segmentCondition`），與現況相同。`SegmentOperation` 不加 `__slots__`，wrapper 自訂屬性照常可用。

### 3. `SegmentLifecycle` 公開方法

```python
class SegmentLifecycle:
	def on_delivery_thread(self) -> bool: ...
	def join_delivery(self, timeout: float | None = None) -> None: ...   # 在 delivery thread 上呼叫時不做事
	def is_resource_busy(self) -> bool: ...
	def wait_idle(self, *, still_wanted: Callable[[], bool] = lambda: True,
			token: CancellationView | None = None) -> bool: ...
	def wake_waiters(self) -> None: ...
```

- `wait_idle`：等到資源不忙時回傳 `True`；`still_wanted()` 變成 `False` 時回傳 `False`。等待期間不輪詢，由下列事件喚醒：資源釋放（lifecycle 既有的 `notify_all`）、`token` 的取消回呼、`wake_waiters()`。
- `wake_waiters`：在 `_condition` 上 `notify_all()`。供 wrapper 在 lifecycle 不知情的狀態改變後呼叫，例如 VE 直接 `cancel()` 一般語音工作。
- `run()` 等待資源時，以 `token.add_callback` 註冊喚醒，取代 `wait(0.05)`；離開等待時移除回呼。

### 4. wrapper 遷移

| 原用法 | 改為 |
| --- | --- |
| OneCore `operation._run_started` | `operation.has_started()` |
| VE、Cerence `operation._retired` | `operation.is_retired()` |
| RHVoice `operation._sink(event)` | `operation.sink(event)` |
| VE、Cerence `threading.current_thread() is not lifecycle._delivery_thread` | `not lifecycle.on_delivery_thread()` |
| OneCore terminate 的 `_delivery_thread` join | `lifecycle.join_delivery(1)` |
| VE、Cerence `_condition.wait_for(not _resource_busy)` 與一般語音迴圈 | `lifecycle.wait_idle(...)`、`lifecycle.is_resource_busy()` |
| VE、Cerence `_wait_segment_delivery` 的 `completion.wait(0.05)` 迴圈 | `token.add_callback(completion.set)` 後 `completion.wait()`，離開時移除 |

VE、Cerence 直接取消一般語音工作的路徑（`cancel()` 內對 `_SpeechWork.cancel()` 的呼叫）之後呼叫 `lifecycle.wake_waiters()`，讓 `wait_idle` 的 `still_wanted` 被重新檢查。

各 wrapper 的具體改法由 plan 依原型確認；本表的每一列都必須消失於驗收的私有存取檢查中。

### 5. 鎖序文件

`runtime/segmentLifecycle.py` 模組 docstring 補上鎖序（`scheduler.py` 已有同類說明）：

1. wrapper 鎖 → lifecycle `_condition`（wrapper 一律如此）。
2. scheduler `_state_cond` → token 回呼 → lifecycle `_condition`（取消通知）。
3. lifecycle 在持有 `_condition` 時不呼叫 hook、sink、token 回呼，也不取得 wrapper 或 scheduler 的鎖。

### 6. 契約 harness

`tests/engine_contract_harness.py` 的 `delivery_thread_ident()` 改為 `on_delivery_thread() -> bool`，委派給 `lifecycle.on_delivery_thread()`。`tests/test_engine_segment_contract.py` 的 `Events` 在交付時記錄 `adapter.on_delivery_thread()`；契約 1 斷言該值為 `[True]`，並維持「不在呼叫端 thread」的斷言。

## 測試

- **`CancellationToken.add_callback`**（`tests/test_runtime_scheduler.py`）：取消時呼叫一次；已取消時立即呼叫；移除後不呼叫；重複 `cancel()` 不重複呼叫；回呼例外不影響其他回呼與 `cancel()`；回呼在 token 鎖之外執行（回呼內可以再呼叫 `is_cancelled()` 與 `add_callback()` 而不死結）。
- **operation 查詢與 lifecycle 方法**（`tests/test_segment_lifecycle.py`）：`has_started`／`is_retired` 在 accept、run、reject、retire 各階段的值；`sink` 為原 sink；`on_delivery_thread` 在 delivery thread 與其他 thread 的值；`join_delivery` 在 delivery thread 上不死結；`wait_idle` 在資源釋放、`still_wanted` 轉為 False、token 取消、`wake_waiters()` 四種情況下返回且回傳值正確。
- **不再輪詢**：資源忙碌時以已註冊的 token 等待 `run()`／`wait_idle`，取消 token 後 20 ms 內返回；以單元測試鎖住。VE 的 `_wait_segment_delivery` 以同一上限驗證。
- **私有存取守門**：新增測試掃描 `addon/synthDrivers/WorldVoice/driver/*/__init__.py`（扣除內層驅動與未追蹤的 Neural），斷言正規式 `\b(operation|lifecycle|_segmentLifecycle)\._(\w+)` 沒有任何命中，但允許 wrapper 自訂屬性前綴 `_ve_`、`_onecore_`、`_rhvoice_`、`_espeak_`、`_neural_`（決定 2）。基準 `dfe01e6` 上這條規則命中 26 處，正好是「現況」表列出的位置；wrapper 自己的欄位（例如 `self._segmentCondition`）不會被比對到。
- 既有測試若因直接讀私有成員而失敗，才改用新 API；未受影響者不動。

## 驗收

- `python3 -m pytest tests -q`：全部通過；skipped 仍為 96，xfailed 仍為 2。
- `grep -n "wait(0.05)" addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py addon/synthDrivers/WorldVoice/driver/VE/__init__.py addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py`：無輸出。
- 私有存取守門測試通過。
- 在含 Neural 快照的臨時 worktree 中，完整測試與契約測試通過。
- `ruff format --check addon`：通過；`git diff master --stat -- 'addon/synthDrivers/WorldVoice/driver/*/driver'`：無輸出；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural`：無輸出。
