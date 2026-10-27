"""The exact text produced by code whose format strings were rewritten."""

import importlib

import pytest
from detector_harness import PACKAGE, load_language_detection


def test_speech_command_reprs(env):
	commands = importlib.import_module(PACKAGE + ".speechCommands")
	assert repr(commands.WVLangChangeCommand("zh")) == "WVLangChangeCommand ('zh')"
	assert repr(commands.WVLangChangeCommand(None)) == "WVLangChangeCommand (None)"
	marker = object.__new__(commands.WorldVoiceIndexCommand)
	marker.index = 7
	assert repr(marker) == "WorldVoiceIndexCommand(7)"


@pytest.fixture
def env(stub_modules, monkeypatch):
	return load_language_detection(stub_modules, monkeypatch)
