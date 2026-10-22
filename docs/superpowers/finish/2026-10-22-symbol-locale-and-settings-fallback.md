# 符號名稱語系與設定讀取退回：交接紀錄

- **日期：** 2026-10-22
- **分支：** `feat/symbol-locale-and-settings-fallback`，用 fast-forward 合進 `master`，合併後是 `ed1f387`。
- **流程：** 輕量的一般流程：spec 和 plan 都寫短，plan 有 7 個 task、不分批，最後由 Fable 5.1 review。
- **文件：**
  - spec：`docs/superpowers/specs/2026-10-22-feat-symbol-locale-and-settings-fallback-design.md`
  - plan：`docs/superpowers/plans/2026-10-22-feat-symbol-locale-and-settings-fallback.md`
  - review：`docs/superpowers/finish/2026-10-22-feat-symbol-locale-and-settings-fallback-review.md`
- **review 結果：** Critical 0、Important 2、Minor 5。兩個 Important 和 Minor 1、2、4 已修正；Minor 3、5 接受不改。

## 1. 修改內容（使用者決定，2026-10-22）

### 1.1 數字裡的符號名稱

- **語系來源：** WorldVoice 會用「實際發聲語音」的完整語系查符號名稱，也就是 `getVoiceNameForLanguage` 回傳的那個語音的 `VoiceSpec.locale`。
  - 語音的語系優先於 NVDA 目前語言的國家碼。
  - 某個語言沒有可用的語音時，`getVoiceNameForLanguage` 本來就會回傳預設語音，所以會用預設語音的語系。
- **正規化與查表：**
  - 語系先用 NVDA 的 `languageHandler.normalizeLanguage` 正規化。
  - 接著確認 NVDA 有沒有 `locale/<語系>/symbols.dic`。沒有，或語音只回報裸代碼時，退回原本的 `_symbol_locale` 規則（D1、D2）。
- **範圍「全部」時的其他合成器：** 不變，不套用數字語言。
- **影響範圍：** 只改變數字裡的符號名稱。NVDA 自己的 `LangChangeCommand` 也走同一套規則（D4、D5）。
- **上一個功能的測試：** M4 測試改成模擬「回傳預設語音」，number-unify 的 spec 用刪除線註記這個變更。

### 1.2 設定讀取的退回

- **`group_size`：** confspec 改成 `min=2,max=10`，並移除 `stored_min_value`。值不在 2～10 時讀成 3。
- **驗證失敗時：** 所有 pipeline 設定、log 開關、log 面板讀取的值，只要 NVDA 驗證失敗（configobj `ValidateError`），就改用預設值，WorldVoice 仍可正常載入。
  - 每個設定、每個值只記一次 debugWarning，不跳出提示。
  - 讀取時不寫回設定檔。
- **存檔時修正設定檔（Important 1）：** ~~使用者下次在面板存檔時，會一併寫入之前退回成預設值的設定，把設定檔改回合法的值。~~ Changed by `fix/uniform-settings-save` (user, 2026-10-22)：拿掉 `fallen_back`。`PipelineSettingsService.update` 會寫入呼叫端給的每一個值，不管有沒有改；NVDA 的 `__setitem__` 發現新值和目前的值 `str` 相同時就不寫、也不把設定檔標成已修改。所以面板存檔時，退回成預設值的設定會被寫成預設值，設定檔改回合法的值；沒改的值不會真的寫入。只有值和 `get()` 讀到的不同時才通知 listener。
  - log 開關和引擎旗標本來就會在存檔時全部寫入。（`fix/uniform-settings-save` 補註：引擎面板只有在啟用的引擎組合改變時才寫入旗標；NVDA 讀取時不驗證引擎旗標，所以不會有被拒絕的值。這次沒有改引擎面板。）
- **找不到 configobj 時：** 改用一個永遠不會被丟出的佔位例外類別，避免把真正的錯誤吞掉。

## 2. 驗證（`master` `ed1f387`，Linux，`ref/nvda` = `7d25bc76e`）

| 項目 | 結果 |
| --- | --- |
| `python3 -m pytest -q tests` | 2324 passed、0 skipped（基準 `b244821`：2254） |
| `prek run --all-files` | 全部 Passed |
| `git diff --check` | 沒有輸出 |
| 受保護路徑（和 `b244821` 比較）、`git ls-files .../Neural` | 沒有輸出 |
| mutmut | 符號語系部分：96 個突變抓到 94 個，存活的 2 個等價。設定讀取部分：`update` 存活 8 個，都只改了 listener 失敗時 `log.error` 的訊息，這一行和 `master` 相同 |
| Fable 驗證 | 逐一還原 5 個功能 commit，每個都會讓測試失敗；Fable 自己植入的 14 個突變中，存活的 2 個就是兩個 Important，已補上測試 |

**沒有打包。** Windows 上的 NVDA 和各引擎都還沒驗證。

## 3. 尚未驗證（spec §7，Windows／NVDA）

1. OneCore 的 `zh-TW` 語音指派給 zh、NVDA 介面是英文、數字模式：`2×3` 念「乘以」，`3.5` 念 zh_TW 的點。
2. zh_CN 語音指派給 zh、NVDA 是繁體中文：`2×3` 念「乘号」。
3. 數字語言設 en，但沒有英文語音：符號念成中文名稱（預設語音的語系）。
4. 在 `nvda.ini` 設 `group_size = 11`，另一次測試設 `number_wait_factor = abc`，再重新啟動 NVDA：
   - WorldVoice 能載入；
   - 面板顯示預設值；
   - debug log 每個設定只有一筆警告；
   - 在面板存檔後，設定檔被改回合法的值。
5. 把某個 log 開關設成 `maybe`：Log Record 面板能打開，該開關是未勾選。

## 4. 使用者還沒確認、使用者看得到的預設

1. **D2：** 語音的語系只是裸代碼時，照原本的規則處理。
2. **D4、D5：** 只有數字裡的符號名稱會改變；NVDA 自己的語言切換指令也套用同一套規則。
3. **警告的層級：** 只記 debugWarning，在 NVDA 預設的 log 層級下看不到。
4. **舊的群組大小：** 設定檔裡存的 `group_size = 1`，現在讀成 3，不再是 2。
5. ~~**log 的 `enable` 旗標：** 這個旗標只在開啟或關閉 log 時寫入。如果它存成不合法的值（例如 `maybe`），會一直留在設定檔裡，每次啟動 NVDA 記一筆 debug 警告，直到使用者切換一次 log 為止。這次沒有修。~~ ~~Fixed by `fix/log-enable-repair` (2026-10-22)：Log Record 面板儲存時，會把目前生效的值寫回不合法的 `enable` 旗標；合法的值不會重寫。~~ Changed by `fix/uniform-settings-save` (user, 2026-10-22)：拿掉 `PipelineLogService.repair`。Log Record 面板每次儲存都把勾選框的值寫進 `enable` 旗標，和 log 開關一樣；NVDA 會略過沒改的值，不合法的值則被換成合法的布林值。開啟時的確認和關閉時的匯出詢問，仍然只在開關狀態真的改變時出現。
6. **zh_CN 語音的符號名稱：** NVDA 是 zh_TW 時，zh_CN 語音會念簡體的名稱（例如「乘号」），這是「語音的語系優先」的結果。

## 5. Commit

`git log --reverse --format='%h %s' b244821..ed1f387`

- `3c5288e` docs: specify symbol names from the voice locale and the settings read fallback
- `2b056d5` docs: plan the symbol-locale and settings-fallback feature
- `5bf22a7` fix: read an invalid stored pipeline setting as its default
- `90ce6ca` fix: read a group size outside 2..10 as 3
- `9a72ba1` fix: read an invalid stored log switch as off
- `be1509b` feat: give pipeline stages the locale of the voice for a language
- `13d5801` feat: name number symbols in the locale of the voice that speaks them
- `5528604` test: expect default-voice names when the number language has no voice
- `da29e37` test: keep the pipeline test ids ASCII so mutmut can select them
- `7c67961` docs: record the symbol-locale mutation results
- `0979d9c` docs: review the symbol-locale and settings-fallback branch
- `36a5f8f` fix: write a refused pipeline value back on the next panel save
- `9089dcc` test: pin that the voice locale, not its language, is returned
- `a185839` test: prove the symbol-table path guard refuses a real traversal
- `4077816` fix: never hide a read bug behind the missing-configobj fallback
- `636450d` docs: correct the NVDA config line numbers and say where stages run
- `ed1f387` docs: record how the symbol-locale review findings were fixed
