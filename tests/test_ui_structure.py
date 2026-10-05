"""The settings UI shares one path for each concern and uses only public driver hooks."""

import ast
from pathlib import Path

ADDON = Path(__file__).resolve().parents[1] / "addon"
DIALOG = ADDON / "globalPlugins/WorldVoice/speechSettingsDialog.py"


def class_source(path, name):
	source = path.read_text(encoding="utf-8")
	tree = ast.parse(source)
	(node,) = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name]
	return node, ast.get_source_segment(source, node)


def method(path, cls, name):
	node, _ = class_source(path, cls)
	(function,) = [n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == name]
	return function


def test_unicode_panel_has_one_script_choice_path():
	_, source = class_source(DIALOG, "UnicodeDetectionSettingsPanel")
	assert [name for name in ("_latinChoice", "_CJKChoice", "_arabicChoice") if name in source] == []
