# Review：feat/hide-unavailable-engines（語音引擎面板隱藏無法載入的引擎）

日期：2026-11-07。分支：`feat/hide-unavailable-engines`（worktree `/workspace/WorldVoice-hide-unavailable-engines`，`master` `d352a06` → `7812b54`，7 個 commit：2 個 `docs:` 規格與計畫、1 個 `refactor:`、3 個 `feat:`、1 個 `docs:` 使用手冊）。基準 `master` 3744 passed／0 skipped；分支 3769 passed／0 skipped（+25；分支數字由審閱者自己在 scratch worktree 重跑確認，基準數字取自進度帳本與 plan）。
審閱者：Fable 5.1（唯讀；只新增本檔）。流程：一般流程（DEVELOPMENT_WORKFLOW.md §3.3）。Linux，單一 pytest 行程，沒有平行 worker。

依據：

- spec `docs/superpowers/specs/2026-11-07-hide-unavailable-engines-design.md`（G1–G2 使用者決定；D1–D8 協調者預設）；plan `docs/superpowers/plans/2026-11-07-hide-unavailable-engines.md`（Review Focus 1–5 逐項檢查）；進度帳本 `.superpowers/sdd/2026-11-07-hide-unavailable-engines/progress.md`（1 行 `Ruling:`，已評估，見下）。
- 實驗都在暫時 detached worktree `<scratchpad>/review-wt`（`7812b54`）做，`ref` 以符號連結指到 `/workspace/WorldVoice/ref`；結束後以 `git worktree remove` 移除。分支 worktree 與主 checkout 沒有被任何指令修改。
- 行號以 head `7812b54` 為準；`discovery:` = `addon/synthDrivers/WorldVoice/engineRegistry/discovery.py`，`registry:` = `engineRegistry/__init__.py`，`ve:` = `driver/VE/__init__.py`，`cerence:` = `driver/Cerence/__init__.py`，`panel:` = `addon/globalPlugins/WorldVoice/panels/engine.py`，`ve2:` = `driver/VE/driver/ve2/__init__.py`（只讀），`ttsapi:` = `driver/Cerence/driver/ttsapi/__init__.py`（只讀）。

## 結論

**可以 merge。** Critical 0、Important 0、Minor 4（三個是文字與型別註記，一個是測試的小缺口）。沒有找到會把能用的引擎誤判成「無法載入」的情境（這是 spec 自己點名最糟的失敗），沒有和 `master` 相比的回歸，§8 限制全部遵守；實作忠於 spec 的 D1–D8。

- **`load_engine_class` 的抽出（`discovery:160-219`、`:222-235`）。** 我用自己的腳本把 `master` 的迴圈本體（`with timed(... total)` 到 `except` 的 `logger.error`，53 行）去掉一層縮排、`continue` → `return None`、`ready[spec.name] = voice` → `return voice`、結尾補一個 `return None`，和新函式本體逐行比對：**完全相同**（見驗證表）。剩下的迴圈只保留 `get_engine_enabled` 的跳過與非 None 的收集，`logger = logger or _LOG` 在兩個函式各做一次，結果一樣。因此 `load_enabled_engine_classes` 的輸出、四條 `timed` debug 行、warning／error 文字、`synth_driver_class` 對映（含 `setattr` 與一次性 warning）、跳過規則都沒有變。既有的 `test_enabled_engines_import_from_their_root_and_must_be_ready_and_named` 與 `test_ready_engine_classes_loads_only_the_enabled_ready_engines` 仍然抓得到「忽略 enabled 旗標」這個突變（M8）。
- **VE／Cerence 的 `ready()`（`ve:895-938`、`cerence:905-945`）。** 對照內層：VE `ve2:86-97` 用 `os.environ["PROCESSOR_ARCHITECTURE"]` 載入 `msvcr110.dll`、`ve.dll`、`vplatform.dll`；Cerence `ttsapi:82-91` 用 `"x64" if sys.maxsize > 2**32 else "x32"` 只載入 `ve.dll`、`vplatform.dll`。外層的 `_nativeFiles` 和這兩組一字不差（順序也一樣），`_engineWorkspace` 的九層 `dirname` 和內層 `module_dir` 的九層 `os.path.dirname(` 相同（我數了內層運算式的括號：`os.path.join(` 加 9 個 `dirname`），而且用的是同一個 `__file__`（`ve2.__file__`／`ttsapi.__file__` 就是內層模組的檔案），所以不管 NVDA 是安裝版（`%APPDATA%\nvda\addons\WorldVoice`）、可攜版（`<portable>\userConfig\addons\WorldVoice`）還是其他 `--config-path`，`ready()` 檢查的路徑和 `LoadLibrary` 開的路徑都是同一條：九層往上就是 `<configPath>`，再接 `WorldVoice-workspace\VE`。`workspace_path()`（`globalVars.appArgs.configPath/WorldVoice-workspace`）在 NVDA 從 `<configPath>/addons/<name>` 載入附加元件時和它一致；pendingInstall 目錄（`addons/<name>.pendingInstall`）NVDA 只用來讀 manifest 與執行安裝步驟，不會從那裡載入 synthDriver，重新啟動時先改名才載入，所以不會出現「從 pendingInstall 載入而路徑差一層」的情況。唯一算不到 `<configPath>` 的是 NVDA scratchpad（`<configPath>/scratchpad/synthDrivers/...` 只有八層），但那是內層本來就有的限制（VE／Cerence 從 scratchpad 一直載不起來），`ready()` 跟著內層走，結果一致，不是這個分支的問題。`cdll.LoadLibrary` 給的是絕對路徑，Windows 不會再去別處搜尋，所以「檔案不在 `lib/<arch>` 但 `LoadLibrary` 仍成功」不會發生，`os.path.isfile` 不會誤判成「無法載入」。32 位元 NVDA 在 64 位元 Windows 上 `PROCESSOR_ARCHITECTURE` 是 `x86`，內外層讀同一個環境變數，也一致。`ready()` 只碰檔案系統，`test_ready_never_loads_a_library` 把 `ctypes.cdll.LoadLibrary` 換成會 raise 的函式確認過。守衛測試 `test_ready_checks_exactly_what_initialize_loads` 真的在測試行程裡重新載入內層模組、執行真正的 `initialize([])`（`cdll` 換成記錄器），斷言載入清單等於 `_nativeFiles()`，VE 一組、Cerence `sys.maxsize` 兩組；我用突變 M4／M5／M6 確認它抓得到少一個 DLL、架構名寫死、少一層 `dirname`。
- **面板（`panel:38-50`、`:58`）。** `available_engine_specs()` 只呼叫一次，`self.settings` 與 `previousActiveEngine` 都只從它來；`isValid` 的「沒有啟用任何語音引擎」只在面板至少有一個核取方塊時顯示；`onSave` 沒改，`_writeSettings` 只寫 `self.settings` 的鍵，隱藏引擎的設定值原封不動。隱藏但設定檔仍啟用的 VE 不會讓 `activeEngine != previousActiveEngine`，按「確定」不會問重新啟動（突變 M1 證明 `test_engine_panel_hides_an_unavailable_engine` 等三個測試抓得到）。空面板：`activeEngine == previousActiveEngine == set()`，`isValid` 回 True、不寫任何東西（M2）。
- **D6 在 GUI 執行緒對每個引擎呼叫 `ready()` 的副作用。** 逐一看過：SAPI5 的 `ready()` 重設 `cls.synthDriverClass`／`cls.drainProfile`，在同一個 NVDA 上每次得到同樣的值，而這兩個屬性只在 `createCore` 讀，執行中的合成器不受影響；eSpeak／OneCore 的 `host_names_ready` 只查名稱；RHVoice 沒有覆寫（基底回 True），它的 DLL 只在內層類別的 `__init__` 載入（`driver/RHVoice/driver/__init__.py:516`），import 不載入；外部 plugin（例如 `ref/Neural`）沒有 `ready()`，import 只拉自己的 `driver` 與 core 的 `Voice`。VE／Cerence 內層 import 只定義 ctypes 型別，不載入 DLL。import 成本是每行程一次；錯誤都被 `load_engine_class` 的 `except` 接住、記一行 error、面板照常開。沒有新的鎖、沒有跨執行緒的 callback。
- **測試抓得到它聲稱的錯誤。** 10 個手動突變全部被對應的測試抓到（表在下方），其中包含 plan Review Focus 1–5 各自點名的測試。
- **翻譯與手冊。** 沒有新 UI 字串、沒有動 `.po`；`tests/test_translator_comments.py` 通過。zh_TW readme 兩句文字和 spec §5 一字不差，語氣自然；兩處用詞可以更貼近既有文件（M1）。
- **§8 限制。** 7 個 commit 都是英文 `<type>: <summary>` 加原因，0 個 `Co-Authored-By`；受保護路徑與 Neural 兩個指令都無輸出；`git diff --check master` 乾淨；prek 8 個 hook 全部 Passed；VE 與 Cerence 的外層互不 import（`grep` 0 筆）；`tests/test_vocalizer_drift.py` 仍要求兩個外層除了 `ALLOWED` 與 Cerence 專屬的 `import sys` 之外逐定義相同（`Voice.ready` 與 `_engineWorkspace` 因此被釘住一致）；`_engineWorkspace`／`_nativeFiles` 是 NVDA 層的 camelCase，`load_engine_class`／`available_engine_specs` 是 core 的 snake_case（`tests/test_naming_layers.py` 通過）。

## Critical

無。

## Important

無。

## Minor

### M1. zh_TW readme 的用詞：「WorldVoice-workspace」沒有在手冊其他地方出現過、「NVDA 記錄檔」和既有的「日誌」不一致、條目位置（`addon/doc/zh_TW/readme.md:90`、`:99`；commit `7812b54`）

- `:90` 是整份 zh_TW 手冊第一次也是唯一一次出現 `WorldVoice-workspace`（`grep -i workspace` 只有這一行）；手冊上一句只說「請額外下載相應的驅動語音包」，沒有說檔案放在哪個資料夾。讀者看到「WorldVoice-workspace 中缺少…」不一定知道那是 NVDA 使用者設定資料夾底下的資料夾。建議改成「例如 NVDA 使用者設定資料夾的 WorldVoice-workspace 中缺少 Vocalizer Expressive 或 Cerence 的程式庫檔案（DLL）時」，或在那句前面先補一句說明驅動語音包會安裝到該資料夾。
- `:99` 的「NVDA 記錄檔」：WorldVoice 自己的 zh_TW `.po` 用「日誌紀錄」（`addon/locale/zh_TW/LC_MESSAGES/nvda.po:73-81`、「匯出流程日誌到檔案」），手冊 `:130-135` 用「日誌記錄」，更新日誌標題本身就是「更新日誌」。建議改成「NVDA 日誌也只會以一行說明缺少哪些檔案，不再記錄錯誤」。
- `:90` 插在「若您想停用特定的語音引擎」和「若您需要使用 eSpeak、OneCore、RHVoice、SAPI5 以外的語音引擎，請額外下載相應的驅動語音包」之間。新句子講的是 VE／Cerence 這類需要額外下載的引擎，放在下載那一句之後讀起來比較順（先說要下載，再說沒下載或缺檔時面板不會顯示）。spec §5 寫「after `readme.md:89`」，實作者照做了；這是 spec 的選擇，不是實作錯誤。

### M2. 面板開啟時的 `timed` debug 行仍叫「WorldVoice init timing: ready check …」（`addon/synthDrivers/WorldVoice/bringup.py:40-46`、`discovery:166-171`、`:212`）

`load_engine_class` 沿用 `timed`，標籤文字是 `WorldVoice init timing: %s`。現在每次開語音引擎面板，每個引擎都會多四行「init timing」debug 行，但那不是初始化。只有 debug 等級、不影響功能；spec D5 也把這些行列為已知成本。若要改，`timed` 的標籤是呼叫端傳入的，可以在 `available_engine_specs` 傳一個不同的 logger 或由 `load_engine_class` 接受標籤前綴；不改也可以，但建議在 D5 的說明裡明寫這些 debug 行的文字就是 `init timing`，方便日後看日誌的人對上。

### M3. `available_engine_specs()` 的回傳型別註記是裸的 `tuple`（`registry:46`；spec §4.1 寫 `tuple[EngineSpec, ...]`）

`registry:` 沒有 import `EngineSpec`，所以寫成 `-> tuple`。建議在 `from .discovery import (...)` 加 `EngineSpec` 並改成 `-> tuple[EngineSpec, ...]`，和 spec 與 `ready_engine_classes -> dict[str, type]` 的精確度一致。純型別註記，不影響行為。

### M4. `test_ready_never_loads_a_library` 只攔 `ctypes.cdll.LoadLibrary`（`tests/test_vocalizer_ready.py:98-105`）

`ready()` 若改成用 `ctypes.CDLL(path)`、`ctypes.windll` 或 `os.add_dll_directory` 之類的方式「試載」DLL，這個測試攔不到。目前的實作只用 `os.path.isfile`，守衛的目的（D1：只查檔案、不載入）已由 `test_ready_with_every_file` 把 `os.path.isfile` 換掉也能回 True 間接證明。若要補強，把 `ctypes.CDLL` 一起換成會 raise 的類別即可（兩行）。

## Review Focus 逐項

1. **隱藏但設定檔仍啟用的引擎（VE 預設開、檔案被刪）：** `panel:47-49` 只從 `available` 算 `previousActiveEngine`，`_writeSettings` 只寫 `self.settings`。`test_engine_panel_hides_an_unavailable_engine`、`test_engine_panel_keeps_a_hidden_engine_flag_on_save` 在突變 M1（`previousActiveEngine` 改回從 `ENGINE_SPECS` 算）與 M11（`settings` 改回 `ENGINE_SPECS`）都失敗。檔案補回來後 `available_engine_specs()` 不快取（D5），下一次開面板就回來，核取狀態讀原本的設定值（`base.py:48-56`）。符合。
2. **部分安裝（只缺 `msvcr110.dll`，或有資料夾但沒有 `lib/<arch>`）：** `test_ready_names_each_missing_file` 五列各缺一個檔、`test_ready_without_the_workspace_names_every_file` 全缺；日誌只列缺的那些完整路徑、以 `", "` 連接。M3／M9 突變都被抓到。符合。
3. **檢查與載入的路徑不一致：** 守衛測試執行真正的內層 `initialize`，VE 一組、Cerence `sys.maxsize` 兩組（`2**63-1` → `x64`、`2**31-1` → `x32`）；M4／M5／M6 都被抓到。另外我獨立數過內層的九層 `dirname`，並確認 `_engineWorkspace` 用的就是內層模組的 `__file__`。符合。
4. **停用的引擎在 import 或 `ready()` raise：** `load_engine_class` 的 `except Exception` 記一行 `Failed to load ready state for <name>: <error>` 回 None，`available_engine_specs` 不會中斷；`test_load_engine_class_gives_none_for_each_failure[raises]`、`test_available_engine_specs_keeps_ready_engines_in_order_enabled_or_not`（`Broken` 引擎 raise `RuntimeError("boom")`，斷言日誌只有那一行 error）、`test_ve_ready_without_processor_architecture_raises_like_initialize`（`KeyError` 往外丟，由上層接住，D3）。符合。
5. **一個引擎都沒有：** `panel:58` 的 `and self.settings`；`test_engine_panel_without_available_engines_saves_without_asking` 在 M2 突變失敗。符合。

## 進度帳本的 Ruling

- **Task 4：`test_engine_panel_keeps_a_hidden_engine_flag_on_save` 把 VE 存成字串 `"True"` 而不是 plan 的 `True`。** 合理，而且必要。我在 scratch 複本把 `settings` 改回從 `ENGINE_SPECS` 算（M11）確認：存 `True` 時，第一次 `onSave`（沒有變更）不會寫設定，第二次（勾 SAPI5）寫回的 VE 仍是 `True`，和原值相同，測試不會失敗；存 `"True"` 時第二次寫回會把它變成 `True`，斷言 `{"OneCore": True, "SAPI5": True, "VE": "True"}` 才抓得到「隱藏引擎的旗標被寫掉」。帳本寫的理由（「with True the test also passed before the fix」）和我的結果一致。沒有副作用：`VE` 隱藏時面板不讀這個值。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 全套測試（分支 head） | scratch worktree `7812b54`：`python3 -m pytest -q -p no:cacheprovider tests` | 3769 passed，0 skipped，133 s（實作者回報 3744 → 3769，一致） |
| prek | 同一 worktree：`prek run --all-files` | 8 個 hook 全部 Passed，worktree 沒有被改動 |
| 空白檢查 | 分支 worktree：`git diff --check master` | 無輸出，rc 0 |
| 受保護路徑 | `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py addon/synthDrivers/WorldVoice/unicodeScripts/unspaced_common_data.py` | 無輸出 |
| Neural | `git ls-files addon/synthDrivers/WorldVoice/driver/Neural` | 無輸出 |
| 搬移比對（順序敏感） | 自寫腳本 `move_check.py`：取 `master` `discovery.py` 迴圈本體 53 行，去一層縮排、`continue`→`return None`、`ready[spec.name] = voice`→`return voice`、尾端補 `return None`，`difflib.unified_diff` 對 head 的 `load_engine_class` 本體（54 行） | IDENTICAL（無差異行） |
| 內層 `dirname` 層數 | 數 `ve2:90`／`ttsapi:85` 的 `os.path.dirname(` 個數（含 `os.path.join(` 共 10 個左括號） | 兩個內層都是 9 層，與外層 `range(9)` 相同 |
| 外層互不 import | `grep -c "Cerence\|ttsapi" driver/VE/__init__.py`；`grep "driver\.VE\|import VE" driver/Cerence/__init__.py` | 0／0 |
| commit 訊息 | `git log --format='%h %s%n%b' master..HEAD` | 7 個 commit 都是英文 `<type>: <summary>` 加原因；`Co-Authored-By` 0 筆 |
| 設定值不經 `.po` | `git diff --stat master` | 沒有 `nvda.po`／`.pot`／`.mo`；只有 zh_TW readme |

### 手動突變（scratch worktree `review-wt`，`7812b54`；每次突變後 `git checkout -- addon` 還原，最後 `git status --short` 乾淨）

| 編號 | 突變 | 跑的測試檔 | 結果（第一個失敗的就是對應的測試） |
| --- | --- | --- | --- |
| M1 | `panel:` `previousActiveEngine` 改回從 `ENGINE_SPECS` 算 | `test_settings_panels.py` | 3 failed／72 passed：`hides_an_unavailable_engine`、`keeps_a_hidden_engine_flag_on_save`、`without_available_engines_saves_without_asking` |
| M2 | `panel:58` 拿掉 `and self.settings` | 同上 | 1 failed：`without_available_engines_saves_without_asking` |
| M11 | `panel:` `self.settings` 改回從 `ENGINE_SPECS` 建 | 同上 | 4 failed：上述三個加 `refuses_when_only_a_hidden_engine_is_enabled` |
| M3 | VE 與 Cerence `ready()` 都 `return True` | `test_vocalizer_ready.py`、`test_vocalizer_drift.py` | 7 failed：五列 `names_each_missing_file`、兩列 `without_the_workspace_names_every_file` |
| M4 | VE `_nativeFiles` 拿掉 `msvcr110.dll` | 同上 | 4 failed，含 `checks_exactly_what_initialize_loads[VE-…-AMD64]` |
| M5 | Cerence 架構寫死 `"x64"` | 同上 | 1 failed：`checks_exactly_what_initialize_loads[Cerence-2147483647-x32]` |
| M6 | 兩邊 `range(9)` → `range(8)` | 同上 | 12 failed／4 passed（三列守衛測試都失敗） |
| M9 | 兩邊 `log.info` → `log.debug` | 同上 | 7 failed（和 M3 同一組） |
| M7 | `registry:` `available_engine_specs` 直接回 `tuple(ENGINE_SPECS)` | `test_engine_registry.py` | 1 failed：`available_engine_specs_keeps_ready_engines_in_order_enabled_or_not` |
| M8 | `discovery:` `load_enabled_engine_classes` 拿掉 enabled 跳過 | `test_engine_discovery.py`、`test_engine_registry.py` | 2 failed：`enabled_engines_import_from_their_root_and_must_be_ready_and_named`、`ready_engine_classes_loads_only_the_enabled_ready_engines`（既有測試仍守住） |
| M10 | `discovery:` `load_engine_class` 拿掉 `if not is_ready: return None` | 同上 | 3 failed，含 `gives_none_for_each_failure[unready]` |

## 使用者還沒確認的使用者可見預設

spec §2.2 的 D1–D8 都是協調者預設；審閱後我認為值得使用者看一眼的是前四項，其餘照預設即可。

1. **D4：每次檢查都記一行 info，沒有「已經記過」的狀態。** VE 與 Cerence 的 manifest 都是 `defaultEnabled: true`，所以從來沒裝過這兩個驅動語音包的使用者，**每次啟動 NVDA 的日誌都會多兩行** `WorldVoice VE engine is unavailable: missing <三條路徑>`、`WorldVoice Cerence engine is unavailable: missing <兩條路徑>`，每次開語音引擎面板再各一行。這取代了 `master` 上每次啟動的兩段 error traceback，是改善；但如果使用者覺得 info 仍太吵，可選：(a) 維持（建議；info 是 NVDA 預設等級，引擎從面板消失時使用者查得到原因）；(b) 降到 debug（面板消失時一般使用者查不到）；(c) 每行程只記一次（需要加狀態，spec 刻意不加）。
2. **D6：開語音引擎面板時會 import 並詢問每一個發現到的引擎，包括停用的與 WorldVoice-workspace 的外部 plugin。** 停用的外部 plugin 以前只在「啟用並重新啟動」之後才 import；現在第一次開面板就在 GUI 執行緒 import，它的 import 根目錄也會進 `sys.path`。import 失敗只記一行 error、面板照開。選項：(a) 維持（建議；「無法載入」和啟用與否無關，這是 G1 的直接後果）；(b) 只檢查已啟用的引擎、停用的一律顯示（會讓「檔案缺失但停用」的引擎又出現核取方塊，和 G1 相反）。
3. **非目標：隱藏的引擎在設定檔裡仍然是啟用的，面板上沒有辦法把它關掉。** 後果只有第 1 點的 info 行與每次啟動多一次檔案檢查。選項：(a) 維持（建議）；(b) 之後若要讓使用者關掉，需要另一個 UI。
4. **D1：只查檔案存在，不查 `common` 資料夾、不查語音資料。** DLL 在但架構不對或損毀的情況，引擎仍會顯示並在合成器載入時照舊失敗（有 traceback）；只有 `common` 而沒有 DLL、或只有 DLL 沒有語音的情況，前者隱藏、後者顯示但沒有語音。spec 的理由（誤判成不可用比顯示一個沒用的核取方塊更糟）我同意。
5. **D7：一個引擎都沒有時面板只有說明文字與空的群組，按確定不提示也不寫設定。** 實務上 SAPI5 的 `ready()` 永遠回 True，不會碰到。
6. **D8／M1：手冊兩句的用詞**（「WorldVoice-workspace」是否要加「NVDA 使用者設定資料夾」、「記錄檔」或「日誌」、條目放在下載那句之前或之後）。root readme 與 ru／uk／zh_CN／zh_HK 依使用者既有規則之後再同步。

## 未在本平台驗證

Linux 上只驗證了受控的檔案系統與 import 邊界。spec §8 的 Windows／NVDA 手動項目 M1–M5（沒有 `WorldVoice-workspace/VE` 時面板沒有 VE 核取方塊且日誌只有 info 行；檔案齊全時 VE 正常出現並發聲；刪掉 `msvcr110.dll` 後隱藏、補回後重新開面板恢復原本勾選狀態；64 位元 NVDA 上 Cerence 用 `lib/x64` 同樣行為；隱藏但設定檔啟用的 VE 按確定不提示重新啟動）都還沒有在 NVDA 上做過；`PROCESSOR_ARCHITECTURE` 在 32 位元 NVDA／64 位元 Windows 上是 `x86` 這一點也只從 Windows 文件推論，沒有實機確認（內外層讀同一個變數，就算值不同也只會一起對或一起錯）。
