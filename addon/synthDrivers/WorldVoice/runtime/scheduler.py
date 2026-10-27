"""Request scheduling independent of engines and application notifications.

Lock order is delivery lock -> state condition. No state-locked path acquires
the delivery lock. Engine calls, output, and Future completion (which can run
user callbacks) always execute outside the state condition. Only the worker
finishes submitted tasks; engine callbacks record signals or delivery intents.
"""

import logging
import queue
import threading
from collections import deque
from collections.abc import Callable, Iterable
from concurrent.futures import Future, InvalidStateError
from dataclasses import dataclass, field
from enum import Enum, auto
from itertools import count
from typing import Protocol

from .completion import CompletionRule, Signal, rule_for
from .models import (
	CompletionContract,
	EventKind,
	PlaybackContext,
	PlaybackEvent,
	SpeechCommands,
)
from .session import PlaybackPort


class NotificationOutput(Protocol):
	def index_reached(self, index: int) -> None: ...

	def done_speaking(self) -> None: ...


log = logging.getLogger(__name__)


class CancellationToken:
	"""Cancellation flag that notifies waiters instead of being polled.

	Callbacks run once, in registration order, on the thread that first calls
	cancel(), outside the token lock. They must only notify (set an Event,
	notify a condition): the scheduler cancels while holding its state lock.
	"""

	def __init__(self, logger=None):
		self._logger = logger if logger is not None else log
		self._event = threading.Event()
		self._lock = threading.Lock()
		self._callbacks: dict[int, Callable[[], None]] = {}
		self._next_callback = count()

	def cancel(self):
		with self._lock:
			if self._event.is_set():
				return
			self._event.set()
			keys = list(self._callbacks)
		for key in keys:
			# Re-check under the lock: a callback removed meanwhile never runs.
			with self._lock:
				callback = self._callbacks.pop(key, None)
			if callback is not None:
				self._run_callback(callback)

	def is_cancelled(self):
		return self._event.is_set()

	def add_callback(self, callback: Callable[[], None]) -> Callable[[], None]:
		"""Call ``callback`` once on cancellation; return a function that removes it."""
		with self._lock:
			if not self._event.is_set():
				key = next(self._next_callback)
				self._callbacks[key] = callback

				def remove():
					with self._lock:
						self._callbacks.pop(key, None)

				return remove
		self._run_callback(callback)
		return lambda: None

	def _run_callback(self, callback):
		try:
			callback()
		except Exception:
			self._logger.error("cancellation callback failed", exc_info=True)

	def wait(self, timeout=None):
		return self._event.wait(timeout)


def _settle_future(future, *, result=None, error=None):
	"""Let public cancellation win even after the completion check.

	Call outside scheduler state locks: settlement can invoke user callbacks.
	Other invalid state transitions remain errors rather than being hidden.
	"""
	if future.done():
		return
	try:
		if error is not None:
			future.set_exception(error)
		else:
			future.set_result(result)
	except InvalidStateError:
		if not future.cancelled():
			raise


class SpeechFuture(Future):
	"""The Future a speech or break task settles when it finishes."""


class RequestState(Enum):
	BUILDING = "building"
	SUBMITTED = "submitted"
	COMPLETED = "completed"
	CANCELLED = "cancelled"
	FAILED = "failed"


class TaskPhase(Enum):
	STARTING = auto()
	AWAITING_COMPLETION = auto()
	FINISHING = auto()


class InvalidRequestState(RuntimeError):
	pass


@dataclass
class SpeechRequest:
	request_id: int
	epoch: int
	token: CancellationToken
	state: RequestState = RequestState.BUILDING
	tasks: list = field(default_factory=list)
	remaining: int = 0
	has_speech: bool = False
	done_sent: bool = False


_segment_ids = count(1)


@dataclass
class _Task:
	playback: PlaybackPort | None
	voice_key: str | None
	commands: SpeechCommands
	seconds: float | None
	future: SpeechFuture
	request: SpeechRequest
	source_id: object = None
	segment_id: int | None = None
	context: PlaybackContext | None = None
	completion: CompletionContract | None = None
	rule: CompletionRule | None = None
	end_seen: bool = False
	drain_seen: bool = False
	error: Exception | None = None


class TaskManager:
	def __init__(self, output: NotificationOutput, *, logger=None):
		self._output = output
		self._logger = logger if logger is not None else logging.getLogger(__name__)
		self._q = queue.Queue()
		self._state_cond = threading.Condition()
		self._delivery_lock = threading.RLock()
		self._pending_event_batches = deque()
		self._dispatching_events = False
		self._closed = False
		self._epoch = 0
		self._next_request_id = 1
		self._requests = {}
		self._stops_in_flight = 0
		self._current_task = None
		self._current_phase = None
		self._current_done_event = None
		self._current_indexes = set()
		self._thread = threading.Thread(target=self._worker, daemon=True)
		self._thread.start()

	def new_request(self) -> SpeechRequest:
		with self._state_cond:
			if self._closed:
				raise InvalidRequestState("Scheduler is shut down")
			request = SpeechRequest(self._next_request_id, self._epoch, CancellationToken(self._logger))
			self._next_request_id += 1
			self._requests[request.request_id] = request
			return request

	def _require_building_locked(self, request):
		if (
			self._closed
			or request.state is not RequestState.BUILDING
			or self._requests.get(request.request_id) is not request
		):
			raise InvalidRequestState("Request is not building")

	def append_speech(
		self,
		request,
		playback: PlaybackPort,
		voice_key: str,
		commands: SpeechCommands,
	) -> SpeechFuture:
		with self._state_cond:
			self._require_building_locked(request)
			future = SpeechFuture()
			request.tasks.append(
				_Task(
					playback,
					voice_key,
					commands,
					None,
					future,
					request,
					segment_id=next(_segment_ids),
				),
			)
			request.has_speech = True
			return future

	def append_break(self, request, seconds: float) -> SpeechFuture:
		with self._state_cond:
			self._require_building_locked(request)
			future = SpeechFuture()
			request.tasks.append(_Task(None, None, (), seconds, future, request))
			return future

	def submit_request(self, request) -> bool:
		with self._state_cond:
			if (
				request.state is not RequestState.BUILDING
				or self._requests.get(request.request_id) is not request
			):
				return False
			if self._closed or request.epoch != self._epoch or request.token.is_cancelled():
				futures = self._cancel_request_locked(request)
			else:
				request.state = RequestState.SUBMITTED
				request.remaining = len(request.tasks)
				if not request.remaining:
					request.state = RequestState.COMPLETED
					self._requests.pop(request.request_id)
				for task in request.tasks:
					self._q.put(task)
				return True
		for future in futures:
			future.cancel()
		return False

	def abort_request(self, request, error: Exception) -> None:
		with self._state_cond:
			if request.state in (RequestState.COMPLETED, RequestState.CANCELLED, RequestState.FAILED):
				return
			self._require_building_locked(request)
			request.state = RequestState.FAILED
			request.token.cancel()
			self._requests.pop(request.request_id)
			futures = [task.future for task in request.tasks]
		for future in futures:
			_settle_future(future, error=error)

	def _valid_locked(self, task):
		request = task.request
		return (
			not self._closed
			and request.state is RequestState.SUBMITTED
			and request.epoch == self._epoch
			and not request.token.is_cancelled()
			and not task.future.cancelled()
		)

	def _accepts_events_locked(self, task):
		return (
			task is not None
			and task.playback is not None
			and self._current_task is task
			and self._current_phase is TaskPhase.AWAITING_COMPLETION
			and self._valid_locked(task)
			and task.error is None
		)

	def _completion_ready_locked(self, task):
		return task.rule.is_complete(task.end_seen, task.drain_seen)

	def _indexes_finished_locked(self, task):
		return task.rule.indexes_finished(task.end_seen, task.drain_seen)

	def on_event(self, event: PlaybackEvent) -> None:
		self.on_events(lambda: (event,))

	def on_events(self, load_events: Callable[[], Iterable[PlaybackEvent]]) -> None:
		# Serialize decoding and output. RLock permits output callbacks to
		# reenter; queue those suppliers so they cannot overtake this batch.
		with self._delivery_lock:
			with self._state_cond:
				task = self._current_task
			self._pending_event_batches.append((task, load_events))
			if self._dispatching_events:
				return
			self._dispatching_events = True
			try:
				while self._pending_event_batches:
					task, supplier = self._pending_event_batches.popleft()
					self._process_event_batch(task, supplier)
			finally:
				self._dispatching_events = False
				self._pending_event_batches.clear()

	def _process_event_batch(self, task, load_events):
		# Called only by the outermost dispatcher with the delivery lock held.
		# Suppliers and output always run outside the state condition.
		try:
			events = load_events()
			for event in events:
				index = None
				with self._state_cond:
					if not self._accepts_events_locked(task) or event.source_id is not task.source_id:
						continue
					rule = task.rule
					if not rule.accepts_segment(task.segment_id, event.segment_id):
						continue
					if event.kind is EventKind.INDEX:
						if (
							self._indexes_finished_locked(task)
							or event.index is None
							or event.index in self._current_indexes
						):
							continue
						self._current_indexes.add(event.index)
						index = event.index
					else:
						signal = rule.signal_for(event.kind)
						if signal is Signal.END:
							task.end_seen = True
						elif signal is Signal.DRAIN:
							task.drain_seen = True
						elif signal is Signal.FAIL:
							task.error = event.error or RuntimeError("Speech segment failed")
				if index is not None:
					self._deliver_index(task, index)
		except Exception as error:
			with self._state_cond:
				if self._accepts_events_locked(task):
					task.error = error
			self._logger.error("Speech event delivery error", exc_info=True)
		finally:
			with self._state_cond:
				if (
					task is not None
					and self._current_task is task
					and self._current_phase is TaskPhase.AWAITING_COMPLETION
					and (task.error is not None or self._completion_ready_locked(task))
				):
					self._current_done_event.set()

	def _deliver_index(self, task, index):
		# Called with the delivery lock held; output can synchronously cancel.
		with self._state_cond:
			valid = self._accepts_events_locked(task) and not self._indexes_finished_locked(task)
		if valid:
			self._output.index_reached(index)

	def _deliver_done(self, request):
		with self._delivery_lock:
			with self._state_cond:
				# Execution failure cancels the token to skip remaining tasks,
				# but still releases the application's speaking wait once.
				valid = (
					not self._closed
					and request.epoch == self._epoch
					and request.state in (RequestState.COMPLETED, RequestState.FAILED)
				)
			if valid:
				self._output.done_speaking()

	def _cancel_request_locked(self, request):
		if request.state not in (RequestState.BUILDING, RequestState.SUBMITTED):
			return []
		building = request.state is RequestState.BUILDING
		request.state = RequestState.CANCELLED
		request.token.cancel()
		if building:
			self._requests.pop(request.request_id, None)
			return [task.future for task in request.tasks]
		return []

	def _wake_current_locked(self):
		if self._current_done_event is not None:
			self._current_done_event.set()
		self._state_cond.notify_all()

	def _ordered_playbacks_locked(self, candidates):
		current = self._current_task
		if current is not None and current.playback is not None:
			candidates = [(current.playback, current.source_id)] + candidates
		seen, ordered = set(), []
		for playback, source in candidates:
			if id(source) not in seen:
				seen.add(id(source))
				ordered.append(playback)
		return ordered

	def _stop_playback(self, playback):
		try:
			playback.cancel()
		except Exception:
			self._logger.debug("Failed to stop playback", exc_info=True)

	def _stop_all(self, playbacks):
		try:
			for playback in playbacks:
				self._stop_playback(playback)
		finally:
			with self._state_cond:
				self._stops_in_flight -= 1
				self._state_cond.notify_all()

	def cancel(self, playbacks: Iterable[PlaybackPort] = ()) -> None:
		# Resolve port properties before locking: ports can contain engine code.
		candidates = [(playback, playback.source_id) for playback in playbacks]
		futures = []
		with self._delivery_lock, self._state_cond:
			self._epoch += 1
			for request in tuple(self._requests.values()):
				futures.extend(self._cancel_request_locked(request))
			self._wake_current_locked()
			ordered = self._ordered_playbacks_locked(candidates)
			self._stops_in_flight += 1
		self._stop_all(ordered)
		for future in futures:
			future.cancel()

	def cancel_current(self) -> None:
		with self._delivery_lock, self._state_cond:
			current = self._current_task
			if current is None:
				return
			self._cancel_request_locked(current.request)
			self._wake_current_locked()
			ordered = self._ordered_playbacks_locked([])
			self._stops_in_flight += 1
		self._stop_all(ordered)

	def pause_current(self, switch: bool) -> None:
		with self._state_cond:
			current = self._current_task
			playback = (
				current.playback
				if current
				and self._valid_locked(current)
				and self._current_phase in (TaskPhase.STARTING, TaskPhase.AWAITING_COMPLETION)
				else None
			)
		if playback is not None:
			playback.pause(switch)

	def shutdown(self, playbacks: Iterable[PlaybackPort] = ()) -> None:
		# Close admission before resolving ports or calling native cancellation;
		# either can block or reenter the scheduler.
		with self._state_cond:
			first = not self._closed
			self._closed = True
		if first:
			self.cancel(playbacks)
			self._q.put(None)
		if threading.current_thread() is not self._thread:
			self._thread.join()

	def _worker(self):
		while True:
			task = self._q.get()
			try:
				if task is None:
					return
				self._run_one(task)
			finally:
				self._q.task_done()

	def _run_one(self, task):
		result, error, failed = None, None, False
		try:
			if self._acquire(task):
				result = self._execute(task)
		except Exception as caught:
			error = caught
			with self._state_cond:
				if self._valid_locked(task):
					task.request.state = RequestState.FAILED
					task.request.token.cancel()
					failed = True
			self._logger.error("Speech scheduler task error", exc_info=True)
		finally:
			self._settle(task, result, error, failed)

	def _acquire(self, task):
		"""Wait out in-flight stops, then make a still-valid task current."""
		source = task.playback.source_id if task.playback is not None else None
		with self._state_cond:
			while self._stops_in_flight:
				self._state_cond.wait()
			if not self._valid_locked(task):
				return False
			task.source_id = source
			if task.playback is not None:
				task.context = PlaybackContext(source, task.segment_id)
			self._current_task = task
			self._current_phase = TaskPhase.STARTING
			self._current_indexes = set()
			self._current_done_event = threading.Event()
		return True

	def _execute(self, task):
		"""Run the current task; True on completion, None when it stopped early.

		Validity is checked again after each engine call, because activate and
		speak run outside the state condition and cancellation can win at any
		point. The final decision waits for the whole event batch to finish.
		"""
		if task.playback is None:
			task.request.token.wait(task.seconds)
			return None
		task.completion = task.playback.completion
		task.rule = rule_for(task.completion)
		task.playback.activate(task.voice_key)
		with self._state_cond:
			if not self._valid_locked(task):
				return None
			# Register before entry because speak can synchronously report completion.
			self._current_phase = TaskPhase.AWAITING_COMPLETION
			done = self._current_done_event
		# Future.cancel is public too. Wake this task's event even when
		# cancellation races the validity check or an active done wait.
		# Registration is outside state: an already-settled Future invokes
		# its callback immediately. The callback never finishes the task.
		task.future.add_done_callback(lambda future: done.set() if future.cancelled() else None)
		task.playback.speak(task.commands, task.request.token, context=task.context)
		if task.request.token.is_cancelled():
			# A non-token-aware synchronous speak may outlive the first stop.
			self._stop_playback(task.playback)
			return None
		with self._state_cond:
			if not self._valid_locked(task):
				return None
		done.wait()
		# A wake is only a signal. Wait for the complete delivery batch and
		# then validate after speak returned; errors/cancellation beat completion.
		with self._delivery_lock, self._state_cond:
			if not self._valid_locked(task):
				return None
			if task.error is not None:
				raise task.error
			if not self._completion_ready_locked(task):
				return None
			self._current_phase = TaskPhase.FINISHING
			return True

	def _settle(self, task, result, error, failed):
		"""Release the task's resources, then settle its Future and the request."""
		if failed and task.playback is not None:
			self._stop_playback(task.playback)
		if task.context is not None:
			try:
				task.playback.finish_segment(task.context)
			except Exception:
				self._logger.error("Failed to finish speech segment", exc_info=True)
		with self._state_cond:
			valid = self._valid_locked(task)
			if self._current_task is task:
				self._current_task = None
				self._current_phase = None
				self._current_done_event = None
				self._current_indexes = set()
			notify_done = self._finish_task_locked(task)
		# The state transition happens before user callbacks can re-enter.
		if error is not None:
			_settle_future(task.future, error=error)
		elif valid:
			_settle_future(task.future, result=result)
		else:
			task.future.cancel()
		if notify_done:
			try:
				self._deliver_done(task.request)
			except Exception:
				self._logger.error("Speech done notification error", exc_info=True)

	def _finish_task_locked(self, task):
		request = task.request
		request.remaining -= 1
		if request.state is RequestState.SUBMITTED and request.token.is_cancelled():
			request.state = RequestState.CANCELLED
		if request.remaining == 0:
			self._requests.pop(request.request_id, None)
			if request.state is RequestState.SUBMITTED:
				request.state = RequestState.COMPLETED
		if (
			request.has_speech
			and not request.done_sent
			and request.epoch == self._epoch
			and request.state in (RequestState.COMPLETED, RequestState.FAILED)
		):
			request.done_sent = True
			return True
		return False
