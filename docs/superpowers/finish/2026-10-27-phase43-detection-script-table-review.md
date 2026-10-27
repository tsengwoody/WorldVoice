# Phase 43 Review 紀錄：語言偵測的 script 表格（`languageDetection/scriptLanguages.py`）

日期：2026-10-27。分支：`phase43-detection-script-table`（`85bcf54..e7d2112`，6 個 commit：2 個 docs（spec、plan）、4 個 refactor），worktree `/workspace/WorldVoice-phase43`。
依據：

- 規格 `docs/superpowers/specs/2026-10-27-phase43-detection-script-table-design.md`
- 計畫 `docs/superpowers/plans/2026-10-27-phase43-detection-script-table.md`（5 個 task，Review Focus 5 項）
- 進度帳本 `.superpowers/sdd/2026-10-27-phase43-detection-script-table/progress.md`（5 條 `Ruling:`；`.superpowers/` 被 git 忽略）
- 路線圖 `storage/refactor9.md` §4.2 F7、§4.1「其他 SRP 觀察」第三點、§5.2／§5.3 的 `languageDetection` 列、§6 P43 列、§6.1 命名規則
- `DEVELOPMENT_WORKFLOW.md` §3.3、§7、§8

流程：審閱者 Fable 5.1，唯讀。全套件、prek 與受保護路徑檢查在任務 worktree 上跑；守衛測試的「還原／破壞」探針在 scratchpad 的暫時 worktree（`git worktree add --detach … e7d2112`，`ref` symlink）上逐一施加、跑對應測試、`git checkout` 還原，審完移除。pytest 一次只跑一個行程，外層是 `runtests.sh` 的 MemAvailable < 3 GB 看門狗（全程沒有觸發，起始約 5.9 GB）。沒有 push、沒有 stash、沒有動主 checkout、沒有修改分支上的原始碼或測試；本文件是審閱者在任務分支上唯一的 commit。

`file:line` 以 `e7d2112` 為準；`WV/<path>` = `addon/synthDrivers/WorldVoice/<path>`，`dialog.py` = `addon/globalPlugins/WorldVoice/speechSettingsDialog.py`。

## 結論

Ready to merge：**是**。Critical 0、Important 0、Minor 4（M1 建議 merge 前順手修，其餘不擋 merge）。

- **沒有使用者可見的變化。** confspec 的 key、default 與順序：`settings.py:18-21` 以 `{**{row.config_key: f"string(default={row.default_language})" …}, "DetectLanguageTiming": …}` 展開，表格順序 Latin、Han、Arabic、Cyrillic、Devanagari 再接 timing，與 master `settings.py:15-23` 逐 key 相同；`SCRIPT_CONFIG_KEYS`（`:23`）同一張表，與 master `:25-31` 相同。既有的字面釘住測試 `test_confspec_and_script_keys_keep_the_stored_names_and_defaults`（`tests/test_detection_settings.py:153-170`）斷言一字未改且綠。對話框 `dialog.py:505-514` 改成迭代 `DETECTION_SCRIPTS`，控制項順序、五個 msgid、`# Translators:` 註解（`:532-544`）、`_add_script_choice` 的候選計算與 `onSave` 都沒變；`git diff 85bcf54 e7d2112 -- addon/locale` 空。
- **偵測器是純搬移。** `c0b9e6f:WV/languageDetection/__init__.py` 與 `e7d2112:WV/languageDetection/detector.py` 的 blob id 相同（`b2e05f68…`）；再和 master 的 `__init__.py` 比，去掉 `:8-95` 資料區後唯一差異是第 7 行多了 `from .scriptLanguages import SCRIPT_LANGUAGES`。資料區 88 行逐位元組連續出現在 `scriptLanguages.py:9-96`（Task 1 Step 5 的檢查我自己重做，`True`）。`git diff -M` 看不出 100% rename 是因為 `__init__.py` 仍在（清空成 0 位元組），不是內容有差。
- **所有 importer 都跟上了。** `git grep languageDetection e7d2112` 之後，import 偵測器的只剩 synth `WV/__init__.py:34`（`from .languageDetection.detector import LanguageDetector`，`:267` 改成直接呼叫）；對話框 `dialog.py:14-15` 只 import `scriptLanguages` 與 `settings`；`pyproject.toml:64` mutmut 路徑改到 `detector.py`；測試 9 個檔跟著改路徑（含 plan 沒列、帳本 Ruling 5 補的 `tests/test_format_outputs.py`）。`ref/Neural` 沒有任何 `languageDetection`／`LanguageDetector` 引用（`grep -rn` 空）；其他 `ref/` 目錄、`tools/`、`buildVars.py`、`sconstruct`、readme 都沒有提到這個套件；`addon/locale/ru/…/nvda.po:24,26` 的 `X-Poedit-SearchPath` 只是目錄路徑，目錄還在。沒有任何地方還用 `languageDetection.LanguageDetector`／`languageDetection.SCRIPT_LANGUAGES` 這種「套件屬性」寫法。refactor9 §5.3 本來就記 `languageDetection` 無公開路徑影響。
- **新守衛都真的會抓**（詳見「守衛探針」表）：少一列、換順序、`scriptLanguages.py` 多一個 NVDA import 或相對 import、對話框再 import 套件或偵測器、`__init__.py` 再匯出、設定鍵字面寫在表格外、settings 改回字面 dict、標籤少一個、拿掉 `# Translators:`，對應的測試全部紅。
- **§8：** 6 個 commit 都是英文 `<type>: <summary>` 加內文，0 個 `Co-Authored-By`；每個 commit 的檔案清單都只含該 task 的檔（表格）；沒有碰 `driver/<Engine>/driver/`、`driver/sonic/`、兩個產生檔、Neural；`git diff --check` 乾淨；`prek run --all-files` 8 個 hook 全數 Passed 且沒改檔；全套件 **3257 passed、0 skipped**（基準 3247，+10 = 新守衛 9 + `test_package_init_stays_empty[languageDetection]` 1，與 plan Task 5 相同）。
- **執行緒與鎖：** 本階段只動資料表、衍生與 import，沒有碰任何鎖、callback 或執行緒程式碼。

## 三個決定的評估

### 1. 表格不含翻譯標籤（協調者預設，使用者可推翻）

**同意。** 理由成立：`scriptLanguages.py` 只 import `dataclasses`，`test_script_languages_import_only_the_standard_library` 與 `test_script_languages_import_by_their_package_path_without_nvda`（`tests/test_script_languages.py:36-47`、`:81-101`）把「不依賴 NVDA」釘成規則，將來抽成獨立函式庫時表格可以原樣帶走；refactor9 F7 草案的 `label` 欄位會把 `addonHandler.initTranslation()` 帶進核心套件，和 §6.1「可攜核心」的歸屬矛盾。代價要說清楚：**新增一種 script 仍要改兩處**（表格一列 + `dialog.py:532` `_script_labels` 一個標籤），不是路線圖 P43 列寫的「改一處」；但漏掉標籤時 `test_detection_panel_lists_every_table_script`（`tests/test_unicode_panel.py:168-179`）會紅（探針 M8：8 個 panel 測試全紅），而且 `dialog.py:511` 的 `labels[detectionScript.script]` 在面板開啟時會 `KeyError`——這和 master 時「有標籤沒 key」的失敗類別相同（spec §1.1），差別是現在測試擋得住。可接受。

### 2. 偵測器搬到 `detector.py`、`__init__.py` 清空（實作者 Ruling 1）

**同意，而且是唯一能同時達成 spec 目標 3／4 的做法。** Python 載入 `a.b.c` 一定先執行 `a/__init__.py` 和 `a/b/__init__.py`；偵測器若留在 `languageDetection/__init__.py`，對話框只要 import `scriptLanguages` 就會把 `speech.commands` 一起載進來，「對話框不再載入偵測器」與「以套件路徑在無 NVDA 下 import」兩個守衛都不可能成立。refactor9 §5.2／§5.3 寫的「`__init__.py` 再匯出 `SCRIPT_LANGUAGES`」也和 §7.2「不讓套件 `__init__.py` 再匯出」的既有政策相違，清空反而和 `bridge/ voices/ ui/ pipeline/ unicodeScripts/` 一致（`tests/test_runtime_import_guard.py:55-64` 現在把 `languageDetection` 一起列入）。mutmut 路徑、六個測試 helper、synth 入口都查過（上節）。帳本記的 fallback（revert `e7d2112`、守衛改成檔案路徑）可行。需要在 merge 後把 `storage/refactor9.md` §5.2／§5.3 的那一列和 P43 列的檔案清單改成實際做法（見 M4）。

### 3. 帳本 Ruling 2–5，特別是 `tests/nvda_stubs.py` 的 AST walker

| # | Ruling | 評估 |
| --- | --- | --- |
| 2 | config stub 用小型 AST walker 展開 `DETECTION_SCRIPTS` 的 dict comprehension，不 `eval` add-on 原始碼 | **合理，不算過度設計**：和同檔 `PIPELINE_CONFSPEC`／`LOG_SWITCHES` 從 `PipelineSettingSpec(...)` 呼叫讀表的既有做法（`:93-120`）同一套路，walker 只認 `row.<field>`、常數、f-string 三種節點，其他一律 `ValueError`（探針 M10：把值改成 `row.default_language.lower()`，stub 測試立刻以 `ValueError` 紅）。**但有一個會默默漂移的洞**：`_detection_confspec`（`:123-141`，條件在 `:130-134`）只檢查 `len(generators) == 1` 和 `iter == DETECTION_SCRIPTS`，**沒檢查 `generators[0].ifs`**，comprehension 加了 `if` 篩選時 walker 仍把每一列都放進 stub（探針 M9：`if row.script != "Latin"` 後，`test_the_config_stub_reads_the_detection_defaults_from_the_table` 仍綠，只有字面釘住測試和 derive 測試紅）。現在靠「stub == 表格、表格 == 字面、settings == 字面」三角關係間接守住；見 M1 的修法。 |
| 3 | `load_settings_module` 用 `load_source` 註冊真的 `scriptLanguages`，`table` 以 callable 接收 | 合理；alias 套件讓 `from .scriptLanguages import` 在不跑 `__init__.py` 的情況下解析，monkeypatch 在測試結束時清掉 `sys.modules`。 |
| 4 | `tests/ui_harness.py:756-761` 不再 stub `languageDetection` 套件，直接註冊真的 `scriptLanguages.py` | 合理；`from a.b.c import X` 在 `sys.modules["a.b.c"]` 已存在時不會再 import 父套件，整個 dialog 測試檔綠。帳本寫的代價（對話框若再 import 裸套件會在 harness 失敗）同時也被 `test_the_dialog_reads_the_tables_without_the_detector` 擋住（探針 M4）。 |
| 5 | `tests/test_format_outputs.py` 改用 `detector_harness.PACKAGE` | 合理；原本從 `env.module.__name__` 砍一層算套件名，偵測器深了一層就會算錯，改成直接用常數更穩。 |

## Critical

無。

## Important

無。

## Minor

### M1. config stub 的 walker 不檢查 comprehension 的 `if`，且 stub 測試只對表格、不對真的 settings 模組

- 位置：`tests/nvda_stubs.py:130-134`（只檢查 `generators` 長度與 `iter`）；`tests/test_detection_settings.py:186-194`（`test_the_config_stub_reads_the_detection_defaults_from_the_table` 把 `worldvoice_conf()` 和 `DETECTION_SCRIPTS` 比，不和載入的 `module.DETECTION_CONFSPEC` 比）。
- 失敗情境：將來有人在 `settings.py:19` 的 comprehension 加 `if`（例如某個 script 改成不存設定），真的 confspec 少一個 key，但每個用 `worldvoice_conf()` 建新 profile 的測試仍拿到那個 key 的預設值；修改者會順手更新字面釘住測試與 derive 測試，stub 測試照樣綠，於是整套測試在一個 NVDA 實際沒有的設定鍵上跑。探針 M9 已證實這條路徑現在不會紅。
- 建議（便宜，merge 前順手修）：(a) `_detection_confspec` 的 `elif` 條件加上 `and not value.generators[0].ifs and not value.generators[0].is_async`，讓篩選式 comprehension 走 `ValueError`；(b) stub 測試改成和真的模組比：`module = load_settings_module(monkeypatch)`，斷言 `{key: nvda_stubs._confspec_default(v) for key, v in module.DETECTION_CONFSPEC.items()} == worldvoice_conf()["WorldVoice"]["autoLanguageSwitching"]`，這樣 walker 和 settings 的任何分歧都直接紅，不必靠三角關係。

### M2. 沒有測試釘住 `SCRIPT_LANGUAGES` 的內容（Review Focus 4 只靠一次性的逐位元組比對）

- 位置：`WV/languageDetection/scriptLanguages.py:67-96`；`tests/test_language_detector.py` 全檔。
- 現象：探針 M12 把 `"Hebrew": ("he",)` 整列刪掉，`tests/test_language_detector.py` 75 個測試全綠——property 測試從表格本身抽樣，所以表格少一列它們看不到。這次的搬移我已用 base blob 逐位元組確認過（`True`），而且 master 本來也沒有這種釘住，不是本階段造成的回歸；只是 plan Review Focus 4 把「全套件」列為保護，實際保護只有 Step 5 的手動比對。
- 建議（可延後）：在 `tests/test_script_languages.py` 加一個小釘子，例如斷言 `set(SCRIPT_LANGUAGES) == {28 個 script 名}` 和 `len(ALL_LATIN) == 47`，讓將來改候選表的人至少要有意識地更新測試。不擋 merge。

### M3. 兩處註解／docstring 在 Task 4 之後過時

- `tests/test_pipeline_structure.py:40-41`：「an import of languageDetection would load the detector, and NVDA's speech commands with it」——`__init__.py` 已經是空的，import 套件本身不會載入偵測器了；守衛仍有意義（pipeline 不該依賴偵測套件），只是理由要改成「pipeline 只需要 `unicodeScripts/`」。
- `tests/test_detection_settings.py:26`：`load_settings_module` 的 docstring 說「whose `__init__.py` (the detector) never runs」——偵測器現在是 `detector.py`，`__init__.py` 為空。
- 建議：兩行文字改掉即可，和 M1 一起處理。

### M4. merge 後要更新的分支外文件

- `storage/refactor9.md` §5.2／§5.3 的 `languageDetection/__init__.py:8-95 → scriptLanguages.py` 列（寫的是「`__init__.py` 再匯出 `SCRIPT_LANGUAGES`」，實際是清空並新增 `detector.py`）、§6 P43 列的檔案清單（`languageDetection/__init__.py` → `detector.py` + 空 `__init__.py`）與「新增 script 改一處」（實際是表格一列 + 標籤一個，由守衛擋漏）、merge sha 與 3257；auto-memory 的 roadmap 條目。
- 順帶：`storage/refactor9.md` §4.1 第三點與 F7 引用的 `languageDetection/__init__.py:98` 等行號是 master 的歷史描述，可留。

## plan 的 Review Focus 逐項

| # | 項目 | 結果 |
| --- | --- | --- |
| 1 | 非預設選擇的 profile（Cyrillic `uk`、Devanagari `mr`）讀寫同樣的 key | `test_update_writes_the_cyrillic_and_devanagari_keys`、`test_the_shared_service_reads_nvda_config` 零變動且綠；`test_detection_confspec_and_keys_derive_from_the_table` 用加了 Hebrew 的表格確認 key 跟著表格、timing 殿後。`DetectionSettingsService` 本體（`settings.py:40` 起）沒改。 |
| 2 | 新 profile 的預設值（NVDA confspec 與測試的 config stub） | 字面釘住測試綠；stub 測試綠。stub 的洞見 M1（現況靠三角關係守住，仍正確）。 |
| 3 | 某 script 沒有語音時停用且不存；Tab 順序 | `test_script_without_candidates_is_disabled_and_not_saved`、`test_controls_choices_and_selections` 零變動且綠；`test_detection_panel_lists_every_table_script` 以反轉表格確認控制項順序跟表格，並確認存檔寫入的是該列的 key（`STORED` 的 Latin 是 `fr`，Select(0) 後存成 `en`，所以不是「本來就是 en」的假陽性）。 |
| 4 | 表格外 script（Hebrew、Thai、kana…）的偵測不變 | 資料區逐位元組比對 `True`；偵測器 blob 相同；`tests/test_language_detector.py` 全綠。但套件本身沒有釘住候選表（M2）。 |
| 5 | synth 啟動／關閉從新模組建構與拆解偵測器 | `tests/test_worldvoice_lifecycle.py`、`tests/test_runtime_composition.py`（真的 `WV/__init__.py`，stub `languageDetection.detector`）、`tests/test_worldvoice_speak.py` 綠；`WV/__init__.py:34`、`:267` 兩處改法正確。 |

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 全套件 | `runtests.sh /workspace/WorldVoice-phase43 tests`（單一行程，看門狗） | **3257 passed、0 skipped**（95 s）；看門狗未觸發 |
| hook | `prek run --all-files`（任務 worktree） | 8 個 hook 全數 Passed；`git status --short` 空 |
| 空白 | `git diff --check 85bcf54 e7d2112` | 無輸出 |
| 受保護路徑 | `git diff --stat 85bcf54 e7d2112 -- 'WV/driver/*/driver/' WV/driver/sonic/ WV/unicodeScripts/script_data.py WV/unicodeScripts/unspaced_common_data.py`；`git ls-files WV/driver/Neural` | 都無輸出 |
| 翻譯檔 | `git diff --stat 85bcf54 e7d2112 -- addon/locale` | 無輸出 |
| 設定鍵只在表格 | `grep -rln CharactersLanguage addon --include=*.py` | 只有 `scriptLanguages.py` |
| 偵測器純搬移 | `git rev-parse c0b9e6f:…/__init__.py e7d2112:…/detector.py` | 同一 blob `b2e05f68…` |
| 偵測器與 master 的差異 | `diff <(git show 85bcf54:…/__init__.py \| sed '8,95d') <(git show e7d2112:…/detector.py)` | 只有第 7 行多 `from .scriptLanguages import SCRIPT_LANGUAGES` |
| 資料區逐位元組 | master `__init__.py:8-95` 文字 `in` `scriptLanguages.py` 文字 | `True` |
| importer 全查 | `git grep -n languageDetection e7d2112`（排除 docs）；`grep -rn languageDetection\|LanguageDetector ref/Neural`；`tools/`、`buildVars.py`、`sconstruct`、readme | 見「結論」第三點；Neural 與其他位置皆無 |
| commit 衛生 | `git log --format=%B 85bcf54..e7d2112 \| grep -i co-authored`；每個 commit `git show --stat` | 0 個 trailer；6 個 commit 的檔案清單各只含該 task 的檔 |
| 使用者可見字串 | `git diff 85bcf54 e7d2112 -- dialog.py` | 五個 `# Translators:` 與 msgid 未動；只改 import 與 `makeSettings`、`_add_script_choice` 的來源 |

### 守衛探針（暫時 worktree，每項施加後跑對應測試再還原）

| # | 破壞 | 預期紅的守衛 | 結果 |
| --- | --- | --- | --- |
| M1 | 刪掉表格的 Devanagari 列 | 表格釘住、confspec 字面釘住、stub、panel | 13 failed（含 `test_detection_scripts_keep…`、`test_confspec_and_script_keys_keep…`、`test_the_config_stub_reads…`、`test_controls_choices_and_selections`、`test_detection_panel_lists_every_table_script`） |
| M2 | Latin／Han 兩列對調 | 表格釘住、panel 順序 | 5 failed |
| M3 | `scriptLanguages.py` 加 `import config` | 標準庫守衛、套件路徑守衛 | 2 failed + 2 error（fixture 載不進） |
| M3b | `scriptLanguages.py` 加 `from ..locales import …` | 同上（`level != 0`；載入名單多了 `locales`） | 2 failed + 2 error |
| M4 | 對話框加回 `from synthDrivers.WorldVoice import languageDetection` | `test_the_dialog_reads_the_tables_without_the_detector` | 1 failed |
| M4b | 對話框 import `languageDetection.detector` | 同上 | 1 failed |
| M5 | `languageDetection/__init__.py` 寫一行再匯出 | `test_package_init_stays_empty[languageDetection]`、套件路徑守衛 | 2 failed |
| M6 | `settings.py` 加 `_HEBREW_KEY = "hebrewCharactersLanguage"` | `test_script_config_keys_are_written_only_in_the_table` | 1 failed |
| M7 | `settings.py` 整檔換回 master 的字面 dict | derive 測試、唯一位置守衛（stub 對字面 dict 仍能讀，其餘 20 個綠） | 2 failed |
| M8 | `_script_labels` 刪掉 Devanagari | panel 覆蓋守衛 | 8 failed（`KeyError`，含 `test_detection_panel_lists_every_table_script`） |
| M9 | comprehension 加 `if row.script != "Latin"` | （探洞）stub 測試應紅 | **stub 測試綠**；只有字面釘住與 derive 紅 → M1 |
| M10 | comprehension 的值改成 `row.default_language.lower()` | stub 以 `ValueError` 紅 | 1 failed（`ValueError: Unexpected detection confspec expression`） |
| M11 | 刪掉 Cyrillic 的 `# Translators:` | `tests/test_translator_comments.py` | 1 failed（指到 `dialog.py:540`） |
| M12 | `SCRIPT_LANGUAGES` 刪掉 `"Hebrew"` | （探洞）偵測器測試 | **75 passed** → M2 |

## 使用者還沒確認的使用者可見預設

本階段沒有任何使用者可見的預設或行為變化（面板順序、標籤、設定鍵、預設值、存檔值都和 master 相同）。兩個**內部**決定仍可由使用者推翻：

1. 表格不含翻譯標籤，標籤留在對話框並由覆蓋測試守住（協調者預設）；代價是新增 script 要改表格一列加標籤一個，而非一處。
2. `LanguageDetector` 搬到 `languageDetection/detector.py`、`languageDetection/__init__.py` 清空（實作者 Ruling 1，偏離 refactor9 §5.2 的假設）；`languageDetection` 非公開路徑，Neural 不受影響。

## 給修正者／協調者的備註

- M1、M3 都只動 `tests/`，合計約 6 行，建議 merge 前一起修；M2 可延後；M4 在 merge 後由協調者處理。
- 未打包、未在 Windows／NVDA 上驗證（本階段沒有使用者可見變化，spec §6 的 smoke check 為可選）。

## 修正記錄

| 項目 | commit | 修正內容與驗證 |
| --- | --- | --- |
| M1 | `2e08302` | `tests/nvda_stubs.py` 的 `_detection_confspec` 遇到帶 `if` 或 `async` 的 comprehension 改丟 `ValueError`；`test_the_config_stub_reads_the_detection_defaults_from_the_table` 改成和載入的 settings 模組真正的 `DETECTION_CONFSPEC`（經 `_confspec_default`）比對，並斷言 stub 除此之外只多三個 `KeepMainLocale*` 鍵。紅燈：新增的 `test_the_config_stub_rejects_a_detection_confspec_it_cannot_read`（兩個參數）修正前 2 failed；探針：在 `settings.py` 的 comprehension 暫時加 `if row.script != "Latin"`，強化後的 stub 測試在修 walker 前即紅（stub 多出 `latinCharactersLanguage`），還原後綠。 |
| M2 | `db7de82` | `tests/test_script_languages.py` 新增 `test_script_languages_keep_their_scripts_and_candidates`：釘住 28 個 script 的順序、非 Latin 各 script 的候選語言（含順序），以及 `ALL_LATIN == BASIC_LATIN + EXTENDED_LATIN`、長度 14／33、首位 `en`。探針：暫時刪掉 `"Hebrew": ("he",)` 一列，該測試紅（1 failed），還原後綠。 |
| M3 | `27d2ce8` | 更新 `tests/test_pipeline_structure.py` 守衛的註解與 `tests/test_detection_settings.py` `load_settings_module` 的 docstring，改為說明偵測器在 `detector.py`、`__init__.py` 為空。探針：修正前 `grep` 找得到兩處過時文字，修正後找不到。 |
| M4 | — | 依協調者指示不在本分支處理（分支外文件，merge 後由協調者更新）。 |

修正後完整驗證：`python3 -m pytest -q tests` → 3260 passed、0 skipped（修正前 3257／0，新增 3 個測試）；`prek run --all-files` 全部 Passed；`git diff --check master` 無輸出；受保護路徑的兩個指令皆無輸出。
