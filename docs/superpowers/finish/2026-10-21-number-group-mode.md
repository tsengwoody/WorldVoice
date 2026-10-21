# 數字群組模式交接紀錄

- **日期：** 2026-10-21
- **分支：** `feat/number-group-mode`，fast-forward merge 進 `master`，merge 後在 `64e1559`。
- **文件：**
  - spec：`docs/superpowers/specs/2026-10-21-feat-number-group-mode-design.md`
  - plan：`docs/superpowers/plans/2026-10-21-feat-number-group-mode.md`，superpowers 7.0 格式，用 executing-plans 執行。共 12 個 task，分成 3 批，每批 4 個。
  - review：`docs/superpowers/finish/2026-10-21-feat-number-group-mode-review.md`
- **review 經過：**
  - 第 1 批批次 review（Opus 5.5 xHigh）：沒有 Critical 或 Important，有 4 個 Minor。
  - 第 2 批批次 review：有 1 個 Important（I1，見 1.4）和 5 個 Minor。
  - 最後 Fable 5.1 review：有 1 個 Important（見 1.5）和 3 個 Minor。
  - 以上全部都已修正。

## 1. 修改內容（使用者決定，2026-10-21）

### 1.1 群組模式（取代「兩位一組」）

- **G1：** 從左邊開始分組。例如每組 3 位時，`"12345"` 唸成 `123`、`45`。
  - 有小數點的數字當成一個值唸。
  - 正負號跟著第一組。
  - 位數不超過一組的數字不分組。
- **G2、G3：** 用 `SelectOnFocusSpinCtrl`（`wx.SpinCtrl` 的子類別）設定每組位數，範圍 1～10，預設 3。
- **G4：** 兩個面板的位置和啟用規則。
  - 語音管線面板的順序是：數字模式 → 每組位數 → 群組停頓。
  - NVDA 語音面板：每組位數放在「數字模式」的正下方。
  - 語音設定環：不加入每組位數。
  - 只有選「群組」時，每組位數和群組停頓才能用，其他模式下停用。
- **G5：** 程式裡的 pair 全部改名為 group，不保留相容性：`number_mode = group`、`group_wait_factor`（driver id 是 `groupwaitfactor`）、`group_size`。
- **G6：** 介面字串改成「群組」、「每組位數：」、「群組停頓參數：」。
- **G7：** 停頓指令改名為 `GroupNumberBreakCommand`。

### 1.2 數字模式與數字停頓

- **U1：** 數字模式在每兩位數字之間插入 `NumberBreakCommand(數字停頓)`。數字停頓是 0 時也照樣插入；0 會變成 `Pause(0)`，讓每一位各自成為一個 segment。
- **U2：** `number_wait_factor` 插入的停頓也改成 `NumberBreakCommand`。

### 1.3 設定

- **U3：** 讀到不認得的數字模式時，一律當成「數值」。例如舊設定檔裡存的 `pair`，讀進來就變成數值模式。
- 整數設定可以各自設定上下限，讀取時會把超出範圍的值夾回範圍內。NVDA 的滑桿也改用 spec 定義的上下限，不過目前所有滑桿都還是 0～100。

### 1.4 修掉的既有問題：語音面板讀取已釋放的記憶體（第 2 批 I1）

- **問題：** NVDA 語音面板搬移控制項時，先執行 `Detach`，之後才讀 sizer item 的排版設定。`Detach` 會把 sizer item 刪掉，所以讀到的是已經釋放的記憶體。
- **範圍：** 標點停頓字元欄位從 `a3493ba` 起就是這樣寫；這次新增的每組位數微調框也照抄了同一種寫法。
- **修正：** 兩處都改成用 `_moveSizer`，在 `Detach` 之前先讀好排版設定（`3ea7aad`）。

### 1.5 修掉的回歸：範圍「全部」時，OneCore 會截掉語音（最後 review 的 I1）

- **原因：** NVDA 的 `speechXml` 用類別名稱找轉換函式。遇到 `BreakCommand` 的子類別時找不到函式，就直接結束，後面的內容全部丟掉。
- **影響：** 範圍設為「全部」、又用 OneCore 的使用者，數字停頓之後的整句話都聽不到。例如 `"共 12 34 個"` 只會唸出「共 12」。
- **既有程度：** `master` 上的標點停頓（`PunctuationBreakCommand`）和舊的兩位一組停頓也有同樣的問題，只是還沒觸發。
- **修正：** `supports_roles` 為 false 時，所有 `BreakCommand` 子類別都換回一般的 `BreakCommand`。WorldVoice 自己使用時照樣保留子類別（`e16089a`）。
- **測試：** 新增守門測試，用 NVDA 真正的 `SsmlConverter` 處理範圍「全部」的輸出，確認整句都還在。
- **決定方式：** 這個修法是協調者照建議預設決定的，使用者在 merge 之後仍然可以改。
- **文件更正：** 先前 spec F2、Q11，以及上一份 review 對 OneCore 的描述是錯的，都已經更正（`fd9f330`）。

## 2. 驗證（`master` `64e1559`，Linux，`ref/nvda` = `7d25bc76e`）

| 項目 | 結果 |
| --- | --- |
| `python3 -m pytest -q tests` | 1938 passed、0 skipped（基準 `4c5183e`：1830） |
| `prek run --all-files` | 全部 Passed |
| `git diff --check` | 沒有輸出 |
| 受保護路徑（和 `4c5183e` 比較）、`git ls-files .../Neural` | 沒有輸出 |
| `msgfmt --check`（zh_TW） | 通過 |
| mutmut | 群組模式相關：146 個突變，抓到 141 個，存活的 5 個都和原本的程式等價。`_plain_breaks`、`_stage_handler`：22 個突變全部抓到 |
| Fable 驗證 | 12 個功能 commit 各自還原後，都有測試失敗；Fable 自己植入的 18 個突變也全部被抓到 |

這次**沒有打包**。Windows 上的 NVDA、實際音訊和各引擎 SDK 都還沒有驗證。

## 3. 尚未驗證

以下是 spec §9.5 列的項目，要在 Windows 上用 NVDA、裝測試版手動驗證：

1. **群組模式：**
   - 每組位數分別設 1、2、3、10，群組停頓分別設 0、50。
   - 朗讀 `"12345678"`、`"-1234567"`、`"12.5"`、`"0912345678"`。
   - 確認：每一組都當成一個數字唸。停頓設 0 時，組與組之間只有 segment 交接的空檔。
2. **數字模式：**
   - 數字停頓分別設 0 和 40，`"12345"` 每兩位之間都要有停頓。
   - 停頓設 0 時，注意聽每一位各自切開 segment 的效果。
   - 在 `unicode.dic` 把數字對應成中文、數字語言設 zh，`"123"` 要逐位唸，而且中間有停頓。
3. **升級：** 準備一個存了 `number_mode = pair`、`pair_wait_factor = 40` 的設定檔，確認：
   - 兩個面板和語音設定環都顯示「數值」，數字也照數值唸。
   - 在語音設定環上切換數字模式不會出錯。
   - `nvda.ini` 裡還留著舊的設定鍵，但 log 沒有任何錯誤。
4. **語音管線面板：**
   - Tab 順序正確。
   - 記下 NVDA 唸「每組位數」微調框的實際內容。
   - 不是群組模式時，Tab 會跳過那兩個控制項，物件瀏覽會報告「無法使用」。
   - 用方向鍵切換數字模式時，那兩個控制項的啟用狀態立刻跟著變。
   - 存檔後重新開啟，設定值都還在。
5. **NVDA 語音面板（WorldVoice）：**
   - 每組位數在 Tab 順序和畫面上，都緊接在「數字模式」後面。
   - NVDA 有唸出它的標籤。
   - 開啟面板時、改變模式時，停用狀態都正確。
   - 面板開著時，用語音設定環改數字模式，再切換語音，啟用狀態要跟著模式變。
   - 存檔後按取消，位數保留；沒存檔就按取消，位數恢復成原本的值。
6. **範圍「全部」，用 eSpeak NG、OneCore、SAPI5 各試一次：**
   - 數字模式、數字停頓 0：`"12345"` 不能被唸成一個數字。
   - 群組模式、群組停頓 0：組與組不能黏在一起。
   - OneCore 唸 `"共 12 34 個"` 這類句子時，數字後面的內容要完整唸出來。
   - 這一項也要回頭補驗 `2026-10-21-number-and-punctuation-pause.md` 第 3 節的第 7 項，因為那時的停頓子類別有同樣的問題，現在已經修好了。

## 4. 使用者還沒確認的使用者可見預設

1. **範圍「全部」的停頓：** 其他語音合成器收到的是一般的 `BreakCommand`，和原本 `master` 的行為相同（1.5 的修法）。
2. **語音面板的位置：** 每組位數放在數字模式正下方，所以群組停頓滑桿和它之間，還隔著全域停頓和數字停頓。
3. **微調框：** 用 `SelectOnFocusSpinCtrl`，焦點移進去時會自動選取整個數值。
4. **整數設定的上下限：** 所有整數設定都統一套用上下限，讀取時把超出範圍的值夾回範圍內。
5. **F1 選項 A：** 如果有人手動把 `nvda.ini` 改成不合法的 `group_size`，NVDA 驗證設定時照樣會丟例外。這和其他整數設定的風險相同。
6. **語音面板目前不是 WorldVoice 時：** 每組位數放在面板最後面，保持啟用，存檔時也會寫入。
7. **文件：** 兩份 readme 補了說明，changelog 不改。
8. **設定鍵名稱：** driver id 改成 `groupwaitfactor`，會出現在 `nvda.ini` 和 pipeline log 裡。
9. **原本用兩位一組的使用者：** 升級後會沒有提示地變成數值模式。`pair_wait_factor` 不遷移，所以群組停頓從 0 開始；預設每組 3 位，和原本的 2 位不同。
10. **數字模式：**
    - 數字停頓設 0 時，每一位都會切成一個 segment。
    - 數字被替換成中文字時，位數之間的停頓改用「數字停頓」，原本用的是「中文空白停頓」。

## 5. Commit

`git log --reverse --format='%h %s' 4c5183e..64e1559`

- `a7c9f9c` docs: specify the number group mode
- `e310187` docs: plan the number group mode
- `89e8623` feat: bound and clamp pipeline integer settings
- `e19d28f` refactor: rename the pair wait to the group wait and add the group size
- `8b8ba47` feat: read numbers in groups of a chosen size
- `453582e` feat: read unknown number modes as value
- `724ae36` feat: mark the number pause as a NumberBreakCommand
- `cff471d` feat: pause between the digits of a number in digit mode
- `e0c205d` feat: set the group size in the speech pipeline panel
- `abc1609` feat: set the group size in the voice settings panel
- `3ea7aad` fix: read sizer layout before detaching it in the voice panel
- `1bb5c5e` feat: enable the voice panel group controls only in group mode
- `9a7a76d` docs: translate and document the number group mode
- `a636244` test: guard against stacked number and group breaks
- `4aceb93` test: pin that the group wait ignores the global wait factor
- `1c28d13` test: pin that an unchanged number mode is not written again
- `dac1324` feat: give numeric pipeline synth settings their spec bounds
- `9255518` test: pin the voice panel saving its pipeline values in one update
- `c02b42d` test: tell NVDA's select-on-focus spin control from a plain one
- `ed12827` fix: save no number mode selection as value in the pipeline panel
- `8642cbf` test: pin that group mode reads a decimal untranslated
- `5ff442e` docs: record the group mode mutation results
- `e4a0467` docs: review the number group mode branch
- `e16089a` fix: give other synthesizers plain breaks in scope all
- `1393696` test: pin the settings and doc a stage handler passes on
- `318e176` fix: keep the stored number mode when the panel has no selection
- `fd9f330` docs: correct how OneCore handles break subclasses
- `435e3a0` docs: point the group translation entry at its source line
- `64e1559` docs: record how the group mode review findings were fixed
