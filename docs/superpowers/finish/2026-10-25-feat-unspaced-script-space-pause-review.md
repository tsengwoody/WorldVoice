# feat/unspaced-script-space-pause Review 紀錄：不分詞文字的空白停頓

日期：2026-10-25。分支：`feat/unspaced-script-space-pause`（`21e302b..5e402f9`，9 個 commit：3 個 docs、1 個 refactor、3 個 feat、1 個 test、1 個 docs），worktree `/workspace/WorldVoice-unspaced`。
依據：

- 規格 `docs/superpowers/specs/2026-10-25-feat-unspaced-script-space-pause-design.md`（U1–U8、Q1–Q3 由使用者決定，O1、D1–D6 為預設）
- 計畫 `docs/superpowers/plans/2026-10-25-feat-unspaced-script-space-pause.md`（8 個 task，Review Focus 5 項）
- 進度帳本 `.superpowers/sdd/2026-10-25-feat-unspaced-script-space-pause/progress.md`（8 條 `Ruling:`）
- `DEVELOPMENT_WORKFLOW.md` §3.3、§7、§8

流程：審閱者 Fable 5.1，唯讀。測試、還原探針、mutmut、與 `master` 舊規則的差異比對都在 scratchpad 的 `git clone --shared` 複本進行（`ref` 以 symlink 接到主 checkout），審完已刪除。pytest 單一行程（mutmut 3 個子行程），每個執行外層都有 MemAvailable < 3 GB 就停掉的看門狗（全程沒有觸發）。沒有 push、沒有 stash、沒有動主 checkout、沒有修改分支上的原始碼或測試；本文件是審閱者在任務分支上唯一的 commit。

`file:line` 以 `5e402f9` 為準；`pipeline:<n>` = `addon/synthDrivers/WorldVoice/pipeline/__init__.py:<n>`；`spec:<n>` = 規格檔的行號。

## 結論

Ready to merge：**是**。Critical 0、Important 0、Minor 4（M1 是實作者標記的判斷項目，建議接受並補 spec 文字；M2 是 readme 一句話；M3、M4 不必改程式）。

- **規則落實正確，而且只在 spec 說的地方。**
  - 分類（`pipeline:599-617`）：`UNSPACED_SCRIPTS` 正是使用者的八個 script（U3）；`_UNSPACED_COMMON` 的 13 個 code point 我用 ScriptExtensions-16.0.0.txt 重新推導（Common、類別 Lo／Lm／Sk、Script_Extensions 只含八個不分詞 script），**與 D1 完全一致**；五個注音調號的 Script_Extensions 確認是 {Bopo, Latn}（F2、Q1）。
  - 判斷（`pipeline:620-632`）：`end == len(text)` 先擋掉結尾的 run；往左只跨過 `Inherited`，遇到空白（Common）就停，所以 `中 ́ 文` 兩個 run 都不停（O1）；右鄰不跨 Inherited，`中 ゙か` 不停。`start == 0` 時 `base = -1`，直接回 False。
  - 階段（`pipeline:635-661`）：一次呼叫只建一個 `BreakCommand`；wait ≤ 0 原樣 `yield from`，物件不變；非字串命令原樣通過；停頓前的文字永遠非空（左基底就在裡面），最後一段只在非空時送出。空字串 `""` 不產生任何項目，與 `master` 的 `_split_by` 相同。
- **與 `master` 相比沒有回歸。** 只含 U+4E00–U+9FA5 漢字、ASCII、韓文、數字、全形標點與各種空白的字串，我把 `master` 的 `_CH_SPACE_RE` 切法寫成 oracle，用 Hypothesis 3000 例 × 2 個 seed 比對新階段的輸出，**逐項相同**（含停頓時間）。P3（新規則是舊規則的超集合）在分支的 property 測試裡也有。數值模式與「不處理」下整條 `STAGES` 對拉丁／韓文輸入的輸出與 `master` 相同（P2 的「沒有不分詞字元就原樣輸出」）。
- **spec 符合度。** §5 的 28 列 worked examples 全部在 `test_worked_examples`（33 個 case）；§8.2 每一項、§8.3 P1–P5、§8.4 mutmut 都有對應。Rename 完整：`grep -rni "chinese_\?space\|chinesespace\|CH_SPACE" addon tests` 只剩 `such_space`；`"Chinese"` 在 `addon/`／`tests/` 只出現在 `DEAD_MSGIDS`（本來就該在）與 `test_role_panel_ui.py` 的 locale 顯示名稱（無關）。confspec、ring、兩個面板、Log Record 標籤都由表格衍生，測試裡的預期清單全部改成新名稱。
- **測試真的抓得到它聲稱的錯誤。** 13 種還原／突變在 scratch 複本上全部變紅（表格「還原探針」），第一個失敗的測試都和該規則對應；mutmut 48 個 mutant 的結果與帳本相同（45 殺、2 存活、1 timeout），兩個存活的我逐一看過 diff，確認等價（見表）。
- **邊角輸入：** 41 組（emoji、Ext B／C／H／I、拆開的 surrogate、`\ud800` 單獨一個、純空白、U+3000 頭尾、`\r\n`、U+0085、U+2028、U+1680、U+202F、U+200B、多個合字符號、VS16、泰文聲調、高棉 COENG、緬甸、寮文、泰文 ๆ、U+30FB、右鄰是 ゛／ー、ˇ ˇ、數字、①、〇、々）沒有例外，文字全部保留。
- **效能：** 查表只在空白 run 發生；120 萬字拉丁文 214 ms、108 萬字泰文（48 萬個 run）450 ms、100 萬字「中 文 」（50 萬個 run）931 ms、每個 run 前有 50 個合字符號的 104 萬字 383 ms、一個 50 萬字的合字 run 171 ms。都是線性，D4 不需要。
- **import：** synth 先 import `languageDetection`（`addon/synthDrivers/WorldVoice/__init__.py:28`）再 import `pipeline`（`:38`）；`languageDetection/__init__.py:1-5` 只 import `speech.commands`、`_speechcommand`、`numberLanguage`、`.scripts`，沒有 pipeline，沒有循環。`speechSettingsDialog.py:16` 直接 import `synthDrivers.WorldVoice.pipeline` 時會先跑 synth 套件的 `__init__`，順序同上。harness 把兩個 `languageDetection` 模組一起 pop（D5），`detector_harness.py` 用自己的套件名 `detector_test_worldvoice`，互不影響。
- **翻譯：** 「中日文及東南亞文字空白停頓參數」與既有的「數字停頓參數」「項目停頓參數」「讀出全部停頓參數」「標點停頓參數」同一句型；readme 第 39 行「中日文及東南亞文字空白停頓」放在「項目間停頓、數字間停頓、…」之間讀得順；第 53 行把補充句放在「0 為不停頓。」之後是對的（帳本 Task 6 的 Ruling）。`msgfmt --check` 無輸出。兩份 readme 用 markdown 3.11 轉檔後 `<li>` 59→60、`<li><strong>` 23→24、`<h2>` 9→9，只多了那一條更新日誌。
- **§8：** 9 個 commit 都是英文 `<type>: <summary>`、內文說明原因、0 個 `Co-Authored-By`；沒有碰 `driver/<Engine>/driver/`、`driver/sonic/`、`script_data.py`、Neural、`buildVars.py`；只改 zh_TW 的 `.po`；prek 八個 hook 全數 Passed（prek 0.4.14、ruff 0.16.3）；`git diff --check master` 乾淨。

## Critical

無。

## Important

無。

## Minor

### M1. 數值模式的泰文／寮文／高棉文／緬甸文數字：`๑ ๒` 的停頓從數字停頓變成空白停頓（實作者標記的判斷項目）

- 位置：`pipeline:1094`（空白階段在 `number_wait_factor` 之前）、`pipeline:262-283`（`_insert_number_breaks` 把任何其他命令當成「已經隔開」）；`tests/test_pipeline_unspaced_space.py:301-306`；`spec:145`、`spec:218`、`spec:502`；帳本 Task 4 的第一條 Ruling。
- 情境：數值模式、數字停頓 > 0。`master`：`๑ ๒` 到 `number_wait_factor` 時被 `split_spaced_numbers` 切開，中間是 `NumberBreakCommand(數字停頓)`。分支：空白階段先把空白換成 `BreakCommand(空白停頓)`，數字階段看到中間有命令就不再加 NB，所以只剩空白停頓（我實測：數字停頓 30、空白停頓 10 → `๑ B10 ๒`，`master` 是 `๑ NB30 ๒`；兩者都是 10 時聽不出差別）。ASCII 的 `1 2` 不受影響（數字是 Common），所以同一個設定下 `1 2` 用數字停頓、`๑ ๒` 用空白停頓。
- 評估：**不是 bug，是 F6 的直接結果**，spec §4.4 已經寫明數值模式的 `๑ ๒` 在這個階段停頓、§10 也要求數字階段「不加第二個 break」，實作正是如此；泰文數字在泰文句子裡本來就是泰文文字，用空白停頓合理。只有 `spec:145` 的「Today: no pause」不準確：`master` 在數值模式、數字停頓 > 0 時已經有數字停頓，只是來源不同。
- 建議（二選一，由使用者定奪，**建議 A**）：
  - **A. 接受。** 把 `spec:145` 改成「Today: the number pause (value mode, number pause > 0); no pause otherwise」，§4.4 補一句「so in value mode the space pause replaces the number pause between two script digits」。不改程式。
  - **B. 兩側都是十進位數字的 run 不算空白停頓**，讓數字階段照舊處理：`_pauses_between` 最後加 `and not (text[base].isdecimal() and text[end].isdecimal())`，`test_stages_script_digits` 的數值模式預期改回 `NumberBreakCommand`，另加一列數字停頓 0 時 `๑ ๒` 不停頓。代價：`๑ ๒` 與 `1 2` 一致，但 F6「script 的數字算該 script」就有例外，spec §3、§5 row 25 要改。

### M2. readme 的「標點停頓字元」段落說「每個空白都會停頓」，與 Q3 的行為不完全一致

- 位置：`readme.md:54`（"entering one makes every space a pause point"）、`addon/doc/zh_TW/readme.md:54`（「輸入後每個空白都會停頓」）。
- 情境：標點停頓字元含空白時，兩側都是不分詞文字的空白用的是空白停頓（預設 10 ms），不是標點停頓（Q3 = A，更新日誌有寫）。`master` 對漢字之間的空白已經如此，這句話當時就不完全準確；現在範圍擴大到假名、泰文等，讀者更容易照這句話設定後覺得「泰文的空白沒有用標點停頓」。
- 建議：在該句後補「spaces between CJK and Southeast Asian characters get the space pause instead」／「中日文及東南亞文字之間的空白用的是空白停頓」。只改文件。

### M3. P2 的 oracle 與實作是同一個演算法（不需改）

- 位置：`tests/test_pipeline_unspaced_space_properties.py:61-71`（`may_pause`）與 `pipeline:620-632`。
- 情境：`may_pause` 用同樣的「往左跨過 Inherited、右鄰不跨」寫法，所以 P2 抓得到實作偏離這個公式的錯（mutmut 證明有效），但抓不到「公式本身理解錯 O1」這種兩邊一起錯的情況。O1 的方向由 `test_pauses_between` 的 21 列與 `test_worked_examples` 的 row 19–21 釘住，所以沒有缺口。
- 建議：不必處理。若想讓 oracle 獨立，可以在測試裡改用 `unicodedata.category` 以 `M`／`Cf` 開頭的字元當「附著符號」（測試不受 pipeline 的 `unicodedata` 禁令限制），但 Inherited 與該類別不完全重疊，收益不大。

### M4. D1 的類別規則排除了帶圈、括號與方形的漢字符號（列為未確認預設）

- 位置：`pipeline:600-605`（D1 註解與集合）、`spec:182-187`。
- 情境：ScriptExtensions.txt 裡 Script_Extensions 只有 Hani 的 Common 字元，除了 D1 收的 13 個，還有 ㈠–㈷（U+3220–U+3247，No／So）、㊀–㊰（U+3280–U+32B0）、㋀–㋋（U+32C0–U+32CB）、㋿ U+32FF（令和）、㍘–㍰、㍻–㍿（平成、昭和、㍿）、㏠–㏾、CJK 筆畫 U+31C0–U+31E5 等，類別都是 So／No，D1 的 Lo／Lm／Sk 規則把它們排除：`中 ㈱ 文`、`令和 ㋿` 不停頓（我實測 `中 ① 文` 不停頓，① 的情況相同）。這是 orchestrator 的預設，影響的是少見的符號，兩側文字照常停頓。
- 建議：不改；列入下方「使用者還沒確認」。若使用者要納入，把這些範圍加進 `_UNSPACED_COMMON` 並更新 `test_unspaced_common_is_pinned`。

## 計畫 Review Focus 逐項檢查

| # | 項目 | 結果 |
| --- | --- | --- |
| 1 | U+FFFF 以上的字元與單獨的 surrogate | `test_pauses_between` 有 `\U00020000 か`、`\ud800 中`、`中 \ud800`；`test_worked_examples` 有 Ext B 對；`test_is_unspaced` 有 U+20000、U+1B001；`test_is_not_unspaced` 有 U+D800。我另外探了 Ext C／H／I、emoji、拆開的 surrogate 對，沒有例外。`get_script` 對 surrogate 回 `None`（`scripts.py:6-13`，表裡沒有 D800–DFFF）。 |
| 2 | run 旁的 Inherited 字元 | 一個／兩個合字符號、U+FE00、U+E0100、ZWJ、ZWNJ、字串開頭的符號、run 之後的符號、`中 ́ 文` 都在 `test_pauses_between`；還原探針 P3、P8、P9 分別證明「不跨」「跨到空白」「右鄰也跨」都會被抓到。 |
| 3 | 項目頭尾的 run、純空白、空字串 | ` 中 `、`   `、`""` 在 `test_worked_examples`；P4 證明拿掉 `end == len(text)` 會 IndexError 並被 ` 中 ` 那列抓到。 |
| 4 | 標點停頓字元含空白、移除開關 | `test_stages_space_among_punctuation_characters[False/True]`：泰文空白是 B10，拉丁空白是 PB250，移除時只拿掉拉丁空白。我另外探了 `ภาษา。 ไทย` 配 `"。 "`（`。` 是 Common 所以空白不算，標點階段把 `。 ` 當一個 run）與 U+3000 列入清單的 `中　文`（空白停頓贏），都與漢字在 `master` 的情況一致。 |
| 5 | `languageDetection` 的 import | `test_pipeline_harness_loads_language_detection_fresh` 在 P6（harness 不 pop）時變紅；`tests/test_worldvoice_speak.py:152` 在同一個別名套件下載入真的 `pipeline` 與 `languageDetection`，全綠；循環分析見「結論」。 |
| 另 | script 數字各模式、長文速度 | `test_stages_script_digits` 六種組合；`test_long_text_stays_fast` 18 萬字 < 2 s（實測約 0.09 s）。我另外確認數字／群組模式、數字停頓 0 的 `๑๒๓`、`๑๒๓๔๕๖` 片段之間是 `NumberBreakCommand(0)` 不是空白，空白階段不會在一個數字內部插停頓。 |

## 進度帳本的 Ruling

| Task | Ruling | 評估 |
| --- | --- | --- |
| 1 | 補 spec §8.2 的「global factor 9 → 0」列 | 合理，spec 有、plan 漏；只是釘住不變的公式。 |
| 2 | 新測試 40 個不是 39 個 | 算術修正，無影響；最終 3054 = 2941 + 1 + 40 + 21 + 46 + 5，與我跑的結果一致。 |
| 4 | 數值模式 `๑ ๒` 得到空白停頓而非 NB | 見 M1：與 spec §4.4、§10 一致，建議接受並修 spec 文字；差別只在兩個參數設得不同時。 |
| 4 | 用 `finditer` 小迴圈而非 `_split_by` | 合理：`_split_by` 不能過濾；停頓前文字非空的推論正確（左基底在裡面）；P13 證明最後一段的處理有測試保護。 |
| 4 | 不加 D4 快速路徑 | 合理：我量到 120 萬字拉丁文 214 ms，典型 utterance 遠低於 1 ms。 |
| 6 | zh_TW 補充句放在「0 為不停頓。」之後 | 正確，中文第一句以逗號連到「0 為不停頓。」，插在中間會斷句。 |
| 6 | grep 仍找到 readme.md:44 的 "Chinese text" 與更新日誌的 "as Chinese text already did" | 都是預期的（數字語言的例子、spec 給的句子）。 |
| 7 | 存活的 `while base > 0`／`>= 1` 等價 | 同意：迴圈提前停在 index 0 的 Inherited 字元時，`_is_unspaced` 對它回 False（Inherited 不在兩個集合，pin 測試證明集合全是 Common），與走過頭回 False 相同。timeout 的 `base = 1` 是死迴圈，算被偵測。 |

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 完整測試（分支 `5e402f9`） | `guard.sh python3 -m pytest -q -p no:cacheprovider tests`（scratch 複本） | **3054 passed、0 skipped**（96.5 s；基準 `master` 2941／0） |
| prek | `prek run --all-files`（scratch 複本，prek 0.4.14、ruff 0.16.3） | 8 個 hook 全數 Passed |
| 空白與受保護路徑 | `git diff --check master`；`git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py buildVars.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 三個都無輸出 |
| commit | `git log master..HEAD --format='%h %s%n%b' \| grep -ic co-authored` | 0；9 個 commit 都是英文 `<type>: <summary>`，內文說明原因 |
| 舊名稱 | `grep -rni "chinese_\?space\|chinesespace\|CH_SPACE" addon tests --include=*.py`；`grep -rn -i chinese addon tests` | 前者只剩 `such_space`；後者在 `addon/`／`tests/` 只有 `DEAD_MSGIDS` 的三條、`test_role_panel_ui.py` 的 locale 名稱與內層驅動的語言表，其他語言的 `.po`／readme 依 U7、Q2 保留 |
| 翻譯檔 | `msgfmt --check -o /dev/null addon/locale/zh_TW/LC_MESSAGES/nvda.po` | 無輸出；新 msgstr 與其他四個「…停頓參數」同句型 |
| readme 轉檔 | `markdown.markdown(text, extensions=["tables"])`（markdown 3.11），分支與 `master` 比較 | 兩份都是 `<li>` 59→60、`<li><strong>` 23→24、`<h2>` 9→9 |
| D1 集合 | 用 ScriptExtensions-16.0.0.txt（scratchpad 既有的副本）與 `script_data.py` 重新推導：Common、類別 Lo／Lm／Sk、Script_Extensions ⊆ {Hani, Hira, Kana, Bopo, Thai, Laoo, Khmr, Mymr}；Python unicodedata 16.0.0 | 恰好 13 個，與 `_UNSPACED_COMMON` 相同；ˇˉˊˋ˙ 的 Script_Extensions 都是 {Bopo, Latn}；類別以外的 Hani-only Common 字元見 M4 |
| 與 `master` 舊規則的差異比對 | `master` 的 `_CH_SPACE_RE` 切法寫成 oracle；Hypothesis `st.text` 字母表＝基本漢字、ASCII、韓文、半形／全形數字、`。、「」`、六種空白，長度 ≤ 20，wait 1–60；3000 例 × 預設 seed 與 seed 7 | 全部逐項相同（含停頓時間） |
| 還原探針（scratch 複本，逐一套用後跑 5 個相關測試檔 `-x`，再 `git checkout`） | P1 `_UNSPACED_COMMON` 不算；P2 調號不算；P3 不跨 Inherited；P4 拿掉 `end == len(text)`；P5 `UNSPACED_SCRIPTS` 去掉 Thai；P6 harness 不 pop `languageDetection`；P7 用 `master` 的漢字 regex 找 run；P8 往左也跨空白；P9 右鄰也跨 Inherited；P10 每個 run 新建一個 BreakCommand；P11 wait 0 不再原樣；P12 `effective(False)` 不歸零；P13 沒有停頓的項目被丟掉 | **13／13 變紅**。第一個失敗：`test_every_listed_character_is_unspaced`／同左／`test_pauses_between[が か]`／`test_pauses_between[ 中 ]`（IndexError）／`test_unspaced_scripts_are_the_users_list`／`test_pipeline_harness_loads_language_detection_fresh`／`test_worked_examples[かな カナ]`／`test_pauses_between[中 ́ 文]`／`test_pauses_between[中 ゙か]`／`test_several_runs_reuse_one_break`／`test_wait_zero_yields_the_same_objects`／`test_effective_matches_the_old_synth_scoping`／`test_worked_examples[hello world]` |
| mutmut | `guard.sh mutmut run --max-children 3 '*x__is_unspaced*' '*x__pauses_between*' '*x_inject_unspaced_script_space_pause*'`（第二個 scratch 複本，測試選擇縮到六個 pipeline 測試檔，`mutants/` 已刪） | **48 個 mutant：45 殺、2 存活、1 timeout**（`_is_unspaced` 7／7、`_pauses_between` 23：20 殺 + 2 存活 + 1 timeout、階段 18／18），與帳本相同；存活的 `while base > 0`、`while base >= 1` 經 `mutmut show` 確認等價（見 Ruling 表） |
| 邊角輸入探針（41 組，`inject_unspaced_script_space_pause`，wait 20） | emoji 左／右、Ext B＋C、Ext H、Ext I、拆開的 surrogate 對、`\ud800`、`" "`、`　`、`　中　`、`\r\n中\r\n文\r\n`、U+0085、U+2028、U+1680、U+202F、U+200B 前後、`́ ́`、`中́́́ ́文`、`中️ ️文`、`゙゙゙ か`、`ก่ ไ`、`ภาษาํ ไทย`、高棉、緬甸、寮文、`ต่างๆ นานา`、`中 ・ 文`、`中 ゛か`、`中 ー文`、`ー ー`、`ˇ ˇ`、`ㄅ ˙`、`中 1 文`、`中 ① 文`、`中 〇 文`、`中 々 文`、`あ゙ か`、`中x中x中 文` | 沒有例外；每組輸出接回等於輸入；停不停都符合 §4 的規則（`\r\n中…文\r\n` 中間停、頭尾不停；U+0085／2028／1680／202F 都是 `\s` 所以停；U+200B 不停；`中 ゛か`、`中 ー文`、`ˇ ˇ`、`ㄅ ˙` 停；`中 〇 文`、`中 々 文` 停兩次） |
| 整條 `STAGES` 探針（21 組，roles 開／關各一次） | `๑ ๒` 數值模式（數字停頓 10／30、空白 10／0）、`ภาษา ๑ ไทย` 三種模式、`๑๒๓` 與 `๑๒๓๔๕๖` 數字／群組模式停頓 0、`1 2`、`中 1 2 文` 數值／數字模式、item 10 的 `["中 文", "か な"]`、`["中", "か"]`、`。` 移除、空白移除、`"。 "`、U+3000 列入清單、`第3 章` 數字／數值模式、`[WVLangChange("ja"), "かな カナ"]` | 與 spec §4.4 一致：數字停頓 > 0 的數字／群組模式先由 `inject_numbers` 處理（E／NB），空白階段不再加；roles 關時只是 plain `BreakCommand`，時間相同；M1 的情況見該項 |
| 速度（`inject_unspaced_script_space_pause`，wait 10） | 120 萬字 `hello world `；108 萬字 `ภาษา ไทย `；100 萬字 `中 文 `；(`中` + 50 個 U+0301 + 空白) × 2 萬；`中` + 50 萬個 U+0301 + ` 文`；96 萬字拉丁／漢字混合 | 214／450／931／383／171／326 ms；查表只在 run 發生，往左的走訪以合字 run 為界，線性 |
| 記憶體 | 看門狗（MemAvailable < 3 GB 停止） | 沒有觸發 |

## 使用者還沒確認的使用者可見預設

這些是規則的直接結果或本次審查量到的可聽見差異，使用者可能還沒逐條聽過：

1. **數值模式的 script 數字**（M1）：`๑ ๒` 之間是空白停頓（預設 10）而非數字停頓；兩個參數相同時聽不出差別。`ภาษา ๑ ไทย` 在數值模式也會在數字前後各停一次（`master` 完全不停）。
2. **數字／群組模式、數字停頓 0**：`๑ ๒` 之間現在有空白停頓 10（`master` 沒有）；`๑๒๓` 內部沒有空白停頓。
3. **右鄰是 Common 的假名符號或注音調號**：`中 ゛か`、`中 ー文`、`中 ˇa`（spec row 24d）都停頓；`ー ー`、`ˇ ˇ` 也停頓。
4. **々 與 〇 是 Han**：`中 々 文`、`中 〇 文` 各停兩次（spec §1 列為目標）。
5. **script 自己的標點算該 script**（F6）：`ต่างๆ นานา`（泰文 ๆ）、高棉 ។、緬甸 ။ 旁的空白會停；CJK 的 `。、「」` 與 `・` 不停。
6. **D1 的類別規則**（M4）：㈱、㊀、㋿、㍻ 等帶圈／方形漢字符號不算不分詞字元，旁邊的空白不停。
7. **`\s` 的範圍**：U+0085、U+2028／2029、U+1680、U+202F、不換行空白都算空白 run（與 `master` 相同）；U+200B 不算（spec 非目標）。
8. **readme 的「每個空白都會停頓」**（M2）。
9. **已決定但要提醒的 U8／§3**：調整過的「中文空白停頓參數」回到 10；Log Record 面板這個開關若原本打開會變成關閉（鍵名改了）。

## 尚未驗證（Windows／NVDA）

Linux 上只驗證了 pipeline 的邏輯與 harness 下的 synth 載入；spec §8.6 的 M1–M12（實際語音、Unicode 偵測與泰文語音切換時停頓的位置、面板與 ring 的讀法、從 `chinesespace_wait_factor = 0` 升級、OneCore／SAPI5／eSpeak 的 scope "all"）都沒有做。未打包。

## 工作區備註

主 checkout `/workspace/WorldVoice` 在 review 開始前就有的未提交變更，與本分支無關，未動：`M buildVars.py`、`D docs/superpowers/finish_task.md`、`?? DEVELOPMENT_WORKFLOW.md`、`?? diff.md`。
