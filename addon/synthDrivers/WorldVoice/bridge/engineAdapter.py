"""Translate legacy engine hooks into the independent runtime contract."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from ..runtime.completion import SpeakEntry, rule_for
from ..runtime.models import (
	CompletionContract,
	EngineCapabilities,
	PlaybackContext,
	SegmentEventSink,
	SpeechCommands,
	VoiceSnapshot,
	VoiceSpec,
)
from ..runtime.session import CancellationView

if TYPE_CHECKING:
	from .indexLedger import IndexLedger

# runtime.voiceSettings.PARAMETER_NAMES in the order engines receive them. rateBoost comes first:
# eSpeak converts the rate through the current rate boost (NVDA synthDrivers/espeak.py _set_rate).
APPLY_ORDER = ("rateBoost", "rate", "pitch", "volume", "inflection")


def _speak_segment(adapter, commands, token, context, on_event):
	adapter._core.speak_segment(commands, token, context=context, on_event=on_event)


def _speak_plain(adapter, commands, token, context, on_event):
	if adapter.capabilities.supports_cancellation_token:
		adapter._core.speak(commands, cancellationToken=token)
	else:
		adapter._core.speak(commands)


# The completion rule names the core entry; each entry has its own signature.
_ENTRIES = {
	SpeakEntry.SEGMENT: _speak_segment,
	SpeakEntry.PLAIN: _speak_plain,
}


class LegacyEngineAdapter:
	def __init__(
		self,
		voice_class: type,
		resolve_voice: Callable[[str], object],
		*,
		index_ledger: IndexLedger | None = None,
		completion: CompletionContract | None = None,
	):
		self._voice_class = voice_class
		self._resolve_voice = resolve_voice
		self._index_ledger = index_ledger
		self._completion = completion or CompletionContract()
		self._completion_configured = completion is not None
		self._segment_events: Callable[[PlaybackContext], SegmentEventSink] | None = None
		self._spoken = False
		self._source_id = None
		self._opened = False
		self._core = None
		self.notification_source = None

	def open(self) -> None:
		if self._opened:
			return
		# create_core either returns a core this adapter owns or raises without one.
		self._core = self._voice_class.create_core()
		self.notification_source = self._core
		self._opened = True

	@property
	def core(self):
		return self._core

	def configure_completion(self, contract: CompletionContract) -> None:
		"""Fix completion semantics for this opened resource before playback."""
		if not self._opened or self._spoken:
			raise RuntimeError("Completion must be configured after open and before speech")
		if self._completion_configured and contract != self._completion:
			raise RuntimeError("An opened resource cannot change its completion contract")
		self._completion = contract
		self._completion_configured = True

	def configure_segment_events(self, factory: Callable[[PlaybackContext], SegmentEventSink]) -> None:
		"""Connect segment notifications before the resource is published."""
		if not self._opened or not self._completion_configured or self._spoken:
			raise RuntimeError("Segment events must be configured after completion and before speech")
		if not callable(getattr(self._core, "speak_segment", None)):
			raise ValueError("Segment events require a callable speak_segment entry")
		if not callable(factory):
			raise TypeError("Segment event factory must be callable")
		self._segment_events = factory

	def close(self) -> None:
		if not self._opened:
			return
		core = self._core
		self._opened = False
		self._core = None
		self.notification_source = None
		self._segment_events = None
		self._spoken = False
		self._voice_class.destroy_core(core)

	@property
	def capabilities(self) -> EngineCapabilities:
		extra = getattr(self._voice_class, "extra_capabilities", frozenset())
		return EngineCapabilities(
			settings=frozenset(self._voice_class.supportedSettings()),
			supports_waitfactor="waitfactor" in extra,
			supports_variants="variant" in extra,
			supports_cancellation_token=bool(getattr(self._core, "supportsCancellationToken", False)),
			completion=self._completion,
		)

	def list_voices(self) -> tuple[VoiceSpec, ...]:
		specs = []
		for voice in self._voice_class.voices(self._core):
			try:
				engine, voice_id, language = voice["engine"], voice["id"], voice["language"]
				specs.append(
					VoiceSpec(
						id=voice_id,
						name=f"{engine}:{voice_id}",
						description=voice.get("description", ""),
						language=language,
						engine=engine,
						locale=voice.get("locale", language),
					),
				)
			except KeyError as error:
				logging.getLogger(__name__).error("Invalid voice data: missing %s", error)
		return tuple(specs)

	def variants(self, key: str) -> tuple[Mapping[str, str], ...]:
		return tuple(self._resolve_voice(key).variants)

	def apply(self, spec: VoiceSpec, snapshot: VoiceSnapshot) -> None:
		core = self._core
		core.voice = spec.id
		supported = self.capabilities.settings
		for name in APPLY_ORDER:
			if name in supported:
				setattr(core, name, getattr(snapshot, name))
		self._resolve_voice(spec.name).applyEngineSettings(core, snapshot)

	def speak(
		self,
		commands: SpeechCommands,
		token: CancellationView,
		*,
		context: PlaybackContext | None = None,
	) -> None:
		self._spoken = True
		rule = rule_for(self._completion)
		if rule.correlated:
			if context is None:
				raise ValueError("Correlated completion requires a playback context")
			if self._index_ledger is None:
				raise ValueError("Marker completion requires an index ledger")
			self._source_id = context.source_id
		if rule.drain_event is not None and self._segment_events is None:
			raise RuntimeError("Drain completion requires a segment event factory")
		if token.is_cancelled():
			if rule.correlated:
				self.finish_segment(context)
			return
		try:
			if rule.correlated:
				# Legacy direct calls must not load NVDA command dependencies.
				from .indexCodec import encodeSegment

				commands = encodeSegment(commands, context, self._index_ledger)
			on_event = self._segment_events(context) if rule.entry is SpeakEntry.SEGMENT else None
			if token.is_cancelled():
				if rule.correlated:
					self.finish_segment(context)
				return
			_ENTRIES[rule.entry](self, commands, token, context, on_event)
		except Exception:
			if rule.correlated:
				self.finish_segment(context)
			raise

	def finish_segment(self, context: PlaybackContext) -> None:
		if self._index_ledger is not None:
			self._index_ledger.retire_segment(context)

	def cancel(self) -> None:
		if self._index_ledger is not None and self._source_id is not None:
			self._index_ledger.retire_source(self._source_id)
		self._core.cancel()

	def pause(self, switch: bool) -> None:
		self._core.pause(switch)
