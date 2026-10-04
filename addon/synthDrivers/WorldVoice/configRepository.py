"""The existing NVDA config format, accessed through injected dependencies."""

from collections.abc import Callable, Mapping, MutableMapping

from .mainLocalePolicy import ParameterConsistency
from .runtime.models import SettingValue, VoiceSpec, VoiceValues
from .runtime.settings import VOICE_PARAMETERS


class ConfigVoiceSettingsRepository:
	def __init__(
		self,
		conf: MutableMapping,
		synth_name: Callable[[], str],
		parameters: ParameterConsistency | None = None,
	):
		self._conf = conf
		self._synth_name = synth_name
		self._parameters = parameters or ParameterConsistency(lambda: conf)

	def load(self, spec: VoiceSpec) -> VoiceValues:
		voices = self._conf["WorldVoice"]["voices"]
		values = {name: convert(default) for name, convert, default in VOICE_PARAMETERS}
		if spec.name not in voices:
			voices[spec.name] = values.copy()
		# Persist the legacy defaults, but load effective main-synth values on
		# first use too, before the shared state establishes its edit baseline.
		source = self._parameters.shared_section(self._synth_name)
		if source is None:
			source = voices[spec.name]
		for name, convert, _ in VOICE_PARAMETERS:
			value = source.get(name, None)
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
