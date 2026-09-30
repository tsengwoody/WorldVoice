# RHVoice Correlated Drain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an RHVoice outer wrapper that can report context-correlated segment drain after RHVoice's true completion barriers, and route RHVoice through evidence-gated DRAIN policy.

**Architecture:** Preserve the inner RHVoice worker and synth behavior. The outer subclass associates each native queued task, callback, buffered index, and player operation with captured `PlaybackWork`; only task retirement after native done, successful native return, and final real player idle may dispatch correlated drain asynchronously. Policy checks the actual loaded wrapper and remains unsupported for all real profiles.

**Tech Stack:** Python, NVDA synth driver interfaces, pytest fake-native/audio harness.

**Spec:** `docs/superpowers/specs/2026-09-30-worldvoice-rhvoice-drain-design.md`

## Global Constraints

- Do not modify NVDA sources, RHVoice's inner `driver/` implementation, or native DLLs.
- Preserve ordinary RHVoice integer index notifications and all existing SSML, profile, language, rate, pitch, volume, and rate-boost behavior.
- Publish exactly one correlated `SEGMENT_DRAINED` only after native done, successful synchronous native return, successful final `AudioPlayer.idle()`, and task/callback/feed retirement.
- Cancellation, stale work, missing native done, and any native/feed/idle/stop error suppress successful drain; control failure fails closed until driver recreation.
- Keep `get_segment_drain_support` false for every real RHVoice profile; unsupported wrappers select `LEGACY_DONE` before playback.
- Do not change unknown-engine `LEGACY_DONE` behavior or claim physical playback acceptance.

## Review Focus

- Native done arrives before `RHVoice_speak` returns: test drain waits for return and final idle.
- Index and PCM callbacks can outlive their initiating callback: test they retain the originating work and never satisfy a successor.
- Inner callback and TTSThread layers swallow errors: test feed/native/idle faults are latched and fail closed.
- Cancel can race a feed and queued successor: test old work cannot enqueue audio after successor admission.
- Terminal notification may terminate the driver: test it runs outside native callback and worker stacks.

---

### Task 1: RHVoice context-aware outer drain wrapper

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py`
- Create: focused actual-wrapper RHVoice drain tests and reusable local fake harness under `tests/`
- Do not modify: `addon/synthDrivers/WorldVoice/driver/RHVoice/driver/`

**Interfaces:**
- Consumes: `PlaybackContext`, `SegmentEventSink`, `SpeechCommands`, `DrainSupport`, `PlaybackWork`, and `CancellationView` from existing runtime modules.
- Produces: `Voice.synth_driver_class = SynthDriver`; outer `SynthDriver.speak_segment(commands, token, *, context, on_event)`; `get_segment_drain_support(*, nvda_version=None, audio_mode=None)` returning unsupported for every profile.

- [ ] Write failing tests against the actual installed outer wrapper for done-before-native-return ordering, final-idle gating, index preservation, cancellation/stale isolation, async terminal delivery, and swallowed boundary failures.
- [ ] Run the focused RHVoice test module and confirm the new contract fails before implementation.
- [ ] Implement the outer wrapper while preserving inner XML conversion/settings/queue semantics and avoiding changes to inner driver or DLLs.
- [ ] Run the focused RHVoice tests and the relevant existing runtime/voice lifecycle tests; record exact results.
- [ ] Commit the wrapper and tests.

### Task 2: RHVoice policy integration and delivery record

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/compat/completionPolicies.py`
- Modify: `addon/synthDrivers/WorldVoice/__init__.py`
- Modify: `tests/test_runtime_completion_policies.py` and RHVoice integration tests
- Modify: `readme.md`, `docs/superpowers/finish_task.md`

**Interfaces:**
- Consumes: Task 1 actual outer wrapper and explicit false `DrainSupport` result.
- Produces: RHVoice included in DRAIN-capability precedence; RHVoice removed from test-only forced END_INDEX; real RHVoice opens as `LEGACY_DONE` until profile evidence exists.

- [ ] Write failing policy and actual Voice/core selection tests for RHVoice fallback, plus a regression asserting unknown engines remain `LEGACY_DONE`.
- [ ] Run the focused policy tests and confirm they fail for the current forced-END_INDEX behavior.
- [ ] Update policy precedence and the runtime engine list; keep all RHVoice profile checks false and preserve version/audio profile logging.
- [ ] Run focused RHVoice/policy tests and the full add-on suite; run `git diff --check`.
- [ ] Build and audit the add-on package; record limits, artifact hash/size, and the commit list in `README.md` and `docs/superpowers/finish_task.md`.
- [ ] Commit the policy integration and delivery notes.

## Review Process

Each task receives an independent `gpt-6-astra high` review after implementation. Critical/Important findings or spec gaps go back to the original implementer for correction and scoped re-review. After both tasks, run one whole-change review with `gpt-6-astra high` before delivery.
