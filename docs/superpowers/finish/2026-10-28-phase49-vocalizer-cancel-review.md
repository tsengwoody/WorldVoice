# Phase 49 Review：VE／Cerence 取消改以 record 有效性判斷，移除 `_SilenceGate`

日期：2026-10-28。分支：`phase49-vocalizer-cancel`（`ea0d197..35542c1`，6 個 commit：2 個 docs、1 個 fix、2 個 test、1 個 refactor；基準 `master` `ea0d197`，3367 passed／0 skipped）。
審閱者：Fable 5.1（唯讀；只新增本檔）。流程：一般流程（DEVELOPMENT_WORKFLOW.md §3.3）；4 個 task 少於 10，沒有批次 review，本次是第一次也是唯一一次 review，看整個分支。

依據：

- spec `docs/superpowers/specs/2026-10-28-phase49-vocalizer-cancel-design.md`（§3 gate 職責清單、§10 突變結果）。
- plan `docs/superpowers/plans/2026-10-28-phase49-vocalizer-cancel.md`（Review Focus 1–5）。
- 進度帳本 `.superpowers/sdd/2026-10-28-phase49-vocalizer-cancel/progress.md`（git 忽略；6 個 `Ruling:`）。
- 實作者的突變材料 `scratchpad/p49/mutants.py`、`mut_ve.txt`、`mut_cerence.txt`、`m7.txt`、`oldmut.txt`；審閱者另外寫了自己的 17 個突變 `scratchpad/p49review/mutants_review.py`。
- 程式碼：`addon/synthDrivers/WorldVoice/driver/VE/__init__.py`（本檔的行號都以 head 的 VE 檔為準；Cerence 同一段落在 +0 到 +10 行後，`tests/test_vocalizer_drift.py` 釘住兩檔只差 `ALLOWED` 四處）、內層 `driver/VE/driver/__init__.py`、`runtime/segmentHost.py`、`runtime/_segmentLifecycle.py`、參考用的 `driver/RHVoice/__init__.py`。
- NVDA 原始碼 `ref/nvda/source/nvwave.py:313-400`（`WavePlayer.feed`／`idle`／`stop` 的 ducking 與 leading-silence trimming 副作用）。

使用者已決定、本次只核對實作的事項：往 RHVoice 的做法統一（spec 目標 1）；內層驅動、`runtime/`、RHVoice 都不動；VE 與 Cerence 改法相同；fallback 路徑不變。**實作全部符合。**

## 結論

**Ready to merge：Yes。** Critical 0、Important 0、Minor 4。

- **gate 職責清單（spec §3）審閱者從 `ea0d197` 獨立重列，結論相同：guard 裝好時 gate 不承擔任何決定。** 內層對 `_isSilence` 的讀寫只有五處（內層 `:154,183,194,196` 的 `isSet()`、`:453-454` 的 `set`／排隊 `clear`、`:289-290` 的建構）：
  - `VECallback.__call__`：`_ContextualVECallback.__call__`（head `:213-230`）只在 `not driver._guardInstalled` 時呼叫 `super().__call__`，否則走 `_process`，`_process` 從頭到尾不讀 `_isSilence`。所以四個 `isSet()` 在 guard 路徑上是死碼；舊 gate 的 `_insideNativeCall`「native call 之外一律 stop」也只有這裡會讀——同樣是死碼，真正擋住 call 外 callback 的是 `_callbackAdmission` 的 `call.admitting`（`:611-630`，`test_callback_rejects_audio_outside_native_call` 釘住）。
  - 內層 `cancel`：包裝層的 `cancel`（`:671-706`）不呼叫 `super().cancel()`；內層 `terminate`（內層 `:336`）呼叫的 `self.cancel()` 是包裝層的，而 `_finishTermination` 在 `super().terminate()` 之前已把 `_playerClosing` 設成 True（`:884` → `:889`），包裝層 `cancel` 在 `:679-680` 直接返回。內層 `grep` 確認 `self.cancel()` 只有 `:336` 這一處。所以 `_isSilence.set()`、排隊的 `clear`、以及舊 gate 阻擋 `clear` 的「下一次 cancel 的旗標被上一次排隊的 clear 重設」競爭，在 guard 路徑上從來沒發生過。
  - `DoneSpeaking` → `self._player.idle()`（內層 `:236`）：`speak` 用 `self._player` 建 `DoneSpeaking`（內層 `:435`），guard 裝好後那是 `_WavePlayer`，`idle` 轉給 `_idlePlayer`（`:108-112`）；`pause`（內層 `:459`）與 `terminate` 的 `close()`（內層 `:346`）經 `__getattr__` 到真正的 player（`test_guard_keeps_original_pause_and_terminate`；審閱者突變 R6 證明有釘住）。
  - 包裝層自己對 gate 的八處讀寫（舊 `:558-559,568,581,621,627,640,737,815,817,697,380`）逐一核對 spec §3.2 的「covered by」：每一處都是同一行已有的 `record is not self._currentRecord`／`_recordValid(record)`／`token.is_cancelled()` 在做同一個判斷。只有 `_idlePlayer` 與 `_onIndexReached(index)` 在 `record is None` 時由旗標單獨決定，也就是 D1／D2 改掉的兩個案例。
- **四個不變量成立（審閱者逐一追 `segmentHost.py`）。**
  - F1 `host.cancel()`（`segmentHost.py:287-289` → `_invalidate` `:663-669`）把 `_pending` 裡每一筆 record 設成 `cancelled`，並對每個 accepted operation 叫 `lifecycle.cancel`。
  - F2 record 在它所有 native 工作期間都在 `_pending`：`enqueue` 進（`:264`）；離開只有 `abandon`（`:404-424`，之後不會成為 current）、`retire` 且已無效（`:501-502`）、`forget`（VE 在 `_retireRecord` 的 `host.retire` 之後才叫，`:521-523`，已在最後一個 `_NativeTask` 與 `DoneSpeaking` 之後）、segment 的 `_deliver`／`_forget_operation`（`:628-655`，在 drain 之後的發佈或丟棄時）。`reset()` 會清 `_pending`，但 VE／Cerence 沒有呼叫它。所以 drain 期間（lifecycle thread 在 `wait_playback_drained` `:564-589`，worker 在 `host.retire` 等 `handoff`）segment record 仍在 `_pending`，`_VEStrategy.drain` 的 `_recordValid` 會看到 cancel。
  - F3 `_currentRecord` 只在 `_beginRecord` 未 skip 的分支設（`:507`）、`_retireRecord` 末尾清（`:525-526`）；舊 `_token` 在同兩處設／清，且就是 `_recordValid` 讀的那個 token（segment 讀 `record.work.is_valid()`，ordinary 讀 `record.native.token`，`:487-496`）。
  - F4 `_doneOwner` 在 skip 與不 skip 兩種分支都設成該 record（`:503`），所以 `_onIndexReached(None)` 看的 token 就是舊 `_token` 或（skip 時）舊 `_token=None` 之外同一個 record 自己的 token——結果相同。
- **審閱者刻意找的競爭，記錄有效性都擋得住（都有測試或突變證明）：**
  - cancel 與 `_runNative` 進入 native call 同時：三種交錯——(a) `host.cancel()` 在第二次 `_recordValid` 檢查（`:576`）之後、SDK 呼叫之前：`_nativeCall` 已在鎖內設好（`:571-573`），cancel 把 `call.admitting` 設 False（`:688-690`），第一個 callback 就被 `_callbackAdmission` 拒絕（USERSTOP）、什麼都沒餵；(b) 整個 cancel 在第一次檢查（`:568`）與取鎖之間跑完：第二次檢查看到 `record.cancelled`，不呼叫 SDK（`test_cancel_before_native_call_starts_skips_it`，實作者 M7、審閱者 R3 證明）；(c) cancel 在取鎖等待期間：`_stopGate` 讓 `wait_for` 等到 stop 結束，再做第二次檢查。舊 gate 在這三種交錯裡沒有比記錄有效性多擋任何東西。
  - cancel 落在 `_Begin` 與第一個 `_NativeTask` 之間：record 已 current 且在 `_pending`，`host.cancel()` 標記它；`_dropQueuedSpeech` 把它的 `_NativeTask`／`DoneSpeaking`／`_Retire` 都留下（`:723-746`），`_NativeTask` 因無效直接返回，`DoneSpeaking` 不 idle、ordinary 仍發 DONE（`test_dropped_request_done_skips_idle_and_reports_done` 的「first」半段）。舊 gate 這裡還有一個反向弱點：cancel 的 `host.cancel()` 跑完、`_isSilence.set()` 還沒拿到鎖時，`_beginRecord` 的 `begin(token)` 會先清旗標——記錄有效性沒有這個洞（`test_cancel_while_request_begins_stays_stopped`，實作者 M8／M19、審閱者 R3 證明）。
  - `_closeAdmission` 之後遲到的 SDK callback：`_callbackAdmission` 看 `call.admitting`（`:615`），`_runNative` 結尾把 `_nativeCall` 清掉（`:598-599`，實作者 M22、審閱者 R17 證明）；這段本 phase 沒改。
  - ENDPROCESS 的 Sonic 尾巴：`_process` 在 flush 前後都查 `_recordValid`（`:271-277`），core cancel 時 admission 已關（USERSTOP），token cancel 時走 legacy 的 NUAN_OK 但不 flush 也不餵（`test_endprocess_after_cancel_feeds_no_sonic_tail[core|token]`，實作者 M14、M16 證明）。
  - pause／resume：`pause`（`:767-821`）只用 `_paused`／`_pauseRevision`／`_pauses`／`_stopGate`，沒碰過 gate；`_idlePlayer` 的暫停等待（`:647-651`）不變。
  - 語音中 terminate：`terminate` → `host.terminate()`（`_invalidate`）→ `cancel()` → `_finishTermination`，gate 不在任何一步；`tests/test_vocalizer_segment_drain.py` 的 terminate 測試全過。
  - legacy ordinary speech 帶 token：`_recordValid` 讀 `record.native.token`（`:490`，實作者 M19 證明）。
- **D1／D2 對 NVDA 不可見（審閱者連 `nvwave.py` 一起查）。** D1 唯一改變的案例是「token 在開始前就取消而中間沒有 core cancel」的 ordinary request：舊碼對真 player 多叫一次 `idle()`，新碼不叫。NVDA 的 `WavePlayer.idle()` 除了等播完還會 `_audioDucker.disable()` 和 `startTrimmingLeadingSilence()`（`nvwave.py:376-382`），但前一筆 record 結束時必經 ordinary 的 `DoneSpeaking` idle、segment 的 drain idle（`:336`）或 cancel／token 取消的 `stop()`（`nvwave.py:384-394`，同樣 disable ducker、重啟 trimming）之一，而被 skip 的 record 沒餵任何音訊，所以多那一次 idle 沒有任何效果；skip 的 DONE 本來就被 token 擋掉（`:760-761`），index／DONE 順序不變。D2 的「沒有 running request 的 index」從 SDK 走不到（`_process` 只在 admitted 的 current record 下呼叫 `_onIndexReached`，`:267`），只有直接呼叫才會；sayAll 靠 `synthIndexReached`／`synthDoneSpeaking` 的順序推進，兩者在未取消的 request 上一字不差（`test_cancelled_request_drops_index_and_done_notifications` 的 live 半段）。
- **fallback 不變。** `_installGuard` 的五欄位檢查、log 文字、提前 return 都和 master 同形（`:411-424`）；每個覆寫方法第一行仍是 `if not self._guardInstalled: return super()…`；`test_missing_private_field_falls_back_without_partial_install` 五個參數 + `test_missing_callback_…` + `test_fallback_delegates_each_original_method` 四個方法全過，實作者 M24（跳過可用性檢查）抓到全部五個參數。
- **VE 與 Cerence 相同；內層與受保護路徑沒動。** 兩檔對 master 的 diff 在把引擎名換成佔位字後逐字相同（審閱者 `diff` 比對）；`git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' …` 無輸出；`git ls-files …/Neural` 無輸出；`runtime/`、`RHVoice/` 無 diff；兩個驅動都只 import 自己的 package 與 core。
- **測試真的抓得到。** 審閱者 17 個突變（下表）14 個被抓到、3 個存活：R4 是測試缺口（見 M4，程式本身正確），R8、R16 是本 phase 沒改過、而且前一行已做同一判斷的冗餘防線；把 master 的兩個包裝層配上 head 的測試，失敗的正好是 D0／D1／D2 的新測試與命名守門，其餘（含 Task 2 的七個「前後都綠」測試）全過，證明新測試只區分這個 phase 改的決定。
- 完整測試 3379 passed、0 skipped（基準 3367 + 26 新 − 14 刪；和帳本一致）；`prek run --all-files` 8 個 hook 全部 Passed；`git diff --check master` 乾淨；6 個 commit 沒有 `Co-Authored-By`。兩個包裝層各 −78／+24 行（VE 1012 → 958）。沒有 readme、changelog、可翻譯字串或儲存鍵的變動（符合 spec §5）。

## Critical

無。

## Important

無。

## Minor

### M1. `_WavePlayer` 與 RHVoice 的 `_WavePlayer` 同名但職責不同

- 位置：`addon/synthDrivers/WorldVoice/driver/VE/__init__.py:96-115`；`driver/RHVoice/__init__.py:169-199`（`class _WavePlayer(LeasedPlayer)`，負責 feed 的 per-record admission 與 index callback 綁定）；spec §2 目標 2、§6。
- 內容：兩者都是「內層驅動眼中的 `nvwave.WavePlayer`」這個意義上的替身，所以名字在各自 package 內都講得通，而且驅動要能單獨安裝、彼此不 import，不會撞名。但讀過 RHVoice 版的人看到 VE 版會預期它也管 feed／admission；VE 版其實只轉 `idle`，feed 由 `_feedCallback` 直接餵 `_realPlayer`。docstring（`:97-102`）已經把差異寫出來，審閱者判斷是**可接受但略有誤導**。
- 失敗情境：無（純可讀性）。
- 建議：維持名字，在 docstring 第二段加一句「Unlike RHVoice's `_WavePlayer`, not a `LeasedPlayer`: feed never comes through here」；或改名 `_IdleRouter`／`_DonePlayer`。列為未確認的預設（下方第 4 點）。

### M2. `_idlePlayer` 留下一個已經不可能為 False 的 `if record is not None:`

- 位置：`addon/synthDrivers/WorldVoice/driver/VE/__init__.py:643-651`（Cerence 同段）。
- 內容：`:643` 已在 `record is None` 時 return，`:647` 的 `if record is not None:` 永遠為真。master 時它有意義（舊碼允許 `record is None` 時 idle）。
- 失敗情境：無；只是讀者會以為還有 `record is None` 而 idle 的路徑。
- 建議：拿掉那層 `if`，把 `with self._speechStateLock:` 往外縮一層；兩檔各 −1 行。

### M3. 「guard 路徑永遠不碰內層 `_isSilence`」的測試沒走 pause／terminate

- 位置：`tests/test_worldvoice_cancel_wrappers.py:734-749`（`test_guarded_speech_never_touches_inner_stop_flag`）；`driver/VE/__init__.py:884-889`（`_playerClosing = True` 再 `super().terminate()`）。
- 內容：內層唯一會 `set()` 旗標的路徑是內層 `terminate` → `self.cancel()`；它靠包裝層 `cancel` 在 `_playerClosing` 時提前返回（`:679-680`）才不會跑到。這條路徑現在由 `test_guard_keeps_original_pause_and_terminate` 間接覆蓋（它沒看旗標）；如果將來有人把 `_playerClosing` 的設定移到 `super().terminate()` 之後，`RecordingEvent` 測試不會發現。
- 失敗情境：將來的 terminate 重排讓內層 `cancel` 真的跑起來——它會清空 `_bgQueue`、`join` 隊列，和包裝層的 BgThread 收尾互相等待。
- 建議：在同一個測試末尾加 `core.pause(True); core.pause(False); core.terminate()`（照 `test_guard_keeps_original_pause_and_terminate` 的 monkeypatch 方式），再斷言 `flag.calls == []`。約 8 行。

### M4. D1／D2 的測試只用全新的 core，沒釘住「上一筆 retire 後 `_currentRecord` 已清掉」（突變 R4 存活）

- 位置：`tests/test_worldvoice_cancel_wrappers.py:494-518`（`test_done_of_never_spoken_request_skips_idle`、`test_index_without_running_request_is_dropped`）；`driver/VE/__init__.py:524-526`（`_retireRecord` 清 `_currentRecord`，spec F3 依賴它）。
- 內容：把 `:525` 的 `if self._currentRecord is record:` 改成 `if False:`（retire 後 `_currentRecord` 留著上一筆有效的 record）後，四個目標測試檔 322 個測試全過。兩個 D1／D2 測試都在沒說過話的 core 上做，`_currentRecord` 本來就是 None，所以看不出差別。審閱者在 scratch 複本上加「先說一筆正常的，再送 token 已取消的一筆」：突變版 `idles` 變成 2（D1 被繞過，回到舊的 idle 行為），head 是 1；再直接 `_onIndexReached(5)` 也會被發佈。
- 失敗情境：將來若 `_retireRecord` 的清理被重排或漏掉，D1／D2 會在第二筆 request 起靜默失效，而且 `pause` 失敗路徑（`:796-805`）會把錯誤記到已 retire 的舊 record 上。
- 建議：兩個測試各先 `speak_now(core, ["live"])`（斷言 `idles == 1`、`dones == [core]`）再做原本的步驟，斷言 `idles` 仍為 1、`indexes == []`、`dones` 不變。約 6 行；審閱者的版本在 `scratchpad/p49review/mastercopy/tests/test_review_r4.py`（head 上綠、R4 上紅）。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 完整測試（head `35542c1`，序列、記憶體看門狗） | 暫時 worktree `/workspace/wv-p49-review`（`ref` 以 symlink 接入）：`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests` | **3379 passed, 0 skipped**（151 s）；基準 3367 |
| prek | `prek run --all-files`（同一 worktree） | 8 個 hook 全部 Passed |
| 空白 | `git diff --check master` | 乾淨 |
| 受保護路徑 | `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' addon/synthDrivers/WorldVoice/driver/sonic/ …script_data.py …unspaced_common_data.py` | 無輸出 |
| Neural | `git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 無輸出 |
| `runtime/`、RHVoice 未動 | `git diff --stat master -- addon/synthDrivers/WorldVoice/runtime addon/synthDrivers/WorldVoice/driver/RHVoice` | 無輸出 |
| VE／Cerence 改法相同 | 兩檔對 master 的 diff 取 `+/-` 行、引擎名換成 `X` 後 `diff` | 完全相同 |
| 內層 `_isSilence`／`_player` 使用點 | `grep -n` 兩個內層檔 | 各 19 處，行號相同（`:104-105,154,177,181,183,194,196-197,232,236,288-290,346,435/419,453-455/437-439,459/443`） |
| 內層呼叫 `self.cancel()` 的位置 | `grep -n 'cancel()' driver/VE/driver/__init__.py` | 只有 `:336`（`terminate`） |
| commit 訊息 | `git log master..HEAD --format='%(trailers)'` | 沒有 `Co-Authored-By` |
| master 包裝層 + head 測試 | scratch 複本換入 `master:driver/VE/__init__.py`、`Cerence/__init__.py`，跑 cancel-wrappers、segment-drain、naming、native-strategy-guards、drift | 21 failed／269 passed；失敗的只有 `test_installs_player_stand_in_…`、`test_missing_private_field_…`（5×2，`module._WavePlayer` 不存在）、`test_assignment_failure_falls_back_unchanged`、`test_done_of_never_spoken_request_skips_idle`、`test_index_without_running_request_is_dropped`、`test_guarded_speech_never_touches_inner_stop_flag`（各 ×2）與 `test_naming_follows_layer`；Task 2 的七個測試與 `[inner-clear]` 在 master 上也綠 |
| R4 存活的追查 | scratch 複本套 R4，加測試「先說一筆正常的，再送 token 已取消的一筆，再直接 `_onIndexReached(5)`」 | R4 上 `idles == 2`（紅），head 包裝層上綠（見 M4） |
| 實作者突變檔時序 | `mut_ve.txt`（07:39）早於 `94a2e70` 加的測試，所以表上 M7 寫 SURVIVED；`m7.txt`（07:41）與 `mut_cerence.txt`（07:50）顯示加測試後 M7 被抓到 | 與 spec §10、帳本一致，只是 VE 表檔沒重跑 |

### 突變測試（審閱者自己的 17 個，scratch 複本，`PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider`，每個 300 s timeout，輸出寫檔）

目標檔：`tests/test_worldvoice_cancel_wrappers.py`、`test_vocalizer_segment_drain.py`、`test_runtime_legacy_adapter.py`、`test_runtime_drain_integration.py`（322 個測試，每輪約 20–50 s）。VE 跑全部 17 個；Cerence 抽查 R3、R5、R11、R12、R13（結果相同）。

| # | 突變（VE head 行號） | 結果 | 抓到它的測試（節錄） |
| --- | --- | --- | --- |
| R1 | `_installGuard` `:433` 把 `_realPlayer` 設成替身本身 | 抓到 | 20 個（drain／cancel 測試遞迴） |
| R2 | `_installGuard` 在 `try` 之前就設 `_guardInstalled = True`（製造部分安裝） | 抓到 | `test_assignment_failure_falls_back_unchanged` |
| R3 | `cancel` `:681` 拿掉 `host.cancel()`（F1） | 抓到 | 13 個，含 `test_cancel_before_native_call_starts_skips_it`、`test_callback_after_core_cancel_feeds_nothing` |
| R4 | `_retireRecord` `:525` 不清 `_currentRecord` | **存活** | 見 M4；審閱者加強版測試抓到 |
| R5 | `_onIndexReached(None)` `:753` 改看 `_currentRecord` 而非 `_doneOwner` | 抓到 | `test_done_of_never_spoken_request_skips_idle`、`test_failed_cancelled_pause_reconciliation_blocks_fresh_speech` |
| R6 | `_WavePlayer` `:114` 拿掉 `__getattr__`（pause／close 不再轉給真 player） | 抓到 | 18 個，含 `test_guard_keeps_original_pause_and_terminate` |
| R7 | `_idlePlayer` `:643` 只看 `record.cancelled`，忽略 token | 抓到 | 6 個，含 `test_cancel_during_real_callback_feed_stops_after_feed` |
| R8 | `_runNative` `:568` 拿掉 `record is not self._currentRecord` | **存活** | 冗餘防線：非 current 的 `_NativeTask` 只會來自 `_dropQueuedSpeech` 留下的 task，其 record 必已被 `host.cancel()` 標記；或 skip 的 record（無效、abandoned 或 control error 已把 `record.error` 設好）。本 phase 沒改這行；master 上同樣存活 |
| R9 | `_onIndexReached(index)` `:762` 只看 `record.cancelled`，忽略 token | 抓到 | `test_cancelled_request_drops_index_and_done_notifications`、`test_cancelled_token_before_core_cancel_reports_nothing` |
| R10 | `_idlePlayer` `:640` 拿掉 segment 的提前 return | 抓到 | 13 個 segment drain 測試 |
| R11 | **D1 還原**：加回 sticky 旗標（cancel 設、`_beginRecord` 清），`_idlePlayer` 改回 `flag or (record is not None and not valid)` | 抓到 | `test_done_of_never_spoken_request_skips_idle` |
| R12 | **D2 還原**：同樣的旗標，`_onIndexReached(index)` 改回舊條件 | 抓到 | `test_index_without_running_request_is_dropped` |
| R13 | `_installGuard` 另外把 callback 的 `_isSilence` 換成新 Event | 抓到 | `test_installs_player_stand_in_and_keeps_inner_stop_flag` |
| R14 | `_WavePlayer.idle` 先 idle 真 player 再轉給 `_idlePlayer` | 抓到 | 29 個 |
| R15 | 舊 gate 語意：`_idlePlayer` 只看 sticky 旗標，不看 record 有效性 | 抓到 | 7 個，含 `test_cancel_while_request_begins_stays_stopped` |
| R16 | `_process` `:236` 拿掉開頭的 `_recordValid` 再檢查 | **存活** | 冗餘：`_callbackAdmission` `:622` 在 yield 前剛做過同一檢查，中間沒有釋放任何鎖以外的狀態變化窗口被測試覆蓋；本 phase 沒改這行 |
| R17 | `_callbackAdmission` `:615` 忽略 `call.admitting` | 抓到 | `test_endprocess_after_cancel_feeds_no_sonic_tail` |

實作者的 24 個突變（spec §10）審閱者核對過 `mut_ve.txt`／`mut_cerence.txt`／`m7.txt`：存活的 M6（`_runNative` 第一次檢查）、M9（drain 的 reach 被 host 擋住）、M10／M15（本 phase 沒改的行）、M18（dead driver 不可達）理由都成立；M9、M10、M15 在 master 上同樣存活（`oldmut.txt`）。

### Review Focus 逐項

1. cancel 落在 `_beginRecord` 有效性檢查之後：`test_cancel_while_request_begins_stays_stopped` 在 `host.begin`（持包裝層鎖）暫停，token 與 core 同時取消；`called == []`、`fed == []`、`idles == 0`。審閱者 R3（拿掉 `host.cancel()`）與實作者 M8、M19 都由它抓到。
2. 排在取消者後面的 ordinary speech：`test_dropped_request_done_skips_idle_and_reports_done`——`dones == [core, core]`、`idles == 0`、第二筆沒到 native。審閱者 R11（把 D1 還原成 sticky 旗標）與 R15 都被它或 `test_done_of_never_spoken_request_skips_idle` 抓到。
3. core cancel 後的 ENDPROCESS 與 Sonic 尾巴：`test_endprocess_after_cancel_feeds_no_sonic_tail[core]` → `[OK, OK, USERSTOP]`、`flushed == []`、`fed == []`；`[token]` 最後一個是 NUAN_OK（legacy 承認）但同樣不 flush、不餵。帳本 Ruling 2 的差異是 master 行為，正確。
4. token 在輪到前取消：`test_done_of_never_spoken_request_skips_idle` → `called == []`、`idles == 0`、`dones == []`。
5. pause／terminate 經替身：`test_guard_keeps_original_pause_and_terminate` → `pauses == [True, False]`、`closes == 1`；審閱者 R6（拿掉 `__getattr__`）證明有釘住；`tests/test_vocalizer_segment_drain.py` 的 pause／terminate 測試在完整測試裡全過。

## Ruling 評估

| Ruling | 評估 |
| --- | --- |
| Task 1：把 `test_cancelled_request_drops_index_and_done_notifications` 的改寫提前到 Task 1 | 合理：它原本在 gate 上假造 token、沒有 running request，正是 D2 改掉的案例，留在 Task 1 才能先紅後綠。 |
| Task 2：ENDPROCESS 在 core cancel 後答 USERSTOP、token cancel 後答 NUAN_OK，參數化 | 合理且正確：core cancel 關掉 `call.admitting`，`_callbackAdmission` 連 `call` 都不給，走不到 legacy 的 NUAN_OK 分支（`:219-229`）；審閱者在 master 包裝層上確認同樣結果。 |
| Task 2：測試改名 `test_endprocess_after_cancel_feeds_no_sonic_tail` | 合理。 |
| Task 3：刪除 `test_restoration_failure_raises_instead_of_returning_partial_core` | 合理：D0 只剩 `self._player = _WavePlayer(real, self)` 一個指派（`:429`）。`_WavePlayer.__init__` 只存兩個屬性與 `weakref.ref(driver)`（driver 已被 `_RecordTask`、`_VEStrategy` 弱參考，可弱參考），建構失敗時沒有任何東西被改；指派失敗時也沒有。審閱者 R2（把 `_guardInstalled = True` 移到 try 之前，製造部分安裝）被 `test_assignment_failure_falls_back_unchanged` 抓到，證明「安裝失敗就完全回到原狀」有釘住。部分安裝狀態確實不可能。 |
| Task 3：移除 `INTERFACE_NAMES` 整個 VE／Cerence 項目 | 合理：各自只有 `_SilenceGate.is_set` 一個鍵；審閱者在 master 包裝層上跑 head 的 naming 守門會失敗，證明守門仍在檢查這兩個檔。 |

spec 的五個「*Decided by orchestrator with the recommended default*」（目標 1、D0、D1、D2、`_WavePlayer` 名）審閱者都同意；列在下一節供使用者覆寫。

## 使用者還沒確認的使用者可見預設

這個 phase 沒有 NVDA 使用者看得到的改變；以下是 spec §9 列的實作層預設，使用者可在 merge 前覆寫：

1. **D0**：guard 安裝只剩一個指派，失敗時不再有「restoration failed」的 log／例外。
2. **D1**：沒有 running request 時內層的 DONE idle 不再對真 player 叫 `idle()`（只影響 token 在開始前就取消的 ordinary request；見結論第 5 點，對 NVDA 不可見）。
3. **D2**：沒有 running request 時的 index 一律丟掉（SDK 走不到這個案例）。
4. **替身名 `_WavePlayer`**（M1）：與 RHVoice 同名但不是 `LeasedPlayer`。
5. **M2、M3** 的小修改要不要在 merge 前一起做。

## 未在 Linux 驗證的項目（Windows／NVDA 手動）

Linux 測試只驗證受控的 native 與音訊邊界；真正的 SDK callback、音訊裝置與 NVDA 沒有跑到。建議在打包後用 VE 與 Cerence 各做一次：

1. 長句朗讀中按 Ctrl 取消：立刻靜音、沒有殘餘音訊、沒有多餘的 DONE 讓 NVDA 誤以為說完（接著按方向鍵的下一句要正常開始）。
2. sayAll（NVDA+下）：游標跟著走（index 順序）、在中途取消後游標停在正確位置、再啟動 sayAll 正常。
3. Shift 暫停／恢復：暫停時無聲、恢復接續；暫停中按 Ctrl 取消後再說話不會卡住。
4. Rate boost 開啟（Sonic）：長句中取消沒有尾巴；ENDPROCESS 後的最後一塊在未取消時仍播出（句尾不被吃掉）。
5. 快速連按多個鍵（多筆短 request 互相取消）：沒有漏字也沒有重複、沒有「嗶」聲或雜音。
6. 說話中切換語音／variant、說話中關閉 NVDA 或換合成器（terminate）：不當機、不殘留音訊。
7. 中文＋英文混合（兩個引擎各一段）的 segment 流程：段落之間沒有多餘停頓或重疊。

## 修正記錄

修正者：Opus 5.5（DEVELOPMENT_WORKFLOW.md §3.4）。分支 `phase49-vocalizer-cancel`，review commit `968acdd` 之後。只有 Minor，依 §3.4 不做修正 review。突變都在 scratch 複本跑（`PYTHONDONTWRITEBYTECODE=1`、`-p no:cacheprovider`、先清 `__pycache__`、每輪 300 s timeout、輸出寫檔），腳本 `scratchpad/p49fix/mutate.py`、`run_mut.sh`，結果 `scratchpad/p49fix/final_*.txt`；VE 與 Cerence 同時套用突變。

| 項目 | commit | 修法 | 驗證 |
| --- | --- | --- | --- |
| M4 | `95fe8f0` | `test_done_of_never_spoken_request_skips_idle`、`test_index_without_running_request_is_dropped` 先說一筆正常的 request（新 helper `speak_live_request`：native 叫一次、`idles == 1`、`dones == [core]`），再送 token 已取消的一筆／直接 `_onIndexReached(5)`，斷言 `idles` 仍為 1、`dones` 不變、`indexes == []` | R4（`_retireRecord` 不清 `_currentRecord`）：目標四檔 322 個測試中 4 failed（兩個測試 ×VE／Cerence；`assert 2 == 1`、`assert [5] == []`）；head：322 passed |
| M3 | `f730f96` | `test_guarded_speech_never_touches_inner_stop_flag` 末尾再做 `pause(True)`／`pause(False)`（斷言 `pauses == [True, False]`）與 `terminate()`（native `close`／`terminate` monkeypatch，斷言 `closes == 1`），最後再斷言 `flag.calls == []` | 突變 T1（`cancel` 在 `_playerClosing` 提前返回前 `self._isSilence.set()`，即內層 `terminate` → 包裝層 `cancel` 這條路）→ `['set'] == []` 失敗；P1（`pause` 在 `super().pause` 前讀 `_isSilence.is_set()`）→ `['is_set', 'is_set'] == []` 失敗；兩者在修正前的測試上都存活（2 passed）；head 綠。見下方 Ruling |
| M2 | `ed54487` | 兩個包裝層的 `_idlePlayer` 拿掉永遠為真的 `if record is not None:`，pause 等待往外縮一層；行為不變 | 無可寫的失敗測試（純死碼）；cancel-wrappers、segment-drain、drift 246 passed |
| M1 | `d45a59e`（改名）、`bfe3b2a`（docstring）、`e630382`（spec） | 協調者決定改名：VE／Cerence 的替身 `_WavePlayer` → `_IdleRoutingPlayer`，docstring 改成一句：只把內層 DoneSpeaking 的 idle 轉給 `_idlePlayer`，其他轉給真 player，不是 RHVoice 那種 `LeasedPlayer`。改名獨立一個 commit，通過會檢查順序的 token 比對（`scratchpad/p49fix/rename_check.py`：只有 7 個 `_WavePlayer` NAME token 變了，VE 2、Cerence 2、測試 3）；RHVoice 的 `_WavePlayer` 與 `test_native_strategy_guards.py:149` 刻意保留。spec 裡描述替身的地方舊名加刪除線、寫新名並標 *Corrected by review M1*；plan 保留原樣當歷史 | naming、drift、native-strategy-guards、cancel-wrappers、segment-drain 290 passed |

第 4 點「使用者還沒確認的使用者可見預設」的替身名改為 `_IdleRoutingPlayer`（協調者決定，使用者可在 merge 前覆寫）；第 5 點 M2、M3 已在 merge 前修。

Ruling（也記在進度帳本）：

- M1：spec 視為這個設計的現行說明，用刪除線更新；plan 是執行紀錄，不改。
- M3：review 舉的「把 `_playerClosing` 移到 `super().terminate()` 之後」會讓包裝層 `cancel` 跑完整流程，但包裝層 `cancel` 從不呼叫內層 `cancel`，不會碰到旗標，所以不是這個測試要釘的東西；改用兩個真的碰旗標的突變（T1、P1）證明擴充後的測試抓得到。那個重排的風險仍由 `test_guard_keeps_original_pause_and_terminate` 與 segment-drain 的 terminate 測試覆蓋。

最後驗證（head `e630382`）：

- 完整測試（序列、記憶體看門狗、bytecode 關閉）：**3379 passed, 0 skipped**（和 review 基準相同：只改既有測試，沒有新增或刪除）。
- `prek run --all-files`：8 個 hook 全部 Passed。
- `git diff --check master`：乾淨。
- 受保護路徑（`driver/*/driver/*`、`sonic/`、兩個產生的 Unicode 資料檔）、`runtime/`、`RHVoice/`：對 master 無 diff；`git ls-files …/Neural` 無輸出。
- VE／Cerence 對 master 的 diff 在引擎名換成佔位字後逐字相同；`tests/test_vocalizer_drift.py` 的 `ALLOWED` 沒動。
- 6 個修正 commit 都沒有 `Co-Authored-By`。
