import os
import sys

import wx

import addonHandler
import config
import globalPluginHandler
import globalVars
import gui
from logHandler import log
from scriptHandler import script, getLastScriptRepeatCount
import speech
import ui

from .speechSettingsDialog import SpeechSettingsDialog
from generics.speechSymbols.views import SpeechSymbolsDialog
from synthDrivers.WorldVoice import VEVoice, Sapi5Voice, AisoundVoice

addonHandler.initTranslation()
ADDON_SUMMARY = addonHandler.getCodeAddon().manifest["summary"]
workspace_path = os.path.join(globalVars.appArgs.configPath, "WorldVoice-workspace")

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self):
		super().__init__()
		try:
			from speech.sayAll import initialize as sayAllInitialize
			sayAllInitialize(
				speech.speech.speak,
				speech.speech.speakObject,
				speech.speech.getTextInfoSpeech,
				speech.speech.SpeakTextInfoState,
			)
		except:
			pass

		if globalVars.appArgs.secure:
			return
		self.createMenu()

	def createMenu(self):
		self.submenu_vocalizer = wx.Menu()

		item = self.submenu_vocalizer.Append(wx.ID_ANY, _("&Speech Settings"), _("Speech Settings."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.popup_SpeechSettingsDialog, item)
		item = self.submenu_vocalizer.Append(wx.ID_ANY, _("&Unicode Settings"), _("Unicode Settings."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU , self.popup_SpeechSymbolsDialog, item)
		item = self.submenu_vocalizer.Append(wx.ID_ANY, _("&File Import"), _("Import File."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU , self.onFileImport, item)
		if not VEVoice.install():
			item = self.submenu_vocalizer.Append(wx.ID_ANY, _("&VE core install"), _("install VE core."))
			gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU , self.onVECoreInstall, item)
		if not AisoundVoice.install():
			item = self.submenu_vocalizer.Append(wx.ID_ANY, _("&aisound core install"), _("install aisound core."))
			gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU , self.onAisoundCoreInstall, item)

		self.submenu_item = gui.mainFrame.sysTrayIcon.menu.Insert(2, wx.ID_ANY, _("WorldVoice"), self.submenu_vocalizer)

	def removeMenu(self):
		if self.submenu_item is not None:
			try:
				gui.mainFrame.sysTrayIcon.menu.Remove(self.submenu_item)
			except AttributeError: # We can get this somehow from wx python when NVDA is shuttingdown, just ignore
				pass
			self.submenu_item.Destroy()

	def fileImport(self, import_path):
		with wx.FileDialog(gui.mainFrame, message=_("Import file..."), wildcard="zip files (*.zip)|*.zip") as entryDialog:
			if entryDialog.ShowModal() != wx.ID_OK:
				return

			path = entryDialog.GetPath()
			try:
				from zipfile import ZipFile
				with ZipFile(path, 'r') as core_file:
					core_file.testzip()
					core_file.extractall(import_path)
			except:
				gui.messageBox(
					_("Import fail"),
					_("Import File"),wx.OK
				)
			else:
				if gui.messageBox(
					_("For the new file to import, NVDA must be restarted. Are you want to restart NVDA now ?"),
					_("Import File"),wx.OK|wx.CANCEL|wx.ICON_WARNING
				)==wx.OK:
					import core
					import queueHandler
					queueHandler.queueFunction(queueHandler.eventQueue,core.restart)

	def onFileImport(self, event):
		self.fileImport(workspace_path)

	def onVECoreInstall(self, event):
		self.fileImport(VEVoice.workspace)

	def onAisoundCoreInstall(self, event):
		self.fileImport(AisoundVoice.workspace)

	def  terminate(self):
		try:
			self.removeMenu()
		except wx.PyDeadObjectError:
			pass

	def popup_SpeechSettingsDialog(self, event):
		if SpeechSettingsDialog._instance is None:
			gui.mainFrame._popupSettingsDialog(SpeechSettingsDialog)
		else:
			ui.message(_("SpeechSettingsDialog have already been opened"))

	def popup_SpeechSymbolsDialog(self, event):
		if SpeechSymbolsDialog._instance is None:
			gui.mainFrame._popupSettingsDialog(SpeechSymbolsDialog)
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
	def script_popup_SpeechSymbolsDialog(self, gesture):
		self.popup_SpeechSymbolsDialog(None)
