"""Engines declare what they can do; nothing proves it by reflection or shares state on classes."""

from pathlib import Path
import re

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


# Engines restored locally from storage/Neural-snapshot-*.zip are untracked and
# keep the old interface; the guard checks only the add-on's own sources.
UNTRACKED_ENGINES = ("driver/Neural/",)

_TARGETS = r"(?:cls|Voice|voice_class|_voice_class|voiceInstance|type\([^)]*\))"
_STATE = r"(?:core|session|_runtime_binding)"
CLASS_STATE = re.compile(
	rf"\b{_TARGETS}\.{_STATE}\s*=[^=]"
	rf"|\bsetattr\(\s*{_TARGETS}\s*,\s*[\"']{_STATE}[\"']",
)
REMOVED_NAMES = ("engineOn", "engineOff", "_runtime_binding", "detach_alias", "is_source_owned")


def _class_state_findings(root):
	found = []
	for path in sorted(root.rglob("*.py")):
		name = path.relative_to(root).as_posix()
		if name.startswith(UNTRACKED_ENGINES):
			continue
		text = path.read_text(encoding="utf-8")
		found.extend(f"{name}: {removed}" for removed in REMOVED_NAMES if removed in text)
		found.extend(
			f"{name}:{number}: {line.strip()}"
			for number, line in enumerate(text.splitlines(), 1)
			if CLASS_STATE.search(line)
		)
	return found


def test_engine_classes_hold_no_shared_core_or_session():
	assert _class_state_findings(ADDON) == []


def test_class_state_scan_skips_untracked_engines_and_catches_indirect_writes(tmp_path):
	neural = tmp_path / "driver/Neural/__init__.py"
	neural.parent.mkdir(parents=True)
	neural.write_text("class Voice:\n\tdef engineOn(cls):\n\t\tcls.core = object()\n", encoding="utf-8")
	other = tmp_path / "driver/Other/__init__.py"
	other.parent.mkdir(parents=True)
	other.write_text(
		'setattr(cls, "core", core)\n'
		"type(self).session = session\n"
		"setattr( voice_class , 'session', None)\n"
		"voice.core == other\n"
		"core = cls.core\n",
		encoding="utf-8",
	)
	assert _class_state_findings(tmp_path) == [
		'driver/Other/__init__.py:1: setattr(cls, "core", core)',
		"driver/Other/__init__.py:2: type(self).session = session",
		"driver/Other/__init__.py:3: setattr( voice_class , 'session', None)",
	]
