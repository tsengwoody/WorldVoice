"""Structures removed in phase 10a stay removed; the voice facade keeps only live members."""

import inspect
from pathlib import Path

from runtime_harness import rt  # noqa: F401 - pytest fixture
from test_runtime_legacy_adapter import compat  # noqa: F401 - pytest fixture

ADDON = Path(__file__).resolve().parents[1] / "addon"

FACADE_MEMBERS = {
	"id", "name", "language", "core",
	"rate", "pitch", "volume", "variant", "inflection", "rateBoost", "waitfactor",
	"snapshot", "update_settings", "loadParameter", "commit", "stop",
}


def test_voice_facade_exposes_only_live_members(compat):  # noqa: F811
	cls = compat.facade.VoiceFacade
	public = {name for name in dir(cls) if not name.startswith("_")}
	assert public | {"id", "name", "language"} == FACADE_MEMBERS
	assert list(inspect.signature(cls.__init__).parameters) == ["self", "spec", "binding"]


def test_create_core_does_not_tag_the_core():
	source = (ADDON / "synthDrivers/WorldVoice/driver/__init__.py").read_text(encoding="utf-8")
	assert ".wv" not in source
