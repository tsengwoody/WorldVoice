"""The WorldVoice global plugin: its NVDA menu, its scripts and the core file import.

The real globalPlugins/WorldVoice/__init__.py runs against ui_harness's GUI stubs; its add-on
collaborators record their calls in env.calls.
"""

import pytest
from ui_harness import MenuItem, load_global_plugin


def plugin(monkeypatch, **options):
	env = load_global_plugin(monkeypatch, **options)
	env.nvda_items = [MenuItem(label) for label in ("Preferences", "Tools", "Help", "Exit")]
	env.tray.menu.items.extend(env.nvda_items)
	env.plugin = env.module.GlobalPlugin()
	return env


def run_called_after(env):
	scheduled, env.wx.called_after[:] = list(env.wx.called_after), []
	for function, args in scheduled:
		function(*args)


def test_starting_adds_the_worldvoice_menu_to_nvdas_menu(monkeypatch):
	env = plugin(monkeypatch)
	p = env.plugin

	assert env.calls == [("patch",), ("attach",)]
	inserted = p.submenuItem
	assert env.tray.menu.items == [*env.nvda_items[:2], inserted, *env.nvda_items[2:]]
	assert inserted.label == "WorldVoice"
	submenu = inserted.submenu
	assert [(item.label, item.help) for item in submenu.items] == [
		("&Settings", "Settings."),
		("&File Import", "Import File."),
	]
	assert [(event, handler, item) for event, handler, item in env.tray.bindings] == [
		("EVT_MENU", p.popupSpeechSettingsDialog, submenu.items[0]),
		("EVT_MENU", p.onFileImport, submenu.items[1]),
	]
	assert env.wx.called_after == [(p.checkLogRecord, ())]


def test_secure_mode_adds_no_menu(monkeypatch):
	env = plugin(monkeypatch, secure=True)
	assert env.tray.menu.items == env.nvda_items
	assert env.plugin.submenuItem is None
	assert env.wx.called_after == []


def test_terminating_removes_and_destroys_the_menu(monkeypatch):
	env = plugin(monkeypatch)
	item = env.plugin.submenuItem

	env.plugin.terminate()

	assert env.tray.menu.items == env.nvda_items
	assert item.destroyed is True
	assert env.calls[-2:] == [("unpatch",), ("detach",)]


def test_a_menu_nvda_already_dismantled_is_still_destroyed(monkeypatch):
	env = plugin(monkeypatch)
	item = env.plugin.submenuItem
	env.gui.mainFrame.sysTrayIcon.menu = None  # NVDA shutting down: Remove raises AttributeError

	env.plugin.terminate()

	assert item.destroyed is True
	assert env.calls[-1] == ("detach",)


def test_settings_menu_and_script_open_the_settings_dialog(monkeypatch):
	env = plugin(monkeypatch)
	run_called_after(env)  # the startup log check
	env.plugin.script_popupSpeechSettingsDialog(None)
	run_called_after(env)
	assert env.popped == [env.settings_dialog]


@pytest.mark.parametrize("enabled", [False, True])
def test_log_script_switches_the_pipeline_log(monkeypatch, enabled):
	env = plugin(monkeypatch, log_enabled=enabled)
	env.wx.called_after.clear()
	env.calls.clear()

	env.plugin.script_switchLogRecord(None)
	run_called_after(env)

	if enabled:
		assert env.calls == [
			"disable",
			("ask", "export"),
			"export",
			("message", "turn off WorldVoice`s log record"),
		]
	else:
		assert env.calls == [("ask", "confirm"), "enable", ("message", "turn on WorldVoice`s log record")]
	assert env.pipeline_log.enabled is not enabled


def test_declined_log_prompts_go_no_further(monkeypatch):
	env = plugin(monkeypatch)
	env.calls.clear()
	env.answers_for["confirm"] = env.wx.NO
	env.plugin.enableLogRecord()
	assert env.calls == [("ask", "confirm")]
	assert env.pipeline_log.enabled is False

	env.pipeline_log.enabled = True
	env.answers_for["export"] = False
	env.calls.clear()
	env.plugin.disableLogRecord()
	# Recording stops either way, so the user hears that it did even without an export.
	assert env.calls == ["disable", ("ask", "export"), ("message", "turn off WorldVoice`s log record")]


@pytest.mark.parametrize(
	"enabled,answer,expected",
	[
		(True, True, [("ask", "disable on start"), "disable", "export"]),
		(True, False, [("ask", "disable on start")]),
		(False, True, []),
	],
)
def test_startup_offers_to_stop_a_log_left_running(monkeypatch, enabled, answer, expected):
	env = plugin(monkeypatch, log_enabled=enabled)
	env.answers_for["disable on start"] = answer
	env.calls.clear()
	run_called_after(env)
	assert env.calls == expected


class FileDialog:
	def __init__(self, answer, path):
		self.answer, self.path, self.opened = answer, path, []

	def __call__(self, parent, **kwargs):
		self.opened.append(kwargs)
		return self

	def __enter__(self):
		return self

	def __exit__(self, *exc):
		return False

	def ShowModal(self):
		return self.answer

	def GetPath(self):
		return self.path


def test_cancelled_import_extracts_nothing(monkeypatch):
	env = plugin(monkeypatch)
	env.calls.clear()
	env.wx.FileDialog = FileDialog(env.wx.ID_CANCEL, "core.zip")

	env.plugin.onFileImport(None)

	assert env.wx.FileDialog.opened == [{"message": "Import file...", "wildcard": "zip files (*.zip)|*.zip"}]
	assert env.calls == []
	assert env.shown == []


@pytest.mark.parametrize("restart", [True, False])
def test_imported_core_is_extracted_into_the_workspace_and_offers_a_restart(monkeypatch, tmp_path, restart):
	env = plugin(monkeypatch)
	env.calls.clear()
	workspace = tmp_path / "missing" / "workspace"
	env.workspace[0] = str(workspace)
	env.wx.FileDialog = FileDialog(env.wx.ID_OK, "C:/cores/VE.zip")
	env.answers.append(env.wx.OK if restart else env.wx.CANCEL)

	env.plugin.onFileImport(None)

	assert workspace.is_dir()  # created before extracting
	assert env.calls[0] == ("extract", "C:/cores/VE.zip", str(workspace))
	((message, caption, style),) = env.shown
	assert caption == "Import File" and "must be restarted" in message
	assert style == env.wx.OK | env.wx.CANCEL | env.wx.ICON_WARNING
	assert env.calls[1:] == ([("queue", "event queue", env.restart)] if restart else [])


def test_failed_extraction_reports_and_logs_the_archive_name(monkeypatch, tmp_path):
	env = plugin(monkeypatch)
	env.workspace[0] = str(tmp_path)
	env.wx.FileDialog = FileDialog(env.wx.ID_OK, "C:/cores/broken.zip")

	def fail(*args):
		raise OSError("bad archive")

	monkeypatch.setattr(env.module, "extractCoreArchive", fail)
	env.plugin.onFileImport(None)

	assert env.shown == [("Import fail", "Import File", env.wx.OK)]
	assert ("exception", "An unexpected error occurred while processing 'broken.zip'") in env.logged
