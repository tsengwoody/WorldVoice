"""Encode only at the playback boundary and retain caller command objects."""

import importlib
from types import SimpleNamespace

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from runtime_harness import load_index_support


@pytest.fixture
def codec_env(monkeypatch, rt, nvda_commands):
	support = load_index_support(monkeypatch, rt, "worldvoice_codec_test")
	contract = rt.models.CompletionContract(
		rt.models.CompletionMode.END_INDEX,
		rt.models.IndexRange(501, 510),
	)
	ledger = support.ledger.IndexLedger()
	source_id = object()
	ledger.bind(object(), source_id, contract)
	# Import inside tests so missing implementation is a clear red assertion.
	return SimpleNamespace(
		support=support,
		ledger=ledger,
		source_id=source_id,
		context=rt.models.PlaybackContext(source_id, 1),
		commands=nvda_commands,
		models=rt.models,
	)


def encode(env, commands):
	path = env.support.package + ".compat.indexCodec"
	assert importlib.util.find_spec(path) is not None, "Segment codec has not been implemented"
	return importlib.import_module(path).encode_segment(commands, env.context, env.ledger)


def test_codec_appends_one_marker_without_mutating_input(codec_env):
	env = codec_env
	original = env.commands.IndexCommand(123)
	other = object()
	commands = ["hello", original, other]
	encoded = encode(env, commands)
	assert isinstance(encoded, tuple)
	assert encoded is not commands
	assert len(encoded) == 4
	assert encoded[0] is commands[0]
	assert encoded[2] is other
	assert type(encoded[1]) is env.commands.IndexCommand
	assert encoded[1] is not original
	assert encoded[1].index == 501
	assert original.index == 123
	assert commands == ["hello", original, other]
	assert isinstance(encoded[-1], env.support.commands.WorldVoiceIndexCommand)
	assert encoded[-1].index == 502
	assert [event.index for event in env.ledger.receive_index(env.source_id, 502)] == [123, None]


def test_codec_rejects_preexisting_internal_marker(codec_env):
	env = codec_env
	marker = env.support.commands.WorldVoiceIndexCommand(123)
	with pytest.raises(ValueError):
		encode(env, ("hello", marker))
	assert env.ledger.prepare(env.context, ()).end_index == 501


def test_codec_scans_original_indexes_before_prepare(codec_env):
	env = codec_env
	original = env.commands.IndexCommand(123)
	original.index = "invalid"
	with pytest.raises((TypeError, ValueError)):
		encode(env, (original,))
	assert env.ledger.prepare(env.context, ()).end_index == 501


def test_codec_constructor_failure_retires_mapping(codec_env, monkeypatch):
	env = codec_env
	path = env.support.package + ".compat.indexCodec"
	assert importlib.util.find_spec(path) is not None, "Segment codec has not been implemented"
	module = importlib.import_module(path)

	def fail_marker(index):
		raise ValueError("constructor failed")

	monkeypatch.setattr(
		env.support.commands.WorldVoiceIndexCommand,
		"__init__",
		lambda self, index: fail_marker(index),
	)
	with pytest.raises(ValueError, match="constructor failed"):
		module.encode_segment((env.commands.IndexCommand(123),), env.context, env.ledger)
	assert env.ledger.receive_index(env.source_id, 501) == ()
	assert env.ledger.receive_index(env.source_id, 502) == ()
	assert env.ledger.prepare(env.context, ()).end_index == 503


@pytest.fixture
def drain_codec_env(codec_env):
	env = codec_env
	ledger = env.support.ledger.IndexLedger()
	source_id = object()
	contract = env.models.CompletionContract(
		env.models.CompletionMode.DRAIN,
		env.models.IndexRange(1, 9999),
	)
	token = ledger.bind(object(), source_id, contract)
	yield SimpleNamespace(
		support=env.support,
		ledger=ledger,
		source_id=source_id,
		context=env.models.PlaybackContext(source_id, 1),
		token=token,
		commands=env.commands,
		models=env.models,
	)
	ledger.close()


def test_drain_codec_rewrites_ordinary_indexes_without_terminal_or_input_mutation(drain_codec_env):
	env = drain_codec_env
	original, repeated = env.commands.IndexCommand(123), env.commands.IndexCommand(123)
	last = env.commands.IndexCommand(7)
	other = object()
	commands = ["hello", original, other, repeated, last]
	encoded = encode(env, commands)
	assert isinstance(encoded, tuple) and len(encoded) == 5
	assert encoded[0] is commands[0] and encoded[2] is other
	assert [encoded[i].index for i in (1, 3, 4)] == [1, 2, 3]
	assert all(type(encoded[i]) is env.commands.IndexCommand for i in (1, 3, 4))
	assert encoded[1] is not original and encoded[3] is not repeated
	assert [commands[i].index for i in (1, 3, 4)] == [123, 123, 7]
	assert commands == ["hello", original, other, repeated, last]
	event = env.models.PlaybackEvent(
		env.models.EventKind.SEGMENT_DRAINED,
		env.source_id,
		segment_id=1,
	)
	assert [e.index for e in env.ledger.receive_segment_event(event, binding_token=env.token)] == [
		123,
		7,
		None,
	]


def test_drain_codec_empty_input_does_not_construct_internal_marker(drain_codec_env, monkeypatch):
	env = drain_codec_env

	def fail_marker(self, index):
		raise AssertionError("DRAIN must not construct an internal marker")

	monkeypatch.setattr(env.support.commands.WorldVoiceIndexCommand, "__init__", fail_marker)
	assert encode(env, ()) == ()
	allocation = env.ledger.prepare(env.models.PlaybackContext(env.source_id, 2), (42,))
	assert allocation.wire_indexes == (1,) and allocation.end_index is None


def test_drain_codec_rejects_external_internal_command_before_allocation(drain_codec_env):
	env = drain_codec_env
	marker = env.support.commands.WorldVoiceIndexCommand(123)
	with pytest.raises(ValueError):
		encode(env, (env.commands.IndexCommand(7), marker))
	assert env.ledger.prepare(env.context, (7,)).wire_indexes == (1,)


def test_drain_codec_rejects_exhausted_segment_before_output(drain_codec_env):
	env = drain_codec_env
	env.ledger.prepare(env.models.PlaybackContext(env.source_id, 2), tuple(range(9999)))
	original = env.commands.IndexCommand(123)
	commands = ["hello", original]
	with pytest.raises(env.support.ledger.IndexSpaceExhausted):
		encode(env, commands)
	assert commands == ["hello", original] and original.index == 123
	assert encode(env, ()) == ()


# Fresh ledgers per example come from the support modules the function-scoped env loaded once.
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
	layout=st.lists(
		st.one_of(st.integers(-(2**31), 2**31), st.sampled_from(["text", "other"])),
		max_size=14,
	).filter(
		lambda items: sum(isinstance(item, int) for item in items) <= 9,
	),
	data=st.data(),
)
def test_property_encoding_keeps_commands_and_reports_each_index_once_in_order(codec_env, layout, data):
	env = codec_env
	ledger = env.support.ledger.IndexLedger()
	source_id = object()
	ledger.bind(
		object(),
		source_id,
		env.models.CompletionContract(env.models.CompletionMode.END_INDEX, env.models.IndexRange(501, 510)),
	)
	others = {}
	commands = []
	for item in layout:
		if isinstance(item, int):
			commands.append(env.commands.IndexCommand(item))
		else:
			commands.append(others.setdefault(len(commands), object() if item == "other" else item))
	snapshot = list(commands)
	encoded = importlib.import_module(env.support.package + ".compat.indexCodec").encode_segment(
		commands,
		env.models.PlaybackContext(source_id, 1),
		ledger,
	)
	assert commands == snapshot
	*body, marker = encoded
	assert isinstance(marker, env.support.commands.WorldVoiceIndexCommand)
	assert len(body) == len(commands)
	originals = [command.index for command in commands if isinstance(command, env.commands.IndexCommand)]
	wires = []
	for given_command, sent in zip(commands, body, strict=True):
		if isinstance(given_command, env.commands.IndexCommand):
			assert type(sent) is env.commands.IndexCommand and sent is not given_command
			wires.append(sent.index)
		else:
			assert sent is given_command
	assert wires == sorted(wires) and len(set(wires)) == len(wires)
	assert all(501 <= wire < marker.index <= 510 for wire in wires)
	# A wire index reports the originals up to it, the marker the rest and then the end; a caller
	# index repeated within one segment is reported once, where it first appears.
	reported = []
	if wires:
		upto = data.draw(st.integers(0, len(wires) - 1))
		reported += [event.index for event in ledger.receive_index(source_id, wires[upto])]
		assert reported == list(dict.fromkeys(originals[: upto + 1]))
	reported += [event.index for event in ledger.receive_index(source_id, marker.index)]
	assert reported == [*dict.fromkeys(originals), None]
