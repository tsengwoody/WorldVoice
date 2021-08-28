from io import StringIO
import os.path
import configobj
from configobj.validate import Validator
import config
import globalVars
from logHandler import log

WORLDVOICE_CONFIG_FILENAME = "WorldVoiceXVED2.ini"

vocalizerConfig = None

_configSpec = """# WorldVoice spec
[WorldVoice]
	[[voices]]
		[[[__many__]]]
			variant = string(default=None)
			rate = integer(default=50,min=0,max=100)
			pitch = integer(default=50,min=0,max=100)
			volume = integer(default=50,min=0,max=100)

	[[autoLanguageSwitching]]
		numberDotReplacement = string(default=".")
		useUnicodeLanguageDetection = boolean(default=true)
		ignoreNumbersInLanguageDetection = boolean(default=false)
		ignorePunctuationInLanguageDetection = boolean(default=false)
		latinCharactersLanguage = string(default=en)
		CJKCharactersLanguage = string(default=None)
		DetectLanguageTiming = string(default=after)
		KeepMainLocaleVoiceConsistent = boolean(default=true)
		KeepMainLocaleParameterConsistent = boolean(default=false)

		[[[__many__]]]
			voice = string(default=None)
"""

config.conf.spec["WorldVoice"] = {
	"autoLanguageSwitching" :{
		"numberDotReplacement": "string(default='.')",
		"useUnicodeLanguageDetection": "boolean(default=true)",
		"ignoreNumbersInLanguageDetection": "boolean(default=false)",
		"ignorePunctuationInLanguageDetection": "boolean(default=false)",
		"latinCharactersLanguage": "string(default=en)",
		"CJKCharactersLanguage": "string(default=ja)",
		"DetectLanguageTiming": "string(default=after)",
		"KeepMainLocaleVoiceConsistent": "boolean(default=true)",
		"KeepMainLocaleParameterConsistent": "boolean(default=false)",
	},
	"voices": {
		"__many__": {
			"variant": "string(default=None)",
			"rate": "integer(default=50,min=0,max=100)",
			"pitch": "integer(default=50,min=0,max=100)",
			"volume": "integer(default=50,min=0,max=100)",
		}
	}
}
