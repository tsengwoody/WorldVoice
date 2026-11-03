"""The legacy command boundary normalizes NVDA's commands and rejects WorldVoice's internal markers."""

import importlib
import sys
from types import SimpleNamespace

import pytest
from addon_loader import alias_package
from hypothesis import HealthCheck, given, settings, strategies as st
from runtime_harness import RUNTIME


@pytest.fixture
def legacy(monkeypatch, rt, nvda_commands):
	name = "worldvoice_commands_test"
	alias_package(monkeypatch, name, RUNTIME.parent)
	monkeypatch.setitem(sys.modules, name + ".runtime", rt.package)
	monkeypatch.setitem(sys.modules, name + ".runtime.models", rt.models)

	for suffix in ("bridge", "bridge.commands", "speechCommands"):
		monkeypatch.delitem(sys.modules, name + "." + suffix, raising=False)
	commands = importlib.import_module(name + ".bridge.commands")
	speech_commands = importlib.import_module(name + ".speechCommands")
	return SimpleNamespace(
		BreakCommand=nvda_commands.BreakCommand,
		commands=commands,
		speech_commands=speech_commands,
	)


def test_normalizer_is_lazy_and_preserves_unrecognized_objects(legacy, rt):
	commands = [
		rt.models.SelectVoice("Fake:b"),
		rt.models.Pause(1),
		SimpleNamespace(name="looks like voice", time=200),
		22,
	]
	seen = []

	def sequence():
		for command in commands:
			seen.append(command)
			yield command
		raise RuntimeError("source failed")

	normalized = legacy.commands.normalizeNvdaCommands(sequence())
	assert seen == []
	for command in commands:
		assert next(normalized) is command
	with pytest.raises(RuntimeError, match="source failed"):
		next(normalized)


def test_normalizer_rejects_external_marker(legacy):
	marker = legacy.speech_commands.WorldVoiceIndexCommand(502)
	normalized = legacy.commands.normalizeNvdaCommands(["before", marker, "after"])
	assert next(normalized) == "before"
	with pytest.raises(ValueError, match="^Internal segment markers cannot be supplied externally$"):
		next(normalized)


def test_full_sequence_normalizes_without_inserting_internal_markers(legacy, rt, nvda_commands):
	select = rt.models.SelectVoice("Fake:b")
	index = nvda_commands.IndexCommand(123)
	result = list(
		legacy.commands.normalizeNvdaCommands(
			[
				"A",
				select,
				select,
				"B",
				index,
				legacy.BreakCommand(200),
				"C",
			],
		),
	)
	assert result == [
		"A",
		rt.models.SelectVoice("Fake:b"),
		rt.models.SelectVoice("Fake:b"),
		"B",
		index,
		rt.models.Pause(0.2),
		"C",
	]
	assert result[4] is index
	assert index.index == 123
	assert not any(isinstance(command, legacy.speech_commands.WorldVoiceIndexCommand) for command in result)


# Parameter replay (feat/segment-pause spec §4.6, O10; decided by the user, 2026-11-03, Q1): WorldVoice
# speaks each segment in its own engine call, which starts from the defaults, so the parameters in
# effect at a pause or voice switch are replayed before the next text, as NVDA's ParamChangeTracker
# does at the start of every utterance.


def param_classes(nvda_commands):
	class Pitch(nvda_commands.SynthParamCommand):
		def __init__(self, offset=0):
			self.offset = offset
			self.isDefault = offset == 0

		def __repr__(self):
			return f"Pitch({self.offset})"

	class CharMode(nvda_commands.SynthParamCommand):
		def __init__(self, state):
			self.state = state
			self.isDefault = not state

		def __repr__(self):
			return f"CharMode({self.state})"

	return Pitch, CharMode


def normalized(legacy, sequence):
	return list(legacy.commands.normalizeNvdaCommands(sequence))


def test_parameters_are_replayed_after_a_pause(legacy, rt, nvda_commands):
	Pitch, _ = param_classes(nvda_commands)
	pitch = Pitch(30)
	result = normalized(legacy, [pitch, "a b", legacy.BreakCommand(10), "c"])
	assert result == [pitch, "a b", rt.models.Pause(0.01), pitch, "c"]
	assert result[3] is pitch


def test_character_mode_is_replayed_after_a_voice_switch(legacy, rt, nvda_commands):
	_, CharMode = param_classes(nvda_commands)
	mode, select = CharMode(True), rt.models.SelectVoice("Fake:b")
	result = normalized(legacy, [mode, "a", select, "b"])
	assert result == [mode, "a", select, mode, "b"]
	assert result[3] is mode


def test_a_default_command_clears_its_type(legacy, rt, nvda_commands):
	Pitch, _ = param_classes(nvda_commands)
	result = normalized(legacy, [Pitch(30), "a", reset := Pitch(0), "b", legacy.BreakCommand(10), "c"])
	assert result[2] is reset
	assert result[4:] == [rt.models.Pause(0.01), "c"]


def test_a_parameter_after_the_pause_is_replayed_once(legacy, rt, nvda_commands):
	Pitch, _ = param_classes(nvda_commands)
	later = Pitch(10)
	result = normalized(legacy, [Pitch(30), "a", legacy.BreakCommand(10), later, "c"])
	assert result[2:] == [rt.models.Pause(0.01), later, "c"]
	assert result[3] is later


def test_commands_before_the_first_text_pass_unchanged(legacy, nvda_commands):
	# The first segment needs no replay; a default command there still reaches the engine.
	Pitch, _ = param_classes(nvda_commands)
	reset, raised = Pitch(0), Pitch(30)
	result = normalized(legacy, [reset, raised, "a"])
	assert result == [reset, raised, "a"]
	assert result[0] is reset


def test_a_reset_after_the_replay_is_passed_on(legacy, rt, nvda_commands):
	Pitch, _ = param_classes(nvda_commands)
	pitch, reset = Pitch(30), Pitch(0)
	result = normalized(legacy, [pitch, "a", legacy.BreakCommand(10), "b", reset, "c"])
	assert result == [pitch, "a", rt.models.Pause(0.01), pitch, "b", reset, "c"]
	assert result[5] is reset


def test_no_replay_at_the_end_of_a_sequence(legacy, rt, nvda_commands):
	Pitch, _ = param_classes(nvda_commands)
	pitch = Pitch(30)
	assert normalized(legacy, [pitch, "a", legacy.BreakCommand(10), Pitch(10)]) == [
		pitch,
		"a",
		rt.models.Pause(0.01),
	]


def test_index_commands_keep_their_place_while_a_replay_is_pending(legacy, rt, nvda_commands):
	Pitch, _ = param_classes(nvda_commands)
	pitch, index = Pitch(30), nvda_commands.IndexCommand(1)
	result = normalized(legacy, [pitch, "a", legacy.BreakCommand(10), index, "b"])
	assert result == [pitch, "a", rt.models.Pause(0.01), index, pitch, "b"]
	assert result[3] is index


def test_language_commands_are_not_tracked(legacy, rt, nvda_commands):
	nvda, wv = nvda_commands.LangChangeCommand("fr"), legacy.speech_commands.WVLangChangeCommand("de")
	result = normalized(legacy, [nvda, wv, "a", legacy.BreakCommand(10), "b"])
	assert result == [nvda, wv, "a", rt.models.Pause(0.01), "b"]
	assert result[0] is nvda and result[1] is wv


def tracked(state, command):
	"""NVDA's ParamChangeTracker.update (ref/nvda/source/speech/manager.py:83-112)."""
	if command.isDefault:
		state.pop(type(command), None)
	else:
		state[type(command)] = command


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data=st.data())
def test_property_every_segment_speaks_with_nvdas_parameters(legacy, rt, nvda_commands, data):
	# P7: the parameters in effect at every text item of every engine call are NVDA's at that item.
	Pitch, CharMode = param_classes(nvda_commands)
	items = st.one_of(
		st.sampled_from(["a", "b c", " "]),
		st.builds(Pitch, st.sampled_from([0, 10, 30])),
		st.builds(CharMode, st.booleans()),
		st.builds(legacy.BreakCommand, st.integers(0, 20)),
		st.builds(rt.models.SelectVoice, st.sampled_from(["Fake:a", "Fake:b"])),
		st.builds(nvda_commands.IndexCommand, st.integers(0, 9)),
	)
	sequence = data.draw(st.lists(items, max_size=12))
	expected, state = [], {}
	for item in sequence:
		if isinstance(item, nvda_commands.SynthParamCommand):
			tracked(state, item)
		elif isinstance(item, str):
			expected.append((item, dict(state)))
	seen, state = [], {}
	for item in normalized(legacy, sequence):
		if isinstance(item, (rt.models.Pause, rt.models.SelectVoice)):
			state = {}
		elif isinstance(item, nvda_commands.SynthParamCommand):
			tracked(state, item)
		elif isinstance(item, str):
			seen.append((item, dict(state)))
	assert seen == expected
