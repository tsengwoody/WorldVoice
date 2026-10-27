"""Shared parts of the WorldVoice settings panels."""

from collections import OrderedDict

import addonHandler
import config
import tones
import wx
from gui import guiHelper
from gui.settingsDialogs import SettingsPanel
from logHandler import log
from synthDrivers.WorldVoice.pipeline.settings import read_stored

addonHandler.initTranslation()


def _asBool(value):
	if isinstance(value, str):
		return value.lower() not in {"false", "0", ""}
	return bool(value)


class BaseSettingsPanel(SettingsPanel):
	# Translators: Title of a setting dialog.
	title = _("WorldVoice")
	settings = OrderedDict({})  # noqa: RUF012
	field = "WorldVoice"

	def makeSettings(self, settingsSizer, settingsSizerHelper=None):
		if not settingsSizerHelper:
			settingsSizerHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		for k, v in self.settings.items():
			if "options" in v:
				attr = k + "Selection"
				options = v["options"]
				widget = settingsSizerHelper.addLabeledControl(
					v["label"],
					wx.Choice,
					choices=list(options.values()),
				)
				setattr(self, attr, widget)
				try:
					index = list(v["options"].keys()).index(str(config.conf["WorldVoice"][self.field][k]))
				except Exception:  # noqa: BLE001 - a missing or invalid stored value selects the first option
					log.debugWarning(f"Invalid stored WorldVoice {self.field} {k}", exc_info=True)
					index = 0
				widget.Selection = index
			else:
				setattr(
					self,
					k + "CheckBox",
					settingsSizerHelper.addItem(wx.CheckBox(self, label=v["label"])),
				)
				# A value NVDA refuses on read shows the default, so the panel still opens.
				value = read_stored(config.conf["WorldVoice"][self.field], k, v.get("default", False))
				getattr(self, k + "CheckBox").SetValue(_asBool(value))
		return settingsSizerHelper

	def onSave(self) -> None:
		self._writeSettings()

	def _writeSettings(self) -> bool:
		"""Write the panel's widgets to config; return False if any value could not be written.

		Every widget is read before anything is written, so a failed read leaves config untouched.
		"""
		try:
			values = {}
			for k, v in self.settings.items():
				if "options" in v:
					widget = getattr(self, k + "Selection")
					values[k] = list(v["options"].keys())[widget.GetSelection()]
				else:
					values[k] = getattr(self, k + "CheckBox").IsChecked()
			for k, value in values.items():
				config.conf["WorldVoice"][self.field][k] = value
		except Exception:
			log.error("WorldVoice: failed to save %s settings", self.field, exc_info=True)
			tones.beep(100, 100)
			return False
		return True


def notWorldVoiceNotice(panel, sizer):
	"""Show the read-only note that WorldVoice is not the synthesizer in a panel that needs it."""
	infoCtrl = wx.TextCtrl(
		panel,
		# Translators: Shown in place of a settings panel that needs WorldVoice as the speech synthesizer.
		value=_("Your current speech synthesizer is not WorldVoice."),
		style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_WORDWRAP | wx.BORDER_NONE,
	)
	infoCtrl.SetBackgroundColour(panel.GetBackgroundColour())
	sizer.Add(infoCtrl, proportion=1, flag=wx.EXPAND)
