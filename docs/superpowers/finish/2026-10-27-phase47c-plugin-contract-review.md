# Phase 47c Review：外掛契約改名

日期：2026-10-27。分支：`phase47c-plugin-contract`（`b7aede2..4ce740e`，9 個 commit；基準 `master` `b7aede2`）。
審閱者：Fable 5.1（唯讀；只新增本檔）。流程：一般流程加 §3.2「改名與搬移的證明」（DEVELOPMENT_WORKFLOW.md §3.3）。9 個 task 少於 10，沒有批次 review，本次是第一次也是唯一一次 review，看整個分支。

依據：

- 規則來源 `storage/refactor9.md` §6.1「外掛契約」段落、§6 的 P47c 列、§5.3 的 `VoiceFacade.update_settings` 與 `driver.Voice` 兩列。
- spec `docs/superpowers/specs/2026-10-27-phase47c-plugin-contract-design.md`。
- plan `docs/superpowers/plans/2026-10-27-phase47c-plugin-contract.md`。
- 進度帳本 `.superpowers/sdd/2026-10-27-phase47c-plugin-contract/progress.md`（git 忽略）。
- 守門測試 `tests/test_naming_layers.py`；契約測試 `tests/test_plugin_voice_contract.py`；discovery 測試 `tests/test_engine_discovery.py`。

使用者與協調者已決定、本次只核對實作的事項：六個契約名稱照宿主層規則改成 mixedCase（`synthDriverClass`、`extraCapabilities`、`drainProfile`、`createCore`、`destroyCore`、`updateSettings`）；不做相容層、不留別名；discovery 對仍用舊名的外掛記一筆清楚的錯誤 log（實作者採「略過該引擎」，使用者可推翻）；`ref/Neural/Neural/__init__.py:8` 的一行由協調者在 merge 時於主 checkout 修改，worktree 用本機 overlay 驗證；`TRANSITIONAL_47C` 刪除，只剩 `TRANSITIONAL_47D`（兩個 `script_` 名稱）與 `INTERFACE_NAMES`。**實作全部符合**，核對細節見「審閱者自行驗證的項目」。

## 結論

**Ready to merge：Yes。** Critical 0、Important 0、Minor 3。

- 5 個改名 commit 全部是純改名。用審閱者自己寫的檢查（`scratchpad/review47c/indep.py`：不讀任何 `OLD=NEW` 清單，從兩版 token 流依序比對**推導**出配對，再要求配對在整個 commit 內一對一且新名等於 mixedCase(舊名)、字串與註解只做整字替換、AST 平行走訪、註解依序比對、守門檔只能刪行）逐一重跑：每個 commit 只有推導出的那一組（Task 5 是兩組）在變，其他 token 的內容與順序完全不動，改名數和實作者的 `check.py` 完全一致（35／7／17／25／6）。改名後的檔案裡沒有任何舊名殘留（見「獨立改名證明」）。
- HEAD 上六個舊名的整字出現只剩 `engineRegistry/discovery.py:33-40` 的對照表和 `tests/test_engine_discovery.py` 的新測試；子字串只多出三個測試函式名（spec §3 的預設）。`getattr` 字串（`completionPolicies.py:60,80,82,120`、`engineAdapter.py:112`）、monkeypatch 目標字串、`test_native_strategy_guards.py` 的目標集合、docstring 與外掛可見的註解都已改名；突變 a2／a3 證明這些字串漏改會被既有測試抓到。
- discovery 的檢查（`a120123`）放在 `Voice.engine` 比對之後、`ready()` 之前、既有 `try` 之內，用 `hasattr` 看定義與繼承的名字，依對照表順序列出並 `continue`；其他引擎的順序與錯誤處理不變（同一次呼叫裡 `Fresh` 在 `Stale` 之後照常載入）。基底 `Voice` 與六個內建 wrapper 都沒有舊名（測試釘住；突變 a4／e 證明若有別名殘留會被抓到）。
- Neural 風格的外掛用新名稱仍能經由 manager 載入、`updateSettings` 設定、`activate`、`terminate`（`test_neural_style_plugin_runs_through_the_manager`）；真實 Neural 檔案在 overlay 下通過契約測試，還原成舊名就失敗（突變 b）。
- 守門終態正確：`TRANSITIONAL_47C` 連同所有引用都不在 `addon/`／`tests/`；docstring 第 33-34 行與 `test_only_stored_identifiers_wait` 一致；47D 被釘住只能縮小（突變 d1／d2）。
- 完整測試 3312 passed、0 skipped（基準 3303 + 9 個新測試）；`prek run --all-files` 8 個 hook 全部 Passed；`git diff --check master` 乾淨；受保護路徑無 diff、Neural 未被 track；9 個 commit 沒有 `Co-Authored-By`，沒有任何 commit 碰到 `ref`；worktree 的 `ref` overlay 和描述一致（7 個 symlink + 複製的 `Neural`，只有第 8 行不同，tab 縮排保留）。

## Critical

無。

## Important

無。

## Minor

### M1. 略過訊息對內建引擎也說「plugin」

- 位置：`addon/synthDrivers/WorldVoice/engineRegistry/discovery.py:188-193`。
- 內容：檢查對每個候選引擎都跑（internal 與 external 都會），訊息固定寫 `plugin uses the pre-rename contract name(s) …; update the plugin`。對外掛這是對的；但若將來某個內建 wrapper 回歸（例如 merge 時誤留 `extra_capabilities = extraCapabilities` 這種別名），NVDA log 會叫使用者「update the plugin」，而實際上要修的是 WorldVoice 本身。
- 失敗情境：突變 e（VE 多留一個 `extra_capabilities` 別名）在測試裡被 `test_naming_follows_layer` 與 `test_no_bundled_voice_defines_a_pre_rename_name` 抓到，所以不會出到使用者手上；只是訊息文字在那種情況下會誤導維護者。
- 建議：訊息帶上 `spec.source`，或改成中性的 `engine candidate uses the pre-rename contract name(s) … (built for an older WorldVoice; update it)`。對應更新 `tests/test_engine_discovery.py:217-219` 的 `STALE_MESSAGE`。成本極低，可不修。

### M2. 內建 wrapper 的舊名測試只看 `class Voice` 本體，看不到從 mixin 繼承的名字

- 位置：`tests/test_plugin_voice_contract.py:130-149`。
- 內容：`test_no_bundled_voice_defines_a_pre_rename_name` 用 AST 只讀每個 wrapper 的 `class Voice` body。執行期的檢查用的是 `hasattr`（`discovery.py:154-156`），會看到繼承來的名字。目前六個 wrapper 都直接繼承 `BaseVoice`，沒有 mixin，所以兩者一致；但若將來某個 wrapper 加了自己的 helper base 並在那裡定義（或忘了改名）`drain_profile`，discovery 會把該內建引擎整個略過，而這個測試不會失敗。
- 失敗情境：引擎從語音清單消失，log 只有 M1 的那一行；守門 `test_naming_follows_layer` 會抓到 snake_case 的定義（host 層），所以實務上還是會在 CI 失敗，但抓到的理由是命名規則，不是「這個引擎會被略過」。
- 建議：在已經載入真實 wrapper 類別的測試裡補一個執行期斷言，例如 `tests/test_native_strategy_guards.py` 或各 `test_*_segment_drain.py` 的 `env.outer.Voice`：`assert not any(hasattr(env.outer.Voice, name) for name in PRE_RENAME_CONTRACT_NAMES)`。或是讓 `test_no_bundled_voice_defines_a_pre_rename_name` 對 `composition` 已載入的 wrapper 類別用 `hasattr` 檢查，與 discovery 用同一個判斷。

### M3. merge 當下 `master` 的驗證順序：先改 Neural 的那一行，再跑完整測試

- 位置：`tests/test_plugin_voice_contract.py:71-88`（`test_reference_neural_plugin_uses_only_plugin_attributes` 直接讀 `REF / "Neural/Neural/__init__.py"`）；主 checkout `/workspace/WorldVoice/ref/Neural/Neural/__init__.py:8` 目前仍是 `synth_driver_class = SynthDriver`。
- 內容：這不是程式缺陷，是 merge 流程的順序。fast-forward 之後，主 checkout 的 `ref` 還是舊的 Neural，§7 的完整驗證會剛好失敗這 1 個測試（突變 b 就是這個情況：`1 failed, 6 passed`），直到協調者套用那一行。
- 建議：協調者在 merge 後、跑 §7 驗證之前先改 `ref/Neural/Neural/__init__.py:8`（指令與帳本 Task 1 相同的 `sed -i '8s/^\tsynth_driver_class = SynthDriver$/\tsynthDriverClass = SynthDriver/'`），並在回報裡寫明「master 3312 passed 是在 Neural 改完一行之後量的」。主 checkout `ref/Neural/Neural/__pycache__/` 裡的舊 `.pyc` 對這個 AST 測試沒有影響，不用處理。

## 審閱者自行驗證的項目

所有測試都在任務 worktree `/workspace/WorldVoice-phase47c`（含 `ref` overlay）或審閱者自己建的 detached 暫時 worktree（`scratchpad/review47c/mut`，另建等價 overlay）執行，序列跑，附 3 GB `MemAvailable` 看門狗（從未觸發）；沒有碰主 checkout，沒有用 `git stash`。

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 完整測試（任務 worktree，overlay 在位） | `review47c/suite.sh /workspace/WorldVoice-phase47c … tests`（序列＋看門狗） | **3312 passed、0 skipped**，96.5 s；與實作者回報一致，基準 3303 + 9 |
| `prek run --all-files` | 在任務 worktree | 8 個 hook 全部 Passed |
| `git diff --check master` | 任務 worktree | 無輸出 |
| 受保護路徑 | §7 的兩個指令 | 兩個都無輸出 |
| `ref` 是否被 stage 或 commit | `git log b7aede2..4ce740e --name-only` 過濾 `^ref/`；`git ls-files ref` | 0 筆；未被 track；`git status` 把 overlay 當 ignored |
| `ref` overlay 內容 | `ls -la ref`；`diff -r /workspace/WorldVoice/ref/Neural ref/Neural -x __pycache__`；`cat -A` | 7 個 symlink 指到主 checkout 的 `ref/*`，`Neural` 是目錄複本；差異只有第 8 行 `synth_driver_class` → `synthDriverClass`，tab 縮排保留 |
| 獨立改名證明 | `python3 -I review47c/indep.py <repo> <commit>` × 5 | 全部 `PURE RENAME OK`，詳見下節 |
| HEAD 舊名殘留（整字） | `git grep -nwE "<六個舊名>\|TRANSITIONAL_47C" -- addon tests tools …` | 只有 `discovery.py:34-39` 對照表、`test_engine_discovery.py:225-230,259-260,283`；`TRANSITIONAL_47C` 零筆 |
| HEAD 舊名殘留（子字串） | 同上去掉 `-w` 再排除整字 | 只有 3 個測試函式名（`test_driver_voice_base.py:55`、`test_runtime_completion_policies.py:278`、`test_runtime_legacy_adapter.py:121`） |
| 舊名在 `addon/`、`tests/`、`docs/` 以外 | `git grep -nwE … -- . ':!addon' ':!tests' ':!docs'` | 零筆 |
| 新名的呼叫點 | `git grep -nwE "<六個新名>" -- addon` | 定義在 `driver/__init__.py:25-27,87,91`、`voiceFacade.py:52`；呼叫在 `engineAdapter.py:72,108,112`、`completionPolicies.py:60,80,82,120`、`rolePresenter.py:76`、六個 wrapper；`voices/` 沒有呼叫（和 spec §2 相符） |
| discovery 檢查的位置與行為 | 讀 `discovery.py:154-201` | 在 `engine` 比對後、`ready()` 前、`try` 內；`hasattr` 含繼承；表序列出；`continue` 不呼叫 `ready()`；例外仍走原本的 `Failed to load ready state` |
| 其他引擎的順序與錯誤處理 | `test_old_contract_names_are_listed_together_and_inherited_ones_count`（`Stale` 後 `Fresh` 照常載入）；既有 `test_ready_engines_load_in_spec_order_with_timing`、`test_failures_are_logged_and_timed` 仍通過 | 不變 |
| 基底 `Voice` 與六個 wrapper 沒有舊名 | `test_pre_rename_names_map_onto_the_base_voice`、`test_no_bundled_voice_defines_a_pre_rename_name` 通過；突變 a4、e 反向確認 | 通過；反向都失敗 |
| Neural 風格外掛端到端 | `test_neural_style_plugin_runs_through_the_manager`（載入、`updateSettings`、`activate`、`terminate`） | 通過 |
| 真實 Neural（overlay） | `test_reference_neural_plugin_uses_only_plugin_attributes`；突變 b 把 overlay 第 8 行改回舊名 | overlay 通過；舊名時 `1 failed, 6 passed` |
| `PLUGIN_VOICE_ATTRIBUTES` | `tests/test_plugin_voice_contract.py:14` | `{"core", "engine", "synthDriverClass", "extraCapabilities", "drainProfile"}`，與 spec §7 相同 |
| 守門終態 | 讀 `tests/test_naming_layers.py:1-36,128-133,384-408`；`git show 0bb9148` | docstring 只提 `TRANSITIONAL_47D`；兩個 `_listed()` 只讀 `INTERFACE_NAMES, TRANSITIONAL_47D`；47D 只有 `script_popup_SpeechSettingsDialog`、`script_switch_log_record`；`test_only_stored_identifiers_wait` 以 `<=` 釘住；`INTERFACE_NAMES` 未變 |
| 47b 的 M2（別名基底自我測試） | `test_the_guard_follows_a_base_imported_under_an_alias` 在 HEAD 存在 | 存在，通過 |
| 各 commit 的守門檔只刪不加 | `indep.py` 的 guard 檢查 | a588ddb −1、7c55913 −1、c4e1653 −1、6882c35 −4、20883e5 −5/+1（+1 是 ruff 把清空的 dict 收成一行，對應的 `= {` 行同時被刪） |
| commit 衛生 | `git log --format=%b` 搜 `Co-Authored` | 零筆；9 個 commit 都有 `<type>: <summary>` 與說明內文 |
| `4ce740e` 只動空白 | `git diff -w --quiet 4ce740e~1 4ce740e` | 是，只有 plan 的縮排 |
| readme 是否寫到外掛契約 | `grep -niE "synth_driver\|extra_capab\|drain_profile\|create_core\|destroy_core\|update_settings\|plugin\|workspace\|外掛\|插件\|плагин\|плагін\|Neural\|driver package"` 於 `readme.md` 與 `addon/doc/{ru,uk,zh_CN,zh_HK,zh_TW}/readme.md` | 只有 `zh_CN:3`「NVDA 插件」（= add-on）；`readme.md:87` 只說其他引擎要另外下載驅動；沒有外掛 how-to；實作者的結論正確 |
| 突變測試（13 種） | `review47c/mutate.sh`，在 scratch worktree 逐一套用、跑對應測試、還原 | 全部被抓到，見下表 |
| scratch worktree 清理 | `git worktree remove` | 已移除，`git worktree list` 回到原本的 7 個 |

### 突變測試

| # | 突變 | 抓到的測試 |
| --- | --- | --- |
| a1 | Espeak `drainProfile` 定義改回 `drain_profile` | `test_naming_follows_layer`、`test_no_bundled_voice_defines_a_pre_rename_name`、`test_runtime_completion_policies` 3 個 Espeak 案例（5 failed） |
| a2 | `completionPolicies.py:120` 的 `getattr` 字串改回 `"drain_profile"` | `test_runtime_completion_policies` 55 failed（DRAIN 全部退回 LEGACY_DONE） |
| a3 | `engineAdapter.py:112` 的 `getattr` 字串改回 `"extra_capabilities"` | `test_waitfactor_updates_declared_capability_without_activating`、`test_real_variant_and_waitfactor_hooks[VE/Cerence]`（3 failed） |
| a4 | 基底 `Voice` 多留 `synth_driver_class = None` 別名 | `test_naming_follows_layer`、`test_pre_rename_names_map_onto_the_base_voice` |
| b | overlay 的 Neural 第 8 行改回 `synth_driver_class` | `test_reference_neural_plugin_uses_only_plugin_attributes` |
| c1 | 刪掉 discovery 的整段 stale 檢查 | 6 個 parametrized 案例 + 繼承案例（7 failed） |
| c2 | `hasattr` 改成 `name in vars(voice)`（看不到繼承） | 繼承案例 1 failed |
| c3 | 檢查搬到 `ready()` 之後 | 7 failed（`asked == []` 斷言） |
| c4 | `logger.error` 改 `logger.warning` | 7 failed |
| c5 | 對照表少了 `update_settings` | parametrized `update_settings` 案例、`test_pre_rename_names_map_onto_the_base_voice`（`len == 6`） |
| d1 | 重新加入 `TRANSITIONAL_47C`（含一筆已不存在的名字）並接進兩個 `_listed()` | `test_lists_hold_only_names_that_break_the_rule` |
| d2 | `TRANSITIONAL_47D` 多一個 `script_` 名字 | `test_lists_hold_only_names_that_break_the_rule`、`test_only_stored_identifiers_wait` |
| e | VE 的 `Voice` 多留 `extra_capabilities = extraCapabilities` 別名 | `test_naming_follows_layer`、`test_no_bundled_voice_defines_a_pre_rename_name` |

### plan 的 Review Focus

| # | 項目 | 核對 |
| --- | --- | --- |
| 1 | `getattr` 字串漏改會靜默失敗 | 突變 a2、a3；HEAD 整字 grep 零殘留 |
| 2 | 檢查誤判會略過所有引擎 | 突變 a4；`test_pre_rename_names_map_onto_the_base_voice` |
| 3 | 從 helper base 繼承或多個舊名要一次列出、在 `ready()` 前 | 突變 c2、c3；`test_old_contract_names_are_listed_together_and_inherited_ones_count` |
| 4 | Neural 的 `core = None` 遮住 facade property 後仍能 `updateSettings`／terminate | `test_neural_style_plugin_runs_through_the_manager` 通過（`voice.core is None` 斷言在 `:52`） |
| 5 | 真實 Neural 一行改動前紅、改動後綠 | 突變 b（紅）；worktree overlay（綠） |

## 獨立改名證明

工具：`scratchpad/review47c/indep.py`（審閱者自寫，和實作者的 `p47c/check.py` 無共用程式碼）。方法：對 commit 碰到的每個檔案，兩版 token 流去掉 `NL` 與 ruff 的結尾逗號後必須等長；NAME token 的差異收集成配對，整個 commit 的配對必須一對一而且新名 = mixedCase(舊名)；STRING／COMMENT token 只能是舊名整字換成新名；其他 token 型別與文字必須相同；另做 AST 平行走訪（identifier 欄位、字串常數、`names` 清單）與註解依序比對，並要求 token 改名數 = AST＋註解改動數；守門檔只能刪行（或 ruff 把空 dict 收成一行）。最後列出新版檔案裡所有舊名殘留。

| commit | 推導出的配對 | 檔案 | 改名 token | 模式 | 殘留 |
| --- | --- | --- | --- | --- | --- |
| `a588ddb` | `synth_driver_class → synthDriverClass` | 20（+守門 −1 行） | 35 | 全部 tokens+AST | 0 |
| `7c55913` | `extra_capabilities → extraCapabilities` | 7（+守門 −1 行） | 7 | 全部 tokens+AST | 0 |
| `c4e1653` | `drain_profile → drainProfile` | 12（+守門 −1 行） | 17 | 全部 tokens+AST | 0 |
| `6882c35` | `create_core → createCore`、`destroy_core → destroyCore` | 12（+守門 −4 行） | 25 | 全部 tokens+AST | 0 |
| `20883e5` | `update_settings → updateSettings` | 6（+守門 −5/+1 行） | 6 | 全部 tokens+AST | 0 |

五個 commit 都是 `PURE RENAME OK`；沒有任何檔案需要退到「AST only」模式（ruff 沒有重排任何一行）；每個檔案的 token 改名數和 AST＋註解改動數相等。配對與使用者決定的六組完全相同，沒有多出任何配對。完整輸出在 `scratchpad/review47c/indep_results.txt`。

## Ruling 評估

| Ruling | 評估 |
| --- | --- |
| 三個測試函式名保留舊字（`…_synth_driver_class`、`…_drain_profiles`、`…_destroy_core_fails`） | 合理。測試在命名規則之外（`test_naming_layers.py:10-11`），名字讀起來是英文片語；改成 camelCase 反而會讓 snake_case 的測試名混入駝峰。子字串 grep 剛好 3 筆，和帳本一致。列為未確認預設。 |
| 契約測試在 stub 套件下載入 `engineRegistry/discovery.py`（`test_plugin_voice_contract.py:112-116`） | 合理。真正的 `engineRegistry/__init__.py:10-21` 在 import 時就 `addonHandler.initTranslation()` 並掃描磁碟，`composition` fixture 沒有 stub 這些；`stub_modules.package` 只是給一個 `__path__`，讀的還是同一個 `discovery.py`，表內容不可能和執行期不同。`discovery` fixture（`test_engine_discovery.py:15-22`）本來就是這樣做。 |
| `_pre_rename_contract_names` 放在 `load_enabled_engine_classes` 正上方、表放在 `_LOG` 下方 | 合理，閱讀順序；無風險。 |
| Task 5 守門檔用行號刪錯、還原後改用內容刪除 | 已核對：`6882c35` 的守門 diff 只有 4 行刪除、0 行新增，刪的正是 `Voice.create_core`／`Voice.destroy_core` 那組；帳本有記紅燈重做。流程事件，沒有留下錯誤。 |

## 使用者還沒確認的使用者可見預設

1. **略過 vs 載入舊契約的外掛**（spec §5、§11-1）：目前 discovery 對仍用舊名的外掛記一筆 error log 並**略過**，不呼叫 `ready()`，語音不出現在清單。另一個選項是照常載入，讓它在 `VoiceClassAdapter.open` 失敗（`engine Neural on error` 加 traceback）；對使用者的結果一樣是語音消失，只是 log 較不清楚，而且 `extraCapabilities`／`drainProfile` 用舊名時會靜默失去 waitfactor／variant 或退回 LEGACY_DONE。審閱者同意「略過」。
2. **changelog 是否告訴 Neural 使用者要一起更新 Neural**（spec §8、§11-3）：目前六份 readme 都沒有改。`readme.md:91` 有「## Next update」段落可放一行；refactor9 §6.1 明寫「WorldVoice 和 Neural 必須一起發布」，審閱者**建議加一行**（例如「Neural 外掛需同時更新到支援 `synthDriverClass` 的版本，舊版 Neural 會被略過並在 NVDA log 記錄原因」），六種語言照 readme-all-languages 的規則同步；可在發布時再補。
3. 三個測試函式名保留舊字（spec §3、§11-2）。
4. 檢查的涵蓋範圍（spec §5 已明寫）：只看外掛 `Voice` **定義或繼承**的名字；外掛方法本體裡**呼叫**舊名（例如自己的 `createCore` 裡 `super().create_core()`，或 `self.update_settings(...)`）不會在 discovery 被發現，會在執行到時以 `AttributeError` 失敗、由 manager 記 `engine X on error`。目前唯一的外掛 Neural 沒有方法，不受影響。
5. M1 的訊息措辭（對內建引擎也說 plugin）。

## 未在 Linux 驗證的項目

- NVDA 本身、實際音訊裝置、引擎 SDK 都沒有載入；舊版 Neural 搭新版 WorldVoice 時 NVDA log 出現 §5 那一行、其他引擎照常載入，以及更新後 Neural 語音回到清單，要在 Windows 手動確認（spec §9 最後一點）。本 phase 未打包。

## 修正記錄

依 DEVELOPMENT_WORKFLOW.md §3.4 的一般流程修正；本輪只有 Minor，不做修正 review。

| 項目 | 處理 | commit |
| --- | --- | --- |
| M1 略過訊息對內建引擎也說「plugin」 | 已修。訊息依候選引擎的 `spec.source` 區分：WorldVoice-workspace 的引擎（`external`）維持 `plugin uses the pre-rename contract name(s) …; update the plugin`；內建引擎（`internal`）改成 `bundled engine uses the pre-rename contract name(s) …; update WorldVoice`。先改測試：`test_plugin_with_old_contract_names_is_reported` 改用 `external` 的 spec，`test_old_contract_names_are_listed_together_and_inherited_ones_count`（內建 spec）改斷言 bundled 訊息，修正前紅燈只有後者（訊息仍是 plugin），修正後綠燈。 | `df244b5` |
| M2 內建 wrapper 的舊名測試看不到繼承來的名字 | 已修。`tests/test_runtime_completion_policies.py` 新增 `test_six_loaded_voices_pass_the_pre_rename_check`（六個引擎各一），用既有的 `load_installed_engine` 載入真實 wrapper，再以 discovery 同一個判斷 `_pre_rename_contract_names`（`hasattr`）檢查 `outer.Voice`；discovery 模組以 stub 套件載入，不跑 `engineRegistry/__init__.py`。探針：在暫時的 worktree 讓 Espeak 的 `Voice` 多繼承一個帶 `drain_profile = None` 的 mixin，AST 測試 `test_no_bundled_voice_defines_a_pre_rename_name` 仍通過（缺口），新測試失敗 `assert ['drain_profile'] == []`；探針 worktree 用完已移除。 | `0c90418` |
| M3 merge 時先改 Neural 那一行再驗證 | 不需修改程式；屬於協調者的 merge 步驟（主 checkout `ref/Neural/Neural/__init__.py:8` 改成 `synthDriverClass = SynthDriver` 後再跑 §7）。 | — |

修正後驗證（worktree 的 Neural overlay 在位）：完整測試 3318 passed、0 skipped（3312 + M2 新增的 6 個）；`prek run --all-files` 全部 Passed；`git diff --check master` 無輸出；兩個受保護路徑指令皆無輸出。
