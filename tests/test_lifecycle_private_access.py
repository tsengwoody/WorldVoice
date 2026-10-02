"""Engine wrappers use the lifecycle's public API, never its private state."""

import re
from pathlib import Path

DRIVERS = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice/driver"
LIFECYCLE_OBJECTS = r"(?:operation|lifecycle|_lifecycle|_segmentLifecycle)"
PRIVATE_ACCESS = re.compile(rf"(?<![A-Za-z0-9]){LIFECYCLE_OBJECTS}\._(\w+)")
PRIVATE_GETATTR = re.compile(
	rf"getattr\(\s*(?:self\.)?{LIFECYCLE_OBJECTS}\s*,\s*[\"']_(\w+)[\"']",
)
# Per-operation data each wrapper attaches itself; SegmentHost replaces it in phase 3.
WRAPPER_PREFIXES = ("ve_", "onecore_", "rhvoice_", "espeak_", "neural_")


def _private_accesses(text):
	return [
		match.group(0)
		for pattern in (PRIVATE_ACCESS, PRIVATE_GETATTR)
		for match in pattern.finditer(text)
		if not match.group(1).startswith(WRAPPER_PREFIXES)
	]


def test_guard_pattern_separates_lifecycle_state_from_wrapper_data():
	sample = "operation._run_started; operation._ve_work; self._segmentLifecycle._condition; self._segmentCondition"
	assert _private_accesses(sample) == ["operation._run_started", "_segmentLifecycle._condition"]


def test_guard_pattern_catches_lifecycle_aliases_and_getattr():
	assert _private_accesses("self._lifecycle._condition") == ["_lifecycle._condition"]
	assert _private_accesses('getattr(operation, "_run_started", False)') == ['getattr(operation, "_run_started"']
	assert _private_accesses("getattr(self._segmentLifecycle, '_delivery_thread')") == [
		"getattr(self._segmentLifecycle, '_delivery_thread'",
	]
	assert _private_accesses('getattr(self, "_veCallbackHandler", None)') == []
	assert _private_accesses('getattr(operation, "_espeak_native", None)') == []


def test_wrappers_do_not_touch_lifecycle_private_state():
	found = []
	for wrapper in sorted(DRIVERS.glob("*/__init__.py")):
		for number, line in enumerate(wrapper.read_text(encoding="utf-8").splitlines(), 1):
			found.extend(f"{wrapper.parent.name}:{number}: {access}" for access in _private_accesses(line))
	assert found == []


# Wrappers moved onto SegmentHost; the host owns their lifecycle entirely.
MIGRATED = ("Espeak",)


def test_migrated_wrappers_only_use_the_segment_host():
	for name in MIGRATED:
		text = (DRIVERS / name / "__init__.py").read_text(encoding="utf-8")
		assert "SegmentHost" in text, name
		assert "_segmentLifecycle" not in text and "SegmentLifecycle" not in text, name
