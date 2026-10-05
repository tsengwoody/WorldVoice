"""WorldVoice's language command must survive NVDA's language-switching filters."""

import importlib.util
from pathlib import Path
import sys

import pytest

from nvda_stubs import StubModules

ADDON = Path(__file__).resolve().parents[1] / "addon"
SPEECH_COMMAND = ADDON / "synthDrivers/WorldVoice/_speechcommand.py"
INSTALL_TASKS = ADDON / "installTasks.py"


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
	spec = importlib.util.spec_from_file_location("speech_command_contract_under_test", SPEECH_COMMAND)
	module = importlib.util.module_from_spec(spec)
	monkeypatch.setitem(sys.modules, spec.name, module)
	spec.loader.exec_module(module)
	return module.WVLangChangeCommand


def test_language_command_is_a_parameter_command_but_not_nvdas_language_change(command):
	assert issubclass(command, SynthParamCommand)
	assert not issubclass(command, LangChangeCommand)


@pytest.mark.parametrize("lang,default", [(None, True), ("", True), ("zh", False)])
def test_switching_back_to_the_default_language_is_a_default_parameter(command, lang, default):
	assert command(lang).isDefault is default


def test_docstring_says_which_nvda_checks_the_command_avoids(command):
	doc = command.__doc__
	for reference in ("speech/speech.py", "speech/manager.py", "isDefault", "installTasks"):
		assert reference in doc, reference


def test_install_task_says_why_it_turns_nvda_language_switching_off():
	lines = INSTALL_TASKS.read_text(encoding="utf-8").splitlines()
	(index,) = [i for i, line in enumerate(lines) if 'config.conf["speech"]["autoLanguageSwitching"] = False' in line]
	comment = []
	for line in reversed(lines[:index]):
		stripped = line.strip()
		if not stripped.startswith("#"):
			break
		comment.append(stripped)
	assert "WVLangChangeCommand" in " ".join(comment)
