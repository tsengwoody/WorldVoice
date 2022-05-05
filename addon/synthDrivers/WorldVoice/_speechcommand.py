from typing import Optional

try:
	from speech import SynthCommand, SynthParamCommand
except BaseException:
	from speech.commands import SynthCommand, SynthParamCommand


class WVLangChangeCommand(SynthParamCommand):
	"""A command to switch the language within speech."""

	def __init__(self, lang: Optional[str]):
		"""
		@param lang: the language to switch to: If None then the NVDA locale will be used.
		"""
		self.lang = lang
		self.isDefault = not lang

	def __repr__(self):
		return "WVLangChangeCommand (%r)" % self.lang


class SplitCommand(SynthCommand):
	"""Insert a split command when text exceed max length.
	"""

	def __repr__(self):
		return "SplitCommand()"
