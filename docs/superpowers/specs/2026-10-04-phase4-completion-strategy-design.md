# 階段 4：完成規則表（CompletionStrategy）、TaskPhase、拆分 _run_one

日期：2026-10-04。
基準：`master`（`3c9df71`，階段 3 全部完成）。分支：`phase4-completion-strategy`。
狀態：範圍與設計已獲使用者確認。

本文件是 [`refactor.md`](../../../refactor.md) §9 的階段 4，對應 §2.1（scheduler）與 §3.2（`LegacyEngineAdapter.speak`）。

## 需求與範圍

背景：「完成模式」決定一段語音何時算完成，以及引擎要怎麼被呼叫。目前同一份知識分散在多處，各自用 `CompletionMode` 比較或布林組合重新推導：
- scheduler 的 `_process_event_batch` 以 `legacy` 布林做 if-chain；`_completion_ready_locked`、`_indexes_finished_locked` 依模式分支。
- adapter 的 `speak` 以四個布林決定呼叫哪個 core 入口，前面還有五個 `raise`。
- `indexLedger.py` 又寫了一份「segment 何時結束」的判定，與 scheduler 的完成判定重複。
- `nvdaEventBridge.py`、`session.py`、`voiceManager.py` 各自問「是否走 index 關聯」「是否有 segment 事件」。

已確認的決定：

1. **方案 A（資料表版）**：
   - 每種完成模式是規則表 `RULES` 中的一列純資料（`CompletionRule`）。
   - scheduler、adapter、ledger、bridge、session 都透過讀取規則欄位的通用函式取得答案，不再各自比較 `CompletionMode`。
   - runtime 只宣告「呼叫哪一類 core 入口」，不知道 core 的存在，依賴方向不變。
2. **ledger、bridge、session、`voiceManager.py:136` 一併改用規則表**。`voiceManager.py:164` 是在「建立」contextual legacy 合約，不是在解讀合約，維持不改。
3. **分步施工**：先寫特性測試鎖定現有行為，再依序改 scheduler、adapter、其他元件。
4. **`SpeechFuture.then` 不刪**：`SpeechFuture` 仍經由相容 shim `taskManager.py` 對外公開，依 refactor.md 施工順序表，留到階段 8 與 shim 一起處理。
5. **沿用的限制**：
   - 純重構，行為不變。
   - `runtime/` 不依賴 `compat/`。
   - 不修改引擎 wrapper 與內層 driver。
   - 新增名稱用 snake_case。
   - contextual legacy 保留，去留在階段 8 決定。
   - plan 的變異步驟放在 commit 之後。

成功條件：

1. **單一知識來源**：除了下列地方，addon 內不再出現 `CompletionMode` 的成員比較（`is`、`is not`、`in`、`not in`、`==`）：
   - `runtime/completion.py`（規則表本身）；
   - `runtime/models.py`（`CompletionContract` 的合法性檢查）；
   - `compat/completionPolicies.py`（建立合約）；
   - `voiceManager.py` 的 `_resource_completion`（建立 contextual legacy 合約）。

   由守門測試強制。
2. **scheduler**：
   - `_current_phase` 改用 `TaskPhase` Enum，不再與字串比較。
   - `_run_one` 拆為 `_acquire`、`_execute`、`_settle` 三段。
   - 鎖序（delivery lock → state condition），以及「engine 呼叫、輸出、Future 結算都在 state condition 外」的規則不變。
3. **行為不變**（硬性要求）：基線 1373 passed 的測試全部不需修改即通過。只新增特性測試與守門測試。
4. **其他程式不變**：`driver/` 下的 wrapper 與內層 driver 完全不改。
5. **格式**：`ruff format --check addon` 通過；Neural 未被追蹤。

**不在範圍內**：
- `SpeechFuture.then` 與相容 shim（階段 8）。
- contextual legacy 的去留（階段 8）。
- `completionPolicies` 的反射式能力偵測（refactor.md §3.3，屬於階段 5）。

## 設計

### 1. 規則表：`runtime/completion.py`

```python
class SpeakEntry(Enum):
	SEGMENT = "segment"            # core.speak_segment(commands, token, context=, on_event=)
	LEGACY_SEGMENT = "legacy_segment"  # core.speak_legacy_segment(...)
	PLAIN = "plain"                # core.speak(commands[, cancellationToken=])

@dataclass(frozen=True)
class CompletionRule:
	correlated: bool               # 使用 index ledger、編碼 marker、需要 context
	segment_scoped: bool           # 事件須帶相同 segment_id；否則須不帶 segment_id
	end_event: EventKind | None    # 記為 end_seen 的事件
	drain_event: EventKind | None  # 記為 drain_seen 的事件；非 None 代表有 segment 事件
	fails_on_segment_failed: bool
	requires_end: bool
	requires_drain: bool
	entry: SpeakEntry
```

`RULES` 以 `(CompletionMode, legacy_contextual)` 為 key，收錄 `CompletionContract` 允許的 5 種組合：

| key | correlated | segment_scoped | end_event | drain_event | fails_on_segment_failed | requires_end | requires_drain | entry |
|---|---|---|---|---|---|---|---|---|
| (LEGACY_DONE, False) | False | False | DONE | None | False | True | False | PLAIN |
| (LEGACY_DONE, True) | False | True | DONE | None | True | True | False | LEGACY_SEGMENT |
| (END_INDEX, False) | True | True | SEGMENT_END | None | True | True | False | PLAIN |
| (END_INDEX_AND_DRAIN, False) | True | True | SEGMENT_END | SEGMENT_DRAINED | True | True | True | SEGMENT |
| (DRAIN, False) | True | True | SEGMENT_END | SEGMENT_DRAINED | True | False | True | SEGMENT |

兩個與原碼字面不同、但觀察不到差別的地方：
- **DRAIN 的 `end_event` 是 SEGMENT_END**：scheduler 原本在非 legacy 模式都會記錄 `end_seen`，DRAIN 的完成判定只是不看它。這列照實保留。
- **END_INDEX 的 `drain_event` 是 None**：原碼在 END_INDEX 收到 SEGMENT_DRAINED 時也會記錄 `drain_seen`，但 END_INDEX 的 `is_complete` 與 `indexes_finished` 都不讀 `drain_seen`，bridge 也不會為 END_INDEX 建立 segment 事件 sink（`segment_sink` 只接受 DRAIN 與 AND）。`drain_event` 同時代表「有 segment 事件」，所以 END_INDEX 必須是 None，ledger 與 bridge 的判定才會和原碼一致。特性測試會鎖定「END_INDEX 收到 SEGMENT_DRAINED 不影響完成」。

查詢介面（只讀規則欄位，不依模式分支）：
- 模組函式 `rule_for(contract) -> CompletionRule`。
  - plan 撰寫時改為只提供這個函式，不在 `CompletionContract` 加 `rule` 屬性：`completion.py` 必須 import `models.py`，反方向會形成循環 import。
  - 所有元件都呼叫 `rule_for(contract)`。
- `CompletionRule` 的方法：
  - `accepts_segment(segment_id, event_segment_id) -> bool`
  - `signal_for(kind) -> Signal | None`：回傳 `Signal.END`／`DRAIN`／`FAIL`，或 None。
    - plan 撰寫時由 `record(rule, state, event)` 改為這個方法：規則不直接改寫 scheduler 的 task 欄位，而是由 scheduler 依訊號設定 `end_seen`、`drain_seen`、`error`。
  - `is_complete(end_seen, drain_seen) -> bool`：`(end_seen or not requires_end) and (drain_seen or not requires_drain)`。
  - `indexes_finished(end_seen, drain_seen) -> bool`：`end_seen` if `requires_end` else `drain_seen`。

**行為對照**（以原碼為準，plan 的特性測試逐條鎖定）：
- scheduler `_completion_ready_locked`：
  - DRAIN → `drain_seen`；
  - END_INDEX → `end_seen`；
  - AND → `end_seen and drain_seen`；
  - legacy → `end_seen`。

  以上與 `is_complete` 一致。
- scheduler `_indexes_finished_locked`：DRAIN → `drain_seen`，其餘 → `end_seen`。與 `indexes_finished` 一致。
- scheduler 的事件篩選與記錄：
  - plain legacy：只接受不帶 segment_id 的事件；DONE 設 end_seen。
  - contextual legacy：只接受相同 segment_id；DONE 設 end_seen；SEGMENT_FAILED 設 error。
  - 非 legacy：只接受相同 segment_id；SEGMENT_END 設 end_seen；SEGMENT_DRAINED 設 drain_seen；SEGMENT_FAILED 設 error。

  非 legacy 模式不處理 DONE；legacy 模式不處理 SEGMENT_END／SEGMENT_DRAINED。這兩點都由「只看 `end_event`／`drain_event`」自然保證。
- ledger：
  - `marker = mode is not DRAIN` → `rule.requires_end`；
  - 收到結尾 marker 時 `finished = mode is END_INDEX or drain_seen` → `is_complete(rule, True, drain_seen)`；
  - 收到 drain 時，`mode is END_INDEX` 就忽略 → `not rule.requires_drain`；
  - 收到 drain 時 `finished = mode is DRAIN or end_seen` → `is_complete(rule, end_seen, True)`；
  - `bind` 的合法性 `mode in (END_INDEX, AND, DRAIN)` → `rule.correlated`。
- bridge：
  - `bind`／`unbind`／`close`／`_receive` 中的 `mode is not LEGACY_DONE` → `rule.correlated`；
  - `segment_sink` 的 `mode in (DRAIN, AND)` → `rule.drain_event is not None`。
- session：`speak` 中的 `mode is not LEGACY_DONE` → `rule.correlated`。
- `voiceManager.py:136`：`mode in (DRAIN, AND)` → `rule.drain_event is not None`。

### 2. scheduler

- `_process_event_batch` 的篩選與記錄改為 `accepts_segment` 加 `record`。INDEX 事件的處理（去重、`indexes_finished` 後忽略）屬於通用邏輯，留在 scheduler。
- `_completion_ready_locked`、`_indexes_finished_locked` 委派給 `is_complete`、`indexes_finished`。
- 新增 `TaskPhase(Enum)`：`STARTING`、`AWAITING_COMPLETION`、`FINISHING`，值用 `auto()`。`_current_phase` 的 5 處字串改用它。
- `_Task` 新增 `rule` 欄位，在讀取 `playback.completion` 的同一處以 `rule_for` 設定，合約仍然每個 segment 只讀一次。
- `_run_one` 拆成三段，原有的每一次狀態轉換、驗證與鎖外呼叫順序都保留：
  - `_acquire(task) -> bool`：等待 stop 結束、驗證、設定目前 task；
  - `_execute(task) -> bool | None`：
    - 等待單純的停頓（break）；
    - activate、登記完成事件、speak、等待；
    - 在 delivery lock 下判定結果。
    `_execute` 為了正確性需要多次進出鎖：speak 前後各驗證一次，最後在 delivery lock 下判定。這些保留，並在註解說明原因。
  - `_settle(task, result, error, failed)`：失敗時停止 playback、finish_segment、清除目前 task、`_finish_task_locked`、結算 Future、送出 done。
  - `_run_one` 只負責串接三段，以及捕捉例外並把請求標為失敗，與原碼的 `except` 區塊相同。

### 3. adapter：`LegacyEngineAdapter.speak`

- 讀取 `rule = self._completion.rule`。
- 前置檢查依欄位進行，錯誤訊息文字逐字保留（現有測試會比對）：
  - contextual legacy（`rule.entry is LEGACY_SEGMENT`）且沒有 context → `ValueError("Contextual legacy completion requires a playback context")`。
  - `rule.correlated` 且沒有 context → `ValueError("Correlated completion requires a playback context")`。
  - `rule.correlated` 且沒有 ledger → `ValueError("Marker completion requires an index ledger")`。
  - `rule.drain_event is not None` 且沒有 segment 事件 factory → `RuntimeError("Drain completion requires a segment event factory")`。
  - contextual legacy 且沒有 legacy 事件 factory → `RuntimeError("Contextual legacy completion requires a segment event factory")`。

  檢查順序與原碼相同。
- marker 編碼依 `rule.correlated`。
- 事件 sink 依 `entry` 選擇：`SEGMENT` 用 segment 事件 factory，`LEGACY_SEGMENT` 用 legacy 事件 factory。
- 最後依 `rule.entry` 查表呼叫 core。`PLAIN` 仍依 `supports_cancellation_token` 決定是否傳入 token。
- 原碼中「`legacy_contextual` 但 context 為 None」會先 raise，所以 contextual legacy 一定帶 context，規則表不需要另一列。

### 4. 測試環境：`tests/conftest.py`

各測試 harness 每次都會重新載入 `runtime.models`，而且常掛在不同的別名套件下。`runtime.completion` 若沿用前一個測試載入的模組，就會綁定舊的 `CompletionMode`／`EventKind`，查表時發生 `KeyError`。

新增 `tests/conftest.py`，其中的 autouse fixture 在每個測試開始前，從 `sys.modules` 移除所有 `runtime/completion.py` 的模組實體，讓它重新綁定當下的 `models`。正式環境只 import 一次，不受影響。

### 5. 守門測試

新增 `tests/test_completion_rules.py`。守門測試隨施工逐步加入：
- Task 3 只檢查 scheduler（以及 phase 改成 Enum）；
- Task 4 加入 adapter；
- Task 5 換成下面的全域掃描。

這樣每一步都有自己的 RED。最終包含：
- **規則表涵蓋性**：每個合法的 `CompletionContract` 組合都有規則；非法組合仍由 `CompletionContract` 拒絕。
- **規則與原碼一致**：用上表逐欄斷言 5 列的值。這同時是表的文件。
- **單一來源**：以 AST 掃描 addon，`CompletionMode.<member>` 只出現在成功條件 1 列出的允許位置。

## 測試

1. **特性測試（Task 1，重構前就必須通過）**，鎖定現有行為：
   - scheduler：對 5 種合約，各送一組事件序列（DONE、SEGMENT_END、SEGMENT_DRAINED、SEGMENT_FAILED、錯誤 segment、無 segment、INDEX 在完成前後）。斷言 future 結果、index 輸出、錯誤。
   - adapter：對 5 種合約，斷言呼叫的 core 入口、是否編碼 marker、使用哪個事件 factory、五種前置錯誤的訊息與順序。
   - ledger：既有的 `tests/test_index_ledger.py` 已逐模式涵蓋，不另寫特性測試。對應的測試：
     - END_INDEX 的結尾 marker：`test_terminal_marker_replays_missing_originals_before_end`、`test_empty_originals_still_allocate_terminal`；
     - END_INDEX 忽略 drain、接受失敗：`test_end_index_contract_rejects_drain_but_accepts_failure`；
     - DRAIN 沒有結尾 marker：`test_drain_allocation_has_no_terminal_and_empty_uses_no_wire`；
     - DRAIN 在 drain 時補發 index：`test_drain_restores_indexes_in_one_batch_before_completion`；
     - AND 的兩種到達順序：`test_and_drain_first_keeps_real_terminal_marker_mapping`、`test_and_end_first_keeps_segment_record_for_later_drain`；
     - 失敗：`test_and_failure_before_both_conditions_retires_remaining_completion`。
   - 特性測試放在 `tests/test_completion_characterization.py`：
     - 5 種合約 × 9 種事件情境的 scheduler 結果矩陣；
     - AND／DRAIN 在 end 之後的 index 行為；
     - adapter 的入口矩陣，以及 7 種前置錯誤的逐字訊息。
2. **既有測試**：1373 個全部不需修改即通過。
3. **變異證明**（commit 之後）：
   - 每改動一個元件，就改壞規則表或通用函式的一處（例如對調 DRAIN 的 `requires_end`／`requires_drain`、把 `entry` 改成 PLAIN、讓 `accepts_segment` 忽略 segment_id），對應的特性測試必須變紅。
   - 守門測試以「在 scheduler 加回一處 `CompletionMode.DRAIN` 比較」證明會變紅。

## 驗收

- `python3 -m pytest tests -q`：`1446 passed`（基線 1373，加上 59 個特性測試與 14 個規則／守門測試），沒有 skipped 或 xfailed。
- 守門測試通過：addon 內 `CompletionMode` 成員比較只出現在允許位置。
- `grep -n '"starting"\|"awaiting_completion"\|"finishing"' addon/synthDrivers/WorldVoice/runtime/scheduler.py`：無輸出。
- `git diff master --stat -- addon/synthDrivers/WorldVoice/driver`：無輸出。
- `ruff format --check addon` 通過；Neural 未被追蹤。
