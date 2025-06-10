import os

import globalVars
import languageHandler

from .driver import _ibmeci
from .driver.ibmeci import SynthDriver
from .. import Voice


class IBMVoice(Voice):
	core = None
	engine = "IBM"
	synth_driver_class = SynthDriver
	workspace = os.path.join(globalVars.appArgs.configPath, "WorldVoice-workspace", "IBM")

	def __init__(self, id, name, taskManager, language=None):
		self.name = name
		self.language = language if language else "unknown"

		super().__init__(id=id, taskManager=taskManager)

	def active(self):
		if self.core.voice != self.id:
			self.core.language = self.language
			super().active()

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
		if not cls.core:
			return result

		result = []

		for name in os.listdir(_ibmeci.ttsPath):
			if name.lower().endswith('.syn'):
				info = _ibmeci.langs[name.lower()[:3]]
				# o[str(info[0])] = VoiceInfo(str(info[0]), info[1], info[2])

				ID = info[0]
				name = info[1]
				language = info[2]
				langDescription = languageHandler.getLanguageDescription(language)
				result.append({
					"id": ID,
					"name": name,
					"locale": language,
					"language": language,
					"langDescription": langDescription,
					"description": "%s - %s" % (name, langDescription),
					"engine": "IBM",
				})
		return result
