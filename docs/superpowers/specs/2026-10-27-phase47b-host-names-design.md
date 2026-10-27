# Phase 47b: host-layer renames

Date: 2026-10-27.
Base: `master` `9848945` (phase 47a merged). Branch: `phase47b-host-names`.
Source: round-9 review `storage/refactor9.md` §6.1 (layered naming rule; rule 3 overturned by the user 2026-10-27 and left to phase 47d; the `@override` correction), §6 rows **P47b**/P47c/P47d, §4.3 (`_BindingEvents`, `class X(X)` shadowing), §5.1 "命名清晰度" and §5.3; phase 47a spec `docs/superpowers/specs/2026-10-27-phase47a-naming-rule-core-design.md` §11 and its review `docs/superpowers/finish/2026-10-27-phase47a-naming-rule-core-review.md` ("47b／47c 交接項目的分類意見").
Status: normal flow (DEVELOPMENT_WORKFLOW.md §3) with §3.2 "改名與搬移的證明": scripted renames from explicit `OLD=NEW` lists, one group per commit, each proven by an order-sensitive token check. No user-visible behavior change.

Paths are under `addon/synthDrivers/WorldVoice/` unless stated; guard paths are relative to `addon/`.

## 1. Problem

Phase 47a's guard `tests/test_naming_layers.py` holds `TRANSITIONAL_47B`: 317 definitions in the NVDA host layer that break its mixedCase style (`tests/test_naming_layers.py:93-505`). By kind: 165 functions and methods, 67 parameters, 42 locals, 41 fields, 2 module variables. By module: bridge 98 (`commands` 1, `indexCodec` 1, `completionPolicies` 18, `engineAdapter` 20, `indexLedger` 29, `nvdaEvents` 29), driver wrappers 122 (VE 32, Cerence 32, RHVoice 20, SAPI5 14, Espeak 13, OneCore 11), `ui/` 21, synth `__init__.py` 14, `globalPlugins/WorldVoice/` 47, `installTasks.py` 10, `generics/coreArchive.py` 5.

The list mixes three things the rule treats differently (refactor9 §6.1 rules 1–3): WorldVoice's own host names (rename), names that implement someone else's interface (keep, and mark), and names that must equal an identifier stored in a user's settings (left to 47d).

Three smells ride along (refactor9 §6 P47b): the class names still say "Legacy" although `bridge/` is a permanent boundary (`bridge/engineAdapter.py:47`, `bridge/voiceFacade.py:11`, `bridge/commands.py:11`); the synth and the six wrappers shadow their base names (`__init__.py:92` `class SynthDriver(SynthDriver)`, `driver/Espeak/__init__.py:208` `class Voice(Voice)` and five more); the synth's `taskManager` is its only public collaborator attribute (`__init__.py:185`, beside `_voiceManager`, `_eventBridge`, `_indexLedger`); and `bridge/nvdaEvents._BindingEvents(tuple)` checks revocation only when iterated (`bridge/nvdaEvents.py:29-41`; refactor9 §4.3).

## 2. Goals

1. `TRANSITIONAL_47B` is empty and deleted. Every entry is renamed, marked as an interface name, or moved to a new `TRANSITIONAL_47D` (§4).
2. The Legacy names, the shadowing imports, `taskManager` and `_BindingEvents` are fixed (§5).
3. Each rename commit is proven pure by a token check with its kept same-spelled tokens listed (§8).
4. The guard's docstring and self-tests describe the end state: no `TRANSITIONAL_47B`; `TRANSITIONAL_47C` and `TRANSITIONAL_47D` only shrink (§6).

## 3. Non-goals

- The plugin contract (`TRANSITIONAL_47C`: `driver.Voice.synth_driver_class`, `extra_capabilities`, `drain_profile`, `create_core`, `destroy_core`; `VoiceFacade.update_settings`): phase 47c, with Neural. Its callers keep these names (for example `bridge/completionPolicies.py:69`, `:78`, `bridge/engineAdapter.py:72`, `:107`).
- Stored identifiers: nvda.ini keys, driver setting ids (`uwv`, `numlan`, `rateBoost`…), the two script names: phase 47d (refactor9 §6 P47d). Strings stay as they are.
- `engineRegistry/`, `workspace.py` (pending; `workspace.workspace_path` keeps its name, called at `installTasks.py:25` and imported at `globalPlugins/WorldVoice/__init__.py:16`), the core, vendored drivers, `driver/sonic/`, generated Unicode data, `tests/` names (a test's own helpers, fixtures and fakes keep their names; only references to renamed add-on names change).
- The generated control attribute names of `ui/panelLayout.pipeline_attribute` (`_<key>_<suffix>`, `ui/panelLayout.py:115-117`): built from setting keys at run time, not definitions; 47d's key renames change them.
- NVDA override names that already follow mixedCase, and the core's `NativeStrategy` hooks the wrappers' strategies implement (already exempt by inheritance).

## 4. Disposition of each `TRANSITIONAL_47B` entry

### 4.1 Rename (the default)

Every entry not named in §4.2–§4.4 is WorldVoice's own host name and is renamed to `mixed(old)`: leading underscores kept, each underscore-separated word after the first capitalized (`_write_settings` → `_writeSettings`, `popup_SpeechSettingsDialog` → `popupSpeechSettingsDialog`). No aliases are kept; every caller in the add-on and the tests follows. Exceptions to `mixed(old)`:

| Old | New | Why |
| --- | --- | --- |
| `panels/detection.py` local `DetectLanguageTimingLabel` | `detectLanguageTimingLabel` | no underscore; only the first letter breaks the rule |
| `globalPlugins/WorldVoice/pipelineLog.py` `pipeline_log` (the `PipelineLogService` instance) | `pipelineLogService` | `mixed` gives `pipelineLog`, the name of its own module: `from .pipelineLog import pipelineLog` in the package `__init__` would rebind the package attribute `globalPlugins.WorldVoice.pipelineLog` from the submodule to the instance, which breaks `import …pipelineLog as m` and dotted `monkeypatch` targets |
| `bridge/commands.normalize_legacy_commands` | `normalizeNvdaCommands` | §5.1 |

Names a core module reads from a host object follow the host's new name. `voices/manager.py` builds the concrete adapter and bridge (`voices/manager.py:7-10`) and calls `adapter.notification_source`, `configure_completion`, `configure_segment_events`, `list_voices`, `self._bridge.segment_sink` (`:110-122`) and passes `index_ledger=` to the adapter (`:94`); `pipeline/context.py:43` calls `synth.speech_context()`. These are the host's own API, not core interfaces: `runtime/session.EngineAdapter` documents that the voice manager uses the concrete adapter directly for them (`runtime/session.py:35-40`). The core's call sites change, its definitions do not. The voices → bridge dependency is the portability debt refactor9 §6.1 assigns to §6.2. **Decided with the recommended default; user may override before merge** (the alternative, a core Protocol for what the voice manager uses, is new design and belongs to §6.2).

### 4.2 Interface names marked by explicit inheritance

The guard exempts a method, field or parameter whose name a readable base class defines (`tests/test_naming_layers.py:11-16`, `:672-682`). Three structural implementations become explicit:

1. `bridge/engineAdapter` adapter (`LegacyEngineAdapter`, renamed `VoiceClassAdapter` in §5.1) derives from `runtime/session.EngineAdapter` (`runtime/session.py:34-64`), which `EngineSession` calls (`runtime/session.py:163-172`). Exempts `finish_segment`.
2. `bridge/nvdaEvents.NvdaEventBridge` derives from `runtime/scheduler.NotificationOutput` (`runtime/scheduler.py:31-34`), the `output` the synth passes to `TaskManager` (`__init__.py:224`), called at `runtime/scheduler.py:371`, `:384`. Exempts `index_reached`, `done_speaking`.
3. A new core class `runtime/segmentHost.SegmentDrainCore` declares the two entries the bridge looks up on an engine core: `speak_segment(commands, token, *, context, on_event)`, called by keyword at `bridge/engineAdapter.py:30`, and `get_segment_drain_support(*, nvda_version, audio_mode)`, called by keyword at `bridge/completionPolicies.py:91` and pinned by `tests/test_native_strategy_guards.py:38-45`. The six wrappers' `SynthDriver` add it as their last base. Exempts `speak_segment`, `speak_segment.<locals>.on_event`, `get_segment_drain_support` and its two parameters in each wrapper (~~36~~ 30 entries, five per wrapper; corrected after the batch-2 review). A rename here would not fail loudly: `drain_support` turns any error into "unsupported" and the segment falls back to LEGACY_DONE (`bridge/completionPolicies.py:90-93`).

**Why not a `typing.Protocol` for 3.** NVDA's `SynthDriver` derives from `AutoPropertyObject` (`ref/nvda/source/synthDriverHandler.py:54`, `driverHandler.py:12`, `autoSettingsUtils/autoSettings.py:25`), whose metaclass is `AutoPropertyType(ABCMeta)` (`ref/nvda/source/baseObject.py:60`, `:121`). A Protocol's metaclass is `typing._ProtocolMeta(ABCMeta)`; neither derives from the other, so `class SynthDriver(BaseSynthDriver, SomeProtocol)` raises "metaclass conflict" when NVDA loads the wrapper. The tests' stub `SynthDriver` bases are plain classes, so the suite would not notice. `SegmentDrainCore` therefore derives from `abc.ABC` with two `@abstractmethod`s, like `NativeStrategy` (`runtime/segmentHost.py:75`): the derived metaclass is then `AutoPropertyType`. A test builds the combination with a stand-in metaclass derived from `ABCMeta` (§9). 1 and 2 are plain classes, so their Protocol bases are safe.

The other wrapper hooks need no mark: the strategies already derive from `NativeStrategy` (`tests/test_native_strategy_guards.py:14-20`), and the wrappers' overrides of vendored methods are exempt because the guard reads the vendored bases.

### 4.3 Interface names listed in `INTERFACE_NAMES`

Names from interfaces the guard cannot read (NVDA, the standard library, native DLL exports), kept and listed with the interface they mirror:

| Module | Name | Interface |
| --- | --- | --- |
| `driver/VE/__init__.py`, `driver/Cerence/__init__.py` | `_SilenceGate.is_set` | `threading.Event.is_set`; ~~which the vendored callback calls through `_isSilence`~~ the vendored callback calls `_isSilence.isSet()` (`driver/VE/driver/__init__.py:153`, `:182`, `:193`, `:195`), which `_SilenceGate.isSet` forwards to it (`driver/VE/__init__.py:113`; corrected after the final review F-M1) (refactor9 §4.3) |
| `driver/Espeak/__init__.py` | `_SegmentNative.espeak_Synth`, `_SegmentNative.espeak_ng_Cancel` | eSpeak NG DLL exports, proxied for NVDA's `_espeak.espeakDLL` (`driver/Espeak/__init__.py:16-55`, `:68`) |
| `driver/RHVoice/__init__.py` | `_NativeLibrary.RHVoice_new_message`, `RHVoice_speak`, `RHVoice_delete_message` | RHVoice library exports, proxied for the vendored driver's `__lib` (`driver/RHVoice/__init__.py:111-157`) |
| `driver/SAPI5/__init__.py` | `_SegmentAudioStream.ISequentialStream_RemoteWrite` | NVDA `synthDrivers.sapi5.SynthDriverAudioStream` (`ref/nvda/source/synthDrivers/sapi5.py:251`) |
| `driver/SAPI5/__init__.py` | `_SegmentSapiSink.ISpNotifySink_Notify`, `StartStream`, `Bookmark`, `EndStream` | NVDA `synthDrivers.sapi5.SapiSink` (`sapi5.py:455`, `:477`, `:486`, `:498`) |

Not interface names although they look like one: `_EspeakPort.run_when_done`, `set_index_callback`, `mark_not_speaking`, `stop_player` (`driver/Espeak/__init__.py:70-85`) are called only by the wrapper; the strategy's own `stop_player(host)` hook (`:110`) is `NativeStrategy`'s and keeps its name (47a review). They are renamed.

### 4.4 `TRANSITIONAL_47D`: stored identifiers

`GlobalPlugin.script_popup_SpeechSettingsDialog` and `GlobalPlugin.script_switch_log_record` (`globalPlugins/WorldVoice/__init__.py:127`, `:134`). NVDA binds a user's gestures by the name after `script_` (`ref/nvda/source/inputCore.py:879`, `getattr(cls, "script_%s" % scriptName)`), stored in `gestures.ini`, so they are rule-3 identifiers for phase 47d. No other entry equals an nvda.ini key or a driver setting id (checked against the confspec tables of `pipeline/settings.py`, `languageDetection/scriptLanguages.py`, `pipeline/registry.py`, `voices/settingsRepository.py`, `runtime/voiceSettings.py`).

### 4.5 Same-spelled tokens kept

A rename touches only the occurrences that name the renamed definition. Kept, and listed per commit (§8):

- Core and NVDA names spelled like a renamed host name: `PlaybackContext.source_id`/`segment_id`, `PlaybackEvent.source_id`/`segment_id` and the `segment_id=` keyword (`runtime/models.py`), `SegmentHost.control_error`, `VoiceManager(index_ledger=, task_manager=)`, NVDA's `WavePlayer.feed(onDone=)`, `LanguageDetector.add_detected_language_commands` (`__init__.py:330`).
- Interface keywords at a call: `speak_segment(…, context=, on_event=)` and `get_segment_drain_support(nvda_version=, audio_mode=)` (§4.2); the 47c contract names.
- Vendored names, `workspace.workspace_path`, config keys and setting ids in strings.
- Runtime message strings that quote a renamed name (log, exception and `DrainSupport.reason` texts) keep their text: no log text changes (as in 47a §7). Docstrings and comments follow the rename.

## 5. Other changes (separate commits)

1. **Legacy wording.** `LegacyEngineAdapter` → `VoiceClassAdapter` (it adapts a `driver.Voice` class and its core; `runtime/session.py` already has the Protocol `EngineAdapter`), `LegacyVoiceBinding` → `VoiceBinding`, `normalize_legacy_commands` → `normalizeNvdaCommands` (it normalizes NVDA command objects for the runtime: `bridge/commands.py:11-18`). Docstrings that call these "legacy" (`bridge/engineAdapter.py:1`, `bridge/commands.py:1`, `bridge/voiceFacade.py:1`) are reworded in the same, non-mechanical commit. No aliases (refactor9 §5.3). Explicit `OLD=NEW` renames, token-checked.
2. **Shadowed bases.** Each wrapper imports `from synthDrivers.WorldVoice.driver import Voice as BaseVoice` and declares `class Voice(BaseVoice)`; the synth imports `SynthDriver as BaseSynthDriver` from `synthDriverHandler` and declares `class SynthDriver(BaseSynthDriver)`. The wrappers' vendored bases already have distinct names (`BaseSynthDriver`, `BaseOneCoreSynthDriver`, `rhvoice.SynthDriver`). Module attributes are unchanged: `module.Voice` and `module.SynthDriver` are still WorldVoice's classes, so plugins and `tests/test_plugin_voice_contract.py` are unaffected.
3. **`taskManager` → `_taskManager`** on the synth (`__init__.py:185`, `:224`, `:237`, `:299`, `:324`, `:354`) and in the tests that set or read it (`tests/test_runtime_composition.py:296`, `tests/test_worldvoice_speak.py:209-372`). A token-checked rename commit.
4. **`_EventsWhileActive`.** `_BindingEvents(tuple)` becomes `_EventsWhileActive(events, isActive)`, a plain class whose only method is `__iter__`, yielding the decoded events while `isActive()` holds. Not a generator function: a generator iterates once and is silently empty the second time. `len()`, indexing and `bool()` are gone, so no consumer can bypass the check. The batch type becomes `Callable[[], Iterable[PlaybackEvent]]` in `runtime/scheduler.TaskManager.on_events` (`runtime/scheduler.py:301`; annotation only) and `NvdaEventBridge.start` (`bridge/nvdaEvents.py:69`); `IndexLedger.receive_index` still returns a tuple. Decoding stays eager inside `load_events()` (`bridge/nvdaEvents.py:170`); the early `return ()` paths stay. The scheduler consumes the batch only with `for` (`runtime/scheduler.py:323-324`).

## 6. Guard end state

`tests/test_naming_layers.py`:

- `TRANSITIONAL_47B` is deleted. `TRANSITIONAL_47D` holds the two script names (§4.4); `TRANSITIONAL_47C` is unchanged. `INTERFACE_NAMES` gains the ~~13~~ 12 entries of §4.3 (corrected: the table lists 12).
- Docstring: rule 2 mentions explicit base classes for structural implementations (and why not a Protocol for an NVDA driver); rule 3 says stored identifiers are renamed by 47d and wait in `TRANSITIONAL_47D`; the closing paragraph names only `TRANSITIONAL_47C` and `TRANSITIONAL_47D`, both shrink-only.
- `test_only_the_host_layer_waits_for_a_rename` becomes `test_only_stored_identifiers_and_the_plugin_contract_wait`: every `TRANSITIONAL_47D` entry is in the host layer and is a `script_` method (the only stored kind defined as a name today), and `TRANSITIONAL_47C` names only the contract's two modules. `test_naming_follows_layer` and `test_lists_hold_only_names_that_break_the_rule` read `INTERFACE_NAMES`, `TRANSITIONAL_47C`, `TRANSITIONAL_47D`.

## 7. Affected layers and files

- bridge: all six modules with entries, plus `voiceFacade.py` (§5.1).
- ui: `controls.py`, `panelLayout.py`.
- synth `__init__.py`; `globalPlugins/WorldVoice/{__init__,pipelineLog,rolePresenter,utils}.py`, `panels/{base,detection,engine,log,role}.py`; `installTasks.py`; `generics/coreArchive.py`.
- driver wrappers: `driver/{VE,Cerence,Espeak,OneCore,RHVoice,SAPI5}/__init__.py` (outer only; inner drivers untouched; VE and Cerence renamed identically so `tests/test_vocalizer_drift.py`'s allowlist, which names `SynthDriver._callback_admission`, follows as `SynthDriver._callbackAdmission`).
- core (call sites and one addition): `voices/manager.py`, `pipeline/context.py` (calls only, §4.1); `runtime/segmentHost.py` (`SegmentDrainCore`); `runtime/scheduler.py` (one annotation).
- tests: every test and harness that names a renamed add-on name, including strings (`monkeypatch.setattr(obj, "name", …)`, `load_definitions(path, ["Class.method"])`, `SimpleNamespace(name=…)` fakes of synth or module attributes).
- Each engine driver stays independently installable: wrappers import only core modules (`runtime/`), never another wrapper. No vendored, sonic, generated or Neural file changes. `ref/Neural` uses only `driver.Voice` names (47c), so nothing it touches changes.

## 8. Proof of the renames

Scripts in the session scratchpad `p47b/` (recorded in the ledger):

- `ren.py <repo> <group.py>` applies a group's rules by AST position: a local or parameter inside a named function, a member of a named class (`def`, class field, `self.x`), an attribute on receivers matching a pattern, a keyword argument at calls to a matching callee, a module name with its imports, and words in strings or comments on a given line. NEW is `mixed(old)` unless given.
- `check.py REV <group.py>` is the proof, independent of how the rules select occurrences: for every file the group names, the token streams of REV and HEAD have equal length; a NAME differs only as one of the file's `OLD → NEW` pairs, a string or comment only by such word replacements; every other token is equal in type, text and order (NL tokens and ruff's trailing commas ignored). Every occurrence of an OLD left in HEAD is counted per file, and the counts must equal the group's `KEPT` table, whose entries the ledger explains (§4.5). A NEW already present in the file before is reported as a possible collision unless listed. Any changed file outside the group fails, except the guard file, whose diff may only delete lines.
- Each rename commit holds one group (one package, one module family, or the VE/Cerence pair, which must change together for the drift test). Non-mechanical edits are separate commits.

## 9. Test plan

- **Red/green per rename task.** Remove the task's entries from `TRANSITIONAL_47B`; `test_naming_follows_layer` fails listing them; rename; it passes. A commit that renamed without removing the entries would fail `test_lists_hold_only_names_that_break_the_rule`.
- **Explicit inheritance.** Removing the entries of §4.2 fails `test_naming_follows_layer` until the base class is added.
- **New tests:**
  - `tests/test_segment_host.py::test_segment_drain_core_combines_with_an_abcmeta_driver_metaclass`: a stand-in `class Meta(ABCMeta)` base, like NVDA's `AutoPropertyType`, combines with `SegmentDrainCore`; `type(SegmentDrainCore) is ABCMeta` (not a Protocol); a subclass missing either entry cannot be instantiated.
  - `tests/test_native_strategy_guards.py::test_every_wrapper_core_declares_the_segment_drain_entries`: each of the six wrappers' `SynthDriver` names `SegmentDrainCore` as its last base.
  - `tests/test_nvda_event_bridge.py::test_batch_iterates_again_and_stops_after_unbind` (§5.4): the batch iterates the same events twice; after the binding is revoked a new iteration yields nothing; it has no `len()`.
  - `tests/test_native_strategy_guards.py::test_wrappers_do_not_shadow_their_bases`: no wrapper or synth class statement names a base with its own name.
- **Existing coverage** of behavior through the new names: composition and lifecycle (`test_runtime_composition.py`, `test_worldvoice_lifecycle.py`, `test_worldvoice_speak.py`, `test_worldvoice_pipeline_settings.py`), bridge (`test_index_ledger.py`, `test_index_codec.py`, `test_nvda_event_bridge*.py`, `test_runtime_legacy_adapter.py`, `test_runtime_completion_policies.py`), wrappers (`test_*_segment_drain.py`, `test_worldvoice_cancel_wrappers.py`, `test_vocalizer_drift.py`, `test_native_strategy_guards.py`, `test_engine_interface_guards.py`), UI (`test_settings_panels.py`, `test_role_*`, `test_unicode_panel.py`, `test_ui_controls.py`, `test_panel_layout.py`, `test_global_plugin_*`), install (`test_core_install.py`, `test_core_archive.py`).
- Full suite: baseline 3293 passed, 0 skipped; 3293 + the new tests after the phase, 0 skipped.
- No mutmut: no decision logic changes.
- Windows/NVDA: nothing new to check by hand, but Linux tests do not load NVDA's real `AutoPropertyType` classes, real audio or engine SDKs; the metaclass combination is covered by the stand-in test only.

## 10. User-visible behavior, strings, settings

None. No panel, label, message, translatable string, log text, setting, setting id, config key or gesture changes; no `.po`, readme or changelog edit. Script names keep their names (§4.4).

## 11. Open questions

None blocking. Defaults taken (user may override before merge):

1. Core call sites follow renamed host API (§4.1). *Decided with the recommended default; user may override before merge.*
2. `SegmentDrainCore` is an ABC in `runtime/segmentHost.py` rather than a Protocol (§4.2). *Decided with the recommended default; user may override before merge.*
3. `pipeline_log` → `pipelineLogService` (§4.1). *Decided with the recommended default; user may override before merge.*
4. Runtime message strings keep quoted old names (§4.5). *Decided with the recommended default; user may override before merge.*
5. The synth's own `class SynthDriver(SynthDriver)` is fixed with the wrappers' `Voice` imports (§5.2; refactor9 §4.3 names both). *Decided with the recommended default; user may override before merge.*
