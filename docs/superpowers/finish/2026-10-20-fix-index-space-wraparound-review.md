# Wire index 範圍用盡修正（cyclic reuse）Review 紀錄

日期：2026-10-20。分支：`fix/index-space-wraparound`（`master` `9a33387..a0764bc`，8 個 commit；worktree `/workspace/WorldVoice-fix-index-space`）。
依據：

- 規格 `docs/superpowers/specs/2026-10-20-fix-index-space-wraparound-design.md`（Q1 由使用者決定為選項 A：cyclic reuse）
- 計畫 `docs/superpowers/plans/2026-10-20-fix-index-space-wraparound.md`（含「Implementation notes」與 mutmut 存活表）
- 被推翻的舊設計 `docs/superpowers/specs/2026-09-27-worldvoice-segment-index-design.md` §6.2（單調配置、不環繞）

流程：

- 審閱：sub agent，模型 Fable 5.1，依 `DEVELOPMENT_WORKFLOW.md` §3.3 唯讀執行。可跑測試；突變實驗只在自己加的暫時 worktree（scratchpad 底下）進行，結束後已移除。
- 修正與複核：尚未啟動，由協調者決定。

## 第 1 輪

### 審閱者（Fable 5.1）結論

Ready to merge：**Yes**。Critical 0、Important 0、Minor 6（全部是測試強度、文件與防禦性註解，沒有行為錯誤）。

修正的核心在 `addon/synthDrivers/WorldVoice/indexLedger.py:86-106`（`_find_start`）、`:145-187`（`prepare`）與 `compat/indexCodec.py:32-36`（降級時略過 `IndexCommand`）。我逐條核對了 spec §6.1–§6.6 與 §8，並在還原修正的暫時 worktree 確認 23 個新增／改寫的測試確實失敗。

### 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 全套測試（分支，`ref` 指向主 checkout 的新 NVDA `7d25bc76e`） | `python3 -m pytest -q tests`（單程序，MemAvailable < 3 GB 即中止的 guard；從未觸發，約 8 GB） | **1740 passed、0 skipped**，46.8 s |
| hook | `prek run --all-files` | 8 個 hook 全數 Passed |
| 空白 | `git diff --check master` | 無輸出 |
| 受保護路徑 | `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 兩者皆無輸出 |
| 內層驅動、跨驅動 import | `git diff --name-only master` 中含 `driver/` 的檔案數；diff 新增行中 `import.*driver\.` | 0 個檔案；無 |
| Co-Authored-By | `git log master..HEAD --format=%b` grep | 0 |
| 可翻譯字串 | diff 中 `_(`、`pgettext`、`ngettext`、`# Translators` | 無；新 log 訊息為英文、不翻譯，與 `compat/completionPolicies.py` 等既有 runtime log 一致 |
| 新測試是否真抓得到 bug | 暫時 worktree checkout `a0764bc`，把 `indexLedger.py` 與 `compat/indexCodec.py` 還原成 `master`，跑 `test_index_ledger.py`、`test_index_codec.py`、`test_runtime_adapter_contract.py`、`test_runtime_drain_integration.py` | **23 failed、120 passed**：新增與改寫的測試全部失敗（含 `test_drain_source_keeps_allocating_after_the_range_is_used` 在第 10000 段、整合測試三引擎在第 4 個 request、兩個 property 測試），原有 120 個全數通過 |
| 自選突變（每個套在乾淨複本上，先跑 `-k property` 再跑其餘 ledger／codec 測試） | a `start = blocker + 1`；b `stop >= maximum + 1`；e `next_index = span.stop - 1`；i 重疊判斷改 `<=`；j 重疊判斷改 `stop - 1`；k 只以 `state.indexes` 當保留；l 忽略 `keep_terminal`；m 降級不清 `ordinary`；n 拿掉 codec 的過濾條件 | 九個都被整套測試抓到。property（預設 200 例）抓到 b、e、j、k、l、m、n；**a 只被單元測試抓到**（見 Minor 1）；i 讓 `_find_start` 無限迴圈，兩次 pytest 都被 600 s timeout 砍掉（等同 mutmut 的 timeout kill，見 Minor 3） |
| 突變 a 用 deep profile | 另一暫時 worktree，`HYPOTHESIS_PROFILE=deep pytest -k property_allocation -x` | 1 failed，76.6 s：20000 例找得到，200 例找不到 |
| deep profile（分支原碼） | `HYPOTHESIS_PROFILE=deep pytest tests/test_index_ledger.py tests/test_index_codec.py -k property` | 3 passed，296.7 s（計畫記 303 s） |
| mutmut 存活表 | 用 `mutmut.mutation.file_mutation.mutate_file_contents` 重新產生 mutant 原始碼對照；兩個疑點直接套用後跑 145 個相關測試 | `_pending_indexes` 「`segment.cursor = None`」145 passed：**確為等價**（整個 `max(...)` 指派被換掉，去重靠 `delivered`）。`bind` 的 `and`→`or` 116 errors：被殺。計畫表中 `bind` 9/22/28/34 的編號與我在未套 coverage 時產生的編號不同（`mutate_only_covered_lines = true` 會改變編號），但表內寫的是變更內容，對得上 |
| 降級路徑 end-to-end（spec 沒要求、計畫沒做） | 暫時 worktree 加 scratch 測試，用 `runtime_drain_integration_harness.assemble(index_range=(1, 1))` 對 OneCore／VE／Cerence 送 `("hello", Index(701), "world", Index(702))` | 三引擎皆 COMPLETED；wrapper 收到的序列沒有任何 `IndexCommand`，文字 `hello`、`world` 完整；NVDA 端依序收到 701、702 再 done；之後正常的一段仍拿到 wire 1 |
| 降級且**只有 index、沒有文字**的段（編碼後為 `()`） | 同上，送 `(Index(701), Index(702))` | OneCore：COMPLETED、701/702 再 done。VE／Cerence：不做 native 呼叫，直接走 player idle；放開 harness 的 idle barrier 後 COMPLETED、701/702 再 done。（第一次看起來卡在 SUBMITTED 是我的 scratch 沒放 barrier，非產品問題。） |
| 暫時 worktree 清理 | `git worktree list` | 只剩原有四個；scratchpad 的 `wt-revert`、`wt-mut` 已 `git worktree remove` |

Linux 上沒驗到的：Windows NVDA、實際音訊裝置、各引擎 SDK；spec §8.5 的手動項目（每引擎 say-all 跨過 10000 個 index、跨 wrap 時 Ctrl 中斷與快速方向鍵、混語言切引擎、SAPI5 legacy audio）都還沒跑。

### 正確性與 spec 逐項核對

- **搜尋與環繞**（`indexLedger.py:86-106`）：從游標出發，`stop > maximum + 1` 就跳過尾段回 `minimum`（尾段下一輪仍可用）；遇到保留區段就跳到該區段 `stop` 之後；`scanned` 精確累計已排除的起點數，所以 `while scanned < size` 恰好試完一整圈。我驗證了跳過的每個起點確實都不可行（尾段：任何 ≥ start 的起點都會跨過 maximum；blocker：任何在 `[start, blocker)` 的起點，其 run 都與該保留區段重疊，因為 `start' + count ≥ stop > span.start`）。
- **游標可能是 `maximum + 1`**（`:175-176`）：唯一讀 `next_index` 的是 `_find_start`；`count > 0` 時第一輪就被尾段分支包回 `minimum`，`count == 0` 時回傳 `maximum + 1` 只用來做空 `range`。行為與 spec §6.1 相同，但 spec 文字仍寫「becomes `minimum`」（Minor 2）。
- **minimum／maximum 邊界**：`[maximum, maximum]` 的單一 index 可用（`stop == maximum + 1` 不觸發尾段）；`size == 1` 的 END 範圍：第一段拿到 marker，第二段在前者未 retire 時正確 raise，retire 後從 `maximum + 1` 包回 `minimum`。舊測試 `test_drain_uses_both_range_endpoints_and_a_full_range_degrades` 仍確認 1 與 9999 都會被用到。
- **0 個 index**：DRAIN 空段 span 為空、不保留、游標不動（`_find_start` 的 `if not count`）；END 空段只拿 marker。
- **大於範圍的段**：`count > size` 時第一輪（最多兩次迭代）就 `scanned >= size` 回 `None`，進入降級；DRAIN 降級一定成功（`_find_start(state, 0)` 不會是 `None`），END 需要一個空 index 給 marker，否則 `IndexSpaceExhausted`，且在改動任何狀態（含 `warned`）之前 raise，原子性成立。
- **END／DRAIN／AND 完成規則**：`receive_index`／`receive_segment_event`／`_remove_indexes` 未改。AND 在 drain 先到時 `keep_terminal=True` 保住 terminal 映射，而 `span` 仍留在 `state.segments` 直到 retire，所以該區段不會被重新配出（`test_a_finished_segment_keeps_its_indexes_until_it_is_retired[END_INDEX_AND_DRAIN]` 驗證；我的突變 l 也證實測試能抓到）。
- **`receive_index` 算術**（`:211`）：`wire_index - wire_indexes[0] + 1` 依賴連續 run；run 永不跨 maximum 且 `state.indexes` 只登記 span 內的 index，所以 `wire_indexes[0]` 存在且位置正確。降級段只登記 marker，必走 terminal 分支。
- **retire_segment／retire_source／unbind／close**（`:252-288`）：都同時清 `segments`（保留）與 `indexes`（映射），兩者一致；`warned` 與 `next_index` 跨 `retire_source`／`unbind` 保留，符合 spec §6.1「rebind 不重用剛用過的 index」與 §6.5「每個 source 一次 WARNING」。
- **codec**（`compat/indexCodec.py:32-36`）：`wire_indexes` 為空時略過 `IndexCommand`，其餘命令保持同一物件與順序；`next(indexes)` 數量與 `originals` 一致，不會 `StopIteration`。`WorldVoiceIndexCommand` 仍在 `prepare` 之前被拒。
- **spec §8 測試計畫**：§8.1 的每條、§8.2 的五個改寫、§8.3 的兩個 property（以 `st.data()` 序列實作而非 `RuleBasedStateMachine`，spec 允許）、§8.4 加入 `indexCodec.py`，全部到位。`tests/runtime_harness.py` 的鏡像修改 spec 沒列，計畫有記。

### 過期 callback 與重用的安全性

- 「每個 source 同時最多一個未 retire 的段」在產品中成立：scheduler 單一 worker（`runtime/scheduler.py:479-487`），每個 task 在 `_settle` 先 `finish_segment` 才回到 `_worker` 取下一個（`:567-575`、`:489-503`）；`speak` 在 token 已取消或任何例外時自己 retire（`compat/engineAdapter.py:169-172`、`:180-188`；codec `:40-42`）。取消：`EngineAdapter.cancel` 在 `core.cancel()` **之前** `retire_source`（`engineAdapter.py:194-197`），被取消段的 index 立即解除保留，但游標已越過它們，仍要繞完一整圈才會再配出，重用距離不變。stop：走同一條 `cancel`。runtime handoff：`VoiceManager.terminate` → `bridge.unbind` → `ledger.unbind`（`voiceManager.py:145-149`、`nvdaEventBridge.py:129-136`），同一 core 重綁回同一 `_Source`，游標延續。ledger 本身每個 synth driver instance 一個（`__init__.py:210-211`）。
- 一個過期 callback 要落到重用後的新段，得同時：(1) 通過 `SegmentHost.consumer` 的「現役 record」admission（`runtime/segmentHost.py:348-360`；延遲 player callback 綁自己的 record `:683-697`、`:326-334`；eSpeak 走 lease `driver/Espeak/__init__.py:154-166`）；(2) 帶著綁定時的 ledger token（`nvdaEventBridge.py:226-240` 與 `indexLedger.py:203-204`）；(3) 通過 scheduler 的 `_accepts_events_locked` 與 `accepts_segment`（`scheduler.py:282-290`、`:327-330`；`runtime/completion.py:43-46`）；(4) 而且晚到超過一整圈（約 9990 個 index）。最壞結果：DRAIN——目前段的前幾個原始 index 提早回報（一句話內的游標提前）；END_INDEX——過期 terminal 可能提早結束目前段；AND——terminal 先到只設 `end_seen`，仍要等 drain。END 兩種模式產品未啟用（`_VERIFIED_CONTRACTS` 為空）。與 NVDA 自己對 1..9999 環繞所接受的風險同級。
- drain／failure 事件只能透過綁定了 `PlaybackContext` 的 sink 進 ledger（`nvdaEventBridge.py:142-178`），過期 wire index 無法完成或失敗一個 DRAIN 段。

### 執行緒與鎖

- ledger 鎖是葉子鎖：鎖內只有 dict 操作與純函式 `_find_start`。`prepare` 在 scheduler worker thread 執行，只取 ledger 鎖；`receive_index`／`receive_segment_event` 在 scheduler 的 `_delivery_lock` 之下（`scheduler.py:304`、bridge `load_events`）再取 ledger 鎖，順序固定 delivery → ledger，沒有反向。`retire_source`（NVDA 的 cancel 執行緒）只取 ledger 鎖。
- log 在 `with self._lock` 之外（`indexLedger.py:177-186`）；只讀不變的 `state.minimum`／`maximum` 與區域變數 `level`、`originals`，`warned` 在鎖內先更新，所以兩個執行緒同時降級也只會有一個 WARNING。測試用 handler 內檢查 `_lock.locked()` 驗證。
- cancel／terminate 與 prepare／receive 的競爭：prepare 之後 retire_source 只會讓該段的 callback 解碼成空；prepare 之前 cancel 則 `token.is_cancelled()` 擋在 codec 之前；都不會留下第二個未 retire 的段。

### Minor

| # | 項目 | 失敗情境 | 建議 |
| --- | --- | --- | --- |
| 1 | `tests/test_index_ledger.py:861-1007`（操作抽樣在 `:926-936`）：property 測試的隨機操作很少產生「wrap 之後、游標前方還有一個未 retire 的區段」。突變 `start = blocker + 1`（跳過 blocker 後的第一個空 index）在預設 200 例下 3 個 property 測試全過，deep 20000 例要 77 s 才找到；只有單元測試 `test_a_finished_segment_keeps_its_indexes_until_it_is_retired` 抓到。 | 若日後單元測試被改寫或刪除，這類 off-by-one 回歸只剩 deep profile 能抓；mutmut（200 例、derandomized）也可能漏。 | 在 `test_property_allocation_keeps_runs_disjoint_and_reports_each_original_once` 加 `@example` 或把操作分佈偏向 prepare／少 retire（例如 `("prepare",)*3 + ("retire",)`），或在模型中額外斷言「blocker 之後第一個空 index 若放得下就要被選到」。 |
| 2 | spec §6.1（`...-design.md:116`）仍寫游標「becomes `minimum`」；實作存 `maximum + 1`（`indexLedger.py:175-176`），計畫「Deviations」有記，spec 沒更新。 | 日後有人依 spec 讀 `next_index` 做診斷或測試，會看到超出範圍的值。 | 在 spec §6.1 補一句「存的值可能是 `maximum + 1`，由 `_find_start` 包回」，或在 `prepare` 直接正規化（會讓計畫中記為等價的 mutant 復活，二擇一即可）。 |
| 3 | `indexLedger.py:101-105`：迴圈的前進依賴 `blocker > start`，而這只因為重疊判斷是嚴格的 `start < span.stop`。改成 `<=` 時 `scanned += 0`、`start = blocker` 不變，`prepare` 在鎖內無限迴圈（我的突變 i：所有 ledger 測試 hang 到 timeout）。 | 行為上沒錯，但一次手滑就是整個引擎卡死在 `speak`，且持有 ledger 鎖。 | 加一行註解說明嚴格比較是終止條件，或 `assert blocker > start`。 |
| 4 | 降級且沒有文字的 DRAIN 段編碼成 `()` 送進 wrapper（`compat/indexCodec.py:32-36`）。我在 harness 上驗證 OneCore／VE／Cerence 都會 drain 並回放 index，但分支沒有測試涵蓋；eSpeak／RHVoice／SAPI5 不在整合 harness 裡。 | 某個 wrapper 若對空序列不觸發 drain，該 request 會停在 SUBMITTED 直到 NVDA 下一次 cancel。產品要 >9999 個 index 且無文字才會發生。 | 在 `test_runtime_drain_integration.py` 加一個 `index_range=(1, 1)`、只送兩個 `IndexCommand` 的案例；spec §8.5 Windows 手動項目可順便確認各引擎對空序列的行為。 |
| 5 | `tests/test_index_ledger.py:926-936`：操作序列每例最多 30 步、範圍最大 12，退休前要先繞完一圈的「重用距離」只在 `test_a_retired_index_decodes_to_nothing_until_it_is_handed_out_again`（範圍 1..3）直接驗證。 | 無直接失敗情境；只是 spec §6.1「reuse distance」沒有獨立的量化測試。 | 可加一個小測試：範圍 1..N、依序 prepare+retire，斷言 index k 第二次出現時中間恰好配出 N−1 個其他 index（尾段例外）。 |
| 6 | 計畫 mutmut 表中 `bind` 的編號（9/22/28/34）與未套 coverage 的產生順序不同（我產生的 22 是 `and`→`or`，已被殺）。表內的「變更內容」欄正確。 | 日後對照 `mutmut show <name>` 時編號可能對不上。 | 表格保留變更內容即可；如要可重現，註明數字來自 `mutate_only_covered_lines = true` 的那次執行。 |

### 改寫的舊測試是否仍有意義

- `test_exhaustion_is_atomic`（`tests/test_index_ledger.py:195-211`）：改成「所有 index 都被保留時連 marker 也拿不到」的原子 raise，並驗證 raise 後游標與保留都沒動（retire 後拿到 marker 1）。仍是原子性測試。
- `test_a_segment_that_misses_a_full_run_keeps_only_its_marker`（`:180-192`）：從原測試拆出的降級分支，驗證 marker 回放與舊段不受影響。
- `test_drain_uses_both_range_endpoints_and_a_full_range_degrades`（`:665-684`）：端點 1／9999 的檢查保留，exhaustion 改為 `((), None)` 並驗證 drain 回放。
- `test_drain_degrading_does_not_publish_or_consume_indexes`（`:687-696`）：仍驗證降級不登記 9999、下一段拿到 9999、回放完整。
- `test_drain_codec_leaves_out_the_indexes_of_a_degraded_segment`（`tests/test_index_codec.py:165-181`）：驗證同物件、順序、輸入不變、回放順序。
- `test_errors_before_core_entry_never_speak`（`tests/test_runtime_adapter_contract.py:283-304`）：拿掉 `exhaustion` 參數，`generator`／`invalid_index` 不變；新增 `test_a_segment_too_large_for_the_range_speaks_and_reports_indexes_at_its_marker` 驗證會說話且只送 marker 501。

### mutmut 存活表的等價宣稱

- `_find_start` 5／6（`size` 變大）、9（`<=`）：只會重試已排除的起點，等價，僅多耗時。
- `_find_start` 15（尾段 `scanned =` 取代 `+=`）：重置後第二圈從 `minimum` 經同樣的 blocker 落到同一個尾段位置 `s*`，此時 `scanned = (max+1-s_1) + (s*-min)`；若仍小於 `size`，第三圈必達 `size`。mutant 的 `scanned` 永遠 ≤ 原版，掃得只多不少，而多掃的都是重複起點，結果相同。等價。
- `_pending_indexes` 13、`__init__` 4、`bind` 4、`close` 5：等價，理由同計畫；`_pending_indexes` 13 已實測。
- 訊息 padding：測試用 `match=`（`re.search`）不加 anchor，與 phase 29 做法一致。

### 使用者還沒確認的使用者可見預設

spec §10 標為「Decided by orchestrator with the recommended default; user may override before merge」，使用者只決定了 Q1（選項 A）：

1. 範圍維持 `IndexRange(1, 9999)`，不放寬。
2. 游標循環、連續 run、不跨 maximum（跨 maximum 時尾段先空著）。
3. 保留到 retire 為止（不是到映射被移除為止）。
4. 不另加時間或次數的 quarantine；整圈就是 quarantine。
5. 放不下時**降級而不失敗**：DRAIN 永不 raise；END 模式只有 marker 也拿不到時才 raise。使用者可見的影響：超過 9999 個 index 的單一段（或 END 模式下 size−1 個）會整段朗讀，但 NVDA 的 index callback（游標、say-all 位置）集中在該段結束時才到。
6. 每個 engine core 第一次降級寫一條 **WARNING** 到 NVDA log（英文、不翻譯）：`WorldVoice index range 1..9999 has no room for a speech segment with N indexes; its indexes are reported when it completes`；之後同一 core 只記 DEBUG。
7. `compat/indexCodec.py` 加入 mutmut `source_paths`（`pyproject.toml:41`）。

另外：spec §8.5 的 Windows 手動驗證全部未執行（Linux 無法驗證）。

### 未評斷的項目

- `runtime/scheduler.py:501` 每個 task 的 error log 沒有 rate limit（spec 非目標）。
- `force_unverified_drain=True` 與各 wrapper 的 drain 宣告不變（spec 非目標）。
- END_INDEX／END_INDEX_AND_DRAIN 的過期 terminal 風險（產品未啟用）。
- `IndexAllocation` 的不變式改為「`len(wire_indexes)` 為 `len(originals)` 或 0」，目前只有 codec 與測試 harness 消費它；日後新消費者要知道。

## 工作區備註

review 開始前就存在、與本分支無關、未動：主 checkout 的 `D docs/superpowers/finish_task.md`、`?? DEVELOPMENT_WORKFLOW.md`、`?? diff.md`。本 worktree 除本檔外乾淨。

## 修正記錄

日期：2026-10-20。修正者：Opus 5.5（依 `DEVELOPMENT_WORKFLOW.md` §3.4）。六個 Minor 全部修正，沒有改變產品行為。突變實驗都在 scratchpad 的複本上做，沒有動到 worktree。

| # | commit | 處理方式與驗證 |
| --- | --- | --- |
| 1 | `ff2c16e`、`93cbc2c` | 在 `test_property_allocation_keeps_runs_disjoint_and_reports_each_original_once` 加一個 `@example`，用 `ScriptedDraws` 代替 `st.data()`，固定跑「wrap 之後游標前方有未 retire 的區段」：範圍 1..6，A 佔 1..2，B 佔 3..4 並 retire，3 個 index 的 run 在 5 放不下、包回後跳過 A，必須從 3 開始。修正前，突變 `start = blocker + 1` 在預設 profile 下 20 個 seed 只被抓到 13 個；修正後 seed 1..10 全部失敗（`assert (4, 5) == (3, 4)`，Failing explicit example），原碼通過。第一次跑 mutmut 時 clean test 失敗：`@example` 在同一個 process 裡只有一個物件，mutmut 在同一個 process 跑兩次 pytest，第二次 `StopIteration`。`93cbc2c` 改成每次執行都 `replay()` 一份新的；在同一個 process 連跑兩次 pytest，修正前第二次失敗、修正後兩次都通過；突變 a 仍在 seed 1..5 全部失敗。 |
| 2 | `f5545ec` | spec §6.1 改寫：游標「over `[minimum, maximum]`」，run 結束在 `maximum` 時存的是 `maximum + 1`，下一次搜尋的尾段分支把它包回 `minimum`。引用 `IndexLedger.prepare` 而不是行號，因為 #3 會讓行號移動。行為不變。 |
| 3 | `80c3794` | 在 `_find_start` 加兩行註解：嚴格的重疊判斷讓 `blocker > start`，所以每一輪都會前進；改成 `<=` 會在鎖內無限迴圈。沒有用 `assert`，因為這個 package 的產品程式碼沒有 runtime assert。 |
| 4 | `226699b` | 新增 `test_a_degraded_index_only_segment_still_drains_and_reports_its_indexes`（OneCore／VE／Cerence），用 `index_range=(1, 1)` 送 `(IndexCommand(701), IndexCommand(702))`：wrapper 收到 `()`，VE／Cerence 不做 native 呼叫，等 player idle；request COMPLETED、一次 drain，NVDA 依序收到 701、702 再 done。harness 會在 drain 進 ledger 時先記一筆 `drain`，所以順序只比較 NVDA 看得到的事件。突變 n（codec 不略過降級段的 `IndexCommand`）與「drain 只回放 `len(wire_indexes)` 個 original」都讓三個案例失敗，原碼通過。 |
| 5 | `ae5e629` | 新增 `test_an_index_is_reused_only_after_the_cursor_has_gone_round_the_range`（END_INDEX、DRAIN），範圍 1..10，長度不一的 run 依序 prepare 再 retire：used 與 skipped 的 index 依序重複 minimum..maximum；跳過的尾段比跳過它的 run 短；同一個 index 兩次使用之間至少隔一整圈，其他每個 index 都出現過。突變「從 minimum first-fit」、「`next_index = span.stop - 1`」、「retire 時把游標重設成 minimum」都讓兩個案例失敗，原碼通過。 |
| 6 | `963d918` | 重新跑 mutmut 後，`bind` 9/22/28/34 的編號和計畫一致：計畫的編號來自 `mutate_only_covered_lines = true`，審閱者沒有套 coverage，所以編號不同。表格改成在「Change」欄寫出每個被加 padding 的訊息，並註明編號的來源，以及要先用 `mutmut show` 確認。 |

mutmut（修正後，`mutmut run --max-children 3 "addon.synthDrivers.WorldVoice.indexLedger*" "addon.synthDrivers.WorldVoice.compat.indexCodec*"`，MemAvailable < 3 GB 就停掉的 guard，從未觸發）：**378 個 mutant：355 killed、6 timeout、17 survived**，存活的名稱與計畫表相同；`mutants/` 已刪除。

驗證（最後一個 commit）：`python3 -m pytest -q tests` **1745 passed、0 skipped**（基準 1740；新增 1 個降級整合測試 ×3 引擎、1 個重用距離測試 ×2 模式）；`prek run --all-files` 全數 Passed；`git diff --check master` 無輸出；兩個受保護路徑指令都沒有輸出。

Linux 上沒有驗到的：Windows NVDA、實際音訊裝置、各引擎 SDK，以及 spec §8.5 的手動項目（包括各引擎對空序列的實際行為）。
