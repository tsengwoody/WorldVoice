# docs/translations-7.1 Review 紀錄

日期：2026-11-07。分支：`docs/translations-7.1`（`5933a45..93d7593`，7 個 commit），worktree `/workspace/WorldVoice-translations-7.1`。
依據：

- 參考文件：使用者定稿的 `addon/doc/zh_TW/readme.md`（`5933a45`）。
- 上一輪翻譯 pass：`docs/translations-7`（merged `a4ee7ec`）。zh_TW 自 `a4ee7ec` 以來的變更以 `git diff a4ee7ec 5933a45 -- addon/doc/zh_TW/readme.md` 為準。
- 流程：DEVELOPMENT_WORKFLOW §3.3，Fable 5.1 唯讀審閱。

## 結論

Ready to merge：**Yes**。Critical 0、Important 0、Minor 3（皆為可選的小修，其中兩項是上一輪就存在的文字，這個分支沒有動到）。

- 四份 readme（英文、ru、uk、zh_CN）每一段都對照 zh_TW 逐段比過：zh_TW 新增的段落都有、zh_TW 刪掉的細節都刪了、沒有多出 zh_TW 沒有的新內容、意思沒有錯。「文字種類」「Unicode 文字類型」在各語言都譯成 Unicode script（en script、ru письменность、uk писемність、zh_CN 文字种类／文字类型）。
- zh_HK readme 與 zh_TW 逐位元組相同。
- 七份 `.po` 只含預期的變更；用 `scons pot` 重新產生 `.pot` 後再 `msgmerge`，七份都沒有差異，證明 msgmerge 是對最新的來源做的。
- 超出範圍的「Group size」改名（zh_HK、zh_CN）建議**保留**，理由見下。

## Critical

無。

## Important

無。

## Minor

### M1：數字模式的符號名稱例子，英文／ru／uk 比 zh_TW 多了「例如 dot、dash」

- `readme.md:49`：`… are read by their names, such as "dot" or "dash", in the number language.`
- `addon/doc/ru/readme.md:49`：`… читаются по своим названиям, например "точка" или "дефис", на языке чисел.`
- `addon/doc/uk/readme.md:49`：`… читаються своїми назвами мовою цифр, наприклад "крапка" або "дефіс".`
- zh_TW `addon/doc/zh_TW/readme.md:49` 只寫「會以數字語言的符號名稱讀出」，沒有舉例。zh_CN 也沒有舉例。
- 這句在 `a4ee7ec`（上一輪）就已經這樣，不是這個分支加的；這個分支只把句尾的「分開」拿掉。屬於「比 zh_TW 多一點細節」，不影響意思。
- 建議（可選）：
  - en：`Symbols between digits, as in "12.5" or "5-3", are read by their names in the number language.`
  - ru：`Символы между цифрами, как в "12.5" или "5-3", читаются по своим названиям на языке чисел.`
  - uk：`Символи між цифрами, як у "12.5" або "5-3", читаються своїми назвами мовою цифр.`

### M2：zh_CN 一致性設定第一條沒有跟上 zh_TW「也→並」

- `addon/doc/zh_CN/readme.md:27`：「…只能从主要语音角色的语音引擎中选择，**也**只会使用该引擎的地区语音角色。」
- zh_TW `addon/doc/zh_TW/readme.md:27` 這一輪改成「…並只會使用…」。意思相同，純粹是措辭沒有同步；英文、ru、uk 的 and／и／і 都沒有問題。
- 建議（可選）：改為「并只会使用该引擎的地区语音角色」。

### M3：zh_CN 引用的 NVDA 核取方塊名稱與 NVDA zh_CN 介面不同（上一輪既有）

- `addon/doc/zh_CN/readme.md:81`：「…未勾选“处理字符和符号时信任语音的语言”时…」
- NVDA zh_CN 目錄（`ref/nvda/source/locale/zh_CN/LC_MESSAGES/nvda.po`）的 msgstr 是「处理字符和标点时信任语音的语言(&T)」。
- ru、uk 這一句都直接用 NVDA 自己的譯名（ru「Использовать язык синтезатора для чтения знаков и символов пунктуации」、uk「Довіряти голосу для вибраної мови обробку знаків та символів」，與 NVDA 目錄逐字相同）。zh_TW 自己也沒有照 NVDA zh_TW 的「處理字元及符號時依靠語音的語言」，所以 zh_CN 是否要改，由使用者決定。
- 這個分支沒有改到這一行。
- 建議（可選）：改為「处理字符和标点时信任语音的语言」，讓簡中使用者能在 NVDA 語音設定面板找到同名選項。

## 超出範圍的「Group size」改名：建議保留

- 變更：zh_HK `每組位數` → `數字分組位數`；zh_CN `每组位数` → `数字分组位数`（`.po` 與 readme 一起改）。
- 正確性：zh_TW 在 `ef89ea2` 改成「數字分組位數」，zh_HK 跟著 zh_TW 是一致的；zh_CN 的「数字分组位数」是同一個詞的簡體寫法，和 zh_CN readme 第 37、46、50、54、55 行引用的名稱一致。
- 必要性：zh_HK readme 是 zh_TW 的逐位元組複本，裡面寫的是「數字分組位數」；如果 zh_HK 的 `.po` 不改，繁中（港）使用者在面板上看到的會是「每組位數」，與說明文件對不上。zh_CN 同理（readme 在 `b0cf6ba` 改了，`.po` 要一起改）。
- 安全性：只改 `msgstr`，msgid 不變，沒有設定鍵、沒有快速鍵（這個 msgid 沒有 `&`），`msgfmt --check` 通過。
- 結論：保留。

## 翻譯用詞審查

### 新字串與同類標籤的一致性

| 語言 | Segment wait factor | Segment length | 同類標籤（既有） | 判斷 |
| --- | --- | --- | --- | --- |
| ar | معامل التوقف بين المقاطع | طول المقطع | معامل التوقف بين الأرقام／بين العناصر／عند علامات الترقيم | 句型與「معامل التوقف بين …」一致。「مقطع」一般指片段、段落；語言學上也可指音節（مقطع صوتي），但在「文字分段」的語境下沒有歧義，可接受。 |
| ru | Длительность пауз между сегментами | Длина сегмента | Длительность пауз между цифрами／между элементами／на знаках препинания | 完全同型。readme 的群組標題「Паузы между сегментами」與標籤只差單複數，和既有「Паузы на знаках препинания」／「Длительность пауз на знаках препинания」的做法相同。 |
| tr | Parça bekleme faktörü | Parça uzunluğu | Sayı bekleme faktörü／Öğe bekleme faktörü／Noktalama bekleme faktörü | 同型。「Parça」（片段）是土耳其文描述文字片段的常用詞；「Bölüm」偏「章節」，「Segment」是外來語，NVDA tr 目錄也沒有用「segment」當一般詞。維持 Parça。 |
| uk | Пауза між сегментами | Довжина сегмента | Пауза між цифрами／Пауза між елементами／Пауза на розділових знаках | 完全同型；與「Пауза між елементами」只差名詞，朗讀時不會混淆。readme 群組標題「Паузи між сегментами」與既有「Паузи на розділових знаках」做法相同。 |
| zh_CN | 分段停顿 | 分段字数 | 全局停顿／数字停顿／语音序列停顿／全文朗读停顿／标点停顿 | zh_CN 所有 wait factor 都沒有「参数」，所以「分段停顿」是一致的。readme 把群組標題寫成「分段停顿设置」（`zh_CN/readme.md:68`）避免與子項標籤同名，與既有「标点停顿设置」（第 59 行）做法相同。 |
| zh_HK | 分段停頓參數 | 分段字數 | 全域停頓參數／數字停頓參數／標點停頓參數 | 與 zh_TW 相同。 |

### readme 引用的介面名稱

| 引用 | 來源 | 結果 |
| --- | --- | --- |
| en「Engine」、ru「Движок」、uk「Рушій」、zh_CN「引擎」 | 各語言 `.po` 的 `&Engine`（`Дви&жок`、`Р&ушій`、`引擎(&E)`） | 一致 |
| ru『панель "Речевой движок"』、uk『панель "Синтезатор мовлення"』 | `.po` 的 `Speech Engine` | 一致 |
| ru「Следовать языку окружающего текста」、uk「Слідувати мові навколишнього тексту」、zh_CN「跟随上下文语言」 | `.po` 的 `Follow surrounding text language` | 一致 |
| en「Segment wait factor」「Segment length」及各語言的對應名稱 | 各語言 `.po` | 一致 |
| ru「Предполагаемый язык для наборов символов」、uk「Передбачена мова для наборів символів」、zh_CN「字符集所使用的语言」 | 各語言 readme 自己的 Unicode 偵測小節標題，字首與 `.po` 的 `Language assumed for … characters:` 譯法一致 | 一致 |
| uk 第 23 行『"Швидкість", "Висота" і "Гучність"』 | NVDA uk 目錄 `Rate`／`Pitch`／`Volume` | 一致 |
| ru 第 81 行、uk 第 81 行的 NVDA 核取方塊 | NVDA ru／uk 目錄 `Trust voice's language when processing characters and symbols` | 逐字一致 |
| zh_CN 第 81 行 | NVDA zh_CN 目錄 | 見 M3 |

## 逐段對照 zh_TW（這一輪 zh_TW 有變更或新增的段落）

| zh_TW 行 | 內容 | en | ru | uk | zh_CN |
| --- | --- | --- | --- | --- | --- |
| 15 | 功能特色：依 Unicode 判斷文字種類、在不同文字之間切換 | ✓ script | ✓ письменность | ✓ писемність | ✓ 文字种类 |
| 23 | 刪掉「加快語速核取方塊」 | ✓ | ✓ | ✓ | ✓ |
| 27 | 「也只會」→「並只會」 | ✓ and | ✓ и | ✓ і | M2 |
| 29 | 刪掉「加快語速參數」 | ✓ | ✓ | ✓ | ✓ |
| 37 | 清單加「數字分組位數」「分段停頓相關設定」 | ✓ | ✓ | ✓ | ✓ |
| 40 | 「Unicode 文字類型」 | ✓ script | ✓ письменности | ✓ писемністю | ✓ 文字类型 |
| 42 | 跟隨前後文語言：特定文字的數字交給該文字的語言，依「字元集假設的語言」順序 | ✓ | ✓ | ✓ | ✓ |
| 46 | 數字模式：每一段的讀法，分段由數字分組位數決定 | ✓ | ✓ | ✓ | ✓ |
| 49 | 數字模式：同一段以空白分開、不停頓 | ✓（M1） | ✓（M1） | ✓（M1） | ✓ |
| 50 | 數字分組位數：刪掉千分位、不處理＋分組、大於最長數字、設定位置四句 | ✓ 已刪 | ✓ 已刪 | ✓ 已刪 | ✓ 已刪 |
| 54–55 | 數字停頓參數改寫 | ✓ | ✓ | ✓ | ✓ |
| 68–70 | 分段停頓三行 | ✓ | ✓ | ✓ | ✓ |
| 87 | 注意：「語音引擎」→「引擎」 | ✓ | ✓ | ✓ | ✓ |
| 95 | 7.1：長文字不再在句子中間停頓 | ✓ | ✓ | ✓ | ✓ |
| 96 | 7.1：停頓後保留音調與拼讀設定 | ✓ | ✓ | ✓ | ✓ |
| 97 | 7.1：隱藏無法載入的語音引擎 | ✓ | ✓ | ✓ | ✓ |
| 98 | 7.1：特定文字的數字交給該文字的語言 | ✓ | ✓ | ✓ | ✓ |
| 99 | 7.1：語音設定值無效時仍能朗讀 | ✓ | ✓ | ✓ | ✓ |
| 112–113 | 7 更新：「語音引擎」→「引擎」 | ✓（master 已是 Engine） | ✓（Движок） | ✓（Рушій） | ✓（引擎） |

第 100 行以後（7／6／5／4 更新日誌）四份 readme 與 `master` 相同，zh_TW 這一輪也只改了 112–113 行。

## 審閱者自行驗證的項目

| 項目 | 指令 | 結果 |
| --- | --- | --- |
| 分支範圍 | `git log --oneline master..HEAD` | 7 個 commit，`721f24b..93d7593` |
| 沒有 Co-Authored-By | `git log master..HEAD --format=%B \| grep -ci co-authored` | 0 |
| 只改 `addon/doc`、`addon/locale`、`readme.md` | `git diff --stat master`；`git diff --name-only master \| grep -v -E '^(addon/doc\|addon/locale\|readme.md)'` | 12 個檔案；範圍外沒有檔案 |
| `addon/doc/en/`、`readme.html` 未動 | `ls addon/doc/en readme.html`；`git check-ignore -v readme.html` | worktree 裡不存在；`*.html` 由 `.gitignore:4` 忽略 |
| zh_HK 與 zh_TW 逐位元組相同 | `cmp addon/doc/zh_HK/readme.md addon/doc/zh_TW/readme.md` | 相同 |
| 六份 readme 結構相同 | 自寫腳本：逐行取標題層級、清單縮排深度、粗體與段落的簽章（zh_TW／zh_HK 一格縮排，其餘兩格） | en、ru、uk、zh_CN、zh_HK 與 zh_TW 144 行簽章完全相同 |
| 翻譯數 | `msgfmt --check --statistics -o /dev/null addon/locale/<l>/LC_MESSAGES/nvda.po`（七種語言） | 每一份都是 `92 translated messages.`，無錯誤 |
| 沒有 fuzzy、沒有 obsolete | `grep -c '#, fuzzy'`；`grep -c '^#~'` | 七份都是 0／0 |
| 版本標頭 | `grep Project-Id-Version` | 七份都是 `'WorldVoice' '7.1'` |
| msgmerge 針對最新來源 | scratch clone 執行 `scons pot`（92 個 msgid＋標頭），再對七份 `.po` 執行 `msgmerge --no-wrap`，與分支版本比對（排除 `POT-Creation-Date`） | 七份差異 0 行 |
| `.po` 只含預期變更 | `git diff master -- <po> \| grep '^[+-]' \| grep -v '^[+-]#:'` | 標頭兩行、移除 obsolete 的 `group`、新增 `Segment wait factor`／`Segment length`、`buildVars.py:29` 字串的換行 churn；zh_HK／zh_CN 另有 `Group size` 改名；zh_TW 只有行號與日期 |
| 快速鍵與格式佔位 | 自寫腳本：比對每一條 msgid／msgstr 的 `&` 數量與 `%s`／`%(name)s`／`{}` 佔位，並列出同一字母重複的快速鍵 | 新字串沒有 `&`、沒有佔位。既有的 `&` 不符只有附加元件描述文字（`SAPI5 & RHVoice`，不是標籤）；重複的快速鍵字母（ar ح：`&Pitch:`／`&Engine`；ru、uk：`&File Import`／`I&nflection:`；tr d：`&File Import`／`Number &language`）都在不同對話框，且 `master` 已如此，不是這個分支引入 |
| `prek run --all-files` | 在 scratch clone 執行（避免 hook 改到 worktree） | 8 個 hook 全部 Passed，`git status` 無修改 |
| 完整測試 | scratch clone（`ref` symlink）單一程序 `python3 -m pytest tests -q`，外加每 2 秒檢查 `MemAvailable < 3 GB` 就中止的守門 | `3808 passed in 132.88s`，0 skipped，守門未觸發 |
| NVDA 介面用詞 | `msgcat --no-wrap ref/nvda/source/locale/<l>/LC_MESSAGES/nvda.po \| grep -A1 'msgid "…"'`：Rate／Pitch／Volume／Variant／Trust voice's language… | 見「readme 引用的介面名稱」表 |

scratch clone 與 `.po` 比對檔都在 scratchpad，審閱結束後已刪除。

## 使用者還沒確認的用詞

以下是這個分支新寫、尚未經使用者確認的譯文；審閱認為都可用，列出供使用者決定。

1. 新標籤譯文：
   - ar：`معامل التوقف بين المقاطع`／`طول المقطع`
   - ru：`Длительность пауз между сегментами`／`Длина сегмента`
   - tr：`Parça bekleme faktörü`／`Parça uzunluğu`（審閱意見：Parça 比 Segment、Bölüm 合適）
   - uk：`Пауза між сегментами`／`Довжина сегмента`
   - zh_CN：`分段停顿`／`分段字数`（不加「参数」，與 zh_CN 既有 wait factor 譯法一致）
   - zh_HK：`分段停頓參數`／`分段字數`（與 zh_TW 相同）
2. 超出範圍的改名：zh_HK `數字分組位數`、zh_CN `数字分组位数`（建議保留）。
3. readme 的群組標題：zh_CN「分段停顿设置」、ru「Паузы между сегментами」、uk「Паузи між сегментами」、en「Segment pause」。
4. 英文 readme 新段落的措辭，例如「Cuts pauses into long text that has no pause in it」、「A letter is never separated from its combining marks」、「Script digits go to their script's language」、「Speech continues with invalid voice settings」。
5. M1～M3 是否要修。

## 修正記錄

依 DEVELOPMENT_WORKFLOW §3.4 處理。三項都是 Minor，只改文件，因此沒有先寫會失敗的測試，也不做修正 review。

- M1：已修，`ad6292b`。英文、ru、uk readme 第 49 行刪掉符號名稱的例子（"dot"／"dash"、"точка"／"дефис"、"крапка"／"дефіс"），採用審閱建議的句子，與 zh_TW 第 49 行一致。
- M2：已修，`4b69144`。zh_CN readme 第 27 行「也只会使用」改為「并只会使用」，與 zh_TW 第 27 行一致。
- M3：不修。zh_TW 自己也沒有照 NVDA zh_TW 介面的核取方塊名稱，而是改寫成「處理字元與符號時信任語音的語言」，zh_CN 是否改用 NVDA zh_CN 的「处理字符和标点时信任语音的语言」由使用者決定。列為未確認的用詞。

修正後確認：六份 readme 仍為 144 行、逐行簽章與 zh_TW 相同；`cmp addon/doc/zh_TW/readme.md addon/doc/zh_HK/readme.md` 相同；`prek run --all-files` 全部 Passed。只改文件，依指示未重跑測試。

### M3 後續（2026-11-07，使用者決定）

使用者要求各語言 readme 一律引用 NVDA 該語言 .po 的原文。英文、ru、uk 原本就相符；zh_TW、zh_HK、zh_CN 改為 NVDA 的翻譯（分支 `docs/nvda-trust-voice-label`）：

- zh_TW：「處理字元及符號時依靠語音的語言」
- zh_HK：「根據字符語言讓所屬語音進行處理」（NVDA zh_HK 的用詞和 zh_TW 不同，因此 zh_HK readme 這一行不再和 zh_TW 相同）
- zh_CN：“处理字符和标点时信任语音的语言”（不含快速鍵 `(&T)`）
