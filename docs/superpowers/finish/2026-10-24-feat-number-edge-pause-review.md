# feat/number-edge-pause Review 紀錄：數字模式與群組模式的數字前後停頓

日期：2026-10-24。分支：`feat/number-edge-pause`（`8612c3d..8eefc59`，13 個 commit：3 個 docs、4 個 feat、1 個 refactor、4 個 test、1 個 docs 執行紀錄），worktree `/workspace/WorldVoice-number-edge-pause`。
依據：

- 規格 `docs/superpowers/specs/2026-10-24-feat-number-edge-pause-design.md`（U1–U5 與 Q1 為使用者決定；O1–O6 為協調者預設；D1–D10 為 spec 撰寫時的預設）
- 計畫 `docs/superpowers/plans/2026-10-24-feat-number-edge-pause.md`（Review Focus 1–5；文末「Execution record」：D9 oracle 3000 例通過、mutmut 182 個 mutant 176 殺 6 存活、5 個由新測試補殺、1 個等價）
- 進度帳本 `.superpowers/sdd/2026-10-24-feat-number-edge-pause/progress.md`（5 個 `Ruling:`）
- NVDA 來源 `ref/nvda/source/speech/speech.py`（`processText` 的 `strip()`）、`speech/commands.py`（`BreakCommand` 無 `__slots__`、`__eq__` 只比 type 與 time）、`speechXml.py:256-258`（依類別名稱找轉換器）
- `DEVELOPMENT_WORKFLOW.md` §3.3、§7、§8

流程：審閱者 Fable 5.1，唯讀。測試、還原探針、與 `master` 的 oracle 比對都在 scratchpad 的 `git clone --shared` 複本進行（`ref` 以 symlink 接到主 checkout），審完已刪除。pytest 單一行程，每個長時間的執行外層都有 MemAvailable < 3 GB 就停掉 pytest 的看門狗（全程沒有觸發，起始 6.1 GB）。沒有 push、沒有 stash、沒有動主 checkout、沒有修改分支上的原始碼或測試；本文件是審閱者在任務分支上唯一的 commit。

`file:line` 以 `8eefc59` 為準；`pipeline:<n>` = `addon/synthDrivers/WorldVoice/pipeline/__init__.py:<n>`。

## 結論

Ready to merge：**處理 I1 之後是**（修程式，或由使用者接受並記入 spec 與 readme）。Critical 0、Important 1、Minor 4（Minor 都是文件與 spec 補記）。

- **使用者決定與預設都落實了，而且只落實在 spec 說的地方。**
  - U1／U4／Q1：`edge`／`gap_break` 只在 `mode in ("number", "group") and pause > 0` 時存在（`pipeline:387-390`）；數值模式與「不處理」整個階段不讀 `pause`（`_translate_number` 在 value 模式回傳原字串，`pipeline:339-354`）。
  - U2：停頓時間就是 `settings.scaled_number_wait()`（`pipeline:383`），沒有新設定、confspec 與 `.po` 都沒動（`git diff --stat master -- addon/locale buildVars.py` 無輸出）。
  - U3／O2／D1：左右邊的判斷只看相鄰的文字片段是否有非空白字元（`pipeline:456`、`:466`），不切 item 字串，所以是線性的（Review Focus 3）。
  - U5／O1／O4：`_split_numbers_for_language`（連字號規則）在每個模式切數字（`pipeline:443`），每個數字依序產生左停頓、開包裝、片段、關包裝、右停頓（`pipeline:456-467`）。
  - O3／D6／D10：兩個數字之間只有空白時換成一個 `NumberBreakCommand`，不加 edge（`pipeline:447-449`）；整個階段只有一個 edge 實例與一個 gap 實例（`pipeline:388`）。
  - O5／F3／D2：`NumberEdgeBreakCommand(NumberBreakCommand)`（`pipeline:40-41`），E1 只讓非 edge 的 break 壓掉邊界停頓（`pipeline:672-673`），E2 在含 edge 的 run 只留最長的、同長先留非 edge（`pipeline:697-722`）。沒有 edge 的 run 原物件原順序回傳（`_merged_run` 直接 `return run`，`pipeline:718-719`），所以 M2、P4b 與既有標點測試都不受影響。
  - D3：`_plain_break` 只在 `_is_edge_break` 為真時設 `worldvoice_number_edge`，重複 plain 也保留（`pipeline:891-895`）；AST 守門確認 `BreakCommand`、`SynthCommand`、`SpeechCommand` 都沒有 `__slots__`（`tests/test_pipeline_nvda_ssml.py:90-117`）。
  - D4：`Stage.also_logged_by`、`_run_logged(..., switches)`、`_log_switches` 讓 `LOG_SWITCHES` 與今天完全相同（`pipeline:855-876`、`:913-954`）；`tests/nvda_stubs.py:105-119` 也讀 `also_logged_by`，面板與 confspec 測試（`tests/test_pipeline_panels.py:27-31`）仍通過。
  - D5：點號規則只看 item 文字，不管包裝是否留下（`pipeline:450-454`）；差異是序列裡多一個空白，NVDA `processText` 會 `strip()`（`ref/nvda/source/speech/speech.py:214`），`_remove_space` 在數字停頓 > 0 時也會——**但標點階段在那之前就讀到它，空白列為停頓字元時它就是停頓點（I1）。**
  - O6：偵測器對非語言命令只 `yield`，不碰 `tmpLang`（`languageDetection/__init__.py:173-174`）；`tests/test_worldvoice_speak.py:577-667` 的 36 個 case 顯示 wait 10 的語音與 wait 0（今天的輸出）完全相同，只多了停頓。
- **和 `master` 相比，數值模式與「不處理」在任何停頓下都沒有變化，數字／群組模式在停頓 0 時也沒有——只有一個例外（I1）。** 我把 `8612c3d` 的 `inject_number_language`、`inject_number_mode`、`iter_number_speech_segments_*` 與 `inject_punctuation_pause` 編進分支的 pipeline 模組，用 Hypothesis 比對**整條 `STAGES`**（含標點階段）的輸出：字母表包含 ASCII／全形／阿拉伯－印度數字、正負號、`.,:×`、`_`、CJK、`。，？?()$`、一般／不換行／全形空白、tab、換行；項目含 NVDA 與 WV 的語言命令（含 `None`）、既有 `BreakCommand`、未知命令；roles 開關；數字語言 default／main／en／zh（同一個語音）／fr（沒有語音）；標點停頓六組字元（含空白）、移除開關、數字／項目／中文停頓隨機。1500 例時三條性質都通過；加到 6000 例後，第一條在 `['0.']`＋數值模式＋數字語言 en＋標點字元 `" "` 找到差異：D5 多出的空白被當成停頓點（I1）。把空白從標點字元拿掉後，三條性質各 6000 例全部通過，所以**除了 I1 這一類，沒有其他與 `master` 不同的地方**。第三條性質另外確認：數字／群組模式在停頓 > 0 時，單一 item 的輸出去掉 edge、接回字串、去掉空白後等於 `master`，也就是**只多了停頓，字沒有變**。
- **測試真的抓得到它聲稱的錯誤。** 17 種還原／突變在 scratch 複本上全部變紅，第一個失敗的測試都和該規則對應（表格「還原探針」）。另外以 `HYPOTHESIS_PROFILE=deep` 跑新的六條性質（除 P-E5 自訂 400 例外每條 20000 例）也通過。
- **Review Focus 1–5 都有對應測試，且我確認會變紅：** 1 `test_merge_edge_breaks[shared-instance]`（`tests/test_pipeline_punctuation_pause.py:347`）；2 `test_plain_breaks_mark_only_edge_breaks` 第二段（`tests/test_pipeline_stages.py:597-604`，`marker-off` 探針）；3 `test_a_long_item_of_numbers_stays_linear`（`tests/test_pipeline_number_edges.py:348-356`；我實測 `"a1 " * 5000` 經所有階段 0.09 s、`* 20000` 0.37 s、列入空白字元時 0.12 s，線性，2 s 的上限有 20 倍餘裕）；4 `test_no_edge_break_at_an_item_end_or_before_only_whitespace[blank-*]`（`:261-295`，`D1-*` 探針）；5 `test_a_space_pause_character_meets_an_edge_break`（`:409-416`）。
- **五個 Ruling 都合理**（見下）。
- **翻譯與文件：** 沒有新增或修改的可翻譯字串。EN 與 zh_TW readme 各改一個條目、加一條更新日誌，文字與 spec §6 逐字相同；用 markdown 3.11（scons 用的轉檔器）確認兩份都仍是 `<li>`／`<strong>`，沒有 phase 35 那種清單被吞掉的問題。zh_TW 用詞和介面一致：「數字模式」「群組模式」「數值模式」對應 `.po` 的 `number`／`group`／`value`＝「數字」「群組」「數值」，「不處理」對應 `off`，「數字停頓參數」對應「Number wait factor」。措辭的小建議見 M2。
- **§8：** 13 個 commit 都是 `<type>: <summary>` 英文、內文說明原因、沒有 `Co-Authored-By`；沒有碰 `driver/<Engine>/driver/`、`driver/sonic/`、`script_data.py`、Neural、`buildVars.py`、`addon/locale`（兩個受保護路徑指令都無輸出）；只改 core pipeline 與測試；prek 八個 hook 全數 Passed（ruff 0.16.3）；`git diff --check master` 乾淨。

## Critical

無。

## Important

### I1. D5 的點號空白在「空白列為標點停頓字元」時變成一個新的停頓點：數值模式＋locale 數字語言的使用者會多聽到一個標點停頓

- 位置：`pipeline:450-454`（點號規則不再看包裝是否留下，D5）；`pipeline:614`、`:619-656`（標點階段把 `" ."` 裡的空白當成停頓點）；spec §4.5 D5「Nothing is audible」、§3「anything in value mode (the default) or "none" — unchanged」；被刪掉的 M5 註記 `tests/test_pipeline_pause_properties.py:744-747`（原本記著這個差異）。
- 情境：數值模式（預設）、數字語言是另一個語音的 locale（例如中文主要語音、數字語言 English，WorldVoice 常見的設定）、標點停頓開啟並且把空白列為停頓字元（`readme.md:54` 明說可以，`3c94c12` 剛修好這條路徑）、標點停頓 50 ms。文字 `12. Next`：
  - `master`：語言階段先把數字包起來，數字模式階段看到的是 `"12"` 與 `". Next"` 兩個字串，點號規則不加空白 → `L(en) "12" L(zh) "." " " PB50 "Next"`，聽到「12（英）、句點、停頓、Next」。
  - 分支：點號規則只看 item 文字，先加了空白 → `L(en) "12" L(zh) " . Next"`，標點階段把那個空白當成停頓點 → `L(en) "12" L(zh) " " PB50 "." " " PB50 "Next"`，聽到「12、**停頓**、句點、停頓、Next」。數字停頓 10 時一樣（`" "` 被 `_remove_space` 去掉，PB50 仍在）。
  - `35.`（數字模式、停頓 0 或 10，同設定）：`master` `L(en) "3" NB "5" L(zh) "."`；分支 `… L(zh) PB50 "."`，句點前多一個停頓；數值模式 `"35."` 同理。
  - 我用 oracle 實測確認以上三組（數值 wait 0／10、數字模式 wait 0／10 都是 DIFF），而數字語言 default／main 的同一句 `master` 本來就有這個停頓（`"12 . Next"` 的空白是 `master` 的數字模式階段自己加的），所以差異只出現在包裝被留下來的 locale 情況；標點字元沒有空白時，差異只是序列裡一個不發音的空白（spec 說的那部分是對的）。
  - 這違反 spec 的核心承諾（數值模式在任何停頓下不變；D5「Nothing is audible」），而且落在預設模式；但觸發條件窄（三個設定同時成立＋句點緊接數字），效果是多一個使用者自己設定長度的標點停頓，所以列 Important 而不是 Critical。P8（`test_property_the_number_language_changes_no_words_or_breaks`）抓不到它，因為它「ignores whitespace and runs with the punctuation pause off」；而記著這個差異的 M5 註記在這個分支被刪了。
- 建議（二選一，由使用者定奪；我建議 A 或 B，維持 spec 的承諾）：
  - **A. 讓點號規則回到 `master` 的行為：只有包裝不會留下來時才加空白。** 在 `inject_numbers` 對每個 item 先算包裝會不會被 `deduplicate_language_command` 留下（目標語音 `ctx.voice_name_for_language(number_language) or default_name` 是否不同於語言在力的語音，起點照 `deduplicate_language_command` 的規則：語言在力等於 `ctx.language` 時用 `default_voice_name`），把結果傳進 `_number_item_segments`，`dot=` 為真才加空白。或 **B. 把點號規則改成 `merge_consecutive_strings` 之後的後處理**：對每個合併後的字串，只在同一字串內「`.` 緊接數字片段」處加空白（這正是 `master` 數字模式階段看到的粒度）。A 改動最小；B 不需要模擬去重。兩者都要：把 `tests/test_worldvoice_speak.py:454` 的 `(EN, " .")` 改回 `(EN, ".")`，調整 D5 的測試（`tests/test_pipeline_filters.py:768-773`、`tests/test_pipeline_number_edges.py:144-150`（row 23）、`:330-333`）與 spec §4.5／§5 row 23／§8.1，恢復 P8 的註記，並加一個會先變紅的回歸測試：`["12. Next"]`、數值模式、數字語言 en、標點字元 `" "`、pwait 50 → `"12"` 與 `"."` 之間沒有 `PunctuationBreakCommand`（經 `STAGES`）。
  - **C. 接受這個改變並記錄**（理由：locale 的行為變得和 default／main 一致）。那就要改 spec §3 的「unchanged」列與 D5 的「Nothing is audible」，並在兩份 readme 的標點停頓字元條目補一句「數字後緊接的句點前面也會停頓」，列入下方「使用者還沒確認的預設」。

## Minor

### M1. 被 edge 停頓切出來的整數片段，和相鄰 item 的整數片段之間多了一個數字停頓，spec 沒有記載

- 位置：`pipeline:456-467`（edge 讓數字片段成為 item 尾／頭的獨立字串）與 `pipeline:234-256`（`_insert_number_breaks` 在兩個相鄰的整數 item 之間加 `NumberBreakCommand`）。spec §4.6.4 只寫「單獨成 item 的數字沒有 edge，所以兩者不會相遇」，沒有提到這個新的相遇方式。
- 情境（數字模式、數字停頓 10，roles 開）：NVDA 因為格式變化把一行切成兩個 item，例如 `["第1", "2章"]`（「1」粗體）或 `["a 1", "2"]`。`master` 的輸出是 `第1`、`2章`（兩個 item 之間沒有停頓）；分支是 `第` E `1` **NB** `2` E `章`：edge 把 `1` 與 `2` 切成各自 item 尾／頭的整數，`number_wait_factor` 再在它們之間加一個數字停頓。我用 oracle 實測確認（`['a 1', '2']` → master `['a 1', '2']`、分支 `['a', E10, '1', NB10, '2']`）。聽起來是「1」與「2」之間多了一個 10 ms 的數字停頓，和數字模式本來「數字之間就停頓」的行為一致，而且只在數字／群組模式、停頓 > 0 時發生，所以我認為是可接受的結果，但它是使用者還沒看過的可聽見差異。
- 建議：在 spec §4.6.4 補一句「edge 切出的整數片段若落在 item 尾／頭，`number_wait_factor` 會像對待 `["1", "2"]` 一樣在它和相鄰 item 的整數之間加一個數字停頓」，並在 `tests/test_pipeline_number_edges.py` 的 `ROWS` 加一列 `["第1", "2章"]` 固定下來。不需要改程式。

### M2. readme 措辭：「數值模式與不處理」少了引號；「設為 0 即可關閉」也會關掉數字之間的停頓

- 位置：`addon/doc/zh_TW/readme.md:53`、`:75`；`readme.md:53`、`:75`。
- 情境：zh_TW 條目「數值模式與不處理不加這個停頓」裡「不處理」是模式名稱，但句中連讀起來像「數值模式與（並）不處理」。更新日誌「將數字停頓參數設為 0 即可關閉這個停頓」正確，但同一個參數設為 0 也會關掉 `1 2` 之間與相鄰數字 item 之間的停頓（`number_wait_factor`，`pipeline:224-227`），讀者可能以為只關 edge。EN 同一句（"Set the number wait factor to 0 to turn the pause off"）同樣。
- 建議：zh_TW 改成「數值模式與「不處理」不加這個停頓」（或「數值模式與不處理模式」）；兩份更新日誌補一個括號，例如「（數字之間的停頓也會一起關閉）」／"(this also turns off the pause between numbers)"。文字修改不影響程式。

### M3. `NumberBreakCommand` 的 docstring 兩次說「in number and group modes」

- 位置：`pipeline:35-37`。
- 情境：spec §4.9 要求加上「and between two numbers that only whitespace separates, in number and group modes」，實作照加，但原句結尾已經是「in number and group modes」，整句變成「…in number and group modes, and between two numbers that only whitespace separates, in number and group modes」。
- 建議：合併成一句，例如「Pause between numbers, and, in number and group modes, between the pieces and symbol names of a number and between two numbers that only whitespace separates.」

### M4. spec §3 的「使用者會聽到的變化」漏了兩個 U3／O4 之下會聽見的例子

- 位置：spec §3 表格、§0 F2。
- 情境：(1) 全形句點不在 `SYMBOLS`（`pipeline/numbers.py:11-13`），`１２．５` 在數字模式是兩個數字夾一個「．」文字，所以得到 `１` NB `２` E `．` E `５`：句點前後各一個停頓（`1，2` 那一列只寫了全形逗號）。(2) `C++11`：`NUMBER_RE` 把第二個 `+` 當正號（前一個字元 `+` 不是 `\w`），分支輸出 `C+` E `+1` NB `1`，NVDA 會把 `+1` 讀成「plus 1」；`master` 數字模式是 `C++1` NB `1`。兩者都是使用者已接受的 U3／O4 的直接後果（spec 自己也說「a mark between two numbers is now an item of its own」），只是表格沒列。
- 建議：在 spec §3 補這兩列，不改程式；若使用者覺得 `C++11` 的讀法不好，那是 `NUMBER_RE` 正負號規則（2026-10-23 的決定）的範圍，不在本分支。

## Review Focus 與 Ruling 的評估

| # | 項目 | 評估 |
| --- | --- | --- |
| RF1 | 一個 break 實例跨多個 run | E2 以索引決定（`pipeline:717-722`），`test_merge_edge_breaks[shared-instance]` 固定；合理 |
| RF2 | scope "all" 的 marker 跨多個 handler | `_plain_break` 對已標記的 plain break 再標記一次（`pipeline:891-895`）；`marker-off` 探針變紅 |
| RF3 | 長 item 線性 | 相鄰片段 `.strip()`，不切 item；實測線性（見上） |
| RF4 | 空白 item 與只有空白的 item | 12 個 case（`tests/test_pipeline_number_edges.py:261-295`），`""` 消失與 `master` 相同 |
| RF5 | 空白列為標點停頓字元 | `共 3 章` 在 `3` 後只剩一個 PB50（`:409-416`）；我另外用 roles 關、移除開確認 `共` B*10 `3` B50 `章` |
| Ruling T2 | 參數化 id 改 ASCII | mutmut 第二次收集無法選取被跳脫的非 ASCII id，`tests/test_pipeline_filters.py` 已有同樣註記；合理 |
| Ruling T5-1 | 長 item 測試用 `".,"` 而非 `"., "` | 列入空白後每個 ` a` 都成為停頓點、E2 會正確丟掉 edge，`10000 − 1` 的斷言本來就不可能成立；空白路徑由 RF5 測試覆蓋，而且我實測 `"., "` 也是線性（0.12 s）；合理 |
| Ruling T5-2 | 無停頓測試用每組 2 位 | 每組 3 位時 `123` 只有一組、沒有 break 可檢查；合理 |
| Ruling T6 | 只走 `STAGES` 的 ROWS 在 Task 5 就寫進表 | 資料而已，Task 6 的測試才檢查它們；合理 |
| Ruling T7 | P-E3 用計數而非定位 | 計數＋「沒有兩個 break 相鄰」，位置由 P-E4 與 worked rows 固定；合理 |

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 完整測試（分支 `8eefc59`） | `guard.sh python3 -m pytest -q -p no:cacheprovider tests`（scratch 複本） | **2827 passed、0 skipped**（89.9 s；基準 `master` 2610／0，與實作者回報相同） |
| prek | `prek run --all-files`（scratch 複本，prek 0.4.14、ruff 0.16.3） | 8 個 hook 全數 Passed |
| 空白與受保護路徑 | `git diff --check master`；`git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural`；`git diff --stat master -- buildVars.py addon/locale` | 四個都無輸出 |
| commit 訊息 | `git log master..HEAD --format='%h %s%n%b' \| grep -i co-authored` | 無輸出；13 個 commit 都是英文 `<type>: <summary>` |
| reviewer oracle（與 `master` 整條 `STAGES` 比對） | `8612c3d` 的五個舊函式與舊 `inject_punctuation_pause` 編進分支模組；Hypothesis 三條性質 × 1500 例，再 × 6000 例（字母表與項目種類見結論第二點） | 1500 例：3 passed。6000 例：(1) value／none、任意停頓 0–60、任意序列 **failed**，最小反例 `['0.']`、value、numlan en、標點字元 `" "`（I1）；(2) number／group、停頓 0：passed；(3) number／group、停頓 1–60、單一 item、去掉 edge 接回字串後：passed。把 `" "` 與 `". ,"` 從標點字元拿掉後再跑 6000 例：3 passed |
| I1 的實例確認 | 同一 oracle，`["12. Next"]` value wait 0／10、`["35."]` number wait 0／10，numlan en，標點字元 `" "`，pwait 50 | 四組都 DIFF：分支在 `"."` 前多一個 `PB50`；numlan default 同句 SAME；標點字元 `"."`／`". "` 只差一個空白 |
| 還原探針（17 種，scratch 複本，逐一套用後跑 8 個相關測試檔再 `git checkout`） | `E1-revert`、`E2-off`、`E2-shortest`、`E2-tie-prefers-edge`、`D1-left`、`D1-right`、`gap-rule-off`、`gap-only-ascii-space`、`marker-off`、`also-logged-by-ignored`、`log-switches-drop-also`、`stub-ignores-also-logged-by`、`pause-ge-0`、`value-gets-edges`、`O1-edge-inside-wrapper`、`dot-rule-in-none` | **17／17 變紅**。第一個失敗：rows 38／34／34／`[tie]`／9／9／9／`[no-break]`／`test_other_synths_get_marked_edge_breaks[29]`／`test_a_stage_logs_under_each_of_its_switches[other-only]`／`test_log_switches_list_each_label_once_in_stage_order`／`test_the_log_confspec_has_every_log_switch`／row 25／row 1v／row 2／`test_off_mode_with_a_locale_keeps_the_dots_as_they_are` |
| 新性質測試深跑 | `HYPOTHESIS_PROFILE=deep python3 -m pytest -q tests/test_pipeline_number_edge_properties.py`（每條 20000 例，P-E5 自訂 400 例） | 6 passed |
| 邊角輸入探針（數字模式、停頓 10） | `C++11`、`x -5`、`(-5)`、`$5`、`1\t2`、`1\n2`、`1　　2`、`1 a 2`、`１２３章`、`第３章`、`٣章`、`１２．５`、`3 章`、`中-1`、`a_-5`、`1st`、`12:30`、`v1.2.3`、數字語言 zh／fr、中文空白停頓、項目停頓、`["a 1", "2"]`、`1，2`（roles 開／關、pwait 0）、`1 ，2`、`Is it 5? Yes`、`12,345元`、`第12,345章`、`["1.", "Next"]` | 全部與 spec §4–§5 的規則一致：tab／換行／雙全形空白都是 gap（一個 NB）；不換行空白被 `_remove_space` 去掉；全形與阿拉伯－印度數字有 edge；連字號留在字上；同語音的 locale 與沒有語音的 locale 包裝被去重後仍有 edge；中文空白停頓不受影響；見 M1、M4 的兩個觀察 |
| 長 item 計時 | `"a1 " * 5000`／`* 20000`，標點字元 `".,"`、`"., "`、無 | 0.09 s／0.37 s／0.12 s／0.18 s，線性 |
| readme 轉檔 | `markdown.markdown(text, extensions=["tables"])`（markdown 3.11） | 兩份 readme 改到的條目仍是 `<li>`，更新日誌仍是 `<li><strong>` |
| 記憶體 | 看門狗（MemAvailable < 3 GB 停止） | 沒有觸發；單一 pytest 行程 |

## 使用者還沒確認的使用者可見預設

spec 已標為「Decided by orchestrator…；user may override before merge」或本次審查新發現，使用者尚未逐條確認：

1. **O1**：edge 停頓在語言包裝外側（`第` | L(en) `3` L(zh) | `章`），語音切換後才停。
2. **O2／D1**：只有同一個 item 內的文字才算鄰居。被格式或 IndexCommand 切成 `["第", "3", "章"]` 的數字沒有 edge 停頓（item 之間的停頓交給項目停頓）；數字之後只剩空白到 item 結尾也不加。
3. **O3／D6**：兩個數字之間只有空白（含不換行、全形空白、tab、換行）時只有一個數字停頓，不是兩個 edge。
4. **O4**：數字／群組模式也改用連字號規則，`COVID-19` 聽起來是 `COVID-` | `1` | `9`（連字號留在字尾），`C++11` 是 `C+` | `+1` | `1`（M4）。
5. **D2（E2「最長的贏」）**：標點停頓與 edge 落在同一處只留較長的；標點停頓為 0 ms 時留 edge。數字／群組模式下 `1，2` 的全形逗號變成自己的 item，開啟「移除」時會被移除（今天不是停頓點）；`１２．５` 的全形句點前後各一個停頓（M4）。
6. **D3**：scope "all" 的其他合成器也得到 edge 停頓（plain `BreakCommand` 加 `worldvoice_number_edge` 屬性），`Total. 12` 保有標點停頓。
7. **D4**：記錄面板維持「數字語言」「數字模式」兩個開關，兩個都會記錄合併後的數字階段，列標籤是 `number_mode`。
8. **D5**：數值模式＋locale 數字語言時序列多一個空白（`L(en) "12" L(zh) " . Next"`）。spec 說不發音，但空白列為標點停頓字元時它是一個停頓點（I1）；若選 I1 的 C 案，這就是使用者要接受的可聽見改變。
9. **D8**：「數字停頓參數」的名稱不變，只改 EN 與 zh_TW readme；ru／uk／zh_CN／zh_HK readme 未改。
10. **本次新發現（M1）**：edge 切出的整數片段若在 item 尾／頭，與相鄰 item 的整數之間會多一個數字停頓（`["第1", "2章"]` → `第` | `1` | `2` | `章`）。
11. **F1（使用者已選 A，列出提醒）**：數字／群組模式下 `the 1st item`、`MP3`、`10am`、`Is it 5?` 都會被切開（`1` | `st item`、`MP` | `3`、`5` | `?`），各引擎對切開後片段的讀法要在 Windows 上聽（spec M6）。

## 尚未驗證（Windows／NVDA）

Linux 上只驗證了 pipeline 與 NVDA 的 `speechXml`／`processText` 邏輯；實際音訊、引擎 SDK、OneCore／SAPI5／eSpeak 對 10 ms `<break>` 的處理、以及 F1 的各引擎讀法都沒有驗證。spec §8.6 的 M1–M10 手動項目全部待做；未打包。

## 工作區備註

主 checkout `/workspace/WorldVoice` 在 review 開始前就有的未提交變更，與本分支無關，未動：`M buildVars.py`、`D docs/superpowers/finish_task.md`、`?? DEVELOPMENT_WORKFLOW.md`、`?? diff.md`。

## 修正記錄

修正者：Opus 5.5（實作 agent），2026-10-24。每項先寫會失敗的測試（程式修正）再修；偏離與判斷記在進度帳本的 `Ruling:`。

| 項目 | 處理 | commit |
| --- | --- | --- |
| I1 | 採 A 案：數字階段每個「語言在力」問 `deduplicate_language_command` 本身，開頭包裝會不會留下；只有包裝不會留下（沒有包裝，或 locale 的語音就是當下語音）時才套點號規則的空白，與 `master` 相同。先紅後綠的回歸測試 `test_the_dot_rule_adds_no_pause_point_where_the_wrapper_stays`：`12. Next`（數值模式）與 `35.`（數字模式、數值模式），數字語言 en、中文主要語音、標點字元 `" "`、pwait 50、數字停頓 0 與 10，句點前都沒有標點停頓（6 case）。D5 測試改為「包裝留下／去掉」四個 case（`test_the_dot_rule_spaces_only_numbers_whose_wrapper_goes`），row 23 與 `test_the_dot_rule_with_a_wrapper_and_edges` 回到 `". Next"`，`tests/test_worldvoice_speak.py` 的 `locale-next` 改回 `(EN, ".")`，P8 的 M5 註記恢復；spec §4.5、§5 row 23、§8.1、§8.2、§11 D5 以刪除線保留舊文並標註更正 | `486aa44` |
| I1（oracle） | 審閱者的整條 `STAGES` 對 `master` oracle（含空白、標點字元含 `" "`）需要編入 `master` 已刪除的函式，所以不放進測試組，只在開發時跑：兩條性質各 6000 例、三個 seed 都通過；修正前的程式在 `['0.']`＋數字模式＋en 立即失敗。執行紀錄寫在 plan 的 Execution record | `242d53a` |
| M1 | spec §4.6.4 補記：edge 切出的整數落在 item 尾／頭時，`number_wait_factor` 會在它和相鄰 item 的整數之間加數字停頓；`ROWS` 加 `m1-items`（`["第1", "2章"]` → `第` E `1` NB `2` E `章`），固定現有行為 | `e5d012d` |
| M2 | zh_TW readme 改為「數值模式與「不處理」不加這個停頓」；兩份更新日誌補上「（數字之間的停頓也會一起關閉）」／"(this also turns off the pause between numbers)"；markdown 3.11 轉檔仍是 `<li><strong>` | `7195c75` |
| M3 | `NumberBreakCommand` docstring 合併成一句，只說一次 number and group modes | `f7f12ef` |
| M4 | spec §3 補 `１２．５`（全形句點前後各一個停頓）與 `C++11`（`C+` \| `+1` \| `1`，屬 2026-10-23 正負號規則的範圍）兩列，不改程式 | `c406fd9` |

修正後驗證（`242d53a`）：完整測試 **2837 passed、0 skipped**（修正前 2827／0；新增 I1 回歸 6、D5 新 case 2、M1 列 2）；`prek run --all-files` 全數 Passed；`git diff --check master` 乾淨；兩個受保護路徑指令與 `git diff --stat master -- buildVars.py addon/locale` 都無輸出。未打包、未在 Windows／NVDA 驗證。
