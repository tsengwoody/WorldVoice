# A part of the WorldVoice add-on.
# Split long speech text into smaller pieces so that speech synthesis
# engines never receive an oversized text in a single call.

import re

# Maximum number of plain characters per piece. Control escape sequences
# (e.g. \x1b\pause=100\) may make a piece slightly longer than this.
MAX_TEXT_LENGTH = 100

# Vocalizer control escape: ESC + backslash + content + backslash.
_ESCAPE_RE = re.compile(r"\x1b\\.*?\\")

# A run of this many identical Arabic letters is considered pathological.
# Vocalizer Arabic text analysis slows down sharply on unbroken runs of 4 or
# more identical letters, so runs longer than this get broken with spaces.
MAX_REPEATED_RUN = 3

# Arabic script code points where repeated-letter runs trigger the slow
# analysis path: Arabic, Arabic Supplement, Arabic Extended-A, Arabic
# Presentation Forms-A and -B.
_ARABIC_LETTER = "[\\u0600-\\u06ff\\u0750-\\u077f\\u08a0-\\u08ff\\ufb50-\\ufdff\\ufe70-\\ufeff]"


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


def break_repeated_runs(text, max_run=MAX_REPEATED_RUN):
	"""Break runs of identical Arabic letters longer than *max_run*.

	Vocalizer Arabic text analysis slows down sharply (seconds of silence
	before any audio) when the input contains an unbroken run of 4 or more
	identical Arabic letters, regardless of surrounding word boundaries.
	Inserting a space after every *max_run* letters turns such a run into
	separate word tokens which the engine analyzes normally; the inserted
	space is inaudible in Arabic speech. Control escape sequences are left
	untouched. Returns *text* unchanged when there is nothing to break.
	"""
	if max_run < 3 or not text:
		return text
	pattern = re.compile(rf"({_ARABIC_LETTER})\1{{{max_run},}}")

	def _repl(match):
		run = match.group(0)
		return " ".join(run[i:i + max_run] for i in range(0, len(run), max_run))

	parts = []
	pos = 0
	for match in _ESCAPE_RE.finditer(text):
		parts.append(pattern.sub(_repl, text[pos:match.start()]))
		parts.append(match.group())
		pos = match.end()
	parts.append(pattern.sub(_repl, text[pos:]))
	return "".join(parts)
