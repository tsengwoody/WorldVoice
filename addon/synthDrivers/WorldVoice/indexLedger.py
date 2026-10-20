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

from .runtime.completion import CompletionRule, rule_for
from .runtime.models import (
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
	wire_indexes: tuple[int, ...]
	end_index: int | None


@dataclass
class _Segment:
	segment_id: int
	originals: tuple[int, ...]
	allocation: IndexAllocation
	# Every wire index the segment holds, reserved until it is retired.
	span: range
	cursor: int = 0
	delivered: set[int] = field(default_factory=set)
	end_seen: bool = False
	drain_seen: bool = False
	finished: bool = False


@dataclass
class _Source:
	# Strong reference prevents id reuse even while this source is unbound.
	source: object
	mode: CompletionMode
	rule: CompletionRule
	minimum: int
	maximum: int
	next_index: int
	binding: object = None
	# Set by the first segment that gets no free run; later ones log at DEBUG.
	warned: bool = False
	segments: dict[int, _Segment] = field(default_factory=dict)
	indexes: dict[int, _Segment] = field(default_factory=dict)


@dataclass
class _Binding:
	# Never read, but needed: bindings are keyed by id(source_id), and this strong reference keeps
	# that id from being reused by another object while the binding exists.
	source_id: object
	state: _Source
	token: object = field(default_factory=object)


def _find_start(state: _Source, count: int) -> int | None:
	"""Return the start of the first free run of count indexes, cyclically from the cursor."""
	if not count:
		return state.next_index
	spans = [segment.span for segment in state.segments.values() if segment.span]
	size = state.maximum - state.minimum + 1
	start, scanned = state.next_index, 0
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

	def bind(self, source: object, source_id: object, contract: CompletionContract) -> object:
		"""Return an opaque token identifying this exact binding generation."""
		mode, index_range = contract.mode, contract.index_range
		rule = rule_for(contract)
		if not rule.correlated or index_range is None:
			raise InvalidIndexContext("Index allocation requires a correlated completion contract")
		minimum, maximum = index_range.minimum, index_range.maximum
		with self._lock:
			if self._closed:
				raise InvalidIndexContext("Ledger is closed")
			state = self._sources.get(id(source))
			existing = self._bindings.get(id(source_id))
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
			binding = _Binding(source_id, state)
			state.binding = binding
			self._bindings[id(source_id)] = binding
			return binding.token

	def prepare(self, context: PlaybackContext, original_indexes: tuple[int, ...]) -> IndexAllocation:
		source_id, segment_id = context.source_id, context.segment_id
		# Normalize caller-owned inputs before locking; map keys below are plain ints.
		originals = tuple(int(index) for index in original_indexes)
		segment_id = int(segment_id)
		with self._lock:
			binding = self._bindings.get(id(source_id))
			if self._closed or binding is None:
				raise InvalidIndexContext("Source is not bound to this ledger")
			state = binding.state
			if segment_id in state.segments:
				raise InvalidIndexContext("Segment is already prepared and has not been retired")
			marker = int(state.rule.requires_end)
			ordinary = len(originals)
			start = _find_start(state, ordinary + marker)
			degraded = start is None
			if degraded:
				# Keep only the terminal marker; completion reports every original in order.
				ordinary = 0
				start = _find_start(state, marker)
				if start is None:
					raise IndexSpaceExhausted("Source wire index range is exhausted")
				level = logging.DEBUG if state.warned else logging.WARNING
				state.warned = True
			span = range(start, start + ordinary + marker)
			allocation = IndexAllocation(tuple(span[:ordinary]), span[-1] if marker else None)
			segment = _Segment(segment_id, originals, allocation, span)
			state.segments[segment_id] = segment
			for index in span:
				state.indexes[index] = segment
			# Just past the maximum after a run that ends there; _find_start wraps it.
			state.next_index = span.stop
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

	def receive_index(
		self,
		source_id: object,
		wire_index: int,
		*,
		binding_token: object | None = None,
	) -> tuple[PlaybackEvent, ...]:
		"""Decode atomically, optionally requiring the generation returned by bind."""
		if type(wire_index) is not int:
			return ()
		with self._lock:
			binding = self._bindings.get(id(source_id))
			if self._closed or binding is None:
				return ()
			if binding_token is not None and binding.token is not binding_token:
				return ()
			state = binding.state
			segment = state.indexes.get(wire_index)
			if segment is None:
				return ()
			allocation = segment.allocation
			terminal = wire_index == allocation.end_index
			stop = len(segment.originals) if terminal else wire_index - allocation.wire_indexes[0] + 1
			events = self._pending_indexes(source_id, segment, stop)
			if terminal:
				segment.end_seen = True
				segment.finished = state.rule.is_complete(True, segment.drain_seen)
				events.append(PlaybackEvent(EventKind.SEGMENT_END, source_id, segment_id=segment.segment_id))
				self._remove_indexes(state, segment)
			return tuple(events)

	def receive_segment_event(
		self,
		event: PlaybackEvent,
		*,
		binding_token: object,
	) -> tuple[PlaybackEvent, ...]:
		"""Decode a context-bound drain/failure into one ordered event batch."""
		if event.kind is not EventKind.SEGMENT_DRAINED and event.kind is not EventKind.SEGMENT_FAILED:
			return ()
		if type(event.segment_id) is not int:
			return ()
		with self._lock:
			binding = self._bindings.get(id(event.source_id))
			if self._closed or binding is None or binding.token is not binding_token:
				return ()
			state = binding.state
			segment = state.segments.get(event.segment_id)
			if segment is None or segment.finished:
				return ()
			if event.kind is EventKind.SEGMENT_FAILED:
				segment.finished = True
				self._remove_indexes(state, segment)
				return (event,)
			if not state.rule.requires_drain or segment.drain_seen:
				return ()
			events = self._pending_indexes(event.source_id, segment, len(segment.originals))
			segment.drain_seen = True
			segment.finished = state.rule.is_complete(segment.end_seen, True)
			# AND still needs the real terminal callback when drain arrives first.
			self._remove_indexes(state, segment, keep_terminal=not segment.finished)
			return (*events, event)

	def retire_segment(self, context: PlaybackContext) -> None:
		source_id, segment_id = context.source_id, int(context.segment_id)
		with self._lock:
			binding = self._bindings.get(id(source_id))
			if binding is None:
				return
			state = binding.state
			segment = state.segments.pop(segment_id, None)
			if segment is not None:
				self._remove_indexes(state, segment)

	def retire_source(self, source_id: object) -> None:
		with self._lock:
			binding = self._bindings.get(id(source_id))
			if binding is not None:
				binding.state.segments.clear()
				binding.state.indexes.clear()

	def unbind(self, source_id: object) -> None:
		with self._lock:
			binding = self._bindings.pop(id(source_id), None)
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
	def _pending_indexes(source_id: object, segment: _Segment, stop: int) -> list[PlaybackEvent]:
		events = []
		for original in segment.originals[segment.cursor : stop]:
			if original not in segment.delivered:
				segment.delivered.add(original)
				events.append(PlaybackEvent(EventKind.INDEX, source_id, original, segment.segment_id))
		segment.cursor = max(segment.cursor, stop)
		return events

	@staticmethod
	def _remove_indexes(state: _Source, segment: _Segment, *, keep_terminal: bool = False) -> None:
		for index in segment.allocation.wire_indexes:
			state.indexes.pop(index, None)
		if not keep_terminal and segment.allocation.end_index is not None:
			state.indexes.pop(segment.allocation.end_index, None)
