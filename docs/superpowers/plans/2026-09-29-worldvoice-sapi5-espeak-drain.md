# SAPI5 and eSpeak correlated drain implementation plan

**Goal:** Extend the existing correlated DRAIN implementation to the outer SAPI5 and eSpeak WorldVoice drivers, while keeping real profile activation evidence-gated.

**Spec:** [2026-09-29-worldvoice-sapi5-espeak-drain-design.md](../specs/2026-09-29-worldvoice-sapi5-espeak-drain-design.md), authorized by the user's request to implement both engines like the existing four wrappers.

**Workspace:** Continue on the user-requested `test/force-segment-end-index-all-engines` branch. The working tree was clean at start. Tasks 1 and 2 touch separate outer-driver modules and separate tests; policy, integration and delivery updates are serialized after both reviews.

## Global constraints

- Preserve original DRAIN semantics: same exact segment context, ordered ordinary indexes, final real player idle before success, failure propagated, cancellation/stale work silent.
- Do not modify NVDA source, inner SAPI5/eSpeak drivers, DLLs or native libraries.
- SAPI5 can use DRAIN only with its WorldVoice-owned WASAPI player path. Its legacy audio path falls back before speech.
- eSpeak must not emit drain from inside its native synthesis callback; queue retirement and event delivery must not create a callback/native-call termination cycle.
- A wrapper does not establish compatibility by name or fake tests. Keep every real SAPI5/eSpeak profile on explicit `LEGACY_DONE` until actual profile and physical playback evidence is recorded.
- No new END_INDEX marker or fixed delay. Preserve the existing END_INDEX contract for engines outside this extension.

## Task 1 — SAPI5 outer drain wrapper

Files: add outer `SynthDriver` subclass in `addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py`; update its `Voice` binding; add real-wrapper fake-boundary tests.

- Use TDD. Prove end-of-stream alone does not complete; only the wrapped `WavePlayer.idle()` returning after final feed may publish drain.
- Preserve ordinary SAPI bookmark notifications, existing configuration and voice reload behavior.
- Suppress drain on cancellation, early idle, missing end marker, feed/idle failure or stale context. Keep completion delivery safe against worker-thread termination reentrancy.
- Add an explicit support result for the WASAPI route, but return unsupported for all profiles until evidence exists; legacy SAPI audio is unsupported.
- Run focused SAPI tests and report exact commands/results. Commit the implementation.

## Task 2 — eSpeak outer drain wrapper

Files: add outer `SynthDriver` subclass in `addon/synthDrivers/WorldVoice/driver/Espeak/__init__.py`; update its `Voice` binding; add actual-wrapper fake-boundary tests.

- Use TDD. Prove callback idle/end occurs before native synthesis return, and DRAIN is delivered only after a FIFO barrier proves `_speak` has returned.
- Capture the original context for index/end callbacks; observable feed/idle/native errors fail the segment. Cancellation invalidates the old work and its barrier; old callbacks cannot satisfy a successor.
- Deliver terminal notifications outside the native callback/bgThread stack. Preserve voice, language, variant, prosody and token behavior.
- Keep support false for all real profiles until evidence exists. Do not modify NVDA's `_espeak.py`.
- Run focused eSpeak tests and report exact commands/results. Commit the implementation.

Tasks 1 and 2 may run in parallel because their product and test files are independent. Any shared runtime or policy edit must be left to Task 3.

## Task 3 — policy, integration and delivery

Files: `compat/completionPolicies.py`, `WorldVoice.__init__.py`, policy and integration tests, README/finish handoff.

- Add SAPI5/eSpeak to DRAIN wrapper precedence so explicit unsupported results fall back to `LEGACY_DONE` before playback instead of the test-only `END_INDEX` experiment.
- Verify actual Voice-to-wrapper selection, context-aware segment entry, event binding before publication, index restoration, request success/failure and cancellation across both new engines. Preserve RHVoice and unknown-engine policies.
- Run the full add-on test suite and `git diff --check`. Do not claim Windows playback acceptance or add real profiles to the verified table.
- Rebuild and audit the `.nvda-addon` if the package is part of the delivery; record package hash/size and unsupported-profile limits in `docs/superpowers/finish_task.md`, with the new commit list.

## Review process

Each engine task receives an independent `gpt-6-astra high` review after implementation. Any Critical/Important or spec finding returns to that implementer; the same reviewer performs a scoped re-review after correction. Once Tasks 1–3 are complete, request a whole-extension review against the addendum and inspect all findings before delivery.
