"""The text helpers the Vocalizer drivers run before speaking: chunking and Arabic run breaking.

The drain harnesses replace both with stubs, so these are their only tests.
"""

import re
import time

import pytest
from addon_loader import WORLDVOICE, load_source
from hypothesis import given, strategies as st

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
	("text", "max_length", "pieces"),
	[
		# Escapes before a break go with the text after it: an inline setting must reach it.
		("a" * 10 + ESCAPE + "b", 10, ["a" * 10, ESCAPE + "b"]),
		# A letter and its marks that do not fit the rest of a piece start the next one.
		("aa" + ESCAPE + "e\u0301\u0301", 3, ["aa", ESCAPE + "e\u0301\u0301"]),
		# A lone ESC is text: it counts and does not shield what follows.
		("\x1b" + "a" * 30, 10, ["\x1b" + "a" * 9, "a" * 10, "a" * 10, "a"]),
		# A would-be escape spanning a line break is text too; no piece comes out empty.
		("a" * 6 + "\x1b\\a\nb\\" + ESCAPE + "c", 6, ["a" * 6, "\x1b\\a\nb\\", ESCAPE + "c"]),
		# Only the escapes at the very end move: text between two escapes stays put.
		("aaa" + ESCAPE + "e\u0301aa" + ESCAPE + "a", 4, ["aaa", ESCAPE + "e\u0301aa", ESCAPE + "a"]),
		# An escape after a letter kept whole past the limit joins that letter's piece.
		("x" + "\u0301" * 7 + ESCAPE, 5, ["x" + "\u0301" * 7 + ESCAPE]),
	],
)
def test_pieces_break_around_escapes_and_whole_letters(chunker, text, max_length, pieces):
	assert chunker.split_speech_text_pieces(text, max_length) == pieces


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
		# Marks with no combining class: Thai vowels, Devanagari vowel signs, variation selectors.
		("\u0e01\u0e34" * 4, ["\u0e01\u0e34" * 2, "\u0e01\u0e34" * 2]),
		("\u0915\u093e" * 4, ["\u0915\u093e" * 2, "\u0915\u093e" * 2]),
		("\u2764\ufe0f" * 4, ["\u2764\ufe0f" * 2, "\u2764\ufe0f" * 2]),
		# Thai AM is a letter by category but follows its consonant.
		("\u0e17\u0e33" * 3, ["\u0e17\u0e33" * 2, "\u0e17\u0e33"]),
		# A zero-width joiner holds both its neighbours; a skin tone stays with its emoji.
		(
			"aaa\U0001f468\u200d\U0001f469\u200d\U0001f467",
			["aaa", "\U0001f468\u200d\U0001f469\u200d\U0001f467"],
		),
		("\U0001f44d\U0001f3fd" * 3, ["\U0001f44d\U0001f3fd" * 2, "\U0001f44d\U0001f3fd"]),
		# The text may end in a letter kept whole past the limit.
		("ab" + "x" + "\u0301" * 7, ["ab", "x" + "\u0301" * 7]),
	],
)
def test_a_hard_cut_keeps_combining_marks_with_their_letter(chunker, text, pieces):
	result = chunker.split_speech_text_pieces(text, 5)
	assert result == pieces
	assert "".join(result) == text


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
TEXT_PARTS = st.sampled_from(
	[
		"a",
		" ",
		"é",
		"กิ",
		"ทำ",
		"का",
		"❤️",
		"\U0001f468‍\U0001f469",
		"\U0001f44d\U0001f3fd",
		"世",
		"\U00020000",
		AIN,
	],
)
SPEECH_TEXT = st.lists(
	st.one_of(TEXT_PARTS, ESCAPES, st.characters(exclude_characters="\x1b")),
	max_size=80,
)


@given(parts=SPEECH_TEXT, max_length=st.integers(1, 12))
def test_property_chunk_pieces_rebuild_the_text_within_the_limit(chunker, parts, max_length):
	text = "".join(parts)
	pieces = chunker.split_speech_text_pieces(text, max_length)
	assert "".join(pieces) == text
	assert all(pieces)
	assert sum(len(TOKEN.findall(piece)) for piece in pieces) == len(TOKEN.findall(text)), "an escape was cut"
	has_text = bool(TOKEN.sub("", text))
	position = 0
	for number, piece in enumerate(pieces):
		words = TOKEN.sub("", piece)
		assert words or not has_text, "a piece holds only escapes"
		if len(words) > max_length:
			# Only one character with everything attached to it may pass the limit.
			assert all(chunker._attached(words, index) for index in range(1, len(words)))
		if number == len(pieces) - 1:
			break
		position += len(piece)
		assert not re.search(r"\x1b\\[^\\\n]*\\\Z", piece), "escapes before a break stayed behind"
		if text[position] != "\x1b":
			assert not chunker._attached(text, position), "a cut split a character"


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
