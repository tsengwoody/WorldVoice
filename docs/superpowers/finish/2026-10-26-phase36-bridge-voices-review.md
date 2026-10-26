# Phase 36 Review 紀錄：`bridge/` 與 `voices/` 套件、單一 primary-language helper

日期：2026-10-26。分支：`phase36-bridge-voices`（`c94623b..6b1364a`，6 個 commit：2 個 docs（spec、plan）、3 個 refactor、1 個 docs（docstring）），worktree `/workspace/WorldVoice-phase36`。
依據：

- 規格 `docs/superpowers/specs/2026-10-26-phase36-bridge-voices-design.md`
- 計畫 `docs/superpowers/plans/2026-10-26-phase36-bridge-voices.md`（5 個 task，Review Focus 5 項，每個 commit 都記了 `HEAD:addon`／`HEAD:tests` tree id）
- 進度帳本 `.superpowers/sdd/2026-10-26-phase36-bridge-voices/progress.md`（8 條 `Ruling:`）
- 路線圖 `storage/refactor8.md` §2.2（F2）、§2.5（F5）、§2.11（F11）、§4.1（A1）、§6「階段 36」
- `DEVELOPMENT_WORKFLOW.md` §3.3、§4.5（複雜流程：在 scratch 複本重放 plan、比對 tree id）、§7、§8

流程：審閱者 Fable 5.1，唯讀。plan 重放在 scratchpad 的全新 clone（`git clone /workspace/WorldVoice`，checkout `c94623b`，`ref` symlink，`prek install`）上用我自己寫的套用器進行，不用實作者的 helper；還原／突變探針在另一個 scratch clone 進行；審完兩個 clone 都刪除。pytest 單一行程，外層有 MemAvailable < 3 GB 就停掉的看門狗（全程沒有觸發）。沒有 push、沒有 stash、沒有動主 checkout、沒有修改分支上的原始碼或測試；本文件是審閱者在任務分支上唯一的 commit。

`file:line` 以 `6b1364a` 為準；`WV/<path>` = `addon/synthDrivers/WorldVoice/<path>`。

## 結論

Ready to merge：**是，但建議先修 I1**（一個測試守門的鬆動，十行以內；不影響產品行為）。Critical 0、Important 1、Minor 3。

- **純搬移成立，沒有 plan 以外的修改。** 我在全新 clone 上從 `c94623b` 照 plan 逐步重放（File／Edit 區塊逐位元組套用、bash 區塊原樣執行），四個 commit 的 tree id 全部和 plan、和分支一致（表格「plan 重放」）；`git diff <重放 HEAD> 6b1364a -- addon tests pyproject.toml` 沒有輸出。由此可知分支上 `addon/`、`tests/`、`pyproject.toml` 的每一個位元組都來自 plan。兩個 docs commit（`2547de8`、`0e9133a`）只動 `docs/`。
- **行為沒有變。** `addon/` 的 diff 只有：import 行（相對層級加一、`compat.`→`bridge.`、五個 voices 模組路徑）、三個 docstring／註解、新檔 `locales.py`、刪掉兩個舊 helper。class／function／attribute 名稱一個都沒改；`driver/__init__.py` 只改 docstring（:1-6）和一行 import（:10），`text/__init__.py` 只改 docstring；`runtime/` 零變動；`tests/test_plugin_voice_contract.py` 零變動。外掛的公開路徑（`synthDrivers.WorldVoice.driver`、`runtime.*`、`text.*`、`driver.sonic`）都在原位：`ref/Neural/Neural/__init__.py:2` 只 import `synthDrivers.WorldVoice.driver`，VE／Cerence 外層（`driver/VE/__init__.py:11-13`、`driver/Cerence/__init__.py:11-13`）只 import `driver`、`text.arabic`、`text.chunker`，照樣解析。
- **依賴方向與 import 週期。** 逐檔看過 import：`runtime/` 只有 `from .x`（不出 runtime）；`bridge/*` 只 import `..runtime`、`.._speechcommand`、`speech.commands`、同套件的 `.indexLedger`；`voices/*` 只 import `..bridge`、`..runtime`、`..locales`、同套件；`locales.py` 零 import（`test_locales_imports_nothing` 守著）；`languageDetection` 多了 `..locales`。沒有逆向邊，沒有循環；`bridge/__init__.py`、`voices/__init__.py` 都是 0 位元組，import 子模組沒有副作用。`bridge/completionPolicies.py:75` 與 `engine/__init__.py:20` 用 `__package__.rsplit(".", 1)[0] + ".driver"` 算路徑：`bridge` 與原本的 `compat` 同深度，結果仍是 `synthDrivers.WorldVoice.driver`。NVDA 載入：synth 套件 `__init__.py:30-33,58-59` import `bridge.*`／`voices.*`；`globalPlugins/WorldVoice/rolePresenter.py:6` 改 import `synthDrivers.WorldVoice.voices.roles`，和以前一樣會先載入 synth 套件，機制不變。
- **沒有殘留舊路徑。** `addon/`、`tests/`、`pyproject.toml`、`sconstruct`、`buildVars.py`、`manifest*.tpl`、`.pre-commit-config.yaml`、`.github/` 用 `compat|nvdaEventBridge|indexLedger|voiceManager|voiceCatalog|mainLocalePolicy|configRepository|getPrimaryLocale|get_primary_language|WorldVoice.roles` 掃過，只剩 `tests/test_locales.py:37,56` 故意寫的兩個舊名（AST 掃描用）與 `bridge/` 內 `.indexLedger`、`voices/` 內 `.roles`／`.mainLocalePolicy` 的同套件 import。`buildVars.py:64-65` 的 `pythonSources` 是 glob（`synthDrivers/*/*.py`、`synthDrivers/*/*/*.py`），新套件在兩層內，翻譯來源不受影響；本階段也沒有新增或改動 UI 字串。mutmut `source_paths` 與 ruff `per-file-ignores`（TRY004）隨檔案搬了，prek 全數 Passed。
- **測試數量算得對。** `master` collect 3213；分支 3219 passed、0 skipped。拿掉 `test_role_repository::test_primary_locale`（1）與 `test_language_detector::test_primary_language_is_the_first_subtag`（6 個參數）共 7 個，`tests/test_locales.py` 新增 10 + 1 + 2 = 13 個。
- **新測試真的抓得到錯誤。** 在 scratch 複本上四種突變（拿掉 None 守衛、加 `import re`、在 `voices/roles.py` 重新定義 `getPrimaryLocale`、把 `lower()` 改 `upper()`）各讓對應的測試變紅（表格「還原／突變探針」）。
- **執行緒與鎖：** 本階段沒有碰任何鎖、callback 或執行緒程式碼（`indexLedger.py`、`nvdaEvents.py` 除了 import 行逐位元組相同）。
- **翻譯：** 無 UI 字串變動，無需翻譯。
- **§8：** 6 個 commit 都是英文 `<type>: <summary>`、內文說明原因、0 個 `Co-Authored-By`；沒有碰 `driver/<Engine>/driver/`、`driver/sonic/`、`script_data.py`、`unspaced_common_data.py`、Neural；`git diff --check master` 乾淨。

## Critical

無。

## Important

### I1. `forbid_legacy_runtime_imports` 對「同套件的相對 import」看不見，比 `master` 鬆

- 位置：`tests/runtime_harness.py:229-243`（`bridge_allowed`、`check`、`guarded_import`）。
- 現象：`check(name)` 拿到的是 `__import__` 收到的**未解析**名稱。`bridge/indexLedger.py`、`bridge/nvdaEvents.py` 現在和 `engineAdapter`／`voiceFacade`／`indexCodec`／`commands`／`completionPolicies` 同套件，若有人在這兩個檔案裡寫 `from .voiceFacade import VoiceFacade`，`name` 是 `"voiceFacade"`、`level=1`，`parts` 裡沒有 `bridge`，守門放行。在 `master` 上同樣的依賴只能寫成 `from .compat.voiceFacade import …`，`name` 含 `compat`，一定被擋。
- 實測（scratch 複本）：
  - G1 在 `bridge/indexLedger.py` 加 `from .voiceFacade import VoiceFacade` → `tests/test_index_ledger.py` + `tests/test_runtime_adapter_contract.py` **99 passed**（應該要紅）。
  - G2 加 `from .engineAdapter import LegacyEngineAdapter` → **99 passed**。
  - G5 在 `bridge/__init__.py` 寫 `from .voiceFacade import VoiceFacade`（spec §2.1／§5.2 明說套件 `__init__` 必須保持空白，但沒有測試守著）→ `test_index_ledger`、`test_runtime_adapter_contract`、`test_nvda_event_bridge` **148 passed**。
  - G3 加 `from .commands import …` 有被擋（27 passed, 72 errors），但原因是 `commands.py:5` import `speech.commands`，撞到 `forbidden` 裡的 `speech`，不是守門認得 `bridge`；G4 寫成 `from ..bridge.voiceFacade import …` 也會被擋（name 含 `bridge`）。
  - 對照 `master`：在根目錄 `indexLedger.py` 加 `from .compat.voiceFacade import VoiceFacade` → `test_index_ledger` **61 errors**，守門有效。
- 失敗情境：將來有人為了方便讓 ledger 或 event bridge 直接用 facade／adapter（都在隔壁，最自然的寫法就是 `from .x import`），「native 引擎只需要 ledger 與 event bridge、不需要 legacy boundary」這個 phase 5 以來的約束就會悄悄失效，而 Review Focus 第 3 項與帳本 Ruling 2 宣稱的「和以前一樣嚴格」不成立。
- 建議修法（我在 scratch 複本試過，守門用到的 7 個測試檔 248 passed；套上 G1 → 80 errors，套上 G5 → 61 errors）：在 `guarded_import` 裡先把相對名稱解析成絕對名稱再檢查：

  ```python
  def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
  	if level and globals and globals.get("__package__"):
  		check(importlib.util.resolve_name("." * level + name, globals["__package__"]))
  	else:
  		check(name)
  	for item in fromlist or ():
  		check(item)
  	return original_import(name, globals, locals, fromlist, level)
  ```

  （`runtime_harness.py:4` 已 `import importlib`；`importlib.util` 需另外 import。）這一改同時涵蓋 G5：`bridge/__init__.py` 內的 `from .voiceFacade` 會解析成 `<alias>.bridge.voiceFacade` 被擋。若想把「兩個 `__init__.py` 保持空白」寫成明文，再加一個 `tests/test_hygiene_guards.py` 風格的斷言（`(WORLDVOICE / "bridge/__init__.py").stat().st_size == 0`，voices 同）也只是兩行。
- 嚴重度說明：這是測試守門的漏洞，不是產品 bug；分支現在的程式碼並沒有這種 import（我逐檔確認過），所以不擋 merge，但修起來便宜，而且 plan 宣稱守住的就是這件事。

## Minor

### M1. 測試 fixture `bridge` 和測試裡到處叫 `bridge` 的 `NvdaEventBridge` 實例撞名

- 位置：`tests/conftest.py:55-73`（fixture `bridge` 回傳 `.adapter`／`.facade` 模組）；對照 `tests/conftest.py:158,260`（`composition.bridge` 是 `NvdaEventBridge` 實例）、`tests/worldvoice_harness.py:176-186`（`bridge_bindings(bridge)` 等 helper 的參數是 event bridge）、`tests/test_worldvoice_lifecycle.py:348`、`tests/test_worldvoice_request_manager.py:85`。
- 現象：同一個字在同一個測試樹裡指兩種東西：套件 `bridge` 的兩個模組，和「the bridge」（事件橋）。目前沒有任何測試函式把 `bridge` 當 event bridge 參數卻意外拿到 fixture（我 grep 了所有 `def …(… bridge …)`），所以不是 bug；但下一個把 `bridge` 寫進參數列的人會踩到。
- 建議：fixture 改名為 `boundary`、`bridge_modules` 或 `bridge_pkg`（`worldvoice_bridge_test` alias 不必動），一次性 sed 24 個使用處。可和 I1 一起做，或留到階段 37。帳本 Ruling 1 選了跟套件同名，這個取捨本身合理，只是和既有用語衝突。

### M2. 守門表留著三個已不存在的名字會造成誤讀

- 位置：`tests/runtime_harness.py:229`（`bridge_allowed = {"indexLedger", "nvdaEvents"}`）與 `:231-234`。
- 現象：`x.compat`、`x.indexLedger`、`x.nvdaEventBridge` 現在都「放行」（我用守門實測），只是因為它們不存在而找不到模組；嚴格度沒有實質差別。但如果將來有人把舊名當 shim 加回根目錄，守門不會叫。
- 建議：不必改程式；若做 I1 的修法，可順手在註解寫明「只有 `bridge.indexLedger`、`bridge.nvdaEvents` 可被 native 契約 import」。

### M3. `tests/test_pipeline_stages.py:323` 註解的行號引用

- 內容改成 `voices/manager.py:295-299`，我對過 `WV/voices/manager.py:295-299` 正是 `getVoiceNameForLanguage`，目前正確。只是提醒：這類行號引用在下一個階段（37 不動 voices，38／39 可能動）會再漂移；用函式名取代行號更耐久。不必在本階段改。

## 帳本 `Ruling:` 的評估

| # | Ruling | 評估 |
| --- | --- | --- |
| 1 | `compat` fixture → `bridge`（alias `worldvoice_bridge_test`）、`test_models_load_without_nvda_or_compat` → `…_or_bridge` | 合理：識別字跟著套件名走。只有 M1 的撞名問題，不影響正確性。 |
| 2 | 守門擋 `bridge.*`，放行 `indexLedger`、`nvdaEvents` | **對實際存在的模組名，接受／拒絕集合和 `master` 一一對應**（我用守門實測：`x.bridge`、`x.bridge.{commands,completionPolicies,engineAdapter,indexCodec,voiceFacade}` 全擋；`x.bridge.{indexLedger,nvdaEvents}` 放行；`master` 上 `x.compat`、`x.compat.*` 擋、根 `indexLedger`／`nvdaEventBridge` 放行）。**但對「同套件相對 import」比以前鬆**，見 I1；Ruling 說的「cost if wrong: guard slightly looser」正是發生的情況。 |
| 3 | 7 個測試項搬進 `test_locales.py`（13 個），3213 → 3219 | 數字核對無誤（`master` collect 3213，分支 3219 passed）。測試搬家合理：一個 helper、一個測試家。`test_locales.py` 的 10 個參數 case 是兩組舊 case 的聯集加 `None`，Hypothesis 測試對 `aZ-_ßİ` 字母表上長度 ≤ 8 的字串逐一比對兩個舊實作，`ß`／`İ` 覆蓋了 `lower()` 的非 ASCII 行為。 |
| 4 | `primary_language` 保留 `getPrimaryLocale` 的 empty／None 守衛；detector 端 `None` 從 AttributeError 變成回傳 None | 合理，且實務上不可達。roles 端：`ConfigRoleRepository.voice_for(language)`（`WV/voices/roles.py:34-36`）可以收到 `None`（`pipeline/__init__.py:936` `cmd.lang or ctx.default_voice_language`，NVDA `VoiceInfo.language` 型別是 `str | None`），行為和以前相同。detector 端六個呼叫點（`languageDetection/__init__.py:108,112,127,161,178,209`）的值來源：`availableLanguages` 來自 `VoiceManager.allLanguages` = `catalog.all_languages`（已經過 `group_by_primary_locale`，是字串）；`self._language()` 是 NVDA `SynthDriver._get_language` → `availableVoices[voice].language`（`ref/nvda/source/synthDriverHandler.py:253-254`），WorldVoice 的 `VoiceInfo` 由 `VoiceSpec.language` 建（`WV/voices/catalog.py:40`），而所有內建 wrapper 的 `voices()` 都走基底 `Voice.voices` → `voiceInfoToMetadata`（`WV/driver/__init__.py:38,67-68`），`localeName = voice.language or "unknown"`，不會是 None；`curLang = command.lang or defaultLang`、`default_language = locale if locale is not None else self._language()` 都回退到它。唯一能送 None 進來的是覆寫 `voices()` 的外掛給 `language=None`，那在 `master` 上每句話都會在 filter 裡拋 AttributeError，現在則安靜地當成「沒有主語言」。這是「原本會當機的路徑不再當機」，不是使用者可見行為的改變；spec §5.3 標為可被使用者推翻的預設，列在下方。 |
| 5 | `composition` fixture 多 `package`，用 `__package__.removesuffix(".voices")` 回到 alias 根 | 正確：`load_source` 以 `<alias>.voices.manager` 註冊，`__package__` 是 `<alias>.voices`。只在測試內。 |
| 6 | `pyproject.toml` 的 ruff ignores 與 mutmut `source_paths` 跟著搬 | 必要且正確；prek 與 `test_hygiene_guards::test_ruff_reports_nothing` 都過。pyproject 不在 tree id 裡，我用重放 clone 的 diff 確認和分支一致。 |
| 7 | harness／測試檔名保留（`load_config_repository`、`test_index_ledger.py`、`test_nvda_event_bridge*.py`、`test_voice_manager_structure.py`、`test_voice_config_repository.py`） | 合理：它們以 class 命名，spec §3 non-goal 也這麼寫。 |
| 8 | 第一次 dry run 在 Task 2 Step 7 失敗（`git add` 寫到被 `git mv` 移走的舊路徑），plan 改成只列新路徑後重做 | 我的重放用的就是修正後的 plan，Task 2／3 的 commit 區塊一次成功，tree id 吻合。 |

## plan 的 Review Focus 逐項

1. **None／空／混合分隔的 locale**：讀碼見 Ruling 4；`test_primary_language_is_the_first_subtag` 的 `None`、`""`、`sr-Latn-RS`、`zh_Hant_TW`、`ZH-tw` 都在，突變 M1／M4 證明會紅。
2. **alias 套件下深一層的相對 import**：`test_main_locale_policy`、`test_role_repository`、`test_voice_config_repository`、`test_nvda_event_bridge*` 在重放的 Task 2／3 聚焦執行（486、380 passed）與全套件都綠；`test_role_repository.py:8-10` 新增 `alias_package` 是因為 `roles.py` 現在有相對 import，必要。
3. **守門**：見 I1。
4. **NVDA 進入點**：`test_runtime_composition::test_entry_point_imports_real_ledger_and_completion_policy` 斷言新 `__file__` 路徑（`:647-648`），`test_runtime_drain_integration` 走 `voices.manager`，都綠；import 圖見結論第三點。
5. **`rolePresenter` 路徑**：`test_role_presenter.py:30-34` 把 `synthDrivers.WorldVoice.voices.roles` 放進 `sys.modules`，`:27-28` 先 stub 父套件，綠。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 全套件（分支 worktree） | `python3 -m pytest -q -p no:cacheprovider tests`（看門狗外層） | **3219 passed**，0 skipped，96 s |
| 基準數量 | `master` 上 `pytest --collect-only -q` | 3213 collected |
| prek | `prek run --all-files`（分支 worktree） | 8 個 hook 全數 Passed；之後 `git status --short` 無輸出（hook 沒改檔） |
| 空白字元 | `git diff --check master` | 無輸出 |
| 受保護路徑 | `git diff --stat master -- 'WV/driver/*/driver/' WV/driver/sonic/ WV/languageDetection/script_data.py WV/pipeline/unspaced_common_data.py`；`git ls-files WV/driver/Neural` | 兩者皆無輸出 |
| 外掛契約測試 | `git diff master --stat -- tests/test_plugin_voice_contract.py` | 無輸出 |
| commit 格式 | `git log master..HEAD --format=%B \| grep -i co-authored` | 無；6 個 commit 皆英文 `<type>: <summary>` 加內文 |
| 兩個 docs commit 範圍 | `git show --stat 2547de8 0e9133a` | 各只動一個 `docs/` 檔 |
| **plan 重放** | 全新 clone 於 `c94623b`，自寫套用器逐步套 Task 1–4 的 File／Edit／bash 區塊 | Task 1 red：`3 failed, 10 errors`；green：`103 passed`；commit → `b165bfb…`／`30c8ca3…` ✔。Task 2 grep 無殘留；`486 passed`；commit → `f2ef46a…`／`390f412…` ✔。Task 3 grep 無殘留；`380 passed`；commit → `6b026b0…`／`e74d2f8…` ✔。Task 4 commit → `9d4a7b0…`／`e74d2f8…` ✔。四個 commit 的 prek hook 都一次通過。`git diff <重放 HEAD> 6b1364a -- addon tests pyproject.toml` **無輸出**。分支四個 refactor／docs commit 的 `git rev-parse <sha>:addon <sha>:tests` 與 plan 逐一相同。 |
| 歷史可追 | `git log --follow -- WV/bridge/nvdaEvents.py \| tail -1`；`WV/voices/settingsRepository.py` 同 | `0b433d1 refactor: isolate NVDA speech event bridge`；`148c47c refactor: separate voice settings persistence and editing` |
| 空的 `__init__.py` | `git cat-file -s master:WV/compat/__init__.py`；`wc -c WV/bridge/__init__.py WV/voices/__init__.py` | 0、0、0 |
| 殘留舊名 | 見結論第四點的 grep（含 `sconstruct`、`buildVars.py`、`manifest*.tpl`、`.pre-commit-config.yaml`、`.github/`） | 只剩 `tests/test_locales.py:37,56` 的刻意引用 |
| 守門接受／拒絕集合 | 在 `forbid_legacy_runtime_imports` 下 `importlib.import_module` 14 個名字，分支與 `master` 各一次 | 分支：`x.bridge`、`x.bridge.{commands,completionPolicies,engineAdapter,indexCodec,voiceFacade}`、`x.driver` 擋；`x.bridge.{indexLedger,nvdaEvents}`、`x.voices.manager`、`x.pipeline` 放行；`master`：`x.compat`、`x.compat.*` 擋，`x.indexLedger`、`x.nvdaEventBridge`、`x.voiceManager` 放行 |
| **還原／突變探針**（scratch clone，只跑對應測試） | M1 刪 `locales.py` 的 `if not locale: return locale` | `test_locales.py` 1 failed（`None` case） |
| | M2 在 `locales.py` 加 `import re` | 1 failed（`test_locales_imports_nothing`） |
| | M3 在 `voices/roles.py` 末尾重新定義 `getPrimaryLocale` | 1 failed（`test_no_other_module_defines_a_primary_language_helper`） |
| | M4 `lower()` → `upper()` | 9 failed（8 個有字母的參數 case + Hypothesis） |
| | G1 `bridge/indexLedger.py` 加 `from .voiceFacade import VoiceFacade` | `test_index_ledger` + `test_runtime_adapter_contract` **99 passed**（漏接，I1） |
| | G2 同上改 `from .engineAdapter import LegacyEngineAdapter` | **99 passed**（漏接，I1） |
| | G3 同上改 `from .commands import normalize_legacy_commands` | 27 passed, 72 errors（被 `speech` 擋到，非 `bridge` 規則） |
| | G4 同上改 `from ..bridge.voiceFacade import VoiceFacade` | 19 passed, 80 errors（被擋） |
| | G5 `bridge/__init__.py` 寫 `from .voiceFacade import VoiceFacade` | 加 `test_nvda_event_bridge` 共 **148 passed**（漏接，I1） |
| | 對照 `master`：根 `indexLedger.py` 加 `from .compat.voiceFacade import VoiceFacade` | `test_index_ledger` 61 errors（被擋） |
| I1 建議修法試套 | 在 scratch clone 改 `guarded_import` 解析相對名稱 | 無突變：7 個守門相關測試檔 248 passed；套 G1 → 80 errors；套 G5 → 61 errors；還原後 `git status` 乾淨 |
| import 圖 | grep `bridge/`、`voices/`、`runtime/`、`locales.py`、`languageDetection/__init__.py`、`driver/__init__.py`、`rolePresenter.py` 的所有 `from`／`import` | `voices → bridge → runtime`、`voices → locales`、`languageDetection → locales`、`driver → bridge.voiceFacade`；`runtime/` 無外部相對 import；無循環 |
| `__package__` 算路徑 | `WV/bridge/completionPolicies.py:75`、`WV/engine/__init__.py:20` | `rsplit(".", 1)[0]` 從 `…WorldVoice.bridge` 回到 `…WorldVoice`，與 `compat` 同深度 |
| 未做 | 打包、Windows／NVDA 實機、mutmut | 未做。spec §7 說明本階段無新邏輯（兩行 helper 由 Hypothesis 對兩個舊實作比對），不需 mutmut；無行為變更，不需 Windows 驗證。 |

## 使用者還沒確認的使用者可見預設

- **`primary_language(None)` 在 language detector 端回傳 `None` 而非拋 `AttributeError`**（spec §5.3，「Decided by orchestrator with the recommended default; user may override before merge」）。影響範圍：只有覆寫 `voices()` 且給 `language=None` 的第三方外掛才會走到；在 `master` 上那會讓每一句話的 filter 拋例外，現在則當成沒有主語言。內建六個引擎與 Neural 走 `voiceInfoToMetadata`，`language` 永遠是字串，使用者不會察覺差別。審閱者建議接受。

除此之外，本階段沒有任何設定鍵、confspec、預設值或 UI 字串的變動；升級的使用者所有設定保留。

## 給修正者的備註

- 若修 I1／M1，`tests/` 會改、`addon/` 不會，所以 `HEAD:tests` tree id 會變；依 §4.5 在 plan 檔尾加「## 修正」段落，寫出 `Edit:` 區塊和 commit 後的 tree id，並從 Task 4 的 tree 接著 dry run。
- 我的 scratch clone（`review36/replay`、`review36/mutate`）審完已刪除；重放用的套用器只解析 plan 的 `### Task N:`／`- [ ] **Step S:`／`**File:**`／`**Edit:**` 標記，和實作者的 helper 互不相依。
