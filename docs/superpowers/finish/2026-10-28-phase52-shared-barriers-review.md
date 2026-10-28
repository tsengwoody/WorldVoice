# Phase 52 Review：逐段語音關卡的共用名稱＋`cancellationToken` 進 `Voice.extraCapabilities`

日期：2026-10-28。分支：`phase52-shared-barriers`（`4ca7e42..186b2aa`，11 個 commit：3 個 docs、1 個 feat、5 個 refactor、2 個 test；基準 `master` `4ca7e42`，3468 passed／0 skipped）。
審閱者：Fable 5.1（唯讀；只新增本檔）。流程：一般流程（DEVELOPMENT_WORKFLOW.md §3.3）；9 個 task 少於 10，沒有批次 review，本次是第一次也是唯一一次 review，看整個分支。四個改名 commit 依 §3.2「改名與搬移的證明」用我自己寫的順序敏感 token 比對獨立重跑（見驗證表）。

依據：

- spec `docs/superpowers/specs/2026-10-28-phase52-shared-barriers-design.md`（§3.1 三種共用關卡、§3.2 逐一分類、§3.4 分組、§4 規則改變、§7 測試與突變、§9 實作紀錄）。
- plan `docs/superpowers/plans/2026-10-28-phase52-shared-barriers.md`（Review Focus 1–5）。
- 進度帳本 `.superpowers/sdd/2026-10-28-phase52-shared-barriers/progress.md`（git 忽略；3 個 `Ruling:`）與實作者的 `tokcheck.py`、`rename.py`、`mutrun.sh`。
- 決策紀錄 `storage/refactor9.md` §6 P52 列（唯讀）：「意思不完全相同的不要硬併（OneCore 的 `sync` 和 `idle` 行為不同、`callback` 和 `returned` 的證據不同）」。
- 程式碼：`addon/synthDrivers/WorldVoice/runtime/barriers.py`（新）、`runtime/segmentHost.py`、`bridge/engineAdapter.py`、`driver/__init__.py`、六個 wrapper、`tests/test_segment_barriers.py`（新）、`tests/test_native_strategy_guards.py`、`tests/test_runtime_legacy_adapter.py`、`tests/test_sapi5_old_nvda.py`、`tests/test_segment_host.py`、`tests/runtime_harness.py`、`tests/test_worldvoice_cancel_wrappers.py`、`tests/test_worldvoice_request_builder.py`。
- NVDA 原始碼（只讀）：`ref/nvda/source/synthDrivers/_espeak.py`、`oneCore.py`、`ref/nvda/source/nvwave.py`。
- 行號以 head `186b2aa` 為準；路徑省略 `addon/synthDrivers/WorldVoice/`。

## 結論

**可以 merge。** Critical 0、Important 0、Minor 3（M1 是本 phase 之前就存在的測試缺口，我在 `master` 上確認過；M2、M3 是守門與測試的小改善，都便宜）。

- **改名是純改名。** 四個改名 commit（G1 `7bf3d87`、G2 `6f61015`、G3 `951c169`、G4 `397df4a`）我用自己的腳本逐檔重比：舊檔 token 流套用 `OLD=NEW` 後，和新檔去掉唯一一行 import 的 token 流在型別、文字、順序上完全相等（含註解）。替換數和帳本一致；刻意保留的同拼法 token（`idle` 這個名字、RHVoice `"message"`、SAPI5 `"processed"`、`tests/test_segment_host.py` 的 `"returned"`／`"done"`／`"ended"`／`"callback"`）數量前後相同。每個 commit 只碰 spec §3.4 列的檔案。
- **分類正確，沒有硬併。** 三種共用關卡的證據我逐一核對（見「分類逐項」）：`SYNTHESIZED` 的三個引擎都是「同步合成呼叫回來了」（eSpeak 以 `AUDIO_OUTPUT_SYNCHRONOUS` 初始化、RHVoice 的 `RHVoice_speak` 同步、VE 的 `_Retire` 排在每個同步 `ve_ttsProcessText2Speech` 任務之後）；`ENGINE_DONE` 三個都是引擎自己的終止通知；`PLAYED_OUT` 四個都是真正的 `WavePlayer.idle()` 回來。保留的四個引擎特有名稱各有不同證據：RHVoice `message` 是前置條件；SAPI5 `processed` 是 EndStream **之後** worker 的收尾（且依賴 `ENGINE_DONE`，`driver/SAPI5/__init__.py:516`）；OneCore `callback` 是非同步交付 callback 裡餵完音訊；OneCore `synced` 只做 `sync()`，不關閉連續段（`nvwave.py:370-382`）。這正是使用者在 refactor9 P52 要求保留的區別。實作者列的替代方案（把 `callback`／`processed` 併進 `SYNTHESIZED`、`synced` 併進 `PLAYED_OUT`）我**不建議採用**：`SYNTHESIZED` 的定義是「同步呼叫回來」，OneCore 與 SAPI5 根本沒有會在完成時回來的合成呼叫；`synced` 和 `PLAYED_OUT` 對 `WavePlayer` 的副作用不同（不重新武裝靜音修剪、不解除 ducking）。要併就得把 `SYNTHESIZED` 改定義成「這筆的音訊全部進了播放器」，那是另一個設計決定，不是改名。
- **行為沒變。** 每個 record 的關卡集合（含 SAPI5／OneCore／VE 的 ordinary 集合）與每個 reach 點都只換了拼法；守門測試 `DECLARED_BARRIERS` 釘住六個引擎的兩個集合。eSpeak 的 `PLAYED_OUT` 來自 runtime 預設（`segmentHost.py:680`），和 eSpeak 在同一個 commit 改；SAPI5 的 `_SegmentPlayer` 傳 `idle_barrier=None`（`:202`）、RHVoice 的 `_WavePlayer` 覆寫 `idle()` 不 reach，所以預設值的改名只影響 eSpeak，和 spec 說的一樣。
- **Part 2 正確。** bridge 只剩 `"cancellationToken" in extra`（`bridge/engineAdapter.py:117`），唯一讀 `supports_cancellation_token` 的是 `_speakPlain`（`:33-37`）。`supportsCancellationToken` 在 `addon/`、`tools/`、readme 全部消失，只剩測試裡「core 上有也不算」的反向斷言。`ref/` 下的 Neural、IBM、Aisound 三個外掛都沒有 `extraCapabilities`、`supportsCancellationToken`、`cancellationToken`，所以照舊是 `speak(commands)`。SAPI5 的 `Voice` 不宣告（繼承 `frozenset()`），舊版 NVDA 換成 `sapi5.SynthDriver` 後 `speak(speechSequence)` 不會收到 token；`tests/test_sapi5_old_nvda.py:195-196,217` 在 2024.1–2025.2 每一版都斷言。「core 說 True、class 沒宣告 → 不傳」這條新規則由 `test_token_support_comes_from_the_voice_class[False-True]` 釘住，我的突變 B3（bridge 重新去讀 core 屬性）被它殺掉。
- **其他。** VE／Cerence 逐字同步（`tests/test_vocalizer_drift.py` 和 `master` 無 diff）；wrapper 之間沒有互相 import，只 import `...runtime.barriers`（核心）；`runtime/barriers.py` 只有三個大寫常數、不 import 任何東西，符合 §6.1。完整套件 3485 passed／0 skipped（+17，和帳本一致）；prek 8 個 hook 全 Passed；`git diff --check` 乾淨；受保護路徑、Neural、`ref/` 都沒有變動。
- 我自己的 21 個突變 17 個被殺、4 個存活：3 個是同一個 RHVoice 缺口（M1，`master` 上同樣存活），1 個是等價突變（VE `_retireRecord` 的 `in` 檢查；見驗證表）。

## Critical

無。

## Important

無。

## Minor

### M1. RHVoice worker 的 `ENGINE_DONE` 閘門沒有測試在看（`driver/RHVoice/__init__.py:242-251`；本 phase 之前就有）

worker 只在 `record.barriers[ENGINE_DONE] and record.barriers[SYNTHESIZED] and …` 都成立時才做最後一次 `player.idle()` 並 reach `PLAYED_OUT`。把 `ENGINE_DONE` 那一項換成 `SYNTHESIZED`（實作者的 m7、我的 R1）或整個拿掉（我的 R1b：`True and …`），`tests/test_rhvoice_segment_drain.py` 74 個測試全過；在 `master` 上做同樣的突變（`"done"`→`"returned"`，R1base）也存活，所以是既有缺口，不是這次改名造成的。

失敗情境：日後有人整理這個條件（例如改成只看 `record.error is None`），done callback 沒來時 worker 仍會對播放器做一次 `idle()`，等到前一筆的音訊真的播完才讓 record 以「缺 `engine_done`」失敗；使用者看到的是取消或失敗變慢，測試全綠。

建議修法（便宜）：`test_missing_done_does_not_drain_after_native_return`（`tests/test_rhvoice_segment_drain.py:53-58`）在拿到 `SEGMENT_FAILED` 後，加一句斷言 harness 播放器的 `idle_count` 只等於內層 `SpeakText` 自己那一次（預期 1；寫測試時先確認 red／green），證明 worker 的最後一次 `idle()` 沒有跑。這一句同時殺掉 R1 和 R1b。

### M2. `_voice_reassigns_core_class` 只認得 `ast.Assign`（`tests/test_native_strategy_guards.py:551-560`）

守門只走訪 `Voice` 類別內的 `Assign` 節點、目標是 `.synthDriverClass` 的 Attribute。`setattr(cls, "synthDriverClass", …)`、`AnnAssign`、或把換 class 的動作放到 `Voice` 以外的 helper 函式，都不會被看到。今天沒事，因為同一個測試在 `:570` 把「宣告 `cancellationToken` 的引擎」釘死為 `{VE, Cerence}`，任何第三個引擎宣告都會先在那裡失敗（我的 G1、G2 就是這樣被殺的）。

失敗情境：將來放寬 `:570` 的精確集合（例如新引擎也宣告 token）時，這個偵測就成了唯一防線，而它漏看上述寫法。

建議修法：在函式 docstring 寫明只看 `Assign`，並在 `:570` 的斷言旁註明「這一行才是真正的防線」；或順手把 `ast.Call` 到 `setattr` 且第二個引數是 `"synthDriverClass"` 的情況也算進去，三行。

### M3. `tests/test_segment_host.py` 用字面 `"played_out"` 複製 runtime 常數的值（`:22`、`:104`、`:150`、`:295`、`:312`、`:323`、`:384`、`:434`、`:680`、`:710`、`:722`）

`LeasedPlayer` 的測試（`:372-385`、`:405-410`、`:626-630`）走 runtime 的預設 `idle_barrier`，所以 fake 宣告的名稱必須和 `runtime/barriers.py:19` 的值一模一樣；現在是 12 處手抄。值要是再改，會以 `KeyError` 失敗（不是無聲），所以只是維護成本，不是正確性問題。spec §8 第二點把「fake 要不要跟著改名」留成開放問題，預設不改。

建議修法（可選）：`FakeStrategy.barriers` 和 `run_native` 的預設改讀 `env.rt.barriers.PLAYED_OUT`（這個測試已經透過 `rt` 載入 runtime 套件），`"returned"` 維持 fake 自己的不透明標籤；`:150`、`:323` 的訊息字串用 f-string 組。改完 token 證明不必重做，因為那是測試檔，不是改名 commit 的產品程式碼。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 完整套件（head `186b2aa`） | `cd /workspace/WorldVoice-phase52 \|\| exit 1; ( while sleep 5; do m=$(awk '/MemAvailable/{print $2}' /proc/meminfo); [ "$m" -lt 3000000 ] && pkill -f pytest && break; done ) & W=$!; python3 -m pytest -p no:cacheprovider tests; kill $W` | **3485 passed／0 skipped**（102.99 s）；基準 3468 → +3（`test_segment_barriers`）+8（關卡守門）+6（token 守門），和帳本一致 |
| prek | `prek run --all-files` | 8 個 hook 全 Passed |
| 空白 | `git diff --check master` | 乾淨 |
| 受保護路徑 | `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' addon/synthDrivers/WorldVoice/driver/sonic/ …script_data.py …unspaced_common_data.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural`；`git diff master --stat -- ref` | 三個都沒有輸出 |
| 改名 commit 的 token 比對（獨立重跑） | 自己寫的 `scratchpad/rev52/tokdiff.py REPO SHA PATH OLD=NEW… --allow-import LINE`：`tokenize` 全部 token（含 COMMENT／NL／INDENT），舊流套用對照表，新流只去掉一行 exactly 等於允許 import 的邏輯行，要求 `(type, text)` 序列相等；另外列出對照表舊名與固定一組同拼法 token 的前後數量，並掃出新檔裡仍含舊名字的字串 | 9 個檔案全部 **OK**：segmentHost `"idle"`→`PLAYED_OUT` 1；Espeak 2／2／1；`test_segment_host.py` `"idle"` 9、整句訊息 1、`"returned, idle"` 1、`"idle, returned"` 1；RHVoice 3／3／2；SAPI5 `"ended"` 4、`"idle"` 2；VE 與 Cerence 各 `"spoken"` 3、`"idle"` 2。保留的同拼法：NAME `idle`（segmentHost 2／2、RHVoice 3／3、SAPI5 5／5、VE／Cerence 3／3）、`"message"` 2／2、`"processed"` 5／5、`test_segment_host.py` 的 `"returned"` 14／14、`"done"` 2／2、`"ended"` 1／1、`"callback"` 2／2。仍含舊字的字串全是 docstring 或錯誤訊息散文（例如 SAPI5 `"… no owned player idle barrier"`、`test_segment_host.py` 的 fault 名 `"idle failed"`），不是關卡標籤 |
| 比對腳本本身 | 對未改的 `driver/OneCore/__init__.py` 用空對照表 → OK；對 Espeak 故意給錯的對照表（`"ended"=PLAYED_OUT`）→ 在第 662 個 token 報 MISMATCH | 腳本能分辨 |
| 每個改名 commit 碰的檔案 | `git show --name-only` | G1 三檔、G2 一檔、G3 一檔、G4 兩檔，和 spec §3.4 一致；改名、常數模組、守門、Part 2 各自獨立 commit |
| 測試裡的字串表／dict key／parametrize id 有沒有漏掉關卡標籤 | `grep -rnE '"(idle\|returned\|ended\|done\|spoken\|processed\|callback\|synced\|message\|synthesized\|engine_done\|played_out)"' tests` | `test_segment_host.py` 以外的命中全是 fault 名（`"feed"`、`"idle"`、`"native"`…）、事件種類（`"index"`、`"done"`）、UI 文字或 VE 測試的順序標記 `("spoken", text)`，都不是 `reach`／`barriers` 的標籤；沒有守門因改名而失去比對對象 |
| `addon/` 剩下的舊字面 | `grep -rnE '"(idle\|returned\|ended\|done\|spoken)"' addon`（排除內層驅動） | 只剩 `runtime/models.py:97` 的 `EventKind.DONE = "done"`（事件種類，不是關卡） |
| `supportsCancellationToken` 殘留 | `grep -rn supportsCancellationToken .`（排除 `ref/nvda`、`.git`、本 phase 的 spec／plan） | 只剩 `tests/test_native_strategy_guards.py:312`、`tests/test_runtime_legacy_adapter.py:78,81,570`、`tests/test_worldvoice_cancel_wrappers.py:65`，全是「不存在／不算數」的斷言 |
| `supports_cancellation_token` 的讀者 | `grep -rn supports_cancellation_token addon tests tools` | 產品程式碼只有 `runtime/models.py:91`（欄位）、`bridge/engineAdapter.py:34,117`；沒有 UI、log、scheduler 讀它 |
| `ref/` 外掛 | `grep -rn 'extraCapabilities\|supportsCancellationToken\|cancellationToken' ref`（排除 `ref/nvda`） | Neural、IBM、Aisound、VE2／Cerence 原版都沒有命中 → 維持 `speak(commands)` |
| SAPI5 舊版 NVDA 路徑 | 讀 `driver/SAPI5/__init__.py:695-724`、`tests/test_sapi5_old_nvda.py:190-247` | `ready()` 只換 `synthDriverClass`／`drainProfile`，`extraCapabilities` 繼承基底的 `frozenset()`；測試在每個舊版都斷言 `"cancellationToken" not in voice.extraCapabilities`、`capabilities.supports_cancellation_token is False`，並真的呼叫 `adapter.speak(…, token)` 走到 NVDA 的 `speak(speechSequence)` |
| 六個 wrapper 的 `speak` 簽章 | `grep -n "def speak(" driver/*/__init__.py` | 只有 VE `:447`、Cerence `:449` 有 `cancellationToken=None`；eSpeak `:159`、RHVoice `:374`、OneCore `:252`、SAPI5 `:440` 都只有 `speechSequence`，和守門「宣告 ⇒ 簽章有該參數」的集合一致 |
| wrapper 互相 import | `grep -n "^from synthDrivers.WorldVoice.driver\." driver/*/__init__.py` | 無；新 import 都是 `from ...runtime.barriers import …`（核心） |
| VE／Cerence 同步 | `git diff master --stat -- tests/test_vocalizer_drift.py`；drift 測試在完整套件內 | 無 diff；通過 |
| §6.1 命名 | `runtime/barriers.py` 三個 UPPER_CASE 常數、模組名小寫；`tests/test_naming_layers.py` 的 CORE 含 `runtime/` | 守門在完整套件內通過 |
| 分類證據 | 逐引擎讀 wrapper 與 NVDA 原始碼（下表） | 和 spec §3.2 一致 |

### 分類逐項（我核對過的 file:line）

| 引擎 | 關卡 | 證據（head） | 判定 |
| --- | --- | --- | --- |
| eSpeak | `SYNTHESIZED` | `espeak_Synth` 的 `finally` reach（`driver/Espeak/__init__.py:48-65`）；NVDA 以 `AUDIO_OUTPUT_SYNCHRONOUS` 初始化（`_espeak.py:371-372`），callback 在呼叫內跑 | 同步呼叫回來 ✓ |
| eSpeak | `ENGINE_DONE` | `index is None` 時 reach（`:182-183`）；NVDA 最後一次無音訊 callback 呼叫 `onIndexReached(None)`（`_espeak.py:172-176`） | 引擎終止通知 ✓ |
| eSpeak | `PLAYED_OUT` | 同一個 callback 先呼叫 `player.idle()`（`_espeak.py:173`），`player` 是 `LeasedPlayer`（`:86`），預設 reach（`segmentHost.py:680,742-743`） | `idle()` 回來 ✓ |
| RHVoice | `"message"`（保留） | `RHVoice_new_message` 成功（`driver/RHVoice/__init__.py:126-133`） | 前置條件，不是完成 ✓ |
| RHVoice | `SYNTHESIZED` | `RHVoice_speak` 成功才 reach（`:140-147`）；內層 `SpeakText.__call__` 同步呼叫（`driver/RHVoice/driver/__init__.py:395-411`） | ✓ |
| RHVoice | `ENGINE_DONE` | done callback 內 reach（`:349-350`） | ✓ |
| RHVoice | `PLAYED_OUT` | worker 最後 `owner._inner.player.idle()` 後 reach（`:249-251`）；`_WavePlayer.idle` 直接轉給真播放器、不 reach（`:202-208`） | ✓ |
| SAPI5 | `ENGINE_DONE` | COM sink `EndStream`（`driver/SAPI5/__init__.py:364-378`） | ✓ |
| SAPI5 | `"processed"`（保留） | `Speak(..., Async)`（`:578-580`），worker 在 EndStream 後 flush Sonic、餵尾音、`_onEndStream` 收尾 bookmark 後 reach（`:597-603`、`:507-529`）；缺 `ENGINE_DONE` 就 raise（`:516-517`） | 依賴 `ENGINE_DONE` 的 wrapper 收尾，不是同步呼叫 ✓ |
| SAPI5 | `PLAYED_OUT` | `drain` 的 `player.idle()` 後 reach（`:150-166`）；`_SegmentPlayer` 傳 `idle_barrier=None`（`:202`），所以不受 runtime 預設影響 | ✓ |
| OneCore | `"callback"`（保留） | `ocSpeech_speak` 非同步（`oneCore.py:462-465`）；在交付 callback 內餵完全部 chunk 後 reach（`driver/OneCore/__init__.py:388-439`、legacy `:450-452`） | 證據來自 callback 內，不是呼叫回來 ✓ |
| OneCore | `"synced"`（保留） | `drain` 只做 `player.sync()` 再等 unpause（`:176-190`）；`sync` 不做 `idle` 的靜音修剪重武裝與 ducking 解除（`nvwave.py:370-382`） | 和 `PLAYED_OUT` 不同 ✓ |
| VE／Cerence | `SYNTHESIZED` | `_Retire` 排在每個同步 `ve_ttsProcessText2Speech` 任務之後（`driver/VE/__init__.py:127-131`、`:160-165`），`_retireRecord` 在 record 仍有效時 reach（`:503-504`；Cerence `:505-506`） | ✓ |
| VE／Cerence | `PLAYED_OUT` | `drain` 的 `driver._realPlayer.idle()` 後 reach（`:325-342`；Cerence `:344`） | ✓ |

### 突變測試（審閱者自己的 21 個；暫時 worktree `/workspace/WorldVoice-rev52mut`（head）與 `/workspace/WorldVoice-rev52base`（`master`），都已移除；`PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider -q -x`，每個 600 s timeout，每次先清 `__pycache__`，輸出在 `scratchpad/rev52/mut-*.txt`；守門檔只在 G 組使用）

| # | 突變 | 測試檔 | 結果 |
| --- | --- | --- | --- |
| R1 | RHVoice worker 讀 `barriers[SYNTHESIZED]` 取代 `[ENGINE_DONE]`（實作者的 m7） | rhvoice drain、runtime drain integration | **存活**（M1） |
| R1base | 同上在 `master`（`"done"`→`"returned"`） | 同上 | **存活** → 既有缺口 |
| R1b | 把 `ENGINE_DONE` 那一項換成 `True` | rhvoice drain | **存活**（M1） |
| V1 | VE `_retireRecord` `SYNTHESIZED in` → `PLAYED_OUT in`（實作者的 m9） | vocalizer drain、cancel wrappers | **存活**：等價——segment record 兩個都宣告（`:299`）、ordinary 兩個都沒有（`_ORDINARY_BARRIERS = frozenset()`） |
| V2 | 同一行把 `in` 檢查整個拿掉 | 同上 | killed（`test_done_of_never_spoken_request_skips_idle[VE]`）→ 那個 `in` 檢查本身有測試在看 |
| E1 | eSpeak `ENGINE_DONE` reach 改成 `SYNTHESIZED` | espeak drain | killed |
| H1 | `LeasedPlayer` 預設改回 `"idle"`（守門排除） | espeak、rhvoice drain | killed（eSpeak `KeyError`） |
| S1 | SAPI5 ordinary 集合丟掉 `"processed"` | sapi5 drain | killed（`test_ordinary_speech_keeps_legacy_notifications_and_indexes`） |
| S2 | SAPI5 strategy 集合丟掉 `PLAYED_OUT` | sapi5 drain | killed |
| S3 | SAPI5 `_onEndStream` 的 `[ENGINE_DONE]` 讀改成 `.get(PLAYED_OUT)` | sapi5 drain | killed |
| O1 | OneCore `drain` reach `"callback"` 取代 `"synced"` | onecore drain | killed |
| RH2 | RHVoice strategy 集合丟掉 `"message"` | rhvoice drain | killed |
| B1 | bridge 讀 `"variant" in extra` | legacy adapter、request builder、sapi5 old nvda | killed |
| B2 | `_speakPlain` 一律傳 token | sapi5 old nvda、legacy adapter | killed（2024.1 舊版 NVDA 的 `speak` `TypeError`）→ 守門的前提成立 |
| B3 | bridge 改成 `… in extra or getattr(core, "supportsCancellationToken", False)` | legacy adapter | killed（`[False-True]`）→ 新規則「core 屬性不算數」真的被釘住 |
| C1 | Cerence `Voice` 拿掉 `"cancellationToken"`（守門排除） | legacy adapter、cancel wrappers、request builder | killed（真 core 的 bridge 測試） |
| G1 | eSpeak `Voice` 宣告 `"cancellationToken"` | 守門 | killed（`speak` 沒有該參數＋精確集合） |
| G2 | SAPI5 `Voice` 宣告 `"cancellationToken"` | 守門、sapi5 old nvda | killed |
| G3 | RHVoice reach `"msg"`（未列的引擎特有名） | 守門 | killed |
| G4 | VE `in` 檢查改用字面 `"spoken"` | 守門 | killed（`in` 比較有被走訪） |
| G5 | OneCore strategy 多加 `PLAYED_OUT`（沒 import） | 守門 | killed |

### Review Focus 逐項

1. **讀而不是 reach 的關卡鍵**（RHVoice `:243-244`、SAPI5 `:262`／`:516`、VE `:503`）：token 比對的替換數涵蓋每一處（RHVoice `"returned"` 3、`"done"` 3；SAPI5 `"ended"` 4；VE `"spoken"` 3）；守門 `_barrier_expressions` 走訪 Subscript、`.get`、`in`（G4 證明 `in` 真的被看到，S3 證明讀的那行有行為測試）。✓
2. **eSpeak 的 `PLAYED_OUT` 來自 runtime 預設**：同一個 commit `7bf3d87` 改兩邊；H1 證明只改一邊會被 eSpeak drain 測試抓到；`test_leased_player_reaches_played_out_by_default` 釘住預設。✓
3. **ordinary 集合**：`DECLARED_BARRIERS` 釘住六個引擎的 strategy 與 ordinary 集合；S1 證明 SAPI5 ordinary 集合有行為測試。✓
4. **SAPI5 舊版 NVDA**：見驗證表；B2 證明傳 token 真的會 `TypeError`，G2 證明宣告會被兩個測試抓到。✓
5. **core 仍帶 `supportsCancellationToken`**：`[False-True]` 案例；B3 證明 bridge 偷讀 core 會被抓到。✓

## Ruling 評估

| Ruling | 評估 |
| --- | --- |
| Task 2：`tests/test_segment_host.py:323` 的 `"returned, idle"`／`"idle, returned"` 子字串沒在 plan 的清單上，完整套件抓到後補進 `OLD=NEW` | 合理。這也說明 spec §3.3「只有 `:22` 和 `:150` 拼出關卡名」原本不準，§9 已更正。我重跑時用整句字串當 token，和帳本一樣 OK。 |
| Task 2：ruff 0.16.3 把 I001 當 unsafe fix，用 `--unsafe-fixes --select I001` 放 import 再做 token 比對 | 合理；比對會證明 import 是唯一多出來的東西。 |
| Task 7：request-builder 的斷言改成看 `voice.engine in ("VE", "Cerence")` | 可接受，但這和 `:197` 的 `supports_token=engine in ("VE", "Cerence")` 是同一個條件抄兩次。更直接的寫法是讀 fake `Voice` 的 `extraCapabilities`；不影響正確性，不列為發現。 |

## 使用者還沒確認的使用者可見預設

- **分類預設（spec §3.2）**：RHVoice `message`、SAPI5 `processed`、OneCore `callback`／`synced` 保留引擎特有名稱；替代方案（併入 `SYNTHESIZED`／`PLAYED_OUT`）未採用。我的判斷：保留是對的，理由見結論；要併需要先改 `SYNTHESIZED` 的定義。
- **NVDA log 的錯誤訊息用字**：`"<engine> synthesis retired without its <names> barriers"` 裡的名字從 `idle`／`returned`／`ended`／`done`／`spoken` 變成 `played_out`／`synthesized`／`engine_done`；引擎特有名稱不變。只出現在 log，不進設定檔、不翻譯、readme 沒提。
- **spec §8 第二點**：`tests/test_segment_host.py` 的 fake 維持 `"returned"` 不透明標籤、`"played_out"` 用字面（M3 建議改讀常數，可選）。
- **M1 不修的話**：RHVoice「done 沒來就不做最後一次 idle」維持沒有測試的狀態（本 phase 之前就是如此）。

## 未在 Linux 驗證的項目（Windows／NVDA 手動）

本 phase 沒有行為改變，不需要新的手動項目；照常的 smoke test 即可：每個引擎各說一段話、取消 VE／Cerence 的語音，並看 NVDA log 沒有 `synthesis retired without its … barriers`。

## 修正記錄

修正者：Opus 5.5（DEVELOPMENT_WORKFLOW.md §3.4）。基準 `a583ea3`（3485 passed／0 skipped）。本輪除了 M1–M3，也落實使用者 2026-10-28 的決定：關卡採用**選項 B′**——依證據證明了什麼來分類、改名定義有變的常數、由 host 強制唯一重要的不變量。只有 Minor，依 §3.4 不需要修正 review。

### 選項 B′（使用者決定）

| commit | 內容 |
| --- | --- |
| `0c0db4e` | `feat`：`runtime/barriers.py` 新增 `AUDIO_FED = "audio_fed"`（這筆的音訊已全部餵進播放器，之後不會再有它的音訊 callback；各引擎證據寫在註解裡）；`ENGINE_DONE` 註明是選用的；`PLAYED_OUT` 改寫為「`idle()` 回來，或 `sync()` 回來加上引擎自己的 unpause 等待；只有 `idle()` 會關閉連續段，本關卡不保證那些副作用」。`SYNTHESIZED` 暫時保留，讓每個 wrapper 各自一個改名 commit。 |
| `a84daed` | 改名：eSpeak `SYNTHESIZED`→`AUDIO_FED`（2 個 token） |
| `f905660` | 改名：RHVoice `SYNTHESIZED`→`AUDIO_FED`（3 個 token；`"message"` 保留） |
| `6d4bbcf` | 改名：VE＋Cerence `SYNTHESIZED`→`AUDIO_FED`（各 3 個 token，同一個 commit；`tests/test_vocalizer_drift.py` 的 `ALLOWED` 未動） |
| `52dd913` | 改名：SAPI5 `"processed"`→`AUDIO_FED`（5 個 token） |
| `53d64f5` | 改名：OneCore `"callback"`→`AUDIO_FED`（4）、`"synced"`→`PLAYED_OUT`（2） |
| `c9d58f1` | 移除過渡用的 `SYNTHESIZED` |
| `a66ca27` | 只加註解：OneCore drain「`sync()` 不是 `idle()`，不會關閉連續段」、交付 callback「也是 OneCore 唯一的終止通知，沒有 `ENGINE_DONE`」；SAPI5 在要求 `ENGINE_DONE` 的 raise 前「`AUDIO_FED` 必須在 `ENGINE_DONE` 之後」 |
| `dc03a46` | eSpeak 把 `AUDIO_FED` 的 reach 從 `finally` 移到成功路徑（見 Ruling） |
| `c9070e2` | `SegmentHost.__init__` 改成要求 strategy 的 `barriers` 含 `PLAYED_OUT`：`ValueError(f"{engine} strategy declares no played-out barrier")`；ordinary 的 `enqueue(barriers=…)` 不受限制（VE 的是空集合） |
| `e89fced` | 守門：`ENGINES` 改為從 `driver/` 列舉（`__init__.py` 定義 `*Strategy` 類別的套件；`sonic` 列為非引擎套件，本機還原、未追蹤的 `Neural` 略過）；引擎特有名稱只剩 `RHVoice: {"message"}`；每個引擎都要有宣告集合列；新增「每個 strategy 的 barriers ⊇ {`AUDIO_FED`, `PLAYED_OUT`}」 |
| `0b4225f` | OneCore 順序斷言：`PLAYED_OUT` 只在 `sync()` 回來之後才 reach |
| `f0f000e` | spec §3：舊分類與協調者預設加刪除線，標註「Decided by the user (2026-10-28): option B′」，新增 §3.5（新定義、逐引擎變更、宣告表、host 檢查、守門） |

新的分類（宣告集合的成員不變，只換拼法）：

| 引擎 | Strategy `barriers` | Ordinary | 各關卡的證據 |
| --- | --- | --- | --- |
| eSpeak | `{AUDIO_FED, ENGINE_DONE, PLAYED_OUT}` | （同 strategy） | 同步 `espeak_Synth` 成功回來；`onIndexReached(None)`；`LeasedPlayer` 的 `idle()` |
| RHVoice | `{"message", ENGINE_DONE, AUDIO_FED, PLAYED_OUT}` | （同 strategy） | `RHVoice_new_message`（前置條件，引擎特有）；done callback；同步 `RHVoice_speak`；worker 最後的 `idle()` |
| SAPI5 | `{ENGINE_DONE, AUDIO_FED, PLAYED_OUT}` | `{ENGINE_DONE, AUDIO_FED}` | `EndStream`；EndStream 後 worker flush Sonic、餵完尾音；drain 的 `idle()` |
| OneCore | `{AUDIO_FED, PLAYED_OUT}` | `{AUDIO_FED}` | 非同步交付 callback 餵完全部 chunk（也是唯一的終止通知）；`sync()`＋unpause 等待（不關閉連續段） |
| VE／Cerence | `{AUDIO_FED, PLAYED_OUT}` | `frozenset()` | `_Retire` 排在每個同步 `ve_ttsProcessText2Speech` 之後；drain 的 `idle()` |

**改名的 token 比對。** 用 `tokcheck2.py`（順序敏感、分辨字串；含 COMMENT／NL／INDENT；`--map` 全檔替換、`--at` 限定舊檔某一行、`--drop-old-line`／`--drop-new-line` 各自只能剛好吻合一行），對每個 commit 的 `sha^` 與 `sha` 重跑，全部 **OK**：上表的替換數；每個 wrapper 唯一多出的差異是排序後的 import 行（OneCore 是新增的 import 行）；守門檔只有該引擎那一列（SAPI5、OneCore 的 `ENGINE_SPECIFIC_BARRIERS` 列以完整舊行／新行列出）。比對腳本本身先驗證過：空對照表、或對照表套到守門檔全檔，都會報 FAIL。腳本與輸出在 `.superpowers/sdd/2026-10-28-phase52-shared-barriers/`（`tokcheck2.py`、`tokchecks-committed.txt`）。

### Minor

| 項目 | commit | 證據 |
| --- | --- | --- |
| M1 | `0745426` | `test_missing_done_does_not_drain_after_native_return` 在 `SEGMENT_FAILED` 之後斷言錯誤提到 `engine_done`，且 harness 播放器的 `idle_count == 1`（只有內層 `SpeakText` 自己那次）。突變 R1（`barriers[ENGINE_DONE]`→`[AUDIO_FED]`）與 R1b（`True and …`）都被這個測試殺掉。 |
| M2 | `32a4123` | `_voice_reassigns_core_class` 也認得 `ast.AnnAssign` 與 `setattr(cls, "synthDriverClass", …)`，docstring 說明只走訪 `Voice` 類別，並在精確集合 `{VE, Cerence}` 那一行註明它才是真正的防線；新增 6 個偵測案例的直接測試。 |
| M3 | `012f02a` | `tests/test_segment_host.py` 在模組層載入 `runtime/barriers.py` 讀 `PLAYED_OUT`，取代 11 處手抄的 `"played_out"`（含兩個缺關卡訊息改用 f-string）；`"returned"` 維持 fake 自己的標籤。host 檢查的 commit（`c9070e2`）另加「沒有 `PLAYED_OUT` 的 strategy → ValueError」、保留空集合案例（改比對新訊息）、「ordinary 空集合仍可 enqueue」。 |

### 突變測試

暫時的 scratch 複本（`git ls-files` 複製、`ref` 用 symlink），`PYTHONDONTWRITEBYTECODE=1`、`-p no:cacheprovider`，每次先清 `__pycache__`、每個 600 s timeout，輸出寫成檔案（`mutants-out.txt`）。

| # | 突變 | 結果 |
| --- | --- | --- |
| H1 | host 檢查改回「非空即可」 | killed（`test_a_strategy_without_played_out_is_rejected`） |
| O1 | OneCore drain 在 `sync()` 之前就 reach `PLAYED_OUT` | killed（`test_onecore_waits_for_tail_sync_before_drain`） |
| S1 | 拿掉 SAPI5 `_onEndStream` 的 `ENGINE_DONE` 檢查 | killed（`test_worker_completion_without_end_marker_fails_exact_work`） |
| P1／P1g | VE strategy 沒有 `PLAYED_OUT`（行為測試／守門） | killed（host 建構時 ValueError；守門 `[VE]`） |
| P2 | OneCore strategy 沒有 `PLAYED_OUT` | killed（host 建構時 ValueError） |
| E1 | `ENGINES` 改回少一個引擎（Cerence）的固定 tuple | killed（`test_every_driver_package_is_an_engine_or_listed`、`test_every_engine_has_a_declared_barriers_row`） |
| E2 | 固定 tuple 含全部六個（對照組） | 存活：等價，今天的列舉結果就是這六個 |
| N1 | 新增一個定義 `*Strategy` 的 wrapper 套件 | killed（5 個守門，含缺宣告列與缺 `AUDIO_FED`／`PLAYED_OUT`）→ 新 wrapper 會被自動納入 |
| N2 | 新增一個沒有 strategy 的套件 | killed（必須明確列為非引擎套件） |
| R1／R1b | RHVoice worker 的 `ENGINE_DONE` 閘門換成 `AUDIO_FED`／`True` | killed（M1） |
| ES1 | eSpeak 的 reach 放回 `finally` | killed（`test_failed_native_synthesis_does_not_reach_audio_fed`） |
| M2 | 偵測函式不看 `setattr` | killed |

### Ruling

- Ruling: `0c0db4e`..`c9d58f1` 之間暫時保留 `SYNTHESIZED`，讓每個 wrapper 的改名各自是一個綠的 commit — 理由：使用者要求逐 wrapper 改名（VE＋Cerence 一起）— 錯了的代價：無（`c9d58f1` 已移除，測試釘住三個公開名稱）。
- Ruling: 每個改名 commit 一併修改守門表裡該引擎那一列 — 理由：維持每個 commit 套件全綠 — 錯了的代價：無（測試檔的列，用 `--at`／整行比對證明沒有夾帶）。
- Ruling: eSpeak 的 `AUDIO_FED` 移到成功路徑（選用項目，決定做）— 理由：失敗的 `espeak_Synth` 並未證明音訊全部餵完；行為不變，因為錯誤在 raise 之前就記在 record 上，retire 與 drain 檢查都先看 `record.error` 再看缺的關卡；新測試同時釘住「不 reach」與「失敗原因是合成錯誤而不是缺關卡」— 錯了的代價：失敗會被報成缺關卡，由該測試抓到。
- Ruling: `test_default_hooks_finish_a_segment` 的 `Bare` strategy 改宣告 `PLAYED_OUT`（原本 `"done"`）— 理由：更嚴格的 host 檢查要求 — 錯了的代價：無。
- Ruling: 列舉 `ENGINES` 時略過未追蹤的 `Neural`（與 `tests/test_engine_interface_guards.py` 相同慣例），`sonic` 是唯一列出的非引擎套件 — 錯了的代價：本機還原的 Neural 不受這組守門檢查（它本來就保留舊介面）。
- Ruling: M1 測試以子字串檢查錯誤訊息提到 `engine_done`，不比對整句 — 理由：`frozenset` 的迭代順序隨 hash seed 變動，整句比對會不穩定 — 錯了的代價：無。

### 驗證

- 完整套件：**3503 passed／0 skipped**（+18：eSpeak 2、host 2、守門 14［套件列舉 1、宣告列 1、⊇ 檢查 6、偵測案例 6］）。
- `prek run --all-files`：全部 Passed。`git diff --check master`：乾淨。
- 受保護路徑（內層驅動、`sonic/`、兩個 Unicode 資料檔）、`git ls-files …/driver/Neural`、`ref/`、`tests/test_vocalizer_drift.py` 相對 `master`：都沒有輸出。
- 使用者可見的變化：只有 NVDA log 的缺關卡訊息用字（`synthesized` → `audio_fed`；OneCore 的 `callback`／`synced`、SAPI5 的 `processed` 變成 `audio_fed`／`played_out`），不進設定、不翻譯、readme 沒提。Windows 上的 NVDA、實際音訊裝置、引擎 SDK 沒有在 Linux 驗證到；手動 smoke test 同 review 原本所列。

## 修正 review（Opus xHigh）

審閱者：Opus 5.5（effort xHigh；DEVELOPMENT_WORKFLOW.md §3.4「修正 review」；唯讀，只新增本節）。範圍：`a583ea3..5e5ebd6` 的 17 個 commit（選項 B′、M1–M3、`SegmentHost` 建構檢查）。行號以 `5e5ebd6` 為準；路徑省略 `addon/synthDrivers/WorldVoice/`。所有暫存檔在 `scratchpad/fix52/`（`tokaudit.py`、`mutate.py`、`tok-out.txt`、`mutants-out.txt`、`seq-out.txt`、`set-out.txt`、`full.txt`）；scratch 複本用 `git ls-files` 複製、`ref` 用 symlink，已刪除；沒有建立 worktree，沒有用 `git stash`。

### 結論

**可以 merge。** 新的 Critical 0、Important 0、Minor 4（兩個是 `runtime/barriers.py` 註解的用字、兩個是守門與測試的強度；都不影響行為，也都便宜）。依 §3.4，只有 Minor，不需要再做一輪修正 review。

- 六個改名 commit 用我自己的順序敏感、分辨字串的 token 比對重跑，全部是純改名；改名、只加註解、eSpeak 的 reach 搬移、host 檢查、守門各自獨立 commit。
- 每個引擎每種 record（segment／ordinary）的關卡集合，成員和大小都不變（每個集合內的對照都是一對一），reach 點也不變；唯一的 reach 搬移（eSpeak，`dc03a46`）在每一條錯誤路徑上都不改變 retire／drain 的結果，也不改變 NVDA 看到的東西。
- host 檢查只會擋下沒有 `PLAYED_OUT` 的 strategy：六個 wrapper、`tests/` 裡的每個 fake 都滿足；ordinary 集合不受限制；SAPI5 舊版 NVDA 路徑根本不建 `SegmentHost`。
- M1、M2、M3 都修好了，測試抓得到原本的錯誤（R1／R1b 被殺；同一個突變配上修正前的測試會存活，證明是新斷言殺掉的）。
- 完整套件 **3503 passed／0 skipped**；prek 8 個 hook 全 Passed；`git diff --check master` 乾淨；受保護路徑、Neural、`ref/`、`tests/test_vocalizer_drift.py` 都沒有變動。

### 逐項檢查

**1. 改名的 token 比對（已驗證）。** 我自己寫的 `tokaudit.py REPO SHA PATH --map KIND:OLD=KIND:NEW … --allow REGEX …`：用 `tokenize` 取全部 token（含 COMMENT／NL／NEWLINE／INDENT／DEDENT），在舊檔 token 流上套用對照表（`STRING` 以含引號的完整原文比對，所以 `"callback"` 不會碰到 `"_callback"` 或散文字串；`STRING`→`NAME` 的型別改變也算進去），再用 `difflib.SequenceMatcher(autojunk=False)` 和新檔比出完整的編輯腳本：相等區塊保持順序，每個不相等的區塊都必須落在 `--allow` 指定的行上（兩邊都檢查）。產品檔只允許 `from ...runtime.barriers import` 那一行；守門檔只允許該引擎在 `ENGINE_SPECIFIC_BARRIERS`／`DECLARED_BARRIERS` 的那一列。

| commit | 檔案 | 結果 |
| --- | --- | --- |
| `a84daed` eSpeak | `driver/Espeak/__init__.py` | OK：`SYNTHESIZED`→`AUDIO_FED` 3（2 個使用＋import），只剩 import 行的重排；`ENGINE_DONE` 3／3、`PLAYED_OUT` 2／2 不變 |
| | 守門檔 | OK：只有 `:411` 的 `"Espeak"` 列，`"SYNTHESIZED"`→`"AUDIO_FED"` |
| `f905660` RHVoice | `driver/RHVoice/__init__.py` | OK：4（3＋import）；`"message"` 2／2、`ENGINE_DONE` 4／4、`PLAYED_OUT` 3／3 不變 |
| | 守門檔 | OK：只有 `"RHVoice"` 列 |
| `6d4bbcf` VE＋Cerence | 兩個 wrapper | 各 OK：4（3＋import）；`PLAYED_OUT` 3／3、`"spoken"` 0／0 |
| | 守門檔 | OK：只有 `"VE"`、`"Cerence"` 兩列 |
| `52dd913` SAPI5 | `driver/SAPI5/__init__.py` | OK：`"processed"`（STRING）→`AUDIO_FED`（NAME）5，唯一多出的是 import 行；舊檔 5 處（`:20`、`:103`、`:262`、`:514`、`:529`）逐一看過都是關卡標籤；`ENGINE_DONE` 5／5、`PLAYED_OUT` 3／3、`idle` 5／5 |
| | 守門檔 | OK：只有兩張表的 `"SAPI5"` 列 |
| `53d64f5` OneCore | `driver/OneCore/__init__.py` | OK：`"callback"`→`AUDIO_FED` 4、`"synced"`→`PLAYED_OUT` 2，唯一多出的是新的 import 行；舊檔 6 處都是關卡標籤；`NVDA_OVERRIDES` 裡的 `"_callback"`（`:73`）是不同 token，6／6 不變 |
| | 守門檔 | OK：只有兩張表的 `"OneCore"` 列 |
| `c9d58f1` 移除 `SYNTHESIZED` | `runtime/barriers.py` | 唯一的差異是刪掉 `# Superseded by AUDIO_FED…`、`SYNTHESIZED = "synthesized"` 和一個空行（腳本報 OUTSIDE 只因 difflib 把相同的 NEWLINE 對到前一行，被刪 token 是 `NEWLINE NL COMMENT NL NAME = STRING`，內容就是那三行） |
| | `tests/test_segment_barriers.py` | OK：只刪過渡註解和 `"SYNTHESIZED"` |
| `a66ca27`（只加註解） | OneCore、SAPI5 | OK：只多 3 個 COMMENT 行（`OneCore :191`、`:441`；`SAPI5 :516`） |

`0c0db4e` 只改 `runtime/barriers.py` 與 `tests/test_segment_barriers.py`（新增常數與註解），不含改名。另外我在 scratch 複本上依序套用每個 commit 的檔案，跑關卡相關的 11 個測試檔（守門、barriers、host、五個 drain、cancel wrappers、drain integration、VE 同步）：17 個 commit 全綠（564 → 566 → 568 → 576 → 582 passed，和每個 commit 新增的測試數一致；`seq-out.txt`），所以「每個改名 commit 都是綠的」這個 Ruling 成立。

**2. 行為不變（已驗證）。** 宣告集合：eSpeak／RHVoice／VE／Cerence 的 `SYNTHESIZED`→`AUDIO_FED`、SAPI5 的 `"processed"`→`AUDIO_FED`、OneCore 的 `"callback"`→`AUDIO_FED`、`"synced"`→`PLAYED_OUT`，在每個 strategy 集合與 ordinary 集合裡都是一對一，所以成員和大小不變。共用名稱沒有帶來新的 reach：OneCore 不用 `LeasedPlayer`，RHVoice 的 `_WavePlayer.idle` 覆寫成不 reach，SAPI5 的 `_SegmentPlayer` 傳 `idle_barrier=None`（`driver/SAPI5/__init__.py:202`），所以 OneCore 的 `PLAYED_OUT` 只在 `drain` 裡 reach。

eSpeak 的 reach 搬移（`dc03a46`，`driver/Espeak/__init__.py:56-65`），逐條錯誤路徑：

| 路徑 | 修正前（`finally`） | 修正後（成功路徑） | retire／drain 回報、NVDA 看到的 |
| --- | --- | --- | --- |
| 原生回傳非 `EE_OK` | 記錯誤→raise→reach | 記錯誤→raise，不 reach | `retire` 先取 `record.error`（`runtime/segmentHost.py:526-528`），`wait_native_boundary`／`wait_playback_drained` 也先看 `record.error`（`:563`、`:572`、`:583`）→ 兩邊都報合成錯誤；同一個 `RuntimeError` 傳到 NVDA 的 `BgThread`，同一行 log（`_espeak.py:213-214`） |
| `espeak_Synth` 本身丟例外（例如 `OSError`） | 同上 | 同上 | 同上；`record_error` 對非 None 的 record 一定會設定錯誤（`:434-437`） |
| 呼叫前已取消、record 無效、或已有 control error | 在 `try` 前就 `return self._ok`，兩邊都不 reach | 同 | 不變 |
| 呼叫中被取消（callback 回 `CALLBACK_ABORT_SYNTHESIS`） | 回 `EE_OK`→reach；回非 OK→記錯誤 | 回 `EE_OK`→reach；回非 OK→記錯誤、不 reach | record 已無效，`retire` 在看錯誤和關卡之前就回 `cancelled`（`:517-524`）；segment 走取消 → 兩邊相同 |
| 呼叫中才 latch control error | 回 OK 時兩邊都 reach | 同 | `latch_control_error` 已把錯誤寫在 record 上（`:445-448`），兩邊相同 |
| 部分 callback 後出錯（例如 `LeasedPlayer.feed` 失敗） | NVDA 的 callback 用裸 `except` 吞掉並 log（`_espeak.py:196-197`），`LeasedPlayer` 先把錯誤記在 record 上；`espeak_Synth` 正常回來→reach | 同 | 兩邊相同 |
| `BaseException`（非 `Exception`） | 不記錯誤、`finally` reach | 不記錯誤、不 reach | 兩邊都因缺關卡失敗，只差訊息多列一個 `audio_fed`；NVDA 的 bg 執行緒實務上不會發生 |

新測試 `test_failed_native_synthesis_does_not_reach_audio_fed[native|native_result]` 同時釘住兩半：我的 ES1（reach 放回 `finally`）兩個參數都被殺；ES2（拿掉 `except` 裡的 `record_error`，讓失敗變成「缺關卡」）被新測試的兩個參數和既有的 `test_observable_callback_or_native_failure_fails_exact_context_after_return[native]` 殺掉。

**3. host 檢查（已驗證）。** `SegmentHost(` 的建構點：六個 wrapper（`Cerence :350`、`Espeak :139`、`RHVoice :308`、`VE :348`、`OneCore :199`、`SAPI5 :390`），宣告都含 `PLAYED_OUT`；`tests/` 只有 `test_segment_host.py` 自己建（`:97` 的 `FakeStrategy`＝`{"returned", PLAYED_OUT}`，`DrainingStrategy`、`PreparingStrategy` 繼承它；`:979` 的 `Bare` 改成 `{PLAYED_OUT}`；`:1094`、`:1103` 是兩個故意被拒的案例）。其他 harness 都建真的 wrapper，完整套件全綠就證明它們都通過。沒有任何地方在執行期改寫 `barriers`（`grep "barriers\s*="` 只有類別屬性與 `enqueue(barriers=…)`）。segment record 一律取 strategy 集合：唯一帶 operation 的呼叫是 `submit_native` → `enqueue(commands, operation)`（`:540`），顯式 `barriers=` 只出現在 ordinary 的 `speak`（OneCore `:265`、SAPI5 `:446`、`:560`、VE `:455`、Cerence `:457`），所以這個檢查涵蓋每一筆 segment record。`test_ordinary_barrier_sets_need_no_played_out` 證明 ordinary 空集合照常可以 enqueue。錯誤訊息 `"{engine} strategy declares no played-out barrier"`，兩個測試用 `^…$` 完整比對；`grep` 不到舊訊息的殘留。SAPI5 舊版 NVDA 路徑：`Voice.ready()` 把 `synthDriverClass` 換成 NVDA 的 `sapi5.SynthDriver`（`driver/SAPI5/__init__.py:713`），不建 `SegmentHost`；`ref/` 的外部外掛都沒有用到 `SegmentHost`／`NativeStrategy`／`runtime.barriers`。突變：H1（改回「非空即可」）、H2（整個拿掉）、H3（訊息改回舊字）都被殺。

**4. `ENGINES` 列舉（已驗證，見 m3）。** `_driver_packages()` 取 `driver/*/__init__.py`，`_defines_strategy` 看模組頂層名稱以 `Strategy` 結尾的類別；`test_every_driver_package_is_an_engine_or_listed` 要求「套件－引擎＝`{"sonic"}`」並且六個已知引擎都在。突變：N1（新增 `driver/Foo/` 定義 `_FooStrategy`、空集合）→ 6 個守門失敗（含缺宣告列、缺 `AUDIO_FED`／`PLAYED_OUT`、沒繼承 `NativeStrategy`），新 wrapper 真的會被納入；N1b（新增沒有 strategy 的套件）、N4（strategy 類別取別的名字）→ 都被列舉檢查擋下。`sonic` 是唯一列出的非引擎套件，正確。但 N3（在 `driver/Neural/` 放一個沒有 `PLAYED_OUT` 的 `*Strategy`）**存活**：略過是看名字，不是看有沒有被追蹤。見 m3。

**5. 註解與文件（大致正確，見 m1、m2）。** 對照 NVDA 原始碼：`idle()`＝`sync()`＋重新開啟前導靜音修剪＋關閉 ducking（`nvwave.py:376-382`），`sync()` 只呼叫 `wasPlay_sync`（`:370-374`）——`PLAYED_OUT` 註解說「只有 `idle()` 會關閉連續段」正確。`AUDIO_FED` 的證據：eSpeak 同步（`_espeak.py:172-176` 的最後一次 callback 在 `espeak_Synth` 內）；VE／Cerence 的 Sonic 尾音在 `VE_MSG_ENDPROCESS`（`driver/VE/driver/__init__.py:190-197`）裡餵，仍在同步的 `ve_ttsProcessText2Speech` 之內；SAPI5 worker 在 `_onEndStream`（`:604`）之前 `sonic.flush()` 並餵尾音（`:597-603`），ordinary 與 segment 都一樣；OneCore 在交付 callback 裡餵完每個 chunk 才 reach（`:439-442`），legacy 在 `super()._callback` 回來後 reach（`:455`）——都對。SAPI5 `:516` 的註解「`AUDIO_FED` 必須在 `ENGINE_DONE` 之後」放在 segment 分支、緊接著那個 raise，正確；OneCore `:191`、`:441` 的註解也和程式一致。兩處不精確見 m1、m2。

**6. M1–M3（已修好）。**

| 突變 | 測試 | 結果 |
| --- | --- | --- |
| R1：RHVoice worker 閘門 `ENGINE_DONE`→`AUDIO_FED` | `tests/test_rhvoice_segment_drain.py` | killed（`test_missing_done_does_not_drain_after_native_return`，`idle_count == 1` 那一句） |
| R1b：閘門那一項換成 `True` | 同上 | killed（同一個測試） |
| R1pre：R1＋把 M1 測試還原成 `a583ea3` 的版本 | 同上 | **存活** → 是新斷言殺掉的 |
| R2：worker 跳過最後的 `idle()` 時仍 reach `PLAYED_OUT` | 同上 | **存活**（見 m4） |
| M2a：偵測函式不看 `AnnAssign` | 守門 | killed（`[cls.synthDriverClass: type = Other-True]`） |
| M2b：偵測函式不看 `setattr` | 守門 | killed（`[setattr(cls, "synthDriverClass", Other)-True]`） |
| G1：VE strategy 拿掉 `AUDIO_FED`（host 不在乎） | 守門 | killed（`[VE]` 兩個） |
| O1：OneCore `drain` 在 `sync()` 之前 reach `PLAYED_OUT` | onecore drain | killed（`test_onecore_waits_for_tail_sync_before_drain`） |
| M3v：把 `runtime/barriers.py` 的值改成 `"played"` | `tests/test_segment_host.py` | 66 個全過——這是想要的：host 測試已不依賴手抄的值（值本身由 `test_shared_barrier_values` 釘住） |

M1 用子字串比對 `engine_done` 的判斷：理由正確（`frozenset` 的順序隨 hash seed 變，整句比對會不穩定），而且真正殺掉 R1／R1b 的是 `idle_count == 1`；我用 `PYTHONHASHSEED` 0、1、2、3、4、5、123、4242 跑三個新測試都通過。不過不必在「整句」和「子字串」之間選：把訊息拆成集合比對，同樣不受順序影響，而且更嚴格（見 m4）。M2 的 6 個直接案例涵蓋一般、tuple、annotated、`setattr` 與兩個反例；docstring 說明只走訪 `Voice`，`{VE, Cerence}` 那一行註明是真正的防線。M3：`tests/test_segment_host.py` 已沒有 `"played_out"` 字面（`grep` 只剩 `tests/test_segment_barriers.py` 的值測試）。

**7. 驗證（已驗證）。**

| 項目 | 指令 | 結果 |
| --- | --- | --- |
| 完整套件（`5e5ebd6`） | `cd /workspace/WorldVoice-phase52 \|\| exit 1; ( while sleep 5; do m=$(awk '/MemAvailable/{print $2}' /proc/meminfo); [ "$m" -lt 3000000 ] && pkill -f pytest && break; done ) & W=$!; python3 -m pytest -p no:cacheprovider tests; kill $W` | **3503 passed／0 skipped**（103.45 s），和修正記錄一致（3485＋18） |
| prek | `prek run --all-files` | 8 個 hook 全 Passed |
| 空白 | `git diff --check master` | 乾淨 |
| 受保護路徑 | `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' …/driver/sonic/ …/script_data.py …/unspaced_common_data.py`；`git ls-files …/driver/Neural`；`git diff --stat master -- ref` | 都沒有輸出 |
| VE／Cerence 同步 | `git diff a583ea3 5e5ebd6 -- tests/test_vocalizer_drift.py` | 無 diff，`ALLOWED` 未動 |
| 突變環境 | scratch 複本、`PYTHONDONTWRITEBYTECODE=1`、`-p no:cacheprovider`、每次先清 `__pycache__`、每個 600 s timeout、輸出寫檔、記憶體監控、序列執行 | 見上表與 `mutants-out.txt` |

### 新的發現

#### m1（Minor）. `PLAYED_OUT` 註解說 OneCore 的 segment mode「never closes it」，說得太滿（`runtime/barriers.py:25-26`；spec §3.5 同一句）

`_segmentMode` 開啟後，ordinary 句子也經過同一個 worker，交付 callback 把它轉給 `_legacyCallback`（`driver/OneCore/__init__.py:400-401`），佇列清空時會呼叫 `self._player.idle()`（`:468`），也就是會關閉連續段。只有 segment 的 `drain`（`:177-192`）只做 `sync()`。使用者決定的原文是「OneCore segment mode only `sync()`s」；「never closes it」是多加的。

失敗情境：日後有人依這句註解推論「OneCore 在 segment mode 下前導靜音修剪與 ducking 永遠不會重設」，據此在 OneCore 加上補償（例如自己再 `idle()` 一次，或假設 ducking 一直開著），結果和 ordinary 句子結束時的 `idle()` 重疊。不影響目前的行為。

修法：改成「OneCore's segment drain only calls sync(), so a segment never closes it (an ordinary utterance that empties the queue still calls idle())」，spec §3.5 同步改。

#### m2（Minor）. `AUDIO_FED` 對 RHVoice 的證據，只有和 `ENGINE_DONE` 一起才成立；模組 docstring 與守門的要求不一致（`runtime/barriers.py:8-9`、`:12-15`）

RHVoice 內層的 `AudioPlayer.play` 會留住最後一塊音訊（`driver/RHVoice/driver/__init__.py:236-241`），要等 done callback 的 `on_done()`（`:261-265`、`:347`）才餵出去。所以 `RHVoice_speak` 成功回來（wrapper `:147` reach `AUDIO_FED`）只證明「之後不會再有它的 callback」；「全部音訊都餵進播放器」要再加上 `ENGINE_DONE`。現在沒有問題，因為 RHVoice 的 record 宣告 `ENGINE_DONE`，worker 的閘門也要求兩者（`:243-244`）。另外模組 docstring 說「nothing else about a strategy's set is required」，可是 `test_every_strategy_feeds_and_plays_out_its_audio`（`tests/test_native_strategy_guards.py:552`）要求每個 wrapper 都宣告 `AUDIO_FED`。

失敗情境：日後有人依 `AUDIO_FED` 的定義認為 RHVoice 的 `ENGINE_DONE` 是多餘的（docstring 也說它是選用的，像 VE），把它從 RHVoice 拿掉，或把閘門簡化成只看 `AUDIO_FED`；done callback 沒來時，留住的最後一塊不會播出，record 卻可能被當成成功。

修法：在 `AUDIO_FED` 的註解補一句「(RHVoice: together with ENGINE_DONE, whose callback feeds the last chunk the inner player holds back)」；docstring 那句改成「SegmentHost requires nothing else; the guard tests also expect AUDIO_FED from every current wrapper」。

#### m3（Minor）. 列舉 `ENGINES` 時用名字略過 `Neural`，會把一個有 strategy 的 Neural 藏起來（`tests/test_native_strategy_guards.py:14`、`:21`）

`_driver_packages()` 不論內容，直接去掉名為 `Neural` 的套件。我的 N3（`driver/Neural/__init__.py` 放一個 `barriers = frozenset()` 的 `_NeuralStrategy`）讓守門 46 個全過。實際風險低：`.gitignore:23` 忽略整個目錄，§7 也檢查 `git ls-files …/driver/Neural`，要追蹤它得連犯兩條規則；而且 `SegmentHost` 的執行期檢查仍會擋下缺 `PLAYED_OUT` 的情況。但「略過未追蹤的套件」這件事，現在其實是「略過叫這個名字的套件」。

失敗情境：Neural 改寫成新介面（有自己的 `*Strategy`）後在本機開發，守門完全不檢查它的關卡命名、宣告列與 `AUDIO_FED`；若哪天被 `git add -f` 進來，也一樣不會被檢查。

修法（便宜）：不要從 `_driver_packages()` 拿掉 Neural；讓它和其他套件一樣，定義了 `*Strategy` 就進 `ENGINES`；列舉檢查改成 `set(_driver_packages()) - set(ENGINES) - UNTRACKED_PACKAGES == NON_ENGINE_PACKAGES`。我用 `zipfile` 看過 `storage/Neural-snapshot-2026-10-01.zip`：它的 `driver/Neural/__init__.py` 沒有任何 `*Strategy` 類別，所以本機還原的舊版 Neural 仍然只是被允許的非引擎套件，不會讓測試變紅。

#### m4（Minor，可選）. M1 測試用子字串比對，抓不到「沒有證據就 reach `PLAYED_OUT`」（`tests/test_rhvoice_segment_drain.py:60`）

`assert env.outer.ENGINE_DONE in str(event.error)` 只確認 `engine_done` 在缺少的名單裡。我的 R2（worker 跳過最後的 `idle()` 時照樣 reach `PLAYED_OUT`）存活：缺少的名單從 `engine_done, played_out` 變成只有 `engine_done`，子字串仍然成立。record 照樣失敗，所以不是使用者看得到的錯誤；但這正是這個 phase 要防的「關卡說謊」。

修法：把訊息拆成集合比對，不受 hash seed 影響：

```python
missing = str(event.error).removeprefix("RHVoice synthesis retired without its ").removesuffix(" barriers")
assert set(missing.split(", ")) == {env.outer.ENGINE_DONE, env.outer.PLAYED_OUT}, str(event.error)
```

我在 scratch 複本上試過：head 在 `PYTHONHASHSEED` 0、1、7 都通過，R2 在三個 seed 下都被殺（`set-out.txt`）。

### 使用者還沒確認的使用者可見預設（本輪新增）

- 沒有新增。NVDA log 缺關卡訊息的用字變化（`audio_fed`、OneCore 與 SAPI5 改用共用名稱）已在修正記錄列出；host 檢查的 `ValueError` 只會在 wrapper 寫錯時出現在 log，不會出現在設定或 UI。

### 未在 Linux 驗證的項目

和原 review 相同：Windows 上的 NVDA、實際音訊裝置、引擎 SDK 都沒有驗證到。OneCore 的 `PLAYED_OUT` 現在由 `sync()`＋unpause 等待證明，屬於改名，行為沒變；手動 smoke test 照原 review 所列即可。

## 修正記錄（修正 review 的 Minor）

修正者：Opus 5.5（DEVELOPMENT_WORKFLOW.md §3.4、§8）。範圍：`287f28c` 之後的 4 個 commit。只有 Minor，依 §3.4 不再做修正 review。行為不變；內層驅動、`ref/`、Neural 都沒有動。暫存檔在 scratchpad 的 `m52/`（`m4-out.txt`、`m3-red.txt`、`m3-green.txt`、`m3-out.txt`、`full.txt`）；突變用 `git ls-files` 複製的 scratch 複本（`ref` 用 symlink），沒有建立 worktree，沒有用 `git stash`。

| 發現 | commit | 修正 |
| --- | --- | --- |
| m1 | `e35a3b1` | `runtime/barriers.py` 的 `PLAYED_OUT` 註解與 spec §3.5：改成「OneCore 的 segment `drain` 只呼叫 `sync()`，所以 drain 一個 segment 不會關閉連續段；segment mode 下的 ordinary 句子在佇列清空時仍會呼叫 `idle()`（`_legacyCallback`）」。只改註解，沒有可寫的測試。 |
| m2 | `bd74bc3` | `AUDIO_FED` 註解、RHVoice 的 reach 點（`driver/RHVoice/__init__.py`，外層 wrapper）與 spec §3.5 都註明：RHVoice 內層播放器留住最後一塊，要等 done callback 才餵出，所以 RHVoice 的 `AUDIO_FED` 只有和 `ENGINE_DONE` 一起才代表「全部音訊都餵了」。模組 docstring 改成「SegmentHost 只要求 `PLAYED_OUT`；守門測試另外要求每個 strategy 都宣告 `AUDIO_FED`」。只改註解。 |
| m4 | `a40daf7` | `tests/test_rhvoice_segment_drain.py` 的 M1 測試把缺少的關卡名稱拆成集合，和 `{ENGINE_DONE, PLAYED_OUT}` 比對。 |
| m3 | `f741c91` | `_driver_packages()` 不再用名字去掉 Neural；定義了 `*Strategy` 的 Neural 就進 `ENGINES`，套用所有通用守門，只免除宣告列（`DECLARED_BARRIERS`）、列舉檢查（`- UNTRACKED_PACKAGES`）與 token 引擎名單。新測試 `test_a_local_neural_is_guarded_when_it_defines_a_strategy[strategy|snapshot]` 在 `tmp_path` 放一個合成的 Neural、把 `ROOT` 指過去。spec §3.5 的 Guards 段同步改。 |

### 紅／綠證據

- **m4**（`PYTHONDONTWRITEBYTECODE=1`、`-p no:cacheprovider`、每次先清 `__pycache__`、600 s timeout、輸出寫檔、記憶體監控、序列執行）：突變 R2＝RHVoice worker 在閘門不成立時仍 `reach(PLAYED_OUT)`（跳過最後的 `idle()`）。`PYTHONHASHSEED` 0、1、7：R2＋舊測試 35 passed（存活）；R2＋新測試 1 failed（`test_missing_done_does_not_drain_after_native_return`，`retired without its engine_done barriers`，被殺）；head＋新測試 35 passed。head＋新測試另在 seed 2、123、4242 都 35 passed。
- **m3**：先只加 `_engines()`（純重構）與新測試、保留名字略過：`[strategy]` 失敗（`assert () == ('Neural',)`），`[snapshot]` 通過；修正後守門檔 48 passed。scratch 複本放真的 `driver/Neural/__init__.py` 比較守門檔新舊版：

  | `driver/Neural` | 舊守門（`287f28c`） | 新守門 |
  | --- | --- | --- |
  | 沒有 | 46 passed | 48 passed |
  | `storage/Neural-snapshot-2026-10-01.zip` 的 `__init__.py`（沒有 `*Strategy`） | 46 passed | 48 passed |
  | N3：`_NeuralStrategy`，`barriers = frozenset()` | 46 passed（存活） | 3 failed（`feeds_and_plays_out[Neural]`、`segment_drain_entries`、`token_capability[Neural]`；被殺） |
  | 合格的 Neural（`AUDIO_FED`＋`PLAYED_OUT`、`SynthDriver(…, SegmentDrainCore)`、`Voice`） | 46 passed | 51 passed（免除宣告列與名單，沒有 KeyError） |

### Ruling

- **Ruling（m3）：** token 引擎名單那一句（`declared is (engine in {"VE", "Cerence"})`）也算「逐引擎的名單」，對未追蹤套件免除；同一個測試裡的通用部分（換掉 core class 就不能宣告 token、宣告了就要固定 core 且 `speak` 收 token）仍然套用。理由：名單只列追蹤中的引擎，和 `DECLARED_BARRIERS` 同性質。
- **Ruling（m3 測試）：** 合成 Neural 的測試直接呼叫 `test_every_strategy_feeds_and_plays_out_its_audio("Neural")` 並用 `monkeypatch.setitem(globals(), "ROOT", tmp_path)`，證明真正的守門會擋下，而不是另寫一份平行的判斷。

### 驗證

| 項目 | 結果 |
| --- | --- |
| 完整套件（`f741c91`，記憶體監控） | **3505 passed／0 skipped**（102.93 s；3503＋m3 的 2 個參數） |
| `prek run --all-files` | 8 個 hook 全 Passed |
| `git diff --check master` | 乾淨 |
| 受保護路徑、`git ls-files …/driver/Neural`、`git diff --stat master -- ref`、`tests/test_vocalizer_drift.py` | 都沒有輸出 |
