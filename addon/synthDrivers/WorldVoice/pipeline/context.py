from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from synthDriverHandler import getSynth


@dataclass(frozen=True)
class SpeechContext:
	"""What a pipeline stage may know about the synthesizer that speaks."""

	supports_roles: bool
	language: str | None
	number_language: str
	speech_symbols: Any = None
	default_voice: Any = None
	voice_name_for_language: Callable[[str], str | None] = lambda language: None


GENERIC_CONTEXT = SpeechContext(supports_roles=False, language=None, number_language="Windows")


def current_context() -> SpeechContext:
	try:
		synth = getSynth()
	except Exception:  # noqa: BLE001 - no synth yet: use the generic context
		return GENERIC_CONTEXT
	if getattr(synth, "name", None) != "WorldVoice":
		return GENERIC_CONTEXT
	return synth.speech_context()
