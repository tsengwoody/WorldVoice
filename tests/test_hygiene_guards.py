"""Hygiene rules that ruff alone does not express."""

from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addon"
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
def test_ruff_reports_no_blind_except_or_unsorted_import():
	result = subprocess.run(
		["ruff", "check", "addon", *RUFF_SCOPE, "--select", "BLE001,I001", "--output-format", "concise"],
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
