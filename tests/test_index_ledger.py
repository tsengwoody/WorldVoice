"""Source-scoped wire indexes cannot be reused or complete the wrong segment."""

import gc
import importlib
import sys
import weakref
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest
from addon_loader import alias_package
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


def test_exhaustion_is_atomic(env):
	ledger = env.module.IndexLedger()
	ledger.bind(
		env.source,
		env.source_id,
		env.models.CompletionContract(
			env.models.CompletionMode.END_INDEX,
			env.models.IndexRange(1, 3),
		),
	)
	allocation = ledger.prepare(env.context, (123,))
	assert (allocation.wire_indexes, allocation.end_index) == ((1,), 2)
	second = env.models.PlaybackContext(env.source_id, 2)
	with pytest.raises(env.module.IndexSpaceExhausted):
		ledger.prepare(second, (124,))
	assert ledger.receive_index(env.source_id, 3) == ()
	assert ledger.prepare(second, ()).end_index == 3
	ledger.close()


def test_duplicate_prepare_rejected_until_retired_even_after_end(env):
	env.ledger.prepare(env.context, ())
	with pytest.raises(env.module.InvalidIndexContext):
		env.ledger.prepare(env.context, ())
	env.ledger.receive_index(env.source_id, 501)
	with pytest.raises(env.module.InvalidIndexContext):
		env.ledger.prepare(env.context, ())
	env.ledger.retire_segment(env.context)
	assert env.ledger.prepare(env.context, ()).end_index == 502


def test_invalid_bindings_do_not_replace_valid_binding(env):
	with pytest.raises(env.module.InvalidIndexContext):
		env.ledger.bind(env.source, object(), env.contract)
	with pytest.raises(env.module.InvalidIndexContext):
		env.ledger.bind(object(), env.source_id, env.contract)
	with pytest.raises(env.module.InvalidIndexContext):
		env.ledger.prepare(env.models.PlaybackContext(object(), 1), ())
	assert env.ledger.prepare(env.context, ()).end_index == 501


@pytest.mark.parametrize("mode,bounds", [("END_INDEX", (1, 100)), ("END_INDEX_AND_DRAIN", (501, 510))])
def test_rebind_rejects_changed_contract(env, mode, bounds):
	env.ledger.unbind(env.source_id)
	changed = env.models.CompletionContract(
		getattr(env.models.CompletionMode, mode),
		env.models.IndexRange(*bounds),
	)
	with pytest.raises(env.module.InvalidIndexContext):
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
	with pytest.raises(env.module.InvalidIndexContext):
		env.ledger.bind(object(), object(), env.contract)
	with pytest.raises(env.module.InvalidIndexContext):
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


def test_drain_uses_both_range_endpoints_and_empty_works_after_exhaustion(drain_env):
	env = drain_env
	allocation = env.ledger.prepare(env.context, tuple(range(9999)))
	assert len(allocation.wire_indexes) == 9999
	assert allocation.wire_indexes[0] == 1
	assert allocation.wire_indexes[-1] == 9999
	assert allocation.end_index is None
	empty = env.models.PlaybackContext(env.source_id, 2)
	assert env.ledger.prepare(empty, ()).wire_indexes == ()
	assert env.ledger.prepare(env.models.PlaybackContext(env.source_id, 3), ()).end_index is None
	exhausted = env.models.PlaybackContext(env.source_id, 4)
	with pytest.raises(env.module.IndexSpaceExhausted):
		env.ledger.prepare(exhausted, (42,))
	event = env.models.PlaybackEvent(
		env.models.EventKind.SEGMENT_DRAINED,
		env.source_id,
		segment_id=2,
	)
	assert env.ledger.receive_segment_event(event, binding_token=env.token) == (event,)


def test_drain_exhaustion_does_not_partially_publish_or_consume_indexes(drain_env):
	env = drain_env
	env.ledger.prepare(env.context, tuple(range(9998)))
	next_context = env.models.PlaybackContext(env.source_id, 2)
	with pytest.raises(env.module.IndexSpaceExhausted):
		env.ledger.prepare(next_context, (123, 124))
	assert env.ledger.receive_index(env.source_id, 9999) == ()
	event = env.models.PlaybackEvent(
		env.models.EventKind.SEGMENT_DRAINED,
		env.source_id,
		segment_id=2,
	)
	assert env.ledger.receive_segment_event(event, binding_token=env.token) == ()
	assert env.ledger.prepare(next_context, (123,)).wire_indexes == (9999,)
	assert [e.index for e in env.ledger.receive_segment_event(event, binding_token=env.token)] == [123, None]


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
