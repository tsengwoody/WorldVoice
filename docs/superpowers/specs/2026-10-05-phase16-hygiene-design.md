# 階段 16：衛生（第二輪）

日期：2026-10-05。
基準：`master`（`10bede4`，階段 14 完成）。分支：`phase16-hygiene`。
狀態：依使用者要求自動執行（spec → plan → 實作 → Fable review），無需使用者決定。這是 `refactor.md` §11 路線圖的最後一個階段。

本文件對應 [`refactor.md`](../../../refactor.md) §10、§9 C12、C13、C7（`CancellableSynthDriver`），以及使用者決定不做階段 15 後併入的三個小項目（§4.3）。

## 需求與範圍

### 1. ruff 規則：依 NVDA 慣例處理

`refactor.md` §10 列出的規則，逐條比對 `ref/nvda` 的作法後處理如下。

- **`G201`（28 處，`log.error(..., exc_info=True)`）：不改成 `log.exception`，在 `pyproject.toml` 忽略。**
  - NVDA 的 `logHandler.Logger.exception`（`ref/nvda/source/logHandler.py:333`）不等於 `error(exc_info=True)`：它會把一組「預期中」的 Windows／COM 錯誤（`ERROR_INVALID_WINDOW_HANDLE`、RPC 斷線、`E_CALL_CANCELED` 等）降為 `debugWarning`。
  - WorldVoice 這 28 處記錄的是原生引擎、player、設定寫入與清理的失敗，要的就是 ERROR。
  - NVDA 自己因此保留了 `log.error(..., exc_info=True)`，並以 124 處 `# noqa: G201` 壓制（lint 升級 commit `2db695f44`）。
  - WorldVoice 改在 `[tool.ruff.lint] ignore` 加 `"G201"` 並附理由，一處說明取代 28 個行內註解。
  - `refactor.md` §10 的建議（改 `log.exception`）因此不採用。
- **`UP031`（15 處，`%` 格式化）：改為 f-string。**
  - 15 處都不是翻譯字串：都是 `repr`、例外訊息、語音 key 與 description、檔案格式行。所以沒有「翻譯字串必須保留 `%`」的顧慮。
  - 輸出逐字相同：`%r` → `!r`，`%d` → `:d` 或 `int` 的 f-string。
  - `views.py` 的 `log.error("…: %s" % e)` 改為 `log.error("…: %s", e)`，交給 logger 格式化，訊息相同。
- **`UP004`（4 處）、`UP008`（4 處）、`UP035`（5 處）：ruff 自動修正。**
  - 對象分別是 `class X(object)`、`super(Class, self)` 與 `typing.Callable` 等改由 `collections.abc` 匯入。
  - 修正後人工複核 diff。
- **`RUF012`（9 處，可變的類別屬性預設值）：**
  - 主驅動的 `supportedCommands`／`supportedNotifications`，以及 `generics/speechSymbols/models.py` 的 4 個查表 dict：照 NVDA 原始碼（`synthDrivers/espeak.py:44、54`、`characterProcessing.py:288`）加 `# noqa: RUF012`。它們是 NVDA 介面要求的類別屬性，或從 NVDA 複製來的查表，形狀不改。
  - `log.py` 的 `PipelineLog.FIELDNAMES`：改為 tuple。`csv.DictWriter` 接受任何序列。
  - 兩個設定面板的 `settings` 類別屬性：子類別或 `makeSettings` 會換成自己的值，從不就地修改。加 `# noqa: RUF012`。
- **其餘規則**（`SIM118`、`PERF102`、`TRY004` 等，各 1–5 處）不在 `refactor.md` §11 的範圍內，不處理。
- **守門**：`tests/test_hygiene_guards.py` 的 ruff 檢查從 `BLE001,I001` 擴充為 `BLE001,I001,UP004,UP008,UP031,UP035,RUF012,G201`。`G201` 由設定檔忽略，所以結果為 0。

### 2. WorldVoice-workspace 路徑單一來源（C12）

- 現況有兩種推導、4 份程式碼：
  - `engine/__init__.py:16-19` 由套件檔案位置往上四層；
  - `globalPlugins/WorldVoice/__init__.py:93` 與 `installTasks.py:60` 由 `globalVars.appArgs.configPath`。
  - 階段 14 已刪除被遮蔽的第四份。
- 新模組 `synthDrivers/WorldVoice/workspace.py`，只 import `os`、`globalVars`：

```python
WORKSPACE_DIRNAME = "WorldVoice-workspace"

def workspace_path() -> str:
	"""Where external engines and imported core files live: NVDA's config directory."""
	return os.path.join(globalVars.appArgs.configPath, WORKSPACE_DIRNAME)
```

- 三個使用端：
  - `engine/__init__.py`：`WVW_PATH = workspace_path()`；
  - GlobalPlugin `onFileImport`：`workspace_path()`；
  - `installTasks.py`：以 `importlib.util.spec_from_file_location` 從 `synthDrivers/WorldVoice/workspace.py` 載入。這與它載入 `generics/coreArchive.py` 的方式相同，因為安裝期間不能 import 尚未生效的 add-on 套件。
- **行為**：
  - 一般安裝（`<configPath>/addons/WorldVoice/...`）兩種推導結果相同。
  - 以 NVDA scratchpad 載入（`<configPath>/scratchpad/synthDrivers/WorldVoice`）時，舊的「往上四層」會指到 config 目錄的上一層，與 GlobalPlugin、installTasks 不一致。統一後三者都指向 config 目錄。這是修正。

### 3. 死碼

- `generics/speechSymbols/models.py:58` 的 `SpeechSymbols.localesToNames`：沒有讀者，而且每次建構都呼叫 `languageHandler.getAvailableLanguages()`。刪除。若 `languageHandler` 因此不再使用，一併刪 import。
- `generics/speechSymbols/views.py:18` 的模組常數 `base_path`：沒有讀者。刪除，未使用的 `globalVars` import 一併刪除。
- `CancellableSynthDriver = SynthDriver` 別名（VE 941、Cerence 948；C7）：addon、tests 與 `ref/Neural` 都沒有使用者。兩檔同步刪除，漂移測試的允許清單不變。

### 4. 原階段 15 併入的兩個註解與一致性項目

- **`_defaultVariant` 註解（C13）**：VE 與 Cerence 的 `Voice._defaultVariant` 註解「captured once per core」與事實不符。實際是每個 `Voice` 實例各存一份，core 換了才重抓。改為：「The engine's own default variant, cached on each voice and re-read when its core changes.」兩檔相同。
- **SAPI5 `_Sapi5Strategy.stop_player`**：
  - 只有它檢查 `driver is not None`，同類別其他方法與其他五家的 `stop_player` 都假設 driver 存在。strategy 由 driver 的 host 持有，host 不會比 driver 活得久。
  - 刪除 `driver is not None` 這一半，保留 `driver.player is not None`。player 在非 WASAPI 模式下確實可能是 `None`。

### 決定

- **以 `exec` 抽類別本體的測試不改為一般 import**（`refactor.md` §10「視 12 的結果」）。
  - 階段 12 收斂了組裝與清理，但沒有把 NVDA 的 import 移出模組層：`gui`、`speech`、`synthDriverHandler`、`wx` 等仍在 import 時就需要。改為一般 import 要為每個測試檔 stub 整組 NVDA 模組，換來的只是測試寫法不同，使用者看不到差異。
- **G201 不改為 `log.exception`**：理由見第 1 節。

### 成功條件

1. 完整測試全部通過；`ruff format --check addon` 通過。
2. `ruff check addon <範圍> --select BLE001,I001,UP004,UP008,UP031,UP035,RUF012,G201,F401,F821` 為 0，並由 hygiene 守門測試執行。
3. 守門測試（`tests/test_hygiene_guards.py` 擴充）：
   - `WorldVoice-workspace` 字串只出現在 `workspace.py`；
   - addon 不出現 `CancellableSynthDriver`；
   - `models.py` 不出現 `localesToNames`；
   - `views.py` 不出現 `base_path`；
   - SAPI5 的 `stop_player` 不出現 `driver is not None`。
4. `workspace_path()` 的單元測試：結果是 `configPath` 加 `WorldVoice-workspace`；installTasks 以檔案路徑載入同一個模組。
5. UP031 改寫前後輸出相同：
   - 既有測試已涵蓋 `voiceInfoToMetadata` description、`getVoiceKey`、`WVLangChangeCommand` repr、`readable_name`；
   - 另新增 `_speechcommand` 兩個 `repr`、`SpeechSymbol.__repr__`、`SpeechSymbols` 存檔行格式的測試，改寫前寫好並通過。
6. VE/Cerence 漂移測試通過，允許清單不變。
7. `driver/<Engine>/driver/`、`driver/sonic` 無變動。

### 不在範圍內

- `refactor.md` §11 範圍外的 ruff 規則。
- exec 測試改寫（見「決定」）。
- 先前各階段延後的 minor。最終報告會彙總列出。
