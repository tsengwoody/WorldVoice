# WorldVoice User Guide

WorldVoice is an NVDA add-on that supports automatic switching between speech roles from different speech engines, including eSpeak, OneCore, RHVoice and SAPI5, and provides a wide range of customization settings. Users can easily adjust speech settings for different situations and personal preferences.

As globalization becomes more widespread, people are exposed to multilingual written content more often. Whether in educational material or leisure reading, it is common to see different languages mixed together, and sometimes Chinese, English, and Japanese text can even appear in the same sentence.

Different types of digital content, such as language-learning material, mathematical information, or literary works, vary in text structure, context, and frequency of language mixing. When using a screen reader, being able to adjust reading behavior flexibly according to the content and personal preference can improve reading quality.

## Features

* Assign dedicated speech roles to different languages, so multilingual content can automatically switch to a more suitable voice while being read.
* Configure rate, pitch, and volume independently for each speech role, so different languages can keep their own reading settings.
* Switch number reading modes as needed, choosing whether numbers are read as values or digit by digit.
* Adjust the pause lengths for numbers, items, punctuation, spaces in Chinese, Japanese and Southeast Asian text, and say all, so the reading rhythm better matches user preference.
* Detect language automatically from Unicode characters, reducing the need to switch voices manually when reading multilingual content.

## Speech Roles

In the WorldVoice speech role settings panel, you can assign dedicated speech roles to different languages. WorldVoice stores the rate, pitch, volume and other settings of each speech role separately and applies them when the role is switched, which is especially helpful when reading content in a non-native language.

* After selecting a locale, the voice list shows the speech roles available for that locale. Selecting a speech role maps that locale to the speech role.
* After selecting a speech role, each setting control in the panel is enabled or disabled according to the settings that role supports; settings it does not support cannot be adjusted.
* After a speech role is selected, setting controls such as the rate, pitch, and volume sliders and the rate boost checkbox switch to that role's values. Changing a value affects only the currently selected speech role, not the settings of other speech roles.

### Consistency Settings

* Keep main engine and locale engine consistent: When enabled, the main speech role and locale speech roles can only be speech roles of the same speech engine. If the main speech role is changed and a locale speech role belongs to a different speech engine, that locale's speech role is reset to an unselected state and can only be selected again from the same engine as the main speech role.
* Keep main speech role and locale speech role consistent: When enabled, the main speech role stays the same as the speech role of the locale of its language (for example, a Chinese voice corresponds to the zh locale and an English voice to the en locale). When you change the main speech role in the NVDA voice settings panel, that locale's speech role changes to the same voice; conversely, when you change that locale's speech role in the WorldVoice speech role settings panel, the main speech role changes with it.
* Keep parameter settings consistent between different speech roles: When enabled, rate, pitch, volume, and rate boost parameters remain consistent across all speech roles. Changing the settings for any speech role updates the settings for all other speech roles as well.

In WorldVoice, the main speech role is the voice set in the NVDA voice settings panel, while locale speech roles are the voices set in the WorldVoice speech role settings panel.

## Speech Pipeline

Speech pipeline settings control reading behavior related to numbers, pauses, and language processing. The "Effect scope" setting in the Speech Pipeline panel decides which synthesizers the globally supported settings apply to: "All Synthesizers (Global)" applies them to every synthesizer, and "Only WorldVoice Synthesizer" (the default) uses them only in WorldVoice.

* Globally supported speech pipeline settings: number mode, group size, global wait factor, number wait factor, item wait factor, space wait factor between CJK and Southeast Asian characters, say all wait factor, punctuation pause settings
* WorldVoice-only speech pipeline settings: detect language based on Unicode characters, number language

* Detect language based on Unicode characters: When enabled, WorldVoice determines the language from the Unicode characters of the text and switches speech roles accordingly. Note: This feature may conflict with NVDA's automatic language switching, so it is recommended not to enable both at the same time.
* Number language: Chooses the language that reads numbers.
  * Follow surrounding text language (default): numbers are read in the language of the text around them.
  * Follow main language: numbers are read in the main language, that is, the language the document marks or the main speech role's language.
  * A specific language: numbers are always read by the speech role of that language.
  * Numbers include full-width digits (０–９) and other Unicode decimal digits, such as Arabic-Indic digits.
* Number mode:
  * Off: Numbers are left as they are.
  * Numeric mode: Reads numbers as values. For example, "12345" is read as "twelve thousand three hundred forty-five." Commas used as thousands separators, as in "12,345,678", are removed so the number is read as one value; other commas, as in "3,14", are kept.
  * Digit mode: Reads numbers digit by digit. For example, "12345" is read as "one two three four five." Symbols between digits, as in "12.5" or "5-3", are read separately by their names, such as "dot" or "dash", in the number language.
  * Group mode: Reads the digits of a number in groups counted from the left. The group size (2–10, default 3) is set in the Speech Pipeline panel or the Voice settings panel; groups and symbols are separated by the pause of the number wait factor. For example, with size 3, "12345" is read as "123", "45", and "123.456" as "123", "dot", "456".
* Speech pause adjustment: Sets the length of each of the following pauses. Smaller values mean shorter pauses, and 0 means no pause.
  * Global wait factor: The multiplier of the wait factors below. The actual pause is "global wait factor ÷ 10 × that wait factor" milliseconds; for example, with a global wait factor of 20 and a number wait factor of 10, the number pause is 20 ms. In the NVDA voice settings panel it ranges from 0 to 100 in steps of 10; the Speech Pipeline panel shows it as 0 to 10.
  * Number wait factor:
    * Two numbers separated only by whitespace get the pause, as in "123 456".
    * In digit mode, the pause goes between every two digits; in group mode, between every group and symbol.
    * In digit mode and group mode, the pause also goes before and after a number, as in "第3章", even when the number is read in the same language as the text.
  * Item wait factor: NVDA often speaks an utterance as several items, such as an object's name, role, and state; this pause goes between two adjacent items. Where it falls at the same place as a pause around a number, only the longer of the two is heard.
  * Space wait factor between CJK and Southeast Asian characters: Han, kana, Bopomofo, Thai, Lao, Khmer, and Myanmar text is written without spaces between words, so a space with characters of these scripts on both sides gets the pause; Korean and Latin text separate words with spaces, so spaces between such characters get no pause.
  * Say all wait factor: During say all, the pause comes after each piece of text that is read.
* Punctuation pause: Pauses at chosen punctuation marks.
  * Enable punctuation pause control: When on, WorldVoice pauses at the marks in "Punctuation pause characters"; when off, none of the punctuation pause settings below take effect.
  * Pause points: Several marks in a row count as one pause point; punctuation inside a number, such as the comma in "12,500", gets no pause, and neither does a mark with no spoken text after it, such as at the end of a sentence.
  * Punctuation wait factor: The pause at each pause point. At 0 (the default), no extra pause is added, but with punctuation pause control on the text is still split at each pause point, so it can sound different there than with the control off. Where it falls at the same place as a pause around a number, only the longer of the two is heard.
  * Remove configured punctuation at pause points: When on, the mark at a pause point is not sent to the speech engine, so it is not read; marks that are not at a pause point, such as at the end of a sentence, are kept.
  * Punctuation pause characters: The list of marks to pause at.
    * Typing: Type the marks next to each other; do not separate them with spaces.
    * Spaces: A space also counts as a character, and adding one makes every space a pause point; spaces between CJK and Southeast Asian characters, however, still pause by the space wait factor between CJK and Southeast Asian characters.
    * Full-width and no-break spaces: Do not put a full-width space (U+3000) or a no-break space at the very start or end of the list: NVDA's configuration file drops these two kinds of spaces there when NVDA restarts.

Globally supported speech pipeline settings can be adjusted through the NVDA voice settings panel or the WorldVoice Speech Pipeline panel. Speech pipeline settings that are not globally supported can only be adjusted through the NVDA voice settings panel.

## Unicode Detection

These options adjust how WorldVoice handles character sets shared by multiple languages when detecting text language.

* Language detection timing: Decides whether Unicode-based language detection runs before or after NVDA processes speech commands: "Before NVDA processes speech commands" or "After NVDA processes speech commands".
* Assumed language for character sets: Sets the default language for Unicode character sets shared by multiple languages, including Latin characters, CJK characters, Arabic characters, Cyrillic characters, and Devanagari characters. For these characters, WorldVoice chooses the reading language in the following order, skipping languages without an installed voice:
  1. The language being read: if this language itself is written with these characters (as Chinese, Japanese, and Korean are with Han characters), it is kept. For example, Han characters met while reading Japanese are still read in Japanese.
  2. The main language: if the main language is written with these characters, it is used. The main language is the language the document marks, or otherwise the main speech role's language (NVDA may replace it with its interface language when detection runs after NVDA and "Trust voice's language when processing characters and symbols" is off).
  3. The assumed language: only when neither of the above applies is this setting used.
  4. If the language of this setting has no installed voice, another language written with these characters that has an installed voice is used.

## Notes

* If you enable both NVDA automatic language switching and WorldVoice Unicode detection, the two features may affect each other. Choose one according to your needs.
* If you want to disable a specific speech engine, clear the corresponding checkbox in the WorldVoice speech engine panel.
* If you need to use a speech engine other than eSpeak, OneCore, RHVoice, or SAPI5, download the corresponding driver or voice package separately.
* On NVDA 2024.1 to 2025.2, WorldVoice's SAPI5 engine uses NVDA's own SAPI5 driver, as WorldVoice 6.2 did, so SAPI5 voices work as they did in 6.2. WorldVoice's own SAPI5 driver, which waits until each part of SAPI5 speech has finished playing before the next part (another voice or a pause) starts, is used only on NVDA 2025.3 or later.

# WorldVoice Changelog

## Next update

* **Space pause for Japanese and Southeast Asian text:** The Chinese space wait factor is now the "Space wait factor between CJK and Southeast Asian characters". A space between two characters of Han (including every extension block), kana, Bopomofo, Thai, Lao, Khmer or Myanmar script now gets the pause, also when the two sides are different scripts, as in "漢字 かな". Earlier versions paused only between two common Chinese characters. If the punctuation pause characters include a space, these spaces use the space wait factor between CJK and Southeast Asian characters instead of the punctuation wait factor, as Chinese text already did.
* **Pause around numbers in digit and group modes:** In digit mode and group mode, the number pause now also separates every number from the text next to it, as in "第3章", even when the number is read in the same language as the text. Digits next to letters, as in "1st" or "MP3", are set apart too. Numeric mode, the default, is unchanged. Set the number wait factor to 0 to turn the pause off (this also turns off the pause between numbers). Where a punctuation pause or an item pause falls next to a number, only the longer of the two pauses is heard.
* **Numbers follow the surrounding text language by default:** The "Ignore numbers when detecting text language" option has been removed from the Unicode Detection panel. Number language now offers "Follow surrounding text language" (the default: numbers are read in the language of the text around them) and "Follow main language" (numbers are read in the main language). Earlier versions read numbers in the main language unless the option was checked; choose "Follow main language" to keep that.
* **Hyphens stay with their word:** With a number language, a hyphen right after a word, as in "COVID-19", now stays with the word instead of being read as a minus sign with the number. A sign after a space, as in "-3", still belongs to the number.
* **Full-width and other Unicode digits are numbers:** Number language, number modes, number pauses and the thousands separator rule now also apply to full-width digits and other Unicode decimal digits, such as Arabic-Indic digits.
* **Assumed languages for Cyrillic and Devanagari:** The Unicode Detection panel now also lets you choose the language assumed for Cyrillic characters (default Russian) and Devanagari characters (default Hindi). Earlier versions always used the first language with an installed voice in WorldVoice's list for the character set; the defaults keep that behavior.
* **Unicode data updated to 18.0.0:** Unicode detection and the space pause between CJK and Southeast Asian characters now know the characters Unicode 17.0 and 18.0 added, such as the ideographs of CJK Unified Ideographs Extension J and new kana. They are detected and get the space pause like the other Han and kana characters. Small seal script characters, new in 18.0, are a script of their own, not Han: Unicode detection does not switch language for them and they get no space pause.
* **WorldVoice waits for each part of speech to finish playing:** With eSpeak, OneCore, RHVoice, VE and Cerence, WorldVoice now waits until each part of speech has finished playing before the next part (another voice or a pause) starts, so the next voice or pause no longer begins while the previous part is still playing. With SAPI5 it does the same on NVDA 2025.3 or later, where WorldVoice's SAPI5 engine uses WorldVoice's own SAPI5 driver, built on the speech queue NVDA 2025.3 introduced. On NVDA 2024.1 to 2025.2, SAPI5 keeps using NVDA's own SAPI5 driver, as in WorldVoice 6.2, without this wait, and WorldVoice writes one line about it to the NVDA log.

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

* Integrated the eSpeak engine into the engines supported by WorldVoice.
* Added a rate boost setting to the NVDA voice settings panel.
* Added a voice variant setting to the NVDA voice settings panel.
* If the current engine or voice supports rate boost, the NVDA voice settings panel dynamically displays the rate boost setting UI.
* Users can set rate boost for individual voices in the WorldVoice voice settings panel.
