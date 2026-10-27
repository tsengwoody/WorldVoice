"""The detection language data and its one table of the scripts with a user-chosen assumed language."""

import ast
import dataclasses
import importlib
import re
import sys
from pathlib import Path

import pytest
from addon_loader import ADDON, WORLDVOICE, alias_package, load_source
from mutation_support import running_under_mutmut

SCRIPT_LANGUAGES_PATH = WORLDVOICE / "languageDetection/scriptLanguages.py"
# The vendored drivers and the generated data, as tests/test_translator_comments.py skips them.
EXCLUDED = re.compile(r"^synthDrivers/WorldVoice/(driver/[^/]+/driver/|unicodeScripts/\w+_data\.py$)")

# What config["WorldVoice"]["autoLanguageSwitching"] stores, so these never change.
STORED_ROWS = [
	("Latin", "latinCharactersLanguage", "en"),
	("Han", "CJKCharactersLanguage", "ja"),
	("Arabic", "arabicCharactersLanguage", "ar"),
	("Cyrillic", "cyrillicCharactersLanguage", "ru"),
	("Devanagari", "devanagariCharactersLanguage", "hi"),
]


@pytest.fixture
def module(monkeypatch):
	return load_source(monkeypatch, "script_languages_under_test", SCRIPT_LANGUAGES_PATH)


# mutmut's rewritten copy imports its own trampoline into every mutated module; the guard judges
# the source, as the hygiene guards do, so it stands aside on that copy.
@pytest.mark.skipif(running_under_mutmut(), reason="mutmut's copy imports mutmut")
def test_script_languages_import_only_the_standard_library():
	# The table loads without NVDA, so a standalone language-switching library could take it as is.
	for node in ast.walk(ast.parse(SCRIPT_LANGUAGES_PATH.read_text(encoding="utf-8"))):
		if isinstance(node, ast.Import):
			modules = [alias.name for alias in node.names]
		elif isinstance(node, ast.ImportFrom):
			assert node.level == 0, ast.unparse(node)
			modules = [node.module]
		else:
			continue
		assert all(module.split(".")[0] in sys.stdlib_module_names for module in modules), ast.unparse(node)


def test_detection_scripts_keep_the_stored_names_and_defaults(module):
	rows = [(row.script, row.config_key, row.default_language) for row in module.DETECTION_SCRIPTS]
	assert rows == STORED_ROWS
	assert [field.name for field in dataclasses.fields(module.DetectionScript)] == [
		"script",
		"config_key",
		"default_language",
	]


def test_every_detection_script_has_candidates_and_a_candidate_default(module):
	for row in module.DETECTION_SCRIPTS:
		assert row.script in module.SCRIPT_LANGUAGES, row
		assert row.default_language in module.SCRIPT_LANGUAGES[row.script], row
	scripts = [row.script for row in module.DETECTION_SCRIPTS]
	keys = [row.config_key for row in module.DETECTION_SCRIPTS]
	assert len(set(scripts)) == len(scripts) and len(set(keys)) == len(keys)


def test_script_config_keys_are_written_only_in_the_table():
	# The settings and the panel derive the keys from DETECTION_SCRIPTS, so a new script is one row.
	holders = set()
	for path in sorted(ADDON.rglob("*.py")):
		relative = path.relative_to(ADDON).as_posix()
		if EXCLUDED.search(relative):
			continue
		for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
			if isinstance(node, ast.Constant) and str(node.value).endswith("CharactersLanguage"):
				holders.add(path)
	assert holders == {SCRIPT_LANGUAGES_PATH}


def test_script_languages_import_by_their_package_path_without_nvda(monkeypatch):
	# The panel imports synthDrivers.WorldVoice.languageDetection.scriptLanguages, so Python runs
	# languageDetection/__init__.py first; it stays empty (the detector is detector.py), and the
	# table loads without NVDA's speech commands, as ui.panelLayout loads without wx.
	for name in [name for name in sys.modules if name.split(".")[0] == "synthDrivers"]:
		monkeypatch.delitem(sys.modules, name)
	# None in sys.modules makes an import of that name fail, even when another test left a stub.
	for name in ("speech", "config", "logHandler", "languageHandler", "synthDriverHandler", "addonHandler"):
		monkeypatch.setitem(sys.modules, name, None)
	alias_package(monkeypatch, "synthDrivers")
	alias_package(monkeypatch, "synthDrivers.WorldVoice", WORLDVOICE)
	package = "synthDrivers.WorldVoice.languageDetection"
	try:
		table = importlib.import_module(package + ".scriptLanguages")
		loaded = sorted(name for name in sys.modules if name.split(".")[0] == "synthDrivers")
	finally:
		# The import registered these itself, so monkeypatch would leave them behind.
		for name in (package + ".scriptLanguages", package):
			sys.modules.pop(name, None)
	assert Path(table.__file__) == SCRIPT_LANGUAGES_PATH
	assert loaded == ["synthDrivers", "synthDrivers.WorldVoice", package, package + ".scriptLanguages"]
