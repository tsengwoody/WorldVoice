# Phase 52: shared segment-barrier names, and token support in `Voice.extraCapabilities`

Date: 2026-10-28.
Base: `master` `4ca7e42`. Branch: `phase52-shared-barriers`.
Source: user decision 2026-10-28 (`storage/refactor9.md` §6 row P52), relayed by the orchestrator.
Status: normal flow (DEVELOPMENT_WORKFLOW.md §3), renames proven by order-sensitive token checks (§3.2 "改名與搬移的證明"). No approval gates; open points are *Decided by orchestrator with the recommended default; user may override before merge*.

Paths are under `addon/synthDrivers/WorldVoice/` unless stated. Line numbers are at `4ca7e42`. The Cerence wrapper is the VE wrapper with the drift pinned by `tests/test_vocalizer_drift.py`; Cerence lines are given where they differ.

## 1. Problem

### 1.1 Barrier names

A *barrier* is a string label that a wrapper declares on each `NativeRecord` and later marks reached; `SegmentHost` treats the labels opaquely. A record is created with `dict.fromkeys(<declared names>, False)` (`runtime/segmentHost.py:327-336`), `reach` flips one to `True` and raises `KeyError` for an undeclared name (`:426-430`), and a record that retires with a `False` entry fails with `"<engine> synthesis retired without its <names> barriers"` (`:525-526`, `:585-586`, `:591-593`). `LeasedPlayer.idle` reaches its `idle_barrier` after the real `idle()` returns (`:679-682`, `:741-742`); the default is `"idle"`.

Each wrapper names its own evidence:

| Engine | Declared (strategy / ordinary) | Reach sites |
| --- | --- | --- |
| eSpeak | `{"returned", "ended", "idle"}` (`driver/Espeak/__init__.py:109`); ordinary = strategy | `"returned"` `:64`; `"ended"` `:182`; `"idle"` via `LeasedPlayer` default (`:86`) |
| RHVoice | `{"message", "done", "returned", "idle"}` (`driver/RHVoice/__init__.py:265`); ordinary = strategy | `"message"` `:131`; `"returned"` `:146`; `"idle"` `:250`; `"done"` `:349`; read `record.barriers["done"]`/`["returned"]` `:242-243` |
| SAPI5 | `{"ended", "processed", "idle"}` (`driver/SAPI5/__init__.py:102`); `_ORDINARY_BARRIERS = {"ended", "processed"}` (`:19`) | `"idle"` `:165`; `"ended"` `:377`; `"processed"` `:513`, `:528`; read `.get("processed")` `:261`, `["ended"]` `:515`; `idle_barrier=None` `:201` |
| OneCore | `{"callback", "synced"}` (`driver/OneCore/__init__.py:124`); `_ORDINARY_BARRIERS = {"callback"}` (`:28`) | `"synced"` `:190`; `"callback"` `:439`, `:452` |
| VE / Cerence | `{"spoken", "idle"}` (`driver/VE/__init__.py:298`); `_ORDINARY_BARRIERS = frozenset()` (`:48`) | `"idle"` `:341` (Cerence `:343`); `"spoken"` `:504-505` (Cerence `:506-507`) |

So the same idea has up to four names (`callback`, `processed`, `spoken`, `returned`), an error log cannot be compared across engines, and a reader has to open each wrapper to learn what a label proves.

### 1.2 Token support

The bridge decides whether the plain entry passes the request's token from a property of the opened core: `supports_cancellation_token=bool(getattr(self._core, "supportsCancellationToken", False))` (`bridge/engineAdapter.py:117`), read by `_speakPlain` (`:33-37`). Only VE and Cerence define it, as the class constant `True` since phase 50 (`driver/VE/__init__.py:345`, `driver/Cerence/__init__.py:347`; commit `3909886`). It was a per-instance property because, before phase 50, a VE/Cerence core whose guard failed to install fell back to the original inner driver, whose `speak` takes no token; phase 50 removed that path. The other engine traits the bridge needs already come from the plugin contract's class attribute `Voice.extraCapabilities` (`bridge/engineAdapter.py:112-116`; `driver/__init__.py:26`; VE/Cerence declare `{"waitfactor", "variant"}`, `driver/VE/__init__.py:873`, `driver/Cerence/__init__.py:880`).

## 2. Goals, non-goals, anti-goals

Goals:

- **Part 1.** Meaning-named shared barrier constants in a new core module `runtime/barriers.py`; every wrapper declares and reaches a barrier of a shared kind through the constant. Barriers whose meaning differs from every shared kind keep an engine-specific name, listed in a guard test with the reason.
- **Part 2.** Token support becomes the optional plugin-contract value `"cancellationToken"` in `Voice.extraCapabilities`; the bridge reads it from there; VE/Cerence drop `supportsCancellationToken`.

Non-goals:

- No change to which barriers a record carries (only their spelling), to where they are reached, or to `SegmentHost`'s handling.
- No change to `EngineCapabilities.supports_cancellation_token` (`runtime/models.py:91`) or to the completion policy.
- The engine-specific names keep their current spelling (`"message"`, `"processed"`, `"callback"`, `"synced"`) and stay literals in their wrappers: one wrapper uses each, and the guard lists them.

Anti-goals (a failure even if tests pass):

- Any behaviour change: a different set of barriers on any record, a reach moved, the token passed to a core that did not get it before, or withheld from one that did.
- Merging two barriers whose evidence proves different things (§3.2).
- Editing an inner driver (`driver/*/driver/*`) or `ref/`; importing one wrapper from another; VE/Cerence drift (`tests/test_vocalizer_drift.py` `ALLOWED` unchanged).
- Losing guard coverage silently in a rename (e.g. a test table or dict key still spelled the old way, so a check no longer matches anything).

## 3. Part 1 — the classification

> **Decided by the user (2026-10-28): option B′.** Classify each barrier by what its evidence proves, rename the constant whose definition changes, and let the host enforce the one invariant that matters. §3.5 is the classification in force. §3.1–§3.4 are the first version, kept for the record; struck-through text there no longer holds.

### 3.1 The shared kinds

`runtime/barriers.py` (portable core; constants are upper case under §6.1 in every layer; module name follows the `runtime/` file names `segmentHost.py`, `hostNames.py`):

| Constant | Value | Meaning (what is true once reached) |
| --- | --- | --- |
| ~~`SYNTHESIZED`~~ | ~~`"synthesized"`~~ | ~~Every native synthesis call the engine made for this record has returned. These engines synthesize synchronously, so all of the record's audio callbacks ran (and fed the player) inside those calls.~~ Replaced by `AUDIO_FED` (§3.5). |
| `ENGINE_DONE` | `"engine_done"` | The engine's own end-of-utterance notification for this record arrived. |
| `PLAYED_OUT` | `"played_out"` | ~~`WavePlayer.idle()` returned for this record: its audio finished playing (`idle` first calls `sync`, `ref/nvda/source/nvwave.py:370-378`) and the continuous segment was closed (leading-silence trimming re-armed, ducking released, `:379-382`).~~ Redefined in §3.5. |

The values are the meanings, so `"VE synthesis retired without its played_out barriers"` reads the same for every engine (refactor9 P52: "錯誤 log 可跨引擎比較").

### 3.2 Every existing barrier

> First version (pre-phase names → phase 52 names). Under option B′ every `SYNTHESIZED` below reads `AUDIO_FED`, and the SAPI5 `"processed"` and OneCore `"callback"`/`"synced"` rows are replaced (§3.5).

| Engine | Old | New | Evidence | Why |
| --- | --- | --- | --- | --- |
| eSpeak | `"returned"` | `SYNTHESIZED` | `espeak_Synth` returned (`driver/Espeak/__init__.py:47-64`, reached in `finally`). NVDA initializes eSpeak with `AUDIO_OUTPUT_SYNCHRONOUS` (`ref/nvda/source/synthDrivers/_espeak.py:371-372`), so its callback (`:151-195`) runs inside `espeak_Synth`. | Synchronous call returned. On a failed or raising call it is still reached, but the error is recorded first (`:57-61`) and an error takes precedence over the barrier check (`runtime/segmentHost.py:525`), so the record fails either way, as today. |
| eSpeak | `"ended"` | `ENGINE_DONE` | NVDA's final callback with no audio calls `onIndexReached(None)` (`_espeak.py:172-176`); the wrapper reaches it for index `None` (`driver/Espeak/__init__.py:181-182`). | Engine's terminal notification. |
| eSpeak | `"idle"` | `PLAYED_OUT` | NVDA's final callback calls `player.idle()` (`_espeak.py:173`) on the `LeasedPlayer` installed at `driver/Espeak/__init__.py:85`, which reaches its default `idle_barrier`. | `WavePlayer.idle()` returned. |
| RHVoice | `"message"` | `"message"` (engine-specific) | `RHVoice_new_message` returned a message (`driver/RHVoice/__init__.py:125-136`). | A precondition of synthesis, not its completion; no other engine has a separate "message created" step. It is RHVoice's second piece of evidence in the synthesis category, so it cannot share `SYNTHESIZED`. |
| RHVoice | `"returned"` | `SYNTHESIZED` | `RHVoice_speak` returned success (`:138-150`); the inner `SpeakText.__call__` calls it synchronously and its audio/done callbacks run inside it (`driver/RHVoice/driver/__init__.py:395-411`). | Synchronous call returned. |
| RHVoice | `"done"` | `ENGINE_DONE` | The native done callback ran (`driver/RHVoice/__init__.py:334-349`; inner `DoneCallback` `driver/RHVoice/driver/__init__.py:343-353`). | Engine's terminal notification. |
| RHVoice | `"idle"` | `PLAYED_OUT` | The worker calls `owner._inner.player.idle()` after the task, then reaches (`driver/RHVoice/__init__.py:240-250`). | `WavePlayer.idle()` returned. |
| SAPI5 | `"ended"` | `ENGINE_DONE` | The COM sink's `EndStream` event (`driver/SAPI5/__init__.py:363-377`). | Engine's terminal notification. |
| SAPI5 | `"processed"` | `"processed"` (engine-specific) | SAPI5 speaks with `SpeechVoiceSpeakFlags.Async` (`:577-580`), so no synthesis call returns at completion. `processed` is reached after the worker, *following* `EndStream`, flushed Sonic, fed the remaining audio and ran `_onEndStream` (tail bookmarks, `_isSpeaking`) (`:592-602`, `:506-528`; it raises if `ended` is missing, `:515-516`). | It proves the wrapper's post-end-of-stream processing, which depends on `ENGINE_DONE`; that is not "a synchronous synthesis call returned". |
| SAPI5 | `"idle"` | `PLAYED_OUT` | `drain` calls `player.idle()` and reaches (`:149-165`). | `WavePlayer.idle()` returned. |
| OneCore | `"callback"` | `"callback"` (engine-specific) | `ocSpeech_speak` is asynchronous (`ref/nvda/source/synthDrivers/oneCore.py:462-465`); the native callback delivers the whole WAV once, and the wrapper reaches `callback` inside it after feeding every chunk and index (`driver/OneCore/__init__.py:387-439`, legacy `:450-452`). | Proof comes from inside the delivery callback, not from a returned synthesis call; it is also OneCore's only terminal notification. Neither `SYNTHESIZED` nor `ENGINE_DONE` describes it exactly. |
| OneCore | `"synced"` | `"synced"` (engine-specific) | `drain` calls `player.sync()` only (`:176-190`). | `sync` is a different `WavePlayer` operation from `idle`: it waits for playback but does not close the continuous segment (`nvwave.py:370-382`). OneCore calls `idle` only on its legacy queue-empty path (`driver/OneCore/__init__.py:455-465`). |
| VE / Cerence | `"spoken"` | `SYNTHESIZED` | `_Retire` (`driver/VE/__init__.py:161-165`) runs on the inner BgThread after every task the inner `speak` queued for the record, each a synchronous `ve_ttsProcessText2Speech` (`:127-131`, `:168-177`); `_retireRecord` reaches it when the record is still valid (`:502-505`). | Every synchronous synthesis call for the record returned. |
| VE / Cerence | `"idle"` | `PLAYED_OUT` | `drain` calls `driver._realPlayer.idle()` and reaches (`:323-341`). | `WavePlayer.idle()` returned. |
| (runtime) | `LeasedPlayer(idle_barrier="idle")` default | `PLAYED_OUT` | `runtime/segmentHost.py:679`, `:741-742`. | Same kind as above. |

Resulting declarations (sets unchanged in size and membership up to spelling):

| Engine | Strategy `barriers` | Ordinary |
| --- | --- | --- |
| eSpeak | `{SYNTHESIZED, ENGINE_DONE, PLAYED_OUT}` | (strategy) |
| RHVoice | `{"message", ENGINE_DONE, SYNTHESIZED, PLAYED_OUT}` | (strategy) |
| SAPI5 | `{ENGINE_DONE, "processed", PLAYED_OUT}` | `{ENGINE_DONE, "processed"}` |
| OneCore | `{"callback", "synced"}` | `{"callback"}` |
| VE / Cerence | `{SYNTHESIZED, PLAYED_OUT}` | `frozenset()` |

~~OneCore uses no shared constant: both its barriers differ in meaning (above). It is still covered by the guard.~~

~~**Decided by orchestrator with the recommended default; user may override before merge:** the alternative is to classify by the claim "all of this record's audio is in the player" and merge OneCore `callback` and SAPI5 `processed` into `SYNTHESIZED` (and OneCore `synced` into `PLAYED_OUT`). That loses the distinction the user asked to keep (refactor9 P52: "callback 和 returned 的證據不同", "sync 和 idle 行為不同"); switching later is a one-line change per wrapper plus the guard table.~~

**Decided by the user (2026-10-28): option B′** (§3.5). The distinction the user asked to keep is kept in the definitions and comments instead of in the names: `AUDIO_FED` lists each engine's different evidence, and `PLAYED_OUT` says that only `idle()` closes the continuous segment.

### 3.3 Where the strings appear

Error messages and logs only (`runtime/segmentHost.py:591-593`). They are never stored in configuration, never compared by the bridge, the scheduler or the UI (`grep` of `addon/` for the old literals: only the wrapper lines in §1.1 and `runtime/segmentHost.py:679`). Record dict iteration order already follows the declared `frozenset`, so the order of names in the error message is unchanged in kind. Tests: only `tests/test_segment_host.py` spells barrier names (its fake strategy, `:22`, and the expected message at `:150`); the engine drain tests never name a barrier (their `"idle"` parameters are fault names, e.g. `tests/test_espeak_segment_drain.py:52`). `tests/test_segment_host.py`'s `"idle"` must become `"played_out"` with the runtime default, because its `LeasedPlayer` tests (`:372-385`, `:405-410`, `:626-630`) run against the fake's declared names; its other names (`"returned"`, `"done"`, `"ended"`) stay: they are the fake's own opaque labels.

### 3.4 How the renames are made

By script, with explicit `OLD=NEW` token lists, one commit per group, each passing the order-sensitive token check (§7.2). Groups follow the coupling, so the suite passes after each:

1. **G1 — runtime + eSpeak + host tests.** `runtime/segmentHost.py` (`"idle"`→`PLAYED_OUT`), `driver/Espeak/__init__.py` (`"returned"`→`SYNTHESIZED`, `"ended"`→`ENGINE_DONE`, `"idle"`→`PLAYED_OUT`), `tests/test_segment_host.py` (`"idle"`→`"played_out"`, `"Fake synthesis retired without its idle barriers"`→`"Fake synthesis retired without its played_out barriers"`). Coupled: eSpeak's `idle` is reached by the runtime default.
2. **G2 — RHVoice.** `"returned"`→`SYNTHESIZED`, `"done"`→`ENGINE_DONE`, `"idle"`→`PLAYED_OUT`. `"message"` kept. (Its `_WavePlayer` takes the `LeasedPlayer` default but overrides `idle()` without reaching it, `driver/RHVoice/__init__.py:199-206`, so G1 does not affect it.)
3. **G3 — SAPI5.** `"ended"`→`ENGINE_DONE`, `"idle"`→`PLAYED_OUT`. `"processed"` kept.
4. **G4 — VE + Cerence** (one commit: the drift test compares them). `"spoken"`→`SYNTHESIZED`, `"idle"`→`PLAYED_OUT`.

OneCore needs no rename. Each renamed file gains exactly one import statement from `runtime/barriers.py`; the token check allows that statement and nothing else. `runtime/barriers.py` itself is added in its own commit before G1; the guard test after G4.

### 3.5 Option B′ (fix round, in force)

`runtime/barriers.py`:

| Constant | Value | Meaning (what is true once reached) |
| --- | --- | --- |
| `AUDIO_FED` | `"audio_fed"` | All of this record's audio has been fed to the player, and no further audio callback for it will come. Evidence per engine: a synchronous synthesis call returned (eSpeak, RHVoice, VE/Cerence); the asynchronous delivery callback fed every chunk (OneCore); the SAPI5 worker flushed Sonic and fed the tail after EndStream (SAPI5). |
| `ENGINE_DONE` | `"engine_done"` | The engine's own end-of-utterance notification for this record arrived. Optional: VE/Cerence and OneCore have no separate terminal notification; OneCore's delivery callback is also its terminal notification. |
| `PLAYED_OUT` | `"played_out"` | The player has played all of this record's audio, proven by `WavePlayer.idle()` returning, or by `sync()` returning plus the engine's own unpause wait. Only `idle()` also closes the continuous segment (re-arms leading-silence trimming, releases ducking); OneCore's segment mode only calls `sync()` and never closes it (see its `drain`). This barrier does not guarantee those side effects. |

RHVoice `"message"` stays engine-specific: a precondition, not completion. It is the only engine-specific barrier left.

Changes from §3.2:

| Engine | Phase 52 first version | Option B′ |
| --- | --- | --- |
| eSpeak, RHVoice, VE/Cerence | `SYNTHESIZED` | `AUDIO_FED` (pure rename) |
| SAPI5 | `"processed"` | `AUDIO_FED`; a comment before the ENGINE_DONE-required raise says `AUDIO_FED` must follow `ENGINE_DONE` |
| OneCore | `"callback"` | `AUDIO_FED`; the delivery-callback reach notes it is also OneCore's only terminal notification (there is no `ENGINE_DONE`) |
| OneCore | `"synced"` | `PLAYED_OUT`; the drain reach notes that `sync()` is not `idle()` and does not close the continuous segment |

eSpeak's reach of `AUDIO_FED` moves from the `finally` of `espeak_Synth` to its success path, so the reach matches the definition. Behaviour is unchanged: a failure is recorded on the record before the exception propagates, and both retire and the drain check report a recorded error ahead of any missing barrier.

Resulting declarations (membership unchanged; only spelling):

| Engine | Strategy `barriers` | Ordinary |
| --- | --- | --- |
| eSpeak | `{AUDIO_FED, ENGINE_DONE, PLAYED_OUT}` | (strategy) |
| RHVoice | `{"message", ENGINE_DONE, AUDIO_FED, PLAYED_OUT}` | (strategy) |
| SAPI5 | `{ENGINE_DONE, AUDIO_FED, PLAYED_OUT}` | `{ENGINE_DONE, AUDIO_FED}` |
| OneCore | `{AUDIO_FED, PLAYED_OUT}` | `{AUDIO_FED}` |
| VE / Cerence | `{AUDIO_FED, PLAYED_OUT}` | `frozenset()` |

**Host check.** `SegmentHost.__init__` no longer refuses only an empty set: it refuses a strategy whose `barriers` lack `PLAYED_OUT` (`ValueError(f"{engine} strategy declares no played-out barrier")`), because a segment must not drain before its audio has played. Ordinary `enqueue(barriers=…)` sets are not subject to it (VE's is empty). Every strategy satisfies it after the renames, so this is the only behaviour change and no engine is affected.

**Guards.** `tests/test_native_strategy_guards.py` reads the engines from `driver/` (every package whose `__init__.py` defines a `*Strategy` class; `sonic` is listed as a non-engine package, and a locally restored untracked `Neural` is skipped), requires a declared-set row for each, lists only `RHVoice: {"message"}` as engine-specific, and asserts every strategy declares `AUDIO_FED` and `PLAYED_OUT` by their constants.

## 4. Part 2 — `"cancellationToken"` in `Voice.extraCapabilities`

- `driver/__init__.py`: `Voice.extraCapabilities` stays `frozenset()`; a comment names the recognized optional values: `"waitfactor"`, `"variant"`, `"cancellationToken"` (the core's `speak(commands, cancellationToken=token)` accepts the request's token).
- `bridge/engineAdapter.py:117`: `supports_cancellation_token="cancellationToken" in extra`.
- `driver/VE/__init__.py:873`, `driver/Cerence/__init__.py:880`: `extraCapabilities = frozenset({"waitfactor", "variant", "cancellationToken"})`; delete `supportsCancellationToken = True` (`:345`, `:347`). Both `speak` methods already take `cancellationToken=None` (`:448`, `:450`).
- Value spelling: `"cancellationToken"`, the keyword it governs (the brief's example). Host-layer string; not a Python identifier, so the naming guard (`tests/test_naming_layers.py`) is unaffected.

**Rule change, made deliberately.** `tests/test_runtime_legacy_adapter.py:73-88` pins "class claims are not authoritative, the core instance is" (`:79`). That rule protected the pre-phase-50 VE/Cerence fallback core, whose token support depended on the instance. With the fallback gone (phase 50) token support is a fixed trait of the engine class, like `waitfactor` and `variant`. The new rule: **the Voice class's `extraCapabilities` is authoritative; a `supportsCancellationToken` attribute on the core is ignored.** The test is rewritten to pin that (declared → token passed; not declared → plain `speak(commands)` even when the core carries `supportsCancellationToken = True`).

Compatibility: old plugins (`ref/Neural`, `ref/IBM`, `ref/Aisound`) declare neither `extraCapabilities` nor `supportsCancellationToken` (grep of `ref/` outside `ref/nvda`), so they keep `speak(commands)`. The only reader of `supports_cancellation_token` is `_speakPlain` (grep of `addon/`), which runs only on an opened adapter, so the value now also being `True` before `open()` changes nothing.

**SAPI5 on NVDA < 2025.3** (phase 51): `Voice.ready()` swaps `synthDriverClass` to NVDA's own `sapi5.SynthDriver` (`driver/SAPI5/__init__.py:694-719`), whose `speak` takes no token. SAPI5's `Voice` declares no `extraCapabilities` (inherits `frozenset()`), so neither core receives a token. Guard: a wrapper `Voice` that declares `"cancellationToken"` must have its own `SynthDriver.speak` accepting `cancellationToken`, and must not reassign `synthDriverClass` (only SAPI5 does); `tests/test_sapi5_old_nvda.py:191-244` additionally asserts `"cancellationToken" not in voice.extraCapabilities` on every old release.

## 5. NVDA user-visible changes

None. Speech, settings, panels and stored configuration are unchanged. Only the barrier names inside an internal error message in the NVDA log change (e.g. `idle` → `played_out`). No new or changed translatable strings; no readme/changelog entry (no behaviour change; the plugin contract's new optional value is not documented in the readme today, `grep extraCapabilities addon/doc readme.md` finds nothing).

## 6. Error handling, configuration, migration

No configuration or migration. `reach` with an undeclared name still raises `KeyError`; a missing barrier still fails the segment with the same message shape.

## 7. Tests

### 7.1 New and changed tests

- `tests/test_segment_barriers.py` (new): the three constants exist with the §3.1 values, are distinct, and `runtime/barriers.py` imports nothing (portable core).
- `tests/test_native_strategy_guards.py` (new guard): for each of the six wrappers, every barrier expression — elements of a `*Strategy.barriers` and `_ORDINARY_BARRIERS` `frozenset`, the second argument of each `.reach(...)` call, `idle_barrier=` arguments, keys read from `.barriers` (`x.barriers[k]`, `x.barriers.get(k)`, `k in x.barriers`) — is either a name imported from `runtime.barriers` or a string in that engine's listed engine-specific names (`OneCore: {"callback", "synced"}`, `SAPI5: {"processed"}`, `RHVoice: {"message"}`). The test also pins each strategy's declared set (§3.2 table) so a dropped or added barrier fails, checks that every listed engine-specific name is still used (no stale entry), that no engine-specific name equals a shared value, and that `LeasedPlayer`'s default `idle_barrier` is `PLAYED_OUT`.
- `tests/test_runtime_legacy_adapter.py:73-88`: rule change (§4). `:555-576` (`test_bridge_passes_the_token_to_the_real_vocalizer_wrapper`, phase 50 M3): still proves the real VE/Cerence core receives the token through `_speakPlain`; additionally asserts the core has no `supportsCancellationToken` and the class declares `"cancellationToken"`.
- `tests/test_native_strategy_guards.py:306-319` (`test_vocalizer_wrapper_has_no_guard_fallback`): the class-constant assertion becomes "the wrapper's `Voice.extraCapabilities` contains `"cancellationToken"` and `SynthDriver` assigns no `supportsCancellationToken`"; plus the §4 guard over all six wrappers.
- `tests/test_worldvoice_cancel_wrappers.py:64`, `tests/test_worldvoice_request_builder.py:72-100,215-217`, `tests/runtime_harness.py:261-264,442-466`: fakes declare support through `Voice.extraCapabilities` instead of a core attribute (their assertions otherwise unchanged).
- `tests/test_sapi5_old_nvda.py`: the old-NVDA bridge test asserts the Voice does not declare `"cancellationToken"`.

### 7.2 Rename proof

A scratchpad script tokenizes the file at the parent commit and in the commit (Python `tokenize`, every token including comments), drops from the new stream exactly the one allowed `import` statement from `runtime/barriers.py`, applies the commit's `OLD=NEW` list to the old stream (exact token text, so `"idle"` the string never matches `idle` the name, and a longer string containing `idle` is a different token), and requires the two sequences to be equal in type, text and order. It reports how many tokens each pair replaced, and lists same-spelling tokens deliberately kept (e.g. `self._player.idle()`, `"message"`, `"processed"`, `"returned"` in `tests/test_segment_host.py`). Commands and results go into the ledger; the reviewer reruns them.

### 7.3 Mutation

On a scratch copy (`PYTHONDONTWRITEBYTECODE=1`, output to a file, per-run timeout), hand-made mutants, each expected to be killed by the named tests:

- bridge: `"cancellationToken" in extra` → `not in`, → `True`, → read from the core again;
- VE/Cerence: drop `"cancellationToken"` from `extraCapabilities`;
- runtime: `LeasedPlayer` default `PLAYED_OUT` → `ENGINE_DONE`;
- eSpeak: the `espeak_Synth` reach `SYNTHESIZED` → `ENGINE_DONE`; RHVoice: `record.barriers[ENGINE_DONE]` → `[SYNTHESIZED]`; SAPI5: `idle` reach → `ENGINE_DONE`; VE: `_retireRecord`'s check `SYNTHESIZED in record.barriers` → `PLAYED_OUT in …`;
- guard: a literal `"idle"` put back into one strategy, and an engine-specific name added to another engine's set.

Survivors are recorded with the reason.

### 7.4 Windows / NVDA

Nothing can be checked on Windows here: no NVDA, no audio device, no engine SDK. The change is spelling-only for barriers and moves a constant claim from the core to the class, so no manual item is required beyond the usual smoke test (speak with each engine; cancel VE/Cerence speech).

## 8. Open questions

- §3.2 classification default (above).
- Whether `tests/test_segment_host.py`'s fake should also rename `"returned"` → `"synthesized"` for readability (default: no, the host test uses opaque labels and the minimal rename keeps the token proof small).

## 9. Implementation notes

- §3.3 missed one test string table: `tests/test_segment_host.py:323` checks the missing-barrier message with the substrings `"returned, idle"` / `"idle, returned"`. The full run caught it in G1 and both strings were added to that commit's `OLD=NEW` list (now `"returned, played_out"` / `"played_out, returned"`). A scan of every string token in `tests/` for barrier words inside longer strings found no other label use (SAPI5's `"... no owned player idle barrier"` drain-support reason is prose, kept).
- Mutation survivors (§7.3): RHVoice's worker read `record.barriers[ENGINE_DONE]` → `[SYNTHESIZED]` survives the behaviour tests, as the same mutant does on `master`: when the done callback never comes the record still fails, the only difference is one extra final `player.idle()`. VE/Cerence `_retireRecord`'s `SYNTHESIZED in record.barriers` → `PLAYED_OUT in …` is equivalent (segment records declare both, ordinary records neither).
- Fix round (option B′, §3.5): the RHVoice survivor above is now killed — `test_missing_done_does_not_drain_after_native_return` asserts the worker's final `idle()` did not run (review M1). The fix round's renames, host check, guards and mutants are recorded in the review's 修正記錄 (`docs/superpowers/finish/2026-10-28-phase52-shared-barriers-review.md`).
