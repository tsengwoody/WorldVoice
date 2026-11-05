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

# The bounds load clamps an int parameter to, as the confspec above states them.
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
		"""*value* converted like pipeline's convert: an int clamped to its bounds without a log.

		A value the conversion refuses, such as "abc" or "50.0" for an int, gives the default, and
		each voice, key and stored value is reported once as a debug warning, like the pipeline's
		read_stored. Nothing is written back: the next save of the voice replaces the value.
		"""
		try:
			result = convert(value)
		except (TypeError, ValueError):
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
		if convert is int:
			return min(max(result, _INT_MIN), _INT_MAX)
		return result

	def save(self, spec: VoiceSpec, values: Mapping[str, SettingValue]) -> None:
		converted = {name: convert(values[name]) for name, convert, _ in VOICE_PARAMETERS}
		voices = self._voices()
		if spec.name not in voices:
			voices[spec.name] = {}
		for name, value in converted.items():
			voices[spec.name][name] = value
