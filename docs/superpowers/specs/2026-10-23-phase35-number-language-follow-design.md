# Phase 35: numbers follow the text language; the number language decides every digit

Date: 2026-10-23.
Baseline: `master` `da7f791`. Branch: `phase35-number-language-follow`, worktree `/workspace/WorldVoice-phase35` (`ref` symlinked to `/workspace/WorldVoice/ref`).
Baseline numbers: `python3 -m pytest -q tests` → 2413 passed, 0 skipped, 0 warnings (pytest turns any DeprecationWarning into an error, phase 33 §1.5); `prek run --all-files` all Passed.
Flow: normal flow (`DEVELOPMENT_WORKFLOW.md` §3). Nothing here needs the complex flow.
Status: the seven parts and three detail points were decided by the user (2026-10-23). Smaller defaults are marked where they apply and collected in §13.

References used throughout:

- Detector: `addon/synthDrivers/WorldVoice/languageDetection/__init__.py` (below: `detection:<line>`).
- Detection settings: `addon/synthDrivers/WorldVoice/languageDetection/settings.py` (below: `dsettings:<line>`).
- Pipeline stages: `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (below: `pipeline:<line>`).
- Number definitions: `addon/synthDrivers/WorldVoice/pipeline/numbers.py` (below: `numbers:<line>`).
- Pipeline settings table: `addon/synthDrivers/WorldVoice/pipeline/settings.py` (below: `psettings:<line>`).
- Synth: `addon/synthDrivers/WorldVoice/__init__.py` (below: `synth:<line>`).
- Unicode Detection panel: `addon/globalPlugins/WorldVoice/speechSettingsDialog.py` (below: `dialog:<line>`).
- NVDA: `ref/nvda/source/...` (`ref/nvda` at `7d25bc76e`).

A prototype of the design in §4 and §6 was run in a scratch copy (not committed) against the speak harness of `tests/test_worldvoice_speak.py`, over 14 inputs × 5 configurations × 3 timing/detection combinations × 2 main languages. Its results are quoted in §4.6.

## 1. Problem

Two settings decide which voice reads a digit, and they interact in a way users cannot predict.

- **Unicode Detection panel, "Ignore numbers when detecting text language"** (`ignoreNumbersInLanguageDetection`, default off, `dsettings:16`, read at `dsettings:62`, panel `dialog:505-511`, saved `dialog:561`). The detector reads it per digit (`detection:136-139`):
  - off: a digit goes to the **base language** (`curLang`: the language of the last `LangChangeCommand`/`WVLangChangeCommand`, or the synth's language, `detection:148-154`);
  - on: a digit stays in the **current language** (`tmpLang`, the language detection last switched to).
- **Number language** synth setting (`numlan`, `synth:177`, choices `synth:455-459`, table entry `psettings:148-162`). `inject_number_language` (`pipeline:278-293`) wraps every number as `WVLangChangeCommand(numlan)`, number, `WVLangChangeCommand(back)` (`pipeline:256-275`). The value `"default"` is a pass-through (`pipeline:284-290`).
- The number stages always run before detection:
  - detection timed "after" runs in `speak()` (`synth:310-311`), after every NVDA filter;
  - detection timed "before" is a filter (`synth:449-451`), and `order_move_to_start_register` moves every stage of `STAGES` in front of it (`pipeline:792-795`; NVDA's `moveToEnd(handler, False)` moves a handler to the start, `ref/nvda/source/extensionPoints/util.py:138-153`).
- So a non-default number language already overrides the ignore option, while "default" hands the decision to the detector. Users meet two controls in two panels for one question.

## 2. Goals and non-goals

### 2.1 Goals (all decided by the user, 2026-10-23)

1. **Number language options.** The stored value `"default"` stays the default and is relabelled "Follow current text language": digits follow the surrounding (detected) language. A new stored value `"main"`, "Follow document main language": digits go to the base language, which is what "ignore numbers" off does today. Specific locales are unchanged.
2. **Remove the Unicode Detection checkbox and the `ignoreNumbersInLanguageDetection` key**: setting field, service parameter, confspec entry, panel control, zh_TW string, readme bullets in all six readmes, tests.
3. **Accept the default change.** A user who never changed anything hears digits follow the text instead of returning to the base. Write a changelog note (§9).
4. **No migration.** A stored number-language value that is not a valid option reads as `"default"`. The old ignore key is no longer read.
5. **All digit decisions move to the pipeline.** The detector passes digits through like Common characters. Spelling follows the number language too (detail point 3, §5).
6. **"main" is implemented in the pipeline**, not in the detector (§4).
7. **Option B: one digit set everywhere.** Every number rule of the pipeline and the detector uses the same digits (detail point 1: Unicode decimal digits, §6).

### 2.2 Non-goals

- Script classification (`languageDetection/script_data.py` is a protected path; `scripts.py` unchanged).
- The order of language choice for letters (phase 33 §2.3, §3.3).
- Number mode semantics (value, number, group), the group size, the symbol set `SYMBOLS` (`numbers:13`, decided by the user 2026-10-22 as Latin-1 P/S only, `docs/superpowers/specs/2026-10-22-feat-number-unify-design.md:33`), signs `+`/`-`, and symbol naming (`pipeline/symbols.py`).
- The punctuation pause stage, the chinese-space stage, the item and say-all pauses.
- What the early number-language stage does with a specific locale when detection is off. The pre-existing loss of a punctuation pause and of the dot rule in front of a number wrapped for another voice (§12, F6) stays as it is.
- Any engine wrapper; upstream drivers; Neural.

## 3. User-visible changes

What NVDA users hear:

| Configuration | Text (main voice English, Chinese voice installed) | Today | After |
|---|---|---|---|
| defaults (detection on, number language "default", ignore off) | `中文 12` | `12` by the English voice | `12` by the Chinese voice |
| ignore on, number language "default" | `中文 12` | Chinese voice | Chinese voice (unchanged) |
| number language "Follow document main language" | `中文 12` | — | English voice (what the defaults did) |
| number language "zh_TW", main voice Chinese, English text | `abc 123 def` | Chinese voice (base) | Chinese voice (kept by §4.4; would have become English) |
| detection off, any "default"/"main" | `中文 12` | all English voice | unchanged |
| number language "en", full-width digits | `中１２３` | English voice: the detector sends `１２３` to the base, although it is not a number (with ignore on: the Chinese voice, with the text) | `１２３` is a number: English voice |

What they see:

- NVDA Speech settings → Voice (WorldVoice's `WorldVoiceVoiceSettingsPanel`, `VoiceSettingsDialogs.py:37`) → combo box "Number language". NVDA builds it from `availableNumlans` (`ref/nvda/source/gui/settingsDialogs.py:1462-1514`). The list now starts with "Follow current text language" (selected by default), then "Follow document main language", then the locales of the installed voices as today. The Speech Pipeline panel does not show the number language (`psettings:160`, `panels=("voice",)`), so it is unchanged.
- Synth settings ring: the "Number language" entry steps through the same values in the same order (`ref/nvda/source/synthSettingsRing.py:74-103`).
- Unicode Detection panel (`dialog:480-568`): the first control was the checkbox "Ignore numbers when detecting text language". It is gone, so focus lands first on the combo box "Language assumed for latin characters:" (or the next enabled script choice). The other controls, their names and order are unchanged.
- Spelling with "trust voice's language" on (§5): a digit right after a letter of another language keeps that letter's character descriptions under "Follow current text language".

## 4. Design: where each number-language value acts

### 4.1 Values

| Stored value | Label | Meaning |
|---|---|---|
| `"default"` | Follow current text language | Digits are not wrapped; detection keeps them in the current language (§6.3). |
| `"main"` | Follow document main language | Digits are wrapped in the language in force where they stand: the last `LangChangeCommand`/`WVLangChangeCommand` before them in the stream, or the synth's language (`ctx.language`) when none. |
| a locale | that locale's description | Unchanged: digits are wrapped in that locale. |

`"main"` cannot collide with a locale: `availableNumlans` lists `voiceManager.languages` (`synth:457`, `voiceManager.py:284-285`), which are locale codes.

### 4.2 The trap in the obvious design

The obvious design is to give `"main"` the code path of a specific locale, with `num_lang = current_lang`:

- `_insert_WVLangChangeCommand_between_number` dedupes each string's wrappers with `start_language=current_lang` (`pipeline:247-252`). `deduplicate_language_command` drops a command whose language equals the language in force (`pipeline:609-610`) or whose voice is the voice in use (`pipeline:621-623`).
- A `"main"` wrapper always names the language in force, so the stage drops every one of them. Detection then sees bare digits, and after §6.3 they follow the text. `"main"` would behave exactly like `"default"`.
- The comment at `pipeline:284-288` already relies on this: for `"default"` (where `num_lang` is also `current_lang`, `pipeline:271`) the wrappers "are always dropped".

**A second trap, for specific locales.** The same dedupe also drops the wrappers of a specific number language whose voice is the voice already in force (`pipeline:621-623`), for example number language zh_TW with a Chinese main voice. Today detection then sends the bare digits to the base language, which is that same voice, so nobody notices. After §6.3 they would follow the text instead, so `abc 123 def` would read `123` in English although the user chose zh_TW (prototype: `'abc 123 def'` reaches detection unwrapped).

### 4.3 Rejected: "no stage-level dedupe for main"

Skipping the stage dedupe and letting the dedupe in `speak()` (`synth:315`) remove the redundant wrappers after detection gets the voices right, but the wrappers then sit in the stream while the later stages run:

- `inject_punctuation_pause` decides a boundary pause only when the next item is text (`pipeline:557-558`). A wrapper between `"Total. "` and `"12"` suppresses it: the prototype gave `('Total', '.', ' ', '12')` with no break, where today's ignore-off output is `('Total', '.')`, break, `(' 12',)`.
- The dot rule of `iter_number_speech_segments_mode` (`pipeline:358-372`) works inside one item. `"12. Next"` split by wrappers loses its separating space: `('12', '.')` instead of `('12 ', '.')`.

Both effects already exist today for a specific number language whose voice differs (prototype, number language zh_TW: `'Total' '.' ' ' <zh_TW> '12'`, no pause). Moving every `"main"` user into them would break the "same as ignore off" promise of goal 1.

### 4.4 Chosen: wrap numbers where detection runs

Decided by the user (2026-10-23): a late wrapping for detection (item 2 as first written). Revised after the batch 1 review (2026-10-23, finding C1): the wrapping is no longer a `STAGES` filter but runs right before detection, wherever detection runs. Decided by orchestrator with the recommended default; user may override before merge.

Why the revision: a `STAGES` filter runs before NVDA's `speak()` calls `processText` on each text item and appends its chunk separator (`ref/nvda/source/speech/speech.py:1137`, `:1216-1225`). A filter that splits an item at every number, even where the voice does not change, made NVDA's context-dependent symbol rules read pieces instead of the item: with NVDA's real `characterProcessing` at symbol level "some", `COVID-19 cases` became `COVID` / ` minus 19` / ` cases`, `the 1st item` became `the  1  st item`, `in 2024!` and `Is it 5?` lost their `!` and `?`, and with a Chinese main voice `第1名` became `第  1  名`. Before phase 35 these items stayed whole.

1. **The early stage** (`inject_number_language`, `pipeline:278-293`) treats `"main"` exactly like `"default"`: a pass-through. A `"main"` wrapper would name the language in force and be dropped by the stage dedupe anyway (§4.2), so this changes nothing and skips the scan. Specific locales keep today's code, dedupe included. Update the comment at `pipeline:284-288` to cover both values.
2. **`wrap_numbers_for_detection` and `detect_with_number_language`** in the pipeline module (not in `STAGES`; `LOG_SWITCHES` and the Log Record panel unchanged). The synth's detection call (`add_detected_language_commands`) is `detect_with_number_language(sequence, detector.add_detected_language_commands, speech_context())`: as NVDA's filter for timing "before" (after every stage, before `processText`), and in `speak()` for timing "after" (after `processText`). The detector itself still decides no digit (goals 5 and 6).
   - It wraps only when `ctx.supports_roles and ctx.number_language != "default"`; otherwise detection runs on the sequence as it is.
   - It tracks the language in force like the early stage does (`pipeline:244-245`): `item.lang or ctx.language` at every `LangChangeCommand`/`WVLangChangeCommand`, starting from `ctx.language`.
   - For each `NUMBER_RE` match in a text item it yields `WVLangChangeCommand(target)`, the match, `WVLangChangeCommand(language in force)`. `target` is the language in force for `"main"`, and the stored locale otherwise.
   - After detection, each wrapper that `deduplicate_language_command` would drop (it keeps the voice) is removed, and the two pieces of one text item it separated join again. Nothing joins across another command (index, break, character mode, NVDA's own `LangChangeCommand`, a command detection inserted) or across two items, and NVDA's `LangChangeCommand`s are never removed (`processText` reads them for the symbol locale). So where the voice does not change, `processText` sees the item as before phase 35; where it changes, the split is the one detection makes anyway. The dedupe in `speak()` (`synth:313-315`) still removes the other redundant commands.
   - Inside the wrappers of the early stage the language in force is already the number language, so a specific locale yields duplicates there (`<zh_TW> <zh_TW> '12' <zh_TW> <en>`). They cost nothing: `speak()` drops them (`pipeline:609-610`).
3. ~~**`SpeechContext` gains `detects_language: bool = False`**~~ Dropped with the revision: the wrapping runs only where detection runs, so no stage needs to know whether it does.

Why this gives exactly today's ignore-off result:

- Every number is wrapped only after the punctuation, number-mode and number-pause stages have run, so their output is today's output. In timing "after" it is wrapped after `processText` too, so NVDA processes every item as before.
- The opening wrapper makes detection switch to the base (`detection:152-154`). The closing wrapper resets `tmpLang` to the base after the number, exactly as today's digit rule leaves `tmpLang` at the base after the last digit (`detection:159-165`).
- In number and group mode, every digit piece is its own match. A symbol name between pieces comes right after a closing wrapper, so detection sees it from the base, as today. Symbol names are still looked up in the language in force (`pipeline:330`, `"main"` added to the "no number language" case, §4.5).

### 4.5 Other code that reads the number language

- `inject_number_mode` (`pipeline:330`): names symbols "for the number language" when it is a locale, else for the language in force. `"main"` must join `"default"` in the second case. Without that, `"main"` would be passed to `symbol_namer` as a locale and every symbol would stay unnamed (`pipeline/symbols.py:53-59`, then NVDA's lookup of locale `"main"`).
- `iter_number_speech_segments_language` (`pipeline:271`): only reached for a locale after §4.4. Keep the `"default"` fallback and add `"main"`, so the helper stays correct for any value.
- One definition of the two stored values, used by the synth, both stages, the settings table and the detector (§5). It must import nothing from NVDA and must not import the `pipeline` package (the detector loads without it, `tests/detector_harness.py:20-49`). Recommended: a new standard-library-only module `addon/synthDrivers/WorldVoice/numberLanguage.py` with `FOLLOW = "default"` and `MAIN = "main"`. The labels go in `pipeline/settings.py` as `NUMBER_LANGUAGE_CHOICES`, next to `NUMBER_MODE_CHOICES` (`psettings:56-65`), so they keep their `# Translators:` comments and `addonHandler.initTranslation()` (`psettings:24`). The plan may pick another home within these limits.
- `_get_availableNumlans` (`synth:455-459`) lists `NUMBER_LANGUAGE_CHOICES` first, then the locales. The `_("default")` msgid stays in use for variants (`synth:412`).

### 4.6 Traces

After the revision of §4.4, read "After the stages" as "what detection receives" (in timing "after", the text has been through `processText`), and redundant wrappers are removed after detection.

Voices: English `A:en` (main voice, synth language `en`) and Chinese `B:zh`. `<x>` is a `WVLangChangeCommand(x)`, `<L:x>` a `LangChangeCommand(x)`. "Voices" is what `queue_speech_sequence` receives, consecutive chunks of one voice joined. The prototype matched today's ignore-off result (or ignore-on result for "default") in every row except §4.7.

| # | Value, detection | Input | After the stages | After detection | Voices |
|---|---|---|---|---|---|
| T1 | main, "after" | `中12` | `'中' <en> '12' <en>` | (in `speak()`) `<zh> '中' <en> '12' <en>` | zh `中`, en `12` (today, ignore off: same) |
| T2 | main, "before" | `中12` | `'中' <en> '12' <en>` | `<zh> '中' <en> '12' <en>` | zh `中`, en `12` (same) |
| T3 | main, detection off | `中12` | `'中12'` (both stages pass through) | none | en `中12` (same) |
| T4 | default, "before" | `中12` | `'中12'` | `<zh> '中12'` | zh `中12` (today, ignore on: same) |
| T5 | main, "before", NVDA tags German, no German voice | `[<L:de_DE>, 'abc 12 中']` | `<L:de_DE> 'abc ' <de_DE> '12' <de_DE> ' 中'` | `<L:de_DE> <en> 'abc ' <de_DE> '12' <de_DE> ' ' <zh> '中'` | en `abc 12 `, zh `中` (same; `12` goes to `de_DE`, whose lookup falls back to the main voice, phase 33 Q6) |
| T6 | zh_TW, "before", main voice Chinese (second trap) | `abc 123 def` | early stage drops its wrappers; late stage: `'abc ' <zh_TW> '123' <zh_TW> ' def'` | `<en> 'abc ' <zh_TW> '123' <zh_TW> ' ' <en> 'def'` | en `abc `, zh `123 `, en `def` (same as today) |
| T7 | zh_TW, "after", main voice English | `abc 12` | early: `'abc ' <zh_TW> '12' <en>`; late adds `<zh_TW>` around `'12'` | unchanged by detection | en `abc `, zh `12` (same) |
| T8 | main, "after", number mode | `中12.5 ok` | `'中' <en> '1' <en> [NB] <en> '2' <en> [NB] 'full stop' [NB] <en> '5' <en> ' ok'` | `<zh> '中' …` | zh `中`, en `1`, `2`, `full stop`, `5`, ` ok` (same) |
| T9 | any, other synth (scope "all") | `中12` | `remove_language_command` (`pipeline:293`), late stage inactive (`supports_roles` False) | — | unchanged; `GENERIC_CONTEXT.number_language` `"Windows"` (`pipeline/context.py:22`) is never compared, because every number-language branch first checks `supports_roles` (`pipeline:283`, `:330`) |

T3 covers every engine with detection off. Engines differ only in the voices they publish; none sees these commands, because `lang_cmd_to_voice` turns them into `SelectVoice` (`pipeline:633-646`).

### 4.7 Where "main" still differs from today's "ignore off"

1. **Signs and hyphens.** `NUMBER_RE` takes a `+`/`-` that does not follow a digit (`numbers:19`). Today's detector moved only the digits, so in `中 -12` the `-` stayed with the Chinese voice; now `-12` is read by the base voice. In `COVID-19` with a Chinese main voice, `-19` moves together. Specific locales already wrap this way. Decided by the user (2026-10-23): accept. With detection timed "before", the voice change at the sign starts a text item, so NVDA's `processText` reads that `-` as a negative sign (`COVID-19 疫情` with a Chinese main voice: `COVID` / `負 19 疫情`), as it already does before phase 35 for a number language whose voice differs; with detection timed "after", `processText` has already read the whole item.
2. **Superscripts and circled digits** (`²`, `①`) went to the base under "ignore off" because the detector tested `str.isdigit()` (`detection:136`). They are not decimal digits (§6.1), so they now stay in the current language.
3. ~~**NVDA rewrites language commands after the filters, timing "after" only.**~~ No longer applies after the revision of §4.4: the wrapping runs where detection runs, so in both timings it sees the same language commands as detection. What follows is kept as the record of the first design. NVDA's `speak()` runs the filters first (`ref/nvda/source/speech/speech.py:1137`) and only then rewrites `LangChangeCommand`s (`speech.py:1184-1200`). The speech manager also drops them unless NVDA's automatic language switching is on (`ref/nvda/source/speech/manager.py:366-369`). The late stage sees the commands before the rewrite; detection timed "after" sees them after it. Two narrow cases differ:
   - "Report language" on, automatic language switching off, a passage NVDA tags with a language: the digits go to the tagged language's voice (or the main voice when it has none), while detection's base is the synth language.
   - Automatic language switching on and "Trust voice's language" off: NVDA inserts its interface language as the default (`speech.py:313-321`, `:1198-1200`), but the digits go to the synth's language.

   The closing wrapper of a specific locale has the same property today. WorldVoice turns automatic language switching off on install (`_speechcommand.py` docstring). Decided by the user (2026-10-23): accept and record it. The alternative (§13 Q3) is a "base language" marker that detection resolves, which puts part of `"main"` back into the detector.

## 5. Spelling

Decided by the user (2026-10-23): spelling follows the number language too.

- Today `process_for_spelling` sends whitespace and digits to the spelling locale (`detection:178-179`). `patchedSpeakSpelling` uses it when detection is on and NVDA's "trust voice's language" is set (`synth:325-330`). The locale chosen there picks NVDA's character descriptions and symbol names, and becomes a `LangChangeCommand` when NVDA's automatic language switching is on (phase 33 §2.4).
- The detector gets the number language through a new keyword-only constructor argument `number_language: Callable[[], str]`. The synth passes `lambda: self._numlan` (`synth:261-265`). It is read once per `process_for_spelling` call, like the settings (`detection:173`). Defaulting the argument to "always `FOLLOW`" keeps the existing direct constructions in the tests valid; the synth always passes it.
- A digit (§6.1) in `process_for_spelling`:
  - `"default"`: the current language, the language of the run so far (at the start of the text that is the spelling locale);
  - `"main"`: the spelling locale (today's behavior);
  - a locale `L`: `L` when `get_primary_language(L)` is in `availableLanguages`, otherwise the spelling locale. Decided by the user (2026-10-23). In practice the fallback is hardly reachable: the choices come from `voiceManager.languages`, a subset of `allLanguages` (`voiceManager.py:276-285`).
- Whitespace keeps today's rule: the spelling locale. Changing it would split runs only to move a space between locales, so there is no reason to.
- Runs still split only when the primary subtag changes (`detection:192`), so with locale `en_US`, number language `zh_TW` and text `中1` the result stays one run `("中1", "zh")`.
- Examples with `en_US` and `zh_TW` installed and locale `en_US`: `中1` → `[("中1","zh")]` under "default"; `[("中","zh"),("1","en_US")]` under "main" (today); `[("中","zh"),("1","en")]` under number language `en`. The existing expectations `a中 1` (`tests/test_language_detector.py:386-393`) stay as they are under "default", because the space resets the run to the locale first.
- The voices that read spelled digits do not come from this function. `speakSpelling` passes its sequence through `speak()` (`ref/nvda/source/speech/speech.py:350-364`), so the pipeline stages, the number language included, already apply to spelled digits.

## 6. Digits (Option B)

### 6.1 The digit set

Decided by the user (2026-10-23): a digit is a Unicode decimal digit, general category Nd. In Python that is `str.isdecimal()` and `\d` in a `str` pattern without `re.ASCII`. It covers ASCII `0-9`, full-width `０-９` (U+FF10-FF19), Arabic-Indic `٠-٩` (U+0660-0669), Extended Arabic-Indic `۰-۹` (U+06F0-06F9), Devanagari, Thai and so on (760 characters under Python 3.14's Unicode 16.0). It excludes superscripts (`²`), subscripts, circled and parenthesized digits (`①`, `⑴`) and Ethiopic digits (category No).

Rejected alternative: `str.isdigit()`, today's detector test (`detection:136`, `:178`). It adds 128 No characters. `10²` would become the number `102` in the pipeline (group mode reads "102"), and NVDA's own reading of `²`/`①` would be lost.

### 6.2 Pipeline changes

`numbers:19-26` and their users:

| Definition | Today | After | Users |
|---|---|---|---|
| `NUMBER_RE` | `(?:(?<![0-9])[+-])?[0-9]+(?:[SYM]+[0-9]+)*` | `[0-9]` → `\d` (lookbehind included) | number language (`pipeline:249`, `:256`), the new late stage, number mode (`pipeline:356`), spaced-number pause (`numbers:45`, `pipeline:117-123`) |
| `NUMBER_TOKEN_RE` | `^[+-]?[0-9]+\|[0-9]+\|[SYM]` | `\d` | `number_pieces` (`numbers:78`) |
| `DIGITS` | `frozenset("0123456789")` | removed; `number_pieces` tests `token[-1].isdecimal()` (`numbers:79`) | — |
| `THOUSANDS_RE` | `(?<![0-9,])[0-9]{1,3}(?:,[0-9]{3})+(?!,*[0-9])` | `\d` | `remove_thousands_separators` (`pipeline:57-70`) |

Already consistent, no change: the punctuation regex's `(?![chars\d])` (`pipeline:427`) already uses Unicode `\d`, so `12,500` written with Arabic-Indic digits already keeps its comma.

Rules that stay (decided earlier and kept):

- **Signs and separators are unchanged.** A sign is ASCII `+`/`-`; separators are Latin-1 punctuation and symbols (`numbers:11-13`, decided by the user 2026-10-22, Q2). So `１２．５` (full-width full stop) is two numbers `１２` and `５`, like `12，34` today (`tests/test_pipeline_filters.py:126`). The same holds for the Arabic decimal and thousands separators `٫` `٬` (U+066B, U+066C). Decided by the user (2026-10-23) (§13 Q6).
- **Mixed digit scripts in one run** (`1٢3`) form one number, as `\d+` matches them. Rare; not special-cased.
- Whitespace pairing of spaced numbers already counts any `isspace()` gap (`numbers:42-48`), including the ideographic space U+3000, so `１　２` gets the number pause.

### 6.3 Detector

- `_language_for_character` (`detection:135-143`): replace the digit branch with `if character.isdecimal(): return current_language`. The branch must stay: many Nd digits are not Common script (Arabic-Indic and Extended Arabic-Indic are Arabic; Devanagari, Bengali, Thai, Myanmar and others carry their own scripts, checked against `script_data.py`). Without the branch, `abc ١٢٣` would switch to an Arabic voice.
- The `ignore_numbers` read and the `base_language` use for digits go.
- `process_for_spelling` (`detection:178`): `isdigit()` becomes `isdecimal()` and the digit rule of §5 applies.

### 6.4 What is spoken for non-ASCII digits

Decided by the user (2026-10-23): pieces keep their original characters. Number and group modes cut `１２３４５` into `１２３`, `４５`, not `123`, `45`. Value mode already keeps the number as written.

- NVDA's default Unicode normalization (`speech.unicodeNormalization`, behavior "enabled", `ref/nvda/source/config/configSpec.py:40`) applies NFKC in `processText` (`speech.py:1180`, `:1225-1230`, `:210-211`; `textUtils/__init__.py:425`, `:560-568`). That runs after the WorldVoice filters, so with NVDA's default settings, engines receive ASCII digits for full-width ones.
- Arabic-Indic and other Nd digits are not compatibility characters, so NFKC leaves them alone. Each voice reads them as it can (manual item M3).

## 7. Settings, data and compatibility

### 7.1 Number language

- Storage: NVDA stores `numlan` in `config.conf["speech"]["WorldVoice"]` as a driver setting (`synth:105-125`, `useConfig` True for `pipeline_config=False`, `psettings:161`). Its confspec is `string(default=default)` (`ref/nvda/source/autoSettingsUtils/driverSetting.py:34-38`), so NVDA accepts any string.
- Invalid values today: no check anywhere. NVDA's loader calls the setter with the stored string (`ref/nvda/source/autoSettingsUtils/autoSettings.py:200-207`), and `_set_numlan` stores it as is (`synth:464-465`). The pipeline settings normalization (`PipelineSettingSpec.convert`, `psettings:107-113`) never sees it, because the entry is not stored in the pipeline section (`psettings:279`). Consequences of an invalid value today:
  - numbers are wrapped in an unknown language, which `getVoiceNameForLanguage` sends to the main voice;
  - the Voice panel combo box shows no selection (`settingsDialogs.py:1501-1507` swallows the `ValueError`);
  - the settings ring breaks: `StringSynthSetting._get_value` returns None (`synthSettingsRing.py:86-90`), and `increase`/`decrease` compute `None + step` (`:38-41`, `:49-52`), which raises `TypeError`.
- New rule (decided by the user, 2026-10-23, goal 4; where it is checked: decided by the user (2026-10-23)): `_set_numlan` accepts `"default"`, `"main"` and the locales in `self._voiceManager.languages`; any other value is stored as `"default"` with one `debugWarning` per call that names the refused value.
  - NVDA loads `voice` before `numlan` (supported-settings order, `synth:129-148`; loader loop `autoSettings.py:200`), so the locale list matches the loaded voice.
  - A locale hidden by "Keep main locale engine consistent" (`voiceManager.py:280-285`) after a voice change also counts as invalid on the next load. Its digits were already going to an unrelated voice.
  - The refused value stays in the file until NVDA saves the synth settings: the Voice panel's `onSave` (`settingsDialogs.py:1630-1631`) writes `"default"` over it. Nothing writes it back on its own.
- Users who stored `"default"` keep `"default"`. Its meaning changes as goal 3 accepts.

### 7.2 The removed key

- `ignoreNumbersInLanguageDetection` leaves `DETECTION_CONFSPEC` (`dsettings:15-21`), `_IGNORE_NUMBERS_KEY` (`:28`), `DetectionSettings.ignore_numbers` (`:36`), `get` (`:62`) and `update` (`:72`, `:84-86`).
- A value left in a user's `nvda.ini`/profile is harmless:
  - NVDA's aggregated config reads a key only on access (`ref/nvda/source/config/__init__.py:1179-1228`), and nothing asks for it any more;
  - configobj keeps unknown keys and does not report them as validation errors (only spec keys appear in `flatten_errors`, `config/profileUpgrader.py:46-60`; the WorldVoice section is not in NVDA's base spec at all).

  The key simply stays in the file. No migration (goal 4).
- `DetectionSettingsService.update(ignore_numbers=...)` now raises `TypeError` (unexpected keyword). The only caller is the panel (`dialog:560-568`).
- Changed-field names delivered to listeners lose `"ignore_numbers"`. `_on_detection_settings` only checks `"timing"` (`synth:439-442`).

### 7.3 Error handling

- No new failure points. The wrapping is a generator over the same items as the early stage and raises nothing new; the rejoin only concatenates text items.

## 8. Affected layers

- Core, shared by all engines:
  - `pipeline/__init__.py`: early-stage gate, `inject_number_mode` gate, `wrap_numbers_for_detection` and `detect_with_number_language` (§4.4);
  - `pipeline/numbers.py`: digit set;
  - `pipeline/settings.py`: `NUMBER_LANGUAGE_CHOICES`;
  - `languageDetection/__init__.py`: digit branch, spelling, constructor;
  - `languageDetection/settings.py`: key removal;
  - new `numberLanguage.py`.
- Synth composition (`synthDrivers/WorldVoice/__init__.py`): choices, setter validation, `speech_context`, detector construction.
- Global plugin (`speechSettingsDialog.py`): checkbox removal.
- Engines: none. The change is audible with every engine that publishes voices for more than one language.

## 9. Strings, translations and documentation

New strings (both in `pipeline/settings.py`, each with a `# Translators:` comment, checked by `tests/test_translator_comments.py`):

| msgid | Translators comment | zh_TW |
|---|---|---|
| `Follow current text language` | A number language choice: numbers are read in the language of the text around them. | 跟隨當前文字語言 |
| `Follow document main language` | A number language choice: numbers are read in the main language, the language the document marks or the main voice's language. | 跟隨文件主要語言 |

The English labels keep the sentence case of the existing labels ("Detect language based on Unicode characters", "Language assumed for latin characters:"). The zh_TW labels are the user's.

Removed string: `Ignore numbers when detecting text language` ("偵測語言時忽略數字", `addon/locale/zh_TW/LC_MESSAGES/nvda.po:147-150`). Delete the entry outright, as in `a4629a1` and phase 33 §7. `msgid "default"` (`nvda.po:428-431`) stays: the variant list still uses it (`synth:412`). Run `msgfmt --check`. Other catalogs are left to their translators.

Readmes. Decided by the user (2026-10-23): the ignore bullet goes from all six readmes. Decided by the user (2026-10-23): so that no section intro promises a number option any more, "numbers" also goes from each Unicode Detection intro (as phase 33 did for punctuation); the number language bullet is rewritten only in the two documents maintained here (`readme.md`, `addon/doc/zh_TW/readme.md`).

- Delete the bullet: `readme.md:57`, `addon/doc/zh_TW/readme.md:57`, `addon/doc/zh_HK/readme.md:55`, `addon/doc/zh_CN/readme.md:56`, `addon/doc/ru/readme.md:56`, `addon/doc/uk/readme.md:56`.
- Intros become:
  - `readme.md:55`: "These options adjust how WorldVoice handles character sets shared by multiple languages when detecting text language."
  - `addon/doc/zh_TW/readme.md:55` and `addon/doc/zh_HK/readme.md:53`: 「這些選項用來調整 WorldVoice 在偵測文字語言時，如何處理多語共用字元集。」
  - `addon/doc/zh_CN/readme.md:54`: 「这些选项用来调整 WorldVoice 在检测文字语言时，如何处理多语共用字符集。」
  - `addon/doc/ru/readme.md:54`: "Эти параметры настраивают, как WorldVoice обрабатывает наборы символов, общие для нескольких языков, при определении языка текста."
  - `addon/doc/uk/readme.md:54`: "Ці параметри налаштовують, як WorldVoice обробляє набори символів, спільні для кількох мов, під час визначення мови тексту."
- Number language bullet, `readme.md:43`:
  > * Number language: Chooses the language that reads numbers.
  >   * Follow current text language (default): numbers are read in the language of the text around them. With Unicode detection on, a number in Chinese text is read by the Chinese voice.
  >   * Follow document main language: numbers are read in the main language: the language the document marks, or the main speech role's language.
  >   * A specific language: numbers are always read by the speech role of that language.
  >
  >   Numbers include full-width digits (０–９) and other Unicode decimal digits, such as Arabic-Indic digits.
- `addon/doc/zh_TW/readme.md:43`:
  > * 數字語言：選擇朗讀數字的語言。
  >  * 跟隨當前文字語言（預設）：數字以前後文字的語言朗讀。開啟 Unicode 偵測時，中文裡的數字由中文語音朗讀。
  >  * 跟隨文件主要語言：數字以主要語言朗讀，也就是文件標示的語言或主要語音角色的語言。
  >  * 指定語言：數字一律由該語言的語音角色朗讀。
  >
  >  數字包括全形數字（０～９）與其他 Unicode 十進位數字，例如阿拉伯-印度數字。

Changelog. The changelog is the second half of each readme (`readme.md:67-`, `addon/doc/zh_TW/readme.md:65-`). Its newest section, "WorldVoice 6 Update", has not changed since the `6.2` tag (`git diff --stat 6.2 HEAD -- readme.md` touches only the user guide part). Phase 33 left it alone (phase 33 §7). `buildVars.py:29` `addon_changelog` is the store summary, and the main checkout has an uncommitted user edit in `buildVars.py`, so that file is not touched.

Decided by the user (2026-10-23): write a changelog note. Decided by the user (2026-10-23): add a new top section in `readme.md` and `addon/doc/zh_TW/readme.md` only, headed "## Next update" / 「## 下一版更新」, to be renamed to the version number at release:

> * **Numbers follow the text language by default:** The "Ignore numbers during language detection" option has been removed from the Unicode Detection panel. Number language now offers "Follow current text language" (the default: numbers are read in the language of the text around them) and "Follow document main language" (numbers are read in the main language). Earlier versions read numbers in the main language unless the option was checked; choose "Follow document main language" to keep that.
> * **Full-width and other Unicode digits are numbers:** Number language, number modes, number pauses and the thousands separator rule now also apply to full-width digits and other Unicode decimal digits, such as Arabic-Indic digits.

> * **數字預設跟隨文字語言：** 移除 Unicode 偵測面板的「偵測語言時忽略數字」選項。數字語言新增「跟隨當前文字語言」（預設：數字以前後文字的語言朗讀）與「跟隨文件主要語言」（數字以主要語言朗讀）。先前版本在未勾選該選項時以主要語言朗讀數字；若要維持，請選擇「跟隨文件主要語言」。
> * **全形與其他 Unicode 數字視為數字：** 數字語言、數字模式、數字停頓與千分位規則現在也適用於全形數字與其他 Unicode 十進位數字，例如阿拉伯-印度數字。

## 10. Risks

- **The default changes for every user** (goal 3). Most audible in mixed Chinese/English text with numbers. The changelog says how to get the old behavior back.
- **Symbol names under "Follow current text language" in number or group mode.** Names are looked up in the language in force before detection (`pipeline:330`, `:343`). Detection later moves the digits to the text's language, but a name in another script can switch the voice mid-number. With a Chinese main voice and English text, `abc 12.5` is read `1`, `2` in English, then "點" and `5` in Chinese. Ignore-on users have this today, and value mode (the default number mode) has no names. Decided by the user (2026-10-23): accept, record it, and check it by hand (M5). §13 Q4 lists the alternatives.
- The wrapping adds commands to every utterance that has a number, while detection is on and the value is not "default"; the rejoin removes those that keep the voice. The cost is one regex scan per text item, the same as the early stage, and one dedupe pass.
- ~~`STAGES` grows to ten.~~ Not after the revision of §4.4: `STAGES` is unchanged.
- `\d` instead of `[0-9]` widens three regexes. The Hypothesis properties in `tests/test_pipeline_pause_properties.py` use ASCII alphabets (`:226`, `:257`, `:280`, `:300`, `:333`, `:364`, `:465`, `:484`, `:641`). Without new alphabets they would not exercise the change, and mutmut would report the `\d` literals as surviving.

## 11. Test plan

Work order:

1. Characterization (green on the baseline).
2. Red tests per goal.
3. Implementation in this order: digit set (§6.2) → detector (§6.3) → setting removal (§7.2) → values and choices (§4.1, §4.5) → late stage (§4.4) → spelling (§5) → validation (§7.1) → panel (§3).
4. Strings and readmes.

Each red test must fail on the baseline for the stated reason.

### 11.1 Characterization (must pass before and after)

- The speak-level harness (`tests/test_worldvoice_speak.py:_synth`, extended with the stage list run in front of `speak()` for timing "before", as the prototype did):
  - **"Follow" equals today's ignore-on:** T4 and its "after" variant; `中 12. Next` and `Total. 12` under value mode with punctuation pause on (the break positions are part of the expectation);
  - **detection off:** for `"default"` and a specific locale, the voices and breaks for `中12`, `Total. 12` and `12. Next` are unchanged (T3; only Option B digits may differ, §11.2);
  - **other synths:** with `supports_roles` False, both number-language stages leave no `WVLangChangeCommand` (T9).
- **Pipeline:** the existing tests of `inject_number_language` with a specific locale and detection off (`tests/test_pipeline_stages.py`, `tests/test_pipeline_filters.py`) stay green unchanged.
- **Detector:** every existing test that does not mention digits stays green, including the phase 33 properties (`tests/test_language_detector.py:543-606`).

### 11.2 Red tests

**Goal 1 / §4: "main" equals today's ignore-off.**

Build each expected value on the baseline with ignore off and number language "default". The voices must match after the change with "main":

- T1, T2, T5, T8 (number mode);
- `Total. 12`: the punctuation break before `12` stays (the §4.3 trap);
- `中 12. Next`: the dot-rule space stays.

Signs, `²` and the §4.7 cases are listed as deliberate exceptions, each with its own expectation.

**§4.2 second trap.** T6 with timing "before" and with timing "after": `123` is read by the Chinese voice.

**Wrapping unit tests** (`tests/test_pipeline_stages.py`):

- nothing wrapped for `"default"` and for `supports_roles` False;
- wraps every match in value, number and group mode;
- tracks `LangChangeCommand(None)` back to `ctx.language`;
- after detection, wrappers that keep the voice are removed and their item joins again; nothing joins across two items or another command; NVDA's `LangChangeCommand`s stay.

**C1 (batch 1 review).** With NVDA's real `characterProcessing` run on each item after the filters, `COVID-19 cases`, `the 1st item`, `in 2024!`, `Is it 5?` (English main voice) and `第1名` (Chinese main voice) reach NVDA whole under "main" and under the main voice's own locale, in both timings.

**§4.5.** `inject_number_mode` with `"main"` names symbols in the language in force (`full stop en`, not unnamed).

**Goal 2 / §7.2.**

- `DETECTION_CONFSPEC` has four keys;
- `DetectionSettings` has no `ignore_numbers`;
- `update(ignore_numbers=True)` raises `TypeError` and writes nothing;
- `get()` on a section that still holds `ignoreNumbersInLanguageDetection` succeeds;
- the Unicode Detection panel's labels are the four remaining controls, in order (`tests/test_unicode_panel.py:79-88`);
- static guard: the string `ignoreNumbersInLanguageDetection` appears nowhere under `addon/` or in any readme.

**Goal 4 / §7.1.**

- `_set_numlan("zz")` stores `"default"` and logs once;
- `_set_numlan("main")` and a listed locale are kept;
- `availableNumlans` starts with `("default", "Follow current text language")`, `("main", "Follow document main language")`.

**Goal 5 / §6.3.**

- `中1` → `<zh_TW> '中1'` whatever the stored settings;
- `abc ١٢٣` with an Arabic voice installed → no command before `١٢٣`;
- `[Lang("de_DE"), "hallo 12"]` → `12` stays with `hallo`'s run.

**§5 spelling.** The three examples of §5; the unavailable-locale fallback; one number-language read per call.

**Goal 7 / §6.2.** `NUMBER_RE` on:

- `１２` → `["１２"]`, replacing the "Digits are ASCII only" expectation (`tests/test_pipeline_filters.py:139-140`);
- `٣٫١٤` → `["٣", "١٤"]`;
- `x²` → `[]`;
- `①` → `[]`;
- `１２,３４５` thousands-stripped in value mode;
- `１２３４５` in group mode with size 3 → `１２３`, `４５` (original characters);
- `１ ２` gets a number pause.

### 11.3 Existing expectations that change

The prototype run of the full suite (25 failures, of which 5 hygiene failures are artifacts of the scratch copy) names these:

- `tests/test_detection_settings.py`: the five-key reads, writes, notifications and confspec (`:37`, `:53`, `:69-71`, `:79`, `:89`, `:97-100`, `:126`, `:143`);
- `tests/test_language_detector.py`:
  - the preference map entry (`:40`);
  - `digits-to-base` and `digits-ignored` (`:105-119`), `digits-ignored` and `digits-return-to-it` (`:160-187`);
  - `test_digits_follow_the_ignore_numbers_setting` (`:345-355`), replaced by the goal 5 tests;
  - `:423`, `:496`, `:558`;
- `tests/test_unicode_panel.py`: the switching fixture and label list (`:37`, `:79-88`, `:106`);
- `tests/test_pipeline_filters.py:139-140`: full-width digits are numbers;
- `tests/test_worldvoice_speak.py:237-248`: the number-language display names;
- `tests/test_driver_ui_hooks.py:87`: the changed-field set no longer names `ignore_numbers`.

### 11.4 Property tests (Hypothesis)

Alphabets gain full-width, Arabic-Indic, Extended Arabic-Indic and Devanagari digits plus `²`, `①` and `٫`.

1. **Digit coverage.** Every Nd character lies inside a `NUMBER_RE` match. No `²`, `①`, letter or whitespace does.
2. **Pieces keep their characters.** In number and group mode, the concatenated decimal characters of the output equal those of the input, code point for code point, and no `\d+` run in an output item is longer than the size (generalizes `tests/test_pipeline_pause_properties.py:333`).
3. **Thousands.** The oracle at `tests/test_pipeline_pause_properties.py:465` is generalized to `\d`.
4. **Detector.** No `WVLangChangeCommand` that detection inserts is directly followed by text whose first character is a decimal digit (digits never start a run). With the phase 33 scenarios, `ignore_numbers` is dropped from the drawn preferences.
5. **End to end, per value**, with random mixed Latin/Han/digit/space text, random base among the installed voices, detection on and both timings. Expected voice for each decimal digit:
   - "default": the voice of the nearest preceding non-digit, non-Common character's run, or the base at the start;
   - "main": the base's voice;
   - a locale: that locale's voice.

   Signs are excluded from the check (§4.7).
6. **Spelling.** For random text, locale and number language, every digit's run carries the language §5 names.

### 11.5 Mutation testing

- Run mutmut on `pipeline/numbers.py`, `pipeline/__init__.py` and `languageDetection/__init__.py` (all already in `[tool.mutmut] source_paths`, `pyproject.toml:45-58`). Add `numberLanguage.py` only if it holds logic beyond the two constants.
- At most 3 workers, with a watchdog that stops pytest when MemAvailable falls below 3 GB (`DEVELOPMENT_WORKFLOW.md` §8).
- Record every surviving mutant and its reason in the implementation notes. Expected equivalent survivors:
  - the `NUMBER_RE` sign lookbehind (documented at `numbers:16-18`);
  - the `\d` lookbehind of `THOUSANDS_RE`, if the oracle cannot tell it apart.

### 11.6 Verification (`DEVELOPMENT_WORKFLOW.md` §7)

- Full suite, compared with 2413 passed, 0 skipped, 0 warnings.
- `prek run --all-files`.
- `git diff --check`.
- Both protected-path checks empty.
- `msgfmt --check` on the zh_TW catalog.

### 11.7 Windows / NVDA manual items

None of these is verified on Linux. Report them as not done until someone checks them.

1. **M1.** Voice panel: "Number language" lists "Follow current text language" (selected on a fresh profile) and "Follow document main language" first. NVDA reads the selected item when the combo box gains focus. The settings ring steps through the same order.
2. **M2.** A profile with `numlan = zz` written by hand loads without errors. The combo box shows "Follow current text language", the ring entry can be changed without an error, and saving the Voice panel writes `default`.
3. **M3** (decided by the user, 2026-10-23). With VE, OneCore and eSpeak voices, group mode with size 3:
   - `１２３４５` is read as numbers ("one hundred twenty-three", "forty-five"), with NVDA's Unicode normalization on and off;
   - number mode `٣٤` with an Arabic voice.
4. **M4.** Main voice English, Chinese voice installed, detection on:
   - `中文 12` under "Follow current text language" is read by the Chinese voice;
   - under "Follow document main language", by the English voice;
   - repeat with detection timed "before".
5. **M5.** Number mode, Chinese main voice, "Follow current text language", `abc 12.5`: record which voice reads "點" and `5` (§10 known limitation).
6. **M6.** Unicode Detection panel: no "Ignore numbers" checkbox; Tab order starts at "Language assumed for latin characters:". A profile that still holds `ignoreNumbersInLanguageDetection = True` opens without errors, and the key stays in the file after saving.
7. **M7.** Spelling (NVDA+numpad 2 twice, or by character) of `中1` with "trust voice's language" on: under "Follow current text language" both characters use Chinese descriptions; under "Follow document main language", `1` uses the spelling locale.

## 12. Findings worth knowing before the plan

- **F1. The stage dedupe hides two traps** (§4.2): it drops every "main" wrapper and, for a specific locale that maps to the voice in force, every wrapper too. Both were invisible while detection sent bare digits to the base.
- **F2. Wrappers in the middle of the pipeline change pauses** (§4.3). Today, a specific number language whose voice differs already loses the punctuation pause in `Total. 12` and the dot-rule space in `12. Next`. This phase leaves that alone.
- **F3. An invalid stored number language breaks the settings ring today** (§7.1): `None + step` in `synthSettingsRing.py:38-41`. The setter validation fixes it.
- **F4. Most non-ASCII decimal digits are not Common script** (§6.3). The detector needs an explicit `isdecimal()` pass-through, not just the removal of its digit branch.
- **F5. `str.isdigit()`, today's detector test, accepts 128 characters that are not decimal digits** (`²`, `①`, Ethiopic numerals), so the detector and the pipeline disagreed even before Option B.
- **F6. NVDA normalizes full-width digits to ASCII by default** after the WorldVoice filters (§6.4). Arabic-Indic digits pass through unchanged.
- **F7. Spelled digits already go through the pipeline** (`speakSpelling` → `speak()`), so the number language already picked their voice. Only the description locale came from `process_for_spelling`.
- **F8. The punctuation stage already used Unicode `\d`** (`pipeline:427`), so it is the one number rule that needs no change.

## 13. Open questions and the defaults applied

- **Q1. Late stage instead of "no stage dedupe for main"** (§4.3, §4.4). Default: the late stage. Decided by the user (2026-10-23). Alternative: wrap early without dedupe and make number-language wrappers transparent in the punctuation stage and in the dot rule. That touches two more stages and also changes specific-locale output.
- **Q2. Specific locales now always win under detection, even with the voice in force** (§4.2, T6). Default: yes. Without it, goal 5 would make those digits follow the text. Decided by the user (2026-10-23).
- **Q3. The timing "after" differences under NVDA's own language handling** (§4.7 item 3). Default: accept and record. Decided by the user (2026-10-23). No longer applies after the revision of §4.4 (the wrapping sees the same commands as detection). Alternative: the pipeline emits a "base language" marker that detection resolves to its own base, which is exact but puts part of "main" back into the detector (against goal 6).
- **Q4. Symbol names under "Follow" in number and group mode** (§10). Default: accept, as ignore-on users have it today. Decided by the user (2026-10-23). Alternatives for a later phase:
  - leave symbols unnamed under "Follow";
  - name them after detection (a new stage after detection, possible only for timing "after").
- **Q5. Signs, hyphens and superscripts under "main"** (§4.7 items 1-2). Default: accept. Decided by the user (2026-10-23).
- **Q6. Separators next to non-ASCII digits** (§6.2). Default: unchanged Latin-1 separators (user decision Q2 of 2026-10-22), so `１２．５` and `٣٫١٤` are two numbers each. Decided by the user (2026-10-23). Alternative: add the full-width forms of the Latin-1 symbols and `٫` `٬`. That reverses Q2 for `12，34` (a common Chinese list separator), so it is not recommended.
- **Q7. Where an invalid number language is caught** (§7.1). Default: in `_set_numlan`, against the current choices. Decided by the user (2026-10-23). Alternative: map it at read time in `speech_context()`. That keeps the stored value, but the ring stays broken.
- **Q8. Changelog location and heading** (§9). Default: a new "Next update" section in the English and zh_TW readmes; `buildVars.py` untouched. Decided by the user (2026-10-23).
- **Q9. Readme scope** (§9). Default: the bullet and intro changes in all six; the number language bullet rewritten in English and zh_TW only. Decided by the user (2026-10-23).
- **Q10. Spelling with a number-language locale that has no voice** (§5). Default: the spelling locale. Decided by the user (2026-10-23).
- **Q11. Where the wrapping for detection runs** (§4.4 revision, batch 1 review C1). Default: right before detection (as NVDA's filter for timing "before", in `speak()` for timing "after"), with redundant wrappers removed and their items joined again. Decided by orchestrator with the recommended default; user may override before merge.

Decided by the user (2026-10-23):

- goals 1-7 (§2.1);
- digit set = Nd (§6.1);
- original characters in pieces (§6.4);
- spelling follows the number language (§5);
- the ignore bullet removed from all six readmes;
- a changelog note.
