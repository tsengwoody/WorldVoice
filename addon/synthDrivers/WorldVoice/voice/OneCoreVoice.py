import winVersion

from ._onecore import OneCoreManager
from . import Voice


class OneCoreVoice(Voice):
	core = None

	def __init__(self, id, name, taskManager, language=None):
		self.engine = "OneCore"
		self.id = id
		self.taskManager = taskManager
		self.name = name
		self.language = language if language else "unknown"

		super().__init__()

		self.core.voice = self.id
		self.core.language = self.language
		self.core.pitch = self._pitch
		self.core.rate = self._rate
		self.core.volume = self._volume

	def active(self):
		if self.core.voice == self.id:
			return
		self.core.voice = self.id
		self.core.language = self.language
		self.core.pitch = self._pitch
		self.core.rate = self._rate
		self.core.volume = self._volume

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
	def waitfactor(self):
		return self._waitfactor

	@waitfactor.setter
	def waitfactor(self, value):
		self._waitfactor = value

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
	def engineOn(cls, lock):
		if not cls.core:
			cls.core = OneCoreManager(lock)

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
		return cls.core.availableVoices
