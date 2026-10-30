"""VoiceManager answers role and consistency questions through its repository and policies."""

import copy
import sys
import types

from hypothesis import HealthCheck, given, settings, strategies as st
from worldvoice_harness import init_policies, load_f4_voice_manager


def make_manager(monkeypatch, *, engine=True, voice=True):
	module = load_f4_voice_manager(monkeypatch)
	conf = sys.modules["config"].conf
	conf["WorldVoice"]["autoLanguageSwitching"].update(
		keepMainLocaleEngineConsistent=engine,
		keepMainLocaleVoiceConsistent=voice,
	)
	conf["WorldVoice"]["role"] = {"fr": {"voice": "B:b"}, "en": {"voice": "X:gone"}}
	manager = object.__new__(module.VoiceManager)
	init_policies(manager)
	spec = module.VoiceSpec
	manager.catalog = module.VoiceCatalog.from_specs(
		[
			spec("a", "A:a", "A", "en_US", "A", "en_US"),
			spec("b", "B:b", "B", "fr", "B", "fr"),
			spec("c", "A:c", "C", "fr", "A", "fr"),
		],
	)
	manager._default_voice_instance = types.SimpleNamespace(name="A:a", engine="A", language="en_US")
	return module, conf, manager


def test_engine_filter_is_shared_by_every_locale_view(monkeypatch):
	_, _, manager = make_manager(monkeypatch, engine=True)
	assert manager.languages == ["en", "fr"]
	assert manager.locale_to_voices_map == {"en": ["A:a"], "fr": ["A:c"]}
	assert set(manager.locales_to_names_map) == {"en", "fr"}
	manager.engine_consistency.enabled = False
	assert manager.locale_to_voices_map == {"en": ["A:a"], "fr": ["A:c", "B:b"]}


def test_main_locale_voice_follows_default_voice(monkeypatch):
	_, conf, manager = make_manager(monkeypatch, voice=True)
	manager.on_keep_main_locale_voice_consistent()
	assert conf["WorldVoice"]["role"]["en"] == {"voice": "A:a"}


def add_voice(module, manager, *specs):
	manager.catalog = module.VoiceCatalog.from_specs([*manager.table, *specs])


def test_a_role_of_another_engine_is_kept_but_skipped(monkeypatch):
	_, conf, manager = make_manager(monkeypatch, engine=True)
	before = copy.deepcopy(conf["WorldVoice"]["role"])
	# fr's role B:b belongs to engine B, the main voice A:a to engine A.
	assert manager.get_voice_name_for_language("fr_CA") == "A:a"
	assert conf["WorldVoice"]["role"] == before
	conf["WorldVoice"]["role"]["fr"] = {"voice": "A:c"}
	assert manager.get_voice_name_for_language("fr_CA") == "A:c"


def test_without_engine_consistency_any_engines_role_speaks(monkeypatch):
	_, _conf, manager = make_manager(monkeypatch, engine=False)
	assert manager.get_voice_name_for_language("fr_CA") == "B:b"
	assert manager.get_voice_name_for_language("en") == "A:a"  # X:gone is not available


def test_a_missing_role_voice_is_kept_and_speaks_when_back(monkeypatch):
	module, conf, manager = make_manager(monkeypatch, engine=True)
	assert manager.get_voice_name_for_language("en") == "A:a"
	assert conf["WorldVoice"]["role"]["en"] == {"voice": "X:gone"}
	add_voice(module, manager, module.VoiceSpec("gone", "X:gone", "X", "en", "A", "en"))
	assert manager.get_voice_name_for_language("en") == "X:gone"


def test_a_skipped_full_locale_role_falls_back_to_the_primary_role(monkeypatch):
	_, conf, manager = make_manager(monkeypatch, engine=True)
	conf["WorldVoice"]["role"] = {"fr_CA": {"voice": "B:b"}, "fr": {"voice": "A:c"}}
	assert manager.get_voice_name_for_language("fr_CA") == "A:c"


def test_initial_voice_is_the_available_role_of_any_engine(monkeypatch):
	# Before NVDA sets a voice there is no main engine to keep consistent with (spec D3).
	_, _conf, manager = make_manager(monkeypatch, engine=True)
	assert manager.initial_voice_name("fr_CA") == "B:b"
	assert manager.get_voice_name_for_language("fr_CA") == "A:a"
	assert manager.initial_voice_name("en") == "A:a"  # X:gone is not available


ROLE_LOCALES = ("en", "fr", "fr_CA", "de")
ROLE_VOICES = ("A:a", "B:b", "A:c", "X:gone")


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
	roles=st.dictionaries(st.sampled_from(ROLE_LOCALES), st.sampled_from(ROLE_VOICES)),
	engine=st.booleans(),
	main=st.sampled_from(("A:a", "B:b")),
	language=st.sampled_from((*ROLE_LOCALES, "en_US")),
)
def test_lookups_never_write_and_speak_only_admitted_voices(monkeypatch, roles, engine, main, language):
	with monkeypatch.context() as patch:
		_, conf, manager = make_manager(patch, engine=engine)
		spec = manager.get_voice_spec(main)
		manager._default_voice_instance = types.SimpleNamespace(
			name=main,
			engine=spec.engine,
			language=spec.language,
		)
		conf["WorldVoice"]["role"] = {locale: {"voice": voice} for locale, voice in roles.items()}
		before = copy.deepcopy(conf["WorldVoice"]["role"])
		name = manager.get_voice_name_for_language(language)
		assert conf["WorldVoice"]["role"] == before
		# The model: the first of the full then primary locale's roles whose voice is installed
		# and, with engine consistency on, of the main voice's engine; else the main voice.
		engines = {"A:a": "A", "B:b": "B", "A:c": "A"}
		speaking = [
			roles[locale]
			for locale in (language, language.split("_")[0])
			if locale in roles
			and roles[locale] in engines
			and (not engine or engines[roles[locale]] == spec.engine)
		]
		assert name == (speaking[0] if speaking else main)
