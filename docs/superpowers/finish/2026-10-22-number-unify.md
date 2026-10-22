# 數字處理統一：交接紀錄

- **日期：** 2026-10-22
- **分支：** `feat/number-unify`，以 fast-forward 合進 `master`，合併後是 `3f09600`。
- **spec：** `docs/superpowers/specs/2026-10-22-feat-number-unify-design.md`
- **plan：** `docs/superpowers/plans/2026-10-22-feat-number-unify.md`
  - 13 個 task 分成 3 批（5／4／4）。
  - 每一批的 review 和最後的 review 都由 Fable 5.1 進行，這是使用者決定的。
- **review：** `docs/superpowers/finish/2026-10-22-feat-number-unify-review.md`
  - 第 1 批：沒有 Critical，也沒有 Important。
  - 第 2 批：有 1 個 Important（I1），後來使用者決定 B，這個問題就不存在了。
  - 最後：Critical 0、Important 0、Minor 6；M3 延後處理，其餘都已修正。

## 1. 修改內容（都是使用者的決定，2026-10-22）

### 1.1 數字的定義（整條 pipeline 共用）

- **正規式：** 數字、符號、數字。
  - 數字只認 ASCII 的 0～9。
  - 符號是 Unicode P／S 類、碼位在 U+0000～U+00FF（Latin-1）的字元，不含空白、字母、全形或 CJK 標點。
- **正負號：** 開頭的 `+`／`-` 前面不是數字時算正負號，前面是數字時算符號。例如 `5-3` 裡的 `-` 是符號。
- **用到這個定義的地方：** 數字語言、數字模式、數字停頓（拆數字、`_both_numbers`）。

### 1.2 數字模式：不處理、數值、數字、群組

- **不處理（新增）：** 跳過數字模式的處理和千分位移除；數字語言和數字停頓照常作用。
- **數值：** 整串都符合千分位格式時才移除逗號，例如 `12,345,678` → `12345678`。
  - 移除在數字語言之前執行。
  - 沒有獨立的 log 開關，記在數字模式的 log 底下。
- **數字：** 等於每組 1 位的群組。
- **群組：** 每組 2～10 位，預設 3。設定檔存的值是 1 時，讀取後會調成 2。
- **數字和群組兩種模式：**
  - 每段數字從左邊開始分組，正負號跟著第一組。
  - 符號一律單獨成一項。查得到名稱時念 NVDA 的單字元名稱（數字語言的符號表；數字語言設成「預設」時，用當下的語言）。查不到名稱時保留原字元。
  - 數字和符號之間都插入 `NumberBreakCommand(數字停頓)`，停頓為 0 也照樣插入。
  - 不再使用 `CharacterModeCommand`，也不再套用數字符號字典。

### 1.3 移除的設定（不遷移）

- **群組停頓：** 設定、`groupwaitfactor`、`GroupNumberBreakCommand`、面板、語音設定環、翻譯字串。
- **忽略數字間的逗號：** 設定、`cni`、面板、語音設定環、log 開關、翻譯字串。

### 1.4 其他

- **每組位數：** 只有選「群組」時才能編輯。
- **`effective()`：** 拿掉範圍「全部」時，全域停頓會影響逗號移除的耦合。
- **數字停頓與數字語言：** 數字停頓會略過語言切換指令，所以數字語言開啟時，空白分隔的數字之間也有停頓（修好 F4）。
- **不換行空白：** U+00A0、U+202F、U+2007 現在和一般空白一樣會拆開數字。這推翻了 2026-10-21 功能的規則，舊的 spec 用刪除線保留。
- **接受的副作用：**
  - 數值模式（F3）：`192.168.0.1` 的點不再補空格；日期和時間之間會有停頓；數字語言會把 `5-3` 整串包起來。
  - 德文格式 `1.234,567` 會變成 `1.234567`（F7）。
  - 沒有名稱的原字元可能被標點停頓刪掉或加上停頓。若被刪掉，WorldVoice 只保留一個數字停頓（M2）。範圍「全部」時，其他合成器仍會聽到兩個停頓（已知限制）。
- **readme：** 英文和 zh_TW 已更新。zh_HK 只拿掉已移除選項的說明，新功能的說明留給譯者。

## 2. 驗證（`master` `3f09600`，Linux，`ref/nvda` 為 `7d25bc76e`）

| 項目 | 結果 |
| --- | --- |
| `python3 -m pytest -q tests` | 2254 passed、0 skipped（基準 `967944e`：2110） |
| `prek run --all-files` | 全部 Passed |
| `git diff --check` | 沒有輸出 |
| 受保護路徑（和 `967944e` 比較）、`git ls-files .../Neural` | 沒有輸出 |
| `msgfmt --check`（zh_TW） | 通過 |
| mutmut | 數字相關函式：275 個中 274 個被抓到，剩下 1 個等價。`inject_punctuation_pause`：119 個中 110 個被抓到，剩下 9 個都已判定等價 |
| Fable 最後 review | 用 NVDA 真正的符號表做端到端驗證（44 種輸入 × 5 種模式 × 2 種 NVDA 語言 × 3 種數字語言）；Fable 自己的 21 個突變全部被抓到 |

**沒有打包。** Windows 上的 NVDA、實際音訊和各引擎 SDK 都還沒有驗證。

## 3. 尚未驗證（spec §11.5，Windows／NVDA）

1. **M1 符號名稱：**
   - 引擎：OneCore、SAPI5、eSpeak、RHVoice、VE、Cerence，每個都測。
   - 模式：數字模式和群組 3。符號層級：無、部分、全部。
   - 輸入：`12.5`、`5-3`、`1,234`、`12:30`、`2×3`、`45°30`、`192.168.0.1`。
   - 預期：符號都念成 zh_TW 的名稱，不會逐字拼出，也不會被略過。
2. **M2 數字語言：**
   - 數字語言設成 en 時，念 "times"、"degrees"、"dot"。
   - 數字語言設成 zh_TW、主要語言是英文時，念「乘以」、「度」。
   - 數字語言設成「預設」、文字中混有英文時，名稱跟著當下的語言。
3. **M3 數字以外的符號：** `a.b`、`x - y`、`12.` 的念法和 `master` 相同。
4. **M4 數字停頓：** 數值模式、數字語言 en 時，`1 2`、`共 12 34 個` 的數字之間有停頓。
5. **M5 數值模式：**
   - `12,345,678`、`1,234.56`、`-1,234` 都念成一個數值。
   - `3,14`、`1,234,56` 不變。
   - 用德文或法文語音確認已接受的風險。
6. **M6 不處理：** 數字照引擎原本的念法；數字語言和數字停頓照常作用。
7. **M7 升級：**
   - 準備一個 `group_size = 1`、`group_wait_factor = 40`、`ignore_comma_between_number = True` 的設定檔。
   - 確認能正常載入、每組位數顯示 2、已移除的控制項不會出現、log 面板沒有忽略逗號的開關。
8. **M8 範圍「全部」：** 用 NVDA 內建的 OneCore、eSpeak、SAPI5，在群組 3 下念 `123.456`，應聽到「123、停頓、點、停頓、456」，後面的內容不會被截掉。
9. **M9 語音設定環：** 數字模式依序切換「不處理、數值、數字、群組」，環裡沒有群組停頓。
10. **M10 已知代價：** 數字語言設成「預設」、文字是中文、NVDA 介面是英文時，裸代碼 `zh` 會用英文的符號名稱。請記下實際聽到的內容。

## 4. 使用者還沒確認、使用者看得到或聽得到的預設

1. **V5：** 「不處理」（`off`）排在下拉選單第一個，預設仍是「數值」。
2. **Q-A～Q-G：**
   - 數字只認 ASCII。
   - 相鄰的兩個符號各自念名稱。
   - 停頓放在第一個語言切換指令之後。
   - 千分位移除記在數字模式的 log 底下。
   - 千分位的判斷採用嚴格規則。
   - 「不處理」的英文標籤是 `_("off")`。
   - 移除不再使用的程式碼。
3. **`_symbol_locale` 的規則：**
   - 其他合成器使用 `getCurrentLanguage()`。
   - 語言代碼裡的 `-` 換成 `_`。
   - 裸代碼只有在和 NVDA 的基本語言相同時，才補上 NVDA 的國家碼；不相同時用英文名稱（M3、M10）。
4. **群組大小：** 設定檔存的 1 讀取時會當成 2，但檔案裡的值要等存檔後才會改成 2。
5. **語言切換：** 數字停頓現在也會跨過 NVDA 自己插入的 `LangChangeCommand`。
6. **法文名稱：** 法文的符號名稱含撇號，當撇號也被設為停頓標點、而且開啟移除時，名稱可能被切開（已知限制）。
7. **範圍「全部」：** 其他合成器遇到被移除的原字元時，仍會聽到兩個停頓（已知限制）。

## 5. Commit

`git log --reverse --format='%h %s' 967944e..3f09600`

- `6880bcc` docs: specify one number definition, an off mode and value-mode thousands separators
- `c5c9f47` docs: fold the user's F1-F3 answers into the number-unify spec
- `231a775` docs: plan the number-unify feature in three batches
- `802bc86` feat: look up NVDA's name for a symbol in the number's language
- `fff6b7d` feat: share one number definition across the speech pipeline
- `f3b7e60` fix: pause between numbers that a number language wraps
- `a4629a1` refactor: remove the "Ignore commas between numbers" option
- `3921517` feat: drop thousands separators in value mode
- `684ef9f` test: loosen the regex timing bound and compare split items by value
- `485b620` docs: note that the number sign's lookbehind is an equivalent mutant
- `d2e7029` docs: correct the plan's count of number symbols
- `e8e282c` fix: keep a number grouped by no-break spaces whole under a number language
- `3ca2a59` docs: record that no-break-space groups stay whole with a number language
- `01691a6` feat: add an "off" number mode that leaves numbers alone
- `c21cdb4` revert: drop the no-break-space grouping under a number language
- `ee07c55` feat: pause at a no-break space between two numbers
- `58ab03d` docs: record that a no-break space now splits two numbers
- `31ed5eb` feat: read number and group modes with NVDA's symbol names
- `b5b678b` refactor: separate digit groups with the number wait
- `cb0298c` feat: offer group sizes 2 to 10 and read a stored 1 as 2
- `35e7793` fix: keep the next digits off a symbol name after an unnamed symbol
- `700c450` test: pin names to the number language when its voice is missing
- `89a3fe6` docs: correct the no-break-space wording and record unnamed-symbol pieces
- `8fb1492` test: pin the number pipeline's properties across modes and languages
- `b011769` test: keep scope "all" speaking the symbol names as plain words
- `f79a16c` docs: describe the off mode, named symbols and thousands separators
- `b107288` feat: send a symbol without a name as its own item between breaks
- `844d8d2` docs: record that a symbol without a name is its own item
- `e81b278` docs: record the number pipeline's mutation testing result
- `dc003e8` docs: review the number-unify branch
- `adc482b` fix: keep one number break where removal drops an unnamed symbol
- `2c4f5c1` test: pin that no en or zh_TW symbol name holds a number symbol
- `3f5d5c2` docs: drop the removed comma option from the zh_HK readme
- `f6829af` test: say what P8 does not cover
- `3f09600` docs: record how the number-unify review findings were fixed
