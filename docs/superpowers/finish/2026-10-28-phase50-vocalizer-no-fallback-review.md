# Phase 50 Review：VE／Cerence 拿掉「guard 裝不上就退回原版驅動」路徑

日期：2026-10-28。分支：`phase50-vocalizer-no-fallback`（`0c3aaa7..b94f023`，6 個 commit：3 個 docs、2 個 refactor、1 個 test；基準 `master` `0c3aaa7`，3379 passed／0 skipped）。
審閱者：Fable 5.1（唯讀；只新增本檔）。流程：一般流程（DEVELOPMENT_WORKFLOW.md §3.3）；3 個 task 少於 10，沒有批次 review，本次是第一次也是唯一一次 review，看整個分支。

依據：

- spec `docs/superpowers/specs/2026-10-28-phase50-vocalizer-no-fallback-design.md`（§3 盤點表 15 列、§6 突變計畫、§8 實作紀錄）。
- plan `docs/superpowers/plans/2026-10-28-phase50-vocalizer-no-fallback.md`（Review Focus 1–5）。
- 進度帳本 `.superpowers/sdd/2026-10-28-phase50-vocalizer-no-fallback/progress.md`（git 忽略；1 個 `Ruling:`）。
- 決策紀錄 `storage/refactor9.md` §6 P50 列（唯讀）；歷史 spec `docs/superpowers/specs/2026-09-24-speech-request-lifecycle-design.md:50,60-61,111,129,149`（主 checkout 裡的 git 忽略檔，內容確實是當年「只有防護安裝成功的 core 才設 `supportsCancellationToken = True`」的設計）。
- 程式碼：`addon/synthDrivers/WorldVoice/driver/VE/__init__.py`（本檔行號以 head 的 VE 檔為準，master 的行號另外標 `master:`；Cerence 同一段落在 +0 到 +10 行後，`tests/test_vocalizer_drift.py` 釘住兩檔只差 `ALLOWED` 四處）、內層 `driver/VE/driver/__init__.py`、`bridge/engineAdapter.py`、`bridge/completionPolicies.py`、`driver/__init__.py`、`voices/manager.py`、`runtime/playbackWork.py`。
- NVDA 原始碼 `ref/nvda/source/autoSettingsUtils/autoSettings.py:42-45`（`AutoSettings.__del__` 只做 `pre_configSave.unregister`）、`driverHandler.py:35-50`。
- 審閱者自己的突變 11 個與 bridge 整合測試 2 個：`scratchpad/p50review/mutants.py`、`run_mutants.sh`、`test_review_p50_bridge.py`，結果 `scratchpad/p50review/summary.txt`、`mut_R*.txt`。

使用者已決定、本次只核對實作的事項（refactor9.md P50 列）：先盤點每個 `if not self._guardInstalled` 分支，確認發布版本走不到才拿掉；拿掉後 VE／Cerence 和其他 wrapper 一樣「一律安裝，名稱由測試把關」；內層不動；VE 與 Cerence 改法相同。**實作全部符合。**

## 結論

**Ready to merge：Yes。** Critical 0、Important 0、Minor 3（都可不修；M3 建議在 merge 前順手加）。

- **盤點表（spec §3）審閱者從 `0c3aaa7` 獨立重列，結論相同。** `grep -n _guardInstalled` 在 master 的 VE 檔正好 15 處（`master:213,307,350,419,427,430,434,437,456,536,545,667,744,763,834`，另加 `:308`、`:438` 兩個 "unavailable" 字串與 `:433` 的 property），Cerence 同樣 15 處（`:213,307,352,421,429,432,436,439,458,538,547,674,751,770,841`），和 spec 表上的 15 列與 Cerence 行號逐一吻合；head 兩檔與 `addon/`、`tests/` 其他地方都沒有這個名字了（`grep -rn _guardInstalled addon tests` 只剩守門測試的字串）。
  - **(a) 五個屬性不可能缺。** `self._isSilence`、`self._player`、`self._veCallbackHandler` 由包裝層自己的 `_initializeNative` 指派（head `:385,391,392`；`master:388,394,395`），它失敗就直接 raise，走不到 `_installGuard`；`callback._isSilence`／`_player`／`_feedBuf` 由 vendored 內層 `VECallback.__init__` 無條件指派（內層 `:103-110`，VE／Cerence 行號相同），而且五個名字都在 `_VEPort.INNER_PRIVATES`（`:65-85`），由 `test_vocalizer_inner_privates_are_listed_and_exist` 對內層原始碼做 `\b` 比對。
  - **(b) 替身建構不可能失敗。** `_IdleRoutingPlayer.__init__`（`:100-102`）只存一個屬性加 `weakref.ref(driver)`；同一個物件在 `:349`（`_VEStrategy(self)` → `:301`）已經成功被弱參考過。
  - **建構期間沒有任何 guarded 入口會跑。** 審閱者逐行看過 `_initializeNative`（`:371-402`）：`ve2.initialize`、`BgThread(self._bgQueue)`（daemon，起來就在空 queue 上 `get()` 等）、`WavePlayer(...)`、`_ContextualVECallback(self, …, self._onIndexReached)`（只把 bound method 存起來，`:197-202`，不呼叫）、`VE_CBOUTNOTIFY(...)`（ctypes 包裝，不呼叫）、`getAvailableResources()`、`next(iter(self.availableVoices))`（內層 `_getAvailableVoices` `:547-551` 只讀 `_resources`，不碰 `getParameters`）、兩個普通屬性。native callback 只會在 `ve_ttsProcessText2Speech` 裡被叫，而那只來自 `_NativeTask`（`:155-158`），此時 queue 是空的；`speak`／`cancel`／`pause`／`terminate`／`getParameters` 都要先有 core 實例在手上（`createCore` `driver/__init__.py:87-88` 要等 `__init__` 回來）。所以「`return super()` 分支拿掉後，提早呼叫會撞到半建構狀態」這個顧慮不存在——而且 master 上同樣的提早呼叫也會走到半建構的內層方法，不是這個 phase 新增的風險。
  - **`_installGuard` 新寫法與舊寫法在成功路徑上同義。** 舊：`real = self._player; self._player = _IdleRoutingPlayer(real, self); self._realPlayer = real`；新：`self._realPlayer = self._player; self._player = _IdleRoutingPlayer(self._realPlayer, self)`（`:404-408`）。`_realPlayer` 仍是真的 `WavePlayer`，`_player` 是替身；`test_installs_player_stand_in_and_keeps_inner_stop_flag` 釘住，審閱者 R2（把順序換成 `_realPlayer` 變成替身）23 個測試失敗。
- **失敗形狀（Review Focus 2）正確。** `_installGuard` 或 `_initializeNative` raise → `SynthDriver.__init__` raise → `createCore` raise（`driver/__init__.py:87-88`）→ `VoiceClassAdapter.open` 在 `self._core = …` 之前 raise（`bridge/engineAdapter.py:72`，`_core` 仍是 None、`_opened` 仍是 False）→ `VoiceManager._open_engine` `log.error("engine %s on error")` 後 `return None`、跳過這個引擎（`voices/manager.py:95-99`）。`close()`（`:99-101`）看到 `_opened` False 直接返回，`destroyCore`／`terminate` 不會碰到半建構的 core；審閱者的 `test_open_failure_leaves_adapter_closed_and_never_terminates`（VE、Cerence）用注入的安裝失敗走完這條鏈，`adapter.core is None`、`terminate` 呼叫 0 次，head 上綠。半建構的實例沒有任何強參考留著（`_VEStrategy`、`_RecordTask`、`_ContextualVECallback` 都用 weakref；`VE_CBOUTNOTIFY` 抓的是 callback 物件不是 driver），被回收時只會跑 NVDA 的 `AutoSettings.__del__` → `pre_configSave.unregister(self.saveSettings)`，對從未註冊的 handler 是 no-op。唯一留下的是 BgThread、`ve2.initialize` 與 `WavePlayer`（見 M1，pre-existing）。
- **`supportsCancellationToken` 常數與 bridge（Review Focus 1、3）。** `bridge/engineAdapter.py:117` 用 `getattr(self._core, "supportsCancellationToken", False)` 讀**實例**，class attribute 自然被找到；`_speakPlain`（`:33-37`）據此帶 `cancellationToken=token`。審閱者的 `test_bridge_passes_token_to_real_wrapper`（真的 VE／Cerence 包裝層 core 經 `VoiceClassAdapter.open()`）：`capabilities.supports_cancellation_token is True`、`_speakPlain` 收到 `[(["hi"], token)]`，head 上綠；R5（整個拿掉屬性）、R11（設成 False）都被它與既有的 `test_installs_player_stand_in_…` 抓到。完成契約：`completionPolicies.drainSupport`（`:66-104`）沒改，`get_segment_drain_support` 現在無條件回 `unverified_drain_support(_PROFILE, …)` = `DrainSupport(True, …, "DRAIN explicitly enabled; … unverified")`（`runtime/playbackWork.py:40-45`），接著 `:98-103` 由 `forceUnverifiedDrain` 決定 DRAIN 或降為 `DrainSupport(False, …)` → `contractFor`（`:106-140`）選 `_DRAIN_CONTRACT` 或 `CompletionContract()`（LEGACY_DONE）——和 master 上 `_guardInstalled` 為 True 時完全同一條路；master 上 `_guardInstalled` 為 False 的那條（`DrainSupport(False, …, "guard installation is unavailable")`）在發布版本從未走過。`runtime/`、`bridge/`、其他四個引擎對 master 無 diff。
- **VE 與 Cerence 相同；內層與受保護路徑沒動（Review Focus／spec 反目標）。** 兩檔對 master 的 diff 在把 `Cerence`→`VE`、`_CerenceStrategy`→`_VEStrategy`、hunk 標頭抹掉後 `diff` 只剩 index 行；`tests/test_vocalizer_drift.py` `ALLOWED` 無 diff；`git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' …` 無輸出；兩個內層檔逐行 `diff` 只差引擎名與 `ve2`／`ttsapi`，行號一致（spec 說「Cerence 內層同行號」成立）；兩個包裝層只 import 自己的 package 與 `...runtime`。
- **刪掉的測試只釘 fallback。** `test_missing_private_field_falls_back_without_partial_install`（5 參數）、`test_missing_callback_…`、`test_fallback_delegates_each_original_method`（4 參數）全都要靠 `new_core(missing=…)` 先把屬性 `delattr` 掉才進 fallback 模式，斷言的都是 `supportsCancellationToken is False`、內層方法被委派——沒有一個斷言在 guarded 路徑上成立過。`new_core` 的 `callback_proxy` 自 `b1c5174`（phase 49）起沒有呼叫者，`original.SynthDriver.__init__` 那條分支也早在包裝層有 `_initializeNative` 後就不可達。`test_assignment_failure_falls_back_unchanged` 改寫成 `test_install_failure_raises_from_the_constructor` 是同一個注入點（`__setattr__` 攔 `_player = _IdleRoutingPlayer(...)`），斷言從「退回」換成「raise」，正好對應 D1。
- **測試真的抓得到。** 把 master 的兩個包裝層配上 head 的測試（含審閱者兩個），失敗的正好是 `test_install_failure_raises_from_the_constructor`、`test_vocalizer_wrapper_has_no_guard_fallback`、`test_open_failure_leaves_adapter_closed_and_never_terminates`（各 ×VE／Cerence），其餘 317 個（含所有 guarded 路徑測試與 `test_bridge_passes_token_to_real_wrapper`）在 master 上也綠——證明新測試只區分這個 phase 改的決定，而 guarded 路徑前後行為一致。審閱者 11 個突變全部被抓到（下表）。
- 完整測試 **3361 passed、0 skipped**（基準 3379 − 20 個 fallback 項目 + 2 個結構守門；和帳本、spec §8 一致）；`prek run --all-files` 8 個 hook 全部 Passed；`git diff --check master` 乾淨；6 個 commit 都沒有 `Co-Authored-By`，內文都有說明理由。兩個包裝層各 +4／−46 行（VE 953 → 911，Cerence 963 → 921）。沒有 readme、changelog、可翻譯字串或儲存鍵的變動（符合 spec §5：發布版本永遠走 guarded 路徑，NVDA 使用者聽不出差別）。

## Critical

無。

## Important

無。

## Minor

### M1. 建構中途失敗會留下 BgThread、`ve2.initialize` 與 `WavePlayer`（pre-existing，本 phase 只是不再把這種 core 回傳）

- 位置：`addon/synthDrivers/WorldVoice/driver/VE/__init__.py:371-408`（`_initializeNative` 從 `:380` 起就有活著的 daemon thread、`:377` 已 `ve2.initialize`、`:385` 已開 `WavePlayer`；之後 `:399-400`、`:404-408` 任何一步 raise 都不會收回）。內層自己的 `__init__`（內層 `:272-298`）同樣沒有收回，是 vendored 行為；spec §2 已列為非目標。
- 失敗情境：引擎語音資源壞掉讓 `getAvailableResources()` 或 `next(iter(self.availableVoices))`（空 dict → `StopIteration`）raise：引擎被 voice manager 跳過（正確），但這個 NVDA 行程裡會多一條在空 queue 上等的 daemon thread，和一個沒 close 的 `WavePlayer`，直到 NVDA 關閉。`_installGuard` 那兩行照 (b) 不可能 raise，所以本 phase 拿掉 `try/except` 不會讓這條路多出新的觸發方式；舊碼在安裝失敗時反而會把 core 回傳、之後由 `terminate` 收回——那是這個 phase 刻意改掉的（D1），也是其他 wrapper 現在的做法。
- 建議：不在本 phase 修。若將來要收，在 `_initializeNative` 把 `:380` 之後的步驟包進 `try`，`except` 時 `self._bgQueue.put(None)`、`self._player.close()`（若已建）、`ve2.terminate()` 後 re-raise；約 8 行，VE／Cerence 同步改，並補一個「`getAvailableResources` raise 時 BgThread 已結束、player 已 close」的測試。

### M2. 結構守門用原始碼字串找 `_guardInstalled`，註解裡提到舊名就會紅

- 位置：`tests/test_native_strategy_guards.py:271`（`assert "_guardInstalled" not in source`）；帳本 Task 3 的 `Ruling:`。
- 內容：Ruling 的理由成立——`getattr(self, "_guardInstalled", True)` 這種用字串繞過的分支（實作者 M4、審閱者 R8）只看 `ast.Attribute` 抓不到，而且它在行為上惰性，沒有行為測試能抓。字串比對是最便宜的解法；代價如 Ruling 所寫，兩個包裝層的註解與 docstring 從此不能提這個名字。審閱者判斷**可接受**：這個名字本來就沒有理由再出現在包裝層裡，而且失敗訊息一看就懂。
- 失敗情境：有人在包裝層加一行 `# formerly _guardInstalled` 的註解，守門紅掉；修法顯而易見，不會誤導。
- 建議（可不做）：改成 AST 層的檢查就能允許註解又抓到 R8：`{n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}` 不含 `"_guardInstalled"`。約 3 行。

### M3. 沒有測試讓真的 VE／Cerence core 經過 `VoiceClassAdapter` 讀 `supportsCancellationToken`

- 位置：`tests/test_worldvoice_cancel_wrappers.py:62-64`（在 core 上直接斷言屬性）、`tests/test_runtime_legacy_adapter.py:73-87`（用假 core 斷言 bridge）；`bridge/engineAdapter.py:117`。
- 內容：Review Focus 1 的證據是兩個各自以名字斷言的測試，它們共用同一個字串，所以任一邊改名都會有一個紅——鏈是有釘住的。但 D2 把 property 換成 class attribute 的正確性（「`getattr` 在實例上找得到 class attribute」）目前只靠閱讀；審閱者 R4（把常數改成 `__init__` 裡的實例屬性，行為等價）只被結構守門抓到，R5／R11 才有行為測試（`test_installs_player_stand_in_…`）跟著紅。
- 失敗情境：將來若 bridge 改成讀 `type(core)` 以外的地方、或包裝層把常數搬進 `Voice`，現有測試不一定會在「token 沒傳進 VE」這個真正的症狀上失敗。
- 建議：把審閱者的 `test_bridge_passes_token_to_real_wrapper`（`scratchpad/p50review/test_review_p50_bridge.py`，去掉 `"supportsCancellationToken" not in vars(core)` 那行即可——那是審閱者為了分辨 R4 加的，不該進正式測試）加進 `tests/test_runtime_legacy_adapter.py`：真的包裝層 core 經 `adapter.open()`，斷言 `capabilities.supports_cancellation_token is True` 且 `_speakPlain` 把 token 傳到 `core.speak`。約 18 行，VE／Cerence 參數化。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 完整測試（head `b94f023`，序列、記憶體看門狗、bytecode 關閉） | 任務 worktree `/workspace/WorldVoice-phase50`：`( while sleep 5; do … MemAvailable < 3000000 → pkill pytest … ) & PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q tests` | **3361 passed, 0 skipped**（99.8 s）；基準 3379；看門狗沒觸發（起跑時 MemAvailable 5.7 GB） |
| prek | `prek run --all-files`（任務 worktree） | 8 個 hook 全部 Passed |
| 空白 | `git diff --check master` | 乾淨 |
| 受保護路徑 | `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' addon/synthDrivers/WorldVoice/driver/sonic/ …script_data.py …unspaced_common_data.py` | 無輸出 |
| Neural | `git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 無輸出 |
| `runtime/`、`bridge/`、其他四個引擎、drift 測試未動 | `git diff --stat master -- addon/synthDrivers/WorldVoice/runtime …/bridge …/driver/{RHVoice,OneCore,SAPI5,Espeak} tests/test_vocalizer_drift.py` | 無輸出 |
| VE／Cerence 改法相同 | 兩檔對 master 的 diff 以 `sed` 把 `Cerence`→`VE`、`_CerenceStrategy`→`_VEStrategy`、hunk 標頭抹掉後 `diff` | 只剩 `index` 行不同 |
| 盤點表獨立重列 | `git show master:…/VE/__init__.py \| grep -n '_guardInstalled\|unavailable\|installation failed\|supportsCancellationToken'`，Cerence 同 | VE 15 處、Cerence 15 處，行號與 spec §3 完全一致 |
| head 殘留 | `grep -rn '_guardInstalled\|supportsCancellationToken\|_realPlayer' addon/`（排除內層） | `_guardInstalled` 0 處；`supportsCancellationToken` 只有 bridge `:117` 與兩個 class constant；`_realPlayer` 只在 `_installGuard` 指派、其餘都是讀 |
| 內層兩檔 | `diff driver/VE/driver/__init__.py driver/Cerence/driver/__init__.py` | 只差引擎名、`ve2`／`ttsapi`、一個 index 解碼；行號一致 |
| 建構期間可達的入口 | 逐行讀 `_initializeNative`（`:371-402`）、`_ContextualVECallback.__init__`（`:197-202`）、內層 `BgThread`（`:79-98`）、`VECallback.__init__`（`:103-115`）、`_getAvailableVoices`（`:547-551`） | 沒有 callback、`getParameters`、`cancel`／`pause`／`terminate` 會在 `_installGuard` 之前跑 |
| 半建構 core 的收尾 | 讀 `bridge/engineAdapter.py:68-74,99-108`、`voices/manager.py:93-99`、NVDA `autoSettings.py:42-45`、`driverHandler.py:35-50` | `open` raise 時 `_core` 仍 None、`_opened` False；`close` 直接返回；`__del__` 只 unregister |
| 審閱者 bridge 整合測試（head） | 暫時 worktree `/workspace/WorldVoice-p50rev`（`ref` symlink）：`tests/test_review_p50_bridge.py`（2 個測試 ×VE／Cerence） | 4 passed |
| master 包裝層 + head 測試 | 暫時 worktree 換入 `master:driver/VE/__init__.py`、`Cerence/__init__.py`，跑 cancel-wrappers、segment-drain、native-strategy-guards、legacy-adapter、drift、drain-integration + 審閱者測試 | 6 failed／317 passed；失敗的只有 `test_install_failure_raises_from_the_constructor`、`test_vocalizer_wrapper_has_no_guard_fallback`、`test_open_failure_leaves_adapter_closed_and_never_terminates`（各 ×2） |
| commit 訊息 | `git log master..HEAD --format='%h %(trailers)'`、`%B` | 沒有 `Co-Authored-By`；6 個都有 `<type>: <summary>` 與理由 |
| spec 引用 | `docs/superpowers/specs/2026-09-24-speech-request-lifecycle-design.md` | 主 checkout 存在（`.gitignore:14 docs` 忽略、未 commit），引用的 `:50,60-61,111,129,149` 內容與 spec §1 的描述相符 |
| 暫時 worktree | `git worktree remove /workspace/WorldVoice-p50rev` | review 後移除 |

### 突變測試（審閱者自己的 11 個，暫時 worktree，`PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider`，每個 600 s timeout，先清 `__pycache__`，輸出寫檔）

VE 與 Cerence **同時**套用同一個突變（避免 drift 守門造成假陽性）。目標檔：`tests/test_worldvoice_cancel_wrappers.py`、`test_vocalizer_segment_drain.py`、`test_native_strategy_guards.py`、`test_runtime_legacy_adapter.py` + 審閱者的 `test_review_p50_bridge.py`（283 個，未突變對照 283 passed，每輪約 13–36 s）。

| # | 突變（VE head 行號） | 結果 | 抓到它的測試（節錄） |
| --- | --- | --- | --- |
| R1 | `_installGuard` `:407-408` 包進 `try/except Exception: return`（實作者 M1） | 抓到 | `test_install_failure_raises_from_the_constructor` ×2、審閱者 `test_open_failure_…` ×2 |
| R2 | `_installGuard` 指派順序對調，`_realPlayer` 變成替身本身 | 抓到 | 23 個，含 `test_installs_player_stand_in_…`、`test_speak_returns_before_native_synthesis` |
| R3 | `_installGuard` 只設 `_realPlayer`，不裝替身 | 抓到 | 45 個，含 `test_cancel_before_native_call_starts_skips_it`、`test_direct_core_cancel_still_reports_done` |
| R4 | class constant 改成 `__init__` 裡的 `self.supportsCancellationToken = True`（行為等價） | 抓到（只有結構） | `test_vocalizer_wrapper_has_no_guard_fallback` ×2（審閱者測試的 `vars(core)` 斷言也紅，見 M3） |
| R5 | 整個拿掉 `supportsCancellationToken`（bridge 會丟掉 token） | 抓到 | `test_installs_player_stand_in_…` ×2、`test_vocalizer_wrapper_has_no_guard_fallback` ×2、審閱者 `test_bridge_passes_token_to_real_wrapper` ×2 |
| R6 | drain support 回 `DrainSupport(True, _PROFILE, "verified")`（理由沒有 unverified） | 抓到 | `test_guarded_native_profiles_are_enabled_with_unverified_evidence` ×4 |
| R7 | drain support 回 `DrainSupport(False, _PROFILE, "x")`（實作者 M3） | 抓到 | 同上 ×4 |
| R8 | `cancel` 開頭加回 `if not getattr(self, "_guardInstalled", True): return super().cancel()`（實作者 M4） | 抓到 | `test_vocalizer_wrapper_has_no_guard_fallback` ×2（只有結構守門，與帳本 Ruling 一致） |
| R9 | `__init__` `:369` 不呼叫 `_installGuard()` | 抓到 | 175 個（`_realPlayer` AttributeError） |
| R10 | `__init__` 先 `_installGuard()` 再 `_initializeNative()` | 抓到 | 60 failed + 169 errors（`_player` 尚不存在） |
| R11 | `supportsCancellationToken = False`（實作者 M2） | 抓到 | `test_installs_player_stand_in_…` ×2、結構守門 ×2、審閱者 bridge 測試 ×2 |

實作者的 4 個突變（spec §8）審閱者以 R1、R11、R7、R8 重做，結果相同；M4 在只看 `ast.Attribute` 的第一版守門下存活、改字串比對後被抓到的說法與 `5227e08` 的 diff 一致。

### Review Focus 逐項

1. PLAIN 入口帶 token：`bridge/engineAdapter.py:117` 在實例上 `getattr`，class attribute 可見；`test_installs_player_stand_in_…` 斷言 `core.supportsCancellationToken is True`，`test_runtime_legacy_adapter.py:73-87` 斷言 bridge 依這個屬性決定 `cancellationToken=`；審閱者 `test_bridge_passes_token_to_real_wrapper` 把兩端接起來在真的包裝層上驗過（R5、R11 抓到）。見 M3 建議把它收進正式測試。
2. `_initializeNative` 之後的安裝失敗：`test_install_failure_raises_from_the_constructor` → `pytest.raises(RuntimeError, match="injected install failure")`；R1 抓到；審閱者另外證明 adapter 不會持有也不會 terminate 這個 core。
3. WASAPI／legacy 的 drain support：`test_guarded_native_profiles_are_enabled_with_unverified_evidence[2026.3-wasapi]`、`[2025.3-legacy]` → `supported` 且理由含 "unverified"；R6、R7 抓到。完成契約的選擇（`:98-103`、`:106-140`）沒改，審閱者逐行比對過。
4. native call 之外的 callback：`test_callback_rejects_audio_outside_native_call` → `NUAN_E_TTS_USERSTOP`、`fed == []`；`_ContextualVECallback.__call__`（`:209-224`）拿掉分支後直接進 `_callbackAdmission`，`call is None` → `(None, None)` → USERSTOP；在 master 包裝層上同樣綠。
5. 替身上的 pause／terminate：`test_guard_keeps_original_pause_and_terminate` 與 `test_vocalizer_segment_drain.py` 的 pause／terminate 測試在完整測試裡全過；R3（不裝替身）45 個失敗證明替身路徑有釘住。

## Ruling 評估

| Ruling | 評估 |
| --- | --- |
| Task 3：結構守門從只看 `ast.Attribute` 改成 `"_guardInstalled" not in source`，以抓到 M4 的 `getattr(self, "_guardInstalled", True)` | 合理。M4 這種分支在行為上惰性（預設值讓它永遠不成立），沒有行為測試能抓，只能靠結構；spec §6 本來就寫「the wrapper source has no `_guardInstalled` name」，字串比對才是 spec 的字面意思，plan 第一版的 AST 版本反而偏弱。代價（註解不能提舊名）如實記下，審閱者接受；AST 層的替代寫法見 M2，可做可不做。 |

spec 的三個「*Decided by orchestrator with the recommended default*」（D1 安裝不檢查、失敗從建構子 raise；D2 保留 `supportsCancellationToken` 為 class constant；D4 連 `callback_proxy` 一起刪）審閱者都同意：D1 和 OneCore／SAPI5／RHVoice／eSpeak 的失敗形狀一致（RHVoice `driver/RHVoice/__init__.py:306-326` 同樣在 `__init__` 直接讀內層私有屬性）；D2 是 bridge `:117` 的硬需求，少了它 VE／Cerence 在 PLAIN 入口會收不到 token；D4 刪的是沒有呼叫者的參數。

## 使用者還沒確認的使用者可見預設

這個 phase 沒有 NVDA 使用者看得到或聽得到的改變（發布版本永遠走 guarded 路徑；唯一的差別是從未出現過的兩條 `log.warning` 文字不再存在）。以下是 spec §7 列的實作層預設，使用者可在 merge 前覆寫：

1. **D1**：VE／Cerence 安裝替身時不再檢查五個內層私有屬性，也不再 `try/except`；任何失敗從 `SynthDriver.__init__` raise，voice manager 記 `engine VE on error` 後跳過引擎（和其他四個 wrapper 一樣）。不加「建構時逐一讀 `_VEPort` 名字」的執行期檢查（那是 P51 針對 NVDA 內建引擎的做法，使用者已排除 vendored 內層）。
2. **D2**：`supportsCancellationToken` 保留為 class constant `True`（不刪、不改成 runtime 的通用能力宣告）。
3. **D4**：測試 harness 的 `new_core()` 不再接受 `missing`／`callback_proxy`。
4. **M2、M3** 要不要在 merge 前順手做。

## 未在 Linux 驗證的項目（Windows／NVDA 手動）

這個 phase 沒有新增必要的手動項目：發布版本的程式路徑逐行與 master 相同（只少了永遠為假的分支）。Linux 上沒有 VE／Cerence SDK、NVDA 與音訊裝置。若之後為別的 phase 打包，可順手用 VE 與 Cerence 各做一次「朗讀、Ctrl 取消、Shift 暫停／恢復、切換合成器」確認沒有回歸，但不是這個 phase 的 merge 條件。
