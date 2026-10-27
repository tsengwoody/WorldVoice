"""The role panel's state and transaction, without wx."""

import sys
import threading
import types

import pytest
from addon_loader import ADDON, load_source
from nvda_stubs import StubModules
from voice_binding_harness import bind_core
from waiting import HOLD_TIMEOUT, WAIT_TIMEOUT, stays_unset
from worldvoice_harness import (
	RecordingCore,
	create_f4_voices,
	init_policies,
	load_f4_voice_manager,
	settings_baseline,
)

PRESENTER = ADDON / "globalPlugins/WorldVoice/rolePresenter.py"


def load_presenter(monkeypatch, voice_settings):
	"""Load the presenter against the runtime voiceSettings module the manager under test uses."""
	stub = StubModules(monkeypatch)
	for package in ("synthDrivers", "synthDrivers.WorldVoice", "synthDrivers.WorldVoice.runtime"):
		stub.module(package, __path__=[])
	monkeypatch.setitem(sys.modules, "synthDrivers.WorldVoice.runtime.voiceSettings", voice_settings)
	package = voice_settings.__name__.rsplit(".", 2)[0]
	monkeypatch.setitem(
		sys.modules,
		"synthDrivers.WorldVoice.voices.roles",
		sys.modules[f"{package}.voices.roles"],
	)
	return load_source(monkeypatch, "role_presenter_under_test", PRESENTER).RolePanelPresenter


@pytest.fixture
def env(monkeypatch):
	module = load_f4_voice_manager(monkeypatch)
	config = sys.modules["config"]
	conf = config.conf
	conf["WorldVoice"]["autoLanguageSwitching"].update(
		KeepMainLocaleEngineConsistent=False,
		KeepMainLocaleVoiceConsistent=False,
		KeepMainLocaleParameterConsistent=False,
	)
	conf["WorldVoice"]["role"] = {"en": {"voice": "A:a"}}
	a, b = create_f4_voices(monkeypatch, config)
	# Real engine classes declare their engine; the harness base class does not.
	monkeypatch.setattr(type(a), "engine", "A")
	c = type(a)(type(a._state.spec)("c", "A:c", "A:c", "en", "A", "en"), a._binding)
	voices = {voice.name: voice for voice in (a, b, c)}
	manager = object.__new__(module.VoiceManager)
	init_policies(manager)
	manager.settings = a._binding.settings
	manager._instance_cache = dict(voices)
	manager.catalog = module.VoiceCatalog.from_specs(voice._state.spec for voice in voices.values())
	manager._default_voice_instance = a
	manager.get_voice_instance = voices.__getitem__
	conf["speech"] = {"WorldVoice": {"voice": a.name}}
	switched = []

	def set_main_voice(name):
		switched.append(name)
		manager.default_voice_name = name
		conf["speech"]["WorldVoice"]["voice"] = name

	voice_settings = sys.modules[module.__package__.removesuffix(".voices") + ".runtime.voiceSettings"]
	presenter = load_presenter(monkeypatch, voice_settings)(
		manager,
		speech_section=lambda: conf["speech"]["WorldVoice"],
		set_main_voice=set_main_voice,
	)
	return types.SimpleNamespace(
		presenter=presenter,
		manager=manager,
		conf=conf,
		a=a,
		b=b,
		c=c,
		switched=switched,
		config=config,
	)


def test_parameter_preview_is_undone_by_discard(env):
	env.presenter.set_parameter_consistency(True)
	env.presenter.set_parameter(env.a.name, "rate", 72)
	assert (env.a.rate, env.b.rate) == (72, 72)
	env.presenter.discard()
	assert (env.a.rate, env.b.rate) == (50, 50)
	assert env.conf["WorldVoice"]["voices"][env.a.name]["rate"] == 50
	assert env.conf["WorldVoice"]["voices"][env.b.name]["rate"] == 50


def test_unticking_parameter_consistency_restores_the_previewed_voices(env):
	env.b.rate = 64
	env.presenter.set_parameter_consistency(True)
	assert env.b.rate == env.a.rate == 50
	env.presenter.set_parameter_consistency(False)
	assert env.b.rate == 64
	env.presenter.apply()
	assert env.conf["WorldVoice"]["voices"][env.b.name]["rate"] == 64
	assert env.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"] is False


def test_unticking_a_consistency_that_was_already_on_changes_nothing(env):
	env.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"] = True
	env.presenter.discard()  # re-read pending flags from config
	env.b.rate = 64
	env.presenter.set_parameter_consistency(False)
	assert env.b.rate == 64
	env.presenter.set_parameter_consistency(True)
	assert env.b.rate == 50


def test_engine_consistency_preview_cancel_and_apply(env):
	env.conf["WorldVoice"]["role"]["fr"] = {"voice": env.b.name}
	env.presenter.set_engine_consistency(True)
	assert env.manager.engine_consistency.preview is True
	assert [locale for locale, _ in env.presenter.locales()] == ["en"]
	assert env.conf["WorldVoice"]["role"]["fr"]["voice"] == env.b.name
	assert env.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleEngineConsistent"] is False
	env.presenter.discard()
	assert env.manager.engine_consistency.preview is None
	assert [locale for locale, _ in env.presenter.locales()] == ["en", "fr"]
	env.presenter.set_engine_consistency(True)
	env.presenter.apply()
	assert env.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleEngineConsistent"] is True
	assert "fr" not in env.conf["WorldVoice"]["role"]
	env.presenter.discard()
	assert env.manager.engine_consistency.enabled is True
	assert env.manager.engine_consistency.preview is None


def test_discard_after_apply_rereads_saved_flags(env):
	env.presenter.set_engine_consistency(True)
	env.presenter.apply()
	assert env.manager.engine_consistency.preview is None
	env.presenter.set_engine_consistency(False)
	assert env.manager.engine_consistency.preview is False
	env.presenter.discard()
	assert env.manager.engine_consistency.preview is None
	assert env.presenter.keep_engine is True


def test_late_voice_is_restored_on_discard(env):
	late = env.manager.settings.ensure(
		type(env.a._state.spec)("late", "Fake:late", "Fake:late", "en", "Fake", "en"),
	)
	late.update(rate=81)
	env.b.rate = 72
	env.presenter.discard()
	assert late.get("rate") == 50
	assert env.b.rate == 50
	assert env.conf["WorldVoice"]["voices"][env.b.name]["rate"] == 50


def test_apply_rebases_voice_and_role_edit_state(env):
	env.a.rate = 72
	env.b.rate = 64
	env.presenter.select_voice("fr", env.b.name)
	env.presenter.apply()
	assert env.conf["WorldVoice"]["voices"][env.b.name]["rate"] == 64
	assert env.conf["WorldVoice"]["role"]["fr"] == {"voice": env.b.name}
	env.a.rate = 81
	env.b.rate = 90
	env.presenter.select_voice("fr", "")
	env.presenter.discard()
	assert (env.a.rate, env.b.rate) == (72, 64)
	assert env.conf["WorldVoice"]["role"]["fr"] == {"voice": env.b.name}
	assert env.presenter.selected_voice("fr") == env.b.name


def test_main_locale_voice_consistency_switches_then_mirrors_new_voice(env):
	env.conf["WorldVoice"]["role"]["fr"] = {"voice": env.b.name}
	env.presenter.set_voice_consistency(True)
	env.presenter.select_voice("en", env.c.name)
	env.c.rate = 72
	env.presenter.apply()
	assert env.switched == [env.c.name]
	assert env.manager.default_voice_name == env.c.name
	assert env.conf["speech"]["WorldVoice"]["voice"] == env.c.name
	assert env.conf["speech"]["WorldVoice"]["rate"] == 72  # D4: mirrored from the new main voice
	assert env.conf["WorldVoice"]["role"] == {"en": {"voice": env.c.name}, "fr": {"voice": env.b.name}}

	env.presenter.apply()
	assert env.switched == [env.c.name]

	env.presenter.select_voice("en", env.a.name)
	env.presenter.select_voice("fr", "")
	env.c.rate = 81
	env.presenter.discard()
	assert env.c.rate == 72
	assert env.manager.default_voice_name == env.c.name
	assert env.conf["WorldVoice"]["role"] == {"en": {"voice": env.c.name}, "fr": {"voice": env.b.name}}


def test_save_failure_writes_nothing_else_and_keeps_pending(env, monkeypatch):
	env.presenter.select_voice("fr", env.b.name)
	env.presenter.set_engine_consistency(True)
	env.a.rate = 72

	def fail_save(*args):
		raise OSError("save failed")

	monkeypatch.setattr(env.manager.settings._repository, "save", fail_save)
	speech_before = dict(env.conf["speech"]["WorldVoice"])
	with pytest.raises(OSError, match="save failed"):
		env.presenter.apply()
	assert env.a.rate == 72
	assert settings_baseline(env.a, "rate") == 50
	assert env.conf["WorldVoice"]["role"] == {"en": {"voice": env.a.name}}
	assert env.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleEngineConsistent"] is False
	assert env.conf["speech"]["WorldVoice"] == speech_before
	assert env.presenter.selected_voice("fr") == env.b.name
	env.presenter.discard()
	assert env.a.rate == 50
	assert env.manager.engine_consistency.enabled is False
	assert env.manager.engine_consistency.preview is None


def test_apply_previews_consistency_before_saving(env):
	env.presenter.set_parameter_consistency(True)
	env.a.rate = 66  # edited after the preview, e.g. via the main synth
	env.presenter.apply()
	assert env.conf["WorldVoice"]["voices"][env.b.name]["rate"] == 66
	env.b.rate = 90
	env.presenter.discard()
	assert env.b.rate == 66


def test_queries_go_through_the_manager(env):
	env.manager.get_voice_capabilities = lambda key: types.SimpleNamespace(
		settings={"rateBoost", "inflection"},
	)
	env.manager.get_voice_variants = lambda key: ({"id": "bright", "name": "Bright"},)
	assert env.presenter.capabilities(env.a.name) == {"rateBoost", "inflection"}
	assert env.presenter.variants(env.a.name) == ["default", "bright"]
	assert env.presenter.voices("en") == [(env.a.name, env.a.name), (env.c.name, env.c.name)]
	assert env.presenter.selected_voice("en") == env.a.name
	assert env.presenter.selected_voice("fr") == ""


def test_select_voice_copies_main_parameters_atomically(env, monkeypatch):
	env.a.update_settings(rate=72, pitch=61, volume=73, inflection=44, rateBoost=True)
	core = RecordingCore()
	bind_core(core, env.a, env.b)
	env.presenter.set_parameter_consistency(True)
	rate_written, release_copy, worker_done = threading.Event(), threading.Event(), threading.Event()
	errors = []
	original_update = env.b._state.update

	def gated_update(**values):
		with env.b._state._lock:
			original_update(**values)
			if values.get("rate") == 72 and not rate_written.is_set():
				rate_written.set()
				release_copy.wait(HOLD_TIMEOUT)

	env.b.rate = 10
	monkeypatch.setattr(env.b._state, "update", gated_update)

	def activate_b():
		try:
			env.b._binding.session.activate(env.b.name)
		except Exception as error:  # noqa: BLE001 - collected and asserted in the test thread
			errors.append(error)
		finally:
			worker_done.set()

	ui_thread = threading.Thread(target=lambda: env.presenter.select_voice("fr", env.b.name))
	worker_thread = threading.Thread(target=activate_b)
	ui_thread.start()
	try:
		assert rate_written.wait(WAIT_TIMEOUT)
		worker_thread.start()
		stays_unset(worker_done, message="worker observed settings during the UI copy")
	finally:
		release_copy.set()
		ui_thread.join(WAIT_TIMEOUT)
		if worker_thread.ident is not None:
			worker_thread.join(WAIT_TIMEOUT)
	assert errors == []


def test_preview_b_while_a_is_playing_then_discard_restores_next_segment(env):
	a, b = env.a, env.b

	class BlockingCore(RecordingCore):
		def __init__(self):
			super().__init__()
			self.entered = threading.Event()
			self.release = threading.Event()

		def speak(self, text):
			super().speak(text)
			self.entered.set()
			self.release.wait(HOLD_TIMEOUT)

	core = BlockingCore()
	bind_core(core, a, b)
	a._binding.session.activate(a.name)
	playback = threading.Thread(target=core.speak, args=("A is speaking",))
	playback.start()
	assert core.entered.wait(WAIT_TIMEOUT)
	current_writes = list(core.writes)
	try:
		env.presenter.set_parameter_consistency(True)
		env.presenter.set_parameter(b.name, "rate", 72)
		assert (a.rate, b.rate) == (72, 72)
		assert playback.is_alive()
		assert core.spoken == ["A is speaking"]
		assert core.writes == current_writes
	finally:
		core.release.set()
		playback.join(WAIT_TIMEOUT)
	assert not playback.is_alive()
	b._binding.session.activate(b.name)
	assert (core.voice, core.rate) == ("b", 72)
	env.presenter.discard()
	assert (a.rate, b.rate) == (50, 50)
	b._binding.session.activate(b.name)
	assert (core.voice, core.rate) == ("b", 50)


def test_unticking_restores_voices_loaded_during_the_preview(env):
	env.presenter.set_parameter_consistency(True)
	late = env.manager.settings.ensure(type(env.a._state.spec)("late", "A:late", "A:late", "en", "A", "en"))
	env.presenter.set_parameter(env.a.name, "rate", 72)
	assert late.get("rate") == 72
	env.presenter.set_parameter_consistency(False)
	assert late.get("rate") == 50
	assert env.a.rate == 50


def test_closing_the_panel_drops_an_unsaved_engine_preview(env):
	env.presenter.set_engine_consistency(True)
	env.presenter.close()
	assert env.manager.engine_consistency.preview is None
