# Phase 56: the remaining audit B items (B8, B12, B14)

Date: 2026-10-30.
Base: `master` `5548ea2`. Branch: `phase56-b-items`. Normal flow (DEVELOPMENT_WORKFLOW.md §3).
Source: the consistency audit `cons.md` (§1 B8, §3 B12, §5 A10 and B14, the summary table and its recommendations). Its line numbers are for `9d96ace`; every line below was re-located on `5548ea2`.

| Item | Decision | This phase |
|---|---|---|
| B8: RHVoice converts SSML inside host admission | Move the conversion to `_RHVoiceStrategy.prepare` (segments and ordinary speech) | Implemented (§1) |
| B12: three shapes share the `Port` name | Rename the four pure name lists by shape; keep `_EspeakPort` and `_RHVoiceInner` | Scripted rename with token-check proof (§2) |
| B14: bridge `apply()` re-sets an unchanged voice | Skip `core.voice = spec.id` when the same core already took this voice in its last fully successful apply, it still reports it, and the core does not ask for a reload | Implemented (§3) |
| B13: eSpeak ordinary DONE thread | Out of scope (won't do); the orchestrator records that in `cons.md` | — |

Line conventions: `RHVoice:292` is `addon/synthDrivers/WorldVoice/driver/RHVoice/__init__.py` line 292 (likewise `SAPI5:`, `OneCore:`, `VE:`, `Cerence:`, `Espeak:`); `inner-RHVoice:` is `driver/RHVoice/driver/__init__.py` (likewise `inner-VE:`, `inner-Cerence:`); `host:` is `runtime/segmentHost.py`; `lifecycle:` is `runtime/_segmentLifecycle.py`; `scheduler:` is `runtime/scheduler.py`; `session:` is `runtime/session.py`; `adapter:` is `bridge/engineAdapter.py`; all under `addon/synthDrivers/WorldVoice/`. NVDA paths are under `ref/nvda/`.

## 1. B8: RHVoice SSML conversion moves to `prepare`

### Problem

`_RHVoiceStrategy.submit` (`RHVoice:292-319`) builds `rhvoice.SsmlConverter(driver, driver.language)` and calls `convertToXml(commands)` (`RHVoice:300-301`). `SegmentHost.enqueue` calls `submit` under host admission (`host:274`, `:298`), so `cancel()` (`RHVoice:420-423`, `host.admission()`) and `terminate()` (`RHVoice:462`) wait for the conversion. The host already offers a hook for exactly this: `NativeStrategy.prepare` runs outside admission "so cancel() and terminate() never wait for it" (`host:96-107`, call and comment at `host:263-272`). OneCore converts there (`OneCore:154-171`); eSpeak, SAPI5 and VE cannot, because their parent's `speak()` converts and queues in one step (cons.md B8).

### Design (`driver/RHVoice/__init__.py`)

- Add `_RHVoiceStrategy.prepare(self, host, commands, operation)`: `driver = self._driver()`, then return `rhvoice.SsmlConverter(driver, driver.language).convertToXml(commands)`. It converts for **both** segments and ordinary speech: unlike OneCore, whose ordinary text arrives already converted by the parent's `speak()` (`OneCore:155-157`), RHVoice's `speak()` passes raw commands to `enqueue` (`RHVoice:417-418`).
- `submit(self, host, record, text)` receives the XML string; drop `RHVoice:300-301`. Everything else stays in `submit`, under admission: the `_segmentById` registration (`RHVoice:294-298`), the `_NativeLibrary`, the `SpeakText` task and its settings snapshot (`inner.profile`, `rate`, `pitch`, `volume`, `rateBoost`, `RHVoice:309-314`), the `ttsQueue.put`, and the `except` that pops `_segmentById` (`RHVoice:316-319`).
- The inner driver is not modified.

### Error semantics

| Conversion fails | Before (in `submit`) | After (in `prepare`) |
|---|---|---|
| Segment | `record_error` + `abandon` (`host:303-305`); `wait_native_boundary` sees the retired record's error and calls `lifecycle.fail` (`host:581-589`) | `self._lifecycle_of(operation).fail(operation, error)` before any record exists (`host:268-271`) |
| Ordinary | `forget(record)` and re-raise (`host:299-302`) | re-raised before any record exists (`host:268-270`) |

Outward outcome is the same: one `SEGMENT_FAILED` carrying the conversion error (the host already proves this for a raising `prepare`: `tests/test_segment_host.py::test_segment_prepare_error_fails_only_that_segment`, `:964-974`), or the exception raised to the ordinary caller (`::test_ordinary_prepare_error_is_raised`, `:977-982`). Nothing leaks: `prepare` runs before `new_record` (`host:273`), so there is no host record, no `_records[operation]` entry and no `_segmentById` entry (registration is in `submit`). `request_stop` finds no record and stops nothing (`host:567-579`), as it stopped nothing for the abandoned record before.

Two accepted ordering differences, the same OneCore already has:

- The conversion now runs before the terminated / control-error checks (`host:274-290`). Only when the conversion itself raises does the caller see the conversion error instead of "RHVoice driver has terminated" or the latched control error; both are failures.
- A cancel that lands while an ordinary `speak()` is still converting no longer waits for it, so that utterance is queued after the cancel returned. Today the same happens when the cancel lands between `speak()` and admission; the window only widens by the conversion time. The scheduler already covers a synchronous plain `speak` that outlives the first stop: it stops the playback again after `speak` returns when the token is cancelled (`scheduler:598-602`). In production RHVoice ordinary speech is not reached at all: the completion policy is built with `forceUnverifiedDrain=True` (`bridge/completionPolicies.py:31`; constructed without the argument at `__init__.py:252`), so RHVoice speaks segments only. A segment cancelled during conversion is discarded after `prepare` by `admit_producer` (`host:291-296`), as `test_cancel_does_not_wait_for_prepare` pins (`tests/test_segment_host.py:949-959`).

### Reading inner state outside admission: no new race

The converter reads `synth._SynthDriver__languages`, `__voice_languages`, `__profile` and, through `driver.language`, `_get_language` (`inner-RHVoice:431-456`, `:623-624`).

- `__languages` and `__voice_languages` are written only in the inner `__init__` (`inner-RHVoice:553-562`), before the wrapper can speak.
- `__profile` is written in `__init__` (`inner-RHVoice:563-573`) and in `_set_voice` (`inner-RHVoice:647-649`). The wrapper does not override `voice`; the only production writer is the bridge's `apply` (`adapter:142`), run from `EngineSession.activate` (`session:144-161`) on the scheduler worker (`scheduler:586`). Neither takes host admission, so today's conversion inside `submit` is already unsynchronised with a voice change; admission never ordered the two.
- Sequencing gives the real ordering: the worker activates, then speaks (`scheduler:586`, `:598`), and activates the next task only after this one completed or was cancelled (`scheduler:561`, `:606-620`). A conversion still running when a later `apply` changes `__profile` therefore belongs to a cancelled operation, whose result `admit_producer` discards (`host:291-296`). Ordinary `speak()` converts on the calling thread (the scheduler worker for the plain entry, `adapter:33-35`), strictly after `apply`.
- The `SpeakText` profile snapshot (`RHVoice:310`) stays in `submit`, so the profile the native call uses is still read under admission, exactly as today.

### What NVDA users hear or see

Nothing. The XML is identical (same converter, same inputs). `cancel()` and `terminate()` no longer wait for an SSML conversion in progress; the conversion of one segment is short, so this is not audible.

### Tests (`tests/test_rhvoice_segment_drain.py`; the harness loads the real inner driver over a stub `speechXml.SsmlConverter`, `tests/rhvoice_drain_harness.py:278-285`, `:316-320`)

- New `test_cancel_does_not_wait_for_a_segment_conversion` (red today): monkeypatch `env.inner.SsmlConverter.convertToXml` to set `entered` and block on `release`; speak a segment; after `entered`, `env.driver.cancel()` on another thread returns within `WAIT_TIMEOUT` while the conversion is held (today it blocks on `host.admission()`); after `release`, no native call is made, the segment publishes no `SEGMENT_DRAINED`, and `env.driver._segmentById == {}`.
- New `test_cancel_does_not_wait_for_an_ordinary_conversion` (red today): the same with `env.driver.speak(("legacy",))` on a thread. After `release`, `speak` returns and its utterance is queued (cancel happened before it existed; production's second stop is the scheduler's, `scheduler:599-601`); the test then cancels again and checks the worker settles.
- New `test_a_failing_segment_conversion_fails_the_segment_and_leaks_nothing` (characterization; green before and after): `convertToXml` raises `ValueError("conversion failed")` → `SEGMENT_FAILED` with that error, no native call, `env.driver._segmentById == {}`; a following segment drains.
- New `test_a_failing_ordinary_conversion_raises_and_leaks_nothing` (characterization): `env.driver.speak(...)` raises the `ValueError`; `_segmentById == {}`; a following ordinary utterance is spoken and notifies DONE (no stale pending record blocks FIFO retirement).
- Unchanged guards: `tests/test_segment_host.py::test_prepare_result_is_what_submit_receives` (`:938-946`), `::test_cancel_does_not_wait_for_prepare` (`:949-959`); `tests/test_rhvoice_segment_drain.py::test_legacy_speak_keeps_inner_settings_snapshot_and_queue` (`:432-446`, asserts `call.text == b"<speak>legacy</speak>"`).

Windows / NVDA: no dedicated item. Sanity only: RHVoice with mixed-language text (two RHVoice languages in one sentence) still switches profiles as before.

## 2. B12: rename the pure name-list `Port` classes by shape

### Problem

Three shapes share one name (cons.md §3 table):

- `_EspeakPort` (`Espeak:61`): name lists **and** the runtime adapter around NVDA's `_espeak` module (`install`, `runWhenDone`, `setIndexCallback`, `markNotSpeaking`, `stopPlayer`; used at `Espeak:112-139`, `:168`, `:196`).
- `_Sapi5Port` (`SAPI5:46-89`), `_OneCorePort` (`OneCore:31-65`): pure lists of NVDA parent names. Their only runtime use is feeding `Voice.ready()` (`SAPI5:703-708` `missing_host_names`; `OneCore:687-695` `host_names_ready`); otherwise the guard tests read them.
- `_VEPort` (`VE:58-86`), `_CerencePort` (`Cerence:58-86`): pure lists of vendored inner-driver privates (`INNER_PRIVATES`, `INNER_OVERRIDES`); their docstrings say "Not used at runtime; tests/test_native_strategy_guards.py pins these lists" (`VE:61-62`, `Cerence:61-62`). Confirmed: no reference outside the guard test.
- `_RHVoiceInner` (`RHVoice:25-104`): a runtime property accessor, already named differently.

### Design

Rename only the pure lists. Class bodies, docstrings and the constants inside (`NVDA_MODULE_NAMES`, `NVDA_PRIVATES`, `NVDA_OVERRIDES`, `INNER_PRIVATES`, `INNER_OVERRIDES`) are unchanged.

| Old | New | Why |
|---|---|---|
| `_Sapi5Port` | `_Sapi5HostNames` | NVDA (host) module and class names, the vocabulary of `runtime/hostNames.py:1-6` that `ready()` checks them with |
| `_OneCorePort` | `_OneCoreHostNames` | same; "Every listed name is NVDA's" (`OneCore:35`) |
| `_VEPort` | `_VEInnerNames` | vendored inner-driver privates (`VE:59`) |
| `_CerencePort` | `_CerenceInnerNames` | same (`Cerence:59`) |

Kept: `_EspeakPort` (it is a port), `_RHVoiceInner`. Kept in the test helper: `tests/nvda_releases.py`'s `EngineNames.port` field and `port_names()` (`tests/nvda_releases.py:107-160`); see open question 4.

References at HEAD (from `git grep -nw` over everything except `docs/superpowers/`; nothing in `docs/README.md`, `docs/history/`, comments or non-Python files):

- `driver/SAPI5/__init__.py:46`, `:706`, `:707` (×2 on `:707`).
- `driver/OneCore/__init__.py:31`, `:691`, `:692` (×2).
- `driver/VE/__init__.py:58`; `driver/Cerence/__init__.py:58`.
- `tests/nvda_releases.py:128` (`"_Sapi5Port"`), `:136` (`"_OneCorePort"`).
- `tests/test_native_strategy_guards.py:161-163` (`"_Sapi5Port"` ×3), `:298-300` (`"_OneCorePort"` ×3), `:359` (`port = f"_{engine}Port"`).
- `tests/test_vocalizer_drift.py:35` normalises Cerence text with `.replace("Cerence", "VE")`; `_CerenceInnerNames` becomes `_VEInnerNames`, so it still matches. The drift test compares definitions by name (`tests/test_vocalizer_drift.py:33-39`), so VE and Cerence must be renamed **in the same commit**.

Historical documents under `docs/superpowers/` (specs, plans, reviews) are not rewritten.

### Commits and proof (DEVELOPMENT_WORKFLOW.md §3.2 "改名與搬移的證明")

The rename is scripted from an explicit `OLD=NEW` list; one group per commit; each commit passes the full test suite:

1. `refactor: name the SAPI5 parent name list _Sapi5HostNames` — `_Sapi5Port=_Sapi5HostNames` in `driver/SAPI5/__init__.py`, `tests/nvda_releases.py`, `tests/test_native_strategy_guards.py`.
2. `refactor: name the OneCore parent name list _OneCoreHostNames` — `_OneCorePort=_OneCoreHostNames` in `driver/OneCore/__init__.py`, `tests/nvda_releases.py`, `tests/test_native_strategy_guards.py`.
3. `test: name the vocalizer inner name lists explicitly in the guard test` — **not a rename commit**: `test_vocalizer_inner_privates_are_listed_and_exist` (`tests/test_native_strategy_guards.py:356-359`) takes the class name from its parametrize, `("VE", "_VEPort"), ("Cerence", "_CerencePort")`, instead of building `f"_{engine}Port"`. The new names would be uniform (`f"_{engine}InnerNames"` would work), but that edit changes an f-string fragment (`Port`), not a whole name, so it would break commit 4's token check; spelled-out names also make the classes findable with `git grep`.
4. `refactor: name the vocalizer inner name lists _VEInnerNames and _CerenceInnerNames` — `_VEPort=_VEInnerNames`, `_CerencePort=_CerenceInnerNames` in `driver/VE/__init__.py`, `driver/Cerence/__init__.py`, `tests/test_native_strategy_guards.py`.

Order-sensitive token check, run on every rename commit (script in the scratchpad; command and output in the progress ledger; the final review re-runs it independently):

- The commit touches only the files listed for it (`git diff --name-only HEAD~1`).
- For each touched file, `tokenize` the parent and the commit versions. The two token streams have the same length; pairwise, the token type is equal and the text is equal, except tokens of type `NAME`, `STRING`, `COMMENT` or `FSTRING_MIDDLE` whose new text equals the old text with every `\bOLD\b` of this commit's list replaced by its `NEW`, and which contained at least one `OLD`.
- Afterwards `git grep -nw -e OLD -- . ':!docs/superpowers'` is empty for each `OLD` of the commit.
- Deliberately kept same-shaped tokens, checked unchanged: `_EspeakPort` (`Espeak:61`, `:131`, `:236-237`; `tests/nvda_releases.py:120`; `tests/test_native_strategy_guards.py:81`, `:99-113`; `tests/test_wrapper_init_cleanup.py:217`), `_RHVoiceInner`, the five constant names, `EngineNames.port`/`port_names`, the test names `test_*_only_through_its_port`. Protected paths unchanged: `git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/*'` is empty.

### What NVDA users hear or see

Nothing; no runtime behaviour changes (`ready()` reads the same frozensets under the new class names).

## 3. B14: bridge `apply()` stops re-setting an unchanged voice

### Problem

`VoiceClassAdapter.apply` always assigns `core.voice = spec.id`, then the supported settings in `APPLY_ORDER`, then `applyEngineSettings` (`adapter:140-147`, order at `adapter:26`). `EngineSession.activate` skips the whole apply only for the same source, key and revision (`session:144-161`). A voice key is `engine:voiceId` (`driver/__init__.py:13-14`), resolved to one spec and one settings state (`voices/manager.py:159-167`), and any changed setting bumps that state's revision (`runtime/voiceSettings.py:51-58`). So every setting change of a voice (rate, pitch, volume, rate boost, inflection, variant, wait factor) re-assigns the same voice on the next utterance.

For most engines that is cheap or already a no-op: VE's inner `_set_voice` returns for the same voice (`inner-VE:556-557`), Cerence's checks `voice != self.voice` (`inner-Cerence:539-541`), RHVoice's only stores the profile name (`inner-RHVoice:647-649`), OneCore's calls `ocSpeech_setVoice` (`ref/nvda/source/synthDrivers/oneCore.py:620-627`), eSpeak's queues `setVoiceAndVariant` (`ref/nvda/source/synthDrivers/espeak.py:327-340`).

For SAPI5 it is a full rebuild: NVDA's `_set_voice` always calls `_initTts` (`ref/nvda/source/synthDrivers/sapi5.py:759-773`), which creates a new COM voice object, stops the worker, closes the player and builds new audio and a new worker (`sapi5.py:730-757`). The wrapper's `_initTts` adds `_invalidateSegments`, `_releaseSink`, `host.reset()` and a new sink (`SAPI5:452-458`, `:460-476`, reset at `:482`). On NVDA before 2025.3 the core is NVDA's own `sapi5.SynthDriver` (`SAPI5:696-720`), with the same `_set_voice`. So each step of a SAPI5 rate change (for example from the synth settings ring, where NVDA then announces the new value) pays one rebuild.

Correction to cons.md A10/B14: "two SAPI5 voices alternating rebuild every segment" is not avoidable here: a different voice must be set, and NVDA's `_set_voice` always rebuilds. Two keys cannot share one voice either (one key = one voice id). The saving is limited to re-applying the **same** voice after a revision change.

### Why not just compare `core.voice` (cons.md's suggestion)

- SAPI5 `_initTts` can fail after `self.tts.Voice = voice` (`sapi5.py:731-737`) but before the player and worker are rebuilt (`sapi5.py:739-751`); the getter (`sapi5.py:649-650`, `tts.Voice.Id`) then reports the requested voice on a broken engine. `EngineSession.activate` already drops its cache after a failed apply for this reason (`session:156-158`).
- **The voice re-set is SAPI5's designed recovery.** A latched SAPI5 control fault (stop or purge failure: `SAPI5:133-135`, `:154-156`, `:235`, `:575`, `:626-634`, `:655-657`; an ordinary request failure even latches on purpose, "Require resource replacement", `SAPI5:626-632`) is cleared only by `host.reset()` (`host:311-329`), which only `_initTts` calls (`SAPI5:471-472`, `:482`). The tests pin this: `tests/test_sapi5_segment_drain.py::test_worker_stop_failure_latches_until_a_voice_reload` (`:1147-1159`) and `::test_voice_reload_replaces_faulted_playback_and_can_speak_again` (`:638-652`) both recover with `driver.voice = "voice"`, the **same** voice. In production the only `core.voice` writer is `apply` (`adapter:142`; `git grep` finds no other). Today, changing any setting of the faulted SAPI5 voice therefore revives it on the next utterance. A skip based only on the remembered voice and the getter would remove that path, leaving only "switch to another SAPI5 voice" or a WorldVoice reload: a user-visible regression in fault recovery. The design below keeps it (open question 1).

### Design

**Bridge (`bridge/engineAdapter.py`, `VoiceClassAdapter`):**

- New state `self._voiceApplied: tuple[object, str] | None` — the core and voice id of the last apply that fully succeeded. Cleared to `None` in `__init__`, in `close()` (`adapter:97-106`) and at the start of each apply (step 1). `open()` (`adapter:66-72`) does not touch it: it returns early when already open, and otherwise follows `__init__` or `close()`, so the memory is already `None`. It therefore never outlives the core it describes (a reopened adapter whose `createCore` returns the same object, as test harnesses do, still sets the voice).
- `apply(spec, snapshot)`:
  1. `core = self._core`; take the memory and clear it (`applied, self._voiceApplied = self._voiceApplied, None`), so a raising step leaves it cleared.
  2. Skip `core.voice = spec.id` only when **all** hold: `applied is not None`, `applied[0] is core`, `applied[1] == spec.id`; the core does not ask for a reload (below); and `core.voice == spec.id`. Evaluate in this order (cheap first; the getter may be a COM call). A raising getter or hook counts as "not unchanged": set the voice as today.
  3. Settings in `APPLY_ORDER` and `applyEngineSettings`, unchanged (`adapter:143-147`); they always run, so every setting still reaches the engine.
  4. Only after every step returned: `self._voiceApplied = (core, spec.id)`.
- Reload hook: optional, duck-typed like the bridge's other core lookups (`bridge/completionPolicies.py:63`, `:87`): `needsVoiceReload = getattr(core, "needsVoiceReload", None)`; when callable and it returns true, set the voice. Absent means no reload is needed. camelCase: it is an NVDA-layer entry defined by the bridge for driver wrappers (the snake_case `speak_segment`/`get_segment_drain_support` belong to the runtime's `SegmentDrainCore`, `host:125-149`).
- Concurrency: `apply` runs under `EngineSession`'s activation lock (`session:145`); `open`/`close` run only while the session is idle (`session:89-94`). No new lock.

**Runtime (`runtime/segmentHost.py`):** new read-only `SegmentHost.faulted -> bool`: true when a control error is latched or the current lifecycle has a fault (`lifecycle:175-178`) — exactly what `reset()` clears (`host:311-329`). NVDA-free; used by the SAPI5 wrapper.

**SAPI5 wrapper (`driver/SAPI5/__init__.py`, `SynthDriver`):** new `needsVoiceReload(self) -> bool`, true when re-setting the voice would replace something broken:

- `self._segmentHost.faulted`;
- `self.tts is None`;
- WASAPI audio (`self.useWasapi`) with `self.player is None`, `self._thread is None` or a dead `self._thread` (the condition `_checkWorker` raises on, `SAPI5:426-428`).

It reads only names already listed (`_thread` is in `NVDA_PRIVATES`, `SAPI5:75-88`; `tts`, `player`, `useWasapi` are public), so `ready()` and the guard tests need no list change. NVDA's own driver on NVDA < 2025.3 has no hook; it latches nothing (its worker logs and continues, `sapi5.py:854-867`), and a failed `_initTts` is still covered by the cleared memory.

**Other core replacements, checked:**

- The adapter's core changes only in `open()`/`close()` (`adapter:66-72`, `:97-106`); `close()` clears the memory, and `open()` runs only after `__init__` or `close()`, so a new core always starts with no memory; the identity check covers any future path. `EngineSession.open`/`close` invalidate the session cache too (`session:104-127`).
- SAPI5 `ready()` chooses the core class before any core exists (`SAPI5:696-720`, called at engine discovery); it never swaps an opened core.
- NVDA's `_set_useWasapi` reloads with `self.voice = self.voice` (`sapi5.py:775-779`), but WorldVoice never writes `useWasapi` on a core (it is only read: `bridge/completionPolicies.py:63`, `SAPI5:107`, `:415`, `:427`, `:441`, `:471`; it is not in `APPLY_ORDER`). Even if it happened, it reloads the same voice, so the memory stays true.
- An output-device change does not rely on the incidental rebuild: NVDA reloads its synth (WorldVoice, with every core) when the device changes (`ref/nvda/source/gui/settingsDialogs.py:3795-3800`).
- Neural (external plugin, `ref/Neural/Neural/driver/__init__.py:385-390`) only stores the voice; it neither subclasses `VoiceClassAdapter` nor calls `apply`. No other `VoiceClassAdapter` subclass exists (`git grep`; production constructs it once per engine, `voices/manager.py:94-95`).
- Getter forms: SAPI5 (`tts.Voice.Id`) and OneCore (`ocSpeech_getCurrentVoiceId`, `oneCore.py:617-618`) echo the id `voices()` lists (`sapi5.py:617-631`); eSpeak's getter returns the lowercased basename it stored (`espeak.py:317-325`, `:327-334`). Where a getter returns another spelling, the voice is simply set as today.

### Compatibility and error handling

- No configuration, data or UI change; no strings.
- Every engine still receives every setting on every non-cached activation; only the voice assignment is skipped, and only when the same core already took that voice in its last fully successful apply and is healthy.
- A failing voice setter, setting setter or `applyEngineSettings` raises from `apply` exactly as today; the memory stays cleared, so the next apply sets the voice again (and `EngineSession` re-applies, `session:156-160`).
- A raising getter or `needsVoiceReload` is not logged: it only selects today's behaviour (set the voice).

### What NVDA users hear or see

- SAPI5 (wrapper on NVDA ≥ 2025.3, and NVDA's own driver on older NVDA): after changing a setting of the current SAPI5 voice, the next utterance no longer waits for a COM voice / player / worker rebuild. Unmeasured on Windows; expected to be noticeable when stepping the rate with the synth settings ring.
- A faulted SAPI5 voice still recovers when one of its settings changes (as today), or when another SAPI5 voice is used.
- Other engines: no audible change.

### Tests

`tests/test_runtime_legacy_adapter.py` (recording `Core`, `tests/legacy_adapter_harness.py:4-23`):

- `test_reapplying_the_same_voice_skips_only_the_voice_setter`: apply `a` (revision 1), clear `core.writes`, apply `a` with `rate=72` → writes are the settings and the hook only, no `("voice", "a")`.
- `test_another_voice_is_set`: apply `a`, then `b`, then `a` → each writes its voice.
- `test_after_a_failed_apply_the_same_voice_is_set_again`: parametrized failing step (`voice` setter, `rate` setter, `applyEngineSettings`); the next apply of `a` writes `("voice", "a")` first.
- `test_a_raising_voice_getter_sets_the_voice`; `test_a_core_reporting_another_voice_gets_it_set` (the getter returns `"b"` after `a` was applied).
- `test_reopening_sets_the_voice_even_on_the_same_core_object`; `test_a_new_core_gets_the_voice_set` (`createCore` returns a fresh `Core` per open).
- `test_a_core_that_needs_a_voice_reload_gets_the_voice_set`: `needsVoiceReload` returning `True` → set; raising → set; `False` → skipped.
- Property test (Hypothesis): random sequences of {apply voice `a`/`b` with a new revision, make one step raise, make the getter raise or lie, set `needsVoiceReload`, close/open} against a model; invariant: an apply writes the voice unless the previous apply on the same open core fully succeeded with the same voice, the getter returns it and no reload is requested; every apply writes every supported setting.

`tests/test_f4_engine_session.py::test_revision_change_reapplies_same_voice` (`:86-92`): also assert no `("voice", "a")` among the writes after the revision change. `::test_reopen_reapplies_same_snapshot` (`:95-105`) keeps passing (memory reset on open).

`tests/test_segment_host.py`: `test_faulted_reports_a_control_error_or_lifecycle_fault_until_reset` — false initially; true after `latch_control_error`; false after `reset()`; true after a lifecycle fault; false after `reset()`.

`tests/test_sapi5_segment_drain.py`:

- `test_needs_voice_reload_reports_faults_and_missing_playback`: false when healthy; true after the `_stopThread` stop failure of `:1147-1153`; false after `driver.voice = "voice"`; true with WASAPI and no player or a dead worker.
- `test_the_bridge_rebuilds_sapi5_for_the_same_voice_only_when_it_needs_reload`: a `VoiceClassAdapter` over the harness driver; apply voice `voice` twice with different revisions → no new native voice (`len(env.natives)` unchanged), player not closed, the new rate applied; then latch the worker stop fault → the next same-voice apply rebuilds (`env.natives[-1]` is new), `control_error` is `None`, and a segment drains.

`tests/test_sapi5_old_nvda.py` (NVDA's own driver, `:200-243`): applying the same voice twice with a changed rate creates no second COM voice (`len(env.spVoices)` unchanged) and sets the new rate.

Mutation: `bridge/engineAdapter.py` is core decision logic; add it to `[tool.mutmut] source_paths` (`pyproject.toml:45-67`) and run mutmut on Linux; record the surviving mutants in `apply` (and why) in the review.

Windows / NVDA manual items (not verifiable on Linux):

1. NVDA ≥ 2025.3, WASAPI on, a SAPI5 voice as WorldVoice's main voice: step the rate up and down with the synth settings ring; each announced value starts without the pause of a rebuild, and the new rate is heard. Repeat for volume and pitch.
2. Two roles on two different SAPI5 voices in one sentence: both voices still speak, with their own settings.
3. NVDA 2025.1 or 2025.2 (NVDA's own SAPI5 driver): rate changes take effect on the next utterance.

## 4. Strings, readme, UI

No UI, configuration or string change, so no zh_TW translations. No readme or changelog entry (open question 6): B8 and B12 are not noticeable, and B14 only removes latency after a SAPI5 setting change.

## 5. Constraints

- Never modify `driver/*/driver/*` (RHVoice's `SsmlConverter`, VE/Cerence/RHVoice inner `_set_voice` stay as vendored), `driver/sonic/`, `unicodeScripts/script_data.py`, `unicodeScripts/unspaced_common_data.py`; no Neural.
- Engine drivers stay independently installable; no cross-driver imports. Shared logic only in `runtime/` (`SegmentHost.faulted`) and `bridge/` (`apply`); engine-specific behaviour in the wrapper (`needsVoiceReload`).
- RHVoice inner privates only through `_RHVoiceInner` (`tests/test_native_strategy_guards.py:224-237`); `SsmlConverter` is a public inner name.
- Rename, move and other changes in separate commits (§2); ruff pinned `0.16.3`; tabs.

## 6. Open questions

1. **B14 fault recovery (pushback on the simpler design).** Comparing only the remembered voice and the getter would stop a setting change from reviving a faulted SAPI5 voice (§3 "Why not"). Default: keep that recovery through `needsVoiceReload()` and `SegmentHost.faulted`. Alternative: drop the hook (simpler; a faulted SAPI5 voice then recovers only by switching SAPI5 voices or reloading WorldVoice). Decided by orchestrator with the recommended default; user may override before merge.
2. **B14 first apply after open.** The voice is set even when the constructor already chose `spec.id` (memory is empty), as today: one rebuild per open, and it guarantees the core's state matches the snapshot. Decided by orchestrator with the recommended default; user may override before merge.
3. **B12 vocalizer guard test.** Spell the class names in the parametrize (commit 3) rather than `f"_{engine}InnerNames"`. Decided by orchestrator with the recommended default; user may override before merge.
4. **B12 test helper vocabulary.** `tests/nvda_releases.py` keeps `EngineNames.port` and `port_names()` although two of the three entries now name `*HostNames` classes ("port" there means "the class listing the names"; eSpeak's is still a port). Renaming them would widen the rename for no reader of the add-on. Decided by orchestrator with the recommended default; user may override before merge.
5. **B8 ordering.** Accept that a conversion error can now surface instead of the terminated / control error, and the wider ordinary cancel window (§1); both match OneCore. Decided by orchestrator with the recommended default; user may override before merge.
6. **Readme.** No changelog line for B14's latency gain. Decided by orchestrator with the recommended default; user may override before merge.

## 7. Verification

- Linux: full `python3 -m pytest -q tests` (baseline 3698 passed, 0 skipped at `5548ea2`), `prek run --all-files`, `git diff --check`, the protected-path checks of DEVELOPMENT_WORKFLOW.md §7 (no output), mutmut on `bridge/engineAdapter.py`, and the §2 token check on each rename commit.
- Windows / NVDA: unverified on Linux; §3's manual items cover B14; B8 and B12 have none beyond the RHVoice sanity listen.
