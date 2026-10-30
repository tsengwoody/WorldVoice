"""The voice a speech engine switch picks (voice engine filter spec §3.3)."""

from collections.abc import Iterable

from ..locales import primary_language
from ..runtime.models import VoiceSpec


def _folded(locale: str) -> str:
	"""A locale with "-" read as "_" and case ignored: zh-TW, ZH_tw and zh_TW are one locale."""
	return locale.replace("-", "_").lower()


def pick_engine_voice(
	specs: Iterable[VoiceSpec],
	engine: str,
	language: str,
	role_voice: str | None,
) -> str:
	"""The voice of engine for language, in the order of specs.

	The role voice when it is a voice of engine; else the first voice whose language is language,
	ignoring case and "-" or "_"; else the first whose primary language is language's; else the
	engine's first voice. A voice without a language is matched only as that last fallback.
	Raises LookupError when engine has no voice.
	"""
	own = [spec for spec in specs if spec.engine == engine]
	if not own:
		raise LookupError(engine)
	if any(spec.name == role_voice for spec in own):
		return role_voice
	spoken = [spec for spec in own if spec.language]
	for spec in spoken:
		if _folded(spec.language) == _folded(language):
			return spec.name
	primary = primary_language(language)
	for spec in spoken:
		if primary_language(spec.language) == primary:
			return spec.name
	return own[0].name
