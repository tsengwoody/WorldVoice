"""The one definition of a number, and the rules for cutting one into spoken pieces.

This module imports only the standard library, so it needs no NVDA module or stub to load.
"""

import re
import unicodedata
from collections.abc import Callable, Iterator
from itertools import pairwise

# The symbols a number may hold between its digits: punctuation and symbols of Latin-1, so
# "12,345", "5-3", "12:30" and "2×3" are one number each. Full-width and CJK punctuation are not.
SYMBOLS = "".join(c for c in map(chr, range(0x100)) if unicodedata.category(c)[0] in "PS")
# The one definition of a number: an optional sign that is not right after a digit, digits, then
# any number of (symbols, digits). "[SYM]+" rather than "[SYM]*" keeps fullmatch from backtracking
# exponentially; both match the same strings. The sign's lookbehind documents Q3 ("not right after a
# digit"); under left-to-right scanning it is equivalent to a bare "[+-]?", because a digit before
# the sign would already belong to the previous match, so mutation testing reports it as equivalent.
NUMBER_RE = re.compile(rf"(?:(?<![0-9])[+-])?[0-9]+(?:[{re.escape(SYMBOLS)}]+[0-9]+)*")
# The tokens of one number: its leading signed digit run, further digit runs, and single symbols.
NUMBER_TOKEN_RE = re.compile(rf"^[+-]?[0-9]+|[0-9]+|[{re.escape(SYMBOLS)}]")
DIGITS = frozenset("0123456789")
# A run of digits and commas that is a whole, valid thousands-separated number: one to three
# digits, then groups of three. The lookarounds keep a longer comma/digit run, as in "1,234,,5" or
# "a,1,234", from losing the commas of a valid part.
THOUSANDS_RE = re.compile(r"(?<![0-9,])[0-9]{1,3}(?:,[0-9]{3})+(?!,*[0-9])")


def strip_thousands(text: str) -> str:
	"""*text* without the commas of each valid thousands run: "12,345,678" -> "12345678"."""
	return THOUSANDS_RE.sub(lambda match: match.group().replace(",", ""), text)


def split_spaced_numbers(text: str) -> Iterator[str]:
	"""
	Yield *text* with every number that only whitespace separates from a
	neighbouring number as an item of its own, without that whitespace.

	Everything else is kept verbatim, spaces included, and no empty piece is
	yielded. Two matches never touch (a match ends with a digit and the next
	one cannot start right after it), so a pause can only replace whitespace.
	Any whitespace pairs two numbers, a no-break space included (decided by
	the user, 2026-10-22), so "10 000" written with one is two numbers.
	"""
	matches = list(NUMBER_RE.finditer(text))
	gaps = [text[left.end() : right.start()] for left, right in pairwise(matches)]
	# joined[i] is True when matches i - 1 and i are split apart; the ends are never joined.
	joined = [False, *(gap.isspace() for gap in gaps), False]
	position = 0
	for index, match in enumerate(matches):
		if not (joined[index] or joined[index + 1]):
			continue
		if not joined[index] and match.start() > position:
			yield text[position : match.start()]
		yield match.group()
		position = match.end()
	if position < len(text):
		yield text[position:]


def number_pieces(
	raw: str,
	mode: str,
	group_size: int,
	name_of: Callable[[str], str | None],
) -> list[str]:
	"""The spoken pieces of one number match in *mode*.

	Value mode keeps it whole. Number and group modes cut each digit run from the left into
	pieces of 1 or *group_size* digits (a leading sign joins the first piece) and make each symbol
	a piece of its own: its name, or the symbol itself when NVDA has no name for it, so NVDA's
	symbol processing decides how it sounds (decided by the user, 2026-10-22).
	"""
	if mode == "value":
		return [raw]
	size = 1 if mode == "number" else group_size
	pieces: list[str] = []
	for token in NUMBER_TOKEN_RE.findall(raw):
		if token[-1] in DIGITS:
			sign = token[0] if token[0] in "+-" else ""
			digits = token[len(sign) :]
			groups = [digits[index : index + size] for index in range(0, len(digits), size)]
			groups[0] = sign + groups[0]
			pieces.extend(groups)
		else:
			name = name_of(token)
			pieces.append(token if name is None else name)
	return pieces
