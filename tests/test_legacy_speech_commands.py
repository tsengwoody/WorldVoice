"""The legacy command boundary owns NVDA and concrete Voice recognition."""

import importlib
import sys
from types import SimpleNamespace

import pytest
from addon_loader import alias_package
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
	with pytest.raises(ValueError):
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
