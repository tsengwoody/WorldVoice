"""The space pause of unspaced scripts (unspaced_script_space_wait_factor): a space between two
characters of scripts written without spaces between words is a break."""

import re
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING

from speech.commands import BreakCommand

from ..unicodeScripts.lookup import get_script
from ..unicodeScripts.unspaced_common_data import UNSPACED_COMMON
from .context import SpeechContext
from .sequence import SpeechCmd

if TYPE_CHECKING:
	from .settings import PipelineSettings


_WHITESPACE_RE = re.compile(r"\s+")


# Scripts whose words are not separated by spaces: a space between two of their characters is a
# pause (decided by the user, 2026-10-25). To extend the rule, add a script here and to
# UNSPACED_SCRIPT_CODES in tools/generate_unspaced_common.py, then regenerate
# unicodeScripts/unspaced_common_data.py.
UNSPACED_SCRIPTS = frozenset({"Han", "Hiragana", "Katakana", "Bopomofo", "Thai", "Lao", "Khmer", "Myanmar"})


def _is_unspaced(character: str) -> bool:
	"""Whether *character* belongs to a script written without spaces between words.

	Besides the characters of UNSPACED_SCRIPTS, a Common letter, number or symbol counts when its
	Script_Extensions name one of those scripts: ー, 〆, ˇ, ㈱, ㊀, but not 。 or 「 (decided by
	the user, 2026-10-25). UNSPACED_COMMON is generated from ScriptExtensions.txt and UnicodeData.txt by
	tools/generate_unspaced_common.py.
	"""
	return character in UNSPACED_COMMON or get_script(ord(character)) in UNSPACED_SCRIPTS


def _pauses_between(text: str, start: int, end: int) -> bool:
	"""Whether the whitespace run text[start:end] is a pause: unspaced characters on both sides.

	An Inherited mark takes the script of the character it attaches to, the one before it (O1). So
	the left side is the first character before the run that is not Inherited, and a mark right
	after the run, which attaches to the whitespace, means no pause.
	"""
	if end == len(text):
		return False
	base = start - 1
	while base >= 0 and get_script(ord(text[base])) == "Inherited":
		base -= 1
	return base >= 0 and _is_unspaced(text[base]) and _is_unspaced(text[end])


def inject_unspaced_script_space_pause(
	speechSequence: Iterable[SpeechCmd],
	settings: "PipelineSettings",
	ctx: SpeechContext,
) -> Iterator[SpeechCmd]:
	waitfactor = settings.scaled_unspaced_script_space_wait()
	if waitfactor <= 0:
		yield from speechSequence
		return

	pause_cmd = BreakCommand(waitfactor)

	for item in speechSequence:
		# non-string commands flow through untouched
		if not isinstance(item, str):
			yield item
			continue

		# a whitespace run between two unspaced characters becomes the pause
		pos = 0
		for match in _WHITESPACE_RE.finditer(item):
			if _pauses_between(item, match.start(), match.end()):
				yield item[pos : match.start()]
				yield pause_cmd
				pos = match.end()
		if pos < len(item):
			yield item[pos:]
