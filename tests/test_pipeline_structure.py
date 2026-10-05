"""Pipeline modules take their dependencies as arguments and share one copy of each loop."""

import ast
from pathlib import Path

WORLDVOICE = Path(__file__).resolve().parents[1] / "addon" / "synthDrivers" / "WorldVoice"
PIPELINE = WORLDVOICE / "pipeline" / "__init__.py"


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
	assert not imported_modules(WORLDVOICE / "languageDetection" / "__init__.py") & {"config", "synthDriverHandler"}


def test_one_break_insertion_and_one_regex_scan():
	source = PIPELINE.read_text(encoding="utf-8")
	assert "_insert_BreakCommand_between_number" not in source and "previousious" not in source
	assert source.count(".finditer(") == 1


def test_dead_commands_stay_removed():
	assert "SplitCommand" not in (WORLDVOICE / "_speechcommand.py").read_text(encoding="utf-8")
	tree = ast.parse((WORLDVOICE / "compat" / "commands.py").read_text(encoding="utf-8"))
	assert not [node for node in tree.body if isinstance(node, ast.ImportFrom) and node.level == 2 and node.module == "driver"]


def test_run_logged_reads_the_log_section_once():
	tree = ast.parse(PIPELINE.read_text(encoding="utf-8"))
	(function,) = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_run_logged"]
	assert ast.unparse(function).count("config.conf['WorldVoice']['log']") == 1
