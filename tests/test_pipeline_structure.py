"""Pipeline modules take their dependencies as arguments and share one copy of each loop."""

import ast
import sys
from pathlib import Path

import pytest
from mutation_support import running_under_mutmut

WORLDVOICE = Path(__file__).resolve().parents[1] / "addon" / "synthDrivers" / "WorldVoice"


def imported_modules(path):
	# Every absolute import, even one inside a function, by its full dotted name.
	tree = ast.parse(path.read_text(encoding="utf-8"))
	names = set()
	for node in ast.walk(tree):
		if isinstance(node, ast.Import):
			names |= {alias.name for alias in node.names}
		elif isinstance(node, ast.ImportFrom) and node.level == 0:
			names.add(node.module)
	return names


def packages(modules):
	# "import os.path" and "from os.path import isfile" reach os as surely as "import os" does.
	return {module.split(".")[0] for module in modules}


def test_language_detection_reaches_for_no_nvda_globals():
	assert not packages(imported_modules(WORLDVOICE / "languageDetection" / "__init__.py")) & {
		"config",
		"synthDriverHandler",
	}


# mutmut's rewritten copy imports its own trampoline into every mutated module; the guard judges
# the source, as the hygiene guards do, so it stands aside on that copy.
@pytest.mark.skipif(running_under_mutmut(), reason="mutmut's copy imports mutmut")
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
	# Symbol lookup and file probing stay in symbols.py. The stages need only speech's commands and
	# its filter extension point; any other part of speech, or os by any submodule, is a lookup or a
	# probe coming back.
	assert (
		packages(imported_modules(package) - {"speech.commands", "speech.extensions"})
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


def test_speech_context_holds_only_plain_values():
	# A stage gets the default voice's name and language, not the voice object behind them.
	tree = ast.parse((WORLDVOICE / "pipeline" / "context.py").read_text(encoding="utf-8"))
	(context,) = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SpeechContext"]
	fields = [n for n in context.body if isinstance(n, ast.AnnAssign)]
	assert [field.target.id for field in fields] == [
		"supports_roles",
		"language",
		"number_language",
		"default_voice_name",
		"default_voice_language",
		"voice_name_for_language",
		"voice_locale_for_language",
	]
	for field in fields:
		assert not any(
			(isinstance(n, ast.Name) and n.id == "Any") or (isinstance(n, ast.Attribute) and n.attr == "Any")
			for n in ast.walk(field.annotation)
		), field.target.id
	for path in WORLDVOICE.rglob("*.py"):
		parts = path.relative_to(WORLDVOICE).parts
		if len(parts) > 2 and parts[0] == "driver" and parts[2] == "driver":
			continue
		for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
			assert not (isinstance(node, ast.Attribute) and node.attr == "default_voice"), path
			assert not (isinstance(node, ast.keyword) and node.arg == "default_voice"), path


def test_only_the_context_asks_nvda_for_the_synth():
	# worldvoice_synth() in context.py is the one way the pipeline reaches the synth; a stage that
	# asks NVDA itself could get another synth, or none.
	for path in (WORLDVOICE / "pipeline").rglob("*.py"):
		if path.name == "context.py":
			continue
		names = set()
		for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
			if isinstance(node, ast.Name):
				names.add(node.id)
			elif isinstance(node, ast.Attribute):
				names.add(node.attr)
			elif isinstance(node, (ast.Import, ast.ImportFrom)):
				names |= {alias.name for alias in node.names} | {alias.asname for alias in node.names}
		assert "getSynth" not in names, str(path.relative_to(WORLDVOICE))
