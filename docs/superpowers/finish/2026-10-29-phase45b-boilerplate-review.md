# Review：Phase 45′ wrapper 樣板收斂

日期：2026-10-29。分支：`phase45b-boilerplate`（worktree `/workspace/WorldVoice-phase45b`，`master` `8ef4e12` 之上 21 個 commit：`4236e8c..188fa87`）。
依據：

- 規格 `docs/superpowers/specs/2026-10-29-phase45b-boilerplate-design.md`（含 §8 實作備註）
- 計畫 `docs/superpowers/plans/2026-10-29-phase45b-boilerplate.md`
- 進度帳本 `.superpowers/sdd/2026-10-29-phase45b-boilerplate/progress.md`（未追蹤）
- 一致性稽核 `cons.md` B1、B2、B3、B6、B7、B11、B15、B16（主 checkout，唯讀）

審閱：Fable 5.1，DEVELOPMENT_WORKFLOW §3.3，唯讀；只跑測試、自己寫的搬移／改名比對腳本，以及 scratch 複本上的突變（沒有動 worktree，沒有用 `git stash`）。行號以分支 HEAD 為準：`VE:` ＝ `addon/synthDrivers/WorldVoice/driver/VE/__init__.py`（Cerence 與 VE 的 diff 逐 token 相同，只差 ruff 的換行，見驗證表），`OneCore:` ＝ `driver/OneCore/__init__.py`，`host:` ＝ `runtime/segmentHost.py`，`control:` ＝ `runtime/engineControl.py`，`adapter:` ＝ `bridge/engineAdapter.py`。

## 結論

**Ready to merge：是。** Critical 0、Important 0、Minor 3。

- **搬移與改名的證明（§3.2）我自己重跑了一次**，用自己寫的順序敏感 token diff（`rev45b/tokdiff.py`，比對 `(token type, text)` 序列並保留 INDENT／DEDENT，略過註解與空行），對 15 個 refactor commit 的每個檔案逐一和它的父 commit 比對。每個 commit 的差異 hunk 都剛好是帳本和 spec §6.2 列的那些，沒有夾帶其他修改（明細在驗證表）。被搬走的三組程式碼（六份 `speak_segment`、五份清理迴圈、三份 `_nvdaLabel`）的 token 都和新家逐 token 相同，差別只有帳本已列的 `-> None`（eSpeak／RHVoice 兩份沒有）、`log`→`logger`、字串字面值→`message`。
- **MRO：** 在六個真正載入的 wrapper 上印出 MRO（scratch 探針）：`SegmentHostSpeaker` 都是最後一個直接 base，`speak_segment` 都解析到 mixin，`get_segment_drain_support` 都解析到 wrapper 自己，MRO 裡沒有別的類別定義 `speak_segment`、`get_segment_drain_support` 或類別層級的 `_segmentHost`。`ref/nvda/source/synthDrivers/` 與六個 vendored 內層 `driver/*/driver/` 都沒有這三個名字，也沒有 `nvdaLabel`／`release_newest_first`。SAPI5 在 NVDA < 2025.3 換成 NVDA 自己的 `sapi5.SynthDriver` 當整個 core（`SAPI5:696-720`），那條路徑沒有 mixin 也沒有 `speak_segment`，adapter 照舊只呼叫 `speak()`（`adapter:34-35`、`:85-87`），這個 phase 沒有碰到它。`super()` 鏈：mixin 不覆寫任何 NVDA 方法，`speak`／`pause`／`cancel`／`terminate` 的解析結果和 `master` 相同（探針輸出）。
- **B6：** `master` 上 `_terminated` 與 `_terminationRequested` 的所有寫入只有建構子的兩個 `False`（`VE:390`、`:395`）和 `terminate` 同一個鎖區塊裡的兩個 `True`（`VE:882-884`），兩者之間沒有讀取，所以四處讀取改名後看到的值相同。VE 自有的檢查都保留在 host 之前（`VE:331`、`:458`、`:773`、`:784`），Review Focus 3 的競態視窗（flag 已設、`host.terminate()` 還在等 admission）行為不變。
- **B7 OneCore：** 我沒有只信帳本的 coverage 紀錄，而是在 scratch 複本的 HEAD wrapper 把三個被刪的 False 分支改成 `raise AssertionError`（旗標改由 `submit` 設），跑完整套 3614 個測試：三個陷阱一次都沒被踩到（唯三的失敗都是我的探針檔和新私有名字觸發的 hygiene／命名守門，見驗證表）。靜態推理也成立：`_processQueue` 只被 wrapper 的 `submit`（`OneCore:179`）、NVDA 的 `_queueSpeech`（被 `OneCore:297-303` 覆寫、不再呼叫它）、NVDA 的 `_callback`／`_handleSpeechFailure`（`oneCore.py:475`、`:531`）呼叫；而 `_callback` 只會在 `ocSpeech_speak` 之後到來，`ocSpeech_speak` 只在 `submit` 之後由 worker（`OneCore:353-`）或 NVDA 的 `_processQueue`（已證不可達）呼叫。設定 setter 只 append tuple、不呼叫 `_processQueue`（`oneCore.py:365-398`），所以「開啟後先改 rate 再第一次說話」的順序不變（`test_settings_tuples_do_not_take_native_job_identity` 仍釘住）。
- **B7 VE／Cerence `_legacyUsed`（本 phase 唯一的行為改變）：** 正式路徑不可達——整個 add-on 只有 `adapter:30`、`:35` 會呼叫 core 的 `speak`／`speak_segment`（`grep`，排除內層驅動），哪一個由 `_completion` 決定，`configureCompletion` 在說過話或已設定不同 contract 後拒絕（`adapter:78-85`），每次 `open` 都 `createCore()` 新建、`close` 都 `destroyCore` 銷毀（`adapter:63-68`、`:97-106`；`driver/__init__.py:90-95`），`_spoken` 隨 `close` 重設但 core 也換了。拿掉守門是否安全：VE 的一般語音自 `717c302`／`bff05d4` 起也走 `host.enqueue(..., native=_VERequest)` → 同一個 `_enqueue` 在 BgThread 上用 `_Begin`／inner speak／`_Retire` 括住（`VE:467-490`），和逐段 record 走同一條佇列、同一個 `_currentRecord`，callback 准入又以 `_nativeCall` 為準（`VE:603-622`）；舊理由「legacy callback lifetimes are unproven」在 `9d96ace` 拿掉 token、三個關卡齊全之後已經不成立。新測試 `test_segment_after_ordinary_speech_drains` 在 VE／Cerence 上實際跑過「一般語音 → 逐段」並得到 `SEGMENT_DRAINED`。我判斷安全。
- **B16：** `_confirmNativeQuiescence` 的 body 是 `return None`，`blocked` 恆為 None，刪掉的 try／except、`if blocked is None:` 與 stop 分支都不可達；留下的 `self._nativeCall = None` 只是少一層縮排（token diff 顯示其餘 token 原地不動）。`_REASONS` 少掉的那條只服務這兩個 handler，不刪的話 `test_every_reason_entry_still_checks_a_handler` 會失敗。39 個 `prove_fake_quiescence` 是把回傳 None 的方法換成回傳 None 的 lambda，刪掉不減少任何覆蓋。
- **B11、B15 不做**的理由（spec §4）我同意：RHVoice 第二次 `terminate` 會重試刪引擎、SAPI5 會重跑父層 `terminate`，改用 `host.terminate()` 回傳值會拿掉這些重試。B15 的表格六個引擎都釘住了；eSpeak 的 `AttributeError` 來自 `ref/nvda/source/synthDrivers/_espeak.py` 真實模組（harness `espeak_drain_harness.py:303` 由 ref 載入）的 `player.pause` 在 `terminate` 把 `player` 設成 None 之後（`_espeak.py:269-271`、`:403-404`），不是 fake 的行為。
- **其他路徑沒有行為改變：** 除 B7 外每個 commit 的 token diff 都只有刪除、import 變動或等價替換；正確路徑與失敗路徑（清理迴圈的順序、`Exception` 捕捉、`exc_info=True`、原例外由 wrapper 的 `raise` 重拋）都和 `master` 相同。
- **限制（§8）：** 受保護路徑與 Neural 兩個指令都沒有輸出；沒有驅動 import 另一個驅動（新共用碼只在 `runtime/`、`bridge/`）；`tests/test_vocalizer_drift.py` 的 `ALLOWED` 沒有改；21 個 commit 都沒有 `Co-Authored-By`；`prek run --all-files` 全部 Passed。

## Critical

無。

## Important

無。

## Minor

### M1. VE／Cerence 自有的 terminate 檢查（`admission_error` 與 `speak`）沒有測試釘住：拿掉它們，全套 3614 個測試照過（`VE:331-332`、`VE:458-459`；`tests/test_engine_segment_contract.py:118`、`:177`）

- **情境：** spec §3.4 保留這兩個檢查的理由是競態視窗——`terminate()` 先設 flag（`VE:842`）再呼叫 `host.terminate()`，後者要等 host admission（`host:331`），而一個正在跑的 `enqueue` 在 inner `speak()` 轉換文字時握著它（`host:275-287`、`VE:478`）。在那個視窗裡 VE 的檢查讓 `speak`／`speak_segment` 立刻被拒，host 的檢查則要等 admission 釋放後才拒（訊息相同：「VE driver has terminated」）。
- **突變（scratch 複本，完整套件）：** M5 把 `admission_error` 的 `if driver._terminationRequested:` 改成 `if False:`；M7 把 `speak` 的同一句改成 `if False:`。兩者都只讓 `test_vocalizer_drift.py`（因為我只改了 VE 一份）和我探針檔觸發的兩個 hygiene 守門失敗，其餘 3611 個通過。原因：`test_segment_after_terminate_fails_once_without_native_call` 和 `test_ordinary_speak_after_terminate_raises` 都在 `terminate()` 完全回來之後才呼叫，那時 host 已經 terminated，先攔下的是 host（`host:224`、`:275-277`），VE 的檢查成了第二道。`pause()` 的那一道有釘住（M6：拿掉 raise → `test_pause_after_terminate_keeps_each_engine_behaviour[VE]` 失敗）。
- **這不是本 phase 引入的：** `master` 上同樣沒有測試覆蓋這個視窗；本 phase 只改了名字，而且 spec 明寫保留的理由。但既然 spec 以這個視窗為由保留程式碼，下一個想把它們換成 `host.terminated` 的人（cons.md B6 原本的建議）不會被任何測試擋下。
- **修法（擇一）：** 加一個 VE／Cerence 測試：在 `tests/test_vocalizer_segment_drain.py` 用 `monkeypatch` 讓 `env.native.processText2Speech`（或 inner `speak`）在進入後等一個 Event，於另一執行緒呼叫 `env.core.terminate()`，等到 `_terminationRequested` 為 True 而 `segment_host(env.core).terminated` 仍為 False 時，斷言 `env.core.speak(("x",))` 在短時間內（例如 `WAIT_TIMEOUT` 內、不等 Event 釋放）就 raise，而 `speak_segment` 的 `on_event` 在 Event 釋放前就收到 `SEGMENT_FAILED`；最後釋放 Event。或者在 spec §3.4 註明「這個視窗沒有測試，依賴程式碼閱讀」。不改程式。

### M2. `release_newest_first` 的 `except Exception`（讓 `KeyboardInterrupt` 等 `BaseException` 逃逸）沒有釘住：改成 `except BaseException` 後 42 個相關測試照過（`control:182-186`；`tests/test_engine_control.py:212-233`）

- spec §3.2 明說「same catch (`Exception`, so `KeyboardInterrupt` in a release still escapes)」，並以此為「行為不變」的一部分。突變 M3 存活，表示這句承諾只靠程式碼閱讀。
- **修法：** 在 `test_release_newest_first_runs_every_release_in_reverse_and_logs_failures` 後加一段：一個 release 丟 `KeyboardInterrupt`，`pytest.raises(KeyboardInterrupt)`，而且較舊的 release 沒有被呼叫、logger 沒有記錄。兩三行。不改程式。

### M3. 層次備註：`runtime/segmentHost.py` 的 mixin 讀 wrapper 的 camelCase 欄位 `self._segmentHost`（`host:151-166`），`release_newest_first` 的 docstring 引用 bridge 的 `VoiceClassAdapter.open`（`control:177-180`）

- `runtime/` 是 NVDA-free、snake_case 的層（`tests/test_naming_layers.py` 規則 3 只管「儲存」的識別字，所以讀取沒有被守門擋下）。mixin 因此知道 wrapper 用哪個名字存 host；docstring 已經把這個約定寫清楚，六個 wrapper 也確實都在建構子第一行設它。替代方案（mixin 定義 `segment_host` property 由 wrapper 實作）要改六個 wrapper 的幾十處引用，不值得在這個「純刪減」phase 做。
- **修法：** 不改程式。若日後做 P48（runtime 拆檔）或 P45 的 `speak()` 半邊，可以順手把 docstring 裡的 `VoiceClassAdapter.open` 改成「the bridge's adapter」，讓 runtime 的文字也不指名 bridge 類別。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 完整測試（序列、記憶體看門狗 MemAvailable < 3 GB 砍 pytest） | `rev45b/runtests.sh … /workspace/WorldVoice-phase45b tests` | **3614 passed、0 skipped**（107 s），看門狗未觸發；基準 3597 + 17 個新測試 |
| hook | `prek run --all-files` | 8 個 hook 全部 Passed |
| 空白 | `git diff --check master` | 無輸出 |
| 受保護路徑 | `git diff --stat master -- 'addon/…/driver/*/driver/*' …/driver/sonic/ …/script_data.py …/unspaced_common_data.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 兩者都無輸出 |
| 殘留名字 | `grep -rn "_segmentMode\|_legacyUsed\|_confirmNativeQuiescence\|_nvdaLabel\|prove_fake_quiescence\|\b_terminated\b" addon tests` | 只剩別的類別自己的 `_terminated`（`__init__.py`、`_segmentLifecycle.py`、`segmentHost.py`、`voices/manager.py` 與其測試）和 `test_nvda_ready.py` 守門裡的字串 |
| commit 訊息 | `git log master..HEAD --format='%B' \| grep -i "co-authored\|generated with"` | 無輸出；21 個 commit 都是 `<type>: <summary>` 英文 |
| 每個 commit 只碰該 task 的檔案 | `git log master..HEAD --name-only` | 五個 B1 搬移 commit 各只有該 wrapper（VE＋Cerence 同一個）；B2 convergence 只有六個 wrapper；B3 搬移只有新模組＋三個 wrapper；B6 只有 VE＋Cerence；測試另外 commit |
| **B1 搬移比對**（`ab9d6b5` eSpeak、`08d43b4` RHVoice、`cac6170` SAPI5、`ebd4d84` OneCore、`d216228` VE＋Cerence） | `python3 rev45b/tokdiff.py . <c>^ <c> driver/<E>/__init__.py --sub SegmentDrainCore=SegmentHostSpeaker` | 每個檔案剛好 4 個 hunk：刪 `runtime.models` import、刪 `runtime.session` import、`SegmentHost` 在 import 行內因排序移位、刪整個 `speak_segment`（token 與 `host:158-166` 相同；eSpeak／RHVoice 少 `-> None`）。其他 token 原地不動 |
| **B2 比對**（`ee45d09`） | 同上，不帶 `--sub` | 六個 wrapper 各 6 個 hunk（VE 4 個，因為一行寫完）：`+release_newest_first` import、`for release in reversed` → `release_newest_first`、`) : try: release() except Exception:` → `, logger =`、`. error (` → `, message =`、刪 `exc_info = True`、刪兩個 DEDENT。`releases`、`log`、字串字面值三個 token 原地保留；helper body（`control:182-186`）就是被刪的迴圈 |
| **B3 搬移比對**（`d8844b9`） | 同上，`--sub _nvdaLabel=nvdaLabel` | 三個 wrapper 各 2 個 hunk：`+from ...bridge.nvdaVersion import nvdaLabel`、刪 `def nvdaLabel(): import versionInfo; return f"NVDA {versionInfo.version}"`，與 `bridge/nvdaVersion.py` 逐 token 相同 |
| **B6 改名比對**（`295fd88`） | `--sub _terminated=_terminationRequested` | VE、Cerence 各 2 個 hunk：刪 `self._terminationRequested = False`（舊 390／390）與 `= True`（舊 868／879）——即改名後重複的兩個賦值。`master` 上兩個旗標的寫入點核對如「結論」所述 |
| **B7 OneCore**（`efec925`） | 不帶 `--sub`；`barriers.py` 另比對 | OneCore 5 個 hunk，剛好是 `admission_error` 分支、`submit` 賦值、建構子初始化、`_processQueue` 與 `_callback` 的 `super()` 分支；`barriers.py` 程式 token 0 差異（只有註解） |
| **B7 VE／Cerence**（`d6ea62f`） | 同上 | 各 3 個 hunk：`admission_error` 分支、建構子 `= False`、`speak` 的 `= True` |
| **B16**（`a3f7f80`） | 同上 | 各 5 個 hunk：`_confirmNativeQuiescence` 定義、`blocked = None`、try／except 區塊、`if blocked is None:`＋INDENT、`DEDENT DEDENT if blocked is not None: … stop …`；`self._nativeCall = None` 的 token 原地保留 |
| **註解 commit**（`9448ccc`） | 不含註解比對四個 wrapper＋`tests/test_onecore_segment_drain.py`；再以 `--keep-comments` 看 | 程式 token 0 差異；含註解只差 spec §3.8 表列的那幾段 |
| Cerence 與 VE 的改動一致 | 把兩個 wrapper 的 `git diff master..HEAD` 把引擎名正規化後互比 | 只差 ruff 的換行（Cerence 的字串較長）；`test_vocalizer_drift.py` `ALLOWED` 未改且通過 |
| MRO 探針（scratch） | `rev45b/copy/tests/test_zz_review_mro_probe.py`，用 `test_engine_segment_contract` 的 `engine` fixture 載入六個真 wrapper | 六個都：`__bases__[-1] is SegmentHostSpeaker`；`speak_segment` → mixin；`get_segment_drain_support` → wrapper；`speak`／`cancel`／`terminate` → wrapper；`pause` → wrapper（VE、Cerence、OneCore）或父層（RHVoice 內層、NVDA sapi5、NVDA espeak，與 `master` 相同）；MRO 內無其他 `speak_segment`／`_segmentHost` 擁有者 |
| 父層與內層沒有這些名字 | `grep -rn "speak_segment\|_segmentHost\|get_segment_drain_support\|nvdaLabel\|release_newest_first" ref/nvda/source/synthDrivers/ driver/*/driver/` | 無輸出 |
| 驅動獨立安裝 | `grep` 六個 wrapper 的 import | 只 import `...runtime.*`、`...bridge.nvdaVersion`、`synthDrivers.WorldVoice.driver`（公開 plugin 模組）、`synthDrivers.WorldVoice.text.*`；沒有驅動 import 另一個驅動 |
| 正式路徑的呼叫者 | `grep -rn "\.speak_segment(\|_core\.speak(\|core\.speak(" addon` | 只有 `adapter:30`、`:35` 和 mixin 自己 |
| 突變 M1a：RHVoice wrapper 自己再定義 `speak_segment` | scratch 複本 | `test_every_wrapper_core_declares_the_segment_drain_entries` 失敗（殺） |
| 突變 M1b：vendored RHVoice 內層 `SynthDriver` 多一個 `speak_segment`（模擬父層日後新增） | scratch 複本 | `test_every_core_speaks_segments_through_the_shared_mixin[RHVoice]` 失敗（殺）；Review Focus 1 成立 |
| 突變 M2：`release_newest_first` 正序 | scratch 複本，不帶 `-x` | helper 單元測試失敗；`test_wrapper_init_cleanup.py`＋`test_vocalizer_init_cleanup.py` 15 failed／16 passed（順序由 wrapper 層也釘住）；Review Focus 2 成立 |
| 突變 M3：helper `except BaseException` | scratch 複本 | 42 passed（**存活**，見 Minor M2） |
| 突變 M3b：helper 不 log | scratch 複本 | helper 單元測試失敗（殺） |
| 突變 M4：`nvdaLabel` 少一個空白 | scratch 複本 | `test_nvda_ready.py::test_ready_skips_with_one_warning_when_a_module_name_is_missing[Espeak]` 失敗（殺；`-x` 停在第一個） |
| 突變 M5／M7：VE `admission_error`／`speak` 忽略 termination | scratch 複本，**完整套件** | 各 3 failed／3611 passed，失敗的只有 drift 守門（我只改 VE）與探針檔觸發的兩個 hygiene 守門（**存活**，見 Minor M1） |
| 突變 M6：VE `pause()` terminate 後靜默 | scratch 複本 | `test_pause_after_terminate_keeps_each_engine_behaviour[VE]` 失敗（殺；Review Focus 3 的 pause 半邊成立） |
| 突變 M8：`_runNative` 不清 `_nativeCall` | scratch 複本 | 172 passed（存活，與帳本一致）。我核對三個讀者：`_callbackAdmission` 看 `call.admitting`（`_closeAdmission` 已設 False）；`cancel`／`pause` 失敗路徑只把 `admitting` 設 False（冪等）。等價突變，清除是防禦性的，不需修 |
| **突變 M9：OneCore 三個被刪分支改成 `raise AssertionError` 陷阱** | scratch 複本，**完整套件** | 3 failed／3611 passed；失敗的是 `test_ruff_reports_nothing`、`test_no_test_module_imports_another`（我的探針檔）與 `test_onecore_parent_privates_are_listed_and_exist`（我的新私有名字），**沒有任何 AssertionError 陷阱被踩到**：三個分支在所有測試路徑都不可達，與帳本的 coverage 紀錄一致 |
| 帳本的 4 個 `Ruling:` | 逐一評估 | B3 搬移與守門測試分開 commit（合理，讓搬移 commit 乾淨）；`tests/test_onecore_segment_drain.py:338` 的「As on master」一併改（合理，註解）；`_REASONS` 表註解改指剩下的合併條目（合理）；`_terminationRequested` 計數 3→7 更正為 4→8（我數 `master`：init、`_retirePlayerOperation`、`terminate` ×2 ＝ 4，更正正確） |
| plan Review Focus 1–5 | 對應測試與突變 | 1：M1a／M1b；2：M2／M3b；3：M6（pause）殺、M5／M7（speak／admission）存活→Minor M1；4：`test_settings_tuples_do_not_take_native_job_identity`、`test_ordinary_speech_and_settings_keep_call_order` 存在且通過，M9 補證不可達；5：M8 等價 |
| 計算 17 個新測試 | 對照 spec §8 | 2（mixin）+ 1 + 6（守門）+ 1（helper）+ 1（label）+ 6（pause 表）＝ 17；`test_segment_after_ordinary_speech_follows_the_engine_mode_rule` 改名為 `test_segment_after_ordinary_speech_drains`，數量不變 |

## 使用者還沒確認的使用者可見預設

NVDA 使用者看得到的行為沒有改變（沒有設定、字串、log 文字、關卡或執行緒的變動）。以下是 spec §7 列為「協調者決定、使用者可在 merge 前推翻」的項目，以及本 review 留下的選擇：

1. **VE／Cerence 直接呼叫時，一般語音之後的逐段語音現在會播放而不是被拒**（spec §3.5；`test_segment_after_ordinary_speech_drains`）。正式路徑到不了：adapter 每個 core 只用一種 contract。建議維持。
2. **`nvdaLabel` 放在 `bridge/nvdaVersion.py`**，而不是稽核也提過的公開 plugin 模組 `driver/__init__.py`，所以 plugin API 沒有變大（spec §7）。建議維持。
3. **B11（terminate 冪等）與 B15（terminate 後 `pause()`）維持每個引擎各自的行為**，B15 的表由 `test_pause_after_terminate_keeps_each_engine_behaviour` 釘住（VE／Cerence raise、eSpeak `AttributeError`、其餘靜默）。要統一需要使用者決定關閉後的行為（spec §4）。
4. `tests/test_vocalizer_segment_drain.py` 裡 39 個測試保留了現在沒用到的 `monkeypatch` 參數（spec §8；沒有 lint 規則會報）。
5. Minor M1／M2 是否補測試（不改程式）：建議 merge 前順手補，兩個都很小。

未在 Linux 上驗證：Windows／NVDA 實機、實際音訊裝置與引擎 SDK；spec §6.3 建議下一個測試版本做六個引擎的 smoke run（say all、取消、暫停／恢復）。沒有打包。

## 修正記錄

修正者：Opus 5.5（DEVELOPMENT_WORKFLOW §3.4）。只改測試與文件，沒有改產品程式；VE／Cerence 同步，`tests/test_vocalizer_drift.py` 的 `ALLOWED` 未改。突變都在 scratch 複本（`scratchpad/p45b/mut/`）上做，沒有動 worktree，沒有用 `git stash`。

| 項目 | commit | 修法 | 突變結果 |
| --- | --- | --- | --- |
| M1 VE／Cerence 自有的 terminate 檢查沒有測試 | `aef0387` | 新增 `tests/test_vocalizer_segment_drain.py::test_speech_is_rejected_while_terminate_waits_for_host_admission`（VE、Cerence）。測試執行緒握住 host admission（模擬 `enqueue` 在 inner `speak()` 轉換文字時握著它），另一執行緒呼叫 `terminate()`；等到 `_terminationRequested` 為 True、`terminate` 仍卡在 `host.terminate()`、`host.terminated` 仍為 False 時，斷言 `speak()` 立刻 raise「<engine> driver has terminated」，而 `speak_segment()` 收到 `SEGMENT_FAILED`（segment 31、同樣訊息）。admission 是 RLock，所以同一執行緒的重入呼叫不會卡住，測試是決定性的 | M5（兩份 `admission_error` 的檢查改 `if False:`）：2 failed（VE、Cerence，等不到事件）；M7（兩份 `speak` 的檢查改 `if False:`）：2 failed（沒有 raise）。兩個突變都被殺 |
| M2 `release_newest_first` 的 `except Exception` 沒有釘住 | `44cc168` | 新增 `tests/test_engine_control.py::test_release_newest_first_lets_a_base_exception_escape`：某一步丟 `KeyboardInterrupt` 時立刻逃逸，較舊的步驟不執行（呼叫順序 `["c", "b"]`），也不記錄 log——和各 wrapper 原本的迴圈相同 | M3（`except BaseException`）：`test_engine_control.py`＋兩個 init-cleanup 檔 1 failed／42 passed，新測試失敗（殺） |
| 預設 4：39 個測試留下沒用到的 `monkeypatch` | `ed14863` | 逐一以 AST 檢查：39 個原本呼叫 `prove_fake_quiescence` 的測試中，只有 `test_cancel_resets_pause_before_next_legacy_speech` 與 `test_resume_failure_faults_active_work_and_suppresses_drain` 真的不再用到 `monkeypatch`，拿掉這兩個參數；其餘 37 個仍用它 patch 其他東西（review 的「39 個」是呼叫者數，不是未使用數）。spec §8 的對應備註以刪除線更正 | 不適用（純測試整理）；`test_vocalizer_segment_drain.py` 219 passed |
| M3 runtime mixin 讀 camelCase `self._segmentHost`、helper docstring 指名 bridge 類別 | — | 依協調者指示不改，維持 review 所述的文件化說明 | — |

驗證（最後一個 commit 之後，§7）：完整測試 **3617 passed、0 skipped**（3614 + 3 個新測試：M1 的 VE、Cerence 兩個參數化案例，M2 一個）；`prek run --all-files` 全部 Passed；`git diff --check master` 無輸出；受保護路徑兩個指令都無輸出。Linux 測試只涵蓋受控的 native 與音訊邊界，Windows／NVDA 未驗證。

