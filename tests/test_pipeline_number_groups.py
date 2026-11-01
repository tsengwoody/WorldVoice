"""The group size, independent of the number mode (feat/number-group-independent spec §4, §9).

Decided by the user (2026-11-01, U1, U2): the group size cuts the digit runs of a number into
pieces, in every number mode, and the number mode renders each piece.
"""

import re
from types import SimpleNamespace

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from pipeline_harness import load_pipeline_module, punctuation_settings, read_back_names, symbol_name

SHARED_ENV = settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
MODES = ("none", "value", "number")


def N(symbol):
	"""The harness's name of a symbol for text in zh."""
	return symbol_name("zh", symbol)


def name_of(symbol):
	"""The namer of the tests: NVDA has no name for "×" here, so it stays as it is."""
	return None if symbol == "×" else N(symbol)


@pytest.fixture
def env(monkeypatch):
	module, BreakCommand = load_pipeline_module(monkeypatch, punctuation_settings(0))
	return SimpleNamespace(module=module, numbers=module.numbers, BreakCommand=BreakCommand)


# Spec §9.2 "Pieces": (raw, size, none, value, number); the "none" column is the cut.
PIECES = [
	pytest.param("123456", 0, ["123456"], ["123456"], ["1 2 3 4 5 6"], id="six-0"),
	pytest.param("123456", 3, ["123", "456"], ["123", "456"], ["1 2 3", "4 5 6"], id="six-3"),
	pytest.param("-1234", 3, ["-123", "4"], ["-123", "4"], ["-1 2 3", "4"], id="sign"),
	pytest.param("+0012", 3, ["+001", "2"], ["+001", "2"], ["+0 0 1", "2"], id="plus-zeros"),
	pytest.param("12.5", 0, ["12.5"], ["12.5"], [f"1 2 {N('.')} 5"], id="dot-0"),
	pytest.param("12.5", 2, ["12", ".", "5"], ["12", N("."), "5"], ["1 2", N("."), "5"], id="dot-2"),
	pytest.param(
		"1.,2",
		1,
		["1", ".", ",", "2"],
		["1", N("."), N(","), "2"],
		["1", N("."), N(","), "2"],
		id="two-symbols",
	),
	pytest.param(
		"１２３４５",
		3,
		["１２３", "４５"],
		["１２３", "４５"],
		["１ ２ ３", "４ ５"],
		id="full-width",
	),
	pytest.param("5×3", 1, ["5", "×", "3"], ["5", "×", "3"], ["5", "×", "3"], id="no-name"),
	pytest.param("123", 2**31 - 1, ["123"], ["123"], ["1 2 3"], id="largest-size"),
]


@pytest.mark.parametrize(("raw", "size", "cut", "value", "number"), PIECES)
def test_group_pieces_cuts_digit_runs_and_symbols(env, raw, size, cut, value, number):
	assert env.numbers.group_pieces(raw, size) == cut


@pytest.mark.parametrize(("raw", "size"), [("1,234.5", 0), ("-12", -1), ("7", 0)])
def test_group_pieces_of_size_zero_is_the_whole_match(env, raw, size):
	assert env.numbers.group_pieces(raw, size) == [raw]


@pytest.mark.parametrize(
	("piece", "mode", "expected"),
	[
		("123", "none", "123"),
		(".", "none", "."),
		(".", "value", N(".")),
		("×", "value", "×"),
		("123", "value", "123"),
		("12.5", "value", "12.5"),
		("-123", "number", "-1 2 3"),
		("12.5", "number", f"1 2 {N('.')} 5"),
		("×", "number", "×"),
		("１２３", "number", "１ ２ ３"),
	],
)
def test_render_piece_by_mode(env, piece, mode, expected):
	assert env.numbers.render_piece(piece, mode, name_of) == expected


DIGITS = st.text(alphabet="0123456789１２٣", min_size=1, max_size=8)
SYMBOL_RUNS = st.text(alphabet=".,:-+×/", min_size=1, max_size=2)
# A NUMBER_RE match: an optional sign, digits, then any number of (symbols, digits).
RAW_NUMBERS = st.builds(
	lambda sign, first, rest: sign + first + "".join(symbols + digits for symbols, digits in rest),
	st.sampled_from(["", "+", "-"]),
	DIGITS,
	st.lists(st.tuples(SYMBOL_RUNS, DIGITS), max_size=3),
)


def is_digit_piece(piece):
	return any(character.isdecimal() for character in piece)


@SHARED_ENV
@given(raw=RAW_NUMBERS, size=st.integers(0, 12))
def test_property_cut_pieces_join_back_and_hold_at_most_n_digits(env, raw, size):
	# P-G1: the pieces join to the match; digit pieces of a run hold n digits, the last 1..n; a
	# symbol is a piece of its own; size 0 keeps the match whole.
	assert env.numbers.NUMBER_RE.fullmatch(raw)
	pieces = env.numbers.group_pieces(raw, size)
	assert "".join(pieces) == raw
	if size == 0:
		assert pieces == [raw]
		return
	runs, current = [], []
	for piece in pieces:
		if is_digit_piece(piece):
			current.append(piece.lstrip("+-"))
			continue
		assert len(piece) == 1 and piece in env.numbers.SYMBOLS, (raw, pieces)
		if current:
			runs.append(current)
		current = []
	runs.append(current)
	for run in runs:
		assert all(len(piece) == size for piece in run[:-1]), (raw, pieces)
		assert 1 <= len(run[-1]) <= size, (raw, pieces)


@SHARED_ENV
@given(raw=RAW_NUMBERS, size=st.integers(0, 12))
def test_property_render_keeps_the_digits_and_names_the_symbols(env, raw, size):
	# P-G2: "none" keeps each piece; "value" names symbol pieces only; "number" reads the digits
	# one by one with single spaces, and names every symbol.
	numbers = env.numbers
	names = {N(symbol): symbol for symbol in numbers.SYMBOLS}
	for piece in numbers.group_pieces(raw, size):
		assert numbers.render_piece(piece, "none", name_of) == piece
		value = numbers.render_piece(piece, "value", name_of)
		assert value == (piece if is_digit_piece(piece) else (name_of(piece) or piece))
		number = numbers.render_piece(piece, "number", name_of)
		assert read_back_names(number, names).replace(" ", "") == piece, (piece, number)
		assert not re.search(r"\d\d", number) and "  " not in number, (piece, number)
		assert number == number.strip(), (piece, number)


@pytest.mark.parametrize(("raw", "size", "cut", "value", "number"), PIECES)
def test_number_pieces_by_mode_and_size(env, raw, size, cut, value, number):
	# Spec §4.1: number_pieces keeps its signature; it cuts by the size, then renders by the mode.
	pieces = env.numbers.number_pieces
	assert [pieces(raw, mode, size, name_of) for mode in MODES] == [cut, value, number]


class Marker:
	"""A speech command no stage knows, such as NVDA's IndexCommand."""


def stage_settings(mode, size, wait=10, item=0, chars=""):
	return SimpleNamespace(
		number_mode=mode,
		scope="WorldVoice",
		punctuation_pause_characters=chars,
		punctuation_pause_enabled=bool(chars),
		remove_punctuation_characters=False,
		scaled_item_wait=lambda: item,
		scaled_number_wait=lambda: wait,
		scaled_unspaced_script_space_wait=lambda: 0,
		scaled_punctuation_wait=lambda: 50,
		group_size=size,
	)


def context(module, numlan="default"):
	return module.SpeechContext(
		supports_roles=True,
		language="zh",
		number_language=numlan,
		default_voice_name="Z",
		default_voice_language="zh",
		voice_name_for_language={"zh": "Z", "en": "E"}.get,
	)


def shape(env, sequence):
	module = env.module
	commands = __import__("sys").modules["speech.commands"]
	result = []
	for item in sequence:
		if isinstance(item, str):
			result.append(item)
		elif isinstance(item, module.NumberEdgeBreakCommand):
			result.append(("E", item.time))
		elif isinstance(item, module.NumberBreakCommand):
			result.append(("NB", item.time))
		elif isinstance(item, env.BreakCommand):
			result.append(("B", item.time))
		elif isinstance(item, commands.EndUtteranceCommand):
			result.append("EU")
		elif hasattr(item, "lang"):
			result.append(("L", item.lang))
		else:
			result.append(item)
	return result


def every_stage(env, sequence, settings, ctx):
	for stage in env.module.STAGES:
		sequence = list(stage.fn(sequence, settings, ctx))
	return sequence


E, NB, NB0 = ("E", 10), ("NB", 10), ("NB", 0)


def test_off_without_groups_or_wrapper_is_the_identity(env):
	# Spec §4.3 "Pass-through": off with a group size of 0 leaves the sequence as it is.
	sequence = ["第1,234.5章", Marker(), "10 20"]
	result = list(env.module.inject_numbers(sequence, stage_settings("none", 0), context(env.module)))
	assert len(result) == len(sequence) and all(a is b for a, b in zip(result, sequence, strict=True))


def test_off_with_a_group_size_runs_the_stage(env):
	# Decided by the user (2026-11-01, U2): off groups too, and leaves the pieces as they are.
	result = env.module.inject_numbers(["1234"], stage_settings("none", 3), context(env.module))
	assert shape(env, result) == ["123", NB, "4"]


@pytest.mark.parametrize("text", ["第1,234.5章", "a 10 20 b", "1.,2", "COVID-19"])
def test_value_without_groups_does_not_depend_on_the_pause(env, text):
	# U8: value mode with a group size of 0 is today's output, with no break at any pause.
	ctx = context(env.module)
	results = [
		shape(env, env.module.inject_numbers([text], stage_settings("value", 0, wait), ctx))
		for wait in (0, 10)
	]
	assert results[0] == results[1]
	assert all(isinstance(item, str) for item in results[0])


@pytest.mark.parametrize("wait", [0, 10])
@pytest.mark.parametrize("size", [0, 3])
@pytest.mark.parametrize("mode", MODES)
def test_edges_appear_iff_a_group_and_a_pause(env, mode, size, wait):
	# Decided by the user (2026-11-01, U4): the edge pause follows the group size, whatever the mode.
	module = env.module
	result = list(module.inject_numbers(["第123章"], stage_settings(mode, size, wait), context(module)))
	edges = [item for item in result if isinstance(item, module.NumberEdgeBreakCommand)]
	assert len(edges) == (2 if size and wait else 0), result


@pytest.mark.parametrize("space", [" ", "  ", " ", "　"], ids=["space", "two", "nbsp", "ideographic"])
@pytest.mark.parametrize("size", [0, 3])
@pytest.mark.parametrize(
	("mode", "first", "second"),
	[("none", "10", "20"), ("value", "10", "20"), ("number", "1 0", "2 0")],
)
def test_numbers_that_only_whitespace_separates_get_one_break(env, mode, first, second, size, space):
	# U5, G1: one break of the number pause, in every mode and with any group size; number mode's own
	# spaces stay inside the number.
	result = every_stage(env, [f"10{space}20"], stage_settings(mode, size), context(env.module))
	assert shape(env, result) == [first, NB, second]


@pytest.mark.parametrize(
	("text", "expected"),
	[
		("1,234,567", ["123", NB, "456", NB, "7"]),
		("12,345.678", ["123", NB, "45", NB, N("."), NB, "678"]),
		# Not a valid thousands run: the comma stays, a named piece of its own.
		("1,23", ["1", NB, N(","), NB, "23"]),
	],
)
def test_thousands_then_groups(env, text, expected):
	# U3: value mode removes the thousands separators first, then groups.
	result = every_stage(env, [text], stage_settings("value", 3), context(env.module))
	assert shape(env, result) == expected


def language(code):
	return __import__("sys").modules["speech.commands"].LangChangeCommand(code)


def end_utterance():
	return __import__("sys").modules["speech.commands"].EndUtteranceCommand()


MARKER = Marker()


@pytest.mark.parametrize(
	("sequence", "expected"),
	[
		(lambda: ["10", "20"], ["1 0", E, "2 0"]),
		(lambda: ["10", MARKER, "20"], ["1 0", E, MARKER, "2 0"]),
		(lambda: ["10", " ", "20"], ["1 0", E, "2 0"]),
		(lambda: ["10", language("en"), "20"], ["1 0", E, ("L", "en"), "2 0"]),
		(lambda: ["10", end_utterance(), "20"], ["1 0", "EU", "2 0"]),
		(lambda: ["第1", "2章"], ["第1", E, "2章"]),
		(lambda: ["第1", "章"], ["第1", "章"]),
		(lambda: ["10", "a", "20"], ["1 0", "a", "2 0"]),
		(lambda: ["a 10", "20 b", "c"], ["a 1 0", E, "2 0 b", "c"]),
	],
	ids=[
		"items",
		"command",
		"blank-item",
		"language",
		"utterance-end",
		"text-around",
		"text-next",
		"text-between",
		"three",
	],
)
def test_number_mode_without_groups_keeps_numbers_in_two_items_apart(env, sequence, expected):
	# Spec §4.3 G2 and O2: one break between a number that ends one spoken item and a number that
	# starts the next spoken item of the utterance, whatever commands lie between; none next to text
	# (U4) and none across an utterance end.
	result = every_stage(env, sequence(), stage_settings("number", 0), context(env.module))
	assert shape(env, result) == expected


@pytest.mark.parametrize(("item", "expected"), [(0, ["1 0", E, "2 0"]), (30, ["1 0", ("B", 30), "2 0"])])
def test_number_mode_without_groups_takes_the_longer_item_pause(env, item, expected):
	# The item stage keeps the longer of its break and the item edge break (items.py), as before.
	result = every_stage(env, ["10", "20"], stage_settings("number", 0, item=item), context(env.module))
	assert shape(env, result) == expected


# Properties of spec §9.3 (Hypothesis).

PAUSES = st.integers(0, 60)


@SHARED_ENV
@given(raw=RAW_NUMBERS, mode=st.sampled_from(MODES), size=st.integers(1, 12), wait=PAUSES)
def test_property_lone_number_is_its_pieces_with_one_break_between_each_two(env, raw, mode, size, wait):
	# P-G3: a lone number is its rendered pieces, in order, with one number break of the pause
	# between each two, in every mode, at any pause (O1).
	module = env.module
	result = list(module.inject_numbers([raw], stage_settings(mode, size, wait), context(module)))
	pieces = module.numbers.number_pieces(raw, mode, size, N)
	assert result[0::2] == pieces, (raw, result)
	breaks = result[1::2]
	assert len(breaks) == len(pieces) - 1
	assert all(type(item) is module.NumberBreakCommand and item.time == wait for item in breaks)
	assert all(item is breaks[0] for item in breaks)


ITEM = object()
SEPARATORS = st.sampled_from([" ", "  ", " ", "　", ITEM])
SPACED_NUMBERS = st.lists(
	st.tuples(st.text(alphabet="0123456789", min_size=1, max_size=7), SEPARATORS),
	min_size=2,
	max_size=4,
)


def items_of(numbers):
	"""The text items of *numbers*, a list of (number, separator after it): ITEM starts a new item."""
	items, current = [], ""
	for index, (number, separator) in enumerate(numbers):
		current += number
		if index == len(numbers) - 1:
			break
		if separator is ITEM:
			items.append(current)
			current = ""
		else:
			current += separator
	return [*items, current]


@SHARED_ENV
@given(
	numbers=SPACED_NUMBERS,
	mode=st.sampled_from(MODES),
	size=st.integers(0, 10),
	item=st.sampled_from([0, 10, 30]),
	numlan=st.sampled_from(["default", "main", "en"]),
	wait=st.integers(1, 60),
)
def test_property_two_numbers_never_share_a_run(env, numbers, mode, size, item, numlan, wait):
	# P-U5 (decided by the user, 2026-11-01, U5): after every stage, no break-free run of text holds
	# digits of two source numbers; without groups every run is one whole source number, so number
	# mode's own spaces never split a number.
	owners = [index for index, (number, _separator) in enumerate(numbers) for _digit in number]
	result = every_stage(
		env,
		items_of(numbers),
		stage_settings(mode, size, wait, item),
		context(env.module, numlan),
	)
	runs, current, position = [], [], 0
	for entry in result:
		if isinstance(entry, env.BreakCommand):
			runs.append(current)
			current = []
		elif isinstance(entry, str):
			for character in entry:
				if character.isdecimal():
					current.append(owners[position])
					position += 1
	runs.append(current)
	runs = [run for run in runs if run]
	assert position == len(owners), (numbers, result)
	assert all(len(set(run)) == 1 for run in runs), (numbers, result)
	if size == 0:
		assert [(run[0], len(run)) for run in runs] == [
			(index, len(number)) for index, (number, _s) in enumerate(numbers)
		], (
			numbers,
			result,
		)


THOUSANDS_TEXT = st.text(alphabet="0123456789,.a -", max_size=16)


@SHARED_ENV
@given(text=THOUSANDS_TEXT, size=st.integers(1, 10), wait=PAUSES)
def test_property_value_groups_after_the_thousands_step(env, text, size, wait):
	# P-U3: value mode with groups strips valid thousands separators first, then cuts.
	module = env.module
	run_settings, ctx = stage_settings("value", size, wait), context(module)
	stripped = module.remove_thousands_separators([text], run_settings, ctx)
	both = shape(env, module.inject_numbers(list(stripped), run_settings, ctx))
	alone = shape(env, module.inject_numbers([module.numbers.strip_thousands(text)], run_settings, ctx))
	assert both == alone


NONE_TEXT = st.text(alphabet="0123456789+-.,:aZ共第章。  　", max_size=16)


@SHARED_ENV
@given(text=NONE_TEXT, size=st.integers(1, 10), wait=PAUSES)
def test_property_off_with_groups_keeps_every_character(env, text, size, wait):
	# P-none: off with a group size cuts but changes no character; only with a pause above 0 does
	# the whitespace that only separates two numbers become the gap break (G1).
	module = env.module
	result = list(module.inject_numbers([text], stage_settings("none", size, wait), context(module)))
	parts = list(module._split_numbers_for_language(text))
	gaps = {
		index for index, (_kind, value) in enumerate(parts) if 0 < index < len(parts) - 1 and value.isspace()
	}
	expected = "".join(
		value for index, (_kind, value) in enumerate(parts) if not (wait > 0 and index in gaps)
	)
	assert "".join(item for item in result if isinstance(item, str)) == expected, (text, result)
