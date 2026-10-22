# Unify number reading: one number definition, an "off" mode, value-mode thousands separators

Date: 2026-10-22.
Base: `master` `967944e`. Branch: `feat/number-unify`. Worktree: `/workspace/WorldVoice-feat-number-unify`.
Flow: normal flow (`DEVELOPMENT_WORKFLOW.md` section 3). Section 15 explains why the complex flow is not needed.
Status: every rule in section 2 was decided by the user in the discussion of 2026-10-22 and is not reopened here. Section 13 lists facts found while writing this spec that the user should see before merge. Section 14 lists the new open questions, each adopted with a conservative default.

All `file:line` references are to `967944e`. NVDA references are to `ref/nvda` at `7d25bc76e`. Sections 5.2, 7 and 12 were checked against a scratch prototype (section 16).

Notation used throughout:

- **NB** is `NumberBreakCommand(settings.scaled_number_wait())`.
- **⟦x⟧** is `CharacterModeCommand(True)`, `"x"`, `CharacterModeCommand(False)`.
- **‹en›** is `WVLangChangeCommand("en")`.
- **SYM** is one character of Unicode category P* or S* with a code point in U+0000..U+00FF.

## 1. Problem

- **Four definitions of "number".** The number language, the number modes and the number pause all use `_NUMBER_RE = [+-]?[0-9]+(?:\.[0-9]+)?` (`pipeline/__init__.py:33`). The ignore-comma stage uses `(?<=[0-9]),(?=[0-9])` (`:31`). `_PURE_NUMBER_RE` (`:32`) is a fourth, unused one. `"12,345"`, `"5-3"`, `"12:30"` and `"192.168.0.1"` are therefore cut into several "numbers" with the symbols left between them.
- **Digit and group mode glue digits across symbols.**
  - Digit mode puts a break only between two adjacent digits (`:386-394`). `"12,345"` becomes `"1"`, NB, `"2,3"`, NB, `"4"`, NB, `"5"`, so `"2,3"` reaches the synth as one item.
  - Group mode reads any number with a `"."` as a whole value (`:369-371`). It groups only `[+-]?[0-9]+`, so `"2026-10-22"` gives `"202"`, break, `"6-10-22 12:30"`.
- **Group mode has its own pause** (`group_wait_factor`, `settings.py:181-190`; `GroupNumberBreakCommand`, `pipeline/__init__.py:41-42`), separate from the number pause that digit mode uses.
- **"Ignore commas between numbers"** (`settings.py:132-141`) removes every comma between two digits (`pipeline/__init__.py:101-109`), so `"3,14"` (a European decimal) becomes `"314"`. It is off by default. For other synthesizers with scope "all" it is also tied to the global wait factor (`settings.py:346-349`).
- **No way to leave numbers alone.** Every mode rewrites numbers in some way.
- **No number pause while a number language is active.** `"1 2"` reaches the number-pause stage as `"1"`, ‹en›, ‹zh›, `"2"`, which is not two adjacent numbers. This was F4 of `docs/superpowers/specs/2026-10-21-feat-number-and-punctuation-pause-design.md:501`.

## 2. Decisions

All are **Decided by the user (2026-10-22)** except V5.

- **Q1.** A number is `\d+(?:[SYM]*\d+)*`. Each digit run is grouped from the LEFT by the group size. Symbols are spoken in character mode. Breaks go between groups and around symbols.
- **Q2.** SYM is Unicode category P* or S* with a code point in U+0000..U+00FF (option A). It never includes whitespace or letters. Full-width and CJK punctuation are not SYM.
- **Q3 (option A).**
  - A `+` or `-` directly before a digit and not preceded by a digit is a sign. It is spoken with the first group: `"-12"` is "minus twelve".
  - A `+` or `-` after a digit is a symbol.
- **Q4 (option A).** A symbol is sent as ⟦x⟧. The result depends on NVDA's symbol level and the engine, and is to be verified on Windows (section 13, F1).
- **Q5.** Every break inside a match is NB, the same pause as between space-separated numbers.
- **Q6.** The digit translate table (`get_translate_table`) is no longer applied in any mode.
- **Q7.**
  - The dropdown keeps "number", which is group size 1 internally.
  - "group" has sizes 2..10, default 3.
  - A stored `group_size = 1` clamps to 2.
- **Remove the group wait setting entirely, with no migration:** `group_wait_factor`, driver id `groupwaitfactor`, `scaled_group_wait`, `GROUP_WAIT_UNIT_MS`, `GroupNumberBreakCommand`, its panel and ring controls, and its msgids.
- **Value mode is otherwise unchanged.**
- **V1.** Value mode removes thousands-separator commas only when the whole comma/digit run is valid: groups of three counted from the right, and a leftmost group of 1–3 digits. Otherwise the run is unchanged. The de/fr risk that `"1,234"` means a decimal is accepted.
- **V2 (option A).** Only value mode removes thousands commas. Number and group modes treat `","` as a symbol.
- **V3.** "none" skips number-mode processing and thousands removal only. Number-language wrapping and the number pause still apply.
- **V4.** `depends_on` is not extended. Group size is enabled only while the mode is "group" (existing rule). Number language and number wait stay enabled.
- **V5.** Value `"none"`, label `"off"` (zh_TW 不處理), first in the list: off, value, number, group. The default stays value. **Decided by orchestrator with the recommended default; user may override before merge.**
- **V6.** Drop the scope-"all" global-wait coupling (`settings.py:347-349`). With scope "all", other synthesizers get value-mode removal regardless of the global wait. With scope "WorldVoice", the stages are not registered for other synthesizers (`pipeline/scope.py:52`), as today.
- **V7.** Thousands removal has no separate log stage or label. It is part of value-mode number processing and is logged under the `number_mode` switch, but it runs before `number_language` internally.
- **Remove "Ignore commas between numbers" with no migration:** the setting, driver id `cni`, panel controls, ring entry, log switch, msgids, and `_COMMA_NUMBER_RE` with its stage.
- **L1.** Number-language detection (`inject_number_language` / `iter_number_speech_segments_language`) uses the same regex, with the sign rule.
- **N (option A).** The number-pause split (`_split_numbers` / `_split_spaced_numbers`, `:210-250`) and `_both_numbers` (`:157-163`) use the same regex.
- **O (option A).**
  - The `STAGES` order stays: `number_language` before `number_mode`, and `number_wait_factor` last but one.
  - `number_wait_factor` treats `LangChangeCommand` and `WVLangChangeCommand` as transparent and puts the break between the language commands. This fixes the old F4.
- **P.** Every batch review of this feature uses Fable 5.1, not Opus. The final whole-branch review is Fable 5.1 as usual.

## 3. Goals and non-goals

Goals:

- **One number definition (`_NUMBER_RE`)** shared by `number_language`, `number_mode`, the number-pause split and `_both_numbers` (Q1–Q3, L1, N).
- **Number and group modes** as one algorithm with a size: 1 for "number", 2..10 for "group". Every break is NB. Every symbol is ⟦x⟧ (Q1, Q4–Q7).
- **A new "off" mode** (V3, V5).
- **Value mode:**
  - removes thousands separators from fully valid runs (V1, V2, V7);
  - is otherwise unchanged (section 13, F3, lists what the shared regex itself changes).
- **Removals.** The group wait setting and the ignore-comma option are removed, with no migration.
- **Number pause with a number language.** The pause now works while a number language is active (O).

Non-goals:

- **Language detection.** Its own digit test (`languageDetection/__init__.py:129`, `:178`, `character.isdigit()`) is a different feature and keeps it.
- **Stage order.** It does not change (O).
- **Full-width and CJK punctuation** (`，`, `．`, `：`) are not symbols (Q2), so `"12，34"` is two numbers.
- **Old specs and plans** are not edited.
- **Readmes other than English and zh_TW** are left to translators.

## 4. Current behaviour (verified)

- **Regexes** (`pipeline/__init__.py:31-36`):
  - `_COMMA_NUMBER_RE`, `_PURE_NUMBER_RE` (unused anywhere; `grep` finds only its definition), `_NUMBER_RE`, `_CH_SPACE_RE`, and `_NO_BREAK_SPACES`.
  - `_SENTENCE_END_RE` (`:38`) is also unused. It is outside this feature.
- **Stages** (`STAGES`, `:837-847`), in order: `apply_speech_dictionaries`, `ignore_comma_between_number`, `number_language`, `number_mode`, `chinesespace_wait_factor`, `item_wait_factor`, `punctuation_wait_factor`, `number_wait_factor`, `speech_viewer`. Each stage handler calls `_run_logged(log_key, ...)` (`:805-817`, `:776-793`). For other synthesizers it replaces `BreakCommand` subclasses with plain breaks (`_plain_breaks`, `:796-802`).
- **Number language** (`inject_number_language`, `:335-351`). With `ctx.number_language == "default"` the sequence passes through (`:342-348`). Otherwise `_insert_WVLangChangeCommand_between_number` (`:284-310`) wraps every `_NUMBER_RE` match as ‹num› match ‹current› (`:313-332`). It then runs `deduplicate_language_command(..., start_language=current_lang)` and `merge_consecutive_strings`.
- **Number mode** (`inject_number_mode`, `:397-422`; `iter_number_speech_segments_mode`, `:425-455`; `_translate_number`, `:354-394`):
  - value yields the match as is;
  - group: see section 1;
  - number: see section 1. Each digit also goes through `get_translate_table` (`:84-93`).
  - A `"."` right after or right before a match gets a space (`:434-445`): the "dot rule".
- **Number pause** (`number_wait_factor`, `:253-272`):
  - drops blank items and strips the others (`_remove_space`, `:180-202`);
  - splits numbers that only whitespace without a no-break space separates (`_split_spaced_numbers`, `:210-242`). Numbers glued with an empty gap are never split: `glued` at `:223`, the earlier spec's F1 option B;
  - puts NB between two adjacent items that each fullmatch `_NUMBER_RE` (`_insert_between` with `_both_numbers`, `:124-138`, `:157-163`).
- **Settings table** (`settings.py:109-270`):
  - `ignore_comma_between_number` (`:132-141`, `cni`, `ring=False`);
  - `number_language` ordering-only (`:143-155`);
  - `number_mode` (`:156-168`), with choices at `:45-53` and normalisation to "value" at `:59-61`;
  - `group_size` (`:170-180`, min 1, max 10, `depends_on=("number_mode", "group")`);
  - `group_wait_factor` (`:181-190`, `depends_on` group);
  - `number_wait_factor` (`:191-199`).
- **Effective settings.** `PipelineSettings.effective` (`:325-349`) drops pauses and ignore-comma for other synthesizers when scope is not "all". For scope "all" it ties ignore-comma to the global wait units (`:346-349`).
- **Driver settings, ring and panels are all table driven.**
  - Synth settings: `WorldVoice/__init__.py:102-123`, `:499-501`.
  - Number-mode values: `availableNummods`, `:475-476`.
  - Panel controls: `pipelineControls.py:52-58`; the spin range is `min_value..max_value`.
  - Voice panel followers: `panelLayout.py:95-113`.
- **Log switches** come from `STAGES`: the confspec at `WorldVoice/__init__.py:74-77`, labels at `speechSettingsDialog.py:38-59`, and the Log Record panel at `:665-671`.
- **`ctx.speech_symbols`** (`pipeline/context.py:15`, set at `WorldVoice/__init__.py:365`) is read only by `get_translate_table`. The synth's `speechSymbols` object itself stays, because language detection uses it (`WorldVoice/__init__.py:268-273`).

## 5. NVDA facts relied on

### 5.1 Where the pipeline runs

- **The pipeline runs before symbol processing.**
  - `speech.speak` runs `filter_speechSequence.apply` first (`ref/nvda/source/speech/speech.py:1137`). WorldVoice's stages are filters on it.
  - Speech Viewer is fed right after (`:1147`). It joins the text items with two spaces (`speechViewer.py:180`, `:199`), so it shows the pipeline's items before symbol processing: `123  .  456`.
  - Empty strings are dropped (`:1196`).
  - Then every string goes through `processText` (`:1215-1232`): speech dictionaries, then `characterProcessing.processSpeechSymbols(locale, text, symbolLevel)`, then strip (`:192-214`). This happens **also inside character mode**. Character mode only skips the trailing `CHUNK_SEPARATOR` (`:1231-1232`).
  - The locale is NVDA's current language. `WVLangChangeCommand` derives from `SynthParamCommand`, not `LangChangeCommand` (`_speechcommand.py:4`), so the number language never changes the symbol locale.
- **Symbol rules are context sensitive** (`characterProcessing.py:599-637`).
  - **Complex symbols** need neighbours in the same string: "decimal point" `(?<![^\d -])\.(?=\d)` (level none, kept) and "negative number" `(?<!\w)[-−](?=[$£€¥.]?\d)` (replaced by "minus" or "負", level none). See `locale/en/symbols.dic:17-19`, `:31-33` and `locale/zh_TW/symbols.dic:19-21`, `:33-35`.
  - **A symbol alone in its own item** loses those neighbours and falls back to its simple entry.
- **Default symbol level.** It is "some" (`config/configSpec.py:38`, `integer(default=100)`; `SymbolLevel.SOME = 100`, `characterProcessing.py:160`).

### 5.2 An isolated symbol through NVDA's real `processText` (scratch run)

NVDA's own `characterProcessing.py` was loaded with stubs and run over `ref/nvda/source/locale/*/symbols.dic` and `cldr.dic` (section 16).

| Symbol | en: none / some / most / all | zh_TW at "some" | Spelling name (`processSpeechSymbol`) |
| --- | --- | --- | --- |
| `.` | `""` / `dot` / `dot` / `dot` | `dot` | `dot` |
| `,` | `,` / `,` / `,` / `comma,` | `,` | `comma` |
| `-` | `-` / `-` / `dash-` / `dash-` | `-` | `dash` |
| `:` | `:` / `:` / `colon` / `colon` | `:` | `colon` |
| `+` | `""` / `plus` / `plus` / `plus` | `plus` | `plus` |
| `/` | `""` / `slash` / `slash` / `slash` | `slash` | `slash` |
| `×` | `""` / `times` / `times` / `times` | `乘以` | `times` / `乘以` |
| `÷` | `""` / `divide by` / … | `除以` | |
| `°` | `""` / `degrees` / … | `度` | |
| `'` | `""` / `""` / `""` / `tick` | | |

For comparison, whole strings at "some": `"-12"` gives `minus 12` (zh_TW `負 12`), `"12.5"` and `"192.168.0.1"` are unchanged (decimal point), `"5-3"` is unchanged, and `"2×3"` gives `2 times 3`.

So within ⟦x⟧, at the default level:

- `,`, `-` and `:` reach the engine as the character itself;
- most other symbols reach it as a **word**, and character mode then asks the engine to spell that word (section 5.3);
- at level "none", `.` `+` `/` `×` `÷` `°` become an empty string and are silent.

This is finding F1 (section 13).

### 5.3 How NVDA itself uses character mode

- **Spelling.** NVDA first replaces a character by its symbol name (`speech.py:517-518`). It wraps an item in character mode only when the item is one character long (`_getSpellingSpeechAddCharMode`, `:367-386`). It does this only if the synth supports `CharacterModeCommand` and "Use spelling functionality" is on (`:638-642`).
- **Key names** do the same (`speech/shortcutKeys.py:78-83`, `:95-106`). MathCAT wraps single characters (`mathPres/MathCAT/speech.py:89`).
- **NVDA never sends a multi-letter word in character mode.** The engines spell whatever is inside:
  - eSpeak: `<say-as interpret-as="characters">` (`synthDrivers/espeak.py:198-199`);
  - SAPI5: `<spell>` (`sapi5.py:919-925`);
  - SSML engines: `say-as characters` (`speechXml.py:296-300`).
- **The speech manager passes character mode through.** `CharacterModeCommand` is a `SynthParamCommand` with `isDefault = not state` (`speech/commands.py:153-167`). The speech manager tracks it (`speech/manager.py:366-370`) and replays a non-default one after an utterance split (`:293-310`). The pipeline always closes ⟦ with ⟧ inside one match, with no `EndUtteranceCommand` between, so nothing is replayed.

## 6. Design

### 6.1 The number definition (Q1–Q3, L1, N)

In `pipeline/__init__.py`, replacing `_COMMA_NUMBER_RE`, `_PURE_NUMBER_RE` and the old `_NUMBER_RE`:

```python
_SYMBOLS = "".join(c for c in map(chr, range(0x100)) if unicodedata.category(c)[0] in "PS")
_SYMBOL_CLASS = f"[{re.escape(_SYMBOLS)}]"
_NUMBER_RE = re.compile(rf"(?:(?<![0-9])[+-])?[0-9]+(?:{_SYMBOL_CLASS}+[0-9]+)*")
```

- **The symbol set.** `_SYMBOLS` is ``!"#$%&'()*+,-./:;<=>?@[\]^_`{|}~¡¢£¤¥¦§¨©«¬®¯°±´¶·¸»¿×÷`` (computed in the prototype).
  - Whitespace (including U+00A0) is category Z. U+00AD is Cf. `ª º µ` are letters. `² ³ ¹ ¼ ½ ¾` are No. None of these is SYM.
- **Digits.** "Digit" means ASCII `0-9`, as `_NUMBER_RE` has today. Python's `\d` on `str` also matches full-width and other Unicode decimal digits. See F4 and Q-A.
- **Same strings, no backtracking blow-up.**
  - `[SYM]+` inside the repetition matches exactly the same strings as the decided `[SYM]*`. A run of digits with no symbol is already taken by the greedy `[0-9]+`.
  - It avoids the `(a+)+` shape, which backtracks exponentially when `fullmatch` fails, for example `"1"*5000 + "a"`. The prototype's adversarial check runs in 2 ms.
- **The sign.** `(?<![0-9])[+-]` encodes Q3. A `+` or `-` after a digit can only be taken as a symbol inside the repetition.
- **Users of `_NUMBER_RE`:**
  - `iter_number_speech_segments_language` (L1);
  - `iter_number_speech_segments_mode` (number modes);
  - `_split_spaced_numbers` and `_both_numbers` (N).
- **The earlier F1 ("glued" numbers, option B) can no longer happen.**
  - A match ends with a digit. The next match starts with a digit or a sign.
  - An empty gap would put a digit right after a digit, which the greedy `[0-9]+` forbids. It would also put a sign right after a digit, which the lookbehind forbids.
  - So every gap between matches is non-empty. `glued` (`:223`) is always empty and is removed.
  - Matches i and i+1 are split apart exactly when their gap is whitespace without a no-break space (`_is_splittable_gap`, `:205-207`, unchanged).
  - What used to be "glued" is now one number: `"02 2345-6789"` gives `"02"`, NB, `"2345-6789"`; `"3-1 2"` gives `"3-1"`, NB, `"2"`.

### 6.2 Number modes (V3, V5, Q7)

`NUMBER_MODE_CHOICES` (`settings.py:46-53`) becomes, in this order:

| Value | Label (msgid) | zh_TW | Meaning |
| --- | --- | --- | --- |
| `none` | `off` (new) | 不處理 | No number-mode processing, no thousands removal |
| `value` | `value` | 數值 | Default. Thousands removal, the dot rule, and the match kept as is |
| `number` | `number` | 數字 | Group size 1 |
| `group` | `group` | 群組 | Group size `settings.group_size` (2..10) |

- **Translator comment** for "off": `# Translators: A number mode: numbers are left as they are.`
- **Normalisation.** `NUMBER_MODES` and `_number_mode` (`:56-61`) follow automatically. An unknown stored value still reads as "value".
- **The ring and both panels** get "off" first, through `availableNummods` (`WorldVoice/__init__.py:475-476`) and the choice control.
- **"none" in the stages:**
  - `inject_number_mode` returns the sequence unchanged. The dot rule does not run either: it is number-mode processing.
  - The thousands step (6.3) passes through.

### 6.3 Value mode: thousands separators (V1, V2, V7)

```python
_THOUSANDS_RE = re.compile(r"(?<![0-9,])[0-9]{1,3}(?:,[0-9]{3})+(?!,*[0-9])")
```

- **The lookahead.** The decision text gives `(?![\d]|,\d)` as an example. That example removes the commas of `"1,234"` inside `"1,234,,5"`, whose whole run is not valid. A Hypothesis comparison against a whole-run oracle found this (F5).
  - `(?!,*[0-9])` follows the decided rule ("the WHOLE comma/digit run is valid"). Its output equals the oracle on 3,000 examples.
  - The oracle: take each maximal `[0-9,]+` run, drop its trailing commas, and remove the commas only when the rest fullmatches `[0-9]{1,3}(?:,[0-9]{3})+`.
- **The new step** `remove_thousands_separators(seq, settings, ctx)`:
  - only for value mode;
  - for each `str` item: `_THOUSANDS_RE.sub(lambda m: m.group().replace(",", ""), item)`;
  - commands pass through;
  - any other mode passes the sequence through unchanged.
- **Examples** (prototype): `12,345,678`→`12345678`, `1,234.56`→`1234.56`, `-1,234`→`-1234`. These are unchanged: `1,2`, `1234,567`, `1,234,56`, `1, 234`, `3,14`, `a,1,234`, `1,234,,5`.
- **Why the step runs before `number_language` (V7).**
  - With a number language, `number_language` cuts the string at the match edges. The value step in `number_mode` would then see `"1,234"` alone.
  - The lookbehind `(?<![0-9,])` needs the character before the run. `"a,1,234"` must stay unchanged, but an isolated `"1,234"` would lose its commas.
  - Running first, on the whole item, gives the same result with or without a number language (prototype rows `a,1,234`).
- **How the step runs before `number_language` but is logged as `number_mode`.**
  - `Stage` gets a field `log_switch: bool = True`.
  - The step is registered as `Stage("number_mode", remove_thousands_separators, log_switch=False)` in the slot that `ignore_comma_between_number` leaves.
  - `_run_logged` then logs it under the `number_mode` switch: two before/after row pairs per utterance, both labelled `number_mode`.
  - A new derived tuple `LOG_SWITCHES = tuple(stage.log_key for stage in STAGES if stage.log_switch)` drives the log confspec (`WorldVoice/__init__.py:76`) and the Log Record panel (`speechSettingsDialog.py:669-671`). It keeps one switch per label, in the order of the stage that owns it: Apply speech dictionaries, Number language, Number mode, ….
  - Rejected alternatives:
    - moving `number_mode` before `number_language` (O forbids it);
    - calling the step from inside the `number_language` handler, which would log it under the wrong switch;
    - deduplicating `STAGES` by first occurrence, which would move "Number mode" above "Number language" in the Log Record panel.
- **The dot rule** (`:434-445`) is unchanged in value, number and group modes. With the shared regex it can only fire on a `"."` outside a match: `"12."` gives `"12 ."`, and `"a.5"` gives `"a. 5"`. A `"."` between digits is inside the match. Value mode keeps it, and NVDA's decimal-point rule reads it. The rule is still needed for the sentence-end case. F3 lists the value-mode change this causes for `"1.2.3"`.

### 6.4 Number and group modes (Q1, Q4–Q7)

`_translate_number(raw, mode, group_size, number_pause)`:

- `value` yields `raw`.
- `number` uses size 1 and `group` uses `group_size`. Then:
  - **Tokens.** Split `raw` with `^[+-]?[0-9]+|[0-9]+|SYM`: a leading signed digit run, further digit runs, and single symbols.
  - **Digit runs.** Cut each digit run from the left into pieces of `size`. A sign joins the first piece of the first run: `"-1234"` at size 3 gives `"-123"`, NB, `"4"`.
  - **Symbols.** Each symbol character becomes ⟦x⟧. Two adjacent symbols are two ⟦ ⟧ pairs (Q-B).
  - **Breaks.** NB goes between every two consecutive tokens or pieces. It is inserted even when the pause is 0, so the pieces reach the synth as separate items. No NB goes at the start or end of a match.
- **Decided examples (prototype):**
  - size 2: `123.456` → `"12"` NB `"3"` NB ⟦.⟧ NB `"45"` NB `"6"`;
  - `5-3` → `"5"` NB ⟦-⟧ NB `"3"`.
- **What is removed:** `GroupNumberBreakCommand`, `group_pause`, the decimal escape of group mode (`:369-371`), and `get_translate_table` with its parameter (Q6).
- **What stays the same.** `inject_number_mode` keeps its `deduplicate_language_command` (when `ctx.supports_roles`) and `merge_consecutive_strings` (`:420-422`). Text from different matches can therefore share an item when non-whitespace separates them: `"12，34"` gives `"1"` NB `"2，3"` NB `"4"`. No two digits are adjacent in such an item, and no digit run inside it exceeds the size (property P6).

### 6.5 Number pause with language commands (O, N)

`number_wait_factor` keeps `_remove_space` and `_split_numbers`. It replaces `_insert_between(..., _both_numbers, NB)` with a new helper `_insert_number_breaks(seq, break_cmd)`:

- It remembers the last item that is not a language command (`LangChangeCommand` or `WVLangChangeCommand`). Language commands since then are held.
- **When the next item comes and `_both_numbers(previous, item)` holds:** yield the first held language command, then the break, then the other held commands, then the item.
- **Otherwise:** yield the held commands, then the item.
- Held commands at the end are yielded.
- **Result.** `"1 2"` with number language en gives ‹en› `"1"` ‹zh› NB ‹en› `"2"` ‹zh› (prototype).
- **Any position inside the run sounds the same.** `inject_langchange_reorder` (`pipeline/__init__.py:714-747`, called from `WorldVoice/__init__.py:324`) moves language commands ahead of the buffered non-text commands. The audio is therefore the same for any position of the break inside the held run. "Between the language commands" is the decided, readable placement.
- **Other commands still block the pause:** a `BreakCommand` or `IndexCommand` between two numbers prevents it, as today. `item_wait_factor` is unchanged: no transparency.

### 6.6 Removed

- **`ignore_comma_between_number`:**
  - the stage (`pipeline/__init__.py:101-109`) and `_COMMA_NUMBER_RE` (`:31`);
  - the spec entry (`settings.py:132-141`) and the `PipelineSettings` field (`:283`);
  - the `effective` lines (`:336`, `:346-349`);
  - the log label (`speechSettingsDialog.py:43-44`);
  - the msgid "Ignore commas between numbers".
- **`group_wait_factor`:**
  - the spec entry (`settings.py:181-190`), the field (`:294`), `scaled_group_wait` (`:319-323`) and `GROUP_WAIT_UNIT_MS` (`:23-26`);
  - the `effective` line (`:344`);
  - `GroupNumberBreakCommand` (`pipeline/__init__.py:41-42`);
  - the msgid "Group wait factor".
- **`get_translate_table`** (`:84-93`), and `SpeechContext.speech_symbols` (`context.py:15`, `WorldVoice/__init__.py:365`), which becomes dead (Q-G).
- **`_PURE_NUMBER_RE`** (`:32`, unused): it is a second "number" definition.

### 6.7 Settings and `effective()` (V6, Q7)

- **`effective`** becomes:
  - `supports_roles` → `self`;
  - scope not "all" → `replace(self, number_wait_factor=0, item_wait_factor=0, sayall_wait_factor=0, chinesespace_wait_factor=0, punctuation_wait_factor=0, punctuation_pause_enabled=False, remove_punctuation_characters=False)`;
  - otherwise → `self`.
  - `number_mode` is not reset in the non-"all" branch, as today. That branch only runs while WorldVoice owns the registration (`scope.py:48-61`).
- **`group_size`: `min_value=2`, `max_value=10`, default 3.**
  - With `min=2` in the confspec, NVDA would validate a stored 1 on read and raise (`config/__init__.py:1269-1273`; the earlier group-mode spec F1, `2026-10-21-feat-number-group-mode-design.md:650-664`). WorldVoice would then fail to load. Q7 asks for a clamp instead (F6).
  - So `PipelineSettingSpec` gets `stored_min_value: int | None = None`, described as "the confspec's lower bound when an older range stored smaller values; `convert` raises them".
  - `confspec` uses it when set: `group_size` stays `integer(default=3,min=1,max=10)`. `convert` clamps to `min_value=2`.
  - The spin control's range is 2..10 (`pipelineControls.py:56-57`).
  - A guard check (`check_bounds`) requires `stored_min_value < min_value` when set, and only for int specs.
- **`depends_on` is unchanged (V4).** Group size depends on ("number_mode", "group"). No other entry depends on the mode.
- **Table order after the removals:** scope, global wait, number language, number mode, group size, number wait, item wait, say-all wait, Chinese space wait, punctuation pause, remove punctuation, punctuation wait, punctuation characters.
  - Number language now follows Global wait factor directly. It followed "Ignore commas" before.
  - Group size still follows Number mode on the Voice panel (`panelLayout.creation_followers`, `:95-113`).

### 6.8 Stage order and log switches

`STAGES` becomes, with order otherwise unchanged (O):

```
apply_speech_dictionaries
number_mode (remove_thousands_separators, log_switch=False)
number_language
number_mode (inject_number_mode)
chinesespace_wait_factor
item_wait_factor
punctuation_wait_factor
number_wait_factor
speech_viewer
```

`order_move_to_start_register` and the other registration helpers (`:850-873`) iterate `STAGES` and need no change. Each `Stage` binds its own handler, named after its function (`:805-833`).

## 7. What an NVDA user hears and sees

Defaults: global wait 10 and number wait 10, so NB is 10 ms; punctuation pause off. Main language zh_TW. "Number language en" means a voice is set for en.

Tables 7.1–7.3 show the pipeline output. That is what Speech Viewer shows, and what reaches NVDA's `processText`. Section 5.2 says what each ⟦x⟧ becomes: at the default level, ⟦,⟧ ⟦-⟧ ⟦:⟧ are the characters themselves, and ⟦.⟧ ⟦×⟧ ⟦÷⟧ ⟦°⟧ are words that the engine spells (F1).

### 7.1 Number language default

| Input | off | value | number | group 3 | group 2 |
| --- | --- | --- | --- | --- | --- |
| `12,345,678` | `"12,345,678"` | `"12345678"` | `"1" NB "2" NB ⟦,⟧ NB "3" NB "4" NB "5" NB ⟦,⟧ NB "6" NB "7" NB "8"` | `"12" NB ⟦,⟧ NB "345" NB ⟦,⟧ NB "678"` | `"12" NB ⟦,⟧ NB "34" NB "5" NB ⟦,⟧ NB "67" NB "8"` |
| `1,234.56` | `"1,234.56"` | `"1234.56"` | `"1" NB ⟦,⟧ NB "2" NB "3" NB "4" NB ⟦.⟧ NB "5" NB "6"` | `"1" NB ⟦,⟧ NB "234" NB ⟦.⟧ NB "56"` | `"1" NB ⟦,⟧ NB "23" NB "4" NB ⟦.⟧ NB "56"` |
| `123.456` | `"123.456"` | `"123.456"` | `"1" NB "2" NB "3" NB ⟦.⟧ NB "4" NB "5" NB "6"` | `"123" NB ⟦.⟧ NB "456"` | `"12" NB "3" NB ⟦.⟧ NB "45" NB "6"` |
| `12.5` | `"12.5"` | `"12.5"` | `"1" NB "2" NB ⟦.⟧ NB "5"` | `"12" NB ⟦.⟧ NB "5"` | `"12" NB ⟦.⟧ NB "5"` |
| `-1234` | `"-1234"` | `"-1234"` | `"-1" NB "2" NB "3" NB "4"` | `"-123" NB "4"` | `"-12" NB "34"` |
| `5-3` | `"5-3"` | `"5-3"` | `"5" NB ⟦-⟧ NB "3"` | `"5" NB ⟦-⟧ NB "3"` | `"5" NB ⟦-⟧ NB "3"` |
| `5 -3` | `"5" NB "-3"` | `"5" NB "-3"` | `"5" NB "-3"` | `"5" NB "-3"` | `"5" NB "-3"` |
| `2026-10-22 12:30` | `"2026-10-22" NB "12:30"` | `"2026-10-22" NB "12:30"` | `"2" NB "0" NB "2" NB "6" NB ⟦-⟧ NB "1" NB "0" NB ⟦-⟧ NB "2" NB "2" NB "1" NB "2" NB ⟦:⟧ NB "3" NB "0"` | `"202" NB "6" NB ⟦-⟧ NB "10" NB ⟦-⟧ NB "22" NB "12" NB ⟦:⟧ NB "30"` | `"20" NB "26" NB ⟦-⟧ NB "10" NB ⟦-⟧ NB "22" NB "12" NB ⟦:⟧ NB "30"` |
| `192.168.0.1` | `"192.168.0.1"` | `"192.168.0.1"` | `"1" NB "9" NB "2" NB ⟦.⟧ NB "1" NB "6" NB "8" NB ⟦.⟧ NB "0" NB ⟦.⟧ NB "1"` | `"192" NB ⟦.⟧ NB "168" NB ⟦.⟧ NB "0" NB ⟦.⟧ NB "1"` | `"19" NB "2" NB ⟦.⟧ NB "16" NB "8" NB ⟦.⟧ NB "0" NB ⟦.⟧ NB "1"` |
| `1 2` | `"1" NB "2"` | `"1" NB "2"` | `"1" NB "2"` | `"1" NB "2"` | `"1" NB "2"` |
| `3,14` | `"3,14"` | `"3,14"` | `"3" NB ⟦,⟧ NB "1" NB "4"` | `"3" NB ⟦,⟧ NB "14"` | `"3" NB ⟦,⟧ NB "14"` |
| `12，34` | `"12，34"` | `"12，34"` | `"1" NB "2，3" NB "4"` | `"12，34"` | `"12，34"` |
| `abc1 2def` | `"abc" "1" NB "2" "def"` | same | same | same | same |
| `2×3` | `"2×3"` | `"2×3"` | `"2" NB ⟦×⟧ NB "3"` | `"2" NB ⟦×⟧ NB "3"` | `"2" NB ⟦×⟧ NB "3"` |
| `6÷2` | `"6÷2"` | `"6÷2"` | `"6" NB ⟦÷⟧ NB "2"` | `"6" NB ⟦÷⟧ NB "2"` | `"6" NB ⟦÷⟧ NB "2"` |
| `45°30` | `"45°30"` | `"45°30"` | `"4" NB "5" NB ⟦°⟧ NB "3" NB "0"` | `"45" NB ⟦°⟧ NB "30"` | `"45" NB ⟦°⟧ NB "30"` |

In `"2026-10-22 12:30"`, number mode: the NB between `"2"` and `"1"` replaces the space. The number pause split it out of `"2 1"` (section 8, number pause).

### 7.2 Number language en (main zh_TW)

The ‹en›…‹zh› wrapper is around the whole match in every mode, including "off" (V3). The inside is as in 7.1, except where shown.

| Input | off | value | number | group 3 |
| --- | --- | --- | --- | --- |
| `12,345,678` | `‹en› "12,345,678" ‹zh›` | `‹en› "12345678" ‹zh›` | `‹en› "1" NB "2" NB ⟦,⟧ … NB "8" ‹zh›` | `‹en› "12" NB ⟦,⟧ NB "345" NB ⟦,⟧ NB "678" ‹zh›` |
| `5 -3` | `‹en› "5" ‹zh› NB ‹en› "-3" ‹zh›` | same | same | same |
| `2026-10-22 12:30` | `‹en› "2026-10-22" ‹zh› NB ‹en› "12:30" ‹zh›` | same as off | `‹en› "2" … NB "2" ‹zh› NB ‹en› "1" NB "2" NB ⟦:⟧ NB "3" NB "0" ‹zh›` | `‹en› "202" NB "6" NB ⟦-⟧ NB "10" NB ⟦-⟧ NB "22" ‹zh› NB ‹en› "12" NB ⟦:⟧ NB "30" ‹zh›` |
| `1 2` | `‹en› "1" ‹zh› NB ‹en› "2" ‹zh›` | same | same | same |
| `12，34` | `‹en› "12" ‹zh› "，" ‹en› "34" ‹zh›` | same as off | `‹en› "1" NB "2" ‹zh› "，" ‹en› "3" NB "4" ‹zh›` | same as off |
| `abc1 2def` | `"abc" ‹en› "1" ‹zh› NB ‹en› "2" ‹zh› "def"` | same | same | same |
| `-1,234` | `‹en› "-1,234" ‹zh›` | `‹en› "-1234" ‹zh›` | `‹en› "-1" NB ⟦,⟧ NB "2" NB "3" NB "4" ‹zh›` | `‹en› "-1" NB ⟦,⟧ NB "234" ‹zh›` |
| `a,1,234` | `"a," ‹en› "1,234" ‹zh›` | `"a," ‹en› "1,234" ‹zh›` (unchanged, as without a number language) | `"a," ‹en› "1" NB ⟦,⟧ NB "2" NB "3" NB "4" ‹zh›` | `"a," ‹en› "1" NB ⟦,⟧ NB "234" ‹zh›` |

Every other input in 7.1 is a single match: it gives ‹en› + the 7.1 cell + ‹zh›.

Inside the wrapper, the number-language voice speaks the symbol words. The words come from NVDA's main-language table: for example `乘以` for `×` with a zh_TW main language (F2).

### 7.3 Changes from `master` (prototype on `967944e` versus the new code)

| Input, mode | `master` | New | Why |
| --- | --- | --- | --- |
| `12,345,678`, value | `"12,345,678"` | `"12345678"` | V1 |
| `192.168.0.1`, value | `"192.168 . 0.1"` | `"192.168.0.1"` | One match; the dot rule no longer fires inside it (F3) |
| `2026-10-22 12:30`, value | `"2026-10-22 12:30"` | `"2026-10-22"` NB `"12:30"` | Earlier F1 "glued" case is now two whitespace-separated numbers |
| `12,345,678`, number | `"1" NB "2,3" NB "4" NB "5,6" NB "7" NB "8"` | see 7.1 | Q1, Q4 |
| `12.5`, group | `"12.5"` | `"12" NB ⟦.⟧ NB "5"` | Decimals are grouped too |
| `-1234`, group | `"-123"` GB(group wait) `"4"` | `"-123" NB "4"` | Group wait removed |
| `12,345,678`, value, number language en | `‹en› "12" ‹zh› "," ‹en› "345" ‹zh› "," ‹en› "678" ‹zh›` | `‹en› "12345678" ‹zh›` | One match, removal first |
| `5-3`, value, number language en | `‹en› "5" ‹zh› ‹en› "-3" ‹zh›` | `‹en› "5-3" ‹zh›` | One match: "5-3" is no longer "5", "minus 3" |
| `1 2`, any, number language en | `‹en› "1" ‹zh› ‹en› "2" ‹zh›` | adds NB | O (old F4) |

### 7.4 Settings UI

- **NVDA Voice panel (WorldVoice):**
  - The "Ignore commas between numbers" checkbox is gone.
  - The "Group wait factor" slider is gone.
  - The "Number mode" list reads "off, value, number, group" (zh_TW 不處理, 數值, 數字, 群組).
  - "Group size" is a spin box from 2 to 10, enabled only when "group" is selected.
  - Tab order follows the table (6.7): … Global wait factor, Number language, Number mode, Group size, Number wait factor, ….
- **Speech Pipeline panel:** the same removals and list. It shows the stored mode. An unknown stored mode shows "value", the normalised value, not the first entry "off".
- **Settings ring:**
  - "Group wait factor" is gone. "Ignore commas" was never in the ring (`ring=False`).
  - "Number mode" cycles off → value → number → group, and NVDA announces "Number mode off".
- **Log Record panel:** the "Ignore commas between numbers" switch is gone. "Number mode" also logs the thousands step.

## 8. Interactions

- **Punctuation pause** (`_get_punctuation_regex`, `:502-513`; `inject_punctuation_pause`, `:535-642`):
  - **A mark directly before a digit** is not a pause point. This keeps `"12.5"` and `"1,234"` intact in value mode and "off".
  - **In number and group mode** a symbol inside a match is its own item, followed by `CharacterModeCommand(False)`. A command is not "non-blank text" (`:582-583`, `:635`). So the item gets no boundary pause and is never removed, even with "remove punctuation" on.
  - The prototype property ran 3,000 examples with `.,:-` configured and removal on, and every ⟦x⟧ survived.
  - A mark after a match (`"12,"` before text) still pauses as today.
- **Item wait** (`:166-177`) breaks only between two adjacent text items. Inside a match, items are always separated by NB or a `CharacterModeCommand`, so item wait adds nothing there. The X1 property ("a number break never has another break next to it") still holds for none/value/number/group with sizes 2..10. It was checked in the prototype with `0-9 a.,-:+×，`.
- **Chinese space** (`_CH_SPACE_RE`, `:34`) needs CJK ideographs on both sides. Matches contain none, and with the translate table gone digits are never turned into `一 二` (the earlier group-mode spec's F3 no longer applies).
- **`merge_consecutive_strings` / `deduplicate_language_command`:**
  - Merging never crosses a command, so ⟦x⟧ and NB keep the pieces apart.
  - Inside `_insert_WVLangChangeCommand_between_number`, deduplication drops the wrapper when the number voice equals the current voice, and merging restores the item (`:304-310`).
  - `inject_number_mode`'s deduplication sees no language commands in its own output.
- **The dot rule:** section 6.3.
- **Number pause:**
  - `_split_spaced_numbers` also splits strings that `number_mode` merged, for example `"2 1"` from `"…22"`, `" "`, `"12…"`. The NB then replaces whitespace.
  - At number wait 0 the stage passes through (`:265-267`). `"1 2"` stays one item, but NB(0) inside a match is still inserted by `number_mode`.
- **Other synthesizers with scope "all":**
  - `_plain_breaks` turns NB into `BreakCommand` (`:796-802`). `CharacterModeCommand` is not a `BreakCommand` and passes unchanged.
  - NVDA's built-in eSpeak, OneCore, SAPI5 and SAPI4 (through the bridge, `_bridge/components/proxies/synthDriver.py:170-176`) all declare and convert it.
  - NVDA does not filter commands against `supportedCommands` in `speak` (only spelling checks, `speech.py:638-642`). A third-party synthesizer that does not handle `CharacterModeCommand` gets it anyway (F8).
- **NVDA spelling and other character-mode input.** NVDA puts only single characters in character mode (5.3). A single character can never contain a symbol between digits, so the pipeline never opens ⟦ inside an NVDA character-mode run.

## 9. Engines and layers

How `CharacterModeCommand` reaches each engine:

- **WorldVoice synth:**
  - It declares `CharacterModeCommand` (`WorldVoice/__init__.py:88-96`).
  - `speak` (`:316-330`) runs `inject_langchange_reorder`, `deduplicate_language_command` and `lang_cmd_to_voice`, which forward it.
  - `normalize_legacy_commands` passes it (`compat/commands.py:11-18`).
  - `queue_speech_sequence` adds it to the current chunk list. A `Pause` (from NB) flushes the chunks (`runtime/requestBuilder.py:35-55`). Because NB always surrounds a symbol, each ⟦x⟧ is one engine call, `[CharacterModeCommand(True), "x", CharacterModeCommand(False)]`.
  - Nothing in `runtime/` or `compat/` filters by command type.

| Engine | Path in WorldVoice | Conversion | Handles it? |
| --- | --- | --- | --- |
| OneCore | `_OneCoreStrategy.prepare` (`driver/OneCore/__init__.py:120-137`) → NVDA `_OcSsmlConverter.convertToXml` | `say-as interpret-as="characters"` (`speechXml.py:296-300`); NVDA adds `"\x1a"` after the opening command (`oneCore.py:118-137`) | Yes |
| SAPI5 | `_Sapi5Strategy.submit` → NVDA `sapi5.SynthDriver.speak` (`driver/SAPI5/__init__.py:85-90`) | `<spell>` (`sapi5.py:919-925`) | Yes |
| eSpeak | `_EspeakStrategy.submit` → NVDA `espeak.SynthDriver.speak` (`driver/Espeak/__init__.py:96-102`) | `<say-as interpret-as="characters">` (`espeak.py:198-199`) | Yes |
| RHVoice | `_RHVoiceStrategy.submit` → inner `SsmlConverter` (`driver/RHVoice/__init__.py:270-279`; `driver/RHVoice/driver/__init__.py:431-455`, declared at `:471-472`) | inherited `say-as characters` | Converted. Whether the RHVoice library honours `say-as characters` is unverified (manual item M3). |
| VE | `_VEStrategy.submit` → `_enqueue` → inner `speak` (`driver/VE/__init__.py:352-356`, `:524-535`; `driver/VE/driver/__init__.py:375-378`, declared at `:252-254`) | inline `\x1b\tn=spell\` … `\x1b\tn=normal\`. The wrapper's `_speak` joins the chunks and runs them through the chunker (`driver/VE/__init__.py:592-599`); the symbol segment is far below any limit, so it stays one piece. | Yes |
| Cerence | same as VE (`driver/Cerence/__init__.py:354`, `:526-533`, `:594-600`; `driver/Cerence/driver/__init__.py:375-378`) | same | Yes |

- **No engine drops `CharacterModeCommand`.** Every engine spells whatever text sits inside it. That makes F1 apply to all of them.
- **Scope "all":** see section 8.
- **No inner driver changes and no engine-specific code** are needed. Everything is in `pipeline/` and `pipeline/settings.py`.

## 10. Config, compatibility, strings

- **Confspec `[WorldVoice][pipeline]`:**
  - `ignore_comma_between_number` and `group_wait_factor` disappear.
  - `group_size` stays `integer(default=3,min=1,max=10)` (6.7).
  - `number_mode` stays `string(default="value")`.
- **Confspec `[WorldVoice][log]`:** the `ignore_comma_between_number` switch disappears.
- **Stale keys in existing profiles.** WorldVoice never reads them: `ConfigPipelineRepository.load` iterates the table (`settings.py:371-375`), and the log code reads only the keys of the `Stage`s. They have no effect. No migration (decided).
- **What changes for existing users:**
  - **"Ignore commas" was on** (default off). Commas of valid thousands runs are still removed in value mode. Other commas between digits are now kept: `"3,14"` stays.
  - **"Ignore commas" was off.** Value mode now removes the commas of valid thousands runs. Engines read `"12345678"` and `"12,345,678"` the same, except a de/fr voice, which may read `"1,234"` as a decimal (risk accepted in V1).
  - **Group wait > 0.** Groups are now separated by the number wait.
  - **`group_size = 1`.** It reads as 2 (`convert`). "number" is the digit-by-digit mode. The stored 1 stays in the file until the user saves another value. `PipelineSettingsService.update` writes only changed values (`settings.py:404-408`).
  - **Number mode with a translated digit table** (`unicode.dic`). Digits are now spoken by the voice itself (Q6).
- **Errors.** Nothing new can raise. The regexes are module constants. `_translate_number` works on a regex match. The clamp happens in `convert`.
- **Strings** (`addon/locale/zh_TW/LC_MESSAGES/nvda.po`):

| msgid | Change | zh_TW |
| --- | --- | --- |
| `off` | new (number mode label) | 不處理 |
| `Ignore commas between numbers` | removed (spec label and log label) | entry deleted |
| `Group wait factor` | removed | entry deleted |
| `value`, `number`, `group`, `Group size`, `Number &mode`, `Number mode` | unchanged | unchanged |

- **Catalog hygiene.** The zh_TW catalog keeps no dead msgids (`tests/test_translator_comments.py:57-80`), so both removed msgids move to `DEAD_MSGIDS`. No other locale has them (checked with `grep`).
- **Readmes.**
  - `readme.md:39`: drop "ignore commas between numbers" from the global list.
  - `readme.md:44-47`: add an "Off" bullet, describe thousands removal in numeric mode, symbols spoken separately in digit and group mode, and group size 2–10 with the pause set by the number wait.
  - `readme.md:49`: delete the "Ignore commas between numbers" bullet.
  - Same lines in `addon/doc/zh_TW/readme.md`.
  - Suggested EN wording:
    - "Off: numbers are left as they are."
    - "Numeric mode: … Commas used as thousands separators, as in "12,345,678", are removed so the number is read as one value."
    - "Digit mode: … Symbols between digits, as in "12.5" or "5-3", are read separately."
    - "Group mode: … The group size (2–10, default 3) is set in …; groups and symbols are separated by the number pause."
  - Suggested zh_TW wording:
    - 「不處理：數字保持原樣。」
    - 「數值模式：……作為千分位的逗號（例如「12,345,678」）會被移除，數字以單一數值朗讀。」
    - 「數字模式：……數字之間的符號（例如「12.5」、「5-3」）會分開讀出。」
    - 「群組模式：……每組位數（2～10，預設 3）……；組與符號之間以數字間停頓分隔。」

## 11. Test plan

### 11.1 Unit tests

- **`_NUMBER_RE`:**
  - every input of 7.1 gives the expected match list;
  - the sign rule: `"5 -3"`, `"a-3"`, `"5-3"`, `"--3"`, `"3.+4"`;
  - SYM edges: `"1\u00a02"` (U+00A0) and `"1\u00ad2"` (U+00AD) are two matches; `"1'000"`, `"1_000"` and `"1×2"` are one;
  - `"１２"` (full-width) gives no match (Q-A);
  - `fullmatch` on `"1"*5000+"a"` and `"1."*3000+"a"` within 50 ms.
- **`remove_thousands_separators`:**
  - V1's examples, plus `1,234,,5`, `a,1,234`, `1,234,` (trailing comma kept) and `1.234,567`;
  - passes through in none, number and group;
  - commands are untouched.
- **`_translate_number` / `inject_number_mode`:**
  - every number and group cell of 7.1, at sizes 2 and 3;
  - `NumberBreakCommand` instances with `time == pause` at pauses 0 and 25;
  - `CharacterModeCommand` states `(True, False)` around each symbol;
  - two adjacent symbols `1--2`;
  - "none" returns the input object sequence unchanged;
  - the dot rule `12.` / `a.5` in value, number and group.
- **`number_wait_factor`:**
  - `"1 2"` with ‹en›/‹zh› around each number gives one NB between ‹zh› and ‹en›;
  - NVDA `LangChangeCommand` is transparent too;
  - an `IndexCommand` or `BreakCommand` between numbers blocks the pause;
  - held commands at the end are kept;
  - wait 0 passes through.
- **`_split_spaced_numbers`:** the earlier F1 inputs now split (`"02 2345-6789"`, `"3-1 2"`, `"1 2 3-4"`). No-break-space gaps still never split.
- **`STAGES` and log switches:**
  - the order (6.8);
  - `LOG_SWITCHES` has no duplicates and is in panel order;
  - the confspec log keys equal `LOG_SWITCHES`;
  - the Log Record panel shows one switch per entry;
  - with the `number_mode` switch on, `_run_logged` writes rows for both `number_mode` stages.
- **Settings:**
  - `NUMBER_MODE_CHOICES` order and labels;
  - `convert` maps "none" to "none" and unknown values to "value";
  - `group_size.convert(1) == 2`, `convert(11) == 10`;
  - the confspec still reads `min=1`;
  - `effective()` for scope all and not all (no ignore-comma or group-wait fields);
  - `PIPELINE_CONFIG_KEYS`;
  - the canonical table order (6.7).
- **Panels and ring:**
  - both panels list "off" first;
  - the spin range is 2..10;
  - a stored 1 shows 2;
  - group-size enabling follows only "group";
  - no group-wait or ignore-comma controls;
  - the ring order and names (`test_settings_order.py`);
  - the Voice panel rows and tab order follow the new table.
- **Scope all:**
  - other synthesizers get only plain breaks;
  - `CharacterModeCommand` passes through;
  - NVDA's real `SsmlConverter` keeps every word and turns ⟦x⟧ into `say-as characters` (`tests/test_pipeline_nvda_ssml.py`, with the harness's `CharacterModeCommand` used by both sides).

### 11.2 Properties (Hypothesis)

Alphabets include `0-9 , . - + : / × ÷ ° % a 共 ， ． \t \u00a0 \u3000`. Every candidate below except P10 ran on the prototype (section 16). P10 is the old X1 property, updated.

- **P1, the regex equals an oracle.** A hand-written scanner implements Q1–Q3 directly: an optional sign not preceded by a digit, digits, then repeated (one or more SYM, digits). It must give the same match spans as `_NUMBER_RE.finditer`.
- **P2, no glued matches.** For any text, every gap between consecutive matches is non-empty.
- **P3, thousands oracle.** `remove_thousands_separators` equals the whole-run oracle (6.3). Only commas are removed, and only from runs the oracle accepts.
- **P4, "none" is the identity** for both number-mode stages.
- **P5, text survives.**
  - Concatenating the `str` items of `inject_number_mode` reproduces the input, except for spaces the dot rule inserts.
  - Over the whole stage list, the input minus the commas P3 removed equals the output text, comparing without whitespace: whitespace is either kept or replaced by a break.
- **P6, digits never glued.** In number and group mode, no `[0-9]+` run in any output item is longer than the size: 1 for number, `group_size` for group.
- **P7, breaks and symbols only inside a match.**
  - In number and group mode, every NB and every `CharacterModeCommand` that `number_mode` emits lies strictly inside one input match.
  - Each `CharacterModeCommand(True)` is followed by exactly one SYM item and then `CharacterModeCommand(False)`.
  - After `number_wait_factor`, every other NB replaces whitespace between two whole numbers (the existing walk property, with the wider alphabet).
- **P8, the number language changes no words or breaks.**
  - Without language commands, the items for number language en equal those for default, compared without whitespace. `_remove_space` strips the edges of the items that wrapping creates, as today.
  - NB positions are equal, relative to the numbers.
- **P9, punctuation never touches a ⟦x⟧,** with any configured marks and removal on.
- **P10, no stacked breaks** (the X1 property updated): sizes 2..10, modes none/value/number/group, symbols in the alphabet.

Existing properties to update:

- `test_property_digit_mode_separates_every_digit` and `test_property_groups_are_separate_items_of_the_chosen_size`: include symbols, drop the translate table.
- `test_property_decimals_are_unchanged_in_group_mode`: replaced by P6 and P7.
- `test_property_number_and_group_breaks_never_touch_another_break`: becomes P10.
- The F1 "glued" comments and branch in `test_property_no_text_item_keeps_two_numbers_apart_by_whitespace` (`tests/test_pipeline_pause_properties.py:313`, `:366-374`): now always false; replace with P2.
- `NUMBER_TEXT` (`:223`): widen to the alphabet above.

### 11.3 Mutation testing (mutmut)

`pyproject.toml` already lists `pipeline/__init__.py` and `pipeline/settings.py` (`:38-47`). Run mutmut on the changed functions only, following the stress-test limits:

- `remove_thousands_separators`, `_translate_number`, `iter_number_speech_segments_mode`, `inject_number_mode`;
- `_split_spaced_numbers`, `_insert_number_breaks`, `number_wait_factor`, `_both_numbers`;
- `PipelineSettingSpec.confspec`, `PipelineSettingSpec.convert`, `_number_mode`, `PipelineSettings.effective`.

Module-level regexes are not mutated by mutmut 3. P1 and P3 (oracles) cover them instead. Record every survivor and its reason in the plan's final task and in the review.

### 11.4 Translator comments

- "off" has a translator comment, enforced by adding it to a list in `tests/test_translator_comments.py`.
- "Group wait factor" leaves `GROUP_MODE_MSGIDS` (`:41`).
- "Ignore commas between numbers" leaves `CHANGED_LABEL_MSGIDS` (`:49`).
- Both join `DEAD_MSGIDS`.
- `msgfmt --check` passes on the zh_TW catalog.

### 11.5 Windows / NVDA manual items

Build a test package (`DEVELOPMENT_WORKFLOW.md` section 6). Main language zh_TW.

- **M1, symbols per engine.** For each engine: OneCore, SAPI5, eSpeak, RHVoice, VE, Cerence.
  - Use number mode and then group 3, at NVDA symbol levels none, some (default) and all.
  - Read `12.5`, `5-3`, `1,234`, `12:30`, `2×3`, `45°30`, `192.168.0.1`.
  - Record for each symbol whether it is heard as its name, spelled letter by letter, or silent. This decides F1.
- **M2, number language en** (with an English voice installed): repeat M1's inputs and record whether the English voice reads the zh_TW symbol words (`乘以`, `度`) (F2).
- **M3, RHVoice:** does `say-as characters` spell `,` and `-`?
- **M4, number pause:** in value mode with number language en, `1 2` and `共 12 34 個` now pause between the numbers (O). Raise the number wait to hear it clearly.
- **M5, value mode:** `12,345,678`, `1,234.56`, `-1,234` are read as single values. `3,14` and `1,234,56` are unchanged. Repeat with a de or fr voice to confirm the accepted risk.
- **M6, "off":** numbers are read exactly as the voice reads them. The number language and number pause still apply.
- **M7, upgrade:**
  - Start from a profile with `group_size = 1`, `group_wait_factor = 40` and `ignore_comma_between_number = True`.
  - WorldVoice loads. The Speech Pipeline panel shows group size 2 and has no removed controls.
  - The Log Record panel has no ignore-comma switch.
- **M8, scope "all"** with NVDA's own OneCore, eSpeak and SAPI5 selected: group 3 on `123.456` gives breaks and the `.` symbol, and nothing after it is dropped.
- **M9, settings ring:** "Number mode" cycles off/value/number/group, and "Group wait factor" is not in the ring.

## 12. Existing tests and documents that need new expectations

Confirmed by a full run of `tests/` on the prototype, after adding `CharacterModeCommand` to the stubs: 129 failed, 1981 passed. The baseline was 2110 passed, 0 skipped. Every failure below is an expected consequence of a decision. None came from the prototype's shortcuts.

- **Test stubs (no expectation change, needed first):**
  - `tests/pipeline_harness.py:58-73`: add `CharacterModeCommand(state)` to the `speech.commands` stub. `punctuation_settings` (`:113-127`) drops `ignore_comma_between_number` and `scaled_group_wait`. `ORDER` (`:130-140`) becomes the 6.8 list, plus a separate list of log switches.
  - `tests/conftest.py:94-101` and `tests/test_worldvoice_speak.py:102-109`: add `CharacterModeCommand` to their `speech.commands` stubs. Without it, 8 tests in `test_worldvoice_speak.py` and several Voice-panel tests fail on import.
  - `tests/ui_harness.py:779-781`: the `STAGES` stub entries need `log_switch`. Better, stub `LOG_SWITCHES`.
  - `tests/nvda_stubs.py:103-110` parses the log confspec comprehension with `ast`. Update it for `LOG_SWITCHES`.
  - `tests/test_pipeline_nvda_ssml.py:31-35`: use the harness's `CharacterModeCommand` for NVDA's `speechXml`. Otherwise the converter sees another class and logs "Unsupported command".
- **`tests/test_pipeline_filters.py`:**
  - `test_number_mode` (27 cases);
  - `test_group_mode_keeps_leading_zeros_and_every_digit`;
  - `test_group_separator_is_one_instance_per_number`;
  - `test_group_mode_then_number_wait_breaks_between_numbers_only`;
  - `test_digit_mode_breaks_only_between_adjacent_digits`;
  - `test_digit_words_are_kept_verbatim_one_per_item`, `test_translated_digits_are_split_by_the_number_wait` and `test_group_mode_does_not_translate_digits`: remove, because the translate table is gone;
  - `test_number_wait_splits_numbers_separated_only_by_whitespace` (5 cases, including the F1 comment at `:133`).
- **`tests/test_pipeline_passthrough.py`:**
  - `test_comma_between_digits_is_dropped_only_when_enabled`: replace with value-mode thousands tests;
  - `test_digit_symbols_translate_only_in_the_number_language_or_windows`: remove;
  - `test_a_group_number_break_counts_as_an_existing_pause_for_punctuation`: use NB.
- **`tests/test_pipeline_pause_properties.py`:**
  - `test_property_decimals_are_unchanged_in_group_mode`;
  - `test_property_digit_mode_separates_every_digit`;
  - `test_property_groups_are_separate_items_of_the_chosen_size`;
  - `test_property_number_and_group_breaks_never_touch_another_break`;
  - plus the comment and strategy updates in 11.2.
- **`tests/test_pipeline_stages.py`:**
  - `test_stages_order_and_log_keys`;
  - `test_number_mode_reads_symbols_from_context`: remove;
  - `test_other_synths_get_only_plain_breaks_from_the_stages`;
  - `test_worldvoice_keeps_the_break_subclasses_from_the_stages`.
- **`tests/test_pipeline_nvda_ssml.py`:** `test_nvda_ssml_keeps_every_word_and_pause_of_the_scope_all_output` drops the 30 ms group pause and expects `say-as`.
- **`tests/test_pipeline_settings_service.py`:**
  - `test_table_drives_fields_defaults_keys_and_confspec`;
  - `test_table_lists_every_setting_in_the_canonical_order`;
  - `test_get_reads_defaults_and_current_profile`;
  - `test_effective_matches_the_old_synth_scoping`;
  - `test_group_settings_replace_the_pair_wait_and_add_the_size`;
  - `test_scaled_waits_follow_their_units_and_caps`: the group cases;
  - `test_convert_clamps_ints_to_their_bounds`: the group size minimum is now 2.
- **`tests/test_pipeline_panels.py`:** `test_log_labels_match_stages_and_confspec`, `test_pipeline_panel_saves_once_through_the_service`.
- **`tests/test_pipeline_controls.py`:** four tests use `ignore_comma_between_number` as their sample checkbox. Switch them to `punctuation_pause_enabled`.
- **`tests/test_panel_layout.py`:** `test_attribute_names`, `test_dependent_states_follow_the_number_mode`, `test_label_text`, `test_panel_specs_follow_the_table_per_panel`.
- **`tests/test_settings_panels.py`:**
  - 11 tests: stored settings, edited and saved controls, group controls, spin range, row spacing, log panel;
  - `test_pipeline_panel_selects_the_first_choice_for_an_unknown_stored_value` now expects index 1 ("value") for the number mode.
- **`tests/test_voice_settings_panel.py`:**
  - 9 tests. `group_controls_enabled` (`:309`) returns the group-wait slider state.
  - Three tests (`:388-400`, `:541-549`, `:575-586`) use `BooleanDriverSetting("cni")` as the sample checkbox row. Switch them to `punctuationpauseenabled` or `removepunctuationcharacters`.
- **`tests/test_settings_order.py`:** 9 tests. `TABLE_DRIVER_IDS` (`:21-24`), the ring (`:61`), the names (`:76`) and the panel order (`:164-168`) lose `cni` and `groupwaitfactor`, and Number language moves up.
- **`tests/test_settings_table_guard.py`:** the "bool slider" and "controller depends" cases (`:271`, `:294`) use `ignore_comma_between_number`. Add a "stored_min_value not below min_value" case.
- **`tests/test_translator_comments.py`:** `test_group_strings_have_translator_comments`, `test_changed_label_strings_have_translator_comments`.
- **`tests/test_worldvoice_pipeline_settings.py`:** `test_settings_lists_keep_their_order_and_store_pipeline_values_outside_speech_config`. `cni` and `groupwaitfactor` are in its id list at `:30-33`, and `:58-59` reads `cni`.
- **Documents:**
  - `readme.md:39`, `:44-49`; `addon/doc/zh_TW/readme.md:39`, `:44-49`;
  - `addon/locale/zh_TW/LC_MESSAGES/nvda.po`, at the entries listed in section 10.

## 13. Findings needing the user

**F1. At NVDA's default symbol level, most symbols reach the engine as words, and character mode makes the engine spell them.** This affects Q4 and the symbol part of Q1.

- **The facts:**
  - NVDA's `processText` runs after the pipeline and also inside character mode (`speech.py:1215-1232`).
  - An isolated `.` becomes `dot` at levels some/most/all. `+` becomes `plus`, `/` `slash`, `×` `times` (zh_TW `乘以`), `÷` `divide by`, `°` `degrees` (zh_TW `度`) (5.2, real NVDA code). At "most"/"all", `-` becomes `dash-` and `:` becomes `colon`. At "all", `,` becomes `comma,`.
  - All six engines spell the text inside character mode (section 9). `123.456` in group mode would therefore be heard as "123, d o t, 456".
  - At level "none", `.` and the other words above are silent: `12.5` in number mode is heard as "1, 2, 5".
- NVDA itself never does this. It replaces a symbol by its name and uses character mode only for a single character (5.3).
- **Options:**
  - **A. Keep Q4 as decided** and judge by manual item M1.
  - **B. (recommended) Follow NVDA's own key and spelling speech** (`shortcutKeys.py:95-106`):
    - replace each symbol by `characterProcessing.processSpeechSymbol(locale, symbol)`;
    - wrap it in character mode only when the result is the same single character and spelling functionality is on (`shortcutKeys.py:78-83`);
    - `.` is then always heard as "dot", independent of the symbol level, like NVDA's character navigation;
    - this needs the NVDA locale in the stage: `getCurrentLanguage()`, or the context's language.
  - **C. No character mode:** send the symbol as a plain item and let the user's symbol level decide. `,` and `-` may then be silent on some engines.
- This spec implements A, as decided. B or C would change sections 6.4, 7 and 11.

**F2. Symbol words now come from the main language and are spoken by the number-language voice.**

- With the shared regex (L1), the symbols between digits are inside the number-language wrapper.
- NVDA picks symbol words by its own language, not the number language (5.1). The words are therefore in the main language and spoken by the number voice. For example, with main zh_TW and number language en, `2×3` is sent as `2 乘以 3` to the English voice.
- On `master`, `×` was outside the wrapper and spoken by the main voice.
- For information. Check it in M2. A fix would be to put symbols outside the wrapper, which contradicts L1.

**F3. The shared regex itself changes value mode in a few places.** For information; this follows from Q1 and N.

- `"192.168.0.1"` and `"1.2.3"` lose the dot-rule spaces. They are now one match, read by the engine with NVDA's decimal-point rule.
- `"2026-10-22 12:30"` gains a number pause between date and time.
- With a number language, `"5-3"`, `"2×3"` and `"12,345,678"` are wrapped as one unit. `"5-3"` is no longer "five, minus three".
- Section 7.3 lists them.

**F4. `\d` in the decided regex.**

- On `str`, Python's `\d` also matches full-width `１２` and other Unicode decimal digits (Arabic-Indic, Devanagari, Thai and so on). `master` uses `[0-9]`.
- This spec keeps ASCII `[0-9]` (Q-A). Taken literally, `\d` would wrap Thai or full-width digits in the number language and group them, which nobody has decided.

**F5. The example thousands regex does not fully implement "the whole run is valid".**

- `(?![\d]|,\d)` removes the commas of `"1,234,,5"`.
- The spec uses `(?!,*[0-9])`, which matches the rule exactly (6.3, P3).

**F6 (for information). The clamp of a stored group size 1 needs the confspec to keep `min=1`.**

- NVDA validates on read, and a stored value below the confspec minimum raises. WorldVoice would then fail to load.
- 6.7 handles this with `stored_min_value`.

**F7 (for information). `"1.234,567"` (German notation) becomes `"1.234567"`.**

- The run after the `.` is a valid thousands run under V1.
- This is part of the accepted de/fr risk. Adding `.` to the lookbehind would avoid it but would differ from V1.

**F8 (for information). A third-party synthesizer with scope "all" may ignore `CharacterModeCommand`.**

- NVDA sends it whether or not the synth declares it (8). NVDA's built-in synthesizers handle it.

## 14. Open questions (new)

Each is adopted with the conservative default. **Decided by orchestrator with the recommended default; user may override before merge.**

1. **Q-A, the meaning of "digit":** ASCII `0-9`, as `master` has (F4).
2. **Q-B, adjacent symbols** (`"1--2"`, `"10:-5"`): each symbol is its own ⟦x⟧, with NB between them. "Every break inside a match" then holds for every boundary.
3. **Q-C, where the NB goes among held language commands:** after the first held command, so between ‹zh› and ‹en› (6.5). The audio is the same for any position.
4. **Q-D, logging the thousands step:** `Stage.log_switch` plus `LOG_SWITCHES` (6.3). The Log Record panel keeps its order.
5. **Q-E, the thousands lookahead:** `(?!,*[0-9])` (F5).
6. **Q-F, the "off" msgid:** plain `_("off")`, like the other mode labels, not `pgettext`.
7. **Q-G, dead code:** remove `SpeechContext.speech_symbols` and `_PURE_NUMBER_RE`. `_SENTENCE_END_RE` (`:38`) is left alone, because it is not about numbers.

## 15. Flow, tasks and batches

- **Normal flow.** The complex flow is not needed:
  - one implementer runs the plan;
  - nothing must be byte-exact (no inner drivers, no packaging);
  - the changes are behavioural, not a mechanical rename across many files.
- **Tasks (13):**
  1. Test stubs: `CharacterModeCommand` in `pipeline_harness`, `conftest`, `test_worldvoice_speak` and the SSML test (no behaviour change).
  2. Shared `_NUMBER_RE`: symbols, sign, `[SYM]+` form; `_PURE_NUMBER_RE` out; `_split_spaced_numbers` without `glued`; `_both_numbers`. P1 and P2.
  3. `number_wait_factor` with transparent language commands (O).
  4. Remove "Ignore commas between numbers": setting, stage, log label, `effective` coupling (V6), tests.
  5. Thousands step: `remove_thousands_separators`, `Stage.log_switch`, `LOG_SWITCHES`, and the confspec and Log Record consumers. P3.
  6. "off" mode: choice, label, pass-through in both number-mode stages. P4.
  7. Number and group modes rewritten (6.4); `GroupNumberBreakCommand`, `get_translate_table` and `SpeechContext.speech_symbols` out. P5–P7.
  8. Remove the group wait setting: spec, scaled, constant, ring, panels.
  9. Group size 2..10 with `stored_min_value`, plus the guard check.
  10. Properties P8–P10 and updates to the existing properties.
  11. Scope "all": the plain-breaks test and the NVDA SSML test with `say-as`.
  12. zh_TW `.po`, translator tests, `readme.md` and the zh_TW readme.
  13. Full verification (section 7 of the workflow) and mutmut on 11.3. Record the survivors.
- **Batches** (section 3.2: 13 tasks give 5/4/4):
  - tasks 1–5, then a batch review;
  - tasks 6–9, then a batch review;
  - tasks 10–13, then the final whole-branch review.
- **Every batch review and the final review use Fable 5.1 (decision P).** Critical and Important findings of a batch review are fixed by TDD before the next batch.

## 16. Prototype record (scratch only, not committed)

- **Scratch copy.** A copy of `967944e` was made in the scratchpad, without `.git`, with `ref` linked. A patch script then applied sections 6.1–6.8.
- **Stubs.** `CharacterModeCommand` was added to the three stubs listed in section 12, and `log_switch` to the `ui_harness` stage stub.
- **Baseline.** The unmodified copy gave 2110 passed.
- **Full run on the prototype:** 129 failed, 1981 passed. Section 12 lists the failures.
- **Tables.** Sections 7.1–7.3 were printed by a scratch test that runs every `Stage.handler` in order. `master`'s column in 7.3 came from the same script on an unmodified copy.
- **Properties.**
  - P3, P5 (first part), P6, P7 (first part) and P9 passed 3,000 examples each.
  - The decided example regex failed P3 on `"0,000,,0"`, which led to F5.
  - The first P8 draft failed on `"0\t:"` because `_remove_space` strips the edges of wrapped items. P8 now compares without whitespace.
  - The existing number-split properties passed with the wider alphabet.
  - The adapted X1 property passed.
- **NVDA symbols.** Section 5.2 came from NVDA's real `characterProcessing.py`, loaded with stubs for `NVDAState`, `config`, `globalVars`, `logHandler` and `addonHandler`, over `ref/nvda/source/locale`.
