"""Shared segment flow for engine wrappers; engines supply only native specifics.

A SegmentHost owns one SegmentLifecycle and implements its hooks. It accepts
contextual segments, rejects them after termination or a control fault, runs
each one on its own thread, records native work for both contextual and
ordinary speech, admits callback/player consumers, latches control errors and
retires work in the engine's FIFO order. An engine provides a NativeStrategy
(how to queue, stop and drain its native work) and marks its own completion
barriers on each record.

Lock order: host admission -> host condition -> lifecycle condition. The host
never calls the strategy, a sink or a player while holding its own condition.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
import logging
from threading import Condition, Event, RLock, Thread, local
from typing import Protocol

from .models import PlaybackContext, PlaybackEvent, SegmentEventSink, SpeechCommands
from .playbackWork import PlaybackWork
from .segmentLifecycle import ProducerLease, SegmentLifecycle, SegmentOperation
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


class NativeStrategy(Protocol):
	"""What an engine supplies; everything else is the host's."""

	barriers: frozenset[str]

	def submit(self, host: "SegmentHost", record: NativeRecord, commands: SpeechCommands) -> None:
		"""Queue native work for ``record``; arrange for ``host.retire(record)`` when it ends."""

	def stop_native(self, host: "SegmentHost", record: NativeRecord) -> None:
		"""Stop the native work that is currently running ``record``."""

	def stop_player(self, host: "SegmentHost") -> None:
		"""Discard queued audio; used after cancellation or failure."""


class SegmentHost:
	def __init__(self, engine: str, strategy: NativeStrategy):
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

			def deliver(event):
				self._deliver(operation, on_event, event)

			operation = self._lifecycle.accept(context, token, deliver)
			with self._condition:
				self._accepted[operation] = False
		Thread(
			target=self._run,
			args=(operation, tuple(commands), deliver),
			name=f"WorldVoice {self.engine} lifecycle",
			daemon=True,
		).start()

	def enqueue(self, commands: SpeechCommands, work: PlaybackWork | None = None, operation=None) -> None:
		"""Queue native work; ordinary speech passes neither work nor operation."""
		record = self.new_record(work, operation)
		with self._admission:
			if self._terminated:
				if work is not None:
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
				self._lifecycle.fail(operation, control_error)
				record.retired.set()
				return
			if operation is not None:
				record.producer = self._lifecycle.admit_producer(operation)
			self._strategy.submit(self, record, commands)

	def cancel(self) -> None:
		with self._admission:
			self._invalidate()

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
		work: PlaybackWork | None,
		operation: SegmentOperation | None = None,
	) -> NativeRecord:
		segment = operation is not None
		return NativeRecord(
			work,
			barriers=dict.fromkeys(self._strategy.barriers, False),
			operation=operation,
			retired=Event() if segment else None,
			handoff=Event() if segment else None,
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
	def consumer(self, record: NativeRecord | None = None) -> Iterator[NativeRecord | None]:
		"""Admit a callback or player call for the current record (None if not admitted)."""
		with self._condition:
			record = record or self._current
			if record is None or record is not self._current or not record.is_valid():
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
		# first control error until the driver reloads, and fail pending work.
		with self._condition:
			if self._control_error is None:
				self._control_error = error
			for record in self._pending:
				if record.error is None:
					record.error = self._control_error

	def forget(self, record: NativeRecord) -> None:
		with self._condition:
			if record in self._pending:
				self._pending.remove(record)

	def retire(self, record: NativeRecord) -> OrdinaryOutcome | None:
		"""Retire ``record`` in FIFO order; return the outcome for ordinary speech."""
		with self._condition:
			valid = record.is_valid()
			record.closed = True
			self._condition.wait_for(lambda: record.consumers == 0)
			valid = valid and not record.cancelled and (record.work is None or record.work.is_valid())
			if not valid and record in self._pending:
				self._pending.remove(record)
			if self._current is record:
				self._current = None
		if record.operation is not None:
			if record.producer is not None:
				self._lifecycle.retire_producer(record.producer)
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
		self.enqueue(commands, operation.work, operation)

	def request_stop(self, operation: SegmentOperation) -> None:
		with self._condition:
			record = self._records.get(operation)
			if record is not None:
				record.cancelled = True
				active = record is self._current
			else:
				active = False
		if active:
			self._strategy.stop_native(self, record)

	def wait_native_boundary(self, operation: SegmentOperation) -> None:
		with self._condition:
			record = self._records[operation]
		record.retired.wait()
		if record.error is not None:
			self._lifecycle.fail(operation, record.error)

	def wait_native_retired(self, operation: SegmentOperation) -> None:
		# retire() already waited for every admitted consumer.
		return

	def wait_playback_drained(self, operation: SegmentOperation) -> None:
		with self._condition:
			record = self._records.get(operation)
		if record is None:
			return
		if not operation.work.is_valid() or record.error is not None:
			self._strategy.stop_player(self)
			return
		if not record.barriers_met():
			self._lifecycle.fail(operation, self._missing_barriers_error(record))
			self._strategy.stop_player(self)

	# Internals ------------------------------------------------------------

	def _missing_barriers_error(self, record: NativeRecord) -> RuntimeError:
		return RuntimeError(
			f"{self.engine} synthesis retired without its {', '.join(record.missing_barriers())} barriers",
		)

	def _run(self, operation: SegmentOperation, commands: SpeechCommands, deliver: Callable) -> None:
		try:
			self._lifecycle.run(operation, commands)
		except Exception as error:
			self._lifecycle.reject_new(
				operation.work.context,
				operation.work.token,
				deliver,
				self.control_error or error.__cause__ or error,
			)
		finally:
			with self._condition:
				record = self._records.pop(operation, None)
				if self._accepted.get(operation) or operation.work.token.is_cancelled():
					self._accepted.pop(operation, None)
			if record is not None:
				record.handoff.set()

	def _deliver(self, operation: SegmentOperation, sink: SegmentEventSink, event: PlaybackEvent) -> None:
		try:
			with self._condition:
				silenced = self._accepted.get(operation, False)
			if not operation.work.token.is_cancelled() and not silenced and not self._terminated:
				sink(event)
		finally:
			# Work stays cancellable until publication starts on the delivery thread.
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
				if record.work is not None and record.operation is None:
					record.work.cancel()


class LeasedPlayer:
	"""Admit every feed/idle as a consumer of the current record."""

	def __init__(self, host: SegmentHost, player, *, idle_barrier: str | None = "idle"):
		self._host = host
		self._player = player
		self._idle_barrier = idle_barrier

	def __getattr__(self, name):
		return getattr(self._player, name)

	def feed(self, data, size=None, onDone=None):
		host = self._host
		with host.consumer() as record:
			if record is None:
				return None
			callback = None
			if onDone is not None:

				def callback():
					with host.consumer(record) as admitted:
						if admitted is None:
							return
						with host.bound_callback(record):
							onDone()

			try:
				return self._player.feed(data, size, callback)
			except Exception as error:
				host.record_error(record, error)
				raise
			finally:
				# A feed that was already admitted may queue audio after cancel's
				# stop. Stop it again before the FIFO barrier permits a successor.
				if not record.is_valid():
					self.stop()

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
			self._host.latch_control_error(error)
			raise
