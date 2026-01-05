import os

import languageHandler

from .driver import EspeakSynthDriver as SynthDriver
# from .driver import SynthDriver
from synthDrivers import _espeak
# from .driver import _espeak
from .. import Voice


class EspeakVoice(Voice):
	core = None
	engine = "Espeak"
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
		return [{
			"id": id,
			"name": name,
		} for id, name in self.core._variantDict.items()]

	@property
	def variant(self):
		return self._variant

	@variant.setter
	def variant(self, value):
		self._variant = value
		self.core.variant = self._variant

	@classmethod
	def ready(cls):
		return True

	@classmethod
	def voices(cls):
		result = []
		if not cls.core:
			return result

		for v in _espeak.getVoiceList():
			l = _espeak.decodeEspeakString(v.languages[1:])  # noqa: E741
			# #7167: Some languages names contain unicode characters EG: Norwegian Bokmål
			name = _espeak.decodeEspeakString(v.name)
			# #5783: For backwards compatibility, voice identifies should always be lowercase
			identifier = os.path.basename(_espeak.decodeEspeakString(v.identifier)).lower()

			ID = identifier
			language = l.split("-")[0]
			langDescription = languageHandler.getLanguageDescription(language)
			langDescription = langDescription if langDescription else l
			result.append({
				"id": ID,
				"name": name,
				"locale": language,
				"language": language,
				"langDescription": langDescription,
				"description": "%s - %s" % (name, langDescription),
				"engine": "Espeak",
			})
		return result
