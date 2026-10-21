"""Properties of the number and punctuation pause stages, checked with Hypothesis.

The stages are pure functions of their arguments, so one pipeline module per test serves every
example: settings are fresh per example and no state carries over.
"""

import math
from itertools import pairwise
from types import SimpleNamespace

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from pipeline_harness import load_pipeline_module, punctuation_settings

SHARED_ENV = settings(suppress_health_check=[HealthCheck.function_scoped_fixture])


@pytest.fixture
def env(monkeypatch):
	module, BreakCommand = load_pipeline_module(monkeypatch, punctuation_settings(0))
	return SimpleNamespace(module=module, BreakCommand=BreakCommand)


def shape(sequence):
	return [item if isinstance(item, str) else (type(item).__name__, item.time) for item in sequence]


# Punctuation

MARKS = ".,"


def punctuation_sequences(env):
	"""Text over letters, a digit, spaces and marks (two configured, one not), between existing breaks."""
	text = st.text(alphabet="ab1 .,;", max_size=12)
	existing = st.builds(lambda: env.BreakCommand(30))
	return st.lists(st.one_of(text, existing), max_size=6)


def run_punctuation(env, sequence, *, enabled=True, characters=MARKS, remove=False, wait=0):
	stage_settings = punctuation_settings(wait, remove_characters=remove)
	stage_settings.punctuation_pause_enabled = enabled
	stage_settings.punctuation_pause_characters = characters
	return list(env.module.inject_punctuation_pause(sequence, stage_settings, env.module.GENERIC_CONTEXT))


def is_punctuation_break(env, item):
	return isinstance(item, env.module.PunctuationBreakCommand)


def is_existing_break(env, item):
	return isinstance(item, env.BreakCommand) and not is_punctuation_break(env, item)


@SHARED_ENV
@given(data=st.data())
def test_property_a_disabled_switch_changes_nothing(env, data):
	sequence = data.draw(punctuation_sequences(env))
	result = run_punctuation(
		env,
		sequence,
		enabled=False,
		characters=data.draw(st.sampled_from(["", " ", MARKS, ".,;"])),
		remove=data.draw(st.booleans()),
		wait=data.draw(st.integers(0, 500)),
	)
	assert len(result) == len(sequence)
	assert all(after is before for after, before in zip(result, sequence))


@SHARED_ENV
@given(data=st.data())
def test_property_the_wait_changes_only_the_break_time(env, data):
	sequence = data.draw(punctuation_sequences(env))
	remove = data.draw(st.booleans())
	wait = data.draw(st.integers(1, 500))
	at_zero = shape(run_punctuation(env, sequence, remove=remove, wait=0))
	at_wait = shape(run_punctuation(env, sequence, remove=remove, wait=wait))
	zero_break = ("PunctuationBreakCommand", 0)
	assert [("PunctuationBreakCommand", wait) if item == zero_break else item for item in at_zero] == at_wait


def chunks(sequence):
	"""The commands of *sequence*, and the joined text before, between and after them."""
	commands, texts, current = [], [], ""
	for item in sequence:
		if isinstance(item, str):
			current += item
		else:
			commands.append((type(item).__name__, item.time))
			texts.append(current)
			current = ""
	texts.append(current)
	return commands, texts


def without_some_marks(shorter, longer):
	"""True when *shorter* is *longer* with some configured marks deleted."""
	position = 0
	for character in longer:
		if position < len(shorter) and shorter[position] == character:
			position += 1
		elif character not in MARKS:
			return False
	return position == len(shorter)


@SHARED_ENV
@given(data=st.data())
def test_property_removal_changes_only_the_marks(env, data):
	sequence = data.draw(punctuation_sequences(env))
	kept = run_punctuation(env, sequence, remove=False)
	removed = run_punctuation(env, sequence, remove=True)

	text = "".join(item for item in sequence if isinstance(item, str))
	assert "".join(item for item in kept if isinstance(item, str)) == text
	kept_commands, kept_texts = chunks(kept)
	removed_commands, removed_texts = chunks(removed)
	# The same breaks, in the same order, with the same text around them.
	assert removed_commands == kept_commands
	assert all(without_some_marks(short, long) for short, long in zip(removed_texts, kept_texts))


def ends_with_a_mark(item):
	return isinstance(item, str) and item.rstrip()[-1:] in tuple(MARKS)


def is_non_blank(item):
	return isinstance(item, str) and bool(item.strip())


def with_suppressed_pauses_restored(env, sequence, result, wait):
	"""
	*result* with each run of existing breaks in *sequence* replaced by the boundary pause it
	suppressed: one punctuation break when the item before the run ends with a mark and non-blank
	text follows the run, else nothing.
	"""
	restored = {}
	for index, item in enumerate(sequence):
		if not is_existing_break(env, item) or (index and is_existing_break(env, sequence[index - 1])):
			continue
		end = index
		while end < len(sequence) and is_existing_break(env, sequence[end]):
			end += 1
		before = sequence[index - 1] if index else None
		after = sequence[end] if end < len(sequence) else None
		suppressed = ends_with_a_mark(before) and is_non_blank(after)
		restored[id(item)] = [("PunctuationBreakCommand", wait)] if suppressed else []
	expected = []
	for item in result:
		if is_existing_break(env, item):
			expected += restored.get(id(item), [])
		else:
			expected += shape([item])
	return expected


@SHARED_ENV
@given(data=st.data())
def test_property_an_existing_break_suppresses_only_the_boundary_pause_before_it(env, data):
	"""
	Taking the existing breaks out of the input brings back exactly the boundary pauses they
	suppressed and changes nothing else. A mark that opens the item after a break is an internal
	pause point (spec item 2-7), so ["a", existing, ". b"] still gives "a", existing, ".", PuB, " b".
	"""
	sequence = data.draw(punctuation_sequences(env))
	remove = data.draw(st.booleans())
	wait = data.draw(st.integers(0, 500))
	result = run_punctuation(env, sequence, remove=remove, wait=wait)
	plain = [item for item in sequence if not is_existing_break(env, item)]
	without_breaks = run_punctuation(env, plain, remove=remove, wait=wait)
	assert shape(without_breaks) == with_suppressed_pauses_restored(env, sequence, result, wait)


@SHARED_ENV
@given(data=st.data())
def test_property_a_punctuation_break_never_ends_the_output_or_sits_next_to_an_existing_one_when_marks_stay(
	env,
	data,
):
	"""
	"Next to" means directly beside it in the output. Text that is only marks can still sit between
	the two, as in ["a", existing, ". b"] or [".", ".", existing, "1"]; see the property above.
	"""
	sequence = data.draw(punctuation_sequences(env))
	remove = data.draw(st.booleans())
	result = run_punctuation(env, sequence, remove=remove, wait=data.draw(st.integers(0, 500)))

	assert not (result and is_punctuation_break(env, result[-1]))
	if remove:
		# Removal can drop all the text between the two breaks: an item that starts with a mark
		# at a pause point, or that is only marks, as in [".", ".", existing, "1"]. The
		# pause-point rules keep that (spec item 2-7).
		return
	for before, after in pairwise(result):
		assert not (is_punctuation_break(env, before) and is_existing_break(env, after))
		assert not (is_existing_break(env, before) and is_punctuation_break(env, after))


@SHARED_ENV
@given(data=st.data())
def test_property_an_empty_or_blank_list_changes_nothing(env, data):
	sequence = data.draw(punctuation_sequences(env))
	result = run_punctuation(
		env,
		sequence,
		characters=data.draw(st.sampled_from(["", " ", "\t "])),
		remove=data.draw(st.booleans()),
		wait=data.draw(st.integers(0, 500)),
	)
	assert len(result) == len(sequence)
	assert all(after is before for after, before in zip(result, sequence))


# Numbers

NO_BREAK_SPACES = "\u00a0\u202f\u2007"
NUMBER_TEXT = st.text(alphabet="0123456789+-.aZ共 \t\n\r\u3000" + NO_BREAK_SPACES, max_size=20)


def run_number_wait(env, sequence, wait):
	stage_settings = punctuation_settings(0)
	stage_settings.scaled_number_wait = lambda: wait
	return list(env.module.number_wait_factor(sequence, stage_settings, env.module.GENERIC_CONTEXT))


@SHARED_ENV
@given(data=st.data())
def test_property_zero_number_wait_changes_nothing(env, data):
	sequence = data.draw(st.lists(st.one_of(NUMBER_TEXT, st.builds(lambda: env.BreakCommand(5))), max_size=6))
	result = run_number_wait(env, sequence, data.draw(st.integers(-5, 0)))
	assert len(result) == len(sequence)
	assert all(after is before for after, before in zip(result, sequence))


@SHARED_ENV
@given(
	sign=st.sampled_from(["", "+", "-"]),
	digits=st.text(alphabet="0123456789", min_size=3, max_size=20),
	pause=st.integers(0, 500),
)
def test_property_pairs_are_separate_items_at_any_pause(env, sign, digits, pause):
	stage_settings = punctuation_settings(0)
	stage_settings.number_mode = "pair"
	stage_settings.scaled_pair_wait = lambda: pause
	result = list(env.module.inject_number_mode([sign + digits], stage_settings, env.module.GENERIC_CONTEXT))

	texts, breaks = result[0::2], result[1::2]
	assert all(isinstance(item, str) for item in texts)
	assert all(isinstance(item, env.module.PairNumberBreakCommand) and item.time == pause for item in breaks)
	assert len(texts) == len(breaks) + 1
	assert len(breaks) == math.ceil(len(digits) / 2) - 1
	assert "".join(texts) == sign + digits


# The number split (F1 option B: a number glued to another with no gap is never split out)

DIGITS = "0123456789"


def split_once(env, text):
	"""number_wait_factor at 40 ms on one string, and the string as the stage sees it."""
	return run_number_wait(env, [text], 40), text.strip()


def walk(result, stripped):
	"""Match the output against the stripped input: each text item is the next slice of it and
	each break takes the whitespace run that follows. Returns the text each break took.
	"""
	taken = {}
	position = 0
	for index, item in enumerate(result):
		if isinstance(item, str):
			assert stripped.startswith(item, position), (stripped, result)
			position += len(item)
		else:
			end = position
			while end < len(stripped) and stripped[end].isspace():
				end += 1
			taken[index] = stripped[position:end]
			position = end
	assert position == len(stripped), (stripped, result)
	return taken


@SHARED_ENV
@given(text=NUMBER_TEXT)
def test_property_the_split_keeps_the_text_and_replaces_only_whitespace(env, text):
	result, stripped = split_once(env, text)
	assert all(walk(result, stripped).values()), "every break must replace whitespace"


@SHARED_ENV
@given(text=NUMBER_TEXT)
def test_property_no_break_replaces_a_gap_with_a_no_break_space(env, text):
	# A no-break space groups digits, as in "10 000", so it never joins two numbers (decided by the user).
	result, stripped = split_once(env, text)
	for gap in walk(result, stripped).values():
		assert not any(space in gap for space in NO_BREAK_SPACES), (text, result)


@SHARED_ENV
@given(text=NUMBER_TEXT)
def test_property_no_text_item_keeps_two_numbers_apart_by_whitespace(env, text):
	result, _stripped = split_once(env, text)
	for item in result:
		if not isinstance(item, str):
			continue
		matches = list(env.module._NUMBER_RE.finditer(item))
		gaps = [item[left.end() : right.start()] for left, right in pairwise(matches)]
		for index, gap in enumerate(gaps):
			if not gap.isspace() or any(space in gap for space in NO_BREAK_SPACES):
				continue
			# Either number is glued to its other neighbour, so neither is split out.
			left_glued = index > 0 and not gaps[index - 1]
			right_glued = index + 1 < len(gaps) and not gaps[index + 1]
			assert left_glued or right_glued, (item, gap)


@SHARED_ENV
@given(text=NUMBER_TEXT)
def test_property_no_digits_are_glued_together(env, text):
	result, _stripped = split_once(env, text)
	for before, after in pairwise(result):
		if isinstance(before, str) and isinstance(after, str):
			assert not (before[-1] in DIGITS and after[0] in DIGITS)


@SHARED_ENV
@given(text=NUMBER_TEXT)
def test_property_breaks_sit_exactly_between_whole_numbers(env, text):
	result, _stripped = split_once(env, text)
	number = env.module._NUMBER_RE.fullmatch
	breaks = [item for item in result if not isinstance(item, str)]
	assert all(item is breaks[0] for item in breaks)
	for index, item in enumerate(result):
		if not isinstance(item, str):
			assert 0 < index < len(result) - 1
			assert number(result[index - 1]) and number(result[index + 1])
	for before, after in pairwise(result):
		if isinstance(before, str) and isinstance(after, str):
			assert not (number(before) and number(after))


@SHARED_ENV
@given(text=NUMBER_TEXT)
def test_property_leftover_text_is_never_a_number(env, text):
	# A text item that is a whole number was split out at whitespace: a break that took
	# whitespace is next to it. The only other way is the input itself being that number.
	result, stripped = split_once(env, text)
	if result == ([stripped] if stripped else []):
		return
	taken = walk(result, stripped)
	for index, item in enumerate(result):
		if isinstance(item, str) and env.module._NUMBER_RE.fullmatch(item):
			assert taken.get(index - 1) or taken.get(index + 1), (text, result)
