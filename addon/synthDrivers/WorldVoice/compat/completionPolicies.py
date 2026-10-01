"""Verified completion opt-ins require evidence for the exact runtime profile.

Keep this table empty until the engine/version/audio mode has documented
physical playback and ordered-index evidence. IndexCommand support alone
never establishes completion semantics or a safe integer range.

Supported custom wrappers use their explicit adapter/native drain contract.
This is separate from physical playback certification. No installed wrapper
profile is verified yet, so DRAIN for them is a forced activation controlled by
FORCE_UNVERIFIED_DRAIN; turning it off restores LEGACY_DONE for every one.
"""

from inspect import signature
import sys

from ..runtime.models import CompletionContract, CompletionMode, IndexRange
from ..runtime.playbackWork import DrainSupport


_VERIFIED_CONTRACTS: dict[tuple[str, str, str], CompletionContract] = {}

# Forced activation of DRAIN on wrapper profiles without playback evidence.
# Read on every completion selection, so it applies to engines opened later.
FORCE_UNVERIFIED_DRAIN = True

# Single source for engines whose custom wrapper may report drain support.
DRAIN_ENGINES = frozenset({"OneCore", "Neural", "VE", "Cerence", "SAPI5", "Espeak", "RHVoice"})
# Engines whose drain support depends on the opened core's WASAPI setting.
_WASAPI_MODE_ENGINES = frozenset({"OneCore", "SAPI5"})
_DRAIN_CONTRACT = CompletionContract(CompletionMode.DRAIN, IndexRange(1, 9999))


def resolve_audio_mode(engine: str, core: object) -> str:
	"""Report the opened core's audio path; only explicit booleans are trusted."""
	if engine not in _WASAPI_MODE_ENGINES:
		return "default"
	use_wasapi = getattr(core, "useWasapi", None)
	return "wasapi" if use_wasapi is True else "legacy" if use_wasapi is False else "unknown"


def get_completion_contract(
	engine: str,
	*,
	nvda_version: str,
	audio_mode: str,
	segment_drain_supported: bool = False,
) -> CompletionContract:
	# Unsupported target profiles must not select a different contract while a
	# segment is waiting for completion.
	if engine in DRAIN_ENGINES:
		return _DRAIN_CONTRACT if segment_drain_supported is True else CompletionContract()
	return _VERIFIED_CONTRACTS.get((engine, nvda_version, audio_mode), CompletionContract())


def get_segment_drain_support(
	voice_class: type,
	core: object,
	*,
	nvda_version: str,
	audio_mode: str,
) -> DrainSupport:
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
	if (
		not isinstance(driver, type)
		or driver.__module__ != module_name
		or getattr(voice_class, "synth_driver_class", None) is not driver
	):
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
	if support.supported and not FORCE_UNVERIFIED_DRAIN:
		return DrainSupport(
			False,
			support.profile,
			f"Unverified DRAIN is disabled by FORCE_UNVERIFIED_DRAIN: {support.reason}",
		)
	return support
