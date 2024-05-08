WorldVoice does not include those commercial TTS libraries (core dll). You must purchase a license from the original developer/company in order to use it, WorldVoice is just the driver for it.
We also cannot guarantee compatibility with the latest versions sold by the developer/company, so please consider carefully before making a purchase if you intend to use those commercial TTS with WorldVoice.
WorldVoice only focuses on TTS engines open source/free and does not prioritize maintaining compatibility with those commercial TTS engines.

# WorldVoice

In this highly interconnected and globalized era, language learning has become increasingly important. In language learning materials, native languages are often used to help explain foreign vocabulary and sentences, and multiple languages are often mixed together. In daily communication, we also often mix multiple languages and scripts. In books, newspapers, and online articles, multiple languages are often used to convey information, sometimes even within the same sentence, using Chinese and English or Chinese and Japanese.

The text composition, contextual meaning, and cross-lingual frequency of different digital content, such as language learning, mathematics, and literary works, may differ, and the corresponding speech reading method may also need to be adjusted accordingly to better meet the needs of different types of documents.

WorldVoice is a multi-language speech reading NVDA add-on, which supports five speech engines (Espeak, OneCore, RHVoice, SAPI5, Piper) and provides a variety of customization options. Users can adjust their settings for different contexts, maximizing the satisfaction of different user groups.

Its main features include:

*	Automatic switching between multiple languages
*	Individual speech parameter settings (speed, pitch, volume)
*	Multi-speech engine selection
*	Switching between numeric reading modes (digits and numerical values)
*	Customizable speech reading behavior (pause length for numbers, items, Chinese space, say all, comma ignore between numbers)

## install

In addition to the general NVDA addon installation steps, if you want to use the aisound voices, you need to install the core packages. If you want to use the RHVoice voice, please download the corresponding voice package addon from the official website. [Official download page](https://rhvoice.org/languages/).

## Main Speech Role Settings

In NVDA Settings: Speech(NVDA+Ctrl+V) Configure basic speech roles and common behaviors.

* speed, pitch, and volume of main speech role.
* Numeric reading: It has two options, "Number Language" and "Number mode". Number language sets the prefer language used for numeric text, and number mode set reading numbers text as numerical values or individual digits.
* Pause duration for numbers, items, Chinese spaces, and say all parameters. Smaller values result in shorter pauses, with 0 meaning no pause.
* Ignore comma between number: When selected, NVDA will ignore commas in numbers, allowing correct reading of numerical values with misplaced commas.
* Enable WorldVoice setting rules to detect text language: When selected, NVDA will use the rules from the voice settings to detect the language of the text and switch the voice accordingly. Note that this option may have compatibility issues with NVDA's "Automatic language switching (when supported)", so it is advisable not to select both simultaneously.

## WorldVoice Voice Settings (NVDA Menu -> WorldVoice -> Voice Settings)

Speech Role: You can configure speech roles for different regions, including individual settings for speed, pitch, volume, and consistency between the main speech role and regional speech roles.

* Selecting a region will display a list of available speech roles for that region. Choosing a speech role will establish the association between the selected region and speech role.
* After selecting a speech role, the list of voice modifiers will show available pitch adjustments for that speech role. Choosing a modifier will associate it with the selected speech role.
* Once a speech role is chosen, the speed, pitch, and volume sliders below will display the settings for that speech role.
* Speed, pitch, and volume settings are specific to each speech role and not tied to regions.
* Keep main engine and locale engine consistent: This option synchronizes the main speech role in NVDA's voice settings with the regional speech role in WorldVoice. Adjusting the main voice settings will also adjust the regional voice engine to be the same.
* Keep main voice and locale voice consistent: This option ensures that the main speech role in NVDA's voice settings matches the regional speech role in WorldVoice. Any changes to the main or regional speech role will be synchronized between the two.
Keep main parameter and locale parameter consistent

Language Switching:

* Detect language using Unicode encoding: When checked, the program will detect the language based on the characters it reads.
* Ignore numbers when detecting language, ignore common punctuation when detecting language: When checked, numbers and common punctuation will be considered part of the main speech role's language.
* Enhance voice commands: This allows the program to automatically detect language and determine when to add pauses for voice commands before or after NVDA's symbol processing. Selecting "after symbol processing" can prevent conflicts with other voice module add-ons (e.g., Instant Translate).

Speech Engine: You can choose the voice engine you want to enable.

# WorldVoice update log

## v3.8

* Update readme
* Remove some menu

# WorldVoice

在高度網路化和國際化的時代，語言學習變得越來越重要。在語言學習教材中，通常使用母語輔助解釋外國語言的詞彙和句子，並且經常出現兩種或以上語言混合的情況。在日常生活中，我們也經常在交流討論時夾雜多種語言和文字。在書報、網路文章中也常常能看到多種語言穿插撰寫以傳達資訊，有些甚至在同一句子中以中英文、中日文等方式呈現。

不同數位內容（例如語言學習、數理學門和文學作品）的文字組成、上下文語意和跨語言頻率等特性會有所不同，相對的語音報讀方式也可能需要依據不同的數位內容進行微調，以更符合該類文件的需求。

WorldVoice 是一款多國語音朗讀 NVDA 附加元件，支援 VE, OneCore, Aisound, SAPI5, RHVoice 五種語音引擎互相搭配選用並提供了豐富的客製化設定選項，讓使用者可以在不同情境下進行不同的設定，最大化滿足不同族群使用者的需求。

主要功能有：

*	多國語系語音自動切換
*	各別語音參數(速度、音調、音量)設定
*	多語音引擎互相搭配選用
*	數字讀法切換(數字與數值)
*	朗讀行為客製(數字、項目、中文空白停頓長度、忽略在數字間的逗號)
*	自訂文字所屬地區

## 安裝

除了一般的 NVDA 附加元件安裝步驟之外，如果您想使用 RHVoice 語音，請從官方網站下載相應的語音包附加元件。[官方下載點](https://rhvoice.org/languages/)。

## 主要語音角色設定

在 NVDA 設定: 語音(NVDA+ctrl+V) 設定基礎語音角色與共通行為

*	語音速度、音調、音量設定
*	數字讀法：分為 2 個設定選項「數字語言」與「數字模式」，數字語言設定數字朗讀時使用的語音角色、數字模式分為數值與數字兩種
*	針對數字、項目、中文空白、讀出全部的語音間停頓時長，數字愈小停頓愈短， 0 為不停頓。
*	忽略在數字間的逗號：選項勾選時會忽略數字中間的逗號，可讓數字位數的逗號標錯位置仍能正常朗讀數值。
*	啟用 WorldVoice 設定規則來偵測文字語言：當選項勾選時，會使用語音設定內的規則來偵測文字語言並切換語音朗讀。在部份情境此選項會與 NVDA 自動切換語言有相容性問題，建議兩者不要同時勾選。

## WorldVoice 語音設定（NVDA 功能表 -> WorldVoice -> 語音設定）

語音角色：可設定不同地區所使用的語音角色、各別語音角色速度、音調、音量、主要語音角色與地區語音角色一致性設定。

*	選擇地區後語音列表會列出該地區可用的語音角色，選擇後即完成該地區與語音角色的對應紀錄。
*	選擇語音角色後變聲列表會列出該語音角色可用的變聲，選擇後即完成該語音角色與變聲的對應紀錄。
*	當語音角色有選擇時，下方速度、音調、音量滑桿會變為該語音角色的設定值。
*	速度、音調、音量是依不同語音角色區分，每個語音角色有各自不同的速度數值，而非依地區區分。
*	保持主要語音引擎與地區語音引擎一致：將 NVDA 語音設定中的語音（主要語音）角色與 WorldVoice 語音設定中的地區對應語音（地區語音）引擎一致，當主要語音設定調整時，地區語音同步調整為相同的語音引擎。
*	保持主要語音角色與地區語音角色一致：將 NVDA 語音設定中的語音（主要語音）角色與 WorldVoice 語音設定中的地區對應語音（地區語音）角色一致，當主要語音或地區語音設定調整時，同步調整雙方的語音角色設定。
*	保持主要語音參數與地區語音參數一致：將 NVDA 語音設定中的語音（主要語音）與 WorldVoice 語音設定中的地區對應語音（地區語音）參數（速度、音調、音量）一致，當主要語音或地區語音設定調整時，同步調整雙方的語音參數設定。

語言設定：

*	用 unicode 編碼偵測文字語言勾選後，程式會根據讀到的字元偵測文字所屬地區。
*	偵測語言時忽略數字、偵測語言時忽略常見標點符號勾選後，數字與標點符號會判定為主要語音的地區文字。
*	增強語音命令：文字自動偵測語言、停頓語音指令的判斷與加入時間點是在 NVDA 的符號處理前或符號處理後進行。當選擇「符號處理後」項目時，可防止與其他使用到語音模組附加元件(ex: Instant Translate)的衝突。

語音引擎：可選擇要啟用的語音引擎。

# WorldVoice 更新日誌

## v3.8

* 更新說明文件
* 移除部份選單
