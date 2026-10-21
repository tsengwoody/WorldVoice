# 數字與標點停頓（feat/number-and-punctuation-pause）Review 紀錄

日期：2026-10-21。分支：`feat/number-and-punctuation-pause`（`master` `133cb1e..4992663`，15 個 commit；worktree `/workspace/WorldVoice-feat-pauses`）。
依據：

- 規格 `docs/superpowers/specs/2026-10-21-feat-number-and-punctuation-pause-design.md`（§4.1–§4.4 的行為規則全部由使用者決定；F1 由使用者決定為選項 B）
- 計畫 `docs/superpowers/plans/2026-10-21-feat-number-and-punctuation-pause.md`（含「Implementation notes」、Deviations 與 mutmut 存活表）

流程：

- 審閱：sub agent，模型 Fable 5.1，依 `DEVELOPMENT_WORKFLOW.md` §3.3 唯讀執行。可跑測試；還原實驗與突變實驗只在自己加的兩個暫時 worktree（scratchpad 底下的 `wt-rev`、`wt-mut`）進行，結束後已移除。
- 修正與複核：尚未啟動，由協調者決定。

## 第 1 輪

### 審閱者（Fable 5.1）結論

Ready to merge：**Yes**，但 Important 1 是協調者代定、會改變預設行為的規則，建議先讓使用者看過再 merge。Critical 0、Important 1、Minor 6。

程式變更集中在 `addon/synthDrivers/WorldVoice/pipeline/__init__.py`（`_both_numbers` `:151-157`、`_split_spaced_numbers` `:199-226`、`number_wait_factor` `:238-256`、`_translate_number` `:355-356`、`inject_punctuation_pause` `:517-529`）、`pipeline/settings.py:162`、兩個面板與 `pyproject.toml`。我逐條核對了 spec §4.1–§4.4 的每一個使用者決定、§5 的三張表、§6 的 stage 順序互動與 §8 的相容性說明，並在暫時 worktree 把七個修正 commit 的原始碼逐一還原，確認對應的測試都會失敗。

### 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 全套測試（分支，`ref` 指向主 checkout 的 NVDA `7d25bc76e`） | `python3 -m pytest -q tests`（單程序，MemAvailable < 3 GB 即中止的 guard；從未觸發） | **1818 passed、0 skipped**，51.4 s，與計畫相符 |
| hook | `prek run --all-files` | 8 個 hook 全數 Passed |
| 空白 | `git diff --check master` | 無輸出 |
| 受保護路徑 | `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 兩者皆無輸出 |
| Co-Authored-By | `git log master..HEAD --format=%B` grep | 0 |
| 跨驅動 import | diff 新增行中 `import.*driver\.` | 無 |
| 可翻譯字串 | diff 中 `_(`、`pgettext`、`ngettext`、`# Translators`；`git diff --stat master -- addon/locale` | 無新增或修改；`.po` 未動。被刪的 `onRemovePunctuationCharactersChange` 不含字串 |
| 修正是否真被測試抓到 | 暫時 worktree `wt-rev`，對每個修正 commit 用 `git show <c> -- addon \| git apply -R` 只還原原始碼，跑相關測試檔 | `e6fd0fe`（fullmatch）6 failed（3 個單元案例 + `1.2.3 4` + N1 + N4）；`72ce60e`（pair 0）4 failed（含 N6）；`1ad4297`（標點開關）13 failed（含 P1、P2）；`de05af2`（Pipeline 面板）3 failed；`31a17b1`（Voice 面板）3 failed（含 voice 切換案例）；`e78e6ba`（預設清單）2 failed；`51becea`（切分）15 failed（含 N2）。其餘測試全數通過 |
| N1／N7 是否分得出選項 A 與 B | `wt-mut` 把 `joined` 條件改成 `gap.isspace()`（選項 A），只跑 `tests/test_pipeline_pause_properties.py` | **N1 與 N7 兩個 failed**，其餘 10 個 property 通過：兩個 property 確實只在選項 B 成立。全套跑時單元案例 `02 2345-6789` 先抓到 |
| 自選突變（套在 `wt-mut` 的乾淨複本） | M1 去掉 `index + 1 not in glued`；M2 去掉 `index not in glued`；M4 joined 時仍 yield 空白；M5 `glued` 只標一側；M6 `_both_numbers` 前項改回 `match`；M7 尾端允許空片段；M8 `boundary_pause` 忽略 pending break | 七個都被抓到（M1、M5 由 `3-1 2`／`02 2345-6789` 單元案例，M4、M7 由 `1 2`，M6 由 `12abc`，M8 由 P3）。只跑 property 檔時也全部被抓到：M1 由 N7；M2 由 N1、N2；M5 由 N1、N2、N7；M6 由 N1、N4；M8 由 P3、P4 |
| 等價突變對照 | M3 `gap.isspace()` → `not gap.strip()` | 149 passed：確為等價（空 gap 已被 `glued` 排除），不是測試漏洞 |
| mutmut 存活表抽查 | 直接套用 `inject_punctuation_pause` 64（`kind == "XXtextXX"`）與 94（`emit(previous, None, False)`），跑 149 個 pipeline 測試 | 各 149 passed：**確為等價**。其餘 8 個以讀碼確認（見下） |
| deep profile（分支原碼） | `HYPOTHESIS_PROFILE=deep pytest tests/test_pipeline_pause_properties.py -k "N1–N4、N7、P4"`（各 20000 例） | 6 passed，150.2 s（計畫記 150 s） |
| 切分演算法邊角與效能 | scratch 腳本直接執行 `_split_spaced_numbers`（`python3 -I`） | `""`→`[]`；`"1​2"` 不切（零寬空白不是 whitespace）；`"+1 +2"`→`+1`,`+2`；`"1+2 3"`、`"1 2+3"`、`"1 - 2"`、`"1. 2"`、`".5 .6"`、`"1 .5"` 不切；`"1..2 3"`→`1..`,`2`,`3`；阿拉伯文數字與全形數字不切。效能：20 萬個以空白分隔的數字 0.31 s、100 萬個連續數字 0.005 s、20 萬個 `1-` 黏連 0.19 s、30 萬個 `1.` 0.11 s；全部線性，regex 無回溯風險 |
| 實作者發現（PuB 緊鄰既有 break）是否既有 | `wt-rev` 把 `pipeline/__init__.py` 換成 `master` 版本，跑同一組案例 | wait 40 時 `master` 與分支輸出逐項相同：`["a", B, ". b"]` → `a`,B,`.`,PuB,` b`（remove off）／`a`,B,PuB,` b`（remove on）。**確為既有行為**；差別只在 wait 0 時分支也會產生 PuB(0)（2-2 的結果） |
| 暫時 worktree 清理 | `git worktree list` | 只剩原有四個；`wt-rev`、`wt-mut` 已 `git worktree remove` |

Linux 上沒驗到的：Windows NVDA、實際音訊、各引擎 SDK；spec §9.4 的 8 個手動項目全部未跑，特別是項目 7（scope「all」下 eSpeak NG／OneCore／SAPI5 對 0 ms break 的處理，F2）。

### 正確性與 spec 逐項核對

**數字（§4.1）**

- **1a**（`:151-157`）：`fullmatch` 兩側都用。`["12abc","3"]`、`["1.","2"]` 不停、`["-3.5","4"]` 停，測試 `test_number_wait_breaks_only_between_whole_numbers` 涵蓋。
- **1b**（`:199-226`、`:252-256`）：順序是 `_remove_space` → `_split_numbers` → `_insert_between`，與 spec 的四步相同；wait ≤ 0 原樣回傳（N5）。切分規則：`glued` 把空 gap 兩側的 match 都標為不可切；`joined[i]` 只在 gap 非空、全是 whitespace、且兩側都不在 `glued` 時為 True；只有 joined 的 match 被單獨 yield，其餘文字逐字保留，絕不 yield 空片段。spec §4.1 表格 12 列與 F1 的三列全部在 `SPLITS` 中，並額外加了 tab、U+3000、NBSP。
  - 「break 只出現在被移除的空白處」：我推導過——verbatim 片段若緊接在 standalone match 之後，開頭不可能是數字（regex 貪婪）也不可能是帶號數字（否則會是空 gap → glued → 前者不 standalone）；若緊接在 standalone match 之前，結尾必是空白或非數字文字。所以兩個相鄰 `str` 同時 fullmatch 只會發生在一個被丟掉的空白 gap 兩側。N1（非空）、N4、N7 把這個推導鎖住，選項 A 變體會讓 N1、N7 失敗。
  - 「數字不會被黏回去」：N3；`merge_consecutive_strings` 只在 `number_mode`／`number_language` 內使用，`number_wait_factor` 之後只有 `speech_viewer`，runtime 端相鄰 `str` 是同一段的 chunk（`runtime/requestBuilder.py:51-52`），所以 `"abc","1"` 仍是一段，`"1",B,"2"` 是兩段。
- **1c**：`"12"` → `"1 2"` → `"1"`,B,`"2"`（`test_digit_mode_then_number_wait_pauses_between_digits`）；翻譯過的數字 `"一 一"` 不切（F5 測試）。
- **1e**（`:355-356`）：`PairNumberBreakCommand(pair_pause)` 無條件產生；`"12"`、`"12.5"` 無分隔符；N6 檢查任意 pause（含 0）下交替、數量與拼回。
- **1f**：`compat/commands.py` 未動（diff 中沒有）；`BreakCommand(0)` → `Pause(0.0)` → `append_break(request, 0.0)`（`runtime/scheduler.py:231-235`）→ `_execute` 對 `playback is None` 的 task 只做 `token.wait(0)` 立即返回（`:530`）。0 秒 break 安全。

**標點（§4.2）**

- **2-1**（`:517-519`）、**2-4**（`:521-525`）、**2-2**（`:528`、`:541`、`:566-571`）：三個早退／無條件 `pause_cmd` 與 spec 一致；`pause_cmd is None` 分支全部移除。
- **2-7**：pause-point 的五條規則沒動——我比對了 `emit` 的 diff，只有拿掉 `pause_cmd is not None`。`test_zero_wait_keeps_the_pause_point_rules` 六個案例加 mutmut 補的兩個（rule 3、rule 4 trailing space）鎖住。
- 計畫 Deviations 記的 `" world"`,`"."`（非 spec §10 的 `" world."`）正確：有 pause point 的項目一律拆成 text／mark 片段，spec §5.2 表本身就是這樣寫的；§10 那一格是 spec 筆誤（Minor 5）。

**Stage 順序（§6）**

- `number_mode` 在 `number_wait` 之前：pair 模式 `"1234 5678"` → `"12"`,PB(0),`"34 56"`,PB(0),`"78"` → 切分後 `"34"`,B,`"56"`（`test_pair_mode_then_number_wait_breaks_between_numbers_only`）。PB 不是 `str`，`_both_numbers` 不會在 pair 之間再加 B。
- `item_wait` 在 `punctuation` 之前：item B 被當 pending break，壓掉 boundary PuB（`:581-585`）；PB 也是 `BreakCommand` 子類別，同樣壓掉（既有測試 `test_a_pair_number_break_counts_as_an_existing_pause_for_punctuation`）。
- `punctuation` 在 `number_wait` 之前：`"1, 2"` 清單 `","` → `"1"`,`","`,PuB,`" 2"` → `_remove_space` 後 `"1"`,`","`,PuB,`"2"`，沒有數字停頓疊加；remove on 時 `"1"`,PuB,`"2"` 亦同。
- `number_language` 用不同語音時每個數字被 `WVLangChangeCommand` 包住，`"1 2"` 到 `number_wait` 時是 `"1"`,cmd,cmd,`"2"`，不加 B——與 master 相同（F4，spec 明列為範圍外）。
- `chinesespace` 只動 CJK 之間的空白，`"共 12 34 個"` 的 `"共 "` 原樣保留。

**到達 runtime 與其他合成器**

- WorldVoice：`normalize_legacy_commands` 用 `isinstance(command, BreakCommand)`，PB／PuB 子類別都變 `Pause`；每個 `Pause` 先 `flush()` 再 `append_break`，所以每個 break 都切段。
- scope「all」：NVDA 不會依 `supportedCommands` 過濾指令（`ref/nvda/source/speech/manager.py` 沒有這種過濾；只有 `speech.py:572/618/640` 對 Pitch／CharacterMode 的查詢），eSpeak（`synthDrivers/espeak.py:204-205`）、SAPI5（`sapi5.py:928-929`）、OneCore（`speechXml.py:307-308`）都用 `isinstance(item, BreakCommand)`，所以子類別會變成 `<break time="0ms" />`／`<silence msec="0" />`。各引擎是否把 0 ms 的標記當成詞界，Linux 上無法驗證（F2、手動項目 7）。忽略 `BreakCommand` 的第三方合成器會把 `"12"`,PB(0),`"34"` 黏成 `1234`——這是 1e 在 scope「all」下的已知風險，spec F2 已記。

**和 master 相比的回歸（預設設定）**

- 數字停頓預設 10 ms、預設開啟（`settings.py:85-102`、`:187-192`），所以**所有預設設定的使用者**現在在同一字串內以空白分隔的數字之間都會多一次切段加 10 ms 靜音：日期 `2026 10 21`、電話 `0912 345 678`、`Windows 11 22H2`（→ `Windows `,`11`,B,`22`,`H2`）、表格儲存格 `12 34 56`。spec §8 已明說並由使用者接受；列入下方「預設」清單提醒。NBSP 的情況見 Important 1。
- pair 模式預設 pause 0：每個 pair 變成一段（1e／1f，使用者接受）。
- 標點：全預設（開關 on、wait 0、remove off、清單 `""`）前後都是 pass-through，**無變化**。有儲存清單、wait 0、remove off 的 profile：以前 pass-through，現在每個 pause point 都 `Pause(0)` 切段（2-3，使用者接受）。NVDA 只在值與目前生效值不同時才寫入（`ref/nvda/source/config/__init__.py:1363-1368`，`str(val) == str(curVal)` 即跳過）且 `PipelineSettingsService.update` 只寫有變的 key（`settings.py:295-298`），`a3493ba` 起舊版面板也是走 `config.conf[...] =`，所以舊預設清單只會存在於使用者自己編輯過的 profile。

**面板（§4.3）**

- Speech Pipeline 面板（`speechSettingsDialog.py:255-262`）：三個控制項跟著開關；`onSave` 仍存被 disable 的值（`test_pipeline_panel_saves_the_disabled_pause_controls`）；remove 不再綁事件；初始呼叫 `onPunctuationPauseEnabledChange(None)` 保留，開啟時狀態正確。
- Voice 面板（`VoiceSettingsDialogs.py:22-50`）：改 Enable 不 Hide。`refreshGui`（`ref/nvda/source/gui/settingsDialogs.py:1633-1646`）在合成器換了之後整個重建、再跑 WorldVoice 的 `makeSettings` 重新綁定；同合成器換語音走 `updateDriverSettings` → `_updateValueForControl`（`:1601-1611`、WorldVoice 覆寫 `:153-162`）只 `Show` 與 `SetValue`，不碰 Enable，所以狀態保留（`test_a_voice_switch_keeps_the_pause_controls_disabled`）。F3 的既有缺陷一併修掉。
- 焦點：三個控制項在 Voice 面板位於開關與「自動語言切換」之間、在 Pipeline 面板是最後三個；wx 的 Tab 會跳過 disabled 視窗，物件瀏覽讀到「unavailable」。開關本身永遠 enabled，Space 切換後焦點不動。`_makeBooleanSettingControl` 以 `MoveAfterInTabOrder` 串 Tab 順序（`:1541-1543`），字元編輯框仍排在滑桿後（`VoiceSettingsDialogs.py:79-81`）。
- 設定環：`punctuationpauseenabled`、`removepunctuationcharacters`、`punctuationwaitfactor` 的 `ring=True` 未變（`settings.py:135-160`）；環沒有 disabled 狀態，開關關閉時改 remove／wait 只會被存起來。與 master 的差別：以前環裡開 remove 在開關關閉時仍有效，現在無效（2-1）。

**設定與 confspec（§4.4）**：`string(default="")`；`normalize=_strip`；已存值不受 confspec 預設影響。無遷移、無 release note（選項 C）。

### mutmut 存活表的等價宣稱

計畫表中 10 個存活 mutant：

- `_translate_number` 1（`pair_pause=1` 預設值）：唯一呼叫點 `iter_number_speech_segments_mode(..., pair_pause)` 一定傳值（`:404`）。等價。
- `_translate_number` 16（`"XX+-XX"`）：`digits[0]` 是 `_NUMBER_RE` match 的第一個字元，只會是正負號或數字。等價。
- `_translate_number` 42（`previous_was_digit = None`）：只做真值判斷。等價。
- `inject_punctuation_pause` 36／43／44（`last_punctuation_index` 的 `default`）：沒有 punct 片段時才用到預設值，而比較 `index == last_punctuation_index` 只在 punct 分支執行。等價。
- 64／65（`kind == "XXtextXX"`／`"TEXT"`）：text 片段落入 punct 分支後 `eligible_here` 為 False、index 不可能等於 `last_punctuation_index`，因此原樣 yield、不加 break。等價；64 已實測 149 passed。
- 94／95（最後一次 `emit` 的旗標改 `None`）：兩個旗標只做真值判斷。等價；94 已實測 149 passed。

### Important

| # | 項目 | 失敗情境 | 建議 |
| --- | --- | --- | --- |
| 1 | `pipeline/__init__.py:214`（`gap.isspace()`）、spec §4.1 `:150` 與 §12 第 4 項：「whitespace」採 `str.isspace`，把不換行空格 U+00A0（以及 U+202F、U+2007）當成可切分的空白；`tests/test_pipeline_filters.py:120` 把 `"1 2"` → `1`,B,`2` 釘成預期。這條是**協調者代定**的預設，使用者尚未確認。 | 不換行空格在法文、俄文、波蘭文、瑞典文等地區設定裡是千位分隔符（Windows 檔案總管的檔案大小、Excel、網頁的 `10 000 €`、`1 234 567`）。這些字元存在的目的就是「這裡不准斷開」。預設設定（數字停頓 10 ms、預設開啟）下，`"10 000"` 現在變成 `"10"`,B,`"000"` 兩段：引擎原本可能讀成「一萬」的數字，會被讀成「十」停頓「零零零」。中文使用者較少遇到，但 scope「all」或多語使用者會。 | 兩個選項擇一，由使用者決定：(a) 把 U+00A0、U+202F、U+2007 從可切分的空白中排除（例如 `gap.isspace() and not gap & _NO_BREAK_SPACES` 的寫法，或以 `_SPLIT_SPACE_RE` 取代 `isspace`），`_remove_space` 的 `strip()` 不用改；同時把 `SPLITS` 的 NBSP 列改成「不切」並在 `NUMBER_TEXT` 字母表加入 U+00A0 讓 N1–N7 也涵蓋。(b) 維持現狀，在 spec §4.1 與「預設」清單明寫「NBSP 也會切」。 |

### Minor

| # | 項目 | 失敗情境 | 建議 |
| --- | --- | --- | --- |
| 1 | `pipeline/__init__.py:511-512` docstring：「An existing BreakCommand between two text items suppresses this pause, so the punctuation pause and item_wait_factor never stack」只對**前一項結尾**的 boundary point 成立。項目**開頭**的標點是 internal point（rule 3），不看前面有沒有 break。實作者在 P4 記的 `["a", B, ". b"]` → `a`,B,PuB,` b`（remove on）；remove off 時是 `a`,B,`"."`,PuB,` b`。我在 `master` 上重跑確認 wait > 0 時完全相同，是既有行為；本分支只是在 wait 0 時也會出現 PuB(0)。 | NVDA 常把欄位邊界後的文字以標點開頭送出（例如連結後的 `", then …"`），item wait > 0 且有設定清單時，那個位置的停頓是 item wait **加** punctuation wait，而不是只取其一；remove off 時 runtime 還會多一段只含 `"."` 的 segment 送給引擎。2-7 規定 pause-point 規則不改，所以這一輪只需修文件。 | docstring 改成「suppresses the boundary pause of the item before it; a mark that opens the next item is still an internal pause point」。若使用者想改行為，另開一條決定：項目開頭的標點 run（前面沒有非空白文字）在前一個輸出是 `BreakCommand` 時不當 pause point。 |
| 2 | `tests/test_pipeline_pause_properties.py:132-142`（P4）：remove off 時只檢查 PuB 與既有 break **直接相鄰**；`a`,B,`"."`,PuB,` b` 中間隔著只含標點的文字，所以沒被視為疊加。 | property 名稱說「never stacks onto an existing one」，但上面這種疊加通過。日後若有人依 property 判斷行為，會被誤導。 | 把「中間只有標點或空白的文字」也算相鄰（例如先把 `str` 中只含清單字元與空白的片段濾掉再比對），並把已知的例外寫進 docstring；或改名為「no punctuation break directly after an existing one」。 |
| 3 | `tests/test_pipeline_pause_properties.py:159` `NUMBER_TEXT` 字母表沒有 U+00A0、U+202F、`\n`、`\r`；`punctuation_sequences` 也沒有 U+3000。 | NBSP 只有單元案例覆蓋，N1–N7 沒跑到；換行在 `_remove_space` 兩端會被 strip、中間會被當 gap，目前沒有任何測試證明這點。 | 字母表加入 ` `、`\n`（配合 Important 1 的決定）。 |
| 4 | `VoiceSettingsDialogs.py:153-162` `_updateValueForControl` 在語音切換時用 `SetValue` 重設 `punctuationpauseenabledCheckbox`，不觸發 `EVT_CHECKBOX`，因此不會重新套用三個相依控制項的 Enable 狀態。 | 對話框開著時用設定環（NVDA+Ctrl+方向鍵）切換 `punctuationpauseenabled`，再在面板換語音：勾選框變了，但三個控制項的 enabled 狀態停留在舊值，直到再按一次開關。極少發生。 | `_updateValueForControl` 處理完 `punctuationpauseenabled` 後，或 `updateDriverSettings` 覆寫的結尾，呼叫 `_applyPunctuationPauseControlsState()`（有 `getattr` 保護，對非 WorldVoice 合成器無副作用）。 |
| 5 | spec §10 表（`...-design.md:436`）寫 wait 0 + removal 的預期為 `" world."`，實作與 §5.2 表（`:261`）及測試是 `" world"`,`"."`。計畫 Deviations 已記，spec 沒改。 | 文件自相矛盾。 | 把 §10 那一格改成 `" world"`, `"."`。 |
| 6 | 計畫 mutmut 表的編號來自 `mutate_only_covered_lines = true` 那次執行；「Change」欄才是可對照的內容（與上一輪 review 的 Minor 6 相同）。 | 日後 `mutmut show` 編號可能對不上。 | 保留現狀即可。 |

### 未評斷的項目

- scope「all」下其他合成器對 `<break time="0ms" />`／`<silence msec="0" />` 是否形成詞界（F2），以及第三方合成器忽略 `BreakCommand` 時 pair 會黏成一個數字——spec 已記為手動項目 7，無 Linux 可驗證的方法。
- `number_language` 用不同語音時數字之間不加停頓（F4），spec 範圍外。
- 設定環沒有 disabled 狀態（§4.3），spec 由協調者決定不改。
- `_both_numbers` 改 fullmatch 後 `["12abc","3"]` 不再停頓——1a 使用者決定。

### 使用者還沒確認的使用者可見預設

spec 標為「Decided by orchestrator with the recommended default; user may override before merge」，或 spec §8 寫為「accepted」但值得在 merge 前再看一眼：

1. **「whitespace」= `str.isspace`，含不換行空格 U+00A0／U+202F 與全形空格 U+3000**（spec §4.1 `:150`、§12 第 4 項）。見 Important 1；建議至少排除不換行空格。
2. **Voice 面板改 disable、不 hide**（§4.3、§12 第 2 項）：開關關閉時滑桿仍看得到但「unavailable」，Tab 行為與以前相同；順便修掉 F3。
3. **設定環不變**（§4.3、§12 第 3 項）：開關關閉時環裡改 remove 或 wait 會被存起來但沒有效果；以前 remove 在開關關閉時仍有效。
4. **`pipeline/__init__.py` 加入 mutmut `source_paths`**（`pyproject.toml:44`，§12 第 5 項）。
5. **預設設定下數字停頓現在會作用在同一字串內的數字之間**（§8；數字停頓預設 10 ms 且預設開啟）：所有沒改過設定的使用者都會聽到 `2026 10 21`、`0912 345 678`、`Windows 11 22H2` 之類被切段加 10 ms 靜音。這是 1b 的目的，但預設即生效、沒有 release note（2-6 選項 C 只講清單），使用者應知道。
6. **pair 模式預設 pause 0 時每個 pair 各自一段**（1e／1f），只剩段落交接的空隙；其他合成器（scope「all」）的行為未驗證。
7. **有儲存清單、wait 0、remove off 的 profile**：以前 pass-through，現在每個 pause point 切段（2-3）。只影響自己編輯過清單的使用者。
8. **預設清單改為空字串、無遷移**（2-6 選項 C）：沒編輯過清單但開了 wait > 0 或 remove 的使用者，升級後標點停頓與移除靜默失效，直到自己輸入字元。

另外：spec §9.4 的 8 個 Windows／NVDA 手動項目全部未執行（Linux 無法驗證）。

## 工作區備註

review 開始前就存在、與本分支無關、未動：主 checkout 的 `M buildVars.py`、`D docs/superpowers/finish_task.md`、`?? DEVELOPMENT_WORKFLOW.md`、`?? diff.md`。本 worktree 除本檔外乾淨。`docs/` 被 `.gitignore` 忽略，本檔以 `git add -f` 加入。

## 修正記錄

修正者：Opus 5.5，依 `DEVELOPMENT_WORKFLOW.md` §3.4，在本 worktree 進行。每項測試變更都先確認在缺口上會失敗，再確認修正後通過。

| 項目 | commit | 內容 |
| --- | --- | --- |
| Important 1 | `ecd147a` | **使用者決定（2026-10-21）：選項 A。** 新增 `_is_splittable_gap`（`gap.isspace()` 且不含 U+00A0、U+202F、U+2007），取代 `pipeline/__init__.py:214` 的 `gap.isspace()`；空白、tab、換行與 U+3000 仍會切分。`tests/test_pipeline_filters.py` 的 `"1 2"` 列改為不切，並新增 `"10 000"`、`"1 234 567"`、`"1 2"`、`"1  2"`、`"10 000 5"`、`"2 10 000"`、`"1\n2"` 各列；修正前 6 列失敗。spec §4.1 規則、範例表、§9.1、§9.2（N2、新增 N8）與 §12 第 4 項已改寫並標記「Decided by the user (2026-10-21)」。注意：`"2 10 000"` 會得到 `"2"`、Break、`"10"`、`" 000"`，後兩段在 runtime 是同一段，引擎仍讀到 `10 000`。 |
| Minor 1 | `0056680` | docstring 改為：既有 break 只壓掉前一項的 boundary pause；開啟下一項的標點是 internal pause point，例如 `["a", existing, ". b"]`。行為未改（2-7）。 |
| Minor 2 | `7af1264` | 新增 property「an existing break suppresses only the boundary pause before it」：把輸入中的既有 break 拿掉後，輸出只多出被壓掉的 boundary pause，其他完全相同；remove 開或關、任何 wait 都成立（deep profile 20000 例通過）。原 P4 保留檢查內容，改名為「never ends the output or sits next to an existing one when marks stay」並在 docstring 寫明例外。缺口驗證：一個「連開頭標點的 pause 也一併壓掉」的變體（違反 2-7）讓新 property 失敗，而舊的 property 檔與 `test_pipeline_filters.py` 全數通過。spec §9.2 的 P4 已改寫並新增 P4b。 |
| Minor 3 | `ecd147a` | `NUMBER_TEXT` 字母表加入 `\n`、`\r`、U+00A0、U+202F、U+2007；N2 的 gap 判斷改用新規則；新增 property「no break replaces a gap with a no-break space」（修正前失敗）。`punctuation_sequences` 未加 U+3000：標點階段不看數字間空白，與本項無關。 |
| Minor 4 | `5244c8c` | `_updateValueForControl` 更新 `punctuationpauseenabled` 勾選框後呼叫 `_applyPunctuationPauseControlsState()`。新增測試（開／關兩種）：對話框開著時用設定環切換開關，再換語音，三個相依控制項跟著開關狀態；修正前 2 個 failed。 |
| Minor 5 | `4fdc238` | spec §10 改為 `" world"`, `"."`。 |
| Minor 6 | `c321cd4` | 計畫 mutmut 表前註明編號只屬於該次執行，之後的執行或程式變更可能改變編號，以「Change」欄辨識 mutant。 |
| mutmut 複跑 | `d364318` | 在 `ecd147a` 後對 `_both_numbers`、`number_wait_factor`、`_is_splittable_gap`、`_split_spaced_numbers`、`_split_numbers` 跑 `mutmut run --max-children 3`（MemAvailable < 3 GB 即中止的 guard，未觸發）。第一次 60 個 mutant 中 1 個存活：`_split_spaced_numbers` 的 `for side in (0, 2)`（把空 gap 右邊第二個 match 標成 glued）。字母表變大後，derandomized 的 property 不再剛好碰到它；新增單元案例 `"1-2 3 4"` → `"1-2 "`, `"3"`, B, `"4"`，在 `mutants/` 以 `MUTANT_UNDER_TEST` 確認會殺掉。清掉 `mutants/` 重跑：**60 個 mutant 全數 killed**（`_both_numbers` 10、`number_wait_factor` 12、`_is_splittable_gap` 2、`_split_spaced_numbers` 35、`_split_numbers` 1）。`_NO_BREAK_SPACES` 是模組常數，mutmut 不突變；三個字元各有單元案例。 |

最終驗證（`d364318` 之後）：`python3 -m pytest -q tests` 單程序 **1830 passed、0 skipped**（基準 1818；新增 12 個）；`prek run --all-files` 全數 Passed；`git diff --check master` 無輸出；兩個受保護路徑指令皆無輸出。

「使用者還沒確認的使用者可見預設」第 1 項已由使用者決定（選項 A）。其餘 2–8 項未變。Linux 無法驗證的項目（Windows NVDA、實際音訊、引擎 SDK、spec §9.4 的 8 個手動項目）仍未驗證。
