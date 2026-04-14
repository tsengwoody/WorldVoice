#aisoundProxy32.py
#A part of NVDA AiSound 5 Synthesizer Add-On

import addonHandler
import os
from _bridge.clients.synthDriverHost32.synthDriver import SynthDriverProxy32


addonHandler.initTranslation()

class SynthDriver(SynthDriverProxy32):
	name = "aisound"
	# Translators: Description for a speech synthesizer.
	description = _("AiSound 5 (32 bit)")
	synthDriver32Path = os.path.abspath(os.path.dirname(__file__))
	synthDriver32Name = "aisound"
