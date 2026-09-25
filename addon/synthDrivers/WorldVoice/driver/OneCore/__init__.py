from .driver import OneCoreSynthDriver as SynthDriver
from synthDrivers.WorldVoice.driver import Voice


class Voice(Voice):
	core = None
	engine = "OneCore"
	synth_driver_class = SynthDriver

	def applyEngineSettings(self, core, snapshot):
		core.language = snapshot.language

	@classmethod
	def supportedSettings(cls):
		return ['voice', 'rate', 'rateBoost', 'pitch', 'volume', 'useWasapi']
