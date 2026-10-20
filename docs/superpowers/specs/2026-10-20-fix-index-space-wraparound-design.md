# Fix: wire index space runs out and WorldVoice goes silent

Date: 2026-10-20.
Baseline: `master` `5e1137b` (`python3 -m pytest -q tests`: 1722 passed, 0 skipped, against `ref/nvda` `732d1ce2f`; `prek run --all-files`: all Passed). Branch: `fix/index-space-wraparound` (worktree `/workspace/WorldVoice-fix-index-space`).
Status: spec. Normal flow (section 3 of `DEVELOPMENT_WORKFLOW.md`); see section 12 for the flow choice. Open question Q1 (section 11) is assumed answered with its recommended option.

Line numbers refer to this branch's base (`5e1137b`) unless they say otherwise. NVDA references are to `ref/nvda` of the main checkout (`7d25bc76e`); every line cited from `source/speech/manager.py` is the same in `732d1ce2f`.

## 1. Problem

A real NVDA log on Windows: after some time of use, every speech task fails, repeatedly, and WorldVoice goes silent:

```
runtime/scheduler.py:495 _run_one -> :548 _execute -> runtime/session.py:185 speak
-> compat/engineAdapter.py:174 speak -> compat/indexCodec.py:25 encode_segment
-> indexLedger.py:119 prepare: raise IndexSpaceExhausted("Source wire index range is exhausted")
```

The user's installed build is slightly older than master. On master the same chain is `runtime/scheduler.py:493` → `:546` → `runtime/session.py:181` → `compat/engineAdapter.py:178` → `compat/indexCodec.py:25` → `indexLedger.py:121`.

Reproduced on master with the ledger alone: a DRAIN source bound with `IndexRange(1, 9999)` that prepares and retires one-index segments raises `IndexSpaceExhausted` on segment 10000, after 9999 wire indexes. `retire_source` + `unbind` + a fresh bind of the same source does not recover. Segments with no original index still prepare.

### 1.1 Mechanism (orchestrator's reading confirmed)

- `IndexLedger.prepare` hands out wire indexes from `_Source.next_index` and only ever adds to it (`indexLedger.py:118-133`). A segment uses `len(originals) + int(requires_end)` indexes (`:118-119`). For DRAIN `requires_end` is False (`runtime/completion.py:96-105`), so a DRAIN segment uses exactly one wire index per original `IndexCommand`, and none when it has no index (`indexLedger.py:119`).
- When `next_index + count - 1 > maximum` the call raises (`indexLedger.py:120-121`). Nothing ever lowers `next_index`. `retire_segment`, `retire_source` and `unbind` drop mappings but leave the cursor alone (`:199-223`).
- `_Source` state is keyed by `id(source)` and kept across unbind/rebind on purpose (`indexLedger.py:87-100`; `_Source.source` holds a strong reference so the id cannot be reused, `:49-50`). Only `close()` drops it (`:226-235`). The ledger is created once per WorldVoice synth driver instance (`addon/synthDrivers/WorldVoice/__init__.py:208-211`). So the cursor never goes back while WorldVoice stays the loaded synthesizer.
- `compat/completionPolicies.py:22` gives every DRAIN contract `IndexRange(1, 9999)`.
- So once one engine core has sent about 9999 original indexes, every later segment of that engine that contains an index raises. NVDA ends almost every utterance with an `IndexCommand` (`ref/nvda/source/speech/manager.py:318-321`) and adds one per callback command (`:330-336`). In practice every request fails. A WorldVoice request can be split into several segments. Leading segments with no index still prepare and speak, so a request may make a fragment of sound before the segment that carries NVDA's index fails.
- On failure the scheduler logs `"Speech scheduler task error"` with a traceback, marks the request FAILED, cancels its token so the remaining tasks are skipped, stops playback, retires the segment and still sends one `done_speaking` (`runtime/scheduler.py:489-503`, `:567-595`, `:373-384`). This happens again on every utterance: one traceback per utterance until NVDA restarts or the user switches synthesizer away from WorldVoice and back (that recreates the ledger, `__init__.py:208-211`).
- The counter belongs to each engine core (one `_Source` per notification source). An engine used heavily goes silent first, while other engines in the same session keep speaking until they reach their own limit.

### 1.2 Where 9999 comes from

It is not an engine limit that WorldVoice verified. It copies NVDA's own index range:

- `SpeechManager.MAX_INDEX = 9999` (`ref/nvda/source/speech/manager.py:200`). NVDA's generator counts 1..9999 and then **wraps back to 1** (`:202-219`). Its docstring explains the trade-off: no quick reuse (late indexes from cancelled speech), but no unbounded growth because "some synths might not be able to handle huge numbers"; 9999 is "small enough that any synth should be able to handle it and large enough that previous indexes won't reasonably get reused" (`:203-214`). NVDA compares wrapped indexes with half-range logic (`:513-532`).
- The WorldVoice correlated-drain spec took "the user-specified test wire range 1..9999 inclusive", and says the range limits wire bookmarks and does not certify any engine's native integer range (`docs/superpowers/specs/2026-09-28-worldvoice-correlated-drain-design.md:61`). It also expected the failure: "long use with ordinary indexes can still exhaust the range; on exhaustion the whole segment fails before it reaches the engine" (`:63`). The plan repeats "wire values in a live source are not reused" (`docs/superpowers/plans/2026-09-28-worldvoice-correlated-drain.md:19`) and tests exhaustion at 9999 (`:116`).
- The segment-index design made no-reuse a deliberate rule: allocation is monotonic and never wraps within one notification source's lifetime. Running out is an explicit error, there is no automatic rebuild, and "range capacity and long reading are part of the enablement acceptance; an adapter with too small a capacity cannot be formally enabled this way" (`docs/superpowers/specs/2026-09-27-worldvoice-segment-index-design.md:154-162`). The same section warns against assuming that engines accept arbitrarily large integers (`:156`).
- DRAIN later shipped to users through `force_unverified_drain=True` (`compat/completionPolicies.py:8-12`, `:31`, `:98-104`), without that long-reading acceptance. That is how the planned error became a field failure.

Because NVDA itself sends wrapped, reused 1..9999 indexes to every synth driver, the inner engine drivers already handle the same integer coming back. Reuse inside 1..9999 is the integer pattern these engines were built for. A wider range is not.

### 1.3 Affected engines

`CompletionPolicy` is created with the default `force_unverified_drain=True` (`__init__.py:231`, `compat/completionPolicies.py:31`). Every wrapper declares a `drain_profile` and answers `unverified_drain_support(...)` when its preconditions hold (`runtime/playbackWork.py:40-45`). Each one then gets `_DRAIN_CONTRACT` (`compat/completionPolicies.py:120-124`):

| Engine | Declaration | DRAIN (affected) when |
| --- | --- | --- |
| eSpeak | `driver/Espeak/__init__.py:210`, `:124-128` | always |
| RHVoice | `driver/RHVoice/__init__.py:431`, `:357-361` | always |
| OneCore | `driver/OneCore/__init__.py:631`, `:199-214` | native token, callback and bindings present (both audio modes) |
| SAPI5 | `driver/SAPI5/__init__.py:654`, `:372-382` | WASAPI only; legacy audio uses LEGACY_DONE and is not affected |
| VE | `driver/VE/__init__.py:956`, `:489-492` | cancellation guard installed |
| Cerence | `driver/Cerence/__init__.py:963`, `:491-494` | cancellation guard installed |

`_VERIFIED_CONTRACTS` is empty (`compat/completionPolicies.py:20`), so in production no engine uses END_INDEX or END_INDEX_AND_DRAIN. The ledger is generic, though, and the fix covers all three correlated modes.

## 2. Goals and non-goals

Goals:

- Speech keeps working however long WorldVoice is used. A correlated source never stops speaking because its wire index range has been used up.
- Keep the stale-callback protection as far as it can be kept. A wire index is never shared by two unretired segments, and a retired index is handed out again only after the allocator has gone round the whole range, as NVDA does.
- A segment that can never fit (more indexes than the range holds) is still spoken. Its index callbacks are reported when the segment completes, and it does not fail.
- The fix lives in core (`indexLedger.py`, `compat/indexCodec.py`). Wrappers and inner drivers do not change.

Non-goals:

- Changing the range 1..9999, or certifying engine integer ranges.
- Changing completion policy selection, `force_unverified_drain`, or any wrapper's drain support.
- General rate-limiting of the scheduler's per-task error log (`runtime/scheduler.py:501`). After this fix it no longer repeats for this cause (section 6.5).
- The main checkout's `ref/nvda` moved to `7d25bc76e` today. Against it the test stubs fail (9 failed / 112 errors, `cannot import name 'SequenceItemT' from 'speech.types'`). That is a separate test-stub issue and out of scope. This branch's tests run against `732d1ce2f`.
- No Neural code. No edits under `driver/<Engine>/driver/`.

## 3. What NVDA users hear or see

- Before: after about 9999 NVDA indexes sent through one DRAIN engine (hours of normal use, sooner in long say-all), that engine goes silent for the rest of the NVDA session. The NVDA log gets one error traceback per utterance.
- After: no audible change in normal use, and speech continues indefinitely. No new setting, dialog, focus change or spoken message.
- Only in the practically unreachable case of a single segment with more original indexes than the range holds (over 9998 in DRAIN with 1..9999), or a range left without a free run: the segment is spoken, and NVDA receives its indexes in order when the segment completes instead of while it plays. Caret or say-all position updates for that segment arrive at its end. NVDA already handles indexes that arrive late or skipped (`ref/nvda/source/speech/manager.py:670-683`). One warning per engine is written to the NVDA log (section 6.5).

No new or changed translatable strings, so no zh_TW translations are needed. The log message is not translated, like the other runtime log messages (for example `compat/completionPolicies.py:52-55`).

## 4. Affected layers

- `addon/synthDrivers/WorldVoice/indexLedger.py`: allocation (cyclic, with reservations and a degraded fallback), the module docstring, the once-per-source warning.
- `addon/synthDrivers/WorldVoice/compat/indexCodec.py`: leave out ordinary `IndexCommand`s from the wire when the allocation carries no ordinary wire indexes.
- No change to `runtime/scheduler.py`, `runtime/session.py`, `compat/engineAdapter.py`, `nvdaEventBridge.py`, `compat/completionPolicies.py`, or any `driver/*` file.
- Docs: a note in the earlier specs is not required. This spec records that it supersedes `2026-09-27-worldvoice-segment-index-design.md` §6.2 (no-wrap rule) and the exhaustion sentence of `2026-09-28-worldvoice-correlated-drain-design.md:63`.

## 5. How stale callbacks are rejected today (what reuse can and cannot weaken)

Late or stale engine callbacks have to pass several independent layers before they reach NVDA. Wire-index uniqueness is only the last of them:

1. **Wrapper callback admission.** Every DRAIN wrapper routes native callbacks through `SegmentHost.consumer`. It admits a callback only for the host's *current* valid record (`runtime/segmentHost.py:336-367`). Delayed player callbacks are bound to their own record (`:683-697`, `:326-334`), and eSpeak resolves the index callback through the record lease (`driver/Espeak/__init__.py:143-166`). A callback from a retired or cancelled native record is dropped before NVDA's `synthIndexReached` sees it.
2. **Binding generation.** The bridge decodes an INDEX with the binding token captured at bind time. A callback from before an unbind/rebind cannot decode against the new binding (`nvdaEventBridge.py:226-240`, `indexLedger.py:150-151`).
3. **Scheduler task and segment check.** A decoded batch is processed for the task that was current when the callback arrived. Each event must carry that task's `segment_id`, and the task must still be awaiting completion (`runtime/scheduler.py:301-339`, `:282-290`, `runtime/completion.py:43-46`).
4. **Context-bound completion.** DRAIN and FAILED events reach the ledger only through a sink that captured the segment's own `PlaybackContext` and binding (`nvdaEventBridge.py:142-178`; `indexLedger.py:167-197`). A stale *wire index* can never complete or fail a DRAIN segment.
5. **Wire index → segment map** in the ledger (`indexLedger.py:153-155`). This is the only layer that reuse affects.

So in DRAIN, the worst a mis-attributed stale ordinary index can do is make the *current* segment report some of its NVDA indexes early (the ledger replays earlier originals up to that position, `indexLedger.py:156-159`, `:238-245`). NVDA may then run callbacks or move the say-all position early (`ref/nvda/source/speech/manager.py:670-715`). In END_INDEX modes (not used in production, section 1.3) a stale terminal marker could also complete a segment early. That is the same class of risk NVDA accepts for its own wrapped indexes (`manager.py:202-219`). For it to happen, a callback has to slip past layers 1–3 *and* arrive after the allocator has gone round the full range back to that index.

Where `retire_segment`, `retire_source` and `unbind` are called:

- `retire_segment`: in `EngineAdapter.finish_segment` (`compat/engineAdapter.py:190-192`). The scheduler calls it for every task with a context, in `_settle`, success or failure (`runtime/scheduler.py:571-575`). The adapter calls it on its own cancel and error paths (`compat/engineAdapter.py:169-172`, `:180-188`), and the codec calls it on an encode failure (`compat/indexCodec.py:35-37`).
- `retire_source`: in `EngineAdapter.cancel`, *before* `core.cancel()` (`compat/engineAdapter.py:194-197`). So mappings are gone while the engine may still be delivering callbacks for the cancelled work. Those callbacks decode to nothing today, and with the new design they keep decoding to nothing until the cursor comes round again.
- `unbind`: from the bridge on unbind/close (`nvdaEventBridge.py:129-136`, `:196-203`), driven by `VoiceManager.terminate` (`voiceManager.py:145-149`).
- The scheduler has one worker thread (`runtime/scheduler.py:479-487`) and one current task, and it retires each segment before the next task runs. So in production **at most one segment per source is unretired at any time**.

## 6. Design

### 6.1 Cyclic allocation of contiguous runs

`prepare` keeps allocating one contiguous run `[start, start + count - 1]` per segment, in command order, with the terminal marker (when required) right after the ordinary indexes. Two things change: where `start` comes from, and what happens when no run fits.

- `next_index` becomes a **cyclic cursor** in `[minimum, maximum]`. After a full allocation, `next_index = start + count`, and if that passes `maximum` it becomes `minimum`. An empty allocation (`count == 0`, DRAIN with no index) leaves the cursor where it is, as today.
- **Search**, starting at the cursor and moving forward cyclically:
  - If the candidate run would pass `maximum`, skip the tail and continue from `minimum`. Runs never wrap across `maximum`, so they stay contiguous. The skipped tail stays free and is a candidate again on the next cycle.
  - If the candidate run overlaps a **reserved** run (section 6.2), continue just past the end of the overlapping reserved run.
  - The first candidate that fits wins. When every start position of one full cycle has been tried, no run fits.
  - If `count` is larger than the range (`maximum - minimum + 1`), no run fits, without searching.
- Sketch for the plan (the names are illustrative):

  ```python
  def _find_start(state, count):
      size = state.maximum - state.minimum + 1
      if count > size:
          return None
      start, scanned = state.next_index, 0
      while scanned < size:
          end = start + count - 1
          if end > state.maximum:  # never split a run across the maximum
              scanned += state.maximum - start + 1
              start = state.minimum
              continue
          blocker_end = max((last for first, last in reserved_spans(state) if first <= end and start <= last), default=None)
          if blocker_end is None:
              return start
          scanned += blocker_end - start + 1
          start = blocker_end + 1 if blocker_end < state.maximum else state.minimum
      return None
  ```

  Cost: in production at most one span is reserved per source, so this is O(count) work under the existing lock. The worst case is bounded by the range size plus the number of reserved spans.
- **Why contiguous runs instead of scattered free indexes.** `receive_index` turns a wire index into a position with `wire_index - allocation.wire_indexes[0] + 1` (`indexLedger.py:158`). `IndexAllocation` consumers zip the wire indexes in order with the segment's `IndexCommand`s (`compat/indexCodec.py:26-34`). Keeping runs contiguous leaves both unchanged and costs at most `count - 1` skipped indexes per wrap.
- **Reuse distance.** Under this scheme an index retired at some moment is handed out again only after the cursor has passed every other index of the range once. The only exceptions are indexes skipped at one wrap (fewer than the new segment's `count`) and indexes reserved by unretired segments. With at most one unretired segment in production and NVDA-sized segments (a few indexes), that leaves about 9990+ other wire indexes allocated before any reuse, the same order as NVDA's own `MAX_INDEX` cycle (`ref/nvda/source/speech/manager.py:200-219`).
- The cursor stays per `_Source` across unbind/rebind and `retire_source`, exactly as today. A rebind of the same core therefore does not reuse the indexes it just used (keeps `test_same_source_rebind_preserves_high_water`, `tests/test_index_ledger.py:76-85`).

### 6.2 Reservations

- A wire index is **reserved** from `prepare` until its segment is **retired**: it leaves `state.segments` through `retire_segment`, `retire_source`, `unbind` or `close`. It stays reserved after its mapping has been dropped from `state.indexes` on terminal, drain or failure (`indexLedger.py:164`, `:186-196`). A finished but unretired segment may still get late callbacks, and those must not land on a new owner.
- Each segment's reserved span is its whole contiguous allocation: ordinary indexes plus terminal marker. A degraded END segment reserves just its marker (section 6.4). An empty or degraded DRAIN segment reserves nothing.
- Invariant: **no wire index is in the reserved span of two unretired segments of the same source.** It follows that `state.indexes` maps each index to at most one segment, so `_remove_indexes` (`indexLedger.py:247-252`) can never pop another segment's mapping. No identity guard is added: through the public API it would be unreachable, and mutmut would report it as an equivalent mutant. The property test (section 8.3) checks the invariant directly.
- The plan may store the span on `_Segment` (for example `first`/`last`) or compute it from `allocation`. Either way it is derived from the allocation and does not need a second index table.

### 6.3 No extra time- or count-based quarantine

Decided by orchestrator with the recommended default; user may override before merge.

- Option considered: keep retired indexes in a FIFO quarantine for N allocations or T seconds before reuse. Rejected for three reasons:
  - Cyclic order already gives the largest quarantine the range allows, the full cycle (section 6.1).
  - An explicit quarantine either needs unbounded memory, or can itself fill the range and bring the original failure back.
  - Nothing documents how late an engine callback can arrive, so no T could be justified. Layers 1–4 of section 5 already reject stale callbacks without relying on wire integers.
- NVDA uses the same plain cycle (`ref/nvda/source/speech/manager.py:202-219`).

### 6.4 Segments that cannot get a full run: degraded allocation

Decided by orchestrator with the recommended default; user may override before merge.

When the full run (`count` indexes) cannot be found (section 6.1):

- **Degrade**: allocate only the terminal marker, `count = int(requires_end)`, with the same search. The ordinary wire indexes are left empty: `IndexAllocation(wire_indexes=(), end_index=<marker or None>)`. The segment still records its full `originals`.
  - DRAIN: the degraded allocation is `((), None)` and **always succeeds**, so DRAIN `prepare` never raises `IndexSpaceExhausted`.
  - END_INDEX / END_INDEX_AND_DRAIN: the degraded allocation needs one free, unreserved index for the marker.
- Completion already replays every undelivered original in order before the completion event:
  - terminal marker: `stop = len(segment.originals)` (`indexLedger.py:157-163`);
  - DRAIN: `_pending_indexes(..., len(segment.originals))` (`:190-197`).
  So NVDA gets all of the segment's indexes, in order and each once, when the segment completes. `SEGMENT_FAILED` still flushes nothing (`:186-189`), as today.
- The codec (`compat/indexCodec.py:25-34`) leaves the ordinary `IndexCommand`s out of the encoded commands when `allocation.wire_indexes` is empty and the input had originals. Every other command passes through as the same object, in order, and the marker is still appended when present. The `IndexAllocation` invariant becomes: `len(wire_indexes)` is either `len(originals)` or 0.
- Why degrade instead of failing:
  - A failure silences the request and logs a traceback.
  - Degrading keeps speech audible and gives NVDA every index. NVDA treats a late index as having reached all earlier ones (`ref/nvda/source/speech/manager.py:670-683`), so a burst at the end is a case it already handles.
  - This matches "prefer the conservative option that keeps speech audible".
- When degrading can happen:
  - In production only when one segment holds more originals than the range: over 9999 in DRAIN with 1..9999, or over `size - 1` in END modes.
  - Fragmentation of the range by unretired segments cannot happen with one unretired segment per source (section 5).

### 6.5 Remaining `IndexSpaceExhausted` and logging

- `IndexSpaceExhausted` stays (same class, same message, raised from `prepare` before anything is published). It now means: an END-mode segment cannot get even one free index for its marker, because every index of the range is reserved by unretired segments. Production cannot reach it (at most one unretired segment per source). If it ever happens, it fails only that request, through the existing scheduler path (`runtime/scheduler.py:489-503`), and stops on its own as soon as a segment retires. It cannot repeat on every utterance forever the way the current bug does.
- Degrading (section 6.4) logs **one `WARNING` per source** (per `_Source`, so per engine core for the ledger's lifetime), without a traceback, for example `"WorldVoice index range %d..%d cannot hold a %d-index speech segment; its indexes are reported when it completes"`. Later degradations of the same source log at `DEBUG`.
  - The ledger logs through a module logger (`logging.getLogger(__name__)`), like other core modules (`runtime/segmentHost.py:27`).
  - NVDA routes every root-logger record at WARNING or above into its log (`ref/nvda/source/logHandler.py:605-612`, `:673`).
  - Logging happens **after the ledger lock is released**: logging handlers are external code (the same rule as `close`, `indexLedger.py:233-235`).
  - A once-per-source flag on `_Source` keeps a pathological source from writing one warning per utterance.
- No scheduler or adapter change: the scheduler's generic error logging stays as it is for every other error.

### 6.6 Unchanged interfaces and compatibility

- Public ledger API is unchanged: `bind`, `prepare`, `receive_index`, `receive_segment_event`, `retire_segment`, `retire_source`, `unbind`, `close`, `IndexAllocation(wire_indexes, end_index)`, `IndexSpaceExhausted`, `InvalidIndexContext`. The bridge, adapter and scheduler need no change.
- No settings, config schema or stored data change. No migration.
- The `CompletionContract` / `IndexRange` model is unchanged (`runtime/models.py:61-83`).
- The module docstring changes from "source-local, never-reused wire indexes" (`indexLedger.py:1`) to describe cyclic reuse with reservations. The test module docstring changes too (`tests/test_index_ledger.py:1`).

## 7. Settings, dialogs, strings

None. No panel or dialog change, no new translatable string.

## 8. Test plan

Tests run with the alias loaders the existing suites use (`tests/test_index_ledger.py:16-41`, `tests/test_index_codec.py:11-29`). Each new behaviour gets a test that fails on master first (red), then the fix.

### 8.1 Unit tests (red on master)

`tests/test_index_ledger.py`:

- `test_drain_source_keeps_allocating_after_the_range_is_used` uses the production range 1..9999. Prepare and retire 3 × 9999 one-index segments. Every `prepare` succeeds, and each segment's index decodes to that segment. Red on master at segment 10000.
- Wrap order on a small END_INDEX range (for example 501..510): after retiring, the next allocation wraps to `minimum` only when the cursor passes `maximum`. A run that would cross `maximum` starts at `minimum`, and the skipped tail is used on the next cycle.
- Reservation: an unretired segment's span (including a drained or ended but unretired segment, and an AND segment whose terminal is still mapped) is skipped. The allocation after it is the first free run past it.
- Stale index after a wrap: a retired index decodes to `()` until it is handed out again, and then decodes only to its new owner.
- `retire_source` / `unbind` + rebind keep the cyclic cursor: the next allocation continues after the last used index and does not restart at `minimum`.
- Degraded DRAIN: a segment with more originals than the range gets `((), None)`. Drain replays all originals in order, then `SEGMENT_DRAINED`. `SEGMENT_FAILED` replays nothing. Wire indexes stay unreserved, and the cursor does not move.
- Degraded END_INDEX: only the marker is allocated, and the terminal replays all originals then `SEGMENT_END`.
- `IndexSpaceExhausted` only when an END-mode marker has no free index (every index reserved). It stays atomic: nothing is published, and the cursor and reservations are unchanged.
- One WARNING per source on degrade (`caplog`), DEBUG afterwards, logged with the lock released. The test logs from a handler that calls back into the ledger, or checks `ledger._lock.locked()` inside a handler.

`tests/test_index_codec.py`:

- Degraded encode: ordinary `IndexCommand`s are left out, every other command is kept as the same object and in order, the input is not mutated, and the marker is appended in END modes. Completion then reports every original once, in order.

Integration (`tests/runtime_drain_integration_harness.py`, `tests/test_runtime_drain_integration.py`):

- Add an `index_range` option to `assemble` (default `IndexRange(1, 9999)`, `runtime_drain_integration_harness.py:363-367`). Submit more one-index requests than a small range holds (for example `IndexRange(1, 3)`, 8 requests) for each of OneCore, VE and Cerence (`ENGINES`, `:20`). Every request speaks, `output.indexes` gets every original, and no task fails. Red on master from the fourth request.

### 8.2 Existing tests whose expectations change

These tests encoded the old "exhaustion fails the segment" behaviour:

- `test_exhaustion_is_atomic` (`tests/test_index_ledger.py:133-150`): a full run no longer fits, so the segment degrades to marker-only. Rewrite it to cover degrading and to keep a separate atomic-raise case (all indexes reserved).
- `test_drain_uses_both_range_endpoints_and_empty_works_after_exhaustion` (`:490-508`) and `test_drain_exhaustion_does_not_partially_publish_or_consume_indexes` (`:511-526`): keep the endpoint and no-partial-publish checks, and expect the degraded allocation instead of a raise.
- `test_drain_codec_rejects_exhausted_segment_before_output` (`tests/test_index_codec.py:165-174`): becomes a degraded-encode test.
- `test_errors_before_core_entry_never_speak[exhaustion]` (`tests/test_runtime_adapter_contract.py:282-307`): 16 originals in `IndexRange(501, 516)` under END_INDEX now degrade and speak. Change this parameter into a test where the segment speaks and its indexes are delivered at the terminal. Keep the `generator` and `invalid_index` cases as they are.

All other ledger tests, including `test_retired_segment_cannot_complete_new_segment`, `test_same_source_rebind_preserves_high_water`, `test_retire_source_drops_all_segments_but_preserves_binding_and_high_water` and `test_concurrent_preparations_allocate_disjoint_complete_segments`, keep their current assertions.

### 8.3 Property tests (Hypothesis)

Existing Hypothesis use: `tests/test_index_codec.py:7`, `:176-235`; profiles in `tests/conftest.py:18-27` (`default` 200 examples, `deep` 20000, `mutmut` derandomized).

- New `RuleBasedStateMachine` (or `st.data()`-driven sequence) in `tests/test_index_ledger.py`:
  - Inputs: a random mode (END_INDEX, END_INDEX_AND_DRAIN, DRAIN) and a small random range (size 1..12).
  - Rules: `prepare` (random originals length 0..size+2), `receive_index` (any wire index in range, plus out-of-range), drain or fail event, `retire_segment`, `retire_source`, unbind+rebind of the same source.
  - Checks against a small model of reservations:
    1. Every allocation is inside `[minimum, maximum]` and contiguous. When present, `end_index == wire_indexes[-1] + 1`, or `end_index` is the whole span when degraded.
    2. No wire index is in two unretired segments' spans.
    3. A full allocation is returned whenever a free contiguous run of `count` exists, and its start is the first such start in cyclic order from the cursor. Otherwise the result is degraded if the marker fits, otherwise `IndexSpaceExhausted` with nothing changed. DRAIN never raises.
    4. Decoding a wire index yields events only for the unretired segment whose span holds it.
    5. Each segment reports its originals once each, in order, and the terminal or drain reports the rest (reusing the oracle of `tests/test_index_codec.py:221-235`).
    6. Liveness: if every prepared segment is retired before the next one, `prepare` never fails for any number of segments whose count fits the range.
- Extend the codec property test (`tests/test_index_codec.py:178-188`) so layouts can hold more indexes than the range. The degraded path then checks that the encoded output keeps every non-index command and that every original is still reported once, in order.

### 8.4 Mutation testing (mutmut)

- `indexLedger.py` is already a mutmut target (`pyproject.toml:35-49`, commit `0c81f41`). Run `mutmut run --max-children 3` on Linux, with the memory guard (stop when MemAvailable < 3 GB).
- Record the surviving mutants and why in this spec's implementation notes. Expected survivors: message-string mutants of the new warning, and equivalent ones. As in phase 29 (`docs/superpowers/specs/2026-10-07-phase29-property-and-mutation-design.md:28`, `:60`), confirm each survivor by running the suite with that mutant applied.
- Optional: add `compat/indexCodec.py` to `source_paths`. Its degraded branch is a core decision too. Decided by orchestrator with the recommended default (add it); user may override before merge.

### 8.5 Windows / NVDA manual items

These are not covered on Linux. The Linux tests reach only the controlled native and audio boundaries.

- For each DRAIN engine (eSpeak, RHVoice, OneCore, SAPI5 with WASAPI, VE, Cerence) on its own, run say-all on a long document until well over 10000 NVDA indexes have passed (for example, enable speech-manager debug logging, or read at least 2 hours / 15000 lines). Speech never stops, the log has no `IndexSpaceExhausted` and no "Speech scheduler task error", and the say-all caret keeps following speech across the wrap.
- Across the wrap: press Ctrl to interrupt say-all repeatedly and arrow through text quickly. No early cursor jumps, and no skipped or repeated phrases compared with before the wrap.
- Mixed-language text that switches engines (for example VE ↔ OneCore): every engine keeps speaking after its own counter wraps.
- SAPI5 with legacy audio (LEGACY_DONE): unchanged behaviour.
- Check the NVDA log once: the degraded warning does not appear in normal use.

## 9. Verification

Before each commit, before merge and after merge (`DEVELOPMENT_WORKFLOW.md` §7):

- `python3 -m pytest -q tests`: compare passed/skipped with the 1722/0 baseline. The count grows only by the new tests, and skips come only from missing optional components.
- `prek run --all-files`: all hooks Passed (ruff `0.16.3`).
- `git diff --check`.
- Protected paths: both commands print nothing.

  ```bash
  git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py
  git ls-files addon/synthDrivers/WorldVoice/driver/Neural
  ```

- mutmut on `indexLedger.py` (section 8.4), with results recorded.
- Report clearly that Windows NVDA, real audio devices and engine SDKs were not verified on Linux.

## 10. Decisions taken by default

Each of these is marked: Decided by orchestrator with the recommended default; user may override before merge.

1. Keep `IndexRange(1, 9999)`. Do not widen it: NVDA picked 9999 so every synth can handle it (`ref/nvda/source/speech/manager.py:209-214`), and the segment-index design forbids assuming larger integers (`2026-09-27-worldvoice-segment-index-design.md:156`).
2. Cyclic cursor with contiguous runs that never cross `maximum` (section 6.1).
3. Reservation lasts until retire, not until decode removal (section 6.2).
4. No explicit time- or count-based quarantine; the full cycle is the quarantine (section 6.3).
5. Degrade instead of failing when no full run fits. DRAIN never raises, and END modes raise only when no marker index is free (section 6.4).
6. One WARNING per source on degrade, then DEBUG, logged outside the lock (section 6.5).
7. Add `compat/indexCodec.py` to mutmut `source_paths` (section 8.4).

## 11. Open questions needing the user

**Q1. Reversing the "never reuse a wire index" rule.** The segment-index design deliberately chose monotonic, never-wrapping allocation. It accepted the exhaustion error and made long-reading capacity an acceptance gate (`docs/superpowers/specs/2026-09-27-worldvoice-segment-index-design.md:154-162`). DRAIN then shipped through `force_unverified_drain` without that gate, and this bug is the result. Options:

- **A. Cyclic reuse with reservations (sections 6.1–6.4). Recommended.** Speech keeps working indefinitely. It gives the same protection NVDA gives its own indexes, on top of the wrapper, binding, scheduler and context-bound completion layers. It needs no engine changes.
- B. Keep the no-reuse rule and widen the range (for example to 2³¹−1). That still runs out eventually in theory, and it needs per-engine proof that large integers survive SAPI5 bookmarks, OneCore SSML marks, VE/Cerence markers, eSpeak and RHVoice. The earlier spec forbids assuming it.
- C. Keep the no-reuse rule and turn off forced DRAIN (`force_unverified_drain=False`), so every engine goes back to LEGACY_DONE. That is a large user-visible change: it removes correlated completion for all six engines, including waiting for the playback drain before the next segment starts.

This spec is written with **A** assumed. It changes no user-visible behaviour apart from fixing the silence, so implementation need not wait for the answer.

## 12. Flow classification

Normal flow (`DEVELOPMENT_WORKFLOW.md` §1, §3). The complex-flow criteria (§4.0) do not apply:

- The plan and the implementation are done by the same agent (§3.2).
- No byte-exact restoration, and no packaging or build change.
- No large mechanical edit: two core modules plus their tests.
