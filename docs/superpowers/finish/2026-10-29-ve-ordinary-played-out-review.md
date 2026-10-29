# Review：VE／Cerence 一般語音宣告並到達 `PLAYED_OUT`，最後 idle 綁定到自己的紀錄

日期：2026-10-29。分支：`fix/ve-ordinary-played-out`（`9c3bec4..a17d260`，2 個 commit：`0bd6454` wrapper＋測試、`a17d260` spec 修正；基準 `master` `9c3bec4`，collect 3589 個測試；分支 collect 3603，+14 ＝ drain 測試每引擎 7 個）。審閱時 `master` 已前進到 `faabf12`（只多一份 finish 文件），所以 `git diff master..HEAD` 多出一個「刪除」`2026-10-29-set-voice-no-stop.md`，那是基準漂移，不是分支的改動；下面的比對一律用 `9c3bec4..HEAD`。
審閱者：Fable 5.1（唯讀；只新增本檔）。流程：簡化流程（DEVELOPMENT_WORKFLOW.md §5），沒有 spec／plan，依 §3.3 的重點審閱；協調者另外指定六個重點：player 替換的執行緒安全、`record.barriers` 建立後的變動、正確路徑的誤判、idle 失敗的處理、測試是否釘住每個主張、VE／Cerence 同步與限制。

依據：

- 程式碼：`addon/synthDrivers/WorldVoice/driver/VE/__init__.py`、`driver/Cerence/__init__.py`、`runtime/segmentHost.py`（`NativeRecord`、`enqueue`、`cancel`／`_invalidate`、`abandon`、`reach`、`record_error`、`latch_control_error`、`withdraw`、`retire`），內層 `driver/VE/driver/__init__.py` 的 `BgThread`、`DoneSpeaking`、`speak`、`_speak`、`cancel`、`pause`、`terminate`（唯讀）。
- 測試：`tests/test_vocalizer_segment_drain.py`、`tests/test_native_strategy_guards.py`、`tests/test_vocalizer_drift.py`、`tests/worldvoice_cancel_wrapper_harness.py`。
- 文件：`docs/superpowers/specs/2026-10-03-phase3d1-ve-design.md`、`2026-10-28-phase52-shared-barriers-design.md`、`docs/superpowers/finish/2026-10-29-ve-ordinary-barriers-review.md`（上一輪）。
- 行號以 head `a17d260` 為準；路徑省略 `addon/synthDrivers/WorldVoice/`。VE 與 Cerence 的行號相差 2：`_ORDINARY_BARRIERS` 都在 `:50`、`_IdleRoutingPlayer` 都在 `:98-119`；`_enqueue` VE `:477-498`（替換 `:485`、`pop` `:493`、還原 `:496`），Cerence `:479-500`（`:487`、`:495`、`:498`）；`_idlePlayer` VE `:664-689`（`record_error` `:681`、`reach` `:689`），Cerence `:671-696`（`:688`、`:696`）。

## 結論

**程式碼正確、找不到正確路徑會被判為缺關卡的情況、可以 merge。** Critical 0、Important 0、Minor 4（都是註解、一個預設值、一行斷言，不擋 merge）。

- **player 替換是安全的，但它是防禦，不是必要條件。** `_enqueue`（`:485`）在 host admission 之下把 `self._player` 換成綁定本筆紀錄的 `_IdleRoutingPlayer`，`finally` 還原（`:496`）。這段期間讀 `self._player` 的只有：內層 `speak()` 最後一行建構 `DoneSpeaking(self._player, …)`（內層 `:435`，這正是要攔的那一個）、`pause()` → 內層 `self._player.pause(switch)`（內層 `:459`，主執行緒；兩種 proxy 都經 `__getattr__` 轉給真 player）、`_finishTermination` → 內層 `terminate()` → `self._player.close()`（內層 `:346`；它在 `host.terminate()` 之後才跑，而 `host.terminate()` 要拿 admission，所以一定等 `_enqueue` 結束）。內層 `cancel()` 的 `self._player.stop()` 被外層 `cancel` 覆寫、改用 `_realPlayer`；callback 的 `_player` 是建構時就給的真 player（`_initializeNative:421-426` 在 `_installGuard` 之前）；`TtsSetParamList`、`ProcessText2Speech`、`_isSilence.clear` 都不碰 player；Sonic 在 callback 裡。`__getattr__` 轉送 `feed`／`stop`／`pause`／`idle`（真 player 的，只有 proxy 自己的 `idle` 被攔）／`close`／任何屬性，沒有漏。tuple 指派先算右邊再指派，`self._player` 沒有瞬間是 `None`。兩次 `_enqueue` 不會重疊（`enqueue` 和 `speak_segment` 的 `submit` 都在 `_admission` 下），所以還原不會把別人的 proxy 蓋掉。
  不過要說清楚：**沒有這個替換，`master` 的 `_currentRecord` 查詢在 production 也不會錯**。`DoneSpeaking` 是在 `_Begin` 和 `_Retire` 之間入列、同一條 BgThread 依序執行；`cancel()` 的 `_dropQueuedSpeech` 保留相對順序，而後一筆的 `_Begin` 要等 cancel 釋放 admission 之後才入列，所以被保留的 `DoneSpeaking`（屬於被丟掉、從未開始的紀錄）永遠在下一筆的 `_Begin` 之前執行，此時 `_currentRecord` 是 `None`。`test_kept_done_of_a_dropped_request_never_plays_out_another`（`:2266`）要靠「在 native 呼叫裡手動執行被保留的 task」才重現那個 hazard（master 上確實多 idle 一次：`(False, 1) != (False, 0)`）。綁定讓歸屬變成局部的、不依賴佇列順序的推理，代價是一個多執行緒可見的狀態替換，而每個讀者都轉送到真 player，所以可接受；但 commit message 和測試註解把它寫成真實風險，見 M4。
- **`record.barriers.pop(PLAYED_OUT)`（`:493`）沒有競爭。** `pop` 在提交執行緒上、`_Retire` 入列（`:498`）之前；BgThread 讀 `record.barriers` 的只有 `_retireRecord`（`in` 判斷、`reach`）和 `_idlePlayer` 的 `reach`，前者在 `_Retire`，後者在 `DoneSpeaking`（而內層 `speak()` 拋出時根本沒入列——`DoneSpeaking` 是內層 `speak()` 的最後一個 statement，`_speak` 的例外、`getVoiceInstance`／`getParameter` 的例外都在它之前）。`host.begin`、`consumer`、`bound_callback`、`record_error`、`latch_control_error` 都不讀 barriers。`queue.put` 之後 `get` 是 happens-before，所以 BgThread 看到的一定是 pop 之後的 dict。host 的文件（`segmentHost.py:1-14`）只說「engine marks its own completion barriers on each record」，沒有「建立後不可變」的不變量；`NativeRecord.barriers` 是 `dict[str, bool]`，`new_record` 用 `dict.fromkeys` 建一份新的，每筆紀錄各自一份，不共用 `_ORDINARY_BARRIERS`。guard 測試把 `.barriers.pop(...)` 的第一個引數也納入「必須是共用常數」的檢查（`tests/test_native_strategy_guards.py:517-523`），和 `get` 同一條規則，合理。
- **找不到正確的 SDK 卻讓一般紀錄缺 `played_out` 的路徑。** 一筆一般紀錄能走到 `host.retire` 的關卡檢查，必須是：host 看來有效（沒被 `_invalidate` 標成 cancelled）、沒有 `error`、沒有 withdrawn（token 未取消）。在這三個前提下，逐條核對 `_idlePlayer`（`:664-689`）的每個提早返回：
  - `record is None`：只有 `_installGuard` 的共用 proxy 沒綁紀錄，而 `DoneSpeaking` 只由 `_enqueue` 視窗內的內層 `speak()` 建構（外層 `speak`／`speak_segment` 都經 `host.enqueue` → `submit` → `_enqueue`；內層沒有別的地方呼叫 `speak`），所以 production 不會有綁到 `None` 的 `DoneSpeaking`。
  - `record.operation is not None`：segment 的 `DoneSpeaking` 一如以前什麼都不做，segment 的 `PLAYED_OUT` 由 `_VEStrategy.drain` 在 lifecycle thread 上到達（`:341-358`，沒改）。
  - `record is not self._currentRecord`：`_currentRecord` 只在 `_beginRecord`（有效且未 abandoned 且沒有 control error 時設定）和 `_retireRecord`（清除）改，兩者和 `DoneSpeaking` 同一條執行緒、順序固定，所以一筆有效紀錄的 `DoneSpeaking` 執行時它一定是 current；不是 current 的只有 skipped（走 `abandon`，不進 `host.retire`）和被丟掉的紀錄（`abandon`；而且它在 `cancel()` 時仍在 `_pending`，`_invalidate` 已把它標成 cancelled）。
  - `not self._recordValid(record)`：四個條件（`cancelled`、`error`、`work`、token）都是單調的；無效的紀錄在 `_retireRecord` 要嘛 withdraw（token），要嘛走 host 的 cancelled／error 分支，三者都不檢查關卡（`segmentHost.py:536-556` 的順序：`not valid` → `error` → `withdrawn` → 關卡）。
  - idle 之後的暫停等待（`:683-686`）：只在「解除暫停」或「紀錄無效」時醒來；醒來後 `:688` 再看一次有效性才 reach，無效就落入上一條。暫停永不解除會卡住 BgThread，但那是 master 既有的等待（`master` 的 `_idlePlayer` 已有同一個 `wait_for`）。
  - 一個請求內換語音（多個 `_NativeTask`、一個 `DoneSpeaking`）、拼字模式、`PitchCommand`／`BreakCommand`：內層 `speak()` 只改送進去的文字和 `_speak` 的次數，`DoneSpeaking` 永遠恰好一個、在最後。`ends=[True, False, True]` 參數釘住多段。
  - 空請求／只有空白／未知命令：內層 `if chunks:` 不成立，沒有 `_NativeTask`，但 `DoneSpeaking` 仍入列 → idle 一次、reach；`lastCallEnded` 預設 `True`，三個關卡都到。審閱者在 scratch 補了四個案例（`()`、`("",)`、`("   ",)`、未知命令），兩個引擎都是三關卡到、`(False, None)`、0 stop、1 idle、1 DONE、沒有缺關卡 log。
  - `terminate()` 在最後 idle 之中：`host.terminate()` → `_invalidate` 標 cancelled → `cancel()` 的 stop 讓 idle 返回 → 暫停等待以「無效」醒來 → 不 reach → `retire` 走 cancelled 分支。scratch 案例：`played_out` 為 `False`、`cancelled=True`、沒有 log、終止正常結束。
  - `_legacyUsed` 只擋 segment admission；control error 只會在 enqueue 時拒絕一般語音，或在 latch 時把 pending 紀錄標成 error（兩者都不會造成「有效卻缺關卡」）。
  - 內層 `speak()` 拋出：沒有 `DoneSpeaking`，`pop` 拿掉 `PLAYED_OUT`，`_Begin`／`_Retire` 照跑，`_retireRecord` reach 兩個關卡、`retire` 通過，呼叫者拿到例外——和 master 相同；`test_inner_speak_failure_after_begin_keeps_todays_outcome` 在 master 的 wrapper 上也通過（審閱者確認），所以它真的是「今天的行為」的釘子。`enqueue` 在 submit 拋出時 `forget` 這筆紀錄（`segmentHost.py:283-286`），之後的 `retire`／`forget` 對不在 pending 的紀錄都有保護，和 master 一樣。
- **idle 失敗的新行為可接受。** 以前：idle 拋出 → BgThread 記一筆「Error running task from queue」→ `_Retire` 照 reach、`retire` 當成功 → 紀錄悄悄過關，DONE 不發。現在：`record_error` 後再拋（`:681-682`）→ BgThread 同一筆 log → `_retireRecord` 因無效不 reach → `retire` 走 error 分支 → `stop_player()` 一次 → `(False, error)`。這和原生呼叫失敗、callback 失敗走的是同一條既有路徑；多的那一次 stop 落在 idle 已經失敗的 player 上：若是裝置失效，音訊早就沒了；若是 idle 早早拋出而音訊還在排，stop 會切掉剩下的，但 DONE 本來就不會發（master 相同），NVDA 要等下一次 cancel 才會往下走，聽感上差別不大。stop 若也失敗，`_stopPlayer` 會 latch control error，所以壞掉的 player 仍會被擋下來。和 segment 的 `drain`（idle 失敗就 latch）相比，一般語音不 latch，是不對稱但更溫和的選擇，見 M3。
- **測試釘住了每個主張。** 審閱者的 10 個突變：7 個被殺（見表），3 個存活——`record is not self._currentRecord`（production 等價，見上）、`finally` 的 `self._player = player` 還原（只影響 `self._player` 是否留著最後一筆紀錄，行為等價）、對 segment 也 `pop`（segment 的 submit 拋出走 `abandon`，沒有 drain，等價）。分支新增或改動的測試在 master 的 wrapper 上：`reaches_every_barrier` 8、`last_call_without_endprocess` 8、token 測試 14、`played_out_waits_for_resume` 2、`cancelled_during_the_final_pause` 4、`kept_done` 2、`failed_final_idle` 2、guard 的 `strategy_barriers_use_shared_or_listed_names[VE|Cerence]` 2，共 42 個全部失敗；`inner_speak_failure` 4 個通過（釘今天的行為）。`played_out_reaches`／`idle_entered` 兩個 helper 讓「idle 返回後、解除暫停前不 reach」是確定性的，不靠時序。
- **VE／Cerence 同步。** 兩個 wrapper 的分支 diff 經 `VE→X`／`Cerence→X` 正規化後逐行相同，只差 `_PROFILE` 字串；`tests/test_vocalizer_drift.py` 沒有 diff。
- **spec 修正（`a17d260`）完整。** 3d-1 的三處（`_VEStrategy` 的關卡、`speak()` 的 `barriers=`、修訂 #2）和 phase 52 的三處（兩張宣告表、host check 段）都在前一輪的刪除線之上再加一層 `Corrected by \`fix/ve-ordinary-played-out\``，內容和實作一致（含「內層 `speak()` 拋出時取消宣告」「idle 拋出時記錄在紀錄上」）。`storage/refactor9.md:458` 原本要求「只評估、不實作」一般語音的 `PLAYED_OUT`，這次是使用者指定要做的，不需要改 storage。
- **限制。** 沒有碰 `driver/*/driver/*`、`driver/sonic/`、Unicode 資料檔；沒有 Neural；wrapper 沒有互相 import；兩個 commit message 都是英文 `fix:`／`docs:` 格式、內文說明原因；沒有 `Co-Authored-By`；`prek` 8 個 hook 全過；`git diff --check` 乾淨。readme 沒改：production 的 `CompletionPolicy` 以預設 `forceUnverifiedDrain=True` 建構（`__init__.py:219`），VE／Cerence 在 NVDA 上一律走 segment，一般 `speak()` 只在測試或直接呼叫 core 時用到，使用者看不到這次改動，不改 readme 是對的。

## Critical

無。

## Important

無。

## Minor

### M1. `record.barriers.pop(PLAYED_OUT)` 沒有預設值：集合裡沒有 `PLAYED_OUT` 時 `KeyError` 會蓋掉內層 `speak()` 的例外（VE `:493`、Cerence `:495`）

production 的一般紀錄永遠用 `_ORDINARY_BARRIERS`，所以今天到不了；但 `host.enqueue(…, barriers=…)` 是公開參數，測試或日後直接呼叫 core 的宿主可以傳自己的集合，這時內層 `speak()` 的例外會變成 `KeyError: 'played_out'`（原例外只剩 `During handling of the above exception` 的鏈），呼叫者看到的錯誤和實際原因不同。

建議修法：`record.barriers.pop(PLAYED_OUT, None)`。順便在註解補一句「pop 在 `_Retire` 入列之前，BgThread 讀 barriers 的兩處（`_retireRecord`、`_idlePlayer`）都在它之後」，把上面那段 happens-before 的推理留在程式碼旁邊，讓日後搬動 `_bgQueue.put(_Retire(...))` 的人知道順序是有意義的。

### M2. 兩個防禦性的判斷沒有測試釘住：`finally` 的 `self._player = player` 還原（VE `:496`、Cerence `:498`）和 `record is not self._currentRecord`（VE `:672`、Cerence `:679`）

突變 M8（拿掉還原）在 `-k VE` 的 197 個測試下存活：之後每次 `_enqueue` 仍會換上新的綁定 proxy，所以行為相同，只是 `self._player` 會一直抓著最後一筆紀錄（和它的 `commands`）。突變 M5（拿掉 `_currentRecord` 判斷）也存活，因為每一筆「不是 current 卻有 `DoneSpeaking`」的紀錄在 production 都同時是無效的（`cancel()` 丟掉的紀錄先被 `_invalidate` 標成 cancelled；latch 時 pending 的紀錄拿到 error；latch 之後的一般 `enqueue` 直接被拒絕）。兩個都該留著，但註解和測試可以更誠實。

建議修法：（1）在 `test_ordinary_speech_reaches_every_barrier` 或 `test_kept_done_…` 加兩行：進入前記下 `shared = env.core._player`，結束後斷言 `env.core._player is shared`（審閱者在 scratch 驗證過，兩個引擎都通過，M8 立刻被殺）。（2）`:670-671` 的註解「a kept DoneSpeaking of a dropped request runs while its record is not the current one」補上「and already invalid」，說明這個判斷是防禦，不是唯一的擋板。

### M3. idle 失敗時一般語音不 latch control error、segment 的 `drain` 會 latch，不對稱沒有寫下理由（VE `:676-682` 對 `:341-358`；Cerence `:683-689` 對 `:343-360`）

`_VEStrategy.drain` 在 idle 失敗時 `record_error` 加 `latch_control_error`（「player 狀態不明，拒絕後續」）；`_idlePlayer` 只 `record_error`，交給 `retire` 的 error 分支做一次 stop，stop 失敗才 latch。審閱者認為這是對的（一次成功的 stop 已把 player 復位，不必拒絕之後的語音；`test_failed_final_idle_fails_the_record` 也釘住 `control_error is None` 且下一句正常），但讀者會問為什麼兩條路徑不同。

建議修法：在 `:679-680` 的註解加一句「Unlike drain, no latch: retire's stop resets the player, and a failed stop latches on its own」；spec 3d-1 的對應句（`:95`）可以同樣補一句。

### M4. commit message 和測試註解把「被保留的 `DoneSpeaking` 在後一筆是 current 時執行」寫成真實風險，但 production 的佇列順序排除了它（`0bd6454` 第二段；`tests/test_vocalizer_segment_drain.py:2266-2269`）

如結論第一點：`_dropQueuedSpeech` 保序、下一筆的 `_Begin` 在 cancel 釋放 admission 之後才入列，所以被保留的 `DoneSpeaking` 一定在下一筆 `_Begin` 之前跑完，`_currentRecord` 當時是 `None`。測試要靠在 native 呼叫裡手動 `done()` 才重現，而且區段註解 `:2172-2174` 說「player／DONE 斷言在 master 的 wrapper 上也通過，除非測試另有說明」，`kept_done` 測試在 master 上 `idles` 差 1（master 會替第三筆 idle 一次），它的註解沒有明說這一點。

建議修法：把 `:2267-2269` 改成「cancel() keeps a dropped request's DoneSpeaking; the BgThread order already runs it before the next _Begin, so run it by hand while a later request is current to prove the binding alone keeps it from idling or reaching for that request (master idles once here)」。commit message 已經在歷史裡，不用改；merge 的交接紀錄可以用同樣的措辭。

## 使用者還沒確認的使用者可見預設

- 一般語音的最後 `idle()` 拋出例外時，紀錄失敗、host 對 player 多做一次 `stop()`（master 只記 log）。這是本分支唯一的 player 行為變化；production 的 NVDA 走 segment，碰不到。
- readme 六個語言都沒改（理由見結論最後一點）。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 完整套件（head `a17d260`，序列） | `cd /workspace/WorldVoice-veplayedout; python3 -m pytest -q tests -p no:cacheprovider`，背景 watchdog 每 2 秒讀 `/proc/meminfo`，MemAvailable < 3 GB 就 kill pytest（腳本 `scratchpad/run_tests.sh`） | **3603 passed／0 skipped**（106.33 s）；watchdog 沒有觸發；`master` `faabf12` collect-only 3589 → +14 ＝ 7 個新測試 × VE／Cerence |
| prek | `prek run --all-files` | 8 個 hook 全 Passed |
| 空白 | `git diff --check`、`git diff 9c3bec4..HEAD --check` | 乾淨 |
| 受保護路徑 | `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' addon/synthDrivers/WorldVoice/driver/sonic/ …script_data.py …unspaced_common_data.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 都沒有輸出 |
| wrapper 互相 import | `grep -n "driver\.\(Cerence\|VE\|RHVoice\|eSpeak\|OneCore\|SAPI5\)\b"` 兩個 wrapper | 無 |
| commit | `git log 9c3bec4..HEAD --format=%B` | 英文 `fix:`／`docs:`，內文說明原因；沒有 `Co-Authored-By` |
| VE／Cerence 同步 | 兩個 wrapper 的 `git diff 9c3bec4..HEAD` 各自 `sed 's/VE/X/g; s/ve2/x2/g'`／`sed 's/Cerence/X/g; s/cerence2/x2/g'` 後 `diff` | 只剩 `_PROFILE` 字串；`git diff 9c3bec4..HEAD -- tests/test_vocalizer_drift.py` 為空 |
| 基準漂移 | `git merge-base master HEAD`、`git log -1 -- docs/superpowers/finish/2026-10-29-set-voice-no-stop.md` | base 是 `9c3bec4`；該檔由 `faabf12` 在分支之後加到 master，不是分支刪的 |
| 還原修正後新測試是否失敗 | scratch 複本 `scratchpad/wt/`（`cp -r`，`ref` symlink）把 `driver/VE/__init__.py`、`driver/Cerence/__init__.py` 換成 `9c3bec4` 的版本，跑 `tests/test_vocalizer_segment_drain.py tests/test_native_strategy_guards.py -k "ordinary or played_out or kept_done or inner_speak or failed_final_idle or token_cancelled or legacy_endprocess or strategy_barriers_use"` | **42 failed／25 passed**（失敗：`reaches_every_barrier` 8、`last_call_without_endprocess` 8、token 測試 14、`played_out_waits_for_resume` 2、`cancelled_during_the_final_pause` 4、`kept_done` 2、`failed_final_idle` 2、guard 2；通過的 25 個是 master 也有的既有測試和 `inner_speak_failure` 4 個——釘今天的行為，預期）；`kept_done` 在 master 的失敗是 `(False, 1) != (False, 0)`（master 替第三筆 idle 一次） |
| 審閱者補的案例（分支，scratch `tests/test_zz_review_scratch.py`） | 空請求 `()`、`("",)`、`("   ",)`、未知命令；`terminate()` 在最後 idle 之中（idle 被擋住、stop 放行）；`self._player` 在請求前後是同一個共用 proxy、`pause(True/False)` 轉到真 player；連續三個請求 | 空請求 8 個案例：三關卡到、`(False, None)`、0 stop、1 idle、1 DONE、無 log；terminate：`played_out` False、`cancelled=True`、無 log、終止完成；identity：通過；三請求：3 idle、三筆三關卡、無 log（兩個引擎都通過） |
| production 是否走一般語音 | `grep -rn "forceUnverifiedDrain\|CompletionPolicy("` | 只有 `__init__.py:219` 以預設 `forceUnverifiedDrain=True` 建構 → NVDA 上一律 segment |
| spec 修正完整性 | 讀 `a17d260` 的 diff，對照實作 | 3d-1 三處、52 三處；敘述與 `_enqueue`／`_idlePlayer` 一致 |

### 突變測試（審閱者自己的 10 個；scratch 複本 `scratchpad/wt/`，只突變 VE，跑 `tests/test_vocalizer_segment_drain.py tests/test_native_strategy_guards.py -k VE -x`（197 個），跑完還原；腳本 `scratchpad/mutants.py`）

| # | 突變 | 結果 |
| --- | --- | --- |
| M1 | 拿掉 `_idlePlayer` 最後的 `host.reach(record, PLAYED_OUT)` | killed（`test_ordinary_speech_reaches_every_barrier`） |
| M2 | 拿掉 `record.barriers.pop(PLAYED_OUT)` | killed（`test_inner_speak_failure_after_begin_keeps_todays_outcome[after-native]`：多了缺關卡 log 和 stop） |
| M3 | idle 失敗時不 `record_error`，只 raise | killed（`test_failed_final_idle_fails_the_record`） |
| M4 | 在暫停等待之前就 reach `PLAYED_OUT` | killed（`test_ordinary_played_out_waits_for_resume_after_the_final_idle`） |
| M5 | 拿掉 `record is not self._currentRecord` | **survived**（production 等價：見 M2 的說明） |
| M6 | `_idlePlayer` 忽略參數、改用 `self._currentRecord` | killed（`test_kept_done_of_a_dropped_request_never_plays_out_another`） |
| M7 | `_enqueue` 不替換 `self._player`（`DoneSpeaking` 拿到共用 proxy） | killed（`test_cancel_retires_inflight_pause_before_fresh_speech`：沒有 idle） |
| M8 | `finally` 不還原 `self._player` | **survived**（行為等價，只多抓著最後一筆紀錄：見 M2） |
| M9 | 暫停等待之後不看有效性、一律 reach | killed（`test_token_cancelled_after_the_last_call_is_withdrawn[token-only]`） |
| M10 | 內層 `speak()` 拋出時對 segment 也 `pop` | **survived**（等價：segment 的 submit 拋出走 `abandon`，沒有 drain） |
