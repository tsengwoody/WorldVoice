"""The exact text produced by code whose format strings were rewritten."""

import importlib
from types import SimpleNamespace

import pytest
from addon_loader import ADDON, load_source
from detector_harness import load_language_detection

MODELS = ADDON / "generics/speechSymbols/models.py"


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
	warnings = []
	stub_modules.module(
		"logHandler",
		log=SimpleNamespace(
			error=lambda *a, **k: None,
			debugWarning=lambda *a, **k: None,
			warning=lambda *a, **k: warnings.append(a),
		),
	)
	stub_modules.translation()
	module = load_source(None, "speech_symbol_models_under_test", MODELS, register=False)
	module.warnings = warnings
	return module


def test_speech_symbol_repr(models):
	symbol = models.SpeechSymbol("a", replacement="alpha")
	assert repr(symbol) == EXPECTED_REPR


def test_saved_symbol_lines(models, tmp_path):
	symbols = models.SpeechSymbols()
	escaped = models.SpeechSymbol(
		"\tx",
		replacement="tab",
		language="en",
		mode=models.SYMMOD_FORCE,
		displayName="Tab",
	)
	plain = models.SpeechSymbol("b", replacement="bravo")
	assert symbols._saveSymbol(escaped) == EXPECTED_ESCAPED
	assert symbols._saveSymbol(plain) == EXPECTED_PLAIN
	symbols.updateSymbol(escaped)
	symbols.updateSymbol(plain)
	path = tmp_path / "out.dic"
	symbols.save(str(path))
	assert path.read_bytes() == EXPECTED_FILE


def test_invalid_symbol_line_warning(models, tmp_path):
	path = tmp_path / "symbols.dic"
	path.write_text("# comment\nx\ty\ten\tbogus\n", encoding="utf-8")
	models.SpeechSymbols().load(str(path))
	assert models.warnings == [(f"Invalid line in file {path}: x\ty\ten\tbogus",)]


EXPECTED_REPR = (
	"SpeechSymbol(identifier='a', replacement='alpha', language=None, mode=None, displayName=None)"
)
EXPECTED_ESCAPED = "\\tx\ttab\ten\tforce\t# Tab"
EXPECTED_PLAIN = "b\tbravo"
EXPECTED_FILE = b"\xef\xbb\xbf\\tx\ttab\ten\tforce\t# Tab\r\nb\tbravo\r\n"


@pytest.fixture
def env(stub_modules, monkeypatch):
	return load_language_detection(stub_modules, monkeypatch)
