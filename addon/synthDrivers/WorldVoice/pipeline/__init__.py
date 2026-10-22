import os
import re
import uuid
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from functools import wraps
from typing import TYPE_CHECKING, Literal, Union

import characterProcessing
import config
import globalVars
import languageHandler
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
from .numbers import NUMBER_RE, number_pieces, split_spaced_numbers, strip_thousands
from .settings import pipeline_settings, read_stored

if TYPE_CHECKING:
	from speech.commands import SpeechCommand

	from .settings import PipelineSettings

SpeechCmd = Union[str, "SpeechCommand"]
pl = PipelineLog("pipeline.csv")

_CH_SPACE_RE = re.compile(r"(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])")

_SENTENCE_END_RE = re.compile(r"^[.:;,?!](?:\s|$)")


class NumberBreakCommand(BreakCommand):
	"""Pause between numbers, and between the pieces and symbol names of a number in number and group modes."""


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


def _has_symbol_table(locale: str) -> bool:
	"""Whether NVDA has its own symbols table for *locale*, with no fallback to another locale.

	NVDA's mandatory built-in dictionary is locale/<locale>/symbols.dic in its program directory
	(characterProcessing.py:893-901). processSpeechSymbol falls back to the base language and then
	to English without saying so, so only the file tells whether the locale has names of its own.
	A locale that is not a plain name (empty, or with a path in it) has none.
	"""
	if not locale.replace("_", "").isalnum():
		return False
	return os.path.isfile(os.path.join(globalVars.appDir, "locale", locale, "symbols.dic"))


def _symbol_locale(language: str | None, voice_locale: str | None = None) -> str:
	"""The locale to look a symbol name up in, for text spoken in *language* by a voice of *voice_locale*.

	The voice's own locale comes first, in NVDA's form ("zh-TW" -> "zh_TW"), when NVDA has a
	symbols table for it (decided by the user, 2026-10-22). Otherwise: no language (another synth's
	context) is NVDA's current language, where NVDA's own symbol processing starts. NVDA only drops
	a country after "_", so a "-" becomes "_"; and a bare language, as WorldVoice stores number
	languages, takes the country of NVDA's current language when the two agree ("zh" -> "zh_TW"), as
	NVDA's spelling does.
	"""
	if voice_locale:
		locale = languageHandler.normalizeLanguage(voice_locale)
		if locale and _has_symbol_table(locale):
			return locale
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


# @with_order_log("speech_view")
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
	# Whole items only: "12", "-3.5", "5-3" and "12:30" are numbers, "12abc" and "1." are not.
	return (
		_both_text(previous, current)
		and bool(NUMBER_RE.fullmatch(previous))
		and bool(NUMBER_RE.fullmatch(current))
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


def _split_numbers(speechSequence: Iterable[SpeechCmd]) -> Iterator[SpeechCmd]:
	for item in speechSequence:
		if isinstance(item, str):
			yield from split_spaced_numbers(item)
		else:
			yield item


# @with_order_log("number_wait_factor")
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


def iter_number_speech_segments_language(item, current_lang, number_language, number_re=NUMBER_RE):
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


def _symbol_namer(
	voice_locale_for_language: Callable[[str], str | None],
) -> Callable[[str | None], Callable[[str], str | None]]:
	"""Name lookups for one stage run: one locale per language and one NVDA lookup per symbol.

	*voice_locale_for_language* gives the locale of the voice that speaks a language; it is asked
	once per language per run, and never for no language.
	"""
	locales: dict[str | None, str] = {}
	names: dict[tuple[str | None, str], str | None] = {}

	def for_language(language: str | None) -> Callable[[str], str | None]:
		def name_of(symbol: str) -> str | None:
			key = (language, symbol)
			if key not in names:
				if language not in locales:
					voice_locale = voice_locale_for_language(language) if language else None
					locales[language] = _symbol_locale(language, voice_locale)
				names[key] = _symbol_name(locales[language], symbol)
			return names[key]

		return name_of

	return for_language


# @with_order_log("number_mode")
def inject_number_mode(
	speechSequence: Iterable[SpeechCmd],
	settings: "PipelineSettings",
	ctx: SpeechContext,
) -> Iterator[SpeechCmd]:
	mode = settings.number_mode
	if mode == "none":
		# "off" leaves numbers as they are, without even the dot rule.
		yield from speechSequence
		return
	group_size = settings.group_size
	number_pause = settings.scaled_number_wait()
	namer = _symbol_namer(ctx.voice_locale_for_language)
	# Symbols are named for the number language, the language of the wrapper around every number;
	# with no number language, for the language in force at that point of the sequence. The locale
	# is that of the voice that speaks the language, when NVDA has a table for it (_symbol_locale).
	number_language = ctx.number_language if ctx.supports_roles and ctx.number_language != "default" else None
	language = ctx.language
	for item in speechSequence:
		if not isinstance(item, str):
			if isinstance(item, (LangChangeCommand, WVLangChangeCommand)):
				language = item.lang or ctx.language
			yield item
			continue
		segments = iter_number_speech_segments_mode(
			item,
			mode,
			group_size,
			number_pause,
			namer(number_language or language),
		)
		if ctx.supports_roles:
			segments = deduplicate_language_command(segments, ctx)
		yield from merge_consecutive_strings(segments)


def iter_number_speech_segments_mode(
	item: str,
	mode: str,
	group_size: int,
	number_pause: int,
	name_of: Callable[[str], str | None],
	number_re: re.Pattern = NUMBER_RE,
) -> Iterator[SpeechCmd]:
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
		yield from _translate_number(value.group(), mode, group_size, number_pause, name_of)
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
	* Removal never brings two number breaks together. When it empties an
	  item between two NumberBreakCommands (only commands and blank text
	  otherwise), the one after it is dropped, so the earlier one is the only
	  pause: ["12", NB, ".", NB, "5"] with an unnamed "." becomes
	  ["12", NB, "5"]. Every other break stays, as removal changes only marks.
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
	# The last break sent since the last non-blank text, if any.
	last_break = None
	for current in it:
		if isinstance(current, BreakCommand):
			pending_breaks.append(current)
			continue
		text_follows = is_non_blank_text(current)
		emitted = list(emit(previous, text_follows and not pending_breaks, text_follows))
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
	# A switch NVDA refuses on read is off, so a bad stored value never stops the stage.
	recording = read_stored(section, "enable", False)
	if not ((debug or recording) and read_stored(section, label, False)):
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
	# False: the stage logs under the switch of a later stage with the same log key.
	log_switch: bool = True
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
	Stage("number_mode", remove_thousands_separators, log_switch=False),
	Stage("number_language", inject_number_language),
	Stage("number_mode", inject_number_mode),
	Stage("chinesespace_wait_factor", inject_chinese_space_pause),
	Stage("item_wait_factor", item_wait_factor),
	Stage("punctuation_wait_factor", inject_punctuation_pause),
	Stage("number_wait_factor", number_wait_factor),
	Stage("speech_viewer", speech_viewer),
)


# One log switch per log key, in the order of the stage that owns it.
LOG_SWITCHES: tuple[str, ...] = tuple(stage.log_key for stage in STAGES if stage.log_switch)


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
