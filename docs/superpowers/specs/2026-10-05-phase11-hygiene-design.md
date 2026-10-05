# 階段 11：衛生

日期：2026-10-05。
基準：`master`（`db32047`，階段 9 完成）。分支：`phase11-hygiene`。
狀態：使用者要求先跳過階段 10、直接做 11；依使用者要求自動執行（spec → plan → 實作 → Fable review）。

本文件是 [`refactor.md`](../../../refactor.md) §9 的階段 11，對應 §8（工程衛生）。

## 需求與範圍

1. **讓 ruff 認得 NVDA 的 logger。**
   - 在 `pyproject.toml` 加入 `[tool.ruff.lint] logger-objects = ["logHandler.log"]`。這與 `ref/nvda/pyproject.toml` 相同；專案以 `ref/nvda` 為格式準則。
   - 加入後，以 `log.exception(...)`／`log.error(..., exc_info=True)` 記錄的 `except Exception` 不再被 BLE001 標記：78 處降到 45 處。
2. **剩下 45 處 BLE001 逐處加註理由。**
   - 審查結果：這 45 處都是有意的邊界。它們包住的是 native、COM、player、使用者設定或外掛呼叫，可能拋出的例外類型無法事先窮舉；而且例外都沒有被吞掉，而是：
     - 記到 record，讓該段落失敗；
     - 鎖定為控制錯誤；
     - 收集起來，在其餘清理完成後重新拋出；
     - 轉成明確的回傳值（例如 drain 不支援、admission 錯誤、退回預設值）。
   - 因此不縮小例外類型，以免讓原本被處理的錯誤逃出邊界，改變行為。
   - 每一處改為 `except Exception ...:  # noqa: BLE001 - <理由>`，理由說明錯誤去了哪裡。
   - 唯一沒有處理錯誤的是 `pipeline.with_order_log` 的 `except Exception: pass`。它是使用者決定保留的 DEBUG 計數工具，同樣加註。
3. **I001：`ruff check --select I001 --fix --unsafe-fixes` 一次整理 import 順序。**
   - 排除內層驅動與 `driver/sonic`；29 處。
   - ruff 只在連續的 import 區塊內排序，不會把 import 移過 `sys.path.insert` 這類敘述，主驅動的 `generics` 匯入仍在 path 設定之後。
   - 整理後跑完整測試，並人工檢查每個有變動的檔案沒有移動到有副作用的 import。
4. **測試的 NVDA stub 集中。**
   - 新增 `tests/nvda_stubs.py`，提供 `StubModules(monkeypatch)`：
     - `.module(name, **attrs)`：建立並註冊到 `sys.modules`；
     - `.package(name, path, **attrs)`：同上，另設 `__path__`；
     - `.translation()`：安裝 builtins 的 `_`。
   - `tests/conftest.py` 新增 fixture `stub_modules`。
   - 以下 6 個檔案的本地 `module`／`package`／`stub` 輔助函式內容相同，改用它：
     - `espeak_drain_harness.py`、`rhvoice_drain_harness.py`、`onecore_drain_harness.py`；
     - `test_sapi5_segment_drain.py`、`worldvoice_cancel_wrapper_harness.py`、`test_runtime_composition.py`。
   - 本系列新增、手寫 `ModuleType` 並 `setitem` 的檔案也改用它：`test_pipeline_settings_service.py`、`test_pipeline_log.py`、`test_core_archive.py`、`test_pipeline_punctuation_pause.py`。
   - 守門測試：`tests/` 中不再有本地定義的 `def module(name`／`def package(name`／`def stub(name` 輔助函式。

### 決定

- **`voiceManager` 的命名統一延到階段 10。**
  - snake_case（`resolve_playback`、`playback_ports`、`roles`）與 camelCase（`getVoiceInstance`、`defaultVoiceName`）目前混用。
  - 階段 10 要把 `VoiceManager` 拆成 `EngineRegistry`／`VoiceCatalog`，屆時整個介面會重新定義。現在改名會讓 UI、主驅動、測試改兩次。
- 其他 ruff 規則（UP031、RUF012、G201 等）不在 §9 的階段 11 範圍內，不處理。

### 成功條件

1. 完整測試全部通過；`ruff format --check addon` 通過。
2. `ruff check addon --exclude ... --select BLE001,I001`（範圍同 refactor.md 附錄）為 0；`--select F401,F821` 仍為 0。
3. 每個 `# noqa: BLE001` 都附帶 ` - ` 開頭的理由（守門測試）。
4. 測試輔助函式集中的守門測試通過。
5. `driver/<Engine>/driver/`、`driver/sonic` 無變動。

### 不在範圍內

- 階段 10 的全部內容，包括 `voiceManager` 命名；
- 其他 ruff 規則；
- 先前子階段延後的 minor。

## 理由分類（BLE001）

| handler 的處理 | 註解文字 |
| --- | --- |
| `host.record_error(...)` | `recorded on the record; the segment fails` |
| `latch_control_error` 或 `_failSegmentControl` | `latched: the player or engine state is unknown` |
| `_latch_fault` | `latched as a lifecycle fault` |
| `_terminationError =` | `kept and raised once termination finishes` |
| `first_error` | `collected; the first is raised after every step ran` |
| `error = exc` | `kept and raised after the remaining cleanup` |
| `return unsupported(...)` | `any failure means drain is unsupported` |
| `return error`（SAPI5 admission） | `returned as the admission error` |

其餘 10 處逐一撰寫：
- `coreArchive` 的 extract：in-use files raise OS-specific errors; they are skipped and reported
- 設定面板的選項索引：a missing or invalid stored value selects the first option
- `configRepository`：an invalid main-synth value falls back to the voice's own
- Cerence `variants`：missing speech databases mean no variants
- 基底 `voices()`：an engine without voice metadata contributes no voices
- `log.py` 匯出：reported to the user
- `mainLocalePolicy.shared_section`：the speech section may not exist during synth startup
- `with_order_log`：debug counter only; never affects speech
- `pipeline.context.current_context`：no synth yet: use the generic context
- `segmentHost._run`：delivered as the segment's terminal failure
