from .driver import OneCoreSynthDriver as SynthDriver
from synthDrivers.WorldVoice.driver import Voice


class Voice(Voice):
	core = None
	engine = "OneCore"
	synth_driver_class = SynthDriver

	def __init__(self, id, name, taskManager, language=None):
		super().__init__(id=id, name=name, taskManager=taskManager, language=language)
		self.core.language = self.language

	@classmethod
	def supportedSettings(cls):
		return ['voice', 'rate', 'rateBoost', 'pitch', 'volume', 'useWasapi']
