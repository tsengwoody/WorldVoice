"""The exact text produced by code whose format strings were rewritten."""

import importlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from detector_harness import load_language_detection

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "addon/generics/speechSymbols/models.py"


def test_speech_command_reprs(env):
	commands = importlib.import_module(env.module.__name__.rsplit(".", 1)[0] + "._speechcommand")
	assert repr(commands.WVLangChangeCommand("zh")) == "WVLangChangeCommand ('zh')"
	assert repr(commands.WVLangChangeCommand(None)) == "WVLangChangeCommand (None)"
	marker = object.__new__(commands.WorldVoiceIndexCommand)
	marker.index = 7
	assert repr(marker) == "WorldVoiceIndexCommand(7)"


@pytest.fixture
def models(stub_modules, tmp_path):
	stub_modules.module("addonHandler", initTranslation=lambda: None)
	stub_modules.module("globalVars", appArgs=SimpleNamespace(configPath=str(tmp_path)))
	stub_modules.module("languageHandler", getAvailableLanguages=lambda: [("en", "English")])
	stub_modules.module("logHandler", log=SimpleNamespace(error=lambda *a, **k: None, debugWarning=lambda *a, **k: None))
	stub_modules.translation()
	spec = importlib.util.spec_from_file_location("speech_symbol_models_under_test", MODELS)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


def test_speech_symbol_repr(models):
	symbol = models.SpeechSymbol("a", replacement="alpha")
	assert repr(symbol) == EXPECTED_REPR


def test_saved_symbol_lines(models, tmp_path):
	symbols = models.SpeechSymbols()
	escaped = models.SpeechSymbol("\tx", replacement="tab", language="en", mode=models.SYMMOD_FORCE, displayName="Tab")
	plain = models.SpeechSymbol("b", replacement="bravo")
	assert symbols._saveSymbol(escaped) == EXPECTED_ESCAPED
	assert symbols._saveSymbol(plain) == EXPECTED_PLAIN
	symbols.updateSymbol(escaped)
	symbols.updateSymbol(plain)
	path = tmp_path / "out.dic"
	symbols.save(str(path))
	assert path.read_bytes() == EXPECTED_FILE


EXPECTED_REPR = "SpeechSymbol(identifier='a', replacement='alpha', language=None, mode=None, displayName=None)"
EXPECTED_ESCAPED = "\\tx\ttab\ten\tforce\t# Tab"
EXPECTED_PLAIN = "b\tbravo"
EXPECTED_FILE = b"\xef\xbb\xbf\\tx\ttab\ten\tforce\t# Tab\r\nb\tbravo\r\n"


@pytest.fixture
def env(stub_modules, monkeypatch):
	return load_language_detection(stub_modules, monkeypatch)
