"""The stage table: the filter stages in NVDA's order, each run with the settings and context of the
synth that speaks and logged on request, and registered with NVDA's filter_speechSequence as one set.

Here too are the two stages too small for a module of their own (apply_speech_dictionaries and
speech_viewer), and listable, with which the synth makes language detection a filter.
"""

import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING

import config
import speechDictHandler
from logHandler import log
from speech.extensions import filter_speechSequence

from . import speechDictionary
from .breaks import _plain_breaks
from .context import SpeechContext, current_context
from .items import item_wait_factor
from .numberStages import inject_numbers, number_wait_factor, remove_thousands_separators
from .punctuation import inject_punctuation_pause
from .recorder import PipelineLog
from .sequence import SpeechCmd
from .settings import pipeline_settings, read_stored, stored_key_for
from .unspaced import inject_unspaced_script_space_pause

if TYPE_CHECKING:
	from .settings import PipelineSettings

# The pipeline log is addon/log/pipeline.csv; parents[3] of a module in pipeline/ is addon/.
pl = PipelineLog(Path(__file__).resolve().parents[3] / "log" / "pipeline.csv")


def listable(func):
	@wraps(func)
	def wrapper(speech_sequence):
		speech_sequence = list(speech_sequence)
		speech_sequence = func(speech_sequence)
		speech_sequence = list(speech_sequence)
		return speech_sequence

	return wrapper


def speech_viewer(speech_sequence, settings: "PipelineSettings", ctx: SpeechContext):
	return list(speech_sequence)


def apply_speech_dictionaries(speech_sequence, settings: "PipelineSettings", ctx: SpeechContext):
	for item in speech_sequence:
		if isinstance(item, str):
			yield speechDictHandler.processText(item)
		else:
			yield item


class _LogWriter:
	"""Write pipeline log rows without letting a failed write reach NVDA's filter.

	NVDA's Filter.apply keeps the input after an exception, and a logged stage has read that
	generator already, so a raised write would leave the rest of the pipeline nothing to speak.
	The first failure of an outage is logged; the next successful write ends the outage.
	"""

	def __init__(self):
		self._failing = False

	def write(self, *row):
		try:
			pl.write(*row)
		except Exception:
			# A full disk raises OSError; a command whose repr cannot be encoded, ValueError.
			if not self._failing:
				log.error("WorldVoice could not write its pipeline log", exc_info=True)
			self._failing = True
		else:
			self._failing = False


_log_writer = _LogWriter()


def _run_logged(label, fn, speech_sequence, settings, ctx, switches=None):
	"""Run one stage, logged under *label* when debugging or recording and any of *switches* (stored
	keys of the log section; by default the switch of *label*) is on."""
	debug = config.conf["general"]["loggingLevel"] == "DEBUG"
	section = config.conf["WorldVoice"]["log"]
	# A switch NVDA refuses on read is off, so a bad stored value never stops the stage.
	recording = read_stored(section, "enable", False)
	switched_on = any(read_stored(section, key, False) for key in switches or (stored_key_for(label),))
	if not ((debug or recording) and switched_on):
		return fn(speech_sequence, settings, ctx)
	_id = uuid.uuid4().hex
	speech_sequence = list(speech_sequence)
	if debug:
		log.debug(f"speech sequence before {label} pipeline: {speech_sequence}")
	if recording:
		_log_writer.write(_id, label, "before", speech_sequence)
	speech_sequence = list(fn(speech_sequence, settings, ctx))
	if debug:
		log.debug(f"speech sequence after {label} pipeline: {speech_sequence}")
	if recording:
		_log_writer.write(_id, label, "after", speech_sequence)
	return speech_sequence


def _stage_handler(log_key, fn, switches):
	def handler(speech_sequence):
		ctx = current_context()
		settings = pipeline_settings.effective(ctx.supports_roles)
		result = _run_logged(log_key, fn, speech_sequence, settings, ctx, switches)
		# Only WorldVoice tells the pauses apart; another synth gets plain breaks.
		return result if ctx.supports_roles else _plain_breaks(result)

	# Not functools.wraps: NVDA binds filter values against inspect.signature,
	# which would follow __wrapped__ to the three-argument stage function.
	handler.__name__ = handler.__qualname__ = fn.__name__
	handler.__doc__ = fn.__doc__
	return handler


@dataclass(frozen=True)
class Stage:
	"""One speech-sequence filter. Its handler is bound once, so NVDA's weak registry keeps it."""

	log_key: str
	fn: Callable[..., Iterable[SpeechCmd]]
	# False: the stage logs under the switch of a later stage with the same log key.
	log_switch: bool = True
	# The switches that also turn this stage's log on; its rows still carry its log key.
	also_logged_by: tuple[str, ...] = ()
	handler: Callable[[Iterable[SpeechCmd]], Iterable[SpeechCmd]] = field(
		init=False,
		repr=False,
		compare=False,
	)

	def __post_init__(self):
		switches = tuple(stored_key_for(key) for key in (*self.also_logged_by, self.log_key))
		object.__setattr__(self, "handler", _stage_handler(self.log_key, self.fn, switches))


# The order NVDA runs the filters in; register, reorder and the log switches derive from it.
STAGES: tuple[Stage, ...] = (
	Stage("apply_speech_dictionaries", apply_speech_dictionaries),
	Stage("number_mode", remove_thousands_separators, log_switch=False),
	Stage("number_mode", inject_numbers, also_logged_by=("number_language",)),
	Stage("unspaced_script_space_wait_factor", inject_unspaced_script_space_pause),
	Stage("item_wait_factor", item_wait_factor),
	Stage("punctuation_wait_factor", inject_punctuation_pause),
	Stage("number_wait_factor", number_wait_factor),
	Stage("speech_viewer", speech_viewer),
)


def _log_switches(stages: Iterable[Stage]) -> tuple[str, ...]:
	"""Each switch of the stages with a switch of their own once: its also_logged_by keys, then its log
	key, each as the key nvda.ini stores the switch under (NVDA camelCase)."""
	keys = (key for stage in stages if stage.log_switch for key in (*stage.also_logged_by, stage.log_key))
	return tuple(dict.fromkeys(stored_key_for(key) for key in keys))


# One log switch per log key, in the order of the stage that owns it; rows and debug lines keep the log key.
LOG_SWITCHES: tuple[str, ...] = _log_switches(STAGES)


def order_move_to_start_register():
	# Move to the front in reverse, so STAGES runs first and in order.
	for stage in reversed(STAGES):
		filter_speechSequence.moveToEnd(stage.handler, False)


def register_stages():
	log.debug("register pipeline stages")
	speechDictionary.install()
	for stage in STAGES:
		filter_speechSequence.register(stage.handler)
	order_move_to_start_register()


def unregister_stages():
	log.debug("unregister pipeline stages")
	for stage in STAGES:
		filter_speechSequence.unregister(stage.handler)
	speechDictionary.uninstall()
