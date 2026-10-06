"""WorldVoice's language command must survive NVDA's language-switching filters."""

import pytest
from addon_loader import ADDON, load_source
from nvda_stubs import StubModules

SPEECH_COMMAND = ADDON / "synthDrivers/WorldVoice/_speechcommand.py"


class SynthCommand:
	pass


class SynthParamCommand(SynthCommand):
	pass


class LangChangeCommand(SynthParamCommand):
	"""Shaped like NVDA's: a language change is a synth parameter command."""


class IndexCommand(SynthCommand):
	def __init__(self, index):
		self.index = index


@pytest.fixture
def command(monkeypatch):
	stubs = StubModules(monkeypatch)
	stubs.module("speech")
	stubs.module(
		"speech.commands",
		SynthCommand=SynthCommand,
		SynthParamCommand=SynthParamCommand,
		LangChangeCommand=LangChangeCommand,
		IndexCommand=IndexCommand,
	)
	return load_source(monkeypatch, "speech_command_contract_under_test", SPEECH_COMMAND).WVLangChangeCommand


def test_language_command_is_a_parameter_command_but_not_nvdas_language_change(command):
	assert issubclass(command, SynthParamCommand)
	assert not issubclass(command, LangChangeCommand)


@pytest.mark.parametrize("lang,default", [(None, True), ("", True), ("zh", False)])
def test_switching_back_to_the_default_language_is_a_default_parameter(command, lang, default):
	assert command(lang).isDefault is default
