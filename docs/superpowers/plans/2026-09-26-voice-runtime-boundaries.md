# Voice Runtime Boundaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 F5、F6、A1、A4，建立可獨立運作的語音設定與排程核心，並以可移除的相容層接入現有引擎。

**Architecture:** 在 WorldVoice 下新增純 Python 的 `runtime` package，容納資料模型、設定狀態、Session、排程及 builder。NVDA 設定與事件留在 package 外的轉接元件，舊 Voice／引擎 API 集中到 `compat`。先新增並驗證元件，再一次切換正式入口，避免中途混用兩套排程。

**Tech Stack:** Python、dataclasses、typing.Protocol、threading、queue、concurrent.futures、pytest；NVDA config 與 synthDriverHandler 只存在於整合邊界。沿用現有 Python 語法與執行環境，不新增第三方執行期依賴。

**Spec:** [2026-09-26-voice-runtime-boundaries-design.md](../specs/2026-09-26-voice-runtime-boundaries-design.md)，使用者已於本輪核准。執行前同時閱讀 spec 與本計畫。

## Global Constraints

- **之後可移除相容層，排程與設定邏輯無須重寫。**
- 本次完成 F5、F6、A1、A4。F7 的各引擎取消後回呼排空契約另行處理。
- F6 採用跳過策略：不可用語音區段的文字、index 與停頓一併跳過；持續處理語音切換命令，遇到可用語音後恢復，不自動改用預設語音。
- 相容層依賴新介面；新排程與設定元件不匯入舊 Voice 類別。
- 快照不得在 request 建構時提早凍結。
- TaskManager 的狀態鎖不得包住引擎呼叫、NVDA 通知或可能執行使用者 callback 的 Future 完成動作。
- 本次不要求變更原生 DLL、NVDA 原始碼、`ref/` 或內嵌的底層 driver 實作。
- 設定檔 key、語音識別與角色 mapping 格式維持相容。
- F2、F3 等修正已在撰寫實作計畫期間納入提交 `6256a23`。後續實作須以包含此提交的當前工作目錄為基礎保留其修正，不能以還原檔案或搬回舊版本的方式進行遷移。
- 執行時使用 using-git-worktrees 檢查隔離環境。基底必須包含 `6256a23` 與已核准的 spec／plan；若執行時又有未提交修改，記錄並攜帶必要內容，不擅自 reset／stash／全部 stage。翻譯及其他無關修改不納入成果提交。
- 本文件中的命令從 repo 根目錄執行。`docs` 已被忽略，提交本計畫或驗證紀錄時只對指定文件使用 `git add -f`。

## Review Focus

- 編輯頁開啟後才建立語音：取消仍恢復該語音首次加入編輯時的值，且新舊入口共用狀態。測試歸 Task 2、9。
- Repository 保存失敗或保存期間另有編輯：取消基準只前進至成功保存的快照，較新的待生效值仍保留。測試歸 Task 2。
- 命令 generator 半途拋錯、取消與建構交錯：不得播放半筆 request，也不得留下 Building request。測試歸 Task 7。
- 同一 core 經不同 alias 接入、或 engineOn 部分成功後拋錯：資源只由一個 Session 關閉，已取得資源可回收。測試歸 Task 4、8。
- 通知通過初次檢查後才取消，或 Future callback 重新進入取消／提交：不得誤送舊通知或在狀態鎖中死鎖。測試歸 Task 6。

---

## 檔案配置與執行順序

以下 `WV/` 只在此配置表代表 `addon/synthDrivers/WorldVoice/`；各任務均列完整路徑。

| 檔案 | 責任 |
| --- | --- |
| `WV/runtime/__init__.py` | 空的 package 入口，不匯入 driver、config 或 NVDA |
| `WV/runtime/models.py` | VoiceSpec、VoiceSnapshot、SelectVoice、Pause、事件值物件、能力宣告 |
| `WV/runtime/settings.py` | VoiceState、VoiceSettingsStore、VoiceEditSession、Repository Protocol |
| `WV/runtime/session.py` | Adapter／PlaybackPort Protocol、EngineSession |
| `WV/runtime/scheduler.py` | 從現有 TaskManager 遷移的純排程、token、Future、request 狀態 |
| `WV/runtime/requestBuilder.py` | 處理已正規化命令，建構並提交完整 request |
| `WV/configRepository.py` | 目前 config 的載入、預設值、型別轉換與儲存規則 |
| `WV/nvdaEventBridge.py` | NVDA 事件註冊、來源對應、對外通知 |
| `WV/compat/__init__.py` | 空的相容 package 入口 |
| `WV/compat/engineAdapter.py` | LegacyEngineAdapter，封裝舊引擎生命週期與 hook |
| `WV/compat/voiceFacade.py` | 舊 Voice 操作轉交新設定及 Session |
| `WV/compat/commands.py` | 舊 Voice 與 NVDA BreakCommand 正規化 |
| `WV/driver/__init__.py` | 採用 facade，保留 metadata／原始引擎接入入口 |
| `WV/driver/engineSession.py` | 舊路徑的型別匯出入口；正式核心移至 runtime |
| `WV/taskManager.py`、`WV/requestBuilder.py` | 舊模組路徑匯出／命令轉接；無另一套排程與建構邏輯 |
| `WV/voiceManager.py`、`WV/__init__.py` | runtime 組裝、Session 索引、資源回收與正式切換 |
| `WV/pipeline/__init__.py` | 產生 SelectVoice，使用語音 key 路由 |
| `addon/globalPlugins/WorldVoice/speechSettingsDialog.py` | 共用編輯 session、能力查詢、保存／取消 |

Task 1 → 2 → 3 建立純核心；Task 4、5 建立邊界；Task 6、7 完成排程與建構；Task 8 切換正式入口；Task 9 完成 UI 編輯邊界；Task 10 驗證遷移契約並整理紀錄。這是一條共享介面的遷移鏈，請按順序執行。

目前正式路徑在 Task 8 前繼續使用現有入口。新增模組應先獨立測試；不可為了讓舊測試通過，在新 scheduler 中加入 `owner`、Voice 或 NVDA 特例。

## 共用命名與測試方法

`VoiceKey = str`，格式維持 `engine:id`。`SettingValue = int | str | bool`，`VoiceValues = dict[str, SettingValue]`。`SourceId` 使用獨立的 `object()` 並以 `is` 比對，每個 core 生命週期一個，不是 request ID。`SpeechCommands = tuple[object, ...]`，排程將語音命令視為不透明資料。

`VoiceSpec` 沿用目前 VoiceMeta 的欄位順序：`id, name, description, language, engine, locale`，全部為 str；`name` 即 key。`voiceManager.VoiceMeta` 最終重新匯出這個類別。`VoiceSnapshot` 沿用目前欄位：`voice_id, revision, language, rate, pitch, volume, variant, inflection, rateBoost, waitfactor`，為 frozen dataclass。

建立 `tests/runtime_harness.py`，用 `importlib` 將 runtime 目錄載入為獨立測試 package；不執行 WorldVoice 根入口或 `driver/__init__.py`。新測試檔以 fixture 名稱 `rt` 提供這些模組。Task 1 加入 `make_spec(key="Fake:a", language="en")`；Task 2 加入 `MemoryRepository`；Task 3 加入 `FakeAdapter`；Task 6 加入 `RecordingOutput`。測試 snippet 中的 factory／fixture 由所屬任務建立，不從產品程式匯出測試捷徑。

每項任務採「新增可重現行為的測試 → 看到預期失敗 → 實作 → 指定測試通過 → 提交」。不把 import 失敗以外的環境錯誤當成預期紅燈，也不為符合新內部欄位而刪除既有行為斷言。

每個 Commit 步驟先逐檔檢查該任務 Files 清單中的 diff，stage 相關檔案／hunks，執行 `git diff --cached --check`，再使用所列 commit message；不要使用 `git add .`。每個紅燈命令須看到本任務尚未實作的 API／行為失敗，綠燈命令的通過條件為該命令選取的全部測試 PASS。

## Task 1：建立不可變資料與唯一的語音設定狀態

**Files:**

- Create: `addon/synthDrivers/WorldVoice/runtime/__init__.py`
- Create: `addon/synthDrivers/WorldVoice/runtime/models.py`
- Create: `addon/synthDrivers/WorldVoice/runtime/settings.py`
- Create: `tests/runtime_harness.py`
- Create: `tests/test_runtime_voice_state.py`

**Interfaces:**

- Produces: frozen `VoiceSpec`、`VoiceSnapshot`、`SelectVoice(voice_key: str)`、`Pause(seconds: float)`。
- Produces: `EngineCapabilities(settings: frozenset[str], supports_waitfactor: bool = False, supports_variants: bool = False, supports_cancellation_token: bool = False)`。
- Produces: `EventKind.INDEX/DONE`、`PlaybackEvent(kind: EventKind, source_id: object, index: int | None = None)`。
- Produces: `VoiceState(spec: VoiceSpec, values: Mapping[str, SettingValue])`，`get(name: str) -> SettingValue`、`update(**values: SettingValue) -> None`、`snapshot() -> VoiceSnapshot`、`checkpoint(values: Mapping[str, SettingValue] | None = None) -> None`、`rollback() -> None`、`baseline(name: str) -> SettingValue`。

- [ ] **Step 1：新增設定與 import 邊界測試。** 建立 harness 與 `test_runtime_voice_state.py`，至少包含以下斷言：

```python
def test_pending_state_is_atomic_and_snapshot_is_immutable(rt):
    state = rt.settings.VoiceState(make_spec(), {})
    before = state.snapshot()
    state.update(rate=72, pitch=63)
    assert (before.rate, before.pitch, before.revision) == (50, 50, 0)
    assert (state.snapshot().rate, state.snapshot().pitch) == (72, 63)
    state.rollback()
    assert state.get("rate") == 50
    assert state.snapshot().revision > before.revision
```

  另建立 `test_unknown_setting_update_changes_nothing`（rate=72 與 unknown 同次更新應拋 ValueError，rate 仍 50）、`test_same_value_does_not_increase_revision`、`test_snapshot_never_observes_half_a_batch`（Event 控制交錯）、`test_runtime_import_does_not_load_legacy_or_nvda`。最後一例在獨立測試 package 下，禁止 config、synthDriverHandler、logHandler、舊 driver 匯入。
- [ ] **Step 2：執行紅燈。** `python3 -m pytest tests/test_runtime_voice_state.py -q -p no:cacheprovider`。預期缺少新模組／型別，或具體行為斷言失敗。
- [ ] **Step 3：實作上述資料與 VoiceState。** 預設 rate／pitch／volume／inflection=50、variant="default"、rateBoost=False、waitfactor=0。先驗證全部 key，再在同一把 RLock 內更新；revision 沿用每個實際改變欄位加一。checkpoint 不改 revision；rollback 更新值並維持版本單調。在 `runtime/settings.py` 定義唯一的 `VOICE_PARAMETERS` 與 `boolean(value)`，供 Repository 與相容入口重新匯出；waitfactor 為不持久化的額外欄位。
- [ ] **Step 4：執行綠燈。** 執行 Step 2 命令，預期全部 PASS；此時不修改正式 Voice。
- [ ] **Step 5：提交本任務的新檔案。** `git commit -m "feat: add independent voice state and runtime models"`。

## Task 2：抽出 Repository 與共用編輯基準

**Files:**

- Modify: `addon/synthDrivers/WorldVoice/runtime/settings.py`
- Create: `addon/synthDrivers/WorldVoice/configRepository.py`
- Modify: `tests/runtime_harness.py`
- Create: `tests/test_runtime_settings_store.py`
- Create: `tests/test_voice_config_repository.py`

**Interfaces:**

- Consumes: Task 1 的 VoiceSpec、VoiceState、VoiceSnapshot。
- Produces: `VoiceSettingsRepository` Protocol：`load(spec: VoiceSpec) -> VoiceValues`、`save(spec: VoiceSpec, values: Mapping[str, SettingValue]) -> None`。
- Produces: `VoiceSettingsStore(repository)`：`ensure(spec) -> VoiceState`、`state(key) -> VoiceState`、`keys() -> tuple[str, ...]`、`snapshot(key) -> VoiceSnapshot`、`commit(key) -> None`、`rollback(key) -> None`、`reload(key) -> None`、`begin_edit() -> VoiceEditSession`。
- Produces: `VoiceEditSession.apply() -> None`、`discard() -> None`、`close() -> None`；同一 Store 一次只持有一個編輯 session。
- Produces: `ConfigVoiceSettingsRepository(conf: MutableMapping, synth_name: Callable[[], str])`，由整合入口注入依賴。

- [ ] **Step 1：新增持久化與延後載入測試。** `MemoryRepository` 記錄 load/save，並可注入保存失敗。測試包括：

```python
def test_late_voice_and_failed_save_keep_cancel_baseline(store, repo):
    edit = store.begin_edit()
    state = store.ensure(make_spec("Fake:b"))
    state.update(rate=72)
    repo.fail_next_save = True
    with pytest.raises(OSError):
        edit.apply()
    assert state.get("rate") == 72
    edit.discard()
    assert state.get("rate") == 50
```

  `test_successful_apply_rebases_discard` 驗證 50 → 套用72 → 預覽81 → 取消為72；`test_edit_during_save_preserves_new_pending_value` 在保存72的屏障期間改81，成功後待生效仍81、baseline為72；`test_ensure_returns_same_state` 驗證新舊取得入口共用實例。加入重複 close、開啟編輯前已有待生效值、保存失敗不更新基準的案例。
- [ ] **Step 2：新增 config 規則測試並執行紅燈。** `test_voice_config_repository.py` 覆蓋 int 字串、"False"、variant、缺少語音節點建立六個既有預設值、KeepMainLocaleParameterConsistent 的主語音來源及例外 fallback。保存不新增 waitfactor key。執行 `python3 -m pytest tests/test_runtime_settings_store.py tests/test_voice_config_repository.py -q -p no:cacheprovider`，預期缺少新介面或保存／回復斷言失敗。
- [ ] **Step 3：實作 Store、編輯 session 與 config Repository。** Store.ensure 每個 key 只載入一次；同 key 不同 metadata 明確拒絕。開始編輯時 checkpoint 已有狀態，編輯中新增語音即加入同一回復範圍。commit 先取快照，鎖外 save，成功後以「保存的快照」checkpoint，不覆蓋較新的 pending 值。apply 依 key 逐項提交；失敗時保留失敗項目的 baseline，已成功項目的 baseline 前進。discard 只回復記憶體，close 只釋放編輯所有權；UI 決定先 apply 或 discard。
- [ ] **Step 4：執行綠燈。** 執行 Step 2 命令及 `tests/test_runtime_voice_state.py`，預期全部 PASS。檢查 Repository 內無 core／Session 建構；pure settings 內無 config 匯入。
- [ ] **Step 5：提交本任務新檔案與變更。** `git commit -m "refactor: separate voice settings persistence and editing"`。

## Task 3：建立 Session 與窄播放契約

**Files:**

- Create: `addon/synthDrivers/WorldVoice/runtime/session.py`
- Modify: `tests/runtime_harness.py`
- Create: `tests/test_runtime_session.py`

**Interfaces:**

- Consumes: VoiceSettingsStore、VoiceSpec、VoiceSnapshot、EngineCapabilities。
- Produces: `CancellationView` Protocol：`is_cancelled() -> bool`。
- Produces: `EngineAdapter` Protocol：`open() -> None`、`close() -> None`、`notification_source: object`、`capabilities: EngineCapabilities`、`list_voices() -> tuple[VoiceSpec, ...]`、`variants(key: str) -> tuple[Mapping[str, str], ...]`、`apply(spec, snapshot) -> None`、`speak(commands: SpeechCommands, token: CancellationView) -> None`、`cancel() -> None`、`pause(switch: bool) -> None`。
- Produces: `PlaybackPort` Protocol：`source_id: object`、`activate(key: str) -> bool`、`speak(commands, token) -> None`、`cancel() -> None`、`pause(switch: bool) -> None`。
- Produces: `EngineSession(adapter: EngineAdapter, settings: VoiceSettingsStore)`，實作 PlaybackPort，另提供 `open() -> None`、`close() -> None`、`invalidate() -> None`、`replace_adapter(adapter: EngineAdapter) -> None`、`capabilities`、`list_voices()`、`variants(key)`。replace_adapter 僅由已停止使用的組裝端呼叫，關閉舊 adapter、開啟新 adapter、更新 source_id。

- [ ] **Step 1：新增 Session 合約測試。** `FakeAdapter` 記錄 applied snapshots、spoken commands、cancel 次數、open/close 次數，可在 apply/speak 注入 Event 或例外。測試：

```python
def test_cached_voice_is_fully_reapplied(session, adapter, store):
    store.ensure(make_spec("Fake:a", "en"))
    store.ensure(make_spec("Fake:b", "zh_TW"))
    for key in ("Fake:a", "Fake:b", "Fake:a"):
        session.activate(key)
    assert [snap.language for _, snap in adapter.applied] == ["en", "zh_TW", "en"]
    assert session.activate("Fake:a") is False
```

  加入 `test_next_activation_reads_latest_state`、`test_failed_apply_invalidates_cache`、`test_replace_adapter_changes_source_and_reapplies`、`test_cancel_can_enter_while_speak_blocks`、`test_open_failure_attempts_close`、`test_close_is_idempotent_even_after_failure`。取消測試在 speak 被 Event 阻擋時確認 cancel 已進入，不能先解除 speak。
- [ ] **Step 2：紅燈。** `python3 -m pytest tests/test_runtime_session.py -q -p no:cacheprovider`，預期缺少新 Session 或行為斷言失敗。
- [ ] **Step 3：實作契約與 Session。** activate 在執行當下取快照，以 source_id／key／revision 快取；Adapter 成功套用後才記錄。open 失敗嘗試回收，close 記錄已關閉以避免重複呼叫底層。停止、暫停與播放之間不共用長時間持有的互斥鎖。Adapter 不直接讀 Repository。
- [ ] **Step 4：綠燈。** 執行 Step 2 命令及 Task 1、2 純核心測試，預期 PASS。
- [ ] **Step 5：提交。** `git commit -m "feat: add engine session playback contract"`。

## Task 4：建立舊引擎 Adapter 與 Voice facade，先不切換正式入口

**Files:**

- Create: `addon/synthDrivers/WorldVoice/compat/__init__.py`
- Create: `addon/synthDrivers/WorldVoice/compat/engineAdapter.py`
- Create: `addon/synthDrivers/WorldVoice/compat/voiceFacade.py`
- Create: `tests/test_runtime_legacy_adapter.py`
- Create: `tests/test_runtime_voice_facade.py`

**Interfaces:**

- Consumes: Tasks 1–3 的狀態、Store、Session、Adapter 契約。
- Produces: `LegacyEngineAdapter(voice_class: type, resolve_voice: Callable[[str], object])`，實作 EngineAdapter；`detach_alias() -> None` 只清除本類別指向共用資源的相容參照，不呼叫 engineOff。
- Produces: 舊引擎 class 的 `extra_capabilities: frozenset[str]`，缺省為空；VE／Cerence 宣告 `frozenset({"waitfactor", "variant"})`，由轉接器轉為 EngineCapabilities。
- Produces: `LegacyVoiceBinding(settings: VoiceSettingsStore, session: EngineSession, spec_for: Callable[[str], VoiceSpec])`。
- Produces: `VoiceFacade.__init__(id, name, taskManager, language=None)`；保留 rate、pitch、volume、variant、inflection、rateBoost、waitfactor、revision、snapshot、update_settings、loadParameter、commit、rollback、active、speak、breaks、stop、pause、resume、close。實際 taskManager 新 API 由 Task 6 提供，本任務以同簽名的 recording fake 驗證。

- [ ] **Step 1：建立轉接合約測試。** 使用 fake legacy class 的 engineOn／engineOff／voices／supportedSettings 及 core，確認 open/close 被委派一次。加入 `test_onecore_cached_a_b_a_restores_language`，使用真實 OneCore hook 搭配 fake core 與 Session；斷言最後 core.voice="a"、language="en"，並恢復 A 的 rate。覆蓋 token 支援為 True／False／缺省時的 speak kwargs、VE／Cerence variant／waitfactor hook，以及部分 engineOn 失敗的清理。

```python
def test_facade_and_new_api_share_one_state(facade, binding):
    facade.rate = 72
    assert binding.settings.snapshot(facade.name).rate == 72
    binding.settings.state(facade.name).update(pitch=63)
    assert facade.pitch == 63
    facade.rollback()
    assert facade.rate == 50
```

  facade 測試須確認 constructor／load 不寫 core、commit_* 為同一 baseline 的代理而非副本、active 委派 session.activate(name)、speak 以語音 key／commands 入列，不捕捉舊 Voice 播放閉包。
- [ ] **Step 2：紅燈。** `python3 -m pytest tests/test_runtime_legacy_adapter.py tests/test_runtime_voice_facade.py -q -p no:cacheprovider`。
- [ ] **Step 3：實作 LegacyEngineAdapter。** open 呼叫舊 engineOn，記錄實際 notification_source；open／close 均須冪等，engineOn 拋錯時嘗試 engineOff 回收部分資源。apply 先設定 core.voice，再依 supportedSettings 套用 rateBoost、rate、pitch、volume、inflection，最後呼叫 resolve_voice(spec.name).applyEngineSettings(core, snapshot)。不得呼叫其 active／speak。capabilities 讀取 supported settings、class.extra_capabilities 與 core.supportsCancellationToken；缺少額外能力／token 宣告時使用 False。variants 讀取既有 hook，不能啟用語音。
- [ ] **Step 4：實作 VoiceFacade。** 從 class `_runtime_binding` 取得唯一 Store／Session；constructor 依 name 取得 spec 與 state。屬性只代理 state；commit_* 只代理 baseline。speak 呼叫 Task 6 的 `append_speech(request, session, name, tuple(text))`，breaks 呼叫 `append_break(request, seconds)`；不持有第二份 settings lock／revision／baseline。未綁定時明確拒絕 runtime 操作；現有直接建構 Voice 的測試在 Task 8 改為先注入 binding，不建立隱藏的全域 Store。
- [ ] **Step 5：綠燈。** 執行 Step 2 命令與 `python3 -m pytest tests/test_worldvoice_cancel_wrappers.py tests/test_f4_engine_adapters.py -q -p no:cacheprovider`，預期 PASS。此時產品入口與底層引擎未切換。
- [ ] **Step 6：提交。** `git commit -m "feat: add removable legacy voice and engine adapters"`。

## Task 5：建立 NVDA 事件 Bridge

**Files:**

- Create: `addon/synthDrivers/WorldVoice/nvdaEventBridge.py`
- Create: `tests/test_nvda_event_bridge.py`

**Interfaces:**

- Consumes: PlaybackEvent、EventKind、source_id。
- Produces: `NvdaEventBridge(owner, *, done_event, index_event, get_synth)`；`start(handler: Callable[[PlaybackEvent], None]) -> None`、`bind(source: object, source_id: object) -> None`、`unbind(source_id: object) -> None`、`close() -> None`、`index_reached(index: int) -> None`、`done_speaking() -> None`。後兩者構成 Task 6 的 NotificationOutput 契約。

- [ ] **Step 1：建立 Bridge 測試。** 用現有 EventStub 模式送入通知，斷言輸出為相同 source_id、INDEX 7／DONE；未知來源與 owner 來源不送給 handler。以兩個 `__eq__` 相等但非同一實例的來源驗證物件身分比對。加入 `test_partial_registration_is_undone`（register 先新增 handler 再拋錯）、`test_owner_change_suppresses_output`、`test_close_ignores_late_callbacks`、`test_same_source_event_has_no_invented_request_id`。
- [ ] **Step 2：紅燈。** `python3 -m pytest tests/test_nvda_event_bridge.py -q -p no:cacheprovider`。
- [ ] **Step 3：實作 Bridge。** source 對應保存強參照並以身分確認，避免 id 重用；同來源重綁不同 source_id 必須明確拒絕。close 先標記關閉，再逐一嘗試 unregister，最後清除 mapping；部分 start 失敗走相同回收。持鎖只取 mapping／handler 快照，鎖外呼叫 scheduler 或公開 NVDA 通知。只接收原始 synth／index，不附會 request／segment ID。
- [ ] **Step 4：綠燈。** Step 2 全部 PASS，並檢查公開 notify kwargs 仍只有 synth 或 synth/index。
- [ ] **Step 5：提交。** `git commit -m "refactor: isolate NVDA speech event bridge"`。

## Task 6：將 TaskManager 遷移為純排程核心

**Files:**

- Create: `addon/synthDrivers/WorldVoice/runtime/scheduler.py`
- Modify: `tests/runtime_harness.py`
- Create: `tests/test_runtime_scheduler.py`

**Interfaces:**

- Consumes: PlaybackPort、PlaybackEvent、Pause／SpeechCommands；不消費舊 Voice。
- Produces: `NotificationOutput` Protocol：`index_reached(index: int) -> None`、`done_speaking() -> None`。
- Produces: `CancellationToken.cancel/is_cancelled/wait`、`SpeechFuture.then`，沿用既有語意。
- Produces: `RequestState.BUILDING/SUBMITTED/COMPLETED/CANCELLED/FAILED`、`SpeechRequest`、`InvalidRequestState(RuntimeError)`。
- Produces: SpeechRequest 保存 `request_id: int`、`epoch: int`、`token: CancellationToken`、`state: RequestState`、`tasks: list`、`remaining: int`、`has_speech: bool`、`done_sent: bool`；failed 由 state 表達，不保留第二個可變的 failed flag。
- Produces: `TaskManager(output: NotificationOutput, *, logger=None)`；`new_request() -> SpeechRequest`、`append_speech(request, playback: PlaybackPort, voice_key: str, commands: SpeechCommands) -> SpeechFuture`、`append_break(request, seconds: float) -> SpeechFuture`、`submit_request(request) -> bool`、`abort_request(request, error: Exception) -> None`、`on_event(event: PlaybackEvent) -> None`、`cancel(playbacks: Iterable[PlaybackPort] = ()) -> None`、`cancel_current() -> None`、`pause_current(switch: bool) -> None`、`shutdown() -> None`。

- [ ] **Step 1：將既有 request manager 的行為案例套到新 fake port。** 保留 `tests/test_worldvoice_request_manager.py` 作為遷移參考，本步建立新的純核心版本。RecordingOutput 保存 indexes/done 次數；FakeAdapter 的 speak hook 可同步呼叫 manager.on_event。核心斷言：

```python
def test_synchronous_done_finishes_once(manager, port, output, rt):
    request = manager.new_request()
    port.on_speak = lambda: manager.on_event(rt.models.PlaybackEvent(rt.models.EventKind.DONE, port.source_id))
    future = manager.append_speech(request, port, "Fake:a", ("hello",))
    assert manager.submit_request(request) is True
    assert future.result(timeout=1) is True
    assert output.wait_done(timeout=1) == 1
    assert manager.submit_request(request) is False
```

  移植既有同步 done、來源不符、index 去重、done 後 index、尾端 break、啟用／播放失敗、取消 building、取消後的新 request、重疊 cancel、目前來源優先、共用來源只 stop 一次、啟用中取消、speak 返回後補停、pause/resume 的斷言。所有阻塞使用 Event 並在 finally 解除。
- [ ] **Step 2：新增狀態與重入案例。** `test_append_after_submit_is_rejected`、`test_abort_building_releases_tracking_and_futures`、`test_cancel_between_acceptance_and_output_suppresses_index_and_done`、`test_future_callback_can_cancel_and_submit`、`test_shutdown_rejects_new_request`。通知交錯用測試包裝的交付 helper 在第一次檢查後阻擋，不能把 NVDA getSynth 放回核心當測試鉤子。
- [ ] **Step 3：紅燈。** `python3 -m pytest tests/test_runtime_scheduler.py -q -p no:cacheprovider`，預期缺少新排程／API 或狀態斷言失敗。
- [ ] **Step 4：遷移 worker 與狀態。** 以原 TaskManager 為基礎保留 Condition、RLock 交付邊界、epoch、stops-in-flight、token wait。task 欄位改為 playback／voice_key／commands／seconds／future／request，無 Voice、core 或 run closure。starting 登記 source_id → activate(key) → 檢查有效性 → awaiting_done → speak(commands, token)。Future resolve/cancel/set_exception 及 callback 均在狀態鎖外。append 在非 BUILDING 狀態拋 InvalidRequestState；shutdown 後 new_request 同樣拒絕。abort_request 僅將 BUILDING 轉 FAILED，終態時無動作，SUBMITTED 時拒絕；空 request 提交後直接 COMPLETED 並移除追蹤。
- [ ] **Step 5：實作取消與通知交付。** 固定鎖順序為 delivery lock → state condition；持 state condition 不再取得 delivery lock。on_event 的初檢結束後，交付 helper 取得 delivery lock 並重新在 state lock 驗證，釋放 state lock 才呼叫 output。取消先失效 epoch/token，再於鎖外 stop；cancel_current 取消目前 request 並使用同一停止閘門，但不取消其他已排入的 request。失敗通知不以 token 已取消為唯一拒絕條件，須依 FAILED／CANCELLED 與 epoch 判定，維持失敗一次完成規則。
- [ ] **Step 6：綠燈。** 執行 Step 3；預期全部 PASS。純核心 loader 禁止 synthDriverHandler、config、logHandler 與 driver 匯入；logger 使用注入介面或標準 logging。逐項對照舊測試名稱，記錄已移植位置，不刪除競態情境。
- [ ] **Step 7：提交。** `git commit -m "refactor: decouple speech scheduler from voices and NVDA"`。

## Task 7：建立 SelectVoice builder 並修正 F6

**Files:**

- Create: `addon/synthDrivers/WorldVoice/runtime/requestBuilder.py`
- Create: `addon/synthDrivers/WorldVoice/compat/commands.py`
- Create: `tests/test_runtime_request_builder.py`
- Create: `tests/test_legacy_speech_commands.py`

**Interfaces:**

- Consumes: TaskManager、SelectVoice、Pause、PlaybackPort。
- Produces: `queue_speech_sequence(task_manager: TaskManager, speech_sequence: Iterable[object], default_voice_key: str, resolve: Callable[[str], PlaybackPort | None]) -> bool`。
- Produces: `normalize_legacy_commands(sequence: Iterable[object]) -> Iterator[object]`：只在此邊界辨識舊 Voice 與 NVDA BreakCommand，輸出 SelectVoice／Pause；其他命令原樣傳遞。

- [ ] **Step 1：建立 F6 序列測試。** 以下示意中的 recording_builder 用真實 builder 與只記錄提交內容的 manager：

```python
def test_unavailable_segment_does_not_block_next_voice(recording_builder, rt):
    select, pause = rt.models.SelectVoice, rt.models.Pause
    recording_builder.run(["A", select("missing:x"), "skip", 999, pause(1),
                           select("Fake:b"), "B", pause(0.2)], default="Fake:a")
    assert recording_builder.speech == [("Fake:a", ("A",)), ("Fake:b", ("B",))]
    assert recording_builder.breaks == [0.2]
    assert recording_builder.submit_count == 1
```

  另測 default 不可用後恢復、多個不可用切換、全部跳過、有效 index 順序、尾端 break；整合測試使用真 scheduler 確認只在尾端 break 結束後 done。
- [ ] **Step 2：建立建構失敗與相容命令測試。** `test_generator_failure_aborts_unsubmitted_request`：yield "A" 後拋 RuntimeError，沒有播放、tracked request 移除、Future 結束；`test_cancel_during_build_returns_false`：取消後 append 被拒絕不改為 FAILED；`test_normalizer_handles_voice_and_break`：舊 Voice → SelectVoice(name)，200ms → Pause(0.2)，原有 index 物件保持同一身分。
- [ ] **Step 3：紅燈。** `python3 -m pytest tests/test_runtime_request_builder.py tests/test_legacy_speech_commands.py -q -p no:cacheprovider`。
- [ ] **Step 4：實作建構與正規化。** SelectVoice 必須先於可用性檢查；flush 原有效 buffer 後切換 key。Pause 只在可用區段入列。resolver 的 None 表示不可用；其他 resolver 例外視為建構失敗，abort 後重新拋出。取消／shutdown 已使 request 無效時返回 False。全部 task 建立完成才 submit；speech commands 存為 tuple。
- [ ] **Step 5：綠燈。** 執行 Step 3 命令，預期 PASS；測試新 builder 可在禁止匯入 driver／speech.commands 時載入，只有 compat normalizer 依賴這些型別。
- [ ] **Step 6：提交。** `git commit -m "fix: recover voice routing after unavailable engines"`。

## Task 8：切換正式入口、Session 所有權與 F5 整合

**Files:**

- Modify: `addon/synthDrivers/WorldVoice/driver/__init__.py`
- Modify: `addon/synthDrivers/WorldVoice/driver/engineSession.py`
- Modify: `addon/synthDrivers/WorldVoice/driver/VE/__init__.py`
- Modify: `addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py`
- Modify: `addon/synthDrivers/WorldVoice/taskManager.py`
- Modify: `addon/synthDrivers/WorldVoice/requestBuilder.py`
- Modify: `addon/synthDrivers/WorldVoice/voiceManager.py`
- Modify: `addon/synthDrivers/WorldVoice/__init__.py`
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py`
- Modify: `tests/test_worldvoice_lifecycle.py`
- Modify: `tests/test_worldvoice_request_manager.py`
- Modify: `tests/test_worldvoice_request_builder.py`
- Modify: `tests/test_f4_voice_state.py`
- Modify: `tests/test_f4_engine_session.py`
- Modify: `tests/test_voice_settings_transaction.py`
- Create: `tests/test_runtime_composition.py`

**Interfaces:**

- Consumes: Tasks 1–7 的全部正式介面。
- Produces: `VoiceManager(taskManager: TaskManager, settings: VoiceSettingsStore, bridge: NvdaEventBridge)`；`resolve_playback(key: str) -> PlaybackPort | None`、`getVoiceSpec(key: str) -> VoiceSpec`、`getVoiceCapabilities(key: str) -> EngineCapabilities`、`getVoiceVariants(key: str) -> tuple[Mapping[str, str], ...]`。既有名稱查詢與 facade 取得入口保持可用。
- Produces: pipeline `lang_cmd_to_voice(...)` 保留函式名稱，但輸出改為 SelectVoice(key)；語言選擇規則維持既有行為。
- Produces: 主入口建立 ConfigVoiceSettingsRepository → Store → Bridge → TaskManager(output=bridge) → bridge.start(manager.on_event) → VoiceManager。主入口保存每個成功取得的資源以供 rollback。

- [ ] **Step 1：新增組裝生命週期測試。** `test_only_started_sessions_are_resolvable`（類別可載入但 open 失敗仍不可路由）、`test_shared_source_alias_uses_one_session_and_close`、`test_initialization_failure_closes_without_commit`、`test_worker_stops_before_bridge_and_sessions_close`、`test_cached_onecore_voice_round_trip_through_manager`。沿用 F2 的 manager／dictionary 階段注入失敗，加入 bridge start/bind 失敗；單項 cleanup 拋錯仍回收其他資源。
- [ ] **Step 2：紅燈。** `python3 -m pytest tests/test_runtime_composition.py -q -p no:cacheprovider`，預期新組裝參數或資源順序尚未符合。
- [ ] **Step 3：接上 facade 與引擎能力。** 共用 `Voice` 繼承 VoiceFacade，保留 metadata helper、ready、supportedSettings 與原始 core 建立／釋放方法；engineOn 只建立 core，不再自行建立另一個 Session。state／Repository 行為從舊類別移除。VE／Cerence 類別新增明確的 waitfactor／variant 能力宣告，保留目前 applyEngineSettings 與取消防護。`driver/engineSession.py` 重新匯出新型別；新核心不從該路徑匯入。
- [ ] **Step 4：實作 VoiceManager 的唯一所有權。** manager 每個引擎建立 Adapter，先 open，依 notification_source 查找已取得資源；同 core alias 綁至既有 Session，不建立第二個 owner，關閉時 alias 呼叫 detach_alias 而非 engineOff。唯一來源交由 Session 接管（adapter.open 必須冪等），綁定 bridge 後才發布可用表。將 `_runtime_binding` 指向同一 Store／Session，建立 facade 前 ensure spec。取得失敗以相反順序逐項清理；terminate(commit=False) 不保存設定。
- [ ] **Step 5：切換主入口與 builder。** 主入口注入 NVDA bus、getSynth、logger；speak 將 pipeline 輸出正規化後交給新 builder 與 resolve_playback。TaskManager 舊模組只匯出新類別／型別，不保留舊 worker；requestBuilder 舊模組只委派。VoiceManager.cancel 傳 Session；waitfactor 依能力更新 state。正常 terminate 先停止提交／worker，再關閉 Bridge，再逐項保存並關閉 Session；初始化失敗須以明確旗標選 commit=False。
- [ ] **Step 6：遷移既有測試的組裝方式。** request manager 測試改注入 fake port/output，NVDA 註冊案例移到 Bridge 測試；所有行為案例保留或在新測試檔找到同等覆蓋。F4 測試改用 binding／新 Session API，保留設定不碰 core、每段一次 activation、原子更新與取消競態斷言。F3 fixture 直接建構 Voice 時也要先注入 Store／binding；fixture 調整列入此切換提交。
- [ ] **Step 7：綠燈與相關回歸。** `python3 -m pytest tests/test_runtime_composition.py tests/test_worldvoice_lifecycle.py tests/test_worldvoice_request_manager.py tests/test_worldvoice_request_builder.py tests/test_f4_voice_state.py tests/test_f4_engine_session.py tests/test_f4_engine_adapters.py tests/test_worldvoice_cancel_wrappers.py tests/test_voice_settings_transaction.py -q -p no:cacheprovider`。全部 PASS，並檢查沒有從新核心回到 facade.active/speak 的循環。
- [ ] **Step 8：提交本任務變更。** 對原先已有修改的檔案檢查 diff，僅 stage 本任務相關內容；需要的 F2／F3 基底保留且記錄，不納入無關翻譯。`git commit -m "refactor: wire voice sessions and event bridge into WorldVoice"`。

## Task 9：設定 UI 使用共用編輯 session 與能力入口

**Files:**

- Modify: `addon/globalPlugins/WorldVoice/speechSettingsDialog.py`
- Modify: `addon/synthDrivers/WorldVoice/voiceManager.py`
- Modify: `addon/synthDrivers/WorldVoice/__init__.py`
- Modify: `tests/test_voice_settings_transaction.py`
- Modify: `tests/test_f4_voice_state.py`

**Interfaces:**

- Consumes: Store.begin_edit、VoiceEditSession、VoiceManager.getVoiceCapabilities/getVoiceVariants。
- Produces: `VoiceManager.beginVoiceSettingsEdit() -> VoiceEditSession`。滑桿仍可使用 facade 屬性，新 UI 的能力與變體查詢直接使用 manager。

- [ ] **Step 1：擴充既有 F3 測試。** `test_dialog_late_voice_is_restored_on_discard`、`test_apply_rebases_voice_and_role_edit_state`、`test_save_failure_keeps_pending_values_and_baseline`、`test_dialog_destroy_releases_edit_session`。保留保持參數一致、保持引擎一致的現有預覽／取消／套用案例。

```python
def test_apply_then_discard_uses_applied_value(panel, voice):
    voice.rate = 72
    panel.onSave()
    voice.rate = 81
    panel.onDiscard()
    assert voice.rate == 72
```

  再確認對已選 voice 的多欄位一致性複製仍呼叫 state.update 一次，worker 看不到半套參數；能力查詢使用 fake engine 名稱也可啟用 waitfactor，不依賴 VE／Cerence 字串。
- [ ] **Step 2：紅燈。** `python3 -m pytest tests/test_voice_settings_transaction.py tests/test_f4_voice_state.py -q -p no:cacheprovider`，預期新增交易情境失敗。
- [ ] **Step 3：接上編輯 session。** SpeechRoleSettingsPanel 在 manager ready 後 begin_edit；onSave 先完成必要的參數一致性預覽，再 apply，成功後更新角色／引擎一致性取消基準。onDiscard 回復同一編輯範圍與 manager 預覽旗標。對話框關閉時 close；取消路徑先 discard 再 close，套用後繼續編輯則保留 session。使用現有錯誤呈現入口回報保存失敗，不把失敗當成功套用。
- [ ] **Step 4：整理設定入口。** `_getVoiceSupportedSettings`／變體清單改用 manager 能力 API。保留主 SynthDriver 設定 setter 的明確 commit 行為，但 commit 實作集中 Store／Repository。UI 不再直接迭代私有 cache 來維護各自的取消基準；role mapping 的 F3 邊界保持由 UI／manager 管理。
- [ ] **Step 5：綠燈。** 執行 Step 2，並加上 Task 2 的兩個測試檔，預期 PASS。
- [ ] **Step 6：提交相關 hunks。** `git commit -m "refactor: share voice editing state across settings interfaces"`。

## Task 10：驗證相容層可移除，完成回歸與紀錄

**Files:**

- Create: `tests/test_runtime_adapter_contract.py`
- Modify: `tests/runtime_harness.py`
- Modify: `review_gpt1.md`（只在本次範圍加入後續紀錄，保留原始發現）
- Create: `docs/superpowers/finish/2026-09-26-voice-runtime-boundaries-validation.md`

**Interfaces:**

- Consumes: 同一 EngineAdapter／PlaybackPort／Store／TaskManager 契約，分別以直接新 Adapter 與 LegacyEngineAdapter 組裝。
- Produces: 相容性、回歸與原生驗證限制的可追溯紀錄。

- [ ] **Step 1：建立兩種組裝共用的合約案例。** 參數化 adapter_kind="native"／"legacy"。兩者執行相同的 A→B→A、pending72→apply→pending81→discard、同步 done、取消／後續請求、關閉一次情境，斷言完全相同。native 組裝須在禁用 compat、driver、NVDA 模組的 loader 下成功執行；不要以複製一份 scheduler 或設定服務通過此測試。
- [ ] **Step 2：驗證邊界。** `python3 -m pytest tests/test_runtime_adapter_contract.py -q -p no:cacheprovider`。若失敗，依錯誤回到責任所屬任務修正；通過後檢查 `runtime/` 無 config、synthDriverHandler、logHandler、compat、driver 匯入，無 voice.core／READY_ENGINE_CLASS 型別判斷。檢查只保留一份 worker、設定寫入與回復實作。
- [ ] **Step 3：執行完整本專案回歸。** `python3 -m pytest tests -q -p no:cacheprovider`，記錄實際數字與命令。全部通過後才執行 `git diff --check`；不收集 `ref/nvda`。若有失敗，只針對具體原因補查／重跑，變更後再執行受影響範圍。
- [ ] **Step 4：記錄整合驗證。** 在可用 Windows／NVDA 環境確認 OneCore 快取切換、跨引擎長文、說全部、index、尾端停頓、快速取消、pause/resume、設定套用與取消，以及可取得的外部引擎版本。無此環境時逐項標記「尚未實機驗證」，不得以 fake 通過取代實機結論。F7 明確維持未處理。
- [ ] **Step 5：更新 review 與驗證文件。** F5 記錄沿用既有 hook 並補齊快取切換證據；F6 記錄跳過／恢復策略；A1／A4 記錄新責任位置及移除相容層的驗證。列出保留的 F2／F3 工作目錄前提、實際測試結果與未驗證限制。
- [ ] **Step 6：提交本任務測試與文件。** 對 `review_gpt1.md` 只追加本次實際修正與驗證紀錄；驗證文件以精確路徑 `git add -f`。`git commit -m "test: verify removable compatibility layer and runtime regressions"`。

## Spec 覆蓋對照與計畫自查

| Spec 要求 | 任務與證據 |
| --- | --- |
| F5 快取語音切換 | Task 3 通用 A→B→A；Task 4 OneCore hook；Task 8 真 manager 組裝 |
| F6 不可用 default／途中失效／恢復 | Task 7 序列、generator 失敗與取消建構測試 |
| A1 資料、設定、引擎分責 | Tasks 1–4；Task 8 單一所有權；Task 9 UI |
| A4 事件邊界與 request 狀態 | Task 5 Bridge；Task 6 狀態、交付與競態；Task 8 生命週期 |
| 下一段快照、原子編輯與 F3 | Tasks 1–3、9 |
| 初始化失敗、逐項回收與 F2 | Tasks 3–5、8 |
| 移除相容層無須重寫 | Task 10 共用契約與禁止舊模組匯入 |
| 相容外部引擎、native 限制、F7 邊界 | Tasks 4、5、10，明確記錄實機狀態 |

自查時確認：所有後續引用的型別與方法都由前面任務定義；五項 Review Focus 均有具名測試；設定與事件只有一份權威狀態；新增模組在正式切換前可獨立測試。文件中的 PASS 均為未來執行的預期結果，不是目前已執行的測試報告。

## 執行交接

使用者需先審閱本計畫並選擇執行方式。此計畫的任務共用多個介面、以連續遷移為主，建議 Native：同一實作者依序處理，最後由獨立 reviewer 檢查整體。若選 Subagent-driven，則每個任務由新的實作者及 reviewer 完成檢查後再進到下一項。
