# 階段 14：UI 第二輪

日期：2026-10-05。
基準：`master`（`a23e630`，階段 13 完成）。分支：`phase14-ui`。
狀態：依使用者要求自動執行（spec → plan → 實作 → Fable review），無需使用者決定。

本文件是 [`refactor.md`](../../../refactor.md) §11 的階段 14，對應 §3.4、§6.2、§6.4，以及 §9 的 C11。

## 需求與範圍

### 1. 三個 `MainLocale*` 政策的 `enabled` 同一語意（C11）

- 現況：
  - `EngineConsistency.enabled` 是建構時讀一次的 pending 屬性，搭配 `persist()`；
  - `VoiceConsistency.enabled`／`ParameterConsistency.enabled` 是即時讀寫 config 的 property。
  - 同一個名字有兩種語意。presenter 因此對三者走三條不同路徑：
    - engine 直接寫政策；
    - voice 只記 pending；
    - parameter 另有預覽還原。
- 改為三個政策的 `enabled` 都是**即時讀寫 config 的 property**，`persist()` 刪除。
- `EngineConsistency` 是唯一會影響可見語音清單的旗標，另有一個預覽值：

```python
class EngineConsistency:
	preview: bool | None = None  # 設定面板開著時的未儲存值；None 表示依 enabled

	@property
	def enabled(self) -> bool: ...          # 讀 config
	@enabled.setter
	def enabled(self, value: bool) -> None: ...  # 寫 config

	def visible(self, table, default_engine):
		active = self.enabled if self.preview is None else self.preview
		...
```

- **Presenter 統一為一條路徑**：
  - 三個 `keep_*` 都是 presenter 自己的 pending 值，從政策的 `enabled` 讀起；
  - `set_*_consistency` 都只改 pending；
  - 需要預覽的兩個旗標另外各做一件事：
    - engine 設 `engine_consistency.preview`；
    - parameter 維持現行的參數預覽與還原記錄。
  - `apply()`：三個旗標都以 `policy.enabled = keep_*` 寫回，並清除 `preview`。
  - `discard()`：清除 `preview` 並重讀旗標。
  - `_initial_engine` 不再需要，刪除。
- **行為**：
  - 設定面板內的預覽、套用、取消，與現行逐項相同。
  - 唯一差異：`KeepMainLocaleEngineConsistent` 在 NVDA 設定檔切換後立即生效。現行是建構時讀一次，要重啟 synth 才生效。
  - 另兩個旗標本來就隨設定檔切換，所以這讓三者一致。

### 2. Unicode 面板三組複製收斂（§6.2）

- `UnicodeDetectionSettingsPanel` 的 Latin／CJK／Arabic 三組「候選清單 + `wx.Choice` + 選取 + 存檔」改由一個表與 `_add_script_choice(script, label)` 建立：
  - config key 取自 `languageDetection.SCRIPT_CONFIG_KEYS`；
  - 候選語言取自 `languageDetection.SCRIPT_LANGUAGES[script]`（Latin → `ALL_LATIN`，Han → `CJK`，Arabic → `ARABIC`，與現行三個常數相同）；
  - 三個 label 仍各自寫成 `_("…")` 字面字串，翻譯擷取工具才找得到。
- `onSave` 以同一個表迴圈寫回。
- 控制項順序、label、預設選取（設定值不在清單時選第一項）、空清單時 `Disable()`、只寫回 enabled 的選擇，都與現行相同。

### 3. UI 不再存取主驅動私有成員（§6.2）

- 主驅動新增：
  - `voice_manager` 唯讀 property：回傳 `_voiceManager`，終止後為 `None`；
  - `refresh_language_detection()`：由現行 `detect_language_timing()` 改名而來，依 `uwv` 與偵測時機註冊或解除 filter；`_set_uwv` 內部呼叫改用新名。
- UI：
  - `getSynth()._voiceManager`（2 處）改為 `getSynth().voice_manager`；
  - `getSynth().uwv = getSynth().uwv` 改為 `getSynth().refresh_language_detection()`。

### 4. `onSave` 回傳型別對齊 NVDA（§6.2）

- `BaseSettingsPanel.onSave -> bool` 違反 NVDA `SettingsPanel.onSave -> None`（LSP）。
- 拆為 `_write_settings() -> bool`（現行內容）與 `onSave() -> None`（呼叫前者）。
- `SpeechEngineSettingsPanel.onSave` 與 `LogSettingsPanel.onSave` 改呼叫 `_write_settings()`，並依它的回傳值決定是否重啟。

### 5. 角色面板 `onSave` 的重複呼叫（§6.4）

- 三個 checkbox 都已綁定事件，即時呼叫對應的 `set_*_consistency`（`speechSettingsDialog.py:396、404、415`）。
- 所以 `onSave` 在 `apply()` 前的三行 `set_*_consistency(...)` 是重複的，刪除。

### 6. GlobalPlugin 遮蔽的常數（§6.4）

- `globalPlugins/WorldVoice/__init__.py` 第 26 行的模組常數 `workspace_path` 無人使用，被 `onFileImport` 的同名區域變數遮蔽，刪除。
- 路徑推導的單一來源屬 C12，在階段 16 處理，本階段只刪無用常數。

### 決定

- **`SpeechPipelinePanel` 表驅動不做**。這是 `refactor.md` 標為可選的項目。做的話需要在 `PIPELINE_SETTINGS` 加 UI 專屬欄位（slider 範圍、`ui_scale`、選項標籤），還要保留「啟用標點暫停」對兩個控制項的連動；控制項順序與 label 又是使用者可見行為。換來的是新增設定時少改 2 處，不值得在本階段承擔。
- 三個政策統一為**即時讀寫**，不統一為 pending。voice／parameter 兩個旗標在執行期（`follow`、`shared_section`、主驅動 `_set_voice_parameter`）都需要讀目前設定檔的值；改成 pending 會讓它們不再隨設定檔切換，是退步。

### 成功條件

1. 完整測試全部通過；`ruff format --check addon`、lint gate 為 0；hygiene 守門通過。
2. 守門測試（`tests/test_ui_structure.py`）：
   - `mainLocalePolicy.py` 不出現 `def persist`；
   - `globalPlugins/WorldVoice/` 不出現 `._voiceManager`、`.uwv = `；
   - `UnicodeDetectionSettingsPanel` 不出現 `_latinChoice`、`_CJKChoice`、`_arabicChoice`；
   - `BaseSettingsPanel.onSave` 沒有 `return` 值；
   - `SpeechRoleSettingsPanel.onSave` 不呼叫 `set_*_consistency`；
   - GlobalPlugin 沒有模組層 `workspace_path`。
3. 政策與 presenter：
   - 預覽、取消、套用的使用者可見結果（`locales()` 清單、config 旗標、角色修剪）不變。現有斷言改為檢查這些可見結果，不再檢查 `engine_consistency.enabled` 的 pending 值。
   - 新增「設定檔切換後 engine 旗標立即生效」測試。
4. Unicode 面板：新增 exec 測試，在三組候選、設定值不在清單、空清單三種情況下：
   - 控制項順序、選取與 Disable 和現行相同；
   - `onSave` 寫回的 key 與值和現行相同。
   - 先對現行程式碼寫好並通過，再重構。
5. `driver/<Engine>/driver/`、`driver/sonic` 無變動。

### 不在範圍內

- `SpeechPipelinePanel` 表驅動（見「決定」）。
- C12 路徑推導（階段 16）。
- exec 測試改為一般 import（階段 16）。
