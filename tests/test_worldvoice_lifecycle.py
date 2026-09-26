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


@pytest.mark.parametrize("failure", ["manager", "symbols"])
def test_failed_synth_construction_releases_acquired_resources(failure):
	changes = []
	panel = object()
	spelling = object()
	settings_dialogs = types.SimpleNamespace(VoiceSettingsPanel=panel)
	speech_api = types.SimpleNamespace(speakSpelling=spelling)
	gui = types.SimpleNamespace(settingsDialogs=settings_dialogs)
	speech = types.SimpleNamespace(speech=speech_api)

	class TaskManager:
		def __init__(self, owner):
			self.owner = owner
			changes.append("task started")

		def shutdown(self):
			changes.append("task stopped")

	class VoiceManager:
		def __init__(self, taskManager):
			if failure == "manager":
				raise RuntimeError("no voices")
			changes.append("engine started")

		def terminate(self):
			changes.append("engine stopped")

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
		"speech": speech,
		"SpeechSymbols": SpeechSymbols,
		"filter_speechSequence": types.SimpleNamespace(unregister=lambda handler: None),
		**commands,
	}
	with pytest.raises(RuntimeError, match="no voices|dictionary failure"):
		_load_synth_class(environment)()

	assert settings_dialogs.VoiceSettingsPanel is panel
	assert speech_api.speakSpelling is spelling
	assert "task stopped" in changes
	assert "pipeline stopped" in changes
	assert changes.count("end") == 1
	if failure == "symbols":
		assert "engine stopped" in changes


def _load_voice_manager(monkeypatch, engine_classes):
	package_name = "lifecycle_test_worldvoice"
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

		@classmethod
		def engineOn(cls):
			pass

		@classmethod
		def voices(cls):
			return []

		@classmethod
		def engineOff(cls):
			closed.append(cls.engine)

	module = _load_voice_manager(monkeypatch, {"A": Engine})
	with pytest.raises(RuntimeError, match="No WorldVoice voices"):
		module.VoiceManager(taskManager=object())
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
	manager._instanceCache = {}
	manager.installEngine = [BrokenEngine, OtherEngine]
	manager._engineClassesToClose = [BrokenEngine, OtherEngine]
	manager.terminate()
	assert set(closed) == {"broken", "other"}
	assert manager.taskManager is None


@pytest.mark.parametrize("failure", ["done", "index"])
def test_task_manager_unregisters_events_if_registration_fails(monkeypatch, failure):
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
	monkeypatch.setitem(sys.modules, "logHandler", types.SimpleNamespace(log=object()))
	monkeypatch.setitem(sys.modules, "synthDriverHandler", types.SimpleNamespace(
		synthDoneSpeaking=done,
		synthIndexReached=FailingEvent(),
		getSynth=lambda: None,
	))
	spec = importlib.util.spec_from_file_location("lifecycle_test_task_manager", WORLDVOICE / "taskManager.py")
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, spec.name, module)
	spec.loader.exec_module(module)
	with pytest.raises(RuntimeError, match="registration failed"):
		module.TaskManager()
	assert done.handlers == []
