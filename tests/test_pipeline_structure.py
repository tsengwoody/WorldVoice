"""Pipeline modules take their dependencies as arguments and share one copy of each loop."""

import ast
import sys
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


def test_number_lexing_imports_only_the_standard_library():
	# The one definition of a number loads without NVDA: every import, even one inside a function,
	# is of the standard library, and none reaches back into the package.
	tree = ast.parse((WORLDVOICE / "pipeline" / "numbers.py").read_text(encoding="utf-8"))
	for node in ast.walk(tree):
		if isinstance(node, ast.Import):
			modules = [alias.name for alias in node.names]
		elif isinstance(node, ast.ImportFrom):
			assert node.level == 0, ast.unparse(node)
			modules = [node.module]
		else:
			continue
		assert all(module.split(".")[0] in sys.stdlib_module_names for module in modules), ast.unparse(node)
