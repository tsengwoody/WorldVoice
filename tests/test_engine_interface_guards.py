"""Engines declare what they can do; nothing proves it by reflection or shares state on classes."""

from pathlib import Path
import re

ADDON = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice"


# Engines restored locally from storage/Neural-snapshot-*.zip are untracked and
# keep the old interface; the guard checks only the add-on's own sources.
UNTRACKED_ENGINES = ("driver/Neural/",)

_TARGETS = r"(?:cls|Voice|voice_class|_voice_class|voiceInstance|type\([^)]*\))"
_STATE = r"(?:core|session|_runtime_binding)"
CLASS_STATE = re.compile(
	rf"\b{_TARGETS}\.{_STATE}\s*=[^=]"
	rf"|\bsetattr\(\s*{_TARGETS}\s*,\s*[\"']{_STATE}[\"']",
)


def _class_state_findings(root):
	found = []
	for path in sorted(root.rglob("*.py")):
		name = path.relative_to(root).as_posix()
		if name.startswith(UNTRACKED_ENGINES):
			continue
		text = path.read_text(encoding="utf-8")
		found.extend(
			f"{name}:{number}: {line.strip()}"
			for number, line in enumerate(text.splitlines(), 1)
			if CLASS_STATE.search(line)
		)
	return found


def test_engine_classes_hold_no_shared_core_or_session():
	assert _class_state_findings(ADDON) == []
