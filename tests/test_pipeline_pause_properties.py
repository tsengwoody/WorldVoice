"""Properties of the number and punctuation pause stages, checked with Hypothesis.

The stages are pure functions of their arguments, so one pipeline module per test serves every
example: settings are fresh per example and no state carries over.
"""

import math
import re
import unicodedata
from itertools import pairwise
from types import SimpleNamespace

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from pipeline_harness import load_pipeline_module, load_settings_module, punctuation_settings, symbol_name

SHARED_ENV = settings(suppress_health_check=[HealthCheck.function_scoped_fixture])


@pytest.fixture
def env(monkeypatch):
	module, BreakCommand = load_pipeline_module(monkeypatch, punctuation_settings(0))
	return SimpleNamespace(module=module, BreakCommand=BreakCommand)


@pytest.fixture
def settings_module(monkeypatch):
	return load_settings_module(monkeypatch, {"WorldVoice": {"pipeline": {}}})


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
NUMBER_TEXT = st.text(
	alphabet="0123456789+-.,:/\u00d7\u00b0aZ共\uff0c\uff0e \t\n\r\u3000" + NO_BREAK_SPACES,
	max_size=20,
)


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


def run_group_mode(env, text, size, pause=0):
	stage_settings = punctuation_settings(0)
	stage_settings.number_mode = "group"
	stage_settings.group_size = size
	stage_settings.scaled_number_wait = lambda: pause
	return list(env.module.inject_number_mode([text], stage_settings, env.module.GENERIC_CONTEXT))


@SHARED_ENV
@given(
	sign=st.sampled_from(["", "+", "-"]),
	digits=st.text(alphabet="0123456789", min_size=1, max_size=30),
	size=st.integers(1, 10),
	pause=st.integers(0, 500),
)
def test_property_groups_are_separate_items_of_the_chosen_size(env, sign, digits, size, pause):
	result = run_group_mode(env, sign + digits, size, pause)

	texts, breaks = result[0::2], result[1::2]
	assert all(isinstance(item, str) for item in texts)
	assert all(isinstance(item, env.module.NumberBreakCommand) and item.time == pause for item in breaks)
	assert len(texts) == len(breaks) + 1
	assert len(breaks) == math.ceil(len(digits) / size) - 1
	assert "".join(texts) == sign + digits
	groups = [texts[0].removeprefix(sign), *texts[1:]]
	assert all(len(group) == size for group in groups[:-1])
	assert 1 <= len(groups[-1]) <= size
	if len(digits) <= size:
		assert result == [sign + digits]


@SHARED_ENV
@given(
	sign=st.sampled_from(["", "+", "-"]),
	digits=st.text(alphabet="0123456789", min_size=1, max_size=30),
	wait=st.integers(0, 500),
)
def test_property_digit_mode_separates_every_digit(env, sign, digits, wait):
	stage_settings = punctuation_settings(0)
	stage_settings.number_mode = "number"
	stage_settings.scaled_number_wait = lambda: wait
	result = list(env.module.inject_number_mode([sign + digits], stage_settings, env.module.GENERIC_CONTEXT))

	texts, breaks = result[0::2], result[1::2]
	assert all(isinstance(item, str) for item in texts)
	assert all(isinstance(item, env.module.NumberBreakCommand) and item.time == wait for item in breaks)
	assert len(breaks) == len(digits) - 1
	assert texts == [sign + digits[0], *digits[1:]]


# Number and group modes name each symbol (spec 6.4, P5-P7)

MODE_SIZES = st.sampled_from([("number", 1), *(("group", size) for size in range(2, 11))])


def run_number_mode(env, text, mode, size):
	stage_settings = punctuation_settings(0)
	stage_settings.number_mode = mode
	stage_settings.group_size = size
	return list(env.module.inject_number_mode([text], stage_settings, env.module.GENERIC_CONTEXT))


def symbol_of_name(env):
	"""The harness's name of each number symbol, in GENERIC_CONTEXT's locale, back to the symbol."""
	return {symbol_name("en", symbol): symbol for symbol in env.module._SYMBOLS}


@SHARED_ENV
@given(text=NUMBER_TEXT, mode_size=MODE_SIZES)
def test_property_number_modes_keep_the_text(env, text, mode_size):
	# P5: with each name read back as its symbol, the text is the input; only the dot rule adds spaces.
	symbols = symbol_of_name(env)
	result = run_number_mode(env, text, *mode_size)
	texts = [symbols.get(item, item) for item in result if isinstance(item, str)]
	assert "".join(texts).replace(" ", "") == text.replace(" ", "")


@SHARED_ENV
@given(text=NUMBER_TEXT, mode_size=MODE_SIZES)
def test_property_no_digit_run_is_longer_than_the_size(env, text, mode_size):
	# P6
	size = mode_size[1]
	for item in run_number_mode(env, text, *mode_size):
		if isinstance(item, str):
			assert all(len(run) <= size for run in re.findall(r"[0-9]+", item)), (text, item)


@SHARED_ENV
@given(text=NUMBER_TEXT, mode_size=MODE_SIZES)
def test_property_breaks_and_names_stay_inside_numbers(env, text, mode_size):
	# P7: a break sits between two pieces of one number; a name has a break on each side; every
	# symbol inside a number, and only those, is named.
	symbols = symbol_of_name(env)
	result = run_number_mode(env, text, *mode_size)
	is_break = lambda item: isinstance(item, env.module.NumberBreakCommand)
	for index, item in enumerate(result):
		if is_break(item):
			assert 0 < index < len(result) - 1, (text, result)
			before, after = result[index - 1], result[index + 1]
			assert before in symbols or before[-1] in DIGITS, (text, result)
			assert after in symbols or after[0] in DIGITS, (text, result)
		elif item in symbols:
			assert is_break(result[index - 1]) and is_break(result[index + 1]), (text, result)
	# A leading sign belongs to the first piece, so it is not named.
	inside = [
		c
		for match in env.module._NUMBER_RE.finditer(text)
		for c in match.group().removeprefix("+").removeprefix("-")
		if is_number_symbol(c)
	]
	assert sorted(symbols[item] for item in result if item in symbols) == sorted(inside), (text, result)


# One number definition (spec 6.1)

DIGITS = "0123456789"


def is_number_symbol(character):
	return ord(character) < 0x100 and unicodedata.category(character)[0] in "PS"


def scanned_numbers(text):
	"""The spans of spec Q1-Q3, scanned by hand: an optional sign that is right before a digit and
	not right after one, digits, then any number of (one or more symbols, then digits).
	"""
	spans = []
	position = 0
	while position < len(text):
		start = position
		signed = (
			text[position] in "+-"
			and position + 1 < len(text)
			and text[position + 1] in DIGITS
			and (position == 0 or text[position - 1] not in DIGITS)
		)
		if not signed and text[position] not in DIGITS:
			position += 1
			continue
		end = position + 1 if signed else position
		while end < len(text) and text[end] in DIGITS:
			end += 1
		while True:
			after_symbols = end
			while after_symbols < len(text) and is_number_symbol(text[after_symbols]):
				after_symbols += 1
			if after_symbols == end or after_symbols == len(text) or text[after_symbols] not in DIGITS:
				break
			end = after_symbols
			while end < len(text) and text[end] in DIGITS:
				end += 1
		spans.append((start, end))
		position = end
	return spans


@SHARED_ENV
@given(text=NUMBER_TEXT)
def test_property_number_re_equals_the_scanner(env, text):
	assert [match.span() for match in env.module._NUMBER_RE.finditer(text)] == scanned_numbers(text)


@SHARED_ENV
@given(text=NUMBER_TEXT)
def test_property_matches_are_never_glued(env, text):
	matches = list(env.module._NUMBER_RE.finditer(text))
	assert all(left.end() < right.start() for left, right in pairwise(matches)), text


# The "off" number mode (V3)


@SHARED_ENV
@given(data=st.data())
def test_property_off_mode_is_the_identity_for_both_number_stages(env, data):
	sequence = data.draw(st.lists(st.one_of(NUMBER_TEXT, st.builds(lambda: env.BreakCommand(5))), max_size=6))
	stage_settings = punctuation_settings(0)
	stage_settings.number_mode = "none"
	stage_settings.group_size = data.draw(st.integers(2, 10))
	for stage in (env.module.remove_thousands_separators, env.module.inject_number_mode):
		result = list(stage(sequence, stage_settings, env.module.GENERIC_CONTEXT))
		assert len(result) == len(sequence)
		assert all(after is before for after, before in zip(result, sequence))


# Value-mode thousands separators (spec 6.3, V1)

WHOLE_THOUSANDS_RUN = re.compile(r"[0-9]{1,3}(?:,[0-9]{3})+")


def without_valid_thousands_separators(text):
	"""Spec 6.3's oracle: each maximal [0-9,] run, trailing commas aside, loses its commas only
	when the whole of it is a valid thousands run.
	"""

	def replace(match):
		run = match.group()
		body = run.rstrip(",")
		if WHOLE_THOUSANDS_RUN.fullmatch(body):
			return body.replace(",", "") + run[len(body) :]
		return run

	return re.sub(r"[0-9,]+", replace, text)


@SHARED_ENV
@given(text=st.text(alphabet="0123456789,.a -", max_size=20))
def test_property_thousands_removal_equals_the_whole_run_oracle(env, text):
	stage_settings = punctuation_settings(0)
	result = list(env.module.remove_thousands_separators([text], stage_settings, env.module.GENERIC_CONTEXT))
	assert result == [without_valid_thousands_separators(text)]


# The number split


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
def test_property_every_whitespace_gap_between_numbers_gets_one_break(env, text):
	# Decided by the user (2026-10-22): any whitespace, a no-break space included, pairs two numbers.
	result, stripped = split_once(env, text)
	matches = list(env.module._NUMBER_RE.finditer(stripped))
	gaps = [stripped[left.end() : right.start()] for left, right in pairwise(matches)]
	assert sum(not isinstance(item, str) for item in result) == sum(gap.isspace() for gap in gaps), (
		text,
		result,
	)


@SHARED_ENV
@given(text=NUMBER_TEXT)
def test_property_no_text_item_keeps_two_numbers_apart_by_whitespace(env, text):
	result, _stripped = split_once(env, text)
	for item in result:
		if not isinstance(item, str):
			continue
		matches = list(env.module._NUMBER_RE.finditer(item))
		for left, right in pairwise(matches):
			gap = item[left.end() : right.start()]
			assert not gap.isspace(), (item, gap)


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


# Settings (S1)


@SHARED_ENV
@given(data=st.data())
def test_property_int_convert_is_bounded_and_idempotent(settings_module, data):
	spec = data.draw(
		st.sampled_from([spec for spec in settings_module.PIPELINE_SETTINGS if spec.kind is int]),
	)
	result = spec.convert(data.draw(st.integers(-1000, 1000)))
	assert spec.min_value <= result <= spec.max_value
	assert spec.convert(result) == result


@SHARED_ENV
@given(
	value=st.one_of(
		st.text(max_size=8),
		st.sampled_from(["value", "number", "group", "pair"]),
		st.none(),
		st.integers(),
	),
)
def test_property_number_mode_normalisation_is_closed_and_idempotent(settings_module, value):
	spec = settings_module.PIPELINE_SETTING_BY_KEY["number_mode"]
	result = spec.convert(value)
	assert result in settings_module.NUMBER_MODES
	assert spec.convert(result) == result


# No stacked breaks (X1)


@SHARED_ENV
@given(data=st.data())
def test_property_number_and_group_breaks_never_touch_another_break(env, data):
	"""After the pause stages, a digit or group break never has another break next to it.

	Two item breaks around a blank item may still meet (spec F7), so only the new classes are checked.
	"""
	sequence = data.draw(st.lists(st.text(alphabet="0123456789 a.,-", max_size=12), max_size=6))
	stage_settings = punctuation_settings(data.draw(st.integers(0, 300)))
	stage_settings.number_mode = data.draw(st.sampled_from(["value", "number", "group"]))
	stage_settings.group_size = data.draw(st.integers(1, 10))
	number_wait, item_wait = (data.draw(st.integers(0, 60)) for _ in range(2))
	stage_settings.scaled_number_wait = lambda: number_wait
	stage_settings.scaled_item_wait = lambda: item_wait
	module, context = env.module, env.module.GENERIC_CONTEXT
	result = sequence
	for stage in (
		module.inject_number_mode,
		module.inject_chinese_space_pause,
		module.item_wait_factor,
		module.inject_punctuation_pause,
		module.number_wait_factor,
	):
		result = list(stage(result, stage_settings, context))

	new_breaks = (module.NumberBreakCommand,)
	for before, after in pairwise(result):
		if isinstance(before, new_breaks) or isinstance(after, new_breaks):
			assert not (isinstance(before, env.BreakCommand) and isinstance(after, env.BreakCommand)), result
