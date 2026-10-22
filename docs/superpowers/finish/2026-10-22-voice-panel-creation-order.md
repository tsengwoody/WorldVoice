# 語音面板控制項依設定表順序建立：交接紀錄

- **日期：** 2026-10-22
- **分支：** `feat/voice-panel-creation-order`，以 fast-forward 合進 `master`，合併後是 `971b847`
- **流程：** 一般流程的輕量版。spec 和 plan 都很短，5 個 task，不分批；最後由 Fable 5.1 review 一次
- **文件：**
  - spec：`docs/superpowers/specs/2026-10-22-feat-voice-panel-creation-order-design.md`
  - plan：`docs/superpowers/plans/2026-10-22-feat-voice-panel-creation-order.md`
  - review：`docs/superpowers/finish/2026-10-22-feat-voice-panel-creation-order-review.md`。Critical 0、Important 0、Minor 5，全部已經修正

## 1. 修改內容（使用者決定，2026-10-22）

- **問題：** 在 NVDA 語音面板裡，「每組位數」和「標點停頓字元」原本是在最後才建立，之後再搬到正確的位置：
  - 畫面位置靠 `_moveSizer` 搬過去。
  - Tab 順序靠 `MoveAfterInTabOrder` 調整，但只移動了控制項，標籤沒有跟著移動。
  - 物件瀏覽（NVDA+numpad4/6）是照視窗的建立順序走，所以這兩項會排在最後，標籤也不在各自的控制項前面。
- **修正：** 這兩項改成在設定表的位置直接建立。視窗的建立順序（也就是物件瀏覽的順序）、Tab 順序、畫面順序現在都和設定表一致，每個標籤都緊接在自己的控制項前面。這兩項不再呼叫 `MoveAfterInTabOrder`。
- **改用繼承：** 原本複製自 NVDA 的 `createDriverSettings` 已經刪掉，改成覆寫 `updateDriverSettings`：
  1. 先依 `allSupportedSettings` 的標準順序，建立所有控制項。
  2. 每建好一列 driver setting，就接著建立排在它後面的 WorldVoice 控制項，並把 `self.lastControl` 設成這個控制項，讓 NVDA 的 Tab 串接自然接上。
  3. 最後呼叫 NVDA 原本的 `updateDriverSettings`。
- **畫面位置：** NVDA 的 `_createNewControl` 用 `len(sizerDict) - 1` 算插入位置，只計算 driver 列。所以畫面位置還是在最後搬一次，把每一列放在前一個建立的列後面。這一步只改變畫面座標，不改變視窗順序和 Tab 順序。
- **間距（M4，使用者決定要修）：** WorldVoice 自己的列改用 NVDA driver 列的間距 `border=10, flag=wx.BOTTOM`。這兩列下面原本緊貼著下一列，現在多出 10px 的間距。
- **守門測試：**
  - 拿掉比對複製程式碼的 AST 守門測試。
  - 新增指紋，涵蓋 NVDA 的 `_createNewControl`、`updateDriverSettings`、`refreshGui`；原本 `_updateValueForControl` 的指紋保留。
  - 新增結構檢查：`lastControl` 的串接、`makeSettings` 先呼叫 `updateDriverSettings`、`StringDriverSettingChanger` 的呼叫，以及 `BoxSizerHelper` 對第一個項目不加間隔的規則。
- **測試用的假物件：**
  - 每個父視窗都記錄子視窗的建立順序，用來代表 HWND 的兄弟順序；Tab 順序另外記錄。
  - 標籤視窗建立在控制項前面。
  - `Sizer.Insert` 的索引超出範圍，或 `MoveAfterInTabOrder` 的對象不是兄弟視窗時，會直接報錯。
- **不變的部分：**
  - 目前不是 WorldVoice 時，不建立也不儲存這兩項（N5）。
  - 已經被刪除的控制項視為不存在（I1）。
  - `depends_on` 的啟用規則、存檔和取消的行為都不變。
  - 切換語音時，語速加倍和抑揚頓挫仍然出現在原本的位置。

## 2. 驗證（`master` `971b847`，Linux，`ref/nvda` 是 `7d25bc76e`）

| 項目 | 結果 |
| --- | --- |
| `python3 -m pytest -q tests` | 2110 passed、0 skipped（基準 `c6a71e4`：2084） |
| `prek run --all-files` | 全部 Passed |
| `git diff --check` | 沒有輸出 |
| 受保護路徑（和 `c6a71e4` 比較）、`git ls-files .../Neural` | 沒有輸出 |
| mutmut（`creation_followers`） | 11 個突變全部被抓到 |
| Fable 驗證 | 把修改換回 `master` 的版本，順序測試的四種情境全部失敗；Fable 自己植入的 12 個突變抓到 10 個，另外 2 個和原本的程式等價 |

**這次沒有打包。** 先前打包給使用者的測試版本都是在這次修改之前做的。

## 3. 尚未驗證（Windows／NVDA）

測試用的假物件假設 `MoveAfterInTabOrder` 只改 Tab 順序、不改 HWND 順序。這和 wxWidgets 的實作一致，也符合使用者在 `master` 上觀察到的狀況，但只有在 Windows 上才能真正證實。

1. **物件瀏覽：**
   - 每組位數在數字模式後面，標點停頓字元在標點停頓參數後面。
   - 兩項的標籤都在控制項前面念出。
   - 每組位數是數字微調框，Windows 上由編輯框和上下箭頭兩個 HWND 組成。箭頭可能在它後面多出一個物件；`master` 也是這樣。
2. **Tab 順序：** Tab 和 Shift+Tab 都照設定表的順序。
3. **切換語音：** 切到支援語速加倍或抑揚頓挫的語音時，這兩項出現在原本的位置。
4. **切換合成器：** 依序做 WorldVoice → eSpeak NG → WorldVoice，以及 WorldVoice → WorldVoice（在合成器對話框直接按確定）。每次的順序都正確，log 沒有錯誤。
5. **其他合成器：** 不顯示 WorldVoice 的控制項，也不儲存它們。
6. **間距：** 每組位數、標點停頓字元下面有 10px 的間距，和 NVDA 的列一致。

## 4. 使用者還沒確認、使用者看得到的預設

1. **畫面搬移：** 仍然保留一次只影響畫面版面的搬移（`_placePipelineRows`），使用者看不出差別。
2. **合成的設定表：** 如果設定表的第一項不是 driver setting，它會建立在所有 driver 列之後、NVDA 自己的控制項之前。實際的設定表已經被守門測試禁止這種情況，只有合成的設定表會遇到。

## 5. Commit

`git log --reverse --format='%h %s' c6a71e4..971b847`

- `adc7259` docs: specify creating the Voice panel controls in table order
- `86375c2` docs: plan the Voice panel creation order change
- `9568631` feat: list the Voice panel controls to create after each driver setting
- `d507454` test: guard the NVDA panel internals the Voice panel relies on
- `b390219` test: model window creation order apart from Tab order in the UI fakes
- `d7b4945` feat: create the Voice panel's WorldVoice controls in table order
- `3f51233` docs: review the Voice panel creation order branch
- `48b1672` test: make the wx fakes fail where wx drops an insert or ignores a move
- `99c04be` test: say the failed-maker test models an idealised NVDA failure
- `e7c84cc` test: pin that the pre-pass leaves the changed setting to NVDA
- `ae943d5` test: guard NVDA's rule that a sizer helper's first item gets no spacer
- `6cd1636` fix: space WorldVoice's Voice panel rows like NVDA's driver rows
- `971b847` docs: record how the Voice panel creation order review findings were fixed
