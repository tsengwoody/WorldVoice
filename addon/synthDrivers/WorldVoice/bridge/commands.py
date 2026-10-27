"""Normalize legacy command types at the boundary of the pure runtime."""

from collections.abc import Iterable, Iterator

from speech.commands import BreakCommand

from ..runtime.models import Pause
from ..speechCommands import WorldVoiceIndexCommand


def normalizeNvdaCommands(sequence: Iterable[object]) -> Iterator[object]:
	for command in sequence:
		if isinstance(command, WorldVoiceIndexCommand):
			raise ValueError("Internal segment markers cannot be supplied externally")
		if isinstance(command, BreakCommand):
			yield Pause(command.time / 1000)
		else:
			yield command
