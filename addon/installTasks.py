import os
from zipfile import ZipFile

import config
import globalVars


def onInstall():
	if "WorldVoice" not in config.conf:
		config.conf["speech"]["autoLanguageSwitching"] = False

	for path, import_path in [
		(os.path.join(os.path.dirname(__file__), "core.zip"), os.path.join(globalVars.appArgs.configPath, "WorldVoice-workspace")),
	]:
		try:
			with ZipFile(path, 'r') as core_file:
				core_file.testzip()
				core_file.extractall(import_path)
			os.remove(path)
		except Exception:
			pass
		else:
			pass
