# Review：`SynthDriver._set_voice` 不再直接停止舊語音的引擎（`fix/set-voice-no-stop`）

日期：2026-10-29。分支：`fix/set-voice-no-stop`（`c6b5a73..2c6d7b5`，3 個 commit：`79bf6c9` 拿掉 `_set_voice` 的 `stop()` 並加回歸測試、`7ea63a6` 刪除 `VoiceFacade.stop` 並加守門測試、`2c6d7b5` 六份 readme 的變更紀錄；基準 `master` `c6b5a73`）。
審閱者：Fable 5.1（唯讀；只新增本檔）。流程：簡化流程（DEVELOPMENT_WORKFLOW.md §5），沒有 spec／plan，依 §3.3 的重點審閱；協調者另外指定七個重點：拿掉 stop 在每條 `_set_voice` 呼叫路徑上是否安全、回歸測試是否真的在舊程式碼上紅、守門測試是否精準、`VoiceFacade.stop` 的外部使用者、readme 文字、殘留的過時描述、第 8 節的限制。

依據：

- 程式碼：`addon/synthDrivers/WorldVoice/__init__.py`（`_set_voice:401-408`、`speak:296-311`、`cancel:332-335`、`loadSettings:287-291`）、`bridge/voiceFacade.py`、`voices/manager.py`（`default_voice_name` setter `:188-194`、`cancel:255-257`）、`voices/mainLocalePolicy.py`（`follow:63-65`）、`runtime/scheduler.py`（`cancel:428-441`、`_stop_playback:413-417`）、`runtime/session.py:188-189`、`bridge/engineAdapter.py:194-197`、`runtime/segmentHost.py`（`cancel:292-294`、`_invalidate:693-699`）、`runtime/_segmentLifecycle.py`（`cancel:386-392`）、`bridge/completionPolicies.py:98-103`、`driver/SAPI5/__init__.py:710-731`、`globalPlugins/WorldVoice/panels/role.py:39-43`。
- NVDA（`ref/nvda/source`，唯讀）：`synthDriverHandler.py`（`loadSettings:386-413`、`changeVoice:439-448`、`handlePostConfigProfileSwitch:582-600`）、`speech/manager.py`（`_switchProfile:732-750`）、`synthDrivers/espeak.py:327-339`、`oneCore.py:620-627`、`sapi5.py:759-773`／`_initTts:730`、`inputCore.py:593`、五個語言的 `locale/*/LC_MESSAGES/nvda.po`。
- 外掛：`ref/Neural/Neural/__init__.py`（唯讀）。
- 測試：`tests/test_set_voice_in_flight.py`、`tests/test_hygiene_guards.py:248-327`、`tests/test_worldvoice_speak.py:279-324`、`tests/test_voice_settings_transaction.py:105-118`、`tests/test_runtime_voice_facade.py`、`tests/runtime_drain_integration_harness.py`、`tests/espeak_drain_harness.py`、`tests/addon_loader.py`（`load_definitions`）。
- 文件：六份 readme 的 `:102`、`docs/superpowers/specs/2026-10-05-phase10a-voice-manager-design.md:108`、`storage/refactor9.md:460-461`（使用者的檔案，唯讀）。
- 行號以 head `2c6d7b5` 為準；路徑省略 `addon/synthDrivers/WorldVoice/`。

## 結論

**修正正確、範圍最小、可以 merge。** Critical 0、Important 0、Minor 5（都是文字與測試的收尾，沒有一項擋 merge；M1 的 spec 修正依 §5.7 由協調者在 `master` 補）。

- **拿掉 stop 在每條路徑都安全。** `_set_voice` 的呼叫者只有 NVDA 的 `changeVoice`（`synthDriverHandler.py:439-448`，被 `loadSettings:386-413` 與設定對話框呼叫）和 WorldVoice 自己的語音角色面板（`panels/role.py:42` `current.voice = name`）。逐條核對：
  - 設定環、設定對話框、按鍵中斷 say-all、換 synth（`setSynth:522/530` 先 `cancel()`）、`resetConfiguration`：NVDA 先取消或根本沒有語音在飛，前後行為相同。
  - say-all 設定檔：NVDA 把 `ConfigProfileTriggerCommand` 排在語句之間，`_switchProfile:732-750` 在前一句 DONE 之後才 `handlePostConfigProfileSwitch(resetSpeechIfNeeded=False)`，所以引擎是閒置的；不受影響。
  - 非按鍵的 app／focus 切換：`handlePostConfigProfileSwitch:593-600` 只在 synth 或輸出裝置改變時 `cancelSpeech()`，否則直接 `loadSettings(onlyChanged=True)` → `_set_voice`，語音可能在飛。這正是修掉的卡住路徑；修正後當下這個 request 的 task 都綁在排入時的 voice key（`speak:307-311` 把 `default_voice_name` 交給 `queue_speech_sequence`），用舊語音講完，下一句（NVDA 在 DONE 之後才送）用新語音。「舊語音繼續講」的範圍就是當下這個 NVDA utterance，不會延伸；scheduler 逐 task 等 drain（或 LEGACY 的 DONE），不會兩個語音重疊——原註解引用的 #3540（兩個 Vocalizer 實例同時講）在這個架構下靠 scheduler 解決，不靠 stop。
  - 語音驗證：setter `:190-192` 對不在 catalog 的名稱先 `raise LookupError`，現在連 stop 都不做就拋出，`_voice` 不變，NVDA `loadSettings:393-398` 照常修回 config；`test_choosing_an_unavailable_voice_raises_and_changes_nothing` 與 `test_main_synth_records_a_chosen_voice_only_once_it_is_set` 釘住。
  - `keepMainLocaleVoiceConsistent`／`keepMainLocaleEngineConsistent`：setter 之後的 `on_keep_engine_consistent`（`roles.prune`）和 `follow:63-65`（`roles.assign`）只改角色設定，不碰引擎；變體與語言改變走 `_setVoiceParameter`，沒有 stop，本來就不受影響。
  - LEGACY／plain 後備（NVDA 2024.1–2025.2 的 SAPI5 走 NVDA 自己的驅動，`driver/SAPI5/__init__.py:714-731`；或測試的 `forceUnverifiedDrain=False`）：舊 stop 靠「`core.cancel()` 不取消 token，DONE 放行」讓 request 完成；現在根本不 stop，引擎自己講完送 DONE，`LEGACY_DONE` 規則（`runtime/completion.py:66-75`）照常完成。只會更穩。
  - 正式程式碼裡再沒有繞過 scheduler 的引擎停止：`SynthDriver.cancel:335` → `VoiceManager.cancel:255-257` → `TaskManager.cancel(ports)`；守門測試的掃描（我用同一個 `_engine_stops()` 把全部 `stop()`／`cancel()` 呼叫連同 receiver 末字 dump 出來）只剩 player、host、token、future、work、lifecycle、manager、self／super 這些合法 receiver。
- **回歸測試真的紅。** 把分支的四個測試檔放進 `master` 的 scratch 複本：13 failed／181 passed；八個新回歸測試全部失敗，而且失敗的方式就是 production 的症狀——`during_native` 是「player idle 1 did not start」（host 把被 stop 的 segment 靜音，沒有 drain），`during_playback` 是「native call 2 did not start」（scheduler 卡在 `AWAITING_COMPLETION`，第二段永遠不開始），eSpeak 是 `future.result` 的 `TimeoutError`。分支上全綠；12 次重複（每次 178 個測試）與 3 個並行行程同時跑都沒有抖動；所有等待都用 Event／Condition 加 `WAIT_TIMEOUT`，沒有 sleep。`_synth_driver` 用 `load_definitions(..., members={"_set_voice"})` 載入的是真的 `SynthDriver._set_voice`，OneCore／VE／Cerence 走真的 `VoiceManager` 與 wrapper，eSpeak 走真的 `VoiceFacade`／`EngineSession`／eSpeak wrapper，只有 adapter 是埠。我在分支的 scratch 複本把 stop 以四種寫法加回 `_set_voice`（`._binding.session.cancel()`、`.core.cancel()`、先取別名再 `engine.cancel()`、`._adapter.cancel()`），八個回歸測試每一種都抓到。
- **守門測試精準、不脆。** 掃描只對 `stop`／`cancel` 兩個屬性名加 receiver 末字的 8 個詞，現況只命中 scheduler 取消鏈的三個 hop；`test_every_engine_cancel_hop_is_still_in_place` 讓改名時測試必然失敗而不是靜靜放行；`test_voices_offer_no_stop_or_cancel` 擋住最直接的重犯（在 `Voice`／`VoiceFacade` 加回 stop）。唯一繞過方式是先取別名（見 M3），而回歸測試仍然會抓到。它沒有禁止任何合法程式：wrapper 自己的 `_player.stop()`、`host.cancel()`、`super().cancel()`、`token.cancel()`、`future.cancel()` 都不在詞表裡。
- **`VoiceFacade.stop` 沒有別的使用者。** addon 內只有 `_set_voice` 呼叫過；`ref/Neural` 的 `Voice` 只宣告 `core`、`engine`、`synthDriverClass`，驅動內層自己的 `cancel()`／`_player.stop()` 和 facade 無關；測試只有被刪的 `test_stop_cancels_the_shared_session_without_closing_it`。唯一的契約文件是 phase 10a spec 把 `stop()` 列為保留成員（M1）。
- **readme。** 六份都放在「下一版更新」（`## Next update`）之下，內容互相一致；每個語言都用 NVDA 自己的「組態設定檔」譯名（我對過 `nvda.po`：zh_TW「組態設定檔」、zh_HK「組態設定」、zh_CN「配置」、ru「профиль конфигурации」、uk「конфігураційний профіль」）；zh_HK 與 zh_TW 除了這個詞仍然逐字相同。「先前版本會中斷正在說的內容」對已發行的 6.2 是對的（6.2 的 stop 真的切斷語音），沒有提到只存在於未發行 drain 模式的卡住，正確。沒有動 `addon/doc/en/` 和 `.html`。兩個可選的修辭建議見 M4、M5。
- **限制。** 沒有碰 `driver/*/driver/*`、`driver/sonic/`、Unicode 資料檔；沒有 Neural；驅動沒有互相 import；三個 commit message 都是英文 `fix:`／`refactor:`／`docs:` 格式、內文說明原因；沒有 `Co-Authored-By`；`prek` 8 個 hook 全過；`git diff --check` 乾淨。

## Critical

無。

## Important

無。

## Minor

### M1. phase 10a spec 仍把 `stop()` 列為 `VoiceFacade` 的保留成員（`docs/superpowers/specs/2026-10-05-phase10a-voice-manager-design.md:108`）

該行「`snapshot()`、`update_settings()`、`loadParameter()`、`commit()`、`stop()`」是 facade 對外 API 的唯一書面契約，`7ea63a6` 把 `stop()` 刪了。依 DEVELOPMENT_WORKFLOW.md §5.7，merge 後由協調者在 `master` 補一個 docs commit：`~~stop()~~` 保留刪除線，標註「Corrected by `fix/set-voice-no-stop`：`stop()` 繞過 scheduler，在逐段語音模式會讓 request 等不到 drain，已刪除；引擎只經 `TaskManager.cancel` 停止」。phase 19（interface DIP）、phase 21、phase 22 的 spec 都沒有提到這個 stop，不用改。`storage/refactor9.md:460` 的「進行中」是使用者的檔案，由使用者更新。

### M2. 過時註解：`tests/test_worldvoice_request_manager.py:688`「Like SynthDriver._set_voice(): stop the core without cancelling the request.」

`_set_voice` 已經不這樣做，而守門測試現在保證正式程式碼沒有任何「只停 core、不取消 request」的呼叫者。這個測試釘住的是 VE／Cerence plain 路徑的 wrapper 契約（直接 `core.cancel()` 後 DONE 仍放行、下一段仍能跑），和 `storage/refactor9.md:461` 的候選項（拿掉 VE／Cerence 的 token 與 `withdraw`）直接相關——那個候選項的前提就是本分支。建議把註解改成「A direct core stop that bypasses the scheduler. No production caller since fix/set-voice-no-stop (the hygiene guard forbids one); kept as the wrappers' plain-path contract until that contract is dropped.」順便讓那個候選項的評估者一眼看到這個測試要跟著處理。其他地方（`tests/test_hygiene_guards.py:252` 的「once did that」、commit message）都已經是過去式，正確。

### M3. 守門測試的末字詞表可以多三個零成本的詞（`tests/test_hygiene_guards.py:260-262`）

`_ENGINE_ENDPOINTS` 是 voice／instance／facade／session／playback／port／adapter／core。facade 的 `core` 是各 wrapper 的 `SynthDriver` 實例，最自然的別名是 `driver`、`engine`、`synth`；我的突變「`engine = …default_voice_instance.core; engine.cancel()`」守門測試放行（回歸測試抓到了，所以不是漏洞，只是守門少一層）。用分支自己的掃描確認：addon 裡沒有任何 `stop()`／`cancel()` 的 receiver 末字是這三個詞（RHVoice 的 `self._driver()._inner.player.stop()` 末字是 player），所以加進去不會誤判任何現有程式。建議 `frozenset({…, "driver", "engine", "synth"})`，並在上一行的註解補上這三個例子。靠名字的守門本來就擋不住任意別名，這點 commit message 已經說清楚，真正的網是回歸測試；這項只是把最可能的寫法也擋住。

### M4. 回歸測試把 `keepMainLocaleVoiceConsistent` 關掉，production 預設是開的（`tests/test_set_voice_in_flight.py:42`）

關掉只是因為 `assemble()` 的 config 沒有這個鍵，`follow:63-65` 讀它會 `KeyError`。我在 scratch 複本改成 `True` 跑了八個案例，全部通過（`roles.assign` 只寫 config 的 `role` 區段，不碰引擎），所以行為上沒有差別。建議改成 `True`（或參數化兩個值），讓測試走和使用者相同的預設路徑，`_set_voice` 的 setter 連 `follow` 的 `assign` 一起被證明不會卡住 request；一行改動。

### M5. readme：「與 NVDA 內建的語音合成器相同」對 SAPI5 不完全成立，而且整條可以再短（六份 `:102`）

NVDA 的 eSpeak（`espeak.py:327-339`）與 OneCore（`oneCore.py:620-627`）換語音確實不停止；但 NVDA 的 SAPI5 `_set_voice:759-773` 會 `_initTts(voice=…)` 重建 tts 物件並 `_stopThread()`，等於切斷。這句話是對使用者的類比，不是技術宣告，保留也無妨；若要精確又更短，建議（zh_TW 為準，其餘語言同步）：

> * **說話時切換語音不再中斷語音：** 例如切換應用程式時啟用了使用另一個語音的組態設定檔，正在說的內容會用原本的語音說完，之後才使用新的語音。先前版本會中斷正在說的內容。

英文對應：

> * **Changing the voice while speaking no longer cuts off speech:** For example, when a configuration profile with another voice becomes active as you switch applications, the speech under way finishes in the previous voice and later speech uses the new voice. Earlier versions cut off the speech under way.

拿掉了「WorldVoice 正在說話時語音改變了」（標題已經說了）和「與 NVDA 內建的語音合成器相同」。zh_HK 用「組態設定」、zh_CN 用「配置」、ru／uk 保留現有譯名即可。可選；現有文字也正確。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 完整套件（序列） | `python3 -m pytest -q tests`，背景 watchdog 每 2 秒讀 `/proc/meminfo`，MemAvailable < 3 GB 就 kill pytest（`scratchpad/review/run_full.sh`） | **3583 passed／0 skipped**（105.11 s）；watchdog 沒有觸發 |
| 舊程式碼上紅 | `git archive master` 解到 scratch（`tarfile`，`ref` 用 symlink），複製分支的 `test_set_voice_in_flight.py`、`test_hygiene_guards.py`、`test_worldvoice_speak.py`、`test_voice_settings_transaction.py`，跑這四個檔 | **13 failed／181 passed**：8 個回歸測試（OneCore／VE／Cerence × during_native／during_playback、eSpeak × 2）、2 個守門、`test_choosing_a_voice_records_it_without_stopping_speech[B:zh]`、`test_choosing_an_unavailable_voice_raises_and_changes_nothing`、`test_main_synth_records_a_chosen_voice_only_once_it_is_set` |
| 紅的原因 | 同上，`--tb=line` | during_native：「player idle 1 did not start」×3；during_playback：「native call 2 did not start」×3；eSpeak：`TimeoutError` ×2——都是 scheduler 等不到 drain 的卡住 |
| 抖動 | 分支上 `test_set_voice_in_flight.py`＋`test_worldvoice_speak.py`＋`test_voice_settings_transaction.py` 連跑 12 次 | 12 × **178 passed**（10.95–11.11 s） |
| 並行壓力 | `test_set_voice_in_flight.py` 3 個行程同時跑（§8 上限） | 3 × 8 passed |
| 突變：把 stop 加回 `_set_voice` | 分支 scratch 複本，四種寫法：`._binding.session.cancel()`、`.core.cancel()`、`engine = ….core; engine.cancel()`、`.get_voice_instance(…)._binding.session._adapter.cancel()` | 守門 `test_engines_are_stopped_only_through_the_scheduler`：killed／killed／**存活**（M3）／killed；回歸測試：四種都 **8 failed** |
| 守門掃描的實際命中 | 用分支的 `_engine_stops()` 與 `_last_word()` dump 全部 `stop()`／`cancel()` 呼叫 | 命中只有 `VoiceClassAdapter.cancel:197`、`TaskManager._stop_playback:415`、`EngineSession.cancel:189`；未命中的 receiver 末字只有 player／host／token／future／work／lifecycle／manager／self／super，沒有 driver／engine／synth |
| M4 | scratch 複本把 `:42` 改成 `True` | 8 passed |
| prek | `prek run --all-files` | 8 個 hook 全 Passed |
| 空白 | `git diff --check`、`git diff --check master..HEAD` | 乾淨 |
| 受保護路徑 | §7 的 `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' …/driver/sonic/ …script_data.py …unspaced_common_data.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural`；另加 `git diff --stat master -- addon/doc/en '*.html'` | 都沒有輸出 |
| `_set_voice` 的呼叫者 | `grep` addon 的 `.voice =`／`changeVoice`／`_set_voice`；NVDA `synthDriverHandler.py`、`speech/manager.py` | 只有 NVDA `changeVoice` 與 `panels/role.py:42`；`handlePostConfigProfileSwitch` 只在 synth／裝置改變時 cancel；`_switchProfile` 在語句之間、`resetSpeechIfNeeded=False` |
| NVDA 內建驅動的換語音 | `espeak.py:327`、`oneCore.py:620`、`sapi5.py:759` | eSpeak／OneCore 不停止；SAPI5 `_initTts` 重建 tts（M5） |
| `VoiceFacade.stop` 的使用者 | `grep` addon、tests、`ref/Neural`、docs | addon 無；tests 只有被刪的一個；Neural 的 `Voice` 不呼叫；spec 只有 phase 10a `:108`（M1） |
| readme 術語 | `ref/nvda/source/locale/{zh_TW,zh_HK,zh_CN,ru,uk}/LC_MESSAGES/nvda.po` 的 `Configuration Profiles` | 五個語言都和 NVDA 譯名一致；`diff zh_HK zh_TW` 只差這個詞 |
| commit | `git log --format=%B master..HEAD` | 三個都是英文 `fix:`／`refactor:`／`docs:`，內文說明原因；沒有 `Co-Authored-By` |

## 使用者還沒確認的使用者可見預設

- 使用者已選 F1（`storage/refactor9.md:460`）：非按鍵的 app／focus 切換啟用另一個主語音的組態設定檔時，當下這句用舊語音講完。本分支的行為與此相符，沒有新增其他可見預設。
- readme 的措辭（M5）是可選的修辭，沿用現有文字也正確。

未打包、未在 Windows 驗證；Linux 只驗證受控的 native 與音訊邊界。
