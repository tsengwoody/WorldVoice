from .driver import SynthDriver
from synthDrivers.WorldVoice.driver import Voice


class Voice(Voice):
	core = None
	engine = "RHVoice"
	synth_driver_class = SynthDriver
