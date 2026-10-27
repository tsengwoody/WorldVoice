"""Correlate source-local wire indexes with speech segments, reusing them cyclically.

Each source gives every segment one contiguous run of wire indexes, from a cursor
that goes round the contract range and never splits a run across its maximum, as
NVDA's own index counter wraps (speech/manager.py, SpeechManager.MAX_INDEX). A run
stays reserved until its segment is retired, so no wire index belongs to two
unretired segments, and a retired index is handed out again only once the cursor
has come round to it. A segment that cannot get a free run is still spoken: it
keeps only its terminal marker (DRAIN: no wire index at all), and completion
reports all of its original indexes in order.

A live driver core must keep its ledger across runtime handoffs. Closing a
ledger releases its identity history; the owner must close the old core before
publishing it through a fresh ledger.
"""

import logging
from dataclasses import dataclass, field
from threading import Lock

from ..runtime.completion import CompletionRule, rule_for
from ..runtime.models import (
	CompletionContract,
	CompletionMode,
	EventKind,
	PlaybackContext,
	PlaybackEvent,
)

log = logging.getLogger(__name__)


class IndexSpaceExhausted(RuntimeError):
	"""Unretired segments reserve every wire index a segment's terminal marker could use."""


class InvalidIndexContext(RuntimeError):
	"""The binding or segment is not valid for this ledger."""


@dataclass(frozen=True)
class IndexAllocation:
	wireIndexes: tuple[int, ...]
	endIndex: int | None


@dataclass
class _Segment:
	segmentId: int
	originals: tuple[int, ...]
	allocation: IndexAllocation
	# Every wire index the segment holds, reserved until it is retired.
	span: range
	cursor: int = 0
	delivered: set[int] = field(default_factory=set)
	endSeen: bool = False
	drainSeen: bool = False
	finished: bool = False


@dataclass
class _Source:
	# Strong reference prevents id reuse even while this source is unbound.
	source: object
	mode: CompletionMode
	rule: CompletionRule
	minimum: int
	maximum: int
	nextIndex: int
	binding: object = None
	# Set by the first segment that gets no free run; later ones log at DEBUG.
	warned: bool = False
	segments: dict[int, _Segment] = field(default_factory=dict)
	indexes: dict[int, _Segment] = field(default_factory=dict)


@dataclass
class _Binding:
	# Never read, but needed: bindings are keyed by id(sourceId), and this strong reference keeps
	# that id from being reused by another object while the binding exists.
	sourceId: object
	state: _Source
	token: object = field(default_factory=object)


def _findStart(state: _Source, count: int) -> int | None:
	"""Return the start of the first free run of count indexes, cyclically from the cursor."""
	if not count:
		return state.nextIndex
	spans = [segment.span for segment in state.segments.values() if segment.span]
	size = state.maximum - state.minimum + 1
	start, scanned = state.nextIndex, 0
	while scanned < size:
		stop = start + count
		if stop > state.maximum + 1:
			# A run never crosses the maximum; the skipped tail is free again on the next cycle.
			# This also wraps a start just past the maximum.
			scanned += state.maximum + 1 - start
			start = state.minimum
			continue
		blocker = max((span.stop for span in spans if span.start < stop and start < span.stop), default=None)
		if blocker is None:
			return start
		# The strict overlap test makes blocker > start, so each pass moves on. With <=, a span
		# ending at start would block it again and loop for ever under the lock.
		scanned += blocker - start
		start = blocker
	return None


class IndexLedger:
	def __init__(self):
		self._lock = Lock()
		self._sources: dict[int, _Source] = {}
		self._bindings: dict[int, _Binding] = {}
		self._closed = False

	def bind(self, source: object, sourceId: object, contract: CompletionContract) -> object:
		"""Return an opaque token identifying this exact binding generation."""
		mode, indexRange = contract.mode, contract.index_range
		rule = rule_for(contract)
		if not rule.correlated or indexRange is None:
			raise InvalidIndexContext("Index allocation requires a correlated completion contract")
		minimum, maximum = indexRange.minimum, indexRange.maximum
		with self._lock:
			if self._closed:
				raise InvalidIndexContext("Ledger is closed")
			state = self._sources.get(id(source))
			existing = self._bindings.get(id(sourceId))
			if existing is not None and existing.state is not state:
				raise InvalidIndexContext("Source ID is already bound to another source")
			if state is not None:
				if (state.mode, state.minimum, state.maximum) != (mode, minimum, maximum):
					raise InvalidIndexContext("A source cannot change its completion contract")
				if state.binding is not None:
					if state.binding is not existing:
						raise InvalidIndexContext("Source is already bound to another source ID")
					return existing.token
			else:
				state = _Source(source, mode, rule, minimum, maximum, minimum)
				self._sources[id(source)] = state
			binding = _Binding(sourceId, state)
			state.binding = binding
			self._bindings[id(sourceId)] = binding
			return binding.token

	def prepare(self, context: PlaybackContext, originalIndexes: tuple[int, ...]) -> IndexAllocation:
		sourceId, segmentId = context.source_id, context.segment_id
		# Normalize caller-owned inputs before locking; map keys below are plain ints.
		originals = tuple(int(index) for index in originalIndexes)
		segmentId = int(segmentId)
		with self._lock:
			binding = self._bindings.get(id(sourceId))
			if self._closed or binding is None:
				raise InvalidIndexContext("Source is not bound to this ledger")
			state = binding.state
			if segmentId in state.segments:
				raise InvalidIndexContext("Segment is already prepared and has not been retired")
			marker = int(state.rule.requires_end)
			ordinary = len(originals)
			start = _findStart(state, ordinary + marker)
			degraded = start is None
			if degraded:
				# Keep only the terminal marker; completion reports every original in order.
				ordinary = 0
				start = _findStart(state, marker)
				if start is None:
					raise IndexSpaceExhausted("Source wire index range is exhausted")
				level = logging.DEBUG if state.warned else logging.WARNING
				state.warned = True
			span = range(start, start + ordinary + marker)
			allocation = IndexAllocation(tuple(span[:ordinary]), span[-1] if marker else None)
			segment = _Segment(segmentId, originals, allocation, span)
			state.segments[segmentId] = segment
			for index in span:
				state.indexes[index] = segment
			# Just past the maximum after a run that ends there; _findStart wraps it.
			state.nextIndex = span.stop
		# Log after unlocking: handlers are external code.
		if degraded:
			log.log(
				level,
				"WorldVoice index range %d..%d has no room for a speech segment with %d indexes; "
				"its indexes are reported when it completes",
				state.minimum,
				state.maximum,
				len(originals),
			)
		return allocation

	def receiveIndex(
		self,
		sourceId: object,
		wireIndex: int,
		*,
		bindingToken: object | None = None,
	) -> tuple[PlaybackEvent, ...]:
		"""Decode atomically, optionally requiring the generation returned by bind."""
		if type(wireIndex) is not int:
			return ()
		with self._lock:
			binding = self._bindings.get(id(sourceId))
			if self._closed or binding is None:
				return ()
			if bindingToken is not None and binding.token is not bindingToken:
				return ()
			state = binding.state
			segment = state.indexes.get(wireIndex)
			if segment is None:
				return ()
			allocation = segment.allocation
			terminal = wireIndex == allocation.endIndex
			stop = len(segment.originals) if terminal else wireIndex - allocation.wireIndexes[0] + 1
			events = self._pendingIndexes(sourceId, segment, stop)
			if terminal:
				segment.endSeen = True
				segment.finished = state.rule.is_complete(True, segment.drainSeen)
				events.append(PlaybackEvent(EventKind.SEGMENT_END, sourceId, segment_id=segment.segmentId))
				self._removeIndexes(state, segment)
			return tuple(events)

	def receiveSegmentEvent(
		self,
		event: PlaybackEvent,
		*,
		bindingToken: object,
	) -> tuple[PlaybackEvent, ...]:
		"""Decode a context-bound drain/failure into one ordered event batch."""
		if event.kind is not EventKind.SEGMENT_DRAINED and event.kind is not EventKind.SEGMENT_FAILED:
			return ()
		if type(event.segment_id) is not int:
			return ()
		with self._lock:
			binding = self._bindings.get(id(event.source_id))
			if self._closed or binding is None or binding.token is not bindingToken:
				return ()
			state = binding.state
			segment = state.segments.get(event.segment_id)
			if segment is None or segment.finished:
				return ()
			if event.kind is EventKind.SEGMENT_FAILED:
				segment.finished = True
				self._removeIndexes(state, segment)
				return (event,)
			if not state.rule.requires_drain or segment.drainSeen:
				return ()
			events = self._pendingIndexes(event.source_id, segment, len(segment.originals))
			segment.drainSeen = True
			segment.finished = state.rule.is_complete(segment.endSeen, True)
			# AND still needs the real terminal callback when drain arrives first.
			self._removeIndexes(state, segment, keepTerminal=not segment.finished)
			return (*events, event)

	def retireSegment(self, context: PlaybackContext) -> None:
		sourceId, segmentId = context.source_id, int(context.segment_id)
		with self._lock:
			binding = self._bindings.get(id(sourceId))
			if binding is None:
				return
			state = binding.state
			segment = state.segments.pop(segmentId, None)
			if segment is not None:
				self._removeIndexes(state, segment)

	def retireSource(self, sourceId: object) -> None:
		with self._lock:
			binding = self._bindings.get(id(sourceId))
			if binding is not None:
				binding.state.segments.clear()
				binding.state.indexes.clear()

	def unbind(self, sourceId: object) -> None:
		with self._lock:
			binding = self._bindings.pop(id(sourceId), None)
			if binding is not None:
				binding.state.binding = None
				binding.state.segments.clear()
				binding.state.indexes.clear()
		# Keep binding alive until after unlocking, including arbitrary source IDs.

	def close(self) -> None:
		with self._lock:
			self._closed = True
			sources, bindings = self._sources, self._bindings
			self._sources, self._bindings = {}, {}
			for state in sources.values():
				state.binding = None
		# Release source objects outside the lock: finalizers may call external code.
		sources.clear()
		bindings.clear()

	@staticmethod
	def _pendingIndexes(sourceId: object, segment: _Segment, stop: int) -> list[PlaybackEvent]:
		events = []
		for original in segment.originals[segment.cursor : stop]:
			if original not in segment.delivered:
				segment.delivered.add(original)
				events.append(PlaybackEvent(EventKind.INDEX, sourceId, original, segment.segmentId))
		segment.cursor = max(segment.cursor, stop)
		return events

	@staticmethod
	def _removeIndexes(state: _Source, segment: _Segment, *, keepTerminal: bool = False) -> None:
		for index in segment.allocation.wireIndexes:
			state.indexes.pop(index, None)
		if not keepTerminal and segment.allocation.endIndex is not None:
			state.indexes.pop(segment.allocation.endIndex, None)
