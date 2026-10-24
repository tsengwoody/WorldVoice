# WorldVoice User Guide

WorldVoice is an NVDA add-on that supports automatic switching between speech roles from different speech engines, including Espeak, OneCore and SAPI5, and provides a wide range of customization settings. Users can easily adjust speech settings for different situations and personal preferences.

As globalization becomes more widespread, people are exposed to multilingual written content more often. Whether in educational material or leisure reading, it is common to see different languages mixed together, and sometimes Chinese, English, and Japanese text can even appear in the same sentence.

Different types of digital content, such as language-learning material, mathematical information, or literary works, vary in text structure, context, and frequency of language mixing. When using a screen reader, being able to adjust reading behavior flexibly according to the content and personal preference can improve reading quality.

## Features

* Assign dedicated speech roles to different languages, so multilingual content can automatically switch to a more suitable voice while being read.
* Configure rate, pitch, and volume independently for each speech role, so different languages can keep their own reading settings.
* Switch number reading modes as needed, choosing whether numbers are read as values or digit by digit.
* Adjust pause lengths between numbers, items, Chinese text, and say-all reading, so the reading rhythm better matches user preference.
* Detect language automatically from Unicode characters, reducing the need to switch voices manually when reading multilingual content.

## Speech Roles

In the WorldVoice speech role settings panel, you can assign dedicated speech roles to different languages and adjust parameters such as rate, pitch, and volume for each role individually.

WorldVoice stores settings for each speech role separately. When a role is switched, the corresponding settings are applied, allowing each speech role to keep its own rate, pitch, and volume. This is especially helpful when reading content in a non-native language.

* After selecting a language or region, the voice list shows the speech roles available for that language or region. Selecting a speech role completes the mapping between that language or region and the speech role.
* After selecting a speech role, if that role supports voice variants, the available variant options are shown for selection.
* After a speech role is selected, the rate, pitch, and volume sliders, as well as the rate boost checkbox, automatically update to that role's settings. Changing these values affects only the currently selected speech role, because each speech role has its own independent settings.

### Consistency Settings

* Keep the main speech engine and regional speech engines consistent: When enabled, the main speech role and regional speech roles can only use speech roles from the same speech engine. If the main speech role is changed and a regional speech role belongs to a different speech engine, that regional speech role is reset to an unselected state and can only be selected again from the same engine as the main speech role.
* Keep the main speech role and regional speech roles consistent: When enabled, the main speech role and regional speech roles remain the same. When you change the speech role setting on either side, the other side is automatically synchronized to the same speech role.
* Keep parameters consistent between different speech roles: When enabled, rate, pitch, volume, and rate boost parameters remain consistent across all speech roles. Changing the settings for any speech role updates the settings for all other speech roles as well.

The main speech role is configured through the NVDA voice settings panel, while regional speech roles are configured through the WorldVoice speech role settings panel.

## Speech Pipeline

Speech pipeline settings control reading behavior related to numbers, pauses, and language processing. You can choose whether these settings apply to all supported synthesizers or only within WorldVoice.

* Globally supported speech pipeline settings: number mode, item pause, number pause, Chinese pause, say-all pause
* WorldVoice-only speech pipeline settings: detect language based on Unicode characters, number language

* Detect language based on Unicode characters: When enabled, WorldVoice automatically determines the language or region from the text's Unicode characters and switches speech roles accordingly. Note: This feature may conflict with NVDA's automatic language switching, so it is recommended not to enable both at the same time.
* Number language: Chooses the language that reads numbers.
  * Follow current text language (default): numbers are read in the language of the text around them. With Unicode detection on, a number in Chinese text is read by the Chinese voice.
  * Follow document main language: numbers are read in the main language, that is, the language the document marks or the main speech role's language.
  * A specific language: numbers are always read by the speech role of that language.
  * Numbers include full-width digits (０–９) and other Unicode decimal digits, such as Arabic-Indic digits.
* Number mode:
  * Off: Numbers are left as they are.
  * Numeric mode: Reads numbers as values. For example, "12345" is read as "twelve thousand three hundred forty-five." Commas used as thousands separators, as in "12,345,678", are removed so the number is read as one value; other commas, as in "3,14", are kept.
  * Digit mode: Reads numbers digit by digit. For example, "12345" is read as "one two three four five." Symbols between digits, as in "12.5" or "5-3", are read separately by their names, such as "dot" or "dash", in the number language.
  * Group mode: Reads the digits of a number in groups counted from the left. The group size (2–10, default 3) is set in the Speech Pipeline panel or the Voice settings panel; groups and symbols are separated by the number pause. For example, with size 3, "12345" is read as "123", "45", and "123.456" as "123", "dot", "456".
* Speech pause adjustment: Sets the pause length between numbers, items, Chinese text, and say-all reading. Smaller values mean shorter pauses, and 0 means no pause. In digit mode and group mode, the number pause is also placed before and after every number that has other spoken text next to it, in the same item or in a neighbouring one, as in "第3章", even when the number is read in the same language as the text. There is no such pause at the very start or end of what is spoken, and where the item pause falls at the same place, only the longer of the two is heard. Numeric mode and Off add no such pause, and a number pause of 0 adds none.
* Punctuation pause characters: The marks at which WorldVoice pauses while "Enable punctuation pause control" is on. Type the marks next to each other without separators; a space also counts as a character, and entering one makes every space a pause point. Do not put a full-width space (U+3000) or a no-break space at the very start or end of the list: NVDA's configuration file drops it there when NVDA restarts.

Globally supported speech pipeline settings can be adjusted through the NVDA speech settings panel or the WorldVoice speech pipeline panel. Speech pipeline settings that are not globally supported can only be adjusted through the NVDA speech settings panel.

## Unicode Detection

These options adjust how WorldVoice handles character sets shared by multiple languages when detecting text language.

* Language detection timing: Determines whether Unicode-based language detection and language-switching commands are handled before or after NVDA processes speech commands.
* Assumed language for character sets: Sets the default language for Unicode character sets shared by multiple languages, including Latin characters, CJK characters, Arabic characters, Cyrillic characters, and Devanagari characters. WorldVoice uses this language only when neither the language being read nor the main language (the main speech role's language, which NVDA may replace with its interface language when detection runs after NVDA and "Trust voice's language when processing characters and symbols" is off; or the language the document marks) is a language of that character set with an installed voice. Languages without an installed voice are skipped.

## Notes

* If you enable both NVDA automatic language switching and WorldVoice Unicode detection, the two features may affect each other. Choose one according to your needs.
* If you want to disable a specific speech engine, clear the corresponding checkbox in the WorldVoice speech engine panel.
* If you need to use a speech engine other than Espeak, OneCore, or SAPI5, download the corresponding driver or voice package separately.

# WorldVoice Changelog

## Next update

* **Pause around numbers in digit and group modes:** In digit mode and group mode, the number pause now also separates every number from the text next to it, as in "第3章", even when the number is read in the same language as the text. Digits next to letters, as in "1st" or "MP3", are set apart too. Numeric mode, the default, is unchanged. Set the number wait factor to 0 to turn the pause off (this also turns off the pause between numbers). Where a punctuation pause or the item pause falls next to a number, only the longer of the two pauses is heard.
* **Numbers follow the text language by default:** The "Ignore numbers when detecting text language" option has been removed from the Unicode Detection panel. Number language now offers "Follow current text language" (the default: numbers are read in the language of the text around them) and "Follow document main language" (numbers are read in the main language). Earlier versions read numbers in the main language unless the option was checked; choose "Follow document main language" to keep that.
* **Hyphens stay with their word:** With a number language, a hyphen right after a word, as in "COVID-19", now stays with the word instead of being read as a minus sign with the number. A sign after a space, as in "-3", still belongs to the number.
* **Full-width and other Unicode digits are numbers:** Number language, number modes, number pauses and the thousands separator rule now also apply to full-width digits and other Unicode decimal digits, such as Arabic-Indic digits.
* **Assumed languages for Cyrillic and Devanagari:** The Unicode Detection panel now also lets you choose the language assumed for Cyrillic characters (default Russian) and Devanagari characters (default Hindi). Earlier versions always used the first language with an installed voice in WorldVoice's list for the character set; the defaults keep that behavior.
* **Spaces in the punctuation pause characters are kept:** The punctuation pause characters now keep every character you type, including spaces. Earlier versions removed spaces at the start and end of the list, so a single space was cleared on saving.

## WorldVoice 6 Update

* **Fixed responsiveness during delayed descriptions:** Break tasks are now cancellable, reducing lag when delayed character descriptions are enabled.
* **Improved speech dictionary compatibility:** Speech dictionaries are now applied before the WorldVoice pipeline.
* **Refined pipeline settings internals:** Pipeline settings handling has been refactored for clearer behavior and easier maintenance.
* **Improved voice metadata handling:** Duplicate voice names across engines are now disambiguated, and fallback language descriptions are normalized.
* **Refactored driver architecture:** Engine driver architecture and loading have been redesigned, replacing hard-coded loading with manifest-based discovery.
* **Refined core packaging:** Core driver packaging has been reorganized.
* **Improved Sonic initialization:** Sonic is now initialized lazily on first voice callback.
* **Refined task execution internals:** TaskManager now uses a Future-based design.
* **Improved built-in engine integration:** SAPI5, OneCore, and eSpeak now inherit from the built-in base class.
* **Improved number pronunciation logic:** Number pronunciation and translation logic have been refined.

## WorldVoice 5 Update

* **Added features and settings panels:** Speech Pipeline and Log Record
* **Removed deprecated features and settings panels:** Unicode normalization, number-dot replacement, and other outdated settings
* **Added speech pipeline feature:** Enable WorldVoice's speech pipeline for all synthesizers
* **Added log recording feature:** Capture speech sequences before and after each pipeline step for debugging
* **Added rate boost feature:** Allow rate boost for specific speech engines
* **Improved user experience:** Improved interactions in the Speech Engine and Log Record dialogs
* **Revised interface text:** Updated interface text for a consistent style

## WorldVoice 4 Update

* Integrated the Espeak engine into the engines supported by WorldVoice.
* Added a rate boost setting to the NVDA voice settings panel.
* Added a voice variant setting to the NVDA voice settings panel.
* If the current engine or voice supports rate boost, the NVDA voice settings panel dynamically displays the rate boost setting UI.
* Users can set rate boost for individual voices in the WorldVoice voice settings panel.
