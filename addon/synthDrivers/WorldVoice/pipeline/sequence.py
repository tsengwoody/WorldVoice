"""The items of a speech sequence as the stages see them, and the checks several stages share."""

from typing import TYPE_CHECKING, Union

from speech.commands import ConfigProfileTriggerCommand, EndUtteranceCommand

if TYPE_CHECKING:
	from speech.commands import SpeechCommand

SpeechCmd = Union[str, "SpeechCommand"]


_MISSING = object()


def _both_text(previous: SpeechCmd, current: SpeechCmd) -> bool:
	return isinstance(previous, str) and isinstance(current, str)


def _ends_utterance(item: SpeechCmd) -> bool:
	"""Whether NVDA's speech manager ends the utterance at *item*, after the filters ran.

	It splits the sequence at an EndUtteranceCommand (speakSpelling puts one after every character,
	the speech of a text range one at the end of a block), and before a ConfigProfileTriggerCommand of a trigger with a
	profile; one without a profile counts too, as the pipeline cannot know.
	"""
	return isinstance(item, (EndUtteranceCommand, ConfigProfileTriggerCommand))
