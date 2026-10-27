"""Extract a WorldVoice core archive into the workspace, skipping files in use."""

import os
from zipfile import BadZipFile, ZipFile

from logHandler import log


def extractCoreArchive(archivePath: str, workspacePath: str) -> list[str]:
	"""Extract every member; return the names skipped because they are in use.

	Raises BadZipFile when the archive is corrupt.
	"""
	name = os.path.basename(archivePath)
	with ZipFile(archivePath, "r") as coreFile:
		try:
			badMember = coreFile.testzip()
		except (BadZipFile, RuntimeError) as error:
			raise BadZipFile(f"Corrupted archive '{name}': {error}") from error
		if badMember is not None:
			raise BadZipFile(f"Corrupted archive '{name}': bad member {badMember}")
		skipped = []
		for member in coreFile.infolist():
			try:
				coreFile.extract(member, path=workspacePath)
			except Exception as error:  # noqa: BLE001 - in-use files raise OS-specific errors; they are skipped and reported
				# Catching a broad Exception is intentional. Locked files (e.g., in-use DLLs)
				# can raise different errors on different OSes. This safely skips them.
				log.warning(f"Could not extract '{member.filename}' (likely in use): {error}")
				skipped.append(member.filename)
	if skipped:
		log.warning(f"Update complete. Skipped {len(skipped)} in-use file(s): {skipped}")
	else:
		log.info("All components extracted successfully.")
	return skipped
