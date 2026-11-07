# Review：fix/script-digit-language（特定文字的數字交給該文字的語言）

日期：2026-11-07。分支：`fix/script-digit-language`（worktree `/workspace/WorldVoice-script-digit`，`master` `9bc5c8f` → `162d253`，7 個 commit：2 個 `docs:` 規格與計畫、2 個 `fix:`、1 個 `test:`、2 個 `docs:` 手冊與 phase 35 註記）。基準 `master` 3769 passed／0 skipped；分支 3805 passed／0 skipped（+36；分支數字由審閱者在 scratch 複本重跑確認，基準數字取自進度帳本與 plan）。
審閱者：Fable 5.1（唯讀；只新增本檔）。流程：一般流程（DEVELOPMENT_WORKFLOW.md §3.3）。Linux，單一 pytest 行程（沒有安裝 xdist），全程有記憶體監控（MemAvailable < 3 GB 即停）。

依據：

- spec `docs/superpowers/specs/2026-11-07-fix-script-digit-language-design.md`（G1–G2 使用者決定；D1–D3 協調者預設）；plan `docs/superpowers/plans/2026-11-07-fix-script-digit-language.md`（Review Focus 1–5 逐項檢查）；進度帳本 `.superpowers/sdd/2026-11-07-fix-script-digit-language/progress.md`（1 行 `Ruling:`，已評估，見下）；協調者的設計說明 `/workspace/WorldVoice/re.md`。
- 實驗都在 scratchpad 的三個 `git clone` 複本做：`review-head`（`162d253`，全套測試與 prek）、`review-revert`（`162d253`，先換成 `master` 的 `detector.py` 做紅燈驗證，再還原做手動突變與探測）、`review-master`（`9bc5c8f`，對照）。`ref` 以符號連結指到 `/workspace/WorldVoice/ref`。分支 worktree 與主 checkout 沒有被任何指令修改；沒有用 `git stash`。
- 行號以 head `162d253` 為準；`detector:` = `addon/synthDrivers/WorldVoice/languageDetection/detector.py`，`stages:` = `addon/synthDrivers/WorldVoice/pipeline/numberStages.py`，`readme:` = `addon/doc/zh_TW/readme.md`，`t-det:` = `tests/test_language_detector.py`，`t-speak:` = `tests/test_worldvoice_speak.py`。

## 結論

**可以 merge。** Critical 0、Important 0、Minor 4（一個是手冊文字、一個是數位模式的既有限制應在手冊或 spec 多寫一句、一個是拼讀的不對稱、一個是提供者被讀兩次）。沒有和 `master` 相比的回歸：所有改變都只在數字語言為「跟隨前後文語言」（`FOLLOW`）且數字屬於 Common／Inherited 以外的文字時發生，這正是 spec G1 要的；「跟隨主要語言」、指定語言、ASCII 與全形數字、字母的路徑我逐一對照 `master` 跑過，輸出一字不差。§8 限制全部遵守。被殺掉的那個重複實作者所寫的兩個 commit（`0c19401`、`d4e5be3`）內容和 plan Task 2／Task 3 一致，沒有夾帶其他改動。

- **修改的本體（`detector:48-64`、`:70`、`:117-126`）。** 字母原本的「看文字 → `find_language_for_script`」被抽成 `_script_language`，`_language_for_character` 只在 `isdecimal() and not digits_by_script` 時提前回目前語言，其餘字元（含 `FOLLOW` 下的數字）走 `_script_language`。Common／Inherited／未知文字的數字在兩條路都回目前語言（`:52-53`），所以 ASCII 與全形數字在每個模式都和以前相同；`find_language_for_script` 在目前語言涵蓋該文字（`:32-33`）與沒有任何語音涵蓋（`:46`）時都回目前語言，所以尼泊爾文內的數字和「沒裝語音」兩種情況也不變；`SCRIPT_LANGUAGES` 沒有條目的文字（Adlam、N'Ko 的數字）在 `:32` 的 `not candidates` 回目前語言，我用探測確認。`digits_by_script` 在 `add_detected_language_commands` 的第一個 `next()` 讀一次（`:70`），和 settings 一樣；`test_detection_reads_the_number_language_once_per_sequence` 證明一個序列只讀一次。
- **「跟隨主要語言」與指定語言不變。** `detect_with_number_language`（`stages:194-226`）在這兩種模式把每個數字包在 `WVLangChangeCommand` 裡再交給偵測器，包裝內的目前語言就是數字語言，而 `digits_by_script` 為 False 時數字一律留在目前語言（`detector:62-63`）。即使沒有包裝（`supports_roles` 為 False 或單元測試直接呼叫），規則看的是數字語言而不是包裝，`test_other_number_languages_keep_digits_in_the_current_run[main-unwrapped]` 釘住這點。端到端 `["२०८१"]` 在 `main` 下兩個時間點都是 `[(EN, "२०८१")]`，分組 2 與數字停頓下也是 `[(EN,"२०"), "|", (EN,"८१")]`，和 `master` 一字不差。
- **隱藏的指定語言。** `NumberLanguageChoice.spoken`（`voices/numberLanguageChoice.py:41-44`）在儲存的 locale 沒有被提供的語音說時回 `FOLLOW`；驅動把 `self._numberLanguage`（回 `spoken`）同時給偵測器（`__init__.py:287-292`）和 `speechContext()`（`:390`），所以偵測器和包裝階段永遠看到同一個值。`test_a_hidden_number_language_reads_script_digits_as_follow` 把 `VoiceManager.all_languages` 加上 `ne` 但 `languages` 不加，`store("ne")` 被接受而 `spoken` 回 `FOLLOW`，結果是 `[(NE,"२०८१")]`；我讀過 harness 確認它測的真的是「隱藏」而不是指定語言的包裝。
- **和數字階段的互動。** `inject_numbers` 在 `FOLLOW` 下不包裝（`stages:287`），分組與停頓只在數字之間放 `NumberBreakCommand`，偵測器讓非語言指令原樣通過且不重設 `tmp_lang`（`detector:98-99`），所以 `["२", break, "०"]` 只在第一片前插一個 `ne`（Review Focus 1）。`number_wait_factor` 的 `_insert_number_breaks` 把語言指令視為透明（`stages:143-149`），探測 `["२०८१ १२"]` 加數字停頓得到 `[(NE,"२०८१"), "|", (NE,"१२")]`，停頓位置正確。經 NVDA 符號處理（`heard_through_nvda`）的 `"link २०८१."` 在分支上是 `[(EN,"link "), (NE,"२०८१  "), (EN,"dot   ")]`，`master` 是整句英文；NVDA 的正規化不會把天城文數字轉成 ASCII，所以兩個時間點結果一樣。
- **拼讀（`detector:108-135`）。** `FOLLOW` 下數字走 `_script_language`，基準語言是拼讀 locale，和字母一樣；`MAIN` 與指定語言仍走 `_spelling_language_for_digit`（去掉已不可達的 `FOLLOW` 分支與 `current_language` 參數，剩下的邏輯和 `master` 的 `:90-92` 相同）。空白仍回拼讀 locale（Review Focus 3）。`patchedSpeakSpelling`（`__init__.py:360-365`）沒有改。朗讀全文（say-all）走的是同一個 filter／`speak` 路徑，沒有另外的程式碼。
- **阿拉伯文家族。** 探測結果：波斯文字後接擴充阿拉伯－印度數字（`سلام ۱۲۳`，裝 fa）整段 fa；文件標示 fa 的 `abc ۱۲۳` 數字回 fa（基準語言優先於假設語言）；英文後接 `۱۲۳` 只裝 fa 時交給 fa；`abc ١٢٣` 裝 ar 時交給 ar，沒裝阿拉伯文家族語音時不變；文件標示 ar 但沒裝 ar 的 `١٢٣` 留在 ar（和字母一樣）；烏爾都文 `اردو ۱۲` 整段 ur；泰文數字 → th、孟加拉數字 → bn；蒙古文數字 → mn。全部符合 G1 的決定鏈。
- **測試抓得到它聲稱的錯誤。** 把 `master` 的 `detector.py` 放回分支：`t-det` 與 `t-speak` 共 26 個失敗（11 個新的單元案例、`abc-arabic-indic`、4 個拼讀案例、`test_property_letters_go_to_installed_languages`、端到端 FOLLOW／隱藏 locale／數位模式各兩個時間點、端到端 property 兩個時間點），全套其餘 260 個通過。帳本說的「harness 接線拿掉後 4 個失敗」我沒有重做，但 `test_main_keeps_script_digits_in_the_main_voice` 在沒有提供者時偵測器會把 `main` 當 `FOLLOW`，從程式碼可以直接看出會失敗。
- **mutmut 的等價判斷。** 我手動套用帳本列出的三類存活 mutant 各一個（`_covers` 的 `.get(script, ())` → `None`、`find_language_for_script` 的同一處、`_script_language` 的 `"Common"` 拼錯），跑 `t-det` + `t-speak`：三個都全綠，判斷正確（理由見驗證表）。對照組把 `not digits_by_script` 改成 `digits_by_script` 被抓到。帳本沒有把這些存活 mutant 記進 spec，只記在帳本；§7 說「在 spec 或 review 記下」，本檔已記。
- **翻譯與手冊。** 沒有新 UI 字串、沒有動 `.po`；只改 zh_TW readme，和 spec §5 的提案一字不差；用詞（「天城文」「阿拉伯－印度數字」「字元集假設的語言」）和 `nvda.po:193-213` 與 `readme:45`、`:80` 一致。一處可以更準確（M1）。phase 35 spec §6.3 的刪除線只劃在被推翻的那一句，前半句「the branch must stay」對 `main` 與指定語言仍然成立，補的說明也寫明了這點，正確。
- **§8 限制。** 7 個 commit 都是英文 `<type>: <summary>` 加原因，`git log` 內 0 個 `Co-Authored-By`；受保護路徑與 Neural 兩個指令都無輸出；`git diff --check master` 乾淨；prek 8 個 hook 全部 Passed（ruff 0.16.3）；沒有動任何 `driver/`；`languageDetection/` 與 `pipeline/` 沒有 import 任何驅動 package；`.superpowers/` 與 `ref` 都沒有被追蹤；工作樹乾淨。

## Critical

無。

## Important

無。

## Minor

### M1. zh_TW 更新紀錄的條件寫成「若前面沒有同一種文字」，和實際規則「若目前的語言不使用這種文字書寫」不完全相同（`readme:100`；commit `531ef18`）

規則是看目前語言是否涵蓋該文字（`detector:32-33`），不是看前面有沒有同一種文字。兩者在多數情況一致，但例如文件標示為尼泊爾語（`[L("ne_NP"), "२०८१"]`）或主要語音本身是印地語時，前面沒有天城文字母，數字也本來就留在該語言，不會「交給別的語言」；反過來，中文語音後面的 `中文 २०८१` 前面有文字但不是同一種，數字仍會交給 ne。`:42` 的功能說明寫法是正確的（「若目前的語言不使用這種文字書寫」）。建議把 `:100` 的「若前面沒有同一種文字」改成「若目前朗讀的語言不使用這種文字書寫」，兩處用同一種說法，讀者也不用自己對照。純文字，不影響程式。

### M2. 數位模式下 `५.५` 會由三段語音輪流唸，spec 只記在 §2.3，手冊沒有提（`stages:359-363`、`:389`；`t-speak:550-557`；spec §2.3）

我在 `master` 對照過：這個限制是既有的，和這個分支無關。`master` 的 `中文1.5`（數位模式、跟隨前後文）就是 `[(ZH,"中文1 "), (EN,"full stop en 5")]`——符號名稱在偵測前用當時生效的語言命名（`stages:389` 的 `namer(number_language or language)`，`FOLLOW` 下 `number_language` 是 None），之後偵測器再依名稱本身的拉丁字母切回英文，連後面的 `5` 也一起帶走。分支上 `५.५` 變成 `[(NE,"५ "), (EN,"full stop en "), (NE,"५")]`，是同一個限制被天城文數字暴露出來；和 `master` 的 `[(EN,"५ full stop en ५")]`（整個數字交給唸不出天城文數字的英文語音）相比沒有更差，反而兩個數字都唸得出來了，而且第二個 `५` 回到 ne 比 `master` 處理 `中文५.५` 時把第二個 `५` 留在英文更一致。判定：真的是既有限制、不在本次範圍、新規則沒有讓它變差。建議：(a) 在 `readme:100` 的條目最後加一句「數位模式下，數字中的符號名稱仍以前後文語言朗讀」，讓使用者遇到時知道是預期行為；(b) 之後若要處理，可在 `_inject_item_numbers` 的 `FOLLOW` 分支把「整個數字只由一種非 Common 文字的數字組成」的符號改用該文字的語言命名，這是獨立的小修改，不該混進這個分支。

### M3. 拼讀時 Common 數字跟著前一個文字數字的語言走：`"२1"` 整段 ne，`"1२"` 卻拆成 en／ne（`detector:117-126`；`t-det:577-593` 只釘了 `1२`）

這是 G2「混合文字逐字判斷」加上「Common 字元跟隨目前 run」的直接結果，朗讀也一樣（property 的 `["link", "२०८१ 12"]` 例子裡 `12` 由 ne 唸）。行為一致、合乎 spec，但使用者可能覺得不對稱，所以列為未確認的預設（見下）。若使用者不接受，最小的改法是在拼讀（`process_for_spelling`）把 Common 數字的目前語言改成拼讀 locale，不過那會和朗讀的規則分家，不建議在這個分支做。現在只建議在 `test_spelling_script_digits` 多釘一個 `("default", "२1", [("२1", "ne")])` 案例，把這個決定寫成測試。

### M4. 每個語音序列讀兩次 `NumberLanguageChoice.spoken`（`__init__.py:351-358`、`:390`；`detector:70`）

`_detectLanguages` 先經 `speechContext()` 讀一次 `_numberLanguage()`，偵測器的產生器啟動時再讀一次。`spoken` 會走 `manager.languages`（`voices/manager.py:305-306`：對可見語音表分組再排序），成本小，而且拼讀路徑（`detector:110`）原本就這樣讀，spec D1 也是刻意選擇「用偵測器已經有的提供者」，所以不是問題。只記下來：若日後 `languages` 變貴，可以讓 `_detectLanguages` 把 `ctx.number_language` 傳進去，不必改介面。

## Review Focus 逐項

1. **兩個文字數字之間夾非文字指令（`["२", MARKER, "०"]`）：** 偵測器對非語言指令只 `yield` 不重設 `tmp_lang`（`detector:98-99`），所以只在 `२` 前插一個 `ne`。`test_script_digits_go_to_their_scripts_language[other-command-between]` 在 `master` 的 detector 下失敗、分支通過。符合。
2. **同文字的項目之後再來文字數字（`["नेपाल", "२०८१"]`）：** `tmp_lang` 跨項目延續（`detector:94`），第二項的目前語言是 ne，`_covers` 成立，不插第二個指令。`[after-nepali-item]` 通過；這個案例在 `master` 也通過（數字跟隨 run），所以它釘的是「沒有多餘指令」而不是修正本身。符合。
3. **拼讀時文字數字之間的空白（`"२ ३"`）：** 空白回拼讀 locale（`detector:115-116`），兩個數字各自回 ne，`[space-between]` 結果 `[("२","ne"), (" ","en_US"), ("३","ne")]`，和指定語言 `ne` 下既有的行為形狀相同（我在 `master` 探測 `"a२ ३b"` 指定 ne 得到同樣的切法）。符合。
4. **儲存的 locale 沒有語音可說（spoken 為 FOLLOW）：** 見結論第三點；測試在 `master` 的 detector 下兩個時間點都失敗。符合。
5. **數位模式下的 `५.५`：** 見 M2；測試釘住的輸出 `[(NE,"५ "), (EN,"full stop en "), (NE,"५")]` 和我在分支複本探測的結果相同，兩個時間點一樣。符合（限制為既有）。

## 進度帳本的 Ruling

| Ruling | 評估 |
| --- | --- |
| Task 2：`test_spelling_script_digits[locale]` 期望 `[("२","en_US")]` 而不是 plan 寫的 `[("२","en")]` | 合理。`_spelling_language_for_digit("en", "en_US")` 回 `"en"`，但 `process_for_spelling` 只在主要語言改變時切 run（`detector:128`），`primary("en") == primary("en_US")`，所以數字留在 `en_US` 的 run。案例仍釘住「指定語言不會把數字送去 ne」。`master` 的同一輸入也是 `en_US`，沒有行為改變。 |

plan Task 1 Step 1 預告「`("lang","en")` 若和 stub 預設不同要記 Ruling」：實際的拉丁假設語言就是 `en`，測試照 plan 寫，不需要 Ruling，帳本沒有多記，正確。

## 被殺掉的重複實作者寫的兩個 commit

- `0c19401`（Task 2）：只動 `detector.py` 的拼讀段（`_spelling_language_for_digit` 簽章與 docstring、`process_for_spelling` 的分支）與 `t-det` 的拼讀測試（改名 `test_spelling_arabic_indic_digits_follow_the_number_language`、新增 `test_spelling_script_digits` 六個案例、property 的 `"default"` 分支）。和 plan Task 2 Step 1／Step 3 逐項相符，沒有其他檔案。
- `d4e5be3`（Task 3）：只動 `t-speak`：harness 接上 `number_language=synth._numberLanguage`（D2）、`NE = "C:ne"`、四個新測試、端到端 property 加 `"२"`、ne 語音、`run_voice` 與兩個 `@example`。和 plan Task 3 相符；`stage_settings`、`heard`、其他列都沒動。
- 兩個 commit 的訊息都是英文、有原因、沒有 `Co-Authored-By`；commit 之間的 diff 沒有和 plan 無關的行。帳本的 Task 2／Task 3 紀錄（95 passed、191 passed、全套 3795／3805）和 commit 內容對得上。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 全套測試（分支 head） | `review-head`：`python3 -m pytest -q -p no:cacheprovider tests`，記憶體監控 | 3805 passed、0 skipped（139.7 s）；基準 3769／0 |
| prek | `review-head`：`prek run --all-files` | 8 個 hook 全部 Passed，工作樹仍乾淨 |
| 受保護路徑／Neural／diff-check | worktree：§7 的 `git diff --stat master -- …`、`git ls-files …/Neural`、`git diff --check master` | 三個都無輸出 |
| `Co-Authored-By` | `git log --format='%b' master..HEAD \| grep -i co-authored` | 0 筆 |
| 驅動獨立性 | `grep -rn "driver" languageDetection/ pipeline/` 的 import | 0 筆 |
| `ref`／`.superpowers` 未被追蹤 | `git ls-files ref .superpowers` | 無輸出；`git status --short` 乾淨 |
| 測試真的抓得到舊行為 | `review-revert`：把 `origin/master:…/detector.py` 蓋上去，跑 `t-det` + `t-speak` | 26 failed、260 passed；失敗清單和預期的新測試一一對應（見結論） |
| 手動突變：`_covers` `.get(script, ())` → `None` | `review-revert`：sed 套用後跑 `t-det` + `t-speak` | 全綠。等價：`_covers` 只在 `find_language_for_script` 的 `not candidates` 短路之後被呼叫，`script` 一定有條目 |
| 手動突變：`find_language_for_script` `.get(script, ())` → `None` | 同上 | 全綠。等價：`not None` 和 `not ()` 一樣為 True，直接回目前語言 |
| 手動突變：`_script_language` 的 `"Common"` 拼錯 | 同上 | 全綠。等價：Common 字元改走 `find_language_for_script`，`SCRIPT_LANGUAGES` 沒有 `"Common"`，`not candidates` 仍回目前語言 |
| 手動突變（對照組）：`not digits_by_script` → `digits_by_script` | 同上 | 被抓到：27 failed、259 passed |
| `master` 對照：數位模式 | `review-master` 與 `review-revert`（head）各跑同一個探測檔 | `master`：`५.५` → `[(EN,"५ full stop en ५")]`、`中文1.5` → `[(ZH,"中文1 "),(EN,"full stop en 5")]`、`中文५.५` → `[(ZH,"中文५ "),(EN,"full stop en ५")]`；head：`५.५` → `[(NE,"५ "),(EN,"full stop en "),(NE,"५")]`、`中文1.5` 不變、`中文५.५` → `[(ZH,"中文"),(NE,"५ "),(EN,"full stop en "),(NE,"५")]`；`main` 下 `५.५` 兩邊都是 `[(EN,"५ full stop en ५")]` |
| `master` 對照：分組與數字停頓 | 同上，`group_size=2, number_wait=50` 與 `number_wait=50` | head `FOLLOW`：`["२०८१"]` → `[(NE,"२०"),"|",(NE,"८१")]`、`["२०८१ १२"]` → `[(NE,"२०८१"),"|",(NE,"१२")]`；`main` 與 `master` 全部是 EN，形狀相同 |
| `master` 對照：經 NVDA 符號處理 | `heard_through_nvda`，`default` 與 `main` | head `default`：`२०८१` → NE、`link २०८१.` → `[(EN,"link "),(NE,"२०८१  "),(EN,"dot   ")]`、`५.५` → `[(NE,"५.५  ")]`；`main` 與 `master` 全部 EN |
| 偵測器探測（head） | 19 個案例（阿拉伯文家族、泰文、孟加拉、蒙古文、無候選語言的 Adlam／N'Ko、hi+ne 預設、混合、跨項目） | 全部符合 G1 的決定鏈（結論第六點）；`master` 同樣輸入全部留在目前語言 |
| 拼讀探測（head） | `"a२ ३b"`，數字語言 default／main／ne／en | default 與 ne 同形 `[(a,en_US),(२,ne),( ,en_US),(३,ne),(b,en_US)]`；main 與 en 整段 `en_US`；`master` 的 default 整段 `en_US` |
| Hypothesis property 的方向 | 讀 `t-det:792-803`、`:849-877` | `test_property_letters_go_to_installed_languages` 經 `has_script` 也對文字數字斷言「有語音涵蓋就一定在涵蓋的語言」（正向），`test_property_only_script_digits_start_a_detected_run` 斷言反向；兩者合起來才完整，在 revert 下前者失敗 |
| 翻譯用詞 | `grep 假設 nvda.po`、readme `:45`、`:80` | 「天城文字元假設的語言」「阿拉伯－印度數字」「字元集假設的語言」皆為既有用語 |

## 使用者還沒確認的使用者可見預設

- **D1：偵測器讀的是「實際使用的」數字語言。** 儲存的指定語言若目前沒有語音可說，數字行為和「跟隨前後文語言」一樣（文字數字會交給該文字的語言）。
- **D3：拼讀也用同一條規則。** 開啟「處理字元與符號時信任語音的語言」時，拼讀 `२` 會由尼泊爾語／印地語語音唸，拼讀 `abc١٢` 裝了阿拉伯文語音時 `١٢` 由阿拉伯文語音唸。
- **Common 數字跟著前面的文字數字走（M3）。** 同一段裡 `२०८१ 12` 的 `12` 由 ne 唸；拼讀 `२1` 整段 ne，`1२` 卻是 en／ne。
- **天城文假設語言預設 hi。** 同時裝 hi 與 ne（eSpeak 兩個都有）時，單獨的 `२०८१` 由印地語唸，直到使用者在 Unicode 偵測面板選尼泊爾語；回覆回報者時要提醒這個設定（re.md 第四節第 4 點）。
- **阿拉伯字元假設語言預設 ar。** 同時裝 ar 與 fa／ur 時，英文後面的擴充阿拉伯－印度數字（波斯／烏爾都寫法 `۱۲۳`）由阿拉伯語唸，和字母規則一致；只在波斯文／烏爾都文字之後、或文件標示 fa／ur 時才由 fa／ur 唸。
- **數位模式下 `५.५` 三段語音（M2）。** 既有限制，不在本次範圍。
- **已由使用者決定（2026-11-07），列出供對照：** `abc ١٢٣` 裝阿拉伯文語音時切到 ar（G1，推翻 phase 35 §6.3）；`1२3` 逐字判斷為 `1` en、`२3` ne（G2）。

## 未在 Linux 驗證的項目

spec §7.6 的 M1–M3（IBM 英文＋eSpeak 尼泊爾語朗讀 `२०८१`、拼讀 `२`、阿拉伯文語音下的 `abc ١٢٣`）需要在 Windows／NVDA 上做；IBM 驅動對天城文數字是跳過還是唸替代字元也沒有驗證。另外一個值得順手看的情境：若回報者有勾「主要語音引擎一致」而 eSpeak 的尼泊爾語音被隱藏，偵測器仍會把數字（和字母一樣）交給 `ne`，但 `get_voice_name_for_language` 會退回主要語音——這不是這個分支造成的，但會讓修正看起來沒效，回覆時可一併提醒。未打包。
