# 階段 10a：VoiceManager 資料結構收斂與 VoiceFacade 瘦身

日期：2026-10-05。
基準：`master`（`4e18937`，階段 11 完成）。分支：`phase10a-voice-manager`。
狀態：使用者要求剩餘階段（10a、12、13、14、16）依序自動執行（spec → plan → 實作 → Fable review），無重大決策不停。使用者已決定：
- 原 10b-1 併入本階段；
- 10b-2（`EngineDescriptor`）不做，採 `refactor.md` §3.2 方案 (A)：`driver.Voice` 仍是外部外掛唯一的子類化點，Neural 式外掛必須繼續可用。

本文件是 [`refactor.md`](../../../refactor.md) §11 的階段 10a，對應 §1.2、§3.1、§3.2（10b-1 部分）、§3.3、§8，以及 §9 的 C3、C5、C6、C7（`VoiceMeta`、`keepMainLocaleEngineConsistent` 兩項）。

## 需求與範圍

### 1. `VoiceManager` 的每引擎資料只有一份

- 現況：四份平行結構。
  - `_resources: list[EngineResource]`：給清理用；
  - `_sessions`、`_bindings`：`_publish` 從 `EngineResource` 拆欄位進去；
  - `_specs`：`_publish` 填入，`_setVoiceDatas` 再排序成 `table`。
- 改為 `_resources: dict[str, EngineResource]`，以引擎名為鍵，插入順序就是開啟順序。
- `EngineResource` 加兩個欄位：
  - `published: bool = False`；
  - `voices: tuple[VoiceSpec, ...] = ()`。
- `_open_engine` 在 `session.open()` 之前放進 dict，維持「先登記清理再開啟」。
- `_publish` 設 `voices = adapter.list_voices()` 與 `published = True`。`list_voices` 仍只呼叫一次，時機不變。
- 查詢只看已發布的資源，與現行「只有 bound 的資源可見」等價：`resolve_playback`、`getVoiceCapabilities`、`getVoiceVariants`、`playback_ports`、`_createVoiceInstance`。
  - 未發布或已終止時：`resolve_playback` 回傳 `None`；其餘以 `KeyError` 失敗，同現行對 `_sessions[...]` 的存取。
- `terminate` 的第一步改為把每個資源的 `published` 設為 `False`，取代清空 `_sessions`／`_bindings`；其餘順序不變。
- `_createVoiceInstance` 用 `resource.voice_class`，不再查 `READY_ENGINE_CLASS`。同一個事實只剩一個來源。

### 2. 引擎類別由組裝端注入，刪除模組可變全域

- 刪除：
  - `engine.READY_ENGINE_CLASS` 與 `refresh_ready_engine_classes`；
  - `EngineType` 別名。UI 的 2 處改用 `ENGINE_SPECS`。
- `engine` 模組新增 `ready_engine_classes(engine_config) -> dict[str, type]`，回傳 `load_enabled_engine_classes(ENGINE_SPECS, engine_config, logger=log)` 的新 dict，不保留任何狀態。
- `VoiceManager` 新增必填的 keyword 參數 `engine_classes: Mapping[str, type]`。
  - 主驅動呼叫 `ready_engine_classes(config.conf["WorldVoice"]["engine"])` 後傳入，讀設定的時機與現行相同（建構 VoiceManager 時）。
  - `_initialize` 改為 `for name, cls in engine_classes.items()`。`load_enabled_engine_classes` 已依 spec 順序、只回傳啟用且 ready 的引擎，所以原本迴圈內的 `get_engine_enabled` 與 `.get(...) is None` 檢查是重複的，一併刪除。
  - `voiceManager.py` 不再 import `.engine`。
- `engine.get_engine_enabled` 對未知引擎的布林轉換改用 `discovery` 的同一個函式，`_coerce_bool` 改名為公開的 `coerce_bool`，只留一份。
- **與 `refactor.md` 的差異**：§3.3 建議的 `EngineRegistry(specs, engine_config)` 類別不建立。它唯一的職責就是「specs + 設定 → ready classes」，而這已經是 `load_enabled_engine_classes` 這一個純函式。包成類別只多一層，沒有第二個讀者（UI 只用 `ENGINE_SPECS`、`get_engine_enabled`、`get_engine_label`、`get_engine_default_enabled`）。注入 mapping 就足以達到 DIP 與可測試性。

### 3. `VoiceCatalog`：不可變的語音目錄

- 新模組 `voiceCatalog.py`：

```python
@dataclass(frozen=True)
class VoiceCatalog:
	table: tuple[VoiceSpec, ...]                 # 依 engine, language, name 排序
	by_name: Mapping[str, VoiceSpec]             # 唯讀
	voice_infos: "OrderedDict[str, VoiceInfo]"  # NVDA availableVoices 期待的型別
	all_languages: tuple[str, ...]               # 全部語音的主要 locale，已排序

	@classmethod
	def from_specs(cls, specs: Iterable[VoiceSpec]) -> "VoiceCatalog": ...

	def readable_name(self, locale: str) -> str: ...  # "描述 - locale"，無描述時回傳 locale

EMPTY_CATALOG = VoiceCatalog.from_specs(())

def group_by_primary_locale(specs: Iterable[VoiceSpec]) -> dict[str, list[str]]: ...
```

- `from_specs` 同名時後者覆蓋前者，與現行 `_specs[spec.name] = spec` 相同。
- `group_by_primary_locale` 取代 `groupByField` 與 `groupVoicesByPrimaryLocale`。
- `VoiceManager`：
  - `catalog` 屬性初始為 `EMPTY_CATALOG`，`_setVoiceDatas` 由已發布資源的 `voices` 建一次。
  - 以下 NVDA／UI 面向的成員保留原名與回傳值，改為轉發 catalog：`table`、`voiceInfos`、`allLanguages`、`getVoiceSpec`、`localesToNamesMap`（用 `catalog.readable_name`）。
  - `languages`、`localeToVoicesMap` 仍依 `engine_consistency.visible(...)` 在每次存取時計算，因為可見集合隨預設語音的引擎變動。
  - `defaultVoiceName` setter、`waitfactor` setter、`getVoiceNameForLanguage` 改讀 catalog。
- **C3 的處理**：兩個 `_getLocaleReadableName` 格式不同，但用途也不同。
  - manager 的格式「描述 - locale」給角色面板。它移到 `VoiceCatalog.readable_name`，成為唯一一份。
  - 主驅動的格式「只有描述」給數字語言（`numlan`）清單，改名為 `_numlanDisplayName`，註解說明它只給設定環用。
  - 兩者顯示的文字都不變。改成同一格式會改變使用者看得到的清單文字，不在本階段範圍內。

### 4. `CompletionPolicy` 自持 NVDA 版本與 fallback 去重

- `CompletionPolicy(*, nvda_version: str | None = None, logger=None, force_unverified_drain=True)`。
- 新增 `select(voice_class, core) -> CompletionContract`，內容是現行主驅動 `_completion_for` 加 `_warn_drain_fallback`：
  - 以 `audio_mode` 加 `contract_for(nvda_version=self.nvda_version, ...)` 選出 contract；
  - 不支援時，同一組 `(engine, nvda_version, audio_mode, profile, reason)` 每個 policy 實例只記錄一次 warning，訊息字串不變。
  - `logger` 為 `None` 時用 `logging.getLogger(__name__)`。
- 主驅動：
  - 改為 `CompletionPolicy(nvda_version=versionInfo.version, logger=nvdaLog)`，並把 `completion_for=self._completionPolicy.select` 傳給 VoiceManager；
  - 刪除 `_completion_for`、`_warn_drain_fallback` 與 `getattr(self, "_drainFallbacks", None)` 懶初始化。
- `VoiceManager` 的 `completion_for` 參數名與型別（`Callable[[type, object], CompletionContract]`）不變，測試的 lambda 注入照舊。

### 5. 刪除死碼（manager 與 engine）

- `voiceManager.py`：
  - `VoiceMeta` 別名、`groupByField`、`groupVoicesByPrimaryLocale`；
  - 未使用的 `getVoiceKey`（`driver.getVoiceKey` 保留，VE、Cerence 與基底在用）；
  - `VoiceManager.ready()`；
  - `keepMainLocaleEngineConsistent` property（C7）。
- UI：`speechSettingsDialog.py` 兩處 `if not self._manager.ready():` 分支及 `self.ready` 屬性。`ready()` 永遠回傳 `True`，分支不可能執行。
- `driver.Voice.ready()` classmethod **保留**：它是引擎 readiness hook，`discovery` 與基底 `voices()` 都在呼叫，外部外掛可覆寫。

### 6. `VoiceFacade` 瘦身（原 10b-1；C5、C6）

- 刪除 11 個沒有生產呼叫者的成員：
  - `commit_rate`、`commit_pitch`、`commit_volume`、`commit_variant`、`commit_inflection`、`commit_rateBoost`，以及只服務它們的 `_baseline` helper；
  - `revision`、`rollback()`、`active()`；
  - `speak()`、`breaks()`、`pause()`、`resume()`、`close()`。
- 刪除 `taskManager` 建構子參數與欄位。它只為 `speak`／`breaks` 存在。建構子改為 `VoiceFacade(spec, binding)`，`VoiceManager._createVoiceInstance` 對應改為 `resource.voice_class(spec, resource.binding)`。
- 保留：
  - 七個設定 property（`rate`、`pitch`、`volume`、`variant`、`inflection`、`rateBoost`、`waitfactor`）；
  - `snapshot()`、`update_settings()`、`loadParameter()`、`commit()`、~~`stop()`~~；Corrected by `fix/set-voice-no-stop`（2026-10-29）：`stop()` 已刪除。它不取消 request 就直接停止引擎，在逐段語音模式會讓 request 等不到 drain；引擎只經 `TaskManager.cancel` 停止，`tests/test_hygiene_guards.py` 守門；
  - `core` property；
  - `id`、`name`、`language`。
- `driver.Voice.create_core` 刪除 `core.wv = cls.engine`（C5），不再對外部 core 物件打標。
- **相容性**：
  - Neural 式外掛只宣告 `core`、`engine`、`synth_driver_class` 類別屬性，不覆寫 `__init__`，也不呼叫被刪的成員，所以不受影響。
  - 覆寫 `__init__(self, spec, binding, taskManager)` 的外掛會受影響，但已知的外部外掛（`ref/Neural`）都不覆寫。MSC／Natural 自階段 5 起已不相容。

### 7. 守門測試固定 Neural 式外掛契約

- 新增 `tests/test_plugin_voice_contract.py`。
- 以一個與 `ref/Neural/Neural/__init__.py` 同形的子類執行完整路徑：

```python
class Voice(WorldVoice):
	core = None            # 遮蔽 VoiceFacade.core property
	engine = "Neural"
	synth_driver_class = FakeCore
```

  - 走真實的 `VoiceManager`：開啟 → `list_voices`（基底 `voices()`／`voiceInfoToMetadata`）→ 建立語音實例 → `resolve_playback(...).activate(...)`（觸發 `adapter.apply` 與基底 `applyEngineSettings`）→ `getVoiceVariants`（基底 `variants`）→ terminate（基底 `destroy_core`）。
  - 斷言：
    - 語音名稱是 `Neural:<id>`；
    - core 收到 `voice`／`rate`／`pitch`／`volume` 設定；
    - variants 為空；
    - `destroy_core` 呼叫了 `terminate`。
- 若 `ref/Neural/Neural/__init__.py` 存在，以 `ast` 讀取其 `Voice` 類別本體，斷言：
  - 類別名是 `Voice`；
  - 基底名稱是 `from synthDrivers.WorldVoice.driver import Voice as ...` 匯入的名稱；
  - 本體只有類別屬性指派，名稱是 `PLUGIN_VOICE_ATTRIBUTES` 的子集。
  - 不存在時 skip。`ref/` 不隨 addon 發佈。
- `PLUGIN_VOICE_ATTRIBUTES`：`{"core", "engine", "synth_driver_class", "extra_capabilities", "drain_profile"}`。它是基底 `Voice` 公開給外掛的類別屬性，測試同時斷言這些名稱都存在於基底 `Voice`。

### 決定

- **`SegmentCore` Protocol 評估後不採用**（原 10b-1 的一項）。逐處檢查 `refactor.md` §2.3 所列的 `getattr` 探測後：
  - `engineAdapter.configure_segment_events` 只需要 `speak_segment`；
  - `CompletionPolicy.drain_support` 需要 `speak_segment` 與 `get_segment_drain_support`，並對缺哪一個回報不同理由（`tests/test_runtime_completion_policies.py:102-103` 固定這兩句）；
  - `supportsCancellationToken` 是可選的布林能力，不是方法。
  - Python 3.11 的 `@runtime_checkable` `isinstance` 只檢查屬性是否存在、不檢查 callable，會放寬現有檢查，並失去分項的診斷理由。
  - `session.py:174` 對 token 的 `callable(add_callback)` 檢查同理：換成 `isinstance(token, CancellationView)` 只會從「可呼叫」放寬為「存在」。
  - 所以五處探測維持原樣。它們是各層邊界上的能力檢查，不是型別重複。
- **命名**：不為統一而改名。NVDA／UI 面向的 manager 成員維持 camelCase（`getVoiceInstance`、`defaultVoiceName`、`voiceInfos`……）。本階段新增的 API 用 snake_case（`VoiceCatalog.from_specs`、`by_name`、`ready_engine_classes`、`group_by_primary_locale`、`CompletionPolicy.select`）。依 `refactor.md` §8。
- **`EngineRegistry` 不建立**：理由見第 2 節。

### 成功條件

1. 完整測試全部通過；`ruff format --check addon` 通過；`ruff check addon <附錄範圍> --select F401,F821,BLE001,I001` 為 0；階段 11 的 hygiene 守門測試通過。
2. 守門測試（`tests/test_voice_manager_structure.py`）：
   - `voiceManager.py` 不出現 `_sessions`、`_bindings`、`_specs`、`READY_ENGINE_CLASS`、`EngineType`、`VoiceMeta`、`groupByField`、`keepMainLocaleEngineConsistent`、`def ready`；
   - `engine/__init__.py` 不出現 `READY_ENGINE_CLASS`、`EngineType`、`refresh_ready_engine_classes`；
   - `speechSettingsDialog.py` 不出現 `EngineType`、`_manager.ready`；
   - 主驅動不出現 `_completion_for`、`_warn_drain_fallback`、`_drainFallbacks`；
   - `discovery.py` 與 `engine/__init__.py` 合計只有一個布林轉換定義。
3. `VoiceFacade` 的公開成員恰好是第 6 節的保留清單（守門測試以 `dir` 比對），`create_core` 不再設 `wv`。
4. Neural 契約測試通過（第 7 節）。
5. `driver/<Engine>/driver/`、`driver/sonic` 無變動。
6. 使用者可見行為不變：語音清單、語言清單與其顯示文字、數字語言清單文字、fallback warning 訊息、引擎啟用邏輯。

### 不在範圍內

- 階段 12 的組裝根（主驅動 `_initialize` 的計時碼與清理旗標）；本階段只改 VoiceManager 建構那一段的參數。
- C4（預設語音兩條規則）、C9（filter 透過 `voice_for_language` 建實例）。
- `ENGINE_SPECS` 在 import 時掃描檔案系統（UI 需要，保留）。
- `WVW_PATH` 等路徑推導（C12，階段 16）。

## 設計

### `VoiceManager`（節錄）

```python
@dataclass
class EngineResource:
	engine: str
	voice_class: type
	adapter: LegacyEngineAdapter
	session: EngineSession
	binding: LegacyVoiceBinding
	voices: tuple[VoiceSpec, ...] = ()
	published: bool = False


class VoiceManager:
	def __init__(self, taskManager, settings, bridge, *, index_ledger, completion_for, engine_classes, roles=None):
		...
		self._engine_classes = dict(engine_classes)
		self._resources: dict[str, EngineResource] = {}
		self.catalog = EMPTY_CATALOG
		...

	def _initialize(self):
		for name, cls in self._engine_classes.items():
			resource = self._open_engine(name, cls)
			if resource is None:
				continue
			self._bind(resource)
			self._publish(resource)
		self._setVoiceDatas()
		...

	def _publish(self, resource):
		# Only bound, operational resources become visible to resolvers.
		resource.voices = resource.adapter.list_voices()
		resource.published = True

	def _published(self, engine: str) -> EngineResource:
		resource = self._resources[engine]
		if not resource.published:
			raise KeyError(engine)
		return resource

	def resolve_playback(self, key):
		spec = self.catalog.by_name.get(key)
		if spec is None:
			return None
		resource = self._resources.get(spec.engine)
		if resource is None or not resource.published:
			return None
		self.settings.ensure(spec)
		return resource.session

	@property
	def playback_ports(self):
		return tuple(r.session for r in self._resources.values() if r.published)

	def _setVoiceDatas(self):
		self.catalog = VoiceCatalog.from_specs(
			spec for r in self._resources.values() if r.published for spec in r.voices
		)
```

- `playback_ports` 現行以 `dict.fromkeys` 去重 session。每個資源各有自己的 session，所以不再需要去重。
- `resolve_playback` 的 `_specs` 在終止後仍保留；catalog 也一樣保留，終止後 `published` 為 `False`，所以回傳 `None`，與現行相同。

### 主驅動（節錄）

```python
self._completionPolicy = CompletionPolicy(nvda_version=versionInfo.version, logger=nvdaLog)
self._voiceManager = VoiceManager(
	taskManager=self.taskManager,
	settings=self._settingsStore,
	bridge=self._eventBridge,
	index_ledger=self._indexLedger,
	completion_for=self._completionPolicy.select,
	engine_classes=ready_engine_classes(config.conf["WorldVoice"]["engine"]),
)
```

## 測試

1. **既有測試**：直接操作已刪內部結構的測試改用新結構或公開 API。
   - 涉及：`test_f4_voice_state`、`test_worldvoice_lifecycle`、`test_runtime_composition`、`runtime_drain_integration_harness`、`test_role_presenter`、`test_voice_settings_transaction`、`test_voice_manager_roles`、`test_runtime_completion_policies`、`test_runtime_voice_facade`、`test_worldvoice_request_manager`、`test_f4_engine_adapters`。
   - 修改方式：
     - `manager.table = [...]` → `manager.catalog = VoiceCatalog.from_specs([...])`；
     - stub 的 `READY_ENGINE_CLASS`／`EngineType` → `engine_classes=` 參數；
     - `voice.active()` → `voice._binding.session.activate(voice.name)`；
     - `voice.rollback()` → `settings.rollback(name)`；
     - `voice.revision` → `voice.snapshot().revision`；
     - `synth._completion_for` → `CompletionPolicy(...).select`。
   - 只測被刪成員本身的測試一併刪除：`test_speech_queue_does_not_activate_voice` 測 `facade.speak`，`commit_rate` 的斷言測 `_baseline`。
   - 每個修改過的測試保持原本的行為斷言。
2. **新測試**：
   - `tests/test_voice_catalog.py`：
     - 排序；
     - 同名後者覆蓋；
     - `voice_infos` 為 `OrderedDict` 且順序同 `table`；
     - `all_languages`；
     - `group_by_primary_locale`；
     - `readable_name` 有描述與無描述兩種情況；
     - frozen（指派欄位拋 `FrozenInstanceError`）；
     - `by_name` 唯讀。
   - `tests/test_runtime_completion_policies.py`：
     - `select` 在支援、不支援、未宣告 profile 三種情況回傳與 `contract_for` 相同的 contract；
     - 同一 fallback 只 warning 一次、不同 profile 各一次；
     - 訊息字串與現行相同。
   - `tests/test_runtime_composition.py`：
     - 未發布的資源（`_bind` 失敗）不出現在 `playback_ports`，`resolve_playback` 回傳 `None`；
     - 終止後 `getVoiceCapabilities` 拋 `KeyError`；
     - `engine_classes` 的順序就是開啟順序。
   - `tests/test_voice_manager_structure.py`：成功條件 2、3。
   - `tests/test_plugin_voice_contract.py`：成功條件 4。
3. **UI**：`speechSettingsDialog` 的既有 exec 測試（`test_pipeline_panels` 等）通過；刪除 `ready` 分支後，Unicode 面板與角色面板在 synth 為 WorldVoice 時照常建立。
