"""The number edge pause: a pause before and after a number in number and group modes.

The rows are the worked examples of the number-edge-pause spec (§5): the output of the number
stage, and the output after every stage of STAGES ("same" when the two are equal). Decided by the
user (2026-10-24): only the number and group modes get the pause, with a number pause above 0,
whatever text is next to the number.
"""

import sys
import time
from types import SimpleNamespace

import pytest
from pipeline_harness import load_pipeline_module, load_settings_module, symbol_name


class Marker:
	"""A speech command no stage knows, such as NVDA's IndexCommand."""


def make_settings(
	*,
	mode="number",
	size=3,
	wait=10,
	chars="",
	remove=False,
	pwait=50,
	item=0,
):
	"""The settings the stages read; the punctuation stage is on when *chars* names characters."""
	return SimpleNamespace(
		number_mode=mode,
		scope="WorldVoice",
		punctuation_pause_characters=chars,
		punctuation_pause_enabled=bool(chars),
		remove_punctuation_characters=remove,
		scaled_item_wait=lambda: item,
		scaled_number_wait=lambda: wait,
		scaled_chinesespace_wait=lambda: 0,
		scaled_punctuation_wait=lambda: pwait,
		group_size=size,
	)


def context(module, numlan="default", roles=True):
	if not roles:
		return module.SpeechContext(supports_roles=False, language=None, number_language=numlan)
	return module.SpeechContext(
		supports_roles=True,
		language="zh",
		number_language=numlan,
		default_voice_name="Z",
		default_voice_language="zh",
		voice_name_for_language={"zh": "Z", "en": "E", "fr": "F"}.get,
	)


def shape(sequence):
	module = sys.modules["synthDrivers.WorldVoice.pipeline"]
	BreakCommand = sys.modules["speech.commands"].BreakCommand
	result = []
	for item in sequence:
		if isinstance(item, str):
			result.append(item)
		elif isinstance(item, module.NumberEdgeBreakCommand):
			result.append(("E", item.time))
		elif isinstance(item, module.NumberBreakCommand):
			result.append(("NB", item.time))
		elif isinstance(item, module.PunctuationBreakCommand):
			result.append(("PB", item.time))
		elif isinstance(item, BreakCommand):
			result.append(("B*" if getattr(item, "worldvoice_number_edge", False) else "B", item.time))
		elif hasattr(item, "lang"):
			result.append(("L", item.lang))
		else:
			result.append(item)
	return result


def N(symbol, locale="zh"):
	"""The harness's name of a symbol for text in *locale*."""
	return symbol_name(locale, symbol)


E, NB, PB = ("E", 10), ("NB", 10), ("PB", 50)
LEN, LZH = ("L", "en"), ("L", "zh")
M = Marker()

# (sequence, options, stage output, output after STAGES). Options: make_settings keywords, and
# "numlan". A stage output of None: the row is checked only after STAGES.
ROWS = [
	pytest.param(["第3章"], {}, ["第", E, "3", E, "章"], "same", id="1"),
	pytest.param(["第3章"], {"mode": "group"}, ["第", E, "3", E, "章"], "same", id="1g"),
	pytest.param(["第3章"], {"mode": "value"}, ["第3章"], "same", id="1v"),
	pytest.param(["第3章"], {"numlan": "en"}, ["第", E, LEN, "3", LZH, E, "章"], "same", id="2"),
	pytest.param(["第3章"], {"mode": "value", "numlan": "en"}, ["第", LEN, "3", LZH, "章"], "same", id="2v"),
	pytest.param(["第123章"], {}, ["第", E, "1", NB, "2", NB, "3", E, "章"], "same", id="3"),
	pytest.param(
		["第123章"],
		{"mode": "group", "size": 2},
		["第", E, "12", NB, "3", E, "章"],
		"same",
		id="4",
	),
	pytest.param(
		["第123章"],
		{"numlan": "en"},
		["第", E, LEN, "1", NB, "2", NB, "3", LZH, E, "章"],
		"same",
		id="5",
	),
	pytest.param(["第3章"], {"mode": "none"}, ["第3章"], "same", id="6"),
	pytest.param(["第3章"], {"mode": "none", "numlan": "en"}, ["第", LEN, "3", LZH, "章"], "same", id="7"),
	pytest.param(["共 3 章"], {}, ["共 ", E, "3", E, " 章"], ["共", E, "3", E, "章"], id="8"),
	pytest.param(["共 3 章"], {"mode": "value"}, ["共 3 章"], "same", id="8v"),
	pytest.param(["1 2"], {}, ["1", NB, "2"], "same", id="9"),
	pytest.param(["1 2"], {"mode": "value"}, ["1 2"], ["1", NB, "2"], id="9v"),
	pytest.param(["1 2"], {"numlan": "en"}, [LEN, "1", LZH, NB, LEN, "2", LZH], "same", id="10"),
	pytest.param(["12 34"], {}, ["1", NB, "2", NB, "3", NB, "4"], "same", id="11"),
	pytest.param(["COVID-19"], {}, ["COVID-", E, "1", NB, "9"], "same", id="13"),
	pytest.param(["COVID-19"], {"mode": "group"}, ["COVID-", E, "19"], "same", id="13g"),
	pytest.param(["COVID-19"], {"mode": "value"}, ["COVID-19"], "same", id="13v"),
	pytest.param(["-5"], {}, ["-5"], "same", id="15"),
	pytest.param(["a -5"], {}, ["a ", E, "-5"], ["a", E, "-5"], id="16"),
	pytest.param(["x-5"], {}, ["x-", E, "5"], "same", id="17"),
	pytest.param(["35."], {}, ["3", NB, "5", E, " ."], ["3", NB, "5", E, "."], id="18"),
	pytest.param(["1."], {}, ["1", E, " ."], ["1", E, "."], id="19"),
	pytest.param(["a.5"], {}, ["a. ", E, "5"], ["a.", E, "5"], id="20"),
	pytest.param(
		["There are 5. Next"],
		{},
		["There are ", E, "5", E, " . Next"],
		["There are", E, "5", E, ". Next"],
		id="21",
	),
	pytest.param(
		["There are 5. Next"],
		{"chars": "."},
		None,
		["There are", E, "5", E, ".", PB, "Next"],
		id="22",
	),
	pytest.param(
		["12. Next"],
		{"mode": "value", "numlan": "en", "wait": 0},
		[LEN, "12", LZH, " . Next"],
		"same",
		id="23",
	),
	pytest.param(["3"], {}, ["3"], "same", id="24"),
	pytest.param(["第3章"], {"wait": 0}, ["第3章"], "same", id="25"),
	pytest.param(
		["the 1st item"],
		{},
		["the ", E, "1", E, "st item"],
		["the", E, "1", E, "st item"],
		id="26",
	),
	pytest.param(["MP3"], {}, ["MP", E, "3"], "same", id="26a"),
	pytest.param(["10am"], {}, ["1", NB, "0", E, "am"], "same", id="26b"),
	pytest.param(["the 1st item"], {"mode": "value"}, ["the 1st item"], "same", id="26v"),
	pytest.param(["Is it 5?"], {}, ["Is it ", E, "5", E, "?"], ["Is it", E, "5", E, "?"], id="27"),
	pytest.param(["第", M, "3", M, "章"], {}, ["第", M, "3", M, "章"], "same", id="28"),
	pytest.param(["第3。"], {"chars": "。"}, None, ["第", E, "3", E, "。"], id="31"),
	pytest.param(["第3。"], {"chars": "。", "remove": True}, None, ["第", E, "3", E, "。"], id="31r"),
	pytest.param(["3，"], {"chars": "，"}, None, ["3", E, "，"], id="32"),
	pytest.param(["3，"], {"chars": "，", "remove": True}, None, ["3", E, "，"], id="32r"),
	pytest.param(["第3。下一章"], {"chars": "。"}, None, ["第", E, "3", E, "。", PB, "下一章"], id="33"),
	pytest.param(
		["第3。下一章"],
		{"chars": "。", "remove": True},
		None,
		["第", E, "3", PB, "下一章"],
		id="34",
	),
	pytest.param(
		["第3。下一章"],
		{"chars": "。", "remove": True, "pwait": 0},
		None,
		["第", E, "3", E, "下一章"],
		id="35",
	),
	pytest.param(["3，下"], {"chars": "，"}, None, ["3", E, "，", PB, "下"], id="36"),
	pytest.param(["3，下"], {"chars": "，", "remove": True}, None, ["3", PB, "下"], id="37"),
	pytest.param(["Total. 12"], {"chars": "."}, None, ["Total", ".", PB, "1", NB, "2"], id="38"),
	pytest.param(["Total. 12"], {"chars": ".", "mode": "value"}, None, ["Total", ".", PB, "12"], id="38v"),
	pytest.param(["Total. 12"], {"chars": ".", "remove": True}, None, ["Total", PB, "1", NB, "2"], id="39"),
	pytest.param(["1，2"], {}, ["1", E, "，", E, "2"], "same", id="40"),
	pytest.param(["1，2"], {"chars": "，"}, None, ["1", E, "，", PB, "2"], id="41"),
	pytest.param(["1，2"], {"chars": "，", "remove": True}, None, ["1", PB, "2"], id="42"),
	pytest.param(["1，2"], {"chars": "，", "remove": True, "mode": "value"}, ["1，2"], "same", id="42v"),
	pytest.param(["1 "], {}, ["1 "], ["1"], id="43"),
	pytest.param(
		["Total. 12"],
		{"chars": ".", "pwait": 0},
		None,
		["Total", ".", E, "1", NB, "2"],
		id="44",
	),
	pytest.param(
		["3，", "下"],
		{"chars": "，", "remove": True, "item": 30},
		None,
		["3", ("B", 30), "下"],
		id="45",
	),
	pytest.param(["12,345元"], {"mode": "value"}, None, ["12345元"], id="46"),
	# O4: a sign after a word stays with the word; a number with a symbol inside is one number.
	pytest.param(["中+2"], {}, ["中+", E, "2"], "same", id="o4-plus"),
	pytest.param(["中+2"], {"mode": "value"}, ["中+2"], "same", id="o4-plus-value"),
	pytest.param(["5-3"], {}, ["5", NB, N("-"), NB, "3"], "same", id="o4-range"),
]
STAGE_ROWS = [row for row in ROWS if row.values[2] is not None]


def run_row(monkeypatch, options):
	options = dict(options)
	numlan = options.pop("numlan", "default")
	settings = make_settings(**options)
	module, _ = load_pipeline_module(monkeypatch, settings)
	return module, settings, context(module, numlan)


@pytest.mark.parametrize(("sequence", "options", "stage", "full"), STAGE_ROWS)
def test_number_stage_worked_examples(monkeypatch, sequence, options, stage, full):
	module, settings, ctx = run_row(monkeypatch, options)
	assert shape(module.inject_numbers(sequence, settings, ctx)) == stage


def test_off_mode_yields_the_same_objects(monkeypatch):
	module, settings, ctx = run_row(monkeypatch, {"mode": "none"})
	sequence = ["第3章"]
	result = list(module.inject_numbers(sequence, settings, ctx))
	assert len(result) == 1 and result[0] is sequence[0]


@pytest.mark.parametrize("wait", [0, -5])
@pytest.mark.parametrize("mode", ["number", "group"])
def test_no_edge_break_without_a_number_pause(monkeypatch, mode, wait):
	# Decided by the user (2026-10-24, U4): a number pause of 0 means no edge break at all; the
	# pieces of a number still reach the synth apart.
	module, settings, ctx = run_row(monkeypatch, {"mode": mode, "size": 2, "wait": wait})
	result = list(module.inject_numbers(["第123章"], settings, ctx))
	breaks = [item for item in result if not isinstance(item, str)]
	assert breaks
	assert all(type(item) is module.NumberBreakCommand and item.time == wait for item in breaks)


def test_a_global_factor_below_ten_adds_no_edge_break(monkeypatch):
	module, _, _ = run_row(monkeypatch, {})
	pipeline = {"number_mode": "number", "global_wait_factor": 9, "number_wait_factor": 10}
	settings = load_settings_module(
		monkeypatch,
		{"WorldVoice": {"pipeline": pipeline}},
	).pipeline_settings.get()
	assert settings.scaled_number_wait() == 0
	assert list(module.inject_numbers(["第3章"], settings, module.GENERIC_CONTEXT)) == ["第3章"]


@pytest.mark.parametrize(
	("text", "expected"),
	[
		("3", ["3"]),
		("3章", ["3", E, "章"]),
		("第3", ["第", E, "3"]),
		("3 ", ["3 "]),
		("3 ", ["3 "]),
		("3　", ["3　"]),
		(" 3", [" 3"]),
		(" 3 ", [" 3 "]),
		("　第3　", ["　第", E, "3　"]),
		("", []),
		(" ", [" "]),
		("　", ["　"]),
	],
	ids=[
		"alone",
		"start",
		"end",
		"space-after",
		"no-break-space-after",
		"ideographic-space-after",
		"space-before",
		"spaces-around",
		"ideographic-spaces-around",
		"blank-empty",
		"blank-space",
		"blank-ideographic",
	],
)
def test_no_edge_break_at_an_item_end_or_before_only_whitespace(monkeypatch, text, expected):
	# O2 and D1: an edge break only where the item has spoken text on that side of the number.
	module, settings, ctx = run_row(monkeypatch, {})
	assert shape(module.inject_numbers([text], settings, ctx)) == expected


@pytest.mark.parametrize(
	("text", "options", "stage", "after"),
	[
		("1 2", {}, ["1", NB, "2"], ["1", NB, "2"]),
		("1 2", {}, ["1", NB, "2"], ["1", NB, "2"]),
		("12 34", {}, ["1", NB, "2", NB, "3", NB, "4"], ["1", NB, "2", NB, "3", NB, "4"]),
		(
			"1 2",
			{"numlan": "en"},
			[LEN, "1", LZH, NB, LEN, "2", LZH],
			[LEN, "1", LZH, NB, LEN, "2", LZH],
		),
		("1 2", {"mode": "value"}, ["1 2"], ["1", NB, "2"]),
	],
	ids=["space", "no-break", "digits", "wrapper", "value"],
)
def test_one_break_between_numbers_that_only_whitespace_separates(monkeypatch, text, options, stage, after):
	# O3: the number stage replaces the gap with one number break; number_wait_factor adds none.
	module, settings, ctx = run_row(monkeypatch, options)
	result = list(module.inject_numbers([text], settings, ctx))
	assert shape(result) == stage
	assert shape(module.number_wait_factor(result, settings, ctx)) == after


def test_edge_breaks_sit_outside_the_wrapper(monkeypatch):
	# O1: the closing wrapper names the language in force, here NVDA's French stretch.
	module, settings, ctx = run_row(monkeypatch, {"numlan": "en"})
	sequence = [sys.modules["speech.commands"].LangChangeCommand("fr"), "y 2x"]
	result = module.inject_numbers(sequence, settings, ctx)
	assert shape(result) == [("L", "fr"), "y ", E, LEN, "2", ("L", "fr"), E, "x"]


def test_the_dot_rule_with_a_wrapper_and_edges(monkeypatch):
	module, settings, ctx = run_row(monkeypatch, {"numlan": "en"})
	result = module.inject_numbers(["12. Next"], settings, ctx)
	assert shape(result) == [LEN, "1", NB, "2", LZH, E, " . Next"]


def test_one_edge_and_one_gap_instance_per_run(monkeypatch):
	# D10: the synth only reads a break's time.
	module, settings, ctx = run_row(monkeypatch, {})
	result = list(module.inject_numbers(["第1章 2 3", "第4章"], settings, ctx))
	edges = [item for item in result if isinstance(item, module.NumberEdgeBreakCommand)]
	assert len(edges) == 5
	assert all(item is edges[0] for item in edges)
	index = result.index("2")
	assert shape(result[index : index + 3]) == ["2", NB, "3"]
	assert type(result[index + 1]) is module.NumberBreakCommand


def test_a_long_item_of_numbers_stays_linear(monkeypatch):
	# Review Focus 3: a row of a spreadsheet, every number with text on both sides.
	module, settings, ctx = run_row(monkeypatch, {"chars": ".,"})
	sequence = ["a1 " * 5000]
	start = time.perf_counter()
	for stage in module.STAGES:
		sequence = list(stage.fn(sequence, settings, ctx))
	assert time.perf_counter() - start < 2
	assert sum(isinstance(item, module.NumberEdgeBreakCommand) for item in sequence) == 10000 - 1


@pytest.mark.parametrize(("sequence", "options", "stage", "full"), ROWS)
def test_worked_examples_through_every_stage(monkeypatch, sequence, options, stage, full):
	module, settings, ctx = run_row(monkeypatch, options)
	for each in module.STAGES:
		sequence = list(each.fn(sequence, settings, ctx))
	assert shape(sequence) == (stage if full == "same" else full)


def run_handlers(monkeypatch, sequence, options, ctx_of):
	"""Every stage handler, as NVDA runs them, in the context *ctx_of(module)* gives."""
	options = dict(options)
	settings = make_settings(**options)
	module, _ = load_pipeline_module(monkeypatch, settings)
	ctx = ctx_of(module)
	monkeypatch.setattr(module, "current_context", lambda: ctx)
	sequence = list(sequence(module)) if callable(sequence) else list(sequence)
	for stage in module.STAGES:
		sequence = stage.handler(sequence)
	return shape(sequence)


@pytest.mark.parametrize(
	("sequence", "numlan"),
	[(["第3章"], "default"), (lambda module: [module.WVLangChangeCommand("en"), "第3章"], "en")],
	ids=["29", "30"],
)
def test_other_synths_get_marked_edge_breaks(monkeypatch, sequence, numlan):
	# Spec D3: another synth gets plain breaks, and the WorldVoice language command is dropped.
	result = run_handlers(monkeypatch, sequence, {}, lambda module: context(module, numlan, roles=False))
	assert result == ["第", ("B*", 10), "3", ("B*", 10), "章"]


@pytest.mark.parametrize(
	("sequence", "options", "expected"),
	[
		(["Total. 12"], {"chars": "."}, ["Total", ".", ("B", 50), "1", ("B", 10), "2"]),
		(["3，下"], {"chars": "，", "remove": True}, ["3", ("B", 50), "下"]),
	],
	ids=["total", "3-comma-remove"],
)
def test_other_synths_keep_the_punctuation_pause_through_the_handlers(
	monkeypatch,
	sequence,
	options,
	expected,
):
	result = run_handlers(monkeypatch, sequence, options, lambda module: context(module, roles=False))
	assert result == expected


@pytest.mark.parametrize("remove", [False, True], ids=["remove-off", "remove-on"])
def test_a_space_pause_character_meets_an_edge_break(monkeypatch, remove):
	# Review Focus 5: the space after the number is a pause point where the edge break already is.
	module, settings, ctx = run_row(monkeypatch, {"chars": " ", "remove": remove})
	sequence = ["共 3 章"]
	for stage in module.STAGES:
		sequence = list(stage.fn(sequence, settings, ctx))
	assert shape(sequence) == ["共", E, "3", PB, "章"]
