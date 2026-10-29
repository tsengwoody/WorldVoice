# Review：VE／Cerence 以最後一次原生呼叫的 `VE_MSG_ENDPROCESS` 標 `ENGINE_DONE`

日期：2026-10-29。分支：`fix/ve-endprocess-engine-done`（`31a1164..5add7e0`，1 個 commit；基準 `master` `31a1164`，collect 3523 個測試）。
審閱者：Fable 5.1（唯讀；只新增本檔）。流程：簡化流程（DEVELOPMENT_WORKFLOW.md §5），沒有 spec／plan，依 §3.3 的重點審閱；協調者另外指定要看 probe 的方法論是否真的證明了「成功返回 ⇒ 恰好一次 `ENDPROCESS` 且在最後」。

依據：

- 程式碼：`addon/synthDrivers/WorldVoice/driver/VE/__init__.py`、`driver/Cerence/__init__.py`、`runtime/barriers.py`、`runtime/segmentHost.py`（唯讀，看 `consumer`／`wait_consumers`／`retire`／`wait_playback_drained`）、內層 `driver/VE/driver/__init__.py` 的 `speak`／`_speak`／`BgThread`（唯讀）、`text/chunker.py`、`text/arabic.py`。
- 測試：`tests/test_vocalizer_segment_drain.py`、`tests/worldvoice_cancel_wrapper_harness.py`、`tests/test_native_strategy_guards.py`、`tests/test_vocalizer_drift.py`。
- 實測證據（分支 `SDKTest`，`ec53410`）：`docs/superpowers/handoff/ve_endprocess_probe.py`、`2026-10-29-ve-endprocess-sdk-test.md`、主 checkout 的 `docs/superpowers/handoff/ve_endprocess_probe.log`（5433 行，只用 grep／awk 彙整）。
- NVDA 原始碼（唯讀）：`ref/nvda/sconstruct`、`ref/nvda/user_docs/en/changes.md`、`ref/nvda/source/speech/speech.py`。
- 行號以 head `5add7e0` 為準；路徑省略 `addon/synthDrivers/WorldVoice/`。VE 與 Cerence 的行號相同，除了 `_retireRecord`（VE `:516-517`、Cerence `:518-519`）和 `_runNative`（VE `:588`、Cerence `:590`）。

## 結論

**程式碼正確、可以 merge；但實測證據有一個缺口（I1），建議在 merge 前補跑一次 32 位元的 probe，或由使用者明確接受這個缺口。** Critical 0、Important 1、Minor 4。

- **旗標的設定、記錄、讀取都在正確的位置，找不到「SDK 行為正確卻漏掉 `ENGINE_DONE`」的路徑。** 逐條核對：
  - `call.ended`（`:282`）在 `_process` 的 `ENDPROCESS` 分支最後、Sonic flush 與尾端 feed 之後設定，且在 `_processingLock` 內、只在 record 仍有效時。到這裡的 callback 一定經過 `_callbackAdmission`（`_nativeCall` 存在、`admitting`、instance 相等、`host.consumer` 收下、record 有效）。
  - `_runNative` 的 `finally`（`:581-588`）先 `_closeAdmission` 再 `host.wait_consumers(record)`，然後才讀 `call.ended` 寫進 `record.native.lastCallEnded`。所以即使 callback 在別的執行緒跑，只要它在呼叫返回前被收下，讀取就在它離開之後。probe 的 5427 次呼叫 `sameThread=True` 全數成立，實際上 `ENDPROCESS` 都在呼叫返回前、同一條執行緒完成。
  - 「最後一次呼叫勝出」靠的是內層 `BgThread` 的 FIFO（`driver/VE/driver/__init__.py:87-96`）：`_enqueue`（`:470-480`）把 `_Begin`、所有 `_NativeTask`、`_Retire` 依序排進同一個 queue，`_dropQueuedSpeech`（`:704-742`）重新放回時保持原順序；`_retireRecord` 在同一條執行緒讀 `lastCallEnded`，不需要跨執行緒同步。換語音時每個 `_NativeTask` 帶自己的 instance，`_callbackAdmission` 用 `call.instance` 比對，和 record 沒關係。
  - 中間呼叫沒有 `ENDPROCESS` 時尾端留在 Sonic 和 `_feedBuf`（兩者只在 `_beginRecord` → `_resetCallbackAudio` 時重設，`:507`、`:530-536`），下一次呼叫的 `ENDPROCESS` 一起沖出去，所以只看最後一次是對的。
  - 取消、`request_stop`、pause 失敗、`terminate` 都先讓 record 失效（`host._invalidate` 把 pending 都標 `cancelled`；pause 失敗 `record_error`），`_retireRecord` 的 `self._recordValid(record)` 擋住 reach，而 `wait_playback_drained` 對無效的 work 直接 `stop_player` 回傳，不檢查關卡；所以取消只會是取消，不會變成「缺 `engine_done`」的失敗。record 有效性是單調的（`cancelled`／`error`／work 失效都不會回復），因此 `:281` 的 `_recordValid` 檢查和 `:516` 的檢查等價（M6 存活，等價突變）。
  - 跳過的 record（`skipped`）走 `host.abandon`，不經過關卡；沒有原生呼叫的 record（序列只有語言切換之類、內層 `if chunks:` 不成立）`lastCallEnded` 預設 `True`，沒有尾端可丟，標 `ENGINE_DONE` 正確。
  - 原生呼叫丟例外或在 record 有效時回傳 `USERSTOP` → `returned=False` 或 `record_error`，segment 本來就失敗，`lastCallEnded` 沒有額外作用（M10 存活，等價突變）。
  - 一般語音：`_ORDINARY_BARRIERS = frozenset()` → `record.barriers == {}`，`:516` 的 `ENGINE_DONE in record.barriers` 擋住 reach。`lastCallEnded` 仍會被寫，但沒有讀者。
- **VE／Cerence 同步。** 兩個 wrapper 的差異只剩 drift 測試原本就允許的四處（`_PROFILE`、marker 讀法、admission 的 `isinstance`、`variants` 的 try），`tests/test_vocalizer_drift.py` 沒有 diff；我只拿掉 Cerence 的 `ENGINE_DONE` 宣告（M11）時 drift 測試立刻失敗。
- **守門與註解。** `DECLARED_BARRIERS` 的 VE／Cerence 列改成 `{AUDIO_FED, ENGINE_DONE, PLAYED_OUT}`／ordinary `set()`，和程式碼一致；`runtime/barriers.py:11-28` 對 `AUDIO_FED`「VE／Cerence 要和 `ENGINE_DONE` 一起才證明音訊全餵完」和 `ENGINE_DONE`「最後一次呼叫的 `ENDPROCESS`、在 record 有效時被收下、flush 與尾端 feed 之後」的描述和實作一致（見 M4 的位元數補充）。
- **限制。** 沒有碰 `driver/*/driver/*`、`driver/sonic/`、Unicode 資料檔；沒有 Neural；wrapper 沒有互相 import；commit message 是英文 `fix:` 格式、沒有 `Co-Authored-By`；`prek` 全過。
- **probe 的方法論**：送的字串和 add-on 一致（同一個 `ve2`／`ttsapi` ctypes 層、`open(voice, callback)` 相同、`VE_INTEXT` 的 UTF-8 長度算法相同、8 KB PCM／100 marker 的緩衝相同），25 種片段涵蓋 chunker 可能切出的末尾形狀（只有標點、只有空白、只有控制碼、100 字的長片段）。判定邏輯 `_verdict`：`OK` 且 `ENDPROCESS` 恰好一次且是最後一個訊息才算 `pass`；非 `OK` 只算 `info`，這是對的，因為 add-on 的 `ProcessText2Speech`（`:195-196`）對非 `OK`／`USERSTOP` 的結果本來就 raise，segment 不會走到關卡。log 彙整：VE 40 個語音 1000 pass／80 info，Cerence 161 個語音 4025 pass／322 info；info 全是空字串（`0x80000007`，無訊息；chunker 不會送空字串）和模擬取消（`USERSTOP` 後仍有且只有一次 `ENDPROCESS` 在最後）；`sameThread=False` 0 筆、呼叫外的 stray callback 0 筆；pass 的訊息序列全是 `BEGINPROCESS,(OUTBUFREQ,OUTBUFDONE)+,ENDPROCESS`；1967 筆 pass 的音訊是 0 位元組，證明不產生音訊的片段也有 `ENDPROCESS`。**結論成立，但只對 64 位元的 SDK 程式庫成立**（I1）。

## Critical

無。

## Important

### I1. probe 只跑了 64 位元的 SDK 程式庫；NVDA 2024.1–2025.x 的使用者載入的是 32 位元版（證據缺口，不是程式碼錯誤）

log 的開頭兩行：`VE … lib …\VE\lib\AMD64 Python 3.14.6 64-bit`、`Cerence … lib …\Cerence\lib\x64 Python 3.14.6 64-bit`。add-on 自己選程式庫的方式：VE 內層用 `os.environ["PROCESSOR_ARCHITECTURE"]`（`driver/VE/driver/ve2/__init__.py:93-94`），在 32 位元行程（WOW64）下是 `x86`；Cerence 內層用 `sys.maxsize`（`driver/Cerence/driver/ttsapi/__init__.py:88`），32 位元下是 `x32`。NVDA 從 2026.1 才改成 64 位元（`ref/nvda/user_docs/en/changes.md:794`「NVDA is now built with Python 3.13.12, 64-bit」），而 `buildVars.py` 的 `addon_minimumNVDAVersion="2024.1"`，所以 2024.1–2025.3 的使用者跑的是 `lib\x86`／`lib\x32` 的 `ve.dll`，這兩個二進位檔沒有被 probe 測過。commit message、`runtime/barriers.py:25`、`end_process` 的 docstring 都把結果寫成「VE SDK 2.2.0／Cerence SDK 21.6.0」而沒有標位元數。

失敗情境：如果 32 位元版的 `ve.dll` 在某種片段（例如只有控制碼或只有空白）回 `OK` 卻不送 `ENDPROCESS`，那些使用者的每一段以該片段結尾的語音都會變成 `SEGMENT_FAILED`，scheduler 取消整個 request，後面的段落不唸——而且這是 add-on 以前沒有的失敗。同版本的 SDK 兩種位元數行為不同的機率很低，但這正是這次改動唯一的新風險，而補證據很便宜。

建議修法（不改程式碼）：在同一台 Windows 用 32 位元 Python 再跑一次 `ve_endprocess_probe.py`（handoff 文件 §2 已寫明兩種位元數各跑一次），把 log 附在 `SDKTest` 分支或 `storage/refactor9.md` 那一列，並在 `runtime/barriers.py:25` 和 `end_process` docstring 加上「32／64 位元程式庫都測過」。如果使用者決定不補，請把「32 位元 NVDA 上未實測」列為未確認的使用者可見預設，寫進回報與 refactor9 那一列。補 log 之後不需要 §3.4 的修正 review（沒有程式碼 diff）。

## Minor

### M1. `test_ordinary_speech_needs_no_endprocess` 的 stub 不送 `ENDPROCESS`，所以沒有測到真正保護一般語音的那個條件（`tests/test_vocalizer_segment_drain.py:1893-1897`）

測試用 `emit(env, instance, end=False)`，於是 `lastCallEnded` 是 `False`，`_retireRecord:516` 不論有沒有 `ENGINE_DONE in record.barriers` 都不會 reach。真實的一般語音每次呼叫都有 `ENDPROCESS`，`lastCallEnded` 是 `True`，這時唯一擋住 `host.reach(record, ENGINE_DONE)` 對空 `barriers` dict 丟 `KeyError` 的就是那個 `in` 檢查。我的突變 M8（把 `in` 檢查拿掉）在 `tests/test_vocalizer_segment_drain.py` 全部 181 個測試下存活；把這個測試的 stub 改成 `emit(env, instance)`（預設 `end=True`）後，M8 立刻被殺（`KeyError` 在 BgThread 被內層 `log.error` 吃掉，record 永遠不 retire，`outcomes` 為空），而未突變的程式碼兩個引擎都通過。

失敗情境：日後有人把 `:516` 整理成「`_recordValid and lastCallEnded`」（看起來只是去掉多餘的 `in`），一般語音每一句都在 BgThread 丟 `KeyError`、不 retire、不發 DONE，測試全綠。

建議修法：把 stub 改成 `emit(env, instance)`（送 `ENDPROCESS`，和 SDK 一樣），測試名稱和斷言都不用動；要保留「沒有 `ENDPROCESS` 也不影響一般語音」這一層，可以用 `parametrize("end", [True, False])`。

### M2. `test_shared_lifecycle_waits_for_chunk_callback_and_idle` 的訊息順序是人造的，註解卻寫得像 SDK 的行為（`tests/test_vocalizer_segment_drain.py:129-133`）

新版先在呼叫執行緒送 `ENDPROCESS`，再在另一條執行緒送 `OUTBUFREQ`／`OUTBUFDONE`，呼叫在 feed 還卡著時返回。SDK 不會這樣做（`ENDPROCESS` 永遠最後、永遠同執行緒）。我判斷這個改法**可以接受**：測試要證明的是「BgThread 在 retire 和 idle 之前會等還在 feed 的 callback 離開」（`wait_consumers`），這一點仍然成立（事件在 `feed_release` 之前是空的、idle 在 feed 之後才進入、最後 `SEGMENT_DRAINED`）；而且沒有別的順序可用——chunk 先、`ENDPROCESS` 後在同一條執行緒會被 `_processingLock` 串成「chunk 做完才輪到 `ENDPROCESS`」，呼叫返回時 consumer 已經離開，就測不到 `wait_consumers`；`ENDPROCESS` 放到 chunk 那條執行緒上、在呼叫返回之後送，會被 `_closeAdmission` 拒收，segment 以缺 `engine_done` 失敗——這正是設計上的限制：`ENGINE_DONE` 只在 callback 同步於呼叫時成立。同一個理由也說明我的突變 M7（把 `lastCallEnded` 的寫入搬到 `wait_consumers` 之前）為什麼沒有測試能殺：它只在非同步 callback 下才是錯的，而非同步 callback 的 `ENDPROCESS` 本來就會被拒收。

建議修法：把 `:130-131` 的註解改成明說「這個順序是人造的：SDK 的 `ENDPROCESS` 一定最後且同執行緒；這裡提前送它，只為了讓 chunk callback 在呼叫返回後還在 feed，測 `wait_consumers`」；並在 `_runNative:586-587` 的註解加一句「`ENGINE_DONE` 依賴 callback 在呼叫返回前完成（probe：`sameThread=True`）」，讓依賴寫在它成立的地方。

### M3. probe 的片段清單還有幾種 add-on 會送、但沒測的形狀（`docs/superpowers/handoff/ve_endprocess_probe.py` `PIECES`；補跑 32 位元時一起加）

- 控制字元與零寬字元：NVDA 的文字可能含 `​`、`﻿`、`‎`／`‏`、`\x07`、`\x7f`，以及 `encode("utf-8", "replace")` 把孤立 surrogate 換成的 `?`；chunker 切出來的末尾片段可能只剩這些。這類片段如果 SDK 回非 `OK`，add-on 本來就 raise（不是新風險）；但如果回 `OK` 而無訊息，就是這次關卡唯一會誤判的形狀，而 probe 沒有涵蓋。
- 很多控制碼的片段：拼字模式下 NVDA 在每個字元之間放 `IndexCommand`，chunker 不計控制碼長度，一個片段可能是 100 個字元加 100 個 `\mrk=`；probe 最多一個片段兩個控制碼。
- `USERSTOP` 之後的下一次呼叫：add-on 取消後會用同一個 instance 繼續說，probe 的 `stop-after-2-buffers` 是每個語音的最後一筆，沒有驗證 `USERSTOP` 之後 instance 的訊息流程是否還正常。
- 參數：add-on 會先 `TtsSetParamList`（rate／pitch／volume／variant／waitfactor）再呼叫，probe 全用預設；影響訊息流程的機率很低，記錄一下即可。

建議修法：在 `PIECES` 加上述片段，把 `STOP_PIECE` 之後再送一個 `text` 片段並計分。

### M4. 證據的位元數沒有寫進註解（`runtime/barriers.py:25`、`tests/worldvoice_cancel_wrapper_harness.py:307-311`、commit message）

三處都寫「a Windows SDK probe」／「VE 2.2.0, Cerence 21.6.0」，沒有說是哪個 `lib` 資料夾。日後看到這些註解的人會以為兩種位元數都證明過。I1 補跑之後一併改成「64／32 位元程式庫都測過」；不補跑則改成「64 位元程式庫（NVDA 2026.1+）」。

## 使用者還沒確認的使用者可見預設

- VE／Cerence 的 segment 在最後一次原生呼叫沒有收到（或被拒收）`ENDPROCESS` 時，現在會以「`VE synthesis retired without its engine_done barriers`」失敗，scheduler 取消該 request 其餘段落；以前會靜默丟掉尾端音訊、segment 照常 drained。這是這次改動的目的，但是使用者可見的行為改變。
- 32 位元 NVDA（2024.1–2025.3）上未實測（I1）。
- 未打包、未在 Windows 上以 NVDA 驗證（簡化流程）。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 完整套件（head `5add7e0`，序列） | `cd /workspace/WorldVoice-veendprocess; python3 -m pytest -q tests`，背景 watchdog 每 2 秒讀 `/proc/meminfo`，MemAvailable < 3 GB 就 kill pytest（腳本 `scratchpad/run_tests.sh`） | **3535 passed／0 skipped**（104.08 s）；watchdog 沒有觸發；`master` collect-only 3523 → +12 ＝ 6 個新測試 × VE／Cerence |
| prek | `prek run --all-files` | 8 個 hook 全 Passed |
| 空白 | `git diff --check master..HEAD` | 乾淨 |
| 受保護路徑 | `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' addon/synthDrivers/WorldVoice/driver/sonic/ …script_data.py …unspaced_common_data.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 都沒有輸出 |
| wrapper 互相 import | `grep -n "from synthDrivers.WorldVoice.driver\.\(VE\|Cerence\|RHVoice\|eSpeak\|OneCore\|SAPI5\)" driver/VE/__init__.py driver/Cerence/__init__.py` | 無 |
| commit | `git log -1 --format=%B` | 英文 `fix:` 格式，內文說明原因與證據；沒有 `Co-Authored-By` |
| VE／Cerence 同步 | `git diff master..HEAD -- tests/test_vocalizer_drift.py`；`diff` 兩個 wrapper（Cerence 換名後） | ALLOWED 無 diff；實際差異只有 `_PROFILE`、`szValue`／`ulMrkId`、admission 的 `isinstance`、`variants` 的 try，都是原本允許的 |
| 還原修正後新測試是否失敗 | scratch 複本（`scratchpad/mut/`，`git ls-files` 複製 + `ref` symlink）把兩個 wrapper 換成 `master` 版，跑分支的 `-k "engine_done or endprocess"` | 4 failed／14 passed：`test_last_call_without_endprocess_fails_the_segment[VE/Cerence]`、`test_refused_endprocess_does_not_reach_engine_done[VE/Cerence]`；其餘四個（每次都有 `ENDPROCESS`、只有最後一次需要、沒有原生呼叫、一般語音）在 `master` 也通過，符合「行為不變」的設計 |
| probe 方法論 | 讀 `ve_endprocess_probe.py`（`_process`、`_Recorder`、`_verdict`、`PIECES`）對照 `ProcessText2Speech:174-197`、`ve2.open:115`、內層 `speak:349-435`、`chunker.py`、`CHUNK_SEPARATOR = "  "`（`speech.py:172`） | 送的字串、open 參數、緩衝大小與 add-on 一致；`pass` 的條件是 `OK` ∧ `ENDPROCESS` 恰好一次 ∧ 是最後一個訊息；非 `OK` 不計分是對的（add-on 對非 `OK`／`USERSTOP` 本來就 raise）；涵蓋缺口見 M3 |
| probe log 彙整 | `grep -o "^\[[a-zA-Z]*\]" … \| sort \| uniq -c`、`grep -c sameThread=False`、pass 的 `msgs=` 去重、info 行去重、`grep stray` | 5025 `[pass]`／402 `[info]`；info ＝ 201 筆空字串 `0x80000007 endprocess=0 msgs=`（每個語音一筆）＋ 201 筆 `USERSTOP endprocess=1 …,ENDPROCESS`；`sameThread=False` 0；stray 0；pass 序列全為 `BEGINPROCESS,(OUTBUFREQ,OUTBUFDONE)+,ENDPROCESS`；1967 筆 pass `audio=0B`；25 種片段每種 97 筆（40 VE＋161 Cerence 的子集合） |
| probe 的位元數 | log 第 1、1084 行；`ve2/__init__.py:93`、`ttsapi/__init__.py:88`；`ref/nvda/user_docs/en/changes.md:613,794`；`buildVars.py:39` | 只跑了 `lib\AMD64`／`lib\x64`、Python 3.14.6 64-bit；NVDA 2026.1 起 64 位元，add-on 最低支援 2024.1 → I1 |
| `DECLARED_BARRIERS` 守門 | 在完整套件內；M11 | 通過；M11 被 drift 測試殺掉 |

### 突變測試（審閱者自己的 11 個；scratch 複本 `scratchpad/mut/`，兩個 wrapper 同時突變，`PYTHONDONTWRITEBYTECODE=1 pytest -q -x -p no:cacheprovider tests/test_vocalizer_segment_drain.py`，每次先清 `__pycache__`，跑完還原；腳本 `scratchpad/mutrun.py`）

| # | 突變 | 結果 |
| --- | --- | --- |
| M1 | 拿掉 `_process` 的 `call.ended = True`（`:281-282`） | killed（`test_shared_lifecycle_waits_for_chunk_callback_and_idle`） |
| M2 | `lastCallEnded = returned or call.ended` | killed（`test_last_call_without_endprocess_fails_the_segment`） |
| M3 | `lastCallEnded` 預設 `False` | killed（`test_zero_audio_segments_still_wait_for_real_idle[empty]`） |
| M4 | `_retireRecord` 不看 `lastCallEnded` | killed（`test_last_call_without_endprocess_fails_the_segment`） |
| M5 | 改成「每一次呼叫都要有 `ENDPROCESS`」（`lastCallEnded and returned and call.ended`） | killed（`test_only_the_last_call_needs_endprocess`） |
| M6 | `call.ended = True` 不檢查 `_recordValid` | **存活**：等價——record 有效性單調，`_retireRecord:516` 再檢查一次 |
| M7 | `lastCallEnded` 寫在 `wait_consumers` 之前 | **存活**：只在非同步 callback 下才錯，而那種 `ENDPROCESS` 本來就會被拒收（M2 說明） |
| M8 | 拿掉 `:516` 的 `ENGINE_DONE in record.barriers` | **存活** → M1（把一般語音測試的 stub 改成送 `ENDPROCESS` 後 killed） |
| M9 | 在 `OUTBUFDONE` 分支也設 `call.ended = True` | killed（`test_last_call_without_endprocess_fails_the_segment`） |
| M10 | `lastCallEnded = call.ended`（不看 `returned`） | **存活**：等價——呼叫丟例外時已 `record_error` |
| M11 | 只有 Cerence 拿掉 `ENGINE_DONE` 宣告 | killed（`test_vocalizer_drift.py::test_cerence_differs_from_ve_only_where_allowed`） |

## 修正記錄

修正者：Opus 5.5（簡化流程，依 §3.4）。只有 Minor 需要在本分支修，沒有 Critical／Important 的程式碼修正，所以不做修正 review。

| 發現 | 處理 | commit |
| --- | --- | --- |
| I1 | 不在本分支處理：probe 在 `SDKTest` 分支擴充中，使用者會在 Windows 上用 32 位元 Python 執行。在 32 位元結果出來之前，「32 位元 NVDA（2024.1–2025.3）上未實測」仍是未確認的使用者可見預設。 | — |
| M1 | `test_ordinary_speech_needs_no_endprocess` 改成 `parametrize("end", [True, False])`，`end=True`（SDK 的實際順序）讓 `lastCallEnded` 為 `True`，此時只剩 `_retireRecord` 的 `ENGINE_DONE in record.barriers` 擋住 reach。突變驗證：scratch 複本中 VE、Cerence 兩個 wrapper 同時拿掉這個 `in` 檢查，`[VE-endprocess]`、`[Cerence-endprocess]` 失敗（`outcomes` 為空，record 沒有 retire），`no-endprocess` 兩個仍通過；還原後 4 個都通過。 | `bb5b188` |
| M2 | 測試註解改成明說訊息順序是人造的（SDK 的 `ENDPROCESS` 一定最後、同執行緒），並說明為什麼這是證明 `wait_consumers` 的唯一方式；VE 與 Cerence 的 `_runNative` 加上相同註解：`ENGINE_DONE` 依賴 SDK 在呼叫內、同一條執行緒跑 callback（probe 每次呼叫都 `sameThread=True`），呼叫返回後才到的 `ENDPROCESS` 會被拒收、不算數。 | `39cadcd` |
| M3 | 不在本分支處理：probe 在 `SDKTest` 分支擴充中（片段清單、`USERSTOP` 之後的呼叫等），使用者會在 Windows 上用 32 位元 Python 執行。 | — |
| M4 | `runtime/barriers.py` 的 `ENGINE_DONE` 註解和 `end_process` 的 docstring 註明證據來自 64 位元程式庫（VE SDK 2.2.0 `lib\AMD64`、Cerence SDK 21.6.0 `lib\x64`）。32 位元結果出來後再改成兩種位元數都測過。既有的 commit message（`5add7e0`）不改寫。 | `1a52b68` |

VE／Cerence 保持同步：`tests/test_vocalizer_drift.py` 的 `ALLOWED` 沒有變動，drift 測試通過。

### 32 位元 probe 之後（2026-10-29）

使用者在 Windows 上以擴充後的 probe（分支 `SDKTest`，`eb1a92f`）分別用 32 位元與 64 位元 Python 各跑一次，log 在主 checkout 的 `docs/superpowers/handoff/ve_endprocess_probe-32bit.log` 與 `ve_endprocess_probe-64bit.log`。

| 發現 | 處理 | commit |
| --- | --- | --- |
| I1 | **已解決。** 32 位元：Python 3.11.9 32-bit，VE SDK 2.2.0 `lib\x86`（40 個語音，2440 pass／120 info）、Cerence SDK 21.6.0 `lib\x32`（161 個語音，9499 pass／805 info）。64 位元（Python 3.14.6，`lib\AMD64`／`lib\x64`）用同一組擴充片段重跑，數字相同，逐筆判定和 32 位元一致。兩次都是 0 筆 FAIL／WARN／ERROR、0 個呼叫外的 callback、0 筆 `sameThread=False`；每次 11939 筆成功呼叫都恰好一次 `ENDPROCESS` 且在最後（`BEGINPROCESS,(OUTBUFREQ,OUTBUFDONE)+,ENDPROCESS`），其中 4813 筆不產生音訊。「32 位元 NVDA（2024.1–2025.3）上未實測」不再是未確認的預設。 | — |
| M3 | **已解決。** 擴充片段涵蓋：控制字元（BEL、DEL、C0、C1）、零寬字元（ZWSP、ZWNJ、ZWJ、word joiner、BOM、LRM、RLM、soft hyphen）、孤立 surrogate、拼字模式（含 chunker 切出的三段各 250 個拼字字元加 bookmark）、只有 100 個 bookmark、同一個 instance 在 `USERSTOP` 之後的下一次呼叫、rate／pitch／volume／waitfactor 的最小與最大參數，全部 pass。只列為 info：空字串（`0x80000007`，無訊息）、NUL、`USERSTOP` 那次呼叫本身（之後仍有 `ENDPROCESS`）、Cerence 的 `\rate=`／`\vol=`（內層驅動不會送；結果仍是 `OK` 且有 `ENDPROCESS`）。 | — |
| M4 | `runtime/barriers.py` 的 `ENGINE_DONE` 註解、`end_process` 的 docstring、VE／Cerence 的 `_runNative` 註解改成 32 位元（`lib\x86`／`lib\x32`）與 64 位元（`lib\AMD64`／`lib\x64`）程式庫都測過。VE 與 Cerence 保持相同，`tests/test_vocalizer_drift.py` 的 `ALLOWED` 沒有變動。 | `bdbbf91` |
