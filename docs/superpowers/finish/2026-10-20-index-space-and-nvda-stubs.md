# Index space 循環重用與新版 NVDA 測試 stub 交接紀錄

**日期：** 2026-10-20

**分支：**
- `fix/nvda-stubs-new-nvda`：fast-forward merge 進 `master`，到 `9a33387`。
- `fix/index-space-wraparound`：rebase 到 `9a33387` 後，fast-forward merge 進 `master`，到 `21a942c`。

## 1. 修正內容

### 1.1 Index space 用完導致失聲（`fix/index-space-wraparound`）

- **問題：** 使用者在 Windows 上使用一段時間後，每一句話都丟出 `IndexSpaceExhausted("Source wire index range is exhausted")`，NVDA 從此沒有聲音。
- **原因：** `IndexLedger.prepare` 在 DRAIN 合約的 `IndexRange(1, 9999)` 裡，從 `next_index` 一路往上分配 wire index，用過的號碼永遠不回收。`next_index` 在整個 driver core 的生命週期都不會歸零。
- **修法：**
  - **循環重用：** wire index 在範圍內循環使用。每個 segment 拿到一段連續、不跨過最大值的號碼，這段號碼保留到 segment retire 為止。
  - **降級而不失敗：** 找不到能放下整段的空間時，segment 改成只帶結束標記；DRAIN 模式連標記都不帶。codec 會拿掉呼叫端的 `IndexCommand`，等 segment 結束時再依序送出原本的 index。
  - **log：** 每個 source 第一次降級時記一則 WARNING，之後改記 DEBUG。log 在鎖外寫。
- **使用者的決定：** 採用方案 A（循環重用）。`Decided by the user (2026-10-20)`。

### 1.2 新版 NVDA 測試 stub（`fix/nvda-stubs-new-nvda`）

- **問題：** `ref/nvda` 從 `732d1ce2f` pull 到 `7d25bc76e` 之後，`oneCore.py:32` 多 import 了 `SequenceItemT`，測試 stub 沒有這個名稱，造成 9 failed、112 errors。
- **修法：** 在 `tests/onecore_drain_harness.py` 的 stub 補上 `SequenceItemT`、`SetAttrCommand`、`XmlBalancerCommand`。另外新增一個測試，用 `inspect.get_annotations` 檢查這些型別標註名稱都有 stub 可用。新舊兩版 NVDA 都通過。
- **產品程式碼：** 沒有修改。

## 2. 驗證（`master` `21a942c`，Linux）

| 項目 | 結果 |
| --- | --- |
| `python3 -m pytest -q tests`（`ref/nvda` = `7d25bc76e`） | 1745 passed、0 skipped（基準 `5e1137b` 連舊版 NVDA：1722 passed、0 skipped） |
| `prek run --all-files` | 全部 Passed |
| `git diff --check` | 沒有輸出 |
| 受保護路徑（與 `5e1137b` 比較）、`git ls-files .../Neural` | 沒有輸出 |
| mutmut（`indexLedger.py`、`compat/indexCodec.py`） | 共 378 個：355 killed、6 timeout、17 survived；存活原因見 plan 的 Implementation notes |
| review | 兩份 review 都由 Fable 5.1 撰寫，都是 Critical 0、Important 0；Minor 都已修正，或已說明不修的理由 |

## 3. 測試版本

| 項目 | 內容 |
| --- | --- |
| 檔案 | `/workspace/WorldVoice-pkg-index-space/WorldVoice-6.2-test-index-space-1-9999.nvda-addon` |
| 來源 commit | `21a942c`（從 detached worktree 執行 `scons version=6.2-test-index-space-1-9999 channel=dev`） |
| 大小 | 1,845,611 bytes |
| SHA-256 | `be74c5d66c836097c5d2a56e61e7d5d2c8b9f15fe768dc06417dab58a90c7fbe` |
| 內容 | 121 個項目，不含 Neural；套件裡的 `indexLedger.py`、`indexCodec.py` 和 commit 的內容逐位元組相同 |

## 4. 尚未驗證

這些項目都要用上面的測試版本，在 Windows 上的 NVDA 手動驗證。

### Index space（spec §8.5）

1. **長時間朗讀：** eSpeak、RHVoice、OneCore、SAPI5（WASAPI）、VE、Cerence 各自用 say-all 讀長文件，直到遠超過 10000 個 NVDA index，例如連續讀 2 小時以上。
   - 聲音不會中斷。
   - log 沒有 `IndexSpaceExhausted`，也沒有 "Speech scheduler task error"。
   - 號碼繞回之後，say-all 的游標仍然跟著語音走。
2. **繞回之後的中斷與移動：** 反覆按 Ctrl 中斷 say-all，並快速用方向鍵移動。游標不會提早跳走，和繞回之前相比，沒有漏讀或重讀的片語。
3. **多語言混合：** 會切換引擎的文字（例如 VE ↔ OneCore），每個引擎在自己的號碼繞回之後都繼續發聲。
4. **SAPI5 舊式音訊（LEGACY_DONE）：** 行為和修正前相同。
5. **降級 WARNING：** 一般使用時，NVDA log 不會出現降級的 WARNING。

### 新版 NVDA（`7d25bc76e` 以後）

6. **OneCore 逐字：** 用 OneCore 語音，按 Numpad 5 兩下拼字，用 Numpad 1／3 逐字移動。
   - 字元的唸法和 NVDA 自己的 OneCore driver 相同。
   - say-all 的 index 與游標追蹤不受影響。
7. **語音設定面板：**
   - 改一個下拉選單後按取消。
   - NVDA 設定開著時切換語音合成器，再回到語音面板。
   - log 沒有例外，「Punctuation pause characters」欄位沒有重複出現。

## 5. 使用者還沒確認的使用者可見預設

1. 範圍維持 `IndexRange(1, 9999)`。
2. 單一 segment 超過 9999 個 index 時，照樣唸出，但它的 NVDA index callback 要等它結束時才送出。第一次發生時，NVDA log 會記一則英文 WARNING。
3. OneCore 的 `CharacterModeCommand` 沿用新版 NVDA 的行為：逐字的唸法和 NVDA 自己的 OneCore 一樣。
4. 不在 WorldVoice 定義 `RATE_BOOST_MULTIPLIER`。用 eSpeak 並開啟語速加倍時，MathCAT 的停頓不會跟著放大。
5. 測試繼續相容舊版 NVDA `732d1ce2f`。

Linux 上只驗證了受控的 native 與音訊邊界。Windows 上的 NVDA、實際音訊裝置與各引擎 SDK 都還沒有驗證。

## 6. Commit

`git log --reverse --format='%h %s' 5e1137b..21a942c`

- `ae7415c` docs: spec the test-stub fix for NVDA 7d25bc76e
- `c5b24ba` docs: plan the test-stub fix for NVDA 7d25bc76e
- `8a6d4d1` test: stub SequenceItemT for NVDA's new OneCore import
- `8e7cc82` docs: review the test-stub fix for NVDA 7d25bc76e
- `0b8f21a` test: stub the speechXml names oneCore.py uses only in annotations
- `36905db` docs: list the plan in the spec's expected branch diff
- `9a33387` docs: record how the review's minor items were handled
- `e3ca207` docs: add the index space wraparound fix spec
- `272537f` docs: add the index space wraparound fix plan
- `8b8c1da` fix: reuse wire indexes cyclically so a source never runs out
- `960e64d` docs: record the user's choice of cyclic index reuse
- `e315a47` fix: speak a segment that gets no free index run instead of failing it
- `89ad043` test: check the cyclic allocation invariants with Hypothesis
- `a107d4e` build: run mutmut on the index codec too
- `a0764bc` test: kill index ledger and codec mutants and record the survivors
- `664581e` docs: review the index space wraparound fix
- `ff2c16e` test: pin a live run ahead of the cursor in the allocation property test
- `f5545ec` docs: say the stored index cursor may be one past the maximum
- `80c3794` docs: note why the index search loop always advances
- `226699b` test: drain a degraded index-only segment through the real wrappers
- `ae5e629` test: check that an index comes back only after a full turn of the range
- `93cbc2c` test: replay the scripted property example afresh on every run
- `963d918` docs: identify surviving mutants by their change, not only their number
- `21a942c` docs: record how the review's minor items were fixed
