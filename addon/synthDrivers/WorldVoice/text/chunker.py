# A part of the WorldVoice add-on.
# Split long speech text into smaller pieces so that speech synthesis
# engines never receive an oversized text in a single call.

import re
import unicodedata

# Maximum number of plain characters per piece. Control escape sequences
# (e.g. \x1b\pause=100\) may make a piece slightly longer than this.
MAX_TEXT_LENGTH = 100

# Vocalizer control escape: ESC + backslash + content + backslash.
_ESCAPE_RE = re.compile(r"\x1b\\.*?\\")


def _cut_before_marks(token, cut):
	"""Move a hard cut off a combining mark so it never leaves a mark without its letter.

	Returns 0 when the whole head is one letter and its marks.
	"""
	while 0 < cut < len(token) and unicodedata.combining(token[cut]):
		cut -= 1
	return cut


def _end_of_marks(token, start):
	end = start + 1
	while end < len(token) and unicodedata.combining(token[end]):
		end += 1
	return end


def split_speech_text_pieces(text, max_length=MAX_TEXT_LENGTH):
	"""Split *text* into pieces of at most *max_length* plain characters.

	Pieces are split at whitespace boundaries when possible, otherwise at
	character boundaries, never between a letter and its combining marks (a
	letter whose marks alone pass the limit stays whole; an escape between a
	letter and its marks counts as a boundary). Control escape sequences are
	not counted, never split and never form a piece of their own.
	Concatenating all returned pieces in order reproduces the original *text*.
	"""
	if not text:
		return []
	if len(_ESCAPE_RE.sub("", text)) <= max_length:
		return [text]
	pieces = []
	current = ""
	plain = 0
	pos = 0
	tokens = []
	for match in _ESCAPE_RE.finditer(text):
		if match.start() > pos:
			tokens.append(text[pos : match.start()])
		tokens.append(match.group())
		pos = match.end()
	if pos < len(text):
		tokens.append(text[pos:])
	for token in tokens:
		if token.startswith("\x1b"):
			current += token
			continue
		while token:
			remaining = max_length - plain
			if remaining <= 0:
				pieces.append(current)
				current, plain = "", 0
				remaining = max_length
			if len(token) <= remaining:
				current += token
				plain += len(token)
				token = ""
				continue
			head = token[:remaining]
			cut = head.rfind(" ")
			cut = _cut_before_marks(token, cut + 1 if cut > 0 else remaining)
			if cut == 0:
				if plain:
					# The letter fits after a flush; try again on an empty piece.
					pieces.append(current)
					current, plain = "", 0
					continue
				cut = _end_of_marks(token, 0)
			current += token[:cut]
			token = token[cut:]
			pieces.append(current)
			current, plain = "", 0
	if current:
		if plain or not pieces:
			pieces.append(current)
		else:
			# Escapes after the last cut stay with the last piece.
			pieces[-1] += current
	return pieces
