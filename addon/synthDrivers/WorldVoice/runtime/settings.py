"""Thread-safe pending voice settings, independent of persistence and engines."""

from collections.abc import Mapping
from threading import RLock

from .models import SettingValue, VoiceSnapshot, VoiceSpec


def boolean(value):
    """Preserve the existing voice configuration's boolean conversion."""
    if isinstance(value, str):
        return value not in ("False", "false")
    return bool(value)


VOICE_PARAMETERS = (
    ("rate", int, 50),
    ("pitch", int, 50),
    ("volume", int, 50),
    ("variant", str, "default"),
    ("inflection", int, 50),
    ("rateBoost", boolean, False),
)

_SETTING_NAMES = frozenset(name for name, _, _ in VOICE_PARAMETERS) | {"waitfactor"}


def _validate_names(values: Mapping[str, SettingValue]) -> None:
    if set(values) - _SETTING_NAMES:
        raise ValueError("Unknown voice setting")


class VoiceState:
    def __init__(self, spec: VoiceSpec, values: Mapping[str, SettingValue]):
        values = dict(values)
        _validate_names(values)
        self.spec = spec
        self._lock = RLock()
        self._values = {name: default for name, _, default in VOICE_PARAMETERS}
        self._values["waitfactor"] = 0
        self._values.update(values)
        self._baseline = self._values.copy()
        self._revision = 0

    def get(self, name: str) -> SettingValue:
        with self._lock:
            return self._values[name]

    def update(self, **values: SettingValue) -> None:
        _validate_names(values)
        with self._lock:
            for name, value in values.items():
                if self._values[name] != value:
                    self._values[name] = value
                    self._revision += 1

    def snapshot(self) -> VoiceSnapshot:
        with self._lock:
            return VoiceSnapshot(
                voice_id=self.spec.id,
                revision=self._revision,
                language=self.spec.language,
                **self._values,
            )

    def checkpoint(self, values: Mapping[str, SettingValue] | None = None) -> None:
        """Advance the rollback baseline without overwriting pending edits.

        Explicit values can describe an earlier successfully saved snapshot.
        Omitted fields retain their existing baseline.
        """
        if values is not None:
            values = dict(values)
            _validate_names(values)
        with self._lock:
            if values is None:
                self._baseline = self._values.copy()
            else:
                self._baseline.update(values)

    def rollback(self) -> None:
        with self._lock:
            self.update(**self._baseline)

    def baseline(self, name: str) -> SettingValue:
        with self._lock:
            return self._baseline[name]
