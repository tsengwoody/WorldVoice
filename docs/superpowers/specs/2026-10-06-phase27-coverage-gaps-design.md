# 階段 27：補上主路徑與覆蓋缺口

日期：2026-10-06。
基準：`master`（`0f536bc`，階段 24 合併完成）。分支：`phase27-coverage-gaps`。
狀態：使用者要求依序完成階段 23～28，自動流程執行；審查改用 Opus 5.5（Fable 額度用完，使用者指示）。

對應 repo 根目錄 `refactor-test.md`（不入版控）的階段 27。原則：只新增測試；若需要可測試性的注入點，維持產品預設行為不變，且必須在 spec 實作備註說明。Hypothesis 不在本階段使用（使用者決定留給階段 29 討論）。

## 現況（`--cov=addon --cov-branch`，排除 vendored driver 與 `script_data.py`）

整體 88%（7661 行／799 未覆蓋；2190 分支／242 部分）。53 個檔案被量到；另有 8 個檔案從未被任何測試 import，不在數字內：

| 檔案 | 行數 | 說明 |
| --- | --- | --- |
| `text/chunker.py` | 64 | VE／Cerence 實際使用（`split_speech_text_pieces`），drain harness 以 stub 取代 |
| `text/arabic.py` | 44 | VE／Cerence 實際使用（`break_repeated_runs`），同上 |
| `engine/__init__.py` | 56 | 主驅動 `ready_engine_classes` 的來源 |
| `sayAll.py` | 47 | global plugin 的 `patch`／`unpatch` |
| `globalPlugins/WorldVoice/utils.py` | 53 | `guard_errors` 等，設定對話框使用 |
| `generics/speechSymbols/views.py` | 353 | 符號編輯 UI（使用者曾表示此功能可能移除） |
| `generics/speechSymbols/__init__.py`、`text/__init__.py` | 0–1 | 空 |

90% 以下的已量測檔案：`VoiceSettingsDialogs.py` 19%、`globalPlugins/WorldVoice/__init__.py` 41%、`speechSettingsDialog.py` 42%、`installTasks.py` 59%、`engine/discovery.py` 64%、`languageDetection/scripts.py` 71%、`driver/__init__.py` 82%、`speechSymbols/models.py` 82%、`log.py` 83%、`pipeline/__init__.py` 85%、`coreArchive.py` 86%、`SAPI5` 87%、`Espeak` 88%、主驅動 `__init__.py` 89%。

主驅動 `SynthDriver.speak()` 本體與 `pipeline.inject_langchange_reorder` 沒有任何測試走過。

## 範圍

分兩組，彼此不碰同一個檔案，可平行進行：

### A 組：核心路徑與純邏輯

1. `SynthDriver.speak()` 端到端：以既有的主驅動載入方式（`worldvoice_harness.load_synth_class` 一類）與真的 pipeline，餵含 `LangChangeCommand`、`IndexCommand`、`BreakCommand` 的序列，涵蓋偵測時機 `before`／`after`、`inject_langchange_reorder`、`deduplicate`、`lang_cmd_to_voice`、`queue_speech_sequence` 串接，斷言送進排程的語音片段與 index 順序。
2. `pipeline/__init__.py` 的其他缺口：自訂 BreakCommand 子類、stage 的空輸入早退。
3. `engine/discovery.py::discover_engine_specs` 正常路徑（內建＋外部引擎目錄、enabled 旗標、manifest 欄位驗證、停用分支）；`engine/__init__.py`（`ready_engine_classes`、旗標轉換）。
4. `text/chunker.py`、`text/arabic.py` 單元測試（邊界：空字串、只有分隔符號、超長無分隔、混合語系、組合字元、surrogate pair）。
5. `sayAll.py` 的 patch／unpatch 行為。
6. 錯誤路徑：`log.py` 寫檔失敗、`coreArchive` 非 `PermissionError` 的例外、`nvdaEventBridge.bind` 重複綁定／契約不符與 `unbind` 未知來源、`installTasks.onUninstall` 與有 core 檔時的 `onInstall`、`languageDetection/scripts.py` 的 fallback、`driver/__init__.py` 基底 `Voice` 的未覆蓋分支。

### B 組：UI

1. 設定面板 `makeSettings`：`SpeechPipelinePanel`、`SpeechEngineSettingsPanel`、`LogSettingsPanel`、`SpeechRoleSettingsPanel`（沿用 `test_unicode_panel.py` 的 `Control`／`Helper` 假件模式）。
2. `VoiceSettingsDialogs.py`：`createDriverSettings`、`makeSettings`、標點停頓的 slider 可見性。
3. `globalPlugins/WorldVoice/__init__.py`：選單建立、`script_*`／`onFile*` 處理器的正常路徑；`utils.py` 的 `guard_errors`。
4. `speechSymbols/views.py`：不在範圍（使用者曾表示該功能可能移除）；在實作備註列為已知未測。

## 撰寫原則

- 每個新測試要能說出它守的是哪條執行路徑或哪個行為；斷言檢查行為（輸出、事件、呼叫），不只檢查「有執行到」。
- 使用階段 24 的 `tests/addon_loader.py`、harness 模組與 `nvda_stubs.worldvoice_conf()`；等待用 `tests/waiting.py`；不新增測試模組互相 import。
- 不為了覆蓋率去測防禦性的不可能分支；若某段程式在測試環境無法合理觸發，列在實作備註。

## 驗證

- 全套通過、逐檔單獨執行通過、`ruff check/format addon tests` 乾淨。
- 覆蓋率（同上設定）≥ 92%，並列出前後逐檔數字；8 個未 import 檔案中，除 `speechSymbols/views.py` 外都要被量到。
