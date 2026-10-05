# 階段 18：語言偵測設定 Repository 與隱性契約文件

日期：2026-10-05。
基準：`master`（`54e5453`，階段 17 收尾完成）。分支：`phase18-detection-settings`。
狀態：依使用者要求自動執行（spec → plan → 實作），無需使用者決定。

本文件對應 `storage/refactor4.md`（第四輪審查，不入版控）§11 階段 18，細節在 §1.2（語言偵測設定沒有 Repository）、§6.1（Unicode 面板沒有中介物件）、§5.2 與 §9 N6（`WVLangChangeCommand` 的隱性契約）。

## 現況

`config.conf["WorldVoice"]["autoLanguageSwitching"]` 有 8 個鍵。3 個 `KeepMainLocale*` 由 `mainLocalePolicy.py` 獨佔（`tests/test_role_guards.py` 守門），不在本階段範圍。另外 5 個是語言偵測鍵，存取點分散在三處：

| 鍵 | 讀 | 寫 |
| --- | --- | --- |
| `ignoreNumbersInLanguageDetection` | `languageDetection/__init__.py:139`；`speechSettingsDialog.py:628` | `speechSettingsDialog.py:682` |
| `latinCharactersLanguage`／`CJKCharactersLanguage`／`arabicCharactersLanguage` | `languageDetection/__init__.py:128`（經 `SCRIPT_CONFIG_KEYS`）；`speechSettingsDialog.py:668` | `speechSettingsDialog.py:687` |
| `DetectLanguageTiming` | 主驅動 `__init__.py:461`；`speechSettingsDialog.py:647、691` | `speechSettingsDialog.py:694`，之後手動 `getSynth().refresh_language_detection()`（695） |

- confspec 在主驅動 `__init__.py:62-67`。
- `LanguageDetector` 以 `conf_provider` 取得整個 NVDA config，每次需要時讀 `["WorldVoice"]["autoLanguageSwitching"]`（`_switching()`，118-119）。
- 同一專案的其他設定區段都已收口：`roles.ConfigRoleRepository`、`pipeline.settings.PipelineSettingsService`、`globalPlugins.pipelineLog.PipelineLogService`。語言偵測是唯一還沒有的。

`WVLangChangeCommand`（`_speechcommand.py:6-17`）的 docstring 只寫「A command to switch the language within speech」。它為何繼承 `SynthParamCommand` 而不是 `LangChangeCommand`、`isDefault` 為何必要、`installTasks.onInstall` 為何關掉 NVDA 的 `autoLanguageSwitching`（`installTasks.py:62-65`），程式碼裡都沒有寫。

## 需求與範圍

### 1. `languageDetection/settings.py`：值物件與 Service

新模組。`DetectionSettingsService` 本身就是 Repository：直接讀寫 config 區段，並以 Observer 通知訂閱者，不另設 Repository 類別。這點與 `pipeline/settings.py` 分成 `ConfigPipelineRepository` 與 `PipelineSettingsService` 兩層不同：偵測設定只有五個鍵、一個呼叫端，沒有替換儲存層的需求。對外介面（`get`／`update`／`subscribe`／`unsubscribe`）與 `PipelineSettingsService` 相同：

```python
DETECTION_CONFSPEC = {
	"ignoreNumbersInLanguageDetection": "boolean(default=false)",
	"latinCharactersLanguage": "string(default=en)",
	"CJKCharactersLanguage": "string(default=ja)",
	"arabicCharactersLanguage": "string(default=ar)",
	"DetectLanguageTiming": "string(default=after)",
}
SCRIPT_CONFIG_KEYS = {"Latin": "latinCharactersLanguage", "Han": "CJKCharactersLanguage", "Arabic": "arabicCharactersLanguage"}

@dataclass(frozen=True)
class DetectionSettings:
	ignore_numbers: bool
	script_language: Mapping[str, str]   # 唯讀，鍵同 SCRIPT_CONFIG_KEYS
	timing: str                          # "before" | "after"（存的是什麼就是什麼，不驗證）

class DetectionSettingsService:
	"""autoLanguageSwitching 五個偵測鍵的唯一讀寫者。"""
	def __init__(self, conf_provider: Callable[[], Any]): ...
	def get(self) -> DetectionSettings: ...
	def update(self, *, ignore_numbers=None, script_language=None, timing=None) -> DetectionSettings: ...
	def subscribe(self, listener: Callable[[DetectionSettings, frozenset[str]], None]) -> None: ...
	def unsubscribe(self, listener) -> None: ...

detection_settings = DetectionSettingsService(lambda: config.conf)
```

- `get()` 每次由 config 建一個新值物件，所以設定檔（profile）切換後讀到的就是新值；與 `PipelineSettingsService.get()` 相同，不快取。
- `update()`：
  - 參數為 `None` 表示不改；`script_language` 可以只給部分語系（面板只存啟用中的選單），未知的 script 名稱在寫入任何鍵之前就 `KeyError`。
  - 只寫值有變的鍵。NVDA 的 `AggregatedSection.__setitem__` 本來就會略過與現值相同的寫入（`ref/nvda/source/config/__init__.py:1352-1366`，以 `str` 比較），所以「只寫有變的」與舊面板「全部照寫」對設定檔的結果相同。
  - 沒有任何改變就不通知，回傳目前的值。
  - 有改變時以 `(新設定, 改變的欄位名稱集合)` 通知每個 listener；listener 失敗只記 log（`log.error(..., exc_info=True)`），不影響其他 listener 與寫入結果。與 `PipelineSettingsService.update` 相同。
- `DETECTION_CONFSPEC` 由主驅動併入 `config.conf.spec["WorldVoice"]["autoLanguageSwitching"]`，與 `PIPELINE_CONFSPEC` 的作法相同。鍵名與預設值逐字不變。
- `SCRIPT_CONFIG_KEYS` 從 `languageDetection/__init__.py` 搬來；`__init__.py` 不再有它。

**模組放置**：`settings.py` 與 `pipeline/settings.py` 一樣 import `config` 並建立模組層單例。`languageDetection/__init__.py` 不 import `settings.py`，仍然不碰 `config`／`synthDriverHandler`（`tests/test_pipeline_structure.py:21` 守門不變）；偵測器只拿到注入的 service。

### 2. `LanguageDetector` 改走 service

- 建構子：`LanguageDetector(availableLanguages, speechSymbols=None, *, settings, language)`；`conf_provider` 與 `_switching()` 刪除。`settings` 只需要有 `get()`。
- 每次 `add_detected_language_commands`、`process_for_spelling` 呼叫開始時讀一次 `settings.get()`，整段序列用同一份快照。
  - 舊實作是每個需要設定的字元各讀一次 config。快照的差別只在「同一段序列處理到一半時設定被改」這個不會發生的情況（面板存檔與 speak 都在主執行緒）。
  - 換來的是每段序列只建一次值物件，不會因為改走 service 而在每個字元多讀四個鍵。
- `find_language_for_script(script, current_language, settings=None)`：內部呼叫傳入快照；直接呼叫（測試）時自己 `get()`。邏輯不變。
- `_language_for_character` 讀快照的 `ignore_numbers`。

### 3. 主驅動

- `config.conf.spec["WorldVoice"]["autoLanguageSwitching"]` 改為 `{**DETECTION_CONFSPEC, <三個 KeepMainLocale* 鍵>}`。
- `LanguageDetector(…, settings=detection_settings, language=lambda: self.language)`。
- `_detectLanguageTiming()` → `detection_settings.get().timing`。
- Observer：偵測器建好、`add_detected_language_commands` 存在之後，`detection_settings.subscribe(self._on_detection_settings)`，並登記 teardown `"detection settings unsubscribe"`。
  - `_TEARDOWN_ORDER` 新增這個名稱，排在 `"language detection unregister"` 之前：先停止接收通知，再把 filter 取消註冊，拆卸期間不會有通知把 filter 註冊回去。
  - `_on_detection_settings(settings, changed)`：只有 `"timing" in changed` 時呼叫 `refresh_language_detection()`。
- `refresh_language_detection()` 保留原名與行為（`_set_uwv` 仍呼叫它），docstring 改為說明它由 uwv 與時機設定的通知觸發。

### 4. `UnicodeDetectionSettingsPanel`

- `makeSettings` 讀一次 `detection_settings.get()`：勾選框用 `ignore_numbers`，三個 script 選單用 `script_language[script]`，時機選單用 `timing`。
- `onSave` 一次 `detection_settings.update(ignore_numbers=…, script_language={啟用中的 script: 選的語系}, timing=…)`。
- 面板不再 import／使用 `languageDetection.SCRIPT_CONFIG_KEYS`，不再直接讀寫 config，也不再呼叫 `getSynth().refresh_language_detection()`。
- 不變：`getSynth().name == "WorldVoice"` 的判斷、`voice_manager.languages`／`localesToNamesMap` 列候選語言、`languageDetection.SCRIPT_LANGUAGES` 決定候選、選單順序與 label。

使用者可見行為逐項不變：

- 控制項、label、選項與預設選取相同；
- 存檔寫入的值相同；
- 停用的 script 選單不寫；
- 時機改變時 filter 重新註冊／取消。舊實作由面板直接呼叫 synth；新實作由 service 通知 synth。時機未改變時都不呼叫（`refresh_language_detection` 會呼叫 `order_move_to_start_register`，重排 NVDA 的 filter 順序，所以不能每次存檔都呼叫）。

有一處刻意的差異：舊實作中 `getSynth().refresh_language_detection()` 拋出的例外會從面板的 `onSave` 傳出去；現在由 `DetectionSettingsService` 以 `log.error(..., exc_info=True)` 記錄，存檔照常完成（設定已寫入）。這與 `PipelineSettingsService` 處理 listener 失敗的方式相同。

### 5. 隱性契約文件（§5.2、N6）

- `WVLangChangeCommand` docstring 寫下三點並引用 `ref/nvda`（HEAD `1406f9f8a`）行號：
  1. 它必須直接繼承 `SynthParamCommand`、不能是 `LangChangeCommand` 子類。NVDA 的 `speech.speak()` 在 `filter_speechSequence` 之後，只要 `shouldMakeLangChangeCommand()`（`autoLanguageSwitching or reportLanguage`）為假，就丟掉所有 `LangChangeCommand`（`speech/speech.py:1178-1180`、`speech/languageHandling.py:60-62`）。`SpeechManager._processSpeechSequence` 在 `shouldSwitchVoice()` 為假時又丟一次（`speech/manager.py:366-369`）。「before」時機的偵測是 `filter_speechSequence` handler，插入的命令會經過這兩處檢查。
  2. `installTasks` 首次安裝就關掉 NVDA 的 `autoLanguageSwitching`，所以在 WorldVoice 的預設環境下，第 1 點的剝除一定會發生。
  3. `isDefault` 是 `ParamChangeTracker.update` 的契約（`speech/manager.py:95-105`）：預設值會把該型別移出追蹤表。否則 manager 在同一段序列拆出的每個後續 utterance 開頭都會重放上一個語言命令。
- docstring 同時說明 pipeline 為何同時處理兩種型別：`reportLanguage` 或 NVDA 自己的 `autoLanguageSwitching` 開著時，NVDA 仍會產生自己的 `LangChangeCommand`。
- `installTasks.onInstall` 的設定處加註解：WorldVoice 自己偵測語言並插入 `WVLangChangeCommand`；NVDA 的自動語言切換開著時，NVDA 會再依文件標記插入一套 `LangChangeCommand`。因此首次安裝關掉它，使用者之後仍可自行打開。
- 只改 docstring 與註解，程式行為不變。

## 決定

- **Observer 而非顯式呼叫**：`refactor4.md` §11 把選擇留給實作者。採用 Observer：
  - 與 `pipeline_settings.subscribe(self._apply_pipeline_settings)` 同形；
  - 面板完全不需要知道 synth 有什麼方法；
  - 拆卸由 `Teardown` 負責。
- **listener 多收一個「改變的欄位」參數**（與 `refactor4.md` §1.2 草圖、`PipelineSettingsService` 不同）：
  - synth 只在時機改變時才需要重新註冊 filter。如果只傳新設定，synth 要嘛每次存檔都 refresh（會重排 filter 順序，屬行為改變），要嘛自己記住上次的時機（多一份要同步的狀態）。
  - 傳 `frozenset` 的欄位名稱，synth 不需要保存任何狀態。
- **confspec 搬進 `settings.py`**（`refactor4.md` 未提）：守門測試要求五個鍵名只出現在一處。主驅動的 confspec 也是這五個鍵的一份拷貝，比照 `PIPELINE_CONFSPEC` 由 settings 模組提供。
- **偵測器每段序列讀一次快照**（`refactor4.md` 草圖未提）：理由見第 2 節。
- **`update()` 用具名參數而非 `**changes`**：只有三個欄位，`script_language` 是部分合併、語意與其他欄位不同。具名參數比字串鍵表清楚，打錯名稱時 Python 本身就會拒絕。
- **`refresh_language_detection` 不改名**：它仍是 uwv setter 與通知共用的進入點；改成私有名稱只會讓 `tests/test_driver_ui_hooks.py` 跟著改，沒有其他收益。

## 成功條件

1. 完整測試全部通過（基準 1698）；`tests/test_hygiene_guards.py` 的 lint gate 為 0；`ruff check`（同 `refactor4.md` 附錄的範圍）總數不超過 39；`ruff format --check addon --extend-exclude addon/synthDrivers/WorldVoice/driver/sonic` 通過。
2. Service 單元測試（`tests/test_detection_settings.py`）涵蓋：
   - `get()` 的值與 config 相同，`script_language` 唯讀；
   - `update()` 只寫有變的鍵，部分 `script_language` 只寫給的語系；
   - 未知 script 在寫入前就 `KeyError`；
   - 沒改變不通知；
   - 通知帶正確的 changed 集合；
   - 失敗的 listener 被記錄，其他 listener 照常收到；
   - `subscribe` 去重、`unsubscribe` 未登記者不報錯；
   - `DETECTION_CONFSPEC` 的鍵與預設值和舊 confspec 逐字相同。
3. 既有偵測器測試（`tests/test_language_detector.py`）改為注入 service 後，原有的斷言不變；新增一個測試：同一段序列只呼叫一次 `get()`。
4. 面板測試（`tests/test_unicode_panel.py`）原有斷言不變（選項、選取、存檔值、停用不存），改為以 service 驗證；時機測試改為驗證 service 通知帶 `"timing"`，以及面板不碰 synth。
5. 主驅動測試：
   - `_on_detection_settings` 只在 changed 含 `"timing"` 時 refresh；
   - `_detectLanguageTiming` 讀 service；
   - 建構時訂閱，拆卸時取消訂閱，順序在 filter 取消註冊之前（`tests/test_worldvoice_lifecycle.py` 擴充：失敗的建構也成對）。
6. 守門測試：
   - 五個偵測鍵名只出現在 `languageDetection/settings.py`；
   - `speechSettingsDialog.py` 不含 `refresh_language_detection`；
   - `languageDetection/__init__.py` 不 import `config`（既有）。
7. 契約測試：在仿 NVDA 繼承關係的 stub 下（`LangChangeCommand` 繼承 `SynthParamCommand`），
   - `WVLangChangeCommand` 是 `SynthParamCommand` 子類、不是 `LangChangeCommand` 子類；
   - `isDefault` 在 `None`／`""` 為真、在 `"zh"` 為假；
   - docstring 引用 `speech/speech.py`、`speech/manager.py`；
   - `installTasks.py` 在設定 `autoLanguageSwitching` 處有註解。
8. `driver/<Engine>/driver/`、`driver/sonic`、VE/Cerence wrapper 無變動；`tests/test_plugin_voice_contract.py` 通過。

## 不在範圍內

- `refactor4.md` 階段 19、20 的項目（`cancel`／`pause` 守門、`synth_name` 提供者、參數名單、ruff 39 項等）。
- UI 的 `getSynth().name == "WorldVoice"` 判斷與 `SIM201`（階段 20）。
- `KeepMainLocale*` 三個鍵（已由 `mainLocalePolicy.py` 收口）。
