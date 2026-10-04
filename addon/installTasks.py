import importlib.util
import os
from zipfile import BadZipFile

from logHandler import log

import config
import globalVars


def _load_core_archive():
	# Load by path: during installation an older `generics` may already be imported.
	path = os.path.join(os.path.dirname(__file__), "generics", "coreArchive.py")
	spec = importlib.util.spec_from_file_location("_worldvoice_install_core_archive", path)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


def _extract_core_archive(archive_path, workspace_path):
	log.info(f"Found '{os.path.basename(archive_path)}', preparing to extract to '{workspace_path}'")

	try:
		_load_core_archive().extract_core_archive(archive_path, workspace_path)
	except BadZipFile as e:
		log.error(f"Cannot extract corrupted archive '{os.path.basename(archive_path)}': {e}")
	except Exception:
		# Catch any other unexpected errors during I/O or ZipFile init.
		log.exception(f"An unexpected error occurred while processing '{os.path.basename(archive_path)}'")

	finally:
		# The source archive must be removed regardless of success or failure
		# to prevent re-installation on every startup.
		try:
			os.remove(archive_path)
			log.info(f"Source archive '{os.path.basename(archive_path)}' removed.")
		except OSError as e:
			log.warning(
				f"Could not remove source archive '{os.path.basename(archive_path)}' (it may be locked): {e}",
			)


def onInstall():
	"""
	Handles the installation of core components from zip archives.

	This function checks for '*.zip' files in the addon's 'core' directory.
	If found, it extracts their contents to the addon's workspace directory,
	safely skipping any files that are currently locked or in use.
	Each source zip file is removed after processing, regardless of whether
	all files were successfully extracted.
	"""
	log.info("Checking for WorldVoice core components to install/update...")

	# For a first-time install, set a default configuration value.
	if "WorldVoice" not in config.conf:
		log.info("First-time installation: setting default configuration.")
		config.conf["speech"]["autoLanguageSwitching"] = False

	core_dir = os.path.join(os.path.dirname(__file__), "core")
	workspace_path = os.path.join(globalVars.appArgs.configPath, "WorldVoice-workspace")
	if not os.path.isdir(core_dir):
		return

	core_zip_paths = sorted(
		os.path.join(core_dir, name) for name in os.listdir(core_dir) if name.lower().endswith(".zip")
	)
	if not core_zip_paths:
		return

	try:
		os.makedirs(workspace_path, exist_ok=True)
	except Exception:
		log.exception(f"An unexpected error occurred while preparing '{workspace_path}'")
		return

	for archive_path in core_zip_paths:
		_extract_core_archive(archive_path, workspace_path)
