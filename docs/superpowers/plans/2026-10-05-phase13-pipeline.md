# Phase 13 Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- Give every `speak()` step one context-based contract and make voice lookups name-only (C9).
- Inject `LanguageDetector`'s globals.
- Collapse the duplicated break-insertion and regex-scan loops.
- Read the log config once per stage call.
- Delete `SplitCommand` and the dead `Voice` branch.

**Architecture:**
- `SpeechContext.voice_name_for_language` replaces `voice_for_language`.
- `pipeline/__init__.py` gains `_insert_between` and `_split_by`.
- `LanguageDetector` gets `conf_provider` and `language` callables.
- Characterization tests are written first against today's behavior, then kept unchanged through the refactor.

**Tech Stack:** Python 3.11; pytest with `tests/nvda_stubs.StubModules`; ruff.

**Spec:** `docs/superpowers/specs/2026-10-05-phase13-pipeline-design.md`

## Global Constraints

- Never edit `driver/<Engine>/driver/` or `driver/sonic`. The ruff scope excludes `addon/synthDrivers/WorldVoice/driver/*/driver` and `addon/synthDrivers/WorldVoice/driver/sonic`.
- User-visible behavior must not change: voice switching, number language and mode, pauses, language detection, spelling.
- Characterization tests (Task 1) keep their assertions unchanged after Task 1's commit. Only their construction helpers may change, for new signatures.
- `git add` explicit paths only. Never stage the `docs/superpowers/finish_task.md` deletion or `refactor.md`.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Full suite: `python3 -m pytest tests -q` (baseline 1580).
- Lint gate: `ruff check … --select F401,F821,BLE001,I001` → 0, and `ruff format --check addon`.

## Review Focus

1. **A language with no voice.** `voice_name_for_language` returns `None` or `""`. Both dedupe and `lang_cmd_to_voice` must fall back to the default voice name exactly as before. Task 2 tests it.
2. **`LangChangeCommand(None)` after a switch.** Dedupe treats it as the default voice. `lang_cmd_to_voice` looks up the default voice's *language*, which may map to a role voice; that existing quirk must be preserved. Task 2 tests it.
3. **Number-mode `.` spacing.** Cases: a number directly followed by `.`, text ending in `.` before a number, consecutive numbers separated only by `.`, and `.` at the very start or end. Task 1 pins these and Task 4 must keep them.
4. **Detector reading the language per call, not at construction.** A language change between two `speak()` calls must be seen. Task 3 tests it.
5. **An empty string item in a sequence.** It goes through `_split_by`-based stages and `item_wait_factor`; the output must match today's for `""`. Task 1 pins it.

---

### Task 1: Characterization tests

**Files:**
- Create: `tests/test_language_detector.py`, `tests/test_pipeline_filters.py`

**Interfaces:**
- Produces: the helper `make_detector(module, languages, symbols, conf, language)` in `tests/test_language_detector.py`. It is the only place the constructor is called, and Task 3 edits it.

- [ ] **Step 1: Write `tests/test_language_detector.py`.** The loader uses `stub_modules`:
  - stub package `detector_test_worldvoice` at `WORLDVOICE`, and subpackage `.languageDetection` at `WORLDVOICE / "languageDetection"`;
  - `config` with `conf = {"WorldVoice": {"autoLanguageSwitching": {...}}}`, built from a dict the test controls;
  - `speech.commands` with simple `LangChangeCommand(lang)`, `IndexCommand`, `SynthCommand` and `SynthParamCommand` classes;
  - `synthDriverHandler` with `getSynth=lambda: synth`, where `synth` is a `SimpleNamespace(language=...)` the test controls;
  - import `detector_test_worldvoice.languageDetection`.

  Before writing assertions, read `languageDetection/__init__.py`, `languageDetection/scripts.py` and the `SCRIPT_LANGUAGES`/`SCRIPT_CONFIG_KEYS` tables. Pick inputs whose expected output you can derive by hand from those tables: for example, a Han character with a CJK config key, a Latin word, digits, and a symbol in a stub `speechSymbols.symbols` with `mode=1`.

  Tests:
  - `add_detected_language_commands`:
    - a Latin+Han mixed string yields text and `WVLangChangeCommand` in the right places;
    - digits follow `ignoreNumbersInLanguageDetection` True and False;
    - a mode-1 symbol switches to its own language and uses its replacement;
    - an incoming `LangChangeCommand("ja")` resets the base language, and `LangChangeCommand(None)` restores the synth language;
    - non-string commands pass through as the same object.
  - `process_for_spelling`:
    - with `locale=None` it uses the synth language;
    - with an explicit locale, spaces and digits stay in the default language, and a Han run switches.
  - `find_language_for_script`:
    - a configured candidate wins when available;
    - an unavailable configured value falls back to the first available candidate;
    - no candidate returns the current language.
  - `test_language_is_read_per_call`: change `synth.language` between two calls; the second call uses the new value.

  `make_detector(module, languages, symbols, conf, language)` mutates the stubs. `conf` is the dict behind `config.conf`; `language` is a callable that the `getSynth` stub's `language` property reads. It returns `module.LanguageDetector(languages, symbols)`.
- [ ] **Step 2: Write `tests/test_pipeline_filters.py`** using `load_pipeline_module` and `punctuation_settings` from `test_pipeline_punctuation_pause`. Set fields on the settings object as the existing tests do.
  - `item_wait_factor`:
    - `[]` → `[]`; `["a"]` → `["a"]`;
    - `["a", "b", cmd, "c", "d"]` → breaks only between adjacent strings;
    - every inserted break is the same object (`is`);
    - `["", "b"]` behaves as today (assert today's output).
  - `number_wait_factor`:
    - `["1", " ", "2", "a", "3"]`: blanks are removed first, then a break goes only between adjacent number strings.
  - `inject_number_language`:
    - `ctx.number_language="de"`, `language="en"`, with `voice_name_for_language`/`voice_for_language` resolving to distinct names or instances;
    - `"a1b2"` → today's sequence.
  - `inject_number_mode` for `"value"`, `"number"` and `"pair"` (pair with and without pause) on:
    - `"12.5"`, `"-1234"`, `"v1.2"`, `"a. 3"`, `"3."`, `".5"`, `"1.2.3"`, `""`.
    - Compute expectations by running today's code once while writing the test, then hard-code them.
  - `inject_chinese_space_pause`: `"中 文 abc 中 文"` with a wait factor > 0 → today's sequence; with 0 → unchanged.
  - `_split_punctuation_segments`: `"a, b,, 12,500. c"` → today's segments.
  - Keep the context construction in one helper `ctx(module, **fields)`; Task 2 changes the field name there only.
- [ ] **Step 3: Run** both files → PASS against the current code. These tests pin current behavior, so failing first is not expected. Ledger that.
- [ ] **Step 4: Commit** `test: pin language detection and pipeline filter behavior`.

---

### Task 2: Name-only voice lookup and one context contract

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/context.py`, `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (`deduplicate_language_command`, `lang_cmd_to_voice`), `addon/synthDrivers/WorldVoice/__init__.py` (`speak`, `speech_context`)
- Test: `tests/test_pipeline_stages.py`, `tests/test_runtime_composition.py:~425-440`, `tests/test_worldvoice_pipeline_settings.py`, `tests/test_pipeline_filters.py` (`ctx` helper), create `tests/test_pipeline_voice_lookup.py`

**Interfaces:**
- Produces:
  - `SpeechContext.voice_name_for_language: Callable[[str], str | None]`, defaulting to `lambda language: None`;
  - `lang_cmd_to_voice(speechSequence, ctx) -> Iterator`.

- [ ] **Step 1: Failing tests** in `tests/test_pipeline_voice_lookup.py`, using `load_pipeline_module`:

```python
def voice(name, language):
	return SimpleNamespace(name=name, language=language)

def context(module, names, default):
	return module.SpeechContext(supports_roles=True, language=default.language, number_language="default",
		default_voice=default, voice_name_for_language=names.get)

def test_dedupe_keeps_only_real_voice_switches(monkeypatch):
	module, settings = load_pipeline_module(monkeypatch, punctuation_settings(0))
	en = voice("A:en", "en")
	ctx = context(module, {"en": "A:en", "de": "A:de", "fr": None}, en)
	L = module.LangChangeCommand
	result = list(module.deduplicate_language_command(["x", L("de"), "y", L("fr"), "z", L(None), "w", L("en")], ctx))
	assert [getattr(c, "lang", c) for c in result] == ["x", "de", "y", "fr", "z", "w"]

def test_lang_cmd_to_voice_selects_names_and_falls_back(monkeypatch):
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	en = voice("A:en", "en")
	ctx = context(module, {"en": "R:en-role", "de": "A:de"}, en)
	L = module.LangChangeCommand
	result = list(module.lang_cmd_to_voice([L("de"), "a", L("xx"), L(None)], ctx))
	assert result == [module.SelectVoice("A:de"), "a", module.SelectVoice("A:en"), module.SelectVoice("R:en-role")]

def test_filters_do_not_create_voice_instances(composition):
	# real VoiceManager; build a ctx from a synth-like speech_context and run dedupe over many languages;
	# assert len(manager._instanceCache) is unchanged
```

  Write the last test against the composition fixture (`from test_runtime_composition import composition`) with the real manager:

```python
def test_filters_do_not_create_voice_instances(composition, monkeypatch):
	c = composition
	c.engine("ok")
	manager = c.create()
	pipeline = importlib.import_module(c.module.__package__ + ".pipeline")
	before = dict(manager._instanceCache)
	ctx = pipeline.SpeechContext(supports_roles=True, language="en", number_language="default",
		default_voice=manager.defaultVoiceInstance, voice_name_for_language=manager.getVoiceNameForLanguage)
	list(pipeline.deduplicate_language_command(["a", pipeline.LangChangeCommand("zh"), "b"], ctx))
	assert manager._instanceCache == before
```

  If importing the real pipeline package under the composition stubs fails on missing NVDA modules, add the missing stubs in this test with `stub_modules`, as `test_pipeline_punctuation_pause.load_pipeline_module` does, and load `pipeline/__init__.py` there. The assertion stays the same.
- [ ] **Step 2: Run** → FAIL (`voice_name_for_language` is an unexpected field).
- [ ] **Step 3: Implement.**
  - `context.py`: rename the field and type: `voice_name_for_language: Callable[[str], str | None] = lambda language: None`.
  - `deduplicate_language_command`:

```python
	default_name = voice_name = ctx.default_voice.name
	current_language = default_language = ctx.language
	for command in speechSequence:
		if isinstance(command, (LangChangeCommand, WVLangChangeCommand)):
			if command.lang == current_language:
				continue
			if command.lang is None:
				new_name = default_name
				current_language = default_language
			else:
				new_name = ctx.voice_name_for_language(command.lang) or default_name
				current_language = command.lang
			if new_name == voice_name:
				continue
			voice_name = new_name
			yield command
		else:
			yield command
```

    Keep the docstring and update it to say "voice" rather than "voice instance".
  - `lang_cmd_to_voice(speechSequence, ctx)`:

```python
	for cmd in speechSequence:
		if isinstance(cmd, (LangChangeCommand, WVLangChangeCommand)):
			lang = cmd.lang or ctx.default_voice.language
			yield SelectVoice(ctx.voice_name_for_language(lang) or ctx.default_voice.name)
		else:
			yield cmd
```

  - Main driver:
    - `speech_context` passes `voice_name_for_language=manager.getVoiceNameForLanguage`;
    - `speak()` computes `ctx = self.speech_context()` once after the detection step and passes it to both calls: `lang_cmd_to_voice(speechSequence, ctx)`.
  - Update existing tests: `test_pipeline_stages.test_number_language_wraps_numbers_for_worldvoice_only` (names instead of instances), the `test_runtime_composition` exec of `lang_cmd_to_voice`, `test_worldvoice_pipeline_settings` (the context dict keys), and the `ctx` helper in `tests/test_pipeline_filters.py`. Assertions keep their expected outputs.
- [ ] **Step 4: Run** the full suite and the lint gate → PASS.
- [ ] **Step 5: Commit** `refactor: look up voices by name in the pipeline and pass one context to every speak step`.

---

### Task 3: Inject the detector's config and language

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/languageDetection/__init__.py`, `addon/synthDrivers/WorldVoice/__init__.py`
- Test: `tests/test_language_detector.py` (`make_detector` only), `tests/test_worldvoice_lifecycle.py` (the `LanguageDetector` stub signature), create `tests/test_pipeline_structure.py`

**Interfaces:**
- Produces: `LanguageDetector(availableLanguages, speechSymbols=None, *, conf_provider, language)` and `SynthDriver._detectLanguageTiming() -> str`.

- [ ] **Step 1: Failing tests.**
  - `tests/test_pipeline_structure.py`: the `languageDetection/__init__.py` AST imports contain neither `config` nor `synthDriverHandler`.
  - Change `make_detector` to call `module.LanguageDetector(languages, symbols, conf_provider=lambda: conf, language=language)` and drop the `config`/`synthDriverHandler` stubs from the loader.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
  - `__init__` stores `self._conf_provider` and `self._language`.
  - Add a private `_switching()` helper returning `self._conf_provider()["WorldVoice"]["autoLanguageSwitching"]`, and use it at both config sites.
  - Replace both `getSynth().language` with `self._language()`.
  - Remove the two imports.
  - Main driver constructs the detector with `conf_provider=lambda: config.conf, language=lambda: self.language`.
  - Add:

```python
	def _detectLanguageTiming(self):
		return config.conf["WorldVoice"]["autoLanguageSwitching"]["DetectLanguageTiming"]
```

    Use it in `speak()` and `detect_language_timing()`.
  - Update the lifecycle `LanguageDetector` stub to accept `**providers`.
- [ ] **Step 4: Run** the full suite and the lint gate → PASS. The characterization assertions must not change.
- [ ] **Step 5: Commit** `refactor: give the language detector its config and language instead of reaching for NVDA globals`.

---

### Task 4: `_insert_between` and `_split_by`

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py`
- Test: `tests/test_pipeline_structure.py` (append)

- [ ] **Step 1: Failing guard** (append):

```python
def test_one_break_insertion_and_one_regex_scan():
	source = PIPELINE.read_text(encoding="utf-8")
	assert "_insert_BreakCommand_between_number" not in source and "previousious" not in source
	assert source.count(".finditer(") == 1
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**

```python
_MISSING = object()


def _insert_between(speechSequence, should_break, break_cmd):
	"""Yield speechSequence with break_cmd between each adjacent pair that should_break accepts."""
	previous = _MISSING
	for current in speechSequence:
		if previous is not _MISSING:
			yield previous
			if should_break(previous, current):
				yield break_cmd
		previous = current
	if previous is not _MISSING:
		yield previous


def _split_by(regex, text):
	"""Yield ("text", str) for the non-empty parts between matches and ("match", Match) for each match."""
	pos = 0
	for match in regex.finditer(text):
		if match.start() > pos:
			yield ("text", text[pos : match.start()])
		yield ("match", match)
		pos = match.end()
	if pos < len(text):
		yield ("text", text[pos:])
```

  - `item_wait_factor`: after the wait-factor check, `yield from _insert_between(speechSequence, lambda a, b: isinstance(a, str) and isinstance(b, str), BreakCommand(wait_factor))`. Keep a one-line docstring.
  - `number_wait_factor`:

```python
yield from _insert_between(
	_remove_space(speechSequence),
	lambda a, b: isinstance(a, str) and isinstance(b, str) and bool(_NUMBER_RE.match(a)) and bool(_NUMBER_RE.match(b)),
	BreakCommand(wait_factor),
)
```

    Delete `_insert_BreakCommand_between_number`.
  - `iter_number_speech_segments_language`:

```python
	for kind, value in _split_by(number_re, item):
		if kind == "text":
			yield value
			continue
		num_lang = number_language if number_language != "default" else current_lang
		yield WVLangChangeCommand(num_lang)
		yield value.group()
		yield WVLangChangeCommand(current_lang)
```

  - `iter_number_speech_segments_mode`:

```python
	previous_was_number = False
	preceding_text = ""
	for kind, value in _split_by(number_re, item):
		if kind == "text":
			if previous_was_number and value[0] == ".":
				yield " "
			yield value
			preceding_text = value
			continue
		if preceding_text.endswith("."):
			yield " "
		yield from _translate_number(value.group(), mode, translate_table, pair_pause)
		previous_was_number = True
		preceding_text = ""
```

  - `inject_chinese_space_pause` inner loop: `for kind, value in _split_by(_CH_SPACE_RE, item): yield value if kind == "text" else pause_cmd`. Write it as an if/else that yields.
  - `_split_punctuation_segments`: `for kind, value in _split_by(regex, text): yield ("text", value) if kind == "text" else ("punct", value.group())`. Again write it as an if/else.
- [ ] **Step 4: Run** the full suite (the characterization tests must pass unchanged) and the lint gate → PASS.
- [ ] **Step 5: Commit** `refactor: insert pauses and scan text through one helper each`.

---

### Task 5: Log reads and dead code

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/pipeline/__init__.py` (`_run_logged`), `addon/synthDrivers/WorldVoice/_speechcommand.py`, `addon/synthDrivers/WorldVoice/compat/commands.py`
- Test: `tests/test_pipeline_structure.py` (append), `tests/test_legacy_speech_commands.py`, and `_run_logged` tests if they exist (grep `_run_logged` in tests)

- [ ] **Step 1: Failing guards** (append):
  - `_speechcommand.py` has no `SplitCommand`;
  - `compat/commands.py`'s AST has no `ImportFrom` with `module == "driver"` at level 2;
  - `_run_logged`'s body contains `config.conf["WorldVoice"]["log"]` exactly once. Count with `ast.unparse` of the function.

  In `tests/test_legacy_speech_commands.py`:
  - drop the `Voice` items from the two sequences that contain them, and their expected `SelectVoice`s;
  - add `test_normalizer_passes_voice_objects_through_unchanged`: an object that is not a recognized command is yielded as itself. This replaces the deleted branch's coverage with the new contract.
  - If the `legacy` fixture imports `.driver` only for `Voice`, keep it; the fixture may still load `driver`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**

```python
def _run_logged(label, fn, speechSequence, settings, ctx):
	debug = config.conf["general"]["loggingLevel"] == "DEBUG"
	section = config.conf["WorldVoice"]["log"]
	recording = section["enable"]
	if not ((debug or recording) and section[label]):
		return fn(speechSequence, settings, ctx)
	...  # rest unchanged
```

  - Delete `SplitCommand`, and `SynthCommand` from the import if it becomes unused.
  - `compat/commands.py`: delete the `Voice` import and branch, and `SelectVoice` from the import if unused.
- [ ] **Step 4: Run** the full suite and the lint gate → PASS.
- [ ] **Step 5: Commit** `refactor: read the log section once and drop SplitCommand and the Voice normalizer branch`.

---

Final verification:

```bash
python3 -m pytest tests -q
ruff check addon --exclude 'addon/synthDrivers/WorldVoice/driver/*/driver' --exclude 'addon/synthDrivers/WorldVoice/driver/sonic' --select F401,F821,BLE001,I001
ruff format --check addon
git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver' addon/synthDrivers/WorldVoice/driver/sonic
```
