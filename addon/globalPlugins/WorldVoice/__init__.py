import os
import sys
base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
addon_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
synth_drivers_path = os.path.join(addon_path, 'synthDrivers', 'WorldVoice')
sys.path.insert(0, base_dir)

import wx

import addonHandler
import config
import globalPluginHandler
import globalVars
import gui
from logHandler import log
from scriptHandler import script
import speech
import ui

from .speechSettingsDialog import SpeechSettingsDialog
from generics.speechSymbols.views import SpeechSymbolsDialog
from synthDrivers.WorldVoice import _config

addonHandler.initTranslation()
ADDON_SUMMARY = addonHandler.getCodeAddon().manifest["summary"]
SpeechSettingsDialog = SpeechSettingsDialog()
workspaceVE_path = os.path.join(globalVars.appArgs.configPath, "WorldVoice-workspace", "VE")

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
		self.ve = False
		self.initialize()

	def initialize(self):
		if globalVars.appArgs.secure:
			return
		if not os.path.isdir(os.path.join(workspaceVE_path, 'common')):
			self.createMenu()
			wx.CallLater(2000, self.onNoCoreInstalled)
			return
		try:
			self.ve = True
			self.createMenu()
		except:
			self.createMenu()

	def createMenu(self):
		self.submenu_vocalizer = wx.Menu()
		if self.ve:
			item = self.submenu_vocalizer.Append(wx.ID_ANY, _("&Speech Settings"), _("Speech Settings."))
			gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self.popup_SpeechSettingsDialog, item)
			item = self.submenu_vocalizer.Append(wx.ID_ANY, _("&Unicode Settings"), _("Unicode Settings."))
			gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU , self.popup_SpeechSymbolsDialog, item)
		item = self.submenu_vocalizer.Append(wx.ID_ANY, _("&File Import"), _("Import File."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU , self.onFileImport, item)
		self.submenu_item = gui.mainFrame.sysTrayIcon.menu.Insert(2, wx.ID_ANY, _("WorldVoice(VE)"), self.submenu_vocalizer)

	def removeMenu(self):
		if self.submenu_item is not None:
			try:
				gui.mainFrame.sysTrayIcon.menu.Remove(self.submenu_item)
			except AttributeError: # We can get this somehow from wx python when NVDA is shuttingdown, just ignore
				pass
			self.submenu_item.Destroy()

	def onFileImport(self, event):
		with wx.FileDialog(gui.mainFrame, message=_("Import file..."), wildcard="zip files (*.zip)|*.zip") as entryDialog:
			if entryDialog.ShowModal() != wx.ID_OK:
				return

			path = entryDialog.GetPath()
			try:
				from zipfile import ZipFile
				with ZipFile(path, 'r') as core_file:
					core_file.testzip()
					core_file.extractall(workspaceVE_path)
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

	def onNoCoreInstalled(self):
		if gui.messageBox(_("You have no core(driver 2) installed.\n"
		"Do you want to install the core(driver 2) now?"),
		caption=_("No core installed."), style=wx.YES_NO|wx.ICON_WARNING) == wx.YES:
			self.onFileImport(None)

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
		gesture="kb:NVDA+alt+l",
		description=_("popup SpeechSettingsDialog"),
		category=ADDON_SUMMARY,
	)
	def script_demo(self, gesture):
		from synthDriverHandler import getSynth
		synthInstance = getSynth()
		voiceManager = synthInstance._voiceManager
		voiceManager.sapi5.rate = 20
		voiceManager.sapi5.speak("hello world")
		voiceManager._defaultVoiceInstance.speak("hello world")
		voiceManager.sapi52.rate = 35
		voiceManager.sapi52.speak("hello world")

	@script(
		description=_("popup SpeechSettingsDialog"),
		category=ADDON_SUMMARY,
	)
	def script_popup_SpeechSettingsDialog(self, gesture):
		self.popup_SpeechSettingsDialog(None)

	@script(
		description=_("popup SpeechSymbolsDialog"),
		category=ADDON_SUMMARY,
	)
	def script_popup_SpeechSymbolsDialog(self, gesture):
		self.popup_SpeechSymbolsDialog(None)
