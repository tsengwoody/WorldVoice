# 階段 1：引擎 segment 契約測試

日期：2026-10-01。
基準：`master`（`0fa002b`，含階段 0）。分支：`phase1-engine-contract`。
狀態：對話中的範圍與設計已獲使用者確認；本文件待使用者審閱。

本文件是 [`refactor.md`](../../../refactor.md) §9 的階段 1，對應 §4.4 末段「契約測試」。階段 0 的 spec 見 [2026-10-01-phase0-hygiene-fixes-design.md](2026-10-01-phase0-hygiene-fixes-design.md)。

## 需求與範圍

使用者要用一組對所有引擎參數化的契約測試，鎖住 `speak_segment` 對 scheduler 可觀察的行為。階段 3 會把各 wrapper 遷移到共用的 `SegmentHost`，這組測試就是那時的安全網。已知不符合契約的引擎要在測試結果中看得見（「先讓差異變紅」），修好時要能自動察覺。

涵蓋引擎：VE、Cerence、OneCore、RHVoice、SAPI5（WASAPI 路徑）、eSpeak，以及 Neural。Neural 不在 repo 內，驅動不存在時其案例 skip。

契約項目：

1. **正常完成**：恰好一個 `SEGMENT_DRAINED`，帶原 context 的 `source_id`、`segment_id`；在 lifecycle delivery thread 上交付，不在呼叫 `speak_segment` 的 thread 上。
2. **terminate 後**：`terminate()` 之後呼叫 `speak_segment`，恰好一個 `SEGMENT_FAILED`，帶原 context；native 沒有被呼叫。
3. **token 已取消**：以已取消的 token 呼叫 `speak_segment`，呼叫正常返回、native 沒有被呼叫、等待期間沒有任何終端事件。
4. **不阻塞到 delivery**：在該段尚未完成時，`speak_segment` 就返回；之後放行完成，恰好一個 `SEGMENT_DRAINED`。

**不在範圍內**：

- 修改任何 production code（含 C3 本身的修正，屬於階段 3）。
- control error → FAILED 契約：各引擎觸發方式不同、adapter 成本最高，且各自的 drain 測試已涵蓋錯誤路徑；待階段 3 由 `SegmentHost` 統一 latch 後再列入。
- `get_segment_drain_support` 簽名統一：唯一呼叫端（`compat/completionPolicies.py`）一律以關鍵字傳入 `nvda_version`、`audio_mode`，現有兩種簽名都能運作，屬表面差異。
- `pause`：`refactor.md` §4.1 只列出哪些引擎覆寫 `pause`，沒有 scheduler 可觀察的契約可寫。
- 既有各引擎 drain 測試與 `tests/test_runtime_adapter_contract.py`（假 `ContractCore`）維持不變。
- 內層驅動 `driver/<Engine>/driver/` 不修改；Neural 程式碼不提交。

成功條件：

1. 四項契約 × 七個引擎，共 28 個參數化案例，全部存在於單一測試檔。
2. 沒有 Neural 時：VE、Cerence 的第 4 項為 XFAIL，Neural 的 4 個案例 SKIP，其餘全部 PASS。
3. XFAIL 一律 `strict=True` 並附原因；修好時轉成 XPASS，測試失敗，強迫移除標記。
4. 解開 `storage/Neural-snapshot-2026-10-01.zip` 後，Neural 的 4 個案例執行並通過（或依「意外差異」規則標 xfail）。
5. 全部測試通過：基線 1233 passed、92 skipped，加上本階段新增案例。
6. 測試不會因 adapter 卡住而掛起：每個等待都有逾時，收尾時一律放行所有卡住的假物件。

## 現況

- 每個引擎已有自己的 drain 測試與假 native／player，但驅動方式各不相同：
  - eSpeak、RHVoice、OneCore、Neural：`tests/<engine>_drain_harness.py` 提供 `load_<engine>`；
  - SAPI5：loader 與假物件寫在 `tests/test_sapi5_segment_drain.py` 內；
  - VE、Cerence：`tests/worldvoice_cancel_wrapper_harness.load_real_driver_with_native_stubs`，測試內以 `emit(...)` 模擬 SDK callback，token 用 `test_worldvoice_cancel_wrappers.Token`。
- 每個 loader 都重新載入一份 runtime，事件 enum 必須取自同一份（`env.rt.models.EventKind`）。
- 已確認的契約差異：
  - **C1** 已在階段 0 修正，七個引擎在 terminate 後都會回報 FAILED，第 2 項預期全綠。
  - **C3**：VE、Cerence 的 `speak_segment` 同步執行 native 合成，再以 50 ms 輪詢等待 delivery（`driver/VE/__init__.py` 的 `_wait_segment_delivery`）。其餘引擎排入 thread 後立即返回。
- C3 的實際影響小於 `refactor.md` 所述。`runtime/scheduler.py` 的 `_run_one` 在 `playback.speak(...)` 之後本來就 `done.wait()`，一次只處理一段；VE/Cerence 阻塞並沒有額外序列化 pipeline。實際差異是：取消後最多約 50 ms 才返回，以及為避免在 delivery thread 上自我等待而需要的特殊處理。仍屬引擎間不一致（LSP），因此列為契約。

## 設計

### 元件

**`tests/engine_contract_harness.py`**：定義 adapter 介面與七個實作。

```python
class SegmentContractAdapter(Protocol):
	engine: str
	EventKind: type          # 該 adapter 所載入 runtime 的 EventKind
	PlaybackContext: type

	def open(self, monkeypatch, tmp_path) -> None: ...
	def close(self) -> None: ...                       # 放行所有 hold，再 terminate；可重複呼叫
	def new_token(self) -> object: ...                 # 該引擎測試慣用的 CancellationView
	def speak(self, commands, token, context, sink) -> None: ...   # 直接呼叫 speak_segment
	def complete(self) -> None: ...                    # 放行假 native／player，讓目前這段正常完成
	def terminate(self) -> None: ...
	def native_call_count(self) -> int: ...
	def delivery_thread_ident(self) -> int | None: ...
```

- 每個 adapter 沿用該引擎既有的 loader 與假物件，不複製假物件程式碼。若既有 loader 寫在測試檔內（SAPI5），adapter 從該檔 import。
- 讀取 lifecycle 私有屬性（例如 `_segmentLifecycle._delivery_thread`）只發生在 adapter 內。階段 2 提供公開 API 後，只需要改 adapter。
- `open()` 之後，假物件預設就讓每一段停在完成之前（例如 player 的 idle／sync 或 native 返回尚未放行），只有 `complete()` 會放行。原型確認六個既有 harness 的假物件本來就是這樣運作；VE/Cerence adapter 自行把 player 的 `idle` 換成等待 `complete()` 的 Event。
- 每個測試都在輔助 thread 上呼叫 `speak`。VE/Cerence 的 `speak_segment` 會在呼叫端 thread 上同步執行 native，若在測試 thread 上呼叫，就等不到 `complete()`。
- Neural adapter 套用 `neural_drain_harness.requires_neural`。

**`tests/test_engine_segment_contract.py`**：四個契約測試，以 `pytest.fixture(params=[...])` 參數化七個 adapter，案例 id 為引擎名稱。fixture 在 yield 之後一律呼叫 `adapter.close()`。

### 四項契約的測試方式

1. **正常完成**：在輔助 thread 呼叫 `speak` → `complete()` → 等待事件（逾時 2 秒）。斷言恰好一個事件、`kind is EventKind.SEGMENT_DRAINED`、`source_id is context.source_id`、`segment_id` 相同；交付 thread 等於 `delivery_thread_ident()`，且不等於呼叫端 thread。等待 0.1 秒後再斷言仍只有一個事件，以抓晚到的重複事件（階段 0 審查的 minor）。
2. **terminate 後**：`terminate()` → `speak` → 等待事件。斷言恰好一個 `SEGMENT_FAILED`、context 相同、`native_call_count() == 0`。同樣補 0.1 秒後的重複檢查。
3. **token 已取消**：建立 token 並取消 → `speak`。斷言呼叫返回、`native_call_count() == 0`；等待 0.2 秒，事件清單仍為空。
4. **不阻塞到 delivery**：在 daemon thread 呼叫 `speak` → `join(1)`。斷言 thread 已結束且尚無事件 → `complete()` → 等待恰好一個 `SEGMENT_DRAINED`。thread 未結束時測試失敗，收尾的 `close()` 放行 hold，讓 thread 結束。

### 已知差異的標示

```python
pytest.param("VE", marks=pytest.mark.xfail(strict=True, raises=C3Blocking,
	reason="C3: VE speak_segment blocks until delivery; fixed by SegmentHost in phase 3"))
# Cerence 同上，原因字串中的引擎名稱改為 Cerence。
```

只套在第 4 項測試的 VE、Cerence 參數上，並以 `raises=C3Blocking` 收窄：測試把 C3 斷言放在最後，以 `C3Blocking`（`AssertionError` 子類別）拋出，其餘斷言（complete 前不得交付、事件種類）對 VE/Cerence 照常生效。（最終審查發現：整個測試 xfail 會把 VE/Cerence 的其他退化吞成 XFAIL，例如提早交付。）實作時若發現其他差異，同樣以 strict xfail 標示，原因寫明現象與 `refactor.md` 的對應編號（若有），並在本文件「實作發現」一節補記。階段 1 不修改 production code。

### Neural 的驗證

Neural 程式碼只在臨時 worktree 中由 `storage/Neural-snapshot-2026-10-01.zip` 解開，用來驗證 Neural adapter；完成後刪除該 worktree。主 checkout 與任何 commit 都不含 `driver/Neural/`。

## 測試與驗收

- `python3 -m pytest tests/test_engine_segment_contract.py -v`：沒有 Neural 時為 22 passed、2 xfailed、4 skipped（另加實作發現的 xfail，passed 數相應減少）。
- `python3 -m pytest tests -q`：全部通過，passed 為 1233 加上本階段新增的 PASS 案例數，skipped 為 92 加 4。
- 在含 Neural 快照的臨時 worktree 中，Neural 的 4 個案例執行且不 skip。
- `git ls-files addon/synthDrivers/WorldVoice/driver/Neural`：無輸出。
- `git diff master --stat -- addon/`：無輸出（本階段不改 production code）。
- 除了 VE/Cerence 第 4 項以外，契約測試寫好就會通過，因為它們鎖的是現有行為。每項契約都以一次暫時的 production 變異證明它能失敗，驗證後以 `git checkout` 還原：
  - 第 1 項：`runtime/segmentLifecycle.py` 的 `_deliver` 對同一事件呼叫 sink 兩次 → 所有引擎失敗（收到 2 個事件）。
  - 第 2 項：還原 eSpeak 的 C1 修正（terminated 時 `return`）→ eSpeak 失敗。
  - 第 3 項：`runtime/playbackWork.py` 的 `is_valid` 忽略 token → OneCore、RHVoice、SAPI5、eSpeak、Neural 失敗。VE/Cerence 在 wrapper 內自行檢查 token，不受此變異影響。
  - 第 4 項：`--runxfail` 下 VE、Cerence 失敗，訊息為 "speak_segment did not return before the segment completed"。

## 實作發現

原型（暫時 worktree，含 Neural 快照）結果：沒有發現 C3 以外的契約差異。含 Neural 時為 26 passed、2 xfailed；不含 Neural 時為 22 passed、4 skipped、2 xfailed；連續 5 次結果相同。

- 既有 Neural／VE 測試使用的 `prove_fake_quiescence` stub 在這四項契約中不需要（它只影響取消路徑），adapter 不套用。
- VE/Cerence 的 fake SDK 在 terminate 時需要 stub `native.close`、`native.terminate`；既有 VE fixture 收尾時從不 terminate，所以沒有這兩個 stub。

實作時若發現其他差異，於此逐項補記：引擎、契約項目、現象、xfail 原因。
