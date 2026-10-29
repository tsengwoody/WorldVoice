# 交接：在 Windows 上驗證 VE／Cerence SDK 的 `VE_MSG_ENDPROCESS`

日期：2026-10-29。基準：master（P52 已 merge，`1c22d47` 之後）。
檢測程式：同目錄的 `ve_endprocess_probe.py`。這是獨立的 Python 腳本，**不需要 NVDA**。
相關紀錄：`storage/refactor9.md` 中「評估：VE／Cerence 以最後一塊的 `VE_MSG_ENDPROCESS` 標 `ENGINE_DONE`」那一列（目前結論為建議不做，等這次實測結果再決定）。

## 1. 要回答的問題

**每一次 `ve_ttsProcessText2Speech` 成功返回（`NUAN_OK`）之前，SDK 是否一定會送一次 `VE_MSG_ENDPROCESS`？** 包括不產生音訊的片段，例如只有標點、只有空白、只有控制碼（bookmark、pause、pitch 等）的片段。

### 為什麼要問

- VE／Cerence 的 wrapper 只在收到 `ENDPROCESS` 時，才會沖刷 Sonic 和 `_feedBuf`，把尾端音訊送進播放器（`addon/synthDrivers/WorldVoice/driver/VE/__init__.py` 的 `_ContextualVECallback._process`）。
- 目前 VE 的 `AUDIO_FED` 只代表「這段的每個原生呼叫都已返回」，沒有證明尾端已經沖刷出去。
- 我們在考慮讓 VE／Cerence 在「這段最後一個原生呼叫收到 `ENDPROCESS`」時標 `ENGINE_DONE`（P52 的共用關卡，見 `runtime/barriers.py`）。
- 這件事的主要風險是誤判。如果某些片段 SDK 本來就不送 `ENDPROCESS`，這段就會被判失敗，scheduler 會取消整個請求，後面的段落都不會唸。
- 目前只有「有音訊時一定會送」的實證：Sonic 尾端從 2020 年起都靠它沖刷，從沒有尾端遺失的回報。但「沒有音訊的片段也一定會送」，從來沒有驗證過。而一段文字的最後一個片段，常常就是句尾的標點（chunker 每 100 字元切一塊）。
- VE 和 Cerence 是兩套不同的 SDK，兩個都要測。

### 判定標準

| 結果 | 結論 |
|---|---|
| VE、Cerence 的每個語音都只有 `[pass]`（以及不計分的 `[info]`），沒有 `[FAIL]`、`[WARN]`、`[ERROR]`；腳本結束碼為 0 | 可以證明不會誤判，建議實作「最後一個呼叫的 `ENDPROCESS` → `ENGINE_DONE`」 |
| 有任何 `[FAIL]`（返回 `OK` 但沒有 `ENDPROCESS`） | 不做關卡。另外記下是哪種片段、哪個語音 |
| 只有 `[WARN]`（`ENDPROCESS` 出現多次，或不是最後一個訊息） | 回報，再討論判定方式 |
| 有 `[ERROR]` | 腳本或環境出了問題，回報後再看 |

`[info]` 不計入判定，只當參考，包括：
- 空字串（add-on 從不送空字串，因為 chunker 對空文字不會切出片段）；
- 模擬取消：callback 回傳 USERSTOP 後，SDK 還會不會送 `ENDPROCESS`。

## 2. 準備

1. Windows 上要有 VE 和 Cerence 的 SDK 和語音，也就是 WorldVoice 平常使用的那一套：
   - SDK：`%APPDATA%\WorldVoice-workspace\VE`、`%APPDATA%\WorldVoice-workspace\Cerence`；
   - 語音：workspace 內的語音、`%APPDATA%\nvda\addons` 裡的語音 add-on（`vocalizer-expressive2-voice*`、`CerenceTTS-voice*`），或 Freedom Scientific 的 VE 語音資料。
2. 要有一般的 Windows Python 3.8 以上，**位元數必須和 SDK 的 lib 一致**：
   - VE：`lib\x86` 用 32 位元，`lib\AMD64` 用 64 位元；
   - Cerence：`lib\x32` 用 32 位元，`lib\x64` 用 64 位元；
   - 位元數不對時，腳本會直接告訴你要換哪一種。
3. 腳本會從 WorldVoice 的程式碼載入各引擎自己的 ctypes 層（`driver/VE/driver/ve2`、`driver/Cerence/driver/ttsapi`），確保結構定義和 add-on 一致：
   - 在 repo checkout 裡執行時（`docs/superpowers/handoff/` 底下），自動使用 repo 的 `addon/synthDrivers/WorldVoice/driver`；
   - 單獨複製腳本出來執行時，自動使用已安裝的 add-on：`%APPDATA%\nvda\addons\WorldVoice\synthDrivers\WorldVoice\driver`；
   - 都不對時，用 `--driver-dir` 指定。

執行時不需要開 NVDA，不會播放聲音，也不會修改任何檔案或設定。唯一寫入的是 log 檔。

## 3. 執行

```bat
cd <repo>\docs\superpowers\handoff
python ve_endprocess_probe.py
```

- 預設會測**兩個引擎、所有已安裝的語音**。兩個 SDK 都帶有同名的 `ve.dll`，所以腳本會讓每個引擎各跑一個子行程。
- 只測部分：
  ```bat
  python ve_endprocess_probe.py --engine VE
  python ve_endprocess_probe.py --engine Cerence --voices "Mei-Jia" "Samantha"
  ```
- 其他參數：`--workspace`、`--addons-dir`、`--driver-dir`、`--log`。用 `python ve_endprocess_probe.py -h` 查看說明。

如果 VE 和 Cerence 的 lib 位元數不同，例如一個只有 32 位元、一個只有 64 位元，就用兩種 Python 各跑一次 `--engine`。

### 每個語音送出的片段

這些是 add-on 實際可能送給 `ve_ttsProcessText2Speech` 的字串：內層驅動會把命令轉成控制碼，chunker 每 100 字元切一塊。

| 類別 | 片段 |
|---|---|
| 一般文字（對照組） | `Hello world.`、`Hello`、`123.`、`你好。`、`word ` × 20 |
| 只有標點 | `.`、`。`、`,`、`!?`、`-`、`…` |
| 只有空白 | 一個空白、三個空白、全形空白、換行 |
| 只有控制碼 | `\mrk=`（bookmark）、`\pause=`、`\pitch=`、`\rate=`、`\vol=`、`\tn=spell\` |
| 混合 | `\tn=spell\a\tn=normal\`、文字＋bookmark、bookmark＋`.`、空白＋bookmark |
| 參考（不計分） | 空字串；長文字在第 2 個音訊緩衝時回傳 USERSTOP（模擬取消） |

開啟語音的參數和 add-on 相同（`ve2.open`／`ttsapi.open`：marker 開啟、UTF-8、sentence read mode、22 kHz），callback 提供的緩衝大小也和 add-on 相同（8 KB PCM、100 個 marker）。

## 4. 結果

- log 寫在腳本旁邊的 `ve_endprocess_probe.log`，也會同時印在畫面上。每次執行都附加在後面，不會覆蓋。
- 每次原生呼叫一行，例如：

  ```
  [pass] VE Mei-Jia (Mandarin Taiwanese) punct OK endprocess=1 audio=2048B sameThread=True msgs=BEGINPROCESS,OUTBUFREQ,OUTBUFDONEx2,ENDPROCESS
  ```

  - `endprocess`：這次呼叫收到幾次 `ENDPROCESS`。
  - `audio`：這次呼叫產生了多少 PCM 位元組，可以看出這個片段是否「不產生音訊」。
  - `sameThread`：callback 是否都在呼叫的同一條執行緒上執行。這可以順便驗證「VE 是同步呼叫」的假設。
  - `msgs`：訊息順序，重複的會壓縮成 `×N`。
- 每個引擎結束時會印出 `=== <engine> summary … ===`，內容包括：
  - 語音數；
  - pass、FAIL、WARN、info、ERROR 的數量；
  - 所有 FAIL／WARN 的行；
  - 沒有原生呼叫在進行時收到的 callback（stray）。
- 結束碼：0 表示沒有 FAIL、WARN、ERROR，1 表示有。

**請回傳整個 log 檔。** 如果太長，至少回傳：
- 每個 `=== … probe … SDK x.y.z …` 開頭那一行（SDK 版本、lib、Python 位元數）；
- 每個 `summary` 區塊；
- 所有 `[FAIL]`／`[WARN]`／`[ERROR]` 行；
- 一兩個 `[info] … stop-after-2-buffers` 行。

## 5. 限制

- 不會載入 add-on 的語音調校資料（`.rules` ruleset 和 `.dcb` 字典）。它們影響發音，不影響 SDK 的訊息流程。
- 測的是片段本身，不經過 WorldVoice 的 pipeline。但上表已涵蓋 add-on 可能送出的各種片段形式。
- 取消是模擬的：WorldVoice 的取消方式就是讓 callback 回傳 USERSTOP，所以結果可以參考。不過 add-on 在取消時還會停止播放器，這部分這裡不需要測。

## 6. 給接手的人（或 Windows 上的 Claude）

- 背景決策和理由都寫在 `storage/refactor9.md` 那一列。P52 的關卡定義在 `runtime/barriers.py` 和 `docs/superpowers/specs/2026-10-28-phase52-shared-barriers-design.md`。
- 如果結果是可以做，實作方向是：
  - `_NativeCall` 加 `ended` 旗標，在 `_process` 的 `ENDPROCESS` 分支設定；
  - `_runNative` 在呼叫成功返回後，把結果寫到 record（每次覆寫，最後留下的就是最後一個呼叫的結果；BgThread 先進先出，所以不需要跨執行緒協調）；
  - `_retireRecord` 在「沒有原生呼叫」或「最後一個呼叫有 `ENDPROCESS`」時，標 `ENGINE_DONE`；
  - VE 的 strategy 宣告加上 `ENGINE_DONE`；
  - VE 和 Cerence 要同步修改（`tests/test_vocalizer_drift.py`），並更新 `tests/test_native_strategy_guards.py` 的 `DECLARED_BARRIERS`。
- 如果結果是不做，把 log 的結論記到 refactor9 那一列，維持「建議不做」。
