"""Hygiene rules that ruff alone does not express."""

import re
import shutil
import subprocess
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
	import ast

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


# The spec's reason table: the first entry whose calls all appear in a handler's
# own body names where its error goes. Combined entries come first, so a handler
# that both records and latches says both.
_LATCHED = "recorded on the record and latched: later speech is rejected"
_REASONS = (
	(
		("record_error", "operation is not None", "_failSegmentControl"),
		"recorded on the record; a segment's failure also latches",
	),
	(("record_error", "latch_control_error"), _LATCHED),
	(("record_error", "_failSegmentControl"), _LATCHED),
	(("latch_control_error", "error = exc"), "latched, and kept to raise after the remaining cleanup"),
	(("record_error",), "recorded on the record; the segment fails"),
	(("latch_control_error",), "latched: the player or engine state is unknown"),
	(("_failSegmentControl",), "latched: the player or engine state is unknown"),
	(("_latch_fault",), "latched as a lifecycle fault"),
	(("_terminationError",), "kept and raised once termination finishes"),
	(("first_error",), "collected; the first is raised after every step ran"),
	(("error = exc",), "kept and raised after the remaining cleanup"),
	(("return unsupported",), "any failure means drain is unsupported"),
	(("return error",), "returned as the admission error"),
)


def _own_body(handler):
	"""The handler's statements, without the bodies of handlers nested inside it."""
	import ast
	import copy

	body = copy.deepcopy(handler.body)
	for statement in body:
		for nested in ast.walk(statement):
			if isinstance(nested, ast.ExceptHandler):
				nested.body = [ast.Pass()]
	return "\n".join(ast.unparse(statement) for statement in body)


def test_blind_except_reasons_match_their_handlers():
	import ast

	wrong = []
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
			expected = next((reason for keys, reason in _REASONS if all(key in body for key in keys)), None)
			if expected is not None and match.group(1) != expected:
				wrong.append(f"{path.relative_to(ROOT)}:{node.lineno}: {match.group(1)!r} != {expected!r}")
	assert wrong == []


def test_only_the_addon_loader_loads_modules_from_files():
	# Tests load add-on files through tests/addon_loader.py, so the loading steps have one copy.
	import ast

	loaders = []
	for path in (ROOT / "tests").glob("*.py"):
		if path.name == "addon_loader.py":
			continue
		for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
			name = getattr(node, "attr", None) or (node.name if isinstance(node, ast.alias) else None)
			if name == "spec_from_file_location":
				loaders.append(f"{path.name}:{node.lineno}")
	assert loaders == []
