import os
from zipfile import ZipFile, BadZipFile

from logHandler import log

import config
import globalVars


def onInstall():
	"""
	Handles the installation of core components from a zip archive.

	This function checks for a 'core.zip' file in the addon's directory.
	If found, it extracts its contents to the addon's workspace directory,
	safely skipping any files that are currently locked or in use.
	The 'core.zip' file is removed after the process, regardless of
	whether all files were successfully extracted.
	"""
	log.info("Checking for WorldVoice core components to install/update...")

	# For a first-time install, set a default configuration value.
	if "WorldVoice" not in config.conf:
		log.info("First-time installation: setting default configuration.")
		config.conf["speech"]["autoLanguageSwitching"] = False

	core_zip_path = os.path.join(os.path.dirname(__file__), "core.zip")
	workspace_path = os.path.join(globalVars.appArgs.configPath, "WorldVoice-workspace")

	if not os.path.exists(core_zip_path):
		return

	log.info(f"Found 'core.zip', preparing to extract to '{workspace_path}'")

	try:
		os.makedirs(workspace_path, exist_ok=True)

		with ZipFile(core_zip_path, 'r') as core_file:
			try:
				core_file.testzip()
			except (BadZipFile, RuntimeError) as e:
				log.error(f"Cannot extract corrupted archive '{os.path.basename(core_zip_path)}': {e}")
				return

			skipped_files = []
			for member in core_file.infolist():
				try:
					core_file.extract(member, path=workspace_path)
				except Exception as e:
					# Catching a broad Exception is intentional. Locked files (e.g., in-use DLLs)
					# can raise different errors on different OSes. This safely skips them.
					log.warning(f"Could not extract '{member.filename}' (likely in use): {e}")
					skipped_files.append(member.filename)
			
			if skipped_files:
				log.warning(f"Update complete. Skipped {len(skipped_files)} in-use file(s): {skipped_files}")
			else:
				log.info("All components extracted successfully.")

	except Exception:
		# Catch any other unexpected errors during I/O or ZipFile init.
		log.exception(f"An unexpected error occurred while processing '{os.path.basename(core_zip_path)}'")
	
	finally:
		# The source archive must be removed regardless of success or failure
		# to prevent re-installation on every startup.
		try:
			os.remove(core_zip_path)
			log.info(f"Source archive '{os.path.basename(core_zip_path)}' removed.")
		except OSError as e:
			log.warning(f"Could not remove source archive '{os.path.basename(core_zip_path)}' (it may be locked): {e}")
