# Review：Phase 58 coverage gaps（補覆蓋率缺口的行為測試）

日期：2026-10-31。分支：`phase58-coverage-gaps`（`06ea3e2..3ba0e10`，20 個 commit：2 個 `docs:`、1 個 `refactor:`、17 個 `test:`；基準 `master` `06ea3e2` 3243 passed／0 skipped，分支 3332 passed／0 skipped，+89 個 id）。
審閱者：Fable 5.1（唯讀；只新增本檔）。流程：一般流程（DEVELOPMENT_WORKFLOW.md §3.3）。批次 1（Tasks 1–6，`1679ce9..6742675`）已有 Opus 批次 review（`scratchpad/p58/batch1-review.md`，I1／I2／M1／M3／M4／M5 已在 `7aeb36e..ab02901` 修好），本次把重點放在批次 2（`81a24f0..3ba0e10`：VE／Cerence、SAPI5、OneCore、RHVoice、eSpeak），並把 spec 的 mutant、覆蓋率、重複執行與 §8 檢查全部自己重做一遍。

依據：

- spec `docs/superpowers/specs/2026-10-31-phase58-coverage-gaps-design.md`（§5 class (a) 每個測試都指名 mutant；§6 class (b)；§7 刪除；§10 Q1–Q6）；plan `docs/superpowers/plans/2026-10-31-phase58-coverage-gaps.md`（Review Focus 1–5 逐項檢查）；進度帳本 `.superpowers/sdd/2026-10-31-phase58-coverage-gaps/progress.md`（28 行 `Ruling:`，全部評估，特別是批次 2 把 (a) 改成 (b) 的七處）。
- 實驗都在暫時 worktree `scratchpad/p58/fable/wt`（detached `3ba0e10`，自己的 `ref` symlink，結束後已移除）；審閱者自己的腳本在 `scratchpad/p58/fable/tools/`（`guard.sh` 記憶體看門狗、`mut.py`＋`mutants.py` 突變表、`covcmp.py`、`fthreadleak.py`、`race_demo.py`、`test_fable_adhoc_sapi5.py`），輸出在 `scratchpad/p58/fable/out/`。實作者 `scratchpad/p58/impl/` 的 mutant log 與覆蓋率檔沒有拿來當證明，只拿來對數字。
- 行號以 head `3ba0e10` 為準；`addon/` 的行號在 base 與 head 相同（只有 `discovery.py` 少兩行）。路徑省略 `tests/`；`sd/` = `addon/synthDrivers/WorldVoice/`。

## 結論

**可以 merge，但先修 I1（便宜）。** Critical 0、Important 1、Minor 1。兩項都是同一類問題：新測試的結果依賴執行緒排程順序，而不是被 harness 的 gate 強制；I1 在我的 session 裡真的紅過一次。沒有找到產品 bug、沒有空洞斷言、沒有繞過真實路徑的 mock。

- **刪除是死碼，行為中立。** `_load_manifest`（`sd/engineRegistry/discovery.py:75`）只有兩個呼叫點 `:136`、`:147`，兩處都先 `if not manifest_path.is_file(): …; continue`（`:133-135`、`:144-146`）；`grep -rn _load_manifest addon tests tools` 只有定義與這兩處。刪掉 `:77-78` 後唯一差別是檔案在兩次檢查之間消失的競爭：改由 `read_text` 例外走 `:79-85` 的 warning 回傳 `None`，一樣跳過該引擎。`test_engine_discovery.py:112` 的 NoManifest／Bare 兩個 case 釘住兩個呼叫點的 debug 訊息；`discovery.py` 100 %。
- **新測試殺得死它們的 mutant。** 我獨立套用 36 個 mutant（30 個是 spec 指名、批次 2 為主，另外 6 個是我自己的探針），30 個 KILLED，1 個超時（RHVoice 270-274 的 try 拿掉後 `[segment]` 永遠等不到 retire，和帳本一致，是「語音卡住」的正確紅燈），3 個預期存活（帳本已重新分類為 b-equiv，見下），2 個是我探針的等價存活（RHVoice `cancel` 末端的 `_failSegmentControl` 與 `LeasedPlayer.stop` 自己的 latch 重複；VE 797 見下）。明細在驗證表。批次 1 review 的 I1／I2 修正也用原 reviewer 的 mutant 重驗，都紅。
- **七處 (a)→(b) 重新分類都成立，而且是「程式碼真的等價」，不是「測試看錯地方」。** 逐項：
  - VE 796-797／Cerence 805-806（`call.admitting = False`）：pause 失敗先 `_failSegmentControl` → `latch_control_error`，把 `record.error` 設在每個 pending record 上（`segmentHost.py:462-475`），`:801-802` 又對當前 record `record_error`；之後 `_callbackAdmission`（VE:600-617）因 `_recordValid` 為假回 `(None, call)`，和關掉 admission 的 `(None, None)` 只差 `__call__`（VE:239-250）對 legacy ENDPROCESS 回 `NUAN_OK` 還是 `USERSTOP`，而 `_checked` 兩個值都接受（VE:215-220）。我把這兩行拿掉跑整個 `test_vocalizer_segment_drain.py`：229 passed。b-equiv 成立。
  - VE 287-288／Cerence 291-292（marker 迴圈內的再檢查）：`_onIndexReached`（VE:748-765）對 `not _recordValid(record)` 直接 return，所以 cancel 之後的 bookmark 6 不會被報；迴圈結束時 `:307` 也照 `_recordValid` 回 `USERSTOP`。測試保留下來抓 `eMrkType` 那個 mutant（我重套：紅）。成立。
  - SAPI5 331-332、341-342（cancelled record 的 Bookmark／onIndexReached）：`Bookmark` 拿掉 guard 後進 NVDA 的 `Bookmark`（`ref/nvda/source/synthDrivers/sapi5.py:486-496`）→ `player.feed(None, 0, onDone)` → `_SegmentPlayer.feed`（SAPI5:196-214）→ `host.consumer(record)`（`segmentHost.py` 的 `consumer` 檢查 `record.is_valid()`）拒絕 → 不排任何 callback；`onIndexReached` 在 WASAPI 上只會經 `_SegmentPlayer._callback`（SAPI5:216-223，`if record.is_valid(): onDone()`）到達，segment 路徑還有 `:347` 的 `record.work.is_valid()`。我寫了一個 ad hoc 探針（token 取消當前 record 後打 `Bookmark(1,0,"7",7)`、`onIndexReached(1,7)`，斷言沒有 callback、沒有 index，後繼 segment 照常 drain）：未突變 pass；把兩個 guard 都拿掉（m21）後探針＋整個 SAPI5 檔 75 passed。成立。
  - OneCore 194->210（drain 時 `_player` 為 None）：segment 只在成功的 callback 之後 drain，而每個成功的 `_segmentPlayback` 都先 `_maybeInitPlayer(wav)`（OneCore:467）才 `AUDIO_FED`；`length == 0` 會先 raise。b-inv 成立。
  - OneCore 448-449（`or self._earlyExitCB`）：spec 說 cancel 會設 `_earlyExitCB`，實際只有 terminate（OneCore:664）與建構失敗（:263）會設，NVDA 自己也是（`ref/nvda/source/synthDrivers/oneCore.py:305`）。terminate 先 `host.cancel()`（:661）再設旗標，segment callback 被 `host.consumer` 拒絕，legacy callback 進 NVDA 的 `_callback` 時被它自己的 `_earlyExitCB` 檢查擋下（oneCore.py:484）。剩下的差別只有 `_legacyCallback` 會對已取消 record 多呼叫一次 `host.reach(record, AUDIO_FED)`（OneCore:501），對已取消 record 無可觀察效果。成立。
  - OneCore 535-536（`_feedSegment` 的 `is_valid` 早退）：`_player` 是 `LeasedPlayer`，其 `feed`（`segmentHost.py:718-722`）經 `consumer()` 只接受 valid 的當前 record，拒絕時回 `None`，`_feedSegment` 再 `return record.is_valid()` 一樣是 `False`。帳本說測試「token 在 callback 之前取消」，那種情況其實在 `_callback` 的 `host.consumer` 就被擋掉（OneCore:454-456），根本到不了 `:535`；真正能到 `:535` 的是「admission 之後、feed 之前取消」的 race，由 lease 擋住。結論（b-equiv／b-race）正確，理由寫得不精確。我把兩行拿掉跑整個 OneCore 檔：唯一的紅是 I1 的 flake（見下），與這個 mutant 無關（覆蓋率證明 `:536` 從未執行）。
  - eSpeak 195->196、196、91（`markNotSpeaking`）：失敗的 ordinary record 在 `host.retire` 走 `error is not None and control_error is None` → `stop_player`（`segmentHost.py:560-561`）→ `_EspeakPort.stopPlayer` 先清 `isSpeaking`（Espeak:94-97），所以 `:196` 重複。差別只在 control error 已 latch（retire 不 stop）時，而那時引擎本來就要 reload。注意這三行在 head 其實**有**被 `conversion` case 覆蓋（Espeak 剩下未覆蓋的只有 §6 列的 37->39、44、165、185-187、206->211、208-209），被重新分類的是 mutant 不是行。我把 `:195-196` 拿掉跑整個 eSpeak 檔：30 passed。成立。
- **批次 2 的測試看的是對的東西。** 每個 P1 測試都在錯誤之後再講一段（spec／plan Review Focus 1）：VE 溢位（`test_vocalizer_segment_drain.py:918-948` 第二段 `fed == [b"pcm"]`、DRAINED）、pause 清理失敗後 `terminate` 以 `finish(run_thread(...))` 在 timeout 內完成且 `closes == 1`（`:1778-1797`）、terminate 的 cancel 失敗後 player 已關、native 已 terminate、`_terminationDone` 已設、第二次 terminate 回來（`:1817-1831`）、SAPI5 purge 失敗後 control error 被記住並點名下一段（`test_sapi5_segment_drain.py:1333-1348`、`:1468-1478`）、stream 不符後下一段 DRAINED（`:1480-1503`）、OneCore 無 player 時 cancel 不 latch 且下一段 DRAINED（`test_onecore_segment_drain.py:1750-1767`）、截斷 WAV 後 `unraisable == []`、沒有 feed、下一段 DRAINED（`:1832-1863`）、RHVoice final idle 失敗後下一段 DRAINED（`test_rhvoice_segment_drain.py:1036-1077`）、eSpeak 轉換失敗後 `isSpeaking is False`、DONE 一次、下一句多一次 `espeak_ng_Cancel`（`test_espeak_segment_drain.py:535-563`）。Review Focus 2（`test_vocalizer_init_cleanup.py:159-169`，真的讀 `conf["speech"]["outputDevice"]`）、3（`test_sapi5_segment_drain.py:1413-1424`，Speak 在呼叫執行緒、`current() is None`、Bookmark／onIndexReached 立即報）、4（VE marker 清單 `[5]`、SAPI5 segment bookmark `[8]` → `[8, 9]`）、5（批次 1 已核）都有對應測試且 mutant 紅。
- **沒有 over-mock。** VE／Cerence 用真的 wrapper＋真的 `VECallback` 子類，只替換 native 與 player 的 fake（`_ensureSonicStream` 以假 Sonic 取代是既有 `:949` 測試的寫法；真 Sonic 是 vendored）；SAPI5 的 `Notify` 測試只假造 `_SapiEvent.enumerateFrom` 的事件來源，dispatch 走真的 `ISpNotifySink_Notify`；OneCore 的截斷測試用真的 ctypes buffer 直接呼叫 native callback；RHVoice／eSpeak 用既有 harness。讀私有狀態的地方（`segment_host(env.driver).control_error`、`termination_done(env.core)`、`host.retire` 包一層記 outcome）都是既有 drain 測試已經在用的觀察點（spec Q5）。
- **Harness 沒有改。** diffstat 裡沒有任何 `*_harness.py`；`test_vocalizer_init_cleanup.py:43` 的 `RecordingPlayer.options = kwargs` 與 `test_lint_rewrites.py` 的 `_context_module(get_synth=…)`（批次 1）都是加參數，不改既有測試的行為。
- **覆蓋率沒有回歸。** 我自己在 base 與 head 各跑一次完整分支覆蓋：83 個模組逐模組比對，18 個模組有變化，**0 個模組出現新的未覆蓋行或 arc**；TOTAL 8368／180／2374／157 → 8366／67／2372／89（98.53 %，和實作者兩次 run 相同）。時序行：我的兩次 run 都漏 `scheduler.py:393`（base 也漏，不是回歸），`_segmentLifecycle.py:166` 兩次都有覆蓋；實作者的 run 2 相反。帳本 Ruling（Task 12）把這兩行記成時序相關正確。六個引擎剩下的未覆蓋行逐一對過 spec §6 加七處重新分類，沒有多出來的。
- **帳本 28 個 `Ruling:` 都合理**（表在下方）；只有 T8.9 的理由寫得不精確（見上）。
- **限制。** `git diff --stat master -- addon` 只有 `engineRegistry/discovery.py | 2 --`；受保護路徑與 Neural 兩個指令都沒有輸出；20 個 commit 都是英文 `<type>: <summary>` 加原因，0 個 `Co-Authored-By`；`ref`、`.superpowers` 未追蹤；分支只動 `tests/`、`docs/` 與那一個 `addon/` 檔；`git diff --check` 乾淨；prek 8 個 hook 全 Passed；ruff 0.16.3；新測試 diff 裡沒有 `sleep`。

## Critical

無。

## Important

### I1. `test_a_segment_cancelled_while_the_player_opens_is_never_spoken` 的結果依賴測試執行緒先於 worker 執行（`test_onecore_segment_drain.py:1794-1813`，commit `6dafb56`）

`speak(env, commands=("bravo",))`（`:1804`）一送出，OneCore worker 就可能開始 bravo 並呼叫 `player.open()`；而 `open_and_cancel`（`:1798-1801`）要在 `tokens` 非空時才取消，`tokens.append(token)` 卻在 `speak()` 回來之後（`:1805`）。只要 worker 在 `speak_segment` 還沒回來前拿到 GIL（例如 5 ms 切換間隔剛好落在 `speak()` helper 裡，或測試執行緒被 OS 搶佔），bravo 就不會被取消而正常講出，charlie 排在後面；`env.native.wait_calls(1)` 等到的是 bravo 的 native call，`respond` 完成的是 bravo，charlie 的事件永遠不來，`wait_events(events)` 在 3 s 後報 "Segment event was not delivered"。

失敗情境：**偶發紅燈，沒有產品變更。** 我在跑一個與此無關的 mutant（m27，拿掉 OneCore:535-536，覆蓋率證明這兩行從未執行）時整個 OneCore 檔只有這個測試紅，訊息就是上面那句；之後單獨重跑 30 次、在 coverage 下重跑 10 次都過。為了證明是順序問題，在 scratch 複本的 `:1804` 與 `:1805` 之間插入 20 ms 的 `sleep`，測試**確定**失敗（`scratchpad/p58/fable/out/t85-delay.log`）。spec §8 要求「interleaving is forced, not timed」，這個測試沒有做到。

建議修法（任一，先在 scratch 複本確認插入 sleep 後仍然綠）：

1. 在 `speak()` 之前就備好 token：給 `test_onecore_segment_drain.py` 的 `speak()` helper 加 `token=None` 參數（`test_vocalizer_segment_drain.py:106` 的 helper 已經這樣做），測試先 `token = env.scheduler.CancellationToken()`、`tokens.append(token)`，再 `speak(env, commands=("bravo",), token=token)`。
2. 或讓 `open_and_cancel` 等一個 `Event`：`token_ready = Event()`；`open_and_cancel` 裡 `assert token_ready.wait(WAIT_TIMEOUT)` 再取消；測試在 `tokens.append(token)` 之後 `token_ready.set()`。

順便檢查過同檔其他新測試：`test_a_token_cancelled_queued_segment_is_abandoned_unopened`（`:1770-1791`）在 alpha 的 native call 還沒 `respond` 前取消 bravo，worker 被 alpha 擋住，順序是被 gate 強制的；`test_cancel_before_any_audio_stops_nothing`、`test_truncated_wav_*`、`test_cancel_during_a_paused_final_idle_publishes_no_done` 也都有 `wait_calls`／`idle_entered` 之類的 gate。

## Minor

### M1. `test_start_stream_marks_speaking_only_for_the_current_stream` 假設 `wait_calls(1)` 回來時 worker 已記下 stream 編號（`test_sapi5_segment_drain.py:1401-1410`，commit `f6bbe83`）

harness 的 `Native.Speak`（`sapi5_drain_harness.py:108-123`）在 `calls.append` 並 `notify_all` 之後才 `return stream`，worker 再在 `_threadCond` 下寫 `native.stream = stream`（SAPI5:595-598）。測試在 `wait_calls(1)` 之後立刻 `StartStream(2, 0)`（`:1404`）；若這時 `native.stream` 還是 `None`，`_native`（SAPI5:294-313）會把 2 當成這個 request 的 stream（2 不在 `_segmentSeenStreams`），`record.is_valid()` 為真而標成 speaking，`assert is_speaking(env.driver) is False` 失敗（或稍後 worker 的 `native.stream != stream` 丟出 mismatch）。視窗只有 Speak 回來到寫入之間的幾個 bytecode，需要 worker 在那裡被搶佔超過一個 GIL 切換間隔，所以我 10×／30× 都沒有碰到；但把 fake `Speak` 的 `return stream` 延後 20 ms（只改 scratch 複本的 harness），SAPI5 檔 74 個測試中**只有**這一個失敗（`scratchpad/p58/fable/out/sapi-delay.log`），其他 73 個對這個順序都不敏感。失敗情境：極低機率的偶發紅燈。建議在 `:1404` 之前加 `eventually(lambda: segment_host(env.driver).current().native.stream == 1)`（`eventually`、`segment_host` 這個檔都已 import），或先送 `StartStream(1, 0)` 再送 `StartStream(2, 0)` 並改成斷言 speaking 狀態沒有被第二次改掉。可不修，但和 I1 一起修很便宜。

## 審閱者自行驗證的項目

所有 pytest 都在 `scratchpad/p58/fable/wt`（`3ba0e10`）一次只跑一個，`guard.sh`／`mut.py` 每秒看 `MemAvailable`，低於 3 GB 只砍自己的 pytest PID（全程未觸發，起始 6.4 GB）。mutant 由 `mutants.py` 的精確字串替換套用（舊字串必須恰好出現一次，否則不跑），跑完 `git checkout -- <file>` 還原並確認 `git status` 乾淨。

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 完整測試＋分支覆蓋（head） | `python3 -m pytest -q -p no:cacheprovider -rs tests --cov=addon --cov-branch --cov-report=term-missing`（`out/full-cov1.log`） | **3332 passed、0 skipped**（180 s）；TOTAL 8366／67 miss、2372／89 partial（98.53 %），與 `impl/final-cov1.txt`、`final-cov2.txt` 相同 |
| 完整測試＋分支覆蓋（base，同一 worktree `git checkout 06ea3e2 -- tests addon`） | 同上（`out/base-cov.log`） | 3243 passed、0 skipped；TOTAL 8368／180、2374／157 |
| 逐模組覆蓋比較 | 自寫 `covcmp.py base-cov.log full-cov1.log`（Stmts／Miss／Branch／BrPart 與 missing 清單逐模組比） | 83 個模組；18 個有變化，全部只有「變成已覆蓋」；**0 個模組有新的未覆蓋行或 arc**；`discovery.py` 138→136 stmts、52→50 branches、100 % |
| 時序行 | 兩次 run 的 `_segmentLifecycle.py`、`scheduler.py` missing 欄 | 我的 base／head 都漏 `scheduler.py:393`、都覆蓋 `:166`；實作者 run 2 相反；與帳本 Task 12 的 Ruling 一致，非回歸 |
| 引擎剩餘未覆蓋 vs spec §6 | head run 六個 `driver/*/__init__.py` 的 missing 欄逐項對 §6 加七處重新分類 | 完全一致，沒有多出的行或 arc |
| 收集差異 | `pytest --collect-only -q` 在 base 與 head（`out/ids-base.txt`、`ids-head.txt`，`comm`） | 3243 → 3332；新增 89 個 id、移除 0；89 個分佈在 19 個檔、65 個測試函式 |
| 死碼刪除 | `grep -rn _load_manifest addon tests tools`；讀 `discovery.py:126-152`、`test_engine_discovery.py:112-142` | 只有定義與兩個呼叫點，兩處都先 `is_file()`；兩個 missing-manifest case 被釘住 |
| mutant m01–m10（VE，spec T6.1–T6.7、T6.9–T6.11） | 270-271 guard 刪；`if data.cntPcmBufLen`→`if True`；278-280 刪；289 `eMrkType` 檢查→`if True`；291 `elif ENDPROCESS`→`else`；413-414 fallback 刪；`tasks = []`；806-807 except 刪；844-845 except 刪；884 無條件 | 10 個全部 KILLED（VE 參數紅、Cerence 參數綠：m01 2 failed/2 passed、m10 1 failed/3 passed、其餘 1 failed/1 passed） |
| mutant m12（Cerence 943-944） | `except Exception`→`except ZeroDivisionError` | KILLED（OSError 逸出） |
| mutant m13–m20（SAPI5，T7.1–T7.7、T7.9–T7.12） | 103-106 try 刪；152-156 內層 try 刪；171-172 刪；`elif TTS_BOOKMARK`→`else`；451-453 legacy return 刪；348 去掉 `index not in bookmarks`；582-585 try 刪；595-596 刪 | 8 個全部 KILLED（m19 worker 死掉、3 s 後紅＋thread exception warning；m20 等不到 terminal event） |
| mutant m22–m26（OneCore，T8.2、T8.4、T8.5、T8.7、T8.8） | `stop_native` 的 `if player:` 刪；355-357 刪；472-473 刪；498 `if self._player:` 刪；522 條件→`True` | 5 個全部 KILLED（m25 在 `unraisable == []` 紅：AttributeError 從 ctypes callback 逸出） |
| mutant m28–m29（RHVoice，T9.1、T9.2） | 270-274 try 刪；459-460 `if error is None: error = exc` 刪 | m28 KILLED(timeout)：`[segment]` 永遠等不到 retire，120 s 後被 `mut.py` 砍掉，和帳本一致；m29 KILLED（DID NOT RAISE） |
| mutant m30–m31（eSpeak，T10.1、T10.2） | 31-32 刪；115-116 except 刪 | 兩個 KILLED（native cancel 被呼叫；ValueError 逸出 `speak()`） |
| mutant m33–m34（批次 1 review I1／I2 的 mutant） | `segmentHost.py:546-547` except 加 `latch_control_error`；`scheduler.py:547` 後加 `if not failed: raise` | 兩個 KILLED（`control_error is None` 紅；fresh request 等不到） |
| mutant m35（探針：VE pause 失敗清理不釋放 stop gate） | 拿掉 `:808-810` 的 `finally: self._stopGate.leave()` | KILLED：`test_a_pause_failure_cleanup_stop_error_is_logged` 的 `finish(run_thread(terminate))` 超時 → 測試真的守住「terminate 不會卡死」 |
| 預期存活 m11（VE 797 `call.admitting = False`） | 刪兩行，跑整個 `test_vocalizer_segment_drain.py` | SURVIVED，229 passed → Task 7 Ruling（b-equiv）成立 |
| 預期存活 m21（SAPI5 331-332、341-342） | 兩個 `if not record.is_valid(): return` 都刪，跑整個 SAPI5 檔＋我的 ad hoc 探針 | SURVIVED，75 passed；探針未突變也 pass → Task 8 Ruling（T7.8 b-equiv）成立 |
| 預期存活 m27（OneCore 535-536） | 刪兩行，跑整個 OneCore 檔 | 第一次 1 failed／90 passed，紅的是 **I1 的測試**（與這兩行無關，覆蓋率證明 `:536` 從未執行）；結論仍是等價（見結論） |
| 預期存活 m32（eSpeak 195-196） | 刪兩行，跑整個 eSpeak 檔 | SURVIVED，30 passed → Task 11 Ruling 成立 |
| 探針 m36（RHVoice 460 的 `_failSegmentControl(exc)`） | 只拿掉 latch 保留 `error = exc` | SURVIVED：`LeasedPlayer.stop`（`segmentHost.py:777-782`）已經 `latch_control_error`，這一行是重複保險；不是測試弱點，記錄備查 |
| I1 的重現 | 單獨跑 T8.5 30 次；coverage 下 10 次；scratch 複本在 `:1804` 後插 `sleep(0.02)` 跑一次 | 0／30、0／10 紅；插入延遲後**確定**紅（"Segment event was not delivered"） |
| M1 的重現 | scratch 複本的 `sapi5_drain_harness.py` 讓 `Speak` 在 `notify_all` 後 `sleep(0.02)` 再 `return stream`，跑整個 SAPI5 檔 | 1 failed／73 passed，紅的只有 `test_start_stream_marks_speaking_only_for_the_current_stream` |
| 89 個新 id 連跑 10 次＋執行緒洩漏＋`sys.unraisablehook` | `run10.sh`：每輪一個 pytest，`-p fthreadleak`（每個測試 logfinish 後最多等 2 s 看多出的執行緒，並比對 logstart／logfinish 的 `sys.unraisablehook` 身分） | 10／10 輪 **89 passed**（每輪約 30 s）、0 warning；`sys.unraisablehook` 在 890 次測試前後都是同一個物件（OneCore 截斷測試的 monkeypatch 沒有洩漏）；每輪有同樣 14 個 id 在 teardown 後 2 s 內還留著 `WorldVoiceSegmentDelivery`＋一個 `Thread-N`，全部在 `test_vocalizer_segment_drain.py`——用同一個 plugin 跑該檔的既有測試（`test_parameter_read_never_reorders_queued_speech`、`test_processing_errors_latch_failure_on_original_context`、`test_last_call_without_endprocess_fails_the_segment`）18／18 也一樣，是 `env` fixture 的既有收尾方式，不是本 phase 引入；其餘 75 個新 id（含 SAPI5、OneCore、RHVoice、eSpeak 全部）0 個殘留執行緒 |
| 固定 sleep | `git diff master..HEAD -- tests \| grep '^+' \| grep sleep` | 無 |
| ruff／prek（scratch worktree，乾淨樹） | `ruff check addon tests tools`；`ruff format --check addon tests tools`；`prek run --all-files` | All checks passed；242 files already formatted；8 個 hook 全 Passed，worktree 未被修改 |
| §8 限制 | `git diff --stat master -- addon`；§7 兩個受保護路徑指令；`git log --format=%B master..HEAD \| grep -c Co-Authored`；`git log --format=%s`；`git diff --check master HEAD`；`git ls-files ref .superpowers`；`git diff --name-only master HEAD \| grep -v '^tests/\|^docs/\|^addon/'` | 只有 `discovery.py \| 2 --`；兩個指令無輸出；0；20 個英文 `<type>: <summary>`；乾淨；未追蹤；無 |
| 清理 | `git worktree remove --force fable/wt`；`git worktree list` | 只剩原有 worktree |

### 進度帳本 `Ruling:` 評估（28 行）

| # | Ruling | 評估 |
| --- | --- | --- |
| 1（Task 4） | `test_bind_requires_a_correlated_contract` 不參數化 | 合理：`CompletionContract` 拒絕 LEGACY_DONE 帶範圍，另一半沒有人能建構（批次 1 已核） |
| 2（Task 4） | engineAdapter 191-194 早退的 mutant 存活，b-equiv | 合理；批次 1 M5 已補「被 sibling 以讀取次數抓到屬人為」 |
| 3（Task 5） | 第二次 terminate 改成 teardown 中重入 | 合理（批次 1 已核，M3 改名） |
| 4（Task 5） | getter 用 `_get_<name>()` 讀 | 合理，與既有 setter 測試一致 |
| 5（Task 6） | apply 測試刪 `conf["speech"]` | 合理，是真的 KeyError 路徑 |
| 6–11（批次 1 修正） | I1、I2、M1、M3、M4、M5 的修法；M2 不合併 | I1／I2 我用原 reviewer 的 mutant 重驗都紅（m33、m34）；M1 的 getter 先讀 seed 再讀設定值；M2 不合併理由（既有 fake 只有 `commit`）成立；M3、M4、M5 照建議做 |
| 12（批次 1） | M6 延到 Task 12 | 已做（Ruling 26） |
| 13（Task 7） | T6.8 `call.admitting = False` 改 b-equiv、測試不加 | **成立**，見結論；m11 存活 |
| 14（Task 7） | VE 287-288 改 b-equiv，測試留著抓 eMrkType | **成立**；m04 紅 |
| 15（Task 7） | T6.10／T6.11 讓 terminate 自己的 cancel 失敗（第一次），不是 player stop 失敗 | 合理：stop 失敗會在 cancel 的 finally 由 `_retirePlayerOperation` 完成 termination，`:844-845` 的 except 分不出來；代價（釘住一個目前沒有程式碼會產生的 cancel 失敗型態）帳本有寫 |
| 16（Task 7） | T6.12／T6.13 放 `test_f4_engine_adapters.py` | 合理：`test_driver_voice_base.py` 只載 base Voice |
| 17（Task 7） | 用 `logged_errors` 包 `env.module.log.error` | 合理：harness 的 logHandler stub 丟掉訊息 |
| 18（Task 8） | T7.8 改 b-equiv／b-race，測試不加 | **成立**，我的探針在有無 guard 下都沒有 index、沒有 callback（m21） |
| 19（Task 8） | purge 失敗測試斷言 segment 帶 control error 而非 idle error | 合理：delivery 用 latched control error 重貼標籤；測試另外斷言 `event.error is control_error` |
| 20（Task 8） | cancel 中 purge 失敗不斷言 worker 存活 | 合理：latch 後 worker 依設計退出，`needsVoiceReload()` 為真 |
| 21（Task 8） | 319 的 mutant 用「條件→True」而非只拿掉 `record.is_valid()` | 合理；只拿掉 `is_valid()` 的那一半是 b-race |
| 22（Task 9） | T8.3 改 b-inv | **成立**：`_maybeInitPlayer` 在每個成功 callback 的 `AUDIO_FED` 之前 |
| 23（Task 9） | T8.6 改 b-equiv／b-race：只有 terminate 設 `_earlyExitCB` | **成立**；spec 前提錯（cancel 不設旗標）；殘餘差別只有對已取消 record 多一次 `host.reach(AUDIO_FED)` |
| 24（Task 9） | T8.9 寫了、mutant 存活、改 b-equiv | 結論**成立**（lease 的 `feed` 經 `consumer` 擋），但理由不精確：「token 在 callback 之前取消」在 `_callback` 的 `consumer` 就被擋，到不了 `:535`；能到的是 admission 之後的 race |
| 25（Task 9） | 截斷 WAV 測試直接呼叫 native callback並收集 `sys.unraisablehook` | 合理且必要：ctypes callback 的例外只會變 unraisable；monkeypatch 在 teardown 還原，我的 plugin 確認沒有跨測試洩漏 |
| 26（Task 10） | final idle 測試讓第三次 idle 失敗、ordinary 不斷言「無 DONE」 | 合理：前兩次 idle 是 inner callback 與 inner SpeakText 的，失敗會被 worker 自己的 except 記錄而跳過 final idle；RHVoice 的 DONE 在 native call 回來前就發了 |
| 27（Task 11） | T10.2 `synth` case 與 mutant 丟掉，改 b-equiv | **成立**（m32 存活）；注意行本身已被 `conversion` case 覆蓋 |
| 28（Task 12） | `_segmentLifecycle.py:166`、`scheduler.py:393` 是時序行 | 成立：我的 base／head 都漏 393、都覆蓋 166，與實作者相反 |

（第 6–11 列合併了批次 1 修正的 7 行 `Ruling:`（I1、I2、M1、M2、M3、M4、M5）；第 12 列的 M6 延後在帳本裡不是 `Ruling:` 行；其餘每列一行，共 28 行。）

未做：未重跑 mutmut（spec 非目標；以 36 個手工 mutant 取代）；未在 Windows／NVDA 實機驗證（純測試變更加一個不可達 guard 的刪除，使用者看不到也聽不到差異）；未打包。

## 使用者還沒確認的使用者可見預設

這個 phase 只改測試與一個死碼刪除，NVDA 使用者看不到、聽不到任何變化。下面是協調者採建議預設、使用者可在 merge 前推翻的決定：

1. **Q1：RHVoice 148-150、319-322 留白不測**（稽核列為「最有價值」的兩個缺口，spec §6 判為 b-equiv）。審閱者同意：前者的錯誤由 `_QueuedSpeech` 自己的 except 記錄，後者只動私有 `_segmentById`。
2. **Q2：`TaskManager.cancel_current` 沒有產品呼叫者**（`scheduler.py:451-460`，只有測試用）。預設保留 API 與測試、不補 idle 分支；拿掉未用 API 是另一個清理。
3. **Q3：b-race 與 b-gc 分支不測**，不在私有鎖內加 hook。審閱者同意。
4. **Q4：b-inv 防禦 guard 保留**，只刪 `discovery.py:77-78`。審閱者同意；刪除已獨立驗證為行為中立。
5. **Q5：測試經 `env.driver._segmentHost.control_error` 讀私有屬性的公開 property**，與既有 drain 測試一致。
6. **Q6：發現產品 bug 時不在本 phase 修**。本 phase 沒有觸發（沒有發現產品 bug）。
7. **七處 (a)→(b) 重新分類**（帳本 Task 7、8、9、11）：VE 796-797／Cerence 805-806、VE/Cerence 287-288、SAPI5 331-332／341-342、OneCore 194->210、448-449、535-536、eSpeak 196 的 mutant。審閱者逐項讀碼並以 mutant／探針驗證，全部成立；代價是這些 guard 將來被刪也不會有測試擋（它們都是另一層已經擋住的重複保險）。相應地 TOTAL 是 98.53 %，比 spec §4 的 98.67 % 少 7 行＋6 個 partial arc（加每次 run 一行時序行），spec 的目標數字沒有回補。
8. **spec §6 的 (b) 清單整體**（60 行／83 arcs）留白。
9. **plan 的計數落後**：plan 表預期 3340，實際 3332（上述重新分類少 8 個 id）；plan Task 8 的運行計數 +13 與它自己列的 12 個測試不一致。只是文件，不影響合併；若要補，連同 spec §4 的目標數字一起改。
10. **I1、M1 若不修**：兩個新測試在排程不利時會偶發紅燈；本次 10× 重跑沒有碰到，但 I1 在我的 session 已紅過一次。
11. **只在 Linux 驗證**：所有結論來自 fake／stub 測試；Windows 的 NVDA、音訊裝置、引擎 SDK 都沒有驗證到。

## 修正記錄

依協調者決定（DEVELOPMENT_WORKFLOW.md §3.4），I1 與 M1 都修。兩項都先在暫時 worktree（`scratchpad/p58/impl/mut-*`，自己的 `ref` symlink，跑完即移除）重現審閱者的 20 ms 延遲注入，確認紅燈，再改測試，最後確認注入延遲後轉綠。

| 項目 | commit | 修法 | 驗證 |
| --- | --- | --- | --- |
| I1 | `0b635c9` | `tests/test_onecore_segment_drain.py` 的 `speak()` helper 新增 `token=None` 參數（與 vocalizer helper 相同）；`test_a_segment_cancelled_while_the_player_opens_is_never_spoken` 先建立 token、放進 `tokens`，再用它呼叫 `speak()`，worker 的 `player.open()` 一定看得到 token。 | 修正前：在 `speak()` 與 `tokens.append` 之間插入 `sleep(0.02)` → 紅（"Segment event was not delivered"）。修正後：在 `speak()` 之後插入同樣延遲 → 綠。spec 指名的 mutant（OneCore 392-393）仍然紅。 |
| M1 | `05c2e1a` | `test_start_stream_marks_speaking_only_for_the_current_stream` 在 `StartStream(2, 0)` 之前加 `eventually(lambda: segment_host(env.driver).current().native.stream == 1)`，等 worker 記下 Speak 回傳的 stream 編號。 | 修正前：scratch 複本的 `sapi5_drain_harness.py` 讓 fake `Speak` 在 `notify_all` 後延遲 20 ms 才回傳 → 紅（`assert True is False`）。修正後同樣注入 → 綠。mutant（319 條件→True、321→True）仍然紅。 |
| 計畫數字 | `272b0a2` | 計畫的 running counts 改成實際數字（Task 7–11：3309／3320／3327／3330／3332），並註明原本計畫的數字與被重新分類的項目。 | — |

重跑結果：兩個修好的測試各連跑 30 次 0 紅；`tests/test_onecore_segment_drain.py` 與 `tests/test_sapi5_segment_drain.py` 一起連跑 5 次，每次 165 passed；完整測試 **3332 passed、0 skipped**（記憶體看門狗下，`rc=0 killed=0`）；`prek run --all-files` 全部 Passed；`git diff --check master` 乾淨；`git diff --stat master -- addon` 只有 `engineRegistry/discovery.py | 2 --`；受保護路徑與 Neural 兩個指令都沒有輸出。
