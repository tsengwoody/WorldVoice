"""Pipeline stages resolve languages to voice names without creating voices."""

import sys
from types import SimpleNamespace

from test_pipeline_punctuation_pause import load_pipeline_module, punctuation_settings
from test_runtime_composition import composition  # noqa: F401 - pytest fixture


def voice(name, language):
	return SimpleNamespace(name=name, language=language)


def context(module, names, default):
	return module.SpeechContext(
		supports_roles=True, language=default.language, number_language="default",
		default_voice=default, voice_name_for_language=names.get,
	)


def test_dedupe_keeps_only_real_voice_switches(monkeypatch):
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	ctx = context(module, {"en": "A:en", "de": "A:de", "fr": None}, voice("A:en", "en"))
	L = module.LangChangeCommand
	sequence = ["x", L("de"), "y", L("fr"), "z", L(None), "w", L("en")]
	result = list(module.deduplicate_language_command(sequence, ctx))
	assert [getattr(command, "lang", command) for command in result] == ["x", "de", "y", "fr", "z", "w"]


def test_lang_cmd_to_voice_selects_names_and_falls_back(monkeypatch):
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	ctx = context(module, {"en": "R:en-role", "de": "A:de"}, voice("A:en", "en"))
	L = module.LangChangeCommand
	result = list(module.lang_cmd_to_voice([L("de"), "a", L("xx"), L(None)], ctx))
	# A None language looks up the default voice's language, which may be a role voice.
	assert result == [
		module.SelectVoice("A:de"), "a", module.SelectVoice("A:en"), module.SelectVoice("R:en-role"),
	]


def test_filters_do_not_create_voice_instances(composition, monkeypatch):  # noqa: F811
	composition.engine("ok")
	manager = composition.create()
	sys.modules["config"].conf["WorldVoice"]["role"] = {"zh": {"voice": "ok:b"}}
	assert "ok:b" not in manager._instanceCache
	before = dict(manager._instanceCache)
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	ctx = module.SpeechContext(
		supports_roles=True, language="en", number_language="default",
		default_voice=manager.defaultVoiceInstance, voice_name_for_language=manager.getVoiceNameForLanguage,
	)
	L = module.LangChangeCommand
	list(module.deduplicate_language_command(["a", L("zh"), "b", L("en"), "c"], ctx))
	assert list(module.lang_cmd_to_voice([L("zh"), "a"], ctx)) == [module.SelectVoice("ok:b"), "a"]
	assert manager._instanceCache == before
