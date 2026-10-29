# Review：Phase 54 drain semantics（暫停落在段落交界由 scheduler 保留；OneCore 逐段 idle）

日期：2026-10-29。分支：`phase54-drain-semantics`（`5d836bd..8e29343`，11 個 commit：`3624beb` spec、`c67f087` plan、`e1d1bd4` lease 註記、`5f0aeaf` 完成保留、`27f7674` 開始保留、`0dfee13` OneCore 拿掉 drain 等待、`d385dd2` VE／Cerence 拿掉 drain 等待、`cd46239` barrier 註解＋readme、`dfc8c97` C4 決定、`3a982bc` OneCore drain 改真正 player 的 `idle()`、`8e29343` spec 修正＋readme；基準 `master` `5d836bd` 3617 passed，分支 3630 passed）。
審閱者：Fable 5.1（唯讀；只新增本檔）。流程：一般流程（DEVELOPMENT_WORKFLOW.md §3.3）。

依據：

- spec `docs/superpowers/specs/2026-10-29-phase54-drain-semantics-design.md`；plan `docs/superpowers/plans/2026-10-29-phase54-drain-semantics.md`（Review Focus 1–5 逐項檢查）；進度帳本 `.superpowers/sdd/2026-10-29-phase54-drain-semantics/progress.md`（兩個 `Ruling:`）；來源 `cons.md` C3／B10、C4、B9（唯讀）。
- 程式碼：`runtime/scheduler.py`（`TaskManager._paused`／`_pause_target`、`_pausable_playback_locked` `:462-475`、`pause_current` `:477-509`、`cancel` `:433-449`、`_acquire` `:549-566`、`_execute` `:568-616`、`_wake_cancelled` `:618-622`）、`runtime/barriers.py:31-37`、`driver/OneCore/__init__.py`（`_OneCorePlayer` `:101-125`、`drain` `:191-211`、`_legacyCallback` `:481-505`、`_maybeInitPlayer` `:559-571`、`pause` `:606-634`）、`driver/VE/__init__.py:347-353`、`driver/Cerence/__init__.py:347-353`、`runtime/segmentHost.py`（`LeasedPlayer` `:699-775`）、`runtime/session.py`（`PlaybackPort` `:67-85`、`EngineSession.pause` `:191-192`）、`__init__.py:332-340`。
- NVDA（`ref/nvda/`，唯讀）：`source/nvwave.py:331-332`（feed 啟用 ducker）、`:370-382`（`sync`／`idle`）、`:384-392`（`stop`）、`:396-404`（`pause`）；`source/audioDucking.py:109-146`（ref count、延後 1000 ms 的 `_unensureDucked`）、`:208-266`（`enable`／`disable`）；`source/speech/speech.py:217-240`（`cancelSpeech`／`pauseSpeech`）、`:1159-1160`（`speak` 時暫停中先 cancel）；`source/speech/manager.py:704-730`、`:768-770`；`source/keyboardHandler.py:737` 與 `source/inputCore.py:607-612`（NVDA 用自己的 `isPaused` 決定送 `pause(True)` 還是 `pause(False)`，都在 main thread 的 event queue 上）；`nvdaHelper/local/wasapi.cpp:650-670`（`pause`／`resume` 在 `playState != playing` 時直接回 `S_OK`）；`source/locale/{zh_TW,zh_HK,zh_CN,ru,uk}/LC_MESSAGES/nvda.po` 的 "Audio d&ucking mode:"。
- 測試：`tests/test_runtime_scheduler.py`（新增 11 個、改寫 1 個）、`tests/test_runtime_drain_integration.py:181-196`、`tests/test_onecore_segment_drain.py`、`tests/onecore_drain_harness.py`、`tests/test_vocalizer_segment_drain.py`、`tests/test_vocalizer_drift.py`（沒有 diff）。
- 行號以 head `8e29343` 為準；路徑省略 `addon/synthDrivers/WorldVoice/`。

## 結論

**程式碼正確、符合 spec 與使用者決定、可以 merge；merge 前請補 I1（一個確定性的測試）。** Critical 0、Important 1、Minor 6。

- **scheduler 的狀態機正確，鎖序沒有破。** 新狀態只在 `_state_cond` 下讀寫；兩個保留（完成保留 `:601-605`、開始保留 `:555-556`）都只在 `_state_cond` 上 `wait()`，不持 `_delivery_lock`，所以 `cancel()`（`_delivery_lock` → `_state_cond`，`:437`）和引擎 thread 的 `on_events`（同樣先拿 `_delivery_lock`）都不會被卡住。所有轉發給引擎的 `pause()` 都在鎖外（`:496-498`），和今天一樣。每一種喚醒都在同一個 condition 上 `notify_all`：恢復 `:509`、`cancel`／`cancel_current` 的 `_wake_current_locked` `:402-405`、`shutdown`（經 `cancel`）、公開 `Future.cancel()` 的 `_wake_cancelled` `:618-622`；`_state_cond` 預設是 `RLock`，done-callback 在持鎖的 thread 上跑也不會死鎖。我把每條喚醒路徑逐一拿掉做突變（S1、S2、S6、S7、S10），分支的測試都抓得到（見驗證表）。
- **和 NVDA `isPaused` 的一致性（spec §2 的三個條件）成立。** NVDA 永遠用自己的 `isPaused` 決定送 `pause(True)` 還是 `pause(False)`（`keyboardHandler.py:737`），`pauseSpeech` 在 synth 丟例外時不改 `isPaused`（`speech.py:237-239`）；scheduler 的 `pause(True)` 失敗會還原、`pause(False)` 失敗維持暫停（`:499-504`），兩邊同步（S5、S11 都被殺）。每一條清掉 `isPaused` 的 NVDA 路徑都先 `cancel()` 到 synth（`speech.py:231-233`、`:1159-1160`；`pauseSpeech` 重設 `beenCanceled` `:240`，所以暫停之後的第一次 cancel 一定會到 synth），而 `TaskManager.cancel` 同時清掉 `_paused`／`_pause_target`（`:439-441`）。say-all 期間 NVDA 的 manager 直接呼叫 `getSynth().speak`（`manager.py:715`、`:730`），不經 `speech.speak`、不會 cancel，但新請求的第一個 task 會停在開始保留，恢復後才播——這正是 C3 要的行為。
- **「不把 pause 轉給已完成的段落」的邏輯正確，但只涵蓋 scheduler 已經看到完成的情況。** `_pausable_playback_locked` `:472-474` 在 `_completion_ready_locked` 成立時回 `None`，避免 `pause(True)`／`pause(False)` 在空閒的 WASAPI player 上重新啟用 ducker（`nvwave.py:396-404`）。音訊已經播完、但 `SEGMENT_DRAINED` 還沒送到 scheduler 的窗口仍會轉發，這和 master 一樣（master 對任何 AWAITING 的 task 都轉發），不是回歸；見 M5。
- **C4 真的到了真正的 player。** `_OneCorePlayer` 是 `LeasedPlayer(idle_barrier=None)`（`:109`），`LeasedPlayer.idle` 先進 `host.consumer()`，沒有被准入的 record 就回 `None`（`segmentHost.py:758-762`）；drain 在 record 退役後才跑，所以 `player.idle()` 會什麼都不做。分支改呼叫 `player._player.idle()`（`:200`），`_player` 是 `LeasedPlayer.__init__` 存的真正 `WavePlayer`（`segmentHost.py:708`）。突變 O1（改回 `player.idle()`）讓 `test_segment_drain_idles_the_real_player` 和另外 8 個既有測試失敗（harness 的 `Player.idle` 不會被呼叫、`idles` 停在 0）；O2（改回 `sync()`）被 2 個新測試殺掉。失敗路徑照 P53：`record_error` → `player.stop()` → 只有 stop 失敗才 `_failSegmentControl`（`:201-210`），`test_idle_failure_fails_only_its_segment` 釘住 `control_error is None` 與後繼段落照常 drain。一般路徑 `_legacyCallback:490-497` 沒動，`test_legacy_speak_still_uses_parent_interface` 加了 `idles == 1`。
- **spec 對 NVDA ducking／trimming 的說法逐條核對無誤。** `idle()` = `sync()` + 重新啟用開頭靜音修剪 + `_audioDucker.disable()`（`nvwave.py:376-382`）；`disable()` 只是把全域 ref count 的遞減排到 1000 ms 後（`audioDucking.py:123-129` 的 `core.callLater(1000, …)`），`enable()` 立刻遞增（`:109-112`），所以一秒內接著的下一段 `feed()`（`nvwave.py:331-332`）讓 ducking 不會在段落之間放開；「OneCore 說完後約一秒恢復其他音訊」的描述正確。`WavePlayer.idle()` 不呼叫 C++ 的 `wasPlay_idle`，不會重開裝置。
- **VE／Cerence 同步。** 兩個檔案的 hunk 在名稱代換後逐行相同；`tests/test_vocalizer_drift.py` 沒有 diff，`ALLOWED` 不變。拿掉的等待 `_pauses == 0 and not _paused` 只在「`idle()` 返回之後、`reach(PLAYED_OUT)` 之前」這個窄窗有作用（`idle()` 本身在暫停時不返回，`wasapi.cpp:620-634`），現在由 scheduler 的完成保留接手；突變 V1（把等待加回 VE）被 VE 的 2 個改寫測試與整合測試 `[VE]` 抓到。
- **外掛相容。** `SegmentDrainCore.speak_segment` 的介面沒變、`SegmentHost` 沒變；等待放在 scheduler 而不是 `SEGMENT_DRAINED` 發布之前，是為了不改 Neural 實作的介面（spec §2「Where the wait goes」），我同意這個預設。`LEGACY_DONE`／一般路徑：`_completion_ready_locked` 對 `LEGACY_DONE` 在 DONE 之後成立，所以暫停同樣不轉給已完成的 task、同樣被保留；OneCore 無 token 的一般路徑保留自己的 `_segmentPaused` 等待（`:491-501`），和 scheduler 的保留疊加無害。
- **plan 的 Review Focus。** 1（跨引擎的下一段不得開始）：`test_pause_after_drain_holds_next_engine_until_resume` 殺 S1、S4 ✓。2（恢復要先到達被暫停的引擎）：測試存在但**抓不到反例**，見 I1。3（`pause(True)` 失敗不能永遠卡住）：`test_failed_pause_restores_unpaused_state` 殺 S5 ✓（帳本說它在修正前就會過，是因為沒有保留就沒有東西要還原；作為回歸守門是對的）。4（cancel 釋放兩種保留）：`test_cancel_releases_completion_hold_and_clears_pause`、`test_cancel_releases_start_hold` 與既有的 `test_cancel_wakes_break_token_and_allows_new_request` 殺 S7 ✓。5（P53 情境）：`test_failed_paused_task_holds_next_request_and_resume_reaches_failed_engine` 釘住失敗延後回報、下一個請求被保留、恢復送到失敗的引擎 ✓。
- **帳本的兩個 Ruling 都合理。** （1）`test_pause_resume_holds_request_after_actual_idle_returns` 從「暫停中沒有 `SEGMENT_DRAINED`」改成「引擎回報 drain、scheduler 保留請求」，是 spec 的新語意，必須改；我在 scratch 把分支 checkout 到 `0dfee13` 重跑，確認只有 `[OneCore]` 失敗（1 failed、2 passed），帳本的紀錄屬實。代價是一個 commit 不 bisect-clean，見 M4。（2）readme 用粗體標題＋「part of speech」沿用相鄰的既有條目而不是 plan 的一句話，spec 已同步更新，合理。
- **readme。** 六份都加了兩條，位置、格式和相鄰條目一致；ducking 用詞和 NVDA 各語言的 "Audio d&ucking mode:" 一致（zh_TW 自動音量調整、zh_HK 自動調整其他音量、zh_CN 音频闪避、ru приглушение аудио、uk приглушування）。沒有碰 `addon/doc/en/` 和 `.html`。zh_TW 兩條簡潔、口語，符合使用者偏好。
- **限制。** `runtime/` 仍然 NVDA-free（`scheduler` fixture 的 import 守門在跑）；沒有碰 `driver/*/driver/*`、`driver/sonic/`、Unicode 資料檔；沒有 Neural；wrapper 之間沒有互相 import；11 個 commit message 都是英文 `<type>: <summary>` 加原因、沒有 `Co-Authored-By`；舊 spec 的修正用刪除線＋`Corrected by`（phase 3c `:93`、phase 52 `:85`／`:129`／`:140`），但漏了兩處，見 M3。

## Critical

無。

## Important

### I1. Review Focus 2 的測試抓不到「恢復還沒到達引擎就讓後繼段落開始」：把 `pause_current(False)` 改成先清狀態、再轉發的突變，`test_resume_reaches_paused_engine_before_successor_starts` 連跑 4 次都過（`tests/test_runtime_scheduler.py:1007-1022`；受測程式 `runtime/scheduler.py:494-509`）

spec §2 和 plan Global Constraints 都把「轉發的 `pause(False)` 在狀態清除**之前**返回，所以同一引擎的後繼段落不會在該引擎恢復之前開始」當成設計重點，plan 指定由這個測試涵蓋。測試只記錄呼叫順序 `["speak", ("pause", True), ("pause", False), "speak"]`，但轉發的 `pause(False)` 是 main thread 上一個立刻返回的 fake，而 worker 要被 `notify_all` 喚醒、拿兩個鎖、`finish_segment`、再 `_acquire` 才會 `speak`——即使程式先清狀態再轉發，main thread 幾乎一定先 append `("pause", False)`。突變 S3（在 `:495` 之後立刻 `_paused = False`、`_pause_target = None`、`notify_all`，然後才轉發）在整個 `tests/test_runtime_scheduler.py`＋整合測試下只被 `test_failed_resume_keeps_the_pause` 殺掉——那是另一個性質（失敗的恢復維持暫停），不是順序；如果日後有人把「失敗維持暫停」改成用旗標實作，順序的保證就沒有任何測試守著。

失敗情境：日後重構 `pause_current`（例如把清狀態和轉發合併成一個 `finally`），OneCore／VE 的後繼段落在 `pause(False)` 尚未送到引擎時就 `speak`；OneCore 的 `_maybeInitPlayer:566-568` 看到 `_segmentPaused` 仍為 True 會把新 player 再暫停一次，使用者聽到恢復後第一段沒聲音，要再按一次暫停／恢復；測試全綠。

建議修法：讓轉發的 `pause(False)` 阻塞，證明後繼在它返回之前不會開始。我在 scratch 寫了下面的測試並驗證：未突變的分支通過，S3 立刻失敗（`stays_unset` 看到第二次 `speak`）。

```python
def test_resume_forward_returns_before_successor_starts(manager, rt):
	port = drain_port(rt)
	release, second_speak = Event(), Event()
	calls = []
	original = port.pause

	def pause(switch):
		original(switch)
		if not switch:
			calls.append("resume-entered")
			assert release.wait(HOLD_TIMEOUT)
			calls.append("resume-returned")

	def on_speak():
		calls.append("speak")
		if calls.count("speak") == 2:
			second_speak.set()

	port.pause = pause
	port.on_speak = on_speak
	request = manager.new_request()
	manager.append_speech(request, port, "Fake:a", ("one",))
	manager.append_speech(request, port, "Fake:a", ("two",))
	assert manager.submit_request(request)
	assert port.entered.wait(WAIT_TIMEOUT)
	manager.pause_current(True)
	drained(manager, rt, port)
	resuming = Thread(target=lambda: manager.pause_current(False))
	resuming.start()
	eventually(lambda: "resume-entered" in calls)
	stays_unset(second_speak, message="the successor started before the forwarded resume returned")
	release.set()
	resuming.join(WAIT_TIMEOUT)
	assert second_speak.wait(WAIT_TIMEOUT)
	assert calls == ["speak", "resume-entered", "resume-returned", "speak"]
```

可以取代現有的 `test_resume_reaches_paused_engine_before_successor_starts`，或並列保留（現有的那個仍證明「恢復有送到被暫停的 port」）。

## Minor

### M1. 開始保留裡的 `_valid_locked(task)` 沒有測試守著，而且公開 `Future.cancel()` 不會喚醒它（`runtime/scheduler.py:555-556`、`:591`）

突變 S12（`while self._stops_in_flight or self._paused:`）在 scheduler 與整合測試 102 個下全部存活：`cancel()` 本來就清掉 `_paused`，所以分支的測試看不出差別。而且 `_wake_cancelled` 的 done-callback 要到 `_execute:591` 才註冊，停在 `_acquire` 的 task 被 `Future.cancel()` 時沒有人 `notify`——我在 scratch 寫的探針（暫停、送出請求、`future.cancel()`、等 DONE）在**未突變**的分支上也等不到 DONE，worker 要等到恢復或 cancel 才略過那個 task。production 沒有人呼叫公開的 `Future.cancel()`（grep 只有 scheduler 自己的三處 `:262`、`:449`、`:647`），`_stops_in_flight` 的等待在 master 上也是同樣行為，所以只是和完成保留（spec 明寫 `Future.cancel()` 要喚醒）不對稱。建議：若要補齊，把 `add_done_callback` 提前到 `_acquire` 進入等待之前（callback 只 `notify_all`，`done` 事件那時還沒有，可以只在 `done is not None` 時 `set`），並加測試 `test_cancelled_future_releases_start_hold`（暫停、送出、`future.cancel()`、`output.wait_done() == 1`、`port.entered` 未設定）；若不補，至少在 `_acquire` 的註解寫明「`_valid_locked` 只影響略過無效 task 的時機，喚醒靠 resume／cancel」。

### M2. `self._pause_target or self._pausable_playback_locked()` 用真值判斷 `PlaybackPort`（`runtime/scheduler.py:495`）

`EngineSession` 和 `FakePlayback` 目前都沒有 `__bool__`／`__len__`，所以正確；但 `PlaybackPort` 是 Protocol，外掛或日後的 port 若定義了 `__len__`（例如可迭代的 port），`_pause_target` 會被當成 falsy 而把恢復送錯對象。改成 `playback = self._pause_target if self._pause_target is not None else self._pausable_playback_locked()`，零風險。

### M3. 兩處舊文件沒有一起修正（`docs/superpowers/specs/2026-10-02-phase3c-onecore-design.md:44`；`docs/superpowers/specs/2026-10-29-phase53-player-control-fault-design.md:69-74`）

- phase 3c `:44`「暫停：pause lock、`_segmentPaused`、`_segmentControlGeneration`，drain 時暫停中要等待恢復。」——`:93` 改了，`:44` 的同一句沒改。
- phase 53 `:69-74`「Known consequence (no change in this phase)」整段描述 VE 失敗後「a successor segment of the same utterance plays although NVDA still shows speech paused … that successor's drain waits for a resume」與 OneCore「that successor's drain waits for a resume」。本分支之後：失敗的 task 停在完成保留，恢復後才 raise，同一請求的後繼段落被 token 取消、不會播；兩個引擎的 drain 都不再等待恢復。這段應該加刪除線並標 `Corrected by \`phase54-drain-semantics\``，否則下一次讀 P53 的人會以為這個後果還在。

### M4. `0dfee13` 單獨 checkout 時 `test_pause_resume_holds_request_after_actual_idle_returns[OneCore]` 失敗（帳本 Ruling 已記）

帳本誠實記了「不 bisect-clean」。更好的切法是在 Task 3 的 commit 就一起改整合測試的 OneCore 期望（或把整合測試的修改放在 Task 2 的 commit，因為那時 scheduler 的語意就已經確定）。不需要重寫歷史；記在這裡供下次參考。

### M5. 兩個 ducker 會被「空轉」啟用的窗口沒有在 spec／barriers 註明（`runtime/scheduler.py:491-498`；`nvwave.py:396-404`）

（a）音訊已播完、`SEGMENT_DRAINED` 還沒送到 scheduler 時的 `pause(True)` 仍會轉發：`WavePlayer.pause(True)` 停掉 client 並 `disable()` ducker；之後的 `pause(False)` 對一個沒有音訊的 player `enable()` ducker，直到該引擎下一次 `idle()`／`stop()` 才放開（如果下一段在另一個引擎，可能是很久以後）。master 也是如此（它對任何 AWAITING 的 task 都轉發），不是回歸。（b）P53 情境：失敗路徑的 `stop()` 已經清掉 player 的暫停並 `disable()` ducker，恢復時轉發到 `_pause_target` 的 `pause(False)` 又 `enable()` 一次；`wasPlay_resume` 在 `playState != playing` 時無害（`wasapi.cpp:661-664`），但 ducker 會留在啟用狀態。兩個都是「有開 ducking 時其他音訊維持被壓低」的邊角，不是本 phase 引入，建議只在 spec §2 的「不把 pause 轉給已完成的段落」段落補一句說明窗口範圍。

### M6. `test_segment_drain_does_not_wait_for_resume`（OneCore）結尾的 `env.driver.pause(False)` 沒有 `try/finally` 保護（`tests/test_onecore_segment_drain.py:917-928`）

前面的斷言失敗時 driver 留在暫停狀態；`env` fixture 若有 teardown 會等 `_segmentPaused` 清除就可能卡住。VE 版（`:1106-1118`）和 `test_drain_reports_while_a_resume_is_in_flight` 都用了 `try/finally`，OneCore 這個照做即可。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 完整測試（序列、記憶體看門狗 MemAvailable < 3 GB 即殺） | `python3 -m pytest -q tests -p no:cacheprovider` 於 worktree | **3630 passed、0 skipped**，108 s；看門狗未觸發 |
| prek | `prek run --all-files` | 8 個 hook 全部 Passed |
| 空白 | `git diff --check master..HEAD` | 乾淨 |
| 受保護路徑 | `git diff --stat master -- 'driver/*/driver/*' driver/sonic/ unicodeScripts/script_data.py unicodeScripts/unspaced_common_data.py`；`git ls-files driver/Neural` | 兩個都沒有輸出 |
| VE／Cerence 同步 | 兩個 hunk 以 `VE`／`Cerence` → `X` 代換後 `diff` | 逐行相同；`tests/test_vocalizer_drift.py` 無 diff |
| 署名 | `git log master..HEAD` 全文 grep `Co-Authored` | 無 |
| 突變（scratch 複本 `git clone --shared`，每個套用後 `git checkout -- .` 還原；測試範圍 `test_runtime_scheduler.py`＋`test_runtime_drain_integration.py`，OneCore／VE 另加各自的 drain 測試） | S1 拿掉完成保留 | 殺：`test_pause_after_drain_holds_next_engine_until_resume` |
| | S2 拿掉開始保留的 `_paused` 條件 | 殺：`test_pause_without_current_task_holds_next_task` |
| | S3 恢復先清狀態再轉發 | **只被 `test_failed_resume_keeps_the_pause` 殺**；`test_resume_reaches_paused_engine_before_successor_starts` 4／4 次通過 → I1；I1 的替代測試 1／1 次殺掉 |
| | S4 拿掉「完成就不轉發」 | 殺：`test_pause_after_drain_holds_next_engine_until_resume`（`first.paused == []`） |
| | S5 `pause(True)` 失敗不還原 | 殺：`test_failed_pause_restores_unpaused_state` |
| | S6 `_wake_cancelled` 不 `notify` | 殺：`test_cancelled_future_releases_completion_hold` |
| | S7 `cancel()` 不清暫停 | 殺：`test_cancel_wakes_break_token_and_allows_new_request`、`test_cancel_releases_completion_hold_and_clears_pause`、`test_cancel_releases_start_hold` |
| | S8 恢復忽略 `_pause_target`；S9 不記 `_pause_target` | 殺：`test_pause_during_segment_is_forwarded_and_resume_returns_to_it` |
| | S10 完成保留不看 `_valid_locked` | 殺：`test_cancelled_future_releases_completion_hold` |
| | S11 `pause(False)` 失敗仍清狀態 | 殺：`test_failed_resume_keeps_the_pause` |
| | S12 開始保留不看 `_valid_locked` | **存活**（102 passed）→ M1 |
| | O1 OneCore drain 用 lease 的 `player.idle()` | 殺：`test_segment_drain_idles_the_real_player`、`test_idle_failure_fails_only_its_segment` 與 7 個既有測試（真正的 idle 從未被呼叫） |
| | O2 OneCore drain 改回 `sync()` | 殺：同上 2 個新測試（2 failed、85 passed） |
| | O3 OneCore drain 加回 `_segmentPaused` 等待 | 殺：`test_segment_drain_does_not_wait_for_resume`、`test_drain_reports_while_a_resume_is_in_flight`、整合測試 `[OneCore]` |
| | V1 VE drain 加回 `_pauses`／`_paused` 等待 | 殺：VE 的 2 個改寫測試、整合測試 `[VE]` |
| 帳本 Ruling（`0dfee13` 不 bisect-clean） | scratch `git checkout 0dfee13`，跑 `-k pause_resume_holds_request` | `[OneCore]` 1 failed、`[VE]`／`[Cerence]` passed，與帳本相符 |
| 開始保留的 `Future.cancel()` 探針 | scratch 加測試（暫停、送出、`future.cancel()`、等 DONE） | 未突變的分支也等不到 DONE → M1 |
| NVDA ducking／trimming／pause 的說法 | 讀 `nvwave.py:331-332`、`:370-404`；`audioDucking.py:109-146`、`:208-266`；`wasapi.cpp:650-670` | spec §3.1 全部屬實：`idle()` 只 `disable()`，解除延後 1000 ms；`pause(False)` 會 `enable()` |
| NVDA pause／cancel／speak 路徑 | 讀 `speech.py:217-240`、`:1159-1160`；`manager.py:715`、`:730`、`:768-770`；`keyboardHandler.py:737`；`inputCore.py:607-612` | spec §2 的三個「可靠」條件成立；say-all 的 push 不經 cancel，由開始保留接住 |
| readme 的 NVDA 用詞 | grep 五個 `nvda.po` 的 "Audio d&ucking mode:" | zh_TW 自動音量調整、zh_HK 自動調整其他音量、zh_CN 音频闪避、ru приглушение аудио、uk приглушування，全部一致 |
| 舊 spec 修正完整性 | grep specs 的 `_segmentPaused`／`等待恢復`／`waits for a resume` | 漏 phase 3c `:44`、phase 53 `:69-74` → M3 |

Linux 上只驗證了受控的 fake player／native；Windows 上 NVDA、WASAPI、引擎 SDK 都沒有驗證到。spec §2 與 §3.6 列的手動項目（多引擎 say-all 在段落交界按暫停、長停頓中暫停、暫停後打字、有開 ducking 時音樂約一秒後恢復、OneCore 段落開頭是否被修剪過頭）仍需在 Windows 上聽。

## 使用者還沒確認的使用者可見預設

1. **等待放在 scheduler，而不是 `SEGMENT_DRAINED` 發布之前**（spec §2「Where the wait goes」，orchestrator 預設）：對 NVDA 使用者聽起來相同；差別是外掛的 `speak_segment` 介面不變、引擎的 lifecycle 資源在等待期間已釋放。審閱者同意。
2. **暫停中發生的段落失敗，要到恢復或 cancel 之後才回報給 NVDA**（spec §6.2，orchestrator 預設）：暫停期間 NVDA 不會收到那個請求的 DONE，也不會 push 下一句；恢復後請求失敗、下一句照常。審閱者同意；替代方案（失敗立刻回報）會讓 NVDA 在暫停中 push 下一句並被開始保留擋住，結果一樣，只是多一個狀態。
3. **break（WorldVoice 自己的停頓）在暫停期間繼續計時**（spec 非目標）：暫停落在長停頓中，恢復時停頓已過、直接播下一段。
4. **C4 選項 A 的副作用：OneCore 每段都重新啟用開頭靜音修剪**（spec §3.6）：OneCore 段落之間的銜接會略緊；使用者已選 A，但「段落開頭沒有被剪到字」要在 Windows 聽過才算確認。
5. **readme 條目用粗體標題＋「part of speech」**（Ruling），而不是 plan 的一句話；spec 已同步。
