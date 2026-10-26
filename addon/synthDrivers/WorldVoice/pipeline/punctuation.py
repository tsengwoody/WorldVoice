"""The punctuation pause (punctuation_wait_factor): a break at each configured punctuation mark,
which the stage may also remove."""

import re
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Literal

from speech.commands import BreakCommand

from .breaks import NumberBreakCommand, PunctuationBreakCommand, _is_edge_break, _merge_edge_breaks
from .context import SpeechContext
from .sequence import SpeechCmd

if TYPE_CHECKING:
	from .settings import PipelineSettings


def _split_by(regex: re.Pattern, text: str) -> Iterator[tuple[Literal["text", "match"], str | re.Match]]:
	"""Yield ("text", str) for the non-empty parts between matches and ("match", Match) for each match."""
	pos = 0
	for match in regex.finditer(text):
		if match.start() > pos:
			yield ("text", text[pos : match.start()])
		yield ("match", match)
		pos = match.end()
	if pos < len(text):
		yield ("text", text[pos:])


_PUNCTUATION_RE_CACHE: dict[str, re.Pattern] = {}


def _get_punctuation_regex(chars: str) -> re.Pattern:
	regex = _PUNCTUATION_RE_CACHE.get(chars)
	if regex is None:
		# Match the entire punctuation run only when it is not followed by
		# a digit. This preserves "12,500" and "3.5", while allowing a
		# sentence-ending mark after a digit, as in "There are 5. Next".
		# Checking for another configured mark also prevents backtracking
		# into a partial run when the complete run precedes a digit.
		escaped_chars = re.escape(chars)
		regex = re.compile(rf"[{escaped_chars}]+(?![{escaped_chars}\d])")
		_PUNCTUATION_RE_CACHE[chars] = regex
	return regex


def _split_punctuation_segments(
	text: str,
	regex: re.Pattern,
) -> Iterator[tuple[str, str]]:
	"""
	Split *text* into ("text"|"punct", value) segments.

	Consecutive punctuation marks form a single "punct" segment, and any
	punctuation run surrounded by digits (e.g. the comma in "12,500" or the
	dot in "3.5") is part of a "text" segment.
	"""
	for kind, value in _split_by(regex, text):
		if kind == "text":
			yield ("text", value)
		else:
			yield ("punct", value.group())


def inject_punctuation_pause(
	speechSequence: Iterable[SpeechCmd],
	settings: "PipelineSettings",
	ctx: SpeechContext,
) -> Iterator[SpeechCmd]:
	"""
	Insert pauses at eligible punctuation and optionally omit those marks
	from the text sent to the synthesizer.

	* The punctuation pause switch turns the whole stage on or off. With it
	  off, or with no configured characters, the sequence passes through
	  unchanged.
	* With the switch on, every pause point gets a PunctuationBreakCommand,
	  even when its duration is 0 ms; a 0 ms break still separates the text
	  on either side of it.
	* Works both between consecutive text items and *inside* a single text
	  item, because a screen reader usually sends a whole sentence as one
	  command.
	* Consecutive punctuation marks count as a single pause point, and
	  numeric punctuation such as the comma in "12,500" is skipped.
	* The pause is only inserted when real text follows, and never as the
	  last command of a sequence, so the voice cannot fall silent at the end.
	* The pause length is capped (see PipelineSettings.scaled_punctuation_wait),
	  so the voice never stops for a long silence at punctuation no matter how
	  high the configured factor is.
	* An existing BreakCommand between two text items suppresses only the
	  boundary pause of the item before it. A mark that opens the next item
	  is an internal pause point, so it still gets this pause after the
	  existing break, as in ["a", existing, ". b"].
	* Removal only decides whether the mark at a pause point is dropped. A
	  mark at the end of an item is dropped even when an existing
	  BreakCommand, not this stage, supplies the pause.
	* Removal never brings two number breaks together. When it empties an
	  item between two NumberBreakCommands (only commands and blank text
	  otherwise), the one after it is dropped, so the earlier one is the only
	  pause: ["12", NB, ".", NB, "5"] with an unnamed "." becomes
	  ["12", NB, "5"]. Every other break stays, as removal changes only marks.
	* An edge break of the number stage (NumberEdgeBreakCommand) does not
	  suppress a boundary pause: "Total. 12" in number mode keeps its pause
	  before the number. Only the other breaks do.
	* Where breaks meet around an edge break (between two non-blank text
	  items, with only blank text and other commands among them), only one
	  is kept: the longest, on a tie the first that is not an edge break.
	  The punctuation pause the user tuned for a mark then wins over the
	  short number pause, and a 0 ms one never leaves a number glued to the
	  text. Breaks that meet without an edge break are left as they are.
	"""
	if not settings.punctuation_pause_enabled:
		yield from speechSequence
		return

	# Every character listed counts, a space included: entering one makes each space a pause point.
	chars = settings.punctuation_pause_characters
	if not chars:
		# An empty character class would not compile (see _get_punctuation_regex).
		yield from speechSequence
		return

	yield from _merge_edge_breaks(_punctuation_pauses(speechSequence, settings, chars))


def _punctuation_pauses(
	speechSequence: Iterable[SpeechCmd],
	settings: "PipelineSettings",
	chars: str,
) -> Iterator[SpeechCmd]:
	"""inject_punctuation_pause without the merge of the breaks around an edge break."""
	remove_punctuation = settings.remove_punctuation_characters
	pause_cmd = PunctuationBreakCommand(settings.scaled_punctuation_wait())
	regex = _get_punctuation_regex(chars)

	def is_non_blank_text(command: SpeechCmd) -> bool:
		return isinstance(command, str) and bool(command.strip())

	def emit(item: SpeechCmd, pause_text_follows: bool, removal_text_follows: bool) -> Iterator[SpeechCmd]:
		if not isinstance(item, str):
			yield item
			return
		parts = list(_split_punctuation_segments(item, regex))
		stripped = item.rstrip()
		boundary_eligible = bool(stripped and stripped[-1] in chars and removal_text_follows)
		boundary_pause = bool(stripped and stripped[-1] in chars and pause_text_follows)
		last_punctuation_index = max(
			(index for index, (kind, _) in enumerate(parts) if kind == "punct"),
			default=-1,
		)
		internal_pause_points = {
			index
			for index, (kind, _) in enumerate(parts)
			if kind == "punct"
			and any(
				later_kind == "text" and later_value.strip() for later_kind, later_value in parts[index + 1 :]
			)
		}
		if remove_punctuation and not internal_pause_points and not boundary_eligible:
			yield item
			return
		for index, (kind, value) in enumerate(parts):
			if kind == "text":
				yield value
				continue
			eligible_here = index in internal_pause_points
			if not remove_punctuation or not (
				eligible_here or boundary_eligible and index == last_punctuation_index
			):
				yield value
			if eligible_here:
				yield pause_cmd
		# The item ends with a punctuation mark (its last significant
		# character is a configured one); pause before the next text item.
		if boundary_pause:
			yield pause_cmd

	it = iter(speechSequence)
	try:
		previous = next(it)
	except StopIteration:
		return

	pending_breaks = []
	# The last break sent since the last non-blank text, if any.
	last_break = None
	for current in it:
		if isinstance(current, BreakCommand):
			pending_breaks.append(current)
			continue
		text_follows = is_non_blank_text(current)
		# An edge break alone does not suppress the boundary pause; _merge_edge_breaks keeps one of the two.
		pause_follows = text_follows and all(map(_is_edge_break, pending_breaks))
		emitted = list(emit(previous, pause_follows, text_follows))
		removed = is_non_blank_text(previous) and not any(map(is_non_blank_text, emitted))
		if (
			removed
			and isinstance(last_break, NumberBreakCommand)
			and pending_breaks
			and isinstance(pending_breaks[0], NumberBreakCommand)
		):
			# Removal left the number breaks around the item next to each other: keep the earlier.
			del pending_breaks[0]
		for command in (*emitted, *pending_breaks):
			if is_non_blank_text(command):
				last_break = None
			elif isinstance(command, BreakCommand):
				last_break = command
			yield command
		pending_breaks.clear()
		previous = current

	yield from emit(previous, False, False)
	yield from pending_breaks
