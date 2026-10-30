# Voice engine filter Review 紀錄

日期：2026-10-30。分支：`feat/voice-engine-filter`（`650291e..32f3789`，10 個 commit：spec 2、plan 1、實作 6、文件 1）。
依據：

- 規格 `docs/superpowers/specs/2026-10-30-voice-engine-filter-design.md`
- 計畫 `docs/superpowers/plans/2026-10-30-voice-engine-filter.md`
- 進度帳本 `.superpowers/sdd/2026-10-30-voice-engine-filter/progress.md`

流程：一般流程（DEVELOPMENT_WORKFLOW.md §3.3）。審閱：Fable 5.1，唯讀，未修改任何原始碼或測試；只在 scratchpad 的複本上做還原與突變測試。基準 `master` 3638 passed、0 skipped。

## 結論

Ready to merge：**Yes**。Critical 0、Important 0、Minor 4。

實作與 spec 一致（R1、R2、R4、D1–D4、D7–D10），和 `master` 相比沒有找到回歸；NVDA 整合點（`availableVoices` 快取、settings ring 重建與起始位置、Cancel、handler 數量、面板重整、換 synth、設定檔切換、`loadSettings` 的語音驗證、`languageIsSupported`）逐一對照 `ref/nvda/source` 與 `release-2024.1`／`release-2025.1` 都成立。四個 Minor 都是測試缺口或文件措辭，不影響合併。

## Review Focus（plan §Review Focus）逐項檢查

| # | 項目 | 結果 |
| --- | --- | --- |
| 1 | 介面語言與語音語言拼法不同（`zh-TW`、`ZH_tw`、`pt_BR` vs `pt-br`、`en` vs `en_US`） | `test_exact_match_folds_separator_and_case`、`test_primary_language_comes_before_the_first_voice` 存在且有效：把摺疊改回 `spec.language == language`（還原 M17）3 個案例失敗；拿掉主要語言步驟（M12）4 個案例失敗。 |
| 2 | 其他引擎或已不存在的 role 語音 | `test_a_role_voice_outside_the_engine_is_ignored`：把引擎限制改成 `if role_voice is not None`（M13）後 2 個參數案例與 Hypothesis 測試失敗。 |
| 3 | 語言為空的語音只當最後備援 | `test_a_voice_without_language_is_matched_only_as_fallback` 通過，但該規則在實務上無法觀察（見 Minor 2）：拿掉 `spoken` 篩選（M18）所有測試仍通過。產品行為沒有問題，只是測試宣稱的保護不存在。 |
| 4 | `loadSettings` 之前（`_voice is None`）role 語音屬於另一個引擎 | `test_before_load_settings_the_engine_follows_the_role_voice`：把 `_get_engine` 改成讀 `default_voice_name`（M11）後失敗。對照 `synth:443-444`、`:455-458` 與 NVDA `_get_language`（`sdh:253-254`），`availableVoices[self.voice]` 必定存在。 |
| 5 | 選到目前的引擎 | synth 路徑 `test_choosing_the_current_engine_changes_nothing`：拿掉 `if value == self.engine: return`（M2）後失敗。面板路徑 `test_choosing_the_current_engine_keeps_the_voice` 測的是測試替身自己的 setter 守衛（見 Minor 3），帳本已承認它在實作前就通過。 |

## 進度帳本 `Ruling:` 評估

| Ruling | 評估 |
| --- | --- |
| P1 精確語言步驟摺疊 `-`／`_` 與大小寫 | 合理。eSpeak 回報 `pt-br`、`en-gb`，不摺疊會落到主要語言步驟選到第一個 `pt`／`en` 語音。測試 M17 證實有效。 |
| P2 工廠用 `SynthDriver._engineSetting()` 靜態方法 | 合理。`test_naming_layers` 要求 host 方法 mixedCase；`_driverSettings` 呼叫它，`test_voice_settings_transaction.py` 的名單同步加入。 |
| P3 `test_nvda_setting_ids_are_nvdas` 扣掉 `{"uwv", "engine"}` | 合理。`engine` 是 WorldVoice 自己的 id，和 `uwv` 同類。 |
| P4 role 測試放在 `test_role_panel_ui.py` | 合理。`setMainVoice` 是 `makeSettings` 裡的 closure，只有這個 fixture 跑到真正的 `makeSettings`。 |
| P5 manager 測試直接傳 `language` | 合理。§3.2／§3.4 的簽章就是 `(engine, language)`，synth 端傳 `languageHandler.getLanguage()`。 |
| Task 3 transaction 測試名單加 `_engineSetting` | 合理，純測試 harness。 |
| Task 4 `test_entry_point_imports_real_ledger_and_completion_policy` 的 stub 加 `changeVoice` | 合理。NVDA 2024.1 到參考版都有 `synthDriverHandler.changeVoice`（`sdh:439`）。 |
| Task 5 三個面板測試實作前就通過 | 誠實記錄；engine 專屬的三個（cancel、Unbind、重建語音清單）確實先紅後綠，M4／M5／M7 還原後也失敗。 |
| Task 5 harness 補 `Event.GetSelection`、stand-in `onDiscard`、`sizerDict={}` | 合理。`onDiscard` 的 stand-in 和 NVDA `sd:1621-1628` 一致（先 Unbind 每個 `<id>List`，再 `loadSettings`）。 |
| Task 5 `self.driver.engine = ...` 取代 `setattr` | 合理，ruff B010；效果相同。 |
| Task 6 `test_role_panel.py` 改用 `changeVoice` 替身 | 合理。 |
| Task 7 ru／uk readme 用英文標籤 "Speech engine" 加註解 | 合理：這兩個語言的 .po 沒有翻譯，使用者看到的就是英文。日後 ru／uk 翻譯補上時要同步改 readme（已記在帳本）。ring 的譯名與 NVDA 自己的譯名一致（見驗證表）。 |
| Task 8 mutmut 22 個 mutant、20 killed、2 存活且等價 | 我在 scratch 複本重跑結果相同；兩個存活者確為等價（見驗證表）。 |

## Critical

無。

## Important

無。

## Minor

### 1. 面板測試分不出 `changedSetting="engine"` 和 `changedSetting=None`

- 位置：`tests/test_voice_settings_panel.py:759-772`（`test_choosing_an_engine_switches_the_voice_and_rebuilds_the_voice_list`）；受測程式 `addon/synthDrivers/WorldVoice/ui/voicePanel.py:51`。
- 失敗情境：日後有人把 `self.container.updateDriverSettings(changedSetting="engine")` 改成 `None` 或 `"voice"`，NVDA 的迴圈就不再跳過 engine 列，WorldVoice 的 `_updateValueForControl`（`voicePanel.py:253-283`）會對**正在用方向鍵操作、有焦點的** engine 下拉清單呼叫 `SetItems` 再 `SetSelection`。spec §3.5 明確要求 engine 控制項保持不動（`sd:1564-1566`），但目前的測試在還原 M6（`changedSetting=None`）後 49 個測試全部通過，抓不到。
- 建議：在 harness 的 `Choice` 記錄 `SetItems` 呼叫，測試中在觸發 `EVT_CHOICE` 後斷言 `engineList` 沒有被 `SetItems`，而 `voiceList` 有一次。

### 2. `pick_engine_voice` 的「空語言只當備援」規則無法觀察

- 位置：`addon/synthDrivers/WorldVoice/voices/engineFilter.py:32`（`spoken = [spec for spec in own if spec.language]`）；`tests/test_engine_filter.py:93-96`。
- 說明：`_folded("")` 與 `primary_language("")` 都只會等於空字串，而 `languageHandler.getLanguage()` 不會回傳空字串；所以就算拿掉篩選（還原 M18：`spoken = list(own)`），16 個測試（含 `test_a_voice_without_language_is_matched_only_as_fallback`）全部仍通過。產品行為正確，只是 docstring 和測試宣稱了一條實際上由別的條件保證的規則。
- 建議（擇一）：(a) 加一個能區分的案例，例如引擎 `C` 有 `C:a en`、`C:x ""`，`pick(specs, "C", "", None)` 期望 `C:a`；或 (b) 拿掉篩選與 docstring 那句，讓程式碼和測試一致。優先度低。

### 3. RF5 的面板路徑測試只測到測試替身

- 位置：`tests/test_voice_settings_panel.py:725-729`（`EngineDriver.engine` setter 自己做 `if value != self.engine`）、`:775-780`。
- 說明：真正的守衛在 synth 的 `_set_engine`（`__init__.py:447-448`），由 `test_engine_setting.py::test_choosing_the_current_engine_changes_nothing` 守住（M2 失敗）。面板測試在替身裡複製了同樣的守衛，所以它只能證明「面板不會另外改語音」，不能證明產品守衛存在。帳本已坦承。
- 建議：不必改；若要讓面板測試有意義，可讓替身的 setter 無條件換語音，改為斷言 `driver.engineSets == ["A"]` 且面板沒有重整 voice 清單以外的東西。

### 4. readme 「語音引擎本身只能在語音設定面板中切換」不完全準確

- 位置：`readme.md:89`、`:95`，以及 `addon/doc/{ru,uk,zh_CN,zh_HK,zh_TW}/readme.md` 對應兩處。
- 說明：WorldVoice 語音角色面板把主要語音指派成另一個引擎的語音時（spec §3.6、§7 第 7 項，`keepMainLocaleVoiceConsistent` 開啟），以及切換設定檔時，引擎也會跟著變。spec §1 的說法是「快速語音設定沒有引擎項目；要換引擎請用語音設定面板」，比較精確。
- 建議：改成「快速語音設定沒有語音引擎項目；要切換語音引擎，請使用 NVDA 語音設定面板」（各語言同步）。

## 審閱者自行驗證的項目

| 項目 | 結果 |
| --- | --- |
| `python3 -m pytest -q tests`（worktree，序列） | 3679 passed、0 skipped（基準 3638／0，+41），與實作者回報相同 |
| `prek run --all-files`（worktree） | 8 個 hook 全部 Passed，`git status --short` 無變動 |
| `git diff --check master` | 無輸出 |
| 受保護路徑：`git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' .../driver/sonic/ .../script_data.py .../unspaced_common_data.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural`；`git diff --stat master -- addon/synthDrivers/WorldVoice/driver` | 三者皆無輸出：沒有動到任何驅動（含外層 wrapper） |
| `git ls-files ref` | 無輸出，symlink 未被 stage |
| 驅動可單獨安裝、外掛相容 | 新模組 `voices/engineFilter.py` 只 import `..locales`、`..runtime.models`；manager 透過 `catalog.engine_voice_infos` 分組，依 `VoiceSpec.engine`（adapter 從 `Voice.engine` 類別屬性取得）；`ref/Neural/Neural/__init__.py` 以 `engine = "Neural"` 宣告，`test_a_plugin_is_listed_under_its_engine` 驗證列在 `Neural` 下、文字保留 ` [Neural]` |
| NVDA 整合（`ref/nvda/source`） | `sdh:274-277` 快取確認，WorldVoice 的 `_get_availableVoices` 由 `AutoPropertyType` 建成子類別自己的 `Getter`（`baseObject.py:76-94` 掃描 namespace 裡所有 `_get_*`；`cachePropertiesByDefault=False`，`baseObject.py:144`）；`sdh:386-404` `loadSettings` 沒有 `availableVoices` 成員檢查，只靠 `_set_voice` 拋 `LookupError`（`manager:192-193` 用完整 `voice_infos` 驗證）→ F10 成立；`sdh:439-449` `changeVoice` 不寫 config、重建 ring、載入語音字典；`sdh:364-384` `initSettings` 的 `hasattr(self, "engine")` 走 `_get_engine` 不會拋；`ring:75-77` 快照、`ring:130`／`:232` 用 `initialSettingsRingSetting`、`ring:197-240` 只列 `availableInSettingsRing`；`sd:1333-1356` voice 分支、`sd:1462-1515` 字串控制項設 `_<id>s`／`<id>List` 並綁一個 handler、`sd:1546-1575` 跳過 `changedSetting`、`sd:1601-1619` 不重建清單、`sd:1621-1628` Cancel 對每個 `<id>List` Unbind 一次後 `loadSettings`、`sd:1406-1408` `settingsStorage` 就是 synth；`types.py:330-344` 字典檔名取自 `availableVoices[voice].displayName`（文字未變）；`autoSettings.py:130-166` `useConfig=False` 不進 spec 也不存檔；`sdh:339-362` `languageIsSupported` 讀 `availableLanguages`（已覆寫為全部引擎）；`sdh:582-600` 設定檔切換走 `loadSettings(onlyChanged=True)` → `changeVoice` |
| NVDA 2024.1／2025.1（`git show release-2024.1:…`、`release-2025.1:…`） | `_makeStringSettingControl(setting, settingsStorage)` 簽章、`StringDriverSettingChanger(driver, setting, container)`、`changeVoice`、`_get_availableVoices` 快取、`loadSettings`、ring 皆相同；2024.1 的 `onDiscard` 對 `supportedSettings` 每個字串設定做 `getattr(self, f"{id}List").Unbind`，`engineList` 一定存在 |
| wx `Unbind(wx.EVT_CHOICE)` 語意 | 不給 handler 時 Phoenix 走 `Disconnect(id, lastId, type, EventThunker)`，移除一個最近綁定的 Python handler；覆寫時只有 NVDA 的一個，移除後綁上 `_EngineSettingChanger`，恰好一個，Cancel 再移除它 |
| 執行緒 | `_EngineSettingChanger.__call__` 在 wx 主執行緒（EVT_CHOICE）；`speech.cancelSpeech()` → `synth.cancel()` → `manager.cancel()`，接著 `changeVoice` → `_set_voice` → `default_voice_name` setter，與 NVDA 自己的語音切換路徑同一執行緒；沒有新的鎖、沒有背景執行緒 callback；語音角色面板的 `changeVoice` 在對話框儲存時於主執行緒執行 |
| 其他寫入語音的路徑 | `grep` 整個 add-on：只有 `_set_voice`（NVDA 路徑）和 `role.py:44` 的 `changeVoice`；沒有別處寫 `default_voice_name`，所以沒有新的「ring 快照過期」路徑 |
| `availableVoices` 的其他讀者 | add-on 內 synth 以外沒有（內層驅動讀的是自己的）；NVDA 只有 `_get_language`、`_get_availableLanguages`（已覆寫）、`languageIsSupported`、語音字典載入、面板、ring |
| 快速鍵 `&H` | NVDA 語音面板字串（`sd:1700-1960`、`sdh:110-215`）與 WorldVoice 標籤都沒有 `&h`／`&H`；NVDA zh_TW `(&H)` 的 10 個 msgstr 都不在語音面板 |
| 翻譯與用詞 | zh_TW 「語音引擎(&H)」與 .po 既有 `(&X)` 風格一致；readme 用 NVDA 自己的譯名：zh_TW 「快速語音設定」、zh_CN 「循环切换合成器设置」（`user_docs/*/userGuide.xliff`）、ru 「кольцо настроек синтезатора」、uk 「кільце параметрів／налаштувань синтезатора」（NVDA .po）；`#:` 行號 `__init__.py:130` 正確；`# Translators:` 註解緊貼 `_()` |
| 還原測試（scratch 複本，18 項單一還原，逐一套用、跑對應測試、復原） | 16 項被抓到：M1 改回 NVDA 快取本體、M2 拿掉同引擎守衛、M3 ring 起始改回 NVDA 算法（2 個測試）、M4 不 Unbind（3 個）、M5 不 cancel、M7 不重整、M8 role.py 改回 `current.voice = name`（2 個）、M9 `availableLanguages` 只列目前引擎、M10 引擎順序反轉（2 個）、M11 engine 改讀 `default_voice_name`、M12 拿掉主要語言步驟（4 個）、M13 role 不檢查引擎（3 個）、M14 engine 進 ring（3 個）、M15 `useConfig=True`（2 個）、M16 engine 排在 Voice 之後（3 個）、M17 不摺疊（3 個）。2 項存活：M6 `changedSetting=None`（Minor 1）、M18 `spoken = list(own)`（Minor 2） |
| mutmut（scratch 複本，`source_paths` 縮到 `engineFilter.py`，測試選 `test_engine_filter`／`test_runtime_composition`／`test_plugin_voice_contract`，`--max-children 3`，MemAvailable < 3 GB 守衛未觸發） | 22 個 mutant：20 killed、2 survived、0 timeout，與帳本相同。存活者 `x__folded__mutmut_1`（`.lower()`→`.upper()`：兩邊都用同一函式摺疊，等價）、`x_pick_engine_voice__mutmut_4`（`LookupError(engine)`→`LookupError(None)`：只差訊息，契約是例外型別，等價） |
| `git worktree list` | 只有原有四個；我的複本是 scratchpad 內的普通目錄，未新增 worktree，審閱結束後已刪除 |

## 使用者還沒確認的使用者可見預設

spec 標為「orchestrator 以建議預設決定，使用者可在 merge 前推翻」的項目，以及本分支帶來的其他可見行為：

1. **D1** 引擎由目前語音推導，不另外儲存；nvda.ini 與設定檔沒有新欄位。
2. **D2** 快速語音設定（settings ring）沒有「語音引擎」項目；只能在 NVDA 語音設定面板切換引擎。
3. **D3** 引擎清單顯示內部名稱：`Cerence`、`Espeak`、`OneCore`、`RHVoice`、`SAPI5`、`VE`、外掛如 `Neural`，依字母排序（例如顯示 `Espeak` 而不是 `eSpeak`）。
4. **D4** 標籤 `Speec&h engine`／「語音引擎(&H)」（Alt+H）。注意 WorldVoice 自己的設定裡已有一個「語音引擎」面板（啟用／停用引擎、需重啟），兩者同名；readme 以「NVDA 語音設定面板」區分。
5. **D7** 切換引擎時選語音的順序：該語言的 role 語音（若屬於該引擎）→ 語言完全相符（摺疊 `-`／`_` 與大小寫）→ 主要語言相符 → 該引擎第一個語音。
6. **D8** `availableLanguages` 仍列出所有引擎的語言，所以 NVDA「切換到不支援的語言時回報」不會把其他引擎 role 語音會講的語言報成不支援。
7. **D9** 語音角色面板改以 NVDA `changeVoice` 設定主要語音：新的副作用是語音字典會跟著主要語音改變（以前不會），快速語音設定也會重建。
8. **D10** 切換引擎時 `keepMainLocaleEngineConsistent` 的角色修剪行為不變（立即修剪、Cancel 不會還原）；另開分支修正。
9. **R2 的連帶效果**：NVDA 的 `availableVoices` 只剩目前引擎的語音，所以語音面板的「語音」清單、快速語音設定的「語音」項目，以及任何讀 `getSynth().availableVoices` 的第三方附加元件，看到的都只有目前引擎的語音。
10. 切換引擎時 NVDA 立即停止語音並以新語音朗讀新引擎名稱；每按一次方向鍵就切換一次（和「語音」清單一樣）。
11. ru／uk readme 以英文 "Speech engine" 稱呼這個控制項（這兩個語言的介面也會顯示英文）。
12. 快速語音設定重啟 NVDA 後的起始項目仍是「速度」（WorldVoice 覆寫了 `initialSettingsRingSetting`，否則會因為多了不在 ring 的 engine 設定而往後偏一格）。

## 未在 Linux 驗證（Windows／NVDA 手動項目）

spec §7 的手動清單 1–10 全部未驗證：真實 NVDA 面板的焦點與朗讀、`Alt+H`、方向鍵切換引擎時的停頓與朗讀、zh_TW 介面下的語音選擇、Cancel／OK／重啟後的引擎、ring 只在引擎內循環、舊語音字典仍適用、語音角色面板改主要語音後 ring 與面板跟隨、「回報不支援的語言」、Neural 外掛、換 synth 與設定檔切換。Linux 測試只覆蓋受控的 NVDA 與 wx 邊界。

## 工作區備註

- 主 checkout `/workspace/WorldVoice` 未動；review 開始時主 checkout 既有的未提交變更（`M buildVars.py`、`D docs/superpowers/finish_task.md`、未追蹤的 `DEVELOPMENT_WORKFLOW.md`、`cons.md`、`diff.md`、`syn.md`）與本分支無關。
- 未打包、未 push。
