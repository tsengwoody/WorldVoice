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


def percent_property(attr):
	"""Return a property that keeps self._<attr> in sync with self.core.<attr>."""
	private_name = f"_{attr}"

	def getter(self):
		return getattr(self, private_name)

	def setter(self, percent):
		setattr(self, private_name, percent)
		if self.core and attr in [i.id for i in self.core.supportedSettings]:
			setattr(self.core, attr, percent)

	return property(getter, setter)


class Voice(object):
	core = None
	engine = ""
	synth_driver_class = None

	def __init__(self, id, taskManager):
		self.id = id
		self.taskManager = taskManager

		for p, t, d in VOICE_PARAMETERS:
			setattr(self, p, t(d))
			setattr(self, "commit_" + p, t(d))

		self.loadParameter()
		self.setCoreParameter()

	rate   = percent_property("rate")
	pitch  = percent_property("pitch")
	volume = percent_property("volume")
	inflection = percent_property("inflection")
	rateBoost = percent_property("rateBoost")

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

	def break_(self, time):
		raise NotImplementedError

	def index(self, index):
		raise NotImplementedError

	def active(self):
		if self.core and self.core.voice != self.id:
			self.setCoreParameter()

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
		raise NotImplementedError

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
		raise NotImplementedError

	def setCoreParameter(self):
		if self.core:
			self.core.voice = self.id
			vp = [i[0] for i in VOICE_PARAMETERS]
			ss = [i.id for i in self.core.supportedSettings]
			for attr in list(set(ss) & set(vp) - set(["variant"])):
				private_name = f"_{attr}"
				percent = getattr(self, private_name)
				setattr(self.core, attr, percent)

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
