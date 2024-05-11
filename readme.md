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

## WorldVoice v4.0 Update

* Integrate the espeak engine into WorldVoice-supported engines.
* Add speech rate boost setting in NVDA - speech setting dialog.
* Add speech variant value setting in NVDA - speech setting dialog.
* NVDA - speech setting dialog will dynamically display rate boost setting UI if the engine/voice is supported.
* Users can set rate boost for individual voices in the WorldVoice speech setting dialog.
