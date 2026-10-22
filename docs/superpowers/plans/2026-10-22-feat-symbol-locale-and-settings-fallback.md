# Symbol Locale and Settings Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** Name symbols inside numbers in the full locale of the WorldVoice voice that speaks them. Make every invalid stored pipeline value (and log switch) read as its default instead of stopping WorldVoice.

**Architecture:** A new `SpeechContext.voice_locale_for_language` callback, fed by `VoiceManager.getVoiceLocaleForLanguage`, gives `_symbol_namer` the voice locale. `_symbol_locale` uses it when NVDA has a `symbols.dic` for it, and otherwise keeps the current rule. In `pipeline/settings.py`, a `read_stored` helper catches configobj's `ValidateError`, logs once per key and value, and returns the default. The repository, the log stage, the log service and the panels' checkbox read all use it. `group_size` drops `stored_min_value` and resets out-of-range values to 3.

**Tech Stack:** Python 3 (NVDA add-on), pytest + Hypothesis, mutmut 3.8.0, ruff 0.16.3 via prek.

**Spec:** `docs/superpowers/specs/2026-10-22-feat-symbol-locale-and-settings-fallback-design.md`

## Global Constraints

- Never modify `addon/synthDrivers/WorldVoice/driver/<Engine>/driver/`, `driver/sonic/` or `languageDetection/script_data.py`. Both protected-path commands of DEVELOPMENT_WORKFLOW.md §7 print nothing.
- Engine drivers stay independently installable. Never add `driver/Neural` back.
- ruff is pinned `==0.16.3`, and prek hooks run on commit. Never use `--no-verify`.
- Commits:
  - English `<type>: <summary>` with a body that explains why;
  - no `Co-Authored-By`;
  - explicit paths only, checking `git diff --cached --stat` first;
  - never `git stash`, never push, never stage `ref`.
- Tests run single-process under the memory guard (stop below 3 GB MemAvailable). mutmut runs with at most 3 workers under the same guard.
- Fixed values:
  - `group_size` confspec is `integer(default=3,min=2,max=10)`, and outside 2..10 reads as 3;
  - the log switch default is `False`;
  - symbol tables live at `os.path.join(globalVars.appDir, "locale", <loc>, "symbols.dic")`;
  - the normaliser is `languageHandler.normalizeLanguage`.
- Nothing is written back on read (Q3). One `log.debugWarning` per invalid key and stored value (D3). No UI prompt, and no new strings.
- Baseline: 2254 passed, 0 skipped.

## Review Focus

1. **Voice locales that are not plain locale names:** `""`, `x-western`, `zh-Hant-TW`, a path such as `../en`. These must never select a table and must fall back to the current rule. Task 5 (`test_has_symbol_table_matches_nvdas_locale_dir`, `test_symbol_locale_prefers_the_voice_locale_with_a_table`).
2. **A role or default voice changed between utterances.** The cache must hold for one stage run only, so the next utterance asks again. Task 5 (`test_namer_asks_each_language_once_per_run`).
3. **One bad key among good ones.** Only that key falls back; the warning is not repeated per utterance, but a different bad value warns again. Task 1 (`test_load_reads_the_default_for_each_invalid_key`, `test_a_new_invalid_value_warns_again`).
4. **A voice name with no catalog entry**, for example a role naming a voice whose engine is now disabled. The locale is `None`, so the current rule applies. Task 4 (`test_voice_locale_is_none_for_a_voice_without_a_spec`).
5. **An invalid log switch inside a speech filter.** The stage must still run (unlogged), not raise into NVDA's filter. Task 3 (`test_an_invalid_log_switch_reads_off`).

---

### Task 1: Stored values fall back to their default

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/settings.py` (imports, `_get_value` at `:322-333`)
- Modify: `tests/pipeline_harness.py` (`load_settings_module`: logHandler stub gains `debugWarning`, configobj stub)
- Modify: `tests/nvda_stubs.py` (add `configobj_stub(stubs)` and `RefusingSection`)
- Test: `tests/test_pipeline_settings_service.py`, `tests/test_nvda_config_guards.py` (new)

**Interfaces:**
- Produces:
  - `ValidateError` (module attribute of `pipeline/settings.py`);
  - `read_stored(section: Any, key: str, default: Any) -> Any`;
  - `nvda_stubs.configobj_stub(stubs) -> ModuleType`, the `configobj.validate` stub with `ValidateError`, `VdtTypeError`, `VdtValueTooSmallError` and `VdtValueTooBigError`, whose messages match configobj's `the value "%s" is …`;
  - `nvda_stubs.RefusingSection(values: dict, refused: dict[str, Exception])`, a dict whose `get` and `[]` raise `refused[key]`.

- [ ] **Step 1: Write the failing tests**
  - `test_read_stored_returns_the_default_for_an_invalid_value_and_warns_once`: a section that refuses `"group_size"` with `VdtValueTooBigError(11)`. Two reads both return `3`. `warnings` (the debugWarning stub records) has length 1 and contains `"group_size"` and `'"11"'`.
  - `test_load_reads_the_default_for_each_invalid_key[key]`, parametrized over every key of `PIPELINE_STORED_SETTINGS`:
    - the section stores `OLD_DEFAULTS` changed for one other key (`item_wait_factor=40`, or `number_wait_factor=40` when key is `item_wait_factor`), and refuses `key`;
    - `getattr(loaded, key) == DEFAULT_PIPELINE_SETTINGS[key]` (after `convert`), and the other key is still 40.
  - `test_a_new_invalid_value_warns_again`: refuse with value 11, read; refuse with 12, read; 2 warnings.
  - `test_validate_error_comes_from_configobj[source]`, with source in `"configobj.validate"`, `"validate"`, `None`. With only that stub module registered, `module.ValidateError` is that module's class; with none it is `Exception`.
  - `tests/test_nvda_config_guards.py`:
    - `test_nvda_validates_a_leaf_on_read_and_get_passes_the_error_on`: the source of `ref/nvda/source/config/__init__.py` contains `val = self.manager.validator.check(spec, val)`, and the `AggregatedSection.get` body catches only `KeyError` (ast);
    - `test_nvda_imports_validate_error_from_configobj_validate`: `argsParsing.py` contains `from configobj.validate import` with `ValidateError`.
- [ ] **Step 2: Run them to see them fail**
  - Run: `python3 -m pytest -q tests/test_pipeline_settings_service.py tests/test_nvda_config_guards.py`.
  - Expected: FAIL. `read_stored` is missing, and `ValidateError` propagates from `load`. The guard tests PASS: they pin NVDA facts.
- [ ] **Step 3: Implement in `pipeline/settings.py`**
  - The `ValidateError` import chain: `configobj.validate`, then `validate`, then `Exception`.
  - `read_stored(section, key, default)`, with a module-level `_reported: set[tuple[str, str]]` keyed by `(key, str(error))`. The message is `f"WorldVoice: stored setting {key!r} is invalid ({error}); using its default {default!r}"`.
  - `_get_value(section, key)` returns `read_stored(section, key, DEFAULT_PIPELINE_SETTINGS[key])`. Drop the `AttributeError` branch.
- [ ] **Step 4: Run the tests.** The same command PASSES.
- [ ] **Step 5: Full verification and commit.**
  - Expected: about 2273 passed, 0 skipped.
  - Commit: `fix: read an invalid stored pipeline setting as its default`.

### Task 2: Group size range 2..10, reset outside

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/settings.py` (`PipelineSettingSpec` at `:60-106`, the `group_size` entry at `:160-172`)
- Test:
  - `tests/test_pipeline_settings_service.py`;
  - `tests/test_settings_table_guard.py` (`check_bounds`, `BROKEN`);
  - `tests/test_settings_panels.py:242-270`;
  - `tests/test_pipeline_pause_properties.py` (property).

**Interfaces:**
- Consumes: Task 1 `read_stored`.
- Produces: `PipelineSettingSpec.reset_out_of_range: bool = False`. `stored_min_value` no longer exists.

- [ ] **Step 1: Change the tests first**
  - Replace `test_group_size_confspec_keeps_the_stored_minimum` with `test_group_size_confspec_is_its_range`:
    - `(spec.min_value, spec.max_value, spec.default, spec.reset_out_of_range) == (2, 10, 3, True)`;
    - `PIPELINE_CONFSPEC["group_size"] == "integer(default=3,min=2,max=10)"`;
    - `not hasattr(spec, "stored_min_value")`.
  - Split `test_convert_clamps_ints_to_their_bounds` into two tests:
    - the five non-group rows unchanged;
    - `test_group_size_outside_its_range_reads_as_the_default` with `(0,3), (-5,3), (1,3), (11,3), (99,3), (2,2), (10,10), ("7",7)`.
  - `test_group_settings_add_the_size_without_a_wait` expects the new confspec.
  - Property `test_property_group_size_convert_keeps_or_resets`: for any `st.integers()`, `convert(n) == (n if 2 <= n <= 10 else 3)`.
  - Table guard:
    - `check_bounds` drops the `stored_min_value` checks and reports `"{key}: reset_out_of_range is set on a {kind} setting"`;
    - `BROKEN` drops its two stored-minimum cases and adds `"reset on a non-int": (check_bounds, lambda m: _with(m, "scope", reset_out_of_range=True))`.
  - Panels:
    - `test_pipeline_panel_saves_an_out_of_range_group_size_clamped` becomes `..._as_the_default`, with `(0,3), (42,3)`;
    - the shown-size test uses `(0,3), (1,3), (12,3), ("4",4)`.
- [ ] **Step 2: Run them to see them fail**
  - Run: `python3 -m pytest -q tests/test_pipeline_settings_service.py tests/test_settings_table_guard.py tests/test_settings_panels.py tests/test_pipeline_pause_properties.py`.
  - Expected: FAIL on the new values and the missing field.
- [ ] **Step 3: Implement**
  - Remove `stored_min_value` and its confspec branch.
  - Add `reset_out_of_range`.
  - In `convert`, for int kinds: when `reset_out_of_range` and the result is outside `min_value..max_value`, return `self.default`; otherwise clamp.
  - Set `reset_out_of_range=True` on `group_size`, and replace its comment with the spec 3.3 reason.
- [ ] **Step 4: Run the tests.** The same command PASSES.
- [ ] **Step 5: Full verification and commit.**
  - Expected: about 2275 passed, 0 skipped.
  - Commit: `fix: read a group size outside 2..10 as 3`.

### Task 3: Log switches read through `read_stored`

**Files:**
- Modify:
  - `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (`_run_logged` at `:852-855`; import `read_stored` from `.settings`);
  - `addon/globalPlugins/WorldVoice/pipelineLog.py:24-25`;
  - `addon/globalPlugins/WorldVoice/speechSettingsDialog.py:103`.
- Modify: `tests/pipeline_harness.py` (the settings stub gets `read_stored = lambda section, key, default: section.get(key, default)`); `tests/test_pipeline_log.py` (`load_service` registers a `synthDrivers.WorldVoice.pipeline.settings` stub carrying the real `read_stored`); `tests/ui_harness.py` if the dialog loader needs it.
- Test: `tests/test_pipeline_stages.py`, `tests/test_pipeline_log.py`, `tests/test_settings_panels.py`.

**Interfaces:**
- Consumes: Task 1 `read_stored`, `RefusingSection`, `configobj_stub`.

- [ ] **Step 1: Write the failing tests**
  - `test_an_invalid_log_switch_reads_off`:
    - the pipeline module's `read_stored` is replaced by the real one from `load_settings_module`;
    - `config.conf["WorldVoice"]["log"]` is a `RefusingSection` refusing `"enable"` and `"number_mode"`, with loggingLevel `DEBUG`;
    - `module._run_logged("number_mode", fn, ["a"], settings, ctx)` returns `fn`'s output, and `log.debug` was not called.
  - `test_service_reads_an_invalid_enable_flag_as_off`: the service over a section refusing `"enable"` gives `enabled is False`.
  - `test_log_panel_shows_an_invalid_switch_unticked`: the log env with the `log` section refusing `"number_mode"`. The panel builds, and that checkbox's value is `False`.
- [ ] **Step 2: Run them to see them fail.** Expected: FAIL with the stub `ValidateError` raised.
- [ ] **Step 3: Implement**
  - `_run_logged` reads `read_stored(section, "enable", False)` and `read_stored(section, label, False)`.
  - `PipelineLogService.enabled` returns `bool(read_stored(self._section(), "enable", False))`.
  - The panel checkbox reads `read_stored(config.conf["WorldVoice"][self.field], k, v.get("default", False))`.
- [ ] **Step 4: Run the tests.** PASS.
- [ ] **Step 5: Full verification and commit.**
  - Expected: about 2278 passed, 0 skipped.
  - Commit: `fix: read an invalid stored log switch as off`.

### Task 4: Voice locale callback

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/context.py:9-16`, `addon/synthDrivers/WorldVoice/voiceManager.py` (after `:295-299`), `addon/synthDrivers/WorldVoice/__init__.py:357-367`
- Test: `tests/test_pipeline_voice_lookup.py`, `tests/test_worldvoice_pipeline_settings.py:179-198`

**Interfaces:**
- Produces:
  - `SpeechContext.voice_locale_for_language: Callable[[str], str | None] = lambda language: None`;
  - `VoiceManager.getVoiceLocaleForLanguage(language: str) -> str | None`.

- [ ] **Step 1: Write the failing tests**
  - `test_voice_locale_follows_the_voice_for_the_language`, on the composition fixture with role `zh → ok:b`:
    - `getVoiceLocaleForLanguage("zh") == "zh"`;
    - `getVoiceLocaleForLanguage("fr")` is the default voice's locale (`"en"`).
  - `test_voice_locale_is_none_for_a_voice_without_a_spec`: monkeypatch `getVoiceNameForLanguage` to return `"gone:x"`, and the result is `None`.
  - `test_generic_context_has_no_voice_locale`: `GENERIC_CONTEXT.voice_locale_for_language("zh") is None`.
  - The speech_context test: give the fake manager `getVoiceLocaleForLanguage` and assert `context["voice_locale_for_language"] == manager.getVoiceLocaleForLanguage`.
- [ ] **Step 2: Run them to see them fail.** Expected: `AttributeError` or `KeyError`.
- [ ] **Step 3: Implement** the field, the manager method (`self.catalog.by_name.get(name)`), and the wiring.
- [ ] **Step 4: Run the tests.** PASS.
- [ ] **Step 5: Full verification and commit.**
  - Expected: about 2281 passed, 0 skipped.
  - Commit: `feat: give pipeline stages the locale of the voice for a language`.

### Task 5: Symbol locale from the voice

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (imports `os`, `globalVars`, `languageHandler`; `_symbol_locale` at `:94-108`; `_symbol_namer` at `:433-449`; `inject_number_mode` at `:465`)
- Modify: `tests/pipeline_harness.py` (`globalVars.appDir = str(REF / "nvda/source")`; a `languageHandler` stub whose `normalizeLanguage` is NVDA's, via `load_definitions`)
- Test: `tests/test_pipeline_nvda_symbols.py`, `tests/test_pipeline_filters.py`

**Interfaces:**
- Consumes: Task 4 `ctx.voice_locale_for_language`.
- Produces:
  - `_has_symbol_table(locale: str) -> bool`;
  - `_symbol_locale(language: str | None, voice_locale: str | None = None) -> str`;
  - `_symbol_namer(voice_locale_for_language: Callable[[str], str | None]) -> Callable[[str | None], Callable[[str], str | None]]`.

- [ ] **Step 1: Write the failing tests**
  - `test_has_symbol_table_matches_nvdas_locale_dir[locale, expected]`:
    - true: `zh_TW`, `en`, `de_CH`;
    - false: `zh`, `en_US`, `""`, `".."`, `"../en"`.
  - `test_symbol_locale_prefers_the_voice_locale_with_a_table[current, language, voice, expected]`:

    | current | language | voice | expected |
    |---|---|---|---|
    | en | zh | zh-TW | zh_TW |
    | en | zh | zh_tw | zh_TW |
    | zh_TW | zh | zh_CN | zh_CN |
    | zh_TW | zh | zh_SG | zh_TW |
    | en | zh | zh_SG | zh |
    | en | zh | zh | zh |
    | zh_TW | zh | zh | zh_TW |
    | en | zh | x-western | zh |
    | en | zh | zh-Hant-TW | zh |
    | zh_TW | en | en_US | en |
    | en | de | de-CH | de_CH |
    | en | en | "" | en |
  - `test_namer_asks_each_language_once_per_run`:
    - a recording callback; one namer, names `×` and `.` for `"zh"` twice and for `"en"` once, gives calls `["zh", "en"]`;
    - a second `_symbol_namer(...)` asks `"zh"` again;
    - `for_language(None)` never calls the callback.
  - `test_symbol_names_follow_the_voice_locale`, in test_pipeline_filters:
    - roles context, language `"zh"`, number language `"en"`, `voice_locale_for_language={"en": "zh-TW"}.get`, `speech.getCurrentLanguage` gives `"en"`: names are `[N("×", "zh_TW")]`;
    - the same with number language `"default"` and `{"zh": "zh_CN"}.get`: names are `[N("×", "zh_CN")]`.
  - `test_nvda_builtin_symbols_live_in_appdir_locale` (guard): `characterProcessing.py` source contains `os.path.join(globalVars.appDir, "locale", "{locale}", "symbols.dic")` in a definition named `"builtin"` with `mandatory=True`.
  - `test_normalize_language_is_nvdas` (guard): `load_definitions(languageHandler.py, ["normalizeLanguage"])` gives `"zh_TW"` for `"zh-tw"` and `None` for `"x-western"`.
  - `test_pipeline_names_symbols_from_the_voice_locale_with_nvdas_real_lookup[voice, name]`, with `("zh-TW", "乘以")` and `("zh_SG", "times")`. NVDA's real characterProcessing, getCurrentLanguage `"en"`, and `_symbol_name(_symbol_locale("zh", voice), "×") == name`.
- [ ] **Step 2: Run them to see them fail**
  - Run: `python3 -m pytest -q tests/test_pipeline_nvda_symbols.py tests/test_pipeline_filters.py`.
  - Expected: FAIL. `_has_symbol_table` is missing and `_symbol_locale` takes one argument; the guards PASS.
- [ ] **Step 3: Implement**
  - `_has_symbol_table`: the locale must be non-empty and `locale.replace("_", "").isalnum()`, and then `os.path.isfile(...)`.
  - The voice branch of `_symbol_locale` (spec 3.2).
  - `_symbol_namer` keyed by language, calling the callback only for a truthy language.
  - `inject_number_mode` builds `_symbol_namer(ctx.voice_locale_for_language)`.
  - Update the docstrings.
- [ ] **Step 4: Run the tests.** PASS.
- [ ] **Step 5: Full verification and commit.**
  - Expected: about 2310 passed, 0 skipped.
  - Commit: `feat: name number symbols in the locale of the voice that speaks them`.

### Task 6: M4 test and the previous spec

**Files:**
- Modify: `tests/test_pipeline_stages.py:242-259`
- Modify: `docs/superpowers/specs/2026-10-22-feat-number-unify-design.md` (F2 at `:66`, 6.4.1 symbol locale at `:287-295`, M10 at `:658`)

- [ ] **Step 1: Rewrite `test_symbol_names_follow_the_number_language_without_its_voice`**
  - Rename it `test_symbol_names_without_a_number_language_voice_use_the_default_voice_locale`.
  - `voice_name_for_language=lambda language: "Z"` (`getVoiceNameForLanguage`'s default-voice return) and `voice_locale_for_language=lambda language: "zh_TW"`.
  - Expected strings `["2", "multiplication sign zh tw", "3"]`, and still no language command.
- [ ] **Step 2: Run it.**
  - Run: `python3 -m pytest -q tests/test_pipeline_stages.py`.
  - Expected: PASS (Task 5 is in). Check RED by temporarily passing `None` as the voice locale in `inject_number_mode`; it fails with `"multiplication sign en"`. Revert.
- [ ] **Step 3: Previous spec.** Strike through the superseded sentences (F2 "from the NUMBER LANGUAGE's symbol table", 6.4.1's number-language bullet, M10's expectation). Add after each: `Changed by \`feat/symbol-locale-and-settings-fallback\` (user, 2026-10-22): <the new rule in one line>`.
- [ ] **Step 4: Full verification and commit.**
  - Expected: the same count as Task 5.
  - Commit: `test: expect default-voice names when the number language has no voice`.

### Task 7: mutmut and final verification

**Files:**
- Modify: this plan (append `## Mutation results`)

- [ ] **Step 1: Run mutmut**
  - Use 3 workers and the memory guard on `pipeline/__init__.py` `x__has_symbol_table*`, `x__symbol_locale*` and `x__symbol_namer*`, and on `pipeline/settings.py` `x_read_stored*`, `x__get_value*` and `xǁPipelineSettingSpecǁconvert*`/`confspec*`.
  - Kill a meaningful survivor with a test (RED on the mutant, GREEN on the source). Record equivalent survivors with a reason.
- [ ] **Step 2: Full verification (§7).**
  - pytest: the final count, 0 skipped.
  - `prek run --all-files`: all Passed.
  - `git diff --check master`: clean.
  - Both protected-path commands: empty.
- [ ] **Step 3: Commit** the plan update: `docs: record the symbol-locale mutation results`.

## Mutation results

The run used mutmut 3.8.0 on 2026-10-22 against `da29e37`, in the worktree, with 3 children and the memory guard. It made 96 mutants in the changed decision functions: 94 were killed and 2 survived.

| Function | Killed | Survived |
| --- | --- | --- |
| `pipeline._has_symbol_table` | 20 | 1 |
| `pipeline._symbol_locale` | 21 | 1 |
| `pipeline._symbol_namer` | 19 | 0 |
| `settings.read_stored` | 9 | 0 |
| `settings._get_value` | 6 | 0 |
| `settings.PipelineSettingSpec.convert` | 19 | 0 |

- **Equivalent survivor:** `x__has_symbol_table__mutmut_7`, `locale.replace("_", "")` → `locale.replace("_", "XXXX")`. Replacing `_` with any alphanumeric text gives the same `isalnum()` answer, so no locale can tell the two apart.
- **Equivalent survivor (number-unify line, unchanged here):** `x__symbol_locale__mutmut_15`, `"_" not in locale` → `"XX_XX" not in locale`. A locale that contains `_` can never equal `current.split("_")[0]`, which has none, so the `_` test only documents intent.
- **Not mutated by mutmut 3:** `PipelineSettingSpec.confspec` is a property. It is pinned by `test_group_size_confspec_is_its_range`, `test_int_confspec_carries_the_spec_bounds` and the table guard.
- **Tooling fix needed to run mutmut** (`da29e37`). pytest escapes explicit non-ASCII parametrize ids in place, so mutmut's second in-process collection could not select the spec-table tests. The ids are now ASCII.
