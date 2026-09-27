"""Encode caller indexes and a single terminal marker at the engine boundary."""

from speech.commands import IndexCommand

from .._speechcommand import WorldVoiceIndexCommand
from ..indexLedger import IndexLedger
from ..runtime.models import PlaybackContext, SpeechCommands


def encode_segment(commands: SpeechCommands, context: PlaybackContext,
                   ledger: IndexLedger) -> SpeechCommands:
    # Snapshot and validate the complete input before publishing any mapping.
    commands = tuple(commands)
    originals = []
    for command in commands:
        if isinstance(command, WorldVoiceIndexCommand):
            raise ValueError("Input already contains an internal segment marker")
        if isinstance(command, IndexCommand):
            if not isinstance(command.index, int):
                raise ValueError("Index command requires an integer")
            originals.append(command.index)
    allocation = ledger.prepare(context, tuple(originals))
    try:
        indexes = iter(allocation.wire_indexes)
        encoded = tuple(IndexCommand(next(indexes)) if isinstance(command, IndexCommand)
                        else command for command in commands)
        return (*encoded, WorldVoiceIndexCommand(allocation.end_index))
    except Exception:
        ledger.retire_segment(context)
        raise
