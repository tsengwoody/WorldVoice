import ast
from collections import defaultdict
import importlib.util
import sys
import threading
import types
from pathlib import Path

import pytest

from test_worldvoice_request_manager import buses, manager, task_module


WORLDVOICE = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice"
PANEL_PATH = WORLDVOICE.parents[1] / "globalPlugins/WorldVoice/speechSettingsDialog.py"


def _load_voice_manager(monkeypatch, engine_classes):
	package_name = "f4_test_worldvoice"
	package = types.ModuleType(package_name)
	package.__path__ = [str(WORLDVOICE)]
	monkeypatch.setitem(sys.modules, package_name, package)
	config = types.SimpleNamespace(conf={"WorldVoice": {
		"voices": {},
		"autoLanguageSwitching": {
			"KeepMainLocaleEngineConsistent": False,
			"KeepMainLocaleParameterConsistent": False,
		},
		"engine": {},
	}})
	monkeypatch.setitem(sys.modules, "config", config)
	monkeypatch.setitem(sys.modules, "languageHandler", types.SimpleNamespace(
		getLanguage=lambda: "en", getLanguageDescription=lambda language: language))
	log = types.SimpleNamespace(
		debug=lambda *args: None,
		error=lambda *args, **kwargs: None,
	)
	monkeypatch.setitem(sys.modules, "logHandler", types.SimpleNamespace(log=log))
	monkeypatch.setitem(sys.modules, "synthDriverHandler", types.SimpleNamespace(
		VoiceInfo=object, getSynth=lambda: types.SimpleNamespace(name="WorldVoice")))
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


def _create_voices(monkeypatch, config):
	name = "f4_test_worldvoice.driver"
	spec = importlib.util.spec_from_file_location(name, WORLDVOICE / "driver/__init__.py")
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, name, module)
	spec.loader.exec_module(module)
	return (
		module.Voice("a", "A:a", None, "en"),
		module.Voice("b", "B:b", None, "fr"),
	)


def _load_panel_class(config):
	tree = ast.parse(PANEL_PATH.read_text(encoding="utf-8"))
	panel = next(node for node in tree.body
		if isinstance(node, ast.ClassDef) and node.name == "SpeechRoleSettingsPanel")
	environment = {
		"SettingsPanel": object,
		"_": lambda value: value,
		"guard_errors": lambda **kwargs: lambda method: method,
		"got_error_callback": lambda self: None,
		"config": config,
		"getSynth": lambda: types.SimpleNamespace(name="WorldVoice"),
		"wx": types.SimpleNamespace(NOT_FOUND=-1),
		"defaultdict": defaultdict,
	}
	exec(compile(ast.Module(body=[panel], type_ignores=[]), str(PANEL_PATH), "exec"), environment)
	return environment["SpeechRoleSettingsPanel"]


def _voices(monkeypatch):
	_load_voice_manager(monkeypatch, {})
	config = sys.modules["config"]
	return _create_voices(monkeypatch, config), config


class RecordingCore:
	def __init__(self):
		self.writes = []
		self.spoken = []
		self.supportedSettings = [types.SimpleNamespace(id=name) for name in
			("rate", "pitch", "volume", "inflection", "rateBoost")]

	def __setattr__(self, name, value):
		if name in ("voice", "rate", "pitch", "volume", "inflection", "rateBoost"):
			self.writes.append((name, value))
		object.__setattr__(self, name, value)

	def speak(self, text):
		self.spoken.append(text)

	def cancel(self):
		pass


def test_voice_settings_are_pending_and_revision_tracks_real_changes(monkeypatch):
	(a, b), config = _voices(monkeypatch)
	core = RecordingCore()
	a.__class__.core = core
	c = a.__class__("c", "C:c", None, "en")
	assert (a.revision, b.revision, c.revision) == (0, 0, 0)
	assert core.writes == []
	a.rate = 72
	assert a.revision == 1
	a.rate = 72
	assert a.revision == 1
	first = a.snapshot()
	a.rate = 81
	assert (first.rate, first.revision) == (72, 1)
	assert (a.snapshot().rate, a.snapshot().revision) == (81, 2)
	a.rollback()
	assert (a.rate, a.revision) == (50, 3)
	a.variant = "fast"
	a.waitfactor = 2
	assert a.revision == 5
	a.update_settings(pitch=60, volume=70)
	assert (a.pitch, a.volume, a.revision) == (60, 70, 7)
	with pytest.raises(ValueError, match="Unknown voice setting"):
		a.update_settings(rate=75, unknown=1)
	assert (a.rate, a.revision) == (50, 7)
	assert core.writes == []
	assert config.conf["WorldVoice"]["voices"][a.name]["rate"] == 50


def test_worker_activation_uses_one_snapshot_per_segment(monkeypatch):
	(a, _), _ = _voices(monkeypatch)
	from f4_test_worldvoice.driver.engineSession import EngineSession
	core = RecordingCore()
	a.__class__.core = core
	a.session = EngineSession(core)
	a.active()
	first_count = len(core.writes)
	assert first_count > 0
	a.active()
	assert len(core.writes) == first_count
	a.rate = 72
	old = a.snapshot()
	a.rate = 81
	a.session.activate(old, a.applyEngineSettings)
	assert core.rate == 72
	a.active()
	assert core.rate == 81
	assert len(core.writes) == first_count * 3


def test_speech_closure_does_not_activate_voice(monkeypatch):
	(a, _), _ = _voices(monkeypatch)
	core = RecordingCore()
	a.__class__.core = core
	queued = []
	a.taskManager = types.SimpleNamespace(append_speech=lambda request, voice, run: queued.append(run))
	a.active = lambda: (_ for _ in ()).throw(AssertionError("closure activated voice"))
	request = types.SimpleNamespace(token=types.SimpleNamespace(is_cancelled=lambda: False))
	a.speak("hello", request)
	assert len(queued) == 1
	queued[0]()
	assert core.spoken == ["hello"]
	assert core.writes == []


def test_manager_assigns_engine_session_to_new_voice(monkeypatch):
	(a, _), _ = _voices(monkeypatch)
	module = sys.modules["f4_test_worldvoice.voiceManager"]
	engine = a.__class__
	engine.session = object()
	module.READY_ENGINE_CLASS["A"] = engine
	voice_meta = module.VoiceMeta("new", "A:new", "New", "en", "A", "en")
	manager_instance = object.__new__(module.VoiceManager)
	manager_instance.table = [voice_meta]
	manager_instance.taskManager = None
	manager_instance._instanceCache = {}
	manager_instance._waitfactor = 0
	created = manager_instance._createVoiceInstance("A:new")
	assert "session" in created.__dict__
	assert created.session is engine.session


def test_engine_lifecycle_owns_one_session(monkeypatch):
	(a, _), _ = _voices(monkeypatch)
	terminated = []

	class Core(RecordingCore):
		def terminate(self):
			terminated.append(self)

	class Voice(a.__class__):
		core = None
		synth_driver_class = Core

	Voice.engineOn()
	assert Voice.session.core is Voice.core
	core = Voice.core
	Voice.engineOff()
	assert terminated == [core]
	assert Voice.core is None
	assert Voice.session is None


def test_engine_session_is_cleared_after_terminate_failure(monkeypatch):
	(a, _), _ = _voices(monkeypatch)

	class Core(RecordingCore):
		def terminate(self):
			raise RuntimeError("terminate failed")

	class Voice(a.__class__):
		core = None
		synth_driver_class = Core

	Voice.engineOn()
	with pytest.raises(RuntimeError, match="terminate failed"):
		Voice.engineOff()
	assert Voice.core is None
	assert Voice.session is None


def test_cancel_during_activation_skips_speech(manager, buses):
	entered = threading.Event()
	release = threading.Event()
	core = RecordingCore()
	voice = types.SimpleNamespace(
		core=core,
		active=lambda: (entered.set(), release.wait(2)),
	)
	request = manager.new_request()
	manager.append_speech(request, voice, lambda: core.speak("stale"))
	assert manager.submit_request(request)
	assert entered.wait(1)
	try:
		manager.cancel([voice])
	finally:
		release.set()
	manager._q.join()
	assert core.spoken == []
	assert request.token.is_cancelled()
	assert buses.outer_done == []


def test_worker_activates_once_before_running_speech(manager, buses):
	core = RecordingCore()
	activations = []
	voice = types.SimpleNamespace(core=core, active=lambda: activations.append("active"))
	request = manager.new_request()
	manager.append_speech(request, voice,
		lambda: (core.speak("hello"), buses.done.notify(synth=core)))
	assert manager.submit_request(request)
	assert buses.wait_for_outer_done(1) == [manager.owner]
	assert activations == ["active"]
	assert core.spoken == ["hello"]


def test_activation_error_fails_request_before_speech(manager, buses):
	core = RecordingCore()
	voice = types.SimpleNamespace(
		core=core,
		active=lambda: (_ for _ in ()).throw(RuntimeError("apply failed")),
	)
	request = manager.new_request()
	manager.append_speech(request, voice, lambda: core.speak("never"))
	assert manager.submit_request(request)
	with pytest.raises(RuntimeError, match="apply failed"):
		request.tasks[0].future.result(timeout=1)
	assert buses.wait_for_outer_done(1) == [manager.owner]
	assert request.failed
	assert core.spoken == []


def test_preview_b_while_a_is_playing_then_cancel_restores_next_segment(monkeypatch):
	(a, b), config = _voices(monkeypatch)
	from f4_test_worldvoice.driver.engineSession import EngineSession
	class BlockingCore(RecordingCore):
		def __init__(self):
			super().__init__()
			self.entered = threading.Event()
			self.release = threading.Event()

		def speak(self, text):
			super().speak(text)
			self.entered.set()
			self.release.wait(2)

	core = BlockingCore()
	a.__class__.core = core
	session = EngineSession(core)
	a.session = b.session = session
	a.active()
	playback = threading.Thread(target=core.speak, args=("A is speaking",))
	playback.start()
	assert core.entered.wait(1)
	current_writes = list(core.writes)
	manager_module = sys.modules["f4_test_worldvoice.voiceManager"]
	manager_instance = object.__new__(manager_module.VoiceManager)
	manager_instance._instanceCache = {a.name: a, b.name: b}
	manager_instance.getVoiceInstance = lambda name: manager_instance._instanceCache[name]
	panel_type = _load_panel_class(config)
	panel = panel_type()
	panel.disable = False
	panel._manager = manager_instance
	panel._initialKeepEngineConsistent = False
	panel._voicesChoice = types.SimpleNamespace(GetCurrentSelection=lambda: 1)
	panel._voiceNamesByChoiceIndex = [a.name, b.name]
	panel._rateSlider = types.SimpleNamespace(GetValue=lambda: 72)
	panel._keepParameterConsistentCheckBox = types.SimpleNamespace(GetValue=lambda: True)
	try:
		panel.onSpeechRateSliderScroll(None)
		assert (a.rate, b.rate) == (72, 72)
		assert playback.is_alive()
		assert core.spoken == ["A is speaking"]
		assert core.writes == current_writes
	finally:
		core.release.set()
		playback.join(1)
	assert not playback.is_alive()
	b.active()
	assert (core.voice, core.rate) == ("b", 72)
	panel.onDiscard()
	assert (a.rate, b.rate) == (50, 50)
	b.active()
	assert (core.voice, core.rate) == ("b", 50)


def test_consistency_preview_updates_each_voice_in_one_batch(monkeypatch):
	(a, b), _ = _voices(monkeypatch)
	manager_module = sys.modules["f4_test_worldvoice.voiceManager"]
	manager_instance = object.__new__(manager_module.VoiceManager)
	manager_instance._instanceCache = {a.name: a, b.name: b}
	updates = []
	b.update_settings = lambda **values: updates.append(values)
	a.update_settings(rate=72, pitch=60, volume=70, inflection=55, rateBoost=True)
	manager_instance.previewVoiceParameterConsistent(a)
	assert updates == [{"rate": 72, "pitch": 60, "volume": 70,
		"inflection": 55, "rateBoost": True}]
