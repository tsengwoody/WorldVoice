"""What each completion contract means, in one table.

The scheduler, the engine adapter, the index ledger, the event bridge and the
session read a contract only through its rule. Adding or removing a completion
mode changes one row here instead of every component's branches.
"""

from dataclasses import dataclass
from enum import Enum

from .models import CompletionContract, CompletionMode, EventKind


class SpeakEntry(Enum):
	"""Which core entry the adapter calls; runtime never calls a core itself."""

	SEGMENT = "segment"  # speak_segment(commands, token, context=, on_event=)
	LEGACY_SEGMENT = "legacy_segment"  # speak_legacy_segment(commands, token, context=, on_event=)
	PLAIN = "plain"  # speak(commands[, cancellationToken=])


class Signal(Enum):
	"""What an accepted event means for its segment."""

	END = "end"
	DRAIN = "drain"
	FAIL = "fail"


@dataclass(frozen=True)
class CompletionRule:
	# Uses the index ledger: markers are encoded and a playback context is required.
	correlated: bool
	# Events must carry the segment's ID; otherwise they must carry none.
	segment_scoped: bool
	end_event: EventKind
	# Not None exactly when the core reports segment events (drain/failure).
	drain_event: EventKind | None
	fails_on_segment_failed: bool
	requires_end: bool
	requires_drain: bool
	entry: SpeakEntry

	def accepts_segment(self, segment_id: int | None, event_segment_id: int | None) -> bool:
		if self.segment_scoped:
			return event_segment_id == segment_id
		return event_segment_id is None

	def signal_for(self, kind: EventKind) -> Signal | None:
		if kind is self.end_event:
			return Signal.END
		if kind is self.drain_event:
			return Signal.DRAIN
		if kind is EventKind.SEGMENT_FAILED and self.fails_on_segment_failed:
			return Signal.FAIL
		return None

	def is_complete(self, end_seen: bool, drain_seen: bool) -> bool:
		return (end_seen or not self.requires_end) and (drain_seen or not self.requires_drain)

	def indexes_finished(self, end_seen: bool, drain_seen: bool) -> bool:
		"""Whether later INDEX events for the segment are stale."""
		return end_seen if self.requires_end else drain_seen


_RULES = {
	(CompletionMode.LEGACY_DONE, False): CompletionRule(
		correlated=False,
		segment_scoped=False,
		end_event=EventKind.DONE,
		drain_event=None,
		fails_on_segment_failed=False,
		requires_end=True,
		requires_drain=False,
		entry=SpeakEntry.PLAIN,
	),
	# Contextual legacy: software-correlated DONE without a native drain barrier.
	(CompletionMode.LEGACY_DONE, True): CompletionRule(
		correlated=False,
		segment_scoped=True,
		end_event=EventKind.DONE,
		drain_event=None,
		fails_on_segment_failed=True,
		requires_end=True,
		requires_drain=False,
		entry=SpeakEntry.LEGACY_SEGMENT,
	),
	(CompletionMode.END_INDEX, False): CompletionRule(
		correlated=True,
		segment_scoped=True,
		end_event=EventKind.SEGMENT_END,
		drain_event=None,
		fails_on_segment_failed=True,
		requires_end=True,
		requires_drain=False,
		entry=SpeakEntry.PLAIN,
	),
	(CompletionMode.END_INDEX_AND_DRAIN, False): CompletionRule(
		correlated=True,
		segment_scoped=True,
		end_event=EventKind.SEGMENT_END,
		drain_event=EventKind.SEGMENT_DRAINED,
		fails_on_segment_failed=True,
		requires_end=True,
		requires_drain=True,
		entry=SpeakEntry.SEGMENT,
	),
	# A drain segment has no terminal marker; SEGMENT_END is recorded but never required.
	(CompletionMode.DRAIN, False): CompletionRule(
		correlated=True,
		segment_scoped=True,
		end_event=EventKind.SEGMENT_END,
		drain_event=EventKind.SEGMENT_DRAINED,
		fails_on_segment_failed=True,
		requires_end=False,
		requires_drain=True,
		entry=SpeakEntry.SEGMENT,
	),
}


def rule_for(contract: CompletionContract) -> CompletionRule:
	return _RULES[(contract.mode, contract.legacy_contextual)]
