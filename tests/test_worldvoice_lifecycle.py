import ast
import importlib.util
import sys
import types
from pathlib import Path

import pytest


WORLDVOICE = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice"


def _load_synth_class(environment):
	"""Execute the real driver class with NVDA's unavailable services replaced."""
	tree = ast.parse((WORLDVOICE / "__init__.py").read_text(encoding="utf-8"))
	driver = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SynthDriver")
	exec(compile(ast.Module(body=[driver], type_ignores=[]), str(WORLDVOICE / "__init__.py"), "exec"), environment)
	return environment["SynthDriver"]


@pytest.mark.parametrize("failure", ["manager", "symbols", "bridge"])
def test_failed_synth_construction_releases_acquired_resources(failure):
	changes = []
	panel = object()
	spelling = object()
	settings_dialogs = types.SimpleNamespace(VoiceSettingsPanel=panel)
	speech_api = types.SimpleNamespace(speakSpelling=spelling)
	gui = types.SimpleNamespace(settingsDialogs=settings_dialogs)
	speech = types.SimpleNamespace(speech=speech_api)

	class TaskManager:
		def __init__(self, output=None, logger=None):
			changes.append("task started")

		def on_event(self, event):
			pass

		def shutdown(self):
			changes.append("task stopped")

	class VoiceManager:
		def __init__(self, taskManager, settings=None, bridge=None):
			if failure == "manager":
				raise RuntimeError("no voices")
			changes.append("engine started")

		def terminate(self, *, commit=True):
			assert commit is False
			changes.append("engine stopped")

	class Bridge:
		def __init__(self, *args, **kwargs):
			pass

		def start(self, handler):
			changes.append("bridge started")
			if failure == "bridge":
				raise RuntimeError("bridge failure")

		def close(self):
			changes.append("bridge stopped")

	class SpeechSymbols:
		def load(self, path):
			if failure == "symbols":
				raise RuntimeError("dictionary failure")

	class Action:
		def __init__(self, label):
			self.label = label

		def notify(self):
			changes.append(self.label)

	commands = {name: type(name, (), {}) for name in (
		"IndexCommand", "CharacterModeCommand", "LangChangeCommand", "BreakCommand",
		"PitchCommand", "RateCommand", "VolumeCommand",
	)}
	def apply_pipeline():
		changes.append("pipeline started")

	def clear_pipeline():
		changes.append("pipeline stopped")

	environment = {
		"SynthDriver": type("NVDASynthDriver", (), {}),
		"synthIndexReached": object(),
		"synthDoneSpeaking": object(),
		"WVStart": Action("start"),
		"WVEnd": Action("end"),
		"time": types.SimpleNamespace(perf_counter=lambda: 0),
		"nvdaLog": types.SimpleNamespace(debug=lambda *args: None, error=lambda *args, **kwargs: None),
		"apply_worldvoice_pipeline": apply_pipeline,
		"clear_pipeline": clear_pipeline,
		"gui": gui,
		"WorldVoiceVoiceSettingsPanel": object(),
		"TaskManager": TaskManager,
		"VoiceManager": VoiceManager,
		"NvdaEventBridge": Bridge,
		"ConfigVoiceSettingsRepository": lambda *args: object(),
		"VoiceSettingsStore": lambda repository: object(),
		"config": types.SimpleNamespace(conf={}),
		"getSynth": lambda: None,
		"speech": speech,
		"SpeechSymbols": SpeechSymbols,
		"filter_speechSequence": types.SimpleNamespace(unregister=lambda handler: None),
		**commands,
	}
	with pytest.raises(RuntimeError, match="no voices|dictionary failure|bridge failure"):
		_load_synth_class(environment)()

	assert settings_dialogs.VoiceSettingsPanel is panel
	assert speech_api.speakSpelling is spelling
	assert "task stopped" in changes
	assert "bridge stopped" in changes
	assert changes.index("task stopped") < changes.index("bridge stopped")
	assert "pipeline stopped" in changes
	assert changes.count("end") == 1
	if failure == "symbols":
		assert "engine stopped" in changes
		assert changes.index("bridge stopped") < changes.index("engine stopped")


def _load_voice_manager(monkeypatch, engine_classes):
	package_name = "lifecycle_test_worldvoice"
	for name in tuple(sys.modules):
		if name.startswith(package_name + "."):
			monkeypatch.delitem(sys.modules, name)
	package = types.ModuleType(package_name)
	package.__path__ = [str(WORLDVOICE)]
	monkeypatch.setitem(sys.modules, package_name, package)
	config = types.SimpleNamespace(conf={"WorldVoice": {
		"autoLanguageSwitching": {"KeepMainLocaleEngineConsistent": False},
		"engine": {},
	}})
	monkeypatch.setitem(sys.modules, "config", config)
	monkeypatch.setitem(sys.modules, "languageHandler", types.SimpleNamespace(getLanguage=lambda: "en"))
	monkeypatch.setitem(sys.modules, "logHandler", types.SimpleNamespace(log=types.SimpleNamespace(
		debug=lambda *args: None, error=lambda *args, **kwargs: None,
	)))
	monkeypatch.setitem(sys.modules, "synthDriverHandler", types.SimpleNamespace(VoiceInfo=object))
	engine_name = f"{package_name}.engine"
	engine = types.ModuleType(engine_name)
	engine.EngineType = [types.SimpleNamespace(name=name) for name in engine_classes]
	engine.READY_ENGINE_CLASS = dict(engine_classes)
	engine.get_engine_enabled = lambda *args: True
	engine.refresh_ready_engine_classes = lambda *args: None
	monkeypatch.setitem(sys.modules, engine_name, engine)
	name = f"{package_name}.voiceManager"
	spec = importlib.util.spec_from_file_location(name, WORLDVOICE / "voiceManager.py")
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, name, module)
	spec.loader.exec_module(module)
	return module


def test_voice_manager_closes_engine_when_no_voices(monkeypatch):
	closed = []

	class Engine:
		engine = "A"
		core = None

		@classmethod
		def engineOn(cls):
			cls.core = object()

		@classmethod
		def voices(cls):
			return []

		@classmethod
		def engineOff(cls):
			closed.append(cls.engine)

	module = _load_voice_manager(monkeypatch, {"A": Engine})
	from runtime_harness import MemoryRepository
	store = module.VoiceSettingsStore(MemoryRepository())
	bridge = types.SimpleNamespace(bind=lambda *args: None, unbind=lambda *args: None)
	with pytest.raises(RuntimeError, match="No WorldVoice voices"):
		module.VoiceManager(taskManager=object(), settings=store, bridge=bridge)
	assert closed == ["A"]


def test_voice_manager_continues_cleanup_after_one_engine_fails(monkeypatch):
	closed = []

	class BrokenEngine:
		engine = "broken"

		@classmethod
		def engineOff(cls):
			closed.append("broken")
			raise RuntimeError("failure while closing")

	class OtherEngine:
		engine = "other"

		@classmethod
		def engineOff(cls):
			closed.append("other")

	module = _load_voice_manager(monkeypatch, {"broken": BrokenEngine, "other": OtherEngine})
	manager = object.__new__(module.VoiceManager)
	manager.taskManager = object()
	manager._terminated = False
	manager._instanceCache = {}
	manager.installEngine = [BrokenEngine, OtherEngine]
	manager._sessions = {}
	manager.settings = types.SimpleNamespace(keys=lambda: ())
	manager._bridge = types.SimpleNamespace(unbind=lambda source: None)
	manager._resources = [
		(object(), types.SimpleNamespace(close=cls.engineOff, source_id=object()), None, cls, True)
		for cls in (BrokenEngine, OtherEngine)
	]
	manager.terminate()
	assert set(closed) == {"broken", "other"}
	assert manager.taskManager is None


@pytest.mark.parametrize("failure", ["done", "index"])
def test_bridge_unregisters_events_if_registration_fails(monkeypatch, failure):
	class DoneEvent:
		def __init__(self):
			self.handlers = []

		def register(self, handler):
			self.handlers.append(handler)
			if failure == "done":
				raise RuntimeError("registration failed")

		def unregister(self, handler):
			self.handlers.remove(handler)

	class FailingEvent:
		def register(self, handler):
			if failure == "index":
				raise RuntimeError("registration failed")

		def unregister(self, handler):
			pass

	done = DoneEvent()
	module = _load_voice_manager(monkeypatch, {})
	bridge = module.NvdaEventBridge(object(), done_event=done,
		index_event=FailingEvent(), get_synth=lambda: None)
	with pytest.raises(RuntimeError, match="registration failed"):
		bridge.start(lambda event: None)
	assert done.handlers == []
