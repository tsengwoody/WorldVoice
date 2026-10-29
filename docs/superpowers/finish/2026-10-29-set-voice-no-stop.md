# 交接紀錄：說話時切換語音不再讓語音卡住

日期：2026-10-29。分支：`fix/set-voice-no-stop`（`c6b5a73..9c3bec4`），以 fast-forward merge 到 master `9c3bec4`。流程：簡化流程＋最後 Fable review。review 結果是 Critical 0、Important 0、Minor 5，全部修正。review：`docs/superpowers/finish/2026-10-29-set-voice-no-stop-review.md`。

## 問題

正式使用時，所有引擎都走逐段語音（`forceUnverifiedDrain` 預設為 True）。

舊的 `SynthDriver._set_voice` 在換成不同聲音時，會先呼叫舊聲音的 `stop()`，一路走到 `core.cancel()`，但沒有取消請求的 token。結果：
- `SegmentHost` 把進行中的段落標成「靜默」，既不送 DRAINED，也不送 FAILED；
- scheduler 停在 `AWAITING_COMPLETION`，沒有逾時，要等到下一次 NVDA 取消（也就是任何按鍵）才會放開；
- 使用者聽到的是：正在說的內容被切斷，之後一直安靜，讀全文也不再往下讀。

按鍵換聲音的路徑不會遇到，因為 NVDA 會先取消，問題被蓋住了。會遇到的情況：
- 不是按鍵造成的切換程式或焦點變化（滑鼠、觸控、程式自己搶焦點），而且目的程式的設定檔用的是另一個聲音，當下正在讀全文、`ui.message` 或通知；
- 其他 add-on 用程式直接設定 `synth.voice`。

## 改了什麼

- **`_set_voice` 不再呼叫 `stop()`**（`79bf6c9`）。當下這句會用原本的聲音說完，之後才使用新的聲音，這和 NVDA 內建的 eSpeak、OneCore 相同。不存在的聲音名稱仍會丟出 `LookupError`，而且丟出前不會動到任何東西；以前是先停掉語音，才發現名稱不存在。
- **刪除 `VoiceFacade.stop`**，並加上守門測試（`7ea63a6`、`618194f`）。正式程式只能在 scheduler 的取消流程裡停止引擎，只有三個地方：`TaskManager._stop_playback`、`EngineSession.cancel`、`VoiceClassAdapter.cancel`。
- **回歸測試** `tests/test_set_voice_in_flight.py`：OneCore、VE、Cerence 用真實的組合，eSpeak 用 port；在合成中和播放中各換一次聲音，`keepMainLocaleVoiceConsistent` 開和關都測。這些測試在修正前的程式上全部失敗，症狀和實際卡住的情況一樣。
- **readme**：六個語言都在「下一版更新」加了一條（`999d48a`）。
- **spec 更正**：phase 10a spec 用刪除線保留原文，並標註 Corrected by（`cca6d2b`）。
- 測試從 3571 增加到 3589 passed，0 skipped。

## 尚未驗證（Windows／NVDA）

測試版本：master `9c3bec4` 以後建置的 add-on，WASAPI 開啟。每個引擎（eSpeak、OneCore、SAPI5、RHVoice、VE、Cerence）都要測。

1. **非按鍵切換程式。** 設定一個 app 專屬設定檔，主語音用和預設不同的聲音。在程式 A 開始讀全文，或播一段長訊息，然後用滑鼠點到程式 B。
   - 修正前：語音被切斷，之後一直安靜。
   - 修正後：這句用原本的聲音說完，接著用新聲音報出程式 B。
2. **讀全文時用設定環換聲音。** NVDA 停掉讀全文是預期的行為，要確認新聲音能正常報出來。
3. **在設定對話框換聲音。** 用鍵盤和滑鼠各試一次。
4. **讀全文設定檔用不同的聲音。** 開始讀全文、讀到自然結束、用按鍵中斷，三種情況都要試。
5. **設定檔裡設了已經移除的聲音。** 切換到這個設定檔時不會卡住，也不會先把語音停掉。
