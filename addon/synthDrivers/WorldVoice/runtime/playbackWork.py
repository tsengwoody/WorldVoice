"""Segment playback work and drain-support evidence, independent of native SDKs.

Drivers own playback barriers and proof of native quiescence; SegmentHost holds
callback consumers through real feed and any final stop of invalidated playback.
"""

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock

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

	def __init__(
		self,
		context: PlaybackContext,
		token: CancellationView,
		on_event: SegmentEventSink,
		*,
		on_cancel: Callable[[], None] | None = None,
	):
		self._context = context
		self._token = token
		self._on_event = on_event
		self._on_cancel = on_cancel
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
		"""Invalidate this work without mutating the caller's token or notifying its sink.

		``on_cancel`` (the owner's wake-up) runs after the work lock is released.
		"""
		with self._lock:
			self._active = False
		if self._on_cancel is not None:
			self._on_cancel()

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
			event = PlaybackEvent(
				kind,
				self._context.source_id,
				segment_id=self._context.segment_id,
				error=error,
			)
		# The sink may cancel/unbind, reenter this work, or block.
		self._on_event(event)
		# A finished work is invalid too; wake its owner's waiters.
		if self._on_cancel is not None:
			self._on_cancel()
		return True
