# 數字停頓與標點停頓交接紀錄

**日期：** 2026-10-21

**分支：** `feat/number-and-punctuation-pause`。用 fast-forward merge 進 `master`，merge 後 `master` 在 `a72e982`。

**文件：**
- spec：`docs/superpowers/specs/2026-10-21-feat-number-and-punctuation-pause-design.md`
- plan：`docs/superpowers/plans/2026-10-21-feat-number-and-punctuation-pause.md`
- review：`docs/superpowers/finish/2026-10-21-feat-number-and-punctuation-pause-review.md`（Fable 5.1 審閱：Critical 0、Important 1、Minor 6，全部已修正）

## 1. 修改內容（全部由使用者決定，2026-10-21）

### 1.1 數字停頓（`pipeline/__init__.py`）

- **判斷數字：** `_both_numbers` 改用 `fullmatch`。`"12abc"` 這類「數字開頭、後面接其他字元」的字串，不再算數字。
- **拆數字：** 數字停頓大於 0 時，`number_wait_factor` 依序處理：
  1. 先執行 `_remove_space`。
  2. 拆數字：同一個字串裡，只隔著空白的數字各自拆成獨立項目。
  3. 用 fullmatch 判斷，在相鄰的數字之間插入停頓。
- **拆數字的規則：**
  - **不拆黏住的數字（方案 B）：** 兩個數字中間沒有任何字元時（例如 `"2345-6789"`），兩個都不拆。所以 `"02 2345-6789"`、`"3-1 2"` 維持原樣。
  - **不在不換行空白拆開（Important 1 方案 A）：** 間隔裡只要有 U+00A0、U+202F 或 U+2007，就不拆，所以 `10 000` 維持一個數字。一般空白、tab、換行和全形空白（U+3000）照常拆開。
- **逐位模式：** 每一位數字之間都會停頓。
- **兩位一組模式：** 不管停頓設多少，每兩組之間都插入 `PairNumberBreakCommand(pause)`。設為 0 時，`Pause(0)` 照樣會把 segment 切開。
- **runtime 入口：** `compat/commands.py` 不修改。

### 1.2 標點停頓（`inject_punctuation_pause`）

- **開關關閉：** 原樣回傳。就算開了「移除標點」，也不移除。
- **開關打開：** 每個停頓點都插入 `PunctuationBreakCommand(參數)`。
  - 參數是 0 時也照樣插入，和有沒有開「移除標點」無關。
  - 「移除標點」只決定標點本身要不要保留。
- **標點清單是空的：** 原樣回傳。
- **停頓點的判斷條件：** 和以前一樣，沒有修改。
- **預設標點清單：** 改成空的，不遷移舊設定，也不另外說明（選項 C）。

### 1.3 設定面板

- **開關關閉時停用三個控制項：** 語音管線面板和 WorldVoice 語音面板，「移除標點」、停頓參數、標點清單都會停用。語音面板原本是隱藏，改成停用之後，切換語音時滑桿不會再被 NVDA 重新顯示出來。
- **語音設定環切換後狀態正確：** 從語音設定環切換開關之後，再切換語音，相依控制項的啟用狀態也會正確（`5244c8c`）。
- **語音設定環本身：** 沒有修改。
- **翻譯：** 介面字串沒有新增或修改，不需要更新翻譯。

## 2. 驗證（`master` `a72e982`，Linux，`ref/nvda` = `7d25bc76e`）

| 項目 | 結果 |
| --- | --- |
| `python3 -m pytest -q tests` | 1830 passed、0 skipped（基準 `133cb1e`：1745 passed） |
| `prek run --all-files` | 全部 Passed |
| `git diff --check` | 沒有輸出 |
| 受保護路徑（和 `133cb1e` 比較）、`git ls-files .../Neural` | 沒有輸出 |
| Hypothesis | N1–N8、P1–P5、P4b；深度設定（20,000 個例子）通過 |
| mutmut | 拆數字的相關函式：60 個突變全部抓到。整段 pipeline 存活的 10 個突變都是等價變化，原因記在 plan 裡 |
| review 驗證 | 個別還原每個修正 commit，對應的測試都會失敗；N1、N7 可以分辨方案 A 和 B |

Windows 上的 NVDA、實際音訊和各引擎 SDK 都還沒驗證。

## 2.1 測試版本

| 項目 | 內容 |
| --- | --- |
| 檔案 | `/workspace/WorldVoice-pkg-pauses/WorldVoice-6.2-test-number-punctuation-pause-1-9999.nvda-addon` |
| 來源 commit | `6c5022d`，在 detached worktree 裡執行 `scons version=6.2-test-number-punctuation-pause-1-9999 channel=dev`。`addon/` 的內容和 `a72e982` 相同 |
| 大小 | 1,846,742 bytes |
| SHA-256 | `8748e0a6e94b28c0daec02bdfbddd853e33ae0a1eb6add9714116a57aff982d0` |
| 內容 | 共 121 個項目，ZIP CRC 檢查全部通過，不含 Neural；這次修改的檔案和 commit 逐位元組相同；manifest 的 version 是 `6.2-test-number-punctuation-pause-1-9999`，channel 是 `dev` |
| 包含的修改 | 這次的數字停頓和標點停頓，以及 2026-10-20 的 index space 循環重用與 NVDA stub 修正 |

## 3. 尚未驗證

以下是 spec §9.4 的項目，要在 Windows 上用 NVDA 手動驗證：

1. **數值模式，預設數字停頓：**
   - 朗讀這些字串：`"1 2"`、`"共 12 34 個"`、`"5 -3"`、`"abc1 2def"`、`"12 apples"`、`"02 2345-6789"`、`"10 000"`（千分位用不換行空白）。
   - 可以把數字停頓調大，比較容易聽出差別。
2. **逐位模式：** `"12345"` 每一位數字之間都有停頓。
3. **兩位一組模式，停頓 0 和 50：**
   - `"12345678"` 每兩位唸成一個兩位數。
   - 停頓 0 時，只有 segment 交接的空檔。
4. **標點：** 標點清單設為 `",."`，朗讀 `"Hello, world. Bye."`。
   - 開關打開時，分別試參數 0 和 50、移除開和關。參數 0 時，聽一下切開 segment 的效果。
   - 開關關閉時，結果和原文相同。
5. **語音管線面板：**
   - 用空白鍵切換開關。
   - 開關關閉時，Tab 會跳過那三個控制項。
   - 物件瀏覽時，這三個控制項讀作「無法使用」。
   - 存檔後重新開啟，設定值都還在。
6. **WorldVoice 語音面板：**
   - 項目 5 的每個檢查都再做一次。
   - 開關關閉時切換語音，三個控制項仍然是停用，滑桿位置不變。
   - 從語音設定環（NVDA+Ctrl+方向鍵）切換開關後再切換語音，三個控制項的啟用狀態正確。
7. **範圍「全部」：** 用 eSpeak NG、OneCore、SAPI5 各試一次。兩位一組停頓 0 時的數字、開了數字停頓時的 `"1 2"`，兩組數字或兩個數字都不能黏在一起唸。
8. **升級：**
   - 沒存過標點清單的設定檔，升級後清單是空的，也沒有標點停頓。
   - 存過標點清單的設定檔，升級後保留原本的清單。

## 4. 使用者還沒確認的使用者可見預設

1. **數字停頓：** 數字停頓預設是 10 ms，而且預設開啟。所以同一個字串裡用空白隔開的數字，例如 `2026 10 21`、`0912 345 678`、`Windows 11 22H2`，每一處都會停頓並切開 segment。不另外寫更新說明。
2. **兩位一組：** 預設停頓是 0。每一組數字會各自成為一個 segment；其他語音合成器在範圍「全部」下的效果還沒驗證。
3. **標點停頓點：** 已經存了標點清單、參數 0、沒開「移除標點」的設定檔，每個標點停頓點都會切開 segment（`Pause(0)`）。
4. **預設標點清單改成空的：**
   - 不遷移舊設定。
   - 調過參數或開了「移除標點」、但從沒改過清單的使用者，標點停頓和移除會在沒有提示的情況下失效。
5. **語音設定環：** 沒有修改。開關關閉時，在環上調整「移除標點」和停頓參數，值會存下來，但不會生效。
6. **`pipeline/__init__.py` 加進 mutmut 的 `source_paths`：** 以後跑 mutmut 會一併涵蓋整段 pipeline。

## 5. Commit

`git log --reverse --format='%h %s' 133cb1e..a72e982`

- `9970c40` docs: specify number and punctuation pause changes
- `5f1ddbf` docs: plan the number and punctuation pause changes
- `e6fd0fe` fix: pause only between items that are whole numbers
- `72ce60e` fix: separate number pairs with a pair break even at pause 0
- `1ad4297` fix: let the punctuation switch control pauses and removal together
- `322a66e` docs: record the user's choice of option B for F1
- `3b0622e` test: check the pause stages with Hypothesis
- `de05af2` fix: enable the punctuation controls only while pauses are on
- `31a17b1` fix: disable the voice panel's punctuation controls while pauses are off
- `e78e6ba` feat: start with no punctuation pause characters
- `51becea` feat: pause between numbers separated by spaces within one string
- `be70fb1` test: check the number split with Hypothesis
- `c4f2410` build: run mutmut on the speech pipeline
- `c6bbc48` test: kill the pipeline mutants that tests let through
- `4992663` docs: record the final verification of the pause changes
- `dea8321` docs: review the number and punctuation pause changes
- `0056680` docs: say which punctuation pause an existing break suppresses
- `7af1264` test: pin which pause an existing break suppresses
- `5244c8c` fix: keep the pause controls in step with the switch after a voice change
- `4fdc238` docs: match the spec's zero-wait removal row to the pause-point pieces
- `c321cd4` docs: say the mutmut numbers in the plan belong to one run
- `ecd147a` fix: never split numbers at a no-break space
- `d364318` test: split a free number pair after a glued one
- `a72e982` docs: record how the pause review findings were fixed
