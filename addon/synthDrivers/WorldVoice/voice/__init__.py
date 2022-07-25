import threading

import config

VOICE_PARAMETERS = [
	("rate", int, 50),
	("pitch", int, 50),
	("volume", int, 50),
	("variant", str, ""),
	# ("waitfactor", int, 0),
]


class Voice(object):
	speaking = threading.Lock()

	def __init__(self):
		self.rate = 50
		self.pitch = 50
		self.volume = 50

		self.variant = ""
		self.waitfactor = 0

		self.commitRate = 50
		self.commitPitch = 50
		self.commitVolume = 50

		self.loadParameter()

	@property
	def rate(self):
		raise NotImplementedError

	@rate.setter
	def rate(self, percent):
		raise NotImplementedError

	@property
	def pitch(self):
		raise NotImplementedError

	@pitch.setter
	def pitch(self, percent):
		raise NotImplementedError

	@property
	def volume(self):
		raise NotImplementedError

	@volume.setter
	def volume(self, percent):
		raise NotImplementedError

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
		raise NotImplementedError

	def break_(self, time):
		raise NotImplementedError

	def index(self, index):
		raise NotImplementedError

	def stop(self):
		raise NotImplementedError

	def pause(self):
		raise NotImplementedError

	def resume(self):
		raise NotImplementedError

	def close(self):
		raise NotImplementedError

	@classmethod
	def ready(cls):
		raise NotImplementedError

	@classmethod
	def engineOn(cls, lock=None, taskManager=None):
		raise NotImplementedError

	@classmethod
	def engineOff(cls, taskManager=None):
		raise NotImplementedError

	@classmethod
	def voices(cls):
		raise NotImplementedError

	def loadParameter(self):
		voiceName = self.name
		if voiceName in config.conf["WorldVoice"]["voices"]:
			for p, t, _ in VOICE_PARAMETERS:
				if config.conf["WorldVoice"]["autoLanguageSwitching"]["KeepMainLocaleParameterConsistent"]:
					try:
						value = config.conf["speech"][getSynth().name].get(p, None)
					except BaseException:
						value = config.conf["WorldVoice"]['voices'][voiceName].get(p, None)
				else:
					value = config.conf["WorldVoice"]['voices'][voiceName].get(p, None)
				if value is None:
					continue
				setattr(self, p, t(value))
		else:
			config.conf["WorldVoice"]["voices"][voiceName] = {}
			for p, t, d in VOICE_PARAMETERS:
				config.conf["WorldVoice"]['voices'][voiceName][p] = t(d)
				setattr(self, p, t(d))

		self.commitRate = self.rate
		self.commitPitch = self.pitch
		self.commitVolume = self.volume

	def commit(self):
		self.commitRate = self.rate
		self.commitPitch = self.pitch
		self.commitVolume = self.volume

		voiceName = self.name
		if voiceName not in config.conf["WorldVoice"]["voices"]:
			config.conf["WorldVoice"]["voices"][voiceName] = {}
		for p, t, _ in VOICE_PARAMETERS:
			config.conf["WorldVoice"]["voices"][voiceName][p] = t(getattr(self, p))

	def rollback(self):
		self.rate = self.commitRate
		self.pitch = self.commitPitch
		self.volume = self.commitVolume

		voiceName = self.name
		if voiceName not in config.conf["WorldVoice"]["voices"]:
			config.conf["WorldVoice"]["voices"][voiceName] = {}
		for p, t, _ in VOICE_PARAMETERS:
			config.conf["WorldVoice"]["voices"][voiceName][p] = t(getattr(self, p))
