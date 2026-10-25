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
		# Assigned by Unicode 17.0 and 18.0 (fix/unicode-18): CJK Extension J, more Han, new kana.
		(0x323B0, "Han"),
		(0x33479, "Han"),
		(0x16FF2, "Han"),
		(0x2B81E, "Han"),
		(0x1B123, "Hiragana"),
		(0x1B124, "Katakana"),
		(0x1B168, "Katakana"),
		# Small seal script is a script of its own, not Han.
		(0x3D000, "Seal"),
		(0x3FC3F, "Seal"),
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


def test_script_data_is_of_unicode_18(scripts):
	data = sys.modules[PACKAGE + ".languageDetection.script_data"]
	assert data.UNICODE_VERSION == "18.0.0"
	assert data.SOURCE_SHA256 == "0071fd81b6aeae25f6e8bce8efec3066a6476a91b49bdb2f52dc76e817862a6a"
