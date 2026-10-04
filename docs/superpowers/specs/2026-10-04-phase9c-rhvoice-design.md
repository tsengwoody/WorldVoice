# 階段 9c：RHVoice

日期：2026-10-04。
基準：`master`（`70fa354`，9b 完成）。分支：`phase9c-rhvoice`。
狀態：依使用者要求自動執行（spec → plan → 實作 → Fable review）。

本文件是 [`refactor.md`](../../../refactor.md) §9 階段 9 的第三個子階段，對應：
- §4.1：player proxy、stops 計數閘、weakref trampoline；
- §4.2：`get_segment_drain_support` 簽名；
- §4.3：RHVoice 對內層 `_SynthDriver__*` 名稱的存取；
- §7 的 D10（ctypes callback 內 `self._owner()` 未檢查 None）。

## 需求與範圍

1. **`_RHVoiceInner` port**：wrapper 對 vendored 內層驅動 `driver/RHVoice/driver/__init__.py` 的 `SynthDriver` 名稱改編屬性的所有存取，集中到一個類別。
   - 讀寫的屬性（`_SynthDriver__player`、`__lib`、`__tts_engine`、`__tts_queue`、`__tts_thread`、`__cancel_flag`、`__profile`、`__rate`、`__pitch`、`__volume`、`__rate_boost`）以具名 property 取得。`tts_engine` 需要可寫，因為 terminate 會把它設為 None。
   - `__setattr__` 攔截的四個 callback 名稱列為常數 `CALLBACK_NAMES`。
   - wrapper 其餘程式不再出現 `_SynthDriver__` 字串（守門測試）；port 裡的每個名稱都必須存在於內層驅動原始碼（守門測試）。
   - 內層驅動本身不改。
2. **`_WavePlayer` 改為 `LeasedPlayer` 的子類。**
   - `LeasedPlayer` 把 admit 之後的 feed 主體抽成 `_feed_admitted(record, data, size, onDone)`；`feed` 改為 `with host.consumer() as record: ... return self._feed_admitted(...)`。eSpeak 與 SAPI5 行為不變。
   - RHVoice 的 `feed(data, onDone=None)`：只在綁定的 callback record（`host.callback_record()`）下 admit，沒有就丟棄；然後呼叫 `_feed_admitted(record, data, None, onDone)`。
   - `_callback`：以 `consumer(record, audio=True)` admit。worker 最後的 idle 可能在 native gate 關閉後才釋放它。錯誤只記錄、不再拋出（同現行）。
   - `idle`：整個覆寫，把錯誤記到綁定的 record（同現行）。
   - `stop`：沿用 `LeasedPlayer.stop`（失敗時 latch，同現行）。
3. **`_segmentCancelling` 改用 `StopGate(self._segmentCondition)`。**
   - worker（`_QueuedSpeech`）的等待條件 `record.closed or owner._segmentCancelling == 0` 改為 `record.closed or owner._stopGate.clear`。
   - `cancel()` 以 `with self._stopGate.hold():` 包住整段。計數比現行更早 +1（在取得 admission 之前），只會讓 worker 更早等待。
4. **D10：wrapper 被回收後 C callback 不再拋 `AttributeError`。**
   - `_NativeCallback.__call__`：owner 已回收時回傳拒絕值（done callback 回傳 None，其他回傳 0），與現行「record 不存在」時相同。
   - `_NativeLibrary` 改為直接持有 host（host 不強參照 driver，不形成循環），不再透過 owner weakref 取 host。
   - `_QueuedSpeech` 已檢查 owner 是否為 None，不變。
5. **`get_segment_drain_support(self, *, nvda_version: str, audio_mode: str) -> DrainSupport`**（keyword-only 必填）。

### 成功條件

1. 完整測試全部通過；`ruff format --check addon` 通過；`ruff check --select F401,F821`（範圍同 refactor.md 附錄）為 0。
2. RHVoice wrapper 除 `_RHVoiceInner` 類別內以外不出現 `_SynthDriver__`；port 的名稱都存在於內層驅動原始碼（守門測試）。
3. `_WavePlayer` 是 `LeasedPlayer` 的子類；wrapper 不再有 `_segmentCancelling`（守門測試）。
4. `get_segment_drain_support` 為 keyword-only 必填（守門測試，與 eSpeak 同一個測試參數化）。
5. `driver/<Engine>/driver/`、`driver/sonic` 無變動。

### 不在範圍內

- `_segmentById`：它是 callback identity → record 的查表，包含目前的 record，不是「尚未被 worker 取走的佇列」，所以不改用 `QueuedRecords`。cancel 中的「丟掉目前以外的 record 並 abandon」維持原樣。
- `ControlFaultPolicy`：RHVoice 的 latch 不伴隨清佇列（內層 cancel 清自己的佇列），沒有可以共用的形狀。
- 9a/9b 延後的 minor。

## 設計

### `_RHVoiceInner`

```python
class _RHVoiceInner:
	"""The vendored RHVoice SynthDriver's name-mangled state this wrapper uses.

	The inner driver stays unmodified; every access to its private names goes
	through here, so an update of the vendored driver is checked in one place.
	"""

	CALLBACK_NAMES = frozenset({
		"_SynthDriver__sample_rate_callback", "_SynthDriver__speech_callback",
		"_SynthDriver__mark_callback", "_SynthDriver__done_callback",
	})
	DONE_CALLBACK = "_SynthDriver__done_callback"

	def __init__(self, driver): self._driver = weakref.ref(driver)
	# 唯讀 property：player、lib、tts_queue、tts_thread、cancel_flag、profile、rate、pitch、volume、rate_boost
	# 可寫 property：tts_engine
```

- port 以 weakref 持有 driver，與現行 helper 一致。
- `SynthDriver.__init__` 在 `super().__init__()` 之前建立 `self._inner`，因為 `__setattr__` 在內層 init 期間就會用到 `CALLBACK_NAMES`。
- `__setattr__` 改用 `_RHVoiceInner.CALLBACK_NAMES` 與 `DONE_CALLBACK`，都是類別常數，不需要 instance。

### `LeasedPlayer._feed_admitted`

```python
	def feed(self, data, size=None, onDone=None):
		with self._host.consumer() as record:
			if record is None:
				return None
			return self._feed_admitted(record, data, size, onDone)

	def _feed_admitted(self, record, data, size, onDone):
		callback = None if onDone is None else self._callback(record, onDone)
		try:
			if size is None:
				return self._player.feed(data, onDone=callback)
			return self._player.feed(data, size, onDone=callback)
		except Exception as error:
			self._record_error(record, error)
			raise
		finally:
			# （現行註解）
			if not record.is_valid():
				self.stop()
```

## 測試

1. `tests/test_segment_host.py`：`_feed_admitted` 可由子類呼叫（以子類只覆寫 `feed` 的方式驗證）；既有 LeasedPlayer 測試不變。
2. `tests/test_rhvoice_segment_drain.py`：
   - D10：owner 被回收後 `_NativeCallback` 回傳拒絕值（以 `weakref` 被清除的替身驗證）；
   - `_WavePlayer` 的 feed 只在綁定 record 下 admit；
   - index callback 在 close 之後仍可觸發（既有測試涵蓋時引用之）；
   - cancel 期間 worker 不 begin 下一個 record（既有 `_segmentCancelling` 相關測試涵蓋時引用之）。
3. 守門測試（`tests/test_native_strategy_guards.py`）：成功條件 2、3、4。
4. 契約測試全部通過。
