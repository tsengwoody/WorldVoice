# 階段 9e：VE 與 Cerence

日期：2026-10-05。
基準：`master`（`9be155a`，9d 完成）。分支：`phase9e-vocalizer`。
狀態：依使用者要求自動執行（spec → plan → 實作 → Fable review）。使用者已決定 VE/Cerence 維持兩份手工複本，不在建置時共用本體；改以漂移測試防止兩份分歧。

本文件是 [`refactor.md`](../../../refactor.md) §9 階段 9 的最後一個子階段，對應：
- §4.1：stops 計數閘、`voices()` 覆寫、VE/Cerence 漂移；
- §4.2：第三個契約情境；
- §4.3：InnerPort；
- §4.4：未使用的 `_DONE`。

## 需求與範圍

以下每一項都在 VE 與 Cerence 兩個檔案各做一次，內容相同，不共用程式碼。

1. **`_stops` 改用 `StopGate(self._speechStateLock)`。**
   - `_stop_player`：`with self._stopGate.hold():` 包住 player stop，失敗時 latch，行為不變。
   - `cancel()`：
     - 在原本 +1 的同一個鎖區塊內呼叫 `enter()`。這一處要與 `_isSilence.set()`、清佇列、`call.admitting = False`、player-operation depth +1 同時發生，所以不改成 `hold()`。
     - `leave()` 放在 `finally`，並把 try 的起點提前到 `enter()` 之後，涵蓋 admission 內的 abandon 迴圈。以往 abandon 若拋例外，計數會卡住，與 9d 修正的 OneCore 同一類問題。
   - `pause()` 的失敗路徑：原本鎖內 +1、`finally` 中 -1，改為 `enter()`／`leave()`。
   - 讀取端的 `self._stops == 0` 改為 `self._stopGate.clear`，共 6 處：`_begin_record`、`_retire_record`、`_run_native` 兩處、`pause`、`_finish_termination`。
2. **InnerPort：`_VEPort`／`_CerencePort`**，列出 wrapper 使用的內層 vendored 驅動（`driver/VE/driver/`、`driver/Cerence/driver/`）私有名稱。
   - `INNER_PRIVATES` 共 17 個：
     - `_bgQueue`、`_bgThread`、`_ensureSonicStream`、`_feedBuf`、`_instanceCache`、`_isSilence`；
     - `_markBuf`、`_normalization`、`_pcmBuf`、`_player`、`_rateBoost`、`_resources`；
     - `_sonicEnabled`、`_sonicInitTried`、`_veCallback`、`_veCallbackHandler`、`_voice`。
   - `INNER_OVERRIDES` 為 `{"_speak", "_onIndexReached"}`。
   - 守門測試：
     - wrapper 存取的私有名稱，扣除 wrapper 自己的名稱後都在清單內。wrapper 自己的名稱包括：方法、任何 wrapper 類別的 `__init__` 中 `self.x =` 指派、類別本體的指派、`_install_guard` 中的 `self.x =` 指派。
     - 清單名稱以單字邊界存在於內層套件原始碼。
     - 覆寫清單完整。
3. **`voices()` 改為覆寫 `voiceInfoToMetadata` hook**（基底 `Voice.voices` 已逐一呼叫它）。
   - VE/Cerence 與基底的差別保留在 hook 裡：語言描述去掉 `b'…'` 外殼，`description` 用 voice id 而非 displayName。
   - 刪除各自的整段 `voices()`。
4. **刪除未使用的 `_DONE` sentinel 及其註解**（§4.4）。
5. **VE/Cerence 漂移測試**（`tests/test_vocalizer_drift.py`）。
   - 把 Cerence 檔案的 `Cerence`→`VE`、`ttsapi`→`ve2` 正規化後，與 VE 檔案逐一比對每個頂層定義，以及每個類別方法的 `ast.dump`。
   - 有差異的定義必須恰好等於允許清單：
     - `_PROFILE`；
     - `_ContextualVECallback._process`（bookmark id 來源：`ulMrkId` 對 `szValue`）；
     - `SynthDriver._callback_admission`（Cerence 的 `VE_HSAFE` isinstance 守衛）；
     - `Voice.variants`（Cerence 的 try/except）。
   - 新的分歧必須同時改兩份，或明確加入允許清單。
6. **第三個契約情境**（`tests/test_engine_segment_contract.py`）：一般 `speak` 之後的 `speak_segment`。
   - 先 `speak_ordinary(("first",))`，再 speak 一個 segment，然後最多呼叫 3 次 `complete()`，直到收到一個終結事件。
   - 預期結果寫成每家一張表：
     - VE、Cerence：`SEGMENT_FAILED`，錯誤訊息含 "Legacy"。`_legacyUsed` 永久拒絕：legacy 模式的 callback 生命週期未經證明，進入 correlated 模式不安全。
     - 其他四家：`SEGMENT_DRAINED`。
   - 這把 §4.2 的「一般 speak 後是否永久拒絕 correlated 模式」由隱性差異變成明列的契約。實際使用中，WorldVoice 依 completion 合約為每家引擎在啟動時選定一種模式，不會在執行中混用，所以永久拒絕不影響使用者。

### 評估後不採用（記錄理由）

- **`_GuardedPlayer` 併入 `LeasedPlayer`**：它以 silence gate（`_isSilence.cancelled()`）決定是否 feed，不經過 host 的 consumer admission。callback 的 admission 由 `_callback_admission` 在 native call 層處理。兩者的模型不同，強行併入要另外加 hook 繞過 consumer。
- **`ControlFaultPolicy`**：VE/Cerence 的 latch 散在 pause 失敗、drain 的 idle 失敗、native quiescence 失敗等路徑。這些路徑各有自己的 player-operation depth、pause revision、record error 處理，也不需要清佇列（`_drop_queued_speech` 只在 cancel 使用）。
- **`QueuedRecords`**：佇列是內層 BgThread 的 `_bgQueue`，裡面是 Begin/NativeTask/Retire/設定/DoneSpeaking 等 task，record 從 task 推得。

### 成功條件

1. 完整測試全部通過；`ruff format --check addon` 通過；`ruff check --select F401,F821`（範圍同 refactor.md 附錄）為 0。
2. 兩檔都不再出現 `_stops`、`_DONE`、`def voices(`（守門測試）。
3. InnerPort 守門測試在兩家都通過。
4. 漂移測試通過，允許清單恰好是上述 4 項。
5. 第三個契約情境在六家都通過，沒有 xfail。
6. `driver/<Engine>/driver/`、`driver/sonic` 無變動。

### 不在範圍內

- strategy ↔ driver 的雙向耦合（§4.3 (a)/(b)）、VE 的 21 個 instance 欄位整理：階段 10 以後再評估。
- 先前子階段延後的 minor。

## 設計

### `cancel()`（兩檔相同）

```python
	def cancel(self):
		if not self._guard_installed:
			return super().cancel()
		host = self._segmentHost
		entered = False
		try:
			with host.admission():
				with self._speechStateLock:
					if self._playerClosing:
						return
				host.cancel()
				with self._speechStateLock:
					self._isSilence.set()
					# （保留現行註解）
					self._paused = False
					self._pauseRevision += 1
					dropped = self._drop_queued_speech()
					call = self._nativeCall
					if call is not None:
						call.admitting = False
					self._stopGate.enter()
					entered = True
					self._playerLocal.depth = getattr(self._playerLocal, "depth", 0) + 1
					self._speechStateLock.notify_all()
				for record in dropped:
					host.abandon(record)
			try:
				self._real_player.stop()
			except Exception as error:
				host.latch_control_error(error)
				raise
		finally:
			if entered:
				with self._speechStateLock:
					self._stopGate.leave()
				self._retire_player_operation()
```

`_retire_player_operation` 必須在 `leave()` 之後執行（同現行），因為它可能完成 terminate，而 terminate 要等 stop 計數歸零。

### `voiceInfoToMetadata`（兩檔相同）

```python
	@classmethod
	def voiceInfoToMetadata(cls, voice):
		localeName = voice.language or "unknown"
		langDescription = languageHandler.getLanguageDescription(localeName)
		if not langDescription:
			if " - " in voice.displayName:
				langDescription = _strip_bytes_repr(voice.displayName.split(" - ", 1)[1])
			else:
				langDescription = localeName
		return {
			"id": voice.id,
			"name": getVoiceKey(cls.engine, voice.id),
			"locale": localeName,
			"language": localeName,
			"langDescription": langDescription,
			"description": "%s - %s [%s]" % (voice.id, langDescription, cls.engine),
			"engine": cls.engine,
		}
```

`_strip_bytes_repr` 是模組層函式，等同現行的巢狀 `clean`。基底 `voices()` 對 `availableVoices` 例外與未 ready 的處理與現行 VE/Cerence 相同（逐行比對過），所以可以直接刪掉自己的 `voices()`。

## 測試

1. `tests/test_engine_control.py`：不需新增，StopGate 已涵蓋。
2. `tests/test_vocalizer_segment_drain.py`（VE/Cerence 參數化）：
   - cancel 期間 abandon 拋例外時 gate 仍會釋放（新）；
   - 既有測試全部通過，並連跑 20 次。
3. `tests/test_f4_engine_adapters.py`：
   - `voices()` 的輸出與修改前相同：包含 `b'…'` 清理、description 用 id、engine 名稱；
   - 既有的 `test_voice_metadata_names_the_declaring_engine` 仍通過。
4. `tests/test_native_strategy_guards.py`：成功條件 2、3。
5. `tests/test_vocalizer_drift.py`：成功條件 4。
6. 契約測試：成功條件 5。
