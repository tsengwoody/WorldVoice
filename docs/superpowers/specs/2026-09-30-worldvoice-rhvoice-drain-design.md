# WorldVoice RHVoice correlated drain design

Date: 2026-09-30. Implementation target: `test/force-segment-end-index-all-engines`.

## Goal and boundary

Add the same context-correlated segment-drain interface used by the SAPI5 and eSpeak wrappers to RHVoice. The outer WorldVoice wrapper may coordinate the existing inner driver, but must not modify the vendored `driver/` implementation, native DLLs, or NVDA source. Existing speech conversion, voice profiles, prosody, index commands, and the inner RHVoice worker remain authoritative.

This is an implementation of a drain contract, not physical-playback certification. Every RHVoice profile reports `DrainSupport(False, ...)` until a named NVDA/RHVoice/audio profile has physical playback and ordered-index evidence.

## RHVoice completion contract

RHVoice invokes its native `done` callback before synchronous `RHVoice_speak` returns. The callback flushes the buffered tail and calls `AudioPlayer.idle()`, then emits anonymous `synthDoneSpeaking`; after native return, `SpeakText` calls `AudioPlayer.idle()` once more. Neither the native callback nor the worker may publish correlated completion.

For a valid `PlaybackWork`, the wrapper emits exactly one `SEGMENT_DRAINED` with the context and event sink captured by `speak_segment` only after all of the following hold:

1. Native `done` was observed for that exact work.
2. `RHVoice_speak` returned successfully.
3. The worker's final player `idle()` returned successfully.
4. The inner callable has retired, including message cleanup and callback/feed consumers.
5. The work is still valid and no feed, idle, stop, callback, or native error was recorded.

Ordinary index callbacks keep their integer values and are correlated with the work active when the native callback is admitted. Anonymous `synthDoneSpeaking` remains available to legacy users but cannot satisfy or publish DRAIN. Terminal delivery must run outside the native callback and RHVoice worker stacks, so consumers may safely terminate the driver.

Cancellation invalidates the active work, drains queued work according to the inner driver's existing behavior, stops playback, waits for the current callable/callback/feed activity to retire before admitting a successor, then stops again if an already-admitted feed could have queued old audio. A cancelled, stale, incomplete, or failed work never reports a successful drain. A stop/control failure is latched and causes later work to fail closed until driver recreation.

## Compatibility and policy

`Voice.synth_driver_class` must point to the installed outer custom `SynthDriver`. It exposes `speak_segment(commands, token, *, context, on_event)` and `get_segment_drain_support(*, nvda_version, audio_mode)`. The latter explicitly returns unsupported for all real profiles. Runtime policy must route RHVoice through the DRAIN wrapper capability precedence and fall back to `LEGACY_DONE` before playback when unsupported; RHVoice must leave the test-only forced `END_INDEX` list. Unknown engines remain `LEGACY_DONE`.

The implementation must preserve RHVoice's existing `speak`, `cancel`, and `terminate` behavior and must not allow the WorldVoice context API to introduce a separate queue competing with RHVoice's single native worker.

## Validation

Tests use the actual installed outer `Voice`/`SynthDriver` with fake native and WavePlayer boundaries. They must prove callback-before-return ordering, no drain before final idle and task retirement, index preservation, stale/cancelled work isolation, exactly-once delivery outside callback/worker stacks, and fail-closed behavior for native/feed/idle/stop errors. Policy tests prove RHVoice no longer uses forced END_INDEX and real wrapper profiles select `LEGACY_DONE` while support is false.

No Windows playback acceptance or supported profile is claimed by this change.
