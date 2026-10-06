# 階段 24：測試基礎設施——統一模組載入

日期：2026-10-06。
基準：`master`（`e153aec`，階段 25 合併完成）。分支：`phase24-test-infrastructure`。
狀態：使用者要求依序完成階段 23～28，自動流程執行。

對應 repo 根目錄 `refactor-test.md`（不入版控）的階段 24。

## 現況

- **以路徑載入模組**：`importlib.util.spec_from_file_location` → `module_from_spec` → `sys.modules[...] = module` → `exec_module` 這四步，在 30 個測試檔／harness 各寫一份（`runtime_harness.py` 3 份、`test_worldvoice_lifecycle.py`、`test_pipeline_log.py`、`test_f4_voice_state.py` 各 2 份，其餘各 1 份）。有的用 `monkeypatch.setitem` 登記、有的直接寫 `sys.modules`、有的先建別名 package。
- **測試模組互相 import**：26 個 `from test_x import ...`，主要是 `test_worldvoice_lifecycle`（6）、`test_pipeline_punctuation_pause`（3）、`test_worldvoice_request_builder`、`test_worldvoice_cancel_wrappers`、`test_vocalizer_segment_drain`、`test_runtime_composition`、`test_f4_voice_state`（各 2）。被 import 的是 helper、常數與 `composition` fixture；pytest 也會把這些模組當測試收集，helper 散在測試檔中不易找到。
- **`exec` 抽原始碼**：15 個檔以 `ast` 抽出 add-on 的類別或函式，在 stub 命名空間 `exec`。理由多為 UI 類別需要 wx、或主驅動需要整個 NVDA。`pyproject.toml` 對 `tests/**` 忽略 S102（階段 25）。
- **WorldVoice config stub**：各測試手寫 `{"WorldVoice": {"autoLanguageSwitching": {...}, ...}}`，常缺鍵；階段 22 就因 stub 少了 `KeepMainLocaleParameterConsistent` 改了兩個 harness。

## 範圍調整（相對路線圖）

路線圖原寫「`addon_module(name)` 自動解析依賴」。現有 harness 刻意把模組載入到**別名 package**（例如 `worldvoice_runtime_test`），讓每個測試拿到全新的模組物件、彼此隔離；通用的自動解析要處理別名、相對 import 與 NVDA stub 的組合，風險高、收益只是少寫幾行。本階段改為：一個載入函式＋一個 package 函式取代所有手寫副本，載入行為（名稱、別名、隔離）由呼叫端明確指定，與現況一致。

## 設計

### 1. `tests/addon_loader.py`

```python
ROOT, ADDON, WORLDVOICE  # 路徑常數

def load_source(monkeypatch, name, path, *, register=True):
	"""以 name 從 path 載入模組（測試結束時由 monkeypatch 移除登記）並回傳。"""

def alias_package(monkeypatch, name, path):
	"""登記一個 __path__ 指向 path 的空 package，讓 name.sub 以相對 import 載入。"""

def load_definitions(path, names, namespace):
	"""以 ast 從 path 抽出 names 指定的頂層類別／函式（或 Class.method），在 namespace 執行並回傳 namespace。"""
```

- 所有 `spec_from_file_location` 改用 `load_source`；手建 package 改用 `alias_package`。原本不經 monkeypatch、直接寫 `sys.modules` 的，若是刻意跨測試保留（例如 session 級），保留並註明；否則改為 monkeypatch 登記。
- 所有 `exec` 抽原始碼改用 `load_definitions`（若某檔抽取方式特殊，例如先改寫 AST 再執行，保留在該檔並註明）。能直接 import 的（不需 wx、不需整個 NVDA）改成 `load_source`。
- S102 的 per-file-ignores 由 `tests/**` 縮小為 `tests/addon_loader.py` 與保留特殊抽取的檔案。

### 2. 共用 helper 移出測試模組

- 被其他測試 import 的 helper、常數與 `composition` fixture，搬到對應的 harness 模組（沿用既有 harness，例如 `runtime_harness.py`、`worldvoice_cancel_wrapper_harness.py`；沒有合適的就新增，例如 `worldvoice_harness.py`）。`composition` 移入 `tests/conftest.py`，刪除 `test_plugin_voice_contract.py`、`test_pipeline_voice_lookup.py` 的 `noqa: F401/F811`。
- 守門：`tests/` 內沒有 `from test_` 或 `import test_`。

### 3. WorldVoice config stub 的預設值

- `nvda_stubs.py` 新增 `worldvoice_conf(**overrides)`：回傳含 add-on confspec 預設值的 `{"WorldVoice": {...}}`（`autoLanguageSwitching` 的五個偵測鍵與三個 `KeepMainLocale*` 旗標、`pipeline`、`engine`、`role`、`voices`、`log` 等，值取自 add-on 的 confspec 常數或 `__init__.py` 的 spec，不手抄）。
- 手寫且缺鍵的 WorldVoice config stub 改用它；刻意測「缺鍵」行為的測試保留手寫。

## 驗證

- 每個 commit：收集清單（node id）不變、全套通過、逐檔單獨執行全部通過、`ruff check/format` 乾淨。
- 守門：`spec_from_file_location` 只出現在 `tests/addon_loader.py`（與註明的例外）；沒有測試模組互相 import。

## 實作備註

- 7 個 commit（`9798f80`…`d27fbcc`）。`spec_from_file_location` 35 處 → 只在 `addon_loader.py`；`exec` 15 檔 → `addon_loader.load_definitions` 與 `pipeline_harness.load_synth`（需執行模組層的 `for _spec in PIPELINE_SETTINGS` 迴圈，`load_definitions` 選不到，已註明）；S102 只對這兩檔忽略；測試模組互相 import 30 行 → 0。
- `load_definitions` 增加 `members=`（只保留指定方法、去掉 bases／decorators），取代三個手寫 AST 改寫。
- `load_source(register=False)` 用於原本不登記 `sys.modules` 的 5 處。`test_core_archive` 原本用一個從未 undo 的 `pytest.MonkeyPatch()`（stub 洩漏到後續測試），改用測試自己的 monkeypatch。
- 搬到 harness 的 helper 改為公開名稱（去掉底線）；兩版 voice manager loader 分別命名為 `load_voice_manager`、`load_f4_voice_manager`。
- `worldvoice_conf` 以 ast 讀主驅動的 `config.conf.spec["WorldVoice"]`、`DETECTION_CONFSPEC`、`PIPELINE_SETTINGS`、pipeline `STAGES` 的 log key；validator 只解析 boolean／integer／string，未預期的寫法直接報錯；`__many__` 區段預設 `{}`。刻意測缺鍵或使用 Section 物件的測試保留手寫。
- 守門測試兩個（在 `test_hygiene_guards.py`），收集數 1492 → 1494。
