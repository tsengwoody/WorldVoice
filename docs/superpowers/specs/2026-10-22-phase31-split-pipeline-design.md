# Phase 31: split `pipeline/__init__.py`, with number lexing and symbol lookup in their own modules

Date: 2026-10-22.
Base: `master` `41dc50d`. Branch: `phase31-split-pipeline` (worktree `/workspace/WorldVoice-phase31`).
Flow: normal flow (DEVELOPMENT_WORKFLOW.md §3), one implementer, one final Fable 5.1 review.
Source: round-6 review `storage/refactor6.md` §1.1, §1.2, §8, §9 (N20, N21), §10, and §11 "階段 31".
Status: the user approved D1–D4 as recommended on 2026-10-22 (section 3). The smaller choices in section 13 are orchestrator defaults.

All line numbers refer to `41dc50d`. Unless a path says otherwise, it is under `addon/synthDrivers/WorldVoice/`. NVDA references are to `ref/nvda` at `7d25bc76e`.

## 1. Problem and goal

`pipeline/__init__.py` has 986 lines. It mixes five jobs (review §1.1):

- number lexing (`:37-52`, `:256-280`, `:435-446`);
- NVDA symbol-name lookup (`:97-139`, `:455-478`);
- nine stage functions and the three passes that `speak()` uses (`:143-853`);
- CSV stage logging (`:856-900`);
- the NVDA filter registry (`:903-986`).

The number lexing uses only `re`, `unicodedata` and `itertools`. Even so, a test can reach it only through `load_pipeline_module` (`tests/pipeline_harness.py:41-136`), which stubs the 10 NVDA imports at `:11-20`.

The symbol lookup also probes the file system on the speech path:

- `_has_symbol_table` calls `os.path.isfile` (`:107`).
- It is reached from `_symbol_locale` (`:122`), and `_symbol_namer` creates the only memo per stage run (`:463-464`).
- So every utterance repeats the probe for every language that has a voice locale. Probe, re-run for this spec: three runs of `inject_number_mode` over a zh/en sequence made 6 `isfile` calls on two paths.

Goals:

1. **`pipeline/numbers.py`.** It holds the one definition of a number and the cutting of a number into pieces. It imports only the standard library.
2. **`pipeline/symbols.py`.** It holds NVDA's symbol-name lookup. The symbols-table probe runs once per locale per NVDA run (D2).
3. **`pipeline/__init__.py`.** It keeps only the stages, the speak passes, stage logging and the `STAGES` registry. It shrinks to about 855 lines.
4. **Public names.** The moved names become public in their new modules. The tests use those names (D3).
5. **Dead code.** `_SENTENCE_END_RE` is deleted (N21).
6. **mutmut.** Both new modules are added to the mutmut `source_paths`.
7. **Guards.** Two structure guards keep the split in place.

Affected layers: only the core pipeline package (`pipeline/`), the test harness and tests, and `pyproject.toml`. No engine wrapper, no inner driver (`driver/<Engine>/driver/`), no UI module and no translation changes. Neural is untouched (`ref/Neural` does not import `pipeline`).

## 2. Non-goals

- Any change to what NVDA users hear or see, apart from the probe count in section 5. No new or changed strings, settings, config keys, panels or log keys.
- `pipeline/stageLog.py`. `_LogWriter`, `_run_logged` and `pl` stay in `__init__.py` (D1 = A).
- Narrowing `SpeechContext.default_voice` (D4). That is phase 32.
- Caching `speech.getCurrentLanguage()`, or caching names at the namer level. Review §10 rules out the namer-level cache. Section 5 explains why `getCurrentLanguage()` is not cached.
- Logic edits to any moved body, beyond these two:
  - the D3 renames;
  - pulling the piece computation out of `_translate_number` (section 4.1).
- Moving `_CH_SPACE_RE`, `_split_numbers`, `_both_numbers` or `NumberBreakCommand`. These belong to stages (section 4.4).
- Updating line references in older specs, plans or reviews. They are historical records.

## 3. Decisions

| # | Decision | By |
| --- | --- | --- |
| D1 | **A.** Make two modules: `numbers.py` (pure) and `symbols.py` (NVDA lookup). No `stageLog.py`. | Decided by the user (2026-10-22) |
| D2 | **A.** Cache `has_symbol_table`. The key is the locale; there is no invalidation (section 5). Do not cache `getCurrentLanguage()`. | Decided by the user (2026-10-22) |
| D3 | Every moved name is public in its new module. Tests import the public name from the module that defines it. `__init__.py` has no underscore aliases. | Decided by the user (2026-10-22) |
| D4 | Narrowing `SpeechContext.default_voice` belongs to phase 32. | Decided by the user (2026-10-22) |

## 4. Module boundaries

### 4.1 `pipeline/numbers.py` (new)

Module docstring: this module holds the one definition of a number and the rules for cutting one into spoken pieces. It imports only the standard library, so tests and mutmut can load it alone.

Imports: `re`, `unicodedata`, `collections.abc.Callable`/`Iterator`, `itertools.pairwise`. Nothing else.

| Current name | Current `file:line` | New public name | Notes |
| --- | --- | --- | --- |
| `_SYMBOLS` | `pipeline/__init__.py:37-39` | `SYMBOLS` | Moved verbatim, with its comment. |
| `_NUMBER_RE` | `:40-45` | `NUMBER_RE` | Verbatim. The comment's reference to the sign lookbehind stays. |
| `_NUMBER_TOKEN_RE` | `:46-47` | `NUMBER_TOKEN_RE` | Verbatim. Only `number_pieces` uses it. |
| `_DIGITS` | `:48` | `DIGITS` | Verbatim. Only `number_pieces` uses it. |
| `_THOUSANDS_RE` | `:49-52` | `THOUSANDS_RE` | Verbatim. Only `strip_thousands` uses it. |
| `_split_spaced_numbers` | `:256-280` | `split_spaced_numbers(text: str) -> Iterator[str]` | Body verbatim, except `_NUMBER_RE` becomes `NUMBER_RE`. |
| The piece computation in `_translate_number` | `:432-446` | `number_pieces(raw: str, mode: str, group_size: int, name_of: Callable[[str], str \| None]) -> list[str]` | New function. It contains `:435-446` verbatim and returns `pieces`. Value mode returns `[raw]` (from `:432-434`). The docstring takes the piece rules from `:426-429`. |
| The `sub` call in `remove_thousands_separators` | `:158` | `strip_thousands(text: str) -> str` | `return THOUSANDS_RE.sub(lambda match: match.group().replace(",", ""), text)`, the same expression. |

### 4.2 `pipeline/symbols.py` (new)

Module docstring: NVDA's name for a symbol in the locale of the voice that speaks it, and whether NVDA has a symbols table for a locale. The docstring states the cache rule from section 5.

Imports:
- standard library: `os`, `functools.lru_cache`, `collections.abc.Callable`;
- NVDA: `characterProcessing`, `globalVars`, `languageHandler`, `speech`.

There is no relative import.

| Current name | Current `file:line` | New name | Notes |
| --- | --- | --- | --- |
| `_has_symbol_table` | `pipeline/__init__.py:97-107` | `_symbol_table_on_disk(locale: str) -> bool` (private, undecorated) plus `has_symbol_table = lru_cache(maxsize=None)(_symbol_table_on_disk)` (public) | The body and docstring are verbatim. The docstring adds one sentence on the cache (section 5). It uses the call form, not `@lru_cache`, so mutmut still mutates the body (section 9). |
| `_symbol_locale` | `:110-130` | `symbol_locale(language: str \| None, voice_locale: str \| None = None) -> str` | Body verbatim. Its call at `:122` becomes `has_symbol_table(locale)`, the cached name. |
| `_symbol_name` | `:133-139` | `symbol_name(locale: str, symbol: str) -> str \| None` | Verbatim. |
| `_symbol_namer` | `:455-478` | `symbol_namer(voice_locale_for_language)` with the same return type | Body verbatim, but `_symbol_locale` and `_symbol_name` become `symbol_locale` and `symbol_name`. |

`_symbol_table_on_disk` is the only underscore name in either new module. Only `has_symbol_table` calls it. It exists so that mutmut can reach the probe (section 9). Tests never touch it.

### 4.3 Deleted

`_SENTENCE_END_RE` (`pipeline/__init__.py:55`, and the blank line at `:54`).

- It is dead. `grep -rn SENTENCE_END addon tests ref/Neural` finds only its definition.
- Its last reader was removed in `97d7187` ("fix: improve number parsing and speech segmentation", 2026-07-31).
- Review §9 N21 deleted it in a scratch worktree, and 680 related tests passed.

### 4.4 What stays in `pipeline/__init__.py`

Everything else stays, unchanged except for the call sites in section 4.5:

- **Module setup:**
  - `SpeechCmd`;
  - `pl` (`:34-35`), which `globalPlugins/WorldVoice/pipelineLog.py:10` imports;
  - `_CH_SPACE_RE` (`:53`), the private regex of the CJK-space stage;
  - `NumberBreakCommand` and `PunctuationBreakCommand` (`:58-63`);
  - `with_order_log` (`:66-83`) and `listable` (`:86-94`).
- **Stages:**
  - `speech_viewer` (`:143-144`);
  - `remove_thousands_separators` (`:147-160`);
  - `apply_speech_dictionaries` (`:164-169`);
  - `item_wait_factor` (`:218-228`);
  - `number_wait_factor` (`:292-310`);
  - `inject_number_language` (`:399-414`);
  - `inject_number_mode` (`:482-515`);
  - `inject_chinese_space_pause` (`:558-581`);
  - `inject_punctuation_pause` (`:620-748`).
- **Stage helpers:**
  - `_MISSING`, `_insert_between` and `_split_by` (`:172-201`);
  - `_both_text` and `_both_numbers` (`:204-214`);
  - `_remove_space` (`:231-253`) and `_split_numbers` (`:283-288`);
  - `_insert_number_breaks` (`:313-335`);
  - `remove_language_command` and `_insert_WVLangChangeCommand_between_number` (`:338-373`);
  - `iter_number_speech_segments_language` (`:376-395`);
  - `_translate_number` (`:417-452`), reduced to the shape in section 4.5;
  - `iter_number_speech_segments_mode` (`:518-540`) and `merge_consecutive_strings` (`:543-554`);
  - `_PUNCTUATION_RE_CACHE`, `_get_punctuation_regex` and `_split_punctuation_segments` (`:584-616`).
- **Speak passes:**
  - `deduplicate_language_command` (`:751-801`);
  - `lang_cmd_to_voice` (`:804-817`);
  - `inject_langchange_reorder` (`:820-853`).
- **Logging:** `_LogWriter` (`:856-876`), `_log_writer` (`:879`) and `_run_logged` (`:882-900`).
- **Registry:**
  - `_plain_breaks` (`:903-909`) and `_stage_handler` (`:912-924`);
  - `Stage` (`:927-942`), `STAGES` (`:946-956`) and `LOG_SWITCHES` (`:960`);
  - `order_move_to_start_register` and `order_move_to_end_register` (`:963-971`);
  - `register_stages` and `unregister_stages` (`:974-986`).

`_run_logged`, `_get_punctuation_regex` and `_split_punctuation_segments` stay private. Tests keep reaching them as they do today (section 7.3). The public API that the main driver imports does not change: `LOG_SWITCHES`, `deduplicate_language_command`, `inject_langchange_reorder`, `lang_cmd_to_voice`, `listable` and `order_move_to_start_register` (`__init__.py:37-44`). Neither does the one the UI imports (`LOG_SWITCHES`, `speechSettingsDialog.py:17`; `pl`, `pipelineLog.py:10`).

### 4.5 Edits inside `pipeline/__init__.py`

**Imports that leave:**
- `os` (`:1`), `unicodedata` (`:3`), `pairwise` (`:8`);
- `characterProcessing` (`:11`), `globalVars` (`:13`), `languageHandler` (`:14`), `speech` (`:15`).

Nothing else in the file uses them. `from speech.commands …` and `from speech.extensions …` (`:18-19`) stay, and they do not bind the name `speech`.

**Imports added:**
```python
from .numbers import NUMBER_RE, number_pieces, split_spaced_numbers, strip_thousands
from .symbols import symbol_namer
```

**Call sites:**
- `:158` becomes `yield strip_thousands(item)`.
- `:212-213` become `NUMBER_RE.fullmatch(...)`.
- `:286` becomes `yield from split_spaced_numbers(item)`.
- The defaults `number_re=_NUMBER_RE` at `:376` and `:524` become `NUMBER_RE`.
- `:494` becomes `namer = symbol_namer(ctx.voice_locale_for_language)`.
- The comment at `:497` says `symbols.symbol_locale` instead of `_symbol_locale`.

**`_translate_number`** keeps its signature, generator form and break rule:
```python
def _translate_number(raw, mode, group_size, number_pause, name_of) -> Iterator[SpeechCmd]:
	"""Speak one number match in *mode*: its pieces (numbers.number_pieces), with a number break
	between every two, even at pause 0, so each reaches the synth as an item of its own."""
	pieces = number_pieces(raw, mode, group_size, name_of)
	# One break instance per number, as the synth only reads its time.
	separator = NumberBreakCommand(number_pause)
	for index, piece in enumerate(pieces):
		if index:
			yield separator
		yield piece
```

## 5. The symbol-table cache (D2)

**What is cached:** `has_symbol_table(locale) -> bool`. The cache key is the `locale` string. That string is the output of `languageHandler.normalizeLanguage(voice_locale)` at `symbol_locale`, `:121-122`, so it is canonical, for example `"zh_TW"`. `maxsize=None` is safe because the keys come from the voice locales of the installed engines, a small finite set.

The cache also stores the guard's `False` for non-plain names (`:105-106`). That is harmless: the answer is the same either way.

**Why no invalidation is needed:**
- The probe's path is `globalVars.appDir/locale/<locale>/symbols.dic` (`:107`). NVDA sets `globalVars.appDir` once at startup, before any driver loads (`ref/nvda/source/nvda.pyw:41,56,59`).
- The directory is part of NVDA's own install. A new built-in locale arrives only with an NVDA update, and an update restarts NVDA, which re-imports the module with an empty cache.
- Add-ons cannot add a built-in table. They register their own symbol dictionary definitions (`characterProcessing.py:902-903`, "Add add-on symbols"), and `has_symbol_table` never considered those.
- NVDA makes the same assumption. It globs the same `{locale}` pattern once per run: `SymbolDictionaryDefinition.availableLocales` is a `cached_property` (`ref/nvda/source/characterProcessing.py:836-846`). The built-in definition with that path is at `:893-899`.

**Thread safety:** `functools.lru_cache` is thread-safe. A race at most computes the same `bool` twice.

**`speech.getCurrentLanguage()` is not cached.**
- It is `ref/nvda/source/speech/speech.py:313-325`. It calls `getSynth()`, reads `synth.language`, which is `availableVoices[self.voice].language` (`synthDriverHandler.py:253-254`), and reads `config.conf["speech"]["trustVoiceLanguage"]`. It then normalizes the result or falls back to `languageHandler.getLanguage()`.
- All of that is in memory, with no I/O, so one call costs microseconds.
- Its answer changes at runtime: the user can switch synth or voice, toggle "trust voice's language", or switch profile.
- It is already memoized per stage run per language by the namer's `locales` dict (`:463`, `:470-472`). It runs only when the voice locale has no table, or there is no voice locale (`:120-124`).
- Caching it would leave symbol names in the old language after a voice change (review §11 risk). The re-run probe in section 1 made 3 `getCurrentLanguage()` calls in 3 runs (en_US has no table), and that stays 3.

**Effect:** the probe in section 1 drops from 6 `isfile` calls to 2, one per locale.

## 6. Import direction

```
pipeline/__init__.py ──► pipeline/numbers.py   (stdlib only)
          │
          └────────────► pipeline/symbols.py   (stdlib + NVDA: characterProcessing, globalVars,
                                                languageHandler, speech)
```

- Neither new module imports the package, any sibling, or each other, so there is no cycle.
- `context.py`, `settings.py`, `scope.py` and `speech_dictionary.py` do not change.
- `symbols.py` imports the same NVDA modules `__init__.py` imports today, at the same time (when the package is imported), so NVDA's import order does not change.

**Name shadowing:** `numbers` is also a standard-library module name. It is shadowed only if the `pipeline/` directory itself is on `sys.path`, and it never is:
- `synthDrivers/WorldVoice/__init__.py:56-57` adds the add-on root;
- `engine/discovery.py:97-103` adds the parent of a driver package.

Absolute `import numbers` anywhere still gets the standard library. ruff's A005 (stdlib-module-shadowing) is not enabled: `pyproject.toml` has no `select`, so ruff uses its defaults minus the ignores (`tests/test_hygiene_guards.py:45-48`).

## 7. Test harness and test changes

### 7.1 `tests/pipeline_harness.py`

`load_pipeline_module` pops 19 module names before loading (`:43-64`). The review says 14. The pipeline package is then loaded with `load_source(..., register=True)` (`:134`).

- `spec_from_file_location` on an `__init__.py` gives the module a `__path__`. So `from .numbers import …` and `from .symbols import …` resolve through the normal import system to `WORLDVOICE/pipeline/numbers.py` and `symbols.py`. No loader change and no alias handling is needed. `context` and `speech_dictionary` already load this way.
- **Required change:** add `"synthDrivers.WorldVoice.pipeline.numbers"` and `"synthDrivers.WorldVoice.pipeline.symbols"` to the pop list.
  - Submodules imported this way go into `sys.modules` without monkeypatch, and they stay there after the test. That is why `context`, `scope` and `speech_dictionary` are already in the list.
  - Without the pop, the next test would reuse the previous `symbols` module. That module is bound to the previous test's `speech`, `globalVars` and `characterProcessing` stubs, and it keeps its filled cache. A test that patches the new stubs would then test the wrong objects.
  - `conftest.py:30-39` guards the same hazard for `runtime/completion.py`.
- The import system also sets the submodules as attributes of the package (`module.numbers`, `module.symbols`). Tests use those attributes (section 7.3), so the object under test is exactly the one the stages call.

### 7.2 Other loaders (no change)

- `tests/nvda_stubs.py:109` reads `STAGES` from `pipeline/__init__.py` with `ast`. `STAGES` stays.
- `tests/test_worldvoice_speak.py:101-104` deletes every `speak_test_worldvoice.*` module before it imports the real package. That covers the new submodules.
  - Its `speech` stub has no `getCurrentLanguage` (`:107`).
  - That is true today, and the move neither adds nor removes a call.
- These stub or alias `synthDrivers.WorldVoice.pipeline` without running `__init__.py`:
  - `tests/ui_harness.py:683`, `:779-780`, `:867`;
  - `tests/test_runtime_composition.py:600-621`;
  - `tests/test_pipeline_log.py:34-37`.
- `tests/mutation_support.py:24-29,50-59` names trampolines by file. `pipeline/numbers.py` maps to `addon.synthDrivers.WorldVoice.pipeline.numbers` with no edit.

### 7.3 Test edits

The review says 9 private names in 5 files. Verified with `grep -rnE` over `tests/`: **9 private names, in 3 files**.

| Name | Sites | After |
| --- | --- | --- |
| `_NUMBER_RE` | `test_pipeline_filters.py:144,150`; `test_pipeline_pause_properties.py:355,408,414,531,546,565,587` | `env.module.numbers.NUMBER_RE` |
| `_SYMBOLS` | `test_pipeline_pause_properties.py:313,440,693` | `env.module.numbers.SYMBOLS` |
| `_symbol_name` | `test_pipeline_nvda_symbols.py:30,49,230,247` | `module.symbol_name` (the fixture now returns `symbols`, see below) |
| `_symbol_locale` | `test_pipeline_nvda_symbols.py:67,119,230,247` | `module.symbol_locale` |
| `_has_symbol_table` | `test_pipeline_nvda_symbols.py:88` (and comment `:141`) | `module.has_symbol_table` |
| `_symbol_namer` | `test_pipeline_nvda_symbols.py:130,136` | `module.symbol_namer` |
| `_run_logged` | `test_pipeline_filters.py:725,742` | unchanged (stays private in `__init__.py`) |
| `_get_punctuation_regex` | `test_pipeline_filters.py:686` | unchanged |
| `_split_punctuation_segments` | `test_pipeline_filters.py:687` | unchanged. The review's list does not name it. |

The review missed a second coupling. **Tests reach the NVDA stubs through the pipeline module's attributes**, and those attributes disappear when the imports leave `__init__.py`:

- `test_pipeline_filters.py:512,527,611` use `env.module.speech`. They become `env.module.symbols.speech`.
- `test_pipeline_filters.py:540` uses `env.module.characterProcessing`. It becomes `env.module.symbols.characterProcessing`.
- `test_pipeline_pause_properties.py:442,443,449,654,655,670` use `….module.characterProcessing`. They become `….module.symbols.characterProcessing`.
- `test_pipeline_nvda_symbols.py:48,66,118,228,229,245,246`: the `module` fixture (`:23-26`) returns `load_pipeline_module(...)[0].symbols`.
  - After that, every `module.speech`, `module.characterProcessing` and `monkeypatch.setattr(module, "characterProcessing", …)` in the file addresses `symbols.py`. These lines need no other edit.
  - This matters for `:228` and `:245`, which replace the module attribute itself.

A miss fails loudly, not silently:
- Reading `env.module.speech` raises `AttributeError`.
- `monkeypatch.setattr` defaults to `raising=True`.

No `cache_clear()` fixture is needed, although review §1.2 asks for one. Each test loads a fresh `symbols` module after the section 7.1 pop, so each test gets a fresh cache.

Within one Hypothesis test, the examples share the function-scoped `env`, so they share the cache (`test_pipeline_pause_properties.py:17,21-23`). That is harmless, because the answer depends only on the locale and `appDir` is fixed at `REF/nvda/source` (`pipeline_harness.py:72`).

`test_pipeline_nvda_symbols.py:20` keeps its own `NUMBER_SYMBOLS`. It is an independent oracle for NVDA's names and does not import `SYMBOLS` (section 13, Q6). The harness stub `pipeline_harness.symbol_name` (`:13-18`) and the new `symbols.symbol_name` do not clash, because tests reach the real one only as a module attribute.

### 7.4 New tests

1. **Guard A**, `tests/test_pipeline_structure.py::test_number_lexing_imports_only_the_standard_library`.
   - It walks every `Import` and `ImportFrom` node in `pipeline/numbers.py` with `ast.walk`, so imports inside functions count too.
   - Each top-level module name must be in `sys.stdlib_module_names`.
   - No `ImportFrom` may have `level > 0`.
2. **Guard B**, `tests/test_pipeline_structure.py::test_pipeline_package_keeps_only_stages_logging_and_registry`.
   - The top-level `FunctionDef`, `ClassDef`, `Assign` and `AnnAssign` names of `pipeline/__init__.py` include none of `SYMBOLS`, `NUMBER_RE`, `NUMBER_TOKEN_RE`, `DIGITS`, `THOUSANDS_RE`, `SENTENCE_END_RE`, `split_spaced_numbers`, `number_pieces`, `strip_thousands`, `has_symbol_table`, `symbol_table_on_disk`, `symbol_locale`, `symbol_name` or `symbol_namer`. Each is checked both bare and with one leading underscore.
   - Its imports (`Import` names, and level-0 `ImportFrom` modules) include none of `os`, `unicodedata`, `characterProcessing`, `globalVars`, `languageHandler` or `speech`. `speech.commands` and `speech.extensions` are allowed.
   - `pipeline/symbols.py` has no `ImportFrom` with `level > 0`, so there is no cycle back into the package.
   - **Why this form:** the names catch a move that is undone or copied back. The imports catch symbol lookup or file probing that creeps back into the package. A check on "`re.compile` of a number pattern" (review §11 step 1) would have to recognize patterns, and would miss `_has_symbol_table` and `symbol_namer` coming back.
3. **Cache**, `tests/test_pipeline_nvda_symbols.py::test_symbol_tables_are_probed_once_per_locale`.
   - Setup:
     - patch `module.os.path.isfile` with a recording wrapper around the real one;
     - patch `module.speech.getCurrentLanguage` with a counting stub that returns `"en"`.
   - Run three times: `namer = module.symbol_namer({"zh": "zh-TW", "en": "en-US"}.get)`, then `namer("zh")("×")` and `namer("en")("×")`.
   - Assertions:
     - The recorded probes are exactly one each for `locale/zh_TW/symbols.dic` and `locale/en_US/symbols.dic`. Today the test would record 6.
     - The names equal what NVDA's tables give through the harness stub, unchanged.
     - `getCurrentLanguage` was called 3 times, once per run for `en_US`, which has no table. This pins that it is *not* cached.
   - It goes through `symbol_namer`, not `has_symbol_table` directly. So it also fails if `symbol_locale` calls the uncached `_symbol_table_on_disk` and skips the cache.

Existing tests keep pinning the per-run memo:
- `test_pipeline_nvda_symbols.py:122-137` checks that the voice locale is asked once per language per run;
- `test_pipeline_filters.py:607-619` checks one `getCurrentLanguage` per run and one lookup per symbol.

## 8. mutmut configuration

`pyproject.toml:38-47` `[tool.mutmut] source_paths`: add these two paths after `"addon/synthDrivers/WorldVoice/pipeline/__init__.py"`:
```toml
	"addon/synthDrivers/WorldVoice/pipeline/numbers.py",
	"addon/synthDrivers/WorldVoice/pipeline/symbols.py",
```
`pipeline/__init__.py` stays in the list: the stages are still core decision logic. No other mutmut key changes.

## 9. mutmut and decorated functions

mutmut 3.8.0 skips every decorated function except `@staticmethod` and `@classmethod`:
- `/usr/local/lib/python3.14/dist-packages/mutmut/mutation/file_mutation.py:325-335`;
- the decorators themselves are skipped at `:337-341`.

Written as `@lru_cache def has_symbol_table`, the probe's body would silently drop out of mutation testing. That would lose its 20 mutants (`7c67961`: `_has_symbol_table` 20 mutants, 1 equivalent survivor).

So section 4.2 wraps an undecorated function with a call at module level. mutmut puts its trampoline on `_symbol_table_on_disk`, and `lru_cache` wraps the trampoline. A fresh module per test (section 7.1) means a fresh cache under every mutant.

Module-level constants (`NUMBER_RE` and the others) are not mutated before or after. `e81b278` already records that. Oracle and table tests pin them.

## 10. Test plan

**Suite:**
- Baseline: `python3 -m pytest -q -p no:cacheprovider tests`, single process, under the memory guard (stop below 3 GB MemAvailable). Re-run for this spec on `41dc50d` in the worktree: **2343 passed, 0 skipped**.
- After the phase: **2346 passed, 0 skipped**. That is 2343 plus the two guards and the cache test in section 7.4.
- No existing test is removed, renamed or parametrized differently. The three edited files still collect 207, 29 and 45 tests (`test_pipeline_filters.py`, `test_pipeline_pause_properties.py`, `test_pipeline_nvda_symbols.py`). The last becomes 46.
- `test_pipeline_structure.py` goes from 1 test to 3.

**Checks:** `prek run --all-files` all Passed, `git diff --check` clean, and the §7 protected-path commands print nothing.

**mutmut, before and after.**
- Setup: scratch copies, at most 3 children, the memory guard, `mutants/` removed afterwards.
- Before: run on `41dc50d`. After: run on the branch head.
- Globs: confirm the names with `mutmut results` first. Prefix: `addon.synthDrivers.WorldVoice.pipeline.`

| Before (`pipeline.`) | After |
| --- | --- |
| `x__split_spaced_numbers*` | `numbers.x_split_spaced_numbers*` |
| `x__translate_number*` | `numbers.x_number_pieces*` + `pipeline.x__translate_number*` |
| `x_remove_thousands_separators*` | `numbers.x_strip_thousands*` + `pipeline.x_remove_thousands_separators*` |
| `x__has_symbol_table*` | `symbols.x__symbol_table_on_disk*` |
| `x__symbol_locale*` | `symbols.x_symbol_locale*` |
| `x__symbol_name*` | `symbols.x_symbol_name*` |
| `x__symbol_namer*` | `symbols.x_symbol_namer*` |
| `x__both_numbers*`, `x_iter_number_speech_segments_mode*`, `x_inject_number_mode*` | same names (bodies unchanged except `NUMBER_RE` and `symbol_namer`) |

Acceptance:
- A body moved verbatim has the same mutant count and the same killed count.
- The surviving mutants are the same, apart from renames. The known ones are:
  - `x__has_symbol_table__mutmut_7` becomes `x__symbol_table_on_disk__mutmut_7` (`"_"` → `"XXXX"`, equivalent, `7c67961`);
  - `x__symbol_locale__mutmut_15` becomes `x_symbol_locale__mutmut_15` (`"XX_XX"`, equivalent, `7c67961`).
- For the two split functions, the after-sum may differ from the before-count only by the glue lines (`return [raw]` against `yield raw`; the `strip_thousands` call). Every survivor on a glue line must be killed by a test or shown equivalent.
- No new timeout and no "suspicious" result.
- The plan's implementation notes record both tables.

**Behaviour equivalence.** There are no logic edits apart from the cache and the renames:

1. **Verbatim moves.** Every function body and constant in sections 4.1 and 4.2 moves verbatim, apart from the D3 renames of the names it references.
   - The reviewer checks this with `git diff --color-moved=plain --color-moved-ws=allow-indentation-change master...HEAD -- addon/`.
   - The moved blocks should show as moved. The only new lines should be the imports, the `number_pieces`/`strip_thousands` signatures and returns, the `_translate_number` glue and the cache wrapper.
2. **`number_pieces` with `_translate_number`.**
   - Value mode: `[raw]` yields `raw` with no separator, as `:432-434` does.
   - Other modes: the token loop is the same, and the list is built in full before the first `yield`, as it is today. So `name_of` is called in the same order and the same number of times.
   - The separator is built once per number, as at `:448`.
   - The one difference is that value mode now also builds one unused `NumberBreakCommand`. NVDA's `BreakCommand.__init__` only stores `time` (`ref/nvda/source/speech/commands.py:203-207`), so nothing can observe it.
   - `_translate_number` is still a generator, so laziness does not change.
3. **`strip_thousands`** is the same `re.sub` call with the same pattern and replacement.
4. **`has_symbol_table`.**
   - It is a pure function of `locale` once `appDir` is fixed and NVDA's `locale/` directory is unchanged (section 5). Caching changes how often it runs, not its answer.
   - `getCurrentLanguage()` still runs at the same points and the same number of times.
5. **Tests.** The full suite passes with the same count, and the pipeline's behavioural tests are not edited beyond attribute paths.
   - These cover stage outputs, symbol names against NVDA's real `characterProcessing`, Hypothesis properties P1–P10, and NVDA SSML.
   - Their assertions are unchanged.

## 11. What users notice, and Windows manual items

Users notice nothing. What they hear and see does not change, and there are no new strings, settings, panels or log keys. The only runtime difference is fewer `stat` calls on the speech path.

There are no Windows manual items beyond an optional smoke test, and no dedicated test build is needed. On the next packaged build:
1. Turn on number mode with a zh-TW voice and an English NVDA interface.
2. Read "2×3". It should still be spoken as 2, 乘以, 3.
3. Switch to an en voice. It should still say "times".

## 12. Risks

| Risk | Mitigation |
| --- | --- |
| The new submodules are missing from the harness pop list. Tests then share a stale `symbols` module, with the previous test's stubs and cache. | Section 7.1 change. Run the full suite in default order, and run each of the three edited files alone. |
| An edited test still reaches `speech` or `characterProcessing` through the package. | It fails loudly (`AttributeError`). Section 7.3 lists all 17 sites (`grep -rnE "module\.(speech|characterProcessing)\b|\"characterProcessing\"" tests/`, less the harness pop entry and stub-creation lines). |
| `@lru_cache` decorator syntax silently removes the probe from mutmut. | Use the call form (section 9). The after-run must list `x__symbol_table_on_disk__mutmut_*`. |
| `symbol_locale` calls the uncached function. | The cache test goes through `symbol_namer` (section 7.4, item 3). |
| `getCurrentLanguage()` gets cached too, so symbol names stay in the old language after a voice change. | It is a non-goal. The cache test pins 3 calls in 3 runs. |
| A transient I/O failure is cached as `False` for the rest of the run. That locale's symbols then fall back to NVDA's interface-language rule. | Accepted. NVDA's own `availableLocales` glob has the same property (`characterProcessing.py:836-846`). `os.path.isfile` already turns errors into `False` today. |
| An import cycle (`numbers`/`symbols` → package). | Guards A and B forbid relative imports in both new modules. |
| `numbers` shadows the standard-library module. | `pipeline/` is never on `sys.path` (section 6). The import is relative. |
| A mutmut glob mismatch makes the before/after comparison miss functions. | Confirm the names with `mutmut results` before the comparison (as in earlier phases). |
| The line-number references inside `__init__.py` docstrings go stale. | `has_symbol_table` keeps its `characterProcessing.py:893-901` reference unchanged. No `__init__.py` line numbers are quoted in code. |

## 13. Open questions

Decided by orchestrator with the recommended default; user may override before merge:

- **Q1: `is_number(text)` helper (review sketch §1.1).** Not added. `_both_numbers` keeps `NUMBER_RE.fullmatch` (`:212-213`). It is not in the approved scope, and it would change two lines that need no change.
- **Q2: cache form.** Use `has_symbol_table = lru_cache(maxsize=None)(_symbol_table_on_disk)`, not `@lru_cache` or `functools.cache` used as a decorator (section 9). `maxsize=None` because the keys are the finite set of voice locales.
- **Q3: helper constants.** `NUMBER_TOKEN_RE`, `DIGITS` and `THOUSANDS_RE` become public along with `SYMBOLS` and `NUMBER_RE`. This follows one rule: every moved name is public (D3). `_symbol_table_on_disk` is the only private name, because it is new and must not be called directly.
- **Q4: how tests reach the new modules.** Through the submodule that the loaded pipeline imported (`env.module.numbers`, `module.symbols`). They do not load `numbers.py` standalone, and they do not load `symbols.py` with its own four stubs (review §11 step 3). This way the tested object, its NVDA stubs and its cache are the ones the stages use. Guard A shows that `numbers.py` imports nothing a stub would have to provide.
- **Q5: `_CH_SPACE_RE`, `_split_numbers`, `_both_numbers`, `_translate_number`.** They stay in `__init__.py` and stay private. They are stage helpers over speech sequences or commands, not number lexing.
- **Q6: `test_pipeline_nvda_symbols.py:20` `NUMBER_SYMBOLS`.** It stays as an independent oracle and does not import `SYMBOLS`.

## 14. Task estimate

7 tasks, so no batches (fewer than 10). There is one final Fable 5.1 review, as every review in this flow uses Fable 5.1. Each task commits only when the suite is green.

1. **mutmut baseline** on `41dc50d` for the "before" column of section 10. Scratch copy, no commit. Record in the ledger.
2. **`numbers.py`.**
   - Write Guard A and see it fail, because the file is missing.
   - Move the section 4.1 names. Edit `__init__.py` as in section 4.5 (the numbers part).
   - Add `numbers` to the harness pop list. Edit the `_NUMBER_RE` and `_SYMBOLS` test sites.
   - Green: 2344. Commit.
3. **`symbols.py`, no cache yet.**
   - Move the section 4.2 names, with `has_symbol_table` as a plain alias of `_symbol_table_on_disk`.
   - Edit `__init__.py` as in section 4.5. Add `symbols` to the pop list.
   - Edit the section 7.3 symbol sites and the stub reach-through sites.
   - Green: 2344. Commit.
4. **Cache.** Write the cache test and see it fail (6 probes). Wrap with `lru_cache` (call form). Green: 2345. Commit.
5. **Dead code.** Write Guard B and see it fail on `_SENTENCE_END_RE`. Delete it. Green: 2346. Commit.
6. **mutmut.** Edit `source_paths` (section 8), run the after-run, and compare with task 1. Kill or justify every new survivor. Commit `pyproject.toml` and the plan's implementation notes.
7. **Full verification** (§7: pytest 2346/0, `prek run --all-files`, `git diff --check`, protected paths), then report.

Effort: about half a day.
- `pipeline/__init__.py` goes from 986 lines to about 855. That is −130, not the −250 to −300 in review §11.
- `numbers.py` is about 90 lines and `symbols.py` about 85.
- About 40 test lines change, plus about 60 new test lines.
