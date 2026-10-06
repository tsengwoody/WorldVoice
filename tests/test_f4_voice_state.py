import importlib.util
import sys
import types
from pathlib import Path

from test_worldvoice_lifecycle import init_policies
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


def activate(voice):
	return voice._binding.session.activate(voice.name)


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


def test_worker_activation_uses_one_snapshot_per_segment(monkeypatch):
	(a, _), _ = _voices(monkeypatch)
	core = RecordingCore()
	bind_core(core, a)
	activate(a)
	first_count = len(core.writes)
	assert first_count > 0
	activate(a)
	assert len(core.writes) == first_count
	a.rate = 72
	# Activation reads one immutable snapshot; an edit during apply is deferred.
	original_apply = a.applyEngineSettings
	def edit_during_apply(core, snapshot):
		a.rate = 81
		original_apply(core, snapshot)
	a.applyEngineSettings = edit_during_apply
	activate(a)
	assert core.rate == 72
	activate(a)
	assert core.rate == 81
	assert len(core.writes) == first_count * 3


def test_consistency_preview_updates_each_voice_in_one_batch(monkeypatch):
	(a, b), _ = _voices(monkeypatch)
	manager_module = sys.modules["f4_test_worldvoice.voiceManager"]
	manager_instance = object.__new__(manager_module.VoiceManager)
	init_policies(manager_instance)
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


