from collections.abc import Callable
from functools import wraps

import globalVars
import speech

from ..assembly import patch_attribute

_restore: Callable[[], None] | None = None


def install() -> None:
	global _restore

	if _restore is not None:
		return

	original_process_text = speech.speech.processText

	@wraps(original_process_text)
	def process_text_without_dictionaries(*args, **kwargs):
		previous = globalVars.speechDictionaryProcessing
		globalVars.speechDictionaryProcessing = False
		try:
			return original_process_text(*args, **kwargs)
		finally:
			globalVars.speechDictionaryProcessing = previous

	_restore = patch_attribute(speech.speech, "processText", process_text_without_dictionaries)


def uninstall() -> None:
	global _restore

	if _restore is None:
		return

	restore, _restore = _restore, None
	restore()
