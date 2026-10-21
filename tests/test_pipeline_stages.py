"""STAGES is the single order and log-key source, and stages read settings from their arguments."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pipeline_harness import ORDER, load_pipeline_module, punctuation_settings

SYNTH = Path(__file__).resolve().parents[1] / "addon/synthDrivers/WorldVoice/__init__.py"


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


def test_a_failing_log_write_neither_silences_the_stage_nor_floods_the_log(monkeypatch):
	# NVDA's Filter.apply keeps the input after an exception; the stage has read that generator
	# already, so a raised write would leave every later stage and the synth with nothing.
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	sys.modules["config"].conf["WorldVoice"]["log"] = {"enable": True, "speech_viewer": True}
	failing = [OSError("disk full")]

	def write(*args):
		if failing[0]:
			# A full disk, or a command whose repr cannot be encoded.
			raise failing[0]

	errors = []
	monkeypatch.setattr(module, "pl", SimpleNamespace(write=write))
	monkeypatch.setattr(module, "log", SimpleNamespace(error=lambda *a, **k: errors.append(a), debug=print))
	monkeypatch.setattr(module, "current_context", lambda: module.GENERIC_CONTEXT)
	stage = module.Stage("speech_viewer", lambda sequence, s, ctx: [item.upper() for item in sequence])
	assert stage.handler(iter(["a"])) == ["A"]
	assert stage.handler(iter(["b"])) == ["B"]
	assert len(errors) == 1, "every failed write of one outage was logged"
	failing[0] = None
	assert stage.handler(iter(["c"])) == ["C"]
	failing[0] = UnicodeEncodeError("utf-8", "\ud800", 0, 1, "surrogates not allowed")
	assert stage.handler(iter(["d"])) == ["D"]
	assert len(errors) == 2, "a new outage after a successful write was not logged"


def test_zero_number_wait_keeps_spaces(monkeypatch):
	settings = punctuation_settings(0)
	module, _ = load_pipeline_module(monkeypatch, settings)
	assert list(module.number_wait_factor([" 1 ", "  ", "2"], settings, module.GENERIC_CONTEXT)) == [
		" 1 ",
		"  ",
		"2",
	]


def test_positive_number_wait_breaks_between_numbers(monkeypatch):
	settings = punctuation_settings(0)
	settings.scaled_number_wait = lambda: 40
	module, _BreakCommand = load_pipeline_module(monkeypatch, settings)
	result = list(module.number_wait_factor([" 1 ", "  ", "2"], settings, module.GENERIC_CONTEXT))
	assert result[0] == "1" and result[2] == "2" and result[1].time == 40


def test_number_mode_reads_symbols_from_context(monkeypatch):
	settings = punctuation_settings(0)
	settings.number_mode = "number"
	module, _ = load_pipeline_module(monkeypatch, settings)
	symbols = SimpleNamespace(symbols={"1": SimpleNamespace(language="zh", replacement="一")})
	ctx = module.SpeechContext(
		supports_roles=True,
		language="zh",
		number_language="zh",
		speech_symbols=symbols,
	)

	def shape(sequence):
		return [item if isinstance(item, str) else (type(item).__name__, item.time) for item in sequence]

	no_wait = ("NumberBreakCommand", 0)
	assert shape(module.inject_number_mode(["11"], settings, ctx)) == ["一", no_wait, "一"]
	assert shape(module.inject_number_mode(["11"], settings, module.GENERIC_CONTEXT)) == ["1", no_wait, "1"]


def test_number_language_wraps_numbers_for_worldvoice_only(monkeypatch):
	settings = punctuation_settings(0)
	module, _ = load_pipeline_module(monkeypatch, settings)
	english = SimpleNamespace(name="A:en", language="en")
	ctx = module.SpeechContext(
		supports_roles=True,
		language="en",
		number_language="de",
		default_voice=english,
		voice_name_for_language={"en": "A:en", "de": "A:de"}.get,
	)
	result = list(module.inject_number_language(["a 1 b"], settings, ctx))
	assert [getattr(item, "lang", item) for item in result] == ["a ", "de", "1", "en", " b"]
	command = module.WVLangChangeCommand("de")
	assert list(module.inject_number_language([command, "x"], settings, module.GENERIC_CONTEXT)) == ["x"]


def test_stage_handlers_bind_like_nvda_filter_dispatch(monkeypatch):
	# NVDA's Filter.apply calls callWithSupportedKwargs, which binds the value
	# against inspect.signature(handler); that follows __wrapped__.
	import inspect

	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	for stage in module.STAGES:
		inspect.signature(stage.handler).bind(["text"])
		assert stage.handler.__name__ == stage.fn.__name__


def pause_settings(number_mode):
	settings = punctuation_settings(20)
	settings.number_mode = number_mode
	settings.scaled_number_wait = lambda: 10
	settings.scaled_group_wait = lambda: 30
	settings.group_size = 2
	return settings


def run_stages(module, sequence):
	for stage in module.STAGES:
		sequence = stage.handler(sequence)
	return list(sequence)


def break_types(sequence):
	return {(type(item).__name__, item.time) for item in sequence if not isinstance(item, str)}


# Scope "all" with another synth: NVDA's speechXml (OneCore) finds a command's converter by
# its class name, so a BreakCommand subclass would end the utterance there.
@pytest.mark.parametrize(
	("number_mode", "expected"),
	[
		("value", {("BreakCommand", 10), ("BreakCommand", 20)}),
		("number", {("BreakCommand", 10), ("BreakCommand", 20)}),
		("group", {("BreakCommand", 10), ("BreakCommand", 20), ("BreakCommand", 30)}),
	],
)
def test_other_synths_get_only_plain_breaks_from_the_stages(monkeypatch, number_mode, expected):
	module, _ = load_pipeline_module(monkeypatch, pause_settings(number_mode))
	monkeypatch.setattr(module, "current_context", lambda: module.GENERIC_CONTEXT)
	assert break_types(run_stages(module, ["共 12 34 個. 5678 and 3"])) == expected


@pytest.mark.parametrize(
	("number_mode", "expected"),
	[
		("value", {("NumberBreakCommand", 10), ("PunctuationBreakCommand", 20)}),
		("number", {("NumberBreakCommand", 10), ("PunctuationBreakCommand", 20)}),
		(
			"group",
			{("NumberBreakCommand", 10), ("PunctuationBreakCommand", 20), ("GroupNumberBreakCommand", 30)},
		),
	],
)
def test_worldvoice_keeps_the_break_subclasses_from_the_stages(monkeypatch, number_mode, expected):
	module, _ = load_pipeline_module(monkeypatch, pause_settings(number_mode))
	ctx = module.SpeechContext(supports_roles=True, language="zh", number_language="default")
	monkeypatch.setattr(module, "current_context", lambda: ctx)
	assert break_types(run_stages(module, ["共 12 34 個. 5678 and 3"])) == expected
