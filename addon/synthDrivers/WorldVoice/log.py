import csv
from pathlib import Path
import shutil
import time

import addonHandler
import gui
import wx

addonHandler.initTranslation()
script_dir = Path(__file__).resolve().parent
parent_dir = script_dir.parent.parent

log_dir = parent_dir / "log"

MAX_LOG_SIZE = 5 * 1024 * 1024


class PipelineLog:
	FIELDNAMES = ["id", "label", "timing", "timestamp", "sequence"]

	def __init__(self, log_name):
		self.log_file = log_dir / log_name
		self._csvfile = None
		self._writer = None
		self._open()

	def _open(self):
		if self._csvfile is not None:
			return
		log_dir.mkdir(parents=True, exist_ok=True)
		file_exists = self.log_file.exists()
		self._csvfile = self.log_file.open(mode="a", encoding="utf-8", newline="")
		self._writer = csv.DictWriter(self._csvfile, fieldnames=self.FIELDNAMES)
		if not file_exists:
			self._writer.writeheader()
			self._csvfile.flush()

	def close(self):
		if self._csvfile is not None:
			self._csvfile.close()
			self._csvfile = None
			self._writer = None

	def _rotate_if_needed(self):
		if self._csvfile is None:
			return
		if self.log_file.stat().st_size < MAX_LOG_SIZE:
			return
		self.close()
		old = self.log_file.with_suffix(".old")
		if old.exists():
			old.unlink()
		shutil.move(str(self.log_file), str(old))
		self._open()

	def write(self, _id, label, timing, sequence):
		self._open()
		self._rotate_if_needed()
		self._writer.writerow({
			"id": _id,
			"label": label,
			"timing": timing,
			"timestamp": time.time(),
			"sequence": sequence,
		})
		self._csvfile.flush()

	def export(self):
		self.close()
		with wx.FileDialog(
			# Translators: The title of the Export pipeline log file window
			gui.mainFrame, message=_("Export pipeline log files..."),
			defaultDir="",
			defaultFile="pipeline_log.csv",
			wildcard="csv files (*.csv)|*.csv",
			style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
		) as entryDialog:
			if entryDialog.ShowModal() != wx.ID_OK:
				self._open()
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
		finally:
			self._open()
