import os

import languageHandler

from .driver import SynthDriver
from .driver import _espeak
from .. import Voice


class EspeakVoice(Voice):
	core = None
	engine = "Espeak"
	synth_driver_class = SynthDriver

	def __init__(self, id, name, taskManager, language=None):
		self.name = name
		self.language = language if language else "unknown"

		super().__init__(id=id, taskManager=taskManager)

	def active(self):
		if self.core.voice != self.id:
			self.core.voice = self.id
			self.core.pitch = self._pitch
			self.core.rate = self._rate
			self.core.volume = self._volume
			self.core.variant = self.variant
			self.core.rateBoost = self._rateBoost

	@property
	def name(self):
		return self._name

	@name.setter
	def name(self, name):
		self._name = name

	@property
	def rate(self):
		return self._rate

	@rate.setter
	def rate(self, percent):
		self._rate = percent
		self.core.rate = self._rate

	@property
	def pitch(self):
		return self._pitch

	@pitch.setter
	def pitch(self, percent):
		self._pitch = percent
		self.core.pitch = self._pitch

	@property
	def volume(self):
		return self._volume

	@volume.setter
	def volume(self, percent):
		self._volume = percent
		self.core.volume = self._volume

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

	@property
	def rateBoost(self):
		return self._rateBoost

	@rateBoost.setter
	def rateBoost(self, value):
		self._rateBoost = value
		self.core.rateBoost = self._rateBoost

	def speak(self, text):
		def _speak():
			self.active()
			self.core.speak(text)
		self.taskManager.add_dispatch_task((self, _speak),)

	def stop(self):
		self.core.cancel()

	def pause(self):
		self.core.pause(True)

	def resume(self):
		self.core.pause(False)

	def close(self):
		pass

	@classmethod
	def ready(cls):
		return True

	@classmethod
	def engineOn(cls):
		if not cls.core:
			cls.core = cls.synth_driver_class()
			cls.core.wv = cls.engine

	@classmethod
	def engineOff(cls):
		if cls.core:
			cls.core.terminate()
			cls.core = None

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
