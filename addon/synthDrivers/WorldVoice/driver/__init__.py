import threading

import config
from synthDriverHandler import getSynth


def boolean(value):
	if isinstance(value, str):
		if value in ["False", "false"]:
			return False
		else:
			return True
	else:
		return bool(value)


VOICE_PARAMETERS = [
	("rate", int, 50),
	("pitch", int, 50),
	("volume", int, 50),
	("variant", str, "default"),
	("inflection", int, 50),
	("rateBoost", boolean, False),
]


class Voice(object):
	speaking = threading.Lock()

	def __init__(self, id, taskManager):
		self.id = id
		self.taskManager = taskManager

		for p, t, d in VOICE_PARAMETERS:
			setattr(self, p, t(d))
			setattr(self, "commit_" + p, t(d))

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
	def inflection(self):
		return self._inflection

	@inflection.setter
	def inflection(self, value):
		self._inflection = value

	@property
	def rateBoost(self):
		return self._rateBoost

	@rateBoost.setter
	def rateBoost(self, value):
		self._rateBoost = value

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
	def engineOn(cls):
		raise NotImplementedError

	@classmethod
	def engineOff(cls):
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

		for p, t, _ in VOICE_PARAMETERS:
			value = t(getattr(self, p))
			setattr(self, "commit_" + p, value)

	def commit(self):
		for p, t, _ in VOICE_PARAMETERS:
			value = t(getattr(self, p))
			setattr(self, "commit_" + p, value)

		voiceName = self.name
		if voiceName not in config.conf["WorldVoice"]["voices"]:
			config.conf["WorldVoice"]["voices"][voiceName] = {}
		for p, t, _ in VOICE_PARAMETERS:
			value = t(getattr(self, p))
			config.conf["WorldVoice"]["voices"][voiceName][p] = value

	def rollback(self):
		for p, t, _ in VOICE_PARAMETERS:
			value = t(getattr(self, "commit_" + p))
			setattr(self, p, value)

		voiceName = self.name
		if voiceName not in config.conf["WorldVoice"]["voices"]:
			config.conf["WorldVoice"]["voices"][voiceName] = {}
		for p, t, _ in VOICE_PARAMETERS:
			value = t(getattr(self, p))
			config.conf["WorldVoice"]["voices"][voiceName][p] = value
