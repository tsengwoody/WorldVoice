"""The three "keep main locale consistent" options, each owning its config flag."""

from collections.abc import Callable, Mapping
from typing import Any

from .roles import getPrimaryLocale
from .runtime.settings import PARAMETER_NAMES


def _flags(conf_provider: Callable[[], Any]) -> Any:
	return conf_provider()["WorldVoice"]["autoLanguageSwitching"]


class EngineConsistency:
	"""KeepMainLocaleEngineConsistent: role choices come from the main voice's engine.

	``enabled`` is the saved flag; ``preview`` is a settings panel's unsaved choice,
	which the visible voice list follows until it is cleared.
	"""

	_KEY = "KeepMainLocaleEngineConsistent"

	def __init__(self, conf_provider: Callable[[], Any]):
		self._conf_provider = conf_provider
		self.preview: bool | None = None

	@property
	def enabled(self) -> bool:
		return bool(_flags(self._conf_provider)[self._KEY])

	@enabled.setter
	def enabled(self, value: bool) -> None:
		_flags(self._conf_provider)[self._KEY] = value

	def visible(self, table, default_engine: str) -> list:
		active = self.enabled if self.preview is None else self.preview
		if active:
			return [voice for voice in table if voice.engine == default_engine]
		return list(table)


class VoiceConsistency:
	"""KeepMainLocaleVoiceConsistent: the main locale's role follows the main voice."""

	_KEY = "KeepMainLocaleVoiceConsistent"

	def __init__(self, conf_provider: Callable[[], Any], roles, language: Callable[[], str]):
		self._conf_provider = conf_provider
		self._roles = roles
		self._language = language

	@property
	def enabled(self) -> bool:
		return bool(_flags(self._conf_provider)[self._KEY])

	@enabled.setter
	def enabled(self, value: bool) -> None:
		_flags(self._conf_provider)[self._KEY] = value

	def main_locale(self, voice) -> str:
		return getPrimaryLocale(voice.language or self._language())

	def follow(self, voice) -> None:
		if self.enabled:
			self._roles.assign(self.main_locale(voice), voice.name)


class ParameterConsistency:
	"""KeepMainLocaleParameterConsistent: every voice speaks with the main voice's parameters."""

	_KEY = "KeepMainLocaleParameterConsistent"

	def __init__(self, conf_provider: Callable[[], Any]):
		self._conf_provider = conf_provider

	@property
	def enabled(self) -> bool:
		return bool(_flags(self._conf_provider)[self._KEY])

	@enabled.setter
	def enabled(self, value: bool) -> None:
		_flags(self._conf_provider)[self._KEY] = value

	def copy_from(self, store, base_name: str) -> None:
		base = store.snapshot(base_name)
		values = {name: getattr(base, name) for name in PARAMETER_NAMES}
		for key in store.keys():
			# One update per voice keeps each copy atomic for a worker activation.
			store.state(key).update(**values)

	def shared_section(self, synth_name: str) -> Mapping | None:
		"""The main synth's speech settings every voice loads from, or None.

		The section does not exist until NVDA first saves this synth's settings.
		"""
		if not self.enabled:
			return None
		speech = self._conf_provider().get("speech")
		return None if speech is None else speech.get(synth_name)
