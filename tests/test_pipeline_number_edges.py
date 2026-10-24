"""The number edge pause: a pause before and after a number in number and group modes.

The rows are the worked examples of the number-edge-pause spec (§5): the output of the number
stage, and the output after every stage of STAGES ("same" when the two are equal). Decided by the
user (2026-10-24): only the number and group modes get the pause, with a number pause above 0,
whatever text is next to the number, in its item or another (fix/number-edge-pause-items).
"""

import sys
import time
from dataclasses import replace
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


# NVDA's commands that end an utterance, by class name, and their notation.
UTTERANCE_ENDS = {"EndUtteranceCommand": "EU", "ConfigProfileTriggerCommand": "CPT"}


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
		elif type(item).__name__ in UTTERANCE_ENDS:
			result.append(UTTERANCE_ENDS[type(item).__name__])
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

B10, B20 = ("B", 10), ("B", 20)


def item_rows(sequence, stage, by_item_wait, name):
	"""Rows of *sequence* at each item wait of *by_item_wait*: its output after STAGES ("same": *stage*)."""
	return [
		pytest.param(sequence, {"item": item}, stage, full, id=f"{name}-item{item}")
		for item, full in by_item_wait.items()
	]


# Corrected by fix/number-edge-pause-items (decided by the user, 2026-10-24; replaces O2 and D1): a
# number gets an edge break on each side with spoken text anywhere in the sequence, in its item or
# another, but none at the start or end of the sequence. An item break that meets it leaves one break,
# the longest (E2), so the item wait no longer decides whether a number is apart from the text.
ITEM_ROWS = [
	*item_rows(
		["第3", "章"],
		["第", E, "3", E, "章"],
		{0: "same", 5: "same", 10: ["第", E, "3", B10, "章"]},
		"end",
	),
	*item_rows(["第3", "章"], ["第", E, "3", E, "章"], {20: ["第", E, "3", B20, "章"]}, "end"),
	*item_rows(
		["第", "3", "章"],
		["第", E, "3", E, "章"],
		{0: "same", 10: ["第", B10, "3", B10, "章"]},
		"alone",
	),
	*item_rows(["第3章"], ["第", E, "3", E, "章"], {0: "same", 10: "same"}, "inside"),
	*item_rows(
		["第1", "2章"],
		["第", E, "1", E, "2", E, "章"],
		{0: "same", 10: ["第", E, "1", B10, "2", E, "章"]},
		"numbers",
	),
	*item_rows(["1", "2"], ["1", E, "2"], {0: "same", 10: ["1", B10, "2"]}, "whole-numbers"),
	*item_rows(["3", "章"], ["3", E, "章"], {0: "same", 10: ["3", B10, "章"]}, "first"),
	*item_rows(["第", "3"], ["第", E, "3"], {0: "same", 10: ["第", B10, "3"]}, "last"),
	*item_rows(["3章"], ["3", E, "章"], {0: "same", 10: "same"}, "sequence-start"),
	*item_rows(["第3"], ["第", E, "3"], {0: "same", 10: "same"}, "sequence-end"),
	*item_rows([" ", "3", " "], [" ", "3", " "], {0: ["3"]}, "blank-around"),
	*item_rows(["1 ", "章"], ["1 ", E, "章"], {0: ["1", E, "章"], 10: ["1", B10, "章"]}, "space-end"),
	*item_rows(["第", " 3"], ["第", E, " 3"], {0: ["第", E, "3"], 10: ["第", B10, "3"]}, "space-start"),
	*item_rows(
		["第3", " ", "章"],
		["第", E, "3", E, " ", "章"],
		{0: ["第", E, "3", E, "章"], 10: ["第", E, "3", B10, "章"]},
		"blank-item",
	),
	*item_rows(["第3", M, "章"], ["第", E, "3", E, M, "章"], {0: "same", 10: "same"}, "command"),
	pytest.param(
		["第3", "章"],
		{"numlan": "en", "item": 10},
		["第", E, LEN, "3", LZH, E, "章"],
		"same",
		id="wrapper-item10",
	),
	pytest.param(
		["第", "3", "章"],
		{"mode": "group", "item": 10},
		None,
		["第", B10, "3", B10, "章"],
		id="group",
	),
	*[
		pytest.param(sequence, {"mode": mode, "item": item}, None, full, id=f"{name}-{mode}-item{item}")
		for sequence, full, name in [
			(["第3", "章"], ["第3", "章"], "end"),
			(["第", "3", "章"], ["第", "3", "章"], "alone"),
			(["1", "2"], ["1", NB, "2"], "whole-numbers"),
		]
		for mode in ("value", "none")
		for item in (0,)
	],
	pytest.param(["第", "3", "章"], {"wait": 0}, ["第", "3", "章"], "same", id="alone-pause0"),
	pytest.param(["Total.", "12"], {"chars": "."}, None, ["Total", ".", PB, "1", NB, "2"], id="total-items"),
	pytest.param(
		["Total.", "12"],
		{"chars": ".", "item": 10},
		None,
		["Total", ".", B10, "1", NB, "2"],
		id="total-items-item10",
	),
	pytest.param(
		["Total.", "12"],
		{"chars": ".", "pwait": 0},
		None,
		["Total", ".", E, "1", NB, "2"],
		id="total-items-pwait0",
	),
]

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
		[LEN, "12", LZH, ". Next"],
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
	pytest.param(["第", M, "3", M, "章"], {}, ["第", M, E, "3", E, M, "章"], "same", id="28"),
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
	# Review M1: whole numbers that an edge break leaves at the end and start of two items get the
	# number pause between them, as ["1", "2"] does.
	pytest.param(["第1", "2章"], {}, ["第", E, "1", E, "2", E, "章"], "same", id="m1-items"),
	*ITEM_ROWS,
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
def test_no_edge_break_at_the_sequence_start_or_end(monkeypatch, text, expected):
	# An edge break only where spoken text is on that side of the number; an item alone is the
	# whole sequence, so only whitespace before or after a number is nothing spoken (corrected by
	# fix/number-edge-pause-items: this pinned O2 and D1, no edge break at an item's start or end).
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
	assert shape(result) == [LEN, "1", NB, "2", LZH, E, ". Next"]


def test_one_edge_and_one_gap_instance_per_run(monkeypatch):
	# D10: the synth only reads a break's time.
	module, settings, ctx = run_row(monkeypatch, {})
	result = list(module.inject_numbers(["第1章 2 3", "第4章", "5"], settings, ctx))
	edges = [item for item in result if isinstance(item, module.NumberEdgeBreakCommand)]
	inside = [item for item in edges if not isinstance(item, module.NumberItemEdgeBreakCommand)]
	at_items = [item for item in edges if isinstance(item, module.NumberItemEdgeBreakCommand)]
	assert (len(inside), len(at_items)) == (5, 2)
	assert all(item is inside[0] for item in inside)
	assert all(item is at_items[0] for item in at_items)
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
	("sequence", "item", "expected"),
	[
		(["第3", "章"], 0, ["第", ("B*", 10), "3", ("B*", 10), "章"]),
		(["第3", "章"], 10, ["第", ("B*", 10), "3", ("B", 10), "章"]),
		(["第", "3", "章"], 0, ["第", ("B*", 10), "3", ("B*", 10), "章"]),
		(["第", "3", "章"], 20, ["第", ("B", 20), "3", ("B", 20), "章"]),
		(["第1", "2章"], 0, ["第", ("B*", 10), "1", ("B*", 10), "2", ("B*", 10), "章"]),
	],
	ids=["end-item0", "end-item10", "alone-item0", "alone-item20", "numbers-item0"],
)
def test_other_synths_get_edge_breaks_across_items(monkeypatch, sequence, item, expected):
	# The item stage tells an edge break at an item's start or end apart on a plain break too.
	result = run_handlers(monkeypatch, sequence, {"item": item}, lambda module: context(module, roles=False))
	assert result == expected


@pytest.mark.parametrize("item", [0, 10])
@pytest.mark.parametrize(
	("sequence", "expected"),
	[
		# NVDA's speakSpelling puts the whole spelling in one speak(), an EndUtteranceCommand after
		# every character; the filters see it all, the synth one utterance per character.
		(["a", "EU", "1", "EU", "b", "EU"], "same"),
		(["1", "EU", "2", "EU"], "same"),
		(["EU", "3", "EU"], "same"),
		# Say All ends a chunk with an EndUtteranceCommand.
		(["第3", "EU", "章"], ["第", E, "3", "EU", "章"]),
		(["第", "EU", "3章"], ["第", "EU", "3", E, "章"]),
		(["第3", "CPT", "章"], ["第", E, "3", "CPT", "章"]),
		# Inside one utterance the text of another item still counts.
		(
			["a", "EU", "第3", "章", "EU"],
			{0: ["a", "EU", "第", E, "3", E, "章", "EU"], 10: ["a", "EU", "第", E, "3", B10, "章", "EU"]},
		),
		(["第", "EU", "3", "章"], {0: ["第", "EU", "3", E, "章"], 10: ["第", "EU", "3", B10, "章"]}),
	],
	ids=[
		"spell-a1b",
		"spell-12",
		"spell-1",
		"say-all-end",
		"say-all-start",
		"profile-trigger",
		"inside",
		"after-end",
	],
)
def test_an_utterance_end_is_the_end_of_the_sequence(monkeypatch, item, sequence, expected):
	# Review I1: NVDA's speech manager splits the sequence at an EndUtteranceCommand, and at a
	# ConfigProfileTriggerCommand, into utterances; no edge break starts or ends one.
	module, settings, ctx = run_row(monkeypatch, {"item": item})
	commands = sys.modules["speech.commands"]
	makers = {"EU": commands.EndUtteranceCommand, "CPT": commands.ConfigProfileTriggerCommand}
	items = [makers[entry]() if entry in makers else entry for entry in sequence]
	for stage in module.STAGES:
		items = list(stage.fn(items, settings, ctx))
	if isinstance(expected, dict):
		expected = expected[item]
	assert shape(items) == (sequence if expected == "same" else expected)


@pytest.mark.parametrize("item", [0, 10])
def test_language_commands_between_items_do_not_hide_the_text(monkeypatch, item):
	module, settings, ctx = run_row(monkeypatch, {"item": item})
	LangChangeCommand = sys.modules["speech.commands"].LangChangeCommand
	sequence = ["第3", LangChangeCommand("en"), "abc", LangChangeCommand(None), "4"]
	for stage in module.STAGES:
		sequence = list(stage.fn(sequence, settings, ctx))
	assert shape(sequence) == ["第", E, "3", E, LEN, "abc", ("L", None), E, "4"]


def test_a_long_sequence_of_number_items_stays_linear(monkeypatch):
	# A table read cell by cell: every number item with spoken items around it.
	module, settings, ctx = run_row(monkeypatch, {"chars": ".,", "item": 10})
	sequence = ["a", "1"] * 5000
	start = time.perf_counter()
	for stage in module.STAGES:
		sequence = list(stage.fn(sequence, settings, ctx))
	assert time.perf_counter() - start < 2
	assert shape(sequence[:5]) == ["a", B10, "1", B10, "a"]
	assert sum(isinstance(item, module.BreakCommand) for item in sequence) == 10000 - 1


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


def test_the_shortest_number_wait_adds_edge_breaks(monkeypatch):
	# A number wait factor of 1 at the default global factor is a 1 ms pause, above 0 (mutmut).
	module, settings, ctx = run_row(monkeypatch, {"wait": 1})
	result = module.inject_numbers(["第3章"], settings, ctx)
	assert shape(result) == ["第", ("E", 1), "3", ("E", 1), "章"]


@pytest.mark.parametrize(
	("numlan", "expected"),
	[("en", ["a.", LEN, "1", LZH, ". b"]), ("zh", ["a.1. b"]), ("fr", ["a.1. b"])],
	ids=["wrapper-kept", "same-voice", "no-voice"],
)
def test_off_mode_with_a_locale_keeps_the_dots_as_they_are(monkeypatch, numlan, expected):
	# "Off" wraps a number for a locale number language but adds no dot-rule space (mutmut), also
	# where the wrapper goes: zh is the voice in force, fr has no voice here (review M4).
	module, settings, ctx = run_row(monkeypatch, {"mode": "none", "numlan": numlan})
	ctx = replace(ctx, voice_name_for_language={"zh": "Z", "en": "E"}.get)
	result = module.inject_numbers(["a.1. b"], settings, ctx)
	assert shape(result) == expected


@pytest.mark.parametrize("wait", [0, 10])
@pytest.mark.parametrize(
	("text", "mode"),
	[("12. Next", "value"), ("35.", "number"), ("35.", "value")],
	ids=["next-value", "35-number", "35-value"],
)
def test_the_dot_rule_adds_no_pause_point_where_the_wrapper_stays(monkeypatch, text, mode, wait):
	# Review I1: with a space among the punctuation pause characters, a dot-rule space next to a
	# number read by another voice would be a new pause point before the period. Today's output
	# has none, in value mode at any pause and in number mode alike.
	module, settings, ctx = run_row(monkeypatch, {"mode": mode, "numlan": "en", "wait": wait, "chars": " "})
	sequence = [text]
	for stage in module.STAGES:
		sequence = list(stage.fn(sequence, settings, ctx))
	result = shape(sequence)
	assert ("PB", 50) not in result[: result.index(".")], result
