"""SegmentLifecycle is internal to SegmentHost; engine wrappers use only the host."""

import ast
import re
from pathlib import Path

ADDON = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice"
RUNTIME = ADDON / "runtime"
DRIVERS = ADDON / "driver"
LIFECYCLE_OBJECTS = r"(?:operation|lifecycle|_lifecycle|_segmentLifecycle)"
PRIVATE_ACCESS = re.compile(rf"(?<![A-Za-z0-9]){LIFECYCLE_OBJECTS}\._(\w+)")
PRIVATE_GETATTR = re.compile(
	rf"getattr\(\s*(?:self\.)?{LIFECYCLE_OBJECTS}\s*,\s*[\"']_(\w+)[\"']",
)
# Per-operation data each wrapper attaches itself; SegmentHost replaces it in phase 3.
WRAPPER_PREFIXES = ("ve_", "onecore_", "rhvoice_", "espeak_")


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


WRAPPERS = ("Espeak", "SAPI5", "RHVoice", "OneCore", "VE", "Cerence")
LIFECYCLE_MODULES = ("_segmentLifecycle", "segmentLifecycle")


def _imported_modules(path):
	tree = ast.parse(path.read_text(encoding="utf-8"))
	for node in ast.walk(tree):
		if isinstance(node, ast.ImportFrom):
			if node.module:
				yield node.module
			yield from (alias.name for alias in node.names)
		elif isinstance(node, ast.Import):
			yield from (alias.name for alias in node.names)


def _methods(path, class_name):
	tree = ast.parse(path.read_text(encoding="utf-8"))
	cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
	return {node.name for node in cls.body if isinstance(node, ast.FunctionDef)}


def test_only_the_segment_host_imports_the_lifecycle():
	importers = sorted(
		path.relative_to(ADDON).as_posix()
		for path in ADDON.rglob("*.py")
		if any(name.split(".")[-1] in LIFECYCLE_MODULES for name in _imported_modules(path))
	)
	assert importers == ["runtime/segmentHost.py"]


def test_the_lifecycle_module_is_private():
	assert not (RUNTIME / "segmentLifecycle.py").exists()
	assert (RUNTIME / "_segmentLifecycle.py").is_file()


def test_wrappers_only_use_the_segment_host():
	for name in WRAPPERS:
		text = (DRIVERS / name / "__init__.py").read_text(encoding="utf-8")
		assert "SegmentHost" in text, name
		for banned in ("_lifecycle", "SegmentLifecycle", "segmentLifecycle", "CallbackGate"):
			assert banned not in text, (name, banned)


def test_wrapper_era_lifecycle_api_is_gone():
	lifecycle = RUNTIME / "_segmentLifecycle.py"
	assert not {"is_resource_busy", "reject_pending"} & _methods(lifecycle, "SegmentLifecycle")
	assert not {"sink", "has_started", "is_retired"} & _methods(lifecycle, "SegmentOperation")
	playback = (RUNTIME / "playbackWork.py").read_text(encoding="utf-8")
	for name in ("CallbackGate", "CallbackLease", "_NativeCall"):
		assert f"class {name}" not in playback, name
