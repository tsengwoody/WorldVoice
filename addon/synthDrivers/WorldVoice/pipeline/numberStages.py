"""The number stages: the thousands step, number mode and number language (inject_numbers) and
the pause between numbers (number_wait_factor); and the number language for language detection."""

import re
from collections.abc import Callable, Iterable, Iterator
from typing import TYPE_CHECKING

from speech.commands import ConfigProfileTriggerCommand, EndUtteranceCommand, LangChangeCommand

from ..numberLanguage import FOLLOW, MAIN
from ..speechCommands import WVLangChangeCommand
from .breaks import NumberBreakCommand, NumberEdgeBreakCommand, NumberItemEdgeBreakCommand, _merge_edge_breaks
from .context import SpeechContext
from .languageCommands import deduplicate_language_command, remove_language_command
from .numbers import NUMBER_RE, number_pieces, split_spaced_numbers, strip_thousands
from .sequence import _MISSING, SpeechCmd, _both_text
from .symbols import symbol_namer

if TYPE_CHECKING:
	from .settings import PipelineSettings


def remove_thousands_separators(speech_sequence, settings: "PipelineSettings", ctx: SpeechContext):
	"""In value mode, drop the commas of each valid thousands run: "12,345,678" -> "12345678".

	It runs before the number language, which would otherwise cut the run away from the text
	before it ("a,1,234" must stay as it is), and is logged as part of the number mode.
	"""
	if settings.number_mode != "value":
		yield from speech_sequence
		return
	for item in speech_sequence:
		if isinstance(item, str):
			yield strip_thousands(item)
		else:
			yield item


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


def _both_numbers(previous: SpeechCmd, current: SpeechCmd) -> bool:
	# Whole items only: "12", "-3.5", "5-3" and "12:30" are numbers, "12abc" and "1." are not.
	return (
		_both_text(previous, current)
		and bool(NUMBER_RE.fullmatch(previous))
		and bool(NUMBER_RE.fullmatch(current))
	)


def _remove_space(
	speech_sequence: Iterable[SpeechCmd],
) -> Iterator[SpeechCmd]:
	"""
	Yield items from *speech_sequence* while removing blank strings on the fly.

	* If the item is a string:
		– Strip leading/trailing whitespace.
		– Yield the string only when the stripped result is non‑empty.
	* If the item is not a string (e.g., BreakCommand, IndexCommand),
	  yield it unchanged.

	The function is a generator, so elements are streamed without
	constructing an intermediate list.
	"""
	for cmd in speech_sequence:
		if isinstance(cmd, str):
			stripped = cmd.strip()
			if stripped:
				yield stripped
			# Blank strings are skipped entirely.
		else:
			yield cmd


def _split_numbers(speech_sequence: Iterable[SpeechCmd]) -> Iterator[SpeechCmd]:
	for item in speech_sequence:
		if isinstance(item, str):
			yield from split_spaced_numbers(item)
		else:
			yield item


def number_wait_factor(
	speech_sequence: Iterable[SpeechCmd],
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
		yield from speech_sequence
		return
	yield from _insert_number_breaks(
		_split_numbers(_remove_space(speech_sequence)),
		NumberBreakCommand(wait_factor),
	)


def _insert_number_breaks(speech_sequence: Iterable[SpeechCmd], break_cmd: SpeechCmd) -> Iterator[SpeechCmd]:
	"""Yield *speech_sequence* with *break_cmd* between two adjacent whole numbers.

	Language commands are transparent: a number language wraps each number as
	"en", "1", "zh", "en", "2", "zh", and the break goes after the first language
	command between the two numbers. Any other command still keeps the numbers apart.
	"""
	previous = _MISSING
	held: list[SpeechCmd] = []
	for item in speech_sequence:
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


def wrap_numbers_for_detection(
	speech_sequence: Iterable[SpeechCmd],
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
	for item in speech_sequence:
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
	speech_sequence: Iterable[SpeechCmd],
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
		return list(detect(speech_sequence))
	# Wrappers are told apart by id(): every wrapper stays alive in *detected* until the loop below
	# ends, so no other object can take over one of these ids during the pass.
	joins: dict[int, bool] = {}
	detected = list(detect(list(wrap_numbers_for_detection(speech_sequence, ctx, joins))))
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
	speech_sequence: Iterable[SpeechCmd],
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

	The edge pauses go on each side of a number with spoken text anywhere in the sequence, in its
	item or another, whatever commands lie between; none before the first spoken item or after the
	last (corrected by fix/number-edge-pause-items, decided by the user, 2026-10-24). The sequence
	here is one utterance: NVDA splits the filtered sequence at an EndUtteranceCommand or a
	ConfigProfileTriggerCommand (_ends_utterance, review I1). Where breaks
	meet around an edge break, only one stays (_merge_edge_breaks): two numbers at the end and start
	of two items get one pause, and so does a number next to a break of the sequence.
	"""
	mode = settings.number_mode
	wraps = ctx.supports_roles and ctx.number_language not in (FOLLOW, MAIN)
	if not ctx.supports_roles:
		speech_sequence = remove_language_command(speech_sequence)
	if mode == "none" and not wraps:
		yield from speech_sequence
		return
	pause = settings.scaled_number_wait()
	# Decided by the user (2026-10-24, U1, U4): the number pause also goes before and after a number
	# in number and group modes, and a pause of 0 adds no break at all. One instance each per run,
	# as the synth only reads their time.
	if mode in ("number", "group") and pause > 0:
		edges = (NumberEdgeBreakCommand(pause), NumberBreakCommand(pause), NumberItemEdgeBreakCommand(pause))
		yield from _merge_edge_breaks(
			_inject_item_numbers(list(speech_sequence), settings, ctx, wraps, edges),
		)
	else:
		yield from _inject_item_numbers(speech_sequence, settings, ctx, wraps, None)


def _is_spoken(item: SpeechCmd) -> bool:
	return isinstance(item, str) and bool(item.strip())


def _ends_utterance(item: SpeechCmd) -> bool:
	"""Whether NVDA's speech manager ends the utterance at *item*, after the filters ran.

	It splits the sequence at an EndUtteranceCommand (speakSpelling puts one after every character,
	the speech of a text range one at the end of a block), and before a ConfigProfileTriggerCommand of a trigger with a
	profile; one without a profile counts too, as the pipeline cannot know.
	"""
	return isinstance(item, (EndUtteranceCommand, ConfigProfileTriggerCommand))


def _spoken_later(speech_sequence: list[SpeechCmd]) -> list[bool]:
	"""For each index, whether a spoken item comes after it in its utterance."""
	later = [False] * len(speech_sequence)
	spoken = False
	for index in range(len(speech_sequence) - 1, -1, -1):
		later[index] = spoken
		item = speech_sequence[index]
		if _ends_utterance(item):
			spoken = False
		elif _is_spoken(item):
			spoken = True
	return later


def _inject_item_numbers(
	speech_sequence: Iterable[SpeechCmd],
	settings: "PipelineSettings",
	ctx: SpeechContext,
	wraps: bool,
	edges: tuple[SpeechCmd, SpeechCmd, SpeechCmd] | None,
) -> Iterator[SpeechCmd]:
	"""inject_numbers, item by item, without the merge of the breaks around an edge break.

	*edges* is None, or the edge break, the break between two numbers that only whitespace
	separates, and the edge break at an item's start or end; with it, *speech_sequence* is a list.
	"""
	mode = settings.number_mode
	group_size = settings.group_size
	pause = settings.scaled_number_wait()
	edge, gap_break, item_edge = edges or (None, None, None)
	# Whether a spoken item comes before this one in its utterance, and after it (review I1: an
	# utterance, what the synth gets, is the sequence the rule speaks of).
	spoken_before = False
	spoken_after = _spoken_later(speech_sequence) if edges is not None else None
	number_language = ctx.number_language if wraps else None
	# Symbols are named for the number language, the language of the wrapper around every number;
	# with no number language, for the language in force at that point of the sequence. The locale
	# is that of the voice that speaks the language, when NVDA has a table for it (symbols.symbol_locale).
	namer = symbol_namer(ctx.voice_locale_for_language)
	language = ctx.language
	# Whether the wrapper stays, by the language in force: deduplicate_language_command decides it.
	kept: dict[str | None, bool] = {}
	for index, item in enumerate(speech_sequence):
		if not isinstance(item, str):
			if isinstance(item, (LangChangeCommand, WVLangChangeCommand)):
				language = item.lang or ctx.language
			elif _ends_utterance(item):
				spoken_before = False
			yield item
			continue
		if wraps and language not in kept:
			opening = [WVLangChangeCommand(number_language)]
			kept[language] = any(
				True for _ in deduplicate_language_command(opening, ctx, start_language=language)
			)
		segments = _number_item_segments(
			item,
			mode=mode,
			# A "." next to a number is spaced only where the number stays in the text's voice, as
			# before the number stages were merged: next to a number read by another voice the
			# space could be a new punctuation pause point (review I1).
			dot_rule=mode != "none" and not (wraps and kept[language]),
			group_size=group_size,
			pause=pause,
			name_of=namer(number_language or language),
			number_language=number_language,
			language=language,
			edge=edge,
			gap_break=gap_break,
			edge_before=item_edge if spoken_before else None,
			edge_after=item_edge if spoken_after and spoken_after[index] else None,
		)
		spoken_before = spoken_before or _is_spoken(item)
		if wraps:
			# The language in force here may not be the context's (phase 30 item 6).
			segments = deduplicate_language_command(segments, ctx, start_language=language)
		yield from merge_consecutive_strings(segments)


def _number_item_segments(
	item: str,
	*,
	mode: str,
	dot_rule: bool,
	group_size: int,
	pause: int,
	name_of: Callable[[str], str | None],
	number_language: str | None,
	language: str | None,
	edge: SpeechCmd | None,
	gap_break: SpeechCmd | None,
	edge_before: SpeechCmd | None,
	edge_after: SpeechCmd | None,
) -> Iterator[SpeechCmd]:
	"""The segments of one text item: its text, and each number with its pauses, wrapper and pieces.

	*number_language* is the language of the wrapper, or None for no wrapper; the wrapper closes with
	*language*, the language in force. With *dot_rule*, a "." right after a number, or right before
	one, is spoken apart from it.

	With an *edge* break, a number gets it on each side where its item has spoken text, whatever
	that text is (U3), outside the wrapper (O1). Whitespace between two numbers becomes *gap_break*,
	one pause between two numbers (O3). Text parts and numbers alternate, so the text next to a
	number decides. An item that a number begins, or ends, with only whitespace before it, or after
	it, starts with *edge_before*, or ends with *edge_after*, when that is not None: inject_numbers
	passes one where spoken text comes before or after the item (corrected by
	fix/number-edge-pause-items; this replaces O2 and D1, no edge break at an item's start or end).
	"""
	parts = list(_split_numbers_for_language(item))
	last = len(parts) - 1
	spoken_kinds = [kind for kind, value in parts if value.strip()]
	if edge_before is not None and spoken_kinds[:1] == ["number"]:
		yield edge_before
	for index, (kind, value) in enumerate(parts):
		if kind == "text":
			if edge is not None and 0 < index < last and value.isspace():
				yield gap_break
				continue
			if dot_rule and index > 0 and value[0] == ".":
				yield " "
			yield value
			if dot_rule and index < last and value.endswith("."):
				yield " "
			continue
		if edge is not None and index > 0 and parts[index - 1][1].strip():
			yield edge
		if number_language is not None:
			yield WVLangChangeCommand(number_language)
		if mode == "none":
			yield value
		else:
			yield from _translate_number(value, mode, group_size, pause, name_of)
		if number_language is not None:
			yield WVLangChangeCommand(language)
		if edge is not None and index < last and parts[index + 1][1].strip():
			yield edge
	if edge_after is not None and spoken_kinds[-1:] == ["number"]:
		yield edge_after


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
