# Digits of a script go to that script's language when numbers follow the text

- Branch: `fix/script-digit-language` (normal flow, DEVELOPMENT_WORKFLOW.md §3), from `master` `9bc5c8f`.
- Report: a Nepali user reads English with IBM TTS (main voice) and Nepali with eSpeak, number language "Follow surrounding text language" (the default). Numbers written in Devanagari digits are often skipped.
- G1 and G2 (§2.1) are `Decided by the user (2026-11-07)`. D1–D3 (§2.2) are `Decided by orchestrator with the recommended default; user may override before merge`.
- Baseline: `python3 -m pytest -q tests` 3769 passed, 0 skipped; `prek run --all-files` all Passed; protected paths unchanged.

## 0. Findings

### F1. A decimal digit always stays in the current run

`LanguageDetector._language_for_character` returns the current language for every `isdecimal()` character before it looks at the script (`addon/synthDrivers/WorldVoice/languageDetection/detector.py:47-56`, the digit branch at `:51-52`). Letters go through `find_language_for_script` (`detector.py:27-45`): current language → base language → configured assumed language → first installed language of the script → current language (`:31-45`). `add_detected_language_commands` calls it once per character with the run's language (`tmp_lang`) as current and the last language command's language (`cur_lang`) as base (`detector.py:58-83`, call at `:72`); `tmp_lang` carries across text items (`:63`, `:78`).

### F2. Many decimal digits are not Common script

`get_script` (`addon/synthDrivers/WorldVoice/unicodeScripts/lookup.py:8-15`) gives, from the generated `script_data.py` (checked on this branch): U+0030–0039 Common, U+FF10–FF19 (full-width) Common, U+0966–096F Devanagari, U+0660–0669 and U+06F0–06F9 Arabic, U+09E6 Bengali, U+0E50 Thai. `SCRIPT_LANGUAGES` maps Devanagari to `("hi", "sa", "mr", "ne")` and Arabic to `("ar", "fa", "ps", "ur")` (`languageDetection/scriptLanguages.py:63-64`, `:70-71`); the Devanagari assumed language defaults to `hi` (`scriptLanguages.py:119`).

### F3. Consequence for the reported case

With the main voice English, `२०८१` at the start of a text, alone, or in an item after an English item (`["link", "२०८१"]`) has no Devanagari letter before it in the run, so F1 keeps it in English and the IBM voice gets it. IBM encodes text with the Windows cp1252 best-fit conversion before sending it (`ref/IBM/IBM/driver/ibmeci.py:206-220`, used at `:382`); cp1252 has no Devanagari digits. Whether the engine then drops them or reads a replacement character is not verified on Windows; either way the wrong voice gets them. A scratch reproduction on `master` (installed `en_US`, `hi`, `ne`; number language `"default"`) gave `["२०८१ साल"]` → `['२०८१ ', (lang ne), 'साल']`, `["२०८१"]` → `['२०८१']`, `["link", "२०८१"]` → `['link', '२०८१']`, while `["नेपालमा ५० जिल्ला"]` is all `ne`. Setting the Devanagari assumed language to Nepali does not help: digits never reach `find_language_for_script`.

### F4. Where the number language acts today

- Stored values: `FOLLOW = "default"`, `MAIN = "main"`, or a locale (`addon/synthDrivers/WorldVoice/numberLanguage.py:7-10`).
- Under `MAIN` or a locale, `detect_with_number_language` wraps every number in `WVLangChangeCommand`s of the number language before calling the detector (`pipeline/numberStages.py:194-226`, condition at `:208`; wrapping in `wrap_numbers_for_detection`, `:158-191`, target at `:178`). Inside the wrapper the run's language is the number language, and F1 keeps the digits there. Under `FOLLOW` nothing is wrapped (`:208-209`). `NUMBER_RE` matches every Nd digit (`pipeline/numbers.py:22`), so every digit is wrapped.
- The driver wires the detector with `number_language=self._numberLanguage` (`addon/synthDrivers/WorldVoice/__init__.py:287-292`). `_numberLanguage` returns `NumberLanguageChoice.spoken` (`__init__.py:525-527`), not the stored value: a stored locale that no offered voice speaks reads as `FOLLOW` (`voices/numberLanguageChoice.py:40-44`). The pipeline reads the same value through `speechContext()` (`__init__.py:390`), so the detector and `detect_with_number_language` always agree on the number language. The detector's docstring calls it "the stored number language" (`detector.py:15-16`), which is inaccurate.
- Today the detector reads the number language only in `process_for_spelling`, once per call (`detector.py:94-96`).

### F5. Spelling

`process_for_spelling` sends a decimal digit to `_spelling_language_for_digit` (`detector.py:103-108`): under `FOLLOW` the current language (`:88-89`), under `MAIN` the spelling locale (`:92`), under a locale that locale when it has a voice, otherwise the spelling locale (`:90-92`). Letters use `find_language_for_script` with the spelling locale as base (`detector.py:109-119`). `patchedSpeakSpelling` uses it when detection is on and NVDA's "trust voice's language" is set (`__init__.py:360-365`).

### F6. The phase 35 rationale this fix supersedes

Phase 35 spec §6.3 kept the digit branch because "Without the branch, `abc ١٢٣` would switch to an Arabic voice" (`docs/superpowers/specs/2026-10-23-phase35-number-language-follow-design.md:211`). Tests that pin the old behaviour: `test_decimal_digits_never_switch_the_language` case `abc-arabic-indic` (`tests/test_language_detector.py:409-422`), `test_spelling_keeps_arabic_indic_digits_in_a_latin_run` case `default` (`tests/test_language_detector.py:474-477`), and the Hypothesis properties `test_property_digits_never_start_a_detected_run` (`:718-728`) and `test_property_spelling_digits_carry_the_number_language`, its `"default"` branch (`:732-752`). A scratch run of the full suite with the change of §4 failed exactly these four tests (3765 passed, 4 failed).

### F7. Digit mode names symbols before detection

Under `FOLLOW`, digit mode names a symbol between digits for the language in force before detection (`pipeline/numberStages.py:359-363`, `name_of=namer(number_language or language)` at `:389`, with `number_language` None under `FOLLOW`). The name is then detected by its own letters, like any text.

### F8. Test harness wiring

The speak harness builds its detector without a number-language provider (`tests/test_worldvoice_speak.py:211-215`), so it always sees `FOLLOW`; the driver passes one (F4). Its voices are `{"en": "A:en", "zh": "B:zh"}` (`tests/test_worldvoice_speak.py:21`), with no Devanagari voice. The end-to-end digit property (`tests/test_worldvoice_speak.py:979-1013`) samples `"٣"` but no Arabic voice is installed there, so it is not affected by this fix.

## 1. Problem

Under "Follow surrounding text language", a digit of a script other than Common (Devanagari, Arabic-Indic, Bengali, Thai, …) goes to the voice of the current run even when that voice's language is not written in that script (F1). With the main voice English, Devanagari digits with no Devanagari letter before them reach the English voice, which cannot read them (F3).

## 2. Goals and non-goals

### 2.1 Goals (Decided by the user, 2026-11-07)

- G1. **Supersede phase 35 §6.3's rationale.** Under number language `FOLLOW`, a decimal digit whose Unicode script is not Common, Inherited or unknown is treated like a letter of its script: it goes through `find_language_for_script` (current language → base language → configured assumed language → first installed language → current language). When the current language does not cover the digit's script, the digit goes to that script's language. This includes `abc ١٢٣` switching to Arabic when an Arabic voice is installed.
- G2. **Mixed-script numbers stay per character**, no special case: in `1२3`, `1` stays in the current language and `२3` goes to Nepali (`3` is Common and follows the run).

### 2.2 Orchestrator defaults (Decided by orchestrator with the recommended default; user may override before merge)

- D1. **Which number language the detector reads:** the provider it already has, i.e. the spoken value (F4). A stored locale that no offered voice speaks behaves as `FOLLOW` in the detector, exactly as `detect_with_number_language` already treats it (no wrapping). Read once per `add_detected_language_commands` call, like the settings (`detector.py:59-60`). The docstring at `detector.py:15-16` is corrected to say so.
- D2. **The speak harness passes the provider** the driver passes (`number_language=synth._numberLanguage`), so end-to-end tests under `MAIN` see what the driver sees. Without it the harness detector would treat every sequence as `FOLLOW`.
- D3. **Spelling under `FOLLOW` uses the letter rule for digits** (the same rule as G1, base language = the spelling locale, as letters already use, F5), so spelling `२` alone under an English locale goes to Nepali. Under `MAIN` and a locale spelling is unchanged.

### 2.3 Non-goals

- `MAIN` and locale number languages: unchanged. Their digits are wrapped before detection (F4) and the detector keeps them in the wrapper's language, as today.
- ASCII and full-width digits (Common, F2): unchanged in every mode.
- The digit-mode symbol name under `FOLLOW` (F7): a known, pre-existing limitation, not fixed here. In `५.५` with digit mode, the main voice English and a Nepali voice installed, the name of "." is English (named before detection); detection then gives the digits to Nepali and the name to English by its Latin letters, so the number is spoken by two voices.
- The Devanagari assumed language default (`hi`, F2): a user setting. With both `hi` and `ne` installed (eSpeak offers both), Devanagari digits and letters go to Hindi until the user picks Nepali in the Unicode Detection panel.
- No conversion of script digits to ASCII (phase 35 §6.4 keeps original characters).
- No change to `wrap_numbers_for_detection`, `detect_with_number_language`, the number stages, or any engine driver.

## 3. What an NVDA user hears

Main voice English (IBM), Nepali installed (eSpeak), number language "Follow surrounding text language", Devanagari assumed language Nepali (or Hindi not installed):

| Input | Before | After |
| --- | --- | --- |
| `नेपालमा ५० जिल्ला` | Nepali | Nepali (the current language covers Devanagari) |
| `२०८१ साल` | `२०८१ ` English, `साल` Nepali | all Nepali, one voice |
| `२०८१` alone | English (skipped or misread) | Nepali |
| `["link", "२०८१"]` | `link` English, digits English | `link` English, digits Nepali |
| `२०८१ link` | digits English | digits Nepali, `link` English |
| `abc 123`, `abc １２３` | English | English (Common digits) |
| `abc ١٢٣`, Arabic voice installed | English | `abc ` English, `١٢٣` Arabic |
| `२०८१`, no Devanagari voice | English | English (no voice for the script) |
| `२०८१`, number language "Follow main language" | English | English |
| `1२3` | English | `1` English, `२3` Nepali |
| Spelling `२` (English locale) | English | Nepali |

No settings panel, string, or stored value changes.

## 4. Design

All changes are in `languageDetection/detector.py` (NVDA-free core module, snake_case).

### 4.1 Normal detection

- New `LanguageDetector._script_language(self, character, current_language, base_language, settings) -> str`: the current language when `get_script(ord(character))` is `None`, `"Common"` or `"Inherited"`; otherwise `find_language_for_script(script, current_language, settings, base_language=base_language)`. This is the existing letter part of `_language_for_character` (`detector.py:53-56`), moved so spelling can share it.
- `_language_for_character(self, character, current_language, base_language, settings, digits_by_script)`: when `character.isdecimal()` and not `digits_by_script`, the current language (today's rule, for `MAIN` and locales); otherwise `_script_language(...)`. `digits_by_script` is a required positional argument. The comment above the digit branch is rewritten to say why only `FOLLOW` reads a digit's script (other number languages wrap the digits before detection).
- `add_detected_language_commands` reads `digits_by_script = self._number_language() == FOLLOW` once, next to the settings read (`detector.py:59-61`), and passes it on each call (`:72`).

### 4.2 Spelling

- `process_for_spelling`: whitespace keeps the spelling locale; a decimal digit under `MAIN` or a locale uses `_spelling_language_for_digit`; every other character, digits under `FOLLOW` included, uses `_script_language(character, current_language, default_language, settings)`.
- `_spelling_language_for_digit(self, number_language, default_language)`: the `FOLLOW` branch and the `current_language` parameter go (unreachable); the rest is unchanged (`detector.py:90-92`). Its docstring drops the "current one when it follows the text" clause.

### 4.3 Unchanged guarantees, by construction

- Common/Inherited/unknown-script digits return the current language in both branches, as before.
- `find_language_for_script` returns the current language when the current language covers the script (`detector.py:31-32`) and when no installed language covers it (`:45`), so Nepali text and "no voice for the script" are unchanged.
- A script with no entry in `SCRIPT_LANGUAGES` (e.g. Adlam digits) keeps the current language (`detector.py:30-32`).

### 4.4 Error handling and threading

No new failure mode: the provider is already called by `process_for_spelling` (`detector.py:96`); `add_detected_language_commands` stays a generator that reads its inputs on the first `next()`, as the settings read does today. After `terminate` the filter is unregistered by the teardown (`__init__.py:293-297`) and `speak` returns early (`__init__.py:333-335`), so the provider (which needs `_numberLanguageChoice`) is not reached.

## 5. Strings, translations and documentation

- No new or changed UI string; no `.po` change.
- `addon/doc/zh_TW/readme.md` only (root `readme.md` and other languages are synced later by the user):
  - Number-language bullet "跟隨前後文語言（預設）" (`readme.md:42`): add one sentence, proposed: 「屬於特定文字的數字（例如天城文數字、阿拉伯－印度數字），若目前的語言不使用這種文字書寫，則依「字元集假設的語言」的順序，交給使用這種文字的語言朗讀。」
  - `## 下一版更新` (`readme.md:95`): one entry, proposed: 「**特定文字的數字交給該文字的語言：** 數字語言為「跟隨前後文語言」時，天城文數字、阿拉伯－印度數字這類屬於特定文字的數字，若前面沒有同一種文字，現在會交給使用這種文字的語言朗讀，不再交給可能唸不出來的主要語音。例如主要語音為英文時，單獨出現的「२०८१」會由尼泊爾語或印地語語音朗讀（依天城文字元假設的語言）。拼讀時也一樣。一般數字（0～9）與全形數字不受影響。」
- Phase 35 spec §6.3: strike the superseded sentence with `~~…~~` and add "Corrected by `fix/script-digit-language`" (a docs commit on this branch).

## 6. Settings, data and compatibility

No settings, config keys, or stored data change. Users who relied on `abc ١٢٣` staying in the main voice can pick "Follow main language". Users with both Hindi and Nepali voices get the Devanagari assumed language's choice, as letters already do (§2.3).

## 7. Test plan

### 7.1 Existing expectations that change (deliberately)

- `tests/test_language_detector.py:409-422` `test_decimal_digits_never_switch_the_language`: the `abc-arabic-indic` case becomes `["abc ", ("lang", "ar"), "١٢٣"]`; the test is renamed to describe the new rule; the comment above it cites this spec.
- `tests/test_language_detector.py:474-477` `test_spelling_keeps_arabic_indic_digits_in_a_latin_run`: the `default` case becomes `[("abc", "en_US"), ("١٢", "ar")]`; `main` stays `[("abc١٢", "en_US")]`.
- `tests/test_language_detector.py:718-728` `test_property_digits_never_start_a_detected_run`: see 7.3.
- `tests/test_language_detector.py:732-752` `test_property_spelling_digits_carry_the_number_language`: see 7.3.

### 7.2 New unit tests (`tests/test_language_detector.py`)

Installed `en_US`, `ne_NP` unless stated; base `en_US`; number language `FOLLOW` unless stated.

- The user's scenarios: `["२०८१ साल"]` → `[("lang","ne"), "२०८१ साल"]`; `["२०८१"]` → `[("lang","ne"), "२०८१"]`; `["link", "२०८१"]` → `["link", ("lang","ne"), "२०८१"]`; `["२०८१ link"]` → `[("lang","ne"), "२०८१ ", ("lang","en_US"), "link"]`.
- Unchanged: `["नेपालमा ५० जिल्ला"]` → one `ne` run; `["abc 123"]` and `["abc １２３"]` unchanged; no Devanagari voice (`en_US`, `zh_TW`): `["२०८१"]` unchanged; a document language command of a covering language (`[L("ne_NP"), "२०८१"]`) unchanged.
- `MAIN` and a locale keep wrapped digits: number language `"main"` with `[WV("en_US"), "२०८१", WV("en_US")]`, and number language `"en_US"` with the same, give no `ne` command; `"main"` with an unwrapped `["२०८१"]` gives none either (the rule depends on the number language, not on the wrapper).
- Assumed language decides the target: installed `en_US`, `hi_IN`, `ne_NP`; Devanagari preference `ne` → `ne`, `hi` → `hi`.
- Base language before the assumed language: installed `en_US`, `hi_IN`, `ne_NP`, Devanagari preference `ne`, `[L("hi_IN"), "abc २"]` → the digit goes to `hi_IN` (the base), not `ne`.
- Mixed `["1२3"]` → `["1", ("lang","ne"), "२3"]`.
- Arabic: installed `en_US`, `ar`: `["abc ١٢٣"]` → `["abc ", ("lang","ar"), "١٢٣"]`.
- The number language is read once per sequence: a counting provider, `list(detect(["१ a २", "३"]))`, reads == 1.
- Spelling: `process_for_spelling("२", "en_US")` → `[("२","ne")]` under `"default"`, `[("२","en_US")]` under `"main"`, `[("२","en")]` under `"en"` (installed `en_US`, `ne_NP`); `"1२"` under `"default"` → `[("1","en_US"), ("२","ne")]`; `"नेपाल५"` → one `ne` run.

### 7.3 Property tests (Hypothesis, `tests/test_language_detector.py`)

- Alphabets: `SCRIPT_SAMPLES` gains `"२०"`; `VOICES` gains `"ne_NP"`; the Devanagari preference is drawn from `["hi", "mr", "ne"]`.
- `is_letter` becomes `has_script`: any character whose script is not `None`/Common/Inherited, decimal digits included. The two letter properties (`test_property_letters_go_to_installed_languages`, `test_property_inserted_commands_prefer_a_covering_base`) therefore also check script digits under `FOLLOW` (the scenario detector's default).
- `test_property_digits_never_start_a_detected_run` is replaced by:
  - under `FOLLOW`: a detection-inserted command directly followed by text starting with a decimal digit only happens for a digit with a script, and the inserted language covers that script;
  - under `"main"` and locales (`"main"`, `"en"`, `"zh_TW"`, `"fr"`): no detection-inserted command is directly followed by a decimal digit (phase 35 §11.4 item 4, kept for these values).
- `test_property_spelling_digits_carry_the_number_language`, `"default"` branch: a run after the first that starts with a decimal digit starts with a digit that has a script, and the run's language covers that script.
- End to end (`tests/test_worldvoice_speak.py:979-1013`): pieces gain `"२"`, the property installs an `ne` voice, and the oracle gives a Devanagari digit the Nepali voice under `"default"` (and makes it the run voice that following digits follow); `"main"`/locales unchanged.

### 7.4 End-to-end tests (`tests/test_worldvoice_speak.py`)

With the harness detector wired as the driver (D2) and an `ne` voice added for the test: number language `"default"`, detection on, both timings: `["२०८१"]` is heard as `[(NE, "२०८१")]`, `["link", "२०८१"]` as `[(EN, "link"), (NE, "२०८१")]`; number language `"main"`: `["२०८१"]` stays `[(EN, "२०८१")]`.

### 7.5 Mutation testing

`detector.py` is a core decision module (already in `[tool.mutmut] source_paths`, `pyproject.toml:45-73`). Run mutmut scoped to it on a scratch copy, at most 3 children, with the memory guard; record surviving mutants and reasons in the ledger.

### 7.6 Windows / NVDA manual items (not verified on Linux)

- M1. IBM TTS English main voice, eSpeak Nepali, number language "Follow surrounding text language", Devanagari assumed language Nepali: read `२०८१`, `२०८१ साल`, and a link `link` followed by `२०८१`; the digits are read by eSpeak Nepali.
- M2. Same setup, spell `२` with "trust voice's language" on: Nepali.
- M3. Arabic voice installed: `abc ١٢٣` reads the digits with the Arabic voice.

## 8. Open questions

None. G1 and G2 were decided by the user; D1–D3 follow from the existing wiring.
