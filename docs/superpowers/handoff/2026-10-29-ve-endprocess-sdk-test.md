# 交接：在 Windows 上驗證 VE／Cerence SDK 的 `VE_MSG_ENDPROCESS`

日期：2026-10-29（第二輪同日補充）。基準：master（P52 已 merge，`1c22d47` 之後）。
檢測程式：同目錄的 `ve_endprocess_probe.py`。這是獨立的 Python 腳本，**不需要 NVDA**。
相關紀錄：`storage/refactor9.md` 中「評估：VE／Cerence 以最後一塊的 `VE_MSG_ENDPROCESS` 標 `ENGINE_DONE`」那一列；實作在分支 `fix/ve-endprocess-engine-done`，review 在該分支的 `docs/superpowers/finish/2026-10-29-ve-endprocess-engine-done-review.md`（I1、M3 就是這一輪要補的）。

## 第二輪：32 位元補測

### 為什麼要再跑一次

- 第一輪只用 **64 位元** Python 跑，載入的是 `VE\lib\AMD64` 和 `Cerence\lib\x64`（VE SDK 2.2.0、Cerence SDK 21.6.0），全部通過：VE 40 個語音 1000 pass／80 info，Cerence 161 個語音 4025 pass／322 info，沒有 FAIL、WARN、ERROR。
- 但 add-on 支援 NVDA 2024.1 起的版本，而 **NVDA 2024.1–2025.x 是 32 位元**（2026.1 才改成 64 位元）。這些使用者載入的是另一組二進位檔：VE 的 `lib\x86`、Cerence 的 `lib\x32`，第一輪沒有測到。
- 同一版 SDK 兩種位元數行為不同的機率很低，但這是這次改動唯一沒有證據的地方，補測很便宜。
- 這一輪也順便加上 review 指出的片段形狀（見下方「新增的片段」）。新片段在 64 位元也沒測過，所以**兩種位元數都請再跑一次**。

### 怎麼跑

1. 準備一個 **32 位元** 的 Windows Python（3.8 以上即可；NVDA 2024.1–2025.x 本身用的是 32 位元 Python 3.11，用 3.11 最接近）：
   - 從 python.org 下載 **Windows installer (32-bit)** 安裝；或
   - 已經有 `py` 啟動器時，`py -0p` 列出已安裝的版本，名稱後面有 `-32` 的就是 32 位元。
   - 確認位元數：`py -3-32 -c "import struct; print(struct.calcsize('P') * 8)"` 要印出 `32`。
2. 執行（在 repo checkout 裡，或單獨複製腳本出來都可以，見 §2）：

   ```bat
   cd <repo>\docs\superpowers\handoff
   py -3-32 ve_endprocess_probe.py
   py -3-64 ve_endprocess_probe.py
   ```

   第一行測 32 位元程式庫，第二行用 64 位元 Python 重跑一次新片段。指定版本也可以，例如 `py -3.11-32 ve_endprocess_probe.py`。
3. 腳本用 **add-on 自己的規則** 選 lib 資料夾，不需要也不能手動指定：

   | 引擎 | add-on 的規則 | 32 位元 Python | 64 位元 Python |
   |---|---|---|---|
   | VE | 環境變數 `PROCESSOR_ARCHITECTURE`（`driver/VE/driver/ve2/__init__.py`） | `lib\x86`（64 位元 Windows 上的 32 位元行程，WOW64 會把它設成 `x86`） | `lib\AMD64` |
   | Cerence | `sys.maxsize`（`driver/Cerence/driver/ttsapi/__init__.py`） | `lib\x32` | `lib\x64` |

   32 位元那一次，每個引擎開頭那一行必須是 `… 32-bit lib x86 (PROCESSOR_ARCHITECTURE=x86; WOW64 on AMD64) …`（VE）和 `… 32-bit lib x32 (sys.maxsize: 32-bit; …) …`（Cerence）。如果腳本說找不到 `lib\x86` 或 `lib\x32`，代表 workspace 裡沒有 32 位元程式庫——32 位元 NVDA 也會載入失敗，請直接回報這件事。
4. log 檔名帶位元數，兩次執行不會混在一起：`ve_endprocess_probe-32bit.log`、`ve_endprocess_probe-64bit.log`（都在腳本旁邊）。每一行結果也帶 `py32 lib=x86` 這樣的標記。

### 新增的片段

計分（pass／FAIL）的是 add-on 真的會送的形狀；只記錄（info）的是 add-on 不會送、或不會用到結果的形狀。完整清單見 §3。

| 類別 | 片段 | 計分？ | 理由 |
|---|---|---|---|
| 控制字元 | `\x07`、`\x7f`、`\x01\x02\x03`、`\x9b`、`Hello\x07` | 計分 | 內層 `speak()` 只 `strip()` 空白、只拿掉 ESC，其他控制字元會原樣送出 |
| 零寬與格式字元 | U+200B、U+200C、U+200D、U+2060、U+FEFF（BOM）、U+200E、U+200F、U+00AD、五個零寬混在一起、`Hello`＋U+200B、BOM＋`Hello` | 計分 | Python 的 `strip()` 不把它們當空白 |
| 孤立 surrogate | `\ud800`（`encode("utf-8", "replace")` 後送出 `?`） | 計分 | NVDA 從 UTF-16 來源拿到的文字可能有 |
| 拼字模式 | `\tn=spell\` `\pitch=130\` `a` `\pitch=100\` `\mrk=\` `\tn=normal\`（大寫字母） | 計分 | NVDA 對大寫字母送 `PitchCommand(offset)`／`PitchCommand()` |
| 拼字模式、很多控制碼 | 拼 250 個字、每個字後面一個 `\mrk=`，chunker 切出的三塊：`\tn=spell\`＋100 字＋99 個 `\mrk=`；`\mrk=`＋100 字＋99 個 `\mrk=`（共 100 個）；50 字＋51 個 `\mrk=`＋`\tn=normal\` | 計分 | chunker 不計控制碼長度，每 100 個字切一次，切點後的控制碼跟著下一塊 |
| 只有 bookmark | 連續 100 個 `\mrk=` | 計分 | 只有 `IndexCommand` 的序列不會被切開，整串送出 |
| 取消之後 | 模擬取消之後，**同一個 instance** 立刻再送 `Hello world.` 和 `.` | 計分 | add-on 取消後會用同一個 instance 繼續說 |
| 參數 | 先 `setParamList`（variant 設回目前值、rate、pitch、volume、waitfactor），再送 `Hello world.`、`.`、空白、bookmark、`\tn=spell\a\tn=normal\`、U+200B；兩組：最小值（rate 50、pitch 50、volume 0、waitfactor 0）、最大值（rate 400、pitch 200、volume 100、waitfactor 9）；測完還原 | 計分 | add-on 說話前會用 `TtsSetParamList` 設這些參數，範圍是 NVDA 設定能到的兩端 |
| NUL | `\x00` | info | NVDA 的文字來自以 NUL 結尾的 C 字串，不會帶 NUL |
| Cerence 的 `\rate=`、`\vol=` | 第一輪已有的片段 | Cerence 改為 info（VE 仍計分） | Cerence 內層 `speak()` 沒有 `RateCommand`／`VolumeCommand` 分支，不會送這兩種 |

### 要回傳什麼

**請回傳兩個 log 檔**：`ve_endprocess_probe-32bit.log` 和 `ve_endprocess_probe-64bit.log`，以及兩次執行的結束碼。太長的話，每個檔至少回傳：

- 每個 `=== … probe …` 開頭那一行（SDK 版本、Python 位元數、lib 資料夾和選擇的理由）；
- 每個 `=== … summary (…-bit Python, lib …) … ===` 區塊（含下面列出的 FAIL／WARN 行）；
- 所有 `[FAIL]`／`[WARN]`／`[ERROR]` 行；
- 一兩個 `[info] … stop-after-2-buffers` 行和緊接著的 `after-stop-text` 行；
- 一兩個 `@min-params` 行。

判定標準和第一輪相同（§1）：兩個位元數、兩個引擎都只有 `[pass]` 和 `[info]`，結束碼 0，才能說 32／64 位元程式庫都證明過。

## 1. 要回答的問題

**每一次 `ve_ttsProcessText2Speech` 成功返回（`NUAN_OK`）之前，SDK 是否一定會送一次 `VE_MSG_ENDPROCESS`？** 包括不產生音訊的片段，例如只有標點、只有空白、只有控制碼（bookmark、pause、pitch 等）、只有控制字元或零寬字元的片段。

### 為什麼要問

- VE／Cerence 的 wrapper 只在收到 `ENDPROCESS` 時，才會沖刷 Sonic 和 `_feedBuf`，把尾端音訊送進播放器（`addon/synthDrivers/WorldVoice/driver/VE/__init__.py` 的 `_ContextualVECallback._process`）。
- 原本 VE 的 `AUDIO_FED` 只代表「這段的每個原生呼叫都已返回」，沒有證明尾端已經沖刷出去。
- 分支 `fix/ve-endprocess-engine-done` 讓 VE／Cerence 在「這段最後一個原生呼叫收到 `ENDPROCESS`」時標 `ENGINE_DONE`（P52 的共用關卡，見 `runtime/barriers.py`）。
- 這件事的主要風險是誤判。如果某些片段 SDK 本來就不送 `ENDPROCESS`，這段就會被判失敗，scheduler 會取消整個請求，後面的段落都不會唸。
- 原本只有「有音訊時一定會送」的實證：Sonic 尾端從 2020 年起都靠它沖刷，從沒有尾端遺失的回報。「沒有音訊的片段也一定會送」在第一輪才驗證（只有 64 位元）。而一段文字的最後一個片段，常常就是句尾的標點（chunker 每 100 字元切一塊）。
- VE 和 Cerence 是兩套不同的 SDK，兩個都要測；32 位元和 64 位元是不同的二進位檔，也都要測。

### 判定標準

| 結果 | 結論 |
|---|---|
| VE、Cerence 的每個語音都只有 `[pass]`（以及不計分的 `[info]`），沒有 `[FAIL]`、`[WARN]`、`[ERROR]`；腳本結束碼為 0 | 可以證明不會誤判，「最後一個呼叫的 `ENDPROCESS` → `ENGINE_DONE`」成立 |
| 有任何 `[FAIL]`（返回 `OK` 但沒有 `ENDPROCESS`） | 不做關卡。另外記下是哪種片段、哪個語音、哪個位元數 |
| 只有 `[WARN]`（`ENDPROCESS` 出現多次，或不是最後一個訊息） | 回報，再討論判定方式 |
| 有 `[ERROR]` | 腳本或環境出了問題，回報後再看 |

`[info]` 不計入判定，只當參考，包括：
- 空字串（add-on 從不送空字串，因為 chunker 對空文字不會切出片段）；
- NUL（NVDA 的文字不會帶 NUL）；
- Cerence 的 `\rate=`、`\vol=`（Cerence 內層不會送）；
- 模擬取消：callback 回傳 USERSTOP 後，SDK 還會不會送 `ENDPROCESS`（add-on 對 USERSTOP 結果本來就 raise，不看 `ENDPROCESS`）；
- 任何非 `OK` 的結果（add-on 對非 `OK`／USERSTOP 的結果本來就 raise，不會走到關卡）。

## 2. 準備

1. Windows 上要有 VE 和 Cerence 的 SDK 和語音，也就是 WorldVoice 平常使用的那一套：
   - SDK：`%APPDATA%\nvda\WorldVoice-workspace\VE`、`%APPDATA%\nvda\WorldVoice-workspace\Cerence`（已安裝的 add-on 就是在 `addons` 資料夾旁邊找 workspace；可攜版 NVDA 或其他位置用 `--workspace` 指定）；
   - 語音：workspace 內的語音、`%APPDATA%\nvda\addons` 裡的語音 add-on（`vocalizer-expressive2-voice*`、`CerenceTTS-voice*`），或 Freedom Scientific 的 VE 語音資料。
2. 要有一般的 Windows Python 3.8 以上。**Python 的位元數決定測哪一組程式庫**（規則見上方「怎麼跑」第 3 點）：
   - 32 位元 Python → VE `lib\x86`、Cerence `lib\x32`（NVDA 2024.1–2025.x 載入的那組）；
   - 64 位元 Python → VE `lib\AMD64`、Cerence `lib\x64`（NVDA 2026.1 起載入的那組）；
   - add-on 會選的資料夾不存在時，腳本會說出它找的路徑和理由，然後停止。
3. 腳本會從 WorldVoice 的程式碼載入各引擎自己的 ctypes 層（`driver/VE/driver/ve2`、`driver/Cerence/driver/ttsapi`），確保結構定義和 add-on 一致：
   - 在 repo checkout 裡執行時（`docs/superpowers/handoff/` 底下），自動使用 repo 的 `addon/synthDrivers/WorldVoice/driver`；
   - 單獨複製腳本出來執行時，自動使用已安裝的 add-on：`%APPDATA%\nvda\addons\WorldVoice\synthDrivers\WorldVoice\driver`；
   - 都不對時，用 `--driver-dir` 指定。

執行時不需要開 NVDA，不會播放聲音，也不會修改任何檔案或設定（參數只設在腳本自己開的 instance 上，測完會還原）。唯一寫入的是 log 檔。

## 3. 執行

```bat
cd <repo>\docs\superpowers\handoff
py -3-32 ve_endprocess_probe.py
py -3-64 ve_endprocess_probe.py
```

- 預設會測**兩個引擎、所有已安裝的語音**。兩個 SDK 都帶有同名的 `ve.dll`，所以腳本會讓每個引擎各跑一個子行程（用同一個 Python）。
- 只測部分：
  ```bat
  py -3-32 ve_endprocess_probe.py --engine VE
  py -3-32 ve_endprocess_probe.py --engine Cerence --voices "Mei-Jia" "Samantha"
  ```
- 其他參數：`--workspace`、`--addons-dir`、`--driver-dir`、`--log`。用 `python ve_endprocess_probe.py -h` 查看說明。

### 每個語音送出的片段

這些是 add-on 實際可能送給 `ve_ttsProcessText2Speech` 的字串：內層驅動會把命令轉成控制碼，chunker 每 100 字元切一塊（控制碼不計長度）。依序送出：

| 類別 | 片段 | 計分？ |
|---|---|---|
| 一般文字（對照組） | `Hello world.`、`Hello`、`123.`、`你好。`、`word ` × 20 | 計分 |
| 只有標點 | `.`、`。`、`,`、`!?`、`-`、`…` | 計分 |
| 只有空白 | 一個空白、三個空白、全形空白、換行 | 計分 |
| 只有控制碼 | `\mrk=`（bookmark）、`\pause=`、`\pitch=`、`\rate=`、`\vol=`、`\tn=spell\`、連續 100 個 `\mrk=` | 計分（`\rate=`、`\vol=` 只對 VE 計分，Cerence 為 info） |
| 混合 | `\tn=spell\a\tn=normal\`、文字＋bookmark、bookmark＋`.`、空白＋bookmark | 計分 |
| 控制字元 | `\x07`、`\x7f`、`\x01\x02\x03`、`\x9b`、`Hello\x07` | 計分 |
| 零寬與格式字元 | U+200B、U+200C、U+200D、U+2060、U+FEFF、U+200E、U+200F、U+00AD、混合、`Hello`＋U+200B、U+FEFF＋`Hello` | 計分 |
| 孤立 surrogate | `\ud800`（送出 `?`） | 計分 |
| 拼字模式 | 大寫字母（`\pitch=` 前後包住）；250 字拼字切出的三塊（100 字＋100 個控制碼、100 字＋100 個 `\mrk=`、最後 50 字＋`\tn=normal\`） | 計分 |
| 參考 | 空字串、NUL | info |
| 模擬取消 | 長文字在第 2 個音訊緩衝時回傳 USERSTOP | info |
| 取消之後 | 同一個 instance 接著送 `Hello world.`、`.` | 計分 |
| 參數兩端 | 最小值、最大值兩組參數下送 `Hello world.`、`.`、空白、bookmark、`\tn=spell\a\tn=normal\`、U+200B（標籤後綴 `@min-params`／`@max-params`） | 計分 |

開啟語音的參數和 add-on 相同（`ve2.open`／`ttsapi.open`：marker 開啟、UTF-8、sentence read mode、22 kHz），callback 提供的緩衝大小也和 add-on 相同（8 KB PCM、100 個 marker）。

## 4. 結果

- log 寫在腳本旁邊的 `ve_endprocess_probe-32bit.log` 或 `ve_endprocess_probe-64bit.log`（依 Python 位元數），也會同時印在畫面上。每次執行都附加在後面，不會覆蓋。第一輪的 `ve_endprocess_probe.log` 不會再被寫入。
- 每個引擎開頭一行，例如：

  ```
  === VE probe 2026-10-29 10:00:00 SDK 2.2.0 Python 3.11.9 32-bit lib x86 (PROCESSOR_ARCHITECTURE=x86; WOW64 on AMD64) C:\…\VE\lib\x86 ===
  ```

- 每次原生呼叫一行，例如：

  ```
  [pass] VE py32 lib=x86 Mei-Jia (Mandarin Taiwanese) punct OK endprocess=1 audio=2048B sameThread=True msgs=BEGINPROCESS,OUTBUFREQ,OUTBUFDONEx2,ENDPROCESS
  ```

  - `py32 lib=x86`：Python 位元數和 lib 資料夾。
  - `endprocess`：這次呼叫收到幾次 `ENDPROCESS`。
  - `audio`：這次呼叫產生了多少 PCM 位元組，可以看出這個片段是否「不產生音訊」。
  - `sameThread`：callback 是否都在呼叫的同一條執行緒上執行。這可以順便驗證「VE 是同步呼叫」的假設。
  - `msgs`：訊息順序，重複的會壓縮成 `×N`。
- 每個引擎結束時會印出 `=== <engine> summary (<位元數>-bit Python, lib <資料夾>): … ===`，內容包括：
  - 語音數；
  - pass、FAIL、WARN、info、ERROR 的數量；
  - 所有 FAIL／WARN 的行；
  - 沒有原生呼叫在進行時收到的 callback（stray）。
- 結束碼：0 表示沒有 FAIL、WARN、ERROR，1 表示有。

要回傳的內容見最上方「要回傳什麼」。

## 5. 限制

- 不會載入 add-on 的語音調校資料（`.rules` ruleset 和 `.dcb` 字典）。它們影響發音，不影響 SDK 的訊息流程。
- 測的是片段本身，不經過 WorldVoice 的 pipeline。但上表已涵蓋 add-on 可能送出的各種片段形式；拼字模式的三塊和 chunker 的實際切法逐字相同（在 Linux 上用 `text/chunker.py` 驗證過）。
- 取消是模擬的：WorldVoice 的取消方式就是讓 callback 回傳 USERSTOP，所以結果可以參考。不過 add-on 在取消時還會停止播放器，這部分這裡不需要測。
- 參數只測兩端兩組，沒有測 variant 換成別的 voice model（add-on 會把 variant 設成使用者選的，這裡只設回目前值）。

## 6. 給接手的人（或 Windows 上的 Claude）

- 背景決策和理由都寫在 `storage/refactor9.md` 那一列。P52 的關卡定義在 `runtime/barriers.py` 和 `docs/superpowers/specs/2026-10-28-phase52-shared-barriers-design.md`。
- 第一輪（64 位元）通過後，實作已經在分支 `fix/ve-endprocess-engine-done` 完成並 review（可以 merge，只差 I1 這一輪的證據）。實作方向：
  - `_NativeCall` 加 `ended` 旗標，在 `_process` 的 `ENDPROCESS` 分支設定；
  - `_runNative` 在呼叫成功返回後，把結果寫到 record（每次覆寫，最後留下的就是最後一個呼叫的結果；BgThread 先進先出，所以不需要跨執行緒協調）；
  - `_retireRecord` 在「沒有原生呼叫」或「最後一個呼叫有 `ENDPROCESS`」時，標 `ENGINE_DONE`；
  - VE 的 strategy 宣告加上 `ENGINE_DONE`；
  - VE 和 Cerence 同步修改（`tests/test_vocalizer_drift.py`），並更新 `tests/test_native_strategy_guards.py` 的 `DECLARED_BARRIERS`。
- 第二輪全部通過：把 `runtime/barriers.py` 和 `end_process` docstring 的證據說明改成「32／64 位元程式庫都測過」（review M4），再 merge。
- 第二輪有 FAIL：記下片段、語音、位元數，回到 refactor9 那一列重新決定（不 merge，或只在證明過的位元數啟用）。
