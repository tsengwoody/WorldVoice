# -*- coding: utf-8 -*-

import webbrowser
import wx

import addonHandler
addonHandler.initTranslation()
import globalPluginHandler
import globalVars
import gui
from logHandler import log
import speech

from .dialogs import *
from .speechRate import *

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self):
		super(GlobalPlugin, self).__init__()
		if globalVars.appArgs.secure:
			return
		# See if we have at least one voice installed
		if not any(addon.name.startswith("vocalizer-expressive-voice") for addon in addonHandler.getRunningAddons()):
			wx.CallLater(2000, self.onNoVoicesInstalled)
			return
		with VocalizerOpened():
			self.createMenu()
			from synthDrivers.MultipleWorldVoice import _config
			_config.load()

	def createMenu(self):
		self.submenu_vocalizer = wx.Menu()
		item = self.submenu_vocalizer.Append(wx.ID_ANY, _("Automatic &Language Switching Settings"), _("Configure which voice is to be used for each language."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU , lambda e : gui.mainFrame._popupSettingsDialog(VocalizerLanguageSettingsDialog), item)
		item = self.submenu_vocalizer.Append(wx.ID_ANY, _("&Speech Rate Settings"), _("Configure speech rate each voice."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU , lambda e : gui.mainFrame._popupSettingsDialog(SpeechRateSettingsDialog), item)
		self.submenu_item = gui.mainFrame.sysTrayIcon.menu.Insert(2, wx.ID_ANY, _("Multiple World-Voice"), self.submenu_vocalizer)

	def removeMenu(self):
		if self.submenu_item is not None:
			try:
				gui.mainFrame.sysTrayIcon.menu.Remove(self.submenu_item)
			except AttributeError: # We can get this somehow from wx python when NVDA is shuttingdown, just ignore
				pass
			self.submenu_item.Destroy()

	def _openVoicesDownload(self):
		VOICE_DOWNLOADS_URL_TEMPLATE = "https://vocalizer-nvda.com/downloads?lang={lang}"
		webbrowser.open(VOICE_DOWNLOADS_URL_TEMPLATE.format(
			lang=languageHandler.getLanguage().split("_")[0]
		))

	def onNoVoicesInstalled(self):
		if gui.messageBox(_("You have no Vocalizer voices installed.\n"
		"You need at least one voice installed to use Vocalizer for NVDA.\n"
		"You can download all Vocalizer voices from the product web page.\n"
		"Do you want to open the vocalizer for NVDA voices download page now?"),
		caption=_("No voices installed."), style=wx.YES_NO|wx.ICON_WARNING) == wx.YES:
			self._openVoicesDownload()

	def  terminate(self):
		try:
			self.removeMenu()
		except wx.PyDeadObjectError:
			pass
