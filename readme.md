# WorldVoice User Guide

As globalization becomes more widespread, exposure to multilingual content has become increasingly common. From educational materials to leisure reading, it’s not unusual to see multiple languages mixed, even within the same sentence.

Digital content, such as language textbooks, mathematical information, or literature, differs in textual structure, context, and frequency of language mixing. Therefore, the ability to flexibly adjust reading methods according to content characteristics and personal preferences is a crucial feature when using screen readers.

WorldVoice is an NVDA add-on that supports automatic switching among various role of speech engines, including Espeak, OneCore, RHVoice, and SAPI5, and provides diverse customization settings. Users can easily adjust speech settings to suit various scenarios and individual needs.

## Features

* Independent setting of speech rate, pitch, and volume for each speech role.
* Supports automatic switching of speech roles from various speech engines.
* Switching between numeric reading mode (numeric or digit-by-digit).
* Adjustable speech pause durations for various contexts, including between numbers, items, Chinese space and during say-all reading.
* Automatic language detection based on Unicode characters.

## speech role

In the WorldVoice speech role settings panel, you can assign specific speech roles to different region, adjusting parameters such as speed, pitch, and volume individually.

WorldVoice independently stores the settings for each speech role. When a role is switched, its corresponding parameters—such as rate, pitch, and volume—are automatically applied, allowing each role to Keep its own voice characteristics. This feature is especially helpful for reading content in non-native languages.

* After selecting a region, available speech roles for that region are displayed. Choosing a speech role completes the region-to-voice-role mapping.
* If the selected speech role supports voice variant, variant options will be available for selection.
* Upon selecting a speech role, sliders for speed, pitch, volume, and the boost speed checkbox will adjust to that role’s settings. Adjustments apply only to the selected role independently.

### Consistency Settings:

* Keep main speech engine consistency with regional speech engines: Ensures the main and regional speech roles use the same speech engine. If a main speech role adjustment involves a different engine, regional speech roles reset and require re-selection.
* Keep main speech role consistency with regional speech roles: Keeps the main and regional speech roles identical. Adjusting one automatically synchronizes the other.
* Keep parameter consistency between speech roles: Synchronizes parameters like speed, pitch, volume, and boost speed settings across all speech roles. Adjustments to one role affect all others.

The main speech is configured through the NVDA voice settings panel, while regional speechs are configured through WorldVoice’s speech role settings panel.

## Speech Pipeline

Through WorldVoice’s speech pipeline panel, you can configure settings for various speech processes and select the scope of the speech pipeline (global or WorldVoice-only).

* Globally supported speech pipeline settings: Ignore commas between numbers, number reading mode, pauses between items, pauses between numbers, pauses between Chinese characters, and pauses during say-all reading.
* WorldVoice-only supported speech pipeline settings: Language detection based on Unicode characters, number language.

* Language Detection Based on Unicode Characters: Automatically detects the language region from Unicode characters and switches speech roles accordingly. Note: This feature may conflict with NVDA’s automatic language switching, so concurrent use is not recommended.
* Number Language: Specifies the regional speech role for reading numbers.
* Number Mode:
 * Numeric Mode: Reads numbers as values, e.g., "12345" as "twelve thousand three hundred forty-five."
 * Digit Mode: Reads numbers digit-by-digit, e.g., "12345" as "one two three four five."
* Speech Pause Adjustment: Sets the duration of pauses between numbers, items, Chinese characters, and say-all reading. Lower values indicate shorter pauses; zero means no pause.
* Ignore Commas Between Numbers: Skips commas during number reading to enhance accuracy for specific speech roles.

Globally supported speech pipeline settings can be adjusted through NVDA’s speech settings panel or WorldVoice’s speech pipeline panel. WorldVoice-only supported speech pipeline must be adjusted through NVDA’s speech settings panel.

## Unicode Detection

* Ignore numbers during language detection: Numbers are excluded from language detection, using the current speech role.
* Ignore common punctuation during language detection: Punctuation marks are excluded from language detection, using the current speech role.
* Language detection timing: Determines when Unicode-based language detection and language-switching commands are processed—either before or after NVDA’s speech pipeline.
* Assumed language for character sets: Sets a default language assumption for character sets shared by multiple languages in Unicode, including Latin, CJK (Chinese, Japanese, Korean), and Arabic.

## Notes

If you want to disable specific speech engines, uncheck the corresponding checkboxes in the WorldVoice speech engine settings panel.

To use the RHVoice speech engine, download the appropriate voice pack add-on from the official RHVoice website.

# WorldVoice update log

## WorldVoice v5.0 Update

* **Add new s features and setting panels:** Speech Pipeline and Log Record
* **Remove deprecated features and setting panels:** Unicode normalization, number-dot replacement, and other outdated items
* **Add speech pipeline feature:** Enable WorldVoice’s speech pipeline for all synthesizers
* **Add log record feature:** Capture pipeline data before and after each speech sequence to facilitate debugging
* **Add boost-rate feature:** Allow speed boosts for specific speech engines
* **Enhance UX:** Improve interactions in the Speech Engine and Log Record dialogs
* **Revise UI text:** Update UI text for style

## WorldVoice v4.0 Update

* Integrate the espeak engine into WorldVoice-supported engines.
* Add speech rate boost setting in NVDA - speech setting dialog.
* Add speech variant value setting in NVDA - speech setting dialog.
* NVDA - speech setting dialog will dynamically display rate boost setting UI if the engine/voice is supported.
* Users can set rate boost for individual voices in the WorldVoice speech setting dialog.
