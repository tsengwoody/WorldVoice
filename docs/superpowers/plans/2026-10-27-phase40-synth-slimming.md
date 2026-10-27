# Phase 40 synth slimming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** Move the confspec assembly out of the synth `__init__.py` into `confspec.py` (`installConfspec(conf)`) and the number-language state into `voices/numberLanguageChoice.py` (`NumberLanguageChoice`), with no behaviour change.

**Architecture:** Each extraction is two commits: an edit commit that reshapes the code in place inside `__init__.py` (TDD), then a move commit that moves the reshaped top-level definition verbatim to its new module and passes an order-sensitive move check. A final commit adds import guards for both new modules.

**Tech Stack:** Python 3.11 floor (container 3.14), pytest, NVDA stubs in `tests/`, ruff 0.16.3 via prek.

**Spec:** `docs/superpowers/specs/2026-10-27-phase40-synth-slimming-design.md`

## Global Constraints

- No user-visible change: same `[WorldVoice]` keys, defaults and order; same number-language list, order and warning text `"WorldVoice: unknown number language %r, using %r"`.
- Out of scope: descriptors for `_get_x/_set_x`, `resolve_voices()`, any driver setting id or stored key change.
- Root `numberLanguage.py` unchanged (standard library only, `tests/test_pipeline_structure.py:72-83`).
- Naming (refactor9 §6.1, `tests/test_naming_layers.py` docstring): `confspec.py` is HOST (mixedCase, registered in `HOST`); `voices/numberLanguageChoice.py` is CORE (snake_case).
- `installConfspec(config.conf)` is called at module level in `__init__.py`, where the assignment is today.
- Moves (§3.2): move commits separate from edit commits; each passes the order-sensitive move check (script and results in the ledger); tests in a move commit change only path references.
- Never modify `driver/<Engine>/driver/`, `driver/sonic/`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py`; never add Neural; engine drivers stay independently installable.
- ruff pinned `0.16.3`; prek hooks must pass; never `--no-verify`.
- Commits: English `<type>: <summary>` with a body, no `Co-Authored-By`, explicit paths only; no push, no merge, no `git stash`.
- Tests: serial or ≤3 workers with the MemAvailable < 3 GB watchdog; `PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider` when mutating code to prove a test.
- Baseline: 3346 passed / 0 skipped.

## Review Focus

1. **Global plugin with another synth active:** importing `synthDrivers.WorldVoice.<sub>` (as `globalPlugins/WorldVoice/__init__.py:14` does) must install `config.conf.spec["WorldVoice"]`, or the Pipeline/Engine/Log panels fail. Task 1 asserts it in the real package import test (`tests/test_runtime_composition.py`).
2. **Stored locale hidden by a voice or engine change** survives NVDA's load/save and is listed last in `availableNumlans`; speech reads `"default"` until a voice offers it again. Existing `test_a_hidden_locale_survives_loading_and_saving_and_comes_back` plus Task 3's `test_a_hidden_locale_is_kept_and_listed_last`.
3. **Unknown stored value** (`"zz"`, a locale with no installed voice) reads as `"default"` with exactly one debug warning. Existing `test_an_unknown_number_language_reads_as_follow`, `test_a_locale_of_an_uninstalled_voice_is_refused_on_load`; Task 3's `test_a_refused_value_stores_follow`.
4. **Live manager reads:** the choice must read `languages`/`all_languages` on every call, not a copy taken at construction (voices change when engines are enabled or the keep-consistent settings change). Task 3's `test_the_choice_reads_the_manager_each_time`.
5. **Detector provider and profile switch:** the `LanguageDetector`'s `number_language` provider follows a later `_set_numlan` (profile switch through `loadSettings`). Existing `test_the_detector_reads_the_drivers_number_language`, updated in Task 3 to set the value through `_set_numlan`.

---

### Task 1: Reshape the confspec into `installConfspec(conf)` in place

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/__init__.py:69-86`
- Modify: `tests/nvda_stubs.py:56-66` (reader)
- Create: `tests/test_confspec.py`
- Modify: `tests/test_runtime_composition.py` (package import test, `:555-650`)

**Interfaces:**
- Produces: `installConfspec(conf) -> None` (top-level function in `__init__.py`, moved in Task 2); `tests/nvda_stubs.CONFSPEC_SOURCE` (path of the file defining it).

- [ ] **Step 1: Write the failing tests**

`tests/test_confspec.py::test_confspec_sections`: load `installConfspec` with `load_definitions(CONFSPEC_SOURCE, ["installConfspec"], owners)` where `owners` gives sentinel `DETECTION_CONFSPEC = {"a": "string(default=x)"}`, `PIPELINE_CONFSPEC = {"p": "integer(default=1)"}`, `LOG_SWITCHES = ("s1", "s2")`, `VOICE_CONFSPEC = {"rate": "integer(default=50)"}`; call it on `SimpleNamespace(spec={"speech": {}})`; assert:
```python
assert list(conf.spec) == ["speech", "WorldVoice"]
spec = conf.spec["WorldVoice"]
assert list(spec) == ["autoLanguageSwitching", "pipeline", "role", "engine", "log", "voices"]
assert spec["autoLanguageSwitching"] == {"a": "string(default=x)", "keepMainLocaleVoiceConsistent": "boolean(default=true)",
	"keepMainLocaleParameterConsistent": "boolean(default=false)", "keepMainLocaleEngineConsistent": "boolean(default=true)"}
assert spec["pipeline"] == {"p": "integer(default=1)"} and spec["pipeline"] is not owners["PIPELINE_CONFSPEC"]
assert spec["role"] == {} and spec["engine"] == {"__many__": "boolean(default=false)"}
assert spec["log"] == {"enable": "boolean(default=false)", "s1": "boolean(default=false)", "s2": "boolean(default=false)"}
assert spec["voices"] == {"__many__": {"rate": "integer(default=50)"}}
```
In `tests/test_runtime_composition.py`'s real package import test, keep the `config` stub object and assert after `load_source(...)`: `assert list(config_stub.conf.spec["WorldVoice"]) == ["autoLanguageSwitching", "pipeline", "role", "engine", "log", "voices"]`.

- [ ] **Step 2: Run to verify red**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_confspec.py`
Expected: FAIL, `installConfspec` not found by `load_definitions` (and `CONFSPEC_SOURCE` import error until Step 3 adds it). The package import assertion passes already (behaviour pinned before the reshape).

- [ ] **Step 3: Reshape in `__init__.py` and the stub reader**

Wrap the assignment unchanged in `def installConfspec(conf):` with `conf.spec["WorldVoice"] = {...}` and call `installConfspec(config.conf)` right after the definition. In `tests/nvda_stubs.py` add `CONFSPEC_SOURCE = WORLDVOICE / "__init__.py"` and make `_worldvoice_defaults` find the `Assign` to `conf.spec['WorldVoice']` inside the top-level `FunctionDef` named `installConfspec` of `CONFSPEC_SOURCE` (error text names `installConfspec`).

- [ ] **Step 4: Run to verify green, then the full suite**

Run: `python3 -m pytest -q -p no:cacheprovider tests/test_confspec.py tests/test_runtime_composition.py tests/test_naming_layers.py tests/test_detection_settings.py`, then the full suite with the watchdog.
Expected: all pass; full suite 3347 passed / 0 skipped.

- [ ] **Step 5: Commit** — `refactor: assemble the confspec in installConfspec` (paths: `__init__.py`, `tests/nvda_stubs.py`, `tests/test_confspec.py`, `tests/test_runtime_composition.py`).

### Task 2: Move `installConfspec` to `confspec.py`

**Files:**
- Create: `addon/synthDrivers/WorldVoice/confspec.py`
- Modify: `addon/synthDrivers/WorldVoice/__init__.py` (remove the function and the four owner imports; add `from .confspec import installConfspec`)
- Modify: `tests/nvda_stubs.py` (`CONFSPEC_SOURCE = WORLDVOICE / "confspec.py"`), `tests/test_naming_layers.py` (`SYNTH + "confspec.py"` in `HOST`)

**Interfaces:**
- Consumes: `installConfspec(conf)` from Task 1.
- Produces: `synthDrivers.WorldVoice.confspec.installConfspec(conf) -> None`.

- [ ] **Step 1: Move verbatim**: new module = short docstring, the four owner imports (`from .languageDetection.settings import DETECTION_CONFSPEC`, `from .pipeline.registry import LOG_SWITCHES`, `from .pipeline.settings import PIPELINE_CONFSPEC`, `from .voices.settingsRepository import VOICE_CONFSPEC`), then the function byte-identical. `__init__.py` keeps the call line in place.
- [ ] **Step 2: Run the move check** `scratchpad/p40/move_check.py --old addon/synthDrivers/WorldVoice/__init__.py --new addon/synthDrivers/WorldVoice/confspec.py --name installConfspec` against parent `HEAD` and the working tree (staged). Expected: `OK` (segment identical, new file = docstring + imports + segment, old file = parent minus segment with only import lines changed).
- [ ] **Step 3: Run tests**: targeted files of Task 1 plus the full suite. Expected: 3347 passed / 0 skipped. Without the `HOST` entry `test_every_add_on_module_has_a_layer` fails (red check).
- [ ] **Step 4: Commit** — `refactor: move installConfspec to confspec.py`; record the move-check command and output in the ledger.

### Task 3: Reshape the number-language state into `NumberLanguageChoice` in place

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/__init__.py:183`, `:198-250` (`_initialize`), `:469-509`
- Create: `tests/test_number_language_choice.py`
- Modify: `tests/test_worldvoice_speak.py:203-207`, `:356`; `tests/test_worldvoice_pipeline_settings.py:201`; `tests/test_worldvoice_lifecycle.py:174`, `:258`; any other harness whose environment runs `_initialize` or sets `_numlan`.

**Interfaces:**
- Produces: `NumberLanguageChoice(manager)` (top-level class in `__init__.py`, moved in Task 4), members exactly as spec §5.2: `is_storable(value) -> bool`, `stored` (property, str), `store(value) -> bool`, `spoken` (property, str), `listed_locales() -> list[str]`; `tests/test_number_language_choice.CHOICE_SOURCE`.
- Driver: `self._numberLanguageChoice` (None in `__init__`, built in `_initialize` right after `VoiceManager`).

- [ ] **Step 1: Write the failing unit tests** in `tests/test_number_language_choice.py`, loading the class with `load_definitions(CHOICE_SOURCE, ["NumberLanguageChoice"], {"FOLLOW": "default", "MAIN": "main"})`, `CHOICE_SOURCE = WORLDVOICE / "__init__.py"`, over `manager = SimpleNamespace(languages=("en", "zh_TW"), all_languages=("en", "zh_TW", "ja"))`:
  - `test_a_new_choice_follows_the_text`: `stored == spoken == "default"`, `listed_locales() == ["en", "zh_TW"]`.
  - `test_storable_values` (parametrized): `"default"`, `"main"`, `"en"`, `"ja"` → `store(v) is True` and `stored == v`.
  - `test_a_refused_value_stores_follow` (parametrized `"zz"`, `"fr"`): after `store("en")`, `store(v) is False`, `stored == "default"`.
  - `test_a_hidden_locale_is_kept_and_listed_last`: `store("ja")` → `stored == "ja"`, `spoken == "default"`, `listed_locales() == ["en", "zh_TW", "ja"]`.
  - `test_a_stored_locale_no_longer_installed_reads_as_follow`: `store("zh_TW")`, then `manager.all_languages = manager.languages = ("en",)` → `stored == "default"`, `spoken == "default"`, `listed_locales() == ["en"]`.
  - `test_the_choice_reads_the_manager_each_time`: `store("ja")`, then `manager.languages = ("en", "ja")` → `spoken == "ja"`, `listed_locales() == ["en", "ja"]`.
- [ ] **Step 2: Run to verify red**: `python3 -m pytest -q -p no:cacheprovider tests/test_number_language_choice.py` → FAIL (`NumberLanguageChoice` not defined in `__init__.py`).
- [ ] **Step 3: Implement** `class NumberLanguageChoice` as a top-level class at the end of `__init__.py` (after the `_PipelineSetting` loop), snake_case, docstring per spec; rewire the driver per spec §5.2 (forwards; `_set_numlan` logs only when `store` returns False; `_isStoredNumberLanguage` removed; `_numlanDisplayName` stays). Update the tests listed under Files: the speak harness builds `synth._numberLanguageChoice = NumberLanguageChoice(synth._voiceManager)` (class from `load_definitions`, or the environment) and replaces `synth._numlan = x` with `synth._set_numlan(x)` (or `choice.store(x)`); the lifecycle environment provides `"NumberLanguageChoice"`; `driver._numlan = "main"` becomes `driver._set_numlan("main")`.
- [ ] **Step 4: Run to verify green**: the new file, `tests/test_worldvoice_speak.py`, `tests/test_worldvoice_lifecycle.py`, `tests/test_worldvoice_pipeline_settings.py`, `tests/test_driver_ui_hooks.py`, `tests/test_naming_layers.py`; then full suite. Expected: 3347 + 13 new = 3360 passed / 0 skipped (count per the parametrization actually written; record it).
- [ ] **Step 5: Commit** — `refactor: keep the number-language state in NumberLanguageChoice`.

### Task 4: Move `NumberLanguageChoice` to `voices/numberLanguageChoice.py`

**Files:**
- Create: `addon/synthDrivers/WorldVoice/voices/numberLanguageChoice.py`
- Modify: `addon/synthDrivers/WorldVoice/__init__.py` (remove the class; add `from .voices.numberLanguageChoice import NumberLanguageChoice`)
- Modify: `tests/test_number_language_choice.py` (`CHOICE_SOURCE` path only); harnesses that loaded the class from `__init__.py` (path only)

**Interfaces:**
- Consumes: Task 3's class. Produces: `synthDrivers.WorldVoice.voices.numberLanguageChoice.NumberLanguageChoice`.

- [ ] **Step 1: Move verbatim**: new module = docstring, `from ..numberLanguage import FOLLOW, MAIN`, the class byte-identical.
- [ ] **Step 2: Move check** `move_check.py --old addon/synthDrivers/WorldVoice/__init__.py --new addon/synthDrivers/WorldVoice/voices/numberLanguageChoice.py --name NumberLanguageChoice` → `OK`.
- [ ] **Step 3: Run tests**: Task 3's targeted files, then the full suite. Expected: same count as Task 3.
- [ ] **Step 4: Commit** — `refactor: move NumberLanguageChoice to voices/numberLanguageChoice.py`; ledger entry.

### Task 5: Import guards for the two new modules, and full verification

**Files:**
- Modify: `tests/test_confspec.py`, `tests/test_number_language_choice.py`

- [ ] **Step 1: Write the guards**
  - `test_confspec_receives_conf`: AST of `confspec.py` has no `import config` / `from config import` and only relative `ImportFrom`s; `installConfspec` takes one parameter `conf`.
  - `test_the_choice_imports_only_the_number_language_values`: every import of `voices/numberLanguageChoice.py` is `from ..numberLanguage import FOLLOW, MAIN` (level 2, module `numberLanguage`).
- [ ] **Step 2: Prove they bite**: temporarily add `import config` to each module (`PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider`) → each guard FAILs; revert (`git diff` empty for addon/).
- [ ] **Step 3: Full verification** (DEVELOPMENT_WORKFLOW.md §7): full suite (expected Task 4 count + 2, 0 skipped), `prek run --all-files` all Passed, `git diff --check`, protected-path commands empty; `wc -l` of `__init__.py` before/after.
- [ ] **Step 4: Commit** — `test: guard the imports of confspec and NumberLanguageChoice`.
