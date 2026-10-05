# 階段 13：Pipeline 第二輪

日期：2026-10-05。
基準：`master`（`ff0b49a`，階段 12 完成）。分支：`phase13-pipeline`。
狀態：依使用者要求自動執行（spec → plan → 實作 → Fable review），無需使用者決定。

本文件是 [`refactor.md`](../../../refactor.md) §11 的階段 13，對應 §5.1、§5.2、§5.3（`_run_logged`），以及 §9 的 C7（`SplitCommand`）、C8、C9。

## 需求與範圍

### 1. 語言 → 語音只查名稱（C9）並統一 stage 契約（§5.1）

- 現況：
  - `deduplicate_language_command(seq, ctx)` 透過 `ctx.voice_for_language`（= `VoiceManager.getVoiceInstanceForLanguage`）取得 **facade 實例** 來比較。它在 filter 內建立實例，instance cache 跟著成長。
  - `lang_cmd_to_voice(seq, voice_manager=…, default_instance=…)` 吃整個 manager，是 `speak()` 四步中唯一的不同介面。
- `SpeechContext` 的 `voice_for_language: Callable[[str], Any]` 改為 `voice_name_for_language: Callable[[str], str | None]`。
  - 主驅動傳 `manager.getVoiceNameForLanguage`：純名稱查詢，不建立實例。
  - `GENERIC_CONTEXT` 的預設值為 `lambda language: None`。
- `deduplicate_language_command` 改為比較語音**名稱**：
  - 起點是 `ctx.default_voice.name`；
  - 新語言的名稱是 `ctx.voice_name_for_language(lang) or ctx.default_voice.name`。
  - 現行 `getVoiceInstanceForLanguage` 的結果就是 `getVoiceInstance(getVoiceNameForLanguage(lang))`，名稱為空時退回預設實例。instance cache 對每個名稱只有一個實例，所以比較名稱與比較實例等價，輸出逐項相同。
- `lang_cmd_to_voice(seq, ctx)`：
  - `lang = cmd.lang or ctx.default_voice.language`；
  - `key = ctx.voice_name_for_language(lang) or ctx.default_voice.name`。
  - 這與現行 `voice_manager.getVoiceNameForLanguage(lang) or default_instance.name` 完全相同，包括「`lang` 為 None 時以預設語音的語言查角色設定」這個既有行為。
- 主驅動 `speak()`：一次 `ctx = self.speech_context()`，傳給 `deduplicate_language_command` 與 `lang_cmd_to_voice`。

### 2. `LanguageDetector` 不再自取全域（§5.1）

- `LanguageDetector(availableLanguages, speechSymbols=None, *, conf_provider, language)`：
  - `conf_provider: Callable[[], Mapping]`：回傳 `config.conf`。讀 `["WorldVoice"]["autoLanguageSwitching"]` 的 `ignoreNumbersInLanguageDetection` 與各 script 設定，共 2 處，與 `ConfigRoleRepository(conf_provider)` 同形。
  - `language: Callable[[], str]`：回傳主驅動目前的語言，取代 `getSynth().language` 2 處。
- `languageDetection/__init__.py` 不再 import `config`、`synthDriverHandler`。
- 主驅動建構時傳 `conf_provider=lambda: config.conf`、`language=lambda: self.language`。
  - 現行 `getSynth().language` 在三個呼叫路徑（filter「before」、`speak()`「after」、`process_for_spelling`）中，取得的都是同一個 WorldVoice synth，因為只有 `uwv` 為真時才註冊。所以改為 `self.language` 等價。
  - 本函式在 filter 註冊期間每次呼叫都即時讀取，與現行相同，不快取。
- 主驅動新增 `_detectLanguageTiming()`，回傳 `config.conf["WorldVoice"]["autoLanguageSwitching"]["DetectLanguageTiming"]`。`speak()` 與 `detect_language_timing()` 兩處改用它，取代兩份相同的路徑字串。

### 3. DRY：兩組同形程式（§5.2）

- **`_insert_between(seq, should_break, break_cmd)`**：「相鄰兩項之間依 predicate 插入同一個 break 物件」的唯一實作。
  - `item_wait_factor` 用 `lambda prev, cur: isinstance(prev, str) and isinstance(cur, str)`。
  - `number_wait_factor` 用「兩者都是數字字串」。
  - 刪除 `_insert_BreakCommand_between_number` 與兩份重複註解（含 `previousious` 錯字）。
  - 空序列、單一元素、插入位置與 break 物件身分（同一個實例重複出現）都與現行相同。
- **`_split_by(regex, text) -> Iterator[tuple[Literal["text", "match"], str | re.Match]]`**：唯一的「以 regex 切字串」掃描迴圈。
  - 依序產生非空的 `("text", str)` 片段與每個 `("match", Match)`。
  - 改寫四處使用端，各自只寫片段 → 命令的對應：
    - `iter_number_speech_segments_language`；
    - `iter_number_speech_segments_mode`。它的 `"."` 前後空白規則改由「上一段是否為數字」與「緊鄰的前一段文字」兩個狀態表達，規則與現行逐條相同。
    - `inject_chinese_space_pause` 的內迴圈；
    - `_split_punctuation_segments`。它的對外形狀 `("text"|"punct", str)` 不變。

### 4. `_run_logged` 少讀 config（§5.3）

- 現況每次 stage 呼叫最多讀 `config.conf` 三次：
  - `["general"]["loggingLevel"]`；
  - `["WorldVoice"]["log"]["enable"]`；
  - `["WorldVoice"]["log"][label]`。
- 改為先取 `section = config.conf["WorldVoice"]["log"]` 一次，再讀 `enable` 與 `label`。邏輯與短路順序不變。
- **`LogPolicy` 快取評估後不採用**。這些值有四個寫入者：
  - `PipelineLogService.enable/disable`；
  - `LogSettingsPanel` 的逐項開關；
  - NVDA 自己的一般設定面板（`loggingLevel`）；
  - config profile 切換。
  - 快取要在每個寫入者處失效，漏一處就會「設定了卻不記錄」。換到的只是每次 stage 呼叫少幾次 dict 查詢，`refactor.md` 本身列為低優先。

### 5. 刪除死碼

- `_speechcommand.SplitCommand`（C7）：addon 與 tests 內無使用者。
- `compat/commands.normalize_legacy_commands` 的 `isinstance(command, Voice)` 分支（C8）：
  - 序列進入 `normalize_legacy_commands` 之前一定經過 `lang_cmd_to_voice`，它把語言命令轉成 `SelectVoice`。pipeline 也不產生 `Voice` 物件。
  - 外部 filter 要放入 WorldVoice 的 `Voice` 實例，必須存取私有的 `getSynth()._voiceManager`，已知外掛（`ref/Neural`）沒有這樣做。
  - 刪除後解除 `compat → driver` 的 import 依賴。

### 決定

- `SpeechContext` 不加 `detect_language_timing` 欄位。這個值只在主驅動內讀，兩處讀取以 `_detectLanguageTiming()` 收斂就夠，不需要經過 pipeline 的 context。
- `LanguageDetector` 不吃 `ctx`，改注入兩個 provider。它同時是 NVDA filter（只收序列）與主驅動的直接呼叫對象，注入 provider 讓兩種用法共用同一個建構時的依賴，不必在 filter 端另包一層。

### 成功條件

1. 完整測試全部通過；`ruff format --check addon`、lint gate（`F401,F821,BLE001,I001`）為 0；hygiene 守門測試通過。
2. 守門測試（`tests/test_pipeline_structure.py`）：
   - `languageDetection/__init__.py` 不 import `config`、`synthDriverHandler`；
   - `pipeline/__init__.py` 不出現 `_insert_BreakCommand_between_number`、`previousious`、`voice_manager`；
   - `.finditer(` 在 `pipeline/__init__.py` 只出現一次（在 `_split_by` 內）；
   - `_speechcommand.py` 不出現 `SplitCommand`；
   - `compat/commands.py` 不 import `..driver`。
3. `LanguageDetector` 的特性測試（新增，在改動前寫好並通過，改動後不修改斷言）全部通過：
   - `add_detected_language_commands`：
     - 混合 script；
     - 數字與 `ignoreNumbersInLanguageDetection` 兩種設定；
     - 符號表 mode 1；
     - 既有 `LangChangeCommand` 重設基準語言；
     - 非字串命令透傳。
   - `process_for_spelling`：空白與數字回到預設語言；有與無 `locale` 兩種情況。
   - `find_language_for_script`：設定值優先，以及不可用時的 fallback。
4. Filter 的特性測試（新增，同上，改動前寫好）全部通過：
   - `item_wait_factor`、`number_wait_factor`：空序列、單一項目、連續字串、夾命令、break 物件身分；
   - `inject_number_language`、`inject_number_mode`：三種模式，含 `.` 前後空白規則、正負號、小數；
   - `inject_chinese_space_pause`；
   - `_split_punctuation_segments`。
5. `deduplicate_language_command` 與 `lang_cmd_to_voice`：
   - 既有測試改用 `voice_name_for_language` 後，斷言不變；
   - 新增測試：filter 期間 manager 的 instance cache 不成長。
6. `driver/<Engine>/driver/`、`driver/sonic` 無變動。
7. 使用者可見行為不變：語音切換、數字語言與模式、停頓、語言偵測、拼讀。

### 不在範圍內

- C4（預設語音兩條規則）與 `lang_cmd_to_voice` 在 `lang is None` 時查角色設定的既有行為。只保留，不修改。
- UI 第二輪（階段 14）。

## 測試

- 依成功條件 2–5。
- 特性測試先寫並對 `master` 的程式碼通過，再進行對應的重構。
- 所有新測試以 `tests/nvda_stubs.StubModules` 建 stub，pipeline 模組以真實檔案在 stub package 下載入。依 `tests/test_pipeline_stages.py` 的 loader。
