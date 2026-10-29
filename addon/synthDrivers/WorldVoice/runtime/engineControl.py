"""Parts an engine wrapper uses around its own native queue and worker.

Each part is guarded by the engine's own condition (its queue lock), which
comes after host admission and before the host condition in the lock order.

The latch rule, for every engine:

- Control failures latch. A failure of an operation whose job is to put the
  player or engine back into a known state (stop, purge, pause/resume, the
  inner engine's cancel, releasing a native resource, or a native call whose
  callbacks cannot be proven finished) latches the engine's control error:
  nothing else can reset that state, so no later speech may run on it until
  the core is reloaded.
- Progress failures fail only their record. A failure while a record makes or
  plays its audio (opening or replacing the player, feeding, idle()/sync(),
  native synthesis, callback processing) is recorded on that record. The stop
  on that record's failure path resets the player before any successor uses
  it; only a failed stop latches, by the first rule.
- Exception: SAPI5 latches a failed ordinary request, because its single COM
  stream cannot attribute a callback after the purge to the next request.

A wrapper with its own native queue latches only through its ControlFaultPolicy.
eSpeak, whose queue is NVDA's, latches through LeasedPlayer's default stop hook.
"""

from collections.abc import Callable, Hashable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Condition, local

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


@dataclass(frozen=True)
class ControlFault:
	"""A latched control error and the queued records its policy dropped."""

	error: Exception
	dropped: tuple[NativeRecord, ...]


class ControlFaultPolicy:
	"""Latch the first control error, drop queued work and wake the engine's worker.

	capture() latches and drops under the engine condition; deliver() abandons the
	dropped records and runs ``after`` with no lock held. fail() does both, unless
	this thread is inside deferred(): then delivery waits until that block ends, so
	a wrapper can capture under a lock it must not deliver under.
	"""

	def __init__(
		self,
		host: SegmentHost,
		condition: Condition,
		drop: Callable[[], Iterable[NativeRecord]] | None = None,
		*,
		after: Callable[[ControlFault], None] | None = None,
	):
		self._host = host
		self._condition = condition
		self._drop = drop
		self._after = after
		self._local = local()

	def capture(self, error: Exception) -> ControlFault | None:
		"""Latch ``error`` and drop queued work; None when a control error was already latched."""
		host = self._host
		with self._condition:
			if host.control_error is not None:
				return None
			host.latch_control_error(error)
			dropped = tuple(self._drop()) if self._drop is not None else ()
			self._condition.notify_all()
		return ControlFault(error, dropped)

	def deliver(self, fault: ControlFault | None) -> None:
		"""Abandon the dropped records, then run ``after``; call with no engine lock held."""
		if fault is None:
			return
		try:
			# Queued work never reaches the worker; it fails with the latched error.
			# abandon() waits for consumers, which may need the engine lock.
			for record in fault.dropped:
				self._host.abandon(record)
		finally:
			if self._after is not None:
				self._after(fault)

	def fail(self, error: Exception) -> bool:
		"""Return False when a control error was already latched."""
		fault = self.capture(error)
		local = self._local
		if getattr(local, "depth", 0):
			if fault is not None:
				local.fault = fault
		else:
			self.deliver(fault)
		return fault is not None

	@contextmanager
	def deferred(self) -> Iterator[None]:
		"""Deliver a fault this thread captures inside the block when the outermost block ends."""
		local = self._local
		depth = getattr(local, "depth", 0)
		if depth == 0:
			local.fault = None
		local.depth = depth + 1
		try:
			yield
		finally:
			local.depth = depth
			if depth == 0:
				fault, local.fault = local.fault, None
				self.deliver(fault)
