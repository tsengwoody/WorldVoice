"""The segment pause (segment_wait_factor): a break after at most segment_length characters of text with
no other pause, so a long run is spoken in shorter pieces (spec feat/segment-pause §4.2)."""

from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING

from speech.commands import BreakCommand

from ..text.chunker import segment_cuts
from .breaks import SegmentBreakCommand
from .context import SpeechContext
from .sequence import SpeechCmd, _ends_utterance

if TYPE_CHECKING:
	from .settings import PipelineSettings


def inject_segment_pause(
	speech_sequence: Iterable[SpeechCmd],
	settings: "PipelineSettings",
	ctx: SpeechContext,
) -> Iterator[SpeechCmd]:
	"""Cut each run of *speech_sequence* where segment_cuts says, with one SegmentBreakCommand after
	each cut piece, before any command that follows it.

	A run is what lies between two breaks of any kind (0 ms included: in WorldVoice each one ends a
	segment) or utterance ends: the count restarts there, and not at a language, index or callback
	command (decided by orchestrator, O5). Commands keep their order and never count. A segment
	length or pause of 0 leaves the sequence alone, the same objects (decided by the user,
	2026-11-03, U3). The stage reads no context.
	"""
	length = settings.segment_length
	pause = settings.scaled_segment_wait()
	if length <= 0 or pause <= 0:
		yield from speech_sequence
		return
	break_cmd = SegmentBreakCommand(pause)
	run: list[SpeechCmd] = []
	for item in speech_sequence:
		if isinstance(item, BreakCommand) or _ends_utterance(item):
			yield from _cut_run(run, length, break_cmd)
			run.clear()
			yield item
		else:
			run.append(item)
	yield from _cut_run(run, length, break_cmd)


def _cut_run(run: list[SpeechCmd], length: int, break_cmd: SpeechCmd) -> Iterator[SpeechCmd]:
	cuts: dict[int, list[int]] = {}
	for index, offset in segment_cuts([item for item in run if isinstance(item, str)], length):
		cuts.setdefault(index, []).append(offset)
	text_index = -1
	for item in run:
		if not isinstance(item, str):
			yield item
			continue
		text_index += 1
		offsets = cuts.get(text_index)
		if not offsets:
			yield item
			continue
		start = 0
		for offset in offsets:
			yield item[start:offset]
			yield break_cmd
			start = offset
		if start < len(item):
			yield item[start:]
