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
			self.core.voice = self.id
			self.core.pitch = self._pitch
			self.core.rate = self._rate
			self.core.volume = self._volume
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
		self._variants = []
		return self._variants

	@property
	def variant(self):
		return self._variant

	@variant.setter
	def variant(self, value):
		self._variant = value

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
