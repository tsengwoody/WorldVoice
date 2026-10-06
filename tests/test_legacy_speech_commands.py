"""The legacy command boundary owns NVDA and concrete Voice recognition."""

import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest

from runtime_harness import RUNTIME


@pytest.fixture
def legacy(monkeypatch, rt, nvda_commands):
	name = "worldvoice_commands_test"
	package = ModuleType(name)
	package.__path__ = [str(RUNTIME.parent)]
	monkeypatch.setitem(sys.modules, name, package)
	monkeypatch.setitem(sys.modules, name + ".runtime", rt.package)
	monkeypatch.setitem(sys.modules, name + ".runtime.models", rt.models)
	monkeypatch.setitem(sys.modules, "config", SimpleNamespace(conf={}))
	monkeypatch.setitem(sys.modules, "languageHandler", SimpleNamespace())
	monkeypatch.setitem(sys.modules, "synthDriverHandler", SimpleNamespace(getSynth=lambda: None))

	for suffix in ("driver", "compat", "compat.commands", "_speechcommand"):
		monkeypatch.delitem(sys.modules, name + "." + suffix, raising=False)
	driver = importlib.import_module(name + ".driver")
	commands = importlib.import_module(name + ".compat.commands")
	speechcommand = importlib.import_module(name + "._speechcommand")
	return SimpleNamespace(
		Voice=driver.Voice,
		BreakCommand=nvda_commands.BreakCommand,
		commands=commands,
		speechcommand=speechcommand,
	)


def test_normalizer_passes_voice_objects_through_unchanged(legacy):
	# Voices are chosen by SelectVoice from lang_cmd_to_voice; a Voice object is not a command.
	voice = object.__new__(legacy.Voice)
	voice.name = "Fake:a"
	assert list(legacy.commands.normalize_legacy_commands([voice])) == [voice]


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

	normalized = legacy.commands.normalize_legacy_commands(sequence())
	assert seen == []
	for command in commands:
		assert next(normalized) is command
	with pytest.raises(RuntimeError, match="source failed"):
		next(normalized)


def test_normalizer_rejects_external_marker(legacy):
	marker = legacy.speechcommand.WorldVoiceIndexCommand(502)
	normalized = legacy.commands.normalize_legacy_commands(["before", marker, "after"])
	assert next(normalized) == "before"
	with pytest.raises(ValueError):
		next(normalized)


def test_full_sequence_normalizes_without_inserting_internal_markers(legacy, rt, nvda_commands):
	select = rt.models.SelectVoice("Fake:b")
	index = nvda_commands.IndexCommand(123)
	result = list(
		legacy.commands.normalize_legacy_commands(
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
	assert not any(isinstance(command, legacy.speechcommand.WorldVoiceIndexCommand) for command in result)
