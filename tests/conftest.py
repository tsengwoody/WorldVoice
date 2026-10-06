"""Shared fixtures for every test module."""

import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest
from addon_loader import alias_package
from nvda_stubs import StubModules
from runtime_harness import RUNTIME, load_runtime


@pytest.fixture(autouse=True)
def fresh_completion_rules(monkeypatch):
	"""Bind runtime.completion to the models each test loads.

	Harnesses reload runtime.models per test, often under an alias package. A
	completion module imported by an earlier test would keep that test's enums.
	"""
	for name, module in tuple(sys.modules.items()):
		if (getattr(module, "__file__", None) or "").replace("\\", "/").endswith("runtime/completion.py"):
			monkeypatch.delitem(sys.modules, name)


@pytest.fixture
def stub_modules(monkeypatch):
	"""Register stub NVDA modules for this test only."""
	return StubModules(monkeypatch)


@pytest.fixture
def rt(monkeypatch):
	"""The pure runtime package, loaded fresh under a test alias."""
	return load_runtime(monkeypatch)


@pytest.fixture
def compat(monkeypatch, rt):
	"""The compat engine adapter and voice facade, bound to this test's runtime."""
	name = "worldvoice_compat_test"
	alias_package(monkeypatch, name, RUNTIME.parent)
	for suffix, module in (
		("", rt.package),
		(".models", rt.models),
		(".settings", rt.settings),
		(".session", rt.session),
	):
		monkeypatch.setitem(sys.modules, name + ".runtime" + suffix, module)
	# Remove cached compatibility imports between isolated runtime fixtures.
	for suffix in ("compat", "compat.engineAdapter", "compat.voiceFacade"):
		monkeypatch.delitem(sys.modules, name + "." + suffix, raising=False)
	return SimpleNamespace(
		adapter=importlib.import_module(name + ".compat.engineAdapter"),
		facade=importlib.import_module(name + ".compat.voiceFacade"),
	)


@pytest.fixture
def nvda_commands(monkeypatch):
	"""Stub NVDA speech.commands with the command classes WorldVoice uses."""

	class SynthCommand:
		pass

	class SynthParamCommand(SynthCommand):
		pass

	class IndexCommand(SynthCommand):
		def __init__(self, index):
			if not isinstance(index, int):
				raise ValueError("index must be an integer")  # noqa: TRY004 - NVDA's IndexCommand raises ValueError
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
def session_module(rt):
	"""The runtime's EngineSession and VoiceSnapshot."""
	return SimpleNamespace(EngineSession=rt.session.EngineSession, VoiceSnapshot=rt.models.VoiceSnapshot)


@pytest.fixture
def snap(session_module):
	"""Build a VoiceSnapshot from a voice id and revision."""
	return lambda id, rev: session_module.VoiceSnapshot(
		voice_id=id,
		revision=rev,
		language="en",
		rate=50,
		pitch=50,
		volume=50,
		variant="default",
		inflection=50,
		rateBoost=False,
		waitfactor=0,
	)
