"""Thread-safe pending voice settings, independent of persistence and engines."""

from collections.abc import Mapping
from threading import RLock
from typing import Protocol

from .models import SettingValue, VoiceSnapshot, VoiceSpec, VoiceValues


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


class VoiceSettingsRepository(Protocol):
    def load(self, spec: VoiceSpec) -> VoiceValues: ...

    def save(self, spec: VoiceSpec, values: Mapping[str, SettingValue]) -> None: ...


class VoiceSettingsStore:
    """Own one shared state per voice, independently of playback resources."""

    def __init__(self, repository: VoiceSettingsRepository):
        self._repository = repository
        self._lock = RLock()
        self._states: dict[str, VoiceState] = {}
        self._edit: VoiceEditSession | None = None

    def ensure(self, spec: VoiceSpec) -> VoiceState:
        with self._lock:
            state = self._states.get(spec.name)
            if state is not None:
                if state.spec != spec:
                    raise ValueError(f"Conflicting metadata for voice {spec.name}")
                return state
            state = VoiceState(spec, self._repository.load(spec))
            self._states[spec.name] = state
            # The initial baseline also enrolls a late voice in the active edit.
            return state

    def state(self, key: str) -> VoiceState:
        with self._lock:
            return self._states[key]

    def keys(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._states)

    def snapshot(self, key: str) -> VoiceSnapshot:
        return self.state(key).snapshot()

    def commit(self, key: str) -> None:
        state = self.state(key)
        snapshot = state.snapshot()
        values = {name: getattr(snapshot, name) for name in _SETTING_NAMES}
        # Repository I/O must not block readers or newer pending edits.
        self._repository.save(state.spec, values)
        state.checkpoint(values)

    def rollback(self, key: str) -> None:
        self.state(key).rollback()

    def reload(self, key: str) -> None:
        state = self.state(key)
        values = self._repository.load(state.spec)
        with state._lock:
            state.update(**values)
            state.checkpoint()

    def begin_edit(self) -> "VoiceEditSession":
        with self._lock:
            if self._edit is not None:
                raise RuntimeError("A voice settings edit is already open")
            for state in self._states.values():
                state.checkpoint()
            self._edit = VoiceEditSession(self)
            return self._edit


class VoiceEditSession:
    """A shared cancel baseline; the UI chooses apply or discard before close."""

    def __init__(self, store: VoiceSettingsStore):
        self._store = store

    def _keys(self) -> tuple[str, ...]:
        with self._store._lock:
            if self._store._edit is not self:
                raise RuntimeError("This voice settings edit is closed")
            return self._store.keys()

    def apply(self) -> None:
        # Each successful save advances only that voice's baseline. Exceptions
        # leave the remaining pending values available for retry or discard.
        for key in self._keys():
            self._store.commit(key)

    def discard(self) -> None:
        for key in self._keys():
            self._store.rollback(key)

    def close(self) -> None:
        with self._store._lock:
            if self._store._edit is self:
                self._store._edit = None
