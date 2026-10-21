# Settings order from the pipeline table Review 紀錄

日期：2026-10-21。分支：`feat/settings-order-from-table`（`658f8b9..b8498e6`，19 個 commit），worktree `/workspace/WorldVoice-feat-order`。
依據：

- 規格 `docs/superpowers/specs/2026-10-21-feat-settings-order-from-table-design.md`（使用者決定 Q1–Q5、標籤規則、N1、N5；N2–N4、N6–N8 採建議預設）
- 使用者決定摘要 `scratchpad/order-decisions.md`
- 計畫 `docs/superpowers/plans/2026-10-21-feat-settings-order-from-table.md`（Review Focus 1–5）
- 進度帳本 `.superpowers/sdd/2026-10-21-feat-settings-order-from-table/progress.md`（13 個 `Ruling:`）
- 批次 review：batch 1（Opus，B1-M1–M9，無 Critical／Important），回報已修

流程：審閱者 Fable 5.1，唯讀；測試、還原實驗、種子突變與假物件保真度實驗都在暫時 worktree（`scratchpad/review/wt`、`wt-master`、`wt-revert`，審完已移除）進行，單一 pytest 行程加 3 GB MemAvailable 記憶體監控。NVDA 參考 `ref/nvda` 為 `7d25bc76e`。

`file:line` 以 `b8498e6` 為準。

## 結論

Ready to merge：**建議先修 Important 1（一行修法），再 merge。** Critical 0、Important 1、Minor 5。

程式與使用者的 Q1–Q5、標籤規則、N1、N5 全部相符：兩個面板的控制項順序與 Tab 順序、設定環順序（只有 Global wait factor 與 Group wait factor 移動）、儲存鍵與 confspec 不變、`numlan` 仍是 NVDA 儲存的驅動設定且驅動屬性完好、`panel_scale=10`、`depends_on` 啟用規則、共用標籤與 zh_TW 翻譯都驗證過。計畫 Review Focus 五項各有測試且都能抓到對應錯誤；13 個 `Ruling:` 都合理（Ruling 5、7 與使用者的 N5 一致）；B1-M1–M9 都確實修好；三個聲稱等價的 mutant 確認等價。

唯一要先修的是 Voice 面板在 NVDA `refreshGui` 重建時仍然會碰到上一次建置、已被 wx 銷毀的控制項（I1）。這在 master 就存在（審閱者用嚴格版假物件在 master 上重現同樣的兩條路徑），不是本分支造成的回歸；但本分支的 N5 設計（spec §5.8）明確聲稱「nothing refers to windows of an earlier build」而實際只重設了兩個非驅動屬性、而且重設得太晚，手動項目 6（開著對話框切換合成器）正是會踩到的情境，修法只要一行，所以列為 Important。

## Critical

無。

## Important

### I1. Voice 面板重建（NVDA `refreshGui`）時使用上一次建置已銷毀的控制項，真實 wx 會丟 `RuntimeError`

- **位置：** `addon/synthDrivers/WorldVoice/VoiceSettingsDialogs.py:93-96`（`_voiceControl` 只用 `getattr(..., None)`）、`:44-50`（`_bindControllers` 對取得的控制項呼叫 `Bind`）、`:61-74`（`_readController` 呼叫 `GetValue`／`GetSelection`）、`:78-86`（`_applyDependencies` 呼叫 `Enable`）、`:107-110`（N5 只把非驅動屬性設為 `None`，而且是在 `super().makeSettings` 之後）、`:266-268`（`_updateValueForControl` 尾端在 `super().makeSettings` 期間就呼叫 `_applyDependencies`）。NVDA 端 `ref/nvda/source/gui/settingsDialogs.py:1633-1646`（`refreshGui`：`sizerDict.clear()`、`settingsSizer.Clear(delete_windows=True)`、再跑 `makeSettings`，**不會**清掉 `nummodList`、`punctuationpauseenabledCheckbox`、`groupSizeSpin` 這些屬性）、`:1229-1245`（換合成器後 `onPanelActivated` 觸發）、`ref/nvda/source/synthDriverHandler.py:529-537`（`setSynth` 一律先 terminate 再建新實例，即使選的是同一個合成器）。
- **機制：** `wx.Sizer.Clear(delete_windows=True)` 會遞迴 `Destroy()` 所有子視窗；wxPython 之後對該 Python 物件呼叫任何方法都丟 `RuntimeError: wrapped C/C++ object of type … has been deleted`（物件本身變成 falsy，這正是 NVDA `if self.lastControl:` 依賴的行為）。本分支有兩條路徑會碰到：
  1. **WorldVoice → 其他合成器（N5 的情境）：** 新的 `makeSettings` 不再建立 `nummodList`／`punctuationpauseenabledCheckbox`，但舊屬性還在。`_bindControllers`（`:44-50`）取到舊的 `nummodList` 就呼叫 `.Bind(...)` → RuntimeError，`makeSettings` 中斷，Voice 面板只建到一半。
  2. **WorldVoice → WorldVoice（在「變更合成器」對話框按 OK，合成器仍是 WorldVoice）：** `createDriverSettings` 建好新的驅動控制項後，`super().makeSettings` → `updateDriverSettings` → `_updateValueForControl("nummod")` → `_applyDependencies`（`:266-268`）→ `_voiceControl(group_size)` 取到**舊的** `groupSizeSpin`（`_addPipelineControls` 還沒跑，`:107-108` 的重設還沒發生）→ `.Enable(...)` → RuntimeError。
- **審閱者實測：** 在暫時 worktree 把假物件 `Control` 改成「`destroyed` 後任何方法都 raise RuntimeError」（與 wxPython 一致），跑 `tests/test_voice_settings_panel.py`：既有的 `test_a_rebuild_for_another_synth_drops_the_worldvoice_controls` 立刻在 `_bindControllers`（`VoiceSettingsDialogs.py:50`）失敗；再加一個 WorldVoice→WorldVoice 的 `refreshGui` 測試，在 `_applyDependencies`（`:86`）失敗。把同樣的嚴格假物件套到 **master**（`wt-master`），兩條路徑同樣失敗（`_bindPunctuationPauseEnabledToggle` 與 `_applyGroupControlsState`），所以是既有問題，不是回歸。
- **失敗情境（Windows）：** 開啟 NVDA 語音設定、按「變更…」、選 eSpeak NG（或維持 WorldVoice）按 OK → log 出現 RuntimeError，Voice 面板缺控制項或完全空白；spec §10.6 手動項目 6 就是這個操作。
- **建議修法（一行，涵蓋三條路徑）：** `_voiceControl` 把 falsy（已銷毀）的視窗當成不存在：

  ```python
  def _voiceControl(self, spec):
      name = driver_attribute(spec) if spec.driver_id is not None else voice_attribute(spec)
      control = getattr(self, name, None)
      # wxPython: a destroyed window is falsy (NVDA's "if self.lastControl:" relies on it).
      return control if control else None
  ```

  或者在 `makeSettings` 一開始（`createDriverSettings` 之前）就把表格裡每個 entry 的屬性（驅動與非驅動）都設為 `None`。測試：
  1. `tests/ui_harness.py` 的 `Control` 在 `destroyed` 後對 `Enable`／`GetValue`／`Select`／`Bind`／`MoveAfterInTabOrder` 等方法 raise `RuntimeError`（像 `SizerItem._alive`，`:179`，對 Detach 後的讀取那樣）。這樣既有的 `test_a_rebuild_for_another_synth_drops_the_worldvoice_controls` 就會先紅。
  2. 新增 `test_a_rebuild_for_worldvoice_from_worldvoice_places_the_controls_again`：`open_panel(Driver(ALL, nummod="group"))`，換成另一個 `Driver(ALL, nummod="value")`，`refreshGui()`，斷言 Group size 在 `nummod` 之後、`groupSizeSpin` 不是舊物件、群組控制項已停用。
  3. spec §5.8 的「sets their attributes to None, so nothing refers to windows of an earlier build」改成描述新的規則（見 M5）。

## Minor

### M1. 假物件保真度：`tests/ui_harness.py` 的 `Control` 在 `destroyed` 後仍可正常呼叫方法

- `tests/ui_harness.py:33`、`:42-44`（只有 `__bool__` 反映銷毀）、`:83-85`（`Enable` 不檢查）、`:251-259`（`Sizer.Clear` 只設旗標）。真實 wxPython 會 raise；這個落差正是 I1 被 `test_a_rebuild_for_another_synth_drops_the_worldvoice_controls`（`tests/test_voice_settings_panel.py:417`）和 `test_a_rebuild_for_worldvoice_places_the_controls_again`（`:404`）漏掉的原因。前一個功能的 review 也發現過同類問題（`SizerItem` Detach 後讀取），當時的修法是讓假物件 raise，這次比照即可（I1 的測試 1）。
- 其餘假物件對照 `ref/nvda/source/gui/guiHelper.py:375-440`（`addItem` 的 spacer 規則、`addLabeledControl` 把 `labeledControl.sizer` 加進 sizer）、`settingsDialogs.py:1457-1459`／`:1512-1514`／`:1541-1543`（`MoveAfterInTabOrder`）、`:1577-1590`（`_createNewControl` 的 `Insert(len(sizerDict)-1)`）、`:1517-1544`（checkbox 列是視窗本身）都相符；新的 `Spacer` 模型（`GetSizer()`／`GetWindow()` 都是 `None`）與 wx 的 spacer item 一致，`_rowIndex`（`VoiceSettingsDialogs.py:142-152`）比對 `is row` 不會誤中 spacer。

### M2. 表格守門測試的幾個缺口

- `tests/test_settings_table_guard.py:145-158`（`check_sentence_case`）不擋結尾的「:」：一個 `label="New wait factor:"` 的新 entry 會通過全部檢查，但 Speech Pipeline 面板與 NVDA Voice 面板都會再加一個冒號，顯示成 `New wait factor::`。建議加一條 `label.endswith(":")` → 報錯。
- 沒有檢查 `min_value <= default <= max_value` 與 `min_value < max_value`：`default=500` 或 `max_value=10, min_value=50` 都通過，而 `confspec`（`settings.py:98-104`）會產生 configobj 無法驗證的 `integer(default=500, min=0, max=100)`，NVDA 載入設定時才出錯。
- `min_step` 與 `panel_scale` 沒有一致性檢查（`check_scale`，`:122-142`）：`panel_scale=10, min_step=1` 會讓 Voice 面板 slider 以 1 為步進、Speech Pipeline 面板以 10 為步進。
- `check_attribute_names`（`:177-187`）對 `control=None` 或 `control="text"` 的驅動 entry 會在 `layout.driver_attribute`（`panelLayout.py:122`，`_DRIVER_SUFFIXES[...]`）丟 `KeyError` 而不是回報訊息；因為 `check_control_known`／`check_placement` 會另外抓到，守門仍然擋得住，只是訊息不清楚。建議在該檢查裡跳過 `spec.control not in _DRIVER_SUFFIXES` 的 entry。
- 審閱者另外試了 21 個畸形 entry（見驗證表）；其餘會造成面板出錯的情況（缺 `control`、驅動 entry 用 spin／text、choice 沒有 `choices`、controller 在後面、checkbox controller 期待非 bool、ordering-only 進 Speech Pipeline 面板、第一個 Voice entry 沒有驅動列、大小寫錯）都被擋下。

### M3. 兩個分支在真實表格下等價、但沒有測試鎖住的判斷

- `VoiceSettingsDialogs.py:165`（`onSave` 過濾 `value is not None`）：種子突變「直接 `update(**values)`」在完整測試下存活。真實表格的非驅動 Voice 控制項只有 spin 與 text，不會讀到 `None`；spec §5.10 也寫明「there is none today」。若要鎖住，用合成表格放一個非驅動 choice、選取 −1 再 Save，斷言該鍵不在 `update` 裡。
- `VoiceSettingsDialogs.py:178`（`onDiscard` 的 `or not self._isWorldVoice()`）：種子突變拿掉這個條件也存活。只有「面板為 WorldVoice 建好（有 snapshot）、合成器換掉、NVDA 還沒重建就 Cancel」才會走到，而 NVDA 換合成器後立刻 `onPanelActivated` 重建，實務上到不了。master 同樣沒有測試，不擋 merge。
- `speechSettingsDialog.py:184`（`onSave` 的 `if spec.pipeline_config`）：突變成 `if True` 存活。守門測試 `check_ordering_only` 禁止 ordering-only entry 出現在 Speech Pipeline 面板，所以這個條件在真實表格下是死碼；留著當防線沒問題，但可以在註解寫明它靠守門測試保證。

### M4. `nvda.po` 新條目沒有 `#:` 參照行，舊條目的參照行過時

- `addon/locale/zh_TW/LC_MESSAGES/nvda.po:569-603`：9 個新條目只有 `#. Translators:` 註解、沒有 `#:` 來源行；既有條目的 `#:` 行號本來就過時（前一輪 review M2 已指出）。`msgfmt --check` 通過，功能無影響。建議下次打包時用 `scons pot` + `msgmerge` 一次更新。

### M5. spec §5.8 對「另一個合成器」的描述與程式不符（文件）

- `docs/superpowers/specs/2026-10-21-feat-settings-order-from-table-design.md:346`：「`_addPipelineControls` … sets their attributes to `None`, so nothing refers to windows of an earlier build … neither hiding nor destroying is needed」。實際上驅動控制項的屬性（`nummodList` 等）沒有重設，而且非驅動屬性的重設在 `super().makeSettings` 之後才發生（I1）。修 I1 時一併改寫這段，並在 §10.6 手動項目 6 補上「WorldVoice → WorldVoice（按 OK 不換）」的情況。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 完整測試（§7） | `guard.sh … python3 -m pytest -q -p no:cacheprovider tests`（單一行程，MemAvailable < 3 GB 即中止；`ref` → NVDA `7d25bc76e`） | **2070 passed、0 skipped**，2 warnings，57.04s；與帳本一致 |
| prek（§7） | `prek run --all-files` | 8 個 hook 全數 Passed，worktree 無變動 |
| 空白檢查 | `git diff --check master` | 無輸出 |
| 受保護路徑 | `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 兩者皆無輸出 |
| Co-Authored-By | `git log master..HEAD --format='%H %b' \| grep -i co-authored` | 0 筆 |
| 跨驅動 import | grep `pipelineControls`／`panelLayout`／其他驅動 package 於 `addon/synthDrivers/WorldVoice/driver/` | 無；新模組只被 `VoiceSettingsDialogs.py` 與 `speechSettingsDialog.py` import |
| 翻譯 | `msgfmt --check -o /dev/null addon/locale/zh_TW/LC_MESSAGES/nvda.po`；以腳本比對 `addon/**/*.py` 的 `_()` msgid 與 `.po` | 通過；spec §7.1 的 9 個新／改 msgid 都有 zh_TW（數字模式(&M)、數字語言(&L)、項目停頓參數、忽略在數字間的逗號、作用範圍、每組位數、標點停頓字元、套用語音字典、語音檢視器），用詞與既有條目一致；21 個刪除的 msgid 在 `addon/` 裡已無 `_()` 呼叫（`test_changed_label_strings_have_translator_comments` 也鎖住）；沒有任何仍在使用的 msgid 失去 zh_TW 條目；`# Translators:` 註解齊全且正確指名面板（scope 只寫 Speech Pipeline、number language 只寫 voice settings panel） |
| 控制項順序與 Tab 順序 | 讀 `tests/test_settings_order.py`（`VOICE_KEYS`、`test_voice_panel_tab_order_follows_the_table`、`test_pipeline_panel_controls_follow_the_table`）與 `tests/test_settings_panels.py:52-66`（標籤清單） | Voice 面板 14 列、Speech Pipeline 面板 14 列（含 scope、無 numlan）都等於 spec §6.1／§6.2；Tab 鏈同序；種子突變「不呼叫 `MoveAfterInTabOrder`」「插在 anchor 前面」「`_rowIndex` 只比對 sizer」都被殺 |
| 設定環 | `test_ring_follows_the_table_after_the_standard_settings`、`test_ring_names_follow_the_label_rule`；與 spec §3.2 的 master 順序逐項比對 | 新順序 uwv, globalwaitfactor, numlan, nummod, groupwaitfactor, numberwaitfactor, item, sayall, chinesespace, ppe, rpc, pwf：恰好只有 Global wait factor 與 Group wait factor 移動；cni 仍不在環裡；環名 Number language／Number mode／Item wait factor |
| 儲存鍵、confspec、numlan | `test_table_drives_fields_defaults_keys_and_confspec`、`test_number_language_is_ordering_only`、`test_number_language_is_a_driver_setting_nvda_stores`；讀 `settings.py:273-277`、`__init__.py:103-124`、`:497-502` | `PIPELINE_CONFSPEC` 同樣 14 鍵、字串不變；`number_language` 不在 `PIPELINE_SETTING_BY_KEY`／`CONFSPEC`／`CONFIG_KEYS`／`PipelineSettings` 欄位；`numlan` 的 `useConfig=True`、`defaultVal="default"`、環名相同，descriptor 迴圈跳過它，`_get_numlan`／`_set_numlan`（`:469-473`）仍是驅動自己的；突變「useConfig False」「descriptor 覆蓋 numlan」都被殺 |
| `panel_scale` 進位 | `test_pipeline_panel_reads_and_saves_an_off_grid_global_wait_on_the_grid`、`test_pipeline_panel_global_wait_slider_shows_tens_and_saves_units` | 57 → 顯示 5、服務讀 50、未動存檔不改原值；4 → 存 40；slider 範圍 0..10，其他 slider 0..100 |
| 選取 −1 | `test_pipeline_panel_keeps_the_stored_scope_when_nothing_is_selected`、`…_mode…`、`test_a_mode_missing_from_the_list_counts_as_not_group` | scope 與 mode 都保留儲存值；Voice 面板 −1 不算 group（突變「讀 `options[-1]`」被殺） |
| `depends_on` 四個時點 | Speech Pipeline：開啟、`fire` 後、−1；Voice：開啟、`fire`（checkbox 與 choice）、設定環改值後換語音、ABSENT（另一個合成器 `dependent_states` 回 `{}`） | 全部有測試；突變「開啟時不套用」「handler 不做事」「不 Skip」「換語音後不套用」「group wait 拿掉 depends_on」都被殺 |
| 還原關鍵 commit（`wt-revert`：把該 commit 的 `addon/`／`pyproject.toml` 檔案退回父 commit，測試維持 HEAD，跑本分支改到的 15 個測試檔） | `347f7f2` 表格欄位與順序 | 180 failed |
| | `9314eb3` numlan ordering-only | 15 failed |
| | `2eb7c62` `panelLayout.py` | 2 collection errors（模組不存在） |
| | `4a53a76` `pipelineControls.py` | 107 failed |
| | `ba2a657` Speech Pipeline 面板 | 6 failed |
| | `b913ba0` Voice 面板放置 | 13 failed |
| | `f022d98` Voice 面板啟用規則 | 2 failed |
| | `67df643` log 切換標籤與 zh_TW | 3 failed |
| 審閱者種子突變（42 個：`pipelineControls.py` 8、`speechSettingsDialog.py` 7、`VoiceSettingsDialogs.py` 13、`panelLayout.py` 6、`settings.py` 6、`__init__.py` 3；先跑 15 個相關測試檔，存活者再跑完整 2070） | `scratchpad/review/mutate.py` | **39 個被殺**，3 個存活（M3：Voice `onSave` 不過濾 `None`、`onDiscard` 不檢查合成器、Speech Pipeline `onSave` 的 `pipeline_config` 條件），三者在真實表格下都是等價或到不了的分支 |
| 聲稱等價的 mutant | M9（`dependent_states` 拿掉 `is not None`）、B4（slider `minValue` 不縮放）、B6（拿掉 `style=wx.SL_HORIZONTAL`）各套用後跑完整測試 | 各 2070 passed；理由成立（守門只允許 bool／choice 值當 expected；所有 slider `min_value=0`；`SL_HORIZONTAL` 是預設樣式） |
| 守門測試擋畸形 entry | `scratchpad/review/probe/test_guard_probe.py`：21 個審閱者自訂的壞 entry | 15 個被至少一個 check 擋下；2 個讓 `check_attribute_names` 丟 KeyError（仍被其他 check 擋下）；4 個沒被擋：結尾冒號、`default` 超出範圍、`max<min`、`min_step` 與 `panel_scale` 不一致（M2）；另外 2 個是合法 entry（Voice 面板非驅動 spin） |
| 假物件保真度（I1、M1） | 把 `Control` 改成銷毀後 raise，跑 `tests/test_voice_settings_panel.py` + WorldVoice→WorldVoice 重建測試；同樣做法套到 master | 本分支 2 個測試失敗（`_bindControllers`、`_applyDependencies`）；master 同樣 2 條路徑失敗（`_bindPunctuationPauseEnabledToggle`、`_applyGroupControlsState`）→ 既有問題，非回歸 |
| NVDA 重建語意 | `settingsDialogs.py:1229-1245`、`:1633-1646`、`synthDriverHandler.py:504-547` | `refreshGui` 清 `sizerDict` 與 sizer、不清控制項屬性；`setSynth` 對同名合成器也會建新實例，所以 WorldVoice→WorldVoice 也會重建 |
| 計畫 Review Focus 1–5 | 1 `test_pipeline_panel_reads_and_saves_an_off_grid_global_wait_on_the_grid`；2 `test_pipeline_panel_saves_an_out_of_range_group_size_clamped`；3 `test_a_rebuild_for_worldvoice_places_the_controls_again`；4 `test_saving_strips_unicode_whitespace_from_the_characters`；5 `test_voice_panel_rows_and_tab_order_survive_a_voice_change` | 五項都有測試；1、2、4、5 的種子突變都被殺；3 只覆蓋「其他→WorldVoice」，且假物件不 raise，所以漏掉 I1（修 I1 的測試 2 補上） |
| 進度帳本 13 個 `Ruling:` | 逐條對照程式 | 皆合理。Ruling 5（N5：另一個合成器不建、不存，代價是 eSpeak 使用者少兩個控制項）與 Ruling 7（B1-M9 拿掉「沒有驅動列 → anchor 全為 None」分支，因 N5 不再有這條路）都與使用者的 N5 一致；Ruling 6（`onSave` 提前到 Task 6）只是順序；Ruling 1 的字面 `NUMBER_MODE_CHOICES` 由 `test_driver_choices_match_the_driver_options` 另外鎖住 |
| B1-M1–M9 | 逐項對照 | M1 `test_a_control_may_follow_an_earlier_worldvoice_control` 與 nearest-anchor 屬性測試存在；M2 `check_choices`／`check_scale` 新規則與兩個 broken case 存在；M3 假 spacer 與三處無孤兒 spacer 斷言存在；M4 `control.parent is env.parent`；M5 `test_an_unknown_control_kind_is_refused`；M6 註解指名面板；M7／M8 註解與測試改名；M9 `voice_placements` 無該分支（`panelLayout.py:95-110`） |
| 執行緒與鎖 | — | 本分支只改 GUI 建構與純函式，沒有執行緒、鎖或 callback 的變動 |
| 暫時 worktree 與 scratch 清理 | `git worktree remove` ×3、刪除 `scratchpad/review/` | 已移除；`git worktree list` 只剩主 checkout 與既有的功能 worktree |

Linux 上沒驗到的：Windows NVDA、實際 wx 版面與朗讀、各引擎 SDK；spec §10.6 的 7 個手動項目全部未跑。本分支未打包。

## 使用者還沒確認的使用者可見預設

spec §12、§13 中由協調者採預設的項目，加上本次 review 的發現：

1. **I1 的修法（新）：** `_voiceControl` 把已銷毀（falsy）的 wx 視窗當作不存在；假物件改成銷毀後 raise。
2. **N2：** Speech Pipeline 面板的 scope 選取為 −1 時保留儲存值，不再寫成 `"WorldVoice"`（UI 到不了這個狀態）。
3. **N5 的效果：** 用 eSpeak NG 等其他合成器時，NVDA Voice 面板不再顯示「每組位數」與「標點停頓字元」，Save 也不寫入；要改只能到 WorldVoice 的語音流程面板。
4. **N6：** 其他語言目錄不動。ar、ru、uk、tr、zh_CN、zh_HK 使用者會看到英文的「Number &mode」「Number &language」「Ignore commas between numbers」「Item wait factor」「Effect scope」；所有非 zh_TW 語言看到英文的「Group size」「Punctuation pause characters」「Apply speech dictionaries」「Speech viewer」。
5. **N7：** zh_TW 目錄刪掉 21 個不再使用的條目（不是標成 obsolete）。
6. **F2：** Speech Pipeline 面板的「數字模式(&M):」多了 Alt+M 快速鍵（面板內無衝突）。
7. **F5：** zh_TW 的 Speech Pipeline 面板標籤冒號由全形「：」改為 ASCII「:」（例如「作用範圍:」「每組位數:」），與 NVDA Voice 面板一致。
8. **F4（既有）：** 未知的儲存 scope 會選到「所有合成器(全域)」並在 Save 時存成 `"all"`。
9. **N1 的效果：** 日誌面板的開關標籤改為「套用語音字典」「忽略在數字間的逗號」「中文空白停頓參數」「項目停頓參數」「標點停頓參數」「數字停頓參數」「語音檢視器」（英文為 sentence case）。
10. **Q1 的效果：** 設定環裡「Global wait factor」緊跟在「Detect language based on Unicode characters」之後，「Group wait factor」緊跟在「Number mode」之後；Voice 面板與 Speech Pipeline 面板的 Global wait factor 都移到最前面（scope 之後）。
11. **N8：** 只有 checkbox 與 choice 能當 controller，controller 不能再依賴別的設定（守門測試強制）。

Windows／NVDA 手動項目（spec §10.6，未驗證），並補上一項：

1. Voice 面板（WorldVoice）版面與 Tab 順序（§6.2），記錄 NVDA 對每個控制項的朗讀。
2. Speech Pipeline 面板版面與 Tab 順序（§6.1）；Global wait factor 0..10，Save 後重開數值不變；Alt+M 跳到 Number mode。
3. 兩個面板的啟用狀態：開啟時、方向鍵切模式、切換開關；Tab 跳過停用控制項，物件導覽報「無法使用」。
4. Voice 面板換語音後每列位置不變、啟用狀態跟著語音值；設定環改模式／開關後再換語音。
5. 設定環順序（§6.3），從 rate 開始；環裡改值會保存，numlan 重啟 NVDA 後仍在。
6. 其他合成器（eSpeak NG）：Voice 面板沒有 Group size／Punctuation pause characters，Save 不改 pipeline 設定；**開著對話框** WorldVoice → eSpeak NG → WorldVoice，以及 **WorldVoice → WorldVoice（按 OK 不換）**，每次 Voice 面板都正確顯示、log 無錯誤（修 I1 前預期會出現 RuntimeError）。
7. zh_TW：§7 的每個標籤都有翻譯，記錄冒號的顯示方式。
