"""Engine ownership and playback contracts independent of legacy drivers."""

from collections.abc import Callable, Mapping
from threading import RLock
from typing import Protocol

from .models import (
	CompletionContract,
	CompletionMode,
	EngineCapabilities,
	PlaybackContext,
	SourceId,
	SpeechCommands,
	VoiceSnapshot,
	VoiceSpec,
)
from .settings import VoiceSettingsStore


class CancellationView(Protocol):
	"""Read-only cancellation state with change notification.

	add_callback(callback) calls ``callback`` once when the token is cancelled,
	immediately if it already is, and returns a function that removes it.
	Callbacks run outside the token's lock and must only notify.
	"""

	def is_cancelled(self) -> bool: ...

	def add_callback(self, callback: Callable[[], None]) -> Callable[[], None]: ...


class EngineAdapter(Protocol):
	notification_source: object
	capabilities: EngineCapabilities

	def open(self) -> None: ...

	def close(self) -> None: ...

	def list_voices(self) -> tuple[VoiceSpec, ...]: ...

	def variants(self, key: str) -> tuple[Mapping[str, str], ...]: ...

	def apply(self, spec: VoiceSpec, snapshot: VoiceSnapshot) -> None: ...

	def speak(
		self,
		commands: SpeechCommands,
		token: CancellationView,
		*,
		context: PlaybackContext | None = None,
	) -> None: ...

	def finish_segment(self, context: PlaybackContext) -> None: ...

	def cancel(self) -> None: ...

	def pause(self, switch: bool) -> None: ...


class PlaybackPort(Protocol):
	source_id: SourceId
	completion: CompletionContract

	def activate(self, key: str) -> bool: ...

	def speak(
		self,
		commands: SpeechCommands,
		token: CancellationView,
		*,
		context: PlaybackContext | None = None,
	) -> None: ...

	def finish_segment(self, context: PlaybackContext) -> None: ...

	def cancel(self) -> None: ...

	def pause(self, switch: bool) -> None: ...


class EngineSession:
	"""Own one adapter lifecycle and remember only successful activations.

	The assembly owner opens, closes, or replaces resources only while the
	session is idle. Activation is serialized separately from playback:
	cancel and pause never wait on an activation or a blocking speak call.
	"""

	def __init__(self, adapter: EngineAdapter, settings: VoiceSettingsStore):
		self._adapter = adapter
		self._settings = settings
		self._opened = False
		self.source_id: SourceId = object()
		self._activation_lock = RLock()
		self._applied: tuple[SourceId, str, int] | None = None

	def open(self) -> None:
		if self._opened:
			return
		self.source_id = object()
		self.invalidate()
		# Claim cleanup before open: an adapter can acquire resources and
		# then fail. close must run once even for that partial initialization.
		self._opened = True
		try:
			self._adapter.open()
		except Exception as error:
			try:
				self.close()
			except Exception as cleanup_error:
				# Keep initialization primary without hiding cleanup failure.
				raise error from cleanup_error
			raise

	def close(self) -> None:
		if not self._opened:
			return
		self._opened = False
		self.invalidate()
		self._adapter.close()

	def replace_adapter(self, adapter: EngineAdapter) -> None:
		"""Replace idle resources; the assembly owner must rebind events."""
		self.close()
		self._adapter = adapter
		self.open()

	def invalidate(self) -> None:
		with self._activation_lock:
			self._applied = None

	@property
	def capabilities(self) -> EngineCapabilities:
		return self._adapter.capabilities

	@property
	def completion(self) -> CompletionContract:
		return self.capabilities.completion

	def list_voices(self) -> tuple[VoiceSpec, ...]:
		return self._adapter.list_voices()

	def variants(self, key: str) -> tuple[Mapping[str, str], ...]:
		return self._adapter.variants(key)

	def activate(self, key: str) -> bool:
		with self._activation_lock:
			state = self._settings.state(key)
			snapshot = state.snapshot()
			applied = self._applied
			if (
				applied is not None
				and applied[0] is self.source_id
				and applied[1] == key
				and applied[2] == snapshot.revision
			):
				return False
			# A failed apply may have changed the engine partially, including
			# its voice. Even the previously active voice then needs reapply.
			self._applied = None
			self._adapter.apply(state.spec, snapshot)
			self._applied = (self.source_id, key, snapshot.revision)
			return True

	def speak(
		self,
		commands: SpeechCommands,
		token: CancellationView,
		*,
		context: PlaybackContext | None = None,
	) -> None:
		if context is None:
			if self.completion.mode is not CompletionMode.LEGACY_DONE:
				raise ValueError("Correlated completion requires a playback context")
			self._adapter.speak(commands, token)
		else:
			if context.source_id is not self.source_id:
				raise ValueError("Playback context belongs to a different source")
			self._adapter.speak(commands, token, context=context)

	def finish_segment(self, context: PlaybackContext) -> None:
		if context.source_id is not self.source_id:
			raise ValueError("Playback context belongs to a different source")
		self._adapter.finish_segment(context)

	def cancel(self) -> None:
		self._adapter.cancel()

	def pause(self, switch: bool) -> None:
		self._adapter.pause(switch)
