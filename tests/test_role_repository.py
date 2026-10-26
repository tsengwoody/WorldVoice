"""Role assignments live behind one repository."""

import pytest
from addon_loader import WORLDVOICE, alias_package, load_source


def load_roles(monkeypatch):
	alias_package(monkeypatch, "roles_pkg", WORLDVOICE)
	return load_source(monkeypatch, "roles_pkg.roles", WORLDVOICE / "roles.py")


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


def test_prune_keeps_only_available_assignments(roles):
	_, conf, repository = roles
	repository.prune({"en": ["A:en"], "zh": ["X:zh"]})
	assert conf["WorldVoice"]["role"] == {"en": {"voice": "A:en"}, "legacy": "kept"}
