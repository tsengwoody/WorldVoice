"""Hygiene rules that ruff alone does not express."""

import ast
import re
import shutil
import subprocess
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addon"


def _addon_sources():
	for path in ADDON.rglob("*.py"):
		parts = path.relative_to(ADDON).parts
		if parts[:3] == ("synthDrivers", "WorldVoice", "driver") and (
			parts[3] == "sonic" or len(parts) > 5 and parts[4] == "driver"
		):
			continue
		yield path


def test_every_blind_except_says_where_the_error_goes():
	missing = []
	for path in (*_addon_sources(), *(ROOT / "tests").glob("*.py")):
		for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
			if "noqa: BLE001" in line and not re.search(r"noqa: BLE001 - \S", line):
				missing.append(f"{path.relative_to(ROOT)}:{number}")
	assert missing == []


def test_ruff_version_matches_the_pre_commit_hook():
	pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
	config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
	required = re.search(r'^required-version = "==(\S+)"$', pyproject, re.MULTILINE)
	hook = re.search(r"ruff-pre-commit\n(?:\s*#.*\n)*\s*rev: v(\S+)", config)
	assert required and hook
	assert required.group(1) == hook.group(1)


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff is not installed")
def test_ruff_reports_nothing():
	# Every rule, as pyproject.toml configures it. No CLI --select or --exclude: either would
	# replace the pyproject lists, and --exclude would bring script_data.py back in.
	# pyproject has no `select`, so the rules are ruff's defaults minus the ignores; its
	# required-version makes any other ruff fail here instead of checking other rules.
	result = subprocess.run(
		["ruff", "check", "addon", "tests", "--output-format", "concise"],
		cwd=ROOT,
		capture_output=True,
		text=True,
		check=False,
	)
	assert result.returncode == 0, result.stdout + result.stderr


def test_deprecation_warnings_fail_the_suite():
	# pyproject.toml turns them into errors, so a deprecated call fails the test that makes it.
	with pytest.raises(DeprecationWarning, match="probe"):
		warnings.warn("probe", DeprecationWarning, stacklevel=1)


def test_pre_commit_runs_the_ruff_lint_hook():
	config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
	lint = config.index("- id: ruff\n")
	assert "args: [ --fix ]" in config[lint : config.index("- id: ruff-format")]
	assert "omits the lint hook" not in config


def test_pre_commit_hooks_cover_the_addon_and_the_tests():
	config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
	scopes = re.findall(r"^\s*files: (\S+)$", config, re.MULTILINE)
	assert scopes
	assert set(scopes) == {"^(addon|tests)/"}


def test_generics_is_imported_only_after_the_package_that_adds_its_path():
	# `generics` lives at the add-on root, which only the WorldVoice synth
	# package adds to sys.path; import sorting must not move it first.
	for path in _addon_sources():
		tree = ast.parse(path.read_text(encoding="utf-8"))
		imports = [
			node for node in tree.body if isinstance(node, ast.ImportFrom) and node.module and node.level == 0
		]
		generics = [node.lineno for node in imports if node.module.split(".")[0] == "generics"]
		if not generics or path.relative_to(ADDON).parts[:2] == ("synthDrivers", "WorldVoice"):
			continue
		worldvoice = [node.lineno for node in imports if node.module.startswith("synthDrivers.WorldVoice")]
		assert worldvoice and min(worldvoice) < min(generics), path


def _imported_modules(node, package):
	"""The absolute names an import statement in package (a tuple of names) can load."""
	if isinstance(node, ast.Import):
		return [alias.name for alias in node.names]
	if not isinstance(node, ast.ImportFrom):
		return []
	base = list(package[: len(package) - node.level + 1]) if node.level else []
	module = ".".join([*base, *([node.module] if node.module else [])])
	# `from x import y` may load the submodule x.y.
	return [module, *(f"{module}.{alias.name}" for alias in node.names)]


def _is_speech_symbols(name):
	return name == "generics.speechSymbols" or name.startswith("generics.speechSymbols.")


def test_the_speech_symbols_feature_is_gone():
	# Removed in phase 33; an existing unicode.dic stays on disk, and nothing reads it again.
	# A checkout that ran the old tests may keep an ignored __pycache__ there; Python never
	# imports a cached module without its source.
	package = ADDON / "generics" / "speechSymbols"
	assert [path for path in package.rglob("*") if "__pycache__" not in path.parts] == []
	offenders = []
	for path in _addon_sources():
		text = path.read_text(encoding="utf-8")
		where = path.relative_to(ROOT)
		# The module name as text also catches importlib.import_module("generics.speechSymbols...").
		offenders += [
			f"{where}: {word}" for word in ("unicode.dic", "generics.speechSymbols") if word in text
		]
		parent = path.relative_to(ADDON).parent.parts
		offenders += [
			f"{where}:{node.lineno}"
			for node in ast.walk(ast.parse(text))
			if any(_is_speech_symbols(name) for name in _imported_modules(node, parent))
		]
	assert offenders == []


def test_the_ignore_numbers_option_is_gone():
	# Removed in phase 35: the number language decides every digit. A profile may keep the key.
	readmes = [ROOT / "readme.md", *sorted((ADDON / "doc").glob("*/readme.md"))]
	offenders = [
		str(path.relative_to(ROOT))
		for path in (*_addon_sources(), *readmes)
		if "ignoreNumbersInLanguageDetection" in path.read_text(encoding="utf-8")
	]
	assert offenders == []


# The spec's reason table: the first entry whose calls all appear in a handler's
# own body names where its error goes. Combined entries come first, so a handler
# that both records and latches says both.
_LATCHED = "recorded on the record and latched: later speech is rejected"
_REASONS = (
	(("record_error", "latch_control_error"), _LATCHED),
	(("record_error", "_failSegmentControl"), _LATCHED),
	(("latch_control_error", "error = exc"), "latched, and kept to raise after the remaining cleanup"),
	(("record_error",), "recorded on the record; the segment fails"),
	(("_failSegmentControl",), "latched: the player or engine state is unknown"),
	(("_latch_fault",), "latched as a lifecycle fault"),
	(("_terminationError",), "kept and raised once termination finishes"),
	(("firstError",), "collected; the first is raised after every step ran"),
	(("error = exc",), "kept and raised after the remaining cleanup"),
	(("return unsupported",), "any failure means drain is unsupported"),
	(("return error",), "returned as the admission error"),
)


def _own_body(handler):
	"""The handler's statements, without the bodies of handlers nested inside it."""
	import copy

	body = copy.deepcopy(handler.body)
	for statement in body:
		for nested in ast.walk(statement):
			if isinstance(nested, ast.ExceptHandler):
				nested.body = [ast.Pass()]
	return "\n".join(ast.unparse(statement) for statement in body)


def _marked_handlers():
	"""(location, reason, the first matching _REASONS keys) for every handler with a BLE001 reason."""
	for path in _addon_sources():
		source = path.read_text(encoding="utf-8")
		lines = source.splitlines()
		for node in ast.walk(ast.parse(source)):
			if not isinstance(node, ast.ExceptHandler):
				continue
			match = re.search(r"noqa: BLE001 - (.+)$", lines[node.lineno - 1])
			if match is None:
				continue
			body = _own_body(node)
			keys = next((keys for keys, _reason in _REASONS if all(key in body for key in keys)), None)
			yield f"{path.relative_to(ROOT)}:{node.lineno}", match.group(1), keys


def test_blind_except_reasons_match_their_handlers():
	reasons = dict(_REASONS)
	wrong = [
		f"{where}: {reason!r} != {reasons[keys]!r}"
		for where, reason, keys in _marked_handlers()
		if keys is not None and reason != reasons[keys]
	]
	assert wrong == []


def test_every_reason_entry_still_checks_a_handler():
	# An entry no marked handler selects checks nothing: a renamed call it names silently ends
	# the check of its handlers.
	used = {keys for _where, _reason, keys in _marked_handlers()}
	assert [keys for keys, _reason in _REASONS if keys not in used] == []


@pytest.fixture(scope="module")
def test_sources():
	# Both scans below walk every test file: parse them once, and let the trees go with this module.
	return tuple(
		(path, ast.parse(path.read_text(encoding="utf-8"))) for path in (ROOT / "tests").glob("*.py")
	)


def test_only_the_addon_loader_loads_modules_from_files(test_sources):
	# Tests load add-on files through tests/addon_loader.py, so the loading steps have one copy.
	loaders = []
	for path, tree in test_sources:
		if path.name == "addon_loader.py":
			continue
		for node in ast.walk(tree):
			name = getattr(node, "attr", None) or (node.name if isinstance(node, ast.alias) else None)
			if name == "spec_from_file_location":
				loaders.append(f"{path.name}:{node.lineno}")
	assert loaders == []


def test_no_test_module_imports_another(test_sources):
	# Shared helpers live in harness modules and fixtures in conftest.py; pytest collects test
	# modules, so a helper kept in one is hard to find and is loaded under two names.
	imports = []
	for path, tree in test_sources:
		for node in ast.walk(tree):
			if isinstance(node, ast.ImportFrom):
				names = [node.module or ""]
			elif isinstance(node, ast.Import):
				names = [alias.name for alias in node.names]
			else:
				continue
			imports.extend(
				f"{path.name}:{node.lineno}" for name in names if name.split(".")[0].startswith("test_")
			)
	assert imports == []
