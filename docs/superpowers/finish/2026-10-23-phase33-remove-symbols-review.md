# Phase 33 Review 紀錄：移除 speech symbols、偵測回到基底語言、只算已安裝語音

日期：2026-10-23。分支：`phase33-remove-symbols`（`9d5b8c5..2cd7cf4`，15 個 commit），worktree `/workspace/WorldVoice-phase33`。
依據：

- 規格 `docs/superpowers/specs/2026-10-23-phase33-remove-symbols-design.md`（A／B／C 三部分為使用者決定；§11 的 Q1–Q7 為協調者預設）
- 計畫 `docs/superpowers/plans/2026-10-23-phase33-remove-symbols.md`（Review Focus 1–5；`2cd7cf4` 補上 mutmut 實作筆記）
- 進度帳本 `.superpowers/sdd/2026-10-23-phase33-remove-symbols/progress.md`（6 個 `Ruling:`；批次 1、2 審查各一個 Important，已修）
- 上游偵測器 `ref/VE2(origin)/synthDrivers/vocalizer_expressive2/languageDetection/__init__.py`、回歸前版本 `git show 9816ce0^:…/languageDetection/__init__.py`
- `DEVELOPMENT_WORKFLOW.md` §3.3、§6、§7、§8

流程：審閱者 Fable 5.1，唯讀。測試、還原探針、守門種子、mutant 抽查、Hypothesis 重跑與 coverage 都在 scratchpad 的兩個 `git clone --shared` 複本（`head`、`head2`，都在 `2cd7cf4`，`ref` 以 symlink 接到主 checkout）進行，審完已刪除。pytest 單一行程（本機沒有 xdist），每個探針前都檢查 MemAvailable > 3 GB（全程最低 6.5 GB）。沒有 push、沒有 stash、沒有動主 checkout；本文件是審閱者在任務分支上唯一的 commit。

`file:line` 以 `2cd7cf4` 為準；上游行號以 `upstream:<line>` 標示。

## 結論

Ready to merge：**是。** Critical 0、Important 0、Minor 3（另有 7 個批次審查已延後的 Minor，見下，不重列；其中 M-1 的風險評估更新）。

- **三個部分都達成，偵測邏輯與上游一致，和 spec §2.3／§3.3 逐步對得上。**
  - `_covers`（`languageDetection/__init__.py:110-113`）＝「primary 在 `SCRIPT_LANGUAGES[S]` 且 primary 在 `availableLanguages`」，就是上游 `languageBlocks` 只對已安裝語言建表的效果（`upstream:55-87`、`:149`）。
  - `find_language_for_script`（`:115-133`）的順序：無候選→目前語言→基底語言（原字串）→設定值（需可用）→第一個可用候選→目前語言。第 2 步對應 `upstream:149-151`，第 3 步對應 `upstream:153`＋`:165-166`（`newLang == curLang` 時送出完整 locale），第 6 步保留 WorldVoice 既有的「留在目前語言」（spec 明列的刻意分歧）。
  - `process_for_spelling`（`:172-199`）以 `default_language` 當基底；被刪掉的兩行正規化確實是死碼：能回傳基底 primary 的只有第 2 步（目前語言，依歸納就是基底本身或 primary 不同的語言）、第 3 步（基底原字串）、空白／數字（基底原字串）；第 4、5 步要回傳同 primary 必須基底可用且在候選中，但那時第 3 步已經回傳。`test_property_spelling_runs_of_the_base_primary_carry_the_base` 釘住了這個不變量。
- **用真實 NVDA 序列推演沒有找到回歸。** NVDA 在 `speak` 內先套 `filter_speechSequence`（`ref/nvda/source/speech/speech.py:1137`），再依 `shouldMakeLangChangeCommand()` 在每段文字前補 `LangChangeCommand(curLanguage)`（`:1178-1200`），最後 `processText`（`:1225`）。因此「after」時機的偵測器看到的基底是 NVDA 送來的語言（`trustVoiceLanguage` 開時為主要語音的語言，關時為 NVDA 介面語言，經 `normalizeLanguage` 變成底線形式），「before」時機看到的是合成器語言（可能是 `ar-WW` 這種連字號形式）。兩種來源 `get_primary_language` 都處理（`:96-97`），命令原字串送到下游後 `roles.voice_for`（`roles.py:40-48`）先查原字串再查 primary，所以 `en_GB`／`ar-WW` 都能解析；`deduplicate_language_command`（`pipeline/__init__.py:610-656`）用語音名稱比對，多出來的回基底命令不會變成多餘的 `SelectVoice`。`LangChangeCommand(None)` 走 `command.lang or defaultLang`（`:153`），空字串同樣回到合成器語言。沒有語音的基底（文件標 `de_DE`）：字母走設定值或第一個可用候選，數字仍回 `de_DE`（spec Q6，與上游 `upstream:117-140` 相同）。「忽略數字」開時數字留在目前 run（Review Focus 2）。混合 CJK／拉丁／阿拉伯／西里爾、全形標點（Common 留在目前 run）、假名與諺文先於基底（`ceafd20`）都有測試釘住。
- **Part A 沒有漏掉的使用者可見影響。** `speechSymbols` 的唯一消費者是偵測器的逐字分支（master `languageDetection/__init__.py:152-155`）；pipeline 的數字／符號階段、`speechSettingsDialog.py`、`installTasks.py`、`ref/Neural` 都沒有引用（grep `speechSymbols`／`SpeechSymbols`／`unicode.dic`／`LanguageDetector` 在 `addon/` 只剩測試）。NVDA 自己的符號處理在偵測之前（after）或之後（before）發生的順序沒有改變。`generics/` 沒有 `__init__.py`，`coreArchive` 仍靠合成器的 `sys.path.insert`（`synthDrivers/WorldVoice/__init__.py:56-59`）載入，`4dc379e` 已釘住。
- **生命週期：** 合成器建構失敗注入點從「symbols」換成「detector」（`tests/test_worldvoice_lifecycle.py:91-93`、`:196-220`），仍斷言 bridge 先於 engine 停止；全域外掛的 `terminate`（`globalPlugins/WorldVoice/__init__.py:43-51`）用 `removeMenu()` 整個子選單移除，不依賴項目索引。
- **Review Focus 1–5 都有對應測試且我逐一讀過：** `installed-primary`（`tests/test_language_detector.py:171-178`）、`digits-ignored`（`:163-170`）、`hyphenated-base`（`:228-235`）、`hyphenated-locale`（`:291-298`）、`test_symbols_argument_is_rejected[positional|keyword]`（`:344-356`）。
- **六個 Ruling 都合理**（見下方逐項）。
- **測試真的抓得到它聲稱的錯誤：** 七種還原／突變在 scratch 複本上全部變紅、對應測試名稱和帳本一致（見驗證表）。
- **mutmut：** 抽查三個「等價」存活者（`.get(script, None)`、拼錯 `"Common"`、去掉 `maxsplit`）在全部 55 個偵測器測試下確實存活，而且等價理由成立（`_covers` 只會在 `not candidates` 之後被呼叫；`SCRIPT_LANGUAGES` 沒有 `Common`／`Inherited` 鍵，所以拼錯後走到 `find_language_for_script` 仍回目前語言；`split(...)[0]` 與 `maxsplit` 無關）。另外兩個我自己造的 mutant（基底回傳 primary 而非原字串；數字回目前語言）分別被 14 個與 2 個測試殺掉。
- **翻譯與文件：** zh_TW catalog 只有 120 行刪除、25 個 msgid、無新增，`msgfmt --check` 通過，剩餘內容沒有 `speechSymbols` 殘留；六份 readme 的「忽略常見標點符號」項目與導言的「標點符號」都已移除；EN／zh_TW 新增的一句話語意與程式一致（細節見 M2）。
- **§8：** 15 個 commit 都是 `<type>: <summary>` 英文、內文說明原因、沒有 `Co-Authored-By`；`docs/` 下的 spec／plan 用 `-f` 加入；prek 八個 hook 全數 Passed；ruff 0.16.3；受保護路徑無 diff；沒有 Neural。

## Critical

無。

## Important

無。

## Minor

### M1. `error::DeprecationWarning` 比 spec §1.5 與 `pyproject.toml` 註解描述的範圍更廣：import 時的警告會中斷整個收集，pytest 自己的 deprecation 也算

- **位置：** `pyproject.toml:33-37`（註解寫「A deprecated call fails the test that makes it」）；spec §1.5、§9。
- **情境（審閱者實測）：** 在 scratch 複本放一個在模組層 `warnings.warn("…", DeprecationWarning)` 的測試檔，`pytest tests/<該檔>` 的結果不是「該測試失敗」，而是 `ERROR … DeprecationWarning` ＋ `Interrupted: 1 error during collection`——ini 的 `filterwarnings` 在收集階段同樣生效，所以任何在 import 時觸發的 deprecation（測試模組、`conftest.py`、被測試檔在模組層 import 的 add-on 模組，或 `ref/nvda` stub）會讓整個 suite 一個測試都不跑。另外 `pytest.PytestDeprecationWarning` 的 MRO 含 `DeprecationWarning`（本機 pytest 9.1.1 驗證），所以升級 pytest 後它對 fixture／hook 用法的 deprecation 也會變成錯誤；Hypothesis 的 `HypothesisDeprecationWarning` 繼承 `FutureWarning`，不受影響。
- **影響：** 這是 Q2 刻意要的「升級時立刻看到」，而且目前 suite 0 warnings，所以不影響合併。但 NVDA 升級時若 `ref/nvda` 某個 stub 在 import 時發出 deprecation，看到的會是整個 suite 中斷而不是某個 guard test 變紅，和 spec §1.5 的描述不同，第一次遇到的人容易誤判為環境壞掉。
- **建議：** 在 `pyproject.toml` 的註解補兩句：收集階段也適用（import 時的 deprecation 會中斷整個 suite）、pytest 自己的 `PytestDeprecationWarning` 也算；並寫明逃生口（對單一測試用 `@pytest.mark.filterwarnings("ignore:<訊息開頭>:DeprecationWarning")`，如 `tests/test_pipeline_nvda_symbols.py:19-20` 的做法；臨時診斷用 `-W default::DeprecationWarning`）。spec §1.5 的「fails the test that makes it」順手改成「fails the test that makes it, or aborts collection when it happens at import time」。不改也可以合併。

### M2. readme 新句子把基底語言說成「主要語音角色的語言，或文件標示的語言」，漏掉 NVDA 未信任語音語言時的情況

- **位置：** `readme.md:59`、`addon/doc/zh_TW/readme.md:59`。
- **情境：** 偵測時機為「after」時，基底是 NVDA 在每段文字前補的 `LangChangeCommand(curLanguage)`；`getCurrentLanguage()`（`ref/nvda/source/speech/speech.py:313-322`）只有在 NVDA「信任語音的語言」開啟時才回合成器語言，關閉時回 NVDA 介面語言。例如介面語言 en、主要語音 ja_JP、CJK 設定 zh_TW、信任語音語言關閉、NVDA 自動切換語言開啟：`漢字 hello 漢字` 的第二個「漢字」會走設定值 zh_TW，而不是 readme 所說的主要語音 ja_JP（這與 master 相同，不是回歸，只是文件把條件說滿了）。「before」時機與信任語音語言開啟時，readme 的說法正確。
- **建議：** 可在括號內多一個條件，例如 EN「(the main speech role's language when NVDA trusts the voice's language, otherwise NVDA's language; or the language the document marks)」、zh_TW「（NVDA 信任語音語言時為主要語音角色的語言，否則為 NVDA 的介面語言；或文件標示的語言）」。也可以接受現在的簡化說法，因為 WorldVoice 安裝時預設就信任語音語言。不改不影響合併。

### M3. spec §5 的使用者可見變更漏列「拼字 locale 沒有語音時，空白／數字會切成獨立 run」

- **位置：** spec §3.3 第 4 點只舉 `"a b"` → 三個 run；§5「使用者可見的變更」沒有列。
- **情境：** `process_for_spelling("abc 123 def", "de_DE")`（只裝 en_US、zh_TW）現在是 `[("abc","en"), (" 123 ","de_DE"), ("def","en")]`，`patchedSpeakSpelling`（`synthDrivers/WorldVoice/__init__.py:328-333`）對每個 run 各呼叫一次 `_realSpellingFunc`。NVDA 的拼字本來就每個字元一個 utterance（spec 已指出），所以聽感只差在空白與數字的符號名稱用 de 的 locale，字母用 en——這是 Part C 的直接後果、也和上游一致，但它是 §5 沒有寫出的使用者可見差異。
- **建議：** 在 spec §5 補一條「拼字時若 locale 沒有安裝語音，字母用該字元集可用語言的字元描述，空白與數字仍用 locale 的符號名稱」。純文件，不影響合併。

## 批次審查已延後的 Minor（不重列，只更新一項）

M-1、M-2、M-3、B2-M1、B2-M2、B2-M3、B2-M4 都仍然成立，應在本審查後一併修。補充：

- **M-1（第 6 步只有部分釘住）：** 批次 1 說 `return base_language or current_language` 這個 mutant 會存活。審閱者在 scratch 複本套上它、每次清掉 `.hypothesis` 重跑三次，`test_property_letters_go_to_installed_languages`（`tests/test_language_detector.py:548-559`）三次都殺掉它（隨機抽到「文件標 `de_DE` 無語音＋希臘文無語音」就會插入未安裝的 `de_DE`，違反第一個斷言）。所以風險比批次 1 的描述低，但它靠隨機抽樣；M-1 建議的兩個固定案例（`["中Ελλ"]` en_US／zh_TW → `[<zh>, "中Ελλ"]`、拼字 `"中Ελ"` en_US 一個 run）仍值得加，成本兩行。
- **B2-M2（守門漏掉相對 import）：** 審閱者種子確認 `from .speechSymbols import models` 放在 `addon/generics/coreArchive.py` 時守門通過，其餘五種種子（殘留 `models.py`、絕對 import、`from generics import speechSymbols`、`unicode.dic` 字串）都失敗，目錄完全不存在時守門仍通過（`Path.rglob` 對不存在的目錄回空）。

## Review Focus 與 Ruling 逐項

| 項目 | 審閱者評估 |
| --- | --- |
| RF1 區域變體、primary 有語音（`en_GB`，只裝 en_US） | 成立；`_covers` 以 primary 比對，`installed-primary` 釘住，且 master 與分支同綠（帳本記錄一致）。 |
| RF2 無語音語言後接數字、忽略數字開啟 | 成立；數字留在 `de_DE` run，字母切到 en；`digits-ignored` 釘住。 |
| RF3 連字號基底（`ar-WW`） | 成立；第 3 步回傳原字串，`hyphenated-base` 釘住；下游 `roles.voice_for` 先查原字串再查 primary。 |
| RF4 連字號 spelling locale（`zh-TW`） | 成立；正規化移除後仍靠第 3 步回原字串，`hyphenated-locale` 釘住。 |
| RF5 舊呼叫者傳 symbols | 成立；位置參數與 `speechSymbols=` 關鍵字都 `TypeError`。 |
| Ruling 1 把六份 readme 的標點項目併入 Task 8 | 合理；使用者在執行前的決定，一個 docs commit。 |
| Ruling 2 zh_HK 導言也刪「標點符號」 | 合理；符合「沒有導言承諾標點選項」的意圖；diff 確認六份導言都已改。 |
| Ruling 3 Task 2 讓 symbol 測試先裝 de_DE | 合理；Part C 後「force 到無語音的 de」會被送到 en，測試情境而非斷言改了，Task 5 隨後整個刪掉。 |
| Ruling 4 守門容忍 `__pycache__` | 合理；審閱者在 worktree 看到 `addon/generics/speechSymbols/__pycache__/*.cpython-314.pyc` 確實殘留，Python 不會在沒有 `.py` 時從 `__pycache__` 載入；種子測試證明守門對 `.py` 殘留仍會失敗。 |
| Ruling 5 性質 1、2 各加一個 `@example` | 合理但偏保守；審閱者拿掉兩個 `@example`、清掉 `.hypothesis` 後，去掉基底步驟 5/5 次仍被性質 2 與 3 抓到，去掉可用性檢查 3/3 次被性質 1 抓到。固定例子無害，留著可以。 |
| Ruling 6 性質 1 加上「強形式」 | 合理且必要；spec 原本的弱形式（插入的命令都是已安裝語言）在 master 就成立，只有強形式（字母落在覆蓋它的語言）能抓到缺少可用性檢查。 |

## 審閱者自行驗證的項目

| 項目 | 結果 |
| --- | --- |
| `python3 -m pytest -q -p no:cacheprovider tests`（scratch `head`，`2cd7cf4`） | **2410 passed, 0 skipped**，沒有 warnings 行（71 s）；與帳本相同，較 master 的 2372 多 38 |
| `prek run --all-files`（scratch `head2`） | 8 個 hook 全數 Passed；`ruff --version` 0.16.3，`prek` 0.4.14 |
| `git diff --check master..2cd7cf4` | 無輸出 |
| 受保護路徑：`git diff --stat master..2cd7cf4 -- 'driver/*/driver/' driver/sonic/ script_data.py`；`git ls-files …/driver/Neural` | 兩者皆無輸出 |
| `msgfmt --check -o /dev/null addon/locale/zh_TW/LC_MESSAGES/nvda.po` | exit 0；diff 為 120 行刪除、25 個 `-msgid`、0 新增；多行 msgid「For the edited unicode rule…」是整筆刪除，header 未動 |
| 還原 Part C（`_covers` 去掉可用性） | 7 failed／48 passed：C1、C2、C4、digits-ignored、`prefers_an_available_base[ko_KR-ja]`、`spelling_with_an_unavailable_locale`、性質 1 |
| 還原 Part B（刪第 3 步） | 15 failed／40 passed：R1–R4、hyphenated-base、`prefers_an_available_base[zh_TW]`、三個 spelling 案例、`mixed_scripts`、`spelling_with_locale`、兩個 `one_settings_read`、性質 2、性質 3 |
| 還原 spelling 修正（不傳基底＋恢復正規化） | 3 failed：`spelling_prefers_the_spelling_locale[base-ja|base-zh]`、`spelling_with_locale` |
| 批次 1 I-1 的 M5（基底先於目前語言）與 M10（刪目前語言檢查） | 各 3 failed：`current_language_comes_before_the_base[kana|hangul]`、`spelling_keeps_the_current_language_before_the_locale` |
| 批次 2 I-1：刪 `sys.path.insert(0, base_dir)` | `test_entry_point_imports_real_ledger_and_completion_policy` 失敗（`sys.path[0]` 變成 `tests/`），另 ruff F401 `sys` 未使用 |
| 刪 `filterwarnings` | `test_deprecation_warnings_fail_the_suite` 失敗（1 warning） |
| 模組層 `DeprecationWarning` 探針 | `ERROR … Interrupted: 1 error during collection`（M1） |
| 守門 `test_the_speech_symbols_feature_is_gone` 種子 | 目錄不存在：pass；殘留 `models.py`：fail；合成器加絕對 import：fail；`from generics import speechSymbols`：fail；`addon/generics/coreArchive.py` 加相對 import：pass（B2-M2 已知）；`installTasks.py` 加 `"unicode.dic"`：fail |
| mutmut 存活者抽查（手動套用） | `.get(script, None)`、`"XXCommon"`（spelling 分支）、`split("_")[0]` 三者 55 passed，確認等價 |
| 額外 mutant | 第 3 步回 `get_primary_language(base_language)`：14 failed；數字回目前語言：2 failed；`return base_language or current_language`：性質 1 在 3/3 次 fresh `.hypothesis` 下失敗 |
| Hypothesis `@example` 必要性（拿掉兩個 `@example`，每次清 `.hypothesis`） | 去基底步驟：5/5 次性質 2、3 失敗；去可用性：3/3 次性質 1 失敗 |
| 上游對照 | 逐行比對 `upstream:149-168`（目前→基底，`newLang == curLang` 時送原字串）與 `:176-185`；`pre-9816ce0:196-211`、`:219-228` 相同順序；spelling 路徑 `pre-9816ce0:260` 確實只傳 primary，spec 說「不是回歸」正確 |
| NVDA 序列順序 | `ref/nvda/source/speech/speech.py:1137`（filter）→ `:1178-1200`（補 `LangChangeCommand`）→ `:1225`（`processText`）；`getCurrentLanguage` `:313-322`；`languageHandler.normalizeLanguage` `:444-457` |
| `addon/` 殘留引用 | grep `speechSymbols`／`SpeechSymbols`／`unicode.dic`／`LanguageDetector(`：只剩偵測器本身與測試；`ref/Neural` 無引用 |
| commit 衛生 | 15 個 commit 皆 `<type>: <summary>`，內文有原因，無 `Co-Authored-By`；`4dc379e`、`45b474b`、`2cd7cf4` 同時更新 spec／plan |
| coverage（scratch `head2`，`--cov`） | 見文末「coverage」 |
| 未做 | 未打包；未在 Windows／NVDA 驗證 spec §10.8 的 8 個手動項目（選單兩項、手勢對話框、`unicode.dic` 不被建立或改動、R1／R3 聽感、無德語語音的網頁、拼字描述、log 無 SpeechSymbols 行） |

## 使用者還沒確認的使用者可見預設

spec §11 的協調者預設（合併前可推翻）：

| # | 預設 | 審閱者意見 |
| --- | --- | --- |
| Q1 | 既有 `unicode.dic` 留在設定資料夾不動、不搬、不刪 | 同意；檔名太通用，刪了風險大於益處。 |
| Q2 | `pyproject.toml` 加 `filterwarnings = ["error::DeprecationWarning"]` | 同意，但注意 M1：import 階段的 deprecation 會中斷整個 suite，pytest 自己的 deprecation 也算。 |
| Q3 | 拼字路徑跟偵測一樣先回 locale；刪掉死碼正規化；locale 沒有語音時字母改用可用語言的字元描述、空白與數字仍用 locale（M3） | 同意；兩條路徑現在答案一致。 |
| Q4 | 「可用」＝所有已開啟引擎的已安裝語音（`allLanguages`），不看角色是否指派、不看 KeepMainLocaleEngineConsistent 是否隱藏 | 同意；要看角色會讓偵測器跟著角色設定變動。後果：有語音但沒指派角色的語言仍算可用，文字仍由主要語音讀。 |
| Q5 | 只有 EN 與 zh_TW 的「字元集假設的語言」項目加新句子；ru／uk／zh_CN／zh_HK 不加（留給譯者）；不改 changelog | 同意；但六份 readme 都刪了標點項目，所以 zh_HK／zh_CN 現在和 zh_TW 只差這一句。spec §11 Q5 仍寫標點項目「out of scope」（B2-M1）。 |
| Q6 | 文件標的語言沒有語音時，數字仍切回該語言（主要語音讀） | 同意，與上游相同；是已知限制。 |
| Q7 | `languageDetection/__init__.py` 永久加入 mutmut `source_paths` | 同意；每次 mutmut 多 142 個 mutant。 |

spec 沒有單獨列、但值得使用者知道的使用者可見後果：

1. **「字元集假設的語言」對主要語言已覆蓋的字元集不再生效。** 這是 Part B 的一般規則（spec §5 第 4 點的抽象說法）：主要語音 en_US、拉丁設定 fr 的使用者，在 6.2 聽到 CJK 後面的 `bonjour` 用法語語音，合併後回到 en_US。與上游和 6.2 之前一致，但若有人在 6.2 期間依賴這個回歸調了設定，會覺得「設定沒用了」。readme 新句子有說明。
2. **基底語言以原字串回傳**（`en_GB`、`ar-WW`、`zh_TW`），下游角色查找先用原字串再用 primary，所以指派了 `en_GB` 角色的人現在真的會聽到那個語音（R2）。
3. **拼字時 locale 沒有語音**會把字母和空白／數字拆成不同 run（M3）。
4. **第 6 步仍留在目前語言而不是上游的基底**（例：文件標 `de_DE` 無語音，後接無語音的希臘文，整段留在 `de_DE`→主要語音），spec §4 非目標。
5. **已綁定「popup unicode settings dialog」的手勢**留在 `gestures.ini` 裡變成無作用，不清理，也不會在輸入手勢對話框顯示。
6. **zh_TW catalog 的 25 筆直接刪除**（不是 `#~`），依 `a4629a1` 慣例；其他語言的 catalog 留著無用條目。

## coverage

scratch `head2`（`2cd7cf4`）`python3 -m pytest -q -p no:cacheprovider tests --cov --cov-report=term`：`languageDetection/__init__.py` 91 statements／46 branches 全覆蓋（100%）；TOTAL 7959 statements、243 miss、2292 branches、185 partial，**96%**（帳本記錄 242 miss，差 1 行在隨機測試的分支內，非本階段檔案）。`views.py` 的 omit 已隨檔案移除。
