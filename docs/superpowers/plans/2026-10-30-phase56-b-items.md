# Phase 56 (audit items B8, B12, B14) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> WorldVoice normal flow: one implementer runs every task in order; the
> orchestrator dispatches the final Fable 5.1 review (DEVELOPMENT_WORKFLOW.md §3.3).

**Goal:** RHVoice converts SSML outside host admission (B8); the four pure name-list classes are named by shape (B12); the bridge stops re-setting an unchanged, healthy voice after a setting change, so SAPI5 no longer rebuilds its COM voice, player and worker for each rate step (B14).

**Architecture:** B8 moves `SsmlConverter.convertToXml` from `_RHVoiceStrategy.submit` into the existing `NativeStrategy.prepare` hook. B12 is a scripted rename proven by an order-sensitive token check, one group per commit. B14 gives `VoiceClassAdapter` a memory of the last fully successful `(core, voice id)` apply and an optional duck-typed `core.needsVoiceReload()` hook; the runtime adds `SegmentHost.faulted`, and the SAPI5 wrapper answers the hook from it and its playback resources.

**Tech Stack:** Python 3 (NVDA add-on), pytest + Hypothesis, mutmut 3.8.0 (Linux), ruff 0.16.3 via prek 0.4.14.

**Spec:** `docs/superpowers/specs/2026-10-30-phase56-b-items-design.md` (commit `90bfad0`). The orchestrator accepted every "Decided by orchestrator" default of spec §6.

## Global Constraints

- Never modify `addon/synthDrivers/WorldVoice/driver/*/driver/*` (RHVoice's `SsmlConverter`, the VE/Cerence/RHVoice inner `_set_voice` stay as vendored), `driver/sonic/`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py`; never add Neural; `ref` is a git-ignored symlink, never staged.
- Engine drivers stay independently installable: no cross-driver imports. Shared logic only in `runtime/` (`SegmentHost.faulted`) and `bridge/` (`apply`); engine-specific behaviour in the wrapper (`needsVoiceReload`).
- `runtime/` is NVDA-free and snake_case; the NVDA layer (`bridge/`, wrappers) is camelCase (`tests/test_naming_layers.py`). Tabs; match surrounding comment density.
- RHVoice inner privates only through `_RHVoiceInner` (`tests/test_native_strategy_guards.py:224-237`); `SsmlConverter` is a public inner name.
- SAPI5's `needsVoiceReload` reads only names already in `_Sapi5HostNames` (`_thread`) or public (`tts`, `player`, `useWasapi`); no list change.
- Rename, move and other edits never share a commit. Renames come from an explicit `OLD=NEW` list run by a script; each rename commit passes the token check of Task 2.
- Historical documents under `docs/superpowers/` are not rewritten. No UI string, configuration, readme or changelog change.
- ruff pinned `==0.16.3`; prek hooks run on commit (re-stage and recommit if a hook rewrites files; never `--no-verify`); explicit `git add` paths and `git diff --cached --stat` before each commit; English `<type>: <summary>` + why-body; no `Co-Authored-By`; no push; no `git stash`; at most 3 pytest/mutmut workers, always under the MemAvailable ≥ 3 GB watchdog.

## Review Focus

1. **Cancel during an RHVoice segment conversion, then an immediate successor:** the cancelled segment's XML never reaches `RHVoice_speak`; the successor speaks its own text, exactly one native call — Task 1 `test_cancel_does_not_wait_for_a_segment_conversion` (successor part).
2. **Terminate while an RHVoice conversion is held** (NVDA switching synth mid-utterance): `terminate()` returns while the conversion is held; after release nothing is queued and no native call is made — Task 1 `test_terminate_does_not_wait_for_a_segment_conversion`.
3. **A variant-only (or wait-factor-only) change of the current voice:** the voice setter is skipped but `applyEngineSettings` still runs with the new variant — Task 4 `test_reapplying_the_same_voice_skips_only_the_voice_setter` (variant assertion).
4. **SAPI5 on legacy (non-WASAPI) audio, healthy:** `player` is `None` there by design, so `needsVoiceReload()` must be false, otherwise every rate step still rebuilds — Task 5 `test_needs_voice_reload_reports_faults_and_missing_playback` (legacy-audio assertion).
5. **`destroyCore` raising in `close()`, then reopening onto the same core object:** the memory is cleared anyway, so the reopened core gets its voice set — Task 4 `test_a_failed_close_still_forgets_the_voice`.

Baseline (worktree at `90bfad0`): **3698 passed, 0 skipped**; prek all Passed; protected paths clean.

Expected full-suite counts after each task (0 skipped throughout): Task 1 → 3703; Tasks 2–3 → 3703; Task 4 → 3704 (`faulted` commit) then 3718; Task 5 → 3726; Task 6 → 3726.

---

### Task 1: B8 — RHVoice converts SSML in `prepare`

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py:285-319` (`_RHVoiceStrategy`)
- Test: `tests/test_rhvoice_segment_drain.py`

**Interfaces:**
- Consumes: `NativeStrategy.prepare(self, host, commands, operation) -> SpeechCommands` (`runtime/segmentHost.py:96-107`); its result is what `submit` receives.
- Produces: `_RHVoiceStrategy.prepare(self, host, commands, operation) -> str` (the XML); `_RHVoiceStrategy.submit(self, host, record, text)` takes that string.

- [ ] **Step 1: Write the tests** in `tests/test_rhvoice_segment_drain.py`. Hold the conversion with `monkeypatch.setattr(env.inner.SsmlConverter, "convertToXml", held)` where `held` sets `entered`, waits `release.wait(HOLD_TIMEOUT)`, then calls the original; read the map with `tracked_segments(env.driver)` (import it from `rhvoice_drain_harness`).
  - `test_cancel_does_not_wait_for_a_segment_conversion`: `speak(env, text="held")`; after `entered.wait(WAIT_TIMEOUT)`, `env.driver.cancel()` on a thread finishes within `WAIT_TIMEOUT` while held (`assert done.wait(WAIT_TIMEOUT), "cancel() waited for the SSML conversion"`); then `release.set()`; `quiet_period` shows `env.native.calls == []` and the held segment's `events == []`; `tracked_segments(env.driver) == {}`. Successor (Review Focus 1): `env.native.scripts.append({"auto_return": True})`, `speak(env, segment=2, text="next")` → `wait_one().kind is SEGMENT_DRAINED`, `len(env.native.calls) == 1`, `env.native.calls[0].text == b"<speak>next</speak>"`.
  - `test_terminate_does_not_wait_for_a_segment_conversion` (Review Focus 2): same hold; `env.driver.terminate()` on a thread finishes within `WAIT_TIMEOUT`; after `release.set()`, `quiet_period` shows `env.native.calls == []`; `tracked_segments(env.driver) == {}`.
  - `test_cancel_does_not_wait_for_an_ordinary_conversion`: hold; `env.driver.speak(("legacy",))` on a thread; after `entered`, `cancel()` on another thread finishes within `WAIT_TIMEOUT`; `release.set()`; the `speak` thread finishes; the utterance was queued (`env.native.wait_call()` sees `b"<speak>legacy</speak>"`); then release the call (`call.return_release.set()`) and `env.driver.cancel()` again; `eventually(lambda: tracked_segments(env.driver) == {})`.
  - `test_a_failing_segment_conversion_fails_the_segment_and_leaks_nothing` (characterization): `convertToXml` raises `ValueError("conversion failed")` → `wait_one()` is `SEGMENT_FAILED` with `isinstance(event.error, ValueError)`; `env.native.calls == []`; `tracked_segments(env.driver) == {}`; undo the patch, `scripts.append({"auto_return": True})`, the next segment drains.
  - `test_a_failing_ordinary_conversion_raises_and_leaks_nothing` (characterization): `pytest.raises(ValueError, match="conversion failed")` around `env.driver.speak(("bad",))`; `tracked_segments(env.driver) == {}`; undo, `scripts.append({"auto_return": True})`, `env.driver.speak(("good",))` → `wait_call().returned.wait(WAIT_TIMEOUT)` and `eventually(lambda: env.dones == [env.driver])`.

- [ ] **Step 2: Run them, expect red for the three cancel/terminate tests**

Run: `python3 -m pytest -q tests/test_rhvoice_segment_drain.py -k "conversion"`
Expected: 3 failed (`cancel() waited for the SSML conversion` / the terminate equivalent: today `submit` converts under `host.admission()`), 2 passed (the characterization tests).

- [ ] **Step 3: Implement.** Add `_RHVoiceStrategy.prepare(self, host, commands, operation)`: `driver = self._driver()`; `return rhvoice.SsmlConverter(driver, driver.language).convertToXml(commands)` for segments and ordinary speech alike. Rename `submit`'s third parameter to `text` and drop the two converter lines (`RHVoice:300-301`); everything else in `submit` stays under admission. One short comment on `prepare` saying why it converts both kinds (RHVoice's `speak()` passes raw commands, `RHVoice:417-418`).

- [ ] **Step 4: Run green**

Run: `python3 -m pytest -q tests/test_rhvoice_segment_drain.py tests/test_segment_host.py tests/test_native_strategy_guards.py`
Expected: all pass (incl. `test_legacy_speak_keeps_inner_settings_snapshot_and_queue`, `test_prepare_result_is_what_submit_receives`, `test_cancel_does_not_wait_for_prepare`).
Full suite under the watchdog: **3703 passed, 0 skipped** (+5).

- [ ] **Step 5: Commit** `fix: convert RHVoice SSML before host admission` (paths: the wrapper and the test file).

### Task 2: B12 — rename the SAPI5 and OneCore host name lists

**Files:**
- Create (scratchpad, not committed): `.../scratchpad/phase56/rename.py`, `.../scratchpad/phase56/tokcheck.py`
- Modify: `addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py`, `addon/synthDrivers/WorldVoice/driver/OneCore/__init__.py`, `tests/nvda_releases.py`, `tests/test_native_strategy_guards.py`

**Interfaces:**
- Produces: classes `_Sapi5HostNames`, `_OneCoreHostNames` (bodies unchanged; Task 5 reads `_Sapi5HostNames.NVDA_PRIVATES` only through the existing guard tests).
- `rename.py OLD=NEW [OLD=NEW ...] -- FILE...`: `re.sub(rf"\b{OLD}\b", NEW)` per pair over each file, prints per-file replacement counts.
- `tokcheck.py --files FILE... OLD=NEW [...]`: (1) `git diff --name-only HEAD~1 HEAD` equals the given file set; (2) per file, `tokenize` `git show HEAD~1:f` and `git show HEAD:f`: same length; pairwise equal type; text equal, except tokens of type `NAME`/`STRING`/`COMMENT`/`FSTRING_MIDDLE` whose new text is the old text with every `\bOLD\b` replaced by `NEW` and which contained at least one `OLD`; prints the number of changed tokens per file; (3) `git grep -nw -e OLD -- . ':!docs/superpowers'` is empty for each OLD; (4) counts of the kept tokens `_EspeakPort`, `_RHVoiceInner`, `NVDA_MODULE_NAMES`, `NVDA_PRIVATES`, `NVDA_OVERRIDES`, `INNER_PRIVATES`, `INNER_OVERRIDES`, `port_names`, `port` (NAME tokens) are equal before and after in every touched file, and `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*'` is empty. Exit non-zero on any failure.

- [ ] **Step 1: Write both scripts; prove the checker catches a smuggled edit.** In a scratch `git clone --shared` of the worktree, rename `_Sapi5Port` and also change one unrelated token (e.g. a frozenset member); commit there; `tokcheck.py` must exit non-zero naming that token. Record in the ledger.
- [ ] **Step 2: SAPI5 rename.** `rename.py _Sapi5Port=_Sapi5HostNames -- <SAPI5 wrapper> tests/nvda_releases.py tests/test_native_strategy_guards.py`; expected counts 4 / 1 / 3. Full suite: **3703 passed, 0 skipped**. Commit `refactor: name the SAPI5 parent name list _Sapi5HostNames`; then `tokcheck.py` on HEAD → pass. Ledger: command + output.
- [ ] **Step 3: OneCore rename.** `_OneCorePort=_OneCoreHostNames` over the OneCore wrapper and the same two tests; expected counts 4 / 1 / 3. Full suite **3703 / 0**. Commit `refactor: name the OneCore parent name list _OneCoreHostNames`; `tokcheck.py` → pass; ledger.

(If a token check fails after committing, amend only that rename commit; never fold other edits in.)

### Task 3: B12 — vocalizer guard parametrize, then the VE and Cerence rename

**Files:**
- Modify: `tests/test_native_strategy_guards.py:356-359`; `addon/synthDrivers/WorldVoice/driver/VE/__init__.py:58`; `addon/synthDrivers/WorldVoice/driver/Cerence/__init__.py:58`

**Interfaces:**
- Consumes: `rename.py`, `tokcheck.py` (Task 2).
- Produces: `_VEInnerNames`, `_CerenceInnerNames`.

- [ ] **Step 1: Non-rename test edit.** `test_vocalizer_inner_privates_are_listed_and_exist` takes `("engine", "names")` from `@pytest.mark.parametrize(..., [("VE", "_VEPort"), ("Cerence", "_CerencePort")])` and uses `names` instead of building `f"_{engine}Port"`. Same 2 cases. Full suite **3703 / 0**. Commit `test: name the vocalizer inner name lists explicitly in the guard test`.
- [ ] **Step 2: VE + Cerence rename, one commit** (the drift test compares them by name). `rename.py _VEPort=_VEInnerNames _CerencePort=_CerenceInnerNames -- <VE wrapper> <Cerence wrapper> tests/test_native_strategy_guards.py`; expected counts 1 / 1 / 2. Full suite **3703 / 0** (incl. `tests/test_vocalizer_drift.py`). Commit `refactor: name the vocalizer inner name lists _VEInnerNames and _CerenceInnerNames`; `tokcheck.py` → pass; ledger.

### Task 4: B14 — `SegmentHost.faulted` and the bridge's voice memory

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/runtime/segmentHost.py` (after `control_error`, `:232-235`)
- Modify: `addon/synthDrivers/WorldVoice/bridge/engineAdapter.py:46-106`, `:139-147`
- Test: `tests/test_segment_host.py`, `tests/test_runtime_legacy_adapter.py`, `tests/test_f4_engine_session.py:86-92`

**Interfaces:**
- Produces: `SegmentHost.faulted -> bool` (property): `True` while a control error is latched or the current lifecycle's `fault` is set; reads `_control_error` under `_condition`, then `self._lifecycle.fault`.
- Produces: `VoiceClassAdapter._voiceApplied: tuple[object, str] | None`; `core.needsVoiceReload() -> bool`, an optional camelCase core hook the bridge defines (absent or non-callable = no reload needed).
- Produces: module function `_voiceIsCurrent(applied: tuple[object, str] | None, core, voiceId: str) -> bool` in `engineAdapter.py`: true only when `applied` is not None, `applied[0] is core`, `applied[1] == voiceId`, the hook (if callable) returns false, and `core.voice == voiceId`, evaluated in that order; any exception from the hook or getter → `False`.

- [ ] **Step 1: `faulted` test (red).** `test_faulted_reports_a_control_error_or_lifecycle_fault_until_reset` in `tests/test_segment_host.py`: `env.host.faulted is False`; `latch_control_error(OSError("stop failed"))` → `True`; `reset()` under `admission()` → `False`; lifecycle fault made as in `test_reset_recovers_from_a_lifecycle_fault` (`:581-599`) → `True`; `reset()` → `False`. Run: `python3 -m pytest -q tests/test_segment_host.py -k faulted` → FAIL `AttributeError: ... 'faulted'`.
- [ ] **Step 2: Implement `faulted`; green;** commit `feat: let a segment host report whether it is faulted` (full suite **3704 / 0**).
- [ ] **Step 3: Bridge tests (red)** in `tests/test_runtime_legacy_adapter.py`, over `legacy_adapter_harness.Core` (its `voice` getter is the stored attribute) and `VoiceState(spec, settings).snapshot()`:
  - `test_reapplying_the_same_voice_skips_only_the_voice_setter`: apply `a`; `core.writes.clear()`; apply `a` with `{"rate": 72, "variant": "bright"}` → `core.writes == [("rateBoost", False), ("rate", 72), ("pitch", 50), ("volume", 50), ("inflection", 50), ("hook", "bright")]` (Review Focus 3).
  - `test_another_voice_is_set`: `voices` lists `a` and `b`; applies `a`, `b`, `a` → `[w for w in core.writes if w[0] == "voice"] == [("voice", "a"), ("voice", "b"), ("voice", "a")]`.
  - `test_after_a_failed_apply_the_same_voice_is_set_again`, `@pytest.mark.parametrize("step", ["voice", "rate", "hook"])`: apply `a`; on a fresh adapter the first apply of `a` raises `RuntimeError` at that step (`voice`/`rate`: a `Core` subclass whose `__setattr__` stores the value, then raises once; `hook`: `applyEngineSettings` raises once), so the getter already reports `a`; `core.writes.clear()`; the next apply of `a` → `core.writes[0] == ("voice", "a")`.
  - `test_a_raising_voice_getter_sets_the_voice`; `test_a_core_reporting_another_voice_gets_it_set` (getter returns `"b"` after `a` was applied) → each writes `("voice", "a")` first.
  - `test_reopening_sets_the_voice_even_on_the_same_core_object`: apply, `close()`, `open()` (same `Core`), apply → `("voice", "a")` written.
  - `test_a_new_core_gets_the_voice_set`: `createCore` returns a fresh `Core` each open → the second core's first write is `("voice", "a")`.
  - `test_a_failed_close_still_forgets_the_voice` (Review Focus 5): `destroyCore` raises `OSError`; apply, `pytest.raises(OSError)` on `close()`, restore `destroyCore`, `open()` (same core), apply → `("voice", "a")` written.
  - `test_a_core_that_needs_a_voice_reload_gets_the_voice_set`, `@pytest.mark.parametrize("reload,written", [(True, True), ("raise", True), (False, False)])`: after a first apply, `core.needsVoiceReload` returns `True` / raises `RuntimeError` / returns `False` → `("voice", "a") in core.writes` is `written`.
  - `test_property_the_voice_is_set_unless_the_same_healthy_core_already_took_it` (Hypothesis `@given(st.lists(actions, max_size=12))`): actions are `("apply", voice ∈ {a, b}, fail ∈ {None, "voice", "rate", "hook"}, getter ∈ {"true", "raise", "lie"}, reload ∈ {None, False, True, "raise"})` and `("reopen",)`; each apply uses a new revision. Model: `remembered` = voice of the last apply on this open core that raised nothing, else `None`; reset by `reopen`. Invariant per apply: voice written ⇔ `not (remembered == voice and getter == "true" and reload in (None, False))`; when `fail is None`, every name of `APPLY_ORDER` and the hook are written.
  - `tests/test_f4_engine_session.py::test_revision_change_reapplies_same_voice`: also `assert ("voice", "a") not in engine.core.writes[before:]`.

  Run: `python3 -m pytest -q tests/test_runtime_legacy_adapter.py tests/test_f4_engine_session.py`
  Expected red: the skip tests (`..._skips_only_the_voice_setter`, `needs_a_voice_reload[False-False]`, the property test, `test_revision_change_reapplies_same_voice`); the rest pass today (characterizations of "set as today").
- [ ] **Step 4: Implement `apply` per spec §3:** `core = self._core`; `applied, self._voiceApplied = self._voiceApplied, None`; `if not _voiceIsCurrent(applied, core, spec.id): core.voice = spec.id`; settings and `applyEngineSettings` unchanged; finally `self._voiceApplied = (core, spec.id)`. Set `self._voiceApplied = None` in `__init__`, `open()` and `close()` (in `close()` before `destroyCore`, with the other resets). A short comment saying why the hook exists (SAPI5 recovers a fault by re-setting the voice).
- [ ] **Step 5: Green.** Same command → all pass; full suite **3718 passed, 0 skipped** (+14 adapter ids: 1+1+3+1+1+1+1+1+3+1). Commit `feat: skip re-setting an unchanged healthy voice in the bridge`.

### Task 5: B14 — SAPI5 `needsVoiceReload`

**Files:**
- Modify: `addon/synthDrivers/WorldVoice/driver/SAPI5/__init__.py` (`SynthDriver`, near `_checkWorker`, `:426-428`)
- Test: `tests/test_sapi5_segment_drain.py`, `tests/sapi5_drain_harness.py` (only if a named private view is needed), `tests/test_sapi5_old_nvda.py`

**Interfaces:**
- Consumes: `SegmentHost.faulted`, `VoiceClassAdapter.apply` skip (Task 4).
- Produces: `SynthDriver.needsVoiceReload(self) -> bool`: `self._segmentHost.faulted or self.tts is None or (self.useWasapi and (self.player is None or self._thread is None or not self._thread.is_alive()))`; read without `_threadCond`, like `get_segment_drain_support`.

- [ ] **Step 1: Tests (red).**
  - `test_needs_voice_reload_reports_faults_and_missing_playback`: healthy → `False`; `player.stop_error = True`, `pytest.raises(OSError)` on `env.driver._stopThread()`, clear the error → `True`; `env.driver.voice = "voice"` → `False`; `monkeypatch.setattr(env.driver, "player", None)` → `True`, undo; a dead worker (`_thread` replaced by an object whose `is_alive()` is `False`) → `True`, undo; legacy audio healthy (`useWasapi` false and `player` `None`) → `False` (Review Focus 4).
  - `test_the_bridge_rebuilds_sapi5_for_the_same_voice_only_when_it_needs_reload`: import `synthDrivers.WorldVoice.bridge.engineAdapter` after `load_sapi5` (as `tests/test_sapi5_old_nvda.py:172-181` does, dropping a cached copy first); a minimal voice class whose `createCore` returns `env.driver`, `supportedSettings` lists `voice`, `rate`, `pitch`, `volume`; `resolveVoice` returns an object with a no-op `applyEngineSettings`. Apply spec `voice` twice with revisions 1 and 2 and rates 50 then 70 → `len(env.natives)` unchanged after the second apply, `env.player.closed is False`, and `env.driver.rate == 70`. Then latch the worker-stop fault (`_stopThread` as above) → third apply (revision 3) → `env.natives[-1]` is a new object, `segment_host(env.driver).control_error is None`, and a segment on the new native drains (`native.wait_calls(1)`, `native.end()`, `wait_event(events).segment_id == 18`).
  - `tests/test_sapi5_old_nvda.py::test_old_nvda_sapi5_same_voice_reapply_keeps_the_com_voice`, parametrized over `OLD_RELEASES` (6): via `load_release`, open the adapter, apply `v1` at rate 70, then `v1` at rate 30 with revision 2 → `len(env.spVoices) == 1` and `env.spVoices[-1].Rate == core._percentToRate(30)`.

  Run: `python3 -m pytest -q tests/test_sapi5_segment_drain.py -k "needs_voice_reload or rebuilds_sapi5" tests/test_sapi5_old_nvda.py -k same_voice`
  Expected: `needs_voice_reload` FAIL (`AttributeError: needsVoiceReload`); `rebuilds_sapi5` FAIL at the third apply (no rebuild: the bridge skips because the hook is absent); the old-NVDA tests already PASS after Task 4 (characterization: NVDA's own core has no hook).
- [ ] **Step 2: Implement `needsVoiceReload`** with a docstring naming the bridge contract (re-setting the voice is SAPI5's fault recovery: `_initTts` → `host.reset()`).
- [ ] **Step 3: Green.** `python3 -m pytest -q tests/test_sapi5_segment_drain.py tests/test_sapi5_old_nvda.py tests/test_native_strategy_guards.py tests/test_naming_layers.py` → all pass. Full suite **3726 passed, 0 skipped** (+2 drain, +6 old NVDA). Commit `feat: ask the bridge to reload a faulted SAPI5 voice`.

### Task 6: Mutation testing and full verification

**Files:**
- Modify: `pyproject.toml` (`[tool.mutmut] source_paths`, `:45-67`: add `"addon/synthDrivers/WorldVoice/bridge/engineAdapter.py"` after `bridge/indexCodec.py`)

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Add the source path; commit** `test: run mutmut on the bridge engine adapter`.
- [ ] **Step 2: mutmut in a scratch copy** (`git clone --shared` of the branch into the scratchpad, `ref` symlinked, `source_paths` narrowed to `engineAdapter.py`, test selection `tests/test_runtime_legacy_adapter.py tests/test_f4_engine_session.py tests/test_sapi5_segment_drain.py tests/test_sapi5_old_nvda.py`): `guard.sh <copy> mutmut run --max-children 3 "*VoiceClassAdapter*apply*" "*_voiceIsCurrent*" "*VoiceClassAdapter*open*" "*VoiceClassAdapter*close*"`; `mutmut results`. Expected: every survivor explained in the ledger as equivalent or as a deliberate gap; a non-equivalent survivor in the new code gets a killing test (Ruling if not).
- [ ] **Step 3: Full verification (§7).** `python3 -m pytest -q tests` → **3726 passed, 0 skipped** (delta +28 vs 3698: 5 RHVoice, 1 host, 14 adapter, 2 SAPI5 drain, 6 old NVDA; recount from the ledger); `prek run --all-files` all Passed; `git diff --check master`; `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/unicodeScripts/script_data.py addon/synthDrivers/WorldVoice/unicodeScripts/unspaced_common_data.py` and `git ls-files addon/synthDrivers/WorldVoice/driver/Neural` both empty; re-run `tokcheck.py` against each rename commit (checkout-free: pass the commit to compare with its parent).
