"""Assemble real facade/settings/session boundaries for legacy caller tests."""

import importlib

from runtime_harness import FakeAdapter


def install_binding(driver, config):
    package = driver.__name__.rsplit(".", 1)[0]
    models = importlib.import_module(package + ".runtime.models")
    settings = importlib.import_module(package + ".runtime.settings")
    sessions = importlib.import_module(package + ".runtime.session")
    facade = importlib.import_module(package + ".compat.voiceFacade")
    repository = importlib.import_module(package + ".configRepository")
    store = settings.VoiceSettingsStore(repository.ConfigVoiceSettingsRepository(config.conf, lambda: "WorldVoice"))

    def spec_for(key):
        engine, voice_id = key.split(":", 1)
        language = "fr" if voice_id == "b" else "en"
        return models.VoiceSpec(voice_id, key, key, language, engine, language)

    session = sessions.EngineSession(FakeAdapter(), store)
    driver.Voice._runtime_binding = facade.LegacyVoiceBinding(store, session, spec_for)
    return store


def bind_core(core, *voices):
    voice_class = type(voices[0])
    package = voice_class.__module__.split(".driver")[0]
    adapters = importlib.import_module(package + ".compat.engineAdapter")
    sessions = importlib.import_module(package + ".runtime.session")
    facade = importlib.import_module(package + ".compat.voiceFacade")
    old = voices[0]._binding
    by_name = {voice.name: voice for voice in voices}
    voice_class.core = core
    voice_class.supportedSettings = classmethod(lambda cls: [setting.id for setting in core.supportedSettings])
    adapter = adapters.LegacyEngineAdapter(voice_class, by_name.__getitem__)
    session = sessions.EngineSession(adapter, old.settings)
    session.open()
    binding = facade.LegacyVoiceBinding(old.settings, session, old.spec_for)
    voice_class._runtime_binding = binding
    for voice in voices:
        voice._binding = binding
        voice.session = session
    return session
