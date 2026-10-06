# 階段 21 實作計畫：variant 外漏修正與第五輪收尾

Spec：`docs/superpowers/specs/2026-10-06-phase21-variant-cleanup-design.md`。分支 `phase21-variant-cleanup`，基準 `2df3fe3`。

每個任務：先寫或改測試並確認失敗（純重構任務以既有測試為準），再改實作，跑相關測試，最後一次全套測試，commit（prek hook 會跑 ruff）。

## 任務 1：N13 — `load` 只從共用區段讀 `PARAMETER_NAMES`

1. `tests/test_voice_config_repository.py`：三個 `variant="main"` 期望改為語音自己的值；新增 `test_shared_variant_never_overrides_the_voice_variant`（共用 `variant="main"`、語音 `variant="bright"` → `bright`）；新增守門測試：`configRepository.py` 的 `load` 引用 `PARAMETER_NAMES`。
2. `configRepository.py`：import `PARAMETER_NAMES`；迴圈內 `own = voices[spec.name].get(name)`，`shared is None or name not in PARAMETER_NAMES` 時用 `own`。
3. Commit：`fix: keep each voice's own variant when parameters follow the main voice`。

## 任務 2：N14 — 不可用的主語音名稱拋 `LookupError`

1. 測試：`VoiceManager.defaultVoiceName = "missing"` 拋 `LookupError`，主語音不變；主驅動 `_set_voice("missing")` 拋 `LookupError` 且 `_voice` 不變；成功時 `_voice` 記下。
2. `voiceManager.py` setter 改 `raise LookupError(name)`；`__init__.py:_set_voice` 在 setter 之後才寫 `_voice`。
3. Commit：`fix: reject an unavailable main voice so NVDA repairs the saved voice`。

## 任務 3：N15 — 刪除 `wait_native_retired`

1. 測試改寫：`test_segment_lifecycle.py` 的 `Hooks` 刪 `wait_native_retired`／`retirement_entered`／`retired_error`，加 `boundary_error`；`test_nested_lease_retires_before_successor` 改等 `_admitting` 為假；`test_retirement_failure_latches_core_fault` 改名為 `test_hook_failure_after_the_native_boundary_latches_core_fault` 並用 `boundary_error`。`test_segment_host.py` 兩個 `broken` 改包 `wait_native_boundary`。
2. 刪 Protocol、呼叫點、host 實作。
3. Commit：`refactor: drop the empty wait_native_retired segment hook`。

## 任務 4：N16 + N17(1) — `retire` 契約與 `_drop_pending_locked`

1. 測試：host 層「retire 後 forget 前 cancel 標記 cancelled；forget 後 pending 不含該記錄」。
2. `retire` docstring 補 `forget` 契約；`_drop_pending_locked`。
3. Commit：`refactor: document retire's forget step and share the pending drop`。

## 任務 5：N17(2)(3)、N18、N19

1. presenter 改用 `prune_assignments`（既有 `tests/test_role_presenter.py` 覆蓋）。
2. `installTasks._load_by_path`（既有 `tests/test_workspace.py`、`tests/test_core_archive.py` 覆蓋）。
3. 刪 `VoiceSettingsDialogs.py:37`；確認相關結構測試。
4. N19：`onSave` 比對 `voice_manager`；以 `tests/test_ui_structure.py` 同類方式加測試。
5. Commits：`refactor: reuse prune_assignments and one by-path loader`、`refactor: drop the duplicate punctuation-pause write`、`fix: skip saving roles to a voice manager the synth replaced`。

## 任務 6：衛生

1. OneCore `log.exception` → `log.error(..., exc_info=True)`。
2. `makeSettings` 的 beep → log。
3. `_get_availableNumlans`。
4. `CancellationToken(logger=)`，`new_request` 傳 `self._logger`；測試：callback 失敗走注入的 logger。
5. VE/Cerence `_ThreadState`；跑漂移測試。
6. Commit：`style: align OneCore logging, token logger and thread-local defaults`（可拆）。

## 任務 7：驗證與審查

全套 pytest、`ruff check addon`、`ruff format --check addon`；Fable 審查整個分支；修正後 fast-forward 合併到 master。
