"""Source-scoped wire indexes cannot be reused or complete the wrong segment."""

from dataclasses import FrozenInstanceError
import gc
import importlib
import sys
from types import ModuleType, SimpleNamespace
import weakref

import pytest

from runtime_harness import RUNTIME, forbid_legacy_runtime_imports, rt


@pytest.fixture
def env(monkeypatch, rt):
    name = "worldvoice_ledger_test"
    package = ModuleType(name)
    package.__path__ = [str(RUNTIME.parent)]
    monkeypatch.setitem(sys.modules, name, package)
    monkeypatch.setitem(sys.modules, name + ".runtime", rt.package)
    monkeypatch.setitem(sys.modules, name + ".runtime.models", rt.models)
    monkeypatch.delitem(sys.modules, name + ".indexLedger", raising=False)
    with forbid_legacy_runtime_imports(monkeypatch):
        module = importlib.import_module(name + ".indexLedger")
    ledger = module.IndexLedger()
    source, source_id = object(), object()
    contract = rt.models.CompletionContract(
        rt.models.CompletionMode.END_INDEX, rt.models.IndexRange(501, 510),
    )
    ledger.bind(source, source_id, contract)
    yield SimpleNamespace(ledger=ledger, source=source, source_id=source_id,
                          contract=contract, module=module, models=rt.models,
                          context=rt.models.PlaybackContext(source_id, 1))
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
    ledger.bind(env.source, env.source_id, env.models.CompletionContract(
        env.models.CompletionMode.END_INDEX, env.models.IndexRange(1, 3)))
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
    changed = env.models.CompletionContract(getattr(env.models.CompletionMode, mode), env.models.IndexRange(*bounds))
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
            callback_blocked.append(not callback_finished.wait(1))

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
        allocations = tuple(pool.map(
            lambda segment_id: env.ledger.prepare(env.models.PlaybackContext(env.source_id, segment_id), (7,)),
            range(1, 6),
        ))
    assert sorted((a.wire_indexes, a.end_index) for a in allocations) == [
        ((501,), 502), ((503,), 504), ((505,), 506), ((507,), 508), ((509,), 510),
    ]


@pytest.mark.parametrize("same_source", [False, True])
def test_decode_binding_token_cannot_consume_replacement_segment(env, same_source):
    old_token = env.ledger.bind(env.source, env.source_id, env.contract)
    env.ledger.prepare(env.context, (42, 7))
    env.ledger.unbind(env.source_id)
    source = env.source if same_source else object()
    new_token = env.ledger.bind(source, env.source_id, env.contract)
    allocation = env.ledger.prepare(env.models.PlaybackContext(env.source_id, 2), (80, 81))
    assert env.ledger.receive_index(
        env.source_id, allocation.end_index, binding_token=old_token) == ()
    events = env.ledger.receive_index(env.source_id, allocation.end_index, binding_token=new_token)
    assert [(e.index, e.segment_id) for e in events] == [(80, 2), (81, 2), (None, 2)]


def test_duplicate_bind_token_still_decodes_existing_segment(env):
    token = env.ledger.bind(env.source, env.source_id, env.contract)
    allocation = env.ledger.prepare(env.context, (42,))
    env.ledger.bind(env.source, env.source_id, env.contract)
    events = env.ledger.receive_index(env.source_id, allocation.end_index, binding_token=token)
    assert [(e.index, e.segment_id) for e in events] == [(42, 1), (None, 1)]
