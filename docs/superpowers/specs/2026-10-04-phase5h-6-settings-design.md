# 階段 5½ + 6：快速修正、pipeline 設定單一事實來源

日期：2026-10-04。
基準：`master`（`bc6c869`）。分支：`phase5h-6-settings`。
狀態：使用者要求 5½ 與 6 一起實作，並在無重大決策時自動走完 spec → plan → 實作 → review。

本文件涵蓋 [`refactor.md`](../../../refactor.md) §9 的階段 5½ 與 6，對應 §1.1、§5.1–5.3、§6.2、§6.4、§7 的 D2、D3、D5、D8、D9、D11、D12、D14，以及 §8 的 `F401`。

## 需求與範圍

### 階段 5½（快速修正）

1. **D2**：`LogSettingsPanel` 可以開關 `punctuation_wait_factor` stage 的 log。實作上由階段 6 的 `STAGES` 產生清單（見設計 §4），並以守門測試確認面板、confspec、`STAGES` 三者一致。
2. **D3**：`GlobalPlugin` 在 secure mode 或 wx 物件已刪除時，`terminate` 仍完成其餘清理。
   - `__init__` 第一行設定 `self.submenu_item = None`（在 secure mode 的 return 之前）。
   - `terminate` 改攔 `RuntimeError`（wxPython Phoenix 對已刪除 C++ 物件拋出的例外）；`wx.PyDeadObjectError` 已不存在。
3. **D8**：VE 與 Cerence 的 `_stop_player` 與 `cancel` 中 `_real_player.stop()` 失敗時，先 `host.latch_control_error(error)` 再照原樣 raise，與 `LeasedPlayer.stop`、RHVoice 一致。兩個檔案各自修改，不共用程式碼。
4. **D9**：Cerence `Voice.voices` 的 `"engine": "Cerence"` 改為 `cls.engine`。
5. **D14**：`pipeline/__init__.py` 的字串型別註解指向實際存在的名稱：`SpeechCommand`（取代不存在的 `BaseSpeechCommand`）、`VoiceManager`、`Voice`，以 `TYPE_CHECKING` 匯入。
6. **死碼**：
   - `SpeechPipelinePanel` 的 8 個只有 `pass` 的 handler 與其 `self.Bind`；
   - `SpeechPipelinePanel.sliderEnable/sliderDisable`（無人呼叫）；
   - `SpeechPipelinePanel.onScopeSelectionChange` 與 `self._scope`（階段 6 後 scope 由 service 處理）。
   - `SpeechRoleSettingsPanel`、`LogSettingsPanel` 的同名 `sliderEnable/sliderDisable` 有人呼叫，保留。
7. **F401**：刪除 `ruff` 列出的 12 個未使用 import。

### 階段 6（設定單一事實來源）

1. `config.conf["WorldVoice"]["pipeline"]` 是 pipeline 13 個值**唯一**的持久化位置。
   - 主驅動的 11 個 pipeline `DriverSetting` 改為 `useConfig=False`，NVDA 不再把它們讀寫到 `config.conf["speech"]["WorldVoice"]`。
   - `get_effective_pipeline_settings` 的字串反射（`_runtime_value`）、`apply_pipeline_settings_to_synth`、`apply_pipeline_settings_to_speech_config` 刪除。
2. 一張 `PIPELINE_SETTINGS` 表（`PipelineSettingSpec`）產生：預設值、config key 順序、`config.conf.spec["WorldVoice"]["pipeline"]`、主驅動的 `DriverSetting`。`PipelineSettings` dataclass 保留手寫欄位，以守門測試確認欄位與表一致。
3. `PipelineSettingsService`（Facade + Observer）：`get()`、`update(**changes)`、`effective(supports_roles)`、`subscribe/unsubscribe`。主驅動 descriptor、UI 面板、`WorldVoiceVoiceSettingsPanel` 都只呼叫 `update`。
4. `STAGES` registry 是 9 個 filter stage 順序、log key 的唯一來源；`register_stages`／`unregister_stages`／`order_move_to_start_register`／`order_move_to_end_register` 由它產生。log confspec 與 `LogSettingsPanel` 也由它產生。
5. stage 簽名統一為 `fn(speechSequence, settings, ctx)`；`SpeechContext` 取代 stage 內的 `getSynth()`、`synth._numlan`、`synth._voiceManager`、`synth.speechSymbols`。
6. `PipelineScope` 取代五個 scope 函式與模組全域 `_last_scope_application`。
7. 主驅動：11 組 pipeline getter/setter 改為 descriptor；`supportedSettings`／`allSupportedSettings` 由同一個函式產生；六個語音參數 setter 共用一個 helper。
8. 隨之消失：D5（一次 OK 寫 3–4 遍）、D11（`loadSettings` 寫 config）、D12（`number_wait_factor` 為 0 時仍去空白）。

### 已做的決定（無需使用者裁示，記錄於此）

1. **預設值以 pipeline confspec 為準。** 目前 `DriverSetting.defaultVal` 與 pipeline confspec 不一致（global 50 對 10、number/item/sayall/chinesespace 0 對 10）。
   - 既有使用者不受影響：每次 WorldVoice 載入時 setter 都把值寫進 pipeline 區段，與 confspec 預設不同的值已被存下。
   - 若改成 `DriverSetting` 的預設值，存值剛好等於舊 confspec 預設（因此沒被存下）的使用者會被改值，所以不改 confspec。
   - 唯一的行為差異：**全新安裝**第一次載入 WorldVoice 時，等待係數從 50/0 變成 confspec 的 10/10。這也是 pipeline 面板一直顯示的預設值。
2. **NVDA 語音設定對話框按「取消」仍會還原 pipeline 值。** 以往靠 `loadSettings` 從 speech 區段重設屬性。改為 `WorldVoiceVoiceSettingsPanel` 在 `makeSettings` 時快照 `pipeline_settings.get()`，`onDiscard` 時把有差異的欄位 `update` 回去（只在目前 synth 是 WorldVoice 時）。
   - 不採用「暫存 overlay、saveSettings 才寫入」：WorldVoice 沒有註冊 `pre_configSave`，overlay 會讓設定環（settings ring）的變更在存檔時遺失。寫入即生效（write-through）維持目前的設定環與 profile 行為。
3. **cni 與 item_wait_factor stage 永遠註冊。** 以往 WorldVoice 依設定值 register/unregister；scope=all 時本來就永遠註冊。兩個 stage 在設定關閉時本來就原樣傳遞，輸出不變。唯一差異是 pipeline log 開啟時這兩個 stage 也會記一筆 before/after 相同的紀錄。
4. **D12**：`number_wait_factor` 的縮放等待 ≤ 0 時整段原樣傳遞，不再 `_remove_space`。
5. `LogSettingsPanel` 的項目順序改為 `STAGES` 順序（執行順序）。

### 成功條件

1. 完整測試全部通過；新增的守門與行為測試涵蓋下文每一節。
2. addon 內不再出現：`get_effective_pipeline_settings`、`_runtime_value`、`apply_pipeline_settings_to_synth`、`apply_pipeline_settings_to_speech_config`、`apply_global_pipeline_scope`、`apply_pipeline_after_worldvoice_end`、`clear_global_pipeline_scope`、`apply_worldvoice_pipeline`、`clear_pipeline`、`_last_scope_application`、`static_register`、`dynamic_register`、`with_speech_sequence_log`，以及 pipeline 的 10 個 `get_*` 存取器。由守門測試強制。
3. `config.conf["WorldVoice"]["pipeline"]` 的直接讀寫只出現在 `pipeline/settings.py`（守門測試）。
4. `pipeline/__init__.py` 的 stage 不再呼叫 `getSynth()`；只剩除錯工具 `with_order_log`（階段 8 保留，讀 `synth.order`）。stage 經由 `pipeline/context.py` 的 `current_context()` 取得 synth 資訊。
5. `ruff check`（範圍同 refactor.md 附錄）的 `F401`、`F821` 為 0；`ruff format --check addon` 通過。
6. `driver/<Engine>/driver/` 無變動；Neural 未被追蹤。

### 不在範圍內

- 階段 7（Role 設定、`RolePanelPresenter`、D1/D4/D6/D7、`PipelineLogService`、`guard_errors`、`WorldVoiceVoiceSettingsPanel` monkey-patch 去留）。
- §5.4 的 DRY（`_insert_between`、`_split_by`）、`PipelineLog` 惰性建立、`with_speech_sequence_log` 讀 config 次數的最佳化。
- 主驅動 `speak()` 內四步改為 `placement="driver"` 的 stage（§5.1 的延伸）；四個函式只改為接收 `ctx`。
- 設定檔（profile）切換時重新套用 scope：目前也沒有處理，維持現狀。
- VE callback `finally` 中只 `record_error` 的 stop、VE `blocked` 路徑的 stop（refactor.md 未列）。
- `with_order_log` 與其被註解的裝飾器保留（階段 8 使用者決定）；只把 wrapper 改成接受任意參數，讓它仍可套在新簽名的 stage 上。

## 設計

### 1. `pipeline/settings.py`：表、dataclass、service

```python
@dataclass(frozen=True)
class PipelineSettingSpec:
	key: str                       # config key，也是 PipelineSettings 欄位名
	kind: type                     # bool | int | str
	default: object
	driver_id: str | None = None   # 主驅動 DriverSetting id；None 表示不是 driver setting（scope）
	label: str | None = None       # 已翻譯的 DriverSetting 標籤
	display_name: str | None = None
	ring: bool = True              # availableInSettingsRing；cni 為 False（同現行）
	min_step: int = 1              # NumericDriverSetting
	normalize: Callable[[object], object] | None = None

PIPELINE_SETTINGS: tuple[PipelineSettingSpec, ...]
```

- 表的順序是主驅動設定對話框的順序：`ignore_comma_between_number`（cni）、`number_mode`（nummod）、`global_wait_factor`（min_step 10，normalize 為 `int(v) // 10 * 10`）、`number_wait_factor`、`pair_wait_factor`、`item_wait_factor`、`sayall_wait_factor`、`chinesespace_wait_factor`、`punctuation_pause_enabled`、`remove_punctuation_characters`、`punctuation_wait_factor`，再加上非 driver 的 `scope`、`punctuation_pause_characters`（normalize 為 `str(v).strip()`）。
- 標籤、`display_name` 與目前主驅動的 `_()` 字串完全相同；模組呼叫 `addonHandler.initTranslation()` 取得 `_`。
- 由表產生：`DEFAULT_PIPELINE_SETTINGS`、`PIPELINE_CONFIG_KEYS`、`PIPELINE_CONFSPEC`。confspec 依 kind 產生：`boolean(default=...)`、`integer(default=...,min=0,max=100)`、`string(default="...")`，預設值與目前字面值相同。
- `PipelineSettings` 改為 `frozen=True`，保留 `scaled_*` 方法，新增 `effective(supports_roles: bool) -> PipelineSettings`。它是 `get_effective_pipeline_settings` 非 WorldVoice 分支的純函式版本：
  - `supports_roles=True`：原值；
  - 否則 `scope != "all"`：等待與標點相關值歸零（同現行）；
  - 否則：`ignore_comma_between_number = bool(global_factor_units * ignore_comma_between_number)`（同現行）。
- `ConfigPipelineRepository(conf_provider)`：`load() -> PipelineSettings`（沿用 `_get_value` 的缺值處理與型別轉換）、`save(changes: Mapping)`（只寫傳入的 key）。`conf_provider` 預設 `lambda: config.conf`，每次呼叫才取，讓 profile 切換自然生效。
- `PipelineSettingsService(repository)`：
  - `get()`：每次從 repository 讀，不快取（profile 切換無需失效處理；成本與現行每個 stage 呼叫 `load_pipeline_settings` 相同）。
  - `update(**changes) -> PipelineSettings`：未知 key 拋 `KeyError`；依 spec 轉型、normalize；只寫與目前值不同的 key；有變更時依序呼叫訂閱者 `listener(settings)`；回傳新值。
  - `effective(supports_roles)`：`get().effective(supports_roles)`。
  - `subscribe(listener)`／`unsubscribe(listener)`：強參照清單；訂閱者例外記 log 後繼續通知其他訂閱者。
- 模組單例：`pipeline_settings = PipelineSettingsService(ConfigPipelineRepository())`。
- 刪除 `save_pipeline_settings`、`load_pipeline_settings`（由 repository 取代）、`get_effective_pipeline_settings`、`_runtime_value`、`apply_*`、scope 函式、`_last_scope_application`、`_load_scope_functions`。

### 2. `pipeline/context.py`：`SpeechContext`

```python
@dataclass(frozen=True)
class SpeechContext:
	supports_roles: bool                  # 目前 synth 是 WorldVoice
	language: str | None
	number_language: str                  # "default"、locale，或泛用 synth 的 "Windows"
	speech_symbols: object | None
	default_voice: object | None
	voice_for_language: Callable[[str], object | None]

GENERIC_CONTEXT = SpeechContext(False, None, "Windows", None, None, lambda language: None)

def current_context() -> SpeechContext: ...
```

- `current_context()` 呼叫 `getSynth()`；例外或回傳 None 時回傳 `GENERIC_CONTEXT`；synth 名稱為 `"WorldVoice"` 時回傳 `synth.speech_context()`，否則 `GENERIC_CONTEXT`。
- 主驅動新增 `speech_context()`：`SpeechContext(True, self.language, self._numlan, self.speechSymbols, self._voiceManager.defaultVoiceInstance, self._voiceManager.getVoiceInstanceForLanguage)`。
- 對應關係：
  - `get_translate_table(ctx)` 用 `ctx.number_language`、`ctx.speech_symbols`；
  - `inject_number_language` 以 `ctx.supports_roles` 取代 `hasattr(synth, "_voiceManager")`；
  - `inject_number_mode` 以 `ctx.supports_roles` 取代迴圈內的 `getSynth().name`；
  - `_insert_WVLangChangeCommand_between_number(seq, ctx)` 用 `ctx.number_language`、`ctx.language`；
  - `deduplicate_language_command(seq, ctx)` 用 `ctx.default_voice`、`ctx.voice_for_language`、`ctx.language`。

### 3. `pipeline/__init__.py`：stage 與 `STAGES`

- 9 個 stage 函式簽名改為 `fn(speechSequence, settings: PipelineSettings, ctx: SpeechContext)`，`settings` 是已套用 `effective` 的值；函式內不再呼叫任何 `get_*` 或 `getSynth()`。
- `number_wait_factor`：`settings.scaled_number_wait() <= 0` 時原樣傳遞（D12）。
- `_translate_number` 的 pair 模式改由參數取得 `pause`（`settings.scaled_pair_wait()`）。

```python
@dataclass(frozen=True)
class Stage:
	log_key: str
	fn: Callable[[Iterable[SpeechCmd], PipelineSettings, SpeechContext], Iterable[SpeechCmd]]
	handler: Callable[[Iterable[SpeechCmd]], list | Iterator]   # 建構時綁定一次，供 filter_speechSequence 以 identity 註冊

STAGES: tuple[Stage, ...] = (
	Stage("apply_speech_dictionaries", apply_speech_dictionaries),
	Stage("ignore_comma_between_number", ignore_comma_between_number),
	Stage("number_language", inject_number_language),
	Stage("number_mode", inject_number_mode),
	Stage("chinesespace_wait_factor", inject_chinese_space_pause),
	Stage("item_wait_factor", item_wait_factor),
	Stage("punctuation_wait_factor", inject_punctuation_pause),
	Stage("number_wait_factor", number_wait_factor),
	Stage("speech_viewer", speech_viewer),
)
```

- 這是目前 `order_move_to_end_register` 的 FIFO 順序（即實際執行順序）。
- `handler(seq)`：取 `ctx = current_context()`、`settings = pipeline_settings.effective(ctx.supports_roles)`，再以與現行 `with_speech_sequence_log` 相同的條件與格式記 log（label 為 `log_key`），然後回傳 `fn(seq, settings, ctx)`。handler 由 `Stage` 持有，NVDA `HandlerRegistry` 的 weakref 因此有效。
- `register_stages()`：`speech_dictionary.install()`，依序 register 全部 handler，再 `order_move_to_start_register()`。
- `unregister_stages()`：unregister 全部 handler，再 `speech_dictionary.uninstall()`。
- `order_move_to_start_register()`：逆序 `moveToEnd(handler, False)`；`order_move_to_end_register()`：順序 `moveToEnd(handler, True)`。兩者保留原名（主驅動 `detect_language_timing` 使用前者；後者是階段 8 決定保留的除錯工具）。
- 刪除 `static_register`、`dynamic_register`、`unregister`、`with_speech_sequence_log`、10 個 `get_*`。
- `with_order_log` 的 wrapper 改為 `wrapper(speechSequence, *args, **kwargs)`，其餘不變；被註解的 `# @with_order_log(...)` 保留。
- D14：`if TYPE_CHECKING:` 匯入 `SpeechCommand`、`VoiceManager`、`Voice`；`SpeechCmd = Union[str, "SpeechCommand"]`。

### 4. log 開關由 `STAGES` 產生

- 主驅動 confspec：`"log": {"enable": "boolean(default=false)", **{stage.log_key: "boolean(default=false)" for stage in STAGES}}`。key 集合與現行相同（9 個）。
- `LogSettingsPanel.settings` 由 `STAGES` 依序產生，標籤取自面板內的 `_LOG_LABELS` dict（保留 `_()` 供翻譯抽取），新增 `"punctuation_wait_factor": _("punctuation wait factor")`。缺標籤時退回 key。
- 守門測試：`_LOG_LABELS` 的 key 集合 == `STAGES` 的 log key 集合 == 主驅動 confspec `log` 扣掉 `enable`（以 AST 讀面板檔）。

### 5. `pipeline/scope.py`：`PipelineScope`

```python
class PipelineScope:
	def __init__(self, settings: PipelineSettingsService, register, unregister): ...
	def worldvoice_started(self) -> None
	def worldvoice_ended(self) -> None
	def attach_global(self) -> None
	def detach_global(self) -> None
	@property
	def registered(self) -> bool
```

- 規則：`want = worldvoice_active or (global_attached and settings.get().scope == "all")`；`want` 與 `registered` 不同時才呼叫 register/unregister。建構時訂閱 settings 變更，變更後重算。
- 模組單例 `pipeline_scope = PipelineScope(pipeline_settings, register_stages, unregister_stages)`。
- 呼叫端：
  - 主驅動 `_initialize`：以 `pipeline_scope.worldvoice_started()` 取代 `apply_worldvoice_pipeline()`。
  - 主驅動 `terminate`：以 `worldvoice_ended()` 取代 `clear_pipeline`。
  - `GlobalPlugin.__init__`：`attach_global()`（取代「非 WorldVoice 時 `apply_global_pipeline_scope`」）。
  - `GlobalPlugin.terminate`：`detach_global()`。
  - `on_worldvoice_start/end` 與其 `WVStart/WVEnd` 註冊刪除；`WVStart`/`WVEnd` 本身保留（公開 extension point，主驅動照常 notify）。
- 與現行等價的狀態轉換：
  - 非 WorldVoice、scope=all → 已註冊；
  - 切到 WorldVoice → 仍註冊（以往是先清再註冊）；
  - WorldVoice 結束 → scope=all 時仍註冊，否則註銷；
  - UI 把 scope 改成 WorldVoice 且目前非 WorldVoice → 註銷。

### 6. 主驅動

- confspec：`"pipeline": dict(PIPELINE_CONFSPEC)`、`"log"` 如 §4。
- `_driver_settings(capabilities: frozenset | None) -> list`：
  - Voice、Variant、Rate、（RateBoost）、Pitch、（Inflection）、Volume、uwv；
  - 接著依表順序產生 pipeline 設定，在 cni 之後插入 numlan。
  - `capabilities is None` 時包含 RateBoost 與 Inflection。
  - `supportedSettings` 傳入預設語音的 capabilities；`allSupportedSettings` 傳入 None。
  - 順序與現行完全相同。
- `_pipeline_driver_setting(spec)`：bool → `BooleanDriverSetting`；int → `NumericDriverSetting(minStep=spec.min_step)`；str → `DriverSetting`。皆 `availableInSettingsRing=spec.ring`、`defaultVal=spec.default`、`useConfig=False`；`display_name` 有值時傳入。
  - cni 現行沒有設定 `availableInSettingsRing`（預設 False），因此表中 cni 為 `ring=False`，其餘為 True。
- `class _PipelineSetting`（descriptor）：`__get__` 回傳 `getattr(pipeline_settings.get(), key)`；`__set__` 呼叫 `pipeline_settings.update(**{key: value})`。類別定義後依表 `setattr(SynthDriver, spec.driver_id, _PipelineSetting(spec.key))`。
- 刪除 11 組 `_get_x/_set_x`（`cni`、`nummod`、`globalwaitfactor`、`numberwaitfactor`、`pairwaitfactor`、`itemwaitfactor`、`sayallwaitfactor`、`chinesespacewaitfactor`、`punctuationpauseenabled`、`removepunctuationcharacters`、`punctuationwaitfactor`）。`numlan`、`uwv`、`availableNummods`、`availableNumlans` 保留。
- 全域等待係數與 `VoiceManager.waitfactor`：
  - `_apply_pipeline_settings(settings)` 設 `self._voiceManager.waitfactor = min(settings.global_wait_factor // 10, 9)`。即使值沒變也每次都設：VoiceManager 從 0 起算，而它的 setter 會把值寫進每個語音的設定；
  - `_initialize` 建好 VoiceManager 後呼叫一次並 `pipeline_settings.subscribe(self._apply_pipeline_settings)`；
  - `terminate` 以 `_run_cleanup` 取消訂閱；
  - `loadSettings`：`super().loadSettings()` → `_apply_pipeline_settings(pipeline_settings.get())` → `self._voiceManager.reload()`，不再寫 config（D11）。
- 刪除 `saveSettings` 覆寫。
- 語音參數：`_set_volume/_set_rate/_set_pitch/_set_inflection/_set_variant/_set_rateBoost` 都呼叫 `_set_voice_parameter(name, value)`。它負責：設值、commit，以及 `KeepMainLocaleParameterConsistent` 時呼叫 `onVoiceParameterConsistent`。getter 不變。
- `speak()`：`ctx = self.speech_context()`，`deduplicate_language_command(seq, ctx)`。

### 7. UI

- `SpeechPipelinePanel`：
  - 初始值取自 `pipeline_settings.get()`。
  - `onSave` 只呼叫一次 `pipeline_settings.update(...)`，傳入全部 13 個值；global 為 slider 值 × 10。scope 生效由 `PipelineScope` 訂閱處理。不再呼叫 `apply_*`，也不再呼叫 `getSynth().saveSettings()`（D5）。
  - 死碼依 5½ §6 刪除。
- `WorldVoiceVoiceSettingsPanel`（`VoiceSettingsDialogs.py`）：
  - 標點字元讀 `pipeline_settings.get().punctuation_pause_characters`；
  - `onSave` 以 `pipeline_settings.update(punctuation_pause_characters=...)` 取代直接寫 config；
  - 新增 `makeSettings` 快照與 `onDiscard` 還原（決定 2）；`onSave`（NVDA 的「套用」）後更新快照，讓之後的「取消」保留已套用的值。
- `LogSettingsPanel`：§4。
- `GlobalPlugin`：§5 與 D3。`check_log_record` 等 log 開關邏輯不動（階段 7）。

### 8. 其他呼叫者

- `sayAll.py`：`pipeline_settings.effective(current_context().supports_roles).scaled_sayall_wait()`。
- 所有測試中對被刪名稱的 stub、呼叫，改用新 API。

### 9. 錯誤處理

- `PipelineSettingsService.update` 對未知 key 拋 `KeyError`，對無法轉型的值讓 `ValueError`/`TypeError` 傳出（呼叫端是 UI 與 NVDA setattr，與現行 `int(...)` 行為一致）。
- 訂閱者例外：`log.error(..., exc_info=True)` 後繼續，不中斷其他訂閱者，也不回滾已寫入的 config。
- `current_context()` 吞掉 `getSynth()` 例外並回傳泛用 context（同現行 `get_effective_pipeline_settings`）。
- `PipelineScope` 的 register/unregister 例外會傳出；主驅動 `terminate` 已以 `_run_cleanup` 包住。

## 測試

新增或改寫（tab 縮排不強制，`tests/` 不做 format）：

1. `tests/test_pipeline_settings_service.py`：
   - 表 ↔ dataclass 欄位 ↔ `DEFAULT_PIPELINE_SETTINGS` ↔ `PIPELINE_CONFSPEC` 一致，且 confspec 字串與舊字面值的預設等價；
   - `update` 轉型、normalize（global 取整到 10、字元 strip）；
   - 只寫有變更的 key；
   - 未知 key 拋錯；
   - 通知訂閱者、訂閱者例外不中斷；
   - `effective` 三種分支（取代 `test_punctuation_removal_settings.py` 的舊 API 測試）；
   - `get` 反映 conf_provider 的切換（profile）。
2. `tests/test_pipeline_scope.py`：attach/detach × worldvoice start/end × scope 變更的狀態表；每次轉換 register/unregister 的呼叫次數。
3. `tests/test_pipeline_stages.py`：
   - `STAGES` 順序；
   - `register_stages` 後 handler 的最終順序，以會記錄順序的假 `filter_speechSequence` 驗證；
   - `unregister_stages` 全部註銷並解除 speech dictionary；
   - handler 依 log 設定記錄；
   - D12；
   - number_mode/number_language 在 WorldVoice 與泛用 context 下的輸出；
   - `pipeline/__init__.py` 只有 `with_order_log` 使用 `getSynth`（AST）。
4. 改寫 `tests/test_pipeline_punctuation_pause.py`：stub 新的 settings/context 介面，改以 stage 函式三參數呼叫。
5. 主驅動：
   - descriptor 讀寫經 service；
   - `supportedSettings`／`allSupportedSettings` 的 id 順序與現行相同，pipeline 設定 `useConfig=False`；
   - `loadSettings` 不寫 pipeline config；
   - waitfactor 同步與取消訂閱；
   - 六個語音參數 setter 行為不變。
6. UI：
   - `SpeechPipelinePanel.onSave` 只呼叫一次 `update`；
   - log 標籤守門（§4）；
   - `WorldVoiceVoiceSettingsPanel` 的 discard 還原；
   - `GlobalPlugin` 的 D3（secure mode 下 terminate；`removeMenu` 拋 `RuntimeError`）。
   - 都沿用現有 `ast` 抽類別的作法。
7. D8：`tests/test_vocalizer_segment_drain.py`（VE、Cerence 參數化）——`_real_player.stop` 在 `cancel` 中失敗後，下一個 segment 收到 `SEGMENT_FAILED`；`_stop_player` 失敗同樣 latch。
8. D9：Cerence `voices()` 的 `engine` 欄位等於 `cls.engine`。
9. 守門：成功條件 2、3、4 的名稱與存取限制（AST／文字掃描 `addon/`，排除內層驅動）。
