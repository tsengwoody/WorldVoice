"""VoiceManager answers role and consistency questions through its repository and policies."""

import sys
import types

from test_f4_voice_state import _load_voice_manager


def make_manager(monkeypatch, *, engine=True, voice=True):
	module = _load_voice_manager(monkeypatch)
	conf = sys.modules["config"].conf
	conf["WorldVoice"]["autoLanguageSwitching"].update(
		KeepMainLocaleEngineConsistent=engine, KeepMainLocaleVoiceConsistent=voice)
	conf["WorldVoice"]["role"] = {"fr": {"voice": "B:b"}, "en": {"voice": "X:gone"}}
	manager = object.__new__(module.VoiceManager)
	manager._init_policies()
	spec = module.VoiceSpec
	manager.catalog = module.VoiceCatalog.from_specs([spec("a", "A:a", "A", "en_US", "A", "en_US"),
		spec("b", "B:b", "B", "fr", "B", "fr"), spec("c", "A:c", "C", "fr", "A", "fr")])
	manager._defaultVoiceInstance = types.SimpleNamespace(name="A:a", engine="A", language="en_US")
	return module, conf, manager


def test_engine_filter_is_shared_by_every_locale_view(monkeypatch):
	_, _, manager = make_manager(monkeypatch, engine=True)
	assert manager.languages == ["en", "fr"]
	assert manager.localeToVoicesMap == {"en": ["A:a"], "fr": ["A:c"]}
	assert set(manager.localesToNamesMap) == {"en", "fr"}
	manager.engine_consistency.enabled = False
	assert manager.localeToVoicesMap == {"en": ["A:a"], "fr": ["A:c", "B:b"]}


def test_keep_engine_consistent_prunes_through_the_repository(monkeypatch):
	_, conf, manager = make_manager(monkeypatch, engine=False)
	manager.onKeepEngineConsistent()
	assert conf["WorldVoice"]["role"] == {"fr": {"voice": "B:b"}}


def test_main_locale_voice_follows_default_voice(monkeypatch):
	_, conf, manager = make_manager(monkeypatch, voice=True)
	manager.onKeepMainLocaleVoiceConsistent()
	assert conf["WorldVoice"]["role"]["en"] == {"voice": "A:a"}


def test_configured_voice_comes_from_the_repository(monkeypatch):
	module, conf, manager = make_manager(monkeypatch)
	manager.catalog = module.VoiceCatalog.from_specs([s for s in manager.table if s.name == "B:b"])
	manager._defaultVoiceInstance.name = "A:a"
	assert manager.getVoiceNameForLanguage("fr_CA") == "B:b"
	assert manager.getVoiceNameForLanguage("en") == "A:a"
