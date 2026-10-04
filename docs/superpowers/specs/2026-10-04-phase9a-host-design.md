# 階段 9a：SegmentHost 介面收斂與 eSpeak

日期：2026-10-04。
基準：`master`（`5c99167`，階段 7 完成）。分支：`phase9a-host`。
狀態：依使用者要求自動執行（spec → plan → 實作 → Fable review）。使用者已決定：
- 階段 9 拆成子階段：9a host + eSpeak、9b SAPI5、9c RHVoice、9d OneCore、9e VE/Cerence；
- VE/Cerence 維持兩份手工複本，不在建置時複製共用本體。

本文件是 [`refactor.md`](../../../refactor.md) §9 階段 9 的第一個子階段，對應 §2.1（`NativeStrategy`、terminated、`fail_accepted`）、§4.2（LSP 不一致、契約情境）、§4.3（InnerPort）與 §4.4（eSpeak 全域）。

## 需求與範圍

1. **`NativeStrategy` 改為 ABC（Template Method）。**
   - `submit`、`stop_native`、`stop_player` 為 abstract；`prepare`、`admission_error`、`drain` 提供預設實作（原樣傳回、None、不做事）。
   - `SegmentHost` 刪除三處 `getattr` 探測，一律呼叫。
   - 六家的 `_XStrategy` 都繼承 `NativeStrategy`。其他五家在 9a 只改基底類別，行為不動。
   - `drain` 的預設實作不做事，與現行「沒有 drain 時只檢查 barrier」相同，因為 barrier 檢查在 host。
2. **terminated 之後的一般 `speak()` 一律 raise。**
   - `SegmentHost.enqueue(commands, operation=None)` 在 terminated 時拋 `RuntimeError(f"{engine} driver has terminated")`，不再靜默丟棄。
   - 帶 operation 的路徑照舊取消 work 並 return。
   - 現在靜默丟棄的是 eSpeak 與 RHVoice，改由 host 統一。其他四家 wrapper 自己的檢查在各自的子階段移除，9a 不動。
3. **控制錯誤一律讓已接受的段落失敗。**
   - 刪除 `SegmentHost(..., fail_accepted_on_control_error=...)` 參數，行為固定為現行的 True：
     - latch 時讓所有已接受的 operation `fail`；
     - 送出時 DRAINED 改報 FAILED。
   - 理由：階段 3b-2 定下「停止失敗後不得回報成功」。eSpeak 與 SAPI5 當時保留 False 只是為了「行為不變」，沒有引擎層面的理由。
   - 對外行為的改變：eSpeak 與 SAPI5 在控制錯誤後，已排空但尚未送出的段落改報 `SEGMENT_FAILED`。
   - VE、Cerence、OneCore、RHVoice 的建構呼叫刪除這個參數。
4. **`get_segment_drain_support` 簽名一致**：eSpeak 改為 `(self, *, nvda_version: str, audio_mode: str) -> DrainSupport`（keyword-only 必填）。RHVoice 在 9c 處理。呼叫端（`completionPolicies`）一律以 keyword 傳入。
5. **eSpeak 的 `InnerPort`**：新增 `_EspeakPort`，列出並集中 wrapper 對 NVDA `synthDrivers._espeak` 私有模組的所有存取：
   - 換掉 `player`、`espeakDLL`；
   - 設定 `onIndexReached`、`isSpeaking`；
   - 呼叫 `_execWhenDone`。

   wrapper 其餘程式不再出現 `_espeak.`（守門測試）。NVDA 的 `_espeak.terminate()` 會把 `player`、`espeakDLL`、`onIndexReached` 設回 None，wrapper 不需另外還原；這點寫在類別說明中。
6. **契約測試新增兩個情境**（`tests/test_engine_segment_contract.py`，六家）：
   - **terminated 後一般 speak**：`terminate()` 後呼叫 `speak(("hello",))` 拋 `RuntimeError`。
   - **player stop 失敗後下一個 segment**：讓下一次 player `stop()` 失敗一次，呼叫 `cancel()`（例外忽略），之後的 `speak_segment` 收到一次 `SEGMENT_FAILED`。
   - 目前做不到的引擎以 `xfail(strict=True)` 標記並寫明原因，由該引擎的子階段移除。
   - refactor.md 列出的第三個情境（一般 speak 後的 correlated speak）留到 9e：只有 VE/Cerence 的 `_legacyUsed` 永久拒絕，而它有 callback 生命週期上的理由，需要在 9e 一起決定。

### 成功條件

1. 完整測試全部通過；`ruff format --check addon` 通過；`ruff check --select F401,F821`（範圍同 refactor.md 附錄）為 0。
2. `segmentHost.py` 不再出現 `getattr(self._strategy`；`fail_accepted_on_control_error` 在 addon 中不存在（守門測試）。
3. 六個 `_XStrategy` 都是 `NativeStrategy` 的子類（守門測試）。
4. eSpeak wrapper 中，`_espeak.` 只出現在 `_EspeakPort` 類別內（AST 守門測試）。
5. 新增的兩個契約情境在六家都執行；預期失敗的引擎以 strict xfail 標明原因。
6. `driver/<Engine>/driver/` 與 `driver/sonic` 無變動。

### 不在範圍內

- `StopGate`／`QueuedRecords`／`ControlFaultPolicy`、player proxy 併入 `LeasedPlayer`、其他五家的 InnerPort：只有其他五家用得到，在第一個用到的子階段（9b 起）抽出。
- strategy ↔ driver 的雙向耦合（§4.3 的 (a)/(b) 選項）：eSpeak 的 strategy 只有三行轉發，維持 weakref。
- `NativeRecord` 狀態 Enum、`ConsumerGate`：階段 10。
- 第三個契約情境：9e。

## 設計

### 1. `runtime/segmentHost.py`

```python
class NativeStrategy(ABC):
	"""What an engine supplies; everything else is the host's."""

	barriers: frozenset[str] = frozenset()

	@abstractmethod
	def submit(self, host, record, commands) -> None: ...      # 原 docstring
	@abstractmethod
	def stop_native(self, host, record) -> None: ...
	@abstractmethod
	def stop_player(self, host) -> None: ...

	def prepare(self, host, commands, operation) -> SpeechCommands:
		"""Runs outside admission before the record exists; returns what submit receives."""
		return commands

	def admission_error(self, host) -> Exception | None:
		"""Called under admission before a segment is accepted; an error rejects it."""
		return None

	def drain(self, host, record) -> None:
		"""Wait for this record's playback on the lifecycle thread (may be called repeatedly)."""
```

- `speak_segment`：`engine_error = self._strategy.admission_error(self)`。
- `enqueue`：
  - 一律 `commands = self._strategy.prepare(self, commands, operation)`，例外處理不變；
  - terminated 分支：`if operation is None: raise RuntimeError(...)`，否則取消 work 並 return。
- `wait_playback_drained`：一律呼叫 `self._strategy.drain(self, record)`，之後的錯誤與 barrier 檢查不變。
- `__init__(self, engine, strategy)`：刪除 `_fail_accepted`。
  - `latch_control_error` 一律收集 `self._accepted` 並逐一 `fail`；
  - `_deliver` 的 DRAINED → FAILED 改報不再看旗標。
- 模組說明與 `NativeStrategy` 註解同步更新。

### 2. eSpeak（`driver/Espeak/__init__.py`）

```python
class _EspeakPort:
	"""Every NVDA private the wrapper touches in synthDrivers._espeak.

	NVDA's _espeak.terminate() resets player, espeakDLL and onIndexReached to
	None, so nothing here needs restoring.
	"""

	def install(self, host, driver) -> None          # 包裝 player（LeasedPlayer）與 espeakDLL（_SegmentNative）
	def run_when_done(self, function, record) -> None  # _espeak._execWhenDone(function, record, mustBeAsync=True)
	def set_index_callback(self, callback) -> None     # _espeak.onIndexReached = callback
	def stop_player(self) -> None                      # _espeak.isSpeaking = False; _espeak.player.stop()
	def mark_not_speaking(self) -> None                # _espeak.isSpeaking = False
	@property
	def ok(self) -> int                                # _espeak.EE_OK
```

- `_SegmentNative` 改為接收 port 提供的 `EE_OK`，或在 port 內以 `_espeak.EE_OK` 建構。實作時選擇讓守門測試成立的最小改動：`_SegmentNative` 定義在 `_EspeakPort` 內作為巢狀用法，或由 port 傳入 `ok` 值。
- `_EspeakStrategy(NativeStrategy)`：
  - `submit` 使用 `driver._port.run_when_done`；
  - `stop_native` 與 `stop_player` 呼叫 `driver._port.stop_player()`。
- `SynthDriver.__init__`：`self._port = _EspeakPort()`，`super().__init__()` 之後 `self._port.install(self._segmentHost, self)`。
- `_beginSpeech` 使用 `self._port.set_index_callback(...)`；`_retireSpeech` 使用 `self._port.mark_not_speaking()`。
- `get_segment_drain_support(self, *, nvda_version: str, audio_mode: str) -> DrainSupport`。

### 3. 其他五家（只改宣告）

- `class _Sapi5Strategy(NativeStrategy)`，其餘四家同；各自 import `NativeStrategy`。
- VE、Cerence、OneCore、RHVoice 的 `SegmentHost(...)` 刪除 `fail_accepted_on_control_error=True`。

### 4. 契約測試

- 介面卡（`tests/engine_contract_harness.py`）新增：
  - `speak_ordinary(commands)`：直接呼叫 `self.core.speak(commands)`；
  - `fail_next_stop()`：讓該引擎真正的 player 下一次 `stop()` 拋 `OSError` 一次，之後恢復原行為。各家 player 的位置：
    - eSpeak：`env.player`；
    - RHVoice：`env.driver._SynthDriver__player`；
    - SAPI5：`env.player`；
    - OneCore：`env.player`；
    - VE/Cerence：`core._real_player`。
- 新測試：
  - `test_ordinary_speak_after_terminate_raises`；
  - `test_segment_after_player_stop_failure_fails`：`fail_next_stop()` → `cancel()`（`suppress(Exception)`）→ speak segment → `wait_one()` 為 `SEGMENT_FAILED`。
- 實作時先在六家執行。失敗的引擎改以 `_engines(...)` 的 strict xfail 標記，`raises=` 指定實際的斷言類型，原因寫「player stop failure is not latched by <path>」，並在 plan 的 ledger 記錄。

## 測試

1. `tests/test_segment_host.py`：
   - 原本參數化 `fail_accepted_on_control_error` 的三個測試改為只測「一律失敗」的那一支，預設分支刪除；
   - 新增 ABC 預設 hook 的單元測試（未覆寫 `prepare`/`admission_error`/`drain` 的最小 strategy 可以完成一個 segment）；
   - 新增「terminated 後 `enqueue` 一般語音拋錯、帶 operation 不拋」。
2. eSpeak 既有測試（`tests/test_espeak_segment_drain.py` 等）：
   - 原本斷言控制錯誤後 DRAINED 的，改斷言 FAILED；
   - 原本斷言 terminated 後一般 speak 靜默的，改斷言拋錯。
   - plan 逐一列出。
3. SAPI5 既有測試：同上，僅限 `fail_accepted` 的行為改變。
4. 守門測試（`tests/test_native_strategy_guards.py`）：成功條件 2、3、4。
5. 契約測試：§4。
