"""Translate NVDA notifications at the boundary of the pure voice runtime."""

from collections.abc import Callable
from threading import RLock

from .runtime.models import EventKind, PlaybackEvent


class NvdaEventBridge:
    """Own event subscriptions and resource identities, never request identities.

    The composition owner starts and closes the bridge in lifecycle order.
    Event delivery may run on other threads; the state lock protects snapshots
    only and is never held while calling handlers or public notifications.
    """

    def __init__(self, owner, *, done_event, index_event, get_synth):
        self._owner = owner
        self._done_event = done_event
        self._index_event = index_event
        self._get_synth = get_synth
        self._lock = RLock()
        self._closed = False
        self._handler = None
        self._sources = {}
        self._registrations = []

    def start(self, handler: Callable[[PlaybackEvent], None]) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("Event bridge is closed")
            if self._handler is not None:
                raise RuntimeError("Event bridge is already started")
            self._handler = handler
        try:
            for event, callback in (
                (self._done_event, self._on_done),
                (self._index_event, self._on_index),
            ):
                # Claim cleanup before register: it can add the handler then fail.
                with self._lock:
                    self._registrations.append((event, callback))
                event.register(callback)
        except Exception as error:
            try:
                self.close()
            except Exception as cleanup_error:
                raise error from cleanup_error
            raise

    def bind(self, source: object, source_id: object) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("Event bridge is closed")
            existing = self._sources.get(id(source))
            if existing is not None and existing[1] is not source_id:
                raise ValueError("Notification source is already bound to another source ID")
            # Retain the object as well as its id to prevent identity reuse.
            self._sources[id(source)] = (source, source_id)

    def unbind(self, source_id: object) -> None:
        with self._lock:
            for identity, (_, bound_id) in tuple(self._sources.items()):
                if bound_id is source_id:
                    del self._sources[identity]

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._handler = None
            registrations = self._registrations
            self._registrations = []
        first_error = None
        try:
            for event, callback in registrations:
                try:
                    event.unregister(callback)
                except Exception as error:
                    if first_error is None:
                        first_error = error
        finally:
            with self._lock:
                self._sources.clear()
        if first_error is not None:
            raise first_error

    def _on_index(self, synth, index: int) -> None:
        self._receive(synth, EventKind.INDEX, index)

    def _on_done(self, synth) -> None:
        self._receive(synth, EventKind.DONE)

    def _receive(self, source, kind: EventKind, index: int | None = None) -> None:
        with self._lock:
            if self._closed or source is self._owner:
                return
            binding = self._sources.get(id(source))
            if binding is None or binding[0] is not source:
                return
            source_id = binding[1]
            handler = self._handler
        if handler is not None:
            handler(PlaybackEvent(kind, source_id, index))

    def _can_notify(self) -> bool:
        if self._get_synth() is not self._owner:
            return False
        with self._lock:
            return not self._closed and self._handler is not None

    def index_reached(self, index: int) -> None:
        if self._can_notify():
            self._index_event.notify(synth=self._owner, index=index)

    def done_speaking(self) -> None:
        if self._can_notify():
            self._done_event.notify(synth=self._owner)
