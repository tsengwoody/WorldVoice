# Phase 44 Review：設定基礎設施一致化（F9 `conf_provider`＋F5 共用 `listeners.py`）

日期：2026-10-27。分支：`phase44-settings-infra`（`10a1b30..e8c205f`，6 個 commit：2 個 docs、4 個程式；基準 `master` `10a1b30`，3336 passed／0 skipped）。
審閱者：Fable 5.1（唯讀；只新增本檔）。流程：一般流程（DEVELOPMENT_WORKFLOW.md §3.3）；5 個 task 少於 10，沒有批次 review，本次是第一次也是唯一一次 review，看整個分支。不是大範圍改名或搬移，§3.2 的 token／搬移比對不適用。

依據：

- 規則來源 `storage/refactor9.md` §4.1 F5、§4.5 F9、§6 的 P44 列、§6.1 命名規則。
- spec `docs/superpowers/specs/2026-10-27-phase44-settings-infra-design.md`。
- plan `docs/superpowers/plans/2026-10-27-phase44-settings-infra.md`（Review Focus 1–5）。
- 進度帳本 `.superpowers/sdd/2026-10-27-phase44-settings-infra/progress.md`（git 忽略；1 個 `Ruling:`）。
- NVDA 原始碼 `ref/nvda/source/logHandler.py`（`Logger._log`、`getCodePath`）、`config/__init__.py`。

使用者已決定、本次只核對實作的事項：F9 方向是 `conf_provider`，主驅動傳 `lambda: config.conf`；F5 是根目錄的 NVDA-free 模組，logger 用注入的、`ParamSpec` 泛型、兩句 log 訊息逐字不變；最低 Python 3.11（不用 `typing.override`、PEP 695 語法、`type` 敘述）。**實作全部符合**。

## 結論

**Ready to merge：Yes。** Critical 0、Important 0、Minor 3。

- **行為與 master 逐項相同。** `Listeners.subscribe` 以 `not in`（`==`）去重、`unsubscribe` 吞 `ValueError`、`notify` 先 `tuple()` 複製再迭代、只接 `Exception`、`logger.error(<訊息>, exc_info=True)`——和 master 兩個 service 各自手寫的版本（`pipeline/settings.py:440-455`、`languageDetection/settings.py:89-104`，舊行號）逐行同形；兩個 service 把 `log` 物件原樣傳入，所以仍是 `logHandler.log.error`。通知仍在 `update()` 內同步執行，呼叫端（`__init__.py:524` 的 descriptor、`ui/voicePanel.py:202,225`）沒動，執行緒不變。`DetectionSettingsService.update` 以前每個 listener 各建一個 `frozenset(changed)`，現在只建一個——frozenset 不可變，無差。
- **F9 的讀取時機和 master 一樣新鮮或更好。** master 每次 `load`／`save` 都走 `self._conf["WorldVoice"]["voices"]`，NVDA 的 `config.conf` 是同一個 `ConfigManager`，profile 切換在 `__getitem__` 時解析，所以 master 本來就不會讀到舊 profile；分支把物件換成 provider，每次 `load`／`save` 經 `_voices()` 呼叫 provider（`voices/settingsRepository.py:30-31`），若 `config.conf` 整個被換掉（測試或將來）也跟得上。`__init__.py:211` 的 `lambda: config.conf` 閉包抓的是模組層的 `config` 名稱，生命週期測試用注入的 `config` 物件證明換掉 `config.conf` 後 provider 跟著變。
- **`listeners.py` 符合 §6.1。** 只 import `logging`、`collections.abc`、`typing`；名字全是 snake_case（`failure_message`、`_logger`）；`P` 是常數；`tests/test_naming_layers.py:61` 把它列在 `CORE`（根模組群組之首，位置合理），守門測試 `test_every_add_on_module_has_a_layer` 與 `test_naming_follows_layer` 各自抓得到漏列與 camelCase（突變 m12、m13）。
- **Python 3.11 相容。** 分支 diff 裡沒有 `typing.override`、PEP 695 `class X[T]`、`type` 敘述、`itertools.batched`；用到的 `ParamSpec`、`Generic[P]`、`collections.abc.Callable[P, None]`、`sys.stdlib_module_names`（測試）都是 3.10 起就有。容器只有 3.14，無法實際以 3.11 執行；依語法與標準庫文件判斷相容。
- **測試真的抓得到。** 18＋5 次突變（詳見下表）全部被對應的測試抓到；plan Review Focus 1–5 逐項核對（見下）。帳本提到 stale bytecode 曾讓一次突變假存活，審閱者全程 `PYTHONDONTWRITEBYTECODE=1`、`-p no:cacheprovider`、每次清 `__pycache__`。
- **`Ruling`（淨 +29 行）評估：合理，數字正確。** `git diff --numstat master -- addon`：59 added／30 deleted；F9 +3（`_voices()` helper，與其他 repository 的 `_section()` 同形），F5 +26（`listeners.py` +37；pipeline −7；detection −4）。refactor9 估的「淨省 5–10 行」沒算 forwarder（每個 service 6 行含空行）和新模組的 docstring／完整註記。能再省行的形狀都要犧牲 spec §3 的訂閱介面或把 `notify` 公開，見下方「可省行的選項」；審閱者同意維持現狀，行數不是缺陷。
- 完整測試 3346 passed、0 skipped（基準 3336 + 8 個 `test_listeners.py` + 1 repository + 1 lifecycle）；`prek run --all-files` 8 個 hook 全部 Passed；`git diff --check master` 乾淨；受保護路徑無 diff、Neural 未被 track；6 個 commit 沒有 `Co-Authored-By`，沒碰 `ref`；沒有可翻譯字串、readme、changelog 或儲存鍵變動（符合 spec §3）。

### 可省行的選項（供使用者決定，審閱者建議維持現狀）

| 選項 | 省多少 | 代價 |
| --- | --- | --- |
| A. service 繼承 `Listeners[[…]]`，`__init__` 改 `super().__init__(log, "…")` | 約 −10（兩個 service 各去掉 forwarder 6 行、加 1 行 super） | `notify` 變成 service 的公開方法（任何人可在沒改設定時觸發 listener）；`_listeners`／`_logger`／`_failure_message` 進入 service 的命名空間；「service 是一個 listener 清單」的 is-a 關係不對。spec §5.2 已否決。 |
| B. 公開 `service.listeners`，呼叫端改 `service.listeners.subscribe(...)` | 約 −10 | 改 5 處產品呼叫（`pipeline/scope.py:26`、`__init__.py:253,256,278,281`）和約 20 處測試；`notify` 仍可經 `service.listeners.notify` 觸發；違反 spec §3「不改誰訂閱」。 |
| C. `__init__` 裡 `self.subscribe = self._listeners.subscribe`（實例屬性） | 約 −8 | 類別上看不到 `subscribe` 的簽名，型別檢查與讀者都吃虧；專案沒有這種寫法的先例。 |
| D. detection 的 `Listeners[[DetectionSettings, frozenset[str]]](...)` 用 PEP 612 簡寫 `Listeners[DetectionSettings, frozenset[str]]` | 0 | 審閱者實測簡寫可用，但單行寬度 125 仍超過 ruff 的 110，照樣換成四行；沒有收益。 |

## Critical

無。

## Important

無。

## Minor

### M1. NVDA log 行的 codepath 前綴從 service 變成 `listeners.Listeners.notify`

- 位置：`addon/synthDrivers/WorldVoice/listeners.py:37`；NVDA `ref/nvda/source/logHandler.py:266-271`（`codepath = getCodePath(f)`，取呼叫 `log.error` 的那一個 frame）。
- 內容：訊息本文 `"WorldVoice: pipeline settings listener failed"`／`"… detection settings listener failed"` 逐字不變，但 NVDA log 每行開頭的 codepath（例如 `ERROR - synthDrivers.WorldVoice.pipeline.settings.PipelineSettingsService.update (hh:mm:ss.sss)`）現在會寫成 `…listeners.Listeners.notify`；兩個 service 的失敗都顯示同一個 codepath，要靠訊息本文分辨。
- 失敗情境：無功能影響；只有看 NVDA log 的人會注意到。任何共用實作都會這樣，除非傳 NVDA 專有的 `codepath=` 參數（違反 NVDA-free）。
- 建議：不修；列為使用者還沒確認的預設（下方第 4 點）。

### M2. 兩個 service 層的隔離測試只釘訊息文字，沒釘 `exc_info=True`

- 位置：`tests/pipeline_harness.py:275`、`tests/test_detection_settings.py:38`（`error=lambda *args, **kwargs: errors.append(args)` 只記 `args`）；`tests/test_pipeline_settings_service.py:366`、`tests/test_detection_settings.py:158`。
- 內容：突變 m4b（`listeners.py` 拿掉 `exc_info=True`）在這兩個測試下存活（2 passed），只有 `tests/test_listeners.py::test_listeners_isolate_a_failing_listener` 抓到。spec §2.4 把「仍以 `exc_info=True` 記錄」列為目標，而 §7 只要求 service 測試比對訊息文字，所以實作符合 spec；`exc_info` 由單元測試釘住，service 不再自己呼叫 `log.error`，重複釘住的價值低。
- 失敗情境：將來若有人在 service 裡改回自己呼叫 `log.error(msg)` 而漏掉 `exc_info`，這兩個測試不會發現。目前沒有這種路徑。
- 建議：可不修。要修的話把兩個 stub 改成 `errors.append((args, kwargs))`，斷言改成 `[(("…",), {"exc_info": True})] * 2`，約 4 行。

### M3. `DetectionListener` 別名與 `Listeners[[DetectionSettings, frozenset[str]]]` 把同一個簽名寫了兩次

- 位置：`addon/synthDrivers/WorldVoice/languageDetection/settings.py:38` 與 `:49`。
- 內容：`DetectionListener = Callable[[DetectionSettings, frozenset[str]], None]` 用在 `subscribe`／`unsubscribe` 的參數型別，`Listeners[[…]]` 的參數列表是同一組型別，但 `ParamSpec` 無法從 `Callable` 別名推回，所以只能各寫一次。pipeline 側沒有別名，`subscribe` 直接寫 `Callable[[PipelineSettings], None]`，兩個 service 的寫法不一致。
- 失敗情境：無；只是將來改簽名要改兩處，型別檢查器會抓到不一致。
- 建議：可不修。若要一致，pipeline 側也加 `PipelineListener` 別名（+1 行），或兩側都不用別名。

## 審閱者自行驗證的項目

所有測試都在任務 worktree `/workspace/WorldVoice-phase44`（`ref` 為 symlink）或審閱者自己建的 detached 暫時 worktree（`scratchpad/review44/mut`，另建 `ref` symlink，用完已移除）執行，序列跑，附 3 GB `MemAvailable` 看門狗（從未觸發；開跑時 MemAvailable 5.7 GB）；沒有碰主 checkout，沒有用 `git stash`，沒有修改任何原始碼。

| 項目 | 指令 | 結果 |
| --- | --- | --- |
| 完整測試（分支頭 `e8c205f`） | `scratchpad/review44/guarded.sh /workspace/WorldVoice-phase44 … tests`（`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests`，序列，看門狗；先清 `__pycache__`） | 3346 passed、0 skipped（151.49 s）；看門狗 0 次觸發 |
| hook | `prek run --all-files`（worktree） | 8 個 hook 全部 Passed；之後 `git status --short` 乾淨 |
| 空白與受保護路徑 | `git diff --check master`；`git diff --stat master -- '…/driver/*/driver/' …/sonic/ …/script_data.py …/unspaced_common_data.py`；`git ls-files …/driver/Neural` | 三者皆無輸出 |
| commit 衛生 | `git log master..HEAD --format='%b' \| grep -ic co-authored`；`git log master..HEAD --name-only --format= \| grep ^ref`；每個 commit 的 subject 與 body | 0；無；6 個都是英文 `<type>: <summary>` 加說明原因的內文 |
| Python 3.11 相容 | `git diff master -U0 -- addon tests \| grep -E 'typing\.override\|\boverride\b\|^\+\s*type\s+\w+\s*=\|^\+\s*class\s+\w+\['` | 無；`python3 --version` 3.14.4（無 3.11 可實跑） |
| `listeners.py` 的 import | 讀 `listeners.py:6-8`；`test_listeners_import_only_the_standard_library`；突變 m7 | 只有 `logging`、`collections.abc`、`typing`；加 `from logHandler import log` 後測試失敗 |
| 行為比對 | 逐行讀 `git diff master -- addon`，對照 master 的 `pipeline/settings.py:440-455`、`languageDetection/settings.py:89-104` | 去重、未知 listener、tuple 複製、`except Exception`、`exc_info=True`、`log` 物件、通知順序與執行緒皆相同（見「結論」第 1 點） |
| F9 讀取時機 | 讀 `voices/settingsRepository.py:27-50`、`__init__.py:211`、NVDA `config/__init__.py`；突變 m10、m11 | 每次 `load`／`save` 呼叫 provider；eager 讀取或傳物件都被對應測試抓到 |
| 直接碰 `_listeners` 的測試 | `grep -rn '\._listeners' tests addon`（排除三個擁有者） | 0 筆；`addon/` 內只有 `listeners.py` 與兩個 service 的欄位 |
| 載入 settings 模組的 harness | 全套測試 + `grep -rln 'pipeline/settings.py\|languageDetection/settings.py' tests`（24 個檔案） | 全部通過；`pipeline_harness.load_settings_module`、`ui_harness._pipeline_ui`、`test_detection_settings.load_settings_module` 都先載 `listeners.py` 進別名套件 |
| 行數 Ruling | `git diff --numstat master -- addon` | `__init__.py` 1/1、`languageDetection/settings.py` 8/12、`listeners.py` 37/0、`pipeline/settings.py` 5/12、`voices/settingsRepository.py` 8/5 → +29，和帳本一致 |
| PEP 612 簡寫與單行寬度 | `python3` 實測 `Listeners[int, frozenset[str]]` 與 `Listeners[[int, frozenset[str]]]`；計算 detection 單行寬度 | 兩種寫法 `__orig_class__` 相同；單行 125 字元 > `line-length = 110`（`pyproject.toml:79`） |
| NVDA log codepath | 讀 `ref/nvda/source/logHandler.py:237-291,466-473` | `codepath` 預設取呼叫 `log.error` 的 frame（M1） |
| 突變測試（18 + 5 次，暫時 worktree） | `python3 scratchpad/review44/mutate.py` → `mutate_results.txt`；另 5 次針對 service 層測試 | 見下表；每次 `git checkout --` 還原後 `git status --short` 乾淨 |

### 突變測試

每次只改一處、清 `__pycache__`、`PYTHONDONTWRITEBYTECODE=1`、`-p no:cacheprovider`、跑目標測試檔（m1–m18 加 `-x`，所以列的是第一個失敗）、還原。

| # | 還原的東西 | 抓到的測試 |
| --- | --- | --- |
| m1 | `Listeners.notify` 拿掉 `try/except` | `test_listeners.py::test_listeners_isolate_a_failing_listener`；m1b 不加 `-x` 只跑 service 層：pipeline 與 detection 的隔離測試都失敗（`RuntimeError: listener failed`） |
| m2 | `notify` 不複製 tuple、直接迭代清單 | `test_a_listener_may_unsubscribe_while_told` |
| m3 | `except Exception` → `except BaseException` | `test_a_base_exception_is_not_swallowed` |
| m4 | 拿掉 `exc_info=True` | `test_listeners_isolate_a_failing_listener`；m4b 只跑 service 層：**2 passed（存活）**，見 M2 |
| m5 | `subscribe` 不去重 | `test_listeners_tell_each_listener_once_in_subscription_order`；m5b service 層兩個隔離測試也失敗 |
| m6 | `unsubscribe` 讓 `ValueError` 傳出 | `test_unsubscribing_an_unknown_listener_is_ignored` |
| m7 | `listeners.py` 加 `from logHandler import log` | `test_listeners_import_only_the_standard_library` |
| m8 | pipeline 訊息 `failed` → `faileD` | `test_pipeline_settings_service.py::test_update_notifies_subscribers_and_survives_a_failing_one` |
| m9 | detection 訊息 `failed` → `faileD` | `test_detection_settings.py::test_a_failing_listener_is_logged_and_the_others_still_run` |
| m10 | repository 在 `__init__` 呼叫一次 provider 並抓住結果 | `test_repository_reads_the_conf_its_provider_returns_at_each_call` |
| m11 | `__init__.py:211` 改回傳 `config.conf` | `test_worldvoice_lifecycle.py::test_the_driver_gives_the_voice_settings_repository_a_conf_provider` |
| m12 | 守門 `CORE` 拿掉 `"listeners.py"` | `test_naming_layers.py::test_every_add_on_module_has_a_layer` |
| m13 | `failure_message` 參數改 `failureMessage` | `test_naming_layers.py::test_naming_follows_layer` |
| m14 | pipeline `update` 通知後 `return current` | `test_update_converts_normalizes_and_writes_every_passed_key`（`-x` 先遇到）；m14b 單跑隔離測試也失敗（Review Focus 5） |
| m15 | detection `update` 通知後 `return current` | `test_update_writes_only_the_given_changed_keys`；m15b 單跑隔離測試也失敗（Review Focus 5） |
| m16 | `notify` 不傳 `**kwargs` | `test_notify_passes_positional_and_keyword_arguments` |
| m17 | pipeline `update` 完全不通知 | `test_update_notifies_subscribers_and_survives_a_failing_one` |
| m18 | detection 通知 `frozenset()` 而不是 `changed` | `test_update_writes_the_cyrillic_and_devanagari_keys[…]`（`seen` 比對 `changed`） |

### Review Focus 逐項

| # | 項目 | 核對 |
| --- | --- | --- |
| 1 | 兩次訂閱同一個 bound method、再用新的 bound method 退訂 | `subscribe` 用 `not in`、`unsubscribe` 用 `list.remove`，兩者都走 `==`，bound method 比 `__self__` 與 `__func__`；`test_a_bound_method_is_matched_by_equality` 釘住，m5 證明去重被動到會失敗。和 master 的寫法完全相同 |
| 2 | listener 在被通知時退訂自己或別人 | `notify` 先 `tuple()` 複製（`listeners.py:33`）；`test_a_listener_may_unsubscribe_while_told` 釘住本輪不受影響、下一輪略過；m2 抓到 |
| 3 | `KeyboardInterrupt` 必須傳到 NVDA | `except Exception`（`listeners.py:36`）；`test_a_base_exception_is_not_swallowed` 釘住且 logger 沒被呼叫；m3 抓到 |
| 4 | profile 切換或 `config.conf` 被換掉 | provider 每次 `load`／`save` 呼叫（`settingsRepository.py:30-31`）；repository 測試換掉 provider 回傳值、lifecycle 測試換掉 `config.conf`；m10、m11 抓到。另核對 master 本來就經 `ConfigManager.__getitem__` 解析 profile，不是回歸修正而是形狀一致化 |
| 5 | 失敗的 listener 不能讓更新丟失 | 兩個隔離測試新增 `update(...)` 回傳值與寫入值的斷言；m14b、m15b 證明回傳舊值會被抓到；`save`／`section[key] = value` 在 `notify` 之前，listener 例外不影響寫入 |

## Ruling 評估

| Ruling | 評估 |
| --- | --- |
| Task 5：產品碼淨 +29 行（59／30），而不是 refactor9 估的淨省 5–10 行、也超過 spec 估的 +10～+15；原因是 forwarder、ruff 把 detection 的建構式換成四行、新模組的 docstring 與完整 `ParamSpec` 註記；不採繼承（會公開 `notify`）或 `service.listeners.subscribe`（改 5 處呼叫、約 20 處測試） | **合理。** 數字審閱者重算一致（見驗證表）；三個原因各自核實（forwarder 每個 service 6 行；單行 125 > 110 連 PEP 612 簡寫都救不了；`listeners.py` 37 行中 docstring／註解／空行 13 行）。能省行的形狀（上方選項 A–D）都要犧牲 spec §3 的訂閱介面、把 `notify` 公開、或沒有收益；refactor9 F5 寫明主要收益是「隔離失敗 listener 的做法只有一份」，m1／m5 證明這一份被兩個 service 共用。帳本寫的「代價若錯：約 10 行 forwarder，之後可無行為變更地移除」也正確。 |
| Task 3／4 註記：強化後的隔離測試在改動前就通過，紅燈證據是突變 | 正確；plan Step 2 就這樣寫。審閱者的 m8／m9／m1b／m5b／m14b／m15b 重現並擴充了帳本的突變。 |
| Task 3 註記：`pipeline_harness`／`ui_harness` 顯式載入 `listeners.py` 進別名套件 | 合理；與既有 `numberLanguage.py` 的載法同形，全套 3346 通過。 |
| Task 4 註記：stale bytecode 曾讓同秒同大小的 sed 假存活 | 正確的教訓；審閱者全程停用 bytecode 並清快取，18＋5 次突變沒有一次假存活。 |

## 使用者還沒確認的使用者可見預設

協調者採建議預設、使用者可在 merge 前推翻的事項（spec §5.1、§5.2、§5.3、§8）；都不影響 NVDA 使用者看到的介面或設定：

1. **呼叫端傳完整的 log 訊息**（`Listeners(log, "WorldVoice: pipeline settings listener failed")`），不是片段組 f-string。審閱者同意：訊息留在擁有它的 service 裡可直接 grep，「逐字不變」能用測試釘住（m8、m9）。
2. **service 包含 `Listeners` 並保留兩行 forwarder，不繼承、不公開 `.listeners`**。審閱者同意，理由見「可省行的選項」。
3. **`ConfigVoiceSettingsRepository` 沒有預設 provider**。審閱者同意：`voices/settingsRepository.py` 刻意不 import `config`（`test_repository_load_and_save_need_no_nvda_or_engine_imports` 守住）。順帶一提 add-on 內的現況並不一致——`ConfigPipelineRepository`（`pipeline/settings.py:387`）與 `PipelineLogService`（`globalPlugins/WorldVoice/pipelineLog.py:17`）有預設 `lambda: config.conf`，`ConfigRoleRepository`、`DetectionSettingsService`、`mainLocalePolicy` 的三個類別沒有；這不在 P44 範圍，只記錄。
4. **NVDA log 的 codepath 前綴變成 `listeners.Listeners.notify`**（M1）；訊息本文不變。
5. `listeners.py` 的 logger 型別註記是 `logging.Logger`（NVDA 的 `logHandler.Logger` 是它的子類），沒有預設 logger。

## 未在 Linux 驗證的項目

- NVDA 本身、Windows、實際音訊裝置、引擎 SDK 都沒有載入；Python 3.11 沒有實跑（容器只有 3.14），相容性依語法與標準庫文件判斷。本 phase 沒有使用者可見的行為變更，不需要打包；未打包、未在 Windows 驗證。

## 修正記錄

- **M1 不修**：共用實作的必然結果；NVDA-free 模組無法傳 NVDA 的 `codepath=`。log 文字不變，列為未確認的預設。
- **M2 不修**：`exc_info=True` 已由 `test_listeners_isolate_a_failing_listener` 釘住（m4b 在單元層會被抓到）；要在服務層也釘住，得改兩個共用 log stub 的記錄格式，牽動其他比對 `errors` 內容的測試，代價大於收益。
- **M3 不修**：`DetectionListener` 別名在 master 就已存在，本 phase 只是沿用；pipeline 端原本就沒有別名。兩邊寫法統一可留待之後順手整理。
