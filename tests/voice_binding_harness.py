"""Assemble real facade/settings/session boundaries for legacy caller tests."""

import importlib

from runtime_harness import FakeAdapter


def install_binding(driver, config):
	"""Bind voices of *driver* to one settings store; returns a voice factory."""
	package = driver.__name__.rsplit(".", 1)[0]
	models = importlib.import_module(package + ".runtime.models")
	settings = importlib.import_module(package + ".runtime.settings")
	sessions = importlib.import_module(package + ".runtime.session")
	facade = importlib.import_module(package + ".bridge.voiceFacade")
	repository = importlib.import_module(package + ".configRepository")
	store = settings.VoiceSettingsStore(repository.ConfigVoiceSettingsRepository(config.conf))
	session = sessions.EngineSession(FakeAdapter(), store)
	binding = facade.LegacyVoiceBinding(store, session, None)

	def voice(voice_id, key, language):
		engine = key.split(":", 1)[0]
		return driver.Voice(models.VoiceSpec(voice_id, key, key, language, engine, language), binding)

	return voice


def bind_core(core, *voices):
	"""Rebind *voices* to a real adapter and session that own *core*."""
	voice_class = type(voices[0])
	package = voice_class.__module__.split(".driver")[0]
	adapters = importlib.import_module(package + ".bridge.engineAdapter")
	sessions = importlib.import_module(package + ".runtime.session")
	facade = importlib.import_module(package + ".bridge.voiceFacade")
	old = voices[0]._binding
	by_name = {voice.name: voice for voice in voices}
	voice_class.supportedSettings = classmethod(
		lambda cls: [setting.id for setting in core.supportedSettings],
	)
	voice_class.create_core = classmethod(lambda cls: core)
	adapter = adapters.LegacyEngineAdapter(voice_class, by_name.__getitem__)
	session = sessions.EngineSession(adapter, old.settings)
	session.open()
	binding = facade.LegacyVoiceBinding(old.settings, session, core)
	for voice in voices:
		voice._binding = binding
	return session
