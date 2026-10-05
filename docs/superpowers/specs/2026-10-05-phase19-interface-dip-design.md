# 階段 19：介面瘦身與 DIP 收尾

日期：2026-10-05。
基準：`master`（`31e6661`，階段 18 合併完成）。分支：`phase19-interface-dip`。
狀態：依使用者要求自動執行（spec → plan → 實作），無需使用者決定。

本文件對應 `storage/refactor4.md`（第四輪審查，不入版控）§11 階段 19。細節在：

- §1.3（N2）、§1.4（N1、N4）、§1.1（N11）；
- §2.3（N5）、§3.1（N8）、§3.4（N7）；
- §4（`Voice.voices()` 的 `ready()`）、§6.2（N9）、§8（`discovery._log`）；
- §9 的 N 表。

以下行號都以 `31e6661` 為準，每一項都已在原始碼上逐行複核。

## 現況與複核結果

| # | 位置 | 複核結果 |
| --- | --- | --- |
| N1 | 主驅動 `__init__.py:336-366` | 成立。`speak` 以 `_terminated` 守門。`cancel` 直接呼叫 `self._voiceManager.cancel()`，`pause` 直接呼叫 `self.taskManager.pause_current()`；`terminate` 的 `finally`（323）把兩者設為 `None`，之後呼叫就會 `AttributeError`。 |
| N2 | 主驅動 `:242`；`mainLocalePolicy.py:92-100`；`configRepository.py:12-35` | 成立，原因見下方。 |
| N4 | 主驅動 `:420-426`；`voiceManager.py:281-291` | 成立。`getVoiceNameForLanguage` 的兩個出口都是字串（`configured`，或 `self.defaultVoiceName`），所以 `_get_voice` 的 `if voice is None` 不可達。`getVoiceInstanceForLanguage` 在 `addon`、`tests`、`ref/Neural` 都沒有呼叫者。 |
| N5 | `runtime/session.py:125-129、143-144`；`voiceManager.py:115` | 成立。`replace_adapter` 只有 `tests/test_runtime_session.py:91`、`tests/test_f4_engine_session.py:107` 呼叫。`EngineSession.list_voices` 只有 `tests/test_runtime_session.py:205` 與 `tests/runtime_harness.py:424` 呼叫；生產端 `VoiceManager._publish` 直接呼叫 `adapter.list_voices()`。`EngineAdapter` Protocol（34-60）另外列了 `notification_source`，session 也從未使用。`ref/Neural` 不碰 session。 |
| N7 | `runtime/settings.py:17-26`；`mainLocalePolicy.py:8`；`rolePresenter.py:5`；`compat/engineAdapter.py:143`；主驅動 `:78-86` | 成立，confspec 的實際作用見下方。 |
| N8 | `voiceManager.py:4-5、65-72、201-206`；`configRepository.py:19` | 成立。`_init_policies` 在 manager 內以全域 `config.conf` 建立 `conf_provider`，`languageHandler.getLanguage` 在 `_init_policies` 與 `_getDefaultVoiceSpec` 各直接引用一次。`ConfigVoiceSettingsRepository` 另外自建一個 `ParameterConsistency`。 |
| N9 | `speechSettingsDialog.py:312-319` | 成立。`set_main_voice` 寫 `config.conf["speech"]["WorldVoice"]`，`speech_section` 讀 `config.conf["speech"][synth.name]`。 |
| N11 | 主驅動 `:181-225` | 成立。四個清理在 `_new_teardown()` 預先登記，以 None 守衛等資源出現；其餘七個（含階段 18 新增的 `detection settings unsubscribe`）都在取得後登記。 |
| `ready()` | `driver/__init__.py:53`；`engine/discovery.py:176-179` | 成立。discovery 只回傳 `ready()` 為真的類別，`voices()` 又檢查一次。六家 wrapper 與 `ref/Neural` 都沒有覆寫 `ready()` 或 `voices()`。 |
| `_log` | `engine/discovery.py:26-32` | 成立。`_log(logger, method, …)` 以 `logger is None` 與 `getattr(logger, method, None)` 兩次判斷處理「沒有 logger」。 |

### N2：建構期間的 `getSynth()`

`ConfigVoiceSettingsRepository(config.conf, lambda: getSynth().name)`（主驅動 242）。

NVDA 的 `setSynth()` 先把 `_curSynth` 設為 `None`，再呼叫 `getSynthInstance()`（`ref/nvda/source/synthDriverHandler.py:530-537`）。`getSynthInstance` 在回傳之前呼叫 `newSynth.initSettings()` → `loadSettings()`（`:490-495`、`:364-385`）。所以從 `SynthDriver.__init__` 一直到 `loadSettings` 結束，`getSynth()` 都是 `None`。

這段期間載入的語音，都走同一條例外路徑：

1. `repository.load` 呼叫 `ParameterConsistency.shared_section(synth_name)`；
2. `KeepMainLocaleParameterConsistent` 開啟時，`synth_name()` 以 `AttributeError` 失敗；
3. 失敗被 `mainLocalePolicy.py:98` 的 blind except 吞掉、回傳 `None`；
4. `load` 退回語音自己的值。

這段期間載入的語音包括：建構時的主語音、VE／Cerence 支援 waitfactor 的每個語音（`_apply_pipeline_settings` → `waitfactor` setter → `settings.ensure`），以及 `loadSettings` 的 `changeVoice`。

noqa 寫的理由是「the speech section may not exist during synth startup」。這只在首次載入成立，正常啟動失敗的原因是 `getSynth()` 為 `None`。

NVDA 的 `config.conf["speech"]` 是 `AggregatedSection`。它的 `__getitem__` 在鍵不存在時拋 `KeyError`，`get(key, default)` 則回傳預設值（`config/__init__.py:1178-1232、1249-1253`）。`__setitem__` 建立區段時，會清掉快取的「不存在」紀錄（1342-1344），所以「先查不到、`initSettings` 之後再建立」的順序不會讀到舊的快取。

### N7：`voices.__many__` confspec 的實際作用

NVDA 的 `AggregatedSection.__getitem__` 用 `self._spec.get(key)` 取子鍵的 spec（`config/__init__.py:1194`），沒有展開 `__many__`。這和 ConfigObj 的行為一致：`__many__` 只在 `validate()` 時展開。

所以 `voices["Espeak:xx"]` 拿到的 spec 是 `None`，NVDA 隨即為它建一個空 spec（1234-1238），葉值不驗證、原樣回傳字串。NVDA 自己需要 `__many__` 時，是明確複製一份（`autoSettingsUtils/autoSettings.py:134`）。WorldVoice 的程式碼也已經按「拿到的是字串」處理：

- `runtime/settings.boolean`（「Preserve the existing voice configuration's boolean conversion」）；
- `engine/discovery.coerce_bool`（`engine.__many__` 同理）。

結論：`config.conf.spec["WorldVoice"]["voices"]["__many__"]` 在 NVDA 執行期不參與讀寫，是文件性質的宣告。刪掉 `waitfactor`、補上 `inflection`／`rateBoost` 不改變既有使用者設定檔的讀寫：

- 設定檔裡既有的 `waitfactor` 鍵仍留在檔案中，沒有程式讀它（`tests/test_voice_config_repository.py:91-94` 已固定 `save` 保留未知鍵）；
- 未來若有人改用 `validate()`，WorldVoice 寫入的值也都符合產生的 spec。這些值是 `int` 0–100，`variant` 是字串，`rateBoost` 是 `"True"`／`"False"`。

## 需求與範圍

### 1. N1：`cancel`／`pause` 與 `speak` 同一種守門

- `cancel()` 與 `pause()` 開頭加 `if self._terminated: return`，和 `speak()` 相同。
- 契約測試：建構成功、`terminate()` 之後，`speak`、`cancel`、`pause(True)` 都靜默返回，不碰 manager 或 task manager。
- 這是修正（terminate 之後不再拋例外），沒有其他可見行為改變。

### 2. N2：`synth_name` 是 synth 自己的名字，`shared_section` 是查詢

- 主驅動：`ConfigVoiceSettingsRepository(config.conf, self.name, parameters)`。`self.name` 是類別屬性 `"WorldVoice"`；這與 `SpeechRoleSettingsPanel` 以 `synth.name` 取 speech 區段的做法一致。
- `ConfigVoiceSettingsRepository.__init__(conf, synth_name: str, parameters=None)`：`synth_name` 由 `Callable[[], str]` 改為 `str`。
  - 名字是常數，不需要延遲求值。
  - 改成字串之後，「取名字會失敗」這個情況從型別上就消失了。
- `ParameterConsistency.shared_section(synth_name: str) -> Mapping | None`：

  ```python
  if not self.enabled:
  	return None
  speech = self._conf_provider().get("speech")
  return None if speech is None else speech.get(synth_name)
  ```

  blind except 與 noqa 一起刪除；docstring 寫明區段在首次載入前可能不存在。
- `load` 內「主 synth 的值無效時退回語音自己的值」那個 `except`（`configRepository.py:28-32`）不變：它處理的是 NVDA 驗證失敗，與本項無關。
- **特性測試先行**（刪 except 之前，以現有程式通過）：
  - 停用 → `None`；
  - 啟用且區段存在 → 回傳區段；
  - 啟用但 speech 下沒有該 synth 區段 → `None`，`load` 用語音自己的值；
  - 用一個仿 `AggregatedSection` 的 stub：`__getitem__` 拋 `KeyError`、`get` 回傳預設值，結果同上。
- 原本兩個測試固定的是「取名字的函式拋例外時退回語音自己的值」與「`KeyboardInterrupt` 不被吞」（`tests/test_voice_config_repository.py:55-76`，以及 `tests/test_main_locale_policy.py:94-96` 的 `unavailable`）。名字改為字串後這個輸入不再存在，這些測試刪除。
- 主驅動測試：建構時 repository 收到的名字是 `"WorldVoice"`，建構過程不呼叫 `getSynth()`。
- 啟動期間是否查共用區段，由下面的明確閘門決定（審查後補上）。

**啟動期間的明確閘門**（審查後修正；啟動行為與舊實作完全相同）：

- 舊實作「沒有共用區段」的期間，就是 `getSynth()` 為 `None` 的期間。NVDA 的 `setSynth` 先把 `_curSynth` 設為 `None`，再呼叫 `getSynthInstance()`；後者依序建構 driver、呼叫 `initSettings()`（首次載入是 `changeVoice` + `saveSettings`，否則是 `loadSettings`），回傳之後 `setSynth` 才執行 `_curSynth = …`（`synthDriverHandler.py:490-495、530-537`）。`initSettings` 回傳與 `_curSynth` 指派之間沒有任何 WorldVoice 程式碼執行，所以邊界就是「`initSettings` 回傳」。
  - `_bridge/runtimes/synthDriverHost` 會在建構後直接指派 `_curSynth`、不呼叫 `initSettings`，但那是 32 位元 out-of-process 驅動的宿主，不會載入 WorldVoice 這個 add-on。
- 實作：
  - `ConfigVoiceSettingsRepository(conf, synth_name, parameters, *, main_settings_ready: Callable[[], bool] = lambda: True)`；`load` 只有在 `main_settings_ready()` 為真時才查 `shared_section`，否則等同沒有共用區段。
  - 主驅動以 `main_settings_ready=lambda: self._settingsInitialized` 建立 repository；`__init__` 設為 `False`，覆寫 `initSettings()`：先呼叫 `super().initSettings()`，回傳後設為 `True`。
  - `synth_name` 仍是 driver 自己的名字；閘門是另一個明確命名的條件，不再藉由例外表達。
- 結果：建構期間（含 `_apply_pipeline_settings` → `waitfactor` setter 對每個 VE／Cerence 語音的 `settings.ensure`）與 NVDA `initSettings` 期間載入的語音，即使 `KeepMainLocaleParameterConsistent` 開啟，也載入自己的值（含 `variant`、`inflection`、`rateBoost`）。之後才延遲載入的語音照舊使用共用區段。
- 為什麼一定要保留：`variant` 不在 `PARAMETER_NAMES` 裡，`copy_from`／`onVoiceParameterConsistent` 不會把它拉平。若啟動期間就讀共用區段，每個 VE／Cerence 語音都會拿到主 synth 的 variant（例如 eSpeak 的 `max`），`applyEngineSettings` 以 `ValueError("Unavailable variant")` 失敗、該句靜音，`onVoiceParameterConsistent` 的 commit 還會把外來的 variant 寫回 `voices[...]`。
- 特性測試：
  - repository：閘門關閉時載入語音自己的值，開啟後載入共用區段；
  - 組裝：manager 建構期間載入的主語音保有自己的 `rate`／`variant`／`inflection`／`rateBoost`，閘門開啟後延遲載入的語音使用共用區段；
  - 主驅動：建構後與 NVDA `initSettings` 執行期間閘門關閉，`initSettings` 回傳後開啟。
- **已知的既有問題（不在範圍內）**：driver 上線之後，延遲載入的語音（或 profile 切換後重新載入）在參數一致性開啟時仍會從共用區段拿到主 synth 的 `variant`。這與舊實作相同，本階段不修。
- 舊實作在 driver 被 `terminate`、另一個 synth 成為目前 synth 之後，`getSynth().name` 會是那個 synth 的名字；那時不會再有語音載入，所以不需要重現。

### 3. N4：刪死分支與無呼叫者的方法

- `_get_voice`：`_voice is None` 時直接回傳 `getVoiceNameForLanguage(languageHandler.getLanguage())`，刪 `if voice is None:` 分支。
- `VoiceManager.getVoiceInstanceForLanguage` 刪除。
- 先寫特性測試固定 `_get_voice` 的兩條路：`_voice is None` 時回傳 manager 依 NVDA 語言選出的名字；否則回傳 `defaultVoiceName`。
- 守門：`voiceManager.py` 不含 `getVoiceInstanceForLanguage`（加進 `tests/test_voice_manager_structure.py` 的 `FORBIDDEN`）。

### 4. N5：`EngineSession` 與 `EngineAdapter` Protocol 只留 session 用到的

- 刪 `EngineSession.replace_adapter` 與 `EngineSession.list_voices`。
- `EngineSession` docstring 的「opens, closes, or replaces resources」改為「opens or closes」。
- `EngineAdapter` Protocol 刪 `notification_source` 與 `list_voices` 兩個 session 從未使用的成員。docstring 寫明分工：
  - Protocol 是 session 播放期間需要的介面；
  - `VoiceManager` 以具體的 `LegacyEngineAdapter` 建構並配置 adapter，自己使用 `open`、`list_voices`、`notification_source`、`configure_completion`、`configure_segment_events`。

  Protocol 沒有 `runtime_checkable`，只是型別說明，刪成員不影響執行。
- 測試：
  - `test_replace_adapter_changes_source_and_reapplies` 與 `test_replace_core_reapplies_same_snapshot` 固定的行為是「重新開啟後換新 `source_id`、同一份 snapshot 重新套用」，這兩個測試改用 `close()` + `open()` 表達。
  - `test_capability_and_metadata_queries_do_not_activate` 刪掉 `session.list_voices()` 那一行。
  - `runtime_harness.py:424` 改為 `adapter.list_voices()`（與生產端 `_publish` 同一條路）。
- 守門：`runtime/session.py` 不含 `def replace_adapter`、`def list_voices`。

### 5. N7：語音參數名稱單一來源

- `runtime/settings.py` 匯出 `PARAMETER_NAMES = tuple(name for name, _, _ in VOICE_PARAMETERS if name != "variant")`，註解為「可以從一個語音複製到其他語音的參數」。值與現有兩份逐字相同：`("rate", "pitch", "volume", "inflection", "rateBoost")`。
- `mainLocalePolicy.py` 改為 `from .runtime.settings import PARAMETER_NAMES`。
- `globalPlugins/WorldVoice/rolePresenter.py` 改為 `from synthDrivers.WorldVoice.runtime.settings import PARAMETER_NAMES`，與 `speechSettingsDialog.py` 引用 synth 套件的方式相同。
- `compat/engineAdapter.py` 的套用順序抽成模組常數 `APPLY_ORDER = ("rateBoost", "rate", "pitch", "volume", "inflection")`。註解說明兩點：
  - 這是 `PARAMETER_NAMES` 的套用順序；
  - `rateBoost` 必須先套用，因為 eSpeak 的 `_set_rate` 依 `_rateBoost` 換算（`ref/nvda/source/synthDrivers/espeak.py:264-282`）。
- `configRepository.py` 匯出 `VOICE_CONFSPEC`，由 `VOICE_PARAMETERS` 產生：`int` → `integer(default=…,min=0,max=100)`、`boolean` → `boolean(default=…)`、其他 → `string(default=…)`。
  - 主驅動 `voices.__many__` 改為 `dict(VOICE_CONFSPEC)`，`waitfactor` 鍵消失，`inflection`／`rateBoost` 補上。
  - `rate`／`pitch`／`volume` 三行與舊 spec 逐字相同。
  - `variant` 的預設值由 `None` 改為 `default`，與 `VOICE_PARAMETERS` 和 `load` 實際寫入的預設值一致。理由見「現況」：這個 spec 在執行期不參與讀寫。
- 守門測試：
  - `set(VOICE_CONFSPEC) == {name for name, _, _ in VOICE_PARAMETERS}`；
  - `set(APPLY_ORDER) == set(PARAMETER_NAMES)`；
  - `rolePresenter.py`、`mainLocalePolicy.py` 不再定義自己的參數名單（原始碼不含 `PARAMETER_NAMES = (`）；
  - 主驅動的 `voices.__many__` 來自 `VOICE_CONFSPEC`（AST 檢查）。

### 6. N8：`VoiceManager` 的政策依賴由組裝根注入

- `VoiceManager.__init__(…, *, index_ledger, completion_for, engine_classes, conf_provider, get_language, parameter_consistency=None, roles=None)`：
  - `conf_provider`、`get_language` 為必填關鍵字參數，因為 manager 不再 import `config`、`languageHandler`，沒有可以退回的全域；
  - `parameter_consistency`、`roles` 未給時，以 `conf_provider` 自建。
- `_init_policies(conf_provider, get_language, *, roles=None, parameter_consistency=None)`：同時保存 `self._get_language`，供 `_getDefaultVoiceSpec` 使用。
- `voiceManager.py` 刪 `import config`、`import languageHandler`。
- 組裝根（主驅動 TaskManager 那一步）：
  - 建立一個 `parameters = ParameterConsistency(lambda: config.conf)`；
  - 交給 `ConfigVoiceSettingsRepository(config.conf, self.name, parameters)` 與 `VoiceManager(…, conf_provider=lambda: config.conf, get_language=languageHandler.getLanguage, parameter_consistency=parameters)`。
  - 同一個政策只有一個實例。
- 測試：
  - 呼叫 `manager._init_policies()` 的測試改傳 provider（以 helper 集中）；
  - 組裝 harness（`tests/test_runtime_composition.py` 的 `create`、`tests/runtime_drain_integration_harness.py`、`tests/test_worldvoice_lifecycle.py` 的兩處）補兩個參數；
  - 主驅動測試確認 repository 與 manager 拿到同一個 `ParameterConsistency`；
  - 守門：`voiceManager.py` 不 import `config`、`languageHandler`（AST）。

### 7. N9：speech 區段一種拼法

`set_main_voice` 的 `config.conf["speech"]["WorldVoice"]["voice"]` 改為 `config.conf["speech"][synth.name]["voice"]`，與第 318 行的 `speech_section` 相同。此處 `synth.name` 必為 `"WorldVoice"`（`makeSettings` 開頭已判斷），行為不變。

### 8. N11：清理在資源取得後登記

- 刪 `_new_teardown()`。`__init__` 直接 `self._teardown = Teardown(self._TEARDOWN_ORDER, nvdaLog)`。
- `_initialize` 在每個資源建立後立即登記：
  - `IndexLedger` → `"index ledger close"`；
  - `NvdaEventBridge` → `"event bridge close"`；
  - `TaskManager` → `"task manager shutdown"`，登記在 `bridge.start()` 之前；
  - `VoiceManager` → `"voice manager terminate"`。
- 清理函式捕捉剛建立的物件，不再讀 `self.x` 再做 None 守衛。唯一的例外是 `"task manager shutdown"`：它仍需在執行時讀 `self._voiceManager`，因為 manager 在 task manager 之後才建立，可能不存在。
- `_TEARDOWN_ORDER` 不變，所以清理順序不變。
- `__init__` 的 `= None` 初始化保留：`speech_context`、`voice_manager`、`_apply_pipeline_settings` 都讀這些屬性，`terminate` 也把它們設回 `None`。刪掉只會讓「建構失敗後屬性不存在」成為新的狀態。
- 測試：
  - `tests/test_worldvoice_lifecycle.py` 既有的建構失敗測試（manager、symbols、bridge、pipeline）不改斷言；
  - `test_terminate_cleanup_logs_errors_but_lets_interrupts_through` 原本以 `_new_teardown()` 建立，改為走真正的建構流程（bridge 的 `close` 拋錯），斷言不變。
  - `tests/test_runtime_composition.py` 的 `make_synth` 以真實 runtime 物件驗證拆卸順序，原本也呼叫 `_new_teardown()`。改為以驅動的 `_TEARDOWN_ORDER` 建 `Teardown`，並照 `_initialize` 的方式登記四個 runtime 清理。

### 9. `Voice.voices()` 不再檢查 `ready()`

- `driver/__init__.py:53` 改為 `if not core: return result`。
- 理由：
  - 唯一的呼叫者 `LegacyEngineAdapter.list_voices` 只處理 `ready_engine_classes` 回傳的類別，discovery 已經檢查過 `ready()`；
  - 六家 wrapper 與 `ref/Neural` 都不覆寫 `ready()`。
- `Voice` 的公開介面（`ready`、`voices` 都還在）與 `tests/test_plugin_voice_contract.py` 不變。

### 10. `discovery` 的 Null Object logger

- `discover_engine_specs`、`_load_manifest`、`load_enabled_engine_classes` 開頭 `logger = logger or _LOG`，`_LOG = logging.getLogger(__name__)`；刪 `_log`，改為直接呼叫 `logger.debug`／`warning`／`error`。
- 生產端一律傳入 NVDA 的 `log`（`engine/__init__.py:22-28、35`），行為不變。
- 不傳 logger 的呼叫（只有測試）改由 stdlib logging 處理。NVDA 把 handler 掛在 root logger（`logHandler.py:673`），所以在 NVDA 內這些訊息也會進 nvda.log；`compat/engineAdapter.py` 的 `list_voices` 已經這樣做。
- `assembly.timed` 的 `if logger is not None` 不改：它是主驅動與 discovery 共用的小工具，discovery 改後一律傳入非 `None` 的 logger。

## 決定

- **N2 啟動閘門以 `initSettings` 回傳為界**（審查後補上）：這正是舊實作 `getSynth()` 開始回傳這個 driver 的時點，所以啟動行為逐一相同；理由與證據見第 2 節。
- **N2 的 `synth_name` 用字串而非 `lambda: self.name`**（`refactor4.md` §1.3 寫的是 lambda）：名字是類別常數，lambda 只是保留了「可能失敗」的形狀。改成字串之後，「取名字失敗」這種輸入不再存在，相關的兩個測試隨之刪除，不必保留一個不會發生的路徑。
- **N5 一併刪 Protocol 的 `notification_source`、`list_voices`**（`refactor4.md` 只要求 docstring 註明分工）：Protocol 的意義是「session 需要什麼」。session 刪掉 `list_voices` 後，這兩個成員都只有 manager 經由具體類別使用。留在 Protocol 裡，會讓 docstring 寫的分工與宣告不一致。
- **N7 的 `VOICE_CONFSPEC` 放 `configRepository.py`，不放 `runtime/settings.py`**：confspec 是 NVDA 設定格式的一部分，`configRepository.py` 的模組 docstring 就是「The existing NVDA config format」。`runtime/` 不依賴 NVDA 的格式。
- **N7 `APPLY_ORDER` 保留獨立的順序**：套用順序是引擎行為（eSpeak），不是名單本身的屬性；以守門測試確保集合相同。
- **N8 `parameter_consistency`／`roles` 可省略**：與 `ConfigVoiceSettingsRepository(parameters=None)` 一致，測試可以只給 provider。生產端一律由組裝根傳入同一個實例。
- **N11 保留 `= None` 初始化**（`refactor4.md` §1.1 說可以少掉）：理由見第 8 節。
- **`discovery` 用 `logging.getLogger(__name__)` 當 Null Object**（照 `refactor4.md` §8），不另寫一個什麼都不做的類別：在 NVDA 內它會寫進 nvda.log，比靜默更好，且與 `compat/engineAdapter.py` 一致。

## 排除

`refactor4.md` §11 列的十項都做，沒有排除項。以下是複核後**不**一併做的相鄰項目：

- `ConfigVoiceSettingsRepository.load` 內「主 synth 的值無效」的 `except Exception`（`noqa: BLE001`）：它處理 NVDA 驗證失敗（`AggregatedSection._cacheLeaf` 的 validator 例外），理由正確，不屬 N2。
- `getSynth()` 的其他使用者（事件橋接的 `get_synth=getSynth`、UI 的 synth 判斷）：不在本階段。
- `assembly.timed` 的 None 判斷：理由見第 10 節。
- ruff 的 39 項：階段 20。`_get_voice` 刪掉的 `list(...)[0]` 本身是一項 `RUF015`，所以總數會少一項，這是附帶結果。

## 成功條件

1. 完整測試全部通過（基準 1725）；`tests/test_hygiene_guards.py` 的 lint gate 為 0；`ruff check addon --extend-exclude addon/synthDrivers/WorldVoice/driver/sonic` 總數不超過 39；`ruff format --check addon --extend-exclude addon/synthDrivers/WorldVoice/driver/sonic` 通過。
2. N1：terminate 後 `speak`／`cancel`／`pause` 靜默的契約測試。
3. N2：`shared_section` 的特性測試（停用、存在、不存在、仿 `AggregatedSection`）在刪 except 前後都通過；主驅動給 repository 的名字是 `"WorldVoice"`；`mainLocalePolicy.py` 沒有 `except`；啟動閘門的三組特性測試（repository、組裝、主驅動）通過。
4. N4：`_get_voice` 兩條路的特性測試；`getVoiceInstanceForLanguage` 的守門。
5. N5：重新開啟的測試改用 `close`／`open` 後通過；`replace_adapter`、`EngineSession.list_voices` 的守門。
6. N7：`PARAMETER_NAMES`、`APPLY_ORDER`、`VOICE_CONFSPEC` 的守門；`rate`／`pitch`／`volume` 的 spec 字串逐字不變。
7. N8：`voiceManager.py` 不 import `config`／`languageHandler`；repository 與 manager 共用一個 `ParameterConsistency`。
8. N9：`speechSettingsDialog.py` 不含 `["speech"]["WorldVoice"]`。
9. N11：`_new_teardown` 不存在；既有的建構失敗與拆卸錯誤測試斷言不變。
10. `driver/<Engine>/driver/`、`driver/sonic`、六家 wrapper 無變動；`tests/test_plugin_voice_contract.py`、`tests/test_vocalizer_drift.py` 通過；`ref/Neural` 不使用任何被刪的名稱。

## 不在範圍內

- `refactor4.md` 階段 20（ruff 39 項、pre-commit lint hook、`worldvoice_synth()` helper、`SIM201`、`B010`、`B020` 等）。
- 使用者已否決的方案：`Voice` 拆為 `EngineDescriptor`（10b-2）、階段 15。
