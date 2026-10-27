# Phase 47d Review：儲存識別字改成 NVDA camelCase

日期：2026-10-27。分支：`phase47d-stored-ids`（`f1f61bf..2e138a7`，11 個 commit；基準 `master` `f1f61bf`）。
審閱者：Fable 5.1（唯讀；只新增本檔）。流程：一般流程加 §3.2「改名與搬移的證明」（DEVELOPMENT_WORKFLOW.md §3.3）。9 個 task 少於 10，沒有批次 review，本次是第一次也是唯一一次 review，看整個分支。

依據：

- 規則來源 `storage/refactor9.md` §6.1 規則 3（使用者 2026-10-27 推翻）、§6 的 P47d 列。
- spec `docs/superpowers/specs/2026-10-27-phase47d-stored-ids-design.md`。
- plan `docs/superpowers/plans/2026-10-27-phase47d-stored-ids.md`。
- 進度帳本 `.superpowers/sdd/2026-10-27-phase47d-stored-ids/progress.md`（git 忽略）。
- 守門測試 `tests/test_naming_layers.py`、`tests/test_settings_table_guard.py`；設定 stub `tests/nvda_stubs.py`。
- NVDA 原始碼 `ref/nvda/source/`：`autoSettingsUtils/autoSettings.py`、`gui/settingsDialogs.py`、`synthSettingsRing.py`、`inputCore.py`、`scriptHandler.py`、`config/configSpec.py`。

使用者與協調者已決定、本次只核對實作的事項：nvda.ini `[WorldVoice]` 的鍵、WorldVoice 自己的 driver setting id、gestures.ini 的 `script_` 名稱全部改成 NVDA camelCase；不寫 migration、不加 changelog；`WorldVoice` 段落與 synth 名稱不變；使用者的設定重設是可接受的。**實作全部符合**，核對細節見「審閱者自行驗證的項目」。

## 結論

**Ready to merge：Yes。** Critical 0、Important 0、Minor 3。

- 6 個改名 commit 全部是純改名。用審閱者自己寫的檢查（`scratchpad/review47d/indep.py`：不讀任何 `OLD=NEW` 清單，從兩版 token 流（去掉 NL 與註解）逐位置比對**推導**出配對，字串與註解只允許整字替換，再與審閱者自己依 spec §2.1 抄下的允許配對表比對；t5／t6 先把群組列出的 EDITS 套到父版本，剩下的差異必須是純改名；守門檔只能刪行）逐一重跑：每個 commit 推導出的配對都在 spec 的表內，改名 token 數和實作者的 `check.py` 完全一致（25／44／103／4／122／52），沒有任何檔案的 token 流長度不同（ruff 沒有重排任何一行），沒有任何註解在整字替換之外改變。唯一的「額外配對」是 t5 把測試裡一個否定斷言的假鍵 `pair_wait_factor` 改成 `pairWaitFactor`（見 M1），不影響任何行為。
- 每個改名後的鍵，讀寫走同一個名字：pipeline 段落由 `PIPELINE_CONFSPEC`（`spec.stored_key`）、`ConfigPipelineRepository.load`／`save`（`read_stored(section, spec.stored_key, …)`／`section[PIPELINE_SETTING_BY_KEY[key].stored_key]`）三處共用同一個 `stored_key_for`；log 段落由 `LOG_SWITCHES`（confspec 與 Log Record 面板的鍵）和 `Stage.__post_init__`／`_run_logged` 的 fallback 各自經 `stored_key_for` 推導，`tests/test_pipeline_stages.py:44,103` 把真實的 `LOG_SWITCHES` 釘在 `LOG_SWITCH_ORDER` 與 stub 的 confspec 上；detection 的 `_TIMING_KEY`／`DETECTION_CONFSPEC`／`DetectionScript.config_key` 同一個字串；三個主語系旗標各自只有一個 `_KEY`，讀寫同一個；gesture 只剩 `script_popupSpeechSettingsDialog`／`script_switchLogRecord`。`addon/` 內沒有任何地方再以舊名讀 `["autoLanguageSwitching"]`／`["pipeline"]`／`["log"]`（只剩 `panels/detection.py:50-101` 的 `self._DetectLanguageTiming*` 屬性，不是儲存鍵）。
- NVDA 依 id 拼法查找的地方都核對過真實原始碼：`<id>Slider`／`<id>Checkbox`／`<id>List`（`gui/settingsDialogs.py:1443,1496,1526`）與 `ui/panelLayout.driverAttribute` 一致；`available{id.capitalize()}s`（`:1484`、`synthSettingsRing.py:76`）只影響 choice 設定，而 choice 的 id `numlan`／`nummod` 不變，`_get_availableNumlans`／`_get_availableNummods` 仍對得上；`getattr(synth, setting.id)`（`autoSettings.py:160,201`、`synthSettingsRing.py:61-65`）走 `_PipelineSetting` descriptor，`__init__.py:528-530` 以 `spec.driver_id` 安裝；`useConfig=False` 的 id 不進 `[speech][WorldVoice]`（`autoSettings.py:136,160,201`），所以 NVDA 那一段沒有任何鍵改名；`helpId` 的大寫邏輯（`settingsDialogs.py:1670-1682`）只對 NVDA 標準設定生效；gestures.ini 的綁定走 `getattr(cls, "script_%s" % name)`（`inputCore.py:879`、`scriptHandler.py:73`），舊綁定只會 debug warning 後略過。
- 舊鍵成孤兒而不壞事：用 `python3 -I` 重跑實作者的 configobj 5.0.9 驗證，`number_mode`／`global_wait_factor`／`DetectLanguageTiming` 對只列新鍵的 spec `validate: True errors: []`，舊鍵列在 `extra_values`，`write()` 原樣保留。Task 7 的五個測試釘住「只讀新鍵、不動舊鍵」，突變 m7／m8／m9／m10 證明它們各自抓得到讀回舊鍵。
- 測試基礎設施補強合理：`worldvoice_conf` 對 confspec 沒有的鍵（資料段落除外）丟 `KeyError`（`3fc1c24`），所以任何 fixture 若還餵 snake_case 的 pipeline／log／autoLanguageSwitching 鍵會直接炸，不會靜默變成預設值；stub 的 pipeline 與 log 預設用 `load_definitions` 執行真實的 `stored_key_for`，`test_config_stub.py` 再和真實 `PIPELINE_CONFSPEC` 交叉比對（突變 m1／m14 各抓到）。
- 守門終態正確：`TRANSITIONAL_47D` 與 `test_only_stored_identifiers_wait` 在 `addon/`／`tests/` 都不存在；docstring 規則 3 改寫、第 36 行「No list waits」；新的 `test_stored_identifiers_use_nvda_camel_case` 收集 fresh profile 的每個段落與鍵、六個 voice 參數鍵、`allSupportedSettings` 的 18 個 id、宿主層兩個 `script_` 名稱，突變 m7b／m11／m12／m13 各由守門抓到；`check_stored_names` 的三個 BROKEN 案例都真的失敗（m3／m11）。
- 完整測試 3336 passed、0 skipped（基準 3318 + 18：+5 推導、+1 stub 安全網、+5 舊鍵、+4 表守門、+4 命名守門、−1 刪除的 `test_only_stored_identifiers_wait`）；`prek run --all-files` 8 個 hook 全部 Passed；`git diff --check f1f61bf` 乾淨；受保護路徑無 diff、Neural 未被 track；11 個 commit 沒有 `Co-Authored-By`，沒有任何 commit 碰到 `ref`；readme（六份）、七份 `.po`、`buildVars.py` 沒有任何舊名。

## Critical

無。

## Important

無。

## Minor

### M1. `pairWaitFactor` 的否定斷言是空的

- 位置：`tests/test_pipeline_settings_service.py:228`（`assert "pairWaitFactor" not in module.PIPELINE_CONFSPEC`）。
- 內容：`pair_wait_factor` 從來不是表的項目，改名前這一行就已經恆真；t5 把它一起改成 camelCase（審閱者的推導配對裡唯一不在 spec §2.1 的一組）。同檔 `:614-626` 的 `test_repository_reads_and_writes_stored_keys` 已經把 `list(PIPELINE_CONFSPEC)` 釘成剛好 12 個 stored key，這一行沒有任何額外保護。
- 失敗情境：無（純測試可讀性）。
- 建議：刪掉這一行，或改成 `assert set(module.PIPELINE_CONFSPEC) == {spec.stored_key for spec in module.PIPELINE_STORED_SETTINGS}`。可不修。

### M2. 帳本 t2 的註記「每個改名項目的 `driverAttribute` 都等於 `voiceAttribute`」對 `sayall_wait_factor` 不成立

- 位置：帳本 Task 2 group t2 的 Note；程式 `addon/synthDrivers/WorldVoice/ui/panelLayout.py:121-129` 與 `pipeline/settings.py:71-83`。
- 內容：`voiceAttribute` 用 `str.capitalize()` 且沒有 `STORED_WORDS`，對 `sayall_wait_factor` 得到 `sayallWaitFactorSlider`；`driverAttribute` 用 driver id 得到 `sayAllWaitFactorSlider`。程式碼裡於是有兩套 snake→camel 的推導（`voiceAttribute` 給 WorldVoice 自己的 Voice 面板控制項，`stored_key_for` 給儲存鍵與 driver id）。
- 失敗情境：目前沒有。一個表項目只會有 driver id **或** WorldVoice 自己的控制項（`ui/voicePanel.py:91` `_voiceControl`），`check_attribute_names` 只比對無 driver id 的項目，所以兩套推導不會撞名；`voiceAttribute` 的結果也不是儲存識別字，不受規則 3 管。只是帳本的說法不準，將來若有人依它假設兩者相等，會在 `sayall` 這一項踩到。
- 建議：把帳本那一句改成「除了 `sayall_wait_factor`（`voiceAttribute` 不經 `STORED_WORDS`）之外相等」；不建議讓 `panelLayout` import `pipeline.settings`（它刻意不 import 任何 add-on 模組）。可不修。

### M3. plan Review Focus 5 說 `tests/test_global_plugin_menu.py` 保住「依名稱綁定 gesture」，實際上只直接呼叫方法

- 位置：`tests/test_global_plugin_menu.py:77,96`（`env.plugin.script_popupSpeechSettingsDialog(None)`、`env.plugin.script_switchLogRecord(None)`）。
- 內容：這兩個測試證明方法存在且能跑，沒有走 NVDA 的 `getattr(cls, "script_%s" % name)`。名稱拼法由 `test_naming_layers.py` 的 `_stored_identifiers`（AST 收集 `script_` 方法）守住，所以結果仍然正確；只是 plan 的描述比測試實際涵蓋的多。
- 失敗情境：無（`inputCore.py:879` 與 `scriptHandler.py:73` 的查找就是 `script_` 加名稱，守門已經釘住名稱）。
- 建議：不用加測試；下次 plan 寫 Review Focus 時描述成「命名守門釘住 `script_` 名稱，面板測試直接呼叫」即可。可不修。

## 審閱者自行驗證的項目

所有測試都在任務 worktree `/workspace/WorldVoice-phase47d`（`ref` 為 symlink）或審閱者自己建的 detached 暫時 worktree（`scratchpad/review47d/mut`，另建 `ref` symlink，用完已移除）執行，序列跑，附 3 GB `MemAvailable` 看門狗（從未觸發）；沒有碰主 checkout，沒有用 `git stash`。

| 項目 | 指令 | 結果 |
| --- | --- | --- |
| 完整測試（分支頭 `2e138a7`） | `scratchpad/review47d/suite.sh /workspace/WorldVoice-phase47d …`（`python3 -m pytest -q -p no:cacheprovider tests`，序列，看門狗） | 3336 passed、0 skipped（99.94 s）；看門狗 0 次觸發 |
| hook | `prek run --all-files`（worktree） | 8 個 hook 全部 Passed，未修改檔案 |
| 空白與受保護路徑 | `git diff --check f1f61bf`；`git diff --stat f1f61bf -- '…/driver/*/driver/' …/sonic/ …/script_data.py …/unspaced_common_data.py`；`git ls-files …/driver/Neural` | 三者皆無輸出 |
| commit 衛生 | `git log f1f61bf..HEAD --format='%b' \| grep -ic co-authored`；`git log f1f61bf..HEAD --name-only \| grep ^ref`；`git status --short` | 0；無；乾淨 |
| 獨立改名證明 | `python3 scratchpad/review47d/indep.py --verbose` → `indep_results.txt` | 見下表；每個 commit 推導出的配對都在允許表內、token 流長度一致、註解只做整字替換 |
| 改名 commit 以外的變更 | `git show 3fc1c24 c558b51 185aac2 2e138a7`（逐一讀） | `3fc1c24` 只動 `nvda_stubs.worldvoice_conf` 與一個測試；`c558b51` 只加 `STORED_WORDS`／`stored_key_for`／`stored_key` 與 5 個測試；`185aac2` 只加 5 個測試；`2e138a7` 只動兩個守門檔。改名與其他修改沒有混在同一個 commit（t5／t6 的程式修改是列出的 EDITS） |
| 審閱者多算的「保留」舊名 | `indep.py` 對群組內每個檔案數**所有**舊名（實作者的 `check.py` 只數該檔案有規則的舊名） | 多出的每一筆都逐行看過：`PipelineSettings(**{...})`／`replace`／`update` 的關鍵字、`settings.<field>` 屬性、stage 函式名（`item_wait_factor(...)`）、`PIPELINE_SETTING_BY_KEY[...]`、`STORED_KEYS` 的 field 側、`stage.log_key == "punctuation_wait_factor"`、`SpeechContext(number_language=...)`；沒有一筆是段落鍵 |
| 測試 fixture 還有沒有 snake_case 段落鍵 | `grep -n -E '"(pipeline\|log\|autoLanguageSwitching)": \{' tests/*.py` 加逐一讀 | 手寫的段落字典只有 8 處，除 Task 7 刻意的舊鍵測試（`test_pipeline_settings_service.py:629`）外全是新鍵；其餘 fixture 走 `worldvoice_conf`，而它對 off-spec 鍵丟 `KeyError`（突變 m14 證明 stub 的鍵也被交叉比對） |
| 舊名殘留 | `git grep -n -i -E '<13 個舊名>' HEAD -- addon ':!…/driver/*/driver'`；`grep -r -n -i -w … readme.md addon/doc addon/locale buildVars.py`；`git grep -n TRANSITIONAL HEAD -- . ':!docs'` | `addon/` 只剩 `panels/detection.py:50-101` 的 `_DetectLanguageTiming*` 屬性（不是儲存鍵）；文件、`.po`、`buildVars.py` 0 筆；`TRANSITIONAL` 0 筆 |
| 讀寫同名（程式碼） | `git grep -n -E '\["autoLanguageSwitching"\]\|\["log"\]\|\["pipeline"\]\|LOG_SWITCHES\|_TIMING_KEY\|config_key\|driver_id\|driverAttribute\|available\{' HEAD -- addon` 加逐一讀 | 讀者與寫者如「結論」第 2、3 點所列，沒有以舊名讀取而靜默退回預設的路徑 |
| NVDA 原始碼核對 | 讀 `ref/nvda/source/autoSettingsUtils/autoSettings.py:128-215`、`gui/settingsDialogs.py:1443-1526,1670-1682`、`synthSettingsRing.py:60-95`、`inputCore.py:870-890`、`scriptHandler.py:65-85`、`config/configSpec.py:53` | 見「結論」第 3 點；`sayAll` 的拼法確為 NVDA 自己的（`sayAllReadingUnit`） |
| configobj 孤兒鍵 | `python3 -I scratchpad/p47d/orphan_check.py scratchpad/p47d/cobj/ex`（configobj 5.0.9） | `validate: True errors: []`，`extra: ['number_mode', 'global_wait_factor']`，`write()` 保留舊行 |
| 突變測試（15 次，暫時 worktree） | `python3 scratchpad/review47d/mutate.py` → `mutate_results.txt` | 見下表；全部抓到，worktree 每次還原後 `git status` 乾淨 |

### 獨立改名證明

| commit | 配對（推導出的） | 檔案 | 改名 token | EDITS | 問題 |
| --- | --- | --- | --- | --- | --- |
| `4acab01` t1a | `DetectLanguageTiming→detectLanguageTiming`（10）、`CJKCharactersLanguage→cjkCharactersLanguage`（15） | 8 | 25 | — | 0 |
| `652104e` t1b | 三個 `KeepMainLocale*Consistent`（10／18／14）、docstring 的 `KeepMainLocale→keepMainLocale`（2） | 13 | 44 | — | 0 |
| `b87ffcf` t2 | 8 個 driver id 加 4 個 `<id>Slider`／`<id>Checkbox` | 7 | 103 | — | 0 |
| `fa3c21a` t3 | 兩個 `script_` 名稱（各 2） | 2＋守門 | 4 | — | 守門只刪行：−6／+1，+1 是 ruff 把空字典收成一行 `TRANSITIONAL_47D: dict[str, set[str]] = {}` |
| `7bdad31` t5 | 11 個 pipeline 鍵（spec §2.1 的表）＋ `pair_wait_factor→pairWaitFactor`（1，M1） | 10 | 122 | 4 個檔案 12 段 | 0 |
| `747b149` t6 | 8 個 log 開關＋ `number_modeCheckBox`／`speech_viewerCheckBox`（各 1） | 8 | 52 | 5 個檔案 12 段 | 0 |

### 突變測試

每次只改一處、跑目標測試檔、`git checkout` 還原並清 `__pycache__`（帳本提到的 stale `.pyc` 問題，審閱者也防了）。

| # | 還原的東西 | 抓到的測試 |
| --- | --- | --- |
| m1 | `PIPELINE_CONFSPEC` 只改回以 field key 為鍵（讀寫仍用 stored key） | `test_config_stub.py::test_pipeline_defaults_match_the_confspec_the_add_on_registers` |
| m2 | Log Record 面板 `_SETTING_NAMES` 只改回 `spec.key` | `test_pipeline_panels.py::test_log_switch_labels_are_unchanged` |
| m3 | `STORED_WORDS = {}`（`sayall` 不再變 `sayAll`） | `test_stored_key_is_nvda_camel_case_of_the_field[sayall_wait_factor-sayAllWaitFactor]`（`check_stored_names` 也會因 driver id ≠ stored key 失敗） |
| m4 | `_run_logged` 預設開關改回 `(label,)` | `test_pipeline_filters.py::test_run_logged_records_only_when_switched_on[INFO-True-True-writes2]` |
| m5 | `Stage.__post_init__` 開關改回原始鍵 | `test_pipeline_stages.py::test_number_mode_switch_logs_both_number_mode_stages` |
| m6 | `_log_switches` 不再推導（confspec 與面板 snake、stage camel） | `test_pipeline_stages.py::test_log_switches_list_each_label_once_in_stage_order`（第一次只跑面板／守門檔時沒抓到，因為面板測試把 `LOG_SWITCHES` stub 成 `LOG_SWITCH_ORDER`、守門用 stub 的 confspec；真正把真實 `LOG_SWITCHES` 釘住的是 `test_pipeline_stages.py:44,103`，加進目標後抓到） |
| m7 | `_TIMING_KEY` 改回 `DetectLanguageTiming`（confspec 不變） | `test_detection_settings.py::test_get_reads_the_six_detection_keys` |
| m7b | `DETECTION_CONFSPEC` 的 timing 鍵改回 PascalCase（讀者不變） | `test_naming_layers.py::test_stored_identifiers_use_nvda_camel_case` |
| m8 | `VoiceConsistency._KEY` 改回 PascalCase | `test_main_locale_policy.py::test_voice_consistency_follows_the_main_voice_only_when_enabled` |
| m9 | `load` 改讀 `spec.key` | `test_get_reads_defaults_and_current_profile` |
| m10 | `save` 改寫 `section[key]` | `test_update_converts_normalizes_and_writes_every_passed_key` |
| m11 | `driver_id="numberwaitfactor"` | `test_settings_table_guard.py::test_the_table_passes_every_check[check_stored_names]` |
| m12 | `script_switchLogRecord` 改回 snake_case | `test_naming_layers.py::test_naming_follows_layer` |
| m13 | confspec 的 `keepMainLocaleEngineConsistent` 改回 PascalCase（讀者不變） | `test_naming_layers.py::test_stored_identifiers_use_nvda_camel_case` |
| m14 | `nvda_stubs` 的 pipeline 預設改回以 field key 為鍵（測試基礎設施） | `test_config_stub.py::test_pipeline_defaults_match_the_confspec_the_add_on_registers` |

### Review Focus 逐項

| # | 項目 | 核對 |
| --- | --- | --- |
| 1 | pipeline 值寫在一個鍵、讀另一個鍵 | 三處共用 `stored_key_for`；m1／m9／m10 各別還原都被抓到；`test_repository_reads_and_writes_stored_keys` 釘住讀寫與 confspec 鍵序 |
| 2 | 升級後 profile 仍有舊鍵 | configobj 5.0.9 驗證（審閱者 `-I` 重跑）；五個舊鍵測試；m7／m8 證明讀回舊鍵會失敗 |
| 3 | Voice 面板依 driver id 命名的控制項 | `driverAttribute` 與 NVDA `settingsDialogs.py:1443,1526` 一致；`test_voice_settings_panel.py:192-299,373-394` 以 `punctuationPauseEnabledCheckbox` 走依賴關係；`test_worldvoice_pipeline_settings.py:96-171` 以 `synth.itemWaitFactor`／`globalWaitFactor` 走 descriptor |
| 4 | choice 設定與 `available{id.capitalize()}s` | `numlan`／`nummod` 不變，`_get_availableNumlans`／`_get_availableNummods` 存在；`check_stored_names` 的 choice 規則用 `id != id.lower()`，與 `capitalize()` 的語意一致；BROKEN「camel-case choice driver id」真的失敗 |
| 5 | Log Record 的標籤與開關 | `_SETTING_NAMES` 以 `stored_key` 為鍵，m2 抓到；`numberLanguage` 開關經 `also_logged_by` 推導，m5 抓到；gesture 見 M3 |

## Ruling 評估

| Ruling | 評估 |
| --- | --- |
| Task 5 前加 stub 安全網 `3fc1c24`（`worldvoice_conf` 對 off-spec 鍵丟 `KeyError`，資料段落除外） | 合理且重要：這是「fixture 還餵舊鍵卻靜默通過」的結構性防線（上一 phase 就漏過守門鍵）。審閱者確認資料段落（`engine`／`role`／`voices`）仍收任何鍵，`test_data_sections_hold_no_defined_keys` 釘住它們在 fresh profile 為空。代價正確：沒有測試需要 off-spec 鍵。 |
| t5 的測試檔 EDITS（`STORED_KEYS`／`STORED_DEFAULTS` 表、`RefusingSection` 預設、寫入鍵集合的比對） | 合理：以 field key 參數化又要指名段落鍵的測試無法用改名表達。審閱者把同一組 EDITS 套到父版本後，剩餘差異是純改名（122 個 token、全在 spec 表內）。 |
| ren.py 改成 EDITS 在規則之後套（`before` 不含改名 token，所以和 check.py 的 EDITS-on-REV 等價） | 合理；審閱者的檢查就是 EDITS-on-REV，結果純改名，等價性成立。 |
| t6 的 `test_pipeline_panels.py` EDITS（三個 `table` 查表改 `spec.stored_key`） | 合理且必要：否則 `test_table_labels_tell_translators_they_name_log_switches` 會對每個開關靜默略過。m2 證明標籤鍵對不上時會失敗。 |
| Task 7 數量 3329 而非 3328、Task 8 數量 3336 而非 3335 | 正確，差的 1 就是安全網測試；審閱者重跑得 3336。 |
| `INTERFACE_NAMES` 保留 `VoiceSnapshot.rateBoost` | 合理：它鏡射 NVDA 的 setting id，`test_lists_hold_only_names_that_break_the_rule` 仍需要這一行。列為未確認預設。 |
| t2 COLLISIONS：`removePunctuationCharactersCheckbox` 已出現在 `test_voice_settings_panel.py:594` | 已核對 `_voiceControl` 的「二擇一」邏輯；註記本身正確。同一段的另一句見 M2。 |
| 帳本 Task 5 Note：`test_number_language_is_ordering_only` 的 `"number_language" not in PIPELINE_CONFSPEC` 變成恆真 | 正確；`test_repository_reads_and_writes_stored_keys` 已把 confspec 鍵釘成剛好 12 個，恆真的那一行無害（與 M1 同類）。 |

## 使用者還沒確認的使用者可見預設

協調者採建議預設、使用者可在 merge 前推翻的事項（spec §3、§5、§10）：

1. **`uwv`、`numlan`、`nummod` 不改名**：它們是單一小寫 token，已符合 mixedCase；`uwv`／`numlan` 是 NVDA 存在 `[speech][WorldVoice]` 的唯二 WorldVoice id，保留它們就保住這兩個設定不被重設；`numlan`／`nummod` 是 choice，camelCase 的 choice id 會需要 `_get_availableNumbermodes` 這種 accessor（`capitalize()` 會把後面全部小寫）。審閱者同意保留；`check_stored_names` 已把「choice id 必須是單一小寫 token」寫成規則。
2. **stored key 由單一推導 `stored_key_for` 加字表 `STORED_WORDS = {"sayall": "sayAll"}` 產生**，不是每個項目各寫一個欄位。審閱者同意；參數化測試逐字釘住，m3 證明字表被動到會失敗。
3. **`VoiceSnapshot.rateBoost` 留在 `INTERFACE_NAMES`**。
4. **`addon/log/pipeline.csv` 的列與 debug 訊息仍用 snake_case 的 log key**（`number_mode` 等），只有 nvda.ini 的開關鍵是 camelCase。使用者匯出的 CSV 不會變；Log Record 面板的標籤也不變。
5. **Log Record 面板的 checkbox 屬性名跟著開關變成 `<switch>CheckBox`**（`numberModeCheckBox` 等）——不是儲存的東西，只是 `BaseSettingsPanel` 用鍵名組屬性名的副作用。
6. 測試基礎設施預設：`worldvoice_conf` 從此對 confspec 沒有的鍵丟 `KeyError`（Ruling，`3fc1c24`）；之後要測「孤兒鍵」要像 Task 7 一樣手寫字典。

使用者已決定、本次不再討論但值得在回報時再提一次的使用者可見結果（spec §4）：升級後 Unicode Detection 的 CJK 語言與偵測時機、三個「keep main locale … consistent」、Speech Pipeline 除 effect scope 外的每個設定（含 settings ring 的 number mode）、Log Record 的各階段開關、兩個 gesture 的自訂綁定，都會回到預設；不寫 migration、不加 changelog。

## 未在 Linux 驗證的項目

- NVDA 本身、實際音訊裝置、引擎 SDK 都沒有載入。要在 Windows 手動確認（spec §8 最後一點）：在仍有舊鍵的 profile 上升級，NVDA 啟動不出現 config 錯誤；被重設的設定顯示預設值且能儲存；nvda.ini 保留舊行；兩個 gesture 可在 Input Gestures 的 WorldVoice 類別重新綁定；settings ring 的 number mode 與各 wait factor 仍可切換。本 phase 未打包。

## 修正記錄

- **M1 不修**：`assert "pairWaitFactor" not in PIPELINE_CONFSPEC` 雖然已被逐一列出 12 個鍵的測試涵蓋，但它在這個測試裡說明「group 只加 size、不加 wait」的意圖，保留無害；master 上原本的 `pair_wait_factor` 斷言只是跟著改名。
- **M2 已修**：進度帳本（未追蹤）的 t2 註記改為「除 `sayall_wait_factor` 外」，並寫出原因。
- **M3 不修**：plan 是實作時的紀錄，不回頭改寫；正確的覆蓋說明已寫在本 review 的 M3。
