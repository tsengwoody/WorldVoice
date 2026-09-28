"""Verified completion opt-ins require evidence for the exact runtime profile.

Keep this table empty until the engine/version/audio mode has documented
physical playback and ordered-index evidence. IndexCommand support alone
never establishes completion semantics or a safe integer range.

Supported custom wrappers use their explicit adapter/native drain contract.
This is separate from physical playback certification. The remaining three
built-in engines retain the unverified END_INDEX experiment on this branch.
"""

from inspect import signature
import sys

from ..runtime.models import CompletionContract, CompletionMode, IndexRange
from ..runtime.playbackWork import DrainSupport


_VERIFIED_CONTRACTS: dict[tuple[str, str, str], CompletionContract] = {}

# TEST ONLY: test/force-segment-end-index-all-engines. No hardware evidence.
# Remove this block and its branch below to restore verified-only index policy.
_TEST_ONLY_FORCE_END_INDEX_ENGINES = frozenset({"SAPI5", "Espeak", "RHVoice"})
_TEST_ONLY_END_INDEX_CONTRACT = CompletionContract(CompletionMode.END_INDEX, IndexRange(1, 9999))
_DRAIN_ENGINES = frozenset({"OneCore", "Neural", "VE", "Cerence"})
_DRAIN_CONTRACT = CompletionContract(CompletionMode.DRAIN, IndexRange(1, 9999))


def get_completion_contract(engine: str, *, nvda_version: str, audio_mode: str,
                            segment_drain_supported: bool = False) -> CompletionContract:
    # Unsupported target profiles must not fall through to the index experiment
    # or a different contract while a segment is waiting for completion.
    if engine in _DRAIN_ENGINES:
        return _DRAIN_CONTRACT if segment_drain_supported is True else CompletionContract()
    # Deliberately ignore NVDA version and audio mode for this test override.
    if engine in _TEST_ONLY_FORCE_END_INDEX_ENGINES:
        return _TEST_ONLY_END_INDEX_CONTRACT
    return _VERIFIED_CONTRACTS.get((engine, nvda_version, audio_mode), CompletionContract())


def get_segment_drain_support(voice_class: type, core: object, *,
                              nvda_version: str, audio_mode: str) -> DrainSupport:
    """Check the opened installed wrapper before composing its event binding.

    Method presence and engine names do not establish native compatibility.
    The loaded outer module must own both the actual Voice and its driver;
    only that driver's explicit DrainSupport decision can enable DRAIN.
    """
    module_name = __package__.rsplit(".", 1)[0] + ".driver." + voice_class.engine

    def unsupported(reason):
        return DrainSupport(False, module_name, reason)

    module = sys.modules.get(module_name)
    if module is None or getattr(module, "Voice", None) is not voice_class:
        return unsupported("The actual Voice is not the installed custom outer wrapper")
    driver = getattr(module, "SynthDriver", None)
    if (not isinstance(driver, type) or driver.__module__ != module_name
            or getattr(voice_class, "synth_driver_class", None) is not driver):
        return unsupported("Voice does not select the installed custom outer SynthDriver")
    if not isinstance(core, driver):
        return unsupported("The opened core is not the Voice's custom outer SynthDriver")
    entry = getattr(core, "speak_segment", None)
    if not callable(entry):
        return unsupported("The custom core has no callable speak_segment entry")
    try:
        signature(entry).bind((), object(), context=object(), on_event=object())
    except (TypeError, ValueError):
        return unsupported("speak_segment does not accept commands, token, context and on_event")
    check = getattr(core, "get_segment_drain_support", None)
    if not callable(check):
        return unsupported("The custom core has no callable get_segment_drain_support check")
    try:
        support = check(nvda_version=nvda_version, audio_mode=audio_mode)
    except Exception as error:
        return unsupported(f"Drain support inspection failed: {type(error).__name__}: {error}")
    if not isinstance(support, DrainSupport) or not isinstance(support.supported, bool):
        return unsupported("The wrapper did not return an explicit DrainSupport boolean decision")
    if not support.supported and not support.reason:
        return unsupported("The wrapper has no supported adapter/native drain profile")
    return support
