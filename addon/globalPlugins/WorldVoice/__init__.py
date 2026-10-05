import os

import addonHandler
import globalPluginHandler
import globalVars
import gui
import ui
import wx
from logHandler import log
from scriptHandler import script

# Importing the WorldVoice synth package puts the add-on root, home of
# `generics`, on sys.path; keep these before the generics imports.
from synthDrivers.WorldVoice.pipeline.scope import pipeline_scope
from synthDrivers.WorldVoice.sayAll import patch, unpatch

# isort: split
from generics.coreArchive import extract_core_archive
from generics.speechSymbols.views import SpeechSymbolsDialog

from .pipelineLog import ask_disable_on_start, ask_export, confirm_enable, pipeline_log
from .speechSettingsDialog import WorldVoiceSettingsDialog

addonHandler.initTranslation()
ADDON_SUMMARY = addonHandler.getCodeAddon().manifest["summary"]


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self):
		super().__init__()
		self.submenu_item = None

		patch()
		pipeline_scope.attach_global()

		if globalVars.appArgs.secure:
			return

		self.createMenu()

		wx.CallAfter(self.check_log_record)

	def terminate(self):
		try:
			self.removeMenu()
		except RuntimeError:
			# wxPython raises RuntimeError for a menu whose C++ object is gone.
			pass

		unpatch()
		pipeline_scope.detach_global()

	def createMenu(self):
		self.submenu_WorldVoice = wx.Menu()

		item = self.submenu_WorldVoice.Append(wx.ID_ANY, _("&Settings"), _("Settings."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.popup_SpeechSettingsDialog, item)
		item = self.submenu_WorldVoice.Append(wx.ID_ANY, _("&Unicode Settings"), _("Unicode Settings."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.popup_SpeechSymbolsDialog, item)
		item = self.submenu_WorldVoice.Append(wx.ID_ANY, _("&File Import"), _("Import File."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onFileImport, item)
		# if not AisoundVoice.install():
		# 	item = self.submenu_WorldVoice.Append(wx.ID_ANY, _("&Aisound Core Install"), _("Install Aisound Core."))
		# 	gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onAisoundCoreInstall, item)

		self.submenu_item = gui.mainFrame.sysTrayIcon.menu.Insert(
			2,
			wx.ID_ANY,
			_("WorldVoice"),
			self.submenu_WorldVoice,
		)

	def removeMenu(self):
		if self.submenu_item is not None:
			try:
				gui.mainFrame.sysTrayIcon.menu.Remove(self.submenu_item)
			except (
				AttributeError
			):  # We can get this somehow from wx python when NVDA is shuttingdown, just ignore
				pass
			self.submenu_item.Destroy()

	def onFileImport(self, event):
		with wx.FileDialog(
			gui.mainFrame,
			message=_("Import file..."),
			wildcard="zip files (*.zip)|*.zip",
		) as entryDialog:
			if entryDialog.ShowModal() != wx.ID_OK:
				return
			core_zip_path = entryDialog.GetPath()

		workspace_path = os.path.join(globalVars.appArgs.configPath, "WorldVoice-workspace")
		try:
			os.makedirs(workspace_path, exist_ok=True)
			extract_core_archive(core_zip_path, workspace_path)
		except Exception:
			log.exception(
				f"An unexpected error occurred while processing '{os.path.basename(core_zip_path)}'",
			)
			gui.messageBox(
				_("Import fail"),
				_("Import File"),
				wx.OK,
			)
		else:
			if (
				gui.messageBox(
					_(
						"For the new file to import, NVDA must be restarted. Are you want to restart NVDA now ?",
					),
					_("Import File"),
					wx.OK | wx.CANCEL | wx.ICON_WARNING,
				)
				== wx.OK
			):
				import core
				import queueHandler

				queueHandler.queueFunction(queueHandler.eventQueue, core.restart)

	def popup_SpeechSettingsDialog(self, event):
		wx.CallAfter(gui.mainFrame.popupSettingsDialog, WorldVoiceSettingsDialog)

	def popup_SpeechSymbolsDialog(self, event):
		if SpeechSymbolsDialog._instance is None:
			gui.mainFrame.popupSettingsDialog(SpeechSymbolsDialog)
		else:
			ui.message(_("SpeechSymbolsDialog have already been opened"))

	@script(
		description=_("popup speech settings dialog"),
		category=ADDON_SUMMARY,
	)
	def script_popup_SpeechSettingsDialog(self, gesture):
		self.popup_SpeechSettingsDialog(None)

	@script(
		description=_("popup unicode settings dialog"),
		category=ADDON_SUMMARY,
	)
	def script_popup_unicode_settings_dialog(self, gesture):
		self.popup_SpeechSymbolsDialog(None)

	@script(
		description=_("switch log record"),
		category=ADDON_SUMMARY,
	)
	def script_switch_log_record(self, gesture):
		if not pipeline_log.enabled:
			wx.CallAfter(self.enable_log_record)
		else:
			wx.CallAfter(self.disable_log_record)

	def check_log_record(self):
		if pipeline_log.enabled and ask_disable_on_start():
			pipeline_log.disable()
			pipeline_log.export()

	def enable_log_record(self):
		if confirm_enable(allow_cancel=False) == wx.YES:
			pipeline_log.enable()
			ui.message(_("turn on WorldVoice`s log record"))

	def disable_log_record(self):
		pipeline_log.disable()
		if ask_export():
			pipeline_log.export()
			ui.message(_("turn off WorldVoice`s log record"))
