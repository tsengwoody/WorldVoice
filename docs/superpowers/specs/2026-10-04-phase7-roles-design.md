# 階段 7：Role 設定、主語系政策、Role 面板 Presenter

日期：2026-10-04。
基準：`master`（`c972256`，階段 5½ + 6 完成）。分支：`phase7-roles`。
狀態：依使用者要求自動執行（spec → plan → 實作 → Fable review）。唯一需裁示的項目（`WorldVoiceVoiceSettingsPanel` monkey-patch）使用者選擇「維持現狀」。

本文件是 [`refactor.md`](../../../refactor.md) §9 的階段 7，對應 §3.1（role、參數一致性）、§6.1（Presenter、`guard_errors`、log 開關、zip 匯入）與 §7 的 D1、D4、D6、D7。

## 需求與範圍

1. **Role 只有一個寫入者：`ConfigRoleRepository`**（`config["WorldVoice"]["role"]`）。
   - `VoiceManager.onKeepEngineConsistent`、`onKeepMainLocaleVoiceConsistent`、`_getConfiguredVoiceNameForLanguage` 改為呼叫它。
   - `SpeechRoleSettingsPanel.onSave` 自己重建 role、之後又呼叫 `onKeepEngineConsistent` 再重建一次；兩次合併為一次 `save(prune(...))`。
2. **三個主語系政策集中在 `mainLocalePolicy.py`**：`EngineConsistency`、`VoiceConsistency`、`ParameterConsistency`。
   - `KeepMainLocale*` 三個旗標的讀寫只在這個模組。
   - `configRepository.py` 依參數一致旗標決定載入來源的分支，改由 `ParameterConsistency.shared_section` 提供。
   - `VoiceManager` 的 `languages`／`localeToVoicesMap`／`localesToNamesMap` 三份「依引擎過濾」改為一個 `_visible_table()`，過濾規則來自 `EngineConsistency.visible`。
3. **`RolePanelPresenter`**（`globalPlugins/WorldVoice/rolePresenter.py`，不依賴 wx）承擔 role 面板的所有狀態與交易。`SpeechRoleSettingsPanel` 只做 widget ↔ presenter，並修正：
   - **D1**：勾選「參數一致」的預覽可以還原。勾選前先記下每個語音的五個參數，取消勾選時還原這份記錄，而不是 edit baseline，以免抹掉對話框中其他語音的編輯。按 OK 時若旗標為關閉，寫入的就是還原後的值。
   - **D4**：apply 的順序改為：存語音參數 → 存 role 與旗標 → 視需要切換主語音 → 以**切換後**的主語音鏡像 `config["speech"][synth]` 的五個參數。
   - **D6**：apply 失敗時，面板顯示錯誤後改拋 `ValueError`。NVDA 的 `MultiCategorySettingsDialog.onOk/onApply` 只攔 `ValueError`，會中止這次存檔並保持對話框開啟；未套用的 edit 保留，可重試或取消。
   - 其他行為維持不變：取消時復原 edit、pending 選擇與引擎一致旗標；面板銷毀時關閉 edit。
4. **D7**：`LogSettingsPanel.isValid` 在確認啟用對話框選「否」時，取消勾選啟用並同步停用 stage 核取方塊，回傳 True。
5. **`PipelineLogService`**（`globalPlugins/WorldVoice/pipelineLog.py`）由 plugin 的三個 log 開關流程與 `LogSettingsPanel` 共用，提供 `enabled`、`enable()`、`disable()`、`export()`。三段提示訊息也只存在於這個模組的提示函式中。
6. **`extract_core_archive`**（`addon/generics/coreArchive.py`）由 `installTasks.onInstall` 與 plugin 的 `onFileImport` 共用。
   - `installTasks` 以檔案路徑載入此模組（`importlib.util.spec_from_file_location`）：安裝時 `generics` 可能已是舊版且已被 import。
   - plugin 以 `generics.coreArchive` 正常 import。
   - 匯入損毀的 zip 時，plugin 改為顯示「Import fail」，以往只寫 log、沒有任何回饋。
7. **`guard_errors` 不再以類別屬性當 service locator。**
   - `got_error_callback` 改用 `wx.GetTopLevelParent(panel)` 取得所在對話框，關閉後以同一個類別重開。
   - 刪除 `WorldVoiceSettingsDialog.wvd` 與其 `_onDestroy`。
8. **`WorldVoiceVoiceSettingsPanel` monkey-patch 維持現狀**（使用者決定）。只在 `createDriverSettings` 加註解：它複製自 NVDA 私有方法，NVDA 升級時需比對。

### 成功條件

1. 完整測試全部通過；`ruff format --check addon` 通過；`ruff check --select F401,F821`（範圍同 refactor.md 附錄）為 0。
2. 守門測試（AST／文字掃描 `addon/`，排除內層驅動）：
   - `["role"]` 的讀寫只出現在 `roles.py`；
   - `KeepMainLocale` 只出現在 `mainLocalePolicy.py` 與主驅動 confspec；
   - `speechSettingsDialog.py` 不再出現 `config.AggregatedSection`、`_dataToPercist`、`_defaultVoiceInstance`、`.wvd`。
3. Role 面板的行為測試改以 presenter 的一般單元測試撰寫；舊的 AST 抽類別測試（`test_voice_settings_transaction.py`、`test_f4_voice_state.py` 中針對 `SpeechRoleSettingsPanel` 的部分）移植到 presenter，原本斷言的行為全部保留。
4. 內層 driver 與 `driver/sonic` 無變動；Neural 未被追蹤。

### 不在範圍內

- 階段 9（wrapper）、階段 10（`VoiceManager` 拆成 `EngineRegistry`／`VoiceCatalog`，`Voice` 拆分）、階段 11（衛生）。
- `BaseSettingsPanel.onSave -> bool` 與 NVDA 介面的不一致（§6.3）、Unicode 面板三組重複（§6.2）、`UnicodeDetectionSettingsPanel` 內 `getSynth().uwv = getSynth().uwv`。
- `GlobalPlugin` 的 `workspace_path` 遮蔽等 §6.4 其餘死碼。
- 第 5 點與第 6 點的 UI 文字不變（不新增翻譯字串）；第 6 點「Import fail」重用既有字串。

## 設計

### 1. `synthDrivers/WorldVoice/roles.py`

```python
def getPrimaryLocale(locale: str) -> str   # 由 voiceManager 搬來；voiceManager 重新匯出以維持既有 import

class ConfigRoleRepository:
	"""Locale → voice assignments in config["WorldVoice"]["role"]."""

	def __init__(self, conf_provider: Callable[[], Any] = lambda: config.conf): ...
	def voice_for(self, language: str) -> str | None      # 先精確 locale，再主語言（同 _getConfiguredVoiceNameForLanguage）
	def assignments(self) -> dict[str, str]                # 有 "voice" 的 section；值為 voice 名稱
	def save(self, assignments: Mapping[str, str]) -> None # 一次寫回整個 role 區段
	def assign(self, locale: str, voice: str) -> None      # save({**assignments(), locale: voice})
	def prune(self, available: Mapping[str, Collection[str]]) -> None
```

- 判斷 section 的方式：值為 `Mapping`，或具有 `get` 與 `items` 的物件（NVDA `AggregatedSection`）。不再依賴 `config.AggregatedSection` 型別。
- `save` 寫入 `{locale: {"voice": voice}}`，並保留 role 區段中非 section 的純量項目（同現行 `onKeepEngineConsistent`）。沒有 `"voice"` 的 section 會被捨棄，與現行 `onKeepEngineConsistent` 一致。
- `prune(available)` 保留 `locale in available and voice in available[locale]` 的項目，等價於現行 `onKeepEngineConsistent`。

### 2. `synthDrivers/WorldVoice/mainLocalePolicy.py`

```python
PARAMETER_NAMES = ("rate", "pitch", "volume", "inflection", "rateBoost")

class EngineConsistency:
	"""KeepMainLocaleEngineConsistent: role choices come from the main voice's engine."""
	def __init__(self, conf_provider): self.enabled = <config flag>   # 可預覽的 pending 值
	def persist(self) -> None                                         # 寫回 config
	def visible(self, table, default_engine) -> list[VoiceSpec]

class VoiceConsistency:
	"""KeepMainLocaleVoiceConsistent: the main locale's role follows the main voice."""
	def __init__(self, conf_provider, roles: ConfigRoleRepository, language=languageHandler.getLanguage): ...
	enabled: bool  (property，讀寫 config)
	def main_locale(self, voice) -> str            # getPrimaryLocale(voice.language or language())
	def follow(self, voice) -> None                # enabled 時 roles.assign(main_locale(voice), voice.name)

class ParameterConsistency:
	"""KeepMainLocaleParameterConsistent: every voice speaks with the main voice's parameters."""
	def __init__(self, conf_provider): ...
	enabled: bool  (property，讀寫 config)
	def copy_from(self, store: VoiceSettingsStore, base_name: str) -> None   # 現行 previewVoiceParameterConsistent 的本體：每個 state 一次 update
	def shared_section(self, synth_name: Callable[[], str]) -> Mapping | None
```

- `shared_section`：
  - 旗標關閉時回傳 None；
  - 開啟時回傳 `conf["speech"][synth_name()]`；
  - 取不到（任何例外）時回傳 None。
- `ConfigVoiceSettingsRepository.load` 的規則：
  - section 不為 None：一律從它取值，缺值即預設；
  - section 為 None：從 `voices[...]` 取值。

  這與現行行為完全相同，`tests/test_voice_config_repository.py` 不需修改。
- `ConfigVoiceSettingsRepository(conf, synth_name, parameters=None)`：未傳入時自建 `ParameterConsistency(lambda: conf)`。
- 主驅動 `_set_voice_parameter` 改用 `self._voiceManager.parameter_consistency.enabled`。

### 3. `VoiceManager`

- `__init__`：
  - `self.roles = roles or ConfigRoleRepository()`（新增 keyword-only 參數 `roles=None`）；
  - `self.engine_consistency = EngineConsistency(...)`；
  - `self.voice_consistency = VoiceConsistency(..., self.roles)`；
  - `self.parameter_consistency = ParameterConsistency(...)`。
  - 原本在 `_initialize` 讀旗標的那一行刪除。
- `keepMainLocaleEngineConsistent` 改為 property，委派 `engine_consistency.enabled`（保留，供既有呼叫者與測試使用）。
- `_visible_table()` → `self.engine_consistency.visible(self.table, self._defaultVoiceInstance.engine)`；`languages`、`localeToVoicesMap`、`localesToNamesMap` 都改用它。
- `onKeepEngineConsistent()` → `self.roles.prune(self.localeToVoicesMap)`。
- `onKeepMainLocaleVoiceConsistent()` → `self.voice_consistency.follow(self.defaultVoiceInstance)`。
- `_getConfiguredVoiceNameForLanguage(language)` → `self.roles.voice_for(language)`。
- `previewVoiceParameterConsistent(base)` → `self.parameter_consistency.copy_from(self.settings, base.name)`；`onVoiceParameterConsistent` 不變（preview 後逐一 commit）。

### 4. `globalPlugins/WorldVoice/rolePresenter.py`

```python
class RolePanelPresenter:
	def __init__(self, manager, *, speech_section: Callable[[], MutableMapping], set_main_voice: Callable[[str], None]): ...
	# 查詢
	def locales(self) -> list[tuple[str, str]]          # (locale, 顯示名稱)，依 manager.languages
	def voices(self, locale) -> list[tuple[str, str]]   # (voice 名稱, 描述)，依 localeToVoicesMap，去重
	def selected_voice(self, locale) -> str             # pending 選擇或已存 role；"" 表示未選
	def voice(self, name)                               # manager.getVoiceInstance
	def capabilities(self, name) -> frozenset[str]
	def variants(self, name) -> list[str]               # ["default", ...]
	keep_engine / keep_voice / keep_parameters: bool    # pending 旗標
	# 編輯
	def select_voice(self, locale, name) -> facade | None
	def set_parameter(self, name, parameter, value) -> None
	def set_variant(self, name, value) -> None
	def set_engine_consistency(self, enabled) -> None
	def set_voice_consistency(self, enabled) -> None
	def set_parameter_consistency(self, enabled) -> None
	# 交易
	def apply(self) -> None
	def discard(self) -> None
	def close(self) -> None
```

- 建構時 `manager.beginVoiceSettingsEdit()`；記下引擎一致旗標的初始值；三個 pending 旗標取自各政策。
- `select_voice`：
  - 記錄 pending；
  - 參數一致為開啟且有選擇語音時，以 `voice.update_settings(**主語音五參數)` 一次批次複製（維持現行的原子性，`test_ui_consistency_copy_is_atomic_for_worker_activation`）；
  - 回傳 facade。
- `set_parameter`：`setattr(voice, parameter, value)`；參數一致開啟時 `manager.previewVoiceParameterConsistent(voice)`。
- `set_engine_consistency`：設定 `manager.engine_consistency.enabled`（預覽，影響 `locales`/`voices`）。
- `set_parameter_consistency(enabled)`（D1）：
  - 由關到開：記下 `settings.keys()` 每個 state 的五個參數，然後 `previewVoiceParameterConsistent(default)`；
  - 由開到關：若有記錄，就逐一 `state.update(**記錄)` 還原後清除記錄。開啟對話框時旗標本來就是開，不會有記錄，這時關閉不做任何事（與現行相同：沒有可還原的預覽）。
- `apply()`：
  1. 參數一致開啟時，從主語音 preview。
  2. `edit.apply()`。失敗時直接拋出，其後步驟都不執行（pending 保留）。
  3. 計算 role：`assignments()` 套用 pending（"" 刪除，其餘設定）。
  4. 寫三個旗標（`engine_consistency.persist()`、`voice_consistency.enabled`、`parameter_consistency.enabled`）。
  5. `roles.save(...)` 後 `roles.prune(manager.localeToVoicesMap)`。合起來是一次 prune 後的寫入：先在記憶體中 prune，再一次 `save`。
  6. 語音一致開啟、pending 中主語系有選擇且不等於目前主語音時，`set_main_voice(chosen)`。
  7. 以 `manager.settings.snapshot(manager.defaultVoiceName)` 鏡像五個參數到 `speech_section()`；取不到 section（`KeyError`）時略過（D4）。
  8. 清除 pending 與 D1 記錄；引擎一致的初始值更新為目前值。
- `discard()`：`edit.discard()`、清除 pending 與 D1 記錄、引擎一致旗標還原為初始值、三個 pending 旗標重新取自政策。
- `close()`：`edit.close()`。

### 5. `SpeechRoleSettingsPanel`

- `makeSettings`：非 WorldVoice 或 manager 未 ready 時的提示不變。其餘情況建立 presenter：
  - `speech_section=lambda: config.conf["speech"][getSynth().name]`；
  - `set_main_voice`：WorldVoice 時 `getSynth().voice = name`，並寫 `config.conf["speech"]["WorldVoice"]["voice"] = name`，同現行。
- 所有 handler 只讀 widget、呼叫 presenter、再把 presenter 的結果寫回 widget。`sliderEnable`/`sliderDisable` 的條件改用 `presenter.capabilities`。
- `onSave`：
  - 依序 `set_*_consistency(checkbox 值)`，這三個旗標本來就在勾選時即時呼叫，這裡是保險；
  - `try: presenter.apply()`；
  - `except Exception as error`：記 log、顯示既有的錯誤訊息，然後 `raise ValueError(...) from error`（D6）。
- `onDiscard` → `presenter.discard()`；`_onDestroy` → `presenter.close()`。
- `NO_SELECT` 只用於顯示（第一個選項文字）；presenter 以 "" 表示未選。

### 6. `pipelineLog.py`、`LogSettingsPanel`、`GlobalPlugin`

```python
class PipelineLogService:
	def __init__(self, conf_provider=lambda: config.conf, exporter=None): ...   # exporter 預設 pl.export
	@property
	def enabled(self) -> bool
	def enable(self) -> None
	def disable(self) -> None
	def export(self) -> None      # 例外記 log，不傳出（同現行 try/except）

def confirm_enable(*, allow_cancel: bool) -> int   # wx.YES / wx.NO / wx.CANCEL，訊息與現行相同
def ask_export() -> bool
def ask_disable_on_start() -> bool
```

- plugin `enable_log_record`：`confirm_enable(allow_cancel=False) == wx.YES` 時 `enable()` 並 `ui.message`。
- `disable_log_record`：`disable()`；`ask_export()` 為 True 時 `export()` 並 `ui.message`（順序同現行）。
- `check_log_record`：已啟用且 `ask_disable_on_start()` 時 `disable()` 再 `export()`。
- `LogSettingsPanel.isValid`（D7）：要啟用時 `confirm_enable(allow_cancel=True)`：
  - CANCEL：取消勾選並回傳 False（同現行）；
  - NO：取消勾選、同步 stage 核取方塊，回傳 True；
  - YES：回傳 True。
- `LogSettingsPanel.onSave`：
  - 勾選且之前未啟用：`enable()`；
  - 未勾選且之前啟用：`disable()`，`ask_export()` 為 True 時 `wx.CallAfter(service.export)`；
  - 最後 `super().onSave()`。
- `self.confirm` 欄位刪除。

### 7. `generics/coreArchive.py`

```python
def extract_core_archive(archive_path: str, workspace_path: str) -> list[str]:
	"""Extract every member; return the names skipped because they are in use. Raises BadZipFile when corrupt."""
```

- `testzip()` 回傳壞檔名，或拋出 `BadZipFile`/`RuntimeError` 時，一律改拋 `BadZipFile`。逐檔 extract 失敗的檔名回傳，並各記一筆 warning（同現行）。結尾的 info/warning log 移到此函式內。
- `installTasks._extract_core_archive(archive_path, workspace_path)`：
  - 開頭的 info log 保留；
  - `try: extract_core_archive(...)`；
  - `except BadZipFile`：記 error（同現行）；
  - `except Exception`：`log.exception`；
  - `finally`：移除 archive（同現行）。
- 模組以 `_load_core_archive()` 依路徑載入。
- plugin `onFileImport`：
  - `try: os.makedirs(...); extract_core_archive(...)`；
  - `except Exception`：`log.exception` 並顯示「Import fail」，這也涵蓋損毀的 zip；
  - `else`：照舊詢問重新啟動。

### 8. `guard_errors`

- `got_error_callback(panel)`：
  - `dialog = wx.GetTopLevelParent(panel)`；
  - `dialog.onCancel(None)`；
  - `wx.CallAfter(gui.mainFrame.popupSettingsDialog, type(dialog))`。
- `WorldVoiceSettingsDialog` 刪除 `self.__class__.wvd = self`、`_onDestroy` 及其 `Bind`。

## 測試

1. `tests/test_role_repository.py`：
   - `voice_for` 的精確與主語言回退；
   - `assignments` 忽略純量與無 voice 的 section；
   - `save` 保留純量；
   - `prune` 等價於舊 `onKeepEngineConsistent`（以舊程式的已知輸入輸出表驗證）；
   - `assign`。
2. `tests/test_main_locale_policy.py`：
   - `EngineConsistency.visible` 與 `persist`；
   - `VoiceConsistency.follow` 開或關、語言為空時回退 `getLanguage`；
   - `ParameterConsistency.copy_from` 每個 state 一次 update（移植 `test_consistency_preview_updates_each_voice_in_one_batch`）；
   - `shared_section` 三種情況。
3. `tests/test_role_presenter.py`：移植 `test_voice_settings_transaction.py` 中所有 role 面板測試，以及 `test_f4_voice_state.py` 的 `test_preview_b_while_a_is_playing_then_cancel_restores_next_segment`、`test_ui_consistency_copy_is_atomic_for_worker_activation`。原斷言全數保留，並新增：
   - D1：開 → 關還原；開 → 關 → OK 不同質化；已開時關閉不動作；
   - D4：切換主語音後，鏡像用的是新主語音的參數；
   - apply 失敗時 role、旗標、speech 區段都未寫。
4. 面板：以 AST 載入 `SpeechRoleSettingsPanel`，驗證 `onSave` 把 presenter 例外轉成 `ValueError` 並顯示訊息（D6）。
5. `tests/test_pipeline_log.py`：service 的 enable/disable/export 例外吞掉；`LogSettingsPanel.isValid` 選 NO 時取消勾選並回傳 True（D7）。
6. `tests/test_core_archive.py`：正常解壓、損毀 zip 拋 `BadZipFile`、單檔失敗回傳 skipped；`installTasks` 不論成敗都移除 archive。
7. 守門測試：成功條件 2。
8. 既有 `tests/test_voice_config_repository.py` 不改即通過。
