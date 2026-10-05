"""NVDA's processText runs without speech dictionaries while the pipeline applies them itself."""

import ast
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

WORLDVOICE = Path(__file__).resolve().parents[1] / "addon" / "synthDrivers" / "WorldVoice"
PACKAGE = "speech_dictionary_test_worldvoice"


@pytest.fixture
def env(stub_modules, monkeypatch):
	for name in tuple(sys.modules):
		if name.startswith(PACKAGE + "."):
			monkeypatch.delitem(sys.modules, name)
	stub_modules.package(PACKAGE, WORLDVOICE)
	stub_modules.package(PACKAGE + ".pipeline", WORLDVOICE / "pipeline")
	global_vars = stub_modules.module("globalVars", speechDictionaryProcessing=True)

	def process_text(text):
		return text, global_vars.speechDictionaryProcessing

	speech = stub_modules.module("speech", speech=SimpleNamespace(processText=process_text))
	module = importlib.import_module(PACKAGE + ".pipeline.speech_dictionary")
	return SimpleNamespace(module=module, speech=speech, globalVars=global_vars)


def test_install_bypasses_dictionaries_and_uninstall_restores(env):
	original = env.speech.speech.processText
	env.module.install()
	wrapped = env.speech.speech.processText
	env.module.install()
	assert env.speech.speech.processText is wrapped is not original
	assert wrapped("text") == ("text", False)
	assert env.globalVars.speechDictionaryProcessing is True
	env.module.uninstall()
	env.module.uninstall()
	assert env.speech.speech.processText is original


def test_one_module_level_state():
	tree = ast.parse((WORLDVOICE / "pipeline/speech_dictionary.py").read_text(encoding="utf-8"))
	names = set()
	for node in tree.body:
		if isinstance(node, ast.AnnAssign):
			names.add(node.target.id)
		elif isinstance(node, ast.Assign):
			names |= {target.id for target in node.targets}
	assert names == {"_restore"}
