import re
from itertools import chain, pairwise
from typing import Iterable, Iterator, Union

import config
from logHandler import log
from speech.commands import BreakCommand, CharacterModeCommand, LangChangeCommand
from synthDriverHandler import getSynth

from ._speechcommand import SplitCommand, WVLangChangeCommand

SpeechCmd = Union[str, "BaseSpeechCommand"]

number_pattern = re.compile(r"[0-9\-\+]+[0-9.:]*[0-9]+|[0-9]")
comma_number_pattern = re.compile(r"(?<=[0-9]),(?=[0-9])")
_NUMBER_RE = re.compile(r"[0-9\-\+]+[0-9.:]*[0-9]+|[0-9]")
_CH_SPACE_RE = re.compile(r"(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])")


def with_order_log(label: str):
	"""
	Decorator for speech-sequence filters.
	* Logs the filter *label*.
	* Increments and logs synth.order to show evaluation order.
	* Then streams the wrapped generator’s output unchanged.
	"""
	def decorator(func):
		def wrapper(speechSequence):
			try:
				synth = getSynth()
				synth.order += 1
				log.debug(f"{label} order {synth.order}")
			except:
				pass
			yield from func(speechSequence)
		return wrapper
	return decorator


@with_order_log("ignore_comma_between_number")
def ignore_comma_between_number(speechSequence):
	yield from (comma_number_pattern.sub(lambda m: '', command) if isinstance(command, str) else command for command in speechSequence)


@with_order_log("item_wait_factor")
def item_wait_factor(
	speechSequence: Iterable[SpeechCmd],
) -> Iterator[SpeechCmd]:
	"""
	Insert a BreakCommand between every two consecutive plain‑text items.

	The inserted pause length equals synth._itemwaitfactor × 5.
	Implemented with itertools.pairwise() for clarity.
	"""
	synth = getSynth()
	wait_factor = synth._globalwaitfactor * synth.itemwaitfactor
	if wait_factor <= 0:
		# feature disabled → passthrough
		yield from speechSequence
		return

	break_cmd = BreakCommand(wait_factor * 5)

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


@with_order_log("number_wait_factor")
def number_wait_factor(
	speechSequence: Iterable[SpeechCmd],
) -> Iterator[SpeechCmd]:
	"""
	Insert a BreakCommand between every two consecutive plain‑text items.

	The inserted pause length equals synth._itemwaitfactor × 5.
	Implemented with itertools.pairwise() for clarity.
	"""
	synth = getSynth()
	waitfactor = synth._globalwaitfactor * synth.numberwaitfactor
	waitfactor = waitfactor if waitfactor > 0 else 1
	break_cmd = BreakCommand(waitfactor)

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
		if isinstance(previous, str) and number_pattern.match(previous) \
			and isinstance(current, str) and number_pattern.match(current):
			yield break_cmd			  # Insert pause when both are strings.

	# pairwise() stops before the last element, so emit it here.
	yield current


@with_order_log("remove_space")
def remove_space(
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
	voice_instance   = default_instance   = synth._voiceManager.defaultVoiceInstance
	current_language = default_language   = synth.language

	for command in speechSequence:
		# Handle language-change commands
		if isinstance(command, (LangChangeCommand, WVLangChangeCommand)):
			# Skip if the language is actually unchanged
			if command.lang == current_language:
				continue

			# Resolve the new language and its voice instance
			if command.lang is None:					   # Revert to default language
				new_instance	= default_instance
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


def _translate_number(raw: str, mode: str, table: dict[int, str]) -> str:
	if mode == "number":
		parts = raw.split(".")
		raw = ".".join(
			n.translate(table)
			for n in parts
		)
		if len(raw) > 1:
			yield CharacterModeCommand(True)
			yield raw
			yield CharacterModeCommand(False)
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


@with_order_log("inject_number_langchange")
def inject_number_langchange(
	speechSequence: Iterable[SpeechCmd],
) -> Iterator[SpeechCmd]:
	speechSequence = inject_number_langchangei(speechSequence)
	speechSequence = deduplicate_language_command(speechSequence)
	yield from speechSequence


def inject_number_langchangei(
	speechSequence: Iterable[SpeechCmd],
) -> Iterator[SpeechCmd]:
	"""
	Yield *speechSequence* while wrapping every numeric fragment with
	`WVLangChangeCommand`s so the TTS switches to *number_language* for
	numbers and then back to the current language.

	Parameters
	----------
	mode : {"value", "number"}
		"value"  – read numbers as a value (e.g. 123)  
		"number" – spell every digit (e.g. 1 2 3)
	number_language : str
		Target locale for numbers; "default" keeps the current locale.
	speech_symbols : SpeechSymbols
		Optional symbol table for custom digit replacements.
	"""
	synth = getSynth()
	mode = synth._nummod
	number_language = synth._numlan
	speech_symbols = synth.speechSymbols

	current_lang = synth.language
	default_lang = synth.language

	# Build translation table for single digits
	translate_table: dict[int, str] = {}
	if speech_symbols:
		for d in "0123456789":
			if d in speech_symbols.symbols:
				sym = speech_symbols.symbols[d]
				if sym.language in (number_language, "Windows"):
					translate_table[ord(d)] = sym.replacement or d

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
			yield from _translate_number(number_raw, mode, translate_table)
			# End-number switch back to original language
			yield WVLangChangeCommand(current_lang)

		# Emit trailing text after the last match
		if pos < len(item):
			yield item[pos:]


@with_order_log("inject_chinese_space_pause")
def inject_chinese_space_pause(
	speechSequence: Iterable[SpeechCmd],
) -> Iterator[SpeechCmd]:
	"""
	Insert BreakCommand(self._chinesespacewaitfactor×5) whenever a space
	appears *between* two CJK characters, using the same start/end/pos
	pattern as `inject_number_langchange`.
	"""
	synth = getSynth()
	waitfactor = synth._globalwaitfactor * synth.chinesespacewaitfactor
	if waitfactor <= 0:
		# feature disabled → passthrough
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
	buffer: List[SpeechCmd] = []

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
