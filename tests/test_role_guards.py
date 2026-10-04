"""Role config, consistency flags and the dialog locator each have one home."""

import ast
from pathlib import Path
import re
import types

ADDON = Path(__file__).resolve().parents[1] / "addon"
PANELS = ADDON / "globalPlugins/WorldVoice/speechSettingsDialog.py"


def addon_sources():
	for path in ADDON.rglob("*.py"):
		parts = path.relative_to(ADDON).parts
		if parts[:3] == ("synthDrivers", "WorldVoice", "driver") and (
			parts[3] == "sonic" or len(parts) > 5 and parts[4] == "driver"
		):
			continue
		yield path, path.read_text(encoding="utf-8")


def test_role_section_is_only_touched_by_the_repository():
	pattern = re.compile(r"\[\s*[\"']role[\"']\s*\]")
	assert [p.name for p, text in addon_sources() if pattern.search(text)] == ["roles.py"]


FLAG_KEY = re.compile(r"[\"']KeepMainLocale\w+[\"']")


def test_keep_main_locale_flags_live_in_the_policy_module():
	found = {str(p.relative_to(ADDON)) for p, text in addon_sources() if FLAG_KEY.search(text)}
	assert found == {"synthDrivers/WorldVoice/mainLocalePolicy.py", "synthDrivers/WorldVoice/__init__.py"}
	synth = (ADDON / "synthDrivers/WorldVoice/__init__.py").read_text(encoding="utf-8")
	assert len(FLAG_KEY.findall(synth)) == 3  # the confspec entries only


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
		"wx": types.SimpleNamespace(GetTopLevelParent=lambda window: dialog, CallAfter=lambda *args: calls.append(args)),
		"gui": types.SimpleNamespace(mainFrame=types.SimpleNamespace(popupSettingsDialog="popup")),
	}
	exec(compile(ast.Module(body=[node], type_ignores=[]), str(PANELS), "exec"), environment)
	environment["got_error_callback"](object())
	assert calls == [("cancel", None), ("popup", Dialog)]
