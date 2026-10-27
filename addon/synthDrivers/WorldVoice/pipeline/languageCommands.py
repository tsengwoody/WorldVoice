"""The language commands of a speech sequence: SynthDriver.speak reorders, deduplicates and turns
them into voices with these, and the number stage drops them for a synth without roles."""

from collections.abc import Iterable, Iterator

from speech.commands import LangChangeCommand

from ..runtime.models import SelectVoice
from ..speechCommands import WVLangChangeCommand
from .context import SpeechContext
from .sequence import SpeechCmd


def remove_language_command(speech_sequence):
	for command in speech_sequence:
		# Handle language-change commands
		if isinstance(command, WVLangChangeCommand):
			continue
		else:
			yield command


def deduplicate_language_command(speech_sequence, ctx: SpeechContext, start_language=None):
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

	for command in speech_sequence:
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
	speech_sequence: Iterable[SpeechCmd],
	ctx: SpeechContext,
) -> Iterator[SpeechCmd]:
	"""
	Convert each LangChangeCommand / WVLangChangeCommand into a voice key.
	All other commands pass through unchanged.
	"""
	for cmd in speech_sequence:
		if isinstance(cmd, (LangChangeCommand, WVLangChangeCommand)):
			lang = cmd.lang or ctx.default_voice_language
			yield SelectVoice(ctx.voice_name_for_language(lang) or ctx.default_voice_name)
		else:
			yield cmd


def inject_langchange_reorder(
	speech_sequence: Iterable[SpeechCmd],
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

	for cmd in speech_sequence:
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
