"""The voice parameter names, their apply order and their confspec come from VOICE_PARAMETERS."""

from runtime_harness import load_settings_repository


def test_copyable_parameters_are_every_voice_parameter_but_the_variant(rt):
	assert rt.voice_settings.PARAMETER_NAMES == ("rate", "pitch", "volume", "inflection", "rateBoost")
	names = {name for name, _, _ in rt.voice_settings.VOICE_PARAMETERS}
	assert set(rt.voice_settings.PARAMETER_NAMES) == names - {"variant"}


def test_the_adapter_applies_every_copyable_parameter_rate_boost_first(rt, bridge_modules):
	order = bridge_modules.adapter.APPLY_ORDER
	assert sorted(order) == sorted(rt.voice_settings.PARAMETER_NAMES)
	assert order[0] == "rateBoost"


def test_voice_confspec_lists_exactly_the_stored_parameters(monkeypatch, rt):
	spec = load_settings_repository(monkeypatch, rt).VOICE_CONFSPEC
	assert set(spec) == {name for name, _, _ in rt.voice_settings.VOICE_PARAMETERS}
	for name in ("rate", "pitch", "volume", "inflection"):
		assert spec[name] == "integer(default=50,min=0,max=100)"
	assert spec["rateBoost"] == "boolean(default=False)"
	assert spec["variant"] == "string(default=default)"
