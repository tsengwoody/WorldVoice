"""Translate legacy engine hooks into the independent runtime contract."""

from collections.abc import Callable, Mapping

from ..runtime.models import EngineCapabilities, SpeechCommands, VoiceSnapshot, VoiceSpec
from ..runtime.session import CancellationView


class LegacyEngineAdapter:
    def __init__(self, voice_class: type, resolve_voice: Callable[[str], object], *,
                 is_source_owned: Callable[[object], bool] | None = None):
        self._voice_class = voice_class
        self._resolve_voice = resolve_voice
        self._is_source_owned = is_source_owned
        self._opened = False
        self._core = None
        self.notification_source = None

    def open(self) -> None:
        if self._opened:
            return
        # Claim cleanup before engineOn: it may acquire a core then raise.
        self._opened = True
        try:
            self._voice_class.engineOn()
            self._core = self._voice_class.core
            self.notification_source = self._core
        except Exception as error:
            try:
                source = getattr(self._voice_class, "core", None)
                if self._is_source_owned is not None and self._is_source_owned(source):
                    # engineOn may expose an existing owner's resource before
                    # failing. This alias must not release that owner's core.
                    self.detach_alias()
                else:
                    self.close()
            except Exception as cleanup_error:
                raise error from cleanup_error
            raise

    def close(self) -> None:
        if not self._opened:
            return
        self._opened = False
        try:
            self._voice_class.engineOff()
        finally:
            self._core = None
            self.notification_source = None

    def detach_alias(self) -> None:
        """Relinquish a duplicate adapter without releasing the owner's core."""
        self._opened = False
        self._core = None
        self.notification_source = None
        self._voice_class.core = None
        self._voice_class.session = None
        self._voice_class._runtime_binding = None

    @property
    def capabilities(self) -> EngineCapabilities:
        extra = getattr(self._voice_class, "extra_capabilities", frozenset())
        return EngineCapabilities(
            settings=frozenset(self._voice_class.supportedSettings()),
            supports_waitfactor="waitfactor" in extra,
            supports_variants="variant" in extra,
            supports_cancellation_token=bool(getattr(self._core, "supportsCancellationToken", False)),
        )

    def list_voices(self) -> tuple[VoiceSpec, ...]:
        return tuple(VoiceSpec(
            id=voice["id"], name=voice["name"], description=voice["description"],
            language=voice["language"], engine=voice["engine"], locale=voice["locale"],
        ) for voice in self._voice_class.voices())

    def variants(self, key: str) -> tuple[Mapping[str, str], ...]:
        return tuple(self._resolve_voice(key).variants)

    def apply(self, spec: VoiceSpec, snapshot: VoiceSnapshot) -> None:
        core = self._core
        core.voice = spec.id
        supported = self.capabilities.settings
        for name in ("rateBoost", "rate", "pitch", "volume", "inflection"):
            if name in supported:
                setattr(core, name, getattr(snapshot, name))
        self._resolve_voice(spec.name).applyEngineSettings(core, snapshot)

    def speak(self, commands: SpeechCommands, token: CancellationView) -> None:
        if self.capabilities.supports_cancellation_token:
            self._core.speak(commands, cancellationToken=token)
        else:
            self._core.speak(commands)

    def cancel(self) -> None:
        self._core.cancel()

    def pause(self, switch: bool) -> None:
        self._core.pause(switch)
