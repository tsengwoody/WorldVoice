# Review：Phase 53 player 與 control-fault 統一

日期：2026-10-29。分支：`phase53-player-control-fault`（worktree `/workspace/WorldVoice-phase53`，`master` `9d96ace` 之上 11 個 commit：`8e1b79d..80da555`）。
依據：

- 規格 `docs/superpowers/specs/2026-10-29-phase53-player-control-fault-design.md`
- 計畫 `docs/superpowers/plans/2026-10-29-phase53-player-control-fault.md`
- 進度帳本 `.superpowers/sdd/2026-10-29-phase53-player-control-fault/progress.md`（未追蹤）
- 一致性稽核 `cons.md` B4、B5、C2、C5（主 checkout，唯讀）

審閱：Fable 5.1，DEVELOPMENT_WORKFLOW §3.3，唯讀；只跑測試與 scratch 複本上的突變。行號以分支 HEAD 為準：`OneCore:` ＝ `addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py`，`VE:` ＝ `driver/VE/__init__.py`（Cerence 的 diff 區塊與 VE 逐字相同，見驗證表），`control:` ＝ `runtime/engineControl.py`，`host:` ＝ `runtime/segmentHost.py`，`lifecycle:` ＝ `runtime/_segmentLifecycle.py`。

## 結論

**Ready to merge：是，修掉 I1 之後。** Critical 0、Important 1、Minor 5。

- 正確路徑沒有回歸：六個引擎的 feed／stop／idle、DONE 與 index 發佈、segment 事件在沒有失敗時走的路徑和 `master` 相同。OneCore 多的只是每次 feed 經 `host.consumer()` 取一次 host condition（巢狀准入，callback 已被 `_callback` 准入且還沒 `close`），index callback 原樣傳給 WavePlayer（`OneCore:121-125`）；VE／Cerence 的 feed 同樣只多一次巢狀准入。
- 一條 latch 規則（`control:6-23`）在五個有自己佇列的 wrapper 都套了，而且安全：每個「只記錄在 record」的失敗，後繼開始前都至少有一次 stop——drain 自己的 stop（OneCore `:215-219`、VE `:362-368`），然後 lifecycle 的 `fail → _start_stop → request_stop → stop_native`（`lifecycle:394-407`、`:471-495`、`host:549-560`）和第二次 `wait_playback_drained → stop_player`（`lifecycle:306-318`、`host:578-580`）；而 `record.handoff` 要等 `lifecycle.run` 整個回來才設（`host:610-636`），所以 OneCore worker 上排在後面的一般語音也進不去。stop 失敗一律經 `LeasedPlayer._stop_failed` latch，沒有被吞掉的 stop 失敗（逐一核對 `_afterControlFault`、VE `pause` 清理、VE `_runNative` blocked stop、`host.retire` 的三處：都是 lease 先 latch、呼叫者只 log 或 record）。
- 執行緒與鎖：OneCore 鎖序仍是 pause lock → `_segmentCondition` → host condition；新加的「pause lock 之下取 host condition」只有 lease 的 `consumer()`／`record_error`（`_maybeInitPlayer` 裡舊 player 的 `idle()`），沒有反向路徑。`deferred()` 在 `local.depth` 歸零之後才 `deliver`（`control:167-171`），所以 `_afterControlFault` 裡再次 stop 失敗 → `fail()` 不會再被延後、也不會遞迴。
- 測試：實作者的 M1–M8、mutmut 52/53 的紀錄屬實；我自己的 9 個突變殺掉 7 個。存活的 2 個：M2a（已記錄，可接受）和 **MA（`_legacyCallback` 的 `record_error`，見 I1，需要補測試）**。

## Critical

無。

## Important

### I1. OneCore 一般語音 callback 失敗的 handler 沒有被測試釘住：拿掉 `record_error` 後測試照過，實際後果是 NVDA 語音卡住（`OneCore:530-534`；`tests/test_onecore_segment_drain.py:1510-1527`）

- **情境：** `test_ordinary_callback_failure_fails_only_its_sentence` 用 `env.player.error = "feed"`（`:1516`）。feed 走 `LeasedPlayer._feed_admitted`，錯誤已由 lease 的 `_record_error` 記在 record（`host:709-711`），所以 `_legacyCallback` 的 `self._segmentHost.record_error(record, error)`（`OneCore:534`）是多餘的——對這個測試而言。只有不經 lease 的呼叫失敗時它才是唯一的紀錄點：`self._player.sync()`（`OneCore:516`，經 `__getattr__` 直達 WavePlayer）、`reach`、以及 `super()._callback` 裡 feed 以外的任何例外。
- **突變（scratch 複本）：** 刪掉 `OneCore:534` 這一行 → `tests/test_onecore_segment_drain.py` 85 個全部通過。再用同一個測試改成 `env.player.error = "sync"`：分支上通過，突變後失敗（`the failed sentence never completed`）。原因：record 沒有 error，`_ORDINARY_BARRIERS` 只有 `AUDIO_FED`（`OneCore:29`）而它已經 reach，`host.retire` 沒有錯誤、沒有 stop，`_speakRecord` 的 `skipped or record.error is not None`（`OneCore:419`）為 False → 沒有 `DONE`。NVDA 的 speech manager 等不到 `synthDoneSpeaking`，直到下一次 cancel 之前都不會送下一句。
- **修法：** 把 `test_ordinary_callback_failure_fails_only_its_sentence` 參數化為 `("feed", "sync")`（fake player 的 `sync()` 已支援 `error == "sync"`，`tests/onecore_drain_harness.py:119-123`），或另加一個 `sync` 版本。程式不用改。

## Minor

### M1. Review Focus 1 的兩個測試名稱超過它們證明的內容：拿掉 lease 的 late-feed stop，它們仍通過（`tests/test_onecore_segment_drain.py:1626-1653`；`tests/test_vocalizer_segment_drain.py:2442-2476`）

- 實作者的 M3 已經記錄這點：`test_cancelled_segment_feed_is_stopped_by_the_lease_before_successor` 和 `test_late_feed_after_cancel_is_stopped_and_stop_failure_latches`（訊息「the feed that returned after cancel was not stopped again」）在沒有 `host:712-716` 時照樣通過，因為 lifecycle 的 `stop_native`（OneCore `:192-195`；VE `_stopPlayer`，`:346`）在後繼之前也會 stop 一次、也會 latch。只有 eSpeak 的 `test_cancelled_feed_final_stop_finishes_before_successor_native_call` 殺得掉 M3（我重跑確認）。
- 核心程式碼有一個測試釘住就夠，但這兩個測試的名稱和訊息會誤導下一個改 lease 的人。建議二擇一：改名／改訊息為「在後繼之前被 stop」；或真的釘 lease：OneCore 在 fake 的 stop 裡記錄 `record.native.called`（lease 的 stop 發生在 callback 內、`called` 還是 False；lifecycle 的在 `_releaseSegmentWorker` 之後），VE 記錄 `env.core._callbackLocal.depth`（lease 的 stop 在 callback 內是 1，`_stopPlayer` 的是 0），斷言至少一次 stop 來自 callback 內。

### M2. drain 自己的 stop 沒有測試能和 lifecycle 的 stop 分開（M2a 存活；`OneCore:215-219`、`tests/test_onecore_segment_drain.py:604`、`:917`；VE `tests/test_vocalizer_segment_drain.py:435`）

- 我重跑 M2a（OneCore drain 只 `record_error` 不 stop）：`tests/test_onecore_segment_drain.py` 85 個全部通過，和帳本一致。`stops >= 1` 來自 `stop_native`／`stop_player`（上面「結論」追過的路徑），所以這個 stop 是防禦性的，spec §3.1、§9 已如實寫明；保留它和 SAPI5 對稱沒有壞處（多一次對已停 player 的 `stop()`，只在失敗路徑）。
- 不需要改程式。建議在 `test_sync_failure_fails_only_its_segment` 的註解「The drain stopped the player before reporting」改成「the drain or the lifecycle stopped…」，或把 M2a 的事實寫在測試旁邊，免得下一輪有人以為 `>= 1` 是在釘 drain 的 stop。

### M3. `ControlFaultPolicy.fail` 與 `deferred` 的區域變數 `local` 遮蔽了 `from threading import local`（`control:148`、`:159`；import 在 `:29`）

- 可讀性問題：同一個模組裡 `local` 既是型別又是實例。ruff 沒有抓（不是 F811）。建議改名為 `state`／`thread_state`。

### M4. spec §3.4 的 `_CallbackPlayer.feed admits host.callback_record()` 與實作不符，只在 §9 的 ruling 說明（spec `:120` 對 `:200`；plan Task 5 Interfaces `:128`）

- 帳本的 ruling 合理：`_callbackAdmission` 走 `host.consumer(record)`，准入就代表 `record is host.current()`（`host:376-383`），所以 lease 預設的「准入 current record」是同一筆；覆寫還得呼叫 `LeasedPlayer` 的私有 `_feed_admitted`。但 §3.4 正文仍寫舊設計，下一個讀 spec 的人會以為有 override。建議把 §3.4 那句改成現況（文件修改）。

### M5. 延到 P54 的「暫停中 drain 失敗 → 後繼在 NVDA 顯示暫停時播放」在 OneCore 其實不會發生，spec 的描述可以更精確（spec `:69`；`OneCore:592-594`）

- OneCore 每次 callback 的 `_maybeInitPlayer` 都會在 `_segmentPaused and _stopGate.clear` 時對 player `pause(True)`（不只換 player 時），所以 drain 失敗後的 stop 雖然清掉 WavePlayer 的 pause，後繼的第一個 callback 在 feed 之前就會把它重新暫停，後繼的 drain 再等 resume——使用者聽不到東西。VE／Cerence 沒有這個重新暫停，才會「後繼播放、NVDA 顯示暫停」；SAPI5 的 drain 和 VE 一般語音在 master 就已經如此。
- 延後可以接受：觸發條件是 `idle()`／`sync()` 在使用者暫停期間 raise，`WasapiPlayer` 幾乎不會（cons.md C2），而且 NVDA 任何新的 utterance 之前都會先取消暫停。建議 spec `:69` 把「OneCore 會重新暫停、只有 VE／Cerence 會播」寫清楚，P54 才知道範圍。

### 觀察（不需處理）

- `_maybeInitPlayer` 裡舊 player 的 `idle()` 現在走 lease（`OneCore:591` → `host:742-752`）：record 已被取消時 `consumer()` 不准入、idle 被略過。master 會對舊 player 做一次真的 `idle()`。只在取消路徑上有差，而且 cancel 的 stop 已經丟掉音訊，略過是安全的；正確路徑（換取樣率）照舊 idle。
- `host.retire` 對已取消一般語音的 stop 失敗（`host:521-525`）在 OneCore 從「只 log」變成「lease 先 latch 再 log」。這是規則的結果，spec §4「a failed player stop now rejects later speech」涵蓋，列在下面的預設清單。

## 使用者還沒確認的使用者可見預設

全部在 spec §3.1、§8 標為 `Decided by orchestrator with the recommended default; user may override before merge`；都只影響失敗路徑，正確路徑沒有變化。

1. **latch 規則本身**（`control:6-23`）：控制失敗（stop、purge、pause／resume、內層 cancel、原生資源釋放、無法證明 callback 已結束的原生呼叫）latch 引擎到重載為止；進度失敗（開／換 player、feed、`idle()`／`sync()`、原生合成、callback 處理）只讓那一筆失敗，失敗路徑的 stop 復位 player，stop 失敗才 latch。
2. **pause／resume 失敗、RHVoice 原生訊息刪除失敗、VE `_confirmNativeQuiescence` 失敗算控制失敗（latch）**——和 master 相同，只是改經 `ControlFaultPolicy`。
3. **OneCore 一般語音 callback 失敗改成完成那一句**（`OneCore:419-420`：佇列空且未取消時發一次 `DONE`，和 `ocSpeech_speak` 失敗的「跳過這句」相同），master 會 latch 並發一次 `DONE`。production 走不到一般路徑（cons.md §4），但若有一般語音排在後面的 segment 之前失敗，`DONE` 會由後面那筆的結尾發出，不是立刻。
4. **SAPI5 例外保留**：一般請求失敗仍 latch（單一 COM stream 無法把 purge 後的 callback 歸給下一筆，cons.md A12）。理由成立，而且 SAPI5 程式碼沒有動。
5. **延到 P54**：VE／Cerence 在使用者暫停期間 drain `idle()` 失敗 → stop 取消 player 的暫停 → 同一 utterance 的後繼 segment 會播，NVDA 仍顯示暫停（M5 說明 OneCore 不受影響）。
6. **VE／Cerence late-feed 的 stop 失敗從「只記錄」變成 latch**（spec §4；`VE:295-302` 的 finally 已移除，由 `host:712-716` 接手）。
7. **OneCore 任何 stop 失敗（含 `stop_native`／`stop_player`、`host.retire` 的 stop）都 latch**（C2 修正）；master 只有 `cancel` 裡的 stop 會 latch。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 完整套件（HEAD `80da555`，序列） | `scratchpad/p53/runtests.sh /workspace/WorldVoice-phase53 … -p no:cacheprovider tests`（背景 watchdog 每 2 秒讀 `/proc/meminfo`，MemAvailable < 3 GB 就 kill pytest） | **3596 passed／0 skipped**（107.04 s）；watchdog 沒有觸發；基準 3566 + 30 個新測試（engine_control 5、OneCore 8、vocalizer 3×2、RHVoice 1、guards 10）與 spec §9 相符 |
| prek | `prek run --all-files` | 8 個 hook 全 Passed |
| 空白 | `git diff --check`、`git diff master..HEAD --check` | 乾淨 |
| 受保護路徑 | `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' addon/synthDrivers/WorldVoice/driver/sonic/ …script_data.py …unspaced_common_data.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 都沒有輸出 |
| readme／翻譯 | `git diff --stat master..HEAD -- readme.md addon/doc` | 沒有變動（spec 要求） |
| wrapper 互相 import | 讀六個 wrapper 的 import 區塊 | 只 import `runtime/`、`bridge/` 與各自的 `.driver` |
| commit | `git log master..HEAD --format=%B` | 英文 `<type>: <summary>`，內文說明原因；沒有 `Co-Authored-By`；SAPI5、eSpeak 沒有變動 |
| VE／Cerence 同步 | 兩個 wrapper `git diff master..HEAD` 只留 `+`／`-` 行後 `diff` | **完全相同**；`git diff master..HEAD -- tests/test_vocalizer_drift.py` 為空 |
| `_feed_admitted` 參數轉發（Task 5 ruling） | 讀 `ref/nvda/source/nvwave.py:313-318`（`feed(data, size=None, onDone=None)`）、eSpeak `_espeak.py:185-193`、SAPI5 `_SegmentPlayer.feed`（自己呼叫 `_feed_admitted`）、RHVoice `_WavePlayer.feed` | 真 player 兩種寫法等價；SAPI5／RHVoice／eSpeak 的呼叫形式不變 |
| 鎖序 | 讀 `OneCore:585-597`、`:599-657`、`control:145-172`、`host:364-396`、`:434-437` | pause lock → `_segmentCondition` → host condition 不變；`deliver`／`after` 都在 pause lock 之外；`_afterControlFault` 內的 stop 失敗 → `fail()` 時 `depth` 已是 0 → `deliver(None)` no-op，不遞迴 |
| 後繼之前必有 stop（Review Focus 5） | 讀 `lifecycle:306-318`、`:394-407`、`:471-495`，`host:549-560`、`:573-580`、`:610-636` | 失敗紀錄 → `fail` → `request_stop`（`draining` 為真）→ `stop_native`；第二次 `wait_playback_drained` → `stop_player`；`handoff` 在 `lifecycle.run` 回來後才設，worker 的下一筆（含一般語音）要等它 |
| Review Focus 1–4 | 讀碼 + 下表突變 MV、MD、對應測試 | 1：路徑成立但測試釘的是「有 stop」不是「lease 的 stop」（M1）；2：`_callback` 原樣回傳 `on_done`，MV 殺掉；3：`test_cancel_pause_lock_stop_failure_delivers_after_lock_release` 釘住 deferred 交付；4：setter 包每個 player、MD 殺掉 |
| 帳本 7 個 Ruling | 逐一對照程式與 spec | 都合理：Task 3（deferred 只交付有捕到的 fault）、Task 4（`_REASONS` 搬移）、Task 5 ×2（見 M4、`_feed_admitted`）、Task 6 ×2（`>= 1` 見 M2；事件帶 stop error 是 `host:446-452` 既有順序）、Task 8（guard 命名放寬） |
| 實作者 M3 的說法 | scratch 複本拿掉 `host:712-716`，跑 eSpeak＋OneCore＋vocalizer 三個檔（`-x`） | `tests/test_espeak_segment_drain.py::test_cancelled_feed_final_stop_finishes_before_successor_native_call` 失敗（killed），與帳本一致 |

### 突變測試（審閱者自己的 9 個；scratch 複本 `scratchpad/p53rev/mut/`（`cp -r`，`ref` symlink），每個只換一個檔、跑該引擎的測試檔、跑完還原；腳本 `scratchpad/p53rev/runmut.sh`）

| # | 突變 | 結果 |
| --- | --- | --- |
| MA | OneCore `_legacyCallback` except 不 `record_error`（`OneCore:534`） | **survived**（85 passed）→ I1；我的 `sync` 版本測試殺得掉 |
| MC | `_speakRecord` 的 `or record.error is not None` 拿掉（`OneCore:419`） | killed（`test_ordinary_callback_failure_fails_only_its_sentence`） |
| MD | `_maybeInitPlayer` 對 `super()._maybeInitPlayer` 失敗 latch | killed（`test_player_replacement_failure_fails_only_its_segment`） |
| ME | segment `open()` 失敗 latch（`OneCore:386-387`） | killed（`test_segment_player_open_failure_fails_only_its_segment`） |
| M2a | OneCore drain 只記錄、不自己 stop（`OneCore:216-219`） | **survived**（已記錄；見 M2） |
| MV | `_OneCorePlayer._callback` 改回 `super()._callback`（`OneCore:125`） | killed（`test_index_fires_after_the_record_retired`） |
| MB | RHVoice `_WavePlayer._stop_failed` → `return None` | killed（`test_stop_fault_before_deferred_terminal_delivery_fails_closed`） |
| MO | VE `_CallbackPlayer._stop_failed` → `return None` | killed（`test_late_feed_after_cancel_is_stopped_and_stop_failure_latches[VE]`） |
| M3 | `LeasedPlayer._feed_admitted` 沒有 late stop（`host:712-716`） | killed（eSpeak，見上表） |

Linux 上的測試只驗證受控的 native 與音訊邊界；Windows 上的 NVDA、實際音訊裝置與引擎 SDK 沒有驗證到（spec §7.3 的 OneCore／VE／Cerence／RHVoice 正確路徑 smoke 仍待手動）。
