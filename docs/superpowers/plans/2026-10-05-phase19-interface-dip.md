# Phase 19 Interface and DIP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- Guard `cancel` and `pause` after `terminate` the way `speak` is guarded.
- Give the voice settings repository the synth's own name, and turn `shared_section` into a query without a blind except.
- Delete dead code: the unreachable `_get_voice` branch, `getVoiceInstanceForLanguage`, `EngineSession.replace_adapter` / `list_voices`, the second `ready()` check.
- Keep one list of voice parameter names, and derive the `voices` confspec from it.
- Inject the voice manager's policy dependencies from the composition root, with one `ParameterConsistency`.
- Register every driver cleanup right after its resource exists.
- Give engine discovery a Null Object logger.

**Architecture:**
- No new module.
- Constants:
  - `runtime/settings.py` gains `PARAMETER_NAMES`;
  - `configRepository.py` gains `VOICE_CONFSPEC`;
  - `compat/engineAdapter.py` gains `APPLY_ORDER`.
- The driver's `_initialize` builds one `ParameterConsistency` and passes it, `conf_provider` and `get_language` to `VoiceManager`. `voiceManager.py` stops importing `config` and `languageHandler`.

**Tech Stack:** Python 3.11; pytest; ruff 0.16.

**Spec:** `docs/superpowers/specs/2026-10-05-phase19-interface-dip-design.md`

## Global Constraints

- Never edit `driver/<Engine>/driver/` or `driver/sonic`. This phase touches no engine wrapper (`driver/<Engine>/__init__.py`); `driver/__init__.py` (the shared `Voice` base) is in scope.
- The Neural plugin contract stays: `tests/test_plugin_voice_contract.py` passes, and no deleted name occurs in `ref/Neural`.
- Config key names, stored values and every user-visible behavior stay the same. The two deliberate exceptions are in the spec: `cancel`/`pause` after terminate no longer raise (§1), and voices loaded during startup with parameter consistency on read the main synth's section like later voices (§2).
- `git add` explicit paths only (`-f` for files under the ignored `docs/`). Never stage `docs/superpowers/finish_task.md`, `refactor-cleanup.md`, `refactor.md` or anything under `storage/`.
- Commits end with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Tab indentation, line length 110, `ruff format`.
- Before deleting behavior, add a characterization test that passes on the current code.
- Verification after every task:
  - the full suite `python3 -m pytest tests -q` (baseline 1725);
  - the lint gate in `tests/test_hygiene_guards.py`;
  - the ruff total, at most 39: `ruff check addon --extend-exclude 'addon/synthDrivers/WorldVoice/driver/sonic' --statistics`;
  - `ruff format --check addon --extend-exclude addon/synthDrivers/WorldVoice/driver/sonic`.

## Review Focus

1. **Startup parameter load (Task 4).** With parameter consistency on, `shared_section` now returns the main synth's section during construction. Check that `load` still falls back per key on invalid values, and that a missing section still yields the voice's own values.
2. **Teardown registration timing (Task 8).** `"task manager shutdown"` must be registered before `bridge.start()`; failing constructions must still release exactly what they acquired.
3. **Manager injection (Task 5).** The repository and the manager share one `ParameterConsistency`; no test silently relies on the removed `config` import in `voiceManager.py`.
4. **Confspec (Task 6).** `rate`/`pitch`/`volume` spec strings are unchanged byte for byte; the reason the `__many__` spec is inert in NVDA is written next to it.
5. **Protocol trim (Task 3).** `EngineAdapter` keeps every member `EngineSession` uses.

---

### Task 1: Guard `cancel` and `pause` after terminate (N1)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/__init__.py`, `tests/test_worldvoice_lifecycle.py`

- [ ] **Step 1: Failing test.** `test_entry_points_are_silent_after_terminate`: build the driver through `_construction_environment(None, changes)`, call `terminate()`, then `speak([])`, `cancel()`, `pause(True)`. None may raise.
- [ ] **Step 2: Run** → FAIL (`AttributeError: 'NoneType' object has no attribute 'cancel'`).
- [ ] **Step 3: Implement.** Add `if self._terminated: return` at the top of `cancel` and `pause`.
- [ ] **Step 4: Run** the test and the full suite → PASS.
- [ ] **Step 5: Commit** `fix: let cancel and pause do nothing after the driver terminates`.

---

### Task 2: Delete the unreachable voice lookups (N4)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/__init__.py`, `addon/synthDrivers/WorldVoice/voiceManager.py`, `tests/test_voice_settings_transaction.py`, `tests/test_voice_manager_structure.py`

- [ ] **Step 1: Characterization test.** In `tests/test_voice_settings_transaction.py`, use the `_synth_settings_class` harness (it already compiles `_get_voice`) with a `languageHandler` stub in its environment. Assert two cases:
  - `_voice is None` → `_get_voice()` returns `manager.getVoiceNameForLanguage(<stub language>)`;
  - `_voice` set → it returns `manager.defaultVoiceName`.

  Run → PASS on current code.
- [ ] **Step 2: Guard test.** Add `"getVoiceInstanceForLanguage"` to `FORBIDDEN["synthDrivers/WorldVoice/voiceManager.py"]`. Run → FAIL.
- [ ] **Step 3: Implement.**
  - `_get_voice`: return the name directly when `_voice is None`.
  - Delete `VoiceManager.getVoiceInstanceForLanguage`.
  - Before deleting, `grep -rn getVoiceInstanceForLanguage addon tests ref/Neural` must show only the definition.
- [ ] **Step 4: Run** the full suite and the ruff total → PASS (RUF015 drops by one).
- [ ] **Step 5: Commit** `refactor: drop the voice lookups nothing can reach`.

---

### Task 3: Trim `EngineSession` and its adapter protocol (N5)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/runtime/session.py`, `tests/test_runtime_session.py`, `tests/test_f4_engine_session.py`, `tests/runtime_harness.py`, `tests/test_voice_manager_structure.py`

- [ ] **Step 1: Rewrite the reopen tests on current code first.**
  - `test_replace_adapter_changes_source_and_reapplies` becomes `test_reopen_changes_source_and_reapplies`. Activate, `close()`, `open()`, then assert:
    - a new `source_id`;
    - `(open_count, close_count) == (2, 1)`;
    - `activate` returns True and applies again.
  - `test_replace_core_reapplies_same_snapshot` becomes `test_reopen_reapplies_same_snapshot`: after `close()` + `open()`, the next `activate` writes the same voice and parameters again.
  - Drop the `session.list_voices()` line from `test_capability_and_metadata_queries_do_not_activate`.
  - `runtime_harness.py:424` uses `adapter.list_voices()`.
  - Run → PASS.
- [ ] **Step 2: Guard test.** Add `"synthDrivers/WorldVoice/runtime/session.py": ["def replace_adapter", "def list_voices", "notification_source"]` to `FORBIDDEN`. Run → FAIL.
- [ ] **Step 3: Implement.**
  - Delete `EngineSession.replace_adapter` and `EngineSession.list_voices`.
  - Delete `notification_source` and `list_voices` from the `EngineAdapter` Protocol. Give it a docstring: it is what a session needs during playback; `VoiceManager` builds and configures the concrete `LegacyEngineAdapter` itself (`open`, `list_voices`, `notification_source`, `configure_completion`, `configure_segment_events`).
  - The `EngineSession` docstring says "opens or closes".
  - `grep -rn "replace_adapter\|\.list_voices" addon tests ref/Neural` shows only adapter-level calls.
- [ ] **Step 4: Run** the full suite → PASS.
- [ ] **Step 5: Commit** `refactor: keep only what a playback session uses on the engine session`.

---

### Task 4: Name the synth's speech section without asking NVDA (N2)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/mainLocalePolicy.py`, `addon/synthDrivers/WorldVoice/configRepository.py`, `addon/synthDrivers/WorldVoice/__init__.py`, `tests/test_main_locale_policy.py`, `tests/test_voice_config_repository.py`, `tests/voice_binding_harness.py`, `tests/test_runtime_composition.py`, `tests/test_worldvoice_lifecycle.py`

- [ ] **Step 1: Characterization tests (pass on current code).** In `tests/test_main_locale_policy.py`:
  - disabled → `None`;
  - enabled + section → the section;
  - enabled + no synth section under `speech` → `None`;
  - enabled with an `AggregatedSection`-like `speech` stub whose `__getitem__` raises `KeyError` and whose `get` returns the default → `None`.

  Use the current call form, `shared_section(lambda: "WorldVoice")`. Run → PASS.
- [ ] **Step 2: Failing tests.**
  - Switch the tests to the new form `shared_section("WorldVoice")`.
  - Repository tests construct with `ConfigVoiceSettingsRepository(conf, "WorldVoice")`.
  - Delete the tests whose input no longer exists: the `unavailable` lines in `test_shared_section_only_when_enabled_and_available`, `test_main_synth_lookup_exception_falls_back_to_voice` and `test_main_synth_lookup_does_not_swallow_keyboard_interrupt`.
  - Lifecycle: the `ConfigVoiceSettingsRepository` stub records its arguments. After construction the name argument is `"WorldVoice"`, and the `getSynth` stub raises if called.
  - Add a source test: `mainLocalePolicy.py` has no `except`.
  - Run → FAIL.
- [ ] **Step 3: Implement** per spec §2.
  - `shared_section(synth_name: str)` with `.get` lookups and a docstring line: the section does not exist before NVDA first saves this synth.
  - `ConfigVoiceSettingsRepository(conf, synth_name: str, parameters=None)`.
  - Driver: `ConfigVoiceSettingsRepository(config.conf, self.name)`.
  - Update `voice_binding_harness.py` and `test_runtime_composition.py:269` to pass the string.
- [ ] **Step 4: Run** the full suite and the lint gate → PASS.
- [ ] **Step 5: Commit** `refactor: give the voice repository the synth's own name instead of NVDA's current synth`.

---

### Task 5: Inject the voice manager's policy dependencies (N8)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/voiceManager.py`, `addon/synthDrivers/WorldVoice/__init__.py`, and the tests that build a manager: `tests/test_f4_voice_state.py`, `tests/test_role_presenter.py`, `tests/test_voice_manager_roles.py`, `tests/test_voice_settings_transaction.py`, `tests/test_worldvoice_lifecycle.py`, `tests/test_runtime_composition.py`, `tests/runtime_drain_integration_harness.py`, `tests/test_voice_manager_structure.py`

- [ ] **Step 1: Failing tests.**
  - Add `init_policies(manager, config)` to `tests/test_f4_voice_state.py`. It calls `manager._init_policies(lambda: config.conf, lambda: "en")`. Every bare `manager._init_policies()` goes through it.
  - The composition `create`, the drain harness and the two lifecycle constructions pass `conf_provider=` and `get_language=`. Composition tests that reached the config stub through `c.module.config` use the fixture's `c.config`.
  - Lifecycle: the fake `VoiceManager` takes the new keywords and records `parameter_consistency`. The repository stub records `parameters`. Assert the two are the same object, and that it is a `ParameterConsistency` from the environment.
  - Guard: `voiceManager.py` imports neither `config` nor `languageHandler` (AST over `Import`/`ImportFrom`).
  - A default-voice test: with `get_language=lambda: "zh"`, a manager over `en` and `zh` voices picks the `zh` voice as default.
  - Run → FAIL.
- [ ] **Step 2: Implement** per spec §6.
  - Signature: `conf_provider`, `get_language` required; `parameter_consistency`, `roles` optional.
  - `_init_policies(conf_provider, get_language, *, roles=None, parameter_consistency=None)` stores `self._get_language`.
  - `_getDefaultVoiceSpec` calls `self._get_language()`.
  - Delete the two imports.
  - Driver: `from .mainLocalePolicy import ParameterConsistency`. Build `parameters = ParameterConsistency(lambda: config.conf)` next to the repository and pass it to both. Pass `conf_provider=lambda: config.conf` and `get_language=languageHandler.getLanguage` to the manager.
  - Lifecycle environment: add `ParameterConsistency` and `languageHandler` stubs.
- [ ] **Step 3: Run** the full suite → PASS.
- [ ] **Step 4: Commit** `refactor: inject the voice manager's config and language from the composition root`.

---

### Task 6: One list of voice parameter names (N7)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/runtime/settings.py`, `addon/synthDrivers/WorldVoice/mainLocalePolicy.py`, `addon/globalPlugins/WorldVoice/rolePresenter.py`, `addon/synthDrivers/WorldVoice/compat/engineAdapter.py`, `addon/synthDrivers/WorldVoice/configRepository.py`, `addon/synthDrivers/WorldVoice/__init__.py`, `tests/test_role_presenter.py`
- Create: `tests/test_voice_parameter_guards.py`

- [ ] **Step 1: Failing tests** in `tests/test_voice_parameter_guards.py`:
  - `runtime.settings.PARAMETER_NAMES == ("rate", "pitch", "volume", "inflection", "rateBoost")`;
  - `set(engineAdapter.APPLY_ORDER) == set(PARAMETER_NAMES)` and `APPLY_ORDER[0] == "rateBoost"`;
  - `set(configRepository.VOICE_CONFSPEC) == {name for name, _, _ in VOICE_PARAMETERS}`;
  - `rate`/`pitch`/`volume` equal `"integer(default=50,min=0,max=100)"`;
  - `rateBoost == "boolean(default=False)"`, `variant == "string(default=default)"`;
  - the driver's AST has `"__many__": dict(VOICE_CONFSPEC)` under `voices`;
  - `mainLocalePolicy.py` and `rolePresenter.py` do not contain `PARAMETER_NAMES = (`.

  Load modules with the existing harnesses (`runtime_harness.rt`, `load_config_repository`, `compat` fixture). Run → FAIL.
- [ ] **Step 2: Implement** per spec §5.
  - `rolePresenter.py` imports `from synthDrivers.WorldVoice.runtime.settings import PARAMETER_NAMES`.
  - `tests/test_role_presenter.py::load_presenter` registers `synthDrivers`, `synthDrivers.WorldVoice` and `synthDrivers.WorldVoice.runtime` as path-only packages (`StubModules.package`), so that the real `runtime/settings.py` is imported.
  - Put a comment above `VOICE_CONFSPEC` explaining two things: NVDA does not expand `__many__` for aggregated sections (`config/__init__.py:1194`), so this spec documents the stored keys; the values WorldVoice writes satisfy it.
  - Driver: `"voices": {"__many__": dict(VOICE_CONFSPEC)}`.
- [ ] **Step 3: Run** the full suite → PASS.
- [ ] **Step 4: Commit** `refactor: keep the voice parameter names and their confspec in one place`.

---

### Task 7: One spelling for the speech section (N9)

**Files:**
- Modify: `addon/globalPlugins/WorldVoice/speechSettingsDialog.py`, `tests/test_ui_structure.py`

- [ ] **Step 1: Failing guard:** `speechSettingsDialog.py` does not contain `["speech"]["WorldVoice"]`. Run → FAIL.
- [ ] **Step 2: Implement:** `config.conf["speech"][synth.name]["voice"] = name`.
- [ ] **Step 3: Run** the full suite → PASS (existing role panel tests keep passing).
- [ ] **Step 4: Commit** `refactor: name the main voice's speech section the same way twice`.

---

### Task 8: Register driver cleanups as resources come up (N11)

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/__init__.py`, `tests/test_worldvoice_lifecycle.py`, `tests/test_assembly_structure.py`, `tests/test_runtime_composition.py`

- [ ] **Step 1: Rewrite the teardown error test on current code first.**
  - Give `_construction_environment` a `close_error` option: the bridge's `close` raises it after recording.
  - `test_terminate_cleanup_logs_errors_but_lets_interrupts_through` builds the driver through the environment, with an `nvdaLog` that records errors, and keeps its assertions:
    - `RuntimeError`: logged once as `("WorldVoice terminate: %s", "event bridge close")`, and the ledger still closes;
    - `KeyboardInterrupt`: propagates, nothing logged, the ledger not closed.
  - Run → PASS.
- [ ] **Step 2: Guard:** the driver source has no `_new_teardown` (`tests/test_assembly_structure.py`). Run → FAIL.
- [ ] **Step 3: Implement** per spec §8. The order of registration within the TaskManager step:
  1. ledger;
  2. bridge;
  3. task manager;
  4. `bridge.start(...)`.

  The voice manager registers right after its construction.

  `tests/test_runtime_composition.py::make_synth` built its teardown through `_new_teardown()` around real runtime objects; it now builds a `Teardown` from the driver's `_TEARDOWN_ORDER` and registers the four runtime cleanups the way `_initialize` does.
- [ ] **Step 4: Run** the lifecycle tests, then the full suite → PASS.
- [ ] **Step 5: Commit** `refactor: register each driver cleanup once its resource exists`.

---

### Task 9: Drop the second ready check and the null-logger helper

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/__init__.py`, `addon/synthDrivers/WorldVoice/engine/discovery.py`, `tests/test_plugin_voice_contract.py`, `tests/test_engine_discovery.py`

- [ ] **Step 1: Characterization tests (pass now):**
  - `Voice.voices(None) == []`;
  - a core without `availableVoices` → `[]`;
  - a core with voices → metadata per voice.
- [ ] **Step 2: Failing tests:**
  - `Voice.voices(core)` does not call `ready()`: a subclass whose `ready` raises still lists its voices;
  - discovery with `logger=None` still skips a broken manifest and reports through `logging.getLogger(<discovery module name>)` (pytest `caplog`);
  - discovery source has no `def _log`.
- [ ] **Step 3: Implement** per spec §9 and §10.
- [ ] **Step 4: Run** the full suite, the lint gate, the ruff total and the format check → PASS.
- [ ] **Step 5: Commit** `refactor: check engine readiness once and give discovery a real logger by default`.

---

Final verification:

```bash
python3 -m pytest tests -q
ruff check addon --extend-exclude 'addon/synthDrivers/WorldVoice/driver/sonic' --statistics
ruff format --check addon --extend-exclude 'addon/synthDrivers/WorldVoice/driver/sonic'
grep -rn "replace_adapter\|getVoiceInstanceForLanguage\|_new_teardown\|def _log" addon ref/Neural --include=*.py
git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/'
```

Expected:
- the suite passes;
- the ruff total is at most 39 (38 expected after Task 2);
- the format check passes;
- the grep shows nothing;
- no engine wrapper or inner driver changed.
