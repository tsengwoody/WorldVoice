"""Hygiene rules that ruff alone does not express."""

from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addon"
# G201 is ignored in pyproject.toml, and an explicit --select would override that.
GATED_RULES = "BLE001,I001,UP004,UP008,UP031,UP035,RUF012"
RUFF_SCOPE = [
	"--exclude", "addon/synthDrivers/WorldVoice/driver/*/driver",
	"--exclude", "addon/synthDrivers/WorldVoice/driver/sonic",
]


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
	for path in _addon_sources():
		for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
			if "noqa: BLE001" in line and not re.search(r"noqa: BLE001 - \S", line):
				missing.append(f"{path.relative_to(ROOT)}:{number}")
	assert missing == []


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff is not installed")
def test_ruff_reports_none_of_the_gated_rules():
	result = subprocess.run(
		["ruff", "check", "addon", *RUFF_SCOPE, "--select", GATED_RULES, "--output-format", "concise"],
		cwd=ROOT, capture_output=True, text=True,
	)
	assert result.returncode == 0, result.stdout


def test_generics_is_imported_only_after_the_package_that_adds_its_path():
	# `generics` lives at the add-on root, which only the WorldVoice synth
	# package adds to sys.path; import sorting must not move it first.
	import ast

	for path in _addon_sources():
		tree = ast.parse(path.read_text(encoding="utf-8"))
		imports = [
			node for node in tree.body
			if isinstance(node, ast.ImportFrom) and node.module and node.level == 0
		]
		generics = [node.lineno for node in imports if node.module.split(".")[0] == "generics"]
		if not generics or path.relative_to(ADDON).parts[:2] == ("synthDrivers", "WorldVoice"):
			continue
		worldvoice = [node.lineno for node in imports if node.module.startswith("synthDrivers.WorldVoice")]
		assert worldvoice and min(worldvoice) < min(generics), path


def test_tests_share_one_module_stub_helper():
	local = []
	for path in (ROOT / "tests").glob("*.py"):
		if path.name == "nvda_stubs.py":
			continue
		for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
			if re.match(r"\s*def (module|package|stub)\(name", line):
				local.append(f"{path.name}:{number}")
	assert local == []


# The spec's reason table: the first entry whose call appears in a handler's
# own body names where its error goes.
_REASONS = (
	("record_error", "recorded on the record; the segment fails"),
	("latch_control_error", "latched: the player or engine state is unknown"),
	("_failSegmentControl", "latched: the player or engine state is unknown"),
	("_latch_fault", "latched as a lifecycle fault"),
	("_terminationError", "kept and raised once termination finishes"),
	("first_error", "collected; the first is raised after every step ran"),
	("error = exc", "kept and raised after the remaining cleanup"),
	("return unsupported", "any failure means drain is unsupported"),
	("return error", "returned as the admission error"),
)


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
			body = "\n".join(ast.unparse(statement) for statement in node.body)
			expected = next((reason for key, reason in _REASONS if key in body), None)
			if expected is not None and match.group(1) != expected:
				wrong.append(f"{path.relative_to(ROOT)}:{node.lineno}: {match.group(1)!r} != {expected!r}")
	assert wrong == []


def test_g201_is_ignored_for_the_documented_nvda_reason():
	config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
	assert '"G201",' in config and "log.exception lowers expected Windows/COM errors" in config
