"""The settings UI shares one path for each concern and uses only public driver hooks."""

import ast
from types import SimpleNamespace

from addon_loader import ADDON, load_definitions

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


def test_ui_uses_only_public_driver_hooks():
	for path in (ADDON / "globalPlugins/WorldVoice").glob("*.py"):
		source = path.read_text(encoding="utf-8")
		assert "._voiceManager" not in source and ".uwv =" not in source, path.name


def _role_panel_on_save(synth, log):
	env = {"worldvoice_synth": lambda: synth, "log": log}
	return load_definitions(DIALOG, ["SpeechRoleSettingsPanel.onSave"], env)["onSave"]


def test_role_panel_does_not_save_to_a_voice_manager_the_synth_replaced():
	# The dialog is not modal: NVDA may rebuild WorldVoice (an audio device change) while it is open.
	applied, warnings = [], []
	log = SimpleNamespace(warning=warnings.append)
	opened_with = object()
	panel = SimpleNamespace(
		disable=False,
		_manager=opened_with,
		_presenter=SimpleNamespace(apply=lambda: applied.append(True)),
	)
	_role_panel_on_save(SimpleNamespace(voice_manager=object()), log)(panel)
	assert applied == []
	assert len(warnings) == 1
	_role_panel_on_save(SimpleNamespace(voice_manager=opened_with), log)(panel)
	assert applied == [True]
