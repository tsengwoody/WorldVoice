"""Encode caller indexes and any required terminal marker at the engine boundary.

A segment the ledger gave no wire indexes (no free run was left) goes out without
its caller indexes; the ledger reports them when the segment completes.
"""

from speech.commands import IndexCommand

from ..runtime.models import PlaybackContext, SpeechCommands
from ..speechCommands import WorldVoiceIndexCommand
from .indexLedger import IndexLedger


def encode_segment(
	commands: SpeechCommands,
	context: PlaybackContext,
	ledger: IndexLedger,
) -> SpeechCommands:
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
		encoded = tuple(
			IndexCommand(next(indexes)) if isinstance(command, IndexCommand) else command
			for command in commands
			if allocation.wire_indexes or not isinstance(command, IndexCommand)
		)
		if allocation.end_index is not None:
			return (*encoded, WorldVoiceIndexCommand(allocation.end_index))
		return encoded
	except Exception:
		ledger.retire_segment(context)
		raise
