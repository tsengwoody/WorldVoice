"""Normalize legacy command types at the boundary of the pure runtime."""

from collections.abc import Iterable, Iterator

from speech.commands import BreakCommand

from ..driver import Voice
from ..runtime.models import Pause, SelectVoice


def normalize_legacy_commands(sequence: Iterable[object]) -> Iterator[object]:
    for command in sequence:
        if isinstance(command, Voice):
            yield SelectVoice(command.name)
        elif isinstance(command, BreakCommand):
            yield Pause(command.time / 1000)
        else:
            yield command
