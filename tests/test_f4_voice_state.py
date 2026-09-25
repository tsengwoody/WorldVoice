import sys
import threading
import types

import pytest

from test_voice_settings_transaction import _create_voices, _load_panel_class
from test_worldvoice_lifecycle import _load_voice_manager
from test_worldvoice_request_manager import buses, manager, task_module


def _voices(monkeypatch):
	_load_voice_manager(monkeypatch, {})
	config = sys.modules["config"]
	monkeypatch.setattr(sys.modules["synthDriverHandler"], "getSynth",
		lambda: types.SimpleNamespace(name="WorldVoice"), raising=False)
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
	from lifecycle_test_worldvoice.driver.engineSession import EngineSession
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
	module = sys.modules["lifecycle_test_worldvoice.voiceManager"]
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
	from lifecycle_test_worldvoice.driver.engineSession import EngineSession
	core = RecordingCore()
	a.__class__.core = core
	session = EngineSession(core)
	a.session = b.session = session
	a.active()
	current_writes = list(core.writes)
	manager_module = sys.modules["lifecycle_test_worldvoice.voiceManager"]
	manager_instance = object.__new__(manager_module.VoiceManager)
	manager_instance._instanceCache = {a.name: a, b.name: b}
	manager_instance.getVoiceInstance = lambda name: manager_instance._instanceCache[name]
	panel_type = _load_panel_class(config, lambda: types.SimpleNamespace(name="WorldVoice"))
	panel = panel_type()
	panel.disable = False
	panel._manager = manager_instance
	panel._initialKeepEngineConsistent = False
	panel._voicesChoice = types.SimpleNamespace(GetCurrentSelection=lambda: 1)
	panel._voiceNamesByChoiceIndex = [a.name, b.name]
	panel._rateSlider = types.SimpleNamespace(GetValue=lambda: 72)
	panel._keepParameterConsistentCheckBox = types.SimpleNamespace(GetValue=lambda: True)
	panel.onSpeechRateSliderScroll(None)
	assert (a.rate, b.rate) == (72, 72)
	assert core.writes == current_writes
	b.active()
	assert (core.voice, core.rate) == ("b", 72)
	panel.onDiscard()
	assert (a.rate, b.rate) == (50, 50)
	b.active()
	assert (core.voice, core.rate) == ("b", 50)


def test_consistency_preview_updates_each_voice_in_one_batch(monkeypatch):
	(a, b), _ = _voices(monkeypatch)
	manager_module = sys.modules["lifecycle_test_worldvoice.voiceManager"]
	manager_instance = object.__new__(manager_module.VoiceManager)
	manager_instance._instanceCache = {a.name: a, b.name: b}
	updates = []
	b.update_settings = lambda **values: updates.append(values)
	a.update_settings(rate=72, pitch=60, volume=70, inflection=55, rateBoost=True)
	manager_instance.previewVoiceParameterConsistent(a)
	assert updates == [{"rate": 72, "pitch": 60, "volume": 70,
		"inflection": 55, "rateBoost": True}]
