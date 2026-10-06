# 階段 22：參數繼承移出 repository

日期：2026-10-06。
基準：`master`（`4d85419`，階段 21 合併完成）。分支：`phase22-parameter-inheritance`。
狀態：使用者已核准（2026-10-06），依自動流程執行。

本文件對應 `storage/refactor5.md`（不入版控）§3.1「建議 B」與 §11 階段 22。行號以 `4d85419` 為準。

## 現況

`ConfigVoiceSettingsRepository.load`（`configRepository.py:40-58`）同時負責三件事：

1. 讀寫每個語音自己的 `WorldVoice.voices.<name>` 區段；
2. 「參數一致」開啟時，從主 synth 的 NVDA speech 區段（`config.conf["speech"]["WorldVoice"]`）繼承 `PARAMETER_NAMES`，經 `ParameterConsistency.shared_section`（`mainLocalePolicy.py:91-99`）；
3. 啟動閘門：`main_settings_ready`（主驅動 `_settingsInitialized`，`__init__.py:177、211-216、306-311`）在 NVDA 的 `initSettings` 回傳前關閉繼承。

「哪些值跟著主語音」已經有主人：`ParameterConsistency`（`copy_from`）。repository 因為第 2、3 點而必須知道 NVDA speech 區段、synth 名稱與啟動時序，違反 SRP 與 DIP（runtime 的 repository 依賴 NVDA 的設定版面）。

## 設計

繼承改為「從主語音目前的 state」取得，不再讀 NVDA speech 區段：

- `ParameterConsistency`
  - 新增 `values_of(store, base_name) -> dict`：主語音 snapshot 的 `PARAMETER_NAMES`。
  - `copy_from` 改用 `values_of`。
  - 新增 `inherited(store, base_name) -> dict`：開啟時回傳 `values_of`，關閉時回傳 `{}`。
  - 刪除 `shared_section`。
- `VoiceSettingsStore`
  - 新增 `set_inheritance(provider)`，`provider(spec) -> Mapping`。
  - `ensure` 建立新 state 時，以 `load(spec)` 再疊上 `provider(spec)` 作為初始值；初始值同時是 cancel baseline，與現行「載入的共用值就是 baseline」相同（`tests/test_runtime_composition.py::test_first_voice_resolution_inherits_main_values_and_keeps_cancel_baseline`）。
  - `reload` 同樣疊上 `provider(spec)` 後才 `update` + `checkpoint`。
  - provider 在 `ensure` 內於 store 鎖下呼叫（RLock，同執行緒可重入），其他執行緒看不到尚未繼承的 state。鎖序維持 store → state。
- `VoiceManager`
  - `__init__` 先設 `_defaultVoiceInstance = None`，再 `settings.set_inheritance(self._inherited_parameters)`。
  - `_inherited_parameters(spec)`：主語音尚未建立時回傳 `{}`，否則 `parameter_consistency.inherited(settings, 主語音名稱)`。
- `ConfigVoiceSettingsRepository(conf)`：只讀寫 `voices` 區段；刪除 `synth_name`、`parameters`、`main_settings_ready`、`shared_section` 呼叫與 try/except。
- 主驅動：刪除 `initSettings` 覆寫、`_settingsInitialized`；`ParameterConsistency` 不再由主驅動建立（manager 自建預設實例）。

## 各流程的等價性

參數一致**關閉**：provider 回傳 `{}`，`load` 與現行（`shared is None`）完全相同。以下都是**開啟**時。

| 流程 | 現行 | 新設計 |
| --- | --- | --- |
| 建構期間（主語音、VE/Cerence 的 waitfactor 語音） | 閘門關閉，各讀自己的值 | 主語音建立前 `{}`；之後建立的語音繼承主語音（主語音自己的 `voices` 值） |
| NVDA `initSettings` → `loadSettings`（非首次） | 對每個設定 `setattr` → `_set_voice_parameter` → `copy_from` + commit 全部 | 相同 |
| 首次載入（speech 區段不存在） | NVDA 不呼叫 `loadSettings`；建構期語音保留自己的值，之後的延遲語音讀剛存入的 speech 區段（= 主語音的值） | 所有語音繼承主語音 |
| 延遲載入（`resolve_playback`、`getVoiceInstance`） | 讀 speech 區段 | 讀主語音目前的 state |
| profile 切換、面板取消（`loadSettings` → `reload`） | NVDA 先把主語音設為 speech 區段的值；之後每個語音的 `PARAMETER_NAMES` 讀 speech 區段 | NVDA 先把主語音設為 speech 區段的值（`onlyChanged` 只跳過已相等的值，所以之後主語音 state 與 speech 區段相等）；之後每個語音繼承主語音 state |

差異只在三個邊角，新行為都更符合「每個語音以主語音的參數說話」：

1. 首次載入時，建構期建立的語音也繼承主語音（現行保留自己的值，直到使用者第一次改主語音參數）。
2. 語音設定面板編輯中（尚未按儲存，speech 區段仍是舊值）建立的語音，繼承主語音的編輯中值（現行拿到 speech 區段的舊值，與其他語音不一致）。面板取消時 NVDA 的 `loadSettings` 會讓主語音回到舊值並 `copy_from` + commit 到所有 state。
3. speech 區段缺某個鍵（主 synth 不支援該設定，例如 `inflection`）時，現行回到預設值，新設計取主語音 state 的值（與 `copy_from` 相同）。

## 測試

- repository：刪除讀 speech 區段的測試（共用值、閘門、無效值退回、缺 speech 節點）；保留讀寫 `voices` 與「不 import NVDA」的測試；守門：`configRepository.py` 不出現 `speech`、`ParameterConsistency`。
- store：`set_inheritance` 後 `ensure` 的初始值與 baseline 含繼承值；`reload` 疊上繼承值；provider 在 store 鎖下呼叫（另一執行緒在 provider 執行中看不到 state）。
- policy：`inherited` 開啟／關閉；`copy_from` 不變；刪除 `shared_section` 測試。
- manager／composition：主語音建立前不繼承；延遲語音繼承主語音 state；`reload` 後非主語音的 `PARAMETER_NAMES` 等於主語音、variant 是自己的；參數一致關閉時各自讀自己的值。
- 主驅動：刪除閘門與「repository 與 manager 共用一個 policy」的測試；改為「主驅動不覆寫 `initSettings`」。

## 不在範圍內

- `VoiceManager.reload` 只重載有 instance 的語音（現行行為）。
- 繼承的值不寫回 repository，直到 commit（現行行為）。

## 驗證

全套 pytest、`ruff check addon`、`ruff format --check addon`、prek hook。
