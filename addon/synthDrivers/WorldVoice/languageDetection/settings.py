"""The language detection settings: the only reader and writer of their config keys.

They live in config["WorldVoice"]["autoLanguageSwitching"] beside the three
KeepMainLocale* flags, which mainLocalePolicy owns.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import config
from logHandler import log

DETECTION_CONFSPEC = {
	"ignoreNumbersInLanguageDetection": "boolean(default=false)",
	"latinCharactersLanguage": "string(default=en)",
	"CJKCharactersLanguage": "string(default=ja)",
	"arabicCharactersLanguage": "string(default=ar)",
	"DetectLanguageTiming": "string(default=after)",
}
# The scripts whose assumed language the user chooses, and where each choice is stored.
SCRIPT_CONFIG_KEYS = {
	"Latin": "latinCharactersLanguage",
	"Han": "CJKCharactersLanguage",
	"Arabic": "arabicCharactersLanguage",
}
_IGNORE_NUMBERS_KEY = "ignoreNumbersInLanguageDetection"
_TIMING_KEY = "DetectLanguageTiming"


@dataclass(frozen=True)
class DetectionSettings:
	"""One reading of the detection settings."""

	ignore_numbers: bool
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
		self._listeners: list[DetectionListener] = []

	def _section(self) -> Any:
		return self._conf_provider()["WorldVoice"]["autoLanguageSwitching"]

	def get(self) -> DetectionSettings:
		section = self._section()
		return DetectionSettings(
			ignore_numbers=bool(section[_IGNORE_NUMBERS_KEY]),
			script_language=MappingProxyType(
				{script: section[key] for script, key in SCRIPT_CONFIG_KEYS.items()}
			),
			timing=section[_TIMING_KEY],
		)

	def update(
		self,
		*,
		ignore_numbers: bool | None = None,
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
		if ignore_numbers is not None and ignore_numbers != current.ignore_numbers:
			writes[_IGNORE_NUMBERS_KEY] = ignore_numbers
			changed.add("ignore_numbers")
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
		for listener in tuple(self._listeners):
			try:
				listener(settings, frozenset(changed))
			except Exception:
				log.error("WorldVoice: detection settings listener failed", exc_info=True)
		return settings

	def subscribe(self, listener: DetectionListener) -> None:
		if listener not in self._listeners:
			self._listeners.append(listener)

	def unsubscribe(self, listener: DetectionListener) -> None:
		try:
			self._listeners.remove(listener)
		except ValueError:
			pass


detection_settings = DetectionSettingsService(lambda: config.conf)
