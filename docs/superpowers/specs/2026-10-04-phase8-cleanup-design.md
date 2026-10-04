# 階段 8：刪除相容 shim 與死碼、移除 contextual legacy、歸檔舊紀錄

日期：2026-10-04。
基準：`master`（`d7dca69`，階段 0–5 完成）。分支：`phase8-cleanup`。
狀態：範圍與設計已獲使用者確認。使用者決定先做階段 8，階段 6、7 之後再處理。

本文件是 [`refactor.md`](../../../refactor.md) §9 的階段 8，對應 §8（相容 shim、流程文件）與 §2.1（`SpeechFuture.then`）。refactor.md 列出的 `order_move_to_end_register`、`with_order_log` 依使用者決定保留。另外處理階段 3e 留給本階段的 contextual legacy 去留。

## 需求與範圍

已確認的決定：

1. **刪除三個相容 shim**：`taskManager.py`、`requestBuilder.py`、`driver/engineSession.py`。
   - `WorldVoice-workspace` 中的 MSC、Natural 外掛只 import `synthDrivers.WorldVoice.driver`（從 bytecode 確認），不用這三個 shim。
2. **刪除 `SpeechFuture.then`**：add-on 內沒有呼叫者。
3. **pipeline 完全不改**（使用者決定）：
   - 保留 `order_move_to_end_register`、`with_order_log`、9 行被註解掉的 `# @with_order_log(...)`，以及主驅動的 `self.order`。
   - `with_order_log` 在 DEBUG 模式下會讀寫 `synth.order`；refactor.md「`self.order` 沒有任何地方讀取」的說法並不正確。
4. **移除 contextual legacy**（使用者決定）：
   - 只有 Neural 實作過 `speak_legacy_segment`。Neural 自階段 3e 起就已無法載入。
   - 倉庫內六個引擎與 MSC、Natural 外掛都沒有實作它，因此行為不變。
   - 將來遷移 Neural 時，若需要這個模式，可以從 git 歷史還原。
5. **只歸檔散落的舊紀錄**（使用者決定）：
   - `docs/superpowers/` 維持原位，它仍是使用中的流程目錄；
   - `review_gpt1.md` 與 `docs/superpowers/finish/` 移到 `docs/history/`；
   - 誤被追蹤的 `.superpowers/sdd/` 檔案取消追蹤；
   - `readme.md` 說明這些是開發紀錄。
6. **沿用的限制**：
   - 不修改內層 driver；六個外層 wrapper 也完全不改；
   - 不碰使用者未 stage 的 `docs/superpowers/finish_task.md` 刪除，也不碰未追蹤的 `refactor.md`；
   - plan 的變異步驟放在 commit 之後。

成功條件：

1. 三個 shim 檔案不存在；addon 與測試都不再以舊路徑匯入。
2. addon 內不再出現：
   - `def then`；
   - `legacy_contextual`、`speak_legacy_segment`、`LEGACY_SEGMENT`、`legacy_segment_sink`、`configure_legacy_segment_events`。

   由守門測試強制。`order_move_to_end_register`、`with_order_log` 與 `self.order` 仍在。
3. `CompletionMode` 的成員比較只出現在 `runtime/completion.py`、`runtime/models.py` 的 `__post_init__`、`compat/completionPolicies.py`。voiceManager 的 `_resource_completion` 隨 contextual legacy 一併刪除，因此從允許清單移除。
4. 行為不變：開啟的引擎、完成合約、語音、設定、取消與關閉流程都和現在相同。
5. 完整測試全部通過；`ruff format --check addon` 通過；`driver/` 下沒有任何變動；Neural 未被追蹤。

**不在範圍內**：
- 階段 6（pipeline 設定單一事實來源、`STAGES` registry）與階段 7（Role 設定）；
- MSC、Natural 外掛的更新。它們在階段 5 的建構子變更後需要更新，但不在倉庫內，也只有 `.pyc`。

## 設計

### 1. 相容 shim

- 刪除 `addon/synthDrivers/WorldVoice/taskManager.py`、`requestBuilder.py`、`driver/engineSession.py`。
- 主驅動 `__init__.py` 改為直接匯入：
  - `from .runtime.scheduler import TaskManager`
  - `from .runtime.requestBuilder import queue_speech_sequence`
- 以舊路徑載入或 stub 這些模組的測試，改用新路徑；plan 逐檔列出。

### 2. `SpeechFuture.then`

- 從 `runtime/scheduler.py` 刪除 `then` 方法。`SpeechFuture` 類別保留（`append_speech`／`append_break` 仍回傳它），docstring 改寫成不再提到 `then`。
- 刪除只測 `then` 的測試。

### 3. pipeline

不改。`pipeline/__init__.py` 與主驅動的 `self.order` 都維持原樣。

### 4. contextual legacy

- `runtime/models.py`：刪除 `CompletionContract.legacy_contextual` 欄位，以及「contextual 只能搭配 LEGACY_DONE」的檢查。
- `runtime/completion.py`：
  - 刪除 `SpeakEntry.LEGACY_SEGMENT` 與 contextual legacy 那一列；
  - `_RULES` 的 key 改為 `CompletionMode`；
  - `rule_for(contract)` 改為 `_RULES[contract.mode]`。
- `compat/engineAdapter.py`：
  - 刪除 `_speak_legacy_segment` 與 `_ENTRIES` 中對應的項目；
  - 刪除 `configure_legacy_segment_events` 與 `_legacy_events`；
  - 刪除 `speak` 中兩個 contextual 前置檢查與 legacy sink 的分支。

  其餘檢查的順序與訊息不變。
- `nvdaEventBridge.py`：
  - 刪除 `legacy_segment_sink`；
  - 刪除 `bind` 中「contextual 需要 batch handler」的檢查；
  - 刪除 `_receive` 中 contextual 的提早返回。
- `voiceManager.py`：
  - 刪除 `_resource_completion`，`_bind` 直接呼叫 `self._completion_for(cls, source)`；
  - 刪除 `_bind` 的 `elif completion.legacy_contextual` 分支；
  - 刪除沒人使用的 `replace`、`CompletionMode` import。
- `runtime/scheduler.py` 不需要改，它只經由規則表讀取合約。

### 5. 文件

- `git mv review_gpt1.md docs/history/review_gpt1.md`。
- `git mv docs/superpowers/finish/*.md docs/history/`（3 份）。
- `git rm --cached` 兩個 `.superpowers/sdd/2026-09-30-worldvoice-shared-segment-lifecycle/` 檔案；本機檔案保留。
- `readme.md` 加一小段（英文，與 readme 原文一致）：`docs/superpowers/` 是各階段的設計與計畫，`docs/history/` 是過去的審查與驗證紀錄；兩者都是開發紀錄，不是現行規格。
- `docs/` 在 `.gitignore` 中，新增或移動的文件用 `git add -f`。

## 測試

1. **刪除**：
   - contextual legacy 的測試，每個都只測已刪除的功能：
     - `test_runtime_legacy_adapter.py`：`test_contextual_legacy_reopen_reconfigures_segment_events`、`test_contextual_legacy_entry_preserves_commands_and_original_context`、`test_contextual_legacy_requires_context_instead_of_anonymous_fallback`；
     - `test_nvda_event_bridge.py`：`test_contextual_legacy_supplier_rechecks_source_binding`、`test_contextual_legacy_sink_rejects_unrelated_events`；
     - `test_runtime_scheduler.py`：`test_contextual_legacy_completion_requires_exact_segment_identity`、`test_contextual_legacy_segment_failure_fails_request`；
     - `test_runtime_completion_policies.py`：`test_contextual_legacy_option_cannot_change_marker_completion`。
   - `test_runtime_scheduler.py` 中只測 `then` 的測試。
2. **修改**：
   - `test_completion_characterization.py` 與 `test_completion_rules.py` 刪除 contextual 那一列；
   - 規則表涵蓋性測試改為「每個 `CompletionMode` 恰有一條規則」；
   - `test_completion_rules.py` 的 `ALLOWED` 移除 voiceManager；
   - 以舊路徑匯入 shim 的測試改用新路徑。
3. **守門**：新增測試確認成功條件 1、2。
4. **變異證明**（commit 之後）：
   - 加回一個 shim 檔案；
   - 在 adapter 加回 `legacy_contextual` 字樣；
   - 在 scheduler 加回 `def then`。

   守門測試都必須變紅。

## 驗收

- `python3 -m pytest tests -q`：全部通過，沒有 skipped。
- 守門測試通過。
- `git diff master --stat -- addon/synthDrivers/WorldVoice/driver`：只列出被刪除的 `driver/engineSession.py`。
- `ruff format --check addon` 通過；Neural 未被追蹤。
