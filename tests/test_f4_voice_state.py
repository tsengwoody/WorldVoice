import ast
import dataclasses
import inspect
from collections import defaultdict
import importlib.util
import sys
import threading
import types
from pathlib import Path

import pytest

from test_worldvoice_request_manager import buses, manager, task_module, append_speech, cancel
from voice_binding_harness import install_binding, bind_core


WORLDVOICE = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice"
PANEL_PATH = WORLDVOICE.parents[1] / "globalPlugins/WorldVoice/speechSettingsDialog.py"


def _load_voice_manager(monkeypatch, engine_classes):
	package_name = "f4_test_worldvoice"
	for name in tuple(sys.modules):
		if name.startswith(package_name + "."):
			monkeypatch.delitem(sys.modules, name)
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
	voice = install_binding(module, config)
	return voice("a", "A:a", "en"), voice("b", "B:b", "fr")


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
	spec = type(a._state.spec)("c", "C:c", "C:c", "en", "C", "en")
	c = a.__class__(spec, dataclasses.replace(a._binding, core=core), None)
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
	core = RecordingCore()
	bind_core(core, a)
	a.active()
	first_count = len(core.writes)
	assert first_count > 0
	a.active()
	assert len(core.writes) == first_count
	a.rate = 72
	# Activation reads one immutable snapshot; an edit during apply is deferred.
	original_apply = a.applyEngineSettings
	def edit_during_apply(core, snapshot):
		a.rate = 81
		original_apply(core, snapshot)
	a.applyEngineSettings = edit_during_apply
	a.active()
	assert core.rate == 72
	a.active()
	assert core.rate == 81
	assert len(core.writes) == first_count * 3


def test_speech_queue_does_not_activate_voice(monkeypatch):
	(a, _), _ = _voices(monkeypatch)
	core = RecordingCore()
	bind_core(core, a)
	queued = []
	a.taskManager = types.SimpleNamespace(append_speech=lambda *args: queued.append(args))
	a.active = lambda: (_ for _ in ()).throw(AssertionError("queue activated voice"))
	request = object()
	a.speak(["hello"], request)
	assert queued == [(request, a._binding.session, a.name, ("hello",))]
	assert core.spoken == []
	assert core.writes == []


def test_manager_binds_new_voice_to_its_engine(monkeypatch):
	(a, _), _ = _voices(monkeypatch)
	module = sys.modules["f4_test_worldvoice.voiceManager"]
	module.READY_ENGINE_CLASS["A"] = a.__class__
	voice_meta = type(a._state.spec)("new", "A:new", "A:new", "en", "A", "en")
	manager_instance = object.__new__(module.VoiceManager)
	manager_instance._specs = {voice_meta.name: voice_meta}
	manager_instance._bindings = {"A": a._binding}
	manager_instance.settings = a._binding.settings
	manager_instance.taskManager = None
	manager_instance._instanceCache = {}
	manager_instance._waitfactor = 0
	created = manager_instance._createVoiceInstance("A:new")
	assert created._binding is a._binding
	assert created.core is a._binding.core
	assert "session" not in vars(created)


def test_engine_core_factory_keeps_no_class_state(monkeypatch):
	(a, _), _ = _voices(monkeypatch)
	terminated = []

	class Core(RecordingCore):
		def terminate(self):
			terminated.append(self)

	class Voice(a.__class__):
		synth_driver_class = Core

	Voice.engine = "A"
	first, second = Voice.create_core(), Voice.create_core()
	assert isinstance(first, Core) and first is not second
	assert first.wv == "A"
	Voice.destroy_core(first)
	assert terminated == [first]
	assert {"core", "session", "_runtime_binding"}.isdisjoint(vars(Voice))
	assert isinstance(inspect.getattr_static(Voice, "core"), property)


def test_destroy_core_failure_propagates(monkeypatch):
	(a, _), _ = _voices(monkeypatch)

	class Core(RecordingCore):
		def terminate(self):
			raise RuntimeError("terminate failed")

	class Voice(a.__class__):
		synth_driver_class = Core

	core = Voice.create_core()
	with pytest.raises(RuntimeError, match="terminate failed"):
		Voice.destroy_core(core)


def test_cancel_during_activation_skips_speech(manager, buses):
	entered = threading.Event()
	release = threading.Event()
	core = RecordingCore()
	voice = types.SimpleNamespace(
		core=core,
		active=lambda: (entered.set(), release.wait(2)),
	)
	request = manager.new_request()
	append_speech(manager, request, voice, lambda: core.speak("stale"))
	assert manager.submit_request(request)
	assert entered.wait(1)
	try:
		cancel(manager, [voice])
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
	append_speech(manager, request, voice,
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
	append_speech(manager, request, voice, lambda: core.speak("never"))
	assert manager.submit_request(request)
	with pytest.raises(RuntimeError, match="apply failed"):
		request.tasks[0].future.result(timeout=1)
	assert buses.wait_for_outer_done(1) == [manager.owner]
	assert request.state.value == "failed"
	assert core.spoken == []


def test_preview_b_while_a_is_playing_then_cancel_restores_next_segment(monkeypatch):
	(a, b), config = _voices(monkeypatch)
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
	session = bind_core(core, a, b)
	a.active()
	playback = threading.Thread(target=core.speak, args=("A is speaking",))
	playback.start()
	assert core.entered.wait(1)
	current_writes = list(core.writes)
	manager_module = sys.modules["f4_test_worldvoice.voiceManager"]
	manager_instance = object.__new__(manager_module.VoiceManager)
	manager_instance._instanceCache = {a.name: a, b.name: b}
	manager_instance.settings = a._binding.settings
	manager_instance.getVoiceInstance = lambda name: manager_instance._instanceCache[name]
	panel_type = _load_panel_class(config)
	panel = panel_type()
	panel.disable = False
	panel._manager = manager_instance
	panel._editSession = manager_instance.settings.begin_edit()
	panel._dataToPercist = defaultdict(dict)
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
	manager_instance.settings = a._binding.settings
	updates = []
	original_update = b._state.update
	def record_update(**values):
		updates.append(values)
		original_update(**values)
	b._state.update = record_update
	a.update_settings(rate=72, pitch=60, volume=70, inflection=55, rateBoost=True)
	manager_instance.previewVoiceParameterConsistent(a)
	assert updates == [{"rate": 72, "pitch": 60, "volume": 70,
		"inflection": 55, "rateBoost": True}]
	assert (b.rate, b.pitch, b.volume) == (72, 60, 70)


@pytest.mark.parametrize("action", ["onVoiceChange", "onKeepParameterConsistentChange"])
def test_ui_consistency_copy_is_atomic_for_worker_activation(monkeypatch, action):
	(a, b), config = _voices(monkeypatch)
	a.update_settings(rate=72, pitch=61, volume=73, inflection=44, rateBoost=True)
	core = RecordingCore()
	bind_core(core, a, b)
	manager_module = sys.modules["f4_test_worldvoice.voiceManager"]
	manager_instance = object.__new__(manager_module.VoiceManager)
	manager_instance._instanceCache = {a.name: a, b.name: b}
	manager_instance.settings = a._binding.settings
	manager_instance._defaultVoiceInstance = a
	manager_instance.getVoiceInstance = lambda name: manager_instance._instanceCache[name]
	panel = _load_panel_class(config)()
	panel._manager = manager_instance
	panel._localesChoice = types.SimpleNamespace(GetCurrentSelection=lambda: 0)
	panel._locales = ["fr"]
	panel._voicesChoice = types.SimpleNamespace(GetCurrentSelection=lambda: 1)
	panel._voiceNamesByChoiceIndex = [a.name, b.name]
	panel._dataToPercist = defaultdict(dict)
	panel._keepParameterConsistentCheckBox = types.SimpleNamespace(GetValue=lambda: True)
	for name in ("_rateSlider", "_pitchSlider", "_volumeSlider", "_inflectionSlider",
			"_rateBoostCheckBox"):
		setattr(panel, name, types.SimpleNamespace(SetValue=lambda value: None))
	panel._updateVariantsSelection = lambda: None
	panel.sliderDisable = lambda: None
	panel.sliderEnable = lambda: None

	rate_written = threading.Event()
	release_copy = threading.Event()
	worker_done = threading.Event()
	errors = []
	original_update = b._state.update
	def gated_update(**values):
		with b._state._lock:
			original_update(**values)
			if values.get("rate") == 72 and not rate_written.is_set():
				rate_written.set()
				release_copy.wait(2)
	monkeypatch.setattr(b._state, "update", gated_update)

	def activate_b():
		try:
			b.active()
		except Exception as error:
			errors.append(error)
		finally:
			worker_done.set()

	ui_thread = threading.Thread(target=lambda: getattr(panel, action)(None))
	worker_thread = threading.Thread(target=activate_b)
	ui_thread.start()
	try:
		assert rate_written.wait(1)
		worker_thread.start()
		assert not worker_done.wait(0.05), "worker observed settings during the UI copy"
	finally:
		release_copy.set()
		ui_thread.join(1)
		if worker_thread.ident is not None:
			worker_thread.join(1)
	assert not ui_thread.is_alive() and not worker_thread.is_alive()
	assert errors == []
	assert (core.voice, core.rate, core.pitch, core.volume, core.inflection,
		core.rateBoost) == ("b", 72, 61, 73, 44, True)
