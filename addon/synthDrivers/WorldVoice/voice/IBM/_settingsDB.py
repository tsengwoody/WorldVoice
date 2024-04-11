# -*- coding: UTF-8 -*-
#Copyright (C) 2009 - 2019 David CM, released under the GPL.
# Author: David CM <dhf360@gmail.com> and others.
#synthDrivers/settingsDB.py

from ._configHelper import configSpec, registerConfig, boolValidator

import globalVars
import os

BASE_PATH = os.path.join(globalVars.appArgs.configPath, "WorldVoice-workspace", "IBM")

# Add-on config database
@configSpec("ibmeci")
class _AppConfig:
	dllName = ("string(default='eci.dll')", True)
	TTSPath = ("string(default='ibmtts')", True)
	autoUpdate  = ('boolean(default=True)', True, boolValidator)
appConfig = registerConfig(_AppConfig)
# appConfig.TTSPath = os.path.join(BASE_PATH, appConfig.TTSPath)#.replace("\\", "/")

@configSpec("speech")
class _SpeechConfig:
	ibmtts = ""
	outputDevice = ""
speechConfig = _SpeechConfig()
