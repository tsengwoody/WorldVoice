# -*- coding: utf-8 -*-

import os
import sys
base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
addon_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
synth_drivers_path = os.path.join(addon_path, 'synthDrivers', 'WorldVoiceXVED2')
sys.path.insert(0, base_dir)

import webbrowser
import wx

import addonHandler
addonHandler.initTranslation()
import globalPluginHandler
import globalVars
import gui
from logHandler import log
import speech

from .languageSettingsDialog import LanguageSettingsDialog
from .speechSettingsDialog import SpeechSettingsDialog
from generics.views import SpeechSymbolsDialog


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self):
		super(GlobalPlugin, self).__init__()
		self.ve = False
		self.initialize()

	def initialize(self):
		if globalVars.appArgs.secure:
			return
		if not os.path.isdir(os.path.join(synth_drivers_path, 'common')):
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
			item = self.submenu_vocalizer.Append(wx.ID_ANY, _("Automatic &Language Switching Settings"), _("Configure which voice is to be used for each language."))
			gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU , lambda e : gui.mainFrame._popupSettingsDialog(LanguageSettingsDialog()), item)
			item = self.submenu_vocalizer.Append(wx.ID_ANY, _("&Speech Settings"), _("Configure speech rate each voice."))
			gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU , lambda e : gui.mainFrame._popupSettingsDialog(SpeechSettingsDialog()), item)
			item = self.submenu_vocalizer.Append(wx.ID_ANY, _("&Unicode Settings"), _("Configure unicode setting."))
			gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU , lambda e : gui.mainFrame._popupSettingsDialog(SpeechSymbolsDialog), item)
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
					core_file.extractall(synth_drivers_path)
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
