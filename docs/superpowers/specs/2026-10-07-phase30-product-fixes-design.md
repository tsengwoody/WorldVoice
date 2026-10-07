# 階段 30：測試過程發現的產品問題修正

日期：2026-10-07。
基準：`master`（`100e3a6`，測試優化階段 23～28 完成）。分支：`phase30-product-fixes`。
狀態：使用者指示（2026-10-07）「除了 5 外，請都修正，將 4 沒用到的死碼刪除」；自動流程執行，審查使用 Opus 5.5。

問題清單來自 `docs/superpowers/specs/2026-10-06-phase27-coverage-gaps-design.md` 的「測試過程發現的產品程式問題」。第 5 項（`createDriverSettings` 重新顯示隱藏控制項，目前因 NVDA 隨後再隱藏而無實際影響）依使用者決定不修。階段 29 的編號保留給 mutmut 試跑。

## 1. 拒絕匯出時沒有「已關閉記錄」提示

`addon/globalPlugins/WorldVoice/__init__.py:166-170` 的 `disable_log_record`：`ui.message(_("turn off WorldVoice`s log record"))` 縮排在 `if ask_export():` 內。記錄已在第 167 行關閉，提示卻只在使用者選擇匯出時念出。

修法：提示移到 `if` 之外，關閉記錄後一律念出；匯出與否只決定是否呼叫 `export()`。

## 2. chunker 的 escape 長度與組合符號

`addon/synthDrivers/WorldVoice/text/chunker.py`（VE／Cerence 使用）：

- docstring 說上限只算純文字、escape 可以讓 piece 略長，但實作 `remaining = max_length - len(current)` 把 escape 算進長度：`ESC + "a"*20`（上限 10）切出只有 escape 的 piece；`"aaa" + ESC + "b"*20` 第一段只有 3 個純文字字元。開頭的 `len(text) <= max_length` 也以含 escape 的長度判斷。
- 沒有空白可切時在 `remaining` 硬切，可能把組合符號（例如 U+0301）與前面的字母切到不同 piece，引擎會把落單的組合符號當成獨立字元處理。

修法：

- 以純文字長度計算上限（另記 `plain` 計數；開頭的快速路徑以去掉 escape 後的長度判斷）。escape 永遠附在下一段文字所在的 piece（或結尾時附在最後一個 piece），不會單獨成為一個 piece。
- 硬切點若落在組合符號（`unicodedata.combining(ch) != 0`）之前，往前退到該字母之前；若退到 0（整段都是同一個字母加組合符號），則往後延伸到組合序列結束，寧可略超過上限也不拆開。在空白處切的路徑不變。
- 不變式：所有 piece 串接等於原文；每個 piece 的純文字長度不超過上限（唯一例外：單一字母的組合序列本身超過上限）；escape 不被切開；沒有只含 escape 的 piece。

## 3. pipeline log 寫檔失敗讓整句無聲

`addon/synthDrivers/WorldVoice/pipeline/__init__.py` 的 `_run_logged`：開啟某 stage 的 log 時，先以 `list()` 讀完輸入 generator，再 `pl.write(...)`；寫檔的 `OSError`（磁碟滿、檔案被鎖）往外拋。NVDA 的 `Filter.apply`（`ref/nvda/source/extensionPoints/__init__.py:112-117`）記錄例外後沿用原本那個已讀空的 generator，後面所有 stage 與 synth 都拿到空序列，整句不發聲。

修法：記錄寫入改走一個 helper，攔下 `OSError`：

- 第一次失敗以 `log.error(..., exc_info=True)` 記錄；之後連續失敗不再重複記錄（避免每句話都寫 NVDA log），直到某次寫入成功才重設。
- 不論寫入成功與否，stage 照常執行並回傳轉換後的序列。
- 不自動關閉記錄設定（那是使用者可見的設定變更）。

## 4. 刪除死碼 `SpeechRoleSettingsPanel.voiceInstance`

`addon/globalPlugins/WorldVoice/speechSettingsDialog.py` 的 `voiceInstance` property 在整個 add-on 與測試中都沒有使用者。刪除。

## 6. 數字語言在其他語言區段內被誤判

`pipeline/__init__.py` 的 `_insert_WVLangChangeCommand_between_number` 追蹤目前語言 `current_lang`，但對每段文字呼叫 `deduplicate_language_command(..., ctx)`，後者從 `ctx.language`／預設語音重新開始判斷。主語言 zh、number_language zh、序列 `[LangChangeCommand("en"), "Hello 123"]`：插入的 `WVLangChangeCommand("zh")` 被當成「與目前（zh）相同」而丟掉，`123` 以英文語音念出。只在序列含 NVDA 自己的 `LangChangeCommand`（使用者開了 NVDA 自動語言切換或 reportLanguage）時觸發。

修法：`deduplicate_language_command(speechSequence, ctx, start_language=None)`；給定時，初始語言為 `start_language`、初始語音為該語言的語音（沒有則預設語音）。`_insert_WVLangChangeCommand_between_number` 傳入 `current_lang`。其他呼叫端不傳，行為不變。

## 測試

每項先寫會在舊程式失敗的測試，再修：

1. `test_global_plugin_menu.py`：拒絕匯出時仍念出提示、不匯出。
2. `test_text_preprocessing.py`：escape 不計入上限、沒有只含 escape 的 piece；硬切不拆開字母與組合符號（含整段同一組合序列超過上限的情況）；串接等於原文。
3. `_run_logged` 的測試：寫檔拋 `OSError` 時回傳轉換後的序列、只記錄一次錯誤、成功後重設。
4. 確認沒有任何引用（刪除後全套通過）。
6. `test_worldvoice_speak.py`（或 pipeline 測試）：上述 zh／zh／en 例子中 `123` 以 zh 語音念出；主語言 en、number_language zh 的既有情況不變。

## 驗證

全套、逐檔、`ruff check/format addon tests`、`pytest tests --cov`（覆蓋率不降）、壓力測試（最多 3 個 worker、有記憶體看門狗）。
