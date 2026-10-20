"""Source-scoped wire indexes are reused only cyclically and never complete the wrong segment."""

import gc
import importlib
import logging
import sys
import weakref
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest
from addon_loader import alias_package
from hypothesis import HealthCheck, given, settings, strategies as st
from runtime_harness import RUNTIME, forbid_legacy_runtime_imports
from waiting import WAIT_TIMEOUT


@pytest.fixture
def env(monkeypatch, rt):
	name = "worldvoice_ledger_test"
	alias_package(monkeypatch, name, RUNTIME.parent)
	monkeypatch.setitem(sys.modules, name + ".runtime", rt.package)
	monkeypatch.setitem(sys.modules, name + ".runtime.models", rt.models)
	monkeypatch.delitem(sys.modules, name + ".indexLedger", raising=False)
	with forbid_legacy_runtime_imports(monkeypatch):
		module = importlib.import_module(name + ".indexLedger")
	ledger = module.IndexLedger()
	source, source_id = object(), object()
	contract = rt.models.CompletionContract(
		rt.models.CompletionMode.END_INDEX,
		rt.models.IndexRange(501, 510),
	)
	ledger.bind(source, source_id, contract)
	yield SimpleNamespace(
		ledger=ledger,
		source=source,
		source_id=source_id,
		contract=contract,
		module=module,
		models=rt.models,
		context=rt.models.PlaybackContext(source_id, 1),
	)
	ledger.close()


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
			ledger=ledger,
			source=source,
			source_id=source_id,
			contract=contract,
			token=token,
			module=env.module,
			models=env.models,
		)

	yield make
	for ledger in ledgers:
		ledger.close()


def use(s, source_id, segment_id, originals):
	"""Prepare and retire one segment; return its allocation as plain tuples."""
	context = s.models.PlaybackContext(source_id, segment_id)
	allocation = s.ledger.prepare(context, originals)
	s.ledger.retire_segment(context)
	return allocation.wire_indexes, allocation.end_index


def drained(s, segment_id, source_id=None):
	event = s.models.PlaybackEvent(
		s.models.EventKind.SEGMENT_DRAINED,
		s.source_id if source_id is None else source_id,
		segment_id=segment_id,
	)
	return s.ledger.receive_segment_event(event, binding_token=s.token)


def test_terminal_marker_replays_missing_originals_before_end(env):
	allocation = env.ledger.prepare(env.context, (123, 124))
	assert allocation.wire_indexes == (501, 502)
	assert allocation.end_index == 503
	with pytest.raises(FrozenInstanceError):
		allocation.end_index = 504
	events = env.ledger.receive_index(env.source_id, 503)
	assert [e.kind for e in events] == [env.models.EventKind.INDEX] * 2 + [env.models.EventKind.SEGMENT_END]
	assert [e.index for e in events] == [123, 124, None]
	assert all(e.segment_id == 1 and e.source_id is env.source_id for e in events)
	assert env.ledger.receive_index(env.source_id, 501) == ()
	assert env.ledger.receive_index(env.source_id, 503) == ()


def test_intermediate_marker_replays_in_command_order(env):
	env.ledger.prepare(env.context, (900, 3, 50))
	assert [e.index for e in env.ledger.receive_index(env.source_id, 502)] == [900, 3]
	assert env.ledger.receive_index(env.source_id, 501) == ()
	assert [e.index for e in env.ledger.receive_index(env.source_id, 504)] == [50, None]


def test_retired_segment_cannot_complete_new_segment(env):
	env.ledger.prepare(env.context, (123,))
	env.ledger.retire_segment(env.context)
	env.ledger.retire_segment(env.context)
	next_context = env.models.PlaybackContext(env.source_id, 2)
	allocation = env.ledger.prepare(next_context, (124,))
	assert allocation.wire_indexes == (503,)
	assert env.ledger.receive_index(env.source_id, 502) == ()
	assert [e.segment_id for e in env.ledger.receive_index(env.source_id, 504)] == [2, 2]


def test_same_source_rebind_preserves_high_water(env):
	env.ledger.prepare(env.context, (123,))
	env.ledger.unbind(env.source_id)
	env.ledger.unbind(env.source_id)
	rebound_id = object()
	env.ledger.bind(env.source, rebound_id, env.contract)
	allocation = env.ledger.prepare(env.models.PlaybackContext(rebound_id, 1), ())
	assert allocation.end_index == 503
	assert env.ledger.receive_index(env.source_id, 502) == ()
	assert env.ledger.receive_index(rebound_id, 502) == ()


def test_alias_same_binding_does_not_reset(env):
	env.ledger.prepare(env.context, ())
	env.ledger.bind(env.source, env.source_id, env.contract)
	assert env.ledger.prepare(env.models.PlaybackContext(env.source_id, 2), ()).end_index == 502
	assert [e.segment_id for e in env.ledger.receive_index(env.source_id, 501)] == [1]


def test_equal_but_distinct_source_uses_identity(env):
	class EqualSource:
		def __eq__(self, other):
			return True

		__hash__ = None

	first, second = EqualSource(), EqualSource()
	first_id, second_id = object(), object()
	env.ledger.bind(first, first_id, env.contract)
	env.ledger.bind(second, second_id, env.contract)
	assert env.ledger.prepare(env.models.PlaybackContext(first_id, 1), ()).end_index == 501
	assert env.ledger.prepare(env.models.PlaybackContext(second_id, 1), ()).end_index == 501


def test_duplicate_original_index_delivered_once(env):
	env.ledger.prepare(env.context, (123, 123, 124, 123))
	assert [e.index for e in env.ledger.receive_index(env.source_id, 502)] == [123]
	assert [e.index for e in env.ledger.receive_index(env.source_id, 505)] == [124, None]


def test_empty_originals_still_allocate_terminal(env):
	allocation = env.ledger.prepare(env.context, ())
	assert allocation.wire_indexes == ()
	assert allocation.end_index == 501
	events = env.ledger.receive_index(env.source_id, 501)
	assert len(events) == 1
	assert events[0].kind is env.models.EventKind.SEGMENT_END


def test_unknown_large_index_does_not_advance(env):
	env.ledger.prepare(env.context, (123,))
	assert env.ledger.receive_index(env.source_id, 1000000) == ()
	assert env.ledger.receive_index(object(), 502) == ()
	assert [e.index for e in env.ledger.receive_index(env.source_id, 501)] == [123]
	assert env.ledger.prepare(env.models.PlaybackContext(env.source_id, 2), ()).end_index == 503


def test_a_segment_that_misses_a_full_run_keeps_only_its_marker(make_ledger):
	s = make_ledger("END_INDEX", 1, 3)
	assert s.ledger.prepare(s.models.PlaybackContext(s.source_id, 1), (123,)) == s.module.IndexAllocation(
		(1,),
		2,
	)
	# Two indexes are needed but only 3 is free: the segment keeps only its terminal marker.
	assert s.ledger.prepare(s.models.PlaybackContext(s.source_id, 2), (124,)) == s.module.IndexAllocation(
		(),
		3,
	)
	assert [(e.index, e.segment_id) for e in s.ledger.receive_index(s.source_id, 3)] == [(124, 2), (None, 2)]
	assert [(e.index, e.segment_id) for e in s.ledger.receive_index(s.source_id, 1)] == [(123, 1)]


def test_exhaustion_is_atomic(make_ledger):
	s = make_ledger("END_INDEX", 1, 3)
	first = s.models.PlaybackContext(s.source_id, 1)
	assert s.ledger.prepare(first, (123, 124)) == s.module.IndexAllocation((1, 2), 3)
	# Every index is reserved: not even a terminal marker fits.
	second = s.models.PlaybackContext(s.source_id, 2)
	for originals in ((125,), ()):
		with pytest.raises(s.module.IndexSpaceExhausted, match="Source wire index range is exhausted"):
			s.ledger.prepare(second, originals)
	assert [(e.index, e.segment_id) for e in s.ledger.receive_index(s.source_id, 3)] == [
		(123, 1),
		(124, 1),
		(None, 1),
	]
	# The failed calls registered nothing and moved nothing.
	s.ledger.retire_segment(first)
	assert s.ledger.prepare(second, ()) == s.module.IndexAllocation((), 1)


def test_an_end_segment_without_a_free_run_keeps_only_its_marker(make_ledger):
	s = make_ledger("END_INDEX", 1, 3)
	assert s.ledger.prepare(s.models.PlaybackContext(s.source_id, 1), (1, 2, 3)) == s.module.IndexAllocation(
		(),
		1,
	)
	events = s.ledger.receive_index(s.source_id, 1)
	assert [(e.kind.name, e.index) for e in events] == [
		("INDEX", 1),
		("INDEX", 2),
		("INDEX", 3),
		("SEGMENT_END", None),
	]
	# Only the marker moved the cursor.
	assert s.ledger.prepare(s.models.PlaybackContext(s.source_id, 2), ()).end_index == 2


def test_degrading_warns_once_per_source_with_the_lock_released(make_ledger, caplog):
	s = make_ledger("DRAIN", 1, 3)
	other_id = object()
	s.ledger.bind(object(), other_id, s.contract)
	records = []

	class Recorder(logging.Handler):
		def emit(self, record):
			records.append((record.levelno, record.getMessage(), s.ledger._lock.locked()))

	log = s.module.log
	caplog.set_level(logging.DEBUG, logger=log.name)
	handler = Recorder()
	log.addHandler(handler)
	try:
		s.ledger.prepare(s.models.PlaybackContext(s.source_id, 1), (1, 2, 3, 4))
		s.ledger.prepare(s.models.PlaybackContext(s.source_id, 2), (5, 6, 7, 8))
		s.ledger.prepare(s.models.PlaybackContext(other_id, 1), tuple(range(5)))
		s.ledger.prepare(s.models.PlaybackContext(s.source_id, 3), (9,))
	finally:
		log.removeHandler(handler)
	message = (
		"WorldVoice index range 1..3 has no room for a speech segment with {} indexes; "
		"its indexes are reported when it completes"
	)
	assert records == [
		(logging.WARNING, message.format(4), False),
		(logging.DEBUG, message.format(4), False),
		(logging.WARNING, message.format(5), False),
	]


def test_runs_wrap_to_the_minimum_without_crossing_the_maximum(make_ledger):
	s = make_ledger("END_INDEX", 501, 510)
	assert use(s, s.source_id, 1, (1, 2, 3)) == ((501, 502, 503), 504)
	assert use(s, s.source_id, 2, (4, 5, 6, 7)) == ((505, 506, 507, 508), 509)
	# Two indexes do not fit in 510..510: the run starts again at the minimum.
	assert use(s, s.source_id, 3, (8,)) == ((501,), 502)
	assert use(s, s.source_id, 4, (9,) * 6) == ((503, 504, 505, 506, 507, 508), 509)
	# The tail skipped at the wrap is used on the next cycle.
	assert use(s, s.source_id, 5, ()) == ((), 510)
	assert use(s, s.source_id, 6, ()) == ((), 501)


def test_rebinding_a_source_continues_its_cycle(make_ledger):
	# Before the fix the cursor never came back, so a rebind could not recover a used-up range.
	s = make_ledger("END_INDEX", 501, 510)
	assert use(s, s.source_id, 1, (1, 2, 3)) == ((501, 502, 503), 504)
	s.ledger.retire_source(s.source_id)
	s.ledger.unbind(s.source_id)
	source_id = object()
	s.ledger.bind(s.source, source_id, s.contract)
	assert use(s, source_id, 2, (4,)) == ((505,), 506)
	assert use(s, source_id, 3, (5, 6, 7)) == ((507, 508, 509), 510)
	s.ledger.unbind(source_id)
	source_id = object()
	s.ledger.bind(s.source, source_id, s.contract)
	assert use(s, source_id, 4, (8,)) == ((501,), 502)


@pytest.mark.parametrize("mode", ["END_INDEX", "END_INDEX_AND_DRAIN", "DRAIN"])
def test_a_finished_segment_keeps_its_indexes_until_it_is_retired(make_ledger, mode):
	s = make_ledger(mode, 1, 10)
	marker = mode != "DRAIN"
	first = s.models.PlaybackContext(s.source_id, 1)
	allocation = s.ledger.prepare(first, (42,))
	span = (1, 2) if marker else (1,)
	assert (*allocation.wire_indexes, *((allocation.end_index,) if marker else ())) == span
	if mode == "END_INDEX":
		s.ledger.receive_index(s.source_id, 2)
	else:
		# AND still waits for its terminal marker after the drain.
		drained(s, 1)
	# A filler takes the rest of the range and is retired, so the cursor wraps to the minimum.
	assert use(s, s.source_id, 2, (0,) * (10 - len(span) - marker))[0][0] == len(span) + 1
	third = s.ledger.prepare(s.models.PlaybackContext(s.source_id, 3), (7,))
	assert third.wire_indexes == (len(span) + 1,)
	assert s.ledger.receive_index(s.source_id, 1) == ()
	if marker:
		events = s.ledger.receive_index(s.source_id, 2)
		ended = [(s.models.EventKind.SEGMENT_END, 1)] if mode == "END_INDEX_AND_DRAIN" else []
		assert [(e.kind, e.segment_id) for e in events] == ended


def test_a_retired_index_decodes_to_nothing_until_it_is_handed_out_again(make_ledger):
	s = make_ledger("DRAIN", 1, 3)
	for number in (1, 2, 3):
		assert use(s, s.source_id, number, (10 * number,)) == ((number,), None)
	assert [s.ledger.receive_index(s.source_id, wire) for wire in (1, 2, 3)] == [(), (), ()]
	assert s.ledger.prepare(s.models.PlaybackContext(s.source_id, 4), (40,)).wire_indexes == (1,)
	assert [(e.index, e.segment_id) for e in s.ledger.receive_index(s.source_id, 1)] == [(40, 4)]
	assert s.ledger.receive_index(s.source_id, 2) == ()


def test_duplicate_prepare_rejected_until_retired_even_after_end(env):
	env.ledger.prepare(env.context, ())
	with pytest.raises(env.module.InvalidIndexContext, match="Segment is already prepared"):
		env.ledger.prepare(env.context, ())
	env.ledger.receive_index(env.source_id, 501)
	with pytest.raises(env.module.InvalidIndexContext, match="Segment is already prepared"):
		env.ledger.prepare(env.context, ())
	env.ledger.retire_segment(env.context)
	assert env.ledger.prepare(env.context, ()).end_index == 502


def test_invalid_bindings_do_not_replace_valid_binding(env):
	# Each guard of bind and prepare raises the same type; match says which one stopped the call.
	with pytest.raises(env.module.InvalidIndexContext, match="Source is already bound to another source ID"):
		env.ledger.bind(env.source, object(), env.contract)
	with pytest.raises(env.module.InvalidIndexContext, match="Source ID is already bound to another source"):
		env.ledger.bind(object(), env.source_id, env.contract)
	with pytest.raises(env.module.InvalidIndexContext, match="Source is not bound to this ledger"):
		env.ledger.prepare(env.models.PlaybackContext(object(), 1), ())
	assert env.ledger.prepare(env.context, ()).end_index == 501


@pytest.mark.parametrize("mode,bounds", [("END_INDEX", (1, 100)), ("END_INDEX_AND_DRAIN", (501, 510))])
def test_rebind_rejects_changed_contract(env, mode, bounds):
	env.ledger.unbind(env.source_id)
	changed = env.models.CompletionContract(
		getattr(env.models.CompletionMode, mode),
		env.models.IndexRange(*bounds),
	)
	with pytest.raises(
		env.module.InvalidIndexContext,
		match="A source cannot change its completion contract",
	):
		env.ledger.bind(env.source, env.source_id, changed)
	env.ledger.bind(env.source, env.source_id, env.contract)
	assert env.ledger.prepare(env.context, ()).end_index == 501


def test_retire_source_drops_all_segments_but_preserves_binding_and_high_water(env):
	env.ledger.prepare(env.context, ())
	second = env.models.PlaybackContext(env.source_id, 2)
	env.ledger.prepare(second, ())
	env.ledger.retire_source(env.source_id)
	env.ledger.retire_source(env.source_id)
	assert env.ledger.receive_index(env.source_id, 501) == ()
	assert env.ledger.receive_index(env.source_id, 502) == ()
	assert env.ledger.prepare(env.context, ()).end_index == 503


def test_close_releases_source_retained_through_unbind_and_rejects_work(env):
	class Source:
		pass

	source = Source()
	source_ref = weakref.ref(source)
	source_id = object()
	env.ledger.bind(source, source_id, env.contract)
	env.ledger.unbind(source_id)
	del source
	gc.collect()
	assert source_ref() is not None
	env.ledger.close()
	env.ledger.close()
	gc.collect()
	assert source_ref() is None
	with pytest.raises(env.module.InvalidIndexContext, match="Ledger is closed"):
		env.ledger.bind(object(), object(), env.contract)
	with pytest.raises(env.module.InvalidIndexContext, match="Source is not bound to this ledger"):
		env.ledger.prepare(env.context, ())
	assert env.ledger.receive_index(env.source_id, 501) == ()
	env.ledger.retire_segment(env.context)
	env.ledger.retire_source(env.source_id)
	env.ledger.unbind(env.source_id)


def test_source_and_token_identity_never_calls_custom_hash_or_equality(env):
	class IdentityOnly:
		def __hash__(self):
			raise AssertionError("User hash must not run")

		def __eq__(self, other):
			raise AssertionError("User equality must not run")

	source, source_id = IdentityOnly(), IdentityOnly()
	context = env.models.PlaybackContext(source_id, 7)
	env.ledger.bind(source, source_id, env.contract)
	env.ledger.bind(source, source_id, env.contract)
	allocation = env.ledger.prepare(context, (42,))
	assert [e.index for e in env.ledger.receive_index(source_id, allocation.end_index)] == [42, None]
	env.ledger.retire_segment(context)
	env.ledger.unbind(source_id)


def test_close_releases_sources_after_unlocking(env):
	from threading import Event, Thread

	callback_finished = Event()
	callback_blocked = []
	threads = []
	ledger = env.ledger

	class Source:
		def __del__(self):
			def callback():
				ledger.receive_index(object(), 501)
				callback_finished.set()

			thread = Thread(target=callback, daemon=True)
			threads.append(thread)
			thread.start()
			callback_blocked.append(not callback_finished.wait(WAIT_TIMEOUT))

	source = Source()
	source_id = object()
	ledger.bind(source, source_id, env.contract)
	del source
	ledger.close()
	for thread in threads:
		thread.join(1)
	assert callback_blocked == [False]


def test_concurrent_preparations_allocate_disjoint_complete_segments(env):
	from concurrent.futures import ThreadPoolExecutor

	with ThreadPoolExecutor(max_workers=4) as pool:
		allocations = tuple(
			pool.map(
				lambda segment_id: env.ledger.prepare(
					env.models.PlaybackContext(env.source_id, segment_id),
					(7,),
				),
				range(1, 6),
			),
		)
	assert sorted((a.wire_indexes, a.end_index) for a in allocations) == [
		((501,), 502),
		((503,), 504),
		((505,), 506),
		((507,), 508),
		((509,), 510),
	]


@pytest.mark.parametrize("same_source", [False, True])
def test_decode_binding_token_cannot_consume_replacement_segment(env, same_source):
	old_token = env.ledger.bind(env.source, env.source_id, env.contract)
	env.ledger.prepare(env.context, (42, 7))
	env.ledger.unbind(env.source_id)
	source = env.source if same_source else object()
	new_token = env.ledger.bind(source, env.source_id, env.contract)
	allocation = env.ledger.prepare(env.models.PlaybackContext(env.source_id, 2), (80, 81))
	assert (
		env.ledger.receive_index(
			env.source_id,
			allocation.end_index,
			binding_token=old_token,
		)
		== ()
	)
	events = env.ledger.receive_index(env.source_id, allocation.end_index, binding_token=new_token)
	assert [(e.index, e.segment_id) for e in events] == [(80, 2), (81, 2), (None, 2)]


def test_duplicate_bind_token_still_decodes_existing_segment(env):
	token = env.ledger.bind(env.source, env.source_id, env.contract)
	allocation = env.ledger.prepare(env.context, (42,))
	env.ledger.bind(env.source, env.source_id, env.contract)
	events = env.ledger.receive_index(env.source_id, allocation.end_index, binding_token=token)
	assert [(e.index, e.segment_id) for e in events] == [(42, 1), (None, 1)]


@pytest.fixture
def drain_env(env):
	ledger = env.module.IndexLedger()
	source, source_id = object(), object()
	contract = env.models.CompletionContract(
		env.models.CompletionMode.DRAIN,
		env.models.IndexRange(1, 9999),
	)
	token = ledger.bind(source, source_id, contract)
	yield SimpleNamespace(
		ledger=ledger,
		source=source,
		source_id=source_id,
		contract=contract,
		token=token,
		module=env.module,
		models=env.models,
		context=env.models.PlaybackContext(source_id, 1),
	)
	ledger.close()


def segment_event(env, kind="SEGMENT_DRAINED", **kwargs):
	return env.models.PlaybackEvent(
		getattr(env.models.EventKind, kind),
		env.source_id,
		segment_id=env.context.segment_id,
		**kwargs,
	)


def test_drain_allocation_has_no_terminal_and_empty_uses_no_wire(drain_env):
	env = drain_env
	empty = env.ledger.prepare(env.context, ())
	assert empty.wire_indexes == () and empty.end_index is None
	following = env.models.PlaybackContext(env.source_id, 2)
	allocation = env.ledger.prepare(following, (123, 124))
	assert allocation.wire_indexes == (1, 2)
	assert allocation.end_index is None


def test_drain_restores_indexes_in_one_batch_before_completion(drain_env):
	env = drain_env
	originals = [900, 3, 50, 900]
	allocation = env.ledger.prepare(env.context, originals)
	assert allocation.wire_indexes == (1, 2, 3, 4)
	assert originals == [900, 3, 50, 900]
	assert [e.index for e in env.ledger.receive_index(env.source_id, 2)] == [900, 3]
	event = segment_event(env)
	events = env.ledger.receive_segment_event(event, binding_token=env.token)
	assert isinstance(events, tuple)
	assert [e.kind for e in events] == [env.models.EventKind.INDEX, env.models.EventKind.SEGMENT_DRAINED]
	assert [e.index for e in events] == [50, None]
	assert events[-1] is event
	assert all(e.source_id is env.source_id and e.segment_id == 1 for e in events)
	assert env.ledger.receive_index(env.source_id, 3) == ()
	assert env.ledger.receive_segment_event(event, binding_token=env.token) == ()
	assert (
		env.ledger.receive_segment_event(
			segment_event(env, "SEGMENT_FAILED", error=RuntimeError()),
			binding_token=env.token,
		)
		== ()
	)
	with pytest.raises(env.module.InvalidIndexContext):
		env.ledger.prepare(env.context, ())


def test_drain_replays_all_missing_indexes_in_original_order(drain_env):
	env = drain_env
	env.ledger.prepare(env.context, (900, 3, 900, 50))
	events = env.ledger.receive_segment_event(segment_event(env), binding_token=env.token)
	assert [e.index for e in events] == [900, 3, 50, None]
	assert env.ledger.receive_index(env.source_id, 1) == ()
	assert env.ledger.receive_index(env.source_id, 4) == ()


def test_empty_drain_segment_still_accepts_correlated_completion(drain_env):
	env = drain_env
	env.ledger.prepare(env.context, ())
	event = segment_event(env)
	assert env.ledger.receive_segment_event(event, binding_token=env.token) == (event,)


def test_failed_segment_does_not_flush_pending_indexes(drain_env):
	env = drain_env
	env.ledger.prepare(env.context, (900, 3, 50))
	assert [e.index for e in env.ledger.receive_index(env.source_id, 1)] == [900]
	error = RuntimeError("native failure")
	event = segment_event(env, "SEGMENT_FAILED", error=error)
	events = env.ledger.receive_segment_event(event, binding_token=env.token)
	assert events == (event,) and events[0].error is error
	assert env.ledger.receive_index(env.source_id, 2) == ()
	assert env.ledger.receive_segment_event(event, binding_token=env.token) == ()
	assert env.ledger.receive_segment_event(segment_event(env), binding_token=env.token) == ()


def test_segment_end_event_is_not_a_drain_failure(drain_env):
	env = drain_env
	env.ledger.prepare(env.context, (42,))
	assert (
		env.ledger.receive_segment_event(
			segment_event(env, "SEGMENT_END"),
			binding_token=env.token,
		)
		== ()
	)
	assert [
		e.index
		for e in env.ledger.receive_segment_event(
			segment_event(env),
			binding_token=env.token,
		)
	] == [42, None]


@pytest.mark.parametrize("kind", ["SEGMENT_DRAINED", "SEGMENT_FAILED"])
def test_segment_event_requires_matching_source_segment_and_token(drain_env, kind):
	env = drain_env
	env.ledger.prepare(env.context, (42,))
	event = segment_event(env, kind)
	assert env.ledger.receive_segment_event(event, binding_token=object()) == ()
	assert env.ledger.receive_segment_event(event, binding_token=None) == ()
	for source_id, segment_id in [(object(), 1), (env.source_id, 2), (env.source_id, None)]:
		wrong = env.models.PlaybackEvent(event.kind, source_id, segment_id=segment_id)
		assert env.ledger.receive_segment_event(wrong, binding_token=env.token) == ()
	events = env.ledger.receive_segment_event(event, binding_token=env.token)
	assert events[-1] is event


@pytest.mark.parametrize("cleanup", ["retire_segment", "retire_source", "unbind", "close"])
def test_drain_cleanup_is_idempotent_and_rejects_late_events(drain_env, cleanup):
	env = drain_env
	env.ledger.prepare(env.context, (42,))
	method = getattr(env.ledger, cleanup)
	args = () if cleanup == "close" else ((env.context,) if cleanup == "retire_segment" else (env.source_id,))
	method(*args)
	method(*args)
	assert env.ledger.receive_index(env.source_id, 1) == ()
	assert env.ledger.receive_segment_event(segment_event(env), binding_token=env.token) == ()
	assert (
		env.ledger.receive_segment_event(
			segment_event(env, "SEGMENT_FAILED"),
			binding_token=env.token,
		)
		== ()
	)


@pytest.mark.parametrize("same_source", [False, True])
def test_old_segment_event_token_cannot_consume_replacement_segment(drain_env, same_source):
	env = drain_env
	env.ledger.prepare(env.context, (42,))
	env.ledger.unbind(env.source_id)
	source = env.source if same_source else object()
	new_token = env.ledger.bind(source, env.source_id, env.contract)
	allocation = env.ledger.prepare(env.context, (80,))
	assert allocation.wire_indexes == ((2,) if same_source else (1,))
	assert env.ledger.receive_segment_event(segment_event(env), binding_token=env.token) == ()
	assert [
		e.index
		for e in env.ledger.receive_segment_event(
			segment_event(env),
			binding_token=new_token,
		)
	] == [80, None]


def test_drain_uses_both_range_endpoints_and_a_full_range_degrades(drain_env):
	env = drain_env
	allocation = env.ledger.prepare(env.context, tuple(range(9999)))
	assert len(allocation.wire_indexes) == 9999
	assert allocation.wire_indexes[0] == 1
	assert allocation.wire_indexes[-1] == 9999
	assert allocation.end_index is None
	empty = env.models.PlaybackContext(env.source_id, 2)
	assert env.ledger.prepare(empty, ()).wire_indexes == ()
	assert env.ledger.prepare(env.models.PlaybackContext(env.source_id, 3), ()).end_index is None
	# Segment 1 holds the whole range: the next segment with an index is spoken without wire indexes.
	degraded = env.models.PlaybackContext(env.source_id, 4)
	assert env.ledger.prepare(degraded, (42,)) == env.module.IndexAllocation((), None)
	event = env.models.PlaybackEvent(
		env.models.EventKind.SEGMENT_DRAINED,
		env.source_id,
		segment_id=2,
	)
	assert env.ledger.receive_segment_event(event, binding_token=env.token) == (event,)
	assert [(e.index, e.segment_id) for e in drained(env, 4)] == [(42, 4), (None, 4)]


def test_drain_degrading_does_not_publish_or_consume_indexes(drain_env):
	env = drain_env
	env.ledger.prepare(env.context, tuple(range(9998)))
	degraded = env.models.PlaybackContext(env.source_id, 2)
	assert env.ledger.prepare(degraded, (123, 124)) == env.module.IndexAllocation((), None)
	assert env.ledger.receive_index(env.source_id, 9999) == ()
	assert env.ledger.prepare(env.models.PlaybackContext(env.source_id, 3), (125,)).wire_indexes == (9999,)
	assert [e.index for e in drained(env, 2)] == [123, 124, None]


def test_a_drain_segment_without_a_free_run_is_reported_when_it_drains(make_ledger):
	s = make_ledger("DRAIN", 1, 3)
	assert s.ledger.prepare(s.models.PlaybackContext(s.source_id, 1), (900, 3, 50, 900)) == (
		s.module.IndexAllocation((), None)
	)
	assert [s.ledger.receive_index(s.source_id, wire) for wire in (1, 2, 3)] == [(), (), ()]
	# It reserves nothing and leaves the cursor: the next segment starts at the minimum.
	assert s.ledger.prepare(s.models.PlaybackContext(s.source_id, 2), (7,)).wire_indexes == (1,)
	assert [(e.kind.name, e.index, e.segment_id) for e in drained(s, 1)] == [
		("INDEX", 900, 1),
		("INDEX", 3, 1),
		("INDEX", 50, 1),
		("SEGMENT_DRAINED", None, 1),
	]
	# A failed degraded segment reports nothing, as any failed segment.
	s.ledger.prepare(s.models.PlaybackContext(s.source_id, 3), (1, 2, 3, 4))
	failure = s.models.PlaybackEvent(s.models.EventKind.SEGMENT_FAILED, s.source_id, segment_id=3)
	assert s.ledger.receive_segment_event(failure, binding_token=s.token) == (failure,)
	assert drained(s, 3) == ()


def test_drain_source_keeps_allocating_after_the_range_is_used(make_ledger):
	# The production DRAIN range; before the fix segment 10000 raised IndexSpaceExhausted.
	s = make_ledger("DRAIN", 1, 9999)
	for number in range(1, 3 * 9999 + 1):
		context = s.models.PlaybackContext(s.source_id, number)
		allocation = s.ledger.prepare(context, (number,))
		assert allocation == s.module.IndexAllocation(((number - 1) % 9999 + 1,), None)
		events = s.ledger.receive_index(s.source_id, allocation.wire_indexes[0])
		assert [(e.index, e.segment_id) for e in events] == [(number, number)]
		s.ledger.retire_segment(context)


@pytest.fixture
def and_env(env):
	ledger = env.module.IndexLedger()
	source, source_id = object(), object()
	contract = env.models.CompletionContract(
		env.models.CompletionMode.END_INDEX_AND_DRAIN,
		env.models.IndexRange(1, 9999),
	)
	token = ledger.bind(source, source_id, contract)
	yield SimpleNamespace(
		ledger=ledger,
		source_id=source_id,
		token=token,
		models=env.models,
		context=env.models.PlaybackContext(source_id, 1),
	)
	ledger.close()


def test_and_drain_first_keeps_real_terminal_marker_mapping(and_env):
	env = and_env
	allocation = env.ledger.prepare(env.context, (42, 7))
	event = segment_event(env)
	assert [e.index for e in env.ledger.receive_segment_event(event, binding_token=env.token)] == [
		42,
		7,
		None,
	]
	assert env.ledger.receive_index(env.source_id, 1) == ()
	assert env.ledger.receive_segment_event(event, binding_token=env.token) == ()
	events = env.ledger.receive_index(env.source_id, allocation.end_index)
	assert [(e.kind, e.index, e.segment_id) for e in events] == [(env.models.EventKind.SEGMENT_END, None, 1)]
	assert env.ledger.receive_index(env.source_id, allocation.end_index) == ()


def test_and_end_first_keeps_segment_record_for_later_drain(and_env):
	env = and_env
	allocation = env.ledger.prepare(env.context, (42, 7))
	assert [e.index for e in env.ledger.receive_index(env.source_id, allocation.end_index)] == [42, 7, None]
	event = segment_event(env)
	assert env.ledger.receive_segment_event(event, binding_token=env.token) == (event,)
	assert env.ledger.receive_segment_event(event, binding_token=env.token) == ()
	assert (
		env.ledger.receive_segment_event(segment_event(env, "SEGMENT_FAILED"), binding_token=env.token) == ()
	)


@pytest.mark.parametrize("first", ["drain", "end"])
def test_and_failure_before_both_conditions_retires_remaining_completion(and_env, first):
	env = and_env
	allocation = env.ledger.prepare(env.context, (42, 7))
	if first == "drain":
		env.ledger.receive_segment_event(segment_event(env), binding_token=env.token)
	else:
		env.ledger.receive_index(env.source_id, allocation.end_index)
	failure = segment_event(env, "SEGMENT_FAILED", error=RuntimeError("failure"))
	assert env.ledger.receive_segment_event(failure, binding_token=env.token) == (failure,)
	assert env.ledger.receive_index(env.source_id, allocation.end_index) == ()
	assert env.ledger.receive_segment_event(segment_event(env), binding_token=env.token) == ()


def test_end_index_contract_rejects_drain_but_accepts_failure(env):
	token = env.ledger.bind(env.source, env.source_id, env.contract)
	allocation = env.ledger.prepare(env.context, (42,))
	assert env.ledger.receive_segment_event(segment_event(env), binding_token=token) == ()
	failure = segment_event(env, "SEGMENT_FAILED", error=RuntimeError("failure"))
	assert env.ledger.receive_segment_event(failure, binding_token=token) == (failure,)
	assert env.ledger.receive_index(env.source_id, allocation.end_index) == ()


def test_a_failure_after_the_end_index_is_ignored(env):
	# An END_INDEX segment is finished at its terminal marker; a late failure must not reopen it.
	token = env.ledger.bind(env.source, env.source_id, env.contract)
	allocation = env.ledger.prepare(env.context, (5,))
	assert [e.kind for e in env.ledger.receive_index(env.source_id, allocation.end_index)] == [
		env.models.EventKind.INDEX,
		env.models.EventKind.SEGMENT_END,
	]
	assert env.ledger.receive_segment_event(segment_event(env, "SEGMENT_FAILED"), binding_token=token) == ()


def test_a_failure_after_drain_and_end_is_ignored(and_env):
	env = and_env
	allocation = env.ledger.prepare(env.context, (42,))
	env.ledger.receive_segment_event(segment_event(env), binding_token=env.token)
	env.ledger.receive_index(env.source_id, allocation.end_index)
	assert (
		env.ledger.receive_segment_event(segment_event(env, "SEGMENT_FAILED"), binding_token=env.token) == ()
	)


def test_a_bound_source_id_stays_alive_until_unbound(env):
	# Bindings are keyed by id(source_id); were a bound ID freed, a new object could take its
	# id() and receive another source's events.
	class SourceId:
		pass

	source_id = SourceId()
	reference = weakref.ref(source_id)
	env.ledger.bind(object(), source_id, env.contract)
	del source_id
	gc.collect()
	assert reference() is not None
	env.ledger.unbind(reference())
	gc.collect()
	assert reference() is None


PROPERTY_MODES = ("END_INDEX", "END_INDEX_AND_DRAIN", "DRAIN")


def first_free_run(cursor, count, minimum, maximum, reserved):
	"""Brute force: the first start, cyclically from the cursor, of a free run that fits."""
	if not count:
		return cursor
	size = maximum - minimum + 1
	for step in range(size):
		start = minimum + (cursor - minimum + step) % size
		if start + count - 1 <= maximum and reserved.isdisjoint(range(start, start + count)):
			return start
	return None


# Fresh ledgers per example come from the module the function-scoped env loaded once.
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
	mode=st.sampled_from(PROPERTY_MODES),
	minimum=st.integers(1, 20),
	size=st.integers(1, 12),
	data=st.data(),
)
def test_property_allocation_keeps_runs_disjoint_and_reports_each_original_once(
	env,
	mode,
	minimum,
	size,
	data,
):
	models, kinds = env.models, env.models.EventKind
	maximum = minimum + size - 1
	marker = int(mode != "DRAIN")
	ledger = env.module.IndexLedger()
	source, source_id = object(), object()
	contract = models.CompletionContract(
		getattr(models.CompletionMode, mode),
		models.IndexRange(minimum, maximum),
	)
	token = ledger.bind(source, source_id, contract)
	cursor, live, next_id = minimum, {}, 1

	def finished(segment):
		if segment.failed:
			return True
		return {
			"END_INDEX": segment.end_seen,
			"END_INDEX_AND_DRAIN": segment.end_seen and segment.drain_seen,
			"DRAIN": segment.drain_seen,
		}[mode]

	def check_reported(segment, events):
		assert all(event.segment_id == segment.id and event.source_id is source_id for event in events)
		indexes = [event for event in events if event.kind is kinds.INDEX]
		assert events[: len(indexes)] == tuple(indexes)
		segment.reported += [event.index for event in indexes]
		# Each original once, in order, up to the furthest position reached.
		assert segment.reported == list(dict.fromkeys(segment.originals[: segment.position]))

	def receive(wire):
		events = ledger.receive_index(source_id, wire, binding_token=token)
		owners = [segment for segment in live.values() if wire in segment.span]
		assert len(owners) <= 1
		if not owners:
			assert events == ()
			return
		segment = owners[0]
		if wire == segment.end and not (segment.end_seen or segment.failed):
			assert events[-1].kind is kinds.SEGMENT_END
			events = events[:-1]
			segment.end_seen, segment.position = True, len(segment.originals)
		elif wire in segment.wires and not (segment.end_seen or segment.drain_seen or segment.failed):
			segment.position = max(segment.position, segment.wires.index(wire) + 1)
		else:
			assert events == ()
		check_reported(segment, events)

	def drain(segment_id):
		event = models.PlaybackEvent(kinds.SEGMENT_DRAINED, source_id, segment_id=segment_id)
		events = ledger.receive_segment_event(event, binding_token=token)
		segment = live.get(segment_id)
		if segment is None or finished(segment) or mode == "END_INDEX" or segment.drain_seen:
			assert events == ()
			return
		assert events[-1] is event
		segment.drain_seen, segment.position = True, len(segment.originals)
		check_reported(segment, events[:-1])

	for _ in range(data.draw(st.integers(1, 30))):
		operation = data.draw(
			st.sampled_from(
				("prepare", "prepare", "index", "drain", "fail", "retire", "retire_source", "rebind"),
			),
		)
		segment_id = data.draw(st.sampled_from((*live, next_id)))
		if operation == "prepare":
			originals = tuple(data.draw(st.lists(st.integers(0, 5), max_size=size + 2)))
			reserved = {wire for segment in live.values() for wire in segment.span}
			ordinary = len(originals)
			start = first_free_run(cursor, ordinary + marker, minimum, maximum, reserved)
			if start is None:
				ordinary = 0
				start = first_free_run(cursor, marker, minimum, maximum, reserved)
			context = models.PlaybackContext(source_id, next_id)
			if start is None:
				# Only a marker can miss; DRAIN never raises. Nothing changes: the model stays valid.
				assert marker
				with pytest.raises(env.module.IndexSpaceExhausted):
					ledger.prepare(context, originals)
				continue
			allocation = ledger.prepare(context, originals)
			span = range(start, start + ordinary + marker)
			assert allocation.wire_indexes == tuple(span[:ordinary])
			assert allocation.end_index == (span[-1] if marker else None)
			assert minimum <= span.start and span.stop - 1 <= maximum
			assert reserved.isdisjoint(span)
			cursor = span.stop if span.stop <= maximum else minimum
			live[next_id] = SimpleNamespace(
				id=next_id,
				originals=originals,
				wires=allocation.wire_indexes,
				end=allocation.end_index,
				span=span,
				position=0,
				reported=[],
				end_seen=False,
				drain_seen=False,
				failed=False,
			)
			next_id += 1
		elif operation == "index":
			receive(data.draw(st.integers(minimum - 1, maximum + 1)))
		elif operation == "drain":
			drain(segment_id)
		elif operation == "fail":
			event = models.PlaybackEvent(kinds.SEGMENT_FAILED, source_id, segment_id=segment_id)
			events = ledger.receive_segment_event(event, binding_token=token)
			segment = live.get(segment_id)
			if segment is None or finished(segment):
				assert events == ()
			else:
				assert events == (event,)
				segment.failed = True
		elif operation == "retire":
			ledger.retire_segment(models.PlaybackContext(source_id, segment_id))
			live.pop(segment_id, None)
		elif operation == "retire_source":
			ledger.retire_source(source_id)
			live.clear()
		else:
			ledger.unbind(source_id)
			token = ledger.bind(source, source_id, contract)
			live.clear()
	# Completing every live segment reports all of its originals, degraded or not.
	for segment in tuple(live.values()):
		if segment.failed:
			continue
		if marker and not segment.end_seen:
			receive(segment.end)
		if mode != "END_INDEX" and not segment.drain_seen:
			drain(segment.id)
		assert segment.reported == list(dict.fromkeys(segment.originals))
	ledger.close()


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
	mode=st.sampled_from(PROPERTY_MODES),
	minimum=st.integers(1, 20),
	size=st.integers(1, 12),
	counts=st.lists(st.integers(0, 12), min_size=1, max_size=40),
)
def test_property_retired_segments_never_run_the_range_out(env, mode, minimum, size, counts):
	models = env.models
	marker = int(mode != "DRAIN")
	ledger = env.module.IndexLedger()
	source_id = object()
	contract = models.CompletionContract(
		getattr(models.CompletionMode, mode),
		models.IndexRange(minimum, minimum + size - 1),
	)
	ledger.bind(object(), source_id, contract)
	for segment_id, count in enumerate(counts, 1):
		originals = tuple(range(min(count, size - marker)))
		context = models.PlaybackContext(source_id, segment_id)
		allocation = ledger.prepare(context, originals)
		assert len(allocation.wire_indexes) == len(originals)
		assert (allocation.end_index is not None) == bool(marker)
		ledger.retire_segment(context)
	ledger.close()
