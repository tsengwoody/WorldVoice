# SAPI5 and eSpeak correlated drain extension

## Purpose and scope

The 2026-09-28 correlated-drain design implemented outer wrappers for OneCore, Neural, VE and Cerence. The user has now explicitly extended that scope to SAPI5 and eSpeak, asking for the same per-segment drain contract and review process.

This extension preserves the shared runtime, index ledger, event bridge, scheduler and `DRAIN` semantics from the original design. It adds custom outer drivers at `driver/SAPI5/__init__.py` and `driver/Espeak/__init__.py`; NVDA source, inner driver implementations, DLLs and native libraries remain unmodified. Runtime selection remains evidence-gated: having a wrapper does not certify a Windows/NVDA profile. SAPI5 legacy audio and all unverified SAPI5/eSpeak profiles must select `LEGACY_DONE` before playback.

## Shared contract

- A segment captures its exact `PlaybackContext`, cancellation token and event sink when admitted. It publishes `SEGMENT_DRAINED` only once after synthesis completion, final audio processing and the real player idle barrier. Observable synth/audio errors publish `SEGMENT_FAILED`; cancellation and stale callbacks never publish success.
- Ordinary indexes continue through the existing NVDA source notifications and ledger mapping. The wrappers add no synthetic terminal marker.
- `get_segment_drain_support` returns false until a supported loaded profile has documented SDK/NVDA callback retirement and real playback evidence. Tests of a fake wrapper are not evidence to enable a real profile.
- The wrappers own their event identity and per-segment state. Completion notifications that can re-enter cancellation or termination must be delivered outside native/player callback stacks where those stacks participate in shutdown waits.

## SAPI5 wrapper

`SAPI5.SynthDriver` gains an outer custom subclass and its `Voice` selects that class. The DRAIN path is eligible only for the WASAPI `WavePlayer` route. The base driver's non-WASAPI output uses SAPI's legacy audio stream and has no WorldVoice-owned player idle barrier, so it remains `LEGACY_DONE`.

For WASAPI, SAPI's `EndStream` only wakes its worker; that worker flushes Sonic and feeds the final buffer, calls `_onEndStream`, and then calls `WavePlayer.idle`. The wrapper must associate `_onEndStream` with the admitted segment, suppress no existing index behavior, and report drain only after the wrapped real `idle` call returns. A player idle reached without the segment's end notification is a failure unless the work was cancelled. Delivery must not synchronously terminate/join the SAPI worker from that worker's own stack.

## eSpeak wrapper

`Espeak.SynthDriver` gains an outer custom subclass and its `Voice` selects that class. NVDA's eSpeak callback handles a null waveform by calling `player.idle()` and then `_onIndexReached(None)`, but this happens inside the eSpeak native synthesis callback before `espeak_Synth` returns. The wrapper captures the null-waveform terminal observation, then places a FIFO barrier behind the queued native `_speak` operation. It emits drain from a separate delivery thread only after the native call and callback have returned, and only if the player idle observation succeeded and the work remains valid.

Audio feed/idle exceptions observable at the player boundary are latched as failure; a native operation that retires without either an end observation or a player error must fail rather than leave the scheduler waiting. A cancelled operation's queued barrier retires silently. FIFO ordering must prevent its callbacks from being attributed to a successor.

## Verification

- Use native-boundary fakes while loading the actual SAPI5/eSpeak outer wrapper code.
- SAPI5 tests cover WASAPI eligibility, `EndStream` before idle, actual idle before drain, tail/index order, empty audio, observable worker/player failures, cancellation that makes idle return early, stale context and notification reentrancy.
- eSpeak tests cover the native callback's idle/end ordering, deferred delivery until `_speak` returns, feed/idle/native failures, cancellation with an active or queued call, stale callbacks and FIFO successor handoff.
- Integration tests cover voice selection, policy precedence over the test-only `END_INDEX` override, binding setup before publication, index mapping, request completion and legacy fallback.
- Windows audio acceptance and SDK callback-retirement evidence remain separate requirements; no synthetic test enables `_VERIFIED_CONTRACTS`.
