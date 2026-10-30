"""The three "keep main locale consistent" options, each owning its config flag."""

from collections.abc import Callable
from typing import Any

from ..locales import primary_language
from ..runtime.voiceSettings import PARAMETER_NAMES


def _flags(conf_provider: Callable[[], Any]) -> Any:
	return conf_provider()["WorldVoice"]["autoLanguageSwitching"]


class EngineConsistency:
	"""keepMainLocaleEngineConsistent: role choices come from the main voice's engine.

	Only the main voice's engine's roles speak (``admits``); other engines' roles stay stored.
	``enabled`` is the saved flag; ``preview`` is a settings panel's unsaved choice,
	which the visible voice list follows until it is cleared.
	"""

	_KEY = "keepMainLocaleEngineConsistent"

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

	def admits(self, engine: str, default_engine: str) -> bool:
		"""Whether a role voice of engine speaks beside a main voice of default_engine (saved flag)."""
		return not self.enabled or engine == default_engine


class VoiceConsistency:
	"""keepMainLocaleVoiceConsistent: the main locale's role follows the main voice."""

	_KEY = "keepMainLocaleVoiceConsistent"

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
		return primary_language(voice.language or self._language())

	def follow(self, voice) -> None:
		if self.enabled:
			self._roles.assign(self.main_locale(voice), voice.name)


class ParameterConsistency:
	"""keepMainLocaleParameterConsistent: every voice speaks with the main voice's parameters."""

	_KEY = "keepMainLocaleParameterConsistent"

	def __init__(self, conf_provider: Callable[[], Any]):
		self._conf_provider = conf_provider

	@property
	def enabled(self) -> bool:
		return bool(_flags(self._conf_provider)[self._KEY])

	@enabled.setter
	def enabled(self, value: bool) -> None:
		_flags(self._conf_provider)[self._KEY] = value

	def values_of(self, store, base_name: str) -> dict:
		"""The main voice's parameters every voice follows: all but the variant."""
		base = store.snapshot(base_name)
		return {name: getattr(base, name) for name in PARAMETER_NAMES}

	def inherited(self, store, base_name: str) -> dict:
		"""What a voice takes from the main voice when it loads: nothing unless enabled."""
		return self.values_of(store, base_name) if self.enabled else {}

	def copy_from(self, store, base_name: str) -> None:
		values = self.values_of(store, base_name)
		for key in store.names():
			# One update per voice keeps each copy atomic for a worker activation.
			store.state(key).update(**values)
