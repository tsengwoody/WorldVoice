# Review：fix/leading-punctuation-language（項目開頭的標點跟隨後面的文字）

日期：2026-11-10。分支：`fix/leading-punctuation-language`（worktree `/workspace/WorldVoice-leading-punct`，`master` `6ea5665` → `da1e273`，13 個 commit：5 個 `docs:`、3 個 `feat:`、2 個 `fix:`、3 個 `test:`）。基準 `master` 3808 passed／0 skipped；分支 3940 passed／0 skipped（+132；分支數字由審閱者在 scratch 複本重跑確認）。
審閱者：Fable（唯讀；只新增本檔）。流程：一般流程（DEVELOPMENT_WORKFLOW.md §3.3）。Linux，沒有安裝 xdist；同時最多 3 個 pytest 行程，全程有記憶體監控（MemAvailable < 3 GB 即停，實際最低約 9.2 GB）。

依據：

- spec `docs/superpowers/specs/2026-11-09-fix-leading-punctuation-language-design.md`（`d12f58d`；U1–U9 使用者決定，D1–D13 協調者預設）；plan `docs/superpowers/plans/2026-11-09-fix-leading-punctuation-language.md`（Review Focus 1–5 逐項檢查）；進度帳本 `.superpowers/sdd/2026-11-09-fix-leading-punctuation-language/progress.md`（7 行 `Ruling:`，逐行評估，見下）。
- 實驗都在 scratchpad 的複本做（`git archive` 解出的 `master`、`branch`、`mut` 三份，`ref` 以符號連結指到 `/workspace/WorldVoice/ref`）。沒有用 `git stash`，沒有修改分支 worktree 與主 checkout 的任何原始碼。複本與腳本在審閱結束時已刪除。
- 行號以 head `da1e273` 為準；`detector:` = `addon/synthDrivers/WorldVoice/languageDetection/detector.py`，`breaks:` = `…/pipeline/breaks.py`，`punct:` = `…/pipeline/punctuation.py`，`items:` = `…/pipeline/items.py`，`stages:` = `…/pipeline/numberStages.py`，`readme:` = `addon/doc/zh_TW/readme.md`，`t-det:` = `tests/test_language_detector.py`，`t-speak:` = `tests/test_worldvoice_speak.py`。
- 語音代號：`A` = 英文（主要語音，回報者的 IBM）、`B` = 中文、`C` = 尼泊爾語（eSpeak）、`D` = 印地語；`|` = 停頓；`||` = utterance 界線。

## 結論

**Important 2 項處理（或由使用者裁決）後可以 merge。** Critical 0、Important 2、Minor 6。

- 回報的情境（主要語音英文、數字語言「跟隨前後文語言」或「跟隨主要語言」）在兩個偵測時間點都修好了，spec §3 的每一列我都重跑過，結果和表一致。
- 和 `master` 相比沒有發現回歸：5000 組隨機語料中，各階段輸出的停頓位置、時間與類別（把兩個新子類別還原成父類別後）逐項相同；聽到的文字與停頓位置相同；語音切換次數沒有任何一組變多；「跟隨主要語言」與指定語言下每個數字的語音不變；每個有自己文字的字元語音不變。
- 兩個不變量各找到一個反例，都在項目停頓大於 0 時成立：
  - **I1**：數字語言是「指定語言」（且該語言的語音不是主要語音）時，項目結尾的數字會讓下一個項目的界線消失。這時數字停頓的設定會改變開頭標點的語音（違反 U5 的保證／Invariant 2），而且回報的問題在這個位置沒有修到。
  - **I2**：開頭的標點跨過兩個文件語言指令、第一段語言沒有語音時，語音切換比 `master` 多一次（違反 D6／Invariant 1）。情境很罕見，修法很小。
- 兩個反例都落在 property 測試的生成器沒有涵蓋的地方（M2）。

以下各點是我確認沒有問題的部分：

- **規則本體（`detector:129-265`）。** 每次呼叫建立一個 `_SequenceDetection`，設定與數字語言各讀一次（`detector:83-88`）；`_utterances`（`detector:268-279`）一次緩衝一個 utterance；`plan`（`detector:160-186`）每個 run 只掃一次，`came_before` 為真時只掃自己的項目，為假時掃到 utterance 結尾後不再重掃，所以是線性的。字元的切換比較（`detector:253`）和 `master` 相同。
- **停頓類別的改變不影響下游。** `InternalPunctuationBreakCommand`（`breaks:54`）與 `UnspacedSpaceBreakCommand`（`breaks:63`）都還是 `BreakCommand`／`PunctuationBreakCommand` 的子類別；產品程式碼沒有用確切型別或 `==` 比較停頓（我重新 grep 過 `type(…) is`、`__class__`）；`_merge_edge_breaks`、`_plain_break`、項目階段、分段階段、bridge 都只用 `isinstance` 或 `.time`。沒有角色的合成器仍拿到一般的 `BreakCommand`（`test_the_new_breaks_keep_their_parents` 與既有的 role-less guard）。
- **D13 接線。** `languageDetection/` 沒有 import `pipeline/`；驅動在 `__init__.py:44`、`:293` 把 `is_internal_break` 交給偵測器，兩個時間點共用同一個偵測器實例（`__init__.py:295`、`:339`、`:513`）；拼讀走 `process_for_spelling`（`detector:99-126`），不讀這個檢查，行為和 `master` 相同（D7）。偵測器沒有可變的共用狀態，`_SequenceDetection` 是每次呼叫各自的物件，沒有執行緒問題。把接線那一行拿掉時，lifecycle 測試會失敗（見驗證表）。
- **§8 限制。** 13 個 commit 都是英文 `<type>: <summary>`，`git log` 內 0 個 `Co-Authored-By`；受保護路徑與 Neural 兩個指令都無輸出；`git diff --check` 乾淨；prek 全部 Passed（ruff 0.16.3，`pyproject.toml:84`）；`ref` 沒有被追蹤；readme 只動了 zh_TW；沒有動任何 `.po`。
- **7.1 spec 的刪除線。** `2026-11-07-fix-script-digit-language-design.md` 的 G2、§3 表格列、§7 單元測試列三處都只劃掉被 U9 推翻的部分，補上的說明（項目開頭整段尼泊爾語；項目中間仍跟隨 run）和實際行為一致（`1२3` 我重跑過：`C:'1२3'`；`abc 1२3` 的 `1` 仍是英文）。

## Critical

無。

## Important

### I1. 指定語言的數字在項目結尾時，下一個項目的界線看不見：數字停頓的設定會改變開頭標點的語音，回報的問題在這裡也沒修到（`detector:220-226`、`:181`；`items:44-45`；`stages:287`、`:453-456`；spec D3、D8、§4.4；`t-speak:1307`、`:1344`）

**原因。** 數字語言是指定語言時，`inject_numbers` 在階段裡就把每個數字包進 `WVLangChangeCommand`（`stages:287`、`:453-456`）。項目階段只在兩個**相鄰**的字串之間放項目停頓（`items:44-45`，`_both_text`），數字結尾的收尾 wrapper 夾在兩個項目之間，項目停頓就不放了。這是 `master` 既有的行為（兩邊的階段輸出相同）。偵測器把 wrapper 一律當成「項目繼續」（D3，`detector:223-226`），於是下一個項目不算項目開頭，開頭的標點走舊規則。spec D8 寫的「With the item pause above 0, two items are separated by the item break anyway」在這個情況不成立。

**重現**（主要語音英文，已安裝英、中、尼泊爾語音，數字語言 `zh_TW`，項目停頓 10，兩個時間點結果相同）：

| 輸入與設定 | 聽到的結果 |
| --- | --- |
| `["abc 12", '"नेपाल"']`，分組位數 3，數字停頓 0 | `A:'abc ' B:'12' A:'"' C:'नेपाल"'` |
| 同上，數字停頓 10 | `A:'abc' \| B:'12' \| C:'"नेपाल"'` |
| `["Total 12", '"नेपाल"']`，數值模式、分組 0、數字停頓 10（接近預設值） | `A:'Total' B:'12' A:'"' C:'नेपाल"'` |
| 同一列，數字語言「跟隨主要語言」 | `A:'Total 12' \| C:'"नेपाल"'`（正確） |

- 第一、二列只差數字停頓，引號的語音就不同：U5 的保證（項目停頓大於 0 時，停頓設定不改變任何字元的語音）不成立。
- 第三列是回報者的問題本身：在接近預設的設定下，接在數字結尾項目之後的引號仍由主要語音朗讀。
- 我的隨機語料 7000 組（項目停頓 10 或 30）中有 3 組違反 Invariant 2，全部是這一類（數字語言 `zh_TW` 配主要語音英文，或 `en` 配主要語音中文）。
- 和 `master` 相比不是回歸：`master` 在這些情況引號一律由主要語音朗讀。

**為什麼測試沒抓到。** `test_property_pause_settings_do_not_change_voices` 的數字語言只抽 `default` 與 `main`（`t-speak:1307`），沒有指定語言。

**建議修法（需要使用者選一個，見「未確認的預設」）：**

- (a) **當成限制接受並寫明。** 在 spec U5 與 readme 把它和「項目停頓參數為 0」並列：數字語言為指定語言時，緊接在以數字結尾的項目之後的項目，開頭的標點可能仍由前一個語音朗讀。property 加入指定語言，並排除這個形狀或改成斷言這個限制。不改產品行為。
- (b) **在 `inject_numbers` 保留項目界線。** 這個階段知道數字在項目的開頭或結尾（它在那裡放 `NumberItemEdgeBreakCommand`，`stages:437-438`、`:459-460`）。指定語言且數字停頓不產生邊緣停頓時，可以在同一個位置留下界線，讓項目停頓照常放進去。這會改變 `master` 的停頓位置，等於同時修掉下面的既有問題，所以要使用者決定。
- 只改偵測器做不到：wrapper 在項目裡面和在項目邊界的形狀完全一樣，資訊在 `inject_numbers` 就丟了。

**範圍外的既有問題（供使用者參考）。** 同一個原因讓指定語言下「項目邊緣是數字」的項目停頓消失，例如 `["Total 12", "apples"]` 在 `master` 與分支都是 `A:'Total' B:'12' A:'apples'`，中間沒有項目停頓；「跟隨主要語言」下是 `A:'Total 12' | A:'apples'`。

### I2. 開頭的標點跨過兩個文件語言指令時，語音切換可能比 `master` 多一次（`detector:207-210`；spec D6、D10、§4.3 Invariant 1）

**原因。** `stretch_targets` 對每一段各自判斷：該段生效的語言涵蓋決定字元的文字就保留，否則取 target。三段以上時，中間那段保留自己的語言，前面那段卻取了後面的 target，形成「target、中間語言、target」的來回。

**重現**（主要語音尼泊爾語，已安裝英、中、尼泊爾、印地語音，沒有德語語音；項目停頓 10；兩個時間點相同）：

`[L("de_DE"), '"', L("ne_NP"), "(", L("hi_IN"), "नेपाल"]`

- `master`：`C:'"(' D:'नेपाल'`（切換 1 次；德語沒有語音，引號由主要語音朗讀）。
- 分支：`D:'"' C:'(' D:'नेपाल'`（切換 2 次）。

主要語音是英文時，同一個序列是 `master` `A C D`、分支 `D C D`，次數相同但出現來回。

**影響。** 需要 NVDA 送出文件語言指令（WorldVoice 安裝時預設關閉 NVDA 的自動語言切換），而且連續兩個語言標示的片段都只有標點。實際上很罕見，但它是 Invariant 1 的字面反例，而且修法很小。

**為什麼測試沒抓到。** 偵測器層的 property 數的是主要語言的變化（`t-det:1331`），沒有語音的語言不會併入主要語音；端到端的 property 不抽文件語言指令（`t-speak:1263`）。

**建議修法。** 在 `stretch_targets` 從最後一段往前決定：一旦某一段保留了自己的語言（涵蓋該文字，且和 target 的主要語言不同），它前面的每一段都回 `None`（照舊規則）。只有緊接在決定字元之前、連續不涵蓋的那幾段取 target。補一個三段的單元測試（上面的序列），並把它加成 Invariant 1 property 的 `@example`。M3 的測試缺口會一起補上。

## Minor

### M1. 指定語言、偵測在 NVDA 之後：同一次 `speak()` 的後一個 utterance 若開頭有 NVDA 重播的 wrapper，第一個項目不會套用新規則（`detector:220-226`；spec D3 的前提、F3）

NVDA 的 speech manager 在同一個序列切出下一個 utterance 時，會把還沒回到預設值的參數指令重播在開頭（`ref/nvda/source/speech/manager.py:302-310`）。指定語言的收尾 wrapper 是 `WVLangChangeCommand(語言)`，`isDefault` 為假，所以會被重播。偵測在 NVDA 之後執行時，偵測器看到 utterance 以 `WVLangChangeCommand` 開頭，就設 `came_before = True`、`at_item_start = False`，第一個項目的開頭標點走舊規則。spec D3 假設「偵測器輸入裡的 `WVLangChangeCommand` 只來自數字 wrapper」，F3 自己卻提到重播。

重現（我在 scratch 的執行器裡照 `manager.py` 模擬分割與重播；主要語音英文，數字語言 `zh_TW`）：`["abc 12", EndUtteranceCommand, "(नेपाल)"]`

- 偵測在 NVDA 之後：`A:'abc ' B:'12' || A:'(' C:'नेपाल)'`（沒修到）。
- 偵測在 NVDA 之前：`A:'abc ' B:'12' || C:'(नेपाल)'`。

結果和 `master` 相同，不是回歸。一次 `speak()` 含多個 utterance 的情況不多（文字區塊結尾、設定檔觸發），所以列為 Minor。

建議修法：utterance 裡第一個字串之前的 `WVLangChangeCommand` 不改 `came_before` 與 `at_item_start`。真正的開頭 wrapper 後面緊接數字，數字本身是 stop，會設定這兩個旗標，所以既有行為不變。

### M2. 兩個不變量的 property 生成器比 spec §7.3 與審閱重點要求的窄（`t-speak:1262-1267`、`:1304-1309`、`:1341-1346`、`:1291-1293`；`t-det:1331-1337`、`:1347`）

- 端到端的兩個 property：數字語言只抽 `default`／`main`（沒有指定語言，I1 因此漏掉）；項目只有字串（沒有文件 `LangChangeCommand`、`IndexCommand`、utterance 結尾，I2 因此漏掉）；數字模式固定是數值模式；`max_examples=50`。
- 端到端的切換次數只數非空白字元（`voice_change_count`），spec §3 說「只拿到空白的語音也算一次切換」。我另外用含空白的算法比過，沒有變多的案例，所以只是測試可以更嚴。
- 偵測器層的 Invariant 1 數的是主要語言變化，不是語音變化；數字語言只抽 `default`／`main`。它的策略本身有涵蓋數字 wrapper、文件語言指令、utterance 結尾與每一種停頓。
- 端到端的 harness 沒有模擬 speech manager 的分割與重播，所以兩個 utterance 的情境只在偵測器層測到（帳本的 Ruling 已說明），M1 也因此看不到。

建議：修 I1、I2 時，端到端 property 加入一個指定語言（`zh_TW`）與文件語言指令；Invariant 2 加 `@example(items=["abc 12", '"नेपाल"'], numlan="zh_TW", …)`；`voice_change_count` 改成含空白片段。

### M3. 帳本把 mutant「plan 33」判為等價，實際上不等價（`detector:185`；`t-det:824-829`）

把 `stretch_languages.append(tmp_lang)` 改成 `append(None)` 後，repo 的測試全過，但 `['"', L("ne_NP"), "(", L("hi_IN"), "नेपाल"]`（已安裝英、印地、尼泊爾）的輸出不同：原本 `(` 留在 `ne_NP`，mutant 會在 `(` 前多插一個 `hi_IN`。帳本的理由「從文件指令開始的那一段，涵蓋與否等同 target 是否等於該指令的語言」只對最後一段成立。現有測試最多只有兩段。和 I2 是同一塊程式碼，修 I2 時補三段的測試即可。

我抽查的另外四個等價判斷是對的（見驗證表）。

### M4. zh_TW readme 的文字（`readme:84`、`:96`）

用詞與 NVDA 介面名稱都正確：「標點及符號等級」（NVDA `nvda.po:13907`，去掉加速鍵與冒號）、「一些」「多數」「全部」（`nvda.po:1282`、`:1288`、`:1294`，`msgctxt "symbolLevel"`）、「語言偵測時間點」「跟隨前後文語言」「項目停頓參數」（附加元件 `nvda.po:188`、`:375`、`:430`）。`## 下一版更新` 在 `## WorldVoice 7.1 更新` 之上。有四處建議修改：

1. **更新日誌的「各種停頓設定不再影響標點由哪個語音朗讀」不正確（`readme:96`）。** 在 7.1 停頓設定本來就不影響語音：我在 `master` 跑了 1500 組「全部停頓關閉／隨機開啟」的對照，沒有任何字元的語音改變。這一句會讓使用者以為 7.1 有這個問題。建議整句刪掉。
2. **「停頓設定不會改變任何字由哪個語音朗讀」少了條件（`readme:84`）。** spec U5 的保證只在項目停頓大於 0 時成立。建議和最後一句合併成：「「項目停頓參數」大於 0 時，標點停頓、數字停頓、分段停頓與中日文及東南亞文字空白停頓的設定不會改變各字元由哪個語音朗讀；設為 0 時，緊接在前一個項目之後的開頭標點可能仍由前一個項目的語音朗讀。」I1 若選 (a)，在這裡再補一句指定語言的限制。
3. **「NVDA 已經換成名稱的符號除外」只發生在「在 NVDA 處理語音指令後」（`readme:84`、`:96`）。** 偵測在 NVDA 之前時符號還沒被換成名稱，開頭的引號照樣跟隨後面的文字（等級為「多數」時，名稱「quote」會由尼泊爾語語音朗讀）。建議寫成：「「語言偵測時間點」為「在 NVDA 處理語音指令後」時，NVDA 已經換成名稱的符號不適用（「標點及符號等級」為「多數」或「全部」時較常見），名稱依它本身的文字決定語言。」
4. **精簡與用語。** `readme:84` 一個項目符號裡有八句，建議照同一節「字元集假設的語言」的寫法拆成子項目。「一段朗讀項目開頭」建議改成「每個項目開頭」（`readme:56` 已經說明一段朗讀由多個項目組成）；「一段朗讀的開頭若只有標點」建議改成「一段朗讀開頭的項目若只有標點」。

### M5. 偵測器自己的 utterance 定義沒有防漂移的測試（`detector:268-279`；`pipeline/sequence.py:20-27`）

Ruling「偵測器自己判斷 utterance 結尾」合理（D13 不允許 import）。帳本自己寫了代價：NVDA 新增結束 utterance 的指令時兩處可能不一致。`tests/test_pipeline_segment_pause.py:207-210` 已經有一個測試釘住 pipeline 內部共用同一個 `_ends_utterance`。建議加一個類似的測試：對 `EndUtteranceCommand`、`ConfigProfileTriggerCommand` 與一個其他指令，`_utterances` 的切法和 `_ends_utterance` 的回傳一致。

### M6. `plan` 的 `offset` 參數與相關分支不會被走到（`detector:160`、`:177`）

`plan` 只在項目的第一個字元被呼叫，`offset` 恆為 0（帳本的 mutmut 紀錄也這樣寫，並說是保留當防護）。把 `range(offset if i == index else 0, …)` 改成 `range(0, …)`，測試全過，30000 組偵測器輸出也完全相同。可以拿掉參數，或留著；不影響行為。

## Review Focus 逐項（plan）

1. **空字串與空白在開頭的 run 裡：** `["", '"नेपाल"']` 聽到 `C:'"नेपाल"'`；`[" ", "नेपाल"]`（utterance 開頭，項目停頓 10）聽到 `C:' ' | C:'नेपाल'`，沒有輸出空字串，只有一次切換且在 run 之前。`test_blank_text_joins_the_leading_run` 通過；把開頭規則關掉時整組失敗。符合。
2. **Inherited 記號在項目開頭：** `"́नेपाल"` 聽到整段 `C`；`test_inherited_marks_join_the_leading_run` 涵蓋結合重音與 virama。符合。
3. **一次性的 iterator 輸入含 utterance 結尾：** `_utterances` 逐項讀取、每個 utterance 交出一個 list，指令物件原樣 `yield`（`detector:231`、`:265`）；`test_a_generator_input_with_utterance_ends_keeps_every_command` 通過，設定只讀一次。符合。
4. **很長、只有 Common 字元的 utterance：** 沒有決定字元時 `plan` 只掃一次到 utterance 結尾（`detector:186`），之後每個字元都落在 `run_end` 之前；`test_a_long_common_only_utterance_stays_linear`（20000 個項目，< 2 秒）通過。符合。
5. **「跟隨主要語言」的 wrapper 在開頭 run 旁邊、偵測在 NVDA 之前：** wrapper 物件原樣通過偵測器，`detect_with_number_language` 仍能依 `id()` 黏回項目。`(2024) नेपाल` 聽到 `A:'(2024) ' C:'नेपाल'`（數字留在項目裡）；`नेपाल (2024) नेपाल` 聽到 `C:'नेपाल (' A:'2024) ' C:'नेपाल'`，都和 `master` 相同。符合。

## 審閱者自行驗證的項目

| 項目 | 指令或做法 | 結果 |
| --- | --- | --- |
| 全套測試 | scratch 複本 `branch`：`python3 -m pytest -q -p no:cacheprovider tests`（記憶體監控） | 3940 passed，0 skipped（154 秒） |
| hook | worktree：`prek run --all-files` | 全部 Passed，沒有修改檔案 |
| 受保護路徑、Neural、空白 | DEVELOPMENT_WORKFLOW §7 的兩個指令；`git diff --check 6ea5665..HEAD` | 都沒有輸出 |
| commit 規範 | `git log 6ea5665..HEAD`（grep `co-authored`）、`git ls-files ref`、`git diff --name-only … -- addon/doc readme.md addon/locale` | 0 個 `Co-Authored-By`；`ref` 未追蹤；只有 `addon/doc/zh_TW/readme.md` |
| spec §3 與每個例子 | 自寫執行器（重用 `t-speak` 的 `_synth` 與各階段，加上 `manager.py` 的分割與重播模擬、NVDA 真正的符號處理）：23 個序列 × 2 個時間點 × 主要語音英／中／尼 × 數字語言 `default`／`main`／`zh_TW` × 符號等級 無／SOME／MOST，共 1206 組，`master` 與分支各跑一次 | 全部符合 spec：`"नेपाल"`、`(नेपाल)`、`- नेपाल`、`["link", '"नेपाल"']` 整段尼泊爾語；項目停頓 0 時 `link"` 留在英文；Price/100 不變；`-`、`नेपाल` 與 `(`、`1`、`नेपाल` 向後看；`(` 設為停頓字元時 `C:'(' \| C:'नेपाल)'`；標點停頓開／關與數字停頓 0／10 兩對的語音相同；`1२3` 整段尼泊爾語；`「中文」`（主要語音英文）整段中文；`"Hello"`（主要語音尼泊爾語）整段英文；兩個 utterance 的情境在偵測於 NVDA 之前時 `(` 由 `C` 變 `A`、之後時不變；`before`＋MOST 為 `C:' quote नेपाल quote'`，`after`＋MOST 不變 |
| 「跟隨主要語言」與指定語言的數字不變 | 同一份結果，含數字的列（Price、`(`/`1`/`नेपाल`、`abc 12 34 (नेपाल)`、`(2024) नेपाल`、`नेपाल (2024) नेपाल`、`2024年`、`3 apples`、`1. Introduction`、`1२3`） | `main` 與 `zh_TW` 下和 `master` 完全相同 |
| 和 `master` 的回歸語料 | 5000 組隨機序列（1–4 個項目，夾 `LangChangeCommand`、`IndexCommand`、utterance 結尾、NVDA 的 `BreakCommand`；隨機的數字模式、分組、五種停頓、移除標點、兩個時間點、主要語音英／中、數字語言 `default`／`main`／`zh_TW`／`en`），`master` 與分支各跑一次 | 階段輸出（文字、停頓位置、時間、還原後的類別）不同：0；聽到的文字或停頓位置不同：0；語音切換變多（不含／含空白片段）：0／0；`main` 與指定語言下數字的語音不同：0；有自己文字的字元語音不同：0；聽到的結果不同的 1404 組都只是 Common 字元換了語音 |
| Invariant 2 | 分支，7000 組（項目停頓 10 或 30；同一序列跑「停頓全關」與「隨機開啟」，數字模式與分組相同） | 3 組失敗，全是 I1 的形狀；其餘 6997 組每個非空白字元語音相同 |
| Invariant 1（端到端） | 同 7000 組，新規則對照 `master_detection` | 0 組切換變多（含空白片段也是 0） |
| Invariant 1（偵測器層） | 30000 組隨機序列（wrapper、文件語言含沒有語音的、每種停頓、utterance 結尾），分別以主要語言與「沒有語音的語言併入主要語音」兩種算法比較 | 0 組變多。I2 的反例是手寫的三段序列，隨機語料沒有抽到 |
| I1、I2、M1 的重現 | 上表各節列出的序列，兩個時間點 | 如各節所述 |
| 7.1 的停頓是否影響語音（readme 的說法） | `master` 複本，1500 組「停頓全關／隨機開啟」 | 0 組有字元換語音 |
| 測試抓得到錯誤：關掉開頭規則 | `mut` 複本，`detector:237` 改成 `elif False:`，跑 `t-det`、`t-speak` 與 pipeline 的 7 個測試檔 | 66 failed（`test_leading_punctuation_is_read_by_the_voice_of_the_text` 20、`test_a_leading_run_follows_the_text_after_it` 13、`test_an_utterance_start_looks_ahead` 9 等） |
| 拿掉驅動的接線（`__init__.py:293`） | 同上 | lifecycle 測試失敗（含 `test_the_detector_reads_through_the_pipelines_internal_breaks`） |
| 內部標點停頓改回一般類別（`punct:192`） | 同上 | 30 failed |
| 項目內邊緣停頓旁的收尾停頓不設為內部（`punct:215`） | 同上 | 8 failed（含 `test_the_end_of_item_pause_beside_an_in_item_number_edge_is_internal`） |
| 空白停頓改回一般 `BreakCommand`（`unspaced.py:64`） | 同上 | 51 failed（含兩個端到端 property） |
| 拿掉 utterance 範圍（`detector:275-277`） | 同上 | 3 failed（都在偵測器層的 `test_utterances_bound_the_lookahead`；端到端沒有對應測試） |
| 一律向後看／永不向後看（`detector:181`） | 同上 | 4 failed／9 failed |
| `NumberItemEdgeBreakCommand` 當成內部（`breaks:73`） | 同上 | 2 failed（`test_is_internal_break`、`test_boundaries_end_the_item`） |
| 拿掉 D10 的「已涵蓋就保留」（`detector:208`） | 同上 | 2 failed |
| 拿掉 Ruling 的「沒有語音就保留」（`detector:208`） | 同上 | 1 failed（`test_the_lookahead_keeps_the_language_when_no_voice_reads_the_text`） |
| wrapper 之後算項目開頭（`detector:225`） | 同上 | 16 failed（`main` 與指定語言的既有測試） |
| mutmut 等價抽查 1：target 呼叫的 `tmp_lang` → `None`（帳本 plan 20／stretch_targets 8） | 測試全過；30000 組偵測器輸出和原版比較 | 0 組不同；推理也成立（只有一段時該段語言就是 `tmp_lang`；多段時 `tmp == cur`）。判斷正確 |
| 等價抽查 2：`run_end` 的偏移 `(i, 0)` → `(i, 1)`（plan 29／34） | 同上 | 0 組不同。判斷正確 |
| 等價抽查 3：`(index, 0) < run_end` → `<=`（detect 18／19） | 同上 | 0 組不同。判斷正確 |
| 等價抽查 4：`offset` 分支（plan 10–14） | 同上 | 0 組不同。判斷正確（M6） |
| 等價抽查 5：後段的語言 → `None`（plan 33） | 測試全過；手寫三段序列 | **輸出不同，不等價**（M3） |
| stray `git init` | `cat .git`、`git worktree list`、`git fsck --no-dangling`、三個 worktree 的 `git status --short` 與 `git diff --summary`、`.git/config` 內容與時間 | worktree 仍指向主 repo；fsck 無輸出；三個 worktree 都沒有模式變更；prek 的 `pre-commit` hook 未變（11 月 3 日）。**補充：主 repo 共用的 `.git/config` 修改時間是 2026-11-10 02:32:12**，表示那次 `git init` 重寫過它。重新初始化只會寫 `core.filemode`（重新偵測）與 `core.bare=false`，目前的值是 `filemode=true`、`bare=false`，沒有多出 `core.worktree`，remote、branch、user 設定都在。我無法得知之前的 `filemode` 值，但沒有任何 worktree 出現模式差異，所以沒有實際影響 |

Linux 上的測試只驗證受控的邊界。Windows 上的 NVDA、IBM TTS、eSpeak、實際的 speech manager 與音訊都沒有驗證到；spec §7.6 的 M1–M7 需要在 Windows 手動確認。

## 帳本 `Ruling:` 的評估

| # | Ruling | 評估 |
| --- | --- | --- |
| 1 | Task 4：驅動與 harness 的接線、端到端數字 property 的 oracle 提前併入 Task 4 的 commit | 合理。目的是每個 commit 都是綠的，程式碼相同，只是早一個 commit |
| 2 | Task 4：`"Hello"`（主要語音尼泊爾語）與 `3 apples`（主要語音中文）的期望是 `("lang","en")` 而不是 `"en_US"` | 合理。`find_language_for_script` 在基準語言不涵蓋拉丁字母時回候選語言 `"en"`，是既有行為；spec 寫「goes to `en`」 |
| 3 | Task 5（實作者標為會影響行為）：跨過文件語言指令時，決定字元拿到的語言若不涵蓋它的文字（沒有任何已安裝語音讀這種文字），各段保留原本的語言 | **合理，建議接受。** D10 字面上會在引號前插入一個沒有語音的語言，聽起來仍回到主要語音，只是多一個無用的指令；§4.4 寫「沒有語音涵蓋該文字時什麼都不變」。我驗證過 D10 自己的例子不受影響：`['"', L("xx"), "नेपाल"]`（有尼泊爾語音）整段 `C`。把這個條件拿掉時 `test_the_lookahead_keeps_the_language_when_no_voice_reads_the_text` 失敗。建議在 spec D10 補一句說明這個例外。仍列入未確認的預設 |
| 4 | Task 5：偵測器自己判斷 utterance 結尾，不 import `pipeline.sequence._ends_utterance` | 合理（D13）。漂移風險見 M5 |
| 5 | Task 5：兩個 utterance 的列只在偵測器層測試，`heard()` 不學 `EndUtteranceCommand` | 可接受（spec F9 允許）。我用模擬 speech manager 的執行器補做了端到端驗證，結果和 spec §3 一致。代價是 M1 這類和重播有關的行為在 repo 的測試裡看不到 |
| 6 | Task 6：停頓對照的測試比較時忽略空白；`1. Introduction` 的期望是 `1 . Introduction` | 合理。各階段在停頓處切開文字，非空白字元的語音都有比較；數值模式把 `1.` 隔開是既有行為（`FOLLOW_ROWS` 的 `next`） |
| 7 | Task 8：7.1 spec 除了 G2 之外，§3 的表格列與 §7 的單元測試列也加刪除線 | 合理。三處是同一個被推翻的說法，內容正確 |

## 使用者還沒確認的使用者可見預設

需要使用者決定的新項目：

1. **I1 的處理方式。** (a) 當成限制寫進 spec 與 readme；或 (b) 在 `inject_numbers` 保留項目界線，這會讓指定語言下「項目邊緣是數字」時恢復項目停頓（改變 7.1 的停頓位置）。
2. **I2 的修法會改變的行為。** 修正後，`['"', L("ne_NP"), "(", L("hi_IN"), "नेपाल"]`（主要語音英文）的第一個引號會留在主要語音（和 7.1 相同），不再提前交給印地語。

協調者預設、使用者尚未逐項確認的行為（D1–D13 中使用者聽得到的部分）：

3. **D10 與 Ruling 3。** 開頭的標點向後看時跨過文件語言指令：標點取決定字元實際拿到的語言；標點所在的語言已經涵蓋該文字、或沒有任何語音讀該文字時，保留原本的語言。
4. **D5。** 文件標示的語言沒有語音時，開頭的標點也跟著後面的文字，例如 `[L("de_DE"), ", hallo"]` 的 `, ` 由英文語音朗讀（7.1 是主要語音，兩者在主要語音為英文時聽起來相同）。
5. **D9。** 「跟隨主要語言」與指定語言下，數字會擋住向後看：`(`、`1`、`नेपाल` 三個項目的 `(` 與 `1` 留在主要語音。
6. **D11。** utterance 的界線只限制「前面是否出現過文字」與向後看的範圍，不重設進行中的語言。偵測在 NVDA 之前時，`["नेपाल", utterance 結尾, "100"]` 的 `100` 仍由尼泊爾語朗讀；偵測在 NVDA 之後時由主要語音朗讀（既有的差異）。
7. **D7。** 拼讀不變：開頭的標點仍以拼讀的語言朗讀。
8. **偵測在 NVDA 之前、符號等級「多數」或「全部」。** 開頭引號的名稱（英文的「quote」）現在由尼泊爾語語音朗讀（7.1 是主要語音先讀「quote」再切換）。spec §2.3 列為非目標，結尾與行中的引號在 7.1 已經如此，但回報者聽得到這個改變。
9. **M1 的限制**（若不修）：指定語言、偵測在 NVDA 之後、同一次朗讀的後一個 utterance。
10. **readme 的文字**（M4 的四處）在使用者定稿前都還可以改。

## 修正記錄

修正依 DEVELOPMENT_WORKFLOW §3.4 進行：每項先寫會失敗的測試，再修正。I1 以外各項修正後的完整驗證：`python3 -m pytest -q tests` 3942 passed，0 skipped（3940 加上 2 個新測試）；I1 修正後：3986 passed，0 skipped（再加 44 個新測試）；兩次的 `prek run --all-files` 都全部 Passed；`git diff --check master` 沒有輸出；兩個受保護路徑指令都沒有輸出。

| 項目 | 處理 | commit |
| --- | --- | --- |
| I1 | 使用者選 (b)（2026-11-10）。`inject_numbers` 為項目開頭或結尾那個數字的 wrapper 加上標記；項目階段把項目停頓放在結尾 wrapper 之後、開頭 wrapper 之前，標點階段計算項目結尾的停頓時越過開頭 wrapper。拿掉 wrapper 後，各階段的輸出和「跟隨主要語言」相同（30 組對照）。審閱者的 `["abc 12", '"नेपाल"']`、`["Total 12", '"नेपाल"']`（數字語言 `zh_TW`、項目停頓 10，兩個時間點）現在引號由尼泊爾語朗讀、有項目停頓、數字停頓開或關的語音相同。改動的既有期望：`test_worked_examples_through_every_stage[wrapper-item10]`（原本釘住缺少的項目停頓）。端到端 property 加抽 `zh_TW`、`en`（`73e3598`），spec 記為 U10 並更正 U5、D8、§4.1（`70814d1`），readme 加一行更新日誌（`f64aaae`） | `1277d63` |
| I2 | 照建議修正：`stretch_targets` 從最後一段往前決定，某一段保留了涵蓋該文字、且主要語言和 target 不同的語言後，它前面的每一段都照舊規則。新增 `test_a_run_across_two_document_languages_adds_no_switch`（審閱者的三段序列），修正前失敗（印地、尼泊爾、印地），修正後通過 | `27d349e` |
| M1 | 不修。結果和 `master` 相同，依協調者指示保留，列為未確認的限制 | — |
| M2 | 偵測器層的 Invariant 1 改為也數語音切換（沒有語音的語言由主要語音朗讀，含空白），數字語言加抽 `zh_TW`，例數 300，並把 I2 的三段序列加成 `@example`（在修正前的程式碼會失敗）。端到端的兩個 property 加抽文件語言指令與 index 指令，只拿到空白的語音也算一次切換，每個時間點 100 例。utterance 結尾只在偵測器層抽（`heard()` 讀不了 `EndUtteranceCommand`）。指定數字語言的抽樣等 I1 決定後再加；這次加寬沒有遇到 I1 形狀的反例，所以沒有排除任何形狀 | `5fe506f` |
| M3 | 修 I2 後，「plan 33」的 mutant（`stretch_languages.append(None)`）會被 `test_a_run_across_two_document_languages_adds_no_switch` 殺掉（scratch 複本驗證：1 failed）。帳本原本「等價」的判斷已更正 | `27d349e` |
| M4 | 更新日誌刪掉不正確的「各種停頓設定不再影響標點由哪個語音朗讀」，改寫成「項目停頓參數」大於 0 時，開啟這些停頓也不影響新規則；保證的句子補上「項目停頓參數」大於 0 的條件；「NVDA 已換成名稱」的例外限定在「在 NVDA 處理語音指令後」；長項目拆成子項目，「一段朗讀項目」改為「每個項目」。和 I1 有關的限制說明等使用者決定 | `dc74500` |
| M5 | 新增 `test_detection_ends_an_utterance_where_the_pipeline_does`：偵測器的 `_utterances` 和 `pipeline.sequence._ends_utterance` 對同一組指令（兩種 utterance 結尾、各種停頓、index、wrapper、文件語言、其他物件）切法一致。把偵測器的判斷縮成只看 `EndUtteranceCommand` 時測試失敗 | `34c8e9e` |
| M6 | 拿掉 `plan` 的 `offset` 參數，每個字串從頭掃（`Ruling:` 已記在帳本：run 只在項目的第一個字元開始，offset 恆為 0）。行為不變，plan 10–14 的 mutant 隨之消失 | `9c76c5e` |
