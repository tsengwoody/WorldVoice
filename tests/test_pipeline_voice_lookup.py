"""Pipeline stages resolve languages to voice names without creating voices."""

import sys
from types import SimpleNamespace

from pipeline_harness import load_pipeline_module, punctuation_settings
from worldvoice_harness import voice_instances


def voice(name, language):
	return SimpleNamespace(name=name, language=language)


def context(module, names, default):
	return module.SpeechContext(
		supports_roles=True,
		language=default.language,
		number_language="default",
		default_voice_name=default.name,
		default_voice_language=default.language,
		voice_name_for_language=names.get,
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
		module.SelectVoice("A:de"),
		"a",
		module.SelectVoice("A:en"),
		module.SelectVoice("R:en-role"),
	]


def test_filters_do_not_create_voice_instances(composition, monkeypatch):
	composition.engine("ok")
	manager = composition.create()
	sys.modules["config"].conf["WorldVoice"]["role"] = {"zh": {"voice": "ok:b"}}
	assert "ok:b" not in voice_instances(manager)
	before = voice_instances(manager)
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	ctx = module.SpeechContext(
		supports_roles=True,
		language="en",
		number_language="default",
		default_voice_name=manager.defaultVoiceInstance.name,
		default_voice_language=manager.defaultVoiceInstance.language,
		voice_name_for_language=manager.getVoiceNameForLanguage,
	)
	L = module.LangChangeCommand
	list(module.deduplicate_language_command(["a", L("zh"), "b", L("en"), "c"], ctx))
	assert list(module.lang_cmd_to_voice([L("zh"), "a"], ctx)) == [module.SelectVoice("ok:b"), "a"]
	assert voice_instances(manager) == before


def test_voice_locale_follows_the_voice_for_the_language(composition):
	# Decided by the user (2026-10-22): the locale of the voice that speaks the language; with no
	# usable voice for it, getVoiceNameForLanguage gives the default voice, so its locale.
	# Voice b reports language "zh" with the full locale "zh-TW", as OneCore does: the locale is
	# what the symbol names need, not the bare language.
	composition.engine("ok", locales={"b": "zh-TW"})
	manager = composition.create()
	sys.modules["config"].conf["WorldVoice"]["role"] = {"zh": {"voice": "ok:b"}}
	assert manager.getVoiceSpec("ok:b").language == "zh"
	assert manager.getVoiceNameForLanguage("zh") == "ok:b"
	assert manager.getVoiceLocaleForLanguage("zh") == "zh-TW"
	assert (
		manager.getVoiceLocaleForLanguage("fr")
		== manager.getVoiceSpec(manager.defaultVoiceName).locale
		== "en"
	)


def test_voice_locale_is_none_for_a_voice_without_a_spec(composition, monkeypatch):
	composition.engine("ok")
	manager = composition.create()
	monkeypatch.setattr(manager, "getVoiceNameForLanguage", lambda language: "gone:x")
	assert manager.getVoiceLocaleForLanguage("zh") is None


def test_generic_context_has_no_voice_locale(monkeypatch):
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	assert module.GENERIC_CONTEXT.voice_locale_for_language("zh") is None
