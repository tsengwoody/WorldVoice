"""The settings dialog's error callback finds its dialog without a class registry."""

import types

from addon_loader import ADDON, load_definitions

PLUGIN = ADDON / "globalPlugins/WorldVoice"
ROLE_PANEL = PLUGIN / "panels/role.py"


def test_error_callback_finds_its_dialog_without_a_class_registry():
	for path in PLUGIN.rglob("*.py"):
		assert ".wvd" not in path.read_text(encoding="utf-8"), path.name
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
	load_definitions(ROLE_PANEL, ["gotErrorCallback"], environment)
	environment["gotErrorCallback"](object())
	assert calls == [("cancel", None), ("popup", Dialog)]
