# Number Unify Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order, in three batches (5/4/4).
> After batch 1 and batch 2 the implementer stops and reports; the orchestrator dispatches a
> Fable 5.1 batch review (user decision P), and Critical/Important findings are fixed by TDD
> before the next batch. After batch 3 the orchestrator dispatches the final Fable 5.1
> whole-branch review (DEVELOPMENT_WORKFLOW.md §3.3). Steps use checkbox (`- [ ]`) syntax.

**Goal:** One definition of "number" across the speech pipeline, number and group modes as one algorithm that names each symbol in the number language, an "off" mode, value-mode thousands-separator removal, a number pause that works across language commands, and the removal of the group wait and "Ignore commas" settings.

**Architecture:** All behaviour lives in `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (stages) and `pipeline/settings.py` (the settings table); panels, the settings ring and the log switches are table- or `STAGES`-driven and follow. Symbol names come from NVDA's `characterProcessing.processSpeechSymbol`, chosen per match by a small locale helper. No engine wrapper, inner driver or runtime change.

**Tech Stack:** Python 3 (NVDA add-on), pytest, Hypothesis, mutmut 3, ruff 0.16.3 via prek, gettext `msgfmt`.

**Spec:** `docs/superpowers/specs/2026-10-22-feat-number-unify-design.md` (commit `c5c9f47`; F1 option D, F2, F3 decided by the user 2026-10-22).

## Global Constraints

- Work only in `/workspace/WorldVoice-feat-number-unify` on `feat/number-unify`. `ref` is a symlink to `/workspace/WorldVoice/ref` (NVDA `7d25bc76e`); never stage it.
- Never modify `addon/synthDrivers/WorldVoice/driver/<Engine>/driver/`, `driver/sonic/` or `languageDetection/script_data.py`. Engine drivers stay independently installable (no driver imports another driver's package). Never add Neural back.
- ruff is pinned `==0.16.3` (`required-version`); prek hooks run on commit. If a hook changes files, restage and recommit; never `--no-verify`.
- git: stage explicit paths only; check `git diff --cached --stat` before each commit; messages `<type>: <summary>` in English with a body that explains why; no `Co-Authored-By`; never `git stash`; never push; do not touch `/workspace/WorldVoice`.
- Delete only your own scratchpad files.
- Tests: `python3 -m pytest -q tests`, single process, with a memory guard that stops pytest below 3 GB MemAvailable. mutmut: at most 3 workers, same guard.
- Every UI string has a `# Translators:` comment directly above it. zh_TW `nvda.po` changes pass `msgfmt --check`. Never commit `.pot` or `.mo`.
- A symbol is SYM: Unicode category P* or S* with a code point in U+0000..U+00FF. A digit is ASCII `0-9`.
- NB is `NumberBreakCommand(settings.scaled_number_wait())`, inserted even at pause 0.
- No `CharacterModeCommand` is ever emitted by the pipeline (F1 option D).
- Number-mode values and display order: `none` ("off", zh_TW 不處理), `value` (default), `number`, `group`. Group size 2..10, default 3; confspec keeps `min=1` so a stored 1 loads and converts to 2.
- `STAGES` order (spec 6.8): `apply_speech_dictionaries`, `number_mode` (thousands, `log_switch=False`), `number_language`, `number_mode`, `chinesespace_wait_factor`, `item_wait_factor`, `punctuation_wait_factor`, `number_wait_factor`, `speech_viewer`.
- Every deviation from this plan is ledgered as `Ruling: <decision> — <why> — <cost if wrong>` in `.superpowers/sdd/2026-10-22-feat-number-unify/progress.md`.
- Verification before every commit and at every batch end (workflow §7): full suite count as stated per task (baseline `2110 passed, 0 skipped`), `prek run --all-files` all Passed (plus `prek run --files <new files>` before committing them), `git diff --check master`, and both protected-path commands print nothing:
  - `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py`
  - `git ls-files addon/synthDrivers/WorldVoice/driver/Neural`

## Review Focus

1. **Bare number languages.** WorldVoice stores number languages as primary subtags (`"zh"`, `"en"`; `voiceCatalog.py:16-19`, `roles.py:8-12`) and NVDA has no `zh` table, so `"zh"` must not give English names to a Chinese voice: with NVDA in zh_TW, `"zh"` → `"乘以"`. Pinned in Task 1 (`test_symbol_locale`, `test_pipeline_names_symbols_with_nvdas_real_lookup`).
2. **Dash locales.** Voice catalogs and browse-mode `lang` attributes may give `"zh-TW"` / `"en-US"`; NVDA only drops a country after `_`, so they must normalise to `zh_TW` names, not English. Pinned in Task 1 (`test_symbol_locale`).
3. **Long symbol-dense numbers** (IP lists, version strings, `"1."*3000+"1"` in number mode): finish quickly and call NVDA's lookup at most once per distinct symbol per text item. Pinned in Task 7 (`test_long_symbol_runs_look_each_symbol_up_once_per_item`).
4. **A symbol without a name next to "remove punctuation".** If a user symbols dictionary gives `.` no name, `"12.5"` in group mode with `.` configured and removal on ~~must still keep its `.` (as on `master`). Pinned in Task 7 (`test_an_unnamed_symbol_between_digits_survives_punctuation_removal`).~~ (Changed by the user, 2026-10-22: a symbol without a name is now its own item between number breaks, and the punctuation stage may pause at it or remove it; the test is `test_an_unnamed_symbol_is_left_to_the_punctuation_stage`.)
5. **A number split across text items** (browse mode splits at formatting: `"12"`, Marker, `",345"`): value mode must leave both items unchanged and keep the command; nothing is joined across items. Pinned in Task 5 (`test_thousands_step_passes_commands_and_split_items`).

## Batches

| Batch | Tasks | Ends with | Expected suite |
| --- | --- | --- | --- |
| 1 | 1–5 | stop, report, Fable 5.1 batch review | 2186 passed, 0 skipped |
| 2 | 6–9 | stop, report, Fable 5.1 batch review | 2245 passed, 0 skipped |
| 3 | 10–13 | report; Fable 5.1 final whole-branch review | 2246 passed, 0 skipped |

Counts for later tasks are computed from the tests each task lists; if the real count differs, record the actual number and the reason as a Ruling.

## File Structure

- `addon/synthDrivers/WorldVoice/pipeline/__init__.py` — regexes, `_symbol_locale`, `_symbol_name`, thousands step, number modes, number pause, `Stage.log_switch`, `STAGES`, `LOG_SWITCHES`.
- `addon/synthDrivers/WorldVoice/pipeline/settings.py` — choices, table entries, `PipelineSettings`, `effective`, `stored_min_value`.
- `addon/synthDrivers/WorldVoice/pipeline/context.py` — drop `speech_symbols`.
- `addon/synthDrivers/WorldVoice/__init__.py` — log confspec from `LOG_SWITCHES`; `speech_context` without `speech_symbols`.
- `addon/globalPlugins/WorldVoice/speechSettingsDialog.py` — log labels and Log Record panel from `LOG_SWITCHES`.
- `addon/locale/zh_TW/LC_MESSAGES/nvda.po`, `readme.md`, `addon/doc/zh_TW/readme.md`.
- Tests: `tests/pipeline_harness.py` (stubs, `symbol_name`, `ORDER`, `LOG_SWITCH_ORDER`), new `tests/test_pipeline_nvda_symbols.py`, and the files listed per task.

## Shared test helpers (defined in Task 1, used later)

- `pipeline_harness.symbol_name(locale: str, symbol: str) -> str`: the stub for `processSpeechSymbol`. Returns the lower-case Unicode name of the symbol with `-` turned into a space, followed by the locale split at `_`, joined by single spaces: `symbol_name("en", ".") == "full stop en"`, `symbol_name("zh_TW", "×") == "multiplication sign zh tw"`. Letters and spaces only, unique per symbol and locale.
- `load_pipeline_module` installs `characterProcessing.processSpeechSymbol = symbol_name` and `speech.getCurrentLanguage = lambda: "en"`.

---

### Task 1: Symbol names from NVDA

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (imports; new helpers after `listable`)
- Modify: `tests/pipeline_harness.py` (`load_pipeline_module` stubs, `symbol_name`)
- Modify: `tests/test_worldvoice_speak.py` (`_load_modules`: stub `characterProcessing`)
- Create: `tests/test_pipeline_nvda_symbols.py`

**Interfaces:**
- Consumes: NVDA `characterProcessing.processSpeechSymbol(locale, symbol)`, `speech.getCurrentLanguage()`.
- Produces: `_symbol_locale(language: str | None) -> str`; `_symbol_name(locale: str, symbol: str) -> str | None` (None = no name); harness `symbol_name`.

- [ ] **Step 1: Write the failing tests** in `tests/test_pipeline_nvda_symbols.py` (fixture `env` = `load_pipeline_module(monkeypatch, punctuation_settings(0))`):
  - `test_symbol_name_is_the_lookups_name`: with the harness stub, `module._symbol_name("en", "×") == "multiplication sign en"`.
  - `test_symbol_name_is_none_without_a_name`, parametrized over a lookup that raises `LookupError`, returns `None`, returns `""`, returns the symbol: `module._symbol_name("en", ".") is None`.
  - `test_symbol_locale`, parametrized `(current, language, expected)`: `("en_GB", None, "en_GB")`, `("zh_TW", "zh-TW", "zh_TW")`, `("zh_TW", "zh", "zh_TW")`, `("zh_TW", "en", "en")`, `("zh_TW", "de_CH", "de_CH")`; monkeypatch `module.speech.getCurrentLanguage` to return `current`.
  - Real NVDA (skip when `REF / "nvda/source/characterProcessing.py"` is missing). Helper `load_nvda_character_processing(monkeypatch)` loads it with `StubModules` stubs for `NVDAState` (`shouldWriteToDisk=lambda: False`, `WritePaths.getSymbolsConfigFile` → a `tmp_path` file), `logHandler.log` (no-op `debug`, `debugWarning`, `error`, `exception`), `globalVars.appDir = REF / "nvda/source"`, `config.conf = {"speech": {"symbolDictionaries": ["cldr"]}}`, `addonHandler.getRunningAddons = lambda: []`, builtins `_` and `pgettext`; then calls `_addSymbolDefinitions()`.
    - `test_nvda_names_symbols_in_the_requested_language`, parametrized: `("en","×","times")`, `("zh_TW","×","乘以")`, `("zh_TW","°","度")`, `("de_CH","×","Mal")`, `("xx","×","times")`, `("en",".","dot")`.
    - `test_every_number_symbol_has_a_name`, parametrized `en`, `zh_TW`: for every Latin-1 P*/S* character `s`, `processSpeechSymbol(locale, s)` is non-empty and `!= s`.
    - `test_pipeline_names_symbols_with_nvdas_real_lookup`: with the real module as `module.characterProcessing` and `getCurrentLanguage` → `"zh_TW"`, `module._symbol_name(module._symbol_locale("zh"), "×") == "乘以"`.
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_pipeline_nvda_symbols.py`. Expected: the 6 real-lookup cases and 2 symbol cases pass (they test NVDA only); the others FAIL with `AttributeError: ... has no attribute '_symbol_name'` / `'_symbol_locale'`, or at harness import of `characterProcessing` (module stub missing).
- [ ] **Step 3: Implement** in `pipeline/__init__.py`: `import characterProcessing` and `import speech` (module-level); `_symbol_locale(language: str | None) -> str` and `_symbol_name(locale: str, symbol: str) -> str | None` per spec 6.4.1 (`None` → `speech.getCurrentLanguage()`; `-` → `_`; a bare language equal to the current locale's base → the current locale; catch only `LookupError`; `None`, `""` or the symbol itself → `None`). Add the stubs to `pipeline_harness.load_pipeline_module` and `test_worldvoice_speak._load_modules` (`characterProcessing.processSpeechSymbol = symbol_name`; `speech.getCurrentLanguage = lambda: "en"`).
- [ ] **Step 4: Run** the file again. Expected: `19 passed`. Then the full suite. Expected: `2129 passed, 0 skipped`.
- [ ] **Step 5: Commit** `tests/test_pipeline_nvda_symbols.py tests/pipeline_harness.py tests/test_worldvoice_speak.py addon/synthDrivers/WorldVoice/pipeline/__init__.py` as `feat: look up NVDA's name for a symbol in the number's language`.

### Task 2: One number definition

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py:31-36` (regexes), `:157-163` (`_both_numbers` docstring/comment), `:210-242` (`_split_spaced_numbers`)
- Test: `tests/test_pipeline_filters.py`, `tests/test_pipeline_pause_properties.py`

**Interfaces:**
- Produces: `_SYMBOLS: str` (the 55 Latin-1 P*/S* characters, in code-point order) and `_NUMBER_RE = re.compile(rf"(?:(?<![0-9])[+-])?[0-9]+(?:[{re.escape(_SYMBOLS)}]+[0-9]+)*")`. `_PURE_NUMBER_RE` is gone. All users of `_NUMBER_RE` keep their signatures.

- [ ] **Step 1: Write the failing tests** in `tests/test_pipeline_filters.py`:
  - `test_number_re_finds_whole_numbers`, parametrized `(text, matches)` (`[m.group() for m in module._NUMBER_RE.finditer(text)]`): `"12,345,678"`→`["12,345,678"]`; `"1,234.56"`→`["1,234.56"]`; `"-1234"`→`["-1234"]`; `"5-3"`→`["5-3"]`; `"5 -3"`→`["5","-3"]`; `"2026-10-22 12:30"`→`["2026-10-22","12:30"]`; `"192.168.0.1"`→`["192.168.0.1"]`; `"12，34"`→`["12","34"]`; `"abc1 2def"`→`["1","2"]`; `"a-3"`→`["-3"]`; `"--3"`→`["-3"]`; `"3.+4"`→`["3.+4"]`; `"1 2"`→`["1","2"]`; `"1­2"`→`["1","2"]`; `"1'000"`→`["1'000"]`; `"1_000"`→`["1_000"]`; `"1×2"`→`["1×2"]`; `"１２"`→`[]`; `"12."`→`["12"]`; `"+3 a+4"`→`["+3","+4"]`.
  - `test_number_re_fullmatch_fails_fast`, parametrized `"1"*5000+"a"`, `"1."*3000+"a"`: `fullmatch` is `None` and takes under 50 ms (`time.perf_counter`).
  - `SPLITS` edits: `("1.2.3 4", ["1.2.3", B40, "4"])`; the four "F1 option B" rows become `("02 2345-6789", ["02", B40, "2345-6789"])`, `("3-1 2", ["3-1", B40, "2"])`, `("1 2 3-4", ["1", B40, "2", B40, "3-4"])`, `("1-2 3 4", ["1-2", B40, "3", B40, "4"])` with the comment "One number definition: a match never touches another, so every whitespace gap splits"; add `("2026-10-22 12:30", ["2026-10-22", B40, "12:30"])` and `("12,345 6", ["12,345", B40, "6"])`.
  - `test_number_wait_breaks_only_between_whole_numbers`: add `(["5-3", "4"], ["5-3", B40, "4"])` and `(["12:30", "1"], ["12:30", B40, "1"])`.
  - `TEXTS`/`SHARED` of `test_number_mode`: `"1.2.3"` now gives `["1.2.3"]` in every mode (one match; interim until Task 7 for number/group).
  - In `tests/test_pipeline_pause_properties.py`: `NUMBER_TEXT` alphabet becomes `"0123456789+-.,:/×°aZ共，．" + " \t\n\r　" + NO_BREAK_SPACES`; P1 `test_property_number_re_equals_the_scanner` (a hand-written scanner implementing spec Q1–Q3 directly: at each position, an optional `+`/`-` that is followed by a digit and not preceded by a digit, then digits, then repeated "one or more SYM followed by at least one digit"; spans equal `[m.span() for m in _NUMBER_RE.finditer(text)]`); P2 `test_property_matches_are_never_glued` (every gap between consecutive matches is non-empty); `test_property_no_text_item_keeps_two_numbers_apart_by_whitespace` drops the glued branch and asserts no whitespace-only gap ~~without a no-break space~~ remains inside any text item (Changed by the user, 2026-10-22: a no-break space is ordinary whitespace for the split, so the exception is gone; see the spec's NB rule in section 2.).
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_pipeline_filters.py tests/test_pipeline_pause_properties.py`. Expected: FAIL on most new `_NUMBER_RE` cases (e.g. `"12,345,678"` gives `["12", "345", "678"]`), the edited `SPLITS` rows, the `1.2.3` rows, and P1.
- [ ] **Step 3: Implement** the regex constants (`import unicodedata`), remove `_PURE_NUMBER_RE`, remove `glued` from `_split_spaced_numbers` (joined[i] is just `_is_splittable_gap(gap)`, ~~keeping the no-break-space exception~~ (Changed by the user, 2026-10-22: a no-break space is ordinary whitespace for the split, so the exception is gone; see the spec's NB rule in section 2.); update the docstring: matches never touch, so only a no-break space keeps two numbers together), and update the `_both_numbers` comment to the new examples (`"5-3"`, `"12:30"` are numbers).
- [ ] **Step 4: Run** the two files. Expected: PASS. Full suite: `2157 passed, 0 skipped`.
- [ ] **Step 5: Commit** the module and both test files as `feat: share one number definition across the speech pipeline`.

### Task 3: Number pause across language commands

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (`number_wait_factor`, new `_insert_number_breaks`)
- Test: `tests/test_pipeline_filters.py`, `tests/test_pipeline_stages.py`

**Interfaces:**
- Produces: `_insert_number_breaks(speechSequence: Iterable[SpeechCmd], break_cmd: SpeechCmd) -> Iterator[SpeechCmd]` (spec 6.5); `number_wait_factor` signature unchanged.

- [ ] **Step 1: Write the failing tests** in `tests/test_pipeline_filters.py` (wait 40, `GENERIC_CONTEXT`; `WV = module.WVLangChangeCommand`, `LC = sys.modules["speech.commands"].LangChangeCommand`):
  - `test_number_wait_breaks_between_numbers_across_language_commands`, parametrized over `WV` and `LC`: `[C("en"), "1", C("zh"), " ", C("en"), "2", C("zh")]` → `[("lang","en"), "1", ("lang","zh"), B40, ("lang","en"), "2", ("lang","zh")]`.
  - `test_number_wait_breaks_after_a_single_language_command`, parametrized `WV("zh")`, `LC(None)`: `["1", cmd, "2"]` → `["1", ("lang", cmd.lang), B40, "2"]`.
  - `test_number_wait_does_not_break_across_other_commands`, parametrized a marker command and `BreakCommand(5)`: `["1", WV("zh"), other, WV("en"), "2"]` has no `NumberBreakCommand`.
  - `test_number_wait_keeps_held_language_commands_at_the_end`: `["1", WV("zh")]` → `["1", ("lang","zh")]`.
  - `test_number_wait_does_not_break_between_a_number_and_text_across_language_commands`: `["1", WV("zh"), "abc"]` → unchanged shape.
  - In `tests/test_pipeline_stages.py`, `test_number_language_and_number_wait_pause_between_numbers`: settings with `scaled_number_wait = lambda: 10`, `ctx = SpeechContext(supports_roles=True, language="zh", number_language="en", default_voice=..., voice_name_for_language={"zh": "Z", "en": "E"}.get)`, run every `STAGES` handler on `["1 2"]` → `[("lang","en"), "1", ("lang","zh"), ("NumberBreakCommand",10), ("lang","en"), "2", ("lang","zh")]`.
- [ ] **Step 2: Run** both files. Expected: the new tests FAIL (no `NumberBreakCommand` between the language commands).
- [ ] **Step 3: Implement** `_insert_number_breaks` (hold language commands after the last non-language item; when `_both_numbers(previous, item)`, yield the first held command, the break, the rest, then the item; otherwise the held commands then the item; flush held commands at the end) and use it in `number_wait_factor` instead of `_insert_between(..., _both_numbers, ...)`.
- [ ] **Step 4: Run** both files: PASS. Full suite: `2166 passed, 0 skipped`.
- [ ] **Step 5: Commit** as `fix: pause between numbers that a number language wraps`.

### Task 4: Remove "Ignore commas between numbers"

**Files:**
- Modify: `pipeline/__init__.py` (`_COMMA_NUMBER_RE`, `ignore_comma_between_number`, its `Stage`), `pipeline/settings.py` (entry `:132-141`, field `:283`, `effective` `:336`, `:346-349`), `addon/globalPlugins/WorldVoice/speechSettingsDialog.py:43-44`, `addon/locale/zh_TW/LC_MESSAGES/nvda.po` (delete the entry)
- Test: `tests/pipeline_harness.py` (`punctuation_settings`, `ORDER`), `tests/test_pipeline_settings_service.py`, `tests/test_pipeline_passthrough.py`, `tests/test_panel_layout.py`, `tests/test_pipeline_controls.py`, `tests/test_pipeline_panels.py`, `tests/test_settings_order.py`, `tests/test_settings_panels.py`, `tests/test_settings_table_guard.py`, `tests/test_translator_comments.py`, `tests/test_worldvoice_pipeline_settings.py`, `tests/test_voice_settings_panel.py`

**Interfaces:**
- Produces: `PipelineSettings` without `ignore_comma_between_number`; `effective(False)` for scope "all" returns `self` (V6).

- [ ] **Step 1: Write the failing tests:**
  - `tests/test_pipeline_settings_service.py::test_ignore_comma_option_is_gone`: `"ignore_comma_between_number"` is not in `PIPELINE_CONFIG_KEYS`, not a `PipelineSettings` field, and no spec has `driver_id == "cni"`.
  - `test_effective_matches_the_old_synth_scoping`: drop the ignore-comma fields; for scope "all" with `global_wait_factor=0`, `settings.effective(False) is settings` (V6: no global-wait coupling).
  - `tests/test_translator_comments.py`: move `"Ignore commas between numbers"` from `CHANGED_LABEL_MSGIDS` to `DEAD_MSGIDS`.
  - `tests/pipeline_harness.py`: `ORDER` without `"ignore_comma_between_number"`; `punctuation_settings` without the field.
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_pipeline_settings_service.py tests/test_translator_comments.py tests/test_pipeline_stages.py`. Expected: FAIL (field still present, `effective` couples to the global wait, the dead msgid is still called, `STAGES` still has the stage).
- [ ] **Step 3: Implement** the removals listed under Files; delete the zh_TW entry `msgid "Ignore commas between numbers"`. Update the remaining tests that used ignore-comma as a sample: switch the sample checkbox to `punctuation_pause_enabled` (`test_pipeline_controls.py`, `test_settings_table_guard.py` "bool slider", "controller depends", "scaled checkbox", `test_panel_layout.py` `test_label_text` and `test_attribute_names` rows) and to `BooleanDriverSetting("punctuationpauseenabled")` in the three `test_voice_settings_panel.py` row tests; drop `cni`/the key from `test_settings_order.py` (`TABLE_DRIVER_IDS`, ring filter, panel order), `test_worldvoice_pipeline_settings.py` (`EXPECTED_IDS`, the `cni` ring assertion), `test_pipeline_panels.py`, `test_settings_panels.py`, `test_panel_layout.py` `Q1` list; delete `test_comma_between_digits_is_dropped_only_when_enabled`.
- [ ] **Step 4: Run** the full suite: `2165 passed, 0 skipped`. `msgfmt --check -o /dev/null addon/locale/zh_TW/LC_MESSAGES/nvda.po` prints nothing.
- [ ] **Step 5: Commit** as `refactor: remove the "Ignore commas between numbers" option`.

### Task 5: Value-mode thousands separators and log switches

**Files:**
- Modify: `pipeline/__init__.py` (`_THOUSANDS_RE`, `remove_thousands_separators`, `Stage.log_switch`, `STAGES`, `LOG_SWITCHES`), `addon/synthDrivers/WorldVoice/__init__.py:74-77` (log confspec), `addon/globalPlugins/WorldVoice/speechSettingsDialog.py:17`, `:669-671`
- Test: `tests/pipeline_harness.py` (`ORDER`, new `LOG_SWITCH_ORDER`), `tests/nvda_stubs.py:103-110`, `tests/ui_harness.py:778-780`, `tests/test_runtime_composition.py:599-601`, `tests/test_pipeline_panels.py`, `tests/test_pipeline_passthrough.py`, `tests/test_pipeline_stages.py`, `tests/test_pipeline_pause_properties.py`

**Interfaces:**
- Produces: `_THOUSANDS_RE = re.compile(r"(?<![0-9,])[0-9]{1,3}(?:,[0-9]{3})+(?!,*[0-9])")`; `remove_thousands_separators(speechSequence, settings, ctx) -> Iterator[SpeechCmd]` (value mode only); `Stage(log_key, fn, log_switch: bool = True)`; `LOG_SWITCHES: tuple[str, ...] = tuple(stage.log_key for stage in STAGES if stage.log_switch)`.

- [ ] **Step 1: Write the failing tests:**
  - `tests/test_pipeline_passthrough.py::test_value_mode_removes_only_valid_thousands_separators`, parametrized `(text, expected)`: `12,345,678`→`12345678`; `1,234.56`→`1234.56`; `-1,234`→`-1234`; `1,234,`→`1234,`; `1.234,567`→`1.234567`; `1,000,000,000`→`1000000000`; `12,345 and 3,4`→`12345 and 3,4`; unchanged: `1,2`, `1234,567`, `1,234,56`, `1, 234`, `3,14`, `a,1,234`, `1,234,,5`.
  - `test_thousands_step_passes_through_other_modes`, parametrized `number`, `group`: `["12,345"]` unchanged.
  - `test_thousands_step_passes_commands_and_split_items` (Review Focus 5): value mode, `["12", marker, ",345"]` → the same three objects.
  - `tests/test_pipeline_stages.py`: `test_stages_order_and_log_keys` expects the new `ORDER` (spec 6.8); `test_log_switches_list_each_label_once_in_stage_order`: `module.LOG_SWITCHES == tuple(LOG_SWITCH_ORDER)` with `LOG_SWITCH_ORDER = ["apply_speech_dictionaries", "number_language", "number_mode", "chinesespace_wait_factor", "item_wait_factor", "punctuation_wait_factor", "number_wait_factor", "speech_viewer"]`; `test_thousands_removal_runs_before_number_language`: value mode, ctx with number language en (as in Task 3), all `STAGES` on `["12,345,678"]` → `[("lang","en"), "12345678", ("lang","zh")]`; `test_number_mode_switch_logs_both_number_mode_stages`: with log enable and only `number_mode` on, the recorded labels are `["number_mode"]*4` for one utterance.
  - `tests/test_pipeline_panels.py::test_log_labels_match_stages_and_confspec`: `list(_LOG_LABELS) == LOG_SWITCH_ORDER`; the synth source holds `key: 'boolean(default=false)' for key in LOG_SWITCHES`.
  - P3 in `tests/test_pipeline_pause_properties.py::test_property_thousands_removal_equals_the_whole_run_oracle`: text over `"0123456789,.a -"` (max 20); oracle per spec 6.3 (each maximal `[0-9,]+` run, trailing commas dropped, commas removed only when the rest fullmatches `[0-9]{1,3}(?:,[0-9]{3})+`) equals the stage's output in value mode.
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_pipeline_passthrough.py tests/test_pipeline_stages.py tests/test_pipeline_panels.py tests/test_pipeline_pause_properties.py`. Expected: FAIL (`remove_thousands_separators`, `LOG_SWITCHES` undefined; order mismatch).
- [ ] **Step 3: Implement** the step and `Stage.log_switch`; register `Stage("number_mode", remove_thousands_separators, log_switch=False)` in the freed slot; define `LOG_SWITCHES` after `STAGES`; the synth log confspec becomes `**{key: "boolean(default=false)" for key in LOG_SWITCHES}`; the Log Record panel iterates `LOG_SWITCHES`; `_LOG_LABELS` keeps its order (already `LOG_SWITCH_ORDER`). Update the stubs: `nvda_stubs` parses the `LOG_SWITCHES` comprehension (keys of `Stage(...)` calls in `STAGES` without `log_switch=False`), `ui_harness` stubs `LOG_SWITCHES = tuple(LOG_SWITCH_ORDER)`, `test_runtime_composition` stubs `LOG_SWITCHES=()`.
- [ ] **Step 4: Run** the four files: PASS. Full suite: `2186 passed, 0 skipped`.
- [ ] **Step 5: Commit** as `feat: drop thousands separators in value mode`.
- [ ] **Step 6: Batch 1 end.** Full §7 verification, then STOP and report: commits (sha, subject), the batch range `<plan commit>..HEAD`, counts, and every Ruling. Do not start Task 6 until the orchestrator says so.

### Task 6: The "off" number mode

**Files:**
- Modify: `pipeline/settings.py:45-53` (`NUMBER_MODE_CHOICES`), `pipeline/__init__.py` (`inject_number_mode`), `nvda.po` (new entry)
- Test: `tests/test_pipeline_settings_service.py`, `tests/test_pipeline_filters.py`, `tests/test_pipeline_passthrough.py`, `tests/test_pipeline_pause_properties.py`, `tests/test_settings_panels.py`, `tests/test_voice_settings_panel.py`, `tests/test_panel_layout.py`, `tests/test_settings_order.py`, `tests/test_translator_comments.py`

**Interfaces:**
- Produces: `NUMBER_MODE_CHOICES[0] == ("none", _("off"))` with `# Translators: A number mode: numbers are left as they are.`; `"none"` in `NUMBER_MODES`.

- [ ] **Step 1: Write the failing tests:** `test_number_mode_choices_put_off_first` (values `["none","value","number","group"]`, labels `["off","value","number","group"]`); `test_number_mode_reads_and_writes_only_known_modes` gains `("none","none")`; `test_off_mode_leaves_the_sequence_unchanged` (`inject_number_mode` on `["12.5 a", marker, "3."]` returns the same objects, no dot-rule space); `test_thousands_step_passes_through_other_modes` gains `none`; P4 `test_property_off_mode_is_the_identity_for_both_number_stages`; `test_settings_panels.py` stored-mode parametrization gains `"none"` and the unknown-stored test expects index 1; `test_voice_settings_panel.py` `(mode, enabled)` gains `("none", False)`; `test_panel_layout.py` mode list gains `"none"` and `("group", 3)` replaces `("group", 2)`; ring cycle order in `test_settings_order.py`; `"off"` joins a translator-comment list in `test_translator_comments.py` and must have a zh_TW translation.
- [ ] **Step 2: Run** those files. Expected: FAIL ("none" unknown, normalises to "value").
- [ ] **Step 3: Implement** the choice, the early pass-through in `inject_number_mode` for `"none"`, and the zh_TW entry `msgid "off"` / `msgstr "不處理"` (with the translator comment and source reference).
- [ ] **Step 4: Run:** PASS. Full suite: `2194 passed, 0 skipped`. `msgfmt --check` clean.
- [ ] **Step 5: Commit** as `feat: add an "off" number mode that leaves numbers alone`.

### Task 7: Number and group modes name each symbol

**Files:**
- Modify: `pipeline/__init__.py` (`_translate_number`, `iter_number_speech_segments_mode`, `inject_number_mode`; remove `GroupNumberBreakCommand`, `get_translate_table`), `pipeline/context.py:15` (drop `speech_symbols`), `WorldVoice/__init__.py:365`
- Test: `tests/test_pipeline_filters.py`, `tests/test_pipeline_stages.py`, `tests/test_pipeline_passthrough.py`, `tests/test_pipeline_pause_properties.py`

**Interfaces:**
- Consumes: `_NUMBER_RE`, `_SYMBOLS` (Task 2); `_symbol_locale`, `_symbol_name` (Task 1); harness `symbol_name`.
- Produces: `_translate_number(raw: str, mode: str, group_size: int, number_pause: int, name_of: Callable[[str], str | None]) -> Iterator[SpeechCmd]`; `iter_number_speech_segments_mode(item: str, mode: str, group_size: int, number_pause: int, name_of: Callable[[str], str | None], number_re: re.Pattern = _NUMBER_RE) -> Iterator[SpeechCmd]`.

- [ ] **Step 1: Write the failing tests** (`N = lambda s, loc="en": symbol_name(loc, s)`; GENERIC_CONTEXT with `getCurrentLanguage` → `"en"` unless stated):
  - `test_number_and_group_modes_name_each_symbol`, parametrized over 12 inputs × `(number,1)`, `(group,3)`, `(group,2)`, expectations from spec 7.1 with `⟨x⟩ = N(x)`: `12,345,678`, `1,234.56`, `123.456`, `12.5`, `-1234`, `5-3`, `2026-10-22`, `192.168.0.1`, `3,14`, `2×3`, `6÷2`, `45°30`.
  - `test_number_breaks_use_the_number_pause`, parametrized 0, 25: every break is a `NumberBreakCommand` with `time == pause`; no `GroupNumberBreakCommand` attribute on the module.
  - `test_adjacent_symbols_get_a_name_each`: number mode `"1--2"` → `["1", NB, N("-"), NB, N("-"), NB, "2"]`.
  - `test_symbol_names_follow_the_number_language`: roles ctx, number language `en`, language `zh_TW`, input `[WV("en"), "2×3", WV("zh_TW")]` → name `N("×","en")`.
  - `test_symbol_names_follow_language_commands_with_default_number_language`: roles ctx, number language `default`, language `zh_TW`: `["2×3", WV("de"), "2×3", LC(None), "2×3"]` names `zh tw`, `de`, `zh tw`.
  - `test_symbol_names_without_roles_ignore_the_number_language`: `SpeechContext(supports_roles=False, language="fr", number_language="en")` → `N("×","fr")`.
  - `test_symbol_names_without_a_language_use_nvdas_current_language`: GENERIC_CONTEXT, `getCurrentLanguage` → `"de"` → `N("×","de")`.
  - `test_value_and_off_leave_symbols_alone`, parametrized `value`, `none`: `"2×3"` → `["2×3"]`, the lookup is never called.
  - `test_a_symbol_without_a_name_stays_attached_to_its_digits`: lookup returns the symbol for `.`; group 3 `"123.456"` → `["123.456"]`; number `"12.5"` → `["1", NB, "2.5"]`.
  - `test_an_unnamed_symbol_between_digits_survives_punctuation_removal` (Review Focus 4): unnamed `.`, group 3, punctuation pause on with `.` configured and removal on, ~~all `STAGES` on `["12.5"]`: the joined text still contains `"12.5"`.~~ (Changed by the user, 2026-10-22: a symbol without a name is now its own item between number breaks, and the punctuation stage may pause at it or remove it; the test is `test_an_unnamed_symbol_is_left_to_the_punctuation_stage`.)
  - `test_long_symbol_runs_look_each_symbol_up_once_per_item` (Review Focus 3): number mode on `"1."*3000 + "1"` with a counting lookup: one call for `.`, and the stage finishes in under 2 s.
  - Properties P5 (text survives, names mapped back via the harness name table), P6 (no `[0-9]+` run longer than the size in any item), P7 (every NB and name item lies inside one input match; each name has NB on both sides).
  - Update `TEXTS`/`SHARED`/`test_number_mode`, `test_group_mode_keeps_leading_zeros_and_every_digit`, `test_group_separator_is_one_instance_per_number`, `test_group_mode_then_number_wait_breaks_between_numbers_only`, `test_digit_mode_breaks_only_between_adjacent_digits`, `test_property_digit_mode_separates_every_digit`, `test_property_groups_are_separate_items_of_the_chosen_size` (`NumberBreakCommand`, no table); delete `test_number_mode_reads_symbols_from_context`, `test_digit_symbols_translate_only_in_the_number_language_or_windows`, `test_translated_digits_are_split_by_the_number_wait`, `test_group_mode_does_not_translate_digits`, `test_digit_words_are_kept_verbatim_one_per_item`, `test_property_decimals_are_unchanged_in_group_mode`.
- [ ] **Step 2: Run** the four files. Expected: FAIL (symbols are not named; group mode returns decimals whole; `GroupNumberBreakCommand` still used).
- [ ] **Step 3: Implement** spec 6.4 and 6.4.1: tokens `^[+-]?[0-9]+|[0-9]+|SYM`; digit runs cut from the left by size (1 for number, `settings.group_size` for group), the sign joins the first piece; a named symbol is one item; NB between consecutive pieces and names; an unnamed symbol has no NB on either side. `inject_number_mode` tracks the language (`ctx.language`, updated by `LangChangeCommand`/`WVLangChangeCommand` with `cmd.lang or ctx.language`), uses `ctx.number_language` when roles are supported and it is not `"default"`, and builds `name_of` with a per-item cache that calls `_symbol_locale` at most once per item and `_symbol_name` once per distinct symbol. Remove `GroupNumberBreakCommand`, `get_translate_table`, `speech_symbols` (context and synth).
- [ ] **Step 4: Run:** PASS. Full suite: `2239 passed, 0 skipped`.
- [ ] **Step 5: Commit** as `feat: read number and group modes with NVDA's symbol names`.

### Task 8: Remove the group wait setting

**Files:**
- Modify: `pipeline/settings.py` (`GROUP_WAIT_UNIT_MS` `:23-26`, entry `:181-190`, field `:294`, `scaled_group_wait` `:319-323`, `effective` `:344`), `nvda.po` (delete `Group wait factor`)
- Test: `tests/pipeline_harness.py`, `tests/test_pipeline_settings_service.py`, `tests/test_settings_order.py`, `tests/test_settings_panels.py`, `tests/test_voice_settings_panel.py`, `tests/test_panel_layout.py`, `tests/test_worldvoice_pipeline_settings.py`, `tests/test_translator_comments.py`, `tests/test_pipeline_stages.py`, `tests/test_pipeline_nvda_ssml.py`

**Interfaces:**
- Produces: `PipelineSettings` without `group_wait_factor`/`scaled_group_wait`; no driver id `groupwaitfactor`.

- [ ] **Step 1: Write the failing tests:** `test_group_wait_setting_is_gone` (key, field, method, driver id, `GROUP_WAIT_UNIT_MS` absent); `test_group_settings_replace_the_pair_wait_and_add_the_size` without the wait; `GROUP_MODE_MSGIDS` loses `"Group wait factor"`, which joins `DEAD_MSGIDS`; `group_controls_enabled` helpers return the spin state only.
- [ ] **Step 2: Run** those files. Expected: FAIL (setting present).
- [ ] **Step 3: Implement** the removals and delete the zh_TW entry; update the id/key lists in the other test files (`groupwaitfactor`, `group_wait_factor`), `punctuation_settings` (no `scaled_group_wait`), and the stage tests' expected break sets (group mode now only `NumberBreakCommand`).
- [ ] **Step 4: Run:** full suite `2240 passed, 0 skipped`; `msgfmt --check` clean.
- [ ] **Step 5: Commit** as `refactor: separate digit groups with the number wait`.

### Task 9: Group size 2..10 with a stored minimum

**Files:**
- Modify: `pipeline/settings.py` (`PipelineSettingSpec.stored_min_value`, `confspec`, `group_size` entry)
- Test: `tests/test_pipeline_settings_service.py`, `tests/test_settings_table_guard.py`, `tests/test_settings_panels.py`, `tests/test_pipeline_controls.py`

**Interfaces:**
- Produces: `PipelineSettingSpec.stored_min_value: int | None = None` ("the confspec's lower bound when an older range stored smaller values; convert raises them"); `group_size`: `min_value=2`, `max_value=10`, `stored_min_value=1`.

- [ ] **Step 1: Write the failing tests:** `test_convert_clamps_ints_to_their_bounds` group rows become `(0, 2)`, `(-5, 2)`, add `(1, 2)`; `test_group_size_confspec_keeps_the_stored_minimum` (`PIPELINE_CONFSPEC["group_size"] == "integer(default=3,min=1,max=10)"`); guard `check_bounds` rejects `stored_min_value >= min_value` (BROKEN case "stored minimum not below the minimum") and a `stored_min_value` on a non-int spec (BROKEN case "stored minimum on a non-int"); `test_stored_group_size_one_shows_two` (Speech Pipeline panel spin shows 2); the spin range is 2..10.
- [ ] **Step 2: Run:** FAIL (min is 1; field unknown).
- [ ] **Step 3: Implement** the field, `confspec` using `stored_min_value` when set, the entry values, and the guard rule in `check_bounds`.
- [ ] **Step 4: Run:** full suite `2245 passed, 0 skipped`.
- [ ] **Step 5: Commit** as `feat: offer group sizes 2 to 10 and read a stored 1 as 2`.
- [ ] **Step 6: Batch 2 end.** Full §7 verification, then STOP and report (range `<last batch-1 or fix commit>..HEAD`).

### Task 10: Pipeline-wide properties

**Files:** Test: `tests/test_pipeline_pause_properties.py`

**Interfaces:** Consumes the stages as changed by Tasks 2–9.

- [ ] **Step 1: Write the tests:** P8 `test_property_the_number_language_changes_no_words_or_breaks` (all `STAGES` handlers with number language en vs default, same mode and waits, alphabet of spec 11.2: text items equal when compared without whitespace and language commands; NB positions equal relative to the numbers); P10 replaces `test_property_number_and_group_breaks_never_touch_another_break` (modes none/value/number/group, sizes 2..10, alphabet `"0123456789 a.,-:+×，"`; only `NumberBreakCommand` is checked); P9 `test_property_punctuation_never_touches_a_name` (marks `.,:-` configured, removal on: every name item from `inject_number_mode` leaves `inject_punctuation_pause` unchanged).
- [ ] **Step 2: Run** the file. Expected: PASS once written against Tasks 2–9; if a property fails, the failure is a finding in the stage it names — debug it (systematic-debugging), fix by TDD in that stage, and ledger it.
- [ ] **Step 3:** (no production code unless Step 2 found a defect).
- [ ] **Step 4: Run:** full suite `2246 passed, 0 skipped`.
- [ ] **Step 5: Commit** as `test: pin the number pipeline's properties across modes and languages`.

### Task 11: Scope "all" with other synthesizers

**Files:** Test: `tests/test_pipeline_stages.py`, `tests/test_pipeline_nvda_ssml.py`

- [ ] **Step 1: Update the tests:** `test_other_synths_get_only_plain_breaks_from_the_stages` and `test_worldvoice_keeps_the_break_subclasses_from_the_stages` without the 30 ms group pause; `test_nvda_ssml_keeps_every_word_and_pause_of_the_scope_all_output` with `pause_settings` lacking `scaled_group_wait`: the SSML contains every word of `TEXT` and, in number and group modes, no `say-as`, and every pause; add a case with `"12.5"` in group mode whose SSML holds the harness name of `.` as text between two breaks.
- [ ] **Step 2: Run:** expected PASS against Task 7–8 code (red happened in Tasks 7–8; if anything fails, debug and ledger).
- [ ] **Step 3: Run:** full suite `2246 passed, 0 skipped` (the new SSML case replaces nothing; if it is a new parametrization, `2247` — record the actual).
- [ ] **Step 4: Commit** as `test: keep scope "all" speaking the symbol names as plain words`.

### Task 12: Readmes and the catalog

**Files:** `readme.md:39`, `:44-49`; `addon/doc/zh_TW/readme.md` (same lines); `addon/locale/zh_TW/LC_MESSAGES/nvda.po` (final check only)

- [ ] **Step 1:** Apply spec section 10 "Readmes": drop "ignore commas between numbers" from the global list and its bullet; add "Off: numbers are left as they are."; describe thousands removal in numeric mode, symbols named separately in digit and group modes in the number language, and group size 2–10 with the pause set by the number wait; the zh_TW readme gets the spec's zh_TW wording.
- [ ] **Step 2:** `msgfmt --check -o /dev/null addon/locale/zh_TW/LC_MESSAGES/nvda.po` prints nothing; `python3 -m pytest -q tests/test_translator_comments.py` passes; `git grep -n "Ignore commas\|Group wait factor\|groupwaitfactor\|cni\b" -- addon readme.md` finds nothing outside `DEAD_MSGIDS`.
- [ ] **Step 3: Run:** full suite unchanged from Task 11.
- [ ] **Step 4: Commit** as `docs: describe the off mode, named symbols and thousands separators`.

### Task 13: Full verification and mutation testing

**Files:** none committed except the ledger notes in the report.

- [ ] **Step 1:** Full §7 verification; record counts.
- [ ] **Step 2:** mutmut 3 (≤3 workers, memory guard, scratch copy) on `remove_thousands_separators`, `_translate_number`, `iter_number_speech_segments_mode`, `inject_number_mode`, `_symbol_locale`, `_symbol_name`, `_split_spaced_numbers`, `_insert_number_breaks`, `number_wait_factor`, `_both_numbers`, `PipelineSettingSpec.confspec`, `PipelineSettingSpec.convert`, `_number_mode`, `PipelineSettings.effective`. Kill reasonable survivors with tests (commit `test: kill surviving mutants in the number pipeline`); list every remaining survivor with its reason in the report.
- [ ] **Step 3:** Report to the orchestrator: commits, `BASE..HEAD`, counts, survivors, all Rulings. The orchestrator dispatches the final Fable 5.1 review.
