# Script Digits Follow Their Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** Under number language "Follow surrounding text language", a decimal digit with its own Unicode script (Devanagari, Arabic-Indic, …) goes to that script's language like a letter, in detection and in spelling.

**Architecture:** One core module changes: `languageDetection/detector.py`. The detector reads its existing `number_language` provider once per sequence; only `FOLLOW` sends digits through `find_language_for_script`. `MAIN` and locales keep today's rule, because the pipeline wraps their digits before detection.

**Tech Stack:** Python 3 (NVDA add-on), pytest, Hypothesis, mutmut 3.8, ruff 0.16.3 via prek.

**Spec:** `docs/superpowers/specs/2026-11-07-fix-script-digit-language-design.md`

## Global Constraints

- Only number language `FOLLOW` (`"default"`) changes; `MAIN` (`"main"`) and locales keep digits in the current run (spec §2.3).
- Common/Inherited/unknown-script digits (ASCII, full-width) never change behaviour.
- Mixed `1२3` stays per character (spec G2).
- The number language is read once per `add_detected_language_commands` call (spec D1).
- Docs: only `addon/doc/zh_TW/readme.md`; no root readme, no other language readme or `.po`. No new UI strings.
- Never edit `addon/synthDrivers/WorldVoice/driver/*/driver/*`, `driver/sonic/`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py`. Engine drivers stay independently installable. Never add Neural. Never stage `ref`.
- ruff pinned `==0.16.3`; commits run prek hooks; if a hook edits files, stage and re-commit, never `--no-verify`.
- git: stage explicit paths (new files under `docs/` need `git add -f`); check `git diff --cached --stat`; commit format `<type>: <summary>` + body explaining why; no `Co-Authored-By`; no push; no `git stash`.
- Tests: at most 3 parallel workers; run under the memory guard (stop pytest when MemAvailable < 3 GB).
- Baseline: 3769 passed, 0 skipped.

## Review Focus

1. A non-text command between two script digits (`["२", marker, "०"]`): one language change, before `२`, none before `०` — Task 1 `test_script_digits_go_to_their_scripts_language[other-command-between]`.
2. A script digit item right after an item of the same script (`["नेपाल", "२०८१"]`): no second command — Task 1 `[after-nepali-item]`.
3. Whitespace between script digits in spelling (`"२ ३"`): the space still goes to the spelling locale, each digit to `ne` — Task 2 `test_spelling_script_digits[space-between]`.
4. A stored locale that no offered voice speaks (spoken value `FOLLOW`): script digits follow their script — Task 3 `test_a_hidden_number_language_reads_script_digits_as_follow`.
5. Digit mode under `FOLLOW` with Devanagari digits (`५.५`): digits Nepali, the English symbol name English (known limitation pinned, spec §2.3) — Task 3 `test_digit_mode_names_the_symbol_before_detection`.

---

### Task 1: Detection gives script digits to their script's language under FOLLOW

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/languageDetection/detector.py:14-83`
- Test: `tests/test_language_detector.py` (409-422, 563-728)

**Interfaces:**
- Consumes: `LanguageDetector.find_language_for_script(script, current_language, settings=None, base_language=None)`, `get_script`, `FOLLOW`.
- Produces: `LanguageDetector._script_language(self, character: str, current_language: str, base_language: str | None, settings) -> str` (used by Task 2); `_language_for_character(self, character, current_language, base_language, settings, digits_by_script: bool) -> str`.

- [ ] **Step 1: Update the changed expectation and write the failing unit tests**

In `tests/test_language_detector.py`:
- Rename `test_decimal_digits_never_switch_the_language` to `test_decimal_digits_follow_the_letter_rule_of_their_script`; case `abc-arabic-indic` expects `["abc ", ("lang", "ar"), "١٢٣"]`; rewrite the comment above it: digits with a script follow the letter rule under "Follow surrounding text language" (spec `fix/script-digit-language` G1, superseding phase 35 §6.3).
- Add (use the existing `detect(env, sequence, languages=..., base=..., **preferences)` and `make_detector` helpers; `NE = ("en_US", "ne_NP")`; `MARKER = object()` at module level):

```python
@pytest.mark.parametrize(("sequence", "expected"), [
	(["२०८१ साल"], [("lang", "ne"), "२०८१ साल"]),                       # id year-then-word
	(["२०८१"], [("lang", "ne"), "२०८१"]),                               # year-alone
	(["link", "२०८१"], ["link", ("lang", "ne"), "२०८१"]),               # after-english-item
	(["२०८१ link"], [("lang", "ne"), "२०८१ ", ("lang", "en_US"), "link"]),  # back-to-english
	(["नेपालमा ५० जिल्ला"], [("lang", "ne"), "नेपालमा ५० जिल्ला"]),        # nepali-text
	(["abc 123"], ["abc 123"]),                                         # ascii
	(["abc １２３"], ["abc １２３"]),                                     # full-width
	(["1२3"], ["1", ("lang", "ne"), "२3"]),                             # mixed
	([L("ne_NP"), "२०८१"], [("lang", "ne_NP"), "२०८१"]),                 # covering-document-language
	(["नेपाल", "२०८१"], [("lang", "ne"), "नेपाल", "२०८१"]),               # after-nepali-item
	(["२", MARKER, "०"], [("lang", "ne"), "२", MARKER, "०"]),            # other-command-between
], ids=[...])
def test_script_digits_go_to_their_scripts_language(env, sequence, expected):
	assert detect(env, sequence, languages=NE, base="en_US") == expected

def test_script_digits_without_a_voice_for_their_script_stay(env):
	assert detect(env, ["२०८१"], languages=("en_US", "zh_TW"), base="en_US") == ["२०८१"]

@pytest.mark.parametrize(("number_language", "sequence"), [
	("main", [WV("en_US"), "२०८१", WV("en_US")]),
	("en_US", [WV("en_US"), "२०८१", WV("en_US")]),
	("main", ["२०८१"]),
], ids=["main-wrapped", "locale-wrapped", "main-unwrapped"])
def test_other_number_languages_keep_digits_in_the_current_run(env, number_language, sequence):
	# WV = env.WV; no "ne" language command is added.
	env.state.language = "en_US"
	result = shape(env, make_detector(env, NE, number_language).add_detected_language_commands(sequence))
	assert ("lang", "ne") not in result and "".join(i for i in result if isinstance(i, str)) == "२०८१"

@pytest.mark.parametrize("assumed", ["ne", "hi"])
def test_the_devanagari_assumed_language_picks_the_digit_language(env, assumed):
	assert detect(env, ["२०८१"], languages=("en_US", "hi_IN", "ne_NP"), base="en_US",
		devanagari=assumed) == [("lang", assumed), "२०८१"]

def test_a_script_digit_prefers_a_covering_base_language(env):
	assert detect(env, [L("hi_IN"), "abc २"], languages=("en_US", "hi_IN", "ne_NP"), base="en_US",
		devanagari="ne") == [("lang", "hi_IN"), ("lang", "en"), "abc ", ("lang", "hi_IN"), "२"]

def test_detection_reads_the_number_language_once_per_sequence(env):
	reads = []
	detector = env.module.LanguageDetector(list(NE), settings=env.settings,
		language=lambda: env.state.language, number_language=lambda: reads.append(1) or "default")
	list(detector.add_detected_language_commands(["१ a २", "३"]))
	assert reads == [1]
```

The `("lang", "en")` in the base test is the Latin assumed language's value; if the stub's default differs, take the value the Latin preference yields and record a `Ruling:`.

- [ ] **Step 2: Update the detection properties (spec §7.3)**

- `SCRIPT_SAMPLES` gains `"२०"`; `VOICES` gains `"ne_NP"`; the scenario's `"devanagari"` draw becomes `st.sampled_from(["hi", "mr", "ne"])`.
- Rename `is_letter` to `has_script(env, character) -> bool`: script not in `(None, "Common", "Inherited")`, decimal digits included; update `spoken_letters` to use it.
- Replace `test_property_digits_never_start_a_detected_run` with:
  - `test_property_only_script_digits_start_a_detected_run(env, scenario, items)` (FOLLOW): for an inserted command followed by text whose first character `c` is decimal: `has_script(env, c)` and `covers(env, scenario, command.lang, get_script(ord(c)))`.
  - `test_property_digits_never_start_a_detected_run_under_other_number_languages(env, scenario, items, number_language)` with `number_language` from `("main", "en", "zh_TW", "fr")` set as `detector._number_language = lambda: number_language`: no inserted command is directly followed by text starting with a decimal digit.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python3 -m pytest -q tests/test_language_detector.py -p no:cacheprovider`
Expected: FAIL — at least these 11 deterministic failures: `abc-arabic-indic`, the 6 cases year-then-word, year-alone, after-english-item, back-to-english, mixed, other-command-between, both assumed-language cases, the base-language test, the read-once test (`reads == []`). The updated properties may also fail.

- [ ] **Step 4: Implement in `detector.py`**

- `_script_language(self, character, current_language, base_language, settings) -> str`: the letter part of today's `_language_for_character` (lines 53-56).
- `_language_for_character(self, character, current_language, base_language, settings, digits_by_script)`: decimal and not `digits_by_script` → current language; else `_script_language(...)`. Rewrite the comment: other number languages wrap digits before detection (`pipeline/numberStages.py` `detect_with_number_language`), so only `FOLLOW` reads a digit's script.
- `add_detected_language_commands`: `digits_by_script = self._number_language() == FOLLOW` next to the settings read; pass it at the call.
- Constructor docstring: `number_language` returns the number language speech uses (the driver's spoken value), which digits follow in detection and spelling.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest -q tests/test_language_detector.py -p no:cacheprovider` → all pass except `test_spelling_keeps_arabic_indic_digits_in_a_latin_run[default]` and `test_property_spelling_digits_carry_the_number_language`, which Task 2 changes — they must still pass here (spelling untouched); if either fails, stop and investigate.
Full suite under the guard: `python3 -m pytest -q tests` → **3789 passed, 0 skipped** (3769 + 19 new unit cases + 1 property).

- [ ] **Step 6: Commit**

```bash
git add addon/synthDrivers/WorldVoice/languageDetection/detector.py tests/test_language_detector.py
git commit   # "fix: give script digits their script's language when numbers follow the text"
```

### Task 2: Spelling uses the same rule under FOLLOW

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/languageDetection/detector.py:85-128`
- Test: `tests/test_language_detector.py` (474-477, 732-752)

**Interfaces:**
- Consumes: `_script_language` (Task 1).
- Produces: `_spelling_language_for_digit(self, number_language: str, default_language: str) -> str` (FOLLOW branch and `current_language` removed).

- [ ] **Step 1: Write the failing tests**

- Rename `test_spelling_keeps_arabic_indic_digits_in_a_latin_run` to `test_spelling_arabic_indic_digits_follow_the_number_language`, parametrized `("default", [("abc", "en_US"), ("١٢", "ar")])`, `("main", [("abc١٢", "en_US")])`.
- Add:

```python
@pytest.mark.parametrize(("number_language", "text", "expected"), [
	("default", "२", [("२", "ne")]),                                # alone
	("main", "२", [("२", "en_US")]),                                # main
	("en", "२", [("२", "en")]),                                     # locale
	("default", "1२", [("1", "en_US"), ("२", "ne")]),               # mixed
	("default", "नेपाल५", [("नेपाल५", "ne")]),                        # nepali-text
	("default", "२ ३", [("२", "ne"), (" ", "en_US"), ("३", "ne")]),  # space-between
], ids=[...])
def test_spelling_script_digits(env, number_language, text, expected):
	detector = make_detector(env, ("en_US", "ne_NP"), number_language)
	assert list(detector.process_for_spelling(text, "en_US")) == expected
```

- `test_property_spelling_digits_carry_the_number_language`, `"default"` branch: `index == 0` or `part[0]` not decimal, or (`has_script(env, part[0])` and `covers(env, scenario, language, get_script(ord(part[0])))`).

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest -q tests/test_language_detector.py -k spelling -p no:cacheprovider`
Expected: FAIL — `arabic-indic ... [default]`, `[alone]`, `[mixed]`, `[space-between]` (4); the property may fail.

- [ ] **Step 3: Implement**

`process_for_spelling`: whitespace → spelling locale; decimal and `number_language != FOLLOW` → `_spelling_language_for_digit(number_language, default_language)`; otherwise `_script_language(character, current_language, default_language, settings)`. Update `_spelling_language_for_digit`'s signature and docstring as in Interfaces.

- [ ] **Step 4: Run to verify they pass**

`python3 -m pytest -q tests/test_language_detector.py -p no:cacheprovider` → all pass. Full suite: **3795 passed, 0 skipped**.

- [ ] **Step 5: Commit** — `fix: spell script digits in their script's language when numbers follow the text`

### Task 3: End to end through the speak harness

**Files:**
- Modify: `tests/test_worldvoice_speak.py` (211-215 harness detector, 979-1013 property, new tests near `FOLLOW_ROWS`)

**Interfaces:**
- Consumes: Tasks 1–2 behaviour; `speak_through_stages`, `VOICES`, `VoiceManager`, `NUMBER_MODE`, `TIMINGS`.
- Produces: harness detector built with `number_language=synth._numberLanguage` (spec D2); `NE = "C:ne"`.

- [ ] **Step 1: Write the tests** (each adds the voice with `monkeypatch.setitem(VOICES, "ne", NE)` before `speak_through_stages`)

```python
@TIMINGS
@pytest.mark.parametrize(("sequence", "expected"), [
	(["२०८१"], [(NE, "२०८१")]),
	(["link", "२०८१"], [(EN, "link"), (NE, "२०८१")]),
], ids=["alone", "after-english-item"])
def test_follow_gives_script_digits_to_their_language(monkeypatch, sequence, expected, timing): ...  # numlan="default"

@TIMINGS
def test_main_keeps_script_digits_in_the_main_voice(monkeypatch, timing):
	# numlan="main": ["२०८१"] -> [(EN, "२०८१")]

@TIMINGS
def test_a_hidden_number_language_reads_script_digits_as_follow(monkeypatch, timing):
	# monkeypatch.setattr(VoiceManager, "all_languages", ("en", "zh_TW", "ne")); numlan="ne"
	# (stored, not offered -> spoken FOLLOW): ["२०८१"] -> [(NE, "२०८१")]

@TIMINGS
def test_digit_mode_names_the_symbol_before_detection(monkeypatch, timing):
	# Known limitation (spec §2.3): numlan="default", settings=NUMBER_MODE, ["५.५"]
	# -> [(NE, "५ "), (EN, "full stop en "), (NE, "५")]
```

Extend the end-to-end property: `SPOKEN_PIECES` gains `"२"`; inside the test `patch.setitem(VOICES, "ne", NE)`; the oracle tracks `run_voice` (set by letters and by Devanagari digits); under `"default"` a Devanagari digit expects `NE` and sets `run_voice = NE`, other digits expect `run_voice or main_voice`; `"main"`, `"en"`, `"zh_TW"` unchanged. Add `@example(text="abc२ 12", main="en", numlan="default")` and `@example(text="२", main="en", numlan="main")`.

- [ ] **Step 2: Run to verify the red part**

Run: `python3 -m pytest -q tests/test_worldvoice_speak.py -p no:cacheprovider`
Expected: FAIL — `test_main_keeps_script_digits_in_the_main_voice` (both timings) and the property's `numlan="main"` example: the harness detector has no provider, so it treats `main` as FOLLOW. The FOLLOW, hidden-locale and digit-mode tests already pass (Tasks 1–2). If the digit-mode output differs from the expectation, pin what the code produces only if digits are `NE`, and record a `Ruling:`.

- [ ] **Step 3: Wire the harness detector** with `number_language=synth._numberLanguage` (spec D2), as the driver does (`__init__.py:287-292`).

- [ ] **Step 4: Run to verify green**

`python3 -m pytest -q tests/test_worldvoice_speak.py -p no:cacheprovider` → all pass. Full suite: **3805 passed, 0 skipped** (+10).

- [ ] **Step 5: Commit** — `test: hear script digits in their script's voice end to end`

### Task 4: Documentation

**Files:**
- Modify: `addon/doc/zh_TW/readme.md:42`, `:95-99`
- Modify: `docs/superpowers/specs/2026-10-23-phase35-number-language-follow-design.md:211`

- [ ] **Step 1: zh_TW readme** — after bullet `跟隨前後文語言（預設）` (line 42) add the sentence of spec §5; add the spec §5 entry as the last item under `## 下一版更新`. Keep the existing bullet indentation (` * `).
- [ ] **Step 2: Verify** — `prek run --all-files` all Passed; full suite **3805 passed, 0 skipped**.
- [ ] **Step 3: Commit** — `docs: describe script digits following their script's language`
- [ ] **Step 4: Phase 35 spec** — wrap the sentence `Without the branch, \`abc ١٢٣\` would switch to an Arabic voice.` in `~~…~~` and append ` Corrected by \`fix/script-digit-language\`: under "Follow surrounding text language" a digit with a script now follows the letter rule, so \`abc ١٢٣\` switches to Arabic when an Arabic voice is installed; the branch stays for "main" and locales.`
- [ ] **Step 5: Commit** — `docs: mark phase 35's digit rationale as superseded`

### Task 5: Mutation testing and full verification

**Files:** none in the repo (scratch copy + ledger only, unless a test gap is found).

- [ ] **Step 1: mutmut on `detector.py`** — `git clone -q` the worktree into the scratchpad at HEAD, symlink `ref`, set `[tool.mutmut] source_paths = ["addon/synthDrivers/WorldVoice/languageDetection/detector.py"]` and `pytest_add_cli_args_test_selection = ["tests/test_language_detector.py", "tests/test_worldvoice_speak.py", "tests/test_worldvoice_lifecycle.py"]` in the copy only; `mutmut run --max-children 3` under the memory guard; `mutmut results`.
- [ ] **Step 2: Record** each survivor with `mutmut show` and its reason in the ledger. A survivor that exposes a missing test in this branch's code → add the test to `tests/test_language_detector.py` (red on the mutant, green on HEAD), commit `test: …`, and update the expected counts.
- [ ] **Step 3: Full verification** (DEVELOPMENT_WORKFLOW §7): full suite **3805 passed, 0 skipped** (plus any Step 2 tests); `prek run --all-files` all Passed; `git diff --check master` empty; both protected-path commands print nothing.
