import languageHandler

from .driver import SynthDriver
from .. import Voice


class RHVoice(Voice):
	core = None
	engine = "RH"
	synth_driver_class = SynthDriver

	def __init__(self, id, name, taskManager, language=None):
		self.name = name
		self.language = language if language else "unknown"

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
		return True

	@classmethod
	def voices(cls):
		result = []
		for profile in cls.core.profiles:
			ID = name = profile
			language = cls.core.voice_languages[profile.split("+")[0]]
			langDescription = languageHandler.getLanguageDescription(language)
			result.append({
				"id": ID,
				"name": name,
				"locale": language,
				"language": language,
				"langDescription": langDescription,
				"description": "%s - %s" % (name, langDescription),
				"engine": "RH",
			})
		return result
