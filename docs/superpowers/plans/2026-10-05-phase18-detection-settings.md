# Phase 18 Detection Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- Give the five language detection keys of `autoLanguageSwitching` one reader and writer, `DetectionSettingsService`.
- Have the detector, the main driver and the Unicode panel go through it. The driver learns about timing changes by subscribing; the panel no longer calls the synth.
- Write down why `WVLangChangeCommand` is not a `LangChangeCommand`, why it has `isDefault`, and why installTasks turns NVDA's automatic language switching off.

**Architecture:**
- New module `synthDrivers/WorldVoice/languageDetection/settings.py`: `DETECTION_CONFSPEC`, `SCRIPT_CONFIG_KEYS`, the frozen `DetectionSettings`, `DetectionSettingsService` and the singleton `detection_settings`. The service is also the repository: it reads and writes the config section itself and notifies subscribers (Observer). There is no separate repository class, unlike `pipeline/settings.py`'s `ConfigPipelineRepository` + `PipelineSettingsService`.
- `languageDetection/__init__.py` still imports no `config`; it gets the service injected.
- Docstring, comment and guard tests for the command contract.

**Tech Stack:** Python 3.11; pytest; ruff 0.16.

**Spec:** `docs/superpowers/specs/2026-10-05-phase18-detection-settings-design.md`

## Global Constraints

- Never edit `driver/<Engine>/driver/` or `driver/sonic`. This phase touches no engine wrapper.
- Config key names, defaults and every user-visible behavior stay the same.
- `git add` explicit paths only (`-f` for files under the ignored `docs/`). Never stage `docs/superpowers/finish_task.md`, `refactor-cleanup.md`, `refactor.md` or anything under `storage/`.
- Commits end with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Tab indentation, line length 110, `ruff format`.
- Full suite `python3 -m pytest tests -q` (baseline 1698), the lint gate in `tests/test_hygiene_guards.py`, the ruff total (baseline 39) and `ruff format --check addon --extend-exclude addon/synthDrivers/WorldVoice/driver/sonic`.

## Review Focus

1. **Refresh only on timing changes.** `refresh_language_detection` calls `order_move_to_start_register`, which reorders NVDA's filters. Saving the panel without changing the timing must not call it. Task 4 tests the listener; Task 5 tests that the panel's save reports `"timing"` only when it changed.
2. **Teardown order.** `"detection settings unsubscribe"` runs before `"language detection unregister"`, and a construction that fails after subscribing still unsubscribes (Task 4).
3. **Snapshot per sequence.** The detector reads settings once per call, not once per character. The existing detector assertions must hold unchanged (Task 3).
4. **The panel's partial save.** A disabled script choice is not written. `update(script_language=…)` merges and does not replace the mapping (Tasks 2 and 5).
5. **Entry-point import test.** `tests/test_runtime_composition.py` executes the real `__init__.py` with stubbed subpackages; the new `languageDetection.settings` import needs its own stub (Task 3, where the driver first imports it).

---

### Task 1: Document the language command contract (§5.2, N6)

**Files:**
- Create: `tests/test_speech_command_contract.py`
- Modify: `addon/synthDrivers/WorldVoice/_speechcommand.py`, `addon/installTasks.py`

- [ ] **Step 1: Failing tests.**
  - Stub `speech.commands` the way NVDA defines it: `SynthCommand`, `SynthParamCommand(SynthCommand)`, `LangChangeCommand(SynthParamCommand)`, `IndexCommand(SynthCommand)` that stores `index`. Load `_speechcommand.py` by file path under these stubs (use `StubModules`).
  - Assert:
    - `issubclass(WV, SynthParamCommand)` and not `issubclass(WV, LangChangeCommand)`;
    - `WV(None).isDefault`, `WV("").isDefault` are true and `WV("zh").isDefault` is false;
    - the class docstring mentions `speech/speech.py`, `speech/manager.py`, `isDefault` and `installTasks`.
  - Parse `installTasks.py`. The comment lines directly above `config.conf["speech"]["autoLanguageSwitching"] = False` must mention `WVLangChangeCommand`.
- [ ] **Step 2: Run** → the docstring and comment assertions FAIL; the subclass and `isDefault` assertions pass, since they characterize the current code.
- [ ] **Step 3: Implement.**
  - Write the `WVLangChangeCommand` docstring per spec §5. Cite `ref/nvda` (HEAD `1406f9f8a`): `speech/speech.py:1178-1180`, `speech/languageHandling.py:60-62`, `speech/manager.py:366-369`, `speech/manager.py:95-105`.
  - Replace the installTasks comment `# For a first-time install, set a default configuration value.` with the reason from spec §5.
- [ ] **Step 4: Run** the new test and the full suite → PASS.
- [ ] **Step 5: Commit** `docs: explain why WorldVoice language commands bypass NVDA's language switching`.

---

### Task 2: `DetectionSettingsService`

**Files:**
- Create: `addon/synthDrivers/WorldVoice/languageDetection/settings.py`, `tests/test_detection_settings.py`

- [ ] **Step 1: Failing tests.** Load the module by file path with `StubModules`: `config.conf`, plus `logHandler.log` whose `error` records its calls. Cover:
  - `get()` maps the five keys: `ignore_numbers`, `script_language == {"Latin": …, "Han": …, "Arabic": …}`, `timing`. `script_language` rejects item assignment (`TypeError`).
  - `update(ignore_numbers=True, script_language={"Han": "zh"})` writes those two keys only and leaves the Latin and Arabic keys as they were. Record the writes with a dict subclass whose `__setitem__` logs the key.
  - Writing a value equal to the stored one writes nothing and notifies no one, and returns the current settings.
  - `update(script_language={"Klingon": "tlh"})` raises `KeyError` and writes nothing, even when other fields are given too.
  - A listener receives `(settings, frozenset({"timing"}))` after a timing change, and `frozenset({"ignore_numbers", "script_language"})` after those two change.
  - A failing listener is logged once and the next listener still runs. `subscribe` twice notifies once; `unsubscribe` of an unknown listener does nothing.
  - `DETECTION_CONFSPEC` equals the five old confspec entries copied verbatim from `__init__.py:63-67`. `SCRIPT_CONFIG_KEYS` equals the old table.
- [ ] **Step 2: Run** → FAIL (module missing).
- [ ] **Step 3: Implement** per spec §1.
  - Module docstring: the only reader and writer of the detection keys.
  - `import config` and `from logHandler import log` at the top, as `pipeline/settings.py` does.
  - `get()` builds `script_language` as `types.MappingProxyType`.
  - `update()` validates every script name before reading or writing. It compares each given value with `get()`, writes the changed config keys, then calls `get()` again and notifies `(settings, frozenset(changed_fields))`.
  - Wrap each listener call in `except Exception` with `log.error("WorldVoice: detection settings listener failed", exc_info=True)`. This is not a blind except: it logs (BLE001 is not raised for handlers that log with `exc_info`; confirm with the lint gate).
  - `detection_settings = DetectionSettingsService(lambda: config.conf)`.
- [ ] **Step 4: Run** the new tests, the full suite and the lint gate → PASS.
- [ ] **Step 5: Commit** `refactor: add a single reader and writer for language detection settings`.

---

### Task 3: The detector reads the service

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/languageDetection/__init__.py`, `tests/detector_harness.py`, `tests/test_language_detector.py`; and, so the commit leaves the driver working, the detector construction in `addon/synthDrivers/WorldVoice/__init__.py` with `tests/test_worldvoice_lifecycle.py` (providers `{"settings", "language"}`) and the entry-point stub in `tests/test_runtime_composition.py` (moved here from Task 4)

- [ ] **Step 1: Tests first.**
  - `detector_harness.load_language_detection` also loads `languageDetection/settings.py`. Add stub `config` and `logHandler` modules; `config.conf` is the harness `conf`, now with `DetectLanguageTiming` too. Expose `env.settings_module` and `env.settings = settings_module.DetectionSettingsService(lambda: env.conf)`.
  - `make_detector` passes `settings=env.settings` instead of `conf_provider=`. The `switching(env)` helper and every existing assertion stay unchanged: writes to `env.conf` must still reach the detector.
  - New test: a counting wrapper around `env.settings` sees exactly one `get()` for one `add_detected_language_commands([...])` call over text that needs several lookups (`"中1中1"` with `ignoreNumbers` on). Likewise one `get()` for one `process_for_spelling` call.
- [ ] **Step 2: Run** → FAIL (`settings` is an unexpected keyword).
- [ ] **Step 3: Implement** per spec §2.
  - The constructor takes `*, settings, language`; delete `_conf_provider` and `_switching`. `SCRIPT_CONFIG_KEYS` stays until Task 5, because the Unicode panel still reads it from this module.
  - `find_language_for_script(script, current_language, settings=None)`: when `settings` is None, use `self._settings.get()`. A configured language comes from `settings.script_language.get(script)`.
  - `_language_for_character(character, current_language, base_language, settings)`.
  - `add_detected_language_commands` and `process_for_spelling` take one snapshot at the start, next to `self._language()`.
  - `tests/test_pipeline_structure.py:21` still passes: `__init__.py` must not import `config` or `.settings`.
- [ ] **Step 4: Run** the detector tests, the full suite and the lint gate → PASS.
- [ ] **Step 5: Commit** `refactor: let the language detector read one settings snapshot per sequence`.

---

### Task 4: The driver subscribes to timing changes

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/__init__.py`, `tests/test_driver_ui_hooks.py`, `tests/test_worldvoice_lifecycle.py`

- [ ] **Step 1: Failing tests.**
  - `tests/test_driver_ui_hooks.py`: put a `detection_settings` into the exec'd driver's globals, a stub whose `get()` returns `SimpleNamespace(timing=<conf value>)` read from the fixture's `conf`. Then:
    - the existing refresh tests run through it unchanged;
    - `_on_detection_settings(settings, frozenset({"timing"}))` refreshes (register and reorder for `"before"`);
    - `_on_detection_settings(settings, frozenset({"ignore_numbers", "script_language"}))` records no call;
    - `_detectLanguageTiming()` returns the stub's timing.
  - `tests/test_worldvoice_lifecycle.py`: add a `detection_settings` stub to the construction environment that records `"detection subscribed"` and `"detection unsubscribed"` (the fake `LanguageDetector`'s `{"settings", "language"}` providers check already came in Task 3). Assert:
    - after a successful construction and `terminate()`, the unsubscribe happens before the filter unregister. Record the unregister through the `filter_speechSequence` stub;
    - every failing construction has as many unsubscribes as subscribes.
  - The `tests/test_runtime_composition.py` entry-point stub for `languageDetection.settings` already came in Task 3.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** per spec §3.
  - Extend Task 3's import to `from .languageDetection.settings import DETECTION_CONFSPEC, detection_settings`.
  - Confspec: `"autoLanguageSwitching": {**DETECTION_CONFSPEC, <the three KeepMainLocale* entries unchanged>}`.
  - Add `"detection settings unsubscribe"` to `_TEARDOWN_ORDER` directly before `"language detection unregister"`.
  - In the `LanguageDetector` step:
    - the detector is already constructed with `settings=detection_settings` (Task 3);
    - after registering `"language detection unregister"`, subscribe `self._on_detection_settings` and register its unsubscribe.
  - `_detectLanguageTiming()` returns `detection_settings.get().timing`.
  - `_on_detection_settings(self, settings, changed)`: refresh only when `"timing" in changed`. Give it a one-line docstring with the reason (refresh reorders NVDA's filters).
  - Update the `refresh_language_detection` docstring.
- [ ] **Step 4: Run** the full suite and the lint gate → PASS.
- [ ] **Step 5: Commit** `refactor: refresh language detection when its timing setting changes`.

---

### Task 5: The Unicode panel goes through the service

**Files:**
- Modify: `addon/globalPlugins/WorldVoice/speechSettingsDialog.py`, `tests/test_unicode_panel.py`; create `tests/test_detection_settings_guards.py`

- [ ] **Step 1: Failing tests.**
  - `tests/test_unicode_panel.py::build`: the exec'd environment gets a real `DetectionSettingsService(lambda: conf)` from `env.settings_module` as `detection_settings`, and a listener that records its `changed` sets. Its `config` stub has no `autoLanguageSwitching` access path: make `config.conf` an object whose `__getitem__` raises, so any direct read fails. The service gets the dict through its own provider. The synth stub keeps recording attribute sets and any `refresh_language_detection` call.
    - The existing choice, selection and saved-value assertions stay unchanged.
    - The timing test becomes: after `onSave`, the listener saw `"timing"` in `changed` exactly when the timing changed, and `built.synth.events == []` in both cases.
  - `tests/test_detection_settings_guards.py`:
    - the five key names (regex on the quoted literals) occur in add-on sources only in `synthDrivers/WorldVoice/languageDetection/settings.py`. Reuse the `addon_sources()` skip rule from `tests/test_role_guards.py`;
    - `speechSettingsDialog.py` contains neither `refresh_language_detection` nor `SCRIPT_CONFIG_KEYS`; delete the leftover `SCRIPT_CONFIG_KEYS` from `languageDetection/__init__.py`;
    - `languageDetection/__init__.py` contains no `SCRIPT_CONFIG_KEYS`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** per spec §4.
  - `from synthDrivers.WorldVoice.languageDetection.settings import detection_settings`.
  - In `makeSettings`, `settings = detection_settings.get()`; use `settings.ignore_numbers` and `settings.timing`. Store `settings` as `self._detection` for `_add_script_choice`, which reads `self._detection.script_language[script]`.
  - `onSave`: a single `detection_settings.update(ignore_numbers=…, script_language={…enabled choices…}, timing=…)`.
  - Keep the `getSynth().name == "WorldVoice"` checks as they are.
  - Run `ruff format` on the touched files.
- [ ] **Step 4: Run** the full suite, the lint gate, the ruff total and the format check → PASS.
- [ ] **Step 5: Commit** `refactor: save the Unicode detection panel through the detection settings service`.

---

Final verification:

```bash
python3 -m pytest tests -q
ruff check addon --extend-exclude 'addon/synthDrivers/WorldVoice/driver/sonic' --statistics
ruff format --check addon --extend-exclude 'addon/synthDrivers/WorldVoice/driver/sonic'
grep -rn 'config.conf\["WorldVoice"\]' addon --include=*.py | grep -v '/driver/[A-Za-z0-9]*/driver/'
git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver'
```

Expected:
- the suite passes;
- the ruff total is at most 39;
- the format check passes;
- `config.conf["WorldVoice"]` appears 4 times in `speechSettingsDialog.py` and once in the main driver (`engine`);
- the driver directory shows no diff.
