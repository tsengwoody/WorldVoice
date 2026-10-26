"""The settings UI shares one path for each concern and uses only public driver hooks."""

import ast
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from addon_loader import ADDON, WORLDVOICE, alias_package, load_definitions
from mutation_support import running_under_mutmut

DIALOG = ADDON / "globalPlugins/WorldVoice/speechSettingsDialog.py"
VOICE_PANEL = WORLDVOICE / "ui/voicePanel.py"
PIPELINE_CONTROLS = WORLDVOICE / "ui/controls.py"


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
	# rglob: a subpackage of the global plugin is settings UI too.
	for path in (ADDON / "globalPlugins/WorldVoice").rglob("*.py"):
		source = path.read_text(encoding="utf-8")
		assert "._voiceManager" not in source and ".uwv =" not in source, str(path.relative_to(ADDON))


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


def called_names(node):
	return {n.func.id for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def test_panels_apply_dependencies_through_one_path():
	# The depends_on loop and the controller read live in ui/controls.py; each panel passes in
	# only its own lookups.
	panels = {DIALOG: "SpeechPipelinePanel", VOICE_PANEL: "WorldVoiceVoiceSettingsPanel"}
	for path, cls in panels.items():
		tree = ast.parse(path.read_text(encoding="utf-8"))
		referred = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
			alias.asname or alias.name
			for n in ast.walk(tree)
			if isinstance(n, (ast.Import, ast.ImportFrom))
			for alias in n.names
		}
		assert referred & {"dependent_states", "ABSENT", "selected_value"} == set(), path.name
		apply = method(path, cls, "_applyDependencies")
		assert "apply_dependencies" in called_names(apply), path.name
		# ast.comprehension covers list, set and dict comprehensions and generator expressions.
		loops = (ast.For, ast.AsyncFor, ast.While, ast.comprehension)
		assert not any(isinstance(n, loops) for n in ast.walk(apply)), path.name
		assert "read_control" in called_names(method(path, cls, "_readController")), path.name


# mutmut's rewritten copy imports its own trampoline into every mutated module; the guard judges
# the source, as the hygiene guards do, so it stands aside on that copy.
@pytest.mark.skipif(running_under_mutmut(), reason="mutmut's copy imports mutmut")
def test_pipeline_controls_imports_only_wx_and_the_layout_rules():
	# The main driver imports the Voice panel, which imports this module: reaching back into the
	# driver package, the panels or globalPlugins would close a cycle.
	tree = ast.parse(PIPELINE_CONTROLS.read_text(encoding="utf-8"))
	for node in ast.walk(tree):
		if isinstance(node, ast.ImportFrom) and node.level:
			assert (node.level, node.module) == (1, "panelLayout"), ast.unparse(node)
			continue
		if isinstance(node, ast.Import):
			modules = [alias.name for alias in node.names]
		elif isinstance(node, ast.ImportFrom):
			modules = [node.module]
		else:
			continue
		assert all(module.split(".")[0] in {"wx", "gui", "typing", "collections"} for module in modules), (
			ast.unparse(node)
		)


def test_settings_ui_asks_for_worldvoice_not_for_the_synth():
	# worldvoice_synth() already returns the synth; asking NVDA again could only disagree with it.
	for path in (ADDON / "globalPlugins/WorldVoice").rglob("*.py"):
		tree = ast.parse(path.read_text(encoding="utf-8"))
		names = set()
		for node in ast.walk(tree):
			if isinstance(node, ast.Name):
				names.add(node.id)
			elif isinstance(node, ast.Attribute):
				names.add(node.attr)
			elif isinstance(node, (ast.Import, ast.ImportFrom)):
				names |= {alias.name for alias in node.names} | {alias.asname for alias in node.names}
		assert "getSynth" not in names, str(path.relative_to(ADDON))


def test_panel_layout_imports_by_its_package_path_without_wx_or_nvda(monkeypatch):
	# The global plugin imports synthDrivers.WorldVoice.ui.panelLayout, so Python runs
	# ui/__init__.py first; the layout tests load the file on their own and would miss an import
	# there. ui/__init__.py stays empty and the layout rules import nothing from the add-on, wx
	# or NVDA, so the rules load without any of them.
	for name in [name for name in sys.modules if name.split(".")[0] == "synthDrivers"]:
		monkeypatch.delitem(sys.modules, name)
	# None in sys.modules makes an import of that name fail.
	for name in ("wx", "gui", "config", "speech", "synthDriverHandler", "logHandler", "addonHandler"):
		monkeypatch.setitem(sys.modules, name, None)
	alias_package(monkeypatch, "synthDrivers")
	alias_package(monkeypatch, "synthDrivers.WorldVoice", WORLDVOICE)
	try:
		layout = importlib.import_module("synthDrivers.WorldVoice.ui.panelLayout")
		loaded = sorted(name for name in sys.modules if name.split(".")[0] == "synthDrivers")
	finally:
		# The import registered these itself, so monkeypatch would leave them behind.
		for name in ("synthDrivers.WorldVoice.ui.panelLayout", "synthDrivers.WorldVoice.ui"):
			sys.modules.pop(name, None)
	assert Path(layout.__file__) == WORLDVOICE / "ui/panelLayout.py"
	assert loaded == [
		"synthDrivers",
		"synthDrivers.WorldVoice",
		"synthDrivers.WorldVoice.ui",
		"synthDrivers.WorldVoice.ui.panelLayout",
	]
