# 階段 9b：SAPI5 與共用的引擎控制元件

日期：2026-10-04。
基準：`master`（`1f24924`，9a 完成）。分支：`phase9b-sapi5`。
狀態：依使用者要求自動執行（spec → plan → 實作 → Fable review）。

本文件是 [`refactor.md`](../../../refactor.md) §9 階段 9 的第二個子階段，對應：
- §4.1：stops 計數閘、「清佇列 + abandon」、control-fault 路徑、player proxy；
- §4.2：player stop 失敗時 latch；
- §4.3：InnerPort。

## 需求與範圍

1. **修正 SAPI5 的 player stop 失敗不 latch**（9a 契約測試的 strict xfail）。
   - NVDA `sapi5.SynthDriver.cancel()` 與 `_stopThread()` 直接呼叫 `self.player.stop()`。`_SegmentPlayer` 沒有 `stop()`，經 `__getattr__` 轉給真正的 player，失敗不會 latch。
   - 改為：`stop()` 失敗時先走 SAPI5 的 control-fault 路徑（latch、清佇列、喚醒 worker），再照原樣 raise。
   - 移除契約測試的 SAPI5 xfail。
2. **新增 `runtime/engineControl.py`**，放三個引擎共用的元件。SAPI5 是第一個使用者；OneCore、VE、Cerence 在 9d/9e 改用。
   - **`StopGate`**：「進行中的 stop 計數」。worker 在計數歸零前不取下一個請求，取代 SAPI5 的 `_segmentStops`（OneCore 的 `_segmentStops`、VE/Cerence 的 `_stops` 之後同樣改用）。
   - **`QueuedRecords`**：已送進引擎佇列、尚未被 worker 取走的 record，以引擎自己的請求識別碼為 key。取代 SAPI5 的 `_segmentRecords` dict。
   - **`ControlFaultPolicy`**：只 latch 一次控制錯誤、在引擎鎖下丟掉佇列、喚醒 worker，然後在鎖外逐一 `host.abandon`。取代 SAPI5 的 `_failSegmentControl` 本體。
3. **SAPI5 的 player proxy 改為 `LeasedPlayer` 的子類。**
   - `LeasedPlayer` 新增三個可覆寫的 hook，預設值即現行行為：
     - `_callback(record, onDone)`：admit consumer、bind callback、記錄錯誤；
     - `_record_error(record, error)`：`host.record_error`；
     - `_stop_failed(error)`：`host.latch_control_error`。
   - `_SegmentPlayer(LeasedPlayer)`：
     - `feed`：保留 SAPI5 的前置檢查（driver 已回收、已被換掉的 player、沒有目前 record 時直接餵給真正的 player），其餘交給 `super().feed`；
     - `_callback`：維持「record 仍有效才呼叫」，因為 NVDA 的 bookmark index 以 `feed(None, 0, onDone)` 送出，必須在 `EndStream` 關閉 admission 之後仍能觸發；
     - `_record_error`：`driver._recordSegmentError`；
     - `_stop_failed`：`ControlFaultPolicy.fail`；
     - `idle` 整個覆寫：保留「idle 早於段落結束通知即失敗」的偵測。
   - feed 失效後的補 stop 改用 proxy 的 `stop()`（會 latch），與 `LeasedPlayer` 一致。以往 SAPI5 用的是真正 player 的 `stop()`，失敗不會 latch。
4. **SAPI5 的 `InnerPort`（`_Sapi5Port`）**：列出 wrapper 對 NVDA `synthDrivers.sapi5` 的所有私有存取：
   - 狀態：`_threadCond`、`_speakRequests`、`_isCancelling`、`_isCompleted`、`_isSpeaking`、`_isStoppingThread`、`_bookmarkLists`、`_requestsAvailable`、`_requestCompleted`、`_thread`；
   - 模組成員：`sapi5._SapiEvent`、`sapi5._SPEventEnum`、`sapi5.SynthDriverAudioStream`、`sapi5.SapiSink`。

   本子階段只建立 port 類別，以常數與 docstring 列出這些名稱，並以守門測試確認 wrapper 不存取清單以外的 `_` 開頭 NVDA 名稱。不把每次存取改成經過 port 轉發：SAPI5 的 worker 重新實作 NVDA 的 `_speakThread`，逐一轉發會讓 128 行 worker 難以和 NVDA 原碼對照。NVDA 升級時只需比對清單。
### 成功條件

1. 完整測試全部通過；契約測試不再有 SAPI5 的 xfail。
2. `ruff format --check addon` 通過；`ruff check --select F401,F821`（範圍同 refactor.md 附錄）為 0。
3. SAPI5 wrapper 不再出現 `_segmentStops`、`_segmentRecords`、`_dropQueuedRecords` 這些名稱；`_failSegmentControl` 只是轉發到 policy 的一行。
4. `_SegmentPlayer` 是 `LeasedPlayer` 的子類（守門測試）。
5. SAPI5 wrapper 存取的 NVDA 私有名稱都在 `_Sapi5Port.NVDA_PRIVATES` 清單內（守門測試）。
   - 存取：`self._x`／`driver._x`／`sapi5._X`，扣除 wrapper 自己在 `SynthDriver.__init__` 指派的屬性與 wrapper 類別定義的方法。
   - 清單中每個名稱都必須出現在 `ref/nvda/source/synthDrivers/sapi5.py`，確保清單沒有過時。
6. `driver/<Engine>/driver/`、`driver/sonic` 無變動。

### 不在範圍內

- OneCore、RHVoice、VE、Cerence 改用 `engineControl`：9c–9e。
- `NativeRecord` 狀態 Enum：階段 10。
- 9a 延後的小項：`barriers` 預設空集合的防呆、eSpeak terminate 後的強化測試，留待下一次動 host 時處理。

## 設計

### 1. `runtime/engineControl.py`

```python
class StopGate:
	"""Stops in flight on an engine's queue; its worker takes no request until none remain.

	Guarded by the engine's own condition, which the gate notifies on release.
	"""

	def __init__(self, condition: Condition): ...
	@contextmanager
	def hold(self) -> Iterator[None]: ...   # 在 condition 下 +1；離開時在 condition 下 -1 並 notify_all
	@property
	def clear(self) -> bool: ...            # 呼叫端持有 condition 時讀取


class QueuedRecords:
	"""Records submitted to an engine queue and not yet taken by its worker.

	The caller guards it with the lock that also guards the engine's queue.
	"""

	def add(self, key, record) -> None: ...
	def pop(self, key) -> NativeRecord | None: ...
	def take_all(self) -> list[NativeRecord]: ...
	def __len__(self) -> int: ...


class ControlFaultPolicy:
	"""Latch the first control error, drop queued work and wake the worker."""

	def __init__(self, host: SegmentHost, condition: Condition, drop: Callable[[], list[NativeRecord]]): ...
	def fail(self, error: Exception) -> bool:
		# 在 condition 下：已有 control error 則 return False；latch；dropped = drop()；notify_all。
		# 在鎖外：逐一 host.abandon(record)；return True。
```

鎖順序沿用 host 模組：host admission → 引擎鎖（condition）→ host condition → lifecycle condition。`ControlFaultPolicy.fail` 在引擎鎖下呼叫 `latch_control_error`，與現行 `_failSegmentControl` 相同；`abandon` 會等 consumer，所以一定在鎖外。

### 2. `LeasedPlayer` hook

```python
	def feed(self, data, size=None, onDone=None):
		host = self._host
		with host.consumer() as record:
			if record is None:
				return None
			callback = None if onDone is None else self._callback(record, onDone)
			try:
				...（不變）
			except Exception as error:
				self._record_error(record, error)
				raise
			finally:
				if not record.is_valid():
					self.stop()

	def _callback(self, record, onDone): ...   # 現行的巢狀 callback
	def _record_error(self, record, error): self._host.record_error(record, error)
	def _stop_failed(self, error): self._host.latch_control_error(error)

	def stop(self):
		try:
			return self._player.stop()
		except Exception as error:
			self._stop_failed(error)
			raise
```

eSpeak 使用預設 hook，行為不變。

### 3. SAPI5

- `__init__`：
  - `self._stopGate = StopGate(self._threadCond)`，這要在 `super().__init__()` 之後，因為 `_threadCond` 由 parent 建立。若 parent 建構期間就會用到 gate，改為延後建立；實作時確認。
  - `self._queued = QueuedRecords()`；
  - `self._controlFault = ControlFaultPolicy(self._segmentHost, ..., drop=self._dropQueued)`，同樣在 `super().__init__()` 之後建立。
- `_dropQueued()`：清 `_speakRequests`，並回傳 `self._queued.take_all()`。
- `_failSegmentControl(error)` → `self._controlFault.fail(error)`。
- `submit`：`driver._queued.add(id(request), record)`。
- worker：
  - 等待條件改為 `self._stopGate.clear and self._requestsAvailable()`；
  - `record = self._queued.pop(id(request))`。
- `cancel()`：

```python
	def cancel(self):
		with self._stopGate.hold():
			self._invalidateSegments()
			return super().cancel()
```

  現行版本在 admission 內遞增計數，`hold()` 改在取得 admission 之前遞增。這只會讓 worker 更早開始等待，不影響安全；`hold()` 只短暫取得引擎鎖，不與 admission 巢狀。
- `_SegmentPlayer(LeasedPlayer)`：依需求 3。
- `_Sapi5Port`：依需求 4，清單以 `NVDA_PRIVATES = frozenset({...})` 呈現。

## 測試

1. `tests/test_engine_control.py`：
   - `StopGate`：hold 期間 `clear` 為 False；巢狀 hold；離開時喚醒等待者；hold 內拋例外仍會釋放。
   - `QueuedRecords`：add/pop/take_all/len。
   - `ControlFaultPolicy`：
     - 第一次 latch 並 abandon 被丟掉的 record，回傳 True；
     - 第二次回傳 False、不 abandon；
     - `abandon` 在鎖外執行：以會在 abandon 時嘗試取得 condition 的假 host 驗證不會 deadlock。
2. `tests/test_segment_host.py`：`LeasedPlayer` 的三個 hook 由子類覆寫時會被呼叫；預設行為不變（既有測試）。
3. SAPI5：
   - `cancel()` 中 player stop 失敗會 latch，之後的 segment 與一般 speak 被拒；
   - 失效 feed 之後的補 stop 失敗會 latch；
   - bookmark 的 `feed(None, 0, onDone)` 在 `EndStream` 之後仍會觸發 index（既有測試涵蓋時引用之）。
4. 契約測試：移除 SAPI5 xfail。
5. 守門測試：成功條件 3、4、5。
