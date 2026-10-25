# Unspaced-script space pause: the Chinese space pause for every script written without spaces

Date: 2026-10-25.
Baseline: `master` `21e302b`. Branch: `feat/unspaced-script-space-pause`, worktree `/workspace/WorldVoice-unspaced` (`ref` symlinked to `/workspace/WorldVoice/ref`).
Baseline numbers: `python3 -m pytest -q -p no:cacheprovider tests` → 2941 passed, 0 skipped.
Flow: normal flow (`DEVELOPMENT_WORKFLOW.md` §3.1).

Status:

- U1–U8 were decided by the user (2026-10-25).
- O1 is the orchestrator's call (Decided by orchestrator with the recommended default; user may override before merge).
- D1–D6 are defaults added while writing this spec (§11). Decided by orchestrator with the recommended default; user may override before merge.
- F1 contradicts an assumption of the request: the readmes do mention this pause (§0).
- Q1–Q3 were decided by the user (2026-10-25), each with option A (§11). D7 became Q2's answer. No question is open.

References used throughout:

- Pipeline stages: `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (below: `pipeline:<line>`).
- Pipeline settings table: `addon/synthDrivers/WorldVoice/pipeline/settings.py` (below: `psettings:<line>`).
- Panel layout rules: `addon/synthDrivers/WorldVoice/pipeline/panelLayout.py` (below: `layout:<line>`).
- Number definitions: `addon/synthDrivers/WorldVoice/pipeline/numbers.py` (below: `numbers:<line>`).
- Synth: `addon/synthDrivers/WorldVoice/__init__.py` (below: `synth:<line>`).
- Script lookup: `addon/synthDrivers/WorldVoice/languageDetection/scripts.py` (below: `scripts:<line>`). Its table is `languageDetection/script_data.py` (Unicode 16.0.0, `script_data.py:3`), a protected file this branch does not touch.
- Speech settings dialogs: `addon/globalPlugins/WorldVoice/speechSettingsDialog.py` (below: `dialog:<line>`).
- NVDA: `ref/nvda/source/...`.

The rule (§4) was prototyped in a scratch test file outside the repository. The file was not committed. It used the real `script_data.py` and the pipeline harness:

- Every row of §5 gives the output shown there.
- A Hypothesis check of 3000 examples passed: the split keeps the text, and every pause replaces a whole whitespace run that has an unspaced character after it.
- A second check of 3000 examples passed: every whitespace run that today's `_CH_SPACE_RE` replaces is still replaced (the new rule is a superset of today's, §4.2).
- Today's interaction with a space among the punctuation pause characters was run through the real stages (F3).
- Timing: a 160 000-character text took about 70 ms with the new split, against about 3 ms with today's regex (§7).

## 0. Findings

### F1 (contradicts the request; Q2). The readmes describe this pause

The request assumed no add-on document mentions the setting. They do. They call it the "Chinese pause", and all six readmes mention it:

- `readme.md:14`, `:39`, `:53`. Examples: "Adjust pause lengths between numbers, items, Chinese text, and say-all reading", "Chinese pause".
- `addon/doc/zh_TW/readme.md:14`, `:39`, `:53`: 「中文」, 「中文間停頓」, 「中文之間」.
- `addon/doc/zh_CN/readme.md:14`, `:39`, `:47`, `addon/doc/zh_HK/readme.md:14`, `:39`, `:47`, `addon/doc/ru/readme.md:14`, `:39`, `:47` and `addon/doc/uk/readme.md:14`, `:39`, `:47`.

None of them names the setting's label ("Chinese space wait factor") or its key. Decided by the user (2026-10-25), Q2 = A: update `readme.md` and `addon/doc/zh_TW/readme.md` only, and add a changelog entry. The other four readmes stay as they are, as in the number edge pause spec (`docs/superpowers/specs/2026-10-24-feat-number-edge-pause-design.md` §6, D8). §6 gives the text.

### F2 (Q1). Bopomofo tone marks are Common

The four Taiwan tone marks are Unicode modifier letters of the Common script: ˇ U+02C7, ˊ U+02CA, ˋ U+02CB and ˙ U+02D9. So is the first-tone macron ˉ U+02C9. Their Script_Extensions are {Bopomofo, Latin}. Only U+02EA–U+02EB are Bopomofo (`script_data.py:23`).

- In Zhuyin written with tones, most syllables end with a tone mark. The light-tone dot is written before the syllable. So with the rule as stated, `ㄋㄧˇ ㄏㄠˇ` gets no pause, while `ㄧㄣ ㄓㄨ` (first tone, no mark) does.
- The tone marks do not pass the D1 test (Script_Extensions only unspaced scripts), because Latin is in their extensions.
- Decided by the user (2026-10-25), Q1 = A: U+02C7, U+02C9, U+02CA, U+02CB and U+02D9 count as Bopomofo for this rule, like ー for kana. A pause still needs an unspaced character on both sides, so Latin text with these marks never gets one.
- They are listed explicitly in `_UNSPACED_BOPOMOFO_MARKS`, next to the D1 set, because the D1 rule does not cover them (§4.2).

### F3 (Q3). With a space among the punctuation pause characters, this pause replaces the punctuation pause at that space

- The space stage runs before the punctuation stage (`pipeline:1048-1057`). It turns the space into a `BreakCommand` (`pipeline:603`, `:615-619`), so the punctuation stage never sees that space.
- Prototype with today's stages, punctuation characters `" "`, punctuation wait 250 and Chinese wait 10. `你好 世界 hello world` gives `你好`, Break 10, `世界`, `" "`, PunctuationBreak 250, `hello`, `" "`, PunctuationBreak 250, `world`.
- Today this affects only spaces between two basic CJK ideographs. After the change it also affects kana, Thai and the other unspaced scripts. A user who put a space in the list (allowed since 2026-10-23, `tests/test_pipeline_punctuation_pause.py:166-191`) hears the short space pause (10 ms by default) at those spaces instead of the punctuation pause.
- Decided by the user (2026-10-25), Q3 = A: keep it as it is. It matches today's Han behaviour, and the user can raise the space wait factor. The punctuation stage is not changed.

### F4 (for information). The new label needs three proper nouns in the sentence-case guards

"Space wait factor between CJK and Southeast Asian characters" capitalises three words after the first: "CJK", "Southeast" and "Asian". Two guards would fail:

- `tests/test_settings_table_guard.py:24` lists the words allowed to keep a capital (`PROPER_NOUNS = {"Unicode", "Chinese", "WorldVoice"}`), and `:181-187` applies the list;
- `tests/test_pipeline_panels.py:55` exempts only "Chinese" in the log labels.

Both get "CJK", "Southeast" and "Asian". "Chinese" is then used by no label; D6 removes it.

### F5 (for information). "CJK" in the English label includes Korean, which never pauses

Hangul separates words with spaces, so `한국 어` gets no pause (U2). The English label is the user's choice (U6). The zh_TW label 「中日文及東南亞文字」 does not mention Korean, so it says exactly what the rule does.

### F6 (for information). Script digits and script punctuation count as their script

The rule goes by the Unicode script table, so some digits and marks count as their script:

- Thai, Lao, Khmer and Myanmar digits are in those scripts (`๑` U+0E51 Thai, Myanmar digits U+1040–U+1049 at `script_data.py:231`). So `๑ ๒` gets a pause, while `1 2` and `１ ２` (Common) do not.
- Their own punctuation is also in the script: Thai ฯ U+0E2F and ๆ U+0E46, Khmer ។ U+17D4, Myanmar ။ U+104B. So `ต่างๆ นานา` gets a pause.
- CJK punctuation (`。`, `、`, `「`, `」`) is Common, so `中。 文` gets no pause, as today.

## 1. Problem

- `inject_chinese_space_pause` (`pipeline:596-619`) turns a whitespace run into one `BreakCommand` only between two characters of U+4E00–U+9FA5 (`_CH_SPACE_RE`, `pipeline:32`).
- Other scripts are written without spaces between words too: Japanese kana, Bopomofo, Thai, Lao, Khmer and Myanmar. When their text has a space, it marks a phrase or sentence boundary, as in Chinese. Today none of them gets the pause.
- `漢字 かな` and `中文 ภาษาไทย` do not pause either.
- Han characters outside U+4E00–U+9FA5 get no pause: Extension A (U+3400), U+9FA6–U+9FFF, the compatibility ideographs and Extensions B–I (U+20000 and up). Neither do 々 (U+3005) and 〇 (U+3007).
- The setting's name, label and key say "Chinese", so they no longer describe the rule.

## 2. Goals and non-goals

### 2.1 Goals (decided by the user, 2026-10-25)

- **U1.** A whitespace run becomes the pause when the character just before it and the character just after it are both of an unspaced script. "Whitespace run" means `\s+`, as today (`pipeline:32`), newlines and U+3000 included. The two sides may be different unspaced scripts: `漢字 かな` and `中文 ภาษาไทย` pause.
- **U2.** If either side is of a spaced script (Latin, Hangul, Cyrillic, …), or is Common punctuation, a digit or anything else, there is no pause.
- **U3.** The unspaced scripts are Han, Hiragana, Katakana, Bopomofo, Thai, Lao, Khmer and Myanmar.
  - Han covers every ideograph block, through the Unicode script table, not a hard-coded range.
  - The script comes from the existing `get_script` (`scripts:6-13`).
- **U4.** The prolonged sound marks U+30FC (ー) and U+FF70 (ｰ) are Common in Unicode, but count as kana for this rule. D1 extends this to the other kana-only Common letters.
- **U5.** The rule does not look at the main voice language, and it applies to every synth, as today. It works within one string item, as today: no look across commands or items. A wait of 0 disables it.
- **U6.** Everything is renamed, with no backward compatibility and no config migration:
  - setting key `unspaced_script_space_wait_factor`, driver_id `unspacedscriptspacewaitfactor`;
  - stage function `inject_unspaced_script_space_pause`;
  - `PipelineSettings.scaled_unspaced_script_space_wait()`;
  - the log switch key, which is the setting key.

  The old names are removed everywhere in `addon/` and `tests/`. Old specs under `docs/` stay as history.
- **U7.** Label: "Space wait factor between CJK and Southeast Asian characters", with the existing translator comment. zh_TW: 「中日文及東南亞文字空白停頓參數」. Only the zh_TW `.po` is updated. zh_CN, zh_HK, ru, tr and uk keep their stale entries for translators (`DEVELOPMENT_WORKFLOW.md` §6).
- **U8.** Old stored values are lost. A user who had 0 gets the default 10 again. The changelog says so (§6).

### 2.2 Orchestrator call (Decided by orchestrator with the recommended default; user may override before merge)

- **O1.** An Inherited character (a combining mark, a variation selector, ZWJ or ZWNJ) next to the whitespace takes the script of the base character it attaches to. A mark attaches to the character before it:
  - **Before the run:** look back past Inherited characters to the first character that is not Inherited. That character decides. If there is none before the string's start, there is no pause.
  - **After the run:** a mark right after the whitespace attaches to the whitespace. Its base is not an unspaced character, so there is no pause.

### 2.3 Non-goals

- Tibetan, Yi, Javanese, Balinese, Sundanese, the Tai scripts (Tai Le, New Tai Lue, Tai Tham, Tai Viet) and historic scripts. Each can be added later by one entry in `UNSPACED_SCRIPTS` (§4.2).
- Zero-width space (U+200B) and other characters that are not `\s` (`str.isspace()` is false for U+200B and U+FEFF). Thai, Khmer and Myanmar text may use U+200B between words, and it stays silent, as today.
- Looking across items or commands, or at the voice language (U5).
- Changing the pause time formula. It stays `global_factor_units * factor` (`psettings:309-322`), with the default 10 (`psettings:229-238`).
- Any engine wrapper, the upstream drivers under `driver/<Engine>/driver/`, `driver/sonic/`, `languageDetection/script_data.py`, and Neural.
- The zh_CN, zh_HK, ru, tr and uk catalogs, and the zh_CN, zh_HK, ru and uk readmes (U7, Q2).

## 3. User-visible changes

What NVDA users hear with the default factor 10 and global wait factor 10 (10 ms). "|" is the pause.

| Text | Today | After |
|---|---|---|
| `中 文 abc 中 文` | `中` \| `文 abc 中` \| `文` | unchanged |
| `hello world`, `中 abc`, `한국 어`, `中 한국`, `1 2` | no pause | unchanged |
| `かな カナ`, `コーヒー ください` | no pause | `かな` \| `カナ`; `コーヒー` \| `ください` |
| `ｺｰﾋｰ ｸﾀﾞｻｲ` (half-width, ｰ and ﾞ before or at the space) | no pause | `ｺｰﾋｰ` \| `ｸﾀﾞｻｲ` |
| `ภาษา ไทย`, `ລາວ ພາສາ`, `ខ្មែរ ភាសា`, `မြန်မာ စာ` | no pause | pause |
| `漢字 かな`, `中文 ภาษาไทย` | no pause | pause |
| `㐀 㐁` (Extension A), `𠀀 𠀁` (Extension B), `鿀 鿁` (U+9FC0–U+9FC1) | no pause | pause |
| `ㄧㄣ ㄓㄨ` | no pause | pause |
| `ㄋㄧˇ ㄏㄠˇ`, `ㄓㄨˋ ㄧㄣ` (tone marks, F2, Q1) | no pause | pause |
| `中。 文`, `中 ２` | no pause | unchanged |
| `中　文`, `中\n文` | pause | unchanged |
| `๑ ๒` (Thai digits, F6) | ~~no pause~~ the number pause (value mode, number pause > 0); no pause otherwise (corrected by the review, M1) | pause |
| Space among the punctuation pause characters, `ภาษา ไทย` (F3) | punctuation pause | the space pause instead (Q3 = A) |
| Factor set to 0 before the update | no pause anywhere | the default 10 again (U8) |

- Every space that pauses today still pauses (§4.2).
- The setting is in the same place in every panel and the settings ring, with the new label (§6).
- The Log Record panel lists the stage's switch with the new label. A switch the user had turned on is off again, because its key changed (§7).

## 4. Design

### 4.1 Terms

- **Unspaced character:** a character for which `_is_unspaced` (§4.2) is true.
- **Whitespace run:** a match of `\s+` in a string item, as found by `re.finditer`. It is maximal, so the characters on each side are not whitespace, or are the string's ends.
- **Left base:** the first character before the run that is not Inherited (O1).
- **Right neighbour:** the character right after the run.
- A run **becomes the pause** when the left base exists and is unspaced, and the right neighbour exists and is unspaced.

### 4.2 Classifying a character (U3, U4, D1)

In `pipeline/__init__.py`, near the stage:

```python
# Scripts whose words are not separated by spaces: a space between two of their characters is a
# pause (decided by the user, 2026-10-25). Add a script here to extend the rule.
UNSPACED_SCRIPTS = frozenset({"Han", "Hiragana", "Katakana", "Bopomofo", "Thai", "Lao", "Khmer", "Myanmar"})
# Common letters whose Script_Extensions are only unspaced scripts (Unicode 16.0.0 ScriptExtensions.txt):
# 〆 U+3006, the vertical kana repeat marks U+3031–U+3035, 〼 U+303C, ゛゜ U+309B–U+309C,
# ー U+30FC, ｰ U+FF70 and ﾞﾟ U+FF9E–U+FF9F.
_UNSPACED_COMMON = frozenset({...})
# The Bopomofo tone marks ˇ U+02C7, ˉ U+02C9, ˊ U+02CA, ˋ U+02CB and ˙ U+02D9: Common, with Latin in
# their Script_Extensions, but counted as Bopomofo for this rule (decided by the user, 2026-10-25).
_UNSPACED_BOPOMOFO_MARKS = frozenset({...})
```

- `_is_unspaced(character)` is true when the character is in `_UNSPACED_COMMON` or `_UNSPACED_BOPOMOFO_MARKS`, or `get_script(ord(character))` is in `UNSPACED_SCRIPTS`. The plan may merge the two sets into one, as long as each keeps its comment.
- `get_script` returns `None` for code points outside the table (`scripts:7-12`): unassigned ones, private use (U+E000) and lone surrogates (U+D800). These are not unspaced.
- **D1. The Common characters that count.**
  - U4 names ー and ｰ. This spec adds every other Common character that:
    - is a letter or a modifier symbol (categories Lo, Lm, Sk), and
    - has only unspaced scripts in its Script_Extensions.

    That gives the set in the comment above. The set was read from `ScriptExtensions.txt` 16.0.0.
  - Not included:
    - punctuation and symbols such as ゠ U+30A0, ・ U+30FB, 。 and 「」, which are Common punctuation (U2);
    - the Bopomofo tone marks, which have Latin in their extensions. They are not in this set, but Q1 = A adds them explicitly (next item).
    - U+3099 and U+309A (the combining voiced marks). They are Inherited, so O1 covers them: in `が か` the left base is か.
- `languageDetection/script_data.py` does not hold Script_Extensions, and this branch does not change it. So the set is written out, and a test pins it (§8.2).
- **Q1 = A (decided by the user, 2026-10-25).** The five Bopomofo tone marks count as unspaced through `_UNSPACED_BOPOMOFO_MARKS`, listed explicitly because they fall outside the D1 rule (F2). So `ㄋㄧˇ ㄏㄠˇ` pauses, and so does `ㄓㄨˋ ˙ㄉㄜ` (the light-tone dot before the syllable is the right neighbour).
- **Superset of today.**
  - All of U+4E00–U+9FA5 is Han in the table, and a Han character is never Inherited.
  - So when today's regex sees an ideograph right before and right after a run, the new rule sees the same characters as the left base and the right neighbour.
  - Every run that pauses today still pauses. The prototype checked this (header), and P3 (§8.3) keeps checking it.

### 4.3 The decision and the stage

- **`_pauses_between(text, start, end) -> bool`** says whether the run `text[start:end]` becomes the pause.
  - Walk back from `start - 1` while the character is Inherited (`get_script(...) == "Inherited"`).
  - The result is false if the walk passes the string's start, or if `end == len(text)`.
  - Otherwise it is `_is_unspaced(base) and _is_unspaced(text[end])`.
- **`inject_unspaced_script_space_pause(speechSequence, settings, ctx)`** replaces `inject_chinese_space_pause` (`pipeline:596-619`) and keeps its shape:
  - `waitfactor = settings.scaled_unspaced_script_space_wait()`. At `<= 0`, it yields the sequence unchanged (`pipeline:602-604`).
  - One `BreakCommand(waitfactor)` per call, reused for every pause, as today (`pipeline:606`).
  - Non-string items pass through untouched, in order (`pipeline:610-612`).
  - For each string item, iterate `_WHITESPACE_RE = re.compile(r"\s+")` with `finditer`. A run for which `_pauses_between` is true is replaced by the break. Everything else is kept as text, so the non-empty text pieces between pauses are yielded exactly as `_split_by` yields them today (`pipeline:118-127`).
  - How the split is written (a filtered `_split_by`, or a small loop) is left to the plan.
- `_CH_SPACE_RE` (`pipeline:32`) and the comment at `pipeline:614` are removed.

### 4.4 The other stages

- **Numbers before it.**
  - `remove_thousands_separators` and `inject_numbers` run first (`pipeline:1050-1051`).
  - A whitespace run next to a digit has a Common neighbour, so number pieces never touch this rule, as today.
  - The Thai, Lao, Khmer and Myanmar digits count as their script (F6). The number stage treats them as numbers: `NUMBER_RE` uses Unicode decimal digits (`numbers:22`; phase 35, `readme.md:78`). In the number and group modes with a number pause above 0, `inject_numbers` puts one number break between two whitespace-separated numbers and removes the whitespace (number edge pause spec §2.2 O3, §8.3 P-E1). So that whitespace is gone before this stage runs. In value mode, `๑ ๒` reaches this stage with its space, and it pauses. So in value mode the space pause replaces the number pause between two script digits: `number_wait_factor` adds no number break where a command already separates the numbers (`pipeline:262-283`). Accepted by the orchestrator with the review's option A (review M1, 2026-10-25). The plan checks the number modes at pause 0 with a test.
- **Item and number waits after it** (`pipeline:1053`, `:1055`): unchanged. They already see this stage's breaks today.
- **Punctuation pause** (`pipeline:1054`, `:657-716`): an existing break between two items suppresses an item's boundary pause, as today. F3 describes the space-in-the-list case.
- **Language detection** runs on the stage output inside the synth and passes breaks through, as today. In `中文 ภาษาไทย` the break comes before the switch to the Thai voice, as `中 abc` breaks do today.
- **Other synths:**
  - In scope "WorldVoice" they get the factor 0 (`psettings:330-349`, renamed field), so no pause.
  - In scope "all" they get the same breaks, as today.
  - `_plain_breaks` (`pipeline:991-1009`) leaves a plain `BreakCommand` as it is.

### 4.5 Renames (U6)

- **`addon/synthDrivers/WorldVoice/pipeline/settings.py`:**
  - the table entry `psettings:229-238`: key, driver_id, label and translator comment;
  - the `PipelineSettings` field at `psettings:301`;
  - `scaled_chinesespace_wait` at `psettings:321-322` becomes `scaled_unspaced_script_space_wait`;
  - the `effective` override at `psettings:344`.
- **`addon/synthDrivers/WorldVoice/pipeline/__init__.py`:** `_CH_SPACE_RE` (`:32`); the stage function (`:596-619`) and its call of the scaled wait (`:601`); the `STAGES` entry `Stage("chinesespace_wait_factor", inject_chinese_space_pause)` (`:1052`).
- **Derived without code changes**, because they read the table or `STAGES`:
  - the synth setting (`synth:153-157`, `synth:112-133`) and its property (`synth:529-532`);
  - the confspec of the pipeline section (`psettings:285-290`, `synth:78`);
  - the log switch (`pipeline:1060-1067`, `synth:83-86`) and its label (`dialog:46-49`, `dialog:644-649`);
  - the Speech Pipeline panel's slider attribute `_<key>_slider` (`layout:116-118`);
  - NVDA's Voice panel control `<driver_id>Slider` (`layout:127-129`).
- **No other `addon/` file** names the setting. `grep -rni "chinese_\?space\|chinesespace\|CH_SPACE" addon --include=*.py` finds only the lines above.

### 4.6 Imports and placement (D2, D3)

- **D2.** The decision functions live in `pipeline/__init__.py` with the stage. That file is already in mutmut's `source_paths` (`pyproject.toml:51`).
- **D3.** Import: `from ..languageDetection.scripts import get_script`.
  - The import runs `languageDetection/__init__.py`. That file imports only `speech.commands`, `.._speechcommand`, `..numberLanguage` and `.scripts` (`languageDetection/__init__.py:1-5`). The pipeline already imports `_speechcommand` and `numberLanguage` (`pipeline:14`, `:16`).
  - Nothing in `languageDetection/` imports the pipeline, so there is no import cycle.
  - The structure guard checks only absolute imports (`tests/test_pipeline_structure.py:14-22`, `:102-118`). It forbids `unicodedata` in the package, so the rule cannot use `unicodedata.category`. It does not need it: O1 uses the Inherited script.

### 4.7 Logging

The stage logs under its log key `unspaced_script_space_wait_factor`, which is also its switch. `ORDER` and `LOG_SWITCH_ORDER` in `tests/pipeline_harness.py:175-194` follow the rename. The pipeline CSV rows of this stage carry the new key.

## 5. Worked examples

`|` is `BreakCommand(20)` with the wait at 20; one input string each, checked in the prototype.

| # | Input | Output |
|---|---|---|
| 1 | `中 文 abc 中 文` | `中` \| `文 abc 中` \| `文` |
| 2 | `hello world` | `hello world` |
| 3 | `かな カナ` | `かな` \| `カナ` |
| 4 | `ภาษา ไทย` | `ภาษา` \| `ไทย` |
| 5 | `漢字 かな` | `漢字` \| `かな` |
| 6 | `中文 ภาษาไทย` | `中文` \| `ภาษาไทย` |
| 7 | `中 abc` | `中 abc` |
| 8 | `中 한국` / `한국 어` | unchanged |
| 9 | `コーヒー ください` | `コーヒー` \| `ください` |
| 10 | `ｺｰﾋｰ ｸﾀﾞｻｲ` | `ｺｰﾋｰ` \| `ｸﾀﾞｻｲ` |
| 11 | `㐀 㐁` | `㐀` \| `㐁` |
| 12 | `\U00020000 \U00020001` | `\U00020000` \| `\U00020001` |
| 13 | `中　文` | `中` \| `文` |
| 14 | `中\n\t 文` | `中` \| `文` (one break for the whole run) |
| 15 | `中 文` | `中` \| `文` |
| 16 | `中​文` | unchanged (U+200B is not `\s`) |
| 17 | ` 中 ` | unchanged (no character before the first run or after the last) |
| 18 | `   ` | unchanged |
| 19 | `が か` | `が` \| `か` (O1, look back) |
| 20 | `葛\U000E0100 中` | `葛\U000E0100` \| `中` (an ideographic variation selector is Inherited) |
| 21 | `中 ゙か` | unchanged (O1: the mark after the run attaches to the space) |
| 22 | `中。 文` | unchanged |
| 23 | `ㄧㄣ ㄓㄨ` | `ㄧㄣ` \| `ㄓㄨ` |
| 24 | `ㄓㄨˋ ㄧㄣ` | `ㄓㄨˋ` \| `ㄧㄣ` (Q1) |
| 24a | `ㄋㄧˇ ㄏㄠˇ` | `ㄋㄧˇ` \| `ㄏㄠˇ` (Q1) |
| 24b | `ㄓㄨˋ ˙ㄉㄜ` | `ㄓㄨˋ` \| `˙ㄉㄜ` (Q1) |
| 24c | `a ˇ`, `ˇ a` | unchanged (a Latin neighbour) |
| 24d | `中 ˇa` | `中` \| `ˇa` (the tone mark right after the run counts as Bopomofo; an accepted effect of Q1, as unlikely as it is harmless) |
| 25 | `๑ ๒` | `๑` \| `๒` (F6) |
| 26 | `1 2` | unchanged |
| 27 | wait 0, any input | the same objects, unchanged |
| 28 | `[marker, "中 文"]` | `marker`, `中`, \|, `文` |

## 6. Panels, strings and documentation

### Panels and dialogs

Both panels and the settings ring derive their controls from the table (`psettings:131-283`). The NVDA Voice panel and the ring list `supportedSettings` in table order (`synth:135-157`). The Speech Pipeline panel uses `panel_specs` (`layout:35-37`, `dialog:16-23`).

- No control is added, removed or moved. The slider keeps its place, between "Say all wait factor" and "Enable punctuation pause control". The focus order is unchanged.
- The name NVDA reads changes:
  - "Space wait factor between CJK and Southeast Asian characters:" for the controls WorldVoice makes (`layout:40-42` adds the colon);
  - "Space wait factor between CJK and Southeast Asian characters" in the settings ring and in the Log Record panel;
  - zh_TW: 「中日文及東南亞文字空白停頓參數」.
- The control attributes change with the key and driver_id (§4.5). Nothing outside the derived code refers to them.

### Translatable strings

- New msgid "Space wait factor between CJK and Southeast Asian characters". Its translator comment is the existing one, unchanged (`psettings:234-235`): "Label for a pipeline setting in the voice settings panel and the Speech Pipeline panel; also the label of the setting's pipeline log switch in the Log Record panel."
- `addon/locale/zh_TW/LC_MESSAGES/nvda.po:419-423`: replace the entry `msgid "Chinese space wait factor"` / `msgstr "中文空白停頓參數"` with the new msgid and `msgstr "中日文及東南亞文字空白停頓參數"`. Check with `msgfmt --check`.
- "Chinese space wait factor" becomes a dead msgid. Add it to `DEAD_MSGIDS` (`tests/test_translator_comments.py:64-89`), so that `tests/test_translator_comments.py:150-153` checks the zh_TW catalog no longer holds it. Add the new msgid to `CHANGED_LABEL_MSGIDS` (`:43-62`).
- Other catalogs are not edited (U7). Their stale entries are:
  - ru `nvda.po:624`;
  - tr `:596`;
  - uk `:569`;
  - zh_HK `:562`;
  - zh_CN `:589`.

  Their older lowercase entries (`"chinese space wait factor"`, `"chinese space wait factor:"`) are already dead today. The `.pot` is not committed.

### Readmes (Q2 = A, decided by the user, 2026-10-25; F1)

Change `readme.md` and `addon/doc/zh_TW/readme.md` only.

- Line 14:
  - EN: "Adjust pause lengths between numbers, items, spaces in Chinese, Japanese and Southeast Asian text, and say-all reading, so the reading rhythm better matches user preference."
  - zh_TW: 「可調整數字、項目、中日文及東南亞文字空白與全文朗讀間的停頓長度，使朗讀節奏更符合使用習慣。」
- Line 39: "Chinese pause" becomes "CJK and Southeast Asian space pause"; zh_TW 「中文間停頓」 becomes 「中日文及東南亞文字空白停頓」.
- Line 53, the first sentence:
  - EN: "Sets the pause length between numbers, items, spaces in Chinese, Japanese and Southeast Asian text, and say-all reading." Add after it: "The space pause is used where a space has Han, kana, Bopomofo, Thai, Lao, Khmer or Myanmar characters on both sides; Korean and Latin text never get it."
  - zh_TW: 「設定數字之間、項目之間、中日文及東南亞文字的空白與全文朗讀之間的停頓時間，」. Add: 「空白停頓只用在空白兩側都是漢字、假名、注音符號、泰文、寮文、高棉文或緬甸文字元時；韓文與拉丁字母不會停頓。」
- Changelog, under "Next update" (`readme.md:73`, `addon/doc/zh_TW/readme.md:73`):
  - EN: "**Space pause for Japanese and Southeast Asian text:** The Chinese space wait factor is now the "Space wait factor between CJK and Southeast Asian characters". A space between two characters of Han (including every extension block), kana, Bopomofo, Thai, Lao, Khmer or Myanmar script now gets the pause, also when the two sides are different scripts, as in "漢字 かな". Earlier versions paused only between two common Chinese characters. Because the setting was renamed, a value you changed returns to the default 10; set it again, or set it to 0 to turn the pause off."
  - zh_TW: 「**日文與東南亞文字的空白停頓：** 「中文空白停頓參數」改為「中日文及東南亞文字空白停頓參數」。空白兩側都是漢字（包括所有擴充區）、假名、注音符號、泰文、寮文、高棉文或緬甸文字元時，現在都會停頓，兩側是不同文字時也一樣，例如「漢字 かな」。先前版本只在兩個常用中文字之間停頓。由於設定已更名，您調整過的值會回到預設值 10；請重新設定，或設為 0 關閉這個停頓。」
- Q3 = A, so add to both changelog entries: EN "If the punctuation pause characters include a space, these spaces get the space pause instead of the punctuation pause, as Chinese text already did."; zh_TW 「標點停頓字元包含空白時，這些空白使用空白停頓而非標點停頓，與先前中文的情況相同。」

`buildVars.py` stays untouched.

## 7. Settings, data, compatibility and errors

- **Pipeline config section:**
  - The confspec gets `unspaced_script_space_wait_factor = integer(default=10,min=0,max=100)` from the table (`psettings:122-128`, `:285-290`). `chinesespace_wait_factor` leaves the confspec.
  - No migration (U6, U8). A stored `chinesespace_wait_factor` is never read again: `ConfigPipelineRepository.load` reads table keys only (`psettings:392-396`).
  - The stored key stays in `nvda.ini`, because configobj writes the whole profile back (`ref/nvda/source/config/__init__.py:714-716`). NVDA validates it against no spec, because the WorldVoice section is not in NVDA's base spec.
  - This is the same as the stale keys of earlier specs (`docs/superpowers/specs/2026-10-21-feat-number-group-mode-design.md:439`).
- **Log section:** the switch key `chinesespace_wait_factor` (`synth:83-86`) becomes `unspaced_script_space_wait_factor`, default false. A switch the user had turned on is off after the update. Its old key stays in the file, unread.
- **NVDA's speech section:** the setting uses `useConfig=False` (`synth:118`, `pipeline_config` is true), so NVDA never stored it under `[speech][WorldVoice]`. Nothing is left there.
- **Settings profiles:** every profile behaves the same, because each one holds the old key in its own pipeline section.
- **Errors:** no new error path.
  - `get_script` cannot fail for an `ord()` of a `str` character (`scripts:6-13`).
  - A failure in a stage still goes through NVDA's filter handling, as today.
- **Performance:**
  - `get_script` is a `bisect_right` over 979 ranges (`scripts:7`). It is called only for the neighbours of whitespace runs: one call for the right neighbour, and one or more for the left base (one more per Inherited mark skipped). Lookups stop at the first side that fails.
  - The prototype took about 70 ms for a 160 000-character mixed text, against about 3 ms for today's regex. A typical NVDA utterance is under 1 000 characters, which is well under 1 ms.
  - Optional (D4): an ASCII fast path, where a code point below 0x80 is never unspaced and needs no `get_script` call. Most whitespace runs in Latin text are then decided without a lookup.

## 8. Test plan

### 8.1 Existing tests that change

Mechanical renames, identical behaviour. The list holds every occurrence that `grep -rni "chinese_\?space\|chinesespace\|CH_SPACE" tests` reports, plus the related local names.

- `tests/pipeline_harness.py:167` (`scaled_chinesespace_wait=lambda: 0`), `:179` (`ORDER`), `:190` (`LOG_SWITCH_ORDER`).
- `tests/test_panel_layout.py:25`.
- `tests/test_pipeline_filters.py:817-828`: `test_chinese_space_pause` becomes `test_unspaced_script_space_pause`, with the same rows.
- `tests/test_pipeline_pause_properties.py:695`: the P10 chain calls the renamed stage.
- `tests/test_pipeline_number_edges.py:41`.
- `tests/test_pipeline_number_edge_properties.py:38`, plus the parameter `chinese` (`:29`, `:227`), which becomes `unspaced`.
- `tests/test_pipeline_passthrough.py:178-182`: `test_chinese_space_pause_passes_commands` becomes `test_unspaced_script_space_pause_passes_commands`.
- `tests/test_pipeline_settings_service.py:18`, `:45`, `:106`, `:326`, `:360`.
- `tests/test_pipeline_panels.py:40`, with the new label; `:55`, with the F4 nouns; `:71` and `:88`, where the slider name becomes `unspaced_script_space` and the key is renamed.
- `tests/test_settings_order.py:26`, `:77` (with the new label) and `:167`.
- `tests/test_settings_panels.py:43`, `:59` (`"Space wait factor between CJK and Southeast Asian characters:"`) and `:72`.
- `tests/test_worldvoice_pipeline_settings.py:36`.
- `tests/test_worldvoice_speak.py:316`.
- `tests/test_settings_table_guard.py:24`: F4 and D6.
- `tests/test_translator_comments.py`: the `DEAD_MSGIDS` and `CHANGED_LABEL_MSGIDS` changes of §6. The old dead msgids at `:73` and `:85` stay.
- `tests/test_pipeline_punctuation_pause.py:187` matches the grep only as "su**ch_space**" and is not touched.

Harness (D5):

- `load_pipeline_module` pops a fixed list of modules (`tests/pipeline_harness.py:47-71`). With D3 the pipeline imports `synthDrivers.WorldVoice.languageDetection.scripts`, so that list gains `synthDrivers.WorldVoice.languageDetection` and `synthDrivers.WorldVoice.languageDetection.scripts`.
- Each load then imports them fresh against the current stubs, and none is left cached against an earlier test's stubs.
- `ui_harness` stubs the pipeline package and `languageDetection` (`tests/ui_harness.py:755-756`, `:780`), so the dialog tests do not load the new import.

These guards must keep passing:

- `tests/test_pipeline_structure.py`;
- `tests/test_hygiene_guards.py`;
- `tests/test_translator_comments.py`;
- `tests/test_settings_table_guard.py`, with F4.

### 8.2 New unit tests (red first)

- **Worked examples:** every row of §5 as a parametrized case through `inject_unspaced_script_space_pause` at wait 20. This covers the user's list:
  - Chinese text pauses (1, 13, 14);
  - English words never pause (2);
  - kana (3, 9, 10), Thai (4), mixed Han and kana (5) and Han and Thai (6) pause;
  - Han next to Latin (7) and Hangul (8) do not;
  - ー (9, 10), Extension A (11), U+3000 (13);
  - wait 0 (27) and commands passing through (28).
- **Classification:**
  - `_is_unspaced` is true for a sample of each script in `UNSPACED_SCRIPTS`: U+4E00, U+3400, U+9FFF, U+F900, U+20000, U+3005, U+3007, あ, ア, ｱ U+FF71, ㄅ U+3105, ㆠ U+31A0, ก, ກ, ក, က and U+1B001.
  - It is true for every code point in `_UNSPACED_COMMON`.
  - It is true for the five Bopomofo tone marks ˇ ˉ ˊ ˋ ˙ (Q1).
  - It is false for: a, A, Я, 한, ㄱ U+3131, 1, １, 。, 「, ・ U+30FB, ゠ U+30A0, U+3000, U+3099, U+E000, U+D800, an unassigned code point, and the other Common modifier letters next to the tone marks, ˈ U+02C8 and ˌ U+02CC.
- **D1 and Q1 pins:** `_UNSPACED_COMMON` equals the thirteen code points listed in §4.2, and `_UNSPACED_BOPOMOFO_MARKS` equals U+02C7, U+02C9, U+02CA, U+02CB and U+02D9. Each one is Common in `get_script`, so a later Unicode table that moves one into a script shows up in review.
- **O1:**
  - rows 19–21;
  - a run of two marks before the space (`が́ か`);
  - a mark at the string's start (`゙ か`), which gives no pause;
  - `中 ́ 文`: no pause at either run.
- **Ends of the string:** a run at the start or end of an item, an item of only whitespace, and an empty string (row 17, row 18, `""`). None gives a pause, and the text is kept.
- **Several runs in one item:** `中 文 か ภา`, where every run pauses. The same break object is reused, as today.
- **Real settings:** `PipelineSettings.scaled_unspaced_script_space_wait()` is `global_wait_factor // 10 * factor`. A global factor of 9 gives 0. In scope "WorldVoice", `effective(False)` sets the factor to 0. These are the `tests/test_pipeline_settings_service.py:326` and `:360` rows, renamed.
- **Whole `STAGES`:** `漢字 かな` in value mode with roles on gives `漢字`, `BreakCommand(10)`, `かな`. In number mode, `第3 章` gives no space pause (a digit neighbour), as today.
- **F3:** the punctuation characters `" "` with `ภาษา ไทย hello` through the stages give the space break at the Thai space and the punctuation break at the Latin space (Q3 = A).
- **Settings and panels:** the confspec has the new key and no old one. The driver setting `unspacedscriptspacewaitfactor` has the new label. The Log Record label is the new label (renamed rows of §8.1).

### 8.3 Property tests (Hypothesis)

Alphabet: Han (U+4E00, U+3400, U+20000), kana, ー, ｰ, Thai, Hangul, Latin, digits, `。`, U+3099, U+0301, ˇ, and whitespace (`" "`, `\n`, U+3000, U+00A0). Items may be strings or a marker command.

- **P1, text kept.** Joining the output strings, with each break replaced by the whitespace run it stands for, gives the input exactly. The test re-finds the runs with `\s+` on the input. Each break replaces one whole maximal run.
- **P2, no pause next to a spaced character.** For every run of the input, if the right neighbour is not unspaced, or the left base (after skipping Inherited) is not unspaced or does not exist, the run is still in the output text. A string with no unspaced character comes out unchanged.
- **P3, superset of today.** Every run that today's regex `(?<=[一-龥])\s+(?=[一-龥])` matches becomes a break. The regex is kept as an oracle literal in the test.
- **P4, off is the identity.** At a wait ≤ 0 the output is the same objects, in order.
- **P5, commands pass through.** Non-string items come out in their order, each once. Every break has non-empty text from the same input item on both sides.
- **P10** (`tests/test_pipeline_pause_properties.py:663-701`) keeps running with the renamed stage in its chain, and must still pass.

### 8.4 Mutation testing

`pipeline/__init__.py` is in `[tool.mutmut] source_paths` (`pyproject.toml:45-58`). Run mutmut on Linux over `_is_unspaced`, `_pauses_between` and `inject_unspaced_script_space_pause`. Record each surviving mutant and its reason in the plan or the review (`DEVELOPMENT_WORKFLOW.md` §7). `languageDetection/scripts.py` is not in `source_paths` and stays out.

### 8.5 Verification (`DEVELOPMENT_WORKFLOW.md` §7)

- `python3 -m pytest -q -p no:cacheprovider tests`: compare with 2941 passed, 0 skipped. Passed rises with the new tests; skipped stays at 0.
- `prek run --all-files`: all Passed.
- `git diff --check`.
- Protected paths, both printing nothing:

  ```bash
  git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py
  git ls-files addon/synthDrivers/WorldVoice/driver/Neural
  ```

- `grep -rni "chinese_\?space\|chinesespace\|CH_SPACE" addon tests --include=*.py` finds nothing (apart from the "such_space" test name).
- `msgfmt --check addon/locale/zh_TW/LC_MESSAGES/nvda.po`.
- Not verifiable on Linux: NVDA on Windows, real audio, engine SDKs. The report must say so.

### 8.6 Windows / NVDA manual items (listed, not run)

- **M1.** Chinese voice: `中文 測試` pauses as before; `中文 abc` and `中文 123` do not.
- **M2.** Japanese voice, Unicode detection on: `漢字 かな`, `コーヒー ください` and half-width `ｺｰﾋｰ ｸﾀﾞｻｲ` pause.
- **M3.** Thai voice (and Lao, Khmer, Myanmar where a voice exists): a sentence with spaces pauses at each space.
- **M4.** Mixed `中文 ภาษาไทย` with detection on: the pause comes before the switch to the Thai voice, with no lost or doubled words.
- **M5.** English and Korean text: no change.
- **M6.** Labels and focus:
  - the Voice panel, the Speech Pipeline panel, the settings ring and the Log Record panel read "Space wait factor between CJK and Southeast Asian characters", or 「中日文及東南亞文字空白停頓參數」 in zh_TW;
  - the slider sits between the say-all and punctuation controls, and Tab order is unchanged.
- **M7.** Upgrade from a profile with `chinesespace_wait_factor = 0`: after the update the pause is back at 10, NVDA opens without errors, and the old key stays in `nvda.ini`.
- **M8.** Scope "all" with OneCore, eSpeak and SAPI5: `かな カナ` pauses.
- **M9.** A document with Extension B characters (for example 𠀀): spaces between them pause.
- **M10.** Say all through a long Japanese or Thai page: no noticeable lag.
- **M11.** Punctuation pause on with a space in the list: Thai and kana spaces get the space pause, Latin spaces the punctuation pause (Q3 = A).
- **M12.** Chinese voice: Zhuyin with tone marks, `ㄋㄧˇ ㄏㄠˇ`, pauses at the space (Q1).

## 9. Affected layers

| File | Change |
|---|---|
| `addon/synthDrivers/WorldVoice/pipeline/__init__.py` | `UNSPACED_SCRIPTS`, `_UNSPACED_COMMON`, `_UNSPACED_BOPOMOFO_MARKS`, `_is_unspaced`, `_pauses_between`, the renamed stage, `STAGES`, the import (§4) |
| `addon/synthDrivers/WorldVoice/pipeline/settings.py` | the table entry, field, scaled method and `effective` (§4.5) |
| `addon/locale/zh_TW/LC_MESSAGES/nvda.po` | §6 |
| `readme.md`, `addon/doc/zh_TW/readme.md` | §6 (Q2 = A) |
| `tests/…` | §8 |

- The panels and the synth change only through the table (§4.5, §6). Their code is untouched: `addon/synthDrivers/WorldVoice/__init__.py`, `speechSettingsDialog.py`, `panelLayout.py` and `VoiceSettingsDialogs.py`.
- Engine wrappers, upstream drivers, `driver/sonic/`, `languageDetection/` (including `script_data.py`) and Neural are untouched.
- This is core pipeline code, so every engine gets the same behaviour.

## 10. Review Focus (risky inputs)

- **Extension B and later Han (one code point above U+FFFF):** Python `str` holds them as one character, so `text[i]` is the whole character. Test `𠀀 𠀁` and `𠀀 か`. A string that holds a lone surrogate (U+D800) gives `get_script` → `None`: no pause and no crash.
- **Whitespace at the string's start or end, and strings of only whitespace:** there is no neighbour on that side, so there is no pause. Watch for index errors at `end == len(text)` and at `start == 0`.
- **Combining marks:**
  - a mark before the run takes its base's script, after one or many marks;
  - a mark after the run gives no pause;
  - a mark at the string's start has no base;
  - variation selectors (U+FE00–U+FE0F, U+E0100–U+E01EF), ZWJ and ZWNJ are Inherited and count the same way.
- **Look-back across whitespace:** in `中 ́ 文` the look-back from the second run stops at the space. It must never skip whitespace.
- **The left base is a Common kana mark:** `ｺｰ ｸ`, `ーー か` and `カﾞ ア`.
- **Performance on long text:**
  - lookups must happen only at whitespace runs, never per character;
  - the look-back must be bounded by the run of marks;
  - check that a long Latin text (many runs, all failing at once) is not much slower than today, and consider D4.
- **The import of `languageDetection`:**
  - check that no cycle appears at NVDA start: the synth imports both packages;
  - check that the pipeline harness does not leave `languageDetection` cached with an earlier test's stubs (D5);
  - check that `tests/detector_harness.py` still gets a fresh package.
- **The F3 interaction** with a space among the punctuation characters, and with `remove_punctuation_characters` on: the space is gone before the punctuation stage, so removal cannot remove it.
- **Thai, Lao, Khmer and Myanmar digits in value mode** (F6): `๑ ๒` pauses, and the number pause stage (`pipeline:240-284`) does not add a second break next to it.
- **Rename completeness:** the confspec, the log confspec, the ring, both panels and the Log Record labels all derive from the table. Check that no hard-coded old name is left in the tests' expected lists.

## 11. Questions and the defaults applied

### Resolved (decided by the user, 2026-10-25)

- **Q1 (F2). Bopomofo tone marks.** Decided by the user (2026-10-25): A. ˇ U+02C7, ˉ U+02C9, ˊ U+02CA, ˋ U+02CB and ˙ U+02D9 count as Bopomofo for this rule, like ー for kana. They are listed explicitly (`_UNSPACED_BOPOMOFO_MARKS`, §4.2), so Zhuyin with tones pauses at its spaces (§5 rows 24–24c). Option B, keeping the user's first list literally, was not chosen.
- **Q2 (F1). Readmes.** Decided by the user (2026-10-25): A. Update `readme.md` and `addon/doc/zh_TW/readme.md` at lines 14, 39 and 53, and add a changelog entry that says the setting is reset (§6). The zh_CN, zh_HK, ru and uk readmes stay unchanged. Options B (no readme) and C (all six) were not chosen.
- **Q3 (F3). A space among the punctuation pause characters.** Decided by the user (2026-10-25): A. Keep today's behaviour: the space pause replaces the punctuation pause at spaces between unspaced characters, now for every unspaced script. Option B (the longer pause wins) was not chosen.

### Decided by orchestrator with the recommended default; user may override before merge

- **O1.** Inherited characters take their base's script. The base comes before the mark, so a mark right after the run means no pause (§2.2).
- **D1.** The Common letters with only unspaced Script_Extensions count, as for ー and ｰ (§4.2). These are 〆, 〱–〵, 〼, ゛, ゜, ー, ｰ, ﾞ and ﾟ. Punctuation does not count.
- **D2.** The decision lives in `pipeline/__init__.py`, which is already mutated by mutmut.
- **D3.** `get_script` is imported with `from ..languageDetection.scripts import get_script`. `script_data.py` is not touched.
- **D4.** The ASCII fast path is optional. The plan may add it if the long-text check in §10 shows a need.
- **D5.** The pipeline harness pops the `languageDetection` modules with the others.
- **D6.** "Chinese" leaves `PROPER_NOUNS` (`tests/test_settings_table_guard.py:24`) and the exemption at `tests/test_pipeline_panels.py:55`, because no label uses it any more. "CJK", "Southeast" and "Asian" are added (F4).
