from .driver import OneCoreSynthDriver as SynthDriver
from synthDrivers.WorldVoice.driver import Voice


class Voice(Voice):
	core = None
	engine = "OneCore"
	synth_driver_class = SynthDriver

	def __init__(self, id, name, taskManager, language=None):
		self.name = name
		self.language = language if language else "unknown"
		self.core.language = self.language

		super().__init__(id=id, taskManager=taskManager)
