"""Immutable values shared across settings, playback and scheduling."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum


VoiceKey = str
SettingValue = int | str | bool
VoiceValues = dict[str, SettingValue]
SourceId = object
SpeechCommands = tuple[object, ...]


@dataclass(frozen=True)
class VoiceSpec:
	id: str
	name: str
	description: str
	language: str
	engine: str
	locale: str


@dataclass(frozen=True)
class VoiceSnapshot:
	voice_id: str
	revision: int
	language: str
	rate: int
	pitch: int
	volume: int
	variant: str
	inflection: int
	rateBoost: bool
	waitfactor: int


@dataclass(frozen=True)
class SelectVoice:
	voice_key: str


@dataclass(frozen=True)
class Pause:
	seconds: float


@dataclass(frozen=True)
class PlaybackContext:
	source_id: object
	segment_id: int


class CompletionMode(Enum):
	LEGACY_DONE = "legacy_done"
	END_INDEX = "end_index"
	END_INDEX_AND_DRAIN = "end_index_and_drain"
	DRAIN = "drain"


@dataclass(frozen=True)
class IndexRange:
	minimum: int
	maximum: int

	def __post_init__(self):
		if not 1 <= self.minimum <= self.maximum:
			raise ValueError("Index range must satisfy 1 <= minimum <= maximum")


@dataclass(frozen=True)
class CompletionContract:
	"""Opting in certifies ordered indexes and the selected completion behavior."""

	mode: CompletionMode = CompletionMode.LEGACY_DONE
	index_range: IndexRange | None = None

	def __post_init__(self):
		if self.mode is CompletionMode.LEGACY_DONE:
			if self.index_range is not None:
				raise ValueError("Legacy completion cannot declare an index range")
		elif self.index_range is None:
			raise ValueError("Correlated completion requires an index range")


@dataclass(frozen=True)
class EngineCapabilities:
	settings: frozenset[str]
	supports_waitfactor: bool = False
	supports_variants: bool = False
	supports_cancellation_token: bool = False
	completion: CompletionContract = CompletionContract()


class EventKind(Enum):
	INDEX = "index"
	DONE = "done"
	SEGMENT_END = "segment_end"
	SEGMENT_DRAINED = "segment_drained"
	SEGMENT_FAILED = "segment_failed"


@dataclass(frozen=True)
class PlaybackEvent:
	kind: EventKind
	source_id: object
	index: int | None = None
	segment_id: int | None = None
	error: Exception | None = None


SegmentEventSink = Callable[[PlaybackEvent], None]
