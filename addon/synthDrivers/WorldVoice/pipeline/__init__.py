import re
import uuid
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from functools import wraps
from itertools import pairwise
from typing import TYPE_CHECKING, Literal, Union

import characterProcessing
import config
import speech
import speechDictHandler
from logHandler import log
from speech.commands import BreakCommand, LangChangeCommand
from speech.extensions import filter_speechSequence
from synthDriverHandler import getSynth

from .._speechcommand import WVLangChangeCommand
from ..log import PipelineLog
from ..runtime.models import SelectVoice
from . import speech_dictionary
from .context import GENERIC_CONTEXT as GENERIC_CONTEXT, SpeechContext, current_context
from .settings import pipeline_settings

if TYPE_CHECKING:
	from speech.commands import SpeechCommand

	from .settings import PipelineSettings

SpeechCmd = Union[str, "SpeechCommand"]
pl = PipelineLog("pipeline.csv")

_COMMA_NUMBER_RE = re.compile(r"(?<=[0-9]),(?=[0-9])")
_PURE_NUMBER_RE = re.compile(r"[0-9]+")
_NUMBER_RE = re.compile(r"[+-]?[0-9]+(?:\.[0-9]+)?")
_CH_SPACE_RE = re.compile(r"(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])")
# No-break spaces group the digits of one number, as in "10 000", so they never join two numbers.
_NO_BREAK_SPACES = frozenset("\u00a0\u202f\u2007")

_SENTENCE_END_RE = re.compile(r"^[.:;,?!](?:\s|$)")


class GroupNumberBreakCommand(BreakCommand):
	"""Pause between digit groups in group number mode."""


class NumberBreakCommand(BreakCommand):
	"""Pause between numbers, and between the digits of a number in digit mode."""


class PunctuationBreakCommand(BreakCommand):
	"""Pause after a configured punctuation mark."""


def with_order_log(label: str):
	"""The order numbers are reversed because of recursion: the order number assigned earlier execution is greater than that of a later execution."""

	def decorator(func):
		@wraps(func)
		def wrapper(speechSequence, *args, **kwargs):
			if config.conf["general"]["loggingLevel"] == "DEBUG":
				try:
					synth = getSynth()
					synth.order += 1
					log.debug(f"{label} order {synth.order}")
				except Exception:  # noqa: BLE001 - debug counter only; never affects speech
					pass
			return func(speechSequence, *args, **kwargs)

		return wrapper

	return decorator


def listable(func):
	@wraps(func)
	def wrapper(speechSequence):
		speechSequence = list(speechSequence)
		speechSequence = func(speechSequence)
		speechSequence = list(speechSequence)
		return speechSequence

	return wrapper


def _symbol_locale(language: str | None) -> str:
	"""The locale to look a symbol name up in, for text spoken in *language*.

	No language (another synth's context) is NVDA's current language, where NVDA's own symbol
	processing starts. NVDA only drops a country after "_", so a "-" becomes "_"; and a bare
	language, as WorldVoice stores number languages, takes the country of NVDA's current
	language when the two agree ("zh" -> "zh_TW"), as NVDA's spelling does.
	"""
	current = speech.getCurrentLanguage()
	if not language:
		return current
	locale = language.replace("-", "_")
	if "_" not in locale and locale.lower() == current.split("_")[0].lower():
		return current
	return locale


def _symbol_name(locale: str, symbol: str) -> str | None:
	"""NVDA's name of *symbol* in *locale*, as when NVDA reads that one character; None without one."""
	try:
		name = characterProcessing.processSpeechSymbol(locale, symbol)
	except LookupError:
		return None
	return name if name and name != symbol else None


def get_translate_table(ctx: SpeechContext) -> dict[int, str]:
	# Build translation table for single digits
	translate_table: dict[int, str] = {}
	if ctx.speech_symbols:
		for d in "0123456789":
			if d in ctx.speech_symbols.symbols:
				sym = ctx.speech_symbols.symbols[d]
				if sym.language in (ctx.number_language, "Windows"):
					translate_table[ord(d)] = sym.replacement or d
	return translate_table


# @with_order_log("speech_view")
def speech_viewer(speechSequence, settings: "PipelineSettings", ctx: SpeechContext):
	return list(speechSequence)


# @with_order_log("ignore_comma_between_number")
def ignore_comma_between_number(speechSequence, settings: "PipelineSettings", ctx: SpeechContext):
	if settings.ignore_comma_between_number:
		yield from (
			_COMMA_NUMBER_RE.sub(lambda m: "", command) if isinstance(command, str) else command
			for command in speechSequence
		)
	else:
		yield from speechSequence


# @with_order_log("apply_speech_dictionaries")
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


def _both_text(previous: SpeechCmd, current: SpeechCmd) -> bool:
	return isinstance(previous, str) and isinstance(current, str)


def _both_numbers(previous: SpeechCmd, current: SpeechCmd) -> bool:
	# Whole items only: "12" and "-3.5" are numbers, "12abc" and "1." are not.
	return (
		_both_text(previous, current)
		and bool(_NUMBER_RE.fullmatch(previous))
		and bool(_NUMBER_RE.fullmatch(current))
	)


# @with_order_log("item_wait_factor")
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


def _is_splittable_gap(gap: str) -> bool:
	"""Whitespace with no no-break space in it: space, tab, newline or U+3000, never U+00A0, U+202F or U+2007."""
	return gap.isspace() and _NO_BREAK_SPACES.isdisjoint(gap)


def _split_spaced_numbers(text: str) -> Iterator[str]:
	"""
	Yield *text* with every number that only whitespace separates from a
	neighbouring number as an item of its own, without that whitespace.

	Everything else is kept verbatim, spaces included, and no empty piece is
	yielded. A number glued to another number with no gap, as in
	"2345-6789", is never split out, so a pause can only replace whitespace.
	A gap that holds a no-break space (U+00A0, U+202F, U+2007) never joins
	two numbers, so "10 000" written with one stays whole.
	"""
	matches = list(_NUMBER_RE.finditer(text))
	gaps = [text[left.end() : right.start()] for left, right in pairwise(matches)]
	glued = {index + side for index, gap in enumerate(gaps) if not gap for side in (0, 1)}
	# joined[i] is True when matches i - 1 and i are split apart; the ends are never joined.
	joined = [
		False,
		*(
			_is_splittable_gap(gap) and index not in glued and index + 1 not in glued
			for index, gap in enumerate(gaps)
		),
		False,
	]
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


def _split_numbers(speechSequence: Iterable[SpeechCmd]) -> Iterator[SpeechCmd]:
	for item in speechSequence:
		if isinstance(item, str):
			yield from _split_spaced_numbers(item)
		else:
			yield item


# @with_order_log("number_wait_factor")
def number_wait_factor(
	speechSequence: Iterable[SpeechCmd],
	settings: "PipelineSettings",
	ctx: SpeechContext,
) -> Iterator[SpeechCmd]:
	"""
	Pause between numbers: between two items that are each a whole number, and
	between numbers that only whitespace separates inside one item, which become
	items of their own. Blank text items are dropped and the others stripped.
	"""
	wait_factor = settings.scaled_number_wait()
	if wait_factor <= 0:
		yield from speechSequence
		return
	yield from _insert_between(
		_split_numbers(_remove_space(speechSequence)),
		_both_numbers,
		NumberBreakCommand(wait_factor),
	)


def remove_language_command(speechSequence):
	for command in speechSequence:
		# Handle language-change commands
		if isinstance(command, WVLangChangeCommand):
			continue
		else:
			yield command


def _insert_WVLangChangeCommand_between_number(
	speechSequence: Iterable[SpeechCmd],
	ctx: SpeechContext,
) -> Iterator[SpeechCmd]:
	"""
	Yield *speechSequence* while wrapping every numeric fragment with
	`WVLangChangeCommand`s so the TTS switches to *number_language* for
	numbers and then back to the current language.
	"""
	number_language = ctx.number_language
	current_lang = ctx.language
	default_lang = ctx.language

	for item in speechSequence:
		# Forward non-string commands; update current_lang for explicit changes
		if not isinstance(item, str):
			yield item
			if isinstance(item, (LangChangeCommand, WVLangChangeCommand)):
				current_lang = item.lang or default_lang
			continue
		yield from merge_consecutive_strings(
			deduplicate_language_command(
				iter_number_speech_segments_language(item, current_lang, number_language),
				ctx,
				start_language=current_lang,
			),
		)


def iter_number_speech_segments_language(item, current_lang, number_language, number_re=_NUMBER_RE):
	"""
	Yield segments in the following order:
	  - Plain text fragments (non-numeric parts of the original string)
	  - WVLangChangeCommand(num_lang)
	  - The numeric fragment as it appears
	  - WVLangChangeCommand(current_lang)

	The function processes the input string without building an intermediate list.
	"""
	for kind, value in _split_by(number_re, item):
		if kind == "text":
			yield value
			continue
		# Language for the numeric fragment
		num_lang = number_language if number_language != "default" else current_lang
		# Insert language switch and number
		yield WVLangChangeCommand(num_lang)
		yield value.group()
		yield WVLangChangeCommand(current_lang)


# @with_order_log("number_language")
def inject_number_language(
	speechSequence: Iterable[SpeechCmd],
	settings: "PipelineSettings",
	ctx: SpeechContext,
) -> Iterator[SpeechCmd]:
	if ctx.supports_roles:
		if ctx.number_language == "default":
			# The number-language wrapper commands are always dropped by
			# deduplicate_language_command in this case, so the pass-through
			# below is behavior-identical and avoids scanning every string
			# for numbers.
			yield from speechSequence
			return
		yield from _insert_WVLangChangeCommand_between_number(speechSequence, ctx)
		return
	yield from remove_language_command(speechSequence)


def _translate_number(
	raw: str,
	mode: str,
	table: dict[int, str],
	group_size: int,
	group_pause: int,
	number_pause: int,
) -> Iterator[SpeechCmd]:
	if mode == "value":
		yield raw
		return

	if mode == "group":
		# Decimal numbers are read as a single value; only pure digit runs
		# are cut into groups of group_size digits, counted from the left.
		if "." in raw:
			yield raw
			return
		sign = ""
		digits = raw
		if digits and digits[0] in "+-":
			sign = digits[0]
			digits = digits[1:]
		groups = [digits[i : i + group_size] for i in range(0, len(digits), group_size)]
		# A break even at pause 0: the groups must reach the synth as separate items.
		separator = GroupNumberBreakCommand(group_pause)
		for index, group in enumerate(groups):
			if index > 0:
				yield separator
			yield (sign + group) if index == 0 else group
		return

	# A break even at pause 0: each digit must reach the synth as a separate item.
	separator = NumberBreakCommand(number_pause)
	previous_was_digit = False
	for character in raw:
		is_digit = character.isdigit()
		if is_digit and previous_was_digit:
			yield separator
		yield character.translate(table)
		previous_was_digit = is_digit


# @with_order_log("number_mode")
def inject_number_mode(
	speechSequence: Iterable[SpeechCmd],
	settings: "PipelineSettings",
	ctx: SpeechContext,
) -> Iterator[SpeechCmd]:
	mode = settings.number_mode
	translate_table = get_translate_table(ctx)
	group_size = settings.group_size
	group_pause = settings.scaled_group_wait()
	number_pause = settings.scaled_number_wait()
	for item in speechSequence:
		if not isinstance(item, str):
			yield item
			continue
		segments = iter_number_speech_segments_mode(
			item,
			mode,
			translate_table,
			group_size,
			group_pause,
			number_pause,
		)
		if ctx.supports_roles:
			segments = deduplicate_language_command(segments, ctx)
		yield from merge_consecutive_strings(segments)


def iter_number_speech_segments_mode(
	item,
	mode,
	translate_table,
	group_size,
	group_pause,
	number_pause,
	number_re=_NUMBER_RE,
):
	# A "." right after a number, or right before one, is spoken apart from it.
	previous_was_number = False
	preceding_text = ""
	for kind, value in _split_by(number_re, item):
		if kind == "text":
			if previous_was_number and value[0] == ".":
				yield " "
			yield value
			preceding_text = value
			continue
		if preceding_text.endswith("."):
			yield " "
		yield from _translate_number(
			value.group(),
			mode,
			translate_table,
			group_size,
			group_pause,
			number_pause,
		)
		previous_was_number = True
		preceding_text = ""


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


# @with_order_log("chinesespace_wait_factor")
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


# @with_order_log("punctuation_wait_factor")
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
	"""
	if not settings.punctuation_pause_enabled:
		yield from speechSequence
		return

	chars = settings.punctuation_pause_characters.strip()
	if not chars:
		# An empty character class would not compile (see _get_punctuation_regex).
		yield from speechSequence
		return

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
	for current in it:
		if isinstance(current, BreakCommand):
			pending_breaks.append(current)
			continue
		text_follows = is_non_blank_text(current)
		yield from emit(previous, text_follows and not pending_breaks, text_follows)
		yield from pending_breaks
		pending_breaks.clear()
		previous = current

	yield from emit(previous, False, False)
	yield from pending_breaks


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
	default_voice = ctx.default_voice
	voice_name = default_name = default_voice.name if default_voice is not None else None
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
			lang = cmd.lang or ctx.default_voice.language
			yield SelectVoice(ctx.voice_name_for_language(lang) or ctx.default_voice.name)
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


def _run_logged(label, fn, speechSequence, settings, ctx):
	debug = config.conf["general"]["loggingLevel"] == "DEBUG"
	section = config.conf["WorldVoice"]["log"]
	recording = section["enable"]
	if not ((debug or recording) and section[label]):
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
	drops the rest of the utterance at a command it has none for.
	"""
	return [BreakCommand(item.time) if isinstance(item, BreakCommand) else item for item in speechSequence]


def _stage_handler(log_key, fn):
	def handler(speechSequence):
		ctx = current_context()
		settings = pipeline_settings.effective(ctx.supports_roles)
		result = _run_logged(log_key, fn, speechSequence, settings, ctx)
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
	handler: Callable[[Iterable[SpeechCmd]], Iterable[SpeechCmd]] = field(
		init=False,
		repr=False,
		compare=False,
	)

	def __post_init__(self):
		object.__setattr__(self, "handler", _stage_handler(self.log_key, self.fn))


# The order NVDA runs the filters in; register, reorder and the log switches derive from it.
STAGES: tuple[Stage, ...] = (
	Stage("apply_speech_dictionaries", apply_speech_dictionaries),
	Stage("ignore_comma_between_number", ignore_comma_between_number),
	Stage("number_language", inject_number_language),
	Stage("number_mode", inject_number_mode),
	Stage("chinesespace_wait_factor", inject_chinese_space_pause),
	Stage("item_wait_factor", item_wait_factor),
	Stage("punctuation_wait_factor", inject_punctuation_pause),
	Stage("number_wait_factor", number_wait_factor),
	Stage("speech_viewer", speech_viewer),
)


def order_move_to_start_register():
	# Move to the front in reverse, so STAGES runs first and in order.
	for stage in reversed(STAGES):
		filter_speechSequence.moveToEnd(stage.handler, False)


def order_move_to_end_register():
	for stage in STAGES:
		filter_speechSequence.moveToEnd(stage.handler, True)


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
