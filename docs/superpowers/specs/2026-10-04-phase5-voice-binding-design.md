# 階段 5：Voice binding 注入、EngineResource、DrainProfile

日期：2026-10-04。
基準：`master`（`f4fc958`，階段 0–4 完成）。分支：`phase5-voice-binding`。
狀態：範圍與設計已獲使用者確認。

本文件是 [`refactor.md`](../../../refactor.md) §9 的階段 5，對應 §3.1（Voice 類別屬性當全域狀態）、§3.3（反射式能力偵測）與 §3.4（`EngineResource`、拆分 `_initialize`）。

## 需求與範圍

背景：
- **共享類別屬性**：`Voice` 的類別屬性 `core`、`session`、`_runtime_binding` 被當成全域狀態，由 `VoiceManager`、`LegacyEngineAdapter`、`Voice.engineOff` 三方寫入。
  - `VoiceFacade.__init__` 必須先讀到 `_runtime_binding` 才能建構；`Voice.voices()` 也要讀 `cls.core`。
  - adapter 的 alias 機制（`is_source_owned`、`detach_alias`），以及「`engineOn` 可能先暴露別人的 core 才失敗」的處理，都是共享類別狀態造成的複雜度。
- **反射式能力偵測**：`completionPolicies.get_segment_drain_support` 用 `sys.modules`、`__module__` 比對與 `signature().bind()` 反射「證明」core 是倉庫內的 wrapper。另外有兩份寫死的引擎名單（`DRAIN_ENGINES`、`_WASAPI_MODE_ENGINES`），`FORCE_UNVERIFIED_DRAIN` 也是模組層的可變旗標。
- **`VoiceManager` 的結構**：`_resources` 是以 index 拆解的 5 元 tuple，`_initialize` 一個方法做完所有事。

已確認的決定：

1. **一份 spec、一份 plan** 涵蓋三件事：binding 注入、`EngineResource`、`DrainProfile`。
2. **不保留舊的外掛介面**：
   - `engineOn`／`engineOff`、`cls.core`、`cls.session`、`_runtime_binding` 直接移除。
   - 外掛引擎需要照新介面更新。舊外掛會在開啟時失敗，由 `discovery`／`VoiceManager` 記錄錯誤並跳過該引擎。
   - 這與「不考慮 Neural 相容性」一致。
3. **刪除 alias 機制**：每個 adapter 建立並獨佔自己的 core，兩個引擎名稱不再可能共用同一個 core。
4. **沿用的限制**：
   - 不修改內層 driver；
   - 外層 wrapper 只改 `Voice` 類別，`SynthDriver` 不動；
   - `runtime/` 不依賴 `compat/`；
   - 新增名稱用 snake_case；
   - plan 的變異步驟放在 commit 之後。

成功條件：

1. **行為不變（對使用者）**：開啟的引擎、每個引擎得到的完成合約、語音清單、設定套用、取消與關閉流程都和現在相同。
2. **介面**：
   - addon 內不再出現 `engineOn`、`engineOff`、`_runtime_binding`；
   - 不再對 Voice 類別或實例寫入 `.core`／`.session`；
   - `completionPolicies.py` 不再使用 `sys.modules`、`signature`，也不再有 `FORCE_UNVERIFIED_DRAIN`、`DRAIN_ENGINES`、`_WASAPI_MODE_ENGINES`。

   以上由守門測試強制。
3. **測試**：
   - 依賴舊介面的測試改用新介面；
   - alias 測試與「驗證反射檢查」的測試刪除；
   - 新增 `DrainProfile`、`CompletionPolicy`、獨立 core 的測試。

   plan 逐一列出對應關係。完整套件全部通過，沒有 skip。
4. **範圍**：
   - `driver/*/driver/`（內層）完全不改；
   - 外層 wrapper 的 diff 只落在 `Voice` 類別內；
   - `ruff format --check addon` 通過；Neural 未被追蹤。

**不在範圍內**：
- `SpeechFuture.then`、相容 shim、contextual legacy 的去留（階段 8）；
- 把 `force_unverified_drain` 做成使用者設定（之後再做）；
- 階段 4 延後的 Minor。

## 設計

### 1. Voice 介面（`driver/__init__.py` 與六個引擎的 `Voice`）

base `Voice`：
- 刪除 `core`、`session` 類別屬性與 `engineOn`／`engineOff`。
- 新增：
  ```python
  drain_profile: DrainProfile | None = None

  @classmethod
  def create_core(cls):
  	core = cls.synth_driver_class()
  	core.wv = cls.engine
  	return core

  @classmethod
  def destroy_core(cls, core):
  	core.terminate()

  @classmethod
  def voices(cls, core): ...  # 原本讀 cls.core 的地方改讀參數 core
  ```
- 保留的類別層級 metadata：`engine`、`synth_driver_class`、`extra_capabilities`、`supportedSettings()`、`ready()`、`voiceInfoToMetadata()`、`applyEngineSettings()`。

引擎的 `Voice`：
- 刪除各自的 `core = None`。
- VE、Cerence 覆寫的 `voices` 改為 `voices(cls, core)`。
- 加上 `drain_profile`（見 §3）。
- 其他內容不變。

### 2. 實例、binding 與 adapter

`compat/voiceFacade.py`：
```python
@dataclass(frozen=True)
class LegacyVoiceBinding:
	settings: VoiceSettingsStore
	session: EngineSession
	core: object

class VoiceFacade:
	def __init__(self, spec: VoiceSpec, binding: LegacyVoiceBinding, taskManager):
		self._binding = binding
		self._state = binding.settings.ensure(spec)
		self.id, self.name, self.language = spec.id, spec.name, spec.language
		self.taskManager = taskManager

	@property
	def core(self):
		return self._binding.core
```
- 原本 binding 的 `spec_for` 不再需要，因為 spec 直接傳入。
- `core` 唯讀屬性讓 VE、Cerence `variants` 中的 `self.core` 不必改寫。

`compat/engineAdapter.py`：
- `__init__` 移除 `is_source_owned` 參數。
- `open()`：`self._core = self._voice_class.create_core()`；`notification_source = self._core`。若 `create_core` 拋出，adapter 不持有任何 core，直接把例外往上拋，不需要另外清理。
- `close()`：先清掉 adapter 自己的欄位，再呼叫 `self._voice_class.destroy_core(core)`。這和原本「`engineOff` 失敗也一定清除欄位」的 try/finally 語意相同。
- `list_voices()`：`self._voice_class.voices(self._core)`。
- 刪除 `detach_alias()`。
- 新增唯讀屬性 `core`，供 `VoiceManager` 建立 binding。

### 3. DrainProfile 與 CompletionPolicy

`runtime/playbackWork.py` 新增：
```python
@dataclass(frozen=True)
class DrainProfile:
	"""The wrapper declares that its core reports segment drain."""

	wasapi_dependent: bool = False  # the audio mode follows core.useWasapi
```

各引擎宣告：
- VE、Cerence、RHVoice、Espeak：`drain_profile = DrainProfile()`。
- OneCore、SAPI5：`drain_profile = DrainProfile(wasapi_dependent=True)`。

`compat/completionPolicies.py` 改為 `CompletionPolicy` 類別，保留 `_VERIFIED_CONTRACTS` 表與 `_DRAIN_CONTRACT`：
```python
class CompletionPolicy:
	def __init__(self, *, force_unverified_drain: bool = True): ...

	def audio_mode(self, voice_class, core) -> str:
		# 與 resolve_audio_mode 相同：非 WASAPI 相依 → "default"；
		# 否則依 core.useWasapi 的明確布林值 → "wasapi"／"legacy"，其他 → "unknown"。

	def drain_support(self, voice_class, core, *, nvda_version, audio_mode) -> DrainSupport:
		# 1. voice_class.drain_profile is None → 不支援。
		# 2. core 不是 voice_class.synth_driver_class 的實例 → 不支援。
		# 3. 呼叫 core.get_segment_drain_support(nvda_version=, audio_mode=)：
		#    不可呼叫、拋例外、回傳非 DrainSupport 或非布林 → 不支援（原因與原碼相同）。
		# 4. 不支援且沒有原因 → 不支援（原文訊息）。
		# 5. 支援但 force_unverified_drain 為 False → 不支援（原文訊息）。

	def contract_for(self, voice_class, core, *, nvda_version) -> tuple[CompletionContract, DrainSupport | None]:
		# 有 profile：DRAIN（支援）或 CompletionContract()（不支援），並回傳 support 供主驅動記錄 fallback。
		# 無 profile：_VERIFIED_CONTRACTS.get((engine, nvda_version, audio_mode), CompletionContract())，support 為 None。
```
- 刪除 `DRAIN_ENGINES`、`_WASAPI_MODE_ENGINES`、`FORCE_UNVERIFIED_DRAIN`、`resolve_audio_mode`、`get_completion_contract`、`get_segment_drain_support`，以及 `sys`、`signature` 的 import。
- 被刪除的反射檢查有：模組歸屬、`driver.__module__`、`speak_segment` 是否可呼叫及其簽名。倉庫內六個引擎今天全部都會通過這些檢查，因此結果不變。`speak_segment` 是否存在，仍由 `LegacyEngineAdapter.configure_segment_events` 的既有檢查負責。
- 主驅動（`WorldVoice/__init__.py`）：
  - 建立 `self._completionPolicy = CompletionPolicy()`；
  - `_completion_for(voice_class, core)` 改為呼叫 `contract_for`。若回傳的 support 不為 None 且不支援，照舊呼叫 `_warn_drain_fallback`。

### 4. EngineResource 與 VoiceManager

```python
@dataclass
class EngineResource:
	engine: str
	voice_class: type
	adapter: LegacyEngineAdapter
	session: EngineSession
	binding: LegacyVoiceBinding
```
`_initialize` 拆成：
- `_open_engine(name, cls) -> EngineResource | None`：
  - 建立 adapter 並 `open()`；開啟失敗時記錄錯誤並回傳 None，與原碼相同。
  - 建立 `EngineSession` 並先加入 `_resources`，讓失敗時仍能清理，與原碼「先認領再綁定」相同。
  - 再 `session.open()`。
- `_bind(resource)`：設定完成合約、綁定 bridge、設定 segment 或 legacy 事件 sink，順序與原碼相同。
- `_publish(resource)`：把 session 加入 `_sessions`，把 spec 加入 `_specs`。

其他調整：
- `terminate`：依 `_resources` 反向，對每個資源 unbind，再 `session.close()`。alias 分支刪除，`cls.session`／`_runtime_binding` 的清除也一併刪除。
- `_publish` 另外把 binding 放進 `self._bindings[engine]`。這和 `_sessions` 一起在 `terminate` 開頭清除，維持「先停止公開，再釋放資源」的順序。
- `_createVoiceInstance`：`cls(spec, self._bindings[spec.engine], self.taskManager)`，不再寫入 `voiceInstance.session`。
- 刪除只寫不讀的 `installEngine`。

## 測試

1. **改寫**：依賴舊介面的測試改用新介面，包括：
   - harness 中的 `Voice.core = ...` 改為讓 `create_core` 回傳指定的 core；
   - 讀取 `cls.core` 改為讀 `adapter.core` 或 `resource.binding.core`；
   - monkeypatch `FORCE_UNVERIFIED_DRAIN` 改為建構 `CompletionPolicy(force_unverified_drain=False)`。

   plan 逐檔列出。
2. **刪除**：
   - 3 個 alias 測試（`test_runtime_composition.py` 的 `test_shared_source_alias_uses_one_session_and_close`、`test_failed_alias_open_preserves_existing_owner_and_closes_once`、`test_alias_uses_one_allocator_and_one_close`），以及 `test_runtime_legacy_adapter.py` 的 `test_alias_detach_preserves_shared_resource_owner`；
   - completion policy 中專門驗證已刪除反射檢查的測試。

   plan 寫明每個被刪測試保護的行為為何已不存在。
3. **新增**：
   - 每個引擎宣告的 `DrainProfile`（WASAPI 相依與否）；
   - `CompletionPolicy` 各分支：無 profile、core 類別不符、檢查拋例外、回傳非 `DrainSupport`、不支援且無原因、force 關閉、三種 WASAPI 音訊模式、已驗證合約表；
   - 兩個引擎各自建立並關閉自己的 core。
4. **守門**：AST 或文字掃描確認成功條件 2。
5. **變異證明**（commit 之後）：每個新測試至少一個對應的變異，例如：
   - `drain_support` 忽略 profile；
   - `audio_mode` 忽略 `wasapi_dependent`；
   - `close()` 不呼叫 `destroy_core`；
   - 加回一處 `cls.core =` 寫入。

## 驗收

- `python3 -m pytest tests -q`：全部通過，沒有 skipped 或 xfailed。
- 守門測試通過。
- `git diff master --stat -- 'addon/synthDrivers/WorldVoice/driver/*/driver'`：無輸出。
- 外層 wrapper（`driver/<Engine>/__init__.py`）的 diff 只落在 `class Voice` 內。
- `ruff format --check addon` 通過；Neural 未被追蹤。
