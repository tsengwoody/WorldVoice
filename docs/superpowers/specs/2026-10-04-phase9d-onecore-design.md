# 階段 9d：OneCore

日期：2026-10-04。
基準：`master`（`22ac2ab`，9c 完成）。分支：`phase9d-onecore`。
狀態：依使用者要求自動執行（spec → plan → 實作 → Fable review）。

本文件是 [`refactor.md`](../../../refactor.md) §9 階段 9 的第四個子階段，對應 §4.1（stops 計數閘）、§4.3（InnerPort）與 §4.4（`Voice.synth_driver_class` 定義順序）。

## 需求與範圍

1. **`_segmentStops` 改用 `StopGate(self._segmentCondition)`。**
   - OneCore 的 stop 計數有兩種用法：
     - `cancel()` 包住整段：改用 `with self._stopGate.hold()`；
     - 控制錯誤分兩段處理：`_captureSegmentControlFailure` 在 condition 下 +1，`_deliverSegmentControlFailure` 稍後 -1。
   - 第二種用法需要非 context manager 的介面，因此 `StopGate` 新增 `enter()`／`leave()`，由呼叫端在持有 condition 時呼叫。`hold()` 改為建立在這兩者之上，行為不變。
   - 讀取端（worker 的等待條件、`pause()`、`_maybeInitPlayer`）改用 `self._stopGate.clear`。
2. **`_OneCorePort`：列出 wrapper 使用的父類別私有名稱。**
   - 父類別包括 vendored 內層 `driver/OneCore/driver/__init__.py` 的 `OneCoreSynthDriver`，以及 NVDA 的 `synthDrivers.oneCore`。
   - `NVDA_PRIVATES` 共 13 個：
     - `_OcPreAPI5SsmlConverter`、`_OcSsmlConverter`、`_callbackInst`、`_dll`；
     - `_earlyExitCB`、`_isProcessing`、`_ocSpeechToken`、`_pitch`、`_player`；
     - `_queuedSpeech`、`_rate`、`_volume`、`_wasCancelled`。
   - `NVDA_OVERRIDES` 共 4 個：`_queueSpeech`、`_processQueue`、`_callback`、`_maybeInitPlayer`。
   - 守門測試與 SAPI5 相同：
     - wrapper 存取的私有名稱（扣除自己定義的）都在清單內；
     - 清單名稱存在於內層驅動或 NVDA `oneCore.py`，以單字邊界比對；
     - 覆寫的私有方法清單完整。
   - 與 SAPI5 一樣不逐一轉發存取：OneCore 的 worker 與 callback 圍繞這些狀態重寫父類別流程。
3. **§4.4：`Voice` 移到 `SynthDriver` 之後，在類別本體宣告 `synth_driver_class = SynthDriver`**，與其餘五家一致。
   - 刪除開頭的 `SynthDriver = BaseOneCoreSynthDriver` 別名與模組末尾的重新指派。
   - `tests/test_runtime_composition.py` 以 AST 取第一個類別的地方改為以名稱取 `Voice`。

### 評估後不採用（記錄理由）

- **`ControlFaultPolicy`**：
  - OneCore 的控制錯誤必須先在持有 `_segmentPauseLock` 時 capture，搶在 cancel 讓操作退場之前；deliver 則在鎖外。
  - 這個流程還要處理 `_segmentControlGeneration`、`_wasCancelled`、legacy 的 DONE 通知與解除暫停。
  - 單段式的 `fail()` 套不上；為了它擴充兩段式 API 與多個 hook，會讓共用元件只為一家服務。
- **`QueuedRecords`**：佇列是父類別的 `_queuedSpeech` list，裡面混著設定 tuple 與 `_SpeechJob`，record 從 job 取出，沒有獨立的 record 表。
- **併入 `LeasedPlayer`**：
  - OneCore 沒有 player proxy。player 由父類別的 `_maybeInitPlayer` 建立；feed 在 native callback 已 admit 的 consumer 內直接呼叫。
  - 要包一層 proxy 得攔截父類別對 `_player` 的指派，風險高於收益。
- **`get_segment_drain_support` 簽名**：已是 keyword-only 必填。

### 成功條件

1. 完整測試全部通過；`ruff format --check addon` 通過；`ruff check --select F401,F821`（範圍同 refactor.md 附錄）為 0。
2. OneCore wrapper 不再出現 `_segmentStops`（守門測試）。
3. `_OneCorePort` 守門測試通過。
4. OneCore wrapper 只在 `SynthDriver` 之後定義一次 `Voice`，不再有模組層的 `SynthDriver =` 指派（守門測試）。
5. `driver/<Engine>/driver/`、`driver/sonic` 無變動。

### 不在範圍內

VE/Cerence（9e）；先前子階段延後的 minor。

## 設計

```python
class StopGate:
	def enter(self) -> None:
		"""Start a stop; call while holding the condition."""
		self._stops += 1

	def leave(self) -> None:
		"""End a stop and wake waiters; call while holding the condition."""
		self._stops -= 1
		self._condition.notify_all()

	@contextmanager
	def hold(self):
		with self._condition:
			self.enter()
		try:
			yield
		finally:
			with self._condition:
				self.leave()
```

OneCore 的對應：
- `__init__`：`self._stopGate = StopGate(self._segmentCondition)` 取代 `self._segmentStops = 0`。
- `cancel()`：
  - 原本在 admission 與 condition 下 +1，在最外層 `finally` 中 -1。
  - 改為整段包在 `with self._stopGate.hold():` 內，其餘內容不變；+1 提前到取得 admission 之前，只會讓 worker、`pause` 更早讓路。
  - 但 `cancel` 在 condition 區塊內同時設定 `_segmentPaused = False` 與 generation +1，這兩項仍留在原位。
- `_captureSegmentControlFailure`：`self._stopGate.enter()`。
- `_deliverSegmentControlFailure`：`self._stopGate.leave()`，取代原本的 -1 與 `notify_all`。
- worker 條件：`self._stopGate.clear`。
- `pause()` 的兩處 `self._segmentStops`：改為 `not self._stopGate.clear`。
- `_maybeInitPlayer`：`self._segmentPaused and self._stopGate.clear`。

## 測試

1. `tests/test_engine_control.py`：`enter`／`leave` 的計數與喚醒。
2. OneCore 既有測試全部通過；`tests/test_onecore_segment_drain.py` 連跑 20 次。
3. 守門測試（`tests/test_native_strategy_guards.py`）：成功條件 2、3、4。
4. 契約測試全部通過。
