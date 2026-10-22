# feat/symbol-locale-and-settings-fallback Review 紀錄

日期：2026-10-22。分支：`feat/symbol-locale-and-settings-fallback`（`b244821..7c67961`，10 個 commit）。
依據：

- 規格 `docs/superpowers/specs/2026-10-22-feat-symbol-locale-and-settings-fallback-design.md`
- 計畫 `docs/superpowers/plans/2026-10-22-feat-symbol-locale-and-settings-fallback.md`（含 Review Focus 與 Mutation results）
- 進度帳本 `.superpowers/sdd/2026-10-22-feat-symbol-locale-and-settings-fallback/progress.md`（含 Ruling）
- 使用者決定檔 `next-symbol-locale.md`（協調者 scratchpad；決定不重開，只查是否照做）

流程：最後的 Fable 5.1 review（DEVELOPMENT_WORKFLOW.md §3.3），唯讀；測試與突變實驗都在 scratchpad 的暫時 worktree 做，做完已移除。

## 結論

Ready to merge：**修正 Important 1 之後可以**。Critical 0、Important 2、Minor 5。

程式本體與使用者的決定一致：語音 locale 優先、無語音用預設語音、`normalizeLanguage`、`symbols.dic` 存在檢查、每次 stage run 每語言快取一次、每個 pipeline 鍵各自回退、不寫回、每鍵每值一則 `debugWarning`、`group_size` 2..10 之外讀成 3。對照真正的 NVDA 原始碼（`ref/nvda` `7d25bc76e`），`read_stored` 依賴的三件事都成立：`AggregatedSection._cacheLeaf` 每次讀都驗證（`config/__init__.py:1269-1273`），驗證失敗不進快取所以每次讀都再拋，`get` 只接 `KeyError`（`:1250-1254`）。唯一的落差是 spec 自己寫的「下一次面板存檔會把預設值寫回檔案」在實作上不成立（Important 1）。

## Important

### Important 1：回退後的面板存檔不會修好 `nvda.ini`

- **位置：** `addon/synthDrivers/WorldVoice/pipeline/settings.py:403-409`（`PipelineSettingsService.update`），對照 `:339-357`（`read_stored`）。
- **情境：** `nvda.ini` 裡 `group_size = 11`。NVDA 啟動，`load` 讀到 3 並記一則警告；面板顯示 3；使用者按確定。`speechSettingsDialog.py:187` 把顯示的每個值交給 `update`，`update` 先 `current = self.get()`（已經是回退後的 3），再用 `getattr(current, key) != value` 篩掉「沒變」的鍵，於是 `changed` 是空的，**什麼都不寫**。檔案裡仍是 11，每次啟動 NVDA 都再警告一次；`VoiceSettingsDialogs.py:209, 232` 和設定環（`__init__.py:496`）走同一條路。只有使用者把值改成別的數字才會寫回。
- **對照：** spec 3.3「The next save of a panel rewrites the key」、spec 4 表尾「The next panel save writes the shown (default) value into the file」、spec 7 手動項目 4「saving the panel fixes the file」、使用者決定 Q3 A「the file is fixed on the next panel save」。實作沒有做到最後一句。
- **驗證：** 用 harness 的 `RefusingSection` 存 `group_size = 11` 並拒絕讀取，`get().group_size == 3`，再以面板的方式 `update(**全部顯示值)`，section 仍是 `{'group_size': 11, 'number_wait_factor': 40}`。NVDA 這一側沒有障礙：`AggregatedSection.__setitem__` 比對舊值時用 `checkValidity=False`（`config/__init__.py:1355-1365`），所以真的寫 3 的話會成功寫入。
- **建議：** 讓 repository 記住上一次 `load` 回退了哪些鍵（例如 `read_stored` 多收一個 `on_fallback` callback，或 `ConfigPipelineRepository.load` 順便填 `self.fallen_back: set[str]`），`update` 把這些鍵一律放進 `changed`（值等於要寫的預設）。先寫會失敗的測試：拒絕 `group_size` 的 section，`update(group_size=3)` 後 `section["group_size"] == 3`、listener 被呼叫一次。若使用者改為接受「只有改成別的值才會修檔」，則要改 spec 3.3、spec 4、手動項目 4 與 Q3 的描述，並列入未確認預設。

### Important 2：測試分不出「語音 locale」和「語音語言」

- **位置：** `tests/test_pipeline_voice_lookup.py:67-78`，fixture 在 `tests/conftest.py:75-76`。
- **情境：** composition fixture 的語音只給 `language`（`("a", "en")`、`("b", "zh")`），`compat/engineAdapter.py:133` 讓 `locale` 預設等於 `language`，所以 `VoiceSpec.locale == VoiceSpec.language`。把 `voiceManager.py:304` 改成 `return spec.language if spec is not None else None`，`test_pipeline_voice_lookup.py`、`test_worldvoice_speak.py`、`test_worldvoice_pipeline_settings.py` 共 34 個測試全綠。這個功能的重點正是全 locale（`zh-TW`）而不是裸碼（`zh`），卻沒有任何測試釘住 `getVoiceLocaleForLanguage` 回傳的是 locale。
- **建議：** 給 fixture 的一個語音不同的 `locale`（例如 `b`：`language="zh"`、`locale="zh-TW"`，看 `conftest.py` 的 driver stub 怎麼餵 `voice.get("locale")`），斷言 `getVoiceLocaleForLanguage("zh") == "zh-TW"`，並確認 `getVoiceNameForLanguage` 等現有斷言不受影響。

## Minor

### Minor 1：`_has_symbol_table` 的路徑守門沒有被測試證明

- **位置：** `addon/synthDrivers/WorldVoice/pipeline/__init__.py:105-106`；測試 `tests/test_pipeline_nvda_symbols.py:183-199`。
- **情境：** 測試列的 `".."` 和 `"../en"` 分別解析成 `appDir/symbols.dic` 和 `appDir/en/symbols.dic`，兩個本來就不存在，所以有沒有 `isalnum` 守門結果都是 False。把 `:105-106` 兩行刪掉，`test_pipeline_nvda_symbols.py` 44 個測試全綠（自行植入的突變）。Review Focus 1「a path such as `../en`」因此只是形式上覆蓋。
- **建議：** 加一列真的會穿越的值，例如 `"../locale/en"`（`appDir/locale/../locale/en/symbols.dic` 存在），預期 False。順帶一提 `str.isalnum` 也接受非 ASCII 字母，但那種字串組不出 `..`、`/`、`\`，無害。

### Minor 2：`ValidateError = Exception` 的保底會吞掉真正的 bug

- **位置：** `addon/synthDrivers/WorldVoice/pipeline/settings.py:10-18`。
- **情境：** 在 NVDA 裡到不了這個分支：NVDA 自己 `from configobj.validate import ValidateError`（`argsParsing.py:47`），configobj 由 `pyproject.toml:400` 釘住，`tests/test_nvda_config_guards.py` 也釘住了。但一旦到了（例如未來 configobj 改名），`read_stored` 會把 `section.get` 裡任何例外（`AttributeError`、`TypeError`）都當成「值無效」記一則 debug 警告然後回預設，真正的 bug 會被藏起來。
- **建議：** 保底改成一個永遠不會被拋出的類別（`class ValidateError(Exception): ...`，附註解說明沒有 configobj 時 NVDA 本身也跑不起來），或至少在那個分支用 `log.error` 而不是靜默。測試 `test_validate_error_comes_from_configobj[None]` 要跟著改預期。

### Minor 3：警告去重的 memo 不分 section、不會清除

- **位置：** `addon/synthDrivers/WorldVoice/pipeline/settings.py:336-356`。
- **情境：** `_reported` 是模組層級的 set，鍵只有 `(key, message)`。(a) `log`、`engine` 面板的勾選框和 pipeline 鍵共用它：不同 section 的同名鍵若存了同一個無效值，整個 NVDA 工作階段只警告一次。(b) 值修好之後再壞成同樣的字串，不再警告。(c) 「檢查再加入」不是原子操作，但最壞只是多印一行。大小以不同的無效值計，只有改檔才會增加，有界。
- **建議：** 可接受；若要精確，把 `section.path`（NVDA 的 `AggregatedSection` 有）或呼叫端給的 section 名稱放進鍵。不修也行，列為已知。

### Minor 4：spec 行號與「pipeline thread」的說法

- **位置：** spec 2「`get` catches only `KeyError` (`:1246-1250`)」實際在 `config/__init__.py:1250-1254`；`_cacheLeaf` 在 `:1269-1273`。純文字。
- **執行緒：** 本次 review 的交辦提到 `getVoiceLocaleForLanguage` 從 pipeline thread 呼叫。實際上 stage 是 `speech.extensions.filter_speechSequence` 的 handler（`pipeline/__init__.py:19, 965-971`），在 NVDA 主執行緒跑，和既有的 `getVoiceNameForLanguage` 同一條線，沒有新的鎖需求。唯一的跨執行緒情況是 `_setVoiceDatas` 在 `voiceManager.py:303` 的兩次 `self.catalog` 讀取之間換掉 catalog（引擎重載），這時名字來自舊目錄、spec 查新目錄，查不到就回 `None` 走舊規則，無害。成本：`roles.voice_for` 兩次 dict 查詢、`voice_infos` 的 `in`、`by_name.get`，每個 stage run 每語言一次（`_symbol_namer` 快取），可忽略。

### Minor 5：`_has_symbol_table` 比 NVDA 嚴格，但結果相同

- **位置：** `addon/synthDrivers/WorldVoice/pipeline/__init__.py:97-107`。
- **情境：** NVDA 的 `_getSpeechSymbolsForLocale` 只要有兩個字典就接受一個 locale（`characterProcessing.py:413-426`）；`user` 字典永遠算一個（`:819-826`，USER 來源不拋錯），`cldr` 預設啟用（`configSpec.py:42`）。安裝版 NVDA 的 `locale/` 裡 `af_ZA as gu id kok ml mni ne te th ur` 只有 `cldr.dic` 沒有 `symbols.dic`（`include/nvda-cldr/locale` 對照 `source/locale/*/symbols.dic`），NVDA 會接受這些 locale，本分支會拒絕而走舊規則。但這些 locale 本來就沒有內建符號名，`×`、`.` 在 CLDR 字典裡也查不到，所以兩條路唸出來一樣（舊規則下裸碼同樣落到同一個 locale）。使用者自己的 `symbols-<locale>.dic` 單獨存在時 NVDA 也不接受，檢查不會誤拒。
- **建議：** 不必改；在 `_has_symbol_table` 的 docstring 補一句「只認內建表；只有 CLDR 的 locale 沒有符號名，結果相同」即可。

## Ruling 評估

| Ruling | 評估 |
| --- | --- |
| Task 3：`_run_logged` 的測試放在 `tests/test_pipeline_filters.py` | 合理，和 `test_run_logged_records_only_when_switched_on` 共用 `env`。 |
| Task 4：`test_worldvoice_speak.py` 的假 VoiceManager 加 `getVoiceLocaleForLanguage` | 必要；`speech_context` 從每個 manager 讀這個方法。 |
| Task 5：同檔加 `languageHandler` 與 `globalVars.appDir` stub | 必要；pipeline 套件新增兩個 import。 |
| Task 7：兩個測試檔的 parametrize id 改 ASCII（`da29e37`） | 合理。`test_number_and_group_modes_name_each_symbol` 在 master 與分支都收集到 36 個案例，12 列 id 互不重複，`SPEC_TABLE` 本身沒動；真實查表測試的兩個 id 是新測試。 |
| Task 7：刪除剛產生的 `mutants/` | 只刪自己產生的檔案，符合 §8。 |

## Review Focus 逐項

1. 不像 locale 的語音 locale：`""`、`x-western`、`zh-Hant-TW` 由 `test_symbol_locale_prefers_the_voice_locale_with_a_table` 覆蓋；路徑案例只是形式（Minor 1）。
2. 兩句之間換語音：`test_namer_asks_each_language_once_per_run` 證明快取只活在一個 `_symbol_namer`，`inject_number_mode` 每次 run 新建一個（`:494`）。
3. 一個壞鍵：`test_load_reads_the_default_for_each_invalid_key` 對每個鍵逐一驗證其他鍵仍是存的值；`test_a_new_invalid_value_warns_again` 證明換值會再警告。
4. 沒有目錄項目的語音名：`test_voice_locale_is_none_for_a_voice_without_a_spec`。
5. filter 裡的壞開關：`test_an_invalid_log_switch_reads_off` 證明 stage 照跑且不記錄。

## mutmut 存活者

- `x__has_symbol_table__mutmut_7`（`replace("_", "XXXX")`）：等價。`"XXXX"` 是字母數字，`isalnum` 答案只在 locale 全是 `_` 時不同，而那種 locale 接下來 `isfile` 也是 False。
- `x__symbol_locale__mutmut_15`（`"XX_XX" not in locale`）：等價。含 `_` 的 locale 不可能等於 `current.split("_")[0]`，`"_" not in locale` 只是說明意圖。

## 和 master 相比的行為差異

- 預設使用者（設定有效、`group_size` 3）：只有數字／分組模式裡數字內符號的名字會變：語音有帶國家的 locale 且 NVDA 有該表時用該表。例如 OneCore `zh-TW` 語音在英文 NVDA 下 `2×3` 從「times」變「乘以」；zh_CN 語音在 zh_TW NVDA 下從「乘以」變「乘号」（使用者決定第 1 點）。值模式、關閉模式、scope「all」與其他合成器不變。
- 舊版存了 `group_size = 1` 的使用者：master 讀成 2，本分支由 NVDA 拒絕後讀成 3 並記一則 debug 警告（使用者決定「不放寬、拿掉 `stored_min_value`」）。
- 存了無效值的使用者：master 載入 WorldVoice 會失敗，本分支載入成功、該鍵用預設。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 完整測試 | `python3 -m pytest -q tests -p no:cacheprovider`，單一程序，MemAvailable < 3 GB 即終止的監控 | 2307 passed、0 skipped、2 warnings（`codecs.open`，既有）、62 s |
| prek | `prek run --all-files`（prek 0.4.14） | 8 個 hook 全數 Passed，沒有改到檔案 |
| 空白 | `git diff --check master` | 無輸出 |
| 受保護路徑 | §7 的兩個指令 | 皆無輸出 |
| Co-Authored-By | `git log master..HEAD --format=%B \| grep -i co-authored` | 無 |
| 跨驅動 import | 對分支改動的 `addon/` 檔案 grep `synthDrivers.WorldVoice.driver` | 無 |
| 還原 `5bf22a7`（`read_stored`）的原始碼 hunk | 暫時 worktree，`git apply -R` 只還原來源檔 | `test_read_stored_returns_the_default_for_an_invalid_value_and_warns_once` 失敗 |
| 還原 `90ce6ca`（`group_size` 範圍） | 同上 | `test_group_size_confspec_is_its_range` 失敗 |
| 還原 `9a72ba1`（log 讀取） | 同上 | `test_an_invalid_log_switch_reads_off` 失敗 |
| 還原 `be1509b`（locale callback） | 同上 | `test_voice_locale_follows_the_voice_for_the_language` 失敗 |
| 還原 `13d5801`（symbol locale） | 同上 | `test_has_symbol_table_matches_nvdas_locale_dir[zh_TW-True]` 失敗 |
| 自行植入的突變（14 個） | 同一個暫時 worktree，逐一套用後跑對應測試 | 12 個被殺：namer 對 `None` 也問、去掉警告 memo、memo 不看值、`_run_logged` 直接 `section[label]`、面板改回 `.get`、service 改回 `["enable"]`、拿掉 `_has_symbol_table` 檢查、`inject_number_mode` 不用 ctx 的 callback、`speech_context` 不接 callback、`convert` 只重設上界、`_get_value` 預設 `None`、`language` 不跟隨語言命令。**2 個存活**：`getVoiceLocaleForLanguage` 回 `spec.language`（Important 2）、刪掉 `_has_symbol_table` 的路徑守門（Minor 1） |
| 面板存檔是否修檔 | scratch 腳本，`RefusingSection` 拒絕 `group_size`，以面板方式 `update` 全部顯示值 | section 仍是 `{'group_size': 11, ...}`（Important 1） |
| ASCII id 案例數 | 在 master 與分支 `pytest --collect-only -q` 該測試 | 36／36；12 個 id 互不重複 |
| NVDA 驗證路徑 | 讀 `ref/nvda/source/config/__init__.py:1179-1273, 1321-1373, 537-575` | 讀取時 `_cacheLeaf` 驗證、失敗不快取、`get` 只接 `KeyError`；`__setitem__` 比對舊值不驗證；啟動時 `profile.validate` 只驗 `BASE_ONLY_SECTIONS`，不含 WorldVoice；profile 切換會重建 `rootSection`，`read_stored` 沒有自己的值快取，不受影響 |
| `ValidateError` 來源 | `argsParsing.py:47`、`pyproject.toml:31,400` | NVDA 從 `configobj.validate` import，configobj 釘在 git rev `9c8a0a8`；`Exception` 保底在 NVDA 裡到不了 |
| `normalizeLanguage` | `languageHandler.py:444-457` | `-`→`_`、語言小寫、國家大寫、`x-` 給 `None`；harness 用的是 NVDA 原函式 |
| `appDir` | `nvda.pyw:39-59` | 原始碼執行是 `source/`，安裝版與可攜版是 `sys.prefix`，`locale/` 都在其下 |
| characterProcessing 還看哪裡 | `characterProcessing.py:880-945, 413-426, 808-826` | builtin（必要）、cldr、add-on 字典、user 字典；只有 CLDR 的 locale 會被 `_has_symbol_table` 拒絕但結果相同（Minor 5） |
| 其他直接讀 pipeline／log section 的地方 | grep `["pipeline"]`、`["log"]`、`[self.field]` | 只有 `settings.py:371`（repository）、`pipeline/__init__.py:884-887`、`pipelineLog.py:22-26`、`speechSettingsDialog.py:92`（已在 `try/except Exception` 內）與 `:104`；`sayAll.py`、`_PipelineSetting`、`VoiceSettingsDialogs` 都經 `pipeline_settings` |
| 暫時 worktree 清理 | `git worktree list` | 只剩 `/workspace/WorldVoice` 與 `/workspace/WorldVoice-feat-symbol-locale` |

Linux 上只驗證了 harness 與 `ref/nvda` 的純 Python 部分；Windows 上的 NVDA、真正的 configobj 錯誤訊息、OneCore 回報的 locale 字串（`zh-TW`）都沒有驗證到，spec 7 的手動項目仍要做。

## 使用者還沒確認的使用者可見預設

1. **回退後面板存檔不修檔**（Important 1）：目前要把值改成別的數字才會寫回；若不修，`nvda.ini` 裡的無效值會留著，每次啟動都記一則 debug 警告。使用者決定 Q3 的最後一句（「the file is fixed on the next panel save」）寫的是會修。
2. **D2**：語音 locale 是裸碼（`zh`）時走舊規則（借 NVDA 介面的國家，否則 NVDA 自己的 fallback）。決定檔記為「no objection」，spec 標為協調者採建議預設。
3. **D4／D5**：只有數字內的符號名改變；NVDA 自己的 `LangChangeCommand` 在 WorldVoice 內也套同一規則。同樣是「no objection」。
4. **警告只在 debug 等級**：`log.debugWarning` 在預設的 info 等級看不到，使用者不會知道自己的設定被改回預設，直到打開面板。D3 決定「no UI prompt」，但沒說等級。
5. **舊的 `group_size = 1` 變 3 而不是 2**：使用者決定拿掉 `stored_min_value`，這是其結果，列出供確認。

## 工作區備註

主 checkout 在 review 開始前就有的未提交變更（`M buildVars.py`、`D docs/superpowers/finish_task.md`、`?? DEVELOPMENT_WORKFLOW.md`、`?? diff.md`）與本分支無關，未動。
