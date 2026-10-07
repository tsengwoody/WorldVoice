# 階段 29：性質測試與變異測試試跑

日期：2026-10-07。
基準：`master`（`f2b9d44`，階段 30 合併完成）。分支：`phase29-property-tests`。
狀態：使用者選擇「A 和 B 都做」（2026-10-07）：A 正式加入 Hypothesis 性質測試；B 在 scratchpad 副本試跑 mutmut（`runtime/completion.py`），結果先回報使用者再決定是否擴大。六家引擎共用契約測試不做。

## A. 性質測試

設定（`tests/conftest.py`）：profile `default`（每個測試 200 例、不設 deadline）每次執行；`deep`（2 萬例）以 `HYPOTHESIS_PROFILE=deep` 手動開啟。找到的反例存在 `.hypothesis/`（已 gitignore）並在之後每次重跑。

| 測試 | 性質 |
| --- | --- |
| `test_text_preprocessing.py::test_property_chunk_pieces_rebuild_the_text_within_the_limit` | 串接等於原文；沒有空段；escape 不被切開；沒有只含 escape 的段；純文字不超過上限（例外：單一字元加附屬字元）；斷開處的尾端 escape 移到下一段；切點不在附屬字元之前（除非緊鄰 escape） |
| `test_text_preprocessing.py::test_property_arabic_runs_only_gain_spaces` | escape 不變；只增加空白；不留下四個以上相同字母的連續；冪等 |
| `test_language_detector.py::test_property_detection_only_inserts_language_changes` | 文字串接不變、沒有空字串；輸入的命令原物件、原順序保留；新增的命令都是 `WVLangChangeCommand` |
| `test_index_codec.py::test_property_encoding_keeps_commands_and_reports_each_index_once_in_order` | 輸入不被修改；非 index 命令原物件保留；index 換成遞增、不重複、在範圍內的 wire index，結尾 marker 在最後；任一 wire index 回報到它為止的原始 index，marker 回報其餘並結束；同一段內重複的原始 index 只在首次出現處回報一次 |

`languageDetection/scripts.py::get_script` 的輸入空間由偵測器的性質測試以任意字元涵蓋，不另寫。

發現：codec 性質第一次執行就找到「同一段內重複的原始 index 只回報一次」。追查 `indexLedger._pending_indexes` 的 `segment.delivered` 集合，這是刻意去重；NVDA 的 SpeechManager 在同一段內不會產生重複 index，所以是設計而非 bug，性質依此描述。

成本：四個測試在 default profile 合計約 2.3 秒（全套 41 → 44 秒）；deep profile 約 4.5 分鐘，全部通過。

## B. mutmut

### 試跑（scratchpad 副本，`runtime/completion.py`）

第一次跑通後回報「13 個變異中 2 個存活」。但逐一驗證時發現：`tests/test_completion_rules.py` 把 completion 載入成 `worldvoice_runtime_test.completion`，名稱轉換只比對結尾 `runtime.completion` 而漏掉它，mutmut 因此沒有為這兩個變異選到這支測試。名稱改為依函式的原始碼檔案路徑推得後，**13 個全部被殺死**。教訓：在這個專案，mutmut 的「存活」必須以「該變異啟用時跑整套仍通過」再確認。

### 正式設定（使用者選擇「三項都做」）

- `pyproject.toml` 的 `[tool.mutmut]`：四個核心模組（`runtime/completion.py`、`indexLedger.py`、`configRepository.py`、`mainLocalePolicy.py`）、只變異有被跑到的行、複製 `addon/` 與兩個設定檔、排除 `tests/test_hygiene_guards.py`（它 lint 與掃描原始碼，對 mutmut 改寫過的副本判斷的是改寫而非行為）。執行：`mutmut run`（Linux／WSL），`mutmut results`、`mutmut show <名稱>`。
- `tests/mutation_support.py`（`tests/conftest.py` 只在 mutmut 的 `mutants/` 副本中啟用）：mutmut 以檔案路徑推得的模組名稱對應變異、以函式的 `__module__` 記錄哪些測試跑到哪個函式；測試以別名 package 載入 add-on，兩者對不上時 mutmut 不會為變異選測試而誤判存活。做法：裝飾時把被包裝函式的 `__module__` 改為檔案路徑名稱，並記下「別名 → 檔案路徑名稱」，統計階段記錄命中時換成檔案路徑名稱。最初另包一層函式的做法會改變 `indexLedger` 的行為（一個 composition 測試在副本中穩定失敗），已改為不包裝。
- `tests/addon_loader.REF`：測試讀 `ref/`（NVDA、Neural 原始碼，3.9 GB）的路徑集中於此；在 `mutants/` 副本中指向原 repo 的 `ref/`，不必複製。

### 結果（四個模組）

369 個變異：331 殺死、38 存活、0 逾時；約 4.8 分鐘；最低可用記憶體 8.4 GB。38 個存活逐一以「啟用該變異跑整套」確認都是真的存活，分類：

| 類別 | 數量 | 處理 |
| --- | --- | --- |
| 例外訊息字串（`None`、大小寫、加字） | 28 | 不補：測試檢查例外型別，訊息只給開發者看 |
| 等價變異：`_closed = None`（同為 falsy）、`.get(name, )`（預設即 None）、`cursor = None`（`delivered` 集合去重，結果相同）、`close` 中 `binding = ""`（close 後 bind 先因 closed 拋出）、`bind` 的 `or`→`and`（`CompletionContract` 已禁止可區分的組合）、`_Binding(None, …)` | 6 | 不補。`_Binding.source_id` 欄位從未被讀取，是死欄位，記錄於此 |
| **真正缺口**：`receive_index` 在結尾 marker 設定的 `segment.finished`（4 個變異） | 4 | 補 `test_a_failure_after_the_end_index_is_ignored`、`test_a_failure_after_drain_and_end_is_ignored`：segment 完成後遲到的 `SEGMENT_FAILED` 必須被忽略，否則已念完的語音可能被回報為失敗。兩個測試殺死全部 4 個變異 |

`runtime/completion.py` 與 `mainLocalePolicy.py` 的變異全部被殺死。
