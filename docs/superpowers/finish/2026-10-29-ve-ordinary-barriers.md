# 交接紀錄：VE／Cerence 一般語音宣告 `AUDIO_FED`、`ENGINE_DONE`

日期：2026-10-29。分支：`fix/ve-ordinary-barriers`（`3a8e87a..717c302`），以 fast-forward merge 到 master `717c302`。流程：簡化流程＋最後 Fable review。使用者同意的兩個補強：token 取消如果改變播放器行為就先停下來問（結果不需要，行為不變）；以及這份交接紀錄。

## 改了什麼

- **`SegmentHost.withdraw(record)`**（`513a3e9`）：讓引擎把「只被自己的 token 取消」的一般語音 record 撤回。`retire` 會回報已取消（`OrdinaryOutcome(cancelled=True, error=None)`），不檢查關卡，**也不停播放器**。host 的取消和已記錄的錯誤，仍然各走原本的路徑。只有一般語音的 record 能撤回，逐段語音會被拒絕。
- **VE／Cerence 一般語音**（`3b42e8a`）：`_ORDINARY_BARRIERS = {AUDIO_FED, ENGINE_DONE}`。`_retireRecord` 在兩次標記之後才讀 token，如果 token 已經取消，就呼叫 `withdraw`。
- **缺關卡時寫 log**（`6acda3d`）：一般語音結束時如果缺關卡，`SegmentHost.retire` 會寫一行 `log.error`（「`<引擎> ordinary speech retired without its <名稱> barriers`」）。以前這種情況完全沒有紀錄。
- **spec 更正**（`ff87a35`）：phase 3d-1 的決策 #2，以及 P52 spec 的宣告表，都用刪除線保留原文，並標註 Corrected by。
- 測試：從 3537 增加到 3571 passed，0 skipped。review：`docs/superpowers/finish/2026-10-29-ve-ordinary-barriers-review.md`。
  - Fable 結果：Critical 0、Important 2、Minor 2，全部修正。
  - 修正 review（Opus xHigh）：新的 Minor 1 項（N1），也已修正。

## 為什麼只有 VE／Cerence 需要 `withdraw`

VE／Cerence 是唯一會收到請求 cancellation token 的 core（`Voice.extraCapabilities` 的 `"cancellationToken"`）。token 由 worker 自己判斷，host 不知道。其他四個引擎的一般語音只會被 NVDA 的 `cancel()` 取消，取消一律經過 host。

唯讀調查確認了兩件事：
- 正式使用時，所有引擎都走逐段語音，plain 路徑只是後備。
- token 現在的作用是核對 plain 路徑 DONE 屬於哪個請求。拿掉 token 會讓舊請求的 DONE 被當成新請求已完成，這已經在 Linux 上重現。所以保留 token，並加上 `withdraw`。

`withdraw` 不停播放器的原因：VE 的 `_stopPlayer()` 不會重設 `_paused`，只有 `cancel()` 會。如果在「token 已取消、`core.cancel()` 還沒到」這段時間停掉播放器，暫停中的下一句可能卡在「等恢復」。

## 已驗證（Linux）

- token 取消的播放器行為不變。Fable 用 master 的 wrapper 和 host，搭配分支上的 token 測試，只保留播放器和 DONE 的斷言來跑。涵蓋開始前、原生呼叫前、送音中、最後一個呼叫之後、兩個片段之間、token 取消後接著 `core.cancel()` 等情況，16 個全部通過，數字和分支一致。
- 正常的 SDK 執行不會被判失敗。檢查過的情況包括：切換聲音、字元模式、空白請求、暫停、`cancel()` 保留的 `DoneSpeaking`，以及舊路徑的 `ENDPROCESS`。
- 跑完整套件時記錄所有 log：缺關卡的 ERROR 只出現在刻意測試缺關卡的案例，六個引擎正常的一般語音一筆都沒有。
- 每個錯誤寫法的突變（W6、W3b、W3c、拿掉 log）都會被測試抓到。

## 尚未驗證（Windows／NVDA）

測試版本：master `717c302` 以後建置的 add-on，WASAPI 開啟。

正式設定下，VE／Cerence 走逐段語音，不會用到一般語音路徑。所以要測這一項，必須另外建一個關掉 `forceUnverifiedDrain` 的測試版（在 `CompletionPolicy` 設 `forceUnverifiedDrain=False`），強制 VE／Cerence 走 plain 路徑。

1. **token 取消時，聲音停止的方式不變。** 用 VE 和 Cerence 各試一次：
   - 讀一段長文字，中途按鍵打斷；
   - 讀全文時快速上下移動焦點，例如在長清單裡連續按方向鍵。

   確認舊句子會立刻停止、新句子正常開始、不會卡住或重疊。也要在暫停中打斷一次，確認恢復後下一句正常。
2. **一般語音正常朗讀時，NVDA log 沒有出現「ordinary speech retired without its … barriers」。**
3. 以上都用正式版（沒關 `forceUnverifiedDrain`）再做一次，確認逐段語音沒有受影響。
