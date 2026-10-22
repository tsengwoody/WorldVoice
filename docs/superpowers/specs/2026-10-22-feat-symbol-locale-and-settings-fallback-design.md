# Symbol names from the voice's locale, and a default for every invalid stored pipeline setting

Date: 2026-10-22.
Base: `master` `b244821` (number-unify delivered). Branch: `feat/symbol-locale-and-settings-fallback`.
Flow: lightweight normal flow (DEVELOPMENT_WORKFLOW.md §3), one final Fable review.
Status: every decision below was made by the user in the discussion of 2026-10-22 unless it says otherwise. The decisions file is the orchestrator's `next-symbol-locale.md`.

## 1. Problem and goal

**Part 1.** In number and group modes a symbol inside a number is replaced by NVDA's name for it, looked up by `_symbol_locale` (`addon/synthDrivers/WorldVoice/pipeline/__init__.py:94-108`). WorldVoice's languages are bare codes (`"zh"`, `"pt"`, `"nb"`), but NVDA's symbol tables for these exist only with a country (section 2). `_symbol_locale` borrows NVDA's interface country only when the base language matches. Otherwise NVDA falls back to English, and a Chinese voice says "times" and "dot". The voice that speaks the number knows its full locale (`VoiceSpec.locale`, `runtime/models.py:14-21`). Goal: look the name up in that locale.

**Part 2.** NVDA validates a stored value against the confspec on every read and raises configobj's `ValidateError` for a value outside it (section 2). `ConfigPipelineRepository.load` (`pipeline/settings.py:341-345`) does not catch that error. A hand-edited or out-of-range value therefore stops WorldVoice from loading: the synth reads the pipeline settings in its constructor (`synthDrivers/WorldVoice/__init__.py:248`). The group size also keeps a confspec minimum of 1 (`stored_min_value`, `pipeline/settings.py:77-79, 170`) only so that an old stored 1 still validates. Goal: every invalid stored pipeline value reads as that key's default, and `group_size` takes the plain range 2..10.

Non-goals:
- symbols outside numbers;
- the voice, detection and engine config sections;
- writing a repaired value back.

## 2. NVDA facts

- **Symbol lookup.** `characterProcessing.processSpeechSymbol(locale, symbol)` (`ref/nvda/source/characterProcessing.py:728-742`) fetches the locale's processor with `fetchLocaleData(locale)`. Fallback is on, so `"zh_SG"` tries `"zh_SG"` and then `"zh"` (`:46-74`). When both fail it **silently** uses `"en"`. So a passed locale cannot tell us whether NVDA really had a table for it.
- **Where the tables are.**
  - The mandatory built-in dictionary is `os.path.join(globalVars.appDir, "locale", "{locale}", "symbols.dic")` (`characterProcessing.py:893-901`).
  - Its `availableLocales` globs that pattern (`:836-846`).
  - A locale without that file raises `FileNotFoundError`, and `_getSpeechSymbolsForLocale` then raises `LookupError` (`:413-426`, `:819-826`).
- **The tables at `7d25bc76e`.** `ref/nvda/source/locale/*/symbols.dic` exists for 61 locales. Among them are `zh_CN`, `zh_HK`, `zh_TW`, `pt_BR`, `pt_PT`, `nb_NO`, `nn_NO`, `de`, `de_CH`, `es`, `es_CO` and `en`. There is none for `zh`, `pt`, `nb`, `nn`, `zh_SG` or `en_US`.
- **Names differ per country.** `×` is `乘以` in zh_TW, `乘号` in zh_CN and `乘號` in zh_HK. In en it is `times`.
- **Normaliser.** `languageHandler.normalizeLanguage` (`ref/nvda/source/languageHandler.py:444-457`):
  - `-` becomes `_`;
  - the language is lower-cased and the country upper-cased;
  - `x-…` gives `None`.
- **Validation on read.** `AggregatedSection.__getitem__` validates every leaf with a spec: `self.manager.validator.check(spec, val)` (`ref/nvda/source/config/__init__.py:1269-1274`). `get` catches only `KeyError` (`:1246-1250`), so the validation error reaches the caller.
- **The validator** is configobj's `Validator` (`config/__init__.py:28`). Its errors subclass `configobj.validate.ValidateError`. NVDA itself imports the class from there (`argsParsing.py:47`, `config/featureFlag.py:18-19`). configobj ships a top-level `validate` shim for older imports. The messages quote the stored value: `the value "11" is too big.`, `the value "abc" is of the wrong type.`
- **Voices.** `VoiceManager.getVoiceNameForLanguage` (`voiceManager.py:295-299`) returns the assigned voice when it exists, otherwise the default voice. The locale comes from the engine as `voice.get("locale", language)` (`compat/engineAdapter.py:133`), so it may be a bare code, `zh-TW` or `zh_TW`.

## 3. Design

### 3.1 Voice locale callback

- **`SpeechContext.voice_locale_for_language: Callable[[str], str | None]`** (`pipeline/context.py`). The default is `lambda language: None`, as for `voice_name_for_language`. `GENERIC_CONTEXT` (other synths) keeps the default.
- **`VoiceManager.getVoiceLocaleForLanguage(language) -> str | None`** returns the `VoiceSpec.locale` of `getVoiceNameForLanguage(language)`, or `None` when that name has no spec. A language with no usable voice therefore gives the default voice's locale (Q1 A, point 2).
- **`SynthDriver.speech_context`** (`__init__.py:357-367`) passes `voice_locale_for_language=manager.getVoiceLocaleForLanguage`.

### 3.2 Symbol locale (`pipeline/__init__.py`)

- **`_has_symbol_table(locale: str) -> bool`** is true when `os.path.join(globalVars.appDir, "locale", locale, "symbols.dic")` is a file. This is exactly the path NVDA's mandatory dictionary uses. A guard test pins NVDA's path against `ref/nvda`.
- **`_symbol_locale(language: str | None, voice_locale: str | None = None) -> str`.** When `voice_locale` normalises with `languageHandler.normalizeLanguage` to a locale that `_has_symbol_table` accepts, return it. Otherwise apply the current rule unchanged:
  - `None` gives `speech.getCurrentLanguage()`;
  - `-` becomes `_`;
  - a bare code borrows NVDA's interface country when the bases match;
  - NVDA's own fallback does the rest.
- **The decisions this applies:**
  - point 1: the voice locale wins over the NVDA interface country;
  - D1 and D2: no table, a bare code without a table, or an `x-` locale gives the current rule;
  - D2 is `Decided by orchestrator with the recommended default; user may override before merge`.
- **`_symbol_namer(voice_locale_for_language)`** calls `voice_locale_for_language(language)` and `_symbol_locale` at most once per language per stage run (point 5). It does not call the callback for a `None` language. `inject_number_mode` passes `ctx.voice_locale_for_language`.
- **The language whose voice is asked** is unchanged from number-unify:
  - the number language when roles are supported and it is not `"default"`;
  - otherwise the language in force, following `WVLangChangeCommand` and NVDA's `LangChangeCommand` (`cmd.lang or ctx.language`).
- **D4/D5.** Only symbol names inside numbers change. NVDA's own `LangChangeCommand` inside WorldVoice follows the same rule, because WorldVoice picks the voice for it. `Decided by orchestrator with the recommended default; user may override before merge`.
- **Scope "all" and other synths** are unchanged (point 3). `GENERIC_CONTEXT` gives no voice locale, so the language in force (NVDA's `LangChangeCommand`, else `speech.getCurrentLanguage()`) is used.

### 3.3 Reading stored settings (`pipeline/settings.py`)

- **The error class.** `ValidateError` is imported from `configobj.validate`, then from the top-level `validate` shim. If both imports fail, it falls back to `Exception`, so WorldVoice still loads with any configobj NVDA ships.
- **`read_stored(section, key, default) -> Any`** returns `section.get(key, default)`. On `ValidateError` it returns `default`.
  - It logs one `log.debugWarning` per key and stored value, with the key and configobj's message, which quotes the stored value (D3). The message is not repeated on every later read: stages read the settings for every utterance.
  - It writes nothing back (Q3 A). It tells an optional `on_fallback(key)` callback which key fell back.
- **The next panel save rewrites the key (Q3 A).**
  - `ConfigPipelineRepository.load` collects the keys that fell back as `fallen_back`. Every load replaces the set, and `save` drops a key once it has written it.
  - `PipelineSettingsService.update` writes a key in `fallen_back` even when its value equals what `get` returned. The panel shows the default and saves every value it shows, so its save writes the default over the refused value.
  - NVDA accepts the write: `AggregatedSection.__setitem__` validates the new value and compares it with the old one unvalidated (`checkValidity=False`, `config/__init__.py:1355-1365`).
  - A save that does not name the key leaves it. The slider ring, for example, saves only the key it changes.
  - The log and engine panels write every checkbox, so their save rewrites a refused switch the same way. The log enable flag is written only when logging is turned on or off, so a refused enable flag stays until then.
- **`_get_value`** delegates to `read_stored` with the key's default. Its `AttributeError` branch goes: NVDA's `AggregatedSection` and configobj sections both have `get`. `load` therefore falls back key by key; one bad key leaves the others as stored. This is decision A: every pipeline key.
- **Other readers that bypass the repository:**
  - the log stage switches, `_run_logged` (`pipeline/__init__.py:852-855`);
  - the log enable flag, `PipelineLogService.enabled` (`globalPlugins/WorldVoice/pipelineLog.py:24-25`);
  - the Log Record and engine panels' checkbox read (`speechSettingsDialog.py:103`).
  These read the `log` (and `engine`) section directly and raise the same error. They use `read_stored` with the confspec default `False`. The panels' choice read (`:91-95`) already catches every error. Every other panel reads through `pipeline_settings.get()`.
- **`group_size`:**
  - the confspec becomes `integer(default=3,min=2,max=10)`;
  - `stored_min_value` is removed: the field, its confspec branch, the guard checks and the tests;
  - a new field `reset_out_of_range: bool = False` is set only on `group_size`.
- **The clamp in `convert`.** For `group_size`, `convert` returns the default 3 for an int outside 2..10 instead of clamping. Other ints keep their clamp.
  - Why: through NVDA, a stored value outside the confspec never reaches `convert`, because validation refuses it first and `read_stored` gives the default.
  - So `convert` only meets out-of-range values written through `update` (the slider ring, the panels) or read from a non-validating section. For the 0..100 sliders, clamping a written value is the existing, expected behaviour.
  - For the group size the user's rule is "outside 2..10 reads as 3, not clamped", and `convert` applies it the same way on both paths. The spin control cannot produce such a value on Windows.
  - A non-int is the validator's case (`VdtTypeError` → 3).

## 4. What users notice

The examples assume number mode, `2×3`, and NVDA's tables at `7d25bc76e`.

| Situation | Before | After |
|---|---|---|
| zh voice with locale `zh-TW` (for example OneCore), NVDA interface en | `"zh"` gets no country, so `times` | `zh_TW`: `乘以` |
| zh_CN voice, NVDA interface zh_TW | `"zh"` borrows TW: `乘以` | `zh_CN`: `乘号` |
| zh_SG voice | `"zh"`: `乘以` with NVDA zh_TW; `times` with NVDA en | no zh_SG table, so the current rule; same as before |
| voice locale a bare `zh` | current rule | no `zh` table, so the current rule; same as before |
| number language en, no en voice, default voice zh_TW | `times` (spoken by the zh voice) | the default voice's locale `zh_TW`: `乘以` |
| number language en, en_US voice | `times` | no en_US table, so the current rule: `"en"`, `times` |
| scope "all", another synth | NVDA `LangChangeCommand` language, else `getCurrentLanguage()` | unchanged |
| stored `group_size` 1 | validates (min 1), clamped to 2 | refused by NVDA, reads 3, one debug warning |
| stored `group_size` 11 or `"abc"` | NVDA raises, so WorldVoice fails to load | reads 3, one debug warning |
| stored `number_wait_factor` 150 or `"x"` | NVDA raises, so WorldVoice fails to load | reads 10, one debug warning; the other keys keep their stored values |
| stored log switch `"maybe"` | every logged stage raises, and the Log Record panel fails to open | reads off |

The next panel save writes the shown (default) value into the file. The log enable flag is the exception: it is written only when logging is turned on or off.

## 5. Strings

None added or changed. The `.po` file is not touched.

## 6. Test plan

- **Part 1 unit tests (harness).**
  - The pipeline harness stubs `globalVars.appDir` as `ref/nvda/source`, so `_has_symbol_table` sees NVDA's real tables.
  - `languageHandler.normalizeLanguage` is NVDA's own function, loaded from `ref/nvda`.
  - `_symbol_locale` cases: `zh-TW`, `zh_tw`, `zh_CN`, `zh_SG`, bare `zh`, `x-western`, `en_US`, `de_CH`, `None`, each with NVDA interface en and zh_TW.
  - The namer asks the callback once per language per run, and never for `None`.
  - `inject_number_mode` takes names from the voice locale for the number language and for the language in force.
  - The rewritten M4 test (`test_symbol_names_follow_the_number_language_without_its_voice`) simulates the default-voice return and expects zh_TW names.
  - `getVoiceLocaleForLanguage` is checked on the composition fixture; `speech_context` wiring is checked too.
- **Part 1 against NVDA's real `characterProcessing`.** A zh_TW voice locale with NVDA interface en gives `乘以`; a zh_SG voice with interface en gives `times`.
- **Guard tests against `ref/nvda`:**
  - the builtin dictionary path is `os.path.join(globalVars.appDir, "locale", "{locale}", "symbols.dic")`;
  - `normalizeLanguage` exists;
  - `config/__init__.py` validates in `_cacheLeaf` and `get` catches only `KeyError`;
  - NVDA imports `ValidateError` from `configobj.validate`.
- **Part 2:**
  - a validating section stub raises `ValidateError` subclasses, as NVDA does, for each stored key;
  - `load` falls back per key and warns once per key and value;
  - the import fallbacks are covered;
  - `group_size` convert and panel tests are updated (stored 0, 1, 12 read 3);
  - the settings table guard swaps the `stored_min_value` checks for a `reset_out_of_range`-only-on-int check;
  - the log readers (stage, service, panel) read off for an invalid switch.
- **Mutation testing:** mutmut on `_has_symbol_table`, `_symbol_locale`, `_symbol_namer`, `read_stored`, `_get_value`, `PipelineSettingSpec.convert` and `PipelineSettingSpec.confspec`. Use 3 workers and the memory guard. Survivors are recorded in the plan.
- **Full verification (§7).** Baseline 2254 passed, 0 skipped.

## 7. Windows manual items

1. A OneCore `zh-TW` voice for zh, NVDA interface English, number mode: `2×3` says `乘以`, and `3.5` says the zh_TW name for `.`.
2. A zh_CN voice assigned to zh, NVDA in Traditional Chinese: `2×3` says `乘号`.
3. Number language en with no English voice: the names are Chinese (the default voice's locale).
4. Edit `nvda.ini` to set `[WorldVoice] [[pipeline]] group_size = 11`, and in a second run `number_wait_factor = abc`. Restart NVDA:
   - WorldVoice loads;
   - the panel shows 3 (or 10);
   - the debug log has one warning per key;
   - saving the panel fixes the file.
5. Set a log switch to `maybe`: the Log Record panel opens, with that switch unticked.

## 8. Task estimate

7 tasks, so no batches:
1. stored-value fallback;
2. `group_size` range;
3. log readers;
4. voice locale callback;
5. symbol locale;
6. M4 test and the previous spec's notes;
7. mutmut and full verification.
