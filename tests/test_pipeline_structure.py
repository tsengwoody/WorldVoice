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


# What phase 31 moved out of the package, or deleted: a name that comes back, bare or private,
# means a move was undone or copied.
MOVED = [
	"SYMBOLS",
	"NUMBER_RE",
	"NUMBER_TOKEN_RE",
	"DIGITS",
	"THOUSANDS_RE",
	"SENTENCE_END_RE",
	"split_spaced_numbers",
	"number_pieces",
	"strip_thousands",
	"has_symbol_table",
	"symbol_table_on_disk",
	"symbol_locale",
	"symbol_name",
	"symbol_namer",
]


def top_level_names(path):
	names = set()
	for node in ast.parse(path.read_text(encoding="utf-8")).body:
		if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
			names.add(node.name)
		elif isinstance(node, ast.Assign):
			names |= {target.id for target in node.targets if isinstance(target, ast.Name)}
		elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
			names.add(node.target.id)
	return names


def test_pipeline_package_keeps_only_stages_logging_and_registry():
	package = WORLDVOICE / "pipeline" / "__init__.py"
	assert top_level_names(package) & {*MOVED, *(f"_{name}" for name in MOVED)} == set()
	# Symbol lookup and file probing stay in symbols.py; speech.commands and speech.extensions are fine.
	assert (
		imported_modules(package)
		& {
			"os",
			"unicodedata",
			"characterProcessing",
			"globalVars",
			"languageHandler",
			"speech",
		}
		== set()
	)
	symbols = ast.parse((WORLDVOICE / "pipeline" / "symbols.py").read_text(encoding="utf-8"))
	assert [
		ast.unparse(node) for node in ast.walk(symbols) if isinstance(node, ast.ImportFrom) and node.level
	] == []
