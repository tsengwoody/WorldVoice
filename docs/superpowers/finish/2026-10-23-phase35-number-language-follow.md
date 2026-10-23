# 階段 35 交接紀錄：數字語言統一處理數字

**分支：** `phase35-number-language-follow`（已 fast-forward merge 到 `master`，`e08abb4`）

**日期：** 2026-10-23

**文件：**

- spec：`docs/superpowers/specs/2026-10-23-phase35-number-language-follow-design.md`
- plan（含 mutmut 與覆蓋率紀錄）：`docs/superpowers/plans/2026-10-23-phase35-number-language-follow.md`
- review 與修正記錄：`docs/superpowers/finish/2026-10-23-phase35-number-language-follow-review.md`

## 內容

- **數字語言三種選項：** `"default"` 改名「跟隨當前文字語言」，是預設，數字跟著前後文字的語言；新增 `"main"`「跟隨文件主要語言」，數字回到基準語言，等於舊的「忽略數字＝關」；指定語言不變。
- **移除「Unicode 偵測」的「偵測語言時忽略數字」**：勾選框、設定鍵 `ignoreNumbersInLanguageDetection`、`DetectionSettings.ignore_numbers`。舊設定檔中的鍵不再讀取，不會出錯。偵測器遇到十進位數字一律留在目前語言。
- **預設行為改變：** 從沒改過設定的使用者，數字由「回到主語言」改為「跟著前後文字」。已寫進英文與 zh_TW readme 的 changelog。
- **不遷移：** 存的值不是 `default`、`main` 或已安裝語音的語言時，存成 `default`。暫時被「保持主語言引擎一致」隱藏的語言會保留，隱藏期間讀作「跟隨當前文字」。這也修好了存了不合法的值時，NVDA 設定環會出錯的問題。
- **數字範圍：** 所有數字處理（數字語言、數字模式、停頓、千分位）都改用 Unicode 十進位數字（Nd），包含全形與阿拉伯－印度數字，不含 `²`、`①`，並保留原字元。
- **拼讀：** 數字的語言照數字語言設定。
- **連字號：** `+`、`-` 緊接在字元後面時算連字號，留在前面的文字，例如 `COVID-19`、`a-1`、`中-1`。兩種數字包裝都適用，和 NVDA 自己判斷負數的規則一致。
- **實作位置：** 數字在偵測前那一刻才包（`pipeline.detect_with_number_language`），包完後去掉沒換語音的命令，並把被切開的字串接回去，NVDA 的符號處理因此看到完整的字串（修正批次 review 的 C1）。
- **已知且接受：** 偵測時間點 after＋指定數字語言時，NVDA 符號名稱裡的數字（例如「H₂O」展開後的「subscript 2」）也會換語音。

## 驗證（Linux）

| 項目 | 結果 |
| --- | --- |
| `python3 -m pytest -q tests`（merge 後 master） | 2589 passed，0 skipped，0 warnings（基準 2413） |
| `prek run --all-files` | 全部 Passed |
| `git diff --check`、受保護路徑、Neural `ls-files` | 皆無輸出；`buildVars.py` 未動 |
| `msgfmt --check` zh_TW | exit 0 |
| 覆蓋率 | `numberLanguage.py`、`pipeline/numbers.py`、`pipeline/__init__.py`、`languageDetection/*` 皆 100% |
| mutmut | 407 個 mutant，381 killed，26 個存活皆為等價變異（理由見 plan） |
| Fable 比對 | 4480 組情境經 NVDA 真正的 `characterProcessing`，差異都屬於使用者決定過的類別 |

## 尚未驗證

未打包，未在 Windows／NVDA 上驗證。需要時從 `e08abb4` 建乾淨的 detached worktree 打包（`DEVELOPMENT_WORKFLOW.md` §6），再逐項確認（spec §11.7）：

1. 語音面板的「數字語言」最前面是「跟隨當前文字語言」（全新設定檔預設選取）與「跟隨文件主要語言」，NVDA 能讀出；設定環的順序相同。
2. 手動把 `numlan = zz` 寫進設定檔：載入不出錯，下拉選單顯示「跟隨當前文字語言」，設定環可切換，儲存語音面板後寫成 `default`。
3. VE、OneCore、eSpeak 語音，分組模式、每組 3 位：`１２３４５` 念成數字（「一百二十三」「四十五」），NVDA 的 Unicode 正規化開或關都試；阿拉伯語音念數字模式的 `٣٤`。
4. 主語音英文、裝有中文語音、開啟偵測：`中文 12` 在「跟隨當前文字」時由中文語音念，「跟隨文件」時由英文語音念；偵測時間點改成 before 再試一次。
5. 數字模式、主語音中文、「跟隨當前文字」，念 `abc 12.5`：記下「點」和 `5` 由哪個語音念（spec §10 的已知限制）。
6. 「Unicode 偵測」面板沒有「忽略數字」，Tab 順序從「拉丁字元假設的語言」開始；仍含 `ignoreNumbersInLanguageDetection = True` 的設定檔開啟不出錯，儲存後該鍵仍留在檔案中。
7. 開啟「信任語音的語言」，拼讀（或逐字閱讀）`中1`：「跟隨當前文字」時兩個字都用中文說明；「跟隨文件」時 `1` 用拼讀的 locale。

## 待使用者確認的預設

- Q11：數字在偵測前那一刻才包（修 C1 的設計調整）。
- M2：暫時被隱藏的數字語言會保留，並仍列在下拉選單中，直到使用者改掉。
- `+` 緊接在字元後面時也算連字號（例如 `中+5` → `中+`／`5`）。
- changelog 用介面上的選項名稱「Ignore numbers when detecting text language」指稱被移除的選項。
