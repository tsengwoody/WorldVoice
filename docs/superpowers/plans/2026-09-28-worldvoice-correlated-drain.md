# WorldVoice 四引擎 Correlated DRAIN Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** OneCore、Neural、VE、Cerence 在該 segment 音訊確實排空後，發出帶有原始 source_id／segment_id 的完成事件，安全推進 WorldVoice 語音分段。

**Architecture:** 延續現有 runtime／adapter／bridge／IndexLedger，新增獨立 DRAIN 模式。四個外層 driver 子類別捕捉 PlaybackContext 與 native 工作身分；一般 index 沿用 wire 映射，DRAIN 不追加 WorldVoiceIndexCommand。成功通知必須經真正的播放器屏障及取消／失敗檢查，再於既有事件批次序列中交付。

**Tech Stack:** Python、pytest、threading／concurrent.futures、NVDA OneCore／WavePlayer、ctypes（VE／Cerence）、CFFI Embedded Speech SDK（Neural）、SCons。

**Spec:** [2026-09-28-worldvoice-correlated-drain-design.md](../specs/2026-09-28-worldvoice-correlated-drain-design.md)，使用者已要求依此撰寫 plan。

程式起點：`645ac47`，目前測試分支；產品程式基準為 `4951d39`。Neural 是使用者提供的未追蹤目錄，執行時還需要此原始快照。此 plan 僅規劃實作；新增 task 均未執行。

## Global Constraints

- 四個客製 `SynthDriver` 定義在各自外層 `driver/<engine>/__init__.py`，且 `Voice.synth_driver_class = SynthDriver`；不修改內層 driver、NVDA source 或 native DLL。
- 獨立 `DRAIN` 只以本段 `SEGMENT_DRAINED` 成功完成；保留 `LEGACY_DONE`、`END_INDEX`、`END_INDEX_AND_DRAIN` 的既有契約。
- wire 範圍 **1..9999，含兩端**；DRAIN 僅重編原始 index，沒有 index 不消耗 wire 值，live source 的 wire 值不重用。
- context 必須在工作建立／native 提交時捕捉；禁止從目前 scheduler task 回推舊回呼的身分。
- `source_id` 以物件身分比較；`activate()` 保留 `(source_id, voice_key, revision)`，segment 不加入設定快取鍵。
- callback／feed／播放器等待／native stop／terminate 及事件交付不持有彼此需要的狀態鎖；取消解除等待後不得報成功。
- SDK 回呼結束契約未確認時，目標 wrapper 在播放前固定選 legacy，不落入強制 END_INDEX，也不在播放中換完成策略。
- VE／Cerence 的 `CancellableSynthDriver` 保留為新類別的 alias，維持既有取消、切塊、Sonic、variant／waitfactor 行為。
- SAPI5／Espeak／RHVoice 保留本測試分支的實驗 END_INDEX；四個 DRAIN wrapper 不證明 SAPI5 或混合模式已安全排空。
- 不為每段重建合成器、不新增 UI 開關或固定延遲猜測排空。
- 最終 `docs/superpowers/finish_task.md` 包含新增 commit list、測試／封裝結果與實機驗證界線。

## Review Focus

以下五項是除正常流程外最容易傷害實際使用的情況；各自的測試列於負責 task。

1. 取消發生在最後一次有效性檢查與 real feed 之間：下一工作啟動前，舊 feed 必須退出且舊播放已停止（Tasks 3、5–8）。
2. 部分 index handler 重入取消或 unbind：同批次剩餘 index／drain 不得成功交付；再綁定後的舊 sink 仍失效（Task 4）。
3. 暫停時仍在排空或空白／只有 index 的 segment：pause 不算完成，resume 後才繼續；真正無音訊與 native 合成失敗要區分（Tasks 5–8、10）。
4. LangChange 切換 actual native synth，取消時 self._voice 已改變：停止保存的 active synth，所有子工作仍屬原 context（Tasks 6–8）。
5. SDK 版本不符、callback 安裝部分失敗或只有方法名稱吻合：不能啟用 DRAIN；還原資源並保留明確 fallback 原因（Tasks 5–9）。

## 執行方式、檔案責任與相依順序

本次依使用者要求直接撰寫 plan，不派遣 plan reviewer。實作階段仍沿用 spec 的 Subagent-Driven：每 task 由 `gpt-6-sol high` 實作，獨立 `gpt-6-astra high` 檢查 spec 符合性與程式品質；main agent 核對結果，有問題交回實作者修正並重新 review，通過才推進下一個 task。

每項產品 task 都有 red → green → commit 的檢查點。時間順序測試使用 Event／Condition 與可控制的 fake，不以 sleep 猜時序。測試匯入真實 wrapper Python 方法，替換 native DLL／SDK 邊界；不得用假 wrapper 取代受測產品程式。

執行前依 using-git-worktrees 建立隔離分支；只把 Neural 明確目錄的原始快照複製至隔離工作區，記錄相對路徑、大小及 SHA-256，不改來源。Neural baseline 未追蹤不能由 git checkout 自動取得；本案修改／提交採明確路徑清單，禁止 `git add addon/` 將使用者資料或 DLL 一併提交。其內層原始檔與 DLL 在測試套件中仍須來自記錄的快照。

下文 `WV` 一律代表 `addon/synthDrivers/WorldVoice`；task 的 `Files` 用此前綴對應真實路徑。

| 檔案／單位 | 責任 | Task |
| --- | --- | --- |
| `WV/runtime/models.py`、`scheduler.py`、`session.py` | DRAIN 值、事件型別、完成狀態 | 1 |
| `WV/indexLedger.py`、`compat/indexCodec.py` | DRAIN 一般 index 配置／批次完成 | 2 |
| 新增 `WV/runtime/playbackWork.py` | 不依賴 NVDA 的工作有效性、失敗鎖存、callback admission | 3 |
| `WV/nvdaEventBridge.py`、`compat/engineAdapter.py`、`voiceManager.py` | binding-scoped sink 與 segment 呼叫介面 | 4 |
| 各 engine 外層 `__init__.py` | 真正的 native 歸屬、callback、播放器屏障 | 5–8 |
| `WV/compat/completionPolicies.py`、`WV/__init__.py` | 已連接且相容的四個 wrapper 選 DRAIN | 9 |
| tests／readme／validation／finish_task | 整合、測試套件、驗證與交付紀錄 | 10–11 |

Tasks 1 → 2 → 3 → 4；Tasks 5–8 都依賴 1–4；Task 8 同時沿用 Task 7 的既有 guard 相容介面；9 → 10 → 11。wrapper tasks 可在各自檔案獨立實作，但同一 shared helper 或測試 harness 的修改必須序列化。

---

### Task 1: 定義 DRAIN 模式與 scheduler 完成契約

**Files:** Modify `WV/runtime/models.py`、`WV/runtime/scheduler.py`、`WV/runtime/session.py`；Test `tests/test_runtime_segment_completion.py`、`tests/test_runtime_playback_context.py`、`tests/test_runtime_session.py`。

**Interfaces:**
- 新增 `CompletionMode.DRAIN = "drain"`；DRAIN 的 CompletionContract 要求 IndexRange，legacy 仍禁止 range。
- 在 models 定義 `SegmentEventSink = Callable[[PlaybackEvent], None]`，後續 wrapper／bridge 共用。
- 延續 `EngineSession.speak(commands, token, *, context=None)`；所有非 legacy 要求 context，錯 source 拒絕。
- DRAIN 的 `_completion_ready_locked(task)` 只檢查 drain_seen；收到成功 drain 後拒絕後續 INDEX，保留原有错误／取消優先次序。

- [ ] **1. 寫模式測試。** 在既有測試檔沿用 `marker/start/emit` helper，新增以下情境，並測錯 source／segment、重複 drain、drain 後晚到 index、drain 先同步發出而 speak 後續丟例外。

```python
def test_drain_needs_matching_drain_not_end_or_done(manager, rt):
    port = FakePlayback(rt.models.CompletionContract(
        rt.models.CompletionMode.DRAIN, rt.models.IndexRange(1, 9999)))
    _, future = start(manager, port)
    emit(manager, rt, port, "SEGMENT_END")
    manager.on_event(rt.models.PlaybackEvent(rt.models.EventKind.DONE, port.source_id))
    assert not future.done()
    emit(manager, rt, port, "SEGMENT_DRAINED")
    assert future.result(1) is True
```

- [ ] **2. Red。** Run `python3 -m pytest tests/test_runtime_segment_completion.py tests/test_runtime_playback_context.py tests/test_runtime_session.py -q -p no:cacheprovider`；預期新 DRAIN 測試因缺少 mode／完成行為失敗，不能是測試匯入錯誤。
- [ ] **3. 實作契約。** 保留 AND 模式兩種事件順序；DRAIN 的 completed 判斷也用於 INDEX 接受邊界。將 session 的 marker-only 訊息更新為符合所有非 legacy 的語意，不改 activation key。
- [ ] **4. Green。** 同一命令通過；確認原 END_INDEX／AND／legacy 測試仍通過。
- [ ] **5. Commit。** 僅 stage 本 task 檔案，commit message `feat: define correlated drain completion mode`。

### Task 2: DRAIN 的一般 index 編碼與原子完成

**Files:** Modify `WV/indexLedger.py`、`WV/compat/indexCodec.py`；Test `tests/test_index_ledger.py`、`tests/test_index_codec.py`。

**Interfaces:**
- `IndexAllocation.end_index: int | None`；`IndexLedger.prepare(context, original_indexes)` 依 binding 的 mode 配置，不讓 codec 另提供矛盾 mode。
- 新增 `IndexLedger.receive_segment_event(event: PlaybackEvent, *, binding_token: object) -> tuple[PlaybackEvent, ...]`，僅接受 DRAINED／FAILED，核對 source／segment／generation。
- `encode_segment(commands, context, ledger) -> SpeechCommands` 原 signature 保留：end_index 非 None 才追加 WorldVoiceIndexCommand。

- [ ] **1. 寫 ledger／codec 測試。** 新增 `drain_env` fixture，以新 ledger／source 綁 `CompletionContract(DRAIN, IndexRange(1, 9999))`，保存 bind 回傳 token。測一般 index 重新配置、輸入不變、缺失前置 index 補交、錯 token、重复／退休事件。

```python
def test_drain_allocation_has_no_terminal_and_empty_uses_no_wire(drain_env):
    env = drain_env
    empty = env.ledger.prepare(env.context, ())
    assert empty.wire_indexes == () and empty.end_index is None
    following = env.models.PlaybackContext(env.source_id, env.context.segment_id + 1)
    allocation = env.ledger.prepare(following, (123, 124))
    assert allocation.wire_indexes == (1, 2)
    assert allocation.end_index is None
```

- [ ] **2. Red。** Run `python3 -m pytest tests/test_index_ledger.py tests/test_index_codec.py -q -p no:cacheprovider`；預期 DRAIN bind／配置／專用事件測試失敗。
- [ ] **3. 實作配置與事件。** DRAIN 成功一次批次先交付所有未交付原始 INDEX，再交付 DRAINED，移除其 wire 映射；FAILED 不補 index。AND 的 drain-first 保留真正 terminal map，end-first 保留接受 drain 的 segment 記錄。retire／unbind／close 持續冪等。
- [ ] **4. 補端點測試並 Green。** 在 9999 已用盡後，無原始 index 的 DRAIN 仍可 prepare；一個新的原始 index 在送入 native 前失敗。測 1／9999、整段配置不足不部分發布、同 core rebind 不重用 wire、DRAIN 不附 marker且拒絕外來內部 command；同一命令通過。
- [ ] **5. Commit。** `feat: correlate ordinary indexes with drain completion`。

### Task 3: 工作生命週期與 callback admission helper

**Files:** Create `WV/runtime/playbackWork.py`、`tests/test_playback_work.py`；Modify `tests/runtime_harness.py` 的純 runtime 載入 helper。

**Interfaces:**
- 新增不可變 `DrainSupport(supported: bool, profile: str, reason: str)`；只記錄適配與 native 契約確認結果，硬體驗證狀態放 validation 文件。
- `PlaybackWork(context: PlaybackContext, token: CancellationView, on_event: SegmentEventSink)` 保存固定輸入；提供 `is_valid() -> bool`、`cancel() -> None`、`fail(error: Exception) -> bool`、`complete_drained() -> bool` 及唯讀 `error`。兩個 bool 表示是否第一次終止並發出事件；cancel 不報成功。
- `CallbackGate.begin_native(work: PlaybackWork) -> object` 產生 opaque call token；`enter_callback() -> CallbackLease | None` 捕捉該 call／work；`close(call_token) -> None` 關閉 admission；`finish_native(call_token) -> None` 由 driver 在已證實 native 不再產生 callback 時呼叫；`wait_retired(call_token) -> None` 等已進入 callback 全退出。
- `CallbackLease.work`／`.call_token` 唯讀，`.close() -> None` 釋放一次；新 begin_native 必須在前一 call finish_native 且 callback 全退出後才允許。helper 不自行推論 SDK quiescence。

- [ ] **1. 寫 helper 測試。** 使用 scheduler 的 CancellationToken 或 fixture 的同契約 token，測原 context 不變、第一個錯誤鎖存、只通知一次、token 取消後 complete 返回 False、外部 sink 重入 cancel 不互鎖。callback lease 保存舊工作，即使另一工作排隊也不重新取 context。

代表測試 `test_cancelled_work_never_reports_drain`：建立實際 PlaybackWork，呼叫 token.cancel，斷言 `work.complete_drained() is False`、`events == []`。`test_first_fault_wins`：依序 fail(first)／fail(second)，斷言 `work.error is first`、只一個帶原context的FAILED，complete返回False。
- [ ] **2. Red。** Run `python3 -m pytest tests/test_playback_work.py -q -p no:cacheprovider`；預期缺少 helper／介面而失敗。
- [ ] **3. 實作純 helper。** 鎖只保護狀態與計數，通知及等待外部完成不持鎖。driver 的 feed guard 採「記錄 admission → real feed 在鎖外 → 若作廢則 stop → 釋放 admission」；新 native 工作等待完整退休，舊 feed 的 finally stop 因此不會停止新段。
- [ ] **4. 競態測試與 Green。** fake 卡在 real feed 開始前取消：允許已 admission 的旧 feed 退出清理，但新工作不能進入；stop 後 feed 結束必須再次停止舊播放再釋放。callback 計數為零但 native 未 finish 仍禁止下一次 begin；native 已 finish 但有 lease 仍禁止交接。命令通過且 helper 不匯入 NVDA／native driver。
- [ ] **5. Commit。** `feat: guard segment work and native callback lifetimes`。

### Task 4: 連接 binding-scoped drain／failure 事件

**Files:** Modify `WV/nvdaEventBridge.py`、`WV/compat/engineAdapter.py`、`WV/voiceManager.py`；Test `tests/test_nvda_event_bridge.py`、`tests/test_runtime_legacy_adapter.py`、`tests/test_runtime_composition.py`、`tests/test_worldvoice_lifecycle.py`。

**Interfaces:**
- `NvdaEventBridge.segment_sink(source: object, context: PlaybackContext) -> SegmentEventSink` 捕捉當前 binding／ledger token，僅接收與原 context 相符的 DRAINED／FAILED。
- `LegacyEngineAdapter.configure_segment_events(factory: Callable[[PlaybackContext], SegmentEventSink]) -> None` 在 open／configure completion／bind 後、資源發布及 speak 前設定；晚設拒絕。
- wrapper 統一入口 `speak_segment(commands: SpeechCommands, token: CancellationView, *, context: PlaybackContext, on_event: SegmentEventSink) -> None`；adapter 在 DRAIN／AND 使用它。END_INDEX／legacy 維持既有 speak 呼叫及 cancellationToken 相容。

- [ ] **1. 寫 adapter／bridge 測試。** fake core 記錄上述入口四個參數；驗證 context／token 原物件、重編 commands、同步 drain、失敗及取消前退休。測不相符 source／segment、sink 建立後 unbind/rebind、延遲批次執行時再驗證 generation。

代表測試 `test_old_segment_sink_drops_after_rebind`：保存舊sink，unbind後再bind同core，呼叫舊sink的相符DRAINED，斷言 `received == []` 且新request仍等待；`test_adapter_passes_original_context_to_segment_entry` 斷言記錄中的 `context is context_a`、`token is token_a`、編碼commands不含WorldVoiceIndexCommand。
- [ ] **2. Red。** Run `python3 -m pytest tests/test_nvda_event_bridge.py tests/test_runtime_legacy_adapter.py tests/test_runtime_composition.py tests/test_worldvoice_lifecycle.py -q -p no:cacheprovider`；預期專用入口／sink 缺少而失敗。
- [ ] **3. 實作橋接與組裝。** sink 不接受任意匿名 DONE；以既有 batch_handler 的 supplier 在交付鎖內呼叫 Task 2 的 receive_segment_event。VoiceManager 先 bind 再 configure factory，全部完成才公開 session；錯誤時還原 binding／resource 所有權。共享 core alias 使用 owner session，不產生重複接收端。
- [ ] **4. 重入測試與 Green。** drain 批次中的第一個補交 INDEX handler 取消／unbind，後續 drain不得完成；close 時延遲 supplier 返回空 tuple。保留 `55ab4fa` 的重入批次序列，不在橋接鎖下呼叫 handler。同一命令通過。
- [ ] **5. Commit。** `feat: bridge context-bound segment drain events`。

### Task 5: OneCore 外層 SynthDriver

**Files:** Modify `WV/driver/OneCore/__init__.py`；Create `tests/onecore_drain_harness.py`、`tests/test_onecore_segment_drain.py`；逐步更新 `docs/superpowers/finish/2026-09-28-worldvoice-correlated-drain-validation.md`。

**Interfaces:**
- `SynthDriver(BaseOneCoreSynthDriver)` 保留 language 支援；新增 Task 4 的 speak_segment。
- wrapper 提供 `get_segment_drain_support(*, nvda_version: str, audio_mode: str) -> DrainSupport`；DrainSupport 在 Task 3 的 helper 定義為不可變值 `(supported: bool, profile: str, reason: str)`。supported 只表示已確認 Python／native API 契約適配，不代表實機證書。
- `Voice.synth_driver_class = SynthDriver`；legacy speak 保留父類別介面；runtime 的 policy 在 Task 9 才啟用。

- [ ] **1. 確認 native 歸屬前提。** 記錄 ref NVDA source／helper 的版本或內容雜湊及 callback 流程：初始化固定 callback、單一 in-flight、成功及 len=0 如何退出。制定可證明相容的 profile 檢查，缺證據／API 不符回報 unsupported 與具體原因；不要猜 NVDA 所有版本相容。驗證紀錄加入此依據。
- [ ] **2. 寫 real-wrapper 測試。** harness stub NVDAHelper、converter、可控制 native response 與 WavePlayer，載入實際 outer class。測 marker 回呼先到、tail feed 完但 sync未完成仍無 drain；sync完成後 context 正確且只通知一次。測設定 tuple 不占 native job、cancel後 len=0／成功舊callback不算新段。

代表測試 `test_onecore_waits_for_tail_sync_before_drain`：等待fake `sync_entered`，斷言 `events == []`；釋放sync後，斷言唯一事件kind為DRAINED、source身分與segment值皆來自context_a。
- [ ] **3. Red。** Run `python3 -m pytest tests/test_onecore_segment_drain.py -q -p no:cacheprovider`；預期自訂入口／逐段屏障缺少而失敗。
- [ ] **4. 實作 native 工作與排空。** 覆寫必要的 queue／callback接點，在 ocSpeech_speak前保存完整 immutable job；cancel 不移除尚未被消耗的 in-flight 身分。背景 callback 完成最後 marker 後尾端 feed，再 sync，檢查 work才 complete_drained；錯誤先 fail，不能由父類別自動 processQueue重新算成功。
- [ ] **5. 競態與 Green。** len=0、WAV／marker 錯誤、可觀察 feed／sync錯誤、只有 index／break／空音訊、pause→resume、terminate、sync因stop返回、feed admission後取消、初始化不相容都覆蓋。stop可以解除等待，下一nativecall不覆寫舊job；上述命令通過。
- [ ] **6. Commit。** `feat: wrap OneCore with correlated playback drain`；明確 stage outer／harness／test／validation，validation 用 `git add -f`。

### Task 6: Neural 自有 callback、工作佇列與 native 交接

**Files:** Modify 使用者提供的 `WV/driver/Neural/__init__.py`；Create `tests/neural_drain_harness.py`、`tests/test_neural_segment_drain.py`；Modify 同一 validation 文件。內層 driver／speechapi／DLL 僅讀取及參照。

**Interfaces:**
- `SynthDriver(BaseNeuralSynthDriver)` 提供 speak_segment、get_segment_drain_support 及固定 profile 支援；`Voice.synth_driver_class = SynthDriver`。
- 外層 `_ContextualAudioCallback`／`_SegmentSpeakTask`／`_SegmentDrainTask` 使用 Task 3 的 PlaybackWork／CallbackGate；native stop helper保存 operation handle並等待完成，不修改 speechapi 全域符號。

- [ ] **1. 確認 SDK callback 結束契約。** 查同步 speak_ssml 成功／失敗、native stop completion及其audio／bookmark回呼生命週期，記錄SDK版本與依據。選擇外層可呼叫的 stop wait API、持有／釋放handle規則；「CFFI有函式」與「目前callback計數零」均不足。無契約的profile固定unsupported；不得為了讓測試啟用跳過前提。
- [ ] **2. 寫 construction／工作測試。** native stream stub保存callback原物件，確認自有callback在建構時就安裝。測LangChange多子task共享context、snapshot不受後續設定影響、最後只一個drain；Sonic尾端已feed後idle仍阻塞不報成功。

代表測試 `test_neural_stream_owns_contextual_audio_callback` 斷言各native stream保存的callback為外層自有類別，且與core使用的物件相同；`test_neural_waits_for_stop_and_callback_exit` 在stop未完成／callback lease未退出各階段斷言第二個native speak未開始，兩者及舊speak退出後才允许開始。
- [ ] **3. Red。** Run `python3 -m pytest tests/test_neural_segment_drain.py -q -p no:cacheprovider`；預期自有callback／段落task缺少而失敗。
- [ ] **4. 實作外層初始化／tasks。** 必要初始化使用WorldVoice自己的callback及基底模型發現／設定工具；每個native子task捕捉work／voice。處理及flush錯誤鎖存到work，安全返回CFFI，不呼叫會吞掉錯誤的父callback再猜成功。Sonic初始化fallback與播放途中失敗分開。全子task成功才在最終idle後complete。
- [ ] **5. 實作取消與交接。** 保存actual native synth，cancel關gate→stop播放器→發native stop；背景worker等stop完成、同步speak退出、audio／bookmark lease退出，才交接新job。舊bookmark CFFI handle保存到屏障後；新task可排隊但不能先開gate。taskexception或SDK非SynthesizingAudioComplete只fail，不讓DoneSpeakingTask覆蓋。
- [ ] **6. 故障／競態與 Green。** 注入Sonic寫入／flush、SDK非成功、task例外、CFFI bookmark晚到、cancel使用不同於self._voice的synth、callback仍在feed／stop未完成、只有index／break／無音訊、pause/resume/terminate。Gate三條件缺任一個都不交接；命令通過，內層檔案雜湊保持不變。
- [ ] **7. Commit。** `feat: wrap Neural with context-bound drain tasks`；明確加入outer及測試，不能stage整個未追蹤Neural目錄。紀錄仍需原始baseline快照才能重現。

### Task 7: VE 擴充既有取消 wrapper

**Files:** Modify `WV/driver/VE/__init__.py`、`tests/worldvoice_cancel_wrapper_harness.py`；Create `tests/test_vocalizer_segment_drain.py`（先VE參數）；Modify `tests/test_worldvoice_cancel_wrappers.py`、validation。

**Interfaces:**
- 以基底別名改為外層 `class SynthDriver(BaseSynthDriver)`，沿用既有guard／speak cancellationToken介面並新增speak_segment、get_segment_drain_support；`CancellableSynthDriver = SynthDriver`、`Voice.synth_driver_class = SynthDriver`。
- 自有 `_ContextualVECallback` 在真正PCM／Sonic／bookmark／ENDPROCESS處理中使用native-call lease，讀取VE `ulMrkId`；不修改基底module class。

- [ ] **1. 確認 ve2 native 交接與建構接點。** 記錄ProcessText2Speech退出後無新callback的支援profile契約；owned callback須在第一個voiceinstance open前安裝。Harness改成實際驗證constructor/native註冊持有ownedcallback，而非永遠直接建立原VECallback；不相容guard安装／還原分支有明確結果。
- [ ] **2. 寫VE測試。** 多文字塊／LangChange使用一個work且只通知一次；ENDPROCESS先到但real idle尚未完成無drain；idle取消略過、stop解除idle、direct cancel都不報帶ID成功。測owned callback及ulMrkId一般index。

代表測試 `test_vocalizer_endprocess_is_not_segment_drain[VE]`：送ENDPROCESS、卡住idle，斷言 `events == []`；idle釋放後唯一DRAINED具有原context。`test_cancelled_idle_cannot_complete_segment[VE]`：cancel使idle略過或返回，斷言沒有DRAINED。
- [ ] **3. Red。** Run `python3 -m pytest tests/test_vocalizer_segment_drain.py -q -k VE -p no:cacheprovider`；預期新segment／callback功能失敗。
- [ ] **4. 實作外層工作與callback。** 在既有scheduler worker同步執行；每次native chunk保存call token／instance，ENDPROCESS只flush本chunk。真正idle完成後记录本work的排空證據，再檢查取消／fault並complete，不從匿名_onIndexReached(None)猜context。Callback吞錯路徑改由owned處理器鎖存錯誤，安全返回native停止值，USERSTOP不當成功。
- [ ] **5. 回歸／競態與 Green。** 測PCM／Sonic／marker／flush錯誤、late ENDPROCESS不修改下一段buffer、callbackoutsidecall、cancel後clear阻擋、feed最後stop不停止新段、guard失敗完全還原、Sonic取消尾端丟棄與初始化fallback。Run `python3 -m pytest tests/test_vocalizer_segment_drain.py tests/test_worldvoice_cancel_wrappers.py -q -p no:cacheprovider`；所有新／既有測試通過。
- [ ] **6. Commit。** `feat: add correlated drain to VE cancellation wrapper`。

### Task 8: Cerence 保留 native 差異並加入 DRAIN

**Files:** Modify `WV/driver/Cerence/__init__.py`、`tests/test_vocalizer_segment_drain.py`、`tests/worldvoice_cancel_wrapper_harness.py`、validation。

**Interfaces:** 與Task7相同外層入口／alias；自有 `_ContextualCerenceCallback` 沿用ttsapi與Cerence型別，使用`szValue`解碼bookmark。共用Task3的生命週期，不假設VE的markerlayout。

- [ ] **1. 確認 ttsapi 契約及寫Cerence參數測試。** 記錄自身SDK版本／native退出保證；擴充所有Task7的行為案例為VE／Cerence參數化，增加szValue合法／無法解析bookmark及不同voiceinstance。

代表測試 `test_vocalizer_endprocess_is_not_segment_drain[Cerence]`、`test_cancelled_idle_cannot_complete_segment[Cerence]` 沿用Task7斷言；`test_cerence_bookmark_decode_fault_fails_work` 注入非整數szValue，斷言一次FAILED且最終idle後仍沒有DRAINED。
- [ ] **2. Red。** Run `python3 -m pytest tests/test_vocalizer_segment_drain.py -q -k Cerence -p no:cacheprovider`；預期Cerence尚未提供DRAIN而失敗。
- [ ] **3. 實作 Cerence outer subclass。** 沿用現有guard、arabic_text/chunker、variant/waitfactor；ownedcallback安裝、錯誤鎖存、native quiescence與最後idle證據按本SDK處理。保持USERSTOP取消／失敗區分及alias相同物件。
- [ ] **4. Green。** Run `python3 -m pytest tests/test_vocalizer_segment_drain.py tests/test_worldvoice_cancel_wrappers.py tests/test_f4_engine_adapters.py -q -p no:cacheprovider`；兩引擎及設定回歸通過。驗證內層driver原始碼／DLL未變。
- [ ] **5. Commit。** `feat: add correlated drain to Cerence wrapper`。

### Task 9: Policy 啟用、支援檢查與安全 fallback

**Files:** Modify `WV/compat/completionPolicies.py`、`WV/__init__.py`、必要的 `WV/voiceManager.py`；Test `tests/test_runtime_completion_policies.py`、`tests/test_runtime_composition.py`、`tests/test_worldvoice_lifecycle.py`；Modify `readme.md`。

**Interfaces:** `get_completion_contract(engine, *, nvda_version, audio_mode, segment_drain_supported: bool = False) -> CompletionContract`；composition在core open後確認實際core為該Voice的客製類別、segment入口符合Task4介面，且get_segment_drain_support回傳supported，才傳True。此時只是選擇待組裝的contract；接著configure completion、bind、configure事件factory，全部成功後才發布可播放session，避免要求先有binding才能選擇binding所需的contract。

- [ ] **1. 寫policy矩陣。** 四個目標engine支援=True選`CompletionContract(DRAIN, IndexRange(1, 9999))`；False選legacy，優先於強制END_INDEX。SAPI5／Espeak／RHVoice保留END_INDEX；unknown／external即使True也不選DRAIN。版本／音訊mode參數仍傳入wrapper相容檢查，synthetic輸入不作為已支援版本證據。

代表測試 `test_target_without_drain_support_never_uses_test_index_override` 以四engine參數化，斷言 `contract.mode is LEGACY_DONE`、`contract.index_range is None`；`test_supported_target_uses_drain_range` 斷言mode為DRAIN、range等於IndexRange(1,9999)。
- [ ] **2. Red。** Run `python3 -m pytest tests/test_runtime_completion_policies.py tests/test_runtime_composition.py tests/test_worldvoice_lifecycle.py -q -p no:cacheprovider`；預期尚未啟用政策的新測試失敗。
- [ ] **3. 實作組裝／priority。** 完成contract及binding／sink後才發布session；不支援profile記錄一次具體fallback原因，禁止只靠hasattr或engine字串認證。Contract在首次speak前固定，失敗初始化rollback及sharedcorealias符合既有所有權。
- [ ] **4. Green及說明。** 同一命令通過；readme標記四個wrapper的DRAIN適用條件、其餘三engine仍為實驗END_INDEX，以及native／實機證據界線。`_VERIFIED_CONTRACTS`不因fake通過而新增證書。
- [ ] **5. Commit。** `feat: select supported driver drain contracts before playback`。

### Task 10: 跨引擎整合、取消、快取及 request 完成

**Files:** Create `tests/test_runtime_drain_integration.py`；Modify必要harness、`tests/test_runtime_session.py`、`tests/test_runtime_composition.py`、validation。

**Interfaces:** 只消費已完成的models／adapter／bridge／wrapper介面；整合fixture載入真實Python組裝，native/player為可控制fake。

- [ ] **1. 寫整合測試。** 四wrapper各一正常流程及OneCore→Neural→OneCore、VE→Cerence→VE。下一段在本段tail feed完但播放器未釋放前不得進入native；放行後只開始一次。補交原始index發生在drain及requestdone前，整筆request含Pause仍只done一次。

代表測試 `test_next_engine_starts_only_after_segment_drain` 斷言第一段播放器未釋放前 `next_native.started.is_set() is False`，釋放後其call count為1；`test_cached_voice_still_has_two_segment_drains` 斷言apply count為1、contexts的segment_id不同、request done count為1。
- [ ] **2. Red。** Run `python3 -m pytest tests/test_runtime_drain_integration.py -q -p no:cacheprovider`；若產品已符合則確認测试確實卡住播放器，另測取消／舊回呼故障注入能使被破壞的屏障判斷失敗，不能只量fake事件數。
- [ ] **3. 交叉失效測試。** pause→resume、空白／index-only／break-only、cancel後同source新segment、sink跨unbind/rebind、LangChange active synth改變、設定修訂和voice切換。兩段同source/voice/revision只apply一次但兩個context、兩次drain；不相容profile從第一段便走legacy。
- [ ] **4. 修正整合問題並驗證。** 必要修正交回對應wrapper/task實作者，沿用原taskreview再驗證受影響整合。Run `python3 -m pytest tests -q -p no:cacheprovider`，預期全數通過；Run `git diff --check`，預期exit0。記錄實際測試數，不能沿用舊636作本次結果。
- [ ] **5. Commit。** `test: cover cross-engine correlated drain integration`。

### Task 11: 測試套件、Windows 驗證與完成紀錄

**Files:** Modify `readme.md`、`docs/superpowers/finish/2026-09-28-worldvoice-correlated-drain-validation.md`、`docs/superpowers/finish_task.md`；既有SCons與buildVars僅使用，不因封裝改動依賴檔案。產物不加入git。

**Interfaces:** 交付可安裝測試addon、完整source／profile證據、新增commitlist；真實Windows結果與Linux檢查分開呈現。

- [ ] **1. 封裝已驗證來源。** 用乾淨的隔離來源及記錄的Neural baseline快照，排除cache，Run `scons version=6.2-test-correlated-drain-1-9999 channel=dev`。所需SCons／Markdown放隔離環境，gettext依既有build需求；不要執行會修改翻譯檔的pot目標來完成單純套件。
- [ ] **2. 檢查產物。** 記錄`.nvda-addon`路徑／大小／SHA-256；ZIP CRC、test版manifest／devchannel、help警語、四wrapper及helper與來源逐位元組一致、Neural baseline native檔案一致，且無pycache／pyc。套件中適用profile的DRAIN選用必須對得上policy，不能只看到新class就宣称已啟用。
- [ ] **3. Windows 測試記錄。** 依spec §11矩陣記錄NVDA／音效模式／裝置／SDK及profile，四引擎各自短長語音與四組跨引擎來回、rateBoost、variant/waitfactor、快速cancel、pause/resume、index-only/break-only。記錄native提交／尾端feed／播放屏障完成／drain交付／下一段開始的context時間戳並聽測尾音。VE→SAPI5→VE另列混合模式觀察。
- [ ] **4. 處理驗證界線。** 無Windows裝置時交付testpackage與可直接填入的測試表，將實機步驟保持未勾選，不宣稱排空時序已驗證。若SDK quiescence依據未建立，明列該wrapper仍是legacy且其DRAIN啟用驗收未完成，不能把fallback當四engineDRAIN完成。
- [ ] **5. 更新finish_task與commitlist。** 列`1d7ab27`、`645ac47`、本plan的commit，以及Tasks1–10實際新增commit；以`git log --reverse --format='%h %s' 4951d39..HEAD`核對，記錄測試／review／build／硬體狀態及仍在實驗END_INDEX的engine。記錄Neural baseline必備來源與雜湊，不能把原始檔未追蹤省略。
- [ ] **6. Commit交付文件。** 對docs使用明確`git add -f`，message `docs: record correlated drain implementation and validation`。文件列明commitlist截至提交前的確切HEAD；收尾文件本身的commit在最終回報另列，並附`git log --reverse --format='%h %s' 4951d39..HEAD`取得含它的完整列表，勿嘗試在commit內自嵌尚不存在的SHA。最終核對追蹤工作樹狀態、commitlist及產物hash。

## 完成判準與 handoff

每個task實作及獨立review通過，才勾選其checkbox；發現bug回到負責task修正並重跑相關驗證。Task11的Windows項目只在真正完成測試後勾選。

plan與spec一起交給實作者。runtime/helper完成代表通用協定可用；wrapper完成代表Python/native流程已實作；四個profile可啟用DRAIN還需要各自SDK契約依據。這三者在finish_task分開記錄，避免用單元測試或fallback代替尚缺的啟用證據。

本次交付的是plan；使用者已指定未來以Subagent-Driven執行及模型配置，無須重新選擇執行方式。
