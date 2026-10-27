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


def _speakSegment(adapter, commands, token, context, onEvent):
	adapter._core.speak_segment(commands, token, context=context, on_event=onEvent)


def _speakPlain(adapter, commands, token, context, onEvent):
	if adapter.capabilities.supports_cancellation_token:
		adapter._core.speak(commands, cancellationToken=token)
	else:
		adapter._core.speak(commands)


# The completion rule names the core entry; each entry has its own signature.
_ENTRIES = {
	SpeakEntry.SEGMENT: _speakSegment,
	SpeakEntry.PLAIN: _speakPlain,
}


class LegacyEngineAdapter:
	def __init__(
		self,
		voiceClass: type,
		resolveVoice: Callable[[str], object],
		*,
		indexLedger: IndexLedger | None = None,
		completion: CompletionContract | None = None,
	):
		self._voiceClass = voiceClass
		self._resolveVoice = resolveVoice
		self._indexLedger = indexLedger
		self._completion = completion or CompletionContract()
		self._completionConfigured = completion is not None
		self._segmentEvents: Callable[[PlaybackContext], SegmentEventSink] | None = None
		self._spoken = False
		self._sourceId = None
		self._opened = False
		self._core = None
		self.notificationSource = None

	def open(self) -> None:
		if self._opened:
			return
		# create_core either returns a core this adapter owns or raises without one.
		self._core = self._voiceClass.create_core()
		self.notificationSource = self._core
		self._opened = True

	@property
	def core(self):
		return self._core

	def configureCompletion(self, contract: CompletionContract) -> None:
		"""Fix completion semantics for this opened resource before playback."""
		if not self._opened or self._spoken:
			raise RuntimeError("Completion must be configured after open and before speech")
		if self._completionConfigured and contract != self._completion:
			raise RuntimeError("An opened resource cannot change its completion contract")
		self._completion = contract
		self._completionConfigured = True

	def configureSegmentEvents(self, factory: Callable[[PlaybackContext], SegmentEventSink]) -> None:
		"""Connect segment notifications before the resource is published."""
		if not self._opened or not self._completionConfigured or self._spoken:
			raise RuntimeError("Segment events must be configured after completion and before speech")
		if not callable(getattr(self._core, "speak_segment", None)):
			raise ValueError("Segment events require a callable speak_segment entry")
		if not callable(factory):
			raise TypeError("Segment event factory must be callable")
		self._segmentEvents = factory

	def close(self) -> None:
		if not self._opened:
			return
		core = self._core
		self._opened = False
		self._core = None
		self.notificationSource = None
		self._segmentEvents = None
		self._spoken = False
		self._voiceClass.destroy_core(core)

	@property
	def capabilities(self) -> EngineCapabilities:
		extra = getattr(self._voiceClass, "extra_capabilities", frozenset())
		return EngineCapabilities(
			settings=frozenset(self._voiceClass.supportedSettings()),
			supports_waitfactor="waitfactor" in extra,
			supports_variants="variant" in extra,
			supports_cancellation_token=bool(getattr(self._core, "supportsCancellationToken", False)),
			completion=self._completion,
		)

	def listVoices(self) -> tuple[VoiceSpec, ...]:
		specs = []
		for voice in self._voiceClass.voices(self._core):
			try:
				engine, voiceId, language = voice["engine"], voice["id"], voice["language"]
				specs.append(
					VoiceSpec(
						id=voiceId,
						name=f"{engine}:{voiceId}",
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
		return tuple(self._resolveVoice(key).variants)

	def apply(self, spec: VoiceSpec, snapshot: VoiceSnapshot) -> None:
		core = self._core
		core.voice = spec.id
		supported = self.capabilities.settings
		for name in APPLY_ORDER:
			if name in supported:
				setattr(core, name, getattr(snapshot, name))
		self._resolveVoice(spec.name).applyEngineSettings(core, snapshot)

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
			if self._indexLedger is None:
				raise ValueError("Marker completion requires an index ledger")
			self._sourceId = context.source_id
		if rule.drain_event is not None and self._segmentEvents is None:
			raise RuntimeError("Drain completion requires a segment event factory")
		if token.is_cancelled():
			if rule.correlated:
				self.finish_segment(context)
			return
		try:
			if rule.correlated:
				# Legacy direct calls must not load NVDA command dependencies.
				from .indexCodec import encodeSegment

				commands = encodeSegment(commands, context, self._indexLedger)
			onEvent = self._segmentEvents(context) if rule.entry is SpeakEntry.SEGMENT else None
			if token.is_cancelled():
				if rule.correlated:
					self.finish_segment(context)
				return
			_ENTRIES[rule.entry](self, commands, token, context, onEvent)
		except Exception:
			if rule.correlated:
				self.finish_segment(context)
			raise

	def finish_segment(self, context: PlaybackContext) -> None:
		if self._indexLedger is not None:
			self._indexLedger.retireSegment(context)

	def cancel(self) -> None:
		if self._indexLedger is not None and self._sourceId is not None:
			self._indexLedger.retireSource(self._sourceId)
		self._core.cancel()

	def pause(self, switch: bool) -> None:
		self._core.pause(switch)
