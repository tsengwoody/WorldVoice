# Phase 44 Settings Infrastructure Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** `ConfigVoiceSettingsRepository` takes a conf provider like every other config reader, and one NVDA-free `Listeners` replaces the two settings services' hand-written listener lists.

**Architecture:** F9 swaps the repository's stored conf object for a zero-argument provider read on each `load`/`save`. F5 adds the root module `listeners.py` (`Listeners(Generic[P])`, logger injected, caller's full failure message); each settings service composes one and keeps `subscribe`/`unsubscribe` as forwarders.

**Tech Stack:** Python 3.11 (NVDA 2024.1), pytest, ruff 0.16.3 via prek.

**Spec:** `docs/superpowers/specs/2026-10-27-phase44-settings-infra-design.md`

## Global Constraints

- Paths are under `addon/synthDrivers/WorldVoice/` unless stated.
- `listeners.py` imports only the standard library; its names are PEP 8 snake_case; it is listed in `CORE` of `tests/test_naming_layers.py`.
- Log texts byte for byte: `"WorldVoice: pipeline settings listener failed"`, `"WorldVoice: detection settings listener failed"`, logged by `log.error(..., exc_info=True)`.
- Python 3.11 floor: no `typing.override`; `ParamSpec` is fine.
- No user-visible change; no readme, changelog, translatable string or stored key change.
- Subscribers keep calling `service.subscribe(...)` / `service.unsubscribe(...)` (`pipeline/scope.py:26`, `__init__.py:253-256`, `:278-281`).
- Do not touch `driver/<Engine>/driver/`, `driver/sonic/`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py`; never add `driver/Neural`. Engine drivers stay independently installable.
- ruff pinned `==0.16.3`; commits run prek hooks (re-stage on modification, never `--no-verify`); English `<type>: <summary>` with a body, no Co-Authored-By; stage explicit paths; no stash, no push.
- Tests serial or ≤3 workers under a memory watchdog (kill pytest when MemAvailable < 3 GB). Baseline 3336 passed, 0 skipped.

## Review Focus

1. A bound method subscribed twice and unsubscribed by a fresh bound method (`self._applyPipelineSettings` is a new object on each access): dedupe and removal go by equality — Task 2 `test_a_bound_method_is_matched_by_equality`.
2. A listener that unsubscribes itself or another while being told (scope teardown during a settings change): this round is unaffected, the next round skips it — Task 2 `test_a_listener_may_unsubscribe_while_told`.
3. `KeyboardInterrupt` inside a listener must still reach NVDA, not be logged and swallowed — Task 2 `test_a_base_exception_is_not_swallowed`.
4. An NVDA profile switch or a replaced `config.conf` after the synth started: the voice repository reads whatever the provider returns now — Task 1 `test_repository_reads_the_conf_its_provider_returns_at_each_call`.
5. A failing listener must not lose the update: the values are stored and `update` returns the new settings — Tasks 3 and 4 add the return-value assertion to the isolation tests.

---

### Task 1: Voice settings repository takes a conf provider (F9)

**Files:**
- Modify: `voices/settingsRepository.py:24-47`, `__init__.py:211`
- Test: `tests/test_voice_settings_repository.py:25-28`, `:78`; `tests/test_runtime_composition.py:172`; `tests/voice_binding_harness.py:16`; `tests/test_worldvoice_lifecycle.py`

**Interfaces:**
- Produces: `ConfigVoiceSettingsRepository(conf_provider: Callable[[], MutableMapping])`; `load`/`save` unchanged.

- [ ] **Step 1: Write the failing tests**

In `tests/test_voice_settings_repository.py`, the `repository` fixture and `:78` pass `lambda: conf`, and:

```python
def test_repository_reads_the_conf_its_provider_returns_at_each_call(monkeypatch, rt, conf):
	current = [{**worldvoice_conf(), "speech": {"WorldVoice": {}}}]
	repository = load_settings_repository(monkeypatch, rt).ConfigVoiceSettingsRepository(lambda: current[0])
	current[0] = conf
	conf["WorldVoice"]["voices"]["Fake:a"] = {"rate": "72"}
	assert repository.load(make_spec())["rate"] == 72
	repository.save(make_spec(), {**DEFAULTS, "pitch": 61})
	assert conf["WorldVoice"]["voices"]["Fake:a"]["pitch"] == 61
```

In `tests/test_worldvoice_lifecycle.py`:

```python
def test_the_driver_gives_the_voice_settings_repository_a_conf_provider():
	built = _construction_environment(None, [])
	load_synth_class(built.environment)()
	((args, kwargs),) = built.repositories
	(provider,) = args
	assert kwargs == {}
	config = built.environment["config"]
	assert provider() is config.conf
	config.conf = worldvoice_conf()
	assert provider() is config.conf
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest -q tests/test_voice_settings_repository.py tests/test_worldvoice_lifecycle.py`
Expected: FAIL — `TypeError: 'function' object is not subscriptable` in the repository tests; the lifecycle test fails with `TypeError: 'dict' object is not callable` at `provider()`.

- [ ] **Step 3: Implement**

`ConfigVoiceSettingsRepository.__init__(self, conf_provider: Callable[[], MutableMapping])` stores it; a private `_voices(self) -> MutableMapping` returns `self._conf_provider()["WorldVoice"]["voices"]`; `load` and `save` use it. `__init__.py:211` passes `lambda: config.conf`. `tests/test_runtime_composition.py:172` passes `lambda: c.config.conf`, `tests/voice_binding_harness.py:16` passes `lambda: config.conf`.

- [ ] **Step 4: Run to verify they pass, then the full suite**

Run: `python3 -m pytest -q tests/test_voice_settings_repository.py tests/test_worldvoice_lifecycle.py tests/test_runtime_composition.py` → all pass.
Full suite: 3338 passed, 0 skipped.

- [ ] **Step 5: Commit** `refactor: give the voice settings repository a conf provider`

### Task 2: The `listeners` module (F5)

**Files:**
- Create: `listeners.py`
- Test: `tests/test_listeners.py` (new); `tests/test_naming_layers.py:54-67` (add `"listeners.py"` to `CORE`)

**Interfaces:**
- Produces: `listeners.P = ParamSpec("P")`; `listeners.Listeners(Generic[P])` with `__init__(self, logger: logging.Logger, failure_message: str)`, `subscribe(self, listener: Callable[P, None]) -> None`, `unsubscribe(self, listener: Callable[P, None]) -> None`, `notify(self, *args: P.args, **kwargs: P.kwargs) -> None`.

- [ ] **Step 1: Write the failing tests**

`tests/test_listeners.py` loads `WORLDVOICE / "listeners.py"` with `addon_loader.load_source`; a `RecordingLogger` keeps `(args, kwargs)` of each `error` call. `MESSAGE = "WorldVoice: test listener failed"`.

- `test_listeners_isolate_a_failing_listener`: subscribe `seen.append`, a raising listener, `other.append`; `notify("x")` → `seen == other == ["x"]`, `logger.errors == [((MESSAGE,), {"exc_info": True})]`.
- `test_listeners_tell_each_listener_once_in_subscription_order`: subscribe `a`, `b`, `a`; `notify(1)` → calls `[("a", 1), ("b", 1)]`.
- `test_unsubscribing_an_unknown_listener_is_ignored`: `unsubscribe(print)` on an empty list raises nothing; after `unsubscribe` of a subscribed one, `notify` does not call it.
- `test_a_bound_method_is_matched_by_equality`: subscribe `holder.method` twice, `notify` → one call; `unsubscribe(holder.method)` → next `notify` makes none.
- `test_a_listener_may_unsubscribe_while_told`: `first` unsubscribes `second` and itself; round one calls both, round two calls none.
- `test_notify_passes_positional_and_keyword_arguments`: `notify(1, changed=frozenset({"x"}))` → listener got `(1,), {"changed": frozenset({"x"})}`.
- `test_a_base_exception_is_not_swallowed`: a listener raising `KeyboardInterrupt` → `pytest.raises(KeyboardInterrupt)`, `logger.errors == []`.
- `test_listeners_import_only_the_standard_library`: every import node of `listeners.py` is absolute and its top module is in `sys.stdlib_module_names` (as `tests/test_pipeline_structure.py:57-69`; skip under mutmut the same way).

In `tests/test_naming_layers.py` add `"listeners.py"` to the `CORE` tuple.

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest -q tests/test_listeners.py tests/test_naming_layers.py`
Expected: FAIL — `FileNotFoundError` for `listeners.py`; the naming guard passes (no module yet).

- [ ] **Step 3: Implement `Listeners` in `listeners.py`**

Module docstring says it is NVDA-free and the caller injects the logger. `notify` iterates `tuple(self._listeners)`, `except Exception: self._logger.error(self._failure_message, exc_info=True)`.

- [ ] **Step 4: Run to verify they pass, then the full suite**

Run: `python3 -m pytest -q tests/test_listeners.py tests/test_naming_layers.py` → all pass.
Full suite: 3346 passed, 0 skipped.

- [ ] **Step 5: Commit** `feat: add one listener list that isolates a failing listener`

### Task 3: The pipeline settings service uses `Listeners`

**Files:**
- Modify: `pipeline/settings.py:409-455`
- Test: `tests/test_pipeline_settings_service.py:344-363`; loaders that load `pipeline/settings.py` inside an alias package without its parent's modules (`tests/pipeline_harness.py:289-296`, `tests/ui_harness.py:683-691`, others the full suite reveals) load `listeners.py` beside it.

**Interfaces:**
- Consumes: `Listeners` (Task 2).
- Produces: `PipelineSettingsService.subscribe/unsubscribe` unchanged.

- [ ] **Step 1: Strengthen the test**

`test_update_notifies_subscribers_and_survives_a_failing_one`: the first `update(scope="all")` returns settings whose `scope == "all"` and `conf["WorldVoice"]["pipeline"]["scope"] == "all"`; replace `len(errors) == 2` with `errors == [("WorldVoice: pipeline settings listener failed",)] * 2`.

- [ ] **Step 2: Run it** — passes already (it pins today's behaviour; this is the regression net, not a red step).

- [ ] **Step 3: Implement** — `__init__` builds `self._listeners = Listeners[[PipelineSettings]](log, "WorldVoice: pipeline settings listener failed")` (import `from ..listeners import Listeners`); `update` calls `self._listeners.notify(settings)`; `subscribe`/`unsubscribe` forward. Update the test loaders the suite shows failing with `ImportError` on `..listeners`.

- [ ] **Step 4: Prove the net, then verify**

In a scratch copy of the worktree, change the message in `pipeline/settings.py` by one character and run the test → FAIL; remove the `try/except` from `listeners.py` → FAIL. Record both in the ledger.
Run: `python3 -m pytest -q tests/test_pipeline_settings_service.py tests/test_pipeline_scope.py` → pass. Full suite: 3346 passed, 0 skipped.

- [ ] **Step 5: Commit** `refactor: keep the pipeline settings listeners in Listeners`

### Task 4: The detection settings service uses `Listeners`

**Files:**
- Modify: `languageDetection/settings.py:46-104`
- Test: `tests/test_detection_settings.py:26-43` (loader: an alias root package with `languageDetection` under it and `listeners` loaded, so `from ..listeners` resolves), `:135-152`; other loaders the full suite reveals.

**Interfaces:**
- Consumes: `Listeners` (Task 2).
- Produces: `DetectionSettingsService.subscribe/unsubscribe` and `DetectionListener` unchanged.

- [ ] **Step 1: Strengthen the test**

`test_a_failing_listener_is_logged_and_the_others_still_run`: the first `update(timing="before")` returns settings with `timing == "before"`; replace `len(env.errors) == 2` with `env.errors == [("WorldVoice: detection settings listener failed",)] * 2`.

- [ ] **Step 2: Run it** — passes already (regression net).

- [ ] **Step 3: Implement** — `self._listeners = Listeners[[DetectionSettings, frozenset[str]]](log, "WorldVoice: detection settings listener failed")`; `update` calls `self._listeners.notify(settings, frozenset(changed))`; `subscribe`/`unsubscribe` forward; update loaders.

- [ ] **Step 4: Prove the net, then verify**

Scratch copy: one-character change of the message → the test FAILs. Record in the ledger.
Run: `python3 -m pytest -q tests/test_detection_settings.py tests/test_unicode_panel.py tests/test_language_detector.py` → pass. Full suite: 3346 passed, 0 skipped.

- [ ] **Step 5: Commit** `refactor: keep the detection settings listeners in Listeners`

### Task 5: Full verification and line delta

**Files:** none (ledger only).

- [ ] **Step 1:** `python3 -m pytest -q tests` → 3346 passed, 0 skipped.
- [ ] **Step 2:** `prek run --all-files` → all Passed; `git diff --check master` → empty.
- [ ] **Step 3:** protected paths (DEVELOPMENT_WORKFLOW.md §7) → both commands print nothing.
- [ ] **Step 4:** `git diff --stat master -- addon` and the product-code net line delta; if it grows, record `Ruling:` in the ledger with the numbers and the reason (spec §5.2).
- [ ] **Step 5:** `rg -n '_listeners\b' addon/synthDrivers/WorldVoice` shows only the two services' `Listeners` fields; `rg -n 'listener failed' addon` shows the two messages once each.
