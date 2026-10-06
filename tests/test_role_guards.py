"""The settings dialog's error callback finds its dialog without a class registry."""

import ast
import types
from pathlib import Path

ADDON = Path(__file__).resolve().parents[1] / "addon"
PANELS = ADDON / "globalPlugins/WorldVoice/speechSettingsDialog.py"


def test_error_callback_finds_its_dialog_without_a_class_registry():
	assert ".wvd" not in PANELS.read_text(encoding="utf-8")
	tree = ast.parse(PANELS.read_text(encoding="utf-8"))
	node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "got_error_callback")
	calls = []

	class Dialog:
		def onCancel(self, event):
			calls.append(("cancel", event))

	dialog = Dialog()
	environment = {
		"wx": types.SimpleNamespace(
			GetTopLevelParent=lambda window: dialog,
			CallAfter=lambda *args: calls.append(args),
		),
		"gui": types.SimpleNamespace(mainFrame=types.SimpleNamespace(popupSettingsDialog="popup")),
	}
	exec(compile(ast.Module(body=[node], type_ignores=[]), str(PANELS), "exec"), environment)
	environment["got_error_callback"](object())
	assert calls == [("cancel", None), ("popup", Dialog)]
