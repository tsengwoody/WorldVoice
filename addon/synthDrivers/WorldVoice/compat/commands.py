"""Normalize legacy command types at the boundary of the pure runtime."""

from collections.abc import Iterable, Iterator

from speech.commands import BreakCommand

from .._speechcommand import WorldVoiceIndexCommand
from ..runtime.models import Pause


def normalize_legacy_commands(sequence: Iterable[object]) -> Iterator[object]:
	for command in sequence:
		if isinstance(command, WorldVoiceIndexCommand):
			raise ValueError("Internal segment markers cannot be supplied externally")
		if isinstance(command, BreakCommand):
			yield Pause(command.time / 1000)
		else:
			yield command
