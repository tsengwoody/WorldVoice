# feat/punctuation-wait-global-factor Review 紀錄：標點停頓改用全域停頓參數

日期：2026-10-26。分支：`feat/punctuation-wait-global-factor`（`47b98c9..5d0ee7d`，2 個 commit：`23328af` feat、`5d0ee7d` docs），worktree `/workspace/WorldVoice-punct-global`。
依據：

- 簡化流程，沒有 spec 和 plan；行為由使用者決定（2026-10-26）：`scaled_punctuation_wait()` 改為 `global_factor_units × punctuation_wait_factor`，沒有 5 ms 單位、沒有 500 ms 上限（最大 10 × 100 = 1000 ms）；不遷移設定值；預設 0、範圍 0..100、`effective()` 不變；開關開啟時每個停頓點仍插入 `PunctuationBreakCommand`，全域 0 也一樣（0 ms 的 break 仍會把文字切開）；`_merge_edge_breaks` 不變。
- `DEVELOPMENT_WORKFLOW.md` §3.3、§7、§8。

流程：審閱者 Fable 5.1，唯讀。測試、突變探針、Review Focus 探針都在 scratchpad 的 `git clone --shared` 複本進行（`ref` 以 symlink 接到主 checkout），審完已刪除。pytest 最多 2 個行程同時跑，每個都在 MemAvailable < 3 GB 就停掉的看門狗底下（全程沒有觸發）。沒有 push、沒有 stash、沒有動主 checkout、沒有修改分支上的原始碼或測試；本文件是審閱者在任務分支上唯一的 commit。

`file:line` 以 `5d0ee7d` 為準；`settings:<n>` = `addon/synthDrivers/WorldVoice/pipeline/settings.py:<n>`；`punct:<n>` = `addon/synthDrivers/WorldVoice/pipeline/punctuation.py:<n>`。

## 結論

Ready to merge：**是**，建議先修 I1（只改六份 readme 的措辭，不改程式）。Critical 0、Important 1、Minor 3。

- **程式正確，只有一處算式。** `settings:312-313` 現在是 `self.global_factor_units * self.punctuation_wait_factor`，和 `scaled_number_wait`／`scaled_item_wait`／`scaled_sayall_wait`／`scaled_unspaced_script_space_wait`（`settings:300-310`）同一個寫法；`global_factor_units = global_wait_factor // 10`（`settings:297-298`）不變。兩個常數 `PUNCTUATION_WAIT_UNIT_MS`、`MAX_PUNCTUATION_WAIT_MS` 和解釋「獨立於全域參數」的註解已刪除。
- **呼叫端全部確認。** `scaled_punctuation_wait` 在 `addon/` 只有一個呼叫者 `punct:134`；兩個常數在 `addon/`、`tests/`、`globalPlugins`、UI 面板（`ui/*.py`）、`.po` 都沒有其他引用，只剩守門測試 `tests/test_pipeline_settings_service.py:89-90` 斷言它們不存在。面板標籤（`settings:243-251` 的 `"Punctuation wait factor"`）和 `nvda.po` 都沒有「5 ms」或「500」的文字，不需改。`git grep` 整棵樹只剩歷史 spec／plan（phase 5½–6、phase 27、number-group-mode）提到舊公式，屬歷史文件，不改。
- **和 `master` 相比沒有回歸。** 分支只改 `scaled_punctuation_wait` 的回傳值；`inject_punctuation_pause`／`_punctuation_pauses`（`punct:113-205`）的邏輯一行都沒動，只改 docstring。全套測試 3247 passed／0 skipped，`master` 基準 3240／0，多出的 7 個正是新測試（換算表 +2 列、常數守門 1、Hypothesis 性質 1、真實設定驅動標點階段 3）。
- **Review Focus 五項都用真實的 `PipelineSettings`（`ConfigPipelineRepository` 讀出）跑過 `STAGES` 全部階段**，結果見下表「Review Focus 探針」，和使用者的決定一致：全域 0 時每個停頓點有 `PunctuationBreakCommand(0)`、1000 ms 沒有上限、平手時非 edge 的標點停頓勝出、其他合成器經 `effective()` 完全不處理、空白字元與不分詞空白停頓的分工和 `master` 相同。
- **測試真的抓得到它聲稱的錯誤。** 五種突變（還原舊公式、加回 500 上限、整個階段在 0 時跳過、只在 0 時不送 break 但仍移除標點、用 `global_wait_factor` 不除 10）在 scratch 複本上全部變紅，見「突變探針」表。新加的 `test_the_punctuation_pause_follows_the_global_factor[0-30-0]` 是唯一同時抓到「0 時跳過」兩種寫法與舊公式的測試，正是使用者要的那條規則。
- **文件六份都改了同樣三處**（全域參數 bullet、標點停頓參數 bullet、「下次更新」更新日誌），數字和例子都對：預設全域 10 時數值 N = N ms；舊 20 × 5 = 100 ms 現在要設 100；上限 1000 ms 用「不再有 500 毫秒的上限」表達。翻譯自然，用詞和各檔案其他段落一致（ru「место паузы」、uk「місце паузи」沿用第 62 行；zh 見 M2）。唯一的問題是「0 時沒有停頓」的說法沒有提到文字仍被切開，見 I1。
- **§7／§8：** prek 8 個 hook 全數 Passed（prek 0.4.14、ruff 0.16.3）；`git diff --check master` 乾淨；受保護路徑無 diff、Neural 無追蹤檔；`tests/test_plugin_voice_contract.py` 與 `master` 無差異；兩個 commit 都是英文 `<type>: <summary>` 加內文、沒有 `Co-Authored-By`；`master` 仍是 `47b98c9`，可以 fast-forward。

## Critical

無。

## Important

### I1. 六份 readme 說全域 0（或標點停頓參數 0）時「沒有停頓」，沒有說文字仍會在停頓處被切開

- 位置：`readme.md:52`（「At 0, none of the pauses below are added.」）、`readme.md:63`（「At 0 (the default), no extra pause is added.」）、`readme.md:101`（「With a global wait factor of 0, there is no pause at punctuation either.」）；`addon/doc/{zh_TW,zh_HK,zh_CN,ru,uk}/readme.md` 同三行。程式：`punct:134`（`pause_cmd = PunctuationBreakCommand(settings.scaled_punctuation_wait())`，0 ms 照樣建立並送出）、`punct:71-73` docstring 明寫「a 0 ms break still separates the text on either side」；`addon/synthDrivers/WorldVoice/bridge/commands.py:15-16` 把它轉成 `Pause(0.0)`，`runtime/requestBuilder.py:44-50` 遇到 `Pause` 就 `flush()` 目前累積的文字再 `append_break`，所以兩側的文字是分開合成的。
- 情境：使用者在「標點停頓字元」輸入了「，。」，想「全部關掉停頓」而把全域停頓參數調到 0。照文件讀，標點處應該和沒設定一樣；實際上 WorldVoice 仍在每個標點把句子切成兩段合成（其他階段在 0 時都 `yield from` 原樣跳過：`items.py:30-32`、`numberStages.py:119-121`、`unspaced.py:61-63`），句子的語調會在標點處重新開始，和關閉「啟用標點停頓控制」時不同。使用者在 2026-10-26 明確指出這一點，並要求保留 0 ms break；所以這是刻意的行為，文件卻把它藏起來。第 63 行的句子在 `master` 就有，先前標點停頓參數 0 時也已經如此；但第 52 行刪掉「標點停頓不受這個設定影響」之後，「下列停頓都不會加入」第一次把標點停頓也包含進去，第 101 行的新句子更直接說「全域 0 時標點處也不會停頓」，都會讓人以為全域 0 等於關閉。
- 評估：不是程式 bug，是使用者可見的文件說明與實際聽感不符；修法只改文件，建議在 merge 前一併修。建議在三處各補半句，說明「0 ms」和「關閉」的差別，並指出要完全不處理就關掉開關。
- 建議措辭（直接取代各檔對應句子）：
  - `readme.md:52`：「At 0, none of the pauses below are added; with punctuation pause control on, the text is still split at each pause point (see below).」
  - `readme.md:63`：「At 0 (the default), no extra pause is added, but with punctuation pause control on the text is still split at each pause point, so it can sound different there than with the control off.」
  - `readme.md:101`：「With a global wait factor of 0 the punctuation pause is 0 ms too, but with punctuation pause control on the text is still split at each pause point; turn punctuation pause control off to leave the text as it is.」
  - `addon/doc/zh_TW/readme.md:52` 與 `zh_HK:52`：「設為 0 時，下列停頓都不會加入；但啟用標點停頓控制時，文字仍會在每個停頓處被切開（見下文）。」
  - `zh_TW:63` 與 `zh_HK:63`：「設為 0（預設）時不額外停頓，但啟用標點停頓控制時，文字仍會在每個停頓處被切開，因此聽起來可能和關閉時不同。」
  - `zh_TW:101` 與 `zh_HK:101`：「全域停頓參數設為 0 時，標點停頓也是 0 毫秒，但啟用標點停頓控制時，文字仍會在每個停頓處被切開；要讓文字保持原樣，請關閉標點停頓控制。」
  - `addon/doc/zh_CN/readme.md:52`：「设为 0 时，下列停顿都不会加入；但启用标点停顿控制时，文本仍会在每个停顿处被切开（见下文）。」
  - `zh_CN:63`：「设为 0（默认）时不额外停顿，但启用标点停顿控制时，文本仍会在每个停顿处被切开，因此听起来可能与关闭时不同。」
  - `zh_CN:101`：「全局停顿设为 0 时，标点停顿也是 0 毫秒，但启用标点停顿控制时，文本仍会在每个停顿处被切开；要让文本保持原样，请关闭标点停顿控制。」
  - `addon/doc/ru/readme.md:52`：「При значении 0 ни одна из перечисленных ниже пауз не добавляется; однако при включённом управлении паузами на знаках препинания текст по-прежнему разделяется в каждом месте паузы (см. ниже).」
  - `ru:63`：「При значении 0 (по умолчанию) дополнительная пауза не добавляется, но при включённом управлении паузами текст по-прежнему разделяется в каждом месте паузы, поэтому речь там может звучать иначе, чем при выключенном управлении.」
  - `ru:101`：「При общей длительности пауз 0 пауза на знаках препинания тоже равна 0 мс, но при включённом управлении паузами текст по-прежнему разделяется в каждом месте паузы; чтобы текст оставался без изменений, выключите управление паузами на знаках препинания.」
  - `addon/doc/uk/readme.md:52`：「Якщо встановлено 0, жодна з наведених нижче пауз не додається; проте якщо керування паузами на розділових знаках увімкнено, текст усе одно розділяється в кожному місці паузи (див. нижче).」
  - `uk:63`：「Якщо встановлено 0 (типово), додаткова пауза не додається, але якщо керування паузами ввімкнено, текст усе одно розділяється в кожному місці паузи, тому мовлення там може звучати інакше, ніж із вимкненим керуванням.」
  - `uk:101`：「Якщо загальна пауза очікування дорівнює 0, пауза на розділових знаках теж становить 0 мс, але якщо керування паузами ввімкнено, текст усе одно розділяється в кожному місці паузи; щоб текст залишався без змін, вимкніть керування паузами на розділових знаках.」

## Minor

### M1. `punct:111` 的 docstring 行沒有照段落的寬度換行

- 位置：`punct:109-111`。前兩行約 75 字元換行，第三行把原本兩行併成一行（108 字元，剛好在 ruff 的 110 以內，所以 prek 通過）。
- 建議：在「glued to the text.」後換行，讓「Breaks that meet without an edge break are left as they are.」自成一行，和整個 docstring 的寬度一致。純格式。

### M2. 三份中文 readme 第 63 行用「停頓點」，同一段其他行用「停頓處」

- 位置：`addon/doc/zh_TW/readme.md:63`、`zh_HK:63`（「每個停頓點的停頓長度」）、`zh_CN:63`（「每个停顿点的停顿长度」）。同段第 62、64、67 行與面板標籤「移除停頓位置的指定標點符號」都用「停頓處」或「停頓位置」，「停頓點」只在這一句出現。
- 建議：改成「每個停頓處的停頓長度」／「每个停顿处的停顿长度」。若採用 I1 的措辭，I1 也用「停頓處」。

### M3. 數字停頓的兩個性質測試仍只抽 0..500 ms（不必改）

- 位置：`tests/test_pipeline_pause_properties.py:269`、`:291`（`pause=st.integers(0, 500)`、`wait=st.integers(0, 500)`）。
- 說明：這兩個是數字停頓（群組模式、數字模式），上限 1000 ms 在 `master` 就已經如此，和本分支無關；分支只把標點停頓的五個抽樣改到 1000（`:72`、`:83`、`:175`、`:194`、`:217`），commit 內文寫得準確。要一致可以一起改成 1000，不影響正確性。

## 審閱者自行驗證的項目

| 項目 | 指令 | 結果 |
| --- | --- | --- |
| 完整測試（分支 `5d0ee7d`，scratch 複本） | `python3 -m pytest -q tests -p no:cacheprovider` | 3247 passed、0 skipped（100.86 s），與實作者回報相同 |
| 完整測試（`master` `47b98c9`，scratch 複本） | 同上 | 3240 passed、0 skipped（94.38 s）；差 7 = 新測試數 |
| prek | `prek run --all-files`（scratch 複本） | check-ast、case-conflict、yaml、trailing-whitespace、end-of-file、add-trailing-comma、ruff、ruff-format 共 8 個 Passed；沒有檔案被修改 |
| 空白檢查 | `git diff --check master` | 無輸出 |
| 受保護路徑 | `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py addon/synthDrivers/WorldVoice/unicodeScripts/unspaced_common_data.py` | 無輸出 |
| Neural | `git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 無輸出 |
| voice contract 測試 | `git diff master -- tests/test_plugin_voice_contract.py` | 無差異 |
| commit 訊息 | `git log --format=%B 47b98c9..5d0ee7d` | 2 個 commit，英文 `feat:`／`docs:` 加內文；`Co-Authored-By` 0 個 |
| `master` 位置 | `git -C /workspace/WorldVoice rev-parse master` | `47b98c9`，分支可 fast-forward |
| 分支改動範圍 | `git diff --stat 47b98c9..5d0ee7d` | 11 個檔案：settings.py、punctuation.py（docstring）、3 個測試檔、6 份 readme |
| 呼叫端 | `grep -rn "scaled_punctuation_wait\|PUNCTUATION_WAIT_UNIT_MS\|MAX_PUNCTUATION_WAIT_MS"`（排除 `ref/`） | `addon/` 只有 `punct:134` 一個呼叫；常數只剩守門測試；UI、`.po`、globalPlugins 無「5 ms」「500」文字 |
| 突變探針 a：還原 `min(factor*5, 500)` | 8 個相關測試檔 | 9 failed／972 passed：換算表 5 列、Hypothesis 性質、真實設定 3 列 |
| 突變探針 b：加回 `min(..., 500)` | 同上 | 3 failed：換算表 `[100,100→1000]`、性質測試、真實設定 `[100-100-1000]` |
| 突變探針 c1：`scaled_punctuation_wait() <= 0` 時整個階段 `yield from` | 同上 | 31 failed：`test_zero_wait_*` 全部、`[0-30-0]`、兩個 Hypothesis 性質 |
| 突變探針 c2：只在 `pause_cmd.time > 0` 才送 break（仍移除標點） | 同上 | 20 failed：含 `[0-30-0]`、`test_zero_wait_*`、`test_worldvoice_speak.py::test_main_language_numbers` 3 列 |
| 突變探針 d：`self.global_wait_factor * factor`（不 `// 10`） | 同上 | 7 failed：換算表 `global 9`、`10`、`25`、`100` 四列、性質測試、真實設定 `[10-30-30]`、`[100-100-1000]` |
| Review Focus 探針（真實 `PipelineSettings` 跑完 `STAGES`，11 個 case） | scratch 複本的臨時測試檔 | 11 passed，結果見下表 |
| 看門狗 | 每個 pytest 外層 MemAvailable < 3 GB 即停 | 全程沒有觸發（起始 MemAvailable 5.6 GB） |

### Review Focus 探針

| 情境 | 設定 | `STAGES` 全部跑完的輸出 |
| --- | --- | --- |
| 全域 0、開關開、字元「. 」、標點 30、數字模式、數字／項目／空白停頓 10 | `["Hello. 第3章 World", "role"]` | `["Hello", ". ", PB0, "第3章", " ", PB0, "World", "role"]`：數字、項目、不分詞空白階段在 0 時全部跳過，只有標點階段在兩個停頓處各放一個 0 ms break；「. 」是一個停頓處 |
| 全域 0、字元「. 」、數值模式 | `["中 文 a b"]` | `["中", " ", PB0, "文", " ", PB0, "a", " ", PB0, "b"]` |
| 全域 10、同上 | `["中 文 a b"]` | `["中", B10, "文", PB30, "a", PB30, "b"]`：中文間的空白用不分詞空白停頓（10），其餘用標點停頓（30）；空白項目被 `number_wait_factor` 階段去掉，與 `master` 相同 |
| 全域 100、標點 100 | `["Hello.World"]` | `scaled_punctuation_wait() == 1000`；`["Hello", ".", PB1000, "World"]`，沒有上限 |
| 平手：數字 30、標點 30、數字模式 | `["Total. 12"]` | `["Total", ".", PB30, "1", NB30, "2"]`：標點停頓（非 edge）勝出 |
| 數字 30、標點 20 | 同上 | `["Total", ".", E30, "1", NB30, "2"]`：較長的 edge break 勝出 |
| 數字 30、標點 40 | 同上 | `["Total", ".", PB40, "1", NB30, "2"]` |
| 三方平手：項目 30、數字 30、標點 30 | `["Total.", "12"]` | `["Total", ".", B30, "1", NB30, "2"]`：只剩一個 30 ms，不是 edge break |
| 其他合成器、scope `WorldVoice`、全域 50、標點 20 | `effective(supports_roles=False)` | `punctuation_wait_factor == 0`、`punctuation_pause_enabled is False`、`scaled_punctuation_wait() == 0`；`["Hello. World"]` 原樣通過 |
| 其他合成器、scope `all` | 同上 | `effective()` 回傳原物件；`scaled_punctuation_wait() == 100`；輸出含 PB100 |
| 預設與範圍 | `PIPELINE_SETTING_BY_KEY["punctuation_wait_factor"]` | default 0、min 0、max 100；`convert(500) == 100`、`convert(-3) == 0`；confspec `integer(default=0,min=0,max=100)` |

## 使用者還沒確認的使用者可見預設

- **I1 的文件措辭**（六種語言各三句）是審閱者提議的，使用者未確認；行為本身（0 ms break 仍切開文字）是使用者決定的。
- **M2 的「停頓處」用詞**是審閱者提議的。
- 以下是使用者已經決定、這裡只列出提醒的可見變化：不遷移設定值，所以已把標點停頓參數調成非 0 的使用者在預設全域 10 下會聽到停頓從 5N ms 變成 N ms；全域 0 現在也把標點停頓變成 0 ms（先前不受影響）；最大停頓從 500 ms 變成 1000 ms。
- Linux 上只驗證到 pipeline 輸出與 `Pause(0.0)` 的切分；0 ms break 在 Windows 各引擎（VE／Cerence／OneCore／SAPI5／eSpeak／RHVoice）實際聽起來和關閉開關差多少，沒有在這裡驗證，屬於手動項目。
