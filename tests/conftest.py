"""Shared fixtures for every test module."""

import importlib
import os
import sys
from types import ModuleType, SimpleNamespace

import pytest
from addon_loader import alias_package
from hypothesis import settings
from mutation_support import name_trampolines_by_file, running_under_mutmut
from nvda_stubs import StubModules
from runtime_harness import RUNTIME, MemoryRepository, load_runtime
from worldvoice_harness import EventStub, load_voice_manager

# Property tests: a quick default for every run, and a deep profile for hunting edge cases:
# HYPOTHESIS_PROFILE=deep python3 -m pytest tests -k property
settings.register_profile("default", max_examples=200, deadline=None)
settings.register_profile("deep", max_examples=20000, deadline=None)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))

if running_under_mutmut():
	name_trampolines_by_file()


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


@pytest.fixture
def composition(monkeypatch):
	manager_module = load_voice_manager(monkeypatch)
	package = manager_module.__package__
	monkeypatch.setattr(
		importlib.import_module(package + ".voiceCatalog"),
		"VoiceInfo",
		lambda key, description, language: SimpleNamespace(
			id=key,
			description=description,
			language=language,
		),
	)
	monkeypatch.setattr(
		sys.modules["languageHandler"],
		"getLanguageDescription",
		lambda value: value,
		raising=False,
	)
	monkeypatch.setattr(sys.modules["synthDriverHandler"], "getSynth", lambda: None, raising=False)
	driver = importlib.import_module(package + ".driver")
	settings = importlib.import_module(package + ".runtime.settings")
	scheduler = importlib.import_module(package + ".runtime.scheduler")
	bridge_module = importlib.import_module(package + ".nvdaEventBridge")
	models = importlib.import_module(package + ".runtime.models")
	ledger = importlib.import_module(package + ".indexLedger").IndexLedger()
	repo = MemoryRepository()
	store = settings.VoiceSettingsStore(repo)
	done, index = EventStub(), EventStub()
	owner = object()
	bridge = bridge_module.NvdaEventBridge(
		owner,
		done_event=done,
		index_event=index,
		get_synth=lambda: owner,
		index_ledger=ledger,
	)
	tasks = scheduler.TaskManager(bridge)
	bridge.start(tasks.on_event, batch_handler=tasks.on_events)
	cores = []

	class Core:
		def __init__(self):
			self.closes = 0
			self.cancels = 0
			self.availableVoices = {
				key: SimpleNamespace(id=key, language=language, displayName=key)
				for key, language in (("a", "en"), ("b", "zh"))
			}
			cores.append(self)

		def terminate(self):
			self.closes += 1

		def cancel(self):
			self.cancels += 1

	def engine(name, *, fail=False, empty=False):
		class Voice(driver.Voice):
			synth_driver_class = Core
			opened = None  # Test bookkeeping: the core this engine has open.

			@classmethod
			def create_core(cls):
				if fail:
					raise RuntimeError("partial open")
				cls.opened = cls.synth_driver_class()
				return cls.opened

			@classmethod
			def destroy_core(cls, core):
				if cls.opened is core:
					cls.opened = None
				super().destroy_core(core)

			@classmethod
			def supportedSettings(cls):
				return ["rate", "pitch", "volume"]

			@classmethod
			def voices(cls, core):
				return [] if empty else super().voices(core)

			def applyEngineSettings(self, core, snapshot):
				core.language = snapshot.language

		Voice.engine = name
		engines[name] = Voice
		return Voice

	engines = {}
	managers = []

	config = sys.modules["config"]

	def create(
		completion_for=lambda cls, core: models.CompletionContract(),
		engine_classes=None,
		get_language=lambda: "en",
		parameter_consistency=None,
		roles=None,
	):
		manager = manager_module.VoiceManager(
			tasks,
			store,
			bridge,
			index_ledger=ledger,
			completion_for=completion_for,
			engine_classes=engines if engine_classes is None else engine_classes,
			conf_provider=lambda: config.conf,
			get_language=get_language,
			parameter_consistency=parameter_consistency,
			roles=roles,
		)
		managers.append(manager)
		return manager

	yield SimpleNamespace(
		engine=engine,
		engines=engines,
		create=create,
		store=store,
		repo=repo,
		bridge=bridge,
		tasks=tasks,
		cores=cores,
		Core=Core,
		module=manager_module,
		driver=driver,
		ledger=ledger,
		models=models,
		done=done,
		index=index,
		owner=owner,
		config=config,
	)
	tasks.shutdown()
	bridge.close()
	for manager in managers:
		manager.terminate(commit=False)
	ledger.close()
