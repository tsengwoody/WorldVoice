from speech.commands import IndexCommand, SynthParamCommand


class WVLangChangeCommand(SynthParamCommand):
	"""A language switch that WorldVoice's own language detection inserts into speech.

	It derives from SynthParamCommand and must never derive from LangChangeCommand.
	NVDA drops every LangChangeCommand when its own automatic language switching is off
	(line numbers from ref/nvda 1406f9f8a):
	- speech.speak, after filter_speechSequence, unless shouldMakeLangChangeCommand()
	  (speech/speech.py:1178-1180; that is autoLanguageSwitching or reportLanguage,
	  speech/languageHandling.py:60-62);
	- SpeechManager._processSpeechSequence, unless shouldSwitchVoice()
	  (speech/manager.py:366-369).
	Detection timed "before" NVDA's processing runs as a filter_speechSequence handler,
	so its commands go through both checks; and installTasks turns autoLanguageSwitching off
	on first install, so in WorldVoice's default setup both checks drop LangChangeCommand.

	isDefault is the SynthParamCommand contract that ParamChangeTracker.update reads
	(speech/manager.py:95-105): a default value removes the command type from the
	tracker. Without it, the speech manager would replay the last switch at the start
	of every later utterance split from the same sequence.

	The pipeline still handles LangChangeCommand too, because NVDA keeps producing its
	own when reportLanguage or its automatic language switching is on.
	"""

	def __init__(self, lang: str | None):
		"""
		@param lang: the language to switch to: If None then the NVDA locale will be used.
		"""
		self.lang = lang
		self.isDefault = not lang

	def __repr__(self):
		return f"WVLangChangeCommand ({self.lang!r})"


class WorldVoiceIndexCommand(IndexCommand):
	"""Internal segment marker carried through the engine index boundary."""

	def __repr__(self):
		return f"WorldVoiceIndexCommand({self.index:d})"
