# Review：Phase 55 audit C 項（C1 RHVoice 逐段 DONE、C6 OneCore 建構失敗漏 token、C7 RHVoice cancel 同步等 worker）

日期：2026-10-30。分支：`phase55-c-items`（`b768c57..b0f0a99`，5 個 commit：`255da2e` spec、`3616516` plan、`ea58e10` C1、`d456a92` C6、`b0f0a99` C7 註解＋測試；基準 `master` `b768c57` 3632 passed／0 skipped，分支 3637 passed／0 skipped）。
審閱者：Fable 5.1（唯讀；只新增本檔）。流程：一般流程（DEVELOPMENT_WORKFLOW.md §3.3）。

依據：

- spec `docs/superpowers/specs/2026-10-29-phase55-c-items-design.md`；plan `docs/superpowers/plans/2026-10-29-phase55-c-items.md`（Review Focus 1–5 逐項檢查）；進度帳本 `.superpowers/sdd/2026-10-29-phase55-c-items/progress.md`（三個 `Ruling:`）；來源 `cons.md` §8 C1、§1 C6、§5 C7（唯讀）。
- 程式碼：`driver/RHVoice/__init__.py`（`_RHVoiceInner.segmentDone` `:93-103`、`_WavePlayer` `:183-229`、`_QueuedSpeech` `:232-280`、`_wrapPlayer` `:358-371`、`_nativeCallback` `:382-408`、`cancel` `:419-456`、`terminate` `:458-477`）；內層 `driver/RHVoice/driver/__init__.py`（`AudioPlayer` `:180-272`、`DoneCallback` `:336-353`、`SpeakText.__call__` `:395-410`、`cancel` `:605-612`；無 diff）；`driver/OneCore/__init__.py`（`_DetachableCallback` `:68-98`、`__init__` `:216-257`、`_releaseParentNative` `:259-273`、`terminate` `:633-653`）；`runtime/segmentHost.py`（`consumer` `:384-412`、`abandon` `:424-446`、`wait_settled` `:472-486`、`retire` `:488-561`、`_invalidate` `:690-697`、`LeasedPlayer._feed_admitted` `:716-734`、`stop` `:772-777`）；`runtime/scheduler.py`（`_stop_all` `:424-431`、`cancel` `:433-449`、`_acquire` `:549-566`）；`bridge/engineAdapter.py:191-194`；`bridge/nvdaEvents.py:232-235`；`runtime/engineControl.py:176-186`。
- NVDA（`ref/nvda/`，唯讀）：`source/synthDrivers/oneCore.py:241-281`（建構順序：`_callbackInst` `:268`、`_ocSpeechToken` `:269-270`、`self.voice = …` `:280`）、`:303-312`（`terminate`）；`source/driverHandler.py:43-49`（基底 `terminate` 只做 `saveSettings`）；`nvdaHelper/local/wasapi.cpp:320-323`（feed 進來時 `stopping` → `completeStop()` 後照常餵）、`:582-603`（`stop` 設 `stopping` 並喚醒 feed）、`:620-626`（`idle`）；`source/nvwave.py:313-366`（`feed`）。
- 測試：`tests/test_rhvoice_segment_drain.py`（`:294-307`、`:310-356`、`:358-388`、`:558-584`、`:816-865`）、`tests/test_wrapper_init_cleanup.py`（`:1-8`、`:290-374`）、`tests/onecore_drain_harness.py:335-342`、`tests/rhvoice_drain_harness.py`（`Player` `:15-80`、`Native._speak` `:152-186`）。
- 行號以 head `b0f0a99` 為準；路徑省略 `addon/synthDrivers/WorldVoice/`。

## 結論

**程式碼正確、符合 spec、可以 merge。** Critical 0、Important 0、Minor 4（都是註解／spec 用語與測試風格，不影響行為）。

- **C1 正確，一般語音逐位元組不變。** `_nativeCallback:395-400` 只在 `isDone and record.operation is not None` 時改走 `segmentDone()`；`operation is None` 的一般語音仍呼叫內層 `DoneCallback`，它的 `on_done()`、`idle()`、`synthDoneSpeaking.notify` 一個不少。`segmentDone():99-103` 和內層 `DoneCallback.__call__:344-348` 逐步相同：同一個 `cancelFlag` 物件先檢查、`player.on_done()`、`player.idle()`；內層的第二次 cancel 檢查（`:349-350`）只擋 notify，隨 notify 一起拿掉是對的。`on_done()` → `AudioPlayer.do_play` → `self.get_player()` 走的是 `_wrapPlayer:363-371` 換掉的 instance attribute，所以拿到的是 `_WavePlayer`，feed 走 `host.callback_record()` 的綁定（`:196-204`，`_nativeCallback:393` 的 `bound_callback` 之內）、`idle` 走 `_WavePlayer.idle:222-229`——和從內層 callback 進來時完全同一條路、同一個 thread（callback 在 worker 的 `RHVoice_speak` 內同步呼叫）。`host.reach(record, ENGINE_DONE)` 位置不變（`:401-402`），cancel 旗標已設時 `segmentDone()` 提早返回後照樣到達 ENGINE_DONE，和以前內層返回 `None` 後到達一樣。
- **C1 的例外語意：變嚴格，沒有回歸，也不會卡住。** 以前內層吞掉例外並 `log.error` 後 wrapper 仍到達 ENGINE_DONE；現在例外進到 `_nativeCallback:406-408` 被記在 record 上、回 refused，ENGINE_DONE 不到達。沒有任何地方**等** ENGINE_DONE：`_QueuedSpeech:262-268` 只在最終 idle 前檢查它，而 `record.error` 一旦設定就跳過 idle；host 的交接以 `record.error` 優先、barriers 其次（`segmentHost.py:588-613`），所以結果事件仍是 `SEGMENT_FAILED` 並帶同一個第一個錯誤。對 `_WavePlayer.feed`／`idle` 丟出的錯誤（`:716-729`、`:222-229` 已先 `record_error`）結果與 master 相同；只有從 `AudioPlayer.do_get_player()`（建 `nvwave.WavePlayer`、讀 `outputDeviceSection`，內層 `:189-198`）丟出的錯誤以前**沒有**記在 record 上，現在會，見 M2——那是更正確的結果，不是回歸。`test_swallowed_native_and_audio_failures_never_publish_success[idle]`、`test_cancelled_old_callbacks_do_not_complete_or_index_successor` 都仍綠。
- **C1 沒有消費者會少收到東西。** bridge 對 correlated binding 只處理 INDEX（`nvdaEvents.py:232-235`），NVDA 的 speech manager 只理 `getSynth()` 的 DONE，WorldVoice 自己的 `__init__.py:202` 用 `doneEvent=synthDoneSpeaking` 經 bridge 過濾；`addon/` 裡沒有其他 `synthDoneSpeaking.register`。
- **C6 對照 NVDA 的 `oneCore.py` 逐點成立。** NVDA 的建構在 `:268-270` 建好 trampoline 與 token 之後還有 `:280` 的 `self.voice = self._getDefaultVoice()` 會呼叫 `ocSpeech_setVoice` 而可能 raise；NVDA 自己的 `terminate:303-312` 做的就是 `_earlyExitCB = True` → `super().terminate()` → `ocSpeech_terminate(token)` → 丟掉兩個 ref。`_releaseParentNative:259-273` 鏡射這個順序，只少了基底 `driverHandler.Driver.terminate` 的 `saveSettings()`（`driverHandler.py:49`）——建構失敗的 driver 沒有初始化設定，不該存，省略正確。各個半建構點：`_dll`／`supportsProsodyOptions` 失敗 → 沒有 `_callbackInst` → 只釋放 host；`ocSpeech_initialize` raise → `HANDLE()` 的 `.value` 是 `None` → 不 terminate（`:269`）；回傳 null → 同上；`:280` raise → `token.value` 為真 → terminate；`ocSpeech_terminate` 自己 raise → `finally:271-273` 仍丟 ref，`release_newest_first` 記 log 後仍釋放 host，原例外由 `:257` 的 `raise` 重拋（`release_newest_first` 內部的 `except` 不會蓋掉 `except BaseException` 區塊的例外脈絡）。建構期間 `_player` 只會被設成 `None`（`oneCore.py:273`；沒有 callback 就不會 `_maybeInitPlayer`），所以「`_player` 已設定後失敗」沒有東西要釋放。順序：`releases = [host.terminate, _releaseParentNative]` 反轉後先 native 再 host，和 spec「newest first」一致；`detach()` 在 `ocSpeech_terminate` 之前，任何還會進來的 callback 到 `_DetachableCallback.__call__:75-81` 就停，不碰半建構的 driver。trampoline 包的是 `_DetachableCallback`（`:235-243` 攔截了 `self._callback`），`_TERMINATED_CALLBACKS` 不會留住 driver。沒有新的 parent private 名稱；guard `test_onecore_parent_privates_are_listed_and_exist` 綠。
- **C7：保留等待是對的，推理我獨立核過。** `scheduler._acquire:558-559` 在 `_stops_in_flight` 非零時不讓任何 task 開始；`_stops_in_flight` 在 `_stop_all:424-431` 的 `finally` 中、**所有** `playback.cancel()` 都返回之後才遞減，所以「每個 `core.cancel()` 返回 ⇒ 任一引擎的後繼可以開始」成立。RHVoice 這邊：`host.cancel()` → `_invalidate:690-697` 只標記；已在 `consumer()` 內、正在 `self._player.feed()` 的 feed 不受影響；內層 cancel 的 `player.stop()`（`wasapi.cpp:582-603`）把狀態設成 `stopping` 並喚醒它；若它**之後**才進 `wasPlay_feed`，`:320-323` 會 `completeStop()` 然後照常餵並 `Start()`，舊音訊真的會播到 `_feed_admitted:731-734` 的再 stop 為止。這個再 stop 跑在 worker 上；沒有 `wait_settled`，它和 `cancel()` 返回之間沒有任何順序保證，也沒有別的機制補（lifecycle 的 resource gate 是每個 host 自己的、`finish_segment` 只退 index ledger `engineAdapter.py:187-189`）。同引擎後繼由單一 worker 加 stop gate（`:235`、`:421`）排序，不需要等待。等待有界：`host.cancel()` 之後 `consumer()` 一律拒絕（`record.is_valid()` 為假），內層 speech callback 回 0 讓 `RHVoice_speak` 中止；從綁定該 record 的 callback 呼叫 `cancel()` 時 `wait_settled:481-483` 不等該 record；從 delivery thread 呼叫時 worker 的 `retire` 在 `handoff.wait()` 之前就已把 `_current` 清掉（`:526-529` 先於 `:533`），不會互等。其他四個引擎今天確實有同一個跨引擎窗口（cons.md §5 表），所以這是「它們少做」而不是「RHVoice 多做」；拿掉等待是使用者可聽見的取捨（spec §6.1），由使用者決定，維持現狀是正確的保守預設。settle 後的第二次 stop：內層 cancel 在它自己的 stop 之前或之中 raise 時（`:436-439` 只 latch），已排進去的音訊沒有人停——feed 的再 stop 只對還在飛的 feed 有效、retire 的 `stop_player` 只在一般語音且已不是 current 之後（`:536-543`）——所以這一次 stop 是 cancelling thread 上唯一保證在 worker 離開之後跑的 stop，註解正確。註解裡只有「The wait is short」一語太肯定，見 M1。
- **測試真的抓得到。** 在暫時 worktree 還原 C1：`test_ordinary_speech_waits_for_contextual_final_idle`、`test_a_segment_and_an_ordinary_utterance_notify_exactly_one_done` 失敗（`env.dones` 多一個 driver）。還原 C6：`…after_the_token_terminates_it…`、`…failing_token_release_is_logged…` 失敗（`record.calls == ["host"]`），null-token 與 initialize-raise 兩個測試不論修不修都過，和 plan 預測一致（它們釘的是「不要 terminate」）。拿掉 `host.wait_settled(current)`：20／20 次失敗（`assert stopper.is_alive()` 為假；若 stopper 碰巧還活著，之後的 `"fed" in atReturn` 也會擋）。拿掉 settle 後的 stop：20／20 次失敗（`assert True in []`）。新增與改寫的 13 個測試在分支上連跑 30 次 0 失敗。`ea58e10`、`d456a92` 各自 checkout 時 RHVoice／OneCore／guard 三個測試檔都綠，bisect-clean。
- **plan 的 Review Focus。** 1（done callback 執行中被 cancel）：`segmentDone:99-100` 的旗標檢查 + 既有兩個測試綠 ✓。2（單一 worker 上段落之後的一般語音恰好一個 DONE）：改寫的 `test_ordinary_speech_waits_for_contextual_final_idle:829-850` 先斷言 `env.dones == []` 再斷言 `== [env.driver]`，還原 C1 即失敗 ✓。3（DONE listener 從 worker 的 done callback 取消不死鎖）：`test_legacy_done_callback_can_cancel_without_deadlocking_worker:294-307` 改講一般語音，仍 `cancelled.wait` + `call.returned.wait` ✓。4（OneCore null token／terminate raise）：兩個新測試 + 還原驗證 ✓。5（cancel 追上已准入的 feed）：強化測試記錄 `fed`→`stop` 順序並在 `cancel()` 返回時快照；新測試用確定性的事件（第一次 stop 才放行 native 返回）✓。
- **帳本的三個 Ruling 都合理。** （1）`test_reentrant_successor_during_concurrent_cancel_does_not_deadlock:558-584` 原本掛在段落的 `synthDoneSpeaking` 上，這個 phase 正好拿掉那個 DONE，改掛 `synthIndexReached`：fake `Player.idle:53-73` 在 `segmentDone()` 的 `idle()` 裡同步觸發 index callback，仍在 worker、仍在 `bound_callback(record)` 內、仍與 cancel 並行，情境保住了；只是從「idle 之後」變成「idle 之內」的重入深度，對這個測試的目的（不死鎖）沒有差別。（2）null token 也把 trampoline 留在 `_TERMINATED_CALLBACKS`：`ocSpeech_initialize` raise 或回 null 之後 helper 是否還握著 callback 無從得知，留一個小 ctypes 物件比釋放後被 helper 呼叫安全，同意。（3）新測試只計 cancelling thread 的 stop、在它的第一次 stop 才放行 native 返回：`host.cancel()` 會讓 lifecycle 在自己的 thread 上 `request_stop`（也會打到同一個 fake `stop`），不這樣做測試會 flaky；而 spec §3.4 說明了 lifecycle 那次 stop 本來就不在 `cancel()` 返回之前排序，所以不計它是對的。
- **限制。** `driver/*/driver/*`、`driver/sonic/`、Unicode 資料檔無 diff；`git ls-files …/Neural` 無輸出；wrapper 沒有互相 import（OneCore 只多用既有的 `_TERMINATED_CALLBACKS`、RHVoice 只多 port 方法）；5 個 commit message 都是英文 `<type>: <summary>` 加原因，沒有 `Co-Authored-By`；prek 8 個 hook 全 Passed；ruff 0.16.3；tab 縮排、註解密度與周圍一致；readme 不動（spec §4，無使用者可見變化），同意。

## Critical

無。

## Important

無。

## Minor

### M1. 「The wait is short」說得比 spec 肯定（`driver/RHVoice/__init__.py:444-445`）

spec §3.3(d) 與 §3.4 的用語是 *bounded*，並明說「`RHVoice_speak` 在 callback 被拒之後多久返回——Windows 上未量測」。註解寫成 *short* 會讓日後讀的人以為量過。失敗情境：日後有人在 Windows 上量到長句子的 `RHVoice_speak` 要幾十毫秒才返回，回頭懷疑註解或程式有錯，而其實是設計已知的取捨。建議改成「The wait is bounded: every callback is refused now, so RHVoice_speak aborts at its next callback」。

### M2. spec §1「segment outcome is unchanged」對一類錯誤不成立；新行為更正確，但 spec 應寫明（spec `:29`；`driver/RHVoice/__init__.py:101-103`；內層 `driver/RHVoice/driver/__init__.py:189-198`）

spec 說「feed 與 idle 的失敗在傳出前就已記在 record 上」，這對 `_WavePlayer.feed`／`idle` 成立，但 `on_done()`／`idle()` 還會經 `AudioPlayer.get_player()` → `do_get_player()` 建 `nvwave.WavePlayer(... outputDevice=self.__synth.outputDeviceSection["outputDevice"])`；單一 chunk 的段落第一次 `do_play` 就在 `on_done()`，這裡丟出的錯誤（裝置開不起來、設定缺鍵）以前被內層吞掉、wrapper 到達 ENGINE_DONE，然後 `_QueuedSpeech:270` 的最終 idle 再試一次 `get_player()`——成功的話段落回報 `SEGMENT_DRAINED` 而最後一個 chunk 其實沒播。現在這個錯誤記在 record 上，段落回報 `SEGMENT_FAILED`。失敗情境：沒有，使用者只會從「靜默成功」變成「段落失敗並記 log」。建議在 spec §1 Errors 段補一句，並在 `segmentDone` 的 docstring「Errors propagate to the caller」後加「including player creation」；不需要改程式。

### M3. `segmentDone()` 鏡射的是 vendored 程式碼，沒有 guard 提醒升級時重核（`driver/RHVoice/__init__.py:93-103`；`tests/test_native_strategy_guards.py`）

`_RHVoiceInner` 其他成員只是名稱轉接，vendored driver 升級時 guard 會因名稱消失而失敗；`segmentDone()` 卻複製了 `DoneCallback.__call__:344-348` 的**邏輯**，上游若在 `on_done()` 與 `idle()` 之間多加一步（例如 flush），名稱都還在、guard 全綠、段落路徑卻悄悄少做一步。失敗情境：vendored RHVoice 更新後一般語音有新步驟、段落沒有，只有聽得出來。建議在 `test_native_strategy_guards.py` 加一個釘住 `inspect.getsource(rhvoice.DoneCallback.__call__)` 的測試（比對去除縮排後的文字，或列出預期的呼叫序列 `on_done`、`idle`、`notify`），失敗訊息指向 `segmentDone`。

### M4. 新測試的區域名稱用 camelCase，和同檔其他 helper 的 snake_case 不一致（`tests/test_rhvoice_segment_drain.py:315`、`:322`、`:327`、`:338`、`:366-368`）

`order, atReturn`、`recordedFeed`、`recordedStop`、`failingOnceStop`、`firstStop` 是檔案裡僅有的 camelCase 區域名稱；同檔的 `blocked_player`、`enqueue_from_done`、`cancel_from_done`、`delayed_delivery` 都是 snake_case（測試層不是 NVDA 層，依 naming 慣例應用 snake_case）。只影響可讀性；merge 前順手改掉即可。

## 審閱者自行驗證的項目

| 項目 | 指令 | 結果 |
| --- | --- | --- |
| 完整測試（分支 worktree） | `python3 -m pytest -q -p no:cacheprovider tests` | 3637 passed、0 skipped（108 s；基準 3632 + 5） |
| hook | `prek run --all-files` | 8 個 hook 全 Passed |
| ruff | `ruff check addon tests`；`ruff format --check addon tests` | All checks passed；241 files already formatted（ruff 0.16.3） |
| 空白 | `git diff --check master` | 無輸出 |
| 受保護路徑 | `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' addon/synthDrivers/WorldVoice/driver/sonic/ …/script_data.py …/unspaced_common_data.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 兩者皆無輸出 |
| commit 內容 | `git log --format=%B master..HEAD \| grep -ci co-authored`；`git log --format='%h %s' master..HEAD` | 0；5 個 commit 都是英文 `<type>: <summary>` |
| 跨 driver import | 檢視兩個 wrapper 的 `import` 行 | 只有 runtime／bridge／自己的 `.driver`／NVDA 模組 |
| 還原 C1（暫時 worktree `scratchpad/wt-mut`，已刪除） | `_nativeCallback` 改回一律 `callback(*args)`；`pytest tests/test_rhvoice_segment_drain.py` | 2 failed／37 passed：`test_ordinary_speech_waits_for_contextual_final_idle`、`test_a_segment_and_an_ordinary_utterance_notify_exactly_one_done`（`env.dones` 多一個 driver） |
| 還原 C6 | 刪掉 `releases.append(self._releaseParentNative)`；`pytest tests/test_wrapper_init_cleanup.py -k onecore` | 2 failed／5 passed：`…after_the_token_terminates_it_and_releases_the_host`、`…failing_token_release_is_logged_and_the_original_error_raised`；null-token 與 initialize-raise 測試照 plan 預測仍過 |
| 突變：刪 `host.wait_settled(current)` | 同上 worktree；目標兩個 C7 測試連跑 20 次 | 20／20 失敗；`test_cancel_waits_for_admitted_feed…` 在 `assert stopper.is_alive()`，`test_cancel_stops_again_after_settling…` 在 `True in stops[1:]` |
| 突變：刪 settle 後的 `self._inner.player.stop()` 區塊 | 同上，20 次 | 20／20 失敗：`assert True in []`；`test_cancel_waits_for_admitted_feed…` 仍過（它釘的是等待） |
| flakiness | 分支上 13 個新增／改寫的 RHVoice 與 OneCore 測試 ×30 | 0 失敗（每輪 13 passed） |
| 逐 commit | `wt-mut` checkout `ea58e10`、`d456a92`，跑 `test_rhvoice_segment_drain.py`、`test_wrapper_init_cleanup.py`、`test_native_strategy_guards.py` | 104 passed、107 passed |
| C7 推理 | 讀 `scheduler.py:424-431`、`:549-566`；`wasapi.cpp:320-323`、`:582-603`；`segmentHost.py:472-486`、`:488-561`、`:716-734` | 與 spec §3.3 一致（見結論第 5 點） |
| C6 對照 NVDA | 讀 `oneCore.py:241-281`、`:303-312`；`driverHandler.py:43-49` | 釋放順序與 NVDA `terminate` 一致；略過 `saveSettings` 正確 |
| 資源 | `MemAvailable` 6.3 GB；單一 pytest process（環境無 xdist） | 未觸及 3 GB 下限 |
| 清理 | `git worktree remove --force scratchpad/wt-mut`；`git worktree list` | 只剩原有三個 worktree |

未做：Windows／NVDA 實機（C1 不可聽見；C6 需要強迫 OneCore 啟動失敗；C7 無行為變更）。未打包。

## 使用者還沒確認的使用者可見預設

1. **C7 保留 `host.wait_settled(current)` 與 settle 後的第二次 stop**（spec §3.4「Decided by orchestrator with the recommended default; user may override before merge」）。取捨：NVDA 主執行緒的 `cancel()` 會等 `RHVoice_speak` 在 callback 被拒後返回（Windows 未量測）；拿掉則和其他四個引擎一樣，但多出一個「RHVoice 的尾音疊到另一個引擎第一聲」的窗口。審閱者建議維持保留。
2. **其他四個引擎的跨引擎窗口不處理**（spec §6.2）：eSpeak、SAPI5、OneCore、VE／Cerence 的 `cancel()` 在已准入的 feed 還在飛時就返回。要補等待會改它們的 cancel 延遲；本 phase 不做。
3. **C6 只在 Linux fake 上驗證**：Windows 上 OneCore 啟動失敗的 token 釋放未實測（spec §2 說明沒有實用的手動項目）。
4. **不加 changelog／readme**（spec §4）：三項都沒有 NVDA 使用者可察覺的變化。

## 修正記錄

日期：2026-10-30。修正者：Opus 5.5（一般流程 §3.4）。只有 Minor，依 §3.4 不做修正 review。

| 發現 | commit | 修正 |
| --- | --- | --- |
| M1 | `42a3cc9` docs: call RHVoice's cancel wait bounded rather than short | `driver/RHVoice/__init__.py` 的 cancel 註解改成「The wait is bounded: every callback is refused now, so RHVoice_speak aborts at its next callback (how soon it returns is unmeasured)」，和 spec §3.3(d)、§3.4 用語一致。 |
| M2 | `cd8e855` docs: note that RHVoice segments now fail on player creation errors | spec §1 Errors 段改寫：`_WavePlayer.feed`／`idle` 的失敗結果不變；`AudioPlayer.do_get_player()`（建 `nvwave.WavePlayer`、讀 `outputDeviceSection`）的錯誤以前被內層吞掉、段落可能 `SEGMENT_DRAINED` 但最後一個 chunk 沒播，現在記在 record 上而回報 `SEGMENT_FAILED`，是更正確的結果。`segmentDone` docstring 補「including player creation failures, which the inner callback swallowed」。無行為變更。 |
| M3 | `71e4638` test: pin the vendored RHVoice DoneCallback that segmentDone mirrors | `tests/test_native_strategy_guards.py` 新增 `test_rhvoice_segment_done_mirrors_the_pinned_inner_done_callback`：以 `ast.unparse` 正規化內層 `DoneCallback.__call__`，和 `RHVOICE_DONE_CALLBACK_CALL` 比對（照同檔其他 guard 用 AST 讀原始碼、不 import）；失敗訊息要求重核 `_RHVoiceInner.segmentDone()` 再更新常數。驗證：暫時從預期文字拿掉 `self.__player.idle()` 一行 → 1 failed（訊息如上）；還原後同檔 50 passed。 |
| M4 | `6b95ea4` test: use snake_case locals in the RHVoice cancel tests | `tests/test_rhvoice_segment_drain.py` 的 `atReturn`、`recordedFeed`、`recordedStop`、`failingOnceStop`、`firstStop` 改成 `at_return`、`recorded_feed`、`recorded_stop`、`failing_once_stop`、`first_stop`；39 passed。`tests/test_wrapper_init_cleanup.py` 的 `setVoice` 不改：該檔既有的替身函式都沿用被替換的 native 名稱（`deleteEngine`、`stopGate`、`sonicInitialize`），`setVoice` 對應 `ocSpeech_setVoice`，和該檔一致（見帳本 Ruling）。 |

驗證（head `6b95ea4`）：`python3 -m pytest -q -p no:cacheprovider tests` 3638 passed、0 skipped（3637 + M3 的 1 個 guard；MemAvailable 6.3 GB，單一 process）；`prek run --all-files` 8 個 hook 全 Passed；`git diff --check master` 無輸出；受保護路徑與 `git ls-files …/Neural` 皆無輸出。未做 Windows／NVDA 實機驗證（本輪只有註解、spec、測試變更）。
