"""The language detection settings: the only reader and writer of their config keys.

They live in config["WorldVoice"]["autoLanguageSwitching"] beside the three
keepMainLocale* flags, which voices/mainLocalePolicy.py owns.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import config
from logHandler import log

from ..listeners import Listeners
from .scriptLanguages import DETECTION_SCRIPTS

# Each script of the table, then the timing, which is not a script.
DETECTION_CONFSPEC = {
	**{row.config_key: f"string(default={row.default_language})" for row in DETECTION_SCRIPTS},
	"detectLanguageTiming": "string(default=after)",
}
# The scripts whose assumed language the user chooses, and where each choice is stored.
SCRIPT_CONFIG_KEYS = {row.script: row.config_key for row in DETECTION_SCRIPTS}
_TIMING_KEY = "detectLanguageTiming"


@dataclass(frozen=True)
class DetectionSettings:
	"""One reading of the detection settings."""

	# Read-only; keyed by the script names of SCRIPT_CONFIG_KEYS.
	script_language: Mapping[str, str]
	# "before" or "after" NVDA processes speech commands, as stored.
	timing: str


DetectionListener = Callable[[DetectionSettings, frozenset[str]], None]


class DetectionSettingsService:
	"""Reads and writes the detection settings and tells subscribers what changed.

	Listeners receive the new settings and the names of the fields that changed.
	"""

	def __init__(self, conf_provider: Callable[[], Any]):
		self._conf_provider = conf_provider
		self._listeners = Listeners[[DetectionSettings, frozenset[str]]](
			log,
			"WorldVoice: detection settings listener failed",
		)

	def _section(self) -> Any:
		return self._conf_provider()["WorldVoice"]["autoLanguageSwitching"]

	def get(self) -> DetectionSettings:
		section = self._section()
		return DetectionSettings(
			script_language=MappingProxyType(
				{script: section[key] for script, key in SCRIPT_CONFIG_KEYS.items()},
			),
			timing=section[_TIMING_KEY],
		)

	def update(
		self,
		*,
		script_language: Mapping[str, str] | None = None,
		timing: str | None = None,
	) -> DetectionSettings:
		"""Store the given values; None leaves a field alone, script_language may name some scripts."""
		script_language = dict(script_language or {})
		unknown = set(script_language) - set(SCRIPT_CONFIG_KEYS)
		if unknown:
			raise KeyError(f"Unknown detection scripts: {sorted(unknown)}")
		current = self.get()
		writes = {}
		changed = set()
		for script, language in script_language.items():
			if language != current.script_language[script]:
				writes[SCRIPT_CONFIG_KEYS[script]] = language
				changed.add("script_language")
		if timing is not None and timing != current.timing:
			writes[_TIMING_KEY] = timing
			changed.add("timing")
		if not writes:
			return current
		section = self._section()
		for key, value in writes.items():
			section[key] = value
		settings = self.get()
		self._listeners.notify(settings, frozenset(changed))
		return settings

	def subscribe(self, listener: DetectionListener) -> None:
		self._listeners.subscribe(listener)

	def unsubscribe(self, listener: DetectionListener) -> None:
		self._listeners.unsubscribe(listener)


detection_settings = DetectionSettingsService(lambda: config.conf)
