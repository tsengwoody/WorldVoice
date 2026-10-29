# Review：VE／Cerence 一般語音宣告 `AUDIO_FED`、`ENGINE_DONE`，token 取消改由 `SegmentHost.withdraw` 回報

日期：2026-10-29。分支：`fix/ve-ordinary-barriers`（`3a8e87a..ff87a35`，3 個 commit：`513a3e9` host 的 `withdraw`、`3b42e8a` wrapper 宣告關卡、`ff87a35` spec 修正；基準 `master` `3a8e87a`，collect 3537 個測試；分支 collect 3559）。
審閱者：Fable 5.1（唯讀；只新增本檔）。流程：簡化流程（DEVELOPMENT_WORKFLOW.md §5），沒有 spec／plan，依 §3.3 的重點審閱；協調者另外指定六個重點：token 取消的行為中立、`withdraw` 的正確性、誤判（正確的 SDK 卻失敗）、失敗能不能被看見、測試是否真的釘住行為、VE／Cerence 同步與 spec 修正。

依據：

- 程式碼：`addon/synthDrivers/WorldVoice/driver/VE/__init__.py`、`driver/Cerence/__init__.py`、`runtime/segmentHost.py`、`runtime/scheduler.py`（`cancel`／`cancel_current`／`_stop_all`／`_execute`／`_settle`、`CancellationToken`）、`runtime/session.py`（`CancellationView`）、`bridge/engineAdapter.py`（`_speakPlain`）、`bridge/completionPolicies.py`、內層 `driver/VE/driver/__init__.py` 的 `speak`／`cancel`／`DoneSpeaking`／`BgThread`（唯讀）。
- 測試：`tests/test_segment_host.py`、`tests/test_vocalizer_segment_drain.py`、`tests/test_worldvoice_cancel_wrappers.py`、`tests/test_worldvoice_request_manager.py`、`tests/test_native_strategy_guards.py`、`tests/test_vocalizer_drift.py`、`tests/worldvoice_cancel_wrapper_harness.py`。
- 文件：`docs/superpowers/specs/2026-10-03-phase3d1-ve-design.md`、`2026-10-28-phase52-shared-barriers-design.md`、`docs/superpowers/handoff/2026-10-29-ve-endprocess-sdk-test.md`、`storage/refactor9.md` 第 458 列（唯讀）。
- 行號以 head `ff87a35` 為準；路徑省略 `addon/synthDrivers/WorldVoice/`。VE 與 Cerence 的行號相差 2：`_ORDINARY_BARRIERS` 都在 `:49`；`_retireRecord` VE `:509-534`（讀 token 與 withdraw `:523-525`、`host.retire` `:526`），Cerence `:511-536`（`:525-527`、`:528`）；`_idlePlayer` VE `:644`／Cerence `:651`；`_onIndexReached` VE `:753`／Cerence `:760`。

## 結論

**程式碼正確、token 取消對 player 的行為完全中立、可以 merge；merge 前請補兩項（I1 一行 log、I2 把兩個測試加上活的 token），都是便宜的修正。** Critical 0、Important 2、Minor 2。

- **token 取消是行為中立的（審閱者自行驗證，不是採信實作者的說法）。** 我把分支的 6 個 token 測試拆掉所有和關卡／`withdrawn`／`outcome` 有關的斷言，只留 player 的 `fed`／`idles`／`stops` 和 DONE 計數，再加上分支沒釘的兩個窗口（呼叫返回後、`DoneSpeaking` 的 idle 之前取消；兩段文字之間取消），放到 `master` 的 scratch 複本上跑（master 的 wrapper＋master 的 host，沒有 `withdraw`、沒有關卡）：16 個全部通過，數字和分支的斷言逐一相同。唯一不同的是 `host.retire` 回傳的 `OrdinaryOutcome`：master 對「只有 token 取消」的 record 回 `cancelled=False`（host 不知道 token），分支回 `cancelled=True`；兩個 wrapper 都沒有讀這個回傳值（`:526`／`:528` 直接丟掉），所以對 NVDA 沒有任何差別。每個窗口的對照見下面的表。
- **「token 永遠不會回復」成立。** `runtime/scheduler.py:40-93` 的 `CancellationToken` 只有 `_event.set()`，沒有 clear；測試的 `Token`（harness `:258-277`）同樣只設不清。`_recordValid`（VE `:482-491`）的四個條件（`cancelled`、`error`、`work`、token）都是單調的，所以「在兩次 reach 之後才讀 token」（`:523`）保證：讀到未取消 ⇒ 兩次 reach 的檢查當時也未取消 ⇒ 兩個關卡都到了（前提 `lastCallEnded`，它只由最後一次原生呼叫決定）；讀到已取消 ⇒ withdraw，`retire` 不看關卡。中間任何時刻取消都落在這兩種之一，沒有第三種結果。順序若反過來（先讀 token 再 reach）就有誤判的窗口，這一行是整個改動的支點——但沒有測試釘住它（M1）。
- **`SegmentHost.withdraw`／`retire` 的新分支順序正確。** `retire`（`:493-556`）先看 host 的有效性（`cancelled`／`work`）→ 停 player、回已取消；再看 `record.error` → 停 player（除非已 latch control error）、回錯誤；然後才看 `withdrawn`（`:546-547`）→ 回已取消、不停 player；最後才是關卡檢查。所以 host 的 cancel、已記錄的錯誤、control error 都保持 master 的路徑（含停止次數），只有「host 看來有效、沒有錯誤、token 已取消」這一種情況從「可能缺關卡」變成「已取消」。`withdraw`（`:473-486`）只設旗標、拒絕 segment record（segment 的 token 經由 `work.is_valid()` 早就被 host 看見，不需要也不該走這條）、NVDA-free、和 `forget`／pending 清單的互動不變（withdrawn 的 record 仍有效、仍在 pending，直到 `_retireRecord:528` 的 `forget`；期間的 host cancel 仍會標記它，`test_a_withdrawn_record_stays_cancellable_until_forgotten` 釘住）。`terminate`／`reset` 都走 `_invalidate` → `record.cancelled` → 比 `withdrawn` 更早的分支。API 是最小的：一個布林、一個方法、`retire` 兩行；用 `retire(record, withdrawn=True)` 的關鍵字參數也行，但現在的寫法把「只能在 retire 之前、只能是一般 record」講清楚了，可接受。
- **找不到正確的 SDK 卻讓一般 record 失敗的路徑。** 逐條核對（都和 segment 共用同一段 `_retireRecord`，上一輪 review 已驗證過 segment 的版本）：
  - 一個請求內換語音：每段 `_NativeTask` 帶自己的 instance，`_callbackAdmission` 以 `call.instance` 比對，`lastCallEnded` 由最後一次呼叫覆寫，中間呼叫的尾端留在 Sonic／`_feedBuf` 等下一次 `ENDPROCESS`；`middle-call-unended` 參數釘住。
  - 拼字模式、`PitchCommand`、`BreakCommand`：只改送進去的文字，不改訊息序列。
  - 空請求／沒有原生呼叫（只有空字串、只有語言切換）：內層 `speak` 的 `if chunks:` 不成立，沒有 `_NativeTask`，`lastCallEnded` 預設 `True`，兩個關卡都到；我在 scratch 加了 `("",)`／`("   ",)` 兩個案例，兩個引擎都是 `(cancelled=False, error=None)`、0 stop、1 idle、1 DONE。
  - 暫停／恢復：`_retireRecord:518-519` 等 `_pauses == 0` 才讀 token 和 retire；pause 失敗走 `record_error`＋latch，是 master 既有的錯誤路徑。
  - `cancel()` 保留一般語音的 `DoneSpeaking`：`_dropQueuedSpeech` 沒改；被丟掉的 record 走 `abandon`（`skipped`），`_retireRecord` 的新程式碼在 `if not record.native.skipped:` 裡面，碰不到。
  - legacy `ENDPROCESS` 分支（`:222-228`）：只在 `_recordValid` 為假時進入，此時 record 不是被 host 取消就是 token 已取消（→ withdraw）或已有錯誤，三種都不檢查關卡；`test_legacy_endprocess_after_token_cancel_does_not_count` 釘住。`_legacyUsed` 只擋 segment 的 admission，和一般語音的關卡無關。
  - 原生呼叫丟例外或有效時回 `USERSTOP`：`record_error`，是 master 既有的錯誤路徑（含停止）。
- **真的缺 `ENDPROCESS` 時會發生什麼。** `DoneSpeaking` 在 `_Retire` 之前跑：`_idlePlayer` 已 `idle()`（音訊播完）、`_onIndexReached(None)` 已發 DONE。接著 `retire` 合成缺關卡的錯誤、`stop_player()`——對一個已經 idle 的 player 做 stop，什麼都不會丟掉，NVDA 使用者聽不出差別；兩個 wrapper 又丟掉 `outcome`，所以 log 裡也沒有任何痕跡。這就是 I1。另外要說明：production 的 `CompletionPolicy(nvdaVersion=…, logger=…)`（`__init__.py:219`）用預設 `forceUnverifiedDrain=True`，VE／Cerence 的 `get_segment_drain_support` 永遠回 `supported=True`，所以 NVDA 上一律走 `speak_segment`；一般 `speak()` 只在 `forceUnverifiedDrain=False`（測試）或直接呼叫 core 時才會用到。這降低了 I1 的實際衝擊，但不改變「偵測」在這條路徑上目前是看不見的這個事實。
- **測試。** 分支的 24 個新測試在 master 的程式碼上全部失敗（24 failed／26 passed，見驗證表），分支上全綠；改過的既有 stub（`test_speak_returns_before_native_synthesis`、`test_settings_apply_in_call_order_with_speech`、`test_engine_settings_variant_waits_for_running_speech`、`test_cancelled_request_drops_index_and_done_notifications` 的 live 分支、`test_failed_sonic_init_is_not_retried_on_next_speak`、`speak_live_request`、`test_direct_wrapper_stop_mid_speech_lets_next_segment_run` 的第二段）都只是讓「成功的 SDK 呼叫」的替身多送 SDK 本來就會送的 `ENDPROCESS`；這些測試的斷言都和 stop 次數無關（`speak_live_request` 看 `idles == 1`），不送的話只會多一次對 idle player 的 stop、仍然會過，所以改了沒有削弱任何證明，只是讓 stub 忠實。其他沒改的 stub 要嘛會 `core.cancel()`（record 被 host 取消，不看關卡），要嘛用 `emit_audio`（本來就送 `ENDPROCESS`）。審閱者的 15 個突變：13 個被分支自己的測試殺掉，2 個存活（M1、I2），兩個都能用確定性的測試殺掉，我已寫出並驗證。
- **VE／Cerence 同步。** Cerence 換名後和 VE `diff`，只剩 drift 測試原本允許的五處（`_PROFILE`、`szValue`／`ulMrkId`、admission 的 `isinstance`、`variants` 的 try、錯誤訊息的斷行）；`tests/test_vocalizer_drift.py` 沒有 diff；突變 W7（只有 Cerence 保留 `frozenset()`）被 `test_ordinary_speech_reaches_audio_fed_and_engine_done[Cerence-one-call]` 殺掉（guard 測試也會抓）。
- **spec 修正（`ff87a35`）完整、正確。** 3d-1 spec 的三處（`_VEStrategy` 的「一般語音不設 barrier」`:95`、`speak()` 的 `barriers=frozenset()` `:102`、修訂 #2 `:158-159`）和 phase 52 spec 的三處（兩張宣告表 `:98`、`:152`、host check 的「VE's is empty」`:154`）都用刪除線保留舊文並標 `Corrected by \`fix/ve-ordinary-barriers\``。phase 52 spec `:24` 的 `_ORDINARY_BARRIERS = frozenset()` 是「phase 52 之前的現況」表，是歷史，不用改；3d-2（Cerence）spec 沒有對應的句子；phase 49／50／51 spec 也沒有。兩份 finish review（phase 52、endprocess）提到空集合，是審閱當時的紀錄，§5.7 只要求改 spec，不用動。
- **`storage/refactor9.md:458` 要求「順便評估一般語音能否也證明 `PLAYED_OUT`，只回報不實作」**，實作者的回報應涵蓋；審閱者的評估：可行且很小——`_idlePlayer`（`:644-658`）在 `_Retire` 之前、同一條 BgThread 上 `idle()` 並等 pause 解除，在它之後、record 仍有效時 `host.reach(record, PLAYED_OUT)` 即可；token 取消的 record 不會進 `_idlePlayer`（`_recordValid` 擋住），而會被 withdraw，所以不會誤判。但「idle 之後、reach 之前」被 host 取消的窗口要和 `wait_playback_drained` 的 segment 版本一樣靠 `_recordValid` 擋，而且要先問使用者要不要讓一般語音多一個關卡；本分支不做是對的。
- **限制。** 沒有碰 `driver/*/driver/*`、`driver/sonic/`、Unicode 資料檔；沒有 Neural；wrapper 沒有互相 import；三個 commit message 都是英文 `feat:`／`fix:`／`docs:` 格式、內文說明原因；沒有 `Co-Authored-By`；`prek` 8 個 hook 全過；`git diff --check` 乾淨。

## Critical

無。

## Important

### I1. 一般語音缺 `engine_done` 的失敗沒有人看得見：wrapper 丟掉 `outcome`，host 只對已經 idle 的 player 做一次 stop，不寫 log（VE `:526`、Cerence `:528`；`runtime/segmentHost.py:548-556`）

`3b42e8a` 的目的是讓「最後一次呼叫沒有被准入的 `ENDPROCESS`」在一般語音上也被判為失敗。分支上這個失敗的全部後果是：`retire` 合成 `RuntimeError("VE synthesis retired without its engine_done barriers")`、呼叫 `stop_player()`、回傳 `OrdinaryOutcome(False, error)`。但（1）`DoneSpeaking` 已在 `_Retire` 之前 `idle()`，這次 stop 對一個空的 player 不丟任何音訊，使用者聽不到；（2）兩個 wrapper 的 `_retireRecord` 不接 `host.retire` 的回傳值；（3）`retire` 本身對合成的錯誤不寫 log（已記錄的錯誤在它們發生的地方都有 `log.error`：callback 失敗 `:287`、原生呼叫失敗 `:584`；只有這個合成的錯誤沒有）。其他引擎也沒有在一般語音上記錄 `outcome.error`（eSpeak 只 `markNotSpeaking`、`driver/Espeak/__init__.py:209-213`；OneCore `:368`、RHVoice `:255`、SAPI5 `:679` 都不看），所以這是 host 層的缺口，不只是 VE 的。

失敗情境：某個 SDK 版本或某種片段在一般語音模式（`forceUnverifiedDrain=False`，或日後直接呼叫 core 的宿主）下不送 `ENDPROCESS`，Sonic 的尾端永遠不會餵出去、每句話的結尾被吃掉；使用者回報「句尾少字」，log 裡什麼都沒有，和 master 的「靜默成功」一樣難查——這正是這次改動要消除的狀況。production 的 NVDA 一律走 segment（DRAIN 強制啟用），所以今天不會發生在使用者身上，但分支的用意（偵測）在這條路徑上等於沒有兌現。

建議修法（一行，NVDA-free，涵蓋六個引擎）：在 `SegmentHost.retire` 合成缺關卡錯誤的地方（`:548-549`）加 `log.error("%s ordinary speech retired without its %s barriers", self.engine, ", ".join(record.missing_barriers()))`（模組的 `log` 是 `logging.getLogger(__name__)`，NVDA 上會進 NVDA log）。測試：`tests/test_segment_host.py::test_ordinary_record_outcomes[missing]` 加 `caplog`，斷言一筆 ERROR 含 `returned`／`played_out`；`test_withdrawn_ordinary_record_outcomes[missing]` 斷言沒有 log（withdrawn 不是失敗）。不建議改在 wrapper 裡：那要在 VE／Cerence 各加一段「`outcome.error` 是不是 retire 之前就記錄過的」判斷，而且其他四個引擎仍然不記。

### I2. 正確路徑和失敗偵測的測試都沒有帶活的 token，而 production 每個一般請求都帶；拿掉 `.is_cancelled()` 的突變在整個套件下存活（`tests/test_vocalizer_segment_drain.py:1938-1975`）

`bridge/engineAdapter.py:34-35`：VE／Cerence 的 `extraCapabilities` 含 `"cancellationToken"`，所以 adapter 永遠以 `speak(commands, cancellationToken=token)` 呼叫；production 不存在 `token is None` 的一般請求。但 `test_ordinary_speech_reaches_audio_fed_and_engine_done` 和 `test_ordinary_last_call_without_endprocess_fails_the_record` 都用 `speak_ordinary_pieces(..., native)`，`token=None`。於是突變 W6——`:524` 的 `if token is not None and token.is_cancelled():` 改成 `if token is not None:`——在 `tests/test_vocalizer_segment_drain.py`、`test_native_strategy_guards.py`、`test_vocalizer_drift.py`、`test_worldvoice_cancel_wrappers.py`、`test_worldvoice_request_manager.py` 共 328 個測試下存活（`test_worldvoice_cancel_wrappers.py` 裡帶 token 的測試只看 index／DONE／feed，不看 outcome）。在這個突變下，每個 production 形狀的一般請求都被 withdraw，`retire` 回「已取消」、不檢查關卡：偵測整個失效，而且因為 I1，沒有任何徵兆。

失敗情境：日後整理 `_retireRecord`，把條件誤改成「有 token 就 withdraw」或把 `token.is_cancelled()` 換成別的屬性，測試全綠，一般語音的關卡形同不存在。

建議修法：兩個測試各加 `@pytest.mark.parametrize("token", [None, "live"])`（或直接改成一律 `Token()`——`None` 的形狀只有直接呼叫 core 的舊路徑會用到，留一個案例即可），在 `speak_ordinary_pieces` 傳入 `Token()`（不取消），並多斷言 `record.withdrawn is False`。我在 scratch 寫了 `test_live_token_correct_run_is_not_cancelled`（斷言 `withdrawn is False`、關卡都到、`(False, None)`、`(idles, stops) == (1, 0)`、1 個 DONE）和 `test_live_token_missing_endprocess_fails`（`withdrawn is False`、`"engine_done" in str(outcome.error)`、`(1, 1)`），未突變的分支兩個引擎都通過，W6 立刻被前者殺掉。

## Minor

### M1. 「token 要在兩次 reach 之後才讀」是整個設計的支點，註解寫了，測試沒釘：把讀取搬到 reach 之前的突變存活（VE `:520-525`、Cerence `:522-527`）

突變 W3b：在 `AUDIO_FED` 的 reach 之前先 `_cancelled = token.is_cancelled()`，`:524` 改用這個早讀的值。分支的測試全部通過（328 個），因為沒有測試在「第一次 reach 之後、讀 token 之前」取消 token。這個窗口在 NVDA 上是真的：scheduler 的 `cancel()` 在 `_cancel_request_locked` 裡 `token.cancel()`（`scheduler.py:391`）和 BgThread 的 `_retireRecord` 沒有任何同步。早讀的後果：`AUDIO_FED` 到了、`ENGINE_DONE` 因 `_recordValid` 為假沒到、沒有 withdraw → 合成缺關卡錯誤 → 多一次 `stop_player()`——正是 3d-1 決策 #2 當初要避免的那一次多餘的 stop。

建議修法（確定性的測試，不靠時序）：monkeypatch `segment_host(env.core).reach`，在 `barrier == "audio_fed"` 的 reach 完成後 `token.cancel()`；斷言 `record.barriers == {"audio_fed": True, "engine_done": False}`、`record.withdrawn`、`(outcome.cancelled, outcome.error) == (True, None)`、`(player.fed, player.idles, player.stops) == ([b"pcm"], 1, 0)`、`len(env.dones) == 1`（DONE 由 `DoneSpeaking` 在 token 取消之前發出——我第一版寫成 `env.dones == []`，在未突變的分支上失敗，修正後兩個引擎都通過）。這個測試殺掉 W3b。可以放在 `test_token_cancelled_after_the_last_call_is_withdrawn` 旁邊，並把 `:520-522` 的註解指向它。

### M2. 新測試的註解把「如以前一樣」寫成斷言的理由，但沒有說明讀者要怎麼驗證（`tests/test_vocalizer_segment_drain.py:1899-1903`、`:2072`、`:2084-2085`）

檔案頂部和 `token-then-cancel` 的註解說「player 的行為和以前一樣」，commit message 也說「the new token tests pin it and their player/DONE assertions also pass on the previous wrapper」。這是對的（我重做了一次，見驗證表），但「以前」的證據只存在於實作者的紀錄裡。建議在 `:1899-1903` 的註解加一句：這些測試的 player／DONE 斷言在 `master` 的 wrapper＋host 上也通過，只有 `withdrawn`／`barriers`／`outcome` 是新的——讓日後改動 wrapper 的人知道要把哪些斷言當成「不可變」。順便：`test_token_cancelled_after_the_last_call_is_withdrawn` 的 `# The scheduler cancels the request's token, then the playback (core.cancel()).` 可以補上出處 `scheduler.py:386-395, 419-441`，因為這是「NVDA 上 token 取消永遠伴隨 `core.cancel()`」的依據，也是為什麼「只有 token」的窗口在 NVDA 上只會短暫存在。

## token 取消：每個窗口 master 與分支的對照（一般語音，一段文字，SDK 正常送 `ENDPROCESS`）

「stop」只算 `_realPlayer.stop()` 的次數（來源標在括號內）；「idle」是 `_realPlayer.idle()`；DONE 是 `synthDoneSpeaking`。每一列的 master 數字都在 master 的 scratch 複本上跑過（見驗證表「行為中立」列）。

| 取消的時間點 | master：stop／idle／DONE，`retire` 回傳 | 分支：stop／idle／DONE，`retire` 回傳 | 差異 | 釘住的測試 |
| --- | --- | --- | --- | --- |
| `_Begin` 之前（含 adapter 已擋掉的情況） | 0／0／0；`abandon`，不 retire | 同左 | 無（新程式碼在 `if not skipped` 裡） | `test_token_cancelled_before_begin_never_retires` |
| `_Begin` 之後、原生呼叫之前 | 0／0／0；`(False, None)` | 0／0／0；withdrawn，`(True, None)` | 只有回傳值，wrapper 不讀 | `test_token_cancelled_before_the_native_call_is_withdrawn` |
| callback 的 `OUTBUFDONE` 中（feed 之後） | 1（callback 的 `finally`）／0／0；`ENDPROCESS` 走 legacy 分支回 `OK`；`(False, None)` | 1／0／0；`lastCallEnded=False`，withdrawn，`(True, None)` | 只有回傳值 | `test_token_cancelled_mid_feed_keeps_only_the_callback_stop` |
| 呼叫內、`ENDPROCESS` 之前（legacy 分支收到 `ENDPROCESS`） | 0／0／0；`(False, None)` | 0／0／0；withdrawn，`(True, None)` | 只有回傳值 | `test_legacy_endprocess_after_token_cancel_does_not_count` |
| 呼叫返回後、`DoneSpeaking` 的 idle 之前（審閱者補的窗口） | 0／0／0；`(False, None)` | 0／0／0；withdrawn，`(True, None)` | 只有回傳值 | scratch `test_token_cancelled_after_call_before_idle` |
| 兩段文字之間（第一次呼叫之後；審閱者補的窗口） | 0／0／0；第二段不呼叫；`(False, None)` | 同左；withdrawn，`(True, None)` | 只有回傳值 | scratch `test_token_cancelled_between_calls` |
| `DoneSpeaking` 的 `idle()` 之中（最後一次呼叫之後） | 0／1／0（`_onIndexReached(None)` 看到 token 已取消）；`(False, None)` | 0／1／0；兩個 reach 都被 `_recordValid` 擋住，withdrawn，`(True, None)` | 只有回傳值 | `test_token_cancelled_after_the_last_call_is_withdrawn[token-only]` |
| 第一次 reach 之後、讀 token 之前（審閱者補的窗口） | 0／1／1；`(False, None)` | 0／1／1；`audio_fed` 到、`engine_done` 沒到，withdrawn，`(True, None)` | 只有回傳值（讀 token 若搬到 reach 之前就會多一次 stop：M1） | scratch `test_token_cancelled_during_the_audio_fed_reach_is_withdrawn` |
| 讀 token 之後（`retire` 之前或之後） | 0／1／1；`(False, None)` | 0／1／1；兩個關卡都到，`(False, None)` | 無 | 由單調性推得（兩次 reach 時未取消） |
| token 取消後接著 `core.cancel()`（scheduler 的順序） | 2（cancel 的 `:703`＋`retire` 的 cancelled 路徑 `:541`）／1／0；`(True, None)` | 2／1／0；`not valid` 分支先於 `withdrawn`，`(True, None)` | 無 | `test_token_cancelled_after_the_last_call_is_withdrawn[token-then-cancel]`、`test_withdrawn_ordinary_record_outcomes[cancelled]` |
| token 取消且 record 有已記錄的錯誤 | 1（`retire` 的錯誤路徑）／–／–；`(False, error)` | 同左；`error` 分支先於 `withdrawn` | 無 | `test_withdrawn_ordinary_record_outcomes[error]` |

## 使用者還沒確認的使用者可見預設

- 沒有新的使用者可見預設。token 取消時 player 的行為和 master 相同（上表）；新的失敗路徑（缺 `engine_done`）只在一般語音模式出現，而 NVDA 上 VE／Cerence 一律走 segment，且失敗的唯一動作是對已 idle 的 player 做 stop，聽不出來（I1 是要讓它被看見，不是要改變聲音）。
- 未打包、未在 Windows 驗證（簡化流程）。`storage/refactor9.md:458` 約定的 Windows 手動項目：NVDA 上 token 取消一般語音（例如 VE 在 `forceUnverifiedDrain=False` 下連續按方向鍵）時聲音停止的方式不變——程式碼和測試都說不變，但實際音訊裝置沒有驗證。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 完整套件（head `ff87a35`，序列） | `cd /workspace/WorldVoice-veordinary; python3 -m pytest -q tests`，背景 watchdog 每 2 秒讀 `/proc/meminfo`，MemAvailable < 3 GB 就 kill pytest（腳本 `scratchpad/run_tests.sh`） | **3559 passed／0 skipped**（103.99 s）；watchdog 沒有觸發；`master` collect-only 3537 → +22 ＝ host 6＋drain 每引擎 −2＋10 |
| prek | `prek run --all-files` | 8 個 hook 全 Passed |
| 空白 | `git diff --check master..HEAD` | 乾淨 |
| 受保護路徑 | `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' addon/synthDrivers/WorldVoice/driver/sonic/ …script_data.py …unspaced_common_data.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 都沒有輸出 |
| wrapper 互相 import | `grep` 兩個 wrapper 的 `from synthDrivers.WorldVoice.driver.<其他引擎>`／`from ..<其他引擎>` | 無 |
| commit | `git log -3 --format=%B` | 英文 `feat:`／`fix:`／`docs:`，內文說明原因；沒有 `Co-Authored-By` |
| VE／Cerence 同步 | `sed 's/Cerence/VE/g; s/cerence/vocalizer/g; s/ttsapi/ve2/g' Cerence/__init__.py \| diff - VE/__init__.py`；`git diff master..HEAD -- tests/test_vocalizer_drift.py` | 只剩五處原本允許的差異；drift 測試無 diff |
| 行為中立（master 上重跑 token 測試） | scratch 複本 `scratchpad/base/`（`git archive master`，`ref` symlink）加 `test_neutrality_scratch.py`：分支 6 個 token 測試只留 `fed`／`idles`／`stops`／DONE／`calls`／`results` 斷言，另加「呼叫返回後 idle 之前」「兩段之間」兩個窗口；`pytest -q -s` | **16 passed**（8 案例 × VE／Cerence）；數字與分支斷言逐一相同；master 的 `retire` 回傳：只有 token 取消 → `(False, None)`，token＋`cancel()` → `(True, None)` |
| 還原修正後新測試是否失敗 | 把分支的 `test_vocalizer_segment_drain.py`、`test_segment_host.py` 複製到 `base/tests/`，`-k "ordinary or token_cancelled or legacy_endprocess or withdraw"` | **24 failed／26 passed**：4 個 `reaches_audio_fed_and_engine_done`、4 個 `last_call_without_endprocess_fails`、10 個 token 測試（`withdrawn` 屬性不存在或 outcome 不同）、6 個 host 測試（沒有 `withdraw`）；通過的 26 個是 master 也有的既有測試和 `before_begin_never_retires`（兩邊行為相同） |
| 審閱者補的測試（分支） | `scratchpad/mut/tests/test_reviewer_extra.py`（活 token 的正確路徑、活 token 缺 `ENDPROCESS`、第一次 reach 中取消、空／空白請求），複本留在 `scratchpad/test_reviewer_extra.py` | **10 passed**（5 × VE／Cerence）；空／空白請求：關卡都到、`(False, None)`、0 stop、1 idle、1 DONE |
| production 是否走一般語音 | `grep -rn "CompletionPolicy("`、`forceUnverifiedDrain` | 只有 `__init__.py:219` 以預設 `forceUnverifiedDrain=True` 建構；VE／Cerence 的 `get_segment_drain_support` 永遠 `supported=True` → NVDA 上一律 DRAIN／`speak_segment`；一般 `speak()` 只在測試或直接呼叫 core 時使用 |
| spec 修正完整性 | `grep` 3d-1、3d-2、49–52 spec 與 finish／handoff 文件 | 3d-1 三處、52 三處都已修正；52 的 `:24` 是歷史現況表；3d-2 與 49–51 沒有對應句；兩份 finish review 是歷史紀錄，不用改 |

### 突變測試（審閱者自己的 15 個；scratch 複本 `scratchpad/mut/`（`git archive HEAD`），VE 與 Cerence 同時突變，`PYTHONDONTWRITEBYTECODE=1 pytest -q -x -p no:cacheprovider`，每次先清 `__pycache__`，跑完還原；腳本 `scratchpad/mutrun.py`。W 系列跑 `test_vocalizer_segment_drain.py`、`test_native_strategy_guards.py`、`test_vocalizer_drift.py`、`test_worldvoice_cancel_wrappers.py`、`test_worldvoice_request_manager.py`（328 個）；H 系列跑 `test_segment_host.py`＋drain）

| # | 突變 | 結果 |
| --- | --- | --- |
| W1 | 拿掉 `host.withdraw(record)` | killed（`test_token_cancelled_before_the_native_call_is_withdrawn`） |
| W2 | `host.retire` 之後才 withdraw | killed（同上） |
| W3b | token 在兩次 reach 之前讀、用早讀的值決定 withdraw | **存活**（328 passed）→ M1；加上 scratch 的「第一次 reach 中取消」測試後 killed |
| W4 | `_ORDINARY_BARRIERS = {AUDIO_FED}` | killed（`test_ordinary_speech_reaches_audio_fed_and_engine_done[VE-one-call]`，guard 也會抓） |
| W5 | `_ORDINARY_BARRIERS = frozenset()`（master） | killed（同上） |
| W6 | `if token is not None:`（有 token 就 withdraw） | **存活**（328 passed）→ I2；加上 scratch 的活 token 正確路徑測試後 killed |
| W7 | 只有 Cerence 保留 `frozenset()` | killed（`[Cerence-one-call]`；drift 與 guard 也會抓） |
| H1 | `retire` 的 `withdrawn` 分支搬到 `not valid` 之前（withdrawn 壓過 host cancel） | killed（`test_withdrawn_ordinary_record_outcomes[error]`；`[cancelled]` 與 `token-then-cancel` 也會抓） |
| H2 | `withdrawn` 分支搬到 `error = record.error` 之前 | killed（`test_withdrawn_ordinary_record_outcomes[error]`） |
| H3 | `withdraw` 不拒絕 segment record | killed（`test_a_segment_record_cannot_be_withdrawn`） |
| H4 | withdrawn 分支回 `cancelled=False` | killed（`test_withdrawn_ordinary_record_outcomes[missing]`） |
| H5 | withdrawn 分支也 `stop_player()` | killed（同上） |
| H6 | `withdraw` 不設旗標 | killed（同上） |
| H7 | 拿掉 withdrawn 分支（關卡檢查勝出） | killed（同上） |
| W3 | （無效突變：早讀但仍用晚讀的值；等價） | 存活，不計 |

## 修正記錄

日期：2026-10-29。修正者：Opus 5.5（DEVELOPMENT_WORKFLOW.md §3.4）。四項都修，每項先寫測試、看它失敗，再修正。突變測試在 scratch 複本（`git archive HEAD`，`ref` symlink）上做，VE 與 Cerence 同時突變，`PYTHONDONTWRITEBYTECODE=1 pytest -p no:cacheprovider`，每次先清 `__pycache__`，跑完還原成未突變的複本。

### I1 — `6acda3d` `fix: log an ordinary record retired without its barriers`

- 修法：照 review 的建議，在 `SegmentHost.retire` 合成缺關卡錯誤的地方加一筆 `log.error("%s ordinary speech retired without its %s barriers", self.engine, ", ".join(record.missing_barriers()))`（模組既有的 `log`）。不改 `outcome`、不改 stop 次數。
- 測試：`test_segment_host.py::test_ordinary_record_outcomes` 加 `caplog`，`[missing]` 斷言 host logger 恰好一筆 ERROR，含引擎名、`returned`、`played_out`；其他三種情況斷言沒有 ERROR。`test_withdrawn_ordinary_record_outcomes` 四種情況都斷言 `retire` 不寫 ERROR（withdrawn 不是失敗）。`test_vocalizer_segment_drain.py` 的正確路徑測試斷言沒有這筆 log，缺 `ENDPROCESS` 的測試斷言恰好一筆、含引擎名與 `engine_done`。
- 紅／綠：把 `segmentHost.py` 暫時換回 `7692ee4` 的版本，新斷言 5 個失敗（host `[missing]`＋VE／Cerence 各 2 個缺 `ENDPROCESS` 案例）；換回修正後全過。
- 不增加 log 雜訊：用 scratch pytest plugin（root logger 上的 handler，記下每個寫出這筆訊息的測試）跑完整套件。最終 head 上寫出這筆 log 的只有：host 的 `test_ordinary_record_outcomes[missing]`、VE／Cerence 的 8 個 `test_ordinary_last_call_without_endprocess_fails_the_record` 案例（都是刻意缺關卡），以及 `test_retire_waits_for_admitted_consumers[0]`／`[0.1]`（fake strategy 刻意不 reach 就 retire 一般 record，測的是 consumer 等待，不是引擎的正常執行）。eSpeak、RHVoice、SAPI5、OneCore、VE、Cerence 的一般語音正確執行沒有任何一個測試走到這個分支。

### I2 — `794ac80` `test: run the VE/Cerence ordinary barrier tests with a live token`

- 修法：`test_ordinary_speech_reaches_audio_fed_and_engine_done` 和 `test_ordinary_last_call_without_endprocess_fails_the_record` 加 `@pytest.mark.parametrize("token", ["live-token", "no-token"])`，`live-token` 傳未取消的 `Token()`，兩個測試都多斷言 `record.withdrawn is False`；缺 `ENDPROCESS` 測試後半的第二個請求也用同一種 token，並斷言它沒有被 withdraw。
- 突變 W6（`if token is not None and token.is_cancelled():` → `if token is not None:`，VE＋Cerence）：
  - 修正前的測試檔（`6acda3d`）：`test_vocalizer_segment_drain.py`、`test_native_strategy_guards.py`、`test_vocalizer_drift.py`、`test_worldvoice_cancel_wrappers.py`、`test_worldvoice_request_manager.py` **328 passed**——存活，和 review 一致。
  - 修正後：**8 failed**（兩個測試 × 兩種 `ends` × VE／Cerence 的全部 `live-token` 案例），`no-token` 案例照常通過——**killed**。
  - 未突變的複本：`test_vocalizer_segment_drain.py` 207 passed。

### M1 — `05ee8cf` `test: pin reading the token after the VE/Cerence ordinary reaches`

- 修法：新增 `test_token_cancelled_during_the_audio_fed_reach_is_withdrawn`（monkeypatch `segment_host(env.core).reach`，`audio_fed` 的 reach 完成後 `token.cancel()`），斷言 `record.barriers == {"audio_fed": True, "engine_done": False}`、`record.withdrawn`、`(outcome.cancelled, outcome.error) == (True, None)`、`(player.fed, player.idles, player.stops) == ([b"pcm"], 1, 0)`、`len(env.dones) == 1`。VE 與 Cerence 的 `_retireRecord` 註解加一行指向這個測試（兩邊同一行，`ALLOWED` 不變）。
- 突變 W3b（在 `AUDIO_FED` 的 reach 之前先讀 `_early = token.is_cancelled()`，withdraw 改用 `_early`，VE＋Cerence）：同上五個檔案 **2 failed／336 passed**，失敗的正是新測試的 `[VE]`、`[Cerence]`（`record.withdrawn` 為 False，記錄成缺 `engine_done`）——**killed**；其他 336 個在突變下全過，表示只有這個測試釘住順序。未突變的分支上新測試 2 passed。

### M2 — `206ec97` `test: say what the VE/Cerence token tests' neutrality rests on`

- 修法（只改註解，沒有可失敗的測試）：`test_vocalizer_segment_drain.py` 一般語音段落的開頭註解補上「token 測試的 player（`fed`／`idles`／`stops`）與 DONE 斷言在 `master` 的 wrapper＋host 上也通過（本 review 已驗證），只有 `withdrawn`／`barriers`／`retire` 的回傳是新的，改 wrapper 時前者要保持不變」；`token-then-cancel` 的註解補上出處 `runtime/scheduler.py` `_cancel_request_locked`（`:386-395`）在 `cancel()` 裡，之後是 `_stop_all`（`:419-441`），行號已在本分支核對。

### 驗證（最後一個修正 commit `206ec97` 之後，DEVELOPMENT_WORKFLOW.md §7）

| 項目 | 結果 |
| --- | --- |
| `python3 -m pytest -q tests`（序列，watchdog：MemAvailable < 3 GB 就 kill） | **3569 passed／0 skipped**（105.10 s）；watchdog 沒有觸發；3559 ＋ I2 的 8 個 `live-token` 案例 ＋ M1 的 2 個 |
| `prek run --all-files` | 8 個 hook 全 Passed |
| `git diff --check master..HEAD`、`git diff --check` | 乾淨 |
| 受保護路徑（`driver/*/driver/*`、`driver/sonic/`、兩個 Unicode 資料檔；`git ls-files …/driver/Neural`） | 都沒有輸出 |
| VE／Cerence 同步 | Cerence 換名後和 VE 的 `diff` 與 `7692ee4` 時完全相同；`tests/test_vocalizer_drift.py` 沒有 diff |

依 §3.4，本輪有 Important（I1、I2），修正的 diff（`7692ee4..` 之後的 commit）待協調者另派 Opus 5.5 做修正 review。

### 修正 review（Opus 5.5 xHigh，2026-10-29）

審閱者：Opus 5.5（effort xHigh；DEVELOPMENT_WORKFLOW.md §3.4 的修正 review）。範圍：只看修正的 diff `7692ee4..1ce666c`（`6acda3d` I1、`794ac80` I2、`05ee8cf` M1、`206ec97` M2、`1ce666c` 修正記錄），對照上面的 I1、I2、M1、M2 與修正記錄。唯讀，只新增本節。突變都在 scratch 複本（`git archive HEAD`，`ref` symlink）上做，VE 與 Cerence 同時突變，`PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider`，每次前後清 `__pycache__`、跑完還原（腳本 `scratchpad/fixreview/mutrun.py`）；worktree 的追蹤檔沒有動過，沒有用 `git stash`。行號以 head `1ce666c` 為準，路徑省略 `addon/synthDrivers/WorldVoice/`。

**結論：四項都真的修好，可以 merge。** 新的 Critical 0、Important 0、Minor 1（N1，可選，不擋 merge）。沒有新的 Critical／Important，依 §3.4 不需要再一輪修正 review。

#### 逐項判定

- **I1 — 已修好。**
  - 程式碼：`runtime/segmentHost.py:552-556` 的 `log.error` 只在合成缺關卡錯誤的分支（`:548-549`）裡，排在 host cancel（`:536-544`）、已記錄的錯誤、`withdrawn`（`:546-547`）之後，所以 host 取消、已有錯誤、被 withdraw 的 record 都不會寫；呼叫時沒有持有 `_condition`，不影響鎖順序。diff 只加一個 log 呼叫，`outcome` 和 `stop_player` 的條件與次數都沒變（完整套件裡所有 stop 次數的斷言照常通過）。
  - 措辭與層級：用模組既有的 stdlib `log`，維持 NVDA-free；NVDA 的 `logHandler` 把 handler 掛在 root（`ref/nvda/source/logHandler.py:673`），所以在 NVDA 上會寫進 NVDA log。ERROR 和同檔其他失敗（`:543`、`:561`）一致；訊息「`VE ordinary speech retired without its engine_done barriers`」對應 `_missing_barriers_error` 的 `RuntimeError` 文字，有引擎名和缺的關卡。
  - 測試抓得到：在 head 拿掉這筆 log（還原 I1），`test_segment_host.py`＋`test_vocalizer_segment_drain.py` **9 failed**／272 passed（host 的 `test_ordinary_record_outcomes[missing]`，加上 drain 的 8 個 `test_ordinary_last_call_without_endprocess_fails_the_record` 案例）；換回 `7692ee4` 的兩個測試檔則 271 passed，也就是修正前的測試抓不到，和 review 一致。我另外做了四個 log 位置的突變：L2（log 搬到 `withdrawn` 分支之前）被 `test_withdrawn_ordinary_record_outcomes[missing]` 殺掉；L3（已記錄的錯誤也 log）被兩個 `[error]` 案例殺掉；L4（改成 `log.warning`）被 `test_ordinary_record_outcomes[missing]` 殺掉；L5（只在沒有 control error 時 log）存活，但實務上等價：latch 時 pending 的 record 都會被寫入 error（`:442-452`），之後的一般 `enqueue` 直接丟出 control error（`:265-268`），所以「有 control error、沒有 record error、關卡沒到齊」的 record 走不到這個分支，不計。
  - 不增加雜訊：我自己寫了一個 pytest plugin（在 root logger 掛 handler，記下每筆含 `ordinary speech retired without its` 的訊息和當時的測試，`scratchpad/fixreview/plugin/logprobe.py`），跑完整套件（3569 passed）。總共 11 筆，全部來自刻意缺關卡的測試：host 的 `test_ordinary_record_outcomes[missing]`、`test_retire_waits_for_admitted_consumers[0]`／`[0.1]`（fake record 沒有 reach 就 retire），以及 VE、Cerence 各 4 個 `test_ordinary_last_call_without_endprocess_fails_the_record`。六個引擎的一般語音正確執行一筆都沒有，和修正記錄的說法逐筆相同。程式碼面：這個分支在 `master` 本來就判為失敗（合成錯誤、stop），log 只是讓它被看見，沒有新增任何判定。eSpeak 的一般語音一律經過 `_speak`→`espeak_Synth`，NVDA callback 最後一次 `wav=None` 時會 `idle()` 和 `onIndexReached(None)`，三個關卡都會到；SAPI5 legacy audio 不經過 host（`driver/SAPI5/__init__.py:459-461`）；OneCore 開 player 失敗時先 `record_error`（`driver/OneCore/__init__.py:335`），不會多一筆 log。
- **I2 — 已修好。** 突變 W6（`if token is not None:`）：用 `7692ee4` 的測試檔跑 5 個檔案，328 passed（存活，重現 review 的結果）；在 head 上 **8 failed**／330 passed，失敗的正好是兩個測試 × 兩種 `ends` × VE、Cerence 的全部 `live-token` 案例，`no-token` 照常通過。`request_token` 的註解（production 一律傳 token、`None` 是直接呼叫 core 的形狀）正確：`bridge/engineAdapter.py:33-35` 的 `_speakPlain` 在宣告 `cancellationToken` 時一律傳 token。缺 `ENDPROCESS` 測試後半的第二個請求也用同一種 token，並斷言沒有被 withdraw，同樣沒問題。
- **M1 — 已修好（就 review 指定的 W3b 而言）。** 突變 W3b（兩次 reach 之前讀 token）：用 `7692ee4` 的測試檔 328 passed（存活）；在 head 上 **2 failed**／336 passed，失敗的就是新測試 `test_token_cancelled_during_the_audio_fed_reach_is_withdrawn[VE]`、`[Cerence]`。新測試是確定性的（monkeypatch 實例的 `reach`，`_retireRecord` 透過 `host.reach` 呼叫，會被攔到），未突變時兩個引擎都通過。殘留的較窄變體見 N1。
- **M2 — 已修好。** 只改註解，內容正確：
  - `runtime/scheduler.py` 的行號已核對：`_cancel_request_locked` 是 `:386-395`（`token.cancel()` 在 `:391`）；`:419-441` 涵蓋 `_stop_all`（`:419-426`）和 `cancel()`（`:428-441`，在 `:435` 取消 token、`:439` 呼叫 `_stop_all`），和 review 建議的出處一致。「token-only 的取消在 NVDA 上只會短暫存在」這句，我另外看了只取消 token 的路徑：`abort_request`（`:265-266`）只發生在 BUILDING，這時任務還沒送出；`_run_one` 失敗（`:497-499`）時 `_settle` 會 stop 失敗任務自己的 playback（`:569-570`），而 scheduler 會等每個任務的 done（`_execute` `:554`）才跑下一個，所以前一個 VE 任務最多只剩 `_Retire` 的窗口，會被 withdraw，不會多 stop。這句在實務上成立。
  - 「token 測試的 player／DONE 斷言在 `master` 上也通過」，我獨立重做了一次：`master` 的 scratch 複本，放入 head 的 drain 測試檔，刪掉 27 個 `withdrawn`／`record.barriers`／`outcome`／`lastCallEnded`／log 斷言，跑 `-k "token_cancelled or legacy_endprocess_after_token"`，**16 passed**（M2 註解涵蓋的 7 個 token 測試，加上既有的 `test_token_cancelled_ordinary_leaves_contextual_final_idle_untouched`，各兩個引擎）。M1 的新測試也在其中：`master` 的一般語音沒有 reach，所以它的取消 hook 不會觸發，數字等於一次正常執行，和 review 表中「第一次 reach 之後、讀 token 之前」那一列的 `master` 數字（0／1／1）相同。

#### 新發現

Critical：無。Important：無。

##### N1（Minor）. M1 的測試只釘住「在 `AUDIO_FED` 的 reach 之後才讀 token」，沒有釘住「在兩次 reach 之後」：把讀取放在兩次 reach 之間的突變 W3c 存活（`tests/test_vocalizer_segment_drain.py:2116-2140`；VE `:513-526`、Cerence `:515-528`）

突變 W3c：在 `AUDIO_FED` 的 reach（VE `:513`）之後、`ENGINE_DONE` 的條件（`:516`）之前先讀 `_early = token.is_cancelled()`，withdraw 改用這個值。5 個檔案 **338 passed**，存活（`7692ee4` 的測試檔也是 328 passed）。M1 的新測試是在 `AUDIO_FED` 的 reach 返回時取消 token，這時 W3c 的讀取還沒發生，所以讀到的是已取消，照樣 withdraw。但 wrapper 註解寫的是「Read it after the reaches」和「pins this order」，實際上只釘住了一半。失敗情境：token 在 W3c 的讀取之後、`:516` 的 `_recordValid` 之前被取消，`ENGINE_DONE` 不會 reach，record 也沒有被 withdraw，結果被合成缺 `engine_done` 的錯誤，多一次 `stop_player()`。有了 I1 之後，NVDA log 還會多一筆假的 ERROR。窗口很窄，性質和 M1 相同，所以列為 Minor。

建議修法（確定性，不靠時序）：在 M1 的測試旁加一個案例，monkeypatch `env.core._recordValid`，在「`audio_fed` 已到、`engine_done` 還沒到」時先 `token.cancel()` 再回傳原本的判斷（也就是 `_retireRecord` 的 `ENGINE_DONE` 檢查），斷言和 M1 的測試相同：`barriers == {"audio_fed": True, "engine_done": False}`、`withdrawn`、`(True, None)`、`([b"pcm"], 1, 0)`、1 個 DONE。我寫的 scratch 版本 `test_token_cancelled_in_the_engine_done_check_is_withdrawn`（`scratchpad/fixreview/test_fixreview_extra.py`）未突變時兩個引擎都通過，W3c 和 W3b 都被殺掉（各 2 failed）。也可以把 M1 的測試參數化成兩個取消點。不修也可以 merge；要修的話，wrapper 註解指向的測試名稱要一起更新。

#### 突變結果

W 系列跑 `test_vocalizer_segment_drain.py`、`test_native_strategy_guards.py`、`test_vocalizer_drift.py`、`test_worldvoice_cancel_wrappers.py`、`test_worldvoice_request_manager.py`；I1／L 系列跑 `test_segment_host.py`＋`test_vocalizer_segment_drain.py`。「修正前」是把 `test_vocalizer_segment_drain.py`、`test_segment_host.py` 換成 `7692ee4` 的版本，其餘程式碼都是 head。

| # | 突變 | 修正前的測試 | 修正後（head） |
| --- | --- | --- | --- |
| I1 還原 | 拿掉 `retire` 的 `log.error` | 271 passed（存活） | **killed**：9 failed／272 passed |
| W6 | `if token is not None:`（有 token 就 withdraw） | 328 passed（存活） | **killed**：8 failed／330 passed（全部 `live-token` 案例） |
| W3b | 兩次 reach 之前讀 token | 328 passed（存活） | **killed**：2 failed／336 passed（M1 新測試的 `[VE]`、`[Cerence]`） |
| W3c | 兩次 reach 之間讀 token | 328 passed（存活） | **存活**：338 passed → N1；加上 scratch 測試後 killed |
| L2 | log 搬到 `withdrawn` 分支之前 | – | killed（`test_withdrawn_ordinary_record_outcomes[missing]`） |
| L3 | 已記錄的錯誤也 log | – | killed（`test_ordinary_record_outcomes[error]`、`test_withdrawn_ordinary_record_outcomes[error]`） |
| L4 | `log.warning` 取代 `log.error` | – | killed（`test_ordinary_record_outcomes[missing]`） |
| L5 | 只在沒有 control error 時 log | – | 存活，實務上等價（見 I1），不計 |

#### 驗證（head `1ce666c`）

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 完整套件（序列） | `python3 -m pytest -q tests`，背景 watchdog 每 2 秒讀 `/proc/meminfo`，MemAvailable < 3 GB 就 kill pytest（`scratchpad/fixreview/run_full.sh`） | **3569 passed／0 skipped**（104.27 s）；watchdog 沒有觸發（最低 MemAvailable 約 5.86 GB）；和修正記錄的數字相同 |
| log 雜訊探測 | 同一套件加 `-p logprobe`（`scratchpad/fixreview/run_probe.sh`） | 3569 passed；11 筆，全部是刻意缺關卡的測試（見 I1） |
| prek | `prek run --all-files` | 8 個 hook 全 Passed |
| 空白 | `git diff --check`、`git diff --check 7692ee4..HEAD`、`git diff --check master..HEAD` | 乾淨 |
| 受保護路徑 | §7 的 `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' …/driver/sonic/ …script_data.py …unspaced_common_data.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 都沒有輸出 |
| VE／Cerence 同步 | `sed 's/Cerence/VE/g; s/cerence/vocalizer/g; s/ttsapi/ve2/g'` 後和 VE `diff`，比較 `7692ee4` 和 head；`git diff 7692ee4..HEAD -- tests/test_vocalizer_drift.py` | 兩個版本的差異行完全相同（44 行），兩個 wrapper 各只多同一行註解；drift 測試沒有 diff，`ALLOWED` 不變 |
| commit | `git log --format=%B 7692ee4..1ce666c` | 5 個都是英文 `fix:`／`test:`／`docs:`，內文說明原因；沒有 `Co-Authored-By` |
| M2 的 `master` 中立說法 | `master` 的 scratch 複本＋head 的 drain 測試檔（刪掉 27 個新斷言），`-k "token_cancelled or legacy_endprocess_after_token"` | 16 passed |
| 未突變的 scratch 複本 | 6 個相關測試檔 | 410 passed |

Windows／NVDA 上的實際 log 輸出和音訊裝置都沒有驗證（Linux 只驗證受控的邊界）。
