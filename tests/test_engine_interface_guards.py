"""Engines declare what they can do; nothing proves it by reflection or shares state on classes."""

from pathlib import Path

ADDON = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice"


def test_completion_policy_reads_declarations_instead_of_reflection():
	text = (ADDON / "compat/completionPolicies.py").read_text(encoding="utf-8")
	for removed in ("import sys", "signature", "sys.modules", "__module__", "FORCE_UNVERIFIED_DRAIN",
					"DRAIN_ENGINES", "_WASAPI_MODE_ENGINES", "def get_segment_drain_support",
					"def get_completion_contract", "def resolve_audio_mode"):
		assert removed not in text, removed
	assert "class CompletionPolicy" in text


def test_driver_selects_completion_through_its_policy():
	text = (ADDON / "__init__.py").read_text(encoding="utf-8")
	assert "from .compat.completionPolicies import CompletionPolicy\n" in text
	for removed in ("DRAIN_ENGINES", "get_completion_contract", "get_segment_drain_support", "resolve_audio_mode"):
		assert removed not in text, removed


def _addon_sources():
	for path in sorted(ADDON.rglob("*.py")):
		yield path.relative_to(ADDON).as_posix(), path.read_text(encoding="utf-8")


def test_engine_classes_hold_no_shared_core_or_session():
	import re

	found = []
	class_state = re.compile(r"\b(cls|Voice|voice_class|_voice_class|voiceInstance)\.(core|session|_runtime_binding)\s*=[^=]")
	for name, text in _addon_sources():
		for removed in ("engineOn", "engineOff", "_runtime_binding", "detach_alias", "is_source_owned"):
			if removed in text:
				found.append(f"{name}: {removed}")
		for number, line in enumerate(text.splitlines(), 1):
			if class_state.search(line):
				found.append(f"{name}:{number}: {line.strip()}")
	assert found == []
