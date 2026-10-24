# fix/number-edge-pause-items Review 紀錄：數字前後停頓跨 item 的修正

日期：2026-10-24。分支：`fix/number-edge-pause-items`（`20a8d9f..838e4ac`，2 個 commit：`04f4f03` fix、`838e4ac` docs），worktree `/workspace/WorldVoice-number-edge-items`。
依據：

- 規格 `docs/superpowers/specs/2026-10-24-feat-number-edge-pause-design.md`（本分支以刪除線更正 O2／D1，§2.2、§4.3、§4.6.2、§4.6.3、§4.6.4、§5、§6、§8.1、§8.3、§11）
- 使用者 2026-10-24 的新規則：數字的某一側只要在整個 speech sequence 裡有要朗讀的（非空白）文字，不論在同一個或其他 item、中間隔著什麼命令，就加 edge 停頓；sequence 的最開頭與最結尾不加；item 停頓或其他停頓與 edge 停頓相遇而中間沒有朗讀內容時，E2 只留最長的（同長留非 edge）。數值模式與「不處理」在任何停頓、數字／群組模式在停頓 ≤ 0 時與 `master` 逐位元組相同。
- 前一輪審閱 `docs/superpowers/finish/2026-10-24-feat-number-edge-pause-review.md`
- NVDA 來源 `ref/nvda/source/speech/speech.py:1137`（`filter_speechSequence.apply` 在整個 `speak()` 序列上執行）、`:349-362`（`speakSpelling` 把整段拼讀放進一次 `speak()`）、`:545-546`（拼讀時每個字元後面都有 `EndUtteranceCommand`）、`speech/manager.py:300-335`（`EndUtteranceCommand` 把序列切成多個 utterance）
- `DEVELOPMENT_WORKFLOW.md` §8

流程：審閱者 Fable 5.1，唯讀。測試、還原探針、mutmut、與 `master` 的差異比對都在 scratchpad 的 `git clone --shared` 複本進行（`ref` 以 symlink 接到主 checkout），審完已刪除。pytest 單一行程（mutmut 3 個子行程），每個長時間的執行外層都有 MemAvailable < 3 GB 就停掉 pytest 的看門狗（全程沒有觸發，起始 6.1 GB）。沒有 push、沒有 stash、沒有動主 checkout、沒有修改分支上的原始碼或測試；本文件是審閱者在任務分支上唯一的 commit。

`file:line` 以 `838e4ac` 為準；`pipeline:<n>` = `addon/synthDrivers/WorldVoice/pipeline/__init__.py:<n>`；`spec:<n>` = 規格檔的行號。

## 結論

Ready to merge：**處理 I1 之後是**（修程式，或由使用者接受並記入 spec 與 readme）。Critical 0、Important 1、Minor 4（M1–M3 是文件與措辭，M4 是 mutmut 找到的三個測試缺口，程式本身正確）。

- **新規則在 pipeline 層面落實正確，而且只落實在規格說的地方。**
  - 「某一側有朗讀文字」：`_inject_item_numbers` 用 `spoken_before`（前面是否已有非空白 item，`pipeline:447`、`:490`）與 `last_spoken`（最後一個非空白 item 的索引，`pipeline:449-453`）判斷，命令一律跳過（`pipeline:463-467`），所以語言命令、IndexCommand、未知命令都不會擋住文字，也不會被當成文字。「要朗讀的」用 `str.strip()`（`_is_spoken`，`pipeline:426-427`），與 `_merge_edge_breaks` 的 run 邊界（`pipeline:795`）用同一個定義。
  - item 頭尾的 edge 只在數字是 item 的第一個／最後一個非空白片段時加（`spoken_kinds`，`pipeline:528-530`、`:554-555`），所以 `" 3"`、`"3 "`、`" 3 "` 都算數字在頭尾；item 內部相鄰文字的 edge 仍由原本的規則（`pipeline:542-543`、`:552-553`）決定，兩者互斥，一個數字一側永遠只有一個 edge。
  - sequence 最開頭／最結尾：`spoken_before` 在處理完該 item 才更新（`pipeline:490`），`index < last_spoken` 嚴格小於，所以 `["3章"]`、`["第3"]`、`["3"]`、`[" ", "3", " "]`、`[Index, "3", Index]` 都沒有 edge（我的探針確認）。
  - 兩個數字分屬相鄰 item（`["1", "2"]`、`["第1", "2章"]`）各出一個 item edge，`inject_numbers` 自己的 `_merge_edge_breaks`（`pipeline:421`）留一個；輸入裡本來就有的 BreakCommand 與 edge 相遇也在這裡留最長的。
  - item 停頓：`_insert_item_breaks` 把 str 後面的 item edge 先扣住，判斷兩個 str 相鄰時把 item break 放在 edge 前面（`pipeline:189-204`），再 `_merge_edge_breaks`（`pipeline:186`）。item 10 與 edge 10 同長時留 item break；item 20 留 B20；item 5 留 E10。item 停頓為 0 時整個階段原樣放行，edge 單獨分隔數字。
  - 其他合成器：`_plain_break` 把 edge 種類（`True`／`"item"`）寫進 marker（`pipeline:979-984`），`_edge_kind` 對已經 plain 的 break 讀回 marker（`pipeline:56-61`），所以 scope "all" 下每個 handler 之間反覆 plain 化後 item 階段仍認得 item edge；我用 handler 鏈實測 `["第3", "章"]` roles 關 → `第 B*True 3 B*item 章`，item 10 → `第 B*True 3 B10 章`。
  - 偵測前／後：偵測器對非語言命令只 `yield`（`languageDetection/__init__.py:156-174`），`detect_with_number_language` 的 wrapper 貼合也不跨命令，所以 edge 的位置不受偵測時機影響。數字語言 default／main／locale 三種我都探過（locale 包裝留下時 edge 在包裝外側，去重後 edge 直接貼數字）。
- **與 `master` 相比，數值模式與「不處理」在任何停頓下、數字／群組模式在停頓 ≤ 0 時，整條 `STAGES` 的輸出逐位元組相同**（含 handler 鏈與 `_plain_breaks`）：我把 `master` 的 pipeline 模組與分支模組同時載入同一個 stub 環境做差異比對（Hypothesis，三條性質 × 4000 例，再以 seed 1、2 各 8000 例），全部通過；比對器本身在數字模式停頓 10 的 `["第3", "章"]`、`["1", "2"]` 會報 DIFF，所以不是空測。第三條性質確認數字／群組模式停頓 > 0 時多 item 序列的字（去空白接回）與語言命令與 `master` 相同——**只多了停頓，字沒有變**。
- **測試真的抓得到它聲稱的錯誤。** 13 種還原／突變在 scratch 複本上全部變紅，第一個失敗的測試都和該規則對應（表格「還原探針」）；一種等價突變（item break 與扣住的 edge 的先後順序，E2 同長留非 edge，順序無關）。mutmut 結果見表。
- **線性時間：** `["a", "1"] * 40000`（80000 item）經所有階段 1.4 s，5000→20000→40000 成比例；數字 item、空白 item、IndexCommand、en 包裝各種形狀都線性。`list(speechSequence)` 只在有 edge 時做一次。
- **文件：** 兩份 readme 各改一個條目與一條更新日誌，markdown 3.11 轉檔後 `<li>` 數量不變（59／59，`<li><strong>` 23），沒有清單被吞掉。spec 的更正以刪除線保留舊文、標註來源，§2.2、§4.3、§4.6.2、§4.6.3、§4.6.4、§5、§6、§8.1、§8.3、§11 都改到了，我沒有找到仍以舊 O2／D1 為前提卻沒有劃掉的句子（§4.3 標題的「O2, D1」是章節參照，可留）。用詞見 M3。
- **§8：** 2 個 commit 都是英文 `<type>: <summary>`、內文說明原因、沒有 `Co-Authored-By`；沒有碰 `driver/<Engine>/driver/`、`driver/sonic/`、`script_data.py`、Neural、`buildVars.py`、`addon/locale`；prek 八個 hook 全數 Passed（ruff 0.16.3）；`git diff --check master` 乾淨。

## Critical

無。

## Important

### I1. `EndUtteranceCommand` 被當成「中間的命令」：拼讀時數字模式的每個數字 utterance 會以 edge 停頓開頭／結尾

- 位置：`pipeline:462-467`（命令一律 `yield` 後跳過，不影響 `spoken_before`／`last_spoken`）、`pipeline:449-453`（`last_spoken` 以整個序列算）；spec `spec:689`「No pause is left at the end of an utterance」、`spec:113`「the only exception is the very start or end of the whole sequence」。
- 情境：NVDA 的 `speak()` 先對整個序列跑 filter（`ref/nvda/source/speech/speech.py:1137`），再由 `speech/manager.py` 的 `_processSpeechSequence` 在每個 `EndUtteranceCommand` 把它切成多個 utterance 送給合成器。拼讀（`speakSpelling`，`speech.py:349-362`；WorldVoice 的 `patchedSpeakSpelling` 也是呼叫它）把整段文字放進一次 `speak()`，每個字元後面跟一個 `EndUtteranceCommand`（`speech.py:545-546`）。數字模式、數字停頓 10，拼讀 `a1b`：
  - 分支（我用一個未知命令代表 `EndUtteranceCommand` 實測）：`a` EndUtt **E10** `1` **E10** EndUtt `b` EndUtt → 合成器收到的第二個 utterance 是 `[E10, "1", E10, Index]`：數字前面先靜音一個數字停頓，後面再靜音一個。拼讀 `12`：`1` **E10** EndUtt `2` → 第一個 utterance 以停頓結尾。
  - `master`：拼讀沒有任何停頓（`EndUtteranceCommand` 在 `_insert_number_breaks` 也是「其他命令把數字隔開」）。
  - 瀏覽模式 Say All 在區塊結尾也會放 `EndUtteranceCommand`（`speech.py:1678`），`"…第3"` EndUtt `"章…"` 會讓前一個 utterance 以 E10 結尾。
  - 預設 10 ms 聽不出來；但數字停頓是使用者會調大的參數（`scaled_number_wait` 最大 10 × 100 = 1000 ms），調大後每個拼讀的數字前面都會先等一個數字停頓才出聲。這與 spec D1 的「No pause is left at the end of an utterance」和規則的例外（sequence 開頭／結尾不加）的本意相反——對合成器與使用者而言，utterance 才是「sequence」。測試看不到它，因為 `tests/pipeline_harness.py` 的 `speech.commands` stub 沒有 `EndUtteranceCommand`。
- 建議（二選一，由使用者定奪）：
  - **A. 把 `EndUtteranceCommand`（與同樣結束 utterance 的 `ConfigProfileTriggerCommand`，`speech/manager.py:313-316`）當成 sequence 邊界。** `_inject_item_numbers` 遇到它時把 `spoken_before` 歸零，`last_spoken` 改成「這個 item 之後、下一個邊界之前的最後一個非空白 item」（一次反向掃描即可，仍是線性）。`_merge_edge_breaks` 不用改（邊界兩側不會再有 edge 相遇）。stub 要在 `tests/pipeline_harness.py` 的 `speech.commands` 加 `EndUtteranceCommand`，並加一個先紅後綠的 row：`["a", EndUtt, "1", EndUtt, "b", EndUtt]` → 原樣；`["第3", EndUtt, "章"]` → `第 E 3 EndUtt 章`。spec §4.3「Where」補一條、§4.6.5 補一句。
  - **B. 接受並記錄**：spec D1 刪掉「No pause is left at the end of an utterance」或改成「of the speech sequence」，§3 補一列「拼讀時數字模式的數字前後各一個數字停頓」，readme 的「朗讀內容的最開頭與最結尾」維持（對使用者而言拼讀的每個字元都像一段朗讀，所以 readme 的說法會與實際不符，建議還是選 A）。

## Minor

### M1. spec §4.6.2 說「run 裡有 edge 時 E2 只留一個 break」，但移除標點把兩個 run 接起來時仍會留下兩個 item break

- 位置：`spec:281`；`pipeline:186`（item 階段先 merge）、`pipeline:762-771`（標點階段的移除與 M2 規則只處理 `NumberBreakCommand`）、`pipeline:806`（沒有 edge 的 run 原樣放行）。
- 情境：數字模式、停頓 10、item 10、`。` 列為停頓字元、移除開啟，`["3", "。", "4"]`：數字階段 `3` E `。` E `4`；item 階段兩個 run 各留 B10（同長留 item break）→ `3` B10 `。` B10 `4`；標點階段把 `。` 移掉，兩個 B10 相鄰，run 裡已經沒有 edge，E2 不碰 → `3` B10 B10 `4`（20 ms）。`master` 完全相同（F7 的既有行為），所以不是回歸，只是 spec 這句話在「item break 先贏、再被移除接起來」時不成立。
- 建議：把 `spec:281` 改成「…with a number edge still in the run, E2 leaves one break; where the item breaks already won and removal then joins two runs, F7's two breaks remain, as on `master`」。不改程式。

### M2. 開頭的標點被移除、標點停頓為 0 時，sequence 以 10 ms 的 edge 開頭（`master` 以 0 ms 的標點停頓開頭）

- 位置：`pipeline:743-744`（移除開頭的標點後仍送出邊界 PB）、`pipeline:691`、`:804-810`（E2 在第一個 run 留最長的）。實作者自己列為不確定項目 (2)。
- 情境：`["。", "3", "章"]`、`。` 列為停頓字元、移除開啟、標點停頓 0、數字模式停頓 10：數字階段 `。` E `3` E `章`；標點階段把 `。` 移掉、送出 PB0 → 第一個 run `[PB0, E10]`，E2 留 E10 → `E10 3 E 章`。`master` 是 `PB0 3 章`。差 10 ms 的開頭靜音，而且只在「句子以要移除的標點開頭」時發生；標點停頓 > 10 時兩邊都是 PB 開頭，與 `master` 相同。
- 建議：可接受並記入 spec §4.6.3（「the run before the first spoken item may keep an edge where removal dropped the mark」）；若要修，在 `inject_punctuation_pause` 的 merge 之後把第一個 run 裡的 edge 丟掉（最後一個 run 不會有 edge）。不急。

### M3. readme 的「相鄰的項目」／"a neighbouring one" 比規則窄

- 位置：`readme.md:53`、`addon/doc/zh_TW/readme.md:53`。
- 情境：規則是「序列裡任何一處」：`["第3", " ", "章"]`（空白 item 隔開）、`["第3", Index, "章"]`（格式變化的 IndexCommand 隔開）、`["第3", LangChange, "abc"]` 都有 edge，文字不一定在相鄰的 item。使用者讀 readme 不會知道 item 是什麼，所以影響小；但「不論文字在同一個項目或相鄰的項目」會讓懂 NVDA 的讀者以為隔一個空白項目就不加。
- 建議：zh_TW 改成「（數字前後有其他要朗讀的文字時，不論那段文字是否與數字在同一個項目）」；EN 改成 "every number that has other spoken text somewhere before or after it, in the same item or not"。更新日誌那句（「標點停頓或項目間停頓與數字停頓落在同一處時，只會聽到較長的那一個」）正確。

### M4. mutmut 的三個存活突變是測試缺口（程式正確，差異比對已確認與 `master` 相同）

- `x_item_wait_factor__mutmut_3`（`pipeline:183`，`wait_factor <= 0` → `<= 1`）：item 停頓剛好 1 ms（global 10、item factor 1）時不加 item break。沒有測試用 item 停頓 1，而有數字的列殺不了它（B1 遇到 E10 本來就輸給 E10），要用沒有數字的 `["a", "b"]`、item 1 → `a B1 b`（`tests/test_pipeline_filters.py` 的 item 測試加一個 case）。這個條件是既有程式，本分支只是搬動。
- `x__inject_item_numbers__mutmut_42`／`_45`（`pipeline:470-472`，算包裝會不會留下時 `start_language=language` → `None`／省略）：語言在力不是 ctx 語言時判斷錯：`[LangChange("en"), "12. Next"]`、數值模式、數字語言 en → 正確是 `L(en) "12 . Next"`（包裝被去重，點號規則加空白，與 `master` 相同），突變是 `"12. Next"`。前一輪 I1 修正（`486aa44`）加的邏輯，沒有「語言在力 ≠ ctx 語言」的 case。建議在 `test_the_dot_rule_spaces_only_numbers_whose_wrapper_goes` 加一個 `LangChangeCommand("en")` 開頭的 case。
- `x__inject_item_numbers__mutmut_73`／`_74`（`pipeline:479`，`mode != "none"` 的字串）：「不處理」＋包裝會被去掉的 locale（zh 同一個語音、fr 沒有語音）時，突變會套點號規則：`["3. Next"]`、none、numlan zh → 正確 `"3. Next"`，突變 `"3 . Next"`。`test_off_mode_with_a_locale_keeps_the_dots_as_they_are` 只用 numlan en（包裝留下，兩邊都不套）。建議多參數化 numlan zh 與 fr。
- 其餘 8 個存活突變等價：`_edge_kind` 的 `getattr(..., None)`（falsy，`== "item"` 也為假）；`_insert_item_breaks` 的 `previous = None`（不是 str，與 `_MISSING` 同效）；`spoken_before = None`（falsy，`None or bool` 仍是 bool）；`last_spoken` 的初值與 `default` 改成 +1／−2（有 edge 時一定被 `max` 覆蓋，沒有任何朗讀 item 時也沒有數字 item 會用到它；沒有 edge 時 `item_edge` 是 None，`index < last_spoken` 的結果不會被用到）；`wraps and language not in kept` → `or`（不 wraps 時多算一次 `kept`，但 `dot_rule` 的 `wraps and …` 仍為假，結果不變）。

## 實作者標記的五個不確定項目

| # | 項目 | 評估 |
| --- | --- | --- |
| 1 | `["1", "2"]` 在 item 0 時得到 edge（`NumberItemEdgeBreakCommand`）而非 `NumberBreakCommand` | **沒有問題。** 會分辨 break 類別的只有：E1（edge 不壓掉邊界標點停頓，`pipeline:761`）——兩個整數 item 之間沒有標點，E1 不會觸發；M2 移除規則（`pipeline:766-768`）看的是 `NumberBreakCommand`，`NumberItemEdgeBreakCommand` 是它的子類別，行為相同；`number_wait_factor` 的 `_insert_number_breaks` 看到任何非語言命令就不再加 NB（`pipeline:274`），所以不會重複；其他合成器只讀 `.time`；log 只是 repr 的類別名稱不同。時間相同（10 ms），聽不出差異。spec §4.6.4 已記錄。 |
| 2 | 移除開頭的標點可能留下 sequence 開頭的 break | 見 M2：只在標點停頓 0 時與 `master` 不同（E10 對 PB0），其他情況 `master` 也以 PB 開頭。 |
| 3 | item break 之間的空白 item | `["第3", " ", "章"]` item 10：數字階段 `第 E 3 IE " " 章`，item 階段 `第 E 3 B10 IE " " B10 章` → E2 在同一個 run（`[B10, IE, " ", B10]`）留第一個 B10 → `第 E 3 B10 章`，`master` 是 `B10 B10`（20 ms）。這是規則的直接結果（run 裡有 edge），也是 spec `spec:281` 所寫；`["第3", "", " ", "章"]`、`["a", " ", "3"]` 我也探過，都只剩一個 break。沒有 edge 相鄰的空白 item（value 模式）與 `master` 相同（差異比對）。列入「使用者還沒確認」第 2 項。 |
| 4 | item 停頓仍不跨 wrapper／index／語言命令 | 既有行為，本分支沒有改也不該改（`_both_text` 只看相鄰兩個 str）。差別是以前這些位置完全沒有停頓，現在有 E10：`["第3", "章"]`、數字語言 en、item 20 → `第 E L(en) 3 L(zh) E10 章`（不是 B20）。spec §5 已寫。列入「使用者還沒確認」第 6 項。 |
| 5 | 沒有跑 mutmut | 我跑了，見表「mutmut」。 |

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 完整測試（分支 `838e4ac`） | `guard.sh python3 -m pytest -q -p no:cacheprovider tests`（scratch 複本） | **2919 passed、0 skipped**（98 s；基準 `master` 2837／0，與協調者回報相同） |
| prek | `prek run --all-files`（scratch 複本，prek 0.4.14、ruff 0.16.3） | 8 個 hook 全數 Passed |
| 空白與受保護路徑 | `git diff --check master`；`git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py buildVars.py addon/locale`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 三個都無輸出 |
| commit 訊息 | `git log master..HEAD --format='%h %s%n%b' \| grep -ic co-authored` | 0；2 個 commit 都是英文 `<type>: <summary>`，內文說明原因 |
| 與 `master` 的差異比對（整條 `STAGES`，`stage.fn` 與 handler 鏈各半） | `master` `20a8d9f` 的 pipeline 模組與分支模組載入同一個 stub 環境；Hypothesis 三條性質：(1) value／none、停頓 −5–60；(2) number／group、停頓 −5–0；(3) number／group、停頓 1–60，去空白接回的字與語言命令相同。項目最多 6 個：ASCII／全形／阿拉伯－印度數字、正負號、`.,:×_`、字母、CJK、`。，？?()$`、一般／不換行／全形空白、tab；`BreakCommand(0／5／30)`、NVDA 與 WV 語言命令（含 `None`）、未知命令；數字語言 default／main／en／zh／fr；roles 開關；標點字元六組（含 `" "`）、移除開關、標點停頓 0–300、item 與中文停頓 0–60、每組位數 2–10 | 預設 seed × 4000 例：3 passed（69 s）；seed 1、2 × 8000 例：各 3 passed（157 s）。比對器對數字模式停頓 10 的 `["第3", "章"]`、`["1", "2"]` 報 DIFF、`["第3章"]` 報 SAME（靈敏度確認） |
| 還原探針（scratch 複本，逐一套用後跑 6 個相關測試檔，`-x`，再 `git checkout`） | P1 `inject_numbers` 不 merge；P2 `item_wait_factor` 不 merge；P3 不給 `edge_before`；P4 不給 `edge_after`；P5 `index <= last_spoken`（sequence 結尾也加）；P6 `edge_before` 永遠給（開頭也加）；P7 item 階段不扣住 item edge；P8 `_plain_break` marker 一律 `True`；P9 空白 item 算有朗讀；P10 開頭空白擋住 `edge_before`；P11 結尾空白擋住 `edge_after`；P12 `NumberItemEdgeBreakCommand = NumberEdgeBreakCommand`；P13 `spoken_before` 在該 item 之前更新；P14 item break 放在扣住的 edge 之後 | **13／13 變紅**，P14 等價（見下）。第一個失敗：`m1-items`／`end-item5`／row 28／row 28／row 9／row 9／`end-item10`／`test_other_synths_get_edge_breaks_across_items[end-item10]`／`blank-around-item0`／`space-start-item0`／`space-end-item0`／`test_one_edge_and_one_gap_instance_per_run`／row 28。P14：`[B10, IE]` 與 `[IE, B10]` 經 E2 都留 B10（同長留非 edge，與位置無關），609 個測試全綠，是等價突變，不是測試缺口 |
| mutmut | `guard.sh mutmut run --max-children 3` 加 glob `*x__inject_item_numbers*` `*x_inject_numbers*` `*x__insert_item_breaks*` `*x_item_wait_factor*` `*x__number_item_segments*` `*x__edge_kind*` `*x__is_item_edge_break*` `*x__is_edge_break*` `*x__plain_break*` `*x__is_spoken*`（scratch 複本，`mutants/` 已刪） | 十個函式共 **262 個 mutant：249 殺、13 存活、0 timeout**（`_inject_item_numbers` 94、`_number_item_segments` 78、`inject_numbers` 46、`_insert_item_breaks` 11、`_plain_break` 10、`item_wait_factor` 9、`_edge_kind` 8、其餘各 2）。存活 13 個：8 個等價、5 個（三組）是測試缺口，見 M4；每個存活突變我都用 `mutmut show` 看過 diff，M4 的三組另外套到 scratch 複本上實測輸出差異 |
| 邊角輸入探針（41 組，`inject_numbers` 輸出與整條 `STAGES`，roles 關的另跑 handler 鏈） | 拼讀形狀 `["a", EndUtt, "1", EndUtt, "b", EndUtt]`、`["1", EndUtt, "2", EndUtt]`；`["第3", Index, "章", Index]`；輸入裡既有的 B5／B30／B0 在數字前後、開頭、結尾；空白 item 一個／兩個／空字串；開頭／中間的標點移除（標點停頓 50／0，item 0／10）；中文空白停頓在數字前後；數字語言 en（包裝留下）、zh（去重）、main；roles 關；NVDA／WV 語言命令夾在 item 之間；`["第", "3 "]`、`["1 2", "3"]`；value 模式跨 item；group 模式 `["第123", "456章"]`；`["1 ", "2"]` item 10；點號規則 `["5.", "下"]`、`["下", ".5"]`；空白列為停頓字元；`[Index, "3", Index]` | 除 I1、M1、M2 外全部符合新規則：每個有朗讀文字的一側恰好一個 break、sequence 開頭結尾沒有 edge（`[B30, "3", "章"]` 的開頭 B30 是輸入）、既有 B5／B0 被 E10 取代、B30 留下、`["第123", "456章"]` group 2 → `第 E 12 NB 3 E 45 NB 6 E 章`、`["1 2", "3"]` → `1 NB 2 E 3`（item 10 時 `2 B10 3`） |
| 線性時間（整條 `STAGES`，item 10，標點字元 `".,"`） | `["a", "1"] * n`、`["1"] * n`、`["1", " ", "a"] * n`、`["第3", Index, "章"] * n`、`["第3", "章"] * n`（en 包裝），n = 5000／20000／40000 | 0.18／0.73／1.40 s（a/1）、0.08／0.30／0.60 s（只有數字）、0.15／0.57／1.17 s（空白）、0.14／0.55／1.11 s（Index）、0.15／0.63／1.35 s（en）：線性；分支自己的測試（10000 item < 2 s）約 0.4 s，有 5 倍餘裕 |
| readme 轉檔 | `markdown.markdown(text, extensions=["tables"])`（markdown 3.11），比較改前後 | 兩份都是 59 個 `<li>`、23 個 `<li><strong>`，改到的條目仍在同一個 `<li>` 內 |
| 記憶體 | 看門狗（MemAvailable < 3 GB 停止） | 沒有觸發 |

## 使用者還沒確認的使用者可見預設

這些是新規則或本次審查發現的、使用者可能還沒逐條聽過的可聽見差異（數字／群組模式、數字停頓 > 0）：

1. **兩個數字分屬相鄰 item**（`["1", "2"]`、`["第1", "2章"]`、`["1 ", "2"]`）：item 0 時聽到一個數字停頓（以前是 `number_wait_factor` 的數字停頓，時間相同）；item 10 時是 item 停頓（不變）。
2. **空白 item 夾在中間**（`["第3", " ", "章"]`，item 10）：只剩一個 item 停頓，以前是兩個（F7，20 ms → 10 ms）。沒有數字相鄰時仍是兩個；移除標點把兩個 run 接起來時也仍是兩個（M1）。
3. **輸入裡本來就有的較短停頓被 edge 取代**：`["第3", BreakCommand(5), "章"]` → E10；`["3", BreakCommand(0), "章"]` → E10；較長的（B30）留下。NVDA 自己很少在數字旁放 BreakCommand，影響小。
4. **IndexCommand／語言命令隔開的 item 也有停頓**：瀏覽模式格式變化切出的 `["第", Index, "3", Index, "章"]` 現在是 `第 | 3 | 章`（spec §5 row 28 改為此），Say All 的 `["第3", Index, "章"]` 也是。
5. **拼讀**（I1）：數字模式下拼讀含數字的字串，每個數字 utterance 前後各一個數字停頓；`master` 沒有。
6. **locale 包裝擋住 item 停頓**：`["第3", "章"]`、數字語言 en、item 20 → `3` 與 `章` 之間是 E10 不是 B20（以前完全沒有停頓）；去重後（zh 同一個語音）則是 B20。
7. **其他合成器（scope "all"）**：plain break 帶 marker `"item"`；聽到的與 WorldVoice 相同。
8. **開頭標點被移除、標點停頓 0**：以 10 ms 的 edge 開頭（M2）。
9. **readme 用詞**「相鄰的項目」／"neighbouring"（M3）。

## 尚未驗證（Windows／NVDA）

Linux 上只驗證了 pipeline 與 NVDA 的 `speak`／`manager`／`speakSpelling` 邏輯；實際音訊、各引擎對 utterance 開頭 `<break>`／靜音 task 的處理（I1 的可聽程度）、OneCore／SAPI5／eSpeak 對 10 ms break 的處理都沒有驗證。未打包。

## 工作區備註

主 checkout `/workspace/WorldVoice` 在 review 開始前就有的未提交變更，與本分支無關，未動：`M buildVars.py`、`D docs/superpowers/finish_task.md`、`?? DEVELOPMENT_WORKFLOW.md`、`?? diff.md`。

## 修正記錄

實作者 Opus 5.5，2026-10-24，依協調者指示處理（I1 採審閱者的選項 A）。修正後完整測試 **2941 passed、0 skipped**（審閱時 2919／0，新增 22 個測試）；`prek run --all-files` 8 個 hook 全數 Passed；`git diff --check master` 無輸出；受保護路徑（`driver/*/driver/`、`driver/sonic/`、`script_data.py`）的 `git diff --stat master` 與 `git ls-files …/driver/Neural` 都無輸出；commit 都沒有 `Co-Authored-By`。

| 項目 | 處理 | commit |
| --- | --- | --- |
| I1 | 改程式：`_ends_utterance` 把 `EndUtteranceCommand` 與 `ConfigProfileTriggerCommand` 當成 sequence 的邊界。`_inject_item_numbers` 遇到它就把 `spoken_before` 歸零；`_spoken_later` 一次反向掃描，標出每個 item 之後在同一個 utterance 內是否還有要朗讀的文字（取代整個序列的 `last_spoken`），仍是線性。`_merge_edge_breaks` 不用改。測試 stub（`tests/pipeline_harness.py`、`tests/test_worldvoice_speak.py`）加上兩個命令。先紅後綠的 row：拼讀 `a1b`（`["a", EU, "1", EU, "b", EU]`，原樣）、拼讀 `12`、`[EU, "3", EU]`、區塊結尾 `["第3", EU, "章"]` → `第 E 3 EU 章`、`["第", EU, "3章"]`、`["第3", CPT, "章"]`，以及同一個 utterance 內仍跨 item 的兩列，item 0 與 10 各一次（16 個 case）。P-E7 的輸入加上這兩個命令，改成逐 utterance 檢查；另加一條只抽文字與這兩個命令的性質（原本的 P-E7 在 400 例內抽不到這個情況，新性質修正前即紅）。與 `master` 的差異比對（scratch 複本，30000 個含 `EndUtteranceCommand`／`ConfigProfileTriggerCommand` 的隨機序列，數值模式與「不處理」任何停頓、數字／群組模式停頓 ≤ 0，roles 開關、`_plain_breaks`）逐位元組相同。spec §4.3、§4.6.5、§5、P-E7、D1 與 O2 更正句改為「utterance」。 | `6a57bd4`（程式與測試）、`3ebe69f`（spec 與原始碼註解）、`1bcf06f`（測試註解） |
| M1 | spec §4.6.2 補一句：item break 已在兩個 run 各自勝出、標點移除再把兩個 run 接起來時，run 裡已沒有 edge，F7 的兩個 break 仍在，與 `master` 相同（`["3", "。", "4"]` → `3 B10 B10 4`，已實測）。不改程式。 | `3ebe69f` |
| M2 | 接受並記入 spec §4.6.3：開頭的標點被移除、標點停頓 0 時以 E10 開頭（`["。", "3", "章"]` → `E10 3 E10 章`，`master` 是 `PB0 3 章`，已實測）。沒有改程式：要在標點階段丟掉第一個 run 的 edge，就得同時處理 I1 的每個 utterance 開頭，不算小改動。 | `3ebe69f` |
| M3 | 兩份 readme 改寫：文字可以在同一段朗讀（utterance）裡的任何其他項目，中間隔著什麼命令都一樣；每段朗讀的開頭與結尾不加（以逐字拼讀為例）。 | `001ccf7` |
| M4 | 補三組測試，並把審閱者的三組突變各套到工作區後確認都變紅，再還原：item 停頓剛好 1 ms（`["a", "b"]` → `a B1 b`，另一個 case 是 0）；`[LangChange("en"), "12. Next"]`、數值模式、數字語言 en → `L(en) "12 . Next"`（語言在力 ≠ ctx 語言）；`test_off_mode_with_a_locale_keeps_the_dots_as_they_are` 加上數字語言 zh（與語言在力同一個語音）與 fr（沒有語音），兩者都是 `"a.1. b"`。 | `179ed7b` |

裁定：

- **`ConfigProfileTriggerCommand` 一律當成邊界。** NVDA 只在觸發器有設定檔時才在它前面結束 utterance（`speech/manager.py:342-363`），沒有設定檔時直接忽略；pipeline 不讀觸發器的狀態，所以一律當成邊界。代價是：沒有設定檔的觸發器前後，數字不會跨過它取得 edge 停頓。這種觸發器只出現在 utterance 的開頭與結尾（例如 Say All 的設定檔觸發器），實際上很少遇到。
- **`BaseCallbackCommand` 不算邊界。** speech manager 只會在它那裡插入 index 並切開，utterance 沒有結束。

仍未驗證：Windows 上的 NVDA、實際音訊與各引擎。未打包。
