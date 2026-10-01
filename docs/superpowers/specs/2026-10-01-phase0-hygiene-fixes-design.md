# 階段 0：格式化對齊 NVDA 與低風險正確性修正

日期：2026-10-01。
基準：`master`（`42ea20b`）。
狀態：對話中的範圍與設計已獲使用者確認；本文件待使用者審閱。

本文件是 [`refactor.md`](../../../refactor.md) §9「建議施工順序」的階段 0。階段 1–5 各自另寫 spec 與 plan。

## 需求與範圍

使用者要在動到 runtime 與引擎 wrapper 結構之前，先完成兩件低風險的事：

1. 讓 `addon/` 的格式與工具設定對齊 NVDA 主程式（`ref/nvda`，`1406f9f8a`）的規範，之後每次提交都自動維持。
2. 修正 `refactor.md` §7 中已確認、改動局部的問題：C1、C4、C10、C11。

**不在範圍內**：

- C5（符號對話框遇 `None` 崩潰）：該功能可能移除，暫不處理。
- 格式化以外的 ruff lint 項目（`BLE001` 以外的 `I001`、`F401`、`F821` 等）。
- 命名風格（NVDA 規範 mixedCase，`refactor.md` §8 建議 snake_case）：留待階段 2 決定。
- `tests/` 的縮排：測試檔維持 4 空格，不納入格式化與 hook。
- 內層驅動 `driver/<Engine>/driver/` 與 `driver/Neural/`：不修改、不提交。

成功條件：

1. `ruff format --check` 對 `addon/`（扣除排除項目）通過。
2. `.pre-commit-config.yaml` 含 NVDA 同版本的格式化 hook（不含 lint hook，見設計第 1 節），限定 `addon/`。
3. 純格式 commit 只含工具產生的變更，並登記在 `.git-blame-ignore-revs`。
4. `addon/` 內每個 `# Translators:` 註解都緊貼含 gettext 呼叫的那一行，且有測試守住。
5. Espeak、RHVoice 在 terminated 後收到 `speak_segment` 時，經 lifecycle delivery thread 發出 `SEGMENT_FAILED`，不再靜默返回。
6. 引擎面板變更引擎時，旗標在存設定檔之前寫入。
7. 吞掉例外的 `except BaseException` 改為 `except Exception`；設定面板存檔失敗時不改寫任何設定。
8. 全部測試通過（基線 1220 passed、92 skipped，加上本階段新增測試）。

## 現況

- `pyproject.toml` 已設 `indent-style = "tab"`、`line-length = 110`，但 16 個新檔（`runtime/`、`compat/`、`indexLedger.py`、`nvdaEventBridge.py`、`configRepository.py`、`taskManager.py`）使用 4 空格縮排。對 `addon/` 執行 `ruff format` 會改動 40–41 個檔案。
- 試跑結果（暫時 worktree，已刪除）：先 `add-trailing-comma` 再 `ruff format` 各跑一次，41 檔、+3,832／−2,876（跑到穩定後的數字見設計第 2 節）；測試 1220 passed、92 skipped，與基線相同。
- 試跑發現 `log.py:55` 的 `# Translators:` 會被 ruff 換行拆離 `message=_(...)`；`generics/speechSymbols/views.py` 另有兩處原本就未緊貼（格式化前，註解後一行分別是第 57 行的 `self.speechSymbols = None` 與第 253 行的 `gui.messageBox(`）。
- `languageDetection/script_data.py` 由 `tools/generate_unicode_scripts.py` 產生，檔頭註明不得手改；格式化它會在下次重新產生時整檔回彈。
- `origin/pr-82` 有 6 個 commit 不在 master；全量格式化後該分支無法直接合併。使用者已接受此成本。

## 設計

### 1. 工具設定對齊 NVDA

`pyproject.toml`：

- `[tool.ruff.format]` 補 `line-ending = "lf"`。
- `[tool.ruff.lint]` 的 `ignore` 加 `N999`（模組名稱採 lowerCamelCase，同 NVDA）；加 `extend-unsafe-fixes = ["I001"]`。
- `exclude` 加兩項，各附註解。依 NVDA 註解，具體路徑以 `./` 開頭，表示相對於設定檔：
  - `./addon/synthDrivers/WorldVoice/driver/*/driver`：內層原廠驅動，依專案規則不修改。
  - `./addon/synthDrivers/WorldVoice/languageDetection/script_data.py`：自動產生。

`.pre-commit-config.yaml`：保留現有三個 hook，新增下列 hook，版本對齊 NVDA。頂層設 `files: ^addon/`，以及排除上述兩個路徑的 `exclude` 正規式。ruff 的 hook 以 `--force-exclude` 執行，本來就會遵守 pyproject；add-trailing-comma 與空白類 hook 不讀 pyproject，因此需要頂層的 `exclude`。

| repo | rev | hook |
| --- | --- | --- |
| `pre-commit/pre-commit-hooks` | 維持現有 | `trailing-whitespace`、`end-of-file-fixer`（`types_or: [python]`） |
| `asottile/add-trailing-comma` | `v4.0.0` | `add-trailing-comma` |
| `astral-sh/ruff-pre-commit` | `v0.16.3` | `ruff-format` |

不加入 NVDA 的兩個 hook：

- `no-commit-to-branch`：WorldVoice 直接在 master 上提交。
- `ruff`（`args: [--fix]`）lint hook：ruff 0.16.3 預設規則下，`addon/` 52 個檔案中有 39 個共 249 項 lint 問題（`BLE001` 89、`I001` 32、`UP031` 16、`F401` 14 等）。NVDA 能跑這個 hook 是因為它的程式碼沒有 lint 問題；WorldVoice 若照搬，任何碰到這 39 個檔案的 commit 都會被擋下。設定檔中以註解記錄此原因，lint 清理完成後（另排階段）再加入。

C11 把 `except BaseException` 改成 `except Exception` 後，ruff 仍會報 `BLE001`（該規則也涵蓋 `Exception`），所以本階段不會降低 lint 數量。

### 2. 一次性格式化

以 `pre-commit run --all-files` 執行上述 hook，重複到 exit code 為 0。原型實測要跑 3 輪才會穩定：ruff 拆行後，add-trailing-comma 會再補逗號，ruff 再重排一次。最終結果是 41 個 `.py` 檔、+3,930／−2,876，單獨成一個 commit，不含任何手動修改。接著另一個 commit 新增 `.git-blame-ignore-revs`，格式比照 NVDA：檔頭寫文件連結與 `git config --local blame.ignoreRevsFile .git-blame-ignore-revs` 用法，每筆 hash 前加 `# 說明` 註解。

### 3. 翻譯註解

依 NVDA `codingStandards.md`「Translatable Strings」修正三處：註解緊貼字串所在行；呼叫跨行時，註解放進 `_(` 括號內、字串之前。

新增測試 `tests/test_translator_comments.py`：掃描 `addon/` 內所有 `.py`（扣除排除項目），每個 `# Translators:` 註解須符合下列其一：

- 其後第一個非註解行含有 `_(`、`pgettext(`、`ngettext(` 或 `npgettext(`。
- 註解的上一行以上述呼叫的左括號結尾，也就是 NVDA 的跨行寫法，註解在括號內。

### 4. C1：terminated 後發 FAILED

`driver/Espeak/__init__.py` 的 `speak_segment` 與 `driver/RHVoice/__init__.py` 的 `speak_segment`，在 `_segmentTerminated` 為真時改為：

```python
self._segmentLifecycle.reject_new(context, token, on_event,
	RuntimeError("eSpeak driver has terminated"))  # RHVoice 用 "RHVoice driver has terminated"
return
```

錯誤訊息比照 OneCore／SAPI5／VE 的 `"<engine> driver has terminated"`。`reject_new` 的 docstring 已保證 lifecycle 關閉後仍可交付。已被 accept 的工作在 terminate 時保持靜默，由既有的 `test_cancel_or_terminate_before_deferred_delivery_keeps_event_silent` 等測試保護，本次不改。

### 5. C4：先寫旗標再存檔

`SpeechEngineSettingsPanel.onSave` 改為：

```python
def onSave(self):
	if self.activeEngine != self.previousActiveEngine:
		# Write the engine flags first so the saved configuration includes them.
		if super().onSave() and self.confirm == wx.YES:
			gui.mainFrame.onSaveConfigurationCommand(None)
			queueHandler.queueFunction(queueHandler.eventQueue, core.restart)
```

引擎集合沒有變更時不寫入，與現行行為相同。`BaseSettingsPanel.onSave` 改為回傳 `bool`（見第 6 節）：旗標寫到一半失敗時不存檔也不重啟，避免 NVDA 以只寫了一半的引擎集合重啟。NVDA 會忽略 `SettingsPanel.onSave` 的回傳值；`LogSettingsPanel` 呼叫 `super().onSave()` 時不使用回傳值，行為不變。

### 6. C10、C11：例外處理

吞掉例外的 7 處改為 `except Exception`：

| 位置 | 備註 |
| --- | --- |
| `globalPlugins/WorldVoice/speechSettingsDialog.py`（`BaseSettingsPanel.makeSettings` 的選項索引） | 維持 fallback 到第 0 項並嗶聲 |
| 同檔 `BaseSettingsPanel.onSave` | 一併處理 C10，見下 |
| 同檔 `SpeechRoleSettingsPanel` 讀取 role voice | 行為不變 |
| 同檔 `SpeechRoleSettingsPanel.onSave` 刪除 role 項目 | 行為不變 |
| `synthDrivers/WorldVoice/configRepository.py` 讀取 `config["speech"][synth]` | 行為不變 |
| `synthDrivers/WorldVoice/__init__.py` `_run_cleanup` | 行為不變，仍記 log |
| `synthDrivers/WorldVoice/driver/Cerence/__init__.py` `Voice.variants` | 行為不變，仍回 `[]` |

C10：`BaseSettingsPanel.onSave` 失敗時不再把所有欄位寫成第一個選項或 True，改為：

```python
except Exception:
	log.error("WorldVoice: failed to save %s settings", self.field, exc_info=True)
	tones.beep(100, 100)
	return False
return True
```

失敗前已寫入的欄位維持原樣，其餘欄位不動。回傳值供第 5 節的引擎面板判斷是否存檔與重啟。

清理後重新拋出的 2 處（`synthDrivers/WorldVoice/__init__.py` 建構子、`voiceManager.py` 建構子）的 `except BaseException: self.terminate(commit=False); raise` 是正確寫法，保留不改，並加一行註解說明遇到 `KeyboardInterrupt` 也須先清理。

## 提交順序

1. `pyproject.toml` 與 `.pre-commit-config.yaml` 設定。
2. 純格式 commit。
3. `.git-blame-ignore-revs`。
4. 翻譯註解修正與掃描測試。
5. C1 Espeak（紅燈測試 → 修正）。
6. C1 RHVoice（紅燈測試 → 修正）。
7. C4（紅燈測試 → 修正）。
8. C10 與 C11（紅燈測試 → 修正）。

步驟 2 之後，每個 commit 都應通過新的格式類 hook（`ruff format --check` 對變更檔案無輸出）。

## 測試

- **C1**：在 `tests/test_espeak_segment_drain.py` 與 `tests/test_rhvoice_segment_drain.py` 各加一個測試，仿照 `test_onecore_rejected_segment_uses_async_lifecycle_delivery(terminated=True)`：
  - `terminate()` 後呼叫 `speak_segment`，sink 收到唯一一個 `SEGMENT_FAILED`，`source_id` 與 `segment_id` 對應原 context。
  - 交付發生在 lifecycle delivery thread，不在呼叫端 thread。
  - native 沒有收到呼叫。
- **C4**：沿用 `tests/test_voice_settings_transaction.py` 以 stub 載入 `speechSettingsDialog.py` 的方式，記錄 `config` 寫入、`onSaveConfigurationCommand`、`queueFunction` 的呼叫順序，斷言引擎旗標寫入早於存檔。另斷言 `confirm == wx.NO` 時仍寫入旗標但不存檔、不重啟。
- **C10**：讓 `getattr(self, k + "CheckBox").IsChecked()` 在第二個欄位拋例外，斷言第一個欄位已寫入、其餘欄位維持原值、沒有任何欄位被改成 True，並記錄了 error log。
- **C11**：
  - `_run_cleanup` 遇到 `KeyboardInterrupt` 時往外拋，遇到 `Exception` 時記錄 log 並繼續後續清理。
  - 既有的 `tests/test_voice_config_repository.py::test_main_synth_lookup_exception_falls_back_to_voice` 以 `BaseException` 參數鎖住舊行為（來自 `148c47c`）。改為只參數化 `LookupError`、`RuntimeError`，另加測試斷言 `KeyboardInterrupt` 會往外拋。
- **C4 + C10 交互**：引擎變更時旗標寫入失敗，不存檔、不重啟。
- **翻譯註解**：見設計第 3 節。

## 驗收

- `python3 -m pytest tests`：全部通過，skip 數仍為 92（Neural 未安裝）。
- `ruff format --check addon`：通過。
- `git diff 42ea20b --stat -- 'addon/synthDrivers/WorldVoice/driver/*/driver' addon/synthDrivers/WorldVoice/languageDetection/script_data.py`：無輸出。
- `git ls-files addon/synthDrivers/WorldVoice/driver/Neural`：無輸出。
