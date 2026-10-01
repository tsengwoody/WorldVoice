"""The existing NVDA config format, accessed through injected dependencies."""

from collections.abc import Callable, Mapping, MutableMapping

from .runtime.models import SettingValue, VoiceSpec, VoiceValues
from .runtime.settings import VOICE_PARAMETERS


class ConfigVoiceSettingsRepository:
	def __init__(self, conf: MutableMapping, synth_name: Callable[[], str]):
		self._conf = conf
		self._synth_name = synth_name

	def load(self, spec: VoiceSpec) -> VoiceValues:
		voices = self._conf["WorldVoice"]["voices"]
		values = {name: convert(default) for name, convert, default in VOICE_PARAMETERS}
		if spec.name not in voices:
			voices[spec.name] = values.copy()
		# Persist the legacy defaults, but load effective main-synth values on
		# first use too, before the shared state establishes its edit baseline.

		consistent = self._conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"]
		for name, convert, _ in VOICE_PARAMETERS:
			if consistent:
				try:
					value = self._conf["speech"][self._synth_name()].get(name, None)
				except Exception:
					# Preserve the legacy fallback even during synth startup.
					value = voices[spec.name].get(name, None)
			else:
				value = voices[spec.name].get(name, None)
			if value is not None:
				values[name] = convert(value)
		return values

	def save(self, spec: VoiceSpec, values: Mapping[str, SettingValue]) -> None:
		converted = {name: convert(values[name]) for name, convert, _ in VOICE_PARAMETERS}
		voices = self._conf["WorldVoice"]["voices"]
		if spec.name not in voices:
			voices[spec.name] = {}
		for name, value in converted.items():
			voices[spec.name][name] = value
