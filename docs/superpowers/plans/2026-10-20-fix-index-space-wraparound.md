# Plan: wire index space wraparound fix

Spec: `docs/superpowers/specs/2026-10-20-fix-index-space-wraparound-design.md` (commit `b1d718a`), option A of Q1 assumed.
Branch `fix/index-space-wraparound`, worktree `/workspace/WorldVoice-fix-index-space`, base `5e1137b`.
Baseline: `python3 -m pytest -q tests` 1722 passed, 0 skipped (against `ref/nvda` `732d1ce2f`, through the worktree's git-ignored `ref` symlink); `prek run --all-files` all Passed.

Each step: write the tests first and run them on the unchanged code (red), then change the code (green), then run the full verification of `DEVELOPMENT_WORKFLOW.md` §7 and commit. pytest runs single-process.

Full verification before every commit:

```bash
python3 -m pytest -q tests
prek run --all-files
git diff --check
git diff --stat master -- 'addon/synthDrivers/WorldVoice/driver/*/driver/' addon/synthDrivers/WorldVoice/driver/sonic/ addon/synthDrivers/WorldVoice/languageDetection/script_data.py
git ls-files addon/synthDrivers/WorldVoice/driver/Neural
```

The last two print nothing.

## Step 1. Cyclic allocation with reservations (commit `fix: reuse wire indexes cyclically ...`)

### 1a. Red tests

File: `tests/test_index_ledger.py`

Edit: module docstring.

```python
"""Source-scoped wire indexes are reused only cyclically and never complete the wrong segment."""
```

Edit: add a `make_ledger` fixture after `env` that binds fresh ledgers with a given mode and range and closes them at teardown, plus the tests below (placed after `test_exhaustion_is_atomic`, and the DRAIN ones after the drain block).

```python
@pytest.fixture
def make_ledger(env):
	ledgers = []

	def make(mode, minimum, maximum):
		ledger = env.module.IndexLedger()
		ledgers.append(ledger)
		source, source_id = object(), object()
		contract = env.models.CompletionContract(
			getattr(env.models.CompletionMode, mode),
			env.models.IndexRange(minimum, maximum),
		)
		token = ledger.bind(source, source_id, contract)
		return SimpleNamespace(
			ledger=ledger, source=source, source_id=source_id, contract=contract, token=token,
			module=env.module, models=env.models,
		)

	yield make
	for ledger in ledgers:
		ledger.close()


def use(s, source_id, segment_id, originals):
	"""Prepare and retire one segment; return its allocation as plain tuples."""


def test_runs_wrap_to_the_minimum_without_crossing_the_maximum(make_ledger):
	# 501..510 END_INDEX: (1,2,3) -> 501..504; (4,5,6,7) -> 505..509; (8,) needs two and only 510
	# is left before the maximum -> 501, 502; six originals -> 503..509; () -> 510 (the skipped
	# tail, on the next cycle); () -> 501.


def test_rebinding_a_source_continues_its_cycle(make_ledger):
	# retire_source + unbind + bind under a new source ID keeps the cursor: 501..504, then 505/506,
	# 507..510, and after another rebind the run wraps to 501/502 (raised before the fix).


@pytest.mark.parametrize("mode", ["END_INDEX", "END_INDEX_AND_DRAIN", "DRAIN"])
def test_a_finished_segment_keeps_its_indexes_until_it_is_retired(make_ledger, mode):
	# Range 1..10. Segment 1 (42,) takes 1..2 (1 in DRAIN) and finishes: END by its marker,
	# AND and DRAIN by a drain (AND keeps its marker mapped). A filler takes the rest and is
	# retired, so the cursor wraps to 1. Segment 3 (7,) skips the finished but unretired span and
	# gets the first free run after it. Wire 1 decodes to nothing; in AND wire 2 still ends
	# segment 1 only.


def test_a_retired_index_decodes_to_nothing_until_it_is_handed_out_again(make_ledger):
	# DRAIN 1..3: three one-index segments are prepared and retired; wires 1..3 decode to nothing;
	# segment 4 gets wire 1 again and wire 1 then decodes to segment 4 only.


def test_drain_source_keeps_allocating_after_the_range_is_used(make_ledger):
	# The production DRAIN range 1..9999; 3 x 9999 one-index segments, each prepared, decoded and
	# retired. Segment n gets wire (n - 1) % 9999 + 1 and decodes to segment n. Before the fix,
	# segment 10000 raised IndexSpaceExhausted.
```

The test bodies are in the commit; each comment above states its exact assertions.

File: `tests/runtime_drain_integration_harness.py`

Edit: `def assemble(monkeypatch, tmp_path, *, supported=True, index_range=(1, 9999)):` and in `completion_for` use `rt.models.IndexRange(*index_range)`.

File: `tests/test_runtime_drain_integration.py`

Edit: add

```python
@pytest.mark.parametrize("engine", ENGINES)
def test_requests_keep_speaking_after_the_index_range_is_used(monkeypatch, tmp_path, engine):
	c = assemble(monkeypatch, tmp_path, index_range=(1, 3))
	try:
		control = c.controls[engine]
		requests = []
		for number in range(1, 9):
			requests.append(c.submit(("hello", c.commands.IndexCommand(700 + number)), engine))
			control.tail(number).release.set()
			c.wait_done(number)
		assert c.output.indexes == list(range(701, 709))
		assert all(request.state is c.scheduler.RequestState.COMPLETED for request in requests)
		# wires sent to the wrapper cycle 1, 2, 3, 1, 2, 3, 1, 2
	finally:
		c.close()
```

Expected red (on `5e1137b` code):

- `python3 -m pytest -q tests/test_index_ledger.py -k "wrap or rebinding_a_source or finished_segment_keeps or handed_out_again or keeps_allocating"`: 7 failed (`IndexSpaceExhausted: Source wire index range is exhausted`); `test_a_retired_index...` fails at segment 4, the keeps-allocating test at segment 10000.
- `python3 -m pytest -q tests/test_runtime_drain_integration.py -k index_range_is_used`: 3 failed, `<engine> native call 4 did not start` (the fourth request fails before the native call).

### 1b. Green

File: `addon/synthDrivers/WorldVoice/indexLedger.py`

Edit: module docstring describes cyclic reuse with reservations (keeps the second paragraph on ledger lifetime).

Edit: `_Segment` gains `span: range` (all wire indexes the segment holds: ordinary indexes then its marker), placed after `allocation`.

Edit: new module-level helper:

```python
def _find_start(state: _Source, count: int) -> int | None:
	"""Return the start of the first free run of count indexes, cyclically from the cursor."""
	if not count:
		return state.next_index
	spans = [segment.span for segment in state.segments.values() if segment.span]
	size = state.maximum - state.minimum + 1
	start, scanned = state.next_index, 0
	while scanned < size:
		stop = start + count
		if stop > state.maximum + 1:
			# A run never crosses the maximum; the skipped tail is free again on the next cycle.
			scanned += state.maximum + 1 - start
			start = state.minimum
			continue
		blocker = max((span.stop for span in spans if span.start < stop and start < span.stop), default=None)
		if blocker is None:
			return start
		scanned += blocker - start
		start = blocker if blocker <= state.maximum else state.minimum
	return None
```

Edit: in `prepare`, replace the high-water check and allocation with:

```python
			marker = int(state.rule.requires_end)
			start = _find_start(state, len(originals) + marker)
			if start is None:
				raise IndexSpaceExhausted("Source wire index range is exhausted")
			span = range(start, start + len(originals) + marker)
			allocation = IndexAllocation(tuple(span[: len(originals)]), span[-1] if marker else None)
			segment = _Segment(segment_id, originals, allocation, span)
			state.segments[segment_id] = segment
			for index in span:
				state.indexes[index] = segment
			state.next_index = span.stop if span.stop <= state.maximum else state.minimum
			return allocation
```

Expected green: the 7 + 3 new tests pass; `tests/test_index_ledger.py` all pass (the old exhaustion tests still raise: in each the full range or every free run is held by an unretired segment). Full suite: 1722 + 10 = **1732 passed, 0 skipped**.

## Step 2. Degrade instead of failing (commit `fix: speak a segment that gets no free index run ...`)

### 2a. Red tests

File: `tests/test_index_ledger.py`

- Replace `test_exhaustion_is_atomic` by two tests:
  - `test_a_segment_that_misses_a_full_run_keeps_only_its_marker`: END 1..3, segment 1 (123,) -> ((1,), 2) unretired; segment 2 (124,) -> ((), 3); wire 3 replays [124, None]; wire 1 still decodes to segment 1 only.
  - `test_exhaustion_is_atomic`: END 1..3, segment 1 (123, 124) -> ((1, 2), 3) holds the whole range; segment 2 with (125,) and with () raises `IndexSpaceExhausted`; wire 3 still ends segment 1 with [123, 124, None]; after retiring segment 1, segment 2 (never registered) prepares () -> marker 1 (the failed calls moved nothing).
- `test_drain_uses_both_range_endpoints_and_empty_works_after_exhaustion` -> `test_drain_uses_both_range_endpoints_and_a_full_range_degrades`: same endpoint checks; segment 4 (42,) now gets `IndexAllocation((), None)`, and draining it reports [42, None].
- `test_drain_exhaustion_does_not_partially_publish_or_consume_indexes` -> `test_drain_degrading_does_not_publish_or_consume_indexes`: segment 1 holds 1..9998; segment 2 (123, 124) -> ((), None); wire 9999 decodes to nothing; segment 3 (125,) gets (9999,); draining segment 2 reports [123, 124, None].
- New `test_a_drain_segment_without_a_free_run_is_reported_when_it_drains` (DRAIN 1..3, four originals -> ((), None), nothing published or reserved, the cursor stays (next segment gets wire 1), drain replays [900, 3, 50, None], a failed degraded segment replays nothing).
- New `test_an_end_segment_without_a_free_run_keeps_only_its_marker` (END 1..3, (1, 2, 3) -> ((), 1), marker replays [1, 2, 3, None], next () -> 2).
- New `test_degrading_warns_once_per_source_with_the_lock_released` (a handler on the module logger records level, message and `ledger._lock.locked()`; two degrades on one source and one on a second source give WARNING, DEBUG, WARNING with the exact message, all with the lock released; a segment that fits logs nothing).

File: `tests/test_index_codec.py`

- `test_drain_codec_rejects_exhausted_segment_before_output` -> `test_drain_codec_leaves_out_the_indexes_of_a_degraded_segment`: with the range held, `["hello", IndexCommand(123), other, IndexCommand(7)]` encodes to the same `"hello"` and `other` objects in order, the input is unchanged, and the drain reports [123, 7, None].
- New `test_codec_sends_only_the_marker_for_a_degraded_segment` (END 501..510, eleven indexes: the encoded tuple is the non-index commands as the same objects, then a `WorldVoiceIndexCommand(501)`; the marker reports the eleven originals then None).

File: `tests/test_runtime_adapter_contract.py`

- Drop `"exhaustion"` from `test_errors_before_core_entry_never_speak` (keep `generator` and `invalid_index`; the else branch builds `[c.index_command(123)]`).
- New `test_a_segment_too_large_for_the_range_speaks_and_reports_indexes_at_its_marker`: 16 originals in 501..516 under END_INDEX; the request completes, the core spoke once, its only wire index is the marker 501, `c.output.indexes == list(range(16))`, one done.

File: `tests/runtime_harness.py`

- The native contract adapter mirrors the codec: when `allocation.wire_indexes` is empty it leaves the `NativeIndex` commands out (otherwise `next()` on the empty iterator raises inside the generator).

Expected red: the 4 changed + 5 new ledger/codec/contract tests fail with `IndexSpaceExhausted` (the warning test with it too); `test_exhaustion_is_atomic` (new form) already passes; the contract test fails in both `native` and `legacy` (request FAILED).

### 2b. Green

File: `addon/synthDrivers/WorldVoice/indexLedger.py`

- `import logging`; `log = logging.getLogger(__name__)`.
- `IndexSpaceExhausted` docstring: no free wire index is left for a segment's terminal marker.
- `_Source` gains `warned: bool = False`.
- `prepare`:

```python
			marker = int(state.rule.requires_end)
			ordinary = len(originals)
			start = _find_start(state, ordinary + marker)
			degraded = start is None
			if degraded:
				# Keep only the terminal marker; completion reports every original in order.
				ordinary = 0
				start = _find_start(state, marker)
				if start is None:
					raise IndexSpaceExhausted("Source wire index range is exhausted")
				level = logging.DEBUG if state.warned else logging.WARNING
				state.warned = True
			span = range(start, start + ordinary + marker)
			...
		# Log after unlocking: handlers are external code.
		if degraded:
			log.log(
				level,
				"WorldVoice index range %d..%d has no room for a speech segment with %d indexes; "
				"its indexes are reported when it completes",
				state.minimum, state.maximum, len(originals),
			)
		return allocation
```

File: `addon/synthDrivers/WorldVoice/compat/indexCodec.py`

- Docstring: a degraded segment goes out without its caller indexes.
- The encoded generator skips `IndexCommand`s when `allocation.wire_indexes` is empty:

```python
		encoded = tuple(
			IndexCommand(next(indexes)) if isinstance(command, IndexCommand) else command
			for command in commands
			if allocation.wire_indexes or not isinstance(command, IndexCommand)
		)
```

Expected green: full suite 1732 - 1 (`[exhaustion]`) + 1 (split `test_exhaustion_is_atomic`) + 3 (new ledger) + 1 (new codec) + 2 (contract test, two params) = **1738 passed, 0 skipped**.

## Step 3. Property tests (commit `test: check the cyclic allocation invariants with Hypothesis`)

File: `tests/test_index_ledger.py`

- `test_property_allocation_keeps_runs_disjoint_and_reports_each_original_once`: random mode, range minimum 1..20, size 1..12, and up to 30 random operations (prepare with 0..size+2 originals, `receive_index` of any wire in `[minimum - 1, maximum + 1]`, drain or failure of a live or unknown segment, `retire_segment`, `retire_source`, unbind + rebind). A model keeps the cursor and the unretired segments' spans and checks:
  1. every allocation equals the brute-force oracle (first free contiguous run in cyclic order from the cursor that does not cross the maximum; otherwise marker only; otherwise `IndexSpaceExhausted` and the model is unchanged); DRAIN never raises;
  2. runs are inside `[minimum, maximum]`, contiguous, the marker last, and disjoint from every unretired span;
  3. a wire decodes only to the unretired segment whose span holds it, and to nothing outside every span;
  4. each segment's reported originals equal `dict.fromkeys(originals[:position])` for the furthest position reached (each once, in order), and terminal or drain reports all of them; at the end every live segment is completed and checked; failures report nothing.
- `test_property_retired_segments_never_run_the_range_out`: random mode/range and up to 40 segment sizes that fit the range, each retired before the next: every allocation is full (never degraded, never raises).

File: `tests/test_index_codec.py`

- The codec property test allows up to 24 layout items without the `<= 9` filter, so layouts may hold more indexes than 501..510; a degraded encode keeps exactly the non-index commands as the same objects, in order, and the end still reports every original once, in order.

Expected: these pass on step 2 code (they check, they do not drive). Sanity red: with step 1 code only, the ledger property test and the codec property test fail (degraded cases raise). Full suite **1740 passed, 0 skipped**. Also run `HYPOTHESIS_PROFILE=deep python3 -m pytest -q tests/test_index_ledger.py tests/test_index_codec.py -k property` once.

## Step 4. mutmut (commit `build: run mutmut on the index codec` and, if needed, `test: ...` killing survivors)

File: `pyproject.toml`

- Add `"addon/synthDrivers/WorldVoice/compat/indexCodec.py"` to `[tool.mutmut] source_paths`.

Run (Linux, worktree): `mutmut run --max-children 3 "addon.synthDrivers.WorldVoice.indexLedger*" "addon.synthDrivers.WorldVoice.compat.indexCodec*"` with a memory guard in the scratchpad that kills the run when `MemAvailable` < 3 GB. Then `mutmut results`; confirm each survivor by applying it (`mutmut apply` is not used on the worktree; the mutant is applied to a scratch copy, or checked with `mutmut show` and reasoning plus the suite run inside `mutants/`). Survivors and reasons are recorded below in "Implementation notes". `mutants/` is git-ignored and is removed afterwards.

## Step 5. Final verification

Full verification as above; record the counts below.

## Implementation notes

(filled in during implementation)
