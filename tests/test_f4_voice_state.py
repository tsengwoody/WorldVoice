import sys

from voice_binding_harness import bind_core
from worldvoice_harness import RecordingCore, create_f4_voices, init_policies, load_f4_voice_manager


def activate(voice):
	return voice._binding.session.activate(voice.name)


def _voices(monkeypatch):
	load_f4_voice_manager(monkeypatch)
	config = sys.modules["config"]
	return create_f4_voices(monkeypatch, config), config


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
	assert updates == [
		{
			"rate": 72,
			"pitch": 60,
			"volume": 70,
			"inflection": 55,
			"rateBoost": True,
		},
	]
	assert (b.rate, b.pitch, b.volume) == (72, 60, 70)
