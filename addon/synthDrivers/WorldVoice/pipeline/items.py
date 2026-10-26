"""The item pause (item_wait_factor): a break between two text items."""

from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING

from speech.commands import BreakCommand

from .breaks import _is_item_edge_break, _merge_edge_breaks
from .context import SpeechContext
from .sequence import _MISSING, SpeechCmd, _both_text

if TYPE_CHECKING:
	from .settings import PipelineSettings


def item_wait_factor(
	speechSequence: Iterable[SpeechCmd],
	settings: "PipelineSettings",
	ctx: SpeechContext,
) -> Iterator[SpeechCmd]:
	"""Insert a BreakCommand between every two consecutive plain-text items.

	The edge break the number stage put at the end or start of an item (NumberItemEdgeBreakCommand)
	still leaves the two items consecutive: the item break goes in before it, and where breaks meet
	around an edge break only one stays, as in the punctuation stage (_merge_edge_breaks): the
	longest, on a tie the item break. Corrected by fix/number-edge-pause-items (decided by the user,
	2026-10-24).
	"""
	wait_factor = settings.scaled_item_wait()
	if wait_factor <= 0:
		yield from speechSequence
		return
	yield from _merge_edge_breaks(_insert_item_breaks(speechSequence, BreakCommand(wait_factor)))


def _insert_item_breaks(speechSequence: Iterable[SpeechCmd], break_cmd: SpeechCmd) -> Iterator[SpeechCmd]:
	"""Yield *speechSequence* with *break_cmd* between two adjacent text items, or two text items
	that only item edge breaks separate: before those breaks."""
	previous = _MISSING
	held: list[SpeechCmd] = []
	for current in speechSequence:
		if isinstance(previous, str) and _is_item_edge_break(current):
			held.append(current)
			continue
		if _both_text(previous, current):
			yield break_cmd
		yield from held
		held.clear()
		yield current
		previous = current
	yield from held
