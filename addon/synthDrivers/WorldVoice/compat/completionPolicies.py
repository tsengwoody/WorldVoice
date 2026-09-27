"""Verified completion opt-ins require evidence for the exact runtime profile.

Keep this table empty until the engine/version/audio mode has documented
physical playback and ordered-index evidence. IndexCommand support alone
never establishes completion semantics or a safe integer range.

This test branch deliberately bypasses that policy for six built-in engines
via the separate, unverified override below. It is not production certification.
"""

from ..runtime.models import CompletionContract, CompletionMode, IndexRange


_VERIFIED_CONTRACTS: dict[tuple[str, str, str], CompletionContract] = {}

# TEST ONLY: test/force-segment-end-index-all-engines. No hardware evidence.
# Remove this block and the early return below to restore verified-only policy.
_TEST_ONLY_FORCE_END_INDEX_ENGINES = frozenset({"SAPI5", "OneCore", "Espeak", "VE", "Cerence", "RHVoice"})
_TEST_ONLY_END_INDEX_CONTRACT = CompletionContract(CompletionMode.END_INDEX, IndexRange(1, 9999))


def get_completion_contract(engine: str, *, nvda_version: str, audio_mode: str) -> CompletionContract:
    # Deliberately ignore NVDA version and audio mode for this test override.
    if engine in _TEST_ONLY_FORCE_END_INDEX_ENGINES:
        return _TEST_ONLY_END_INDEX_CONTRACT
    return _VERIFIED_CONTRACTS.get((engine, nvda_version, audio_mode), CompletionContract())
