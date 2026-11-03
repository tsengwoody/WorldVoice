"""The segment cut rule the speech pipeline uses (pipeline/segments.py): where a long run of text is
cut, never between a letter and what is attached to it. NVDA-free."""

import unicodedata
from bisect import bisect_left, bisect_right
from collections.abc import Sequence

_ZWJ = "\u200d"
# Spacing vowels written after their consonant whose category is Lo, not M: Thai and Lao AM.
_SPACING_VOWELS = frozenset("\u0e33\u0eb3")


def _attached(token, index):
	"""Whether token[index] belongs to the character before it.

	Combining marks of any combining class (Thai vowels, Devanagari vowel signs and
	variation selectors have class 0), Thai and Lao AM, emoji skin tones, a zero-width
	non-joiner, and both sides of a zero-width joiner. Not recognized: conjoining Hangul
	jamo, regional-indicator flag pairs, emoji tag sequences and conjuncts formed with a
	virama.
	"""
	char = token[index]
	return (
		unicodedata.category(char).startswith("M")
		or char in _SPACING_VOWELS
		or "\U0001f3fb" <= char <= "\U0001f3ff"
		or char in ("\u200c", _ZWJ)
		or token[index - 1] == _ZWJ
	)


def _inseparable(token, index):
	"""Whether a cut before token[index] is not allowed: token[index] is attached (_attached), or it
	is inside a whitespace run, so a run such as "\r\n" or a blank item is never split."""
	return _attached(token, index) or (token[index - 1].isspace() and token[index].isspace())


def _cut_before_marks(token, cut, start=0):
	"""Move a cut back so it never leaves a mark without its letter, never lands inside a
	whitespace run (_inseparable), and never goes before *start*.

	Returns *start* when everything from there to the cut is one letter and its marks.
	"""
	while start < cut < len(token) and _inseparable(token, cut):
		cut -= 1
	return cut


def _end_of_marks(token, start):
	end = start + 1
	while end < len(token) and _inseparable(token, end):
		end += 1
	return end


def segment_cuts(texts: Sequence[str], max_length: int) -> list[tuple[int, int]]:
	"""Where to cut the text items of one run: (item index, offset), the piece ending after
	texts[index][:offset], with 0 < offset <= len(texts[index]); in order.

	A piece is counted from its first to its last non-blank character and ends after the last
	whitespace run or at the last item boundary whose spoken text before it fits in *max_length*
	characters; with none, at *max_length*, moved back so no attached character (_attached) loses
	the one it belongs to. No cut lands inside a whitespace run (_inseparable). A single letter whose
	marks pass the limit stays whole. Every cut has non-blank text before and after it, so no piece
	is only whitespace and no cut lands before trailing whitespace: the rest is not cut once its
	non-blank text fits in *max_length*. Concatenating the pieces gives back the joined text.
	*max_length* 0 or less: no cut (spec feat/segment-pause §4.1; decided by the user, 2026-11-03,
	Q2, Q3).
	"""
	text = "".join(texts)
	if max_length <= 0:
		return []
	spoken = [index for index, char in enumerate(text) if not char.isspace()]
	if not spoken:
		return []
	last = spoken[-1]
	boundaries = set()
	end = 0
	for item in texts[:-1]:
		end += len(item)
		boundaries.add(end)
	# A candidate follows whitespace or is an item boundary, and is not _inseparable, so it ends a
	# whitespace run; it fits when the spoken text before it does (spoken_ends): the whitespace it
	# ends is not counted.
	candidates, spoken_ends = [], []
	spoken_end = 0
	for position in range(1, len(text)):
		if not text[position - 1].isspace():
			spoken_end = position
		if (text[position - 1].isspace() or position in boundaries) and not _inseparable(text, position):
			candidates.append(position)
			spoken_ends.append(spoken_end)
	cuts = []
	start = 0
	while True:
		first = bisect_left(spoken, start)
		if first == len(spoken):
			break
		piece_start = spoken[first]
		if last - piece_start < max_length:
			break
		limit = piece_start + max_length
		best = bisect_right(spoken_ends, min(limit, last)) - 1
		if best >= 0 and candidates[best] > piece_start:
			cut = candidates[best]
		else:
			cut = _cut_before_marks(text, limit, piece_start)
			if cut == piece_start:
				cut = _end_of_marks(text, piece_start)
			if cut > last:
				break
		cuts.append(cut)
		start = cut
	return _item_offsets(texts, cuts)


def _item_offsets(texts, cuts):
	"""Each cut position of the joined text as (item index, offset) of the first item ending at or after it."""
	result = []
	index, item_start = 0, 0
	for cut in cuts:
		while item_start + len(texts[index]) < cut:
			item_start += len(texts[index])
			index += 1
		result.append((index, cut - item_start))
	return result
