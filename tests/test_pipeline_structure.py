"""Pipeline modules take their dependencies as arguments and share one copy of each loop."""

import ast
from pathlib import Path

WORLDVOICE = Path(__file__).resolve().parents[1] / "addon" / "synthDrivers" / "WorldVoice"


def imported_modules(path):
	tree = ast.parse(path.read_text(encoding="utf-8"))
	names = set()
	for node in tree.body:
		if isinstance(node, ast.Import):
			names |= {alias.name for alias in node.names}
		elif isinstance(node, ast.ImportFrom) and node.level == 0:
			names.add(node.module)
	return names


def test_language_detection_reaches_for_no_nvda_globals():
	assert not imported_modules(WORLDVOICE / "languageDetection" / "__init__.py") & {
		"config",
		"synthDriverHandler",
	}
