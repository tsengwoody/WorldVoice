"""Shared ownership and retirement of one contextual speech segment at a time.

Engine hooks establish native and playback boundaries. This coordinator never
infers native quiescence from an empty callback count alone.
"""

from collections import deque
from threading import Condition, Event, Thread
from typing import Protocol

from .models import PlaybackContext, PlaybackEvent, SegmentEventSink, SpeechCommands
from .playbackWork import PlaybackWork
from .session import CancellationView


class SegmentEngineHooks(Protocol):
    def submit_native(self, operation: "SegmentOperation", commands: SpeechCommands) -> None: ...
    def request_stop(self, operation: "SegmentOperation") -> None: ...
    def wait_native_boundary(self, operation: "SegmentOperation") -> None: ...
    def wait_native_retired(self, operation: "SegmentOperation") -> None: ...
    def wait_playback_drained(self, operation: "SegmentOperation") -> None: ...


class SegmentOperation:
    """Identity retained by callbacks and feeds through resource retirement."""

    def __init__(self, lifecycle: "SegmentLifecycle", work: PlaybackWork,
                 sink: SegmentEventSink, event_holder: list[PlaybackEvent]):
        self._lifecycle = lifecycle
        self.work = work
        self._sink = sink
        self._event_holder = event_holder
        self._admitting = True
        self._leases = 0
        self._submitted = False
        self._submit_done = Event()
        self._playback_verified = False
        self._playback_stop_done: Event | None = None
        self._run_started = False
        self._retired = False
        self._error: Exception | None = None
        self._stop_done: Event | None = None

    def is_valid(self) -> bool:
        with self._lifecycle._condition:
            failed = self._error is not None
        return not failed and self.work.is_valid()


class ProducerLease:
    """A producer's original operation, retained until its actual work exits."""

    def __init__(self, operation: SegmentOperation):
        self._operation = operation
        self._retired = False

    @property
    def operation(self) -> SegmentOperation:
        return self._operation


class SegmentLifecycle:
    def __init__(self, hooks: SegmentEngineHooks):
        self._hooks = hooks
        self._condition = Condition()
        self._resource_busy = False
        self._fault: Exception | None = None
        self._terminated = False
        self._operations: set[SegmentOperation] = set()
        self._delivery_queue: deque[SegmentOperation] = deque()
        self._delivery_thread = Thread(target=self._deliver,
                                       name="WorldVoiceSegmentDelivery", daemon=True)
        self._delivery_thread.start()

    def accept(self, context: PlaybackContext, token: CancellationView,
               sink: SegmentEventSink) -> SegmentOperation:
        with self._condition:
            if self._terminated:
                raise RuntimeError("segment lifecycle is terminated")
            # PlaybackWork commits exactly once. Its internal sink records the
            # event while the coordinator arbitrates fail/cancel vs success;
            # the external sink runs later, outside that lock.
            holder = []
            work = PlaybackWork(context, token, holder.append)
            operation = SegmentOperation(self, work, sink, holder)
            self._operations.add(operation)
            return operation

    def run(self, operation: SegmentOperation, commands: SpeechCommands) -> None:
        self._require_operation(operation)
        with self._condition:
            if operation._run_started:
                raise RuntimeError("segment operation was already run")
            operation._run_started = True
            while self._resource_busy and not self._terminated and self._fault is None:
                if not operation.work.is_valid():
                    self._operations.discard(operation)
                    return
                # An external token can cancel without calling cancel().
                self._condition.wait(0.05)
            if self._fault is not None:
                self._operations.discard(operation)
                raise RuntimeError("segment resources cannot be safely reused") from self._fault
            if self._terminated or not operation.work.is_valid():
                self._operations.discard(operation)
                return
            self._resource_busy = True

        try:
            self._run_owned(operation, commands)
        finally:
            # Coordinate the last stop check with cancel(). A late cancel
            # cannot stop an old operation after its successor takes over.
            while True:
                with self._condition:
                    stop_done = operation._stop_done
                    needs_stop = (operation._submitted and operation._error is None
                                  and not operation.work.is_valid() and stop_done is None)
                    # A stop can race with the player barrier. Only a barrier
                    # completed after the latest stop permits handoff.
                    needs_playback = (operation._submitted and self._fault is None
                                      and (not operation._playback_verified
                                           or operation._playback_stop_done is not stop_done))
                    if (not needs_stop and not needs_playback
                            and (stop_done is None or stop_done.is_set())):
                        operation._retired = True
                        self._resource_busy = False
                        if operation.work.is_valid():
                            self._delivery_queue.append(operation)
                        else:
                            self._operations.discard(operation)
                        self._condition.notify_all()
                        break
                if needs_stop:
                    self.cancel(operation)
                elif stop_done is not None and not stop_done.is_set():
                    stop_done.wait()
                elif needs_playback:
                    try:
                        self._hooks.wait_playback_drained(operation)
                    except Exception as error:
                        self._latch_fault(operation, error)
                    else:
                        with self._condition:
                            operation._playback_verified = True
                            operation._playback_stop_done = stop_done

    def _run_owned(self, operation: SegmentOperation, commands: SpeechCommands) -> None:
        with self._condition:
            if operation._error is not None or not operation.work.is_valid():
                return
            operation._submitted = True
        try:
            try:
                self._hooks.submit_native(operation, commands)
            finally:
                operation._submit_done.set()
            self._stop_if_cancelled(operation)
            self._hooks.wait_native_boundary(operation)
            self._stop_if_cancelled(operation)
            self.close_admission(operation)
            self._hooks.wait_native_retired(operation)
            with self._condition:
                self._condition.wait_for(lambda: operation._leases == 0)
                stop_done = operation._stop_done
            self._stop_if_cancelled(operation)
            with self._condition:
                stop_done = operation._stop_done
            if stop_done is not None:
                stop_done.wait()
        except Exception as error:
            self._latch_fault(operation, error)
        finally:
            self.close_admission(operation)
            with self._condition:
                stop_done = operation._stop_done
            if stop_done is not None:
                stop_done.wait()

    def admit_producer(self, operation: SegmentOperation,
                       parent: ProducerLease | None = None) -> ProducerLease | None:
        self._require_operation(operation)
        with self._condition:
            if parent is not None:
                if parent.operation is not operation or parent._retired:
                    return None
                # A child may be needed for cleanup after cancellation.
            elif not operation._admitting or not operation.work.is_valid():
                return None
            if operation not in self._operations:
                return None
            lease = ProducerLease(operation)
            operation._leases += 1
            return lease

    def retire_producer(self, lease: ProducerLease) -> None:
        operation = lease.operation
        self._require_operation(operation)
        with self._condition:
            if lease._retired:
                return
            lease._retired = True
            operation._leases -= 1
            self._condition.notify_all()

    def close_admission(self, operation: SegmentOperation) -> None:
        self._require_operation(operation)
        with self._condition:
            operation._admitting = False
            self._condition.notify_all()

    def cancel(self, operation: SegmentOperation) -> None:
        self._require_operation(operation)
        with self._condition:
            operation.work.cancel()
            operation._admitting = False
            self._condition.notify_all()
        self._start_stop(operation)

    def fail(self, operation: SegmentOperation, error: Exception) -> None:
        self._require_operation(operation)
        with self._condition:
            if operation._error is None:
                operation._error = error
            operation._admitting = False
            self._condition.notify_all()
        self._start_stop(operation)

    def terminate(self) -> None:
        with self._condition:
            self._terminated = True
            operations = tuple(self._operations)
            self._condition.notify_all()
        for operation in operations:
            self.cancel(operation)

    def _deliver(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._delivery_queue or self._terminated)
                if not self._delivery_queue:
                    return
                operation = self._delivery_queue.popleft()
                error = operation._error
                if error is None:
                    operation.work.complete_drained()
                else:
                    operation.work.fail(error)
                event = operation._event_holder.pop() if operation._event_holder else None
            try:
                if event is not None:
                    operation._sink(event)
            except Exception:
                # A consumer's exception must not stop the dispatcher or
                # become the following operation's failure.
                pass
            finally:
                with self._condition:
                    self._operations.discard(operation)
                    self._condition.notify_all()

    def _start_stop(self, operation: SegmentOperation) -> None:
        with self._condition:
            if (not operation._submitted or operation._retired
                    or operation._stop_done is not None):
                return
            done = Event()
            operation._stop_done = done
            # A stop may run before the submit hook enters native code. Keep
            # that first stop available to interrupt a blocking submit, then
            # stop again after submission returns to cover the launch race.
            submitting = not operation._submit_done.is_set()

        def stop():
            try:
                self._hooks.request_stop(operation)
                if submitting:
                    operation._submit_done.wait()
                    self._hooks.request_stop(operation)
            except Exception as error:
                self._latch_fault(operation, error)
            finally:
                done.set()
                with self._condition:
                    self._condition.notify_all()

        Thread(target=stop, name="WorldVoiceSegmentStop", daemon=True).start()

    def _stop_if_cancelled(self, operation: SegmentOperation) -> None:
        with self._condition:
            failed = operation._error is not None
        if not failed and not operation.work.is_valid():
            self.cancel(operation)

    def _latch_fault(self, operation: SegmentOperation, error: Exception) -> None:
        with self._condition:
            if operation._error is None:
                operation._error = error
            if self._fault is None:
                self._fault = error
            operation._admitting = False
            self._condition.notify_all()

    def _require_operation(self, operation: SegmentOperation) -> None:
        if not isinstance(operation, SegmentOperation) or operation._lifecycle is not self:
            raise ValueError("operation does not belong to this lifecycle")
