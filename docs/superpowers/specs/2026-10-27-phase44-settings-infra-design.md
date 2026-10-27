# Phase 44: settings infrastructure consistency (F9 + F5)

Date: 2026-10-27.
Base: `master` `10a1b30` (phase 47d merged). Branch: `phase44-settings-infra`.
Source: round-9 review `storage/refactor9.md` §4.5 **F9**, §4.1 **F5** (both revised 2026-10-27), the §6 row **P44**, and the naming rule §6.1; the user's scope decisions of 2026-10-27 relayed by the orchestrator.
Status: normal flow (DEVELOPMENT_WORKFLOW.md §3). Not a wide rename or move, so §3.2's proof scripts do not apply; the complex flow's conditions (byte-exact target, hand-off plan) do not hold.

Paths are under `addon/synthDrivers/WorldVoice/` unless stated. NVDA paths are under `ref/nvda/source/`.

## 1. Problem

**F9: one repository takes the conf object, the rest take a provider.**
`ConfigVoiceSettingsRepository.__init__(self, conf: MutableMapping)` (`voices/settingsRepository.py:27-28`) keeps the conf object, and the main driver passes `config.conf` (`__init__.py:211`). Every other reader of the config takes a zero-argument callable: `ConfigPipelineRepository(conf_provider=lambda: config.conf)` (`pipeline/settings.py:386-387`), `DetectionSettingsService(conf_provider)` (`languageDetection/settings.py:46-47`), `ConfigRoleRepository(conf_provider)` (`voices/roles.py:28-29`), `PipelineLogService(conf_provider)` (`addon/globalPlugins/WorldVoice/pipelineLog.py`). The object form is a leftover of phase 19/22 (refactor9 §4.5 F9 note), not a decision, so readers think the difference means something. NVDA's `config.conf` is one `ConfigManager` from `config.initialize()` on (`config/__init__.py:55`, `:104-107`), so a provider called later returns the same object; this is not the N2 trap (`getSynth()` returning `None` during construction).

**F5: two hand-written listener lists.**
`PipelineSettingsService` (`pipeline/settings.py:414`, notify loop `:440-444`, `subscribe`/`unsubscribe` `:447-455`) and `DetectionSettingsService` (`languageDetection/settings.py:48`, loop `:89-93`, `:96-104`) each keep `self._listeners`, deduplicate in `subscribe`, ignore an unknown listener in `unsubscribe`, and notify over a `tuple` copy with `try/except Exception` and `log.error(..., exc_info=True)`. They differ only in the listener signature (`(settings)` versus `(settings, changed)`) and the log text. Isolating a failing listener is written twice.

## 2. Goals

1. `ConfigVoiceSettingsRepository(conf_provider: Callable[[], MutableMapping])` reads the conf through the provider on every `load` and `save`. The main driver passes `lambda: config.conf`. Every call site and test helper passes a provider. *Decided by the user (2026-10-27).*
2. A new root module `listeners.py` holds the one listener list: `Listeners(Generic[P])` with `P = ParamSpec("P")`, `subscribe`, `unsubscribe`, `notify(*args: P.args, **kwargs: P.kwargs)`. Both services keep a `Listeners` and drop their own list, loop and isolation. *Decided by the user (2026-10-27).*
3. `listeners.py` is NVDA-free: it imports only the standard library (no `logHandler`), and the caller injects the logger, as `CancellationToken(logger)` does (`runtime/scheduler.py:48-49`). It is portable core, so its own names are PEP 8 snake_case (§6.1) and the naming guard lists it in `CORE` (`tests/test_naming_layers.py:54-67`). *Decided by the user (2026-10-27).*
4. Log texts stay byte for byte: `"WorldVoice: pipeline settings listener failed"` and `"WorldVoice: detection settings listener failed"`, still logged by `log.error` with `exc_info=True`. *Decided by the user (2026-10-27).*

## 3. Non-goals

- `CancellationToken`'s callback list (`runtime/scheduler.py`) fires once and takes a lock; different semantics, not merged (refactor9 F5 note).
- No change to who subscribes: `PipelineScope.__init__` (`pipeline/scope.py:26`) and `SynthDriver._initialize` (`__init__.py:253-256`, `:278-281`) keep calling `service.subscribe(...)` / `service.unsubscribe(...)`.
- No locking added: today's lists have none and are used from NVDA's main thread; unchanged.
- No readme, changelog or translatable string changes; no stored key changes.
- Python 3.11 floor (NVDA 2024.1, `buildVars.py:39`): no `typing.override`; `ParamSpec` (3.10) is fine.

## 4. NVDA user's view

Nothing changes. Settings load and save the same keys; a failing settings listener is logged with the same text and the other listeners still run.

## 5. Design

### 5.1 `listeners.py`

```python
P = ParamSpec("P")

class Listeners(Generic[P]):
	def __init__(self, logger: logging.Logger, failure_message: str): ...
	def subscribe(self, listener: Callable[P, None]) -> None: ...    # a listener already there is not added again
	def unsubscribe(self, listener: Callable[P, None]) -> None: ...  # an unknown listener is ignored
	def notify(self, *args: P.args, **kwargs: P.kwargs) -> None: ...
```

`notify` iterates over a tuple copy taken first (a listener may unsubscribe while told), calls each listener with the arguments, and on `Exception` calls `logger.error(failure_message, exc_info=True)` and goes on. `BaseException` that is not an `Exception` (e.g. `KeyboardInterrupt`) propagates, as today.

- **The caller passes the whole message, not a fragment.** refactor9's sketch built `f"WorldVoice: {what} listener failed"`. Passing the full text keeps each log line greppable in the service that owns it and makes "byte for byte" a literal check. *Decided by orchestrator with the recommended default; user may override before merge.*
- **The logger annotation is `logging.Logger`.** NVDA's `logHandler.Logger` subclasses it (`logHandler.py:222`); tests pass a stub with `error`. No default logger: an NVDA-free module has no right default for NVDA's log. *Decided by orchestrator with the recommended default; user may override before merge.*

### 5.2 The services

Each service builds its list in `__init__` with its own message:

- `PipelineSettingsService`: `Listeners[[PipelineSettings]](log, "WorldVoice: pipeline settings listener failed")`; `update` calls `notify(settings)`.
- `DetectionSettingsService`: `Listeners[[DetectionSettings, frozenset[str]]](log, "WorldVoice: detection settings listener failed")`; `update` calls `notify(settings, frozenset(changed))`. `DetectionListener` stays as the public alias.

Both keep `subscribe` and `unsubscribe` as two-line forwarders to the list, so subscribers see the same interface (§3). *Decided by orchestrator with the recommended default (composition with forwarders, not inheriting from `Listeners`, which would make `notify` public on the service, nor `service.listeners.subscribe`, which changes every subscriber); user may override before merge.*

**Line count.** refactor9 expected a net saving of about 5–10 lines, counting the two duplicated blocks (about 15 lines each) against a 25-line module. The forwarders keep about 4 lines per service, so the expected result is a small net growth (about +10 to +15 lines of product code). If that happens, the ledger records a `Ruling:` with the measured delta. The benefit sought is that isolation exists once, not the line count.

### 5.3 `ConfigVoiceSettingsRepository`

`__init__(self, conf_provider: Callable[[], MutableMapping])` stores the provider; `load` and `save` read `self._conf_provider()["WorldVoice"]["voices"]` through one private `_voices()` helper, as the other repositories use `_section()`. No default provider: `voices/settingsRepository.py` takes its dependencies by injection and does not import `config` (its docstring, `:1`; guarded by `tests/test_voice_settings_repository.py:65-82`). *Decided by orchestrator with the recommended default; user may override before merge.*

Call sites: `__init__.py:211` → `ConfigVoiceSettingsRepository(lambda: config.conf)`; tests `tests/test_voice_settings_repository.py:28`, `:78`, `tests/test_runtime_composition.py:172`, `tests/voice_binding_harness.py:16`. `tests/test_worldvoice_lifecycle.py:167` stubs the class with `*args, **kwargs` and records the calls in `repositories` (`:127`), which no test reads yet.

## 6. Error handling

Unchanged: a listener's `Exception` is logged and swallowed; everything else propagates. A provider that raises propagates from `load`/`save`, as a failing `conf["WorldVoice"]` lookup does today.

## 7. Test plan

- **New `tests/test_listeners.py`** (loads `listeners.py` alone):
  - `test_listeners_isolate_a_failing_listener`: a failing listener between two recording ones; the others are told, and the logger got exactly `("<message>",)` with `{"exc_info": True}` once.
  - `test_listeners_tell_each_listener_once_in_subscription_order` (dedupe) and `test_unsubscribing_an_unknown_listener_is_ignored`.
  - `test_a_listener_may_unsubscribe_while_told` (the tuple copy): a listener that unsubscribes another during `notify` does not stop that one this round, and it is gone next round.
  - `test_notify_passes_positional_and_keyword_arguments`.
  - `test_a_base_exception_is_not_swallowed` (`KeyboardInterrupt` propagates).
  - `test_listeners_import_only_the_standard_library` (as `tests/test_pipeline_structure.py:57-69`).
- **Existing isolation tests keep pinning the service behaviour and now the log text**: `tests/test_detection_settings.py::test_a_failing_listener_is_logged_and_the_others_still_run` and `tests/test_pipeline_settings_service.py::test_update_notifies_subscribers_and_survives_a_failing_one` assert the recorded `log.error` arguments equal the exact message twice (today they only count errors).
- **F9**: `tests/test_voice_settings_repository.py::test_repository_reads_the_conf_its_provider_returns_at_each_call` (swap the conf after construction; `load` and `save` use the new one); `tests/test_worldvoice_lifecycle.py::test_the_driver_gives_the_voice_settings_repository_a_conf_provider` (the one recorded call has one callable argument returning the current `config.conf`, also after `config.conf` is replaced).
- **Naming guard**: `listeners.py` added to `CORE`; `test_every_add_on_module_has_a_layer` is the red step.
- Full suite: baseline 3336 passed, 0 skipped; afterwards 3336 plus the new cases, 0 skipped.
- No mutmut: the only logic is the moved loop, pinned by the tests above (mutations proven in a scratch copy if a test seems to lose coverage).
- Windows/NVDA: nothing user-visible to check; not verified on Windows.

## 8. Open questions

None blocking. Defaults taken (the user may override before merge):

1. The caller passes the full failure message (§5.1). *Decided by orchestrator with the recommended default; user may override before merge.*
2. Services keep `subscribe`/`unsubscribe` as forwarders to a composed `Listeners` (§5.2), accepting a small net line growth. *Decided by orchestrator with the recommended default; user may override before merge.*
3. `ConfigVoiceSettingsRepository` has no default provider (§5.3). *Decided by orchestrator with the recommended default; user may override before merge.*
