# Phase 50: VE and Cerence without the "guard not installed" fallback

Date: 2026-10-28.
Base: `master` `0c3aaa7`. Branch: `phase50-vocalizer-no-fallback`.
Source: user decision 2026-10-28 (`storage/refactor9.md` §6 row P50), relayed by the orchestrator.
Status: normal flow (DEVELOPMENT_WORKFLOW.md §3). No approval gates; open points are *Decided by orchestrator with the recommended default; user may override before merge*.

Paths are under `addon/synthDrivers/WorldVoice/` unless stated. VE line numbers are for `driver/VE/__init__.py` at `0c3aaa7`; the Cerence wrapper `driver/Cerence/__init__.py` is the same code (its lines are +0 to +7 later; `tests/test_vocalizer_drift.py:7` pins every difference). Inner lines are for `driver/VE/driver/__init__.py`; the Cerence inner is the same at the same lines.

## 1. Problem

Each VE/Cerence core carries a flag `_guardInstalled` (`:350`, set `True` at `:430`). When it is false, every wrapper entry hands the call to the original inner driver (`return super()…`), the token capability reports false and drain support reports "unsupported". The flag is false only when `_installGuard` (`:407-430`) finds one of five attributes missing or fails to build the player stand-in.

This came from the 2026-09-24 request-lifecycle design (`docs/superpowers/specs/2026-09-24-speech-request-lifecycle-design.md:50`, `:60-61`, `:111`, `:129`, `:149`; commits `bf89f3a` VE, `281dde7` Cerence). Then the wrapper subclassed the inner driver, called the inner `__init__` and *afterwards* checked the inner's private attributes, as a defence against a different inner version. Since then:

- The wrapper no longer calls the inner `__init__`. `_initializeNative` (`:374-405`) is wrapper code that builds the same resources itself; three of the five checked attributes (`self._isSilence`, `self._player`, `self._veCallbackHandler`) are assigned by that wrapper code a few lines earlier (`:388`, `:394`, `:395`).
- The other two-plus-one (`callback._isSilence`, `callback._player`, `callback._feedBuf`) are assigned unconditionally by the vendored inner `VECallback.__init__` (inner `:103-115`; Cerence inner `:103-115`), which `_ContextualVECallback.__init__` calls (`:198`).
- The inner drivers ship inside the add-on (the shipped inner is the tested inner), and `_VEPort.INNER_PRIVATES` (`:65-85`) is pinned against the inner source by `tests/test_native_strategy_guards.py:235-264` (`test_vocalizer_inner_privates_are_listed_and_exist`); all five names are on that list.
- Phase 49 removed `_SilenceGate`; the install is now one assignment of `_IdleRoutingPlayer` (`:423-430`).

So the runtime check catches nothing the tests do not, and the fallback is a second, never-shipped path behind every entry. The other wrappers (OneCore, SAPI5, RHVoice, eSpeak) install unconditionally, with names pinned by tests (`tests/test_native_strategy_guards.py:176-201` for OneCore); a missing name there raises from `__init__` or at use (e.g. RHVoice `driver/RHVoice/__init__.py:306-326` reads `self._inner.player` in `__init__`).

## 2. Goals, non-goals, anti-goals

Goals:

- Remove `_guardInstalled`, every `if not …_guardInstalled` branch, the "guard unavailable" returns and the install-time attribute checks from both wrappers. VE and Cerence change identically.
- After removal, the install has no check and no `except`: a failure in it propagates out of `SynthDriver.__init__`, so `createCore` raises and the voice manager logs the engine error and skips the engine (as for every other wrapper).

Non-goals:

- No runtime private-name check for VE/Cerence (that is phase P51, for the NVDA built-in engines only, whose inner is the user's NVDA).
- The bridge's generic `supportsCancellationToken` capability (`bridge/engineAdapter.py:33-37`, `:117`), the completion policy (`bridge/completionPolicies.py:66-104`) and `runtime/` stay unchanged.
- `_initializeNative` leaking its BgThread when it raises part-way (pre-existing; unrelated to the fallback).

Anti-goals (a failure even if tests pass):

- Any behaviour change on the guarded path, which is the only path a shipped build takes.
- Editing an inner driver (`driver/*/driver/*`), or sharing code between `driver/VE` and `driver/Cerence`.
- A VE/Cerence drift (`tests/test_vocalizer_drift.py` `ALLOWED` changes).

## 3. Inventory: every fallback read, and whether a shipped build reaches it

Reachability argument, used below as **(R)**: `SynthDriver.__init__` (`:349-372`) sets `_guardInstalled = False`, runs `_initializeNative`, then `_installGuard`. Once `__init__` returns, `_installGuard` has set the flag `True` unless (a) one of the five attributes is missing, or (b) `_IdleRoutingPlayer(real, self)` raised.

- (a) cannot happen in a shipped build: `self._isSilence`/`self._player`/`self._veCallbackHandler` are assigned by `_initializeNative` itself (`:388-400`), whose failure raises out of `__init__` before `_installGuard` runs; `callback._isSilence`/`_player`/`_feedBuf` are assigned unconditionally by the vendored inner `VECallback.__init__` (inner `:104-110`), pinned by `_VEPort` (`:65-85`) and `tests/test_native_strategy_guards.py:235-264`.
- (b) cannot happen: `_IdleRoutingPlayer.__init__` (`:100-102`) stores the player and `weakref.ref(driver)`; the same `weakref.ref(self)` already succeeded at `:352` (`_VEStrategy(self)`, `:302-303`) on the same object.
- Before `__init__` returns no guarded entry runs: no speech has been queued, so the native callback (invoked only inside `ve_ttsProcessText2Speech`, from tasks queued by `speak`) cannot fire; `self.availableVoices` (`:403`) reads `_resources` only (inner `:547-551`), not `getParameters`.

| # | Site (VE; Cerence same) | Fallback action | Shipped build |
| --- | --- | --- | --- |
| 1 | `__init__` `:350` `self._guardInstalled = False` | flag default | removed with the flag |
| 2 | `_installGuard` `:408-420` five-attribute check + `log.warning(... using original driver)` | skip install | unreachable (R a) |
| 3 | `_installGuard` `:424-428` `try/except` around the stand-in + `log.warning(... failed)` | skip install | unreachable (R b) |
| 4 | `_installGuard` `:430` `self._guardInstalled = True` | flag | removed with the flag |
| 5 | `supportsCancellationToken` property `:432-434` | `False` | always `True` (R) |
| 6 | `get_segment_drain_support` `:437-438` "guard installation is unavailable" | `DrainSupport(False, …)` | unreachable (R) |
| 7 | `_ContextualVECallback.__call__` `:213-214` → inner `VECallback.__call__` | original callback | unreachable (R) |
| 8 | `_VEStrategy.admission_error` `:307-308` "guard installation is unavailable" | reject segment | unreachable (R) |
| 9 | `speak` `:456-457` → inner `speak` | original | unreachable (R) |
| 10 | `_speak` `:536-537` → inner `_speak` | original | unreachable (R) |
| 11 | `getParameters` `:545-546` → inner | original | unreachable (R); not called during `__init__` |
| 12 | `cancel` `:667-668` → inner | original | unreachable (R) |
| 13 | `_onIndexReached` `:744-745` → inner | original | unreachable (R) |
| 14 | `pause` `:763-764` → inner | original | unreachable (R) |
| 15 | `terminate` `:834-835` → inner | original | unreachable (R); a core whose `__init__` raised is never returned, so never terminated (`driver/__init__.py:87-92`, `bridge/engineAdapter.py:71-72`) |

Cerence lines: 1 `:352`; 2 `:410-422`; 3 `:425-430`; 4 `:432`; 5 `:434-436`; 6 `:439-440`; 7 `:213-214`; 8 `:307-308`; 9 `:458-459`; 10 `:538-539`; 11 `:547-548`; 12 `:674-675`; 13 `:751-752`; 14 `:770-771`; 15 `:841-842`.

Consumers outside the wrappers:

- `bridge/engineAdapter.py:117` reads `supportsCancellationToken` from the **core instance** (`getattr(core, …, False)`) and `_speakPlain` (`:33-37`) calls `speak(commands, cancellationToken=token)` only when it is true. In-tree only the VE and Cerence wrappers define it (grep of `addon/`; the external Neural plugin source `ref/Neural` does not either). It is load-bearing: VE/Cerence take the PLAIN entry whenever unverified drain is off (`bridge/completionPolicies.py:98-103`, `forceUnverifiedDrain`), and without the attribute the bridge would drop the token. So it stays, as a constant (D2).
- `bridge/completionPolicies.py:87-104` calls `get_segment_drain_support`; with row 6 gone VE/Cerence always return `unverified_drain_support(...)` (`runtime/playbackWork.py:40-45`), as they do today in every shipped build.
- `runtime/models.py:91` (`supports_cancellation_token` default `False`) and the bridge tests that build fake cores with either value (`tests/test_runtime_legacy_adapter.py:73-87`, `tests/test_worldvoice_request_builder.py:81`, `tests/runtime_harness.py:264`, `:388`) exercise the generic bridge capability, not the VE fallback. Unchanged.

Tests that build a core where the guard cannot install (`tests/test_worldvoice_cancel_wrappers.py`, both engines via the `engine_harness` fixture):

| Test | Lines | Pins | Action |
| --- | --- | --- | --- |
| `test_missing_private_field_falls_back_without_partial_install` (5 params) | `:76-101` | fallback on a missing attribute | delete |
| `test_missing_callback_falls_back_without_partial_install` | `:104-108` | fallback on a missing callback | delete |
| `test_fallback_delegates_each_original_method` (4 params) | `:111-129` | entries delegate to the inner on fallback | delete |
| `test_assignment_failure_falls_back_unchanged` | `:132-145` | install failure is swallowed | rewrite: install failure raises from the constructor (D1) |
| `test_installs_player_stand_in_and_keeps_inner_stop_flag` | `:62-74` | guarded install (survives) | keep unchanged (`supportsCancellationToken is True` still holds) |

Test helpers: `new_core(missing=None, callback_proxy=None)` in `tests/worldvoice_cancel_wrapper_harness.py:235-262`. `missing` is used only by the three deleted tests; `callback_proxy` has had no caller since `b1c5174` (phase 49). Both go; `new_core()` becomes `wrapped.SynthDriver()` (D4). `tests/test_native_strategy_guards.py:216-232` (`_vocalizer_own_names`) treats names stored in `_installGuard` as the wrapper's own; `_installGuard` stays, still storing `_realPlayer` and `_player`, so that test is unchanged.

Result: nothing on the list is reachable or load-bearing in a shipped build except `supportsCancellationToken`, whose value is already constant there. No stop condition.

## 4. Design

### D1. Install without a check

`_installGuard` keeps its name and becomes:

```python
def _installGuard(self):
	# The inner stop Event and the callback's player stay as created: the
	# guarded callback decides by record validity and feeds _realPlayer.
	self._realPlayer = self._player
	self._player = _IdleRoutingPlayer(self._realPlayer, self)
```

No `hasattr`, no `try/except`, no warning. Anything that raises here (or in `_initializeNative`) propagates out of `SynthDriver.__init__`; `createCore` raises (`driver/__init__.py:87-88`), `VoiceClassAdapter.open` raises (`bridge/engineAdapter.py:71-72`), and `VoiceManager._open_engine` logs `engine VE on error` with the traceback and skips the engine (`voices/manager.py:92-98`). That is how OneCore, SAPI5, RHVoice and eSpeak fail today.

A renamed inner private does not reach this point in a shipped build: the build-time pin (`_VEPort` + `tests/test_native_strategy_guards.py`) fails first. A name read only later (e.g. `callback._pcmBuf` in `_process`) would raise at use, and the wrapper records it on the segment and logs it (`:276-280`), never degrading silently. *Decided by orchestrator with the recommended default; user may override before merge.* Alternative not taken: an explicit construction-time read of every `_VEPort` name, which would be a runtime check like P51's and is what the user ruled out for vendored inners.

The `_installGuard` method stays (rather than inlining into `__init__`) because `tests/test_native_strategy_guards.py:216-232` uses its stores as "own" names; inlining into `_initializeNative` would make that test treat inner names like `_bgQueue` as own and weaken the pin.

### D2. `supportsCancellationToken` becomes a class constant

`supportsCancellationToken = True` as a `SynthDriver` class attribute, replacing the property. The bridge reads it via `getattr` on the instance, which finds the class attribute. Kept rather than removed because the bridge needs it to pass the token (§3). *Decided by orchestrator with the recommended default; user may override before merge.*

### D3. Drain support

`get_segment_drain_support` returns `unverified_drain_support(_PROFILE, "SDK callback quiescence and physical playback are")` unconditionally (the existing guarded return).

### D4. Removed

From each wrapper: the `_guardInstalled` attribute and rows 1-15 of §3 (each `if not …_guardInstalled:` with its `return super()…`, the admission and drain "unavailable" returns, the attribute check and the `try/except` in `_installGuard`). From the tests: the three fallback tests and `new_core`'s `missing`/`callback_proxy` parameters. `log` stays imported (used by `:279`, `:578`, `:805`, `:888`).

Estimated delta: about -37 lines per wrapper.

## 5. NVDA user's view, strings, settings

No audible change: a shipped build always took the guarded path. The only observable difference is that the never-seen warnings `VE cancellation guard unavailable; using original driver` / `VE cancellation guard installation failed` (and the Cerence ones) can no longer be logged. No UI, no translatable strings, no settings, no migration. No readme/changelog entry (no user-visible behaviour change).

## 6. Test plan

- Rewrite `test_assignment_failure_falls_back_unchanged` → `test_install_failure_raises_from_the_constructor` (VE, Cerence): inject a failing `__setattr__` for `_player = _IdleRoutingPlayer(...)`; assert `engine_harness.new_core()` raises `RuntimeError("injected install failure")`. It pins D1 (no swallowing).
- Add `test_wrappers_have_no_guard_fallback` (structural, in `tests/test_native_strategy_guards.py`): for VE and Cerence, the wrapper source has no `_guardInstalled` name and `SynthDriver.supportsCancellationToken is True` as a class constant (AST: a class-level `Assign` of `True`). This keeps the fallback from coming back half-way.
- Delete the three fallback tests (§3).
- Existing guarded-path tests (`tests/test_worldvoice_cancel_wrappers.py`, `tests/test_vocalizer_segment_drain.py`, `tests/test_runtime_drain_integration.py`, `tests/test_runtime_legacy_adapter.py`) run unchanged and must pass: they are the "no behaviour change" proof.
- Expected count: baseline 3379 − 20 deleted test items (fallback: 5+1+4 per engine) + 2 new structural items (one per engine) = 3361 passed, 0 skipped (the rewritten test keeps its two items).

### Mutation testing

Targeted mutants per wrapper on a scratch copy, bytecode off (`PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, `__pycache__` cleared), against `tests/test_worldvoice_cancel_wrappers.py`, `tests/test_vocalizer_segment_drain.py`, `tests/test_native_strategy_guards.py`, `tests/test_runtime_legacy_adapter.py`:

1. Wrap the install in `try/except Exception: return` → killed by `test_install_failure_raises_from_the_constructor`.
2. `supportsCancellationToken = False` → killed by `test_installs_player_stand_in_and_keeps_inner_stop_flag` and the structural test.
3. Drain support returns `DrainSupport(False, …)` → killed by `test_guarded_native_profiles_are_enabled_with_unverified_evidence`.
4. Re-add one `if not getattr(self, "_guardInstalled", True): return super().cancel()` → killed by the structural test.

Windows/NVDA: nothing here can be checked on Windows; a manual check (VE and Cerence speak, cancel, pause) would confirm the same behaviour, but none is required since the shipped path is unchanged.

## 7. Open questions

None blocking. Defaults the user may override: D1 (no runtime check; install failure propagates from the constructor), D2 (keep `supportsCancellationToken` as a class constant), D4 (drop the dead `callback_proxy` harness parameter along with `missing`).
