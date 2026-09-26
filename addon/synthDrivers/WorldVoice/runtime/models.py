"""Immutable values shared across settings, playback and scheduling."""

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
class EngineCapabilities:
    settings: frozenset[str]
    supports_waitfactor: bool = False
    supports_variants: bool = False
    supports_cancellation_token: bool = False


class EventKind(Enum):
    INDEX = "index"
    DONE = "done"


@dataclass(frozen=True)
class PlaybackEvent:
    kind: EventKind
    source_id: object
    index: int | None = None
