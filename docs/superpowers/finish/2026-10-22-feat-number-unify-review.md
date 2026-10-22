# Number unify Review 紀錄

日期：2026-10-22。分支：`feat/number-unify`（`967944e..e81b278`，30 個 commit），worktree `/workspace/WorldVoice-feat-number-unify`。
依據：

- 規格 `docs/superpowers/specs/2026-10-22-feat-number-unify-design.md`（使用者決定 Q1–Q7、V1–V7、L1、N、O、P、F1 option D、F2、F3、NB rule、R；V5 與 Q-A～Q-G 為協調者預設）
- 決定紀錄 `scratchpad/unify-decisions.md`（後面的條目取代前面的：Q4 被 F1 D 取代，批次 1 M3 被 Q 取代，Ruling 1／Ruling 9／批次 2 I1 被 R 取代）
- 計畫 `docs/superpowers/plans/2026-10-22-feat-number-unify.md`（Review Focus 1–5；第 4 項已依使用者決定改寫）
- 進度帳本 `.superpowers/sdd/2026-10-22-feat-number-unify/progress.md`（25 個 `Ruling:`）
- 批次 1、批次 2 的 Fable review（無 Critical／Important；批次 2 的 I1 已被使用者的決定 R 取代）；批次 3（Task 10–13）沒有批次 review，本次加重檢查。

流程：審閱者 Fable 5.1，唯讀。測試、端對端探針、種子突變與 mutmut 子集都在 scratchpad 的暫時 detached worktree（`rv/wt`，審完已移除）進行；單一 pytest 行程，記憶體監控在 MemAvailable 低於 3 GB 時停掉。`ref` 為指向 `/workspace/WorldVoice/ref` 的 symlink，NVDA `7d25bc76e`，與 spec 相同。

`file:line` 以 `e81b278` 為準；NVDA 的行號以 `ref/nvda` `7d25bc76e` 為準。

## 結論

Ready to merge：**是。** Critical 0、Important 0、Minor 6。

- **程式與使用者的全部決定相符。** spec 7.1（16 列 × 5 種模式）、7.2（number language en 的 8 列）、7.3（與 master 的 12 項差異）都用 NVDA 真正的 `characterProcessing` 與符號表跑過一遍（見驗證表），每一格都和 spec 一致；NB rule（U+00A0／U+202F／U+2007 當一般空白）、R（沒有名稱的符號自成一項、兩側都有 NB）、O（number wait 穿透語言命令，舊 F4 修好）、V6（`effective()` 不再和全域停頓耦合）都有對應測試，而且我種的 21 個突變全部被殺。
- **I1 的 `35e7793` 已被 `b107288` 完整取代。** `git grep` 在 `addon/` 找不到 `glue`、`last_is_name` 或任何黏接邏輯；`_translate_number`（`pipeline/__init__.py:395-430`）只剩「名稱或原字元，各自一片」一條路徑。
- **25 個 Ruling 都合理**（逐項評估見下）。唯一有使用者可見代價的是 `_symbol_locale` 的「bare language」規則（M10：NVDA 介面英文、數字語言 `zh` 時名稱是英文），帳本與 spec 都已記為已知代價並列入手動項目。
- **批次 3 的 P8／P9／P10 與 SSML 測試確實守住它們聲稱的東西**，但 P9 只在測試樁（名稱全是字母）之下有意義：NVDA 真正的表裡，法文的四個名稱含撇號（M1）。
- Linux 上驗證不到的：六個引擎對「名稱是一般文字」的實際發音（M1–M3）、`speech.getCurrentLanguage()` 在真實 NVDA 下的值（M10）、升級情境（M7）。

## Critical

無。

## Important

無。

## Minor

### M1. spec 8「名稱不含 ASCII 標點」只對 en／zh_TW 成立；法文表的四個名稱含撇號，P9 只在測試樁下成立

- **位置：** spec `:443`（「A name holds no ASCII punctuation in any NVDA table probed」）、`:183`（探針只檢查「名稱 ≠ 符號本身」）；`tests/test_pipeline_nvda_symbols.py:117-126`（`test_every_number_symbol_has_a_name` 只斷言非空且不等於符號）；`tests/test_pipeline_pause_properties.py:705-719`（P9 用 harness 的 `symbol_name`，名稱永遠只有字母和空白）。
- **審閱者實測：** 用 NVDA 真正的 `characterProcessing` 對 55 個 SYM 查 en、zh_TW、zh_CN、ja、de、fr：只有 fr 的 `!`→`point d'exclamation`、`?`→`point d'interrogation`、`¡`、`¿` 含 `'`（U+0027，本身是 SYM）。其餘語言全部只含字母與空白。
- **情境：** 數字語言 fr（或 NVDA 介面法文、數字語言 default）、數字／群組模式、標點停頓字元含 `'`、移除標點開啟時，`"1!2"` 的名稱 `point d'exclamation` 會被標點階段切成 `point d` PB `exclamation`（撇號被移除）。需要四個條件同時成立，而且 `!`／`?` 夾在數字中間很少見，所以只是 Minor。
- **建議：** `test_every_number_symbol_has_a_name` 加一個斷言：en 與 zh_TW 的每個名稱都不含 SYM 字元（`is_number_symbol`），把 spec 8 的說法鎖在真正的表上；spec `:443` 改成「en 與 zh_TW 的表」。fr 的情況記為已知，不用改程式。

### M2. 沒有名稱的符號被「移除標點」拿掉後，兩個 NB 相鄰（停頓變成 2 倍數字停頓）

- **位置：** `pipeline/__init__.py:660-673`（移除時不 yield 該符號，但兩側的 `NumberBreakCommand` 已由 `_translate_number` `:426-430` 放好）；`tests/test_pipeline_filters.py:556-572`（只斷言文字項目在 `("12", ".", "5")` 之內）；P10 `tests/test_pipeline_pause_properties.py:626-652` 的字母表全部有名稱，所以 X1 性質看不到這個情況。
- **審閱者實測（NVDA zh_TW 表，`.` 與 `,` 的名稱清空）：** `"12.5"` 群組 3、標點 `.,:-`、移除開啟 → `'12' NB NB '5'`；`"1..2"` → `'1' NB NB NB '2'`；`"1,234.56"` 數字模式 → `'1' NB NB '2' NB '3' NB '4' NB NB '5' NB '6'`。只開停頓不移除時，`.` 保留且不加標點停頓（NB 已在前面，符合既有「既有 break 抑制邊界停頓」規則）。
- **情境：** 使用者在符號字典把 `.` 的替代清空、又開啟「移除配置的標點」時，`12.5` 在群組模式聽到 `12`、20 ms 停、`5`，而不是 10 ms。使用者已接受「可能被標點階段移除」，但堆疊的 NB 沒有被明說。
- **建議：** 不修也可以；要修的話在 `inject_punctuation_pause` 的 `emit` 裡，當整個項目被移除且前一個已 yield 的是 `BreakCommand` 時，跳過 `pending_breaks` 裡的第一個 NB。或在 spec 6.4.1 補一句「移除後兩個 NB 相鄰」，並讓 P10 的字母表加入一個無名稱符號。列為未確認預設。

### M3. 數字語言為 bare `zh`、NVDA 介面英文時，中文語音讀英文名稱（已知代價，帳本 Ruling、spec M10）

- **位置：** `pipeline/__init__.py:94-108`（`_symbol_locale`：bare language 只在與 `speech.getCurrentLanguage()` 的 base 相同時取 NVDA 的國家）；spec `:656`（M10）。
- **審閱者實測：** NVDA locale `en`、數字語言 `zh`：`2×3` 數字模式 → `'2' NB 'times' NB '3'`；`45°30` → `… 'degrees' …`。NVDA locale `zh_TW` 時同樣輸入是 `乘以`、`度`。
- **情境：** 台灣使用者把 NVDA 介面設成英文、數字語言選中文語音，中文語音會讀「2 times 3」。這是 Ruling 記錄的代價，不是缺陷；但它是這個功能最可能被回報的「奇怪發音」。
- **建議：** 維持現狀並靠 M10 手動項目確認。若使用者覺得不能接受，便宜的改法是在 `_symbol_locale` 找不到表時改查數字語言語音自己的 locale（`VoiceSpec.language`，例如 `zh_TW`），需要 `SpeechContext` 多帶一個 `voice_locale_for_language` 回呼，屬下一輪工作。

### M4. zh_HK readme 仍列出已移除的「忽略在數字間的逗號」（帳本 Task 12 Ruling）

- **位置：** `addon/doc/zh_HK/readme.md:39`、`:48`。
- **情境：** zh_HK 介面的使用者在說明文件看到一個面板上找不到的選項。
- **建議：** spec 3 把其他語言的 readme 留給譯者，Ruling 合理；但這份是中文、改法與 zh_TW 完全相同（刪兩行、改三行），建議 merge 前順手比照 zh_TW 改掉，或在交接紀錄列為待譯者處理。

### M5. P8 的比較刻意忽略空白與標點停頓，所以「數字語言不改變任何字或停頓」只對 NB 成立

- **位置：** `tests/test_pipeline_pause_properties.py:668-700`（`spoken_between_number_breaks` 只看 NB 之間、去掉所有空白；`punctuation_pause_enabled = False`）；帳本 Task 10 Ruling 已記錄這個代價。
- **審閱者實測：** 這是 master 既有、與本分支無關的差異：value 模式 `"There are 5. Next"` 無數字語言 → `'There are 5 . Next'`（dot rule 補空白）；有數字語言 → `<en> '5' <zh_TW> '. Next'`（wrapper 先切開項目，dot rule 看不到句點）。P8 看不到這個差異是設計使然，不是漏洞。
- **建議：** 不用改。在 P8 的 docstring 補一句「dot rule 的空白與標點停頓位置可能因 wrapper 切項而不同（master 既有）」，免得下一位讀者以為它涵蓋。

### M6. `test_an_unnamed_symbol_is_left_to_the_punctuation_stage` 的斷言兩種結果都接受

- **位置：** `tests/test_pipeline_filters.py:556-572`：`all(item in ("12", ".", "5") for item in texts)` 在「`.` 被移除」和「`.` 保留」時都通過，所以它守的是「數字兩側分開、沒有東西黏在一起」，不是標點階段對它的處理。
- **建議：** 既然使用者接受的是「可能被停頓或移除」，這樣寫可以；但測試名稱暗示它鎖住了結果。改成明確斷言目前的結果（移除開啟 → `["12", "5"]` 且兩個 NB 相鄰；只開停頓 → `["12", ".", "5"]`），和 M2 一起決定。

## Review Focus 逐項檢查

| # | 項目 | 結果 |
| --- | --- | --- |
| 1 | bare `zh` 不能給中文語音英文名稱 | `_symbol_locale("zh")` 在 NVDA zh_TW 下是 `zh_TW` → `乘以`（`test_symbol_locale`、`test_pipeline_names_symbols_with_nvdas_real_lookup`，種子突變 M12 被殺）。NVDA 介面英文時仍是英文名稱（本審 M3，已知代價）。 |
| 2 | `zh-TW`／`en-US` 要正規化成 `_` | `test_symbol_locale[zh_TW-zh-TW-zh_TW]`，種子突變 M06 被殺；端對端以 `LangChangeCommand("de_CH")` 得到 `Mal`（base fallback）。 |
| 3 | 長符號串的效能與查表次數 | `test_long_symbol_runs_look_each_symbol_up_once_per_item`（種子突變 M19 被殺）。審閱者實測 40k 字元的 IP 串、版本串、`1-`×20000 在三個數字階段 ≤ 170 ms；全部階段 700 ms 的案例是標點階段（master 既有）。 |
| 4 | 無名稱符號與移除標點（已改為使用者決定 R） | `test_an_unnamed_symbol_is_left_to_the_punctuation_stage`、`test_property_every_symbol_is_its_own_item_when_some_have_no_name`；種子突變 M20（黏回數字）被殺。堆疊 NB 見 M2。 |
| 5 | 瀏覽模式把一個數字切成兩個項目 | `test_thousands_step_passes_commands_and_split_items`（`["12", Marker, ",345"]` 原樣、命令同一物件）。 |

## Ruling 評估

| Ruling | 評估 |
| --- | --- |
| spec 層：無名稱符號黏回數字（Ruling 1）；Task 7 Ruling 9（名稱之後開新片） | 已被使用者決定 R 取代，程式中沒有殘留（`git grep glue\|last_is_name` 無結果）。 |
| spec 層：`None` → `speech.getCurrentLanguage()` | 合理：與 NVDA 自己的 `processText` 起點一致（`speech.py:1177`）。 |
| spec 層：`-`→`_`、bare language 取 NVDA 國家 | 合理；代價（M10）已記錄，見本審 M3。 |
| .po 跟各 task 走 | 合理（否則 catalog 測試在 task 之間失敗）。 |
| Task 4：guard「controller depends」改用 `punctuation_pause_enabled`；ring 斷言改為「全部在 ring」 | 合理；兩個案例仍各自觸發同類錯誤。 |
| 批次 1 M4+M5：timing 0.05→0.5 s、字串用 `==` | 合理。 |
| 批次 1 M1：sign lookbehind 是等價突變 | 正確：左到右掃描時，前一個數字已屬於前一個 match。 |
| 批次 1 M2：55 個 SYM | 審閱者實測 `len(_SYMBOLS) == 55`。 |
| 批次 1 M3：NBSP 分組（`e8e282c`）→ 使用者反轉（`c21cdb4`、`ee07c55`、`58ab03d`） | 反轉乾淨：`_NO_BREAK_SPACES`、`_is_splittable_gap`、`_GROUPED_NUMBER_RE` 都不存在；`10 000` 在六種組合都是 `10` NB `000`。 |
| Task 6：`off` 進 `CHANGED_LABEL_MSGIDS`；panel_layout 的 (group, 2) 案例保留 | 合理。 |
| Task 7：拿掉 `("group", 1, 0)` 列 | 合理：群組大小 1 已不合法；size 1 路徑由 number 模式測。 |
| Task 7：P7 oracle 把前導正負號當符號是測試錯 | 正確（spec 6.4：正負號併入第一片）。 |
| Task 7：SSML 與 break-set 測試提前更新 | 合理。 |
| Task 7 M6：每次 stage run 快取 locale 與名稱 | 合理；`_symbol_namer` `:433-449`。 |
| Task 8：disabled-not-hidden 改檢查 group size spin | 合理。 |
| Task 10：P8 只比 NB 之間、標點停頓關 | 合理，見本審 M5。 |
| Task 12：zh_HK readme 不改 | spec 非目標，但見本審 M4。 |
| Task 13：存活突變 `previous = _MISSING → None` 等價 | 正確：`_both_numbers(None, item)` 經 `_both_text` 必為 False，和 `_MISSING` 分支同義。 |

## 審閱者自行驗證的項目

| 項目 | 結果 |
| --- | --- |
| `python3 -m pytest -q tests`（任務 worktree，單一行程，記憶體監控） | 2241 passed、0 skipped、2 warnings（既有的 `codecs.open` DeprecationWarning） |
| `prek run --all-files` | 8 個 hook 全數 Passed |
| `git diff --check master` | 無輸出 |
| 受保護路徑 `git diff --stat master -- 'driver/*/driver/' driver/sonic/ languageDetection/script_data.py`；`git ls-files …/driver/Neural` | 兩個指令都無輸出 |
| `git log master..HEAD` 的 `Co-Authored-By` | 30 個 commit 都沒有 |
| `msgfmt --check -o /dev/null addon/locale/zh_TW/LC_MESSAGES/nvda.po` | rc=0，無輸出 |
| 跨驅動 import | `driver/*/__init__.py` 只 import `...runtime`／`..compat`（core），沒有驅動互相 import |
| `ref` symlink | `ref -> /workspace/WorldVoice/ref`，`ref/nvda` 為 `7d25bc76e` |
| 殘留的舊符號（`group_wait`、`groupwaitfactor`、`ignore_comma`、`cni`、`GroupNumberBreak`、`get_translate_table`、`speech_symbols`、`_PURE_NUMBER`、`_NO_BREAK_SPACES`、`_is_splittable_gap`、`glue`、`last_is_name`、`CharacterMode`） | `addon/`、`readme.md` 只剩 `DEAD_MSGIDS` 與「已移除」的負向測試；zh_HK readme 例外（M4） |
| spec 7.1／7.2／7.3 端對端（每個 `Stage.fn` 依序、NVDA 真正的 `characterProcessing` 與 `ref/nvda/source/locale` 符號表、44 個輸入 × 5 模式 × NVDA locale zh_TW／en × 數字語言 default／en／zh） | 每一格與 spec 相同。例：`12,345,678` value → `12345678`；group 3 → `12 NB comma NB 345 NB comma NB 678`；`2026-10-22 12:30` value → `2026-10-22 NB 12:30`；`5-3` 數字語言 en value → `<en> 5-3 <zh_TW>`；`2×3` 數字語言 en 數字模式 → `<en> 2 NB times NB 3 <zh_TW>`，數字語言 zh（同語音，wrapper 被去重）→ `2 NB 乘以 NB 3`；`12，34` 數字模式 → `1 NB 2，3 NB 4`；`１２` 不動；`1 2` 數字語言 en → `<en> 1 <zh_TW> NB <en> 2 <zh_TW>` |
| 使用者符號字典清空 `.`／`,` 的名稱 | `12.5` 數字模式 → `1 NB 2 NB . NB 5`；`1-.2` → `1 NB dash NB . NB 2`；`1.-2` → `1 NB . NB dash NB 2`（spec 6.4.1）。開標點停頓不移除：`.` 保留、不另加 PB；開移除：`.` 消失、兩個 NB 相鄰（M2） |
| 互動：標點停頓 30 ms＋移除、項目停頓 7、中文空白 5，數字語言 en | 名稱從不被標點階段動到；NB 旁永遠沒有其他 break；`中 文 12.5 字` → `中 Br5 文 <en> 12 NB dot NB 5 <zh_TW> 字`；`12.5, then 3.` → `<en> 1 NB 2 NB dot NB 5 <zh_TW> PB then <en> 3 <zh_TW> .` |
| NVDA `LangChangeCommand` 序列（`["abc", LC("en"), "2×3 and 1 2", LC(None), "4÷2", LC("de_CH"), "7×8"]`，數字語言 default） | 名稱跟著語言命令：`times`、`除以`、`Mal`；`LC(None)` 回到 `ctx.language`；數字語言 en 時全部是英文名稱 |
| Scope all：`GENERIC_CONTEXT` 經 `stage.handler` | 只有 `BreakCommand`（`_plain_breaks`）；名稱是純文字；locale 跟 NVDA 的 `LangChangeCommand`（`zh_TW` → `乘以`，否則 `getCurrentLanguage()`） |
| 效能（40k 字元）：`1`×20000、`1.`×10000+a、`1,234`×5000、`1 `×10000、IP×3000、`1-`×20000、`+-`×10000+1、`,`×20000 | 三個數字階段 value ≤ 7 ms、number／group ≤ 170 ms；`symbols10k` 全部階段 700 ms 是標點階段產生 30k 項目（master 既有，與本分支無關） |
| NVDA 真正的符號表：55 個 SYM 的名稱是否含 SYM 字元 | en、zh_TW、zh_CN、ja、de、zh：無；fr：`!`、`?`、`¡`、`¿` 含 `'`（M1） |
| `len(_SYMBOLS)` | 55（批次 1 M2） |
| 種子突變（暫時 worktree，21 個，各跑 9 個相關測試檔 `-x`） | 全部被殺：number wait 不穿透語言命令、名稱改為原字元、pause 0 不放 NB、千分位在所有模式移除、名稱不跟語言命令、locale 保留 `-`、千分位 lookahead 改回決定文字的 `(?![0-9]\|,[0-9])`、split 只認一般空格、off 模式消失、分隔符放兩次、正負號丟失、bare language 規則消失、NB 放在所有 held 命令之後、`_plain_breaks` 不轉換、每個 stage 都有 log switch、`convert` 用 `stored_min_value` 夾住、`effective()` 不歸零 number wait、名稱忽略數字語言、名稱不快取、無名稱符號黏回數字、off 模式仍跑 dot rule |
| 只用 `test_pipeline_pause_properties.py`（P1–P10）與 `test_pipeline_nvda_ssml.py` 對 8 個種子突變（批次 3 的測試是否自己能抓） | 7 個被殺：number wait 不穿透 → P8；名稱改原字元 → P7 與 SSML 名稱測試；pause 0 不放 NB → P7、無名稱性質等 6 個；分隔符放兩次 → P10 與 SSML；正負號丟失 → P5；`_plain_breaks` 不轉換 → 兩個 SSML 測試；無名稱符號黏回數字 → 無名稱性質。1 個存活：NB 放在所有 held 語言命令之後——P8 刻意只比 NB 之間的文字，位置由單元測試 `test_number_wait_breaks_between_numbers_across_language_commands` 鎖住（Q-C 說明任何位置聲音相同），符合預期 |
| mutmut 3.8.0 子集（`_insert_number_breaks`、`_translate_number`、`remove_thousands_separators`、`_symbol_locale`、`_both_numbers`；3 children、記憶體監控、暫時 worktree） | 102 個突變（與帳本表格的 12+47+14+18+10 = 102 相同）：101 killed、1 survived。存活的是 `x__insert_number_breaks__mutmut_1`（`previous = _MISSING` → `None`），與 Task 13 回報的同一個等價突變；沒有其他存活、timeout 或 suspicious。對 274/275 的整體數字，審閱者只重跑了這五個函式的子集（其餘函式以 21 個種子突變抽查） |
| I1 `35e7793` 是否被 `b107288` 完整取代 | `b107288` 刪除 `glue`／`last_is_name` 路徑（`pipeline/__init__.py` −25/+8），`35e7793` 的測試輸入 `1.-2` 在新規則下保留；`addon/` 無殘留 |
| 設定與 UI | 表格順序 scope、global wait、number language、number mode、group size、number wait…（`test_table_lists_every_setting_in_the_canonical_order`）；兩個面板「off」在最前、未知值顯示 value（index 1）；spin 2..10、儲存 1 顯示 2；confspec 仍 `min=1`（`stored_min_value`）；guard 新增兩個案例；ring 順序與名稱；Voice panel 的 Group size 緊接 nummod（`test_group_size_follows_the_number_mode_list`，前一功能的建立順序仍成立）；`LOG_SWITCHES` 無重複、Log Record 面板一個 label 一個開關、`number_mode` 開關記兩個 stage |
| 翻譯 | `off`→「不處理」有 `# Translators:`；`Ignore commas between numbers`、`Group wait factor` 移入 `DEAD_MSGIDS` 且 .po 已刪；EN／zh_TW readme 的四個 bullet 與 spec 10 的建議文字一致，用詞與既有介面一致 |
| 與 master 相比、預設值使用者（value、數字語言 default）聽到的差異 | 僅 spec 7.3 所列：千分位逗號移除；`192.168.0.1`、`1.2.3` 不再加點的空白；`2026-10-22 12:30`、`02 2345-6789`、`3-1 2` 之間多一個 NB；`10 000` 變兩個數字；`["12:30", "1"]`、`["5-3", "4"]` 兩項之間多 NB。沒有其他差異 |

## 使用者還沒確認的使用者可見預設

1. **V5：** 值 `none`、標籤 `off`／「不處理」、排在清單第一；預設仍是 value（協調者預設）。
2. **Q-A～Q-G（協調者預設）：** 數字只有 ASCII `0-9`（全形 `１２` 不是數字）；相鄰符號各念一次（`1--2` → `1` NB `dash` NB `dash` NB `2`）；NB 放在第一個 held 語言命令之後；千分位步驟記在 `number_mode` 開關下；lookahead `(?!,*[0-9])`；`off` 用一般 `_()`；`speech_symbols` 與 `_PURE_NUMBER_RE` 移除。
3. **`_symbol_locale` 的三條規則：** 另一個合成器用 `speech.getCurrentLanguage()`；`-`→`_`；bare language 只在與 NVDA 目前語言同 base 時取其國家，否則 NVDA 退回英文名稱（M3／手動 M10）。
4. **無名稱符號被「移除標點」拿掉後兩個 NB 相鄰**（M2）。
5. **zh_HK readme 仍寫著已移除的選項**（M4）。
6. **儲存的群組大小 1 讀成 2，檔案裡的 1 直到下次存檔才改**（spec 10）。
7. **number wait 現在也穿過 NVDA 自己的 `LangChangeCommand`**（O 決定「LangChangeCommand 與 WVLangChangeCommand 都透明」）：兩個分開的項目 `["… 1 2", LangChangeCommand(None), "4÷2"]` 之間也會有 NB；master 上語言命令會擋住停頓。
8. **法文表的 `!`、`?`、`¡`、`¿` 名稱含撇號**，標點停頓字元含 `'` 且開啟移除時會被切開（M1）。
9. **spec 13 F3 已接受的 value 模式副作用**：`192.168.0.1` 失去點的空白、日期與時間之間多停頓、`5-3` 整個被數字語言包住。
10. **`1.234,567`（德式）在 value 模式變 `1.234567`**（spec F7，屬已接受的 de/fr 風險）。

## Windows／NVDA 仍待手動驗證

spec 11.5 的 M1–M10 全部仍待 Windows 驗證；Linux 上只驗證了 pipeline 的輸出與 NVDA 的 `characterProcessing`／`speechXml` 純 Python 部分。特別留意：

- M1／M2：六個引擎對名稱（`dot`、`dash`、`乘以`、`度`）的實際發音，以及符號等級 none／some／all 下名稱是否都被唸出。
- M7：舊設定檔（`group_size = 1`、`group_wait_factor = 40`、`ignore_comma_between_number = True`）載入後 WorldVoice 正常啟動、面板顯示 2、沒有已移除的控制項。
- M10：NVDA 介面英文、數字語言 zh 時聽到的名稱語言（本審 M3）。
