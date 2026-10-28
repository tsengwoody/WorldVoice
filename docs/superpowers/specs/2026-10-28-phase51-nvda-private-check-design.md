# Phase 51: runtime NVDA-name check and multi-version tests for eSpeak, SAPI5 and OneCore

Date: 2026-10-28.
Base: `master` `2fff780`. Branch: `phase51-nvda-private-check`.
Source: user decision 2026-10-28, option B (`storage/refactor9.md` §6 row P51), relayed by the orchestrator.
Status: normal flow (DEVELOPMENT_WORKFLOW.md §3). No approval gates; open points are *Decided by orchestrator with the recommended default; user may override before merge*.

Paths are under `addon/synthDrivers/WorldVoice/` unless stated. Line numbers are at `2fff780`. NVDA sources are `ref/nvda/source/synthDrivers/...` (a 2027.1 dev checkout, `ref/nvda/source/buildVersion.py:66-67`) or `git -C ref/nvda show release-<v>:source/synthDrivers/...` for a release tag.

## 1. Problem

Three wrappers sit on NVDA's own synth modules, which ship with the user's NVDA and change between NVDA versions:

| Engine | NVDA module(s) | Wrapper |
| --- | --- | --- |
| eSpeak | `synthDrivers._espeak` (module globals), `synthDrivers.espeak.SynthDriver` | `driver/Espeak/__init__.py:6-7`, port `:59-85` |
| SAPI5 | `synthDrivers.sapi5` (module and `SynthDriver`) | `driver/SAPI5/__init__.py:7-8`, port `:39-62` |
| OneCore | `synthDrivers.oneCore` (module and `OneCoreSynthDriver`, aliased `SynthDriver` at `ref/nvda/source/synthDrivers/oneCore.py:188`, `:671`), through the vendored one-method subclass `driver/OneCore/driver/__init__.py:1-9` | `driver/OneCore/__init__.py:10`, `:18`, port `:29-53` |

The add-on declares `addon_minimumNVDAVersion="2024.1"` (`buildVars.py:39`); the last tested version is 2026.1.1 on master (`buildVars.py:41`) and 2026.3 in the user's uncommitted main checkout.

Today nothing checks these names at run time. `Voice.ready()` is the base `return True` (`driver/__init__.py:82-84`). A missing NVDA name raises `AttributeError`:

- at import, if the wrapper reads it in a class statement (SAPI5 `class _SegmentAudioStream(sapi5.SynthDriverAudioStream)` `:135`, `class _SegmentSapiSink(sapi5.SapiSink)` `:243`); discovery then logs `Failed to load ready state for SAPI5: …` (`engineRegistry/discovery.py:223-224`);
- at construction (e.g. SAPI5 `_ensureEngineControl` reads `self._threadCond` `:366-370`); the voice manager logs `engine SAPI5 on error` with a traceback (`voices/manager.py:94-99`);
- or later, at speak time, in a rarely run path.

The names are pinned only against `ref/nvda` (the dev checkout): SAPI5 by `tests/test_native_strategy_guards.py:65-118`, OneCore by `:176-201`, with a whole-word regex over the NVDA source. eSpeak only checks that `_espeak.X` is reached inside `_EspeakPort` (`:23-35`); it has no list.

### 1.1 Finding: SAPI5 needs NVDA 2025.3 or later

Running the existence check of §4 over every NVDA feature release (§5) gives:

| NVDA | eSpeak | SAPI5 | OneCore |
| --- | --- | --- | --- |
| 2024.1, 2024.2, 2024.3, 2024.4 | complete | **22 names missing** (import fails today) | complete |
| 2025.1 | complete | **16 names missing** | complete |
| 2025.2 | complete | **15 names missing** | complete |
| 2025.3, 2026.1, 2026.2, 2026.3beta6, 2027.1 dev | complete | complete | complete |

SAPI5's wrapper re-implements the request-queue worker that NVDA 2025.3 introduced (`_speakThread`, `_threadCond`, `_speakRequests`, `_SapiEvent`, … are absent from `git -C ref/nvda show release-2025.2:source/synthDrivers/sapi5.py`). So **on NVDA 2024.1–2025.2 the SAPI5 engine does not work on `master`** (released 6.2 ran SAPI5 there through NVDA's own driver; the break came with the unreleased `2b3b159`, fix review NI1): on 2024.x the wrapper module fails to import (`SynthDriverAudioStream` is new in 2025.1), on 2025.1–2025.2 its constructor raises. The add-on still declares 2024.1 as its minimum. ~~This phase does not change which versions SAPI5 runs on (option A, a per-entry fallback to NVDA's own behaviour, was not chosen); it turns the failure into a clean, logged skip and pins the boundary in tests.~~ *Correction, decided by the user (2026-10-28):* on these versions SAPI5 uses NVDA's own `sapi5.SynthDriver` as the whole core, as 6.2 did (§4.4); the boundary is pinned in tests. Whether to raise the add-on minimum, or say so in the readme, is a user decision (§9 Q1).

## 2. Goals, non-goals, anti-goals

Goals:

- Each of the three wrappers lists every NVDA name it relies on (§3), and `Voice.ready()` checks that list against the running NVDA. When a name is missing, `ready()` returns `False` (discovery skips the engine) and logs one warning naming the engine, the NVDA version and every missing name. (SAPI5 instead uses NVDA's own driver, §4.4.)
- The same lists, with the same definition of "exists", are checked in tests against `ref/nvda` and against every NVDA feature release from 2024.1 to the newest tag (§5).
- eSpeak gets a list and an existence check like SAPI5 and OneCore.
- The SAPI5 wrapper module imports on every NVDA version, so `ready()` can report instead of discovery logging an import error.

Non-goals:

- ~~No fallback to NVDA's original behaviour (option A).~~ No per-entry branches. *Correction, decided by the user (2026-10-28):* SAPI5 falls back to NVDA's own driver as one whole class, not per entry (§4.4).
- VE, Cerence and RHVoice (their inner driver is vendored and pinned by `tests/test_native_strategy_guards.py:130-143`, `:236-264`).
- Members of NVDA classes other than the synth driver class (SAPI5's subclasses of `sapi5.SapiSink` and `sapi5.SynthDriverAudioStream` override `StartStream`, `ISequentialStream_RemoteWrite`, …), public instance attributes (`self.tts`, `self.player`, `self.sonicStream`, `self.useWasapi`), and the eSpeak DLL exports NVDA calls (`espeak_Synth`, `espeak_ng_Cancel`, proxied at `driver/Espeak/__init__.py:27-56`). See §9 Q2.
- No change to discovery, the voice manager, the plugin contract or the base `Voice`.

Anti-goals (a failure even if the tests pass):

- Any behaviour change on an NVDA version where every name exists: same classes, same construction, no log line.
- A false skip: `ready()` reporting a name missing that the running NVDA has. The runtime definition is therefore the more permissive one (§4.2).
- A test that silently passes when an NVDA tag is not available.

## 3. The lists

Each port class carries three `frozenset` literals (the existing constant style, read by the guards with `ast.literal_eval`):

- `NVDA_MODULE_NAMES`: every attribute the wrapper reads through the NVDA module object (`_espeak.X`, `sapi5.X`, `oneCore.X`), underscore or not. Anything read through a synth module is that module's internal, including the modules it re-exports (`sapi5.config`, `sapi5.nvwave`, `sapi5.hresult`).
- `NVDA_PRIVATES`: underscore members of the NVDA synth class the wrapper reads or writes on `self`/`driver`/`synth` and does not define itself (the existing guard rule, unchanged).
- `NVDA_OVERRIDES`: underscore methods of the NVDA synth class the wrapper's `SynthDriver` overrides (unchanged rule).

| Port | `NVDA_MODULE_NAMES` | `NVDA_PRIVATES` | `NVDA_OVERRIDES` |
| --- | --- | --- | --- |
| `_EspeakPort` (module `_espeak`, class `espeak.SynthDriver`) | `EE_OK`, `_execWhenDone`, `espeakDLL`, `isSpeaking`, `onIndexReached`, `player` | none | `_onIndexReached` (`:166`, `:168`) |
| `_Sapi5Port` (module and class `sapi5.SynthDriver`) | `ISpEventSource`, `ISpNotifySource`, `ISpVoice`, `SapiSink`, `SonicStream`, `SpeechVoiceSpeakFlags`, `SynthDriverAudioStream`, `_SPEventEnum`, `_SapiEvent`, `config`, `hresult`, `nvwave`, `sonicInitialize` | today's list minus `_SPEventEnum`, `_SapiEvent` (they move to module names) | unchanged: `_initTts`, `_initWasapiAudio`, `_onEndStream`, `_speakThread` |
| `_OneCorePort` (module and class `oneCore.SynthDriver`) | `HUNDRED_NS_PER_SEC`, `WAVE_HEADER_LENGTH`, `_OcPreAPI5SsmlConverter`, `_OcSsmlConverter` | today's list minus the two converters | unchanged: `_queueSpeech`, `_processQueue`, `_callback`, `_maybeInitPlayer` |

The guards pin each list exactly: module names equal the set of `<module>.X` attribute reads in the wrapper; privates are a superset of the accessed-and-not-own underscore names (today's `<=` rule); overrides equal the overridden underscore methods that NVDA's class defines.

*Decided by orchestrator with the recommended default; user may override before merge:* module names include public module attributes, not only underscore ones. They are read the same way and fail the same way (a moved `SonicStream` raises at speak time); the check is an exact `hasattr`; on every version where today's private lists are complete, all of them exist too, so this hides no gap.

For OneCore the runtime class is NVDA's `oneCore.SynthDriver`, not the vendored subclass: every listed name is NVDA's (the vendored class defines only `_get_language`/`_set_language`), and the log line then names NVDA's class.

## 4. Design

### 4.1 Where the check lives

New core module `runtime/hostNames.py` (portable core: NVDA-free, snake_case names, refactor9 §6.1; `tests/test_naming_layers.py:51-66`). It knows nothing about NVDA: it checks names on any module and class.

```python
def stored_attribute_names(code: types.CodeType) -> frozenset[str]
def missing_host_names(module, host_class, *, module_names, class_names) -> tuple[str, ...]
def host_names_ready(engine, module, host_class, *, module_names, class_names, host_label, logger) -> bool
```

- `missing_host_names` returns the missing names qualified and sorted: `f"{module.__name__}.{name}"` for module names, `f"{host_class.__module__}.{host_class.__qualname__}.{name}"` for class names.
- `host_names_ready` returns `True` when nothing is missing, without calling `host_label` or logging. Otherwise it logs one warning and returns `False`:

  ```
  Skipping SAPI5 engine candidate: NVDA 2025.1.0 lacks names this engine needs: synthDrivers.sapi5.ISpVoice, …, synthDrivers.sapi5.SynthDriver._threadCond
  ```

  `host_label` is a zero-argument callable so the host version is read only in the skip branch.

Each wrapper (host layer) overrides `Voice.ready()`:

```python
@classmethod
def ready(cls):
	return host_names_ready(cls.engine, <module>, <NVDA class>, module_names=<Port>.NVDA_MODULE_NAMES,
		class_names=<Port>.NVDA_PRIVATES | <Port>.NVDA_OVERRIDES, host_label=_nvdaLabel, logger=log)
```

with a module-level `_nvdaLabel()` that imports NVDA's `versionInfo` inside the function and returns `f"NVDA {versionInfo.version}"` (the same version source the synth passes to drain support, `__init__.py:219`; `versionInfo` star-imports `buildVersion` in every supported release, `git -C ref/nvda show release-2024.1:source/versionInfo.py:12`). The import is local so loading a wrapper needs no new NVDA stub.

Why not elsewhere: drivers must not import each other, so shared code goes to core; `driver/__init__.py` is public plugin API and the drain harnesses stub it with only `Voice` (`tests/espeak_drain_harness.py:223`), so a helper there would break every wrapper load in tests. The three `_nvdaLabel` copies (3 lines each) are the price of independent drivers, as with VE/Cerence.

Log level *Decided by orchestrator with the recommended default*: `warning`. It is a permanent property of the user's environment, not a fault at run time; discovery's other "Skipping … engine candidate" lines are warnings (`engineRegistry/discovery.py:179`, `:183-188`); an error would make NVDA's error sound play at every start on NVDA 2024.1–2025.2 (SAPI5) where logged errors are audible. The prefix matches discovery's lines so one search finds every skip. (SAPI5 no longer skips; its line is `info`, §4.4.)

Interplay: discovery calls `voice.ready()` only for enabled engines, after import (`engineRegistry/discovery.py:162-225`); `False` makes it `continue` without its own log (`:220-221`), so our warning is the only line. An exception in the check would still be caught and logged by discovery (`:223-224`). Nothing else calls `ready()`. A skipped engine contributes no voices, as an uninstalled one does.

### 4.2 One definition of "exists"

Two kinds, the same in the runtime check (live objects) and the tests (compiled source of a release):

| Kind | Live (`missing_host_names`) | Static (tests, compiled source) |
| --- | --- | --- |
| module name | `hasattr(module, name)` | the module body stores the name at top level (`STORE_NAME` in the module code object: assignment, `def`, `class`, `import`, also inside top-level `if`/`try`) |
| class name (privates and overrides) | `hasattr(host_class, name)`, or `name in stored_attribute_names(code)` for the code of any function defined on a class in `host_class.__mro__` (functions, and the functions under `staticmethod`/`classmethod`/`property`) | the class body stores the name (`STORE_NAME` in the class body code object), or `name in stored_attribute_names(class body code)` |

`stored_attribute_names(code)` is the shared primitive: every `STORE_ATTR` target in `code` and in every code object nested in it (methods, inner functions, lambdas), read with `dis.get_instructions`. It is what makes instance attributes created in `__init__` (SAPI5 `_threadCond`, OneCore `_dll`) visible without constructing the driver. Decisions:

- Callables and data are not distinguished; only existence is checked. A removed NVDA method that we override is reported missing (the override would never be called).
- `STORE_ATTR` on any object counts, not only `self`: telling `self` apart needs the instruction before the store, which differs between Python 3.11 (NVDA 2024.1–2025.3) and 3.13 (2026.x); a name NVDA stores on another object of the class's code is accepted. Both views use the same primitive, so they agree.
- Name-mangled names are listed in mangled form (`_Class__name`), which is what both `hasattr` and `STORE_ATTR` see. None are listed today.
- The live view looks through the whole MRO and sees later-bound attributes; the static view sees only the named class and the module body of one file. So the runtime is never stricter than the test (no false skip, §2), and a name the test cannot see in the file fails the test, which is the direction we want for CI. The asymmetry is pinned by a unit test. (The review found two exceptions, written down in `tests/nvda_releases.py`: a module name bound only under `if`/`try` counts statically even when the branch does not run, and a method whose function is not one level below the class attribute (under a decorator that keeps no `__wrapped__`, under two wrapping decorators, or under `staticmethod`/`property` over a wrapping decorator) hides its stores from the live view only. No listed name is bound either way in any covered release; the live view now reads the class attribute's own `__wrapped__`, one level only, without following a chain.)
- `dis` is in NVDA's frozen standard library (NVDA's `logHandler` imports `inspect`, which imports `dis`: `ref/nvda/source/logHandler.py:15`).

The static view lives in a test helper (`tests/nvda_releases.py`), built on `stored_attribute_names`; agreement tests run both views on the same synthetic sources and on `ref/nvda`.

### 4.3 SAPI5 imports on every NVDA

The two class statements read `sapi5.SynthDriverAudioStream` and `sapi5.SapiSink` at import (`:135`, `:243`). They take their base from a module-level helper:

```python
def _nvdaBase(name):
	# ready() refuses the engine when NVDA lacks the class (it is in NVDA_MODULE_NAMES);
	# object only lets this module import so ready() can say so.
	return getattr(sapi5, name, object)
```

On every NVDA that has the class this is the same class as today. A guard checks that none of the three wrappers reads an NVDA module attribute at import time (outside function bodies) except as the argument of `_nvdaBase`; today only these two class statements do.

*Decided by orchestrator with the recommended default:* the placeholder base, rather than leaving 2024.x to discovery's import error. It is not a behaviour fallback: the class is never instantiated, because ~~`ready()` is false~~ `ready()` then chooses NVDA's own driver (§4.4).

### 4.4 SAPI5 on NVDA without the wrapper's names (correction)

*Decided by the user (2026-10-28).* `Voice.ready()` of SAPI5 always returns `True` and chooses the whole core from the same check (`missing_host_names` over `_Sapi5Port`'s three lists; eSpeak and OneCore keep `host_names_ready` and the skip):

| Running NVDA | `Voice.synthDriverClass` | `Voice.drainProfile` | Log |
| --- | --- | --- | --- |
| every listed name exists (2025.3 and later) | the wrapper `SynthDriver` | `DrainProfile(wasapi_dependent=True)` | none |
| a name is missing (2024.1–2025.2) | NVDA's `synthDrivers.sapi5.SynthDriver` | `None` | one `info` line |

`ready()` sets both attributes on every call, so a later check on a complete NVDA restores the wrapper. Everything downstream already handles a plain core: `Voice.createCore()` builds `synthDriverClass()`; `supportedSettings()` reads its settings; `CompletionPolicy.contractFor` returns `CompletionContract()` (LEGACY_DONE) without asking the core and without the fallback warning, because the drain profile is `None`; `VoiceClassAdapter` calls `speak(commands)` without a token, because NVDA's driver has no `supportsCancellationToken`; `voices()`, `voiceInfoToMetadata()` and `applyEngineSettings()` are the base `Voice`'s. No wrapper code runs on this path; `_nvdaBase` only lets the module import on 2024.x.

Log line (`info`: SAPI5 works and nothing needs fixing; an upgrade to 2025.3 or later is the only way to get the drain):

```
SAPI5 engine uses NVDA's own SAPI5 driver, without WorldVoice's segment drain: NVDA 2025.1.0 lacks 16 of the names WorldVoice's SAPI5 driver needs: synthDrivers.sapi5.ISpVoice, …
```

`tests/test_sapi5_old_nvda.py` loads each release's `sapi5.py` from `ref/nvda` behind the SAPI5 harness stubs: 2024.1–2025.2 choose NVDA's driver, which constructs, lists voices, applies settings, speaks, cancels and closes through `VoiceClassAdapter` as a LEGACY_DONE core; 2025.3 and later choose the wrapper with no log line.

## 5. Multi-version tests

Versions: one tag per NVDA feature release in the supported range, the newest tag, and the dev checkout:

`release-2024.1`, `release-2024.2`, `release-2024.3`, `release-2024.4`, `release-2025.1`, `release-2025.2`, `release-2025.3`, `release-2026.1`, `release-2026.2`, `release-2026.3beta6`, and the `ref/nvda` working tree (2027.1 dev).

Why: the four NVDA files never change between a feature release and its point releases (`git -C ref/nvda diff --stat release-X release-X.Y -- <files>` is empty for 2024.3.1, 2024.4.2, 2025.1.2, 2025.3.3, 2026.1.1), so the `.0` tags cover every final release; `release-2026.3beta6` is the newest tag and stands for 2026.3, the version the user tests. This is more than the required 2024.1, 2025.1, 2026.1 and newest, at little cost (40 `git show` reads plus compiles, under a second), and it locates the SAPI5 boundary exactly.

Reading: `git -C ref/nvda show <tag>:source/synthDrivers/<file>`, never a checkout; files `_espeak.py`, `espeak.py`, `sapi5.py`, `oneCore.py`.

Expected results: `FIRST_COMPLETE = {"Espeak": "2024.1", "SAPI5": "2025.3", "OneCore": "2024.1"}`. From that version on, the static check reports nothing missing; before it, it reports at least one name (so the runtime skips the engine). The SAPI5 boundary is the §1.1 finding, pinned so a change in either direction fails.

Missing tag *Decided by orchestrator with the recommended default*: the test fails (no skip; §7 allows skips only for missing optional components) with a message naming the tag and the fix (`git -C ref/nvda fetch --tags`, or use a full clone). `ref/` is already required by about 214 tests. A new NVDA release is added to the table by hand when the user updates `ref/nvda` (the maintenance step the round-5 review suggested for NVDA upgrades); the test does not auto-discover tags, so results do not depend on what a checkout happens to have.

## 6. NVDA user's view, strings, settings

On NVDA 2025.3 and later (every engine complete): no change; no log line.

~~On NVDA 2024.1–2025.2: SAPI5 voices were already missing (import error or constructor traceback); now the log has one warning naming the NVDA version and the missing names, and no traceback. eSpeak and OneCore are unaffected.~~

*Correction, decided by the user (2026-10-28):* on NVDA 2024.1–2025.2, SAPI5 voices are offered and speak through NVDA's own SAPI5 driver, as in WorldVoice 6.2, without WorldVoice's segment drain; the log has one info line naming the NVDA version and the missing names. eSpeak and OneCore are unaffected.

No new translatable strings (log lines are not translated), no settings, no UI, no migration. Readme and changelog: the user chose (a) plus (c) (§9 Q1), so the Notes section of the root readme and of `addon/doc/{ru,uk,zh_CN,zh_HK,zh_TW}/readme.md` ~~states that the SAPI5 engine needs NVDA 2025.3 or later, and each "Next update" changelog has an entry for it~~ (*correction, decided by the user 2026-10-28:* states that on NVDA 2024.1–2025.2 SAPI5 uses NVDA's own driver as in 6.2, without waiting for each part to finish playing, and WorldVoice's own SAPI5 driver only on 2025.3 or later; each "Next update" changelog has an entry for it).

## 7. Test plan

- `tests/test_runtime_host_names.py` (new): `stored_attribute_names` finds stores in methods, nested functions and lambdas, mangled names, ignores loads; `missing_host_names` covers module names present/absent, class attributes, inherited attributes, instance attributes from `__init__` and from another method, properties/static/class methods, sorted qualified output; `host_names_ready` returns `True` without calling the label or logging, and on a miss logs exactly one warning with engine, label and names and returns `False`.
- Agreement: synthetic sources executed into a module (live) and compiled (static) give the same missing tuple; the documented asymmetry (a name inherited from a base outside the file) is pinned.
- `tests/test_native_strategy_guards.py`: eSpeak list test (module names equal the `_espeak.X` reads; overrides equal the overridden NVDA methods); SAPI5 and OneCore tests read the three constants; module names equal the `sapi5.X`/`oneCore.X` reads; the import-time guard.
- `tests/test_nvda_release_names.py` (new): parametrized over engine × version (§5) with the static view; a missing tag fails with the message.
- Live `ready()` on `ref/nvda` through the drain harnesses (`tests/espeak_drain_harness.py`, `sapi5_drain_harness.py`, `onecore_drain_harness.py`): `ready()` is `True` with no warning; with one listed name deleted from the live module or class it is `False` with one warning naming the NVDA version and that name (SAPI5: `True`, NVDA's own driver, one `info` line, §4.4); live and static views agree on `ref/nvda`.

Mutation: `runtime/hostNames.py` is a new core decision module, so it gets a mutation run (scratch copy, textual mutants, bytecode off, per-run timeout); survivors and reasons go in §10.

Windows: nothing here runs on Windows or a real NVDA. Manual items for the user: on NVDA 2025.3+ all three engines list voices and speak, with no "Skipping … engine candidate" line in the log; on an NVDA 2024.x or 2025.1/2025.2 install (if available), ~~the log shows one SAPI5 skip line~~ SAPI5 voices are listed, speak and stop on cancel, the log shows one SAPI5 info line ("SAPI5 engine uses NVDA's own SAPI5 driver …"), and eSpeak/OneCore work.

## 8. Risks

- `dis` output on NVDA's Python 3.11/3.13 versus the tests' 3.14: only `STORE_ATTR` and `STORE_NAME` are used; both exist with the same meaning in all three.
- A name NVDA binds only through `setattr(self, "x", …)` or a mixin outside its MRO would be a false skip. None of the listed names is bound that way in any covered version (the static test would fail first, since its view is stricter).

## 9. Open questions (for the user)

1. **SAPI5 on NVDA 2024.1–2025.2** (§1.1). Today it is broken there; after this phase it is cleanly skipped with a log line. Options: (a) keep it so (recommended for this phase; no behaviour change); (b) raise `addon_minimumNVDAVersion` to 2025.3 (affects eSpeak/OneCore users on older NVDA too); (c) note in the readme that SAPI5 needs NVDA 2025.3+; (d) support the pre-2025.3 SAPI5 driver separately (a large phase). ~~*Decided by the user (2026-10-28): (a) and (c) — SAPI5 stays skipped on NVDA < 2025.3 with the minimum at 2024.1, and the readmes say SAPI5 needs NVDA 2025.3 or later.*~~ *Decided by the user (2026-10-28), replacing the line above after fix review NI1 showed that 6.2 ran SAPI5 on these versions:* on NVDA < 2025.3, SAPI5 uses NVDA's own `synthDrivers.sapi5.SynthDriver` as the whole core, like 6.2 (§4.4); the minimum stays 2024.1; the readmes say so.
2. Coverage beyond the synth class (§2 non-goals): members of `sapi5.SapiSink`/`SynthDriverAudioStream` the wrapper overrides, public instance attributes, and the eSpeak DLL calls NVDA makes. All exist on every version where the lists are complete; a follow-up could add them. *Decided by orchestrator with the recommended default: out of scope.*

## 10. Implementation notes

Commits `94445d6`..`a81967e` on top of the spec/plan. Full suite 3363 → 3428 passed, 0 skipped. `prek run --all-files` Passed; `git diff --check` clean; protected paths and Neural empty.

Rulings (deviations from §4 and the plan):

- The static module view counts top-level `STORE_GLOBAL` as well as `STORE_NAME`: Python 3.14 compiles `_espeak.py`'s module globals (declared `global` in its functions) to `STORE_GLOBAL` at module level. Both bind a module attribute; the synthetic agreement source pins it.
- `_OneCorePort.NVDA_MODULE_NAMES` also lists `SynthDriver`: `ready()` reads `oneCore.SynthDriver`, and the module-read guard is exact. If it were missing, the argument would raise before the check, but the vendored inner imports it at module load, so that cannot happen first.
- The module-read guard counts SAPI5's `_nvdaBase("X")` as a read of `sapi5.X`.
- Missing names are sorted as plain strings, so class entries (`…SynthDriver._x`) come before lowercase module entries.
- The engine table and the port reader moved into `tests/nvda_releases.py` in Task 4, because the `ref/nvda` agreement test needs them.
- `object` is no longer skipped in the live MRO walk (an equivalent mutant: it has no code).
- Mutation run: hand-written textual mutants on a scratch copy (as in phase 49), not mutmut. The targeted test files run in seconds, where mutmut would run the whole suite per mutant.

Results per NVDA version: exactly §1.1. Missing on SAPI5: 2024.1–2024.4: `ISpEventSource`, `ISpNotifySource`, `ISpVoice`, `SonicStream`, `SynthDriverAudioStream`, `_SPEventEnum`, `_SapiEvent`, `hresult`, `sonicInitialize` and `SynthDriver.` `_bookmarkLists`, `_initWasapiAudio`, `_isCancelling`, `_isCompleted`, `_isSpeaking`, `_isStoppingThread`, `_onEndStream`, `_requestCompleted`, `_requestsAvailable`, `_speakRequests`, `_speakThread`, `_thread`, `_threadCond` (22); 2025.1: `ISpVoice`, `_SPEventEnum`, `_SapiEvent` and the same 13 class names (16); 2025.2: the same without `_initWasapiAudio` (15). eSpeak and OneCore: nothing missing on any version.

Mutation (`runtime/hostNames.py` and two wrapper mutants; tests `test_runtime_host_names.py`, `test_nvda_release_names.py`, `test_nvda_ready.py`, `timeout 300`, bytecode off): 18 mutants, 18 killed after three tests were added for the first run's survivors (decorated property setter/deleter: `fset`, `fdel`; `__qualname__` vs `__name__` for a nested class). Mutants: MRO walk reduced to the class itself; no nested-code recursion; `STORE_ATTR`→`LOAD_ATTR`; no `__func__`; no `fget`/`fset`/`fdel`; module `hasattr` negated; no sorting; `error` instead of `warning`; label read eagerly; `True` on missing; class `hasattr` skipped; stored names ignored; `__qualname__`→`__name__`; `", "`→`" "`; SAPI5 `ready()` without overrides; `_nvdaBase` without the default.
