"""STAGES is the single order and log-key source, and stages read settings from their arguments."""

import ast
from pathlib import Path
import sys
from types import SimpleNamespace

from test_pipeline_punctuation_pause import load_pipeline_module, punctuation_settings


PIPELINE = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice/pipeline/__init__.py"
SYNTH = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice/__init__.py"

ORDER = [
	"apply_speech_dictionaries", "ignore_comma_between_number", "number_language", "number_mode",
	"chinesespace_wait_factor", "item_wait_factor", "punctuation_wait_factor", "number_wait_factor",
	"speech_viewer",
]


class OrderedFilter:
	def __init__(self):
		self.handlers = []

	def register(self, handler):
		if handler not in self.handlers:
			self.handlers.append(handler)

	def unregister(self, handler):
		if handler in self.handlers:
			self.handlers.remove(handler)

	def moveToEnd(self, handler, last=False):
		if handler not in self.handlers:
			return False
		self.handlers.remove(handler)
		if last:
			self.handlers.append(handler)
		else:
			self.handlers.insert(0, handler)
		return True


def test_stages_order_and_log_keys(monkeypatch):
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	assert [stage.log_key for stage in module.STAGES] == ORDER


def test_register_puts_stages_first_in_order_and_unregister_removes_them(monkeypatch):
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	fake = OrderedFilter()
	other = lambda sequence: sequence
	fake.register(other)
	monkeypatch.setattr(module, "filter_speechSequence", fake)
	installs = []
	monkeypatch.setattr(module.speech_dictionary, "install", lambda: installs.append("install"))
	monkeypatch.setattr(module.speech_dictionary, "uninstall", lambda: installs.append("uninstall"))

	module.register_stages()
	assert fake.handlers == [stage.handler for stage in module.STAGES] + [other]
	module.order_move_to_end_register()
	assert fake.handlers == [other] + [stage.handler for stage in module.STAGES]
	module.unregister_stages()
	assert fake.handlers == [other]
	assert installs == ["install", "uninstall"]


def test_handler_passes_effective_settings_and_context(monkeypatch):
	settings = punctuation_settings(0)
	module, _ = load_pipeline_module(monkeypatch, settings)
	seen = []
	monkeypatch.setattr(module, "current_context", lambda: module.GENERIC_CONTEXT)
	stage = module.Stage("speech_viewer", lambda sequence, s, ctx: seen.append((s, ctx)) or list(sequence))
	assert stage.handler(["a"]) == ["a"]
	assert seen == [(settings, module.GENERIC_CONTEXT)]


def test_handler_logs_before_and_after_when_enabled(monkeypatch):
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	sys.modules["config"].conf["WorldVoice"]["log"] = {"enable": True, "speech_viewer": True}
	writes = []
	monkeypatch.setattr(module, "pl", SimpleNamespace(write=lambda *args: writes.append(args[1:3])))
	monkeypatch.setattr(module, "current_context", lambda: module.GENERIC_CONTEXT)
	stage = module.Stage("speech_viewer", lambda sequence, s, ctx: [item.upper() for item in sequence])
	assert stage.handler(["a"]) == ["A"]
	assert writes == [("speech_viewer", "before"), ("speech_viewer", "after")]


def test_zero_number_wait_keeps_spaces(monkeypatch):
	settings = punctuation_settings(0)
	module, _ = load_pipeline_module(monkeypatch, settings)
	assert list(module.number_wait_factor([" 1 ", "  ", "2"], settings, module.GENERIC_CONTEXT)) == [" 1 ", "  ", "2"]


def test_positive_number_wait_breaks_between_numbers(monkeypatch):
	settings = punctuation_settings(0)
	settings.scaled_number_wait = lambda: 40
	module, BreakCommand = load_pipeline_module(monkeypatch, settings)
	result = list(module.number_wait_factor([" 1 ", "  ", "2"], settings, module.GENERIC_CONTEXT))
	assert result[0] == "1" and result[2] == "2" and result[1].time == 40


def test_number_mode_reads_symbols_from_context(monkeypatch):
	settings = punctuation_settings(0)
	settings.number_mode = "number"
	module, _ = load_pipeline_module(monkeypatch, settings)
	symbols = SimpleNamespace(symbols={"1": SimpleNamespace(language="zh", replacement="一")})
	ctx = module.SpeechContext(supports_roles=True, language="zh", number_language="zh", speech_symbols=symbols)
	assert list(module.inject_number_mode(["11"], settings, ctx)) == ["一 一"]
	assert list(module.inject_number_mode(["11"], settings, module.GENERIC_CONTEXT)) == ["1 1"]


def test_number_language_wraps_numbers_for_worldvoice_only(monkeypatch):
	settings = punctuation_settings(0)
	module, _ = load_pipeline_module(monkeypatch, settings)
	english, german = object(), object()
	ctx = module.SpeechContext(
		supports_roles=True, language="en", number_language="de", default_voice=english,
		voice_for_language=lambda language: {"en": english, "de": german}.get(language),
	)
	result = list(module.inject_number_language(["a 1 b"], settings, ctx))
	assert [getattr(item, "lang", item) for item in result] == ["a ", "de", "1", "en", " b"]
	command = module.WVLangChangeCommand("de")
	assert list(module.inject_number_language([command, "x"], settings, module.GENERIC_CONTEXT)) == ["x"]


def test_only_the_order_log_debug_tool_asks_for_the_synth():
	tree = ast.parse(PIPELINE.read_text(encoding="utf-8"))
	users = {
		node.name for node in tree.body
		if isinstance(node, ast.FunctionDef)
		and any(isinstance(inner, ast.Name) and inner.id == "getSynth" for inner in ast.walk(node))
	}
	assert users == {"with_order_log"}
