"""VoiceManager answers role and consistency questions through its repository and policies."""

import sys
import types

from test_f4_voice_state import _load_voice_manager


def make_manager(monkeypatch, *, engine=True, voice=True):
	module = _load_voice_manager(monkeypatch, {})
	conf = sys.modules["config"].conf
	conf["WorldVoice"]["autoLanguageSwitching"].update(
		KeepMainLocaleEngineConsistent=engine, KeepMainLocaleVoiceConsistent=voice)
	conf["WorldVoice"]["role"] = {"fr": {"voice": "B:b"}, "en": {"voice": "X:gone"}}
	manager = object.__new__(module.VoiceManager)
	manager._init_policies()
	spec = module.VoiceMeta
	manager.table = [spec("a", "A:a", "A", "en_US", "A", "en_US"), spec("b", "B:b", "B", "fr", "B", "fr"),
		spec("c", "A:c", "C", "fr", "A", "fr")]
	manager._defaultVoiceInstance = types.SimpleNamespace(name="A:a", engine="A", language="en_US")
	return module, conf, manager


def test_engine_filter_is_shared_by_every_locale_view(monkeypatch):
	_, _, manager = make_manager(monkeypatch, engine=True)
	assert manager.languages == ["en", "fr"]
	assert manager.localeToVoicesMap == {"en": ["A:a"], "fr": ["A:c"]}
	assert set(manager.localesToNamesMap) == {"en", "fr"}
	manager.keepMainLocaleEngineConsistent = False
	assert manager.engine_consistency.enabled is False
	assert manager.localeToVoicesMap == {"en": ["A:a"], "fr": ["B:b", "A:c"]}


def test_keep_engine_consistent_prunes_through_the_repository(monkeypatch):
	_, conf, manager = make_manager(monkeypatch, engine=False)
	manager.onKeepEngineConsistent()
	assert conf["WorldVoice"]["role"] == {"fr": {"voice": "B:b"}}


def test_main_locale_voice_follows_default_voice(monkeypatch):
	_, conf, manager = make_manager(monkeypatch, voice=True)
	manager.onKeepMainLocaleVoiceConsistent()
	assert conf["WorldVoice"]["role"]["en"] == {"voice": "A:a"}


def test_configured_voice_comes_from_the_repository(monkeypatch):
	_, conf, manager = make_manager(monkeypatch)
	manager._voiceInfos = {"B:b": object()}
	manager._defaultVoiceInstance.name = "A:a"
	assert manager.getVoiceNameForLanguage("fr_CA") == "B:b"
	assert manager.getVoiceNameForLanguage("en") == "A:a"
