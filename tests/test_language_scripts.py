"""get_script looks a code point up in the generated Unicode script ranges."""

import importlib
import sys

import pytest
from addon_loader import WORLDVOICE, alias_package

PACKAGE = "language_scripts_test_worldvoice"


@pytest.fixture
def scripts(monkeypatch):
	for name in tuple(sys.modules):
		if name.startswith(PACKAGE + "."):
			monkeypatch.delitem(sys.modules, name)
	alias_package(monkeypatch, PACKAGE, WORLDVOICE)
	# The detection package without its __init__, which needs NVDA's speech commands.
	alias_package(monkeypatch, PACKAGE + ".languageDetection", WORLDVOICE / "languageDetection")
	return importlib.import_module(PACKAGE + ".languageDetection.scripts")


@pytest.mark.parametrize(
	("codepoint", "script"),
	[
		(0x0, "Common"),
		(0x40, "Common"),
		(0x41, "Latin"),
		(0x5A, "Latin"),
		(0x5B, "Common"),
		(0x4E2D, "Han"),
		(0x0639, "Arabic"),
		(0x0301, "Inherited"),
		(0x20000, "Han"),
	],
)
def test_assigned_code_points_have_their_script(scripts, codepoint, script):
	assert scripts.get_script(codepoint) == script


@pytest.mark.parametrize(
	"codepoint",
	[
		# Unassigned code points between two ranges.
		0x0378,
		0x0379,
		# Private use and the last code point lie in no range.
		0xE000,
		0x10FFFF,
	],
)
def test_code_points_outside_every_range_have_no_script(scripts, codepoint):
	assert scripts.get_script(codepoint) is None
