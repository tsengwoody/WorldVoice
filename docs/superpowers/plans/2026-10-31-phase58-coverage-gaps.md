# Phase 58 coverage gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** Add a behavioural test for every class-(a) coverage gap of the spec (81 items, 118 lines / 84 arcs), each killing its named mutant, and delete the one dead guard in `discovery.py`, so TOTAL coverage moves from 96.77 % towards 98.67 % with no behaviour change in `addon/`.

**Architecture:** Test-only phase plus one 2-line deletion. Each task owns one area of the spec's §5 (T1–T10) and adds tests next to their neighbours in the existing test module, using the existing harnesses (`tests/*_harness.py`, `conftest.py`, `nvda_stubs.py`, `tests/waiting.py`). Every new test is proven red against the spec's named mutant in a scratch worktree and green on the branch; the ledger records both.

**Tech Stack:** pytest (+ pytest-cov), Python threading gates (`threading.Event`/`Condition`), `tests/waiting.py`, git worktrees for mutants, prek (ruff `==0.16.3`).

**Spec:** `docs/superpowers/specs/2026-10-31-phase58-coverage-gaps-design.md` (scenario, assertion and mutant of each test are in its §5; this plan names the tests, the files, the order and the checks, and does not repeat the scenarios).

## Global Constraints

- Worktree `/workspace/WorldVoice-phase58`, branch `phase58-coverage-gaps`; `ref` is a git-ignored symlink, never staged. The main checkout is not touched.
- `addon/` changes only by the spec §7 deletion (`git diff --stat master -- addon` = `sd/engineRegistry/discovery.py`, 2 deletions). No product fix: a test exposing a bug stops that item (spec Q6) — record it in the ledger under **PRODUCT BUG**, keep the test out or mark it `xfail(strict=True, reason=...)` only if needed to keep the suite green, report it.
- Never touch inner drivers (`driver/<Engine>/driver/`), `driver/sonic/`, the generated `unicodeScripts/script_data.py` / `unspaced_common_data.py`; never add Neural. Engine drivers stay independently installable (tests may load each driver, drivers never import each other).
- No new harness module, no test module importing another test module, no test-only hook in add-on code. Tabs. ruff pinned `==0.16.3` (prek on commit; re-stage and re-commit when a hook modifies a file; never `--no-verify`).
- No fixed sleeps: `eventually`, `stays_unset`, `holds_within`, `WAIT_TIMEOUT`, `HOLD_TIMEOUT` from `tests/waiting.py`; interleavings forced by gates the fake owns.
- Assert behaviour (spec §5's "assert"), not coverage. Log assertions only where §5 names the log.
- An (a) item that proves unreachable, or whose mutant survives a strengthened assertion, moves to (b) with `Ruling: <decision> — <reason> — <cost if wrong>`; never weaken an assertion to reach a line.
- git: stage explicit paths; `git diff --cached --stat` before each commit; English `<type>: <summary>` with a why body (`test:` for tests, `refactor:` for the deletion); no `Co-Authored-By`; no push; never `git stash`. Scratch worktrees only under the scratchpad, removed only if created here.
- Resources: one pytest/coverage process at a time, always under `impl/runpy.sh` (MemAvailable < 3 GB → `kill -TERM` of its own PID only).

## Review Focus

1. **Speech stuck after an engine error at cancel/pause/stop time** (a stop, pause, purge or idle that raises while the user presses Ctrl). The user expects the next utterance to speak. → every P1 test asserts the next segment/request speaks: Task 2 (T1.1, T1.2, T1.4), Task 3 (T2.2, T2.4), Task 7 (T6.1, T6.8–T6.11), Task 8 (T7.2, T7.11, T7.12), Task 9 (T8.2, T8.7), Task 10 (T9.1), Task 11 (T10.2).
2. **NVDA 2024.x config layout** (`outputDevice` still in `[speech]`). The user expects VE/Cerence to load on every supported NVDA. → Task 7 `test_nvda_2024_config_opens_the_player_on_the_speech_output_device`.
3. **SAPI5 with "use WASAPI" off** (a real NVDA setting). The user expects say-all to keep tracking (bookmarks reported). → Task 8 `test_legacy_audio_speaks_in_the_caller_and_reports_bookmarks_at_once`.
4. **Stale indexes after cancel** (a bookmark or callback that arrives after the user interrupted say-all). The user expects the cursor not to jump. → Task 7 (T6.4), Task 8 (T7.8, T7.10), Task 9 (T8.6, T8.9).
5. **Settings dialog with unexpected stored values or a missing NVDA section** (stored timing not offered, no `[speech]` section on apply). The user expects the dialog to open and OK to save. → Task 6 (`test_stored_timing_not_offered_selects_the_first`, `test_apply_without_a_speech_section_still_saves`).

---

## Tooling (scratchpad, not committed)

`SP=/tmp/claude-0/-workspace-WorldVoice/a68674de-080e-47c7-b392-44942b53ef24/scratchpad/p58`, scripts in `$SP/impl/`:

| Script | Use | Pass output |
|---|---|---|
| `runpy.sh <cwd> <log> <pytest args>` | one pytest under the memory watchdog | `rc=0 killed=0` |
| `mut.sh <name> <file> <python-edit-script>` | `git worktree add $SP/impl/mut-<name> HEAD` (own `ref` symlink), apply the mutant by a scripted exact-string replace (fails if the old text is not found exactly once), run the given node ids there, then `git worktree remove` it | test(s) FAIL |
| `covcmp.py BEFORE AFTER` | per-module coverage comparison against `impl/base-cov.txt` (spec §2 run) | `COVERAGE GATE OK` |

**Mutant proof** (every new test): (1) `mut.sh` with the spec's mutant → the new test fails (record the assertion/timeout that failed); (2) the same node id on the branch passes. Ledger line: `<test id> | mutant <file:line change> | red: <failure> | green: pass`.

**Task verification block** (every task, before its commit): the task's test file(s) alone → all pass; `prek run --files <touched>` → Passed; `impl/runpy.sh … -q -p no:cacheprovider tests` → expected passed count, 0 skipped, `rc=0 killed=0`.

**Running counts** (passed, 0 skipped; a different count from a parametrization choice is recorded as a Ruling):

| After | Count | | After | Count |
|---|---|---|---|---|
| base `1679ce9` | 3243 | | Task 7 VE/Cerence | 3311 |
| Task 1 deletion | 3243 | | Task 8 SAPI5 | 3324 |
| Task 2 T1 | 3251 | | Task 9 OneCore | 3334 |
| Task 3 T2 | 3255 | | Task 10 RHVoice | 3337 |
| Task 4 T3 | 3268 | | Task 11 eSpeak | 3340 |
| Task 5 T4 | 3277 | | | |
| Task 6 T5 | 3282 | | | |

**Batches** (§3.2, 11 tasks): batch 1 = Tasks 1–6 (core, runtime, driver shell, global plugin), stop and report; batch 2 = Tasks 7–11 (engine drivers), then Task 12 final verification (no commit of code) and report.

---

### Task 1: Delete the dead manifest guard

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/engineRegistry/discovery.py:77-78`

**Interfaces:**
- Consumes: none. Produces: `_load_manifest(path)` unchanged signature; callers unchanged.

- [ ] **Step 1:** Confirm the two callers (`discovery.py:135-137`, `146-148`) `continue` before calling when `not manifest_path.is_file()`, and `rg _load_manifest addon tests` shows no other reference.
- [ ] **Step 2:** Delete the two lines `if not path.is_file():` / `return None` in `_load_manifest`.
- [ ] **Step 3:** `python3 -m pytest -q tests/test_engine_discovery.py` → all pass; `git diff --stat master -- addon` → `discovery.py | 2 --`.
- [ ] **Step 4:** Verification block → **3243 passed**.
- [ ] **Step 5:** Commit `refactor: drop the dead manifest guard in discovery` (body: both callers already skip a missing file; spec §7).

### Task 2: Segment host and lifecycle error paths (T1)

**Files:**
- Test: `tests/test_segment_host.py`, `tests/test_segment_lifecycle.py`

**Interfaces:**
- Consumes: `env` fixtures and `FakeStrategy`/`Hooks` of the two modules; `SegmentHost.control_error`, `.faulted`, `.latch_control_error`, `.terminate`, `.reset`, `.cancel`; `OrdinaryOutcome`; `SEGMENT_FAILED`.
- Produces: nothing for later tasks.

- [ ] **Step 1: Write the tests (spec §5 T1.1–T1.6)**

```python
# test_segment_host.py
@pytest.mark.parametrize("case", ["cancelled", "failed"])
def test_ordinary_retire_survives_a_failing_stop(env, caplog, case):
	# stop_player raises OSError("stop failed")
	# cancelled: outcome == OrdinaryOutcome(cancelled=True, error=None); ERROR "Error stopping cancelled Fake playback" with exc_info
	# failed: isinstance(outcome.error, RuntimeError) (missing barrier); record.error is the OSError; "Error stopping failed Fake playback"

@pytest.mark.parametrize("case", ["plain", "chained"])
def test_a_raising_lifecycle_run_fails_the_segment(env, case):
	# eventually: exactly one SEGMENT_FAILED; its error is the RuntimeError (plain) / the OSError __cause__ (chained)
	# a following segment is accepted and completes

def test_reset_after_terminate_keeps_the_host_terminated(env):
	# host.control_error is the latched error; host.faulted; a new segment rejected with "driver has terminated"

# test_segment_lifecycle.py
def test_a_raising_retirement_callback_does_not_stop_delivery(env, caplog):
	# operation 19's terminal event delivered; "segment retirement callback failed for segment 18" logged

def test_an_operation_of_another_lifecycle_is_refused(env):
	# other.run(op, ...) and other.admit_producer(op) raise ValueError("operation does not belong to this lifecycle")
	# the first lifecycle still runs and delivers op

def test_a_child_producer_is_refused_after_a_faulted_operation_retired(env):
	# after the failure delivery: lifecycle.admit_producer(operation, parent=lease) is None
```

- [ ] **Step 2: Green on the branch:** `python3 -m pytest -q tests/test_segment_host.py tests/test_segment_lifecycle.py -k "failing_stop or raising_lifecycle_run or reset_after_terminate or raising_retirement or another_lifecycle or child_producer_is_refused"` → 8 passed.
- [ ] **Step 3: Red on mutants** (`mut.sh`): drop try/except `segmentHost.py:544-547` → `cancelled` fails (OSError raised from retire); drop try/except `560-563` → `failed` fails; drop `self.record_error(record, stop_error)` at 564 → `failed` fails (`record.error is None`); drop except `636-642` → both `run` cases fail on `eventually`; `error.__cause__ or error` → `error` → `chained` fails; delete `322-323` → reset test fails (control_error None); drop try/except `_segmentLifecycle.py:448-455` → retirement test fails on `eventually`; delete `513-514` → another-lifecycle fails (no ValueError); delete `364-365` → child producer gets a lease.
- [ ] **Step 4:** Verification block → **3251 passed**; run each of the 6 functions 5× (concurrency).
- [ ] **Step 5:** Commit `test: cover the segment host and lifecycle error paths`.

### Task 3: Scheduler error paths (T2)

**Files:**
- Test: `tests/test_runtime_scheduler.py`

**Interfaces:**
- Consumes: `scheduler`, `manager`, `output`, `port` fixtures, `speech()`, `event()`; `RequestState.CANCELLED`; logger "Speech event delivery error", "Speech scheduler task error".

- [ ] **Step 1: Write the tests (spec §5 T2.1–T2.4)**

```python
def test_an_event_batch_error_between_tasks_is_logged_not_raised(...):
	# on_events(raising supplier) returns; "Speech event delivery error" logged; a following request completes
def test_a_pause_failing_after_a_cancel_does_not_restore_the_old_pause(...):
	# second pause(True) raises; a new request then starts and completes without pause(False)
def test_shutdown_from_the_worker_thread_does_not_join_itself(...):
	# no "cannot join current thread" task error logged; eventually(lambda: not thread.is_alive())
def test_a_task_error_after_cancellation_leaves_the_request_cancelled(...):
	# request.state is RequestState.CANCELLED; no done_speaking; "Speech scheduler task error" logged
```

- [ ] **Step 2: Green:** the 4 tests pass.
- [ ] **Step 3: Red on mutants:** `scheduler.py:358` guard dropped → T2.1 raises out of `on_events`; `504` `if self._paused:` dropped → T2.2 next request never completes (fails on its wait); `522` thread check dropped → T2.3 logs the join error; `543` validity check dropped → T2.4 state `FAILED`.
- [ ] **Step 4:** Verification block → **3255 passed**; each test 5×.
- [ ] **Step 5:** Commit `test: cover the scheduler error paths between and after tasks`.

### Task 4: Runtime pieces with small harnesses (T3)

**Files:**
- Test: `tests/test_runtime_request_builder.py`, `tests/test_runtime_completion_policies.py`, `tests/test_index_ledger.py`, `tests/test_runtime_composition.py`, `tests/test_lint_rewrites.py`

**Interfaces:**
- Consumes: `builder`/`recording_builder` fixtures; completion-policies `env` + `make_adapter` (built with an `IndexLedger`); index-ledger `env`/`make_ledger`, `InvalidIndexContext`; composition helpers; `GENERIC_CONTEXT`, `current_context()`.

- [ ] **Step 1: Write the tests (spec §5 T3.1–T3.5)**

```python
# request builder (2)
def test_cancel_during_build_stops_at_the_next_voice_change(...):   # returns False; resolver never called for "b"
def test_cancel_during_build_stops_at_the_next_pause(...):          # returns False; append_break never called
# completion policies (4)
def test_legacy_speak_with_a_cancelled_token_never_enters_the_core(...)   # core.speak not called; speak returns None
def test_legacy_speak_cancelled_during_entry_never_enters_the_core(...)   # token False then True; core not called
def test_legacy_core_error_propagates_unchanged(...)                      # raised is the same OSError instance
def test_segment_event_factory_must_be_callable(...)                      # TypeError; drain speech still refused
# index ledger (3)
@pytest.mark.parametrize("with_range", [False, True])
def test_bind_requires_a_correlated_contract(...)        # LEGACY_DONE → InvalidIndexContext
def test_a_non_int_wire_index_decodes_nothing(...)       # receiveIndex(src, True) == (); index 1 still decodes
# composition (4 + one assert line)
def test_default_voice_falls_back_to_the_first_voice(...)        # main voice is table[0]
#   extend the waitfactor test near line 447: assert manager.waitfactor == 4
def test_all_languages_lists_each_primary_language_once(...)     # == sorted primary languages
def test_cancel_after_terminate_does_nothing(...)                # no exception
def test_no_voice_instance_is_created_while_terminating(...)     # KeyError(engine); nothing cached
# lint rewrites (1)
def test_current_context_without_a_synth_is_generic(...)         # current_context() is GENERIC_CONTEXT
```

- [ ] **Step 2: Green:** the 14 new ids and the extended waitfactor test pass.
- [ ] **Step 3: Red on mutants:** `requestBuilder.py:38-39` / `45-46` → bare `flush()`; `engineAdapter.py:191-194` early return removed and 193 unconditional; `202-205` deleted; `209` unconditional; `113-114` deleted; `indexLedger.py:122-123` deleted; `199-200` deleted; `manager.py:212-213` fallback deleted; waitfactor getter `return 0`; `all_languages` → `[]`; `253` guard dropped; `128-129` deleted; `context.py:37-40` try/except deleted. Each → its test fails.
- [ ] **Step 4:** Verification block → **3268 passed**.
- [ ] **Step 5:** Commit per module group if the diff is large (request builder + adapter + ledger; composition + context), message `test: cover ...`.

### Task 5: Main driver shell (T4)

**Files:**
- Test: `tests/test_worldvoice_lifecycle.py`, `tests/test_worldvoice_pipeline_settings.py` (harness `tests/worldvoice_harness.py`)

**Interfaces:**
- Consumes: the harness's synth construction; `SynthDriver`, `PIPELINE_SETTINGS`, `_PipelineSetting`.

- [ ] **Step 1: Write the tests (spec §5 T4.1–T4.4)**

```python
def test_check_reports_the_driver_available(...):   # SynthDriver.check() is True
def test_a_second_terminate_does_nothing(...):      # event bridge close and task manager shutdown called once each
@pytest.mark.parametrize(("name", "value"), [("volume", ...), ("rate", ...), ("pitch", ...), ("inflection", ...), ("variant", ...), ("rateBoost", ...)])
def test_parameter_getters_read_the_main_voice(...):  # distinct value per parameter; getattr(synth, name) == value
def test_pipeline_settings_are_descriptors_on_the_class(...):  # getattr(SynthDriver, driver_id) is the _PipelineSetting; pipeline_settings.get not called
```

- [ ] **Step 2: Green:** 9 ids pass.
- [ ] **Step 3: Red on mutants:** `check` → `return False`; delete `sd/__init__.py:310-311`; each getter returning another parameter (one mutant per getter: e.g. `rate` getter reads `pitch`); delete `547-548`.
- [ ] **Step 4:** Verification block → **3277 passed**.
- [ ] **Step 5:** Commit `test: cover the main driver's check, terminate and getters`.

### Task 6: Global plugin presenter and detection panel (T5)

**Files:**
- Test: `tests/test_role_presenter.py`, `tests/test_unicode_panel.py`

**Interfaces:**
- Consumes: `env` / `load_presenter` of the presenter module (`setVariant`, `setParameter`, `keepParameters`, `discard`, `apply`, `speechSection`); `build(env, languages, stored)` of the panel module.

- [ ] **Step 1: Write the tests (spec §5 T5.1–T5.2)**

```python
def test_set_variant_previews_and_discard_restores(env)                      # variant changed, then restored
def test_a_parameter_without_consistency_changes_only_that_voice(env)        # main and other voices unchanged
def test_enabling_parameter_consistency_twice_keeps_the_first_snapshot(env)  # others back to pre-first-enable values
def test_apply_without_a_speech_section_still_saves(env)                     # apply returns; roles + flags saved; nothing mirrored
def test_stored_timing_not_offered_selects_the_first(env)                    # timing choice selection == 0
```

- [ ] **Step 2: Green:** 5 pass.
- [ ] **Step 3: Red on mutants:** `setVariant` no-op; `rolePresenter.py:81-82` preview unconditional; drop `and not self.keepParameters` at 96; delete try/except 143-146; delete `except ValueError` at `detection.py:59-60`.
- [ ] **Step 4:** Verification block → **3282 passed**.
- [ ] **Step 5:** Commit `test: cover the role presenter and detection timing fallbacks`.
- [ ] **Step 6: Batch 1 boundary.** Coverage run (`runpy.sh … --cov=addon --cov-branch --cov-report=term-missing`) + `covcmp.py impl/base-cov.txt <new>`; report commits, counts, coverage delta, Rulings to the orchestrator and STOP until told to continue.

### Task 7: VE and Cerence (T6)

**Files:**
- Test: `tests/test_vocalizer_segment_drain.py` (`env` runs VE and Cerence), `tests/test_vocalizer_init_cleanup.py` (T6.6), `tests/test_f4_engine_adapters.py` or `tests/test_vocalizer_segment_drain.py` (T6.12, whichever already loads the real VE/Cerence `Voice`), Cerence-only T6.13 next to T6.12.

**Interfaces:**
- Consumes: `env`, `speak`, `run_thread`, `finish`, `settle_segment`, `_ending_native`; native message constants (`VE_MSG_OUTBUFDONE`, `VE_MSG_ENDPROCESS`, `VE_MRK_BOOKMARK`, `NUAN_E_TTS_USERSTOP`, `NUAN_OK`); `load_real_driver_with_native_stubs`.

- [ ] **Step 1: Write the tests (spec §5 T6.1–T6.13; each runs for VE and Cerence unless noted)**

```python
@pytest.mark.parametrize("overflow", ["pcm", "markers"])
def test_output_beyond_the_allocated_buffers_fails_the_segment     # USERSTOP; no feed; segment fails with ValueError; next speaks
def test_marker_only_output_feeds_no_audio                         # index reported; no feed
def test_sonic_feeds_a_full_buffer_during_the_call                 # feed happens before ENDPROCESS is sent
def test_a_marker_list_reports_only_bookmarks_until_cancelled      # indexes == [5]; USERSTOP
def test_other_native_messages_do_not_end_the_call                 # NUAN_OK; segment fails as without ENDPROCESS
def test_nvda_2024_config_opens_the_player_on_the_speech_output_device  # WavePlayer got speech.outputDevice
def test_a_parameter_read_returns_the_queued_value                 # queued values, no native getParamList; other instance native
def test_a_pause_failure_refuses_the_running_calls_callbacks       # later callback USERSTOP, no feed; segment fails with pause error
def test_a_pause_failure_cleanup_stop_error_is_logged              # raises pause error; "WorldVoice pause failure cleanup failed"; terminate returns
def test_terminate_finishes_and_then_raises_a_cancel_error         # inner terminate ran; second terminate returns; raises cancel error
@pytest.mark.parametrize("failure", ["close", "cancel_and_close"])
def test_terminate_reports_its_first_cleanup_error                 # "WorldVoice VE|Cerence termination failed"; first error raised; second terminate returns
def test_metadata_without_a_language_description_uses_the_locale   # langDescription == locale; description "<id> - <locale> [VE]"
def test_cerence_variants_are_empty_without_speech_databases        # Cerence only: variants == []
```

- [ ] **Step 2: Green:** 29 ids pass.
- [ ] **Step 3: Red on mutants** (VE file; the Cerence copy at its bracketed line, spec §5 T6): delete 270-271; `if data.cntPcmBufLen:` → `if True:`; delete 278-280; delete 287-288; drop the `eMrkType` check at 289; `elif … ENDPROCESS` → `else`; delete the `except KeyError` at 413-414; skip queued tasks at 554-557; delete `call.admitting = False` at 797; delete the `except` at 806-807; delete the `except` at 844-845; make `if self._terminationError is None` at 884 unconditional; `langDescription = ""` at 942; Cerence 943-944 try/except removed. Mutate VE and Cerence separately; each mutant fails its engine's id.
- [ ] **Step 4:** Verification block → **3311 passed**; each concurrency test (T6.3–T6.11) 5×.
- [ ] **Step 5:** Commit (two commits if large: native callback paths T6.1–T6.5; lifecycle/config/metadata T6.6–T6.13).

### Task 8: SAPI5 (T7)

**Files:**
- Test: `tests/test_sapi5_segment_drain.py` (harness `tests/sapi5_drain_harness.py`)

**Interfaces:**
- Consumes: `env`, `speak`, `wait_event`, `TerminalEvents`, `latch_worker_stop_fault`; harness event enumerator and `useWasapi` switch; `driver._segmentHost.control_error`.

- [ ] **Step 1: Write the tests (spec §5 T7.1–T7.12)**

```python
def test_a_dead_worker_rejects_new_speech                          # failure event "SAPI5 playback worker is unavailable"; ordinary speak raises RuntimeError
def test_a_purge_failure_after_an_idle_failure_latches             # segment fails with idle error; control_error is purge error; next rejected
def test_a_stale_audio_stream_write_is_dropped                     # S_OK; pcbWritten[0] == 0; no feed
def test_notify_dispatches_start_and_bookmark_and_ignores_other_events  # speaking at start; index 7 once; other event no change
def test_start_stream_marks_speaking_only_for_the_current_stream   # current → speaking; old stream → not
def test_legacy_audio_speaks_in_the_caller_and_reports_bookmarks_at_once  # tts.Speak before speak returns; no worker record; index at Bookmark
def test_a_bookmark_outside_any_request_on_wasapi_is_ignored       # nothing reported
def test_a_cancelled_requests_bookmarks_are_ignored                # nothing reported
def test_an_ordinary_wasapi_bookmark_reports_through_nvda          # [7, 9] each once
def test_a_segment_bookmark_reports_once_and_drops_earlier_ones    # 8 reported; 7 dropped; repeated 8 / 42 nothing; EndStream reports 9 only
def test_a_purge_failure_while_cancelling_latches_a_control_fault  # control_error is purge error; next rejected; needsVoiceReload()
def test_a_stream_mismatch_fails_the_request                       # "SAPI5 callback stream did not match the admitted request"; next speaks
```

- [ ] **Step 2: Green:** 12 ids pass (a mutant pair split into two tests is a Ruling).
- [ ] **Step 3: Red on mutants** (spec §5 T7): try/except 103-106; inner try/except 152-156; delete 166-167 and 171-172 (two runs); drop START / BOOKMARK dispatch, `elif` → `else`; drop validity at 319, 321 true; delete 451-453, 328-329, 338-339; ignore `not driver.player` at 328/338; delete 331-332/341-342; delete 343-344; drop `index not in bookmarks` at 348, single pop at 350-352; try/except 582-585; delete 595-596.
- [ ] **Step 4:** Verification block → **3324 passed**; each test 5×.
- [ ] **Step 5:** Commit `test: cover the SAPI5 worker, bookmark and purge paths` (split by topic if large).

### Task 9: OneCore (T8)

**Files:**
- Test: `tests/test_onecore_segment_drain.py` (harness `tests/onecore_drain_harness.py`)

**Interfaces:**
- Consumes: `env`, `speak`, `finish`, `wait_events`, `queue_segment_behind_ordinary_speech`, `_leased_player_class`; `_OcSsmlConverter`, `_OcPreAPI5SsmlConverter`; `WAVE_HEADER_LENGTH`.

- [ ] **Step 1: Write the tests (spec §5 T8.1–T8.9)**

```python
def test_segment_conversion_without_prosody_options_uses_the_pre_api5_converter  # pre-API5 converter used, the other not
def test_cancel_before_any_audio_stops_nothing                     # no exception; control_error None; next speaks
def test_a_segment_without_a_player_drains_at_once                 # SEGMENT_DRAINED, no failure
def test_a_token_cancelled_queued_segment_is_abandoned_unopened    # no open / ocSpeech_speak for B; C speaks
def test_a_segment_cancelled_while_the_player_opens_is_never_spoken  # no ocSpeech_speak; next speaks
def test_a_callback_after_cancel_feeds_nothing                     # no feed, no index
@pytest.mark.parametrize("truncation", ["header_before_player", "payload"])
def test_truncated_wav_fails_the_segment_without_feeding           # ValueError failure; no feed; callback does not raise; next speaks
def test_cancel_during_a_paused_final_idle_publishes_no_done       # no synthDoneSpeaking
def test_a_callback_for_a_token_cancelled_segment_feeds_nothing    # _feedSegment False; no feed
```

- [ ] **Step 2: Green:** 10 ids pass.
- [ ] **Step 3: Red on mutants** (spec §5 T8): always `_OcSsmlConverter`; drop `if player:` at 183/188; at 194; delete 355-357; 392-393; drop `or self._earlyExitCB` at 448; delete 472-473; drop `if self._player:` at 498; drop condition at 522; delete 535-536.
- [ ] **Step 4:** Verification block → **3334 passed**; each concurrency test 5×.
- [ ] **Step 5:** Commit `test: cover the OneCore no-player, cancel and truncated-audio paths`.

### Task 10: RHVoice (T9)

**Files:**
- Test: `tests/test_rhvoice_segment_drain.py`

**Interfaces:**
- Consumes: `env`; the inner player fake; `driver._segmentHost.control_error`.

- [ ] **Step 1: Write the tests (spec §5 T9.1–T9.2)**

```python
@pytest.mark.parametrize("kind", ["ordinary", "segment"])
def test_a_final_idle_failure_fails_only_that_record    # fails with the idle error (ordinary: no DONE); next request speaks
def test_a_cancel_stop_failure_latches_and_raises       # cancel raises the stop error; control_error is it
```

- [ ] **Step 2: Green:** 3 ids pass.
- [ ] **Step 3: Red on mutants:** delete try/except `RHVoice/__init__.py:270-274` (record never retired: the next request's wait fails); delete `error = exc` at 460.
- [ ] **Step 4:** Verification block → **3337 passed**; each test 5×.
- [ ] **Step 5:** Commit `test: cover the RHVoice final idle and cancel stop failures`.

### Task 11: eSpeak (T10)

**Files:**
- Test: `tests/test_espeak_segment_drain.py` (harness `tests/espeak_drain_harness.py`)

**Interfaces:**
- Consumes: `env`; native `espeak_ng_Cancel`, `espeak_Synth`; `_espeak.isSpeaking`; `synthDoneSpeaking` recorder.

- [ ] **Step 1: Write the tests (spec §5 T10.1–T10.2)**

```python
def test_cancel_after_a_control_fault_skips_the_native_cancel   # returns EE_OK; native cancel not called
@pytest.mark.parametrize("failure", ["conversion", "synth"])
def test_a_failed_ordinary_utterance_clears_speaking_and_reports_done  # speak returns (conversion); isSpeaking False; one done; next spoken in full
```

- [ ] **Step 2: Green:** 3 ids pass.
- [ ] **Step 3: Red on mutants:** delete `Espeak/__init__.py:31-32`; delete `self._port.markNotSpeaking()` at 196; delete the `except` at 115-116.
- [ ] **Step 4:** Verification block → **3340 passed**; each test 5×.
- [ ] **Step 5:** Commit `test: cover the eSpeak fault cancel and failed utterance paths`.

### Task 12: Final verification (no code)

- [ ] **Step 1:** Full suite under the watchdog → **3340 passed, 0 skipped** (or the ledger's Ruling-adjusted count).
- [ ] **Step 2:** Coverage run (spec §2 command) under the watchdog; `covcmp.py impl/base-cov.txt <final>` → `COVERAGE GATE OK` (`discovery.py` loses 1 stmt/1 branch by Task 1); TOTAL vs spec §4's 98.67 %, each (a) module vs spec §2's "expected after"; every remaining (a) miss explained by a Ruling. A one-line change in an untouched module counts as noise only if two reruns agree.
- [ ] **Step 3:** `prek run --all-files` → all Passed; `git diff --check master` → empty.
- [ ] **Step 4:** `git diff --stat master -- addon` → only `discovery.py | 2 --`; protected paths (`git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py addon/synthDrivers/WorldVoice/unicodeScripts/unspaced_common_data.py`) and `git ls-files addon/synthDrivers/WorldVoice/driver/Neural` → empty.
- [ ] **Step 5:** Each new concurrency test file's new tests 5× (if not already done per task); report to the orchestrator (commits, counts, coverage, mutant table, Rulings, product bugs). Linux only: Windows NVDA, audio devices and engine SDKs are not exercised.
