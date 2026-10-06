# 階段 25：測試程式的 lint 與格式

日期：2026-10-06。
基準：`master`（`f7bb32b`，階段 23 合併完成）。分支：`phase25-test-lint`。
狀態：使用者已同意一次性全檔格式化（2026-10-06），自動流程執行。

對應 repo 根目錄 `refactor-test.md`（不入版控）的階段 25。

## 現況

- `.pre-commit-config.yaml` 的格式化與 lint hook 都以 `files: ^addon/` 限定，註解寫明「tests keep their own style」。`tests/test_hygiene_guards.py::test_ruff_reports_nothing` 只檢查 `addon`。
- `tests/` 縮排混用：59 檔 tab、34 檔 4 空格（專案規範為 tab，`pyproject.toml` 的 `[tool.ruff.format] indent-style = "tab"`）。
- `ruff check tests`（同一份 pyproject 規則）361 項：F811 156、I001 71、RUF059 41、F401 40、BLE001 16、S102 15、F841 5、RUF012 3、SIM117 3、B023 2、C408 2、PIE807 2、其他各 1。
- F811 與大部分 F401 來自同一個寫法：pytest fixture 以 `from runtime_harness import rt` 這類 import 共用，再當成測試參數名稱。F401 的自動修正會刪掉這些 import，使測試找不到 fixture。共用的 fixture：`rt`（`runtime_harness.py`）、`compat`（`test_runtime_legacy_adapter.py`）、`nvda_commands`（`test_worldvoice_index_command.py`）、`module`／`snap`（`test_f4_engine_session.py`）。

## 設計

### 1. 共用 fixture 由 `tests/conftest.py` 提供

- 把上述 fixture 的定義搬進 `tests/conftest.py`（pytest 的標準共用方式），它們依賴的 helper 由 conftest import。各測試檔刪除這些 fixture 的 import。
- `test_f4_engine_session.py` 的 `module` 名稱太泛，搬到 conftest 時改名為 `session_module`，並更新使用處。
- 測試檔自己定義同名 fixture 的，維持 pytest 的「近者優先」，不改。
- 測試模組彼此 import 一般函式（`from test_x import helper`，41 處）不在本階段處理（階段 24）。

### 2. 一次性格式化

- 依 pre-commit 的順序：`add-trailing-comma`，再 `ruff format`，套用到 `tests/` 全部檔案。單獨一個 commit，不夾帶其他修改。
- 驗證：收集清單（node id）與格式化前完全相同，全套通過。

### 3. 清除 lint

- 安全的自動修正（F401 非 fixture 部分、I001、SIM117、PIE807、C408…），每類修完跑全套；import 排序可能改變有副作用的 import 順序（例如修改 `sys.path` 或 stub 模組的 import），出問題時以註解說明並維持原順序。
- RUF059：未使用的解包變數改 `_` 前綴。
- BLE001：測試執行緒以 `except Exception` 收集錯誤、交回主執行緒斷言的寫法，加上 `# noqa: BLE001 - <錯誤去哪裡>`，與 addon 的慣例一致。
- S102（`exec`）：以 per-file-ignores 對 `tests/**` 忽略，註明理由（測試以 AST 抽出 addon 原始碼載入；階段 24 會把能改的改成真的 import）。
- 其他（F841、RUF012、B023、B018、PLR0402、PLW1510、UP031）逐一修正。

### 4. hook 與守門擴及 `tests/`

- `.pre-commit-config.yaml`：trailing-whitespace、end-of-file-fixer、add-trailing-comma、ruff lint、ruff format 的 `files` 由 `^addon/` 改為 `^(addon|tests)/`；更新「tests keep their own style」註解。
- `tests/test_hygiene_guards.py::test_ruff_reports_nothing` 檢查 `addon` 與 `tests`。

## 驗證

- 每個 commit：收集數 1491、全套通過。
- `ruff check addon tests`、`ruff format --check addon tests` 皆 0 項；prek hook 通過。

## 實作備註

- 四個 commit：fixture 移入 conftest（`fe58854`）、格式化（`0b8b696`）、清 lint（`71bb2f1`）、hook 與守門（`cd31cc0`）。
- 格式化：add-trailing-comma 與 ruff format 交替兩輪才穩定；逐檔 AST 比對，只有 `runtime_harness.py` 一個 docstring 續行的縮排改變。
- fixture 移入 conftest 後 F811 的 156 項全部消失。`composition` fixture 依賴其他測試模組的 helper，未移入（階段 24），其 `noqa: F401/F811` 保留。
- BLE001 共 16 處加上寫明錯誤去處的 noqa。`test_sapi5_segment_drain.py::test_stop_failure_after_an_invalidated_feed_latches` 原本收集 callback 執行緒錯誤卻沒有檢查，補上斷言（連跑 30 次穩定）。
- `tests/conftest.py` 的 IndexCommand stub 保留 `noqa: TRY004`（與 NVDA 相同，拋 ValueError）。
- I001 自動排序後沒有任何 import 順序例外（全套與逐檔單獨執行皆通過）。
