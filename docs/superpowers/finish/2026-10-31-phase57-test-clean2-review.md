# Review：Phase 57 test-clean2 removals（刪除 486 個低價值測試）

日期：2026-10-31。分支：`phase57-test-clean2`（`3c178f4..fec2c3f`，32 個 commit：5 個 `docs:`、27 個 `test:`；基準 `master` `3c178f4` 3727 passed／0 skipped，分支 3243 passed／0 skipped）。
審閱者：Fable 5.1（唯讀；只新增本檔）。流程：一般流程（DEVELOPMENT_WORKFLOW.md §3.3）。批次 1（Tasks 1–5）與批次 2（Tasks 6–10）已各有一份批次 review（`scratchpad/p57/batch1-review.md`、`batch2-review.md`），本次把重點放在批次 3（`f4e9df4..fec2c3f`：R4–R7、fixture 切換、兩個改名、E1–E5、清理 commit `2ae55ac`、M1–M3）和三個 review 追加的測試（`c464e2a`、`5c1be56`、`f85006c`），並把端到端的證明、覆蓋率與抽查整個重做一遍。

依據：

- spec `docs/superpowers/specs/2026-10-31-phase57-test-clean2-design.md` 與附錄 `-remove.txt`（486 個 id）、`-renames.txt`（7 個改名、2 個新 id）、`-edited.txt`（164 行：13 `[E]`、4 `[E][N]`、3 `[M]`、125 `[R]`、13 `[F]`、3 `[V]`）、`-coverage-before.txt`（84 個模組）；plan `docs/superpowers/plans/2026-10-31-phase57-test-clean2.md`（Review Focus 1–5 逐項檢查）；進度帳本 `.superpowers/sdd/2026-10-31-phase57-test-clean2/progress.md`（21 行 `Ruling:`，全部評估）；稽核 `storage/test-clean2.md`、`storage/test-clean2-remove.txt`（455）、`storage/test-clean2-decide.txt`（121）。
- 實驗都在暫時 worktree `scratchpad/p57/fable/wt`（detached，自己的 `ref` symlink，結束後已移除）；審閱者自己的腳本在 `scratchpad/p57/fable/tools/`（`fcollect.py`、`fproof.py`、`fsrc.py`、`guard.sh`），輸出在 `scratchpad/p57/fable/out/`。實作者 `scratchpad/p57/impl/` 的腳本與輸出沒有拿來當證明。
- 行號以 head `fec2c3f` 為準，被刪的測試以 `3c178f4` 為準；路徑省略 `tests/`。

## 結論

**可以 merge。** Critical 0、Important 0、Minor 2（都是清理 commit 留下的外觀問題，不影響任何測試的判定）。

- **端到端收集證明成立，而且我用自己的腳本重做。** `3c178f4` 收集 3727、`fec2c3f` 收集 3243；以 (函式, 參數值) 的多重集合比較「基準 − 486 個 id」與「head − 2 個新 id」完全相等；7 個改名都對到；id 層面只剩 69 個索引改號配對，全部落在 spec §5.2 列的函式加 D4（`test_number_re_finds_whole_numbers` 17、`test_number_wait_splits_numbers_separated_only_by_whitespace` 13、`test_worked_examples` 15、`test_pauses_between` 10、`test_engine_enabled_reads_the_config_then_the_manifest` 3、`test_number_wait_breaks_only_between_whole_numbers` 3、`test_network_errors_name_the_url_and_suggest_a_local_file` 1+2、`test_a_configured_engine_flag_overrides_the_manifest_default` 1、`test_select_drops_characters_without_an_unspaced_script` 1、`test_native_and_parse_errors_fail_original_work_without_drain` 1、`test_scaled_waits_are_the_global_units_times_the_factor` 1、`test_read_control_without_a_control_is_absent` 1）。配對是以參數值相等為條件，所以「改號後的 id 帶著相同的參數值」由構造保證。三個紅燈對照（少列一個 id、少一行改名、竄改一個 head 參數值）都正確地 FAIL。帳本 Ruling（Task 11）說的 fixture 名稱對應（`engine → skipped_engine`）我也獨立碰到：不做對應時只有 `test_ready_on_ref_nvda_is_true_and_silent` 的兩個 id 報錯，其餘全部相符。
- **最終清單就是稽核清單加 31 個傾向移除的 decide 項。** `storage/test-clean2-remove.txt` 的 455 個 id 全在最終清單裡；多出來的 31 個 id 全在 `storage/test-clean2-decide.txt`。
- **覆蓋率逐模組相同。** 完整 `--cov=addon --cov-branch` 一次（3243 passed、167.6 s、watchdog 未觸發）：84 個模組的 Stmts／Miss／Branch／BrPart 四個數字全部和 `-coverage-before.txt` 相同，TOTAL 8368／180／2374／157；唯一的字面差異是百分比欄的格式（基準印 `96.75%`，我這次印 `97%`），不是數字差異。`addon/generics/coreArchive.py`、`addon/installTasks.py`、`workspace.py` 都 100%（Review Focus 1、N4）。
- **R1–R7 恰好保留 spec 的 case。** `-edited.txt` 的 125 個 `[R]` id 全部在 head 的收集裡，而且這 8 個函式在 head 沒有多出任何一個 id（`test_number_mode` 27、`test_number_and_group_modes_name_each_symbol` 21、`test_number_stage_worked_examples` 55、`test_unconfirmed_wrapper_uses_legacy_and_logs_concrete_fallback_once` 3、兩個 R5 測試各 5、`test_voice_parameters_commit_and_follow_the_consistency_policy` 7、`test_pipeline_panel_enables_pause_controls_from_the_stored_switch` 2）。R4–R7 的函式本體在 diff 裡沒有改（R4 `test_runtime_composition.py:911-914`、R5 `test_pipeline_settings_service.py:389-393`、R6 `test_worldvoice_pipeline_settings.py:178-184`、R7 `test_settings_panels.py:320`），只換了 decorator。fixture 切換（`test_nvda_ready.py:98-99`）：`engine` 與 `skipped_engine` 都是 `yield from _opened(request.param, …)`（`:73-81`），只差 params，`[Espeak]`、`[OneCore]` 的參數值不變。
- **合併與搬移沒有漏掉斷言。** M1（`test_worldvoice_cancel_wrappers.py:207-229`）：被刪測試的 `idles == 0` 是「native 內 `cancel()` 再 `_onIndexReached(7)` 的請求不產生 idle」；合併後在 live 請求之後記下 `idles`，被取消的請求（`:214-216` 同樣在 native 內 `cancel()` 再 `_onIndexReached(7)`）之後斷言不變，語意等價。M2（`test_role_panel_ui.py:137-138`）：harness 的 `SettingsPanel.Bind` 記 `(event, handler, source)`（`ui_harness.py:409-414`），`EVT_WINDOW_DESTROY` 是字串，所以 `("EVT_WINDOW_DESTROY", panel._onDestroy, None)` 是對的；被刪 D21 另外斷言的 `setMainVoice` 行為（現任 synth 是 WorldVoice 時走 `changeVoice`、不是時只寫 config，`panels/role.py:40-46`）由保留的 `test_setting_the_main_voice_goes_through_nvdas_change_voice:118-122` 與 `…_without_worldvoice_only_writes_the_config:125-129` 釘住。M3：`test_core_archive.py:21-80`（`c68c9aa` 版）與 `test_core_install.py:167-225` 逐位元組相同；`test_core_install.py` 其餘差異只有 docstring 一句、`import types`、`load_definitions`、`PLUGIN`；loader 仍是 `core_archive_harness.load(INSTALL, …)` 的真實檔案（N4）。`test_core_install.py` 自己的 `make_zip`（`ZIP_STORED`、回傳 `Path`）和舊的不同，但搬過來的測試不用回傳值、成員相同，無影響。
- **E1–E5 照 spec。** E1 刪 `:70-72` 三行（`befe7bd`，純刪除）；E2 刪 `MOVED`／`top_level_names`／`:136` 斷言，`symbols.py` 的相對 import 檢查原封不動搬進 `test_symbols_module_has_no_relative_imports:120-124`，`:103-105` 的註解留在它解釋的 import 斷言上；E3 刪 `default_voice` 掃描；E4 刪 `_guardInstalled` 斷言並改名，註解提到 `fix/ve-drop-cancellation-token`；E5 的註解不再指向被刪的 bridge 測試（措辭見 M2）。`_TOKEN_NAMES`（`test_native_strategy_guards.py:596`）同時含 `cancellationToken` 與 `supportsCancellationToken`，E1 刪掉的兩個斷言的名字都在守門範圍內。
- **清理 commit `2ae55ac` 行為中性。** 刪掉的每個分支都對應一個已不存在的參數值：`test_nvda_event_bridge.py` 的 `legacy`（`invalid` 剩 `unknown|wrong_context|owner|end_index`，四個都有自己的 `if/elif`，`:567-589`）、mismatch dict 的 `done`／`index`（`mismatch` 剩 `source|segment|end`）；`test_runtime_composition.py` 的 `bind`（`failure` 剩 `empty`）、`SAPI5`（`engine` 剩 `OneCore|VE`）、R4 的四個 failure；`test_runtime_session.py` 的 `mode != "LEGACY_DONE"`；`test_pipeline_filters.py` 的 `BreakCommand(5)` 三元式；`test_vocalizer_segment_drain.py` 的 `break`；R5 的 `item_wait_factor` 分支。我的 token 子序列檢查：六個檔案裡五個是純刪除，`test_runtime_composition.py` 只多了 `==`（`in (…)` 改 `==`，實作者在帳本已宣告為 edit）。`segment_event(env, "SEGMENT_END")` 和原來 `{"end": "SEGMENT_END"}[mismatch]` 在剩下的 case 值相同（Ruling 21）。收集不變（3246）。
- **三個 review 追加的測試都抓得到它們要抓的錯。** `c464e2a`：把 VE 與 Cerence `cancel()` 的 `self._leasedPlayer.stop()` 包進 `try/except OSError: pass` → `test_segment_after_player_stop_failure_fails[VE]`、`[Cerence]` 2 failed、4 passed。`5c1be56`：`VoiceSpec` 改成 `@dataclass(unsafe_hash=True)` → `test_runtime_value_classes_are_frozen` 1 failed。`f85006c`：`source_url` 固定回傳 16.0.0 的 URL → `test_downloaded_bytes_must_match_the_checksum` 1 failed、13 passed。
- **抽查 25 個刪除（批次 review 沒抽過的），沒有再找到涵蓋主張錯誤。** 16 個稽核「被涵蓋／重複」項加 9 個依傾向刪除的 decide 項，兩邊的測試都讀過（表在驗證項目之後）。只有一個看起來較弱的主張做了突變：`test_is_edge_break` 被刪後，`_edge_kind` 的 `getattr(command, _EDGE_MARKER, False)` 這一支（`pipeline/breaks.py:36`）只有它直接測；把它改成 `return False`，保留的 `test_other_synths_get_marked_edge_breaks[29|30]`、`test_other_synths_get_edge_breaks_across_items[*]` 等至少 5 個失敗，稽核說的「B* 標記的 plain break 參與合併」成立。
- **孤兒與過時引用。** 我自己的 AST 掃描（`tests/*.py` 頂層定義在整個 `tests/` 只出現一次者）只剩 4 個在 `master` 就已經沒人用的名字（`conftest.fresh_completion_rules`、`SHAPED_SYMBOLS`、`new_work`、`COMMANDS`），這個 phase 沒有留下新的孤兒；127 個被整個刪掉的測試函式名，在 `docs/superpowers`、`storage` 之外 0 處引用；4 個被刪的檔名在 `docs/superpowers` 之外 0 處引用（`pyproject.toml` 的 mutmut／pytest 設定只指到 `tests/` 目錄）；`start_delay`、`leased_player`、`MOVED`、`_guardInstalled`、`CONFSPEC`、`plain_shape`、`SCRIPT_LOOKUP` 等被刪機制的名字在 `tests/` 只剩同名但無關的定義（`test_pipeline_panels.py` 自己的 `voice_panel`、`test_runtime_legacy_adapter.py` 的 `ProbeCore.fail_on`）。
- **plan 的 Review Focus。** 1（M3 的複製檔盲點）：搬移逐位元組相同、loader 不變、`coreArchive.py` 100% ✓。2（fixture／helper 修改）：逐模組覆蓋相同，25 個被改的檔案單獨跑都過 ✓。3（順序依賴）：完整跑加單檔跑 ✓。4（R1–R7 差一）：多重集合證明加 `[R]` id 比對 ✓。5（時序 case 刪除）：五個並行檔三輪 411 passed；風險本身（helper 弱化後變 flaky 而非確定失敗）仍在，spec §7.5 已記，無法用測試消除。
- **帳本 21 個 `Ruling:` 都合理**（表在下方）。批次 1 的 m1 清單（含批次 1 review 補的四處和 Task 11 的兩處）在 `2ae55ac` 全部處理完；批次 2 的 m3 docstring 也在。
- **限制。** `addon/` 無任何 diff；受保護路徑與 Neural 無輸出；32 個 commit 都是英文 `<type>: <summary>` 加原因，0 個 `Co-Authored-By`；`ref`、`.superpowers` 未追蹤；分支只動 `tests/` 與 `docs/`；prek 8 個 hook 全 Passed；ruff 0.16.3。

## Critical

無。

## Important

無。

## Minor

### M1. 清理 commit 刪掉分支後，三個單列 parametrize 的參數變成沒人讀（`test_runtime_session.py:221-222`、`:233-234`；`test_pipeline_filters.py:221-224`；`test_runtime_composition.py:82-85`；commit `2ae55ac`）

spec §5.2 說「只剩一列的 parametrize 保留」，而 `2ae55ac` 又把讀那個參數的分支刪掉，結果是：`test_cached_activation_still_speaks_two_distinct_segments(…, mode)` 與 `test_session_rejects_foreign_context(…, mode)` 的 `mode` 整個函式沒有用到；`test_number_wait_does_not_break_across_other_commands(env, blocker)` 的第一行 `blocker = Marker()` 直接蓋掉自己的參數；`test_initialization_failure_closes_without_commit(composition, failure)` 只剩 `empty=failure == "empty"`，永遠為真。這和 Task 12 兩個改名的理由（「參數的機制變成死碼」）是同一種情況，只是這三個是清理 commit 之後才變成死碼的。失敗情境：沒有；只是讀者會以為還有別的 mode／blocker／failure 在測，或去找 `blocker` 參數的來源。建議：一個純刪除的 `test:` commit 拿掉這三個 decorator 和參數（`blocker` 那行改成直接 `Marker()` 已經是現狀），三個 id 掉尾碼（`[LEGACY_DONE]` ×2、`[index]`、`[empty]`），加進 `-renames.txt`；或放進 spec §5.6 延後清單並在 §5.2 補一句。不修也可以。

### M2. E5 的註解說這是「唯一」的檢查，略為誇大（`test_native_strategy_guards.py:641-643`；commit `53e2046`）

`test_no_add_on_code_names_the_request_token` 的註解現在寫 "This is the one check on that rule"。同檔 `test_vocalizer_voice_declares_waitfactor_and_variant:351-360` 仍把 VE／Cerence `Voice.extraCapabilities` 釘成恰好 `{"waitfactor", "variant"}`，所以那兩個 Voice 的 trait 回來時它也會失敗。差別是 AST 守門涵蓋全部原始檔（含 vendored inner），是 spec C1 想表達的重點。失敗情境：沒有。建議改成 "the one check that covers every add-on source file (vendored inner drivers included)" 之類；可不修。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 收集（基準與 head） | 自寫 plugin `fable/tools/fcollect.py`（集合／dict 依元素 repr 排序、帶型別名、遮位址），`PYTHONHASHSEED=0 python3 -m pytest --collect-only -q -p no:cacheprovider -p fcollect tests`，在 `3c178f4` 與 `fec2c3f` 各一次；head 另以 `PYTHONHASHSEED=77` 再收集一次 | 3727／3243；兩次 head 的 jsonl 位元組相同 |
| 端到端收集證明 | 自寫 `fable/tools/fproof.py base.jsonl head.jsonl -remove.txt -renames.txt --param-rename=…test_ready_on_ref_nvda_is_true_and_silent:engine=skipped_engine`（清單 id 都在基準；(函式, 參數) 多重集合相等；id 以相同參數一對一配對；`+ new` 都在 head） | `FPROOF OK`：removed 486、renames 7、new 2、pairs 69，全在 spec §5.2 函式加 D4 |
| 證明的紅燈 | 刪掉清單最後一個 id；拿掉 `test_menu_import…` 那行改名；把 head 的 `12.5` 參數竄改成 `12.6` | 分別 FAIL（2、4、16 個錯誤），都點名正確的 id |
| fixture 名稱對應的必要性 | 同上但不帶 `--param-rename` | 8 個錯誤，全部只在 `test_ready_on_ref_nvda_is_true_and_silent`（參數鍵 `engine`→`skipped_engine`，值 `Espeak`／`OneCore` 相同） |
| 最終清單 vs 稽核清單 | `comm` 比對 `-remove.txt`（486）、`storage/test-clean2-remove.txt`（455）、`storage/test-clean2-decide.txt`（121） | 455 ⊂ 486；多出的 31 個全在 decide 清單 |
| 完整測試＋分支覆蓋（scratch worktree `fable/wt` at `fec2c3f`，`guard.sh`：setsid，MemAvailable < 3 GB 只殺自己的 process group） | `COVERAGE_FILE=… python3 -m pytest tests -q -p no:cacheprovider --cov=addon --cov-branch --cov-report=term` | 3243 passed、0 skipped（167.6 s）；watchdog 未觸發，MemAvailable 起始 6.4 GB |
| 逐模組覆蓋比較 | 自寫比較器對 `-coverage-before.txt` | 84 個模組 Stmts／Miss／Branch／BrPart 全部相同；TOTAL 8368／180／2374／157；只有百分比欄格式不同（`96.75%` vs `97%`）；`coreArchive.py`、`installTasks.py`、`workspace.py` 100% |
| R1–R7 保留的 id | `-edited.txt` 的 125 個 `[R]` id 對 head 收集；同函式在 head 有無多出 id | 125／125 在 head；8 個函式沒有多出的 id（27／21／55／3／5／5／7／2） |
| M3 搬移比對 | `git show c68c9aa:tests/test_core_archive.py` 第 21–80 行 vs `test_core_install.py:167-225` 做 `diff`；其餘 diff 行逐行看 | 逐位元組相同；其餘新增只有 docstring 一句、`import types`、`load_definitions`、`PLUGIN` |
| M1／M2 的斷言搬移 | 讀 `test_worldvoice_cancel_wrappers.py:207-229`、`ui_harness.py:405-414`、`panels/role.py:28-52`、`test_role_panel_ui.py:118-138` | 等價（見結論）；D21 的 `setMainVoice` 兩個分支由兩個保留的 UI 測試釘住 |
| 突變 A：VE／Cerence `cancel()` 吞掉 stop 例外（`driver/VE/__init__.py:700`、`driver/Cerence/__init__.py`） | `pytest tests/test_engine_segment_contract.py -k stop_failure` | 2 failed（`[VE]`、`[Cerence]`）、4 passed → `c464e2a` 有效 |
| 突變 B：`VoiceSpec` 改 `unsafe_hash=True` | `pytest tests/test_runtime_playback_context.py` | 1 failed（`test_runtime_value_classes_are_frozen`） → `5c1be56` 有效 |
| 突變 C：`source_url` 固定 16.0.0 | `pytest tests/test_generate_unicode_scripts.py` | 1 failed（`test_downloaded_bytes_must_match_the_checksum`）、13 passed → `f85006c` 有效 |
| 突變 D：`_edge_kind` 不看 `worldvoice_number_edge`（`pipeline/breaks.py:36`） | `pytest tests/test_pipeline_number_edges.py tests/test_pipeline_stages.py tests/test_pipeline_punctuation_pause.py` | ≥5 failed（`test_other_synths_get_marked_edge_breaks[29|30]`、`…_across_items[end-item0|end-item10|alone-item0]`…）→ 刪 `test_is_edge_break` 的主張成立 |
| 純刪除 token 檢查（自寫：去掉 NL／NEWLINE／INDENT／DEDENT 後，新檔 token 是舊檔的子序列） | `4113da8`、`92385ff`、`befe7bd`；`2ae55ac` 的 6 個檔 | 三個 commit 純刪除；`2ae55ac` 五個檔純刪除、`test_runtime_composition.py` 只多 `==`（宣告的 edit）；紅燈 `c464e2a` 判為 ADDS TOKENS |
| 孤兒掃描 | 自寫 AST 掃描 `tests/*.py` 頂層名稱在整個 `tests/` 的出現次數 | 只剩 `master` 既有的 4 個；無新孤兒 |
| 過時引用 | `git grep -w -F -f gone-names.txt HEAD -- . ':!docs/superpowers' ':!storage'`（127 個名字）；`git grep -E "test_role_guards|test_workspace\b|test_worldvoice_index_command|test_core_archive"`；被刪機制名字的 grep | 只有 M3 搬過去的兩個定義本身；檔名 0 處；機制名只剩同名無關定義 |
| 沒人讀的 parametrize 參數 | 自寫 AST 掃描（parametrize 的 argnames 在函式本體沒有 `Name` 讀取） | `test_runtime_session.py` 兩個 `mode`（M1）；`test_number_stage_worked_examples` 的 `full`（`master` 就如此，非本 phase） |
| 單檔執行 | 25 個批次 3 動到或抽查涉及的測試檔各自 `python3 -m pytest -q -p no:cacheprovider tests/<file>`（watchdog） | 全部 rc=0 |
| 並行檔重複 | `test_segment_host.py`、`test_segment_lifecycle.py`、`test_runtime_scheduler.py`、`test_worldvoice_cancel_wrappers.py`、`test_vocalizer_segment_drain.py` 連跑 3 輪 | 每輪 411 passed |
| ruff／prek（scratch worktree） | `ruff check addon tests tools`；`ruff format --check addon tests tools`；`prek run --all-files` | All checks passed；242 files already formatted；8 個 hook 全 Passed；worktree 未被修改 |
| §8 限制 | `git diff --stat master -- addon`；受保護路徑兩個指令；`git log --format=%B master..HEAD \| grep -c Co-Authored`；`git log --format=%s`；`git diff --check master HEAD`；`git ls-files ref .superpowers`；`git diff --name-only master HEAD \| grep -v '^tests/\|^docs/'` | `addon/` 無 diff；受保護路徑與 Neural 無輸出；0；27 `test:`＋5 `docs:` 全為英文；diff check 乾淨；未追蹤；分支外無檔案 |
| 清理 | `git worktree remove --force fable/wt`；`git worktree list` | 只剩原有 worktree（master、tc2/base、phase57、SDKTest） |

### 抽查「被涵蓋／重複」與 decide 項（25 項，批次 review 沒抽過的）

| 被刪（`3c178f4`） | 涵蓋者（head） | 結果 |
| --- | --- | --- |
| G1 `test_vocalizer_segment_drain.py::test_explicit_activation_override_allows_successor_after_idle[VE\|Cerence]` | `test_late_endprocess_outside_call_preserves_next_buffer:1004-1016`（呼叫外 ENDPROCESS 回 USERSTOP、buffer 不動）；兩段依序 drain 由 `test_terminal_listener_can_speak_successor` 等 | 成立 |
| G2 `test_segment_host.py::test_segment_host_speaker_forwards_to_the_core_host` | D1 `test_every_core_speaks_segments_through_the_shared_mixin:168-172`（每個 wrapper 的 `speak_segment` 就是 mixin 的）＋每個 drain 測試都經 `speak_segment` 進入並斷言 context 的 id 回來 | 成立 |
| G3 `test_runtime_composition.py::test_initialization_failure_closes_without_commit[bind]` | `test_partial_bind_failure_releases_resources_without_commit:538-558`（同一條 bind 失敗清理路徑，多斷言 ledger 撤銷） | 成立 |
| G4 `test_pipeline_nvda_symbols.py::test_symbol_name_is_the_lookups_name` | `test_pipeline_filters.py::test_symbol_names_without_a_language_use_nvdas_current_language:475-479`（經真實 stage 得到 `N("×", "de")`） | 成立 |
| G4 `test_pipeline_punctuation_pause.py::test_is_edge_break` | `test_merge_edge_breaks:301-335`（三種 break 類別）＋ number_edges 的 `test_other_synths_*`（B* 標記的 plain break） | 成立（突變 D 被抓到） |
| G4 `test_pipeline_settings_service.py::test_group_size_outside_its_range_reads_as_the_default[0\|-5\|99]` | `test_property_group_size_convert_keeps_or_resets:663-667`（`st.integers()`，oracle `value if 2<=value<=10 else 3`） | 成立；邊界 1／2／10／11 與 `"7"` 仍保留 |
| G4 `test_pipeline_stages.py::test_zero_number_wait_keeps_spaces` | `test_property_zero_number_wait_changes_nothing:247-253`（`NUMBER_TEXT` 字母表含空白、tab、U+3000；wait −5..0；`is` 相等） | 成立 |
| G4 `test_pipeline_unspaced_space.py::test_common_characters_of_unspaced_scripts_are_unspaced[ー\|ｰ\|〆\|゛\|ˇ\|ˉ\|ˊ\|ˋ\|˙]` | `test_unspaced_common_keeps_the_hand_listed_characters:82-89`（U+3006、U+309B、U+30FC、U+FF70 與五個聲調符號 ⊂ `UNSPACED_COMMON`）＋`test_every_unspaced_common_character_is_unspaced:99-100` | 成立 |
| G4 `test_pipeline_punctuation_pause.py::test_an_empty_list_changes_nothing[False\|True]` | `test_property_an_empty_list_changes_nothing:207-220`（`characters=""`、`remove` 布林、`is` 相等） | 成立 |
| G5 `test_ui_controls.py::test_read_control_reads_a_checkbox[False]` | `test_read_control_ignores_driver_options_for_a_checkbox:194-198`（`value=False`、`is False`、`calls == [("GetValue",)]`） | 成立 |
| G5 `test_ui_controls.py::test_apply_dependencies_enables_dependents_from_their_controller[group-True-True]` | `test_apply_dependencies_only_enables_dependents:241-249`（同輸入、另斷言其他控制項無呼叫） | 成立 |
| G5 `test_voice_settings_panel.py::test_a_voice_switch_keeps_the_pause_controls_disabled` | `…_matches_the_controls_to_the_switch[False]:281-291`（從啟用切到停用）＋`test_a_voice_switch_shows_its_controls_in_place:147-157`（`shown_ids == list(sizerDict)`） | 成立 |
| G5 `test_voice_settings_panel.py::test_a_rebuild_for_worldvoice_places_the_controls_again` | `test_settings_order.py::test_voice_panel_orders_follow_the_table[other synth rebuild]:250-263`（`build_then:232-247` 先 `OtherDriver` 再 `refreshGui`；window／tab／row 順序與標籤位置全部比對） | 成立 |
| G5 `test_worldvoice_speak.py::test_an_unknown_number_language_reads_as_follow[zz]` | 保留的 `[fr]`（`_set_numlan:527-529` 對 zz／fr 走同一支：`store()` 的 `is_storable` 只問 `all_languages`）＋`test_number_language_choice.py::test_a_refused_value_stores_follow[zz]:34` | 成立 |
| G7 `test_detection_settings.py::test_update_writes_the_cyrillic_and_devanagari_keys[*]` | `update()` 是照 `SCRIPT_CONFIG_KEYS` 的通用迴圈（`languageDetection/settings.py:78-94`）；`test_update_writes_only_the_given_changed_keys:86-90`、`test_confspec_and_script_keys_keep_the_stored_names_and_defaults:143-159` | 成立 |
| G7 `test_core_archive.py::test_extracts_members_and_reports_skipped` | `test_core_install.py::test_any_extraction_error_skips_only_that_file:60-72`（被鎖成員略過、其他成員解出、警告訊息）；完整解開由 `test_install_extracts_every_core_archive_in_order_and_removes_it` | 成立；`coreArchive.py` 仍 100% |
| D5 `test_runtime_segment_completion.py::test_marker_pause_cancel_current_and_future_callback` | `test_runtime_scheduler.py` 的 `test_pause_forwarding_follows_the_current_segment`、`test_cancel_current_preserves_queued_request_and_gates_stop`、`test_future_callback_can_cancel_and_submit`（三件事分開測；契約不被這三條路讀） | 成立（使用者決定） |
| D9 `test_completion_rules.py::test_every_completion_mode_has_exactly_one_rule` | `test_rule_table_rows`；新 mode 少 rule 時 `rule_for` 會在大量測試 KeyError | 成立 |
| D10 `test_f4_engine_adapters.py::test_onecore_language_is_applied_only_on_activation` | `test_runtime_legacy_adapter.py::test_onecore_cached_a_b_a_restores_language`；被刪測試的 `BaseVoice` 是測試自建的假物件，「建構時不寫 language」近乎恆真 | 成立 |
| D12 `test_pipeline_filters.py::test_an_old_snake_case_log_switch_does_not_log` | 後半由 `test_run_logged_records_only_when_switched_on[INFO-True-True]`；前半是「舊名無效」存在性釘子（使用者要刪的類別） | 成立 |
| D17 `test_pipeline_nvda_ssml.py::…[group-pauses2]` | `[value]`、`[number]` 列（group 與 number 產生同樣的命令類別，speechXml 看不到新東西） | 成立 |
| D27 `test_plugin_voice_contract.py::test_no_bundled_voice_defines_a_pre_rename_name` | D11 `test_six_loaded_voices_pass_the_pre_rename_check[*]`（`hasattr` 連繼承名都看，spec 已核） | 成立 |
| D32 `test_native_strategy_guards.py::test_drain_support_requires_keywords[Espeak\|RHVoice]` | 簽名釘子，無行為 | 成立（存在性） |
| D33 `test_native_strategy_guards.py::test_onecore_uses_the_stop_gate_and_declares_voice_last` | 結構釘子；順序錯了 OneCore 載入測試會失敗 | 成立（存在性） |
| D40／D41 `test_old_pascal_case_keys_are_ignored`、`test_old_pascal_case_flags_are_ignored` | 「不遷移」存在性釘子，`get()` 本來只讀 camelCase | 成立（存在性；見未確認預設 2） |

### 進度帳本 `Ruling:` 評估（21 項）

| # | Ruling | 評估 |
| --- | --- | --- |
| 1（Task 1） | 另 commit `bf35bcf` 修 plan，不 amend | 合理；只改 Task 14 檔案清單 |
| 2（Task 3） | `delfn.py` 去掉檔尾多餘空行 | 合理；純空白，prek `end-of-file` 守住 |
| 3（Task 4） | 刪除 commit 保留被刪列留下的死分支 | 合理（刪除 commit 不混入 edit）；已在 `2ae55ac` 清掉，殘餘見 M1 |
| 4（Task 5） | `proof.py` 第 3 步也比對參數 | 合理且更嚴格；我的證明同樣以參數配對 |
| 5（Task 5） | 刪只描述 `12，34` 列的註解 | 合理 |
| 6（批次 1 I1） | `c464e2a` 契約測試改 `pytest.raises(OSError)` | 正確；突變 A 被抓到；同時替 Espeak 加了同一斷言（列為未確認預設 5） |
| 7（批次 1 m2） | `5c1be56` 新增 frozen 守門，`-renames.txt` 加 `+ new` | 正確；突變 B 被抓到；`IndexRange`／`VoiceSnapshot` 仍由既有 `FrozenInstanceError` 測試守住 |
| 8（批次 1 m1） | 死分支完整清單留到 Task 13 | 合理；`2ae55ac` 全部處理（含 Task 11 補的 R4／R5 兩處） |
| 9（批次 1 m3） | 改寫 `test_pipeline_nvda_symbols.py:75` 註解 | 合理；新句「Never an empty locale, nor a path outside…」同時涵蓋 `""` 與 `../locale/en` |
| 10（Task 6） | `rowdel.py` byte／char offset bug，重做 G4b | 合理；參數值比對會抓到被弄壞的列（批次 2 已核） |
| 11（Task 6） | 刪三個「所描述的列全部刪除」的註解 | 合理（批次 2 已逐一核） |
| 12（Task 6） | `delfn.py` 空行處理 | 合理；ruff format 守住 |
| 13（Task 8） | `tokcheck.py` 丟 INDENT／DEDENT、記首 token 欄位 | 合理；我的子序列檢查用同一設計，三個批次 3 純刪除 commit 都過 |
| 14（Task 8） | `delfn.py` 保留定義前空行 | 合理 |
| 15（Task 10） | R3 (c) 用 `ITEM_WAIT_IDS` 集合 | 可接受（批次 2 詳評）；本次的多重集合證明確認結果恰為 kept ids |
| 16（批次 2 m1） | `f85006c` checksum 測試改 15.1.0 並斷言 URL | 正確；突變 C 被抓到；無新 id |
| 17（批次 2） | Ruling 15 照原樣接受 | 合理 |
| 18（批次 2 m3） | `test_legacy_speech_commands.py` docstring 進清理 commit | 已做（`2ae55ac`） |
| 19（批次 2 m2） | `a047136` 把 spec／plan 計數改成 3243、§8 補例外 | 已做；spec `:25`、`:27`、`:290`、`:341` 一致 |
| 20（Task 11） | fixture 切換時證明把參數鍵 `engine` 對到 `skipped_engine` | 必要且正確；我不做對應時正好只有那兩個 id 報錯，值相同 |
| 21（Task 13） | mismatch 查表改成 `segment_event(env, "SEGMENT_END")` | 合理；剩下的 case 值相同，呼叫形狀同原本的位置參數 |

未做：未重跑 mutmut（本 phase 不動 `addon/`，以四個手工突變驗證三個新斷言與一個較弱的涵蓋主張）；未在 Windows／NVDA 實機驗證（純測試變更，使用者看不到也聽不到差異）；未打包。

## 使用者還沒確認的使用者可見預設

這個 phase 只改測試，NVDA 使用者看不到、聽不到任何變化。下面是協調者採建議預設、使用者可在 merge 前推翻的決定：

1. **C1：request-token 守門（D34、D35）違背傾向而保留**（spec §4 C1、§10.1）。理由是稽核其他五個刪除都把它指為保留的守門，而且只有它掃 vendored inner drivers。替代方案：兩個都刪，之後沒有任何測試擋 `cancellationToken`／`supportsCancellationToken` 回來。審閱者同意保留。
2. **N1：「speech symbols 已移除」與「ignore-numbers 已移除」的檢查照清單刪掉**（`test_hygiene_guards.py::test_the_speech_symbols_feature_is_gone`、`::test_the_ignore_numbers_option_is_gone`，以及 D40／D41 的 PascalCase 不遷移釘子），之後沒有測試擋這些選項回來。這和 C1 的判斷不同向（spec §7.8），使用者可能想一致處理。
3. **D38、D39 延後保留**（`test_translator_comments.py` 的 `CHANGED_LABEL_MSGIDS`／`DEAD_MSGIDS` 兩個測試）：傾向是「換成通用守門後刪」，通用守門（G6 合併建議）不在本 phase，所以先留。
4. **§5.6 的延後清單**：所有不是為了保住斷言的合併（G1–G7 各項）、保留測試裡的一行式存在性斷言、D45 改名，都留給之後的 phase。
5. **三個 review 追加的測試**（不在使用者核准的「照稽核刪」範圍內，spec §8 已列）：`c464e2a` 把契約測試 `test_segment_after_player_stop_failure_fails` 從吞例外改成要求 `cancel()` 對六個引擎都拋 `OSError("player stop failed")`（原本只有 VE／Cerence 的專屬測試這樣斷言，Espeak 是新加的要求）；`5c1be56` 新測試 `test_runtime_value_classes_are_frozen`（七個 runtime 值類別必須是 frozen dataclass）；`f85006c` 把 `test_downloaded_bytes_must_match_the_checksum` 的版本改成 15.1.0 並斷言下載 URL。三者都是為了補回稽核「被涵蓋」判斷錯誤造成的斷言流失。
6. **M1 若不修**：三個單列 parametrize 的參數留著沒人讀。
7. **時序 case 刪除後的檢查方式改變**（spec §7.5）：`[0.1]`、`[0.06]`、`[1]` 刪掉後，`_wait_until_waiting` 之類的 helper 若被弱化，會變成偶發失敗而不是確定失敗；現在靠的是 5× 重跑（實作者）／3× 重跑（審閱者）。
8. **只在 Linux 驗證**：所有結論都來自 Linux 的 fake／stub 測試，和基準相同。

## 修正記錄

協調者決定在 merge 前修好兩項 Minor（DEVELOPMENT_WORKFLOW.md §3.4）。

| 項目 | commit | 修法 | 驗證 |
|---|---|---|---|
| M1 | `4a765f1` | 拿掉四個測試裡沒人讀的單列 parametrize：`test_runtime_session.py` 的兩個 `mode`、`test_pipeline_filters.py::test_number_wait_does_not_break_across_other_commands` 的 `blocker`（函式本體會覆寫它）、`test_runtime_composition.py::test_initialization_failure_closes_without_commit` 的 `failure`（`empty=failure == "empty"` 恆為真，直接寫成 `empty=True`）。這四個 id 不再帶 `[...]` 後綴。 | 這個 commit 的收集證明（4 組改名）PROOF OK；`test_runtime_session.py` 與 `test_pipeline_filters.py` 的部分通過純刪除 token 檢查；三個檔案單獨跑都通過；完整測試 3243 passed |
| M1（清單） | `4a864e5` | 把四組 `舊 id -> 新 id` 加進 spec 的 `-renames.txt`，讓端到端證明預期這些改名。 | 端到端收集證明（基準 3727、移除 486、改名 11、新增 2）PROOF OK，69 組改號配對都在 spec §5.2 列出的函式；收集 3243 |
| M2 | `69c20a3` | 改寫 `test_no_add_on_code_names_the_request_token` 的註解，不再說它是唯一的檢查，並註明 `test_vocalizer_voice_declares_waitfactor_and_variant` 也釘住 VE、Cerence 的 Voice 能力宣告。 | 收集不變（PROOF OK）；檔案單獨跑 44 passed |

修完後在 `69c20a3` 重跑：完整測試 **3243 passed、0 skipped**；`prek run --all-files` 全部 Passed；`git diff --check master` 乾淨；`git diff --stat master -- addon` 沒有輸出；受保護路徑兩個指令都沒有輸出。
