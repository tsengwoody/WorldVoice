"""Translate NVDA notifications at the boundary of the pure voice runtime."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from threading import RLock

from ..runtime.completion import rule_for
from ..runtime.models import (
	CompletionContract,
	EventKind,
	PlaybackContext,
	PlaybackEvent,
	SegmentEventSink,
)
from .indexLedger import IndexLedger

# Frozen, so one instance can be every binding's default.
_LEGACY_CONTRACT = CompletionContract()


@dataclass(frozen=True, eq=False)
class _Binding:
	source: object
	sourceId: object
	completion: CompletionContract
	ledgerToken: object | None


class _BindingEvents(tuple):
	"""Keep one decoded batch while checking revocation between deliveries."""

	def __new__(cls, events: tuple[PlaybackEvent, ...], is_active: Callable[[], bool]):
		batch = super().__new__(cls, events)
		batch._is_active = is_active
		return batch

	def __iter__(self) -> Iterator[PlaybackEvent]:
		for event in super().__iter__():
			if not self._is_active():
				return
			yield event


class NvdaEventBridge:
	"""Own event subscriptions and resource identities, never request identities.

	The composition owner starts and closes the bridge in lifecycle order.
	Event delivery may run on other threads; the state lock protects snapshots
	only and is never held while calling handlers or public notifications.
	"""

	def __init__(self, owner, *, doneEvent, indexEvent, getSynth, indexLedger: IndexLedger | None = None):
		self._owner = owner
		self._doneEvent = doneEvent
		self._indexEvent = indexEvent
		self._get_synth = getSynth
		self._indexLedger = indexLedger
		self._lock = RLock()
		self._closed = False
		self._handler = None
		self._batchHandler = None
		self._sources = {}
		self._registrations = []

	def start(
		self,
		handler: Callable[[PlaybackEvent], None],
		*,
		batchHandler: Callable[[Callable[[], tuple[PlaybackEvent, ...]]], None] | None = None,
	) -> None:
		with self._lock:
			if self._closed:
				raise RuntimeError("Event bridge is closed")
			if self._handler is not None:
				raise RuntimeError("Event bridge is already started")
			self._handler = handler
			self._batchHandler = batchHandler
		try:
			for event, callback in (
				(self._doneEvent, self._onDone),
				(self._indexEvent, self._onIndex),
			):
				# Claim cleanup before register: it can add the handler then fail.
				with self._lock:
					self._registrations.append((event, callback))
				event.register(callback)
		except Exception as error:
			try:
				self.close()
			except Exception as cleanupError:
				raise error from cleanupError
			raise

	def bind(
		self,
		source: object,
		sourceId: object,
		*,
		completion: CompletionContract = _LEGACY_CONTRACT,
	) -> None:
		with self._lock:
			if self._closed:
				raise RuntimeError("Event bridge is closed")
			existing = self._sources.get(id(source))
			if existing is not None:
				if existing.sourceId is not sourceId:
					raise ValueError("Notification source is already bound to another source ID")
				if existing.completion != completion:
					raise ValueError("Notification source cannot change its completion contract")
				return
			ledgerToken = None
			if rule_for(completion).correlated:
				if self._indexLedger is None or self._batchHandler is None:
					raise ValueError("Marker completion requires an index ledger and batch handler")
				if any(binding.sourceId is sourceId for binding in self._sources.values()):
					raise ValueError("Marker source ID is already bound to another source")
				try:
					ledgerToken = self._indexLedger.bind(source, sourceId, completion)
				except Exception as error:
					# A ledger can publish its binding before raising.
					try:
						self._indexLedger.unbind(sourceId)
					except Exception as cleanupError:
						raise error from cleanupError
					raise
			# The binding object also serves as the deferred supplier's generation.
			self._sources[id(source)] = _Binding(source, sourceId, completion, ledgerToken)

	def unbind(self, sourceId: object) -> None:
		with self._lock:
			bindings = [binding for binding in self._sources.values() if binding.sourceId is sourceId]
			for binding in bindings:
				del self._sources[id(binding.source)]
			if any(rule_for(binding.completion).correlated for binding in bindings):
				self._indexLedger.unbind(sourceId)
		# Release source references after unlocking.

	def _bindingIsActive(self, binding: _Binding) -> bool:
		with self._lock:
			return not self._closed and self._sources.get(id(binding.source)) is binding

	def segmentSink(self, source: object, context: PlaybackContext) -> SegmentEventSink:
		"""Capture the actual resource, context and binding generation for a job."""
		with self._lock:
			binding = self._sources.get(id(source))
			if (
				self._closed
				or source is self._owner
				or binding is None
				or binding.source is not source
				or binding.sourceId is not context.source_id
				or rule_for(binding.completion).drain_event is None
			):
				raise ValueError("Segment events require a matching drain-capable source binding")
			batchHandler = self._batchHandler

		def receive(event: PlaybackEvent) -> None:
			if (
				event.kind not in (EventKind.SEGMENT_DRAINED, EventKind.SEGMENT_FAILED)
				or event.source_id is not context.source_id
				or event.segment_id != context.segment_id
				or not self._bindingIsActive(binding)
			):
				return

			def loadEvents() -> tuple[PlaybackEvent, ...]:
				if not self._bindingIsActive(binding):
					return ()
				# Decode inside the scheduler's delivery lock. The ledger token
				# also closes the race between bridge validation and decoding.
				events = self._indexLedger.receiveSegmentEvent(event, bindingToken=binding.ledgerToken)
				# An INDEX handler can unbind before this batch's drain. Keep
				# the batch intact, but stop iteration when its generation dies.
				return _BindingEvents(events, lambda: self._bindingIsActive(binding))

			batchHandler(loadEvents)

		return receive

	def close(self) -> None:
		with self._lock:
			if self._closed:
				return
			self._closed = True
			self._handler = None
			self._batchHandler = None
			registrations, self._registrations = self._registrations, []
			sources, self._sources = self._sources, {}
		firstError = None
		for event, callback in registrations:
			try:
				event.unregister(callback)
			except Exception as error:  # noqa: BLE001 - collected; the first is raised after every step ran
				if firstError is None:
					firstError = error
		for binding in sources.values():
			if not rule_for(binding.completion).correlated:
				continue
			try:
				self._indexLedger.unbind(binding.sourceId)
			except Exception as error:  # noqa: BLE001 - collected; the first is raised after every step ran
				if firstError is None:
					firstError = error
		sources.clear()
		if firstError is not None:
			raise firstError

	def _onIndex(self, synth, index: int) -> None:
		self._receive(synth, EventKind.INDEX, index)

	def _onDone(self, synth) -> None:
		self._receive(synth, EventKind.DONE)

	def _receive(self, source, kind: EventKind, index: int | None = None) -> None:
		with self._lock:
			if self._closed or source is self._owner:
				return
			binding = self._sources.get(id(source))
			if binding is None or binding.source is not source:
				return
			handler = self._handler
			batchHandler = self._batchHandler
		if not rule_for(binding.completion).correlated:
			if handler is not None:
				handler(PlaybackEvent(kind, binding.sourceId, index))
		elif kind is EventKind.INDEX and batchHandler is not None:
			# The consumer serializes both decode and delivery of this batch.
			def loadEvents() -> tuple[PlaybackEvent, ...]:
				with self._lock:
					if self._closed or self._sources.get(id(source)) is not binding:
						return ()
				# Unbind/rebind can occur after the bridge check; validate the
				# ledger generation atomically with decode to reject that race.
				return self._indexLedger.receiveIndex(
					binding.sourceId,
					index,
					bindingToken=binding.ledgerToken,
				)

			batchHandler(loadEvents)

	def _canNotify(self) -> bool:
		if self._get_synth() is not self._owner:
			return False
		with self._lock:
			return not self._closed and self._handler is not None

	def index_reached(self, index: int) -> None:
		if self._canNotify():
			self._indexEvent.notify(synth=self._owner, index=index)

	def done_speaking(self) -> None:
		if self._canNotify():
			self._doneEvent.notify(synth=self._owner)
