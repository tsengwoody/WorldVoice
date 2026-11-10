"""The items of a speech sequence as the stages see them, and the checks several stages share."""

from typing import TYPE_CHECKING, Union

from speech.commands import ConfigProfileTriggerCommand, EndUtteranceCommand

if TYPE_CHECKING:
	from speech.commands import SpeechCommand

SpeechCmd = Union[str, "SpeechCommand"]


_MISSING = object()


# Set by inject_numbers on the wrapper of a number at the start ("start") or end ("end") of its item, so
# the item and punctuation stages still see the item boundary on the other side of it: without the
# wrapper the two items would be adjacent texts (review I1 of fix/leading-punctuation-language, decided
# by the user, 2026-11-10, option b). NVDA's commands have no __slots__, and the synths never read it.
# A stage that reads two adjacent texts as an item boundary must read a marked wrapper as one too;
# tests/test_pipeline_stages.py test_a_number_at_an_item_edge_keeps_the_items_apart runs every stage.
_ITEM_EDGE_WRAPPER = "worldvoice_item_edge_wrapper"


def _mark_item_edge_wrapper(command: SpeechCmd, side: str) -> SpeechCmd:
	setattr(command, _ITEM_EDGE_WRAPPER, side)
	return command


def _opens_item(command: SpeechCmd) -> bool:
	"""Whether *command* is the wrapper that opens the number an item starts with."""
	return getattr(command, _ITEM_EDGE_WRAPPER, None) == "start"


def _closes_item(command: SpeechCmd) -> bool:
	"""Whether *command* is the wrapper that closes the number an item ends with."""
	return getattr(command, _ITEM_EDGE_WRAPPER, None) == "end"


def _both_text(previous: SpeechCmd, current: SpeechCmd) -> bool:
	return isinstance(previous, str) and isinstance(current, str)


def _ends_utterance(item: SpeechCmd) -> bool:
	"""Whether NVDA's speech manager ends the utterance at *item*, after the filters ran.

	It splits the sequence at an EndUtteranceCommand (speakSpelling puts one after every character,
	the speech of a text range one at the end of a block), and before a ConfigProfileTriggerCommand of a trigger with a
	profile; one without a profile counts too, as the pipeline cannot know.
	"""
	return isinstance(item, (EndUtteranceCommand, ConfigProfileTriggerCommand))
