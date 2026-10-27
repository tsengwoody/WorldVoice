# Phase 47b Host-Layer Renames Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).
> 15 tasks in three batches of five (§3.2): Tasks 1–5, 6–10, 11–15; an Opus batch review after the
> first two batches. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Empty and delete `TRANSITIONAL_47B` by renaming WorldVoice's own host names to NVDA mixedCase, marking interface names, and moving stored identifiers to `TRANSITIONAL_47D`, plus the Legacy names, shadowed bases, `_taskManager` and `_EventsWhileActive`.

**Architecture:** Each rename group is applied by `p47b/ren.py` from an explicit rule list (`p47b/groups/<task>.py`) and proven by `p47b/check.py` (order-sensitive token check with a `KEPT` table). Interface names are marked by explicit base classes (`EngineAdapter`, `NotificationOutput`, a new `runtime/segmentHost.SegmentDrainCore` ABC) or `INTERFACE_NAMES`. Non-mechanical edits are separate commits.

**Tech Stack:** Python 3.11 semantics (NVDA 2024.1 floor), pytest, ruff 0.16.3 via prek, AST/tokenize scripts.

**Spec:** `docs/superpowers/specs/2026-10-27-phase47b-host-names-design.md`

## Global Constraints

- No user-visible behavior change: no translatable string, log text, setting, setting id, config key or gesture changes (spec §10).
- Stored identifiers are not renamed in 47b: the two `script_` names go to `TRANSITIONAL_47D` (spec §4.4).
- `TRANSITIONAL_47C` names and their call sites are untouched (phase 47c).
- Do not rename a method that overrides a vendored or NVDA method; check each wrapper's `_XxxPort` lists, the vendored bases and `tests/test_native_strategy_guards.py`.
- Never edit `driver/<Engine>/driver/`, `driver/sonic/`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py`; never add Neural.
- Engine drivers stay independently installable: a wrapper imports only core modules, never another wrapper.
- VE and Cerence are renamed identically in one commit (`tests/test_vocalizer_drift.py`).
- Renames only by `ren.py` from explicit lists, one group per commit, each passing `check.py`; renames and non-mechanical edits never share a commit.
- Formatting follows ref/nvda: tabs, line length 110, ruff pinned `0.16.3`.
- git: stage explicit paths, `git diff --cached --stat` before each commit; English `<type>: <summary>` with a body; no `Co-Authored-By`; re-stage after a hook change, never `--no-verify`; no push; never `git stash`; never stage `ref`; new files under `docs/` need `git add -f`.
- Tests serially, or at most 3 workers with a watchdog killing pytest below 3 GB MemAvailable.

## Review Focus

1. A renamed parameter still passed by its old keyword at a constructor or `start` call (`NvdaEventBridge(index_ledger=…)`, `CompletionPolicy(nvda_version=…)`, `start(batch_handler=…)`) would stop the synth from loading: Tasks 1, 3, 7 run the composition tests that build the real synth (`tests/test_runtime_composition.py`, `tests/test_worldvoice_lifecycle.py`).
2. An interface keyword renamed by mistake (`get_segment_drain_support(nvda_version=, audio_mode=)`, `speak_segment(on_event=)`) silently drops DRAIN to LEGACY_DONE: Task 1 keeps `check(nvda_version=…, audio_mode=…)` in `KEPT`; Task 10 adds `test_every_wrapper_core_declares_the_segment_drain_entries`; `tests/test_runtime_completion_policies.py` and `test_drain_support_requires_keywords` run in every task.
3. The new base combined with NVDA's `AutoPropertyType` metaclass (tests use plain stubs): Task 10's `test_segment_drain_core_combines_with_an_abcmeta_driver_metaclass`.
4. A name reached by string (`getattr`/`hasattr`, `monkeypatch.setattr(obj, "name")`, `load_definitions(path, ["Class.method"])`, `object.__setattr__(self, "name")`, drift allowlist) left unrenamed: every rename task's group carries `text` rules for them and `check.py --verbose` lists every kept occurrence; the wrapper drain harnesses (Tasks 11–13) exercise the monkeypatched methods.
5. A batch iterated twice or after its binding is revoked mid-delivery: Task 5's `test_batch_iterates_again_and_stops_after_unbind`.

---

## The rename procedure (Tasks 1–4, 6–9, 11–13)

Scratch tools (session scratchpad `p47b/`): `ren.py <repo> <group> [--dry]`, `check.py REV <group> [--verbose]`, `scan.py <repo> NAME[,NAME] [path…]`. A group file defines `RENAMES = {path: [rule…]}`, `KEPT = {path: {OLD: count}}`, optional `COLLISIONS`.

For each group:

- [ ] Delete the group's entries from `TRANSITIONAL_47B` (and only those).
- [ ] Run `python3 -m pytest -q tests/test_naming_layers.py`. Expected red: `test_naming_follows_layer` fails listing exactly the deleted entries.
- [ ] Write the group file from `scan.py` output: every definition, call site, keyword site and string that names the renamed definition; nothing else.
- [ ] Run `ren.py`, then `ruff format` on the touched files only if `prek` would change them (it must not change tokens).
- [ ] Run `python3 -m pytest -q tests/test_naming_layers.py` → all passed; then the full suite → expected count, 0 skipped.
- [ ] `git add` the group's paths and the guard; commit; run `python3 check.py HEAD~1 <group> --verbose` → `pure rename: OK (…)`. Record the line and every kept count with its reason in the ledger. If it fails, fix the group, `git reset --soft HEAD~1`, re-run.

---

### Task 1: bridge commands, indexCodec, completionPolicies

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/bridge/{commands,indexCodec,completionPolicies}.py`, callers in `bridge/engineAdapter.py`, `__init__.py`
- Test: callers in `tests/` (`test_index_codec.py`, `test_runtime_completion_policies.py`, `test_legacy_speech_commands.py`, …), `tests/test_naming_layers.py`

**Interfaces:**
- Produces: `indexCodec.encodeSegment(commands, context, ledger)`; `CompletionPolicy(*, nvdaVersion=None, logger=None, forceUnverifiedDrain=True)` with `audioMode`, `drainSupport(voiceClass, core, *, nvdaVersion, audioMode)`, `contractFor(…)`, attributes `nvdaVersion`, `forceUnverifiedDrain`. `select(voice_class, core)` keeps its name; its parameters become `voiceClass`. `normalize_legacy_commands` stays until Task 4.

- [ ] Rename procedure, entries: `bridge/indexCodec.py` (1), `bridge/completionPolicies.py` (18). Kept: `check(nvda_version=…, audio_mode=…)` keywords (interface), the `force_unverified_drain` word in the `DrainSupport` reason string (spec §4.5). Suite: 3293 passed.

### Task 2: bridge indexLedger

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/bridge/indexLedger.py`, callers in `bridge/{indexCodec,nvdaEvents,engineAdapter}.py`
- Test: `tests/test_index_ledger.py` and other callers

**Interfaces:**
- Produces: `IndexAllocation(wireIndexes, endIndex)`; `IndexLedger.receiveIndex(sourceId, wireIndex, *, bindingToken=None)`, `receiveSegmentEvent(event, *, bindingToken)`, `retireSegment(context)`, `retireSource(sourceId)`; `bind(source, sourceId, contract)`, `prepare(context, originalIndexes)`, `unbind(sourceId)`.

- [ ] Rename procedure, entries: `bridge/indexLedger.py` (29). Kept: `context.source_id`/`segment_id`, `event.source_id`/`segment_id`, `PlaybackEvent(…, segment_id=…)`. Suite: 3293 passed.

### Task 3: bridge nvdaEvents and the `NotificationOutput` base

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/bridge/nvdaEvents.py`, callers in `__init__.py`, `voices/manager.py`
- Test: `tests/test_nvda_event_bridge*.py` and other callers

**Interfaces:**
- Produces: `NvdaEventBridge(owner, *, doneEvent, indexEvent, getSynth, indexLedger=None)`, `start(handler, *, batchHandler=None)`, `bind(source, sourceId, *, completion=…)`, `unbind(sourceId)`, `segmentSink(source, context)`; `class NvdaEventBridge(NotificationOutput)` keeps `index_reached`, `done_speaking`. `_BindingEvents` is untouched until Task 5 (its `is_active` parameter stays listed).

- [ ] Rename procedure, entries: `bridge/nvdaEvents.py` (29 minus `index_reached`, `done_speaking`, `_BindingEvents.__new__.<locals>.is_active`). Kept: `context.source_id`, `event.source_id`, `index_ledger=` passed to `VoiceManager`. Suite: 3293 passed.
- [ ] Delete `NvdaEventBridge.index_reached` and `.done_speaking` from `TRANSITIONAL_47B`; guard red listing both.
- [ ] Add `from ..runtime.scheduler import NotificationOutput`; `class NvdaEventBridge(NotificationOutput)`. Guard green; suite 3293 passed. Commit `refactor: mark the event bridge as the scheduler's notification output`.

### Task 4: bridge engineAdapter, the `EngineAdapter` base, the Legacy names

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/bridge/{engineAdapter,voiceFacade,commands}.py`, `voices/manager.py`, `__init__.py`
- Test: `tests/test_runtime_legacy_adapter.py`, `tests/legacy_adapter_harness.py`, `tests/runtime_harness.py`, `tests/voice_binding_harness.py`, and the other callers

**Interfaces:**
- Produces: `VoiceClassAdapter(voiceClass, resolveVoice, *, indexLedger=None, completion=None)` deriving from `runtime.session.EngineAdapter`, with `configureCompletion`, `configureSegmentEvents`, `listVoices`, `notificationSource`, `finish_segment` (interface); `VoiceBinding(settings, session, core)`; `normalizeNvdaCommands(sequence)`.

- [ ] Rename procedure, entries: `bridge/engineAdapter.py` (20 minus `LegacyEngineAdapter.finish_segment`). Kept: `speak_segment(…, context=…, on_event=…)` keywords. Suite: 3293 passed.
- [ ] Delete `LegacyEngineAdapter.finish_segment` from `TRANSITIONAL_47B`; red; `class LegacyEngineAdapter(EngineAdapter)` (import from `..runtime.session`); green. Commit `refactor: mark the engine adapter as the session's EngineAdapter`.
- [ ] Rename group with explicit pairs `LegacyEngineAdapter=VoiceClassAdapter`, `LegacyVoiceBinding=VoiceBinding`, `normalize_legacy_commands=normalizeNvdaCommands` across add-on and tests (delete `normalize_legacy_commands` from the guard; other qualnames follow the class rename in the guard file: edit `TRANSITIONAL_47B` keys only by deletion — none remain for these classes after the steps above). `check.py` OK. Suite 3293 passed.
- [ ] Reword the three "legacy" module docstrings (`bridge/engineAdapter.py:1`, `bridge/commands.py:1`, `bridge/voiceFacade.py:1`). Commit `docs: describe the bridge without the legacy wording`.

### Task 5: `_EventsWhileActive` and the widened batch type

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/bridge/nvdaEvents.py`, `addon/synthDrivers/WorldVoice/runtime/scheduler.py:301`
- Test: `tests/test_nvda_event_bridge.py`

**Interfaces:**
- Produces: `_EventsWhileActive(events: tuple[PlaybackEvent, ...], isActive: Callable[[], bool])` with only `__iter__`; `TaskManager.on_events(load_events: Callable[[], Iterable[PlaybackEvent]])`; `NvdaEventBridge.start(…, batchHandler: Callable[[Callable[[], Iterable[PlaybackEvent]]], None] | None = None)`.

- [ ] Write `test_batch_iterates_again_and_stops_after_unbind`: a drain-bound source; a segment sink's delivered `load_events()` result `batch`; `list(batch) == list(batch)` (two INDEX… events and the drain); `with pytest.raises(TypeError): len(batch)`; after `bridge.unbind(source_id)`, `list(batch) == []`.
- [ ] Run it: FAIL on `len(batch)` (a tuple has a length).
- [ ] Replace `_BindingEvents` by `_EventsWhileActive`; widen the two annotations; `load_events` return annotations become `Iterable[PlaybackEvent]`; delete `_BindingEvents.__new__.<locals>.is_active` from `TRANSITIONAL_47B`.
- [ ] Test passes; guard passes; suite 3294 passed. Commit `refactor: deliver bridge batches through an iterable that checks its binding`.
- [ ] Batch report (Tasks 1–5): suite, prek, `git diff --check master`, protected paths, remaining 47B size.

### Task 6: ui controls and panelLayout

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/ui/{controls,panelLayout,voicePanel}.py`, `globalPlugins/WorldVoice/panels/*.py` (callers)
- Test: `tests/test_ui_controls.py`, `tests/test_panel_layout.py`, `tests/test_settings_table_guard.py`, other callers

**Interfaces:**
- Produces: `controls.makeControl`, `controlValue`, `controlRow`, `readControl(spec, control, driverOptions=None)`, `applyDependencies(specs, read, controlOf)`; `panelLayout.panelSpecs`, `labelText`, `toDisplay`, `fromDisplay`, `choiceValues`, `choiceIndex`, `selectedValue`, `controllerKeys`, `dependentStates`, `creationFollowers`, `pipelineAttribute`, `voiceAttribute`, `driverAttribute`.

- [ ] Rename procedure, entries: `ui/controls.py` (7), `ui/panelLayout.py` (14). Kept: setting attribute strings. Suite: 3294 passed.

### Task 7: synth `__init__.py`, `_taskManager`, the synth's base name

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/__init__.py`, `pipeline/context.py:43`, `globalPlugins/WorldVoice/panels/{role,detection}.py`
- Test: `tests/test_worldvoice_*.py`, `tests/test_runtime_composition.py`, `tests/test_driver_ui_hooks.py`, UI fakes

**Interfaces:**
- Produces: `SynthDriver.voiceManager`, `speechContext()`, `refreshLanguageDetection()`, `addDetectedLanguageCommands`, `_taskManager`; module `baseDir`.

- [ ] Rename procedure, entries: synth `__init__.py` (14). Kept: `self._languageDetector.add_detected_language_commands` (core). Suite: 3294 passed.
- [ ] Rename group `taskManager=_taskManager` (synth and tests; kept: the core `task_manager=` keyword, `BaseVoice(…, taskManager, …)` fakes). Suite 3294.
- [ ] `from synthDriverHandler import SynthDriver as BaseSynthDriver, …`; `class SynthDriver(BaseSynthDriver)`. Suite 3294. Commit `refactor: import the synth's NVDA base under its own name`.

### Task 8: global plugin and settings panels, `TRANSITIONAL_47D`

**Files:**
- Modify: `addon/globalPlugins/WorldVoice/{__init__,pipelineLog,rolePresenter,utils}.py`, `panels/{base,detection,engine,log,role}.py`
- Test: `tests/test_global_plugin_*.py`, `tests/test_settings_panels.py`, `tests/ui_harness.py`, `tests/test_role_*`, `tests/test_pipeline_log.py`, `tests/test_guard_errors.py`

**Interfaces:**
- Produces: `pipelineLog.pipelineLogService`, `askExport`, `askDisableOnStart`, `confirmEnable(*, allowCancel)`, `exportWithDialog(pipelineLogFile=None)`; `utils.guardErrors`; `RolePanelPresenter` mixedCase members; `GlobalPlugin.popupSpeechSettingsDialog`, `checkLogRecord`, `enableLogRecord`, `disableLogRecord`, `submenuWorldVoice`, `submenuItem`.

- [ ] Guard-only commit: add `TRANSITIONAL_47D` with the two script names, removed from `TRANSITIONAL_47B`, and read it in `test_naming_follows_layer` and `test_lists_hold_only_names_that_break_the_rule`. Suite 3294. Commit `test: hold the stored script names for phase 47d`.
- [ ] Rename procedure, entries: the remaining 45 `globalPlugins/WorldVoice/` entries (`DetectLanguageTimingLabel=detectLanguageTimingLabel`, `pipeline_log=pipelineLogService`). Kept: script names, `"pipeline_log.csv"` file name. Suite: 3294 passed.

### Task 9: installTasks and generics

**Files:**
- Modify: `addon/installTasks.py`, `addon/generics/coreArchive.py`, `addon/globalPlugins/WorldVoice/__init__.py` (import)
- Test: `tests/test_core_install.py`, `tests/test_core_archive.py`, `tests/core_archive_harness.py`

**Interfaces:**
- Produces: `coreArchive.extractCoreArchive(archivePath, workspacePath)`; `installTasks._loadByPath`, `_loadCoreArchive`, `_workspacePath`, `_extractCoreArchive`.

- [ ] Rename procedure, entries: `generics/coreArchive.py` (5), `installTasks.py` (10). Kept: `module.workspace_path()` (pending module). Suite: 3294 passed.

### Task 10: `SegmentDrainCore`

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/runtime/segmentHost.py`, the six `driver/<Engine>/__init__.py`
- Test: `tests/test_segment_host.py`, `tests/test_native_strategy_guards.py`

**Interfaces:**
- Produces: `class SegmentDrainCore(ABC)` with `@abstractmethod get_segment_drain_support(self, *, nvda_version: str, audio_mode: str) -> DrainSupport` and `@abstractmethod speak_segment(self, commands: SpeechCommands, token: CancellationView, *, context: PlaybackContext, on_event: SegmentEventSink) -> None`; each wrapper `class SynthDriver(<vendored base>, SegmentDrainCore)`.

- [ ] Write `test_segment_drain_core_combines_with_an_abcmeta_driver_metaclass`: `type(SegmentDrainCore) is ABCMeta`; `class Meta(ABCMeta)`, `class Driver(metaclass=Meta)`, a `class Core(Driver, SegmentDrainCore)` defining both entries instantiates and `type(Core) is Meta`; a subclass defining only one raises `TypeError` on instantiation. Write `test_every_wrapper_core_declares_the_segment_drain_entries`: for the six engines, `ast.unparse(SynthDriver.bases[-1]) == "SegmentDrainCore"`.
- [ ] Run: FAIL (`ImportError` / bases differ).
- [ ] Add `SegmentDrainCore` (docstring: the entries the bridge looks up by name; why ABC, not Protocol); delete the ~~36~~ 30 (five per wrapper) `speak_segment`/`get_segment_drain_support` entries from `TRANSITIONAL_47B` (guard red), add the base and import in six wrappers (guard green).
- [ ] Suite 3296 passed. Commit `refactor: declare the wrappers' segment drain entries as a core base`.
- [ ] Batch report (Tasks 6–10).

### Task 11: VE and Cerence

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/{VE,Cerence}/__init__.py`
- Test: `tests/test_vocalizer_drift.py` (allowlist), `tests/test_vocalizer_segment_drain.py`, `tests/worldvoice_cancel_wrapper_harness.py`, `tests/test_worldvoice_cancel_wrappers.py`, `tests/runtime_drain_integration_harness.py`, `tests/test_f4_engine_adapters.py`

- [ ] Guard-only commit: move both `_SilenceGate.is_set` to `INTERFACE_NAMES` (`threading.Event.is_set`). Suite 3296.
- [ ] Rename procedure, entries: the remaining 25 per wrapper, identical in both. Kept: vendored privates in `_VEPort`/`hasattr` lists. Suite: 3296 passed; drift test passes.

### Task 12: Espeak and OneCore

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/{Espeak,OneCore}/__init__.py`
- Test: `tests/test_espeak_segment_drain.py`, `tests/espeak_drain_harness.py`, `tests/test_onecore_segment_drain.py`, `tests/onecore_drain_harness.py`

- [ ] Guard-only commit: `_SegmentNative.espeak_Synth`, `espeak_ng_Cancel` to `INTERFACE_NAMES`.
- [ ] Rename procedure: Espeak (`_EspeakPort.runWhenDone`, `setIndexCallback`, `markNotSpeaking`, `stopPlayer`; locals), OneCore (locals, `_feedSegment(…, onDone=None)`); one commit per wrapper. Kept: `NativeStrategy.stop_player` hooks, `host.control_error`, NVDA `onDone=`. Suite: 3296 passed.

### Task 13: RHVoice and SAPI5

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/{RHVoice,SAPI5}/__init__.py`
- Test: `tests/test_rhvoice_segment_drain.py`, `tests/rhvoice_drain_harness.py`, `tests/test_sapi5_segment_drain.py`, `tests/sapi5_drain_harness.py`

- [ ] Guard-only commit: RHVoice `_NativeLibrary.RHVoice_*` (3) and SAPI5 `_SegmentAudioStream.ISequentialStream_RemoteWrite`, `_SegmentSapiSink.{ISpNotifySink_Notify,StartStream,Bookmark,EndStream}` to `INTERFACE_NAMES`.
- [ ] Rename procedure: RHVoice (`_RHVoiceInner.ttsEngine`, `ttsQueue`, `ttsThread`, `cancelFlag`, `rateBoost`, `_nativeCallback`, `_isDone`, locals), SAPI5 (`_SapiRequest.indexLock`, `_purgeFlags`, locals); one commit per wrapper. Kept: mangled `_SynthDriver__*` strings, NVDA `onDone`. Suite: 3296 passed.

### Task 14: unshadowed `Voice` bases

**Files:**
- Modify: the six `driver/<Engine>/__init__.py`
- Test: `tests/test_native_strategy_guards.py`

- [ ] Write `test_wrappers_do_not_shadow_their_bases`: for the six wrappers and the synth `__init__.py`, no top-level `class X(...)` has a base `ast.Name` with id `X`. Run: FAIL listing six `Voice` classes.
- [ ] `from synthDrivers.WorldVoice.driver import Voice as BaseVoice`; `class Voice(BaseVoice)`. Pass; suite 3297 passed. Commit `refactor: import the wrappers' Voice base under its own name`.

### Task 15: guard end state

**Files:**
- Modify: `tests/test_naming_layers.py`

- [ ] Delete the empty `TRANSITIONAL_47B` and its uses; rewrite rules 2 and 3 and the closing paragraph of the docstring (spec §6); `test_only_the_host_layer_waits_for_a_rename` → `test_only_stored_identifiers_and_the_plugin_contract_wait` (47D entries are host `script_` methods; 47C the two contract modules).
- [ ] Probe: add a `TRANSITIONAL_47D` entry for a conforming name → `test_lists_hold_only_names_that_break_the_rule` fails; restore.
- [ ] Suite 3297 passed, 0 skipped; prek all Passed; `git diff --check master`; protected-path commands print nothing; `git grep -n TRANSITIONAL_47B` prints nothing outside `docs/`. Commit `test: state the naming guard's end state after phase 47b`.
