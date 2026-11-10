# Punctuation at the start of a text item follows the text after it

- Branch: `fix/leading-punctuation-language` (normal flow, DEVELOPMENT_WORKFLOW.md §3), from `master` `6ea5665`.
- Report (second email from the reporter of `fix/script-digit-language`, after WorldVoice 7.1): English is read by IBM TTS (the main voice) and Nepali by eSpeak. When a line starts with punctuation such as a quote or a left parenthesis, WorldVoice gives that punctuation to IBM TTS although the text after it is Nepali. Every such line gets an extra synthesizer switch and pause. Punctuation in the middle of a line is read by the voice of the text around it, which he likes.
- Decisions:
  - U1 and U2 (§2.1) are `Decided by the user (2026-11-09)`.
  - U3 is also from 2026-11-09 and is replaced by U4.
  - U4–U9 are `Decided by the user (2026-11-10)`.
  - D1–D13 (§2.2) are `Decided by orchestrator with the recommended default; user may override before merge`.
  - No open question remains (§8).
- Baseline: `python3 -m pytest -q tests` 3808 passed, 0 skipped; `prek run --all-files` all Passed; protected paths unchanged.
- Prototype: F2, F4, F6, F10–F13, §3 and §7.1 rest on throwaway changes to four files, implementing the H rule of §2.1: `languageDetection/detector.py`, `pipeline/breaks.py`, `pipeline/punctuation.py` and `pipeline/unspaced.py`. I ran them in this worktree in three ways:
  - against the speak harness, with NVDA's real `characterProcessing` from `ref/nvda`;
  - against the full suite;
  - against two scratch Hypothesis properties (the two invariants of §4.3, 400 examples each).

  Then I restored the files with `git checkout`. Nothing of the prototype is committed; the plan implements the rule anew.

## 0. Findings

### F1. Characters with no script of their own stay in the run in progress

- **The per-character rule.** `LanguageDetector._script_language` returns the current language for a character whose script is `None`, `"Common"` or `"Inherited"` (`addon/synthDrivers/WorldVoice/languageDetection/detector.py:48-54`, the check at `:52-53`). `_language_for_character` also returns the current language for any decimal digit when the number language is not "Follow surrounding text language" (`detector.py:56-64`, `:62-63`).
- **How the loop applies it.** `add_detected_language_commands` calls it once per character, with the run's language (`tmp_lang`) as the current language and the last language command's language (`cur_lang`) as the base (`detector.py:66-99`, call at `:82-88`).
  - `tmp_lang` changes only when a character's language has another primary language (`:89-94`).
  - It is carried from one string to the next (`:73`, `:94`), and across utterance ends.
  - Only a `LangChangeCommand` or `WVLangChangeCommand` resets it (`:75-78`).
- **Consequence.** Punctuation, symbols, spaces and Common digits at the start of a text item take the language the previous text ended in. If no text came before, they take the document's language or the synth's language (`:71-73`).

### F2. Reproduction on `master`

Setup for these runs:
- the speak harness (`tests/test_worldvoice_speak.py:394-424`), with an `ne` voice added (`NE`, `:345`);
- number language `"default"`;
- detection timing "before";
- NVDA's processing simulated at symbol level "some" with NVDA's real `characterProcessing` (F4).

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

At symbol level "most", the blank becomes NVDA's English name: IBM says "quote" or "left paren" before the switch.

### F3. Where detection runs, and in which language NVDA names symbols

- **Default timing.** Detection timing defaults to "after" (`addon/synthDrivers/WorldVoice/languageDetection/settings.py:21`).
- **"before".** Detection is a `filter_speechSequence` handler. It is registered and then placed after WorldVoice's pipeline stages (`addon/synthDrivers/WorldVoice/__init__.py:505-514`, `pipeline/registry.py:175-178`).
  - It receives the whole sequence of one `speech.speak()` call (`ref/nvda/source/speech/speech.py:1137`), which may hold several utterances.
  - NVDA's `speak()` then runs `processText` on each string (`speech.py:1214-1232`).
- **"after".** Detection runs in `WorldVoice.speak` (`__init__.py:336-337`), after NVDA's `processText`.
  - It receives one utterance that the speech manager built (`ref/nvda/source/speech/manager.py:293-322`, `:448-462`).
  - That utterance may start with replayed parameter commands (`manager.py:302-310`, `:454-456`).
- **Stage order.** In both timings the pipeline stages (`pipeline/registry.py:149-161`) run before detection.
- **Symbol-name language.** `processText` names symbols in the language of the last NVDA `LangChangeCommand`, or else `getCurrentLanguage()` (`speech.py:1177`, `:1214`, `:1221`).
  - That is the synth's language when "trust voice's language" is on, which is its default (`speech.py:313-325`, `ref/nvda/source/config/configSpec.py:39`).
  - WorldVoice's commands are `WVLangChangeCommand`, which never derives from `LangChangeCommand` (`addon/synthDrivers/WorldVoice/speechCommands.py:4-17`).
  - So with timing "before", NVDA names the symbols of every string in the synth's language, English here, including strings WorldVoice gave to Nepali.

### F4. What NVDA leaves of a leading mark

Checked with NVDA's real `characterProcessing` and the symbol tables in `ref/nvda` (loader `tests/pipeline_harness.py:424-448`), locale `en`. How NVDA handles a symbol:
- `processText` substitutes symbols, then strips the text (`speech.py:192-214`, strip at `:214`).
- A symbol below the current level is dropped (replaced by a space), unless its `preserve` keeps it (`ref/nvda/source/characterProcessing.py:629-637`).
- The default level is "some" (`configSpec.py:38`; `SymbolLevel.SOME = 100`, `characterProcessing.py:160`).

| Mark (English table line) | Levels "none" and "some" | Levels "most" and "all" |
| --- | --- | --- |
| `"`, `“`, `”` (`locale/en/symbols.dic:47`, `:105-106`, level most, no preserve) | dropped; at the start of a string, stripped | " quote ", " left quote " (Latin letters) |
| `(`, `)`, `-` (`symbols.dic:61-62`, `:67`, preserve always) | kept as the character | " left paren(" (name and character) |
| `「`, `（` and other CJK brackets (no entry in the English table) | kept | kept |
| ASCII digits (`2024年`) | kept | kept |

So with timing "after", the detector still sees the marks NVDA keeps as characters, and the rule moves them. A name NVDA has already inserted is Latin letters, and it goes by its own script. Prototype in "after" with NVDA's processing at "some":
- `(नेपाल)`: `master` gives IBM `(` and eSpeak `नेपाल)`; the prototype gives all eSpeak.
- `"नेपाल"`: all eSpeak on both, because NVDA had already dropped the quote.

### F5. Nepali has no symbol table

- `ref/nvda/source/locale/ne/` holds only `LC_MESSAGES` and `characterDescriptions.dic`.
- `_getSpeechSymbolsForLocale` raises `LookupError` when it finds no built-in table (`characterProcessing.py:413-427`). `processSpeechSymbols` and `processSpeechSymbol` then fall back to `"en"` (`:719-723`, `:735-739`).
- Every locale also uses the English built-in table as its base (`:458-462`).

For speech this changes nothing, because NVDA names symbols in the synth's language anyway (F3). It matters for spelling (D7).

### F6. Number-language wrappers split a text item into several strings

- **Where wrappers come from.** Under "main" and a locale, `detect_with_number_language` wraps every number in `WVLangChangeCommand`s before detection (`pipeline/numberStages.py:194-226`, condition at `:208`, wrappers at `:185-188`). Under a locale, `inject_numbers` also wraps them (`:287`, `:452-456`).
- **How the item comes back together.** After detection, the wrappers that keep the voice are dropped and the pieces are glued back (`:211-225`). During detection, `नेपाल (2024) नेपाल` is `"नेपाल ("`, wrapper, `"2024"`, wrapper, `") नेपाल"`.
- **What goes wrong if a string after a wrapper starts an item.** A first prototype made the string after a closing wrapper start an item. It moved the `)` to Nepali under "main" and failed 13 existing "main"/locale tests. D3 avoids that.

### F7. Pipeline stages split one NVDA item into several strings

All the stages run before detection in both timings (F3), in the order of `STAGES` (`pipeline/registry.py:149-161`). Some split an item without any break between the pieces; others put a break of one of their own classes there.

- **Punctuation pause** (`pipeline/punctuation.py`). Enabled by default (`pipeline/settings.py:252-254`); the character list is empty by default (`:286-288`).
  - `emit` yields the text part and the mark part of an item as separate strings (`punctuation.py:164-174`).
  - It puts a `PunctuationBreakCommand` after a mark that text follows (an internal point, `:153-160`, `:173-174`).
  - It also puts one after an item whose last character is a configured mark, before the next text (`:175-178`).
  - Checked: `abc, (नेपाल)` with `,` configured becomes `'abc', ',', PunctuationBreakCommand, ' (नेपाल)'`.
- **Number pause, between two numbers** (`number_wait_factor`, on by default at 10 ms). It strips every string and drops blank ones (`numberStages.py:74-96`). It cuts spaced numbers out of their item (`numbers.py:36-60`) and puts a `NumberBreakCommand` only between the two numbers (`numberStages.py:106-150`).
  - Checked: `abc 12 34 (नेपाल)` becomes `'abc ', '12', NumberBreakCommand, '34', ' (नेपाल)'`.
  - With the pause at 0 it stays one string.
- **Number pauses with a group size above 0** (`inject_numbers`):
  - a `NumberEdgeBreakCommand` between a number and text in the same item (`numberStages.py:298`, `:449-451`, `:457-458`);
  - a `NumberItemEdgeBreakCommand` at an item's start or end (`:437-438`, `:459-460`);
  - a `NumberBreakCommand` between pieces (`:245`) and between spaced numbers (`:298-300`, `:441-442`).
- **Space pause between CJK and Southeast Asian characters.** A plain `BreakCommand` (`pipeline/unspaced.py:65`).
  - It replaces a whitespace run inside a string, with an unspaced-script character on both sides (`_pauses_between`, `unspaced.py:38-50`).
  - Such characters include Common ones whose Script_Extensions name an unspaced script, such as ー and ㊀; `「` and `。` do not count (`unspaced.py:29-37`).
- **Segment pause.** Off by default (`pipeline/settings.py:308-321`). It cuts after whitespace, at a boundary between two strings, or at the length limit (`text/chunker.py:56-69`).
  - Checked: `segment_cuts(['link', '"नेपाल"'], 5)` gives `[(0, 4), (1, 5)]`, a cut at the boundary between the two strings.
  - This needs the two strings to be in one segment run, which restarts at every break (`segments.py:38-45`). So it happens only when no item pause separates them.
- **Item pause.** A plain `BreakCommand` between every two adjacent text items (`pipeline/items.py:36-51`, `_both_text` at `pipeline/sequence.py:16-17`). On by default: 10 × 1 ms (`settings.py:223-230`).
- **NVDA's say all.** It splits a string after the last sentence end and speaks the rest with the next line (`ref/nvda/source/speech/speechWithoutPauses.py:32-35`, `:150-170`).

### F8. Spelling

- `patchedSpeakSpelling` uses `process_for_spelling` when detection is on and "trust voice's language" is set (`__init__.py:360-365`).
- Whitespace keeps the spelling locale (`detector.py:115-116`); digits under "main" or a locale use the number-language rule (`:117-118`); every other character uses `_script_language` with the current language (`:119-126`).
- So a leading mark stays in the spelling locale.

### F9. Test harness

- `speak_through_stages` runs the stages, then detection with timing "before", then the optional `nvda` function, then `speak` (`tests/test_worldvoice_speak.py:394-424`). Without `nvda` it does not simulate NVDA's `processText`.
- `heard_through_nvda` (`:915-918`) does the simulation, through `nvda_processes_each_item` (`:654-676`) at level "some".
- `heard()` cannot take an `EndUtteranceCommand` (`:376-391`): it reads every non-text chunk as an index. So utterance cases are tested at the detector level, or the harness learns that command.
- The harness voices are `{"en": "A:en", "zh": "B:zh"}` (`:21`); tests add `NE` (`:345`). `main` supports `"en"` and `"zh"` only (`:409-412`).

### F10. Strings next to each other are not always separate NVDA items

F7 shows that the punctuation stage and the number pause leave adjacent strings inside one NVDA item, with no break between them. So "the string right after another string starts an item" is false.

The first version of this spec used that rule (its D3). Under it, the mid-line ` (` of `abc 12 34 (नेपाल)` would follow the Nepali word with the default number pause, and stay English with that pause at 0. Under it, the user's `abc, "नेपाल"` would also differ with and without `,` configured.

H (U5) treats adjacent strings as one item.

### F11. Where an item boundary can stand, and what merging does to it

`_merge_edge_breaks` cuts every run of breaks that contains a number edge break down to one break: the longest, or on a tie the first that is not an edge break (`pipeline/breaks.py:58-83`). It runs in `inject_numbers` (`numberStages.py:304`), in the item stage (`items.py:33`) and in the punctuation stage (`punctuation.py:125`). It keeps the objects it does not drop and creates none. What survives at a real item boundary depends on the settings:

- **The item pause gives way to a longer number item-edge break.** Checked: `["Total 12", "34 (नेपाल)"]` with number pause 20 and item pause 10 keeps only the `NumberItemEdgeBreakCommand` between the items.
- **The end-of-item punctuation pause gives way too, inside an item.** When the punctuation stage meets a non-item `NumberEdgeBreakCommand` after a piece that ends with a configured mark, it still emits its end-of-item pause. Checked: `नेपाल, 12 abc` with group size 3, number pause 10 and punctuation pause 20 gives `'नेपाल', ',', PunctuationBreakCommand, '12', …`.
  - The pause from the end-of-item path then stands inside the NVDA item, in place of the edge break.
  - U5 makes this case internal.
- **A segment cut can fall between two adjacent items** when the item pause is 0 (F7).

### F12. Classes, exact-type checks and equality

| Place | How it reads a break | Effect of the new subclasses |
| --- | --- | --- |
| `pipeline/items.py:42`, `:45` | `_is_item_edge_break`, `_both_text` | none (no edge marker, not text) |
| `punctuation.py:190`, `:195`, `:200-202` | `isinstance(…, BreakCommand)`, `_is_edge_break`, `isinstance(…, NumberBreakCommand)` | none: a pending unspaced break still suppresses the end-of-item pause, as the plain one did |
| `segments.py:40` | `isinstance(item, BreakCommand)` restarts the count | none |
| `breaks.py:77-83` (`_merged_run`) | `isinstance(…, BreakCommand)`, `_is_edge_break` | none; it never creates a break (F11) |
| `breaks.py:86-103` (`_plain_breaks`, `_plain_break`) | creates a plain `BreakCommand(command.time)`, keeping only the edge marker | applies only to synths without roles (`registry.py:118`). WorldVoice detection never runs there, so these synths keep getting plain breaks, as today. (The orchestrator's note placed `breaks.py:99` in `_merge_edge_breaks`; it is in `_plain_break`.) |
| `pipeline/sayAll.py:29` | creates a plain `BreakCommand` | unchanged, stays a boundary |
| `bridge/commands.py:48` | `isinstance(command, BreakCommand)` turns it into a `Pause` | none |
| NVDA's speech manager | appends any non-parameter command (`manager.py:364-372`) | none |
| NVDA's `BreakCommand.__eq__` | compares the exact type, then time (`ref/nvda/source/speech/commands.py:213-218`) | test expectations that compare a stage's output with `BreakCommand(n)` or `PunctuationBreakCommand(n)` must name the new class (§7.1) |

No product code compares breaks by exact type or by `==`. The prototype's full suite failed only test expectations (§7.1).

### F13. The language in force at an utterance's start differs between timings today

- **"before".** The detector carries `tmp_lang` and `cur_lang` across an `EndUtteranceCommand` (F1). The speech manager replays the last non-default `WVLangChangeCommand` at the start of the next utterance split from the same sequence (`speechCommands.py:19-22`, `manager.py:95-105`, `:302-310`). So the carried language is what the voice really uses.
- **"after".** Each utterance reaches the detector on its own and starts at the synth's language (`detector.py:71-73`), apart from replayed commands.

This is pre-existing. It matters only where text has no script of its own and nothing in the utterance decides for it (D11).

## 1. Problem

Characters with no script of their own at the start of a text item take the language of the run before them (F1). At the start of an utterance, or after an item in the main language, that is the main language. So a Nepali line that starts with a quote, a parenthesis or a dash switches to the main voice for that one mark and then to the Nepali voice (F2). The same happens:
- with CJK brackets before Chinese text when the main voice is English;
- in mirror form with Latin text when the main voice is Nepali.

Every such line costs one extra synthesizer switch and its pause.

## 2. Goals and non-goals

### 2.1 Decisions by the user

- **U1. Approach A.** `Decided by the user (2026-11-09)`. Within one text item, the Common and Inherited characters before the item's first character that has a script with candidate languages go to the language that first script character gets. Leading punctuation, symbols, spaces and digits follow the text after them. Common characters in the middle of an item keep following the run before them, unchanged.
  - What counts as an item is set by U5.
  - An item with no such character is handled by U7.
  - Rejected: approach B, direction by punctuation type. Straight quotes are ambiguous, and mid-line punctuation is not a complaint.
- **U2. Accepted side effect.** `Decided by the user (2026-11-09)`.
  - Under number language "Follow surrounding text language", leading ASCII digits (Common) follow the text after them too. With main voice English, `2024年` goes to Chinese. With main voice Chinese, `1. Introduction` and `3 apples` go to English.
  - Under "Follow main language" and a locale, numbers are wrapped before detection and stay exactly as today (§4.4).
- **U3.** `Decided by the user (2026-11-09)`; **replaced by U4.** It said: "only with timing 'before'; 'after' stays unchanged".
- **U4. Both timings.** `Decided by the user (2026-11-10)`; replaces U3.
  - The rule applies in both detection timings, and the detector gets no timing input.
  - In "after" it moves what NVDA leaves as characters: `(`, `)`, `-`, CJK brackets, and digits under U2.
  - It cannot move what NVDA has already turned into names at "most" and "all" (F4).
- **U5. Option H: WorldVoice's own pauses inside an item are transparent.** `Decided by the user (2026-11-10)`; replaces the first spec's D3 and D4 and its Q2.
  - **Adjacent strings belong to one item.** The punctuation stage and the number pause split items without a break (F10).
  - **Transparent: these breaks do not end an item.**
    - the internal punctuation pause (a new subclass, U6, D12);
    - `SegmentBreakCommand`;
    - `NumberBreakCommand` and `NumberEdgeBreakCommand`, but not `NumberItemEdgeBreakCommand` (D8);
    - the CJK space pause (a new subclass, U6);
    - the number wrappers (`WVLangChangeCommand`, D3).
  - **Item boundaries.**
    - a plain `BreakCommand`: the item pause, the say-all pause, NVDA's own;
    - `NumberItemEdgeBreakCommand`;
    - the end-of-item punctuation pause (`PunctuationBreakCommand` itself), except when it replaces an in-item number edge break (F11), where it is internal;
    - any other command: `IndexCommand`, NVDA `LangChangeCommand`, callbacks, and so on;
    - and the utterance ends (U8).
  - **Guarantee.** With the item pause above 0 (the default, 10 ms), the voice of every spoken character is the same whether the punctuation pause, the number pauses, the segment pause and the CJK space pause are on or off.
    - The exception is characters a stage removes: marks removed by "remove configured punctuation at pause points", and whitespace a stage strips or turns into a pause.
  - **Limitation, accepted.** With the item pause at 0, the boundary between two adjacent items is invisible after the stages. A mark at the start of an item right after another item may then still follow the previous item's voice.
    - Checked: `["link", '"नेपाल"']` gives `link"` to English.
    - With item pause 0 the pause settings can also make a difference at item boundaries. Checked: `["abc,", "12नेपाल"]` gives `12` to English without a `,` pause and to Nepali with one.
  - Rejected:
    - (A) Change three stages so adjacent strings can be item boundaries.
    - Making `PunctuationBreakCommand` always transparent: with item pause 0 the reported bug would come back for `["Hello.", PB, '"नेपाल"']`.
- **U6. The CJK space pause is internal.** `Decided by the user (2026-11-10)`.
  - `pipeline/unspaced.py:65` emits a new subclass of `BreakCommand`, defined in `pipeline/breaks.py`, instead of a plain one.
  - The detector treats it as transparent, and the guarantee of U5 covers the space wait factor between CJK and Southeast Asian characters.
  - Effect on languages: text after this pause starts with an unspaced-script character (`_pauses_between`, F7), which has a script of its own, except a Common one such as ー or ㊀. So it practically never had a leading run anyway.
- **U7. Look ahead only when nothing came before.** `Decided by the user (2026-11-10)`; replaces the first spec's Q3. It covers an item with no deciding character (D1), that is, only Common and Inherited characters.
  - **Something came before.** If a deciding character, or a wrapped number (D9), already appeared earlier in the same utterance, the item keeps today's behaviour: the preceding language, no lookahead.
    - Common-only text earlier does not count.
    - A document `LangChangeCommand` does not count as text, but takes part through the G1 chain and D10.
  - **Nothing came before.** Otherwise the item looks ahead across commands and strings (breaks, index commands, other items) to the first deciding character in the utterance, and takes the language that character gets (D10). With none, it stays in the current language.
  - **A wrapped number never decides** (D9).
  - **Examples that hold** (checked with the prototype, item pause on):
    - `"Price"`, `"100"`, `"नेपाल"` (separate items): `100` stays English.
    - At an utterance's start, `"(" [punctuation pause] "नेपाल)"` with `(` configured: the mark goes to Nepali.
    - At an utterance's start, `"-" [item pause] "नेपाल"`: the mark goes to Nepali.
    - At an utterance's start, `"(" [pause] "1" [pause] "नेपाल"`: both go to Nepali under "Follow surrounding text language". Under "main" both stay English, as today.
  - **What remains of the old Q3 limitation.** A mark cut off by a configured punctuation pause stays in the preceding voice only in the middle of an utterance. There, following the preceding voice is the intended behaviour. At the start of an utterance it follows the text after it.
- **U8. Utterance scope.** `Decided by the user (2026-11-10)`.
  - "Earlier in the utterance" (U7) and the lookahead (U7) are bounded by the utterance. They reset at `EndUtteranceCommand` and `ConfigProfileTriggerCommand`, the definition `_ends_utterance` already uses (`pipeline/sequence.py:20-27`, from `fix/number-edge-pause-items`).
  - No lookahead crosses an utterance end. With that reset, the rule has the same scope in both timings, although "before" sees a whole `speak()` sequence and "after" one utterance (F3).
  - The user's reason: in say all, a new line starting with `(` must not follow the previous line's language.
- **U9. `1२3` at the start of an item.** `Decided by the user (2026-11-10)`. Under "Follow surrounding text language" it goes entirely to Nepali. This supersedes the 7.1 spec's G2 at item start only. The note on that spec stays (§5).

### 2.2 Orchestrator defaults (Decided by orchestrator with the recommended default; user may override before merge)

- **D1. The deciding character.** It is a character that either:
  - has a script of its own: `get_script` is not `None`, `"Common"` or `"Inherited"`, the test `_script_language` already uses (`detector.py:52`); or
  - is a decimal digit while the number language is not "Follow surrounding text language".

  Details:
  - Under "Follow surrounding text language", a script digit decides (the 7.1 rule, `detector.py:56-64`), and a Common digit does not (U2).
  - A character of a script with no entry in `SCRIPT_LANGUAGES` (for example Cherokee) decides too. It gets the current language (`detector.py:31-33`), so nothing changes.
- **D2. The language of a leading run** is what the deciding character gets.
  - That is `_language_for_character(character, tmp_lang, cur_lang, settings, digits_by_script)` with today's inputs at that character. Leading Common characters never change `tmp_lang` (F1).
  - This keeps the G1 chain of `fix/script-digit-language`. If the current language covers the script, or no installed language does, nothing changes.
  - **Under "main" and a locale, a decimal digit ends the search and decides nothing.** The leading characters keep the current language. This keeps the phase 35 §11.4 item 4 property in the detector itself, even for unwrapped digits.
- **D3. Number wrappers continue the item.** A `WVLangChangeCommand` in the detector's input comes only from the number wrappers (F6). It is transparent for items, and it still resets `cur_lang` and `tmp_lang` as today (`detector.py:75-78`). The wrapped number is opaque: its first digit stops every search (D2, D9). So strings inside a wrapper, and the text around it, keep today's languages.
- **D4. The search for an item's deciding character** runs over the item's strings in order, across transparent breaks and wrappers (U5). It stops at the item's end, at a deciding character, or at a stop (D2).
- **D5. Document language commands keep today's meaning.** An NVDA `LangChangeCommand` ends an item and resets `cur_lang` and `tmp_lang`. Examples:
  - `[L("ne_NP"), '"नेपाल"']` changes nothing.
  - `[L("en"), '"नेपाल"']` gives the quote to Nepali.
  - `[L("de_DE"), ", hallo"]` (German, no voice) gives `, ` to English with `hallo`.
- **D6. Never an extra switch.** Within an item, the rule moves the point where the language changes to the item's start and never adds a change. The same holds for the utterance-start lookahead of U7: it only lets a run of Common characters join the voice of the text after it.
  - Invariant 1 (§4.3): heard voice changes are never more than today's.
  - Checked with a scratch property against `master`'s rule, both timings, item pause 0 and 10.
- **D7. Spelling is unchanged.** `process_for_spelling` keeps its rule (F8), for three reasons:
  - Spelling speaks one character at a time, and in the spelling locale a leading mark gets the name NVDA would say without WorldVoice. A Nepali voice would read NVDA's English name (F5).
  - Character navigation spells one character, which has nothing after it.
  - Spelling already treats whitespace differently from reading (`detector.py:115-116`).
- **D8. `NumberBreakCommand` is transparent.** It stands between number pieces, between spaced numbers in one item, and, from `number_wait_factor`, between two whole-number strings (F7).
  - The number pause splits an item only when the pause is on (`numberStages.py:123-126`), so U5's guarantee needs the break to be transparent.
  - Between two whole-number items, both sides are digits: a Common digit never decides, and a wrapped one stops. So item start or continuation gives the same languages there (U7 decides).
  - With the item pause above 0, two items are separated by the item break anyway (`_insert_number_breaks` keeps numbers apart at any other command, `numberStages.py:133-150`).
- **D9. Wrapped numbers and the lookahead.** Under "main" and a locale:
  - **A wrapped number stops the utterance-start lookahead** of U7 without deciding: its first digit is a stop (D2), and the lookahead does not skip past it. Skipping it would give `(` to Nepali, the number to English, then Nepali again: an extra switch.
  - **A wrapped number counts as "came before".** So "main" and locale numbers, and the text after them, keep today's behaviour.
- **D10. The lookahead language across a document `LangChangeCommand`.** When the lookahead of U7 crosses an NVDA `LangChangeCommand`, the leading characters take the language the deciding character actually gets. The exception: if the language in force at the leading characters already covers that character's script, they keep it.
  - Within one item (no document command inside, D5) this is the same as D2.
  - Checked: `['"', L("hi"), "नेपाल"]` with no Hindi voice is heard all Nepali.
- **D11. The utterance reset does not reset the run language.** It bounds only the came-before check and the lookahead (U8). `tmp_lang` and `cur_lang` keep today's carry-over, because in "before" the speech manager replays the last switch at the next utterance (F13). A reset in the detector alone would no longer match what the voice uses. The start-of-utterance difference between the timings (F13) stays as today, and it matters only for text that nothing in the utterance decides.
- **D12. Names of the new classes.** Both are defined in `pipeline/breaks.py`:
  - `InternalPunctuationBreakCommand(PunctuationBreakCommand)`, for the internal points, and for the end-of-item path when the pending breaks hold a non-item `NumberEdgeBreakCommand`;
  - `UnspacedSpaceBreakCommand(BreakCommand)`, for the CJK space pause.

  `isinstance(…, PunctuationBreakCommand)` and `isinstance(…, BreakCommand)` stay true, so every existing check keeps working (F12).
- **D13. The detector does not import the pipeline.** `languageDetection/` imports no `pipeline/` module today. The transparency check is a function in `pipeline/breaks.py`, next to the classes. The driver hands it to `LanguageDetector`, as it hands the number-language provider (`__init__.py:287-292`). The default, used when none is passed, treats no break as transparent. The speak harness passes the driver's function (`tests/test_worldvoice_speak.py:209-215`).

### 2.3 Non-goals

- Opening punctuation in the middle of an item (`abc "नेपाल"`): unchanged (U1).
- A mark in an item of its own, or cut off by a configured punctuation pause, in the middle of an utterance (`["abc", "(", "नेपाल)"]`): it follows the preceding voice (U7).
- Symbol names NVDA has already inserted with timing "after" (F4).
- The language NVDA names symbols in with timing "before" (F3). A leading `"` at level "most" becomes "quote", now read by the Nepali voice, as trailing and mid-line quotes already are.
- Adjacent items with the item pause at 0 (U5 limitation).
- The start-of-utterance language difference between timings (F13, D11).
- Spelling (D7).

## 3. What an NVDA user hears

Main voice English (IBM), eSpeak Nepali installed, number language "Follow surrounding text language", NVDA symbol level "some", item pause on (default) unless stated. "Blank" means a voice given only whitespace, which still costs a switch. Rows marked † were checked with the prototype.

Timing "before":

| Input | Before | After |
| --- | --- | --- |
| `"नेपाल"` † | IBM blank, then eSpeak | eSpeak only |
| `"नेपाल"`, level "most" † | IBM "quote", eSpeak "नेपाल quote" | eSpeak "quote नेपाल quote" |
| `(नेपाल)`, `“नेपाल”`, `- नेपाल` † | IBM `(` or blank or `-`, eSpeak | eSpeak only |
| `link`, then `"नेपाल"` (two items) † | IBM `link` and a blank, eSpeak | IBM `link`, eSpeak |
| the same, item pause 0 † | IBM `link"`, eSpeak | unchanged (U5 limitation) |
| `" २०८१` | IBM blank, eSpeak digits | eSpeak only |
| `abc "नेपाल"` † | IBM `abc "`, eSpeak | unchanged (mid-line) |
| `abc, "नेपाल"`, punctuation pause off / on with `,` † | IBM `abc, "`, eSpeak | unchanged in both (U5) |
| `abc 12 34 (नेपाल)`, number pause 0 / 10 † | IBM `abc 12 34 (`, eSpeak | unchanged in both (U5) |
| `(नेपाल)` at utterance start, `(` a punctuation pause character † | IBM `(`, pause, eSpeak | eSpeak `(`, pause, eSpeak (U7) |
| `-`, then `नेपाल` (two items) at utterance start † | IBM `-`, eSpeak | eSpeak only (U7) |
| `Price`, `100`, `नेपाल` (three items) † | IBM `Price`, IBM `100`, eSpeak | unchanged (U7: `Price` came before) |
| `(`, `1`, `नेपाल` (three items) at utterance start † | IBM `(`, IBM `1`, eSpeak | eSpeak only; under "Follow main language" unchanged (D9) |
| two utterances in one speech call (for example a block end): `नेपाल`, utterance end, then `(` and `abc` as two items † | `(` eSpeak (the run language carries over), `abc` IBM | `(` IBM (U8: it looks ahead to `abc`) |
| `(2024) नेपाल` | IBM `(2024)`, eSpeak | eSpeak only (U2); under "Follow main language" unchanged |
| `नेपाल (2024) नेपाल`, "Follow main language" † | eSpeak, IBM `2024)`, eSpeak | unchanged (D3) |

Main voice English with a Chinese voice: `「中文」`, `（中文）` and `(中文)` become all Chinese †. `2024年` becomes all Chinese (U2) †; under "Follow main language" it is unchanged †.

Main voice Chinese: `「中文」` and `(中文)` are unchanged. `1. Introduction` and `3 apples` become all English (U2).

Main voice Nepali with an English voice: `"Hello"` goes from a Nepali blank plus English to English only.

Timing "after" (the default), symbol level "some":

| Input | Before | After |
| --- | --- | --- |
| `"नेपाल"`, `“नेपाल”` † | eSpeak (NVDA dropped the quote) | unchanged |
| `(नेपाल)`, `- नेपाल` † | IBM `(` or `-`, eSpeak | eSpeak only |
| `「中文」` (main English) † | English `「`, Chinese | Chinese only |
| `2024年` (main English) † | English `2024`, Chinese | Chinese only |
| any mark at level "most" or "all" † | IBM says the name, eSpeak the text | unchanged (the name is English words) |
| the pause, item-pause-0, Price and wrapper rows above | as in "before" | as in "before" |
| the two-utterance row above | `(` IBM: each utterance starts at the synth language (F13) | unchanged |

No settings panel, UI string or stored value changes.

## 4. Design

### 4.1 Affected layers

- `languageDetection/detector.py`: the rule (§4.2).
- `pipeline/breaks.py`: the two classes (D12) and the transparency check (D13).
- `pipeline/punctuation.py`: emits `InternalPunctuationBreakCommand` at internal points, and at the end-of-item path when the pending breaks hold a non-item number edge break (F11). Otherwise it emits `PunctuationBreakCommand` as today.
- `pipeline/unspaced.py`: emits `UnspacedSpaceBreakCommand` (U6).
- `__init__.py`: passes the transparency check to the detector (D13).

No other stage changes behaviour: the items, numbers, number pause, segment, say-all and dictionary stages emit what they do today. The punctuation and unspaced stages change only the class of breaks they already emit; their times and positions are unchanged (F12). Spelling, settings, panels and engines are unchanged.

### 4.2 The rule

`add_detected_language_commands` processes the sequence one utterance at a time (U8). Utterance ends pass through, and `tmp_lang`/`cur_lang` carry on as today (D11).

1. **Items.** Strings joined by adjacency, transparent breaks and wrappers form one item (U5). Any other command ends it.
2. **Item with a deciding character** (D1, D4). Every Common or Inherited character before it takes the language it gets (D2). If the search hits a stop first (D2), nothing changes. From the deciding character on, the per-character loop is unchanged.
3. **Item without a deciding character.**
   - If a deciding character or a wrapped number came earlier in the utterance, nothing changes.
   - Otherwise the item looks ahead across items and commands to the first deciding character of the utterance (U7). It takes that character's language (D10), unless it first meets a stop (D9) or the utterance ends; then nothing changes.
4. **Switch emission.** The comparison that decides a switch (`primary_language(target) != primary_language(tmp_lang)`, `detector.py:89`) and the yielded commands are unchanged. Settings and the number language are still read once per sequence (`:67-70`).

The detector stays a generator over its input. Steps 2 and 3 need the input up to the deciding character or the utterance end, so it buffers at most one utterance. In "before", NVDA's filter already turns the input into a list (`listable`, `pipeline/registry.py:39-47`). The plan chooses the helper names.

### 4.3 Invariants (Hypothesis properties, §7.3)

- **Invariant 1, never an extra switch (D6).** For every sequence, the number of voice changes between spoken text is at most what today's rule gives (the oracle), and the text is the same.
  - Detector level, a stronger form: if no document `LangChangeCommand` lies inside a span the lookahead crosses, the detection-inserted commands are the oracle's: same languages, order and count.
  - Every character outside a leading run or lookahead run has the oracle's language.
- **Invariant 2, pause settings do not change voices (U5, U6).** With the item pause above 0, each spoken non-whitespace character gets the same voice whether these are on or off: the punctuation pause (any characters, any wait), the number pause (with a fixed group size and mode), the segment pause, and the CJK space pause. Excluded: characters removed by "remove configured punctuation at pause points".

The prototype passed both as scratch properties: 400 examples each, both timings, "default" and "main", main voice English or Chinese. With the item pause at 0, Invariant 2 failed at once with `["abc,", "12नेपाल"]`, which is the U5 limitation.

### 4.4 Unchanged by construction

- **Numbers under "main" and a locale.** Every Nd digit is wrapped (`pipeline/numbers.py:22`, `numberStages.py:208`) and is a stop (D2, D9).
  - No leading run reaches past a number.
  - No lookahead crosses one.
  - A number makes "came before" true.
  - The prototype passed every existing "main" and locale test.
- **Items that start with a deciding character** have no leading run.
- **When the current language covers the deciding character's script**, nothing changes (D2, D10).
- **When no installed voice covers the script**, nothing changes (`detector.py:43-46`).
- **Mid-utterance items with only Common characters** keep today's language (U7).
- **Merging never turns a transparent break into a boundary, or the reverse** (F11). `_merged_run` keeps one of the run's own breaks, and no run holds both kinds:
  - Internal breaks stand between two non-blank texts of one item. The unspaced pause has unspaced characters on both sides. A segment cut has non-blank text on both sides (`chunker.py:63-65`). An internal punctuation point has a mark before it and non-blank text after it.
  - Number edge breaks stand next to a number inside the item.
  - Boundary breaks stand between items.
  - The one mixed case found, an end-of-item punctuation pause beside a non-item edge break, is made internal (D12). Both kinds in that run are then internal.
  - Invariant 2 pins this.

### 4.5 Error handling and threading

No new failure mode. The rule reads only the sequence at hand, and calls the existing `_language_for_character`. If the transparency check is missing, the default treats nothing as transparent (D13). `add_detected_language_commands` stays a generator that reads its inputs on the first `next()`.

## 5. Strings, translations and documentation

- No new or changed UI string; no `.po` change.
- `addon/doc/zh_TW/readme.md` only. The root `readme.md` and the other languages are synced later by the user.
  - NVDA UI names are quoted from NVDA's zh_TW catalog: 「標點及符號等級」 (`ref/nvda/source/locale/zh_TW/LC_MESSAGES/nvda.po:13906-13907`, accelerator and colon dropped), and the levels 「一些」, 「多數」 and 「全部」 (`nvda.po:1280-1294`).
  - WorldVoice's own names come from `addon/locale/zh_TW/LC_MESSAGES/nvda.po:179-188` and `:374-375`. 「項目停頓參數」, 「標點停頓字元」 and the other pipeline labels come from the readme's own list (`readme.md:47-66`).
  - **`## Unicode 偵測`**: add a bullet after the 「字元集假設的語言」 list (`readme.md:79-83`). Proposed text:

    「* 開頭的標點與符號：一段朗讀項目開頭的標點、符號與空白，交給後面第一個文字的語言朗讀，不會先切到前一個語言的語音。例如主要語音為英文時，「(नेपाल)」整段由尼泊爾語語音朗讀，「（中文）」整段由中文語音朗讀。數字語言為「跟隨前後文語言」時，開頭的一般數字（0～9）也一樣，例如「2024年」整段由中文語音朗讀。項目中間的標點仍跟隨前面文字的語言；一段朗讀的開頭若只有標點，則跟隨後面第一個文字的語言。標點停頓、數字停頓、分段停頓與中日文及東南亞文字空白停頓的設定，不會改變任何字由哪個語音朗讀。兩種「語言偵測時間點」都適用，但 NVDA 已經換成名稱的符號除外：「標點及符號等級」為「多數」或「全部」時，符號會被換成名稱（例如英文的「quote」），名稱依它本身的文字決定語言。「項目停頓參數」設為 0 時，緊接在前一個項目之後的項目，開頭的標點仍可能由前一個項目的語音朗讀。」
  - **Changelog**: add a `## 下一版更新` heading above `## WorldVoice 7.1 更新` (`readme.md:93`), with one entry. Proposed text:

    「* **開頭的標點跟隨後面的文字：** 一段朗讀項目開頭的標點、符號與空白，現在由後面文字的語言朗讀，不再先交給前一個語言（通常是主要語音）再切換語音。例如主要語音為英文時，以引號或括號開頭的尼泊爾文不再多一次語音切換與停頓。數字語言為「跟隨前後文語言」時，開頭的一般數字也一樣（例如「2024年」）。項目中間的標點不變。各種停頓設定不再影響標點由哪個語音朗讀。兩種「語言偵測時間點」都適用；NVDA 已換成名稱的符號除外。「項目停頓參數」為 0 時，緊接在前一個項目後的開頭標點可能仍跟隨前一個項目。」
- **`fix/script-digit-language` spec §2.1 G2** (`docs/superpowers/specs/2026-11-07-fix-script-digit-language-design.md`, the G2 bullet): add the note "At the start of a text item the leading `1` now follows `२` (`fix/leading-punctuation-language` U9)." This is a docs commit on this branch.

## 6. Settings, data and compatibility

No settings, config keys or stored data change. A user who wants a leading mark read by the previous voice can mark the language in the document. The new break classes are WorldVoice-internal. Synths without roles still get plain breaks (F12).

## 7. Test plan

### 7.1 Existing expectations that change (deliberately)

The prototype's full run: 3743 passed, 65 failed. One of the 65 was the prototype's own ruff finding (`test_hygiene_guards.py::test_ruff_reports_nothing`). The other 64 are below.

- **Detector rule** (`tests/test_language_detector.py`):
  - `:267` `test_unavailable_language_does_not_cover_its_script`:
    - case `C2` (`:225-232`) becomes `[("lang","de_DE"), ("lang","en"), ", hallo"]` (D5);
    - case `digits-ignored` (`:241-247`) becomes `[("lang","de_DE"), ("lang","en"), "12 hallo"]` (U2).
  - `:468` `test_script_digits_go_to_their_scripts_language`: `mixed` (`:444`) becomes `[("lang","ne"), "1२3"]`, and `common-then-script` (`:447`) becomes `[("lang","ne"), "1२"]` (U9).
  - `:860` `test_property_only_script_digits_start_a_detected_run`: under "Follow surrounding text language", a detection-inserted command may now be directly followed by a Common digit that starts a leading run or a lookahead run. The property states that case. The property for other number languages (`:875`) passes unchanged (D2).
- **End-to-end digit property**: `tests/test_worldvoice_speak.py:1040` `test_property_each_digit_is_read_by_the_number_language_voice`. Under `"default"`, a Common digit before the first deciding character of the text takes that character's voice. The oracle gets that branch.
- **Break class only.** These tests compare output with `PunctuationBreakCommand(n)` or `BreakCommand(n)`, and NVDA's equality checks the exact type (F12). Their expectations name `InternalPunctuationBreakCommand` or `UnspacedSpaceBreakCommand`; the positions and times are unchanged.
  - `tests/test_pipeline_punctuation_pause.py`: 21 tests, including all cases of `test_an_edge_break_keeps_the_punctuation_pause`.
  - `tests/test_pipeline_unspaced_space.py`: 28 tests.
  - `tests/test_pipeline_stages.py:373` `test_worldvoice_keeps_the_break_subclasses_from_the_stages`: 4 cases.
  - `tests/test_pipeline_filters.py:645` `test_an_unnamed_symbol_in_number_mode_is_left_to_the_punctuation_stage`: 2 cases.
  - `tests/test_pipeline_passthrough.py:180` `test_punctuation_pause_passes_a_leading_command`.
  - `tests/test_pipeline_pause_properties.py:85` `test_property_the_wait_changes_only_the_break_time`, whose helper keys on the exact punctuation class.
- **No longer changes.** The first version of this spec listed `test_follow_language_numbers[next]` (`tests/test_worldvoice_speak.py:500-505`). Under H it passes unchanged.

### 7.2 New unit tests

`tests/test_language_detector.py`. Installed `en_US`, `ne_NP` (`NE`, `:426`) unless stated; base `en_US`; number language "default" unless stated. The transparency check passed to the detector is the driver's (D13).

- **Reported cases:**
  - `['"नेपाल"']`, `["(नेपाल)"]`, `["“नेपाल”"]` and `["- नेपाल"]` each give `[("lang","ne"), …]`.
  - `["link", BreakCommand(10), '"नेपाल"']` gives the quote to `ne`.
  - `['" २०८१']` gives everything to `ne`.
- **Unchanged:**
  - `['abc "नेपाल"']`, `['नेपाल "नेपाल"']` and `['"']`.
  - `["link", BreakCommand(10), "("]`.
  - `[L("ne_NP"), '"नेपाल"']`.
  - `['"नेपाल"']` with no Devanagari voice.
  - `['"ᏣᎳᎩ']` (Cherokee: decides, no candidates).
- **Items under H (U5):**
  - `["link", '"नेपाल"']` (adjacent, item pause 0) gives `link"` to `en_US`: the limitation.
  - `["abc", ",", InternalPunctuationBreakCommand(0), ' "नेपाल"']` gives ` "` to `en_US`, the same as `['abc, "नेपाल"']`.
  - `["abc ", "12", NumberBreakCommand(10), "34", " (नेपाल)"]` keeps ` (` in `en_US`.
  - With a `SegmentBreakCommand`, a `NumberEdgeBreakCommand` or an `UnspacedSpaceBreakCommand` in place of the punctuation break: the same.
  - With `PunctuationBreakCommand(0)`, a `NumberItemEdgeBreakCommand`, an `IndexCommand` or a plain `BreakCommand` there: ` "` goes to `ne`.
- **Utterance-start lookahead (U7):**
  - `["(", InternalPunctuationBreakCommand(0), "नेपाल)"]`, `["-", BreakCommand(10), "नेपाल"]` and `["(", BreakCommand(10), "1", BreakCommand(10), "नेपाल"]` give the leading marks and `1` to `ne`.
  - `["Price", BreakCommand(10), "100", BreakCommand(10), "नेपाल"]` keeps `100` in `en_US`.
  - `["(", BreakCommand(10)]` alone keeps the current language.
- **Wrapped numbers (D3, D9).** Number language "main":
  - `["(", BreakCommand(10), WV("en_US"), "1", WV("en_US"), BreakCommand(10), "नेपाल"]` keeps `(` and `1` in `en_US`.
  - `["नेपाल (", WV("en_US"), "2024", WV("en_US"), ") नेपाल"]` keeps `2024) ` in `en_US`.
  - `[WV("en_US"), "2024", WV("en_US"), BreakCommand(10), "(", BreakCommand(10), "नेपाल"]` keeps `(` in `en_US` (came before).
- **Utterances (U8, D11):**
  - `["नेपाल", EndUtteranceCommand(), "(", BreakCommand(10), "abc"]` gives `(` to `en`.
  - The same with a `ConfigProfileTriggerCommand` in place of the utterance end: the same.
  - Without the utterance end, `(` stays `ne`.
  - The lookahead never crosses an utterance end: `["(", EndUtteranceCommand(), "नेपाल"]` keeps `(` in the current language.
  - The run language carries over the utterance end: `["नेपाल", EndUtteranceCommand(), "100"]` keeps `100` in `ne`.
- **Document commands (D5, D10):**
  - `[L("en"), '"नेपाल"']` gives the quote to `ne`.
  - Installed `en_US`, `hi_IN`, `ne_NP`: `['"', L("hi_IN"), "नेपाल"]` gives the quote to `hi_IN`, and `[L("ne_NP"), '"', L("hi_IN"), "नेपाल"]` keeps the quote in `ne_NP` (covered).
  - Base before the assumed language: installed `en_US`, `hi_IN`, `ne_NP`, Devanagari preference `ne`. `[L("hi_IN"), "abc", BreakCommand(10), '"नेपाल"']` gives the quote to `hi_IN`.
- **CJK and mirror:**
  - Installed `en_US`, `zh_TW`: `["「中文」"]`, `["（中文）"]` and `["(中文)"]` go to `zh_TW` with base `en_US`, and are unchanged with base `zh_TW`.
  - Base `ne_NP`: `['"Hello"']` goes to `en`.
- **Digits (U2, D2):**
  - Under "default": `["2024年"]` goes to `zh_TW`, and `["3 apples"]` with base `zh_TW` goes to `en`.
  - Under "main" unwrapped: `["2024年"]` keeps `2024` in `en_US`.
- **Default check.** Without a transparency check, `["abc", ",", InternalPunctuationBreakCommand(0), ' "नेपाल"']` treats the break as a boundary (D13).
- **Spelling is unchanged (D7).** `process_for_spelling('"नेपाल', "en_US")` gives `[('"', "en_US"), ("नेपाल", "ne")]`.
- **Read counts.** Settings and the number language are still read once per sequence. Extend `test_detection_reads_the_number_language_once_per_sequence` (`:511-520`) with a leading mark and an utterance end.

`tests/test_pipeline_punctuation_pause.py`:
- Internal points emit `InternalPunctuationBreakCommand`.
- The end-of-item pause emits `PunctuationBreakCommand`.
- With a non-item `NumberEdgeBreakCommand` pending, the end-of-item pause emits `InternalPunctuationBreakCommand` (the `नेपाल, 12 abc` case of F11).
- Both are `isinstance(…, PunctuationBreakCommand)`.

`tests/test_pipeline_unspaced_space.py`: the pause is an `UnspacedSpaceBreakCommand`, and still a `BreakCommand`. `tests/test_pipeline_stages.py`: synths without roles still get plain breaks for both new classes.

### 7.3 Property tests (Hypothesis)

- **`tests/test_language_detector.py`.**
  - `SCRIPT_SAMPLES` (`:686-692`) gains `'"'`, `"("`, `"「"`, `"- "`.
  - The item strategy (`ITEMS`, `:713-716`) also draws: number wrappers; plain, internal-punctuation, punctuation, segment, number, number-edge, number-item-edge and unspaced breaks; `IndexCommand`s; utterance ends.
  - An oracle written out in the test applies today's per-character rule (`detector.py:74-99`) with the detector's unchanged `_language_for_character`.
  - **Invariant 1** (§4.3): fewer or equal language changes between non-blank text characters, the same joined text, and every character outside a leading or lookahead run with the oracle's language. The command-list equality holds when no document `LangChangeCommand` lies in a crossed span.
  - The existing properties keep passing with the new alphabets: `test_property_detection_only_inserts_language_changes`, `test_property_letters_go_to_installed_languages`, `test_property_inserted_commands_prefer_a_covering_base` and `test_property_digits_never_start_a_detected_run_under_other_number_languages`.
- **`tests/test_worldvoice_speak.py`.**
  - **Invariant 2** (§4.3) end to end: random texts from pieces such as `abc`, `नेपाल`, `中文`, `12`, `34`, ` `, `,`, `.`, `(`, `)`, `"`, `「`, `-`, `२`, `ー`, in one to three items.
    - Number language "default" or "main"; main voice English or Chinese; both timings.
    - Item pause 10 ms; group size 0 or 3, the same in both runs.
    - Compare all four pauses off with a random on-configuration: punctuation pause on with `,.("` at wait 0, 5 or 30; number pause 0 or 10; segment length 0 or 4; CJK space pause 0 or 10.
    - Compare the voice of each non-whitespace character.
  - **Invariant 1** end to end: the harness against itself, with the detector's method swapped for the oracle. Item pause 0 or 10, random pauses. Same text, and no more voice changes.

### 7.4 End-to-end tests (`tests/test_worldvoice_speak.py`)

- **The rows of §3**, in both timings. Use `heard_through_nvda`, or a level-parameterized `nvda_processes_each_item`, where NVDA's symbol processing matters:
  - `"नेपाल"` at "some" and at "most";
  - `(नेपाल)` at "some" and "most" with timing "after" (the "most" case stays as on `master`, `[(EN, "left paren("), (NE, "नेपाल "), (EN, "right paren)  ")]`);
  - the punctuation pause pair;
  - the number pause pair;
  - the item-pause-0 limitation;
  - Price/100;
  - the utterance-start rows;
  - the "Follow main language" wrapper rows.
- **The say-all row.** It needs an `EndUtteranceCommand` in the harness. Either `heard()` learns to skip it (F9), or the case is tested at the detector level, as in §7.2.
- **Mirror.** The harness `main` gains `"ne"`, with main voice `NE`. `"Hello"` is heard by English only in both timings.

### 7.5 Mutation testing

Run mutmut on a scratch copy, with at most 3 children and the memory guard. Scope:
- `languageDetection/detector.py`, already in `[tool.mutmut] source_paths` (`pyproject.toml:42-73`);
- `pipeline/punctuation.py` and `pipeline/breaks.py`, added for this run.

Record surviving mutants and the reasons in the ledger.

### 7.6 Windows / NVDA manual items (not verified on Linux)

- **M1.** IBM TTS as the English main voice, eSpeak Nepali, timing 「在 NVDA 處理語音指令前」, level 「一些」. Read lines that start with `"नेपाल`, `(नेपाल`, `“नेपाल` and `- नेपाल`. There is no IBM switch or pause before the Nepali voice.
- **M2.** Timing 「在 NVDA 處理語音指令後」. `(नेपाल)` has no IBM switch. `"नेपाल"` is as on 7.1, with no switch.
- **M3.** Level 「多數」. In "before", eSpeak reads the English name "quote". In "after", IBM reads it, as on 7.1.
- **M4.** A browse-mode link followed by quoted Nepali text, and say all over Nepali paragraphs that start with quotes. The quotes are read by eSpeak, and a line starting with `(` followed by English is read by IBM.
- **M5.** Turn the punctuation pause on with `,` and `(`. `abc, "नेपाल"` keeps the same voices, and a line starting with `(नेपाल` is read by eSpeak.
- **M6.** With 「項目停頓參數」 at 0: a link followed by quoted Nepali may read the quote with IBM (U5 limitation).
- **M7.** English main voice with a Chinese voice: `「中文」` is read entirely by the Chinese voice.

## 8. Open questions

None. The first version's Q1–Q4 are resolved:
- Q1 by U4;
- Q2 by U5 (option H) and U6;
- Q3 by U7;
- Q4 by U9.
