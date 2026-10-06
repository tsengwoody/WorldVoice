"""SegmentLifecycle is internal to SegmentHost; engine wrappers use only the host."""

import ast
from pathlib import Path

ADDON = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice"
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


def test_only_the_segment_host_imports_the_lifecycle():
	importers = sorted(
		path.relative_to(ADDON).as_posix()
		for path in ADDON.rglob("*.py")
		if any(name.split(".")[-1] in LIFECYCLE_MODULES for name in _imported_modules(path))
	)
	assert importers == ["runtime/segmentHost.py"]
