"""Role assignments live behind one repository."""

import pytest
from addon_loader import WORLDVOICE, alias_package, load_source
from hypothesis import HealthCheck, given, settings, strategies as st


def load_roles(monkeypatch):
	alias_package(monkeypatch, "roles_pkg", WORLDVOICE)
	return load_source(monkeypatch, "roles_pkg.voices.roles", WORLDVOICE / "voices/roles.py")


class Section(dict):
	"""Stands in for NVDA's AggregatedSection (not a dict subclass in NVDA)."""


@pytest.fixture
def roles(monkeypatch):
	module = load_roles(monkeypatch)
	conf = {
		"WorldVoice": {
			"role": {
				"en": Section(voice="A:en"),
				"zh": Section(voice="B:zh"),
				"ja": Section(),
				"legacy": "kept",
			},
		},
	}
	return module, conf, module.ConfigRoleRepository(lambda: conf)


def test_voice_for_prefers_exact_then_primary_locale(roles):
	_module, conf, repository = roles
	conf["WorldVoice"]["role"]["zh_TW"] = Section(voice="C:tw")
	assert repository.voice_for("zh_TW") == "C:tw"
	assert repository.voice_for("zh_CN") == "B:zh"
	assert repository.voice_for("ja") is None
	assert repository.voice_for("fr") is None


def test_voice_for_skips_an_unusable_voice_to_the_primary_locale(roles):
	_module, conf, repository = roles
	conf["WorldVoice"]["role"]["zh_TW"] = Section(voice="C:tw")
	assert repository.voice_for("zh_TW", lambda voice: voice != "C:tw") == "B:zh"
	assert repository.voice_for("zh_TW", lambda voice: voice == "C:tw") == "C:tw"


def test_voice_for_is_none_when_no_voice_is_usable(roles):
	_module, conf, repository = roles
	conf["WorldVoice"]["role"]["zh_TW"] = Section(voice="C:tw")
	assert repository.voice_for("zh_TW", lambda voice: False) is None
	asked = []
	assert repository.voice_for("ja", asked.append) is None
	# Only stored voices are asked about: ja has a section without a voice.
	assert asked == []


def test_assignments_ignore_scalars_and_voiceless_sections(roles):
	_, _, repository = roles
	assert repository.assignments() == {"en": "A:en", "zh": "B:zh"}


def test_save_rewrites_sections_and_keeps_scalars(roles):
	_, conf, repository = roles
	repository.save({"fr": "C:fr"})
	assert conf["WorldVoice"]["role"] == {"fr": {"voice": "C:fr"}, "legacy": "kept"}


def test_assign_adds_or_replaces_one_locale(roles):
	_, _conf, repository = roles
	repository.assign("zh", "C:zh")
	assert repository.assignments() == {"en": "A:en", "zh": "C:zh"}


def test_save_drops_role_sections_under_full_locale_keys(roles):
	# Versions before 2026-07-28 also wrote the full locale (zh_TW); the panel writes only
	# primary languages, and the lookup prefers the full locale, so such a key would shadow it.
	_, conf, repository = roles
	conf["WorldVoice"]["role"].update({"zh_TW": Section(voice="C:tw"), "fr_CA": "scalar"})
	repository.save({"zh": "B:zh", "zh_TW": "C:tw", "pt-br": "D:br"})
	assert conf["WorldVoice"]["role"] == {"zh": {"voice": "B:zh"}, "legacy": "kept", "fr_CA": "scalar"}


def test_assign_drops_a_stored_full_locale_role_so_the_primary_role_speaks(roles):
	_, conf, repository = roles
	conf["WorldVoice"]["role"]["zh_TW"] = Section(voice="C:tw")
	assert repository.voice_for("zh_TW") == "C:tw"
	repository.assign("zh", "C:zh")
	assert "zh_TW" not in conf["WorldVoice"]["role"]
	assert repository.voice_for("zh_TW") == "C:zh"
	assert repository.assignments() == {"en": "A:en", "zh": "C:zh"}


SAVE_LOCALES = ("en", "zh", "zh_TW", "zh-tw", "pt-br", "pt_BR", "pt")


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
	stored=st.dictionaries(
		st.sampled_from(SAVE_LOCALES),
		st.one_of(st.sampled_from(("A:x", "B:y")).map(lambda voice: Section(voice=voice)), st.just("scalar")),
	),
	saved=st.dictionaries(st.sampled_from(SAVE_LOCALES), st.sampled_from(("A:x", "B:y"))),
)
def test_save_keeps_primary_roles_and_scalars_and_no_full_locale_role(roles, stored, saved):
	module, _, _ = roles
	conf = {"WorldVoice": {"role": dict(stored)}}
	repository = module.ConfigRoleRepository(lambda: conf)
	repository.save(saved)
	role = conf["WorldVoice"]["role"]
	# The model: every primary-language assignment as a section, every stored scalar as it was.
	scalars = {locale: value for locale, value in stored.items() if value == "scalar"}
	sections = {locale: {"voice": voice} for locale, voice in saved.items() if locale.isalpha()}
	assert role == {**sections, **scalars}
