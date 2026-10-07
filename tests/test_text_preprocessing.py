"""The text helpers the Vocalizer drivers run before speaking: chunking and Arabic run breaking.

The drain harnesses replace both with stubs, so these are their only tests.
"""

import re

import pytest
from addon_loader import WORLDVOICE, load_source

ESCAPE = "\x1b\\pause=100\\"
ESCAPE_RE = re.compile(r"\x1b\\.*?\\")
AIN = "ع"
BEH = "ب"


@pytest.fixture(scope="module")
def chunker():
	return load_source(None, "text_chunker_under_test", WORLDVOICE / "text/chunker.py", register=False)


@pytest.fixture(scope="module")
def arabic():
	return load_source(None, "text_arabic_under_test", WORLDVOICE / "text/arabic.py", register=False)


def plain(piece):
	return ESCAPE_RE.sub("", piece)


@pytest.mark.parametrize(
	("text", "max_length", "pieces"),
	[
		("", 10, []),
		("short", 10, ["short"]),
		("exactly ten", 11, ["exactly ten"]),
		# Split after the last space that fits; the space stays with the piece before it.
		("aaa bbb ccc", 8, ["aaa bbb ", "ccc"]),
		# No space to split at: cut at the length.
		("a" * 25, 10, ["a" * 10, "a" * 10, "a" * 5]),
		# Only separators: still at most max_length per piece.
		(" " * 25, 10, [" " * 10, " " * 10, " " * 5]),
		# A space only at the start is no split point.
		(" " + "a" * 15, 10, [" " + "a" * 9, "a" * 6]),
		("Hello 世界 مرحبا world", 12, ["Hello 世界 ", "مرحبا world"]),
	],
)
def test_split_pieces(chunker, text, max_length, pieces):
	assert chunker.split_speech_text_pieces(text, max_length) == pieces


def test_default_limit_splits_long_text_at_spaces(chunker):
	text = " ".join(["word"] * 60)
	pieces = chunker.split_speech_text_pieces(text)
	assert "".join(pieces) == text
	assert all(len(piece) <= chunker.MAX_TEXT_LENGTH for piece in pieces)
	assert all(piece.endswith(" ") for piece in pieces[:-1])


@pytest.mark.parametrize(
	"text",
	[
		"a" * 8 + ESCAPE + "b" * 8,
		"one two " + ESCAPE + " three four five six seven",
		ESCAPE + "a" * 20 + ESCAPE,
	],
)
def test_escape_sequences_are_never_split(chunker, text):
	pieces = chunker.split_speech_text_pieces(text, 10)
	assert "".join(pieces) == text
	assert sum(piece.count(ESCAPE) for piece in pieces) == text.count(ESCAPE)
	assert all(len(plain(piece)) <= 10 for piece in pieces)


def test_astral_characters_count_once_and_stay_whole(chunker):
	text = "\U00020000" * 25
	pieces = chunker.split_speech_text_pieces(text, 10)
	assert [len(piece) for piece in pieces] == [10, 10, 5]


def test_combining_marks_stay_with_their_letter_at_a_space(chunker):
	word = "e\u0301" * 3
	pieces = chunker.split_speech_text_pieces(f"{word} {word}", 8)
	assert pieces == [f"{word} ", word]


@pytest.mark.parametrize(
	("text", "pieces"),
	[
		# The limit counts plain characters: an escape never makes a piece of its own.
		(ESCAPE + "a" * 20, [ESCAPE + "a" * 10, "a" * 10]),
		("aaa" + ESCAPE + "b" * 20, ["aaa" + ESCAPE + "b" * 7, "b" * 10, "b" * 3]),
		# Within the limit once the escapes are left out: one piece.
		(ESCAPE + "a" * 10 + ESCAPE, [ESCAPE + "a" * 10 + ESCAPE]),
		# A trailing escape stays with the last piece, also right after a cut.
		("a" * 15 + ESCAPE, ["a" * 10, "a" * 5 + ESCAPE]),
		("a" * 20 + ESCAPE, ["a" * 10, "a" * 10 + ESCAPE]),
	],
)
def test_escapes_do_not_count_toward_the_limit(chunker, text, pieces):
	assert chunker.split_speech_text_pieces(text, 10) == pieces


@pytest.mark.parametrize(
	("text", "pieces"),
	[
		# No space to split at: the cut moves back before the letter its mark belongs to.
		("e\u0301" * 8, ["e\u0301" * 2, "e\u0301" * 2, "e\u0301" * 2, "e\u0301" * 2]),
		("ab" + "c\u0301\u0327" * 3, ["abc\u0301\u0327", "c\u0301\u0327", "c\u0301\u0327"]),
		# One letter whose marks alone pass the limit stays whole rather than split.
		("x" + "\u0301" * 7 + "yy", ["x" + "\u0301" * 7, "yy"]),
		# A cut at a space also stays off a mark that space carries.
		("aaaa \u0301", ["aaaa", " \u0301"]),
	],
)
def test_a_hard_cut_keeps_combining_marks_with_their_letter(chunker, text, pieces):
	assert chunker.split_speech_text_pieces(text, 5) == pieces
	assert "".join(pieces) == text


@pytest.mark.parametrize(
	("text", "expected"),
	[
		("", ""),
		(AIN * 3, AIN * 3),
		(AIN * 4 + BEH, AIN * 3 + " " + AIN + BEH),
		(AIN * 7, f"{AIN * 3} {AIN * 3} {AIN}"),
		# Different letters, or letters with a mark between them, are no run.
		(AIN + BEH + AIN + BEH + AIN, AIN + BEH + AIN + BEH + AIN),
		((AIN + "\u0651") * 4, (AIN + "\u0651") * 4),
		# Only Arabic script is broken.
		("aaaaaa", "aaaaaa"),
		# Presentation forms count as Arabic letters.
		("ﻉ" * 4, "ﻉ" * 3 + " ﻉ"),
	],
)
def test_runs_longer_than_three_identical_arabic_letters_are_broken(arabic, text, expected):
	assert arabic.break_repeated_runs(text) == expected


def test_escape_sequences_keep_their_runs_and_split_runs(arabic):
	escape = f"\x1b\\{AIN * 5}\\"
	assert arabic.break_repeated_runs(escape + AIN * 4) == escape + AIN * 3 + " " + AIN
	# An escape between two halves ends the run.
	assert arabic.break_repeated_runs(AIN * 2 + ESCAPE + AIN * 2) == AIN * 2 + ESCAPE + AIN * 2


@pytest.mark.parametrize(
	("max_run", "text", "expected"),
	[
		(4, AIN * 4, AIN * 4),
		(4, AIN * 5, AIN * 4 + " " + AIN),
		# A limit below three turns the breaking off.
		(2, AIN * 5, AIN * 5),
	],
)
def test_max_run_sets_the_longest_run_kept(arabic, max_run, text, expected):
	assert arabic.break_repeated_runs(text, max_run) == expected
