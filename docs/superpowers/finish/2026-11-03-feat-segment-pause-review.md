# Review：feat/segment-pause（分段停頓階段取代 VE/Cerence 的 100 字元切割）

日期：2026-11-03。分支：`feat/segment-pause`（worktree `/workspace/WorldVoice-segment`，`master` `73eb8c8` → `311951b`，12 個 commit：3 個 `docs:` 規格、決定與計畫、6 個 `feat:`／`fix:`、2 個 `test:`、1 個 `docs:` 翻譯與使用手冊）。基準 `master` 3633 passed／0 skipped；分支 3699 passed／0 skipped（+66；兩個數字都由審閱者自己在 scratch worktree 重跑確認）。
審閱者：Fable 5.1（唯讀；只新增本檔）。流程：一般流程（DEVELOPMENT_WORKFLOW.md §3.3）。Linux、Python 3.14，單一 pytest 行程（本機沒有 xdist），記憶體守衛 MemAvailable < 3 GB 時只殺自己的 pytest（守衛在突變實驗中確實觸發過一次，見驗證表）。

依據：

- spec `docs/superpowers/specs/2026-11-03-feat-segment-pause-design.md`（U1–U7 使用者決定；O1–O12 協調者預設，其中 O4、O7、O10 與 Q1–Q3 由使用者決定）；plan `docs/superpowers/plans/2026-11-03-feat-segment-pause.md`（Review Focus 1–5 逐項檢查）；進度帳本 `.superpowers/sdd/2026-11-03-feat-segment-pause/progress.md`（9 行 `Ruling:`，全部評估，見下）。
- 實驗都在暫時 detached worktree `<scratchpad>/wv-mut`（`311951b`）與 `<scratchpad>/wv-base`（`73eb8c8`）做，`ref` 以符號連結指到 `/workspace/WorldVoice/ref`；結束後兩個 worktree 都以 `git worktree remove` 移除。分支 worktree 與主 checkout 沒有被任何指令修改。
- 行號以 head `311951b` 為準；`chunker:` = `addon/synthDrivers/WorldVoice/text/chunker.py`，`segments:` = `pipeline/segments.py`，`bcommands:` = `bridge/commands.py`，`items:` = `pipeline/items.py`，`ve:` = `driver/VE/__init__.py`，`veinner:` = `driver/VE/driver/__init__.py`（只讀）。

## 結論

**可以 merge，但建議先修 I1（一行）。** Critical 0、Important 1、Minor 4。沒有找到執行緒或鎖的問題、沒有與 `master` 相比的非預期回歸、§8 限制全部遵守；實作忠於 spec，I1 其實是 spec §4.1 步驟 2 自己的一個漏洞，實作者照著做了。

- **切割規則（`segment_cuts`，`chunker:49-112`）。** 候選位置是任何空白字元之後與項目邊界（O4，Q2 (a)）且 `not _attached`；片段從第一個非空白字元起算（Q3 (a)）；`min(limit, last)` 保證切點後一定還有有聲文字；硬切先 `_cut_before_marks` 再退回 `_end_of_marks`，`cut > last` 時停止，所以不會在尾端空白前停頓。`_item_offsets` 把切點對應到「結尾在切點或之後的第一個項目」，空項目永遠不擁有切點。線性時間：候選與非空白位置各算一次，之後只用 `bisect`；`_cut_before_marks` 往回最多走一個字叢、`_end_of_marks` 往前最多走一個字叢，而每次切割至少前進一個字叢，所以總和仍是 O(L)（`test_segment_cuts_stay_fast` 的四組 10 萬字元輸入都在 2 秒內）。唯一的問題是停止條件把尾端空白算進去（I1）。
- **階段（`segments:18-69`）。** 只在 `isinstance(item, BreakCommand)`（含 0 ms、含 `_plain_break` 做出來的標記 break）與 `_ends_utterance` 處重新計數（O5）；語言、索引、callback 指令不中斷，也不計入字數；break 放在切下的文字之後、後續指令之前；一個 `SegmentBreakCommand` 實例共用（和 item／unspaced 階段一樣）。`length <= 0 or pause <= 0` 時 `yield from`，物件相同（U3），所以兩個預設都是 0 時整條序列不變，VE/Cerence 回到 6.2 的一通呼叫。`_merge_edge_breaks` 不需要處理：segment break 和任何其他 break 之間一定有有聲文字（P4，性質測試釘住）。
- **STAGES 位置（`registry.py:155-160`）。** 在 `number_wait_factor` 之後、`speech_viewer` 之前，所以它看得到所有既有停頓並在那裡重新計數（O6）；`LOG_SWITCHES` 自動多出 `segmentWaitFactor`，Log Record 面板標籤「Segment wait factor」（`test_log_switch_labels_are_unchanged`），before／after 兩列（`test_the_segment_switch_logs_its_stage`）。
- **`effective()`（`settings.py:389`）。** 無角色的合成器在「僅 WorldVoice」範圍下 `segment_wait_factor=0`，`segment_length` 保留（O3，和 `group_size` 一樣）；「所有合成器」範圍下另一合成器得到 `_plain_breaks` 轉成的普通 `BreakCommand`，NVDA 的 `SsmlConverter` 轉成 4 個 `<break time="30ms"/>`、文字一字不少（`test_nvda_ssml_keeps_every_word_at_the_segment_cuts`，`ref/nvda` 真的 `speechXml`）。
- **設定表、confspec、面板順序（`settings.py:295-321`）。** 兩個項目緊接在 `punctuation_pause_characters` 之後，先 slider 再 spin（U6）；`segmentWaitFactor = integer(default=0,min=0,max=100)`、`segmentLength = integer(default=0,min=0,max=2147483647)` 由表推出；`segment_length` 無 `driver_id`、無 `depends_on`，`reset_out_of_range=True`（U2）；NVDA 語音面板的 spin 跟在 `segmentWaitFactor` 列之後（`creationFollowers`，`test_panel_layout`）；ring 只有「Segment wait factor」（`EXPECTED_IDS`）。都是表驅動，UI 沒有改程式碼。
- **橋接重播（`bcommands:11-54`，O10／Q1 (a)）。** 追蹤 `SynthParamCommand` 中除了 `LangChangeCommand`／`WVLangChangeCommand` 的指令，`isDefault` 時移除該型別（NVDA `ParamChangeTracker` 語意，`ref/nvda/source/speech/manager.py:83-112`）；`Pause` 或 `SelectVoice` 之後進入 pending，pending 期間參數指令只更新不輸出、索引等指令原位輸出，遇到下一個 `str` 才先輸出追蹤到的指令；序列結尾 pending 時什麼都不輸出，所以不會產生只有參數的引擎呼叫（P7 性質測試和 NVDA 的追蹤器逐項比對）。順序：`lang_cmd_to_voice` 先把語言指令變成 `SelectVoice` 再進橋接（`__init__.py:340-344`），所以 `SelectVoice` 確實在流裡；`deduplicate_language_command` 先去掉同語音切換，不會多餘重播。`inject_langchange_reorder` 把語言指令移到它所屬群組之前，所以 NVDA 放在 utterance 開頭的參數會落在 `SelectVoice` 之後、不會單獨成段（這點和 `master` 相同）。對 VE 的意義：內層 `speak`（`veinner:354-434`）每通呼叫從 `charMode = False` 起算，音高等都是當次呼叫的行內 escape，所以重播是必要的，F2 成立。拼讀：每個字母後 NVDA 自己結束 utterance，重播只在 N 很小切進「cap A」時才發生；讀出全部：每段自成一次 `speak`。唯一的邊角是空白文字（M2）。
- **VE/Cerence `_speak`（`ve:536-544`、`cerence:540-548`）。** 一段一通 `_NativeTask`，`break_repeated_runs` 仍套用，空字串不排任務（舊 chunker 對空字串回傳 `[]` 的行為保留）。`lastCallEnded`（`ve:146-148`、`:585-591`）由「`_Retire` 前最後一通呼叫」設定，一通呼叫時就是那一通；零通呼叫時維持預設 `True`，retire 時 ENGINE_DONE 照舊到達（`test_segment_without_native_call_reaches_engine_done` 改用空白文字觸發）。多通呼叫的路徑（內層語言切換，F5）仍在，測試改由 `LangChangeCommand` 取得兩通呼叫（`switching`、`two_pieces`），取消與不重啟的斷言不變。WorldVoice 的一段裡永遠沒有語言指令，所以實際上每筆 record 就是一通呼叫。沒有新的鎖、沒有改 callback 執行緒。
- **測試抓得到它聲稱的錯誤。** 23 個手動突變（還原各項修正、換順序、拿掉重播）全部被對應的測試抓到，第一個紅燈都是該行為的測試（表在下方）。另外用 100 000 個隨機案例驗證 I1 的建議修法仍滿足 P1–P5。
- **翻譯與手冊。** 「分段停頓參數」「分段字數」與既有「標點停頓參數」「每組位數」格式一致；`msgfmt --check` 無輸出，兩個新條目都不是 fuzzy；readme 的子清單縮排（單一空白）和同檔其他區塊一致；`## 下一版更新` 直接放在 `# WorldVoice 更新日誌` 下（O12）。`msgattrib --no-obsolete` 拿掉的 `msgid "group"` 在 `HEAD` 的原始碼裡確實已經不存在（`git grep '_("group")'` 空），是 feat/number-group-independent 留下的過時條目，拿掉正確；其他六種語言的 `.po` 還有這條，留待統一整理時處理。翻譯與 readme 只動 zh_TW 兩個檔案（U7）。一處用詞不一致見 M3。
- **§8 限制。** 12 個 commit 都是英文 `<type>: <summary>` 加原因，0 個 `Co-Authored-By`；受保護路徑與 Neural 兩個指令都無輸出；`git diff --check master...HEAD` 乾淨；prek 8 個 hook 全部 Passed；VE 與 Cerence 只 import core 的 `text.arabic`，彼此不相依；`split_speech_text_pieces`／`MAX_TEXT_LENGTH` 在 `addon`、`tests` 裡已無殘留（O7）。

## Critical

無。

## Important

### I1. 停止條件把尾端空白算進字數，讓剛好放得下的一行多出一個停頓（`chunker:85`；spec §4.1 步驟 2；commit `626e603`）

`segment_cuts` 用 `len(text) - piece_start <= max_length` 決定「剩下的都放得下，停止」，但 `len(text)` 含尾端空白，而後面的候選搜尋又用 `min(limit, last)` 把尾端空白排除。結果是：一段有聲文字明明 ≤ N，只因後面跟著空白或換行，就被切開。實測（head 的程式）：

| 輸入 | N | 輸出 |
| --- | --- | --- |
| `["Hello world\r\n"]` | 11 | `"Hello "`，SB，`"world\r\n"` |
| `["Hello world "]` | 11 | `"Hello "`，SB，`"world "` |
| `["abc d" + " " × 10]` | 5 | `"abc "`，SB，`"d          "` |
| `["Hello world"]` | 11 | 不切（正確） |

失敗情境：使用者把分段字數設成 50 逐行閱讀，NVDA 的行文字常帶 `\r\n`；49 個字元的一行（51 含換行）會在最後一個空白處多一個停頓，而 48 個字元的一行不會。對使用者來說這條規則變成「有時候 N 要扣掉 1～2」，而 readme 寫的是「每一段最多幾個字元」。spec 自己的保證（§4.1「each piece, without … the last piece's trailing whitespace, has at most max_length characters」）也暗示尾端空白不該算；plan Review Focus 5 的「no cut for N ≥ text length」在 `"Hello world\r\n"` 這種輸入上其實沒有被測到（`trailing-spaces` 列是沒有候選的硬切案例）。舊 chunker 有同樣的算法，但它的 100 不是使用者看得到的設定。

建議修法（一行，不改其他分支）：`chunker:85` 改成 `if last - piece_start < max_length:`（即有聲區間 `last + 1 - piece_start <= max_length` 就停）。`cut > last` 的檢查仍要留著（只有字叢的 `_end_of_marks` 可能越過 `last`）。我在 scratch 複本上套了這個修法：上表三個案例都不再切，`test_text_preprocessing.py` 的 §5 各列結果不變，100 000 個隨機案例（plan 的 `SEGMENT_PARTS` 字元集、0–5 個項目、N 1–15）P1–P5 全部成立，且「`len(text.strip()) <= N` 時無切點」也成立。測試：在 `test_segment_cuts_without_a_cut` 加 `(["Hello world\r\n"], 11)`、`(["abc d" + " " * 10], 5)` 兩列，並在 `test_property_segment_cuts_keep_the_rules` 加一條斷言 `if len(text.strip()) <= n: assert cuts == []`。spec §4.1 步驟 2 的 `L - s0` 改成 `last + 1 - s0`。

## Minor

### M1. 候選位置是「任何空白字元之後」，所以 `\r\n` 會被切在 `\r` 與 `\n` 之間、空白項目會被切成兩半（`chunker:76`、`segments:60-68`；plan Review Focus 1）

plan Review Focus 1 寫「`\r\n` cuts after the `\n`」，但程式對每個空白字元之後都給候選，性質測試也沒有檢查這件事。實測：`["abc\r\ndef"]`，N 4 → `"abc\r"`，SB，`"\ndef"`；`["one two", "  ", "three"]`，N 8 → `"one two"`，`" "`，SB，`" "`，`"three"`（階段把 `"  "` 這個空白項目切成兩個單一空白夾著 break）。聽不出差別（下一段的開頭空白不計數、引擎忽略），只是和 plan 的說法不符，且輸出比必要的多一個項目。建議：候選只放在一段連續空白的結尾，`chunker:76` 的條件改成 `((text[position - 1].isspace() and not text[position].isspace()) or position in boundaries) and not _attached(text, position)`；`position` 最大是 `len(text) - 1`，所以 `text[position]` 一定存在。這樣 `\r\n` 只在 `\n` 後有候選、空白項目後面的切點落在它結尾。若保留現狀，把 plan Review Focus 1 的那句改掉即可。

### M2. 重播在任何 `str` 之前觸發，包括空字串，讓「停頓 → 空白項目」在 VE/Cerence 多出一通只有 escape 的原生呼叫（`bcommands:44`、`items:45`）

`normalizeNvdaCommands` 以 `isinstance(command, str)` 判斷「下一段的文字到了」。項目階段在兩個相鄰 `str` 之間放 break 時不檢查是否空白（`items:45` 的 `_both_text`），所以 `[Pitch(30), "Hello", ""]` 開項目停頓後變成 `Pitch, "Hello", Pause, Pitch, ""`（在 scratch 複本以測試夾具確認：`[p, "a", Break(10), "", "b"]` → `[p, "a", Pause, p, "", "b"]`）。`master` 上 `[""]` 這一段進內層 `speak` 時空白被跳過、`chunks` 為空，沒有 `_speak`、沒有原生呼叫；現在 `chunks` 裡有 `\x1b\pitch=…\`，外層 `if text:` 擋不住，VE 會收到一通只有 escape 的 `ProcessText2Speech`。無聲、很短，`lastCallEnded` 由它設定也無害，但這是和 `master` 相比唯一多出來的引擎呼叫。NVDA 很少送空字串項目，且 `number_wait_factor > 0` 時數字階段會丟掉空白項目，所以實務上罕見。建議：`bcommands:44` 改成 `elif isinstance(command, str) and command.strip() and pending:`，重播延到第一個有聲文字（同一段內 escape 仍在文字之前，順序不變）；測試 `[p, "a", Break(10), "", "b"]` → `[p, "a", Pause, "", p, "b"]`。

### M3. 更新日誌一句裡同時用「音調」與「音高」（`addon/doc/zh_TW/readme.md:97`；commit `d3c0a14`）

標題「停頓後保留音調與拼讀設定」用「音調」，內文「停頓前的音高、語速、音量…」用「音高」。readme 其他地方（`:12`、`:19`、`:23`、`:29`）、WorldVoice 的 `.po`（「音調(&P)」）和 NVDA zh_TW（`Pitch` → 「音調」）都用「音調」。建議內文改成「音調」。其餘翻譯與手冊文字自然。

### M4. `segment_cuts` 的迴圈沒有前進保證，這類回歸會讓測試掛住而不是失敗（`chunker:83-100`）

突變 m17（`candidates[best] > piece_start` 改成 `>=`）讓 `cut == start`，`while True` 永不結束、`cuts` 無限成長；`test_segment_cuts_pieces[leading-spaces-hard-cut]` 不會紅，而是吃掉記憶體直到被殺（實作者的 mutmut 也遇到同一種「segfault」mutant）。產品程式沒有這個 bug，但測試套件對這一類回歸沒有防線。建議二擇一：在 `pyproject.toml` 的 pytest 設定加 `faulthandler_timeout = 120`（掛住的測試會印出 traceback 並結束，整個套件都受益），或在 `segment_cuts` 的迴圈尾加 `assert cut > start`（審閱期間沒有看到更便宜的做法）。

## Review Focus 逐項

1. 特殊空白：NBSP、全形空白是候選、ZWSP 不是、尾端空白前不停頓，`test_segment_cuts_pieces` 的 `nbsp`／`ideographic`／`zwsp`／`trailing-spaces` 列都有；「`\r\n` 在 `\n` 後切」不成立（M1）；尾端空白會逼出切點（I1）。
2. 空白與空項目：`test_segment_cuts_map_a_cut_to_the_first_item_ending_there`、`test_a_blank_item_keeps_the_break_after_it`、P4 性質都在；空項目不擁有切點已由 `_item_offsets` 的迴圈條件保證。
3. 索引與 callback：`test_the_break_goes_before_the_commands_after_the_cut`、`test_the_count_goes_on_across[index, callback]`、P1+P6 性質；橋接的 `test_index_commands_keep_their_place_while_a_replay_is_pending`。突變 m23（break 放到後續指令之後）被抓到。
4. 重播邊角：開頭就是停頓（`changed` 空、無輸出）、結尾是停頓加參數（`test_no_replay_at_the_end_of_a_sequence`）、兩個停頓中間沒文字（pending 維持，第二個 `Pause` 原位輸出，request builder 對空段只 `append_break`）、跨語音切換的拼讀模式（`test_character_mode_is_replayed_after_a_voice_switch`）；P7 把每段每個文字項目的參數狀態和 NVDA 追蹤器比對。只剩 M2 的空字串。
5. 極端長度：N = 1、N = `SPIN_MAX`（`n-max` 列）、10 萬字元四組都在 2 秒內；線性分析見結論。

## 進度帳本的 Ruling

| Task | Ruling | 評估 |
| --- | --- | --- |
| 2 | 也更新 `TABLE_DRIVER_IDS` 與 `driver_ids` 清單；log 標籤測試留到 Task 4 | 合理，都是表的鏡像。 |
| 3 | `test_worked_examples` 一個測試跑 8 列；重新計數加 0 ms `BreakCommand` 案例 | 合理，0 ms 重設是 O5 明文；只是計數簿記。 |
| 3 | 性質測試加 `suppress_health_check(function_scoped_fixture)` | 合理，fixture 無狀態，與 `test_pipeline_pause_properties` 同做法。 |
| 4 | Log Record 標籤檢查放進既有的 `test_log_switch_labels_are_unchanged` | 合理，該測試本來就列出所有標籤。 |
| 5 | `WVLangChangeCommand` 也排除在追蹤器外 | 正確：它繼承 `SynthParamCommand`（`speechCommands.py:4-7`），spec 說「other than a language command」；兩者在橋接前都已是 `SelectVoice`。 |
| 6 | `break_repeated_runs` 回傳空字串時不排任務 | 正確，spec §4.7，和舊 chunker 對空字串回 `[]` 一致。 |
| 7 | mutmut 在 `git ls-files` 複本跑、`--max-children 2`、`ulimit -c 0`、RSS 守衛 | 合理；我也遇到同類的失控 mutant（`>=`，`candidates[best] >= piece_start` 讓 `start` 不前進、`cuts` 無限成長），守衛確實需要。帳本列的 11 個等價存活我逐一看過，理由都成立（`length <= 0` → `< 0` 時 `segment_cuts` 回空、物件相同；`pending = None` 與 `False` 同義；位置 0 永遠不大於 `piece_start`）。 |
| 8 | 保留 msgmerge 預設換行 | 無妨，只影響一個 msgid 的排版。 |
| 8 | `msgattrib --no-obsolete` 拿掉過時的 `"group"` | 正確，見結論；其他語言的同條目留待統一整理。 |

## 審閱者自行驗證的項目

pytest 一次只跑一個行程；突變由 `mut_runner.py` 以精確字串替換套用（舊字串必須恰好出現一次），每個以 `-x` 停在第一個紅燈，跑完 `git checkout --` 還原並斷言 `git status --porcelain` 為空；每個 pytest 子行程另有 RSS > 1.5 GB 或 300 秒就殺掉的看門狗（失控 mutant 算被抓到，標 RUNAWAY）。

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 分支全套測試 | `python3 -m pytest -q -p no:cacheprovider tests`（`/workspace/WorldVoice-segment`） | 3699 passed、0 skipped，125.8 s |
| `master` 基準 | 同指令，scratch worktree `wv-base`（`73eb8c8`） | 3633 passed、0 skipped，124.9 s |
| prek | `prek run --all-files`（分支 worktree） | 8 個 hook 全部 Passed，未修改檔案 |
| 空白與格式 | `git diff --check master...HEAD` | 無輸出 |
| 受保護路徑 | §7 的兩個指令 | 都無輸出 |
| commit 訊息 | `git log master..HEAD --format=%B \| grep -ci co-authored-by` | 0；12 個主旨都是 `<type>: <summary>` |
| 翻譯與手冊範圍 | `git diff --stat master...HEAD -- addon/locale addon/doc readme.md` | 只有 `addon/doc/zh_TW/readme.md`、`addon/locale/zh_TW/LC_MESSAGES/nvda.po` |
| `.po` | `msgfmt --check -o /dev/null …/zh_TW/…/nvda.po`；兩個新條目前兩行 grep `fuzzy` | 無輸出；0 |
| `"group"` 條目 | `git grep -n '_("group")' HEAD -- addon` | 無輸出（條目確實過時） |
| 驅動獨立安裝 | grep VE／Cerence 外層的 `synthDrivers.WorldVoice.driver.` import | 只有 `driver`（core）與 `text.arabic` |
| 舊 chunker 殘留 | `git grep -n 'split_speech_text_pieces\|MAX_TEXT_LENGTH' -- addon tests` | 無輸出 |
| I1 重現 | 直接載入 `chunker.py` 跑表中四個輸入 | 如 I1 表 |
| I1 修法驗證 | scratch 複本改 `chunker:85` 為 `last - piece_start < max_length`，100 000 個隨機案例檢查 P1–P5 與「有聲文字 ≤ N 時無切點」 | 0 個違反；§5 各列輸出不變 |
| M1 重現 | 同上載入，`["abc\r\ndef"]` N 4；`["one two", "  ", "three"]` N 8 | `"abc\r"`／`"\ndef"`；`"one two "`／`" three"` |
| M2 重現 | scratch worktree 內以 `test_legacy_speech_commands` 的夾具跑 `[p, "a", Break(10), "", "b"]`；`items.item_wait_factor(["Hello", ""])` | 重播落在 `""` 之前；項目階段在 `"Hello"` 與 `""` 之間放 break |
| 記憶體守衛 | `guard.sh`（MemAvailable < 3 GB 殺自己的行程樹） | 第一輪突變時因失控 mutant（m17）觸發一次；改用看門狗版重跑 |

### 手動突變（scratch worktree `wv-mut`，`311951b`）

| # | 突變（還原或改壞的行為） | 跑的測試檔 | 結果：第一個紅燈 |
| --- | --- | --- | --- |
| m01 | `bcommands:49` `Pause` 後不設 pending（不重播） | `test_legacy_speech_commands.py` | KILLED：`test_parameters_are_replayed_after_a_pause` |
| m02 | `bcommands:53` `SelectVoice` 後不設 pending | 同上 | KILLED：`test_character_mode_is_replayed_after_a_voice_switch` |
| m03 | pending 期間參數指令也原位輸出（重播兩次） | 同上 | KILLED：`test_a_parameter_after_the_pause_is_replayed_once` |
| m04 | `isDefault` 不清除該型別 | 同上 | KILLED：`test_a_default_command_clears_its_type` |
| m05 | 語言指令也追蹤 | 同上 | KILLED：`test_language_commands_are_not_tracked` |
| m06 | `ve:543` 空字串也排 `_NativeTask` | `test_vocalizer_segment_drain.py` | KILLED：`test_empty_wrapper_text_makes_no_native_call[VE]` |
| m07 | VE 外層改回每 100 字元一通呼叫 | 同上 | KILLED：`test_a_long_segment_is_one_native_call[VE]` |
| m08 | Cerence 外層改回每 100 字元一通呼叫 | 同上 | KILLED：`test_a_long_segment_is_one_native_call[Cerence]` |
| m09 | VE 外層跳過 `break_repeated_runs` | 同上 | KILLED：`test_break_repeated_runs_still_runs[VE]` |
| m10 | `STAGES` 把分段階段移到 `number_wait_factor` 之前 | `test_pipeline_stages.py` 等 4 檔 | KILLED：`test_stages_order_and_log_keys` |
| m11 | `STAGES` 拿掉分段階段 | `test_worldvoice_speak.py`、`test_pipeline_stages.py` | KILLED：`test_a_long_sentence_is_spoken_in_segments` |
| m12 | `effective()` 不把 `segment_wait_factor` 歸零 | `test_pipeline_segment_pause.py`、`test_pipeline_settings_service.py` | KILLED：`test_nothing_changes_for_another_synth_in_worldvoice_scope` |
| m13 | 設定表先 `segment_length` 再 `segment_wait_factor` | `test_settings_order.py`、`test_pipeline_settings_service.py` | KILLED：`test_voice_panel_orders_follow_the_table[first…]` |
| m14 | `chunker:76` 只有 U+0020 是候選 | `test_text_preprocessing.py` | KILLED：`test_segment_cuts_pieces[newline-tab]` |
| m15 | 項目邊界不是候選 | 同上 | KILLED：`test_segment_cuts_pieces[item-boundary]` |
| m16 | 候選不檢查 `_attached` | 同上 | KILLED：`test_segment_cuts_pieces[mark-item]` |
| m17 | `chunker:89` `>` 改 `>=`（切點可落在片段開頭） | 同上 | RUNAWAY：`start` 不前進、`cuts` 無限成長，RSS > 1.5 GB 被看門狗殺掉（見 M4） |
| m18 | `chunker:95` `cut > last` 改 `cut > len(text)`（尾端空白前硬切） | 同上 | KILLED：`test_segment_cuts_pieces[trailing-spaces]` |
| m19 | 硬切不 `_cut_before_marks` | 同上 | KILLED：`test_segment_cuts_pieces[marks]` |
| m20 | `segments:40` utterance 結尾不重新計數 | `test_pipeline_segment_pause.py` | KILLED：`test_worked_examples` |
| m21 | 只有 `type(item) is BreakCommand` 重新計數 | 同上 | KILLED：`test_the_count_restarts_at[number-edge]` |
| m22 | `pause <= 0` 仍切 | 同上 | KILLED：`test_nothing_changes_without_a_pause[8-0]` |
| m23 | 項目邊界的 break 放到後續指令之後 | 同上 | KILLED：`test_worked_examples` |

每個突變還原後 `git status --porcelain` 都為空。

## 使用者還沒確認的使用者可見預設

- O1：`segment_wait_factor` 是驅動設定（出現在 NVDA 語音面板、語音流程面板與設定環）；`segment_length` 只在兩個面板，不在設定環。
- O2：兩個設定都不依賴「啟用標點停頓控制」，彼此也不相依。
- O3：無角色的合成器在「僅 WorldVoice」範圍下分段停頓為 0；「所有合成器」範圍下其他合成器也分段（SSML break，同一通呼叫）。
- O5：任何 `BreakCommand`（含 0 ms）與 utterance 結尾都重新計數；語言切換不重新計數。
- O6／O9：階段在數字停頓之後、speech viewer 之前；log 開關叫 `segmentWaitFactor`，標籤「Segment wait factor」，分段字數沒有自己的開關。
- O8：WorldVoice 內部用 `SegmentBreakCommand`，其他合成器得到普通 `BreakCommand`。
- O11：`_ends_utterance` 搬到 `pipeline/sequence.py`。
- O12：更新日誌放在新的「## 下一版更新」。
- spec §4.1 步驟 2 的停止條件把尾端空白算進字數（I1；建議改）。
- 候選落在每個空白字元之後，不是一段空白的結尾（M1）。
- 字數算的是 NVDA 處理符號與加 `CHUNK_SEPARATOR` 之前的文字（F3），符號多的片段唸出來會比 N 長。
- NBSP 也是切點（Q2 (a) 使用者已決定「任何空白」；這裡只提醒它的常見用途是「不要在這裡斷」）。
- VE/Cerence 每一段都像句尾（U1 已接受），1 ms 的停頓也聽得出來。
- O10 改變所有既有停頓之後的音調／語速／音量／拼讀行為（Q1 (a) 使用者已決定）；M2 的空字串邊角。
- 其他六種語言 `.po` 的過時 `"group"` 條目與新字串，留待統一整理（U7）。
- 更新日誌的「音調」／「音高」用詞（M3）。

## 未在本平台驗證

spec §9.5 的 7 項 Windows／NVDA 手動項目（真實 VE/Cerence 一通長呼叫的聽感、eSpeak／OneCore／RHVoice／SAPI5 的分段、面板 Tab 順序與 NVDA 朗讀、拼讀與 MathCAT 的重播、Log Record）都沒有驗證；Linux 只驗證到受控的 native 與音訊邊界。

## 修正記錄

日期：2026-11-03。修正者：Opus 5.5（一般流程 §3.4）。每項先寫會失敗的測試、確認紅燈，再修正；一項一個 commit，都在 review commit `6ecb014` 之後。

| 發現 | commit | 修正 |
| --- | --- | --- |
| I1 | `6733731` fix: stop cutting a segment whose spoken text fits | `chunker` 的停止條件改成 `last - piece_start < max_length`（`cut > last` 保留）。`test_segment_cuts_without_a_cut` 加 `fits-before-a-newline`（`["Hello world\r\n"]`，11）、`fits-before-a-space`、`fits-before-spaces`（`["abc d" + " " × 10]`，5）三列；性質測試加「`len(text.strip()) <= n` 時無切點」。修正前三列與性質測試都是紅燈。spec §4.1 步驟 2 改成 `last + 1 - s0 <= max_length`，標「Corrected by review I1」。 |
| M1 | `131f4d2` fix: never cut a segment inside a whitespace run | 見下方說明：只照建議改候選條件不夠，另外加了 `_inseparable` 與「spoken end」。新增 `crlf`（`["abc\r\ndef"]`，4 → `"abc\r\n"`／`"def"`，plan Review Focus 1 聲稱的測試）、`whitespace-run`、`fits-before-a-newline`（非最後一段）、`space-after-the-limit`、`blank-item-whole` 列；映射測試加 `(["one two", "  ", "three"], 8, [(1, 2)])`；階段測試 `test_a_blank_item_is_never_split`；`test_inseparable_marks_and_whitespace_runs` 6 列；兩個性質測試改成每段都去掉頭尾空白計數、檢查「切點不在一段空白中間」，例外改用 `_inseparable`。spec §4.1（候選定義、步驟 3、4、保證、helper 說明）、§9.3 P2 與 plan Review Focus 1 一併更新。 |
| M2 | `d260101` fix: replay synth parameters only before spoken text | `bcommands` 改成 `isinstance(command, str) and command.strip() and pending`。新增 `test_blank_text_does_not_take_the_replay`（`[p, "a", Break(10), "", " \n", "b"]` → `[p, "a", Pause, "", " \n", p, "b"]`）與 `test_no_replay_before_blank_text_at_the_end`，修正前都是紅燈；P7 只比對有聲文字項目。docstring 與 spec §4.6 更新，標「Corrected by review M2」。 |
| M3 | `c8d99ca` docs: call pitch 音調 in the zh_TW changelog entry | `addon/doc/zh_TW/readme.md:97` 的「音高」改成「音調」；全檔已無「音高」。純文字，沒有測試。 |
| M4 | `2c0c720` fix: fail a segment cut that does not advance | `segment_cuts` 在 `cut <= piece_start` 時 `raise RuntimeError`（每個切點一次比較）。新增 `test_a_cut_that_does_not_advance_fails`（monkeypatch 讓 helper 回傳片段開頭）：修正前在 8 秒 timeout 內掛住、被殺；修正後通過。另外在分支上暫時套用審閱者的 m17（`candidates[best] >= piece_start`）：現在以 `RuntimeError: segment cut 3 does not advance past 3` 失敗，不再失控；已還原。 |

### M1 的修法比建議多一步（Ruling，已記入進度帳本）

照建議只把候選改成「一段空白的結尾」之後，在 scratch 複本實測 `["abc\r\ndef"]`、N 4 仍得到 `(0, 4)`，也就是仍在 `\r` 與 `\n` 之間切：空白的結尾 5 超過上限 4，沒有候選，硬切落在 4。所以另外做兩件事：

1. 新增 `_inseparable(token, index)`：`_attached`，或位置在一段空白中間（前後都是空白）。候選、`_cut_before_marks`、`_end_of_marks` 都改用它，所以任何切點都不會落在一段空白中間（項目邊界若在空白中間也不再是候選；同一段空白的結尾有相同的 spoken end，原本就會勝出）。
2. 候選以「spoken end」（往回跳過它前面的空白）和 `min(limit, last)` 比較，也就是 I1「尾端空白不算」套用到每一段。

使用者聽得到的差別：非最後一段現在可以有 N 個有聲字元再加上它結尾的空白。`["Hello world\r\nfoo"]`、N 11 → `"Hello world\r\n"`／`"foo"`（原本 `"Hello "`／`"world\r\nfoo"`），也就是 I1 描述的逐行情境在多行文字的中間幾行也修好了。

### spec §5 例子表

重新對照程式：只有第一列（fox，N 50）的輸出改變，已更新為 `"The quick brown fox jumps over the lazy dog. The "`、SB、`"quick brown fox jumps over the lazy dog. The quick "`、SB、`"brown fox jumps over the lazy dog."`（有聲字元 48、50、34；原本 49、45、40 個字元），並標「corrected by review M1」。原因：第二段結尾的空白不再計入，所以多放一個字。其他列不變（`test_worked_examples` 對照 §5 全部列，通過）。`test_segment_cuts_pieces` 也改了兩列：`newline-tab` 的 N 5 現在得到 `"ab\ncd\t"`／`"ef"`；`leading-spaces-hard-cut` 換成 `["   aaaaaaaaab"]`，讓它仍走硬切，原本的輸入改成新列 `space-after-the-limit`（`"   aaaaaaaa "`／`"b"`）。

### M4 的選擇（Ruling）

選 `RuntimeError`，不用 `assert`（ruff S101，WorldVoice 的產品程式沒有 `assert`），也不用 `faulthandler_timeout`（只會印 traceback，迴圈仍繼續吃記憶體，不會讓測試失敗）。

### 驗證

| 項目 | 結果 |
| --- | --- |
| 全套測試 `python3 -m pytest -q -p no:cacheprovider tests`（head `896bf68`） | 3720 passed、0 skipped（review 時 3699；+21：I1 3、M1 15、M4 1、M2 2） |
| `prek run --all-files` | 8 個 hook 全部 Passed |
| `git diff --check master` | 無輸出 |
| §7 受保護路徑兩個指令 | 都無輸出 |
| 隨機檢查（scratch，200 000 例，`SEGMENT_PARTS` 字元集、0–5 個項目、N 1–15） | 切點有序、兩側有有聲文字、不切字叢、不落在空白中間、去頭尾空白後 ≤ N（或單一不可分字叢）、有聲文字 ≤ N 時無切點：0 個違反 |
| 線性時間 | 10 萬字元的長空白段、空白後接附加符號、ZWJ 後接空白等 5 組對抗輸入都在 0.1 秒內 |
| 手動突變（新改的 9 行：`spoken_ends`→`candidates`、三處 `_inseparable`→`_attached`、`and`→`or`、`spoken_end - 1`、I1 的 `<`→`<=`、M4 的 `<=`→`<`、M2 拿掉 `command.strip()`） | 9 個全部被抓到（M4 的那個是 guard 測試掛住、被 timeout 殺掉）。其中三個 `_attached` 突變原本只有 Hypothesis 抓得到，`896bf68` 加了 `hard-cut-before-a-run`、`cluster-ends-after-its-run` 兩列固定抓住 |
| mutmut | 沒有跑：只跑了上面便宜的手動突變。之前的 mutmut 曾出現失控 mutant，跑完整一輪很耗時 |

另外一個 commit：`896bf68` test: pin the whitespace-run cuts the property test alone caught（只加兩列測試）。

修正 review：I1 是 Important，依 §3.4 要由協調者派 Opus 5.5（xHigh）review `6ecb014..` 之後的修正 diff。

未在本平台驗證：Windows 上的 NVDA、VE/Cerence 實際聽感（同 review 的「未在本平台驗證」）。
