"""Engine wrappers use the lifecycle's public API, never its private state."""

import re
from pathlib import Path

DRIVERS = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice/driver"
PRIVATE_ACCESS = re.compile(r"\b(operation|lifecycle|_segmentLifecycle)\._(\w+)")
# Per-operation data each wrapper attaches itself; SegmentHost replaces it in phase 3.
WRAPPER_PREFIXES = ("ve_", "onecore_", "rhvoice_", "espeak_", "neural_")


def _private_accesses(text):
	return [
		match.group(0)
		for match in PRIVATE_ACCESS.finditer(text)
		if not match.group(2).startswith(WRAPPER_PREFIXES)
	]


def test_guard_pattern_separates_lifecycle_state_from_wrapper_data():
	sample = "operation._run_started; operation._ve_work; self._segmentLifecycle._condition; self._segmentCondition"
	assert _private_accesses(sample) == ["operation._run_started", "_segmentLifecycle._condition"]


def test_wrappers_do_not_touch_lifecycle_private_state():
	found = []
	for wrapper in sorted(DRIVERS.glob("*/__init__.py")):
		for number, line in enumerate(wrapper.read_text(encoding="utf-8").splitlines(), 1):
			found.extend(f"{wrapper.parent.name}:{number}: {access}" for access in _private_accesses(line))
	assert found == []
