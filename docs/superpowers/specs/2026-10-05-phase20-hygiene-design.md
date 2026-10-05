# 階段 20：衛生（第三輪）

日期：2026-10-05。
基準：`master`（`7d9ad19`，階段 19 合併完成）。分支：`phase20-hygiene`。
狀態：依使用者要求自動執行（spec → plan → 實作），無需使用者決定。

本文件對應 `storage/refactor4.md`（第四輪審查，不入版控）§11 階段 20。細節在：

- §6.3（`worldvoice_synth()` helper、`B010`）、§7（`B008`、`TRY004`）、§8（`generics/speechSymbols`）；
- §9 的 N12（OneCore 的 `RUF100`／`RUF059`）；
- 附錄的 ruff 統計與 `--extend-exclude` 說明。

以下行號都以 `7d9ad19` 為準，每一項都已在原始碼上逐行複核，並逐條比對 `ref/nvda`（HEAD `1406f9f8a`）的作法。

## 現況

`ruff check addon --extend-exclude addon/synthDrivers/WorldVoice/driver/sonic --statistics`（ruff 0.16.9）→ **38 項**。審查時是 39 項，階段 19 的 N4 刪掉了 `_get_voice` 的 `list(...)[0]`，少一項 `RUF015`。

| 規則 | 數量 | 位置 |
| --- | --- | --- |
| `SIM118` | 5 | `rolePresenter.py:100、111`；`mainLocalePolicy.py:87`；`voiceManager.py:137、233` |
| `PERF102` | 4 | `speechSettingsDialog.py:726、795、799`；`voiceManager.py:243` |
| `TRY004` | 4 | `compat/commands.py:14`；`compat/engineAdapter.py:94`；`compat/indexCodec.py:20、23` |
| `SIM117` | 3 | `runtime/scheduler.py:432、445、559` |
| `SIM201` | 3 | `speechSettingsDialog.py:297、605、676` |
| `UP032` | 2 | `generics/speechSymbols/models.py:39、80` |
| `RUF015` | 2 | `generics/speechSymbols/views.py:276、277` |
| 各 1 | 15 | `SIM102`（`speechSettingsDialog.py:756`）、`C403`（同檔 716）、`B008`（`nvdaEventBridge.py:96`）、`B020`＋`PLR1704`（主驅動 355）、`C418`（主驅動 502）、`B010`（`VoiceSettingsDialogs.py:37`）、`UP045`（`_speechcommand.py:30`）、`UP007`（`pipeline/__init__.py:136`）、`S110`（`pipeline/__init__.py:57`）、`UP009`（`languageDetection/__init__.py:1`）、`UP024`（`views.py:324`）、`RUF023`（`models.py:26`）、`RUF100`（`driver/OneCore/__init__.py:304`）、`RUF059`（同檔 499） |

另外兩件事決定了守門與 hook 的範圍：

- `driver/sonic` 不在 pyproject 的 `exclude` 裡。它是從 NVDA 複製的 ctypes 綁定（檔頭版權 NV Access），WorldVoice 不修改，但單獨 `ruff check` 有 2 項（`I001`、`F401`）。所以每次統計都要加 `--extend-exclude`，而 pre-commit 的全域 `exclude` 也沒有排除它。
- `tests/test_hygiene_guards.py` 的 `RUFF_SCOPE` 用的是 `--exclude`。CLI 的 `--exclude` 會**取代** pyproject 的清單，所以 `script_data.py` 會被納入。目前它只檢查 7 條規則，所以沒有出錯；改成檢查全部規則後就會出錯。

## 需求與範圍

每一條都先比對 NVDA 的處理方式。NVDA 的 lint 升級（`2db695f44`）對無法改的地方一律用行內 `# noqa: RULE`，例如 `TRY004` 27 處、`S110` 40 處、`SIM118` 4 處、`B008` 1 處。WorldVoice 在階段 16 對 `G201` 改用 pyproject 整條忽略並寫下理由，本階段沿用這個作法。

### 1. ruff 的安全自動修正（7 項）

`UP009`、`UP045`、`UP007`、`UP024`、`B010`、`SIM117`×3，用 `ruff check --fix --select …` 套用，再逐行人工複核 diff：

- `UP009`：刪 `# -*- coding: utf-8 -*-`。Python 3 原本就預設 UTF-8。
- `UP045`／`UP007`：`Optional[str]` 改 `str | None`，`Union[str, re.Match]` 改 `str | re.Match`。add-on 最低 NVDA 2024.1，也就是 Python 3.11，執行期可以求值。`pipeline/__init__.py:27` 的 `Union[str, "SpeechCommand"]` 含字串前向參照，ruff 不報，維持原樣，所以 `Union` 的 import 保留。`_speechcommand.py` 不再用到 `Optional`，import 一併刪除。
- `UP024`：`except IOError` 改 `except OSError`。Python 3 裡 `IOError` 就是 `OSError` 的別名。
- `B010`：`setattr(storage, "punctuationpauseenabled", v)` 改成直接賦值，行為相同。§6.3 / N10 指出這是重複寫入（NVDA 的 checkbox handler 已經寫過），但刪除它要先確認兩個 handler 的綁定順序，不屬本階段。
- `SIM117`：`with self._delivery_lock:` 包著 `with self._state_cond:`，改成 `with self._delivery_lock, self._state_cond:`。兩層之間沒有其他敘述，取得與釋放的順序相同。NVDA 唯一一處 `noqa: SIM117` 是因為內層需要外層的值，這裡沒有這個情況。

### 2. `generics/speechSymbols`（`UP032`×2、`RUF015`×2、`RUF023`）

- `UP032`：兩個 `.format()` 改成 f-string，寫法與 NVDA `characterProcessing.py:223、267` 逐字相同。
  - `"{name}={val!r}".format(...)` 改為 `f"{attr}={getattr(self, attr)!r}"`。
  - `log.warning("Invalid line in file {file}: {line}".format(...))` 改為 `f"Invalid line in file {fileName}: {line}"`。
  - 改寫前先寫測試釘住警告文字。`__repr__` 的文字已由 `tests/test_format_outputs.py` 釘住。
- `RUF015`：`list(X.keys())[0]` 改 `next(iter(X))`。兩個查表都是非空的模組常數，結果相同。
- `RUF023`：`SpeechSymbol.__slots__` 依字母排序。
  - NVDA 也排序了，但它的 `__repr__` 逐一走訪 `__slots__`，所以 NVDA 的 repr 欄位順序跟著變了。
  - WorldVoice 的 repr 輸出要逐位元組不變（`tests/test_format_outputs.py` 的 `EXPECTED_REPR`）。所以另外加一個類別常數 `_REPR_FIELDS`，保留建構子的欄位順序，`__repr__` 改走訪它。
  - 守門：`set(_REPR_FIELDS) == set(__slots__)`，避免以後加了欄位卻漏掉 repr。

### 3. `SIM118`：`VoiceSettingsStore.keys()` 改名 `names()`

複核後發現，5 處都是誤報：被呼叫的不是 dict，而是 `runtime/settings.py:125` 的 `VoiceSettingsStore.keys()`。

- 這個方法在鎖內取一份 `tuple(self._states)` 快照。store 本身不可迭代，也不是 `Mapping`。
- 照 ruff 的建議寫成 `for key in store`，執行期會 `TypeError`，只有測試才抓得到。
- 這個陷阱的根源是名字：一個非 mapping 的類別，卻有一個和 `dict.keys()` 同名的方法。

處理：

- 改名為 `names()`。回傳的是語音名稱，也就是 `spec.name`。
- 呼叫端共 6 處：
  - 5 處 ruff 回報的位置；
  - `VoiceEditSession._keys()`（`runtime/settings.py:170`），不被回報，但呼叫同一個方法。
- 測試 2 處（`test_runtime_settings_store.py:26`、`test_runtime_session.py:189`）跟著改；兩個測試替身（`test_main_locale_policy.py:81`、`test_worldvoice_lifecycle.py:365、393` 的 `keys=lambda`）也跟著改名。
- `ref/Neural` 不使用這個方法，外掛契約不變。

這和 `refactor4.md` 的建議不同。審查把 `SIM118` 歸為「人工改」，但沒有注意到被呼叫的不是 dict。

### 4. `PERF102`、`C403`、`C418`、`SIM102`

- `PERF102`：
  - `speechSettingsDialog.py` 的三處 `for k, v in self.settings.items()` 只用到 `k`，改為 `for k in self.settings`。`settings` 是 `OrderedDict`，順序相同。不寫 `.keys()`，否則會換成觸發 `SIM118`。
  - `voiceManager.reload` 只用到 value，改為 `self._instanceCache.values()`。
- `C403`：`set([... for ...])` 改為 set comprehension。
- `C418`：`dict({...})` 改為 `{...}`。兩種寫法每次呼叫都回傳新的 dict。
- `SIM102`：`SpeechEngineSettingsPanel.onSave` 的兩層 `if` 合為一個 `and` 條件。短路順序不變，引擎沒有變更時仍然不會呼叫 `_write_settings()`；註解移到合併後的 `if` 上方。

### 5. `SIM201` 與 `worldvoice_synth()` helper（§6.3）

在 `pipeline/context.py` 新增：

```python
def worldvoice_synth():
	"""NVDA's current synth when it is WorldVoice, otherwise None."""
	synth = getSynth()
	return synth if getattr(synth, "name", None) == "WorldVoice" else None
```

- `current_context()` 改用它，`try`／`except` 與 `GENERIC_CONTEXT` 的退路不變。
- `speechSettingsDialog.py` 六處判斷改用它：297、313-314、581、605、676、833。
  - 313-314 的 `set_main_voice` 閉包在存檔當下才查詢，保留「對話框不是 modal，synth 可能已經換掉」的語意。
  - 閉包外已經有一個 `synth` 變數，所以這裡的區域變數取名 `current`。
- 唯一的語意差異是 `getSynth()` 回傳 `None` 時：舊寫法 `getSynth().name` 會丟 `AttributeError`，新寫法視為「不是 WorldVoice」。
  - NVDA 只在 `setSynth` 換 synth 的瞬間讓 `_curSynth` 為 `None`（`synthDriverHandler.py:530-537`），這時設定對話框的程式碼不會執行。
  - 所以使用者可見的行為不變。
- 以 `exec` 抽類別本體的 UI 測試（`test_role_panel.py`、`test_unicode_panel.py`）改為在環境中提供 `worldvoice_synth`。
- `test_role_panel.py` 開啟面板的測試另外呼叫 `set_main_voice`，確認它在執行當下才查詢 synth：synth 換掉之後只寫設定，不設定舊 synth 的 voice。
- `VoiceSettingsDialogs.py:91` 檢查的是 `self.driver` 而不是目前的 synth，不改。

### 6. 主驅動與事件橋接（`B020`／`PLR1704`、`B008`）

- `B020`／`PLR1704`：`patchedSpeakSpelling` 的 `for text, loc in self._languageDetector.process_for_spelling(text, locale)`，迴圈變數改名為 `part`。
  - 迭代器在迴圈開始前就已經以原本的 `text` 建好，迴圈之後也沒有再讀 `text`，所以行為相同。
  - 這個方法原本沒有測試，改名前先補上特性測試。
  - NVDA 有 17 處 `noqa: B020`；這裡改名就能消除，不需要 noqa。
- `B008`：`bind(..., completion: CompletionContract = CompletionContract())` 改為模組常數 `_LEGACY_CONTRACT = CompletionContract()`。
  - 預設值本來就只在 `def` 時建立一次，改成模組常數後也是同一個實例，語意逐一相同。
  - `CompletionContract` 是 frozen dataclass，共用是安全的。
  - 命名沿用 `compat/completionPolicies.py` 的 `_DRAIN_CONTRACT`。

### 7. OneCore wrapper（N12：`RUF100`、`RUF059`）

`driver/OneCore/__init__.py` 是外層 wrapper，可以改。VE／Cerence 的 lint 項目不涉及，漂移測試允許清單不變（兩檔只有第 12 節的尾逗號）。

- `RUF100`（304）：
  - `37004cb` 在這個 handler 的 `else` 分支加了 `log.error(..., exc_info=True)`。ruff 因此不再把它視為 blind except，`noqa: BLE001` 變成無作用。
  - 刪除整段 `# noqa: BLE001 - …` 註解。兩個分支內已經各有說明錯誤去向的註解。
- `RUF059`（499）：`error, dropped, legacy = failure` 的 `error` 沒有使用，改名為 `_error`，保留 tuple 的形狀說明。

### 8. 以 pyproject 忽略並寫下理由（`TRY004`、`S110`）

- **`TRY004`**：只在 `compat/commands.py`、`compat/engineAdapter.py`、`compat/indexCodec.py` 三個檔案忽略（`per-file-ignores`）。
  - 這 4 處 `ValueError` 是 runtime 邊界的既定契約，由測試釘住：`test_legacy_speech_commands.py:72`、`test_index_codec.py:56、134`、`test_runtime_legacy_adapter.py:540`、`test_worldvoice_lifecycle.py:464`。
  - 其中三處拒絕的是「型別正確、但不允許從外部傳入」的內部標記，本來就比較接近值錯誤。
  - 改成 `TypeError` 是 API 變更。NVDA 對同樣的情況是保留 `raise` 並加行內 noqa。
  - 只對三個檔案忽略，其他檔案以後若寫出 `TRY004`，仍然會被報出來。
- **`S110`**：在 `[tool.ruff.lint] ignore` 整條忽略。
  - ruff 的 `S110` 預設只報 `except:`、`except Exception:`、`except BaseException:` 後面只有 `pass` 的情況（`check-typed-exception = false`）。實測結果：這些情況一定同時是 `BLE001`（`Exception`／`BaseException`）或 `E722`（bare `except`）。
  - 所以 `S110` 只是重複回報，而那兩條規則本身就要求各自的 noqa。WorldVoice 的 `noqa: BLE001` 還必須寫出錯誤去向（`tests/test_hygiene_guards.py`）。
  - 唯一一處是 `with_order_log` 的 `except Exception: pass`，使用者在階段 8 決定保留。它已經有 `# noqa: BLE001 - debug counter only; never affects speech`。
  - 如果改用 NVDA 的寫法 `# noqa: BLE001, S110`，會與守門測試的 `noqa: BLE001 - 理由` 格式衝突。
- 兩條忽略各附一段註解，格式與 `G201` 相同，並由守門測試檢查理由仍在。

### 9. `driver/sonic` 排除

- `pyproject.toml` 的 `exclude` 加入 `./addon/synthDrivers/WorldVoice/driver/sonic`，註解說明它是 NVDA 的 sonic 綁定複本，WorldVoice 不修改。
- `.pre-commit-config.yaml` 的全域 `exclude` 也加入 `driver/sonic/`。
- 結果：
  - `ruff check addon`、`ruff format --check addon` 不再需要 `--extend-exclude`；
  - 新的 lint hook 不會掃到 sonic；
  - 與內層驅動、`script_data.py` 的排除方式一致。
- sonic 目前已經符合格式，所以從 format hook 移除不會留下任何未格式化的檔案。

### 10. pre-commit lint hook

照 NVDA `.pre-commit-config.yaml` 的 ruff 段落，在 `ruff-format` 之前加入：

```yaml
      - id: ruff
        name: lint with ruff
        args: [ --fix ]
        files: ^addon/
```

- 刪除 40-42 行「等既有 lint 清完再加」的註解。
- `files: ^addon/` 與 format hook 相同：測試維持自己的風格。
- ruff-pre-commit 的 hook 帶 `--force-exclude`，所以 pyproject 的 `exclude` 對 pre-commit 傳入的檔名同樣有效。
- `I001` 已經列在 `extend-unsafe-fixes`，`--fix` 不會自動重排 import（`generics` 的 import 順序有守門測試）。

### 11. 守門測試

- `tests/test_hygiene_guards.py`：
  - `test_ruff_reports_none_of_the_gated_rules` 改為 `test_ruff_reports_nothing`：執行 `ruff check addon`，不帶 `--select`、不帶 CLI exclude，以 pyproject 設定檢查全部規則，結果必須為 0。
  - 刪除 `GATED_RULES`、`RUFF_SCOPE`；更新 `G201` 測試裡「explicit --select would override」的註解。
- 新增 `test_lint_ignores_keep_their_documented_reasons`：`TRY004`、`S110` 的忽略與理由仍在 pyproject，且 pyproject 與 `.pre-commit-config.yaml` 兩個 exclude 都排除 sonic。
- 新增 `test_pre_commit_runs_the_ruff_lint_hook`：`.pre-commit-config.yaml` 有 `id: ruff` 加 `--fix`。
- 突變驗證：任意加入一項 ruff finding，`test_ruff_reports_nothing` 必須失敗；還原後通過。

### 12. 實作時補上：pre-commit 的尾逗號（審查後補上）

第一次執行 `pre-commit run --all-files` 時，`add-trailing-comma` 改了 7 個檔案：

- 主驅動、`speechSettingsDialog.py`、`languageDetection/settings.py`、`pipeline/__init__.py`、OneCore、VE、Cerence。
- 都是先前階段只跑了 `ruff format`、沒跑 `add-trailing-comma` 留下的：多行呼叫的最後一個引數少了逗號。補上後 ruff format 會把它們展開成每行一個引數。
- 只動格式，不改行為。VE 與 Cerence 的 `threading.Thread(...)` 改法相同；Cerence 多一處，是因為它的錯誤訊息較長，原本就已經拆成多行（VE 那一行沒有超過行寬）。漂移測試通過，允許清單不變。
- 獨立成一個 commit，使 `pre-commit run --all-files` 全部通過且不修改任何檔案。

## 決定

- **`SIM118` 改名 `names()`，不加 noqa、不讓 store 可迭代**（`refactor4.md` 寫「人工改」）：5 處都是誤報，理由見第 3 節。
  - 加 noqa 會留下陷阱：一個看起來像 dict 的 `keys()`。
  - 加 `__iter__` 會讓「在鎖內取快照」這件事從呼叫端消失。
  - 改名只動 8 行，名字也說出了回傳的是什麼。
- **`RUF023` 排序，但 repr 輸出不變**（NVDA 讓 repr 順序跟著改）：本專案規定改寫時輸出逐位元組不變，見第 2 節。
- **`TRY004` 用 per-file，`S110` 整條忽略**（`refactor4.md` 寫「per-file／per-rule ignore」）：
  - `TRY004` 是真正的規則，只對三個邊界檔案豁免；
  - `S110` 在本專案設定下只會重複 `BLE001`／`E722` 的回報，整條忽略不會漏掉任何東西。
- **sonic 加入 pyproject 與 pre-commit 的 exclude**（`refactor4.md` 沒有提到）：要讓 hook 不掃到 sonic，又不必每次都加 CLI 參數，這是唯一一致的作法。
- **`worldvoice_synth()` 一併做**（`refactor4.md` 列為順手項）：`SIM201` 的三處正好都是這個判斷。七處判斷收成一處，UI 不再拼寫 synth 名稱字串。
- **`B010` 只改成直接賦值，不刪除**：刪除屬於 N10，需要先確認 wx handler 的順序。
- **補上 `add-trailing-comma` 的 7 處尾逗號**（`refactor4.md` 沒有提到）：不補，`pre-commit run --all-files` 就不會通過，新的 hook 也會在下一次碰到這些檔案時自動改動；見第 12 節。
- **lint hook 用 NVDA 的 `id: ruff`**（ruff-pre-commit 新的 id 是 `ruff-check`，`ruff` 是相容別名）：與 NVDA 逐字相同，日後比對時比較容易。

## 排除

`refactor4.md` §11 階段 20 列的項目全部都做。以下是複核後**不**一併做的相鄰項目：

- N10（`B010` 那一行是重複寫入）：見上。
- `driver/sonic` 的 2 項：不修改供應商程式碼，改以排除處理。
- `generics/speechSymbols/models.py` 的 `codecs.open` DeprecationWarning：`refactor-cleanup.md` #72 決定等 NVDA 升級。
- `with_order_log` 的 `except: pass`：使用者保留，只以 `S110` 忽略處理。
- `exec` 測試改寫：階段 16 決定不改。

## 成功條件

1. 完整測試全部通過（基準 1745；完成時 1753）。
2. `ruff check addon` 為 0，不需要任何 CLI exclude；`ruff format --check addon` 通過。
3. `test_ruff_reports_nothing` 在 0 項時通過，在加入任意一項時失敗（突變驗證）。
4. `pre-commit run --all-files` 通過（環境允許時執行，否則說明原因）。
5. 改寫前先寫好並通過的特性測試：
   - `SpeechSymbols.load` 的警告文字；
   - `patchedSpeakSpelling` 的兩條路；
   - `_get_availableNummods` 的內容與順序；
   - `worldvoice_synth()` 的三種情況。
   既有的 `EXPECTED_REPR` 不變。
6. `driver/<Engine>/driver/`、`driver/sonic` 無變動；VE／Cerence 只有第 12 節的格式變動；`tests/test_vocalizer_drift.py`、`tests/test_plugin_voice_contract.py` 通過。
7. 翻譯字串（`_()`、`pgettext`）內容沒有任何改變。

## 不在範圍內

- 使用者已否決或延後的方案（`refactor4.md` §10）。
- `pre-commit install`（安裝到 `.git/hooks`）：由使用者自行決定是否啟用；本階段只提供設定。啟用後，lint hook 因為帶 `--fix`，會直接改寫可安全修正的檔案，該次 commit 隨之失敗，需重新 add 後再 commit（與 NVDA 相同）；`extend-unsafe-fixes = ["I001"]` 讓 import 不會被自動重排。
- 已知限制：pyproject 沒有 `select`，gate 檢查的規則是 ruff 0.16 的預設規則減去 `ignore`（0.16.3 與 0.16.9 已確認相同）。較新的 ruff 若擴大預設規則，`test_ruff_reports_nothing` 可能失敗，而釘住版本的 pre-commit hook 仍通過。是否加 `required-version` 由使用者決定，本階段不加。
