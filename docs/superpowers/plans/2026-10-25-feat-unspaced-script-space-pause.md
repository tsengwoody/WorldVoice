# Unspaced-script space pause Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** Turn the "Chinese space" pause into a pause at every whitespace run between two characters of an unspaced script (Han, kana, Bopomofo, Thai, Lao, Khmer, Myanmar), and rename the setting, stage and label to match.

**Architecture:** The decision lives in `pipeline/__init__.py` next to the stage: `_is_unspaced(character)` classifies one character through the existing `languageDetection.scripts.get_script` plus two explicit sets of Common characters, and `_pauses_between(text, start, end)` decides one `\s+` run, skipping Inherited marks on the left (O1). The renamed stage `inject_unspaced_script_space_pause` keeps today's shape (one reused `BreakCommand`, commands untouched). Panels, ring, confspec and log switch derive from the settings table and `STAGES`, so they follow the rename without code changes.

**Tech Stack:** Python 3 (NVDA add-on), pytest, Hypothesis, mutmut, ruff `==0.16.3` through prek, gettext `msgfmt`.

**Spec:** `docs/superpowers/specs/2026-10-25-feat-unspaced-script-space-pause-design.md`

Baseline: `master` `21e302b` (+ spec commits `aff08f6`, `577386e`); `python3 -m pytest -q -p no:cacheprovider tests` → 2941 passed, 0 skipped.

## Global Constraints

- Unspaced scripts: exactly `{"Han", "Hiragana", "Katakana", "Bopomofo", "Thai", "Lao", "Khmer", "Myanmar"}` (U3), named `UNSPACED_SCRIPTS`.
- `_UNSPACED_COMMON` = U+3006, U+3031–U+3035, U+303C, U+309B, U+309C, U+30FC, U+FF70, U+FF9E, U+FF9F (13 code points, D1). `_UNSPACED_BOPOMOFO_MARKS` = U+02C7, U+02C9, U+02CA, U+02CB, U+02D9 (Q1). Each set keeps the spec's comment (§4.2).
- Whitespace run = `re.compile(r"\s+")` (`_WHITESPACE_RE`); one `BreakCommand(waitfactor)` per stage call; a wait `<= 0` yields the sequence unchanged.
- New names (U6), no compatibility or migration: key `unspaced_script_space_wait_factor`, driver_id `unspacedscriptspacewaitfactor`, stage `inject_unspaced_script_space_pause`, `PipelineSettings.scaled_unspaced_script_space_wait()`, log switch = the key. Default 10, min 0, max 100 unchanged. Old names leave `addon/` and `tests/`; `docs/` specs stay as history.
- Label: "Space wait factor between CJK and Southeast Asian characters", existing translator comment unchanged; zh_TW 「中日文及東南亞文字空白停頓參數」. Only the zh_TW `.po` is edited; `.pot`/`.mo` are not committed.
- Import `from ..languageDetection.scripts import get_script`; no `unicodedata` in the pipeline package (structure guard).
- Never modify `driver/<Engine>/driver/`, `driver/sonic/`, `languageDetection/script_data.py`; engine drivers stay independently installable; no Neural in commits.
- Readmes: `readme.md` and `addon/doc/zh_TW/readme.md` only (Q2 = A); `buildVars.py` untouched.
- ruff pinned `0.16.3`; tabs, match surrounding style; commits English `<type>: <summary>` with a why-body, no `Co-Authored-By`, explicit `git add` paths, never `--no-verify`, never `git stash`.
- Tests: at most 3 parallel workers, with a memory guard at MemAvailable < 3 GB.

## Review Focus

1. **Characters above U+FFFF and lone surrogates next to a run** (`𠀀 か`, `\ud800 中`): one `str` index is the whole character; a surrogate gives `get_script` → `None`, no pause, no crash. Covered by Task 3 rows and Task 4 row 12.
2. **Inherited characters at the run** (combining marks, U+FE00 and U+E0100 variation selectors, ZWJ, ZWNJ; one or many; at the string start; right after the run; `中 ́ 文` where the look-back must stop at whitespace). Covered by Task 3 rows.
3. **Runs at the item edges, blank and empty items** (` 中 `, `   `, `""`): no index error at `start == 0` or `end == len(text)`, text kept, an empty item still yields nothing. Covered by Task 3 rows and Task 4 rows 17, 18, `""`.
4. **A space among the punctuation pause characters, with removal on** (F3, Q3 = A): the space break wins at unspaced spaces, the punctuation break stays at Latin spaces, removal never eats an unspaced space. Covered by Task 4 `test_stages_space_among_punctuation_characters`.
5. **The new `languageDetection` import under test and at NVDA start**: the harness must reload it per test (D5) and the synth's own import of both packages must not cycle. Covered by Task 2 `test_pipeline_harness_loads_language_detection_fresh` and the synth-loading suites (`tests/test_worldvoice_speak.py`) staying green in Task 2.

Also watched: Thai/Lao/Khmer/Myanmar digits in each number mode (Task 4 `test_stages_script_digits`), and long Latin text speed (Task 4 `test_long_text_stays_fast`; D4 fast path not added unless that test needs it).

---

### Task 1: Rename the setting, stage and label (behaviour unchanged)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/settings.py:229-238`, `:301`, `:321-322`, `:344`
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py:596-619`, `:1052`
- Modify: `addon/locale/zh_TW/LC_MESSAGES/nvda.po:419-423`
- Test: `tests/pipeline_harness.py:167`, `:179`, `:190`; `tests/test_panel_layout.py:25`; `tests/test_pipeline_filters.py:817-828`; `tests/test_pipeline_pause_properties.py:695`; `tests/test_pipeline_number_edges.py:41`; `tests/test_pipeline_number_edge_properties.py:29`, `:38`, `:227`; `tests/test_pipeline_passthrough.py:178-182`; `tests/test_pipeline_settings_service.py:18`, `:45`, `:106`, `:326`, `:360`; `tests/test_pipeline_panels.py:40`, `:55`, `:71`, `:88`; `tests/test_settings_order.py:26`, `:77`, `:167`; `tests/test_settings_panels.py:43`, `:59`, `:72`; `tests/test_worldvoice_pipeline_settings.py:36`; `tests/test_worldvoice_speak.py:316`; `tests/test_settings_table_guard.py:24`; `tests/test_translator_comments.py:43-89`

**Interfaces:**
- Consumes: nothing new.
- Produces: settings key `unspaced_script_space_wait_factor`, driver_id `unspacedscriptspacewaitfactor`, field `PipelineSettings.unspaced_script_space_wait_factor: int`, method `PipelineSettings.scaled_unspaced_script_space_wait() -> int`, stage `inject_unspaced_script_space_pause(speechSequence, settings, ctx) -> Iterator[SpeechCmd]` (still today's Han-only regex), `Stage("unspaced_script_space_wait_factor", inject_unspaced_script_space_pause)`.

- [ ] **Step 1: Rename every test occurrence** listed in Files (spec §8.1): old key/driver_id/method/stage names to the new ones; `test_chinese_space_pause` → `test_unspaced_script_space_pause`; `test_chinese_space_pause_passes_commands` → `test_unspaced_script_space_pause_passes_commands`; the `chinese` parameter → `unspaced`; slider name `chinesespace` → `unspaced_script_space`; labels "Chinese space wait factor" → "Space wait factor between CJK and Southeast Asian characters" (with ":" at `test_settings_panels.py:59`).
  - `tests/test_settings_table_guard.py:24`: `PROPER_NOUNS = {"Unicode", "CJK", "Southeast", "Asian", "WorldVoice"}` (F4, D6).
  - `tests/test_pipeline_panels.py:55`: the exemption becomes `word not in {"CJK", "Southeast", "Asian"}`.
  - `tests/test_translator_comments.py`: add `"Space wait factor between CJK and Southeast Asian characters"` to `CHANGED_LABEL_MSGIDS` (and extend its comment with the 2026-10-25 rename); add `"Chinese space wait factor"` to `DEAD_MSGIDS`.

- [ ] **Step 2: Run the touched tests to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_filters.py tests/test_pipeline_passthrough.py tests/test_pipeline_settings_service.py tests/test_pipeline_panels.py tests/test_settings_order.py tests/test_settings_panels.py tests/test_worldvoice_pipeline_settings.py tests/test_translator_comments.py tests/test_panel_layout.py tests/test_pipeline_structure.py`
Expected: FAIL — `AttributeError: ... 'inject_unspaced_script_space_pause'`, `KeyError`/assertion diffs on the old key and label, and `test_zh_tw_catalog_follows_the_labels` missing the new msgid.

- [ ] **Step 3: Rename in the code**
  - `settings.py`: table entry key, `driver_id`, `label=_("Space wait factor between CJK and Southeast Asian characters")` with the existing two-line translator comment; the field; `scaled_unspaced_script_space_wait(self) -> int` returning `self.global_factor_units * self.unspaced_script_space_wait_factor`; the `effective` override field.
  - `pipeline/__init__.py`: rename the stage function and its `settings.scaled_unspaced_script_space_wait()` call; the `STAGES` entry. Keep `_CH_SPACE_RE` for now (Task 4 removes it).
  - `nvda.po:419-423`: `msgid "Space wait factor between CJK and Southeast Asian characters"` / `msgstr "中日文及東南亞文字空白停頓參數"` in place of the old entry (keep the entry's `#.`/`#:` lines).

- [ ] **Step 4: Run green checks**

Run: the Step 2 command, then `msgfmt --check -o /dev/null addon/locale/zh_TW/LC_MESSAGES/nvda.po`, then `grep -rni "chinese_\?space\|chinesespace" addon tests --include=*.py` (expect only `_CH_SPACE_RE` in `pipeline/__init__.py`; the `such_space` test name is ignored), then the full suite.
Expected: PASS; full suite **2941 passed, 0 skipped**.

- [ ] **Step 5: Commit** (`addon/.../pipeline/settings.py`, `addon/.../pipeline/__init__.py`, `addon/locale/zh_TW/LC_MESSAGES/nvda.po`, the listed tests)

`refactor: rename the Chinese space pause to the unspaced script space pause` — body: the rule is about to cover kana, Bopomofo and the Southeast Asian scripts (U6, U7); no migration, old stored values are dropped (U8).

### Task 2: Classify a character as unspaced

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (import block; constants near the stage)
- Modify: `tests/pipeline_harness.py:47-71` (D5)
- Create: `tests/test_pipeline_unspaced_space.py`

**Interfaces:**
- Consumes: `get_script(codepoint: int) -> str | None` from `addon/synthDrivers/WorldVoice/languageDetection/scripts.py`.
- Produces: `UNSPACED_SCRIPTS: frozenset[str]`, `_UNSPACED_COMMON: frozenset[str]`, `_UNSPACED_BOPOMOFO_MARKS: frozenset[str]` (one-character strings), `_is_unspaced(character: str) -> bool`; module attribute `get_script` in the pipeline module.

- [ ] **Step 1: Write the failing tests** in `tests/test_pipeline_unspaced_space.py` (module docstring naming the spec; `env` fixture = `load_pipeline_module(monkeypatch, punctuation_settings(0))`):
  - `test_unspaced_scripts_are_the_users_list`: `module.UNSPACED_SCRIPTS == frozenset({"Han", "Hiragana", "Katakana", "Bopomofo", "Thai", "Lao", "Khmer", "Myanmar"})`.
  - `test_is_unspaced` parametrized over U+4E00, U+3400, U+9FFF, U+F900, U+20000, U+3005, U+3007, あ, ア, U+FF71, U+3105, U+31A0, ก, ກ, ក, က, U+1B001: `module._is_unspaced(ch) is True` (17 cases).
  - `test_unspaced_common_is_pinned`: `module._UNSPACED_COMMON == {chr(c) for c in (0x3006, *range(0x3031, 0x3036), 0x303C, 0x309B, 0x309C, 0x30FC, 0xFF70, 0xFF9E, 0xFF9F)}` and every member has `module.get_script(ord(ch)) == "Common"`.
  - `test_bopomofo_tone_marks_are_pinned`: `module._UNSPACED_BOPOMOFO_MARKS == {chr(c) for c in (0x02C7, 0x02C9, 0x02CA, 0x02CB, 0x02D9)}`, each `"Common"`.
  - `test_every_listed_character_is_unspaced`: `all(module._is_unspaced(ch) for ch in module._UNSPACED_COMMON | module._UNSPACED_BOPOMOFO_MARKS)`.
  - `test_is_not_unspaced` parametrized over a, A, Я, 한, U+3131, 1, U+FF11, 。, 「, U+30FB, U+30A0, U+3000, U+3099, U+E000, U+D800, U+0378, U+02C8, U+02CC: `module._is_unspaced(ch) is False` (18 cases).
  - `test_pipeline_harness_loads_language_detection_fresh`: load the pipeline twice with `load_pipeline_module`; the `sys.modules["synthDrivers.WorldVoice.languageDetection.scripts"]` object after the second load `is not` the one after the first, and the second pipeline module's `get_script is` that new module's `get_script`.

- [ ] **Step 2: Run to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_unspaced_space.py`
Expected: FAIL — `AttributeError: module 'synthDrivers.WorldVoice.pipeline' has no attribute 'UNSPACED_SCRIPTS'` (and `get_script` / `KeyError` in the harness test).

- [ ] **Step 3: Implement** in `pipeline/__init__.py`: add `from ..languageDetection.scripts import get_script` (D3) to the relative imports; add the three constants with the spec §4.2 comments; `_is_unspaced(character: str) -> bool` is true when the character is in either set or `get_script(ord(character)) in UNSPACED_SCRIPTS`. In `tests/pipeline_harness.py` add `"synthDrivers.WorldVoice.languageDetection"` and `"synthDrivers.WorldVoice.languageDetection.scripts"` to the popped list (D5).

- [ ] **Step 4: Run green**

Run: the Step 2 command, then `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_structure.py tests/test_worldvoice_speak.py tests/test_language_detection*.py`, then the full suite.
Expected: PASS; full suite **2980 passed, 0 skipped** (+39).

- [ ] **Step 5: Commit** — `feat: classify the characters of unspaced scripts` (body: U3, U4, D1, Q1; D5 keeps the harness from reusing a languageDetection loaded against an earlier test's stubs).

### Task 3: Decide one whitespace run

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py`
- Test: `tests/test_pipeline_unspaced_space.py`

**Interfaces:**
- Consumes: `_is_unspaced`, `get_script` (Task 2).
- Produces: `_pauses_between(text: str, start: int, end: int) -> bool` — true when `text[start:end]` (a maximal `\s+` run) becomes the pause.

- [ ] **Step 1: Write the failing test** `test_pauses_between(env, text, expected)`: `expected == [module._pauses_between(text, m.start(), m.end()) for m in re.finditer(r"\s+", text)]`, parametrized (21 rows):

| text | expected | why |
|---|---|---|
| `"中 文"` | `[True]` | Han both sides |
| `"が か"` | `[True]` | row 19 |
| `"葛\U000E0100 中"` | `[True]` | row 20, VS is Inherited |
| `"中︀ 文"` | `[True]` | VS16 range |
| `"中‍ 文"`, `"中‌ 文"` | `[True]` each | ZWJ, ZWNJ |
| `"が́ か"` | `[True]` | two marks |
| `"中 ゙か"` | `[False]` | row 21, mark after the run |
| `"゙ か"` | `[False]` | mark at the string start, no base |
| `"中 ́ 文"` | `[False, False]` | look-back stops at whitespace |
| `" 中 "` | `[False, False]` | row 17 |
| `"   "` | `[False]` | row 18 |
| `"ｺｰ ｸ"`, `"ーー か"`, `"カﾞ ア"` | `[True]` each | Common kana marks as left base |
| `"\U00020000 か"` | `[True]` | Extension B |
| `"\ud800 中"`, `"中 \ud800"` | `[False]` each | lone surrogate |
| `"中 a"` | `[False]` | Latin right |

- [ ] **Step 2: Run to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_unspaced_space.py -k pauses_between`
Expected: FAIL — `AttributeError: ... no attribute '_pauses_between'`.

- [ ] **Step 3: Implement `_pauses_between(text: str, start: int, end: int) -> bool`** per spec §4.3: false at `end == len(text)`; walk back from `start - 1` while `get_script(ord(text[i])) == "Inherited"`; false if the walk passes the start; else `_is_unspaced(base) and _is_unspaced(text[end])`.

- [ ] **Step 4: Run green**

Run: the Step 2 command, then the full suite.
Expected: PASS; full suite **3001 passed, 0 skipped** (+21).

- [ ] **Step 5: Commit** — `feat: decide whether a whitespace run is an unspaced script pause` (body: O1, ends of the string).

### Task 4: The stage pauses at every unspaced run

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py:32` (remove `_CH_SPACE_RE`), the stage body
- Test: `tests/test_pipeline_unspaced_space.py`

**Interfaces:**
- Consumes: `_pauses_between` (Task 3); `inject_unspaced_script_space_pause`, `scaled_unspaced_script_space_wait` (Task 1).
- Produces: `_WHITESPACE_RE = re.compile(r"\s+")`; the stage's final behaviour.

- [ ] **Step 1: Write the failing tests**
  - `test_worked_examples(env, text, expected)`: `shape(list(module.inject_unspaced_script_space_pause([text], settings, module.GENERIC_CONTEXT)))` with `scaled_unspaced_script_space_wait = lambda: 20` equals the §5 output, a break written `("BreakCommand", 20)`. Rows 1–26 of §5 (rows 8 and 24c as two inputs each) plus `""` → `[]`: 33 cases.
  - `test_wait_zero_yields_the_same_objects`: wait 0 on `[marker, "中 文", "かな カナ"]` gives a list whose items are the same objects (`is`), in order.
  - `test_several_runs_reuse_one_break`: `"中 文 か ภา"` gives `["中", B, "文", B, "か", B, "ภา"]` and the three breaks are one object.
  - `test_stages_pause_between_han_and_kana`: every `STAGES` handler in order, value mode, roles on (zh context), wait 10 on `["漢字 かな"]` → `["漢字", ("BreakCommand", 10), "かな"]`.
  - `test_stages_digit_neighbour_has_no_space_pause`: number mode, number pause 0, `["第3 章"]` → no `BreakCommand` of the space wait in the output (only plain text and number commands).
  - `test_stages_space_among_punctuation_characters` parametrized on removal off/on: punctuation characters `" "`, punctuation wait 250, space wait 10, `["ภาษา ไทย hello world"]` → `ภาษา`, `B(10)`, `ไทย`, then at each Latin space a `PunctuationBreakCommand(250)` (with removal off the `" "` stays as text before it; with removal on it is gone) — F3, Q3 = A.
  - `test_stages_script_digits` parametrized over (value, 0), (value, 10), (number, 0), (number, 10), (group, 0), (group, 10) (mode, number pause): `["๑ ๒"]` through `STAGES` gives exactly one break item between `๑` and `๒`; it is the plain space `BreakCommand(10)` unless the mode is number or group with a pause above 0, where it is a `NumberBreakCommand` (spec §4.4).
  - `test_long_text_stays_fast`: `"hello world " * 15000` and `"ภาษา ไทย " * 15000` through the stage at wait 20 each finish under 2 s (`time.perf_counter`), and the Latin one yields one string.

- [ ] **Step 2: Run to see red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_unspaced_space.py`
Expected: FAIL — the kana, Thai, Bopomofo, Extension A/B and mixed-script rows, `test_several_runs_reuse_one_break`, `test_stages_pause_between_han_and_kana`, the Thai rows of the F3 and digit tests show no break; Han-only rows pass.

- [ ] **Step 3: Implement**: remove `_CH_SPACE_RE` and the old `# the space between two CJK characters` comment; add `_WHITESPACE_RE`; for each string item, walk `_WHITESPACE_RE.finditer(item)`, yield the text since the last pause and `pause_cmd` for each run where `_pauses_between(item, start, end)` is true, then the remaining text if non-empty. Do not use `_split_by` (it cannot filter). D4 fast path only if `test_long_text_stays_fast` fails.

- [ ] **Step 4: Run green**

Run: the Step 2 command; `grep -rni "chinese_\?space\|chinesespace\|CH_SPACE" addon tests --include=*.py` (nothing except `such_space`); the full suite.
Expected: PASS; full suite **3047 passed, 0 skipped** (+46).

- [ ] **Step 5: Commit** — `feat: pause at spaces between characters of any unspaced script` (body: U1–U5, F3/Q3, F6; `_CH_SPACE_RE` replaced; timing measured).

### Task 5: Property tests

**Files:**
- Create: `tests/test_pipeline_unspaced_space_properties.py`

**Interfaces:**
- Consumes: `inject_unspaced_script_space_pause`, `_is_unspaced`, `get_script` (Tasks 2–4).
- Produces: nothing for later tasks.

- [ ] **Step 1: Write the properties** (Hypothesis, `SHARED_ENV` as in `tests/test_pipeline_number_edge_properties.py`). Alphabet: 中, U+3400, U+20000, か, カ, ー, ｰ, ก, 한, a, 1, 。, U+3099, U+0301, ˇ, `" "`, `\n`, U+3000, U+00A0. Items: text or a marker command. Wait from `st.integers(1, 60)` unless stated.
  - `test_property_text_is_kept` (P1): for each input string, replacing each break in its output piece list by the next `\s+` match the oracle reports as pausing reconstructs the input exactly, and each break stands for a whole maximal run.
  - `test_property_no_pause_next_to_a_spaced_character` (P2): every input run whose right neighbour is not unspaced, or whose left base (skip Inherited, stop at whitespace) is missing or not unspaced, is still inside the output text; an input with no unspaced character comes out equal.
  - `test_property_superset_of_the_han_rule` (P3): every run matched by the oracle literal `re.compile(r"(?<=[一-龥])\s+(?=[一-龥])")` becomes a break.
  - `test_property_off_is_identity` (P4): wait from `st.integers(-5, 0)` → output items are the input objects, in order.
  - `test_property_commands_pass_through` (P5): non-string items come out once each, in order; each break has non-empty text from the same input item on both sides.

- [ ] **Step 2: Run**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_pipeline_unspaced_space_properties.py tests/test_pipeline_pause_properties.py`
Expected: PASS (properties of Task 4's code; their bite is checked by mutmut in Task 7). Full suite **3052 passed, 0 skipped** (+5).

- [ ] **Step 3: Commit** — `test: properties of the unspaced script space pause` (body: spec §8.3 P1–P5).

### Task 6: Readmes and changelog

**Files:**
- Modify: `readme.md:14`, `:39`, `:53`, changelog under "Next update" (`:73`)
- Modify: `addon/doc/zh_TW/readme.md:14`, `:39`, `:53`, `:73`

**Interfaces:**
- Consumes: the label of Task 1.
- Produces: nothing.

- [ ] **Step 1: Apply the spec §6 "Readmes" text verbatim** (lines 14, 39, 53 first sentence plus the added sentence; one changelog bullet at the top of "Next update" with the Q3 sentence appended), English and zh_TW.
- [ ] **Step 2: Check**: `prek run --files readme.md addon/doc/zh_TW/readme.md`; `grep -n "Chinese pause\|Chinese text\|中文間停頓\|中文之間" readme.md addon/doc/zh_TW/readme.md` → nothing. Full suite unchanged: **3052 passed, 0 skipped**.
- [ ] **Step 3: Commit** — `docs: describe the space pause for unspaced scripts in the readmes` (body: Q2 = A, U8 reset noted in the changelog).

### Task 7: Mutation testing

**Files:**
- Test: `tests/test_pipeline_unspaced_space.py` (only if a survivor is killable)
- Ledger: `.superpowers/sdd/2026-10-25-feat-unspaced-script-space-pause/progress.md`

**Interfaces:**
- Consumes: Tasks 2–5.
- Produces: the survivor list for the report.

- [ ] **Step 1: Run mutmut** in a scratch copy of the worktree (scratchpad, with the `ref` symlink), restricted to `_is_unspaced`, `_pauses_between` and `inject_unspaced_script_space_pause` of `pipeline/__init__.py`, test selection `tests/test_pipeline_unspaced_space.py tests/test_pipeline_unspaced_space_properties.py tests/test_pipeline_filters.py tests/test_pipeline_passthrough.py`, `--max-children 3`, under the memory guard.
- [ ] **Step 2: For each survivor**: if a reasonable input tells it apart, add the test (red on the mutant, green on the code); else record it as equivalent with the reason.
- [ ] **Step 3: Run** the full suite: **3052 + n passed, 0 skipped** (n = tests added in Step 2). Commit any new tests — `test: pin the cases the surviving mutants change`.

### Task 8: Final verification

**Files:** none changed (fix and commit only if a check fails).

- [ ] **Step 1:** `python3 -m pytest -q -p no:cacheprovider tests` → **3052 + n passed, 0 skipped**.
- [ ] **Step 2:** `prek run --all-files` → all Passed; `git diff --check master` → empty.
- [ ] **Step 3:** protected paths: `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py` and `git ls-files addon/synthDrivers/WorldVoice/driver/Neural` → both empty.
- [ ] **Step 4:** `grep -rni "chinese_\?space\|chinesespace\|CH_SPACE" addon tests --include=*.py` → only `such_space`; `msgfmt --check -o /dev/null addon/locale/zh_TW/LC_MESSAGES/nvda.po` → no output.
- [ ] **Step 5:** Report: not verified on Windows/NVDA, real audio or engine SDKs; manual items M1–M12 of spec §8.6 remain.
