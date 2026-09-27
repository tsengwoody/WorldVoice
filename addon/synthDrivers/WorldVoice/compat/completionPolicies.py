"""Completion opt-ins require verification of the exact runtime profile.

Keep this table empty until the engine/version/audio mode has documented
physical playback and ordered-index evidence. IndexCommand support alone
never establishes completion semantics or a safe integer range.
"""

from ..runtime.models import CompletionContract


_VERIFIED_CONTRACTS: dict[tuple[str, str, str], CompletionContract] = {}


def get_completion_contract(engine: str, *, nvda_version: str, audio_mode: str) -> CompletionContract:
    return _VERIFIED_CONTRACTS.get((engine, nvda_version, audio_mode), CompletionContract())
