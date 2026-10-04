"""Extract a WorldVoice core archive into the workspace, skipping files in use."""

import os
from zipfile import BadZipFile, ZipFile

from logHandler import log


def extract_core_archive(archive_path: str, workspace_path: str) -> list[str]:
	"""Extract every member; return the names skipped because they are in use.

	Raises BadZipFile when the archive is corrupt.
	"""
	name = os.path.basename(archive_path)
	with ZipFile(archive_path, "r") as core_file:
		try:
			bad_member = core_file.testzip()
		except (BadZipFile, RuntimeError) as error:
			raise BadZipFile(f"Corrupted archive '{name}': {error}") from error
		if bad_member is not None:
			raise BadZipFile(f"Corrupted archive '{name}': bad member {bad_member}")
		skipped = []
		for member in core_file.infolist():
			try:
				core_file.extract(member, path=workspace_path)
			except Exception as error:
				# Catching a broad Exception is intentional. Locked files (e.g., in-use DLLs)
				# can raise different errors on different OSes. This safely skips them.
				log.warning(f"Could not extract '{member.filename}' (likely in use): {error}")
				skipped.append(member.filename)
	if skipped:
		log.warning(f"Update complete. Skipped {len(skipped)} in-use file(s): {skipped}")
	else:
		log.info("All components extracted successfully.")
	return skipped
