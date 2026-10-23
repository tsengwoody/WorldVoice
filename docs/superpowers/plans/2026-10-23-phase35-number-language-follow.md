# Phase 35 Number Language Follow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** Make "Number language" the only control over which voice reads a digit: a new "Follow document main language" value, the relabelled default "Follow current text language", one Unicode decimal digit set everywhere, the detector passing digits through, spelling following the number language, and the Unicode Detection "Ignore numbers" option removed.

**Architecture:** A stdlib-only module `numberLanguage.py` holds the two stored values (`FOLLOW = "default"`, `MAIN = "main"`); `pipeline/settings.py` holds their labels. The early number-language stage treats `MAIN` as a pass-through; a new late stage `wrap_numbers_for_detection` (after `number_wait_factor`) wraps every number for detection when detection is on and the value is not `FOLLOW`, so detection never needs a digit rule and the stage outputs before it are today's. `NUMBER_RE` and its neighbours use `\d`; the detector treats `isdecimal()` characters as the current language; `process_for_spelling` reads the number language through a new constructor provider.

**Tech Stack:** Python 3.14, pytest 9.1.1, Hypothesis 6.168.5, mutmut 3.8.0, coverage 7.16.2 + pytest-cov 7.1.0, ruff 0.16.3 via prek 0.4.14, GNU gettext (`msgfmt`).

**Spec:** `docs/superpowers/specs/2026-10-23-phase35-number-language-follow-design.md` (commit `7bc165d`). All "Decided by the user (2026-10-23)" items and the orchestrator defaults Q1–Q10 (§13) apply as written. Line numbers below refer to `da7f791`; `pipeline:<n>` = `addon/synthDrivers/WorldVoice/pipeline/__init__.py:<n>`, `detection:<n>` = `addon/synthDrivers/WorldVoice/languageDetection/__init__.py:<n>`, `synth:<n>` = `addon/synthDrivers/WorldVoice/__init__.py:<n>`.

## Global Constraints

- Stored values: `"default"` (label "Follow current text language", the default) and `"main"` ("Follow document main language"); locales unchanged. `availableNumlans` lists the two first, in that order, then `voiceManager.languages` (spec §4.1, §4.5).
- `_set_numlan` keeps `"default"`, `"main"` and any locale in `self._voiceManager.languages`; any other value is stored as `"default"` with one `nvdaLog.debugWarning` naming it. No migration; the old key is never read (spec §7.1, goals 2 and 4).
- Late stage: `Stage("number_language", wrap_numbers_for_detection, log_switch=False)` right after `number_wait_factor`, before `speech_viewer`; active only when `ctx.supports_roles and ctx.detects_language and ctx.number_language != FOLLOW`; target = language in force for `MAIN`, the stored locale otherwise; no dedupe. `LOG_SWITCHES` and the Log Record panel unchanged (spec §4.4).
- `SpeechContext.detects_language: bool = False`, placed after `number_language`; `speech_context()` sets it from `getattr(self, "_uwv", False)` (spec §4.4 item 3).
- Digit = Unicode Nd (`\d` without `re.ASCII`, `str.isdecimal()`); pieces keep their original characters; signs stay ASCII `+`/`-`, separators stay Latin-1 P/S (`numbers:11-13`); `１２．５` and `٣٫١٤` are two numbers each (spec §6, Q6).
- New strings, each with a `# Translators:` comment, in `pipeline/settings.py`; zh_TW `跟隨當前文字語言`, `跟隨文件主要語言`; delete the zh_TW entry `Ignore numbers when detecting text language` outright; keep `msgid "default"` (spec §9).
- Readmes and changelog exactly as spec §9 (Q8, Q9). `buildVars.py` is never touched (the user has an uncommitted edit in the main checkout).
- Never modify `addon/synthDrivers/WorldVoice/driver/<Engine>/driver/`, `driver/sonic/` or `languageDetection/script_data.py`. Engine drivers stay independently installable (no driver imports another driver's package; shared code only in core). Never add Neural back. ruff pinned `==0.16.3`.
- git: stage explicit paths only; `git diff --cached --stat` before each commit; messages in English, `<type>: <summary>` with a body that says why; no `Co-Authored-By`; every commit runs the prek hooks; if a hook rewrites files, restage and recommit; never `--no-verify`, never `git stash`, never push, never touch `/workspace/WorldVoice` (reading `ref/` through the symlink is fine); never stage `ref`. `docs/` is git-ignored: stage plan/spec files with `git add -f`.
- Full suite: `python3 -m pytest -q -p no:cacheprovider tests`, single process, under `<scratch>/guard.sh` (kills the run when MemAvailable < 3 GB). mutmut: `--max-children 3`, same guard, scratch clone only. `<scratch>` = `/tmp/claude-0/-workspace-WorldVoice/86e44456-cf89-4c4b-a7fa-4bbf201ed8c7/scratchpad/phase35-impl`.
- Baseline on `da7f791`: **2413 passed, 0 skipped, 0 warnings** (a DeprecationWarning is an error). Every count below is "passed, 0 skipped, 0 warnings".
- Each task ends with the §7 checks: full suite, `prek run --all-files` all Passed, `git diff --check master`, both protected-path commands print nothing.

## Review Focus

1. **An index command between Chinese text and a number under "Follow document main language"** (`["中", IndexCommand(1), "12"]`). The index must reach the main voice together with `12`, as it does today with ignore off. Task 1 row `index` of `MAIN_ROWS` (run under `"main"` from Task 4).
2. **Empty and blank text items around a number** (`["", "12", ""]`, `["", "12", " "]`) with detection before or after. No empty chunk, no stray switch, the number read once by the main voice. Task 1 row `empty`; Task 4 `test_wrap_numbers_for_detection_drops_empty_texts`.
3. **A number pause with a signed number under "main"** (`中 -12 34`, number wait 50). The pause stays between the two numbers and the sign moves with its number to the main voice. Task 4 `test_main_moves_a_sign_with_its_number[wait-*]`.
4. **A stored locale that the voice list no longer offers** (`zh_TW` after the languages become `("en",)`, e.g. after "Keep main locale engine consistent" hid it). Refused with one warning when NVDA loads it (Task 8 `test_a_locale_the_voices_no_longer_offer_is_refused_on_load`); hidden after it was stored, it reads as Follow without a setter call, so the ring finds it among the choices (batch 2 review M1, `test_a_locale_hidden_after_it_was_stored_reads_as_follow`).
5. **Arabic-Indic digits next to Latin letters, in detection and in spelling** (`abc ١٢٣`, `abc١٢`). They are not Common script; they must never switch to an Arabic voice or description locale. Task 5 `test_decimal_digits_never_switch_the_language[abc-arabic-indic]`; Task 7 `test_spelling_keeps_arabic_indic_digits_in_a_latin_run`.

---

### Task 1: Characterize today's number voices at speak level

**Files:**
- Test: `tests/test_worldvoice_speak.py`, `tests/test_pipeline_stages.py`

**Interfaces:**
- Consumes: `_synth(monkeypatch, *, timing, uwv)`, `IndexCommand`, `LangChangeCommand`, `pipeline_harness.symbol_name`, `pipeline_harness.load_pipeline_module`, `punctuation_settings`.
- Produces (in `tests/test_worldvoice_speak.py`):
  - `stage_settings(*, number_mode="value", punctuation=False, number_wait=0, group_size=3) -> SimpleNamespace` (fields as `pipeline_harness.punctuation_settings`, punctuation characters `".,"`, all other waits 0).
  - `heard(calls) -> list`: each `("speech", voice, chunks)` becomes `(voice, text)` with an `IndexCommand(i)` rendered `"[i]"`, consecutive entries of one voice joined; each break becomes `"|"`; `"submit"` dropped.
  - `speak_through_stages(monkeypatch, sequence, *, numlan, timing="after", uwv=True, main="en", settings=None, ignore=False) -> list`: builds `_synth`, sets `_numlan`, makes `main="zh"` the Chinese default voice (`language="zh_TW"`, voice `B:zh`), writes `ignoreNumbersInLanguageDetection = ignore`, points `speech.getCurrentLanguage` at the synth language and `characterProcessing.processSpeechSymbol` at `symbol_name`, runs every `STAGES` `fn` with `synth.speech_context()`, runs detection for `uwv and timing == "before"`, calls `synth.speak`, returns `heard(...)`.
  - Configs `MAIN = {"numlan": "default", "ignore": False}` and `FOLLOW = {"numlan": "default", "ignore": True}` (Task 4 changes `MAIN`, Tasks 5–6 change `FOLLOW`); tables `MAIN_ROWS`, `FOLLOW_ROWS`, `OFF_ROWS`, `LOCALE_ROWS` of `pytest.param(sequence, options, expected, id=...)`.

- [ ] **Step 1: Write the characterization tests.** `en`/`zh` = `"A:en"`/`"B:zh"`; `P = stage_settings(punctuation=True)`; `N = stage_settings(number_mode="number")`.

`test_main_language_numbers(monkeypatch, sequence, options, expected, timing)` over `MAIN_ROWS` × `timing in ("after", "before")` with `**MAIN`:

| id | sequence | options | expected |
|---|---|---|---|
| zh12 (T1/T2) | `["中12"]` | — | `[(zh,"中"), (en,"12")]` |
| zh-space-12 | `["中文 12"]` | — | `[(zh,"中文 "), (en,"12")]` |
| tagged-de (T5) | `[L("de_DE"), "abc 12 中"]` | — | `[(en,"abc 12 "), (zh,"中")]` |
| zh-main (T6) | `["abc 123 def"]` | `main="zh"` | `[(en,"abc "), (zh,"123 "), (en,"def")]` |
| number-mode (T8) | `["中12.5 ok"]` | `settings=N` | `[(zh,"中"), (en,"1"), "\|", (en,"2"), "\|", (en,"full stop en"), "\|", (en,"5 ok")]` |
| total | `["Total. 12"]` | `settings=P` | `[(en,"Total."), "\|", (en," 12")]` |
| next | `["中 12. Next"]` | `settings=P` | `[(zh,"中 "), (en,"12 ."), "\|", (en," Next")]` |
| index | `["中", IndexCommand(1), "12"]` | — | `[(zh,"中"), (en,"[1]12")]` |
| empty | `["", "12", ""]` | — | `[(en,"12")]` |

`test_follow_language_numbers` over `FOLLOW_ROWS` × both timings with `**FOLLOW`:

| id | sequence | options | expected |
|---|---|---|---|
| zh12 (T4) | `["中12"]` | — | `[(zh,"中12")]` |
| zh-space-12 | `["中文 12"]` | — | `[(zh,"中文 12")]` |
| total | `["Total. 12"]` | `settings=P` | `[(en,"Total."), "\|", (en," 12")]` |
| next | `["中 12. Next"]` | `settings=P` | `[(zh,"中 12 ."), "\|", (zh," "), (en,"Next")]` |
| number-mode | `["中12.5 ok"]` | `settings=N` | `[(zh,"中1"), "\|", (zh,"2"), "\|", (en,"full stop en"), "\|", (en,"5 ok")]` |

`test_numbers_without_detection(monkeypatch, numlan, sequence, options, expected)` over `OFF_ROWS`, `uwv=False`, timing "after" (T3):

| id | numlan | sequence | options | expected |
|---|---|---|---|---|
| default-zh12 | default | `["中12"]` | — | `[(en,"中12")]` |
| default-total | default | `["Total. 12"]` | `P` | `[(en,"Total."), "\|", (en," 12")]` |
| default-next | default | `["12. Next"]` | `P` | `[(en,"12 ."), "\|", (en," Next")]` |
| locale-zh12 | zh_TW | `["中12"]` | — | `[(en,"中"), (zh,"12")]` |
| locale-total | zh_TW | `["Total. 12"]` | `P` | `[(en,"Total. "), (zh,"12")]` |
| locale-next | zh_TW | `["12. Next"]` | `P` | `[(zh,"12"), (en,"."), "\|", (en," Next")]` |

`test_locale_numbers_with_detection` over `LOCALE_ROWS` × both timings, `numlan="zh_TW"`:

| id | sequence | options | expected |
|---|---|---|---|
| zh-main (T6, second trap) | `["abc 123 def"]` | `main="zh"` | `[(en,"abc "), (zh,"123 "), (en,"def")]` |
| en-main (T7) | `["abc 12"]` | — | `[(en,"abc "), (zh,"12")]` |

In `tests/test_pipeline_stages.py`, `test_other_synths_get_no_worldvoice_language_commands(monkeypatch, numlan)` for `numlan in ("default", "en")` (T9): run every `module.STAGES` `fn` over `["中12", "abc 1 2"]` with `SpeechContext(supports_roles=False, language=None, number_language=numlan)` and `punctuation_settings(0)`; assert no item is a `module.WVLangChangeCommand`.

- [ ] **Step 2: Run on the unchanged code**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_worldvoice_speak.py tests/test_pipeline_stages.py`
Expected: all green. These rows were recorded on `da7f791` (scratch probe `<scratch>/base_probe.txt`); if one differs, the baseline output wins: record a Ruling and pin the baseline value.

- [ ] **Step 3: §7 checks.** Expected **2453 passed** (+40).

- [ ] **Step 4: Commit** `tests/test_worldvoice_speak.py tests/test_pipeline_stages.py` — `test: characterize which voice reads numbers before phase 35`.

---

### Task 2: One decimal digit set in the pipeline (Option B, spec §6.2)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/numbers.py:19-26,79`
- Test: `tests/test_pipeline_filters.py`, `tests/test_worldvoice_speak.py`

**Interfaces:**
- Consumes: `speak_through_stages`, `FOLLOW` (Task 1).
- Produces: `NUMBER_RE`, `NUMBER_TOKEN_RE`, `THOUSANDS_RE` with `\d` in place of every `[0-9]` (lookbehinds included); `DIGITS` removed; `number_pieces` tests `token[-1].isdecimal()`. Signatures unchanged.

- [ ] **Step 1: Write the red tests** (`tests/test_pipeline_filters.py`):
  - `test_number_re_finds_whole_numbers`: replace the row `("１２", [])` and its "Digits are ASCII only" comment with `("１２", ["１２"])` under "# Digits are Unicode decimal digits (Nd)"; add `("٣٫١٤", ["٣", "١٤"])`, `("１２．５", ["１２", "５"])`, `("x²", [])`, `("10²", ["10"])`, `("①", [])`.
  - `test_thousands_separators_of_other_digits(env, text, expected)`: value mode, `remove_thousands_separators([text], ...)` → `[expected]` for `("１２,３４５", "１２３４５")`, `("١٢,٣٤٥", "١٢٣٤٥")`.
  - `test_group_and_number_modes_keep_the_original_digits(env, mode, size, text, expected)`: `("group", 3, "１２３４５", ["１２３", NB0, "４５"])`, `("number", 1, "٣٤", ["٣", NB0, "٤"])` via `shape(inject_number_mode(...))` with `GENERIC_CONTEXT`.
  - `SPLITS`: add `("１ ２", ["１", B40, "２"])`, `("١ ٢", ["١", B40, "٢"])`.
  - `tests/test_worldvoice_speak.py`: `test_full_width_digits_are_numbers(monkeypatch, timing)`: `speak_through_stages(..., ["中１２３"], numlan="en", ignore=True)` == `[(zh,"中"), (en,"１２３")]` (spec §3 last row).

- [ ] **Step 2: Run to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_filters.py tests/test_worldvoice_speak.py -k "number_re or thousands_separators_of or original_digits or splits or full_width"`
Expected: 11 failed (`１２`, `٣٫١٤`, `１２．５`, both thousands rows, both mode rows, both splits, both full-width timings: no match for non-ASCII digits), the `x²`, `10²`, `①` rows and the existing rows pass.

- [ ] **Step 3: Implement** the three regex changes, delete `DIGITS`, use `isdecimal()` in `number_pieces`; update the module comments ("digits" means Unicode decimal digits, decided by the user 2026-10-23). `tests/test_pipeline_structure.py` `MOVED` keeps `"DIGITS"` (it guards the package from re-adding it).

- [ ] **Step 4: Run green.** Same command: all passed. Full property file `tests/test_pipeline_pause_properties.py` still passes (its ASCII alphabets are widened in Task 10).

- [ ] **Step 5: §7 checks.** Expected **2466 passed** (+13).

- [ ] **Step 6: Commit** `addon/synthDrivers/WorldVoice/pipeline/numbers.py tests/test_pipeline_filters.py tests/test_worldvoice_speak.py` — `feat: treat every Unicode decimal digit as a digit in the number rules`.

---

### Task 3: The "main" value, its label and the choices (spec §4.1, §4.5)

**Files:**
- Create: `addon/synthDrivers/WorldVoice/numberLanguage.py`
- Modify: `addon/synthDrivers/WorldVoice/pipeline/settings.py:55-68,149-162`, `addon/synthDrivers/WorldVoice/pipeline/__init__.py:256-293,330`, `addon/synthDrivers/WorldVoice/__init__.py:47,177,455-459`
- Test: `tests/test_worldvoice_speak.py`, `tests/test_pipeline_filters.py`, `tests/test_pipeline_structure.py`, `tests/pipeline_harness.py`, `tests/test_worldvoice_lifecycle.py`

**Interfaces:**
- Consumes: —
- Produces:
  - `numberLanguage.py`: `FOLLOW = "default"`, `MAIN = "main"` (module docstring: the two stored number-language values; stdlib only, importable by the detector without the pipeline package).
  - `pipeline/settings.py`: `NUMBER_LANGUAGE_CHOICES: tuple[tuple[str, str], ...] = ((FOLLOW, _("Follow current text language")), (MAIN, _("Follow document main language")))` with the spec §9 Translators comments; the `number_language` spec entry defaults to `FOLLOW`.
  - `SynthDriver._get_availableNumlans()` → `NUMBER_LANGUAGE_CHOICES` first, then each locale; `__init__` sets `self._numlan = FOLLOW`.
  - `inject_number_language`: `ctx.number_language in (FOLLOW, MAIN)` → pass-through; `inject_number_mode` names symbols in the language in force for both; `iter_number_speech_segments_language` falls back to `current_lang` for both.
  - `tests/pipeline_harness.py::load_settings_module` loads `settings.py` inside an alias package so `from ..numberLanguage import FOLLOW, MAIN` resolves; `load_pipeline_module` also pops `synthDrivers.WorldVoice.numberLanguage`.

- [ ] **Step 1: Write the red tests**
  - `test_number_languages_list_every_voice_language_by_its_description` (existing, rewritten): `[(key, info.displayName) for key, info in numlans.items()] == [("default", "Follow current text language"), ("main", "Follow document main language"), ("en", "English"), ("zh_TW", "zh_TW")]`; keep the `_set_numlan("zh_TW")` part. The speak environment gets `NUMBER_LANGUAGE_CHOICES`, `FOLLOW`, `MAIN` from the loaded modules.
  - `test_symbol_names_follow_language_commands_with_main_number_language` (filters): as the `default` sibling with `roles_context(env.module, "zh_TW", "main")` → `[N("×","zh_TW"), N("×","de"), N("×","zh_TW")]`.
  - `test_main_number_language_passes_through_the_early_stage` (filters): `ctx(...)` with `number_language="main"`; `list(inject_number_language(items, ...)) == items` and every item `is` the input item, for `items = ["a1b2", WV("zh"), "3"]`.
  - `test_number_segments_with_main_wrap_in_the_current_language` (filters): `shape(iter_number_speech_segments_language("a1", "en", "main")) == ["a", ("lang","en"), "1", ("lang","en")]`.
  - `test_number_language_values_import_only_the_standard_library` (structure): same AST walk as the numbers test over `numberLanguage.py`, and `(module.FOLLOW, module.MAIN) == ("default", "main")` via `load_source`.

- [ ] **Step 2: Run to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_worldvoice_speak.py tests/test_pipeline_filters.py tests/test_pipeline_structure.py -k "number_languages_list or main_number_language or segments_with_main or number_language_values"`
Expected: 4 failed (choices lack the labels; symbols named for locale `main`; segments wrap in `main`; no `numberLanguage.py`), 1 passed (`passes_through_the_early_stage`: the dedupe already drops `<main>` wrappers, spec §4.2 — it pins the pass-through).

- [ ] **Step 3: Implement** the module, the choices, the harness loader change, the gates and the comment at `pipeline:284-288` (both values pass through: a `MAIN` wrapper names the language in force and the dedupe drops it). Add `FOLLOW` to the lifecycle construction environment (`tests/test_worldvoice_lifecycle.py` `_construction_environment`) and `NUMBER_LANGUAGE_CHOICES` to `pipeline_harness.load_synth`'s environment.

- [ ] **Step 4: Run green.** Same command: all passed; `tests/test_translator_comments.py` passes.

- [ ] **Step 5: §7 checks.** Expected **2470 passed** (+4).

- [ ] **Step 6: Commit** the new module, the three add-on files and the five test files — `feat: add the "Follow document main language" number language`.

---

### Task 4: The late number-language stage for detection (spec §4.4)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (new stage after `inject_number_language`; `STAGES`), `addon/synthDrivers/WorldVoice/pipeline/context.py:11-13`, `addon/synthDrivers/WorldVoice/__init__.py:347-360`
- Test: `tests/test_pipeline_stages.py`, `tests/pipeline_harness.py` (`ORDER`), `tests/test_pipeline_structure.py:111-124`, `tests/test_worldvoice_pipeline_settings.py:193-219`, `tests/test_worldvoice_speak.py`

**Interfaces:**
- Consumes: `FOLLOW`, `MAIN` (Task 3); `speak_through_stages`, `MAIN_ROWS` (Task 1).
- Produces: `wrap_numbers_for_detection(speechSequence: Iterable[SpeechCmd], settings: "PipelineSettings", ctx: SpeechContext) -> Iterator[SpeechCmd]`; `SpeechContext.detects_language: bool = False`; `ORDER` gains `"number_language"` between `"number_wait_factor"` and `"speech_viewer"`. Task 1's `MAIN` becomes `{"numlan": "main", "ignore": False}`; `_synth` also sets `synth._uwv = uwv`.

- [ ] **Step 1: Write the red tests.** `ctx_for(numlan, *, detects=True, roles=True)` = `SpeechContext(supports_roles=roles, language="en", number_language=numlan, detects_language=detects)`; `<x>` = `("lang", x)` in `shape`.
  - `test_wrap_numbers_for_detection_is_inactive[follow|detection-off|other-synth]`: `("default", True, True)`, `("main", False, True)`, `("en", True, False)` → output items are the input items (`is`), for `["a1", WV("zh"), "2"]`.
  - `test_wrap_numbers_for_detection_wraps_every_match[value|number|group]` (main, language en): `["a 12,5 b"]` → `["a ", <en>, "12,5", <en>, " b"]`; `["1", NB, "2"]` → `[<en>, "1", <en>, NB, <en>, "2", <en>]`; `["123", NB, "45"]` → `[<en>, "123", <en>, NB, <en>, "45", <en>]`.
  - `test_wrap_numbers_for_detection_uses_the_locale`: `ctx_for("zh_TW")`, `["a 1"]` → `["a ", <zh_TW>, "1", <en>]`.
  - `test_wrap_numbers_for_detection_tracks_language_commands` (main): `[L("de"), "1", L(None), "2", WV("ja"), "3"]` → `[<de>, <de>, "1", <de>, <None>, <en>, "2", <en>, <ja>, <ja>, "3", <ja>]`.
  - `test_wrap_numbers_for_detection_drops_empty_texts` (main): `["", "12", " "]` → `[<en>, "12", <en>, " "]` (Review Focus 2).
  - `test_number_language_switch_logs_both_number_language_stages`: as the number-mode sibling, switch `number_language` on, a WorldVoice context with `detects_language=True`, `number_language="main"` → writes `[("number_language","before"), ("number_language","after")] * 2`.
  - `test_stages_order_and_log_keys` / `test_log_switches_list_each_label_once_in_stage_order`: update `ORDER`; `LOG_SWITCH_ORDER` unchanged.
  - `test_other_synths_get_no_worldvoice_language_commands`: add `"main"`.
  - Structure: `SpeechContext` field list gains `"detects_language"` after `"number_language"`.
  - `test_speech_context_falls_back_while_the_synth_is_not_running`: with no `_uwv`, `context["detects_language"] is False`; after `synth._uwv = True`, `True`.
  - Speak: switch `MAIN`; `OFF_ROWS` gains `main-zh12` (`"main"`, `["中12"]` → `[(en,"中12")]`); `test_main_moves_a_sign_with_its_number` × both timings (spec §4.7 item 1, Q5), with `**MAIN`:
    - `sign`: `["中 -12"]` → `[(zh,"中 "), (en,"-12")]`
    - `wait`: `["中 -12 34"]`, `stage_settings(number_wait=50)` → `[(zh,"中 "), (en,"-12"), "|", (en,"34")]` (Review Focus 3)
    - `covid`: `["中 COVID-19 中"]`, `main="zh"` → `[(zh,"中 "), (en,"COVID"), (zh,"-19 中")]`

- [ ] **Step 2: Run to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_stages.py tests/test_pipeline_structure.py tests/test_worldvoice_pipeline_settings.py tests/test_worldvoice_speak.py`
Expected: failures for every new `wrap_numbers_for_detection` test (`AttributeError`/`TypeError: unexpected keyword 'detects_language'`), the order and field-list guards, the speech-context test and the six sign rows (today the `-` stays with the Chinese voice); the switched `MAIN_ROWS` pass (the old detector still sends digits to the base with ignore off).

- [ ] **Step 3: Implement** the stage (track `item.lang or ctx.language` at every `LangChangeCommand`/`WVLangChangeCommand`, starting from `ctx.language`; split text items with `_split_by(NUMBER_RE, item)`; yield `WVLangChangeCommand(target)`, the match, `WVLangChangeCommand(in force)`), the `STAGES` entry, the context field and `detects_language=bool(getattr(self, "_uwv", False))` in `speech_context()`. Fix the `Stage.log_switch` comment: the stage logs under the switch of another stage with the same log key.

- [ ] **Step 4: Run green.** Same command: all passed.

- [ ] **Step 5: §7 checks.** Expected **2488 passed** (+18).

- [ ] **Step 6: Commit** — `feat: wrap numbers for detection after the number stages` (body: why a late stage, spec §4.2–§4.4).

**Batch 1 ends here: stop and report.**

---

### Task 5: Detection passes decimal digits through (spec §6.3, goal 5)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/languageDetection/__init__.py:135-143`
- Test: `tests/test_language_detector.py`, `tests/test_worldvoice_speak.py`

**Interfaces:**
- Consumes: `detect(env, sequence, *, languages, base, **preferences)`, `speak_through_stages`, `FOLLOW`, `MAIN`.
- Produces: `_language_for_character`: `character.isdecimal()` → `current_language`; no read of `settings.ignore_numbers`. `FOLLOW` becomes `{"numlan": "default"}`.

- [ ] **Step 1: Write the red tests and update the pins**
  - Characterization: row `digits-to-base` becomes `digits-follow` → `[("lang","zh_TW"), "中12"]`; delete row `digits-ignored` (now identical).
  - `test_unavailable_language_does_not_cover_its_script`: row `digits-ignored` drops its `ignore_numbers` preference (same expectation); row `digits-return-to-it` becomes `digits-stay-in-the-run`: `[L("de_DE"), "hallo 12"]` → `[("lang","de_DE"), ("lang","en"), "hallo 12"]`.
  - `test_digits_follow_the_ignore_numbers_setting` → `test_digits_follow_the_current_language_whatever_is_stored[stored-off|stored-on]`: stored key `False`/`True` → `[("lang","zh"), "中1"]`.
  - `test_decimal_digits_never_switch_the_language` (languages en_US, zh_TW, ar; base en_US): `abc-arabic-indic` `["abc ١٢٣"]` → `["abc ١٢٣"]` (Review Focus 5); `arabic-arabic-indic` `["مرحبا ١٢٣"]` → `[("lang","ar"), "مرحبا ١٢٣"]`; `han-full-width` `["中１２３"]` → `[("lang","zh"), "中１２３"]`.
  - `test_superscripts_are_not_digits`: `["中²"]` → `[("lang","zh"), "中²"]`.
  - `test_one_settings_read_per_sequence`: drop the `ignoreNumbersInLanguageDetection = True` line (same expectation).
  - Speak: `FOLLOW = {"numlan": "default"}`; `test_full_width_digits_are_numbers` drops `ignore=True`; `test_main_keeps_superscripts_in_the_text` × both timings: `["中²"]` with `**MAIN` → `[(zh,"中²")]` (spec §4.7 item 2).

- [ ] **Step 2: Run to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_language_detector.py tests/test_worldvoice_speak.py`
Expected: failed — `digits-follow`, `digits-stay-in-the-run`, `stored-off`, `arabic-arabic-indic`, `han-full-width`, `test_superscripts_are_not_digits`, the 8 `FOLLOW_ROWS` with Chinese digits (default no longer sends them to the base) and both superscript rows; `abc-arabic-indic`, `MAIN_ROWS`, sign rows and `total` rows pass.

- [ ] **Step 3: Implement** the `isdecimal()` branch (keep it: Arabic-Indic, Devanagari and other Nd digits are not Common script, spec F4) and drop the `ignore_numbers` read.

- [ ] **Step 4: Run green.** Same command: all passed; `MAIN_ROWS` still green under `"main"`.

- [ ] **Step 5: §7 checks.** Expected **2493 passed** (+5).

- [ ] **Step 6: Commit** — `feat: let decimal digits follow the detected language`.

---

### Task 6: Remove the "Ignore numbers" setting and checkbox (spec §7.2, goal 2)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/languageDetection/settings.py:15-21,28,36,62,72,84-86`, `addon/globalPlugins/WorldVoice/speechSettingsDialog.py:505-511,561`
- Test: `tests/test_detection_settings.py`, `tests/test_unicode_panel.py`, `tests/test_driver_ui_hooks.py:87`, `tests/test_language_detector.py:36-41,496,558`, `tests/test_worldvoice_speak.py`, `tests/test_hygiene_guards.py`

**Interfaces:**
- Consumes: —
- Produces: `DETECTION_CONFSPEC` with four keys; `DetectionSettings(script_language, timing)`; `DetectionSettingsService.update(*, script_language=None, timing=None)`. `speak_through_stages` loses `ignore`.

- [ ] **Step 1: Write the red tests and update the expectations**
  - `test_detection_settings.py`: fixture and shared-service conf without the key; `test_get_reads_the_four_detection_keys`; update/listener tests without `ignore_numbers` (writes `["CJKCharactersLanguage"]`; changed `frozenset({"script_language"})`); confspec four keys; new `test_update_rejects_ignore_numbers` (`pytest.raises(TypeError)`, `env.section.writes == []`); new `test_get_reads_a_section_that_still_holds_the_old_key` (section with `ignoreNumbersInLanguageDetection=True` → `get()` succeeds, fields as stored); new `test_settings_have_no_ignore_numbers_field` (`[f.name for f in dataclasses.fields(module.DetectionSettings)] == ["script_language", "timing"]`).
  - `test_unicode_panel.py`: fixture without the key; labels `["Language assumed for latin characters:", "Language assumed for CJK characters:", "Language assumed for arabic characters:", "Language detection timing:"]`; indices shift down by one; the save test checks only the three languages.
  - `test_driver_ui_hooks.py`: `frozenset({"script_language"})`.
  - `test_language_detector.py`: drop the `ignore_numbers` preference key, the drawn preference and the plain-scenario entry; `is_letter` uses `isdecimal()`.
  - `tests/test_hygiene_guards.py::test_the_ignore_numbers_option_is_gone`: `ignoreNumbersInLanguageDetection` appears in no `_addon_sources()` file and in none of `readme.md`, `addon/doc/*/readme.md`.
  - Speak harness: remove `ignore` and the config write.

- [ ] **Step 2: Run to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_detection_settings.py tests/test_unicode_panel.py tests/test_hygiene_guards.py`
Expected: failed — the reads/writes/confspec tests (the key and field still exist), `test_update_rejects_ignore_numbers` (no TypeError), the field test, the panel labels and the guard; `test_get_reads_a_section_that_still_holds_the_old_key` passes.

- [ ] **Step 3: Implement** the removal in the settings service and the panel (focus then starts on "Language assumed for latin characters:").

- [ ] **Step 4: Run green.** Full suite green.

- [ ] **Step 5: §7 checks.** Expected **2497 passed** (+4).

- [ ] **Step 6: Commit** — `feat: remove the ignore numbers detection option`.

---

### Task 7: Spelling follows the number language (spec §5)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/languageDetection/__init__.py:104-108,172-199`, `addon/synthDrivers/WorldVoice/__init__.py:261-265`
- Test: `tests/test_language_detector.py`, `tests/test_worldvoice_lifecycle.py:87-95`

**Interfaces:**
- Consumes: `FOLLOW`, `MAIN` (Task 3).
- Produces: `LanguageDetector(availableLanguages, *, settings, language, number_language: Callable[[], str] = <always FOLLOW>)`; `process_for_spelling` reads `number_language()` once per call; a decimal digit's target is: `FOLLOW` → the current language; `MAIN` → the spelling locale; a locale `L` → `L` when `get_primary_language(L) in availableLanguages`, else the spelling locale (Q10). Whitespace keeps the spelling locale. The synth passes `number_language=lambda: self._numlan`. `make_detector(env, languages=..., number_language=None)` in the tests.

- [ ] **Step 1: Write the red tests** (languages `en_US`, `zh_TW`; locale `en_US` unless noted)
  - `test_spelling_digits_follow_the_number_language[default|main|en]`: `"中1"` → `[("中1","zh")]`, `[("中","zh"),("1","en_US")]`, `[("中","zh"),("1","en")]`.
  - `test_spelling_keeps_one_run_for_a_number_language_of_the_same_primary`: numlan `zh_TW` → `[("中1","zh")]`.
  - `test_spelling_uses_the_locale_for_a_number_language_without_a_voice`: numlan `fr` → `[("中","zh"),("1","en_US")]`.
  - `test_spelling_reads_the_number_language_once_per_call`: counting provider, `"1a2b3"` → `reads == 1`.
  - `test_spelling_keeps_arabic_indic_digits_in_a_latin_run[default|main]` (languages en_US, ar): `"abc١٢"` → `[("abc١٢","en_US")]` (Review Focus 5).
  - Lifecycle: the stub `LanguageDetector` accepts `{"settings", "language", "number_language"}` and records the provider; `test_the_detector_reads_the_drivers_number_language`: after construction, `driver._numlan = "main"` → the recorded provider returns `"main"`.
  - Unchanged and still green: `test_spelling_without_locale_uses_the_synth_language`, `test_spelling_with_locale`, `test_spelling_with_an_unavailable_locale`.

- [ ] **Step 2: Run to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_language_detector.py tests/test_worldvoice_lifecycle.py`
Expected: failed — `TypeError: unexpected keyword 'number_language'` for the provider tests, `default` (digit goes to the locale today), the lifecycle tests; `test_spelling_keeps_arabic_indic_digits_in_a_latin_run` passes before (pins the `isdecimal` branch).

- [ ] **Step 3: Implement** the provider and the digit rule (one private helper `_spelling_language_for_digit(number_language, current_language, default_language) -> str`).

- [ ] **Step 4: Run green.** Same command: all passed.

- [ ] **Step 5: §7 checks.** Expected **2505 passed** (+8).

- [ ] **Step 6: Commit** — `feat: spell digits in the number language`.

---

### Task 8: Refuse an unknown stored number language (spec §7.1, Q7)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/__init__.py:464-465`
- Test: `tests/test_worldvoice_speak.py`

**Interfaces:**
- Consumes: `FOLLOW`, `MAIN`; the speak environment gets `nvdaLog` with a recording `debugWarning`.
- Produces: `_set_numlan(self, value)` as in Global Constraints; the warning text `"WorldVoice: unknown number language %r, using %r"` with `(value, FOLLOW)`.

- [ ] **Step 1: Write the red tests**
  - `test_an_unknown_number_language_reads_as_follow[zz|fr]`: `_set_numlan(value)` → `_get_numlan() == "default"`, `speech_context().number_language == "default"`, exactly one warning whose arguments contain `value`.
  - `test_known_number_languages_are_kept[default|main|en|zh_TW]`: stored as given, no warning.
  - `test_a_locale_the_voices_no_longer_offer_reads_as_follow`: `synth._voiceManager.languages = ("en",)`; `_set_numlan("zh_TW")` → `"default"`, one warning; `"default"` is a key of `_get_availableNumlans()`, so NVDA's ring finds the value (Review Focus 4).

- [ ] **Step 2: Run to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_worldvoice_speak.py -k "reads_as_follow or are_kept"`
Expected: 3 failed (`zz`, `fr`, hidden locale: stored as given), 4 passed.

- [ ] **Step 3: Implement** the check.

- [ ] **Step 4: Run green.** Same command: all passed.

- [ ] **Step 5: §7 checks.** Expected **2512 passed** (+7).

- [ ] **Step 6: Commit** — `fix: read an unknown stored number language as follow`.

**Batch 2 ends here: stop and report.**

---

### Task 9: Translations, readmes and changelog (spec §9, Q8, Q9)

**Files:**
- Modify: `addon/locale/zh_TW/LC_MESSAGES/nvda.po`, `readme.md:43,55,57,67-`, `addon/doc/zh_TW/readme.md:43,55,57,65-`, `addon/doc/zh_HK/readme.md:53,55`, `addon/doc/zh_CN/readme.md:54,56`, `addon/doc/ru/readme.md:54,56`, `addon/doc/uk/readme.md:54,56`

**Interfaces:**
- Consumes: the two msgids of Task 3.
- Produces: documentation only.

- [ ] **Step 1: zh_TW catalog.** Add two entries next to the number-mode entries, each with its `#.` Translators comment and `#:` reference to `addon\synthDrivers\WorldVoice\pipeline\settings.py`: `msgid "Follow current text language"` / `msgstr "跟隨當前文字語言"`, `msgid "Follow document main language"` / `msgstr "跟隨文件主要語言"`. Delete the `Ignore numbers when detecting text language` entry (comment, reference, msgid, msgstr). Keep `msgid "default"`.

- [ ] **Step 2: Check the catalog**

Run: `msgfmt --check -o /dev/null addon/locale/zh_TW/LC_MESSAGES/nvda.po && grep -c "Ignore numbers when detecting" addon/locale/zh_TW/LC_MESSAGES/nvda.po`
Expected: no msgfmt output; count `0`.

- [ ] **Step 3: Readmes.** Delete the ignore bullet and replace the intro in all six (spec §9 texts verbatim); rewrite the number-language bullet in `readme.md` and `addon/doc/zh_TW/readme.md` (spec §9 texts; keep each file's list indentation: two spaces in English, one in zh_TW); add the "## Next update" / 「## 下一版更新」 section with the two bullets as the first section under "# WorldVoice Changelog" / 「# WorldVoice 更新日誌」.

- [ ] **Step 4: Check the docs**

Run: `grep -rn "Ignore numbers\|忽略數字\|忽略数字\|Игнорировать числа\|Ігнорувати числа" readme.md addon/doc/*/readme.md`
Expected: only the new changelog bullets in `readme.md` and `addon/doc/zh_TW/readme.md` (which name the removed option).

- [ ] **Step 5: §7 checks.** Expected **2512 passed** (unchanged).

- [ ] **Step 6: Commit** the catalog and six readmes — `docs: describe the number language choices and drop the ignore option`.

---

### Task 10: Pipeline properties over Unicode digits (spec §11.4 items 1–3)

**Files:**
- Test: `tests/test_pipeline_pause_properties.py`

**Interfaces:**
- Consumes: `NUMBER_RE`, `inject_number_mode`, `remove_thousands_separators`.
- Produces: `OTHER_DIGITS = "１２٣٤۵۶१२"` (full-width, Arabic-Indic, Extended Arabic-Indic, Devanagari) and `NOT_DIGITS = "²①٫"` alphabet parts.

- [ ] **Step 1: Write the properties**
  - `NUMBER_TEXT`'s alphabet gains `OTHER_DIGITS + NOT_DIGITS`; `DIGITS` and the scanner use `isdecimal()`; the two digit-run strategies of the group/digit-mode properties draw from `"0123456789" + OTHER_DIGITS`; `test_property_no_digit_run_is_longer_than_the_size` uses `\d+`; the `before[-1] in DIGITS` checks use `isdecimal()`.
  - `test_property_every_decimal_digit_is_inside_a_number(text)`: every index `i` with `text[i].isdecimal()` lies in a match span; no character of a match is in `NOT_DIGITS`, a letter or whitespace.
  - `test_property_pieces_keep_their_digits(text, mode_size)`: `[c for item in result if str for c in item if c.isdecimal()] == [c for c in text if c.isdecimal()]`.
  - Thousands: `WHOLE_THOUSANDS_RUN` and the oracle's run pattern use `\d`; alphabet `"0123456789١٢٣,.a -"`.

- [ ] **Step 2: Run**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_pause_properties.py`
Expected: all passed. Then check one property is live: in a scratch copy, set `NUMBER_RE` back to `[0-9]`; `test_property_every_decimal_digit_is_inside_a_number` fails.

- [ ] **Step 3: §7 checks.** Expected **2514 passed** (+2).

- [ ] **Step 4: Commit** — `test: draw Unicode digits in the number properties`.

---

### Task 11: Detector, spelling and end-to-end properties (spec §11.4 items 4–6)

**Files:**
- Test: `tests/test_language_detector.py`, `tests/test_worldvoice_speak.py`

**Interfaces:**
- Consumes: `scenarios()`, `ITEMS`, `TEXTS`, `make_detector(..., number_language=...)` (Task 7); `speak_through_stages` (Task 1).
- Produces: —

- [ ] **Step 1: Write the properties**
  - `SCRIPT_SAMPLES` gains `"١٢"`, `"１２"`, `"²"`, `"①"`.
  - `test_property_digits_never_start_a_detected_run(env, scenario, items)`: every inserted `WVLangChangeCommand` that is directly followed by a text item is followed by one whose first character is not decimal.
  - `test_property_spelling_digits_carry_the_number_language(env, scenario, text, number_language)` with `number_language` from `("default", "main", "en", "zh_TW", "fr")`: for each run holding a decimal digit, `default` → the run does not start with that digit unless it is the first run; `main` → primary of the run equals primary of the spelling base; a locale `L` with an installed primary → primary equals `primary(L)`, else primary of the base.
  - `test_property_each_digit_is_read_by_the_number_language_voice(monkeypatch, timing, data)` (`deadline=None`, `max_examples=50`, each example in `monkeypatch.context()`): text from `["abc", "中文", "12", "٣", "１", " "]` joined (no signs), `main` from `("en", "zh")`, numlan from `("default", "main", "en", "zh_TW")`; from the recorded calls give each character its voice; for each decimal digit: `default` → the voice of the nearest preceding letter, or the main voice when none; `main` → the main voice; `en`/`zh_TW` → `A:en`/`B:zh`.

- [ ] **Step 2: Run**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_language_detector.py tests/test_worldvoice_speak.py`
Expected: all passed. Liveness check in a scratch copy: remove the late stage from `STAGES`; the end-to-end property fails for `main` (Chinese digits follow the text).

- [ ] **Step 3: §7 checks.** Expected **2518 passed** (+4).

- [ ] **Step 4: Commit** — `test: add digit properties for detection, spelling and speech`.

---

### Task 12: Mutation testing, coverage, final verification

**Files:**
- Test: as the survivors require (`tests/test_pipeline_filters.py`, `tests/test_pipeline_stages.py`, `tests/test_language_detector.py`)
- Modify: this plan (append "Implementation notes: mutmut and coverage")

**Interfaces:**
- Consumes: everything above.
- Produces: —

- [ ] **Step 1: Run mutmut** in a scratch `git clone --shared` of the branch head with `ref` symlinked, under the guard: `mutmut run --max-children 3 "addon.synthDrivers.WorldVoice.pipeline.numbers.*" "addon.synthDrivers.WorldVoice.pipeline.x_wrap_numbers_for_detection*" "addon.synthDrivers.WorldVoice.pipeline.x_inject_number_language*" "addon.synthDrivers.WorldVoice.pipeline.x_inject_number_mode*" "addon.synthDrivers.WorldVoice.pipeline.x_iter_number_speech_segments_language*" "addon.synthDrivers.WorldVoice.languageDetection.*"`.
Expected: clean and stats runs pass with the DeprecationWarning filter; no timeout or "suspicious".

- [ ] **Step 2: Kill or explain each survivor.** A non-equivalent survivor gets a test that fails with the mutant applied in the scratch copy and passes without it. Expected equivalents: the `NUMBER_RE` sign lookbehind (`numbers:16-18`); the `THOUSANDS_RE` `\d` lookbehind if the oracle cannot tell it apart; the phase 33 equivalents in the detector.

- [ ] **Step 3: Coverage**

Run: `python3 -m pytest -q -p no:cacheprovider --cov=addon/synthDrivers/WorldVoice --cov=addon/globalPlugins/WorldVoice --cov-report=term-missing tests`
Expected: every line of `numberLanguage.py`, `pipeline/numbers.py`, `wrap_numbers_for_detection`, `_set_numlan`, `_spelling_language_for_digit` and `languageDetection/settings.py` covered.

- [ ] **Step 4: Record** counts, survivors with reasons, lowest MemAvailable and the coverage figures at the end of this plan; commit it with any new tests — `test: kill the phase 35 mutants` (or `docs:` when no test changed).

- [ ] **Step 5: Final §7 checks** plus `msgfmt --check`. Expected **2518 passed** plus any mutant-killing tests.

- [ ] **Step 6: Report** to the orchestrator: commits, counts, prek, diff-check, protected paths, msgfmt, coverage, mutmut survivors with reasons, all Rulings, spec contradictions; Windows/NVDA manual items M1–M7 (spec §11.7) not verified.

## Implementation notes: mutmut and coverage

mutmut 3.8.0 on 2026-10-23, scratch `git clone --shared` of `06efbe1` with `ref` symlinked, `--max-children 3`, memory guard (lowest MemAvailable 5.7 GB). The functions are those the phase touched after the batch reviews (Ruling in the ledger: the late stage became `detect_with_number_language`/`wrap_numbers_for_detection`, and U2 touched the early wrapper): `pipeline.numbers.*`, `pipeline.x_wrap_numbers_for_detection*`, `x_detect_with_number_language*`, `x__split_numbers_for_language*`, `x_iter_number_speech_segments_language*`, `x_inject_number_language*`, `x__insert_WVLangChangeCommand_between_number*`, `x_inject_number_mode*`, `languageDetection.*`. The clean and stats runs passed with the `error::DeprecationWarning` filter. No timeout, no "suspicious".

407 mutants, 381 killed, 26 survived, all equivalent:

- `_split_numbers_for_language__mutmut_8` and `numbers.number_pieces__mutmut_21` (`"+-"` → `"XX+-XX"`): the tested character is the first of a match, which is a sign or a digit, never an `X`.
- `_split_numbers_for_language__mutmut_20`, `_21` (the `"number"` label renamed): callers test only `kind == "text"`.
- `iter_number_speech_segments_language__mutmut_4` (`number_re` not passed on): every caller uses the default, `NUMBER_RE`.
- `detect_with_number_language__mutmut_26`, `_45` (`glue = None`): falsy like `False`; `_27` (initial `glue = True`): the first item has nothing before it to join to.
- The 18 detector survivors of phase 33, unchanged and equivalent for the reasons recorded there: `get_primary_language__mutmut_5`, `_14` (split limit), `_covers__mutmut_6`, `_8` and `find_language_for_script__mutmut_3`, `_5` (`.get(script, ())` default), `_language_for_character__mutmut_5`–`_10` and `process_for_spelling__mutmut_21`–`_26` (the `"Common"`/`"Inherited"` fast path).

New code with no survivor: `wrap_numbers_for_detection` (29 killed), `_spelling_language_for_digit` (5), `_insert_WVLangChangeCommand_between_number` (20), `inject_number_language` (6), `inject_number_mode` (37). The module-level regexes of `pipeline/numbers.py` are not mutated by mutmut (module code), so the spec's expected `NUMBER_RE` lookbehind survivor does not occur; the `THOUSANDS_RE` lookarounds were checked by hand (batch 1 review M1).

Coverage (`pytest --cov`, 2588 passed): `numberLanguage.py`, `pipeline/numbers.py`, `pipeline/__init__.py`, `languageDetection/__init__.py` and `languageDetection/settings.py` 100% lines and branches; `__init__.py` (synth) 96% with every new line (`_detect_languages`, `_is_number_language`, `_get_numlan`, `_set_numlan`, `speech_context`) covered; `speechSettingsDialog.py` 99% (the Unicode Detection panel fully covered).
