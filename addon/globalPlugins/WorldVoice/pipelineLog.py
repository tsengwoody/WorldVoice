"""Turning the speech pipeline log on and off, shared by the plugin and the log panel."""

import addonHandler
import config
import gui
import wx
from logHandler import log
from synthDrivers.WorldVoice.pipeline import pl

addonHandler.initTranslation()


class PipelineLogService:
	def __init__(self, conf_provider=lambda: config.conf, exporter=None):
		self._conf_provider = conf_provider
		self._exporter = exporter or pl.export

	def _section(self):
		return self._conf_provider()["WorldVoice"]["log"]

	@property
	def enabled(self) -> bool:
		return bool(self._section()["enable"])

	def enable(self) -> None:
		self._section()["enable"] = True

	def disable(self) -> None:
		self._section()["enable"] = False

	def export(self) -> None:
		try:
			self._exporter()
		except Exception:
			log.error("WorldVoice: exporting the pipeline log failed", exc_info=True)


pipeline_log = PipelineLogService()


def confirm_enable(*, allow_cancel: bool) -> int:
	buttons = wx.YES | wx.NO | (wx.CANCEL if allow_cancel else 0)
	return gui.messageBox(
		# Translators: The message displayed
		_(
			"Enabling logging of WorldVoice’s speech pipeline will reduce speech response speed. If you are not debugging, we recommend keeping it disabled. Would you like to enable it anyway?",
		),
		# Translators: The title of the dialog
		_("Speech Pipeline Logging"),
		buttons,
		gui.mainFrame,
	)


def ask_export() -> bool:
	return (
		gui.messageBox(
			# Translators: The message displayed
			_(
				"Logging of WorldVoice’s speech pipeline has been disabled. Would you like to export the pipeline log now?",
			),
			# Translators: The title of the dialog
			_("Speech Pipeline Logging"),
			wx.YES | wx.NO,
			gui.mainFrame,
		)
		== wx.YES
	)


def ask_disable_on_start() -> bool:
	return (
		gui.messageBox(
			# Translators: The message displayed
			_(
				"Logging of WorldVoice’s speech pipeline is enabled. This may reduce speech response speed. If you are not debugging, we recommend disabling it. Would you like to disable it now?",
			),
			# Translators: The title of the dialog
			_("Speech Pipeline Logging"),
			wx.YES | wx.NO,
			gui.mainFrame,
		)
		== wx.YES
	)
