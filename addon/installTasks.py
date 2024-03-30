import os
from zipfile import ZipFile

import config
import globalVars


def onInstall():
	if "WorldVoice" not in config.conf:
		config.conf["speech"]["autoLanguageSwitching"] = False
	for path, import_path in [
		(os.path.join(os.path.dirname(__file__), "core", "VE.zip"), os.path.join(globalVars.appArgs.configPath, "WorldVoice-workspace", "VE")),
		(os.path.join(os.path.dirname(__file__), "core", "aisound.zip"), os.path.join(globalVars.appArgs.configPath, "WorldVoice-workspace", "aisound")),
		(os.path.join(os.path.dirname(__file__), "voice", "voice.zip"), os.path.join(globalVars.appArgs.configPath, "WorldVoice-workspace")),
	]:
		try:
			with ZipFile(path, 'r') as core_file:
				core_file.testzip()
				core_file.extractall(import_path)
			os.remove(path)
		except BaseException:
			pass
		else:
			pass
