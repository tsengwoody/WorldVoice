"""Load the real languageDetection package and _speechcommand under NVDA stubs."""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

WORLDVOICE = Path(__file__).resolve().parents[1] / "addon" / "synthDrivers" / "WorldVoice"
PACKAGE = "detector_test_worldvoice"


class LangChangeCommand:
	def __init__(self, lang):
		self.lang = lang


def load_language_detection(stub_modules, monkeypatch):
	for name in tuple(sys.modules):
		if name.startswith(PACKAGE + "."):
			monkeypatch.delitem(sys.modules, name)
	stub_modules.package(PACKAGE, WORLDVOICE)
	conf = {
		"WorldVoice": {
			"autoLanguageSwitching": {
				"ignoreNumbersInLanguageDetection": False,
				"latinCharactersLanguage": "en",
				"CJKCharactersLanguage": "zh",
				"arabicCharactersLanguage": "ar",
				"DetectLanguageTiming": "after",
			},
		},
	}
	state = SimpleNamespace(language="en_US")
	stub_modules.module("speech")
	stub_modules.module(
		"speech.commands",
		LangChangeCommand=LangChangeCommand,
		IndexCommand=type(
			"IndexCommand",
			(),
			{"__init__": lambda self, index: setattr(self, "index", index)},
		),
		SynthCommand=type("SynthCommand", (), {}),
		SynthParamCommand=type("SynthParamCommand", (), {}),
	)
	stub_modules.module("config", conf=conf)
	stub_modules.module("logHandler", log=SimpleNamespace(error=lambda *args, **kwargs: None))
	module = importlib.import_module(PACKAGE + ".languageDetection")
	settings_module = importlib.import_module(PACKAGE + ".languageDetection.settings")
	return SimpleNamespace(
		module=module,
		conf=conf,
		state=state,
		settings_module=settings_module,
		settings=settings_module.DetectionSettingsService(lambda: conf),
		WV=importlib.import_module(PACKAGE + "._speechcommand").WVLangChangeCommand,
	)
