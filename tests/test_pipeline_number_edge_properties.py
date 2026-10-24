"""Properties of the number edge pause (number-edge-pause spec §8.3, P-E1 to P-E6), with Hypothesis.

The stages are pure functions of their arguments, so one pipeline module per test serves every
example: settings are fresh per example and no state carries over.
"""

import sys
from itertools import pairwise
from types import SimpleNamespace

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from pipeline_harness import load_pipeline_module, punctuation_settings, symbol_name

SHARED_ENV = settings(suppress_health_check=[HealthCheck.function_scoped_fixture])

TEXT = st.text(alphabet="0123456789+-.,:aZ共第章。，，  　", max_size=16)
MODES = st.sampled_from(["none", "value", "number", "group"])
SPACED_MODES = st.sampled_from(["number", "group"])
NUMBER_LANGUAGES = st.sampled_from(["default", "main", "en"])


@pytest.fixture
def env(monkeypatch):
	module, BreakCommand = load_pipeline_module(monkeypatch, punctuation_settings(0))
	return SimpleNamespace(module=module, BreakCommand=BreakCommand)


def stage_settings(mode="number", size=3, wait=10, chars="", remove=False, pwait=50, item=0, chinese=0):
	return SimpleNamespace(
		number_mode=mode,
		scope="WorldVoice",
		punctuation_pause_characters=chars,
		punctuation_pause_enabled=bool(chars),
		remove_punctuation_characters=remove,
		scaled_item_wait=lambda: item,
		scaled_number_wait=lambda: wait,
		scaled_chinesespace_wait=lambda: chinese,
		scaled_punctuation_wait=lambda: pwait,
		group_size=size,
	)


def context(module, numlan, roles=True):
	if not roles:
		return module.SpeechContext(supports_roles=False, language=None, number_language=numlan)
	return module.SpeechContext(
		supports_roles=True,
		language="zh",
		number_language=numlan,
		default_voice_name="Z",
		default_voice_language="zh",
		voice_name_for_language={"zh": "Z", "en": "E"}.get,
	)


def symbol_of_name(module):
	"""The harness's names of the number symbols, in every locale these contexts use, back to the symbol."""
	return {
		symbol_name(locale, symbol): symbol for symbol in module.numbers.SYMBOLS for locale in ("en", "zh")
	}


def shape(sequence):
	return [
		item
		if isinstance(item, str)
		else (type(item).__name__, getattr(item, "lang", getattr(item, "time", None)))
		for item in sequence
	]


def is_language(env, item):
	return isinstance(item, sys.modules["speech.commands"].LangChangeCommand)


def without_language(env, sequence):
	return [item for item in sequence if not is_language(env, item)]


def is_edge(env, item):
	return isinstance(item, env.module.NumberEdgeBreakCommand)


def numbers_and_gaps(env, text):
	"""The parts of *text* the number stage reads, and the indexes of its whitespace gaps."""
	parts = list(env.module._split_numbers_for_language(text))
	gaps = {
		index for index, (kind, value) in enumerate(parts) if 0 < index < len(parts) - 1 and value.isspace()
	}
	return parts, gaps


@SHARED_ENV
@given(
	text=TEXT,
	mode=SPACED_MODES,
	size=st.integers(2, 10),
	numlan=NUMBER_LANGUAGES,
	wait=st.integers(-5, 60),
)
def test_property_edges_keep_the_text(env, text, mode, size, numlan, wait):
	# P-E1: only the whitespace between two numbers goes, and only with a pause; the dot rule adds spaces.
	names = symbol_of_name(env.module)
	result = env.module.inject_numbers([text], stage_settings(mode, size, wait), context(env.module, numlan))
	spoken = "".join(names.get(item, item) for item in result if isinstance(item, str))
	parts, gaps = numbers_and_gaps(env, text)
	expected = "".join(
		value for index, (_kind, value) in enumerate(parts) if not (wait > 0 and index in gaps)
	)
	assert spoken.replace(" ", "") == expected.replace(" ", ""), (text, result)


@SHARED_ENV
@given(
	sequence=st.lists(st.one_of(TEXT, st.sampled_from(["en", "zh", None])), max_size=4),
	mode=MODES,
	numlan=NUMBER_LANGUAGES,
	roles=st.booleans(),
	wait=st.integers(-5, 60),
)
def test_property_no_edge_outside_digit_and_group_modes(env, sequence, mode, numlan, roles, wait):
	# P-E2, decided by the user (2026-10-24, U1, U4).
	module = env.module
	items = [item if isinstance(item, str) else module.WVLangChangeCommand(item) for item in sequence]
	ctx = context(module, numlan, roles)
	result = list(module.inject_numbers(items, stage_settings(mode, wait=wait), ctx))
	if mode in ("value", "none") or wait <= 0:
		assert not any(is_edge(env, item) for item in result), result
	if mode == "value":
		at_zero = list(module.inject_numbers(items, stage_settings(mode, wait=0), ctx))
		assert shape(result) == shape(at_zero)


@SHARED_ENV
@given(
	text=TEXT,
	mode=SPACED_MODES,
	size=st.integers(2, 10),
	numlan=NUMBER_LANGUAGES,
	wait=st.integers(1, 60),
)
def test_property_one_break_between_numbers(env, text, mode, size, numlan, wait):
	# P-E3: no two breaks meet, and between numbers that only whitespace separates there is one
	# number break; the others are the separators between a number's pieces.
	module = env.module
	result = list(module.inject_numbers([text], stage_settings(mode, size, wait), context(module, numlan)))
	is_break = lambda item: isinstance(item, env.BreakCommand)
	for before, after in pairwise(without_language(env, result)):
		assert not (is_break(before) and is_break(after)), (text, result)
	parts, gaps = numbers_and_gaps(env, text)
	name_of = lambda symbol: symbol_name("x", symbol)
	separators = sum(
		len(module.numbers.number_pieces(value, mode, size, name_of)) - 1
		for kind, value in parts
		if kind == "number"
	)
	plain = [item for item in result if type(item) is module.NumberBreakCommand]
	assert len(plain) == separators + len(gaps), (text, result)


@SHARED_ENV
@given(
	text=TEXT,
	mode=SPACED_MODES,
	size=st.integers(2, 10),
	numlan=NUMBER_LANGUAGES,
	wait=st.integers(1, 60),
)
def test_property_edges_sit_at_number_boundaries(env, text, mode, size, numlan, wait):
	# P-E4: one side of an edge break is the first or last piece of a number, the other spoken text.
	module = env.module
	result = without_language(
		env,
		module.inject_numbers([text], stage_settings(mode, size, wait), context(module, numlan)),
	)
	for index, item in enumerate(result):
		if not is_edge(env, item):
			continue
		assert 0 < index < len(result) - 1, (text, result)
		before, after = result[index - 1], result[index + 1]
		assert isinstance(before, str) and isinstance(after, str), (text, result)
		starts_number = after.lstrip("+-")[:1].isdecimal()
		assert (before[-1].isdecimal() and after.strip()) or (starts_number and before.strip()), (
			text,
			result,
		)


@settings(SHARED_ENV, max_examples=400)
@given(data=st.data())
def test_property_edges_never_meet_another_break(env, data):
	# P-E5: after every stage, no edge break sits next to any other break (language commands
	# make no sound, so they are transparent).
	module = env.module
	item = st.one_of(
		TEXT,
		st.builds(lambda: env.BreakCommand(30)),
		st.builds(lambda: module.WVLangChangeCommand("en")),
	)
	sequence = data.draw(st.lists(item, max_size=4))
	chars = data.draw(st.sampled_from(["", ".,", "。，", ". ,"]))
	run_settings = stage_settings(
		mode=data.draw(MODES),
		size=data.draw(st.integers(2, 10)),
		wait=data.draw(st.integers(0, 60)),
		chars=chars,
		remove=data.draw(st.booleans()),
		pwait=data.draw(st.integers(0, 300)),
		item=data.draw(st.integers(0, 60)),
		chinese=data.draw(st.integers(0, 60)),
	)
	ctx = context(module, data.draw(NUMBER_LANGUAGES), data.draw(st.booleans()))
	result = sequence
	for stage in module.STAGES:
		result = list(stage.fn(result, run_settings, ctx))
	audible = without_language(env, result)
	for before, after in pairwise(audible):
		if is_edge(env, before) or is_edge(env, after):
			assert not (isinstance(before, env.BreakCommand) and isinstance(after, env.BreakCommand)), result


@SHARED_ENV
@given(data=st.data())
def test_property_merge_keeps_the_longest(env, data):
	# P-E6: a run that holds an edge break keeps one break, the longest; every other run is untouched.
	module = env.module
	marker = object()
	time = st.integers(0, 60)
	item = st.one_of(
		st.sampled_from(["a", " ", ""]),
		time.map(module.NumberEdgeBreakCommand),
		time.map(module.NumberBreakCommand),
		time.map(module.PunctuationBreakCommand),
		time.map(env.BreakCommand),
		st.just(marker),
	)
	sequence = data.draw(st.lists(item, max_size=10))
	result = list(module._merge_edge_breaks(sequence))

	def runs(items):
		groups, current = [], []
		for entry in items:
			if isinstance(entry, str) and entry.strip():
				groups.append(current)
				current = []
			else:
				current.append(entry)
		groups.append(current)
		return groups

	is_break = lambda entry: isinstance(entry, env.BreakCommand)
	for before, after in zip(runs(sequence), runs(result), strict=True):
		breaks = [entry for entry in before if is_break(entry)]
		if len(breaks) >= 2 and any(map(module._is_edge_break, breaks)):
			(kept,) = [entry for entry in after if is_break(entry)]
			assert kept.time == max(entry.time for entry in breaks)
			assert [entry for entry in after if not is_break(entry)] == [
				entry for entry in before if not is_break(entry)
			]
		else:
			assert len(after) == len(before) and all(a is b for a, b in zip(after, before))
