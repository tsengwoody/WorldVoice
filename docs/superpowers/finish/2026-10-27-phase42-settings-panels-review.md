# Phase 42 Review 紀錄：設定對話框拆成 panels/

日期：2026-10-27。分支：`phase42-settings-panels`（`a7bd115..654ef07`，5 個 commit）。流程：複雜流程（DEVELOPMENT_WORKFLOW.md §4）。
依據：

- 規格 `docs/superpowers/specs/2026-10-27-phase42-settings-panels-design.md`
- 計畫 `docs/superpowers/plans/2026-10-27-phase42-settings-panels.md`
- 進度帳本 `.superpowers/sdd/2026-10-27-phase42-settings-panels/progress.md`（未追蹤）
- 來源：`storage/refactor9.md` §4.1 F2（含 2026-10-27 修訂）、§5.2、§6 列 P42、§6.1

審閱者：Fable 5.1，唯讀；只 commit 本檔。基準 `master` `a7bd115`：3260 passed、0 skipped。

## 結論

**Ready to merge：Yes。** Critical 0、Important 0、Minor 2（都不擋 merge，可留到之後）。

- 拆分是逐位元組的純搬移：舊檔每一個非 import 的非空白行都原封不動、依原順序落到七個新模組之一，新增的只有模組 docstring、import 與 `addonHandler.initTranslation()`（審閱者自寫的順序敏感檢查，見下表）。
- 在 scratch clone 從 `a7bd115` 重放 plan 的 14 個步驟，每個 commit 的 `HEAD:addon`／`HEAD:tests` tree id 都和 plan 與分支相同（見「重放結果」）。
- 使用者可見的行為只有一處改變，而且是使用者選定的 (a)：`guard_errors` 顯示的錯誤對話框從此套用外掛的翻譯；英文字串、標題、樣式不變。其餘 panel 清單與順序、`isValid`／`onSave`／`onDiscard`、「不是 WorldVoice」唯讀提示、選單開啟對話框都和 `master` 相同。

## Critical

無。

## Important

無。

## Minor

### M1 plan 的純搬移檢查對順序不敏感

- 位置：`docs/superpowers/plans/2026-10-27-phase42-settings-panels.md:1023-1029`（`check_move.py` 用 `Counter` 比對非空白行的多重集合）。
- 失敗情境：若 split script 把某個定義搬錯模組、或在模組內調換兩個定義的順序，`Counter` 的差集仍是空的，Step 6 照樣印出 `pure move: OK`；spec §2 goal 1 的「in its original order」沒有被這個檢查證明。這次實際結果沒有問題（審閱者另寫了順序敏感的檢查，見驗證表），只是 plan 自帶的證據比它宣稱的弱。
- 建議：之後同類 plan 的檢查改成「每個新模組的非 header 區塊必須是舊檔的連續片段，且在同一模組內的舊檔位置遞增；所有片段恰好覆蓋舊檔一次」。審閱者的 `strict_move.py` 可以直接沿用（在 scratchpad，未 commit）。

### M2 `DIALOG_FILES` 的 glob 空掉時 `dialog_msgids()` 會變成空集合

- 位置：`tests/test_pipeline_panels.py:12`、`:197-209`、`:226`。
- 失敗情境：`DIALOG_FILES` 用 `(PLUGIN / "panels").glob("*.py")` 收集 panel 模組；若 `panels/` 被改名或搬走，glob 靜默回傳空值，`test_log_labels_come_from_the_table` 的 `dialog_msgids() & strings == set()` 會空洞通過。目前其他測試（loader、`test_panels_package_init_stays_empty`）會先失敗，所以不會漏掉，但這個斷言本身沒有自我保護。
- 建議：改用 `ui_harness.PANEL_MODULES` 組出固定的七個路徑，或在模組頂端加 `assert len(DIALOG_FILES) == 8`。

## 對決定與 Ruling 的評估

| 項目 | 評估 |
| --- | --- |
| **使用者決定 (a)**：`reportError` 共用於 `utils.py`，`utils.py` 呼叫 `initTranslation()` | 同意，而且確認這是**唯一**的使用者可見變化。`utils.py:8` 新增 `initTranslation()`；`reportError`（`utils.py:11-23`）的訊息、標題、`wx.OK | wx.ICON_ERROR` 與 `master` 的兩份副本逐字相同，`gui.messageBox` 一樣不帶 parent。兩個 msgid 在全部 7 個 catalog（ar、ru、tr、uk、zh_CN、zh_HK、zh_TW）都已有翻譯，`scons pot` 前後的 msgid 集合相同（91 個）。沒有 changelog 行，照使用者的選擇。 |
| **協調者預設**：`_as_bool` 留在 `panels/base.py:17-20`，不 import `engineRegistry.discovery` | 同意。refactor9 的修訂已經對 `coerce_bool` 存疑，`engineRegistry/` 歸屬未定（§6.1）；`grep` 確認對話框沒有任何 `engineRegistry.discovery` 的 import。**仍是使用者可改的預設**（見文末）。 |
| **Ruling**：`reportError` 放 `utils.py` 而不是 `panels/base.py` | 合理。放 `panels/base.py` 會讓裝飾器模組反向依賴 panels 套件（連帶 `SettingsPanel`、`config`、`tones`），而 `tests/ui_harness.load_utils` 以無套件方式載入 `utils.py`，相對 import 會讓 harness 要改。放錯的代價只是同套件內搬一個函式。 |
| **Ruling**：`buildVars.py:64` 加 `'addon/globalPlugins/*/*/*.py'` | 必要且正確。用 `pathlib.glob` 跑舊的五個 pattern，`panels/` 的 7 個檔一個都沒涵蓋；新 pattern 只多出這 7 個檔。`sconstruct:44-45` 的 `expandGlobs` 也是 `Path.glob`，所以 `test_every_translated_module_is_a_pot_source` 的判斷和建置一致。實際在 scratch clone 跑 `scons pot`：`WorldVoice.pot` 的 `#:` 來源含 `dialog.py`（2）、`panels/base.py`（2）、`detection.py`（9）、`engine.py`（7）、`log.py`（5）、`pipeline.py`（1）、`role.py`（13）、`utils.py`（2）。 |
| **Ruling**：每個 panel 模組各自呼叫 `addonHandler.initTranslation()` | 必要。`ref/nvda/source/addonHandler/__init__.py:964-981`：`initTranslation()` 取 `inspect.currentframe().f_back` 的模組，`setattr(module, "_", …)`，只綁定**呼叫它的那個模組**；`getCodeAddon(frameDist=2)`（`:928-948`）靠呼叫端檔案路徑判斷外掛，子套件 `panels/` 在外掛目錄內，沒有問題。沒呼叫的模組會落到 NVDA 自己 `trans.install(...)` 安裝的內建 `_`（`languageHandler.py:353`），NVDA 的 catalog 沒有這些字串，介面會變英文。測試的 `_` 是恆等函式，分不出這個差別，所以 `test_every_translated_module_installs_the_add_on_catalog` 這道守門是對的。 |
| Task 3 曾被 gate 住、等使用者回答後才落地 | 符合 §3.1「會改變使用者可見行為的重大決定，停下來問」。`de426f7` 只改 spec。 |

## plan 的 Review Focus 逐項檢查

1. **搬走的 panel 在 NVDA 顯示英文**：七個新模組都有頂層 `addonHandler.initTranslation()`；守門測試拿掉 `panels/engine.py` 或 `utils.py` 的呼叫都會失敗（突變 b、f）。
2. **panel 字串掉出翻譯範本**：拿掉新 glob，`test_every_translated_module_is_a_pot_source` 失敗（突變 d）；`scons pot` 實測見上表。
3. **測試的 patch 打不到程式**：`RolePanelPresenter`（`tests/test_role_panel_ui.py:69`）、`pipeline_log`（`tests/test_settings_panels.py:626`）、`PIPELINE_SETTINGS`（`:194`）、`pipeline_settings`（`tests/test_pipeline_panels.py:69-70`）都改 patch 到 `env.panels.<module>`。`monkeypatch.setattr` 預設 `raising=True`，若仍 patch 在 dialog 模組（沒有這些屬性）會立刻 `AttributeError`；`rolePresenter` 在 harness 是 `RolePanelPresenter=None` 的 stub，patch 失效時建 panel 會 `TypeError`。四個對應測試都斷言 patch 後的效果。
4. **非 WorldVoice 合成器**：`test_panels_for_another_synth_show_the_same_read_only_notice`（`tests/test_settings_panels.py:730`）釘住 TextCtrl 的值、四個 style 旗標、背景色、`proportion=1`、`flag=wx.EXPAND`、border 0；改 `proportion` 兩個案例都失敗（突變 n）；拿掉 role panel 的 `self.disable = True`，`test_panel_for_another_synth_only_says_so` 失敗（突變 m）；調換 dialog 類別順序，`test_dialog_offers_role_and_unicode_panels_only_for_worldvoice[True]` 失敗（突變 l）。
5. **Speech Role 存檔失敗**：`test_a_failed_save_reports_the_error_and_keeps_the_dialog_open`（`tests/test_role_panel_ui.py:270`）用真的 `utils`，斷言訊息開頭、`Details: disk full`、標題、樣式、log 行與 `ValueError`；改標題（突變 o）或拿掉 `raise ValueError`（突變 p）都失敗，`tests/test_guard_errors.py` 同時抓到標題改動。

另外：`__init__.py:21` 改 import `.dialog`；把它改回 `.speechSettingsDialog`，`tests/test_global_plugin_menu.py` 16 個測試失敗（突變 q）。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 分支 tree id | `git rev-parse 654ef07:addon 654ef07:tests` | `b62ed753…`／`76da7b1c…`，與 plan Task 3 相同 |
| **plan 重放**（§4.5） | scratchpad 全新 `git clone`，checkout `a7bd115`，symlink `ref`，`prek install`；用實作者的 `planrun.py`（先讀過：依文件順序執行每步的 bash 區塊、寫 `File:` 區塊、以「恰好出現一次」的整段取代套用 `Edit:` 區塊）跑 Task 1 Step 1–7、Task 2 Step 1–3、Task 3 Step 1–3、Task 4 | 14 個步驟全部照 plan 執行；每個 commit 後的 tree id 都和 plan 與分支相同（表見「重放結果」）；每次 red／green 的 failed／passed 數都等於 plan 寫的預期；三個 commit 的 hook 一次通過 |
| 純搬移（plan Step 6 的檢查） | `check_move.py` 的 `Counter` 法 | `5 old lines not kept, 52 lines added`、`pure move: OK`（重放中印出） |
| 純搬移（順序敏感） | 審閱者自寫 `strict_move.py`：每個新模組去掉 header 後以 `\n\n\n` 切塊，每塊必須是舊檔的連續片段、同模組內舊檔位置遞增、全部片段覆蓋舊檔每一行恰好一次 | `strict pure move: OK`；舊檔未覆蓋的 34 行全是 import／`initTranslation()` |
| `git diff --color-moved=zebra a7bd115 4cf3f98 -- addon/globalPlugins` | 以 ANSI 顏色分類加減行 | moved 1494 行；非 moved 的加行 42、減行 6，全是 `__init__.py` 的 import 改寫、七個模組的 docstring／import 與舊檔的 5 行 import |
| plan 以外的修改 | `git diff --stat a7bd115 654ef07`；`docs/` 只有 spec 與 plan 兩檔；`buildVars.py` 只加一行 | 26 個檔，全在 plan 的 Files 清單內；Task 1 stat `23 files changed, 938 insertions(+), 798 deletions(-)`、Task 2 `5 files, 48/14`、Task 3 `6 files, 54/29`，與 plan 預期相同 |
| ruff（專案設定，含 `builtins = ["_"]`） | `ruff check --no-cache addon/globalPlugins/WorldVoice`、`ruff format --check` | All checks passed；12 files already formatted（每個模組的 header import 都夠用、無未用 import） |
| 舊的 glob 真的漏掉子套件 | `pathlib.glob` 跑舊五個 pattern 與新六個 pattern | 舊：`panels/` 0 個；新：7 個；新 pattern 只多出這 7 個檔 |
| `scons pot` | scratch clone（分支 head）`scons pot`；再 checkout `a7bd115` 重跑，比對 msgid 集合與 `#.` 註解 | 兩邊都是 91 個 msgid、集合相同；`#.` 差異只有：少了舊 `utils.py` 內聯的 `# Caption` 註解，多了「Shown in place of a settings panel …」與「The title of the dialog shown when …」兩條 Translators 註解，且都正確掛在對應 msgid 上 |
| 字串存在於 catalog | `grep` 7 個 `addon/locale/*/LC_MESSAGES/nvda.po` | 「WorldVoice Setting Dialog - Error」、「An unexpected error …」、「Your current speech synthesizer is not WorldVoice.」在全部 7 個 catalog 都有 msgstr |
| 守門測試是否真的抓得到（scratch 複本逐一破壞再還原） | 見下方「突變清單」 | 17 項全部讓宣稱的測試失敗，還原後 `git status` 乾淨 |
| 守門範圍擴大 | 讀 `tests/test_ui_structure.py:40`（`._voiceManager`）、`:148`（`getSynth`）、`:83`（dependency 名稱）、`tests/test_unicode_panel.py:182`（`languageDetection` import）、`tests/test_role_guards.py:11`（`.wvd`）、`tests/test_pipeline_panels.py:12`（msgid 重疊） | 都改為 `PLUGIN.rglob("*.py")` 或全部對話框檔；突變 g、h、i、j 證實擴大後仍會失敗 |
| 命名（refactor9 §6.1） | 讀新定義 | `notWorldVoiceNotice`、`reportError`、參數 `panel`／`sizer`／`error`、區域變數 `infoCtrl` 皆 mixedCase；測試端 helper `referred_names`、`string_constants` 用測試慣例的 snake_case（spec §3） |
| commit 衛生 | `git log --format='%(trailers)'`、commit 內文 | 5 個 commit 都沒有 `Co-Authored-By`；message 為英文 `<type>: <summary>` 加說明理由；每個 commit 的檔案清單等於 plan 的 `git add` 清單 |
| 受保護路徑 | `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' …sonic/ …script_data.py …unspaced_common_data.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 兩個都無輸出 |
| `git diff --check a7bd115` | | 乾淨 |
| 舊模組名殘留 | `git grep -n speechSettingsDialog -- . ':!addon/locale' ':!docs'` | 無；`addon/locale/*/nvda.po` 的 `#:` 參照照 spec §7 留給 `scons pot` 合併時改寫 |
| 翻譯註解位置 | `tests/test_translator_comments.py:31` 的規則：`# Translators:` 下一行必須是 gettext 呼叫 | `base.py:88` 在 `value=_(` 前一行；`utils.py:14`、`:20` 在 `_(` 前一行；把 `base.py:88` 和字串拆開後該測試失敗（突變 k） |
| 完整測試（分支 worktree，單一 pytest 行程，記憶體守門 3 GB） | `$SCRATCH/runtests.sh /workspace/WorldVoice-phase42 tests` | `3268 passed in 96.53s`、0 skipped（基準 3260 + 8 個新測試：2 個翻譯守門、`panels/__init__.py` 守門、notice 守門、notice 特徵化 ×2、錯誤對話框守門、存檔失敗 UI 測試） |
| `prek run --all-files`（分支 worktree） | | 8 個 hook 全部 Passed（check python ast、case conflicts、yaml、trailing whitespace、end of files、add trailing commas、ruff lint、ruff format）；跑完 `git status --short` 無變動 |

### 突變清單（scratch 複本 `mutate-phase42`，每項套用 → 跑指定測試 → `git checkout -- .`）

| # | 破壞 | 失敗的測試 |
| --- | --- | --- |
| a | `panels/detection.py` 把提示 TextCtrl 複製回去（字串第二份） | `test_ui_structure.py::test_panels_share_the_not_worldvoice_notice` |
| b | 刪 `panels/engine.py` 的 `initTranslation()` | `test_translator_comments.py::test_every_translated_module_installs_the_add_on_catalog` |
| c | `panels/__init__.py` 加一行 import | `test_ui_structure.py::test_panels_package_init_stays_empty` |
| d | 刪 `buildVars.py` 新 glob | `test_translator_comments.py::test_every_translated_module_is_a_pot_source` |
| e1 | `panels/role.py` 的 `reportError(error)` 換回內聯 `gui.messageBox` | `test_ui_structure.py::test_settings_errors_share_one_dialog` |
| e2 | `utils.guard_errors` 的 `reportError(e)` 換回內聯 `gui.messageBox` | 同上 |
| f | 刪 `utils.py` 的 `initTranslation()` | 同 b |
| g | `panels/detection.py` 改用 `synth._voiceManager` | `test_ui_structure.py::test_ui_uses_only_public_driver_hooks` |
| h | `dialog.py` import `synthDriverHandler.getSynth` | `test_ui_structure.py::test_settings_ui_asks_for_worldvoice_not_for_the_synth` |
| i | `dialog.py` import `languageDetection.detector` | `test_unicode_panel.py::test_the_dialog_reads_the_tables_without_the_detector` |
| j | `panels/pipeline.py` 出現 `".wvd"` | `test_role_guards.py::test_error_callback_finds_its_dialog_without_a_class_registry` |
| k | `panels/base.py` 的 Translators 註解和字串之間插一行 | `test_translator_comments.py::test_translator_comments_precede_gettext_calls` |
| l | `dialog.py` 調換 Speech Role／Speech Engine 順序 | `test_settings_panels.py::test_dialog_offers_role_and_unicode_panels_only_for_worldvoice[True]` |
| m | `panels/role.py` 非 WorldVoice 分支不再 `self.disable = True` | `test_role_panel_ui.py::test_panel_for_another_synth_only_says_so` |
| n | `notWorldVoiceNotice` 的 `proportion=1` 改 0 | `test_panels_for_another_synth_show_the_same_read_only_notice` 兩個案例 |
| o | `reportError` 標題改字 | `test_role_panel_ui.py::test_a_failed_save_reports_the_error_and_keeps_the_dialog_open`、`test_guard_errors.py::test_a_failing_handler_logs_shows_the_error_and_runs_the_callback` |
| p | `panels/role.py` `onSave` 不再 `raise ValueError` | 同 o 的第一個、`test_role_panel.py::test_failed_apply_shows_error_and_raises_value_error` |
| q | `__init__.py` 改回 import `.speechSettingsDialog` | `test_global_plugin_menu.py` 16 個測試 |

## 重放結果（§4.5）

環境：`git clone -q /workspace/WorldVoice <scratchpad>/replay-phase42`，`checkout -b replay a7bd115`，`ln -s /workspace/WorldVoice/ref ref`，`prek install`；先 `git add -f` spec 與 plan 做一個 docs commit（不影響 `addon`／`tests` tree id），再由 `planrun.py` 依序跑 Task 1 Step 1–7、Task 2 Step 1–3、Task 3 Step 1–3、Task 4 Step 1，pytest 一律經 `runtests.sh`（單一行程、MemAvailable < 3 GB 即終止）。

| 步驟 | plan 預期 | 重放結果 |
| --- | --- | --- |
| T1 S1 守門測試 | `6 passed` | `6 passed` |
| T1 S2 測試改路徑（red） | `116 failed, 46 passed, 14 errors` | `116 failed, 46 passed, 14 errors` |
| T1 S3 split script + `__init__.py`（red，只剩範本守門） | `1 failed, 175 passed` | `1 failed, 175 passed`；`git status` 恰為 ` D speechSettingsDialog.py`、`?? dialog.py`、`?? panels/` |
| T1 S4 加 glob | `176 passed`；`buildVars.py` blob `89f0c1c0…` | `176 passed`；blob `89f0c1c0fbc3563b5ab71cf876706e4c024f04fb` |
| T1 S5 probe（刪 `role.py` 的 `initTranslation()`） | `At index 0 diff: 'globalPlugins/WorldVoice/panels/role.py' != 'globalPlugins/WorldVoice/utils.py'`、`1 failed, 5 passed` | 相同；還原後狀態不變 |
| T1 S6 純搬移檢查 | `5 old lines not kept, 52 lines added`、`pure move: OK` | 相同 |
| T1 S7 全套件 + commit | `3263 passed`；stat `23 files changed, 938 insertions(+), 798 deletions(-)`；`addon` `8bdac220145f2f7af3c8ad752342608295cd0161`、`tests` `f1c758abe508fd695cc9f114a7a38a7d1319a001` | 全部相同（分支 `4cf3f98` 亦同） |
| T2 S1 測試（red） | `1 failed, 76 passed` | `1 failed, 76 passed` |
| T2 S2 helper | `111 passed` | `111 passed` |
| T2 S3 全套件 + commit | `3266 passed`；`5 files changed, 48 insertions(+), 14 deletions(-)`；`addon` `db934584e8c0a5de4f42fa7f350de1adb3c7afae`、`tests` `bc002dfddc972791ed816a9a2bc32d57dfc3695c` | 全部相同（分支 `08b770d` 亦同） |
| T3 S1 測試（red） | `3 failed, 37 passed` | `3 failed, 37 passed` |
| T3 S2 `reportError` | `40 passed` | `40 passed` |
| T3 S3 全套件 + commit | `3268 passed`；`6 files changed, 54 insertions(+), 29 deletions(-)`；`addon` `b62ed75314a91f666f195771ec025f77886d128c`、`tests` `76da7b1ca08375c278df4dd9b6b67477ca5f2574` | 全部相同（= 分支 `654ef07`） |
| T4 完整驗證 | `3268 passed`；hook 全 Passed；`git diff --check`、受保護路徑、Neural、`git grep` 無輸出 | 全部相同 |

重放過程的兩個環境插曲（與 plan 無關，記下供下次參考）：第一次重放時 scratch clone 沒有 git 身分（worktree 用的是 repo 本機設定），三個 `git commit` 都失敗，但所有 `Edit:` 都已套用，當時工作樹的 `git write-tree` 已是 `addon b62ed753…`／`tests 76da7b1c…`；第二次用 `git clean -fd` 重置，留下被忽略的 `panels/__pycache__/`，split script 的 `mkdir()` 因目錄已存在而中止；第三次 `git clean -fdx` 後完整重放，結果如上表。

## 其他觀察（不列為 finding）

- `test_every_translated_module_installs_the_add_on_catalog` 只認 `addonHandler.initTranslation()` 這一種寫法；若有人改寫成 `from addonHandler import initTranslation; initTranslation()` 會被誤判為缺少。方向保守（誤報而非漏報），不需處理。
- `dialog.py:36` 保留了原本的中文行內註解 `# 這時父類別會讀取 self.categoryClasses`，是逐字搬移，不屬本 phase。
- 執行緒與鎖：本 phase 沒有任何執行緒或鎖的改動；`wx.CallAfter`（`role.py:22`、`log.py:92`）照舊。
- Linux 測試只驗證 fake wx 與 stub NVDA；Windows 上的 NVDA、實際對話框顯示與翻譯載入都沒有驗證。spec §8 的選用手動項目（開 NVDA 選單 → WorldVoice → Settings，分別在 WorldVoice 與其他合成器下確認 panel 相同）仍建議在下次打包時順手做。

## 使用者還沒確認的使用者可見預設

- `_as_bool` 留在 `panels/base.py:17-20`、不改用 `engineRegistry.discovery.coerce_bool`（協調者採建議預設）。對使用者沒有可見差異，改不改都只是一個 import。

已由使用者決定（不再列為未確認）：錯誤對話框共用並翻譯（選項 (a)）、不加 changelog 行。

## 修正記錄

| 項目 | 處理 | commit |
| --- | --- | --- |
| M2 `DIALOG_FILES` 的 glob 空掉時 `dialog_msgids()` 變成空集合 | 已修正。`tests/test_pipeline_panels.py` 的 `DIALOG_FILES` 改由 `ui_harness.PANEL_MODULES` 組出固定的 `dialog.py` 加六個 panel 模組路徑，模組不見時會 `FileNotFoundError` 而不是讀不到東西；另加 `test_dialog_msgids_come_from_the_dialog_and_every_panel`，斷言七個模組的標題 msgid 都在 `dialog_msgids()` 裡。照測試優先：先用探針把 glob 指到不存在的資料夾，`test_log_labels_come_from_the_table` 照樣通過（空洞通過）；新測試在同一個探針下失敗；改成固定清單後，把路徑指到不存在的資料夾，`test_log_labels_come_from_the_table` 本身就以 `FileNotFoundError` 失敗。plan 的「## 修正」段落（Task 5–6）在 scratch clone 從 `654ef07` 接續 dry run，tree id 吻合後才落地：`HEAD:addon` = `b62ed753…`（不變）、`HEAD:tests` = `0cbb15ea…`；完整測試 3269 passed、0 skipped。 | `4eb54af`（plan 段落：`f864cf9`） |
| M1 plan 的純搬移檢查對順序不敏感 | 不修改程式碼。`check_move.py` 是多重集合比對，本來就證明不了順序；這是 plan 自帶證據的強度問題，不是分支內容的問題。審閱者自寫的順序敏感檢查 `strict_move.py` 已確認拆分逐段、依原順序搬移（`strict pure move: OK`），結果不受影響。之後同類的拆分 plan 改用「連續片段、位置遞增、恰好覆蓋一次」的檢查。 | 無 |
