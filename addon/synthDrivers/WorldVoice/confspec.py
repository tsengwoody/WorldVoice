"""The [WorldVoice] section of NVDA's confspec.

The synth package calls installConfspec(config.conf) once when it is imported, which the global plugin
also does, so the section has its spec before any settings panel reads it.
"""

from .languageDetection.settings import DETECTION_CONFSPEC
from .pipeline.registry import LOG_SWITCHES
from .pipeline.settings import PIPELINE_CONFSPEC
from .voices.settingsRepository import VOICE_CONFSPEC


def installConfspec(conf):
	"""Give NVDA's conf the [WorldVoice] spec; each section's keys come from the module that owns it."""
	conf.spec["WorldVoice"] = {
		"autoLanguageSwitching": {
			**DETECTION_CONFSPEC,
			"keepMainLocaleVoiceConsistent": "boolean(default=true)",
			"keepMainLocaleParameterConsistent": "boolean(default=false)",
			"keepMainLocaleEngineConsistent": "boolean(default=true)",
		},
		"pipeline": dict(PIPELINE_CONFSPEC),
		"role": {},
		"engine": {
			"__many__": "boolean(default=false)",
		},
		"log": {
			"enable": "boolean(default=false)",
			**{key: "boolean(default=false)" for key in LOG_SWITCHES},
		},
		"voices": {"__many__": dict(VOICE_CONFSPEC)},
	}
