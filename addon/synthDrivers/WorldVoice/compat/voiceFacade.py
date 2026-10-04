"""Legacy caller API backed by one runtime settings store and session."""

from dataclasses import dataclass

from ..runtime.models import VoiceSpec
from ..runtime.session import EngineSession
from ..runtime.settings import VoiceSettingsStore


@dataclass(frozen=True)
class LegacyVoiceBinding:
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


def _baseline(name):
	def get(self):
		return self._state.baseline(name)

	def set(self, value):
		self._state.checkpoint({name: value})

	return property(get, set)


class VoiceFacade:
	def __init__(self, spec: VoiceSpec, binding: LegacyVoiceBinding, taskManager):
		self._binding = binding
		self._state = binding.settings.ensure(spec)
		self.id = self._state.spec.id
		self.name = self._state.spec.name
		self.language = self._state.spec.language
		self.taskManager = taskManager

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

	commit_rate = _baseline("rate")
	commit_pitch = _baseline("pitch")
	commit_volume = _baseline("volume")
	commit_variant = _baseline("variant")
	commit_inflection = _baseline("inflection")
	commit_rateBoost = _baseline("rateBoost")

	@property
	def revision(self):
		return self._state.snapshot().revision

	def snapshot(self):
		return self._state.snapshot()

	def update_settings(self, **values):
		self._state.update(**values)

	def loadParameter(self):
		self._binding.settings.reload(self.name)

	def commit(self):
		self._binding.settings.commit(self.name)

	def rollback(self):
		self._binding.settings.rollback(self.name)

	def active(self):
		return self._binding.session.activate(self.name)

	def speak(self, text, request):
		self.taskManager.append_speech(request, self._binding.session, self.name, tuple(text))

	def breaks(self, sec, request):
		self.taskManager.append_break(request, sec)

	def stop(self):
		self._binding.session.cancel()

	def pause(self):
		self._binding.session.pause(True)

	def resume(self):
		self._binding.session.pause(False)

	def close(self):
		# Individual voices do not own the shared engine resource.
		pass
