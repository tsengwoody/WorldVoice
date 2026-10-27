"""The driver.Voice caller API, backed by one runtime settings store and session."""

from dataclasses import dataclass

from ..runtime.models import VoiceSpec
from ..runtime.session import EngineSession
from ..runtime.voiceSettings import VoiceSettingsStore


@dataclass(frozen=True)
class VoiceBinding:
	"""One opened engine's settings, playback session and core."""

	settings: VoiceSettingsStore
	session: EngineSession
	core: object


def _setting(name):
	def get(self):
		return self._state.get(name)

	def set(self, value):
		self._state.update(**{name: value})

	return property(get, set)


class VoiceFacade:
	def __init__(self, spec: VoiceSpec, binding: VoiceBinding):
		self._binding = binding
		self._state = binding.settings.ensure(spec)
		self.id = self._state.spec.id
		self.name = self._state.spec.name
		self.language = self._state.spec.language

	@property
	def core(self):
		return self._binding.core

	rate = _setting("rate")
	pitch = _setting("pitch")
	volume = _setting("volume")
	variant = _setting("variant")
	inflection = _setting("inflection")
	rateBoost = _setting("rateBoost")
	waitfactor = _setting("waitfactor")

	def snapshot(self):
		return self._state.snapshot()

	def update_settings(self, **values):
		self._state.update(**values)

	def loadParameter(self):
		self._binding.settings.reload(self.name)

	def commit(self):
		self._binding.settings.commit(self.name)

	def stop(self):
		self._binding.session.cancel()
