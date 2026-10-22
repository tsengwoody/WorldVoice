# Phase 32 Review 紀錄：面板相依規則、log 標籤、`worldvoice_synth()`、`SpeechContext` 收窄

日期：2026-10-22。分支：`phase32-panels-context`（`96d6c08..7aa8496`，8 個 commit），worktree `/workspace/WorldVoice-phase32`。
依據：

- 規格 `docs/superpowers/specs/2026-10-22-phase32-panels-context-design.md`（`b2b22b4`；使用者決定 D1–D4，§16 的 Q1–Q8 為協調者預設）
- 計畫 `docs/superpowers/plans/2026-10-22-phase32-panels-context.md`（`cb91dfe`；Review Focus 1–5；`7aa8496` 補上 mutmut 前後表）
- 進度帳本 `.superpowers/sdd/2026-10-22-phase32-panels-context/progress.md`（3 個 `Ruling:`）
- 第六輪審查 `storage/refactor6.md` §11「階段 32」
- `DEVELOPMENT_WORKFLOW.md` §3.3、§6、§7、§8

流程：審閱者 Fable 5.1，唯讀。測試、master 對照探針、守門種子、xgettext 比對與 mutmut 都在 scratchpad 的兩個暫時 worktree（`wt-master` 在 `96d6c08`、`wt-head` 在 `7aa8496`，`ref` 以 symlink 接到主 checkout，審完已 `git worktree remove` 並 `prune`）進行；pytest 單一行程、mutmut 3 個 child，皆有 3 GB MemAvailable 記憶體監控（全程最低 5.9 GB）。沒有 push、沒有 stash、沒有動主 checkout 與其他 worktree。

`file:line` 以 `7aa8496` 為準；master 的行號以 `96d6c08` 為準。

## 結論

Ready to merge：**是。** Critical 0、Important 0、Minor 4。

- **四個目標都達成，而且沒有行為差異。**
  - D1：`read_control`／`apply_dependencies`（`pipelineControls.py:87-117`）的本體就是 master 兩個面板的本體，只把 spec 清單與控制項查找傳進去；唯一的語意步驟 `read_control → control_value` 對表允許的兩種 controller（checkbox、choice）回傳值與 master 逐字相同（slider 分支只有表守門禁止的 slider controller 才會走到）。審閱者對 master 與分支各跑同一支探針（兩個面板、開啟 × 4 種數字模式 × 停頓開關、選取 0..3 與 −1、設定環改值後 `updateDriverSettings("voice")`、清單缺少選項（−1）、另一個合成器（ABSENT）、沒有 nummod／沒有停頓開關的驅動、`refreshGui` 三種重建、被銷毀的視窗、`_control` 回 `None`），把每一次 `Enable(label, bool)` 呼叫與讀到的 controller 值都記下來：**411 行逐位元組相同**，含呼叫次數與順序。`evt.Skip()`（驅動設定仍被 NVDA 寫入）與 I1 規則（`_voiceControl` 把銷毀的視窗當 `None`）都留在 Voice panel，探針裡 `driver.nummod`／`driver.punctuationpauseenabled` 在 fire 後都已改寫。
  - D2：`_LOG_LABELS`（dialog `:48-49`）推導出的八個鍵值對與 master 的字面值逐一相同、順序相同（探針與 `test_log_switch_labels_are_unchanged` 都印出同一份）；Log Record panel 的 `settings`（`:650`）與 confspec 都仍以 `LOG_SWITCHES` 排序。審閱者自己跑 xgettext（兩棵樹各 67 個檔案）：**msgid 集合相同（各 109 筆，不含 header）**；`msgfmt --check` zh_TW 通過；`addon/locale` 沒有 diff。zh_TW 的八個 msgstr 仍是「套用語音字典、數字語言、數字模式、中文空白停頓參數、項目停頓參數、標點停頓參數、數字停頓參數、語音檢視器」，七個 catalog 的六個表 msgid 的 msgstr 都沒有 `&`。沒有任何 `&` 剝除；Guard A 對 `&` 的檢查種子測試確認有效。
  - D3：`worldvoice_synth()` 就是 `getSynth()` 加名稱過濾（`pipeline/context.py:24-27`）；`makeSettings` 在 GUI 執行緒上一次跑完，所以 `synth` 和 master 的第二、三次 `getSynth()` 是同一個物件。另一個合成器在用時兩者都回「不是 WorldVoice」分支；對話框開著時換合成器，`set_main_voice` 仍在執行當下問 `worldvoice_synth()`（`:192-195`），`onSave` 仍比對 `current.voice_manager is self._manager`（`:459`），`test_panel_opens_its_presenter_for_the_worldvoice_manager` 的 `current[0] = None` 路徑與 `test_role_panel_does_not_save_to_a_voice_manager_the_synth_replaced` 未改仍綠。
  - D4：`name`／`language` 是 `VoiceFacade.__init__` 從 `VoiceSpec`（兩者都是 `str`，`runtime/models.py:15-21`）設一次的普通屬性（`compat/voiceFacade.py:34-35`），`driver/*/__init__.py` 與 `ref/Neural` 都沒有覆寫（grep `def name`／`def language`／`.name =`／`.language =`，只有 OneCore 對 `core` 物件的賦值）。`_defaultVoiceInstance` 在 `_initialize` 之後只會被 setter 以實例取代（`voiceManager.py:91`、`:193`），`terminate` 不清它，`speech_context()` 對 `None` manager 先回 `GENERIC_CONTEXT`，所以 `voice.name`／`voice.language`（主驅動 `:361-367`）不會讀到 `None`。`ref/Neural` 不讀 `SpeechContext`／`speech_context`／`current_context`（grep 為 0）。`GENERIC_CONTEXT` 不變，兩個新欄位預設 `None`，`deduplicate_language_command` 仍比 `None`。`addon/` 與 `tests/` 裡 `default_voice` 的讀取者全部改完（grep 只剩 Guard E 本身與兩個測試名稱）。
- **import 方向正確。** `pipelineControls.py` 只 import `collections.abc`、`typing`、`wx`、`gui.nvdaControls` 與 `.pipeline.panelLayout`；兩個面板不再 import `ABSENT`／`choice_values`／`dependent_states`／`selected_value`；沒有 panel→driver 的循環。
- **Review Focus 1–5 與三個 Ruling 都成立**（見下方逐項）。
- **五個守門（A–E）在 16 個種子違規下全部失敗**；Guard C 在 mutmut 複本上的 `skipif` 合理。
- **mutmut 後測表與實作者記錄完全一致**（151 個 mutant、146 killed、5 survived，0 timeout、0 suspicious）。五個存活 mutant 都在本階段沒動的行上、與 master 前測的五個一一對應；但其中兩個**不是等價突變**，是 master 既有的測試缺口（M1）。

## Critical

無。

## Important

無。

## Minor

### M1. `deduplicate_language_command` 的五個存活 mutant 有兩個不等價（master 既有的測試缺口，非本階段造成）

- **位置：** `pipeline/__init__.py:638-639`（`_11`：`continue` → `break`）、`:632`（`_7`：`voice_name = … or default_name` → `None`）；計畫「Implementation notes: mutmut」只說它們「predate this phase」，沒有稱其等價，符合 spec §11 的要求。
- **情境（審閱者在 scratch 複本把突變套進真實函式實測）：** `_11`：ctx.language 為 `en`，序列 `[L("en"), "x", L("de"), "y"]`，master 與分支都輸出 `["x", "de", "y"]`，突變後輸出 **`[]`**——第一個多餘的語言命令之後的所有內容全被丟掉，而 NVDA 經常在序列開頭送目前語言的 `LangChangeCommand`。它存活是因為 `test_dedupe_keeps_only_real_voice_switches`（`tests/test_pipeline_voice_lookup.py:29`）唯一的多餘命令 `L("en")` 在序列最後，`break` 與 `continue` 無法分辨。`_7`：`start_language="fr"`（沒有 fr 語音）後接 `[L(None), "w"]`，正確輸出 `["w"]`，突變後 `[None, "w"]`（多發一個回預設語音的命令；後面會變成對同一語音的 `SelectVoice`，所以使用者聽不出來，但命令序列不同）。其餘三個（`_2`、`_6`、`_14` 把 `current_language` 設成 `None`）在「`voice_name_for_language(ctx.language)` 就是預設語音」這個 `mainLocalePolicy` 維持的不變量下，會被後面的語音名稱比對擋住，實務上等價。
- **建議：** 在 `test_dedupe_keeps_only_real_voice_switches` 的序列最後加一個字串（例如 `"v"`），並斷言輸出以它結尾，就能殺掉 `_11`；`_7` 可在同一檔加一個 `start_language` 案例（`[L(None), "w"]`，`start_language="fr"` → `["w"]`）。兩行的事，可以併入本階段修正，或留到下一次碰 `pipeline/__init__.py`。不改不影響合併。

### M2. Guard B 的「沒有迴圈」檢查只看 `ast.For`

- **位置：** `tests/test_ui_structure.py:75`。
- **情境：** `_applyDependencies` 若改寫成 `[c.Enable(s) for …]`（`ast.comprehension`）、`while` 或 `list(map(…))`，又在某處保留一個對 `apply_dependencies` 的呼叫，Guard B 仍通過。名稱那一半（`:66-72`，`dependent_states`／`ABSENT`／`selected_value` 不得出現）才是真正擋住「把規則複製回面板」的檢查，審閱者種子 B1（把迴圈寫回 dialog）、B2（Voice panel 重新 import `ABSENT`）、B3（`_readController` 自己讀控制項）都 1 failed，所以實際保護足夠。
- **建議：** 可把 `ast.For` 改成 `(ast.For, ast.While, ast.ListComp, ast.GeneratorExp)`，或乾脆只留「呼叫 `apply_dependencies` 且不呼叫 `Enable`」的檢查。不改也可。

### M3. Guard D 只掃 `globalPlugins/WorldVoice/*.py` 一層

- **位置：** `tests/test_ui_structure.py:103`（`glob("*.py")`；同檔 `:29` 的既有守門也是同一寫法）。
- **情境：** 目前 `globalPlugins/WorldVoice/` 只有五個模組、沒有子套件，所以沒有漏網；將來若加了子套件（例如把 presenter 搬進 `panels/`），裡面的 `getSynth` 不會被查到。
- **建議：** 改成 `rglob("*.py")`，一字之差。

### M4. 六個表 msgid 的 Translators 註解不再提到 log 開關

- **位置：** `pipeline/settings.py:156`、`:169`（「Label for a setting in synth settings ring」）、`:196`、`:205`、`:223`、`:255`（「Label for a pipeline setting in the voice settings panel and the Speech Pipeline panel」）。審閱者用 `xgettext --add-comments=Translators:` 比對：master 的 .pot 對這六個 msgid 各有兩條註解（dialog 的「pipeline log switch」＋表的），分支只剩表的那一條；spec §5.3 已預告。
- **情境：** 譯者從下一份 .pot 看不出這六個字串同時是 Log Record panel 的核取方塊標籤。msgid 與既有翻譯都沒變，所以對現有 catalog 沒有影響。
- **建議：** 在表的註解尾端補一句「also the label of its log switch in the Log Record panel」之類的提示；只改註解，不動 msgid。可留到下次改 `settings.py` 時順手做。

## 計畫 Review Focus 與 Ruling 的逐項檢查

| # | 項目 | 結果 |
| --- | --- | --- |
| RF1 | 對話框開著時換走合成器／Voice panel 重建 | 探針：另一個合成器 → 四個相依控制項都不存在、`_readController` 兩個 controller 都回 `ABSENT`，`_applyDependencies` 再跑一次沒有任何 `Enable`；`WV→WV`、`WV→other`、`other→WV` 三種 `refreshGui` 後的狀態與 master 相同，舊的 `groupSizeSpin` 已 `destroyed`，新的不是同一物件；把 `groupSizeSpin.destroyed` 設成 True 再 `_applyDependencies` → 只對其餘三個 `Enable`，沒有例外。`test_voice_settings_panel.py:368-377`、`:429-475` 未改仍綠（`git diff --stat master` 無輸出）。 |
| RF2 | NVDA 清單缺少儲存的選項（−1 或超出清單） | `read_control` 的 driver 分支讀 `GetSelection()`（`pipelineControls.py:98`），`selected_value` 對 −1 與 `>= len` 都回 `None`；`test_read_control_reads_a_driver_choice_from_its_options` 的 fake 讓 `GetSelection` 與 `GetCurrentSelection` 回不同索引並斷言沒呼叫後者。探針：`driver.nummod = "gone"` 後 `updateDriverSettings("voice")` → `selection == -1`、`number_mode` 讀成 `None`、Group size 停用；Pipeline panel `Select(-1)` 同樣停用。與 master 相同。 |
| RF3 | 翻譯後的八個 Log Record 標籤 | msgid 集合相同（xgettext，109 筆）；zh_TW 八個 msgstr 列於上方「結論」；`"&"` 檢查種子 A3（拿掉 `number_mode` 的 `display_name`）→ Guard A 與 pin test 都 1 failed；A4（規則反過來寫成 `label or display_name`）同樣兩個都 failed。`test_translator_comments.py` 在全套內通過（`CHANGED_LABEL_MSGIDS` 的三個表字串由 `settings.py` 的單行 `_()` 供應）。 |
| RF4 | 非 modal 對話框活得比 WorldVoice 久 | `set_main_voice` 的 closure 仍在執行時呼叫 `worldvoice_synth()`（dialog `:192-195`）；`synth.name` 只用來定位 `config.conf["speech"][name]`，與 master 的 `getSynth()` 回傳值是同一物件。`test_role_panel.py:90-157`（含 `current[0] = None` 路徑）與 `test_ui_structure.py` 的「不存到被換掉的 manager」測試都只拿掉 `getSynth` 鍵，其餘未動；若 `getSynth()` 呼叫回來，`load_definitions` 的命名空間會 `NameError`。 |
| RF5 | 兩句話之間預設語音改變 | `speech_context()` 每次呼叫都重新讀 `manager.defaultVoiceInstance`（`:361`），沒有快取；`test_speech_context_falls_back_while_the_synth_is_not_running` 的延伸斷言（換 `defaultVoiceInstance` 後第二次得 `("B:zh", "zh")`）在分支上通過；`test_lang_cmd_to_voice_selects_names_and_falls_back` 仍驗證 `L(None)` → 預設語音的語言（角色語音 `R:en-role`）與 `L("xx")` → 預設語音名稱。 |
| Ruling 1（Task 1） | `test_pipeline_controls.py` 36 而非 32 | **合理。** 審閱者在 `wt-master` 跑該檔：18 passed（計畫把既有的參數化案例算成 14）；分支 36 passed，新測試正好 18 個，與 spec §10.2 相符；全套 2370 與計畫一致。 |
| Ruling 2（Task 5） | 讀取者的 tuple 斷言拆成兩個 | **合理。** `context["number_language"] == "default"` 保住了 spec §10.5 替換行會丟掉的檢查；多一個斷言、值未變。 |
| Ruling 3（Task 6） | 在既有 slider 測試加 `style == SL_HORIZONTAL` 斷言 | **合理。** spec §11 明文允許「一個斷言殺掉 `pipelineControls` 既有存活者」；審閱者重跑 `x_make_control*` 80/80 killed，確認 `_38`／`_44` 已被這個斷言殺掉；測試名稱與參數化未變，套件數不變。 |
| Guard C 的 `skipif(running_under_mutmut())` | — | **合理。** mutmut 3.8.0 把 `from mutmut.mutation.trampoline import …` 注進被突變的 `pipelineControls.py`（審閱者在 `wt-head/mutants/` 看到 `:31`），Guard C 讀原始碼必然失敗，而且它沒有任何 mutant 可殺。在 `mutants/` 下跑 `test_ui_structure.py`：4 passed、1 skipped；正常全套 0 skipped。與階段 31 Guard A 的處理一致。 |

## 守門測試的評估

在 `wt-head` 逐一種入違規，每次只改一處、跑完 `git checkout -- <檔案>`：

| 種子 | 預期 | 結果 |
| --- | --- | --- |
| A1 dialog 的 `_STAGE_LOG_LABELS` 加回 `"number_mode": _("Number mode")` | Guard A 失敗 | 1 failed |
| A2 dialog 另加一個無關的 `_("Item wait factor")` | Guard A 失敗（msgid 交集） | 1 failed |
| A3 表的 `number_mode` 拿掉 `display_name`（標籤變成 `Number &mode`） | Guard A（`&`）與 pin test 失敗 | 兩者都 1 failed |
| A4 推導規則改成 `label or display_name` | Guard A 與 pin test 失敗 | 兩者都 1 failed |
| B1 dialog 的 `_applyDependencies` 寫回 `for` 迴圈 | Guard B 失敗 | 1 failed |
| B2 Voice panel 重新 import `ABSENT` | Guard B 失敗 | 1 failed |
| B3 Voice panel 的 `_readController` 自己讀控制項、不叫 `read_control` | Guard B 失敗 | 1 failed |
| C1 `pipelineControls.py` 加 `from . import VoiceSettingsDialogs` | Guard C 失敗 | 1 failed |
| C2 `apply_dependencies` 函式內加 `from logHandler import log` | Guard C 失敗（`ast.walk`） | 1 failed |
| C3 `pipelineControls.py` 加 `from .pipeline.settings import PIPELINE_SETTINGS` | Guard C 失敗（相對 import 只許 `pipeline.panelLayout`） | 1 failed |
| D1 dialog 加回 `from synthDriverHandler import getSynth` | Guard D 失敗 | 1 failed |
| D2 `globalPlugins/WorldVoice/__init__.py` 加函式內 `synthDriverHandler.getSynth()`（Attribute） | Guard D 失敗 | 1 failed |
| E1 `context.py` 加回 `default_voice: Any = None` | Guard E 失敗 | 1 failed |
| E2 `default_voice_language` 標成 `Any` | Guard E 失敗 | 1 failed |
| E3 `lang_cmd_to_voice` 改讀 `ctx.default_voice.language` | Guard E 失敗 | 1 failed |
| E4 主驅動 `speech_context()` 加 `default_voice=voice,` | Guard E 失敗 | 1 failed |

改過的測試逐一讀過：11 個 `default_voice=` 建構點只改成兩個字串欄位（字面 `SimpleNamespace` 的改成字面值），斷言沒有變；`test_log_labels_match_stages_and_confspec` 只把載入方式換成 `load_settings_dialog`，鍵順序與 confspec 斷言照舊；`test_role_panel.py:130`、`test_unicode_panel.py:59` 只拿掉 `getSynth` 鍵。`test_settings_panels.py`、`test_voice_settings_panel.py`、`test_role_panel_ui.py`、`test_worldvoice_speak.py`、`test_translator_comments.py`、`ui_harness.py`、`pipeline_harness.py` 與 master 沒有 diff。

## mutmut

審閱者在 `wt-head`（`7aa8496`）重跑：`mutmut run --max-children 3` 限定 `pipelineControls.x_*`、`pipeline.x_deduplicate_language_command*`、`pipeline.x_lang_cmd_to_voice*`，記憶體監控（最低 5.9 GB）；無 timeout、無 suspicious。

| 函式 | mutant | killed | survived |
| --- | --- | --- | --- |
| `pipelineControls.x_read_control` | 14 | 14 | 0 |
| `pipelineControls.x_apply_dependencies` | 11 | 11 | 0 |
| `pipelineControls.x_make_control` | 80 | 80 | 0 |
| `pipelineControls.x_control_value` | 15 | 15 | 0 |
| `pipelineControls.x_control_row` | 5 | 5 | 0 |
| `pipeline.x_deduplicate_language_command` | 21 | 16 | 5（`_2`、`_6`、`_7`、`_11`、`_14`） |
| `pipeline.x_lang_cmd_to_voice` | 5 | 5 | 0 |

與計畫「Implementation notes: mutmut」的後測欄完全一致。`pipelineControls` 的基準完整：模組的五個函式全部列出（`CHANGE_EVENTS` 是模組層常數，mutmut 不突變）。

前測：審閱者另在 `wt-master`（`96d6c08`）重跑 `x_deduplicate_language_command*`：25 個 mutant、20 killed、5 survived（`_6`、`_10`、`_11`、`_15`、`_18`），`mutmut show` 的五個差異與分支的 `_2`、`_6`、`_7`、`_11`、`_14` 逐一相同（編號 −4，正是被拿掉的 `if … is not None else None` 那 5 個 mutant 加上新行的 1 個）。與帳本記錄一致，五個存活者確為 master 既有。

五個存活 mutant 的原始碼差異（`mutmut show`）：`_2` `current_language = default_language = ctx.language` → `= None`；`_6` `current_language = start_language` → `= None`；`_7` `voice_name = ctx.voice_name_for_language(start_language) or default_name` → `= None`；`_11` 語言未變時的 `continue` → `break`；`_14` 回到預設語言時 `current_language = default_language` → `= None`。都在本階段沒有改動的行上（diff 只動 `:628` 一行）。等價性見 M1：`_2`、`_6`、`_14` 實務上等價，`_7`、`_11` 不等價。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 全套測試（分支 worktree） | `python3 -m pytest -q -p no:cacheprovider tests`，單一行程，3 GB 記憶體監控 | **2370 passed, 2 warnings in 63.21 s**，0 skipped（最低 MemAvailable 6.28 GB；兩個 warning 與前幾輪相同） |
| prek（分支 worktree，乾淨樹） | `prek run --all-files`（prek 0.4.14、ruff 0.16.3） | 8 個 hook 全 Passed，`git status` 乾淨 |
| 空白 | `git diff --check master` | 乾淨（rc 0、無輸出） |
| 受保護路徑 | `git diff --stat master -- 'driver/*/driver/' driver/sonic/ languageDetection/script_data.py`；`git ls-files …/driver/Neural` | 兩者皆無輸出 |
| 翻譯檔 | `git diff --stat master -- addon/locale` | 無輸出 |
| Co-Authored-By | `git log --format=%B master..HEAD \| grep -ci co-authored-by` | 0；8 個 commit 都是 `<type>: <summary>` 加說明理由的內文 |
| 跨驅動 import | grep 各 `driver/<Engine>/` 內對其他引擎 package 的 import | 無 |
| 行為等價探針（面板） | 同一支腳本在 `wt-master` 與 `wt-head` 各跑一次（ui_harness 載入真實的兩個面板與 `pipelineControls`，`Control.Enable` 包成記錄器） | 411 行逐位元組相同（`diff` 無輸出） |
| xgettext msgid 集合 | 兩棵樹各對 `git ls-files 'addon/*.py'` 減內層驅動與 `script_data.py`（67 檔）跑 `xgettext --language=Python --keyword=_ --from-code=UTF-8`，只比 `msgid`（含續行） | 各 109 筆，`diff` 無輸出 |
| Translators 註解 | 同上加 `--add-comments=Translators:` | 六個表 msgid 在分支仍各有表的註解；dialog 的兩個 stage 標籤仍有註解；master 的「pipeline log switch」那一條消失（M4，spec 已預告） |
| zh_TW catalog | `msgfmt --check`；grep 八個 msgid 的 msgstr；七個 catalog 的六個表 msgid 的 msgstr 是否含 `&` | 通過；八個 msgstr 列於結論；沒有 `&` |
| D4 的讀取者 | grep `default_voice\b` 於 `addon`、`tests`、`ref/Neural`；grep `SpeechContext\|speech_context\|current_context` 於 `ref/Neural` | `addon` 無；`tests` 只剩 Guard E 與兩個測試名稱；Neural 全無 |
| D4 的 `None` 可能性 | 讀 `voiceManager.py:59、:91、:181-193`、主驅動 `:232、:303、:357-368`、`compat/voiceFacade.py:34-35`、`runtime/models.py:15-21` | `_defaultVoiceInstance` 只在 `__init__` 內為 `None`，之後只被實例取代；`name`／`language` 為 `str` 的普通屬性，沒有覆寫 |
| import 方向 | 讀 `pipelineControls.py:10-25`；Guard C；兩個面板的 import 區塊 | 只有 `collections.abc`、`typing`、`wx`、`gui`、`.pipeline.panelLayout`；無循環 |
| 守門種子 | 上表 16 個種子 | 全部失敗，如預期 |
| Guard C 在 mutmut 複本 | 在 `wt-head/mutants/` 跑 `tests/test_ui_structure.py` | 4 passed、1 skipped；`pipelineControls.py:31` 是 mutmut 的 trampoline import |
| Ruling 1 | `wt-master` 跑 `tests/test_pipeline_controls.py` | 18 passed（分支 36） |
| mutmut 後測 | `wt-head`、`--max-children 3`、記憶體監控 | 151 mutant、146 killed、5 survived、0 timeout、0 suspicious（表見上） |
| 存活 mutant 的實測 | 把 `_11`、`_7` 套進 `wt-head` 的真實函式再跑探針 | `_11`：`[L("en"), "x", L("de"), "y"]` → `[]`；`_7`：`start_language="fr"` 的 `[L(None), "w"]` → `[None, "w"]`（M1） |
| 暫時 worktree 清理 | `git worktree remove --force` × 2、`git worktree prune`、`git worktree list` | 只剩主 checkout、`WorldVoice-phase31`、`WorldVoice-phase32` |

Linux 上只驗證了 harness 的假 wx 與真實的面板、pipeline 程式碼；Windows 上 NVDA 的真實 wx、焦點、語音與引擎 SDK 都沒有驗證到（spec §13 的五個手動項目仍待下一個打包版本做煙霧測試）。

## 使用者還沒確認的使用者可見預設

本階段沒有使用者可見的行為變更：沒有新字串、沒有改字串、沒有新設定或 log 鍵、enable 規則與 Tab 順序不變。以下是協調者預設或尚未在 Windows 驗證、使用者未明確確認的項目：

1. spec §16 Q1–Q8 的八個協調者預設（`read_control` 重用 `control_value`；`display_name or label` 且不剝 `&`；不加 `panelLayout` helper；兩個字串欄位命名 `default_voice_name`／`default_voice_language`；`speech_context()` 不加 `None` 守門；`pipelineControls.py` 永久加入 mutmut `source_paths`；binding 與 `_onControllerChange` 留在各面板；拿掉兩個測試命名空間的 `getSynth` 鍵）。審閱者都同意。
2. 下一份 `.pot` 裡六個表 msgid 失去「pipeline log switch」那條 Translators 註解（M4）；對既有翻譯沒有影響。
3. spec §13 的 Windows 手動煙霧測試（Voice panel 與 Speech Pipeline 的兩條 enable 規則、Log Record 八個標籤的英文與 zh_TW、Speech Role／Unicode Detection 在另一個合成器下的提示、混合中英文朗讀後回到預設語音）尚未在 NVDA 上執行。
4. M1 的兩個測試缺口（`_7`、`_11`）是否要在本階段順手補上。

## 修正記錄

修正者 Opus 5.5，2026-10-22，worktree `/workspace/WorldVoice-phase32`，從 `729912e` 開始。四個 Minor 全部修正，每項先證明測試或守門抓不到（RED），再修正。突變與種子違規都只在 scratchpad 的複本裡套用。每個 commit 前都跑了全套測試（單一行程，3 GB 記憶體監控）、`prek run --all-files`、`git diff --check master`、兩個受保護路徑指令與 zh_TW 的 `msgfmt --check`。各項的 `Ruling:` 記在進度帳本。

| # | commit | 修正內容 | 驗證 |
| --- | --- | --- | --- |
| M1 | `facec75` | `test_dedupe_keeps_only_real_voice_switches` 的序列在多餘的 `L("en")` 後面加上 `"v"`。新增 `test_dedupe_starts_on_the_default_voice_when_no_voice_speaks_the_start_language`：`start_language="fr"`、沒有 fr 語音，`[L(None), "w"]` 應得到 `["w"]`。計畫的 mutmut 表同步更新。 | 在複本套用 `_11`（`continue` → `break`）：前一個測試失敗；套用 `_7`（`voice_name = None`）：新測試失敗。`729912e` 的舊測試在兩個突變下都通過。mutmut 重跑（`--max-children 3`，記憶體監控，最低 5.7 GiB）：`x_deduplicate_language_command` 21 個 mutant、18 killed、3 survived，0 timeout、0 suspicious。剩下的 `_2`、`_6`、`_14` 在主語系不變量下實務上等價，照原紀錄保留。 |
| M2 | `8fa813c` | Guard B 的迴圈檢查改成 `(ast.For, ast.AsyncFor, ast.While, ast.comprehension)`。`ast.comprehension` 涵蓋 list、set、dict comprehension 與 generator expression。 | 舊守門讓 dialog 的 list comprehension、generator 與 `while` 三個種子通過，只擋住 `for`。新守門擋住這四個種子，也擋住 Voice panel 的 dict comprehension 種子；沒有種子時通過。 |
| M3 | `7690c0c` | Guard D 改用 `rglob("*.py")`。同一檔案中寫法相同的 public-driver-hooks 守門（`:29`）也一起改。兩者的訊息改成相對於 `addon/` 的路徑，因為子套件的 `__init__.py` 只寫檔名會和外掛本身的 `__init__.py` 混淆。 | 在複本加入 `panels/` 子套件，放入 `getSynth` 與 `._voiceManager`：舊的 `glob` 兩個守門都通過，`rglob` 兩個都失敗；沒有種子時通過。 |
| M4 | `d365dab` | `pipeline/settings.py` 六個表字串的 `# Translators:` 註解各加一行：「also the label of the setting's pipeline log switch in the Log Record panel.」新增 `test_table_labels_tell_translators_they_name_log_switches`。這個測試從 `LOG_SWITCH_ORDER`、設定表與 `_LOG_LABELS` 推導，以後新增以設定命名的 log 開關也會被檢查到。 | 新測試在改註解前對六個鍵失敗，改後通過。xgettext（67 個檔案，`--add-comments=Translators:`）前後各 109 個 msgid，集合相同（`diff` 無輸出）；六個 msgid 的 `#.` 區塊都有新的那一行。`msgfmt --check` zh_TW 通過，`test_translator_comments.py` 通過，`addon/locale` 沒有變動。 |

最終驗證（`d365dab`）：

- 全套測試 **2372 passed、0 skipped**（基準 2370，加上 M1 與 M4 各一個新測試）。
- `prek run --all-files` 全部 Passed。
- `git diff --check master` 乾淨。
- 兩個受保護路徑指令都沒有輸出。

另外，在複本以最終的測試跑 mutmut，stats 階段通過。這表示新加的讀原始碼測試在 mutmut 的複本上也能正常執行。

Windows 上的 NVDA 仍然沒有驗證到（spec §13）。
