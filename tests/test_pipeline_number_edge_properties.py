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


def stage_settings(mode="number", size=3, wait=10, chars="", remove=False, pwait=50, item=0, unspaced=0):
	return SimpleNamespace(
		number_mode=mode,
		scope="WorldVoice",
		punctuation_pause_characters=chars,
		punctuation_pause_enabled=bool(chars),
		remove_punctuation_characters=remove,
		scaled_item_wait=lambda: item,
		scaled_number_wait=lambda: wait,
		scaled_unspaced_script_space_wait=lambda: unspaced,
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


class Marker:
	"""A speech command no stage knows, such as NVDA's IndexCommand."""


def runs(items):
	"""What lies between two spoken text items, before the first and after the last."""
	groups, current = [], []
	for entry in items:
		if isinstance(entry, str) and entry.strip():
			groups.append(current)
			current = []
		else:
			current.append(entry)
	groups.append(current)
	return groups


def draw_sequence(env, data, *, remove=None):
	"""A sequence of up to 4 items, settings for every stage, and a context, from *data*."""
	module = env.module
	item = st.one_of(
		TEXT,
		st.builds(lambda: env.BreakCommand(30)),
		st.builds(lambda: module.WVLangChangeCommand("en")),
		st.builds(Marker),
		st.builds(lambda: sys.modules["speech.commands"].EndUtteranceCommand()),
		st.builds(lambda: sys.modules["speech.commands"].ConfigProfileTriggerCommand()),
	)
	sequence = data.draw(st.lists(item, max_size=5))
	run_settings = stage_settings(
		mode=data.draw(MODES),
		size=data.draw(st.integers(2, 10)),
		wait=data.draw(st.integers(0, 60)),
		chars=data.draw(st.sampled_from(["", ".,", "。，", ". ,"])),
		remove=data.draw(st.booleans()) if remove is None else remove,
		pwait=data.draw(st.integers(0, 300)),
		item=data.draw(st.integers(0, 60)),
		unspaced=data.draw(st.integers(0, 60)),
	)
	ctx = context(module, data.draw(NUMBER_LANGUAGES), data.draw(st.booleans()))
	return sequence, run_settings, ctx


def every_stage(env, sequence, run_settings, ctx):
	for stage in env.module.STAGES:
		sequence = list(stage.fn(sequence, run_settings, ctx))
	return sequence


@settings(SHARED_ENV, max_examples=400)
@given(data=st.data())
def test_property_edges_never_meet_another_break(env, data):
	# P-E5: after every stage, a run between two spoken items that holds an edge break holds no
	# other break: language and other commands make no sound, and the edge break of a number at an
	# item's start or end meets the item break there (corrected by fix/number-edge-pause-items).
	sequence, run_settings, ctx = draw_sequence(env, data)
	result = every_stage(env, sequence, run_settings, ctx)
	for run in runs(result):
		breaks = [entry for entry in run if isinstance(entry, env.BreakCommand)]
		if any(is_edge(env, entry) for entry in breaks):
			assert len(breaks) == 1, (sequence, result)


@settings(SHARED_ENV, max_examples=400)
@given(data=st.data())
def test_property_no_edge_at_the_start_or_end_of_the_sequence(env, data):
	# P-E7 (fix/number-edge-pause-items): nothing spoken before the first spoken item or after the
	# last, so no edge break there, after the number stage and, while removal leaves every mark
	# spoken, after every stage. NVDA's speech manager splits the sequence into utterances at
	# EndUtteranceCommand and ConfigProfileTriggerCommand, and each utterance counts (review I1).
	commands = sys.modules["speech.commands"]
	ends = (commands.EndUtteranceCommand, commands.ConfigProfileTriggerCommand)
	sequence, run_settings, ctx = draw_sequence(env, data, remove=False)
	staged = list(env.module.inject_numbers(sequence, run_settings, ctx))
	result = every_stage(env, sequence, run_settings, ctx)
	for each in (staged, result):
		utterances = [[]]
		for entry in each:
			if isinstance(entry, ends):
				utterances.append([])
			else:
				utterances[-1].append(entry)
		for utterance in utterances:
			groups = runs(utterance)
			assert not any(is_edge(env, entry) for entry in (*groups[0], *groups[-1])), (sequence, each)


@SHARED_ENV
@given(
	sequence=st.lists(st.one_of(TEXT, st.sampled_from(["EU", "CPT"])), max_size=6),
	mode=SPACED_MODES,
	numlan=NUMBER_LANGUAGES,
	roles=st.booleans(),
	wait=st.integers(1, 60),
	item=st.sampled_from([0, 10]),
)
def test_property_no_edge_at_an_utterance_end(env, sequence, mode, numlan, roles, wait, item):
	# P-E7 for utterances (review I1): what NVDA's speech manager sends the synth as one utterance,
	# up to an EndUtteranceCommand or a ConfigProfileTriggerCommand, never starts or ends with an
	# edge break, after every stage.
	commands = sys.modules["speech.commands"]
	makers = {"EU": commands.EndUtteranceCommand, "CPT": commands.ConfigProfileTriggerCommand}
	items = [makers[entry]() if entry in makers else entry for entry in sequence]
	result = every_stage(
		env,
		items,
		stage_settings(mode, wait=wait, item=item),
		context(env.module, numlan, roles),
	)
	utterances = [[]]
	for entry in result:
		if isinstance(entry, tuple(makers.values())):
			utterances.append([])
		else:
			utterances[-1].append(entry)
	for utterance in utterances:
		groups = runs(utterance)
		assert not any(is_edge(env, entry) for entry in (*groups[0], *groups[-1])), (sequence, result)


NUMBER_TOKENS = st.sampled_from(["3", "12", "3.5", "1 2", "12:30"])
WORD_TOKENS = st.text(alphabet="aZ共第章。 　", min_size=1, max_size=4)
# Items that join into the same numbers: a word, blank or not, between every two numbers.
TOKENS = st.builds(
	lambda pairs, last: [token for pair in pairs for token in pair if token is not None] + last,
	st.lists(st.tuples(st.one_of(st.none(), NUMBER_TOKENS), WORD_TOKENS), max_size=3),
	st.one_of(st.just([]), NUMBER_TOKENS.map(lambda token: [token])),
)


@SHARED_ENV
@given(
	items=TOKENS,
	mode=SPACED_MODES,
	size=st.integers(2, 10),
	numlan=NUMBER_LANGUAGES,
	wait=st.integers(1, 60),
	roles=st.booleans(),
)
def test_property_items_do_not_change_the_edges(env, items, mode, size, numlan, wait, roles):
	# P-E8 (fix/number-edge-pause-items): with no item wait, a number gets the same breaks whether
	# the text next to it is in its item or in another. Language commands make no sound, and
	# number_wait_factor strips each item, so whitespace is left out of the comparison.
	module = env.module
	run_settings = stage_settings(mode, size, wait)
	ctx = context(module, numlan, roles)

	def audible(sequence):
		result = []
		for entry in without_language(env, every_stage(env, sequence, run_settings, ctx)):
			if isinstance(entry, str):
				entry = "".join(entry.split())
				if not entry:
					continue
				if result and isinstance(result[-1], str):
					result[-1] += entry
					continue
			result.append(entry if isinstance(entry, str) else ("break", entry.time))
		return result

	assert audible(items) == audible(["".join(items)]), items


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
