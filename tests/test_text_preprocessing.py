"""The text helpers: the segment cut rule the speech pipeline uses, and the Arabic run breaking the
Vocalizer drivers run before speaking.

The drain harnesses replace the Arabic run breaking with a stub, so these are its only tests.
"""

import re
import time

import pytest
from addon_loader import WORLDVOICE, load_source
from hypothesis import given, strategies as st

ESCAPE = "\x1b\\pause=100\\"
AIN = "ع"
BEH = "ب"


@pytest.fixture(scope="module")
def chunker():
	return load_source(None, "text_chunker_under_test", WORLDVOICE / "text/chunker.py", register=False)


@pytest.fixture(scope="module")
def arabic():
	return load_source(None, "text_arabic_under_test", WORLDVOICE / "text/arabic.py", register=False)


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


# Property tests over generated text. The pieces these strategies draw from are the cases the
# hand-written tests above pin; Hypothesis combines them in ways a person would not.
TOKEN = re.compile(r"\x1b\\[^\\\n]*\\")
ESCAPES = st.sampled_from([ESCAPE, "\x1b\\rate=50\\", "\x1b\\mrk=7\\", "\x1b\\tn=spell\\"])


@given(parts=st.lists(st.one_of(st.sampled_from([AIN, BEH, " ", "ّ"]), ESCAPES), max_size=60))
def test_property_arabic_runs_only_gain_spaces(arabic, parts):
	text = "".join(parts)
	broken = arabic.break_repeated_runs(text)
	assert TOKEN.findall(broken) == TOKEN.findall(text), "an escape changed"
	assert broken.replace(" ", "") == text.replace(" ", "")
	# One space for every three letters past the first three of a run; nothing else changes.
	# Every code point of the Arabic blocks counts, the shadda mark included.
	runs = re.finditer(rf"([{AIN}{BEH}\u0651])\1*", TOKEN.sub("|", text))
	needed = sum((len(run.group()) - 1) // 3 for run in runs if len(run.group()) > 3)
	assert broken.count(" ") - text.count(" ") == needed
	assert not re.search(rf"([{AIN}{BEH}\u0651])\1{{3}}", TOKEN.sub("|", broken)), "a run of four was left"
	assert arabic.break_repeated_runs(broken) == broken


# Segment cuts (feat/segment-pause spec §4.1): where the segment pause stage cuts a run of text items.
# A cut goes after the last whitespace or item boundary within N characters, counted from the piece's
# first non-blank character; otherwise at N, never before an attached character.

FOX = ("The quick brown fox jumps over the lazy dog. " * 3).strip()
E_ACUTE = "e\u0301"


def cut_pieces(chunker, texts, n):
	"""The joined text of *texts* split at the cuts segment_cuts returns."""
	text = "".join(texts)
	starts = [0]
	for item in texts:
		starts.append(starts[-1] + len(item))
	pieces, previous = [], 0
	for index, offset in chunker.segment_cuts(texts, n):
		cut = starts[index] + offset
		pieces.append(text[previous:cut])
		previous = cut
	pieces.append(text[previous:])
	return pieces


@pytest.mark.parametrize(
	("texts", "n", "pieces"),
	[
		pytest.param(
			[FOX],
			50,
			[
				"The quick brown fox jumps over the lazy dog. The ",
				"quick brown fox jumps over the lazy dog. The ",
				"quick brown fox jumps over the lazy dog.",
			],
			id="fox",
		),
		pytest.param(["Hello world"], 8, ["Hello ", "world"], id="space"),
		pytest.param(["foo bar baz"], 8, ["foo bar ", "baz"], id="last-space"),
		pytest.param(["one two", "three"], 8, ["one two", "three"], id="item-boundary"),
		pytest.param(["a" * 30, "b" * 30], 40, ["a" * 30, "b" * 30], id="boundary-beats-hard-cut"),
		pytest.param(["中文語音合成" * 3], 5, ["中文語音合", "成中文語音", "合成中文語", "音合成"], id="han"),
		pytest.param([E_ACUTE * 3], 3, [E_ACUTE, E_ACUTE, E_ACUTE], id="marks"),
		pytest.param(["x" * 10 + "   "], 10, ["x" * 10 + "   "], id="trailing-spaces"),
		pytest.param(["  ab cd"], 5, ["  ab cd"], id="leading-spaces-uncounted"),
		pytest.param(["   aaaaaaaa b"], 8, ["   aaaaaaaa", " b"], id="leading-spaces-hard-cut"),
		pytest.param(["ab\ncd\tef"], 5, ["ab\n", "cd\tef"], id="newline-tab"),
		pytest.param(["中文\u3000中文"], 3, ["中文\u3000", "中文"], id="ideographic"),
		pytest.param(["ab\u00a0cd"], 3, ["ab\u00a0", "cd"], id="nbsp"),
		pytest.param(["abcd\u200befgh"], 6, ["abcd\u200be", "fgh"], id="zwsp"),
		pytest.param(["abc", "\u0301def"], 4, ["abc\u0301", "def"], id="mark-item"),
		pytest.param(["\U00020000" * 6], 3, ["\U00020000" * 3] * 2, id="astral"),
		pytest.param(["e\u0301\u0301\u0301x"], 2, ["e\u0301\u0301\u0301", "x"], id="long-cluster"),
		pytest.param(["abcdefgh"], 3, ["abc", "def", "gh"], id="hard-cuts"),
		pytest.param(["aaaa", "  ", "bbbb"], 6, ["aaaa  ", "bbbb"], id="blank-item"),
		pytest.param(["aa", "bb", "cccc"], 5, ["aabb", "cccc"], id="later-boundary"),
		pytest.param(["a", "bcd"], 2, ["a", "bc", "d"], id="boundary-after-one"),
	],
)
def test_segment_cuts_pieces(chunker, texts, n, pieces):
	assert cut_pieces(chunker, texts, n) == pieces


@pytest.mark.parametrize(
	("texts", "n"),
	[
		(["abc"], 0),
		(["abc"], -1),
		([], 5),
		(["   "], 2),
		(["", " \n"], 1),
		(["abc"], 3),
		pytest.param(["a b" * 1000], 2**31 - 1, id="n-max"),
	],
)
def test_segment_cuts_without_a_cut(chunker, texts, n):
	assert chunker.segment_cuts(texts, n) == []


@pytest.mark.parametrize(
	("texts", "n", "cuts"),
	[
		(["ab ", "", "cd"], 3, [(0, 3)]),
		(["ab", "", "cd"], 2, [(0, 2)]),
		(["one two", "three"], 8, [(0, 7)]),
		(["abc", "\u0301def"], 4, [(1, 1)]),
		(["aaaa", "  ", "bbbb"], 6, [(1, 2)]),
	],
)
def test_segment_cuts_map_a_cut_to_the_first_item_ending_there(chunker, texts, n, cuts):
	assert chunker.segment_cuts(texts, n) == cuts


def test_cut_before_marks_stops_at_its_start(chunker):
	assert chunker._cut_before_marks("ae\u0301\u0301", 3, 1) == 1
	assert chunker._cut_before_marks("e\u0301", 1) == 0
	assert chunker._cut_before_marks("ab", 2) == 2


@pytest.mark.parametrize(
	("text", "attached"),
	[
		("a\u0301", True),
		("a\u0e33", True),
		("a\u0eb3", True),
		("a\U0001f3fb", True),
		("a\U0001f3ff", True),
		("a\U0001f3fa", False),
		("a\U0001f400", False),
		("a\u200c", True),
		("a\u200d", True),
		("\u200db", True),
		("ab", False),
		("a ", False),
	],
)
def test_attached_marks_tones_and_joiners(chunker, text, attached):
	# What segment_cuts never cuts before: a mark, Thai or Lao AM, a skin tone, a zero-width
	# non-joiner, and both sides of a zero-width joiner.
	assert chunker._attached(text, 1) is attached


def test_segment_cuts_stay_fast(chunker):
	for texts, n in (
		(["a" * 100_000], 1),
		(["ab " * 33_000], 1),
		(["word " * 20_000], 7),
		(["x" * 100_000], 2**31 - 1),
	):
		start = time.perf_counter()
		chunker.segment_cuts(texts, n)
		assert time.perf_counter() - start < 2


SEGMENT_PARTS = st.sampled_from(
	[
		"a",
		"b",
		" ",
		"\n",
		"\r\n",
		"\t",
		"\u00a0",
		"\u3000",
		"\u200b",
		"\u0301",
		"\u0e33",
		"\u200d",
		"\U0001f3fd",
		"中",
		"ก",
	],
)
SEGMENT_ITEMS = st.lists(st.lists(SEGMENT_PARTS, max_size=12).map("".join), max_size=5)


@given(texts=SEGMENT_ITEMS, n=st.integers(1, 15))
def test_property_segment_cuts_keep_the_rules(chunker, texts, n):
	text = "".join(texts)
	cuts = chunker.segment_cuts(texts, n)
	starts = [0]
	for item in texts:
		starts.append(starts[-1] + len(item))
	positions = []
	for index, offset in cuts:
		assert 0 < offset <= len(texts[index]), "a cut outside its item"
		positions.append(starts[index] + offset)
	assert positions == sorted(set(positions)), "cuts out of order"
	pieces = cut_pieces(chunker, texts, n)
	assert "".join(pieces) == text
	for cut in positions:
		assert text[:cut].strip() and text[cut:].strip(), "a cut without spoken text on one side"
		assert not chunker._attached(text, cut), "a cut split a character"
	for number, piece in enumerate(pieces):
		counted = piece.strip() if number == len(pieces) - 1 else piece.lstrip()
		if len(counted) > n:
			# Only one character with everything attached to it may pass the limit.
			assert all(chunker._attached(counted, index) for index in range(1, len(counted))), piece
