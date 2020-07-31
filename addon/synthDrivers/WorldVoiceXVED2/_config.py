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

VOCALIZER_CONFIG_FILENAME = "WorldVoiceXVED2.ini"

vocalizerConfig = None

_configSpec = u"""[voices]
[[__many__]]
variant = string(default=None)
rate = integer(default=130,min=50,max=400)
pitch = integer(default=95,min=50,max=200)
volume = integer(default=70,min=0,max=100)

[autoLanguageSwitching]
useUnicodeLanguageDetection = boolean(default=false)
ignoreNumbersInLanguageDetection = boolean(default=false)
ignorePunctuationInLanguageDetection = boolean(default=true)
latinCharactersLanguage = string(default=en)
CJKCharactersLanguage = string(default=ja)

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
