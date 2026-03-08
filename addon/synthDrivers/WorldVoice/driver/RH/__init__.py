from .driver import SynthDriver
from synthDrivers.WorldVoice.driver import Voice


class Voice(Voice):
	core = None
	engine = "RH"
	synth_driver_class = SynthDriver

	def __init__(self, id, name, taskManager, language=None):
		self.name = name
		self.language = language if language else "unknown"

		super().__init__(id=id, taskManager=taskManager)
