# 保留其他語音引擎的語音角色 Review 紀錄

日期：2026-10-30。分支：`fix/keep-other-engine-roles`（`031ff3d..fd7ca0a`，12 個 commit，基於 `master` `031ff3d`）。
依據：

- 規格 `docs/superpowers/specs/2026-10-30-keep-other-engine-roles-design.md`
- 計畫 `docs/superpowers/plans/2026-10-30-keep-other-engine-roles.md`
- 進度帳本 `.superpowers/sdd/2026-10-30-keep-other-engine-roles/progress.md`

流程：一般流程 §3.3 的最後 review，模型 Fable 5.1，唯讀。所有需要改動檔案的驗證（還原修正、D4 探針、mutmut）都在 scratchpad 的複本上做；任務 worktree 與主 checkout 都沒有動。

## 結論

Ready to merge：**修完 I1 後可以**。Critical 0、Important 1、Minor 4。

實作與 spec U1–U4、D1–D3、D5、D6 一致：決定從寫入時（prune）移到讀取時（`admits` + `voice_for` 的 `usable`），setter 與面板確定都不再刪除角色，切回引擎後角色恢復，Cancel 不會遺失。Review Focus 五項都有對應測試，且還原修正後都會失敗（見驗證表）。唯一的問題是 spec D4「什麼都不清理」在升級情境下會造成相對 `master` 的回歸，需要在 merge 前補一個很小的清理。

## Critical

無。

## Important

### I1 舊版寫入的完整地區鍵（例如 `zh_TW`）不再被清掉，會蓋過面板的 `zh` 角色（spec D4）

- 位置：`addon/synthDrivers/WorldVoice/voices/roles.py:22-34`（`voice_for` 先查完整地區鍵再查主要語言鍵）；`addon/synthDrivers/WorldVoice/voices/manager.py:189-195`（setter 不再清理）；`addon/synthDrivers/WorldVoice/voices/mainLocalePolicy.py:68-70`（`follow` 只寫主要語言鍵）；`addon/synthDrivers/WorldVoice/voices/catalog.py:16-20`（面板只列主要語言鍵）。
- 背景（從 git 歷史確認）：`78f3880`（2026-07-28）之前的 `onKeepMainLocaleVoiceConsistent` 每次更換主要語音都同時寫 `zh_TW` 與 `zh` 兩個鍵（`git show 78f3880^:addon/synthDrivers/WorldVoice/voiceManager.py`，248–257 行）。當時與 `master` 的 prune 都在 setter 裡刪掉不在 primary-locale 表裡的鍵，所以在含 prune 的版本上，第一次更換主要語音（包含 NVDA 啟動時 `loadSettings` 設回儲存的語音）就會把這種鍵清掉。「保持主要語音角色與地區語音角色一致」預設開啟，因此 6.2（2026-07-31 發布）之前的設定檔幾乎都帶著 `<主要語音的完整地區> → 當時的主要語音`。只要使用者跳過 6.2 直接升級，或 6.2 期間儲存的語音剛好等於暫定語音（setter 沒跑過），這些鍵就會原封不動進到這個版本，而本分支從此不再清理。
- 失敗情境（已在 `master` 與分支的複本上用同一個探針重現，見驗證表）：設定檔 `role = {zh_TW: A:old, zh: A:old}`，主要語音 A:old，引擎一致與語音一致都開啟。使用者在 NVDA 語音面板改成同引擎的 A:new → `follow` 寫 `zh → A:new`，`zh_TW → A:old` 留著。此後 `get_voice_name_for_language("zh_TW")` 回 A:old：
  - 混合文字：偵測器從拉丁字回到漢字時發出 `WVLangChangeCommand(target_lang)`（`addon/synthDrivers/WorldVoice/languageDetection/detector.py:77`，目標語言是目前語言 `zh_TW`）；`lang_cmd_to_voice` 對 `LangChangeCommand(None)` 也用 `ctx.default_voice_language`（A:new 的語言 `zh_TW`）查角色（`addon/synthDrivers/WorldVoice/pipeline/languageCommands.py:85-86`）。結果：每次從英文回到中文都由舊語音 A:old 朗讀，面板裡卻顯示 zh → A:new。`master` 上第一次更換主要語音就清掉 `zh_TW`，兩邊都是 A:new。
  - 語音引擎清單來回：`voice_name_for_engine("A", "zh_TW")`（`manager.py:284-286`）不帶 predicate，拿到 `zh_TW` 的 A:old，切回引擎 A 時落在舊語音，不是使用者最後選的 A:new；接著 `follow` 再把 `zh` 也改回 A:old。
  - 面板只列主要語言鍵，使用者看不到也刪不掉 `zh_TW`；沒有 UI 補救。
- 建議修法（擇一，建議第一種）：
  1. `ConfigRoleRepository.save` 寫入時丟掉主鍵不是主要語言的 section（`primary_language(locale) != locale`），scalar 值照舊保留。觸發點（`follow` 與面板確定）正好是舊 prune 的觸發點；U1「更換主要語音不刪地區角色」仍成立，因為這些鍵不是面板能設定或顯示的角色，而且自 `78f3880` 起沒有任何程式會再寫入。測試：`tests/test_role_repository.py::test_save_drops_legacy_full_locale_keys`（`zh_TW` section 消失、`legacy: kept` scalar 保留）；`tests/test_runtime_composition.py`：legacy `zh_TW` 鍵加同引擎主要語音更換後，`get_voice_name_for_language("zh_TW")` 是新語音、role section 只剩 `zh`。
  2. 或在 `VoiceManager._init_policies` 之後做一次性正規化（啟動時寫 config）；缺點是啟動就寫設定檔，而且 follow 關閉時也會動到。
  - 不建議改 `voice_for` 的鍵順序或拿掉完整地區鍵的查詢：那會動到 D2 與現行查詢語意，而且 NVDA 的 `LangChangeCommand` 本來就帶完整地區。

## Minor

### M1 `voice_name_for_engine` 沒有套 D2 的跳過規則

- `addon/synthDrivers/WorldVoice/voices/manager.py:284-286`：`roles.voice_for(language)` 不帶 predicate。完整地區鍵指向別的引擎時（`fr_CA → B:b`、`fr → A:c`），切到引擎 A 會忽略 `fr` 的 A:c，改由語言比對挑第一個 fr 語音。查詢路徑（`_may_speak`）會跳到 `fr`，引擎切換卻不會，兩條路徑挑到不同語音。
- 建議：`self.roles.voice_for(language, lambda name: (spec := self.catalog.by_name.get(name)) is not None and spec.engine == engine)`，測試加在 `tests/test_runtime_composition.py`。採 I1 修法 1 後這個情境只剩理論上的可能，可不修。

### M2 zh_TW readme 用語

- `addon/doc/zh_TW/readme.md:27`：「主要語音角色屬於其他引擎時」建議改為「主要語音角色切換到其他引擎時」，和同句後半「切換回原本的引擎後」對應；整條偏長，可在「其他語音引擎的地區語音角色會保留」前分句。其餘用語（地區語音角色、語音角色設定面板、未選擇、語音引擎）都和既有條目一致。
- `addon/doc/zh_TW/readme.md:96` 更新日誌條目自然、簡潔，不用改。
- 依使用者規則只更新 zh_TW，其他語言之後同步，不列為缺漏。

### M3 `tests/test_engine_setting.py:158` 只靠假物件缺少方法來失敗

- 把 `_get_voice` 改回 `get_voice_name_for_language` 時，失敗原因是 `AttributeError`（假 `Manager` 沒有該方法，`tests/test_engine_setting.py:62-63`），不是行為斷言。假物件日後同時提供兩個方法時，這條測試抓不到回歸。規則本身由 `tests/test_voice_manager_roles.py::test_initial_voice_is_the_available_role_of_any_engine` 覆蓋，所以只是補強：讓假 `Manager` 的 `get_voice_name_for_language` 回傳主要語音、`initial_voice_name` 回傳角色語音，斷言仍是 `B:b1`。

### M4 Hypothesis 性質在退回主要語音時恆真

- `tests/test_voice_manager_roles.py:114`：`name == main or name in manager.catalog.by_name` 在退回主要語音的分支永遠成立；有力的斷言只有 113 行的「不寫 config」與旗標開啟時的引擎相同。建議改成 `name == main or manager._may_speak(name)`，把「缺少的語音永遠不會被選到」也寫進性質。

## 審閱者自行驗證的項目

| 項目 | 指令 | 結果 |
| --- | --- | --- |
| 完整測試（分支內容的 scratch 複本，序列，MemAvailable < 3 GB 的監控沒有觸發） | `python3 -m pytest -q -p no:cacheprovider tests` | 第一次 3691 passed、1 failed：唯一失敗是 `test_hygiene_guards.py::test_the_ignore_numbers_option_is_gone` 讀不到複本缺少的根目錄 `readme.md`（複本問題）；補上後該檔 16 passed。`--collect-only` 在 worktree 與複本都收集到相同的 3692 個 id。mutmut 結束後再跑一次：見下方「最終完整測試」 |
| 最終完整測試（mutmut 結束後，複本，序列） | 同上 | **3692 passed, 0 skipped**（基準 3680，+12，與實作者回報相同）。附帶：審閱者中途有兩次把 `cd` 寫進背景的監控子 shell，pytest 實際在 `/workspace/WorldVoice`（master）執行，得到 3680 passed，等於基準；主 checkout 只被讀取，`git status` 與開始時相同 |
| ruff（hook 鎖定版本） | `ruff --version; ruff check addon tests tools; ruff format --check addon tests tools` | 0.16.3；All checks passed；246 files already formatted。沒有在 worktree 跑 `prek run --all-files`，避免 hook 改寫實作者的檔案；worktree `git status` 乾淨，表示實作者的 commit 都過了 hook |
| 空白與受保護路徑 | `git diff --check master`；`git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py addon/synthDrivers/WorldVoice/unicodeScripts/unspaced_common_data.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 三個都沒有輸出 |
| commit 訊息 | `git log master..HEAD --format=%B` | 12 個 commit 都是英文 `<type>: <summary>`，沒有 `Co-Authored-By` |
| 殘留 prune | `grep -rn prune addon tests` | 沒有輸出 |
| 還原 A：`admits` 永遠回 `True` | `tests/test_main_locale_policy.py tests/test_voice_manager_roles.py` | 5 failed（admits 測試、另一引擎跳過、full-locale 退回、initial、Hypothesis） |
| 還原 B：`voice_for` 忽略 `usable` | `tests/test_role_repository.py tests/test_voice_manager_roles.py` | 8 failed |
| 還原 C：查詢改回 master（`voice_for(language)` + `voice_infos`） | `tests/test_voice_manager_roles.py tests/test_runtime_composition.py tests/test_role_presenter.py` | 7 failed，含 `test_an_engine_round_trip_keeps_and_restores_the_roles[False/True]`、`test_engine_consistency_preview_cancel_and_apply` |
| 還原 D：`initial_voice_name` 套引擎規則 | `tests/test_voice_manager_roles.py` | 1 failed（`test_initial_voice_is_the_available_role_of_any_engine`） |
| 還原 E：setter 重新 prune | `tests/test_runtime_composition.py tests/test_voice_manager_roles.py` | 3 failed（round trip ×2、`test_switching_back_picks_the_kept_role_voice_of_the_engine`） |
| 還原 F：面板確定重新 prune | `tests/test_role_presenter.py` | 2 failed（`test_engine_consistency_preview_cancel_and_apply`、`test_apply_keeps_an_untouched_role_of_another_engine`） |
| 還原 G：synth `_get_voice` 改回 `get_voice_name_for_language` | `tests/test_engine_setting.py` | 1 failed，但原因是 `AttributeError`（見 M3） |
| D4 探針：legacy `zh_TW → A:old`、`zh → A:old`，兩個旗標開啟，主要語音改成同引擎的 A:new | scratchpad 的 `test_d4_legacy_key.py`，分別放進 master 複本與分支複本執行 | master：role 只剩 `{zh: A:new}`，`zh`、`zh_TW` 都是 A:new。分支：role `{zh_TW: A:old, zh: A:new}`，`zh → A:new`、`zh_TW → A:old`（I1） |
| 查詢所在執行緒 | 讀 `addon/synthDrivers/WorldVoice/__init__.py:330-346`、`runtime/requestBuilder.py:10-35` | `speak` 在 NVDA 主執行緒組 pipeline，`queue_speech_sequence` 當場把序列走完，角色查詢（`_may_speak` 讀 `_default_voice_instance.engine`、`engine_consistency.enabled`、`catalog.by_name`）和 setter、面板寫入都在主執行緒；`catalog.by_name` 是 MappingProxy；沒有新的鎖或跨執行緒讀寫 |
| 突變測試（複本，`source_paths` 縮到 `mainLocalePolicy.py`、`roles.py`，忽略 hygiene 與 naming 測試，`--max-children 2`，記憶體監控） | `mutmut run`、`mutmut results` | 112 個 mutant、100 killed、12 survived，記憶體監控沒有觸發。12 個存活都在 `roles.py`：11 個在 `_is_section`（`roles.py:9-10`，本分支沒有改動的既有輔助函式；測試只用 dict 與 `Section`，`hasattr(items) and hasattr(get)` 這個分支沒有測試走到），1 個是 `voice_for__mutmut_5`（同實作者的紀錄，等價）。本分支新增或修改的函式（`admits`、`voice_for` 的 `usable` 判斷）沒有存活的 mutant |
| 實作者的 mutmut 紀錄 | scratchpad `mutmut.log` | 45 個目標 mutant、44 killed、1 survived：`roles.voice_for__mutmut_5`（`hasattr(section, "get") or True`）。同意是等價 mutant：`_section()` 回傳的 NVDA `AggregatedSection` 與 dict 都有 `get`，差異只在非 mapping 物件 |

## Plan Review Focus 逐項檢查

1. **引擎來回 A → B → A**：`tests/test_runtime_composition.py::test_an_engine_round_trip_keeps_and_restores_the_roles[False/True]` 用真實 `VoiceManager` 走 setter，斷言 B 期間 `zh` 由主要語音朗讀、角色沒刪、回 A 後 `first:b` 恢復、follow 開啟時只有 `en` 跟著主要語音、結束時 section 等於原本。還原 C 與 E 都會讓它失敗。通過。
2. **語音被移除的角色**：`test_a_missing_role_voice_is_kept_and_speaks_when_back` 與 Hypothesis 性質。通過；M4 建議把性質收緊。
3. **面板確定與未動的其他引擎角色**：`test_apply_keeps_an_untouched_role_of_another_engine`（面板列表為空、`selectedVoice` 回存的 B:b、只改 en）、`test_engine_consistency_preview_cancel_and_apply`（勾選後確定仍保留並被跳過）、`test_apply_writes_only_the_changed_locales`（明確「未選擇」移除）、`test_a_stored_voice_the_locale_does_not_list_shows_no_select`（真實面板程式碼、假 presenter：選第 0 項、滑桿停用、不呼叫 presenter）。通過。
4. **另一引擎的完整地區鍵**：`test_voice_for_skips_an_unusable_voice_to_the_primary_locale`、`test_a_skipped_full_locale_role_falls_back_to_the_primary_role`。通過；但同引擎的 legacy 鍵是 I1。
5. **NVDA 設定語音之前**：`test_initial_voice_is_the_available_role_of_any_engine`（真實 manager）與 `test_before_load_settings_the_engine_follows_the_role_voice`（synth，假 manager）。通過；M3 說明後者的弱點。

## 進度帳本 Ruling 評估

| Ruling | 評估 |
| --- | --- |
| Task 9：scratch 複本用 `cp -a` 複製 `addon tests tools pyproject.toml buildVars.py .pre-commit-config.yaml ref`，不用 `cp -rL` | 合理。我用同樣方式建複本，另外發現 hygiene guard 需要根目錄 `readme.md`，複本要一併複製。 |
| Task 8：文件範圍縮到 `addon/doc/zh_TW/readme.md`，其他五個 readme 的修改在新 commit 還原 | 合理，是使用者 2026-10-30 的規則；`630a396` 只還原那五個檔案與縮短 zh_TW 文字，`fd7ca0a` 把 spec §8 與 plan Task 8 同步。 |
| Task 9：複本的 mutmut `source_paths` 縮到三個檔案並忽略 `tests/test_naming_layers.py` | 合理。全量 `source_paths` 的 stats 收集會被 `pipeline/settings.py` 的動態載入擋住，naming guard 會判到 mutmut 改寫的名字；repo 的 `pyproject.toml` 只加了 `roles.py`。 |

## 第 8 節限制

- 內層驅動、sonic、Unicode 資料檔沒有變動；Neural 沒有被加回。
- 改動只在 core（`voices/`）、synth 與 global plugin；沒有碰任何 wrapper，各引擎驅動仍可單獨安裝。
- `voices/` 新名字用 snake_case（`admits`、`usable`、`initial_voice_name`）；presenter 與 synth 維持 mixedCase。`tests/test_naming_layers.py` 通過。
- 沒有 UI 字串變動，不需要翻譯更新。

## 使用者還沒確認的使用者可見預設

1. **D4（建議推翻，見 I1）**：目前分支完全不清理舊鍵。建議至少在寫入時丟掉非主要語言的 section。
2. **D1**：查詢讀的是「已儲存」的引擎一致旗標。語音角色面板裡勾或取消勾選時，列表立刻改變，但在按確定之前朗讀行為不變。
3. **D2**：引擎一致開啟時，完整地區鍵（`zh_TW`）的語音被跳過就退回主要語言鍵（`zh`），再退回主要語音。
4. **D3**：NVDA 還沒設定語音時（第一次啟動、儲存的語音無效），synth 回報介面語言的角色語音，不限引擎（維持今天的規則）。
5. **D5**：引擎切換挑語音的規則不變；角色保留後，切回引擎會回到介面語言的角色語音，而不是該引擎符合介面語言的第一個語音。
6. **spec §4 的邊角**：引擎一致開啟時，某地區顯示「未選擇」（其實存著別的引擎的角色），使用者先選一個語音再改回「未選擇」並確定，會把那個隱藏的角色刪掉。
7. **U4 的已知限制**：「保持主要語音角色與地區語音角色一致」開啟（預設）時，主要語言地區的角色永遠跟著主要語音，不會分引擎保留。
8. **既有行為**：引擎一致開啟時，只有其他引擎才提供的語言不會出現在語音角色面板的地區清單，那些角色看不到也刪不掉（只能先取消勾選引擎一致）。

## Linux 上無法驗證

spec §7 的 Windows／NVDA 手動清單 1–6（OneCore／eSpeak 來回、Cancel、面板在其他引擎下的「未選擇」、停用再啟用引擎、follow 開啟時只有主要語言地區跟著）在 Linux 上沒有驗證；真實引擎 SDK、NVDA 的 `changeVoice` 與設定檔切換也沒有。

## 工作區備註

- 審閱期間 scratchpad 內另有實作者留下的 `full_suite.txt`（3679 passed，03:08，早於本分支）與 `mutmut.log`；本表的數字都是審閱者自己重跑的。
- 未在 worktree 執行任何會改檔案的指令；scratch 複本留在 scratchpad，沒有刪除任何 worktree、分支或他人檔案。

## 修正記錄

修正基準：review commit `73fbedd`。每一項都先寫會失敗的測試（M3、M4 是補強既有測試，改用暫時還原實作的方式確認測試會失敗，還原後以 `git checkout -- <檔案>` 復原，沒有用 `git stash`）。

| 項目 | 處理 | commit | 測試 |
| --- | --- | --- | --- |
| I1 舊版完整地區鍵蓋過 `zh` 角色 | 依使用者決定（2026-10-30），不採 review 建議的寫入時清理，改為**安裝時清理一次**：更新安裝時 `addon/installTasks.py` 的 `onInstall()` 呼叫 `_removeLegacyRoleKeys()`，刪除 `config.conf["WorldVoice"]["role"]` 中鍵含 `_` 或 `-` 的 section（`zh_TW`、`pt-br`），保留所有主要語言鍵與非 section 的值；沒有舊鍵時不改寫；`WorldVoice` 或 `role` 不存在時什麼都不做；任何例外只記 log，安裝照常進行。NVDA 的 `AggregatedSection` 沒有 `__delitem__`，所以和 `ConfigRoleRepository.save` 一樣整段指定（`ref/nvda/source/config/__init__.py:1321-1345`，寫入目前的寫入設定檔），指定前把 `AggregatedSection` 轉成一般 dict。已知限制（使用者接受）：只清理安裝當下作用中的設定（通常是一般設定，其他設定檔不動），並仰賴 NVDA 結束時儲存設定。spec D4 已改為 `Decided by the user (2026-10-30)`。 | `ac5cc6f`（程式與測試）、`28e4d2b`（spec） | `tests/test_core_install.py`：`test_an_update_removes_legacy_full_locale_role_keys`、`test_legacy_role_cleanup_keeps_scalars_and_odd_sections`、`test_a_failing_role_cleanup_is_logged_and_the_install_goes_on` 修正前失敗、修正後通過；`test_roles_without_legacy_keys_are_not_rewritten`、`test_an_update_without_roles_adds_none` 鎖定既有行為 |
| M1 `voice_name_for_engine` 沒套 D2 | `voice_for` 改帶「屬於目標引擎」的 predicate，完整地區鍵指向別的引擎時退回主要語言鍵 | `3183cf1` | `tests/test_runtime_composition.py::test_an_engine_switch_skips_a_full_locale_role_of_another_engine`：修正前 `'first:a' == 'first:b'` 失敗 |
| M2 zh_TW readme 用語 | 第 27 行改為「主要語音角色切換到其他引擎時，原本引擎的地區語音角色會保留……」 | `0151bd7` | 文件，無測試 |
| M3 `test_engine_setting.py` 只靠 `AttributeError` 失敗 | 假 `Manager` 同時提供 `get_voice_name_for_language`（回主要語音）與 `initial_voice_name`（回角色語音）；暫時把 `_get_voice` 改回 `get_voice_name_for_language`，測試以 `'A:a1' == 'B:b1'` 失敗 | `02fbcc3` | `test_before_load_settings_the_engine_follows_the_role_voice` |
| M4 Hypothesis 性質恆真 | 改成獨立的模型：完整地區、主要語言兩個鍵中第一個「語音已安裝且（引擎一致開啟時）屬於主要語音引擎」的角色，否則主要語音；結果必須相等。暫時拿掉引擎檢查或 `voice_for` 的跳過，性質都會失敗 | `ddfc0c5` | `test_lookups_never_write_and_speak_only_admitted_voices` |

驗證（修正後，worktree，序列）：`python3 -m pytest -q tests` **3698 passed, 0 skipped**（review 時 3692，+5 安裝清理、+1 M1）；`prek run --all-files` 8 個 hook 全部 Passed；`git diff --check master` 無輸出；兩個受保護路徑指令無輸出。未打包、未在 Windows／NVDA 驗證；新增的手動項目：從帶有 `zh_TW` 角色鍵的舊設定更新安裝後重新啟動，`zh_TW` 鍵消失、`zh` 角色照常朗讀。

## 修正 review（Opus）

日期：2026-10-30。範圍：`73fbedd..73b625f`（7 個 commit：`ac5cc6f`、`3183cf1`、`02fbcc3`、`ddfc0c5`、`0151bd7`、`28e4d2b`、`73b625f`），對照上方 I1、M1–M4 與「修正記錄」。依 §3.4 的修正 review，模型 Opus 5.5，原始碼唯讀。I1 的修法（安裝時清理一次）是使用者 2026-10-30 的決定，本節只評估實作，不評估決定本身。所有還原與探針都在 scratchpad 的複本上做（`cp -a` worktree 的 `addon tests tools pyproject.toml buildVars.py .pre-commit-config.yaml readme.md`，`ref` 為 symlink）；沒有用 `git stash`，任務 worktree 與主 checkout 沒有改動。

### 結論

I1、M1–M4 都已修好，測試都抓得到原本的錯誤。沒有新的 Critical 或 Important；新的 Minor 3 項（N1–N3），都不擋 merge，N1 建議 merge 前順手修，N2 記成已知限制即可。

### 逐項確認

| 項目 | 結果 | 證據 |
| --- | --- | --- |
| I1 | **已修好**（依使用者決定的安裝時清理） | `addon/installTasks.py:60-87`（`_removeLegacyRoleKeys`）、`:109-110`（只在更新時呼叫）。還原呼叫後 `tests/test_core_install.py` 3 failed（`test_an_update_removes_legacy_full_locale_role_keys`、`test_legacy_role_cleanup_keeps_scalars_and_odd_sections`、`test_a_failing_role_cleanup_is_logged_and_the_install_goes_on`），與修正記錄相符。另外逐一突變：不檢查 section（scalar 也刪）、不認 `-`、不轉成 dict、沒有舊鍵也改寫、拿掉 try/except，各自讓 1 個測試失敗；改成只在首次安裝時清理則 3 failed。以 NVDA 真實的 `AggregatedSection`（從 `ref/nvda/source/config/__init__.py` 以 ast 取出）加 configobj 5.0.9 的探針確認：只有一般設定作用時，寫出的 nvda.ini 中 `zh_TW` 消失，`zh`、`en` 與 scalar `legacy = kept` 保留，不需要標記 dirty（基本設定 `save()` 一定寫出，`config/__init__.py:708-726`）。`_plainSection` 是必要的：拿掉後探針寫出 `zh = <AggregatedSection object at …>`，會損壞 nvda.ini；`test_an_update_removes_legacy_full_locale_role_keys` 的 `type(value) is dict` 斷言抓得到。 |
| M1 | **已修好** | `addon/synthDrivers/WorldVoice/voices/manager.py:284-295`。還原成 `voice_for(language)` 後 `test_an_engine_switch_skips_a_full_locale_role_of_another_engine` 以 `'first:a' == 'first:b'` 失敗。`of_engine` 用 `catalog.by_name`，與 `pick_engine_voice` 的 `own`（同一個 table）一致；未安裝的完整地區語音現在也會退回主要語言鍵，比修正前合理。 |
| M2 | **已修好** | `addon/doc/zh_TW/readme.md:27`「主要語音角色切換到其他引擎時，原本引擎的地區語音角色會保留，這些地區暫時改由主要語音角色朗讀……」通順，和後半句「切換回原本的引擎後」對應，用詞與既有條目一致。 |
| M3 | **已修好** | `tests/test_engine_setting.py:62-67` 假 `Manager` 同時提供兩個方法。還原 `_get_voice` 後失敗原因是斷言 `'A:a1' == 'B:b1'`（`tests/test_engine_setting.py:168`），不再是 `AttributeError`。 |
| M4 | **已修好** | `tests/test_voice_manager_roles.py:101-124` 的模型獨立於實作。三種突變都讓性質失敗：`admits` 永遠 `True`、`voice_for` 忽略 `usable`、只查完整地區鍵不退回主要語言鍵。模型用 `language.split("_")[0]` 代替 `primary_language`，在這組取樣（全小寫、只有 `_`）下等價。 |

### I1 對照 NVDA 原始碼的檢查

- **onInstall 何時、在哪裡執行：** `addonHandler.installAddonBundle`（`ref/nvda/source/addonHandler/__init__.py:528-568`）在解壓後立刻呼叫 `onInstall`，由 `systemUtils.ExecAndPump` 在背景執行緒執行（`gui/addonGui.py:237`、`addonStore/install.py:85`），主執行緒同時 pump 訊息。此時舊版 WorldVoice 仍載入中，`config.conf` 可用，寫入落在 `profiles[-1]`（`_getUpdateSection`，`config/__init__.py:1443`；section 指定走 `__setitem__` 的 `updateSect[key] = val` 與 `cache.profiles[-1] = val`，`:1321-1345`）。`onInstall` 丟出例外會讓整個安裝失敗並移除（`addonHandler/__init__.py:556-563`），所以 try/except 是必要的。
- **不會從 onInstall 丟出：** 函式本體全部在 `try` 裡，`except Exception` 只記 log；呼叫點沒有其他新程式。`test_a_failing_role_cleanup_is_logged_and_the_install_goes_on` 也確認核心壓縮檔照常解開。背景執行緒的副作用：主執行緒朗讀時查角色會在 `role._cache` 插入鍵，若剛好發生在 `roles.items()` 迭代中，會丟 `RuntimeError: dictionary changed size during iteration`，結果是記 log、這次不清理（下次更新會再清）。機率很低，不需要修。
- **重新啟動時是否儲存：** `core.py:1101` 在主迴圈結束後呼叫 `config.saveOnExit()`，只有 `general.saveConfigurationOnExit`（預設開啟）時才存（`config/__init__.py:110-119`）；`speech`、`addonHandler` 等在其後才 terminate，舊版在 terminate 時寫的設定不會被存。「仰賴 NVDA 結束時儲存設定」的限制成立。
- **值的形狀：** `ConfigRoleRepository` 讀寫的角色是 `{"voice": name}` section（`roles.py:22-34`、`:45-53`），非 section 值在 save 時原樣保留；6.1.1 的 follow 也寫 section（`role[locale] = {}` 再寫 `['voice']`）。v5.2.1 起 confspec 的 `role` 一直是 `{}`，沒有會被 `__iter__` 列出的 `__many__` 鍵。清理只刪 `_`／`-` 鍵下的 section，與 repository 的形狀一致。
- **作用中的不是一般設定時**：見 N1。
- **舊版在重新啟動前再寫入**：見 N2。
- **無害的殘影：** 清理後，舊版這次執行期間 `role.items()` 仍會列出空的 `zh_TW: {}`，因為 `AggregatedSection.__getitem__` 第一次遇到該 section 時在 spec 建了 `zh_TW: {}`（`config/__init__.py:1237`），而 `__iter__` 也走訪 spec（`:1284`）。它沒有 `voice`，`voice_for` 與 `assignments` 都會略過；新版啟動時 spec 重建，不會帶過去。

### 新發現

Critical：無。Important：無。

#### N1（Minor）安裝時作用中的是其他設定檔時，一般設定沒被清理，該設定檔反而多了一份凍結的角色副本

- 位置：`addon/installTasks.py:71-84`。
- 失敗情境（探針 B，真實 `AggregatedSection`）：一般設定有 `zh_TW → A:old`、`zh → A:old`、`en → B:en`，使用者手動啟用了設定檔 work（`en → C:en`）後更新 WorldVoice。`roles.items()` 是所有作用中設定的聚合值，指定時寫進 work：work 變成 `legacy = kept`、`en → C:en`、`zh → A:old`，被標記 dirty；一般設定的 `zh_TW` 原封不動，聚合後 `zh_TW → A:old` 仍然有效，I1 的問題在這個使用者身上沒有解決，但 log 寫著「Removed legacy speech role keys: ['zh_TW']」。之後在一般設定改 `zh`，切到 work 時仍是凍結的 `A:old`。（`ConfigRoleRepository.save` 在設定檔中寫入時也會這樣攤平，這是既有行為；新的地方是安裝時在使用者沒有操作的情況下觸發，而且觸發了也沒清到。）spec D4 寫的「只清理安裝當下作用中的設定（通常是一般設定，其他設定檔不動）」在這個情境並不成立。
- 建議修法：
  1. 最小修法：只在 `len(config.conf.profiles) == 1`（只有一般設定作用中，與 NVDA `_markWriteProfileDirty` 的判斷相同，`config/__init__.py:708-712`）時清理，否則記一行 log 後略過；加一個有兩個設定檔的測試（stub 加上 `profiles`）。
  2. 或直接刪一般設定的 ConfigObj：`config.conf.profiles[0].get("WorldVoice", {}).get("role", {})` 中鍵含 `_`／`-` 的 section 用 `del` 刪掉（ConfigObj `Section` 是 dict 子類別，一般設定一定會被 `save()` 寫出），不會攤平，也不需要 `_plainSection`。缺點是舊版這次執行期間 `AggregatedSection` 的快取仍是舊值；若舊版是本分支的測試版，在重新啟動前跑到 follow 或面板確定，可能把快取中的 `zh_TW` 寫回。
  - 建議第 1 種，並把 spec D4 的限制改成「只有一般設定作用中時才清理」。

#### N2（Minor）舊版 ≤ 6.1.1 在重新啟動前更換主要語音，會把 `zh_TW` 寫回

- 位置：`addon/installTasks.py:60-87`（只在安裝時執行一次）；舊版 `git show 6.1.1:addon/synthDrivers/WorldVoice/voiceManager.py` 248-257 行。
- 失敗情境（探針 C）：6.1.1 以前的版本每次更換主要語音（包括在 NVDA 語音面板換語音，或切到語音不同的設定檔時 `loadSettings` 重設語音）都會寫 `role[<完整地區>]` 和 `role[<主要語言>]`。使用者安裝後選「稍後重新啟動」，在重新啟動前換了語音，`zh_TW` 就回來了，結束時存檔，新版啟動後 I1 的情境重現；要等下一次更新 WorldVoice 才會再清。受影響的正是這個清理要照顧的族群（跳過 6.2 的使用者），但需要在安裝與重新啟動之間更換主要語音。
- 建議修法：不改程式，在 spec D4 的限制與修正記錄補上這一條，Windows 手動項目寫明「安裝後立刻重新啟動」與「稍後重新啟動且期間換語音」兩種情況的預期。若使用者要涵蓋這種情況，需要改成新版第一次啟動時清理，屬於使用者決定。

#### N3（Minor）`ConfigRoleRepository` 的 docstring 已不正確

- 位置：`addon/synthDrivers/WorldVoice/voices/roles.py:14`「The only reader and writer of config["WorldVoice"]["role"].」
- 現在 `installTasks._removeLegacyRoleKeys` 也會寫這個 section（而且刻意複製了 `_is_section`，因為安裝時只能用路徑載入）。建議改成「執行期間唯一的讀寫者；`installTasks._removeLegacyRoleKeys` 在更新安裝時移除舊的完整地區鍵」，並在 installTasks 的 `_isRoleSection` 旁註明對應 `roles._is_section`。純文件修正，成本很低。

### 修正記錄裡三個 Ruling 的評估

| Ruling | 評估 |
| --- | --- |
| (1) 只刪 `_`／`-` 鍵下的 section，scalar 保留 | 合理。沒有任何版本在 `role` 下寫過 scalar；`voice_for` 與 `assignments` 都忽略非 section，`save` 原樣保留（`roles.py:45-53`），清理採相同規則才一致。突變「scalar 也刪」會讓 `test_legacy_role_cleanup_keeps_scalars_and_odd_sections` 失敗，規則有測試釘住。 |
| (2) 只在更新時清理，首次安裝不清理 | 合理。`"WorldVoice" not in config.conf` 只有在沒有 confspec 且作用中的設定都沒有 `[WorldVoice]` 時才成立，那時沒有角色可清。解除安裝不會刪 nvda.ini 的 `[WorldVoice]`，所以重新安裝也會走更新分支、會被清理。探針 D 確認舊版停用（沒有 confspec）時清理照樣有效。 |
| (3) 不加更新日誌 | 大致同意。`master` 的 prune 在第一次更換主要語音（包括啟動時 `loadSettings`）就刪掉這些鍵，6.x 的使用者察覺不到差異。但要補充一點：v5.2.1 的語音角色面板同時列出完整地區與主要語言（`git show v5.2.1:addon/synthDrivers/WorldVoice/voiceManager.py` 250-259 行），5.x 使用者可能刻意設了 `zh_HK`（粵語）、`en_GB` 這類角色；這些會在安裝時被刪（`master` 是在第一次更換主要語音時刪，6.0 的更新日誌也沒提）。相對 `master` 不是回歸，列為下方的使用者可見預設，由協調者告知使用者。 |

### 新增的使用者還沒確認的使用者可見預設

1. 從 5.x 直接更新的使用者，在舊面板刻意設定的完整地區角色（例如 `zh_HK`、`en_GB`）會在安裝時刪除，沒有更新日誌（與 `master` 在第一次更換主要語音時刪除相同）。
2. N1：作用中的不是一般設定時的行為（建議改成略過）。
3. N2：舊版 ≤ 6.1.1 在重新啟動前更換主要語音會讓清理失效，直到下一次更新。

### 修正審閱者自行驗證的項目

| 項目 | 指令 | 結果 |
| --- | --- | --- |
| 完整測試（`73b625f` 的 scratch 複本，序列，記憶體監控沒有觸發） | `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests` | **3698 passed**，0 skipped，與修正記錄相同 |
| ruff | `ruff --version; ruff check --no-cache addon tests tools; ruff format --no-cache --check addon tests tools`（複本） | 0.16.3；All checks passed；246 files already formatted。沒有在 worktree 跑 `prek`，避免改到檔案 |
| 空白、受保護路徑、Neural | `git diff --check 73fbedd 73b625f`；§7 的 `git diff --stat master -- …` 與 `git ls-files …/driver/Neural` | 都沒有輸出 |
| commit 訊息 | `git log 73fbedd..73b625f --format=%B` | 7 個都是英文 `<type>: <summary>`，沒有 `Co-Authored-By` |
| I1 還原與突變（複本，`reverts.py`） | 拿掉 `else: _removeLegacyRoleKeys()`；scalar 也刪；不認 `-`；不轉 dict；沒有舊鍵也改寫；拿掉 try/except；改成只在首次安裝清理 → `tests/test_core_install.py` | 依序 3、1、1、1、1、1、3 failed |
| M1 還原 | `voice_for(language, of_engine)` → `voice_for(language)`，`tests/test_runtime_composition.py` | 1 failed：`'first:a' == 'first:b'` |
| M3 還原 | `_get_voice` 改回 `get_voice_name_for_language`，`tests/test_engine_setting.py` | 1 failed：`'A:a1' == 'B:b1'`（斷言，不是 `AttributeError`） |
| M4 突變 | `admits` 回 `True`；`voice_for` 忽略 `usable`；只查完整地區鍵 → Hypothesis 性質 | 三種都 1 failed |
| I1 探針（真實 `AggregatedSection` + configobj 5.0.9） | scratchpad `fixreview/probe/aggregated_probe.py` | A 只有一般設定：`zh_TW` 從寫出的設定消失，其他保留；B 有作用中的設定檔：一般設定沒變、設定檔多了 `legacy` 與 `zh` 的副本（N1）；C 舊版 6.1.1 的 follow 在清理後把 `zh_TW` 寫回（N2）；D 沒有 confspec 時照樣清理。拿掉 `_plainSection` 時寫出 `zh = <AggregatedSection object …>` |
| NVDA 安裝與儲存流程 | 讀 `addonHandler/__init__.py:528-568`、`gui/addonGui.py:237`、`addonStore/install.py:85`、`systemUtils.py:218-253`、`config/__init__.py:110-119, 708-738, 1155-1460`、`core.py:1085-1131` | 見上方「I1 對照 NVDA 原始碼的檢查」 |
| 舊版行為 | `git show 6.1.1:…/voiceManager.py`、`git show 78f3880^:…`、`git show v5.2.1:…/voiceManager.py`、`git grep '"role"' v5.2.1 6.0 6.1.1 6.2` | 6.1.1 的 follow 同時寫完整地區與主要語言；v5.2.1 面板列出完整地區；各版 `role` 的 confspec 都是 `{}`；各版 installTasks 都沒有 `onUninstall` |

未在 Windows／NVDA 上驗證；探針只重現 NVDA 的設定聚合邏輯，沒有跑真正的安裝流程與重新啟動。scratch 複本與探針放在 scratchpad 的 `fixreview/`，還原用的複本跑完即刪。

### 修正 review 新發現（N1–N3）的修正

修正基準：修正 review commit `e6e93a1`。

| 項目 | 處理 | commit | 測試 |
| --- | --- | --- | --- |
| N1 安裝時作用中的是其他設定檔 | 採建議修法 1：只在 `len(config.conf.profiles) == 1`（只有一般設定作用中，與 NVDA `_markWriteProfileDirty` 的判斷相同，`ref/nvda/source/config/__init__.py:708-712`）時清理；否則記一行 log「Legacy speech role keys not checked: a configuration profile is active」後略過，不寫任何設定。spec D4 的限制改為「作用中的不是一般設定時略過清理」。 | `a77347d`（程式與測試）、本表所在 commit（spec） | `tests/test_core_install.py::test_legacy_role_cleanup_is_skipped_while_another_profile_is_active`：修正前角色被改寫而失敗，修正後通過；測試 stub 的 `config.conf` 加上 `profiles`（預設只有一般設定） |
| N2 舊版在重新啟動前寫回 `zh_TW` | 不改程式，記為已知限制（spec D4）：6.1.1 以前的 WorldVoice 在重新啟動前仍在執行，期間更換主要語音會把 `zh_TW` 寫回，要到下一次更新才會再清理。 | 本表所在 commit（spec） | 無 |
| N3 `ConfigRoleRepository` docstring | 改為「執行期間唯一的讀寫者；`installTasks._removeLegacyRoleKeys` 在更新安裝時改寫一次以移除舊的完整地區鍵」；installTasks 的 `_isRoleSection` 註明對應 `roles._is_section`（因安裝時無法 import 而複製）。 | `7f0fae6`（docstring）、`a77347d`（註解） | 文件，無測試 |

Windows／NVDA 手動項目（取代前一節的那一條）：

1. 從帶有 `zh_TW` 角色鍵的舊設定更新安裝，沒有啟用其他設定檔，**安裝後立刻重新啟動**：`zh_TW` 鍵消失，`zh` 角色照常朗讀；NVDA log 有「Removed legacy speech role keys: ['zh_TW']」。
2. 同上，但安裝時手動啟用了其他設定檔：log 有「Legacy speech role keys not checked: a configuration profile is active」，設定沒有改變。
3. 同 1，但選「稍後重新啟動」，重新啟動前在 NVDA 語音面板換了主要語音（舊版 ≤ 6.1.1 仍在執行）：`zh_TW` 會被寫回，屬已知限制（N2），下一次更新時才會再清理。

驗證（修正後，worktree，序列）：`python3 -m pytest -q tests` **3699 passed, 0 skipped**（+1 N1）；`prek run --all-files` 8 個 hook 全部 Passed；`git diff --check master` 無輸出；兩個受保護路徑指令無輸出。未打包、未在 Windows／NVDA 驗證。
