# Punctuation at the start of a text item follows the text after it

- Branch: `fix/leading-punctuation-language` (normal flow, DEVELOPMENT_WORKFLOW.md §3), from `master` `6ea5665`.
- Report (second email from the reporter of `fix/script-digit-language`, after WorldVoice 7.1): English is read by IBM TTS (the main voice) and Nepali by eSpeak. When a line starts with punctuation such as a quote or a left parenthesis, WorldVoice gives that punctuation to IBM TTS although the text after it is Nepali. Every such line gets an extra synthesizer switch and pause. Punctuation in the middle of a line is read by the voice of the text around it, which he likes.
- U1–U3 (§2.1) are `Decided by the user (2026-11-09)`. D1–D8 (§2.2) are `Decided by orchestrator with the recommended default; user may override before merge`. Q1–Q4 (§8) are open questions for the user; this spec is written with their recommended options. Q1 matters most: F4 shows that the premise of U3 does not fully hold.
- Baseline: `python3 -m pytest -q tests` 3808 passed, 0 skipped; `prek run --all-files` all Passed; protected paths unchanged.
- Prototype: F4, F6, §3 and §7.1 rest on a throwaway change to `languageDetection/detector.py` that implemented D1–D4. I ran it in this worktree against the speak harness (with NVDA's real `characterProcessing` from `ref/nvda`) and against the full suite, then restored the file with `git checkout`. It is not committed; the plan implements the rule anew.

## 0. Findings

### F1. Characters with no script of their own stay in the run in progress

`LanguageDetector._script_language` returns the current language for a character whose script is `None`, `"Common"` or `"Inherited"` (`addon/synthDrivers/WorldVoice/languageDetection/detector.py:48-54`, the check at `:52-53`). `_language_for_character` also returns the current language for any decimal digit when the number language is not "Follow surrounding text language" (`detector.py:56-64`, `:62-63`). `add_detected_language_commands` calls it once per character, with the run's language (`tmp_lang`) as the current language and the last language command's language (`cur_lang`) as the base (`detector.py:66-99`, call at `:82-88`). `tmp_lang` changes only when a character's language has another primary language (`:89-94`). It is carried from one string to the next (`:73`, `:94`) and reset only by a `LangChangeCommand` or `WVLangChangeCommand` (`:75-78`). So punctuation, symbols, spaces and Common digits at the start of a string take the language the previous string ended in. If no string came before, they take the document's language or the synth's language (`:71-73`).

### F2. Reproduction on `master`

The runs used the speak harness (`tests/test_worldvoice_speak.py:394-424`) with an `ne` voice added (`NE`, `:345`) and number language `"default"`. Detection timing was "before", and NVDA's processing was simulated at symbol level "some" with NVDA's real `characterProcessing` (F4):

| Input (main voice) | Heard on `master` |
| --- | --- |
| `"नेपाल"` (en) | IBM gets a blank item, then eSpeak `नेपाल` |
| `(नेपाल)` (en) | IBM `(`, eSpeak `नेपाल)` |
| `“नेपाल”` (en) | IBM blank, eSpeak `नेपाल` |
| `- नेपाल` (en) | IBM `-`, eSpeak `नेपाल` |
| `["link", '"नेपाल"']` (en) | IBM `link` and a blank, eSpeak `नेपाल` |
| `abc "नेपाल"` (en) | IBM `abc`, eSpeak `नेपाल` (mid-line) |
| `नेपाल "नेपाल"` (en) | all eSpeak |
| `「中文」`, `（中文）`, `(中文)` (en, zh voice installed) | English voice gets the bracket, Chinese the rest |
| `「中文」` (zh) | all Chinese |
| `"Hello"` (ne, en voice installed) | eSpeak Nepali gets a blank, English the rest |

At symbol level "most", the blank becomes NVDA's English name: IBM says "quote" or "left paren" before the switch. The orchestrator's raw-text runs (no NVDA simulation) gave the same split points.

### F3. Where detection runs, and in which language NVDA names symbols

- **Default timing.** Detection timing defaults to "after" (`addon/synthDrivers/WorldVoice/languageDetection/settings.py:21`).
- **"before".** Detection is a `filter_speechSequence` handler, registered and then placed after WorldVoice's pipeline stages (`addon/synthDrivers/WorldVoice/__init__.py:505-514`, `pipeline/registry.py:175-178`). NVDA's `speak()` then runs `processText` on each string (`ref/nvda/source/speech/speech.py:1137`, `:1214-1232`).
- **"after".** Detection runs in `WorldVoice.speak` (`__init__.py:336-337`), after NVDA's `processText`. In both timings the pipeline stages (`pipeline/registry.py:149-161`) run before detection.
- **Language used for symbol names.** `processText` uses the language of the last NVDA `LangChangeCommand`, or `getCurrentLanguage()` (`speech.py:1177`, `:1214`, `:1221`). That is the synth's language when "trust voice's language" is on, its default (`speech.py:313-325`, `ref/nvda/source/config/configSpec.py:39`). WorldVoice's commands are `WVLangChangeCommand`, which never derives from `LangChangeCommand` (`addon/synthDrivers/WorldVoice/speechCommands.py:4-17`). So with timing "before", NVDA names the symbols of every string in the synth's language (English here), including strings WorldVoice gave to Nepali. That is why the trailing `"` of `"नेपाल"` at level "most" is read by eSpeak as the English word "quote" today.

### F4. What NVDA leaves of a leading mark (corrects the investigation's premise for U3)

I checked this with NVDA's real `characterProcessing` and the symbol tables in `ref/nvda` (the loader `tests/pipeline_harness.py:424-448`), locale `en`. `processText` substitutes symbols and then strips the text (`speech.py:192-214`, strip at `:214`). A symbol below the current level is dropped (replaced by a space) unless its `preserve` keeps it (`ref/nvda/source/characterProcessing.py:629-637`). The default symbol level is "some" (`configSpec.py:38`, `SymbolLevel.SOME = 100` at `characterProcessing.py:160`).

| Mark (English table line) | Levels "none" and "some" | Levels "most" and "all" |
| --- | --- | --- |
| `"`, `“`, `”` (`locale/en/symbols.dic:47`, `:105-106`, level most, no preserve) | dropped; at the start of a string, stripped | " quote ", " left quote " (Latin letters) |
| `(`, `)`, `-` (`symbols.dic:61-62`, `:67`, preserve always) | kept as the character | " left paren(" (name and character) |
| `「`, `（` and other CJK brackets (no entry in the English table) | kept | kept |
| ASCII digits (`2024年`) | kept | kept |

The investigation said the fix works only with timing "before", because NVDA has already turned symbols into words in "after". That holds for quotes, and for every named mark at "most" and "all". It does not hold for marks NVDA keeps as characters. At NVDA's default level, `(`, `)`, `-`, CJK brackets and digits reach the detector unchanged in "after" too, and the detector change of §4 moves them. Prototype runs in "after" with NVDA's processing at "some":

- `(नेपाल)`: master gives IBM `(` and eSpeak `नेपाल)`; the prototype gives all eSpeak.
- `"नेपाल"`: all eSpeak on both. NVDA had already dropped the quote.

The detector is the same function in both timings, so limiting the rule to "before" would need a new input. See Q1.

### F5. Nepali has no symbol table

`ref/nvda/source/locale/ne/` holds only `LC_MESSAGES` and `characterDescriptions.dic`. `_getSpeechSymbolsForLocale` raises `LookupError` when it finds no built-in table (`characterProcessing.py:413-427`). `processSpeechSymbols` and `processSpeechSymbol` then fall back to `"en"` (`:719-723`, `:735-739`). Every other locale also uses the English built-in table as its base (`:458-462`). For speech this changes nothing here, because NVDA names symbols in the synth's language anyway (F3). It matters for spelling (§2.2 D7).

### F6. Number-language wrappers split a text item into several strings

- **Where the wrappers come from.** Under "main" and a locale, `detect_with_number_language` wraps every number in `WVLangChangeCommand`s before detection (`pipeline/numberStages.py:194-226`, condition at `:208`; wrappers at `:185-188`). Under a locale, `inject_numbers` also wraps them (`:287`, `:452-456`).
- **How the item comes back together.** After detection, the wrappers that keep the voice are dropped and the pieces are glued back (`:211-225`). So during detection, `नेपाल (2024) नेपाल` is `"नेपाल ("`, wrapper, `"2024"`, wrapper, `") नेपाल"`, and the last string continues the item.
- **What a plain per-string rule does.** A prototype that applied the lookahead to every string moved the `)` of that example from the English number voice to Nepali under "main". It also failed 13 existing "main"/locale end-to-end tests, for example `test_main_language_numbers[zh-main]` and `test_a_sign_after_a_space_moves_with_the_number[han-sentence]`. D3 below avoids this.
- **The other wrapper stage.** `inject_numbers` creates a test opening at `numberStages.py:376` only to ask `deduplicate_language_command` whether the wrapper stays; it never yields it.

### F7. Pipeline stages that can split a leading mark from its text

All run before detection in both timings (F3), in the order of `STAGES` (`pipeline/registry.py:149-161`):

- **Punctuation pause** (`pipeline/punctuation.py`). Enabled by default (`pipeline/settings.py:252-254`), but the character list is empty by default (`:286-288`). A configured mark followed by text is an internal pause point (`punctuation.py:153-160`). So with `"` configured, `"नेपाल"` becomes `'"'`, `PunctuationBreakCommand`, `'नेपाल'`, `'"'` (`:164-178`). A mark at the end of an item before more text also gets a pause (`:175-178`).
- **Number pauses.** With a group size above 0, edge breaks separate a number from the text next to it in its item (`numberStages.py:298`, `:449-451`, `:457-458`). Item edge breaks go at item ends (`:437-438`, `:459-460`). Between two numbers there is a gap break.
- **Space pause between CJK and Southeast Asian characters.** A plain `BreakCommand` at a space with such a character on both sides (`pipeline/unspaced.py:65`). `「` and `。` do not count (`unspaced.py:29-37`).
- **Segment pause.** Off by default (`pipeline/settings.py:308-321`). It cuts after whitespace, at item boundaries, or as a last resort at the length limit (`text/chunker.py:56-69`).
- **Item pause.** A plain `BreakCommand` between two text items (`pipeline/items.py:36-51`), on by default (10 × 1 ms, `settings.py:223-230`). It never splits an item.

NVDA's say all splits a string after the last sentence end and speaks the rest with the next line (`ref/nvda/source/speech/speechWithoutPauses.py:32-35`, `:150-170`). A sentence that begins with a quote after `. ` on the same line therefore starts a string of a later `speak()` call.

### F8. Spelling

- **Where it is used.** `patchedSpeakSpelling` uses `process_for_spelling` when detection is on and "trust voice's language" is set (`__init__.py:360-365`).
- **Its rule today.** Whitespace keeps the spelling locale (`detector.py:115-116`). Digits under "main" or a locale use the number-language rule (`:117-118`). Every other character uses `_script_language` with the current language (`:119-126`), so a leading mark stays in the spelling locale.
- **How NVDA names it.** NVDA names each spelled character in the locale WorldVoice passes. For Nepali that falls back to English (F5).

### F9. Test harness

- `speak_through_stages` runs the stages, then detection with timing "before", then the optional `nvda` function, then `speak` (`tests/test_worldvoice_speak.py:394-424`). Without `nvda` it does not simulate NVDA's `processText`, so its "after" runs feed raw punctuation to detection. They do not show what NVDA does.
- `heard_through_nvda` (`:915-918`) simulates NVDA with `nvda_processes_each_item` (`:654-676`): NVDA's real `processSpeechSymbols` at level "some", in the synth's language.
- The harness voices are `{"en": "A:en", "zh": "B:zh"}` (`:21`); tests add `NE` (`:345`). `main` supports `"en"` and `"zh"` only (`:409-412`).

## 1. Problem

Characters with no script of their own at the start of a text item take the language of the run before them (F1). At the start of an utterance, or after an item in the main language, that is the main language. So a Nepali line that starts with a quote, a parenthesis or a dash switches to the main voice for that one mark and then to the Nepali voice (F2). The same happens with CJK brackets before Chinese text when the main voice is English, and in mirror form with Latin text when the main voice is Nepali. Every such line costs one extra synthesizer switch and its pause.

## 2. Goals and non-goals

### 2.1 Decided by the user (2026-11-09)

- **U1. Approach A.** Within one text item, the Common and Inherited characters before the item's first character that has a script with candidate languages go to the language that first script character gets. Leading punctuation, symbols, spaces and digits therefore follow the text after them. An item with no such character (all Common) stays in the current language, as today. Common characters in the middle of an item keep following the run before them, unchanged.
  - Rejected: approach B, direction by punctuation type (opening marks look forward, others look back). Straight quotes are ambiguous, and mid-line punctuation is not a complaint.
- **U2. Accepted side effect.** Under number language "Follow surrounding text language", leading ASCII digits (Common) follow the text after them too. With main voice English, `2024年` goes to Chinese. With main voice Chinese, `1. Introduction` and `3 apples` go to English. Under "Follow main language" and a locale, numbers are wrapped before detection and must not change (verified in §4.3).
- **U3. Accepted limitation.** It takes effect only with detection timing "before". The default "after" stays unchanged, because NVDA has already turned the symbols into words. Document this, and the readme should tell users.
  - **This premise is only partly true (F4).** In "after", marks NVDA keeps as characters at its default level (`(`, `)`, `-`, CJK brackets, digits) do reach the detector, and the rule moves them too. This spec is written with Q1's recommended option: the rule is not limited to a timing, and the readme says what each timing covers.

### 2.2 Orchestrator defaults (Decided by orchestrator with the recommended default; user may override before merge)

- **D1. The deciding character.** It is the first character of the string that either:
  - has a script of its own: `get_script` is not `None`, `"Common"` or `"Inherited"`, the test `_script_language` already uses (`detector.py:52`); or
  - is a decimal digit while the number language is not "Follow surrounding text language".

  Under "Follow surrounding text language" a script digit (Devanagari, Arabic-Indic, …) decides, as the 7.1 rule already treats it like a letter (`detector.py:56-64`). A Common digit (ASCII, full-width) does not decide and belongs to the leading run (U2).

  The leading run is everything before the deciding character. A character of a script with no entry in `SCRIPT_LANGUAGES` (for example Cherokee) still decides. It gets the current language (`detector.py:31-33`), so nothing changes. Stopping there, instead of looking past it, keeps the rule from reaching across text the detector cannot place.
- **D2. The language of the leading run** is what the deciding character would get: `_language_for_character(deciding character, tmp_lang, cur_lang, settings, digits_by_script)`, with the same inputs the per-character loop passes today (`detector.py:82-88`). Leading Common characters never change `tmp_lang` (F1), so these are exactly the inputs the deciding character sees today. This keeps the G1 chain of `fix/script-digit-language`: current language, base language, assumed language, first installed language. If the current language covers the script, or no installed language does, the result is the current language and nothing changes.
  - **Under "main" and a locale, a decimal digit ends the leading run and decides nothing.** The leading run then keeps the current language, as today. This keeps the phase 35 §11.4 item 4 property ("no detection-inserted command is directly followed by a decimal digit") true in the detector itself, even for unwrapped digits, which never reach it in the driver (F6).
- **D3. What a text item is.** It is a string of the detector's input, except a string that directly follows a `WVLangChangeCommand`. Such a string continues an item that a number wrapper split (F6). It gets no lookahead, so its leading Common characters keep following the run before them.
  - Before detection, only the number wrappers insert `WVLangChangeCommand`s (`numberStages.py:185-188`, `:452-456`). The detector's own commands are output, never input.
  - A string after anything else starts an item: an NVDA `LangChangeCommand`, a `BreakCommand` of any kind, an `IndexCommand`, any other command, another string, or the start of the sequence. For breaks, see Q2.
- **D4. The lookahead stays within one string.** It never crosses a command or reaches into the next string. A string with no deciding character (for example `'"'` alone, or `"("` before a wrapped number) keeps the current language, as today.
- **D5. Document language commands keep today's meaning.** After an NVDA `LangChangeCommand`, `cur_lang` and `tmp_lang` are the document's language (`detector.py:75-78`), and D2 uses them. `[L("ne_NP"), '"नेपाल"']` changes nothing, because Nepali covers Devanagari. `[L("en"), '"नेपाल"']` gives the quote to Nepali, as the letters already go. `[L("de_DE"), ", hallo"]` (German, no voice) gives `, ` to English with `hallo`.
- **D6. No new switch.** In each string the rule moves the point where the language changes to the string's start. It never adds a change, and it never changes which languages are switched to, or in what order (§4.2). This is a property test (§7.3).
- **D7. Spelling is unchanged.** `process_for_spelling` keeps its rule (F8), for three reasons:
  - Spelling speaks one character at a time, so the voice of a leading mark only decides whose name the user hears. In the spelling locale that is the name NVDA would say without WorldVoice; a Nepali voice would read NVDA's English name (F5).
  - Character navigation, the common case, spells one character, which has nothing after it.
  - Spelling already treats whitespace differently from reading (`detector.py:115-116`).
- **D8. The detector is the only layer that changes.** No change to the pipeline stages, `detect_with_number_language`, the driver, the panels, settings or any engine.

### 2.3 Non-goals

- Opening punctuation in the middle of an item (`abc "नेपाल"`): unchanged (U1). It only moves when a pause break has made it the start of a string (Q2).
- Looking across commands or items: a mark alone in its own item (`["(", "नेपाल)"]`) or split off by a configured punctuation pause (Q3) stays in the current language.
- Symbol names NVDA has already inserted with timing "after" (`quote`, `left paren`): they are Latin letters and go by their own script, as today.
- The language NVDA names symbols in with timing "before" (F3): unchanged. A leading `"` at level "most" becomes the English word "quote", now read by the Nepali voice, as trailing and mid-line quotes already are.
- Spelling (D7).

## 3. What an NVDA user hears

The default setup has the main voice English (IBM) and eSpeak Nepali installed, number language "Follow surrounding text language", and NVDA symbol level "some" unless stated. "Blank" means a voice that gets only whitespace, which still costs a switch.

Timing "before":

| Input | Before | After |
| --- | --- | --- |
| `"नेपाल"` | IBM blank, then eSpeak | eSpeak only |
| `"नेपाल"`, level "most" | IBM "quote", eSpeak "नेपाल quote" | eSpeak "quote नेपाल quote" |
| `(नेपाल)` | IBM `(`, eSpeak | eSpeak only |
| `“नेपाल”`, `- नेपाल` | IBM blank or `-`, eSpeak | eSpeak only |
| `link`, then `"नेपाल"` (two items) | IBM `link` and a blank, eSpeak | IBM `link`, eSpeak |
| `" २०८१` | IBM blank, eSpeak digits | eSpeak only |
| `abc "नेपाल"` | IBM `abc`, eSpeak | unchanged (mid-line) |
| `नेपाल "नेपाल"` | eSpeak | unchanged |
| `"` alone | IBM | unchanged (nothing follows) |
| `(2024) नेपाल` | IBM `(2024)`, eSpeak | eSpeak only (U2) |
| `(2024) नेपाल`, number language "Follow main language" | IBM `(2024)`, eSpeak | unchanged |
| `नेपाल (2024) नेपाल`, "Follow main language" | eSpeak, IBM `2024)`, eSpeak | unchanged (D3) |

Main voice English with a Chinese voice: `「中文」`, `（中文）` and `(中文)` move from English bracket plus Chinese text to all Chinese. `2024年` moves from English `2024` plus Chinese `年` to all Chinese (U2). Under "Follow main language" it is unchanged.

Main voice Chinese with an English voice: `「中文」` and `(中文)` stay all Chinese (unchanged). `1. Introduction` and `3 apples` become all English (U2); under "Follow main language" they are unchanged.

Main voice Nepali with an English voice: `"Hello"` moves from Nepali blank plus English to English only.

Timing "after" (the default), NVDA symbol level "some":

| Input | Before | After |
| --- | --- | --- |
| `"नेपाल"`, `“नेपाल”` | eSpeak (NVDA dropped the quote) | unchanged |
| `(नेपाल)`, `- नेपाल` | IBM `(` or `-`, eSpeak | eSpeak only |
| `「中文」` (main English) | English `「`, Chinese | Chinese only |
| `2024年` (main English) | English `2024`, Chinese | Chinese only |
| any mark at level "most" or "all" | IBM says the name, eSpeak the text | unchanged (the name is English words) |

No settings panel, UI string or stored value changes.

## 4. Design

All changes are in `languageDetection/detector.py`, an NVDA-free core module (snake_case).

### 4.1 Detection

In `add_detected_language_commands`, for each string that starts an item (D3):

1. Find the deciding character (D1). If there is none, or under "main" and a locale it is a decimal digit, process the string exactly as today.
2. Otherwise compute the leading language (D2) once. Every character before the deciding character uses it as its target, in place of `_language_for_character`. From the deciding character on, the loop is unchanged.

A string that continues an item (directly after a `WVLangChangeCommand`) is processed exactly as today. The comparison that decides a switch (`primary_language(target) != primary_language(tmp_lang)`, `detector.py:89`) and the yielded commands are unchanged. Settings and the number language are still read once per sequence (`:67-70`). The plan decides the helper names. The comment above the loop cites this spec.

### 4.2 Invariants

For every input sequence, compare the new rule with today's per-character rule (the oracle):

- The detection-inserted commands are the same: same languages, same order, same count. In each string, today's rule switches at the deciding character, from `tmp_lang` to X. The new rule switches at the string's start, from the same `tmp_lang` to the same X, or not at all when today's does not. In both cases `tmp_lang` is X after the deciding character, so the rest of the string and every later string are processed identically.
- The text is unchanged and in order: only the cut points between strings move.
- A character keeps today's language unless it is in the leading run of an item-start string. A leading-run character gets the language the oracle gives the deciding character.
- What the user hears has at most as many voice changes as today. The voice before the moved switch point is no longer given the leading run, and when that run was the whole of its turn (a blank, or a single mark), one change disappears (F2).

### 4.3 Unchanged by construction

- **Numbers under "main" and a locale.** Every Nd digit is wrapped (`pipeline/numbers.py:22`, `numberStages.py:208`).
  - The string inside a wrapper and the string after it continue the item (D3), so they are processed as today.
  - A string before a wrapper may end with the number's sign or a mark (`"("`). It has no deciding character before the wrapper, because under these number languages digits do not decide (D2) and the number itself sits in the next string. So it also keeps today's language.
  - The prototype with D3 passed every existing "main" and locale test (F6 lists what failed without it).
- **A string that starts with a character of a script** has an empty leading run.
- **When the current language covers the deciding character's script**, D2 gives the current language.
- **When no installed voice covers the script**, D2 gives the current language (`detector.py:43-46`).
- **Items with only Common characters** are unchanged.

### 4.4 Error handling and threading

There is no new failure mode. The lookahead reads only the string at hand, and calls the same `_language_for_character` once more per item-start string. `add_detected_language_commands` stays a generator that reads its inputs on the first `next()`.

## 5. Strings, translations and documentation

- No new or changed UI string; no `.po` change.
- `addon/doc/zh_TW/readme.md` only. The root `readme.md` and the other languages are synced later by the user. NVDA UI names are quoted from NVDA's zh_TW catalog: 「標點及符號等級」 (`ref/nvda/source/locale/zh_TW/LC_MESSAGES/nvda.po:13906-13907`, accelerator and colon dropped) and the levels 「一些」, 「多數」 and 「全部」 (`nvda.po:1280-1294`). WorldVoice's own names come from `addon/locale/zh_TW/LC_MESSAGES/nvda.po:179-188` and `:374-375`.
  - **`## Unicode 偵測`**: add a bullet after the 「字元集假設的語言」 list (`readme.md:79-83`). Proposed text:

    「* 開頭的標點與符號：一段朗讀項目開頭的標點、符號與空白，會交給後面第一個文字的語言朗讀，不會先切到前一個語言的語音。例如主要語音為英文時，以引號或括號開頭的尼泊爾文（例如「(नेपाल)」）整段由尼泊爾語語音朗讀，「（中文）」整段由中文語音朗讀。數字語言為「跟隨前後文語言」時，開頭的一般數字（0～9）也一樣，例如主要語音為英文時，「2024年」整段由中文語音朗讀。項目中間的標點仍由前面文字的語言朗讀。「語言偵測時間點」為「在 NVDA 處理語音指令後」時，NVDA 已經先處理過符號：「標點及符號等級」為「多數」或「全部」時，符號已換成名稱（例如英文的「quote」），名稱依它本身的文字決定語言，不受這項規則影響；引號在「一些」以下已被 NVDA 移除。」
  - **Changelog**: add a `## 下一版更新` heading above `## WorldVoice 7.1 更新` (`readme.md:93`), with one entry. Proposed text:

    「* **開頭的標點跟隨後面的文字：** 一段朗讀項目開頭的標點、符號與空白，現在由後面文字的語言朗讀，不再先交給前一個語言（通常是主要語音）再切換語音。例如主要語音為英文時，以引號或括號開頭的尼泊爾文不再多一次語音切換與停頓。數字語言為「跟隨前後文語言」時，開頭的一般數字也一樣（例如「2024年」）。項目中間的標點不變。「語言偵測時間點」為「在 NVDA 處理語音指令前」時，所有符號都適用；為「在 NVDA 處理語音指令後」時，NVDA 已換成名稱或已移除的符號不受影響。」
- **`fix/script-digit-language` spec §2.1 G2** says that in `1२3`, `1` stays in the current language (`docs/superpowers/specs/2026-11-07-fix-script-digit-language-design.md`, the G2 bullet). Add this note after that bullet: "At the start of a text item the leading `1` now follows `२` (`fix/leading-punctuation-language` U2)." This is a docs commit on this branch. See Q4.

## 6. Settings, data and compatibility

No settings, config keys or stored data change. A user who wants a leading mark read by the main voice can mark the language in the document. There is no option to turn the rule off; see Q1 and Q2.

## 7. Test plan

### 7.1 Existing expectations that change (deliberately)

A full-suite run with the prototype (D1–D4) failed exactly these tests (3799 passed, 9 failed):

- `tests/test_language_detector.py:267` `test_unavailable_language_does_not_cover_its_script`:
  - case `C2` (`:225-232`): `[L("de_DE"), ", hallo"]` becomes `[("lang","de_DE"), ("lang","en"), ", hallo"]` (D5).
  - case `digits-ignored` (`:241-247`): `[L("de_DE"), "12 hallo"]` becomes `[("lang","de_DE"), ("lang","en"), "12 hallo"]` (U2).
- `tests/test_language_detector.py:468` `test_script_digits_go_to_their_scripts_language`:
  - `mixed` (`:444`): `["1२3"]` becomes `[("lang","ne"), "1२3"]`.
  - `common-then-script` (`:447`): `["1२"]` becomes `[("lang","ne"), "1२"]`.
  - Both are U2; see Q4. Their comments cite this spec.
- `tests/test_language_detector.py:860` `test_property_only_script_digits_start_a_detected_run`. Under "Follow surrounding text language" a detection-inserted command may now be directly followed by a Common digit, at the start of an item-start string, in the language of that string's deciding character. The property states that case. The phase 35 property for other number languages (`:875`) still passes unchanged (D2).
- `tests/test_worldvoice_speak.py:500-505` `test_follow_language_numbers`, row `next`:
  - Was `[(ZH, "中 12 ."), "|", (ZH, " "), (EN, "Next")]`; becomes `[(ZH, "中 12 ."), "|", (EN, " Next")]`.
  - The space after the punctuation pause starts a string and follows `Next` (Q2).
  - The "main" row of the same name (`:478-484`) is unchanged.
- `tests/test_worldvoice_speak.py:1040` `test_property_each_digit_is_read_by_the_number_language_voice`. Under `"default"`, a Common digit before the first letter or script digit of the text takes the voice of that character. The oracle gets that branch; the others are unchanged.

### 7.2 New unit tests (`tests/test_language_detector.py`)

Installed `en_US`, `ne_NP` (`NE`, `:426`) unless stated; base `en_US`; number language "default" unless stated.

- **The reported cases:**
  - `['"नेपाल"']` gives `[("lang","ne"), '"नेपाल"']`; `["(नेपाल)"]`, `["“नेपाल”"]` and `["- नेपाल"]` likewise.
  - `["link", '"नेपाल"']` gives `["link", ("lang","ne"), '"नेपाल"']`.
  - `['" २०८१']` gives `[("lang","ne"), '" २०८१']`.
- **Unchanged:**
  - `['abc "नेपाल"']` and `['नेपाल "नेपाल"']`.
  - `['"']`, and `["link", "("]`.
  - `[L("ne_NP"), '"नेपाल"']` gives the document command only.
  - `['"नेपाल"']` with no Devanagari voice (`en_US`, `zh_TW`).
  - A leading run before a script with no `SCRIPT_LANGUAGES` entry (`['"ᏣᎳᎩ']`, Cherokee) keeps the current language.
- **CJK** (installed `en_US`, `zh_TW`): `["「中文」"]`, `["（中文）"]` and `["(中文)"]` give `[("lang","zh_TW"), …]` with base `en_US`, and no command with base `zh_TW`.
- **Mirror** (installed `en_US`, `ne_NP`, base `ne_NP`): `['"Hello"']` gives `[("lang","en"), '"Hello"']`. The Latin assumed language decides, as for letters.
- **Base before assumed language:** installed `en_US`, `hi_IN`, `ne_NP`, Devanagari preference `ne`. `[L("hi_IN"), "abc", '"नेपाल"']` gives the second string to `hi_IN`, the base, not `ne`.
- **Document language without a covering voice:** `[L("en"), '"नेपाल"']` gives the quote to `ne` (D5).
- **Wrappers (D3):**
  - `["नेपाल (", WV("en_US"), "2024", WV("en_US"), ") नेपाल"]` under "main" leaves `) ` in `en_US`, before the `ne` command.
  - The same sequence under "default" (wrappers present) is also unchanged after a wrapper. The rule depends on the wrapper, not on the number language.
  - `["(", WV("en_US"), "2024", WV("en_US"), ") नेपाल"]` keeps `(` and `) ` in `en_US`.
- **Digits (U2, D2):**
  - Under "default": `["2024年"]` (installed `en_US`, `zh_TW`) gives `[("lang","zh_TW"), "2024年"]`, and `["3 apples"]` with base `zh_TW` gives `[("lang","en"), "3 apples"]`.
  - Under "main" with no wrapper: `["2024年"]` keeps `2024` in `en_US` (a decimal digit decides nothing).
- **Breaks and commands:**
  - `['"', BreakCommand(), 'नेपाल']` keeps `'"'` in `en_US` (D4).
  - `["abc", BreakCommand(), ' "नेपाल"']` gives ` "` to `ne` (Q2).
  - `["abc", IndexCommand(1), '"नेपाल"']` gives the quote to `ne`.
- **Spelling is unchanged (D7):** `process_for_spelling('"नेपाल', "en_US")` gives `[('"', "en_US"), ("नेपाल", "ne")]`.
- The settings and the number language are still read once per sequence (extend `test_detection_reads_the_number_language_once_per_sequence`, `:511-520`, with a leading mark).

### 7.3 Property tests (Hypothesis, `tests/test_language_detector.py`)

- **Strategies.** `SCRIPT_SAMPLES` (`:686-692`) gains `'"'`, `"("`, `"「"`, `"- "`. The item strategy (`ITEMS`, `:713-716`) also draws `WVLangChangeCommand`s (number wrappers) and `BreakCommand`s.
- **The oracle.** A test-local function applies today's per-character rule (the loop of `detector.py:74-99`, written out in the test, calling the detector's unchanged `_language_for_character`).
- **New property, "never an extra switch" (D6, §4.2).** For every scenario, items and number language (`"default"`, `"main"`, `"en"`, `"zh_TW"`), compare the detector with the oracle:
  - (a) The languages of the detection-inserted commands are equal, as a list.
  - (b) The joined text is equal.
  - (c) Every character outside the leading run of an item-start string (D3) has the oracle's language.
  - (d) Every leading-run character has the language the oracle gives the deciding character. When there is no deciding character, or under other number languages it is a digit, it has the oracle's own language.
- **The existing properties** keep passing with the new alphabets: `test_property_detection_only_inserts_language_changes`, `test_property_letters_go_to_installed_languages`, `test_property_inserted_commands_prefer_a_covering_base` and `test_property_digits_never_start_a_detected_run_under_other_number_languages`.

### 7.4 End-to-end tests (`tests/test_worldvoice_speak.py`)

- **Timing "before" through the speak harness with `nvda=` NVDA's processing.** `heard_through_nvda` or a level-parameterized variant of `nvda_processes_each_item`, adding the `ne` voice:
  - `"नेपाल"`, `(नेपाल)` and `["link", '"नेपाल"']` at "some" are heard with no IBM turn except `link`.
  - `"नेपाल"` at "most" is heard as `[(NE, "quote नेपाल quote  ")]`.
  - `「中文」` with main English is all Chinese.
- **Timing "after", pinned through NVDA's processing at "some"** (`heard_through_nvda`):
  - `"नेपाल"` stays `[(NE, …)]` (NVDA dropped the quote; unchanged).
  - `(नेपाल)` becomes `[(NE, "(नेपाल)  ")]` (F4, Q1).
  - At "most", `(नेपाल)` is unchanged from `master`: `[(EN, "left paren("), (NE, "नेपाल "), (EN, "right paren)  ")]`.
- **Mirror.** The harness `main` gains `"ne"` (the main voice `NE`). `"Hello"` in both timings is heard by English only.
- **"Follow main language".** `(2024) नेपाल` and `नेपाल (2024) नेपाल`, both timings, give exactly what `master` gives.
- **Property: "at most as many voice changes".** Random texts from `SPOKEN_PIECES` (`:1020`) plus `'"'`, `"("`, `"「"`, joined into one or two items; number language `"default"` or `"main"`; both timings.
  - Compare the harness against itself with the detector's `add_detected_language_commands` swapped for the oracle of §7.3.
  - Both hear the same text, and the new one has no more voice changes in `heard()`.

### 7.5 Mutation testing

`detector.py` is a core decision module, already in `[tool.mutmut] source_paths` (`pyproject.toml:42-73`). Run mutmut scoped to it on a scratch copy, with at most 3 children and the memory guard. Record surviving mutants and the reasons in the ledger.

### 7.6 Windows / NVDA manual items (not verified on Linux)

- **M1.** IBM TTS as the English main voice, eSpeak Nepali, timing "在 NVDA 處理語音指令前", symbol level "一些". Read lines starting with `"नेपाल`, `(नेपाल`, `“नेपाल` and `- नेपाल`. There is no IBM switch or pause before the Nepali voice.
- **M2.** Same setup, timing "在 NVDA 處理語音指令後". `(नेपाल)` has no IBM switch. `"नेपाल"` is as before (no switch).
- **M3.** Symbol level "多數", both timings. "before": eSpeak reads the English name "quote". "after": IBM reads it, as on 7.1.
- **M4.** A browse-mode link followed by a quoted Nepali text, and say all over Nepali paragraphs that start with quotes: the quotes are read by eSpeak.
- **M5.** `abc "नेपाल"` mid-line: unchanged.
- **M6.** English main voice with a Chinese voice: `「中文」` is read entirely by the Chinese voice.

## 8. Open questions

- **Q1. Timing (premise of U3; needs the user).** F4 shows that with timing "after" the rule also moves marks NVDA keeps as characters at its default level: `(`, `)`, `-`, CJK brackets, and ASCII digits under U2. U3 assumed "after" would be unchanged.
  - (a) **Recommended:** apply the rule in both timings, as written here. The detector is shared and needs no new input. "after" users also lose the reported switch for `(` and `-`. The readme (§5) says what each timing covers.
  - (b) Only "before". The detector needs the timing as a new input, and "after" (the default) keeps the IBM switch for `(नेपाल)`.
- **Q2. A string after a pause break inside an NVDA item (D3).** The punctuation pause (configured marks), number edge and gap pauses (group size above 0), segment cuts and the CJK space pause split one NVDA item into several strings (F7). Under D3, each string after such a break starts an item, so its leading Common characters follow the text after them.
  - Example: with `,` configured, `abc, "नेपाल"` gives ` "` to Nepali. The switch count is unchanged (D6).
  - (a) **Recommended:** keep this, as written here. It changes only the leading characters of a piece after a pause, so the switch lands on the pause.
  - (b) Treat a string after a `PunctuationBreakCommand`, `NumberBreakCommand` (and subclasses) or `SegmentBreakCommand` as a continuation. This is imperfect, and it ties the detector to the pipeline's break classes:
    - the CJK space pause uses a plain `BreakCommand` (`unspaced.py:65`), like the item pause;
    - a punctuation pause and a number item edge break also sit between two NVDA items (`punctuation.py:175-178`, `numberStages.py:459-460`), so (b) would miss the reported case after an item that ends with a configured mark when the item pause is 0.
- **Q3. A leading mark that is itself a configured punctuation pause character.** With `"` or `(` in 「標點停頓字元」 (empty by default), the mark is cut from its text by a pause (F7). It is alone in its string and stays in the previous language: the reported switch remains. Does the reporter configure these characters?
  - (a) **Recommended:** accept this as a limitation. The lookahead never crosses a command (D4), and the user asked for a pause there.
  - (b) Let the lookahead cross a `PunctuationBreakCommand` when the string before it holds only Common characters.
- **Q4. `1२3` at the start of an item.** Under "Follow surrounding text language" the leading `1` now goes to Nepali with `२3`. The 7.1 spec's G2 ("mixed-script numbers stay per character") decided `1` stays English. U2 covers this as a leading ASCII digit; mid-item (`abc 1२3`) is unchanged. Confirm that U2 supersedes G2 at item start (§5 adds the note).
