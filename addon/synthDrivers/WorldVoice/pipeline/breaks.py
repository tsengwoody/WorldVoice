"""The pauses the stages add, how an edge break next to a number stays recognizable, and how
pauses that meet around one are merged."""

from collections.abc import Iterable, Iterator

from speech.commands import BreakCommand

from .sequence import SpeechCmd


class NumberBreakCommand(BreakCommand):
	"""Pause between numbers, and, in number and group modes, between the pieces and symbol names of a
	number and between two numbers that only whitespace separates."""


class NumberEdgeBreakCommand(NumberBreakCommand):
	"""Pause between a number and the spoken text next to it (number and group modes)."""


class NumberItemEdgeBreakCommand(NumberEdgeBreakCommand):
	"""An edge break at the start or end of the number's item, where the spoken text next to the
	number is in another item: item_wait_factor's break goes in next to it."""


# Set on the plain BreakCommand another synth gets for a NumberEdgeBreakCommand (_plain_breaks), so
# the item and punctuation stages still tell an edge break apart: _ITEM_EDGE for one at an item's
# start or end, True for any other.
_EDGE_MARKER = "worldvoice_number_edge"
_ITEM_EDGE = "item"


def _edge_kind(command: SpeechCmd) -> bool | str:
	if isinstance(command, NumberItemEdgeBreakCommand):
		return _ITEM_EDGE
	if isinstance(command, NumberEdgeBreakCommand):
		return True
	return getattr(command, _EDGE_MARKER, False)


def _is_edge_break(command: SpeechCmd) -> bool:
	return bool(_edge_kind(command))


def _is_item_edge_break(command: SpeechCmd) -> bool:
	return _edge_kind(command) == _ITEM_EDGE


class PunctuationBreakCommand(BreakCommand):
	"""Pause after a configured punctuation mark."""


def _merge_edge_breaks(speech_sequence: Iterable[SpeechCmd]) -> Iterator[SpeechCmd]:
	"""Yield *speech_sequence* with each run that holds an edge break and another break cut to one break.

	A run is what lies between two non-blank text items (or before the first, or after the last):
	breaks, blank text and other commands. The break kept is the longest; on a tie the first that is
	not an edge break, or the first edge break. The other items of the run keep their order. Runs are
	told apart by position: one break object can sit in several runs.
	"""
	run: list[SpeechCmd] = []
	for item in speech_sequence:
		if isinstance(item, str) and item.strip():
			yield from _merged_run(run)
			run.clear()
			yield item
		else:
			run.append(item)
	yield from _merged_run(run)


def _merged_run(run: list[SpeechCmd]) -> list[SpeechCmd]:
	breaks = [index for index, item in enumerate(run) if isinstance(item, BreakCommand)]
	if len(breaks) < 2 or not any(_is_edge_break(run[index]) for index in breaks):
		return run
	# max keeps the first of equal keys.
	kept = max(breaks, key=lambda index: (run[index].time, not _is_edge_break(run[index])))
	return [item for index, item in enumerate(run) if index == kept or not isinstance(item, BreakCommand)]


def _plain_breaks(speech_sequence: Iterable[SpeechCmd]) -> list[SpeechCmd]:
	"""The sequence with each BreakCommand subclass replaced by a plain BreakCommand.

	NVDA's speechXml, which OneCore uses, finds a command's converter by its class name and
	drops the rest of the utterance at a command it has none for. A break made from an edge break
	(or from a plain one already marked) carries _EDGE_MARKER, so the item and punctuation stages
	still tell it apart. NVDA's BreakCommand has no __slots__ and its __eq__ reads only type and
	time, and the synths read only .time, so the attribute is invisible to them.
	"""
	return [_plain_break(item) if isinstance(item, BreakCommand) else item for item in speech_sequence]


def _plain_break(command: BreakCommand) -> BreakCommand:
	plain = BreakCommand(command.time)
	kind = _edge_kind(command)
	if kind:
		setattr(plain, _EDGE_MARKER, kind)
	return plain
