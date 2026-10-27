# Phase 47b Review：宿主層改名

日期：2026-10-27。分支：`phase47b-host-names`（`9848945..7a3e2eb`，33 個 commit；基準 `master` `9848945`）。
審閱者：Fable 5.1（唯讀；只新增本檔）。流程：一般流程加 §3.2「改名與搬移的證明」（DEVELOPMENT_WORKFLOW.md §3.3）。批次 1（`ca73bdb..4cce86a`）與批次 2（`1324d9c..c129841`）已由 Opus 做過批次 review；批次 3（`c129841..7a3e2eb`）本次第一次看，但整個分支都重看了一遍。

依據：

- 規則來源 `storage/refactor9.md` §6.1（含規則 3 被使用者推翻、`@override` 更正）、§6 的 P47b／P47c／P47d、§4.3、§6.2（核心呼叫宿主 camelCase 方法的附註）。
- spec `docs/superpowers/specs/2026-10-27-phase47b-host-names-design.md`。
- plan `docs/superpowers/plans/2026-10-27-phase47b-host-names.md`。
- 進度帳本 `.superpowers/sdd/2026-10-27-phase47b-host-names/progress.md`（git 忽略）。
- 守門測試 `tests/test_naming_layers.py`。

使用者與協調者已決定、本次只核對實作的事項：分層規則（核心 snake_case、宿主 mixedCase、實作或覆寫介面照原名，由繼承或 `INTERFACE_NAMES` 辨識）；不用 `typing.override`（最低 NVDA 2024.1）；存放識別字留給 47d、外掛契約留給 47c；核心呼叫宿主的 camelCase 方法；`SegmentDrainCore` 是 ABC 且放在每個 wrapper 的最後一個基底；`pipelineLogService`；harness 的 metaclass 替身改繼承 `ABCMeta`；`Legacy*` 改名、`taskManager` → `_taskManager`、`Voice as BaseVoice`／`SynthDriver as BaseSynthDriver`、`_BindingEvents` → `_EventsWhileActive`。**實作全部符合**，核對細節見「審閱者自行驗證的項目」。

## 結論

**Ready to merge：Yes。** Critical 0、Important 0、Minor 4。

- 15 個改名 commit 全部是純改名。用審閱者自己寫的檢查（`review47b3/indep.py`：不讀任何 `OLD=NEW` 清單，從兩版 AST 的平行走訪**推導**出配對，再要求配對一致、註解依序比對、token 流依序比對）逐一重跑：每個 commit 只有推導出的配對在變，其他 token 的內容與順序完全不動；留下來的舊名逐一看過，都是核心欄位、NVDA 關鍵字、vendored 名稱、`NativeStrategy` hook 或測試自己的名字（見「獨立改名證明」）。
- 覆寫與介面名稱完好：沒有任何覆寫 vendored／NVDA 類別的方法被改名（各 `_XxxPort` 名單與改名配對零交集；主檢出與分支之間宿主層消失的 170 個定義全部是改名配對的舊名，只多出 `_BindingEvents`／`__new__` 這兩個刻意刪除的）。`INTERFACE_NAMES` 新增的 12 項每一項都查到了對應的外部介面（見驗證表）。VE 與 Cerence 仍是雙胞胎：自己做的正規化 diff 只在 `_PROFILE`、`_ContextualVECallback._process`、`SynthDriver._callbackAdmission`、`Voice.variants` 四處不同，和 `tests/test_vocalizer_drift.py:7` 的允許清單一致。
- 守門測試的終態正確：`TRANSITIONAL_47B` 連同所有引用都不在 `addon/`／`tests/`；47C 與 47D 被 `test_only_stored_identifiers_and_the_plugin_contract_wait` 釘住只能縮小；突變 13 種情境全部被對應測試抓到（見驗證表）。
- 沒有行為變更：可翻譯字串與 `# Translators:` 註解（148 筆）在 `master` 與分支逐筆相同；NVDA 呼叫的名字（`makeSettings`、`onSave`、`onDiscard`、`isValid`、`postInit`、`onInstall`、`script_*`、`_get_`／`_set_` 設定屬性、extensionPoints handler 的 `synth`／`index` 參數名）沒有一個出現在改名配對裡；`ref/Neural` 只用到 `driver.Voice`（47c 範圍），不宣告 `drain_profile`，`SegmentDrainCore` 對它沒有影響。
- 完整測試 3298 passed、0 skipped（基準 3293 + 5 個新測試）；`prek run --all-files` 全部 Passed；`git diff --check master` 乾淨；受保護路徑無 diff、Neural 未被 track；33 個 commit 沒有 `Co-Authored-By`，沒有任何 commit 碰到 `ref`。

## Critical

無。

## Important

無。

## Minor

### M1. `_SilenceGate.is_set` 在 `INTERFACE_NAMES` 的說明和 vendored 程式碼不符

- 位置：`tests/test_naming_layers.py:86`、`:107`（Cerence 與 VE 兩筆）；spec §4.3 表格同一句。
- 內容：說明寫「`threading.Event.is_set`, which the vendored callback calls through `_isSilence`」。實際上 vendored callback 呼叫的是 `self._isSilence.isSet()`（`driver/VE/driver/__init__.py:153`、`:182`、`:193`、`:195`，Cerence 同），而 wrapper 自己定義了 `_SilenceGate.isSet` 轉呼叫 `is_set`（`driver/VE/__init__.py:113-114`）。`is_set` 要保留的真正理由是它覆寫標準庫 `threading.Event.is_set`（`Event.wait()`、第三方讀取都走它），不是 vendored callback 直接呼叫它。
- 失敗情境：將來有人依說明去 vendored 程式碼找 `is_set` 找不到，以為這筆過時而刪掉，守門測試會立刻失敗，不會造成行為錯誤；只是說明誤導。
- 建議：改成「threading.Event.is_set, overridden so the vendored callback's `isSet()` (through `_SilenceGate.isSet`) and `Event.wait()` see the guard」之類，spec §4.3 同步。

### M2. 守門測試沒有自我測試「以別名匯入的基底」

- 位置：`tests/test_naming_layers.py:540-548`（`test_the_guard_reads_the_imported_base_of_a_class_with_its_name` 只測 `class SynthDriver(SynthDriver)` 同名匯入）。docstring 第 14 行宣稱「also under an alias such as BaseVoice」。
- 失敗情境（已在 scratch 複本驗證反向）：目前別名路徑只靠真實 add-on 間接驗證——把 RHVoice 的 `class Voice(BaseVoice)` 改成 `class Voice(object)`，`test_naming_follows_layer` 列出 `Voice.drain_profile`、`Voice.synth_driver_class`，證明豁免確實來自繼承。但這兩個名字是 47c 要改成 camelCase 的；47c 之後 add-on 裡不再有任何 snake_case 名字靠別名基底豁免，屆時若有人改壞 `_Index._resolve` 的 `module.imports` 路徑（`:278-279`），整套測試不會發現。
- 建議：在 `test_the_guard_reads_the_imported_base_of_a_class_with_its_name` 旁加一個兩檔案的案例：`SYNTH + "driver/__init__.py"` 定義 `class Voice` 帶 `def create_core(self)`，`SYNTH + "driver/X/__init__.py"` 寫 `from synthDrivers.WorldVoice.driver import Voice as BaseVoice` 與 `class Voice(BaseVoice): def create_core(self)`／`def own_name(self)`，斷言只有 `Voice.own_name`。

### M3. 假 presenter 的 `__getattr__` 前綴放寬後，拼錯的屬性名不再報錯

- 位置：`tests/test_role_panel_ui.py:57-61`（`59af1d0`；`__getattr__` 在 `:57`）。
- 內容：原本只錄 `select_`／`set_` 開頭的呼叫，改成 `select`／`set` 開頭，是為了同時相容兩種命名風格。改名完成後，這個放寬已經沒有必要，而且 `selectedVoice`、`settings`、`setup…` 之類的名字現在也會落入錄音 lambda。目前 `selectedVoice` 有明確定義（`:45`），所以沒有實際影響。
- 失敗情境：面板將來把 `self._presenter.selectedVoice(locale)` 打成 `selectedVoices(locale)`，假 presenter 會回傳 lambda 而不是 `AttributeError`，對應的 UI 測試會以奇怪的方式失敗或默默通過。
- 建議：改回明確的方法名集合（`selectVoice`、`setParameter`、`setVariant`、`setEngineConsistency`、`setVoiceConsistency`、`setParameterConsistency`、`discard`、`close`、`apply`），其他名字一律 `AttributeError`。

### M4. 批次 review 的 Minor 內容沒有進帳本

- 位置：`.superpowers/sdd/2026-10-27-phase47b-host-names/progress.md`「Batch 1 review fixes」與「Batch 2 review」兩段只記了數量（批次 1：4 M 延後；批次 2：M1–M3 已併入 Task 15，M4–M6 延後）。
- 內容：協調者要求把批次 1 的 M1–M4 與批次 2 的 M4–M6 併入本次 review 的 Minor 清單，但這七項的文字不在帳本、不在分支、也不在 scratchpad 的 `review47b/`、`review47b2/` 任何檔案裡，審閱者無法逐項判斷是否仍然成立。批次 2 的 M1（spec／plan 的 36→30）、M2（47D 釘住）、M3（docstring 終態）已由 `7a3e2eb`、`c6a2576` 處理，本次核對過。
- 建議：協調者在修正輪開始前把那七項的原文補進帳本（或本檔「修正記錄」上方），修正 agent 再逐項決定修或不修；本檔的 Minor 清單以 M1–M3 為準。

## 審閱者自行驗證的項目

測試都在 scratchpad 的暫時 worktree（`review47b3/wt`，detached 在 `7a3e2eb`，`ref` 用 symlink）執行，序列化、附 MemAvailable < 3 GB 的看門狗；沒有碰主檢出，沒有用 `git stash`；worktree 事後自行移除。

| 項目 | 指令／做法 | 結果 |
| --- | --- | --- |
| 完整測試 | `runtests.sh <wt> tests`（序列，看門狗） | **3298 passed，0 skipped**（102.96 s；看門狗未觸發）。基準 3293 + 5：`test_batch_iterates_again_and_stops_after_unbind`、`test_every_reason_entry_still_checks_a_handler`、`test_segment_drain_core_combines_with_an_abcmeta_driver_metaclass`、`test_every_wrapper_core_declares_the_segment_drain_entries`、`test_wrappers_do_not_shadow_their_bases` |
| hook | `prek run --all-files` | 8 個 hook 全部 Passed |
| 空白 | `git diff --check master` | 無輸出 |
| 受保護路徑 | §7 的兩個指令 | 都無輸出 |
| commit 衛生 | `git log 9848945..7a3e2eb --format=%B \| grep Co-Authored-By`；`--name-only` 找 `ref`；改動檔案是否只在 `addon/`、`tests/`、`docs/` | 0 筆 Co-Authored-By；沒有 commit 含 `ref`；沒有其他路徑 |
| 守門終態 | `git grep TRANSITIONAL_47B 7a3e2eb -- . ':!docs'`；`git grep "import .*override" -- addon` | 都無輸出 |
| 翻譯 | `review47b3/msgids.py`：抽出 `addon/` 所有 `_()`／`pgettext()`／`ngettext()` 引數與 `# Translators:` 註解，`master` 對 `7a3e2eb` | 148 筆逐筆相同 |
| 獨立改名證明 | `review47b3/indep.py <repo> <commit>`，15 個改名 commit | 全部 `PURE RENAME: OK`，見下一節 |
| 殘留舊名掃描 | `review47b3/leftover.py`：204 個舊名在 `7a3e2eb` 的 `addon/`（去 vendored）與 `tests/` 的每一次出現（NAME token 或字串／註解中的整字） | 720 處，逐類看過：核心欄位（`source_id`、`segment_id`、`control_error`、`voice_id`、`voice_class`、`index_ledger`、`conf_provider`、`add_detected_language_commands`、`driver_id`、`index_range`、`load_events`、`on_done`、`cleanup_error`、`_number_language`）、介面關鍵字（`nvda_version`、`audio_mode`、`on_event`）、`NativeStrategy.stop_player` hook（六個 wrapper）、vendored／NVDA（`get_player`、`workspace_path`、`module_name`）、字串裡的 log 文字與 reason 文字（`guard_errors`、`force_unverified_drain`、`pipeline_log.csv`）、以及測試自己的 helper／local／parametrize 標籤。沒有漏改的呼叫點或 `getattr`／`monkeypatch` 字串 |
| 宿主層定義的增減 | `review47b3/defnames.py`：`master` 與 `7a3e2eb` 宿主模組所有 def／class／`self.x` 名字的差集 | 消失 170 個，全部是改名配對的舊名，另加刻意刪掉的 `_BindingEvents`、`__new__`；新增 172 個，全部是配對的新名，另加 `_EventsWhileActive` 的 `_events`、`_isActive`。所以 NVDA 呼叫的 camelCase 名字（`makeSettings`、`onSave`、`onDiscard`、`isValid`、`postInit`、`onInstall`、`_get_*`／`_set_*` 設定屬性）不可能被動到 |
| `script_` 與 `_set_` 前綴 | 在 204 個配對裡 grep `script_\|event_\|_get_\|_set_` | 只有 `_set_main_voice`（rolePresenter 的欄位）與 `_set_voice_parameter`（synth `__init__.py:376`）。後者在 `master` 上因為 NVDA `AutoPropertyType` 的 `_set_` 規則（`ref/nvda/source/baseObject.py:76-110`）會被做成只有 setter 的自動屬性 `voice_parameter`；`master` 與分支都沒有任何地方讀寫 `voice_parameter`（grep `addon/`、`tests/`），所以改成 `_setVoiceParameter` 只是拿掉一個無人使用的意外屬性，不是行為變更 |
| 存放識別字 | 204 個舊名對 confspec／設定表（`pipeline/settings.py`、`scriptLanguages.py`、`registry.py`、`settingsRepository.py`、`voiceSettings.py`、synth 與 globalPlugin 的 `__init__.py`）的字串字面值 | 零命中：沒有改名碰到 nvda.ini 鍵或 setting id（spec §4.4 的說法成立） |
| extensionPoints | `nvdaEvents.py:213-216` `_onIndex(self, synth, index)`／`_onDone(self, synth)`；`filter_speechSequence.register(self.addDetectedLanguageCommands)`（`__init__.py:464`） | handler 參數名維持 NVDA 的 `synth`、`index`；filter 只傳一個位置引數 |
| 覆寫未被改名 | 各 wrapper 的 `_VEPort.INNER_PRIVATES/INNER_OVERRIDES`、`_OneCorePort.NVDA_*`、`_Sapi5Port.NVDA_*`、`_RHVoiceInner.CALLBACK_NAMES`，與批次 3 的配對比對；`tests/test_native_strategy_guards.py` 的五個 `*_privates_are_listed_and_exist` 通過 | 零交集。SAPI5 `_SegmentPlayer._record_error`／`_stop_failed`（`:199`、`:205`）是 `LeasedPlayer` 的 hook（`runtime/segmentHost.py:725`、`:728`），正確保留 |
| `INTERFACE_NAMES` 12 筆的外部介面 | `ref/nvda/source/synthDrivers/_espeak.py:235`、`:241`（`espeakDLL.espeak_ng_Cancel()`、`espeakDLL.espeak_Synth(...)`）；`driver/RHVoice/driver/__init__.py:398`、`:408`、`:410`（`self.__lib.RHVoice_new_message/speak/delete_message`）；`ref/nvda/source/synthDrivers/sapi5.py:251`、`:455`、`:477`、`:486`、`:498`（`ISequentialStream_RemoteWrite`、`ISpNotifySink_Notify`、`StartStream`、`Bookmark`、`EndStream`）；`threading.Event.is_set` | 每一筆都有真實介面。`_SegmentSapiSink(sapi5.SapiSink)`、`_SegmentAudioStream(sapi5.SynthDriverAudioStream)` 的基底在 NVDA，守門測試讀不到，所以列表是對的做法。VE／Cerence 那兩筆的說明用詞見 M1 |
| VE／Cerence 雙胞胎 | `diff <(sed 's/Cerence/VE/g; s/ttsapi/ve2/g' Cerence/__init__.py) VE/__init__.py` | 只差 `_PROFILE`（:43）、`_process` 的 index 來源（:299）、`_callbackAdmission` 的 `VE_HSAFE` 檢查（:672）、`Voice.variants` 的 try（:988），加上一處 ruff 換行；和 `test_vocalizer_drift.py:7` 的 `ALLOWED` 一致，測試通過 |
| `SegmentDrainCore` 與真 NVDA | `ref/nvda/source/baseObject.py:60` `class AutoPropertyType(ABCMeta)`、`:121` `AutoPropertyObject(..., metaclass=AutoPropertyType)`；`baseObject.py`、`garbageHandler.py`、`synthDriverHandler.py`、`driverHandler.py`、`autoSettings.py` 都沒有 `__slots__` | 派生 metaclass 是 `AutoPropertyType`（ABCMeta 的子類），ABC 的空 `__slots__` 不會和 NVDA 的物件佈局衝突；`__abstractmethods__` 在六個 wrapper 都是空集合（各自定義兩個 entry，`test_every_wrapper_core_declares_the_segment_drain_entries` 釘住）。bridge 仍用 `getattr(core, "speak_segment")`（`completionPolicies.py:85-89`、`engineAdapter.py:93`），沒有 `isinstance(…, SegmentDrainCore)`，外掛不必繼承它 |
| `ref/Neural` | `ref/Neural/Neural/__init__.py`：`from synthDrivers.WorldVoice.driver import Voice as WorldVoice`、`class Voice(WorldVoice)`、`synth_driver_class = SynthDriver`；grep 其餘檔案 | 只用 47c 範圍的名字；不宣告 `drain_profile`，走 LEGACY 完成，`SegmentDrainCore`、`BaseVoice` 別名、`_taskManager` 都碰不到它。wrapper 模組屬性 `Voice` 仍是 WorldVoice 的類別，`test_plugin_voice_contract.py` 通過 |
| Protocol 明確繼承 | `VoiceClassAdapter(EngineAdapter)`、`NvdaEventBridge(NotificationOutput)`：兩者都定義自己的 `__init__`，而且 `EngineAdapter` 的 9 個成員（`engineAdapter.py:68-199`）與 `NotificationOutput` 的 2 個（`nvdaEvents.py:253`、`:257`）都有實作 | Python 3.11（NVDA 2024.1）對 concrete 子類不改 `__init__`，沒有載入風險；沒有成員會默默落到 Protocol 的 `...` 本體 |
| 核心呼叫宿主 camelCase | `voices/manager.py:110-122`（`notificationSource`、`configureCompletion`、`configureSegmentEvents`、`segmentSink`、`listVoices`）、`:94` `indexLedger=`；`pipeline/context.py:43` `synth.speechContext()` | 符合 spec §4.1 的預設；refactor9 §6.2 已記下「若將來定義成核心 Protocol 會再改一次」 |
| plan Review Focus 1（建構子關鍵字） | `__init__.py:216-245`：`NvdaEventBridge(doneEvent=, indexEvent=, getSynth=, indexLedger=)`、`start(…, batchHandler=)`、`CompletionPolicy(nvdaVersion=, logger=)`、`VoiceManager(task_manager=, index_ledger=, conf_provider=…)` | 與各簽名一致；`test_runtime_composition.py`、`test_worldvoice_lifecycle.py` 建真實 synth 並通過 |
| plan Review Focus 2（介面關鍵字） | `completionPolicies.py:91` `check(nvda_version=…, audio_mode=…)`、`engineAdapter.py:30` `speak_segment(…, context=, on_event=)`；`test_drain_support_requires_keywords` | 關鍵字未動；突變 M2b（OneCore `speak_segment` → `speakSegment`）被 `test_every_wrapper_core_declares_the_segment_drain_entries` 與 76 個 harness 測試抓到 |
| plan Review Focus 3（metaclass） | `test_segment_drain_core_combines_with_an_abcmeta_driver_metaclass`；Task 10 第一次全跑時 eSpeak／SAPI5／RHVoice harness 的 `BaseMeta(type)` 真的爆 metaclass conflict | 替身改成 `ABCMeta` 子類後與 NVDA 相同；Linux 仍沒載入真的 `AutoPropertyType`，見「未在 Windows 驗證」 |
| plan Review Focus 4（字串裡的名字） | 殘留舊名掃描（上）＋ 批次 3 改名 commit 裡所有字串變更逐行看：`worldvoice_cancel_wrapper_harness.py:249-256` 的 `getattr(…, "_initializeNative", original.SynthDriver.__init__)`（有靜默 fallback，已改到）、`test_vocalizer_segment_drain.py:56`、`runtime_drain_integration_harness.py:288`、`test_native_strategy_guards.py:223`、`test_vocalizer_drift.py:7` | 都已跟著改；沒有漏網 |
| plan Review Focus 5（批次重複迭代） | `test_batch_iterates_again_and_stops_after_unbind`；突變 M8a／M8b | 見下 |
| 突變 M1：部分還原 wrapper 改名（Espeak 呼叫端改回 `_port.stop_player()`） | `test_espeak_segment_drain.py` + 守門 | 11 failed |
| 突變 M1b：VE 只把 `def _stopPlayer` 改回 `_stop_player`，呼叫端不動 | `test_vocalizer_segment_drain.py`、drift、守門 | 6 failed |
| 突變 M2：覆寫被改名（Espeak `_EspeakStrategy.stop_player` → `stopPlayer`） | `test_espeak_segment_drain.py`、`test_native_strategy_guards.py`、`test_segment_host.py` | 26 errors（`NativeStrategy` 抽象方法未實作） |
| 突變 M2b：OneCore `speak_segment` → `speakSegment` | 同上 | 2 failed、76 errors |
| 突變 M2c：vendored 覆寫被改名（SAPI5 `_speakThread` → `_speakWorker`） | `test_native_strategy_guards.py` | 1 failed（`NVDA_OVERRIDES` 不符） |
| 突變 M3：刪掉 `INTERFACE_NAMES` 的 `_NativeLibrary.RHVoice_speak` | `test_naming_layers.py` | 1 failed（`test_naming_follows_layer`） |
| 突變 M4：47D 加 `GlobalPlugin.terminate` | 同上 | 2 failed（`test_lists_hold_only_names_that_break_the_rule`、`test_only_stored_identifiers_and_the_plugin_contract_wait`） |
| 突變 M4b：47C 加 `Voice.applyEngineSettings` | 同上 | 2 failed |
| 突變 M5：RHVoice 改回 `from … import Voice`／`class Voice(Voice)` | `test_native_strategy_guards.py` | 1 failed（`test_wrappers_do_not_shadow_their_bases`） |
| 突變 M6：RHVoice `class Voice(object)`（別名基底消失） | `test_naming_follows_layer` | failed，列出 `Voice.drain_profile`、`Voice.synth_driver_class`：豁免確實來自別名基底的繼承 |
| 突變 M7：Espeak 拿掉 `SegmentDrainCore` 基底 | `test_native_strategy_guards.py` + 守門 | 2 failed（新測試與 `test_naming_follows_layer` 列出 5 個 entry） |
| 突變 M8a：`_EventsWhileActive.__iter__` 不檢查 `isActive` | `test_nvda_event_bridge.py` | 2 failed |
| 突變 M8b：`_EventsWhileActive` 改回 tuple 子類 | 同上 | 1 failed（`len(batch)` 未 raise） |

## 獨立改名證明

工具：`review47b3/indep.py`（scratchpad）。對每個改名 commit 的每個變更檔：

1. 兩版 AST 平行走訪（有序）；識別字欄位（`id`、`arg`、`attr`、`name`、`asname`、import `names`）可以不同，每個差異收成 `OLD → NEW`，整個 commit 內一個 OLD 只能對一個 NEW、一個 NEW 只能來自一個 OLD；節點型別、串列長度、非字串常數都必須相等；字串常數只能以推導出的配對做整字替換。
2. 註解依序比對，只能以配對做整字替換。
3. token 流（去 NL 與 ruff 的尾逗號）依序比對：NAME 只能照配對變，STRING／COMMENT 只能整字替換，其他 token 型別與內容相等。token 數不同時改報 AST-only，並另外證明差異只是括號。
4. 列出每個 OLD 在新版仍出現的位置（NAME 或字串／註解），由審閱者逐一判斷。
5. `tests/test_naming_layers.py` 只允許刪行（或清空後的單行收合）。

| commit | 檔案 | 配對數 | 改掉的 token | 模式 | 留下的舊名（判斷） |
| --- | --- | --- | --- | --- | --- |
| `ca73bdb` completionPolicies／indexCodec | 8 | 9 | 105 | tokens+AST | `check(nvda_version=, audio_mode=)` 介面關鍵字；reason 字串裡的 `force_unverified_drain`；`voice_class` 核心參數 |
| `d4fdf9c` indexLedger | 12 | 19 | 371（含 AST-only 檔 207） | `tests/test_index_ledger.py` AST-only：ruff 拿掉多餘括號，去掉 `(`、`)`、`,` 後 7842 對 7842 個 token 全部相等或照配對 | `context/event.source_id`、`.segment_id`、`PlaybackEvent(segment_id=)`、`contract.index_range`、假 core 的 `wire_indexes`、測試標籤 |
| `b866221` nvdaEvents | 14 | 19 | 154 | tokens+AST | 核心 `source_id`、`VoiceManager(index_ledger=)`、`LegacyEngineAdapter(index_ledger=)`（Task 4 才改）、測試 helper |
| `2ecb946`、`c6896bf` | 基底宣告 | — | — | 非改名 commit，各只加一個 import 與一個基底 | — |
| `4c2d6bd` engineAdapter | 9 | 17 | 102 | tokens+AST | `speak_segment(on_event=)`、`VoiceManager(index_ledger=)`、`_index_ledger` 核心欄位 |
| `f4b47de` Legacy 名稱 | 18 | 3（`LegacyEngineAdapter=VoiceClassAdapter`、`LegacyVoiceBinding=VoiceBinding`、`normalize_legacy_commands=normalizeNvdaCommands`） | 52 | tokens+AST | 無；`git grep` 三個舊名在 `addon/`、`tests/` 為空 |
| `1324d9c` ui | 10 | 21 | 132 | tokens+AST | `spec.driver_id` 核心表欄位 ×13 |
| `92f0b76` synth `__init__` | 15 | 14 | 83 | tokens+AST | `self._languageDetector.add_detected_language_commands` 核心 |
| `085bf2b` `_taskManager` | 3 | 1 | 15 | tokens+AST | 核心 `task_manager=`；`test_f4_engine_adapters.py:88` 假 `BaseVoice(…, taskManager, …)` 參數（測試自己的） |
| `bc634f4` globalPlugins | 22 | 43（含 `pipeline_log=pipelineLogService`、`DetectLanguageTimingLabel=detectLanguageTimingLabel`） | 299 | tokens+AST | `"pipeline_log.csv"` 檔名、log 文字 `Error in guard_errors callback` 與其測試、`workspace_path`（pending 模組）、測試 local |
| `161eeb6` installTasks／generics | 9 | 11 | 63 | tokens+AST | `module.workspace_path()`（pending） |
| `780a590` VE＋Cerence | 10 | 26（兩檔相同） | 107＋107＋測試 11 | tokens+AST | 測試自己的 `real_player`、`message_type` local；五個測試字串（`_initializeNative` ×3、`_confirmNativeQuiescence` ×2、`_installGuard`、drift 允許清單）都已改到 |
| `053d40b` Espeak | 2 | 6 | 13 | tokens+AST | `_EspeakStrategy.stop_player`（`:109`、`:111`，`NativeStrategy` hook；底下呼叫 `_port.stopPlayer()` 已改） |
| `71589e2` OneCore | 2 | 6 | 16 | tokens+AST | `host.control_error`／`self._segmentHost.control_error` ×7（核心 `SegmentHost` 欄位）；`on_done` → `onDone` 與 NVDA `feed(onDone=)` 同名，`_feedSegment` 一律位置傳入 |
| `c1ed233` RHVoice | 2 | 11 | 35 | tokens+AST | `player.get_player`（`:315`、`:326`，vendored player 屬性）；`:387` 註解裡的 `tts_queue` 跟著改 |
| `ff173d9` SAPI5 | 2 | 3 | 14 | tokens+AST | `host.control_error` ×4（核心）；守門檔只刪行＋清空後的單行收合 |

另外確認：15 個 commit 都只改 `.py`；每個 commit 的非守門變更檔都是純改名；改名 commit 與非機械修改（基底宣告、docstring、`_EventsWhileActive`、harness metaclass、新測試）分開。實作者的 `check.py` 我讀過：它的 AST+註解比對與 token 比對邏輯和我的結論一致，但它依賴群組檔的配對清單與 `KEPT` 表；我的檢查不讀那些，所以是獨立的證據。

## 進度帳本的 `Ruling:` 評估

| Ruling | 評估 |
| --- | --- |
| `check.py` 在 ruff 改括號時改比 AST＋註解（Task 2） | 合理；我另外證明 `test_index_ledger.py` 去括號後 token 流逐一相等 |
| `test_engine_interface_guards._TARGETS` 加 `voiceClass`／`_voiceClass`（`74b6172`） | 合理且必要；只放寬 pattern，保留 `voice_class` 給核心 `voices/manager.py` |
| 測試假物件（`runtime_harness` 的 FakeAdapter／NativeAdapter）跟著宿主 API 改名，其餘測試名字不動 | 合理；spec §3 說 tests 自己的名字不改，但 fake 模仿的是被改名的 API，不跟會壞 |
| `pipeline_log` → `pipelineLogService`（模組名衝突） | 合理；`from .pipelineLog import pipelineLog` 會把套件屬性從子模組換成實例，spec §4.1 寫明 |
| eSpeak／SAPI5／RHVoice harness 的 metaclass 替身改繼承 `ABCMeta` | 合理且比原本更接近 NVDA（`baseObject.py:60`）；舊的 `type` 子類會拒絕任何 ABC 基底，NVDA 不會 |
| `TRANSITIONAL_47C` 也釘住六個名字 | 合理；docstring 本來就說兩個清單都只能縮小，成本一行 |

## 使用者還沒確認的使用者可見預設

本 phase 沒有使用者可見的變化：沒有面板、標籤、訊息、翻譯字串、log 文字、設定鍵、setting id、手勢的變更（已逐項驗證）。spec §11 的五個協調者預設都是內部設計，列出供使用者 merge 前過目：

1. 核心（`voices/manager.py`、`pipeline/context.py`）直接呼叫宿主物件的 camelCase 方法，不另定義核心 Protocol（refactor9 §6.2 已註記將來要一併決定）。
2. `SegmentDrainCore` 是 `runtime/segmentHost.py` 的 ABC，不是 Protocol（NVDA metaclass 限制）。
3. `pipeline_log` 實例改名 `pipelineLogService`（避開模組名）。
4. 執行期訊息字串裡引用的舊名維持原文（例如 `DrainSupport.reason`、`Error in guard_errors callback`）。
5. synth 的 `class SynthDriver(SynthDriver)` 與六個 `class Voice(Voice)` 都改成以別名匯入基底。

## 未在 Windows 驗證

Linux 測試沒有載入 NVDA 真正的 `baseObject.AutoPropertyType`、真的音訊裝置與引擎 SDK；`SegmentDrainCore` 與 NVDA metaclass 的組合只靠 `ABCMeta` 子類的替身（`test_segment_drain_core_combines_with_an_abcmeta_driver_metaclass` 與三個 harness）驗證。沒有打包。建議下次在 Windows 打包測試時，六個引擎各載入一次並說一句話，確認 wrapper 類別能建立（metaclass）且 DRAIN 模式沒有退回 LEGACY_DONE（看 log 裡的 `DrainSupport.reason`）。

## 審閱者留下的檔案

- scratchpad `review47b3/`：`indep.py`、`leftover.py`、`defnames.py`、`msgids.py` 與各輸出（`indep_batch3.txt`、`indep_batch12.txt`、`leftover_head.txt`、`suite_head.log`、`msg_master.txt`、`msg_head.txt`）。
- 暫時 worktree `review47b3/wt` 已在 review 後移除（`git worktree remove`），主檢出與任務 worktree 未動。
