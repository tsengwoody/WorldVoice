# Phase 39 Review 紀錄：命名收尾（`engineRegistry/`、`bringup.py`、`speechDictionary.py`、`runtime/voiceSettings.py`、`unicodeScripts/`）

日期：2026-10-26。分支：`phase39-naming-cleanup`（`e54d804..0b1857a`，8 個 commit：1 個 docs（spec、plan）、5 個 refactor、2 個 test），worktree `/workspace/WorldVoice-phase39`。
依據：

- 規格 `docs/superpowers/specs/2026-10-26-phase39-naming-cleanup-design.md`
- 計畫 `docs/superpowers/plans/2026-10-26-phase39-naming-cleanup.md`（8 個 task、157 個 `Edit:` 區塊、0 個 `File:` 區塊（新檔只有 0 位元組的 `unicodeScripts/__init__.py`，由 bash 區塊的 `: >` 建立）、17 個 bash 區塊、19 個 `Run:`、Review Focus 5 項，每個 commit 都記了 `HEAD:addon`／`HEAD:tests` tree id（Task 5 另記 `HEAD:tools`、`pyproject.toml`、`.pre-commit-config.yaml` 的 blob id），檔尾有 dry run 紀錄）
- 進度帳本 `.superpowers/sdd/2026-10-26-phase39-naming-cleanup/progress.md`（6 條 `Ruling:`；`.superpowers/` 被 git 忽略，不在 commit 裡）
- 路線圖 `storage/refactor8.md` §2.4（F4）、§2.9（F9）、§2.10（F10）、§2.11（F11 的 `assembly.py`、`languageDetection/scripts.py` 兩項）、§4.3（A3）、§6「階段 39」，以及檔尾延後到本階段的兩項（階段 37 review M4 的 helper 改名、階段 38 review M2 的 `recorder.py`）
- `DEVELOPMENT_WORKFLOW.md` §3.3、§4.5（複雜流程：在 scratch 複本重放 plan、比對 tree id）、§4.6、§7、§8
- 使用者核准的範圍（2026-10-26）：階段 39 的每一個可選項目；兩個產生檔授權搬移，但必須是 100% rename，且仍等於 `tools/` 產生器的輸出。

流程：審閱者 Fable 5.1，唯讀。`master` 仍在 plan 的基準 `e54d804`（`git log master -1` 確認），§4.6 的重新 dry run 條件不成立。plan 重放在 scratchpad 的全新 clone（`git clone /workspace/WorldVoice`，checkout `e54d804`，`ref` symlink，`prek install`）上用我自己寫的套用器進行（只解析 plan 的 `### Task N:`／`- [ ] **Step S:`／`**Edit:**`（Replace／With 兩個 `text` 圍欄）／bash 圍欄／`Run:` 標記，和實作者 scratchpad `p39/` 的 `planrun.py`、`land.sh` 互不相依）；重放做了四遍，前三遍因為我自己 scratch 環境的錯誤作廢（第一遍：套用器對 focused run 多加了一組 `-q`，`-qq` 吃掉 pytest 的統計行；中止後 `git clean -fd` 沒加 `-x`，留下 git 忽略的 `engineRegistry/__pycache__/`，讓 `git mv engine engineRegistry` 把 `engine` 搬進了既有目錄。第二、三遍：全新 clone 沒有 git 作者身分——這個容器的 `user.name`／`user.email` 只設在主 checkout 的 `.git/config`，clone 不會繼承——七個 `git commit` 都以 `Author identity unknown` 失敗；但 19 個 `Run:` 的 red／green 輸出兩遍都和 plan 一字不差，而且累積的工作樹 `git write-tree` 得到根 tree `e81e389cedc091f73dd96e2eba0391b14c722c7e`，正是 plan dry run 紀錄寫的原型根 tree，所以內容早已吻合，差的只是 commit 與 hook）。下文的「plan 重放」表以第四遍為準：`git reset --hard e54d804 && git clean -fdx -e ref` 後的 pristine clone，`git config user.name/user.email` 設在 clone 本機（tree id 不含作者），commit 經過 prek hook。產生檔的再產生、突變探針、全套件與 prek 在另一個 scratch clone（分支 `0b1857a`）進行；審完兩個 clone 都刪除。pytest 最多同時 2 個行程，外層有 MemAvailable < 3 GB 就停掉的看門狗（全程沒有觸發，起始約 5.0 GB）。沒有 push、沒有 stash、沒有動主 checkout、沒有修改分支上的原始碼或測試；本文件是審閱者在任務分支上唯一的 commit。

`file:line` 以 `0b1857a` 為準；`WV/<path>` = `addon/synthDrivers/WorldVoice/<path>`。

## 結論

Ready to merge：**是**。Critical 0、Important 0、Minor 2（都不擋 merge；M1 是測試衛生，M2 是 merge 後要改的分支外文件）。

- **純搬移成立，沒有 plan 以外的修改。** 在 pristine clone 從 `e54d804` 照 plan 逐步重放 Task 1–7，七個 commit 的 `HEAD:addon`／`HEAD:tests` 全部和 plan、和分支一致，Task 5 之後的 `HEAD:tools` = `e0b77368…` 也一致（表格「plan 重放」）；`git diff <重放 HEAD> 0b1857a -- addon tests tools pyproject.toml .pre-commit-config.yaml` 沒有輸出；`HEAD:pyproject.toml` = `ffcc33ea…`、`HEAD:.pre-commit-config.yaml` = `7b0c8e0b…` 與 plan Task 5 記的 blob id 相同，重放 HEAD 的根 tree `e81e389cedc091f73dd96e2eba0391b14c722c7e` 等於 plan dry run 紀錄寫的原型根 tree。docs commit `b54d5ce` 只動 `docs/`（spec 122 行、plan 3436 行）。七個 commit 的 prek hook 都一次通過（commit 後 `git status --short` 都是空的）。
- **add-on 的 diff 只有改名會帶出的東西。** `git diff -M e54d804 0b1857a -- addon`：`assembly.py => bringup.py`（100%）、`runtime/settings.py => voiceSettings.py`（100%）、兩個產生檔（100%）、`engine/discovery.py => engineRegistry/discovery.py`（99%，只有 `from ..assembly import timed` → `..bringup`）、`pipeline/speech_dictionary.py => speechDictionary.py`（95%，只有 `..assembly` → `..bringup`）、`engine/__init__.py => engineRegistry/__init__.py`（80%，只多 7 行 docstring）、`languageDetection/scripts.py => unicodeScripts/lookup.py`（78%，只多 1 行 docstring 和空行）、新的 0 位元組 `unicodeScripts/__init__.py`；其餘 11 個檔案每個只改 import 行或註解裡的模組名：`WV/__init__.py:29-35`（isort 把 `.bringup` 排到 `.bridge.*` 之後）、`:55`、`runtime/session.py:17`、`bridge/voiceFacade.py:7`、`bridge/engineAdapter.py:24`（註解）、`voices/manager.py:15`、`voices/mainLocalePolicy.py:7`、`voices/settingsRepository.py:6`、`languageDetection/__init__.py:6`、`pipeline/registry.py:20`、`:178`、`:188`、`pipeline/unspaced.py:10-11`、`:22-24`（註解重排成三行）、`globalPlugins/WorldVoice/speechSettingsDialog.py:14`、`rolePresenter.py:5`。沒有任何類別、函式、常數或屬性改名，沒有 `_(` 字串變動（搬動的模組裡沒有翻譯字串），`buildVars.py` 沒有指到任何搬動的路徑。
- **兩個產生檔 100% rename，而且仍是產生器的輸出。** `git diff -M100% --name-status e54d804 0b1857a` 列出 `R100 …/languageDetection/script_data.py → …/unicodeScripts/script_data.py` 與 `R100 …/pipeline/unspaced_common_data.py → …/unicodeScripts/unspaced_common_data.py`；基準 blob 與新路徑的 sha256 相同（`eb570540…`、`00bd8d06…`）。再用分支上的 `tools/generate_unicode_scripts.py`、`tools/generate_unspaced_common.py` 從 unicode.org 下載 Unicode 18.0.0 的 Scripts.txt、ScriptExtensions.txt、UnicodeData.txt（以檔內記的 `SOURCE_SHA256`／`UNICODE_DATA_SHA256` 當 `--expected-sha256`／`--unicode-data-sha256`）寫到 scratch 目錄，`cmp` 與分支上的兩個檔案完全相同；`tests/test_generated_unicode_data.py` 在新路徑也綠。產生器的 docstring、用法範例與 `SCRIPT_DATA` 預設（`tools/generate_unspaced_common.py:43`）、`pyproject.toml:24`（coverage omit）與 `:108`（ruff exclude）、`.pre-commit-config.yaml:12`、`tests/test_translator_comments.py:8` 的排除都跟著走；`unspaced_common_data.py` 一如以往不在 ruff／pre-commit 的排除裡（它本來就通過 ruff）。
- **公開 import 路徑沒有變。** `tests/test_plugin_voice_contract.py` 零變動且綠；`driver/__init__.py`、`driver/*/__init__.py` 的 `runtime` import 只有 `engineControl`、`models`、`playbackWork`、`segmentHost`、`session`（`git grep`），沒有任何包裝器 import `runtime.settings`；`ref/` 底下只有 `ref/Neural/Neural/__init__.py:2` 以 `from synthDrivers.WorldVoice.driver import Voice` 用到 WorldVoice（其他 `ref/` 目錄沒有任何 `synthDrivers.WorldVoice` 引用），所以 `runtime/settings.py` 的改名閘門成立。`text/`、`driver/sonic/`、`driver/<Engine>/driver/` 未動。
- **以字串算模組名的地方只剩兩處，都和深度有關而深度沒變。** `engineRegistry/__init__.py:23` `PACKAGE_ROOT = dirname(dirname(__file__))` 與 `:27` `INTERNAL_DRIVER_PACKAGE = f"{__package__.rsplit('.', 1)[0]}.driver"` 和 master 的 `engine/__init__.py:16`、`:20` 逐字相同，套件仍在 synth 下一層；`tests/test_engine_registry.py:59` 以 `spec.module_name == f"{PACKAGE}.driver.{spec.name}"` 釘住，把 `rsplit` 拿掉或 `PACKAGE_ROOT` 少一層都紅（突變探針 M8、M9）。另一處 `bridge/completionPolicies.py:75` 用自己的 `__package__` 算 `.driver.`，與本階段無關。`pipeline/registry.py:35` 的 `parents[3]` 不受影響（`recorder.py` 沒搬）。`installTasks.py` 的 `importlib` 載的是 `core/`，無關。
- **依賴方向與 import 圖。** 用 AST 算 `WV/` 內所有相對 import（排除內層驅動），套件層級：`languageDetection → {locales, numberLanguage, speechCommands, unicodeScripts}`、`pipeline → {bringup, numberLanguage, runtime, speechCommands, unicodeScripts}`、`unicodeScripts → {}`（只有 `lookup → script_data`）、`engineRegistry → {bringup, workspace}`；`pipeline/` 的任何模組都不再 import `languageDetection`；import `languageDetection` 的只剩 synth `WV/__init__.py:28`（和 `speechSettingsDialog.py:13` 的絕對 import）；模組層級 DFS 沒有環。NVDA 啟動時 synth 套件在 `:28` 就直接 import `languageDetection`，比 `.pipeline.*`（`:37-52`）早，所以沒有任何東西靠「pipeline 順便載入 languageDetection」——master 時 `unspaced.py` 的 `from ..languageDetection.scripts import` 只是多載一次已經載入的套件。`unicodeScripts/` 不 import 任何 NVDA 模組，`tests/test_unicode_scripts.py` 因此不必再為 `languageDetection` 做「沒有 `__init__` 的 alias」（`:15-18` 刪掉兩行），直接 import 真的套件。
- **四個新守衛都真的會抓。** `test_package_init_stays_empty[unicodeScripts]` 比對 `read_bytes() == b""`（`tests/test_runtime_import_guard.py:60`）：`__init__.py` 寫一行 `from . import lookup` 或只有一個換行都紅（M1、M2）。`test_the_pipeline_does_not_import_language_detection`（`tests/test_pipeline_structure.py:39-50`）把 `from` 的點分路徑和 imported names 一起看：`from ..languageDetection.scripts import get_script`、`from .. import languageDetection`、`import synthDrivers.WorldVoice.languageDetection` 三種寫法都紅（M3–M5；M5 同時被 `numbers.py` 的兩個既有守衛抓到）。`test_without_script_data_the_tool_reads_the_committed_one`（`tests/test_generate_unspaced_common.py:96-99`）：把 `SCRIPT_DATA` 改回舊路徑就紅（M6）。`test_pipeline_package_keeps_only_stages_logging_and_registry[recorder]`：`recorder.py` 加 `import os` 紅（M7）；對照組 M12 把 `"recorder"` 從名單拿掉再加 `import os`，16 個測試全綠——這正是階段 38 M2 說的漏洞。
- **測試：斷言沒有變。** 對 38 個被動到的測試檔（4 個改名）比對 `assert`／`pytest.raises` 行（排序後逐行比對）：31 個完全相同；差異只有改名帶出的（`assembly.timed` → `bringup.timed`、`legacy.speechcommand` → `legacy.speech_commands`、`rt.settings.*` → `rt.voice_settings.*` 共 7 行）和 3 行新增（新守衛的 3 個 `assert`），沒有任何既有斷言被刪或改語意。`tests/test_plugin_voice_contract.py` 零變動。helper 的簽章沒變：`load_voice_panel(monkeypatch, *, conf=None)`、`load_ui_controls(monkeypatch, *, conf=None)`、`load_settings_repository(monkeypatch, rt)`（`tests/ui_harness.py:704`、`:815`、`tests/runtime_harness.py:193`），docstring 本來就寫的是新模組名。
- **Review Focus 逐項**：見下節。**§8**：8 個 commit 都是英文 `<type>: <summary>` 加內文、0 個 `Co-Authored-By`；沒有碰 `driver/<Engine>/driver/`、`driver/sonic/`、Neural（`git ls-files WV/driver/Neural` 空）；`git diff --check e54d804 0b1857a` 乾淨；`prek run --all-files` 8 個 hook 全數 Passed 且沒改檔；全套件 **3240 passed、0 skipped**（基準 3236，+4 = 4 個新守衛，與 spec §5.5 相同）。`pyproject.toml:45-58` mutmut `source_paths` 沒有任何一條指到搬動的檔案（`settingsRepository.py`、`mainLocalePolicy.py` 只改 import 行），`per-file-ignores`（`:144-158`）亦然。
- **執行緒與鎖：** 本階段沒有碰任何鎖、callback 或執行緒程式碼。

## Critical

無。

## Important

無。

## Minor

### M1. pipeline harness 的 reload 名單還留著 `synthDrivers.WorldVoice.languageDetection`

- 位置：`tests/pipeline_harness.py:107`；對照 `:108`（`unicodeScripts.lookup`）、`:125`（`unicodeScripts.unspaced_common_data`）。
- 現象：這份名單是「載入 pipeline 會 import 到、所以每次要先 pop 的模組」。master 時 `unspaced.py` 經 `..languageDetection.scripts` 會把真的 `languageDetection/__init__.py`（含 `speech.commands`、`..locales`、`..speechCommands`）載進來，所以要 pop；本階段之後 pipeline 不再碰 `languageDetection`（上面的 import 圖與新守衛），這一行成了死項：pop 一個從來不會被這個 harness 放進去的名字。無害（`pop(name, None)`），但名單的意思是「pipeline 的 import 閉包」，留著會讓下一位讀者以為 pipeline 仍依賴偵測套件。Ruling 6 說名單「一對一對應舊名」，確實如此；只是 `languageDetection` 這一項在舊名單裡是因為 `scripts` 而存在的。
- 失敗情境：沒有（純可讀性）。
- 建議：下個測試衛生階段把 `:107` 刪掉（只動 `tests/`，`HEAD:tests` 會變，依 §4.5 補「## 修正」）。和階段 38 M1（harness 以裸 `sys.modules.pop` 清理）一起處理即可，不在本階段修。

### M2. merge 後要更新的文件與設定（都在分支外）

- 位置：`/workspace/WorldVoice/DEVELOPMENT_WORKFLOW.md:275`（§7 受保護路徑指令仍列 `languageDetection/script_data.py`、`pipeline/unspaced_common_data.py`）、`:294`（§8 產生檔規則的兩個路徑）；auto-memory `generated-unicode-data.md:11`（兩個舊路徑）；`storage/refactor8.md` §6「階段 39」尚未記 merge 狀態（§0 的 `:13`、§2.10 的 `:270-271` 是歷史描述，可留）。
- 現象：spec §6 已列出前兩者由協調者在 merge 後處理；memory 的路徑也要跟著改，否則下一個 session 會對不存在的路徑跑 §7 指令（結果是空輸出，看起來像「通過」，其實沒有保護到新路徑）。
- 建議：merge 後把 §7 指令的兩個路徑改成 `addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py`、`addon/synthDrivers/WorldVoice/unicodeScripts/unspaced_common_data.py`，§8 同步；memory 同步；`refactor8.md` §6 記 merge sha 與 3240。這一輪的 §7 檢查我用 `-M` 版本確認過（表格）。
- 順帶一提（同屬流程文件）：§4.3 的 dry run 配方「`git clone` → checkout → `prek install`」在這個容器裡第一個 commit 就會以 `Author identity unknown` 失敗，因為 `user.name`／`user.email` 只設在主 checkout 的 `.git/config`；建議在配方加一行 `git -C <clone> config user.name/user.email`（tree id 與作者無關），省得每個 dry run／重放的 agent 各自踩一次。

## 帳本 `Ruling:` 的評估

| # | Ruling | 評估 |
| --- | --- | --- |
| 1 | `engineRegistry/__init__.py` 加 docstring，指向 `driver/`（F4 方案 B 的交叉說明疊在方案 A 的改名上） | **合理。** 7 行、內容對：wrappers 在 `driver/<Engine>/` 與 WorldVoice-workspace、`discovery.py` 找並載入、不能併進 `driver/` 的理由（import 時掃磁碟、`addonHandler.initTranslation()`，`:21`）正是路線圖 §2.4「不可行」段落的原因。成本如帳本所說只是一個 docstring；它讓 `engine/__init__.py => engineRegistry/__init__.py` 從 100% 變 80% rename，但這不是產生檔，沒有 100% 的要求。 |
| 2 | `unicodeScripts/lookup.py` 加一行 docstring（原檔沒有） | **合理。** 「The Unicode Script of a code point, looked up in the generated script_data.py」與函式內容相符；78% rename 是因為檔案只有 14 行。 |
| 3 | 測試命名空間把模組叫 `voice_settings`（`rt.voice_settings`、`modules.voice_settings`） | **合理。** `tests/runtime_harness.py`、`tests/conftest.py` 的 runtime 屬性本來就是 snake_case（`playback_work`），和 `rt.settings` 相比也不再和 `pipeline.settings`、`detection_settings` 混淆；40 多行測試改動全是機械替換（斷言比對證實）。 |
| 4 | 改名的測試檔：`test_assembly`→`test_bringup`、`test_language_scripts`→`test_unicode_scripts`、`test_pipeline_controls`→`test_ui_controls`、`test_voice_config_repository`→`test_voice_settings_repository`；保留 `test_speech_dictionary`、`test_runtime_settings_store`、`test_nvda_event_bridge*`、alias 套件標籤、`_config_repository` | **合理。** 保留的都還描述受測對象（`VoiceSettingsStore`、`NvdaEventBridge`、測試檔用 snake_case），改掉的四個原名指的是已不存在的檔案。alias 標籤 `language_scripts_test_worldvoice` → `unicode_scripts_test_worldvoice` 隨檔案改，其餘標籤只在各自檔內出現，不改是對的。 |
| 5 | 兩個額外守衛（pipeline 不 import `languageDetection`；unspaced 產生器的 `SCRIPT_DATA` 預設是搬過去的檔） | **合理，而且兩個都實測有效（M3–M6）。** 前者釘住 F10 的目的（pipeline 只為 Unicode 資料依賴另一個套件），後者釘住 `tools/generate_unspaced_common.py:43` 這個唯一會悄悄失效的路徑字串（它不是 import，ruff 抓不到）。成本 +2 個測試，3240 而非 3238。 |
| 6 | `pipeline_harness` 的 reload 名單一對一改舊名，不加 `unicodeScripts` 套件或 `script_data` | **可接受。** `script_data` 在 master 也沒被 reload（只 reload `scripts`），行為確實相同；`unicodeScripts/__init__.py` 是空的，留在 `sys.modules` 的套件物件只有 `__path__`，不會帶著舊 stub。M10 證實少了 `unicodeScripts.lookup` 這一項時 `test_pipeline_harness_loads_the_script_lookup_fresh` 會紅，所以名單裡真正需要的那一項有守衛。唯一的副作用是 M1 的死項。 |

## plan 的 Review Focus 逐項

1. **套件改名後的引擎探索**：`engineRegistry/__init__.py:23`、`:27` 與 master 逐字相同；`tests/test_engine_registry.py:55-61` 釘住 `module_name`，M8（`__package__` 不 rsplit）、M9（`PACKAGE_ROOT` 少一層：`ENGINE_SPECS` 內建引擎變空集合）都紅；`tests/test_settings_panels.py`（真對話框列引擎）在全套件綠。重放 Task 1 的 red 是 `FileNotFoundError`（對話框 harness 以路徑載 `engineRegistry/discovery.py`）與 `ModuleNotFoundError`，green 174／3236。
2. **全域外掛從新路徑 import**：`speechSettingsDialog.py:14`（`engineRegistry`）、`rolePresenter.py:5`（`runtime.voiceSettings`）兩行 diff；`tests/test_settings_panels.py`、`test_pipeline_panels.py`、`test_role_panel.py`、`test_unicode_panel.py`（Task 1 的 174 passed 包含）與 `tests/test_role_presenter.py`（Task 4 的 132 passed 包含）綠。
3. **產生檔一位元組不改、仍是產生器輸出**：見結論第三點（R100、sha256 相同、產生器重跑 `cmp` 相同、`test_generated_unicode_data.py` 綠、M6 守住 `SCRIPT_DATA`）。
4. **偵測與空格停頓的 script 查表**：`languageDetection/__init__.py:6` 與 `pipeline/unspaced.py:10` 都走 `..unicodeScripts.lookup`；import 圖證實 pipeline 不再載偵測器；`tests/test_language_detector.py`、`test_unicode_scripts.py`、`test_pipeline_unspaced_space.py`（含改名的 `test_pipeline_harness_loads_the_script_lookup_fresh`，M10 證實有效）、`test_the_pipeline_does_not_import_language_detection`（M3–M5）全綠；M11 把 `lookup.py` 改成從 `..languageDetection.script_data` 拿資料，`test_unicode_scripts.py` 98 個全部 `ModuleNotFoundError: No module named 'speech'`——證明 `unicodeScripts/` 今天真的不碰 NVDA。
5. **Bring-up 與 speech dictionary 繞道**：`bringup.py` 100% rename；`speechDictionary.py` 只改 `:7` 的 import；`registry.py:20`、`:178`、`:188` 三行；`tests/test_bringup.py`（12 個 `Edit:` 全是 `assembly`→`bringup` 的名稱替換，斷言比對只差 `bringup.timed` 一行）、`test_worldvoice_lifecycle.py`、`test_runtime_composition.py`（真 `__init__.py`）、`test_speech_dictionary.py`、`test_pipeline_stages.py::test_register_puts_stages_first_in_order_and_unregister_removes_them` 綠（Task 2 的 167、Task 3 的 69）。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| `master` 位置 | `git -C /workspace/WorldVoice log master -1` | 仍是 `e54d804`，等於 plan 基準；不需 rebase 驗證 |
| 全套件（分支 `0b1857a` 的 scratch clone） | `python3 -m pytest -q -p no:cacheprovider tests`（看門狗外層） | **3240 passed**，0 skipped，98 s |
| prek | `prek run --all-files`（同一 clone） | 8 個 hook 全數 Passed；之後 `git status --short` 無輸出 |
| 空白字元 | `git diff --check e54d804 0b1857a` | 無輸出 |
| 受保護路徑（§7 原指令） | `git diff --stat e54d804 0b1857a -- 'WV/driver/*/driver/' WV/driver/sonic/ WV/languageDetection/script_data.py WV/pipeline/unspaced_common_data.py` | 只列出兩個產生檔在舊路徑被刪（1006 行、47 行）——就是授權的搬移；`driver/*/driver/`、`sonic/` 無輸出 |
| 受保護路徑（rename-aware） | 同上加 `-M` 與 `WV/unicodeScripts/` | `{languageDetection => unicodeScripts}/script_data.py | 0`、`{pipeline => unicodeScripts}/unspaced_common_data.py | 0`、`lookup.py +15`、`__init__.py 0` |
| 產生檔 R100 | `git diff -M100% --name-status e54d804 0b1857a` | 兩個 `R100`；`git cat-file -s 0b1857a:WV/unicodeScripts/__init__.py` = 0 |
| 產生檔 = 產生器輸出 | 分支的 `tools/generate_unicode_scripts.py`／`generate_unspaced_common.py`，`--unicode-version 18.0.0`，sha256 取自檔內常數，輸出到 scratch 目錄再 `cmp` | 兩個都 `identical`；sha256 `eb570540…`（script_data）、`00bd8d06…`（unspaced_common_data）與 `e54d804` 的舊路徑 blob 相同 |
| Neural | `git ls-files WV/driver/Neural` | 無輸出 |
| 外掛契約測試 | `git diff --stat e54d804 0b1857a -- tests/test_plugin_voice_contract.py` | 無輸出 |
| `runtime/settings` 閘門 | `git grep -n runtime -- 'WV/driver/*/__init__.py' WV/driver/__init__.py`；`grep -rl synthDrivers.WorldVoice ref/`（排除 `ref/nvda`） | 包裝器只 import `engineControl`、`models`、`playbackWork`、`segmentHost`、`session`；`ref/` 只有 `ref/Neural/Neural/__init__.py:2` 的 `synthDrivers.WorldVoice.driver` |
| commit 格式 | `git log e54d804..0b1857a --format=%B \| grep -ci co-authored` | 0；8 個 commit 皆英文 `<type>: <summary>` 加內文；`b54d5ce` 只動 `docs/` |
| tree id（分支） | `git rev-parse <sha>:addon <sha>:tests <sha>:tools` | 七個 commit 全部等於 plan 記的值（表格「plan 重放」第三欄） |
| **plan 重放** | pristine clone 於 `e54d804`（`ref` symlink、`prek install`、`git clean -fdx`），自寫套用器逐步套 Task 1–7 的 157 個 `Edit:`、16 個 bash 區塊、跑每個 `Run:` | 見下表 |
| 殘留舊名 | plan Task 8 的 `git grep -nE '…' -- . ':!docs'`，再加一組更寬的 grep（`assembly`、`speech_dictionary`、`languageDetection.scripts`、`scripts.py`、`script_data`、`unspaced_common_data`） | 第一組無輸出；第二組只剩 `unicodeScripts/…` 的新路徑、產生器與測試的新路徑、config 區段名 `"engine"`（設定鍵，不是模組）和 `.po` 檔的 UI 字串 |
| 字串算模組名 | `git grep -nE '__package__\|__file__\|importlib\|sys\.modules\|rsplit\(' -- addon`（排除內層驅動、sonic） | `engineRegistry/__init__.py:23`、`:27`（深度不變）、`bridge/completionPolicies.py:75`、`engineRegistry/discovery.py:104`、`pipeline/registry.py:35`、`installTasks.py`、`WV/__init__.py:64`——都不受本階段影響 |
| import 圖與週期 | AST 建 `WV/` 相對 import 圖（套件層級＋模組層級 DFS） | `pipeline → unicodeScripts`、`languageDetection → unicodeScripts`、`unicodeScripts → {}`；pipeline 不 import `languageDetection`；無環 |
| 斷言未改 | 38 個被動到的測試檔，`assert`／`pytest.raises` 行排序後逐行比對（4 個檔用改名對照） | 31 個相同；7 行只是名稱替換；3 行是新守衛的斷言；無刪除 |
| 翻譯字串 | grep `_(`／`pgettext`／`ngettext` 於搬動／新建的 10 個模組 | 無 |
| `pyproject.toml` | 讀 `[tool.mutmut] source_paths`（`:45-58`）、`per-file-ignores`（`:144-158`）、coverage omit（`:24`）、ruff exclude（`:108`） | 前兩者沒有指到搬動的檔案；後兩者改到 `unicodeScripts/script_data.py` |
| **突變探針**（scratch clone `0b1857a`，改後 `git checkout -- .` 還原） | M1 `unicodeScripts/__init__.py` 寫 `from . import lookup` | `test_package_init_stays_empty[unicodeScripts]` 紅 |
| | M2 `unicodeScripts/__init__.py` 只有一個換行 | 同上紅 |
| | M3 `unspaced.py` 改回 `from ..languageDetection.scripts import get_script` | `test_the_pipeline_does_not_import_language_detection` 紅（`unspaced.py: from ..languageDetection.scripts import get_script`） |
| | M4 `unspaced.py` 加 `from .. import languageDetection` | 同上紅（`['', 'languageDetection']`） |
| | M5 `numbers.py` 加 `import synthDrivers.WorldVoice.languageDetection` | 同上紅＋`test_number_lexing_imports_only_the_standard_library`、`…_by_its_package_path_without_nvda` 紅 |
| | M6 `tools/generate_unspaced_common.py:43` `SCRIPT_DATA` 改回 `languageDetection/script_data.py` | `test_without_script_data_the_tool_reads_the_committed_one` 紅 |
| | M7 `pipeline/recorder.py` 加 `import os` | `test_pipeline_package_keeps_only_stages_logging_and_registry[recorder]` 紅（其餘 15 綠） |
| | M8 `engineRegistry/__init__.py:27` 改成 `f"{__package__}.driver"` | `test_import_discovers_the_bundled_drivers_then_the_workspace_engines` 紅 |
| | M9 `engineRegistry/__init__.py:23` `PACKAGE_ROOT` 少一層 `dirname` | 同上紅（`{'Espeak', 'OneCore', 'RHVoice', 'SAPI5'} <= set()`） |
| | M10 `tests/pipeline_harness.py:108` 刪掉 `unicodeScripts.lookup` | `test_pipeline_harness_loads_the_script_lookup_fresh` 紅 |
| | M11 `lookup.py` 改從 `..languageDetection.script_data` import | `tests/test_unicode_scripts.py` 98 個 `ModuleNotFoundError: No module named 'speech'` |
| | M12（對照組）`STAGE_MODULES` 拿掉 `"recorder"` 再對 `recorder.py` 加 `import os` | 15 passed——沒有守衛會抓，即階段 38 M2 的缺口 |
| 看門狗 | 全程輪詢 `/proc/meminfo`，< 3 GB 即 `pkill` pytest | 沒有觸發（MemAvailable 起始約 5.0 GB） |
| 未做 | 打包、Windows／NVDA 實機、mutmut | 未做。spec §7：無邏輯變更，不需 mutmut；無行為變更。NVDA 實機上「WorldVoice 載入時找得到內建引擎、設定對話框列出引擎、speech dictionary 繞道仍生效、中日韓文字間的空格仍有停頓」是下次打包時要看的項目。 |

### plan 重放（pristine clone，從 `e54d804`）

| Commit | 套用 | Focused run（red，然後 green） | 全套件 | `HEAD:addon`／`HEAD:tests`（＝plan＝分支） |
| --- | --- | --- | --- | --- |
| Task 1 `76732b6` | 10 個 `Edit:`、`git mv engine engineRegistry` | `74 failed, 77 passed, 23 errors`，然後 `174 passed` | 3236 | `79a27102…`／`d8af32b8…` ✔ |
| Task 2 `1208cb8` | 23 個 `Edit:`、2 個 `git mv` | `83 failed, 74 passed, 11 errors`，然後 `167 passed` | 3236 | `bcaa84b7…`／`f9744cdd…` ✔ |
| Task 3 `bd68141` | 7 個 `Edit:`、`git mv` | `54 failed, 14 passed, 1 error`，然後 `69 passed` | 3236 | `b910738c…`／`abd56a8e…` ✔ |
| Task 4 `6cc083e` | 46 個 `Edit:`、`git mv` | `132 errors`，然後 `132 passed` | 3236 | `127b3a6e…`／`2e41077c…` ✔ |
| Task 5 `1edb858` | 29 個 `Edit:`、`mkdir`＋`: >`＋3 個 `git mv`、`git mv` 測試檔 | `21 failed, 335 passed, 23 errors`，然後 `379 passed`；兩行 `identical`、兩行 `R100` | 3239 | `d19e2d98…`／`c7e77aeb…` ✔（`HEAD:tools` `e0b77368…`、`pyproject.toml` `ffcc33ea…`、`.pre-commit-config.yaml` `7b0c8e0b…` ✔） |
| Task 6 `9e1908f` | 40 個 `Edit:`、2 個 `git mv` 測試檔 | `178 passed`（沒有 red 狀態） | 3239 | `d19e2d98…`／`4509351f…` ✔ |
| Task 7 `0b1857a` | 2 個 `Edit:` | `16 passed`；未提交的 `import os` 探針 `1 failed, 15 passed`，還原後 `git status` 只剩 ` M tests/test_pipeline_structure.py` | 3240 | `d19e2d98…`／`2d59af18…` ✔ |

157 個 `Edit:` 每一個的 Replace 文字在當下的檔案裡都恰好出現一次；七個 commit 的 prek hook 都一次通過（commit 區塊的輸出沒有任何 `Fixing`／`Failed`，commit 後 `git status --short` 都是空的）；每個 red／green 與全套件數字和 plan 檔尾的 dry run 紀錄一字不差。`git diff <重放 HEAD> 0b1857a -- addon tests tools pyproject.toml .pre-commit-config.yaml` 無輸出。

## 使用者還沒確認的使用者可見預設

- 無使用者可見的變動：沒有任何設定鍵、confspec、預設值或 UI 字串變動；安裝的 add-on 會整包替換，不會留下舊的 `engine/`、`assembly.py`、`runtime/settings.py`、`languageDetection/scripts.py`。
- 加到 add-on 模組裡的文字只有兩個 docstring（`engineRegistry/__init__.py:1-6`、`unicodeScripts/lookup.py:1`，Ruling 1、2），都和內容相符。
- 測試側的命名選擇（Ruling 3、4：`voice_settings`、四個測試檔改名、其餘保留）屬實作者判斷，我認為合理；使用者可在 merge 前推翻，成本只有 `tests/`。

## 給修正者／協調者的備註

- 沒有擋 merge 的項目；`master` 仍在基準上，可直接 `--ff-only`（本 review commit 只動 `docs/`，不影響 tree id）。
- merge 後請做 M2：`DEVELOPMENT_WORKFLOW.md` §7／§8 的兩個路徑、auto-memory `generated-unicode-data.md`、`storage/refactor8.md` §6 的階段 39 狀態；全套件基準改為 3240。
- M1 留給測試衛生階段，和階段 37 M5、階段 38 M1、M3 一起處理。
- 我的 scratch clone（`p39-review/replay`、`p39-review/probe`）、套用器、探針腳本、再產生的輸出與 log 審完已刪除。
