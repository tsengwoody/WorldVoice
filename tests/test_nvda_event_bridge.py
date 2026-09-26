import gc
import importlib.util
import sys
from threading import Thread
from types import ModuleType, SimpleNamespace
import weakref

import pytest

from runtime_harness import RUNTIME, rt


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
    package = ModuleType(name)
    package.__path__ = [str(RUNTIME.parent)]
    monkeypatch.setitem(sys.modules, name, package)
    monkeypatch.setitem(sys.modules, f"{name}.runtime", rt.package)
    monkeypatch.setitem(sys.modules, f"{name}.runtime.models", rt.models)
    spec = importlib.util.spec_from_file_location(
        f"{name}.nvdaEventBridge", RUNTIME.parent / "nvdaEventBridge.py",
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    owner = object()
    env = SimpleNamespace(owner=owner, current=owner, done=EventStub(), index=EventStub(),
                          received=[], models=rt.models)
    env.bridge = module.NvdaEventBridge(
        owner, done_event=env.done, index_event=env.index, get_synth=lambda: env.current,
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
        (env.models.EventKind.INDEX, 7), (env.models.EventKind.DONE, None),
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


def test_same_source_event_has_no_invented_request_id(env):
    source, source_id = object(), object()
    env.bridge.bind(source, source_id)
    env.bridge.start(env.received.append)
    env.done.notify(synth=source)
    env.done.notify(synth=source)
    assert len(env.received) == 2
    for event in env.received:
        assert vars(event) == {"kind": env.models.EventKind.DONE, "source_id": source_id, "index": None}


def assert_other_thread_can_unbind(bridge, source_id):
    worker = Thread(target=bridge.unbind, args=(source_id,), daemon=True)
    worker.start()
    worker.join(2)
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
