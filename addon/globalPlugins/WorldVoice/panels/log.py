"""The Log Record panel: the speech pipeline log and a switch for each logged stage."""

from collections import OrderedDict

import addonHandler
import wx
from synthDrivers.WorldVoice.pipeline.registry import LOG_SWITCHES
from synthDrivers.WorldVoice.pipeline.settings import PIPELINE_SETTINGS

from ..pipelineLog import ask_export, confirm_enable, pipeline_log
from .base import BaseSettingsPanel

addonHandler.initTranslation()


# Labels of the log switches that have no pipeline setting of their own.
_STAGE_LOG_LABELS = {
	# Translators: Label for the pipeline log switch of a speech pipeline stage.
	"apply_speech_dictionaries": _("Apply speech dictionaries"),
	# Translators: Label for the pipeline log switch of a speech pipeline stage.
	"speech_viewer": _("Speech viewer"),
}
# One label per log switch, in LOG_SWITCHES order. A stage named after a pipeline setting uses that
# setting's name: its settings-ring name, else its label (tests keep "&" out of these).
_SETTING_NAMES = {spec.key: spec.display_name or spec.label for spec in PIPELINE_SETTINGS}
_LOG_LABELS = {key: _SETTING_NAMES.get(key) or _STAGE_LOG_LABELS.get(key, key) for key in LOG_SWITCHES}


class LogSettingsPanel(BaseSettingsPanel):
	# Translators: Title of a setting dialog.
	title = _("Log Record")
	field = "log"
	settings = OrderedDict(  # noqa: RUF012
		(key, {"label": _LOG_LABELS[key]}) for key in LOG_SWITCHES
	)

	def makeSettings(self, sizer):
		self._enable_checkbox = wx.CheckBox(
			self,
			label=_("Enable logging of WorldVoice’s speech pipeline"),
		)
		sizer.Add(self._enable_checkbox, proportion=1, flag=wx.EXPAND)
		group_sizer = wx.StaticBoxSizer(
			wx.StaticBox(self, label=_("Select Speech Pipelines to Enable")),
			wx.VERTICAL,
		)
		sizer.Add(group_sizer, proportion=1, flag=wx.EXPAND)

		self.Bind(wx.EVT_CHECKBOX, self.onEnableCheckboxChange, self._enable_checkbox)
		self._enable_checkbox.SetValue(pipeline_log.enabled)
		super().makeSettings(group_sizer)
		self.onEnableCheckboxChange(None)

	def onEnableCheckboxChange(self, event):
		if self._enable_checkbox.GetValue():
			self.sliderEnable()
		else:
			self.sliderDisable()

	def sliderEnable(self):
		for k in self.settings:
			getattr(self, k + "CheckBox").Enable()

	def sliderDisable(self):
		for k in self.settings:
			getattr(self, k + "CheckBox").Disable()

	def isValid(self) -> bool:
		if self._enable_checkbox.GetValue() and not pipeline_log.enabled:
			answer = confirm_enable(allow_cancel=True)
			if answer == wx.CANCEL:
				self._enable_checkbox.SetValue(False)
				self.onEnableCheckboxChange(None)
				return False
			if answer != wx.YES:
				# "No" keeps logging off; show that instead of a checked box.
				self._enable_checkbox.SetValue(False)
				self.onEnableCheckboxChange(None)
		return True

	def onSave(self):
		enabled_before = pipeline_log.enabled
		enabled_after = self._enable_checkbox.GetValue()
		# Written on every save, like the stage switches (decided by the user, 2026-10-22,
		# fix/uniform-settings-save): NVDA skips an unchanged value and replaces a refused one.
		# isValid already confirmed turning logging on, or unticked the box when it was declined.
		if enabled_after:
			pipeline_log.enable()
		else:
			pipeline_log.disable()
		if enabled_before and not enabled_after and ask_export():
			wx.CallAfter(pipeline_log.export)
		self._write_settings()
