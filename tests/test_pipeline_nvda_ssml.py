"""NVDA's SSML converter speaks the whole pipeline output another synth gets in scope "all".

OneCore builds SSML with NVDA's speechXml, which finds the converter of a command by its class
name and ends the utterance at a command it has none for. The test runs NVDA's own converter,
so it still holds when NVDA changes that dispatch.
"""

import ast
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
	[("value", [10, 20]), ("number", [10, 20]), ("group", [10, 20])],
)
def test_nvda_ssml_keeps_every_word_and_pause_of_the_scope_all_output(monkeypatch, number_mode, pauses):
	if not SPEECH_XML.is_file():
		pytest.skip("ref/nvda is not checked out")
	module, _ = load_pipeline_module(monkeypatch, pause_settings(number_mode))
	monkeypatch.setattr(module.registry, "current_context", lambda: module.GENERIC_CONTEXT)
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
	assert "say-as" not in xml
	assert warnings == []


def test_nvda_ssml_speaks_a_symbol_name_as_words_between_breaks(monkeypatch):
	# F1 option D: another synth gets the name as plain text, never in character mode.
	if not SPEECH_XML.is_file():
		pytest.skip("ref/nvda is not checked out")
	module, _ = load_pipeline_module(monkeypatch, pause_settings("group"))
	monkeypatch.setattr(module.registry, "current_context", lambda: module.GENERIC_CONTEXT)
	sequence = ["12.5"]
	for stage in module.STAGES:
		sequence = stage.handler(sequence)
	warnings = []
	speech_xml = load_speech_xml(monkeypatch, warnings)

	xml = speech_xml.SsmlConverter("zh_TW").convertToXml(list(sequence))

	assert re.search(r'12\s*<break time="10ms"/>\s*full stop en\s*<break time="10ms"/>\s*5', xml), xml
	assert "say-as" not in xml
	assert warnings == []


def test_nvda_break_command_has_no_slots():
	# Number-edge-pause spec D3: the plain break another synth gets for a number edge carries an
	# attribute of WorldVoice's own, which needs instances without __slots__.
	commands = REF / "nvda/source/speech/commands.py"
	if not commands.is_file():
		pytest.skip("ref/nvda is not checked out")
	classes = {
		node.name: node
		for node in ast.parse(commands.read_text(encoding="utf-8")).body
		if isinstance(node, ast.ClassDef)
	}
	pending, seen = ["BreakCommand"], []
	while pending:
		name = pending.pop()
		if name in seen or name not in classes:
			continue
		seen.append(name)
		node = classes[name]
		for statement in node.body:
			targets = (
				statement.targets
				if isinstance(statement, ast.Assign)
				else [getattr(statement, "target", None)]
			)
			assert not any(getattr(target, "id", None) == "__slots__" for target in targets), name
		pending.extend(base.id for base in node.bases if isinstance(base, ast.Name))
	assert seen == ["BreakCommand", "SynthCommand", "SpeechCommand"]


def test_nvda_ssml_keeps_every_word_of_a_number_between_edges(monkeypatch):
	# Number-edge-pause spec D3: the marked plain breaks around a number convert like any break.
	if not SPEECH_XML.is_file():
		pytest.skip("ref/nvda is not checked out")
	module, _ = load_pipeline_module(monkeypatch, pause_settings("number"))
	monkeypatch.setattr(module.registry, "current_context", lambda: module.GENERIC_CONTEXT)
	sequence = ["第3章"]
	for stage in module.STAGES:
		sequence = stage.handler(sequence)
	warnings = []
	speech_xml = load_speech_xml(monkeypatch, warnings)

	xml = speech_xml.SsmlConverter("zh_TW").convertToXml(list(sequence))

	assert re.sub(r"<[^>]*>|\s", "", xml) == "第3章"
	assert xml.count('<break time="10ms"/>') == 2
	assert warnings == []
