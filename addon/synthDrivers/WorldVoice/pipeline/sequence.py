"""The items of a speech sequence as the stages see them, and the checks several stages share."""

from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
	from speech.commands import SpeechCommand

SpeechCmd = Union[str, "SpeechCommand"]


_MISSING = object()


def _both_text(previous: SpeechCmd, current: SpeechCmd) -> bool:
	return isinstance(previous, str) and isinstance(current, str)
