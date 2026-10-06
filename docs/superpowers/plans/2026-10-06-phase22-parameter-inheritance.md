# 階段 22 實作計畫：參數繼承移出 repository

Spec：`docs/superpowers/specs/2026-10-06-phase22-parameter-inheritance-design.md`。分支 `phase22-parameter-inheritance`，基準 `4d85419`。

## 任務 1：policy 與 store 的繼承點

1. 測試：`ParameterConsistency.inherited` 開啟回傳主語音的 `PARAMETER_NAMES`、關閉回傳 `{}`；`VoiceSettingsStore.set_inheritance` 後 `ensure` 的初始值與 baseline、`reload` 疊上繼承值、provider 在 store 鎖下執行。
2. 實作 `values_of`／`inherited`、`set_inheritance`、`ensure`／`reload` 疊值。
3. Commit：`feat: let the voice settings store seed new and reloaded states`。

## 任務 2：manager 從主語音繼承，repository 只管 `voices`

1. 測試：composition 層的延遲語音、reload、關閉時的行為；改寫 `test_first_voice_resolution_inherits_main_values_and_keeps_cancel_baseline` 與 `test_voices_loaded_while_the_driver_starts_keep_their_own_values`；repository 測試刪除 speech 區段相關、加守門。
2. `VoiceManager` 註冊 `_inherited_parameters`；`ConfigVoiceSettingsRepository(conf)`；刪 `shared_section`；主驅動刪 `initSettings` 覆寫與 `_settingsInitialized`，不再建立 `ParameterConsistency`；更新 `tests/voice_binding_harness.py`、`tests/test_worldvoice_lifecycle.py`、`tests/test_main_locale_policy.py`。
3. Commit：`refactor: inherit main voice parameters from its state, not NVDA's speech section`。

## 任務 3：驗證與審查

全套 pytest、ruff；spec 對齊；Fable 審查；修正後 fast-forward 合併到 master。
