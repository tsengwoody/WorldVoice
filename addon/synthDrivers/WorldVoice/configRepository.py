"""The existing NVDA config format, accessed through injected dependencies."""

from collections.abc import Callable, Mapping, MutableMapping

from .mainLocalePolicy import ParameterConsistency
from .runtime.models import SettingValue, VoiceSpec, VoiceValues
from .runtime.settings import PARAMETER_NAMES, VOICE_PARAMETERS, boolean


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
	def __init__(
		self,
		conf: MutableMapping,
		synth_name: str,
		parameters: ParameterConsistency | None = None,
		*,
		main_settings_ready: Callable[[], bool] = lambda: True,
	):
		"""``main_settings_ready`` tells whether voices may load the main synth's speech settings yet."""
		self._conf = conf
		self._synth_name = synth_name
		self._parameters = parameters or ParameterConsistency(lambda: conf)
		self._main_settings_ready = main_settings_ready

	def load(self, spec: VoiceSpec) -> VoiceValues:
		voices = self._conf["WorldVoice"]["voices"]
		values = {name: convert(default) for name, convert, default in VOICE_PARAMETERS}
		if spec.name not in voices:
			voices[spec.name] = values.copy()
		# Persist the legacy defaults, but load effective main-synth values on
		# first use too, before the shared state establishes its edit baseline.
		shared = self._parameters.shared_section(self._synth_name) if self._main_settings_ready() else None
		for name, convert, _ in VOICE_PARAMETERS:
			value = voices[spec.name].get(name, None)
			# Only the copyable parameters follow the main voice; the variant stays the voice's own.
			if shared is not None and name in PARAMETER_NAMES:
				try:
					value = shared.get(name, None)
				except Exception:  # noqa: BLE001 - an invalid main-synth value falls back to the voice's own
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
