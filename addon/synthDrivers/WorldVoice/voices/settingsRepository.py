"""The existing NVDA config format, accessed through injected dependencies."""

import logging
from collections.abc import Callable, Mapping, MutableMapping

from ..runtime.models import SettingValue, VoiceSpec, VoiceValues
from ..runtime.voiceSettings import VOICE_PARAMETERS, boolean


def _confspec(convert, default) -> str:
	if convert is int:
		return f"integer(default={default},min=0,max=100)"
	if convert is boolean:
		return f"boolean(default={default})"
	return f"string(default={default})"


# The keys load and save store for each voice. NVDA's aggregated config sections do not expand
# __many__ (ref/nvda/source/config/__init__.py, AggregatedSection.__getitem__ looks the key up
# directly), so NVDA never validates these values against this spec: they come back as stored
# strings, and load converts them itself. This spec documents the stored keys, and every value
# save writes satisfies it.
VOICE_CONFSPEC = {name: _confspec(convert, default) for name, convert, default in VOICE_PARAMETERS}

# The bounds of an int parameter, as the confspec above states them; load refuses a value outside.
_INT_MIN = 0
_INT_MAX = 100

# NVDA's DEBUGWARNING level (logHandler.Logger.DEBUGWARNING), logged by number to stay NVDA-free.
_DEBUG_WARNING = 15

# (voice, key, stored value) triples already reported, so a voice loaded for every utterance logs once.
_reported: set[tuple[str, str, str]] = set()


class ConfigVoiceSettingsRepository:
	"""Each voice's own values in WorldVoice.voices; what voices inherit is decided elsewhere."""

	def __init__(self, conf_provider: Callable[[], MutableMapping], logger=None):
		self._conf_provider = conf_provider
		self._logger = logger or logging.getLogger(__name__)

	def _voices(self) -> MutableMapping:
		return self._conf_provider()["WorldVoice"]["voices"]

	def load(self, spec: VoiceSpec) -> VoiceValues:
		voices = self._voices()
		values = {name: convert(default) for name, convert, default in VOICE_PARAMETERS}
		if spec.name not in voices:
			voices[spec.name] = values.copy()
		for name, convert, default in VOICE_PARAMETERS:
			value = voices[spec.name].get(name, None)
			if value is not None:
				values[name] = self._convert(spec.name, name, convert, default, value)
		# WorldVoice 3.x stored "" for the default variant.
		if values["variant"] == "":
			values["variant"] = "default"
		return values

	def _convert(self, voice: str, name: str, convert, default, value) -> SettingValue:
		"""*value* converted; the default for a value the conversion refuses or outside the bounds.

		A refused value, such as "abc" or "50.0" for an int, and an int outside the confspec bounds,
		such as 150, are both invalid: there is no intent to approximate (decided by the user,
		2026-11-05). Each voice, key and stored value is reported once as a debug warning, like the
		pipeline's read_stored. Nothing is written back: the next save of the voice replaces the value.
		"""
		try:
			result = convert(value)
		except (TypeError, ValueError):
			return self._invalid(voice, name, convert, default, value)
		if convert is int and not _INT_MIN <= result <= _INT_MAX:
			return self._invalid(voice, name, convert, default, value)
		return result

	def _invalid(self, voice: str, name: str, convert, default, value) -> SettingValue:
		"""The default for an invalid stored *value*, reported the first time it is seen."""
		report = (voice, name, repr(value))
		if report not in _reported:
			_reported.add(report)
			self._logger.log(
				_DEBUG_WARNING,
				"WorldVoice: stored voice setting %r of %r is invalid (%r); using its default %r",
				name,
				voice,
				value,
				default,
			)
		return convert(default)

	def save(self, spec: VoiceSpec, values: Mapping[str, SettingValue]) -> None:
		converted = {name: convert(values[name]) for name, convert, _ in VOICE_PARAMETERS}
		voices = self._voices()
		if spec.name not in voices:
			voices[spec.name] = {}
		for name, value in converted.items():
			voices[spec.name][name] = value
