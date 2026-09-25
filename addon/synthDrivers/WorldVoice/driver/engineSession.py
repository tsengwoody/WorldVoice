from dataclasses import dataclass
from typing import Callable


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


class EngineSession:
    def __init__(self, core):
        self.core = core
        self.invalidate()

    def invalidate(self):
        self._applied_core = None
        self._applied_voice = None
        self._applied_revision = None

    def replace_core(self, core):
        self.core = core
        self.invalidate()

    def activate(self, snapshot: VoiceSnapshot, apply_engine: Callable) -> bool:
        if (self._applied_core is self.core
                and self._applied_voice == snapshot.voice_id
                and self._applied_revision == snapshot.revision):
            return False
        try:
            self.core.voice = snapshot.voice_id
            supported = {item.id for item in self.core.supportedSettings}
            for name in ("rateBoost", "rate", "pitch", "volume", "inflection"):
                if name in supported:
                    setattr(self.core, name, getattr(snapshot, name))
            apply_engine(self.core, snapshot)
        except Exception:
            self.invalidate()
            raise
        self._applied_core = self.core
        self._applied_voice = snapshot.voice_id
        self._applied_revision = snapshot.revision
        return True
