# Voice panel creation order Review 紀錄

日期：2026-10-22。分支：`feat/voice-panel-creation-order`（`c6a71e4..d7b4945`，6 個 commit），worktree `/workspace/WorldVoice-feat-create-order`。
依據：

- 規格 `docs/superpowers/specs/2026-10-22-feat-voice-panel-creation-order-design.md`（使用者決定 D1–D4；D5 由實作者決定）
- 計畫 `docs/superpowers/plans/2026-10-22-feat-voice-panel-creation-order.md`（Review Focus 1–5）
- 進度帳本 `.superpowers/sdd/2026-10-22-feat-voice-panel-creation-order/progress.md`（5 個 `Ruling:`）
- 使用者決定（2026-10-22）：非驅動控制項在表格位置建立、`MoveAfterInTabOrder` 移除、以繼承取代複製的 `createDriverSettings`、N5／I1／`depends_on`／`onSave`／`onDiscard`／RateBoost 與 Inflection 原位出現都維持。

流程：審閱者 Fable 5.1，唯讀；測試、還原實驗、種子突變、假物件嚴格化實驗與 mutmut 都在 scratchpad 的暫時 worktree（`review/wt-revert`、`review/wt-mut`，審完已移除）進行，單一 pytest 行程加 3 GB MemAvailable 記憶體監控。NVDA 參考 `ref/nvda` 為 `7d25bc76e`，與 spec 相同。

`file:line` 以 `d7b4945` 為準；NVDA 的行號以 `ref/nvda` `7d25bc76e` 為準。

## 結論

Ready to merge：**是。** Critical 0、Important 0、Minor 5。

程式與使用者的四項決定全部相符：

- **建立順序 = Tab 順序 = 版面順序 = 表格順序，而且每個標籤緊接在控制項前面**（`VoiceSettingsDialogs.py:101-148`）。四種情境（第一次建置、換語音、WorldVoice→WorldVoice 重建、其他合成器→WorldVoice 重建）都有測試，把本分支的程式還原成 master 後四個情境全部失敗（見驗證表）。
- **繼承取代複製**：`createDriverSettings` 與 AST 等價守門都已移除；override 先做 pre-pass 再呼叫 `super().updateDriverSettings`，NVDA 端沒有任何複製的程式碼。
- **N5、I1、`depends_on`、`onSave`／`onDiscard`、RateBoost／Inflection 原位**：對應測試都在，而且各自的種子突變都被抓到（12 個種子突變 10 個被殺，2 個是等價突變，見 M3）。
- 五個 `Ruling:` 都合理；Ruling 2（放在「前一個做出或走訪過的列」之後，拿掉 `voice_placements`）比 spec 原來的 anchor 作法更正確：版面順序依建構就等於建立順序，連 anchor 驅動控制項建立失敗的情況都一致。

Linux 上無法驗證的只有一件事：真實 wx MSW 的 `MoveAfterInTabOrder` 確實只改 wx 的子視窗串列（Tab 順序）而不動 HWND z-order。這與 wxWidgets `wxWindowBase::DoMoveInTabOrder` 的實作（只改 parent 的 `wxWindowList`；MSW port 沒有覆寫）以及使用者在 master 上的觀察（Tab 順序正確、物件導覽卻在最後）一致，但本機沒有 wx，仍以 Windows 手動項目 1 為準。

## Critical

無。

## Important

無。

## Minor

### M1. 失敗 maker 的測試模型比真實 NVDA 樂觀：真實 maker 會留下孤兒視窗

- **位置：** `tests/test_voice_settings_panel.py:613-632`（`Panel._createNewControl` 直接跳過 `nummod`，不建任何視窗）。NVDA 端 `settingsDialogs.py:1489-1503`（`_makeStringSettingControl` 先建 `LabeledControlHelper`——標籤與 Choice 兩個視窗——才讀 `getattr(settingsStorage, setting.id)`）、`:1435-1456`（slider 同樣先建再 `SetValue(getattr(...))`）、`:1525-1539`（checkbox 亦然）、`:1577-1582`（`_createNewControl` 接住 `UnsupportedConfigParameterError` 後不放進 sizer）。
- **情境：** 若某個列在 `allSupportedSettings` 的驅動設定在讀值時丟 `UnsupportedConfigParameterError`，真實 NVDA 會留下已建立、卻不在任何 sizer 裡的標籤與控制項（這是 NVDA 自己的行為，master 也一樣）。此時 HWND 順序是「inflection、孤兒 nummod 標籤、孤兒 nummod 清單、Group size」，與測試斷言的「Group size 緊接 inflection」不同；Tab 順序中那個孤兒控制項也會留在串列尾端。
- **影響：** 沒有。WorldVoice 列出的設定沒有一個會在讀值時丟這個例外（`__init__.py:395-396`、`:431-432` 直接回傳語音實例的屬性），而且 override 對這種情況的處理（放在前一個真正做出的列之後）仍是能做到的最好結果。
- **建議：** 在該測試加一行註解說明這是理想化的失敗模型（NVDA 的 maker 真正失敗時還會留下孤兒視窗，WorldVoice 無法也不需要處理），避免下一位讀者把它當成真實 NVDA 行為的保證。不修也可以。

### M2. 假物件 `Sizer.Insert` 與 `MoveAfterInTabOrder` 比 wx 寬鬆

- **位置：** `tests/ui_harness.py:238-240`（`Insert` 用 `list.insert`，索引超過長度時 Python 會靜默附加在尾端；wx release build 的 `wxSizer::Insert` 遇到 `index > count` 會 `wxCHECK_MSG` 直接回傳、**不插入**，列就消失）、`:102-109`（`MoveAfterInTabOrder` 的 `other` 不是同一個 parent 的子視窗時靜默不動；wx 會 assert）。
- **審閱者實測：** 在暫時 worktree 把這兩處改成 assert（`0 <= index <= len(items)`、`other` 必須是同一個 parent 的子視窗），跑六個面板相關測試檔 126 passed——本分支沒有踩到這兩種情況（分析也確認 `_placePipelineRows` 的 `index + 1` 永遠 ≤ Detach 後的長度，因為被移動的列一定在 `previousRow` 之後）。
- **建議：** 把那兩個 assert 留進 harness，便宜而且是前兩輪 review 發現的同類問題（假物件把真實 wx 的失敗藏起來）的預防。

### M3. 兩個分支在真實情境下等價、但沒有測試鎖住

- `VoiceSettingsDialogs.py:137` 的 `setting.id != changedSetting`：種子突變拿掉它後 56 個面板測試全過。只有「`changedSetting` 已列出卻不在 `sizerDict`」才會走到，而 `changedSetting` 只會是已經有控制項的 `voice`（`settingsDialogs.py:1343-1350`），所以實務上是死碼。留著與 NVDA 的 `updateDriverSettings` 對稱沒問題；要鎖住的話，用 `Driver(ALL - {"rateBoost"})` 建面板後呼叫 `updateDriverSettings(changedSetting="rateBoost")`，斷言 `"rateBoost" not in panel.sizerDict`。
- `VoiceSettingsDialogs.py:127` 的 `absent and`：拿掉後也全過。`_makePipelineControls` 本來就只做 `_voiceControl` 為 `None` 的控制項，`absent` 只省下一次 `pipeline_settings.get()`；等價突變，不需處理。

### M4. 版面：WorldVoice 的列沒有 NVDA 驅動列的 10px 下邊距（master 既有）

- **位置：** `VoiceSettingsDialogs.py:159-160`（`BoxSizerHelper.addItem` 不帶 `border`／`flag`）對照 NVDA `settingsDialogs.py:1585-1590`（`Insert(..., border=10, flag=wx.BOTTOM)`）與 `:1690-1699`（NVDA 自己的 `settingsSizerHelper` 第一個項目前沒有 spacer）。
- **情境：** 表格的最後一個 Voice 項目是 Punctuation pause characters，它緊接著 NVDA 的「Automatic language switching」核取方塊，中間是 0px 而不是驅動列之間的 10px。master 把同一列移到同一個位置，所以不是回歸，純視覺。
- **建議：** 不在本分支處理。日後若要修，在 `_moveSizer` 之後或 `make_control` 的 `addItem` 補 `border=10, flag=wx.BOTTOM`，並在 harness 的 `SizerItem` 記錄 flag 以便斷言。

### M5. 守門：`BoxSizerHelper.addItem` 的 spacer 規則沒有指紋

- **位置：** `tests/test_nvda_settings_copy.py:17-33`（指紋只涵蓋 `AutoSettingsMixin` 的四個方法）。`VoiceSettingsDialogs.py:158-159` 的「一個 helper 一個控制項，第一個項目沒有 spacer，移動列不留 spacer」依賴 NVDA `guiHelper.py:384`、`:412-414`（`shouldAddSpacer = self.hasFirstItemBeenAdded`）。
- **情境：** NVDA 若改成每個項目前都加 spacer，移動後會在 NVDA 自己的控制項前留下孤兒 spacer；現有測試的 `"<spacer>" not in names` 只在假物件上跑，抓不到 NVDA 的改動。這是 master 既有的依賴，不是本分支新增。
- **建議：** 可選。加一個 `BoxSizerHelper.addItem` 的指紋（同 `method(path, cls, name)` 的作法，`guiHelper.py`），註解寫明要複查的是 spacer 規則。

## 計畫 Review Focus 與 Ruling 的逐項檢查

| 項目 | 檢查結果 |
| --- | --- |
| RF1 換語音：不建、不移、三種順序不變 | `test_voice_panel_orders_follow_the_table[voice switch]` 斷言 `panel.children == before`；程式路徑：所有列都在 `sizerDict`，`absent` 為 False，`placements` 為空（`:120-147`）。 |
| RF2 WorldVoice→WorldVoice 重建、`lastControl` 指向已銷毀視窗 | 假物件的 `MoveAfterInTabOrder` 在 `other` 已銷毀時 raise（`ui_harness.py:103-105`），`_createNewControl` 用 `if self.lastControl:` 跳過；override 只對 `lastControl` 賦值（`:164`），從不讀它。`[worldvoice rebuild]` 與 `test_a_rebuild_for_worldvoice_from_worldvoice_places_the_controls_again` 通過。 |
| RF3 anchor 驅動控制項建立失敗 | `test_a_follower_of_a_failed_driver_control_follows_the_row_before`：`previousRow = self.sizerDict.get(setting.id, previousRow)`（`:139`）讓列跟著前一個真正做出的列。見 M1 的保留意見。 |
| RF4 第一個項目沒有驅動設定 | `followers[None]` 在迴圈後做（`:146`），`previousRow` 是最後一列；`test_a_first_entry_without_a_driver_setting_comes_after_the_driver_rows` 斷言三種順序都在驅動列後、NVDA 控制項前。 |
| RF5 沒有 `allSupportedSettings` 的其他合成器 | `:113-117` 退回 `supportedSettings`；`test_another_synth_voice_switch_adds_no_control` 與 `[other synth rebuild]`。 |
| Ruling 1 三個指紋合成一個 parametrize | 同樣三個案例，合理。 |
| Ruling 2 放在前一個做出／走訪的列之後，移除 `voice_placements` | 合理且更正確（見結論）。移除的 6 個測試由 `test_creation_followers_*` 4 個例子與 1 個 property 測試取代，property 測試直接以表格位置當 oracle，不再依賴被移除的函式。 |
| Ruling 3 helper 形狀改名 | 只是簽章差異。 |
| Ruling 4 移除 `Control.tab_after` | 沒有測試再讀它；新的 `before()` 同時檢查 `children` 與 `tab_order`。 |
| Ruling 5 總數 2100 而非 2106 | 2100 − 1（AST 守門）+ 4 + 3 − 6（`voice_placements`）= 2100，相符。 |

## 守門測試的評估

- 四個指紋（`_createNewControl`、`updateDriverSettings`、`refreshGui`、`_updateValueForControl`）加三個結構檢查（maker 的 `lastControl` 鏈、`VoiceSettingsPanel.makeSettings` 第一句、`StringDriverSettingChanger.__call__`）涵蓋 override 依賴的每一個 NVDA 內部行為：插入索引、不重複建立、隱藏與更新、重建時銷毀視窗、Tab 鏈、驅動控制項先於 NVDA 自己的控制項、換語音會進 override。
- `test_nvda_makers_chain_last_control` 的 `(index,) = [...]` 在 NVDA 拿掉 `if self.lastControl:` 時會以 `ValueError` 失敗，仍然擋得住。
- 移除 AST 等價守門是安全的：`createDriverSettings` 已不存在，override 直接呼叫 NVDA 的方法，不可能再漂移。
- 缺口只有 M5 的 spacer 規則（master 既有）。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 完整測試 | `python3 -m pytest -q -p no:cacheprovider tests`（單一行程，3 GB 記憶體監控） | 2100 passed、0 skipped、2 個既有 DeprecationWarning（`codecs.open`，與本分支無關）；監控未觸發 |
| prek | `prek run --all-files`（在 HEAD 的 scratch 複本） | 8 個 hook 全數 Passed，沒有檔案被修改 |
| 空白 | `git diff --check master` | 無輸出 |
| 受保護路徑 | `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 皆無輸出 |
| commit 訊息 | `git log master..HEAD` | 6 個 commit，英文 `<type>: <summary>` 加原因，無 `Co-Authored-By` |
| 翻譯 | `git diff --stat master -- addon/locale '*.po' '*.pot'` | 無變更；diff 中沒有新增或修改的 `_()` 字串 |
| 還原實驗 | 暫時 worktree 在 `d7b4945` 上把 `VoiceSettingsDialogs.py` 與 `panelLayout.py` 換回 master，跑 4 個面板測試檔 | 12 failed、47 passed：`test_voice_panel_orders_follow_the_table` 四個情境全部失敗，另 8 個 Tab／children 相鄰斷言、helpers-gone、Review Focus 3／4 測試失敗 |
| 種子突變（`VoiceSettingsDialogs.py`，12 個） | 不設 `lastControl`、不跑版面 pass、不追蹤 `previousRow`（驅動列／活的非驅動列各一）、拿掉 N5 閘門、拿掉 I1 重設、`index` 不 `+1`、不做 `None` 群組、`followers` 只取 `None`、拿掉 `listed` 檢查、拿掉 `!= changedSetting`、拿掉 `absent and` | 10 個被殺（各自由 1 個對應測試首先抓到）；2 個存活且確認等價（M3） |
| mutmut `creation_followers` | scratch 複本把 `source_paths` 縮到 `panelLayout.py`，`mutmut run --max-children 3 "*creation_followers*"`，記憶體監控 | 11 個 mutant 全部被殺（🎉 ×11，無 survived／timeout），與帳本的 11/11 相符；監控未觸發 |
| 假物件嚴格化 | `Sizer.Insert` 索引範圍 assert、`MoveAfterInTabOrder` 同 parent assert | 6 個面板測試檔 126 passed（M2） |
| 假物件保真度對照 NVDA | `LabeledControlHelper` 先標籤後控制項（`guiHelper.py:289-290`）；`addItem` 第一項不加 spacer（`:384`、`:412`）；三個 maker 的 `MoveAfterInTabOrder`／`lastControl`（`:1457-1459`、`:1512-1514`、`:1541-1543`）；`_createNewControl` 的 `Insert(len(sizerDict)-1)`（`:1585-1590`）；checkbox 列是視窗本身（`:1544`）；`refreshGui` 清 `sizerDict`、`Clear(delete_windows=True)`、不動 `lastControl`（`:1639-1645`）；`Sizer.Clear` 連標籤一起銷毀並從 `children`／`tab_order` 移除 | 全部相符。`children` 只在建立時附加、`MoveAfterInTabOrder` 只動 `tab_order`，對應 wx 的 HWND 順序與 `wxWindowList`（Linux 無 wx，無法執行驗證，見結論） |
| 真實 wx 的 Tab 順序推演 | 以 NVDA 的 label→control→`MoveAfterInTabOrder` 序列手算 `wxWindowList` | 可聚焦控制項順序為 C1、C2、…、CG（我們的）、C4、…、NVDA 自己的控制項；標籤被擠到後面但不可聚焦，不影響 Tab；HWND 順序維持建立順序 |
| 版面移動的索引 | 分析 `_placePipelineRows`：被移動的列永遠在 `previousRow` 之後（驅動列插在 `len(sizerDict)-1`，一定在我們的列之前），Detach 後 `index + 1` 仍在範圍內；`placements` 依建立順序處理，鏈的前一列已先放好 | 正確；無死的 `SizerItem`（`_moveSizer` 先讀再 Detach，`_rowIndex` 每次重新計算）、無孤兒 spacer（每個控制項一個 helper） |
| spec／程式引用的 NVDA 行號 | `settingsDialogs.py:1343-1350`、`:1382`、`:1457-1459`、`:1546-1591`、`:1633-1646`、`:1686-1699`；`guiHelper.py:288-291` | 與 `7d25bc76e` 相符 |
| 暫時 worktree 與 scratch 檔 | `git worktree list` | 審完已移除 `wt-revert`、`wt-mut` 與 scratch 腳本 |

## 使用者還沒確認的使用者可見預設

1. **D5（實作者決定）：版面仍保留一次「只動版面」的移動**（`_placePipelineRows`，`VoiceSettingsDialogs.py:170-179`）。這是 NVDA `len(sizerDict) - 1` 插入索引的必然結果，不改變使用者看到或聽到的任何東西；審閱者認為合理。
2. **第一個 Voice 項目沒有驅動設定時的位置**（RF4）：建立在所有驅動列之後、NVDA 自己的控制項之前。真實表格沒有這種項目（守門測試禁止），只在 synthetic 表格出現。
3. **Spin 控制項在物件導覽中的呈現**（Windows 手動項目 1）：`SelectOnFocusSpinCtrl` 在 MSW 是兩個 HWND（編輯區與上下按鈕），物件導覽可能把上下按鈕當成緊接在編輯區後的另一個物件；這與 master 相同，不是本分支造成，但手動驗證時請注意預期是「Number mode → Group size 標籤 → Group size 編輯區（→ 上下按鈕）→ Group wait factor」。
4. **M4 的 0px 間距**（master 既有）：Punctuation pause characters 與 Automatic language switching 之間沒有 10px 下邊距。

## Windows 手動項目（Linux 無法驗證）

沿用 spec §7 的五項。其中第 1、2 項是本分支的核心主張（HWND 順序 = Tab 順序 = 表格順序、標籤緊接控制項）在真實 wx MSW 上唯一的驗證方式。
