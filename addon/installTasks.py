import os
import shutil
from zipfile import ZipFile

import buildVersion
import config
import globalVars


def onInstall():
	if "WorldVoice" not in config.conf:
		config.conf["speech"]["autoLanguageSwitching"] = False

	version = "2024" if buildVersion.formatBuildVersionString().split(".")[0] == "2024" else "2025"
	src = os.path.join(os.path.dirname(__file__), "driver", version)
	dst = os.path.join(os.path.dirname(__file__), "synthDrivers", "WorldVoice", "voice")
	shutil.copytree(src, dst)

	for path, import_path in [
		(os.path.join(os.path.dirname(__file__), "core.zip"), os.path.join(globalVars.appArgs.configPath, "WorldVoice-workspace")),
	]:
		try:
			with ZipFile(path, 'r') as core_file:
				core_file.testzip()
				core_file.extractall(import_path)
			# os.remove(path)
		except Exception:
			pass
		else:
			pass
