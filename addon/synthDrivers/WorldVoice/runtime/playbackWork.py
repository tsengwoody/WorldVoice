"""Segment lifetime and callback ownership, independent of native SDKs.

Drivers own playback barriers and proof of native quiescence. They must retain
a callback lease through real feed and any final stop of invalidated playback:
admit -> feed outside locks -> stop if invalid -> release. The next native call
cannot take over that player's resources until native finish and every release.
"""

from dataclasses import dataclass
from threading import Condition, Lock

from .models import EventKind, PlaybackContext, PlaybackEvent, SegmentEventSink
from .session import CancellationView


@dataclass(frozen=True)
class DrainSupport:
    """Confirmed adapter/native contract; hardware validation is separate."""

    supported: bool
    profile: str
    reason: str


def runtime_profile(engine: str, nvda_version, audio_mode) -> str:
    """Name a wrapper profile by engine and the runtime it was opened under."""
    return f"{engine}/{nvda_version or 'unknown'}/{audio_mode or 'unknown'}"


def unverified_drain_support(profile: str, unverified: str) -> DrainSupport:
    """Report a drain-capable wrapper whose *unverified* evidence is still missing.

    The completion policy decides whether such a profile may use DRAIN.
    """
    return DrainSupport(True, profile, f"DRAIN explicitly enabled; {unverified} unverified")


class PlaybackWork:
    """Capture one segment's inputs and publish at most one terminal event."""

    def __init__(self, context: PlaybackContext, token: CancellationView,
                 on_event: SegmentEventSink):
        self._context = context
        self._token = token
        self._on_event = on_event
        self._lock = Lock()
        self._active = True
        self._error = None

    @property
    def context(self) -> PlaybackContext:
        return self._context

    @property
    def token(self) -> CancellationView:
        return self._token

    @property
    def error(self) -> Exception | None:
        with self._lock:
            return self._error

    def is_valid(self) -> bool:
        with self._lock:
            return self._active and not self._token.is_cancelled()

    def cancel(self) -> None:
        """Invalidate this work without mutating the caller's token or notifying."""
        with self._lock:
            self._active = False

    def fail(self, error: Exception) -> bool:
        return self._terminate(EventKind.SEGMENT_FAILED, error)

    def complete_drained(self) -> bool:
        """Publish only after the driver has proved this segment is drained."""
        return self._terminate(EventKind.SEGMENT_DRAINED)

    def _terminate(self, kind: EventKind, error: Exception | None = None) -> bool:
        with self._lock:
            if not self._active or self._token.is_cancelled():
                return False
            self._active = False
            self._error = error
            event = PlaybackEvent(kind, self._context.source_id,
                                  segment_id=self._context.segment_id, error=error)
        # The sink may cancel/unbind, reenter this work, or block.
        self._on_event(event)
        return True


class _NativeCall:
    """Opaque token retaining a call's identity until its consumers retire."""

    def __init__(self, gate, work):
        self._gate = gate
        self._work = work
        self._admitting = True
        self._finished = False
        self._callbacks = 0


class CallbackLease:
    """One admitted callback; release only after all its external work exits."""

    def __init__(self, gate, call):
        self._gate = gate
        self._call = call
        self._closed = False

    @property
    def work(self) -> PlaybackWork:
        return self._call._work

    @property
    def call_token(self) -> object:
        return self._call

    def close(self) -> None:
        with self._gate._condition:
            if self._closed:
                return
            self._closed = True
            self._call._callbacks -= 1
            self._gate._condition.notify_all()


class CallbackGate:
    """Serialize native calls without guessing when the SDK stops callbacks.

    State/counters are protected by the condition; its waits release the lock.
    No native calls, player operations or event delivery run under this lock.
    Gate admission may read work validity; PlaybackWork never acquires the gate.
    """

    def __init__(self):
        self._condition = Condition()
        self._current = None

    def begin_native(self, work: PlaybackWork) -> object:
        """Wait for the previous native finish and all its callbacks to exit."""
        with self._condition:
            self._condition.wait_for(lambda: self._current is None or (
                self._current._finished and self._current._callbacks == 0))
            call = _NativeCall(self, work)
            self._current = call
            return call

    def enter_callback(self) -> CallbackLease | None:
        with self._condition:
            call = self._current
            if call is None or not call._admitting or not call._work.is_valid():
                return None
            call._callbacks += 1
            return CallbackLease(self, call)

    def close(self, call_token: object) -> None:
        """Stop new admission; this does not declare native quiescence."""
        call = self._call(call_token)
        with self._condition:
            call._admitting = False

    def finish_native(self, call_token: object) -> None:
        """Driver declaration: this call can no longer initiate callbacks."""
        call = self._call(call_token)
        with self._condition:
            call._admitting = False
            call._finished = True
            self._condition.notify_all()

    def wait_retired(self, call_token: object) -> None:
        """Wait for admitted leases, independently of the native finish.

        Close admission first when a stable zero-callback barrier is needed.
        A return here alone never permits a new native call.
        """
        call = self._call(call_token)
        with self._condition:
            self._condition.wait_for(lambda: call._callbacks == 0)

    def _call(self, token: object) -> _NativeCall:
        if not isinstance(token, _NativeCall) or token._gate is not self:
            raise ValueError("Native call token does not belong to this gate")
        return token
