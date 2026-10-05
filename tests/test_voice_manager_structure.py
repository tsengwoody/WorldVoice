"""Structures removed in phase 10a stay removed; the voice facade keeps only live members."""

import inspect
from pathlib import Path

import pytest

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


FORBIDDEN = {
	"synthDrivers/WorldVoice/voiceManager.py": [
		"self._sessions", "self._bindings", "self._specs", "READY_ENGINE_CLASS", "EngineType",
		"VoiceMeta", "groupByField", "keepMainLocaleEngineConsistent", "def ready",
		# The engine classes are only needed while opening engines.
		"self._engine_classes",
		# getVoiceNameForLanguage always names a voice; nothing asked for the instance.
		"getVoiceInstanceForLanguage",
	],
	"synthDrivers/WorldVoice/engine/__init__.py": ["READY_ENGINE_CLASS", "EngineType", "refresh_ready_engine_classes"],
	"globalPlugins/WorldVoice/speechSettingsDialog.py": ["EngineType", "_manager.ready"],
	"synthDrivers/WorldVoice/__init__.py": ["_completion_for", "_warn_drain_fallback", "_drainFallbacks"],
}


@pytest.mark.parametrize("path", sorted(FORBIDDEN))
def test_removed_structures_stay_removed(path):
	source = (ADDON / path).read_text(encoding="utf-8")
	assert [name for name in FORBIDDEN[path] if name in source] == []


def test_one_boolean_coercion():
	sources = [
		(ADDON / path).read_text(encoding="utf-8")
		for path in ("synthDrivers/WorldVoice/engine/__init__.py", "synthDrivers/WorldVoice/engine/discovery.py")
	]
	assert sum(source.count('{"false", "0", ""}') for source in sources) == 1
