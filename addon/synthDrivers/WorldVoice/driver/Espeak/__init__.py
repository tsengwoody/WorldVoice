from synthDrivers.espeak import SynthDriver
from synthDrivers.WorldVoice.driver import Voice


class Voice(Voice):
	core = None
	engine = "Espeak"
	synth_driver_class = SynthDriver
