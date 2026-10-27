"""Completion contracts chosen from each wrapper's declared drain profile.

Verified opt-ins require evidence for the exact runtime profile. Keep the
verified table empty until the engine/version/audio mode has documented
physical playback and ordered-index evidence. IndexCommand support alone
never establishes completion semantics or a safe integer range.

A wrapper opts into DRAIN by declaring ``Voice.drain_profile``; its opened core
then decides through ``get_segment_drain_support``. This is separate from
physical playback certification. No installed wrapper profile is verified yet,
so DRAIN for them is a forced activation controlled by ``forceUnverifiedDrain``;
turning it off restores LEGACY_DONE for every one.
"""

import logging

from ..runtime.models import CompletionContract, CompletionMode, IndexRange
from ..runtime.playbackWork import DrainSupport

_VERIFIED_CONTRACTS: dict[tuple[str, str, str], CompletionContract] = {}

_DRAIN_CONTRACT = CompletionContract(CompletionMode.DRAIN, IndexRange(1, 9999))


class CompletionPolicy:
	def __init__(
		self,
		*,
		nvdaVersion: str | None = None,
		logger=None,
		forceUnverifiedDrain: bool = True,
	):
		# Forced activation of DRAIN on wrapper profiles without playback evidence.
		self.forceUnverifiedDrain = forceUnverifiedDrain
		self.nvdaVersion = nvdaVersion
		self._logger = logger or logging.getLogger(__name__)
		self._fallbacks: set[tuple] = set()

	def select(self, voiceClass: type, core: object) -> CompletionContract:
		"""Choose the opened core's contract, logging each distinct fallback once."""
		audioMode = self.audioMode(voiceClass, core)
		contract, support = self.contractFor(
			voiceClass,
			core,
			nvdaVersion=self.nvdaVersion,
			audioMode=audioMode,
		)
		if support is not None and not support.supported:
			profile = (voiceClass.engine, self.nvdaVersion, audioMode, support.profile, support.reason)
			if profile not in self._fallbacks:
				self._fallbacks.add(profile)
				self._logger.warning(
					"WorldVoice %s uses LEGACY_DONE (NVDA %s, audio %s, profile %s): %s",
					*profile,
				)
		return contract

	def audioMode(self, voiceClass: type, core: object) -> str:
		"""Report the opened core's audio path; only explicit booleans are trusted."""
		profile = getattr(voiceClass, "drain_profile", None)
		if profile is None or not profile.wasapi_dependent:
			return "default"
		useWasapi = getattr(core, "useWasapi", None)
		return "wasapi" if useWasapi is True else "legacy" if useWasapi is False else "unknown"

	def drainSupport(
		self,
		voiceClass: type,
		core: object,
		*,
		nvdaVersion: str,
		audioMode: str,
	) -> DrainSupport:
		"""Ask the opened core of a Voice that declares a drain profile."""
		moduleName = __package__.rsplit(".", 1)[0] + ".driver." + voiceClass.engine

		def unsupported(reason):
			return DrainSupport(False, moduleName, reason)

		if getattr(voiceClass, "drain_profile", None) is None:
			return unsupported("The Voice declares no drain profile")
		driver = getattr(voiceClass, "synth_driver_class", None)
		if not isinstance(driver, type) or not isinstance(core, driver):
			return unsupported("The opened core is not the Voice's custom outer SynthDriver")
		if not callable(getattr(core, "speak_segment", None)):
			return unsupported("The custom core has no callable speak_segment entry")
		check = getattr(core, "get_segment_drain_support", None)
		if not callable(check):
			return unsupported("The custom core has no callable get_segment_drain_support check")
		try:
			support = check(nvda_version=nvdaVersion, audio_mode=audioMode)
		except Exception as error:  # noqa: BLE001 - any failure means drain is unsupported
			return unsupported(f"Drain support inspection failed: {type(error).__name__}: {error}")
		if not isinstance(support, DrainSupport) or not isinstance(support.supported, bool):
			return unsupported("The wrapper did not return an explicit DrainSupport boolean decision")
		if not support.supported and not support.reason:
			return unsupported("The wrapper has no supported adapter/native drain profile")
		if support.supported and not self.forceUnverifiedDrain:
			return DrainSupport(
				False,
				support.profile,
				f"Unverified DRAIN is disabled by force_unverified_drain: {support.reason}",
			)
		return support

	def contractFor(
		self,
		voiceClass: type,
		core: object,
		*,
		nvdaVersion: str,
		audioMode: str,
	) -> tuple[CompletionContract, DrainSupport | None]:
		"""Select the contract before any segment starts.

		Returns the wrapper's drain support decision too, or None when the Voice
		declares no drain profile. Unsupported profiles must not select a
		different contract while a segment is waiting for completion.
		"""
		if getattr(voiceClass, "drain_profile", None) is None:
			key = (voiceClass.engine, nvdaVersion, audioMode)
			return _VERIFIED_CONTRACTS.get(key, CompletionContract()), None
		support = self.drainSupport(voiceClass, core, nvdaVersion=nvdaVersion, audioMode=audioMode)
		return (_DRAIN_CONTRACT if support.supported else CompletionContract()), support
