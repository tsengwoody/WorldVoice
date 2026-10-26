"""Locale string helpers shared by the voice roles and the language detector.

This module imports nothing, so either side can use it without loading the other or any NVDA
module.
"""


def primary_language(locale: str) -> str:
	"""Return the lower-case primary language subtag of a locale like en_US or en-US.

	An empty locale (or None) is returned as it is.
	"""
	if not locale:
		return locale
	return locale.replace("-", "_").split("_", maxsplit=1)[0].lower()
