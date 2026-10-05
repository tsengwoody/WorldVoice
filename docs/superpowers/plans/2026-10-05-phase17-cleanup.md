# Phase 17 Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the 37 deferred items selected in `refactor-cleanup.md` §3.

**Spec:** `docs/superpowers/specs/2026-10-05-phase17-cleanup-design.md`

The per-item rationale, file:line evidence and fix sketch are in `refactor-cleanup.md` §2–§3. Each task below reads those rows first.

## Global Constraints

- Never edit `driver/<Engine>/driver/` or `driver/sonic`. VE and Cerence change identically.
- `git add` explicit paths only. Never stage `docs/superpowers/finish_task.md`, `refactor-cleanup.md` or `storage/`.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Full suite `python3 -m pytest tests -q` (baseline 1674), lint gate, `ruff format --check addon`.

## Review Focus

1. **#26 with an ordinary open failure followed by a segment, and with a segment open failure.** The first must not latch; the second must still latch. Cancellation during the failed sentence must not hang the worker.
2. **#39 rejecting real strategies.** All six engines' strategies must still construct. Ordinary records with explicit empty barriers (VE/Cerence) must keep working.
3. **#44 a feed outside any admitted callback**, such as a bookmark-only `feed(None, 0, onDone)`, racing a retire/begin.
4. **#57 a `terminate()` that registers during run.** The driver registers nothing during teardown, so this is not expected; check it.
5. **#64 the detector's language provider after the change.** It still reads per call.

## Tasks

### Task A — #26, #49
- [ ] Failing tests:
  - OneCore: an ordinary open failure, then a second ordinary sentence. Assert no control error, the second sentence reaches native, and DONE is published for both. A segment open failure still sets `control_error`.
  - VE/Cerence `_strip_bytes_repr`: `b'bengali'` → `bengali`, `b'Arabic'` → `Arabic`, `plain` unchanged.
- [ ] Implement. Run the full suite and lint.
- [ ] Commit `fix: let a failed OneCore player open fail only its sentence and keep voice-name letters`.

### Task B — #20, #22, #28, #39, #44, #18, #65, #57
- [ ] For each item, write the test that fails first (refactor-cleanup.md §3 Task B), then the one- or two-line fix. #18 is a deletion covered by the existing suite.
- [ ] Run the full suite; run the lifecycle and SAPI5 files 5×.
- [ ] Commit `fix: close the runtime's latent waits, leaks and missing guards`.

### Task C — 14 test gaps
- [ ] Apply each row of §3 Task C. Each tightened test must fail on a deliberately broken copy of the behavior it pins (mutation check), then pass.
- [ ] Commit `test: close the deferred test gaps`.

### Task D — 7 comments and the reason table
- [ ] #50: first add combined entries to the reason table in `tests/test_hygiene_guards.py`, checked before the single ones; the guard fails on the 8 partial reasons. Then update those comments.
- [ ] Apply the other 6 comment rows.
- [ ] Commit `docs: correct misleading comments and complete blind-except reasons`.

### Task E — 6 small tidy-ups
- [ ] Apply each row of §3 Task E, with a test where behavior could move: #55 and #70 behavior tests; #64 the existing per-call detector test.
- [ ] Commit `refactor: small tidy-ups from the deferred list`.
