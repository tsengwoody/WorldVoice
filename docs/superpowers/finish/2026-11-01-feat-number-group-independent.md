# 數字模式與每組位數成為獨立設定：交接紀錄

- **日期：** 2026-11-01
- **分支：** `feat/number-group-independent`，以 fast-forward 合進 `master`，合併後是 `420f4a71`（基準 `65856d26`）。
- **流程：** 一般流程（`DEVELOPMENT_WORKFLOW.md` §3）。
- **spec：** `docs/superpowers/specs/2026-11-01-feat-number-group-independent-design.md`
- **plan：** `docs/superpowers/plans/2026-11-01-feat-number-group-independent.md`
- **review：** `docs/superpowers/finish/2026-11-01-feat-number-group-independent-review.md`
  - Fable 5.1 最後 review：Critical 0、Important 0、Minor 3。M1、M2 已修正，M3 不修（原因見第 3 節）。
- **commit 的 sha：** merge 前，分支上的 commit 以 +0000 的日期重建過，所以 review 文件裡引用的 sha（`274b8eb6`..`83e2e705`）和 `master` 上的不同（`5bcfe131`..`420f4a71`）。內容相同：`83e2e705` 和 `420f4a71` 的 tree 都是 `e33581c7`。對照表見第 6 節。
- **舊 spec 的更正：** spec §11 列出的舊決定，已在分支上的 `2fd5fa32`（`docs: mark the number mode and group size decisions corrected by feat/number-group-independent`）用刪除線保留，標註 Corrected by `feat/number-group-independent`（2026-11-01）。這個 commit 和這份交接紀錄都在分支上，還沒有合進 `master`。

## 1. 修改內容

### 1.1 使用者的決定（U1–U10，2026-11-01）

- **U1 兩個獨立的設定：**
  - 數字模式只決定一段數字怎麼念：「不處理」（none）、「數值」（value）、「數字」（number）。「群組」從下拉選單和語音設定環（`nummod`）移除。
  - 每組位數（`group_size`）只決定數字怎麼切：0 或任何正整數，0 表示不分組。
  - 兩者可以任意搭配。每組位數在兩個面板都一律可以編輯（拿掉 `depends_on`），仍然只在面板裡，不進語音設定環。
- **U2 先分組，再由數字模式念每一片：**
  - 每組位數 0：整個數字是一片。
  - 每組位數 N > 0：每段數字從左邊每 N 位切一片（開頭的正負號跟第一片），每個符號自成一片；每兩片之間插入 `NumberBreakCommand`（NB）。
  - 不處理：數字和符號都照原樣（符號不換成名稱，交給 NVDA 的符號處理）。數值：數字照原樣，符號念名稱（NVDA 沒有名稱時用原字元）。數字：數字之間用單一空格連接，符號念名稱；每組位數 0 時整個數字是一個 item，和改版前的數字模式完全相同。
  - 不處理＋N > 0 也會分組；不處理＋0 維持原本的直接通過（沒有小數點規則、沒有前後停頓，只有數字語言會包起來）。
- **U3 千分位：** 只有數值模式會先移除合法的千分位逗號，再分組：`1,234,567` 數值＋3 → `123`、NB、`456`、NB、`7`。其他模式不移除。
- **U4 數字前後停頓：** 每組位數 > 0 且數字停頓 > 0 時，不論模式都加；每組位數 0 時一律不加。所以數字＋0 失去前後停頓（`共123元` → 一個 item `共1 2 3元`），數值＋N 多了前後停頓。想要前後停頓又不想切開數字，可以把每組位數設得比數字長。
- **U5 只隔著空白的兩個數字**（`10 20`）：數字停頓 > 0 時，在每個模式、每個每組位數下都保留中間的停頓，和以前一樣。數字模式自己用來連接位數的空格不會被切開。
- **U6 每組位數的設定：** 儲存的 key（`groupSize`）和欄位名稱不變。預設 0（原本 3），最小 0。無效的儲存值（負數、不是整數）讀成預設 0。
- **U7 不遷移：** 儲存的模式 `group` 讀成「數值」；有儲存的每組位數照新規則在任何模式下分組。沒有轉換程式。
- **U8 不變：** 小數點規則跟著模式（不處理沒有）；數字語言的包裝和偵測；數值＋0、不處理＋0 的輸出。
- **U9 使用手冊：** `readme.md` 和 `addon/doc/{ru,uk,zh_CN,zh_HK,zh_TW}/readme.md` 的數字模式、每組位數段落與數字停頓說明已更新；7.0 changelog 不動。
- **U10：** 協調者在 merge 後替舊 spec 加上 Corrected by 註記（`2fd5fa32`，見上方）。

### 1.2 協調者預設（O1–O8）

使用者之後接受了 merge，O1–O8 都沒有更改。

- **O1** 數字停頓 0、每組位數 > 0：片段之間仍放 `NumberBreakCommand(0)`，每一片是一個 item，和以前的群組模式相同。
- **O2** 數字＋0：一個 item 以數字結尾、下一個有聲 item 以數字開頭時，中間保留一個 `NumberItemEdgeBreakCommand`，和以前的數字模式相同（`["10", "20"]` → `1 0`、E、`2 0`；item 停頓 30 時是 `1 0`、B30、`2 0`）。只拿掉數字和文字之間的停頓。
- **O3** 數字＋N：正負號跟第一位數，`-123456` 數字＋3 → `-1 2 3`、NB、`4 5 6`。
- **O4** 每組位數上限 2147483647（`2**31 - 1`），confspec 和 spin 相同；更大的儲存值讀成 0，記一次 debug warning。
- **O5** 標籤仍是「Group size」（zh_TW「每組位數」），「0 表示不分組」只寫在使用手冊。
- **O6** `.po` 不動；msgid `group` 不再使用，下次更新翻譯目錄時會移除。
- **O7** 這個分支不加 changelog 段落。
- **O8** mutmut 只能在 Linux 跑；這次在 Windows 沒有跑，改由 review 手動做突變（見第 2 節）。

### 1.3 使用者會注意到的差別

- 預設（數值、每組位數 0）完全不變。
- 數字模式的使用者升級後，如果沒有儲存每組位數，數字前後不再有停頓；兩個數字仍然不會連在一起。
- 每組位數 > 0 時，每個模式都有以前群組模式的切法和前後停頓；數值模式還會先移除千分位，不處理模式把片段和符號交給 NVDA。
- 以前用群組模式、沒改過大小的使用者，升級後變成單純的數值模式；改過大小的使用者保留那個分組，改用數值模式念（先移除千分位）。

## 2. 驗證

環境：Windows，Python 3.14 venv `D:/NVDA/NVDA_development/.venv-worldvoice`，NVDA 原始碼 `D:/NVDA/nvda`（worktree 的 `ref/nvda` junction，NVDA `master` `0041ab653`）。

| 項目 | 結果 |
| --- | --- |
| `pytest -q tests` | 3623 passed、9 failed、1 skipped（基準 `65856d26`：3375 passed、9 failed、1 skipped）。9 個 failed 都在 `tests/test_generated_unicode_data.py`，是 Windows 換行造成的假象，`master` 上也一樣 |
| prek | Passed |
| Fable 5.1 最後 review | Critical 0、Important 0、Minor 3 |
| 手動突變（review） | 16 個，15 個被測試抓到，1 個等價（M1 的 `edge_before`），那段程式在 M1 修正時已移除 |
| NVDA 的 configobj（review 手動） | `integer(default=0,min=0,max=2147483647)`：0、5、2147483647 通過；2147483648、10^20、-1、`abc`、`3.5`、`group`、空字串都被拒絕；缺 key 讀成 0 |
| mutmut | 沒有跑（Windows，O8） |

Review 的 Minor：

- **M1 已修**（`33653378`，review 文件寫作 `9163cf10`）：數字＋0 的 G2 不再放永遠被合併掉的 `edge_before`，輸出不變。
- **M2 已修**（`d24d682b`，review 文件寫作 `6d50afa8`）：P-U5 拿掉寫死的 `max_examples=300`，改由 Hypothesis profile 決定例子數（deep profile 跑 20000 個通過）。
- **M3 不修：** 建議加一個用真正 configobj 驗證 confspec 的測試。審閱者已用 NVDA 的 configobj 手動驗證，結果和 spec F3 相同；這個測試要依賴 NVDA 的開發 venv，其他環境只會 skip，保證有限。之後如果改寫 confspec 字串，真正 Validator 的行為要再人工確認一次。

## 3. 尚未驗證（spec §9.5，Windows／NVDA）

**未打包，未在 Windows NVDA 上驗證。** 目前沒有測試版本，使用者需要從 `master` `420f4a71`（或之後）自行建置一個 add-on 再測。

1. **M1 語音設定面板（WorldVoice）：**
   - 從「數字模式」按 Tab 到「每組位數」，NVDA 念「Group size spin button 0」。
   - 模式清單只有「不處理、數值、數字」。
   - 切換模式時，「每組位數」都不會變成不可用。
   - 輸入 12，按 Tab 離開，按確定，再打開：顯示 12。
2. **M2 語音流程（Speech Pipeline）面板：** 同 M1；存檔後再打開，數值和語音設定面板一致。
3. **M3 語音設定環：** 「數字模式」依序切換「不處理、數值、數字」，沒有「群組」；環裡沒有每組位數。
4. **M4 從 7.0 升級：**
   - 設定檔有 `numberMode = group`、沒有 `groupSize`：面板顯示數值和 0，數字念成數值。
   - 設定檔有 `numberMode = group`、`groupSize = 4`：面板顯示數值和 4，`12345678` 念成「1234」、停頓、「5678」。
5. **M5 無效的儲存值：** 手動把 `groupSize` 改成 `-1`、`abc`、`3000000000`：WorldVoice 能載入，讀成 0，log 裡有一筆 debug warning；面板顯示 0；存檔後寫入 0。
6. **M6 實際聽（OneCore 和另一個引擎）：**
   - 輸入：`123456`、`1234.5678`、`1,234,567`、`共123元`、`10 20`，以及一段結尾是數字、下一行開頭也是數字的兩行選取。
   - 每個模式各測每組位數 0 和 3，數字停頓 10 和 0。
   - 預期：數字＋0 時，`共123元` 的 `123` 前後沒有停頓；`10 20` 不會聽起來像一個數字。
   - 用其他合成器（eSpeak）、範圍「全部」時，片段以一般的停頓送出。
7. **M7 wx 的範圍：** spin 可以輸入 2147483647，而且停在這個值；兩個面板裡 10 位數上限的寬度和版面正常（目前安裝的 wxPython 4.2.4；之後用 wxPython 4.3.2 的 NVDA 版本再確認一次，見 `ref/nvda/pyproject.toml:29`）。

## 4. 待處理事項

- **7.0 changelog（使用者決定不改）：** `readme.md:92` 和五個翻譯的同一段，7.0 changelog 仍寫「In digit mode and group mode, the number pause now also separates every number from the text next to it」（zh_TW：「數字模式與群組模式的數字前後停頓」）。合併後已經沒有群組模式，數字模式在每組位數 0 時也沒有這個停頓。使用者決定不改這一段。

## 5. Commit

`git log --reverse --format='%h %s' 65856d26..420f4a71`（`master`）

- `5bcfe131` docs: spec number mode and grouping as independent settings
- `215c0671` docs: plan number mode and grouping as independent settings
- `ea71e6c0` feat: add the cut and render steps of a number's pieces
- `0718baf8` feat: make the group size an independent 0..2**31-1 setting
- `5573f30b` feat: group numbers in every number mode and tie edge pauses to the group size
- `080490cd` feat: keep a pause between numbers of two items in digit mode without groups
- `8c62080e` test: pin the independent group size with Hypothesis properties
- `924da044` docs: describe the group size as independent of the number mode
- `8c9de203` docs: review the independent group size before merge
- `33653378` refactor: drop the dead edge_before of number mode without groups
- `d24d682b` test: let the Hypothesis profile set P-U5's example count
- `420f4a71` docs: record the fixes of the group size review

## 6. review 文件的 sha 對照

| review 文件（重建前） | `master`（重建後） |
| --- | --- |
| `274b8eb6` | `5bcfe131` |
| `e08193bc` | `215c0671` |
| `e401c323` | `ea71e6c0` |
| `12893d87` | `0718baf8` |
| `a821f3c7` | `5573f30b` |
| `1bd5a146` | `080490cd` |
| `07fb6fd3` | `8c62080e` |
| `747b9ee2` | `924da044` |
| `bf252ab3` | `8c9de203` |
| `9163cf10` | `33653378` |
| `6d50afa8` | `d24d682b` |
| `83e2e705` | `420f4a71` |
