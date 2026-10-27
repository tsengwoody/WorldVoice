"""The existing NVDA config format, accessed through injected dependencies."""

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
# directly), so values come back as stored strings and VOICE_PARAMETERS converts them; this spec
# documents the stored keys, and every value save writes satisfies it.
VOICE_CONFSPEC = {name: _confspec(convert, default) for name, convert, default in VOICE_PARAMETERS}


class ConfigVoiceSettingsRepository:
	"""Each voice's own values in WorldVoice.voices; what voices inherit is decided elsewhere."""

	def __init__(self, conf_provider: Callable[[], MutableMapping]):
		self._conf_provider = conf_provider

	def _voices(self) -> MutableMapping:
		return self._conf_provider()["WorldVoice"]["voices"]

	def load(self, spec: VoiceSpec) -> VoiceValues:
		voices = self._voices()
		values = {name: convert(default) for name, convert, default in VOICE_PARAMETERS}
		if spec.name not in voices:
			voices[spec.name] = values.copy()
		for name, convert, _ in VOICE_PARAMETERS:
			value = voices[spec.name].get(name, None)
			if value is not None:
				values[name] = convert(value)
		return values

	def save(self, spec: VoiceSpec, values: Mapping[str, SettingValue]) -> None:
		converted = {name: convert(values[name]) for name, convert, _ in VOICE_PARAMETERS}
		voices = self._voices()
		if spec.name not in voices:
			voices[spec.name] = {}
		for name, value in converted.items():
			voices[spec.name][name] = value
