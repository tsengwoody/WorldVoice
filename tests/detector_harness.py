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
	conf = {"WorldVoice": {"autoLanguageSwitching": {
		"ignoreNumbersInLanguageDetection": False,
		"latinCharactersLanguage": "en",
		"CJKCharactersLanguage": "zh",
		"arabicCharactersLanguage": "ar",
	}}}
	state = SimpleNamespace(language="en_US")
	stub_modules.module("speech")
	stub_modules.module(
		"speech.commands",
		LangChangeCommand=LangChangeCommand,
		IndexCommand=type("IndexCommand", (), {"__init__": lambda self, index: setattr(self, "index", index)}),
		SynthCommand=type("SynthCommand", (), {}),
		SynthParamCommand=type("SynthParamCommand", (), {}),
	)
	module = importlib.import_module(PACKAGE + ".languageDetection")
	return SimpleNamespace(module=module, conf=conf, state=state,
		WV=importlib.import_module(PACKAGE + "._speechcommand").WVLangChangeCommand)
