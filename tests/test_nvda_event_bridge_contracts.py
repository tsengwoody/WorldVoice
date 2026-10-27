"""The event bridge refuses calls that break its lifecycle or binding contract, and cleans up after failures."""

import importlib
import sys
from types import SimpleNamespace

import pytest
from addon_loader import alias_package, load_source
from runtime_harness import RUNTIME


class Action:
	"""An NVDA extension point whose register and unregister can be made to fail."""

	def __init__(self):
		self.handlers = []
		self.register_error = None
		self.unregister_error = None

	def register(self, handler):
		self.handlers.append(handler)
		if self.register_error is not None:
			raise self.register_error

	def unregister(self, handler):
		self.handlers.remove(handler)
		if self.unregister_error is not None:
			raise self.unregister_error

	def notify(self, **kwargs):
		for handler in tuple(self.handlers):
			handler(**kwargs)


@pytest.fixture
def env(monkeypatch, rt):
	name = "worldvoice_bridge_contract_test"
	alias_package(monkeypatch, name, RUNTIME.parent)
	monkeypatch.setitem(sys.modules, f"{name}.runtime", rt.package)
	monkeypatch.setitem(sys.modules, f"{name}.runtime.models", rt.models)
	monkeypatch.delitem(sys.modules, f"{name}.bridge.indexLedger", raising=False)
	ledger_module = importlib.import_module(f"{name}.bridge.indexLedger")
	module = load_source(monkeypatch, f"{name}.bridge.nvdaEvents", RUNTIME.parent / "bridge/nvdaEvents.py")
	models = rt.models
	env = SimpleNamespace(
		models=models,
		owner=object(),
		done=Action(),
		index=Action(),
		ledger=ledger_module.IndexLedger(),
		received=[],
		batches=[],
		marker=models.CompletionContract(models.CompletionMode.END_INDEX, models.IndexRange(501, 600)),
	)
	env.bridge = module.NvdaEventBridge(
		env.owner,
		done_event=env.done,
		index_event=env.index,
		get_synth=lambda: env.owner,
		index_ledger=env.ledger,
	)
	yield env
	env.done.unregister_error = env.index.unregister_error = None
	env.bridge.close()
	env.ledger.close()


def start(env):
	env.bridge.start(env.received.append, batch_handler=env.batches.append)


def test_a_bridge_starts_once_and_never_after_close(env):
	start(env)
	with pytest.raises(RuntimeError, match="already started"):
		start(env)
	env.bridge.close()
	with pytest.raises(RuntimeError, match="closed"):
		start(env)
	with pytest.raises(RuntimeError, match="closed"):
		env.bridge.bind(object(), object())


def test_a_failed_start_raises_its_own_error_chained_to_a_failed_cleanup(env):
	registration = RuntimeError("register failed")
	cleanup = RuntimeError("unregister failed")
	env.index.register_error = registration
	env.done.unregister_error = cleanup
	with pytest.raises(RuntimeError, match="register failed") as raised:
		start(env)
	assert raised.value is registration
	assert raised.value.__cause__ is cleanup
	# Cleanup still went on past the failure: the bridge is closed and holds no handler.
	assert env.index.handlers == []
	with pytest.raises(RuntimeError, match="closed"):
		start(env)


def test_rebinding_a_source_cannot_change_its_completion_contract(env):
	start(env)
	source, source_id = object(), object()
	env.bridge.bind(source, source_id)
	with pytest.raises(ValueError, match="completion contract"):
		env.bridge.bind(source, source_id, completion=env.marker)
	env.done.notify(synth=source)
	# The first binding is unchanged and still routes.
	assert [event.kind for event in env.received] == [env.models.EventKind.DONE]


def test_a_marker_source_id_belongs_to_one_source(env):
	start(env)
	first, second, source_id = object(), object(), object()
	env.bridge.bind(first, source_id, completion=env.marker)
	with pytest.raises(ValueError, match="already bound to another source"):
		env.bridge.bind(second, source_id, completion=env.marker)
	allocation = env.ledger.prepare(env.models.PlaybackContext(source_id, 3), ())
	env.index.notify(synth=second, index=allocation.endIndex)
	assert env.batches == []
	env.index.notify(synth=first, index=allocation.endIndex)
	assert [event.segment_id for event in env.batches[0]()] == [3]


def test_a_failed_ledger_bind_raises_its_own_error_chained_to_a_failed_revoke(env, monkeypatch):
	start(env)
	bind_error, revoke_error = RuntimeError("bind failed"), RuntimeError("revoke failed")

	def fail_bind(*args):
		raise bind_error

	def fail_unbind(source_id):
		raise revoke_error

	monkeypatch.setattr(env.ledger, "bind", fail_bind)
	monkeypatch.setattr(env.ledger, "unbind", fail_unbind)
	source = object()
	with pytest.raises(RuntimeError, match="bind failed") as raised:
		env.bridge.bind(source, object(), completion=env.marker)
	assert raised.value.__cause__ is revoke_error
	# Nothing was bound: the source's indexes reach no one.
	env.index.notify(synth=source, index=501)
	assert env.batches == []


def test_unbinding_an_unknown_source_id_changes_nothing(env):
	start(env)
	source, source_id = object(), object()
	env.bridge.bind(source, source_id)
	env.bridge.unbind(object())
	env.done.notify(synth=source)
	assert [event.source_id for event in env.received] == [source_id]


def test_close_raises_the_first_cleanup_error_after_trying_every_step(env):
	start(env)
	done_error, index_error = RuntimeError("done"), RuntimeError("index")
	env.done.unregister_error, env.index.unregister_error = done_error, index_error
	with pytest.raises(RuntimeError) as raised:
		env.bridge.close()
	assert raised.value is done_error
	assert env.done.handlers == env.index.handlers == []


def test_close_raises_a_ledger_revoke_error_when_unregistering_succeeded(env, monkeypatch):
	start(env)
	source_id = object()
	env.bridge.bind(object(), source_id, completion=env.marker)
	revoke_error = RuntimeError("revoke failed")
	unbind = env.ledger.unbind

	def fail_after_unbind(bound_id):
		unbind(bound_id)
		raise revoke_error

	monkeypatch.setattr(env.ledger, "unbind", fail_after_unbind)
	with pytest.raises(RuntimeError) as raised:
		env.bridge.close()
	assert raised.value is revoke_error
	assert env.done.handlers == env.index.handlers == []
