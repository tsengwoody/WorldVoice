"""Behavior of code rewritten for lint, pinned before the rewrite."""

import ast
import types

from addon_loader import WORLDVOICE, load_source


def _driver_methods(*names, trust_voice_language=True):
	path = WORLDVOICE / "__init__.py"
	tree = ast.parse(path.read_text(encoding="utf-8"))
	driver = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SynthDriver")
	driver.body = [node for node in driver.body if isinstance(node, ast.FunctionDef) and node.name in names]
	driver.bases = []
	driver.decorator_list = []
	env = {
		"_": lambda text: text,
		"config": types.SimpleNamespace(conf={"speech": {"trustVoiceLanguage": trust_voice_language}}),
		"StringParameterInfo": lambda id, name: types.SimpleNamespace(id=id, name=name),
	}
	exec(compile(ast.Module(body=[driver], type_ignores=[]), str(path), "exec"), env)
	return env["SynthDriver"]


def _spelling_synth(uwv, trust_voice_language):
	synth = _driver_methods("patchedSpeakSpelling", trust_voice_language=trust_voice_language)()
	synth.uwv = uwv
	calls = []
	synth._realSpellingFunc = lambda *args, **kwargs: calls.append((args, kwargs))
	synth._languageDetector = types.SimpleNamespace(
		process_for_spelling=lambda text, locale: [(text[:2], "en"), (text[2:], "zh")],
	)
	return synth, calls


def test_spelling_follows_detected_parts_when_the_voice_language_is_trusted():
	synth, calls = _spelling_synth(uwv=True, trust_voice_language=True)
	synth.patchedSpeakSpelling("ab中文", "fr", True, priority=2)
	assert calls == [(("ab", "en", True), {"priority": 2}), (("中文", "zh", True), {"priority": 2})]


def test_spelling_passes_through_otherwise():
	for uwv, trust in ((False, True), (True, False)):
		synth, calls = _spelling_synth(uwv=uwv, trust_voice_language=trust)
		synth.patchedSpeakSpelling("ab", "fr", False, priority=1)
		assert calls == [(("ab", "fr", False), {"priority": 1})]


def test_number_modes_are_a_plain_dict_in_order():
	modes = _driver_methods("_get_availableNummods")()._get_availableNummods()
	assert type(modes) is dict
	assert [(key, info.id, info.name) for key, info in modes.items()] == [
		("value", "value", "value"),
		("number", "number", "number"),
		("pair", "pair", "pair"),
	]


def _context_module(stub_modules, synth):
	stub_modules.module("synthDriverHandler", getSynth=lambda: synth)
	path = WORLDVOICE / "pipeline/context.py"
	return load_source(None, "pipeline_context_under_test", path, register=False)


def test_worldvoice_synth_returns_only_worldvoice(stub_modules):
	worldvoice = types.SimpleNamespace(name="WorldVoice", speech_context=lambda: "worldvoice context")
	module = _context_module(stub_modules, worldvoice)
	assert module.worldvoice_synth() is worldvoice
	assert module.current_context() == "worldvoice context"
	for other in (types.SimpleNamespace(name="eSpeak"), types.SimpleNamespace(), None):
		module = _context_module(stub_modules, other)
		assert module.worldvoice_synth() is None
		assert module.current_context() is module.GENERIC_CONTEXT
