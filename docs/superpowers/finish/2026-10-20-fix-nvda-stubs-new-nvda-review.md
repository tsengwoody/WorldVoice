# fix/nvda-stubs-new-nvda Review 紀錄

日期：2026-10-20。分支：`fix/nvda-stubs-new-nvda`（`master` `5e1137b` 之後 3 個 commit：spec `ae7415c`、plan `c5b24ba`、修正 `8a6d4d1`）。
依據：

- 規格 `docs/superpowers/specs/2026-10-20-fix-nvda-stubs-new-nvda-design.md`
- 計畫 `docs/superpowers/plans/2026-10-20-fix-nvda-stubs-new-nvda.md`
- `DEVELOPMENT_WORKFLOW.md` 第 3.3、7、8 節

流程：審閱者為 sub agent（Fable 5.1），唯讀；沒有修改原始碼或測試，也沒有動 `ref/`。測試在 worktree 本身與 scratchpad 的樹複本上跑，單一程序，附記憶體監控（MemAvailable 低於 3 GB 就中止 pytest）。

## 結論

Ready to merge：Yes。Critical 0、Important 0、Minor 3。

修正本身只有一行（`tests/onecore_drain_harness.py:220` 的 `speech.types` stub 加上 `SequenceItemT=object`），正確、完整，而且在新舊兩個 NVDA 版本下都通過全套測試。還原修正後 121 個失敗如 spec 所述全部回來，而且只有這一個原因。

## 正確性與完整性

### 修正是否對症

- NVDA `7d25bc76e` 的 `source/synthDrivers/oneCore.py:32` 改成 `from speech.types import SpeechSequence, SequenceItemT`。`from … import` 在載入時就會求值，所以 stub 一定要有這個名字；這是 121 個失敗的唯一原因（見驗證表的第 2 列：121 個 FAILED／ERROR，121 個 `cannot import name 'SequenceItemT'` traceback）。
- `SequenceItemT` 在 oneCore.py 只出現在 `_fixSingleCharacters` 的回傳註解 `Generator[SequenceItemT]`（`:119`）。Python 3.14 不會在定義時求值註解；就算求值，`Generator[object]` 也是合法的。`addon/` 與 `tests/` 裡沒有任何 `isinstance(..., SequenceItemT)` 或其他執行期用法（`grep -rn SequenceItemT addon tests` 只命中這行 stub）。所以 `object` 是安全的值。
- 向後相容：`732d1ce2f` 的 oneCore.py 只 import `SpeechSequence`，多出來的屬性不會被讀到；驗證表第 3、4 列證實舊 NVDA 加不加這行都是 1722 passed。
- 修正放在共用的 `load_onecore` 裡，五組受影響的測試（`test_onecore_segment_drain`、`test_engine_segment_contract[OneCore]`、`test_runtime_drain_integration` 的 `composition` fixture 與 `assemble` 直接呼叫、`test_runtime_completion_policies` 的 `load_installed_engine`）全部經由它恢復；不需要動 `tests/runtime_drain_integration_harness.py:224` 或 `tests/engine_contract_harness.py:145`。

### 其他 stub 有沒有漂移

對照 `git -C ref/nvda diff 732d1ce2f 7d25bc76e -- source/`（82 檔，其中 16 個非 locale 檔）與測試實際載入的 NVDA 檔案：

| 測試載入的真實 NVDA 檔案 | 這次有沒有變 | 結果 |
| --- | --- | --- |
| `synthDrivers/oneCore.py`（`tests/onecore_drain_harness.py:249`、`tests/test_native_strategy_guards.py:153`） | 有（+30／−6） | 除了 `SequenceItemT` 以外，新用到的名字都已在 stub 裡：`CharacterModeCommand` 在 `tests/onecore_drain_harness.py:209` 與 `tests/runtime_drain_integration_harness.py:220` 的 `speech.commands` stub 裡；`Generator` 來自標準庫；`speechXml.XmlBalancerCommand` 只在註解（見 Minor 1）。`_OneCorePort.NVDA_PRIVATES`／`NVDA_OVERRIDES` 列的私名都還在，守門測試通過。 |
| `synthDrivers/sapi5.py`、`_espeak.py`、`espeak.py`（sapi5／espeak harness、guards） | 沒有 | 這三個檔只 import `SpeechSequence`（或完全不碰 `speech.types`），`tests/espeak_drain_harness.py:256` 與 `tests/test_say_all.py:42` 的 stub 不用改。 |
| `gui/settingsDialogs.py`（`tests/test_nvda_settings_copy.py:11`） | 有（39 行） | 三個 hunk 落在 `onDiscard`／`refreshGui`（`:1621-1646`）、瀏覽模式標籤（`:2731`）、`_doOnCategoryChange`（`:6717`）；被指紋的 `updateDriverSettings`（`:1546`）與 `_updateValueForControl`（`:1601`）沒變，測試通過。 |
| `speechXml.py` | 有（+15／−2） | 測試整個 stub 掉（`tests/onecore_drain_harness.py:221`），不載入真檔。新的 `type XmlBalancerCommand = …` 與註解不影響 stub。 |

沒有其他需要補的 stub。

### spec 的產品影響分析

逐項核對後同意 spec 第 4 節，沒有找到遺漏：

- **4.1 OneCore 字元模式。** 路徑確認：`addon/synthDrivers/WorldVoice/__init__.py:88-96` 宣告 `CharacterModeCommand`，所以 NVDA 不會先過濾掉；`runtime/requestBuilder.py:36-52` 只攔 `SelectVoice`／`Pause`，其他指令原樣進 chunk；`driver/OneCore/__init__.py:120-137`（`_OneCoreStrategy.prepare`）與 `:234-237`（`speak` 交給父類）都用 NVDA 自己的 `_OcSsmlConverter`／`_OcPreAPI5SsmlConverter`。內層 `driver/OneCore/driver/__init__.py` 只是 `synthDrivers.oneCore.SynthDriver` 的薄子類，沒有自己的 converter。因此新 NVDA 下 OneCore 語音會以 `<say-as interpret-as="characters">` 加 `"\x1a"` 朗讀字元，與 NVDA 內建 OneCore 一致；舊 NVDA 下 `convertCharacterModeCommand` 回傳 `None`，指令被丟掉。`"\x1a"` 是文字項目，不是 `<mark>`，不會干擾 bookmark／drain。`_fixSingleCharacters` 在每個 `CharacterModeCommand(True)` 後插入，所以就算 WorldVoice 的 pipeline 把 True／False 拆到不同 segment 也沒差。
- **4.2 設定面板。** `WorldVoiceVoiceSettingsPanel`（`VoiceSettingsDialogs.py:14`）繼承 `VoiceSettingsPanel(AutoSettingsMixin, SettingsPanel)`，`onDiscard` 先呼叫 `super().onDiscard()`（`:93-94`）。新的 `onDiscard` 走 `self.sizerDict` 並用 `getattr(self, f"{settingId}List", None)` 保護；WorldVoice 放進 `sizerDict` 的都是 `createDriverSettings` 建立的驅動設定（`punctuationwaitfactor` 等），`punctuationPauseCharactersEdit` 不在 `sizerDict`，不受影響。新的 `refreshGui` 用身分比較後 `settingsSizer.Clear(delete_windows=True)` 再 `makeSettings`，WorldVoice 覆寫的 `makeSettings`（`:15-20`）會重建 `_pipelineSnapshot`、驅動控制項與標點暫停欄位，不會重複。
- **4.3 MathCAT。** `mathPres/MathCAT/speech.py:65-70` 以 `getattr(synth, "RATE_BOOST_MULTIPLIER", 1)` 取值；WorldVoice 有 `rateBoost`（`__init__.py:117-118`、`:431-435`）但沒有該常數，倍率為 1，與這次 NVDA 變更之前所有 synth 的行為相同。不是回歸。
- **4.4 其他。** 把 `addon/` 的頂層 import（`config`、`gui`、`speechXml`、`synthDrivers`、`languageHandler`、`nvwave`、`speech`、`synthDriverHandler`、`extensionPoints` 等）和 16 個非 locale 變更檔交集：`config/__init__.py`（`BASE_ONLY_SECTIONS` 加 `"magnifier"`，WorldVoice 不用這個 section）、`gui/guiHelper.py`（只是把 `wx.siplib.wrappertype` 改成明確 import）、`gui/settingsDialogs.py`（上述）、`speechXml.py`（別名與註解）、`synthDrivers/oneCore.py`（上述）。`speech/`、`synthDriverHandler.py`、`nvwave.py`、`extensionPoints/`、`autoSettingsUtils/`、`languageHandler.py` 在這段範圍沒有變更。RHVoice 內層的 `generateBalancerCommands`（`driver/RHVoice/driver/__init__.py:438-441`）是 `speechXml.SsmlConverter` 的子類覆寫，簽名未變，與 OneCore 的新覆寫無關。
- **4.5 引用。** `addon/synthDrivers/WorldVoice/_speechcommand.py:9-20` 明寫「line numbers from ref/nvda 1406f9f8a」，`speech/speech.py` 的 `shouldMakeLangChangeCommand` 檢查現在在 `:1185-1187`，程式碼相同；`tests/test_nvda_settings_copy.py:13` 的指紋仍符合。同意不改。

### 不加 stub 漂移守門測試的理由

同意計畫的結論。補充兩點：

- 這次的失敗已經是最好的訊號：121 個失敗共用一個 `ImportError`，訊息直接點名缺的名字與 stub 模組，traceback 指到 `oneCore.py:32`。守門測試只能把同一件事多講一次。
- 若要自動化，只能解析 `from speech.types import …` 之類的靜態名字，而 stub 本身是 `load_onecore` 內的行內 `module(...)` 呼叫（`tests/onecore_drain_harness.py:203-247`），守門測試得再抄一份名單，等於多一處會漂移的來源。真正會漏掉的情況（stub 類別缺方法、名字在定義時而非註解裡用到）本來就會以普通測試失敗浮現。

## Findings

### Critical

無。

### Important

無。

### Minor

1. **`tests/onecore_drain_harness.py:220-221`：harness 依賴 Python 3.14 的延遲註解求值（既有，spec 4.6 已記）。** `speechXml` stub 沒有 `SetAttrCommand`（oneCore.py `:95`，舊 NVDA 就有）也沒有新的 `XmlBalancerCommand`（`:115`）。失敗情境：有人在 3.13 或更舊的直譯器跑 `pytest tests`，`load_onecore` 在定義 `_OcSsmlConverter` 時就會以 `AttributeError: module 'speechXml' has no attribute 'XmlBalancerCommand'` 失敗，而且錯誤訊息不會提到直譯器版本。建議：不必在這個分支處理；日後若要去掉這個隱性前提，在 `speechXml` stub 補 `SetAttrCommand=object, XmlBalancerCommand=object` 即可，與這次 `SequenceItemT=object` 同一種做法。
2. **spec 第 4.3 節／開放問題 2：`RATE_BOOST_MULTIPLIER`。** WorldVoice 以 eSpeak 語音開 rate boost 時，MathCAT 的 break 長度不像 NVDA 內建 eSpeak 那樣乘 3。不是回歸，但這是新 NVDA 下 WorldVoice 與內建驅動的一個可見差異。建議維持 spec 的推薦（不改），列入下方待使用者確認。
3. **spec 第 5 節的文字：`git diff --stat master` 列出的檔案。** spec 寫「只有 `tests/onecore_drain_harness.py` 與這份 spec」，實際還有計畫檔（計畫自己有寫對）。純文件描述，不影響合併，不用修。

## 審閱者自行驗證的項目

worktree 的 `ref` 指向 `/workspace/WorldVoice/ref`（`ref/nvda` `7d25bc76e`）。「scratch 新」「scratch 舊」是用 `git ls-files | cp --parents` 複製到 scratchpad 的樹，分別把 `ref` 連到新 NVDA 與 `scratchpad/ref-prev`（`732d1ce2f`）；worktree 的 `ref` 與兩份 NVDA 來源都沒有動。pytest 一律 `python3 -m pytest -q tests -p no:cacheprovider`，單一程序，記憶體監控每 2 秒檢查一次，四次都沒有觸發。

| 項目 | 結果 |
| --- | --- |
| worktree（新 NVDA，含修正）全套 pytest | `1722 passed, 2 warnings in 41.94s`，0 skipped；2 個 warning 是既有的 `codecs.open` DeprecationWarning |
| scratch 新（新 NVDA，`tests/onecore_drain_harness.py` 還原成 master 版本，`diff` 確認逐位元組相同） | `9 failed, 1601 passed, 2 warnings, 112 errors`；121 個 `cannot import name 'SequenceItemT' from 'speech.types'`；分布 `test_onecore_segment_drain` 75 ERROR、`test_engine_segment_contract` 7 ERROR、`test_runtime_drain_integration` 30 ERROR + 3 FAILED、`test_runtime_completion_policies` 6 FAILED，與 spec 第 1 節的表完全一致 |
| scratch 舊（舊 NVDA `732d1ce2f`，含修正） | `1722 passed, 2 warnings in 45.21s` |
| scratch 舊（舊 NVDA，修正還原） | `1722 passed, 2 warnings in 42.27s`（證明舊 NVDA 不需要也不排斥這個名字） |
| `prek run --all-files`（worktree） | 8 個 hook 全數 Passed；之後 `git status --short` 無輸出，hook 沒有改檔 |
| `git diff --check master` | 無輸出 |
| `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py` | 無輸出 |
| `git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 無輸出 |
| `git log master..HEAD --format=%B` | 3 個 commit，英文 `<type>: <summary>`，`grep -ci co-authored-by` 為 0 |
| `git diff --name-only master` | 只有 spec、plan、`tests/onecore_drain_harness.py`；`git ls-files ref` 無輸出；`git diff --cached` 無輸出；`git status --short` 乾淨 |
| `git worktree list` | 四個既有 worktree，審閱沒有新增或刪除 |
| NVDA diff 覆蓋 | `git -C ref/nvda diff --stat 732d1ce2f 7d25bc76e -- source/`：82 檔，16 個非 locale；與 `addon/` 頂層 import 交集為 `config`、`gui`、`speechXml`、`synthDrivers`，逐一核對如上 |
| `SequenceItemT` 的用法 | NVDA：`speech/types.py:22` 定義（兩版都有）、`oneCore.py:32` import、`:119` 註解；`addon/`、`tests/` 無執行期用法 |
| `tests/test_nvda_settings_copy.py` 指紋 | `updateDriverSettings`、`_updateValueForControl` 不在這次 settingsDialogs.py 的三個 hunk 內；測試通過 |
| mutmut | 未跑；沒有碰核心決策模組 |

Linux 上只能驗證到 stub 邊界；Windows 上的 NVDA、OneCore 原生語音、設定對話框都沒有驗證到，下列手動項目仍需使用者在 `7d25bc76e` 或更新的 NVDA 上確認。

## 使用者還沒確認的使用者可見預設

spec 第 6 節的四個開放問題都以推薦預設處理，使用者尚未確認：

1. **OneCore 字元模式跟隨 NVDA（spec 4.1、開放問題 4）。** 新 NVDA 下，透過 WorldVoice 使用 OneCore 語音時，拼讀／逐字移動會以 `<say-as interpret-as="characters">` 加 `"\x1a"` 的方式發音，與 NVDA 內建 OneCore 相同；舊 NVDA 下這個指令是被丟掉的。推薦接受、不在 wrapper 裡剝掉；需在 Windows 以 spec 第 5 節手動項目 1 驗證（審閱游標拼讀、Numpad 1／3 逐字、say-all 索引追蹤）。
2. **不加 `RATE_BOOST_MULTIPLIER`（spec 4.3、開放問題 2）。** WorldVoice + eSpeak 語音 + rate boost 時，MathCAT 的 break 不會像內建 eSpeak 那樣乘 3。推薦維持現狀；若要補，應另開 `fix/` 分支，讓屬性跟著目前預設語音的引擎走。
3. **同時支援 `732d1ce2f`（開放問題 1）。** stub 多一個名字、零成本，已驗證兩版都通過。
4. **`_speechcommand.py:9-20` 的 `1406f9f8a` 行號引用不更新（開放問題 3）。** 引用明確釘在該 commit，內容仍正確。
5. **設定面板的 `onDiscard`／`refreshGui` 新行為（spec 4.2）。** 不需改碼，但 Windows 手動項目 2（改 combo 後 Cancel、開著設定切換合成器再回語音面板，確認沒有例外與重複的「標點暫停字元」欄位）尚未執行。

## 修正記錄

修正者為 sub agent（Opus 5.5），只在 worktree `/workspace/WorldVoice-fix-nvda-stubs` 工作；沒有改產品程式碼，沒有動 `ref/`。

| 項目 | 處理 | commit |
| --- | --- | --- |
| Minor 1：`speechXml` stub 缺 `SetAttrCommand`／`XmlBalancerCommand` | 已修。stub 補上兩個名字，值為 `object`，與 `SequenceItemT=object` 同一種做法。 | `0b8f21a` |
| Minor 2：`RATE_BOOST_MULTIPLIER` | 不修。依指示維持 spec 的推薦，仍列為使用者尚未確認的使用者可見預設（上方第 2 項）。若要補，另開 `fix/` 分支。 | — |
| Minor 3：spec 第 5 節的 `git diff --stat master` 描述 | 已修。改為列出 harness、spec 與計畫，並註明 review 紀錄與 Minor 1 的測試是 review 之後才加入的；第 4.6 節同時補一句，說明這個隱性前提已經處理。 | `36905db` |

Minor 1 的會失敗的測試：環境裡只有 Python 3.14，沒有 3.13 直譯器，所以改用 `inspect.get_annotations`（3.14 預設 `Format.VALUE`）求值載入後 oneCore.py 裡每個類別與函式的註解，等同 3.13 在 `def` 時做的事。新測試 `tests/test_onecore_segment_drain.py::test_stubs_cover_names_that_onecore_annotations_use` 在 stub 補名字之前：

- 新 NVDA `7d25bc76e`：失敗，列出 `_OcSsmlConverter.convertLangChangeCommand`（`SetAttrCommand`）與 `_OcSsmlConverter.generateBalancerCommands`（`XmlBalancerCommand`）兩項。
- 舊 NVDA `732d1ce2f`：失敗，只列出 `SetAttrCommand` 一項。

補上之後兩版都通過。這個測試不依賴直譯器版本，以後 NVDA 在註解裡用到新的名字而 stub 沒跟上時，在 3.14 上也會失敗。

驗證（pytest 一律單一程序，附記憶體監控，MemAvailable 低於 3 GB 即中止，沒有觸發）：

| 項目 | 結果 |
| --- | --- |
| worktree（新 NVDA `7d25bc76e`）全套 pytest | `1723 passed, 2 warnings`，0 skipped（基準 1722，多出的 1 個是新測試） |
| scratchpad 樹複本（`git ls-files \| cp --parents`，`ref` 連到 `scratchpad/ref-prev`，舊 NVDA `732d1ce2f`）全套 pytest | `1723 passed, 2 warnings`，0 skipped |
| `prek run --all-files` | 8 個 hook 全數 Passed |
| `git diff --check` | 無輸出 |
| 受保護路徑的兩個指令 | 皆無輸出 |
