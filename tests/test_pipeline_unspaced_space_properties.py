"""Properties of the unspaced script space pause (unspaced-script-space-pause spec §8.3, P1 to P5), with Hypothesis.

The stage is a pure function of its arguments, so one pipeline module per test serves every example.
"""

import re
from types import SimpleNamespace

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from pipeline_harness import load_pipeline_module, punctuation_settings

SHARED_ENV = settings(suppress_health_check=[HealthCheck.function_scoped_fixture])

# Han (basic, Extension A, Extension B), kana and the prolonged sound marks, Thai, Hangul, Latin, a digit,
# CJK punctuation, two Inherited marks, a Bopomofo tone mark, a parenthesized ideograph, and whitespace.
TEXT = st.text(alphabet="中㐀\U00020000かカーｰก한a1。゙́ˇ㈱ \n　 ", max_size=16)
WHITESPACE = re.compile(r"\s+")
# Today's rule, kept as an oracle: a run between two ideographs of U+4E00-U+9FA5.
HAN_RULE = re.compile(r"(?<=[一-龥])\s+(?=[一-龥])")


class Marker:
	"""A speech command no stage knows, such as NVDA's IndexCommand."""


@pytest.fixture
def env(monkeypatch):
	module, BreakCommand = load_pipeline_module(monkeypatch, punctuation_settings(0))
	return SimpleNamespace(module=module, BreakCommand=BreakCommand)


def run(env, sequence, wait):
	stage_settings = SimpleNamespace(scaled_unspaced_script_space_wait=lambda: wait)
	return list(
		env.module.inject_unspaced_script_space_pause(sequence, stage_settings, env.module.GENERIC_CONTEXT),
	)


def replaced_runs(env, text, output):
	"""The (start, end) of each whitespace run of *text* that a break of *output* stands for.

	Asserts P1 on the way: the output's text and runs put back give *text*, and each break stands for a
	whole maximal run.
	"""
	runs, pos = [], 0
	for item in output:
		if isinstance(item, str):
			assert item and text.startswith(item, pos), (text, output)
			pos += len(item)
		else:
			assert isinstance(item, env.BreakCommand), item
			match = WHITESPACE.match(text, pos)
			assert match and (pos == 0 or not WHITESPACE.match(text[pos - 1])), (text, output)
			runs.append(match.span())
			pos = match.end()
	assert pos == len(text), (text, output)
	return runs


def may_pause(env, text, start, end):
	"""The spec's condition (§4.1): an unspaced left base, skipping Inherited marks, and an unspaced right neighbour."""
	base = start - 1
	while base >= 0 and env.module.get_script(ord(text[base])) == "Inherited":
		base -= 1
	return (
		base >= 0
		and end < len(text)
		and env.module._is_unspaced(text[base])
		and env.module._is_unspaced(text[end])
	)


def plain(env, item):
	"""A break as its time, so the breaks of two stage calls compare equal; anything else as itself."""
	return ("break", item.time) if isinstance(item, env.BreakCommand) else item


@SHARED_ENV
@given(text=TEXT, wait=st.integers(1, 60))
def test_property_text_is_kept(env, text, wait):
	replaced_runs(env, text, run(env, [text], wait))


@SHARED_ENV
@given(text=TEXT, wait=st.integers(1, 60))
def test_property_no_pause_next_to_a_spaced_character(env, text, wait):
	output = run(env, [text], wait)
	assert all(may_pause(env, text, start, end) for start, end in replaced_runs(env, text, output))
	if not any(env.module._is_unspaced(character) for character in text):
		assert output == ([text] if text else [])


@SHARED_ENV
@given(text=TEXT, wait=st.integers(1, 60))
def test_property_superset_of_the_han_rule(env, text, wait):
	runs = replaced_runs(env, text, run(env, [text], wait))
	assert {match.span() for match in HAN_RULE.finditer(text)} <= set(runs)


@SHARED_ENV
@given(sequence=st.lists(st.one_of(TEXT, st.builds(Marker)), max_size=6), wait=st.integers(-5, 0))
def test_property_off_is_identity(env, sequence, wait):
	result = run(env, sequence, wait)
	assert len(result) == len(sequence) and all(out is item for out, item in zip(result, sequence))


@SHARED_ENV
@given(sequence=st.lists(st.one_of(TEXT, st.builds(Marker)), max_size=6), wait=st.integers(1, 60))
def test_property_commands_pass_through(env, sequence, wait):
	result = run(env, sequence, wait)
	markers = [item for item in sequence if isinstance(item, Marker)]
	assert [item for item in result if isinstance(item, Marker)] == markers
	assert all(sum(item is marker for item in result) == 1 for marker in markers)
	# Each item's own output, in order, is the whole output: a break never joins two items, and has
	# text of its own item on both sides.
	per_item = [run(env, [item], wait) for item in sequence]
	assert [plain(env, item) for piece in per_item for item in piece] == [plain(env, item) for item in result]
	for piece in per_item:
		breaks = [index for index, item in enumerate(piece) if isinstance(item, env.BreakCommand)]
		assert all(0 < index < len(piece) - 1 for index in breaks)
		assert all(
			isinstance(piece[index - 1], str) and isinstance(piece[index + 1], str) for index in breaks
		)
