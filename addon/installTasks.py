import importlib.util
import os
from zipfile import BadZipFile

import config
from logHandler import log


def _load_by_path(name, *parts):
	path = os.path.join(os.path.dirname(__file__), *parts)
	spec = importlib.util.spec_from_file_location(name, path)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


def _load_core_archive():
	# Load by path: during installation an older `generics` may already be imported.
	return _load_by_path("_worldvoice_install_core_archive", "generics", "coreArchive.py")


def _workspace_path():
	# Load by path too: the add-on being installed is not importable yet.
	module = _load_by_path("_worldvoice_install_workspace", "synthDrivers", "WorldVoice", "workspace.py")
	return module.workspace_path()


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

	if "WorldVoice" not in config.conf:
		log.info("First-time installation: setting default configuration.")
		# WorldVoice detects languages itself and inserts WVLangChangeCommand. With NVDA's
		# automatic language switching on, NVDA would add its own LangChangeCommand set from
		# document markup on top. Turn it off once; users may turn it back on, and WorldVoice
		# honours both command types.
		config.conf["speech"]["autoLanguageSwitching"] = False

	core_dir = os.path.join(os.path.dirname(__file__), "core")
	if not os.path.isdir(core_dir):
		return

	core_zip_paths = sorted(
		os.path.join(core_dir, name) for name in os.listdir(core_dir) if name.lower().endswith(".zip")
	)
	if not core_zip_paths:
		return

	workspace_path = _workspace_path()
	try:
		os.makedirs(workspace_path, exist_ok=True)
	except Exception:
		log.exception(f"An unexpected error occurred while preparing '{workspace_path}'")
		return

	for archive_path in core_zip_paths:
		_extract_core_archive(archive_path, workspace_path)
