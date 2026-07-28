from functools import wraps
from typing import Any, Callable

import globalVars
import speech


_original_process_text: Callable[..., Any] | None = None
_wrapped_process_text: Callable[..., Any] | None = None


def install() -> None:
	global _original_process_text, _wrapped_process_text

	if _wrapped_process_text is not None:
		return

	original_process_text = speech.speech.processText
	_original_process_text = original_process_text

	@wraps(original_process_text)
	def process_text_without_dictionaries(*args, **kwargs):
		previous = globalVars.speechDictionaryProcessing
		globalVars.speechDictionaryProcessing = False
		try:
			return original_process_text(*args, **kwargs)
		finally:
			globalVars.speechDictionaryProcessing = previous

	_wrapped_process_text = process_text_without_dictionaries
	speech.speech.processText = _wrapped_process_text


def uninstall() -> None:
	global _original_process_text, _wrapped_process_text

	if _wrapped_process_text is None:
		return

	original_process_text = _original_process_text
	assert original_process_text is not None
	speech.speech.processText = original_process_text
	_original_process_text = None
	_wrapped_process_text = None
