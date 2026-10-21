# Number group mode Review 紀錄

日期：2026-10-21。分支：`feat/number-group-mode`（`4c5183e..5ff442e`，22 個 commit），worktree `/workspace/WorldVoice-feat-group`。
依據：

- 規格 `docs/superpowers/specs/2026-10-21-feat-number-group-mode-design.md`（使用者決定 G1–G7、U1–U3；Q1–Q11 與 F1 採建議預設）
- 計畫 `docs/superpowers/plans/2026-10-21-feat-number-group-mode.md`（Review Focus 1–5）
- 進度帳本 `.superpowers/sdd/2026-10-21-feat-number-group-mode/progress.md`（5 個 `Ruling:`）
- 批次 review：batch 1（M1–M4）、batch 2（I1 `_moveSizer`、B2-M1–M5），皆回報已修

流程：審閱者 Fable 5.1，唯讀；測試、還原實驗與種子突變都在暫時 worktree（`scratchpad/wt-review`，審完已移除）進行，單一 pytest 行程加 3 GB MemAvailable 記憶體監控。NVDA 參考 `ref/nvda` 為 `7d25bc76e`。

`file:line` 以 `5ff442e` 為準。

## 結論

Ready to merge：**否，先修 Important 1。** Critical 0、Important 1、Minor 3。

程式與 spec 的 G1–G7、U1–U3 全部相符；計畫 Review Focus 五項各有測試，且都能抓到對應的錯誤；5 個 `Ruling:` 都合理；兩輪批次 review 的 Minor 與 I1 都已確實修好。唯一要擋 merge 的，是 U1／U2 在 scope「all」下對 OneCore（以及任何經由 NVDA `speechXml` 產生 SSML 的合成器）的影響：spec F2 與前一個功能的 review 都說「OneCore 會把 `BreakCommand` 子類別轉成 `<break>`」，這句話是錯的，實際上會把那句話剩下的內容整段丟掉。

## Critical

無。

## Important

### I1. scope「all」＋OneCore：`NumberBreakCommand` 讓 OneCore 丟掉第一個數字停頓之後的所有內容（相對 master 的回歸）

- **位置：** `addon/synthDrivers/WorldVoice/pipeline/__init__.py:271`（`number_wait_factor` 改送 `NumberBreakCommand`，U2）、`:387-394`（digit mode 的 `NumberBreakCommand`，U1）、`:379`（`GroupNumberBreakCommand`）；NVDA 端 `ref/nvda/source/speechXml.py:250-262`、`ref/nvda/source/synthDrivers/oneCore.py:54`、`:112-117`。
- **機制：** eSpeak（`espeak.py:204`）與 SAPI5（`sapi5.py:928`）用 `isinstance(item, BreakCommand)`，子類別沒問題。但 OneCore 的 `_OcSsmlConverter` 繼承 `speechXml.SsmlConverter`，其 `generateBalancerCommands` 用 **類別名稱** 找轉換函式：`getattr(self, "convert%s" % type(item).__name__)`；找不到 `convertNumberBreakCommand` 時，`log.debugWarning("Unsupported command")` 然後 **`return`**，整個 generator 結束，後面的文字與指令全部不送。`speechXml.py:307` 的 `convertBreakCommand` 只有在 `type(item).__name__ == "BreakCommand"` 時才會被找到。NVDA 在 `speech.manager` 與 `speech.speak` 都不會依 `supportedCommands` 過濾指令（`speech/manager.py:427-436`），所以子類別會原樣到達合成器。
- **審閱者實測：** 用 `ref/nvda/source/speechXml.py` 真正的 `SsmlConverter`（stub 掉 `logHandler`、`textUtils`、`speech.commands`）：
  - `["1", BreakCommand(10), "2", " and ", "3"]` → `<speak …>1<break time="10ms"/>2 and 3</speak>`
  - `["1", NumberBreakCommand(10), "2", " and ", "3"]` → `<speak …>1</speak>`，log：`Unsupported command: BreakCommand(time=10)`
- **失敗情境（預設值、只改 scope＝all、合成器 OneCore）：** 數字停頓預設 10 ms（`settings.py:109-116`、`:208-213`），`effective(False)` 在 scope「all」下保留它（`settings.py:232-256`）。朗讀「共 12 34 個」：master 送 `"共"`, `"12"`, B(10), `"34"`, `" 個"`，OneCore 讀完整句；本分支送 `"12"`, **NB(10)**, …，OneCore 只讀到「共 12」。digit mode 的「12」只剩「1」，group mode 的「12345」只剩「123」。相對 master，U2 讓 **預設設定下** 的數字停頓也踩到這個問題，而 master 只有非預設的 pair mode 與標點停頓（`PunctuationBreakCommand`，master 既有）會踩到。
- **影響範圍：** 只有 scope「all」且使用 OneCore（或任何以 `speechXml` 產生 SSML 的第三方合成器）的使用者；WorldVoice 自己（`compat/commands.py:15` 用 `isinstance`）、eSpeak、SAPI5 不受影響。scope 預設是「WorldVoice」，所以預設使用者沒有回歸。
- **建議修法（恢復 master 對其他合成器的行為，不改 WorldVoice 的輸出）：** 對 `ctx.supports_roles` 為 False 的序列，把所有 `BreakCommand` 子類別降成普通 `BreakCommand(item.time)`。最小改法是在 `_stage_handler`（`pipeline/__init__.py:796-806`）或新增最後一個 stage（排在 `speech_viewer` 之前，`STAGES`，`:825-835`）做一次轉換；也可以在三個產生子類別的地方依 `ctx.supports_roles` 選類別。`PunctuationBreakCommand` 一併處理，順便修掉 master 既有的同類問題。測試：
  1. stage 層：GENERIC_CONTEXT 下跑完整 `STAGES` 鏈，斷言每個 break 都是 `type(item) is BreakCommand`；WorldVoice context 下仍是子類別（既有測試已經鎖住）。
  2. 守門測試：像本次實測那樣載入 `ref/nvda/source/speechXml.py` 的 `SsmlConverter`，對 scope「all」的 pipeline 輸出做 `convertToXml`，斷言輸出含有每一段文字與 `<break …/>`。這個測試在 NVDA 升級、`speechXml` 改成 `isinstance` 時也還會通過。
  3. 同步更正 spec §11 F2、Q11 與 §9.5 手動項目 6 的說法（見 Minor M2）。

## Minor

### M1. spec 與前一輪 review 對 OneCore 的描述錯誤（文件）

- `docs/superpowers/specs/2026-10-21-feat-number-group-mode-design.md:670`（F2：「NVDA's eSpeak, SAPI5 and OneCore drivers turn the break into markup … `speechXml.py:307-308`」）與 `docs/superpowers/finish/2026-10-21-feat-number-and-punctuation-pause-review.md:74`（前一輪 review 寫「OneCore（`speechXml.py:307-308`）都用 `isinstance(item, BreakCommand)`」）都不正確，原因見 I1。使用者的 Q11（「keep U1 for every synth; decide on a mitigation only after manual item 6」）是建立在這個錯誤事實上的。
- 建議：修 I1 時在 spec §11 F2 加一段更正，並把 Q11 改成「其他合成器一律收到普通 `BreakCommand`」。

### M2. `nvda.po` 的 `#:` 參照行是手寫的，與目前行號不符

- `addon/locale/zh_TW/LC_MESSAGES/nvda.po:172-192`、`:616-620`：新條目的 `#:` 參照大多對，但 `"group"` 的 `__init__.py:480` 實際在 `:487`。既有條目本來就過時（例如 `"Number mode:"` 寫 `:131`，實際在 `:151`），所以這只是延續現況，`msgfmt --check` 也通過。
- 建議：不擋 merge；下次打包時用 `scons pot` 產生 `.pot`，`msgmerge` 回 `.po` 一次更新所有參照。

### M3. `_selected_number_mode` 在存檔時把「沒有選取」寫成 `"value"`

- `addon/globalPlugins/WorldVoice/speechSettingsDialog.py:270-275`、`:294`。B2-M4 的修法讓 `GetCurrentSelection() == -1` 時存 `"value"`。實務上到不了：未知的儲存值會選第 0 項（`:157-159`），wx.Choice 一旦有選取不會自己變成 `NOT_FOUND`。但若真的發生，一個原本是 `"group"` 的設定會被悄悄改成 `"value"`。
- 建議：不擋 merge。若要更保守，存檔時沒有選取就略過 `number_mode`（不寫），只在啟用狀態判斷上當作非 group。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 完整測試（§7） | `guarded_pytest.sh -q -p no:cacheprovider tests`（單一行程，3 GB 記憶體監控，`ref` → NVDA `7d25bc76e`） | **1926 passed、0 skipped**，2 warnings，54.81s；與帳本一致 |
| prek（§7） | `prek run --all-files` | 8 個 hook 全數 Passed，worktree 無變動 |
| 空白檢查 | `git diff --check master` | 無輸出 |
| 受保護路徑 | `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 兩者皆無輸出 |
| Co-Authored-By | `git log --format='%H %B' master..HEAD \| grep -ci co-authored` | 0；每個 commit 都有內文 |
| 跨驅動 import | grep `addon/synthDrivers/WorldVoice/driver/`（排除內層） | 只有 `driver/__init__.py:5` import core 的 `compat.voiceFacade`，無驅動互相 import |
| 翻譯 | `msgfmt --check -o /dev/null addon/locale/zh_TW/LC_MESSAGES/nvda.po` | 通過；`"group"`→群組、`"Group size:"`→每組位數：、`"group wait factor:"`→群組停頓參數：、`"Group wait factor"`→群組停頓參數，與 G6／Q5 一致；`pair`／`兩位` 在 `addon/`（`.py`、`.po`、`.md`）已無殘留（`pairwise` 與 chunker 的 "flag pairs" 不是）；四個 `_()` 都有 `# Translators:`，`test_group_strings_have_translator_comments` 鎖住 |
| readme 用詞 | 對照 `.po` 的面板名稱 | zh_TW readme 的「語音流程面板」「語音設定面板」與 `"Speech Pipeline"`→語音流程、既有 readme 第 33／51 行的「NVDA 語音設定面板」一致 |
| 還原關鍵 commit（暫時 worktree，把該 commit 的 `addon/` 檔案退回父 commit，跑本分支改到的 12 個測試檔） | `89e8623` clamp／confspec | 82 failed |
| | `e19d28f` pair→group 改名、`group_size` | 181 failed |
| | `8b8ba47` group mode | 82 failed |
| | `453582e` U3 未知模式→value | 8 failed |
| | `724ae36` U2 `NumberBreakCommand` | 36 failed |
| | `cff471d` U1 digit mode | 13 failed |
| | `e0c205d` Speech Pipeline 面板 | 15 failed |
| | `abc1609` Voice 面板 spin | 25 failed |
| | `3ea7aad` `_moveSizer`（I1） | 24 failed（fake `SizerItem` 在 Detach 後讀取會 raise，兩個呼叫點都抓到） |
| | `1bb5c5e` Voice 面板啟用規則 | 6 failed |
| | `dac1324` `minVal`／`maxVal` | 1 failed |
| | `ed12827` 面板存檔 selection −1 | 1 failed |
| 審閱者種子突變（18 個，同樣的測試集） | 群組改從右邊切；wait 0 不插 digit break；未知模式→`"number"`；拿掉 clamp；面板開啟時不套用啟用狀態；Voice 面板拿掉 `evt.Skip()`；語音切換後不重套用；Voice 面板 −1 讀 `_nummods[-1]`；`_moveSizer` 先 Detach 再讀；Speech 面板 −1 讀 `number_mode_value[-1]`；group size 寫死 2；`number_wait_factor` 送普通 `BreakCommand`；第一組丟掉正負號；spin 插在 mode list 前面；spin `min=0`；群組停頓時間寫死 0；`effective()` 不再歸零 `group_wait_factor`；Voice 面板把 spin 值存成字串 | **18 個全部被殺**（各 1–23 個測試失敗） |
| mutmut 的 5 個存活 mutant（spec §14） | 讀 `_translate_number`（`pipeline/__init__.py:354-397`）與 `iter_number_speech_segments_mode`（`:425-457`） | 同意皆為等價：`digits[0]` 來自 `_NUMBER_RE` 的 match，只會是正負號或數字；兩個布林旗標只當真值用；`preceding_text` 只經 `.endswith(".")` 讀取，`""` 與 `"XXXX"` 同為 False |
| OneCore 指令分派（I1） | 以 `ref/nvda/source/speechXml.py` 真正的 `SsmlConverter` 跑 `["1", NumberBreakCommand(10), "2", " and ", "3"]` | 只輸出 `<speak …>1</speak>` 並記 `Unsupported command`；普通 `BreakCommand` 則輸出完整 `<break time="10ms"/>` |
| 計畫 Review Focus 1–5 | 1 Speech 面板 −1：`test_pipeline_panel_counts_no_selection_as_not_group`、`…_saves_no_selection_as_value`；2 Voice 面板 −1：`test_a_mode_missing_from_the_list_counts_as_not_group`；3 前導零：`test_group_mode_keeps_leading_zeros_and_every_digit`（3 個 id）；4 數字黏字母／多字元數字詞：`test_digit_mode_breaks_only_between_adjacent_digits`、`test_digit_words_are_kept_verbatim_one_per_item`；5 範圍外的儲存值：`test_pipeline_panel_shows_an_out_of_range_stored_size_within_the_spin_range` | 五項都有測試，且種子突變 Mh／Mj／Mm／Mb／Md 證實能抓到 |
| 進度帳本的 `Ruling:` | T2（confspec 迴圈排除 `group_size`）、T3（參數化 3 個 id）、T6（M1 併入）、Batch 2（`_moveSizer` 兩個呼叫點）、T12（先修 Minor 再跑 mutmut） | 皆合理；T2 的 `group_size` 由 `test_group_settings_replace_the_pair_wait_and_add_the_size` 另外鎖住 |
| NVDA `NumericDriverSetting` 語意（M4） | `ref/nvda/source/autoSettingsUtils/driverSetting.py:71-119` | `minVal`／`maxVal` 只進 `_get_configSpec`（`useConfig=False` 時不會用到）與 `maxVal = max(maxVal, defaultVal)`；本分支傳入的都是 0／100，和預設相同，所以沒有可見變化，純屬一致性 |
| wx 語意（`_moveSizer`） | wxWidgets `wxSizer::Detach(wxSizer*)` 會刪除 `wxSizerItem` | 先讀 proportion／flag／border 再 Detach 是對的；master 的標點字元編輯框也是同一個 bug，一併修掉 |
| wx／NVDA 假物件的保真度 | `tests/ui_harness.py:118-138`（`SpinCtrl`、`SelectOnFocusSpinCtrl` 為其子類別）、`:148-175`（`SizerItem` Detach 後 raise）、`:277-295`（`fire`：先控制項、後面板，後綁定者先跑，只有 `Skip()` 才往下）、`:383-388`（`Choice` 綁 NVDA 式寫入器） | 與 `ref/nvda/source/gui/nvdaControls.py:103-129`（`SelectOnFocusSpinCtrl(wx.SpinCtrl)`，關鍵字 `min`／`max`／`initial`）、`gui/settingsDialogs.py:1333-1356`（`StringDriverSettingChanger` 先 `evt.Skip()` 再寫）、`:1508-1511`（`lCombo.Bind(EVT_CHOICE, …)` 綁在控制項上，WorldVoice 後綁所以先跑）相符。fake `SpinCtrl` 不 clamp 已有 docstring 註明；面板傳入的值已經過 `convert` clamp |
| 面板三個時點 | `VoiceSettingsDialogs.py:33-42`（開啟）、`:44-47`（`EVT_CHOICE`）、`:49-60`（啟用規則，−1 不算 group）、`:257-259`（`_updateValueForControl`，語音切換與設定環改變後的語音切換） | `super().makeSettings` 期間的 `_updateValueForControl` 只設到 slider（spin 尚未存在，`getattr` 回 None），`_bindNumberModeChoice` 在 spin 建好後再套一次；`tab_after is nummodList`，sizer 緊接 `nummod` 之後 |
| 儲存的 `"pair"`（U3） | `test_a_stored_pair_mode_reads_numbers_as_values`、`test_an_unknown_number_mode_is_stored_and_read_as_value`、`test_pipeline_panel_enables_group_controls_for_the_stored_mode[pair]` | 讀成 value；面板與設定環都顯示 value；`nvda.ini` 裡的 `pair` 與 `pair_wait_factor` 留著不讀 |
| 暫時 worktree 清理 | `git worktree remove` | 已移除；`git worktree list` 只剩主 checkout 與 `WorldVoice-feat-group` |

Linux 上沒驗到的：Windows NVDA、實際音訊、各引擎 SDK；spec §9.5 的 6 個手動項目全部未跑。本分支未打包。

## 使用者還沒確認的使用者可見預設

spec §12 全部是「Decided by orchestrator with the recommended default」，加上本次 review 的發現：

1. **I1 的修法（新）：** scope「all」下其他合成器一律收到普通 `BreakCommand`（恢復 master 行為）。這取代 Q11「keep U1 for every synth」的前提。
2. **Q1：** Voice 面板的「每組位數」放在 Number Mode 之後，因此 Global／Number wait factor 夾在它和「群組停頓參數」slider 之間。
3. **Q2：** spin 控制用 NVDA 的 `SelectOnFocusSpinCtrl`（取得焦點時全選數值）。
4. **Q3：** `convert` 對所有整數設定做 clamp（既有鍵仍是 0–100，使用者看不到差異）。
5. **Q4／F1：** 手動改壞 `nvda.ini` 的 `group_size`（0、11、abc）時維持 NVDA 的驗證錯誤：WorldVoice 載入失敗、stage 被略過、語音流程面板打不開；不做回退預設。
6. **Q5：** 設定環與 Voice 面板的標籤「Group wait factor」→「群組停頓參數」（無冒號）。
7. **Q6：** 在 Voice 面板切到別的合成器時，「每組位數」顯示在 NVDA 控制項之後、標點字元之前，維持啟用並於 Save 時寫入。
8. **Q8：** `readme.md` 與 `addon/doc/zh_TW/readme.md` 新增群組模式一條；沒有 changelog。
9. **Q10：** 驅動 id `groupwaitfactor`（會出現在 `nvda.ini` 的 `[speech][WorldVoice]` 與 pipeline log）。
10. **U3 的效果：** 原本用 pair mode 的使用者升級後聽到的是整數朗讀，沒有提示；要恢復舊行為得自己選群組模式並把每組位數改成 2（預設 3）。`pair_wait_factor` 的值也不會搬過來，群組停頓從 0 開始。
11. **U1 的效果（spec F3）：** digit mode 在數字停頓 0 時，每個數字都是獨立 segment（只剩交接間隙）；用 `unicode.dic` 把數字對應成中文字的使用者，數字間的停頓從「中文間停頓」改為「數字停頓」。

Windows／NVDA 手動項目（spec §9.5，未驗證）：

1. 群組模式 1／2／3／10、群組停頓 0／50，聽 `12345678`、`-1234567`、`12.5`、`0912345678`。
2. digit mode 數字停頓 0／40，含 `unicode.dic` 對應中文字的情況。
3. 升級：`number_mode = pair`、`pair_wait_factor = 40` 的 profile，兩個面板與設定環顯示 value、設定環可切換不出錯、log 無錯誤。
4. 語音流程面板：Tab 順序、NVDA 讀出「每組位數：」與數值、非群組模式時兩個控制項被 Tab 跳過並報為無法使用、方向鍵切換模式即時更新。
5. Voice 面板：spin 在 Number Mode 之後（版面與 Tab）、**NVDA 是否正確讀出它的標籤**（控制項用 `MoveAfterInTabOrder` 搬動，標籤留在原位，與標點字元編輯框同一做法，Windows 上從未驗證）、開啟與切換模式時的停用狀態、設定環改模式後再換語音、Save→Cancel 保留、Cancel 不存還原。
6. scope「all」＋eSpeak NG／OneCore／SAPI5：修完 I1 之後再跑，確認數字不黏在一起、句子不被截斷。
