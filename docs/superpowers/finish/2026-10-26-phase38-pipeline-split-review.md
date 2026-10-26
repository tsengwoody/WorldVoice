# Phase 38 Review 紀錄：拆分 `pipeline/__init__.py`、recorder 與 Say All 搬進 `pipeline/`

日期：2026-10-26。分支：`phase38-pipeline-split`（`9f77382..53d5f44`，4 個 commit：1 個 docs（spec、plan）、3 個 refactor），worktree `/workspace/WorldVoice-phase38`。
依據：

- 規格 `docs/superpowers/specs/2026-10-26-phase38-pipeline-split-design.md`
- 計畫 `docs/superpowers/plans/2026-10-26-phase38-pipeline-split.md`（4 個 task、65 個 `Edit:` 區塊、2 個 `File:` 區塊（抽取腳本、未提交的 patch 探針）、Review Focus 5 項，每個 commit 都記了 `HEAD:addon`／`HEAD:tests` tree id，檔尾有 dry run 紀錄）
- 進度帳本 `.superpowers/sdd/2026-10-26-phase38-pipeline-split/progress.md`（6 條 `Ruling:`；`.superpowers/` 被 git 忽略，不在 commit 裡）
- 路線圖 `storage/refactor8.md` §2.1（F1）、§2.6（F6）、§2.8（F8）、§4.2（A2）、§6「階段 38」（寫在階段 36–37 之前，路徑以現在的程式碼為準）
- `DEVELOPMENT_WORKFLOW.md` §3.3、§4.5（複雜流程：在 scratch 複本重放 plan、比對 tree id）、§4.6、§7、§8

流程：審閱者 Fable 5.1，唯讀。`master` 仍在 plan 的基準 `9f77382`（`git log master` 確認），§4.6 的重新 dry run 條件不成立。plan 重放在 scratchpad 的全新 clone（`git clone /workspace/WorldVoice`，checkout `9f77382`，`ref` symlink，`prek install`）上用我自己寫的套用器進行（只解析 plan 的 `### Task N:`／`- [ ] **Step S:`／`**Edit:**`／`**File:**`／`Run:` 標記與 bash 區塊，和實作者的 step runner 互不相依）；抽取腳本另外從 plan 文字切出來，對 `42b9521` 的 `pipeline/__init__.py` 獨立執行一次再和分支比對；突變探針、patch 觀測、順序與洩漏檢查在另一個 scratch clone（分支 `53d5f44`）進行；審完兩個 clone 都刪除。pytest 單一行程（最多同時 2 個行程），外層有 MemAvailable < 3 GB 就停掉的看門狗（全程沒有觸發）。沒有 push、沒有 stash、沒有動主 checkout、沒有修改分支上的原始碼或測試；本文件是審閱者在任務分支上唯一的 commit。

`file:line` 以 `53d5f44` 為準；`WV/<path>` = `addon/synthDrivers/WorldVoice/<path>`。

## 結論

Ready to merge：**是**。Critical 0、Important 0、Minor 3（都不擋 merge；M1 是既有模式，M2、M3 是便宜的守衛補強，可留到下一階段）。

- **純搬移成立，沒有 plan 以外的修改。** 在全新 clone 從 `9f77382` 照 plan 逐步重放，三個 commit 的 tree id 全部和 plan、和分支一致（表格「plan 重放」）；`git diff <重放 HEAD> 53d5f44 -- addon tests pyproject.toml` 沒有輸出，所以分支上 `addon/`、`tests/`、`pyproject.toml` 的每一個位元組都來自 plan。docs commit `4634c04` 只動 `docs/`。
- **逐位元組的 verbatim move。** 我把 plan 裡的抽取腳本切出來，對 `42b9521` 的 `pipeline/__init__.py`（SHA-256 和腳本的 `INPUT_SHA256` 相同）獨立跑一次：產生的 8 個模組和空的 `__init__.py` 與分支 `53d5f44` 的檔案 `cmp` 全部相同。再用自己的 AST 比對（不經過腳本）：舊檔 66 個頂層定義（含上方緊貼的註解行與 decorator）每一個都在新模組裡找到**完全相同的文字**、沒有缺漏、沒有重複，且每個模組內的相對順序和舊檔一致。非空白行的多重集合比對：舊檔只有 3 行沒有出現在新模組（`from typing import TYPE_CHECKING, Literal, Union`、`speech.commands` 的合併 import、帶 `GENERIC_CONTEXT` re-export 的 `.context` import），新模組多出的 69 行全是 8 個 docstring 與 import 標頭；和 plan 的 dry run 紀錄一字不差。`git diff --color-moved=dimmed-zebra 42b9521 53d5f44 -- WV/pipeline/`：移動 +1128／−1121，未標為移動的刪除只有 7 行（上述 3 行 import、`scope.py` 的一行 import，以及 `import re`、`import uuid`、`_MISSING = object()` 三個太短而 git 不算移動的單行；AST 比對已證明它們原樣出現在新模組）。
- **名稱解析沒有變。** 舊檔沒有任何 `global` 敘述；模組層級會被改動的狀態只有三個：`_PUNCTUATION_RE_CACHE`（`punctuation.py:33`，由同檔 `_get_punctuation_regex` 寫入）、`_log_writer`（`registry.py:84`，由同檔 `_run_logged` 讀）、`pl`（`registry.py:35`，由同檔 `_LogWriter.write` 讀）——每一個都和唯一的讀寫者留在同一個模組，沒有「一個模組 rebind、另一個模組拿到舊 copy」的情形。stage handler 在呼叫時查的名字（`current_context`、`pipeline_settings`、`read_stored`、`config`、`log`、`filter_speechSequence`、`speech_dictionary`、`_plain_breaks`）全部在 `registry.py:15-29` 以 import 綁進 `registry` 的 globals，和舊檔在同一個 namespace 查到的是同一批物件。`STAGES`（`registry.py:148-157`）在 import 時建一次，`Stage.__post_init__` 綁一次 handler，`register_stages`／`unregister_stages`／`order_move_to_start_register`（`:170-188`）都走同一個 tuple 的 `stage.handler`；lru_cache 的 helper（`symbols.py`）沒有搬動。ruff（`F821`／`F401`）在 prek 裡對 8 個新模組全過，所以沒有未定義或多餘的名字。
- **import 圖沒有週期。** 用 AST 算 `pipeline/` 內的相對 import：`registry → {breaks, context, items, numberStages, punctuation, recorder, sequence, settings, speech_dictionary, unspaced}`、`numberStages → {breaks, context, languageCommands, numbers, sequence, settings, symbols}`、`items`／`punctuation → {breaks, context, sequence, settings}`、`unspaced → {context, sequence, settings, unspaced_common_data}`、`languageCommands → {context, sequence}`、`breaks → sequence`、`scope → registry`、`sayAll → {context, settings}`；DFS 沒有找到任何環，和 spec §5.2 寫的方向一致，`languageCommands` 確實不 import `numberStages`。
- **空的 `pipeline/__init__.py`（Ruling 1）可行。** `git cat-file -s` = 0。`addon/` 裡所有 importer 都改成 owning module：synth `WV/__init__.py:37-46`、`WV/pipeline/scope.py:3`、`globalPlugins/WorldVoice/pipelineLog.py:10`（`pl`）、`speechSettingsDialog.py:17`（`LOG_SWITCHES`）、`globalPlugins/WorldVoice/__init__.py:14`（`pipeline.sayAll`）。`git grep` `addon/`（排除內層驅動）找不到任何 `from .pipeline import`／`pipeline import pl`／`WorldVoice.log`／`WorldVoice.sayAll`／`log_dir`／`log_name`／`pipeline.GENERIC_CONTEXT`；用字串算模組名的只有 `bridge/completionPolicies.py:75`、`engine/__init__.py:20`、`engine/discovery.py:104`（都指 `driver`）和 `installTasks.py:11`（依路徑載 `generics/coreArchive.py`、`workspace.py`），都和本階段無關。`ref/Neural` 與 `ref/` 其他外掛沒有任何 `pipeline`、`sayAll`、`PipelineLog` 的引用。`GENERIC_CONTEXT` 在舊 `__init__` 的 re-export 消失後，synth 早就直接從 `.pipeline.context` 拿（`WV/__init__.py:37`，未改）。
- **NVDA 啟動時的 import 順序與副作用。** synth 套件現在依序 import `.pipeline.context`、`.languageCommands`（→ `..runtime.models`、`..speechCommands`）、`.numberStages`、`.registry`（→ 全部 stage 模組、`speech_dictionary`、`recorder`）、`.scope`、`.settings`；集合和 master 一樣（舊的 `pipeline/__init__` 一口氣 import 同一批東西），只是分成幾行。import 時的副作用只有 `pl = PipelineLog(...)`（不碰磁碟，`test_pipeline_log_touches_the_disk_only_when_written`）、`_log_writer = _LogWriter()`、`STAGES` 建表，和以前相同。全域外掛 `globalPlugins/WorldVoice/__init__.py:14-15` 兩行 isort 對調後，第一個 `synthDrivers.WorldVoice.*` import 仍會先跑 synth 套件的 `__init__`（把 add-on 根目錄放進 `sys.path`，`WV/__init__.py:65`），`:12-13` 的註解仍成立；`addonHandler.initTranslation()` 在 `:24`，仍在所有 import 之後、第一個 `_(`（`:56`）之前；`pipelineLog.py:13`、`speechSettingsDialog.py` 的 `initTranslation()` 位置未動。`pipeline.settings`（import `addonHandler`、`config`、`logHandler`）和 `pipeline.context`（import `synthDriverHandler`）本來就需要 NVDA，和空 `__init__` 無關；`pipeline.numbers` 現在以套件路徑 import 只載入 `synthDrivers`、`synthDrivers.WorldVoice`、`synthDrivers.WorldVoice.pipeline`、`...pipeline.numbers`（A2 守衛）。
- **F6 的路徑正確。** master 的 `log.py:6-9`：`Path(__file__).resolve().parent.parent / "log"`，`log.py` 在 `WV/`，所以是 `addon/log`。現在 `registry.py:35` 的 `parents[3]`：`parents[0]=pipeline`、`[1]=WorldVoice`、`[2]=synthDrivers`、`[3]=addon`，repo 版面得 `addon/log/pipeline.csv`；NVDA 安裝版面 `<config>/addons/WorldVoice/synthDrivers/WorldVoice/pipeline/registry.py` 的 `parents[3]` = `<config>/addons/WorldVoice`，和舊的 `<config>/addons/WorldVoice/log` 相同。`PipelineLog(log_name)` → `PipelineLog(log_file)` 的呼叫端只有 `registry.py:35`（產品碼）和測試；`write`／`move_to`／`MAX_LOG_SIZE` 未改。全域外掛用到 `pl` 的只有 `pipelineLog.py:43` `export_with_dialog` 的 `pipeline_log_file.move_to(dst)`，拿到的是 `registry.pl`，和 `_LogWriter.write` 寫的是同一個物件（沒有「clear」功能）。pin test 真的會抓錯：`parents[3]` 改成 `[2]` 或 `[4]` 都紅（表格「突變探針」M1、M2）。
- **F8。** `pipeline/sayAll.py:1-6` 的 docstring 說它走 NVDA `speech.initialize` 做的同一個 `sayAll.initialize` 呼叫：對照 `ref/nvda/source/speech/__init__.py:166-171`（`sayAllInitialize(speak, speakObject, getTextInfoSpeech, SpeakTextInfoState)`）正確。相對 import 改成 `.context`／`.settings`（`:15-16`），其餘程式碼 100% 未動；沒有任何地方 re-export 它。
- **8 個 docstring 都和內容相符。** 逐一對過：`punctuation.py:1-2`「which the stage may also remove」對應 `:132` 的 `settings.remove_punctuation_characters`；`languageCommands.py:1-2`「the number stage drops them for a synth without roles」對應 `numberStages.py:270-271` `if not ctx.supports_roles: remove_language_command(...)`；`registry.py:1-6` 列的 `apply_speech_dictionaries`、`speech_viewer`、`listable` 都在檔內；`numberStages.py:1-2` 的三件事（thousands、`inject_numbers`、`number_wait_factor`）加上偵測用的 number language（`wrap_numbers_for_detection`、`detect_with_number_language`）都在檔內；`sequence`、`breaks`、`items`、`unspaced` 一句話就是檔案內容。`recorder.py:12-15` 說「nothing here depends on where this module lies」——檔內確實沒有 `__file__`。
- **測試：斷言沒有變。** 對 17 個被動到的測試檔比對 `assert` 行（排序後 md5）：15 個完全相同；`test_pipeline_log.py` 多 1 行（pin test）、`test_pipeline_structure.py` 多 2 行（A2 守衛），沒有任何既有斷言被改或刪。`tests/test_plugin_voice_contract.py` 零變動。
- **`PipelineModules` 視圖（Ruling 4）設計站得住。** `pipeline_harness.py:79-85` 每次 `__getattr__` 都讀 `vars(module)`，不是快取，所以 patch 到 `registry` 之後透過視圖讀回看到的就是 patch 後的值（`registry` 排第一）；不會有「stale binding」。我在載入後掃描 14 個模組的 namespace：**沒有任何非 dunder 名稱在兩個模組裡綁到不同物件**（`_MISSING`、`SpeechCmd`、`SpeechContext`、`BreakCommand` 等都是同一個物件的 import），所以查找順序不可能回傳歧義的綁定；測試裡用 `module.__name__`／`__package__` 的四處都不是 pipeline 視圖。`__setattr__` 真的會擋：把 `test_pipeline_stages.py` 第一個 `module.registry` patch 改回 `module`，測試立刻以 `AttributeError: patch current_context on the pipeline module that looks it up, as module.registry` 失敗。非 `registry` 的 patch 目標只有 `env.module.log`（`test_pipeline_filters.py:887`，patch 的是 `registry` 讀的那個 `log` 物件的 `debug`）、`module.speech`（`test_pipeline_nvda_symbols.py`，那裡的 `module` 是 `module.symbols`）、`module.speech_dictionary`（模組本身），都打在被讀的物件上。
- **每個 patch 都真的被讀到。** 我自己寫的 pytest plugin（和 plan 的探針不同實作）包住所有打在 `*.pipeline.registry` 上的 patch 值，在 5 個測試檔 601 個測試上得到 **57 USED、4 UNUSED**，4 個 UNUSED 全是 `pl`，而且就是四個斷言「沒有寫入」的參數化（`test_a_stage_logs_under_each_of_its_switches[none]`、`test_run_logged_records_only_when_switched_on[INFO-False-True-writes0]`、`[INFO-True-False-writes1]`、`[DEBUG-False-True-writes3]`）；和 plan Step 7、重放時 plan 自己的探針輸出逐行相同。被 patch 的名字：`current_context` 44、`pl` 13、`filter_speechSequence`、`log`、`pipeline_settings`、`read_stored` 各 1。
- **順序無關、不洩漏 `None`。** 用自寫 plugin 把整個套件**反向**執行並在每個測試前後比對 `sys.modules`：3236 passed；沒有任何測試留下值為 `None` 的項目；留下 `synthDrivers*` 真實模組的只有 7 個測試，其中屬於本階段的只有反向順序下**第一個**跑到的 pipeline harness 測試（之後的 harness 測試先 pop 再重新 import，所以前後集合相同），其餘 6 個是 phase 37 review M5 已記錄的既有檔案。見 M1。
- **Review Focus 逐項**：見下節。**§8**：4 個 commit 都是英文 `<type>: <summary>` 加內文、0 個 `Co-Authored-By`；沒有碰 `driver/<Engine>/driver/`、`driver/sonic/`、`script_data.py`、`unspaced_common_data.py`、Neural；`git diff --check 9f77382` 乾淨；`prek run --all-files` 8 個 hook 全數 Passed 且沒改檔。`pyproject.toml:51-58` mutmut `source_paths` 以 8 個新模組取代 `pipeline/__init__.py`；`[tool.ruff.lint.per-file-ignores]`（`:144-158`）沒有任何一條指到搬動的檔案；搬動的 10 個模組裡沒有 `_(`，`buildVars.py` 的 glob 不受影響，無翻譯工作。
- **執行緒與鎖：** 本階段沒有碰任何鎖、callback 或執行緒程式碼。

## Critical

無。

## Important

無。

## Minor

### M1. pipeline harness 以裸 `sys.modules.pop` 清理、以 import 系統載入，13 個真實模組會留在 `sys.modules`（既有模式，本階段把名單從 5 個擴到 13 個）

- 位置：`tests/pipeline_harness.py:110-128`（裸 `sys.modules.pop(name, None)`，不經 monkeypatch）、`:214`（`importlib.import_module("synthDrivers.WorldVoice.pipeline.registry")`，由 import 系統註冊，monkeypatch 不知道）；對照 `tests/addon_loader.py:24-38` `load_source` 的 docstring「monkeypatch removes it when the test ends」。
- 現象：測試結束時 monkeypatch 只移除 `synthDrivers.WorldVoice.pipeline`（`load_source` 登記的那個），`...pipeline.registry`、`.sequence`、`.breaks`、`.items`、`.numberStages`、`.punctuation`、`.unspaced`、`.languageCommands`、`.context`、`.numbers`、`.symbols`、`.speech_dictionary`、`.unspaced_common_data` 都留在 `sys.modules`，而且是綁著上一個測試的 stub `config`／`speech` 的真實模組。今天無害：每個會碰這些名字的地方都先 pop（harness 自己）、先 `delitem` 所有 `synthDrivers*`（A2 守衛 `test_pipeline_structure.py:145-146`、`test_worldvoice_speak.py:116`）或用 monkeypatch 的 stub 蓋掉（`ui_harness.py:781`、`test_runtime_composition.py:598-611`、`test_pipeline_log.py:35`）；正向、反向整套件都綠。master 對 `context`、`numbers`、`symbols`、`speech_dictionary`、`unspaced_common_data` 早就是同一模式（phase 37 review M5）。
- 失敗情境：將來某個新測試直接 `importlib.import_module("synthDrivers.WorldVoice.pipeline.registry")` 而沒有先 pop，會拿到上一個 pipeline 測試留下、父套件已被移除、`config` 是舊 stub 的模組——錯誤訊息會指向別的測試。
- 建議：不在本階段修（與 spec 無關、不改行為）。列入測試衛生待辦：`load_pipeline_module` 在 `import_module` 之後對 `PIPELINE_MODULES` 每個名字 `monkeypatch.delitem(sys.modules, name)` 再 `setitem` 回去（讓 monkeypatch 記得要移除），或加一個 autouse fixture 在測試後移除新增的 `synthDrivers*`。只動 `tests/`。

### M2. `test_pipeline_package_keeps_only_stages_logging_and_registry` 的名單沒有 `recorder.py`

- 位置：`tests/test_pipeline_structure.py:104-113`（`STAGE_MODULES`）、`:117-135`。
- 現象：測試名稱說「stages, logging and registry」，但「logging」的 `recorder.py` 不在參數裡；`_LogWriter`／`_run_logged` 在 `registry` 有被檢查，`recorder.py` 本身沒有。今天 `recorder.py` 只 import `csv`、`shutil`、`time`、`pathlib`，加進名單會直接綠。`sayAll.py`（import `speech`）和 `scope.py` 不適合這個測試的禁止集合，排除是對的。
- 失敗情境：有人在 `recorder.py` 加 `import os` 或 `globalVars`（例如想改用 NVDA 的 config 目錄）不會被任何守衛抓到。
- 建議：`STAGE_MODULES` 加 `"recorder"`（+1 個測試，`HEAD:tests` 會變；依 §4.5 在 plan 檔尾補「## 修正」）。可留到階段 39。

### M3. A2 守衛和 phase 37 的 `ui` 守衛各自維護一份 NVDA 名字清單

- 位置：`tests/test_pipeline_structure.py:150-164`（13 個名字）、`tests/test_ui_structure.py` 的同類清單（12 個）、`tests/runtime_harness.py` 的 `forbidden`。
- 現象：三份清單內容相近但不同（這裡多了 `speechDictHandler`、`characterProcessing`），下次再加一個 NVDA 模組要改三處。守衛本身正確：`__init__.py` 寫 `from . import registry` → `import of config halted`；寫 `from . import numbers`（純 Python）→ `test_package_init_stays_empty[pipeline]` 紅；`numbers.py` 加 `import config` 或 `from ..numberLanguage import FOLLOW` → 既有的 `test_number_lexing_imports_only_the_standard_library` 紅（表格「突變探針」M3–M7）。
- 建議：phase 37 review M2 時就提過共用一份常數；仍建議在測試衛生階段合併，不在本階段動。

## 帳本 `Ruling:` 的評估

| # | Ruling | 評估 |
| --- | --- | --- |
| 1 | `pipeline/__init__.py` 留空，importer 指名 owning submodule，不做 re-export | **合理。** re-export `pl`／`LOG_SWITCHES`／stage 函式必然 import `registry`，而 `registry.py:15-18` import `config`、`speechDictHandler`、`logHandler`、`speech.extensions`，A2 就仍然不成立；`bridge/`、`voices/`、`ui/` 也都是空 `__init__`。成本的假設「外部沒有人 import `synthDrivers.WorldVoice.pipeline.<name>`」我在 `addon/`、`ref/Neural`、`ref/` 其他外掛都 grep 過，確實沒有。路線圖 §2.1 的「只 re-export」建議被推翻的理由充分。 |
| 2 | 八個模組而不是路線圖的六個（加 `sequence.py`、`items.py`；偵測包裝放 `numberStages`；`_plain_breaks` 放 `breaks`；`listable`／`speech_viewer`／`apply_speech_dictionaries` 放 `registry`） | **合理，週期的說法屬實。** 六模組版把 `wrap_numbers_for_detection` 放 `languageCommands`，它要用 `_split_numbers_for_language`（`numberStages.py:42`，`:175` 與 `_number_item_segments` 的 `:408` 共用），而 `inject_numbers`（`numberStages.py:271`、`deduplicate_language_command` 的兩處）要用 `languageCommands` 的函式，兩邊互 import。現在方向單一：`numberStages → languageCommands`。`_plain_breaks` 讀 `_EDGE_MARKER`（`breaks.py:19`），留在 `breaks` 讓 marker 維持私有；`sequence.py` 只有 15 行，但省掉 `numberStages → items` 或 `languageCommands → breaks` 的多餘依賴。`item_wait_factor` 不是數字 stage，獨立成 `items.py` 比塞進 `numberStages` 誠實。 |
| 3 | recorder 收檔案參數；`pl` 的擁有者用自己的 `__file__`（`parents[3]`）算 `addon/log/pipeline.csv`，不從 synth／全域外掛注入 | **合理。** 路線圖 §2.6 建議注入，但 `pl` 在 import 時就建立、`pipelineLog.py:43` 的匯出在 WorldVoice 不是目前 synth 時也要用它，而 synth 的根目錄要到 `WV/__init__.py:65` 才算出來（在 `:37-46` import pipeline 之後），注入會留下一段沒有檔案的視窗；對 `pl` 的匯出與 `_LogWriter.write` 來說仍是同一個物件。路線圖「不要只把 `parent.parent` 改成 `parents[2]` 了事」的顧慮以兩件事回應：路徑計算從 recorder 移到 `pl` 的擁有者（recorder 本身再搬也不會動到 log 位置），以及 pin test（兩個錯的深度都紅）。 |
| 4 | 測試透過 `PipelineModules` 讀，`__setattr__` raise，所有 patch 指名 `module.registry` | **合理。** 440 處 `module.<name>` 讀取不用改，而任何打錯目標的 patch 立刻以明確訊息失敗（實測）；14 個模組之間沒有同名不同物件的綁定（實測），所以「看到第一個模組的綁定」在今天不可能回傳錯的東西。Ruling 寫的成本「讀回 patch 過的名字會看到第一個模組的綁定」其實對 `registry` 的 patch 是正確的值（`registry` 排第一），風險比帳本寫的還小。 |
| 5 | 結構測試以 8 個模組參數化（+7） | 合理；單檔版本只會檢查一個空檔。見 M2：名單可以再加 `recorder`。 |
| 6 | plan 的 `Edit:` 區塊由原型分支的 diff 產生，落地用 step runner 套 plan 文字 | **重放證實。** 我用獨立寫的套用器照 plan 文字重做，三個 commit 的 tree id 與 plan、與分支相同，hook 都一次通過；plan 寫的 red／green 數字（`1 failed, 62 passed, 5 errors`、`68 passed`、`16 failed, 2 passed, 5 errors`、`23 passed`、`10 failed, 11 passed`、`21 passed`）和三次全套件（3227、3227、3236）全部一字不差。 |

## plan 的 Review Focus 逐項

1. **patch 不再打到被讀的程式碼**：`__setattr__` raise 實測生效；57 USED／4 UNUSED 與 plan 相同；`_stage_handler`（`registry.py:111-123`）查的 `current_context`、`pipeline_settings`，`_run_logged`（`:87-108`）查的 `config`、`read_stored`、`log`、`_log_writer`，`_LogWriter.write`（`:72-81`）查的 `pl`、`log`，`register_stages`／`unregister_stages` 查的 `filter_speechSequence`、`speech_dictionary`，全部在 `registry` 的 globals。
2. **註冊／註銷的是 NVDA 持有的同一批 handler**：`STAGES` 建一次、handler 綁一次（`registry.py:142-144`）；`test_register_puts_stages_first_in_order_and_unregister_removes_them` 以 `registry.filter_speechSequence` 為 fake（USED）；突變 M8（`unregister_stages` 改用重新綁的 handler）紅。`test_pipeline_scope.py` 的 stub 改成 `scope_pkg.registry`，和 `scope.py:3` 的新 import 對應。
3. **匯出的 log 就是 stage 寫的 log，在 `addon/log/pipeline.csv`**：見結論「F6 的路徑正確」；`test_pipeline_log.py`（service 走 `pipeline.registry` stub 的 `pl.move_to`）與 `test_settings_panels.py:620`（真 `pipelineLog.py` 從 `registry` stub 拿 `pl`）綠；突變 M9（`_LogWriter.write` 改讀 import 時的 `pl` 副本）紅。
4. **NVDA 啟動的 import 順序：沒有週期、沒有缺名**：AST import 圖無環；`test_worldvoice_speak.py:148-150` 真 import `registry`、`languageCommands`、`numberStages`，`test_runtime_composition.py:598-611` 以每模組 stub 跑真 synth `__init__`，A2 守衛以套件路徑 import `numbers`——重放與分支全綠；`test_global_plugin_lifecycle.py` 綠。
5. **Say All 仍在每段後加 `sayall_wait_factor`**：`test_say_all.py` 從 alias 套件以 `.pipeline.sayAll` 載入真檔（相對 import `.context`／`.settings` 真的被解析），5 個測試綠；函式本體 100% 未動。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| `master` 位置 | `git -C /workspace/WorldVoice log --oneline -3 master` | 仍是 `9f77382`，等於 plan 基準；不需 rebase 驗證 |
| 全套件（分支 `53d5f44` 的 scratch clone） | `python3 -m pytest -q -p no:cacheprovider tests`（看門狗外層） | **3236 passed**，0 skipped，101 s |
| 全套件反向順序＋洩漏探針 | 自寫 plugin `pytest_collection_modifyitems` 反轉＋每測試前後比對 `sys.modules` | **3236 passed**；0 個 `None` 殘留；留下 `synthDrivers*` 的 7 個測試中 6 個是既有檔案（phase 37 M5），1 個是本階段 harness 的穩態（M1） |
| prek | `prek run --all-files`（scratch clone） | 8 個 hook 全數 Passed；之後 `git status --short` 無輸出 |
| 空白字元 | `git diff --check 9f77382` | 無輸出 |
| 受保護路徑 | `git diff --stat 9f77382 -- 'WV/driver/*/driver/' WV/driver/sonic/ WV/languageDetection/script_data.py WV/pipeline/unspaced_common_data.py`；`git ls-files WV/driver/Neural` | 兩者皆無輸出 |
| 外掛契約測試 | `git diff 9f77382 --stat -- tests/test_plugin_voice_contract.py` | 無輸出 |
| commit 格式 | `git log 9f77382..HEAD --format=%B \| grep -ci co-authored` | 0；4 個 commit 皆英文 `<type>: <summary>` 加內文 |
| tree id（分支） | `git rev-parse <sha>:addon <sha>:tests` | `cc0406c` `0477c569…`／`603bce91…`、`42b9521` `b13d70ab…`／`335a0318…`、`53d5f44` `eb87b28e…`／`9542603a…`，全部等於 plan |
| **plan 重放** | 全新 clone 於 `9f77382`（`ref` symlink、`prek install`），自寫套用器逐步套 Task 1–3 的 `Edit:`／`File:`／bash 區塊、跑每個 `Run:` | Task 1：15 個區塊（8 個測試、7 個原始碼）；red `1 failed, 62 passed, 5 errors`；green `68 passed`、全套件 3227；commit → `0477c569…`／`603bce91…` ✔。Task 2：5 個區塊；red `16 failed, 2 passed, 5 errors`；green `23 passed`、3227；commit → `b13d70ab…`／`335a0318…` ✔。Task 3：45 個區塊（5 個守衛、抽取腳本、4 個 importer、`pyproject`、35 個 harness／測試）；red `10 failed, 11 passed`；green `21 passed`、**3236**；plan 的探針 `57 USED`／`4 UNUSED`；commit → `eb87b28e…`／`9542603a…` ✔。三個 commit 的 hook 都一次通過。`git diff <重放 HEAD> 53d5f44 -- addon tests pyproject.toml` **無輸出** |
| 抽取腳本獨立重跑 | 從 plan 文字切出 `split_pipeline.py`，對 `git show 42b9521:WV/pipeline/__init__.py`（SHA-256 `a1531e96…` = 腳本的 `INPUT_SHA256`）執行 | 8 個模組與 `__init__.py` 和 `53d5f44` 的檔案 `cmp` 全部相同 |
| verbatim move（不經腳本） | 自寫 AST 比對：舊檔 66 個頂層定義（含上方註解與 decorator）vs 新模組 | 66／66 文字完全相同、每模組內順序保留、無缺漏無重複；非空白行多重集合：舊檔只少 3 行 import，新模組只多 69 行標頭 |
| `git diff --color-moved=dimmed-zebra 42b9521 53d5f44 -- WV/pipeline/` | 計數帶色碼的 +／− 行 | 移動 +1128／−1121；未標移動的刪除 7 行（4 行 import、`import re`、`import uuid`、`_MISSING = object()`），新增 67 個非空白行＝標頭 |
| 模組層級共享狀態 | AST 掃舊檔的 `global`、對模組層級名稱的 attribute／subscript store 與可變呼叫 | 0 個 `global`；只有 `_PUNCTUATION_RE_CACHE[chars]`（punctuation）、`_log_writer.write`（registry）、`pl.write`（registry），都和讀寫者同檔 |
| import 週期 | AST 建 `pipeline/` 相對 import 圖＋DFS | 無環 |
| 名稱綁定歧義 | 載入 harness 後掃 14 個模組 namespace | 0 個非 dunder 名稱綁到不同物件 |
| 殘留舊路徑 | `git grep -nE "from \.pipeline import\|pipeline import pl\|WorldVoice\.log\b\|WorldVoice\.sayAll\|log_dir\|log_name\|pipeline\.GENERIC_CONTEXT\|importlib\|sys\.modules\|__package__" -- addon`（排除內層驅動）；`grep -r` `ref/Neural`、`ref/` 其他外掛 | 只有與本階段無關的 `installTasks.py`、`bridge/completionPolicies.py:75`、`engine/__init__.py:20`、`engine/discovery.py:104`；`ref/` 無任何引用。plan Task 4 的 `git grep` 輸出與 plan 列的 5 行完全相同 |
| 純改名 | `git diff -M --summary 9f77382 -- addon` | `log.py => pipeline/recorder.py`（80%）、`{ => pipeline}/sayAll.py`（71%），其餘 8 個 create；差異只有 docstring、路徑計算與 import 行 |
| 翻譯字串 | grep `_(`／`pgettext`／`ngettext` 於 10 個搬動／新建模組 | 無 |
| `pyproject.toml` | 讀 `[tool.mutmut] source_paths`（`:51-58`）與 `per-file-ignores`（`:144-158`） | 8 個新模組取代 `pipeline/__init__.py`；ignores 沒有指到搬動的檔案 |
| 斷言未改 | 17 個被動到的測試檔，`assert` 行排序後 md5 比對 master | 15 個相同；`test_pipeline_log.py` +1、`test_pipeline_structure.py` +2（新測試），無修改或刪除 |
| patch 觀測 | 自寫 plugin 包住所有打在 `*.pipeline.registry` 的 patch 值，5 個測試檔 601 個測試 | 57 USED／4 UNUSED，4 個全是 `pl` 且正是斷言「沒有寫入」的參數化；與 plan 相同 |
| 視圖拒絕 patch | 把 `test_pipeline_stages.py` 第一個 `module.registry` 改回 `module` | `AttributeError: patch current_context on the pipeline module that looks it up, as module.registry` |
| **突變探針**（scratch clone，改後還原） | M1 `registry.py:35` `parents[3]`→`[2]` | pin test 紅（`addon/synthDrivers/log/pipeline.csv`） |
| | M2 `parents[3]`→`[4]` | pin test 紅（repo 根的 `log/pipeline.csv`） |
| | M3 `__init__.py` 寫 `from . import registry` | A2 守衛紅（`import of config halted`，`registry.py:15`）＋ `test_package_init_stays_empty[pipeline]` 紅 |
| | M4 `__init__.py` 寫 `from . import numbers` | `test_package_init_stays_empty[pipeline]` 紅（A2 守衛因載入集合未變而綠——這就是 phase 37 M1 加的空檔守衛存在的理由） |
| | M5 `__init__.py` 只有一個換行 | `test_package_init_stays_empty[pipeline]` 紅 |
| | M6 `numbers.py` 加 `import config` | `test_number_lexing_imports_only_the_standard_library` 紅 |
| | M7 `numbers.py` 加 `from ..numberLanguage import FOLLOW` | 同上紅（`node.level == 0`） |
| | M8 `unregister_stages` 改註銷重新綁的 handler | `test_register_puts_stages_first_in_order_and_unregister_removes_them` 紅 |
| | M9 `_LogWriter.write` 改讀 import 時的 `pl` 副本 | `test_pipeline_stages.py`／`test_pipeline_filters.py` 多個紅（`'PipelineLog' object has no attribute 'write'`） |
| 看門狗 | 全程輪詢 `/proc/meminfo`，< 3 GB 即 `pkill` pytest | 沒有觸發（MemAvailable 起始 5.6 GB） |
| 未做 | 打包、Windows／NVDA 實機、mutmut | 未做。spec §6 說本階段無新決策邏輯，不需 mutmut；無行為變更。NVDA 實機上「開啟 WorldVoice 設定對話框、切換／匯出 pipeline log、Say All 仍有停頓」是下次打包時要看的項目。 |

## 使用者還沒確認的使用者可見預設

- 無使用者可見的變動：沒有任何設定鍵、confspec、預設值或 UI 字串變動；pipeline log 仍寫到 `addon/log/pipeline.csv`，匯出仍是同一個檔。
- 三個結構性的 Ruling 與路線圖 `storage/refactor8.md` 的建議不同，spec §7 註明「使用者可在 merge 前推翻」：(1) `pipeline/__init__.py` 留空而不是 re-export（§2.1 原建議 re-export）；(2) 八個模組而不是六個；(3) log 路徑由 `registry.py` 以 `parents[3]` 計算，而不是由 synth／全域外掛注入（§2.6 原建議注入）。三者我都認為實作的選擇較好（見「帳本 `Ruling:` 的評估」），而且使用者看不到差別。

## 給修正者／協調者的備註

- 沒有擋 merge 的項目；`master` 仍在基準上，可直接 `--ff-only`。
- 若修 M2／M3（都只動 `tests/`），`HEAD:addon` 仍是 `eb87b28e2eee4ec6c4a3c03249b182e3a6d3f05d`，`HEAD:tests` 會變；依 §4.5 在 plan 檔尾加「## 修正」段落寫出 `Edit:` 區塊和 commit 後的 tree id，從 Task 3 的 tree 接著 dry run。M1 建議留到測試衛生階段，和 phase 37 M5 一起處理。
- 我的 scratch clone（`replay-phase38`、`probe-phase38`）、套用器、探針 plugin 與報告檔審完已刪除。
