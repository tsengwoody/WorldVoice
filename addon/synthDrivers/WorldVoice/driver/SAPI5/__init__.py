from synthDrivers.sapi5 import SynthDriver
from synthDrivers.WorldVoice.driver import Voice


class Voice(Voice):
	core = None
	engine = "SAPI5"
	synth_driver_class = SynthDriver
