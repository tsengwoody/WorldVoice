import languageHandler
import winVersion

from .driver import SynthDriver
from .. import Voice


class OneCoreVoice(Voice):
	core = None
	engine = "OneCore"
	synth_driver_class = SynthDriver

	def __init__(self, id, name, taskManager, language=None):
		self.name = name
		self.language = language if language else "unknown"
		self.core.language = self.language

		super().__init__(id=id, taskManager=taskManager)

	@property
	def name(self):
		return self._name

	@name.setter
	def name(self, name):
		self._name = name

	@property
	def variants(self):
		self._variants = []
		return self._variants

	@property
	def variant(self):
		return self._variant

	@variant.setter
	def variant(self, value):
		self._variant = value

	@classmethod
	def ready(cls):
		return winVersion.getWinVer() >= winVersion.WIN10

	@classmethod
	def voices(cls):
		result = []
		if not cls.ready() or not cls.core:
			return result
		# Fetch the full list of voices that OneCore speech knows about.
		# Note that it may give back voices that are uninstalled or broken.
		# Refer to _isVoiceValid for information on uninstalled or broken voices.
		voicesStr = cls.core._dll.ocSpeech_getVoices(cls.core._ocSpeechToken).split("|")
		for index, voiceStr in enumerate(voicesStr):
			ID, language, name = voiceStr.split(":")
			language = language.replace("-", "_")
			# Filter out any invalid voices.
			if not cls.core._isVoiceValid(ID):
				continue

			langDescription = languageHandler.getLanguageDescription(language)
			result.append({
				"id": ID,
				"name": name,
				"locale": language,
				"language": language,
				"langDescription": langDescription,
				"description": "%s - %s" % (name, langDescription),
				"engine": "OneCore",
			})
		return result
