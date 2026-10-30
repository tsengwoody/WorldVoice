import importlib.util
import os
from zipfile import BadZipFile

import config
from logHandler import log


def _loadByPath(name, *parts):
	path = os.path.join(os.path.dirname(__file__), *parts)
	spec = importlib.util.spec_from_file_location(name, path)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


def _loadCoreArchive():
	# Load by path: during installation an older `generics` may already be imported.
	return _loadByPath("_worldvoice_install_core_archive", "generics", "coreArchive.py")


def _workspacePath():
	# Load by path too: the add-on being installed is not importable yet.
	module = _loadByPath("_worldvoice_install_workspace", "synthDrivers", "WorldVoice", "workspace.py")
	return module.workspace_path()


def _extractCoreArchive(archivePath, workspacePath):
	log.info(f"Found '{os.path.basename(archivePath)}', preparing to extract to '{workspacePath}'")

	try:
		_loadCoreArchive().extractCoreArchive(archivePath, workspacePath)
	except BadZipFile as e:
		log.error(f"Cannot extract corrupted archive '{os.path.basename(archivePath)}': {e}")
	except Exception:
		# Catch any other unexpected errors during I/O or ZipFile init.
		log.exception(f"An unexpected error occurred while processing '{os.path.basename(archivePath)}'")

	finally:
		# The source archive must be removed regardless of success or failure
		# to prevent re-installation on every startup.
		try:
			os.remove(archivePath)
			log.info(f"Source archive '{os.path.basename(archivePath)}' removed.")
		except OSError as e:
			log.warning(
				f"Could not remove source archive '{os.path.basename(archivePath)}' (it may be locked): {e}",
			)


def _isRoleSection(value):
	# As roles._is_section (copied: the add-on being installed is not importable). A dict here,
	# NVDA's AggregatedSection (a mapping, but not a dict) in NVDA.
	return hasattr(value, "items") and hasattr(value, "get")


def _plainSection(value):
	return {key: _plainSection(item) if _isRoleSection(item) else item for key, item in value.items()}


def _removeLegacyRoleKeys():
	"""Drop the speech roles stored under a full locale (zh_TW, pt-br), once per install.

	Versions before 2026-07-28 also wrote the main voice's full locale; the speech role panel
	shows and writes only primary languages (zh, en), and the lookup prefers a full-locale key,
	so such a key would speak instead of the panel's role, with no way to remove it.
	Only the normal configuration is cleaned, and only while no profile is active; NVDA saves
	it on exit.
	"""
	try:
		if "WorldVoice" not in config.conf or "role" not in config.conf["WorldVoice"]:
			return
		if len(config.conf.profiles) != 1:
			# The roles read merge every active configuration and a write goes to the last one, so
			# cleaning now would copy the normal configuration's roles into the profile instead.
			log.info("Legacy speech role keys not checked: a configuration profile is active")
			return
		roles = config.conf["WorldVoice"]["role"]
		legacy = [
			locale
			for locale, value in roles.items()
			if ("_" in locale or "-" in locale) and _isRoleSection(value)
		]
		if not legacy:
			return
		# Assigning a section replaces it in the profile NVDA writes to.
		config.conf["WorldVoice"]["role"] = {
			locale: _plainSection(value) if _isRoleSection(value) else value
			for locale, value in roles.items()
			if locale not in legacy
		}
		log.info(f"Removed legacy speech role keys: {legacy}")
	except Exception:
		log.exception("Could not remove legacy speech role keys")


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
	else:
		_removeLegacyRoleKeys()

	coreDir = os.path.join(os.path.dirname(__file__), "core")
	if not os.path.isdir(coreDir):
		return

	coreZipPaths = sorted(
		os.path.join(coreDir, name) for name in os.listdir(coreDir) if name.lower().endswith(".zip")
	)
	if not coreZipPaths:
		return

	workspacePath = _workspacePath()
	try:
		os.makedirs(workspacePath, exist_ok=True)
	except Exception:
		log.exception(f"An unexpected error occurred while preparing '{workspacePath}'")
		return

	for archivePath in coreZipPaths:
		_extractCoreArchive(archivePath, workspacePath)
