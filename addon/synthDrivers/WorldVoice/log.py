import csv
import shutil
import time
from pathlib import Path

script_dir = Path(__file__).resolve().parent
parent_dir = script_dir.parent.parent

log_dir = parent_dir / "log"
MAX_LOG_SIZE = 5 * 1024 * 1024


class PipelineLog:
	FIELDNAMES = ["id", "label", "timing", "timestamp", "sequence"]

	def __init__(self, log_name):
		self.log_file = log_dir / log_name

	def _ensure_log_file(self):
		self.log_file.parent.mkdir(parents=True, exist_ok=True)
		if self.log_file.exists() and self.log_file.stat().st_size > 0:
			return
		with self.log_file.open(mode="a", encoding="utf-8", newline="") as csvfile:
			csv.DictWriter(csvfile, fieldnames=self.FIELDNAMES).writeheader()

	def _rotate_if_needed(self):
		if not self.log_file.exists() or self.log_file.stat().st_size < MAX_LOG_SIZE:
			return
		old = self.log_file.with_suffix(".old")
		if old.exists():
			old.unlink()
		shutil.move(str(self.log_file), str(old))

	def write(self, _id, label, timing, sequence):
		self._rotate_if_needed()
		self._ensure_log_file()
		with self.log_file.open(mode="a", encoding="utf-8", newline="") as csvfile:
			writer = csv.DictWriter(csvfile, fieldnames=self.FIELDNAMES)
			writer.writerow(
				{
					"id": _id,
					"label": label,
					"timing": timing,
					"timestamp": time.time(),
					"sequence": sequence,
				},
			)

	def move_to(self, dst: Path) -> None:
		"""Move the current log to dst and start a new, empty one."""
		# A log nobody has written yet still exports, as a header-only file.
		self._ensure_log_file()
		dst.parent.mkdir(parents=True, exist_ok=True)
		shutil.move(str(self.log_file), str(dst))
		self._ensure_log_file()
