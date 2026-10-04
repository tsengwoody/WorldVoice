"""The three "keep main locale consistent" options, each owning its config flag."""

from collections.abc import Callable, Mapping
from typing import Any

from .roles import getPrimaryLocale

PARAMETER_NAMES = ("rate", "pitch", "volume", "inflection", "rateBoost")


def _flags(conf_provider: Callable[[], Any]) -> Any:
	return conf_provider()["WorldVoice"]["autoLanguageSwitching"]


class EngineConsistency:
	"""KeepMainLocaleEngineConsistent: role choices come from the main voice's engine.

	``enabled`` is a pending value the settings panel previews; ``persist`` saves it.
	"""

	_KEY = "KeepMainLocaleEngineConsistent"

	def __init__(self, conf_provider: Callable[[], Any]):
		self._conf_provider = conf_provider
		self.enabled = bool(_flags(conf_provider)[self._KEY])

	def persist(self) -> None:
		_flags(self._conf_provider)[self._KEY] = self.enabled

	def visible(self, table, default_engine: str) -> list:
		if self.enabled:
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

	def shared_section(self, synth_name: Callable[[], str]) -> Mapping | None:
		"""The main synth's speech settings every voice loads from, or None."""
		if not self.enabled:
			return None
		try:
			return self._conf_provider()["speech"][synth_name()]
		except Exception:
			# Preserve the legacy fallback even during synth startup.
			return None
