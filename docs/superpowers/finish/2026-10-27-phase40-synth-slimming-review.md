# Phase 40 Review：synth `__init__.py` 瘦身（F3-2 `confspec.py`＋F3-3 `NumberLanguageChoice`）

日期：2026-10-28。分支：`phase40-synth-slimming`（`4688473..07d82ea`，6 個 commit：2 個 docs、4 個程式；基準 `master` `4688473`，3346 passed／0 skipped）。
審閱者：Fable 5.1（唯讀；只新增本檔）。流程：一般流程（DEVELOPMENT_WORKFLOW.md §3.3）加 §3.2 的搬移證明；5 個 task 少於 10，沒有批次 review，本次是第一次也是唯一一次 review，看整個分支。

依據：

- 規則來源 `storage/refactor9.md` §4.1 F3（第 2、3 項）、§6 的 P40 列、§6.1 命名規則、§7 第 13、14 項（descriptor 與 `resolve_voices()` 已否決）。
- spec `docs/superpowers/specs/2026-10-27-phase40-synth-slimming-design.md`。
- plan `docs/superpowers/plans/2026-10-27-phase40-synth-slimming.md`（Review Focus 1–5）。
- 進度帳本 `.superpowers/sdd/2026-10-27-phase40-synth-slimming/progress.md`（git 忽略；4 個 `Ruling:`，含舊→新成員對照）。
- 實作者的搬移比對 `scratchpad/p40/move_check.py`；審閱者另外寫了自己的 token 層級比對 `scratchpad/review40/move_check_tokens.py`。
- NVDA 原始碼 `ref/nvda/source/core.py`（初始化順序）、`synthDriverHandler.py`（`setSynth`、`initSettings`、`loadSettings`、`handlePostConfigProfileSwitch`）、`globalPluginHandler.py`、`gui/settingsDialogs.py:1324,1484`（`driver` 弱參考、`available{Id}s` 查法）、`config/__init__.py:1326,1352,1464-1470`（spec 在存取時解析）。

使用者已決定、本次只核對實作的事項：F3-2 與 F3-3 都在範圍內；descriptor 與 `resolve_voices()` 不做；driver setting id、儲存鍵、警告文字、`[WorldVoice]` 各區段的鍵與預設都不變；根 `numberLanguage.py` 不動；最低 Python 3.11。**實作全部符合。**

## 結論

**Ready to merge：Yes。** Critical 0、Important 0、Minor 2。

- **行為與 master 逐項相同（F3-3 沒有搬移證明，審閱者逐行對照）。** `adfaa8f` 的 diff 和 master `__init__.py:469-509` 比對：
  - `is_storable`（舊 `_isStoredNumberLanguage`）：`value in (FOLLOW, MAIN) or value in manager.all_languages`，逐字同形（`voices/numberLanguageChoice.py:20-22`）。
  - `stored`（舊 `_get_numlan`）：每次讀都重新驗證，不可儲存時答 `FOLLOW`（`:24-28`）。
  - `store`（舊 `_set_numlan` 的驗證與指派）：可儲存就存，否則存 `FOLLOW`、回傳 `False`；driver 的 `_set_numlan` 只在 `False` 時以**同一句** `nvdaLog.debugWarning("WorldVoice: unknown number language %r, using %r", value, FOLLOW)` 記錄（`__init__.py:467-469`）。master 是「先記 log 再指派」，現在是「指派後由 driver 記 log」；只有 `debugWarning` 本身拋例外時才看得出差別，實務上沒有。
  - `spoken`（舊 `_numberLanguage`）：`stored` 不在 `(FOLLOW, MAIN)` 且沒有被提供的語音說它時答 `FOLLOW`（`:40-44`）。
  - `listed_locales`（舊 `_get_availableNumlans` 的 locale 清單）：`list(manager.languages)` 後把被隱藏的 stored locale 排最後（`:46-56`）；driver 的 `_get_availableNumlans` 仍先放 `NUMBER_LANGUAGE_CHOICES` 的兩個 follow 值，再以 `_numlanDisplayName` 做 `StringParameterInfo`（`__init__.py:454-458`），所以 NVDA 的設定環（`gui/settingsDialogs.py:1484` 以 `available{Id}s` 查）與 Voice panel 看到的 id、標籤、順序都和 master 一樣。
  - `manager` 就是 `self._voiceManager` 同一個物件（`_initialize` 的區域變數 `manager`，`__init__.py:230-235`）；`_voiceManager` 只在 `__init__`（None）、`_initialize`、`terminate` 被指派，所以 choice 不會指到舊的 manager。`languages`／`all_languages` 每次呼叫都讀（m02、m24 與 `test_the_choice_reads_the_manager_each_time` 證明），voice／engine 變動後的清單變化行為不變。
  - `LanguageDetector` 仍以 `number_language=self._numberLanguage` 建（`__init__.py:256`），profile 切換經 `loadSettings` → `_set_numlan` 後 provider 跟著變（Review Focus 5；m07、m08 抓到）。
- **F3-2 是逐字搬移。** `58956f6` 只把 dict 原樣包進 `def installConfspec(conf)`（diff 顯示 dict 本體每行只多一個 tab）並在原位呼叫；`05183ee` 的搬移通過審閱者自己的 token 層級比對（見下表）；四個 owner 名稱從 `__init__.py` 的四行 import 移除，正好是 `confspec.py` 匯入的四個，另加 `from .confspec import installConfspec`。move 與 edit 是分開的 commit；move commit 的三個測試檔只改路徑參照（`nvda_stubs.CONFSPEC_SOURCE`、`test_pipeline_panels` 的 `SYNTH→CONFSPEC`、naming guard 的 `HOST` 多一列）。
- **呼叫點留在套件 import（spec §5.1）正確，先於每個讀者。** NVDA 順序：`config.initialize()`（`core.py:720`）→ `addonHandler.initialize()`（`:763`）→ `speech.initialize()`（`:804`，WorldVoice 是設定的合成器時由 `synthDriverHandler.setSynth` → `_getSynthDriver` 匯入套件）→ `gui.initialize()`（`:847`）→ `globalPluginHandler.initialize()`（`:928`，`listPlugins` 匯入 `globalPlugins.WorldVoice`，其第一個 add-on import 是 `synthDrivers.WorldVoice.pipeline.sayAll`（`globalPlugins/WorldVoice/__init__.py:14`），先跑套件 `__init__.py:70` 的 `installConfspec(config.conf)`，再才匯入 `.dialog`、`.pipelineLog`）。add-on 內所有 `["WorldVoice"]` 的讀取（`panels/base.py:43,55,76`、`panels/engine.py:47`、`pipelineLog.py:22`、`pipeline/registry.py:91`、`pipeline/settings.py:391`、`languageDetection/settings.py:55`、`voices/mainLocalePolicy.py:11`、`voices/settingsRepository.py:31`、`voices/roles.py:56-58`、synth `__init__.py:226`）都在函式內，沒有 import 時讀取；`installTasks.py` 不讀 `[WorldVoice]`。WorldVoice 不是目前合成器時，global plugin 的三個 panel 開啟前套件已匯入，spec 已裝好——和 master 的時序完全相同（master 的指派也在同一位置、同樣在 import 之後）。NVDA 的 `AggregatedSection` 在存取時才查 `self._spec.get(key)`（`config/__init__.py:1326,1352`），所以 spec 在 `config.initialize()` 之後加入也能驗證，這點 master 已依賴。`tests/test_runtime_composition.py:633-636` 以真正的套件 import 釘住（m11 抓到）。
- **terminate 之後讀 `numlan` 的行為改變不是風險。** `VoiceManager.terminate`（`voices/manager.py:131-156`）清 `_resources`、`_instance_cache`、`task_manager`，但保留 `catalog` 與 `_default_voice_instance`，所以 `all_languages`（`:277-278`）與 `languages`（`:284-285`，經 `_visible_table` 讀 `_default_voice_instance.engine`）在 terminate 後仍答最後一份清單；`stored`／`spoken`／`listed_locales` 因此都不會拋例外，而 master 在 `_voiceManager = None` 後是 `AttributeError`。查過 NVDA 的呼叫者：`setSynth` 在 `cancel()`、`terminate()` 之後直接丟掉 `_curSynth`，不呼叫 `saveSettings`（`synthDriverHandler.py:519-527`）；`handlePostConfigProfileSwitch` 只對活著的 `_curSynth` 呼叫 `loadSettings(onlyChanged=True)`（`:600`）；設定環與 Voice panel 走 `getSynth()` 或弱參考 `_driverRef()`（`settingsDialogs.py:1324`），就算拿到已 terminate 的 driver，`saveSettings` 會先經 `supportedSettings` 讀 `self._voiceManager.get_voice_capabilities`（`__init__.py:143`）在 None 上拋 `AttributeError`，master 與分支都走不到 `numlan`。`speak()`、`cancel()`、`pause()` 以 `_terminated` 擋，`speechContext()` 在 `_voiceManager is None` 時先答 `GENERIC_CONTEXT`（`:346-349`），`_detectLanguages` 的 filter 已在 teardown 取消註冊。沒有任何呼叫者依賴舊的 `AttributeError`。唯一的副作用見 M1。
- **命名符合 `tests/test_naming_layers.py` 的 docstring。** 規則 1 以模組所屬分層決定風格：`confspec.py` 匯入 `pipeline/registry.py`（它 `import config`、`speechDictHandler`、`logHandler`，`registry.py:15-18`）與 `pipeline/settings.py`，refactor9 §6.1 的歸屬表明列「synth `__init__.py`（含新的 `confspec.py`）」為 NVDA 宿主層，§6 也寫「P40 放在命名之後，新的 `confspec.py`……直接照規則取名」，所以 `installConfspec` 用 mixedCase 正確；refactor9 F3-2 與 P40 列的 `install_confspec` 是 §6.1 之前的草稿（Ruling 2 合理）。`voices/` 是可攜核心，`NumberLanguageChoice` 的成員 `is_storable`、`stored`、`store`、`spoken`、`listed_locales`、`_manager`、`_value` 全是 snake_case，模組只匯入 `..numberLanguage`，沒有 NVDA、沒有 logger；檔名 `numberLanguageChoice.py` 與 `voices/settingsRepository.py`、`mainLocalePolicy.py` 的 camelCase 檔名慣例一致，守門測試不檢查檔名。m17、m18、m19 證明守門會抓漏列與兩個方向的風格錯誤。
- **Python 3.11 相容。** 分支 diff 沒有 `typing.override`、PEP 695、`type` 敘述、`itertools.batched`；新碼只用 `@property` 與一般類別。容器只有 3.14，無法實跑 3.11。
- **測試真的抓得到。** 25 次突變（下表）24 次被抓到，1 次存活（m06，見 M2）；plan Review Focus 1–5 逐項核對（見下）。
- 完整測試 3359 passed、0 skipped（基準 3346 + 1 `test_confspec_sections` + 10 `test_number_language_choice.py` + 2 import guard；和帳本一致）；`prek run --all-files` 8 個 hook 全部 Passed；`git diff --check master` 乾淨；受保護路徑無 diff、Neural 未被 track；6 個 commit 沒有 `Co-Authored-By`、沒碰 `ref`；沒有 readme、changelog、可翻譯字串或儲存鍵的變動（符合 spec §3）。`__init__.py` 530 → 498 行。

## Critical

無。

## Important

無。

## Minor

### M1. `NumberLanguageChoice` 讓已 terminate 的 `VoiceManager` 在 driver 物件存活期間一直可達

- 位置：`addon/synthDrivers/WorldVoice/__init__.py:276-284`（`terminate` 的 `finally` 清 `_taskManager`、`_eventBridge`、`_voiceManager`、`_indexLedger`，沒清 `_numberLanguageChoice`）；`voices/numberLanguageChoice.py:17`（`self._manager = manager`）；spec §5.2「The choice is not cleared on `terminate`: it holds no resource」。
- 內容：master 在 terminate 後對 manager 的最後一個參考是 `_voiceManager`（`Teardown.run` 會把 `_cleanups` 換成空 dict，`bringup.py:28`，所以 teardown 的 closure 也放掉了）；分支多了 `_numberLanguageChoice._manager` 這條路徑，manager 連同 `catalog`、`settings`、`_default_voice_instance`（engine 已關閉的 Voice 實例）要等 `SynthDriver` 本身被回收才釋放。spec 的「holds no resource」就 OS 資源而言正確，但它確實持有 manager 物件。
- 失敗情境：實務上無——NVDA `setSynth` 把 `_curSynth` 設成 None 後整個 driver 連同 choice 一起回收；只有另有人長期持有 driver 時才多留一份已關閉的 manager 圖。
- 建議：二擇一，都很便宜：(a) 在 `terminate` 的 `finally` 加 `self._numberLanguageChoice = None`（terminate 後讀 `numlan` 變回在 None 上拋 `AttributeError`，和 master 的形狀一致，`speechContext()` 仍先以 `_voiceManager is None` 擋住）；(b) 維持現狀，把 spec §5.2 的句子改成「it holds only the manager reference」。列為未確認的預設（下方第 4 點）。

### M2. 「被拒絕的值存成 `FOLLOW`、之後該 locale 裝了語音也不會回來」沒有測試釘住（突變 m06 存活）

- 位置：`addon/synthDrivers/WorldVoice/voices/numberLanguageChoice.py:37`（`self._value = value if accepted else FOLLOW`）；`tests/test_number_language_choice.py:33-38`（`test_a_refused_value_stores_follow`）；`tests/test_worldvoice_speak.py:700-708,719-724`。
- 內容：把 `:37` 改成 `self._value = value`（拒絕時也把值留著）後 209 個目標測試全過，因為 `stored` 每次讀都重新驗證，當下讀起來仍是 `"default"`。差別只在之後：使用者在沒有法語語音時存了 `fr`（被拒），後來啟用了有法語語音的引擎——master 與分支都會一直是 `"default"`（NVDA 下次 `saveSettings` 也會把 `"default"` 寫回），突變版會「復活」成 `fr`。master 也沒有這個測試（當時的 `_set_numlan` 一樣沒人釘），只是現在有了單元測試檔，補一個很便宜。
- 失敗情境：將來若有人把 `store` 改成「先存再說」（例如為了保留使用者原始輸入），沒有測試會發現。
- 建議：在 `tests/test_number_language_choice.py` 加一個案例：`choice.store("fr")` 回傳 `False` 後，`manager.all_languages = ("en", "zh_TW", "ja", "fr")`、`manager.languages = ("en", "fr")`，斷言 `choice.stored == "default"` 且 `choice.spoken == "default"`。約 6 行。

## 審閱者自行驗證的項目

測試都在任務 worktree `/workspace/WorldVoice-phase40`（`ref` 為 symlink）或審閱者自己建的 detached 暫時 worktree（`scratchpad/review40/mut`，另建 `ref` symlink，用完已移除）執行，序列跑，附 3 GB `MemAvailable` 看門狗（從未觸發；開跑時 MemAvailable 5.66 GB）；沒有碰主 checkout，沒有用 `git stash`，沒有修改任何原始碼。

| 項目 | 指令 | 結果 |
| --- | --- | --- |
| 完整測試（分支頭 `07d82ea`） | `scratchpad/review40/guarded.sh /workspace/WorldVoice-phase40 … tests`（先清 `__pycache__`，`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests`，序列，看門狗） | 3359 passed、0 skipped（152.45 s）；看門狗 0 次觸發 |
| hook | `prek run --all-files`（worktree） | 8 個 hook 全部 Passed；之後 `git status --short` 乾淨 |
| 空白與受保護路徑 | `git diff --check master`；`git diff --stat master -- '…/driver/*/driver/' …/sonic/ …/script_data.py …/unspaced_common_data.py`；`git ls-files …/driver/Neural` | 三者皆無輸出 |
| commit 衛生 | `git log master..HEAD --format='%b' \| grep -ic co-authored`；`git log master..HEAD --name-only --format= \| grep ^ref`；每個 subject 與 body | 0；無；6 個都是英文 `<type>: <summary>` 加說明原因的內文 |
| Python 3.11 相容 | `git diff master -U0 -- addon tests \| grep -E 'typing\.override\|\boverride\b\|^\+\s*type\s+\w+\s*=\|^\+\s*class\s+\w+\[\|batched'` | 無；`python3 --version` 3.14.4（無 3.11 可實跑） |
| 搬移比對（自己寫的，token 層級、順序敏感） | `python3 -I scratchpad/review40/move_check_tokens.py /workspace/WorldVoice-phase40 addon/synthDrivers/WorldVoice/__init__.py addon/synthDrivers/WorldVoice/confspec.py installConfspec 05183ee` | `OK`：segment `__init__.py:70-89`（20 行）→ `confspec.py:13-32` 逐位元組相同；`confspec.py` 只有 docstring、4 個 import、segment；`__init__.py` 在 parent 去掉 segment 與 import 後的 token 序列（2805 個，含 NEWLINE／INDENT／DEDENT）和 move commit 去掉 import 後完全相同；import 差異只有四個 owner 名稱移出、`installConfspec` 移入 |
| 搬移比對的負向對照 | 在 scratch 的小 git repo 做 5 個變體 | 乾淨搬移 `OK`；舊模組多改一行、segment 內容變動、舊模組兩個敘述對調、新模組多一個敘述，各自 `FAILED` |
| move／edit commit 分開 | `git show 58956f6 -- __init__.py`；`git show 05183ee -- tests/` | edit commit 只把 dict 包進函式並在原位呼叫（dict 每行只多一個 tab）；move commit 的測試只改路徑參照（6 行） |
| F3-3 逐行對照（無搬移證明） | `git diff master..HEAD -- addon` 對照 master `__init__.py:469-509` | 五個規則逐條同形（見「結論」第 1 點） |
| `[WorldVoice]` 讀者都在函式內 | `grep -rn '\["WorldVoice"\]' addon --include=*.py` | 12 處，全部在函式或方法內；`installTasks.py` 不讀 |
| 舊名稱沒有殘留呼叫者 | `grep -rn '_numlan\b\|_isStoredNumberLanguage' addon tests ref/Neural` | 產品碼 0 筆；測試只剩 `_set_numlan`／`_get_numlan` 的呼叫 |
| `_voiceManager` 指派點 | `grep -n '_voiceManager =' __init__.py` | 只有 `__init__`（None）、`_initialize`、`terminate`；choice 的 manager 不會過期 |
| terminate 後的清單 | 讀 `voices/manager.py:131-156,251-285`、`bringup.py:26-36` | `catalog`、`_default_voice_instance` 保留，`languages`／`all_languages` 仍可讀；`Teardown.run` 清空 closure（M1） |
| NVDA 時序與呼叫者 | 讀 `core.py:720-928`、`globalPluginHandler.py:18-35`、`synthDriverHandler.py:364-410,452-453,504-545,582-600`、`settingsDialogs.py:1324,1484`、`config/__init__.py:1326,1352,1464-1470` | 見「結論」第 3、4 點 |
| 行數 | `git show master:…/__init__.py \| wc -l`；`wc -l __init__.py` | 530 → 498 |
| 突變測試（25 次，暫時 worktree） | `python3 scratchpad/review40/mutate.py …`（每次只改一處、清 `__pycache__`、`PYTHONDONTWRITEBYTECODE=1`、`-p no:cacheprovider`、不加 `-x`、每個突變 300 s 逾時、還原後 `git status --short` 必須乾淨） | 見下表 |

### 突變測試

目標測試：A = `test_number_language_choice.py` + `test_worldvoice_speak.py` + `test_worldvoice_lifecycle.py` + `test_worldvoice_pipeline_settings.py`（209 個）；B = `test_confspec.py` + `test_runtime_composition.py` + `test_pipeline_panels.py`；C = `test_naming_layers.py`。

| # | 還原的東西 | 目標 | 抓到的測試 |
| --- | --- | --- | --- |
| m01 | `stored` 不重新驗證，直接回傳 `_value` | A | `test_a_stored_locale_no_longer_installed_reads_as_follow` |
| m02 | `is_storable` 讀 `languages` 而不是 `all_languages` | A | `test_storable_values[ja]`、`test_a_hidden_locale_is_kept_and_listed_last`、`test_the_choice_reads_the_manager_each_time`、speak 的 `test_a_hidden_locale_survives_loading_and_saving_and_comes_back[×2]`（5 failed） |
| m03 | `spoken` 不看被提供的語音，直接回 `stored` | A | `test_a_hidden_locale_is_kept_and_listed_last`、`…survives_loading_and_saving…[×2]`（3 failed） |
| m04 | `listed_locales` 不把被隱藏的 stored locale 排最後 | A | 同 m03（3 failed） |
| m05 | `store` 什麼都接受 | A | `test_a_refused_value_stores_follow[zz,fr]`、speak 的 `test_an_unknown_number_language_reads_as_follow[zz,fr]`、`test_a_locale_of_an_uninstalled_voice_is_refused_on_load`（5 failed） |
| m06 | `store` 被拒時仍把值留著（`stored` 照樣重新驗證） | A | **存活（209 passed）**，見 M2 |
| m07 | driver `_set_numlan` 每次都記警告 | A | speak 的 `test_known_number_languages_are_kept[×4]`、`…survives…[×2]`、lifecycle 的 `test_the_detector_reads_the_drivers_number_language`（7 failed） |
| m08 | driver `_set_numlan` 完全不呼叫 `store` | A | lifecycle 的 `test_the_detector_reads_the_drivers_number_language` + speak 的 82 個（`test_number_languages_list_every_voice_language_by_its_description`、`test_main_language_numbers[…]`、`test_property_each_digit_is_read_by_the_number_language_voice[…]` 等）：83 failed／126 passed，14.7 s。**第一輪這個突變「停滯」約 2 小時被協調者終止，是審閱者突變腳本的 bug，不是 mutant 的死鎖**：腳本用 pipe 收 pytest 輸出卻在結束後才讀，83 個長 traceback 塞滿 64 KB 的 pipe，pytest 在 write 上阻塞（睡眠、15 s CPU 符合）。把輸出改寫到檔案後 m08（14.7 s）與同樣受影響的 m13（2.2 s）都正常完成；手動以 `timeout 300` 直接重跑也是 15 s。之後每個突變都另加 300 s 逾時 |
| m09 | driver `_get_availableNumlans` 列 `manager.languages` 而不是 `listed_locales()` | A | `…survives_loading_and_saving…[×2]`（2 failed） |
| m10 | `_initialize` 不建 choice（留 None） | A | lifecycle 的 `test_the_detector_reads_the_drivers_number_language` |
| m11 | `__init__.py` 不呼叫 `installConfspec(config.conf)` | B | `test_runtime_composition.py::test_entry_point_imports_real_ledger_and_completion_policy`（Review Focus 1） |
| m12 | confspec 的 `role` 與 `engine` 區段對調 | B | `test_confspec_sections`、`test_entry_point_imports_real_ledger_and_completion_policy` |
| m13 | confspec 的 `pipeline` 直接用 owner 的 dict、不複製 | B | `test_confspec_sections`（`is not` 斷言）；另外 `nvda_stubs` 的 AST 讀取器只接受字面 dict，8 個 panel 測試 failed、63 個 error（9 failed／4 passed／63 errors） |
| m14 | `keepMainLocaleVoiceConsistent` 預設 true → false | B | `test_confspec_sections` |
| m15 | `confspec.py` 加 `import config` | B | `test_confspec_receives_conf` |
| m16 | `numberLanguageChoice.py` 多匯入 `..pipeline.settings` | `test_number_language_choice.py` | `test_the_choice_imports_only_the_number_language_values` |
| m17 | 守門 `HOST` 拿掉 `confspec.py` | C | `test_every_add_on_module_has_a_layer` |
| m18 | 核心的 `is_storable` 改成 `isStorable` | C | `test_naming_follows_layer` |
| m19 | 宿主的 `installConfspec` 改成 `install_confspec`（三處） | C | `test_naming_follows_layer`（另三個靠 `worldvoice_conf` 的測試因 stub 找不到函式而 error，共 4 failed） |
| m20 | confspec 的 `log` 區段拿掉 `enable` | B | `test_confspec_sections` |
| m21 | choice 起始值 `MAIN` 而不是 `FOLLOW` | A | `test_a_new_choice_follows_the_text`、lifecycle 的 `test_the_detector_reads_the_drivers_number_language`、`test_speech_context_falls_back_while_the_synth_is_not_running` |
| m22 | driver `_numberLanguage` 轉發到 `stored` 而不是 `spoken` | A | `…survives_loading_and_saving…[×2]`（speech 讀到被隱藏的 locale） |
| m23 | driver `_get_numlan` 轉發到 `spoken` 而不是 `stored` | A | `…survives_loading_and_saving…[×2]`（save 寫回 `"default"`） |
| m24 | `listed_locales` 以 `all_languages` 為底 | A | `test_a_new_choice_follows_the_text`、`test_the_choice_reads_the_manager_each_time` |
| m25 | driver `_get_availableNumlans` 丟掉兩個 follow 項 | A | `test_number_languages_list_every_voice_language_by_its_description` |

### Review Focus 逐項

| # | 項目 | 核對 |
| --- | --- | --- |
| 1 | 其他合成器在用時 global plugin 的 import 仍裝 spec | `__init__.py:70` 在套件 import 執行；`globalPlugins/WorldVoice/__init__.py:14` 的子模組 import 先跑套件 `__init__`；`test_runtime_composition.py:633-636` 以真正的 import 釘住，m11 抓到；時序與 master 相同（見「結論」第 3 點） |
| 2 | 被隱藏的 stored locale 經 load／save 存活、列最後、speech 讀 `"default"` 直到再被提供 | `test_a_hidden_locale_survives_loading_and_saving_and_comes_back[×2]`（模擬 NVDA `loadSettings(onlyChanged=True)` 與 `saveSettings`）與 `test_a_hidden_locale_is_kept_and_listed_last`；m02、m03、m04、m09、m22、m23 抓到 |
| 3 | 未知的 stored 值讀成 `"default"` 且恰好一個警告 | `test_an_unknown_number_language_reads_as_follow[zz,fr]`（`(warning,) = synth.warnings`）、`test_a_locale_of_an_uninstalled_voice_is_refused_on_load`、`test_a_refused_value_stores_follow`；m05、m07 抓到 |
| 4 | 每次呼叫都讀 manager 的 `languages`／`all_languages`，不是建構時的快照 | `NumberLanguageChoice` 只存 `_manager`，四個成員每次都經 `self._manager.*`（`numberLanguageChoice.py:22,43,52`）；`test_the_choice_reads_the_manager_each_time` 與 speak 測試中途改 `languages` 的案例；m02、m24 抓到 |
| 5 | 偵測器的 `number_language` provider 跟著之後的 `_set_numlan` | `test_the_detector_reads_the_drivers_number_language` 改用 `_set_numlan("main")`；`_initialize` 建 choice 在 `LanguageDetector` 之前（`__init__.py:235,256`）；m07、m08、m10 抓到 |

## Ruling 評估

| Ruling | 評估 |
| --- | --- |
| 模組名 `voices/numberLanguageChoice.py`，不是 refactor9 的 `voices/numberLanguage.py` | **合理。** `voices/numberLanguage.py` 得 `from ..numberLanguage import` 自己的同名模組，`.`／`..` 只差一點；類別名當檔名和 `voices/` 既有的 camelCase 檔名一致。代價若錯：一次檔名改名。 |
| 函式名 `installConfspec`（宿主 mixedCase），不是 refactor9 的 `install_confspec` | **合理。** §6.1 歸屬表明列 `confspec.py` 為宿主層；它匯入的 `pipeline/registry.py` 直接 `import config`；§6 的「P40 放在命名之後……直接照規則取名」就是這個意思。m19 證明用 snake_case 會被守門抓到。 |
| Task 3：`NumberLanguageChoice` 直接寫在新模組、Task 4 併入 Task 3、不做搬移證明 | **合理，但要由審閱者補逐行對照——已做。** 理由成立：把 snake_case 成員的類別暫放在宿主層的 `__init__.py` 會讓 `test_naming_follows_layer` 失敗（依守門規則 `MIXED_CASE_FUNCTION` 不允許 `is_storable`、`listed_locales` 這種底線名；審閱者依規則推斷，沒有實跑中間狀態）；就算先用 mixedCase 再在搬移時改名也不是逐字搬移。帳本附的舊→新對照正確（`_isStoredNumberLanguage→is_storable`、`_get_numlan` 本體→`stored`、`_set_numlan` 驗證與指派→`store`（log 留在 driver）、`_numberLanguage` 本體→`spoken`、`_get_availableNumlans` 的 locale 清單→`listed_locales`），註解以 docstring 形式保留。 |
| Task 3：`worldvoice_harness.number_language_choice_class()` 共用給單元測試與 driver harness | **合理。** 以真正的 `FOLLOW`／`MAIN` 載入真正的類別，單元測試與 driver 測試用的是同一份實作；plan 寫的 `CHOICE_SOURCE` 常數只是位置不同。 |

## 使用者還沒確認的使用者可見預設

協調者採建議預設、使用者可在 merge 前推翻的事項（spec §5.1、§5.2、§8）；都不影響 NVDA 使用者看到的介面或設定：

1. **`installConfspec(config.conf)` 留在套件 import 時呼叫**（不是 `SynthDriver.__init__`）。審閱者同意：WorldVoice 不是目前合成器時 global plugin 的 Pipeline／Engine／Log panel 仍要讀 `[WorldVoice]`（refactor9 §7 第 3 點）；時序與 master 相同。
2. **`confspec.py` 歸宿主層、函式名 mixedCase `installConfspec`**。審閱者同意，理由見「結論」第 5 點與 Ruling 評估。
3. **模組名 `voices/numberLanguageChoice.py`**。審閱者同意。
4. **terminate 不清 `_numberLanguageChoice`**：之後讀 `numlan` 答最後一份清單而不是拋 `AttributeError`，並多留一條到已 terminate 的 manager 的參考（M1）。審閱者傾向在 `terminate` 的 `finally` 一併設成 None（一行），但維持現狀也沒有實際風險。

## 未在 Linux 驗證的項目

- NVDA 本身、Windows、實際音訊裝置、引擎 SDK 都沒有載入；NVDA 真正的 `config.conf.spec` 與 Voice panel 沒有實跑，依原始碼時序判斷。Python 3.11 沒有實跑（容器只有 3.14）。本 phase 沒有使用者可見的行為變更，不需要打包；未打包、未在 Windows 驗證。

## 修正記錄

- **M1 已修**：`b9593b4` `terminate` 的 `finally` 一併清掉 `_numberLanguageChoice`；先加的 `test_terminate_drops_the_number_language_choice` 修正前失敗、修正後通過。terminate 之後讀 `numlan` 恢復成和 master 一樣會失敗；spec §5.2 的對應預設已加刪除線並標註。
- **M2 已修**：`e0191e8` 新增 `test_a_refused_locale_stays_refused_when_its_voice_is_installed_later`；把 `store()` 改成保留被拒的值（m06）時這個測試會失敗。
