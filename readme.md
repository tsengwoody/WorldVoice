# WorldVoice User Guide

As globalization becomes more widespread, exposure to multilingual content has become increasingly common. Whether it’s educational materials or leisure reading, it’s not unusual to encounter multiple languages mixed together—in some cases, Chinese, English, and Japanese characters may even appear within a single sentence.

Digital content—whether language textbooks, mathematical materials, or literary works—differs in textual structure, context, and frequency of language mixing. As a result, having the flexibility to adjust how content is read based on both its characteristics and personal preferences is an essential feature for screen reader users.

WorldVoice is an NVDA add-on that supports automatic switching across roles of different speech engines—including Espeak, OneCore, RHVoice, and SAPI5—and provides a variety of customization settings. Users can easily adjust speech settings to suit various scenarios and personal preferences.

## Features

* Independent setting of speech rate, pitch, and volume for each speech role.
* Supports automatic switching of speech roles from various speech engines.
* Switching between numeric reading mode (numeric or digit-by-digit).
* Adjustable speech pause durations for various contexts, including between numbers, items, Chinese and during say-all reading.
* Automatic language detection based on Unicode characters.

## speech role

In the WorldVoice speech role settings panel, you can assign specific speech roles to different region, adjusting parameters such as rate, pitch, and volume individually.

WorldVoice independently stores the settings for each speech role. When a role is switched, its corresponding parameters—such as rate, pitch, and volume—are automatically applied, allowing each role to Keep its own voice characteristics. This feature is especially helpful for reading content in non-native languages.

* After selecting a region, available speech roles for that region are displayed. Choosing a speech role completes the region-to-voice-role mapping.
* If the selected speech role supports voice variant, variant options will be available for selection.
* Upon selecting a speech role, sliders for rate, pitch, volume, and the rate boost checkbox will adjust to that role’s settings. Adjustments apply only to the selected role independently.

### Consistency Settings:

* Keep main engine and locale engine consistent: Ensures the main and regional speech roles use the same speech engine. If a main speech role adjustment involves a different engine, regional speech roles reset and require re-selection.
* Keep main voice and locale voice consistent: Keeps the main and regional speech roles identical. Adjusting one automatically synchronizes the other.
* Keep parameter settings consistent between different speech roles: Synchronizes parameters rate, pitch, volume, and rate boost settings across all speech roles. Adjustments to one role affect all others.

The main speech role is configured through the NVDA voice settings panel, while locale speech roles are configured through WorldVoice’s speech role settings panel.

## Speech Pipeline

Through WorldVoice’s speech pipeline setting panel, you can configure various speech pipeline options and select the scope of the speech pipeline (global or WorldVoice-only).

* Globally supported speech pipeline: ignore comma between number, Number mode, number wait factor:, item wait factor, chinese space wait factor, sayall wait factor
* WorldVoice-only supported speech pipeline: detect language based on Unicode characters, number language.

* Detect language based on Unicode characters: Automatically detects the language region from Unicode characters and switches speech roles accordingly. Note: This feature may conflict with NVDA’s automatic language switching, so concurrent use is not recommended.
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
* **Add rate boost feature:** Allow rate boost for specific speech engines
* **Enhance UX:** Improve interactions in the Speech Engine and Log Record dialogs
* **Revise UI text:** Update UI text for style

## WorldVoice v4.0 Update

* Integrate the espeak engine into WorldVoice-supported engines.
* Add speech rate boost setting in NVDA - speech setting dialog.
* Add speech variant value setting in NVDA - speech setting dialog.
* NVDA - speech setting dialog will dynamically display rate boost setting UI if the engine/voice is supported.
* Users can set rate boost for individual voices in the WorldVoice speech setting dialog.
