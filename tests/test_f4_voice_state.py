import dataclasses
import inspect
import importlib.util
import sys
import threading
import types
from pathlib import Path

import pytest

from test_worldvoice_request_manager import buses, manager, task_module, append_speech, cancel  # noqa: F401 (fixtures)
from voice_binding_harness import install_binding, bind_core


WORLDVOICE = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice"


def _load_voice_manager(monkeypatch):
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
		VoiceInfo=lambda id, displayName, language: types.SimpleNamespace(id=id, displayName=displayName, language=language), getSynth=lambda: types.SimpleNamespace(name="WorldVoice")))
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


def _voices(monkeypatch):
	_load_voice_manager(monkeypatch)
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
	voice_meta = type(a._state.spec)("new", "A:new", "A:new", "en", "A", "en")
	manager_instance = object.__new__(module.VoiceManager)
	manager_instance._init_policies()
	manager_instance.catalog = module.VoiceCatalog.from_specs([voice_meta])
	manager_instance._resources = {"A": module.EngineResource(
		"A", a.__class__, None, a._binding.session, a._binding, voices=(voice_meta,), published=True)}
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




def test_consistency_preview_updates_each_voice_in_one_batch(monkeypatch):
	(a, b), _ = _voices(monkeypatch)
	manager_module = sys.modules["f4_test_worldvoice.voiceManager"]
	manager_instance = object.__new__(manager_module.VoiceManager)
	manager_instance._init_policies()
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


