import os

import globalVars

from .driver.ibmeci import SynthDriver
from synthDrivers.WorldVoice.driver import Voice


class Voice(Voice):
	core = None
	engine = "IBM"
	synth_driver_class = SynthDriver
	workspace = os.path.join(globalVars.appArgs.configPath, "WorldVoice-workspace", "IBM")

	def __init__(self, id, name, taskManager, language=None):
		self.name = name
		self.language = language if language else "unknown"

		super().__init__(id=id, taskManager=taskManager)

	@classmethod
	def engineOn(cls):
		if not cls.core:
			cls.core = cls.synth_driver_class()
			cls.core.wv = cls.engine
			cls.core.language = ""
