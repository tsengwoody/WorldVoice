# 設定順序統一由設定表決定：交接紀錄

- **日期：** 2026-10-21
- **分支：** `feat/settings-order-from-table`，fast-forward merge 進 `master`，merge 後是 `50663ff`。
- **spec：** `docs/superpowers/specs/2026-10-21-feat-settings-order-from-table-design.md`
- **plan：** `docs/superpowers/plans/2026-10-21-feat-settings-order-from-table.md`。10 個 task 分 2 批，每批 5 個。
- **review：**
  - 第 1 批的批次 review（Opus 5.5 xHigh）：沒有 Critical，也沒有 Important；有 9 個 Minor。
  - 最後由 Fable 5.1 review 整個分支：Important 1 個、Minor 5 個，見 `docs/superpowers/finish/2026-10-21-feat-settings-order-from-table-review.md`。
  - 以上全部都已修正。

## 1. 修改內容（使用者決定，2026-10-21）

### 1.1 統一順序（Q1）

`PIPELINE_SETTINGS` 是唯一的順序來源。NVDA 語音面板、語音設定環、WorldVoice 語音管線面板都依照它的順序建立控制項：

1. 範圍（只出現在語音管線面板）
2. 全域停頓
3. 忽略數字間逗號
4. 數字語言（只出現在語音面板和語音設定環；值照舊由 NVDA 存在語音設定裡，不寫進 pipeline 設定）
5. 數字模式
6. 每組位數
7. 群組停頓
8. 數字停頓
9. 項目停頓
10. 全部朗讀停頓
11. 中文空白停頓
12. 標點停頓開關
13. 移除標點
14. 標點停頓參數
15. 標點停頓字元

和 `master` 比較：

- **語音管線面板：** 全域停頓從第 6 項移到第 2 項。
- **語音設定環：** 全域停頓移到「Detect language based on Unicode characters」後面；群組停頓移到數字模式後面。

### 1.2 標籤（Q2、N1）

- **共用標籤：** 兩個面板用同一套標籤。
- **格式：** 一律句首大寫，快速鍵（`&`）的位置不變。語音管線面板照 NVDA 的作法，在非勾選框的標籤後面自動加「:」。
- **改名的標籤：** Number &mode／Number mode、Number &language／Number language、Item wait factor、Effect scope、Group size、Punctuation pause characters、Ignore commas between numbers。
- **pipeline log 開關：** 也改成同樣的規則，並沿用上面的共用 msgid。
- **zh_TW：** 新增 9 條、刪除 21 條用不到的翻譯，`msgfmt --check` 通過。

### 1.3 其他

- **Q3：** 語音管線面板的全域停頓維持 0～10 的顯示，存檔時 ×10（`panel_scale=10`）。
- **Q4：** 啟用規則改由 `depends_on` 宣告，兩個面板共用同一套邏輯：
  - 標點停頓開關控制三個標點控制項。
  - 數字模式選「群組」時，才啟用每組位數和群組停頓。
- **自訂控制項的位置：** 語音面板裡的自訂控制項（每組位數、標點停頓字元），自動放在設定表中前一個項目的後面，不再寫死位置。
- **N5：** 目前的合成器不是 WorldVoice 時，語音面板不會建立這兩個自訂控制項，存檔時也不寫入。要調整這兩項，請到 WorldVoice 的語音管線面板。
- **新模組：** `pipeline/panelLayout.py`（只有版面規則，不依賴 wx）、`pipelineControls.py`（兩個面板共用的控制項建構器），以及設定表的守門測試 `tests/test_settings_table_guard.py`。
- **I1（最後 review 修掉的既有問題）：**
  - **問題：** 設定對話框開著時切換合成器，NVDA 會重建語音面板（`refreshGui`）。重建時，面板還在使用上一次建立、已經被刪掉的控制項。真正的 wxPython 會丟出 `RuntimeError`，語音面板就建立不出來。
  - **範圍：** 這是 `master` 上原本就有的問題，不是這次造成的。
  - **修正：** `_voiceControl` 把已經刪掉的控制項（布林值為 false）當成不存在（`d511d9d`）。測試用的假控制項也改成刪除後再使用就會丟錯。

## 2. 驗證（`master` `50663ff`，Linux，`ref/nvda` 是 `7d25bc76e`）

| 項目 | 結果 |
| --- | --- |
| `python3 -m pytest -q tests` | 2084 passed、0 skipped（基準 `658f8b9`：1938） |
| `prek run --all-files` | 全部 Passed |
| `git diff --check` | 沒有輸出 |
| 受保護路徑（和 `658f8b9` 比較）、`git ls-files .../Neural` | 沒有輸出 |
| 設定檔 | confspec 的 14 個鍵、預設值都不變 |
| mutmut | `panelLayout.py` 的 46 個突變全部被測試抓到 |
| Fable 驗證 | 逐一還原 8 個功能 commit，都有測試失敗；自己植入的 42 個突變抓到 39 個，剩下 3 個已補測試 |

**沒有打包。** Windows 上的 NVDA 和真正的 wx 都還沒有驗證。

## 3. 尚未驗證（spec §10.6，需要在 Windows 上用 NVDA、裝測試版）

1. **語音面板（WorldVoice）：**
   - 版面和 Tab 順序都照設定表；每組位數在數字模式後面，標點停頓字元在標點停頓參數後面。
   - 記下 NVDA 唸每個控制項的方式。
2. **語音管線面板：**
   - 版面和 Tab 順序都照設定表。
   - 全域停頓顯示 0～10，存檔後重新開啟，值還在。
   - Alt+M 會移到數字模式。
3. **啟用狀態（兩個面板）：**
   - 開啟面板時，各種模式和開關組合下的狀態都正確。
   - 用方向鍵切換模式、切換開關時，狀態立即跟著變。
   - Tab 會跳過停用的控制項；物件瀏覽會讀出「無法使用」。
4. **語音面板切換語音：**
   - 每一列都留在原位，啟用狀態跟著語音的設定。
   - 對話框開著時用語音設定環改模式或開關，再切換語音，狀態也要跟著變。
5. **語音設定環：**
   - 全域停頓排在「Detect language…」後面，群組停頓排在數字模式後面。
   - 用設定環改的值會保留；數字語言在 NVDA 重新啟動後仍然保留。
6. **其他合成器與重建（N5、I1）：**
   - 使用 eSpeak NG 時，語音面板不顯示每組位數和標點停頓字元，存檔也不會改到 pipeline 設定。
   - 設定對話框開著時，依序試三種切換：WorldVoice → eSpeak NG → WorldVoice；再到合成器對話框重新選 WorldVoice，直接按確定（WorldVoice → WorldVoice）。
   - 每次切換後，控制項和順序都正確，log 沒有 `RuntimeError`。
7. **zh_TW：** 所有標籤都有翻譯，並記下冒號的顯示方式（現在是半形「:」）。

## 4. 使用者還沒確認的使用者可見預設

1. **I1 的修法（N9）：** 遇到已經被刪掉的控制項，就當成不存在。
2. **N2：** 語音管線面板的範圍或數字模式沒有選取任何項目時，存檔會保留原本的值。正常操作碰不到這種情況。
3. **N5 的影響：** 使用 eSpeak 等其他合成器時，語音面板不再出現每組位數和標點停頓字元。
4. **N6：其他語言會顯示英文。**
   - ar、ru、uk、tr、zh_CN、zh_HK：改了名稱的標籤會顯示英文。
   - zh_TW 以外的所有語言：Group size、Punctuation pause characters、Apply speech dictionaries、Speech viewer 會顯示英文。
5. **N7：** zh_TW 用不到的 21 條翻譯是直接刪掉，不是標成 obsolete。
6. **F2：** 語音管線面板多了 Alt+M 快速鍵，來自「Number &mode」。
7. **F5：** zh_TW 語音管線面板的標籤冒號，從全形「：」變成半形「:」。
8. **F4（既有行為）：** 設定檔裡存了不認得的範圍值時，面板顯示「All Synthesizers」，存檔後會存成 `all`。
9. **N8：** 只有勾選框和下拉選單可以控制其他控制項，而且不能多層串接；守門測試會強制這一點。

## 5. Commit

`git log --reverse --format='%h %s' 658f8b9..50663ff`

- `8170a18` docs: specify settings order and controls from the pipeline table
- `94c0f4e` docs: plan the settings order and controls from the pipeline table
- `347f7f2` feat: give the pipeline table the canonical order and every control field
- `9314eb3` feat: place number language in the pipeline table as an ordering-only entry
- `2eb7c62` feat: add the pure layout rules both settings panels follow
- `4a53a76` feat: add one builder for every pipeline settings control
- `ba2a657` feat: build the Speech Pipeline panel from the pipeline table
- `df7a2c2` test: pin that a WorldVoice control may follow another one
- `3e5e9b9` test: add NVDA's spacers to the fake sizer helper
- `b913ba0` feat: place the Voice panel's pipeline controls by table order
- `df93f3e` docs: record that another synth gets no WorldVoice controls in the Voice panel
- `f022d98` feat: apply the Voice panel's enable rules from the table
- `94bc361` test: pin the order of both settings panels to the pipeline table
- `67df643` feat: give the log switches the shared labels and update zh_TW
- `f872abf` docs: record that the log switch labels follow the label rule
- `16784ea` test: close the gaps the batch review found in the guard and the builder
- `cd8398b` test: word the Speech Pipeline tests as the panel now works
- `2184ff4` docs: match the plan's first review focus item to the renamed test
- `b8498e6` test: run mutmut on the panel layout rules
- `ce70684` docs: review the settings order from the pipeline table branch
- `d511d9d` fix: treat destroyed Voice panel controls as absent on a rebuild
- `b666eb3` test: make the table guard reject colons, bad bounds and step drift
- `7f2e234` test: pin the save and cancel branches the real table never reaches
- `3aa5ecd` docs: name the source lines of the new zh_TW catalog entries
- `8c2f718` docs: describe how the Voice panel survives a rebuild
- `50663ff` docs: record how the settings order review findings were fixed
