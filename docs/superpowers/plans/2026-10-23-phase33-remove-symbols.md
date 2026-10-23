# Phase 33 Remove Symbols and Restore Base-Language Preference Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** Remove the speech-symbols ("Unicode Settings") feature, make detection prefer the base language again after a run in another script, and stop counting a language without an installed voice as covering a script, with characterization, property and mutation tests around the detector.

**Architecture:** One private predicate `LanguageDetector._covers(language, script) -> bool` (primary subtag in `SCRIPT_LANGUAGES[script]` and in `availableLanguages`) and one keyword `base_language=None` on `find_language_for_script` carry Parts B and C; both `add_detected_language_commands` and `process_for_spelling` pass their base, so the spelling normalization at `detection:187-188` goes. Part A deletes `addon/generics/speechSymbols/`, its menu item and script, the synth's symbol loading and the detector's `speechSymbols` parameter, then pins the removal with a static guard and turns DeprecationWarnings into test errors.

**Tech Stack:** Python 3.14, pytest 9.1.1, Hypothesis 6.168.5, mutmut 3.8.0, ruff 0.16.3 via prek 0.4.14, GNU gettext (`msgfmt`).

**Spec:** `docs/superpowers/specs/2026-10-23-phase33-remove-symbols-design.md` (commit `a484481`). Its orchestrator defaults Q1–Q7 (§11) stand as written. Line numbers below refer to `9d5b8c5`; `detection:<n>` is `addon/synthDrivers/WorldVoice/languageDetection/__init__.py:<n>`.

## Global Constraints

- Detection order for a letter of script S (spec §2.3, §3.3): no candidates → current; current covers S → current; base covers S → base exactly as given; configured language (primary in candidates and available) → configured value; first available candidate in tuple order → it; otherwise → current. "Covers" = `primary(L) in SCRIPT_LANGUAGES[S] and primary(L) in availableLanguages`. Digits, Common/Inherited, the emitted `WVLangChangeCommand` and "emit only on a primary-subtag change" are unchanged (spec §4).
- `LanguageDetector(availableLanguages, *, settings, language)`; a second positional argument raises `TypeError` (spec §1.2).
- Keep the synth's `base_dir` / `sys.path.insert` (`addon/synthDrivers/WorldVoice/__init__.py:56-57`) with a comment saying the global plugin's `generics.coreArchive` needs it. Keep `addon/generics/coreArchive.py`, the "Unicode Detection" panel, and `buildVars.py` untouched.
- `unicode.dic` on disk is left alone; no add-on source mentions it afterwards (Q1).
- No new strings, settings, config keys or defaults. zh_TW `nvda.po`: delete the 25 entries outright (no `#~`); other locales untouched (spec §7). Readmes: the two sentences of Q5, plus removing the non-existent "Ignore common punctuation" bullet and the intro's "punctuation" in all six readmes (decided by the user, 2026-10-23); no changelog edit.
- `[tool.pytest.ini_options] filterwarnings = ["error::DeprecationWarning"]` once the two warnings are gone (Q2). `languageDetection/__init__.py` joins `[tool.mutmut] source_paths` permanently (Q7).
- Never modify `addon/synthDrivers/WorldVoice/driver/<Engine>/driver/`, `driver/sonic/` or `languageDetection/script_data.py`. Engine drivers stay independently installable (no driver imports another driver's package; shared code only in core). Never add Neural back.
- ruff is pinned `==0.16.3`. Every commit runs the prek hooks; if a hook rewrites files, restage and recommit; never `--no-verify`.
- git: stage explicit paths only; check `git diff --cached --stat` before each commit. Messages in English, `<type>: <summary>`, with a body that says why. No `Co-Authored-By`. Never `git stash`, never push, never touch `/workspace/WorldVoice` (reading `ref/` through the symlink is fine). Never stage `ref`. `docs/` is git-ignored: stage plan files with `git add -f`.
- Full suite: `python3 -m pytest -q -p no:cacheprovider tests`, single process, under the scratchpad memory guard (kill when MemAvailable < 3 GB). mutmut: `--max-children 3`, same guard, scratch clone only.
- Baseline on `9d5b8c5`: **2372 passed, 0 skipped, 2 warnings**. Target after Task 10: **2401 passed, 0 skipped, 0 warnings** (Task 11 may add mutant-killing tests).
- Each task ends with the §7 checks: full suite, `prek run --all-files` all Passed, `git diff --check master`, and both protected-path commands print nothing.

## Review Focus

1. **A document marks a regional variant whose primary subtag has a voice** (`Lang("en_GB")` with only en_US installed). Availability is by primary subtag, so the run stays en_GB and nothing is inserted. Task 2: `test_unavailable_language_does_not_cover_its_script[installed-primary]`.
2. **A language with no voice followed by digits while "Ignore numbers" is on** (`[Lang("de_DE"), "12 hallo"]`). The digits stay in the run they follow; only the letters switch: `<de_DE>` `12 ` `<en>` `hallo`. Task 2: `test_unavailable_language_does_not_cover_its_script[digits-ignored]`.
3. **A hyphenated base locale** (`ar-WW`, as some engines publish). After another script, the base comes back exactly as given, not as `ar`. Task 3: `test_base_language_wins_after_another_script[hyphenated-base]`.
4. **Spelling with a hyphenated locale** (`process_for_spelling("a漢", "zh-TW")`). With the normalization at `detection:187-188` gone, the base run must still carry `zh-TW` exactly. Task 4: `test_spelling_prefers_the_spelling_locale[hyphenated-locale]`.
5. **An old caller that passes the symbols** (positionally or as `speechSymbols=`). It must fail loudly at construction with `TypeError`, not silently ignore them. Task 5: `test_symbols_argument_is_rejected[positional]`, `[keyword]`.

---

### Task 1: Characterization of detection (spec §10.1)

**Files:**
- Test: `tests/test_language_detector.py`

**Interfaces:**
- Consumes: `make_detector(env, languages=...)`, `shape(env, sequence)`, `switching(env)`, `LangChangeCommand` (harness), `env.state.language`.
- Produces: `detect(env, sequence, *, languages, base, **preferences) -> list` in `tests/test_language_detector.py` (sets `env.state.language = base`, writes each preference into `switching(env)`, returns `shape(...)` of the detector output); Tasks 2–3 use it. `L = LangChangeCommand` alias.

- [ ] **Step 1: Write `test_detection_characterization`** parametrized with ids, through `detect`. Preference keys are `CJKCharactersLanguage`, `latinCharactersLanguage`, `ignoreNumbersInLanguageDetection` (harness defaults: CJK `zh`, Latin `en`, ignore off).

| id | languages | base | prefs | input | expected |
|---|---|---|---|---|---|
| full-width | en_US, zh_TW | en_US | CJK zh_TW | `["hi 你好，世界。"]` | `["hi ", ("lang","zh_TW"), "你好，世界。"]` |
| hanja | en_US, ko_KR, ja_JP | ko_KR | — | `["한국 漢字 한국"]` | `["한국 漢字 한국"]` |
| hindi | en_US, hi_IN | en_US | — | `["hi नमस्ते"]` | `["hi ", ("lang","hi"), "नमस्ते"]` |
| myanmar | en_US, my_MM | en_US | — | `["hi မြန်မာ"]` | `["hi ", ("lang","my"), "မြန်မာ"]` |
| hyphenated-voice | en_US, ar-WW | en_US | — | `["hi مرحبا"]` | `["hi ", ("lang","ar"), "مرحبا"]` |
| ru-before-uk | en_US, uk_UA, ru_RU | en_US | — | `["hi привет"]` | `["hi ", ("lang","ru"), "привет"]` |
| no-greek-voice | en_US | en_US | — | `["hi Ελληνικά"]` | `["hi Ελληνικά"]` |
| digits-to-base | en_US, zh_TW | en_US | CJK zh_TW | `["中12"]` | `[("lang","zh_TW"), "中", ("lang","en_US"), "12"]` |
| digits-ignored | en_US, zh_TW | en_US | CJK zh_TW, ignore on | `["中12"]` | `[("lang","zh_TW"), "中12"]` |
| no-latin-voice | zh_TW | zh_TW | — | `[L("de_DE"), "hallo 你好"]` | `[("lang","de_DE"), "hallo ", ("lang","zh"), "你好"]` |

- [ ] **Step 2: Run on the unchanged detector**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_language_detector.py`
Expected: all green (characterization must pass before any change). If a row differs, the baseline output is the truth: record a Ruling and use the baseline output.

- [ ] **Step 3: §7 checks.** Expected full suite **2382 passed, 0 skipped, 2 warnings**; prek all Passed; diff-check and protected paths empty.

- [ ] **Step 4: Commit** `tests/test_language_detector.py` — `test: characterize language detection before the phase 33 changes`.

---

### Task 2: A language without an installed voice does not cover a script (Part C)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/languageDetection/__init__.py:111-126`
- Test: `tests/test_language_detector.py`

**Interfaces:**
- Consumes: `detect` (Task 1).
- Produces: `LanguageDetector._covers(self, language: str, script: str) -> bool` — `primary(language)` in `SCRIPT_LANGUAGES.get(script, ())` and in `self.availableLanguages`. Task 3 uses it for the base.

- [ ] **Step 1: Write the red tests**

`test_unavailable_language_does_not_cover_its_script`, parametrized (ids in brackets):
- `[C1]` languages en_US, zh_TW; base en_US; `[L("de_DE"), "hallo 你好"]` → `[("lang","de_DE"), ("lang","en"), "hallo ", ("lang","zh"), "你好"]`
- `[C2]` same voices/base; `[L("de_DE"), ", hallo"]` → `[("lang","de_DE"), ", ", ("lang","en"), "hallo"]`
- `[C4]` fr_FR, zh_TW, en_US; base zh_TW; Latin fr; `[L("de_DE"), "hallo"]` → `[("lang","de_DE"), ("lang","fr"), "hallo"]`
- `[digits-ignored]` en_US, zh_TW; base en_US; ignore on; `[L("de_DE"), "12 hallo"]` → `[("lang","de_DE"), "12 ", ("lang","en"), "hallo"]` (Review Focus 2)
- `[installed-primary]` en_US, zh_TW; base en_US; `[L("en_GB"), "hello"]` → `[("lang","en_GB"), "hello"]` (Review Focus 1; green before and after)

`test_spelling_with_an_unavailable_locale`: `list(make_detector(env, languages=("en_US","zh_TW")).process_for_spelling("a b", "de_DE")) == [("a","en"), (" ","de_DE"), ("b","en")]`.

- [ ] **Step 2: Run to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_language_detector.py -k "unavailable"`
Expected: 5 failed (C1, C2, C4, digits-ignored, spelling: detection stays on de_DE), 1 passed (installed-primary).

- [ ] **Step 3: Implement `_covers(language, script)`** and use it for the current-language check in `find_language_for_script` (the `not candidates` early return stays).

- [ ] **Step 4: Run green**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_language_detector.py`
Expected: all passed; no existing test changes.

- [ ] **Step 5: §7 checks.** Expected **2388 passed, 0 skipped, 2 warnings**.

- [ ] **Step 6: Commit** — `fix: let only installed languages cover a script in detection` (body: upstream builds coverage from installed languages only; a document language without a voice kept its letters on the main voice).

---

### Task 3: Prefer the base language after another script (Part B, main detector)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/languageDetection/__init__.py:111-136`
- Test: `tests/test_language_detector.py` (new tests; update `:35-37` and `:106-117`)

**Interfaces:**
- Consumes: `_covers` (Task 2), `detect` (Task 1).
- Produces: `find_language_for_script(self, script, current_language, settings=None, base_language=None) -> str`; two-argument calls keep working. `_language_for_character` passes its `base_language`. Task 4 passes `base_language` from spelling.

- [ ] **Step 1: Write the red tests and update the two regression pins**

`test_base_language_wins_after_another_script`, parametrized:
- `[R1]` en_US, zh_TW, ja_JP; base zh_TW; CJK ja; `["你好 hello 世界"]` → `["你好 ", ("lang","en"), "hello ", ("lang","zh_TW"), "世界"]`
- `[R2]` en_GB, en_US, zh_TW; base en_GB; CJK zh_TW; `["hi 你好 ok"]` → `["hi ", ("lang","zh_TW"), "你好 ", ("lang","en_GB"), "ok"]`
- `[R3]` en_US, ja_JP, zh_TW; base ja_JP; CJK zh_TW; `["漢字 hello 漢字"]` → `["漢字 ", ("lang","en"), "hello ", ("lang","ja_JP"), "漢字"]`
- `[R4]` en_US, zh_TW, ja_JP; base zh_TW; CJK ja; `[L("ja"), "中", L(None), "a中"]` → `[("lang","ja"), "中", ("lang",None), ("lang","en"), "a", ("lang","zh_TW"), "中"]`
- `[hyphenated-base]` en_US, ar-WW; base ar-WW; `["مرحبا hi مرحبا"]` → `["مرحبا ", ("lang","en"), "hi ", ("lang","ar-WW"), "مرحبا"]` (Review Focus 3)

`test_find_language_for_script_prefers_an_available_base`, parametrized on default languages (en_US, zh_TW, ja), CJK ja: `find_language_for_script("Han", "en_US", base_language="zh_TW") == "zh_TW"`; `base_language="ko_KR"` (no voice) → `"ja"`.

Update (spec §10.3): `test_mixed_scripts_switch_at_script_boundaries` expects `[..., "中文 ", ("lang","en_US"), "ok"]`; `test_one_settings_read_per_sequence` expects `[("lang","zh"), "中1中1 ", ("lang","en_US"), "abc ", ("lang","ar"), "عربي 2"]`.

- [ ] **Step 2: Run to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_language_detector.py -k "base or mixed_scripts or settings_read_per_sequence"`
Expected: 9 failed (the 5 new cases, both `find_language_for_script` cases with `TypeError` for the unknown keyword, the 2 updated pins: the configured or `en` language wins over the base); the other selected tests pass.

- [ ] **Step 3: Implement** the `base_language` keyword (step 3 of the order, after the current-language check, before the configured language; `None` skips it) and pass `base_language` from `_language_for_character`.

- [ ] **Step 4: Run green**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_language_detector.py`
Expected: all passed, including Task 1's characterization.

- [ ] **Step 5: §7 checks.** Expected **2395 passed, 0 skipped, 2 warnings**.

- [ ] **Step 6: Commit** — `fix: prefer the base language again in detection` (body: regression from `9816ce0`; the two updated tests pinned the regressed `en` result, R1–R3 user impact).

---

### Task 4: Spelling uses the same order (spec §2.4, Q3)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/languageDetection/__init__.py:172-196` (pass `base_language=default_language`; delete `:187-188`)
- Test: `tests/test_language_detector.py` (new test; update `:75-77`)

**Interfaces:**
- Consumes: `find_language_for_script(..., base_language=...)` (Task 3).
- Produces: `process_for_spelling(text, locale=None)` unchanged signature.

- [ ] **Step 1: Write the red test and update the pin**

`test_spelling_prefers_the_spelling_locale`, languages en_US, zh_TW, ja_JP unless stated, parametrized:
- `[base-ja]` CJK zh_TW; `process_for_spelling("a漢", "ja_JP")` → `[("a","en"), ("漢","ja_JP")]`
- `[base-zh]` CJK ja; `("a中", "zh_TW")` → `[("a","en"), ("中","zh_TW")]`
- `[hyphenated-locale]` languages en_US, zh-TW; CJK zh; `("a漢", "zh-TW")` → `[("a","en"), ("漢","zh-TW")]` (Review Focus 4; green before and after)

Update `test_spelling_with_locale`: `[("a","en"), ("中 1","ja")]`.

- [ ] **Step 2: Run to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_language_detector.py -k spelling`
Expected: 3 failed (`base-ja` → `zh_TW`, `base-zh` → `ja`, `test_spelling_with_locale` → `zh`), the rest passed.

- [ ] **Step 3: Implement** — pass `base_language=default_language` and remove the two normalization lines.

- [ ] **Step 4: Run green**: same command, all passed.

- [ ] **Step 5: §7 checks.** Expected **2398 passed, 0 skipped, 2 warnings**.

- [ ] **Step 6: Commit** — `fix: let spelling prefer the spelling locale like detection does` (body: Q3 default; the normalization became dead code, the invariant gets a property test in Task 10).

---

### Task 5: Drop the symbols from the detector and the synth (Part A)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/languageDetection/__init__.py:104-106`, `:149-158`
- Modify: `addon/synthDrivers/WorldVoice/__init__.py:56-58`, `:177`, `:262-274`, `:290`
- Test: `tests/test_language_detector.py` (`:15-22`, `:52-55`, `:109-114`, `:122-127`), `tests/test_worldvoice_lifecycle.py` (`:87-95`, `:177`, `:201-224`, `:252-256`), `tests/test_worldvoice_speak.py:182`, `tests/test_worldvoice_pipeline_settings.py:201`, `tests/test_runtime_composition.py:592-594`

**Interfaces:**
- Consumes: nothing new.
- Produces: `LanguageDetector(availableLanguages, *, settings, language)`; the synth has no `speechSymbols` attribute and no `generics` import.

- [ ] **Step 1: Write the red tests and update the stubs**

- `test_symbols_argument_is_rejected`, parametrized `[positional]` (`LanguageDetector(["en_US"], None, settings=env.settings, language=...)`) and `[keyword]` (`speechSymbols=None`): `pytest.raises(TypeError)`. (Review Focus 5)
- `make_detector` loses `symbols`; the two direct constructions lose `None`; delete `test_mode_one_symbol_speaks_its_replacement_in_its_language`.
- Lifecycle: delete the `SpeechSymbols` stub and its environment entry; `LanguageDetector.__init__(self, languages, **providers)` raises `RuntimeError("detector failure")` when `failure == "detector"`. Parametrize `["manager", "detector", "bridge"]`, `match="no voices|detector failure|bridge failure"`; the `failure == "detector"` branch asserts `"engine stopped" in changes` and `changes.index("bridge stopped") < changes.index("engine stopped")`. Rename `test_stages_register_after_symbols_and_detector` → `test_stages_register_after_the_detector`, keeping only the detector assertion.
- Drop `synth.speechSymbols = None` (speak) and `synth.speechSymbols` (pipeline settings: `synth._numlan = "default"`); drop the three `generics` stubs in `test_runtime_composition.py`.

- [ ] **Step 2: Run to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_language_detector.py tests/test_worldvoice_lifecycle.py tests/test_runtime_composition.py`
Expected: `test_symbols_argument_is_rejected` 2 failed (DID NOT RAISE); lifecycle construction tests fail with `NameError: SpeechSymbols` (or the stub's signature `TypeError`); composition fails importing `generics.speechSymbols`.

- [ ] **Step 3: Implement** — detector signature and loop without the symbols branch (`text` is `c`); synth: replace the line-58 import with a comment that the add-on root stays on `sys.path` for the global plugin's `generics.coreArchive` import, remove `self.speechSymbols`, the two timed blocks and the argument; the `:290` comment becomes "voices and the number language exist".

- [ ] **Step 4: Run green**: same command, all passed.

- [ ] **Step 5: §7 checks.** Expected **2399 passed, 0 skipped, 2 warnings** (the `models.py` warnings remain until Task 7).

- [ ] **Step 6: Commit** — `refactor: stop loading speech symbols in the synth and detector`.

---

### Task 6: Remove the Unicode Settings menu item and script

**Files:**
- Modify: `addon/globalPlugins/WorldVoice/__init__.py:20`, `:59-60`, `:126-130`, `:139-144`
- Test: `tests/test_global_plugin_menu.py:34-43`, `:84-92`; `tests/ui_harness.py:877-879`

**Interfaces:**
- Consumes: nothing.
- Produces: `GlobalPlugin` without `popup_SpeechSymbolsDialog` / `script_popup_unicode_settings_dialog`; the harness env without `symbols_dialog`.

- [ ] **Step 1: Write the red tests**

- `test_starting_adds_the_worldvoice_menu_to_nvdas_menu`: submenu `[("&Settings","Settings."), ("&File Import","Import File.")]`, bindings `[("EVT_MENU", p.popup_SpeechSettingsDialog, items[0]), ("EVT_MENU", p.onFileImport, items[1])]`; the insert position assertion is unchanged.
- Delete `test_unicode_script_opens_the_symbols_dialog_once`; add `test_unicode_settings_are_gone`: neither `"script_popup_unicode_settings_dialog"` nor `"popup_SpeechSymbolsDialog"` is an attribute of `env.module.GlobalPlugin`.
- `ui_harness.py`: drop the three `generics.speechSymbols` lines; keep `generics` and `generics.coreArchive`.

- [ ] **Step 2: Run to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_global_plugin_menu.py tests/test_global_plugin_lifecycle.py`
Expected: failures importing the real `generics.speechSymbols.views` (wx is a stub) in every plugin test.

- [ ] **Step 3: Implement** the four removals; the submenu keeps "&Settings" then "&File Import", inserted at position 2.

- [ ] **Step 4: Run green**: same command, all passed.

- [ ] **Step 5: §7 checks.** Expected **2399 passed, 0 skipped, 2 warnings**.

- [ ] **Step 6: Commit** — `feat: remove the Unicode Settings menu item and gesture script`.

---

### Task 7: Delete the speech-symbols package and guard its absence

**Files:**
- Delete: `addon/generics/speechSymbols/__init__.py`, `models.py`, `views.py`
- Modify: `pyproject.toml:25-26`
- Test: `tests/test_hygiene_guards.py`, `tests/test_format_outputs.py`

**Interfaces:**
- Consumes: Tasks 5–6 (no importer left).
- Produces: `test_the_speech_symbols_feature_is_gone` in `tests/test_hygiene_guards.py`.

- [ ] **Step 1: Write the red guard** `test_the_speech_symbols_feature_is_gone`:
  - `not (ADDON / "generics" / "speechSymbols").exists()`;
  - over `_addon_sources()`, collected offenders list is `[]` for: an `ast.Import` alias or `ast.ImportFrom` module equal to `generics.speechSymbols` or starting with `generics.speechSymbols.`, an `ImportFrom` of module `generics` naming `speechSymbols`, and any source text containing `"unicode.dic"`.

Delete from `test_format_outputs.py`: `MODELS`, the `models` fixture, `test_speech_symbol_repr`, `test_saved_symbol_lines`, `test_invalid_symbol_line_warning` and their four `EXPECTED_*` constants, plus imports left unused.

- [ ] **Step 2: Run to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_hygiene_guards.py -k speech_symbols`
Expected: 1 failed on the existence assertion (no importer and no `unicode.dic` mention is left after Tasks 5–6).

- [ ] **Step 3: Implement** — `git rm -r addon/generics/speechSymbols`; remove the `views.py` omit entry and its comment from `[tool.coverage.run]`.

- [ ] **Step 4: Run green**: same command, passed.

- [ ] **Step 5: §7 checks.** Expected **2397 passed, 0 skipped, 0 warnings**.

- [ ] **Step 6: Commit** — `feat: delete the speech symbols package` (body: Q1, `unicode.dic` stays on disk; the guard keeps it gone).

---

### Task 8: zh_TW catalog and readmes

**Files:**
- Modify: `addon/locale/zh_TW/LC_MESSAGES/nvda.po` (lines 23-125, 406-412, 441-443, 449-451)
- Modify: `readme.md:55-60`, `addon/doc/zh_TW/readme.md:55-60`, `addon/doc/zh_HK/readme.md:53-56`, `addon/doc/zh_CN/readme.md:54-57`, `addon/doc/ru/readme.md:54-57`, `addon/doc/uk/readme.md:54-57`
- Modify: `docs/superpowers/specs/2026-10-23-phase33-remove-symbols-design.md` §7 (user decision note)

**Interfaces:** none.

- [ ] **Step 1: Delete the 25 entries** (spec §7): the 21 `models.py`/`views.py` entries (from `context` to `unicode rule edited`, including the `msgctxt "speechSymbols"` "&Filter by:"), "&Unicode Settings", "Unicode Settings.", "SpeechSymbolsDialog have already been opened", "popup unicode settings dialog". The translator comment block before the next entry stays with that entry.

- [ ] **Step 2: Verify the catalog**

Run: `msgfmt --check -o /dev/null addon/locale/zh_TW/LC_MESSAGES/nvda.po` and a scratch Python check that none of the 25 msgids remains as an active `msgid` and that `git diff` removes exactly 25 `msgid` lines.
Expected: msgfmt prints nothing, exit 0; the check reports 0 remaining, 25 removed.

- [ ] **Step 3: Append the Q5 sentences** to the "Assumed language for character sets" bullet, verbatim from spec §7 (EN in `readme.md`, zh_TW in `addon/doc/zh_TW/readme.md`).

- [ ] **Step 4: Remove the non-existent punctuation option** (decided by the user, 2026-10-23; the option went with `9816ce0`): delete the "Ignore common punctuation during language detection" bullet in `readme.md:58`, `addon/doc/zh_TW/readme.md:58`, `addon/doc/zh_HK/readme.md:56`, `addon/doc/zh_CN/readme.md:57`, `addon/doc/ru/readme.md:57`, `addon/doc/uk/readme.md:57`, and drop "punctuation" from each intro sentence that names it (EN `:55` → "numbers and character sets shared by multiple languages"; zh_TW/zh_HK「數字與多語共用字元集」; zh_CN「数字与多语共用字符集」; ru «числа и наборы символов»; uk «числа та набори символів»). Add the user decision to spec §7.
Expected: `grep -rn "punctuation during language detection\|忽略常見標點\|忽略常见标点\|знаки препинания при\|розділові знаки під" readme.md addon/doc` prints nothing.

- [ ] **Step 5: §7 checks.** Expected **2397 passed, 0 skipped, 0 warnings** (`test_translator_comments.py` included).

- [ ] **Step 6: Commit** (plus the spec with `git add -f`) — `docs: drop the removed symbol strings and explain the base-language rule`.

---

### Task 9: DeprecationWarnings fail the suite (spec §1.5, Q2)

**Files:**
- Modify: `pyproject.toml` (new `[tool.pytest.ini_options]` before `[tool.mutmut]`)
- Test: `tests/test_hygiene_guards.py`

**Interfaces:** none.

- [ ] **Step 1: Write the red test** `test_deprecation_warnings_fail_the_suite`: `with pytest.raises(DeprecationWarning, match="probe"): warnings.warn("probe", DeprecationWarning, stacklevel=1)`. It lives in the hygiene guards, which mutmut ignores (`pyproject.toml:56`).

- [ ] **Step 2: Run to see red**: `python3 -m pytest -q -p no:cacheprovider tests/test_hygiene_guards.py -k deprecation` → 1 failed (DID NOT RAISE).

- [ ] **Step 3: Implement** `[tool.pytest.ini_options]` with `filterwarnings = ["error::DeprecationWarning"]` and a comment: NVDA's own `codecs.open` stays ignored by the marks in `tests/test_pipeline_nvda_symbols.py:19-20`.

- [ ] **Step 4: Run green**: same command, passed.

- [ ] **Step 5: §7 checks.** Expected **2398 passed, 0 skipped, 0 warnings**.

- [ ] **Step 6: Commit** — `test: fail the suite on DeprecationWarnings`.

---

### Task 10: Hypothesis properties of detection (spec §10.5)

**Files:**
- Test: `tests/test_language_detector.py` (new properties; widen `:137-166`)

**Interfaces:**
- Consumes: `env.module.get_script`, `env.module.SCRIPT_LANGUAGES`, `env.module.get_primary_language`.
- Produces: a `scenarios` strategy drawing `installed` (unique non-empty subset of `en_US, en_GB, zh_TW, ja_JP, ko_KR, ar-WW, ru_RU, uk_UA, de_DE, fr_FR, hi_IN, el_GR`), `base` (one of `installed`, so the synth language is always available, spec §3.2), CJK (`zh, zh_TW, ja, ko`), Latin (`en, fr, de`), Arabic (`ar, fa`), ignore numbers, and items mixing texts (the existing samples plus `漢字, привет, 한국, かな, Ελληνικά, 12, ，`) with `LangChangeCommand` over `None, de_DE, ar-WW, zh_TW, en_GB, ja, fr, xx_YY` and plain objects.

- [ ] **Step 1: Write the properties** (each sets `env.state.language` and every preference per example):
  1. `test_property_inserted_letter_commands_name_installed_languages`: for every inserted `WVLangChangeCommand` followed by text whose first character is a letter (not a digit, script not `None/Common/Inherited`), `primary(command.lang)` is installed; and for every letter whose script some installed language covers, the language in effect when it is spoken covers that script (the strong form of Part C).
  2. `test_property_inserted_commands_prefer_a_covering_base`: tracking the base as `command.lang or synth language` across given commands, every inserted command before a letter whose script the base covers names the base exactly.
  3. `test_property_spelling_runs_of_the_base_primary_carry_the_base`: for `process_for_spelling(text, locale)` with locale `None`, one of the command languages or an installed one, every run whose primary equals the base's has the base locale exactly, and the runs join back to `text`.
  4. `test_property_detection_only_inserts_language_changes` draws from `scenarios` instead of the fixed four languages.

- [ ] **Step 2: Show they bite.** In a scratch copy of the worktree, remove the base step from `find_language_for_script`, then separately the availability check in `_covers`.
Expected: property 2 and 3 fail without the base step; property 1 (strong form) fails without the availability check. The worktree is untouched.

- [ ] **Step 3: Run green**: `python3 -m pytest -q -p no:cacheprovider tests/test_language_detector.py -k property` → 4 passed; also once with `HYPOTHESIS_PROFILE=deep` → 4 passed.

- [ ] **Step 4: §7 checks.** Expected **2401 passed, 0 skipped, 0 warnings**.

- [ ] **Step 5: Commit** — `test: add property tests for base preference and installed coverage`.

---

### Task 11: mutmut on the detector, coverage, final verification

**Files:**
- Modify: `pyproject.toml:38-50` (append `"addon/synthDrivers/WorldVoice/languageDetection/__init__.py"`)
- Test: `tests/test_language_detector.py` (only if a survivor is not equivalent)
- Modify: this plan (append "Implementation notes: mutmut")

**Interfaces:**
- Consumes: Tasks 1–10.
- Produces: the report to the orchestrator.

- [ ] **Step 1: Add the source path** (Q7) and commit it with the notes in Step 4.

- [ ] **Step 2: Run mutmut** in a scratch `git clone --shared` of the branch head (with `ref` symlinked), under the memory guard: `mutmut run --max-children 3 "addon.synthDrivers.WorldVoice.languageDetection.*"`.
Expected: the clean/stats run passes with the DeprecationWarning filter active (confirm `pyproject.toml` is in `mutants/`); no "suspicious" or timeout; every survivor listed with `mutmut show`.

- [ ] **Step 3: Kill or explain each survivor.** A non-equivalent survivor gets a test in `tests/test_language_detector.py` that fails with the mutant applied in the scratch copy and passes without it (re-run mutmut for that function). An equivalent one gets its reason.

- [ ] **Step 4: Record** an "Implementation notes: mutmut" section at the end of this plan (counts per function, survivors with reasons, lowest MemAvailable) and commit it with the `pyproject.toml` change — `test: add the language detector to the mutmut sources`.

- [ ] **Step 5: Coverage.** Run `python3 -m pytest -q -p no:cacheprovider tests --cov` on the branch head and on a scratch export of `master` (with `ref` symlinked), under the guard.
Expected: the branch's total line+branch coverage is not lower than master's; `languageDetection/__init__.py` stays at 100% or better than master.

- [ ] **Step 6: §7 on the branch head.** Full suite (**2401 + Task 11 additions passed, 0 skipped, 0 warnings**), `prek run --all-files`, `git diff --check master`, both protected-path commands, `msgfmt --check` on zh_TW.

- [ ] **Step 7: Report** to the orchestrator: commits, counts, prek, diff-check, protected paths, msgfmt, mutmut survivors with reasons, Rulings, spec contradictions; Windows/NVDA manual items (spec §10.8) not verified.
