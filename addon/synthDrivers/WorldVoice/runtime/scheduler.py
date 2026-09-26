"""Request scheduling independent of engines and application notifications.

Lock order is delivery lock -> state condition. No state-locked path acquires
the delivery lock. Engine calls, output, and Future completion (which can run
user callbacks) always execute outside the state condition. Only the worker
finishes submitted tasks; engine callbacks record signals or delivery intents.
"""

from collections.abc import Iterable
from concurrent.futures import Future
from dataclasses import dataclass, field
from enum import Enum
import logging
import queue
import threading
from typing import Protocol

from .models import EventKind, PlaybackEvent, SpeechCommands
from .session import PlaybackPort


class NotificationOutput(Protocol):
    def index_reached(self, index: int) -> None: ...

    def done_speaking(self) -> None: ...


class CancellationToken:
    def __init__(self):
        self._event = threading.Event()

    def cancel(self):
        self._event.set()

    def is_cancelled(self):
        return self._event.is_set()

    def wait(self, timeout=None):
        return self._event.wait(timeout)


class SpeechFuture(Future):
    """Future with the legacy callback-taking, Future-flattening then API."""

    def then(self, fn):
        following = SpeechFuture()

        def transfer(result):
            if following.done():
                return
            if result.cancelled():
                following.cancel()
            elif result.exception() is not None:
                following.set_exception(result.exception())
            else:
                following.set_result(result.result())

        def callback(future):
            if following.done():
                return
            if future.cancelled():
                following.cancel()
                return
            try:
                result = fn(future)
                if isinstance(result, Future):
                    result.add_done_callback(transfer)
                else:
                    following.set_result(result)
            except Exception as error:
                if not following.done():
                    following.set_exception(error)

        self.add_done_callback(callback)
        return following


class RequestState(Enum):
    BUILDING = "building"
    SUBMITTED = "submitted"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


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


@dataclass
class _Task:
    playback: PlaybackPort | None
    voice_key: str | None
    commands: SpeechCommands
    seconds: float | None
    future: SpeechFuture
    request: SpeechRequest
    source_id: object = None


class TaskManager:
    def __init__(self, output: NotificationOutput, *, logger=None):
        self._output = output
        self._logger = logger if logger is not None else logging.getLogger(__name__)
        self._q = queue.Queue()
        self._state_cond = threading.Condition()
        self._delivery_lock = threading.RLock()
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
            request = SpeechRequest(self._next_request_id, self._epoch, CancellationToken())
            self._next_request_id += 1
            self._requests[request.request_id] = request
            return request

    def _require_building_locked(self, request):
        if (self._closed or request.state is not RequestState.BUILDING
                or self._requests.get(request.request_id) is not request):
            raise InvalidRequestState("Request is not building")

    def append_speech(self, request, playback: PlaybackPort, voice_key: str,
                      commands: SpeechCommands) -> SpeechFuture:
        with self._state_cond:
            self._require_building_locked(request)
            future = SpeechFuture()
            request.tasks.append(_Task(playback, voice_key, commands, None, future, request))
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
            if (self._closed or request.state is not RequestState.BUILDING
                    or self._requests.get(request.request_id) is not request
                    or request.epoch != self._epoch or request.token.is_cancelled()):
                return False
            request.state = RequestState.SUBMITTED
            request.remaining = len(request.tasks)
            if not request.remaining:
                request.state = RequestState.COMPLETED
                self._requests.pop(request.request_id)
            for task in request.tasks:
                self._q.put(task)
            return True

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
            if not future.done():
                future.set_exception(error)

    def _valid_locked(self, task):
        request = task.request
        return (not self._closed and request.state is RequestState.SUBMITTED
                and request.epoch == self._epoch and not request.token.is_cancelled()
                and not task.future.cancelled())

    def on_event(self, event: PlaybackEvent) -> None:
        with self._state_cond:
            task = self._current_task
            if (task is None or task.playback is None or event.source_id is not task.source_id
                    or self._current_phase != "awaiting_done" or not self._valid_locked(task)
                    or self._current_done_event.is_set()):
                return
            if event.kind is EventKind.DONE:
                self._current_done_event.set()
                return
            if (event.kind is not EventKind.INDEX or event.index is None
                    or event.index in self._current_indexes):
                return
            self._current_indexes.add(event.index)
        self._deliver_index(task, event.index)

    def _deliver_index(self, task, index):
        with self._delivery_lock:
            with self._state_cond:
                valid = (self._current_task is task and self._current_phase == "awaiting_done"
                         and not self._current_done_event.is_set() and self._valid_locked(task))
            if valid:
                self._output.index_reached(index)

    def _deliver_done(self, request):
        with self._delivery_lock:
            with self._state_cond:
                # Execution failure cancels the token to skip remaining tasks,
                # but still releases the application's speaking wait once.
                valid = (not self._closed and request.epoch == self._epoch
                         and request.state in (RequestState.COMPLETED, RequestState.FAILED))
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
        with self._delivery_lock:
            with self._state_cond:
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
        with self._delivery_lock:
            with self._state_cond:
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
            playback = (current.playback if current and self._valid_locked(current)
                        and self._current_phase in ("starting", "awaiting_done") else None)
        if playback is not None:
            playback.pause(switch)

    def shutdown(self) -> None:
        with self._state_cond:
            first = not self._closed
            self._closed = True
        if first:
            self.cancel()
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
            source = task.playback.source_id if task.playback is not None else None
            with self._state_cond:
                while self._stops_in_flight:
                    self._state_cond.wait()
                valid = self._valid_locked(task)
                if valid:
                    task.source_id = source
                    self._current_task = task
                    self._current_phase = "starting"
                    self._current_indexes = set()
                    self._current_done_event = threading.Event()
            if not valid:
                return
            if task.playback is None:
                task.request.token.wait(task.seconds)
                return
            task.playback.activate(task.voice_key)
            with self._state_cond:
                if not self._valid_locked(task):
                    return
                # Register before entry because speak can synchronously emit DONE.
                self._current_phase = "awaiting_done"
                done = self._current_done_event
            task.playback.speak(task.commands, task.request.token)
            if task.request.token.is_cancelled():
                # A non-token-aware synchronous speak may outlive the first stop.
                self._stop_playback(task.playback)
                return
            done.wait()
            result = True
        except Exception as caught:
            error = caught
            with self._state_cond:
                if self._valid_locked(task):
                    task.request.state = RequestState.FAILED
                    task.request.token.cancel()
                    failed = True
            self._logger.error("Speech scheduler task error", exc_info=True)
        finally:
            if failed and task.playback is not None:
                self._stop_playback(task.playback)
            with self._state_cond:
                valid = self._valid_locked(task)
                if self._current_task is task:
                    self._current_task = None
                    self._current_phase = None
                    self._current_done_event = None
                    self._current_indexes = set()
                notify_done = self._finish_task_locked(task)
            # The state transition happens before user callbacks can re-enter.
            if not task.future.done():
                if error is not None:
                    task.future.set_exception(error)
                elif valid:
                    task.future.set_result(result)
                else:
                    task.future.cancel()
            if notify_done:
                self._deliver_done(task.request)

    def _finish_task_locked(self, task):
        request = task.request
        request.remaining -= 1
        if request.state is RequestState.SUBMITTED and request.token.is_cancelled():
            request.state = RequestState.CANCELLED
        if request.remaining == 0:
            self._requests.pop(request.request_id, None)
            if request.state is RequestState.SUBMITTED:
                request.state = RequestState.COMPLETED
        if (request.has_speech and not request.done_sent and request.epoch == self._epoch
                and request.state in (RequestState.COMPLETED, RequestState.FAILED)):
            request.done_sent = True
            return True
        return False
