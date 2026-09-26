"""The legacy command boundary owns NVDA and concrete Voice recognition."""

import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest

from runtime_harness import RUNTIME, rt


@pytest.fixture
def legacy(monkeypatch, rt):
    name = "worldvoice_commands_test"
    package = ModuleType(name)
    package.__path__ = [str(RUNTIME.parent)]
    monkeypatch.setitem(sys.modules, name, package)
    monkeypatch.setitem(sys.modules, name + ".runtime", rt.package)
    monkeypatch.setitem(sys.modules, name + ".runtime.models", rt.models)
    monkeypatch.setitem(sys.modules, "config", SimpleNamespace(conf={}))
    monkeypatch.setitem(sys.modules, "languageHandler", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "synthDriverHandler", SimpleNamespace(getSynth=lambda: None))

    class BreakCommand:
        def __init__(self, time):
            self.time = time

    monkeypatch.setitem(sys.modules, "speech", ModuleType("speech"))
    monkeypatch.setitem(sys.modules, "speech.commands", SimpleNamespace(BreakCommand=BreakCommand))
    for suffix in ("driver", "driver.engineSession", "compat", "compat.commands"):
        monkeypatch.delitem(sys.modules, name + "." + suffix, raising=False)
    driver = importlib.import_module(name + ".driver")
    commands = importlib.import_module(name + ".compat.commands")
    return SimpleNamespace(Voice=driver.Voice, BreakCommand=BreakCommand, commands=commands)


def test_normalizer_handles_voice_and_break(legacy, rt):
    voice = object.__new__(legacy.Voice)
    voice.name = "Fake:a"
    index = object()
    normalized = list(legacy.commands.normalize_legacy_commands([voice, "hello", index, legacy.BreakCommand(200)]))
    assert normalized == [rt.models.SelectVoice("Fake:a"), "hello", index, rt.models.Pause(0.2)]
    assert normalized[2] is index


def test_normalizer_is_lazy_and_preserves_unrecognized_objects(legacy, rt):
    commands = [rt.models.SelectVoice("Fake:b"), rt.models.Pause(1),
                SimpleNamespace(name="looks like voice", time=200), 22]
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
