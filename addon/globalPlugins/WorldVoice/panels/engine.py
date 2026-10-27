"""The Speech Engine panel: which engines WorldVoice loads, applied by restarting NVDA."""

from collections import OrderedDict

import addonHandler
import config
import core
import gui
import queueHandler
import wx
from synthDrivers.WorldVoice.engineRegistry import ENGINE_SPECS, get_engine_enabled

from .base import BaseSettingsPanel

addonHandler.initTranslation()


class SpeechEngineSettingsPanel(BaseSettingsPanel):
	# Translators: Title of a setting dialog.
	title = _("Speech Engine")
	field = "engine"

	def makeSettings(self, sizer):
		infoCtrl = wx.TextCtrl(
			self,
			value=_("Please select one or more speech engines to enable."),
			style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_WORDWRAP | wx.BORDER_NONE,
		)
		infoCtrl.SetBackgroundColour(self.GetBackgroundColour())
		sizer.Add(infoCtrl, proportion=1, flag=wx.EXPAND)

		group_sizer = wx.StaticBoxSizer(
			wx.StaticBox(self, label=_("Select Speech Engines to Enable")),
			wx.VERTICAL,
		)
		sizer.Add(group_sizer, proportion=1, flag=wx.EXPAND)

		self.settings = OrderedDict(
			{eng.name: {"label": eng.label, "default": eng.default_enabled} for eng in ENGINE_SPECS},
		)

		super().makeSettings(group_sizer)

		self.previousActiveEngine = {
			eng.name
			for eng in ENGINE_SPECS
			if get_engine_enabled(eng.name, config.conf["WorldVoice"]["engine"])
		}

	def isValid(self) -> bool:
		self.activeEngine = set()
		for k in self.settings:
			if getattr(self, k + "CheckBox").IsChecked():
				self.activeEngine.add(k)

		if len(self.activeEngine) == 0:
			gui.messageBox(
				# Translators: The message displayed
				_("Changes to speech-engine settings can’t be saved because no speech engine is enabled."),
				# Translators: The title of the dialog
				_("No Speech Engine Enabled"),
				wx.OK | wx.ICON_WARNING,
				self,
			)
			return False
		if self.activeEngine != self.previousActiveEngine:
			self.confirm = gui.messageBox(
				# Translators: The message displayed
				_(
					"To enable or disable the speech engine, NVDA needs to save your configuration and restart. Would you like to restart now?",
				),
				# Translators: The title of the dialog
				_("Speech Engine Change"),
				wx.YES | wx.NO | wx.CANCEL | wx.ICON_WARNING,
				self,
			)
			if self.confirm == wx.CANCEL:
				return False
		return True

	def onSave(self):
		# Write the engine flags first so the saved configuration includes them.
		if (
			self.activeEngine != self.previousActiveEngine
			and self._write_settings()
			and self.confirm == wx.YES
		):
			gui.mainFrame.onSaveConfigurationCommand(None)
			queueHandler.queueFunction(queueHandler.eventQueue, core.restart)
