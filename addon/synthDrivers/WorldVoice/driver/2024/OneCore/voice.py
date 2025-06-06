import languageHandler
import winVersion

from .driver import OneCoreSynthDriver
from .. import Voice


class OneCoreVoice(Voice):
	core = None
	engine = "OneCore"
	def __init__(self, id, name, taskManager, language=None):
		self.name = name
		self.language = language if language else "unknown"

		super().__init__(id=id, taskManager=taskManager)

		self.core.voice = self.id
		self.core.language = self.language
		self.core.pitch = self._pitch
		self.core.rate = self._rate
		self.core.volume = self._volume
		self.core.rateBoost = self._rateBoost

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
		return winVersion.getWinVer() >= winVersion.WIN10

	@classmethod
	def engineOn(cls):
		if not cls.core:
			cls.core = OneCoreSynthDriver()

	@classmethod
	def engineOff(cls):
		if cls.core:
			cls.core.terminate()
			cls.core = None

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
