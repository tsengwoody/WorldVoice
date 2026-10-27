"""STAGES is the single order and log-key source, and stages read settings from their arguments."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from nvda_stubs import worldvoice_conf
from pipeline_harness import LOG_SWITCH_ORDER, ORDER, load_pipeline_module, punctuation_settings

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


def test_log_switches_list_each_label_once_in_stage_order(monkeypatch):
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	assert module.LOG_SWITCHES == tuple(LOG_SWITCH_ORDER)


def test_number_mode_switch_logs_both_number_mode_stages(monkeypatch):
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	sys.modules["config"].conf["WorldVoice"]["log"] = {
		"enable": True,
		**dict.fromkeys(LOG_SWITCH_ORDER, False),
		"number_mode": True,
	}
	writes = []
	monkeypatch.setattr(module.registry, "pl", SimpleNamespace(write=lambda *args: writes.append(args[1:3])))
	monkeypatch.setattr(module.registry, "current_context", lambda: module.GENERIC_CONTEXT)
	sequence = ["12,345"]
	for stage in module.STAGES:
		sequence = stage.handler(sequence)
	assert writes == [("number_mode", "before"), ("number_mode", "after")] * 2


@pytest.mark.parametrize(
	"on",
	[(), ("number_language",), ("number_mode",), ("number_language", "number_mode")],
	ids=["none", "other-only", "own-only", "both"],
)
def test_a_stage_logs_under_each_of_its_switches(monkeypatch, on):
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	sys.modules["config"].conf["WorldVoice"]["log"] = {
		"enable": True,
		**dict.fromkeys(LOG_SWITCH_ORDER, False),
		**dict.fromkeys(on, True),
	}
	writes = []
	monkeypatch.setattr(module.registry, "pl", SimpleNamespace(write=lambda *args: writes.append(args[1:3])))
	monkeypatch.setattr(module.registry, "current_context", lambda: module.GENERIC_CONTEXT)
	stage = module.Stage(
		"number_mode",
		lambda sequence, s, ctx: list(sequence),
		also_logged_by=("number_language",),
	)
	assert stage.handler(["a"]) == ["a"]
	assert writes == ([("number_mode", "before"), ("number_mode", "after")] if on else [])


def test_log_switches_list_each_key_once_in_stage_order(monkeypatch):
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	f = lambda sequence, s, ctx: sequence
	Stage = module.Stage
	stages = (
		Stage("a", f),
		Stage("b", f, log_switch=False, also_logged_by=("x",)),
		Stage("c", f, also_logged_by=("a", "d")),
		Stage("c", f),
	)
	assert module._log_switches(stages) == ("a", "d", "c")


def test_the_log_confspec_has_every_log_switch(monkeypatch):
	# tests/nvda_stubs.py derives the log confspec from STAGES; it must list every switch.
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	assert set(module.LOG_SWITCHES) <= set(worldvoice_conf()["WorldVoice"]["log"])


@pytest.mark.parametrize(
	("on", "pairs"),
	[(("number_language",), 1), (("number_language", "number_mode"), 2)],
	ids=["language-only", "both"],
)
def test_the_number_language_switch_logs_the_number_stage(monkeypatch, on, pairs):
	# Number-edge-pause spec D4: one number stage, logged by either number switch, labelled "number_mode".
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	sys.modules["config"].conf["WorldVoice"]["log"] = {
		"enable": True,
		**dict.fromkeys(LOG_SWITCH_ORDER, False),
		**dict.fromkeys(on, True),
	}
	writes = []
	monkeypatch.setattr(module.registry, "pl", SimpleNamespace(write=lambda *args: writes.append(args[1:3])))
	monkeypatch.setattr(module.registry, "current_context", lambda: module.GENERIC_CONTEXT)
	sequence = ["12,345"]
	for stage in module.STAGES:
		sequence = stage.handler(sequence)
	assert writes == [("number_mode", "before"), ("number_mode", "after")] * pairs


def test_register_puts_stages_first_in_order_and_unregister_removes_them(monkeypatch):
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	fake = OrderedFilter()
	other = lambda sequence: sequence
	fake.register(other)
	monkeypatch.setattr(module.registry, "filter_speechSequence", fake)
	installs = []
	monkeypatch.setattr(module.speechDictionary, "install", lambda: installs.append("install"))
	monkeypatch.setattr(module.speechDictionary, "uninstall", lambda: installs.append("uninstall"))

	module.register_stages()
	assert fake.handlers == [stage.handler for stage in module.STAGES] + [other]
	module.unregister_stages()
	assert fake.handlers == [other]
	assert installs == ["install", "uninstall"]


def test_handler_passes_effective_settings_and_context(monkeypatch):
	settings = punctuation_settings(0)
	module, _ = load_pipeline_module(monkeypatch, settings)
	seen = []
	monkeypatch.setattr(module.registry, "current_context", lambda: module.GENERIC_CONTEXT)
	stage = module.Stage("speech_viewer", lambda sequence, s, ctx: seen.append((s, ctx)) or list(sequence))
	assert stage.handler(["a"]) == ["a"]
	assert seen == [(settings, module.GENERIC_CONTEXT)]


def test_handler_asks_for_the_settings_of_the_contexts_synth(monkeypatch):
	settings = punctuation_settings(0)
	module, _ = load_pipeline_module(monkeypatch, settings)
	asked = []
	monkeypatch.setattr(
		module.registry,
		"pipeline_settings",
		SimpleNamespace(effective=lambda roles: asked.append(roles) or settings),
	)
	stage = module.Stage("speech_viewer", lambda sequence, s, ctx: list(sequence))
	roles = module.SpeechContext(supports_roles=True, language="en", number_language="default")
	for ctx in [module.GENERIC_CONTEXT, roles]:
		monkeypatch.setattr(module.registry, "current_context", lambda ctx=ctx: ctx)
		stage.handler(["a"])
	assert asked == [False, True]


def test_handler_logs_before_and_after_when_enabled(monkeypatch):
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	sys.modules["config"].conf["WorldVoice"]["log"] = {"enable": True, "speech_viewer": True}
	writes = []
	monkeypatch.setattr(module.registry, "pl", SimpleNamespace(write=lambda *args: writes.append(args[1:3])))
	monkeypatch.setattr(module.registry, "current_context", lambda: module.GENERIC_CONTEXT)
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
	monkeypatch.setattr(module.registry, "pl", SimpleNamespace(write=write))
	monkeypatch.setattr(
		module.registry,
		"log",
		SimpleNamespace(error=lambda *a, **k: errors.append(a), debug=print),
	)
	monkeypatch.setattr(module.registry, "current_context", lambda: module.GENERIC_CONTEXT)
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


@pytest.mark.parametrize("numlan", ["default", "main", "en"])
def test_other_synths_get_no_worldvoice_language_commands(monkeypatch, numlan):
	settings = punctuation_settings(0)
	module, _ = load_pipeline_module(monkeypatch, settings)
	ctx = module.SpeechContext(supports_roles=False, language=None, number_language=numlan)
	sequence = ["中12", "abc 1 2"]
	for stage in module.STAGES:
		sequence = list(stage.fn(sequence, settings, ctx))
	assert not any(isinstance(item, module.WVLangChangeCommand) for item in sequence)


def test_number_language_wraps_numbers_for_worldvoice_only(monkeypatch):
	settings = punctuation_settings(0)
	module, _ = load_pipeline_module(monkeypatch, settings)
	english = SimpleNamespace(name="A:en", language="en")
	ctx = module.SpeechContext(
		supports_roles=True,
		language="en",
		number_language="de",
		default_voice_name=english.name,
		default_voice_language=english.language,
		voice_name_for_language={"en": "A:en", "de": "A:de"}.get,
	)
	result = list(module.inject_numbers(["a 1 b"], settings, ctx))
	assert [getattr(item, "lang", item) for item in result] == ["a ", "de", "1", "en", " b"]
	command = module.WVLangChangeCommand("de")
	assert list(module.inject_numbers([command, "x"], settings, module.GENERIC_CONTEXT)) == ["x"]


def test_number_language_and_number_wait_pause_between_numbers(monkeypatch):
	settings = punctuation_settings(0)
	settings.scaled_number_wait = lambda: 10
	module, _ = load_pipeline_module(monkeypatch, settings)
	ctx = module.SpeechContext(
		supports_roles=True,
		language="zh",
		number_language="en",
		default_voice_name="Z",
		default_voice_language="zh",
		voice_name_for_language={"zh": "Z", "en": "E"}.get,
	)
	monkeypatch.setattr(module.registry, "current_context", lambda: ctx)
	sequence = ["1 2"]
	for stage in module.STAGES:
		sequence = stage.handler(sequence)
	assert [
		getattr(item, "lang", item) if not isinstance(item, module.NumberBreakCommand) else ("NB", item.time)
		for item in sequence
	] == ["en", "1", "zh", ("NB", 10), "en", "2", "zh"]


def test_thousands_removal_runs_before_number_language(monkeypatch):
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	ctx = module.SpeechContext(
		supports_roles=True,
		language="zh",
		number_language="en",
		default_voice_name="Z",
		default_voice_language="zh",
		voice_name_for_language={"zh": "Z", "en": "E"}.get,
	)
	monkeypatch.setattr(module.registry, "current_context", lambda: ctx)
	sequence = ["12,345,678"]
	for stage in module.STAGES:
		sequence = stage.handler(sequence)
	assert [getattr(item, "lang", item) for item in sequence] == ["en", "12345678", "zh"]


@pytest.mark.parametrize("space", ["\u00a0", "\u202f", "\u2007"])
def test_number_language_pauses_at_a_no_break_space(monkeypatch, space):
	# Decided by the user (2026-10-22): "10 000" with a no-break space is two numbers, with or
	# without a number language.
	settings = punctuation_settings(0)
	settings.scaled_number_wait = lambda: 10
	module, _ = load_pipeline_module(monkeypatch, settings)
	ctx = module.SpeechContext(
		supports_roles=True,
		language="zh",
		number_language="en",
		default_voice_name="Z",
		default_voice_language="zh",
		voice_name_for_language={"zh": "Z", "en": "E"}.get,
	)
	monkeypatch.setattr(module.registry, "current_context", lambda: ctx)
	sequence = [f"10{space}000"]
	for stage in module.STAGES:
		sequence = stage.handler(sequence)
	assert [
		("NB", item.time) if isinstance(item, module.NumberBreakCommand) else getattr(item, "lang", item)
		for item in sequence
	] == ["en", "10", "zh", ("NB", 10), "en", "000", "zh"]


def test_symbol_names_without_a_number_language_voice_use_the_default_voice_locale(monkeypatch):
	# No voice for the number language: get_voice_name_for_language gives the default voice
	# (voices/manager.py:295-299), so deduplication drops the wrapper and the name comes from the
	# default voice's locale (decided by the user, 2026-10-22, Q1 A; replaces the number-unify F2
	# expectation of the number language's table).
	settings = punctuation_settings(0)
	settings.number_mode = "number"
	module, _ = load_pipeline_module(monkeypatch, settings)
	ctx = module.SpeechContext(
		supports_roles=True,
		language="zh_TW",
		number_language="en",
		default_voice_name="Z",
		default_voice_language="zh_TW",
		voice_name_for_language=lambda language: "Z",
		voice_locale_for_language=lambda language: "zh_TW",
	)
	monkeypatch.setattr(module.registry, "current_context", lambda: ctx)
	sequence = ["2\u00d73"]
	for stage in module.STAGES:
		sequence = stage.handler(sequence)
	assert [item for item in sequence if isinstance(item, str)] == ["2", "multiplication sign zh tw", "3"]
	assert not any(hasattr(item, "lang") for item in sequence)


def test_stage_handlers_bind_like_nvda_filter_dispatch(monkeypatch):
	# NVDA's Filter.apply calls callWithSupportedKwargs, which binds the value
	# against inspect.signature(handler); that follows __wrapped__.
	import inspect

	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	for stage in module.STAGES:
		inspect.signature(stage.handler).bind(["text"])
		assert stage.handler.__name__ == stage.fn.__name__
		assert stage.handler.__doc__ == stage.fn.__doc__


def pause_settings(number_mode):
	settings = punctuation_settings(20)
	settings.number_mode = number_mode
	settings.scaled_number_wait = lambda: 10
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
		("group", {("BreakCommand", 10), ("BreakCommand", 20)}),
	],
)
def test_other_synths_get_only_plain_breaks_from_the_stages(monkeypatch, number_mode, expected):
	module, _ = load_pipeline_module(monkeypatch, pause_settings(number_mode))
	monkeypatch.setattr(module.registry, "current_context", lambda: module.GENERIC_CONTEXT)
	assert break_types(run_stages(module, ["共 12 34 個. 5678 and 3"])) == expected


@pytest.mark.parametrize(
	("number_mode", "expected"),
	[
		("value", {("NumberBreakCommand", 10), ("PunctuationBreakCommand", 20)}),
		(
			"number",
			{("NumberBreakCommand", 10), ("NumberEdgeBreakCommand", 10), ("PunctuationBreakCommand", 20)},
		),
		(
			"group",
			{("NumberBreakCommand", 10), ("NumberEdgeBreakCommand", 10), ("PunctuationBreakCommand", 20)},
		),
	],
)
def test_worldvoice_keeps_the_break_subclasses_from_the_stages(monkeypatch, number_mode, expected):
	module, _ = load_pipeline_module(monkeypatch, pause_settings(number_mode))
	ctx = module.SpeechContext(supports_roles=True, language="zh", number_language="default")
	monkeypatch.setattr(module.registry, "current_context", lambda: ctx)
	assert break_types(run_stages(module, ["共 12 34 個. 5678 and 3"])) == expected


# Numbers wrapped for detection (phase 35 spec §4.4, batch 1 review C1).


class Marker:
	"""A speech command no stage knows, such as NVDA's IndexCommand."""


def number_context(module, numlan, *, roles=True):
	return module.SpeechContext(
		supports_roles=roles,
		language="en",
		number_language=numlan,
		default_voice_name="A:en",
		default_voice_language="en",
		voice_name_for_language={"en": "A:en", "zh_TW": "B:zh"}.get,
	)


def wrapped_shape(module, sequence):
	result = []
	for item in sequence:
		if isinstance(item, module.NumberBreakCommand):
			result.append("NB")
		elif hasattr(item, "lang"):
			result.append(("lang", item.lang))
		else:
			result.append(item)
	return result


def wrap(monkeypatch, sequence, numlan):
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	items = sequence(module) if callable(sequence) else sequence
	return module, list(module.wrap_numbers_for_detection(items, number_context(module, numlan)))


EN = ("lang", "en")


@pytest.mark.parametrize(
	("sequence", "expected"),
	[
		(lambda module: ["a 12,5 b"], ["a ", EN, "12,5", EN, " b"]),
		(
			lambda module: ["1", module.NumberBreakCommand(0), "2"],
			[EN, "1", EN, "NB", EN, "2", EN],
		),
		(
			lambda module: ["123", module.NumberBreakCommand(0), "45"],
			[EN, "123", EN, "NB", EN, "45", EN],
		),
	],
	ids=["value", "number", "group"],
)
def test_wrap_numbers_for_detection_wraps_every_match(monkeypatch, sequence, expected):
	module, result = wrap(monkeypatch, sequence, "main")
	assert wrapped_shape(module, result) == expected


def test_wrap_numbers_for_detection_uses_the_locale(monkeypatch):
	module, result = wrap(monkeypatch, ["a 1"], "zh_TW")
	assert wrapped_shape(module, result) == ["a ", ("lang", "zh_TW"), "1", EN]


def test_wrap_numbers_for_detection_tracks_language_commands(monkeypatch):
	def sequence(module):
		nvda = sys.modules["speech.commands"].LangChangeCommand
		return [nvda("de"), "1", nvda(None), "2", module.WVLangChangeCommand("ja"), "3"]

	module, result = wrap(monkeypatch, sequence, "main")
	de, ja = ("lang", "de"), ("lang", "ja")
	assert wrapped_shape(module, result) == [de, de, "1", de, ("lang", None), EN, "2", EN, ja, ja, "3", ja]


def test_wrap_numbers_for_detection_leaves_a_sign_after_a_word_with_it(monkeypatch):
	# Decided by the user (2026-10-23, U1).
	module, result = wrap(monkeypatch, ["x-1 (-2)"], "main")
	assert wrapped_shape(module, result) == ["x-", EN, "1", EN, " (", EN, "-2", EN, ")"]


def test_wrap_numbers_for_detection_drops_empty_texts(monkeypatch):
	module, result = wrap(monkeypatch, ["", "12", " "], "main")
	assert wrapped_shape(module, result) == [EN, "12", EN, " "]


def detect_numbers(monkeypatch, sequence, numlan, *, roles=True, detect=None):
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))
	items = sequence(module) if callable(sequence) else sequence
	ctx = number_context(module, numlan, roles=roles)
	result = module.detect_with_number_language(items, detect or (lambda seq: seq), ctx)
	return module, items, result


@pytest.mark.parametrize(
	("numlan", "roles"),
	[("default", True), ("en", False)],
	ids=["follow", "other-synth"],
)
def test_detection_wraps_nothing_for_follow_or_another_synth(monkeypatch, numlan, roles):
	_module, items, result = detect_numbers(
		monkeypatch,
		lambda module: ["a1", module.WVLangChangeCommand("zh"), "2"],
		numlan,
		roles=roles,
	)
	assert len(result) == len(items) and all(after is before for after, before in zip(result, items))


def test_detection_sees_the_wrapped_numbers(monkeypatch):
	seen = []
	module, _items, _result = detect_numbers(
		monkeypatch,
		["a 1"],
		"main",
		detect=lambda seq: seen.extend(seq) or seq,
	)
	assert wrapped_shape(module, seen) == ["a ", EN, "1", EN]


@pytest.mark.parametrize(
	("sequence", "expected"),
	[
		# The voice stays: the item comes back whole.
		(["the 1st item"], ["the 1st item"]),
		(["Is it 5?"], ["Is it 5?"]),
		# Two items stay two items.
		(["a", "12", "b"], ["a", "12", "b"]),
		# The voice changes: the wrappers stay and so does the split.
		(["a 1 b"], ["a ", ("lang", "zh_TW"), "1", EN, " b"]),
	],
	ids=["ordinal", "question", "items", "voice-change"],
)
def test_detection_rejoins_what_the_wrappers_split_where_the_voice_stays(monkeypatch, sequence, expected):
	numlan = "zh_TW" if sequence == ["a 1 b"] else "main"
	module, _items, result = detect_numbers(monkeypatch, sequence, numlan)
	assert wrapped_shape(module, result) == expected


def test_detection_keeps_nvdas_language_commands_and_other_commands_between_items(monkeypatch):
	marker = Marker()

	def sequence(module):
		nvda = sys.modules["speech.commands"].LangChangeCommand
		return [nvda("en"), "1", marker, "2", nvda(None), "x 3"]

	module, items, result = detect_numbers(monkeypatch, sequence, "main")
	assert wrapped_shape(module, result) == [EN, "1", marker, "2", ("lang", None), "x 3"]
	assert result[0] is items[0] and result[4] is items[4]


def test_detection_keeps_the_commands_detection_adds(monkeypatch):
	# Detection's own switch right after a number is not a wrapper: nothing joins across it.
	module, _ = load_pipeline_module(monkeypatch, punctuation_settings(0))

	def detect(sequence):
		sequence = list(sequence)
		index = sequence.index("中")
		return [*sequence[:index], module.WVLangChangeCommand("zh_TW"), *sequence[index:]]

	result = module.detect_with_number_language(["1中"], detect, number_context(module, "main"))
	assert wrapped_shape(module, result) == ["1", ("lang", "zh_TW"), "中"]


# Edge breaks for other synths (number-edge-pause spec D3).


def test_plain_breaks_mark_only_edge_breaks(monkeypatch):
	module, BreakCommand = load_pipeline_module(monkeypatch, punctuation_settings(0))
	sequence = [
		module.NumberEdgeBreakCommand(10),
		module.NumberBreakCommand(10),
		module.PunctuationBreakCommand(20),
		BreakCommand(5),
		"x",
	]
	result = module._plain_breaks(sequence)
	assert all(type(item) is BreakCommand for item in result[:4])
	assert [item.time for item in result[:4]] == [10, 10, 20, 5]
	assert [getattr(item, "worldvoice_number_edge", False) for item in result[:4]] == [
		True,
		False,
		False,
		False,
	]
	# Every stage handler plains its output again: a marked break stays marked.
	again = module._plain_breaks(result)
	assert [getattr(item, "worldvoice_number_edge", False) for item in again[:4]] == [
		True,
		False,
		False,
		False,
	]


def plain_shape(sequence):
	return [item if isinstance(item, str) else (type(item).__name__, item.time) for item in sequence]


@pytest.mark.parametrize(
	("sequence", "remove", "expected"),
	[
		(
			["Total. ", "E", "1", "NB", "2"],
			False,
			["Total", ".", " ", ("BreakCommand", 50), "1", ("BreakCommand", 10), "2"],
		),
		(["3", "E", "，下"], True, ["3", ("BreakCommand", 50), "下"]),
	],
	ids=["total", "3-comma-remove"],
)
def test_another_synth_keeps_the_punctuation_pause_next_to_an_edge(monkeypatch, sequence, remove, expected):
	settings = punctuation_settings(50, remove_characters=remove)
	settings.punctuation_pause_characters = "。，."
	module, _ = load_pipeline_module(monkeypatch, settings)
	monkeypatch.setattr(module.registry, "current_context", lambda: module.GENERIC_CONTEXT)
	commands = {"E": module.NumberEdgeBreakCommand(10), "NB": module.NumberBreakCommand(10)}
	plain = module._plain_breaks([commands.get(item, item) for item in sequence])
	(stage,) = [stage for stage in module.STAGES if stage.log_key == "punctuation_wait_factor"]
	assert plain_shape(stage.handler(plain)) == expected
