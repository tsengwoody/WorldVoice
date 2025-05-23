import csv
from pathlib import Path
import shutil
import time

import addonHandler
import config
import gui
import ui
import wx

addonHandler.initTranslation()
script_dir = Path(__file__).resolve().parent
parent_dir = script_dir.parent.parent

log_dir = parent_dir / "log"
log_dir.mkdir(parents=True, exist_ok=True)

class PipelineLog:
	FIELDNAMES = ["id", "label", "timing", "timestamp", "sequence"]

	def __init__(self, log_name):
		self.log_file = log_dir / log_name
		file_exists = self.log_file.exists()
		with self.log_file.open(mode="a", encoding="utf-8", newline="") as csvfile:
			writer = csv.DictWriter(csvfile, fieldnames=self.FIELDNAMES)
			if not file_exists:
				writer.writeheader()

	def write(self, _id, label, timing, sequence):
		file_exists = self.log_file.exists()
		with self.log_file.open(mode="a", encoding="utf-8", newline="") as csvfile:
			writer = csv.DictWriter(csvfile, fieldnames=self.FIELDNAMES)
			writer.writerow({
				"id": _id,
				"label": label,
				"timing": timing,
				"timestamp": time.time(),
				"sequence": sequence,
			})

	def export(self):
		with wx.FileDialog(
			# Translators: The title of the Export pipeline log file window
			gui.mainFrame, message=_("Export pipeline log files..."),
			defaultDir="",
			defaultFile="pipeline_log.csv",
			wildcard="csv files (*.csv)|*.csv",
			style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
		) as entryDialog:
			if entryDialog.ShowModal() != wx.ID_OK:
				return
			dst = Path(entryDialog.GetPath())

		try:
			dst.parent.mkdir(parents=True, exist_ok=True)
			shutil.move(str(self.log_file), str(dst))
			wx.MessageBox(
				_("Log exported to:\n{}").format(dst),
				_("Success"),
				style=wx.OK | wx.ICON_INFORMATION
			)
		except Exception as e:
			wx.LogError(
				_("Cannot export log to {}:\n{}").format(dst, e)
			)
