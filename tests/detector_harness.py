"""Load the real language detector, its settings, speechCommands and the pipeline's breaks under NVDA stubs."""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

from nvda_stubs import worldvoice_conf

WORLDVOICE = Path(__file__).resolve().parents[1] / "addon" / "synthDrivers" / "WorldVoice"
PACKAGE = "detector_test_worldvoice"


class LangChangeCommand:
	def __init__(self, lang):
		self.lang = lang


class BreakCommand:
	def __init__(self, time):
		self.time = time


class EndUtteranceCommand:
	"""NVDA's speech manager ends an utterance here."""


class ConfigProfileTriggerCommand:
	"""NVDA's speech manager ends an utterance before it."""


def load_language_detection(stub_modules, monkeypatch):
	for name in tuple(sys.modules):
		if name.startswith(PACKAGE + "."):
			monkeypatch.delitem(sys.modules, name)
	stub_modules.package(PACKAGE, WORLDVOICE)
	conf = worldvoice_conf(autoLanguageSwitching={"cjkCharactersLanguage": "zh"})
	state = SimpleNamespace(language="en_US")
	stub_modules.module("speech")
	stub_modules.module(
		"speech.commands",
		LangChangeCommand=LangChangeCommand,
		BreakCommand=BreakCommand,
		EndUtteranceCommand=EndUtteranceCommand,
		ConfigProfileTriggerCommand=ConfigProfileTriggerCommand,
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
	module = importlib.import_module(PACKAGE + ".languageDetection.detector")
	settings_module = importlib.import_module(PACKAGE + ".languageDetection.settings")
	return SimpleNamespace(
		module=module,
		conf=conf,
		state=state,
		settings_module=settings_module,
		settings=settings_module.DetectionSettingsService(lambda: conf),
		script_languages=importlib.import_module(PACKAGE + ".languageDetection.scriptLanguages"),
		WV=importlib.import_module(PACKAGE + ".speechCommands").WVLangChangeCommand,
		# The breaks the stages emit and the check the driver hands to the detector (spec
		# fix/leading-punctuation-language D13).
		breaks=importlib.import_module(PACKAGE + ".pipeline.breaks"),
		IndexCommand=sys.modules["speech.commands"].IndexCommand,
	)
