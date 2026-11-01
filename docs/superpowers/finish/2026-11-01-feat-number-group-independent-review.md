# Review：feat/number-group-independent（數字模式與每組位數成為獨立設定）

日期：2026-11-01。分支：`feat/number-group-independent`（worktree `D:/NVDA/NVDA_development/WorldVoice-number-group`，`master` `65856d26` → `747b9ee2`，8 個 commit：2 個 `docs:` 規格與計畫、5 個 `feat:`／`test:`、1 個 `docs:` 使用手冊）。基準 `master` 3375 passed／9 failed／1 skipped；分支 3623 passed／9 failed／1 skipped（+248 個 id；9 個 failed 都在 `tests/test_generated_unicode_data.py`，是 Windows 換行的既有假象，`master` 相同）。
審閱者：Fable 5.1（唯讀；只新增本檔）。流程：一般流程（DEVELOPMENT_WORKFLOW.md §3.3）。Windows、Python 3.14 venv；mutmut 不可用（O8），突變改由審閱者在暫時 worktree 以精確字串替換手動套用。

依據：

- spec `docs/superpowers/specs/2026-11-01-feat-number-group-independent-design.md`（`274b8eb6`；U1–U10 使用者決定，O1–O8 協調者預設；§3.2 聽感表、§5 i1–i30、§9.2 單元表、§9.3 性質）；plan `docs/superpowers/plans/2026-11-01-feat-number-group-independent.md`（`e08193bc`；Review Focus 1–5 逐項檢查）；進度帳本 `.superpowers/sdd/2026-11-01-feat-number-group-independent/progress.md`（1 行 `Ruling:`、4 處 plan 偏離，全部評估）。
- 實驗都在暫時 detached worktree `D:/NVDA/NVDA_development/wv-review-mut`（`747b9ee2`，只做 `ref/nvda` junction；結束後 junction 以 `cmd /c rmdir` 移除、worktree 以 `git worktree remove` 移除，`D:/NVDA/nvda/source/languageHandler.py` 確認仍在）。審閱者的腳本在 `C:/Users/tseng/AppData/Local/Temp/wv-review-tools/`（`mut.py` 突變表、`deep.py`、`wv_cfgcheck.py`），輸出在同目錄 `out/`。分支 worktree 與主 checkout 沒有被任何指令修改。
- 行號以 head `747b9ee2` 為準；`stages:` = `addon/synthDrivers/WorldVoice/pipeline/numberStages.py`，`numbers:` = `pipeline/numbers.py`，`psettings:` = `pipeline/settings.py`，路徑省略 `tests/` 時指測試。

## 結論

**可以 merge。** Critical 0、Important 0、Minor 3。三項 Minor 都是測試強度與程式碼精簡的問題，沒有找到產品 bug、沒有與 `master` 相比的非預期回歸、沒有違反 spec 的地方；兩個預設（value＋每組位數 0、none＋0）的輸出路徑和 `master` 完全相同（`stages:290`、`:301-303` 走和 `master` `else` 分支一樣的 `_inject_item_numbers(..., None)`）。

- **整條管線都看過，不只數字階段。** `registry.py:148-157` 的順序是 thousands → inject_numbers → unspaced → item → punctuation → number_wait_factor，逐一對照：
  - thousands（`stages:23-36`）只看 `number_mode == "value"`，不讀每組位數，所以 value＋N 先去千分位再切（i6、P-U3）。
  - `number_wait_factor`（`stages:107-130`）在 number 模式不做 `split_spaced_numbers`（和 `master` 同一行 `:128`），改由數字階段用 `gap_break` 放 G1 的停頓（`stages:450-452`，條件從 `edge is not None` 改成 `gap_break is not None`）；value／none＋N 時 `_split_numbers` 仍跑但找不到空白（片段裡沒有空白，空白已變成 break），`_insert_number_breaks` 的 `_both_numbers`（`:65-71`）對 `"1 0"`、break 都為假，不會補第二個 break。P-U5 在每個階段之後檢查，3000 個例子通過（見驗證表）。
  - item 階段（`items.py:38-51`）把自己的 break 放在 `NumberItemEdgeBreakCommand` 之前並留較長者，所以 number＋0 的 G2 用 item-edge 類別才能得到 `"1 0"`, B30, `"2 0"`（i17、`test_number_mode_without_groups_takes_the_longer_item_pause`）。
  - punctuation 階段（`punctuation.py:194-195`）的「edge break 不壓掉邊界停頓」規則在 G2 不會觸發：G2 的 break 前面一定是數字結尾的 item，不是標點。
- **G2 的實作正確且對稱。** `_spoken_later(numbers_only=True)`（`stages:326-338`）反向掃描：遇 `EndUtteranceCommand`／`ConfigProfileTriggerCommand` 歸零，遇有聲 item 記「它是否以數字開頭」；正向旗標 `spoken_before`（`:405-406`）記「前一個有聲 item 是否以數字結尾」，同樣在 utterance 結尾歸零（`:379-380`）。兩者都用 `_spoken_kinds`（`:321-323`），和 `_number_item_segments` 自己的 `spoken_kinds`（`:445`）是同一個切法，所以 `"第1"`（text, number）、`" 10"`（number）、`"10 "`（number）、`"COVID-19"`（text, number）判斷一致。`["10", "a", "20"]`、`["10", EU, "20"]`、`["第1", "章"]` 都沒有 break（`test_number_mode_without_groups_keeps_numbers_in_two_items_apart` 的 text-between、utterance-end、text-next）。
- **group > 0 的路徑和 `master` 的 number／group 模式是同一套機制**（`stages:297-298` 的三個 break 實例、`_merge_edge_breaks`、`_spoken_later` 在 `numbers_only=False` 時 `spoken = True`、`spoken_before = True`，與 `master` `:384` 的 `spoken_before or _is_spoken(item)` 等價）。
- **設定層。** `SPIN_MAX = 2**31 - 1`（`psettings:45`）同時是 confspec 的 `max` 與 spin 的上限；表格守衛新增 `check_spin_fits_wx`（`test_settings_table_guard.py:171-177`），把 `max_value=2**31` 的表格複本判為壞（我把 `SPIN_MAX` 改成 `2**31`，`test_group_size_confspec_is_its_range` 紅）。我用 NVDA 自己的 configobj（`D:/NVDA/nvda/.venv`，5.1.0）跑 `Validator().check("integer(default=0,min=0,max=2147483647)", v)`：`"0"`、`"5"`、`"2147483647"` 通過；`"2147483648"`、`"99999999999999999999"` → `VdtValueTooBigError`；`"-1"` → `VdtValueTooSmallError`；`"abc"`、`"3.5"`、`"group"`、`""` → `VdtTypeError`；缺 key 的預設 0。和 spec F3 一致，`read_stored`（`psettings:376-390`）接 `ValidateError` 回預設並只警告一次（`test_a_refused_stored_group_size_reads_as_zero`）。存的 `numberMode=group` 經 `_number_mode`（`:71-73`）讀成 value，ring 的 `availableNummods` 來自 `NUMBER_MODE_CHOICES`（`test_number_modes_match_the_driver_and_the_panel` 釘住 `["none","value","number"]`），`synth.nummod = "group"` 存成 value（`test_synth_nummod_group_stores_value`）。`depends_on` 拿掉後 `controllerKeys` 只剩 `punctuation_pause_enabled`（`test_panel_layout.py:87-90`），兩個面板的 spin 在每個模式都 enabled，模式 choice 不再被 bind（`test_pipeline_panel_binds_only_the_controllers`）。
- **測試抓得到它聲稱的錯誤。** 16 個突變 15 個 KILLED、1 個預期等價存活（M1）；每個 KILLED 的第一個紅燈都是對應該行為的那個測試（表在下方）。另外驗證 spec §9.3 的 P-U5 是「prototype 的 3000 個例子」等級：我把 `max_examples` 暫時改成 3000 跑過（通過），但也發現它在 `HYPOTHESIS_PROFILE=deep` 下仍只跑 300 個（M2）。
- **翻譯。** 六個 readme 都只有一個 hunk（`@@ -43,17 +43,16 @@`），從第 59／60 行起到檔尾（含 7.0 changelog）逐字相同（`diff` 空）。en 與 zh_TW 和 spec §6.4 逐字相同；zh_HK 與 zh_TW 在 `master` 就是同一份內容（blob 相同），改後仍相同。ru／uk／zh_CN 的用詞對過 `.po`：ru「Размер группы」「Речевой канал」「целым числом／по цифрам／не обрабатывать」，uk「Розмір групи」「Мовлення」「цілі числа／по цифрах／не обробляти」，zh_CN「每组位数」「语音流程」「数值／数字／不处理」都和介面字串一致；zh_CN 的「千位分隔符」、「空格」、「文本」沿用該檔既有用語；ru／uk 的句子通順，數字例子（123／4／точка／567／8；1,234,567 → 123／456／7）與 en 一致；縮排各檔自己的風格保留（zh_TW／zh_HK 單空格、其餘雙空格）。`readme.md:37` 的全域設定清單仍列「group size」，正確。
- **§8 限制。** 8 個 commit 都是英文 `<type>: <summary>` 加原因，0 個 `Co-Authored-By`；受保護路徑與 Neural 兩個指令都無輸出；`git diff --stat master...HEAD -- addon/locale` 空（O6）；`git diff --check master...HEAD` 乾淨；`grep -rn '"group"' addon/synthDrivers/WorldVoice/pipeline` 只剩 `psettings:67` 的「讀成 value」註解；`numbers.py` 仍只 import 標準函式庫；沒有動 `driver/*/driver/`、`sonic/`、Unicode 資料檔；分支只改 `addon/synthDrivers/WorldVoice/pipeline/{breaks,numberStages,numbers,settings}.py`、6 個 readme、`tests/`、`docs/`；prek 8 個 hook 在 scratch 複本上對全部 30 個改動檔 Passed。

## Critical

無。

## Important

無。

## Minor

### M1. number＋每組位數 0 的 G2 同時放 `edge_before` 和 `edge_after`，其中 `edge_before` 這一半對輸出沒有任何影響（等價突變存活）（`stages:405-406`、`:402`、`:446-447`；commit `1bd5a146`）

spec §4.3「group 0, number」列要求：第一個 item 在「下一個有聲 item 以數字開頭」時放 `edge_after`，第二個 item 在「前一個有聲 item 以數字結尾」時放 `edge_before`，再由 `_merge_edge_breaks` 留一個。但這兩個條件是同一個合取（前一個以數字結尾 ∧ 下一個以數字開頭），而且兩個旗標在 utterance 結尾的歸零方式一樣，所以只要 `edge_after` 放了，`edge_before` 一定也放，反之亦然；合併後只留第一個，也就是 `edge_after`。結果：把 `spoken_before = not numbers_only or _spoken_kinds(item)[-1:] == ["number"]` 改成 `spoken_before = not numbers_only`（number＋0 永遠不放 `edge_before`），6 個數字相關測試檔 834 個測試全綠（突變 m5）。反過來拿掉 `edge_after`（m6）會被 `command` 列抓到（`"1 0"`, M, E, `"2 0"` ≠ 期望的 `"1 0"`, E, M, `"2 0"`），所以 i29「第一個留下」的位置是被釘住的，只是靠 `edge_after` 釘的。

失敗情境：沒有使用者可見的失敗；這是程式碼有一半無法被任何測試區分，§7 要求把這類存活 mutant 記下來。

建議修法（二擇一，都不改行為）：(a) 在 `_inject_item_numbers` 把 number＋0 的 `edge_before` 省掉——`edge_before=item_edge if spoken_before and not numbers_only else None`，並把 `:405-406` 還原成 `master` 的 `spoken_before = spoken_before or _is_spoken(item)`，同時在 spec §4.3 的那一列與 `inject_numbers` docstring（`:280-283`）註明只放在第一個 item 的尾端；(b) 保留現狀，在本檔（已做）與 spec §9.4 記為等價 mutant。建議 (a)：少一個 `_spoken_kinds` 的正向掃描，也少一條沒人能測的分支。

### M2. P-U5 的 `@settings(SHARED_ENV, max_examples=300)` 讓 `HYPOTHESIS_PROFILE=deep` 對它無效（`test_pipeline_number_groups.py:347`；commit `07fb6fd3`）

`settings()` 裡明寫的 `max_examples` 優先於 profile，所以 `HYPOTHESIS_PROFILE=deep`（conftest 的 20000）下這個性質仍然 `Stopped because settings.max_examples=300`（我在 deep profile 下開 `--hypothesis-show-statistics` 確認）。spec §9.3 說 P-U5 是「the prototype's check」（prototype 跑了 3000 個），§9.3 又說 review 用 deep profile；帳本 Task 5 寫「HYPOTHESIS_PROFILE=deep run of the groups and edge properties」，對 P-U5 實際只有 300 個。其他 5 個 groups 性質在 deep 下確實跑到 20000（134 s 全綠）。

失敗情境：將來 G1／G2 的某個邊角（例如新的空白字元或新的 command 類別）只在少見組合下出錯時，deep 跑法給不了比預設更多的保證。我把上限暫時改成 3000 跑了一次，通過（5.3 s，所以成本不是問題）。

建議：把 300 拿掉，讓它跟 profile（預設 200，deep 20000；本機 20000 個約 30–60 s）；若要在預設 profile 多跑一點，用 `settings(SHARED_ENV, max_examples=max(300, settings().max_examples))` 之類寫法，或在 conftest 註冊一個 `slow` 的 per-test profile。

### M3. `test_a_refused_stored_group_size_reads_as_zero` 只用 stub 的 refusing section；真 configobj 的驗證只在 spec（手動）與本次 review 做過（`test_pipeline_settings_service.py:417-437`；commit `12893d87`）

帳本已說明原因（venv 沒有 configobj，spec §9.2 的「where the harness has it」不成立），結論正確。但 `D:/NVDA/nvda/.venv/Lib/site-packages/configobj` 就在 `ref/nvda` 旁邊，而其他測試（`pipeline_harness.py:421-423`、`test_pipeline_nvda_ssml.py`）已經有「`ref/nvda` 沒 checkout 就 skip」的模式。失敗情境：將來 confspec 字串的寫法改了（例如有人把 `max=` 拿掉或寫成 `2**31-1`），stub 不會發現，只有真 Validator 會。建議：加一個 `pytest.importorskip` 風格的測試，從 `ref/nvda/.venv/Lib/site-packages`（存在時）載入 `configobj.validate.Validator`，對 `PIPELINE_CONFSPEC["groupSize"]` 跑上面那 8 個值；沒有就 skip。可不修。

## 審閱者自行驗證的項目

pytest 一次只跑一個行程，沒有平行 worker。突變由 `mut.py` 以精確字串替換套用（舊字串必須恰好出現一次），每個跑完 `git checkout -- <file>` 還原並斷言 `git status --porcelain` 為空；殺死的突變以 `-x` 停在第一個紅燈，表中列的是那個測試。

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 完整測試（分支 worktree） | `python -m pytest -q -p no:cacheprovider tests` | **3623 passed、9 failed、1 skipped**（150 s）；9 個 failed 全在 `test_generated_unicode_data.py`，與帳本、基準相同 |
| 7.0 changelog 未動 | 六個 readme：`diff <(git show master:f \| sed -n '60,$p') <(sed -n '59,$p' f)`；hunk 標頭 | 六個都只有 `@@ -43,17 +43,16 @@` 一個 hunk；第 59／60 行以後逐字相同 |
| 真 configobj 驗證 | `wv_cfgcheck.py`：`sys.path` 指向 `D:/NVDA/nvda/.venv/Lib/site-packages`（唯讀 import），`Validator().check("integer(default=0,min=0,max=2147483647)", v)` | 0／5／2147483647 通過；2147483648、10^20 → TooBig；-1 → TooSmall；abc、3.5、group、"" → TypeError；缺 key 預設 0 |
| §8：commit message | `git log master..HEAD --format=%B \| grep -ci co-authored` | 0；8 個 commit 都是英文 `<type>: <summary>` 加原因段 |
| §8：受保護路徑 | `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' driver/sonic/ unicodeScripts/{script_data,unspaced_common_data}.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 兩個都無輸出 |
| O6：`.po` 未動 | `git diff --stat master...HEAD -- addon/locale` | 空 |
| `git diff --check master...HEAD` | | 乾淨（rc 0） |
| `"group"` 殘留 | `grep -rn '"group"' addon/synthDrivers/WorldVoice/pipeline addon/synthDrivers/WorldVoice/__init__.py addon/globalPlugins` | 只有 `psettings:67` 註解 |
| prek | scratch worktree：`prek.exe run --files $(git diff --name-only 65856d26 HEAD)`（30 個檔） | 8 個 hook 全 Passed（check-yaml 無檔案 Skipped）；之後的 `M` 只是 autocrlf 換行雜訊（`git diff` 0 行），已 `git checkout -- .` |
| m1 G2 拿掉（`edges=(None, NB, None)`） | 6 個數字測試檔 | KILLED：`test_number_mode_without_groups_keeps_numbers_in_two_items_apart[items]` |
| m2 gap 條件回到 `edge is not None`（`master` 行為） | 同上 | KILLED：`test_numbers_that_only_whitespace_separates_get_one_break[number-…-0-space]` |
| m3 edge 條件回到 `mode == "number"`（`master` 行為） | 同上 | KILLED：`test_edges_appear_iff_a_group_and_a_pause[none-3-10]` |
| m4 pass-through 不看每組位數（`master` 行為） | 同上 | KILLED：`test_off_with_a_group_size_runs_the_stage` |
| m5 number＋0 永不放 `edge_before` | 同上 | **SURVIVED**，834 passed（50 s）→ M1，等價突變 |
| m6 number＋0 永不放 `edge_after` | 同上 | KILLED：`…keeps_numbers_in_two_items_apart[command]`（break 跑到 command 之後） |
| m7 `number_wait_factor` 在 number 模式也 split | 同上 | KILLED：`test_numbers_that_only_whitespace_separates_get_one_break[number-…]` |
| m8 value 不命名符號片段 | 同上 | KILLED：`test_render_piece_by_mode[.-value-…]` |
| m9 number＋0 不做 `_merge_edge_breaks` | 同上 | KILLED：`…keeps_numbers_in_two_items_apart[items]`（兩個 E） |
| m10 pause 0 時把片段接起來（O1 反向） | 同上 | KILLED：`test_property_lone_number_is_its_pieces_with_one_break_between_each_two` |
| m11 number 模式把正負號和第一位數分開（O3 反向） | 同上 | KILLED：`test_render_piece_by_mode[-123-number-…]` |
| m12 `SPIN_MAX = 2**31` | 5 個設定測試檔 | KILLED：`test_group_size_confspec_is_its_range` |
| m13 預設改回 3 | 同上 | KILLED：`test_table_drives_fields_defaults_keys_and_confspec` |
| m14 加回 `depends_on=("number_mode", "number")` | 同上 | KILLED：`test_group_size_is_an_independent_panel_only_spin` |
| m15 加回 `("group", _("group"))` | 同上＋groups | KILLED：`test_number_mode_choices_put_off_first` |
| m16 `min_value=1` | 同上 | KILLED：`test_group_size_confspec_is_its_range` |
| P-U5 以 3000 個例子（spec prototype 等級） | scratch 把 `max_examples=300` 暫改 3000，`-k two_numbers_never_share --hypothesis-show-statistics` | 1 passed，5.3 s，`Stopped because settings.max_examples=3000`；改動已還原 |
| deep profile 對 groups 的 6 個性質 | `HYPOTHESIS_PROFILE=deep pytest tests/test_pipeline_number_groups.py -k property` | 6 passed（134 s）；P-U5 顯示 `Stopped because settings.max_examples=300` → M2 |
| scratch worktree 清理 | `cmd /c rmdir ref\nvda`；`git worktree remove`；`ls D:/NVDA/nvda/source/languageHandler.py` | junction 移除、worktree 移除、NVDA 原始碼仍在（見 commit 後的回報） |

### plan Review Focus 逐項

1. **表格逐格朗讀（number＋0）**：`["10","20"]`、`["10", M, "20"]`、`["10", " ", "20"]`、`["10", L(en), "20"]`、`["10", EU, "20"]`、`["第1","2章"]`、`["第1","章"]`、`["10","a","20"]`、`["a 10","20 b","c"]` 都在 `test_number_mode_without_groups_keeps_numbers_in_two_items_apart`，i16–i18、i29 在 `ROWS`；P-U5 的 ITEM 分隔也涵蓋。m1／m6／m9 都被它抓到。✔
2. **其他空白**：`test_numbers_that_only_whitespace_separates_get_one_break` 跑 space／兩個 space／nbsp／ideographic × 三模式 × {0, 3}；P-U5 同樣四種加 item 邊界。m2／m7 被抓到。✔
3. **巨大／無效的儲存值**：`convert` 的 0／1／11／2^31−1／"7"／−1／2^31／10^20（`test_group_size_outside_its_range_reads_as_the_default`）、P-S（`st.integers()` 加 `str(v)`）、`test_a_refused_stored_group_size_reads_as_zero`、`check_spin_fits_wx`、pieces 列 `123`／2147483647；面板 typed −1、2147483648 存 0，stored −1、2147483648 顯示 0。真 configobj 由我驗證（M3 建議自動化）。✔
4. **舊 profile `numberMode = group`**：`test_a_stored_group_mode_reads_as_value_and_keeps_the_stored_size`（group＋groupSize 4 → value、4）、`test_a_stored_pair_mode_reads_numbers_as_values[group-size-2／no-size]`、`test_synth_nummod_group_stores_value`、`test_number_modes_match_the_driver_and_the_panel`、兩個面板「每個 stored mode 都 enabled」含 "group"／"pair"。✔
5. **none＋N 與沒有名字的符號**：pieces 列 `1.,2`、`5×3`；i3、i7；`test_an_unnamed_symbol_is_left_to_the_punctuation_stage[none]`；P-none；`test_property_every_symbol_is_its_own_item_when_some_have_no_name` 跑三模式。✔

### 帳本的 Ruling 與 plan 偏離

| 項目 | 評估 |
| --- | --- |
| Task 2：`test_available_nummods_match_number_modes` 沒加進 `test_worldvoice_pipeline_settings.py`（harness 沒 `StringParameterInfo`），改由 `test_number_modes_match_the_driver_and_the_panel` 斷言 `== ["none","value","number"]` | 合理；同樣釘住 driver、表格、面板三者一致，Review Focus 4 有覆蓋 |
| Task 2：P-S 提前在 Task 2 重寫 | 合理；舊性質在新表格下必紅 |
| Task 2：venv 沒 configobj，真 Validator 變體做不到 | 原因屬實；我用 NVDA 的 configobj 補做（結果與 spec F3 同），建議見 M3 |
| Task 4：i30 放在 groups 測試而非 `ROWS`（`ROWS` 在 import 時建立，stub 還不存在） | 合理；內容相同 |
| Task 5 `Ruling:` 保留 `test_property_breaks_and_names_stay_inside_numbers` | 合理；它檢查「只有數字內的符號被命名」而且文字夾雜，P-G3 只看單獨的數字；成本 ~1 s |
| Task 5：deep 發現 P-U4 檢查沒 strip nbsp，修測試不修程式 | 看過 `test_pipeline_number_edge_properties.py:140-145`，`before.strip()` / `after.strip().lstrip("+-")` 的判斷正確 |

## 使用者還沒確認的使用者可見預設

- **O1** pause 0 且每組位數 > 0：片段之間仍放 `NumberBreakCommand(0)`，每片是一個 item（和今天的 group 模式一樣）；另一個選項是接成一個 item。
- **O2** number＋0 兩個 item 各以數字結尾／開頭時保留一個數字停頓（今天 number 模式就有）；旁邊是文字時沒有停頓（U4）。
- **O3** number＋N 的正負號跟第一位數：`"-123456"` → `"-1 2 3"`, NB, `"4 5 6"`。
- **O4** 每組位數上限 2147483647（confspec 與 spin 相同）；更大的儲存值讀成 0 並記一次 debug warning。
- **O5** 標籤仍是「Group size／每組位數」，沒有加「(0 = no grouping)」；0 的意義只寫在使用手冊。替代：`Group size (0 = no grouping)`／「每組位數（0 為不分組）」，代價是六個語言暫時回到英文。
- **O6** `.po` 不動，msgid "group" 留著不用；下次 `scons pot` 會拿掉。
- **O7／F6** 本分支不加 changelog 段；`readme.md:92`（與五個翻譯的同一段）的 7.0 changelog 仍說「In digit mode and group mode, the number pause now also separates every number from the text next to it」，而合併後沒有 group 模式、digit 模式在每組位數 0 時也沒有這個停頓。如果 7.0 還沒發佈，協調者在發佈前要決定是否改這一句。
- **O8** mutmut 沒跑（Windows）；本 review 的 16 個手動突變替代了一部分，存活的等價 mutant 記在 M1。
- 另外提醒（U4／U7 已由使用者決定，不是待確認，但是使用者會聽到的差別）：升級後 number 模式使用者沒有儲存每組位數時會失去數字前後的停頓；舊 group 模式使用者沒改過大小時變成純 value 模式。

## 尚未驗證

- spec §9.5 M1–M7（Windows NVDA 面板、ring、升級 profile、無效值、OneCore／eSpeak 聽感、wx 4.3.2 的 spin 上限）都沒有在真 NVDA 裡做；本 review 只到測試 stub 與 NVDA 的 configobj／`ref/nvda` 原始碼。
- 未打包。

## 修正記錄

修正者：Opus 5.5（DEVELOPMENT_WORKFLOW.md §3.4），在分支 worktree 上，從 `bf252ab3` 開始。

- **M1：已修，`9163cf10`**（`refactor: drop the dead edge_before of number mode without groups`）。採建議 (a)：`_inject_item_numbers` 在 number＋每組位數 0（`numbers_only`）時不再放 `edge_before`（`edge_before=item_edge if spoken_before and not numbers_only else None`），`spoken_before` 還原成 `master` 的 `spoken_before = spoken_before or _is_spoken(item)`；docstring、註解與 spec §4.3 的表格列和實作說明一併更新。行為不變的理由：`edge_after`（第一個 item 尾端）與 `edge_before`（第二個 item 開頭）的條件是同一個合取（前一個有聲 item 以數字結尾 ∧ 下一個有聲 item 以數字開頭），兩個旗標在 utterance 結尾的歸零方式一樣；兩者之間只有指令與空白文字，所以落在 `_merge_edge_breaks` 的同一個 run，是同一個物件、同一個時間，`edge_before` 一定在 `edge_after` 之後。run 裡的保留規則是「最長；平手時第一個非 edge break，否則第一個 edge break」，`edge_before` 永遠不會勝過它前面的 `edge_after`，所以拿掉它不改變 run 的結果，後面的 item／punctuation 階段看到的序列也相同。沒有新增只釘這條死路徑的測試；既有的 G2 測試、i29、`test_number_mode_without_groups_takes_the_longer_item_pause` 都綠，P-U5 在 deep profile 下 20000 個例子通過。
- **M2：已修，`6d50afa8`**（`test: let the Hypothesis profile set P-U5's example count`）。拿掉 P-U5 的 `max_examples=300`，改成和這個檔案其他性質一樣的 `@SHARED_ENV`，例子數由 profile 決定（spec §9.3：預設 200，review 用 deep）。驗證：預設 profile `--hypothesis-show-statistics` 顯示 `Stopped because settings.max_examples=200`（0.5 s）；`HYPOTHESIS_PROFILE=deep` 顯示 `20000 passing, 0 failing` 與 `Stopped because settings.max_examples=20000`（約 39 s）。附帶發現：`test_pipeline_number_edge_properties.py:256`、`:270` 也有 `max_examples=400` 的同樣寫法（不在本分支的 review 範圍，未改）。
- **M3：未修。** 審閱者已經用 NVDA 自己的 configobj（`D:/NVDA/nvda/.venv`，5.1.0）手動驗證過 `integer(default=0,min=0,max=2147483647)` 對 8 個值的結果，與 spec F3 一致。自動化的測試要依賴 NVDA 的開發 venv，container 與其他 checkout 都沒有這個 venv，在那些環境只會 skip，提供的保證有限。列為未確認的預設：confspec 字串之後若改寫，只有 stub 的測試會跑到，真 Validator 的行為要靠人工再確認一次。
