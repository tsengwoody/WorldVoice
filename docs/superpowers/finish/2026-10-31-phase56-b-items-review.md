# Review：Phase 56 audit B 項（B8 RHVoice SSML 轉換搬到 `prepare`、B12 純名單類別改名、B14 bridge 不重設未變的聲音）

日期：2026-10-31。分支：`phase56-b-items`（`5548ea2..eadc39e`，12 個 commit：`90bfad0` spec、`5eac270` plan、`5ab38b2` B8、`e50866e`／`fdc7ca0`／`35ff4c8`／`1690f6f` B12、`3b38527`／`269368e`／`d5a0080`／`05c409d`／`eadc39e` B14；基準 `master` `5548ea2` 3698 passed／0 skipped，分支 3727 passed／0 skipped）。
審閱者：Fable 5.1（唯讀；只新增本檔）。流程：一般流程（DEVELOPMENT_WORKFLOW.md §3.3）。

依據：

- spec `docs/superpowers/specs/2026-10-30-phase56-b-items-design.md`；plan `docs/superpowers/plans/2026-10-30-phase56-b-items.md`（Review Focus 1–5 逐項檢查）；進度帳本 `.superpowers/sdd/2026-10-30-phase56-b-items/progress.md`（六個 `Ruling:`）；來源 `cons.md` §1 B8、§3 B12、§5 A10／B14（唯讀，行號是 `9d96ace` 的）。
- 程式碼：`bridge/engineAdapter.py`（`_voiceIsCurrent` `:45-61`、記憶欄位 `:83`、`open` `:89`、`close` `:124`、`apply` `:162-173`）；`runtime/segmentHost.py`（`faulted` `:208-211`、`enqueue` `:259-310`：`prepare` 在 `:272`、`new_record` 在 `:278`、admission 從 `:279`；`reset` `:316-331`）；`runtime/_segmentLifecycle.py`（`fault` `:175-178`、`_latch_fault` `:503-508`）；`driver/RHVoice/__init__.py`（`prepare` `:292-295`、`submit` `:297-321`、`speak` `:420-421`、`cancel` `:423-462`、`terminate` `:464-483`）；內層 `driver/RHVoice/driver/__init__.py`（`SsmlConverter` `:431-456`、`_get_language` `:623-624`、`_set_voice` `:647-649`；無 diff）；`driver/SAPI5/__init__.py`（`_checkWorker` `:426-428`、`needsVoiceReload` `:430-438`、`_initTts` `:476-486`、`_initWasapiAudio` `:488-`）；`runtime/session.py`（`open`／`close` `:104-127`、`activate` `:144-161`）；`runtime/scheduler.py:586`（`activate` 在 worker 上）；`bridge/completionPolicies.py:25-36`、`__init__.py:252`。
- NVDA（`ref/nvda/`，唯讀）：`source/synthDrivers/sapi5.py`（`_initTts` `:730-757`、`_set_voice` `:759-773`、`_set_useWasapi` `:775-779`、`_get_voice` `:649-650`）、`espeak.py`（`__init__` `:77-87`、`_set_voice` `:327-340`）、`oneCore.py:617-627`、`synthDriverHandler.py:218-227`（`UseWasapiSetting`）、`gui/settingsDialogs.py:3793-3800`（換輸出裝置就 `setSynth`）。外部 plugin `ref/Neural/Neural/driver/__init__.py:385-390`。
- 測試：`tests/test_rhvoice_segment_drain.py:962-1058`、`tests/test_segment_host.py:602-624`、`tests/test_runtime_legacy_adapter.py:160-380`、`tests/test_f4_engine_session.py:92`、`tests/test_f4_voice_state.py:39-41`、`tests/test_sapi5_segment_drain.py:1225-1323`、`tests/test_sapi5_old_nvda.py:247-277`、`tests/test_native_strategy_guards.py`、`tests/nvda_releases.py`、`tests/test_vocalizer_drift.py:33-39`（無 diff）。
- 行號以 head `eadc39e` 為準；路徑省略 `addon/synthDrivers/WorldVoice/`。

## 結論

**程式碼正確、符合 spec、可以 merge。** Critical 0、Important 0、Minor 2（一個是多餘的重設、一個是 spec 少寫一句舊版 NVDA 的取捨；都不影響行為）。

- **B8 正確，XML 逐位元組相同。** `prepare:292-295` 用同一個 `rhvoice.SsmlConverter(driver, driver.language).convertToXml(commands)`，`submit:297-321` 只少了那兩行，其餘（`_segmentById` 登記、`_NativeLibrary`、`SpeakText` 與 `inner.profile`／`rate`／`pitch`／`volume`／`rateBoost` 快照、`ttsQueue.put`、失敗時 pop）全部仍在 admission 內。`enqueue:270-277` 在 `new_record:278` 之前呼叫 `prepare`，所以轉換失敗時沒有 host record、沒有 `_records[operation]`、沒有 `_segmentById`；段落走 `_lifecycle_of(operation).fail`（既有 `test_segment_prepare_error_fails_only_that_segment:989`），一般語音直接 raise。`cancel:423`／`terminate:464` 的 `host.admission()` 不再等轉換：三個新測試在還原後全部失敗（見驗證表）。terminate 之後才結束的轉換，進 admission 看到 `_terminated` → 段落 `work.cancel()`、一般語音 raise，和以前一樣；converter 只讀 `__languages`／`__voice_languages`／`__profile`（`inner-RHVoice:431-456`、`:623-624`），`RHVoice_delete_tts_engine` 之後仍可讀。
- **B8 在 admission 外讀內層狀態：沒有新競爭。** `__profile` 唯一的生產寫者是 bridge 的 `apply`（在 scheduler worker 上，`scheduler:586`），它從不拿 host admission，所以 master 上在 `submit` 內的轉換本來就和換聲音不同步；worker 又是先 `activate` 再 `speak`（`scheduler:586`、`:598`），同一個 task 內兩者有序。spec §1 的推理我獨立核過，成立。「一般語音的 cancel 窗口變寬」在生產環境碰不到：`CompletionPolicy` 預設 `forceUnverifiedDrain=True`（`completionPolicies.py:31`），`__init__.py:252` 沒有覆寫，RHVoice 只走段落。
- **B12 改名乾淨。** 自己寫的順序敏感 token 比對（`scratchpad/rev_tokcheck.py`，和實作者的腳本無關）在三個改名 commit 上都 PASS：每個檔案 token 數相同、逐一同型、只有含 `OLD` 的 `NAME`／`STRING` token 的文字變成 `\bOLD\b→NEW` 的結果（4／1／3、4／1／3、1／1／2 個），`_EspeakPort`、`_RHVoiceInner`、五個常數名、`port`、`port_names` 出現次數不變；負向自測（偷改一個 frozenset 成員）被抓到。四個舊名在 HEAD 上除 `docs/superpowers/` 外 0 處。`35ff4c8` 不是改名 commit、只動 parametrize，和 spec §2 第 3 點一致。`test_vocalizer_drift.py` 無 diff，`.replace("Cerence", "VE")` 把 `_CerenceInnerNames` 對到 `_VEInnerNames`，`left.keys() == right.keys()` 仍比對同一組定義；VE 與 Cerence 在同一個 commit `1690f6f` 改名，該 commit 上 drift 測試綠。
- **B14 的跳過規則正確、順序如 spec。** `_voiceIsCurrent:53-61`：先記憶（`applied is not None`、`applied[0] is core`、`applied[1] == voiceId`），再 hook（`getattr` 在 `try` 內，callable 且回真就設聲音），最後 getter；hook 或 getter raise → `False` → 設聲音。`apply:165` 先清記憶再做任何一步，`:173` 只有全部成功才寫回，所以 voice setter、任一設定 setter 或 `applyEngineSettings` raise 之後，下一次 apply 一定重設聲音（測試 `test_after_a_failed_apply_the_same_voice_is_set_again[voice|rate|hook]`）。`applied[0]` 握著舊 core 的強參照，`is` 比對不會被位址重用騙到；`close:124` 在 `destroyCore` 之前清掉，不會留住 core。`APPLY_ORDER` 與 `applyEngineSettings` 每次都跑，Review Focus 3 的 variant（`("hook", "bright")`）在 `test_reapplying_the_same_voice_skips_only_the_voice_setter:223-236` 釘住。
- **B14 沒有引擎靠「重設同一個聲音」的副作用。** 逐一看過五個 voice setter：SAPI5 `_set_voice:759-773` → `_initTts` 全部重建（這正是要省的；rate／volume 由 `APPLY_ORDER` 補回，pitch 走 SSML）；eSpeak `_set_voice:327-340` 的 `setVoiceAndVariant` 與 `_language` 都只依賴聲音本身，`setVoiceByLanguage` 只在 `__init__:81` 呼叫，第一次 apply（記憶為空）一定會設聲音，之後 native 聲音不會在 bridge 不知情下改變；OneCore `ocSpeech_setVoice`、RHVoice 只存 profile、VE／Cerence 內層同聲音早退。沒有引擎的 setter 會重設 variant 或參數。Neural（外部 plugin）`_set_voice:388-390` 只存 `_voice`、`_get_voice` 回 `self._voice.id`，沒有 hook → 同聲音跳過，無害；它不繼承 `VoiceClassAdapter`。加一個選用的 duck-typed 方法不動 `SegmentDrainCore`、`EngineAdapter` 的任何 protocol，`test_naming_layers`、`test_native_strategy_guards`（`_thread` 已在 `NVDA_PRIVATES`；`tts`、`player`、`useWasapi` 是公開名）、`test_hygiene_guards` 全綠。
- **SAPI5 的故障復原保住了。** `needsVoiceReload:430-438` 在 `host.faulted`、`tts is None`、或 WASAPI 下 `player is None`／`_thread is None`／worker 已死時回真；bridge 於是重設聲音 → `_initTts:476-486` → `_invalidateSegments`、新 sink、WASAPI 走 `_initWasapiAudio:488` 的 `host.reset()`、legacy 走 `:481-482` 的 `reset()`。`test_the_bridge_rebuilds_sapi5_for_the_same_voice_only_when_it_needs_reload:1305-1323` 用真的 SAPI5 wrapper：第二次同聲音 apply 不建新 native、player 不關、rate 生效；latch worker-stop fault 後第三次 apply 建新 native、`control_error` 清掉、新段落 drain。Review Focus 4（legacy 音訊健康時 `player is None` 也回假）由 `:1254-1257` 釘住，拿掉 `useWasapi` 守衛即失敗。`useWasapi` 在 WorldVoice 內只被讀（`completionPolicies.py:63`、SAPI5 `:107`、`:415`、`:427`、`:438`、`:451`、`:481`）；NVDA 的 `UseWasapiSetting` 掛在 `getSynth()`（WorldVoice 本身，它的 supportedSettings 沒有這項）而不是 SAPI5 core 上，所以 `_set_useWasapi:775-779` 的 `self.voice = self.voice` 在生產環境不會發生；就算發生也是同聲音重載，記憶仍為真。換輸出裝置 NVDA 直接 `setSynth`（`settingsDialogs.py:3795-3800`），不靠順帶的重建。
- **執行緒與鎖。** `apply` 只在 scheduler worker 上、`EngineSession._activation_lock` 內（`session:145`）；`open`／`close` 只在 session 閒置時。`needsVoiceReload` 讀 `_thread`／`player`／`tts` 不拿 `_threadCond`，但它們的寫者只有 `_initTts`／`_stopThread`（同一個 apply thread，或 terminate 時 session 已閒置），worker 自己不改這三個欄位。`SegmentHost.faulted:209-211` 的兩個讀取各自在自己的鎖內（`control_error` 用 `_condition`、`lifecycle.fault:175-178` 用 lifecycle 的 `_condition`），`self._lifecycle` 的換置只在 `reset()`（admission 內、由 `_initTts` 從 apply thread 呼叫），所以 apply thread 讀到的一定是當前的 lifecycle。latch 寫者（`_failSegmentControl` 從 cancel thread 或 worker、`_latch_fault` 從 lifecycle thread）和這個讀取的競爭只會讓「這一次」apply 沒看到剛 latch 的 fault——master 上同一瞬間 `_initTts` 的 `reset()` 也可能先於 latch 發生，而下一次設定變更照樣會看到 fault 並重建；沒有新的失敗模式，也不需要新鎖。cancel／terminate 不碰 `_voiceApplied`。
- **測試真的抓得到。** 十個還原／突變實驗（見驗證表）：B8 還原 → 3 個 cancel／terminate 測試失敗；B14 一律設聲音 → 12 個失敗（含 f4 的兩個、SAPI5 drain、六個舊版 NVDA）；拿掉 hook 檢查 → 4 個失敗；拿掉 getter 檢查 → 3 個失敗；刪 `needsVoiceReload` → 2 個；刪 `faulted` 檢查 → 2 個；刪 `useWasapi` 守衛 → 1 個；`faulted` 少 lifecycle 部分 → 1 個；apply 不先清記憶 → Hypothesis 性質測試失敗。唯一存活的是刪 `open()` 的重設（M1，等價）。新增的 7 個 RHVoice／SAPI5 測試連跑 20 次 0 失敗。六個中間 commit 各自 checkout 時相關測試檔全綠。
- **plan 的 Review Focus。** 1（轉換中 cancel、後繼只有自己的 XML）：`test_cancel_does_not_wait_for_a_segment_conversion:986-1000` 斷言 `len(calls) == 1`、`calls[0].text == b"<speak>next</speak>"` ✓。2（轉換中 terminate）：`:1003-1010` ✓。3（variant-only）：`:223-236` ✓。4（legacy 音訊健康）：`:1254-1257` ✓，且 `driver.useWasapi = False` 是經 NVDA 的 `_set_useWasapi` 真的重載成 legacy（`assert driver.player is None`）。5（`destroyCore` raise 後重開同一個 core）：`test_a_failed_close_still_forgets_the_voice:307-323` ✓，`close:122-124` 在 `destroyCore:128` 之前清 `_opened`／`_core`／記憶。
- **帳本的六個 Ruling 都合理。** （1）兩個 getter 測試合成 `test_a_core_not_reporting_the_voice_gets_it_set[raise|lie]`：同兩個案例、一個 `ProbeCore`，只是名字和 spec 不同。（2）`test_worker_activation_uses_one_snapshot_per_segment` 改成 `first_count * 3 - 2` 並斷言只有一次 `("voice", a.id)`：spec §3 的直接後果，spec 的測試清單漏列；改法正確。（3）`getattr` 放進 `try`：比 spec 更保守，`test_a_core_that_needs_a_voice_reload_gets_the_voice_set[raise-True]` 涵蓋 hook raise，屬性查找 raise 的情況也同路徑。（4）SAPI5 測試用 try/finally 手動還原而不用 monkeypatch：理由（`monkeypatch.undo()` 會連 harness 的 NVDA stub 一起還原、失敗時 fake `_thread` 讓 teardown 卡住）成立，測試可讀。（5）watchdog 改成 setsid 只殺自己的 process group：正確，和本次 review 用的做法相同。（6）多一個測試 `eadc39e` 殺死 `or→and` 的非等價 mutant：plan Task 6 Step 2 要求如此；該測試（`:247-256`）釘的是「getter 已回報新聲音時換聲音仍要設」，有價值。
- **mutmut。** 帳本：218 個 mutant、183 killed、35 survived、0 timeout；`apply`／`open` 無存活；新行內只剩 `__init__`／`close` 的 `None→""` 兩個（等價：`open()` 會先重設，apply 之前讀不到）；其餘 33 個在本 phase 沒動的程式（`configureCompletion`、`listVoices`、`speak`、`cancel` 等）且只對窄測試集跑過。我沒有重跑 mutmut（成本高），改用上述 10 個針對新程式的手工突變，覆蓋 spec §3 的每個條件；結果和帳本一致，另外多發現 M1。注意帳本說「`open` 無存活」是因為 mutmut 把 `None` 變成 `""` 後 `""[0]` 在 `_voiceIsCurrent` 內 raise `IndexError` 而被殺，不代表那行重設是必要的。
- **限制。** `driver/*/driver/*`、`driver/sonic/`、Unicode 資料檔無 diff；`git ls-files …/Neural` 無輸出；SAPI5／RHVoice wrapper 沒有 import 其他 driver；共用邏輯只在 `runtime/`（`faulted`）與 `bridge/`（`apply`），引擎特有的在 wrapper（`needsVoiceReload`）；命名：runtime `faulted` 小寫單字、bridge／wrapper `_voiceIsCurrent`／`voiceId`／`needsVoiceReload` camelCase；12 個 commit message 都是英文 `<type>: <summary>` 加原因、0 個 `Co-Authored-By`；改名、測試、功能分開 commit；prek 8 個 hook 全 Passed；ruff 0.16.3；tab 縮排、註解密度與周圍一致；無字串、無 readme（spec §4）。

## Critical

無。

## Important

無。

## Minor

### M1. `open()` 的記憶重設是多餘的，spec 把它寫成必要（`bridge/engineAdapter.py:89`；spec §3 `:141`）

`_voiceApplied` 只在 `__init__:83`、`close:124` 設成 `None`、`apply:173` 設成 tuple；`open:86-93` 若已開啟就直接返回，所以到得了 `:89` 的時候記憶必然已是 `None`（還沒 apply 過，或 `close()` 已清）。在暫時 worktree 刪掉 `:89`，`tests/test_runtime_legacy_adapter.py` 55／55 仍綠，包括 `test_reopening_sets_the_voice_even_on_the_same_core_object` 與 `test_a_failed_close_still_forgets_the_voice`。失敗情境：沒有；只是日後讀者（和 mutmut 報告）會以為這行擋住了某個路徑。建議二選一：刪掉 `:89` 並把 spec §3 第一點改成「`close()` 清掉，`open()` 之前必為空」；或保留但註解寫明「`close()` 已清，這裡只是讓 `open()` 自足」。

### M2. 舊版 NVDA（< 2025.3，NVDA 自己的 SAPI5 driver）少了一條順帶的復原路，spec 與 readme 都沒寫（spec §3 `:158`、`:178-180`；commit `d5a0080` 的內文有提）

NVDA 自己的 `sapi5.SynthDriver` 沒有 `needsVoiceReload`、也不 latch 任何 fault，所以它的 WASAPI player 或 worker 壞掉（例如 `player.stop()` 持續 raise、worker thread 死掉）時，master 上「改一下語速」會順帶 `_initTts` 重建並復原，現在只有切到另一個 SAPI5 聲音、換輸出裝置（NVDA 會 `setSynth`）或重載 WorldVoice 才會重建。這和純 NVDA 用 SAPI5 時的行為一致（NVDA 自己改語速不重設聲音），而且只影響 NVDA 2025.2 以前，所以我同意不處理；但 spec §3「NVDA 自己的 driver……latches nothing」只講了沒有 latch，沒講「壞而未 latch」的狀態不再順帶復原，使用者可見段也沒列。失敗情境：舊版 NVDA 使用者遇到 SAPI5 音訊壞掉，照以前的習慣改語速卻沒恢復。建議在 spec §3「Compatibility」補一句，並列入下方「未確認的預設」第 3 點。

## 審閱者自行驗證的項目

| 項目 | 指令 | 結果 |
| --- | --- | --- |
| 完整測試（scratch worktree `rev56` at `eadc39e`，watchdog：MemAvailable < 3 GB 只殺自己的 process group） | `python3 -m pytest -q -p no:cacheprovider tests` | 3727 passed、0 skipped（125 s；基準 3698 + 29；watchdog 未觸發，MemAvailable 起始 6.4 GB） |
| hook | `prek run --all-files` | 8 個 hook 全 Passed，未改檔 |
| ruff | `ruff check addon tests`；`ruff format --check addon tests` | All checks passed；244 files already formatted（ruff 0.16.3） |
| 空白 | `git diff --check master` | 無輸出 |
| 受保護路徑 | `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' addon/synthDrivers/WorldVoice/driver/sonic/ …/script_data.py …/unspaced_common_data.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 兩者皆無輸出 |
| commit 內容 | `git log --format=%B master..HEAD \| grep -c Co-Authored`；`git log --format='%h %s' master..HEAD` | 0；12 個 commit 都是英文 `<type>: <summary>` |
| 跨 driver import | 檢視 SAPI5／RHVoice wrapper 的 import 行 | 沒有 `driver.<其他引擎>` |
| B12 token 比對（自己寫的 `scratchpad/rev_tokcheck.py`：tokenize 父子版本、同長度、逐一同型、只有含 OLD 的 NAME／STRING／COMMENT／FSTRING_MIDDLE 可變且必須等於 `\bOLD\b→NEW`、保留名計數、`git grep -nw` 排除 `docs/superpowers`） | `rev_tokcheck.py <repo> e50866e _Sapi5Port=_Sapi5HostNames`；`… fdc7ca0 _OneCorePort=_OneCoreHostNames`；`… 1690f6f _VEPort=_VEInnerNames _CerencePort=_CerenceInnerNames` | 三個都 PASS：SAPI5 4895 tokens／4 renamed、`nvda_releases.py` 995／1、guards 6734／3；OneCore 4517／4、995／1、6734／3；Cerence 6329／1、VE 6286／1、guards 6738／2；保留名計數不變；每個 OLD 在該 commit 的 `git grep -nw` 皆空 |
| token 比對負向自測 | 在 `e50866e` 的 SAPI5 檔上另把 `"_thread"` 改成 `"_threadX"` 後比對 | 抓到 token #354 `STRING '"_thread"' -> '"_threadX"'` |
| 舊名殘留 | `git grep -nw -e _Sapi5Port -e _OneCorePort -e _VEPort -e _CerencePort HEAD -- . ':!docs/superpowers'` | 0 行 |
| 還原 B8（scratch worktree `rev56b`，`scratchpad/revert56.py`）：轉換搬回 `submit` 的 admission 內 | `pytest tests/test_rhvoice_segment_drain.py -k conversion` | 3 failed／2 passed：`test_cancel_does_not_wait_for_a_segment_conversion`、`test_terminate_does_not_wait_for_a_segment_conversion`、`test_cancel_does_not_wait_for_an_ordinary_conversion`（「cancel()／terminate() waited for the SSML conversion」）；兩個 characterization 測試照 spec 預測仍過 |
| 還原 B14：`apply` 一律 `core.voice = spec.id` | `pytest tests/test_runtime_legacy_adapter.py tests/test_f4_engine_session.py tests/test_f4_voice_state.py tests/test_sapi5_segment_drain.py tests/test_sapi5_old_nvda.py` | 12 failed／138 passed：`needs_a_voice_reload[False-False]`、性質測試、`test_revision_change_reapplies_same_voice`、`test_worker_activation_uses_one_snapshot_per_segment`、`…rebuilds_sapi5…`、六個 `…same_voice_reapply_keeps_the_com_voice[2024.1–2025.2]` |
| 突變：忽略 `needsVoiceReload` | 同上兩檔 | 4 failed：`[True-True]`、`[raise-True]`、性質測試、`…rebuilds_sapi5…`（`assert 2 == 2 + 1`） |
| 突變：記憶相符就回 `True`（不問 getter） | `pytest tests/test_runtime_legacy_adapter.py` | 3 failed：`…not_reporting_the_voice…[raise]`、`[lie]`、性質測試 |
| 刪掉 SAPI5 `needsVoiceReload` | `pytest tests/test_sapi5_segment_drain.py -k "needs_voice_reload or rebuilds_sapi5"` | 2 failed（`AttributeError`；`assert 2 == 2 + 1`） |
| 突變：`needsVoiceReload` 不看 `faulted` | 同上 | 2 failed（`:1237`、`:1315`） |
| 突變：`needsVoiceReload` 不看 `useWasapi` | 同上 | 1 failed（`:1257`，legacy 音訊健康卻要求重載）；`rebuilds_sapi5` 仍過 |
| 突變：`faulted` 不看 lifecycle fault | `pytest tests/test_segment_host.py -k faulted` | 1 failed（`:620`） |
| 突變：`apply` 不先清記憶（只在結尾寫） | `pytest tests/test_runtime_legacy_adapter.py` | 1 failed：性質測試（失敗的 apply 之後同聲音沒重設） |
| 突變：刪 `open()` 的 `_voiceApplied = None` | 同上 | 55 passed —— 等價突變（M1） |
| flakiness | `rev56` 上 5 個 RHVoice conversion 測試 + 2 個 SAPI5 新測試 ×20 | 20／20 輪 7 passed |
| 逐 commit | `rev56b` checkout `5ab38b2`、`e50866e`、`1690f6f`、`3b38527`、`269368e`、`d5a0080`，各跑相關測試檔 | 165、97、51、72、141、167 passed，皆 0 failed |
| B8 生產路徑 | 讀 `completionPolicies.py:25-36`、`__init__.py:252` | `forceUnverifiedDrain=True` 預設未覆寫 → RHVoice 只走段落，一般語音的窗口變化碰不到 |
| B14 對照 NVDA | 讀 `sapi5.py:730-779`、`espeak.py:77-87`／`:327-340`、`oneCore.py:617-627`、`synthDriverHandler.py:218-227`、`settingsDialogs.py:1670-1685`／`:3793-3800`；`ref/Neural/…/driver/__init__.py:385-390` | 沒有 setter 的副作用被依賴；`useWasapi` 在 WorldVoice 只讀；換裝置走 `setSynth`；Neural 只存聲音 |
| Hypothesis 設定 | `tests/conftest.py:18-21` | profile `deadline=None`，新性質測試和同檔其他性質測試用同一個 `suppress_health_check` 寫法 |
| 資源 | 單一 pytest process（環境無 xdist）；`MemAvailable` 6.4 GB | 未觸及 3 GB 下限；未用 `pkill -f pytest`、未用 `git stash` |
| 清理 | `git worktree remove --force` `rev56`、`rev56b`；`git worktree list` | 只剩原有四個 worktree（master、phase55、phase56、SDKTest） |

未做：未重跑 mutmut（以 10 個手工突變代替，見結論）；未在 Windows／NVDA 實機驗證（spec §3 的三個手動項目：SAPI5 語速環逐步、兩個 SAPI5 聲音同句、NVDA 2025.1／2025.2 改語速）；未打包。

## 使用者還沒確認的使用者可見預設

1. **B14 保留 `needsVoiceReload` hook 與 `SegmentHost.faulted`**（spec §6.1，協調者採建議預設）：改一個設定仍會讓故障的 SAPI5 聲音復原。替代方案是拿掉 hook（更簡單；故障後只能換 SAPI5 聲音或重載 WorldVoice）。審閱者同意保留。
2. **每次 `open()` 之後第一次 apply 仍設聲音**（spec §6.2）：SAPI5 每次開啟 core 仍重建一次。
3. **舊版 NVDA（< 2025.3）的 SAPI5 不再因改設定而順帶重建**（M2）：壞而未 latch 的 player／worker 要靠換聲音、換裝置或重載才復原；和純 NVDA 一致。
4. **B8 的兩個順序差異**（spec §6.5）：轉換本身失敗時使用者看到的是轉換錯誤而不是 terminated／control error；一般語音在轉換中被 cancel 的窗口變寬（生產環境碰不到，見結論）。
5. **B12 測試 helper 的用語不改**（spec §6.4）：`tests/nvda_releases.py` 的 `EngineNames.port`／`port_names()` 保留，雖然三個條目中兩個現在指向 `*HostNames`。只影響開發者。
6. **不加 readme／changelog**（spec §6.6）：B14 只是 SAPI5 改設定後下一句少一次重建的延遲；Windows 上未量測。
7. **只在 Linux fake 上驗證**：SAPI5 COM／WASAPI 的實際重建成本與復原、RHVoice 混合語言切換 profile，都未在 Windows 實測。

## 修正記錄

日期：2026-10-31。修正者：Opus 5.5（DEVELOPMENT_WORKFLOW.md §3.4 一般流程）。只有 Minor，依 §3.4 不做修正 review。

- **M1** → `18a99c2` `refactor: drop the redundant voice-memory reset in open()`。刪掉 `open()` 的 `self._voiceApplied = None`；spec §3 第一點改成「在 `__init__`、`close()` 與每次 apply 開頭清掉，`open()` 不動它（已開啟就返回，否則必在 `__init__` 或 `close()` 之後）」，「Other core replacements」第一點同步改寫。純重構、行為不變，無法先寫失敗的測試；改以既有測試證明：`test_reopening_sets_the_voice_even_on_the_same_core_object`、`test_a_new_core_gets_the_voice_set`、`test_a_failed_close_still_forgets_the_voice`、性質測試（含 `reopen` 動作）與 `test_after_a_failed_apply_the_same_voice_is_set_again[voice|rate|hook]` 刪除後全綠，沒有測試需要修改。附帶影響：帳本 Task 6 說 `__init__`／`close` 的 `None→""` mutant 等價，理由是「`open()` 會先重設」；這行刪掉後該理由不再成立（`""[0]` 會在 `_voiceIsCurrent` 的 `try` 外 raise `IndexError`，apply 失敗，應該會被殺），未重跑 mutmut，記在帳本。
- **M2** → `ca28698` `docs: note that old-NVDA SAPI5 no longer heals on a setting change`。spec §3 SAPI5 wrapper 段「NVDA's own driver……latches nothing」後補上後果；「What NVDA users hear or see」加一點；§6 加第 7 個 open question（預設接受，替代方案是對 NVDA 自己的 SAPI5 core 一律設聲音），標 `Decided by orchestrator with the recommended default; user may override before merge.`。readme 依 spec §6.6 不加。

驗證（head `ca28698`）：`python3 -m pytest -q -p no:cacheprovider tests`（setsid watchdog，MemAvailable < 3 GB 只殺自己的 process group；未觸發）3727 passed、0 skipped，與 review 時相同（沒有測試增減）；`prek run --all-files` 8 個 hook 全 Passed；`git diff --check master` 無輸出；受保護路徑 `git diff --stat master -- …` 與 `git ls-files …/driver/Neural` 皆無輸出。
