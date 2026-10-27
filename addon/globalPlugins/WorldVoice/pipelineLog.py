"""Turning the speech pipeline log on and off, shared by the plugin and the log panel."""

from pathlib import Path

import addonHandler
import config
import gui
import wx
from logHandler import log
from synthDrivers.WorldVoice.pipeline.registry import pl
from synthDrivers.WorldVoice.pipeline.settings import read_stored

addonHandler.initTranslation()


class PipelineLogService:
	def __init__(self, confProvider=lambda: config.conf, exporter=None):
		self._confProvider = confProvider
		self._exporter = exporter or exportWithDialog

	def _section(self):
		return self._confProvider()["WorldVoice"]["log"]

	@property
	def enabled(self) -> bool:
		return bool(read_stored(self._section(), "enable", False))

	def enable(self) -> None:
		self._section()["enable"] = True

	def disable(self) -> None:
		self._section()["enable"] = False

	def export(self) -> None:
		try:
			self._exporter()
		except Exception:
			log.error("WorldVoice: exporting the pipeline log failed", exc_info=True)


def exportWithDialog(pipelineLogFile=None):
	"""Ask where to save the pipeline log, move it there and report the result."""
	pipelineLogFile = pipelineLogFile or pl
	with wx.FileDialog(
		gui.mainFrame,
		# Translators: The title of the Export pipeline log file window
		message=_("Export pipeline log files..."),
		defaultDir="",
		defaultFile="pipeline_log.csv",
		wildcard="csv files (*.csv)|*.csv",
		style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
	) as entryDialog:
		if entryDialog.ShowModal() != wx.ID_OK:
			return
		dst = Path(entryDialog.GetPath())

	try:
		pipelineLogFile.move_to(dst)
		wx.MessageBox(
			_("Log exported to:\n{}").format(dst),
			_("Success"),
			style=wx.OK | wx.ICON_INFORMATION,
		)
	except Exception as e:  # noqa: BLE001 - reported to the user
		wx.LogError(
			_("Cannot export log to {}:\n{}").format(dst, e),
		)


pipelineLogService = PipelineLogService()


def confirmEnable(*, allowCancel: bool) -> int:
	buttons = wx.YES | wx.NO | (wx.CANCEL if allowCancel else 0)
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


def askExport() -> bool:
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


def askDisableOnStart() -> bool:
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
