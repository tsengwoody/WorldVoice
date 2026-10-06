"""The settings dialog's error callback finds its dialog without a class registry."""

import types

from addon_loader import ADDON, load_definitions

PANELS = ADDON / "globalPlugins/WorldVoice/speechSettingsDialog.py"


def test_error_callback_finds_its_dialog_without_a_class_registry():
	assert ".wvd" not in PANELS.read_text(encoding="utf-8")
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
	load_definitions(PANELS, ["got_error_callback"], environment)
	environment["got_error_callback"](object())
	assert calls == [("cancel", None), ("popup", Dialog)]
