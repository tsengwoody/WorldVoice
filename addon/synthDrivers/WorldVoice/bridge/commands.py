"""Normalize NVDA command objects at the boundary of the pure runtime."""

from collections.abc import Iterable, Iterator

from speech.commands import BreakCommand, LangChangeCommand, SynthParamCommand

from ..runtime.models import Pause, SelectVoice
from ..speechCommands import WorldVoiceIndexCommand, WVLangChangeCommand


def _isTrackedParameter(command: object) -> bool:
	# Language commands are already voice selections here (lang_cmd_to_voice); a stray one is not
	# replayed.
	return isinstance(command, SynthParamCommand) and not isinstance(
		command,
		(LangChangeCommand, WVLangChangeCommand),
	)


def normalizeNvdaCommands(sequence: Iterable[object]) -> Iterator[object]:
	"""Turn breaks into Pause and replay the synth parameters in effect after every segment start.

	The request builder ends a segment at every Pause and SelectVoice, and each segment is its own
	engine call, which starts from the defaults. So, like NVDA's ParamChangeTracker at the start of
	every utterance (ref/nvda/source/speech/manager.py:83-112), the parameter commands in effect
	(the last of each type that is not a default) are yielded again before the first text after a
	Pause or SelectVoice. Until that text, a parameter command only updates them, so none is yielded
	twice; other commands keep their place. Nothing is yielded for parameters no text follows: a
	segment of parameter commands alone would make an engine call with no text (spec
	feat/segment-pause §4.6; decided by the user, 2026-11-03, Q1).
	"""
	changed: dict[type, object] = {}
	pending = False
	for command in sequence:
		if isinstance(command, WorldVoiceIndexCommand):
			raise ValueError("Internal segment markers cannot be supplied externally")
		if _isTrackedParameter(command):
			if command.isDefault:
				changed.pop(type(command), None)
			else:
				changed[type(command)] = command
			if pending:
				continue
		elif isinstance(command, str) and pending:
			yield from changed.values()
			pending = False
		if isinstance(command, BreakCommand):
			yield Pause(command.time / 1000)
			pending = True
		else:
			yield command
			if isinstance(command, SelectVoice):
				pending = True
