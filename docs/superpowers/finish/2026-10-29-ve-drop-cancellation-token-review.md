# Review：VE／Cerence 一般語音不再收到請求的取消 token，只經 host（`cancel()`）取消

日期：2026-10-29。分支：`fix/ve-drop-cancellation-token`（`bff05d4..46cd7ce`，4 個 commit：`4ab32fb` wrapper＋測試、`0d222e4` 移除 `SegmentHost.withdraw`、`6981d11` 移除 `"cancellationToken"` trait、`46cd7ce` spec 修正；基準 `master` `bff05d4` collect 3605 個測試；分支 collect 3559，−46：刪掉的 token-only 測試多於新增的 4 個整合測試）。
審閱者：Fable 5.1（唯讀；只新增本檔）。流程：簡化流程（DEVELOPMENT_WORKFLOW.md §5），沒有 spec／plan，依 §3.3 的重點審閱；協調者另外指定六個重點：DONE 歸屬的交接、是否還有東西依賴 token／withdraw、刪掉的測試是否合理、新 guard 是否穩、plain fallback 和 master 的行為差異、VE／Cerence 同步與限制。

依據：

- 程式碼：`addon/synthDrivers/WorldVoice/driver/VE/__init__.py`、`driver/Cerence/__init__.py`、`runtime/segmentHost.py`（`enqueue`、`cancel`／`_invalidate`、`abandon`、`retire`）、`runtime/scheduler.py`（`submit_request`、`abort_request`、`_cancel_request_locked`、`cancel`、`cancel_current`、`_stop_all`、`_acquire`、`_execute`、`_settle`、`_run_one`、`shutdown`、`_accepts_events_locked`、`_process_event_batch`）、`bridge/engineAdapter.py`、`bridge/nvdaEvents.py`、`bringup.py`（`Teardown`）、`__init__.py`（`_TEARDOWN_ORDER`）、`voices/manager.py`（`terminate`），內層 `driver/VE/driver/__init__.py` 的 `BgThread`、`DoneSpeaking`、`speak`、`cancel`（唯讀）。
- 測試：`tests/test_runtime_drain_integration.py`、`tests/test_vocalizer_segment_drain.py`、`tests/test_worldvoice_cancel_wrappers.py`、`tests/test_native_strategy_guards.py`、`tests/test_runtime_legacy_adapter.py`、`tests/test_segment_host.py`、`tests/test_worldvoice_request_manager.py`、`tests/test_hygiene_guards.py`、`tests/test_vocalizer_drift.py`、`tests/runtime_harness.py`。
- 文件：分支改的四份 spec，以及主 checkout 未追蹤的 `docs/superpowers/specs/2026-09-24-speech-request-lifecycle-design.md`（唯讀）。
- 行號以 head `46cd7ce` 為準；路徑省略 `addon/synthDrivers/WorldVoice/`。VE 與 Cerence 在 callback 類別之前行號相同（legacy ENDPROCESS 的 ack 都在 `:226-234`），之後相差 7：`_beginRecord` VE `:508`／Cerence `:510`、`_idlePlayer` `:650`／`:657`（`_doneOwner = record` `:656`／`:663`）、`cancel` `:702`／`:709`、`_dropQueuedSpeech` `:737`／`:744`、`_onIndexReached` `:778`／`:785`（交換 `:782`／`:789`、判斷 `:787`／`:794`）。

## 結論

**程式碼正確、新的 DONE 歸屬沒有漏發或誤發、可以 merge。** Critical 0、Important 1（刪掉的 token 測試帶走了一條仍存在的 callback 分支的唯一覆蓋，建議補一個不用 token 的版本）、Minor 5（guard 的寫法、兩個等價的防禦、spec 的幾處殘留、一行註解），都不擋 merge。

- **`_idlePlayer` → `_onIndexReached(None)` 的交接是單執行緒、順序固定的。** 內層 `DoneSpeaking.__call__`（內層 `:234-237`）在 BgThread 上先 `self._player.idle()` 再 `self._onIndexReached(None)`；`_player` 是 `_enqueue`（`:484`）在 host admission 下綁到本筆紀錄的 `_IdleRoutingPlayer`，它的 `idle()` 只轉給 `_idlePlayer(record)`（`:112-116`）。`_doneOwner` 只有三個寫入點：`__init__`（`:366`）、`_idlePlayer` 第一行（`:656`，在任何提早返回之前）、`_onIndexReached(None)` 的交換清除（`:782`）；後兩者都在 BgThread 上、同一個 task 內先後執行，沒有鎖的需要。`_onIndexReached(None)` 只有 DoneSpeaking 會呼叫（內層 VECallback 只送整數索引，內層 `:189`；外層 `_ContextualVECallback._index` 也是），所以「讀到別人的 owner」不可能；內層 driver 在受保護路徑下不會改。逐案核對：
  - 正常完成（含一個請求內換語音的多個 `_NativeTask`、空請求只有 DoneSpeaking）：紀錄是 current 且有效 → idle → 等暫停結束 → reach `PLAYED_OUT` → DONE。和 master 相同，只是 owner 來源從 `_beginRecord` 改成 idle 本身。
  - 失敗的請求（native 錯誤、callback 錯誤、quiescence 失敗）：`_idlePlayer` 因無效提早返回但 owner 已記下 → `_onIndexReached` 看到 `cancelled=False` → DONE 照發（突變 M9 證明 `test_failed_ordinary_speech_still_publishes_done` 釘住）。
  - idle 本身拋出（`:668-675`）：owner 已記下，但 DoneSpeaking 在 `_onIndexReached` 之前就拋出，所以不發 DONE——和 master 相同（master 的註解也是「as before」）；`_doneOwner` 留著舊紀錄直到下一個 DoneSpeaking 覆寫，中間沒有讀者，無害。
  - 被 host 取消：`host.cancel()` 的 `_invalidate`（`segmentHost.py:672-678`）把所有 pending 紀錄標成 cancelled；一般紀錄要到 `retire`＋`forget` 才離開 pending（`:534-536`），而 DoneSpeaking 永遠在 `_Retire` 之前跑，所以「DoneSpeaking 執行時紀錄仍 pending」成立，`_onIndexReached` 的 `record.cancelled` 判斷（`:787`）一定看得到 host 的取消。cancel 卡在 idle 中：`_realPlayer.stop()` 讓 idle 返回、暫停等待以「無效」醒來、不 reach、不發 DONE。
  - 被 `cancel()` 丟掉、從未開始的紀錄（`_dropQueuedSpeech` 保留它的 DoneSpeaking，`:768-771`）：`_idlePlayer` 因不是 current 返回，`_onIndexReached` 因 cancelled 返回。master 在這裡發了 DONE（`_doneOwner` 是 `None`、token 是 `None` → 照發），這就是 commit 說的「token 從未蓋到的缺口」：審閱者把分支的新測試放到 master 的 scratch 複本上跑，`queued-behind-a-retire` 兩個引擎都失敗（`assert not fresh.tasks[0].end_seen` → `True`），`mid-native-call` 兩個通過（token 蓋得到）；在分支上拿掉 `record.cancelled` 判斷（突變 M1），四個案例全部失敗。主張成立。
  - `terminate()`：`host.terminate()` 先 `_invalidate`，再 `cancel()`，`_stopBgThread` 把佇列跑完，被保留的 DoneSpeaking 都不發 DONE；`Teardown` 的固定順序把「task manager shutdown」放在「voice manager terminate」之前（`__init__.py:150-151`），所以沒有「core 被終止但 scheduler 還在等它 DONE」的情況。
  - 暫停：`_idlePlayer` 的暫停等待（`:676-679`）和 owner 無關；`test_ordinary_played_out_waits_for_resume_after_the_final_idle`、`test_ordinary_cancelled_during_the_final_pause_never_plays_out` 沒有因為去掉 token 而變弱。
- **「每次 token 取消之後都會對持有該請求工作的 core 呼叫 `cancel()`」成立。** `_cancel_request_locked`（`scheduler.py:386-395`）的呼叫者：`cancel`（`:428-441`，接著 `_stop_all` 停目前 task 的 playback 加上呼叫者給的 ports）、`cancel_current`（`:443-452`，停目前 task 的 playback）、`submit_request`（`:238-258`，只在 BUILDING，請求還沒進任何 core）；`abort_request`（`:260-270`）同樣只在 BUILDING；`_run_one` 的例外（`:499`）由 `_settle` 的 `_stop_playback`（`:569-570`）跟上；`_execute` 在 `speak` 返回後再補一次（`:547-549`）。一個請求的工作只會由 `_execute` 交給 current task 的 playback，而 `_acquire`（`:509-510`）要等 `_stops_in_flight` 歸零，所以「可能持有請求工作的 core」就是 current task 的 playback，每條路徑都有停到。`Future.cancel()` 確實不停 core，但它也不取消 token，master 上的 VE 也不會因它停下，行為不變。hygiene guard（`tests/test_hygiene_guards.py:248-256`、`:315-340`）把 production 的 `stop`／`cancel` 呼叫鎖在 `TaskManager._stop_playback → EngineSession.cancel → VoiceClassAdapter.cancel` 這條鏈上，所以「host 取消＝請求已取消」的前提有 guard 守著。
- **殘留競爭：位置略有移動，條件沒變，可接受。** 誤投遞需要「DoneSpeaking 的判斷通過 → 之後 scheduler 取消並讓下一個請求在同一 core 成為 current → 之後遲到的 DONE 才進 `on_events`」。以前判斷看 token（`scheduler.cancel()` 的第一步就取消），現在看 `record.cancelled`（在 `_stop_all` → `core.cancel()` → `host.cancel()` 時才設定，比 token 晚一點）。在這兩個時刻之間執行的 DoneSpeaking 以前被壓下、現在會發 DONE——但這時 `_stops_in_flight > 0`，下一個 task 的 `_acquire` 還在等，`_current_task` 仍是舊 task，`_accepts_events_locked`（`:282-290`）因 token 已取消而忽略它。所以要誤投到下一個請求，仍然必須讓 BgThread 在 `super()._onIndexReached(None)` → `synthDoneSpeaking.notify` → `nvdaEvents._onDone` → `on_events`（同步、同一執行緒）這幾個 Python 呼叫之間，被整個 `core.cancel()`（含真 player 的 `stop()`）加上下一個 task 的 `_acquire`／`activate`／`speak` 超車——和以前的條件相同。production 走 segment（drain）路徑，DONE 根本不參與完成判定，所以這只影響 plain fallback。
- **plain fallback 和 master 的差異，除了文件寫的 DONE 壓制之外還有一項，兩者都是使用者決定的後果。**（1）被 host 取消的一般請求不再發 DONE；scheduler 對已取消的請求本來就忽略 DONE（`_accepts_events_locked`），所以無害；而「直接 `core.cancel()`、請求 token 仍有效，還是要有 DONE」這條舊契約（刪掉的 `test_direct_core_cancel_still_reports_done`、`test_direct_wrapper_stop_mid_speech_lets_next_segment_run`）被明確放棄，hygiene guard 保證 production 沒有這種呼叫者。（2）`_recordValid`（`:501-506`）不再看 token：從 `token.cancel()` 到 `host.cancel()` 拿到 admission 之間，舊請求的 callback 會繼續餵音訊、送索引（以前 token 一取消就被拒絕）。索引到了 scheduler 會因 token 已取消被丟掉；音訊幾個 buffer 之後被 `cancel()` 的 `_realPlayer.stop()` 切掉——這正是其他四個引擎一直以來的行為，也是這次的目標。segment 紀錄的 `record.work.is_valid()` 看的是 `CancellationView`，所以 production 路徑的「token 一取消就拒絕」沒有變。（3）player 的 stop 次數：以前 token-only 取消 → `withdraw` → retire 不 stop（只有 callback 自己的 stop）；現在 host 取消 → `cancel()` 一次 stop ＋ retire 的 cancelled 路徑一次 stop。這和 master 的 `token-then-cancel` 變體相同（那才是 NVDA 上實際發生的順序），測試從 `0` 改成 `2` 是把 production 的順序留下來、把不存在的順序刪掉，合理。索引、`AUDIO_FED`／`ENGINE_DONE`／`PLAYED_OUT` 的到達條件、`retire` 的 error 分支都沒有改。
- **刪掉／改寫的測試，逐組看過：** `test_vocalizer_segment_drain.py` 的 token 測試改成 `cancel()` 版本（`:1951`、`:1973`、`:2001`、`:2025`、`:2109`），斷言的 player／DONE／barrier 數值和 master 的 `token-then-cancel` 一致；`test_token_cancelled_in_the_engine_done_check_is_withdrawn` 釘的是「token 要在兩個 reach 之後讀」這個順序，順序和 withdraw 一起消失，刪除合理；`test_token_cancelled_ordinary_leaves_contextual_final_idle_untouched`、`test_ordinary_waiting_behind_contextual_does_not_poll` 只有 token 才能表達（排在 segment 後面的一般請求在佇列裡什麼都不會輪詢，`_Retire(segment)` 等的是 `handoff.wait()` 這個 Event），`test_cancel_during_contextual_final_idle_releases_waiting_ordinary` 留著 host 版本；`test_segment_host.py` 三個 withdraw 測試隨 API 刪除，`test_a_host_cancelled_ordinary_record_retires_cancelled`（`:354`）保留 missing／complete／error 三個案例；`test_worldvoice_cancel_wrappers.py` 的 token 變體合併成 `cancel()` 變體，`test_cancel_during_real_callback_feed_stops_after_feed` 釘的是「token 取消不停 player、靠 callback 的 stop」，這個行為不存在了；`test_worldvoice_request_manager.py` 的直接停止契約如上。**例外是兩條仍存在的分支失去覆蓋**，見 I1（legacy ENDPROCESS 的 ack）與 M3（`_beginRecord` 的 `skipped`）。
- **guard：** `test_no_core_takes_the_request_token`（`tests/test_native_strategy_guards.py:606-615`）用子字串掃整個套件的 `.py`，能守住「關鍵字沒有回來」，但不是它名字說的那件事，見 M1；真正釘住 bridge 行為的是 `test_plain_speak_never_passes_the_request_token`（`tests/test_runtime_legacy_adapter.py:74`，三種 declared／claim 組合都只呼叫 `speak(commands)`）和 `test_bridge_speaks_the_real_vocalizer_wrapper_without_a_token`（`:563`，真 wrapper）。`test_vocalizer_wrapper_has_no_guard_fallback` 的 `extraCapabilities == {"waitfactor", "variant"}` 加上 `_onIndexReached` 的來源檢查，足夠。
- **還有沒有東西依賴 token／withdraw：** `addon/` 零命中；`tests/` 只剩否定斷言和註解；`docs/` 只有 spec（分支已加刪除線的四份，以及四處沒改到的歷史描述，見 M4）；`ref/` 的外掛（Neural、IBM、Aisound）沒有 `cancellationToken`／`supportsCancellationToken`／`withdraw`。
- **VE／Cerence 同步、限制：** 兩個 wrapper 的分支 diff 經 `VE→X`／`Cerence→X` 正規化後逐行相同，只差 `_PROFILE`；`tests/test_vocalizer_drift.py` 的 `ALLOWED` 沒動。沒有碰 `driver/*/driver/*`、`driver/sonic/`、Unicode 資料檔（§7 兩個指令都沒有輸出）；沒有 Neural；wrapper 沒有互相 import；四個 commit message 都是英文、`fix:`／`refactor:`／`docs:` 格式、內文說明原因、沒有 `Co-Authored-By`；`prek` 8 個 hook 全過；`git diff --check` 乾淨。readme 沒改：production 的 `CompletionPolicy` 以 `forceUnverifiedDrain=True` 讓 VE／Cerence 一律走 segment，一般 `speak()` 只在測試或直接呼叫 core 時用到，使用者看不到這次改動。
- **spec 修正（`46cd7ce`）：** 3d-1 的四處（目標 3、`_VEStrategy` 的 token 句、`speak()` 簽章與 `native=`、修訂 #1／#2）、phase 4 的兩處、phase 50 的 D2、phase 52 的五處（Part 2 目標、non-goal、§4 三條宣告、rule change、SAPI5 guard）都在既有刪除線之上再加一層，內容和實作一致。沒改到的殘留見 M4；主 checkout 未追蹤的 09-24 spec 要加的註記列在最後一節。

## Critical

無。

## Important

### I1. `_ContextualVECallback.__call__` 的 legacy ENDPROCESS 承認分支失去唯一的測試（VE／Cerence `:226-234`；刪掉的 `test_legacy_endprocess_after_token_cancel_does_not_count`）

分支：`_callbackAdmission` 找得到 `call`、但 `host.consumer` 不准入或 `_recordValid` 為假時 yield `(None, call)`（`:636-638`），`__call__` 對一般紀錄的 `VE_MSG_ENDPROCESS` 回 `NUAN_OK`、其他訊息回 `NUAN_E_TTS_USERSTOP`（`:229-235`）。它還是會走到：callback 內 `host.record_error`（例如 feed 拋出，`:296-302` 的 finally 或 `_process` 的 except）之後，同一次 native 呼叫的 ENDPROCESS；或是 `host.cancel()` 已把紀錄標成 cancelled、`cancel()` 還沒在 `_speechStateLock` 下關掉 `call.admitting`（`:717-719`）的那段時間。以前唯一走到它的測試是用 token 取消（token 取消不關 admission），這次隨 token 刪掉。審閱者把 `return NUAN_OK` 改成 `return NUAN_E_TTS_USERSTOP`（突變 M4），**完整套件 3559 個全部通過**。`test_cancel_mid_feed_retires_cancelled`（`:1973`）走的是 `cancel()` 關了 admission 之後的路徑（`call is None` → USERSTOP），覆蓋不到這條。

失敗情境：日後有人把這個分支「簡化」成一律 USERSTOP、或把 `message.contents.eMessage` 的比對改壞，套件不會發現；SDK 在一般語音的最後一個 ENDPROCESS 收到 USERSTOP 而不是 OK，`ProcessText2Speech` 的 `raw(*args)` 會回 `NUAN_E_TTS_USERSTOP`，`_runNative`（`:587-588`）在紀錄仍有效時會把它當錯誤記下。

建議修法：把刪掉的測試改成不用 token 的版本——native 內先 `emit(env, instance, end=False)`，再 `host.record_error(record, OSError(...))`（或 `env.core._segmentHost.record_error`），然後 `end_process(env, instance)`，斷言結果是 `[NUAN_OK]`、`record.native.lastCallEnded is False`、`engine_done` 沒到、retire 走 error 分支。這樣 M4 會被殺，而且測的是今天還存在的路徑。

## Minor

### M1. `test_no_core_takes_the_request_token` 是子字串掃描，守的和名字說的不同（`tests/test_native_strategy_guards.py:606-615`）

它對 `addon/synthDrivers/WorldVoice` 下每個 `.py`（含內層 driver、註解、docstring）找 `"cancellationToken"`。兩個方向都不準：一條寫「unlike the old cancellationToken…」的歷史註解會讓它失敗；一個把參數取名 `token=` 的 core 它看不到。「沒有 core 收到請求的 token」真正的釘子是 bridge 的 `_speakPlain` 只呼叫 `speak(commands)`（`test_plain_speak_never_passes_the_request_token`）。

建議修法：二擇一。(a) 改用 AST：對每個 `.py` 檢查沒有名為 `cancellationToken` 的參數、關鍵字引數或字串常數，註解就不會誤觸；(b) 保留子字串掃描但把測試名和註解改成它實際守的事（「the old keyword does not come back」），並把 `test_vocalizer_wrapper_has_no_guard_fallback:369` 那行重複的 `assert "cancellationToken" not in source` 刪掉。

### M2. 兩個等價的防禦沒有說明是防禦（VE `:656-658`、`:782`；Cerence `:663-665`、`:789`）

突變 M8（`self._doneOwner = record` 移到 segment 早退之後）和 M10（`_onIndexReached` 不清除 `_doneOwner`）在五個 vocalizer 測試檔 352 個測試下都存活：segment 的 owner 在 `_onIndexReached` 一樣以 `operation is not None` 擋掉，而每個 DoneSpeaking 都先經 `_idlePlayer` 覆寫 owner，所以清不清除沒有可觀察的差別。兩者都該留（idle 拋出時留下舊 owner、或日後有別的 `_onIndexReached(None)` 來源時，清除是唯一的擋板），但 `:654-655` 的註解可以補一句「cleared on read so a DONE without a preceding idle names nothing」，讓讀者知道這是刻意的。

### M3. `_beginRecord` 的 `skipped` 分支失去了來自 token 測試的覆蓋（VE `:513-519`；Cerence `:515-521`）

刪掉的 `test_token_cancelled_before_begin_never_retires`、`test_done_of_never_spoken_request_skips_idle` 是透過「token 在 Begin 之前已取消」走到 `record.native.skipped = True` → `host.abandon`。現在能走到它的是：cancel 落在 BgThread 已取出 `_Begin`、還沒執行 `_beginRecord` 的空檔（`_dropQueuedSpeech` 看不到它）、pending 時 latch 了 control error、或 segment 的 submit 拋出後被 abandon 的紀錄。突變 M11（分支改成永不 skip）在完整套件 3559 個測試下**存活**。這條分支今天是防禦：沒有它，被取消的紀錄仍會被每個 native 呼叫的 `_recordValid` 拒絕、經 `retire` 的 cancelled 路徑退役，只多一次 `host.begin` 和一次 callback 緩衝重置，所以列 Minor；但它是 production 會走到的路徑，應該有直接的案例。

建議修法：在 `test_vocalizer_segment_drain.py` 加一個 `test_cancel_before_begin_skips_the_record`：monkeypatch `_beginRecord` 為「先 `env.core.cancel()` 再呼叫原本的 `begin(record)`」（和 `:1951` 的順序相反），斷言 `record.native.skipped`、`record.abandoned`、沒有 native 呼叫、`outcomes == []`（abandon 不經 `retire`）、`env.dones == []`、player `(fed, idles, stops) == ([], 0, 1)`。

### M4. 四處沒改到的 spec 殘留仍把 token 寫成現況

- `docs/superpowers/specs/2026-10-03-phase3d1-ve-design.md:87`：BgThread 圖的 `Begin → … silence gate 換成這筆的 token`。P49 拿掉 `_SilenceGate` 時就已過時，這次 token 也沒了，建議一併劃掉並標 `Corrected by fix/ve-drop-cancellation-token`（Begin 現在只做 `host.begin` 與重置 callback 緩衝）。
- `2026-10-28-phase51-nvda-private-check-design.md:166`：「`VoiceClassAdapter` calls `speak(commands)` without a token, because NVDA's driver has no `supportsCancellationToken`」——理由已不成立（對任何 core 都不傳）。
- `2026-10-05-phase10a-voice-manager-design.md:146`：「`supportsCancellationToken` 是可選的布林能力」——介面描述，已移除。
- `2026-09-28-worldvoice-correlated-drain-design.md:33`：表格「目前只傳 commands／既有 cancellationToken 給 core」——當時的現況，可加一句註記。
- `2026-10-28-phase52-shared-barriers-design.md:550`「The only reader of `supports_cancellation_token` is `_speakPlain`」在相容性段落裡沒有劃掉；它描述的是 phase 52 當時的狀態，留作歷史可以，但同段前面已改，最好一致。

建議修法：merge 後和 09-24 spec 一起在 `master` 補一個 docs commit（§5 第 7 步）。

### M5. 區段註解把「被 host 取消的紀錄不發 DONE」寫成絕對（`tests/test_vocalizer_segment_drain.py:1860-1864`）

「A record cancelled through cancel() (the host) retires cancelled: … and it publishes no DONE」——但同一區段的 `test_cancel_between_the_retire_reaches_is_not_a_failure`（`:2025`）和 `test_cancel_after_the_last_call_retires_cancelled`（`:2001`）一個有 DONE、一個沒有：DONE 由 DoneSpeaking 當下的 `record.cancelled` 決定，cancel 落在 DoneSpeaking 之後就已經發了。

建議修法：改成「publishes no DONE when the cancel lands before its DoneSpeaking; a cancel after it leaves the DONE already published」。

## 09-24 spec（主 checkout，未追蹤）需要加「Corrected by `fix/ve-drop-cancellation-token`」的段落

`docs/superpowers/specs/2026-09-24-speech-request-lifecycle-design.md`，行號以主 checkout 現檔為準：

1. `:20` 末句「唯一傳入 core 的是片段的取消 token，且只傳給明確宣告支援的 core（見「VE／Cerence 包裝層取消語意」）」→ plain `speak(commands)` 不傳 token；segment 入口 `speak_segment(commands, token, …)` 傳的是 `CancellationView`。
2. `:31` 末句「支援取消 token 的 core 會在自己的入口再做一次原子檢查，關閉剩餘窗口」→ 沒有 core 做入口檢查；`speak` 返回後 scheduler 再看一次 token 並 `cancel()` playback（`_execute`），對每個引擎都一樣。
3. `:47-49` 「**VE 與 Cerence**：由包裝層 core 入口的 token 檢查處理」整個 bullet → 劃掉；VE／Cerence 和「其他引擎」一樣。兩個前提（token 先於 `core.cancel()` 取消；`starting`／`awaiting_done` 片段的 core 都被 `cancel()`）仍是 scheduler 的規則，保留。`:50` 「其他引擎，以及包裝層防護安裝失敗而退回原行為的 VE／Cerence」→ 所有引擎。
4. `:60-61`（`supportsCancellationToken`、`core.speak(text, cancellationToken=token)`、「`cancellationToken` 為選用參數」）→ 劃掉。
5. `:68`、`:70`、`:73`（`_SilenceGate` 把「token 已取消」視為停止；`_GuardedPlayer.idle()` 已取消時不動作）→ 劃掉（gate 與代理 player 在 P49 已移除；idle 現在由 `_idlePlayer` 對非 current／無效的紀錄略過，並為 DONE 記下紀錄）。
6. `:77-78` `speak(speechSequence, cancellationToken=None)` 與入口 token 檢查 → `speak(speechSequence)`；入列後返回，取消只經 `cancel()`。
7. `:83` `_onIndexReached`：「取消 token 時丟棄索引與完成通知；若只有直接呼叫 `core.cancel()`…轉送完成通知」→ 反過來：被 host 取消的紀錄的 DoneSpeaking 不發 DONE（LEGACY_DONE 的 DONE 不帶請求身分，會結束下一個請求在同一 core 的 task；scheduler 不會等已取消的請求）；直接 `core.cancel()` 而不經 scheduler 的呼叫者由 hygiene guard 禁止。
8. `:85-91` 「為何能關閉入口競態」整節 → 劃掉（沒有入口檢查）。
9. `:93-101` 「token 已取消、但旗標尚未設置的期間」整節，尤其 `:101` → 劃掉；這段期間現在和其他引擎相同：舊請求的 callback 繼續餵音訊到 `host.cancel()` 為止，scheduler 丟掉它的索引，`cancel()` 停 player。
10. 驗證 `:139` 第 1 項「對不支援 token 的假 core…」→ 所有 core；`:145` 第 7 項、`:149` 第 8 項、`:150-152` 第 9–11 項 → 劃掉，改指向 `test_cancel_before_the_native_call_retires_cancelled`、`test_cancel_mid_feed_retires_cancelled`、`test_core_cancel_rejects_real_callbacks_of_the_held_native_call`、`test_cancelled_vocalizer_done_cannot_start_the_next_engine_early`；`:157` 第 16 項「未傳 token 的呼叫仍可…」→ 這是唯一的呼叫形式。

## 使用者還沒確認的使用者可見預設

- 沒有。production 走 segment 路徑，這次的三項 plain fallback 差異（host 取消不發 DONE；token 取消到 `host.cancel()` 之間 callback 不再被拒絕；取消時 player 停兩次）使用者在 NVDA 上碰不到。readme 六個語言都沒改，合理。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 完整套件（head `46cd7ce`，序列） | `cd /workspace/WorldVoice-droptoken; python3 -m pytest -q tests -p no:cacheprovider`，背景 watchdog 每 2 秒讀 `/proc/meminfo`，MemAvailable < 3 GB 就 kill pytest（`scratchpad/verify/run.sh`） | **3559 passed／0 skipped**（105.96 s）；watchdog 沒有觸發 |
| 基準數 | master 的 scratch 複本（分支複本以 `git show master:` 蓋回 24 個改動檔）`pytest --collect-only -q` | 3605 → 3559，−46 |
| hooks | `prek run --all-files` | 8 個 hook 全部 Passed |
| 空白 | `git diff --check` | 無輸出 |
| 受保護路徑 | §7 的 `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' …` 與 `git ls-files …/driver/Neural` | 兩個都無輸出 |
| commit 格式 | `git log master..HEAD --format=%B \| grep -ci co-authored` | 0 |
| VE／Cerence 同步 | 兩個 wrapper 的 `git diff master..HEAD` 經 `sed VE→X`／`Cerence→X` 後 `diff` | 只差 index 行和 `_PROFILE` |
| 新整合測試在 master 上 | master scratch 複本只蓋上分支的 `tests/test_runtime_drain_integration.py`，`-k cancelled_vocalizer_done` | `queued-behind-a-retire` VE／Cerence **失敗**（`end_seen` 為 True）；`mid-native-call` 兩個通過 |
| 突變 M1：`_onIndexReached` 拿掉 `or record.cancelled`（VE／Cerence 同時） | 五個 vocalizer 測試檔 `-x`；另外單跑新整合測試 | 被殺：`test_cancel_during_contextual_final_idle_releases_waiting_ordinary[VE]`；整合測試 4/4 失敗 |
| 突變 M4：legacy ENDPROCESS 的 `return NUAN_OK` → `USERSTOP` | 五個檔 352 個；再跑完整套件 | **存活**（352 passed；完整 3559 passed）→ I1 |
| 突變 M5：`_dropQueuedSpeech` 連一般語音的 DoneSpeaking 也丟掉 | 五個檔 `-x` | 被殺：`test_kept_done_of_a_dropped_request_never_plays_out_another[VE]` |
| 突變 M8：`_doneOwner = record` 移到 segment 早退之後 | 五個檔 | 存活（等價，M2） |
| 突變 M9：非 current／無效的紀錄把 `_doneOwner` 清成 `None` | 五個檔 `-x` | 被殺：`test_failed_ordinary_speech_still_publishes_done[VE]` |
| 突變 M10：`_onIndexReached` 不清除 `_doneOwner` | 五個檔 | 存活（等價，M2） |
| 突變 M11：`_beginRecord` 永不 `skipped` | 五個檔；再跑完整套件 | 五個檔存活（352 passed）；完整套件也**存活**（3559 passed）→ M3 |
| 殘留引用 | `grep -rn "cancellationToken\|withdraw\|supports_cancellation_token\|supportsCancellationToken" addon tests docs`；`ref/` 排除 `ref/nvda` | `addon/` 0；`tests/` 只有否定斷言；`docs/` 只有 spec（M4 列出沒改的四處）；`ref/` 外掛 0 |
| 09-24 spec | 讀主 checkout 的未追蹤檔（唯讀） | 需要註記的段落見上一節 |

Linux 上只驗證了受控的 native 與音訊邊界；Windows 上的 NVDA、實際音訊裝置與 VE／Cerence SDK 沒有驗證到。沒有打包。

## 修正記錄

日期：2026-10-29。修正者：Opus 5.5（依 §3.4，先寫測試再改）。VE 與 Cerence 同步修改，`tests/test_vocalizer_drift.py` 的 `ALLOWED` 沒動。突變在 worktree 上以腳本同時改兩個 wrapper、跑指定測試、再用 `git checkout --` 還原（當時兩個 wrapper 沒有未提交的改動）。

| 項目 | commit | 修法 | 突變結果 |
| --- | --- | --- | --- |
| I1 | `5f22563` | 新增 `test_legacy_endprocess_after_a_recorded_error_is_acknowledged_but_does_not_count`（`tests/test_vocalizer_segment_drain.py`）：native 內先送不含 ENDPROCESS 的音訊，再 `host.record_error(host.current(), …)`，接著送 ENDPROCESS；斷言回 `NUAN_OK`、`lastCallEnded is False`、三個 barrier 都沒到、retire 走 error 分支（`(False, error)`）、player `(fed, idles, stops) == ([b"pcm"], 0, 1)`、失敗的請求仍發一次 DONE、沒有缺 barrier 的 log。 | 突變 M4（legacy ENDPROCESS 的 `return NUAN_OK` → `NUAN_E_TTS_USERSTOP`，兩個 wrapper）：新測試 VE／Cerence 都失敗，**被殺**。 |
| M3 | `dbed6c6` | 新增 `test_cancel_before_begin_skips_the_record`：把 `_beginRecord` 換成「先 `cancel()` 再呼叫原本的 begin」；斷言 `record.native.skipped`、`abandoned`、`cancelled`，沒有 native 呼叫，`outcomes == []`（abandon 不經 `retire`），player `([], 0, 1)`（只有 `cancel()` 自己的 stop），沒有 DONE、沒有缺 barrier 的 log。 | 突變 M11（`_beginRecord` 的 skip 條件改成 `if False:`，兩個 wrapper）：新測試 VE／Cerence 都失敗，**被殺**。 |
| M1 | `86399d4` | 子字串掃描改成 AST：`_token_names` 找名為 `cancellationToken`／`supportsCancellationToken` 的參數、關鍵字引數、屬性、名稱與非 docstring 的字串常數（`extraCapabilities` 裡的 `"cancellationToken"` 也算），註解與 docstring 不算；測試改名 `test_no_add_on_code_names_the_request_token`，另加 `test_token_name_detection` 釘住偵測範圍；刪掉 `test_vocalizer_wrapper_has_no_guard_fallback` 裡重複的子字串 assert。 | 在 VE 的 `speak` 加回 `cancellationToken=None` 參數：guard 失敗（`driver/VE/__init__.py:462`），**被殺**；只在同一行加含 `cancellationToken` 的註解：guard 通過（不再誤觸）。 |
| M2 | `987a66c` | 在 `_idlePlayer` 的 `self._doneOwner = record` 與 `_onIndexReached` 的清除處各補註解，說明兩者今天是等價的防禦（segment 的 DONE 本來就被 operation 擋下；每個 DoneSpeaking 都先 idle）。只改註解。 | 不適用（突變 M8／M10 依舊等價存活，已在註解說明）。 |
| M4 | `3f86812` | 已追蹤的 spec 加刪除線與「Corrected by `fix/ve-drop-cancellation-token`」：3d-1 的 Begin 圖（程式碼區塊內標 `~~…~~`，區塊後補一行說明）、phase 51 不傳 token 的理由、phase 10a 的 `supportsCancellationToken` 能力、2026-09-28 correlated-drain 的 adapter 表格列、phase 52 相容性段落的 `supports_cancellation_token` 讀者句。主 checkout 未追蹤的 09-24 spec 依協調者指示不動。 | 不適用。 |
| M5 | `227218a` | `tests/test_vocalizer_segment_drain.py` 區段註解改成：cancel 落在 DoneSpeaking 之前才不發 DONE；落在之後，DONE 已經發出。 | 不適用。 |

驗證（head `3f86812`，序列＋MemAvailable < 3 GB 即終止的 watchdog）：完整套件 **3564 passed／0 skipped**（3559＋I1 兩個＋M3 兩個＋`test_token_name_detection` 一個）；`prek run --all-files`、`git diff --check`、§7 受保護路徑的兩個指令，結果見下一個 commit 後的重跑。Linux 上只驗證受控的 native 與音訊邊界；Windows 上的 NVDA、實際音訊裝置與 SDK 沒有驗證到。
