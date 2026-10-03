# 階段 3e：SegmentLifecycle 收為 SegmentHost 的內部實作，移除 Neural 測試

日期：2026-10-03。
基準：`master`（`f2a4309`，含 3d-2）。分支：`phase3e-lifecycle-internal`。
狀態：範圍與設計已獲使用者確認。

本文件是 [`refactor.md`](../../../refactor.md) §9 階段 3 的最後一個子階段 3e。3a–3d 完成後，六個引擎 wrapper 都改用 `runtime/segmentHost.py` 的 `SegmentHost`。目前 addon 內只剩 `segmentHost.py` 會 import `segmentLifecycle`，`playbackWork.CallbackGate` 已經沒有任何呼叫者。

## 需求與範圍

已確認的決定：

1. **改名為私有模組**（使用者選擇方案 A）：
   - `runtime/segmentLifecycle.py` 改名為 `runtime/_segmentLifecycle.py`，沿用 NVDA「底線開頭代表內部模組」的慣例。
   - addon 內只有 `segmentHost.py` 可以 import 它。
2. **刪除 Neural 測試**（使用者選擇）：
   - 刪除 `tests/test_neural_segment_drain.py` 與 `tests/neural_drain_harness.py`，並移除其他測試檔中的 Neural 參數與 adapter。
   - `storage/Neural-snapshot-2026-10-01.zip` 原封保留。
3. **只用 Neural 測 scheduler 的整合測試要逐一比對**（使用者同意）：
   - 其他引擎已有等價覆蓋的，直接刪除。
   - 沒有的，移植到 VE、Cerence 或 OneCore，避免 scheduler 的覆蓋默默變少。
4. **沿用的限制**：
   - 不考慮 Neural 相容性。
   - 所有引擎共用的程式碼只放在 `runtime/`。
   - 不修改內層 driver。
   - 新增的公開名稱用 snake_case。
   - plan 的變異步驟放在 commit 之後。

成功條件：

1. **邊界**：addon 內除了 `runtime/segmentHost.py`，沒有任何檔案 import `_segmentLifecycle`。原本的 `runtime/segmentLifecycle.py` 不再存在。由守門測試強制。
2. **死碼移除**：
   - `CallbackGate`、`CallbackLease`、`playbackWork._NativeCall` 不再存在。
   - 下列只為 wrapper 加入、現在沒有呼叫者的 API 不再存在：
     - `SegmentLifecycle.is_resource_busy()`、公開的 `SegmentLifecycle.reject_pending()`；
     - `SegmentOperation.sink`、`SegmentOperation.has_started`、`SegmentOperation.is_retired`。
3. **行為不變**（硬性要求）：
   - 六個引擎的 wrapper 與內層 driver 原始碼完全不改。
   - `SegmentHost` 只改 import。
   - `_segmentLifecycle.py` 只做刪除與文件修改，不改任何保留下來的邏輯。
4. **完整測試**：基線 1377 passed、89 skipped；完成後 **1372 passed、0 skipped**。
5. **格式與保護路徑**：`ruff format --check addon` 通過；Neural 未被追蹤。

**不在範圍內**：
- 階段 4 以後的 scheduler／`LegacyEngineAdapter` 重構。
- `compat/completionPolicies.DRAIN_ENGINES` 中的 `"Neural"` 項目：沒有 Neural 時不起作用，維持不改。

## 設計

### 1. runtime

- 用 `git mv` 把 `segmentLifecycle.py` 改名為 `_segmentLifecycle.py`，保留歷史。
- 模組 docstring 開頭註明：「Internal to SegmentHost; nothing else imports this module.」原有的鎖序說明保留。
- `segmentHost.py`：`from ._segmentLifecycle import ProducerLease, SegmentLifecycle, SegmentOperation`。
- `SegmentLifecycle` 保留 host 與 lifecycle 自己會用到的成員：
  - host 使用：`accept`、`reject_new`、`run`、`admit_producer`、`retire_producer`、`cancel`、`fail`、`fault`、`terminate`、`wait_idle`、`on_delivery_thread`、`join_delivery`。
  - lifecycle 內部使用：`wake_waiters`、`close_admission`、`_reject_pending_locked`。
- `SegmentOperation` 保留 `is_valid()`（lifecycle 與 host 都會用）。
- `playbackWork.py` 刪除 `_NativeCall`、`CallbackLease`、`CallbackGate`，以及只有它們會用到的 import。`DrainSupport`、`unverified_drain_support`、`PlaybackWork` 保留。

舊版 Neural 若被放回 `WorldVoice-workspace`，會因 import 失敗被 `engine/discovery.load_enabled_engine_classes` 記錄錯誤並跳過，其他引擎照常運作。這是預期的行為。

### 2. 測試

1. **刪除 Neural**：
   - 刪除 `test_neural_segment_drain.py`、`neural_drain_harness.py`。
   - 其他檔案移除下列 Neural 相關內容：
     - `engine_contract_harness.py` 的 `NeuralAdapter`（以及 `_engines()` 中對應的項目）；
     - `test_runtime_drain_integration.py` 與 `test_runtime_completion_policies.py` 中的 Neural 參數；
     - `requires_neural` 與 `in_thread` 的 import。若 `in_thread` 仍有其他使用者，移到使用它的檔案或共用的 harness。
2. **只用 Neural 的 scheduler 整合測試**（`test_runtime_drain_integration.py` 的 7 個）：
   - `test_voice_switch_reapplies_native_settings_and_keeps_distinct_drains`
   - `test_unsupported_neural_sdk_failure_releases_legacy_request`
   - `test_contextual_legacy_control_failure_fails_request`
   - `test_neural_legacy_done_acceptance_cannot_release_successor_after_cancel`
   - `test_neural_legacy_control_failure_delivery_cannot_complete_cancelled_request`
   - `test_contextual_neural_legacy_ignores_anonymous_and_revoked_completion`
   - `test_neural_legacy_terminal_and_index_cancel_have_no_lock_inversion`

   處理方式：
   - 每個測試先找出它在 scheduler 或 `LegacyEngineAdapter` 中保護的行為，再搜尋現有非 Neural 測試（`test_runtime_legacy_adapter.py`、`test_runtime_scheduler*.py` 等）。
   - 已有等價覆蓋：刪除，並在 plan 中寫明對應的測試名稱。
   - 沒有等價覆蓋：移植到一個有相同能力的引擎（多 voice instance、legacy 模式、SDK 失敗注入），測試名稱去掉 `neural`。
   - 已參數化、同時跑 Neural 與其他引擎的測試（例如 `test_language_change_active_native_call_cannot_escape_cancel`、`test_next_engine_starts_only_after_segment_drain`），只移除 Neural 參數。

   比對結果（plan 撰寫時確認，使用者同意 A 方案）：
   - `test_voice_switch_reapplies_native_settings_and_keeps_distinct_drains`：**移植到 VE**。
     - 整合 harness 讓 VE 回傳兩個聲音（`VE:fake`、`VE:fake2`）。
     - 測試沿用原名，驗證兩件事：同一引擎換聲音時會重新套用設定；每個聲音各用一個 native instance，每段各自 drain。
   - `test_unsupported_neural_sdk_failure_releases_legacy_request`：**刪除**。`test_runtime_scheduler.py::test_failure_stops_playback_and_completes_once` 已覆蓋同一行為：speak 失敗時請求變為 FAILED、DONE 只發一次、後續工作被取消。
   - 其餘 5 個都依賴 contextual legacy 模式（引擎需實作 `speak_legacy_segment`）。倉庫內只有 Neural 實作過這個模式，沒有能力相同的引擎可以移植，因此**刪除並記錄缺口**：
     - `test_contextual_legacy_control_failure_fails_request`
     - `test_neural_legacy_done_acceptance_cannot_release_successor_after_cancel`
     - `test_neural_legacy_control_failure_delivery_cannot_complete_cancelled_request`
     - `test_contextual_neural_legacy_ignores_anonymous_and_revoked_completion`
     - `test_neural_legacy_terminal_and_index_cancel_have_no_lock_inversion`
   - **缺口內容**：contextual legacy 失去「透過真實引擎跑完整流程」的整合覆蓋。各層單元測試仍在：
     - `test_runtime_legacy_adapter.py`：4 個 contextual legacy 測試；
     - `test_nvda_event_bridge.py`：2 個；
     - `test_runtime_scheduler.py`：1 個。
     等到有引擎實作 `speak_legacy_segment`（例如將來遷移 Neural）時再補回。這個功能本身要不要移除，留到階段 8 決定。
   - 最終審查發現：scheduler 中「contextual legacy 的 SEGMENT_FAILED 讓請求失敗」這個分支原本只靠被刪除的 `test_contextual_legacy_control_failure_fails_request` 覆蓋，因此另外新增單元測試 `test_runtime_scheduler.py::test_contextual_legacy_segment_failure_fails_request`。
3. **清掉舊式雙分支**：
   - harness 與測試中「沒有 `_segmentHost` 就讀 `_segmentLifecycle`」的分支改為只走 host。涉及的地方：
     - `engine_contract_harness.py`；
     - `test_vocalizer_segment_drain.py` 的 `hosted()`／`lifecycle_of()`／`settle_worker`；
     - `test_runtime_completion_policies.py`、`test_runtime_drain_integration.py`。
   - 同時更新過時的註解（3d-2 延後的 Minor）。
   - `test_sapi5_segment_drain.py::test_hook_fault_after_binding_does_not_strand_the_worker` 中為遷移前 SAPI5 留下的 `_segmentBindings`／`stranded` 清理鷹架一併刪除。SAPI5 已沒有 `_segmentBindings`，這段永遠拿到空值。
   - `test_seven_enabled_profiles_use_shared_lifecycle` 改名為 `test_six_enabled_profiles_use_shared_lifecycle`（`SEVEN_ENGINES` 改為 `SIX_ENGINES`）。
   - 只把 "Neural" 當引擎名稱、沒有載入 Neural driver 的測試維持不改。例如 composition、request builder，以及 completion policies 的設定表。
4. **合併雙胞胎**：
   - `test_ve_shared_lifecycle_waits_for_chunk_callback_and_idle` 與 `test_cerence_shared_lifecycle_waits_for_chunk_callback_and_idle` 合併為引擎中性的版本，兩引擎都跑。
   - `test_ve_shared_cancel_retires_guarded_feed_before_successor` 與 Cerence 版同樣合併。
   - 兩者若有引擎特有的斷言，以 `env.engine` 分支保留。
   - 合併後不再有 "VE lifecycle adapter" skip。
5. **模組名稱**：所有 `sys.modules` 清除與 `spec_from_file_location` 改用 `runtime._segmentLifecycle` 與 `_segmentLifecycle.py`。
6. **刪除的 API 的測試**：
   - `test_segment_lifecycle.py`、`test_playback_work.py` 等檔案中，只測已刪除 API 的測試（例如 `CallbackGate` 的 6 個）一併刪除。
   - 只是借用這些查詢做斷言的測試，改用保留的行為或 lifecycle 的內部狀態（這是內部模組的單元測試，可以讀私有狀態）。
7. **守門**（`test_lifecycle_private_access.py` 改寫）：
   - addon 內只有 `runtime/segmentHost.py` import `_segmentLifecycle`；
   - `runtime/segmentLifecycle.py` 不存在；
   - 六個 wrapper 都不出現 `_lifecycle`、`SegmentLifecycle`、`CallbackGate`、`segmentLifecycle`；
   - `playbackWork` 沒有 `CallbackGate` 屬性。
   - 原本針對 wrapper 私有存取的 regex 檢查保留，作用在全部六個 wrapper 上。
8. **變異證明**（commit 之後）：
   - 在 `driver/VE/__init__.py` 加入 `from ...runtime._segmentLifecycle import SegmentLifecycle`，守門測試必須變紅。
   - 把 `CallbackGate` 加回 `playbackWork`，守門測試必須變紅。
   - 每個移植的測試，在它保護的行為上做一個對應的變異，證明測試會失敗。

## 驗收

- `python3 -m pytest tests -q`：`1372 passed`；沒有 skipped，也沒有 xfailed。
- `test ! -e addon/synthDrivers/WorldVoice/runtime/segmentLifecycle.py`。
- `grep -rn "_segmentLifecycle\|segmentLifecycle" addon --include=*.py`：只出現在 `runtime/segmentHost.py` 與 `runtime/_segmentLifecycle.py` 自身。
- `grep -rn "CallbackGate\|CallbackLease" addon --include=*.py`：無輸出。
- `git diff master --stat -- addon/synthDrivers/WorldVoice/driver`：無輸出。
- `git diff master -M --stat -- addon/synthDrivers/WorldVoice/runtime`：只列出 `segmentHost.py`（一行 import）、改名的 `_segmentLifecycle.py`（只有刪除與 docstring）和 `playbackWork.py`（只有刪除）。
- `ls tests | grep -i neural`：無輸出。
- `ruff format --check addon`：通過；Neural 未被追蹤。
