# Phase 31 Review 紀錄：拆分 `pipeline/__init__.py`

日期：2026-10-22。分支：`phase31-split-pipeline`（`41dc50d..98590ac`，9 個 commit），worktree `/workspace/WorldVoice-phase31`。
依據：

- 規格 `docs/superpowers/specs/2026-10-22-phase31-split-pipeline-design.md`（`fd9bd8a`；使用者決定 D1–D4，§13 的 Q1–Q6 為協調者預設）
- 計畫 `docs/superpowers/plans/2026-10-22-phase31-split-pipeline.md`（`a130d94`；Review Focus 1–5；`98590ac` 補上 mutmut 前後表）
- 進度帳本 `.superpowers/sdd/2026-10-22-phase31-split-pipeline/progress.md`（1 個 `Ruling:`）
- 第六輪審查 `storage/refactor6.md` §1.1、§1.2、§11「階段 31」
- `DEVELOPMENT_WORKFLOW.md` §3.3、§7、§8

流程：審閱者 Fable 5.1，唯讀。測試、master 對照、守門種子突變與 mutmut 都在 scratchpad 的兩個暫時 worktree（`p31review-master` 在 `41dc50d`、`p31review-branch` 在 `98590ac`，`ref` 以 symlink 接到主 checkout，審完已 `git worktree remove` 並 `prune`）進行；pytest 單一行程、mutmut 3 個 child，皆有 3 GB MemAvailable 記憶體監控（全程最低約 5.9 GB）。沒有 push、沒有 stash、沒有動主 checkout 與 `scratchpad/p31`。

`file:line` 以 `98590ac` 為準；master 的行號以 `41dc50d` 為準；NVDA 以 `ref/nvda` `7d25bc76e` 為準。

## 結論

Ready to merge：**是。** Critical 0、Important 0、Minor 4。

- **搬家是逐字的。** 用 AST 把 master 的 10 個搬走的定義（5 個常數、`_split_spaced_numbers`、`_has_symbol_table`、`_symbol_locale`、`_symbol_name`、`_symbol_namer`）去掉 docstring、套用 D3 更名後，與 `numbers.py`／`symbols.py` 的新定義逐一比對，**全部相同**；`__init__.py` 其餘 30 多個頂層定義也只差更名（`NUMBER_RE`、`symbol_namer`）或呼叫 `strip_thousands`／`split_spaced_numbers`／`number_pieces`，沒有新增的頂層名稱。
- **行為沒有變。** 對 master 與分支各跑同一支探針：40 個代表字串 × 4 種序列（純字串、夾 `LangChangeCommand`、夾 `WVLangChangeCommand` 與 `BreakCommand`、拆半）× 4 種數字模式（group 另跑 1/2/3 位）× 數字停頓 0/50 × 11 個 context（generic；roles 的 language zh/en/None × number_language default/en/zh；沒有語音 locale）× 3 種符號命名（有名、全部無名、`LookupError`），共 **61,776 個案例**，每個案例記錄九個 stage 各自的輸出與九段串接後的輸出。兩邊的 JSON（79.6 MB）**逐位元組相同**。
- **快取正確。** 鍵是 `languageHandler.normalizeLanguage` 的輸出（`symbols.py:50-51`），只有它會進 `has_symbol_table`；`speech.getCurrentLanguage()` 仍每次 stage 執行都問（`:53`），種子實驗把它一起快取後 `test_symbol_tables_are_probed_once_per_locale` 立刻失敗。路徑只依賴 `globalVars.appDir`，NVDA 在 `nvda.pyw:41-59` 啟動時設定一次；NVDA 自己對同一組檔案也是一次 run 只 glob 一次（`characterProcessing.py:836-846` 的 `cached_property`）。`lru_cache` 的 C 實作對同時讀寫安全，最壞是同一個 `bool` 算兩次。
- **Review Focus 1–5 與唯一的 Ruling 都成立**（見下方逐項）。
- **mutmut 前後表與實作者記錄一致**：審閱者在 scratch 複本重跑兩個新模組與兩個被拆的函式，163 個 mutant、160 killed、3 survived，存活的正是記錄的三個等價突變；另外 7 個 master 既有的存活 mutant，審閱者讀了 mutmut 產生的原始碼差異，確認都等價（見「mutmut」節）。

## Critical

無。

## Important

無。

## Minor

### M1. Guard B 的 import 檢查比 Guard A 鬆：`import os.path`、`from os.path import isfile` 與函式內的 import 都抓不到

- **位置：** `tests/test_pipeline_structure.py:13-21`（`imported_modules` 只看 `tree.body`，而且比對整個點號名稱）、`:81-96`（Guard B 用它比對 `{"os", "unicodedata", "characterProcessing", "globalVars", "languageHandler", "speech"}`）。Guard A（`:34-46`）則用 `ast.walk` 並取 `split(".")[0]`。
- **情境（審閱者實測）：** 在 scratch 複本的 `__init__.py` 分別種入 `import os.path` 與 `from os.path import isfile`，Guard B 都 3 passed；種入 `import os`、`import characterProcessing`、`from speech import getCurrentLanguage` 則都 1 failed。也就是「檔案探測回到套件」這一半的守門，只要寫法換成子模組就繞過了。
- **建議：** 把 `imported_modules` 改成 `ast.walk` 並比對 `name.split(".")[0]`（`speech.commands`／`speech.extensions` 會因此變成 `speech`，所以 Guard B 要改成列出允許的 `ImportFrom` 完整名稱，或改以「`speech` 這個名稱不得被綁定」來判斷，例如只檢查 `ast.Import` 的 `speech` 與 `ImportFrom` 的 `module == "speech"`）。不改也不影響合併；名稱那一半（`MOVED`，`:51-66`）已能抓到逐字複製回來的情況（種子 `_symbol_locale`、`_SENTENCE_END_RE` 都 1 failed）。
- **附註（設計限制，非缺陷）：** 以新名稱重寫一份查詢（種子 `_symbol_lookup`）任何名稱守門都抓不到；spec §7.4 已說明選這種形式的理由，接受。

### M2. 快取測試把全域的 `os.path.isfile` 換掉

- **位置：** `tests/test_pipeline_nvda_symbols.py:145-146`。`module.os` 就是標準庫的 `os`，所以 `monkeypatch.setattr(module.os.path, "isfile", …)` 在測試期間對整個行程生效；`:150` 再對每一條記錄做 `Path(path).relative_to(app_dir)`。
- **情境：** 目前測試本體內只有 `symbol_locale` 會呼叫 `isfile`，所以穩定（monkeypatch 結束會還原）。但將來若 `symbol_namer` 的路徑上多了任何一次對 appDir 之外路徑的 `isfile`（例如 NVDA 的 `languageHandler.normalizeLanguage` 哪天改成查檔案，或測試中途加了會碰檔案的 helper），`relative_to` 會丟 `ValueError`，錯誤訊息不會說是快取壞了。
- **建議：** 只記錄 `app_dir` 底下的路徑（`if Path(path).is_relative_to(app_dir)`），或把 `module.os` 換成只帶 `path.isfile`／`path.join` 的 `SimpleNamespace`。一行的事，可留到下次碰這個檔案時順手改。

### M3. 既有的 mutation 記錄與這次的基準數不一致（master 既有，非本階段造成）

- **位置：** `e81b278`（number-unify 的記錄）寫 `iter_number_speech_segments_mode` 35 個 mutant、0 存活；本階段在 `41dc50d` 的基準與 `98590ac` 的後測都是 35 個、4 存活（`_1`、`_4`、`_34`、`_35`），而 `git show 844d8d2:…/pipeline/__init__.py` 的函式本體與現在逐字相同。`iter_number_speech_segments_language` 則不在 `e81b278` 的清單裡。
- **審閱者驗證：** 讀 mutmut 產生的 `x_iter_number_speech_segments_mode__mutmut_{1,4,34,35}` 與 `x_iter_number_speech_segments_language__mutmut_{11,13,14}` 的原始碼差異（見「mutmut」節），計畫記錄的等價理由都正確；會改變行為的 `!=`→`==`（`_12`）已被殺。
- **建議：** 不需動程式。下次維護性的 mutmut 全跑時，以本計畫的表取代 `e81b278` 作為 pipeline 的基準；若想讓 `_1`、`_4` 不再出現，可在 `iter_number_speech_segments_mode` 把兩個初始值的註解寫清楚「`None`／任何不以 `.` 結尾的字串都等價」，或接受它們為等價突變。

### M4. 文件措辭

- `pipeline/numbers.py:3`「so tests and mutmut can load it alone」：依 spec §13 Q4，測試其實是經由套件的 `module.numbers` 取得它（沒有任何測試單獨載入 `numbers.py`），mutmut 也是經由測試套件。建議改成「so it needs no NVDA stub to load」之類的說法，免得下一位讀者去找不存在的獨立載入測試。
- 進度帳本的 Task 1 寫在 Task 2 之後（時間順序如此，Task 1 不 commit），讀的時候要留意；不需改。

## 計畫 Review Focus 與 Ruling 的逐項檢查

| # | 項目 | 結果 |
| --- | --- | --- |
| RF1 | 測試間的過期子模組 | `pipeline_harness.py:63-64` 已把 `pipeline.numbers`／`pipeline.symbols` 加進 pop 清單。三個改過的測試檔各自單獨跑（46／207／29 passed）、`nvda_symbols → filters → nvda_symbols` 連跑 253 passed、全套預設順序 2346 passed。`test_symbol_tables_are_probed_once_per_locale` 若拿到別的測試填過的快取會記到 0 次探測而失敗，所以它本身就是這個風險的守門。 |
| RF2 | 執行期換語音／合成器／trust voice language | `symbol_locale` 的 `speech.getCurrentLanguage()`（`symbols.py:53`）沒有快取；種子 C3（把它包進 `lru_cache`）→ `test_symbol_tables_are_probed_once_per_locale` 1 failed（`len(current) == 3`）。既有的 `test_namer_asks_each_language_once_per_run` 維持每次執行問一次語音 locale。 |
| RF3 | 非單純名稱的 locale | 9 個案例的 `test_has_symbol_table_matches_nvdas_locale_dir` 現在走的是快取版；審閱者另在 Python 直接呼叫：`has_symbol_table("zh_TW")` True、`"en_US"` False、`""` False、`"../en"` False，`cache_info()` 4 misses、無例外。 |
| RF4 | value 模式與單一片段不插 break | 等價探針含 value 模式與單一片段（`"123"`、`"+5"`）在 4 種序列、11 個 context 下的輸出，與 master 相同；`number_pieces("…", "value", …)` 回 `[raw]`，`_translate_number` 的 `if index:` 對單一片段不 yield separator（`__init__.py:334-337`）。value 模式現在會多建一個沒用到的 `NumberBreakCommand`（`:333`），NVDA 的 `BreakCommand.__init__` 只存 `time`（`commands.py:203-207`），無法觀察到。 |
| RF5 | 真實 add-on 的 import 與 stdlib `numbers` | `test_worldvoice_speak.py` 8 passed（真實 `synthDrivers/WorldVoice/__init__.py` 經 `.pipeline` 載入兩個新子模組）。審閱者在載入 pipeline 後 `import numbers` 仍是標準庫（`numbers.Number` 存在，與載入前同一個物件），`module.numbers.__name__ == "synthDrivers.WorldVoice.pipeline.numbers"`。`pipeline/` 不在 `sys.path`（`__init__.py:57` 加的是 add-on 根目錄，`engine/discovery.py:102-103` 加的是驅動的上層）。 |
| Ruling（Task 6） | Guard A 在 mutmut 的複本上 `skipif` | **合理。** mutmut 3.8.0 把 `from mutmut.mutation.trampoline import …` 注進每個被突變的模組，Guard A 讀的是 `mutants/` 下的那份原始碼，必然失敗，而且 Guard A 沒有任何 mutant 可殺（它只看 import，突變只改函式本體），跳過沒有損失。替代方案（在 Guard A 放行 `mutmut`）會讓守門多一個特例卻同樣沒有 mutant 可殺；改 `pytest_add_cli_args` 則違反 spec §8「其他 mutmut 鍵不變」。審閱者在 mutmut 跑完的 `mutants/` 目錄下跑 `test_pipeline_structure.py`：2 passed、1 skipped（Guard A），Guard B 在 mutmut 的改寫上仍然通過（它不看 `mutmut` 這個名稱，改寫出的 `x_…__mutmut_n` 也不在 `MOVED`）；正常套件 0 skipped。`running_under_mutmut()` 以 `ROOT.name == "mutants"` 判斷，與 `tests/mutation_support.py` 既有的用法一致。 |

## 守門測試的評估

在 scratch 複本逐一種入違規，每次只改一處、跑完 `git checkout -- .`：

| 種子 | 預期 | 結果 |
| --- | --- | --- |
| A1 `numbers.py` 加 `import globalVars` | Guard A 失敗 | 1 failed |
| A2 `numbers.py` 加 `from .symbols import symbol_name` | Guard A 失敗（`level == 0`） | 1 failed |
| A3 `number_pieces` 函式內加 `import speech` | Guard A 失敗（`ast.walk`） | 1 failed |
| A4 `numbers.py` 加 `from synthDrivers.WorldVoice.pipeline.symbols import …` | Guard A 失敗 | 1 failed |
| B1 `__init__.py` 複製一個 `_symbol_locale` 回來 | Guard B 失敗 | 1 failed |
| B2 `__init__.py` 加 `import os` | Guard B 失敗 | 1 failed |
| B3 `__init__.py` 加 `import characterProcessing` | Guard B 失敗 | 1 failed |
| B4 `symbols.py` 加 `from . import numbers` | Guard B 失敗 | 1 failed |
| B5 `__init__.py` 還原 `_SENTENCE_END_RE` | Guard B 失敗 | 1 failed |
| B6 `__init__.py` 加 `import os.path` | （缺口探測） | 3 passed → M1 |
| B7 `__init__.py` 加 `from os.path import isfile` | （缺口探測） | 3 passed → M1 |
| B8 `__init__.py` 加 `from speech import getCurrentLanguage` | Guard B 失敗 | 1 failed |
| B9 `__init__.py` 以新名稱 `_symbol_lookup` 寫一個查詢 | （設計限制） | 3 passed → M1 附註 |
| C1 `has_symbol_table = _symbol_table_on_disk`（拿掉快取） | 快取測試失敗 | 1 failed（6 次探測） |
| C2 `symbol_locale` 直接呼叫 `_symbol_table_on_disk` | 快取測試失敗 | 1 failed |
| C3 `getCurrentLanguage` 也包 `lru_cache` | 快取測試失敗 | 1 failed（`nvda_symbols` + `filters` 共 252 passed、1 failed） |
| C4 改成 `@lru_cache` 裝飾器形式 | 行為測試不會失敗（只有 mutmut 會少 20 個 mutant） | 49 passed，如預期；這個風險由 spec §12「後測必須列出 `x__symbol_table_on_disk__mutmut_*`」守住，審閱者的後測確實列出 21 個 |

17 個改成 `.symbols`／`.numbers` 的測試位置逐一讀過：改的都是取用路徑，斷言沒有變；`test_pipeline_nvda_symbols.py` 的 fixture 回傳 `module.symbols` 後，`:246`、`:264` 換掉的 `characterProcessing` 正是 `symbol_name` 讀取的那個模組屬性，`test_pipeline_filters.py:540` 與 `test_pipeline_pause_properties.py:443`、`:655` 改的是同一個 stub 模組物件的屬性，效果與 master 相同。沒有測試改成對 stub 斷言。

## mutmut

審閱者在 scratch 複本（`98590ac`）重跑：`mutmut run --max-children 3` 限定 `pipeline.numbers.*`、`pipeline.symbols.*`、`pipeline.x__translate_number*`、`pipeline.x_remove_thousands_separators*`，記憶體監控；無 timeout、無 suspicious。

| 函式 | mutant | killed | survived |
| --- | --- | --- | --- |
| `numbers.x_split_spaced_numbers` | 21 | 21 | 0 |
| `numbers.x_number_pieces` | 44 | 43 | 1（`_22`） |
| `numbers.x_strip_thousands` | 11 | 11 | 0 |
| `symbols.x__symbol_table_on_disk` | 21 | 20 | 1（`_7`） |
| `symbols.x_symbol_locale` | 22 | 21 | 1（`_15`） |
| `symbols.x_symbol_name` | 9 | 9 | 0 |
| `symbols.x_symbol_namer` | 19 | 19 | 0 |
| `x__translate_number` | 12 | 12 | 0 |
| `x_remove_thousands_separators` | 4 | 4 | 0 |

與計畫「Implementation notes: mutmut」的後測欄完全一致（44+12 = 47+9 個 glue、11+4 = 14+1 個 glue，glue 全殺）。

存活 mutant 的等價性（讀 `mutants/` 下產生的原始碼差異）：

- `numbers.x_number_pieces__mutmut_22`：`token[0] in "+-"` → `in "XX+-XX"`。`token` 來自 `NUMBER_TOKEN_RE`（`^[+-]?[0-9]+|[0-9]+|[SYM]`），以數字結尾的 token 第一個字只會是數字或正負號，不會是 `X`。等價。
- `symbols.x__symbol_table_on_disk__mutmut_7`、`symbols.x_symbol_locale__mutmut_15`：與 `7c67961` 記錄相同，等價。
- master 既有（本階段未動的函式）：`x_iter_number_speech_segments_mode__mutmut_1`（`previous_was_number = None`，與 `False` 同為假值）、`_4`（初始 `preceding_text = "XXXX"`，不以 `.` 結尾，且第一段若是文字會先被覆寫）、`_34`／`_35`（數字之後的 `preceding_text = None`／`"XXXX"`：兩個 match 永遠不相鄰，數字後面若還有東西一定是文字段，文字分支會先覆寫再被讀取；`None.endswith` 永遠不會執行）；`x_iter_number_speech_segments_language__mutmut_11`（`!= "default" or True`）、`_13`（`"XXdefaultXX"`）、`_14`（`"DEFAULT"`）：唯一的呼叫者 `_insert_WVLangChangeCommand_between_number`（`__init__.py:252-278`）只會從 `inject_number_language` 在 `number_language != "default"` 時被呼叫（`:309-317`），三個 mutant 在這個前提下都算出 `number_language`。會改變行為的 `_12`（`==`）已被殺。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 全套測試（分支 worktree） | `python3 -m pytest -q -p no:cacheprovider tests`，單一行程，3 GB 記憶體監控 | **2346 passed, 2 warnings in 61.81 s**，0 skipped（兩個 warning 與前幾輪相同，`generics/speechSymbols/models.py` 的 `codecs.open`） |
| 改過的測試檔單獨跑 | `nvda_symbols`／`filters`／`pause_properties`／`structure`／`worldvoice_speak` | 46／207／29／3／8 passed |
| prek（scratch 複本，乾淨樹） | `prek run --all-files`（prek 0.4.14、ruff 0.16.3） | 8 個 hook 全 Passed，沒有檔案被修改 |
| 空白 | `git diff --check master` | 乾淨 |
| 受保護路徑 | `git diff --stat master -- 'driver/*/driver/' driver/sonic/ languageDetection/script_data.py`；`git ls-files …/driver/Neural` | 兩者皆無輸出 |
| Co-Authored-By | `git log --format=%B master..HEAD \| grep -ci co-authored` | 0 |
| 跨驅動 import | grep 各 `driver/<Engine>/` 內對其他引擎 package 的 import | 無 |
| 搬家逐字比對 | AST 取出 master 的 10 個定義，去 docstring、套用更名，與新模組比對；`__init__.py` 其餘定義亦比對 | 10 個全部相同；其餘定義只差更名與三個呼叫；沒有新頂層名稱；缺的正是 10 個搬走的名稱加 `_SENTENCE_END_RE` |
| 行為等價探針 | 同一支腳本在 `41dc50d` 與 `98590ac` 各跑一次（harness 載入真實 pipeline，九個 stage 各跑與串接） | 61,776 個案例，JSON 逐位元組相同 |
| 外部對搬走名稱的取用 | `grep -rnE` 在 `addon`、`tests`、`ref/Neural` 找 `_NUMBER_RE`、`_SYMBOLS`、`_symbol_*`、`_has_symbol_table`、`_split_spaced_numbers`、`_SENTENCE_END_RE` 等 | `pipeline/` 以外沒有任何取用；`ref/Neural` 不 import `pipeline` |
| import 方向 | 讀 `numbers.py:6-9`、`symbols.py:11-18`；Guard B 的 `symbols.py` 無相對 import 檢查 | `numbers.py` 只有 `re`、`unicodedata`、`collections.abc`、`itertools`；`symbols.py` 只有 `os`、`collections.abc`、`functools` 與 4 個 NVDA 模組；都不 import 套件；無循環 |
| stdlib `numbers` | 載入 pipeline 後 `import numbers` | 仍是標準庫（同一物件），套件的是 `synthDrivers.WorldVoice.pipeline.numbers` |
| 快取物件 | `type(has_symbol_table)`、`cache_info()`、4 個 locale | `_lru_cache_wrapper`；4 misses、無例外；非單純名稱回 False |
| NVDA 依據 | `nvda.pyw:41-59`（`appDir` 設一次）、`characterProcessing.py:836-846`（`availableLocales` 為 `cached_property`）、`:893-899`（builtin 路徑）、`speech.py:313-325`（`getCurrentLanguage` 純記憶體） | 與 spec §5 一致 |
| 守門種子 | 上表 17 個種子 | 應抓到的 13 個都失敗；3 個缺口探測如 M1；C4 如預期 |
| mutmut 重跑 | scratch 複本、`--max-children 3`、記憶體監控 | 163 mutant、160 killed、3 survived（皆為記錄的等價突變）、0 timeout、0 suspicious |
| Guard A／B 在 mutmut 複本 | 在 `mutants/` 下跑 `test_pipeline_structure.py` | 2 passed、1 skipped（Guard A） |
| 既有存活 mutant 的等價性 | 讀 `mutants/…/pipeline/__init__.py` 中 `_1`、`_2`、`_3`、`_4`、`_34`、`_35` 與 `_10`–`_14` 的差異 | 如「mutmut」節；`_2`、`_3`、`_12` 會改變行為，均已被殺 |
| `e81b278` 的差異 | `git show 844d8d2:…/pipeline/__init__.py` 比對 `iter_number_speech_segments_mode` | 函式本體相同 → M3 |
| 行數 | `wc -l` | `__init__.py` 845、`numbers.py` 88、`symbols.py` 94（spec 估 ≈855／90／85） |
| 收尾 | `git worktree list`、`git status --short`、scratchpad | 只剩主 checkout 與 `WorldVoice-phase31`；分支工作樹乾淨；審閱者的 scratch 檔案已刪，`scratchpad/p31` 未動 |

## 使用者還沒確認的使用者可見預設

本階段沒有使用者可見的行為、字串、設定或面板變更；使用者聽到與看到的都和 master 相同。以下是協調者或實作者替使用者做的、未經使用者明確點頭的小決定，列出備查：

1. **第一次探測失敗會快取成 False 到 NVDA 重啟為止**（spec §12 接受的風險）：若某個 locale 的 `symbols.dic` 在第一次 `os.path.isfile` 時因暫時性 I/O 錯誤回 False，這個 locale 的符號名稱在該次 NVDA 執行期間都會走 NVDA 介面語言的規則，而不是語音 locale 的表。NVDA 自己的 `availableLocales` 也有同樣性質，master 上 `isfile` 本來就把錯誤當 False，只是以前每句會重試。實務上發生機率極低。
2. **spec §13 的協調者預設 Q1–Q6**：不加 `is_number`、`lru_cache(maxsize=None)` 的呼叫形式、三個輔助常數也公開、測試經由套件屬性取用新模組、四個 stage 輔助函式維持私有、`NUMBER_SYMBOLS` 保留為獨立 oracle。都不影響使用者。
3. **Windows 手動項目**：spec §11 只列一個可選的冒煙測試（zh-TW 語音＋英文介面讀「2×3」、換 en 語音讀「times」）。Linux 上已由 `test_pipeline_names_symbols_*_with_nvdas_real_lookup` 以 NVDA 真實的 `characterProcessing` 驗證，不需要專門的測試版。

## Windows 無法在 Linux 驗證的部分

真實 NVDA 中 `globalVars.appDir` 下的 `locale/<locale>/symbols.dic` 探測、`speech.getCurrentLanguage()` 的實際回傳，與 OneCore／SAPI5 等引擎收到的 break 命令，Linux 上都是以 stub 或 `ref/nvda` 的原始碼驗證；但本階段對這些路徑的呼叫次數以外沒有任何改動（等價探針 61,776 個案例相同），所以沒有新增的 Windows 風險。

## 修正記錄

修正者 Opus 5.5，worktree `/workspace/WorldVoice-phase31`，從 `5fe102d` 開始。四項 Minor 全部修正，每項的 `Ruling:` 記在進度帳本。

| # | commit | 修正內容 |
| --- | --- | --- |
| M1 | `c6c6b0d` | `imported_modules` 改用 `ast.walk`，新增 `packages()` 取 `split(".")[0]`；Guard B 先扣掉 `speech.commands`、`speech.extensions`（`__init__.py` 實際用到的 `speech` 子模組只有這兩個，含 `TYPE_CHECKING` 下的 `speech.commands`）再比對頂層套件；languageDetection 的守門也改比頂層套件。先在 scratch 複本的 `with_order_log` 函式內種入 `from os.path import isfile`：新守門 1 failed（`'os'`）、舊守門 3 passed；`import os.path`、`from speech import getCurrentLanguage` 也都 1 failed；真實程式碼 3 passed。仍放行的寫法：`import speech.commands`（會綁定 `speech` 這個名稱），因為允許是依模組名稱而非 import 形式；目前程式碼只用 `from` 形式，記為帳本中的已知代價。 |
| M2 | `2ddf286` | 只把 `appDir` 底下的探測（`Path.is_relative_to`）拿來比對。先在 scratch 複本的 `symbol_locale` 種入 `os.path.isfile('/elsewhere/probe')`：舊測試丟 `ValueError`，新測試通過；拿掉快取（`has_symbol_table = _symbol_table_on_disk`）時新測試仍然失敗，守門效果不變。 |
| M3 | `9ffac2b` | 只改文件：計畫的 mutmut 表上方加「**Baseline:**」段落，說明後測欄自此取代 `e81b278` 作為 pipeline 的基準，並記下 `e81b278` 漏記 `iter_number_speech_segments_mode` 的 4 個存活（`_1`、`_4`、`_34`、`_35`）與 `iter_number_speech_segments_language` 的 3 個存活（`_11`、`_13`、`_14`），全部等價。另確認該函式自 `844d8d2` 起只有預設值 `NUMBER_RE` 的 D3 更名，本體未變。 |
| M4 | `8aacd92` | `pipeline/numbers.py:3` 改為「This module imports only the standard library, so it needs no NVDA module or stub to load.」。進度帳本 Task 1／Task 2 的順序依審閱建議不改。 |

每個 commit 前與修正結束時都跑了 §7 的驗證：`python3 -m pytest -q -p no:cacheprovider tests` 單一行程、3 GB MemAvailable 記憶體監控（最低約 6.0 GB）→ **2346 passed, 0 skipped**；`prek run --all-files` 8 個 hook 全 Passed；`git diff --check master` 乾淨；兩個受保護路徑指令都沒有輸出。沒有 push、沒有 stash、沒有動主 checkout 與 `scratchpad/p31`。
