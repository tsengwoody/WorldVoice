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
from synthDrivers.WorldVoice.pipeline.sayAll import patch, unpatch
from synthDrivers.WorldVoice.pipeline.scope import pipeline_scope
from synthDrivers.WorldVoice.workspace import workspace_path

# isort: split
from generics.coreArchive import extractCoreArchive

from .dialog import WorldVoiceSettingsDialog
from .pipelineLog import askDisableOnStart, askExport, confirmEnable, pipelineLogService

addonHandler.initTranslation()
ADDON_SUMMARY = addonHandler.getCodeAddon().manifest["summary"]


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self):
		super().__init__()
		self.submenuItem = None

		patch()
		pipeline_scope.attach_global()

		if globalVars.appArgs.secure:
			return

		self.createMenu()

		wx.CallAfter(self.checkLogRecord)

	def terminate(self):
		try:
			self.removeMenu()
		except RuntimeError:
			# wxPython raises RuntimeError for a menu whose C++ object is gone.
			pass

		unpatch()
		pipeline_scope.detach_global()

	def createMenu(self):
		self.submenuWorldVoice = wx.Menu()

		item = self.submenuWorldVoice.Append(wx.ID_ANY, _("&Settings"), _("Settings."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.popupSpeechSettingsDialog, item)
		item = self.submenuWorldVoice.Append(wx.ID_ANY, _("&File Import"), _("Import File."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onFileImport, item)
		# if not AisoundVoice.install():
		# 	item = self.submenuWorldVoice.Append(wx.ID_ANY, _("&Aisound Core Install"), _("Install Aisound Core."))
		# 	gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.onAisoundCoreInstall, item)

		self.submenuItem = gui.mainFrame.sysTrayIcon.menu.Insert(
			2,
			wx.ID_ANY,
			_("WorldVoice"),
			self.submenuWorldVoice,
		)

	def removeMenu(self):
		if self.submenuItem is not None:
			try:
				gui.mainFrame.sysTrayIcon.menu.Remove(self.submenuItem)
			except (
				AttributeError
			):  # We can get this somehow from wx python when NVDA is shuttingdown, just ignore
				pass
			self.submenuItem.Destroy()

	def onFileImport(self, event):
		with wx.FileDialog(
			gui.mainFrame,
			message=_("Import file..."),
			wildcard="zip files (*.zip)|*.zip",
		) as entryDialog:
			if entryDialog.ShowModal() != wx.ID_OK:
				return
			coreZipPath = entryDialog.GetPath()

		workspace = workspace_path()
		try:
			os.makedirs(workspace, exist_ok=True)
			extractCoreArchive(coreZipPath, workspace)
		except Exception:
			log.exception(
				f"An unexpected error occurred while processing '{os.path.basename(coreZipPath)}'",
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

	def popupSpeechSettingsDialog(self, event):
		wx.CallAfter(gui.mainFrame.popupSettingsDialog, WorldVoiceSettingsDialog)

	@script(
		description=_("popup speech settings dialog"),
		category=ADDON_SUMMARY,
	)
	def script_popup_SpeechSettingsDialog(self, gesture):
		self.popupSpeechSettingsDialog(None)

	@script(
		description=_("switch log record"),
		category=ADDON_SUMMARY,
	)
	def script_switch_log_record(self, gesture):
		if not pipelineLogService.enabled:
			wx.CallAfter(self.enableLogRecord)
		else:
			wx.CallAfter(self.disableLogRecord)

	def checkLogRecord(self):
		if pipelineLogService.enabled and askDisableOnStart():
			pipelineLogService.disable()
			pipelineLogService.export()

	def enableLogRecord(self):
		if confirmEnable(allowCancel=False) == wx.YES:
			pipelineLogService.enable()
			ui.message(_("turn on WorldVoice`s log record"))

	def disableLogRecord(self):
		pipelineLogService.disable()
		if askExport():
			pipelineLogService.export()
		ui.message(_("turn off WorldVoice`s log record"))
