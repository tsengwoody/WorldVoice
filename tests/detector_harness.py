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


def master_detection(detector, speech_sequence):
	"""The oracle: detection as it was before fix/leading-punctuation-language, each character by
	today's per-character rule (detector.py:66-99 at 6ea5665), with the detector's own unchanged
	_language_for_character, settings and providers."""
	module = sys.modules[type(detector).__module__]
	settings = detector._settings.get()
	digits_by_script = detector._number_language() == module.FOLLOW
	default_lang = detector._language()
	cur_lang = tmp_lang = default_lang
	for command in speech_sequence:
		if isinstance(command, (module.LangChangeCommand, module.WVLangChangeCommand)):
			cur_lang = command.lang or default_lang
			tmp_lang = cur_lang
			yield command
		elif isinstance(command, str):
			buffer = []
			for character in command:
				target = detector._language_for_character(
					character,
					tmp_lang,
					cur_lang,
					settings,
					digits_by_script,
				)
				if module.primary_language(target) != module.primary_language(tmp_lang):
					if buffer:
						yield "".join(buffer)
						buffer = []
					yield module.WVLangChangeCommand(target)
					tmp_lang = target
				buffer.append(character)
			if buffer:
				yield "".join(buffer)
		else:
			yield command
