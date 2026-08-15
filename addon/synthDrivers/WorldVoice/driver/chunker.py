# A part of the WorldVoice add-on.
# Split long speech text into smaller pieces so that speech synthesis
# engines never receive an oversized text in a single call.

import re

# Maximum number of plain characters per piece. Control escape sequences
# (e.g. \x1b\pause=100\) may make a piece slightly longer than this.
MAX_TEXT_LENGTH = 100

# Vocalizer control escape: ESC + backslash + content + backslash.
_ESCAPE_RE = re.compile(r"\x1b\\.*?\\")


def split_speech_text_pieces(text, max_length=MAX_TEXT_LENGTH):
	"""Split *text* into pieces of at most *max_length* plain characters.

	Pieces are split at whitespace boundaries when possible, otherwise at
	character boundaries. Control escape sequences are never split and stay
	attached to a single piece. Concatenating all returned pieces in order
	reproduces the original *text*.
	"""
	if not text:
		return []
	if len(text) <= max_length:
		return [text]
	pieces = []
	current = ""
	pos = 0
	tokens = []
	for match in _ESCAPE_RE.finditer(text):
		if match.start() > pos:
			tokens.append(text[pos:match.start()])
		tokens.append(match.group())
		pos = match.end()
	if pos < len(text):
		tokens.append(text[pos:])
	for token in tokens:
		if token.startswith("\x1b"):
			current += token
			continue
		while token:
			remaining = max_length - len(current)
			if remaining <= 0:
				pieces.append(current)
				current = ""
				remaining = max_length
			if len(token) <= remaining:
				current += token
				token = ""
			else:
				head = token[:remaining]
				cut = head.rfind(" ")
				if cut <= 0:
					cut = remaining
				else:
					cut += 1
				current += token[:cut]
				token = token[cut:]
				pieces.append(current)
				current = ""
	if current:
		pieces.append(current)
	return pieces
