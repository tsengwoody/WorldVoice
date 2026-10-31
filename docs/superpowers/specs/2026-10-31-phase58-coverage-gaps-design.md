# Phase 58: fill the coverage gaps

Date: 2026-10-31.
Base: `master` `06ea3e2` (phase 57 test cleanup merged). Branch: `phase58-coverage-gaps`. Flow: normal
(DEVELOPMENT_WORKFLOW.md §3).
Status: the user asked (2026-10-31) to "fill the coverage gaps" after phase 57. Spec written by the
orchestrated spec agent; no user decision is open (see §10).

All line numbers are at `06ea3e2`. `addon/` did not change in phase 57, so the audit's numbers
(`storage/test-clean2.md`, taken at `3c178f4`) still match; every one quoted here was re-read at
`06ea3e2`. Paths are shortened: `sd/` = `addon/synthDrivers/WorldVoice/`,
`gp/` = `addon/globalPlugins/WorldVoice/`, `ref/nvda/` = the main checkout's NVDA source.

## 1. Problem, goals, non-goals

Problem: 179 statements and 168 branch arcs (156 lines with a partial branch) of the add-on are never
run by the suite. Some of them are error paths whose failure would leave speech stuck (a delivery
thread or engine worker that dies, a queue that never retires a record) or would crash a settings
dialog. They are untested today, so a refactor could break them unnoticed.

Goals:

1. Classify every missed line and missed branch arc (§3, §5, §6).
2. Add a behavioural test for every item worth one (class (a)): each test asserts an observable
   outcome and kills a named mutant.
3. Delete the one provably dead, behaviour-neutral line (`sd/engineRegistry/discovery.py:77-78`, §7).

Non-goals:

- No behaviour change in `addon/` (only the deletion in §7). A test that finds a product bug stops
  that item: the implementer records it as a finding and does not fix it in this phase (§10, Q6).
- No new test harness module and no test-only hook in add-on code; tests use the existing harnesses.
- No mutmut run (no core decision module changes); each new test's mutant is checked by hand (§8).
- Inner drivers (`driver/<Engine>/driver/`), `driver/sonic/` and `unicodeScripts/script_data.py` are
  excluded from coverage (`pyproject.toml` `[tool.coverage.run] omit`) and are not touched.

What an NVDA user hears or sees: nothing changes. No strings, settings, panels or translations change.

## 2. Baseline

Command (one pytest process; a watchdog killed only that PID when MemAvailable < 3 GB):

```bash
python3 -m pytest -q tests -p no:cacheprovider --cov=addon --cov-branch --cov-report=term-missing
```

Two runs at `06ea3e2` in the phase worktree gave identical reports: **3243 passed, 0 skipped**;
TOTAL **8368 stmts / 179 miss, 2374 branches / 156 partial (168 missing arcs), 96.77 %**
(`coverage report --precision=2`). The figure given to this phase (180 miss / 157 partial, 96.75 %)
differs by one line and one partial branch; it was not reproduced in two runs, so one timing-dependent
line probably exists somewhere. The verification (§9) therefore compares module by module and treats a
one-line difference in a module this phase does not touch as noise only after two reruns agree.

Missed lines and arcs per module, and the split this spec makes (lines/arcs):

| Module | missed | (a) test | (b) leave | before % | expected after % |
| --- | --- | --- | --- | --- | --- |
| `gp/panels/base.py` | 0/1 | 0/0 | 0/1 | 98.61 | 98.61 |
| `gp/panels/detection.py` | 2/0 | 2/0 | 0/0 | 96.55 | 100.00 |
| `gp/panels/role.py` | 1/1 | 0/0 | 1/1 | 99.19 | 99.19 |
| `gp/rolePresenter.py` | 3/4 | 3/3 | 0/1 | 95.21 | 99.32 |
| `sd/__init__.py` | 9/2 | 9/2 | 0/0 | 97.02 | 100.00 |
| `sd/bridge/engineAdapter.py` | 1/4 | 1/4 | 0/0 | 97.31 | 100.00 |
| `sd/bridge/indexLedger.py` | 2/2 | 2/2 | 0/0 | 98.55 | 100.00 |
| `sd/bridge/nvdaEvents.py` | 0/1 | 0/0 | 0/1 | 99.57 | 99.57 |
| `sd/driver/Cerence/__init__.py` | 26/27 | 21/13 | 5/14 | 93.42 | 97.64 |
| `sd/driver/Espeak/__init__.py` | 11/8 | 5/2 | 6/6 | 89.08 | 93.10 |
| `sd/driver/OneCore/__init__.py` | 14/17 | 7/11 | 7/6 | 94.62 | 97.74 |
| `sd/driver/RHVoice/__init__.py` | 19/8 | 3/1 | 16/7 | 93.08 | 94.10 |
| `sd/driver/SAPI5/__init__.py` | 38/43 | 25/22 | 13/21 | 87.80 | 94.88 |
| `sd/driver/VE/__init__.py` | 24/27 | 19/13 | 5/14 | 93.65 | 97.63 |
| `sd/engineRegistry/discovery.py` | 1/1 | deleted | 0/0 | 98.95 | 100.00 |
| `sd/pipeline/context.py` | 2/0 | 2/0 | 0/0 | 91.30 | 100.00 |
| `sd/runtime/_segmentLifecycle.py` | 5/4 | 4/2 | 1/2 | 97.91 | 99.30 |
| `sd/runtime/requestBuilder.py` | 2/2 | 2/2 | 0/0 | 94.03 | 100.00 |
| `sd/runtime/scheduler.py` | 5/9 | 0/4 | 5/5 | 97.69 | 98.35 |
| `sd/runtime/segmentHost.py` | 8/3 | 8/1 | 0/2 | 98.08 | 99.65 |
| `sd/ui/voicePanel.py` | 0/1 | 0/0 | 0/1 | 99.48 | 99.48 |
| `sd/unicodeScripts/lookup.py` | 1/1 | 0/0 | 1/1 | 85.71 | 85.71 |
| `sd/voices/manager.py` | 5/2 | 5/2 | 0/0 | 97.54 | 100.00 |

Every other measured module is at 100 %.

## 3. Classification rules

- **(a) behavioural test.** Reachable through a harness the suite already has, and a change to the
  line or branch changes something a caller, NVDA or the user can observe: an event, a returned value
  or raised exception, a call into the engine or player fake, state read through a public property
  (`SegmentHost.control_error`/`faulted`, `request.state`, a voice parameter), or a log line where the
  log is the contract (the code comments say so). Totals: **118 lines, 84 arcs** in 81 items.
- **(b) leave untested.** Totals: **60 lines, 83 arcs** in 75 items. Sub-kinds:
  - **b-gc**: a `weakref` to the driver is dead (`driver = self._driver(); if driver is None`). Reached
    only when the driver was collected while a native thread still calls back; one-line `return`
    guards.
  - **b-race**: reachable only through a thread interleaving inside one function (a re-check after a
    lock was released and re-taken). A deterministic test would need a hook inside a private lock or
    condition, which pins the implementation more than it guards behaviour.
  - **b-equiv**: reachable, but no mutant of the line or branch changes observable behaviour (another
    line already produces the same outcome). A test could not fail when it is broken.
  - **b-inv**: unreachable by an invariant of the add-on, the vendored inner driver or NVDA, cited.
    Kept as a defence against a future change of that invariant; deletion is not proposed because the
    invariant lives in another module or in NVDA (§7 explains the deletion bar).
- **(c) platform-only.** None. Every Windows/NVDA/native behaviour on the list sits behind a stub the
  Linux harness already controls (COM sink calls, ctypes messages, NVDA config sections, the WASAPI
  setting). The two NVDA-version paths (§5 T6, VE/Cerence `413-414`) are reachable with a config stub.
- **del**: provably dead and deleting it is behaviour-neutral: one line (§7).

The full item-by-item list is §5 (class (a), by task) and §6 (class (b)). Every missed line and arc of
§2 appears in exactly one of them; the spec author checked this mechanically against the coverage
JSON of the baseline run.

## 4. Priority and target

Tasks are ordered by user impact:

1. **Speech could get stuck or a worker could die** (P1): segment host/lifecycle error paths (T1),
   scheduler error paths (T2), and the engine error paths whose failure would kill a worker or leave a
   record unretired: VE/Cerence overflow guard and pause/terminate cleanup (T6), SAPI5 purge/drain
   failures and dead worker (T7), OneCore no-player and truncated-audio paths (T8), RHVoice final idle
   and cancel stop failure (T9), eSpeak failed ordinary utterance (T10).
2. **Wrong or stale output** (P2): indexes after cancel, bookmarks on legacy SAPI5 audio, a queued
   parameter read, Sonic mid-call feed (T6-T8).
3. **Settings/UI robustness and small contracts** (P3): T3, T4, T5.

Target: every (a) item covered by a test that kills its named mutant; the deletion in §7 done; no (b)
item tested. Expected TOTAL afterwards (if every (a) item is covered and nothing else moves):
**8366 stmts / 60 miss, 2372 branches / 82 partial (83 missing arcs), 98.67 %**, per-module figures
in §2. If an (a) scenario proves unreachable during implementation, the implementer reclassifies it
as (b) with a `Ruling:` line (§3.2 of the workflow) and the figure drops accordingly; it does not
weaken the assertion to reach the line.

## 5. Class (a): tests to add, by task

Notation per test: **scenario** → **assert** (observable) → **mutant** (the change at the cited line
that must turn the test red). All new tests follow §8.

### T1 Segment host and lifecycle (P1) — `tests/test_segment_host.py`, `tests/test_segment_lifecycle.py`

1. `test_ordinary_retire_survives_a_failing_stop` (parametrized `cancelled`, `failed`) — covers
   `sd/runtime/segmentHost.py:546-547, 562-564`. `FakeStrategy.stop_player` (test_segment_host.py:47)
   raises `OSError("stop failed")`. `cancelled`: enqueue ordinary, begin, `host.cancel()`, retire.
   `failed`: enqueue, begin, retire without barriers. Assert retire returns (no exception);
   `cancelled` → `OrdinaryOutcome(cancelled=True, error=None)` and one ERROR record
   "Error stopping cancelled Fake playback" with `exc_info`; `failed` → `outcome.error` is the
   missing-barrier `RuntimeError`, `record.error` is the stop `OSError` (record_error keeps the first
   error, segmentHost.py:457-460), log "Error stopping failed Fake playback". Mutants: drop the
   `try/except` at 544-547 or at 560-563 (retire raises from the engine worker); drop
   `self.record_error(record, stop_error)` at 564 (`record.error is None`).
2. `test_a_raising_lifecycle_run_fails_the_segment` (parametrized `plain`, `chained`) — covers
   `segmentHost.py:637-638`. Monkeypatch the host's lifecycle `run` to raise `RuntimeError("run
   failed")` (`plain`) or `RuntimeError("outer")` raised `from OSError("inner")` (`chained`). Start a
   segment; `eventually` its sink receives exactly one `SEGMENT_FAILED` whose error is the plain error /
   the `__cause__` (`OSError`), and a following segment is accepted and completes. Mutants: drop the
   `except` at 636-642 (no terminal event: the scheduler would wait forever; the test fails on its
   `eventually`); swap `error.__cause__ or error` (wrong error in `chained`).
3. `test_reset_after_terminate_keeps_the_host_terminated` — covers `segmentHost.py:323`. Latch a
   control error (`host.latch_control_error`), `terminate()`, then `reset()`. Assert
   `host.control_error` is still that error, `host.faulted` is true and a new segment is rejected with
   "driver has terminated". Mutant: delete the guard at 322-323 (reset clears the error).
4. `test_a_raising_retirement_callback_does_not_stop_delivery` — covers
   `sd/runtime/_segmentLifecycle.py:451-452`. Accept operation 18 with `on_retired` raising
   `RuntimeError`, cancel it so only its retirement is queued (as in
   `test_retirement_callback_runs_when_cancel_suppresses_delivery`, test_segment_lifecycle.py:681);
   then accept and run operation 19 with a recording sink. Assert 19's terminal event is delivered and
   the log has "segment retirement callback failed for segment 18". Mutant: drop the `try/except` at
   448-455 (the delivery thread dies with `_delivery_active` still true, 19 is never delivered).
5. `test_an_operation_of_another_lifecycle_is_refused` — covers `_segmentLifecycle.py:514`. Two
   lifecycles; `other.run(operation_of_first, ...)` and `other.admit_producer(operation_of_first)`
   raise `ValueError("operation does not belong to this lifecycle")`, and the first lifecycle's
   operation is untouched (still runs and delivers). Mutant: delete the check at 513-514.
6. `test_a_child_producer_is_refused_after_a_faulted_operation_retired` — covers
   `_segmentLifecycle.py:365`. The fake hooks' `submit_native` admits a producer lease and then raises,
   so `_run_owned` latches a fault without waiting for leases (`_segmentLifecycle.py:342-343`); wait
   for the operation's failure delivery; then `admit_producer(operation, parent=lease)` is `None`.
   Mutant: delete 364-365 (a lease is returned for an operation the lifecycle already dropped).

### T2 Scheduler (P1) — `tests/test_runtime_scheduler.py`

1. `test_an_event_batch_error_between_tasks_is_logged_not_raised` — covers
   `sd/runtime/scheduler.py:358->360`. With no current task, call `on_events` with a supplier that
   raises `RuntimeError`. Assert `on_events` returns normally and the scheduler logger got
   "Speech event delivery error"; a following request still completes. Mutant: drop
   `if self._accepts_events_locked(task)` at 358 (`task.error = ...` on `None` raises out of
   `on_events` into NVDA's event bridge).
2. `test_a_pause_failing_after_a_cancel_does_not_restore_the_old_pause` — covers `scheduler.py:504->506`.
   A request speaks on a fake playback that blocks awaiting completion; `pause(True)` succeeds; a
   second `pause(True)` reaches a playback whose `pause` calls `manager.cancel(...)` and then raises.
   Assert the second `pause` raises, and a new request afterwards starts and completes without a
   `pause(False)` (the scheduler is not left paused). Mutant: drop `if self._paused:` at 504 (the old
   paused state `(True, target)` is restored after the cancel cleared it: the next request waits for a
   resume that never comes).
3. `test_shutdown_from_the_worker_thread_does_not_join_itself` — covers `scheduler.py:522->exit`. A
   fake playback's `speak` calls `manager.shutdown()` on the worker thread. Assert `shutdown` returns
   there (no `RuntimeError("cannot join current thread")` is logged as a task error), and the worker
   thread then exits (`eventually(lambda: not thread.is_alive())`). Mutant: drop the
   `current_thread() is not self._thread` check at 522.
4. `test_a_task_error_after_cancellation_leaves_the_request_cancelled` — covers `scheduler.py:543->547`.
   A playback's `speak` calls `manager.cancel(...)` and then raises. Assert the request's `state` is
   `RequestState.CANCELLED` (not `FAILED`), no `done_speaking` is delivered, and the error is logged
   ("Speech scheduler task error"). Mutant: drop `if self._valid_locked(task):` at 543 (state becomes
   `FAILED`).

### T3 Runtime pieces with small harnesses (P3)

1. `tests/test_runtime_request_builder.py` — covers `sd/runtime/requestBuilder.py:39, 46`.
   `test_cancel_during_build_stops_at_the_next_voice_change` and
   `test_cancel_during_build_stops_at_the_next_pause`: a generator yields `"A"`, cancels the request
   (as `test_cancel_during_build_returns_false`, line 289, does), then yields `SelectVoice("b")` or
   `Pause(0.1)` and more text. Assert `queue_speech_sequence` returns `False`, the resolver is never
   called for `"b"` (voice case) and `append_break` is never called (pause case; wrap the task manager
   to record calls). Mutants: replace `if not flush(): return False` at 38-39 / 45-46 with a bare
   `flush()` (the builder goes on resolving the next voice / appending a break to a cancelled request).
2. `tests/test_runtime_completion_policies.py` (legacy adapter, `env` fixture) — covers
   `sd/bridge/engineAdapter.py:192->194, 203->205, 208->210, 114`. The adapter is built with an
   `IndexLedger`, as the voice manager builds every adapter (`sd/voices/manager.py:95`).
   - `test_legacy_speak_with_a_cancelled_token_never_enters_the_core`: token cancelled before
     `speak`; assert the core's `speak` is not called and `speak` returns `None`. Mutant: remove the
     early return at 191-194, or make 193 unconditional (`finish_segment(None)` raises
     `AttributeError`, engineAdapter.py:212-214 and bridge/indexLedger.py:254-255).
   - `test_legacy_speak_cancelled_during_entry_never_enters_the_core`: a token whose `is_cancelled`
     returns `False` on the first read and `True` afterwards; assert the core is not called. Mutant:
     delete the second check at 202-205.
   - `test_legacy_core_error_propagates_unchanged`: the core's `speak` raises `OSError`; assert the
     same `OSError` instance propagates. Mutant: make `finish_segment(context)` at 209 unconditional
     (an `AttributeError` replaces the engine's error).
   - `test_segment_event_factory_must_be_callable`: `configureSegmentEvents(object())` on a drain
     adapter raises `TypeError` and the adapter still refuses drain speech for lack of a factory
     (engineAdapter.py:189-190). Mutant: delete 113-114.
3. `tests/test_index_ledger.py` — covers `sd/bridge/indexLedger.py:123, 200`.
   - `test_bind_requires_a_correlated_contract`: `bind` with a `LEGACY_DONE` contract (with and without
     an index range) raises `InvalidIndexContext`. Mutant: delete 122-123 (no error, or an
     `AttributeError` on `indexRange.minimum`).
   - `test_a_non_int_wire_index_decodes_nothing`: after binding and encoding a segment so that wire
     index `1` decodes to an event, `receiveIndex(sourceId, True)` returns `()` and leaves index `1`
     decodable. Mutant: delete 199-200 (`True == 1` decodes).
4. `tests/test_runtime_composition.py` (voice manager) — covers `sd/voices/manager.py:129, 199,
   212-213, 253->exit, 299`.
   - `test_default_voice_falls_back_to_the_first_voice` (the audit's case): `get_language=lambda: "fr"`
     with no `fr` voice; the main voice is `table[0]` (`x:a` in the audit's example). Mutant: delete
     the `except StopIteration` fallback at 212-213.
   - Extend the waitfactor test at test_runtime_composition.py:447 with `assert manager.waitfactor == 4`
     (getter, 199). Mutant: `return 0`.
   - `test_all_languages_lists_each_primary_language_once`: equals `sorted` primary languages of the
     table (`sd/voices/catalog.py:48`). Mutant: return `[]`.
   - `test_cancel_after_terminate_does_nothing`: `terminate()` then `cancel()` raises nothing
     (task_manager is `None`, manager.py:157). Mutant: drop `if self.task_manager:` at 253.
   - `test_no_voice_instance_is_created_while_terminating`: a bridge fake whose `unbind` calls
     `manager.get_voice_instance(name)` for an uncached voice (terminate cleared publication at 137-138
     and the cache at 145 before unbinding at 149); assert it raises `KeyError(engine)` and nothing is
     cached. Mutant: delete 128-129.
5. `tests/test_lint_rewrites.py` — covers `sd/pipeline/context.py:39-40`.
   `test_current_context_without_a_synth_is_generic`: `getSynth` raises (NVDA start-up before a synth
   exists); `current_context()` returns `GENERIC_CONTEXT`. Mutant: delete the `try/except` at 37-40.

### T4 Main driver (P3) — `tests/test_worldvoice_lifecycle.py`, `tests/test_worldvoice_pipeline_settings.py`

Harness: `tests/worldvoice_harness.py`.

1. `test_check_reports_the_driver_available` — `sd/__init__.py:98`: `SynthDriver.check()` is `True`
   (NVDA lists only synths whose `check()` is true). Mutant: `return False`.
2. `test_a_second_terminate_does_nothing` — `sd/__init__.py:311`: terminate twice; every teardown step
   runs once (for example the event bridge `close` and the task manager `shutdown` are called once).
   Mutant: delete the guard at 310-311.
3. `test_parameter_getters_read_the_main_voice` (parametrized over `volume`, `rate`, `pitch`,
   `inflection`, `variant`, `rateBoost`) — `sd/__init__.py:403, 409, 415, 421, 477, 483`: set the value
   on the main voice instance through the matching setter, read it back through the NVDA property
   (`synth.rate` ...). Use distinct values per parameter so a getter reading another parameter fails.
   Mutant: any getter returning another parameter or a constant.
4. `test_pipeline_settings_are_descriptors_on_the_class` — `sd/__init__.py:548`: for each
   `PIPELINE_SETTINGS` entry with a `driver_id` and `pipeline_config` (sd/__init__.py:555-558),
   `getattr(SynthDriver, driver_id)` is the `_PipelineSetting` object and reading it does not touch the
   pipeline settings (spy on `pipeline_settings.get`). Mutant: delete the `if synth is None` guard at
   547-548.

### T5 Global plugin presenter and panels (P3)

1. `tests/test_role_presenter.py` — `gp/rolePresenter.py:85, 81->exit, 104->exit, 145-146, 147->152`.
   - `test_set_variant_previews_and_discard_restores`: `setVariant(name, "v2")` changes the voice
     instance's `variant`; `discard()` restores the old one. Mutant: make `setVariant` a no-op.
   - `test_a_parameter_without_consistency_changes_only_that_voice`: `keepParameters` off;
     `setParameter("b", "rate", 70)` leaves the main voice and other voices unchanged. Mutant: make
     the preview at 81-82 unconditional.
   - `test_enabling_parameter_consistency_twice_keeps_the_first_snapshot`: enable, change a main
     parameter (previewed to the others), enable again, disable: the other voices return to their
     values from before the first enable. Mutant: drop `and not self.keepParameters` at 96 (the second
     enable re-snapshots the previewed values). The test also covers the `elif` at 104 taking its
     false branch.
   - `test_apply_without_a_speech_section_still_saves`: `speechSection` raises `KeyError`; `apply()`
     returns, roles and flags are saved, nothing is mirrored. Mutant: delete the `try/except` at
     143-146 (OK in the dialog raises).
2. `tests/test_unicode_panel.py` — `gp/panels/detection.py:59-60`.
   `test_stored_timing_not_offered_selects_the_first`: stored `detectLanguageTiming` is `"later"`; the
   timing choice selects index 0 (symmetric to `test_stored_language_not_offered_selects_the_first`,
   line 125). Mutant: delete the `except ValueError` (the panel fails to open).

### T6 VE and Cerence (P1/P2) — `tests/test_vocalizer_segment_drain.py` (the `env` fixture runs both engines), constructor tests in `tests/test_vocalizer_init_cleanup.py`, metadata in `tests/test_driver_voice_base.py`

Line numbers: VE first, Cerence in brackets.

1. `test_output_beyond_the_allocated_buffers_fails_the_segment` (parametrized PCM length, marker
   count) — `VE:270-271 [270-271]`. A native call delivers `VE_MSG_OUTBUFDONE` with
   `cntPcmBufLen > pcmBufLen` or `cntMrkListLen > markBufSize`. Assert the callback returns
   `NUAN_E_TTS_USERSTOP`, nothing is fed to the player, the segment fails with the `ValueError`, and
   the next segment speaks. Mutant: delete the guard at 270-271 (the harness feeds the oversized
   buffer). This is a memory-safety guard on Windows (`string_at` past the buffer).
2. `test_marker_only_output_feeds_no_audio` — `272->283`. `OUTBUFDONE` with `cntPcmBufLen == 0` and one
   bookmark: the index is reported and the player gets no feed call. Mutant: make `if
   data.cntPcmBufLen:` true (an empty chunk is fed).
3. `test_sonic_feeds_a_full_buffer_during_the_call` — `278->279, 279-280`. Sonic enabled (as in
   `test_cancel_discards_sonic_internal_tail_before_next_segment`, line 949) and enough PCM that the
   Sonic output reaches `pcmBufLen` before `ENDPROCESS`. Assert the player is fed before the
   `ENDPROCESS` message is sent. Mutant: delete 278-280 (all audio waits for `ENDPROCESS`: audible
   latency on long text).
4. `test_a_marker_list_reports_only_bookmarks_until_cancelled` — `287->288, 288, 289->286`. One
   `OUTBUFDONE` carries a non-bookmark marker (for example a word mark), bookmark 5 and bookmark 6;
   the index listener cancels speech when it gets 5. Assert the indexes reported are `[5]` (not the
   word mark's id, not 6) and the callback returns `USERSTOP`. Mutants: drop the validity check at
   287-288 (6 is reported after the cancel: a stale index moves say-all); drop the
   `eMrkType == VE_MRK_BOOKMARK` check at 289 (the word mark's id is reported).
5. `test_other_native_messages_do_not_end_the_call` — `291->306`. The last native call sends a message
   other than `OUTBUFREQ`, `OUTBUFDONE` or `ENDPROCESS` (a type from `veTypes`) and no `ENDPROCESS`.
   Assert the callback returns `NUAN_OK` and the segment fails as in
   `test_last_call_without_endprocess_fails_the_segment` (line 1804). Mutant: turn the `elif
   messageType == VE_MSG_ENDPROCESS` at 291 into `else` (the other message counts as ENDPROCESS).
6. `test_nvda_2024_config_opens_the_player_on_the_speech_output_device` — `VE:413-414 [417-418]`.
   NVDA 2024.x keeps `outputDevice` in `[speech]`: NVDA moved it to `[audio]` in config schema 14
   (`ref/nvda/source/config/profileUpgradeSteps.py:425-440`, first released in `release-2025.1`), and
   the add-on supports NVDA 2024.1 (`buildVars.py:39`). With a config stub whose `audio` section has
   no `outputDevice`, the driver constructs and its `WavePlayer` gets `speech.outputDevice`. Mutant:
   delete the `except KeyError` fallback (the driver cannot load on NVDA 2024.x).
7. `test_a_parameter_read_returns_the_queued_value` — `VE:554-557 [558-561]`. With the BgThread held
   (as `test_parameter_read_never_reorders_queued_speech`, line 345), set rate and pitch; a
   `getParameters(instance, rate, pitch)` returns the queued new values without calling the native
   `getParamList`; a read for another instance still goes native. Mutant: skip queued tasks (the old
   native values are returned: NVDA's settings ring announces the old rate).
8. `test_a_pause_failure_refuses_the_running_calls_callbacks` — `VE:796-797 [805-806]`. A native call
   is in progress (fake native blocked mid-call); `pause(True)` raises. Assert a later callback of that
   call is refused (`USERSTOP`, no feed) and the segment fails with the pause error. Mutant: delete
   `call.admitting = False` at 797.
9. `test_a_pause_failure_cleanup_stop_error_is_logged` — `VE:806-807 [815-816]`. `pause` raises and the
   cleanup `_leasedPlayer.stop()` also raises. Assert `pause` raises the pause error (not the stop
   error), "WorldVoice pause failure cleanup failed" is logged, and `terminate()` afterwards returns
   (the stop gate was released). Mutant: delete the `except` at 806-807 (the stop error replaces the
   pause error).
10. `test_terminate_finishes_and_then_raises_a_cancel_error` — `VE:844-845, 857->858, 858
    [853-854, 866->867, 867]`. The cancel inside `terminate` raises. Assert the inner `terminate`
    still ran (resources released, `_terminationDone` set so a second `terminate` does not hang) and
    `terminate` raises the cancel error. Mutant: delete the `except` at 844-845 (cleanup is skipped).
11. `test_terminate_reports_its_first_cleanup_error` (parametrized `close`, `cancel_and_close`) —
    `VE:883-886, 884->885, 884->886 [892-895, 893->894, 893->895]`. The inner `terminate` raises
    (`close`), or both the cancel and the inner `terminate` raise. Assert "WorldVoice VE termination
    failed" (Cerence: "... Cerence ...") is logged, `terminate` raises the close error (`close`) or the
    cancel error (`cancel_and_close`), and a second `terminate` returns. Mutant: make the
    `if self._terminationError is None` at 884 unconditional (the later error wins).
12. `test_metadata_without_a_language_description_uses_the_locale` — `VE:939->942, 942
    [951->954, 954]`. `voiceInfoToMetadata` for a voice whose language NVDA cannot describe and whose
    `displayName` has no `" - "`: `langDescription` is the locale and the description is
    `"<id> - <locale> [VE]"`. Mutant: `langDescription = ""`.
13. Cerence only: `test_cerence_variants_are_empty_without_speech_databases` — `Cerence:943-944`.
    `ttsapi.getSpeechDBList` raises; `variants` is `[]`. Mutant: delete the `try/except` (the variant
    list raises into the voice settings panel).

### T7 SAPI5 (P1/P2) — `tests/test_sapi5_segment_drain.py` (harness `tests/sapi5_drain_harness.py`)

`useWasapi` is a user setting of NVDA's SAPI5 driver (`ref/nvda/source/synthDriverHandler.py:219-222`,
`ref/nvda/source/gui/settingsDialogs.py:1678`), so the legacy-audio paths are user-reachable.

1. `test_a_dead_worker_rejects_new_speech` — `sd/driver/SAPI5/__init__.py:105-106, 427->428, 428`.
   The worker thread has exited (fake thread not alive). Assert a new segment is rejected with a
   failure event carrying "SAPI5 playback worker is unavailable" (not an exception out of
   `speak_segment`), and ordinary `speak` raises that `RuntimeError`. Mutant: delete the `try/except`
   at 103-106 (the exception escapes the admission into the scheduler's speak call).
2. `test_a_purge_failure_after_an_idle_failure_latches` — `SAPI5:155-156`. A segment's drain `idle()`
   raises, `player.stop()` succeeds, `tts.Speak(None, purge)` raises. Assert the segment fails with
   the idle error, `driver._segmentHost.control_error` is the purge error, and the next segment is
   rejected with it. Mutant: delete the inner `try/except` at 152-156 (the purge error escapes the
   drain; the host only fails the segment and stops the player again, segmentHost.py:605-612, so the
   successor speaks on an engine in an unknown state).
3. `test_a_stale_audio_stream_write_is_dropped` — `SAPI5:166->167, 167, 171->172, 172`. After a voice
   reload replaced `_segmentAudio`, the old stream object's `ISequentialStream_RemoteWrite` is called
   with `pcbWritten = [99]`. Assert it returns `S_OK`, `pcbWritten[0] == 0`, and the player gets no
   feed. Mutants: delete 166-167 (`pcbWritten` keeps 99); delete 171-172 (the old stream's PCM is fed
   to the new request).
4. `test_notify_dispatches_start_and_bookmark_and_ignores_other_events` — `SAPI5:287->288, 288,
   289->291, 291, 291->286, 291->292, 292`. Through `ISpNotifySink_Notify`, the harness's event
   enumerator yields `START_INPUT_STREAM`, `TTS_BOOKMARK` (id 7), an event of another type, then
   `END_INPUT_STREAM`. Assert the driver became speaking at the start, index 7 is reported once, and
   the other event changed nothing. Mutants: drop the START or BOOKMARK dispatch; turn the
   `elif ... TTS_BOOKMARK` into `else`.
5. `test_start_stream_marks_speaking_only_for_the_current_stream` — `SAPI5:319->320, 320, 321->exit`.
   WASAPI: `StartStream` for the current valid request's stream sets NVDA's speaking state
   (`ref/nvda/source/synthDrivers/sapi5.py:477-484`); for an old stream number it does not. Mutants:
   drop the validity condition at 319; make 321 true.
6. `test_legacy_audio_speaks_in_the_caller_and_reports_bookmarks_at_once` — `SAPI5:451->453, 453,
   326->328, 328->329, 329, 337->338, 338->339, 339`. `useWasapi = False`: `speak` calls `tts.Speak` on
   the calling thread before it returns and creates no worker record (NVDA's `_speak_legacy`,
   `ref/nvda/source/synthDrivers/sapi5.py:985-995`); a `Bookmark` callback reports its
   index immediately (NVDA's legacy behaviour, `ref/nvda/source/synthDrivers/sapi5.py:486-496`).
   Mutants: delete the legacy `return super().speak(...)` at 451-453 (the request goes to the worker);
   delete the forward at 328-329 or 338-339 (legacy audio reports no index: say-all stops tracking).
7. `test_a_bookmark_outside_any_request_on_wasapi_is_ignored` — `SAPI5:328->330, 330, 338->340, 340`.
   WASAPI with no current record: `Bookmark` and `onIndexReached` report nothing. Mutant: make the
   conditions at 328 / 338 ignore `not driver.player`.
8. `test_a_cancelled_requests_bookmarks_are_ignored` — `SAPI5:331->332, 332, 341->342, 342`. The
   current record is cancelled (token) before its `Bookmark` and `onIndexReached` arrive: no index is
   reported. Mutant: delete 331-332 / 341-342.
9. `test_an_ordinary_wasapi_bookmark_reports_through_nvda` — `SAPI5:343->344, 344`. Ordinary speech
   with indexes 7 and 9; the fake player runs the `onDone` callbacks queued by NVDA's `Bookmark`
   (`feed(None, 0, onDone)`) before `EndStream`. Assert indexes `[7, 9]` are each reported once (the
   tail at `_onEndStream`, SAPI5:532-537, does not repeat them). Mutant: delete 343-344 (indexes go
   through the segment path, which needs `record.work`).
10. `test_a_segment_bookmark_reports_once_and_drops_earlier_ones` — `SAPI5:348->349, 349, 351->350`.
    A segment with indexes 7, 8, 9: `onIndexReached` for 8 reports 8 and drops 7; a repeated 8 or an
    unknown 42 reports nothing; at `EndStream` only 9 is reported. Mutants: drop the `index not in
    bookmarks` check at 348 (42 is reported); make the loop at 350-352 pop only one entry (7 is reported
    at the end).
11. `test_a_purge_failure_while_cancelling_latches_a_control_fault` — `SAPI5:584-585`. While the
    worker handles a cancel (`record is None` branch, 581-586), `tts.Speak(None, purge)` raises. Assert
    `driver._segmentHost.control_error` is that error, the next segment is rejected with it, and
    `needsVoiceReload()` is true. Mutant: delete the `try/except` at 582-585 (the worker thread dies;
    the next speech fails with "worker is unavailable" instead, and the purge error is lost).
12. `test_a_stream_mismatch_fails_the_request` — `SAPI5:595->596, 596`. The fake `tts.Speak` calls the
    sink's `StartStream(7)` synchronously and returns stream 8. Assert the segment fails with
    "SAPI5 callback stream did not match the admitted request" and the next segment speaks. Mutant:
    delete 595-596 (the request waits for stream 8's end; the test fails on its wait).

### T8 OneCore (P1/P2) — `tests/test_onecore_segment_drain.py` (harness `tests/onecore_drain_harness.py`)

1. `test_segment_conversion_without_prosody_options_uses_the_pre_api5_converter` —
   `sd/driver/OneCore/__init__.py:161->164, 164`. `supportsProsodyOptions` false: the segment's text is
   built by `_OcPreAPI5SsmlConverter` (spy on both converter classes). Mutant: always use
   `_OcSsmlConverter`.
2. `test_cancel_before_any_audio_stops_nothing` — `OneCore:183->exit, 188->exit`. A segment is
   cancelled before its first callback created the player (`_player` is `None`): no exception, no
   control error, the next segment speaks. Mutant: drop `if player:` at 183 / 188 (`None.stop()` is a
   stop failure, which latches a control fault: the first cancel would disable OneCore).
3. `test_a_segment_without_a_player_drains_at_once` — `OneCore:194->210`. A segment whose callback
   produced no audio and created no player completes (`SEGMENT_DRAINED`, no failure). Mutant: drop
   `if player:` at 194 (`AttributeError` fails the segment).
4. `test_a_token_cancelled_queued_segment_is_abandoned_unopened` — `OneCore:355->356, 356-357`. The
   worker is busy with segment A; segment B's token is cancelled without calling the driver's
   `cancel` (an external token, `_segmentLifecycle.py:251-253`). Assert B's player `open` and
   `ocSpeech_speak` are never called for B and segment C after it speaks. Mutant: delete 355-357
   (B is begun and the player opened for it).
5. `test_a_segment_cancelled_while_the_player_opens_is_never_spoken` — `OneCore:392->393, 393`. The
   fake player's `open` cancels the segment's token. Assert `ocSpeech_speak` is not called for it and
   the next segment speaks. Mutant: delete 392-393.
6. `test_a_callback_after_cancel_feeds_nothing` — `OneCore:448->449, 449`. NVDA's cancel set
   `_earlyExitCB`; the in-flight utterance's native callback then arrives with audio. Assert nothing is
   fed and no index is reported. Mutant: drop `or self._earlyExitCB` at 448.
7. `test_truncated_wav_fails_the_segment_without_feeding` (parametrized `header_before_player`,
   `payload`) — `OneCore:472->473, 473, 498->exit`. `header_before_player`: the first segment's
   callback has `length < WAVE_HEADER_LENGTH` (no player yet); `payload`: the header announces more
   data than `length` holds. Assert the segment fails with `ValueError`, nothing is fed, the exception
   does not escape the callback, and the next segment speaks. Mutants: delete 472-473 (a read past the
   buffer); drop `if self._player:` at 498 (`AttributeError` escapes the callback).
8. `test_cancel_during_a_paused_final_idle_publishes_no_done` — `OneCore:522->exit`. Ordinary
   speech; the last callback reaches the queue-empty idle while paused (513-521 wait); cancel. Assert
   no `synthDoneSpeaking` is published. Mutant: drop the condition at 522 (a DONE after cancel: NVDA's
   say-all advances wrongly).
9. `test_a_callback_for_a_token_cancelled_segment_feeds_nothing` — `OneCore:535->536, 536`. The
   segment's token is cancelled just before its callback (no driver `cancel`): `_feedSegment` returns
   `False` and nothing is fed. Mutant: delete 535-536.

### T9 RHVoice (P1) — `tests/test_rhvoice_segment_drain.py`

1. `test_a_final_idle_failure_fails_only_that_record` (parametrized ordinary, segment) —
   `sd/driver/RHVoice/__init__.py:273-274`. The inner player's `idle()` raises. Assert the segment
   fails with that error (ordinary: retires with it, no DONE), and the next request speaks. Mutant:
   delete the `try/except` at 270-274 (the exception escapes `_QueuedSpeech.__call__`, the inner
   `TTSThread` only logs it, `driver/RHVoice/driver/__init__.py:419-428`, and the record is never
   retired: speech stays stuck).
2. `test_a_cancel_stop_failure_latches_and_raises` — `RHVoice:459->460, 460`. The inner cancel
   succeeds; the final `player.stop()` (455-456) raises. Assert `cancel` raises that error and
   `driver._segmentHost.control_error` is it. Mutant: delete `error = exc` at 460 (cancel returns as if
   it stopped).

### T10 eSpeak (P1) — `tests/test_espeak_segment_drain.py` (harness `tests/espeak_drain_harness.py`)

1. `test_cancel_after_a_control_fault_skips_the_native_cancel` — `sd/driver/Espeak/__init__.py:31->32,
   32`. With a control error latched, NVDA's stop calls `espeak_ng_Cancel`; assert it returns `EE_OK`
   without calling the native function. Mutant: delete 31-32.
2. `test_a_failed_ordinary_utterance_clears_speaking_and_reports_done` (parametrized `conversion`,
   `synth`) — `Espeak:115-116, 195->196, 196, 91`. `conversion`: `BaseSynthDriver.speak` raises inside
   `submit`; `synth`: `espeak_Synth` returns an error code. Assert `speak` itself returns normally
   (`conversion`), `_espeak.isSpeaking` is `False` afterwards, `synthDoneSpeaking` is published once,
   and the next utterance is spoken in full. Mutants: delete `self._port.markNotSpeaking()` at 196 (the
   next utterance is aborted early, the comment at 89-90); delete the `except` at 115-116 (`conversion`:
   the exception reaches NVDA's `speak`).

## 6. Class (b): left untested, with reasons

| Module:lines / arcs | Kind | Why |
| --- | --- | --- |
| `gp/panels/base.py:30->32` | b-inv | `settingsSizerHelper` is always `None`: every caller passes only the sizer (`gp/panels/log.py:51`, `gp/panels/engine.py:42`, `sd/ui/voicePanel.py:58`, NVDA `ref/nvda/source/gui/settingsDialogs.py:250, 406`). |
| `gp/panels/role.py:163->164, 164` | b-inv | Items and `_voiceNamesByChoiceIndex` are always set together (role.py:174-179); `wx.Choice` returns `NOT_FOUND` (-1, handled at 161) or a valid index. |
| `gp/rolePresenter.py:45->44` | b-inv | A locale's voice names are unique: the catalog keys specs by name (`sd/voices/catalog.py:36-39`). |
| `sd/bridge/nvdaEvents.py:233->exit` | b-inv | `_handler` is `None` only before `start` or after `close`; `close` sets `_closed`, caught at 225, and the driver starts the bridge before any engine binds (`sd/__init__.py:249` before the voice manager at 253). |
| VE/Cerence `112->114, 114, 134->135, 135, 174->exit, 186->exit, 193->exit, 235->exit, 240->241, 241` | b-gc | Dead `weakref` to the driver. |
| VE/Cerence `216->218, 218->219, 219` | b-inv | The inner driver always installs `veCheckForError` on `ve_ttsProcessText2Speech` (`driver/VE/driver/ve2/__init__.py:44`), which raises for exactly the codes 218 tests (`ve2/__init__.py:16-23`); kept for an inner without the checker. |
| VE/Cerence `259->260, 260` | b-race | Validity re-check under `_processingLock` after `_callbackAdmission` checked it (VE:610). |
| VE/Cerence `299->301`, `304->306` | b-equiv | 301 and 306 re-check validity and 303 resets the buffer, so a cancelled record's Sonic tail is dropped and `call.ended` cannot complete a cancelled record (ENGINE_DONE also needs `_recordValid`, VE:517). |
| VE `475->482` [Cerence `479->486`] | b-equiv | For a segment the submit error is recorded (segmentHost.py:309) and a failed segment never drains (segmentHost.py:602-604). |
| VE `621->exit` [Cerence `630->exit`] | b-race | `_feedCallback` re-checks validity after `_process` checked it. |
| Espeak `37->39, 43->44, 44, 165->exit` | b-gc | Dead `weakref`. |
| Espeak `185-187, 186->exit, 186->187` | b-inv | NVDA's index hook reaches the override only before the first `_beginSpeech` replaced it (Espeak:159-168); no index arrives before speech. The override stays (`NVDA_OVERRIDES`, Espeak:76). |
| Espeak `206->211` | b-race | Cancel or terminate between `_retireSpeech` starting the thread and the thread's check. |
| Espeak `208-209`; OneCore `431-432, 566-567` | b-inv | `synthDoneSpeaking.notify` cannot raise for a handler error: NVDA's `Action.notify` logs and swallows it (`ref/nvda/source/extensionPoints/__init__.py:48-56`). |
| OneCore `90->exit` | b-race | A native callback after the worker released its record. |
| OneCore `121->122, 122` | b-gc | Dead `weakref`. |
| OneCore `326->327, 327` | b-race | Admission was checked under the same condition at 176; only a terminate or fault in between reaches it. |
| OneCore `419->422` | b-inv | `_segmentNative` is the record being spoken until this `finally` clears it; nothing else replaces it on the worker. |
| OneCore `557->562` | b-inv | A control fault before any player exists needs a stop or pause failure, and both need a player. |
| OneCore `635->640, 640` | b-race | Generation or stop gate changed between 631 and 634. |
| RHVoice `100->101, 101` | b-race | `cancelFlag` set while the record is still valid and admitted. |
| RHVoice `138` | b-inv | `_NativeLibrary` overrides the only three library functions the vendored `SpeakText` calls (`driver/RHVoice/driver/__init__.py:398-410`; RHVoice:140-172). Kept for a future inner. |
| RHVoice `148-150` | b-equiv | The audit listed it; on inspection the same error is recorded by `_QueuedSpeech`'s own `except` (RHVoice:253-258) because the inner `SpeakText` does not catch (`driver/RHVoice/driver/__init__.py:395-410`). No test can tell them apart. |
| RHVoice `193->194, 194, 243->244, 244` | b-gc | Dead `weakref`. |
| RHVoice `200->201, 201` | b-inv | Every feed comes from a native callback bound by `bound_callback` (RHVoice:397) or the worker's bound task (RHVoice:255-256). |
| RHVoice `203->204, 204, 249->251, 251, 254->261` | b-race | Cancel or fault between the worker's dequeue and its admission (RHVoice:246-256). |
| RHVoice `218-219` | b-inv | The inner's only `onDone` is `synthIndexReached.notify` (`driver/RHVoice/driver/__init__.py:232`), which does not raise (see Espeak 208-209). |
| RHVoice `319-322` | b-equiv | The audit listed it; the cleanup only removes an entry from the private `_segmentById`; `cancel` abandons a stale abandoned record idempotently (segmentHost.py:429-450) and a callback for that identity is refused (record closed). Nothing public changes. |
| SAPI5 `131->exit` | b-race | `native.player` is set under `_threadCond` right after `begin` (SAPI5:577-580); `request_stop` sees the record as current in between. |
| SAPI5 `145->146, 146-147` | b-inv | Segments are admitted only with a WASAPI player (SAPI5:107-108) and the player is set at begin (580). |
| SAPI5 `168->169, 169, 199->200, 200, 227->228, 228, 233->234, 234, 239->240, 240, 296->297, 297` | b-gc | Dead `weakref`. |
| SAPI5 `180->181, 181` | b-race | The current record sealed between `host.current()` and admission. |
| SAPI5 `202->203, 203` | b-inv | NVDA feeds through `driver.player`, which is always the current lease (SAPI5:483-484). |
| SAPI5 `206->207, 207` | b-inv | All worker speech begins a record (577); legacy audio does not use the player. |
| SAPI5 `350->353` | b-inv | 348 guarantees `index in bookmarks` under `indexLock`, so the loop always breaks. |
| SAPI5 `353->exit`, `514->exit`, `536->534`, `538->540`, `569->571, 571`, `619, 618->619` | b-race | Cancel or a COM callback between a check and its re-check (`571`: the worker's own comment, "after a reload race"). |
| SAPI5 `625->627` | b-equiv | `clear()` on an empty deque is a no-op. |
| SAPI5 `661->660` | b-inv | One request runs at a time, so its bookmark list is the first in `_bookmarkLists` (588). |
| SAPI5 `678->681` | b-inv | `sonicStream` is always created with the WASAPI worker (507), the only caller of `_purgeCancelledSpeech` (583, 621). |
| `_segmentLifecycle.py:310->279` | b-race | `stop_done` set between 297 and 308. |
| `_segmentLifecycle.py:322->323, 323` | b-race | Cancel or fail between releasing the lock at 272 and `_run_owned` taking it. |
| `scheduler.py:102->103, 103` | b-equiv | Without it, `set_*` on a cancelled future raises `InvalidStateError`, caught at 109-111 with the same result. |
| `scheduler.py:110->111, 111` | b-inv | Only the scheduler settles futures and each once; 102 already returned for a done future. |
| `scheduler.py:454->455, 455` | b-inv | `TaskManager.cancel_current` has no production caller (only `tests/test_runtime_scheduler.py:449-462`); see §10 Q2. |
| `scheduler.py:486->487, 487` | b-equiv | After shutdown, `cancel` cleared `_pause_target` and no task is valid, so no playback is paused either way; only the race between `_closed` and that cancel differs. |
| `scheduler.py:619->620, 620` | b-inv | Every setter of the done event either needs completion or an error (369) or invalidates the task first (443-444, 456-457, 597). Kept: "A wake is only a signal" (612). |
| `segmentHost.py:528->530` | b-inv | Engines retire only the record they began (Espeak:160/192, VE:504/521, Cerence:508/525, RHVoice:252/275, SAPI5:577/672, OneCore:359/411). |
| `segmentHost.py:533->535` | b-inv | A segment record loses its producer only through `abandon` (443), and no engine retires an abandoned record (VE:512 `skipped`, RHVoice:249-251, OneCore:408-410). |
| `sd/ui/voicePanel.py:204->202` | b-inv | The previous row is always placed in `settingsSizer` before the row that follows it. |
| `sd/unicodeScripts/lookup.py:10->11, 11` | b-inv | `SCRIPT_RANGE_STARTS` starts at 0 and callers pass `ord()` values. Not deleted: without it a negative input would index the last range (different result). |

## 7. Dead code deletion

Only `sd/engineRegistry/discovery.py:77-78`:

```python
	if not path.is_file():
		return None
```

Evidence: `_load_manifest` has two callers, `discover_engine_specs` at discovery.py:138 and 149, and
both `continue` before the call when `not manifest_path.is_file()` (135-137, 146-148). The function is
private (no other reference in `addon/` or `tests/`). Behaviour after deletion: identical for every
caller; in the nanosecond window where the file disappears between the caller's check and the read,
`read_text` raises and line 81-87 returns `None` with a warning instead of `None` silently, the same
outcome as a disappearance between today's two checks and the read.

No other deletion: the remaining (b-inv) guards depend on invariants held by another module, the
vendored inner driver or NVDA, so deleting them would be behaviour-neutral only while those hold. The
existing tests of discovery (`tests/test_engine_discovery.py:112, 149`) cover both callers; no new
test is needed.

## 8. How the tests are written

- Use the existing harnesses (`tests/*_harness.py`, `conftest.py`, `nvda_stubs.py`); no new harness
  module and no test module importing another. Tabs; ruff `0.16.3` (`prek` runs it).
- No fixed sleeps: `tests/waiting.py` (`eventually`, `stays_unset`, `holds_within`, `WAIT_TIMEOUT`,
  `HOLD_TIMEOUT`). Concurrency tests drive threads with `Event`/`Condition` gates the fake owns, so the
  interleaving is forced, not timed.
- Assert behaviour, not coverage: each test asserts what §5 lists. Log assertions only where §5 says
  the log is the contract.
- **Red, then green.** The code is already correct, so for each new test the implementer:
  1. applies the named mutant in a scratch copy (a temporary worktree created under the scratchpad
     from the branch, or a copied file loaded through the same loader; never edit the branch's
     `addon/` files for this, never `git stash`), runs the test there and records the failure;
  2. runs the test on the branch and records the pass.
  The plan writes the expected red and green output for each test; the ledger keeps the command and
  result. A test whose mutant survives is not added as is: strengthen the assertion, or reclassify
  the item as (b-equiv) with a `Ruling:`.
- Prefer extending an existing parametrized test when the scenario is a new case of it (as T1.1 or
  T3.4's waitfactor line); otherwise a new test next to its neighbours.

## 9. Verification

- Full suite: 3243 + the new tests, **0 skipped**, run once more after the last commit.
- Each new concurrency test (T1.2, T1.4, T1.6, T2, T6.3-T6.11, T7, T8, T9, T10) run 5 times
  (`pytest -q --count` is not installed; loop 5 runs of `pytest <nodeid>`), all green.
- Coverage with the §2 command and the memory watchdog: TOTAL above 96.77 % and close to §4's 98.67 %;
  module by module no line or arc that was covered becomes missed (compare `coverage json` of
  `master` and the branch). Any (a) item still missed is either covered or reclassified with a
  `Ruling:`.
- `prek run --all-files` all Passed; `git diff --check` clean.
- Protected paths (DEVELOPMENT_WORKFLOW.md §7) empty:
  `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py addon/synthDrivers/WorldVoice/unicodeScripts/unspaced_common_data.py`
  and `git ls-files addon/synthDrivers/WorldVoice/driver/Neural`.
- `git diff --stat master -- addon` shows only `sd/engineRegistry/discovery.py` with 2 deletions.
- Linux only: Windows NVDA, real audio devices and engine SDKs are not exercised (as always, §7 of
  the workflow).

## 10. Open questions

- **Q1. Audit items reclassified as (b).** `RHVoice_new_message` raising (RHVoice:148-150) and the
  submit-failure cleanup (RHVoice:319-322) were among the audit's "most valuable" gaps, but neither
  has an observable effect (§6). Default: leave untested. Decided by orchestrator with the recommended
  default; user may override before merge.
- **Q2. `TaskManager.cancel_current` has no production caller** (`scheduler.py:451-460`; only
  `tests/test_runtime_scheduler.py:449-462` uses it). Default: keep it and its test, no new test for
  its idle branch; removing an unused API is a separate cleanup. Decided by orchestrator with the
  recommended default; user may override before merge.
- **Q3. Race-only and dead-`weakref` branches** (b-race, b-gc, §6) stay untested rather than adding
  hooks inside private locks. Decided by orchestrator with the recommended default; user may override
  before merge.
- **Q4. Defensive guards proven unreachable today** (b-inv) are kept, not deleted; only
  `discovery.py:77-78` goes (§7). Decided by orchestrator with the recommended default; user may
  override before merge.
- **Q5. Tests reaching a driver's segment host** (`env.driver._segmentHost.control_error`) read a
  public property of a private attribute, as the existing drain suites already do. Decided by
  orchestrator with the recommended default; user may override before merge.
- **Q6. A test that exposes a product bug.** The implementer keeps the test out (or marks the finding
  in the ledger), does not fix `addon/` in this phase, and reports it; the orchestrator brings it to
  the user. Decided by orchestrator with the recommended default; user may override before merge.

No question needs the user before implementation: nothing here changes what an NVDA user hears or
sees.
