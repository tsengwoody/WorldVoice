"""Correlate source-local, never-reused wire indexes with speech segments.

A live driver core must keep its ledger across runtime handoffs. Closing a
ledger releases its identity history; the owner must close the old core before
publishing it through a fresh ledger.
"""

from dataclasses import dataclass, field
from threading import Lock

from .runtime.models import (
    CompletionContract, CompletionMode, EventKind, PlaybackContext, PlaybackEvent,
)


class IndexSpaceExhausted(RuntimeError):
    """The source cannot allocate a complete segment within its wire range."""


class InvalidIndexContext(RuntimeError):
    """The binding or segment is not valid for this ledger."""


@dataclass(frozen=True)
class IndexAllocation:
    wire_indexes: tuple[int, ...]
    end_index: int


@dataclass
class _Segment:
    segment_id: int
    originals: tuple[int, ...]
    allocation: IndexAllocation
    cursor: int = 0
    delivered: set[int] = field(default_factory=set)


@dataclass
class _Source:
    # Strong reference prevents id reuse even while this source is unbound.
    source: object
    mode: CompletionMode
    minimum: int
    maximum: int
    next_index: int
    binding: object = None
    segments: dict[int, _Segment] = field(default_factory=dict)
    indexes: dict[int, _Segment] = field(default_factory=dict)


@dataclass
class _Binding:
    source_id: object
    state: _Source


class IndexLedger:
    def __init__(self):
        self._lock = Lock()
        self._sources: dict[int, _Source] = {}
        self._bindings: dict[int, _Binding] = {}
        self._closed = False

    def bind(self, source: object, source_id: object, contract: CompletionContract) -> None:
        mode, index_range = contract.mode, contract.index_range
        if mode not in (CompletionMode.END_INDEX, CompletionMode.END_INDEX_AND_DRAIN) or index_range is None:
            raise InvalidIndexContext("Index allocation requires a marker completion contract")
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
                    return
            else:
                state = _Source(source, mode, minimum, maximum, minimum)
                self._sources[id(source)] = state
            binding = _Binding(source_id, state)
            state.binding = binding
            self._bindings[id(source_id)] = binding

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
            end_index = state.next_index + len(originals)
            if end_index > state.maximum:
                raise IndexSpaceExhausted("Source wire index range is exhausted")
            allocation = IndexAllocation(tuple(range(state.next_index, end_index)), end_index)
            segment = _Segment(segment_id, originals, allocation)
            state.segments[segment_id] = segment
            for index in (*allocation.wire_indexes, allocation.end_index):
                state.indexes[index] = segment
            state.next_index = end_index + 1
            return allocation

    def receive_index(self, source_id: object, wire_index: int) -> tuple[PlaybackEvent, ...]:
        if type(wire_index) is not int:
            return ()
        with self._lock:
            binding = self._bindings.get(id(source_id))
            if self._closed or binding is None:
                return ()
            state = binding.state
            segment = state.indexes.get(wire_index)
            if segment is None:
                return ()
            allocation = segment.allocation
            terminal = wire_index == allocation.end_index
            stop = len(segment.originals) if terminal else wire_index - allocation.wire_indexes[0] + 1
            events = []
            for original in segment.originals[segment.cursor:stop]:
                if original not in segment.delivered:
                    segment.delivered.add(original)
                    events.append(PlaybackEvent(EventKind.INDEX, source_id, original, segment.segment_id))
            segment.cursor = max(segment.cursor, stop)
            if terminal:
                events.append(PlaybackEvent(EventKind.SEGMENT_END, source_id, segment_id=segment.segment_id))
                self._remove_indexes(state, segment)
            return tuple(events)

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
    def _remove_indexes(state: _Source, segment: _Segment) -> None:
        for index in (*segment.allocation.wire_indexes, segment.allocation.end_index):
            state.indexes.pop(index, None)
