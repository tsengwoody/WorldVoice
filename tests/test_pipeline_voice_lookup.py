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
	# The redundant L("en") is not the last command: what follows it must still be spoken.
	sequence = ["x", L("de"), "y", L("fr"), "z", L(None), "w", L("en"), "v"]
	result = list(module.deduplicate_language_command(sequence, ctx))
	assert [getattr(command, "lang", command) for command in result] == ["x", "de", "y", "fr", "z", "w", "v"]


def test_dedupe_starts_on_the_default_voice_when_no_voice_speaks_the_start_language(monkeypatch):
	# With no voice for start_language the default voice is already speaking, so reverting to the
	# default language is no switch.
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	ctx = context(module, {"en": "A:en", "fr": None}, voice("A:en", "en"))
	L = module.LangChangeCommand
	result = list(module.deduplicate_language_command([L(None), "w"], ctx, start_language="fr"))
	assert result == ["w"]


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
		default_voice_name=manager.default_voice_instance.name,
		default_voice_language=manager.default_voice_instance.language,
		voice_name_for_language=manager.get_voice_name_for_language,
	)
	L = module.LangChangeCommand
	list(module.deduplicate_language_command(["a", L("zh"), "b", L("en"), "c"], ctx))
	assert list(module.lang_cmd_to_voice([L("zh"), "a"], ctx)) == [module.SelectVoice("ok:b"), "a"]
	assert voice_instances(manager) == before


def test_voice_locale_follows_the_voice_for_the_language(composition):
	# Decided by the user (2026-10-22): the locale of the voice that speaks the language; with no
	# usable voice for it, get_voice_name_for_language gives the default voice, so its locale.
	# Voice b reports language "zh" with the full locale "zh-TW", as OneCore does: the locale is
	# what the symbol names need, not the bare language.
	composition.engine("ok", locales={"b": "zh-TW"})
	manager = composition.create()
	sys.modules["config"].conf["WorldVoice"]["role"] = {"zh": {"voice": "ok:b"}}
	assert manager.get_voice_spec("ok:b").language == "zh"
	assert manager.get_voice_name_for_language("zh") == "ok:b"
	assert manager.get_voice_locale_for_language("zh") == "zh-TW"
	assert (
		manager.get_voice_locale_for_language("fr")
		== manager.get_voice_spec(manager.default_voice_name).locale
		== "en"
	)


def test_voice_locale_is_none_for_a_voice_without_a_spec(composition, monkeypatch):
	composition.engine("ok")
	manager = composition.create()
	monkeypatch.setattr(manager, "get_voice_name_for_language", lambda language: "gone:x")
	assert manager.get_voice_locale_for_language("zh") is None


def test_generic_context_has_no_voice_locale(monkeypatch):
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	assert module.GENERIC_CONTEXT.voice_locale_for_language("zh") is None
