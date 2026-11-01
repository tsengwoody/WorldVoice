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
