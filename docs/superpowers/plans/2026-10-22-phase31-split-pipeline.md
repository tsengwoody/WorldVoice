# Phase 31 Split Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** Move number lexing into `pipeline/numbers.py` (standard library only) and NVDA symbol-name lookup into `pipeline/symbols.py`, cache the symbols-table probe once per locale, and delete the dead `_SENTENCE_END_RE`, with no change to what NVDA users hear.

**Architecture:** A pure move. Every moved body keeps its exact logic; only the D3 renames (public names in the new modules) and the `number_pieces`/`strip_thousands` extractions are new lines. `pipeline/__init__.py` imports the two modules relatively; neither new module imports the package. `has_symbol_table = lru_cache(maxsize=None)(_symbol_table_on_disk)` (call form, so mutmut still mutates the probe). Tests reach the new modules as attributes of the loaded package (`env.module.numbers`, `module.symbols`), so the object under test, its stubs and its cache are the ones the stages use.

**Tech Stack:** Python 3.14, pytest, Hypothesis, mutmut 3.8.0, ruff 0.16.3 via prek 0.4.14.

**Spec:** `docs/superpowers/specs/2026-10-22-phase31-split-pipeline-design.md` (commit `fd9bd8a`). Line numbers below refer to `41dc50d` unless stated.

## Global Constraints

- Pure refactor apart from the `has_symbol_table` cache (spec §2, §10 "Behaviour equivalence"). Every moved function and constant keeps its exact logic; only the names it references are renamed (spec §4.1, §4.2). No string, setting, config key, panel or log key changes.
- Use `lru_cache(maxsize=None)(...)` in call form, never `@lru_cache` or `@cache` (spec §9, Q2). Do not cache `speech.getCurrentLanguage()` (spec §5).
- `numbers.py` imports only `re`, `unicodedata`, `collections.abc`, `itertools`. `symbols.py` imports `os`, `functools`, `collections.abc` and NVDA's `characterProcessing`, `globalVars`, `languageHandler`, `speech`. Neither has a relative import (spec §6).
- `__init__.py` keeps no underscore aliases of moved names (D3). `_run_logged`, `_get_punctuation_regex`, `_split_punctuation_segments`, `_CH_SPACE_RE`, `_split_numbers`, `_both_numbers`, `_translate_number` stay private in `__init__.py` (Q5). No `is_number` helper (Q1). `test_pipeline_nvda_symbols.py:20` `NUMBER_SYMBOLS` stays (Q6).
- No existing test is removed, renamed or re-parametrized; edits are attribute paths only (spec §7.3).
- Never modify `addon/synthDrivers/WorldVoice/driver/<Engine>/driver/`, `driver/sonic/` or `languageDetection/script_data.py`. Engine drivers stay independently installable. Never add Neural back.
- ruff is pinned `==0.16.3`. Every commit runs the prek hooks; if a hook modifies files, restage and recommit; never `--no-verify`. Run `prek run --files <new files>` after staging new files, before committing.
- git: stage explicit paths only, check `git diff --cached --stat` before each commit. Messages English `<type>: <summary>` with a body that says why. No `Co-Authored-By`. Never `git stash`, never push, never touch `/workspace/WorldVoice`. Never stage `ref`. The plan is committed with `git add -f`.
- Full suite: `python3 -m pytest -q -p no:cacheprovider tests`, single process, under the memory guard (kill when MemAvailable < 3 GB). mutmut: `--max-children 3`, memory guard, scratch copies only.
- Baseline on `41dc50d`: **2343 passed, 0 skipped**. Target: **2346 passed, 0 skipped**.
- Each task ends with §7 checks: full suite, `prek run --all-files` all Passed, `git diff --check master`, and both protected-path commands empty.

## Review Focus

1. **A stale submodule between tests.** If the harness pop list misses `pipeline.numbers` or `pipeline.symbols`, the next test reuses the previous `symbols` module with its old stubs and filled cache. Task 3 runs each edited test file alone and the full suite in default order; Task 4's `test_symbol_tables_are_probed_once_per_locale` records zero probes (and fails) if it receives a module whose cache an earlier test filled.
2. **A voice, synth or "trust voice's language" change at runtime.** The answer of `getCurrentLanguage()` must still be asked every stage run. Task 4: `test_symbol_tables_are_probed_once_per_locale` asserts 3 `getCurrentLanguage` calls in 3 runs; the existing `test_namer_asks_each_language_once_per_run` keeps the per-run voice-locale ask.
3. **Locales that are not plain names** (`""`, `".."`, `"../en"`, `"../locale/en"`) and locales with no table (`"zh"`, `"en_US"`) must still give `False` through the cache, with no exception. Task 3/4: `test_has_symbol_table_matches_nvdas_locale_dir` keeps its 9 cases against `module.has_symbol_table`, which after Task 4 is the cached function.
4. **Value mode and single-piece numbers** must reach the synth with no number break: `number_pieces` returns `[raw]`, and `_translate_number` must yield no separator for one piece. Task 2: the existing `test_value_and_off_leave_symbols_alone` and Hypothesis P-properties over all four modes in `test_pipeline_pause_properties.py`, plus `number_pieces` mutants in Task 6.
5. **The real add-on import** (`numbers` is also a standard-library name). The package must import under NVDA's layout, and `import numbers` elsewhere must still get the standard library. Task 2: `test_worldvoice_speak.py` imports the real `synthDrivers.WorldVoice` package; Guard A forbids a relative import in `numbers.py`.

---

### Task 1: mutmut baseline (no commit)

**Files:** none in the worktree. Scratch clone `<scratchpad>/p31/before` at `41dc50d`, with `ref` symlinked.

**Interfaces:**
- Consumes: none.
- Produces: the "before" table (mutants, killed, survived per function) in the ledger, for Task 6.

- [ ] **Step 1: Run mutmut on the base commit**

Run (in the clone, under the memory guard): `mutmut run --max-children 3` with the globs `addon.synthDrivers.WorldVoice.pipeline.` + `x__split_spaced_numbers*`, `x__translate_number*`, `x_remove_thousands_separators*`, `x__has_symbol_table*`, `x__symbol_locale*`, `x__symbol_name*`, `x__symbol_namer*`, `x__both_numbers*`, `x_iter_number_speech_segments_mode*`, `x_inject_number_mode*`, `x_iter_number_speech_segments_language*`.
Expected: run completes; no timeout and no "suspicious". Survivors include `x__has_symbol_table__mutmut_7` and `x__symbol_locale__mutmut_15` (both equivalent, `7c67961`).

- [ ] **Step 2: Record per-function counts in the ledger** from `mutmut results --all true`. Suite unchanged: 2343 passed, 0 skipped.

### Task 2: `pipeline/numbers.py`

**Files:**
- Create: `addon/synthDrivers/WorldVoice/pipeline/numbers.py`
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (`:3`, `:8`, `:37-52`, `:158`, `:212-213`, `:256-280`, `:286`, `:376`, `:417-452`, `:524`)
- Modify: `tests/pipeline_harness.py:43-64` (pop list)
- Test: `tests/test_pipeline_structure.py`, `tests/test_pipeline_filters.py:144,150`, `tests/test_pipeline_pause_properties.py:313,355,408,414,440,531,546,565,587,693`

**Interfaces:**
- Consumes: none.
- Produces (in `pipeline/numbers.py`): `SYMBOLS: str`, `NUMBER_RE: re.Pattern`, `NUMBER_TOKEN_RE: re.Pattern`, `DIGITS: frozenset[str]`, `THOUSANDS_RE: re.Pattern`, `split_spaced_numbers(text: str) -> Iterator[str]`, `number_pieces(raw: str, mode: str, group_size: int, name_of: Callable[[str], str | None]) -> list[str]`, `strip_thousands(text: str) -> str`. Tests reach them as `env.module.numbers.<name>`.

- [ ] **Step 1: Write Guard A** in `tests/test_pipeline_structure.py`

```python
def test_number_lexing_imports_only_the_standard_library():
	tree = ast.parse((WORLDVOICE / "pipeline" / "numbers.py").read_text(encoding="utf-8"))
	for node in ast.walk(tree):
		if isinstance(node, ast.Import):
			modules = [alias.name for alias in node.names]
		elif isinstance(node, ast.ImportFrom):
			assert node.level == 0, ast.unparse(node)
			modules = [node.module]
		else:
			continue
		assert all(module.split(".")[0] in sys.stdlib_module_names for module in modules), ast.unparse(node)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest -q tests/test_pipeline_structure.py`
Expected: 1 failed (`FileNotFoundError: ... pipeline/numbers.py`), 1 passed.

- [ ] **Step 3: Create `numbers.py` and edit `__init__.py`**
  - Module docstring as spec §4.1. Move `_SYMBOLS`, `_NUMBER_RE`, `_NUMBER_TOKEN_RE`, `_DIGITS`, `_THOUSANDS_RE` (`:37-52`, with comments) verbatim under their public names; move `_split_spaced_numbers` (`:256-280`) as `split_spaced_numbers`, body verbatim with `NUMBER_RE`.
  - `number_pieces`: body is `:432-446` verbatim with value mode as `return [raw]` and `return pieces` at the end; docstring from the piece rules of `:426-429`.
  - `strip_thousands(text)`: `return THOUSANDS_RE.sub(lambda match: match.group().replace(",", ""), text)`.
  - `__init__.py`: drop `import unicodedata` and `from itertools import pairwise`; add `from .numbers import NUMBER_RE, number_pieces, split_spaced_numbers, strip_thousands`; edit the call sites of spec §4.5 (`:158`, `:212-213`, `:286`, `:376`, `:524`); reduce `_translate_number` to the spec §4.5 shape, keeping its annotated signature. `_SENTENCE_END_RE` stays until Task 5.
  - `pipeline_harness.py`: add `"synthDrivers.WorldVoice.pipeline.numbers"` to the pop list.
  - Tests: `env.module._NUMBER_RE` → `env.module.numbers.NUMBER_RE`; `env.module._SYMBOLS` → `env.module.numbers.SYMBOLS` (sites above). No other edit.

- [ ] **Step 4: Run the touched tests, then the full suite**

Run: `python3 -m pytest -q tests/test_pipeline_structure.py tests/test_pipeline_filters.py tests/test_pipeline_pause_properties.py tests/test_worldvoice_speak.py`
Expected: all pass (structure 2, filters 207, pause properties 29).
Run: full suite. Expected: **2344 passed, 0 skipped**. Then §7 checks.

- [ ] **Step 5: Commit** (`prek run --files` on the staged new file first): `refactor: move number lexing into pipeline/numbers.py`.

### Task 3: `pipeline/symbols.py`, no cache yet

**Files:**
- Create: `addon/synthDrivers/WorldVoice/pipeline/symbols.py`
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (`:1`, `:11`, `:13-15`, `:97-139`, `:455-478`, `:494`, `:497`)
- Modify: `tests/pipeline_harness.py` (pop list)
- Test: `tests/test_pipeline_nvda_symbols.py` (fixture `:23-26`, `:30,49,67,88,119,130,136,141,230,247`), `tests/test_pipeline_filters.py:512,527,540,611`, `tests/test_pipeline_pause_properties.py:442,443,449,654,655,670`

**Interfaces:**
- Consumes: none from Task 2.
- Produces (in `pipeline/symbols.py`): `_symbol_table_on_disk(locale: str) -> bool`, `has_symbol_table` (plain alias `= _symbol_table_on_disk` in this task), `symbol_locale(language: str | None, voice_locale: str | None = None) -> str`, `symbol_name(locale: str, symbol: str) -> str | None`, `symbol_namer(voice_locale_for_language: Callable[[str], str | None]) -> Callable[[str | None], Callable[[str], str | None]]`. The `module` fixture of `test_pipeline_nvda_symbols.py` returns `load_pipeline_module(...)[0].symbols`.

- [ ] **Step 1: Edit the tests to the new names and paths** (spec §7.3): fixture returns `.symbols`; `_symbol_name`/`_symbol_locale`/`_has_symbol_table`/`_symbol_namer` → public names; comment `:141` → `has_symbol_table`; `env.module.speech` → `env.module.symbols.speech`; `env.module.characterProcessing` / `module.characterProcessing` → `….symbols.characterProcessing`.

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest -q tests/test_pipeline_nvda_symbols.py tests/test_pipeline_filters.py tests/test_pipeline_pause_properties.py`
Expected: FAIL with `AttributeError: module 'synthDrivers.WorldVoice.pipeline' has no attribute 'symbols'` on every edited site.

- [ ] **Step 3: Create `symbols.py` and edit `__init__.py`**
  - Docstring per spec §4.2 (the cache sentence is added in Task 4). Move `:97-107` as `_symbol_table_on_disk` (body and docstring verbatim), add `has_symbol_table = _symbol_table_on_disk`; move `:110-130` as `symbol_locale` (its call becomes `has_symbol_table(locale)`), `:133-139` as `symbol_name`, `:455-478` as `symbol_namer` (calls `symbol_locale`, `symbol_name`).
  - `__init__.py`: drop `import os`, `characterProcessing`, `globalVars`, `languageHandler`, `speech`; add `from .symbols import symbol_namer`; `:494` → `symbol_namer(...)`; comment `:497` → `symbols.symbol_locale`.
  - `pipeline_harness.py`: add `"synthDrivers.WorldVoice.pipeline.symbols"` to the pop list.

- [ ] **Step 4: Run each edited file alone, then the full suite**

Run: the three files of Step 2, each alone. Expected: 45, 207, 29 passed.
Run: full suite. Expected: **2344 passed, 0 skipped**. Then §7 checks.

- [ ] **Step 5: Commit**: `refactor: move NVDA symbol-name lookup into pipeline/symbols.py`.

### Task 4: cache the symbols-table probe

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/symbols.py`
- Test: `tests/test_pipeline_nvda_symbols.py`

**Interfaces:**
- Consumes: Task 3's `symbol_namer`, `has_symbol_table`, `_symbol_table_on_disk`.
- Produces: `has_symbol_table = lru_cache(maxsize=None)(_symbol_table_on_disk)`.

- [ ] **Step 1: Write the failing test**

```python
def test_symbol_tables_are_probed_once_per_locale(module, monkeypatch):
	# D2: one probe per locale per NVDA run; getCurrentLanguage stays live (3 runs -> 3 calls).
	probes, current = [], []
	isfile = module.os.path.isfile
	monkeypatch.setattr(module.os.path, "isfile", lambda path: probes.append(path) or isfile(path))
	monkeypatch.setattr(module.speech, "getCurrentLanguage", lambda: current.append(1) or "en")
	for _ in range(3):
		namer = module.symbol_namer({"zh": "zh-TW", "en": "en-US"}.get)
		assert (namer("zh")("×"), namer("en")("×")) == ("multiplication sign zh tw", "multiplication sign en")
	app_dir = Path(module.globalVars.appDir)
	assert sorted(Path(path).relative_to(app_dir).as_posix() for path in probes) == [
		"locale/en_US/symbols.dic",
		"locale/zh_TW/symbols.dic",
	]
	assert len(current) == 3
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest -q tests/test_pipeline_nvda_symbols.py -k probed_once`
Expected: FAIL on the probe list (6 paths, each locale three times).

- [ ] **Step 3: Wrap with the cache** — `from functools import lru_cache`; `has_symbol_table = lru_cache(maxsize=None)(_symbol_table_on_disk)`; add the cache rule of spec §5 to the module docstring and one sentence to the probe's docstring.

- [ ] **Step 4: Run it, then the full suite**

Run: `python3 -m pytest -q tests/test_pipeline_nvda_symbols.py` → 46 passed. Full suite → **2345 passed, 0 skipped**. Then §7 checks.

- [ ] **Step 5: Commit**: `perf: probe each NVDA symbols table once per locale`.

### Task 5: Guard B and the dead regex

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (`:54-55`)
- Test: `tests/test_pipeline_structure.py`

**Interfaces:**
- Consumes: Tasks 2–3's module layout.
- Produces: none.

- [ ] **Step 1: Write Guard B**

```python
MOVED = ["SYMBOLS", "NUMBER_RE", "NUMBER_TOKEN_RE", "DIGITS", "THOUSANDS_RE", "SENTENCE_END_RE",
	"split_spaced_numbers", "number_pieces", "strip_thousands", "has_symbol_table",
	"symbol_table_on_disk", "symbol_locale", "symbol_name", "symbol_namer"]

def test_pipeline_package_keeps_only_stages_logging_and_registry():
	# defined: top-level FunctionDef/ClassDef names, Assign Name targets, AnnAssign Name targets
	assert defined & {*MOVED, *(f"_{name}" for name in MOVED)} == set()
	assert imported_modules(WORLDVOICE / "pipeline" / "__init__.py") & {
		"os", "unicodedata", "characterProcessing", "globalVars", "languageHandler", "speech"} == set()
	# symbols.py: no ImportFrom with level > 0 anywhere (ast.walk)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest -q tests/test_pipeline_structure.py`
Expected: 1 failed, on `{'_SENTENCE_END_RE'}`; 2 passed.

- [ ] **Step 3: Delete `_SENTENCE_END_RE` and the blank line before it** (`:54-55`).

- [ ] **Step 4: Run it, then the full suite**

Run: `python3 -m pytest -q tests/test_pipeline_structure.py` → 3 passed. Full suite → **2346 passed, 0 skipped**. Then §7 checks.

- [ ] **Step 5: Commit**: `refactor: guard the pipeline split and drop the dead sentence-end regex`.

### Task 6: mutmut after-run and comparison

**Files:**
- Modify: `pyproject.toml:38-47` (`source_paths`)
- Modify: this plan (append "Implementation notes: mutmut")

**Interfaces:**
- Consumes: Task 1's table.
- Produces: none.

- [ ] **Step 1: Add the two paths after `pipeline/__init__.py`** in `source_paths` (spec §8). Full suite: **2346 passed, 0 skipped**; §7 checks. Commit: `chore: mutate the new pipeline modules`.

- [ ] **Step 2: Run mutmut on a scratch clone of the branch head**, same guard and `--max-children 3`, with the "after" globs of spec §10: `numbers.x_split_spaced_numbers*`, `numbers.x_number_pieces*`, `numbers.x_strip_thousands*`, `symbols.x__symbol_table_on_disk*`, `symbols.x_symbol_locale*`, `symbols.x_symbol_name*`, `symbols.x_symbol_namer*`, and in the package `x__translate_number*`, `x_remove_thousands_separators*`, `x__both_numbers*`, `x_iter_number_speech_segments_mode*`, `x_inject_number_mode*`, `x_iter_number_speech_segments_language*`. Confirm the names with `mutmut results --all true` first.
Expected: `symbols.x__symbol_table_on_disk__mutmut_*` exists; verbatim moves have the same mutant and killed counts; survivors are the two known equivalents under their new names; no timeout, no "suspicious".

- [ ] **Step 3: Compare and close.** For the two split functions the after-sum may differ only by glue lines; kill each new glue-line survivor with a test (TDD, full suite, recount) or record why it is equivalent. Append both tables and the survivor notes to this plan. Commit: `docs: record the phase 31 mutation comparison`.

### Task 7: full verification and report

**Files:** none.

- [ ] **Step 1: §7 checks on the branch head**: full suite **2346 passed, 0 skipped**; `prek run --all-files` all Passed; `git diff --check master` clean; both protected-path commands print nothing; `wc -l` of `pipeline/__init__.py` (≈855), `numbers.py` (≈90), `symbols.py` (≈85).
- [ ] **Step 2: Report** to the orchestrator: commits, Rulings, counts, prek, protected-path output, mutmut comparison, line counts. The orchestrator dispatches the final Fable 5.1 review.

## Implementation notes: mutmut

mutmut 3.8.0 on 2026-10-22, scratch clones, `--max-children 3`, memory guard. Before: `41dc50d`. After: `abc92df`. Prefix `addon.synthDrivers.WorldVoice.pipeline.`. Neither run had a timeout or a "suspicious" result.

**Baseline:** the "After" columns are the pipeline's mutmut baseline for these functions from now on, replacing `e81b278`. That record was incomplete: it listed `iter_number_speech_segments_mode` with 0 survivors where it has 4 (`_1`, `_4`, `_34`, `_35`; the body is unchanged since `844d8d2`) and left out `iter_number_speech_segments_language` and its 3 survivors (`_11`, `_13`, `_14`); all 7 are equivalent, for the reasons below.

| Before | Mutants (killed / survived) | After | Mutants (killed / survived) |
| --- | --- | --- | --- |
| `x__split_spaced_numbers` | 21 (21 / 0) | `numbers.x_split_spaced_numbers` | 21 (21 / 0) |
| `x__translate_number` | 47 (46 / 1) | `numbers.x_number_pieces` + `x__translate_number` | 44 (43 / 1) + 12 (12 / 0) |
| `x_remove_thousands_separators` | 14 (14 / 0) | `numbers.x_strip_thousands` + `x_remove_thousands_separators` | 11 (11 / 0) + 4 (4 / 0) |
| `x__has_symbol_table` | 21 (20 / 1) | `symbols.x__symbol_table_on_disk` | 21 (20 / 1) |
| `x__symbol_locale` | 22 (21 / 1) | `symbols.x_symbol_locale` | 22 (21 / 1) |
| `x__symbol_name` | 9 (9 / 0) | `symbols.x_symbol_name` | 9 (9 / 0) |
| `x__symbol_namer` | 19 (19 / 0) | `symbols.x_symbol_namer` | 19 (19 / 0) |
| `x__both_numbers` | 10 (10 / 0) | same | 10 (10 / 0) |
| `x_iter_number_speech_segments_mode` | 35 (31 / 4) | same | 35 (31 / 4) |
| `x_inject_number_mode` | 39 (39 / 0) | same | 39 (39 / 0) |
| `x_iter_number_speech_segments_language` | 16 (13 / 3) | same | 16 (13 / 3) |

- **Verbatim moves:** same mutant count, same killed count, same survivors under their new names.
- **Split functions:** `_translate_number`'s 47 were 44 on the piece computation and 3 on the break loop. After: the same 44 in `number_pieces` (same survivor), the same 3 on the loop, and 9 new glue mutants on the `number_pieces(raw, mode, group_size, name_of)` call (each argument `None` or dropped, and `pieces = None`). `remove_thousands_separators`'s 14 were 3 on the mode test and 11 on the `sub` call. After: the same 11 in `strip_thousands`, the same 3, and 1 glue mutant (`strip_thousands(None)`). All 10 glue mutants are killed.
- **Survivors, all present on `41dc50d` and unchanged by the move:**
  - `symbols.x__symbol_table_on_disk__mutmut_7` (`"_"` → `"XXXX"`) and `symbols.x_symbol_locale__mutmut_15` (`"XX_XX"`): equivalent, recorded in `7c67961`.
  - `numbers.x_number_pieces__mutmut_22` (was `x__translate_number__mutmut_22`), `in "+-"` → `in "XX+-XX"`: equivalent. `token[0]` is one character of a number token, a digit or a sign, never `X`.
  - `x_iter_number_speech_segments_mode__mutmut_1`, `_4`, `_34`, `_35`: the initial `previous_was_number = False` → `None`, and `preceding_text = ""` → `"XXXX"` or `None` after a number. Equivalent. `None` is as falsy as `False`. After a number the next segment is always text, because two matches never touch, and the text branch sets `preceding_text` before the number branch reads it. The initial `"XXXX"` does not end with `"."`.
  - `x_iter_number_speech_segments_language__mutmut_11`, `_13`, `_14`: the `!= "default"` test is changed. Equivalent in context, because `inject_number_language` returns before calling it when the number language is `"default"`.
  - These 7 were not listed in `e81b278` (see **Baseline** above). The function bodies are unchanged by this phase, so they are outside its scope.
- **Ruling (Task 6):** mutmut injects an import of its trampoline into `numbers.py`, which made Guard A fail mutmut's stats run. Guard A now skips only under mutmut (`abc92df`).
