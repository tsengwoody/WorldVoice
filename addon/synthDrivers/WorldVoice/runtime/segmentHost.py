"""Shared segment flow for engine wrappers; engines supply only native specifics.

A SegmentHost owns one SegmentLifecycle and implements its hooks. It accepts
contextual segments, rejects them after termination or a control fault, runs
each one on its own thread, records native work for both contextual and
ordinary speech, admits callback/player consumers, latches control errors and
retires work in the engine's FIFO order. An engine provides a NativeStrategy
(how to queue, stop and drain its native work) and marks its own completion
barriers on each record.

Lock order: host admission -> engine lock -> host condition -> lifecycle
condition. The host never calls the strategy, a sink or a player while holding
its own condition.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Condition, Event, RLock, Thread, local

from ._segmentLifecycle import ProducerLease, SegmentLifecycle, SegmentOperation
from .models import EventKind, PlaybackContext, PlaybackEvent, SegmentEventSink, SpeechCommands
from .playbackWork import PlaybackWork
from .session import CancellationView

log = logging.getLogger(__name__)


@dataclass(eq=False)
class NativeRecord:
	"""One unit of native work, for a contextual segment or ordinary speech."""

	work: PlaybackWork | None
	barriers: dict[str, bool] = field(default_factory=dict)
	operation: SegmentOperation | None = None
	producer: ProducerLease | None = None
	retired: Event | None = None
	handoff: Event | None = None
	cancelled: bool = False
	closed: bool = False
	error: Exception | None = None
	consumers: int = 0
	# Engine-specific data (request, stream, resource snapshots ...).
	native: object | None = None
	# False once close() stops new consumers; the work itself stays valid.
	admitting: bool = True
	# Set by abandon(): the record retired without native work, so a stop
	# has nothing to reach and engine data may never have been bound.
	abandoned: bool = False

	def barriers_met(self) -> bool:
		return all(self.barriers.values())

	def missing_barriers(self) -> tuple[str, ...]:
		return tuple(name for name, reached in self.barriers.items() if not reached)

	def is_valid(self) -> bool:
		return not self.cancelled and not self.closed and (self.work is None or self.work.is_valid())


@dataclass(frozen=True)
class OrdinaryOutcome:
	"""How an ordinary (non-contextual) record retired."""

	cancelled: bool
	error: Exception | None


class NativeStrategy(ABC):
	"""What an engine supplies; everything else is the host's.

	The three optional hooks have defaults, so an engine overrides only what it needs.
	"""

	barriers: frozenset[str] = frozenset()

	@abstractmethod
	def submit(self, host: "SegmentHost", record: NativeRecord, commands: SpeechCommands) -> None:
		"""Queue native work for ``record``; arrange for ``host.retire(record)`` when it ends."""

	@abstractmethod
	def stop_native(self, host: "SegmentHost", record: NativeRecord) -> None:
		"""Stop the native work that is currently running ``record``."""

	@abstractmethod
	def stop_player(self, host: "SegmentHost") -> None:
		"""Discard queued audio; used after cancellation or failure."""

	def prepare(
		self,
		host: "SegmentHost",
		commands: SpeechCommands,
		operation: SegmentOperation | None,
	) -> SpeechCommands:
		"""Return what submit() receives.

		Called by enqueue() outside host admission before the record exists. A
		raised error fails the segment (or is raised to an ordinary caller).
		"""
		return commands

	def admission_error(self, host: "SegmentHost") -> Exception | None:
		"""Called under host admission before a segment is accepted.

		A returned error rejects the segment (e.g. an audio route that cannot drain).
		"""
		return None

	def drain(self, host: "SegmentHost", record: NativeRecord) -> None:
		"""Wait for this record's playback to finish on the lifecycle thread.

		Reach any barriers it proves. Record failures with host.record_error()
		instead of raising; it may be called more than once for the same record.
		The host checks the barriers afterwards.
		"""


class SegmentHost:
	def __init__(self, engine: str, strategy: NativeStrategy):
		if not strategy.barriers:
			# With no barriers a segment would drain before its audio has played.
			raise ValueError(f"{engine} strategy declares no playback barriers")
		self.engine = engine
		self._strategy = strategy
		self._admission = RLock()
		self._condition = Condition(RLock())
		self._callback_local = local()
		self._terminated = False
		self._control_error: Exception | None = None
		self._current: NativeRecord | None = None
		self._pending: list[NativeRecord] = []
		self._records: dict[SegmentOperation, NativeRecord] = {}
		# Accepted operations -> whether the host cancelled them (keeps them silent).
		self._accepted: dict[SegmentOperation, bool] = {}
		# Operations whose sink is running on the delivery thread.
		self._delivering: set[SegmentOperation] = set()
		self._lifecycle = SegmentLifecycle(self)

	# Entry points ---------------------------------------------------------

	@contextmanager
	def admission(self) -> Iterator[None]:
		"""Hold admission so no segment is accepted until the block ends."""
		with self._admission:
			yield

	@property
	def terminated(self) -> bool:
		return self._terminated

	@property
	def control_error(self) -> Exception | None:
		with self._condition:
			return self._control_error

	def on_delivery_thread(self) -> bool:
		return self._lifecycle.on_delivery_thread()

	def wait_idle(self) -> None:
		"""Wait until no segment owns the native resource (e.g. before closing it)."""
		self._lifecycle.wait_idle()

	def speak_segment(
		self,
		commands: SpeechCommands,
		token: CancellationView,
		*,
		context: PlaybackContext,
		on_event: SegmentEventSink,
	) -> None:
		with self._admission:
			if self._terminated:
				self._lifecycle.reject_new(
					context,
					token,
					on_event,
					RuntimeError(f"{self.engine} driver has terminated"),
				)
				return
			control_error = self.control_error
			if control_error is not None:
				self._lifecycle.reject_new(context, token, on_event, control_error)
				return
			engine_error = self._strategy.admission_error(self)
			if engine_error is not None:
				self._lifecycle.reject_new(context, token, on_event, engine_error)
				return

			def deliver(event):
				self._deliver(operation, on_event, event)

			operation = self._lifecycle.accept(context, token, deliver, on_retired=self._forget_operation)
			with self._condition:
				self._accepted[operation] = False
		Thread(
			target=self._run,
			args=(operation, tuple(commands), deliver),
			name=f"WorldVoice {self.engine} lifecycle",
			daemon=True,
		).start()

	def enqueue(
		self,
		commands: SpeechCommands,
		operation: SegmentOperation | None = None,
		*,
		barriers: frozenset[str] | set[str] | None = None,
		native: object | None = None,
	) -> None:
		"""Queue native work; ordinary speech passes no operation."""
		work = operation.work if operation is not None else None
		# Engine preparation (e.g. SSML conversion) runs outside admission so
		# cancel() and terminate() never wait for it.
		try:
			commands = self._strategy.prepare(self, commands, operation)
		except Exception as error:
			if operation is None:
				raise
			self._lifecycle_of(operation).fail(operation, error)
			return
		record = self.new_record(operation, barriers=barriers, native=native)
		with self._admission:
			if self._terminated:
				if work is None:
					raise RuntimeError(f"{self.engine} driver has terminated")
				work.cancel()
				return
			with self._condition:
				control_error = self._control_error
				if control_error is not None and operation is None:
					raise control_error
				self._pending.append(record)
				if operation is not None:
					self._records[operation] = record
			if control_error is not None:
				self._lifecycle_of(operation).fail(operation, control_error)
				self.abandon(record)
				return
			if operation is not None:
				# admit_producer refuses work that is already cancelled.
				record.producer = self._lifecycle_of(operation).admit_producer(operation)
				if record.producer is None:
					self.abandon(record)
					return
			try:
				self._strategy.submit(self, record, commands)
			except Exception as error:
				if operation is None:
					self.forget(record)
					raise
				# The segment fails through its own record; the lifecycle stays usable.
				self.record_error(record, error)
				self.abandon(record)

	def cancel(self) -> None:
		with self._admission:
			self._invalidate()

	def reset(self) -> None:
		"""Recover after a voice/resource reload: clear faults and start a fresh lifecycle.

		Call under admission() after the engine has joined its old worker.
		"""
		with self._admission:
			if self._terminated:
				return
			self._invalidate()
			old = self._lifecycle
			with self._condition:
				self._control_error = None
				self._current = None
				self._pending.clear()
				self._records.clear()
				self._accepted.clear()
			self._lifecycle = SegmentLifecycle(self)
			old.terminate()
		old.join_delivery(1)

	def terminate(self) -> bool:
		"""Stop all work; return False when already terminated."""
		with self._admission:
			if self._terminated:
				return False
			self._terminated = True
			self._invalidate()
			self._lifecycle.terminate()
		self._lifecycle.join_delivery(1)
		return True

	# Records and consumers ------------------------------------------------

	def new_record(
		self,
		operation: SegmentOperation | None = None,
		*,
		barriers: frozenset[str] | set[str] | None = None,
		native: object | None = None,
	) -> NativeRecord:
		segment = operation is not None
		return NativeRecord(
			operation.work if segment else None,
			barriers=dict.fromkeys(self._strategy.barriers if barriers is None else barriers, False),
			operation=operation,
			retired=Event() if segment else None,
			handoff=Event() if segment else None,
			native=native,
		)

	def begin(self, record: NativeRecord) -> None:
		with self._condition:
			self._current = record

	def current(self) -> NativeRecord | None:
		with self._condition:
			return self._current

	def callback_record(self) -> NativeRecord | None:
		return getattr(self._callback_local, "record", None)

	@contextmanager
	def bound_callback(self, record: NativeRecord) -> Iterator[None]:
		"""Bind ``record`` for a delayed player callback on this thread."""
		previous = self.callback_record()
		self._callback_local.record = record
		try:
			yield
		finally:
			self._callback_local.record = previous

	@contextmanager
	def consumer(
		self,
		record: NativeRecord | None = None,
		*,
		audio: bool = False,
	) -> Iterator[NativeRecord | None]:
		"""Admit a callback or player call for the current record (None if not admitted).

		``audio=True`` admits a delayed player callback (e.g. an index onDone)
		after close() until retire() seals the record.
		"""
		with self._condition:
			record = record or self._current
			if (
				record is None
				or record is not self._current
				or not record.is_valid()
				# After close(), only a callback already bound to this record may nest.
				or (not record.admitting and not audio and self.callback_record() is not record)
			):
				admitted = None
			else:
				record.consumers += 1
				admitted = record
		try:
			yield admitted
		finally:
			if admitted is not None:
				with self._condition:
					admitted.consumers -= 1
					self._condition.notify_all()

	def close(self, record: NativeRecord) -> None:
		"""Stop admitting new consumers for ``record``; the work stays valid."""
		with self._condition:
			record.admitting = False

	def wait_consumers(self, record: NativeRecord) -> None:
		with self._condition:
			self._condition.wait_for(lambda: record.consumers == 0)

	def abandon(self, record: NativeRecord) -> None:
		"""Retire a record whose native work will never run (e.g. a cleared queue).

		Unlike retire(), it does not wait for the lifecycle's handoff.
		"""
		with self._condition:
			record.closed = True
			record.admitting = False
			record.abandoned = True
			self._condition.wait_for(lambda: record.consumers == 0)
			if record in self._pending:
				self._pending.remove(record)
			if self._current is record:
				self._current = None
			producer, record.producer = record.producer, None
			# wait_settled() waits for the current record to change.
			self._condition.notify_all()
		if producer is not None:
			self._lifecycle_of(record.operation).retire_producer(producer)
		if record.retired is not None:
			record.retired.set()

	def reach(self, record: NativeRecord, barrier: str) -> None:
		with self._condition:
			if barrier not in record.barriers:
				raise KeyError(barrier)
			record.barriers[barrier] = True

	def record_error(self, record: NativeRecord | None, error: Exception) -> None:
		with self._condition:
			if record is not None and record.error is None:
				record.error = error

	def latch_control_error(self, error: Exception) -> None:
		# A stop failure does not prove queued callbacks were discarded. Keep the
		# first control error until the driver reloads, and fail pending and
		# accepted work: a stop failure must never be reported as success.
		with self._condition:
			if self._control_error is None:
				self._control_error = error
			for record in self._pending:
				if record.error is None:
					record.error = self._control_error
			latched = self._control_error
			accepted = tuple(self._accepted)
		for operation in accepted:
			self._lifecycle_of(operation).fail(operation, latched)

	def wait_settled(self, record: NativeRecord | None) -> None:
		"""After cancel: wait until ``record`` leaves the worker and running sinks return.

		A callback bound to ``record`` does not wait for that record; a bound
		callback or the delivery thread does not wait for sinks, which may in
		turn be waiting for it.
		"""
		bound = self.callback_record()
		in_delivery = self.on_delivery_thread()
		with self._condition:
			if record is not None and bound is not record:
				self._condition.wait_for(lambda: self._current is not record)
			if bound is None and not in_delivery:
				running = set(self._delivering)
				self._condition.wait_for(lambda: not (running & self._delivering))

	def forget(self, record: NativeRecord) -> None:
		with self._condition:
			if record in self._pending:
				self._pending.remove(record)

	def retire(
		self,
		record: NativeRecord,
		*,
		finish: Callable[[], None] | None = None,
	) -> OrdinaryOutcome | None:
		"""Retire ``record`` in FIFO order; return the outcome for ordinary speech.

		Retirement seals the record: no consumer is admitted afterwards. ``finish``
		runs on the calling (worker) thread once every consumer has left, before
		the record stops being current; an exception it raises is recorded on
		the record.
		"""
		with self._condition:
			valid = record.is_valid()
			record.closed = True
			self._condition.wait_for(lambda: record.consumers == 0)
		if finish is not None:
			try:
				finish()
			except Exception as error:  # noqa: BLE001 - recorded on the record; the segment fails
				self.record_error(record, error)
		with self._condition:
			valid = valid and not record.cancelled and (record.work is None or record.work.is_valid())
			if not valid and record in self._pending:
				self._pending.remove(record)
			if self._current is record:
				self._current = None
			self._condition.notify_all()
		if record.operation is not None:
			producer, record.producer = record.producer, None
			if producer is not None:
				self._lifecycle_of(record.operation).retire_producer(producer)
			record.retired.set()
			# The FIFO worker keeps player ownership until the coordinator has
			# finished the final stop or drain check for this operation.
			record.handoff.wait()
			return None
		if not valid:
			# Token-only cancellation can skip the terminal idle; discard queued audio.
			try:
				self._strategy.stop_player(self)
			except Exception:
				log.error("Error stopping cancelled %s playback", self.engine, exc_info=True)
			return OrdinaryOutcome(cancelled=True, error=None)
		error = record.error
		if error is None and not record.barriers_met():
			error = self._missing_barriers_error(record)
		if error is not None and self.control_error is None:
			try:
				self._strategy.stop_player(self)
			except Exception as stop_error:
				log.error("Error stopping failed %s playback", self.engine, exc_info=True)
				self.record_error(record, stop_error)
		return OrdinaryOutcome(cancelled=False, error=error)

	# SegmentEngineHooks ---------------------------------------------------

	def submit_native(self, operation: SegmentOperation, commands: SpeechCommands) -> None:
		self.enqueue(commands, operation)

	def request_stop(self, operation: SegmentOperation) -> None:
		with self._condition:
			record = self._records.get(operation)
			if record is not None:
				record.cancelled = True
				# A retired record may still be draining until its handoff;
				# an abandoned one never ran native work.
				draining = not record.abandoned and record.retired.is_set() and not record.handoff.is_set()
				active = record is self._current or draining
			else:
				active = False
		if active:
			self._strategy.stop_native(self, record)

	def wait_native_boundary(self, operation: SegmentOperation) -> None:
		with self._condition:
			record = self._records.get(operation)
		if record is None:
			# Terminated before the record was registered; nothing to wait for.
			return
		record.retired.wait()
		if record.error is not None:
			self._lifecycle_of(operation).fail(operation, record.error)

	def wait_native_retired(self, operation: SegmentOperation) -> None:
		# retire() already waited for every admitted consumer.
		return

	def wait_playback_drained(self, operation: SegmentOperation) -> None:
		with self._condition:
			record = self._records.get(operation)
		if record is None:
			return
		lifecycle = self._lifecycle_of(operation)
		if not operation.work.is_valid() or record.error is not None:
			self._strategy.stop_player(self)
			return
		try:
			self._strategy.drain(self, record)
		except Exception as error:  # noqa: BLE001 - recorded on the record; the segment fails
			# A raising drain fails this segment, never the whole lifecycle.
			self.record_error(record, error)
			lifecycle.fail(operation, record.error)
			self._strategy.stop_player(self)
			return
		if record.error is not None:
			# The strategy already stopped or purged what it needed to.
			lifecycle.fail(operation, record.error)
			return
		if not record.barriers_met():
			lifecycle.fail(operation, self._missing_barriers_error(record))
			self._strategy.stop_player(self)

	# Internals ------------------------------------------------------------

	def _missing_barriers_error(self, record: NativeRecord) -> RuntimeError:
		return RuntimeError(
			f"{self.engine} synthesis retired without its {', '.join(record.missing_barriers())} barriers",
		)

	@staticmethod
	def _lifecycle_of(operation: SegmentOperation) -> SegmentLifecycle:
		# reset() replaces the lifecycle; an older operation keeps its own.
		return operation._lifecycle

	def _run(self, operation: SegmentOperation, commands: SpeechCommands, deliver: Callable) -> None:
		lifecycle = self._lifecycle_of(operation)
		try:
			lifecycle.run(operation, commands)
		except Exception as error:  # noqa: BLE001 - delivered as the segment's terminal failure
			lifecycle.reject_new(
				operation.work.context,
				operation.work.token,
				deliver,
				self.control_error or error.__cause__ or error,
			)
		finally:
			# The accepted entry (and its cancel flag) stays until the lifecycle
			# either delivers the operation (_deliver) or discards it
			# (_forget_operation): NVDA may still cancel before publication.
			with self._condition:
				record = self._records.pop(operation, None)
			if record is not None and lifecycle.fault is not None:
				# A hook fault skipped the playback drain; discard queued audio
				# before the worker hands the player to a successor.
				try:
					self._strategy.stop_player(self)
				except Exception:
					log.error("Error stopping %s playback after a fault", self.engine, exc_info=True)
			if record is not None:
				record.handoff.set()

	def _deliver(self, operation: SegmentOperation, sink: SegmentEventSink, event: PlaybackEvent) -> None:
		try:
			with self._condition:
				silenced = self._accepted.get(operation, False)
				control_error = self._control_error
				self._delivering.add(operation)
			if not operation.work.token.is_cancelled() and not silenced and not self._terminated:
				if control_error is not None and event.kind is EventKind.SEGMENT_DRAINED:
					event = PlaybackEvent(
						EventKind.SEGMENT_FAILED,
						event.source_id,
						segment_id=event.segment_id,
						error=control_error,
					)
				sink(event)
		finally:
			# Work stays cancellable until publication starts on the delivery thread.
			with self._condition:
				self._delivering.discard(operation)
				self._condition.notify_all()
				self._accepted.pop(operation, None)
				for record in self._pending:
					if record.operation is operation:
						self._pending.remove(record)
						break

	def _forget_operation(self, operation: SegmentOperation) -> None:
		"""Lifecycle discard callback: the operation will never be delivered."""
		with self._condition:
			self._accepted.pop(operation, None)
			for record in self._pending:
				if record.operation is operation:
					self._pending.remove(record)
					break

	def _invalidate(self) -> None:
		with self._condition:
			for operation in tuple(self._accepted):
				self._accepted[operation] = True
				self._lifecycle.cancel(operation)
			for record in self._pending:
				record.cancelled = True


class LeasedPlayer:
	"""Admit every feed/idle as a consumer of the current record.

	Engines adjust three hooks: how a feed's onDone callback is wrapped, how a
	feed error is recorded, and what a failed stop does.
	"""

	def __init__(self, host: SegmentHost, player, *, idle_barrier: str | None = "idle"):
		self._host = host
		self._player = player
		self._idle_barrier = idle_barrier

	def __getattr__(self, name):
		return getattr(self._player, name)

	def feed(self, data, size=None, onDone=None):
		with self._host.consumer() as record:
			if record is None:
				return None
			return self._feed_admitted(record, data, size, onDone)

	def _feed_admitted(self, record: NativeRecord, data, size, onDone):
		"""Feed while ``record`` is admitted; subclasses choose which record to admit."""
		callback = None if onDone is None else self._callback(record, onDone)
		try:
			if size is None:
				return self._player.feed(data, onDone=callback)
			return self._player.feed(data, size, onDone=callback)
		except Exception as error:
			self._record_error(record, error)
			raise
		finally:
			# A feed that was already admitted may queue audio after cancel's
			# stop. Stop it again before the FIFO barrier permits a successor.
			if not record.is_valid():
				self.stop()

	def _callback(self, record: NativeRecord, onDone: Callable[[], None]) -> Callable[[], None]:
		host = self._host

		def callback():
			with host.consumer(record) as admitted:
				if admitted is None:
					return
				with host.bound_callback(record):
					try:
						onDone()
					except Exception as error:
						host.record_error(record, error)
						raise

		return callback

	def _record_error(self, record: NativeRecord, error: Exception) -> None:
		self._host.record_error(record, error)

	def _stop_failed(self, error: Exception) -> None:
		self._host.latch_control_error(error)

	def idle(self):
		host = self._host
		with host.consumer() as record:
			if record is None:
				return None
			try:
				result = self._player.idle()
			except Exception as error:
				host.record_error(record, error)
				raise
			if self._idle_barrier is not None:
				host.reach(record, self._idle_barrier)
			return result

	def stop(self):
		try:
			return self._player.stop()
		except Exception as error:
			self._stop_failed(error)
			raise
