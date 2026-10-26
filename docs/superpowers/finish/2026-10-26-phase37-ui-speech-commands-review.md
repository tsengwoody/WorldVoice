# Phase 37 Review 紀錄：`ui/` 套件與 `speechCommands.py`

日期：2026-10-26。分支：`phase37-ui-speech-commands`（`1f7fa46..ced33e5`，5 個 commit：2 個 docs（spec、plan）、2 個 refactor、1 個 docs（docstring）），worktree `/workspace/WorldVoice-phase37`。
依據：

- 規格 `docs/superpowers/specs/2026-10-26-phase37-ui-speech-commands-design.md`
- 計畫 `docs/superpowers/plans/2026-10-26-phase37-ui-speech-commands.md`（4 個 task、45 個 `Edit:` 區塊，Review Focus 5 項，每個 commit 都記了 `HEAD:addon`／`HEAD:tests` tree id，檔尾有 dry run 紀錄）
- 進度帳本 `.superpowers/sdd/2026-10-26-phase37-ui-speech-commands/progress.md`（4 條 `Ruling:`；`.superpowers/` 被 git 忽略，不在 commit 裡）
- 路線圖 `storage/refactor8.md` §2.3（F3）、§2.7（F7）、§2.11（F11 的 `worldvoice_synth`）、§4.2（A2）、§6「階段 37」
- `DEVELOPMENT_WORKFLOW.md` §3.3、§4.5（複雜流程：在 scratch 複本重放 plan、比對 tree id）、§4.6、§7、§8

流程：審閱者 Fable 5.1，唯讀。plan 重放在 scratchpad 的全新 clone（`git clone /workspace/WorldVoice`，checkout `1f7fa46`，`ref` symlink，`prek install`）上用我自己寫的套用器進行（只解析 plan 的 `### Task N:`／`- [ ] **Step S:`／`**Edit:**` 標記，和實作者的 helper 互不相依），bash 區塊照 plan 原樣執行；突變探針、順序與洩漏檢查在另一個 scratch clone（分支 `ced33e5`）進行；審完兩個 clone 都刪除。pytest 單一行程，外層有 MemAvailable < 3 GB 就停掉的看門狗（全程沒有觸發）。沒有 push、沒有 stash、沒有動主 checkout、沒有修改分支上的原始碼或測試；本文件是審閱者在任務分支上唯一的 commit。

`file:line` 以 `ced33e5` 為準；`WV/<path>` = `addon/synthDrivers/WorldVoice/<path>`。

## 結論

Ready to merge：**是，但 merge 前要先處理 I1**（`master` 已經不在 plan 的基準上，不能 fast-forward；是流程問題，不是程式問題）。Critical 0、Important 1、Minor 5。

- **純搬移成立，沒有 plan 以外的修改。** 我在全新 clone 上從 `1f7fa46` 照 plan 逐步重放（45 個 `Edit:` 區塊逐位元組套用、`git mv`／`mkdir`／commit 區塊原樣執行），三個 commit 的 tree id 全部和 plan、和分支一致（表格「plan 重放」）；`git diff <重放 HEAD> ced33e5 -- addon tests pyproject.toml` 沒有輸出。由此可知分支上 `addon/`、`tests/`、`pyproject.toml` 的每一個位元組都來自 plan。兩個 docs commit（`2fffc87`、`3800db3`）只動 `docs/`。
- **行為沒有變。** `addon/` 的 diff 只有：4 個 `..speechCommands` import 行（isort 把它移到 `..runtime.…`／`..numberLanguage` 之後）、`__init__.py:58` 一行、`speechSettingsDialog.py:19-30` 的兩組 import、`ui/voicePanel.py:7-21` 的三組 import、`ui/controls.py:7` 的 docstring 和 `:16` 的 import、`pipeline/context.py:25-31` 的 docstring、新的 0 位元組 `ui/__init__.py`。`_speechcommand.py → speechCommands.py` 與 `pipeline/panelLayout.py → ui/panelLayout.py` 是 100% 相似度的純改名；`pipelineControls.py → ui/controls.py`（97%）、`VoiceSettingsDialogs.py → ui/voicePanel.py`（98%）的差異只有上述 import 行與 docstring。class／function／attribute 名稱一個都沒改；`runtime/`、`driver/`、`text/`、`voices/` 零變動；`tests/test_plugin_voice_contract.py` 零變動。公開路徑（`synthDrivers.WorldVoice.driver`、`runtime.*`、`text.*`、`driver.sonic`）都在原位。
- **NVDA 載入路徑。** `WV/__init__.py:58` 改從 `.ui.voicePanel` 匯入 `WorldVoiceVoiceSettingsPanel`，`:209` 的 `patch_attribute(gui.settingsDialogs, "VoiceSettingsPanel", WorldVoiceVoiceSettingsPanel)` 一字未改——第二個參數是 NVDA 的屬性名，不是模組路徑；拿到的是 class 物件，`Teardown` 還原機制不變。synth 套件 import 時載入的模組集合和以前相同（`VoiceSettingsDialogs` 本來就在 `__init__.py` 頂層被 import，連帶 `pipelineControls`），沒有從 lazy 變 eager 的東西；只是 `.ui.voicePanel` 排到 `.voices.*` 之前，而 `voicePanel` 不需要 `voices`。`ui/voicePanel.py:7` 的 `..pipeline.settings` 深度正確（`tests/test_voice_settings_panel.py`、`test_settings_order.py` 用 alias 套件 `synthDrivers.WorldVoice.ui` 載入真檔，相對 import 真的被解析過）。全域外掛 `speechSettingsDialog.py:19-30` 的兩個新路徑由 `tests/test_pipeline_panels.py`、`test_role_panel.py`、`test_unicode_panel.py` 載入真檔驗證。`tests/test_runtime_composition.py:624` 以 stub `ui.voicePanel` 跑真正的進入點，綠。
- **沒有 import 週期、沒有新的 import 時副作用。** `pipeline/`、`runtime/`、`bridge/`、`voices/` 都沒有任何 `ui` 的 import（grep）；`ui.voicePanel → ui.controls → ui.panelLayout`、`ui.voicePanel → ..pipeline.settings`，`panelLayout.py:8-9` 只 import `collections.abc` 與 `typing`。`addonHandler.initTranslation()` 在 `ui/voicePanel.py:25` 與 `speechSettingsDialog.py:35` 都仍在所有 import 之後，三個搬移的模組沒有 `_(`（grep 無結果），所以 isort 改序對 `_` 沒有影響；兩處被改序的 import 所載入的套件（`pipeline`）在 NVDA 裡早就被更前面的 import 載入（`__init__.py:36`、`speechSettingsDialog.py:16`）。`bridge/completionPolicies.py:75`、`engine/__init__.py:20` 的 `__package__.rsplit` 算路徑不受影響（`bridge`、`engine` 深度沒變）。NVDA 自己也有頂層模組 `ui`（`globalPlugins/WorldVoice/__init__.py:7` `import ui`）：Python 3 沒有隱式相對 import，`WV/` 目錄也不在 `sys.path`（`__init__.py:67` 放的是 add-on 根目錄），所以 `import ui` 仍是 NVDA 的；`check-case-conflict` hook 也過。
- **沒有殘留舊路徑。** `git grep -E "_speechcommand|pipelineControls|VoiceSettingsDialogs|pipeline\.panelLayout|pipeline/panelLayout" -- . ':!docs'` 無輸出；`sconstruct`、`buildVars.py`、`manifest*.tpl`、`.pre-commit-config.yaml`、`pyproject.toml`、`.github/` 裡沒有任何按檔名列舉這些模組的地方，只有 `pyproject.toml:55-56` 的 mutmut `source_paths`，已跟著搬。`buildVars.py:60-66` 的 `pythonSources` 是 glob（`synthDrivers/*/*.py`、`synthDrivers/*/*/*.py`），`ui/*.py` 在兩層內，翻譯來源不受影響；本階段也沒有新增或改動 UI 字串。add-on 裡用字串算模組名的只有 `engine/discovery.py:104` 與上述兩處 `__package__`，都和搬移的檔案無關。
- **測試數量算得對。** 基準 3224，分支 **3225 passed、0 skipped**，多的一個就是 A2 守衛。
- **A2 守衛真的抓得到錯誤。** 11 個突變中 9 個紅（表格「突變探針」），紅的原因和 spec §5.4 預期一致：`ui/__init__.py` import `controls` → `import of wx halted`；import `..pipeline.settings` → `import of config halted`；`panelLayout` import `wx`／`gui` → halted；import `..numberLanguage`／`..locales` → 載入集合斷言失敗；import `languageHandler`／`tones`／NVDA 的 `ui` → `No module named`。兩個綠的是 `import re`（stdlib，本來就允許）和 `ui/__init__.py` 寫 `from . import panelLayout`（見 M1）。
- **A2 守衛不洩漏。** 自寫的 pytest plugin 在每個測試前後比對 `sys.modules`：守衛與 11 個鄰居測試檔（288 個測試）正向、反向各跑一次，以及「守衛 → voice panel 測試 → 整個 `test_ui_structure.py`」的組合，都沒有新增的 `synthDrivers*` 項目、沒有殘留的 `None` 項目、沒有被移除的 `synthDrivers*` 項目。整個套件在同一個 plugin 下跑：守衛與本階段動到的任何測試都不洩漏；有 8 個**既有**測試（5 個本階段沒碰的檔案：`test_engine_segment_contract.py`、`test_generate_unspaced_common.py`、`test_runtime_completion_policies.py`、`test_runtime_drain_integration.py`、`test_vocalizer_segment_drain.py`）會把 `synthDrivers.WorldVoice.*` 模組留在 `sys.modules`（見 M5），但沒有任何一個留下 `ui*`，而守衛一開始就用 monkeypatch 刪掉所有 `synthDrivers*` 快取，所以不受影響（順序無關，實測正反向都綠）。
- **執行緒與鎖：** 本階段沒有碰任何鎖、callback 或執行緒程式碼。
- **翻譯：** 無 UI 字串變動，無需翻譯。
- **§8：** 5 個 commit 都是英文 `<type>: <summary>`、內文說明原因、0 個 `Co-Authored-By`；沒有碰 `driver/<Engine>/driver/`、`driver/sonic/`、`script_data.py`、`unspaced_common_data.py`、Neural；`git diff --check master` 乾淨；`prek run --all-files` 全數 Passed 且沒改檔。

## Critical

無。

## Important

### I1. `master` 已經離開 plan 的基準，`master:addon` 不同，§4.6 的條件成立，且無法 fast-forward

- 位置：plan 開頭 `**Base:** master 1f7fa46`；`master` 現在是 `71748c1`（`docs: align the user guides and update the translations`），動了 `addon/doc/*/readme.md`、`addon/locale/*/nvda.po`、`readme.md`。
- 現象：`git rev-parse master:addon` = `ac54467f…`，plan 的基準是 `9d4a7b01…`；`master:tests` 仍是 `85401e92…`。§4.6 寫「`master` 動到 `addon/` 或 `tests/` 時，以新的 `master` 為基準重新做 dry run，更新 plan 裡的所有 tree id」，條件在字面上成立；§3.5 的 `merge --ff-only` 也會失敗，必須先 rebase。
- 我已經在 scratch clone 做了 rebase 驗證：`git rebase 71748c1` 無衝突（`master` 的那個 commit 和本階段動的檔案完全不重疊）；`git diff 71748c1 <rebased>` 與 `git diff 1f7fa46 ced33e5`（都限 `addon tests pyproject.toml`）**逐位元組相同**（586 行）。rebase 後的 tree id：`HEAD:addon` = `0ce05e80f67d077c311702467f09befadba10bd5`、`HEAD:tests` = `08f6907fb671bfcf0badeafd32664dcba29d8369`（tests 不變，因為 `master` 沒動 `tests/`）。
- 失敗情境：直接 `--ff-only` 會被拒；若改用 merge commit 或 rebase 但不更新 plan，plan 記的最終 tree id 就不再對應 `master` 上任何 commit，下一個 phase 以「plan 記的 tree id」當基準時會對不上。
- 建議修法（擇一；我建議第一個，因為內容相等已由上面的位元組比對證明，重做整個 dry run 不會多得到資訊）：
  1. 協調者在 worktree `git rebase master`，確認 `git rev-parse HEAD:addon HEAD:tests` 等於 `0ce05e80…`／`08f6907f…`，重跑 §7 全套驗證，然後在 plan 檔尾加一段「## 基準更新」記下新基準 `71748c1`（`addon` `ac54467f…`、`tests` `85401e92…`）與三個 commit rebase 後的 `HEAD:addon`（Task 1、2 的新 id 要在 rebase 後用 `git rev-parse <sha>:addon` 讀出來；Task 3 即上面的值），再 `--ff-only` merge。
  2. 照 §4.6 字面：以 `71748c1` 為基準重新 dry run、改 plan 的全部 tree id、重新落地。

## Minor

### M1. `ui/__init__.py` 必須為空（spec §2.1、§4）沒有測試守著

- 位置：`tests/test_ui_structure.py:122-147`（A2 守衛）；對照 `tests/test_runtime_import_guard.py:58`，phase 36 修正時已經為 `bridge/__init__.py`、`voices/__init__.py` 加了 `read_bytes() == b""` 的斷言，`ui` 不在其列。
- 現象：在 `ui/__init__.py` 寫 `from . import panelLayout`，A2 守衛 **1 passed**（載入集合仍是那四個名字）。這對「不用 wx 也能載入」無害，但 spec 說 `__init__.py` 必須保持空白，而 `__init__` 一旦開始 re-export，下一個加 `controls` 的人就會把 wx 帶進來（那一步守衛會抓到）。
- 建議：把 `tests/test_runtime_import_guard.py:58` 那個斷言的參數加上 `"ui"`（一行），或在 A2 守衛末尾加 `assert (WORLDVOICE / "ui/__init__.py").read_bytes() == b""`。只動 `tests/`，`HEAD:tests` 會變，依 §4.5 補「## 修正」段落。

### M2. A2 守衛只擋 7 個名字，其餘 NVDA 模組靠「Linux 上不存在」才紅

- 位置：`tests/test_ui_structure.py:130-131`。
- 現象：`panelLayout` 若 import `languageHandler`、`tones`、`core`、`queueHandler`、NVDA 的 `ui`、`globalVars`、`nvwave`、`api`，守衛會紅，但原因是 `No module named …`，不是 `None in sys.modules`；只要有哪個測試把這些名字的 stub 留在 `sys.modules`（非 monkeypatch 寫入），守衛就會被遮住。我在整個套件跑完後檢查 `sys.modules`，目前沒有這類殘留（表格「殘留 stub」），所以今天是安全的，但這個保證來自別的測試的衛生，不是守衛自己。
- 建議：把 `tests/runtime_harness.py:210-225` `forbidden` 集合裡的 NVDA 名字（`languageHandler`、`globalVars`、`nvwave`、`winKernel`、`api`）加進守衛的 `None` 清單，或直接讓兩個測試共用一份常數。不擋 merge。

### M3. spec §5.5 說 `wx` 已在 runtime 守門的禁止清單裡，實際上沒有

- 位置：spec §5.5「`ui/` imports `wx`/`gui`, already forbidden」；`tests/runtime_harness.py:210-225` 的 `forbidden` 有 `gui`、沒有 `wx`。
- 現象：文件和程式不一致。效果上沒差：`ui/controls.py:13` 的 `import wx` 在 Linux 上本來就 `ModuleNotFoundError`，`:14` 的 `gui` 會被守門擋；`ui.panelLayout` 是純 Python，runtime 若去 import 它守門不會叫，但那也不是這個守門要擋的邊界。
- 建議：spec 改成「`gui`, already forbidden」，或順手把 `wx` 加進 `forbidden`。只是文件修正。

### M4. 測試 helper 名稱 `load_voice_settings_dialogs` 指的檔案已不存在

- 位置：`tests/ui_harness.py:815`（docstring 已改成 `ui/voicePanel.py`，函式名未改）；`tests/` 內 15 處引用。
- 現象：帳本 Ruling 2 刻意保留（名字描述角色、改名只增加 churn）。我同意不在本階段改，但 "dialogs" 這個字現在既不對應檔名也不對應內容（一個 Panel）。
- 建議：留給階段 39（命名收尾）一併處理為 `load_voice_panel`；不必在本階段改。

### M5. 既有的 8 個測試把 `synthDrivers.WorldVoice.*` 模組留在 `sys.modules`（不是本階段造成）

- 位置：`tests/test_engine_segment_contract.py::test_completed_segment_drains_once_on_the_delivery_thread[VE|Cerence|OneCore]`、`tests/test_generate_unspaced_common.py::test_unspaced_codes_follow_the_pipeline`、`tests/test_runtime_completion_policies.py::test_actual_outer_voice_and_core_select_enabled_drain_profiles[…]`（2 個）、`tests/test_runtime_drain_integration.py`、`tests/test_vocalizer_segment_drain.py`（各 1 個）。這 5 個檔案本階段都沒動。
- 現象：測試結束後 `sys.modules` 多出 `synthDrivers.WorldVoice.runtime.*`、`.bridge.completionPolicies`、`.pipeline.*`、`.languageDetection.*`、`.driver.VE.driver.ve2*` 等真實模組（不是 stub）。沒有 `None` 項目，沒有 `ui*`。A2 守衛不受影響（它先清掉所有 `synthDrivers*`），其他 harness 也多半先 `delitem`，所以今天沒有測試因此失敗；但這是 `addon_loader` docstring 所宣稱「one test's module state never reaches another」的例外。
- 建議：不在本階段處理（與 spec 無關）。可列入 phase 29／測試衛生的待辦：讓這幾個測試改用 `alias_package`＋`monkeypatch`，或加一個 autouse fixture 在測試後清掉新增的 `synthDrivers*`。

## 帳本 `Ruling:` 的評估

| # | Ruling | 評估 |
| --- | --- | --- |
| 1 | `worldvoice_synth()` 留在 `pipeline/context.py`，只改 docstring | **合理。** 依賴方向是決定性理由：`current_context()`（`WV/pipeline/context.py:34-41`）每一句話都經過它，搬到 `ui/` 會讓 pipeline import 設定 UI（進而 wx）。獨立根模組的替代方案確實省不到任何 import：`speechSettingsDialog.py:16-17` 已經 import `pipeline` 與 `pipeline.context`。`tests/test_pipeline_structure.py:154-166` 把 `context.py` 當成 pipeline 唯一能碰 synth 的地方，這個守衛和 `test_lint_rewrites::test_worldvoice_synth_returns_only_worldvoice` 都未改、都綠。路線圖 §2.11 原本建議「移到 `ui/` 或根目錄」，spec §5.3 說明了為什麼兩個都不選，理由成立。 |
| 2 | helper／fixture 名稱保留（`load_voice_settings_dialogs`、`load_pipeline_controls`、`speechcommand`） | 合理，spec §3 non-goal 也這麼寫；見 M4 的後續建議。`load_pipeline_controls` 與 `speechcommand` 仍然描述得對。 |
| 3 | A2 守衛放在 `test_ui_structure.py`，用 `sys.modules` 設 `None` 擋 7 個名字、alias `synthDrivers`／`synthDrivers.WorldVoice`、精確比對載入集合 | **設計合理，不會太脆也不會太弱，有兩個小缺口（M1、M2）。** 不脆：集合裡只有 4 個名字且全由守衛自己造成；守衛先清掉所有 `synthDrivers*` 快取，所以不受前面測試影響（正反向、重複執行都綠）；mutmut 的 trampoline 只 import stdlib，不會多出 `synthDrivers*` 模組。不弱：精確集合斷言抓到了「純 Python 的 add-on 模組」（`..numberLanguage`、`..locales`），這是 None 擋法做不到的，Ruling 說的 "catches add-on imports that need no NVDA" 實測成立。alias 而不跑真正的 synth `__init__.py` 是所有 harness 的既有做法，別無選擇（真 `__init__` 需要整個 NVDA）。`finally` 裡手動 pop 兩個模組是必要的（它們是 import 系統自己註冊的，monkeypatch 不知道），洩漏檢查證實乾淨。 |
| 4 | 「`ui/__init__` import `controls` 會紅」是未提交的檢查（Task 2 Step 6） | 合理：一個已提交的測試不能安全地改寫追蹤中的原始檔。我在重放裡照做：`1 failed`、`import of wx halted; None in sys.modules`（`ui/controls.py:13`），還原後 `6 passed`、`test ! -s ui/__init__.py` 成立。dry run 紀錄裡提到第一次因 `bash -e` 在這一步中斷而把 `from . import controls` 帶進 commit，plan 已用 `\|\| echo` 修正；重放證實修正後的區塊一次過。另見 M1：這個檢查只證明「import controls 會紅」，不證明「`__init__` 非空會紅」。 |

## plan 的 Review Focus 逐項

1. **NVDA 的 Voice 面板仍拿到 WorldVoice 的 class**：`WV/__init__.py:58`、`:209` 讀碼確認；`test_runtime_composition.py:624`（stub `ui.voicePanel` 跑真進入點）、`test_voice_settings_panel.py`、`test_settings_order.py`（alias 套件下載入真 `ui/voicePanel.py`，`..pipeline.settings` 深度被真正解析）在重放 Task 2 的聚焦執行（280 passed）與全套件都綠。
2. **全域外掛的對話框從新路徑 import**：`speechSettingsDialog.py:19-30`；`test_pipeline_panels.py`、`test_role_panel.py`、`test_unicode_panel.py` 載入真對話框，綠。
3. **以套件路徑 import `ui.panelLayout`、不需 wx／NVDA**：重放 Task 2 Step 1 紅（`No module named 'synthDrivers.WorldVoice.ui'`）、Step 6 紅（wx halted）；另加 9 個突變探針，見結論與表格。缺口見 M1、M2。
4. **`speechCommands` 改名後語言／索引標記仍是同一個 class**：`test_speech_command_contract`、`test_worldvoice_index_command`、`test_legacy_speech_commands`、`test_runtime_adapter_contract`、`test_worldvoice_speak` 在重放 Task 1 紅（`164 failed, 24 passed, 35 errors`，和 plan 一字不差）→ 綠（223 passed）；`speechCommands.py` 內容 100% 相同。
5. **pipeline 不依賴 `ui/`**：grep 無；`test_pipeline_structure::test_only_the_context_asks_nvda_for_the_synth`、`test_lint_rewrites::test_worldvoice_synth_returns_only_worldvoice` 未改、綠。

另外 plan 注意的 `pyproject.toml` mutmut `source_paths`（`:55-56`）已跟著搬，`test_hygiene_guards::test_ruff_reports_nothing` 綠。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 全套件（分支 worktree） | `python3 -m pytest -q -p no:cacheprovider tests`（看門狗外層） | **3225 passed**，0 skipped，93 s |
| prek | `prek run --all-files`（分支 worktree） | 8 個 hook 全數 Passed；之後 `git status --short` 無輸出（hook 沒改檔） |
| 空白字元 | `git diff --check master` | 無輸出 |
| 受保護路徑 | `git diff --stat master -- 'WV/driver/*/driver/' WV/driver/sonic/ WV/languageDetection/script_data.py WV/pipeline/unspaced_common_data.py`；`git ls-files WV/driver/Neural` | 兩者皆無輸出 |
| 外掛契約測試 | `git diff master --stat -- tests/test_plugin_voice_contract.py` | 無輸出 |
| commit 格式 | `git log master..HEAD --format=%B \| grep -ci co-authored` | 0；5 個 commit 皆英文 `<type>: <summary>` 加內文 |
| 純改名 | `git diff -M --summary master -- addon tests` | `_speechcommand.py => speechCommands.py`（100%）、`{pipeline => ui}/panelLayout.py`（100%）、`pipelineControls.py => ui/controls.py`（97%）、`VoiceSettingsDialogs.py => ui/voicePanel.py`（98%）；後兩者的 diff 只有 import 行與一行 docstring |
| 殘留舊名 | `git grep -nE "_speechcommand\|pipelineControls\|VoiceSettingsDialogs\|pipeline\.panelLayout\|pipeline/panelLayout" -- . ':!docs'`；另 grep `sconstruct`、`buildVars.py`、`manifest*.tpl`、`.pre-commit-config.yaml`、`.github/` | 皆無輸出；只有 `pyproject.toml:55-56` 的新路徑 |
| 字串式模組引用 | grep `importlib\|sys.modules\|__package__\|import_module` 於 `addon/`（排除內層驅動） | 只有 `bridge/completionPolicies.py:75`、`engine/__init__.py:20`、`engine/discovery.py:104`，都指 `driver`，與本階段無關 |
| **plan 重放** | 全新 clone 於 `1f7fa46`，自寫套用器逐步套 Task 1–3 的 `Edit:`／bash 區塊，每個 commit 跑 prek hook | Task 1：14 + 4 個區塊；red `164 failed, 24 passed, 35 errors`（12 行 `FileNotFoundError`、386 行 `ModuleNotFoundError`）；green `223 passed`；commit → `5a8cee35…`／`0e8ab84f…` ✔（= plan = 分支 `183494a`）。Task 2：3 + 6 + 17 個區塊；red `1 failed, 5 passed`（`No module named 'synthDrivers.WorldVoice.ui'`）；green `280 passed`；Step 6 `1 failed`（`import of wx halted`）→ 還原後 `6 passed`，`ui/__init__.py` 空；commit → `33880423…`／`08f6907f…` ✔（= plan = 分支 `6d5bb04`）。Task 3：1 個區塊；commit → `14d90d18…`／`08f6907f…` ✔（= plan = 分支 `ced33e5`）。三個 commit 的 hook 都一次通過。`git diff <重放 HEAD> ced33e5 -- addon tests pyproject.toml` **無輸出**。 |
| rebase 到現在的 `master`（I1） | scratch clone：`git rebase 71748c1`；比對 `git diff 71748c1 <rebased>` 與 `git diff 1f7fa46 ced33e5`（限 `addon tests pyproject.toml`） | 無衝突；兩份 diff 以 `cmp` 比對逐位元組相同（586 行）。rebase 後 `HEAD:addon` = `0ce05e80f67d077c311702467f09befadba10bd5`、`HEAD:tests` = `08f6907fb671bfcf0badeafd32664dcba29d8369` |
| 空的 `__init__.py` | `git cat-file -s ced33e5:WV/ui/__init__.py` | 0 |
| 歷史可追 | `git log --follow -- WV/ui/voicePanel.py \| tail -1` | `61b1d8a`（espeak 整合的早期 commit）；`ui/panelLayout.py` 的 `--follow` 歷史 5 個 commit |
| **突變探針**（scratch clone，只跑 A2 守衛） | 基準 | 1 passed |
| | M1 `ui/__init__.py` 寫 `from . import controls` | 1 failed：`import of wx halted; None in sys.modules` |
| | M2 `ui/__init__.py` 寫 `from ..pipeline import settings` | 1 failed：`import of config halted` |
| | M3 `panelLayout.py` 加 `import wx` | 1 failed：`import of wx halted` |
| | M4 `panelLayout.py` 加 `from ..numberLanguage import FOLLOW` | 1 failed：載入集合斷言（多了 `synthDrivers.WorldVoice.numberLanguage`） |
| | M5 `panelLayout.py` 加 `import languageHandler` | 1 failed：`No module named 'languageHandler'`（靠不存在，見 M2） |
| | M6 `panelLayout.py` 加 `from gui import nvdaControls` | 1 failed：`import of gui halted` |
| | M7 `panelLayout.py` 加 `import re` | 1 passed（stdlib，應允許） |
| | M8 `ui/__init__.py` 寫 `from . import panelLayout` | **1 passed**（漏接，見 M1） |
| | M9 `ui/__init__.py` 寫 `import ui`（NVDA 的） | 1 failed：`No module named 'ui'` |
| | M10 `panelLayout.py` 加 `import tones` | 1 failed：`No module named 'tones'`（靠不存在，見 M2） |
| | M11 `ui/__init__.py` 寫 `from ..locales import primary_language` | 1 failed：載入集合斷言 |
| 順序與洩漏 | 自寫 plugin 在每個測試前後比對 `sys.modules`（新增的 `synthDrivers*`、任何值為 `None` 的項目、被移除的 `synthDrivers*`）；守衛 + 11 個鄰居檔正向、反向、守衛重複三種排列；再跑整個套件 | 288／288／49 passed；三種排列與全套件 3225 個測試都「no synthDrivers*/None leaks」 |
| 殘留 stub | 全套件跑完後列出 `sys.modules` 裡 NVDA 名字（`wx`、`gui`、`config`、`speech`、`languageHandler`、`tones`、`core`、`queueHandler`、`ui`、`globalVars`、`nvwave`、`api` 等 23 個頂層名） | 3225 passed；session 結束時 `sys.modules` 裡這 23 個名字一個都沒有（`[]`），所以 M2 描述的遮蔽今天不會發生 |
| isort 改序 | 逐行讀 6 個檔的 diff | 全是同一區塊內的排序，無新增或刪除的名字；`initTranslation()` 位置不變；搬移模組無 `_(` |
| 未做 | 打包、Windows／NVDA 實機、mutmut | 未做。spec §7 說明本階段無新邏輯，不需 mutmut；無行為變更，不需 Windows 驗證。NVDA 實機上「Voice 設定面板顯示 WorldVoice 控制項、WorldVoice 設定對話框能開啟」仍是下次打包時要看的項目。 |

## 使用者還沒確認的使用者可見預設

- 無。本階段沒有任何設定鍵、confspec、預設值或 UI 字串的變動；升級的使用者所有設定保留。`worldvoice_synth` 的位置（Ruling 1）是結構決定，使用者看不到。

## 給修正者／協調者的備註

- I1 不需要改任何原始碼；只要 rebase、確認 tree id、補 plan、重跑 §7。
- 若修 M1／M2／M3（都只動 `tests/` 或 spec），`HEAD:addon` 仍是 `14d90d18…`（rebase 後 `0ce05e80…`），`HEAD:tests` 會變；依 §4.5 在 plan 檔尾加「## 修正」段落寫出 `Edit:` 區塊和 commit 後的 tree id，從 Task 3 的 tree 接著 dry run。
- 我的 scratch clone（`replay-phase37`、`mut-phase37`）與 plugin 檔審完已刪除。
