"""Locale to voice assignments ("speech roles") stored in the WorldVoice config."""

from collections.abc import Callable, Collection, Mapping
from typing import Any

from ..locales import primary_language


def prune_assignments(
	assignments: Mapping[str, str],
	available: Mapping[str, Collection[str]],
) -> dict[str, str]:
	"""Keep the assignments whose locale and voice are still available."""
	return {
		locale: voice
		for locale, voice in assignments.items()
		if locale in available and voice in available[locale]
	}


def _is_section(value: Any) -> bool:
	return isinstance(value, Mapping) or (hasattr(value, "items") and hasattr(value, "get"))


class ConfigRoleRepository:
	"""The only reader and writer of config["WorldVoice"]["role"]."""

	def __init__(self, conf_provider: Callable[[], Any]):
		self._conf_provider = conf_provider

	def _section(self) -> Any:
		return self._conf_provider()["WorldVoice"]["role"]

	def voice_for(self, language: str, usable: Callable[[str], bool] | None = None) -> str | None:
		"""The stored voice of language's full locale, else of its primary language.

		A locale whose voice usable rejects counts as unassigned, so the next locale is tried.
		"""
		section = self._section()
		for locale in (language, primary_language(language)):
			value = section.get(locale) if hasattr(section, "get") else None
			if _is_section(value):
				voice = value.get("voice")
				if voice and (usable is None or usable(voice)):
					return voice
		return None

	def assignments(self) -> dict[str, str]:
		result = {}
		for locale, value in self._section().items():
			if _is_section(value):
				voice = value.get("voice")
				if voice:
					result[locale] = voice
		return result

	def save(self, assignments: Mapping[str, str]) -> None:
		conf = self._conf_provider()
		kept = {
			locale: value for locale, value in conf["WorldVoice"]["role"].items() if not _is_section(value)
		}
		conf["WorldVoice"]["role"] = {
			**{locale: {"voice": voice} for locale, voice in assignments.items()},
			**kept,
		}

	def assign(self, locale: str, voice: str) -> None:
		self.save({**self.assignments(), locale: voice})

	def prune(self, available: Mapping[str, Collection[str]]) -> None:
		self.save(prune_assignments(self.assignments(), available))
