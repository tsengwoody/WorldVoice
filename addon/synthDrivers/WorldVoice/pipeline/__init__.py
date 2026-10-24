import re
import uuid
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from functools import wraps
from typing import TYPE_CHECKING, Literal, Union

import config
import speechDictHandler
from logHandler import log
from speech.commands import BreakCommand, LangChangeCommand
from speech.extensions import filter_speechSequence

from .._speechcommand import WVLangChangeCommand
from ..log import PipelineLog
from ..numberLanguage import FOLLOW, MAIN
from ..runtime.models import SelectVoice
from . import speech_dictionary
from .context import GENERIC_CONTEXT as GENERIC_CONTEXT, SpeechContext, current_context
from .numbers import NUMBER_RE, number_pieces, split_spaced_numbers, strip_thousands
from .settings import pipeline_settings, read_stored
from .symbols import symbol_namer

if TYPE_CHECKING:
	from speech.commands import SpeechCommand

	from .settings import PipelineSettings

SpeechCmd = Union[str, "SpeechCommand"]
pl = PipelineLog("pipeline.csv")

_CH_SPACE_RE = re.compile(r"(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])")


class NumberBreakCommand(BreakCommand):
	"""Pause between numbers, and between the pieces and symbol names of a number in number and group modes,
	and between two numbers that only whitespace separates, in number and group modes."""


class NumberEdgeBreakCommand(NumberBreakCommand):
	"""Pause between a number and the text next to it in its item (number and group modes)."""


# Set on the plain BreakCommand another synth gets for a NumberEdgeBreakCommand (_plain_breaks), so
# the punctuation stage still tells an edge break apart.
_EDGE_MARKER = "worldvoice_number_edge"


def _is_edge_break(command: SpeechCmd) -> bool:
	return isinstance(command, NumberEdgeBreakCommand) or bool(getattr(command, _EDGE_MARKER, False))


class PunctuationBreakCommand(BreakCommand):
	"""Pause after a configured punctuation mark."""


def listable(func):
	@wraps(func)
	def wrapper(speechSequence):
		speechSequence = list(speechSequence)
		speechSequence = func(speechSequence)
		speechSequence = list(speechSequence)
		return speechSequence

	return wrapper


def speech_viewer(speechSequence, settings: "PipelineSettings", ctx: SpeechContext):
	return list(speechSequence)


def remove_thousands_separators(speechSequence, settings: "PipelineSettings", ctx: SpeechContext):
	"""In value mode, drop the commas of each valid thousands run: "12,345,678" -> "12345678".

	It runs before the number language, which would otherwise cut the run away from the text
	before it ("a,1,234" must stay as it is), and is logged as part of the number mode.
	"""
	if settings.number_mode != "value":
		yield from speechSequence
		return
	for item in speechSequence:
		if isinstance(item, str):
			yield strip_thousands(item)
		else:
			yield item


def apply_speech_dictionaries(speechSequence, settings: "PipelineSettings", ctx: SpeechContext):
	for item in speechSequence:
		if isinstance(item, str):
			yield speechDictHandler.processText(item)
		else:
			yield item


_MISSING = object()


def _insert_between(
	speechSequence: Iterable[SpeechCmd],
	should_break: Callable[[SpeechCmd, SpeechCmd], bool],
	break_cmd: SpeechCmd,
) -> Iterator[SpeechCmd]:
	"""Yield *speechSequence* with *break_cmd* between each adjacent pair that *should_break* accepts."""
	previous = _MISSING
	for current in speechSequence:
		if previous is not _MISSING:
			yield previous
			if should_break(previous, current):
				yield break_cmd
		previous = current
	if previous is not _MISSING:
		yield previous


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


_WORD_CHARACTER_RE = re.compile(r"\w")


def _split_numbers_for_language(text: str, number_re: re.Pattern = NUMBER_RE) -> Iterator[tuple[str, str]]:
	"""Yield ("text", str) and ("number", str) parts of *text* for a number-language wrapper.

	A sign right after a word character is a hyphen, as in "COVID-19" or "中-1", and stays with the
	text before it; after a space, punctuation or at the start it moves with the number (decided by
	the user, 2026-10-23). NVDA's own negative-number rule reads a sign the same way
	(its negative number rule in locale/en/symbols.dic). The number stage (inject_numbers) cuts
	numbers here in every mode; the number pause between numbers (number_wait_factor) keeps
	NUMBER_RE's matches.
	"""
	position = 0
	for match in number_re.finditer(text):
		start = match.start()
		if text[start] in "+-" and start > 0 and _WORD_CHARACTER_RE.match(text[start - 1]):
			start += 1
		if start > position:
			yield ("text", text[position:start])
		yield ("number", text[start : match.end()])
		position = match.end()
	if position < len(text):
		yield ("text", text[position:])


def _both_text(previous: SpeechCmd, current: SpeechCmd) -> bool:
	return isinstance(previous, str) and isinstance(current, str)


def _both_numbers(previous: SpeechCmd, current: SpeechCmd) -> bool:
	# Whole items only: "12", "-3.5", "5-3" and "12:30" are numbers, "12abc" and "1." are not.
	return (
		_both_text(previous, current)
		and bool(NUMBER_RE.fullmatch(previous))
		and bool(NUMBER_RE.fullmatch(current))
	)


def item_wait_factor(
	speechSequence: Iterable[SpeechCmd],
	settings: "PipelineSettings",
	ctx: SpeechContext,
) -> Iterator[SpeechCmd]:
	"""Insert a BreakCommand between every two consecutive plain-text items."""
	wait_factor = settings.scaled_item_wait()
	if wait_factor <= 0:
		yield from speechSequence
		return
	yield from _insert_between(speechSequence, _both_text, BreakCommand(wait_factor))


def _remove_space(
	speechSequence: Iterable[SpeechCmd],
) -> Iterator[SpeechCmd]:
	"""
	Yield items from *speechSequence* while removing blank strings on the fly.

	* If the item is a string:
		– Strip leading/trailing whitespace.
		– Yield the string only when the stripped result is non‑empty.
	* If the item is not a string (e.g., BreakCommand, IndexCommand),
	  yield it unchanged.

	The function is a generator, so elements are streamed without
	constructing an intermediate list.
	"""
	for cmd in speechSequence:
		if isinstance(cmd, str):
			stripped = cmd.strip()
			if stripped:
				yield stripped
			# Blank strings are skipped entirely.
		else:
			yield cmd


def _split_numbers(speechSequence: Iterable[SpeechCmd]) -> Iterator[SpeechCmd]:
	for item in speechSequence:
		if isinstance(item, str):
			yield from split_spaced_numbers(item)
		else:
			yield item


def number_wait_factor(
	speechSequence: Iterable[SpeechCmd],
	settings: "PipelineSettings",
	ctx: SpeechContext,
) -> Iterator[SpeechCmd]:
	"""
	Pause between numbers: between two items that are each a whole number, even
	with language commands between them, and between numbers that only whitespace
	separates inside one item, which become items of their own. Blank text items
	are dropped and the others stripped.
	"""
	wait_factor = settings.scaled_number_wait()
	if wait_factor <= 0:
		yield from speechSequence
		return
	yield from _insert_number_breaks(
		_split_numbers(_remove_space(speechSequence)),
		NumberBreakCommand(wait_factor),
	)


def _insert_number_breaks(speechSequence: Iterable[SpeechCmd], break_cmd: SpeechCmd) -> Iterator[SpeechCmd]:
	"""Yield *speechSequence* with *break_cmd* between two adjacent whole numbers.

	Language commands are transparent: a number language wraps each number as
	"en", "1", "zh", "en", "2", "zh", and the break goes after the first language
	command between the two numbers. Any other command still keeps the numbers apart.
	"""
	previous = _MISSING
	held: list[SpeechCmd] = []
	for item in speechSequence:
		if isinstance(item, (LangChangeCommand, WVLangChangeCommand)):
			held.append(item)
			continue
		if previous is not _MISSING and _both_numbers(previous, item):
			yield from held[:1]
			yield break_cmd
			yield from held[1:]
		else:
			yield from held
		held.clear()
		yield item
		previous = item
	yield from held


def remove_language_command(speechSequence):
	for command in speechSequence:
		# Handle language-change commands
		if isinstance(command, WVLangChangeCommand):
			continue
		else:
			yield command


def wrap_numbers_for_detection(
	speechSequence: Iterable[SpeechCmd],
	ctx: SpeechContext,
	joins: dict[int, bool] | None = None,
) -> Iterator[SpeechCmd]:
	"""
	Wrap every number in WVLangChangeCommands for the number language, so language detection
	reads it there instead of in the text around it.

	"main" wraps each number in the language in force (the last language command, or the synth's
	language), a locale in that locale; each wrapper closes with the language in force. *joins*
	gets id(wrapper) -> whether text of the same item is on both sides of it.
	"""
	language = ctx.language
	for item in speechSequence:
		if not isinstance(item, str):
			if isinstance(item, (LangChangeCommand, WVLangChangeCommand)):
				language = item.lang or ctx.language
			yield item
			continue
		target = language if ctx.number_language == MAIN else ctx.number_language
		position = 0
		for kind, value in _split_numbers_for_language(item):
			start, position = position, position + len(value)
			if kind == "text":
				yield value
				continue
			opening, closing = WVLangChangeCommand(target), WVLangChangeCommand(language)
			if joins is not None:
				joins[id(opening)] = start > 0
				joins[id(closing)] = position < len(item)
			yield opening
			yield value
			yield closing


def detect_with_number_language(
	speechSequence: Iterable[SpeechCmd],
	detect: Callable[[Iterable[SpeechCmd]], Iterable[SpeechCmd]],
	ctx: SpeechContext,
) -> list[SpeechCmd]:
	"""
	Language detection that reads every number in the number language.

	Unless the number language is "default" (numbers follow the text), each number is wrapped for
	*detect*, which then keeps it in the number language. The wrappers that keep the voice are
	dropped afterwards and the text they split joins up again, so NVDA, when detection runs before
	it, processes each item as it was: its symbol rules read the text around a number (a negative
	sign, "1st", a sentence end). Nothing joins across another command or across two items.
	"""
	if not (ctx.supports_roles and ctx.number_language != FOLLOW):
		return list(detect(speechSequence))
	# Wrappers are told apart by id(): every wrapper stays alive in *detected* until the loop below
	# ends, so no other object can take over one of these ids during the pass.
	joins: dict[int, bool] = {}
	detected = list(detect(list(wrap_numbers_for_detection(speechSequence, ctx, joins))))
	kept = {id(item) for item in deduplicate_language_command(detected, ctx) if id(item) in joins}
	result: list[SpeechCmd] = []
	glue = False
	for item in detected:
		if id(item) in joins and id(item) not in kept:
			glue = glue or joins[id(item)]
			continue
		if glue and isinstance(item, str) and result and isinstance(result[-1], str):
			result[-1] += item
		else:
			result.append(item)
		glue = False
	return result


def _translate_number(
	raw: str,
	mode: str,
	group_size: int,
	number_pause: int,
	name_of: Callable[[str], str | None],
) -> Iterator[SpeechCmd]:
	"""Speak one number match in *mode*: its pieces (numbers.number_pieces), with a number break
	between every two, even at pause 0, so each reaches the synth as an item of its own."""
	pieces = number_pieces(raw, mode, group_size, name_of)
	# One break instance per number, as the synth only reads its time.
	separator = NumberBreakCommand(number_pause)
	for index, piece in enumerate(pieces):
		if index:
			yield separator
		yield piece


def inject_numbers(
	speechSequence: Iterable[SpeechCmd],
	settings: "PipelineSettings",
	ctx: SpeechContext,
) -> Iterator[SpeechCmd]:
	"""
	Speak each number of a text item in its number language and number mode.

	Numbers are found once, with the number-language rule (_split_numbers_for_language), and each
	gets, in order: its edge pauses, the wrapper of its number language, and the pieces of its
	number mode (decided by the user, 2026-10-24, U5). A synth without roles gets no wrapper, and
	the WVLangChangeCommands it was sent are dropped.

	Two cases pass the sequence on as it is: "off" without a locale number language leaves numbers
	alone, without even the dot rule, and "default" and "main" wrap a number in the language in
	force, which deduplicate_language_command would drop again. With detection on, "main" numbers
	are wrapped where detection runs (detect_with_number_language).
	"""
	mode = settings.number_mode
	wraps = ctx.supports_roles and ctx.number_language not in (FOLLOW, MAIN)
	if not ctx.supports_roles:
		speechSequence = remove_language_command(speechSequence)
	if mode == "none" and not wraps:
		yield from speechSequence
		return
	group_size = settings.group_size
	pause = settings.scaled_number_wait()
	edge = gap_break = None
	number_language = ctx.number_language if wraps else None
	# Symbols are named for the number language, the language of the wrapper around every number;
	# with no number language, for the language in force at that point of the sequence. The locale
	# is that of the voice that speaks the language, when NVDA has a table for it (symbols.symbol_locale).
	namer = symbol_namer(ctx.voice_locale_for_language)
	language = ctx.language
	for item in speechSequence:
		if not isinstance(item, str):
			if isinstance(item, (LangChangeCommand, WVLangChangeCommand)):
				language = item.lang or ctx.language
			yield item
			continue
		segments = _number_item_segments(
			item,
			mode=mode,
			group_size=group_size,
			pause=pause,
			name_of=namer(number_language or language),
			number_language=number_language,
			language=language,
			edge=edge,
			gap_break=gap_break,
		)
		if wraps:
			# The language in force here may not be the context's (phase 30 item 6).
			segments = deduplicate_language_command(segments, ctx, start_language=language)
		yield from merge_consecutive_strings(segments)


def _number_item_segments(
	item: str,
	*,
	mode: str,
	group_size: int,
	pause: int,
	name_of: Callable[[str], str | None],
	number_language: str | None,
	language: str | None,
	edge: SpeechCmd | None,
	gap_break: SpeechCmd | None,
) -> Iterator[SpeechCmd]:
	"""The segments of one text item: its text, and each number with its pauses, wrapper and pieces.

	*number_language* is the language of the wrapper, or None for no wrapper; the wrapper closes with
	*language*, the language in force. A "." right after a number, or right before one, is spoken
	apart from it, in every mode but "none".
	"""
	parts = list(_split_numbers_for_language(item))
	for index, (kind, value) in enumerate(parts):
		if kind == "text":
			if mode != "none" and index > 0 and value[0] == ".":
				yield " "
			yield value
			if mode != "none" and index + 1 < len(parts) and value.endswith("."):
				yield " "
			continue
		if number_language is not None:
			yield WVLangChangeCommand(number_language)
		if mode == "none":
			yield value
		else:
			yield from _translate_number(value, mode, group_size, pause, name_of)
		if number_language is not None:
			yield WVLangChangeCommand(language)


def merge_consecutive_strings(items):
	buffer = ""
	for item in items:
		if isinstance(item, str):
			buffer += item
		else:
			if buffer:
				yield buffer
				buffer = ""
			yield item
	if buffer:
		yield buffer


def inject_chinese_space_pause(
	speechSequence: Iterable[SpeechCmd],
	settings: "PipelineSettings",
	ctx: SpeechContext,
) -> Iterator[SpeechCmd]:
	waitfactor = settings.scaled_chinesespace_wait()
	if waitfactor <= 0:
		yield from speechSequence
		return

	pause_cmd = BreakCommand(waitfactor)

	for item in speechSequence:
		# non-string commands flow through untouched
		if not isinstance(item, str):
			yield item
			continue

		# the space between two CJK characters becomes the pause
		for kind, value in _split_by(_CH_SPACE_RE, item):
			if kind == "text":
				yield value
			else:
				yield pause_cmd


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


def _merge_edge_breaks(speechSequence: Iterable[SpeechCmd]) -> Iterator[SpeechCmd]:
	"""Yield *speechSequence* with each run that holds an edge break and another break cut to one break.

	A run is what lies between two non-blank text items (or before the first, or after the last):
	breaks, blank text and other commands. The break kept is the longest; on a tie the first that is
	not an edge break, or the first edge break. The other items of the run keep their order. Runs are
	told apart by position: one break object can sit in several runs.
	"""
	run: list[SpeechCmd] = []
	for item in speechSequence:
		if isinstance(item, str) and item.strip():
			yield from _merged_run(run)
			run.clear()
			yield item
		else:
			run.append(item)
	yield from _merged_run(run)


def _merged_run(run: list[SpeechCmd]) -> list[SpeechCmd]:
	breaks = [index for index, item in enumerate(run) if isinstance(item, BreakCommand)]
	if len(breaks) < 2 or not any(_is_edge_break(run[index]) for index in breaks):
		return run
	# max keeps the first of equal keys.
	kept = max(breaks, key=lambda index: (run[index].time, not _is_edge_break(run[index])))
	return [item for index, item in enumerate(run) if index == kept or not isinstance(item, BreakCommand)]


def deduplicate_language_command(speechSequence, ctx: SpeechContext, start_language=None):
	"""
	Stream *speech_sequence* and emit only the language-change commands
	that actually switch to a different voice.

	Workflow
	--------
	1. Walk through the sequence while tracking the *current language*
	   and the *current voice name*.
	2. Yield a LangChangeCommand only when it maps to a **different**
	   voice than the one currently in use.
	3. Forward all non-language-change commands unchanged.

	Voices are compared by name, so filtering creates no voice instances.
	*start_language* is the language already in force where the sequence
	begins, when that is not the context's language.
	"""
	# Initial voice / language; a context without a default voice compares None.
	voice_name = default_name = ctx.default_voice_name
	current_language = default_language = ctx.language
	if start_language is not None and start_language != default_language:
		current_language = start_language
		voice_name = ctx.voice_name_for_language(start_language) or default_name

	for command in speechSequence:
		# Handle language-change commands
		if isinstance(command, (LangChangeCommand, WVLangChangeCommand)):
			# Skip if the language is actually unchanged
			if command.lang == current_language:
				continue

			# Resolve the new language and its voice
			if command.lang is None:  # Revert to default language
				new_name = default_name
				current_language = default_language
			else:
				# Fall back to the default voice when no voice speaks the language
				new_name = ctx.voice_name_for_language(command.lang) or default_name
				current_language = command.lang

			# Skip if the voice remains the same
			if new_name == voice_name:
				continue

			# Effective switch: update state and yield the command
			voice_name = new_name
			yield command
		# Forward all other commands
		else:
			yield command


def lang_cmd_to_voice(
	speechSequence: Iterable[SpeechCmd],
	ctx: SpeechContext,
) -> Iterator[SpeechCmd]:
	"""
	Convert each LangChangeCommand / WVLangChangeCommand into a voice key.
	All other commands pass through unchanged.
	"""
	for cmd in speechSequence:
		if isinstance(cmd, (LangChangeCommand, WVLangChangeCommand)):
			lang = cmd.lang or ctx.default_voice_language
			yield SelectVoice(ctx.voice_name_for_language(lang) or ctx.default_voice_name)
		else:
			yield cmd


def inject_langchange_reorder(
	speechSequence: Iterable[SpeechCmd],
) -> Iterator[SpeechCmd]:
	"""
	Re-order language-change commands so that any LangChangeCommand /
	WVLangChangeCommand is emitted *before* the group of commands and
	text it belongs to.
	* LangChangeCmd ─→ prepend to current buffer, then flush buffer.
	* plain string   ─→ append to buffer, then flush buffer.
	* other commands ─→ just accumulate.
	"""
	buffer: list[SpeechCmd] = []

	for cmd in speechSequence:
		if isinstance(cmd, (LangChangeCommand, WVLangChangeCommand)):
			# 1. put language switch at the *front* of this mini-chunk
			buffer.insert(0, cmd)
			# 2. flush the whole chunk in order
			yield from buffer
			buffer.clear()

		elif isinstance(cmd, str):
			# accumulate text, then flush together with prior controls
			buffer.append(cmd)
			yield from buffer
			buffer.clear()

		else:
			# other control commands: keep buffering
			buffer.append(cmd)

	# flush any trailing commands at end of sequence
	if buffer:
		yield from buffer


class _LogWriter:
	"""Write pipeline log rows without letting a failed write reach NVDA's filter.

	NVDA's Filter.apply keeps the input after an exception, and a logged stage has read that
	generator already, so a raised write would leave the rest of the pipeline nothing to speak.
	The first failure of an outage is logged; the next successful write ends the outage.
	"""

	def __init__(self):
		self._failing = False

	def write(self, *row):
		try:
			pl.write(*row)
		except Exception:
			# A full disk raises OSError; a command whose repr cannot be encoded, ValueError.
			if not self._failing:
				log.error("WorldVoice could not write its pipeline log", exc_info=True)
			self._failing = True
		else:
			self._failing = False


_log_writer = _LogWriter()


def _run_logged(label, fn, speechSequence, settings, ctx, switches=None):
	"""Run one stage, logged under *label* when debugging or recording and any of *switches*
	(by default the switch named *label*) is on."""
	debug = config.conf["general"]["loggingLevel"] == "DEBUG"
	section = config.conf["WorldVoice"]["log"]
	# A switch NVDA refuses on read is off, so a bad stored value never stops the stage.
	recording = read_stored(section, "enable", False)
	switched_on = any(read_stored(section, key, False) for key in switches or (label,))
	if not ((debug or recording) and switched_on):
		return fn(speechSequence, settings, ctx)
	_id = uuid.uuid4().hex
	speechSequence = list(speechSequence)
	if debug:
		log.debug(f"speech sequence before {label} pipeline: {speechSequence}")
	if recording:
		_log_writer.write(_id, label, "before", speechSequence)
	speechSequence = list(fn(speechSequence, settings, ctx))
	if debug:
		log.debug(f"speech sequence after {label} pipeline: {speechSequence}")
	if recording:
		_log_writer.write(_id, label, "after", speechSequence)
	return speechSequence


def _plain_breaks(speechSequence: Iterable[SpeechCmd]) -> list[SpeechCmd]:
	"""The sequence with each BreakCommand subclass replaced by a plain BreakCommand.

	NVDA's speechXml, which OneCore uses, finds a command's converter by its class name and
	drops the rest of the utterance at a command it has none for. A break made from an edge break
	(or from a plain one already marked) carries _EDGE_MARKER, so the punctuation stage still tells
	it apart. NVDA's BreakCommand has no __slots__ and its __eq__ reads only type and time, and the
	synths read only .time, so the attribute is invisible to them.
	"""
	return [_plain_break(item) if isinstance(item, BreakCommand) else item for item in speechSequence]


def _plain_break(command: BreakCommand) -> BreakCommand:
	plain = BreakCommand(command.time)
	if _is_edge_break(command):
		setattr(plain, _EDGE_MARKER, True)
	return plain


def _stage_handler(log_key, fn, switches):
	def handler(speechSequence):
		ctx = current_context()
		settings = pipeline_settings.effective(ctx.supports_roles)
		result = _run_logged(log_key, fn, speechSequence, settings, ctx, switches)
		# Only WorldVoice tells the pauses apart; another synth gets plain breaks.
		return result if ctx.supports_roles else _plain_breaks(result)

	# Not functools.wraps: NVDA binds filter values against inspect.signature,
	# which would follow __wrapped__ to the three-argument stage function.
	handler.__name__ = handler.__qualname__ = fn.__name__
	handler.__doc__ = fn.__doc__
	return handler


@dataclass(frozen=True)
class Stage:
	"""One speech-sequence filter. Its handler is bound once, so NVDA's weak registry keeps it."""

	log_key: str
	fn: Callable[..., Iterable[SpeechCmd]]
	# False: the stage logs under the switch of a later stage with the same log key.
	log_switch: bool = True
	# The switches that also turn this stage's log on; its rows still carry its log key.
	also_logged_by: tuple[str, ...] = ()
	handler: Callable[[Iterable[SpeechCmd]], Iterable[SpeechCmd]] = field(
		init=False,
		repr=False,
		compare=False,
	)

	def __post_init__(self):
		switches = (*self.also_logged_by, self.log_key)
		object.__setattr__(self, "handler", _stage_handler(self.log_key, self.fn, switches))


# The order NVDA runs the filters in; register, reorder and the log switches derive from it.
STAGES: tuple[Stage, ...] = (
	Stage("apply_speech_dictionaries", apply_speech_dictionaries),
	Stage("number_mode", remove_thousands_separators, log_switch=False),
	Stage("number_mode", inject_numbers, also_logged_by=("number_language",)),
	Stage("chinesespace_wait_factor", inject_chinese_space_pause),
	Stage("item_wait_factor", item_wait_factor),
	Stage("punctuation_wait_factor", inject_punctuation_pause),
	Stage("number_wait_factor", number_wait_factor),
	Stage("speech_viewer", speech_viewer),
)


def _log_switches(stages: Iterable[Stage]) -> tuple[str, ...]:
	"""Each switch of the stages with a switch of their own once: its also_logged_by keys, then its log key."""
	keys = (key for stage in stages if stage.log_switch for key in (*stage.also_logged_by, stage.log_key))
	return tuple(dict.fromkeys(keys))


# One log switch per log key, in the order of the stage that owns it.
LOG_SWITCHES: tuple[str, ...] = _log_switches(STAGES)


def order_move_to_start_register():
	# Move to the front in reverse, so STAGES runs first and in order.
	for stage in reversed(STAGES):
		filter_speechSequence.moveToEnd(stage.handler, False)


def register_stages():
	log.debug("register pipeline stages")
	speech_dictionary.install()
	for stage in STAGES:
		filter_speechSequence.register(stage.handler)
	order_move_to_start_register()


def unregister_stages():
	log.debug("unregister pipeline stages")
	for stage in STAGES:
		filter_speechSequence.unregister(stage.handler)
	speech_dictionary.uninstall()
