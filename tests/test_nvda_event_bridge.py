import gc
import importlib
import sys
import weakref
from threading import Event, Thread
from types import SimpleNamespace

import pytest
from addon_loader import alias_package, load_source
from runtime_harness import RUNTIME
from waiting import HOLD_TIMEOUT, WAIT_TIMEOUT


class EventStub:
	def __init__(self):
		self.handlers = []
		self.notifications = []
		self.on_register = None
		self.on_unregister = None
		self.on_notify = None

	def register(self, handler):
		self.handlers.append(handler)
		if self.on_register:
			self.on_register(handler)

	def unregister(self, handler):
		if self.on_unregister:
			self.on_unregister(handler)
		self.handlers.remove(handler)

	def notify(self, **kwargs):
		self.notifications.append(kwargs)
		if self.on_notify:
			self.on_notify(**kwargs)
		for handler in tuple(self.handlers):
			handler(**kwargs)


@pytest.fixture
def env(monkeypatch, rt):
	name = "worldvoice_bridge_test"
	alias_package(monkeypatch, name, RUNTIME.parent)
	monkeypatch.setitem(sys.modules, f"{name}.runtime", rt.package)
	monkeypatch.setitem(sys.modules, f"{name}.runtime.models", rt.models)
	monkeypatch.delitem(sys.modules, f"{name}.bridge.indexLedger", raising=False)
	ledger_module = importlib.import_module(f"{name}.bridge.indexLedger")
	module = load_source(monkeypatch, f"{name}.bridge.nvdaEvents", RUNTIME.parent / "bridge/nvdaEvents.py")
	owner = object()
	env = SimpleNamespace(
		owner=owner,
		current=owner,
		done=EventStub(),
		index=EventStub(),
		received=[],
		models=rt.models,
		module=module,
		ledger_module=ledger_module,
	)
	env.bridge = module.NvdaEventBridge(
		owner,
		done_event=env.done,
		index_event=env.index,
		get_synth=lambda: env.current,
	)
	yield env
	env.done.on_unregister = env.index.on_unregister = None
	env.bridge.close()


def test_routes_bound_source_index_and_done(env):
	source, source_id = object(), object()
	env.bridge.bind(source, source_id)
	env.bridge.start(env.received.append)
	env.index.notify(synth=source, index=7)
	env.done.notify(synth=source)
	assert [(event.kind, event.index) for event in env.received] == [
		(env.models.EventKind.INDEX, 7),
		(env.models.EventKind.DONE, None),
	]
	assert all(event.source_id is source_id for event in env.received)


def test_unknown_and_owner_sources_are_ignored(env):
	env.bridge.bind(env.owner, object())
	env.bridge.start(env.received.append)
	for source in (object(), env.owner):
		env.index.notify(synth=source, index=7)
		env.done.notify(synth=source)
	assert env.received == []


class EqualSource:
	def __eq__(self, other):
		return isinstance(other, EqualSource)


def test_equal_but_distinct_sources_route_by_identity(env):
	first, second, unknown = EqualSource(), EqualSource(), EqualSource()
	first_id, second_id = object(), object()
	env.bridge.bind(first, first_id)
	env.bridge.bind(second, second_id)
	env.bridge.start(env.received.append)
	for source in (first, second, unknown):
		env.done.notify(synth=source)
	assert len(env.received) == 2
	assert env.received[0].source_id is first_id
	assert env.received[1].source_id is second_id


def test_rebinding_source_to_different_id_is_rejected(env):
	source, source_id = object(), object()
	env.bridge.bind(source, source_id)
	env.bridge.bind(source, source_id)
	with pytest.raises(ValueError):
		env.bridge.bind(source, object())
	env.bridge.start(env.received.append)
	env.done.notify(synth=source)
	assert env.received[0].source_id is source_id


def test_unbind_compares_source_id_by_identity(env):
	source, source_id = object(), EqualSource()
	env.bridge.bind(source, source_id)
	env.bridge.start(env.received.append)
	env.bridge.unbind(EqualSource())
	env.done.notify(synth=source)
	env.bridge.unbind(source_id)
	env.bridge.unbind(source_id)
	env.done.notify(synth=source)
	assert len(env.received) == 1
	assert env.received[0].source_id is source_id


@pytest.mark.parametrize("release", ["unbind", "close"])
def test_binding_keeps_source_alive_until_released(env, release):
	source, source_id = EqualSource(), object()
	reference = weakref.ref(source)
	env.bridge.bind(source, source_id)
	del source
	gc.collect()
	assert reference() is not None
	if release == "unbind":
		env.bridge.unbind(source_id)
	else:
		env.bridge.close()
	gc.collect()
	assert reference() is None


@pytest.mark.parametrize("failing_event", ["done", "index"])
def test_partial_registration_is_undone(env, failing_event):
	def fail_after_registration(handler):
		raise RuntimeError("registration failed after adding handler")

	getattr(env, failing_event).on_register = fail_after_registration
	with pytest.raises(RuntimeError, match="registration failed"):
		env.bridge.start(env.received.append)
	assert env.done.handlers == []
	assert env.index.handlers == []
	env.bridge.done_speaking()
	env.bridge.index_reached(7)
	assert env.done.notifications == env.index.notifications == []


def test_close_continues_after_unregister_error_and_disables_retained_handler(env):
	source = EqualSource()
	reference = weakref.ref(source)
	env.bridge.bind(source, object())
	env.bridge.start(env.received.append)

	def fail(handler):
		raise RuntimeError("unregister failed")

	env.done.on_unregister = fail
	with pytest.raises(RuntimeError, match="unregister failed"):
		env.bridge.close()
	assert env.index.handlers == []
	env.done.notify(synth=source)
	assert env.received == []
	env.done.notifications.clear()
	del source
	gc.collect()
	assert reference() is None
	env.bridge.close()


def test_close_ignores_late_callbacks(env):
	source = object()
	env.bridge.bind(source, object())
	env.bridge.start(env.received.append)
	done, index = env.done.handlers[0], env.index.handlers[0]
	env.done.on_unregister = lambda handler: handler(synth=source)
	env.index.on_unregister = lambda handler: handler(synth=source, index=7)
	env.bridge.close()
	env.bridge.close()
	done(synth=source)
	index(synth=source, index=7)
	env.bridge.done_speaking()
	env.bridge.index_reached(7)
	assert env.received == []
	assert env.done.handlers == env.index.handlers == []
	assert env.done.notifications == env.index.notifications == []


def test_public_output_uses_only_owner_and_index_without_looping(env):
	env.bridge.bind(env.owner, object())
	env.bridge.start(env.received.append)
	env.bridge.index_reached(7)
	env.bridge.done_speaking()
	assert env.index.notifications == [{"synth": env.owner, "index": 7}]
	assert env.done.notifications == [{"synth": env.owner}]
	assert env.received == []


def test_owner_change_suppresses_output(env):
	env.bridge.start(env.received.append)
	env.current = object()
	env.bridge.index_reached(7)
	env.bridge.done_speaking()
	assert env.done.notifications == env.index.notifications == []
	env.current = env.owner
	env.bridge.done_speaking()
	assert env.done.notifications == [{"synth": env.owner}]


def assert_other_thread_can_unbind(bridge, source_id):
	worker = Thread(target=bridge.unbind, args=(source_id,), daemon=True)
	worker.start()
	worker.join(WAIT_TIMEOUT)
	assert not worker.is_alive(), "bridge state lock held during external call"


def test_input_handler_runs_without_bridge_state_lock(env):
	source, source_id = object(), object()
	env.bridge.bind(source, source_id)

	def receive(event):
		assert_other_thread_can_unbind(env.bridge, source_id)
		env.received.append(event)

	env.bridge.start(receive)
	env.done.notify(synth=source)
	env.done.notify(synth=source)
	assert len(env.received) == 1


@pytest.mark.parametrize("output", ["index", "done"])
def test_public_output_runs_without_bridge_state_lock(env, output):
	source_id = object()
	env.bridge.bind(object(), source_id)
	env.bridge.start(env.received.append)
	getattr(env, output).on_notify = lambda **kwargs: assert_other_thread_can_unbind(env.bridge, source_id)
	if output == "index":
		env.bridge.index_reached(7)
		assert env.index.notifications == [{"synth": env.owner, "index": 7}]
	else:
		env.bridge.done_speaking()
		assert env.done.notifications == [{"synth": env.owner}]


@pytest.fixture
def marker_env(env):
	env.ledger = env.ledger_module.IndexLedger()
	env.contract = env.models.CompletionContract(
		env.models.CompletionMode.END_INDEX,
		env.models.IndexRange(501, 600),
	)
	env.source, env.source_id = object(), object()
	env.context = env.models.PlaybackContext(env.source_id, 9)
	env.suppliers = []
	yield env
	env.ledger.close()


def marker_setup(env):
	env.bridge = env.module.NvdaEventBridge(
		env.owner,
		done_event=env.done,
		index_event=env.index,
		get_synth=lambda: env.current,
		index_ledger=env.ledger,
	)
	return env


def start_marker(env, batch_handler=None):
	env.bridge.start(
		env.received.append,
		batch_handler=(env.suppliers.append if batch_handler is None else batch_handler),
	)
	env.bridge.bind(env.source, env.source_id, completion=env.contract)
	return env.ledger.prepare(env.context, (42, 7))


def test_marker_decodes_to_segment_events(marker_env):
	env = marker_setup(marker_env)
	allocation = start_marker(env, lambda load: env.received.extend(load()))
	env.index.notify(synth=env.source, index=allocation.endIndex)
	assert [(e.kind, e.index, e.segment_id) for e in env.received] == [
		(env.models.EventKind.INDEX, 42, 9),
		(env.models.EventKind.INDEX, 7, 9),
		(env.models.EventKind.SEGMENT_END, None, 9),
	]
	assert all(e.source_id is env.source_id for e in env.received)


def test_marker_mode_ignores_unidentified_done(marker_env):
	env = marker_setup(marker_env)
	env.contract = env.models.CompletionContract(
		env.models.CompletionMode.END_INDEX,
		env.models.IndexRange(501, 600),
	)
	start_marker(env)
	env.done.notify(synth=env.source)
	assert env.received == env.suppliers == []


def test_marker_batch_is_decoded_when_consumer_serializes_it(marker_env):
	env = marker_setup(marker_env)
	allocation = start_marker(env)
	env.bridge._on_index(env.source, allocation.endIndex)
	assert len(env.suppliers) == 1 and env.received == []
	events = env.suppliers[0]()
	assert [e.index for e in events] == [42, 7, None]
	assert events[-1].kind is env.models.EventKind.SEGMENT_END
	assert events[-1].segment_id == env.context.segment_id
	assert env.suppliers[0]() == ()


@pytest.mark.parametrize("release", ["unbind", "close", "rebind"])
def test_delayed_supplier_ignores_revoked_binding(marker_env, release):
	env = marker_setup(marker_env)
	allocation = start_marker(env)
	env.index.notify(synth=env.source, index=allocation.endIndex)
	if release == "close":
		env.bridge.close()
	else:
		env.bridge.unbind(env.source_id)
		if release == "rebind":
			env.bridge.bind(env.source, env.source_id, completion=env.contract)
	assert env.suppliers[0]() == ()
	assert env.ledger.receiveIndex(env.source_id, allocation.endIndex) == ()


def test_marker_rebind_preserves_high_water_and_rejects_stale_index(marker_env):
	env = marker_setup(marker_env)
	allocation = start_marker(env)
	env.bridge.unbind(env.source_id)
	with pytest.raises(env.ledger_module.InvalidIndexContext):
		env.ledger.prepare(env.context, ())
	env.bridge.bind(env.source, env.source_id, completion=env.contract)
	next_allocation = env.ledger.prepare(env.context, ())
	assert next_allocation.endIndex == 504
	env.index.notify(synth=env.source, index=allocation.endIndex)
	env.index.notify(synth=env.source, index=next_allocation.endIndex)
	assert env.suppliers[0]() == ()
	assert [e.segment_id for e in env.suppliers[1]()] == [9]


def test_marker_duplicate_bind_keeps_pending_mapping(marker_env):
	env = marker_setup(marker_env)
	allocation = start_marker(env)
	env.bridge.bind(env.source, env.source_id, completion=env.contract)
	env.index.notify(synth=env.source, index=allocation.endIndex)
	assert [e.index for e in env.suppliers[0]()] == [42, 7, None]


@pytest.mark.parametrize("missing", ["ledger", "batch_handler"])
def test_marker_binding_requires_ledger_and_batch_handler(marker_env, missing):
	env = marker_setup(marker_env)
	if missing == "ledger":
		env.bridge = env.module.NvdaEventBridge(
			env.owner,
			done_event=env.done,
			index_event=env.index,
			get_synth=lambda: env.current,
		)
	env.bridge.start(
		env.received.append,
		batch_handler=(None if missing == "batch_handler" else env.suppliers.append),
	)
	with pytest.raises(ValueError):
		env.bridge.bind(env.source, env.source_id, completion=env.contract)
	env.index.notify(synth=env.source, index=501)
	assert env.received == env.suppliers == []


def test_marker_batch_handler_runs_without_bridge_state_lock(marker_env):
	env = marker_setup(marker_env)

	def receive(load):
		assert_other_thread_can_unbind(env.bridge, env.source_id)
		assert load() == ()

	allocation = start_marker(env, receive)
	env.index.notify(synth=env.source, index=allocation.endIndex)


def test_marker_supplier_decodes_without_bridge_state_lock(marker_env, monkeypatch):
	env = marker_setup(marker_env)
	allocation = start_marker(env)
	receive_index = env.ledger.receiveIndex

	def receive(source_id, index, **kwargs):
		assert_other_thread_can_unbind(env.bridge, source_id)
		return receive_index(source_id, index, **kwargs)

	monkeypatch.setattr(env.ledger, "receiveIndex", receive)
	env.index.notify(synth=env.source, index=allocation.endIndex)
	assert env.suppliers[0]() == ()


def test_partial_marker_bind_revokes_ledger_binding(marker_env, monkeypatch):
	env = marker_setup(marker_env)
	env.bridge.start(env.received.append, batch_handler=env.suppliers.append)
	bind = env.ledger.bind

	def fail_after_binding(*args):
		bind(*args)
		raise RuntimeError("bind failed after registration")

	monkeypatch.setattr(env.ledger, "bind", fail_after_binding)
	with pytest.raises(RuntimeError, match="bind failed"):
		env.bridge.bind(env.source, env.source_id, completion=env.contract)
	with pytest.raises(env.ledger_module.InvalidIndexContext):
		env.ledger.prepare(env.context, ())
	env.index.notify(synth=env.source, index=501)
	assert env.received == env.suppliers == []


def test_close_continues_revoking_markers_after_cleanup_failures(marker_env, monkeypatch):
	env = marker_setup(marker_env)
	start_marker(env)
	second_id = object()
	env.bridge.bind(object(), second_id, completion=env.contract)
	second_context = env.models.PlaybackContext(second_id, 1)
	env.ledger.prepare(second_context, ())
	unbind = env.ledger.unbind

	def fail_first(source_id):
		unbind(source_id)
		if source_id is env.source_id:
			raise RuntimeError("ledger unbind failed")

	monkeypatch.setattr(env.ledger, "unbind", fail_first)

	def fail_unregister(handler):
		raise RuntimeError("unregister failed")

	env.done.on_unregister = fail_unregister
	with pytest.raises(RuntimeError):
		env.bridge.close()
	assert env.index.handlers == []
	for context in (env.context, second_context):
		with pytest.raises(env.ledger_module.InvalidIndexContext):
			env.ledger.prepare(context, ())
	env.index.notify(synth=env.source, index=503)
	assert env.suppliers == []
	env.bridge.close()


def test_supplier_cannot_decode_replacement_binding_after_validation(marker_env, monkeypatch):
	env = marker_setup(marker_env)
	allocation = start_marker(env)
	env.index.notify(synth=env.source, index=allocation.endIndex)
	entered_decode, resume_decode = Event(), Event()
	receive_index = env.ledger.receiveIndex
	batches = []

	def paused_receive(source_id, index, **kwargs):
		entered_decode.set()
		assert resume_decode.wait(HOLD_TIMEOUT), "replacement binding was not published"
		return receive_index(source_id, index, **kwargs)

	monkeypatch.setattr(env.ledger, "receiveIndex", paused_receive)
	worker = Thread(target=lambda: batches.append(env.suppliers[0]()), daemon=True)
	worker.start()
	try:
		assert entered_decode.wait(WAIT_TIMEOUT), "supplier did not reach ledger decode"
		env.bridge.unbind(env.source_id)
		replacement = object()
		env.bridge.bind(replacement, env.source_id, completion=env.contract)
		replacement_context = env.models.PlaybackContext(env.source_id, 10)
		replacement_allocation = env.ledger.prepare(replacement_context, (80, 81))
		assert replacement_allocation.endIndex == allocation.endIndex
	finally:
		resume_decode.set()
		worker.join(WAIT_TIMEOUT)
	assert not worker.is_alive()
	assert batches == [()]
	monkeypatch.setattr(env.ledger, "receiveIndex", receive_index)
	env.index.notify(synth=replacement, index=replacement_allocation.endIndex)
	events = env.suppliers[1]()
	assert [(e.index, e.segment_id) for e in events] == [(80, 10), (81, 10), (None, 10)]


@pytest.fixture
def drain_env(marker_env):
	env = marker_setup(marker_env)
	env.contract = env.models.CompletionContract(
		env.models.CompletionMode.DRAIN,
		env.models.IndexRange(1, 9999),
	)
	start_marker(env)
	return env


def segment_event(env, kind="SEGMENT_DRAINED", *, source_id=None, segment_id=None, error=None):
	return env.models.PlaybackEvent(
		getattr(env.models.EventKind, kind),
		env.source_id if source_id is None else source_id,
		segment_id=env.context.segment_id if segment_id is None else segment_id,
		error=error,
	)


def test_segment_sink_decodes_only_inside_batch_supplier(drain_env):
	env = drain_env
	sink = env.bridge.segment_sink(env.source, env.context)
	sink(segment_event(env))
	assert env.received == []
	assert len(env.suppliers) == 1
	assert [(e.kind.name, e.index, e.segment_id) for e in env.suppliers[0]()] == [
		("INDEX", 42, 9),
		("INDEX", 7, 9),
		("SEGMENT_DRAINED", None, 9),
	]
	assert env.suppliers[0]() == ()


@pytest.mark.parametrize("mismatch", ["source", "segment", "done", "end", "index"])
def test_segment_sink_rejects_unrelated_events(drain_env, mismatch):
	env = drain_env
	sink = env.bridge.segment_sink(env.source, env.context)
	event = (
		segment_event(env, source_id=object())
		if mismatch == "source"
		else (
			segment_event(env, segment_id=10)
			if mismatch == "segment"
			else segment_event(env, {"done": "DONE", "end": "SEGMENT_END", "index": "INDEX"}[mismatch])
		)
	)
	sink(event)
	assert env.suppliers == []
	sink(segment_event(env))
	assert env.suppliers[0]()[-1].kind is env.models.EventKind.SEGMENT_DRAINED


@pytest.mark.parametrize("invalid", ["unknown", "wrong_context", "owner", "legacy", "end_index"])
def test_segment_sink_requires_correlated_source_binding(drain_env, invalid):
	env = drain_env
	source, context = env.source, env.context
	if invalid == "unknown":
		source = object()
	elif invalid == "wrong_context":
		context = env.models.PlaybackContext(object(), 9)
	elif invalid == "owner":
		source = env.owner
		owner_id = object()
		env.bridge.bind(source, owner_id, completion=env.contract)
		context = env.models.PlaybackContext(owner_id, 9)
	elif invalid == "end_index":
		# Correlated, but completed by its end index: no drain event to sink.
		source, end_index_id = object(), object()
		env.bridge.bind(
			source,
			end_index_id,
			completion=env.models.CompletionContract(
				env.models.CompletionMode.END_INDEX,
				env.models.IndexRange(1, 9999),
			),
		)
		context = env.models.PlaybackContext(end_index_id, 9)
	else:
		env.bridge.unbind(env.source_id)
		env.bridge.bind(source, env.source_id)
	with pytest.raises(ValueError):
		env.bridge.segment_sink(source, context)


def test_segment_failure_does_not_restore_pending_indexes(drain_env):
	env = drain_env
	error = OSError("native failure")
	env.bridge.segment_sink(env.source, env.context)(segment_event(env, "SEGMENT_FAILED", error=error))
	events = env.suppliers[0]()
	assert len(events) == 1 and events[0].error is error
	assert env.ledger.receiveIndex(env.source_id, 1) == ()


def test_old_segment_sink_drops_after_rebind(drain_env):
	env = drain_env
	old_sink = env.bridge.segment_sink(env.source, env.context)
	env.bridge.unbind(env.source_id)
	env.bridge.bind(env.source, env.source_id, completion=env.contract)
	env.ledger.prepare(env.context, (80,))
	old_sink(segment_event(env))
	assert env.received == env.suppliers == []
	env.bridge.segment_sink(env.source, env.context)(segment_event(env))
	assert [e.index for e in env.suppliers[0]()] == [80, None]


@pytest.mark.parametrize("release", ["unbind", "rebind", "close"])
def test_delayed_segment_supplier_rechecks_binding(drain_env, release):
	env = drain_env
	env.bridge.segment_sink(env.source, env.context)(segment_event(env))
	if release == "close":
		env.bridge.close()
	else:
		env.bridge.unbind(env.source_id)
		if release == "rebind":
			env.bridge.bind(env.source, env.source_id, completion=env.contract)
			env.ledger.prepare(env.context, (80,))
	assert env.suppliers[0]() == ()


def test_segment_supplier_rechecks_ledger_token_after_bridge_validation(drain_env, monkeypatch):
	env = drain_env
	env.bridge.segment_sink(env.source, env.context)(segment_event(env))
	receive = env.ledger.receiveSegmentEvent

	def replace_binding(event, **kwargs):
		assert_other_thread_can_unbind(env.bridge, env.source_id)
		env.bridge.bind(env.source, env.source_id, completion=env.contract)
		env.ledger.prepare(env.context, (80,))
		return receive(event, **kwargs)

	monkeypatch.setattr(env.ledger, "receiveSegmentEvent", replace_binding)
	assert env.suppliers[0]() == ()


def test_segment_batch_stops_after_index_handler_unbinds(drain_env):
	env = drain_env

	def receive(load):
		for event in load():
			env.received.append(event)
			assert_other_thread_can_unbind(env.bridge, env.source_id)

	env.bridge._batch_handler = receive
	env.bridge.segment_sink(env.source, env.context)(segment_event(env))
	assert [(e.kind.name, e.index) for e in env.received] == [("INDEX", 42)]
