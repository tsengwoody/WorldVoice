"""Pin how each completion contract is interpreted by the scheduler and the adapter.

Written before the completion rule table replaced per-mode branches; every
row here records the behavior that refactor had to keep.
"""

from types import SimpleNamespace

import pytest
from legacy_adapter_harness import Core, legacy_class
from runtime_harness import FakePlayback, RecordingOutput, done_signalled, load_index_support, load_scheduler
from waiting import WAIT_TIMEOUT

CONTRACTS = ("plain", "END_INDEX", "END_INDEX_AND_DRAIN", "DRAIN")


def contract(rt, name):
	models = rt.models
	if name == "plain":
		return models.CompletionContract()
	return models.CompletionContract(getattr(models.CompletionMode, name), models.IndexRange(1, 1000))


@pytest.fixture
def scheduler(monkeypatch, rt):
	return load_scheduler(monkeypatch, rt)


@pytest.fixture
def manager(scheduler):
	manager = scheduler.TaskManager(RecordingOutput())
	yield manager
	manager.shutdown()


# Event steps: (kind, segment) where segment is "own", "none" or "other".
SCENARIOS = {
	"done_anonymous": [("DONE", "none")],
	"done_own": [("DONE", "own")],
	"end_own": [("SEGMENT_END", "own")],
	"drained_own": [("SEGMENT_DRAINED", "own")],
	"failed_own": [("SEGMENT_FAILED", "own")],
	"failed_anonymous": [("SEGMENT_FAILED", "none")],
	"end_then_drained": [("SEGMENT_END", "own"), ("SEGMENT_DRAINED", "own")],
	"drained_then_end": [("SEGMENT_DRAINED", "own"), ("SEGMENT_END", "own")],
	"other_segment": [("DONE", "other"), ("SEGMENT_END", "other"), ("SEGMENT_DRAINED", "other")],
}

# What the scheduler did with each scenario before the rule table existed.
OUTCOMES = {
	"plain": {
		"done_anonymous": "complete",
		"done_own": "pending",
		"end_own": "pending",
		"drained_own": "pending",
		"failed_own": "pending",
		"failed_anonymous": "pending",
		"end_then_drained": "pending",
		"drained_then_end": "pending",
		"other_segment": "pending",
	},
	"END_INDEX": {
		"done_anonymous": "pending",
		"done_own": "pending",
		"end_own": "complete",
		"drained_own": "pending",
		"failed_own": "failed",
		"failed_anonymous": "pending",
		"end_then_drained": "complete",
		"drained_then_end": "complete",
		"other_segment": "pending",
	},
	"END_INDEX_AND_DRAIN": {
		"done_anonymous": "pending",
		"done_own": "pending",
		"end_own": "pending",
		"drained_own": "pending",
		"failed_own": "failed",
		"failed_anonymous": "pending",
		"end_then_drained": "complete",
		"drained_then_end": "complete",
		"other_segment": "pending",
	},
	"DRAIN": {
		"done_anonymous": "pending",
		"done_own": "pending",
		"end_own": "pending",
		"drained_own": "complete",
		"failed_own": "failed",
		"failed_anonymous": "pending",
		"end_then_drained": "complete",
		"drained_then_end": "complete",
		"other_segment": "pending",
	},
}


def _segment_id(task, where):
	return {"own": task.segment_id, "none": None, "other": task.segment_id + 1}[where]


@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("name", CONTRACTS)
def test_scheduler_outcome_per_contract(manager, rt, name, scenario):
	port = FakePlayback(contract(rt, name))
	request = manager.new_request()
	future = manager.append_speech(request, port, "Fake:a", ("hello",))
	assert manager.submit_request(request)
	assert port.entered.wait(WAIT_TIMEOUT)
	task = request.tasks[0]
	error = OSError("segment failed")
	for kind, where in SCENARIOS[scenario]:
		manager.on_event(
			rt.models.PlaybackEvent(
				getattr(rt.models.EventKind, kind),
				port.source_id,
				segment_id=_segment_id(task, where),
				error=error,
			),
		)
	expected = OUTCOMES[name][scenario]
	if expected == "complete":
		assert future.result(WAIT_TIMEOUT) is True
	elif expected == "failed":
		assert future.exception(WAIT_TIMEOUT) is error
	else:
		# on_event signals the worker synchronously when the task is ready.
		assert not done_signalled(manager)
		assert not future.done()
		manager.cancel()


@pytest.mark.parametrize("name", ("END_INDEX_AND_DRAIN", "DRAIN"))
def test_scheduler_index_after_end_per_contract(manager, rt, name):
	# AND stops index delivery at END; DRAIN keeps delivering until drained.
	output = manager._output
	port = FakePlayback(contract(rt, name))
	request = manager.new_request()
	future = manager.append_speech(request, port, "Fake:a", ("hello",))
	assert manager.submit_request(request)
	assert port.entered.wait(WAIT_TIMEOUT)
	segment = request.tasks[0].segment_id
	events = rt.models.EventKind
	manager.on_event(rt.models.PlaybackEvent(events.SEGMENT_END, port.source_id, segment_id=segment))
	manager.on_event(rt.models.PlaybackEvent(events.INDEX, port.source_id, 7, segment))
	assert output.indexes == ([] if name == "END_INDEX_AND_DRAIN" else [7])
	manager.on_event(rt.models.PlaybackEvent(events.SEGMENT_DRAINED, port.source_id, segment_id=segment))
	assert future.result(WAIT_TIMEOUT) is True


class EntryCore(Core):
	"""Records which native entry the adapter chose."""

	def __init__(self):
		super().__init__()
		self.entries = []

	def speak(self, commands, **kwargs):
		self.entries.append(("speak", commands, tuple(sorted(kwargs))))

	def speak_segment(self, commands, token, *, context, on_event):
		self.entries.append(("speak_segment", commands, on_event))


@pytest.fixture
def adapter_env(monkeypatch, bridge_modules, rt, nvda_commands):
	support = load_index_support(monkeypatch, rt, "worldvoice_bridge_test")
	ledgers = []

	def make(name, *, ledger=True, segment_events=True):
		core = EntryCore()
		cls = legacy_class(core)
		index_ledger = support.ledger.IndexLedger() if ledger else None
		adapter = bridge_modules.adapter.LegacyEngineAdapter(
			cls,
			lambda key: cls(),
			index_ledger=index_ledger,
		)
		adapter.open()
		chosen = contract(rt, name)
		adapter.configure_completion(chosen)
		source_id = object()
		if index_ledger is not None:
			ledgers.append((adapter, index_ledger))
			if chosen.mode is not rt.models.CompletionMode.LEGACY_DONE:
				index_ledger.bind(core, source_id, chosen)
		else:
			ledgers.append((adapter, None))
		sinks = SimpleNamespace(segment=lambda event: None)
		if segment_events and chosen.mode in (
			rt.models.CompletionMode.DRAIN,
			rt.models.CompletionMode.END_INDEX_AND_DRAIN,
		):
			adapter.configure_segment_events(lambda context: sinks.segment)
		return SimpleNamespace(
			adapter=adapter,
			core=core,
			sinks=sinks,
			context=rt.models.PlaybackContext(source_id, 1),
		)

	yield SimpleNamespace(
		make=make,
		commands=nvda_commands,
		token=SimpleNamespace(is_cancelled=lambda: False),
	)
	for adapter, ledger in ledgers:
		adapter.close()
		if ledger is not None:
			ledger.close()


# (native entry, markers encoded, event sink) per contract.
ENTRIES = {
	"plain": ("speak", False, None),
	"END_INDEX": ("speak", True, None),
	"END_INDEX_AND_DRAIN": ("speak_segment", True, "segment"),
	"DRAIN": ("speak_segment", True, "segment"),
}


@pytest.mark.parametrize("name", CONTRACTS)
def test_adapter_entry_per_contract(adapter_env, name):
	env = adapter_env.make(name)
	original = adapter_env.commands.IndexCommand(123)
	context = None if name == "plain" else env.context
	env.adapter.speak(("hello", original), adapter_env.token, context=context)
	entry, encoded, sink = ENTRIES[name]
	assert len(env.core.entries) == 1
	called, commands, extra = env.core.entries[0]
	assert called == entry
	indexes = [c.index for c in commands if isinstance(c, adapter_env.commands.IndexCommand)]
	assert (indexes != [123]) is encoded
	if sink is not None:
		assert extra is getattr(env.sinks, sink)
	else:
		assert extra == ()


@pytest.mark.parametrize(
	"name,missing,error,message",
	[
		("END_INDEX", "context", ValueError, "Correlated completion requires a playback context"),
		("DRAIN", "context", ValueError, "Correlated completion requires a playback context"),
		("END_INDEX", "ledger", ValueError, "Marker completion requires an index ledger"),
		("DRAIN", "segment_events", RuntimeError, "Drain completion requires a segment event factory"),
		(
			"END_INDEX_AND_DRAIN",
			"segment_events",
			RuntimeError,
			"Drain completion requires a segment event factory",
		),
	],
)
def test_adapter_precondition_errors_per_contract(adapter_env, name, missing, error, message):
	env = adapter_env.make(name, ledger=missing != "ledger", segment_events=missing != "segment_events")
	context = None if missing == "context" else env.context
	with pytest.raises(error) as caught:
		env.adapter.speak(("hello",), adapter_env.token, context=context)
	assert str(caught.value) == message
	assert env.core.entries == []
