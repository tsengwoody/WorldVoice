"""Internal markers retain the NVDA index command boundary contract."""

import importlib.util
import sys
from types import ModuleType

import pytest

from runtime_harness import RUNTIME


@pytest.fixture
def nvda_commands(monkeypatch):
    class SynthCommand:
        pass

    class SynthParamCommand(SynthCommand):
        pass

    class IndexCommand(SynthCommand):
        def __init__(self, index):
            if not isinstance(index, int):
                raise ValueError("index must be an integer")
            self.index = index

    class BreakCommand(SynthCommand):
        def __init__(self, time):
            self.time = time

    commands = ModuleType("speech.commands")
    commands.SynthCommand = SynthCommand
    commands.SynthParamCommand = SynthParamCommand
    commands.IndexCommand = IndexCommand
    commands.BreakCommand = BreakCommand
    monkeypatch.setitem(sys.modules, "speech", ModuleType("speech"))
    monkeypatch.setitem(sys.modules, "speech.commands", commands)
    return commands


@pytest.fixture
def speechcommand(monkeypatch, nvda_commands):
    name = "worldvoice_index_command_test"
    spec = importlib.util.spec_from_file_location(name, RUNTIME.parent / "_speechcommand.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def test_marker_is_an_index_command(speechcommand, nvda_commands):
    marker = speechcommand.WorldVoiceIndexCommand(502)
    assert isinstance(marker, nvda_commands.IndexCommand)
    assert marker.index == 502
    assert repr(marker) == "WorldVoiceIndexCommand(502)"


def test_marker_rejects_non_integer(speechcommand):
    with pytest.raises(ValueError):
        speechcommand.WorldVoiceIndexCommand("502")
