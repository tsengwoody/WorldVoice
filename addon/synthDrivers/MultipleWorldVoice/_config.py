#vocalizer_expressive/_config.py
#A part of the vocalizer driver for NVDA (Non Visual Desktop Access)
#Copyright (C) 2012 Rui Batista <ruiandrebatista@gmail.com>
#Copyright (C) 2012 Tiflotecnia, lda. <www.tiflotecnia.com>
#This file is covered by the GNU General Public License.
#See the file GPL.txt for more details.

from io import StringIO
import os.path
import configobj
from configobj.validate import Validator
import globalVars
from logHandler import log

VOCALIZER_CONFIG_FILENAME = "MultipleWorldVoice.ini"

vocalizerConfig = None

_configSpec = """
demo_expired_reported_time = float(default=0)
demo_license_reported_time = float(default=0)


[voices]
[[__many__]]
variant = string(default=None)

[autoLanguageSwitching]
useUnicodeLanguageDetection = boolean(default=false)
ignorePonctuationAndNumbersInLanguageDetection = boolean(default=false)
latinCharactersLanguage = string(default=en)

[[__many__]]
voice = string(default=None)
"""

def load():
	global vocalizerConfig
	if not vocalizerConfig:
		path = os.path.join(globalVars.appArgs.configPath, VOCALIZER_CONFIG_FILENAME)
		vocalizerConfig = configobj.ConfigObj(path, configspec=StringIO(_configSpec), encoding="utf-8")
		vocalizerConfig.newlines = "\r\n"
		vocalizerConfig.stringify = True
		val = Validator()
		ret = vocalizerConfig.validate(val, preserve_errors=True, copy=True)
		if ret != True:
			log.warning("Vocalizer configuration is invalid: %s", ret)

def save():
	global vocalizerConfig
	if not vocalizerConfig:
		raise RuntimeError("Vocalizer config is not loaded.")
	val = Validator()
	vocalizerConfig.validate(val, copy=True)
	vocalizerConfig.write()