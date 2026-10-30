"""pick_engine_voice: the voice a speech engine switch picks (spec §3.3)."""

import importlib
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

WORLDVOICE = Path(__file__).resolve().parents[1] / "addon" / "synthDrivers" / "WorldVoice"
PACKAGE = "engine_filter_test_worldvoice"

# Table order: engine, language, name. B:x has no language and comes first in B.
VOICES = (
	("A", "de", "de_DE"),
	("A", "hk", "zh_HK"),
	("A", "tw", "zh_TW"),
	("A", "us", "en_US"),
	("B", "x", ""),
	("B", "en", "en"),
	("B", "pt", "pt"),
	("B", "br", "pt-br"),
)


@pytest.fixture
def modules(stub_modules, monkeypatch):
	for name in tuple(sys.modules):
		if name.startswith(PACKAGE + "."):
			monkeypatch.delitem(sys.modules, name)
	stub_modules.package(PACKAGE, WORLDVOICE)
	return (
		importlib.import_module(PACKAGE + ".voices.engineFilter"),
		importlib.import_module(PACKAGE + ".runtime.models"),
	)


@pytest.fixture
def pick(modules):
	return modules[0].pick_engine_voice


@pytest.fixture
def specs(modules):
	models = modules[1]
	return tuple(
		models.VoiceSpec(
			id=voice_id,
			name=f"{engine}:{voice_id}",
			description=f"{engine}:{voice_id}",
			language=language,
			engine=engine,
			locale=language,
		)
		for engine, voice_id, language in VOICES
	)


def test_the_role_voice_of_the_engine_wins(pick, specs):
	assert pick(specs, "A", "de", "A:tw") == "A:tw"


@pytest.mark.parametrize("role", ["B:en", "A:gone", None])
def test_a_role_voice_outside_the_engine_is_ignored(pick, specs, role):
	assert pick(specs, "A", "de", role) == "A:de"


def test_exact_language_comes_before_primary_language(pick, specs):
	# The primary language alone would pick A:hk, the first zh voice.
	assert pick(specs, "A", "zh_TW", None) == "A:tw"


@pytest.mark.parametrize(
	("language", "engine", "expected"),
	[("zh-TW", "A", "A:tw"), ("ZH_tw", "A", "A:tw"), ("pt_BR", "B", "B:br")],
)
def test_exact_match_folds_separator_and_case(pick, specs, language, engine, expected):
	assert pick(specs, engine, language, None) == expected


@pytest.mark.parametrize(
	("language", "engine", "expected"),
	[("en", "A", "A:us"), ("zh", "A", "A:hk"), ("en_GB", "B", "B:en"), ("pt_PT", "B", "B:pt")],
)
def test_primary_language_comes_before_the_first_voice(pick, specs, language, engine, expected):
	assert pick(specs, engine, language, None) == expected


def test_the_first_voice_is_the_fallback(pick, specs):
	assert pick(specs, "A", "fr", None) == "A:de"


def test_a_voice_without_language_is_matched_only_as_fallback(pick, specs):
	assert pick(specs, "B", "en", None) == "B:en"
	assert pick(specs, "B", "fr", None) == "B:x"


def test_an_engine_without_voices_raises(pick, specs):
	with pytest.raises(LookupError):
		pick(specs, "C", "en", None)


def _folded(language):
	return language.replace("-", "_").lower()


NAMES = [f"{engine}:{voice_id}" for engine, voice_id, _language in VOICES]
LANGUAGES = [language for _engine, _voice_id, language in VOICES]


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
	engine=st.sampled_from(["A", "B"]),
	language=st.one_of(st.sampled_from(LANGUAGES), st.text(max_size=6)),
	role=st.one_of(st.none(), st.sampled_from(NAMES)),
)
def test_the_pick_is_always_a_voice_of_the_engine(pick, specs, engine, language, role):
	result = pick(specs, engine, language, role)
	(chosen,) = [spec for spec in specs if spec.name == result]
	assert chosen.engine == engine
	own = [spec for spec in specs if spec.engine == engine]
	if role not in {spec.name for spec in own} and any(
		spec.language and _folded(spec.language) == _folded(language) for spec in own
	):
		assert _folded(chosen.language) == _folded(language)
