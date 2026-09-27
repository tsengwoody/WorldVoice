# WorldVoice Segment Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以 `WorldVoiceIndexCommand` 識別每個語音 segment 的結尾，阻擋同 core 舊回呼誤推進新段，並保留 WorldVoice 對 NVDA 的 request 完成通知。

**Architecture:** builder 在 SelectVoice、Pause 與 sequence 結尾分段；adapter 在真正播放前重編原 index 並附加內部結尾 command。IndexLedger 還原帶來源與 segment 身分的事件，scheduler 保留唯一 worker、取消與 request 狀態機；activation cache 仍使用 `(source_id, voice_key, revision)`。

**Tech Stack:** 現有 Python、dataclasses、typing.Protocol、threading、pytest、NVDA speech commands／extension points；不新增執行期套件。

**Spec:** [2026-09-27-worldvoice-segment-index-design.md](../specs/2026-09-27-worldvoice-segment-index-design.md)。使用者已於本輪同意並要求撰寫 plan；另確認標記由 adapter 附加，不在 `normalize_legacy_commands()` 插入。

基準：`dff1873`（已含 spec）；既有 `review_gpt2.md` 與 `docs/superpowers/finish_task.md` 刪除狀態不屬於本次程式實作。行號以基準為參考，修改時依函式定位。

## Global Constraints

- 「不修改 NVDA OneCore／SAPI5 原始碼，也不修改原生 DLL。」其餘 `ref/` 與內嵌底層 driver 同樣保持唯讀；必要整合只在 WorldVoice 邊界完成。
- 「保留 `_applied = (source_id, voice_key, revision)`，不加入 `segment_id`、`wire_index` 或 `epoch`。」
- 「正式 runtime 不匯入 NVDA、`IndexCommand`、compat 或具體 driver」。
- 「每個真正送入 driver 的語音 segment 尾端恰有一個此標記。」此要求適用已啟用 marker 完成模式的路徑；legacy 遷移狀態需明列。
- 「停頓 task、無效／不可用語音而被跳過的區段不建立標記。」
- 「在同一實際 notification source 的生命週期內採單調配置且不環繞重用。」
- 「完成模式於資源建立時固定，不能在一次播放漏掉 marker 後，偷偷改用任意 done 宣告成功。」
- 「保留 epoch、token、目前來源／phase、delivery lock、`_stops_in_flight` 與單一 worker 的現有保護。」
- 「bridge／ledger 的內部鎖只保護快照與狀態，不能持鎖呼叫 scheduler、NVDA 通知、driver 或 Future callback。」
- 「所有目標引擎通過前，不宣稱整項遷移完成。」Linux fake 通過與 Windows 播放時序證據分開記錄。

## Review Focus

1. 相鄰原 NVDA index 與內部結尾 marker 被 driver 略過：原 callback 仍依順序發送且不重複；Task 2、5、7。
2. 原 index 的交付被另一執行緒結尾回呼超越，或輸出 callback 重入 cancel：不得提前完成／再發舊通知；Task 4、5。
3. cancel 恰好落在映射登記前後、同 core 重新綁定或 alias 接入：不復活舊段、不重設配置器；Task 2、3、6。
4. marker 已到達但 speak 隨後拋錯，或只有 done 沒有 marker：不得成功完成；Task 5、7。
5. 長時間使用耗盡 driver 的整數空間，或整段只有控制命令／index：送出前明確失敗或可靠完成，不能碰撞／加入可聽字元／永久假裝成功；Task 1、2、7、8。

---

## 檔案與責任

下表路徑以 repository 根目錄為準；WV 代表 `addon/synthDrivers/WorldVoice`，僅供表格閱讀，實際任務列出完整路徑。

| 檔案 | 動作與責任 |
| --- | --- |
| `WV/_speechcommand.py`、`WV/compat/commands.py` | 定義 marker；normalizer 只拒絕外來內部 marker，不插入標記 |
| `WV/runtime/models.py` | 新播放 context、完成模式／能力及事件欄位 |
| `WV/indexLedger.py`（新增） | 與 NVDA command 無關的整數配置、映射、撤銷、高水位 |
| `WV/compat/indexCodec.py`（新增） | 識別 NVDA IndexCommand、複製重編、追加 WorldVoiceIndexCommand |
| `WV/compat/engineAdapter.py`、`WV/runtime/session.py` | context 傳遞、codec 呼叫、segment 清理與播放契約 |
| `WV/nvdaEventBridge.py` | 來源綁定、分批解碼輸入，保留 NVDA 對外通知 |
| `WV/runtime/scheduler.py` | segment 狀態、事件順序、完成模式、request 結束與取消 |
| `WV/compat/completionPolicies.py`（新增） | 已驗證的引擎／NVDA 版本／音訊路徑之完成能力表；未知預設 legacy |
| `WV/voiceManager.py`、`WV/__init__.py` | 一個 runtime 的 ledger 組裝與資源順序 |
| `WV/runtime/requestBuilder.py` | 原分段邏輯保持，僅必要註解；由測試鎖定邊界 |
| `tests/test_index_ledger.py`、`tests/test_index_codec.py`（新增） | 純映射與 NVDA 邊界契約 |
| `tests/test_worldvoice_index_command.py`、`tests/test_runtime_playback_context.py`（新增） | 子類別與新模型契約 |
| `tests/test_runtime_segment_completion.py`（新增） | marker 模式競態；沿用真實 TaskManager |
| `tests/test_runtime_completion_policies.py`（新增） | 未驗證引擎不啟用、能力匹配與不可中途降級 |
| 既有 runtime／bridge／composition／builder 測試及 harness | 保留既有契約，增加新模式與真實組裝案例 |
| `docs/superpowers/finish/2026-09-27-worldvoice-segment-index-validation.md`（新增） | 原始碼／fake／實機證據、各引擎進度與限制 |

不建立第二個 scheduler、設定 Store 或 UI。不要為本次重構重新排版整個檔案。

## 任務依賴與執行規則

順序：Task 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9。介面交接多，建議依序實作；不要讓多個任務同時修改 scheduler／session。

開始執行時才依 `using-git-worktrees` 建立或確認隔離工作區。執行一次 `python3 -m pytest tests -q -p no:cacheprovider` 取得本次基準；若基準失敗，先記錄並判定來源。不得收集 `ref/nvda`。本 plan 撰寫階段沒有執行測試。

每個任務的測試案例使用下列判準：先補會失敗的契約，執行限定測試確認失敗原因，再實作並確認通過。沒有新增行為的 characterization 測試可直接通過，不為了製造 RED 暫改正式程式。每個任務完成後只提交該任務列出的檔案。

---

### Task 1: 定義 command、播放身分與完成能力，鎖定分段位置

**Files:** Modify `addon/synthDrivers/WorldVoice/_speechcommand.py`、`addon/synthDrivers/WorldVoice/compat/commands.py`、`addon/synthDrivers/WorldVoice/runtime/models.py`；Test `tests/test_worldvoice_index_command.py`、`tests/test_runtime_playback_context.py`、`tests/test_legacy_speech_commands.py`、`tests/test_runtime_request_builder.py`。

**Interfaces:**

- `WorldVoiceIndexCommand(IndexCommand)`：繼承建構子；repr 為 `WorldVoiceIndexCommand(<integer>)`。
- frozen `PlaybackContext(source_id: object, segment_id: int)`。
- `CompletionMode`: `LEGACY_DONE`、`END_INDEX`、`END_INDEX_AND_DRAIN`。
- frozen `IndexRange(minimum: int, maximum: int)`：`1 <= minimum <= maximum`。
- frozen `CompletionContract(mode: CompletionMode = LEGACY_DONE, index_range: IndexRange | None = None)`：marker mode 缺 range 或 legacy 帶 range 均拒絕。能力被啟用即代表有序 index 與相應完成契約已驗證。
- `EngineCapabilities` 尾端加 `completion: CompletionContract = CompletionContract()`；保留原欄位建構相容性。
- `EventKind` 保留 INDEX／DONE，新增 SEGMENT_END／SEGMENT_DRAINED／SEGMENT_FAILED；`PlaybackEvent` 在既有 `(kind, source_id, index=None)` 後新增 `segment_id: int | None = None`、`error: Exception | None = None`，保持舊位置參數相容。

- [ ] **1. 補 command／模型失敗測試與 builder characterization。** 更新 NVDA stubs 提供真實所需的 IndexCommand、SynthCommand、SynthParamCommand，不以 AST 單獨摘出 marker 類別取代模組載入。關鍵斷言：

```python
# test_marker_is_an_index_command
marker = WorldVoiceIndexCommand(502)
assert isinstance(marker, IndexCommand)
assert marker.index == 502
assert repr(marker) == "WorldVoiceIndexCommand(502)"
# test_marker_rejects_non_integer
with pytest.raises(ValueError):
    WorldVoiceIndexCommand("502")
```

`test_normalizer_rejects_external_marker` 驗證 lazy iteration 拋 ValueError，沒有額外 marker；`test_select_pause_and_end_flush_only_nonempty_segments` 使用既有 recording_builder：輸入 `['A', SelectVoice('Fake:b'), SelectVoice('Fake:b'), 'B', Pause(0.2), 'C']`，tasks 恰為 A／B／Pause／C，各 speech commands 只有原內容。增加不可用 default、途中不可用、只含 command／index 的既有行為斷言。新模型測試確認 frozen、無效 range／contract 拒絕、舊 PlaybackEvent 建構仍可使用。

- [ ] **2. 執行上述四個檔案的限定 pytest。** 預期新型別／驗證案例先 FAIL；既有 builder characterization PASS。
- [ ] **3. 實作 Interfaces。** normalizer 在一般分支前拒絕外部 `WorldVoiceIndexCommand`；不配置編號、不附加 marker。runtime 不匯入 speech。
- [ ] **4. 再執行 Task 1 四個測試檔。** 預期全部 PASS；確認 marker 新增只在 command 模組，builder 未新增 NVDA 相依。
- [ ] **5. 提交。** Message：`feat: define segment completion context and index command`。

### Task 2: 實作來源專屬 IndexLedger

**Files:** Create `addon/synthDrivers/WorldVoice/indexLedger.py`、`tests/test_index_ledger.py`。

**Interfaces:** 消費 Task 1 的 context／range／event；本模組只依賴標準庫與 runtime models。

- frozen `IndexAllocation(wire_indexes: tuple[int, ...], end_index: int)`。
- `IndexLedger.bind(source: object, source_id: object, contract: CompletionContract) -> None`。
- `prepare(context: PlaybackContext, original_indexes: tuple[int, ...]) -> IndexAllocation`：一次配置原 index 數量加一；尚未退休的同 context 再 prepare 應拒絕。
- `receive_index(source_id: object, wire_index: int) -> tuple[PlaybackEvent, ...]`：還原有效段、依命令順序補交前置原 index，結尾最後產生 SEGMENT_END；相同原值同段最多交付一次。
- `retire_segment(context: PlaybackContext) -> None`、`retire_source(source_id: object) -> None`、`unbind(source_id: object) -> None`、`close() -> None`：均可重複呼叫。
- `IndexSpaceExhausted(RuntimeError)`、`InvalidIndexContext(RuntimeError)`；無效綁定／重複 prepare 使用後者。

- [ ] **1. 補 fixture 與失敗測試。** fixture 建立實際 Ledger、source 物件與 context；不複製映射演算法。主要斷言：

```python
# test_terminal_marker_replays_missing_originals_before_end
ledger.bind(core, source_id, CompletionContract(END_INDEX, IndexRange(501, 510)))
allocation = ledger.prepare(PlaybackContext(source_id, 1), (123, 124))
assert allocation.wire_indexes == (501, 502)
assert allocation.end_index == 503
events = ledger.receive_index(source_id, 503)
assert [e.kind for e in events] == [INDEX, INDEX, SEGMENT_END]
assert [e.index for e in events] == [123, 124, None]
assert all(e.segment_id == 1 for e in events)
assert ledger.receive_index(source_id, 501) == ()
```

增加 `test_retired_segment_cannot_complete_new_segment`、`test_same_source_rebind_preserves_high_water`、`test_alias_same_binding_does_not_reset`、`test_equal_but_distinct_source_uses_identity`、`test_duplicate_original_index_delivered_once`、`test_empty_originals_still_allocate_terminal`、`test_unknown_large_index_does_not_advance`。`test_exhaustion_is_atomic` 使用 `IndexRange(1, 3)`：先配置 `(123,)` 得 1／2，第二段需要兩個值時拋 IndexSpaceExhausted，沒有第二段有效映射，之後單一末標記仍可取得 3。

- [ ] **2. Run:** `python3 -m pytest tests/test_index_ledger.py -q -p no:cacheprovider`。預期缺模組／契約 FAIL。
- [ ] **3. 實作 ledger。** 以物件身分及強參照保存來源；每個 source 保存 next index，高水位於 unbind 後保留到 ledger close。相同 core 不得同時綁不同 source_id；unbind 後重綁可用，但 range／mode 必須一致。退休刪除段映射，保留高水位；配置耗盡在變更前整段檢查。closed ledger 拒絕 bind／prepare，輸入事件返回空 tuple。內部鎖內不呼叫外部函式。
- [ ] **4. 重跑 Task 2 測試。** 全部 PASS；加入 weakref 觀察 close 釋放 source、unbind 仍保留高水位所需身分。不同 runtime 若要重用仍活著的同 core，必須移交既有 ledger，不能建立全新配置器；正式 owner teardown 不允許未關閉舊 core 再發布為新來源。
- [ ] **5. 提交。** Message：`feat: correlate driver indexes with speech segments`。

### Task 3: 在 adapter 播放入口編碼，session 保留 activation cache

**Files:** Create `addon/synthDrivers/WorldVoice/compat/indexCodec.py`、`tests/test_index_codec.py`；Modify `addon/synthDrivers/WorldVoice/compat/engineAdapter.py`、`addon/synthDrivers/WorldVoice/runtime/session.py`、`tests/runtime_harness.py`、`tests/test_runtime_legacy_adapter.py`、`tests/test_runtime_session.py`。

**Interfaces:**

- `encode_segment(commands: SpeechCommands, context: PlaybackContext, ledger: IndexLedger) -> SpeechCommands`：新 tuple、一般 index 新建為 IndexCommand、最後一個為 WorldVoiceIndexCommand；其他 command 保持原物件。
- `EngineAdapter.speak`／`PlaybackPort.speak`／`EngineSession.speak(commands, token, *, context: PlaybackContext | None = None) -> None`。marker 模式必須有 context；optional 僅保留既有 legacy 直接呼叫。
- `EngineAdapter.finish_segment(context: PlaybackContext) -> None`、`EngineSession.finish_segment(context) -> None`；PlaybackPort 同名。legacy adapter 轉交 ledger.retire_segment；純 native adapter 可 no-op。
- `PlaybackPort.completion: CompletionContract`；session 從 adapter capabilities 取得。LegacyEngineAdapter 建構子增加 keyword-only `index_ledger: IndexLedger | None = None`、`completion: CompletionContract = CompletionContract()`；舊參數保留。

- [ ] **1. 補失敗測試。** `test_codec_appends_one_marker_without_mutating_input`：`['hello', IndexCommand(123)]` 編碼後最後是專用 marker、原 index 不變、一般 index 重新編號；`test_codec_rejects_preexisting_internal_marker` 必須在 prepare 前拋錯。adapter fake core 在 speak 入口立刻回呼 marker，確認 ledger 先已登記。

```python
# test_cached_activation_still_speaks_two_distinct_segments
assert session.activate("Fake:a") is True
session.speak(("one",), token, context=PlaybackContext(session.source_id, 1))
assert session.activate("Fake:a") is False
session.speak(("two",), token, context=PlaybackContext(session.source_id, 2))
assert len(adapter.applied) == 1
assert [c.segment_id for c in adapter.contexts] == [1, 2]
```

補 `test_cancel_before_and_after_prepare_does_not_publish_live_segment`、`test_speak_failure_retires_mapping`、`test_finish_is_idempotent`、`test_legacy_without_context_preserves_commands`、`test_marker_mode_requires_context`；保留 token support、variant、waitfactor、A→B→A 與 source replacement 測試。

- [ ] **2. 執行 codec、legacy adapter、session 三個測試檔。** 新介面／行為先 FAIL。
- [ ] **3. 實作編碼與轉交。** encode 掃描型別與原 index 完畢後才 prepare；建構 command 失敗時 retire。adapter 僅在 marker 路徑載入 indexCodec，使原 legacy 邊界測試不因未使用的功能強制匯入 NVDA。adapter 在 prepare 前及送入 core 前檢查 token，已取消則清理並返回；core 例外也 retire。cancel 在呼叫 core 前 retire 該來源映射；成功 speak 返回時不 retire，因非同步 marker 可能尚未到。session 驗證 context.source_id 是自身身分，activation 三元組保持原樣。
- [ ] **4. 重跑限定測試。** 全部 PASS。同步 speak 期間 cancel／pause 仍能進入；不能因 context 增加而持 activation lock 執行整個 speak。測試 harness 更新所有正式 Protocol 的 fake 實作，但保留 legacy 案例。
- [ ] **5. 提交。** Message：`feat: append internal end indexes at the playback boundary`。

### Task 4: bridge 解碼與有序批次交付介面

**Files:** Modify `addon/synthDrivers/WorldVoice/nvdaEventBridge.py`、`tests/test_nvda_event_bridge.py`。

**Interfaces:**

- `NvdaEventBridge(..., index_ledger: IndexLedger | None = None)`。
- `start(handler: Callable[[PlaybackEvent], None], *, batch_handler: Callable[[Callable[[], tuple[PlaybackEvent, ...]]], None] | None = None) -> None`。
- `bind(source, source_id, *, completion: CompletionContract = CompletionContract()) -> None`。marker 綁定要求 ledger 與 batch_handler 已存在；legacy 保留原單事件路徑。
- marker index 交給 `batch_handler(load_events)`；`load_events()` 才呼叫 ledger.receive_index。呼叫此 supplier 的序列化責任由 Task 5 的 delivery lock 承擔，避免不同執行緒先解碼後逆序交付。

- [ ] **1. 補 bridge 失敗測試。** 使用真 ledger 與 recording batch_handler；`test_marker_decodes_to_segment_events` 收尾 marker 得到原 index／SEGMENT_END；`test_marker_mode_ignores_unidentified_done` 收底層 done 無 runtime 完成事件。保留 `test_same_source_event_has_no_invented_request_id`，明確限定 legacy。

```python
# test_marker_batch_is_decoded_when_consumer_serializes_it
bridge._on_index(core, allocation.end_index)
assert captured_suppliers and received == []
events = captured_suppliers[0]()
assert events[-1].kind is SEGMENT_END
assert events[-1].segment_id == context.segment_id
```

補 unbind／close 後才執行 supplier 返回空、owner/unknown source 忽略、同物件 rebind 保留高水位，以及 handler／supplier 可從別的執行緒呼叫 unbind 而不被 bridge lock 阻塞。

- [ ] **2. Run:** `python3 -m pytest tests/test_nvda_event_bridge.py -q -p no:cacheprovider`。新 marker 綁定／批次案例先 FAIL。
- [ ] **3. 實作 bridge 新分支。** handler 在 bridge lock 外呼叫；supplier 重新確認 bridge 仍開啟、原 binding 仍有效再解碼。unbind 同時撤銷 ledger binding；partial bind/start 與 close 失敗仍做其餘 cleanup。bridge 不自行讀 current segment、推進 request 或直接轉送 wire index。
- [ ] **4. 重跑 bridge 測試。** 全部 PASS；legacy 原 INDEX／DONE 輸出、owner 檢查與重複 close 維持。
- [ ] **5. 提交。** Message：`refactor: decode segment indexes at the NVDA event boundary`。

### Task 5: scheduler 以 segment 事件完成，保留取消與 request 通知

**Files:** Modify `addon/synthDrivers/WorldVoice/runtime/scheduler.py`、`tests/runtime_harness.py`、`tests/test_runtime_scheduler.py`；Create `tests/test_runtime_segment_completion.py`。

**Interfaces:**

- `TaskManager.on_events(load_events: Callable[[], tuple[PlaybackEvent, ...]]) -> None`：在 delivery lock 下取得事件批次並依序處理；supplier 與 output 均不在 state lock 內執行。`on_event(event)` 委派單元素批次。
- 每個 speech task 建立唯一 segment_id；執行時綁定 source 成 `PlaybackContext`，讀取一次 completion contract，設定 `awaiting_completion` 後呼叫 `playback.speak(..., context=context)`。
- task 狀態保存 end_seen／drain_seen／error／context／completion；Future、remaining、done_sent 仍由現有 request 路徑負責。以目前 `_current_done_event` 作喚醒事件可保留名稱，但喚醒不等於成功。
- worker finally 在鎖外呼叫 `playback.finish_segment(context)`；清理失敗記錄並確保 Future／remaining 仍可收尾。

- [ ] **1. 建立 marker port fixture 與失敗測試。** 擴充 FakePlayback：記錄 contexts、finish 呼叫，completion 可注入；以 `Event`／`Barrier` 控制時序，禁止 sleep 猜測。

| 測試名稱 | 場景與必要斷言 |
| --- | --- |
| `test_same_source_late_events_do_not_finish_next_segment` | A 取消後 B 起播；送 A 的 INDEX／END／DRAIN／FAILED 與無 ID DONE；`assert not future_b.done()`、`assert output.indexes == []`；B END 才完成 |
| `test_duplicate_end_cannot_advance_next_task` | 同 request 前段 END 重複送至後段；後段仍 pending |
| `test_end_then_speak_error_is_failure` | speak 同步 END 後拋 ValueError；`assert request.state is FAILED`，後段取消 |
| `test_end_waits_for_speak_return` | END 後阻塞 speak；`assert not next_port.entered.is_set()` |
| `test_done_without_end_is_not_success` | marker mode 只送 DONE；Future pending，manager.cancel 可結束等待 |
| `test_end_and_drain_require_same_segment` | END_INDEX_AND_DRAIN 的任一旗標單獨都不完成，順序可互換，錯段 DRAIN 無效 |
| `test_index_delivery_precedes_terminal_batch` | 原 index output 暫停時另一執行緒送 END supplier；原 output 返回前 next task 不起播 |
| `test_index_callback_cancels_remaining_batch` | 第一個原 index output 內取消，批次剩下 INDEX／END 都不交付；`assert output.indexes == [123]`、done 0 |
| `test_missing_marker_failure_releases_request_once` | 真來源 SEGMENT_FAILED，request FAILED，Future 拋原 error，remaining tasks 取消，done 最多一次 |
| `test_trailing_pause_and_non_speech_done_policy` | 有 speech 的尾端 Pause 未完成前 done 0，完成後 1；empty／Pause-only 仍 0 |
| `test_finish_segment_runs_on_all_terminal_paths` | success／cancel／error／public Future.cancel 各收尾一次有效清理；重複清理安全 |

- [ ] **2. 執行 scheduler 與 segment_completion 兩個測試檔。** 舊 legacy 案例保持，新增 marker 案例先 FAIL。
- [ ] **3. 實作模式判斷與批次順序。** legacy 僅接收原契約；marker events 必須 source/segment 相符且有效。INDEX 在 delivery lock 內、state lock 外轉送；每次輸出後重查有效性，然後才處理 END。END_INDEX_AND_DRAIN 收齊旗標才喚醒成功路徑；SEGMENT_FAILED 保存 error 並喚醒，由 worker 執行失敗收尾。END 不直接 settle Future；speak 返回後再次驗證 error/token。取消仍先 token/epoch、喚醒，再於鎖外停止；不得移除 stops-in-flight。
- [ ] **4. 重跑兩個測試檔及 `tests/test_worldvoice_request_manager.py`。** 全部 PASS；同步 done 舊契約只在 legacy 測試中保留。特別檢查 Future callbacks、cancel_current、pause_current 對新 phase 的覆蓋與 output 例外不遺留等待。
- [ ] **5. 提交。** Message：`feat: complete speech segments with correlated end indexes`。

### Task 6: 正式組裝 ledger／完成能力，鎖定生命週期

**Files:** Create `addon/synthDrivers/WorldVoice/compat/completionPolicies.py`、`tests/test_runtime_completion_policies.py`；Modify `addon/synthDrivers/WorldVoice/__init__.py`、`addon/synthDrivers/WorldVoice/voiceManager.py`、`addon/synthDrivers/WorldVoice/compat/engineAdapter.py`、`tests/test_runtime_composition.py`、`tests/test_worldvoice_lifecycle.py`。

**Interfaces:**

- `get_completion_contract(engine: str, *, nvda_version: str, audio_mode: str) -> CompletionContract`：只回傳 Task 8 已驗證表中的 exact tuple，其他回傳 LEGACY_DONE；不得猜測最大整數或依是否支援 IndexCommand 直接啟用。
- `VoiceManager(..., index_ledger: IndexLedger, completion_for: Callable[[type, object], CompletionContract])`；`completion_for` 在 adapter.open 後取得實際 core 才呼叫一次，結果固定於該資源。
- `LegacyEngineAdapter.configure_completion(contract: CompletionContract) -> None`：open 後、發布 session 前呼叫一次；第二次不同值或已 speak 後重設拋 RuntimeError。Task 3 的 constructor completion 仍支援獨立測試。

- [ ] **1. 補失敗測試。** 正式 composition fixture 注入 marker contract，驗證 `test_resource_bound_before_first_encoded_speech`、`test_alias_uses_one_allocator_and_one_close`、`test_alias_conflicting_completion_contract_is_rejected`、`test_partial_bind_failure_releases_resources_without_commit`、`test_shutdown_disables_late_index_before_engine_close`。policies 測試：未知版本／engine／audio mode 全為 LEGACY_DONE；錯 range 拒絕；configure 後不能中途降級。
- [ ] **2. 執行 composition、lifecycle、completion_policies 三個檔案。** 新 injection／binding 案例先 FAIL。
- [ ] **3. 實作組裝。** SynthDriver 建立一個 IndexLedger，注入 bridge 與 manager，`bridge.start(tasks.on_event, batch_handler=tasks.on_events)`。`completion_for` 用 `versionInfo.version` 與實際 SAPI5 `useWasapi` 決定音訊鍵（`wasapi`／`legacy`；其他 engine 為 `default`），呼叫 get_completion_contract。bridge.bind 完成後才發布 session；alias 使用 owner contract 並驗證一致。shutdown 保持 worker → bridge → manager/resources 順序，最後 close ledger；初始化失敗也清理 ledger。同 core 在此 runtime unbind/rebind 保留高水位；禁止把尚活著的舊 core 配給全新空 ledger。
- [ ] **4. 重跑三個檔案。** 全部 PASS；production policy 表此時可為空，所有現有引擎仍 legacy，marker 全流程由正式 manager 的注入測試驗證。不能因此宣稱生產 F7 已完成。
- [ ] **5. 提交。** Message：`refactor: assemble segment event ownership and completion policies`。

### Task 7: 共用 adapter 契約與完整序列回歸

**Files:** Modify `tests/runtime_harness.py`、`tests/test_runtime_adapter_contract.py`、`tests/test_runtime_request_builder.py`、`tests/test_legacy_speech_commands.py`、`tests/test_runtime_composition.py`；必要時更新 `tests/test_worldvoice_cancel_wrappers.py` 的 context 相容呼叫。

**Interfaces:** native fixture 直接實作新 PlaybackContext／event 契約，legacy fixture 使用正式 codec／ledger／bridge／adapter；二者共享正式 Store、EngineSession、TaskManager，不複製完成邏輯。新增 `submit_contract_request(c, sequence, *, default_key: str) -> SpeechRequest` 測試 helper，暫時包住 `c.tasks.new_request()` 記錄正式 builder 建立的 request，完成後還原方法，回傳該 SpeechRequest；不得由 helper 手動標 completed。

- [ ] **1. 補參數化案例。** `adapter_kind in ['native', 'legacy']`；marker 完成模式與現有 legacy suite 分別標明。最少以下可檢查結果：

```python
# test_same_voice_two_segments_preserve_activation_cache
assert core.apply_count == 1
assert len(set(core.segment_ids)) == 2
assert output.done_count == 1
# test_original_indexes_round_trip_without_internal_marker_leak
assert output.indexes == [123, 124]
assert not any(i in core.internal_wire_indexes for i in output.indexes)
```

案例資料需刻意令原值與 wire 值不同，使最後一項有意義。加入 A→B→A、pending→apply→pending→discard、同 source A cancel→B→A late 回呼、無文字 commands、錯誤／耗盡不呼叫 core、同步 marker 後 output 取消。完整 sequence `'A', SelectVoice(B), 'B', Pause(0.2), 'C'` 產生三段、恰三個 marker、一個 Pause，最後只發一次 done；重複 SelectVoice 和不可用區段不增加 marker。
- [ ] **2. 執行契約、builder、normalizer、composition 四個檔案。** 新案例先 FAIL（若所有所需行為已完成，保留 characterization PASS，檢查斷言確實經過正式路徑）。
- [ ] **3. 完成 harness 接線與必要相容修正。** native 匯入禁令仍涵蓋至 teardown；只 legacy fixture 安裝 NVDA stubs。F2／F3、VE／Cerence token guard 與既有取消回歸不可藉刪測試規避。主模組新增 ledger／policies imports 須以實際模組匯入路徑驗證；不要只對 AST 摘出的類別補假 globals 就宣稱 import 正確。
- [ ] **4. Run:** `python3 -m pytest tests -q -p no:cacheprovider`。預期全部 PASS；記錄實際數量／時間，不沿用歷史 350。若失敗先修本次變更引入的問題，不收集 ref。
- [ ] **5. 提交。** Message：`test: cover segment index contracts across runtime and legacy adapters`。

### Task 8: 逐引擎取得完成證據並啟用

**Files:** Modify `addon/synthDrivers/WorldVoice/compat/completionPolicies.py`、`tests/test_runtime_completion_policies.py`；必要的 WorldVoice-only 適配位於 `addon/synthDrivers/WorldVoice/driver/OneCore/driver/__init__.py`、`addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py`、`addon/synthDrivers/WorldVoice/driver/VE/__init__.py`、`addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py`、`addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py`、`addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py`；Create `docs/superpowers/finish/2026-09-27-worldvoice-segment-index-validation.md`。

**Interfaces:** policy key 為 Task 6 的 `(engine, nvda_version, audio_mode)`，值為已驗證 CompletionContract。`END_INDEX_AND_DRAIN` 的實作若需要新增 hook，在 `compat/engineAdapter.py` 建構子增加 keyword-only `event_sink: Callable[[PlaybackEvent], None] | None = None`，由 `voiceManager.py` 注入 `self.taskManager.on_event`；這兩個檔案也納入該引擎適配的變更範圍。原始工作建立時捕捉 context，再以 `PlaybackEvent(SEGMENT_DRAINED, context.source_id, segment_id=context.segment_id)` 回報。不以全域 current 或未標識 done 包裝。無法提供可靠 hook 時保留 legacy，該引擎遷移項目維持未完成。

- [ ] **1. 建立證據表與 probe 情境。** 每列含 engine、NVDA 版本、audio mode、子類別接受性、已驗證 index 範圍、順序／相鄰略過、空文字、marker 與 speak 返回／音訊尾段時序、cancel、失敗訊號、選定 mode、原始碼位置、實機日期結果。初始全部記「未驗證」，不得以 fake 結果填實機欄。
- [ ] **2. 在 Windows 逐列執行。** OneCore；SAPI5 WASAPI／legacy 分開；VE；Cerence；RHVoice；Espeak；可取得的 external。核對已知 driver 原始碼範圍後才測安全整數邊界，至少測低值、跨 NVDA 常用 index 範圍的值及候選範圍上界；不可僅由 Python int 支援推論 DLL 支援。播放情境含短文／長文、相鄰索引、空或 command-only、連續取消重播、A→B→A、跨引擎、停頓、說全部、組態切換與 pause/resume。保留事件 trace，另確認實際音訊沒有提前切換／重疊。
- [ ] **3. 為已取得證據的每個 key 補 policy 失敗測試與最小 hook 契約，再啟用。** `test_verified_profile_selects_recorded_contract` 以報告記錄的確切 mode／range 斷言；未知鄰近版本仍 legacy。若有新 drain／failure hook，增加同步、延遲、取消後舊 hook、重複 hook 的 fixture，確保來源 context 於提交時保存。不修改 `ref/`、NVDA 原始碼或內嵌底層 driver。
- [ ] **4. 重跑受影響 policy／adapter／wrapper 契約，並重跑相同實機情境。** 一列只有「fake PASS＋實機符合該 mode」才可勾選已遷移。沒有 Windows 或特定引擎時，記錄缺少條件，保留相應勾選，不要求為了繼續其他工作而假稱已驗證。
- [ ] **5. 按已驗證的 engine/profile 分別提交。** Message 範例：`feat: enable verified OneCore segment index completion`。未驗證列只提交證據狀態，不啟用。所有內建引擎未通過前，Task 8 不能整體標完成。

### Task 9: 最終驗證、spec 覆蓋與交付紀錄

**Files:** Modify `docs/superpowers/finish/2026-09-27-worldvoice-segment-index-validation.md`、本 plan 的完成勾選；程式修正僅限前述任務範圍。

**Interfaces:** 不新增；以正式入口與 Task 8 的生產能力表驗收。

- [ ] **1. 逐項對照下方 coverage 表與所有任務輸出。** 核對每個已啟用引擎均有 policy 證據；仍 legacy 的原因／未完成項目清楚。若一項未完成，交付可描述已完成的核心工作，但不可標整體 F7 已修復。
- [ ] **2. 在最後程式變更後執行 `python3 -m pytest tests -q -p no:cacheprovider` 與 `git diff --check`。** 記錄命令、exit code、實際測試數量；Task 7 後沒有程式改動時可直接引用同一次輸出，不為報告重複跑測試。
- [ ] **3. 稽核依賴與唯一性。** 搜尋 runtime imports，確認沒有 NVDA／compat／driver；builder／normalizer 沒有附加 marker；codec 是唯一結尾 command 建立路徑；activation 三元組未摻入 segment；只有 scheduler 完成 request／對外發 done；ledger 終止後不再接收事件。將結果與 Windows 限制寫入報告。
- [ ] **4. 按執行方式安排獨立審查。** 重點是編號重用、別名來源、解碼／交付順序、失敗與尾端音訊。修正實際發現後執行受影響測試；新增程式變更後再做必要最終回歸。review 結果必須有檔案／案例依據，不能只引用本計畫的預期。
- [ ] **5. 提交交付紀錄。** Message：`docs: record segment index completion validation`。docs 被 gitignore 忽略，僅對本 plan／本報告使用精確路徑 `git add -f -- <path>`，不強制加入整個 docs 目錄。彙整實際 commits、剩餘實機項目與生產啟用範圍。

## Spec coverage 自檢

| Spec 區域／驗收 | 負責任務 |
| --- | --- |
| §1–3 既定命名、範圍、逐 adapter 遷移 | 1、6、8、9 |
| §4 activation／source／segment 分責；C13–15 | 1、3、5、7 |
| §5 runtime 邊界、context／events；D17 | 1、3、4、5、6、7 |
| §6 command、編號隔離、生命週期；A1–6 | 1、2、3、4、6、7 |
| §7 marker／drain／legacy、音訊交接 | 3、5、6、8 |
| §8 取消／例外／順序；B7–12 | 2、3、4、5、6、7 |
| §9 整筆 done、失敗政策；C16 | 5、7 |
| D18–20 實機與證據分層 | 8、9 |
| 使用者補充：SelectVoice／Pause／結尾分段，adapter 才加 marker | 1、3、7 |

## 執行交接

本輪僅撰寫 plan，不執行以上程式與測試任務。建議採 **Native／目前 session 依序實作**：多數任務共享 models、ledger、session 與 scheduler 介面，單一實作者較容易維持契約一致，最後再做一次獨立完整審查。

也可選 **Subagent-driven**：每個任務由新的實作者與審查者依序處理，逐任務把關，成本較高。無論選哪一種，Windows 與特定引擎驗證條件不足時，Task 8 的相應項目仍保持未完成；不以執行方式取代實機證據。
