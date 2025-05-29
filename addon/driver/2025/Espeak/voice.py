from .driver import (SynthDriver as EspeakManager)
from .. import Voice


class EspeakVoice(Voice):
	core = None
	engine = "Espeak"

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
	def engineOn(cls, lock=None):
		if not cls.core:
			cls.core = EspeakManager(lock)

	@classmethod
	def engineOff(cls):
		if cls.core:
			cls.core.terminate()
			cls.core = None

	@classmethod
	def voices(cls):
		if not cls.core:
			return []
		return cls.core.availableVoices
