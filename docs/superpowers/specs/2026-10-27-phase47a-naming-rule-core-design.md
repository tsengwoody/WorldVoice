# Phase 47a: layered naming rule, its guard, and the core-side renames

Date: 2026-10-27.
Base: `master` `8e1df5b` (phase 42 merged). Branch: `phase47a-naming-rule-core`.
Source: round-9 review `storage/refactor9.md` §6.1 (layered naming rule, decided by the user 2026-10-27, overturning refactor7 S5), §6 rows **P47a**/P47b/P47c, §5.1 "命名清晰度" (its 2026-10-27 revision), §5.3 rows on `VoiceManager`.
Status: automatic flow (DEVELOPMENT_WORKFLOW.md §3), run as the **complex flow** (§4). No user-visible behavior change.

Paths are under `addon/synthDrivers/WorldVoice/` unless stated; the guard's own paths are relative to `addon/`.

## 0. Why the complex flow

The phase renames 68 definitions in 11 core modules, updates their callers in 3 host modules and 14 test files and harnesses, and adds a guard whose transitional lists name 323 definitions. DEVELOPMENT_WORKFLOW.md §4.0 lists "大範圍的機械式修改 … 必須證明沒有夾帶其他修改" as a complex-flow case. The plan therefore carries byte-exact `File:`/`Edit:` blocks, a rename script embedded in the plan with an explicit list of names per file (whole-file word renames; the few renames that must skip an occurrence are `Edit:` blocks), an order-sensitive token check after each rename commit that proves the commit changes nothing but the listed names (the phase 42 review's lesson: not a multiset check), and the expected `HEAD:addon`/`HEAD:tests` tree ids after every commit. It is dry-run in a fresh clone before it is applied (§4.2–4.4).

## 1. Problem

1. **Names follow their birth date, not the architecture.** refactor9 §6.1 records how snake_case entered with the new `runtime/` (2026-09-26) and spread only to interfaces touched after phase 10a, so one class mixes both styles. `voices/manager.py` `VoiceManager` has 17 camelCase public members (`getVoiceSpec` `:168` … `getVoiceLocaleForLanguage` `:301`) beside snake_case ones (`resolve_playback` `:158`, `playback_ports` `:260`, `engine_consistency` `:77`), plus camelCase private helpers (`_getDefaultVoiceSpec` `:208`, `_createVoiceInstance` `:222`, `_setVoiceDatas` `:263`, `_getConfiguredVoiceNameForLanguage` `:306`), fields (`taskManager` `:49`, `_instanceCache` `:56`, `_defaultVoiceInstance` `:59`) and parameters (`taskManager` `:37`, `voiceName` `:215`/`:222`, `baseInstance` `:237`/`:240`).
2. **Other core modules have camelCase parameters and locals.** The pipeline stages, the logged runner and NVDA filter handler name their sequence `speechSequence` (26 functions in `pipeline/{breaks,items,languageCommands,numberStages,punctuation,registry,unspaced}.py`); `languageDetection/detector.py` has `availableLanguages` (parameter `:14`, attribute `:20`), `speechSequence` (`:58`) and four camelCase locals (`:61-78`); `pipeline/sayAll.py` has the parameter `getTextInfoSpeech` (`:20`), the nested function `getTextInfoSpeechWithSayAllBreak` (`:24`) and the local `waitFactor` (`:27`); `runtime/segmentHost.py` `LeasedPlayer._feed_admitted` and `_callback` take `onDone` (`:667`, `:683`).
3. **Nothing enforces a rule.** `pyproject.toml:118-125` enables ruff's default rules only (no `select`), so pep8-naming (`N`) is off; `N999` is ignored for module names. refactor9 §6.1 "守門" asks for an AST test.

## 2. Goals

1. **The rule, in code.** A new guard `tests/test_naming_layers.py` whose module docstring states the rule (§4), so it is discoverable from the code.
2. **The guard.** It classifies every add-on module by path, reads every name the module binds itself, and fails on a name that breaks its layer's style unless rule 2 exempts it or a transitional list names it (§4).
3. **Transitional lists.** `TRANSITIONAL_47B` lists every current violation in the host layer (317 names), `TRANSITIONAL_47C` the six names of the plugin contract (`driver/__init__.py` `Voice.synth_driver_class`, `extra_capabilities`, `drain_profile`, `create_core`, `destroy_core`; `bridge/voiceFacade.py` `VoiceFacade.update_settings`). The core has no list after this phase; during the phase a `TRANSITIONAL_47A` list holds the core names still to rename, each task removes its entries before renaming (red), and the last task deletes the empty list.
4. **Core renames, no aliases.** Every camelCase name the core defines becomes snake_case (§5), and every caller follows. Each new name is the old name in snake_case (`snake(name)`: an underscore before each capital that follows a lowercase letter or digit, then lowercase), so the rename is mechanical and checkable.

## 3. Non-goals

- Host-layer names (P47b), the plugin contract `driver.Voice`/`VoiceFacade.update_settings` (P47c), `engineRegistry/`, `workspace.py`: listed, not renamed.
- Config keys and driver setting ids (rule 3): strings stored in nvda.ini, not names.
- NVDA override names, names of vendored or other outside interfaces (rule 2).
- Excluded code: `driver/<Engine>/driver/**`, `driver/sonic/**`, `unicodeScripts/*_data.py`, and `tests/` (test helpers and fakes follow the code they fake, but are not checked).
- `runtime.{engineControl, models, playbackWork, session}` names (refactor9 §5.3 "不碰"): none breaks the rule except `VoiceSnapshot.rateBoost`, which rule 3 keeps (§4.3).
- Docs: `docs/README.md` describes development records, not current rules (`docs/README.md:3-4`), so no pointer goes there; the readme and the translated docs describe user-visible behavior, which does not change. The guard docstring is the rule's home; refactor9 is git-ignored.

## 4. The rule as the guard implements it

### 4.1 Layers (rule 1)

| Layer | Paths (relative to `addon/`) | Style of own names |
| --- | --- | --- |
| core | `synthDrivers/WorldVoice/{runtime,unicodeScripts,text,languageDetection,pipeline,voices}/`, `synthDrivers/WorldVoice/{locales,numberLanguage,bringup,speechCommands}.py` | PEP 8 snake_case: `_*[a-z][a-z0-9_]*` |
| host | `synthDrivers/WorldVoice/{bridge,driver,ui}/` (incl. `driver/__init__.py`), `synthDrivers/WorldVoice/__init__.py`, `globalPlugins/WorldVoice/`, `installTasks.py`, `generics/` | NVDA mixedCase (`ref/nvda/projectDocs/dev/codingStandards.md:26`): `_*(script_|event_|_get_|_set_)?[a-z][a-zA-Z0-9]*` |
| pending | `synthDrivers/WorldVoice/engineRegistry/`, `synthDrivers/WorldVoice/workspace.py` | not checked (refactor9 §6.2) |
| excluded | `synthDrivers/WorldVoice/driver/<Engine>/driver/**`, `driver/sonic/**`, `unicodeScripts/*_data.py` | not checked |

Both layers: a class name is CapWords (`_*[A-Z][a-zA-Z0-9]*`); a module or class name may also be an UPPER_CASE constant (`_*[A-Z][A-Z0-9_]*`) or a CapWords type alias (`VoiceKey = str`, `runtime/models.py:7`); leading underscores and dunder names are free. A module the table does not classify fails `test_every_add_on_module_has_a_layer`, so a new package (for instance P40's `confspec.py`) must be classified when it is added.

### 4.2 Which definitions the guard checks

Every name a module binds, except imports: functions and methods (nested ones too), classes, parameters (lambdas included), class-level fields and dataclass fields, attributes a method sets on its first parameter (`self.x = …`, or `cls.x` in a class method; not in a static method), module variables, and local variables (assignment, `for`, `with … as`, `except … as`, comprehension and walrus targets). A name declared `global` in a function counts as a module variable.

Why this wide: rule 1 says "自己定義的函式、方法、變數、參數、欄位", and parameters, fields and attributes are API (keyword arguments, attributes read by other modules and tests). Locals are not API, but checking them costs 6 renames in the core and 42 entries for 47b, keeps the statement of the rule one sentence ("every name a module binds except imports"), and a local often becomes a parameter or field later. Imports are left out because their names are the imported module's choice (`from . import driver as base`, `driver/VE/__init__.py:20`, is spelled for readability, not as a definition).

Each definition is keyed by a qualified name in Python's style: `name` for a module name, `Class.name` for a method, class field or attribute, `function.<locals>.name` for a parameter, local or nested function. The key does not contain line numbers, so lists survive unrelated edits.

### 4.3 Rule 2: interface names, and why not `typing.override`

**Decided by the user (2026-10-27):** keep the minimum NVDA version at 2024.1 and do not use `typing.override`; rule 2 is marked by inheritance plus `INTERFACE_NAMES`, and `test_no_module_imports_typing_override` stays. The guard exempts a name on two grounds, and `typing.override` is not one of them:

1. **Inheritance the guard can read.** A method or field whose name a base class defines is exempt, with the parameters of such a method, when the base is a class of the add-on named in the class statement: a Protocol or ABC of the core (`runtime/segmentHost.NativeStrategy`), a vendored driver class (`class SynthDriver(base.SynthDriver)` over `driver/VE/driver/`), `driver.Voice`. The guard follows `from … import` (relative ones included), `module.Class` bases, re-exports, and base classes of base classes. In `class SynthDriver(SynthDriver)` the base is the imported class, not the class itself (§4.4). This is rule 2's "explicit Protocol/ABC inheritance for structural implementations" made checkable: the exemption holds only if the base really defines the name, so a renamed base makes its stale overrides fail.
2. **`INTERFACE_NAMES`.** A name taken from an interface the guard cannot read (NVDA, the standard library, wx, a stored setting id) is listed with the interface it mirrors. After this phase it has three core entries:
   - `runtime/models.py` `VoiceSnapshot.rateBoost`: the voice setting id `rateBoost` (`runtime/voiceSettings.py:23`), stored in nvda.ini and NVDA's SynthDriver setting of that name; rule 3, and `runtime.models` is a "不碰" public path (refactor9 §5.3).
   - `runtime/segmentHost.py` `LeasedPlayer.feed.<locals>.onDone`: NVDA's `nvwave.WavePlayer.feed(data, size=None, onDone=None)` (`ref/nvda/source/nvwave.py:313`), which engines call by keyword (`driver/RHVoice/driver/__init__.py:232`, `driver/OneCore/__init__.py:472`); refactor9 §6 P48 says the same.
   - `speechCommands.py` `WVLangChangeCommand.isDefault`: NVDA's `SynthParamCommand.isDefault`, which `ParamChangeTracker.update` reads (`ref/nvda/source/speech/manager.py:95-105`; `speechCommands.py:19-24`).

**Why not `@typing.override`.** `typing.override` is new in Python 3.12. The add-on declares `addon_minimumNVDAVersion="2024.1"` (`buildVars.py:39`); NVDA 2024.1 to 2025.3 run Python 3.11 (`ref/nvda/user_docs/en/changes.md:2000`, section 2024.1) and only 2026.1 moves to Python 3.13 (`changes.md:794`, section 2026.1); phase 20 relied on the same minimum (`docs/superpowers/specs/2026-10-05-phase20-hygiene-design.md:44`). `from typing import override` would raise `ImportError` when NVDA 2024.1–2025.3 loads the synth, so WorldVoice would not load at all there: a user-visible regression. refactor9 §6.1's premise "NVDA 要求 Python 3.13" holds for current NVDA, not for the add-on's declared range. The guard therefore adds `test_no_module_imports_typing_override`, which fails on such an import while the minimum NVDA version is below 2026.1 and skips itself once `buildVars.py` says 2026.1 or later. The user decided to keep the minimum at 2024.1 (§10).

**Rule 2 in the core.** Apart from `isDefault`, no core class overrides an outside base's name that breaks snake_case: the core's classes with outside bases are `NumberBreakCommand`/`PunctuationBreakCommand(BreakCommand)` (no methods), `SpeechFuture(Future)` (no methods), `NativeStrategy(ABC)` (its own snake_case hooks), `WVLangChangeCommand(SynthParamCommand)` and `WorldVoiceIndexCommand(IndexCommand)` (only `__init__`/`__repr__`). A conforming override needs no mark: the marks exist to explain a departure from the layer's style. The stdlib overrides refactor9 mentions (`is_set`, `clear`) are in the host layer (`driver/VE/__init__.py` `_SilenceGate(threading.Event)`, and Cerence's copy), listed for 47b.

### 4.4 Finding while prototyping: `class X(X)`

The synth driver is `class SynthDriver(SynthDriver)` over `synthDriverHandler.SynthDriver` (`__init__.py`). A first prototype looked the base name up among the module's own classes first, so the class counted as its own base and all its members were exempt (12 snake_case members, such as `SynthDriver.voice_manager`, vanished from the host list). The guard now takes a same-module class as a base only if it is defined above the class statement, as Python binds it; `test_the_guard_reads_the_imported_base_of_a_class_with_its_name` pins it.

### 4.5 Guard tests

| Test | Fails when |
| --- | --- |
| `test_every_add_on_module_has_a_layer` | an add-on module matches no layer |
| `test_naming_follows_layer` | a checked definition breaks its layer's style, is not exempt (rule 2) and no list names it |
| `test_lists_hold_only_names_that_break_the_rule` | a list names a definition that no longer exists or now follows the rule (the lists only shrink) |
| `test_only_the_host_layer_waits_for_a_rename` | `TRANSITIONAL_47B` names a non-host module, or `TRANSITIONAL_47C` names other modules than the contract's two |
| `test_no_module_imports_typing_override` | a non-excluded module imports `override` from `typing`/`typing_extensions` while the minimum NVDA version is below 2026.1 |
| `test_the_guard_reads_each_kind_of_name` (11 cases) | the walker misses a kind of definition or flags a conforming one: camelCase function, parameter, dataclass field, `self` attribute, `for` target and lambda parameter in the core; constants, type aliases, classes and dunders pass; snake_case function in the host; `_get_`/`script_` prefixes pass; an override of an unreadable base (`wx.Panel.Destroy`) is flagged |
| `test_the_guard_lets_an_override_keep_the_base_name` | a host class that names a core base loses the exemption for the base's method, attribute or parameter, or gains one for its own method |
| `test_the_guard_reads_the_imported_base_of_a_class_with_its_name` | `class SynthDriver(SynthDriver)` counts as its own base (§4.4) |

## 5. Renames

All in the core; every new name is `snake(old)`.

| Module | Names |
| --- | --- |
| `voices/manager.py` `VoiceManager` (private, fields, parameters, locals) | `taskManager` (parameter `:37` and attribute `:49`), `_instanceCache`, `_defaultVoiceInstance`, `_getDefaultVoiceSpec`, `_createVoiceInstance`, `_setVoiceDatas` (→ `_set_voice_datas`), `_getConfiguredVoiceNameForLanguage`, `voiceName`, `baseInstance`, `voiceInstance` |
| `voices/manager.py` `VoiceManager` (public) | `getVoiceSpec`, `getVoiceCapabilities`, `getVoiceVariants`, `beginVoiceSettingsEdit`, `defaultVoiceInstance`, `defaultVoiceName` (property and setter), `getVoiceInstance`, `previewVoiceParameterConsistent`, `onVoiceParameterConsistent`, `onKeepEngineConsistent`, `onKeepMainLocaleVoiceConsistent`, `voiceInfos`, `allLanguages`, `localeToVoicesMap`, `localesToNamesMap`, `getVoiceNameForLanguage`, `getVoiceLocaleForLanguage` |
| `pipeline/{breaks,items,languageCommands,numberStages,punctuation,registry,unspaced}.py` | `speechSequence` (parameters, and the locals that rebind them in `registry.py:40-44`, `:98-108`) |
| `languageDetection/detector.py` `LanguageDetector` | `availableLanguages` (parameter and attribute), `speechSequence`, locals `defaultLang`, `curLang`, `tmpLang`, `targetLang` |
| `pipeline/sayAll.py` | parameter `getTextInfoSpeech`, nested function `getTextInfoSpeechWithSayAllBreak` (→ `get_text_info_speech_with_say_all_break`), local `waitFactor`; not NVDA's `speech.speech.getTextInfoSpeech` (`:38`, `:47`) nor the docstring's mention of it |
| `runtime/segmentHost.py` `LeasedPlayer` | `onDone` of `_feed_admitted` and `_callback`; not `feed`'s (INTERFACE_NAMES) nor the `onDone=` keyword passed to NVDA's player |

`_set_voice_datas` keeps the old word "Datas": the phase renames mechanically so that a token check can prove it.

**Callers.** Host: `__init__.py` (the `task_manager=` keyword at `:237`; 24 member reads), `globalPlugins/WorldVoice/rolePresenter.py` (16), `globalPlugins/WorldVoice/panels/detection.py:29`. The synth's own `self.taskManager` (`:185`, `:224`, `:237` value, `:299`, `:324`, `:354`) stays: it is a host name for 47b (`_taskManager`, refactor9 §6 P47b). Tests: 14 files and harnesses that call the manager or fake it (`SimpleNamespace` fakes, `object.__new__(VoiceManager)` set-ups, the fake `VoiceManager` classes of `tests/test_worldvoice_lifecycle.py` and `tests/test_worldvoice_speak.py`), including comments that name a renamed method.

**Not renamed although spelled alike.** The vendored VE/Cerence driver core has its own `getVoiceInstance`, `_instanceCache` and `getVoiceNameForLanguage` (`driver/VE/driver/__init__.py:277`, `:323`, `:390`; Cerence alike), which the wrappers and the tests `test_f4_engine_adapters.py`, `test_runtime_legacy_adapter.py`, `test_worldvoice_cancel_wrappers.py`, `test_worldvoice_request_manager.py`, `worldvoice_cancel_wrapper_harness.py`, `test_runtime_drain_integration.py:355` and `test_vocalizer_segment_drain.py:724` use; the fake `BaseVoice(id, name, taskManager, …)` of `test_f4_engine_adapters.py:88`; the host modules' own `voiceName`/`voiceInstance`/`speechSequence` (`panels/role.py`, `__init__.py:312`, the wrappers).

**Keyword safety.** NVDA calls the renamed parameters positionally: `Filter.apply` passes the sequence as the first positional argument (`ref/nvda/source/extensionPoints/__init__.py:114`, from `speech/speech.py:1137`); say-all calls the `getTextInfoSpeech` it was given (`speech/sayAll.py:48-60`) through the wrapper's `*args, **kwargs`; WorldVoice's own callers pass the sequence, the voice name, the languages and the voice instance by position (`LanguageDetector(list(...), settings=…)` at `__init__.py:267-272` and in the tests). The one keyword caller of the manager, the synth's `VoiceManager(taskManager=…)`, is updated with it. The SAPI5 wrapper overrides `LeasedPlayer._callback(self, record, onDone)` and calls `_feed_admitted(…, onDone)` positionally (`driver/SAPI5/__init__.py:188-190`); its `onDone` is a host name (mixedCase) and an override's parameter, so it stays.

## 6. Affected layers and files

- New: `tests/test_naming_layers.py`.
- Core: `voices/manager.py`, `pipeline/{breaks,items,languageCommands,numberStages,punctuation,registry,unspaced,sayAll}.py`, `languageDetection/detector.py`, `runtime/segmentHost.py`.
- Host (callers only): `__init__.py`, `globalPlugins/WorldVoice/rolePresenter.py`, `globalPlugins/WorldVoice/panels/detection.py`.
- Tests: `test_f4_voice_state.py`, `test_pipeline_stages.py`, `test_pipeline_voice_lookup.py`, `test_plugin_voice_contract.py`, `test_role_presenter.py`, `test_runtime_composition.py`, `test_settings_order.py`, `test_unicode_panel.py`, `test_voice_manager_roles.py`, `test_voice_settings_transaction.py`, `test_worldvoice_lifecycle.py`, `test_worldvoice_pipeline_settings.py`, `test_worldvoice_speak.py`, `worldvoice_harness.py`.
- Engines: none; every driver stays independently installable. No vendored, sonic, generated or Neural file changes.

## 7. User-visible behavior, UI, strings

None. No panel, label, message, log text (the pipeline's debug lines print the sequence, not the parameter name), setting, gesture or translation changes; no `.po`, readme or changelog edit.

## 8. Settings, compatibility, errors

No config key or setting id changes (rule 3). No compatibility aliases: `VoiceManager` is reached only through the synth (`synth.voice_manager`), and no plugin path exposes it (refactor9 §5.3). Neural (`ref/Neural`) uses only `driver.Voice` and is untouched (47c).

## 9. Test plan

- Guard tests of §4.5 (18 tests); a probe adds a camelCase function to `locales.py` and sees `test_naming_follows_layer` fail, then restores the file.
- Each rename task first removes its names from `TRANSITIONAL_47A` and sees `test_naming_follows_layer` fail with them (red), then renames (green); a commit that renamed without removing the entries would fail `test_lists_hold_only_names_that_break_the_rule`.
- After each rename commit, an order-sensitive token check (`rename_check.py`, embedded in the plan) compares the previous commit with HEAD file by file: every token must be equal, or a name, comment or string token equal to the old one with the task's names renamed; ruff's line breaks and trailing commas are ignored. A leftover `git grep` shows that the old names survive only where §5 says they must.
- Full suite after every commit: 3269 + 18 = 3287 passed, 0 skipped. Existing tests cover behavior through the new names: the manager (`test_runtime_composition.py`, `test_voice_manager_roles.py`, `test_voice_settings_transaction.py`, `test_pipeline_voice_lookup.py`), the role presenter (`test_role_presenter.py`), the synth (`test_worldvoice_speak.py`, `test_worldvoice_pipeline_settings.py`, `test_worldvoice_lifecycle.py`), the pipeline (`test_pipeline_stages.py`, `test_say_all.py`), detection (`test_language_detector.py`), the leased player (`test_segment_host.py`, the SAPI5/RHVoice/eSpeak drain tests).
- No mutmut run: no decision logic changes (§7 asks for it on core decision modules; a rename has no surviving-mutant question).
- Windows/NVDA: nothing new to check by hand; Linux tests do not cover NVDA itself, real audio or engine SDKs.

## 10. Open questions

None open.

1. **Raise the add-on's minimum NVDA version to 2026.1?** Then `typing.override` would be importable everywhere the add-on runs, and 47b could mark NVDA and stdlib overrides with it instead of `INTERFACE_NAMES` entries. **Decided by the user (2026-10-27):** no. The minimum stays NVDA 2024.1 (Python 3.11); `typing.override` is not used; rule 2 stays marked by inheritance the guard reads plus the `INTERFACE_NAMES` table; `test_no_module_imports_typing_override` stays.

## 11. Notes for 47b and 47c

- The host list holds names that are not WorldVoice's to choose and that 47b should move to `INTERFACE_NAMES` (or cover by explicit base classes) rather than rename: `_SilenceGate.is_set` (`threading.Event`), `_SegmentNative.espeak_Synth`/`espeak_ng_Cancel` (the eSpeak DLL binding), the wrappers' `speak_segment`/`get_segment_drain_support` and `_XxxPort` methods (core interfaces implemented structurally; refactor9 suggests explicit Protocol inheritance, which the guard then reads).
- `GlobalPlugin.script_popup_SpeechSettingsDialog` and `script_switch_log_record` are script names; NVDA stores user gesture bindings by script name (`gestures.ini`), so renaming them is rule-3-like and needs a decision or a migration.
- 47c renames `driver.Voice`'s names; the wrappers' `Voice` overrides are exempt today only because the base defines the old names, so the guard will flag every wrapper that 47c misses.
