import re
from itertools import chain, pairwise
from typing import Iterable, Iterator, Union
import uuid

import config
from gui import speechViewer
from logHandler import log
from speech.commands import BreakCommand, LangChangeCommand
from speech.extensions import filter_speechSequence
from synthDriverHandler import getSynth

from ._speechcommand import WVLangChangeCommand
from .log import PipelineLog

SpeechCmd = Union[str, "BaseSpeechCommand"]
pl = PipelineLog("pipeline.csv")

_COMMA_NUMBER_RE = re.compile(r"(?<=[0-9]),(?=[0-9])")
_PURE_NUMBER_RE = re.compile(r"[0-9]+")
_NUMBER_RE = re.compile(r"[0-9\-\+]+[0-9.:]*[0-9]+|[0-9]")
_CH_SPACE_RE = re.compile(r"(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])")


def with_order_log(label: str):
	""" The order numbers are reversed because of recursion: the order number assigned earlier execution is greater than that of a later execution."""
	def decorator(func):
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
		def wrapper(speechSequence):
			_id = uuid.uuid4().hex
			if (config.conf["general"]["loggingLevel"] == "DEBUG" or config.conf["WorldVoice"]["log"]["enable"]) and config.conf["WorldVoice"]["log"][label]:
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


def get_ignore_comma_between_number():
	synth = getSynth()
	if synth.name == 'WorldVoice':
		return synth._cni
	else:
		return config.conf["WorldVoice"]["pipeline"]["global_wait_factor"] // 10 * config.conf["WorldVoice"]["pipeline"]["ignore_comma_between_number"]


def get_number_mode():
	synth = getSynth()
	if synth.name == 'WorldVoice':
		result = synth._nummod
	else:
		result = config.conf["WorldVoice"]["pipeline"]["number_mode"]
	return result


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
	synth = getSynth()
	if synth.name == 'WorldVoice':
		wait_factor = synth._globalwaitfactor * synth.itemwaitfactor
	else:
		wait_factor = config.conf["WorldVoice"]["pipeline"]["global_wait_factor"] // 10 * config.conf["WorldVoice"]["pipeline"]["item_wait_factor"]
	return wait_factor


def get_number_wait_factor():
	synth = getSynth()
	if synth.name == 'WorldVoice':
		wait_factor = synth._globalwaitfactor * synth.numberwaitfactor
	else:
		wait_factor = config.conf["WorldVoice"]["pipeline"]["global_wait_factor"] // 10 * config.conf["WorldVoice"]["pipeline"]["number_wait_factor"]
	return wait_factor


def get_chinesespace_wait_factor():
	synth = getSynth()
	if synth.name == 'WorldVoice':
		wait_factor = synth._globalwaitfactor * synth.chinesespacewaitfactor
	else:
		wait_factor = config.conf["WorldVoice"]["pipeline"]["global_wait_factor"] // 10 * config.conf["WorldVoice"]["pipeline"]["chinesespace_wait_factor"]
	return wait_factor


# @with_order_log("speech_view")
@with_speech_sequence_log("speech_viewer")
def speech_viewer(speechSequence):
	if speechViewer.isActive:
		return list(speechSequence)
	else:
		return speechSequence


# @with_order_log("ignore_comma_between_number")
@with_speech_sequence_log("ignore_comma_between_number")
def ignore_comma_between_number(speechSequence):
	if get_ignore_comma_between_number():
		yield from (_COMMA_NUMBER_RE.sub(lambda m: '', command) if isinstance(command, str) else command for command in speechSequence)
	else:
		yield from speechSequence


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

		pos = 0
		for m in _NUMBER_RE.finditer(item):
			start, end = m.span()
			number_raw = m.group()

			# Emit the text before the numeric match
			if start > pos:
				yield item[pos:start]
			pos = end

			# Language for the numeric fragment
			num_lang = (
				number_language
				if number_language != "default"
				else current_lang
			)

			# Start-number language switch
			yield WVLangChangeCommand(num_lang)
			# Spoken representation of the number
			yield number_raw
			# End-number switch back to original language
			yield WVLangChangeCommand(current_lang)

		# Emit trailing text after the last match
		if pos < len(item):
			yield item[pos:]


# @with_order_log("number_language")
@with_speech_sequence_log("number_language")
def inject_number_langchange(
		speechSequence: Iterable[SpeechCmd],
) -> Iterator[SpeechCmd]:
	synth = getSynth()
	if hasattr(synth, "_voiceManager"):
		speechSequence = _insert_WVLangChangeCommand_between_number(speechSequence)
		speechSequence = deduplicate_language_command(speechSequence)
		yield from speechSequence
		return
	else:
		speechSequence = remove_language_command(speechSequence)
		yield from speechSequence
		return


def _translate_number(raw: str, mode: str, table: dict[int, str]) -> str:
	if mode == "number":
		parts = raw.split(".")
		raw = ".".join(
			n.translate(table) if len(n) == 1 else n
			for n in parts
		)
		if len(raw) > 1:
			pos = 0
			for m in _PURE_NUMBER_RE.finditer(raw):
				start, end = m.span()
				number_raw = m.group()

				# Emit the text before the numeric match
				if start > pos:
					yield raw[pos:start]
				pos = end

				# Spoken representation of the number
				yield ' '.join(number_raw)

			# Emit trailing text after the last match
			if pos < len(raw):
				yield raw[pos:]
		else:
			yield raw
	else:
		if raw.count(".") != 1:
			parts = raw.split(".")
			raw = ".".join(
				n.translate(table) if len(n) == 1 else n
				for n in parts
			)
		yield raw


# @with_order_log("number_mode")
@with_speech_sequence_log("number_mode")
def change_number_mode(
		speechSequence: Iterable[SpeechCmd],
) -> Iterator[SpeechCmd]:
	speechSequence = _change_number_mode(speechSequence)
	yield from speechSequence


def _change_number_mode(
		speechSequence: Iterable[SpeechCmd],
) -> Iterator[SpeechCmd]:
	mode = get_number_mode()
	translate_table = get_translate_table()

	for item in speechSequence:
		# Forward non-string commands; update current_lang for explicit changes
		if not isinstance(item, str):
			yield item
			continue

		pos = 0
		for m in _NUMBER_RE.finditer(item):
			start, end = m.span()
			number_raw = m.group()

			# Emit the text before the numeric match
			if start > pos:
				yield item[pos:start]
			pos = end

			# Spoken representation of the number
			yield from _translate_number(number_raw, mode, translate_table)

		# Emit trailing text after the last match
		if pos < len(item):
			yield item[pos:]


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
	filter_speechSequence.moveToEnd(number_wait_factor, False)
	filter_speechSequence.moveToEnd(item_wait_factor, False)

	filter_speechSequence.moveToEnd(inject_chinese_space_pause, False)
	filter_speechSequence.moveToEnd(change_number_mode, False)
	filter_speechSequence.moveToEnd(inject_number_langchange, False)

	filter_speechSequence.moveToEnd(ignore_comma_between_number, False)


def order_move_to_end_register():
	# queue: first in first out
	filter_speechSequence.moveToEnd(ignore_comma_between_number, True)

	filter_speechSequence.moveToEnd(inject_number_langchange, True)
	filter_speechSequence.moveToEnd(change_number_mode, True)
	filter_speechSequence.moveToEnd(inject_chinese_space_pause, True)

	filter_speechSequence.moveToEnd(item_wait_factor, True)
	filter_speechSequence.moveToEnd(number_wait_factor, True)

	filter_speechSequence.moveToEnd(speech_viewer, True)


def static_register():
	log.debug("static register")

	filter_speechSequence.register(inject_chinese_space_pause)
	filter_speechSequence.register(inject_number_langchange)
	filter_speechSequence.register(change_number_mode)
	filter_speechSequence.register(number_wait_factor)

	filter_speechSequence.register(speech_viewer)


def dynamic_register():
	log.debug("dynamic register")

	filter_speechSequence.register(ignore_comma_between_number)
	filter_speechSequence.register(item_wait_factor)


def unregister():
	log.debug("unregister")

	filter_speechSequence.unregister(ignore_comma_between_number)

	filter_speechSequence.unregister(inject_chinese_space_pause)
	filter_speechSequence.unregister(change_number_mode)
	filter_speechSequence.unregister(inject_number_langchange)

	filter_speechSequence.unregister(item_wait_factor)
	filter_speechSequence.unregister(number_wait_factor)

	filter_speechSequence.unregister(speech_viewer)
