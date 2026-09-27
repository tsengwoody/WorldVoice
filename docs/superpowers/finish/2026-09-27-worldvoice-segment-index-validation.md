# Segment-index completion validation — evidence pending

Recorded 2026-09-27 on a Linux host (`uname -s` returned `Linux`). **Task 8 is incomplete pending Windows/NVDA/device access.** No real engine/profile has been validated or migrated. The production `_VERIFIED_CONTRACTS` table remains empty; every profile selects `LEGACY_DONE` with no index range. No marker policy rows or drain/failure hooks were added.

## Evidence boundaries

- **Source observations:** the repository contains the wrappers and event paths listed below. These establish inspection targets only. They do not prove that an installed driver accepts an `IndexCommand` subclass, preserves indexes, accepts a particular integer range, or finishes physical audio at any callback.
- **Fake tests:** Linux tests use NVDA stubs, fake engines and fake audio. Their results cover policy fallback and software contracts only. They are not hardware evidence and cannot authorize a production opt-in.
- **Hardware evidence:** none collected. There is no Windows NVDA runtime, installed engine/version inventory, device measurement, listening result or real event trace from this run. Driver availability on a future Windows host is unverified, including external drivers.

## Per-profile evidence matrix

`U` means **unverified / not run on Windows hardware** in every hardware cell below. `default`, `wasapi` and `legacy` are intended policy-key labels, not observations of an opened audio device. The version column requires the exact NVDA version; the engine column also requires the actual driver/DLL version when a run becomes possible. Add separate rows for every tested version/audio-mode combination; do not extrapolate to neighboring versions.

| Engine / driver version | NVDA version | Audio mode | Subclass acceptance | Verified index range | Order & adjacent skip | Empty text | Marker vs speak-return | Audio-tail timing | Cancel | Failure signal | Selected mode | Source location | Hardware date / result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OneCore / U | U | `default` (actual U) | U | U; none approved | U | U | U | U | U | U | `LEGACY_DONE` | S1 | No hardware date; U |
| SAPI5 / U | U | `wasapi` (actual U) | U | U; none approved | U | U | U | U | U | U | `LEGACY_DONE` | S2 | No hardware date; U |
| SAPI5 / U | U | `legacy` (actual U) | U | U; none approved | U | U | U | U | U | U | `LEGACY_DONE` | S2 | No hardware date; U |
| VE / U | U | `default` (actual U) | U | U; none approved | U | U | U | U | U | U | `LEGACY_DONE` | S3 | No hardware date; U |
| Cerence / U | U | `default` (actual U) | U | U; none approved | U | U | U | U | U | U | `LEGACY_DONE` | S4 | No hardware date; U |
| RHVoice / U | U | `default` (actual U) | U | U; none approved | U | U | U | U | U | U | `LEGACY_DONE` | S5 | No hardware date; U |
| Espeak / U | U | `default` (actual U) | U | U; none approved | U | U | U | U | U | U | `LEGACY_DONE` | S6 | No hardware date; U |
| Available external: inventory/name/version U | U | U | U | U; none approved | U | U | U | U | U | U | `LEGACY_DONE` | S7; installed driver path U | No hardware date; U |

## Source observations and locations

Paths are relative to the repository root. These were read without modifying NVDA, `ref/`, or embedded lower-level drivers.

- **S1:** `addon/synthDrivers/WorldVoice/driver/OneCore/driver/__init__.py`, `OneCoreSynthDriver`: imports `synthDrivers.oneCore.SynthDriver` and adds language accessors. Inspect the exact installed NVDA `synthDrivers/oneCore.py` and its native bridge before proposing a range or timing contract. Those installed sources and runtime behavior were not verified here.
- **S2:** `addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py`, `Voice`: uses NVDA `synthDrivers.sapi5.SynthDriver`. `addon/synthDrivers/WorldVoice/__init__.py`, `_completion_for`: selects SAPI5 `wasapi`, `legacy`, or `unknown` from the opened core. Inspect the exact installed `synthDrivers/sapi5.py` and engine implementation independently for each audio mode; neither mode has hardware evidence here.
- **S3:** `addon/synthDrivers/WorldVoice/driver/VE/__init__.py`, `CancellableSynthDriver.speak`, `cancel`, `_onIndexReached`: contains cancellation guards. `addon/synthDrivers/WorldVoice/driver/VE/driver/__init__.py`, `SynthDriver.speak` and `_onIndexReached`: contains index handling and notifications. `driver/ve2/veTypes.py` defines native mark fields. None of these establishes accepted DLL bounds or physical drain timing.
- **S4:** `addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py`, `CancellableSynthDriver.speak`, `cancel`, `_onIndexReached`: contains cancellation guards. `addon/synthDrivers/WorldVoice/driver/Cerence/driver/__init__.py`, `SynthDriver.speak` and `_onIndexReached`: contains index handling and notifications. `driver/ttsapi/veTypes.py` defines native mark fields. These require independent installed-version verification, even where source resembles VE.
- **S5:** `addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py`, `Voice`: selects the bundled driver. `addon/synthDrivers/WorldVoice/driver/RHVoice/driver/__init__.py`, `RHVoice_callback_types.process_mark`, `SynthDriver.speak` and `cancel`: provides native callback and submission inspection targets. A declared C callback type alone does not verify mark parsing, ordering or playback completion.
- **S6:** `addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py`, `Voice`: imports NVDA `synthDrivers.espeak.SynthDriver`. The exact installed NVDA driver, native library, player and version remain to be inspected on Windows.
- **S7:** `addon/synthDrivers/WorldVoice/engine/__init__.py` supplies `WorldVoice-workspace` as the external root; `addon/synthDrivers/WorldVoice/engine/discovery.py`, `_iter_external_candidates` and `discover_engine_specs`, locates external manifests. Inventory the actual Windows workspace and add one row per available external engine/profile. The fake `external-test-engine` policy key is not an installed external engine.

The shared policy is `addon/synthDrivers/WorldVoice/compat/completionPolicies.py`, `get_completion_contract`. `addon/synthDrivers/WorldVoice/runtime/models.py`, `CompletionContract`, defaults to `LEGACY_DONE` and no range. The empty exact-key table is source evidence for conservative selection, not a claim about hardware capability.

## Windows probe plan — all not run

Keep each item unchecked until its associated real evidence is retained. Run every applicable scenario for every matrix row, separately for SAPI5 WASAPI and legacy. Missing engines remain unverified.

- [ ] Record Windows build, exact NVDA build/version, WorldVoice commit, engine/DLL version, voice, language, rate settings, output device/backend and actual opened audio mode. Inventory external drivers and capture their installed source/manifest paths. Associate each artifact with the exact `(engine, nvda_version, audio_mode)` key and run date.
- [ ] Inspect the exact installed driver/native boundary and documented parser/storage limits before selecting test integers. Then test a safe low positive value, a safely supported value beyond NVDA's usual index range, and the candidate upper bound. Record the actual numbers, round-trip callback values and supporting source locations. No Python `int` assumption, guessed DLL bound, unreviewed oversized integer or approved range exists in this report.
- [ ] Submit both ordinary `IndexCommand` and the WorldVoice internal subclass, including adjacent indexes around short text, long text and the end marker. Trace whether each is accepted, skipped, reordered, duplicated, truncated or transformed. Test text with no caller indexes as well. Require ordered observations and usable terminal-marker behavior for the claimed contract.
- [ ] Exercise empty text, an empty sequence, whitespace-only text, and command-only sequences (including adjacent indexes, setting changes and breaks). Record return, marker, done and audio events, including absent callbacks; do not treat a timeout as completion.
- [ ] For short and long speech, record submission start, `speak` return, every index callback, done/drain callback, actual audio tail and next-segment audio start on a common monotonic timeline. Test synchronous and asynchronous delivery. Listen and retain an audio capture with an alignment method so premature switching and overlap can be assessed independently of callback timestamps.
- [ ] Cancel repeatedly during synthesis, queued audio and the final tail, then replay immediately. Exercise A→B→A and stale callbacks from cancelled work. Record cancel request/return and late notifications, verify cancelled audio stops, and verify a stale event cannot finish or advance new speech.
- [ ] Exercise same-engine and cross-engine switching, pauses/breaks, say-all, configuration/voice changes and pause/resume (including near the terminal marker). Verify actual playback has no premature switch, overlap, skipped segment or hang; retain the event trace and listening/capture result for each scenario.
- [ ] With a controlled recoverable failure, record submission exceptions and any asynchronous engine failure notification, its source identity, and whether queued work can recover. Missing or unidentifiable failure signals stay explicitly unverified; never re-label an anonymous done event as a drain/failure signal.

For each trace retain run/scenario IDs, exact profile, source ID, generation, segment ID, command kind/index, timestamp, thread, event type, cancellation state, exception/failure details and audio artifact references where observable. Record how events are correlated to submitted work. An unavailable field or signal must be recorded as unavailable rather than invented. Capture external instrumentation without changing NVDA, `ref/`, or embedded lower-level drivers.

## Opt-in gate and unfinished migration

`END_INDEX` requires real evidence that terminal-marker completion satisfies the audio-tail contract for the exact profile. If the marker arrives before the tail, `END_INDEX_AND_DRAIN` additionally needs a reliable, source-bound drain signal; without it retain `LEGACY_DONE`. If a future WorldVoice-only hook is required, capture the original `PlaybackContext` when work is submitted and emit `PlaybackEvent(SEGMENT_DRAINED, context.source_id, segment_id=context.segment_id)` through the adapter's keyword-only `event_sink` supplied by `voiceManager`. A global current context or unlabelled done notification is insufficient. No such hook was introduced in this run.

- [ ] Execute the Windows matrix and attach dated real event/audio evidence.
- [ ] For each proven exact key, add `test_verified_profile_selects_recorded_contract` asserting the report's exact mode and range, while neighboring unknown versions stay legacy. Add synchronous, delayed, duplicate and post-cancel stale hook fixtures if a hook is needed.
- [ ] Re-run affected policy/adapter/wrapper tests and the same Windows scenarios after implementation. Mark a row migrated only after fake contracts pass **and** real hardware satisfies the selected mode.
- [ ] Commit each verified profile separately. Complete Task 8 only after all built-in engine requirements pass; record unavailable external profiles separately.

## Linux fake-test results

Executed 2026-09-27:

```text
python3 -m pytest tests/test_runtime_completion_policies.py tests/test_runtime_adapter_contract.py tests/test_runtime_legacy_adapter.py tests/test_worldvoice_cancel_wrappers.py tests/test_f4_engine_adapters.py -q -p no:cacheprovider
209 passed in 2.73s
```

The fallback test now covers all matrix engine categories, both SAPI5 modes, unknown audio modes, unknown engine names and the illustrative version strings `unknown`, `2026.1`, `2026.1.1`, `2026.2`. These version strings are test inputs, not an installed-version inventory. Every tested profile explicitly asserts `LEGACY_DONE` and no index range. The other tests exercise existing adapter and wrapper software contracts using fakes. **No result in this section fills a hardware matrix cell or completes Task 8.**
