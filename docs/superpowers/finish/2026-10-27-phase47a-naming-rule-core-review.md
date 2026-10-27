# Phase 47a Review：分層命名規則、守門測試與核心側改名

日期：2026-10-27。分支：`phase47a-naming-rule-core`（`8e1df5b..2354744`，8 個 commit）。
審閱者：Fable 5.1（唯讀；只新增本檔）。流程：複雜流程（DEVELOPMENT_WORKFLOW.md §4.5）。

依據：

- 規則來源 `storage/refactor9.md` §6.1（含 2026-10-27 的 `@override` 更正）與 §6 的 P47a／P47b／P47c。
- spec `docs/superpowers/specs/2026-10-27-phase47a-naming-rule-core-design.md`。
- plan `docs/superpowers/plans/2026-10-27-phase47a-naming-rule-core.md`。
- 進度帳本 `.superpowers/sdd/2026-10-27-phase47a-naming-rule-core/progress.md`（git 忽略）。

使用者 2026-10-27 的決定（不再討論，只核對實作）：分層規則與套件歸屬、覆寫介面照原名、核心改名不留相容別名、最低 NVDA 維持 2024.1 所以不用 `typing.override`，改用守門測試讀繼承關係加 `INTERFACE_NAMES`。實作全部符合，見下表。

## 結論

**Ready to merge：Yes。** Critical 0、Important 0、Minor 5。

- 六個改名 commit 都是純改名：用審閱者自己寫的、逐 token 順序比對的檢查（不是實作者的腳本）證明每個 commit 只把 plan 列出的名字改成 `snake(old)`，保留下來的舊名也恰好是 plan 寫明要保留的那幾處（`__init__.py` 的宿主屬性 `self.taskManager` 6 處與 `_set_voice(self, voiceName)` 4 處、`sayAll.py` 裡 NVDA 的 `speech.speech.getTextInfoSpeech` 2 處與 docstring、`segmentHost.py` 的 `feed(…, onDone=None)`、傳給 NVDA player 的 `onDone=` 關鍵字與兩段 docstring）。
- 分支每個 commit 的 `HEAD:addon`／`HEAD:tests` 都和 plan 一致；在乾淨 clone 從 `8e1df5b` 重放 plan 得到相同的最終 tree id（見「重放結果」）。
- 守門測試能抓到它聲稱要抓的錯誤（在 scratch 複本逐一破壞，12 種情境見驗證表）。
- 沒有使用者可見的行為變更；沒有動到受保護路徑；commit 沒有 `Co-Authored-By`，都只 stage 明確路徑。

## Critical

無。

## Important

無。

## Minor

### M1. 覆寫方法的參數整批豁免，沒有和基底的簽名比對

- 位置：`tests/test_naming_layers.py:677-682`（`_Walker.function`：`overrides` 一旦成立，該方法**所有**參數都以 `overrides=True` 登記）。
- 失敗情境（已在 scratch 複本驗證）：宿主層 `bridge/commands.py` 加上

  ```python
  class Probe(LeasedPlayer):
      def _feed_admitted(self, record, data, size, on_done, extra_snake_param=None):
          self.last_record = record
  ```

  守門只回報 `Probe.last_record`，`extra_snake_param`（宿主層的 snake_case 參數，基底沒有這個參數）沒有被回報。spec §4.3 說「the parameters of such a method mirror the base」，但實作沒有真的比對。
- 影響：只限「覆寫可讀基底的方法」的參數，47b 把 wrapper 改成明確繼承 Protocol 之後，wrapper 自己加的參數會漏檢。方向是漏報，不是誤報。
- 建議：`_resolve`／`inherited` 已經拿得到基底的 `ast.ClassDef`，可以順便收集每個方法的參數名（`{method: {param, …}}`），參數只在「基底同名方法也有這個參數」時才豁免；基底讀不到時本來就不豁免，不受影響。

### M2. 動態綁定和 `match` 的捕獲名稱不在檢查範圍

- 位置：`tests/test_naming_layers.py:650-675`（`_Walker.visit` 只看 `ast.Name(Store)`、`ExceptHandler`、`Lambda`）與 `:519-531`（`_self_fields` 只看 `self.x = …`）。
- 失敗情境（已驗證）：核心模組加上 `setattr(self, "camelName", 1)`、`other.camelAttr = 2`，或 `match x: case [matchCapture]:`，守門 `18 passed`，三個名字都沒有被回報。
- 影響：目前 add-on 沒有 `match` 敘述，核心的 `setattr` 只有 `bringup.py:52,60` 與 `breaks.py:96`，名字都是變數不是字面值，所以今天沒有漏網；這是 AST 守門的固有邊界。
- 建議：`visit` 加上 `ast.MatchAs`／`ast.MatchStar`／`ast.MatchMapping.rest` 的名字（三行）；`setattr` 字面值與「設在別的物件上的屬性」寫進 docstring 的「不檢查」清單即可，不必追。

### M3. `test_no_module_imports_typing_override` 到時候會用 `pytest.skip` 自我停用

- 位置：`tests/test_naming_layers.py:739-747`。
- 情境：最低 NVDA 一旦改成 2026.1，這個測試變成 `skipped`，完整測試就不再是「0 skipped」，和 §7「skip 只能來自缺少的選用元件」的基準規則衝突；帳本的 Ruling 也寫了「one test to drop when the minimum moves」。
- 建議：到時直接刪掉測試（或改成在條件成立時 `return`），現在不用動。記在這裡是讓升版的人看得到。

### M4. 兩個機械式改名產生的拗口名字

- `voices/manager.py:88` `_set_voice_datas`（保留 "Datas"）；`pipeline/sayAll.py:19-24` 外層 `_wrap_get_text_info_speech_with_sayall_break` 和內層 `get_text_info_speech_with_say_all_break` 一個 `sayall` 一個 `say_all`（設定鍵是 `sayall_wait_factor`）。
- 帳本 Ruling 的理由成立：嚴格 `snake(old)` 才能用 token 比對證明 commit 是純改名，這一點審閱者也靠它驗證了。不是缺陷。
- 建議：之後用簡化流程補一個非機械的小改名（例如 `_build_catalog`／`_set_voice_data`，內層改成 `…_with_sayall_break`），或併入 47b；本 phase 不處理。

### M5. 「守門讀得到每一種名字」的 pinning 測試可以再多幾個案例

- 位置：`tests/test_naming_layers.py:791`（11 個案例）。
- 情境：巢狀函式、`except … as`、`with … as`、walrus、`global`、comprehension 變數、`cls.x`、`*args/**kwargs`、async def 都沒有案例。審閱者在 scratch 複本逐一驗證過 walker 目前都讀得到（巢狀 def／class、comprehension、walrus、`nonlocal`、`global` 皆回報），但將來改 walker 時沒有測試會擋住退步。
- 建議：加 3～4 個 parametrize 案例（巢狀 def、walrus、`global`、`cls.x`）。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 完整測試（分支 head `2354744`，scratch clone `probe`，單一 pytest 程序加 MemAvailable < 3 GB 看門狗） | `bash runtests.sh probe tests` | `3287 passed`，0 skipped（基準 3269 + 18） |
| 守門測試 | `pytest tests/test_naming_layers.py` | `18 passed`（7 個測試 + 11 個 parametrize 案例） |
| `prek run --all-files`（probe clone） | — | 8 個 hook 全部 Passed |
| `git diff --check 8e1df5b` | — | 無輸出 |
| 受保護路徑與 Neural | `git diff --stat 8e1df5b -- 'driver/*/driver/' driver/sonic/ script_data.py unspaced_common_data.py`；`git ls-files …/driver/Neural` | 都無輸出 |
| 每個 commit 的 tree id | `git rev-parse <sha>:addon <sha>:tests`，8 個 commit | 881e797 `b62ed753…/17cab13c…`、070b846 `a7cc2080…/f1700693…`、c1ef0d2 `4ad1d341…/80037cae…`、ce08409 `c3f8e830…/a1b522ee…`、d7a3984 `cff5438f…/fae672a0…`、feeb7f0 與 2354744 `5e9cb1fb…/9ebbdff7…`；全部和 plan 寫的一致 |
| 每個 commit 的檔案清單 | `git show --stat` 對照 plan 各 task 的 `git add` 路徑 | Task 2：10 檔、Task 3：18 檔、Task 4：8 檔、Task 5：2 檔、Task 6：3 檔，完全相同；`8997278` 與 `2354744` 只動 `docs/` |
| commit 訊息 | `git log --format=%B` | 英文 `<type>: <summary>` 加內文；沒有 `Co-Authored-By` |
| 純改名（審閱者自己的檢查 `mycheck.py`：舊檔套 `\b名字\b` → `snake()` 後和新檔逐 token 順序比對，忽略 NL／NEWLINE／INDENT／DEDENT 與括號前的逗號；另外列出**保留**舊名的 token） | 五個改名 commit | Task 2：52 個 token 改名、保留 `taskManager` ×6 與 `voiceName` ×4（`__init__.py`）、`taskManager` ×1（`test_runtime_composition.py`）；Task 3：156；Task 4：86；Task 5：26；Task 6：12，保留 `getTextInfoSpeech` ×2 與 docstring（`sayAll.py`）、`onDone` ×4 與兩段 docstring（`segmentHost.py`）。數字和 plan 的預期一致，保留處全是 spec §5 寫明的例外 |
| `tests/test_naming_layers.py` 在改名 commit 裡的變動 | 每個 commit 的 diff 只看 `+` 行 | Task 2～5 零個新增行（只刪 `TRANSITIONAL_47A` 的條目）；Task 6 刪掉整個清單，新增的兩行只是 `_listed(...)` 去掉 `TRANSITIONAL_47A` |
| 舊名殘留 | `git grep -nw` 全樹（排除 vendored 內層、守門檔、docs） | 只剩 VE／Cerence 核心自己的 `getVoiceInstance`／`_instanceCache`／`getVoiceNameForLanguage` 與用它們的 7 個測試檔、OneCore vendored 的 `driver.availableLanguages`、synth 宿主屬性 `self.taskManager` 與測試的 `synth.taskManager`、NVDA 的 `filter_speechSequence`；和 plan Task 7 grep A／B 一致 |
| 動態存取 | `git grep` `setattr(`、`spec=`、`__dict__`、`namedtuple`、`__slots__`、`"<舊名>"` 字串 | `test_runtime_drain_integration.py:355`、`test_vocalizer_segment_drain.py:724` monkeypatch 的是 `control.core`／`env.core`，即 VE／Cerence vendored 核心（harness `self.core = … env.core`），不是 `VoiceManager`；核心沒有以字面值 `setattr` 的 camelCase 名字；`ref/Neural` 不用任何改名的名字 |
| 關鍵字呼叫 | `git grep -E "speechSequence=\|availableLanguages=\|voiceName=\|baseInstance=\|taskManager="` | 只有 `__init__.py:237` 的 `task_manager=`（已改）；NVDA `Filter.apply` 用 `callWithSupportedKwargs(handler, value, **kwargs)` 把序列**位置**傳入（`ref/nvda/source/extensionPoints/__init__.py:114`）；say-all 透過 `*args, **kwargs` 轉呼叫 |
| `onDone`／`on_done` 的拆法 | 讀 `segmentHost.py:661-700`、`driver/SAPI5/__init__.py:171-195`、`driver/RHVoice/__init__.py:175-190`、`tests/test_segment_host.py:1014,1060` | `feed` 維持 `onDone`（RHVoice／OneCore 以關鍵字呼叫 NVDA player）；`_feed_admitted`／`_callback` 的所有呼叫（SAPI5:188、RHVoice:183、測試:1060、基底:665,669）都是位置參數，所以 SAPI5／RHVoice 覆寫保留 `onDone` 不影響執行；覆寫因基底定義同名方法而豁免 |
| 分類表對照 §6.1 | 讀 `CORE`／`HOST`／`PENDING`／`EXCLUDED`（`tests/test_naming_layers.py:38-66`） | 核心 10 項、宿主 7 項（含 `driver/__init__.py`、`installTasks.py`、`generics/`）、待定 2 項、排除 3 類，和 §6.1 表格一致；`find addon -name '*.py'` 的 86 個模組全部有歸屬 |
| `INTERFACE_NAMES` 的 3 條 | `runtime/models.py:34` `rateBoost: bool` 對應 `voiceSettings.py:23` 設定 id；`segmentHost.py:661` `feed(…, onDone=None)` 對應 `ref/nvda/source/nvwave.py:313`；`speechCommands.py:33` `self.isDefault` 對應 `ref/nvda/source/speech/manager.py:101` 的 `command.isDefault` | 三條都是守門讀不到的外部介面或存起來的 id，沒有多餘條目；清單同時受 `test_lists_hold_only_names_that_break_the_rule` 約束 |
| 守門能抓錯（scratch 複本 `probe`，每次破壞後還原） | 核心 `locales.py` 加 camelCase def | `1 failed, 17 passed`，回報 `locales.py:18 badName` |
| 同上 | 核心加 camelCase 參數、區域變數、`self.` 欄位、類別欄位 | 4 個名字全部回報 |
| 同上 | 宿主 `bridge/commands.py` 加 snake_case def | 回報 `bad_name` |
| 同上 | 新增未分類模組 `synthDrivers/WorldVoice/confspec.py` | `test_every_add_on_module_has_a_layer` 失敗 |
| 同上 | 從 `TRANSITIONAL_47B` 刪掉 `SynthDriver.voice_manager` | `test_naming_follows_layer` 回報 `__init__.py:357 SynthDriver.voice_manager` |
| 同上 | 在 `TRANSITIONAL_47B` 加一條已合規的 `SynthDriver.supportedSettings` | `test_lists_hold_only_names_that_break_the_rule` 失敗 |
| 同上 | 核心 `from typing import override` | `test_no_module_imports_typing_override` 失敗 |
| 同上 | 巢狀 def／class、comprehension、walrus、`nonlocal`、`global` | 全部回報（`match` 捕獲除外，見 M2） |
| 同上 | `class SynthDriver(SynthDriver)` 本體加 `probe_snake_method` | 回報（§4.4 的自我遮蔽修正有效） |
| 同上 | 核心類別繼承宿主 `VoiceFacade`，覆寫 `update_settings` 並加 `someHostName` | 只回報 `someHostName`，覆寫豁免正確 |
| 同上 | `setattr(self, "camelName")`、`other.camelAttr`、`match` 捕獲、覆寫方法多加 snake_case 參數 | 不回報（M1、M2） |
| 實作者的工具 | 讀 `scratchpad/p47a/planrun.py`、`checklog.py`、`dryrun.sh` | `planrun.py` 照段落順序執行 bash／`File:`／`Edit:` 區塊，`Edit:` 要求舊文字恰好出現一次；bash 區塊 `check=False`，所以要靠 `checklog.py` 逐一比對預期輸出（含 tree id），我重放時另外自己 grep 了 tree id 和 passed 數 |
| plan Review Focus 1～5 指定的測試 | `git grep -l "def <名稱>"` | 9 個測試全部存在且在完整測試中通過；`test_worldvoice_lifecycle.py:38` 的假 `VoiceManager` 已取 `task_manager` |
| 帳本的 7 條 Ruling | 逐條讀 | 都合理：`@override` 的否決有 `buildVars.py:39` 與 NVDA changes.md 佐證並經使用者確認；檢查區域變數讓規則維持一句話，代價只有 47b 多 42 條；`TRANSITIONAL_47A` 只在 phase 內存在，提供每個 task 的 red；`onDone` 拆法只讓 `feed` 保留關鍵字介面 |
| mutmut | — | 未跑：本 phase 沒有決策邏輯變更（spec §9） |

## 重放結果（§4.5）

在 scratchpad 建全新 clone（`git clone /workspace/WorldVoice`，`checkout -b replay 8e1df5b`，`ref` 連到主 checkout，`prek install`），用實作者的 `planrun.py`（讀過）和自己的 `dryrun.sh`（只改 `$SCRATCH` 指向審閱者的目錄），把分支上 commit 進來的 plan 文字從 Task 1 Step 1 跑到 Task 7 Step 2。

- **第一次重放**：每一步的 red／green 輸出與 passed 數都和 plan 相同（`18 passed`、各 task 的 `Left contains N more items` 與首項、六次 `3287 passed`），但六個 `git commit` 都因為全新 clone 沒有 git 身分而失敗（`Author identity unknown`），所以 `git rev-parse HEAD:…` 一直印基準值。這是審閱者的環境問題，不是 plan 的問題。失敗前工作樹已累積到 Task 6 的狀態，`git add -A addon tests && git write-tree` 得到 `addon` = `5e9cb1fbc5bff84d56ae3669a2fba3c316de6b47`、`tests` = `9ebbdff74ed7505e7ea9cc01fc62f1571971b972`，和分支相同。
- **第二次重放**（clone 設好身分後從基準重來）：21 個步驟全部成功，每個 commit 的 hook 第一次就通過，`git status --short` 每次都是空的。六個 commit 的 tree id：Task 1 `b62ed753…/17cab13c…`、Task 2 `a7cc2080…/f1700693…`、Task 3 `4ad1d341…/80037cae…`、Task 4 `c3f8e830…/a1b522ee…`、Task 5 `cff5438f…/fae672a0…`、Task 6 `5e9cb1fb…/9ebbdff7…`，和 plan 及分支的對應 commit 逐一相同；最終 `HEAD:addon` = `5e9cb1fbc5bff84d56ae3669a2fba3c316de6b47`、`HEAD:tests` = `9ebbdff74ed7505e7ea9cc01fc62f1571971b972`，等於分支 `2354744` 的值。每個 task 的 red（`Left contains 13／17／26／7／5 more items`，首項相同）、`18 passed`、`3287 passed`、stat 行、實作者 token 檢查的數字（52／156／86／26／12）都和 plan 一致；Task 7 的 `prek`、`git diff --check`、受保護路徑、Neural 與 grep A／B 的輸出也和 plan 列的完全相同（用實作者的 `checklog.py` 比對：`all expected outputs found in order`，另外自行 grep 了 tree id 與 passed 數）。結論：plan 文字可以從基準逐位元組重現分支，分支沒有 plan 以外的修改。

## 47b／47c 交接項目的分類意見（spec §11；本 phase 不改）

- `GlobalPlugin.script_popup_SpeechSettingsDialog`、`script_switch_log_record`（`globalPlugins/WorldVoice/__init__.py:127,134`，列在 `TRANSITIONAL_47B`）：NVDA 的 `gestures.ini` 以 `script_` 後面的名字記使用者自訂的手勢（`ref/nvda/source/inputCore.py:879,930`），改名等於清掉使用者的綁定，性質和規則 3 的設定鍵一樣。放在 47B 清單只能算「待決定」的暫放；建議 47b 預設**不改名**，改放進 `INTERFACE_NAMES`（或新開一張「存起來的 id」表，和 `rateBoost` 同類），除非使用者願意付出遷移 `gestures.ini` 的代價。
- `_SilenceGate.is_set`（`driver/VE/__init__.py:108`，Cerence 同）：覆寫標準庫 `threading.Event.is_set`，守門讀不到標準庫，依規則 2 應進 `INTERFACE_NAMES`，不改名。分類正確。
- `_SegmentNative.espeak_Synth`／`espeak_ng_Cancel`（`driver/Espeak/__init__.py:27,39`）：是 ctypes 綁定的代理方法，名字和 DLL 匯出一致並轉呼叫 `self._native.<同名>`，應進 `INTERFACE_NAMES`（eSpeak NG DLL 匯出名），不改名。分類正確。
- 六個 wrapper 的 `SynthDriver.speak_segment`／`get_segment_drain_support` 與各 `_XxxPort` 的 hook：是核心介面的結構性實作，47b 改成明確繼承 Protocol 後守門就會自動豁免，不需要列表。但 `_EspeakPort.run_when_done`／`set_index_callback`／`mark_not_speaking`／`stop_player`（`driver/Espeak/__init__.py:70-81`）只在 Espeak wrapper 內部被呼叫，核心沒有同名介面（核心的 `NativeStrategy.stop_player(host)` 是另一個類別的 hook），這四個是 wrapper 自己的名字，47b 要真的改名。
- 47c：wrapper 的 `Voice` 覆寫目前只因 `driver.Voice` 定義了舊名才豁免，47c 改基底後漏改的 wrapper 會被守門抓到；`ref/Neural` 只用 `synth_driver_class`，本 phase 沒碰。

## 使用者還沒確認的使用者可見預設

本 phase 沒有使用者可見的行為、字串、設定或手勢變更，所以沒有這一類預設。以下是協調者或實作者採用、使用者沒有逐一確認的**開發面**預設：

1. 守門連區域變數一起檢查（帳本 Ruling；代價是 47b 清單多 42 條）。
2. 嚴格 `snake(old)` 產生的 `_set_voice_datas` 與 `get_text_info_speech_with_say_all_break`（M4）。
3. `test_no_module_imports_typing_override` 在最低版本升到 2026.1 時以 skip 自我停用（M3）。
4. 規則的正式家只有守門測試的 docstring，沒有在 tracked 的文件加指標（帳本 Ruling；`refactor9.md` 是 git 忽略的）。

## 未在本機驗證的部分

Linux 上只驗證了測試與受控的 stub；Windows 上的 NVDA、實際音訊裝置與引擎 SDK 都沒有驗證。本 phase 是純改名，沒有新的手動項目；未打包。
