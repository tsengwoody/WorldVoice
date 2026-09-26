# WorldVoice 程式碼審查：Design Patterns 與 SOLID Principles

審查日期：2026-09-25。基準：`5c7d20d` 與本次工作目錄內容。

## 結論與範圍

目前最優先的問題是主驅動缺少 `BreakCommand` 匯入，其次是初始化失敗的資源回收、設定取消的交易邊界，以及語音物件與共用引擎狀態的耦合。專案已使用 Adapter、Factory／Registry、Observer、Decorator 與 Pipeline 等設計；改善重點是讓這些設計具備明確的所有權與行為契約。

本次檢視語音入口、request builder、TaskManager、VoiceManager、引擎探索、Voice adapters、pipeline/settings、語言偵測、設定 UI 與現有測試。原生 DLL、所有底層引擎實作及 NVDA 的完整 Windows 執行環境不在完整驗證範圍。另參照本機 `ref/nvda/source` 的合成器載入與 extension point 實作；它不等同使用者實際安裝版本。

下列發現記錄原始審查時的狀態；F2、F3 的後續修正記錄見文末。原先已有的翻譯修改與兩個未追蹤測試檔保留；原始審查的測試結果包含這兩個測試檔。

## 審查方法：Patterns 與 SOLID 如何配合

Design Patterns 描述可採用的組織方式；SOLID 用來檢查責任、依賴與替換契約是否合理。使用某個 pattern 本身不代表符合 SOLID，也不需要把每個函式都改成類別。

| 原則 | 本專案的檢查重點 | 可採用的設計方式 |
| --- | --- | --- |
| SRP：單一職責 | 播放、設定儲存、設定預覽、生命週期是否由不同理由驅動修改？ | Adapter、設定 Repository、編輯 session |
| OCP：開放封閉 | 新增引擎或 pipeline stage 是否要修改多處既有分支？ | Registry／Factory、Strategy、stage 清單 |
| LSP：里氏替換 | 不同 Voice adapter 的啟用、取消、完成通知是否有相同行為契約？ | 共用契約測試、統一播放介面 |
| ISP：介面隔離 | 消費端是否被迫知道 `core`、設定儲存、變體等無關細節？ | 小型 `Protocol`、獨立能力介面 |
| DIP：依賴反轉 | 排程與轉換邏輯是否直接依賴 NVDA globals、具體 Voice 類別？ | 注入事件出口、設定快照、引擎工廠 |

下列 P1 表示應優先修正的功能或可靠性問題；P2 表示特定操作或契約條件下的問題。架構建議另列，避免把可維護性意見當成已發生的故障。

## 具體發現與修正建議

### F1 · P1：主驅動引用未匯入的 `BreakCommand`

**位置：** [命令匯入](addon/synthDrivers/WorldVoice/__init__.py#L17)、[supportedCommands](addon/synthDrivers/WorldVoice/__init__.py#L112)。

`supportedCommands` 包含 `BreakCommand`，但此模組沒有匯入或定義該名稱。`requestBuilder` 及 `pipeline` 自己匯入此名稱，不會將它加入主驅動的命名空間。執行類別宣告到這裡會產生 `NameError`，導致 WorldVoice 無法正常載入。

**證據：** 依模組實際匯入名稱建立隔離命名空間，求值原始 AST 中的 `supportedCommands` 表達式，得到 `name 'BreakCommand' is not defined`。這是宣告層的重現，未冒充完整 NVDA 啟動測試。

**最小 fix：** 將 `BreakCommand` 加入 `from speech.commands import ...`。

**Refactor／原則：** 此項主要是正確性缺陷，無須強行套用 pattern。增加主入口 import smoke test；目前測試會建立替代 package 再載入子模組，因此測試通過不能證明主入口可匯入。

**驗收：** 以最小 NVDA stubs 匯入完整主模組，確認類別宣告成功，且 `supportedCommands` 含有真正的 `BreakCommand`。

### F2 · P1：初始化失敗沒有對稱回收，正常關閉也有不完整的清理邊界

**位置：** [SynthDriver 初始化](addon/synthDrivers/WorldVoice/__init__.py#L363)、[terminate](addon/synthDrivers/WorldVoice/__init__.py#L409)、[VoiceManager 初始化](addon/synthDrivers/WorldVoice/voiceManager.py#L84)、[引擎終止](addon/synthDrivers/WorldVoice/voiceManager.py#L136)。

初始化先通知 `WVStart`、安裝 pipeline、替換設定面板、啟動 TaskManager，才建立 VoiceManager。若啟用的引擎沒有可用語音，VoiceManager 第 113 行直接拋例外，前述操作沒有 rollback。TaskManager 的 worker 已啟動，部分引擎也可能已開啟。

外層 `terminate()` 的 `_run_cleanup` 只能保護呼叫本身，不能補救建構失敗：例如 `voiceManager = self._voiceManager` 位於保護函式之外，初始化尚未完成時屬性可能不存在。VoiceManager 的 `terminate()` 也會因單一 `commit()`、`close()` 或 `engineOff()` 失敗，跳過後續引擎。

另有一個同類邊界缺口：[`detect_language_timing()`](addon/synthDrivers/WorldVoice/__init__.py#L569) 註冊的實例 handler，未由 [`pipeline.unregister()`](addon/synthDrivers/WorldVoice/pipeline/__init__.py#L809) 或 `terminate()` 明確解除。本機 NVDA registrar 使用弱參照，因此不能直接斷言永久洩漏；但舊 driver 仍被引用時，關閉後的 handler 仍可能存在。

**最小 fix：** 預先建立可安全清理的屬性；用 `try/except` 對已取得的資源逆序 rollback；VoiceManager 逐項嘗試清理；明確解除實例 handler。只關閉該 manager 成功開啟的引擎。

**Refactor／原則：** SRP、DIP。由一個 runtime owner 管理生命週期，用 `ExitStack` 或等價 cleanup stack 記錄成功取得的資源，讓初始化失敗與正常關閉共用清理流程。清理動作必須可重複呼叫，並避免一項失敗阻止其他項目。

**驗收：** 在引擎啟動、語音列舉、字典載入各階段注入失敗；確認 worker 結束、已開啟引擎全部收到關閉、patch 還原、handler 解除。再測單一引擎關閉拋例外與重複終止。

### F3 · P1：設定預覽會覆寫回復基準，按取消仍保留修改

**位置：** [滑桿事件](addon/globalPlugins/WorldVoice/speechSettingsDialog.py#L585)、[參數同步](addon/synthDrivers/WorldVoice/voiceManager.py#L217)、[Voice.commit／rollback](addon/synthDrivers/WorldVoice/driver/__init__.py#L225)、[onDiscard](addon/globalPlugins/WorldVoice/speechSettingsDialog.py#L620)。

啟用「不同語音角色參數保持一致」後，滑桿事件呼叫 `onVoiceParameterConsistent()`。此方法對 cache 中每個 instance 呼叫 `commit()`，同時覆寫 `commit_*` 快照及 `config.conf`。使用者按取消時，`rollback()` 只能回復到剛才預覽時寫入的新值。

**證據：** 原始 `Voice` 的隔離重現：初始 rate 50 → rate 72 → `commit()` → `rollback()`，結果仍為 72。UI 到這條路徑的呼叫關係已由原始碼確認。

同一設定頁的 [`onKeepEngineConsistentChange()`](addon/globalPlugins/WorldVoice/speechSettingsDialog.py#L523) 也會立即呼叫會改寫 role mapping 的 manager 方法，而 `onDiscard()` 僅回復 voice parameters；這些設定應使用相同的編輯邊界。

**最小 fix：** 將「套用參數到其他語音」與「commit」分開；預覽不更新儲存值或取消基準。儲存時才 commit，取消時還原開啟對話框時的參數及 role mapping。

**Refactor／原則：** SRP、DIP。使用 Memento／編輯 session 保存原始快照，Repository 處理設定持久化。UI 只呼叫 preview、save、discard；不要由每個 slider handler 決定交易提交。

**驗收：** 保持參數一致開／關兩種情況，分別修改多個角色後按取消；記憶體參數、設定內容與 role mapping 都應還原。按儲存才應保留新值。

### F4 · P1：建立 Voice 就會切換共用 core，繞過播放排程

**位置：** [Voice 建構子](addon/synthDrivers/WorldVoice/driver/__init__.py#L55)、[setCoreParameter](addon/synthDrivers/WorldVoice/driver/__init__.py#L191)、[惰性建立](addon/synthDrivers/WorldVoice/voiceManager.py#L181)、[語音解析](addon/synthDrivers/WorldVoice/pipeline/__init__.py#L709)。

同一引擎的 Voice 以 class attribute 共用 core。建立新 Voice 時，建構子立即呼叫 `setCoreParameter()`，直接改寫 `core.voice` 及參數。建立動作既可發生於組裝下一個 request，也可發生於 UI 選取語音，並不受 TaskManager 的 worker 排程保護。

**證據：** 使用原始 Voice 與 fake core，先建立 a，再建立 b，沒有提交任何 speech task，`core.voice` 已從 a 變成 b。是否造成正在播放的原生引擎中斷，取決於各引擎 setter 的行為；已確定的是排程之外會修改播放狀態。

**最小 fix：** 建構及載入設定只更新 Voice 的本地值；由 worker 在播放前統一 activation。也要檢查 `percent_property`、VE／Cerence 的 variant setter 與 `waitfactor` setter，避免僅刪除建構子最後一行後仍有硬體寫入。

**Refactor／原則：** SRP、DIP。Factory 建立語音描述與設定；EngineSession 擁有 core 並序列化啟用／播放／參數修改。Voice 不再同時代表「可保存的設定」與「正在使用的硬體狀態」。

**驗收：** 在 a 播放期間建立或預覽 b，不應在排程之外修改 core；排程真正執行 b 時，才完整套用 b 的設定。

### F5 · P2：OneCore 再次啟用已快取語音時沒有恢復 language

**位置：** [OneCore Voice 建構](addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py#L10)、[OneCore language 屬性](addon/synthDrivers/WorldVoice/driver/OneCore/driver/__init__.py#L4)、[基底 active](addon/synthDrivers/WorldVoice/driver/__init__.py#L143)。

OneCore 的 adapter 只在建構子執行 `self.core.language = self.language`。其 core 子類別把 language 改為獨立的 `_language` 欄位；基底 `active()`／`setCoreParameter()` 只切換 voice ID 與通用參數，不更新 language。

因此，建立英文 a → 建立中文 b → 再啟用已快取 a，core 的 voice ID 可回到 a，language 仍保留 b 的值。這是 adapter 狀態不一致；是否進一步改變實際發音，需在 OneCore／NVDA 整合環境驗證。

**最小 fix：** 在每次 activation 時同步 OneCore 的 language，或讓 core 的 language 由目前 voice 的 metadata 推導；避免只在建構階段同步。

**Refactor／原則：** LSP。定義共同 activation 後置條件：voice ID、語言及支援的參數都必須對應被啟用的角色，讓替換 adapter 時上層不必加入 OneCore 特例。

**驗收：** 同一 core 上執行 a → b → a，每次檢查 voice ID、language 及參數；最後一次使用既有 cache instance。

### F6 · P2：遇到不可用引擎後，builder 無法切回可用語音

**位置：** [queue_speech_sequence](addon/synthDrivers/WorldVoice/requestBuilder.py#L6)。

迴圈第 10 行先檢查「目前 voice」是否 ready，再於第 12 行解析切換 voice 的命令。切到不可用 voice 後，後續每個 command 都被 `continue` 跳過，包含原本可以恢復可用狀態的切換命令。

**觸發條件：** sequence 含有 ready registry 未包含的 Voice，或 default voice 已不在該 registry。正常 VoiceManager 路徑不一定產生此輸入，但 builder 的處理邏輯明確嘗試處理引擎不可用情況。

**證據：** 隔離重現 `a/可用 → 文字 → missing/不可用 → 文字 → b/可用 → 文字`，結果只有 a 被排入，b 的 `spoken` 為空。

**最小 fix：** 先處理 voice 切換與舊 buffer 的 flush，再判斷一般文字／break 的可用性；明確選擇不可用角色的 fallback 或跳過政策。

**Refactor／原則：** DIP、OCP。以明確的 `SelectVoice` command 或 voice key 表達路由，避免靠 `isinstance(command, Voice)` 辨識具體 adapter。builder 只建構 request，resolver／factory 負責取得角色。

**驗收：** 包含不可用 default、途中切入不可用 voice、再切回可用 voice、尾端 break 及 index command 的序列。確保恢復後的文字有排入且順序正確。

### F7 · P2：epoch 無法區分同一 core 發出的舊事件

**位置：** [完成與 index 回呼](addon/synthDrivers/WorldVoice/taskManager.py#L236)、[有效性檢查](addon/synthDrivers/WorldVoice/taskManager.py#L264)、[既有舊 epoch 測試](tests/test_worldvoice_request_manager.py#L190)。

TaskManager 檢查目前 task 的 epoch、token、phase 與 `expected_core`，但收到的事件只有 `synth`／`index`，沒有來源 request 或 segment 的識別碼。若舊 request 被取消後，新 request 重用相同 core，延遲送達的舊事件就會符合新 task 的所有條件。

**證據：** 用原始 TaskManager 建立 request A，取消後以相同 fake core 啟動 B；此時送入模擬 A 延遲事件的 index 999 與 done，B 的 future 被完成，999 也被轉送。這證實事件來源無法辨識；不代表已證明所有原生引擎都會在 cancel 後送出這類事件。既有 `test_old_epoch_events_are_discarded` 使用不同 core，未涵蓋這項條件。

**最小 fix／前提：** 先明訂 adapter 的取消契約。如果底層保證 cancel 返回後舊回呼已排空，應以引擎契約測試確認；否則必須在 adapter 保留來源 generation／segment，或等待舊回呼確定排空後才重用 core。

**Refactor／原則：** Observer + LSP／DIP。由 adapter 將原生回呼轉為帶來源識別的播放事件，再交給 scheduler。識別必須在原始請求建立時保存，不能在事件到達時補上「目前 epoch」，否則仍會錯認。公開 NVDA 事件格式可由獨立 bridge 維持相容。

**驗收：** 同 core 的 A cancel → B start → A late index/done 不得推進 B；B 的事件才可完成 B。另保留同步 done、不同 core、尾端 pause、重複 index 等既有案例。

## 架構重構建議

### A1：縮小 Voice 介面，明確區分引擎 session 與語音設定

目前 [`Voice`](addon/synthDrivers/WorldVoice/driver/__init__.py#L50) 包含 core 生命週期、語音 metadata、設定儲存、設定同步、排程與播放控制；TaskManager 又直接存取 `voice.core`。這使 Adapter 洩露了底層表示法，並將設定與播放耦合。

建議逐步分成三個責任：不可變的 VoiceSpec／VoiceParameters、擁有 core 的 EngineSession、負責讀寫的 VoiceSettingsRepository。使用小型 `Protocol` 描述排程需要的播放與取消能力；變體、wait factor 等只由相關消費端依賴。

[`VoiceManager.waitfactor`](addon/synthDrivers/WorldVoice/voiceManager.py#L167) 硬編碼 `Cerence`／`VE` 的型別判斷，可改為 adapter 宣告能力或實作窄介面，讓新引擎加入時不必修改 manager。不要僅以四處增加 `hasattr` 取代明確契約。

**對應：** SRP、ISP、DIP、OCP；Adapter 配合 composition。先處理 F4／F5，再逐步移動持久化，避免一次重寫所有 driver。

### A2：Registry 保留 manifest discovery，但補上所有權、唯一性與驗證

[`engine/discovery.py`](addon/synthDrivers/WorldVoice/engine/discovery.py#L103) 已把引擎探索抽出，是有利於 OCP 的方向。不過 internal 與 external specs 直接串接，最後 [`ready[spec.name] = voice`](addon/synthDrivers/WorldVoice/engine/discovery.py#L186) 以名稱覆寫；同名來源的優先序沒有明確宣告，VoiceManager 又仍迭代原始 specs。

建議在 discovery 完成時即檢查名稱衝突，明確拒絕或合併為唯一有效 spec；驗證 factory、metadata 與必要方法，而不只檢查 `Voice` 匯出及 `ready()`。這是外掛輸入條件下的設計風險，本次未宣稱目前 workspace 已有同名衝突。

把全域可變的 [`READY_ENGINE_CLASS`](addon/synthDrivers/WorldVoice/engine/__init__.py#L36) 改為注入 manager 的 registry snapshot，並讓 runtime owner 保存自己開啟的 sessions。這也解決 F2 中以全域 ready 集合決定關閉對象的問題。

**對應：** Factory／Registry + OCP、DIP。保留現有探索機制，避免為每個引擎再建立重複的 factory 類別。

### A3：Pipeline 與設定各建立單一描述來源

Pipeline 的 stage 清單分散於 [`static_register()`、`dynamic_register()`、兩個排序函式與 `unregister()`](addon/synthDrivers/WorldVoice/pipeline/__init__.py#L763)。新增 stage 時，註冊、順序、取消註冊需同步修改多份清單，容易產生 F2 類型的遺漏。

建議用有序 `StageSpec` 清單描述函式與啟用條件，由 PipelineController 管理自己的 registration handles。轉換函式接收同一份 settings/context 快照，保留現有 generator 寫法，減少每個 stage 重新查詢 `getSynth()` 與全域設定。

設定也重複分布於 [`config.conf.spec`](addon/synthDrivers/WorldVoice/__init__.py#L52)、兩組 driver settings、[`DEFAULT_PIPELINE_SETTINGS`](addon/synthDrivers/WorldVoice/pipeline/settings.py#L8)、`PipelineSettings`、載入／儲存／runtime mapping 及 UI。例如 global wait 的 config default 為 10，而 driver setting 宣告為 50；這已是描述值差異，實際優先序仍應以 NVDA 整合測試確認。

用 SettingSpec 統一 key、runtime name、default、範圍與單位，衍生共用映射。UI 的顯示邏輯可留在 UI，無須建立過度通用的表單框架。

**對應：** Pipeline／Strategy + SRP、OCP、DIP。保留既有 `PipelineSettings` 作為資料模型，逐步移除旁路設定寫入與重複描述。

### A4：TaskManager 保留單一排程責任，將 NVDA 事件轉接移到邊界

目前 request 層級統一提交、CancellationToken 的可中斷等待、完成通知去重與多項取消競態測試值得保留。主要問題是 [`TaskManager`](addon/synthDrivers/WorldVoice/taskManager.py#L87) 同時處理 queue、request 狀態、core 辨識、NVDA 全域事件註冊與通知轉送。

先抽出事件輸入／輸出 adapter，讓 TaskManager 只依賴明確的播放完成契約。request 可用 enum 表達 building、submitted、cancelled、failed、completed，並在狀態轉移時維護 `remaining` 與完成通知規則。現階段不需要為每個 state 建立一個類別。

**對應：** Command／Observer 與明確狀態模型 + SRP、LSP、DIP。抽離過程必須保留同步 done 與 cancel 的鎖定語意，不能為了簡化類別而移除既有競態保護。

## 建議執行順序

| 階段 | 工作 | 完成條件 |
| --- | --- | --- |
| 1：恢復入口可靠性 | F1；補完整入口 smoke test | 主模組可匯入，不只子模組測試通過 |
| 2：修正使用者可見行為 | F2、F3、F5、F6 | 啟動失敗可回收、取消設定可還原、角色切換正確 |
| 3：統一播放契約 | F4、F7、A1、A4 | core 寫入有單一排程邊界，舊回呼不完成新 request |
| 4：降低擴充成本 | A2、A3 | 新引擎／stage／設定不需同步修改多份核心分支 |

每個階段可分成獨立小變更。先加入會重現實際缺陷的案例，再做最小 fix；行為穩定後才移動責任與介面。

## 驗證紀錄與限制

- `python3 -m pytest tests -q -p no:cacheprovider`：**113 passed in 0.44s**。
- 原先從根目錄執行 `python3 -m pytest -q -p no:cacheprovider`，收集到 `ref/nvda` 的參考專案測試，因缺少 `louis`、`monkeyPatches` 等環境依賴發生 **191 個收集錯誤**。因此上方成功結果明確限定為本專案 `tests/`，不能宣稱整個目錄樹測試通過。
- 隔離 Python 重現確認：F1 宣告的 NameError、F3 commit 後無法還原原值的機制、F4 建構即修改 core、F6 後續可用 voice 被跳過、F7 同 core 延遲事件被接收。使用原始 AST／原始子模組與測試 stubs，未寫入新的測試檔。
- F2、F5 由原始碼呼叫路徑與狀態更新確認；原生引擎資源、GUI 互動及實際發音仍需 Windows／NVDA 整合驗證。
- 原始審查階段未實作 fix/refactor；當時的 F1 匯入問題使其餘執行期路徑無法透過正常 WorldVoice 入口完整驗證。後續狀態見下一節。

## 後續修正記錄（2026-09-25）

- **F2 已修正：** 主驅動初始化失敗時回收已取得的 pipeline、UI patch、拼字 patch、TaskManager 與 VoiceManager；VoiceManager 關閉自己啟動的引擎，單項清理失敗不阻斷後續清理；TaskManager 事件註冊失敗時撤銷已完成的註冊。正常終止也解除語言偵測 handler，並可重複呼叫。
- **F3 已修正：** 語音參數一致性的預覽不再提交設定；引擎一致性的切換在儲存前不改寫 role mapping，按取消會回復執行中的設定。按「套用」後更新取消基準。
- 對 F2、F3 新增回歸案例。原始審查段落及其測試數字保留為修正前紀錄；後續驗證結果以實際執行輸出為準。

## F5／F6／A1／A4 後續實作與驗證（2026-09-26）

- **F5：** 沿用 F4 已存在的 OneCore `applyEngineSettings()` language hook，沒有重做相同修正。`EngineSession` 在 A → B → 已快取 A 時依來源、voice key、revision 重新套用 voice ID、language 與參數；證據包含 `test_onecore_cached_a_b_a_restores_language`、`test_cached_onecore_voice_round_trip_through_manager` 與新舊 Adapter 共用的 `test_cached_a_b_a_restores_voice_language_and_parameters`。
- **F6：** 正規化命令的 `runtime/requestBuilder.py` 跳過不可用語音區段中的文字、index 及停頓，但繼續處理 SelectVoice；遇到可用語音即恢復，不偷偷改用 default。不可用 default、途中不可用與恢復、generator 失敗及取消交錯由 `tests/test_runtime_request_builder.py` 覆蓋。
- **A1：** `runtime/models.py`／`settings.py` 分別擁有資料與設定狀態，`configRepository.py` 保存現有 config 格式，`runtime/session.py` 透過 Adapter 管理啟用與資源。`compat/voiceFacade.py` 只轉交設定與播放操作，UI 使用同一 VoiceEditSession，套用更新取消基準。
- **A4：** 唯一 worker 與 request 狀態機在 `runtime/scheduler.py`；`nvdaEventBridge.py` 負責 NVDA 註冊、來源身分與 owner 通知。同步 done、index 去重、取消／後續請求和重複關閉有具名測試；舊 `taskManager.py` 僅重新匯出。
- **相容層移除證據：** `tests/test_runtime_adapter_contract.py` 以 native／legacy 參數化執行相同五組案例。兩者均使用正式 Store、EngineSession、TaskManager；native 在載入 runtime 前禁止 compat、driver、NVDA 匯入並維持至 teardown。legacy 使用正式 LegacyEngineAdapter，沒有複製 scheduler 或設定服務。此處 native 是直接實作契約的測試 Adapter，不代表原生 DLL 已驗證。
- **本次實際驗證：** `python3 -m pytest tests/test_runtime_adapter_contract.py -q -p no:cacheprovider`：10 passed in 0.10s；`python3 -m pytest tests -q -p no:cacheprovider`：338 passed in 3.28s；其後 `git diff --check` 通過。未收集 `ref/nvda`。runtime 匯入稽核沒有 config、synthDriverHandler、logHandler、compat、driver，亦無 voice.core／READY_ENGINE_CLASS 判斷；設定保存與回復沒有旁路副本。
- **前提與限制：** 保留基底 `6256a23` 的 F2／F3 修正。Windows／NVDA、OneCore 真實切換、跨引擎長文、說全部、index、尾端停頓、快速取消、pause/resume、GUI 套用與取消，以及外部引擎版本接入均尚未實機驗證。**F7 同來源取消後延遲回呼排空契約仍未處理**，不可由上述通過測試推論已修正。
- 任務 1–9 已通過逐任務審查；本段撰寫時 Task 10 與全分支最終獨立審查待執行。完整提交對照與逐項限制見 `docs/superpowers/finish/2026-09-26-voice-runtime-boundaries-validation.md`。
