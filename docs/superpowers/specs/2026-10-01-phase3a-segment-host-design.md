# 階段 3a：SegmentHost 核心與 eSpeak 遷移

日期：2026-10-01。
基準：`master`（`024835c`，含階段 0–2 與 Neural 測試修正）。分支：`phase3a-segment-host`。
狀態：對話中的範圍與設計已獲使用者確認；本文件待使用者審閱。

本文件是 [`refactor.md`](../../../refactor.md) §9 階段 3 的第一個子階段，對應 §4.4。前一階段見 [2026-10-01-phase2-lifecycle-public-api-design.md](2026-10-01-phase2-lifecycle-public-api-design.md)。

## 階段 3 的拆分（使用者已確認）

| 子階段 | 內容 |
| --- | --- |
| **3a**（本文件） | `runtime/segmentHost.py` 核心；以 eSpeak 作為第一個遷移對象 |
| 3b | RHVoice、SAPI5 遷移，修 C2 |
| 3c | OneCore 遷移 |
| 3d | VE、Cerence 遷移（兩份 wrapper 各自獨立、不共用基底），修 C3，移除契約 4 的 xfail |
| 3e | `SegmentLifecycle` 收為內部實作；決定 Neural 相關測試的去留 |

每個子階段各自 spec → plan → 實作，交付後由使用者合併，再開下一段。

## 需求與範圍

使用者要讓各引擎 wrapper 不再各自重做一套 segment 生命週期簿記（`refactor.md` §4.1、§4.2），改由共用的 `SegmentHost` 掌管流程，各引擎只提供 native 專屬的部分。3a 建立核心，並以 eSpeak 驗證設計。

已確認的決定：

1. **做法 A：host 掌管流程**。`SegmentHost` 負責共通流程與 `SegmentLifecycle` 的五個 hook；各引擎只寫 `NativeStrategy`。
2. **不需要考慮 Neural 的相容性**（3a 起）。
3. **不建 `runtime/nuanceHost.py`**。VE、Cerence 須能各自獨立安裝，不共用基底；所有引擎共用的程式碼只放在 `runtime/segmentHost.py`。
4. **3a 只支援「每段開一條 thread」的執行模式**。其他模式由 3b–3d 依需要再加。
5. **`NativeRecord` 同時涵蓋一般語音**（`operation` 為 None）。eSpeak、RHVoice、SAPI5 的一般語音與 segment 都共用同一條原生佇列與同一種紀錄。
6. **命名沿用 `runtime/` 的 snake_case**。

成功條件：

1. `runtime/segmentHost.py` 提供 `NativeRecord`、`NativeStrategy`、`SegmentHost`、`LeasedPlayer`，並有不依賴任何引擎的單元測試。
2. eSpeak wrapper 改用 `SegmentHost`，不再直接接觸 `SegmentLifecycle` 或 operation 的私有成員。
3. eSpeak 既有的 drain 測試全部通過；契約測試的 eSpeak 案例全部通過。
4. **未遷移引擎的相容性**（硬性要求）：
   - RHVoice、SAPI5、OneCore、VE、Cerence 的 wrapper 原始碼完全不改（`git diff master -- <這五個 __init__.py>` 無輸出）。
   - 這五個引擎的 drain 測試與契約測試案例照常通過；契約 4 的 VE、Cerence 仍為 xfail。
   - `SegmentLifecycle` 的公開 API 與階段 2 相同。
   - 本階段對所有引擎都有影響的改動（見「一併處理的需求」第 1–4 項）各自有測試證明不改變其他引擎的行為；測試假物件需要補 `add_callback` 時，只改測試。
5. 完整測試全部通過：基線 1277 passed、96 skipped、2 xfailed，加上本階段新增測試；xfailed 仍為 2。
6. `ruff format --check addon` 通過；內層驅動與 Neural 不變。

**不在範圍內**：

- RHVoice、SAPI5、OneCore、VE、Cerence 的遷移（3b–3d）。
- 把 `SegmentLifecycle` 收為內部實作（3e）。
- worker／inline 等其他執行模式。
- eSpeak 以外的 C1–C3 類問題修正。

## 現況：eSpeak wrapper（基準 `024835c`，497 行）

| 元件 | 角色 | 3a 之後 |
| --- | --- | --- |
| `_NativeSpeech` dataclass | 一筆 native 工作的紀錄：`work`、`operation`、`retired`、`handoff`、`producer`、`cancelled`、`closed`、`ended`、`idle_completed`、`returned`、`error`、`consumers` | 由 `NativeRecord` 取代 |
| `_SegmentPlayer` | player 代理：feed／idle 期間持有 consumer、`onDone` callback 的 thread-local 綁定、失效時再 stop、錯誤記錄 | 由 `LeasedPlayer` 取代 |
| `_SegmentNative` | 包住 `espeakDLL`：控制錯誤時略過 `espeak_ng_Cancel`／`espeak_Synth`，`espeak_Synth` 返回時標記 `returned` | 保留（eSpeak 專屬），改為對 record 標記 `"returned"` 屏障 |
| `speak_segment`、`_runSegment` | 接受、終止／控制錯誤時拒絕、開 thread、例外轉 FAILED、handoff | 由 `SegmentHost.speak_segment` 取代 |
| `submit_native`、`request_stop`、`wait_native_boundary`、`wait_native_retired`、`wait_playback_drained` | lifecycle 五個 hook | 由 `SegmentHost` 實作，委派給 `EspeakStrategy` |
| `_queueSpeech`、`_beginSpeech` | 建立紀錄、以 `_espeak._execWhenDone` 排入 begin／`speak`／retire | `EspeakStrategy.submit` 與 eSpeak 的一般語音路徑；共通部分改用 host |
| `_admitConsumer`、`_releaseConsumer`、`_recordError`、`_recordControlError` | consumer 計數與錯誤 latch | 由 host 提供 |
| `_indexFor`、`_onIndexReached` | index 綁定；`index is None` 時標記 `ended` | 保留，改為對 record 標記 `"ended"` 屏障 |
| `_retireSpeech` | FIFO 退場：關閉、等 consumer 歸零、退 producer、`retired.set`、等 `handoff`；一般語音另判斷成功或失敗 | 共通部分改用 `SegmentHost.retire`，一般語音的完成判斷保留在 eSpeak |
| `_dispatchSpeech`、`_deliverSpeech` | 一般語音完成通知（`synthDoneSpeaking`）與 segment 事件交付 | segment 交付由 host 負責；一般語音完成通知保留在 eSpeak |
| `_invalidateSpeech`、`cancel`、`terminate` | 取消所有已接受與待處理的工作 | 由 `SegmentHost.cancel`／`terminate` 提供，eSpeak 只保留 NVDA 端的 `super().cancel()`／`super().terminate()` |

## 設計

### 1. `NativeRecord`

```python
@dataclass(eq=False)
class NativeRecord:
	work: PlaybackWork | None             # 一般語音可為 None
	barriers: dict[str, bool]             # 由 strategy.barriers 初始化為全 False
	operation: SegmentOperation | None = None
	producer: ProducerLease | None = None
	retired: Event | None = None          # segment 才有
	handoff: Event | None = None          # segment 才有
	cancelled: bool = False
	closed: bool = False
	error: Exception | None = None
	consumers: int = 0

	def reach(self, name: str) -> None: ...      # 標記屏障；未知名稱拋 KeyError
	def barriers_met(self) -> bool: ...
	def is_valid(self) -> bool: ...              # not cancelled and not closed and (work is None or work.is_valid())
```

紀錄的欄位只在 host 的鎖下修改；`reach`、`error` 的寫入一律透過 host 方法，讓鎖由 host 持有。

### 2. `NativeStrategy`

```python
class NativeStrategy(Protocol):
	barriers: frozenset[str]
	def submit(self, host: "SegmentHost", record: NativeRecord, commands: SpeechCommands) -> None: ...
	def stop_native(self, host: "SegmentHost", record: NativeRecord) -> None: ...
	def stop_player(self, host: "SegmentHost") -> None: ...
```

- `submit` 把工作排進引擎的原生佇列，並安排在工作結束時呼叫 `host.retire(record)`。
- `stop_native` 停止正在執行的 native 工作（eSpeak：`_espeak.isSpeaking = False` 後停止 player）。
- `stop_player` 只停止 player，用於失效或失敗後丟棄已排入的音訊。

### 3. `SegmentHost`

```python
class SegmentHost:
	def __init__(self, engine: str, strategy: NativeStrategy): ...

	# 對 scheduler／compat 的入口
	def speak_segment(self, commands, token, *, context, on_event) -> None: ...
	def cancel(self) -> None: ...
	def terminate(self) -> None: ...
	@property
	def terminated(self) -> bool: ...
	def on_delivery_thread(self) -> bool: ...

	# 給 strategy 與 wrapper
	def new_record(self, work, operation=None) -> NativeRecord: ...
	def begin(self, record: NativeRecord) -> None: ...          # 標記為目前正在執行的紀錄
	def current(self) -> NativeRecord | None: ...
	def callback_record(self) -> NativeRecord | None: ...   # LeasedPlayer 的 onDone callback 執行期間綁定的紀錄
	@contextmanager
	def consumer(self, record: NativeRecord | None = None): ...   # 進入時 admit（失效則 yield None），離開時 release
	def reach(self, record: NativeRecord, barrier: str) -> None: ...
	def record_error(self, record: NativeRecord | None, error: Exception) -> None: ...
	def latch_control_error(self, error: Exception) -> None: ...
	@property
	def control_error(self) -> Exception | None: ...
	def retire(self, record: NativeRecord) -> bool: ...          # 回傳退場時是否仍有效
```

`SegmentHost` 自己實作 `SegmentEngineHooks`，並擁有一個 `SegmentLifecycle`：

- **`speak_segment`**：
  - 在 admission 鎖下檢查：已終止時以 `RuntimeError("<engine> driver has terminated")` 呼叫 `reject_new`；已有控制錯誤時以該錯誤 `reject_new`。
  - 否則 `accept`，在新 thread 上執行 `lifecycle.run`。
  - `run` 拋例外時，以「控制錯誤 → `error.__cause__` → `error`」的優先順序 `reject_new`，並沿用原 sink。
  - `finally` 中設定 handoff 並移除簿記。
- **交付**：segment 事件只在 token 未取消、該工作未被 host 取消、host 未終止時交付給原 sink，與 eSpeak 現況相同。
- **五個 hook**：
  - `submit_native`：建立 segment 紀錄、admit producer，呼叫 `strategy.submit`。
  - `request_stop`：標記 `cancelled`；若是目前紀錄，呼叫 `strategy.stop_native`。
  - `wait_native_boundary`：等 `retired`，有 `error` 時 `lifecycle.fail`。
  - `wait_native_retired`：不做事（consumer 歸零已在 `retire` 中保證）。
  - `wait_playback_drained`：工作已失效或有錯誤時 `strategy.stop_player()` 後返回；屏障未全部到達時 `lifecycle.fail(... "<engine> synthesis retired without its native return, end and player idle barriers")` 並 `stop_player()`。
- **`retire(record)`**：
  - 關閉紀錄，等 consumer 歸零，退掉 producer，判定是否仍有效。
  - segment：設定 `retired`，然後等 `handoff`，讓 FIFO worker 在 lifecycle 完成最後的 stop／drain 檢查前保有 player。
  - 一般語音：直接回傳是否仍有效，由 wrapper 決定完成通知。
- **`latch_control_error`**：只保留第一個控制錯誤，並讓所有待處理紀錄的 `error` 設為它（與 eSpeak `_recordControlError` 相同）。
- **`cancel`**：取消所有已接受的 operation（`lifecycle.cancel`），把所有待處理紀錄標記為 `cancelled`；一般語音紀錄另呼叫 `work.cancel()`。
- **`terminate`**（第 2 項）：
  - 冪等。
  - 依序 `cancel` 所有工作、`lifecycle.terminate()`、`lifecycle.join_delivery(1)`。
  - 在 delivery thread 上呼叫時不 join 自己。
- **鎖**：host 有自己的 admission 鎖與 condition。鎖序是「host 鎖 → lifecycle condition」，與既有 wrapper 一致；host 在持有自己的鎖時不呼叫 strategy、sink 或 player。

### 4. `LeasedPlayer`

```python
class LeasedPlayer:
	def __init__(self, host: SegmentHost, player, *, idle_barrier: str | None = "idle"): ...
	def feed(self, data, size=None, onDone=None): ...
	def idle(self): ...
	def stop(self): ...
	def __getattr__(self, name): ...      # 其餘屬性轉交真正的 player
```

- `feed`：
  - 以目前紀錄進入 `host.consumer()`，沒有有效紀錄時直接返回。
  - `onDone` 包成「重新以同一紀錄進入 consumer」的 callback，執行期間以 thread-local 綁定該紀錄。eSpeak 的 index 綁定需要這一點，host 提供 `host.callback_record()` 供 wrapper 讀取。
  - 例外時 `record_error`；離開時若紀錄已失效，再呼叫一次 `stop()`。
- `idle`：在 consumer 內呼叫真正的 `idle()`，完成後 `host.reach(record, idle_barrier)`；例外時 `record_error`。
- `stop`：失敗時 `latch_control_error` 並重新拋出。

### 5. eSpeak 遷移

- `SynthDriver.__init__` 建立 `self._segmentHost = SegmentHost("eSpeak", EspeakStrategy(self))`，並以 `LeasedPlayer(self._segmentHost, _espeak.player)` 取代 `_SegmentPlayer`。
- `speak_segment`、`cancel`、`terminate` 委派給 host。eSpeak 只保留 NVDA 端的 `super().cancel()`／`super().terminate()`，呼叫順序與現況相同。
- `EspeakStrategy`：
  - `barriers = frozenset({"returned", "ended", "idle"})`。
  - `submit`：`_execWhenDone(begin)`、`super().speak(commands)`、`_execWhenDone(retire)`。begin 時 `host.begin(record)` 並綁定 index callback；retire 時 `host.retire(record)`。
  - `stop_native`、`stop_player`：`_espeak.isSpeaking = False` 後停止 player。
- `_SegmentNative` 保留；`espeak_Synth` 返回時 `host.reach(record, "returned")`，例外時 `host.record_error`。
- index callback：`index is None` 時 `host.reach(record, "ended")`，否則交給 NVDA 原本的 `_onIndexReached`。
- 一般語音（`speak()`）：以 `host.new_record(None)` 建立紀錄，走同一條 FIFO。退場時依 `host.retire()` 的結果與屏障判斷成功或失敗，維持現有的 `synthDoneSpeaking` 行為。
- 完成後 eSpeak 不得出現 `_segmentLifecycle`；`tests/test_lifecycle_private_access.py` 加入此檢查，只套用到已遷移的 wrapper。

### 6. 一併處理的需求

前四項會影響所有引擎，各自需要測試證明不改變未遷移引擎的行為：

1. **`PlaybackWork._terminate` 也觸發 `on_cancel`**（第 4 項）：`fail`／`complete_drained` 讓工作失效後，喚醒排隊中的 `run()`。
2. **入口檢查 token**（第 5 項）：`EngineSession.speak` 收到沒有 `add_callback` 的 token 時拋出 `TypeError`，訊息指出需要 `CancellationView.add_callback`。測試中傳入 `SimpleNamespace(is_cancelled=...)` 的地方補上 `add_callback`。
3. **`CancellationToken` 移除語意**：`cancel()` 在呼叫每個回呼前，於鎖內確認它仍已註冊，讓「移除後不再被呼叫」成立。
4. **守門正規式擴充**：
   - 補上 `self._lifecycle._x`（以 `(?<![A-Za-z0-9])_lifecycle` 比對）。
   - 補上對 operation／lifecycle 的 `getattr(..., "_x")`。
   - 已遷移的 wrapper 不得出現 `_segmentLifecycle`。
   - 未遷移的五個 wrapper 在擴充後仍須通過（基準上已確認沒有命中）。
5. **鎖序 docstring**：`segmentLifecycle.py` 補上「lifecycle condition → token 鎖／`PlaybackWork` 鎖（leaf）」這條允許的方向。
6. **`EventToken.add_callback`**：改為完整實作語意（註冊、取消時呼叫、可移除），不再是空殼。

## 測試

- **`tests/test_segment_host.py`**：以假 strategy、假 player 直接測 host，不依賴任何引擎。
  - 涵蓋：`speak_segment` 的 accept、拒絕（終止、控制錯誤）與例外轉 FAILED；屏障齊全才 DRAINED、缺屏障時 FAILED 並 `stop_player`；`retire` 等 consumer 歸零與 handoff；`cancel` 讓已接受的 segment 保持沉默；`terminate` 冪等且不在 delivery thread 上自我 join；`latch_control_error` 只保留第一個；`LeasedPlayer` 的 feed／idle／stop 行為與 `onDone` 綁定。
- **eSpeak**：`tests/test_espeak_segment_drain.py` 全部通過。只有在測試直接讀取 eSpeak 已移除的私有實作時，才改為透過 host 讀取，並在 plan 中逐一列出。
- **契約**：`tests/test_engine_segment_contract.py` 的 eSpeak 四個案例通過；eSpeak adapter 的 `on_delivery_thread` 改為委派給 host。
- **影響所有引擎的改動**：第 1–4 項各自有單元測試，加上未遷移五個引擎的完整 drain 測試與契約測試照常通過。
- **變異證明**：每個新的 host 行為測試，至少以一次暫時的 production 變異證明它能失敗。

## 驗收

- `python3 -m pytest tests -q`：全部通過；skipped 96、xfailed 2。
- `git diff master --stat -- addon/synthDrivers/WorldVoice/driver/{RHVoice,SAPI5,OneCore,VE,Cerence}/__init__.py`：無輸出。
- `grep -n "_segmentLifecycle" addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py`：無輸出。
- `ruff format --check addon`：通過；`git diff master --stat -- 'addon/synthDrivers/WorldVoice/driver/*/driver'`：無輸出；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural`：無輸出。
