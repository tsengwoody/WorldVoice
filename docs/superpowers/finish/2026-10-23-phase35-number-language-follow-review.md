# Phase 35 Review 紀錄：數字跟隨文字語言、數字語言決定每一個數字

日期：2026-10-23。分支：`phase35-number-language-follow`（`da7f791..56cbbfc`，21 個 commit），worktree `/workspace/WorldVoice-phase35`。
依據：

- 規格 `docs/superpowers/specs/2026-10-23-phase35-number-language-follow-design.md`（七個部分與三個細節為使用者決定；§4.4 的修訂與 §13 Q11 為協調者預設；U1–U3 為批次 2 審查後的使用者決定）
- 計畫 `docs/superpowers/plans/2026-10-23-phase35-number-language-follow.md`（Review Focus 1–5；文末「Implementation notes: mutmut and coverage」）
- 進度帳本 `.superpowers/sdd/2026-10-23-phase35-number-language-follow/progress.md`（8 個 `Ruling:`；批次 1 的 C1 與 M1–M3、批次 2 的 I1→U3 與 M1–M4 都已修）
- NVDA 來源 `ref/nvda/source/speech/speech.py`、`autoSettingsUtils/autoSettings.py`、`driverHandler.py`、`synthSettingsRing.py`、`extensionPoints/__init__.py`
- `DEVELOPMENT_WORKFLOW.md` §3.3、§6、§7、§8

流程：審閱者 Fable 5.1，唯讀。測試、還原探針、hand mutant、語料比對與 Markdown 轉檔都在 scratchpad 的 `git clone --shared` 複本進行（`head`＝`56cbbfc`、`base`＝`f7915a2`（phase 35 第一個程式變更之前的特徵化 commit，harness 已有 `speak_through_stages`）、`clean`＝`56cbbfc` 只跑 prek 與 hand mutant；`ref` 都以 symlink 接到主 checkout），審完已刪除。pytest 單一行程（本機沒有 xdist），每個探針外層都有 MemAvailable < 3 GB 就停掉 pytest 的看門狗（全程沒有觸發，起始 7.1 GB）。沒有 push、沒有 stash、沒有動主 checkout；本文件是審閱者在任務分支上唯一的 commit。

`file:line` 以 `56cbbfc` 為準。

## 結論

Ready to merge：**修掉 I1 之後是。** Critical 0、Important 1（文件轉檔，改兩行即可）、Minor 3。

- **七個目標都達成，實作與 spec 對得上。** 「default」＝跟隨當前文字語言（偵測器對十進位數字一律回 `current_language`，`languageDetection/__init__.py:138-146`）；「main」與 locale 在偵測執行的地方包裝（`pipeline/__init__.py:322-391`），早期階段對 `default`／`main` 都是 pass-through（`:304-319`）；數字模式的符號命名把 `main` 歸入「語言在力」那一邊（`:427-429`）；拼字依數字語言（`languageDetection/__init__.py:176-183`、`:185-209`）；`numlan` 的 setter 與 getter 都只接受 `default`／`main`／目前可見的 locale（`__init__.py:477-491`）；`ignoreNumbersInLanguageDetection` 從 confspec、服務、面板、zh_TW catalog 與六份 readme 全部移除，`tests/test_hygiene_guards.py:134-142` 守門；數字定義三個 regex 與 `number_pieces` 都改成 Unicode `\d`／`isdecimal()`（`pipeline/numbers.py:14-28`、`:81`）。
- **用真實 NVDA 流程推演與語料比對沒有找到未記錄的回歸。** 我在 `f7915a2`（舊行為：`default`＋忽略數字關＝今天的「main」、忽略數字開＝今天的「default」）與 `56cbbfc` 上，用同一支探針跑 56 段文字 × 5 組設定（value／標點停頓／number 模式／group 模式／數字停頓 50）× 主要語音 en／zh × 時機 after／before × 四種數字語言（main、follow、zh_TW、en）＝ 4480 次，每次都經過 NVDA 真正的 `characterProcessing.processSpeechSymbols`（level some）當作 `processText`，記錄「NVDA 收到的項目」與「每個語音讀到什麼」。413 次「聽到的」不同，全部落在 spec 已記錄、使用者已決定的五類：(1) 字詞後的連字號留在字詞上（U1/U2：`COVID-19`、`中-1`、`a-1`、`中+5`，只影響 locale 數字語言）；(2) 空格後的正負號隨數字走（Q5：`中 -12`、`abc -3 def`、`價格是 -3 度`、`中. -5`，只在 before 時機有差，after 時機 NVDA 已先把 `-` 讀成 minus）；(3) Option B 的數字集合（`中１２３`、`abc１２３`、`٣٫١٤`、`1٢3`、`１２,３４５` 的千分位與分段）；(4) `²`／`₂`／`①` 不是數字，留在目前語言（§4.7 項 2）；以及 after 時機＋locale 數字語言時符號名稱裡的數字換語音（U3：`x²`、`H₂O`、`10²`、`①`）；(5) `[L(de_DE), "abc 12 中"]` 在 before 時機少一個項目切分（語音相同，只是 `abc 12 ` 不再被切成兩段送 NVDA，比舊行為更接近未偵測的項目）。「follow」的差異只有第 (3) 類；「main」沒有任何一段文字在 after 時機與舊的「忽略數字關」不同，除了 (3)(4)。
- **rejoin（`detect_with_number_language`）的不變量成立。** 包裝物件由 `wrap_numbers_for_detection` 新建，`detect` 是偵測器的 generator，逐一 `yield command` 不換物件；`detected = list(detect(list(wrap(...))))` 讓臨時 list 活到 `detected` 建完，所以就算未來的偵測器丟掉包裝，`detected` 裡沒有任何物件能拿到已釋放包裝的 id（id 只在 `detected` 與 `deduplicate_language_command(detected)` 的輸出上比對）。我試過的破壞情境：空字串（兩邊都被丟，與偵測器本身一致）、`["", "12", " "]`、相鄰數字項目 `["12", "34"]`、`["中", "12", "中"]`、`["中12", "34 abc"]`、Index／Break 命令、`LangChangeCommand(None)`、`LangChangeCommand("zh_TW")`、早期階段包裝與偵測包裝疊在一起（`<zh_TW> <zh_TW> '12' <zh_TW> <en>`）、偵測器在數字後插入自己的切換，全部與基準相同或只差 spec 記錄的類別。「語音在項目中間改變」只會由偵測器插入的命令造成，而 `glue` 遇到任何非字串就歸零，所以不會跨命令接合（`:383-389`）。模擬去重從 `ctx.language`／預設語音起算，與 `speak()` 真正的去重起點相同；在 before 時機 NVDA 之後會丟掉或重寫 `LangChangeCommand`，但被移除的包裝都「命名語言在力」或「對應同一個語音」，數字無論如何跟前面的文字同語音，所以移除不改變任何語音決定。
- **Review Focus 1–5 都有對應測試且我逐一讀過並確認會變紅：** 1 `MAIN_ROWS[index]`（`tests/test_worldvoice_speak.py:386`）；2 `MAIN_ROWS[empty]`（`:387`）與 `test_wrap_numbers_for_detection_drops_empty_texts`（`tests/test_pipeline_stages.py:421`）；3 `test_main_moves_a_sign_with_its_number[wait-*]`（`:489`、`:503`，E13 探針就是它抓到的）；4 `test_a_locale_the_voices_no_longer_offer_is_refused_on_load`（`:597`）與 `test_a_locale_hidden_after_it_was_stored_reads_as_follow`（`:606`，E4 探針抓到）；5 `test_decimal_digits_never_switch_the_language[abc-arabic-indic]`（`tests/test_language_detector.py:358-360`）與 `test_spelling_keeps_arabic_indic_digits_in_a_latin_run`（`:415`）。
- **八個 Ruling 都合理**（逐項見下）。
- **測試真的抓得到它聲稱的錯誤：** 20 種還原／突變在 scratch 複本上，除了兩個真正等價的（E15、E20，見驗證表）其餘全部變紅，第一個失敗的測試名稱和帳本一致。
- **mutmut 26 個「等價」存活者的理由我逐一核對：** `"+-"`→`"XX+-XX"`（被測字元是 match 的第一個字，只會是正負號或數字）、`"number"` 標籤改名（呼叫端只測 `kind == "text"`）、`number_re` 沒傳下去（所有呼叫端都用預設）、`glue = None`（只用真假值）、初始 `glue = True`（第一個項目前面沒有東西可接；`result` 空時 `result and …` 為假）、以及 phase 33 已記錄的 18 個偵測器存活者。另外 `number_pieces` 的 `isdecimal()`→`isdigit()`（E15）也等價：token 來自 `NUMBER_TOKEN_RE`，只會是 `\d` 或 Latin-1 P/S 符號，`²³¹` 是 No 類別不在 `SYMBOLS` 裡。
- **翻譯與文件：** zh_TW catalog 新增兩條、刪除一條，`msgfmt --check` 通過；「跟隨當前文字語言」「跟隨文件主要語言」是使用者給的詞；六份 readme 的忽略項目與導言的「數字」都移除；英文與 zh_TW 的數字語言說明和更新日誌語意與程式一致（連字號、全形數字、預設改變與還原方法）。**但新加的那一段「Numbers include…」在 scons 的 Markdown 轉檔下把後面的清單吃掉了（I1）。**
- **§8：** 21 個 commit 都是 `<type>: <summary>` 英文、內文說明原因、沒有 `Co-Authored-By`；`buildVars.py` 在分支上沒有變動（主 checkout 的未提交修改不在分支裡）；prek 八個 hook 全數 Passed；ruff 0.16.3；受保護路徑無 diff；沒有 Neural；`git diff --check` 乾淨。

## Critical

無。

## Important

### I1. readme 新段落讓「數字模式」「語音停頓調整」整段清單在打包後的 HTML 變成一段純文字

- 位置：`readme.md:48`、`addon/doc/zh_TW/readme.md:48`。
- 情境：`sconstruct:113-127` 把根目錄 `readme.md` 複製成 `addon/doc/en/readme.md`，再用 Python-Markdown（`buildVars.markdownExtensions` 只有 `tables`）把每份 readme 轉成 NVDA「附加元件說明」用的 HTML。Python-Markdown 要 4 個空格才算清單項目的延續；`readme.md:48` 只縮 2 格、`zh_TW/readme.md:48` 只縮 1 格，所以這一句變成獨立段落；而下一行 `* Number mode:` 前面沒有空行，在 Python-Markdown 裡清單不能打斷段落，於是「Number mode」「Off／Numeric／Digit／Group」「Pause adjustment」（zh_TW：「數字模式」四個子項與「語音停頓調整」）全部被吞進這個 `<p>`，帶著字面上的 `*`。我用 markdown 3.11 轉檔確認：`master` 的輸出是 `<li>Number mode:</li><li>Off: …</li>…`；`56cbbfc` 的輸出是 `<p>Numbers include … * Number mode:\n  * Off: …</p>`。GitHub（CommonMark）看不出來，NVDA 使用者按「說明」會看到。
- 建議：把這一句改成同層的子項目（兩份都改，縮排跟同檔其他子項目一樣）：
  ```
    * A specific language: numbers are always read by the speech role of that language.
    * Numbers include full-width digits (０–９) and other Unicode decimal digits, such as Arabic-Indic digits.
  * Number mode:
  ```
  （zh_TW 同樣改成 ` * 數字包括全形數字…`，並刪掉前面的空行。）我用 markdown 3.11 驗證過這樣會保持 `<li>` 連續。另一個做法是整段改用 4 格縮排並在段落後留空行，Python-Markdown 會產生真正的巢狀清單，但那會改到既有風格，不建議在本階段做。

## Minor

### M1. 英文說明一句兩個冒號；zh_TW「阿拉伯-印度數字」用 ASCII 連字號

- `readme.md:45`：「Follow document main language: numbers are read in the main language: the language the document marks, or the main speech role's language.」建議「…are read in the main language, that is, the language the document marks or the main speech role's language.」
- `addon/doc/zh_TW/readme.md:48`、`:76`：中文裡夾 ASCII `-`，建議「阿拉伯－印度數字」或「印度－阿拉伯數字」（全形破折號）。純文字風格，不影響行為。

### M2. 暫時被藏起來的 locale 會在下一次設定檔切換時被改寫成「default」，之後任何一次設定存檔就永久遺失

- 位置：`addon/synthDrivers/WorldVoice/__init__.py:485-491`（`_set_numlan`）、`:480-483`（`_get_numlan`）。
- 情境：使用者選了數字語言 zh_TW，之後把主要語音換成另一個引擎的英文語音，「Keep main locale engine consistent」把 zh_TW 從 `voiceManager.languages` 藏起來。`_get_numlan` 讀成 `default`（批次 2 的 M1 修正，正確）。接著只要 NVDA 切換一次設定檔（`synthDriverHandler.handlePostConfigProfileSwitch` → `loadSettings(onlyChanged=True)`，有 app profile 的使用者切視窗就會發生），`autoSettings._loadSpecificSettings` 看到 config 的 `zh_TW` 與目前的 `default` 不同，呼叫 `_set_numlan("zh_TW")`，被拒絕後 `_numlan` 變成 `default` 並記一筆 warning；再來任何一次設定存檔（不只 spec §7.1 說的 Voice 面板 `onSave`：`config.pre_configSave` 在 `AutoSettings.__init__` 註冊了 `saveSettings`，NVDA 結束時存檔、Ctrl+S 存檔都會觸發）就把 `default` 寫回檔案。使用者換回中文主要語音後，zh_TW 的偏好已經不在了。phase 35 之前 `zh_TW` 會留在檔案裡（藏起來時數字送到主要語音，換回來就恢復）。spec Q7 由使用者決定「在 setter 依目前的選項驗證」，且 §7.1 已寫「藏起來的 locale 在下一次載入時視為無效」，所以這是已接受的後果；但「設定檔切換＋任何存檔就永久遺失」這條路徑 spec 沒寫出來。
- 建議（請使用者定奪）：`_set_numlan` 接受 `allLanguages`（任何已安裝語音的語言）裡的 locale，只拒絕完全不存在的值；`_get_numlan` 維持對 `languages` 的讀取時對應，面板與設定環仍然正常。或者只在 spec §7.1 補上這條路徑與「存檔時機包含 `pre_configSave`」。

### M3. 每句話讀兩次 `voiceManager.languages`

- 位置：`__init__.py:371`（`speech_context`）與 `:332-339`（`_detect_languages` 再呼叫一次 `speech_context()`），經 `_get_numlan` → `_is_number_language` → `voiceManager.py:283-285` 的 `sorted(group_by_primary_locale(self._visible_table()))`。
- 情境：數字語言是 locale 時（`default`／`main` 被 `or` 短路），每個 `speak()` 都重新把整張語音表分組排序一到兩次。表通常幾十到幾百筆，微秒到毫秒級，不會聽得出來；只是 phase 33 之前這裡只讀一個欄位。
- 建議：之後若要省，`_is_number_language` 改查 `localeToVoicesMap` 的 key 或在 voice manager 快取 `languages`；本階段不必動。

## 審閱者自行驗證的項目

| 項目 | 指令／方法 | 結果 |
| --- | --- | --- |
| 全部測試（`head` 複本，`56cbbfc`） | `python3 -m pytest -q -p no:cacheprovider tests`，看門狗 MemAvailable ≥ 3 GB | **2588 passed、0 skipped、0 warnings**，82 s（基準 master 2413） |
| prek（`clean` 複本） | `prek run --all-files` | 8 個 hook 全數 Passed（ruff 0.16.3） |
| diff check | `git diff master..HEAD --check` | 無輸出 |
| 受保護路徑與 Neural | `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py`；`git ls-files addon/synthDrivers/WorldVoice/driver/Neural`；`git diff --stat master..HEAD -- buildVars.py` | 三個都無輸出 |
| 翻譯 | `msgfmt --check -o /dev/null addon/locale/zh_TW/LC_MESSAGES/nvda.po` | 通過；`#:` 行號（`settings.py:72`、`:75`）與原始碼相符 |
| commit 衛生 | `git log master..HEAD --format='%h\|%an\|%s'` 與 `%b` grep `co-authored\|signed-off` | 21 個 commit 都是 `<type>: <summary>`，沒有 trailer |
| 語料比對（`base`＝`f7915a2` vs `head`） | 自寫 pytest 探針：56 段文字 × 5 設定 × 2 主要語音 × 2 時機 × 4 數字語言 ＝ 4480 次，經 NVDA 真正的 `characterProcessing`（level some），記錄 NVDA 收到的項目與各語音讀到的文字 | 兩邊都 0 例外；413 次聽感不同、383 次項目不同，全部屬於 spec 記錄的五類（見結論）；「main」在 after 時機與舊「忽略數字關」只差 Option B 與 `²` 類；「follow」只差 Option B |
| 文件轉檔 | markdown 3.11 + `tables`，轉 `master` 與 `56cbbfc` 的 `readme.md`、`zh_TW/readme.md` | `master`：數字模式等為 `<li>`；`56cbbfc`：被吞進 `<p>`（I1）。建議的子項目寫法驗證過會保持 `<li>` |
| E1 關掉連字號規則（`_split_numbers_for_language` 的條件改 `False`） | 5 個相關測試檔 | 1 failed：`test_main_moves_a_sign_with_its_number[covid-after]` |
| E2 關掉 rejoin（`glue = False`） | 同上 | 1 failed：`test_numbers_reach_nvda_in_their_item_where_the_voice_stays[en-main-covid-before]` |
| E3 偵測器數字回 `base_language` | 同上 | 1 failed：`test_follow_language_numbers[zh12-after]` |
| E4 `_get_numlan` 不驗證 | 同上 | 1 failed：`test_a_locale_hidden_after_it_was_stored_reads_as_follow` |
| E5 `_set_numlan` 不驗證 | 同上 | 1 failed：`test_an_unknown_number_language_reads_as_follow[zz]` |
| E6 拼字數字一律用拼字 locale | 同上 | 1 failed：`test_spelling_digits_follow_the_number_language[default-expected0]` |
| E7 數字模式把 `main` 當 locale 命名符號 | 同上 | 1 failed：`test_main_language_numbers[number-mode-after]` |
| E8 `NUMBER_RE` 退回 `[0-9]` | 同上（`clean` 複本） | 見下方補記 |
| E9 偵測包裝把 `main` 當 locale | 同上 | 1 failed：`test_wrap_numbers_for_detection_wraps_every_match[value]` |
| E10 不移除任何包裝（`kept = set(joins)`） | 同上 | 1 failed：`test_numbers_reach_nvda_in_their_item_where_the_voice_stays[en-main-covid-before]` |
| E12 拼字 `isdecimal`→`isdigit` | 同上 | 1 failed：`test_spelling_keeps_a_superscript_in_its_run`（帳本 M2 的說法成立） |
| E13 連字號規則 `start > 0`→`>= 0` | 同上 | 1 failed：`test_main_moves_a_sign_with_its_number[wait-after]` |
| E14 `THOUSANDS_RE` 退回 `[0-9]` | 同上 | 1 failed：`test_thousands_separators_of_other_digits[１２,３４５-…]` |
| E15 `number_pieces` `isdecimal`→`isdigit` | 同上 | 494 passed：等價 mutant（token 只會是 `\d` 或 Latin-1 P/S，`²³¹` 不在其中） |
| E16 早期包裝把 `main` 當 locale | 同上 | 1 failed：`test_number_segments_with_main_wrap_in_the_current_language` |
| E17–E20 hand mutant（`joins` 旗標 `>=`／`<=`、`LangChangeCommand(None)` 不回 `ctx.language`、`glue = joins[...]`） | 同上（`clean` 複本） | 見下方補記 |
| rejoin 不變量 | 讀 `pipeline/__init__.py:358-391` 與 `languageDetection/__init__.py:148-171`；語料裡的 `empty`、`empty-blank`、`num-items`、`zh-num-items`、`two-items`、`index`、`break`、`tagged-*` 列 | 見結論第三點；沒有跨命令或跨項目的接合 |
| 設定環與無效值 | 讀 `ref/nvda/source/synthSettingsRing.py:74-103`、`autoSettings.py:173-207`、`driverHandler.py:43-50` | 藏起來或無效的值經 `_get_numlan` 讀成 `default`，環與面板都找得到；`terminate()` 後的 `saveSettings`（`pre_configSave`）在 master 已經會在 `_get_rate` 碰到 `None`，本階段沒有新增失敗點 |
| Unicode 偵測面板 | `tests/test_unicode_panel.py` 四個控制項順序；`speechSettingsDialog.py:501-560` 只剩 `script_language`／`timing` 的讀寫；`tests/test_detection_settings.py:158-166` 舊 key 仍在 section 時 `get()` 正常 | 通過 |
| Hypothesis 性質 | 讀 `tests/test_pipeline_pause_properties.py`（字母表含 `１２٣٤۵۶१२`、`²①٫`，oracle 改 `isdecimal`）、`tests/test_worldvoice_speak.py:730-770`（end-to-end 每個數字的語音）、`tests/test_language_detector.py` 的 `digits never start a run`／拼字性質 | oracle 不是套套邏輯：end-to-end 用「最近一個字母的語音／主要語音／指定語音」獨立推算 |

補記（E8、E17–E20 在 `clean` 複本的結果）：

| 探針 | 結果 |
| --- | --- |
| E8 `NUMBER_RE` 退回 `[0-9]` | 1 failed：`test_full_width_digits_are_numbers[after]` |
| E17 `joins[id(opening)] = start >= 0` | 1 failed：`test_detection_rejoins_what_the_wrappers_split_where_the_voice_stays[items]` |
| E18 `joins[id(closing)] = position <= len(item)` | 1 failed：同上 |
| E19 偵測包裝遇到 `LangChangeCommand(None)` 不回 `ctx.language` | 1 failed：`test_wrap_numbers_for_detection_tracks_language_commands` |
| E20 `glue = joins[id(item)]`（不帶前一個包裝的旗標） | 494 passed：等價 mutant。兩個連續被移除的包裝只會是「前一項目的關閉包裝＋下一項目的開頭包裝」（兩個旗標都是 False；同一項目裡兩個數字之間一定有文字），或早期階段包裝旁邊的重複（旗標也是 False），所以 `or` 永遠不會改變結果。不是測試缺口。 |

## 帳本 Ruling 逐項評估

| # | Ruling | 評估 |
| --- | --- | --- |
| 1 | 先做 late stage 與 `main`（Task 3–4）再改偵測器（Task 5），與 spec §11 的順序不同 | 合理：每個中間 commit 都保持「main＝今天的忽略數字關」特徵化測試綠燈；最終狀態相同。 |
| 2 | `NUMBER_LANGUAGE_CHOICES` 留在 `pipeline/settings.py` 並從 `..numberLanguage` 匯入；harness 用別名套件載入 | 合理：值只有一個定義（spec §4.5），`numberLanguage.py` 零匯入由 `tests/test_pipeline_structure.py` 的新測試守門。 |
| 3 | 面板 checkbox 與設定 key 同一個 task（Task 6）移除 | 合理：`update(ignore_numbers=…)` 改成 `TypeError` 後面板的 `onSave` 不能有中間狀態。 |
| 4 | Task 2 的 speak-level 全形測試改用 `abc１２３`＋zh_TW，spec §3 的 `中１２３`＋en 列移到 Task 4 | 合理：英文主要語音時 en 包裝被早期去重丟掉（§4.2 第二個陷阱），那一列要到偵測包裝才會綠；兩列現在都釘住。 |
| 5 | 批次 1 C1 修正：包裝改到偵測執行處，去重會丟的包裝事後移除並把同一項目的兩段接回 | 合理且是本階段的核心：語料比對證實「語音不變時 NVDA 收到的項目與 phase 35 之前相同」。風險（id 鍵）如上分析成立，也已在 `:375-376` 註明。 |
| 6 | `COVID-19 疫情` 在中文主要語音＋before 時機讀成「負 19」 | 已被 U1 撤回；現在 `COVID-`／`19 疫情`，`HYPHEN_ROWS[zh-covid]` 釘住基準的項目。 |
| 7 | mutmut 的 glob 改成 `x_detect_with_number_language*`、`x_wrap_numbers_for_detection*`、`x__split_numbers_for_language*` 等 | 合理：涵蓋 C1 與 U2 之後實際被改的每個函式；`_get_numlan`／`_set_numlan` 不在 `source_paths`，由 E4／E5 探針補驗。 |
| 8 | 英文更新日誌用 UI 標籤「Ignore numbers when detecting text language」而不是 spec 的「during language detection」 | 合理：使用者找的是面板上看到的字；zh_TW 用「偵測語言時忽略數字」同理。列入下方待確認。 |

## 使用者還沒確認的使用者可見預設

1. **Q11，包裝在偵測執行處（協調者預設）。** 後果：before 時機只有語音真的改變的地方 NVDA 才會看到切分（`COVID-19 cases`、`the 1st item`、`Is it 5?` 整個項目送 NVDA）；after 時機包裝發生在 `processText` 之後，所以符號名稱裡的數字會換語音（U3 已由使用者接受）。語料比對沒有發現這個預設引入未記錄的差異。
2. **Ruling 8：** 更新日誌以 UI 標籤稱呼被移除的選項（英文與 zh_TW）。
3. **`+` 也算「字詞後的連字號」。** U1/U2 的決定寫的是「a sign right after a word character」，實作與測試把 `+` 一併納入：`中+5`、`C+1` 在 locale 數字語言下現在是 `中+`／`5`，phase 35 之前是 `中`／`+5`（讀「plus 5」）。spec 的例子只有 `-`。
4. **I1 的修法**（子項目 vs 4 格縮排）由使用者挑；兩種都驗證過。
5. **M2** 的取捨（setter 接受 `allLanguages` 的 locale，或只補文件）。

## 沒有列為問題、但值得知道

- `tests/test_language_detector.py:345` 仍以字面寫入舊 key `ignoreNumbersInLanguageDetection`，是刻意證明「存了也沒人讀」；hygiene guard 只掃 `addon/` 與 readme，所以不衝突。
- spec §4.6 的 T 表仍是第一版 late stage 的「After the stages」寫法，§4.6 開頭已註明要讀成「偵測收到的東西」；可讀性問題，不影響正確性。
- Windows／NVDA 上的 M1–M7（spec §11.7）本審查沒有做；特別是 M3（全形與阿拉伯-印度數字在 VE／OneCore／eSpeak 的實際朗讀，含 NVDA Unicode 正規化開關）與 M5（number 模式下「點」的語音），在 Linux 上無法驗證。

## 工作區備註

review 開始前就存在的主 checkout 未提交變更，與本階段無關，未動：`M buildVars.py`、`D docs/superpowers/finish_task.md`、`?? DEVELOPMENT_WORKFLOW.md`、`?? diff.md`。

## 修正記錄

修正於 2026-10-23，每項先寫會失敗的測試（文件類用 Markdown 3.11 實際轉檔比對），再修正。完整驗證：`python3 -m pytest -q tests` 2589 passed、0 skipped、0 warnings；`prek run --all-files` 全數 Passed；`git diff --check master` 乾淨；受保護路徑與 `buildVars.py` 無 diff；沒有 Neural；`.po` 本輪未變動。

- **I1（已修，`7deeefd`）：** `readme.md` 與 `addon/doc/zh_TW/readme.md` 的「Numbers include…」／「數字包括…」改成數字語言底下的子項目，照各檔既有的子項目縮排（英文兩格、zh_TW 一格），並刪掉前面的空行。用 markdown==3.11（scons 的設定，只開 tables）轉檔：修正前英文版有 1 處、zh_TW 版有 2 處「`* 數字模式`」之類的星號變成純文字；修正後 0 處，且與 `master` 的 HTML 比對，差異只剩本階段的文字（數字語言說明、Unicode 偵測導言與移除的項目、「下一版更新」）。
- **M1（已修，`c3f7103`）：** 英文「Follow document main language」改成「numbers are read in the main language, that is, the language the document marks or the main speech role's language.」，一句一個冒號；zh_TW 兩處「阿拉伯-印度數字」改為「阿拉伯－印度數字」。spec §9 的對應文字（含 I1 的子項目寫法）一起更新。
- **M2（已修，`eff9292`；spec `51eb046`）：** setter 改為接受 `default`、`main` 與 `voiceManager.allLanguages` 中的任何 locale（所有已安裝語音，包括「主要地區引擎一致」暫時藏起來的），所以設定檔切換時的 `loadSettings(onlyChanged=True)` 不再把它換成 default。協調者原本的指示是 getter 保留讀取時的對應；但 NVDA 的 `saveSettings` 寫回的正是 getter 的值（`autoSettingsUtils/autoSettings.py:159-163`），getter 若回傳 default，存檔時仍會蓋掉使用者的選擇，所以改成：getter 回傳儲存的值，`availableNumlans` 在它被藏起來時仍列出它（語音設定面板與設定環都找得到目前的值），只有朗讀（`speech_context()`）與拼字的提供者把目前不可見的 locale 當成 default。不在 `allLanguages` 的值仍存成 default 並發出 debugWarning。紅燈測試：`test_a_hidden_locale_survives_loading_and_saving_and_comes_back`（兩種順序：載入時已被藏、載入後才被藏），修正前 2 個都失敗；原本的 `test_a_locale_the_voices_no_longer_offer_is_refused_on_load` 改為 `test_a_locale_of_an_uninstalled_voice_is_refused_on_load`，`test_a_locale_hidden_after_it_was_stored_reads_as_follow` 由新測試取代。spec §7.1 與 Q7 標註「Decided by orchestrator with the recommended default; user may override before merge」。
  - Ruling: getter 回傳儲存值而不是讀取時對應成 default，並讓選項清單在被藏時列出它——否則 NVDA 存檔仍會遺失選擇，與 M2 要修的問題相同——錯了的代價：被藏起來的 locale 會出現在數字語言清單裡，直到使用者換掉它。
- **M3（不修）：** 便宜，沒有可量測的成本；照協調者指示保留。
