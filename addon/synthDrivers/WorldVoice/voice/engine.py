from enum import Enum

import addonHandler

addonHandler.initTranslation()


class EngineType(Enum):
	OneCore = (
		"synthDrivers.WorldVoice.voice.OneCore.voice",
		"OneCoreVoice",
		_("Enable OneCore")
	)
	SAPI5 = (
		"synthDrivers.WorldVoice.voice.SAPI5.voice",
		"Sapi5Voice",
		_("Enable SAPI5")
	)
	Espeak = (
		"synthDrivers.WorldVoice.voice.Espeak.voice",
		"EspeakVoice",
		_("Enable Espeak")
	)
	RH = (
		"synthDrivers.WorldVoice.voice.RH.voice",
		"RHVoice",
		_("Enable RH")
	)
	IBM = (
		"synthDrivers.WorldVoice.voice.IBM.voice",
		"IBMVoice",
		_("Enable IBM")
	)
	VE = (
		"synthDrivers.WorldVoice.voice.VE.voice",
		"VEVoice",
		_("Enable VE")
	)

	@property
	def module_path(self) -> str:
		# e.g. "voice.VEVoice"
		return self.value[0]

	@property
	def class_name(self) -> str:
		# e.g. "VEVoice"
		return self.value[1]

	@property
	def label(self) -> str:
		# e.g. "VE"
		return self.value[2]

	@property
	def default_enabled(self) -> bool:
		# default enabled
		return self in [EngineType.VE, EngineType.OneCore, EngineType.SAPI5]

	@property
	def name(self) -> str:
		# e.g. "VE"
		return self._name_
