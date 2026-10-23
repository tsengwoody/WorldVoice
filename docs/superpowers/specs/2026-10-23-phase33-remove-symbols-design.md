# Phase 33: remove the speech-symbols dialog, restore base-language preference in detection

Date: 2026-10-23.
Baseline: `master` `9d5b8c5` (phase 32 merged). Branch: `phase33-remove-symbols`, worktree `/workspace/WorldVoice-phase33`.
Baseline numbers: `python3 -m pytest -q tests` → 2372 passed, 0 skipped, 2 warnings (both `codecs.open` DeprecationWarnings from `addon/generics/speechSymbols/models.py`); `prek run --all-files` all Passed.
Flow: normal flow (`DEVELOPMENT_WORKFLOW.md` §3). Nothing here needs the complex flow: no byte-exact hand-off, no large mechanical rewrite.
Status: all three parts were decided by the user (2026-10-23). Smaller defaults are marked where they apply and collected in §11.

Roadmap source: `storage/refactor7.md` §5.2 (U7, U9), §5.3 (U8) and §7 "階段 33", option A (remove the feature). Parts B and C were added by the user on the same day after a side-by-side comparison with the original upstream detector.

References used throughout:

- WorldVoice detector: `addon/synthDrivers/WorldVoice/languageDetection/__init__.py` (below: `detection:<line>`).
- Upstream detector: `ref/VE2(origin)/synthDrivers/vocalizer_expressive2/languageDetection/__init__.py` (below: `upstream:<line>`). It is byte-identical to the copy under `ref/Cerence(origin)/` (checked with `cmp`).
- WorldVoice before the regression: `git show 9816ce0^:addon/synthDrivers/WorldVoice/languageDetection/__init__.py` (below: `pre-9816ce0:<line>`).

## 1. Part A: remove the speech-symbols ("Unicode Settings") feature

Decided by the user (2026-10-23): option A of `storage/refactor7.md` §7.

### 1.1 What exists today

- Package `addon/generics/speechSymbols/`: `__init__.py` (empty), `models.py` (199 lines), `views.py` (353 lines).
  - `models.py:12` reads `globalVars.appArgs.configPath` at import time (U8). `models.py:64-67` creates an empty `unicode.dic` in the NVDA user configuration folder when the file is missing, then `:68` reads it. `codecs.open` is used at `:66`, `:68` and `:154` (U9; the source of both baseline warnings).
  - `views.py:43` `SpeechSymbolsDialog`. `views.py:182` and `:217` crash on a `-` (None) field written by hand or by an older version (U7, `storage/refactor7.md` §5.2). No test covers `views.py`. `pyproject.toml:25-26` leaves it out of coverage "because the feature may be removed".
- Global plugin `addon/globalPlugins/WorldVoice/__init__.py`:
  - `:20` imports `SpeechSymbolsDialog`.
  - `:59-60` adds the tray submenu item "&Unicode Settings".
  - `:126-130` `popup_SpeechSymbolsDialog`, which says "SpeechSymbolsDialog have already been opened" when the dialog is open.
  - `:139-144` `script_popup_unicode_settings_dialog` ("popup unicode settings dialog"). It has no default gesture.
- Synth `addon/synthDrivers/WorldVoice/__init__.py`:
  - `:58` imports `SpeechSymbols`.
  - `:177` sets `self.speechSymbols = None`.
  - `:262-266` builds the symbols and loads `unicode.dic` on every synth start.
  - `:269-274` passes them to `LanguageDetector`.
  - The comment at `:290` lists "symbols" among the things stages may rely on.
- Detector:
  - `detection:104-106` takes and stores an optional `speechSymbols`.
  - `detection:152-155` is the per-character branch. For a character listed in the dictionary, the detector speaks the `replacement` text (except for digits). When `mode == 1` ("force"), the run switches to `symbol.language`; otherwise it stays on the current language.

What users lose: characters they listed in `unicode.dic` are no longer replaced by their custom text or forced into a language. Those characters go through NVDA's own symbol processing and normal script detection like every other character. NVDA's own Speech dictionaries and Punctuation/symbol pronunciation dialogs remain the supported ways to customize pronunciation.

### 1.2 Changes

Delete:

- `addon/generics/speechSymbols/` (all three files).

Edit:

- `addon/globalPlugins/WorldVoice/__init__.py`:
  - Remove the `:20` import, the `:59-60` menu item, `popup_SpeechSymbolsDialog` (`:126-130`) and `script_popup_unicode_settings_dialog` (`:139-144`).
  - The submenu keeps "&Settings" and "&File Import", in that order. The submenu is still inserted at position 2 of NVDA's menu (`:67-72`).
- `addon/synthDrivers/WorldVoice/__init__.py`:
  - Remove `:58`, `:177` and `:262-266`. Build the detector without the symbols argument (`:269-274`).
  - Update the comment at `:290` to stop mentioning symbols.
  - **Keep** `base_dir`/`sys.path.insert` (`:56-57`). The global plugin imports `generics.coreArchive` (`globalPlugins/WorldVoice/__init__.py:19`) and depends on this package putting the add-on root on `sys.path` (comment at `:12-13`; pinned by `tests/test_hygiene_guards.py:73-85`). Replace the line-58 import with a comment there saying why the path is still added.
- `detection:104-109`: the signature becomes `LanguageDetector(availableLanguages, *, settings, language)`. The `speechSymbols` parameter and attribute go away, and so does the branch at `detection:152-155`. A caller that still passes a second positional argument gets a `TypeError`.
- `pyproject.toml:25-26`: remove the coverage omit entry for `views.py` and its comment.

Keep:

- `addon/generics/coreArchive.py`. It is still used by `globalPlugins/WorldVoice/__init__.py:19` and `addon/installTasks.py:18-19`.
- The "Unicode Detection" settings panel (`addon/globalPlugins/WorldVoice/speechSettingsDialog.py:480-481`). It is a different feature with a similar name; nothing in it changes.
- `buildVars.py:61-62`. The `addon/generics/*/*.py` glob simply matches nothing afterwards. The main checkout also has an uncommitted user edit in `buildVars.py`, so this phase leaves the file alone.

### 1.3 Stored data: `unicode.dic`

Decided by orchestrator with the recommended default; user may override before merge: an existing `unicode.dic` in the NVDA user configuration folder is left on disk untouched. There is no migration, no deletion and no rename. After this phase WorldVoice no longer creates, reads or writes the file. Because of `models.py:64-67`, practically every existing user has this file, usually empty. The generic file name at the configuration root is one more reason not to delete it.

### 1.4 Gesture

A user who bound a gesture to "popup unicode settings dialog" keeps the entry in `gestures.ini`, but the gesture no longer does anything. NVDA looks the script up with `getattr` and ignores the `AttributeError` (`ref/nvda/source/scriptHandler.py:72-75`), so the key passes through without an error. The script disappears from the WorldVoice category of NVDA's Input gestures dialog.

### 1.5 DeprecationWarning guard

Decided by orchestrator with the recommended default; user may override before merge: once the two warnings are gone, add a pytest configuration to `pyproject.toml` (there is no pytest section today) with `filterwarnings = ["error::DeprecationWarning"]`, as `storage/refactor7.md` §7 suggests.

- Evidence: running today's suite with `-W error::DeprecationWarning` gives 2 failed and 2370 passed. The two failures are `tests/test_format_outputs.py::test_saved_symbol_lines` and `::test_invalid_symbol_line_warning`, both deleted by this phase.
- NVDA's own `codecs.open` in `characterProcessing.py` stays covered by the existing `filterwarnings("ignore:codecs.open:DeprecationWarning")` marks (`tests/test_pipeline_nvda_symbols.py:19-20`), because marks take precedence over the ini filter.
- Risk: mutmut runs pytest with the same configuration, so the plan must confirm that mutmut's clean run still passes with the guard on (§10.6).

## 2. Part B: restore "prefer the base language" in detection

Decided by the user (2026-10-23). This fixes a regression from `9816ce0` ("Refactor Unicode language detection", 2026-07-28); `git tag --contains 9816ce0` shows it first shipped in 6.2.

### 2.1 The order that was lost

Terms:

- **Current language**: `tmpLang`, the language detection has switched to within this text.
- **Base language**: `curLang`. It is the synth's language (`detection:141`), replaced by the language of the last `LangChangeCommand`/`WVLangChangeCommand`, or reset to the synth's language by one whose `lang` is None (`detection:145-147`).

The upstream detector picks a letter's language in this order:

1. The current language covers the script → stay (`upstream:149-151`).
2. The base language covers the script → the base language, as a full locale (`upstream:153`, which calls `find_language_for_charset(charset, curLang)`, and `upstream:176-179`).
3. The configured language for the script (`upstream:180-184`).
4. The first language of the script (`upstream:185`).

WorldVoice used the same order before `9816ce0` (`pre-9816ce0:196`, `:219-228`).

Today `_language_for_character` passes only the current language (`detection:136`), and `find_language_for_script` looks only at that language (`detection:111-126`). Step 2 is gone, so whenever the current language does not cover the script, the configured preference wins over the base language.

### 2.2 Observed regressions

Reproduced on the baseline through `tests/detector_harness.py`. `<x>` stands for an inserted `WVLangChangeCommand("x")`.

| # | Voices installed | Base | Preferences | Input | Today | Required |
|---|---|---|---|---|---|---|
| R1 | en_US, zh_TW, ja_JP | zh_TW | Han → ja (shipped default, `languageDetection/settings.py:18`) | `你好 hello 世界` | `你好 ` `<en>` `hello ` `<ja>` `世界` | … `<zh_TW>` `世界` |
| R2 | en_GB, en_US, zh_TW | en_GB | Han → zh_TW | `hi 你好 ok` | … `<en>` `ok` | … `<en_GB>` `ok` |
| R3 | en_US, ja_JP, zh_TW | ja_JP | Han → zh_TW | `漢字 hello 漢字` | … `<zh_TW>` `漢字` | … `<ja_JP>` `漢字` |
| R4 | en_US, zh_TW, ja_JP | zh_TW | Han → ja | `[Lang("ja"), "中", Lang(None), "a中"]` | … `<en>` `a` `<ja>` `中` | … `<en>` `a` `<zh_TW>` `中` |

What users hear:

- R1: a Chinese-default user with the shipped default (Han → ja) and a Japanese voice installed hears the Chinese after an English word read by the Japanese voice.
- R2: an en_GB user hears English after a Chinese phrase with the voice assigned to "en", which may not be their en_GB voice. Every later lookup also goes through `en` instead of `en_GB` (`roles.py:40-48`).
- R3: Japanese kanji after an English word are read by the Chinese voice.

### 2.3 Required behavior

For a letter (not a digit, not Common/Inherited, `detection:129-135`) of script S with candidate languages `SCRIPT_LANGUAGES[S]` (`detection:64-93`):

1. If S has no candidates → the current language (unchanged, `detection:114-115`).
2. If the current language covers S (§3.3) → the current language.
3. If the base language covers S (§3.3) → the base language, returned exactly as given (full locale, hyphenated forms such as `ar-WW` kept).
4. If the configured language for S has its primary subtag in the candidates and in `availableLanguages` → the configured value (unchanged, `detection:118-122`).
5. The first candidate, in tuple order, that is in `availableLanguages` → that candidate (unchanged, `detection:123-125`).
6. Otherwise → the current language (unchanged, `detection:126`).

Step 6 is a deliberate divergence from upstream, which returns the base language there (`upstream:178-179`). That behavior stays as it is today.

The command is still emitted only when the primary subtag changes (`detection:160-165`). The emitted type stays `WVLangChangeCommand`.

Suggested shape (the plan may choose another): one private predicate "language covers script S", plus an optional `base_language=None` keyword on `find_language_for_script`. Existing two-argument calls (`tests/test_language_detector.py:83`, `:87`) keep working, and `_language_for_character` passes `base_language` (`detection:128`, `:158`).

### 2.4 `process_for_spelling`

`detection:172-196` is WorldVoice's own spelling splitter. Upstream has no equivalent. `patchedSpeakSpelling` uses it when WorldVoice detection is on and NVDA's "trust voice's language" is set (`addon/synthDrivers/WorldVoice/__init__.py:335-340`). Its `default_language` (the spelling locale, or the synth language) plays the role of the base.

- **Same gap, but not a regression.** `detection:185` passes only the current language. Before `9816ce0` the spelling path also passed only the current language (`pre-9816ce0:260`), so this is a long-standing inconsistency rather than something `9816ce0` broke.
- **Mostly masked today.** Whitespace and digits reset to the base (`detection:178-179`), and `detection:187-188` rewrites any result with the base's primary subtag to the base locale. The gap shows only when a letter of the base's script directly follows a letter of another script, with no whitespace in between, and the preference names a different language:
  - base ja_JP, Han → zh_TW, `"a漢"` → today `[("a","en"), ("漢","zh_TW")]`;
  - base zh_TW, Han → ja, `"a中"` → today `[("a","en"), ("中","ja")]`.
- **What the locale controls.** It picks NVDA's character descriptions and symbol names (`ref/nvda/source/speech/speech.py:472-477`, `:535-536`). When NVDA's automatic language switching is on, the locale also becomes the `LangChangeCommand` that the main detector sees for each spelled character.

Decided by orchestrator with the recommended default; user may override before merge: `process_for_spelling` uses the same steps (§2.3, §3.3), with `default_language` as the base. Both paths then answer the same way. Effects:

- the two examples above become `("漢","ja_JP")` and `("中","zh_TW")`;
- the existing expectation `process_for_spelling("a中 1", "ja")` changes from `[("a","en"), ("中","zh"), (" 1","ja")]` to `[("a","en"), ("中 1","ja")]` (§10.3).

After this change `detection:187-188` is dead code. A target with the base's primary subtag can only come from steps 2 or 3 (which return the base exactly) or from the current language (which by induction is the base exactly). Steps 4 and 5 can return such a primary only if the base covers the script and is available, in which case step 3 has already returned it. A 20,000-case random check on a prototype found no counterexample. Remove the two lines and pin the invariant with a property test (§10.5): "every spelling run whose primary subtag equals the base's carries the base locale exactly".

## 3. Part C: a language with no installed voice does not count as covering a script

Decided by the user (2026-10-23).

### 3.1 Upstream and today

Upstream builds its script coverage only for installed languages (`upstream:54-92`, availability at `:57`), so a language without a voice covers nothing. WorldVoice checks coverage against the static `SCRIPT_LANGUAGES` lists (`detection:112-115`) without looking at `availableLanguages`. So when a `LangChangeCommand` names a language with no voice, detection stays on it.

Downstream, `lang_cmd_to_voice` (`pipeline/__init__.py:662-675`) asks `VoiceManager.getVoiceNameForLanguage` (`voiceManager.py:295-299`), which falls back to the main voice. For example, a Chinese main voice reads German text.

| # | Voices | Base | Input | Today | Required (same as upstream) |
|---|---|---|---|---|---|
| C1 | en_US, zh_TW | en_US | `[Lang("de_DE"), "hallo 你好"]` | `<de_DE>` `hallo ` `<zh>` `你好` | `<de_DE>` `<en>` `hallo ` `<zh>` `你好` |
| C2 | en_US, zh_TW | en_US | `[Lang("de_DE"), ", hallo"]` | `<de_DE>` `, hallo` | `<de_DE>` `, ` `<en>` `hallo` |
| C4 | fr_FR, zh_TW, en_US | zh_TW | `[Lang("de_DE"), "hallo"]`, Latin → fr | `<de_DE>` `hallo` | `<de_DE>` `<fr>` `hallo` |

(C3 is in §10.1: it has no Latin voice at all and does not change.)

### 3.2 What `availableLanguages` contains

- The synth passes `self._voiceManager.allLanguages` (`addon/synthDrivers/WorldVoice/__init__.py:270`). That is `catalog.all_languages` (`voiceManager.py:276-278`): the sorted primary subtags of every voice published by every engine that opened (`voiceCatalog.py:16-20`, `:36-41`). The detector reduces each to a primary subtag again (`detection:109`).
- It counts **installed** voices. It does not depend on:
  - KeepMainLocaleEngineConsistent: voices of other engines stay counted although the role list hides them (`mainLocalePolicy.py:35-39`);
  - whether a role is assigned for the language (`roles.py:40-48`).
- **The synth's default language is always available.**
  - The synth's `language` is `availableVoices[self.voice].language` (`ref/nvda/source/synthDriverHandler.py:253-254`).
  - Every voice the synth reports comes from the same catalog table (`voiceCatalog.py:40`, `voiceManager.py:208-213`, `:295-299`, `addon/synthDrivers/WorldVoice/__init__.py:406-409`).
  - A spec's `locale` defaults to its `language` (`compat/engineAdapter.py:133`); VE and Cerence set both to the same value (`driver/VE/__init__.py:1007-1008`, `driver/Cerence/__init__.py:1017-1018`).
- The list is fixed per synth instance. Engines open only while the synth is built (`voiceManager.py:81-91`), and any change to engines or voices reloads the synth.

### 3.3 Required behavior

"Language L covers script S" means: `primary(L)` is in `SCRIPT_LANGUAGES[S]` **and** `primary(L)` is in `availableLanguages`. Steps 2 and 3 of §2.3 use this predicate. Steps 4 and 5 already check availability. Edge cases:

- No available candidate for S → step 6 keeps the current language, so no command is inserted (unchanged). Example: only zh_TW installed, `[Lang("de_DE"), "hallo 你好"]` stays `<de_DE>` `hallo ` `<zh>` `你好`; Greek with no Greek voice stays in the current language.
- Common and Inherited characters (punctuation, spaces, combining marks) stay in the current language even when it is unavailable (unchanged, `detection:133-135`).
- Digits still go to the base language when "Ignore numbers" is off, even when the base has no voice (unchanged, `detection:129-132`). `[Lang("de_DE"), "hallo 12"]` becomes `<de_DE>` `<en>` `hallo ` `<de_DE>` `12`, the same as upstream (`upstream:117-140`), so the digits go back to the main voice. This is a known limitation (§11, Q6).
- In spelling, whitespace and digits still use the spelling locale (`detection:178-179`). With an unavailable locale, `"a b"` in de_DE becomes `[("a","en"), (" ","de_DE"), ("b","en")]` instead of one de_DE run. Spelling already speaks each character separately (`ref/nvda/source/speech/speech.py:350-364`); only the locale of the space changes.
- A language that has an installed voice but no role still counts as available, so its text is still read by the main voice (§11, Q4).

## 4. Non-goals

Nothing below changes, and the characterization tests in §10.1 pin the behavior where it matters:

- Unicode script classification (`languageDetection/script_data.py` is a protected path, `DEVELOPMENT_WORKFLOW.md` §7; `scripts.py` is untouched).
- Common/Inherited characters staying in the current language.
- Digit handling: the base language, or ignored when "Ignore numbers" is set.
- The deterministic candidate order of `SCRIPT_LANGUAGES` (for example `ru` before `uk`).
- The Arabic preference key (`languageDetection/settings.py:19`, `:23-27`) and every other preference key and default.
- The emitted command type (`WVLangChangeCommand`) and the rule that only a change of primary subtag emits a command.
- The availability check on the configured language (WorldVoice already skips a configured language without a voice; upstream does not, `upstream:180-184`).
- Step 6 keeping the current language instead of upstream's base language.
- Any engine's language-code table, the voice manager, roles and the pipeline stages.
- Upstream drivers under `driver/<Engine>/driver/` and `driver/sonic/`.
- The "Unicode Detection" panel.

## 5. User-visible changes

- The WorldVoice submenu in NVDA's menu has two items, "Settings" and "File Import"; "Unicode Settings" is gone.
- The WorldVoice category of Input gestures loses "popup unicode settings dialog". A gesture already bound to it does nothing.
- Custom entries in `unicode.dic` stop having any effect. The file stays on disk.
- After a run in another script, mixed-language text returns to the main or document language, not the per-script preference:
  - R1: Chinese after an English word is read by the Chinese voice, not the Japanese one;
  - R2: an en_GB user keeps the en_GB locale;
  - R3: Japanese kanji after English are read by the Japanese voice.
- When a document marks a language with no installed voice (NVDA's automatic language switching on), its letters are read by the voice of the configured or first available language of their script, not by the main voice. Digits in such a passage still go to the main voice.
- Spelling a letter of the base script right after a letter of another script uses the base locale's character descriptions.
- No new settings, no new strings, no changed defaults.

## 6. Affected layers

- Core: `languageDetection/__init__.py` (Parts A, B, C). It is shared by all engines, so it belongs in core (`DEVELOPMENT_WORKFLOW.md` §3.1).
- Synth composition: `synthDrivers/WorldVoice/__init__.py` (Part A only).
- Global plugin: `globalPlugins/WorldVoice/__init__.py` (Part A only).
- `addon/generics/speechSymbols/` deleted.
- Engines: no engine wrapper changes. The behavior change is audible with every engine that has voices for more than one language (VE, Cerence, OneCore, SAPI5, eSpeak, RHVoice, and the external Neural plugin).

## 7. Strings, translations and documentation

New strings: none.

Removed strings (25): the 21 strings in `views.py` and `models.py`, plus four in the global plugin:

- "&Unicode Settings";
- "Unicode Settings.";
- "SpeechSymbolsDialog have already been opened";
- "popup unicode settings dialog".

An AST scan of every other add-on source confirms that none of the 25 msgids (for example "Language", "Error", "&Add", "Re&move") is used anywhere else.

`addon/locale/zh_TW/LC_MESSAGES/nvda.po` (the only catalog maintained here, `DEVELOPMENT_WORKFLOW.md` §6):

- Delete the 25 entries outright, following the precedent of `a4629a1` (an entry is removed together with its option, not kept as `#~`).
- Each entry has exactly one source reference:
  - lines 23-125: the 21 `models.py`/`views.py` entries, including the `msgctxt "speechSymbols"` entry "&Filter by:";
  - lines 406-412: two entries;
  - lines 441-443: one entry;
  - lines 449-451: one entry.
- Run `msgfmt --check` afterwards.
- Other locales are left to their translators. Their now-unused entries are harmless.

Documentation. Decided by orchestrator with the recommended default; user may override before merge:

- No readme mentions the dialog, the menu item or `unicode.dic`, so Part A needs no documentation change.
- For Parts B and C, extend the "Assumed language for character sets" bullet in `readme.md:60` and `addon/doc/zh_TW/readme.md:60`, the two documents maintained here (as in `f79a16c`):
  - EN, appended: "WorldVoice uses this language only when neither the language being read nor the main language (the main speech role's language, or the language the document marks) is a language of that character set with an installed voice. Languages without an installed voice are skipped."
  - zh_TW, appended: 「只有在目前朗讀的語言與主要語言（主要語音角色的語言，或文件標示的語言）都不是該字元集中已安裝語音的語言時，才會使用這個設定；沒有安裝語音的語言會被略過。」
- The changelog section of `readme.md:68-` is not edited in this phase; §5 is the source for the release notes.

## 8. Settings, data, compatibility, error handling

- Configuration keys: none added, removed or renamed. `config.conf.spec["WorldVoice"]` (`addon/synthDrivers/WorldVoice/__init__.py:62-79`) is unchanged.
- `unicode.dic`: §1.3.
- API: `LanguageDetector` loses its second positional parameter. Its only production caller is the synth (`__init__.py:269`). The external Neural plugin does not construct a detector or touch the symbols (no reference to `LanguageDetector`, `speechSymbols` or `generics` in `ref/Neural`).
- Error handling: one failure point at synth start disappears, the load of `unicode.dic` (`__init__.py:262-266`). Detection adds no new error path. With no voices, construction already fails earlier (`voiceManager.py:89-90`).

## 9. Risks

- Detection is a core decision module used for every utterance. The change is small (one extra step, one extra predicate), but it changes output in common mixed-language text. Hence characterization first, property tests and a mutmut run.
- Three existing tests encode the regressed behavior (§10.3). They must change in the same commit as the fix, with the reason in the commit message.
- The DeprecationWarning guard can turn a future NVDA or Python deprecation into a test failure. That is the intent, but the reviewer should know.

## 10. Test plan

Work order: characterization (green on the baseline) → red tests for B and C → the detector change → removal tests for A → removal. Each red test must fail on the baseline for the stated reason before the fix.

### 10.1 Characterization (must pass before and after)

All through `tests/detector_harness.py` / `tests/test_language_detector.py`. Each output below was checked to be identical on the baseline and on a prototype of §2.3 + §3.3.

| Case | Voices | Base | Input | Output |
|---|---|---|---|---|
| full-width punctuation stays in the run | en_US, zh_TW | en_US | `hi 你好，世界。` (Han → zh_TW) | `hi ` `<zh_TW>` `你好，世界。` |
| Korean Hanja stays ko | en_US, ko_KR, ja_JP | ko_KR | `한국 漢字 한국` | unchanged, no command |
| Hindi | en_US, hi_IN | en_US | `hi नमस्ते` | `hi ` `<hi>` `नमस्ते` |
| Myanmar | en_US, my_MM | en_US | `hi မြန်မာ` | `hi ` `<my>` `မြန်မာ` |
| hyphenated voice code | en_US, ar-WW | en_US | `hi مرحبا` | `hi ` `<ar>` `مرحبا` |
| ru/uk deterministic | en_US, uk_UA, ru_RU | en_US | `hi привет` | `hi ` `<ru>` `привет` |
| script with no voice | en_US | en_US | `hi Ελληνικά` | unchanged, no command |
| digits go to the base | en_US, zh_TW | en_US | `中12` | `<zh_TW>` `中` `<en_US>` `12` |
| digits ignored | same, ignore numbers | en_US | `中12` | `<zh_TW>` `中12` |
| no available Latin voice (C3) | zh_TW | zh_TW | `[Lang("de_DE"), "hallo 你好"]` | `<de_DE>` `hallo ` `<zh>` `你好` |

The existing tests that stay green unchanged also count as characterization:

- `test_digits_follow_the_ignore_numbers_setting`;
- `test_language_commands_reset_the_base_language`;
- `test_spelling_without_locale_uses_the_synth_language`;
- `test_one_settings_read_per_spelling`;
- `test_configured_script_language_wins_only_when_available`;
- `test_script_without_candidates_keeps_the_current_language`;
- `test_language_is_read_per_call`;
- the property test at `tests/test_language_detector.py:143-166`.

### 10.2 Red tests

- B: R1, R2, R3 and R4 from §2.2.
- Spelling:
  - base ja_JP, Han → zh_TW: `"a漢"` → `[("a","en"), ("漢","ja_JP")]`;
  - base zh_TW, Han → ja: `"a中"` → `[("a","en"), ("中","zh_TW")]`.
- C: C1, C2 and C4 from §3.1.
- Spelling with an unavailable locale: `process_for_spelling("a b", "de_DE")` with en_US and zh_TW installed → `[("a","en"), (" ","de_DE"), ("b","en")]`.

### 10.3 Existing expectations that change (they pin the regression)

- `tests/test_language_detector.py:35-37` `test_mixed_scripts_switch_at_script_boundaries`: `"ok"` now follows `<en_US>`, not `<en>`.
- `tests/test_language_detector.py:106-117` `test_one_settings_read_per_sequence`: `"abc "` now follows `<en_US>`, not `<en>`.
- `tests/test_language_detector.py:75-77` `test_spelling_with_locale`: `[("a","en"), ("中 1","ja")]`.

A prototype run of the full suite changed nothing else: the only other failure was `test_mode_one_symbol_speaks_its_replacement_in_its_language`, which Part A deletes.

### 10.4 Part A tests

Updates:

- `tests/test_global_plugin_menu.py:25-44`: the submenu is `[("&Settings","Settings."), ("&File Import","Import File.")]` with two bindings. Delete `test_unicode_script_opens_the_symbols_dialog_once` (`:84-92`). Add a test that the plugin has no `script_popup_unicode_settings_dialog` or `popup_SpeechSymbolsDialog` attribute.
- `tests/ui_harness.py:877-879`: drop the `generics.speechSymbols` stubs and `env.symbols_dialog`. Keep `generics` and `generics.coreArchive` (`:875-876`).
- `tests/test_language_detector.py`:
  - `make_detector` (`:15-22`) and the two direct constructions (`:109-114`, `:122-127`) stop passing `None`;
  - delete `test_mode_one_symbol_speaks_its_replacement_in_its_language` (`:52-55`);
  - add a test that a second positional argument raises `TypeError`.
- `tests/test_worldvoice_speak.py:182` and `tests/test_worldvoice_pipeline_settings.py:201`: drop `speechSymbols`.
- `tests/test_runtime_composition.py:592-594`: drop the `generics` stubs, since the real `__init__.py` no longer imports them.
- `tests/test_worldvoice_lifecycle.py`:
  - drop the `SpeechSymbols` stub (`:87-91`, `:177`); the `LanguageDetector` stub (`:93-95`) loses its `symbols` parameter;
  - the `"symbols"` failure case (`:201`, `:207`, `:222-224`) was the only injection point after the voice manager exists. Replace it with a `"detector"` case in which the `LanguageDetector` stub raises, keeping the assertion that the engine is stopped after the bridge;
  - rename `test_stages_register_after_symbols_and_detector` (`:252-256`) and drop its symbols assertion.
- `tests/test_format_outputs.py`: delete `MODELS`, the `models` fixture and the three symbol tests (`:10`, `:22-78`); keep `test_speech_command_reprs`.

Static guard (in `tests/test_hygiene_guards.py` or a new small test file):

- `addon/generics/speechSymbols` does not exist;
- no add-on source imports a module starting with `generics.speechSymbols`;
- no add-on source contains the string `unicode.dic`.

### 10.5 Property tests (Hypothesis)

Over random sequences of mixed-script text, language commands (including None, unavailable and hyphenated codes), random installed voice sets and random preferences:

1. Every `WVLangChangeCommand` that detection inserts directly before text whose first character is a letter names a language whose primary subtag is installed (Part C).
2. When the base language covers the script of that letter (§3.3), the inserted command names the base exactly (Part B). Track the base across `LangChangeCommand`s as `detection:145-147` does.
3. `process_for_spelling`: every run whose primary subtag equals the base's carries the base locale exactly. This pins the invariant behind removing `detection:187-188`.
4. The existing "only inserts language changes" property (`tests/test_language_detector.py:143-166`) stays, extended to the new voice sets.

### 10.6 Mutation testing

- Run mutmut on `addon/synthDrivers/WorldVoice/languageDetection/__init__.py` on Linux, with at most 3 workers. A memory watchdog stops pytest when MemAvailable falls below 3 GB.
- Decided by orchestrator with the recommended default; user may override before merge: add the file to `[tool.mutmut] source_paths` (`pyproject.toml:38-50`) permanently, since it is a core decision module.
- Confirm that mutmut's clean run passes with the §1.5 warning guard.
- Record surviving mutants and the reason for each in the review or in the implementation notes of this spec.

### 10.7 Verification (`DEVELOPMENT_WORKFLOW.md` §7)

- Full suite: passed count compared with 2372. The expected delta is the removed and added tests, 0 skipped, and **0 warnings**.
- `prek run --all-files`.
- `git diff --check`.
- The protected-path checks, both empty.
- `msgfmt --check` on the zh_TW catalog.
- `pytest tests --cov`: coverage must not drop; the `views.py` omit is gone together with the file.

### 10.8 Windows / NVDA manual items

These have not been verified on Linux; report them as not done until someone checks them.

1. NVDA menu → WorldVoice: two items, "Settings" and "File Import". Arrow-key navigation reads them; both open as before.
2. Input gestures → WorldVoice: no "popup unicode settings dialog". A profile whose `gestures.ini` binds a key to it starts without errors in the NVDA log, and pressing the key does nothing.
3. A profile with a non-empty `unicode.dic`: WorldVoice starts and the file is unchanged afterwards (same size and timestamp). On a fresh profile no `unicode.dic` is created.
4. With VE or Cerence plus OneCore, main voice zh_TW, CJK preference ja and a Japanese voice installed: read `你好 hello 世界`; 世界 is read by the Chinese voice.
5. Main voice ja_JP, CJK preference zh_TW: `漢字 hello 漢字` is read entirely by the Japanese voice, apart from "hello".
6. NVDA automatic language switching on, a web page with `lang="de"` and no German voice: the German text is read by the English role voice, and Chinese in it by the Chinese voice. Digits in the German passage are read by the main voice (known limitation).
7. Spelling (NVDA+numpad 2 twice, or reading by character) of `a漢` with main voice ja_JP and "trust voice's language" on: 漢 uses the Japanese description.
8. The NVDA log at synth load has no "SpeechSymbols" timing lines and no errors.

## 11. Open questions and the defaults applied

- **Q1 `unicode.dic` on disk.** Default: leave it untouched (§1.3). Decided by orchestrator with the recommended default; user may override before merge.
- **Q2 DeprecationWarning guard.** Default: add `error::DeprecationWarning` (§1.5). Decided by orchestrator with the recommended default; user may override before merge.
- **Q3 Spelling path.**
  - Default: `process_for_spelling` gets the same order and availability rule, and the now-dead normalization `detection:187-188` is removed (§2.4). Decided by orchestrator with the recommended default; user may override before merge.
  - Note that this is not a `9816ce0` regression: the spelling path never preferred the base (`pre-9816ce0:260`).
  - Alternative: leave spelling unchanged. The two paths then disagree for adjacent mixed scripts, and an unavailable spelling locale keeps sending letters to the main voice's locale.
- **Q4 Meaning of "available".**
  - Default: installed voices of every opened engine (`allLanguages`, §3.2), as upstream does, and as steps 4 and 5 already use. Decided by orchestrator with the recommended default; user may override before merge.
  - Consequence: a language with an installed voice but no role assignment, or a voice hidden by KeepMainLocaleEngineConsistent, still counts. Its text is still read by the main voice (`voiceManager.py:295-299`).
  - Alternative: count only languages with a role assigned. This needs the detector to follow role changes at runtime, and it would make detection depend on role settings, so it is not recommended in this phase.
- **Q5 Documentation.**
  - Default: extend the "Assumed language" bullet in `readme.md` and the zh_TW readme (§7); no changelog edit. Decided by orchestrator with the recommended default; user may override before merge.
  - Both readmes (and the other locales' readmes) still describe an "Ignore common punctuation during language detection" option at `readme.md:58` and `addon/doc/zh_TW/readme.md:58`. No such option exists any more: there is no key in `languageDetection/settings.py:15-21`, and its zh_TW entry is obsolete (`#~` in `nvda.po`). Default: out of scope, reported to the user, not changed here.
- **Q6 Digits after an unavailable base language.** These still switch back to that language (§3.3), as upstream does. Default: unchanged, because digit handling is a non-goal. Decided by orchestrator with the recommended default; user may override before merge.
- **Q7 mutmut source list.** Default: add `languageDetection/__init__.py` permanently (§10.6). Decided by orchestrator with the recommended default; user may override before merge.

## 12. Findings worth knowing before the plan

- The synth's `sys.path` insertion (`__init__.py:56-57`) must outlive the import it was written for. The global plugin's `generics.coreArchive` import depends on it.
- The `unicode.dic` loader creates the file on every start (`models.py:64-67`), so nearly all existing users have one, usually empty.
- Three detector tests encode the regressed behavior (§10.3). The lifecycle test used symbol loading as its "fails after the voice manager exists" injection point and needs a replacement (§10.4).
- `availableLanguages` is broader than "has a voice that will actually be used" (Q4). Part C removes the most common way the main voice ends up reading a foreign language, but not every way.
- Upstream parity was checked with a throwaway harness: C1, C2 and the digit limitation in §3.3 match upstream output exactly. The remaining differences from upstream are deliberate and unchanged:
  - full-width punctuation, Common-script handling and the newer scripts (Hindi, Myanmar, Han Extension A);
  - the configured-language availability check;
  - step 6 keeping the current language.
