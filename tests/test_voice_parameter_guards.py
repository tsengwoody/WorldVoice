"""The voice parameter names, their apply order and their confspec come from VOICE_PARAMETERS."""

import ast
from pathlib import Path

from runtime_harness import load_config_repository, rt  # noqa: F401 - pytest fixture
from test_runtime_legacy_adapter import compat  # noqa: F401 - pytest fixture

ADDON = Path(__file__).resolve().parents[1] / "addon"
WORLDVOICE = ADDON / "synthDrivers/WorldVoice"


def test_copyable_parameters_are_every_voice_parameter_but_the_variant(rt):  # noqa: F811
	assert rt.settings.PARAMETER_NAMES == ("rate", "pitch", "volume", "inflection", "rateBoost")
	names = {name for name, _, _ in rt.settings.VOICE_PARAMETERS}
	assert set(rt.settings.PARAMETER_NAMES) == names - {"variant"}


def test_the_adapter_applies_every_copyable_parameter_rate_boost_first(rt, compat):  # noqa: F811
	order = compat.adapter.APPLY_ORDER
	assert sorted(order) == sorted(rt.settings.PARAMETER_NAMES)
	assert order[0] == "rateBoost"


def test_voice_confspec_lists_exactly_the_stored_parameters(monkeypatch, rt):  # noqa: F811
	spec = load_config_repository(monkeypatch, rt).VOICE_CONFSPEC
	assert set(spec) == {name for name, _, _ in rt.settings.VOICE_PARAMETERS}
	for name in ("rate", "pitch", "volume", "inflection"):
		assert spec[name] == "integer(default=50,min=0,max=100)"
	assert spec["rateBoost"] == "boolean(default=False)"
	assert spec["variant"] == "string(default=default)"


def test_driver_voices_confspec_comes_from_the_repository():
	tree = ast.parse((WORLDVOICE / "__init__.py").read_text(encoding="utf-8"))
	voices = next(
		value
		for node in ast.walk(tree)
		if isinstance(node, ast.Dict)
		for key, value in zip(node.keys, node.values)
		if isinstance(key, ast.Constant) and key.value == "voices"
	)
	assert ast.unparse(voices) == "{'__many__': dict(VOICE_CONFSPEC)}"


def test_no_module_keeps_its_own_parameter_list():
	for path in ("synthDrivers/WorldVoice/mainLocalePolicy.py", "globalPlugins/WorldVoice/rolePresenter.py"):
		assert "PARAMETER_NAMES = (" not in (ADDON / path).read_text(encoding="utf-8")
