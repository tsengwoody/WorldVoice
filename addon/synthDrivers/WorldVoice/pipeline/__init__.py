from functools import wraps
from itertools import chain, pairwise
import re
import string
from typing import Iterable, Iterator, Union
import uuid

import config
from logHandler import log
from speech.commands import BreakCommand, LangChangeCommand
from speech.extensions import filter_speechSequence
import speechDictHandler
from synthDriverHandler import getSynth

from .._speechcommand import WVLangChangeCommand
from ..log import PipelineLog
from . import speech_dictionary
from .settings import get_effective_pipeline_settings

SpeechCmd = Union[str, "BaseSpeechCommand"]
pl = PipelineLog("pipeline.csv")

_COMMA_NUMBER_RE = re.compile(r"(?<=[0-9]),(?=[0-9])")
_PURE_NUMBER_RE = re.compile(r"[0-9]+")
_NUMBER_RE = re.compile(r"[+-]?[0-9]+(?:\.[0-9]+)?")
_CH_SPACE_RE = re.compile(r"(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])")

_SENTENCE_END_RE = re.compile(r"^[.:;,?!](?:\s|$)")

def with_order_log(label: str):
	""" The order numbers are reversed because of recursion: the order number assigned earlier execution is greater than that of a later execution."""
	def decorator(func):
		@wraps(func)
		def wrapper(speechSequence):
			if config.conf["general"]["loggingLevel"] == "DEBUG":
				try:
					synth = getSynth()
					synth.order += 1
					log.debug(f"{label} order {synth.order}")
				except Exception:
					pass
			return func(speechSequence)
		return wrapper
	return decorator


def with_speech_sequence_log(label: str):
	def decorator(func):
		@wraps(func)
		def wrapper(speechSequence):
			if (config.conf["general"]["loggingLevel"] == "DEBUG" or config.conf["WorldVoice"]["log"]["enable"]) and config.conf["WorldVoice"]["log"][label]:
				_id = uuid.uuid4().hex
				speechSequence = list(speechSequence)
				if config.conf["general"]["loggingLevel"] == "DEBUG":
					log.debug(f"speech sequence before {label} pipeline: {speechSequence}")
				if config.conf["WorldVoice"]["log"]["enable"]:
					pl.write(_id, label, "before", speechSequence)
				speechSequence = func(speechSequence)
				speechSequence = list(speechSequence)
				if config.conf["general"]["loggingLevel"] == "DEBUG":
					log.debug(f"speech sequence after {label} pipeline: {speechSequence}")
				if config.conf["WorldVoice"]["log"]["enable"]:
					pl.write(_id, label, "after", speechSequence)
			else:
				speechSequence = func(speechSequence)
			return speechSequence
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


def get_ignore_comma_between_number():
	settings = get_effective_pipeline_settings()
	return settings.ignore_comma_between_number


def get_number_mode():
	settings = get_effective_pipeline_settings()
	return settings.number_mode


def get_translate_table():
	synth = getSynth()
	if synth.name == 'WorldVoice':
		number_language = synth._numlan
		speech_symbols = synth.speechSymbols
	else:
		number_language = "Windows"
		speech_symbols = None

	# Build translation table for single digits
	translate_table: dict[int, str] = {}
	if speech_symbols:
		for d in "0123456789":
			if d in speech_symbols.symbols:
				sym = speech_symbols.symbols[d]
				if sym.language in (number_language, "Windows"):
					translate_table[ord(d)] = sym.replacement or d

	return translate_table


def get_item_wait_factor():
	settings = get_effective_pipeline_settings()
	return settings.scaled_item_wait()


def get_number_wait_factor():
	settings = get_effective_pipeline_settings()
	return settings.scaled_number_wait()


def get_chinesespace_wait_factor():
	settings = get_effective_pipeline_settings()
	return settings.scaled_chinesespace_wait()


def get_punctuation_wait_factor():
	settings = get_effective_pipeline_settings()
	return settings.scaled_punctuation_wait()


def get_punctuation_pause_chars():
	settings = get_effective_pipeline_settings()
	return settings.punctuation_pause_characters.strip()


# @with_order_log("speech_view")
@with_speech_sequence_log("speech_viewer")
def speech_viewer(speechSequence):
	return list(speechSequence)


# @with_order_log("ignore_comma_between_number")
@with_speech_sequence_log("ignore_comma_between_number")
def ignore_comma_between_number(speechSequence):
	if get_ignore_comma_between_number():
		yield from (_COMMA_NUMBER_RE.sub(lambda m: '', command) if isinstance(command, str) else command for command in speechSequence)
	else:
		yield from speechSequence


# @with_order_log("apply_speech_dictionaries")
@with_speech_sequence_log("apply_speech_dictionaries")
def apply_speech_dictionaries(speechSequence):
	for item in speechSequence:
		if isinstance(item, str):
			yield speechDictHandler.processText(item)
		else:
			yield item


# @with_order_log("item_wait_factor")
@with_speech_sequence_log("item_wait_factor")
def item_wait_factor(
		speechSequence: Iterable[SpeechCmd],
) -> Iterator[SpeechCmd]:
	"""
	Insert a BreakCommand between every two consecutive plain‑text items.
	Implemented with itertools.pairwise() for clarity.
	"""
	wait_factor = get_item_wait_factor()
	if wait_factor <= 0:
		yield from speechSequence
		return

	break_cmd = BreakCommand(wait_factor)

	# Convert to iterator so we can check length‑1 cases quickly.
	it = iter(speechSequence)

	try:
		first = next(it)				 # Grab the first element.
	except StopIteration:				# Empty sequence → nothing to yield.
		return

	# Special case: only one element in the whole sequence.
	# Just yield it and stop early.
	try:
		second = next(it)
	except StopIteration:
		yield first
		return

	# --- Normal path: we have at least two items ---------------------------
	# Re‑chain the first two elements back into a single iterable:
	#   first, second, then the rest of *it*.
	full_iter = chain([first, second], it)

	# Use pairwise() on the *entire* stream so (first, second) is compared.
	for previous, current in pairwise(full_iter):
		yield previous					   # Always emit the previousious element.
		if isinstance(previous, str) and isinstance(current, str):
			yield break_cmd			  # Insert pause when both are strings.

	# pairwise() stops before the last element, so emit it here.
	yield current


def _insert_BreakCommand_between_number(
		speechSequence: Iterable[SpeechCmd],
) -> Iterator[SpeechCmd]:
	"""
	Insert a BreakCommand between every two consecutive plain‑text items.

	The inserted pause length equals synth._itemwaitfactor × 5.
	Implemented with itertools.pairwise() for clarity.
	"""
	wait_factor = get_number_wait_factor()
	if wait_factor <= 0:
		yield from speechSequence
		return

	break_cmd = BreakCommand(wait_factor)

	# Convert to iterator so we can check length‑1 cases quickly.
	it = iter(speechSequence)

	try:
		first = next(it)				 # Grab the first element.
	except StopIteration:				# Empty sequence → nothing to yield.
		return

	# Special case: only one element in the whole sequence.
	# Just yield it and stop early.
	try:
		second = next(it)
	except StopIteration:
		yield first
		return

	# --- Normal path: we have at least two items ---------------------------
	# Re‑chain the first two elements back into a single iterable:
	#   first, second, then the rest of *it*.
	full_iter = chain([first, second], it)

	# Use pairwise() on the *entire* stream so (first, second) is compared.
	for previous, current in pairwise(full_iter):
		yield previous					   # Always emit the previousious element.
		if isinstance(previous, str) and _NUMBER_RE.match(previous) \
		and isinstance(current, str) and _NUMBER_RE.match(current):
			yield break_cmd			  # Insert pause when both are strings.

	# pairwise() stops before the last element, so emit it here.
	yield current


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


# @with_order_log("number_wait_factor")
@with_speech_sequence_log("number_wait_factor")
def number_wait_factor(
		speechSequence: Iterable[SpeechCmd],
) -> Iterator[SpeechCmd]:
	speechSequence = _remove_space(speechSequence)
	speechSequence = _insert_BreakCommand_between_number(speechSequence)
	yield from speechSequence


def remove_language_command(speechSequence):
	for command in speechSequence:
		# Handle language-change commands
		if isinstance(command, WVLangChangeCommand):
			continue
		else:
			yield command


def _insert_WVLangChangeCommand_between_number(
		speechSequence: Iterable[SpeechCmd],
) -> Iterator[SpeechCmd]:
	"""
	Yield *speechSequence* while wrapping every numeric fragment with
	`WVLangChangeCommand`s so the TTS switches to *number_language* for
	numbers and then back to the current language.
	"""
	synth = getSynth()
	number_language = synth._numlan
	current_lang = synth.language
	default_lang = synth.language

	for item in speechSequence:
		# Forward non-string commands; update current_lang for explicit changes
		if not isinstance(item, str):
			yield item
			if isinstance(item, (LangChangeCommand, WVLangChangeCommand)):
				current_lang = item.lang or default_lang
			continue
		yield from merge_consecutive_strings(deduplicate_language_command(iter_number_speech_segments_language(item, current_lang, number_language)))


def iter_number_speech_segments_language(item, current_lang, number_language, number_re=_NUMBER_RE):
	"""
	Yield segments in the following order:
	  - Plain text fragments (non-numeric parts of the original string)
	  - WVLangChangeCommand(num_lang)
	  - The numeric fragment as it appears
	  - WVLangChangeCommand(current_lang)
	
	The function processes the input string without building an intermediate list.
	"""
	pos = 0
	for m in number_re.finditer(item):
		start, end = m.span()
		number_raw = m.group()

		# Emit the text before the numeric match
		if start > pos:
			yield item[pos:start]
		pos = end

		# Language for the numeric fragment
		num_lang = number_language if number_language != "default" else current_lang

		# Insert language switch and number
		yield WVLangChangeCommand(num_lang)
		yield number_raw
		yield WVLangChangeCommand(current_lang)

	# Emit trailing text after the last match
	if pos < len(item):
		yield item[pos:]


# @with_order_log("number_language")
@with_speech_sequence_log("number_language")
def inject_number_language(
		speechSequence: Iterable[SpeechCmd],
) -> Iterator[SpeechCmd]:
	synth = getSynth()
	if hasattr(synth, "_voiceManager"):
		if synth._numlan == "default":
			# The number-language wrapper commands are always dropped by
			# deduplicate_language_command in this case, so the pass-through
			# below is behavior-identical and avoids scanning every string
			# for numbers.
			yield from speechSequence
			return
		speechSequence = _insert_WVLangChangeCommand_between_number(speechSequence)
		yield from speechSequence
		return
	else:
		speechSequence = remove_language_command(speechSequence)
		yield from speechSequence
		return


def _translate_number(raw: str, mode: str, table: dict[int, str]) -> Iterator[str]:
	if mode == "value":
		yield raw
		return

	previous_was_digit = False
	for character in raw:
		is_digit = character.isdigit()
		if is_digit and previous_was_digit:
			yield " "
		yield character.translate(table)
		previous_was_digit = is_digit

# @with_order_log("number_mode")
@with_speech_sequence_log("number_mode")
def inject_number_mode(
		speechSequence: Iterable[SpeechCmd],
) -> Iterator[SpeechCmd]:
	mode = get_number_mode()
	translate_table = get_translate_table()

	for item in speechSequence:
		if not isinstance(item, str):
			yield item
			continue

		synth = getSynth()
		if synth.name == 'WorldVoice':
			yield from merge_consecutive_strings(deduplicate_language_command(iter_number_speech_segments_mode(item, mode, translate_table)))
		else:
			yield from merge_consecutive_strings(iter_number_speech_segments_mode(item, mode, translate_table))


def iter_number_speech_segments_mode(item, mode, translate_table, number_re=_NUMBER_RE):
	pos = 0
	previous_was_number = False
	for m in number_re.finditer(item):
		start, end = m.span()
		number_raw = m.group()
		prefix = item[pos:start]
		if prefix:
			if previous_was_number and prefix[0] == ".":
				yield " "
			yield prefix
		if prefix.endswith("."):
			yield " "
		yield from _translate_number(number_raw, mode, translate_table)
		pos = end
		previous_was_number = True
	if pos < len(item):
		tail = item[pos:]
		if previous_was_number and tail[0] == ".":
			yield " "
		yield tail


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
@with_speech_sequence_log("chinesespace_wait_factor")
def inject_chinese_space_pause(
		speechSequence: Iterable[SpeechCmd],
) -> Iterator[SpeechCmd]:
	waitfactor = get_chinesespace_wait_factor()
	if waitfactor <= 0:
		yield from speechSequence
		return

	pause_cmd = BreakCommand(waitfactor)

	for item in speechSequence:
		# non-string commands flow through untouched
		if not isinstance(item, str):
			yield item
			continue

		pos = 0
		for m in _CH_SPACE_RE.finditer(item):
			start, end = m.span()

			# emit text before the CJK-space-CJK pattern
			if start > pos:
				yield item[pos:start]
			pos = end		# advance pointer to character after the space

			# insert the pause once for this space
			yield pause_cmd

		# emit any tail text after the last match
		if pos < len(item):
			yield item[pos:]


_PUNCTUATION_RE_CACHE: dict[str, re.Pattern] = {}
_PUNCTUATION_REMOVAL_RE_CACHE: dict[str, re.Pattern] = {}


def _get_punctuation_regex(chars: str) -> re.Pattern:
	regex = _PUNCTUATION_RE_CACHE.get(chars)
	if regex is None:
		# A punctuation run (one or more configured marks in a row) is only
		# treated as a pause point when it is not directly surrounded by
		# digits, so "12,500" and "3.5" are left untouched.
		regex = re.compile(rf"(?<![0-9])[{re.escape(chars)}]+(?!\d)")
		_PUNCTUATION_RE_CACHE[chars] = regex
	return regex


def _get_punctuation_removal_regex(chars: str) -> re.Pattern:
	regex = _PUNCTUATION_REMOVAL_RE_CACHE.get(chars)
	if regex is None:
		# Unlike the pause-detection regex above, the lookbehind guard is
		# omitted on purpose: a mark directly preceded by a digit may still be
		# a sentence ending (e.g. the trailing period in "I have 5.") and must
		# be removed. The lookahead alone protects real decimals such as
		# "3.5" and thousands separators such as "12,500".
		regex = re.compile(rf"[{re.escape(chars)}]+(?!\d)")
		_PUNCTUATION_REMOVAL_RE_CACHE[chars] = regex
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
	pos = 0
	for match in regex.finditer(text):
		if match.start() > pos:
			yield ("text", text[pos:match.start()])
		yield ("punct", match.group())
		pos = match.end()
	if pos < len(text):
		yield ("text", text[pos:])


# @with_order_log("punctuation_wait_factor")
@with_speech_sequence_log("punctuation_wait_factor")
def inject_punctuation_pause(
		speechSequence: Iterable[SpeechCmd],
) -> Iterator[SpeechCmd]:
	"""
	Insert a short BreakCommand after a punctuation mark so the TTS does not
	run the text following the punctuation straight into it.

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
	* An existing BreakCommand between two text items suppresses this pause,
	  so the punctuation pause and item_wait_factor never stack.
	"""
	wait_factor = get_punctuation_wait_factor()
	if wait_factor <= 0:
		yield from speechSequence
		return

	chars = get_punctuation_pause_chars()
	if not chars:
		yield from speechSequence
		return

	pause_cmd = BreakCommand(wait_factor)
	regex = _get_punctuation_regex(chars)

	def is_non_blank_text(command: SpeechCmd) -> bool:
		return isinstance(command, str) and bool(command.strip())

	def emit(item: SpeechCmd, text_follows: bool) -> Iterator[SpeechCmd]:
		if not isinstance(item, str):
			yield item
			return
		parts = list(_split_punctuation_segments(item, regex))
		for index, (kind, value) in enumerate(parts):
			if kind == "text":
				yield value
				continue
			yield value
			if any(
				pkind == "text" and pvalue.strip()
				for pkind, pvalue in parts[index + 1:]
			):
				yield pause_cmd
		# The item ends with a punctuation mark (its last significant
		# character is a configured one); pause before the next text item.
		stripped = item.rstrip()
		if stripped and stripped[-1] in chars and text_follows:
			yield pause_cmd

	it = iter(speechSequence)
	try:
		previous = next(it)
	except StopIteration:
		return

	for current in it:
		yield from emit(previous, is_non_blank_text(current))
		previous = current

	yield from emit(previous, False)


# @with_order_log("remove_silence")
@with_speech_sequence_log("remove_silence")
def remove_silence(
		speechSequence: Iterable[SpeechCmd],
) -> Iterator[SpeechCmd]:
	"""
	When the punctuation wait factor is 0, drop every BreakCommand from the
	sequence so the voice is never silent between sentences - not even for a
	fraction of a second.

	* The pause is removed no matter which filter produced it (item wait,
	  number wait, chinese space) or whether the caller inserted it, because
	  this filter runs last in the pipeline.
	* The configured punctuation-pause characters are stripped from the text
	  as well, because the TTS engine itself pauses at marks such as "." or
	  "؟" in the string it receives. Without stripping them the engine would
	  still be silent even though no BreakCommand is left.
	* A mark directly followed by a digit is preserved ("3.5", "12,500").
	* When the factor is greater than 0 the sequence passes through
	  unchanged, so the pauses requested by the other settings are preserved.
	"""
	if get_punctuation_wait_factor() > 0:
		yield from speechSequence
		return

	chars = get_punctuation_pause_chars()
	regex = _get_punctuation_removal_regex(chars) if chars else None

	for command in speechSequence:
		if isinstance(command, BreakCommand):
			continue
		if isinstance(command, str) and regex is not None:
			command = regex.sub("", command)
			if command:
				yield command
			continue
		yield command


def deduplicate_language_command(speechSequence):
	"""
	Stream *speech_sequence* and emit only the language-change commands
	that actually switch to a different voice instance.

	Workflow
	--------
	1. Walk through the sequence while tracking the *current language*
	   and *current voiceInstance*.
	2. Yield a LangChangeCommand only when it maps to a **different**
	   voice instance than the one currently in use.
	3. Forward all non-language-change commands unchanged.
	"""
	synth = getSynth()

	# Initial voice / language
	voice_instance = default_instance = synth._voiceManager.defaultVoiceInstance
	current_language = default_language = synth.language

	for command in speechSequence:
		# Handle language-change commands
		if isinstance(command, (LangChangeCommand, WVLangChangeCommand)):
			# Skip if the language is actually unchanged
			if command.lang == current_language:
				continue

			# Resolve the new language and its voice instance
			if command.lang is None:					   # Revert to default language
				new_instance = default_instance
				current_language = default_language
			else:
				new_instance = synth._voiceManager.getVoiceInstanceForLanguage(command.lang)
				current_language = command.lang
				if new_instance is None:			   # Fallback when no voice found
					new_instance = default_instance

			# Skip if the voice instance remains the same
			if new_instance == voice_instance:
				continue

			# Effective switch: update state and yield the command
			voice_instance = new_instance
			yield command
		# Forward all other commands
		else:
			yield command


def lang_cmd_to_voice(
		speechSequence: Iterable[SpeechCmd],
		voice_manager: "VoiceManager",
		default_instance: "Voice",
) -> Iterator[SpeechCmd]:
	"""
	Convert each LangChangeCommand / WVLangChangeCommand into a Voice instance.
	All other commands pass through unchanged.
	"""
	for cmd in speechSequence:
		if isinstance(cmd, (LangChangeCommand, WVLangChangeCommand)):
			lang = cmd.lang or voice_manager.defaultVoiceInstance.language
			new_instance = voice_manager.getVoiceInstanceForLanguage(lang) or default_instance
			yield new_instance
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


def order_move_to_start_register():
	# stack: first in last out
	filter_speechSequence.moveToEnd(speech_viewer, False)
	filter_speechSequence.moveToEnd(remove_silence, False)
	filter_speechSequence.moveToEnd(number_wait_factor, False)
	filter_speechSequence.moveToEnd(inject_punctuation_pause, False)
	filter_speechSequence.moveToEnd(item_wait_factor, False)
	filter_speechSequence.moveToEnd(inject_chinese_space_pause, False)
	filter_speechSequence.moveToEnd(inject_number_mode, False)
	filter_speechSequence.moveToEnd(inject_number_language, False)
	filter_speechSequence.moveToEnd(ignore_comma_between_number, False)
	filter_speechSequence.moveToEnd(apply_speech_dictionaries, False)


def order_move_to_end_register():
	# queue: first in first out
	filter_speechSequence.moveToEnd(apply_speech_dictionaries, True)
	filter_speechSequence.moveToEnd(ignore_comma_between_number, True)
	filter_speechSequence.moveToEnd(inject_number_language, True)
	filter_speechSequence.moveToEnd(inject_number_mode, True)
	filter_speechSequence.moveToEnd(inject_chinese_space_pause, True)
	filter_speechSequence.moveToEnd(item_wait_factor, True)
	filter_speechSequence.moveToEnd(inject_punctuation_pause, True)
	filter_speechSequence.moveToEnd(number_wait_factor, True)
	filter_speechSequence.moveToEnd(remove_silence, True)
	filter_speechSequence.moveToEnd(speech_viewer, True)


def static_register():
	log.debug("static register")

	speech_dictionary.install()
	filter_speechSequence.register(apply_speech_dictionaries)
	filter_speechSequence.register(inject_chinese_space_pause)
	filter_speechSequence.register(inject_number_language)
	filter_speechSequence.register(inject_number_mode)
	filter_speechSequence.register(number_wait_factor)
	filter_speechSequence.register(remove_silence)
	filter_speechSequence.register(speech_viewer)


def dynamic_register():
	log.debug("dynamic register")

	filter_speechSequence.register(ignore_comma_between_number)
	filter_speechSequence.register(item_wait_factor)
	filter_speechSequence.register(inject_punctuation_pause)


def unregister():
	log.debug("unregister")

	filter_speechSequence.unregister(apply_speech_dictionaries)
	filter_speechSequence.unregister(ignore_comma_between_number)
	filter_speechSequence.unregister(inject_chinese_space_pause)
	filter_speechSequence.unregister(inject_number_mode)
	filter_speechSequence.unregister(inject_number_language)
	filter_speechSequence.unregister(item_wait_factor)
	filter_speechSequence.unregister(inject_punctuation_pause)
	filter_speechSequence.unregister(number_wait_factor)
	filter_speechSequence.unregister(remove_silence)
	filter_speechSequence.unregister(speech_viewer)
	speech_dictionary.uninstall()
