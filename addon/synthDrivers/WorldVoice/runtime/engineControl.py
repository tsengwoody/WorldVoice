"""Parts an engine wrapper uses around its own native queue and worker.

Each part is guarded by the engine's own condition (its queue lock), which
comes after host admission and before the host condition in the lock order.
"""

from collections.abc import Callable, Hashable, Iterator
from contextlib import contextmanager
from threading import Condition

from .segmentHost import NativeRecord, SegmentHost


class StopGate:
	"""Stops in flight on an engine's queue; its worker takes no request until none remain."""

	def __init__(self, condition: Condition):
		self._condition = condition
		self._stops = 0

	def enter(self) -> None:
		"""Start a stop; call while holding the condition."""
		self._stops += 1

	def leave(self) -> None:
		"""End a stop and wake waiters; call while holding the condition."""
		self._stops -= 1
		self._condition.notify_all()

	@contextmanager
	def hold(self) -> Iterator[None]:
		with self._condition:
			self.enter()
		try:
			yield
		finally:
			with self._condition:
				self.leave()

	@property
	def clear(self) -> bool:
		"""Whether no stop is in flight; read it while holding the condition."""
		return self._stops == 0


class QueuedRecords:
	"""Records submitted to an engine queue and not yet taken by its worker.

	The caller guards it with the lock that also guards the engine's queue.
	"""

	def __init__(self):
		self._records: dict[Hashable, NativeRecord] = {}

	def add(self, key: Hashable, record: NativeRecord) -> None:
		self._records[key] = record

	def pop(self, key: Hashable) -> NativeRecord | None:
		return self._records.pop(key, None)

	def take_all(self) -> list[NativeRecord]:
		records = list(self._records.values())
		self._records.clear()
		return records

	def __len__(self) -> int:
		return len(self._records)


class ControlFaultPolicy:
	"""Latch the first control error, drop queued work and wake the engine's worker."""

	def __init__(
		self,
		host: SegmentHost,
		condition: Condition,
		drop: Callable[[], list[NativeRecord]],
	):
		self._host = host
		self._condition = condition
		self._drop = drop

	def fail(self, error: Exception) -> bool:
		"""Return False when a control error was already latched."""
		host = self._host
		with self._condition:
			if host.control_error is not None:
				return False
			host.latch_control_error(error)
			dropped = self._drop()
			self._condition.notify_all()
		# Queued work never reaches the worker; it fails with the latched error.
		# abandon() waits for consumers, which may need the engine lock.
		for record in dropped:
			host.abandon(record)
		return True
