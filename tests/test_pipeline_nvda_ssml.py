"""NVDA's SSML converter speaks the whole pipeline output another synth gets in scope "all".

OneCore builds SSML with NVDA's speechXml, which finds the converter of a command by its class
name and ends the utterance at a command it has none for. The test runs NVDA's own converter,
so it still holds when NVDA changes that dispatch.
"""

import re
import sys
from types import SimpleNamespace

import pytest
from addon_loader import REF, load_source
from nvda_stubs import StubModules
from pipeline_harness import load_pipeline_module, punctuation_settings

SPEECH_XML = REF / "nvda/source/speechXml.py"
TEXT = "共 12 34 個. 5678 and 3"


def pause_settings(number_mode):
	settings = punctuation_settings(20)
	settings.number_mode = number_mode
	settings.scaled_number_wait = lambda: 10
	settings.scaled_group_wait = lambda: 30
	settings.group_size = 2
	return settings


def load_speech_xml(monkeypatch, warnings):
	"""NVDA's speechXml over the speech.commands stub the pipeline was loaded with."""
	stubs = StubModules(monkeypatch)
	commands = sys.modules["speech.commands"]
	for name in ["CallbackCommand", "CharacterModeCommand", "PitchCommand", "RateCommand", "VolumeCommand"]:
		monkeypatch.setattr(commands, name, type(name, (commands.SpeechCommand,), {}), raising=False)
	stubs.module("speech.types", SpeechSequence=list)
	stubs.module("textUtils", REPLACEMENT_CHAR="�")
	monkeypatch.setattr(
		sys.modules["logHandler"],
		"log",
		SimpleNamespace(debugWarning=warnings.append, error=warnings.append),
	)
	return load_source(monkeypatch, "speechXml", SPEECH_XML)


@pytest.mark.parametrize(
	("number_mode", "pauses"),
	[("value", [10, 20]), ("number", [10, 20]), ("group", [10, 20, 30])],
)
def test_nvda_ssml_keeps_every_word_and_pause_of_the_scope_all_output(monkeypatch, number_mode, pauses):
	if not SPEECH_XML.is_file():
		pytest.skip("ref/nvda is not checked out")
	module, _ = load_pipeline_module(monkeypatch, pause_settings(number_mode))
	monkeypatch.setattr(module, "current_context", lambda: module.GENERIC_CONTEXT)
	sequence = [TEXT]
	for stage in module.STAGES:
		sequence = stage.handler(sequence)
	warnings = []
	speech_xml = load_speech_xml(monkeypatch, warnings)

	xml = speech_xml.SsmlConverter("zh_TW").convertToXml(list(sequence))

	spoken = re.sub(r"<[^>]*>|\s", "", xml)
	assert spoken == "共1234個.5678and3"
	for pause in pauses:
		assert f'<break time="{pause}ms"/>' in xml
	assert warnings == []
