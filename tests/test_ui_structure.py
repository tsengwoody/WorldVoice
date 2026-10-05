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


def test_policies_have_no_separate_persist_step():
	assert "def persist" not in (ADDON / "synthDrivers/WorldVoice/mainLocalePolicy.py").read_text(encoding="utf-8")


def test_role_panel_save_only_applies():
	source = ast.unparse(method(DIALOG, "SpeechRoleSettingsPanel", "onSave"))
	assert "set_" not in source


def test_ui_uses_only_public_driver_hooks():
	for path in (ADDON / "globalPlugins/WorldVoice").glob("*.py"):
		source = path.read_text(encoding="utf-8")
		assert "._voiceManager" not in source and ".uwv =" not in source, path.name


def test_base_panel_on_save_returns_nothing():
	function = method(DIALOG, "BaseSettingsPanel", "onSave")
	assert not [node for node in ast.walk(function) if isinstance(node, ast.Return) and node.value is not None]
	method(DIALOG, "BaseSettingsPanel", "_write_settings")


def test_global_plugin_has_no_shadowed_workspace_constant():
	tree = ast.parse((ADDON / "globalPlugins/WorldVoice/__init__.py").read_text(encoding="utf-8"))
	targets = {t.id for node in tree.body if isinstance(node, ast.Assign) for t in node.targets if isinstance(t, ast.Name)}
	assert "workspace_path" not in targets
